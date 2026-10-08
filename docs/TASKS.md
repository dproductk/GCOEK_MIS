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

## Post-Audit Hardening (2026-10-06, no architecture change)

- [x] Role/user/assignment endpoints gated sysadmin-only (+ HOD own-dept CT create); ledger writes fee-desk only
- [x] `SECRET_KEY` fail-closed + `FIELD_ENCRYPTION_KEY`; Fernet PII encrypt/decrypt (`common/encryption.py`); reveal requires reason, no mocks
- [x] Receipt `max+1` + retry; single-active row locks; commit locks + no COMPLETED re-commit; upload magic-byte + filename checks
- [x] Composite indexes `student_enrollments(is_current,department,division)` (migration `students/0007`), `eligibility_verifications(department,final_eligible,class_teacher_status)` (migration `results/0003`); paginated `graduation-pending` + `eligible-candidates` (tests + frontend accept both shapes)
- [x] Full suite 159/159 green with new migrations applied

## Phase 16 — Full Testing + Verification

- [x] Complete acceptance testing across all 16 phases (136/136 automated backend tests passing, 100% pass rate)
- [x] Documentation updated (TASKS.md, BUILD_STATE.md, FILE_MAP.md, DECISIONS.md)
- [x] Comprehensive walkthrough generated for user inspection

## Phase 18 — Production Audit Hardening (2026-10-07, no architecture change)

- [x] Fee-payment audit complete: `PAYMENT` for offline/online ledger capture, `UPDATE` for initiation failure, duplicate-block, tamper-reject, gateway IP/signature rejections (`finance/services.py`, `finance/views.py`); `new_value` carries receipt/amount/txn refs
- [x] Academic/role/import audits complete: CT review + HOD endorse (`VERIFY`), scheme children CRUD, program/year/context CRUD, lab-batch delete, role update/delete + HOD revoke auditing, admission upload (`IMPORT`) + commit (`IMPORT`)
- [x] Audit service hardened: real `actor_role` from scopes, secret redaction (passwords/tokens/Aadhaar/bank), UA truncation, `target_id` preserved everywhere, bulk update/delete blocked at manager level
- [x] Sysadmin audit API: `date_from/date_to`, `target_id`, extended `search`, `ordering`, `select_related`, CSV `export/` capped 10k (archival only — trail stays append-only per SECURITY.md Sec 12/24)
- [x] Sysadmin audit UI: full action/target options incl. fee types, date + target-ID + text filters, server pagination with total count, Download CSV, forensic inspector retained
- [x] Production logging: `LOGGING` console + rotating `logs/django.log` + `logs/audit.log` (no secrets); 168/168 backend tests green, frontend build clean

## Phase 17 — Production Feature: Easebuzz Online Fee Payment for Continuing Students

- [x] Settings & Gateway config (`EASEBUZZ_ENABLED`, `EASEBUZZ_ENV`, `EASEBUZZ_KEY`, `EASEBUZZ_SALT`, `FRONTEND_BASE_URL`)
- [x] Data Model & Migrations: `allow_online_payment` on `StudentFeeAssessment`, `FeeReceiptCounter` for serialized concurrency-safe receipts, `OnlinePaymentAttempt` state machine, `GatewayRawEvent` immutable event log (`finance.0005_gatewayrawevent_and_more`)
- [x] Gateway Adapter: `EasebuzzGateway` with SHA-512 cryptographic initiation hash & reverse callback verification, server-to-server transaction status inquiry (`/transaction/v1/retrieve`), test sandbox mock detection
- [x] Authoritative Payment Application: `apply_gateway_result()`, single-mark lock, permanent atomic `PaymentLedger` generation, non-blocking progression promotion (`check_and_promote_student()`), async email receipt notification
- [x] Accountant Fee Setting: "Online Payment (Easebuzz Gateway)" toggle card on `CandidateFeeSetPage.jsx`, editable before payment
- [x] Candidate Ledger & Fee Desk: Top animated sliding pill tab switcher between `Candidate Fee Desk` and `Online Payment Tracker` on `FeeDeskPage.jsx`
- [x] Accountant Online Payment Tracker: Live monitor table showing candidates with online payment enabled, interactive permission switch, Easebuzz transaction IDs, gateway attempt statuses, and "Verify Bank" reconciliation action
- [x] Student Fee Portal: Outstanding Fee Assessment card with heads breakdown and "Pay Online via Easebuzz" on `StudentFeeReceiptPage.jsx`
- [x] Verification & Polling Page: `PaymentStatusPage.jsx` for polling bank callback/webhook, bank verification inquiry, receipt display, and developer mock sandbox checkout
- [x] Test Suite: 15/15 unit and integration tests passing (`test_finance.py`, `test_online_payment.py`) covering cryptographic hashes, receipt sequence concurrency, idempotency, promotion fail-safe, and accountant tracking

