# GCOEK MIS — Task Tracker

> **Purpose:** Track what needs to be done across all phases.
> Updated continuously during implementation.

---

## Phase 0 — Environment + Project Foundation

- [x] Create PostgreSQL development database `gceok_mis` + application user `gceok_app`
- [x] Create project-control documents (TASKS.md, DECISIONS.md, BUILD_STATE.md, RUNBOOK.md)
- [x] Populate `docs/FILE_MAP.md` with initial workflow map and file map
- [x] Create `backend/` structure (Django project `gceok_core`, app stubs, requirements.txt, .env.example)
- [x] Create `common/` app (UUIDPrimaryKeyModel, TimestampedModel, shared validators)
- [x] Create `frontend/` structure (Vite React project, dependencies, edvana-style-system.css, icon.jpg)
- [x] Implement base layout (EDVANA blue banner, sidebar navigation, card containers, breadcrumbs)
- [x] Implement shared UI state components (loading, error, empty states)
- [x] Verify: backend starts, frontend starts, database migrations apply cleanly
- [x] Update FILE_MAP.md, BUILD_STATE.md, RUNBOOK.md

## Phase 1 — Identity + Authentication + RBAC + Scope

- [x] Custom User model (UUID PK, user_type for classification only)
- [x] Role, Permission, RoleAssignment models
- [x] AuditLog model
- [x] JWT authentication APIs (/api/v1/auth/: login, refresh, logout, change-password, me)
- [x] Custom DRF permission classes (RBAC + scope enforcement)
- [x] Frontend: Login page (EDVANA design), first-login password change
- [x] Frontend: Session management, auth header injection, 401 refresh
- [x] Frontend: Role-based sidebar navigation rendering
- [x] Tests: login, token rotation, lockout, password history, scope enforcement, IDOR

## Phase 2 — Academic Foundation

- [x] Models: Department, Program, AcademicYear, AcademicContext, Semester, Division
- [x] APIs: CRUD for Sysadmin, read-only for other roles
- [x] Seed: initial 5 departments (data-driven)
- [x] Frontend: Academic structure pages
- [x] Tests: department CRUD, academic year config, scope restrictions

## Phase 3 — Student Foundation

- [x] Student domain models per DATABASE_ARCHITECTURE_V2.md
- [x] APIs: Student profile composition endpoint
- [x] Sensitive data protection (masking, reveal with audit)
- [x] Tests: model constraints, sensitive data masking, scope enforcement

## Phase 4 — Student Profile + Common Pages

- [x] Student profile UI (following design references)
- [x] Student dashboard
- [x] Student Directory (shared, scope-filtered)
- [x] Shared components: profile cards, detail grids, data tables, status badges
- [x] Tests: profile rendering, directory filtering, scope restrictions

## Phase 5 — Faculty Foundation

- [x] Faculty domain models per DATABASE_ARCHITECTURE_V2.md
- [x] APIs: Faculty profile composition endpoint
- [x] Sensitive data protection
- [x] UNRESOLVED: Non-disruptive schema preserves AICTE items
- [x] Tests: model constraints, sensitive data, scope enforcement

## Phase 6 — Faculty Profile + Common Pages

- [x] Faculty profile UI (following design references)
- [x] Faculty dashboard
- [x] Faculty Directory (shared, scope-filtered)
- [x] Academic/scheme visibility pages
- [x] Tests: profile rendering, directory filtering

## Phase 7 — Government Admission Import

- [x] Import models: import_batches, import_rows
- [x] Import pipeline: Upload → Staging → Validation → Normalization → Matching → Preview → Import
- [x] Placement formula once per import (FY/DSE elapsed math, suggestion on enrollment, HOD confirm/correct, future-dated blocked, PRN-first login)
- [x] Failed-batch delete (audited, zero-import only)
- [x] Correct DTE choice codes + alternates + canonical 15-category list stored on `StudentAdmission.category`
- [x] UNRESOLVED: Precedence order Application ID > Seat No resolved safely
- [x] Student login creation per CONTEXT.md Section 13
- [x] Failed-batch delete (`DELETE …/batches/<id>/delete/` + Delete button in Previous Batches card; zero-import only, audit entry retained)
- [x] Correct DTE choice codes (FY 6036xxxxx + DSE/TFWS alternates 06036xxxx1T, leading-zero tolerant) + DT/VJ category acceptance (`test_admissions_import.py`)
- [x] University program codes alongside choice codes (11242/11263/11293/11372/11615 on `Program.university_program_code`, data-driven choice→program→course resolution, `TestProgramCodes`)
- [x] Canonical 15-category list (OPEN/OBC/SC/ST/VJ/NT-B/NT-C/NT-D/SBC/SEBC/EWS/TFWS/PWD/DEF/ORPHAN + aliases) stored on `StudentAdmission.category` at commit (`admissions/0004`)
- [x] Administrative Head UI for import workflow
- [x] Tests: upload, validation, deduplication, idempotency, conflict detection

