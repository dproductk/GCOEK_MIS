# GCOEK MIS — File Map

> **Purpose:** Living AI navigation document. Before creating any new file, read this map first.
> Find the relevant workflow → find existing files → search for equivalent functionality →
> reuse/extend/refactor → create only if genuinely necessary.
>
> Updated after every meaningful implementation.

---

## A. Workflow Map

### WF-001: Authentication (Login / Logout / Session / Password Change)

| Field | Content |
|---|---|
| Workflow | User Authentication & Authorization |
| Purpose | Login, JWT token rotation, HttpOnly refresh cookie, session restore, logout, first-login password change |
| Actors/Roles | All users (Student, Faculty, Class Teacher, HOD, Admin Head, Accountant, Sysadmin) |
| Entry Page | `/login` → `LoginPage.jsx` / `/change-password` → `ChangePasswordPage.jsx` |
| Frontend Files | `src/pages/LoginPage.jsx`, `src/pages/ChangePasswordPage.jsx`, `src/context/AuthContext.jsx`, `src/api/client.js`, `src/routes/ProtectedRoute.jsx` |
| Backend Files | `apps/authentication/models.py`, `apps/authentication/serializers.py`, `apps/authentication/views.py`, `apps/authentication/permissions.py`, `apps/authentication/urls.py`, `apps/authentication/management/commands/seed_auth_roles.py` |
| API Endpoints | `POST /api/v1/auth/login/`, `POST /api/v1/auth/refresh/`, `POST /api/v1/auth/logout/`, `POST /api/v1/auth/change-password/`, `GET /api/v1/auth/me/` |
| Services | SimpleJWT token rotation/blacklisting, Audit logging |
| Models | `User`, `Role`, `Permission`, `RolePermission`, `RoleAssignment`, `PasswordHistory` |
| Database Tables | `users`, `roles`, `permissions`, `role_permissions`, `role_assignments`, `password_history` |
| Permissions/Scopes | Public: login, refresh, logout. Authenticated: change-password, me. RBAC: `HasRolePermission`. Scope: `HasScopeAccess` |
| Tests | `backend/tests/test_auth_api.py`, `backend/tests/test_permissions_scope.py` |
| Related Workflows | All protected workflows depend on this |

### WF-002: Audit Logging

| Field | Content |
|---|---|
| Workflow | Audit Trail |
| Purpose | Record all security-sensitive actions |
| Actors/Roles | System (automatic), Sysadmin (read) |
| Frontend Files | (Phase 13) |
| Backend Files | `apps/audit/models.py`, `apps/audit/services.py` |
| API Endpoints | (Phase 13) |
| Services | `apps/audit/services.py` → `audit_log()` |
| Models | `AuditLog` |
| Database Tables | `audit_logs` |
| Permissions/Scopes | Write: system/service layer. Read: Sysadmin only |
| Tests | `backend/tests/test_auth_api.py`, `backend/tests/test_academic_structure.py` |
| Related Workflows | Used by all workflows that perform security-sensitive actions |

### WF-004: Student Domain & Multi-Section Profile

| Field | Content |
|---|---|
| Workflow | Student Identity & Profile Management |
| Purpose | Multi-section student records, sensitive data masking (Aadhaar, Bank) with audited reveal modal |
| Actors/Roles | Student (Self), Faculty/Class Teacher/HOD (Scoped), Admin Head/Sysadmin (All) |
| Entry Page | `/profile` (via `ProfileDispatcher.jsx`) / `/students/:id` / `/students` |
| Frontend Files | `src/pages/student/StudentProfilePage.jsx`, `src/pages/student/StudentDirectoryPage.jsx`, `src/pages/student/StudentDashboardPage.jsx`, `src/api/studentApi.js` |
| Backend Files | `apps/students/models.py`, `apps/students/serializers.py`, `apps/students/views.py`, `apps/students/urls.py`, `apps/students/management/commands/seed_students.py` |
| API Endpoints | `GET /api/v1/students/me/`, `GET /api/v1/students/` (`eligible_only` gated on division+teacher per ADR-017), `GET /api/v1/students/<id>/`, `POST /api/v1/students/<id>/reveal/` |
| Tests | `backend/tests/test_students.py` |

