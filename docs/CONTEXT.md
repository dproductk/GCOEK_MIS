# GCOE Kolhapur Student Management System — Master Context

> **Purpose:** This document is the canonical product/requirements context for AI coding agents working on the college-level student management software.
>
> **Important:** Read this entire file before changing architecture, database models, workflows, permissions, or UI. Treat confirmed requirements as authoritative. Do not invent business rules when a requirement is marked TBD. If a requirement conflicts with this document, stop and ask for clarification rather than silently changing the model.

---

# 1. Product Overview

We are building a **production-level college management application** for:

**Government College of Engineering, Kolhapur (Autonomous)**

The college is under **DBATU University**.

The university website remains the system for university-side/payment-side activities. This application is a **college-level operational record/ledger and management system**. It does not need to become a university-level replacement.

The first release is intentionally limited to a few profiles and workflows because admissions are starting soon. The architecture must nevertheless be production-minded:

- secure
- scalable enough for future college-wide expansion
- maintainable
- auditable
- easy to extend
- safe for AI coding agents to modify
- designed so future features do not require destructive database redesigns

The first major workflows are:

1. Student onboarding from government admission Excel
2. Student academic/result tracking
3. Eligibility verification and promotion
4. Fee configuration
5. Fee assignment and payment recording
6. Student/faculty directory
7. Academic structure and scheme visibility
8. Audit trail
9. Basic analytics

More modules will be added later.

---

# 2. Core Product Philosophy

## 2.1 College-level system, not university-level system

The college uses the university/DBATU website for actual university-side activities and payments.

This application stores the college's local records so staff can:

- organize students
- track academic status
- verify eligibility
- maintain fee records
- maintain student/faculty profiles
- search records easily
- produce reports
- maintain an audit history

There is currently **no API integration with the university payment system**.

Accountant verifies payment externally and records it locally.

---

# 3. Current Profiles

There are three top-level account/profile types:

1. **Student**
2. **Faculty**
3. **Admin / Sysadmin**

Faculty can additionally have one of the currently defined operational roles:

1. **Class Teacher**
2. **HOD (Head of Department)**
3. **Administrative Head**
4. **Accountant**

For the current release:

- One faculty member has one role at a time.
- Multiple faculty members may have the same role.
- A faculty member cannot have multiple roles yet.
- This restriction may change later, so do not make the database impossible to extend to multiple roles.
- Role assignment history must be preserved.

The **Sysadmin is separate from the normal faculty-role model**. The Sysadmin has full system-level authority.

---

# 4. Departments

There are currently five departments.

| Department | Current Seat Capacity |
|---|---:|
| Computer Science and Engineering | 60 |
| Artificial Intelligence and Data Science | 60 |
| Electrical Engineering | 60 |
| Electronics and Telecommunication Engineering | 60 |
| Mechanical and Automation Engineering | 60 |

Each department must support at least:

- internal database ID
- name
- department code
- choice code
- program information
- seat capacity
- active/inactive status
- start date
- future end/deactivation information if needed

The actual government choice code is used during student onboarding to determine the student's department/program.

Do not hard-code the five departments into business logic. The Sysadmin must be able to manage the academic structure so future departments can be added.

---

# 5. Academic Structure

The conceptual academic hierarchy is:

**College → Department → Program → Scheme → Semester → Subject**

For students/classes, the operational structure includes:

**Department → Academic Year/Student Year → Semester → Division → Student**

Example:

> CSE → 2nd Year → Semester 3 → Division A → Student

A division currently has:

- one class teacher
- students assigned to that division

Subject teachers will be added later. The database must make this future extension easy.

---

# 6. Academic Year and Semester

The Sysadmin controls the global current academic context.

Example:

> Academic Year: 2026–27  
> Current academic term: Summer 2026 / current odd/even academic operation

The college has one global current academic context; all departments/classes operate under the same current semester context.

However, a student's academic history must store explicit semester numbers:

- Semester 1
- Semester 2
- Semester 3
- Semester 4
- etc.

Do **not** replace the student's semester with only "odd/even".

The global academic context identifies the college's current academic operation, while student academic enrollment/history stores the student's actual semester.

The Sysadmin can update the academic year/semester context, and this information is visible to all profiles, including students.

---

# 7. Student Academic Progression

Student year/semester must be tracked explicitly.

A student should have historical academic records rather than simply overwriting their current year/semester.

Example:

> 2026–27 → Year 1 → Semester 1 → Division A  
> 2026–27 → Year 1 → Semester 2 → Division A  
> 2027–28 → Year 2 → Semester 3 → Division A

Promotion workflow:

**Eligibility approved → fees set → fees paid → student automatically moves to next year**

The exact implementation of semester progression must preserve history.

---

# 8. Schemes

Examples include:

- G Scheme
- H Scheme

A scheme defines the academic/curriculum and assessment rules used for students belonging to that scheme.

A scheme can contain:

- scheme name
- version
- start date
- end date / active period
- subjects
- course codes
- semester
- credits
- internal marks
- external/written marks
- practical/oral components where applicable
- passing rules
- eligibility/promotion criteria

The attached scheme example is a reference for the expected structure. It is not necessarily identical to the college's final scheme.

The Sysadmin creates/manages schemes and their rules.

Faculty roles can **view** scheme data and marking rules, but cannot modify them.

Students should not be able to modify scheme configuration.

---

# 9. Critical Scheme Rule: Students Stay in Their Scheme

When a student enters a scheme, the student remains associated with that scheme throughout their academic journey.

Example:

> Student enters G Scheme.
> G Scheme later becomes inactive.
> Student still has a backlog from G Scheme.
> The student must clear that backlog using the applicable G Scheme rules.

The student does NOT automatically switch to a newer scheme just because the newer scheme becomes active.

A student must not have backlogs from multiple schemes under the current business rule.

---

# 10. Scheme Versioning

Do not mutate historical scheme definitions in a way that changes historical student results.

If the scheme changes, create a **new scheme version**.

Historical results must remain tied to the scheme/version/rules under which the student was evaluated.

This is important because old students can continue to use an inactive scheme for backlog papers.

---

# 11. Subjects

Subjects belong to schemes.

Each subject can have:

- subject/course ID
- course code
- name
- semester
- credits
- subject type/component
- internal maximum
- external/written maximum
- other assessment components where applicable
- passing rules
- scheme/version association

Do not assume every future scheme will have exactly the same assessment structure.

---

# 12. Eligibility Rules

Eligibility rules are configured by the Sysadmin as part of the scheme/academic rules.

Examples:

- minimum written marks
- minimum internal marks
- minimum total marks
- passing grade/condition
- credits earned
- backlog conditions
- other scheme-specific requirements

Example:

> Written marks must be at least 20 to pass.

The exact rules must be data-driven/configurable rather than hard-coded wherever practical.

---

# 13. Student Identity

Government admission data may contain:

- Application ID
- Enrollment No.
- Board Enrollment No.

These are identifiers belonging to the student.

Important:

- They must be unique according to their business rules.
- They should not all be treated as interchangeable primary keys.
- Use a stable internal Student ID/database primary key.
- Government identifiers should have appropriate unique constraints where applicable.

Student login creation:

1. Government Excel import creates the student.
2. System uses `enrollment_no` if available.
3. If `enrollment_no` is empty, system falls back to `application_id`.
4. Login account is automatically created.
5. Login account is linked to the Student record.

Initial login:

- Username = Enrollment No. when available; otherwise Application ID.
- Initial password = same identifier.
- Student must change password on first login.

---

# 14. Government Admission Excel

The government-provided Excel file is the initial source of student admission data.

The uploaded reference file contains 179 rows and 59 columns. Its fields include:

- Sr. No.
- Application ID
- Candidate Name
- Father Name
- Mother Name
- Gender
- DOB
- Religion
- Region
- Mother Tongue
- Annual Family Income
- Address Line 1
- Address Line 2
- Address Line 3
- State
- District
- Taluka
- Village
- Pincode
- Mobile No
- E-Mail ID
- Phone No
- Candidature Type
- Home University
- Category
- PH Type
- Defence Type
- Linguistic Minority
- Religious Minority
- SSC Board
- SSC Passing Year
- SSC Seat No
- SSC Math Percentage
- SSC Total Percentage
- Qualifying Exam
- HSC Board
- HSC Passing Year
- HSC Seat No
- HSC Physics Percentage
- HSC Chemistry Percentage
- HSC Math Percentage
- HSC Additional Subject for Eligibility
- HSC Subject Percentage
- HSC English Percentage
- HSC Total Percentage
- Eligibility Percentage
- CET Roll No
- CET Percentile
- JEE Application No
- JEE Percentile
- Merit No
- Merit Marks
- Institute Code
- Institute Name
- Course Name
- Choice Code
- Seat Type
- Admission Date
- Reported Date

The government file is authoritative for the imported admission fields at onboarding.

---

# 15. Student Import Architecture

Do NOT import the Excel directly into final Student records.

The required pipeline is:

**Upload Excel**
→ **Import Batch**
→ **Staging Rows**
→ **Validation**
→ **Cleaning/Normalization**
→ **Matching**
→ **Preview/Confirmation**
→ **Final Import**
→ **Student + Enrollment + Login**

## 15.1 Import Batch

When Administrative Head uploads:

- Government Excel file
- Academic year

the system creates an Import Batch.

The original uploaded file must be preserved unchanged for proof/audit.

An Import Batch should have lifecycle/status information.

Suggested lifecycle from requirements:

- UPLOADED
- VALIDATING
- VALIDATED
- IMPORTING
- COMPLETED
- PARTIALLY_COMPLETED
- FAILED

The system should also store metadata such as:

- source filename
- upload time
- uploader
- academic year
- source checksum/hash if useful
- total rows
- validated rows
- invalid rows
- imported rows
- failed rows

