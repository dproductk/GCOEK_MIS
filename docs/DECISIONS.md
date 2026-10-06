# GCOEK MIS — Architecture Decision Records

> **Purpose:** Record important architectural and business decisions with context, rationale, and consequences.
> AI agents and developers must check this file before reversing or contradicting an existing decision.

---

## ADR-001: Technology Stack

**Date:** 2026-09-21
**Status:** Approved

**Context:** Greenfield build of college management system for GCOE Kolhapur (Autonomous).

**Decision:** Django + DRF modular monolith with React frontend and PostgreSQL database.

**Reason:** Matches project architecture documents. Django provides robust ORM, migrations, auth framework. DRF provides serialization, permission classes, throttling. React provides component-based UI. PostgreSQL provides relational integrity, constraints, UUID support.

**Consequences:** All backend code uses Django/DRF patterns. Frontend is a separate React SPA communicating via REST API under `/api/v1/`.

---

## ADR-002: UUID Primary Keys

**Date:** 2026-09-21
**Status:** Approved

**Context:** Internal identifiers for all domain models.

**Decision:** Use UUID v4 as internal primary keys. Government identifiers (application_id, enrollment_no, etc.) are business identifiers with appropriate UNIQUE constraints but are NOT used as database PKs.

**Reason:** Required by DATABASE_ARCHITECTURE_V2.md. Prevents enumeration attacks. Separates internal identity from external business identifiers.

**Consequences:** All models inherit from a base model providing UUID PK. Government identifiers have their own indexed unique columns.

---

## ADR-003: Authorization Model

**Date:** 2026-09-21
**Status:** Approved

**Context:** The system needs role-based and scope-based access control.

**Decision:** Use User → RoleAssignment → Role → Permission → Scope architecture. `User.user_type` is for account/person classification only (STUDENT, FACULTY, SYSADMIN) and is NOT an authorization mechanism.

**Reason:** Required by ARCHITECTURE.md and SECURITY.md. Supports future multiple roles per user. Prevents two competing authorization systems.

**Consequences:** All authorization checks use RoleAssignment + Permission + Scope. Frontend role checks are UX only, never security boundaries.

---

## ADR-004: PostgreSQL Development Database

**Date:** 2026-09-21
**Status:** Approved

**Context:** Need a development database for local development.

**Decision:** Database name `gceok_mis`, application user `gceok_app` (not superuser). Connection details via environment variables, never committed.

**Reason:** Follows SECURITY.md least-privilege principle. Application should never use superuser for runtime operations.

**Consequences:** `.env` files contain database credentials. `.env.example` contains variable names only.

---

## ADR-005: DTE Maharashtra Admissions Ingestion Pipeline

**Date:** 2026-09-21
**Status:** Approved

**Context:** Government admission lists come as HTML table-formatted `.xls` files with 59 standardized attributes and mixed course naming.

**Decision:** Multi-stage pipeline (Upload -> Staging in `ImportRow` -> Validation -> Normalization -> Core Commit).

**Reason:** Isolates raw, imperfect government data from core production tables. Validates without touching core models. Computes SHA-256 checksum to prevent duplicate imports and tampering.

---

## ADR-006: 9-Point Autonomous Grading and Multi-Tier Eligibility

**Date:** 2026-09-21
**Status:** Approved

**Context:** GCOEK Autonomous grading follows a 9-point scale with letter grades and SGPA calculation. Eligibility for subsequent terms requires faculty verification.

**Decision:** Automated SGPA computation engine coupled with a multi-tier verification workflow (System calculation -> Class Teacher division review -> HOD final departmental endorsement).

**Reason:** Eliminates manual grade errors while maintaining academic governance and audit trail.

---

## ADR-007: Financial Quota Separation & Audit-Logged Ledger

**Date:** 2026-09-21
**Status:** Approved

**Context:** Institutional fee heads differ across quotas (Open, OBC/EBC 50% concession, SC/ST waiver, TFWS).

**Decision:** Model fee heads by category quota with versioning by academic year. Candidate payment ledgers compute real-time balance dues, issue official institutional receipts, and log every payment in the append-only `AuditLog`.

---

## ADR-008: Docs-Compliant Student Onboarding Fix

**Date:** 2026-09-27
**Status:** Approved

**Context:** The admissions import diverged from CONTEXT.md Sec 13/15/16 (universal initial password, hard-coded course-keyword department map, fabricated enrollment numbers, no CONFLICT handling, no normalized-data/matching columns, missing PARTIALLY_COMPLETED status, no source-file preservation).

**Decision:** Align implementation with docs without changing architecture: data-driven `Choice Code → Department.choice_code` mapping (course-name fallback only, no hard-coded keywords); identity matching precedence Application ID > Enrollment No with CONFLICT → manual review, never auto-merge; per-Sec-13 login (`username = enrollment_no else application_id`, initial password = same identifier, `must_change_password=True`, set only on creation); per-row atomic import with PARTIALLY_COMPLETED; `normalized_data`/`matching_status`/`matching_detail` on staging rows; original file preserved with checksum; no fabricated Aadhaar/bank records.