### WF-005: Faculty AICTE Profile & Workload

| Field | Content |
|---|---|
| Workflow | Faculty Profile & AICTE Biodata |
| Purpose | Faculty qualifications, experience, publications, PhD guidance, salary masking |
| Actors/Roles | Faculty (Self), HOD (Department), Admin Head/Sysadmin (All) |
| Entry Page | `/profile` / `/faculty/:id` / `/faculty` |
| Frontend Files | `src/pages/faculty/FacultyProfilePage.jsx`, `src/pages/faculty/FacultyDirectoryPage.jsx` (sysadmin Add Faculty modal), `src/pages/faculty/FacultyDashboardPage.jsx`, `src/api/facultyApi.js` (`createFaculty`) |
| Backend Files | `apps/faculty/models.py`, `apps/faculty/serializers.py` (`FacultyCreateSerializer`), `apps/faculty/views.py` (`FacultyViewSet.create` sysadmin-only), `apps/faculty/urls.py`, `apps/faculty/management/commands/seed_faculty.py` |
| API Endpoints | `GET /api/v1/faculty/me/`, `GET /api/v1/faculty/`, `POST /api/v1/faculty/` (sysadmin onboarding: User+Faculty+RoleAssignment, atomic, audited), `GET /api/v1/faculty/<id>/`, `POST /api/v1/faculty/<id>/reveal/` |
| Tests | `backend/tests/test_faculty.py` |

### WF-011: Curriculum Schemes, Subjects & Eligibility Rules

| Field | Content |
|---|---|
| Workflow | Versioned curriculum rulebooks + data-driven passing rules |
| Purpose | Sysadmin creates Scheme versions (code+version unique) with semester subjects, assessment splits, elective groups; passing rules (min theory/total, ATKT cap) live on Scheme, not in code |
| Actors/Roles | Sysadmin (manage), Faculty/HOD/Admin Head/Student (read-only) |
| Entry Page | `/schemes` / `/admin/schemes` → `SchemesSubjectsPage.jsx` |
| Frontend Files | `src/pages/curriculum/SchemesSubjectsPage.jsx`, `src/api/curriculumApi.js` |
| Backend Files | `apps/curriculum/models.py` (Subject, Scheme, SchemeSubject, AssessmentComponent, ElectiveGroup/Option), `apps/curriculum/services.py` (scheme resolution), `apps/curriculum/serializers.py`, `apps/curriculum/views.py`, `apps/curriculum/urls.py` |
| API Endpoints | `/api/v1/curriculum/subjects/`, `/api/v1/curriculum/schemes/` (+`/publish/`, `/retire/`), `/api/v1/curriculum/scheme-subjects/`, `/api/v1/curriculum/assessment-components/`, `/api/v1/curriculum/elective-groups/`, `/api/v1/curriculum/elective-options/` |
| Rules | Published schemes immutable (DRAFT→PUBLISHED→RETIRED); new admissions resolve applicable scheme by program+year; enrollments preserve entry scheme on promotion; results evaluation falls back to 20/40/≤4 when no scheme; publish needs full 8-sem coverage + splits; one published scheme per year+scope; result entry prefers `my-subjects` scheme list |
| Tests | `backend/tests/test_curriculum.py` |

### WF-006: DTE Maharashtra Government Admissions Ingestion

