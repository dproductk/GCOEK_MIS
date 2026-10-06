# SECURITY.md

# College Student Management & Administrative Data System

## Security Contract for Django + DRF + React + PostgreSQL

> **Purpose:** This document is the security contract for the software.
> AI coding agents and developers MUST follow these rules when
> implementing, modifying, reviewing, or deploying the system.

## 1. Security Principles

1.  Security is a system requirement, not an optional feature.
2.  Backend authorization is authoritative. Frontend checks are only UX.
3.  Follow least privilege and deny access by default.
4.  Sensitive data must be minimized, protected, masked, and audited.
5.  Never weaken a security control merely to make a feature work.
6.  Never hardcode secrets, credentials, tokens, encryption keys, or
    passwords.
7.  Security-sensitive operations must be atomic, auditable, and
    resistant to replay/duplication.
8.  Never silently bypass validation, authorization, audit logging, or
    business invariants.
9.  Production must never expose debug information or stack traces.
10. Any security-impacting architectural change must be documented
    before implementation.

------------------------------------------------------------------------

## 2. Authentication & Authorization

### 2.1 Django/DRF Authentication

-   Use JWT authentication with refresh tokens.
-   Use `djangorestframework-simplejwt`.
-   Access tokens should be short-lived: approximately 15--30 minutes.
-   Refresh tokens should be longer-lived: approximately 7 days, subject
    to the deployment security policy.
-   Store refresh tokens in HttpOnly cookies, not localStorage.
-   Rotate refresh tokens.
-   Revoke/blacklist refresh tokens on logout where supported by the
    chosen implementation.

### 2.2 Password Security

-   Use Django's secure password hashing, preferably Argon2 where
    supported and approved.
-   Minimum password length: 12 characters.
-   Enforce appropriate password complexity.
-   Require first-login password change using a `must_change_password`
    flag where applicable.
-   Prevent reuse of the last 5 passwords.
-   Lock or temporarily throttle accounts after 5 failed login attempts
    for approximately 15 minutes.
-   Never store plaintext passwords.
-   Never log passwords or authentication credentials.
-   Never create universal/default passwords for real accounts.

### 2.3 MFA

-   Require TOTP-based MFA for System Administrator and other designated
    high-privilege administrative roles.
-   Use a maintained implementation such as `django-otp` or `pyotp`.

### 2.4 RBAC + Scope

The system uses role-based and scope-based authorization.

Examples:

-   System Admin → system-wide scope
-   Register → Student Section scope
-   HOD → Department scope
-   Class Teacher → assigned batch/class scope
-   Teacher → assigned subject/batch scope
-   Accountant → fee operations
-   Student → own permitted records

Rules:

-   Implement explicit DRF permission classes.
-   Enforce authorization at queryset/data-access level where required.
-   Never rely only on frontend role checks.
-   Never trust a user-supplied `student_id`, `department_id`,
    `batch_id`, etc. without verifying scope.
-   Object-level authorization must prevent IDOR/BOLA vulnerabilities.
-   A user must never access another user's records merely by changing
    an identifier in a URL or request body.

------------------------------------------------------------------------

## 3. React Authentication & Route Security

-   Store short-lived access tokens in memory where possible.
-   Store refresh tokens in HttpOnly, Secure cookies.
-   Never store long-lived authentication secrets in localStorage.
-   Clear authentication state on logout.
-   Protect frontend routes for usability, but treat those checks as
    non-authoritative.
-   Redirect or re-authenticate appropriately on 401 responses.
-   Handle 403 responses without exposing sensitive information.

------------------------------------------------------------------------

## 4. Sensitive Data Protection

Sensitive information may include:

-   Aadhaar-related data
-   Bank account information
-   Personal contact information
-   Student documents
-   Faculty personal information
-   Financial/fee records
-   Academic results
-   Authentication data
-   Audit/security records

### 4.1 Encryption

-   Sensitive fields must be encrypted at rest where required by the
    data classification.