## 15.2 Staging Rows

Every Excel row is first copied to staging.

Each staging row should retain:

- import batch
- source row number
- raw data
- cleaned/normalized data
- validation status
- validation error/reason
- matching result
- final import status

Raw values must remain available so the original government data can be compared with normalized values.

## 15.3 Validation

Validation checks include examples such as:

- missing name
- wrong date
- wrong mobile
- wrong category
- duplicate inside uploaded file
- invalid required identifiers
- invalid department/choice-code mapping
- other row-level data errors

Bad rows are marked INVALID with a reason.

Good rows are VALIDATED.

Only validated rows may proceed to final import.

## 15.4 Cleaning

Normalize data without destroying the raw source:

- trim extra spaces
- normalize names
- normalize dates
- normalize mobile formatting
- normalize other appropriate fields

Display raw vs cleaned values when reviewing an import.

## 15.5 Matching

Check existing students in this order:

1. Application ID
2. Enrollment No.
3. Board Enrollment No.

Possible outcomes:

- no match → new student
- one match → link to existing student
- two IDs point to different students → CONFLICT
- conflict must never be auto-merged

Re-uploading the same file must not create duplicate students.

If the same unique ID appears twice, it represents the same student rather than a new student.

## 15.6 Final Import

Administrative Head reviews the preview and confirms.

Only validated rows become real Student/Enrollment records.

The final import should be transactional and safe to retry.

If some rows fail:

- mark the batch PARTIALLY_COMPLETED or FAILED as appropriate
- allow fixing/retrying only failed rows
- do not duplicate already-successful students

---

# 16. Department Assignment During Import

The student's government Excel record contains a **Choice Code**.

The system uses the choice-code mapping to determine:

- department
- program/course

The relevant HOD then sees students belonging to their department.

Choice codes should be stored/configured rather than hard-coded throughout the application.

---

# 17. Student Profile

Student profile UI is based on the supplied student profile reference ZIP.

Reference sections include:

- Registration Details
- Photo/Profile page
- Aadhaar Details
- Bank Details

The exact UI should follow the supplied reference designs where appropriate.

The student profile should be extensible to include:

- personal details
- contact details
- address
- admission details
- academic details
- bank details
- documents
- profile photo
- result history
- fee history

Students can edit permitted incorrect information after login.

Students cannot delete themselves or their official academic record.

---

# 18. Faculty Profile

Faculty information is based on the supplied AICTE-format faculty reference and faculty profile screenshots.

The AICTE sample contains fields such as:

- teaching staff name
- designation
- department
- joining date
- UG qualification/class
- PG qualification/class
- PhD
- teaching experience
- industry experience
- research experience
- papers published
- conference presentations
- PhD field/university
- PhD/projects guided
- books/IPRs/patents
- professional memberships
- consultancy activities
- awards
- grants
- interaction with professional institutions

The faculty profile UI reference contains sections such as:

- Profile Information
- Qualification Details
- Academic Details
- Bank Details
- Documents

Faculty employment must support at least these real-world categories:

- Permanent
- Temporary
- Visiting

Exact HR/employment fields can be expanded later.

Do not assume all faculty have the same employment type or identical qualification data.

---

# 19. Faculty Base Access

Every normal faculty account, regardless of role, gets:

## Dashboard

Faculty dashboard should use the same visual language as the student dashboard.

It should show useful information such as:

- faculty name
- department
- designation
- current academic year/semester
- relevant student counts/activity
- quick access to common features

## Student Directory

Faculty can search/view general student information.

Suggested filters:

- name
- enrollment no
- application ID
- department
- year
- semester
- division
- gender
- category
- eligibility
- status

Faculty must NOT see fee/payment information.

The student directory shown to faculty should expose only general/personal/academic information permitted to faculty.

## Departments & Programs

Read-only:

- department name
- department code
- choice code
- program
- seat capacity
- active/inactive status
- other general academic structure information

## Schemes & Subjects

Read-only:

- schemes
- scheme versions
- subjects
- course codes
- semester
- credits
- internal/external marks
- passing criteria
- eligibility rules
- scheme validity

## My Profile

Faculty can view their profile.

## Account/Security

- password change
- security/account controls

---

# 20. Class Teacher Role

Class Teacher gets the base Faculty capabilities plus class-specific functions.

A Class Teacher is assigned to one division/class for now.

Example:

> CSE → 2nd Year → Semester 3 → Division A → Class Teacher

## My Class

Shows:

- assigned department
- year
- semester
- division
- students
- student academic information
- result/backlog information
- eligibility status

## Eligibility Verification

Main first-release role feature.

The system calculates eligibility from results and scheme rules.

Class Teacher reviews it.

Possible states:

- Pending
- Eligible
- Not Eligible

If the teacher finds a problem:

- flag/change the result/eligibility
- provide a reason

The student can then correct the flagged marks from their profile.

The teacher rechecks the corrected information.

