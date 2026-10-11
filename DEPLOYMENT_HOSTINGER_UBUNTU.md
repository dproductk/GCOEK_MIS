# GCOEK MIS — Production Deployment Guide (Hostinger Ubuntu VPS)

> **Target Platform:** Hostinger VPS  
> **Operating System:** Ubuntu 22.04 LTS / 24.04 LTS  
> **Stack Architecture:** Nginx (Reverse Proxy & Static Files) + Gunicorn (WSGI) + Django (REST API) + React/Vite (Frontend SPA) + PostgreSQL 15/16 + Let's Encrypt (SSL)

---

## Architecture Overview

```
                                      Internet
                                         │
                                   [ Port 80/443 ]
                                         │
                                   ┌─────▼─────┐
                                   │   Nginx   │ (SSL Termination, Rate Limits, Static Assets)
                                   └─────┬─────┘
                 ┌───────────────────────┼───────────────────────┐
                 │                       │                       │
           Static Files               API & Admin          Frontend SPA
       /static/ & /media/          /api/* & /admin/*             /*
                 │                       │                       │
      ┌──────────▼──────────┐     ┌──────▼──────┐     ┌──────────▼──────────┐
      │  /backend/staticfiles│     │  Gunicorn   │     │   /frontend/dist    │
      │  /backend/media     │     │ (127.0.0.1: │     │ (Vite compiled      │
      └─────────────────────┘     │    8000)    │     │  HTML/JS/CSS)       │
                                  └──────┬──────┘     └─────────────────────┘
                                         │
                                  ┌──────▼──────┐
                                  │ PostgreSQL  │ (Local unix socket /
                                  │ (Port 5432) │  localhost:5432)
                                  └─────────────┘
```

---

## Phase 1: Initial Server Setup & Hardening

Log in to your Hostinger VPS via SSH as `root`:
```bash
ssh root@<YOUR_VPS_IP>
```

### 1.1 Update the System Packages
```bash
sudo apt update && sudo apt upgrade -y
```

### 1.2 Create a Dedicated Deployment User
Do **not** run applications as `root`. Create a dedicated user (e.g., `misadmin`):
```bash
adduser misadmin
usermod -aG sudo misadmin
```
Switch to the new user:
```bash
su - misadmin
```

### 1.3 Configure UFW Firewall
Allow SSH, HTTP, and HTTPS before enabling the firewall:
```bash
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
sudo ufw status
```

---

## Phase 2: Install Required System Dependencies

Run the following command to install Python, PostgreSQL, Nginx, Git, build tools, and dependencies:
```bash
sudo apt install -y \
    python3 \
    python3-pip \
    python3-venv \
    python3-dev \
    postgresql \
    postgresql-contrib \
    nginx \
    git \
    curl \
    libpq-dev \
    build-essential
```

### 2.1 Install Node.js (v20 LTS for building the Frontend)
```bash
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs
node -v   # Should show v20.x.x
npm -v    # Should show v10.x.x
```

---

## Phase 3: PostgreSQL Database Setup

Log into the PostgreSQL CLI as the `postgres` user:
```bash
sudo -u postgres psql
```

Run these SQL commands (replace `'YourSecurePassword123!'` with a strong password):
```sql
-- Create database
CREATE DATABASE gceok_mis ENCODING 'UTF8';

-- Create dedicated database user
CREATE USER gceok_app WITH PASSWORD 'YourSecurePassword123!';

-- Configure database performance & encoding parameters
ALTER ROLE gceok_app SET client_encoding TO 'utf8';
ALTER ROLE gceok_app SET default_transaction_isolation TO 'read committed';
ALTER ROLE gceok_app SET timezone TO 'Asia/Kolkata';

-- Grant all permissions
GRANT ALL PRIVILEGES ON DATABASE gceok_mis TO gceok_app;
ALTER DATABASE gceok_mis OWNER TO gceok_app;

-- Exit psql
\q
```

---