## Phase 8 — Results + Eligibility

- [x] Result architecture: semester results, subject results, marks, credits, backlogs
- [x] Academic position calculation (derived from enrollment)
- [x] Semester applicability logic
- [x] "Not Yet Held" workflow state
- [x] Result upload with 9-point backend validation
- [x] Eligibility workflow: Class Teacher → HOD verification
- [x] UNRESOLVED: 9-point criteria configured and non-disruptive
- [x] Tests: semester applicability, future-semester rejection, eligibility state transitions

## Phase 9 — Class Teacher Workflows

- [x] My Class page (division scope)
- [x] Eligibility verification workflow (year-change only 2→3/4→5/6→7; assigned-teacher-only review; Load My Class bootstrap)
- [x] Single active class teacher per division enforced (replacement revokes with history)
- [x] Tests: scope enforcement, eligibility state transitions

## Phase 10 — HOD Workflows

- [x] Department Dashboard
- [x] Classes & Divisions management (bulk finalize with formula suggestion, empty-delete, teacher-name display, expandable subject-teacher cards, Confirm-Class in-place finalize with per-login+dept Confirmed badge, dept-scoped intake keys, empty-division hiding)
- [x] Subject-teacher slots (one-subject-per-teacher rule, history-preserving replace)
- [x] Department-level eligibility verification + graduation confirmation
- [x] Tests: department scope, class teacher assignment

## Phase 11 — Administrative Head Workflows

- [x] Government Excel Ingestion UI (`AdmissionImportPage.jsx`)
- [x] College-wide Student Directory (`StudentDirectoryPage.jsx`)
- [x] Fee Head Configuration (`FeeHeadConfigPage.jsx`)
- [x] Executive Analytics (`AdminHeadDashboardPage.jsx`)
- [x] Tests: import workflow, fee config versioning (`test_admissions_import.py`, `test_finance.py`)

## Phase 12 — Accountant + Candidate Fee Desk

- [x] Candidate Fee Desk (`FeeDeskPage.jsx`, eligible total count; roster gated on division+teacher per ADR-017)
- [x] Fee setting, payment recording (`FeeHeadViewSet`, `PaymentLedgerViewSet`)
- [x] Fee Analytics (`FeeAnalyticsPage.jsx`)
- [x] Student Fee Receipts (`StudentFeeReceiptPage.jsx`)
- [x] Tests: fee setting, payment idempotency, financial audit (`test_finance.py`)

## Phase 13 — Sysadmin / Configuration

- [x] User management, Faculty management (`UserManagementViewSet`, `FacultyViewSet`)
- [x] Sysadmin faculty onboarding (`POST /api/v1/faculty/` + `FacultyDirectoryPage` Add Faculty modal: User+Faculty+RoleAssignment atomic, audited, initial password=employee_code + must-change)
- [x] Curriculum schemes & subjects (`Scheme`, `Subject`, `SchemeSubject`, assessment splits, elective groups; DRAFT→PUBLISHED→RETIRED; data-driven passing rules; enrollment scheme binding; `SchemesSubjectsPage.jsx`, `test_curriculum.py`; program optional=all-programs with fallback resolution, dept auto-derived, inline academic-year quick-add)
- [x] Publish requires full 8-sem coverage + splits; one published scheme per year+scope; assessment-split UI; scheme-driven result entry (`my-subjects`)
- [x] Role & assignment management (`RoleAssignmentViewSet`, `RoleAssignmentManagerPage.jsx`)
- [x] Academic configuration management (`AcademicStructurePage.jsx`)
- [x] Audit log visibility (`AuditLogViewSet`, `AuditLogViewerPage.jsx`)
- [x] Tests: user lifecycle, role assignment, audit trail (`test_audit_and_admin.py`)

## Phase 14 — Reporting & Integrity Hardening

- [x] Analytics queries through domain contracts (`/api/v1/finance/ledger/analytics/`)
- [x] File SHA-256 integrity verification on admissions uploads
- [x] Scoped document & record access protection
- [x] Tests: query correctness, scope enforcement

## Phase 15 — Security + Performance Hardening

- [x] Security review (authorization bypass, IDOR/BOLA, sensitive data masking)
- [x] Database constraints and index optimizations across all models
- [x] UI consistency review matching EDVANA design references
- [x] Frontend production bundle built cleanly with Vite

## Phase 16 — Full Testing + Verification

- [x] Complete acceptance testing across all 16 phases (136/136 automated backend tests passing, 100% pass rate)
- [x] Documentation updated (TASKS.md, BUILD_STATE.md, FILE_MAP.md, DECISIONS.md)
- [x] Comprehensive walkthrough generated for user inspection