| Field | Content |
|---|---|
| Workflow | Admissions Import Pipeline |
| Purpose | Parse DTE HTML table .xls, stage 59 attributes, validate without core pollution, commit to User/Student |
| Actors/Roles | Admin Head, Sysadmin |
| Entry Page | `/admissions/import` |
| Frontend Files | `src/pages/admissions/AdmissionImportPage.jsx`, `src/api/admissionsApi.js` |
| Backend Files | `apps/admissions/models.py` (`ImportRow.program_code`, `StudentAdmission.program_code`), `apps/admissions/services.py` (`normalize_program_code`, `build_dept_program_map`, choice→program→course resolution), `apps/admissions/serializers.py`, `apps/admissions/views.py`, `apps/admissions/urls.py` |
| API Endpoints | `POST /api/v1/admissions/batches/upload/`, `POST /api/v1/admissions/batches/<id>/commit/`, `DELETE /api/v1/admissions/batches/<id>/delete/` (failed zero-import batches only, audited). Placement formula (`apps/students/placement.py`) suggests sem/year once per import; HOD confirms/corrects; future-dated files blocked; login = PRN (enrollment_no) else application ID |
| Tests | `backend/tests/test_admissions_import.py` |

### WF-007: Results Engine & Eligibility Verification

| Field | Content |
|---|---|
| Workflow | Academic Results & Eligibility |
| Purpose | 9-Point SGPA computation, ATKT detection, Class Teacher -> HOD multi-tier verification |
| Actors/Roles | Student (Self), Class Teacher (Division), HOD (Department), Admin Head/Sysadmin |
| Entry Page | `/results` / `/eligibility` |
| Frontend Files | `src/pages/results/ResultHistoryPage.jsx`, `src/pages/results/EligibilityVerificationPage.jsx`, `src/api/resultsApi.js` |
| Backend Files | `apps/results/models.py`, `apps/results/services.py`, `apps/results/serializers.py`, `apps/results/views.py`, `apps/results/urls.py` |
| API Endpoints | `GET /api/v1/results/semester-results/my-results/`, `GET/POST /api/v1/results/eligibility/` (+`/initialize/` year-change bootstrap), `POST /endorse/`, graduation `GET graduation-pending/` + `POST confirm-graduation/`. Verification is year-change-only (targets 3/5/7); teacher step restricted to assigned division teacher; freshers auto-eligible in ledger |
| Tests | `backend/tests/test_results_engine.py` |

### WF-008: Class Teacher & HOD Oversight

| Field | Content |
|---|---|
| Workflow | Department & Class Cohort Management |
| Purpose | Division student rosters, attendance tracking, faculty workload, class teacher assignment, divisions + lab batches creation |
| Actors/Roles | Class Teacher (Division), HOD (Department - division/batch create scoped to own dept) |
| Entry Page | `/my-class` / `/department/classes` / `/department/divisions` (Student Divisions & Batches) |
| Frontend Files | `src/pages/class_teacher/MyClassPage.jsx`, `src/pages/hod/HODDashboardPage.jsx` (FY/DSY intake cards grouped by admission-year+stream+semester+department scope, screenshot-style Create Class/Division modal with Academic Year/Scheme/Year/Semester/Division/auto Class-Code/Teacher/Strength, Confirm-Class in-place finalize reusing the same popup via updateDivision with duplicate-create guard + extra-division shown only on genuine overflow, per-login+dept Confirmed badge with pen re-edit, empty divisions hidden from classroom/subject lists, click-outside + toggle unselect; Scheme/Year/Class-Code are derived display aids, payload stays department/academic_year/semester/name/seat_capacity/class_teacher), `src/pages/hod/HODDivisionsBatchesPage.jsx` |
| Backend Files | `apps/academic_structure/models.py` (Division, LabBatch — unchanged, no migration per ADR-015), `apps/academic_structure/serializers.py` (DivisionSerializer read-only `year_level`/`year_label`/`class_code` projections + annotated `enrolled_count`), `apps/academic_structure/views.py` (DivisionViewSet annotated enrolled_count, HOD own-dept scope + audit preserved), `apps/faculty/views.py`, `apps/students/views.py` (college-wide for all faculty) |
| Tests | `backend/tests/test_permissions_scope.py`, `backend/tests/test_academic_structure.py` (`TestDivisionIntakeProjections`: projection values, annotated count, read-only write rejection) |