The verified eligibility is then sent to HOD.

Class Teacher should not assign themselves or other teachers.

---

# 21. HOD Role

HOD receives the base Faculty functionality plus department-level controls.

## Department Dashboard

Shows department-level information such as:

- student count
- students by year
- divisions
- pending eligibility verification
- eligible/not eligible counts
- backlog information
- other academic statistics

## Department Student View

HOD can see students in their department.

This should use scope-based access rather than duplicating the entire student directory feature.

## Classes & Divisions

HOD can:

- create divisions
- view divisions
- assign Class Teacher
- change Class Teacher
- view class-teacher assignment history

Current rule:

- one Class Teacher per division
- subject teachers will be added later

The data model must support future subject-teacher assignments without a redesign.

## Eligibility Verification

HOD reviews Class Teacher verification.

HOD can:

- verify
- send back to Class Teacher
- view reason
- review result/backlog data
- view verification history

If HOD believes something is wrong, HOD flags it so the Class Teacher can reconsider.

HOD does not silently erase the teacher's history.

---

# 22. Administrative Head Role

Administrative Head is a normal operational role, not Sysadmin.

Administrative Head responsibilities:

1. Government Excel ingestion
2. Student directory
3. Fee configuration
4. Fee desk/payment ledger visibility/management
5. Executive analytics
6. relevant operational/audit features

## Government Excel Ingestion

Full import workflow defined above.

UI should support:

- upload
- import batch list
- file/source
- academic year/session
- row statistics
- validation status
- view rows
- validate
- execute/import
- delete/retire batch where safe and permitted
- audit information

Original uploaded file must remain preserved.

## Student Directory & Filters

College-wide searchable student directory.

Search/filter examples:

- name
- enrollment number
- application ID
- department
- year
- semester
- division
- category
- eligibility
- gender
- status
- login status
- other useful non-financial filters

Administrative Head can open the full student profile.

Student profile may include:

- personal
- address
- admission
- academic
- bank
- documents
- fees
- results

Administrative Head does NOT delete student records.

## Fee Head Configuration

Administrative Head defines fee categories/heads.

Current major heads:

- Tuition Fee
- Development Fee
- Other Fee

Each fee head can have selectable amount presets.

Example:

Tuition:
- ₹0
- ₹15,000
- ₹30,000
- ₹60,000

Development:
- ₹0
- ₹3,000
- ₹6,000
- ₹10,000

Other:
- ₹0
- ₹500
- ₹1,000
- ₹1,500

These are examples from the UI reference and are configurable.

The Administrative Head can add/configure fee heads and their allowed values.

Fee configuration must be versioned/history-preserving.

Changing next year's fee options must not rewrite historical fee structures.

## Fee Desk & Payment Ledger

Administrative Head can monitor fee information.

Actual payment marking is performed by Accountant.

## Executive Analytics

Initially available to Administrative Head.

Examples:

- total students
- department-wise student count
- category distribution
- gender distribution
- verification pending
- eligibility statistics
- fee collection
- result performance
- reports
- print/export
- Excel export where useful

HOD department-level analytics may be added later.

## Academic Structure for AH

Administrative Head can view academic configuration read-only:

- Departments & Programs
- Academic Calendar & Sessions
- Curriculum Schemes & Subjects
- Faculty Roster
- Results & Eligibility Overview

AH must not modify underlying department/scheme/subject configuration.

---

# 23. Accountant Role

Accountant has normal Faculty features plus finance features.

The fee-setting and fee-marking workflow should be combined into one operational page called:

# Candidate Fee Desk

Do NOT create separate primary menu items for "Eligible Students", "Set Fee", and "Mark Payment".

They are steps inside Candidate Fee Desk.

## Candidate Fee Desk

Shows eligible students available for admission/year progression fee processing.

Suggested tabs:

- All Candidates
- Fee Not Set
- Fee Set
- Fee Paid

Search/filter by:

- name
- enrollment no
- department
- year
- division
- fee status
- payment status
- academic year

Each row may show:

- serial number
- enrollment number
- name
- father/parent name
- mobile
- department/program
- fee marked/status
- fee amount
- actions

Actions:

- Set Fee
- Edit Fee (only before payment according to current rules)
- Mark Fee/Payment
- History

## Setting Fees

Accountant uses only the fee options configured by Administrative Head.

Example:

Student:
- Tuition = ₹15,000
- Development = ₹3,000
- Other = ₹500
- Total = ₹18,500

The UI should calculate the total automatically.

## Marking Payment

The college does not receive payment data via API.

Student pays through the university system.

Accountant verifies externally, then records the payment locally.

Payment record includes, where applicable:

- payment amount
- payment method
- receipt number
- UTR / transaction ID
- remarks/accounting reason
- date/time
- accountant/user who recorded it

No partial payments in the current scope.

Payment is made in full.

The system blocks duplicate payment for the same due.

Once marked paid, the payment is not editable under the current rule.

Future correction/reversal workflows may be added later.