**Reason:** CONTEXT.md product rules are authoritative over the old implementation (AGENTS.md Sec 2). The identifier-as-initial-password form required by Sec 13 is the approved exception to SECURITY.md Sec 2.2's no-default-password rule, mitigated by forced first-login change, Django hashing, never resetting on re-import, and never logging credentials.

**Consequences:** New migration `admissions/0002_*`. Only VALID rows import; DUPLICATE/CONFLICT/INVALID never create students. Re-uploads and retries are idempotent.

---

## ADR-009: Admission Placement Formula (Single Source, HOD-Confirmed)

**Date:** 2026-10-03
**Status:** Approved

**Context:** Imported students need a suggested semester/year/division. The owner specified an exact formula: `elapsed = current_year - admission_year`; FY `base = elapsed*2+1`, DSE `base = elapsed*2+3`; EVEN term +1; `year = ceil(sem/2)`; `sem > 8` → Graduated.

**Decision:** Formula lives once in `apps/students/placement.py`, computed once per import (same admission year for all rows), stored as the suggestion on the current `StudentEnrollment`. HOD confirms or corrects it via bulk finalize; correction overwrites the unconfirmed suggestion (no trace of the first value) because it is pre-confirmation working data, not history. The formula itself is never edited per-student; detentions use `repeat_count` + HOD placement. `Student` carries `admission_year` (FK), `admission_type` (FY/DSE), `repeat_count`. Future-dated files are rejected at upload.

**Consequences:** Exception to the additive-correction rule (ARCHITECTURE.md Sec 16), explicitly scoped to unconfirmed import suggestions. Migrations `students/0004`, `0005`, `0006`.

---

## ADR-010: Scheme Publication Completeness + One Per Year

**Date:** 2026-10-03
**Status:** Approved

**Context:** Owner requires a scheme to be publishable only when fully defined, and one scheme per admission year.

**Decision:** Publish is blocked unless all 8 semesters carry subjects and every subject defines an assessment split. A second PUBLISHED scheme covering the same year for the same program scope (all-programs is its own scope, program-specific wins over it at resolution) is blocked. Program/all-programs coexistence approved earlier is preserved.

---

## ADR-011: Year-Change-Only Verification + First-Year Auto-Ledger

**Date:** 2026-10-03
**Status:** Approved

**Context:** Owner: verification runs once a year at year change (Sem 2→3, 4→5, 6→7); within-year moves are automatic on term flip; FY Sem-1 and DSE Sem-3 freshers of the current admission year are eligible by admission and go straight to the candidate ledger; graduation is HOD-confirmed on the verification page.

**Decision:** `initialize` and marks-triggered evaluation only cover even semesters (targets 3/5/7). `eligible_only`/`is_eligible` include auto-eligible freshers with no verification rows. Term rollover (`POST /academic/contexts/rollover/`, sysadmin-only) auto-advances odd→even enrollments, skipping `repeat_count > 0`. New `confirm-graduation` action sets PASSED_OUT after Sem-8 PASS. Teacher review restricted to the assigned division teacher (+sysadmin); HOD uses endorse; one active CLASS_TEACHER per division enforced (replacement revokes with history).

---

## ADR-012: Subject-Teacher Slots Owned by HOD

**Date:** 2026-10-03
**Status:** Approved