-   The supplied security design allows either PostgreSQL `pgcrypto` or
    application-level encryption using a maintained cryptography
    library.
-   Encryption keys MUST come from secure environment/secret management.
-   Never place encryption keys in source code.
-   Never commit secrets to Git.

### 4.2 Masking

Sensitive values must be masked by default.

Example:

`********1234`

Rules:

-   Default serializers must not expose encrypted sensitive fields.
-   Use dedicated serializers/fields for masking.
-   Full-value reveal requires explicit authorization.
-   Reveal operations must be audited.
-   UI should auto-hide revealed sensitive values after a short period.

### 4.3 Sensitive Data Reveal

A reveal operation requires:

1.  Specific permission.
2.  Valid business justification/reason where required.
3.  Audit-log entry.
4.  Actor identity.
5.  Timestamp.
6.  Target record.
7.  Appropriate scope validation.

Never expose sensitive values in:

-   Console logs
-   Error messages
-   URLs
-   Analytics events
-   Debug pages
-   API responses that do not require them
-   Audit logs

------------------------------------------------------------------------

## 5. File & Document Security

The system may handle student/faculty documents and government-provided
files.

Rules:

-   Do not trust file extensions.
-   Validate MIME/content using a content-aware mechanism such as
    `python-magic`.
-   Scan uploaded files for malware where infrastructure permits,
    e.g. ClamAV.
-   Enforce file size limits.
-   Store uploaded files outside the public web root/object-public
    namespace.
-   Use authenticated access or short-lived presigned URLs.
-   Never expose predictable public file paths for sensitive documents.
-   Validate file ownership and authorization before every
    download/view.
-   Prevent path traversal.
-   Preserve document version/history according to the architecture.
-   Never execute uploaded files.

------------------------------------------------------------------------

## 6. Input Validation

### Backend

All external input must be treated as untrusted.

-   Use DRF serializers for API input validation.
-   Validate type, length, format, range, and allowed values.
-   Use custom validators for domain/business rules.
-   Validate identifiers such as enrollment number, mobile number,
    email, and application number.
-   Validate imported Excel data before production insertion.
-   Reject malformed or unexpected input safely.

### Frontend

-   Validate inputs before submission for usability.
-   Use controlled components.
-   Never assume frontend validation is sufficient.
-   Backend validation remains authoritative.

------------------------------------------------------------------------

## 7. Injection Protection

### SQL Injection

-   Prefer Django ORM.
-   Never concatenate user input into SQL.
-   If raw SQL is unavoidable, use parameterized queries.
-   Never build SQL using string interpolation or formatting with user
    input.

### Command Injection

-   Never pass user-controlled data to shell commands.
-   Do not use `os.system()` with user input.
-   If subprocess execution is genuinely required, use argument arrays
    and `shell=False`.
-   Validate every argument.

### Path Traversal

-   Never concatenate untrusted input directly into filesystem paths.
-   Resolve paths and verify that they remain inside an explicitly
    allowed directory.
-   Prefer generated storage keys rather than user-controlled filenames.

------------------------------------------------------------------------

## 8. XSS & Browser Security

React rules:

-   Never use `dangerouslySetInnerHTML` unless there is a documented,
    necessary reason.
-   If HTML rendering is genuinely required, sanitize it with a
    maintained sanitizer such as DOMPurify.
-   Escape/render user-controlled text safely.
-   Never insert unsanitized HTML from database fields.

Production security headers should include, where compatible with the
deployment:

-   `X-Content-Type-Options: nosniff`
-   `X-Frame-Options: DENY`
-   Strict-Transport-Security (HSTS)
-   `Content-Security-Policy`
-   `Referrer-Policy`

Do not enable headers blindly if they break required application
behavior; test them properly.

------------------------------------------------------------------------

## 9. CSRF, Cookies & Sessions

Where cookie-based authentication is used:

-   Enable Django CSRF protection.
-   Use Secure cookies in production.
-   Use HttpOnly for authentication cookies.
-   Use an appropriate SameSite policy (`Lax` or `Strict` where
    compatible).