## Fee Analytics

Separate menu/page from Candidate Fee Desk.

Shows:

- total assessed
- total paid
- outstanding
- collection rate
- department-wise collection
- year-wise collection
- fee-head-wise collection
- academic-year filtering
- reporting/export

---

# 24. Student Promotion

A student becomes eligible through:

**Result evaluation → Class Teacher verification → HOD verification**

Then:

**Eligible + fee set + fee paid → automatic promotion to next year**

Promotion must preserve historical academic records.

Do not delete or overwrite the student's previous year/semester data.

---

# 25. Results

Student result history is semester-based.

Student can open a semester:

> Semester 1

Then see subject table:

- Subject
- Course code
- Marks/components
- Credits
- Result/pass status
- Backlog status

Student enters their marks.

The system evaluates according to the applicable scheme version.

If marks are wrong:

1. Class Teacher flags the issue with a reason.
2. Student can update the marks.
3. Teacher rechecks.
4. HOD verifies eligibility.

Result changes must be auditable.

---

# 26. Backlog Tracking

Backlogs are first-class academic records.

Example:

> Semester 1 → Mathematics → Backlog

Later:

> Mathematics → Cleared

The historical backlog must remain visible.

The cleared attempt/result must be linked to the relevant original subject/scheme context.

A student remains under the scheme they originally entered.

---

# 27. Audit Trail

Audit trail is mandatory.

Important actions should record:

- who
- role
- action
- timestamp
- target record
- old value where applicable
- new value where applicable
- reason where applicable
- source/request context where appropriate

At minimum audit:

- government Excel uploads
- validation/import operations
- student record changes
- login/account creation
- role assignment/removal
- class teacher assignment
- eligibility changes
- result/mark changes
- teacher flags
- HOD verification
- fee configuration changes
- fee assignment
- payment marking
- important administrative configuration changes

Audit history should be append-oriented and protected from normal users.

---

# 28. Permissions Model

Use this conceptual model:

**User → Role → Permission → Scope**

Examples:

### Class Teacher

Permission examples:

- view_students
- view_class_students
- view_results
- review_eligibility
- flag_result
- verify_class_eligibility

Scope:

> assigned division/class

### HOD

Permissions:

- view_department_students
- manage_divisions
- assign_class_teacher
- verify_eligibility
- department_analytics

Scope:

> their department

### Administrative Head

Permissions:

- import_students
- view_all_students
- configure_fee_heads
- view_fee_records
- analytics

Scope:

> college-wide, excluding Sysadmin-only configuration

### Accountant

Permissions:

- view_eligible_students
- set_fee
- record_payment
- view_payment_history
- fee_analytics

Scope:

> financial/student fee records

### Faculty

General permissions:

- view permitted student directory
- view departments
- view schemes
- view subjects
- view own profile

### Student

Permissions:

- view own profile
- edit permitted own fields
- enter/update own marks where allowed
- view own result history
- view own fee/payment history
- change own password

A user must never gain access simply because a frontend route is hidden. Authorization must be enforced on the backend/service/API level.

---

# 29. Access Boundaries

## Faculty

Can see:

- general student information
- department information
- scheme information
- subject information
- marking rules

Cannot see:

- fee amounts
- payment status
- UTR
- payment history
- financial records

unless a specific financial role grants it.

## Student

Can see:

- own data
- own academic records
- own result history
- own fee/payment history

Cannot see other students' records.

## HOD

Can see/manage:

- own department
- department students
- divisions
- class teachers
- department eligibility workflow

## Administrative Head

Can see/manage:

- college-wide student operations
- admission import
- fee configuration
- operational fee records
- analytics

Cannot modify Sysadmin-controlled academic configuration.

## Accountant

Can see/manage:

- eligible students for fee processing
- fee assignment
- payment records
- fee analytics

Cannot modify academic scheme/department configuration.

## Sysadmin

Full system authority.

---

# 30. Student Dashboard

Use the supplied student dashboard screenshot as the visual reference.

Desired navigation:

```text
STUDENT PORTAL

Dashboard
View / Update Profile
Result History
Fee / Payment History
Account / Security
```

Dashboard should show:

- student name
- department
- current year
- current semester
- division
- scheme
- eligibility
- fee status
- important pending actions

Do not build university exam registration/hall-ticket functionality in the first release unless explicitly requested later.

---

# 31. Faculty Dashboard

Use the same visual language/layout style as the Student dashboard.

Base navigation:

```text
FACULTY PORTAL

Dashboard

Students
└── Student Directory

Academics
├── Departments & Programs
└── Schemes & Subjects

My Profile
Account / Security
```

Role-specific pages appear in addition to these.

---

# 32. Class Teacher Menu

Conceptually:

```text
FACULTY PORTAL

Dashboard

Students
└── Student Directory

My Class
Eligibility Verification

Academics
├── Departments & Programs
└── Schemes & Subjects

My Profile
Account / Security
```

---

# 33. HOD Menu