## Ghost Cleanup + File-Derived Admission Year (2026-10-07, owner-directed, ADR-018)

- [x] Reversed 142 ghost fresher records from Sem-7 rosters mis-imported as FY 2026-27 admissions (`CSE_Semester7_26-27.xls` 77 + `M&A_Semester7_26_27.xls` 65) via sysadmin-only `cleanup_misimported_batch` (dry-run default, skip-gates, 428 audit entries; batches + staging rows retained as evidence)
- [x] Batch admission year now resolves from file (`Student Admitted Year`, then `Academic Year`) with fallback to default; garbage spans rejected; future years still blocked; source recorded in `normalized_data`
- [x] Tests: file-year resolution/fallback/block + cleanup execute/skip/refusal (`test_admissions_import.py`); full suite 187/187 green
- [ ] Senior (2023/2024-cohort) onboarding needs its own channel — never upload Sem-7 rosters through admissions; EE/ETC/AIDS Sem-7 files still pending a decision
## Senior Backfill via Admissions, Even-Sem Landing (owner-directed)
- [x] Senior DSE rows use the DSE formula outcome (elapsed*2+3+term), not hardcoded Sem 3 — e.g. 2023 DSE in 2024-25 EVEN -> Sem 6; FY -> Sem 4 (`admissions/services.py`, both stage preview and commit)
- [x] Test: 2023-24 file in 2024-25 EVEN lands FY->Sem 4, DSE->Sem 6 (`test_candidate_onboarding_excel.py::test_senior_2023_cohort_lands_even_sem_via_formula`)
- [x] Legacy OLE `.xls` parses via xlrd (was accepted by validation but returned no rows); binary workbooks bypass the CSV sniffer; headers-only files report "no student rows"; all sheets scanned (tests: OLE parse, header-only message, second-sheet roster)
- [ ] Ops runbook pending: create past AcademicYears (2023-24+), set term EVEN, import, HOD class+teacher, students fill results 1..4/1..6 (`ResultHistoryPage` already lists 1..current), initialize->review->endorse, fee mark, promote to Sem 5/7
- [x] Classes & Divisions rebuilt (`HODDivisionsBatchesPage.jsx`): pending-imports banner+table derived from unconfirmed enrollments (no batch permission change), Create Division modal with intake select (create+finalize in one step), expandable class cards with roster, subject-teacher Set/green-Set+pencil (same `TeachingAssignment` API as dashboard), Add-students merge for later DSE imports (same `assign-students` endpoint). Obsolete sections removed: stat cards, Setup-2-steps bulk auto-create, per-student allocation table (single moves live on HOD Dashboard; lab-batch creation UI removed with it — re-add per-card if practicals need A1/A2 groups)
- [x] Import-batch single-use enforced (no migration): `GET /admissions/batches/pending-intakes/` (HOD own-dept slice, Admin Head/Sysadmin all; groups IMPORTED rows by batch x dept x stream x sem with pending/total + pending_student_ids; consumed cards omitted) + `POST /academic/divisions/:id/assign-students/` accepts `source_batch_id` (strict create: off-batch + already-placed skipped with reasons, idempotent retry, row locks, batch file in audit); HOD create sends `source_batch_id` and shows File + Pending/Total. Legacy derived grouping kept as fallback for seeds without ImportRow links. Verified: 2 files same sem stay 2 cards, consumed card disappears, reuse skipped, student role 403; `test_academic_structure + test_students` 45 green, admissions 70 green, frontend build ok
- [x] Mounted rebuilt page: `/department/classes` (sidebar Classes & Divisions) now renders `HODDivisionsBatchesPage`; restored single-move + delete-empty-class on cards so nothing was lost. HOD home (`/dashboard`) still shows Department Dashboard stats/overview
- [x] Design pass per owner screenshots: rounder class cards (18px) and tables (14px); subject teachers moved into a Set-popup table (Subject | Teacher, Set / green Set + pencil) with Class Teacher as its first row; Create popup restyled (Academic Year, Scheme aid, auto Year, Semester, Division, auto Class Code, Class Teacher, Expected Strength, live info box). Scheme/Year/Class-Code stay derived display aids — never persisted (DB ARCH Sec 15)
- [x] Faculty dashboard simplified to HOD stat-card style (`FacultyDashboardPage.jsx`): real name/designation/department header, 4 cards (subjects, classes, responsibility, department), real allocations table only — removed hero illustration, checklist, and hardcoded CS201/CS202 fallback rows. HOD card label fixed (`N Professors` -> `N Faculty`)