## Phase 4: Deploy Codebase to `/var/www/gceok_mis`

### 4.1 Prepare Directory Structure
```bash
sudo mkdir -p /var/www/gceok_mis
sudo chown -R misadmin:www-data /var/www/gceok_mis
sudo chmod -R 775 /var/www/gceok_mis
```

### 4.2 Clone or Transfer the Code
Either clone your repository or use `rsync`/`scp` from your local machine:
```bash
git clone <YOUR_GIT_REPO_URL> /var/www/gceok_mis
```
*(If transferring manually via scp, copy files into `/var/www/gceok_mis`)*

Ensure proper ownership:
```bash
sudo chown -R misadmin:www-data /var/www/gceok_mis
```

---

## Phase 5: Backend Setup & Environment Configuration

### 5.1 Create Virtual Environment & Install Dependencies
```bash
cd /var/www/gceok_mis/backend
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### 5.2 Generate Cryptographic Keys for `.env`
Run these commands in terminal to generate random cryptographic keys:

1. **Django Secret Key**:
```bash
python3 -c "import secrets; print(secrets.token_urlsafe(50))"
```
2. **PII Field Encryption Key (Fernet 32-byte)**:
```bash
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

### 5.3 Create `/var/www/gceok_mis/backend/.env`
Create the production environment file:
```bash
nano /var/www/gceok_mis/backend/.env
```

Paste and adjust the following configuration:
```ini
# ============================================================================
# GCOEK MIS - Production Environment Configuration
# ============================================================================

# Core Django Settings
DEBUG=False
SECRET_KEY=PASTE_THE_GENERATED_SECRET_KEY_HERE
FIELD_ENCRYPTION_KEY=PASTE_THE_GENERATED_FERNET_KEY_HERE

# Allowed Domain Names (Replace with your actual domain or VPS IP)
ALLOWED_HOSTS=yourdomain.com,www.yourdomain.com,127.0.0.1,localhost

# Database Configuration (PostgreSQL)
DB_NAME=gceok_mis
DB_USER=gceok_app
DB_PASSWORD=YourSecurePassword123!
DB_HOST=127.0.0.1
DB_PORT=5432

# CORS & CSRF Trusted Origins
CORS_ALLOWED_ORIGINS=https://yourdomain.com,https://www.yourdomain.com
CSRF_TRUSTED_ORIGINS=https://yourdomain.com,https://www.yourdomain.com

# Online Payment Gateway (Disabled per institutional directive)
EASEBUZZ_ENABLED=False
EASEBUZZ_ENV=production
EASEBUZZ_KEY=
EASEBUZZ_SALT=

# Static & Media Directory Paths
STATIC_ROOT=/var/www/gceok_mis/backend/staticfiles
MEDIA_ROOT=/var/www/gceok_mis/backend/media
```
Save and exit (`Ctrl+O`, `Enter`, `Ctrl+X`).

Lock permissions so only `misadmin` and the app can read it:
```bash
chmod 600 /var/www/gceok_mis/backend/.env
```

### 5.4 Run Migrations, Collect Static Files & Seed Admin
Ensure your virtual environment is active (`source venv/bin/activate`):
```bash
cd /var/www/gceok_mis/backend

# 1. Apply all database migrations
python manage.py migrate

# 2. Collect static files for Nginx to serve (Django Admin, DRF browsable API)
python manage.py collectstatic --noinput

# 3. Create media folder and set permissions
mkdir -p /var/www/gceok_mis/backend/media
sudo chown -R misadmin:www-data /var/www/gceok_mis/backend/media
sudo chmod -R 775 /var/www/gceok_mis/backend/media

# 4. Seed system roles (Sysadmin, HOD, Teacher, Student, etc.)
python manage.py seed_auth_roles

# 5. Create the Initial Superuser / Sysadmin
python manage.py createsuperuser

# 6. Link a Faculty card to a pre-existing staff login (idempotent; safe to
# re-run). Needed for any staff account (e.g. admin_head) that must open the
# Faculty Profile page — without a card the page shows an empty state.
# The account itself must already exist; this never creates users/passwords.
python manage.py ensure_staff_faculty_card \
  --username admin_head --employee-code ADMIN_HEAD01 \
  --department-code CSE --date-of-joining 2020-06-01
```