### WF-009: Finance, Candidate Fee Desk & Analytics

| Field | Content |
|---|---|
| Workflow | Institutional Fee Lifecycle |
| Purpose | Fee head configuration, candidate fee collection, receipt generation, revenue analytics |
| Actors/Roles | Student (Receipts), Accountant (Desk/Ledger), Admin Head/Sysadmin (Analytics/Config) |
| Entry Page | `/finance/fee-config` / `/finance/fee-desk` / `/finance/analytics` / `/fees` |
| Frontend Files | `src/pages/finance/FeeHeadConfigPage.jsx`, `src/pages/finance/FeeDeskPage.jsx`, `src/pages/finance/FeeAnalyticsPage.jsx`, `src/pages/finance/StudentFeeReceiptPage.jsx`, `src/api/financeApi.js` |
| Backend Files | `apps/finance/models.py`, `apps/finance/serializers.py`, `apps/finance/views.py`, `apps/finance/urls.py`, `apps/finance/management/commands/seed_finance.py` |
| API Endpoints | `/api/v1/finance/fee-heads/` (audited mutations), `/api/v1/finance/ledger/`, `/api/v1/finance/ledger/my-payments/`, `/api/v1/finance/ledger/analytics/`, `/api/v1/finance/assessments/` (server-side Set Fee with preset validation, frozen once paid). Paid ledgers immutable; throttles per SECURITY-10 |
| Tests | `backend/tests/test_finance.py` |

### WF-010: Sysadmin Governance & Audit Trail

| Field | Content |
|---|---|
| Workflow | Security Governance & Audit Trail |
| Purpose | Role assignments, department/division scope binding, immutable security event audit log viewer |
| Actors/Roles | Sysadmin, Admin Head |
| Entry Page | `/admin/audit` / `/admin/roles` / `/admin/users` |
| Frontend Files | `src/pages/admin/AuditLogViewerPage.jsx`, `src/pages/admin/RoleAssignmentManagerPage.jsx`, `src/api/auditApi.js`, `src/api/adminApi.js` |
| Backend Files | `apps/audit/views.py`, `apps/audit/serializers.py`, `apps/audit/urls.py`, `apps/authentication/views.py` |
| API Endpoints | `/api/v1/audit/logs/`, `/api/v1/auth/roles/`, `/api/v1/auth/users/`, `/api/v1/auth/role-assignments/` |
| Tests | `backend/tests/test_audit_and_admin.py` |

### WF-003: Academic Structure & Configuration

| Field | Content |
|---|---|
| Workflow | Academic Structure Management |
| Purpose | Configure departments, degree programs, academic years, active term context, and class divisions |
| Actors/Roles | Sysadmin (Full CRUD), Faculty/HOD/Admin Head/Student (Read-only) |
| Entry Page | `/departments` / `/admin/departments` → `AcademicStructurePage.jsx` |
| Frontend Files | `src/pages/academic/AcademicStructurePage.jsx`, `src/layouts/AppLayout.jsx` |
| Backend Files | `apps/academic_structure/models.py`, `apps/academic_structure/serializers.py`, `apps/academic_structure/views.py`, `apps/academic_structure/urls.py`, `apps/academic_structure/management/commands/seed_academic_structure.py` |
| API Endpoints | `/api/v1/academic/departments/`, `/api/v1/academic/programs/`, `/api/v1/academic/years/`, `/api/v1/academic/contexts/`, `/api/v1/academic/semesters/`, `/api/v1/academic/divisions/` |
| Services | Academic year and context single-active invariants, audit trail |
| Models | `Department`, `Program`, `AcademicYear`, `AcademicContext`, `Semester`, `Division` |
| Database Tables | `departments`, `programs`, `academic_years`, `academic_contexts`, `semesters`, `divisions` |
| Permissions/Scopes | Read: Authenticated. Write: Sysadmin / `academic.manage` |
| Tests | `backend/tests/test_academic_structure.py` |
| Related Workflows | Schemes, Student Enrollment, Admissions, Class Divisions |