Conceptually:

```text
FACULTY PORTAL

Dashboard

Department
├── Department Dashboard
├── Department Students
└── Classes & Divisions

Eligibility
└── Eligibility Verification

Students
└── Student Directory

Academics
├── Departments & Programs
└── Schemes & Subjects

My Profile
Account / Security
```

Some duplicated views can be implemented as one reusable component with different scope.

---

# 34. Administrative Head Menu

Conceptually:

```text
ADMINISTRATIVE HEAD

Dashboard

Students & Admissions
├── Government Excel Ingestion
├── Student Directory & Filters
├── Class Divisions & Batches
├── Verification Audit Trail
└── Services & Requests (future)

Fees & Finance
├── Fee Head Configuration
└── Fee Desk & Payment Ledger

Academic Structure (Read Only)
├── Departments & Programs
├── Academic Calendar & Sessions
├── Curriculum Schemes & Subjects
├── Faculty Roster
└── Results & Eligibility Overview

Institutional Reporting
└── Executive Analytics

My Profile
Account / Security
```

---

# 35. Accountant Menu

Conceptually:

```text
ACCOUNTANT

Dashboard

Candidate Fee Desk
Fee Analytics

Student Directory
Departments & Programs
Schemes & Subjects

My Profile
Account / Security
```

Candidate Fee Desk combines:

- eligible student list
- fee setting
- payment marking
- history

Fee Analytics remains separate.

---

# 36. Sysadmin Menu

The Sysadmin is the highest-level configuration account.

Suggested conceptual menu:

```text
SYSADMIN

Dashboard

People & Access
├── Users
├── Faculty
├── Roles & Assignments
└── Access / Audit

Academic Configuration
├── Departments & Programs
├── Schemes
├── Subjects
├── Scheme Versions
└── Academic Year & Semester

System
├── Audit Logs
├── System Settings
└── Account Management
```

The exact Sysadmin UI can be finalized later.

---

# 37. Important UI Reference

The supplied UI screenshots establish the design direction:

- strong blue header
- college logo/name
- current term indicator
- light background
- white cards
- rounded panels
- clean data tables
- clear status badges
- blue primary actions
- green success states
- orange/yellow pending states
- red destructive/danger states
- sidebar navigation
- role/profile information in sidebar
- responsive dashboard-style layout

Do not treat screenshots as exact backend/database requirements. They are UI/UX references.

---

# 38. Fee UI Reference

The supplied fee screenshots show:

## Candidate Fee Desk

A student list with:

- enrollment number
- name
- father/parent name
- mobile
- fee status
- actions

Fee status examples:

- FEE NOT SET
- FEE SET: ₹18,500
- FEE PAID

Actions include:

- Set Fee
- Edit Fee
- Mark Fee
- History

## Mark Payment Form

Contains:

- total fee set
- already paid
- remaining
- status
- payment amount
- payment method
- receipt number
- UTR / transaction ID
- remarks/accounting reason
- confirm & mark as paid

Current rule: full payment only.

## Fee Setting

Fee heads are displayed in a table.

Example:

- Tuition Fee
- Development Fee
- Other Fee

Each has a dropdown populated from the presets configured by Administrative Head.

Total is calculated automatically.

---

# 39. What Must NOT Be Hard-Coded

Avoid hard-coding:

- department list
- department choice codes
- seat capacity
- scheme names
- subject lists
- course codes
- marking rules
- eligibility rules
- fee heads
- fee presets
- academic years
- semester configuration
- class/division names
- role assignment history
- student promotion rules

These are data/configuration wherever practical.

---

# 40. Historical Data Rules

Historical data matters.

Do not simply overwrite:

- student academic year
- semester
- division
- scheme
- class teacher
- role assignment
- fee configuration
- payment history
- result history
- eligibility verification

Use historical/temporal records where appropriate.

Examples:

A class teacher changes:

> Teacher A — assigned from date X to date Y  
> Teacher B — assigned from date Y onward

A scheme changes:

> Scheme G v1 → Scheme G v2

A fee configuration changes:

> FY 2026–27 configuration remains historical  
> FY 2027–28 gets a new configuration

---

# 41. Deletion Rules

Students must not be deleted by Administrative Head.

Avoid physical deletion of important academic/financial/audit records.

Use lifecycle/status/archival mechanisms where necessary.

Financial and audit records should be especially protected.

Destructive actions must be restricted and audited.

---

# 42. Production Security Requirements

This is a production system.

At minimum, the architecture must account for:

- backend authorization
- role + permission + scope enforcement
- secure password storage
- forced first-login password change
- session/token security appropriate to the selected architecture
- CSRF protection where applicable
- input validation
- server-side validation
- database constraints
- unique constraints
- transaction safety
- import idempotency
- audit logging
- protection of financial records
- protection of student personal data
- restricted document access
- safe file upload handling
- rate limiting/abuse protection where appropriate
- secure error handling
- no secrets in source control
- environment-based configuration
- safe database migrations
- backups/recovery planning
- logging/monitoring
- least privilege