-   Rotate session/authentication identifiers appropriately.
-   Never disable CSRF protection as a shortcut.
-   Never accept state-changing requests solely because a frontend says
    they are trusted.

------------------------------------------------------------------------

## 10. API Security

### Rate Limiting

Use DRF throttling or an equivalent maintained mechanism.

Initial target limits from the security design:

-   Login: approximately 5 attempts/minute.
-   General API: approximately 1000 requests/hour/user.
-   Import uploads: approximately 10/hour.

These are starting policies and should be adjusted using actual
workload/security requirements.

### CORS

-   Use an explicit allowlist.
-   Never use `CORS_ALLOW_ALL_ORIGINS = True` in production.
-   Allow only known frontend origins.

### Request Limits

-   Validate Content-Type.
-   Set request/body size limits.
-   Validate pagination parameters.
-   Limit expensive query parameters and unbounded result sets.

### API Versioning

Use versioned endpoints such as:

`/api/v1/`

Do not silently break existing API contracts.

### Idempotency

Use idempotency protection for operations where duplicate requests can
cause corruption, especially:

-   Payments
-   Financial charges
-   Imports
-   Result publication
-   Other irreversible state-changing operations

------------------------------------------------------------------------

## 11. Database Security

### PostgreSQL Connection

-   Use TLS/SSL for production database connections.
-   Use secure database credentials.
-   Never use the PostgreSQL superuser for the application.
-   Restrict network/database access.

### Database Users

Where operationally supported:

-   Application user → only required runtime permissions.
-   Migration/deployment user → DDL permissions, used only when
    migrations run.
-   Administrative/superuser credentials → never embedded in the
    application.

### Constraints

Security-critical invariants must also be protected at database level
where appropriate:

-   UNIQUE
-   FOREIGN KEY
-   NOT NULL
-   CHECK
-   appropriate transaction isolation/locking

Never rely only on frontend validation for data integrity.

### Critical Transactions

Use transactions and row locking where necessary, especially for:

-   Payments
-   Fee account changes
-   Result publication
-   Other concurrent state transitions

Use mechanisms such as `SELECT ... FOR UPDATE` only where justified by
the transaction design.

------------------------------------------------------------------------

## 12. Audit Logging

Security-sensitive and business-critical operations must be auditable.

At minimum, audit:

-   Login/security events
-   Permission-sensitive actions
-   Sensitive-data reveals
-   Student record corrections
-   Financial operations
-   Payment recording
-   Result changes/publication
-   Government imports
-   Document verification
-   Administrative configuration changes

Audit entries should capture, where appropriate:

-   Actor
-   Timestamp
-   Action
-   Target entity
-   Target identifier
-   IP address
-   User agent
-   Relevant old/new values or change summary
-   Reason where required

### Never log

-   Passwords
-   Access/refresh tokens
-   Encryption keys
-   Full Aadhaar numbers
-   Full bank account numbers
-   Other secrets or sensitive values unnecessarily

Audit logs should be append-only from normal application workflows. Any
retention/deletion policy must be explicitly defined rather than
silently implemented.

------------------------------------------------------------------------

## 13. Error Handling

Production responses must not expose:

-   Stack traces
-   SQL queries
-   Secret values
-   Internal filesystem paths
-   Database credentials
-   Debug information
-   Internal security decisions that aid attackers

Use safe user-facing error messages.

Detailed errors may be sent to a secured monitoring system such as
Sentry, provided sensitive information is filtered.

Never put raw request bodies containing sensitive information into error
logs.

------------------------------------------------------------------------

## 14. Government Excel Import Security

Government imports are a high-risk boundary because they contain
external data.

Pipeline:

`Upload → Validate → Scan → Stage → Validate/Normalize → Deduplicate → Import`

Rules:

-   Validate file type.
-   Enforce file-size limits.
-   Scan where possible.
-   Calculate/store checksum.
-   Preserve the original source file according to retention policy.
-   Preserve source row number and raw row data in staging.
-   Validate every row before production insertion.
-   Never directly import external Excel rows into production tables.
-   Make imports idempotent.
-   Reprocessing the same source must not create duplicate students.
-   Enforce the matching/deduplication rules defined by
    `DATABASE_ARCHITECTURE.md`.
-   Log who uploaded, validated, approved, imported, failed, or
    cancelled an import.
-   Never execute macros or embedded spreadsheet content.

------------------------------------------------------------------------

## 15. Financial & Payment Security

Financial records require stronger controls.

Rules:

-   A payment is a financial event; never treat it as merely a boolean
    flag.
-   Use database transactions for payment recording.
-   Use idempotency keys where applicable.
-   Prevent duplicate payment recording.
-   Use row-level locking when required by the transaction.
-   Never trust client-provided totals.
-   Recalculate/verify amounts on the backend.
-   Validate fee structure, charge, student account, payment amount, and
    permitted operation.
-   Never store raw card/bank authentication credentials.
-   Record actor and audit information for financial changes.
-   Corrections must use controlled reversal/correction workflows rather
    than destructive edits.

------------------------------------------------------------------------

## 16. Result Publication Security

Result data is sensitive academic information.

Rules:

-   Use controlled states such as:
    `DRAFT → PROCESSING → VALIDATED → APPROVED → PUBLISHED`
-   Publication must be atomic.
-   Only authorized users can approve/publish.
-   Published results must not be silently overwritten.
-   Corrections must create a controlled correction/supersession
    history.
-   Log who changed, approved, published, or corrected results.
-   Verify the applicable scheme/subject/result context before
    publication.
-   Prevent students or unauthorized staff from accessing another
    student's results.

------------------------------------------------------------------------

## 17. Documents & Sensitive Profile Data

For student and faculty profiles:

-   Separate sensitive domain data from general profile data.
-   Return only fields required for the current role/use case.
-   Use scoped authorization for profile access.
-   Mask sensitive fields by default.
-   Protect document downloads individually.
-   Keep document verification/replacement history.
-   Do not expose internal storage keys unnecessarily.
-   Do not put sensitive information in URLs or frontend route
    parameters.

------------------------------------------------------------------------

## 18. Secrets & Environment Configuration

Never commit:

-   Django `SECRET_KEY`
-   JWT signing secrets/keys
-   Database passwords
-   API keys
-   Encryption keys
-   Cloud storage credentials
-   SMTP credentials
-   Third-party service tokens

Rules:

-   Use environment variables for local/staging configuration.
-   Use a proper secret manager for production where available.
-   Maintain separate credentials for development, staging, and
    production.
-   Rotate compromised credentials immediately.
-   Never print environment variables for debugging.
-   Add secret files to `.gitignore`.

If a secret is accidentally committed, treat it as compromised and
rotate it; deleting it from the latest commit is not sufficient.

------------------------------------------------------------------------

## 19. Infrastructure & Deployment Security

Production:

-   Enforce HTTPS.
-   Redirect HTTP to HTTPS.
-   Enable HSTS after verifying HTTPS deployment.
-   Keep OS/runtime/dependencies patched.
-   Restrict firewall/network access.
-   Disable unnecessary services.
-   Do not permit root application execution.
-   Use SSH keys rather than password authentication where applicable.
-   Use non-root Docker containers where practical.
-   Prefer official/minimal base images.
-   Scan container images for known vulnerabilities.
-   Keep production debug mode disabled.
-   Restrict administrative endpoints.
-   Do not expose PostgreSQL publicly unless explicitly required and
    secured.

------------------------------------------------------------------------

## 20. Dependency Security

Before adding a dependency:

1.  Confirm it is actually necessary.
2.  Prefer maintained, reputable packages.
3.  Check licensing and maintenance status where relevant.
4.  Avoid unnecessary packages that expand attack surface.

Regularly:

-   Run `npm audit`/equivalent frontend dependency checks.
-   Run Python dependency vulnerability scanning.
-   Run static security analysis such as Bandit where applicable.
-   Review dependency updates before production deployment.
-   Remove unused dependencies.

Never blindly run automated dependency upgrades in production without
testing.

------------------------------------------------------------------------

## 21. Backup & Recovery Security

Backups must be:

-   Encrypted at rest.
-   Access-controlled.
-   Stored separately from the primary database.
-   Protected against accidental deletion.
-   Tested through regular restore exercises.

A backup that has never been restored successfully should not be treated
as a verified recovery mechanism.

Document:

-   Backup frequency
-   Retention
-   Encryption
-   Access
-   Restore procedure
-   Recovery objectives

------------------------------------------------------------------------

## 22. Security Testing

### Automated

Test at minimum:

-   Authentication
-   Authorization
-   Scope enforcement
-   IDOR/BOLA prevention
-   Sensitive-data masking
-   Sensitive-data reveal permissions
-   Audit logging
-   CSRF
-   Input validation
-   File upload validation
-   Payment idempotency
-   Result publication authorization
-   Import security

Use appropriate tooling such as:

-   `pytest` / `pytest-django`
-   Bandit
-   Frontend test tooling
-   Dependency vulnerability scanning

### Manual

Before production:

-   OWASP Top 10 review
-   SQL injection testing
-   XSS testing
-   CSRF testing
-   Authorization bypass testing
-   IDOR/BOLA testing
-   File upload testing
-   Rate-limit testing
-   Sensitive-data exposure testing
-   Penetration testing

------------------------------------------------------------------------

## 23. Monitoring & Incident Response

Monitor for:

-   Repeated failed logins
-   Account lockouts
-   Unusual API request patterns
-   Authorization failures
-   Sensitive-data reveals
-   Unexpected administrative actions
-   Database anomalies
-   Error spikes
-   Import failures
-   Payment anomalies

Maintain an incident response process covering:

1.  Detection
2.  Containment
3.  Investigation
4.  Credential/key rotation
5.  Recovery
6.  Notification where required
7.  Root-cause analysis
8.  Preventive corrective action

------------------------------------------------------------------------

## 24. Data Privacy & Retention

Follow applicable Indian data-protection requirements and institutional
policies.

Rules:

-   Collect only data required for legitimate system functions.
-   Minimize exposure.
-   Restrict access using least privilege.
-   Define retention periods by data category.
-   Do not automatically delete historical academic/financial/audit
    records without an approved retention policy.
-   Handle Aadhaar and other regulated/sensitive data according to
    applicable requirements.
-   Provide appropriate data access/correction processes where required.

**Important:** Legal/compliance requirements must be verified against
the institution's current policies and applicable law before
implementation. Do not hardcode an unverified retention period or legal
rule merely because it appears in a generic security checklist.

------------------------------------------------------------------------

## 25. AI Coding Agent Security Rules

AI coding agents MUST:

1.  Read `ARCHITECTURE.md` and `DATABASE_ARCHITECTURE.md` before
    modifying backend architecture.
2.  Read this `SECURITY.md` before implementing authentication,
    authorization, profile data, documents, imports, payments, results,
    or deployment changes.
3.  Never disable authentication/authorization to make a test or feature
    pass.
4.  Never add default passwords for real users.
5.  Never create universal login bypasses, demo backdoors, hidden admin
    accounts, or hardcoded credentials.
6.  Never bypass permission checks from the frontend or backend.
7.  Never expose sensitive fields merely because they exist in a model.
8.  Never log secrets or sensitive personal data.
9.  Never use raw SQL with interpolated user input.
10. Never accept a user-supplied object ID without checking
    authorization and scope.
11. Never silently change security-sensitive behavior.
12. Never remove audit logging to simplify implementation.
13. Never delete historical financial/academic/security records as a
    shortcut.
14. Never weaken database constraints without documenting why.
15. Never commit `.env`, credentials, API keys, tokens, or encryption
    keys.