**Context:** Owner: HOD assigns subject teachers per division from scheme subjects; max one subject per teacher per division (same subject's theory+lab may share); one teacher per slot; assignment only, no verification rights; lab/theory splittable.

**Decision:** `TeachingAssignment` gains optional `scheme_subject` FK; write API validates both constraints; replacement = deactivate + create (rows immutable, history kept); HOD division cards expand to per-subject teacher dropdowns.

---

## ADR-013: Compliance Hardening Without Redesign (ARCH 17/18/24/28/38)
**Date:** 2026-10-03
**Status:** Approved

**Context:** Audit found five load-bearing gaps vs ARCH/SECURITY. Fix with smallest changes, no new services or modules.

**Decision:**
1. `EligibilityVerificationViewSet` is read-only; PUT/PATCH/DELETE return 405. State changes only via review/endorse/initialize actions (ARCH 17).
2. `PaymentLedgerViewSet` blocks update/destroy on ALL recorded rows with 400 (recorded = permanent at any status); corrections use future reversal records (ARCH 18/28).
3. `Division.class_teacher` and the CLASS_TEACHER `RoleAssignment` are one fact: all writes go through `academic_structure.services.sync_class_teacher()` (atomic, revokes prior holders, audits old/new) from both the division and role-assignment write paths (ARCH 7).
4. Slot invariant gets a DB partial-unique (`uniq_active_slot_teacher`) plus normalized codes; publish and assignment-create re-verify under `select_for_update`; marks corrections write old/new audit entries. Full result-version supersession (ARCH 24) is deferred: current overwrite + audit + teacher-lock is deemed sufficient for pilot scale; revisit post-go-live.
5. Throttles per SECURITY.md Sec 10: login 5/min scoped, upload 10/hr scoped, default user 1000/hr. Division teacher changes audit old/new values.

---

## ADR-015: HOD Intake Cards Without New Division Columns
**Date:** 2026-10-04
**Status:** Approved

**Context:** HOD wanted per-AH-import cards with a Create Class/Division popup (Academic Year, Scheme, Year, Semester, Division, Class Code, Class Teacher, Expected Strength), an FY/DSY view switch like the AH import page, per-card finalized-division info, scoped individual class changes, and per-card class-teacher assignment.

**Decision:** No new tables or columns. Per DATABASE_ARCHITECTURE_V2 Sec 15 (never create a column because a UI screen has a field) and ARCH Rules 2/7 (single owner, no duplicate truth): Scheme picker resolves via the existing `resolve_applicable_scheme`/`divisions/:id/subjects/` read path and is never persisted on Division (enrollment already binds the student to their entry scheme per CONTEXT Sec 9); Year is derived from `semester.year_level` with the established FY/SY/TY/Final-Year mapping; Class Code is a read-only serializer projection (`DEPT-SemN-Name`, e.g. `CSE-Sem3-A`); Expected Strength maps to the existing `seat_capacity`. Backend change is serializer projections (`year_level`, `year_label`, `class_code`, all read-only) plus a single annotated `enrolled_count` fixing the per-row N+1. Intake separation is frontend aggregation by `(admission_year_code, stream, semester_number)` reusing the existing student/division list APIs — no new endpoint, no permission or audit change (HOD own-department scope and Division audit trail preserved).

**Consequences:** `makemigrations --check` reports no changes. HOD page groups multiple AH imports into separate cards without backend linkage work; a true file-name card would still need ImportBatch HOD-read permission plus a Student→batch link and is explicitly out of scope.

---

## ADR-016: University Program Codes Alongside Choice Codes

**Date:** 2026-10-05
**Status:** Approved

**Context:** Some university-issued admission excels carry a Program Code (e.g. CSE 11242, AI&DS 11263, EE 11293, ETC 11372, MAE 11615) instead of a DTE choice code. Imports must accept either identifier without hard-coding numbers in business logic (ARCH Sec 12: configuration must be data-driven).

**Decision:** Store university codes once as data on `Program.university_program_code` (nullable unique, indexed; Academic Structure owns it). Import staging extracts a Program Code column (aliases: program code / programme code / university program code / branch code), resolves department by precedence choice_code → program_code → course_name via `build_dept_program_map()` (no hard-coded numbers), preserves raw + normalized copies per ARCH Sec 15, records `program_code` on `ImportRow` (indexed staging copy) and `StudentAdmission` (admission-event evidence, alongside existing `choice_code`). Seed + data migration set the five B.Tech codes; seeder repairs them on re-run. Commit reuses the same rule and persists the program code on the admission record.

**Consequences:** Migrations `academic_structure/0007+0008`, `admissions/0005`. `makemigrations --check` clean. Existing choice-code behavior unchanged (choice wins on conflict); program-only, leading-zero (`011242`), unmapped-code INVALID, and commit-persistence cases covered in `test_admissions_import.py::TestProgramCodes`.

---

## ADR-017: Eligibility Requires a Class (Division + Teacher), All Years

**Date:** 2026-10-06
**Status:** Approved

**Context:** ADR-011 made FY Sem-1 / DSE Sem-3 freshers of the current admission year auto-eligible straight to the candidate fee ledger. Owner requires one common rule instead: nobody — including FY freshers — is verification/fee eligible until seated in an HOD-created division WITH an assigned class teacher, so every year's import must pass through class formation.

**Decision:** Narrow the fresher bypass in both `eligible_only` (`students/views.py`) and `is_eligible` (`students/serializers.py`) with `division__isnull=False, division__class_teacher__isnull=False` on the current enrollment. Import still lands students in Div A (teacher-less), so they stay out of the fee roster until the HOD confirms the class and assigns its teacher. HOD-endorsed (`final_eligible`) rows are unchanged — endorsement already implies class-teacher review. Fee Desk header now shows the server-side total (`N Eligible Candidates`).

**Consequences:** No migration (rule-only change on existing columns). Freshers without a teacher disappear from the eligible roster until assigned — intended. Covered by `test_students.py::TestEligibleRequiresClass`.

---

## ADR-014: Fee Flow — AH Heads, Accountant Sets, Marking Is Permanent
**Date:** 2026-10-03
**Status:** Approved

**Context:** Owner: AH configures fee heads with presets; accountant picks (never types) amounts per head; marking collects exactly the set fee; once marked, the record is permanent. Category→quota fit check deferred (needs owner's per-category mapping).

**Decision:** Set Fee moved from browser localStorage to `POST /finance/assessments/` (preset + total==sum validation, audited, frozen once paid). Marking requires an existing assessment and amounts equal to it; receipts are server-sequenced `GCOEK/<year>/FEE/<nnnn>`. Analytics accepts an optional year filter. No category-quota enforcement until the mapping is supplied.