---

## Phase 6: Frontend Build (Vite / React)

### 6.1 Configure Frontend Production API URL
Edit or create `/var/www/gceok_mis/frontend/.env.production`:
```bash
nano /var/www/gceok_mis/frontend/.env.production
```
Paste:
```ini
# When served on the same domain behind Nginx, relative path or full domain works:
VITE_API_BASE_URL=https://yourdomain.com
```

### 6.2 Install Packages & Build Production Bundle
```bash
cd /var/www/gceok_mis/frontend
npm install
npm run build
```
Verify that the `dist/` directory was created:
```bash
ls -la /var/www/gceok_mis/frontend/dist/
```

---

## Phase 7: Gunicorn & Systemd Service

We manage Gunicorn with systemd so it automatically starts on boot and restarts if it ever crashes.

### 7.1 Create Systemd Service File
```bash
sudo nano /etc/systemd/system/gceok_mis.service
```

Paste the following service configuration:
```ini
[Unit]
Description=GCOEK MIS Gunicorn Application Server
After=network.target postgresql.service

[Service]
Type=notify
User=misadmin
Group=www-data
WorkingDirectory=/var/www/gceok_mis/backend
Environment="PATH=/var/www/gceok_mis/backend/venv/bin"
ExecStart=/var/www/gceok_mis/backend/venv/bin/gunicorn \
          --workers 3 \
          --bind 127.0.0.1:8000 \
          --timeout 90 \
          --access-logfile /var/log/gunicorn-access.log \
          --error-logfile /var/log/gunicorn-error.log \
          gceok_core.wsgi:application
ExecReload=/bin/kill -s HUP $MAINPID
KillMode=mixed
TimeoutStopSec=10
PrivateTmp=true
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

### 7.2 Prepare Log Files & Permissions
```bash
sudo touch /var/log/gunicorn-access.log /var/log/gunicorn-error.log
sudo chown misadmin:www-data /var/log/gunicorn-access.log /var/log/gunicorn-error.log
```

### 7.3 Start & Enable Gunicorn
```bash
sudo systemctl daemon-reload
sudo systemctl start gceok_mis
sudo systemctl enable gceok_mis
sudo systemctl status gceok_mis
```
*(You should see `active (running)` in green).*

---

## Phase 8: Nginx Configuration

Nginx acts as the reverse proxy, handles SSL termination, and directly serves both the compiled React frontend SPA and Django static assets.

### 8.1 Create Nginx Site Configuration
```bash
sudo nano /etc/nginx/sites-available/gceok_mis
```

Paste the following configuration (replace `yourdomain.com` with your actual domain name):
```nginx
server {
    listen 80;
    server_name yourdomain.com www.yourdomain.com;

    # Maximum file upload size (documents/certificates)
    client_max_body_size 25M;

    # Gzip Compression
    gzip on;
    gzip_vary on;
    gzip_min_length 1024;
    gzip_proxied any;
    gzip_types text/plain text/css application/json application/javascript text/xml application/xml application/xml+rss text/javascript image/svg+xml;

    # 1. Django Static Files (Admin, DRF)
    location /static/ {
        alias /var/www/gceok_mis/backend/staticfiles/;
        expires 30d;
        add_header Cache-Control "public, max-age=2592000, immutable";
    }

    # 2. Django Media Files (Uploaded documents)
    location /media/ {
        alias /var/www/gceok_mis/backend/media/;
        expires 7d;
        add_header Cache-Control "public, max-age=604800";
    }

    # 3. Backend API
    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 90s;
        proxy_connect_timeout 90s;
    }

    # 4. Django Admin Panel
    location /admin/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # 5. Frontend React SPA (Catch-all)
    location / {
        root /var/www/gceok_mis/frontend/dist;
        index index.html;
        try_files $uri $uri/ /index.html;
    }
}
```

### 8.2 Enable Site & Test Configuration
```bash
# Enable the configuration
sudo ln -s /etc/nginx/sites-available/gceok_mis /etc/nginx/sites-enabled/

