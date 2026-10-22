# Prompt: HOD "Student Admin" — Profile Unlock + Password Reset

Build two new HOD-only administrative capabilities for the MIS, production-grade, **without breaking any existing feature**.

## Context (verified facts about this codebase — rely on these, verify as you go)

- Backend: Django + DRF, JWT (`SimpleJWT`), PostgreSQL. Custom user model `authentication.User`. Passwords hashed with Argon2 (`PASSWORD_HASHERS` in `backend/gceok_core/settings.py`). Min password length 12 (`AUTH_PASSWORD_VALIDATORS` there too).
- Student lock: `Student.profile_locked` / `profile_locked_at` in `backend/apps/students/models.py` (~line 115). Students lock themselves once via a `lock` action and can no longer self-edit (`update_me` raises PermissionDenied at ~line 327).
- Staff unlock already exists: `@action unlock` in `backend/apps/students/views.py` (~line 736–781). It is gated to SYSADMIN / ADMIN_HEAD / superuser, requires a reason (min 5 chars), uses `select_for_update`, and writes an audit entry via the `audit_log(...)` helper.
- HOD department scoping pattern to copy: `assign_division` in the same file (~line 861–873):
  `is_dept_hod = ('HOD' in scopes['roles'] and current_enrollment.department_id in scopes['department_ids'])`, where `scopes = get_user_scopes(user)`.
- Password flows: `set_password()` + `must_change_password=True` forces change at next login via `MustChangePasswordMiddleware` (`backend/apps/authentication/middleware.py`), `MustChangePasswordPermission`, and a frontend redirect in `frontend/src/routes/ProtectedRoute.jsx`. `PasswordHistory` model exists (`backend/apps/authentication/models.py`) and the change-password view records previous hashes there.
- Frontend: React (Vite). HOD pages live in `frontend/src/pages/hod/` (e.g. `HODDivisionsBatchesPage.jsx` routed at `/department/classes` in `frontend/src/App.jsx` ~line 98). Nav entries for HOD are in the `HOD:` block of `frontend/src/layouts/AppLayout.jsx` (~line 118). Frontend nav is UX-only — the backend is the real authorization layer.
- IMPORTANT: frontend has NO role-based route guard. Every new permission must be enforced server-side. A STUDENT-class JWT must get a hard 403 on both new endpoints.

## Feature decisions (do not change these)

1. **Unlock extra edit**: HOD may unlock a locked student profile of **their own department only** (SYSADMIN/ADMIN_HEAD keep existing unrestricted behavior). Unlocking re-opens self-service editing once; the student can then edit and re-lock themselves (verify the existing lock action permits re-lock after unlock).
2. **Password reset**: HOD **types the new password** in a form (no auto-generated password, no email/SMS). The student is forced to change it at next login via `must_change_password=True`. Never email,SMS,or log the plaintext password.
3. New single HOD page: `/department/students-admin` ("Student Admin" nav entry) — department student roster showing lock status, with an "Unlock for edit" action (reason modal) and a "Reset password" action (new password + confirm + reason).