---

## B. File Map

### Project Root

| Path | Layer | Domain | Purpose |
|---|---|---|---|
| `.gitignore` | Infrastructure | — | Git ignore rules |
| `docs/AGENTS.md` | Documentation | — | AI agent operating rules |
| `docs/ARCHITECTURE.md` | Documentation | — | Architecture contract |
| `docs/CONTEXT.md` | Documentation | — | Product requirements |
| `docs/DATABASE_ARCHITECTURE_V2.md` | Documentation | — | Database design |
| `docs/SECURITY.md` | Documentation | — | Security contract |
| `docs/FILE_MAP.md` | Documentation | — | This navigation document |
| `docs/TASKS.md` | Documentation | — | Task tracker |
| `docs/DECISIONS.md` | Documentation | — | Architecture decisions |
| `docs/BUILD_STATE.md` | Documentation | — | Build progress tracker |
| `docs/RUNBOOK.md` | Documentation | — | Setup/run/test instructions |

### Backend — Core

| Path | Layer | Domain | Purpose | Contains |
|---|---|---|---|---|
| `backend/manage.py` | Infrastructure | — | Django CLI entry point | `main()` |
| `backend/requirements.txt` | Infrastructure | — | Python dependencies | Django, DRF, simplejwt, psycopg2, etc. |
| `backend/.env.example` | Infrastructure | — | Env variable template | Variable names only |
| `backend/pytest.ini` | Infrastructure | — | Pytest configuration | Django settings module |
| `backend/gceok_core/settings.py` | Infrastructure | — | Django settings | DB, JWT, CORS, security, DRF config |
| `backend/gceok_core/urls.py` | API | — | Root URL routing | `/admin/`, `/api/v1/auth/` |
| `backend/gceok_core/wsgi.py` | Infrastructure | — | WSGI entry | `application` |
| `backend/gceok_core/asgi.py` | Infrastructure | — | ASGI entry | `application` |

### Backend — Common

| Path | Layer | Domain | Purpose | Contains |
|---|---|---|---|---|
| `backend/apps/common/models.py` | Domain | Common | Base models | `UUIDPrimaryKeyModel`, `TimestampedModel`, `BaseModel` |
| `backend/apps/common/validators.py` | Domain | Common | Shared validators | `validate_mobile_number`, `validate_email_format`, `validate_pincode` |
| `backend/apps/common/apps.py` | Infrastructure | Common | App config | `CommonConfig` |

### Backend — Audit

| Path | Layer | Domain | Purpose | Contains |
|---|---|---|---|---|
| `backend/apps/audit/models.py` | Domain | Audit | Audit log model | `AuditLog` (append-only) |
| `backend/apps/audit/services.py` | Application | Audit | Audit logging service | `audit_log()`, `get_client_ip()` |
| `backend/apps/audit/apps.py` | Infrastructure | Audit | App config | `AuditConfig` |

### Backend — Authentication