16. Never use production credentials in development/test fixtures.
17. Never introduce a dependency without considering its security
    impact.
18. When requirements conflict, stop and identify the conflict instead
    of silently choosing the less secure behavior.
19. When a security requirement is ambiguous, ask for clarification
    before implementing an irreversible security decision.
20. Before declaring a security-sensitive task complete, run the
    relevant tests and perform a security review of the changed code.

------------------------------------------------------------------------

## 26. Security Change Protocol

Any significant security change must include:

-   What security problem it addresses
-   Threat/risk being mitigated
-   Affected domain/module
-   Database impact
-   API impact
-   Frontend impact
-   Audit impact
-   Migration impact
-   Testing performed
-   Rollback considerations

Architecture/security changes should be recorded in `DECISIONS.md` or an
appropriate ADR.

------------------------------------------------------------------------

# 27. Pre-Production Security Checklist

### Authentication

-   [ ] Secure password hashing configured
-   [ ] No default/universal passwords
-   [ ] MFA configured for designated privileged roles
-   [ ] Token/session expiry configured
-   [ ] Refresh token protection configured
-   [ ] Account lockout/throttling configured

### Authorization

-   [ ] RBAC implemented
-   [ ] Scope enforcement implemented
-   [ ] Object-level authorization tested
-   [ ] IDOR/BOLA tests pass
-   [ ] Frontend is not treated as an authorization boundary

### Sensitive Data

-   [ ] Sensitive fields classified
-   [ ] Required sensitive fields encrypted
-   [ ] Default masking implemented
-   [ ] Reveal permissions implemented
-   [ ] Sensitive access audited
-   [ ] Secrets excluded from logs

### API

-   [ ] Rate limiting configured
-   [ ] CORS allowlist configured
-   [ ] Request-size limits configured
-   [ ] Input validation implemented
-   [ ] API versioning policy established
-   [ ] Idempotency implemented for critical operations

### Database

-   [ ] TLS enabled
-   [ ] Application does not use superuser
-   [ ] Database constraints verified
-   [ ] Critical transactions protected
-   [ ] Backups encrypted
-   [ ] Restore process tested

### Files

-   [ ] File type/content validation
-   [ ] File-size limits
-   [ ] Malware scanning where required
-   [ ] Authenticated document access
-   [ ] Path traversal protection
-   [ ] Sensitive documents not publicly accessible

### Application

-   [ ] Production DEBUG disabled
-   [ ] Security headers configured
-   [ ] CSRF protection verified
-   [ ] XSS protections verified
-   [ ] Error messages do not leak internals
-   [ ] Dependencies audited
-   [ ] Security tests pass

### Deployment

-   [ ] HTTPS enforced
-   [ ] Secrets managed securely
-   [ ] Containers/processes do not run unnecessarily as root
-   [ ] Firewall/network access restricted
-   [ ] Production database not unnecessarily exposed
-   [ ] Vulnerability scans completed

### Verification

-   [ ] OWASP Top 10 review completed
-   [ ] Authorization bypass tests completed
-   [ ] Sensitive-data exposure review completed
-   [ ] Penetration testing completed where required
-   [ ] Incident response procedure documented

------------------------------------------------------------------------

# 28. Final Security Contract

The system is considered secure-by-design only when:

-   Authentication is enforced.
-   Authorization is enforced on the backend.
-   Scope boundaries cannot be bypassed.
-   Sensitive data is protected and minimized.
-   Financial and academic operations are atomic and auditable.
-   External imports are validated and idempotent.
-   Files are securely stored and accessed.
-   Secrets are never committed or exposed.
-   Database constraints protect critical invariants.
-   Security events are auditable.
-   Production configuration does not expose development/debug behavior.
-   Security-sensitive changes are tested and reviewed.

> **Core rule for every developer and AI coding agent:**
>
> **Never sacrifice security, authorization, data integrity, or
> auditability merely to make an implementation easier or faster.**