## UX flow spec for the HOD page (build exactly this)
- **Top bar**: search input (by name / login_id) + filter selects for Department (default = HOD's own department, still selectable), Semester, Division, Year level, Status — all wired to the EXISTING student list endpoint query params (`search`, `department`, `semester_number`, `division`, `year_level`, `status` — see `_apply_filters` in `backend/apps/students/views.py` ~line 172–238). **Do not create any new listing API.**
- **List**: one row per student with name, login_id, current class/division, and a status badge for `profile_locked` (Locked / Open for edit). Actions per row, exactly two buttons:
  1. **Reset password** — opens a popup modal: new password + confirm password (12+ chars, hide/show toggle, must differ from login_id) and a mandatory reason (≥ 5 chars). On success show a generic "Password reset — student must change it at next login" notice. Never display or echo the typed password after submit.
  2. **Unlock profile** — only enabled/visible-when-relevant for students with `profile_locked=true`; opens a similar popup for the mandatory reason (≥ 5 chars). On success, re-render the row's badge immediately.
  - If the student's profile is already unlocked, disable "Unlock profile" with a tooltip ("Profile is already open for edit").
- **Disabled/empty states**: loading spinner on list, "No students match" empty state, and every API error surfaced via the project's toast/error convention (403 shows "Only this department's students can be managed").
- **Client-side validation mirrors server**: 5-char reason, 12-char password, confirm-matches. But never trust the client — server enforces everything again.

## Unlock re-lock behavior (do NOT change or "fix" this)
- After the HOD unlocks, the student gains another self-service edit. There is **no automatic re-lock** after editing in this system — the student re-locks themselves using their existing one-time self-lock action (the lock endpoint refuses only when already locked, so re-locking after an unlock succeeds).
- On the page and in success messages, phrase it accordingly: "Profile unlocked — the student may edit and should lock their profile when done."
- Do not invent an auto-re-lock mechanism; it would require schema changes. Out of scope.

## Do it step by step. After each phase, run the checks listed and fix failures before continuing.

---

### Phase 0 — Recon (read-only, no edits)
- Read `backend/apps/students/views.py` (lock/unlock/assign_division/update_me), `students/serializers.py`, `students/urls.py`, `get_user_scopes` in `backend/apps/authentication/permissions.py`, `MustChangePasswordMiddleware` middleware allowlist, and `PasswordHistory` usage in the change-password view.
- Read the existing Student list endpoint(s) available to HOD (there is a HOD branch ~line 162) and how the roster is fetched by `/department/classes` page components.
- Read one existing HOD page (`frontend/src/pages/hod/HODDivisionsBatchesPage.jsx`) + the shared api client under `frontend/src/api/` + modal/form component conventions used elsewhere.
- Produce a one-paragraph plan of exact files to touch. **Do not modify anything in this phase.**

### Phase 1 — Backend: widen `unlock` to department-scoped HOD
In `backend/apps/students/views.py`, `unlock` action only:
- Keep the existing SYSADMIN / ADMIN_HEAD / superuser path untouched.
- Add the department-scoped HOD check using the `assign_division` pattern: resolve the student's **current enrollment**; if `'HOD'` in `scopes['roles']` and enrollment's `department_id` is in `scopes['department_ids']`, allow. If the student has no current enrollment, HOD must be denied (only sysadmin/admin head may act) — say so in the error message.
- Keep everything else identical: reason ≥ 5 chars required, `select_for_update` transaction, same response shapes, audited with `actor=request.user`. Make the audit description clarify who unlocked (e.g. include the role).
- No model changes, no migrations, no signature/response-shape changes. SYSADMIN behavior must remain byte-identical.
- Check: `python manage.py check` passes; grep that no other caller of `unlock` relied on raising for HOD.

### Phase 2 — Backend: new `reset-password` action on the student viewset
Add to `backend/apps/students/views.py` as `@action(detail=True, methods=['post'], url_path='reset-password')` on the same ViewSet (so `get_object()` + existing permission classes apply — additive URL only, e.g. `POST /api/v1/students/{id}/reset-password/`). Confirm the actual URL prefix by reading `students/urls.py`.
- Authorization: same rule as Phase 1 — sysadmin/admin_head unrestricted; HOD only for students whose current enrollment department is theirs; everyone else (including STUDENT tokens) → 403 before any DB work.
- Request body: `new_password` (Twice is the client's job; enforce policy server-side) and `reason` (≥ 5 chars, mandatory, audited).
- Validate `new_password` against the project's `AUTH_PASSWORD_VALIDATORS` (min 12, etc.) — use `django.contrib.auth.password_validation.validate_password` on a `SetPasswordForm`-style check or directly, and **reject if it equals the student's login_id**.
- In one `transaction.atomic()` block with `select_for_update` on the user (and student if needed):
  `user.set_password(new_password)`; set `user.must_change_password = True`; append the **previous** password hash to `PasswordHistory` (mirror what `ChangePasswordView` does) so the temp password they just had can't be reused; save with explicit `update_fields`.
- Audit via `audit_log(...)` with the reason. The response returns only a generic success message + `must_change_password` flag; **never return or log the password**.
- Verify `MustChangePasswordMiddleware` allowlist covers `/change-password/` so the reset student can log in and change it (it already does — just confirm, don't edit the middleware unless a real gap exists).
- Check: `python manage.py check`; existing student test suite still passes (`pytest` or the project's runner — find it and use it).

### Phase 3 — Frontend: HOD "Student Admin" page (additive only)
- New page `frontend/src/pages/hod/HODStudentAdminPage.jsx`:
  - Lists students in the HOD's department (reuse the existing HOD roster endpoint/components found in Phase 0 — do not create a parallel listing API).
  - Columns: name, login_id, current class/division (best available from existing endpoints), plan status (`profile_locked`), actions.
  - "Unlock for edit" → modal asking reason (min 5 chars, enforced client-side too) → calls `POST .../unlock/`.
  - "Reset password" → modal with new password + confirm (12+ chars, must differ from login_id), password visibility toggle, reason field → calls `POST .../reset-password/`. Show a success notice reminding the HOD to hand the password to the student securely.
  - Handle every error response (403「not in your department」, 400 validation, 404) with the project's toast/error conventions.
- Wire-up, additive only: one `<Route>` in `frontend/src/App.jsx` (near the HOD routes) for `/department/students-admin`; one nav entry inside the `HOD:` block of `frontend/src/layouts/AppLayout.jsx`. **Do not touch any other route, nav block, component, or shared file's logic.**
- API helpers go in a new module (e.g. `frontend/src/api/hodStudentAdmin.js`) or the project's existing api client file if that is the convention — no edits to unrelated endpoints.
- Check: `npm run build` (or project build command) passes; manually reason through that no existing route/import is altered.

### Phase 4 — Tests + regression proof
- Add API tests (Django/DRF tests alongside existing `apps/students` tests if they exist, else a minimal `tests.py`/`tests/` module):
  1. HOD can unlock a locked student **in own department**; audit row created.
  2. HOD gets 403 unlocking a student of another department, and a student with no current enrollment.
  2b. After an unlock, the student can self-lock again (re-lock succeeds) — proves the "edit again, then locked again" loop works end-to-end without any new code.
  3. STUDENT token gets 403 on both endpoints; ends up **locked still** and password unchanged (prove no partial writes).
  4. HOD can reset own-department student's password; new password works, old one rejected, `must_change_password=True`, student forced to `/change-password` flow, previous hash recorded in `PasswordHistory`, reason captured in audit.
  5. SYSADMIN/ADMIN_HEAD unlock + reset still work unscoped (no regression).
  6. Reason-missing / <5-char / weak-password / password==login_id → 400, nothing mutated.
- Run the **full** backend test suite + frontend build. Report: files changed list, new routes, and test output summary. If any pre-existing test fails, it must fail identically before and after your change — verify with `git stash` or by checking out the base commit before claiming it's pre-existing.

---

## Hard guardrails (violating any = failure)
- Zero schema changes / zero migrations. This feature needs none.
- All new endpoints additive; no URL, serializer field, or response-shape changes to existing APIs.
- Backend is the authorization boundary; never rely on frontend nav hiding.
- No plaintext password in logs, audit records, responses, or error messages.
- Existing SYSADMIN/ADMIN_HEAD unlock flow and the student self-lock flow must remain functionally identical.
- Do not add email/SMS/notifications — out of scope by decision.
- Do not refactor, rename, or reformat unrelated code touched by the diff.

## Definition of done (production-grade)
- Both actions audited with actor, target student, and reason.
- HOD is hard-scoped to own department on the server for both actions.
- Reset password forces first-login change; student can log in with the typed password and immediately set their own.
- Full test suite green; frontend builds clean; `manage.py check` clean; diff reviewed to contain only the files listed above plus tests.