| Path | Layer | Domain | Purpose | Contains |
|---|---|---|---|---|
| `backend/apps/authentication/models.py` | Domain | Identity | User, Role, Permission, RBAC | `User`, `Role`, `Permission`, `RolePermission`, `RoleAssignment`, `PasswordHistory` |
| `backend/apps/authentication/serializers.py` | API | Identity | Request/response serializers | `LoginSerializer`, `UserProfileSerializer`, `ChangePasswordSerializer` |
| `backend/apps/authentication/views.py` | API | Identity | Auth endpoints | `LoginView`, `TokenRefreshView`, `LogoutView`, `CurrentUserView`, `ChangePasswordView` |
| `backend/apps/authentication/permissions.py` | API | Identity | RBAC & Scope authorization | `HasRolePermission`, `HasScopeAccess`, `IsSysadmin`, helpers |
| `backend/apps/authentication/urls.py` | API | Identity | Auth URL routing | `/login/`, `/refresh/`, `/logout/`, `/me/`, `/change-password/` |
| `backend/apps/authentication/apps.py` | Infrastructure | Identity | App config | `AuthenticationConfig` |
| `backend/apps/authentication/management/commands/seed_auth_roles.py` | Application | Identity | Data seeder | Seeds 7 roles, 23 permissions, role-permissions, default admin |

### Backend — Academic Structure

| Path | Layer | Domain | Purpose | Contains |
|---|---|---|---|---|
| `backend/apps/academic_structure/models.py` | Domain | Academic | Core structure models | `Department`, `Program` (+`university_program_code`: 11242/11263/11293/11372/11615, migrations 0007 schema + 0008 data), `AcademicYear`, `AcademicContext`, `Semester`, `Division` |
| `backend/apps/academic_structure/serializers.py` | API | Academic | Serializers | `DepartmentSerializer`, `ProgramSerializer`, `AcademicYearSerializer`, `AcademicContextSerializer`, `SemesterSerializer`, `DivisionSerializer` |
| `backend/apps/academic_structure/views.py` | API | Academic | ViewSets | `DepartmentViewSet`, `ProgramViewSet`, `AcademicYearViewSet`, `AcademicContextViewSet`, `SemesterViewSet`, `DivisionViewSet` |
| `backend/apps/academic_structure/urls.py` | API | Academic | URL routing | DefaultRouter registering all 6 academic resources |
| `backend/apps/academic_structure/apps.py` | Infrastructure | Academic | App config | `AcademicStructureConfig` |
| `backend/apps/academic_structure/management/commands/seed_academic_structure.py` | Application | Academic | Data seeder | Seeds 5 departments, B.Tech programs, 8 semesters, 2026-27 year, divisions |

### Backend — Tests

| Path | Layer | Domain | Purpose | Contains |
|---|---|---|---|---|
| `backend/tests/test_auth_api.py` | Test | Identity | Auth API tests | Login, lockout, refresh, logout, password history |
| `backend/tests/test_permissions_scope.py` | Test | Identity | Authz & scope tests | HasRolePermission, HasScopeAccess (IDOR prevention) |
| `backend/tests/test_academic_structure.py` | Test | Academic | Academic structure tests | Department CRUD, student read/write guard, year invariants, division constraints |

### Backend — Domain App Stubs (Phase 3+)

| Path | Layer | Domain | Status |
|---|---|---|---|
| `backend/apps/curriculum/models.py` | Domain | Curriculum | Scheme versioning, subjects, assessment splits, electives | `Subject`, `Scheme`, `SchemeSubject`, `SchemeSubjectAssessmentComponent`, `SchemeElectiveGroup`, `SchemeElectiveOption` |
| `backend/apps/curriculum/services.py` | Application | Curriculum | Scheme resolution helpers | `resolve_applicable_scheme()`, `get_student_scheme()`, `get_thresholds()` |
| `backend/apps/curriculum/serializers.py` | API | Curriculum | Curriculum serializers | `SchemeSerializer`, `SubjectSerializer`, `SchemeSubjectSerializer`, … |
| `backend/apps/curriculum/views.py` | API | Curriculum | Sysadmin-write ViewSets, published-immutable | 6 ViewSets + publish/retire actions |
| `backend/apps/curriculum/urls.py` | API | Curriculum | Curriculum URL routing | 6 router resources under `/api/v1/curriculum/` |
| `backend/apps/students/` | Domain | Students | Stub |
| `backend/apps/admissions/` | Domain | Admissions | Stub |
| `backend/apps/results/` | Domain | Results | Stub |
| `backend/apps/faculty/` | Domain | Faculty | Stub |
| `backend/apps/finance/` | Domain | Finance | Stub |
| `backend/apps/reporting/` | Domain | Reporting | Stub |

