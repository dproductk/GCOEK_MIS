# GCOEK MIS — Runbook

> **Purpose:** Complete setup, run, migration, test, and debug instructions.
> A new developer or AI agent must be able to set up and run the project by following this document.

---

## 1. Prerequisites

| Software | Minimum Version | Notes |
|---|---|---|
| Python | 3.11+ | 3.13.5 installed on current dev machine |
| Node.js | 18+ | v24.13.0 installed on current dev machine |
| npm | 9+ | 11.6.2 installed on current dev machine |
| PostgreSQL | 14+ | 18.1 installed on current dev machine |

## 2. Database Setup

```bash
# Connect as PostgreSQL superuser and run:
CREATE DATABASE gceok_mis ENCODING 'UTF8';
CREATE USER gceok_app WITH PASSWORD '<your-password>';
GRANT ALL PRIVILEGES ON DATABASE gceok_mis TO gceok_app;
ALTER DATABASE gceok_mis OWNER TO gceok_app;
```

## 3. Backend Setup

```bash
cd backend/

# Create virtual environment
python -m venv .venv

# Activate (Windows PowerShell)
.\.venv\Scripts\Activate.ps1

# Activate (Linux/Mac)
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Copy environment template and fill in values
cp .env.example .env
# Edit .env with your database credentials and secret key

# Run migrations
python manage.py migrate

# Create superuser (for initial Sysadmin access)
python manage.py createsuperuser

# Start development server
python manage.py runserver
```

Backend runs at: `http://localhost:8000`
API base: `http://localhost:8000/api/v1/`

## 4. Frontend Setup

```bash
cd frontend/

# Install dependencies
npm install

# Copy environment template
cp .env.example .env
# Edit .env if needed (API URL defaults to http://localhost:8000)

# Start development server
npm run dev
```

Frontend runs at: `http://localhost:5173`

## 5. Environment Variables

### Backend (`backend/.env`)

| Variable | Description | Example |
|---|---|---|
| `SECRET_KEY` | Django secret key | (auto-generated) |
| `DEBUG` | Debug mode | `True` (dev only) |
| `DB_NAME` | Database name | `gceok_mis` |
| `DB_USER` | Database user | `gceok_app` |
| `DB_PASSWORD` | Database password | (your password) |
| `DB_HOST` | Database host | `localhost` |
| `DB_PORT` | Database port | `5432` |
| `ALLOWED_HOSTS` | Allowed host headers | `localhost,127.0.0.1` |
| `CORS_ALLOWED_ORIGINS` | CORS origins | `http://localhost:5173` |

### Frontend (`frontend/.env`)

| Variable | Description | Example |
|---|---|---|
| `VITE_API_BASE_URL` | Backend API URL | `http://localhost:8000` |

## 6. Running Tests

```bash
# Backend
cd backend/
pytest

# Frontend
cd frontend/
npm test
```

## 7. Database Migrations

```bash
cd backend/

# Check for pending migrations
python manage.py showmigrations

# Create new migrations after model changes
python manage.py makemigrations

# Apply migrations
python manage.py migrate
```

## 8. Project Structure

See `docs/FILE_MAP.md` for the complete file navigation map.

## 9. Important Notes

- **Never commit:** `.env` files, `.venv/`, `node_modules/`, `__pycache__/`, database credentials, JWT secrets, encryption keys.
- **Database changes:** Always use Django migrations. Never manually alter the database schema.
- **API versioning:** All endpoints live under `/api/v1/`.
- **Design reference:** Visual design follows `design/the software/edvana-style-system.css` and reference screenshots.