Never rely on the frontend to enforce authorization.

---

# 43. AI Coding Agent Rules

AI coding agents will be used to implement the system.

Therefore every coding agent should follow these rules:

1. Read this entire context before coding.
2. Do not redesign existing core entities without checking dependencies.
3. Do not silently invent business rules.
4. Do not hard-code academic/business configuration that should be data-driven.
5. Do not remove historical data to simplify implementation.
6. Do not bypass authorization for convenience.
7. Do not implement permissions only in the frontend.
8. Use database constraints for critical invariants.
9. Make important operations transactional.
10. Make imports idempotent.
11. Preserve audit history.
12. Write tests for business rules.
13. Use migrations for schema changes.
14. Do not directly edit production database structure manually.
15. Do not store passwords in plaintext.
16. Do not expose sensitive fields to unauthorized roles.
17. Do not use broad "admin can do everything" checks for normal roles.
18. Keep reusable domain logic separate from UI code.
19. Prefer explicit service/domain workflows for complex operations such as import, eligibility, promotion and payment.
20. Before changing an existing workflow, explain the impact and check this context.

---

# 44. Core Business Invariants

These rules should eventually be enforced by backend/domain logic and, where possible, database constraints.

### Student

- government identifiers must be appropriately unique
- a student has one applicable scheme for their academic journey
- a student cannot be deleted by Administrative Head
- student academic history is preserved

### Import

- same file re-upload must not create duplicate students
- conflicting identity matches must not auto-merge
- only validated rows reach final import
- original uploaded file is preserved
- successful rows are not imported again during retry

### Scheme

- historical student results stay tied to the correct scheme/version
- old schemes remain available for existing students' backlog requirements
- new scheme versions are created for changed rules

### Division

- one Class Teacher per division in the current release
- assignment history is preserved

### Eligibility

- only Pending, Eligible, Not Eligible in current scope
- teacher changes/flags require a reason
- HOD verification is a separate step
- verification history is preserved

### Promotion

- student becomes eligible
- fees must be set
- fees must be paid
- only then does automatic year promotion occur

### Fees

- fee presets come from AH configuration
- no partial payment in current scope
- duplicate payment must be blocked
- paid records are immutable under current rules
- historical fee configuration remains preserved

### Permissions

- access is determined by user + role + permission + scope
- faculty cannot access financial data merely because they can access student data
- HOD is scoped to department
- Class Teacher is scoped to assigned class/division
- Accountant is scoped to fee operations
- Sysadmin has system-level authority

---

# 45. Things Explicitly Out of Scope for First Release

Unless requirements are later expanded, do not build these now:

- university payment API integration
- real payment gateway
- university exam registration
- hall ticket generation
- SMS/email infrastructure
- complex notification system
- subject-teacher management
- multiple simultaneous roles per faculty
- HOD analytics implementation if not needed immediately
- advanced workflow engine
- microservices
- unnecessary caching infrastructure
- unnecessary AI/ML features
- automatic university result scraping

The system should be designed so these can be added later.

---

# 46. Known Future Extensions

The architecture should make these possible later:

- subject teacher assignment
- additional faculty roles
- multiple roles per person
- department-level HOD analytics
- more student workflows
- examination module
- attendance
- certificates
- additional financial workflows
- university integration/API
- notifications
- advanced reporting
- document workflows
- alumni
- graduation/exit workflows
- more academic rules
- more departments/programs
- additional fee types

---

# 47. Requirements Still Requiring Explicit Decisions

Do not invent answers for these.

### Student editable fields
Which imported/profile fields can the student edit after login?

### Exact promotion implementation
The business rule is confirmed:
**eligible + fee set + fee paid = automatic next-year promotion**.

The exact transaction/workflow implementation remains an engineering decision.

### Academic enrollment model
The system must preserve explicit student semester/year history. The exact table/model design is an engineering decision.

### Backlog attempt structure
Backlog tracking is required. Exact representation of attempts/retakes can be designed later.

### Faculty HR fields
Permanent/Temporary/Visiting are required categories. Exact HR/employment fields can be finalized later.

### Fee correction/reversal
Currently paid fees cannot be edited. A future correction/reversal workflow may be required.

### Student lifecycle statuses
Student deletion is prohibited. Exact statuses such as Active, Graduated, Withdrawn, Cancelled, etc. need to be finalized.

### Sysadmin UI
The Sysadmin is full authority; exact pages and workflows can be designed separately.

---

# 48. Recommended High-Level Domain Areas

Do not treat this as a final schema. It is a domain map for architecture discussions.

Potential domain areas:

```text
Identity & Access
├── User
├── Role
├── Permission
├── Role Assignment
└── Audit

Academic Structure
├── Department
├── Program
├── Academic Year
├── Academic Context
├── Division
└── Semester

Curriculum
├── Scheme
├── Scheme Version
├── Subject/Course
├── Assessment Component
├── Marking Rule
└── Eligibility Rule

Students
├── Student
├── Student Enrollment
├── Student Academic History
├── Student Division Assignment
├── Student Documents
├── Student Profile Data
└── Student Login

Admissions
├── Import Batch
├── Staging Row
├── Validation
├── Match Result
└── Import Execution

Results
├── Semester Result
├── Subject Result
├── Marks
├── Credits
├── Backlog
├── Eligibility Review
└── Verification History

Faculty
├── Faculty
├── Qualification
├── Experience
├── Publication
├── Membership
├── Documents
└── Faculty Assignment

Fees
├── Fee Head
├── Fee Head Version/Configuration
├── Student Fee Assessment
├── Fee Component
├── Payment
└── Payment History

Reporting
├── Student Analytics
├── Academic Analytics
├── Eligibility Analytics
└── Fee Analytics
```

This is a conceptual map only. Do not blindly turn every line into a table.

---

# 49. First-Release Menu Summary

## Student

```text
Dashboard
View / Update Profile
Result History
Fee / Payment History
Account / Security
```

## Faculty — no role

```text
Dashboard
Student Directory
Departments & Programs
Schemes & Subjects
My Profile
Account / Security
```

## Class Teacher

```text
Faculty Base
My Class
Eligibility Verification
```

## HOD

```text
Faculty Base
Department Dashboard
Department Students
Classes & Divisions
Eligibility Verification
```

## Administrative Head

```text
Dashboard

Students & Admissions
- Government Excel Ingestion
- Student Directory & Filters
- Class Divisions & Batches
- Verification Audit Trail
- Services & Requests (future)

Fees & Finance
- Fee Head Configuration
- Fee Desk & Payment Ledger

Academic Structure (Read Only)
- Departments & Programs
- Academic Calendar & Sessions
- Curriculum Schemes & Subjects
- Faculty Roster
- Results & Eligibility Overview

Institutional Reporting
- Executive Analytics

My Profile
Account / Security
```

## Accountant

```text
Dashboard
Candidate Fee Desk
Fee Analytics
Student Directory
Departments & Programs
Schemes & Subjects
My Profile
Account / Security
```

## Sysadmin

```text
Dashboard

People & Access
- Users
- Faculty
- Roles & Assignments
- Access / Audit

Academic Configuration
- Departments & Programs
- Schemes
- Subjects
- Scheme Versions
- Academic Year & Semester

System
- Audit Logs
- System Settings
- Account Management
```

---

# 50. Final Mental Model

The application should be understood as:

```text
                    COLLEGE SYSTEM
                         │
          ┌──────────────┼──────────────┐
          │              │              │
       PEOPLE         ACADEMICS       FINANCE
          │              │              │
     Users/Roles      Departments     Fee Heads
     Permissions      Programs        Assessments
     Faculty          Schemes         Payments
     Students         Subjects        Ledger
          │              │              │
          └──────────────┼──────────────┘
                         │
                     WORKFLOWS
                         │
        ┌────────────────┼─────────────────┐
        │                │                 │
     Admission        Results          Eligibility
        │                │                 │
     Excel →          Marks →          Teacher →
     Staging          Backlogs         HOD
        │                │                 │
        └────────────────┼─────────────────┘
                         │
                     Promotion
                         │
                 Fee Set + Paid
                         │
                   Next Academic Year
```

The most important architectural principle is:

> **Do not build separate disconnected systems for each role. Build one shared domain model with controlled permissions and scopes.**

The same Student record should be viewed differently by Student, Faculty, Class Teacher, HOD, Administrative Head and Accountant according to their permissions and scope.

---

# 51. Current Source References

The requirements above were built from:

- Government admission Excel reference file
- Student profile UI reference ZIP
- Faculty AICTE-format data reference
- Faculty profile UI reference ZIP
- Course Scheme Excel reference
- Student dashboard screenshots
- Administrative Head screenshots
- Accountant/Candidate Fee Desk screenshots
- Fee configuration screenshots
- Student Directory screenshot
- Requirements and workflow decisions provided by the product owner

The UI screenshots are visual references. The government Excel and faculty AICTE document are data/reference sources. The explicitly stated workflows and business rules in this document are the authoritative product requirements.

---

# 52. AI Agent Instruction

When starting a new task on this project:

1. Read `CONTEXT.md` completely.
2. Identify which domain/workflow the task affects.
3. Check existing models, APIs, services, tests and migrations before changing anything.
4. Preserve the business invariants in this document.
5. Do not weaken authorization to make a feature work.
6. Do not modify historical academic, fee, payment or audit records destructively.
7. If requirements are ambiguous, state the ambiguity and ask for a decision.
8. Prefer backward-compatible, migration-safe changes.
9. Add/update tests for changed business behavior.
10. Keep implementation modular so future roles/features can be added without redesigning the core system.
11. Treat this document as the product context, but treat the actual existing codebase and approved technical architecture as the implementation source of truth once they are established.