### Frontend — Core

| Path | Layer | Domain | Purpose | Contains |
|---|---|---|---|---|
| `frontend/index.html` | UI | — | HTML entry point | Inter font, EDVANA body class, SEO meta |
| `frontend/src/main.jsx` | UI | — | React entry | EDVANA CSS import, BrowserRouter, App mount |
| `frontend/src/App.jsx` | UI | — | Root component | AuthProvider, Routes (login, protected layout) |
| `frontend/src/index.css` | UI | — | App CSS | Layout, sidebar, states, login, spinner, utilities |
| `frontend/src/assets/styles/edvana-style-system.css` | UI | — | Design system | EDVANA tokens, components, dark mode |
| `frontend/src/assets/icon.jpg` | UI | — | College icon | Branding |

### Frontend — API

| Path | Layer | Domain | Purpose | Contains |
|---|---|---|---|---|
| `frontend/src/api/client.js` | Infrastructure | — | Axios API client | JWT interceptor, token refresh queue, `setAccessToken`, `clearAccessToken` |

### Frontend — Context

| Path | Layer | Domain | Purpose | Contains |
|---|---|---|---|---|
| `frontend/src/context/AuthContext.jsx` | Application | Identity | Auth state | `AuthProvider`, `useAuth`, login/logout/hasRole |

### Frontend — Components

| Path | Layer | Domain | Purpose | Contains |
|---|---|---|---|---|
| `frontend/src/components/common/Spinner.jsx` | UI | Common | Loading spinner | `Spinner` (sm/md/lg) |
| `frontend/src/components/common/StateDisplays.jsx` | UI | Common | State components | `LoadingState`, `ErrorState`, `EmptyState` |

### Frontend — Layouts

| Path | Layer | Domain | Purpose | Contains |
|---|---|---|---|---|
| `frontend/src/layouts/AppLayout.jsx` | UI | — | Main layout | Sidebar nav (per-role), mobile toggle, user section, Outlet |

### Frontend — Pages

| Path | Layer | Domain | Purpose | Contains |
|---|---|---|---|---|
| `frontend/src/pages/LoginPage.jsx` | UI | Identity | Login page | EDVANA gradient login, error display, show/hide password |
| `frontend/src/pages/ChangePasswordPage.jsx` | UI | Identity | Password update | First-login & self-service password change, 12+ chars, history check |
| `frontend/src/pages/DashboardPage.jsx` | UI | — | Dashboard | EDVANA banner + card placeholder |
| `frontend/src/pages/academic/AcademicStructurePage.jsx` | UI | Academic | Academic management | Departments, B.Tech programs, class divisions, academic calendars |

### Frontend — Routes

| Path | Layer | Domain | Purpose | Contains |
|---|---|---|---|---|
| `frontend/src/routes/ProtectedRoute.jsx` | UI | Identity | Auth guard | Redirect to /login if unauthenticated, redirect to /change-password if must_change_password |

---

## C. Design Reference Assets

| Path | Purpose |
|---|---|
| `design/the software/edvana-style-system.css` | Visual design source of truth |
| `design/the software/student account/` | Student UI screenshots |
| `design/the software/faculty account/` | Faculty UI screenshots |
| `design/the software/HOD/` | HOD UI screenshots |
| `design/the software/Administrative head role/` | Admin Head UI screenshots |
| `design/the software/Accountant/` | Accountant UI screenshots |
| `design/assets/Course Scheme.xlsx` | Scheme data reference |
| `design/assets/GCOEKP_26_27_AdmittedCandidateList.xls` | Government import reference |
| `design/assets/faculty profile in AICTE Format.docx` | Faculty profile reference |
| `design/icon.jpg` | College branding icon |