# Remove default nginx site if still active
sudo rm -f /etc/nginx/sites-enabled/default

# Test Nginx syntax
sudo nginx -t

# Reload Nginx
sudo systemctl restart nginx
```

---

## Phase 9: SSL Certificate (HTTPS) via Let's Encrypt

### 9.1 Install Certbot
```bash
sudo apt install -y certbot python3-certbot-nginx
```

### 9.2 Request SSL Certificate
*Make sure your DNS records (`A` record pointing to your Hostinger VPS IP) have already propagated!*
```bash
sudo certbot --nginx -d yourdomain.com -d www.yourdomain.com
```
Follow the interactive prompts:
1. Enter your administrator email.
2. Accept the terms of service (`Y`).
3. Certbot will automatically verify domain ownership, generate SSL certificates, and configure Nginx to redirect HTTP traffic to HTTPS.

### 9.3 Verify Auto-Renewal
Certbot automatically creates a systemd timer for renewals:
```bash
sudo systemctl status certbot.timer
sudo certbot renew --dry-run
```

---

## Phase 10: Hostinger Backups & Disaster Recovery

While Hostinger VPS creates automated server snapshots, standard institutional policy requires maintaining independent database backups.

### 10.1 Automated Daily Database Backup Script
Create `/home/misadmin/backup_db.sh`:
```bash
nano /home/misadmin/backup_db.sh
```
Paste:
```bash
#!/bin/bash
BACKUP_DIR="/home/misadmin/backups/db"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
FILENAME="$BACKUP_DIR/gceok_mis_$TIMESTAMP.sql.gz"

mkdir -p "$BACKUP_DIR"

# Perform compressed dump
PGPASSWORD="YourSecurePassword123!" pg_dump -U gceok_app -h 127.0.0.1 gceok_mis | gzip > "$FILENAME"

# Delete backups older than 14 days
find "$BACKUP_DIR" -type f -name "*.sql.gz" -mtime +14 -delete
```

Make it executable:
```bash
chmod +x /home/misadmin/backup_db.sh
```

### 10.2 Add Cron Job for 2:00 AM Daily Run
```bash
crontab -e
```
Add the line:
```cron
0 2 * * * /home/misadmin/backup_db.sh > /dev/null 2>&1
```

### 10.3 Emergency Database Restore Command
If ever needed:
```bash
gunzip -c /home/misadmin/backups/db/gceok_mis_YYYYMMDD_HHMMSS.sql.gz | PGPASSWORD="YourSecurePassword123!" psql -U gceok_app -h 127.0.0.1 -d gceok_mis
```

---

## Phase 11: Future Updates & Maintenance Cheat Sheet

When deploying future code updates from git, run this simple sequence:

```bash
cd /var/www/gceok_mis

# 1. Pull latest changes
git pull origin main

# 2. Update Backend
cd /var/www/gceok_mis/backend
source venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py collectstatic --noinput
sudo systemctl restart gceok_mis

# 3. Update Frontend
cd /var/www/gceok_mis/frontend
npm install
npm run build

# 4. Check status
sudo systemctl status gceok_mis
```

### Handy Debugging Commands
- **Check Gunicorn Logs**: `journalctl -u gceok_mis -n 100 --no-pager` or `tail -f /var/log/gunicorn-error.log`
- **Check Nginx Logs**: `sudo tail -f /var/log/nginx/error.log`
- **Restart Backend**: `sudo systemctl restart gceok_mis`
- **Restart Nginx**: `sudo systemctl restart nginx`
