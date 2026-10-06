# DATABASE_ARCHITECTURE_V2 --- Profile, Faculty & Scheme Integration

## Status

**Purpose:** authoritative architecture extension for the College
Student Management & Administrative Data System.

This document extends the previously established `ARCHITECTURE.md` and
`DATABASE_ARCHITECTURE.md`. Where this document conflicts with
prototype/implementation-specific choices in an older database document,
this document is the design target for the new build.

## Source basis

The design below is based on: - the previously supplied master
architectural prompt and database architecture; - the supplied Student
Profile screenshots ZIP; - the supplied Faculty Profile / Profile Page
screenshots ZIP; - the supplied AICTE faculty biodata document; - the
supplied admitted-candidate government Excel file; - the supplied Course
Scheme Excel workbook.

The uploaded faculty biodata explicitly contains teaching staff name,
designation, department, joining date, UG/PG/PhD qualification,
teaching/industry/research experience, papers, conferences, PhD/project
guidance, books/IPRs/patents, professional memberships, consultancy,
awards, grants and professional-institution interaction.
fileciteturn3file0L2-L44

------------------------------------------------------------------------

# 1. Non-negotiable architecture rules

1.  PostgreSQL is the system of record.
2.  Django + DRF modular monolith remains the backend architecture.
3.  UUIDs are internal primary keys; business identifiers remain
    separate.
4.  A profile screen is a UI composition, **not** a database table.
5.  Do not create one giant `student_profile` or `faculty_profile`
    table.
6.  Each business fact has one authoritative owner.
7.  Current academic status comes from enrollment/lifecycle records, not
    a mutable `current_semester` field.
8.  Repeated or historical facts use child/history tables.
9.  Documents store metadata and secure storage references; file
    binaries are not stored in PostgreSQL.
10. Sensitive values such as Aadhaar and bank details are isolated and
    access-audited.
11. Faculty subjects taught are assignments, not a comma-separated
    profile field.
12. Scheme data is versioned/immutable once used by academic records.
13. Historical result/fee/scheme data must not change when a new scheme
    or academic year is introduced.
14. Government Excel is imported through staging; never directly into
    production entities.
15. UI validation is not sufficient; database constraints and backend
    authorization enforce invariants.

------------------------------------------------------------------------

# 2. Bounded contexts affected by these new files

## Student Management

Owns: - student identity - personal/contact data - guardian data -
addresses - admission data - category/reservation data - qualifying
examination history - scholarship profile - bank details - Aadhaar
details - student documents - photo/signature metadata

## Academic Foundation

Owns: - department - program - academic year - semester - batch -
scheme - subject - scheme-subject definition - assessment-component
definition

## Faculty & Assignment

Owns: - faculty identity/employment - designation and department
relationship - faculty contact/address - faculty qualifications -
faculty experience - faculty accreditation/profile records - faculty
documents - teaching assignments

## Results & Eligibility

Owns: - assessments - marks - result imports - published results -
credits - eligibility and progression

## Finance

Owns: - fee definitions - fee structures - student charges - payments -
Candidate Fee Desk workflow

------------------------------------------------------------------------

# 3. Student profile database architecture

The screenshots show the student profile as a set of sections:
Registration Detail, Aadhaar Detail, Bank Detail and Photo/Document
functions. The data should therefore be stored across the following
tables.

## 3.1 `students`

**Purpose:** stable student identity record.

Suggested columns: - `id UUID PK` -
`enrollment_no VARCHAR(50) UNIQUE NOT NULL` - `first_name` -
`middle_name` - `last_name` - `display_name` - `status` - `created_at` -
`updated_at` - `created_by` - `updated_by`

Do not put admission-specific, academic-semester-specific, bank,
Aadhaar, scholarship, qualification or result fields here.

## 3.2 `student_personal_details`

One-to-one with `students`.

Fields represented by the supplied student UI/import: -
`student_id PK/FK` - `date_of_birth` - `gender` - `place_of_birth` -
`religion` - `nationality` - `mother_tongue` - `domicile_state` -
`student_email` - `student_mobile`

Sensitive contact fields must not be exposed by default to every role.

## 3.3 `student_guardians`

One student can have one or more guardian records.

Fields: - `id` - `student_id` - `relationship` - `name` - `mobile` -
`email` - `occupation` - `annual_income` - `is_primary` - `created_at` -
`updated_at`

This replaces hard-coding only father/mother columns and also supports
guardian cases.

The government import currently supplies candidate name, father name,
mother name, mobile, email, family income and address data; those become
source data for normalized student/guardian/address records after
staging validation.

## 3.4 `student_addresses`

One-to-many.

Fields: - `id` - `student_id` - `address_type` =
`PERMANENT | CORRESPONDENCE` - `address_line_1` - `address_line_2` -
`address_line_3` - `village` - `taluka` - `district` - `state` -
`pincode` - `is_current` - `valid_from` - `valid_to`

Do not store permanent and correspondence addresses as two repeated
column groups on `students`.

## 3.5 `student_admissions`

One student can have multiple admission events only when business rules
permit it; each admission must be identifiable.

Fields: - `id` - `student_id` - `academic_year_id` - `application_id` -
`admission_date` - `admission_type` - `candidature_type` -
`institute_code` - `institute_name` - `program_id` - `choice_code` -
`seat_type` - `allotted_seat_type` - `merit_no` - `merit_marks` -
`entrance_exam_type` - `entrance_roll_no` - `entrance_percentile` -
`reported_date` - `source_import_row_id` - `created_at`

Business identifiers such as DTE Application ID are unique where
applicable.

## 3.6 `student_admission_categories`

Stores admission-category information separately from general personal
identity.

Fields: - `id` - `student_admission_id` - `constitutional_category` -
`special_reservation_type` - `ph_type` - `defence_type` -
`linguistic_minority` - `religious_minority` - `home_university` -
`region` - `seat_type`

This is important because category/seat allocation is admission context,
not immutable personal identity.

## 3.7 `student_qualifying_examinations`

One student can have multiple qualifying/previous-education records.

Fields: - `id` - `student_id` - `exam_level` - `board_university` -
`school_college_name` - `seat_or_roll_no` - `passing_month` -
`passing_year` - `mathematics_percentage` - `physics_percentage` -
`chemistry_percentage` - `additional_subject` - `subject_percentage` -
`english_percentage` - `total_percentage` - `eligibility_percentage` -
`source` - `verified_status`

This table supports both the government-admission Excel data and the
profile UI.

## 3.8 `student_scholarship_profiles`

Fields: - `id` - `student_id` - `scholarship_applied` -
`scholarship_type` - `scheme_id` if the scholarship module later has a
controlled scheme list - `status` - `verified_by` - `verified_at` -
`remarks`

Do not use a single free-text `scholarship` field if the institution
needs reporting.

## 3.9 `student_aadhaar_details`

**Sensitive table.**

Fields: - `student_id PK/FK` - `aadhaar_number_encrypted` -
`aadhaar_last4` - `mobile_linked_to_aadhaar` - `name_as_per_aadhaar` -
`verification_status` - `verified_by` - `verified_at` - `created_at` -
`updated_at`

Rules: - never log full Aadhaar; - never return it in ordinary list
APIs; - encrypt at rest at the application/data layer as appropriate; -
sensitive access creates an audit event; - uniqueness of the full
Aadhaar value, if required, must use a secure lookup representation
rather than exposing plaintext.

## 3.10 `student_bank_accounts`

**Sensitive table.**

Fields: - `id` - `student_id` - `account_holder_name` - `bank_name` -
`branch_name` - `account_number_encrypted` - `account_last4` -
`ifsc_code` - `verification_status` - `verified_by` - `verified_at` -
`is_primary` - `created_at` - `updated_at`

Do not make bank data part of the main student table.

## 3.11 `student_documents`

Typed document metadata.

Initial document types observed in the supplied screens: -
`AADHAAR_CARD` - `PAN_CARD` if required for a student -
`PASSPORT_PHOTO` - `SIGNATURE` - `ADMISSION_REPORTING_RECEIPT`

Future document types are added through controlled configuration rather
than new columns.

Fields: - `id` - `student_id` - `document_type` - `storage_key` -
`original_filename` - `mime_type` - `file_size_bytes` -
`checksum_sha256` - `version` - `version_status` -
`verification_status` - `reviewed_by` - `reviewed_at` -
`rejection_reason` - `uploaded_by` - `uploaded_at`

The UI's "View/Download" operation must go through authorization and
audit checks.

## 3.12 `student_enrollments`

This remains the authoritative academic lifecycle table.

Fields: - `id` - `student_id` - `academic_year_id` - `semester_id` -
`department_id` - `program_id` - `batch_id` - `scheme_id` - `status` -
`enrollment_date` - `exit_date` - `status_reason`

Unique constraint should prevent duplicate enrollment for the same
student/year/semester where the business rule requires one active
enrollment.

------------------------------------------------------------------------

# 4. Faculty profile database architecture

The supplied faculty profile screens contain Profile Information,
Qualification Detail, Academic Detail, Bank Detail and Documents. The
AICTE biodata also confirms faculty records must support employment
identity, qualifications, experience, publications, conference papers,
guidance, books/IPRs/patents, memberships, consultancy, awards, grants
and professional-institution interaction. fileciteturn3file0L5-L44

## 4.1 `faculties`

Stable faculty/employment identity.

Fields: - `id` - `employee_code` - `first_name` - `middle_name` -
`last_name` - `display_name` - `department_id` - `designation` -
`employment_type` - `employment_status` - `date_of_joining` -
`date_of_relieving` - `official_email` - `personal_email` - `mobile` -
`residential_telephone` - `created_at` - `updated_at`

## 4.2 `faculty_personal_details`

Fields: - `faculty_id PK/FK` - `date_of_birth` - `gender` -
`nationality` - `domicile_state` - `constitutional_category` -
`special_reservation` - other controlled personal attributes explicitly
approved by the institution

**Important:** the current screenshot labels one faculty field
"Constitutional Category of Admission". That label is preserved as
source UI terminology, but its business meaning for an employee must be
confirmed before it becomes a production field name.

## 4.3 `faculty_addresses`

One-to-many: - `faculty_id` - `address_type` - `address_line_1` -
`address_line_2` - `district` - `state` - `pincode` - `is_current` -
`valid_from` - `valid_to`

## 4.4 `faculty_qualifications`

One faculty → many qualifications.

Fields: - `id` - `faculty_id` - `qualification_level` =
`UG | PG | PHD | OTHER` - `course_name` - `branch_specialization` -
`class_or_grade` - `university_or_board` - `passing_year` -
`is_highest` - `remarks`

This is preferable to columns such as `ug_course`, `pg_course`,
`phd_course`, because one faculty member can have multiple
qualifications.

The supplied AICTE example has B.E. 1st Class, M.E. 1st Class and no
Ph.D.; the profile UI also provides UG, PG, PhD and Other sections.
fileciteturn3file0L12-L20

## 4.5 `faculty_experience`

One-to-many or one current summary plus history.

Fields: - `id` - `faculty_id` - `experience_type` =
`TEACHING | INDUSTRY | RESEARCH` - `organization` - `designation` -
`start_date` - `end_date` - `experience_years` - `remarks`

The AICTE format explicitly separates Teaching, Industry and Research
experience. fileciteturn3file0L21-L23

## 4.6 Faculty academic/accreditation records

Use separate typed tables for records that have materially different
structure.

### `faculty_publications`

-   title
-   journal
-   publication date/year
-   publication type
-   national/international
-   indexing
-   DOI/reference

### `faculty_conference_presentations`

-   title
-   conference name
-   date/year
-   national/international
-   location
-   paper/reference

### `faculty_books`

-   title
-   publisher
-   ISBN
-   publication year
-   authorship role

### `faculty_patents`

-   title
-   patent/application number
-   filing date
-   status
-   grant date

### `faculty_professional_memberships`

-   organization
-   membership type
-   membership number
-   membership date
-   status

### `faculty_consultancies`

-   title/project
-   client/organization
-   role
-   start/end
-   amount if institution requires financial reporting
-   status

### `faculty_awards`

-   title
-   awarding organization
-   date/year
-   description

### `faculty_grants`

-   grant/project title
-   funding agency
-   amount
-   year
-   role
-   status

### `faculty_professional_interactions`

-   interaction type
-   organization
-   title/topic
-   date
-   description

### `faculty_guidance`

-   guidance type = `PHD | MASTERS_PROJECT | OTHER`
-   scholar/student name or linked internal student/person where
    available
-   project/topic
-   university
-   start/year
-   completion/year
-   status

The AICTE source explicitly distinguishes Ph.D. projects and
Masters-level projects. fileciteturn3file0L31-L32

## 4.7 `faculty_documents`

Document metadata: - passport photo - signature - Aadhaar - PAN - future
certificates/appointment documents

Same versioning, checksum, verification and sensitive-access rules as
student documents.

## 4.8 `faculty_bank_accounts`

Sensitive table, structurally similar to student bank accounts but owned
by Faculty & Assignment.

------------------------------------------------------------------------

# 5. Faculty teaching assignment architecture

The profile UI shows "Subjects Taught", but this must **not** be a field
on `faculties`.

Authoritative source:

`faculty_assignments`

Fields: - faculty - scheme subject - academic year - semester -
department/program - batch - assignment role - start/end - assigned by -
status

The faculty profile can display a derived list:

`faculty → assignments → scheme_subject → subject`

This preserves history and supports workload/result/authorization
requirements.

------------------------------------------------------------------------

# 6. Course Scheme database architecture

The supplied Course Scheme workbook contains six semesters and course
rows with: - Sr. No. - Course Title - Abbreviation - Level - Course
Type - Course Code - IKS hours - learning scheme/contact hours -
self-learning/notional-learning hours - credits - paper duration -
theory assessment - practical assessment - SLA assessment - total marks.

The workbook includes examples such as BASIC MATHEMATICS (`CCH105`),
ENGINEERING PHYSICS (`CCH101`), FUNDAMENTAL OF ELECTRONICS (`ITH102`),
WEB PAGE DESIGN (`ITH101`), and later subjects such as COMPUTER NETWORK
(`ITH302`), DATABASE MANAGEMENT SYSTEM (`ITH304`), PYTHON PROGRAMMING
(`ITH401`), MANAGEMENT INFORMATION SYSTEM (`ITH701`) and PROJECT
(`ITH702`).

## 6.1 `schemes`

Represents a curriculum/scheme version.

Fields: - `id` - `code` - `name` - `program_id` - `department_id` -
`effective_from_academic_year_id` - `effective_to_academic_year_id` -
`version` - `status` - `source_document_id` - `created_at`

A scheme becomes immutable once academic results/enrollments depend on
it.

## 6.2 `subjects`

Reusable subject identity.

Fields: - `id` - `code` - `title` - `abbreviation` - `status`

## 6.3 `scheme_subjects`

A subject as defined inside one scheme and semester.

Fields: - `id` - `scheme_id` - `subject_id` - `semester_number` -
`course_code` - `course_level_code` - `course_type_code` - `credits` -
`total_iks_hours` - `contact_cl_hours_per_week` -
`contact_tl_hours_per_week` - `contact_ll_hours_per_week` -
`self_learning_hours_per_week` - `notional_learning_hours_per_week` -
`paper_duration_hours` - `total_marks` - `is_elective` -
`elective_group_id` - `display_order`

`course_level_code` and `course_type_code` remain codes until the
institution provides their official definitions. Do not invent meanings
from the spreadsheet alone.

## 6.4 `scheme_subject_assessment_components`

Normalize the assessment columns instead of adding many hard-coded
fields.

Fields: - `id` - `scheme_subject_id` - `component_type` -
`maximum_marks` - `minimum_marks` - `weight/notes` if required -
`display_order`

Initial component types supported by the workbook: - `THEORY_FA` -
`THEORY_SA` - `PRACTICAL_FA` - `PRACTICAL_SA` - `SLA`

This lets the scheme support different assessment structures without
changing the database every time a course has a different pattern.

## 6.5 `scheme_elective_groups`

Required because the workbook contains `ELECTIVE I` and `ELECTIVE II`.

Fields: - `id` - `scheme_id` - `semester_number` - `group_code` -
`title` - `minimum_selection` - `maximum_selection`

## 6.6 `scheme_elective_options`

Fields: - `id` - `elective_group_id` - `subject_id` -
`scheme_subject_id` - `display_order`

The actual elective option subjects are not present in the supplied
workbook excerpt, so their structure is prepared but their option
records must be supplied when the institution provides them.

------------------------------------------------------------------------

# 7. Scheme import architecture

Course schemes should be importable using the same safe staged pattern
as government student data:

`Source Excel → Scheme Import Batch → Staging Rows → Validation → Normalization → Draft Scheme → Review → Publish`

## `scheme_import_batches`

-   file
-   scheme target
-   uploaded by
-   status
-   checksum
-   counts
-   validation timestamps

## `scheme_import_rows`

-   batch
-   row number
-   raw row JSONB
-   normalized course code/title
-   semester
-   validation errors
-   processing status
-   resulting scheme_subject_id

Never overwrite a published scheme because a new Excel file was
uploaded.

------------------------------------------------------------------------

# 8. Government admitted-candidate import mapping

The supplied admitted-candidate workbook contains admission, identity,
contact, address, category, previous education, entrance-exam and
allotment fields.

Important source fields include: - Application ID - Candidate Name -
Father/Mother Name - Gender - DOB - Religion - Region - Mother Tongue -
Annual Family Income - Address - State/District/Taluka/Village/Pincode -
Mobile/E-mail/Phone - Candidature Type - Home University - Category -
PH/Defence/Minority fields - SSC board/year/seat number/marks - HSC
board/year/seat number/subject marks - CET/JEE identifiers and
percentiles - Merit No/Merit Marks - Institute Code/Name - Course Name -
Choice Code - Seat Type - Admission/Reported dates

Mapping rule:

**Raw Excel fields are not copied blindly into `students`.**

They flow through: 1. `import_batches` 2. `import_rows` 3.
matching/deduplication 4. normalized
student/admission/category/address/qualification entities 5.
`student_admissions.source_import_row_id`

Business identifiers such as Application ID, enrollment number and board
enrollment/seat numbers must have explicit matching precedence.

------------------------------------------------------------------------

# 9. Profile API projection architecture

A profile page can be returned as a read projection without
denormalizing the database.

Example:

`GET /students/{id}/profile`

Composes: - student identity - personal details - current admission -
current enrollment - category/reservation - guardians -
permanent/correspondence addresses - scholarship summary - Aadhaar
masked summary - bank masked summary - documents - academic summary

Example:

`GET /faculties/{id}/profile`

Composes: - faculty identity - department/designation -
personal/contact - current assignments - qualifications - experience -
publications - conferences - books/patents - memberships - consultancy -
awards - grants - professional interactions - guidance - documents

The database remains normalized; the API response may be nested for UI
convenience.

------------------------------------------------------------------------

# 10. Sensitive-data access model

The following must be classified as sensitive: - Aadhaar - PAN - bank
account number - bank documents - Aadhaar/PAN documents - personal
contact details where institutional policy requires protection.

Rules: - role/scope check on every access; - mask by default; - explicit
reveal/download action; - audit every sensitive reveal/download; - never
put full sensitive values in application logs; - never include them in
broad student/faculty list endpoints; - documents use signed/authorized
access rather than public URLs.

------------------------------------------------------------------------

# 11. Data ownership summary

  ----------------------------------------------------------------------------
  Data                                Authoritative table/context
  ----------------------------------- ----------------------------------------
  Student identity                    `students`

  Student personal details            `student_personal_details`

  Guardian                            `student_guardians`

  Address                             `student_addresses`

  Admission                           `student_admissions`

  Category/reservation                `student_admission_categories`

  Previous education                  `student_qualifying_examinations`

  Scholarship profile                 `student_scholarship_profiles`

  Aadhaar                             `student_aadhaar_details`

  Student bank                        `student_bank_accounts`

  Student files                       `student_documents`

  Academic lifecycle                  `student_enrollments`

  Faculty identity/employment         `faculties`

  Faculty personal                    `faculty_personal_details`

  Faculty address                     `faculty_addresses`

  Faculty qualification               `faculty_qualifications`

  Faculty experience                  `faculty_experience`

  Faculty publications                `faculty_publications`

  Faculty conference papers           `faculty_conference_presentations`

  Faculty books                       `faculty_books`

  Faculty patents                     `faculty_patents`

  Faculty memberships                 `faculty_professional_memberships`

  Faculty consultancy                 `faculty_consultancies`

  Faculty awards                      `faculty_awards`

  Faculty grants                      `faculty_grants`

  Faculty professional interaction    `faculty_professional_interactions`

  Faculty guidance                    `faculty_guidance`

  Faculty files                       `faculty_documents`

  Faculty bank                        `faculty_bank_accounts`

  Teaching assignment                 `faculty_assignments`

  Reusable subject                    `subjects`

  Scheme version                      `schemes`

  Subject-in-scheme                   `scheme_subjects`

  Assessment definition               `scheme_subject_assessment_components`

  Elective group                      `scheme_elective_groups`

  Elective options                    `scheme_elective_options`
  ----------------------------------------------------------------------------

------------------------------------------------------------------------

# 12. Constraints that must exist

## Student

-   `students.enrollment_no` UNIQUE.
-   Application IDs unique within their issuing system where applicable.
-   One current permanent address per student.
-   One current correspondence address per student.
-   One primary guardian where required.
-   One primary bank account where required.
-   One current passport photo/signature per document type.
-   No duplicate student created by repeated government import.

## Faculty

-   employee code UNIQUE.
-   official email UNIQUE if institution guarantees uniqueness.
-   qualification records are independent rows.
-   assignment uniqueness prevents the same
    faculty/subject/year/semester/batch from being assigned twice.

## Scheme

-   scheme code/version unique.
-   subject code unique at the reusable-subject level.
-   one subject occurrence per scheme/semester unless the business rule
    explicitly permits otherwise.
-   assessment components unique by
    `(scheme_subject_id, component_type)`.
-   published scheme definitions cannot be mutated destructively.

------------------------------------------------------------------------

# 13. Important UI-to-database rules

### Student

"Subjects/results/passed/failed" displayed on the student dashboard are
derived academic data. Do not store those counters as profile facts.

"Admission Fee" belongs to Finance, not the student profile.

"Payment History" belongs to Finance.

"Result" and "Year-Wise Result" belong to Results.

### Faculty

"Subjects Taught" is derived from faculty assignments.

"Result Analysis" is a reporting projection over results, not a faculty
profile field.

"Manage Workload" derives from assignments and workload rules.

"Books Published/IPRS/Patents", "Awards", "Grants Fetched", etc. are
separate owned records.

------------------------------------------------------------------------

# 14. Decisions intentionally NOT invented from the supplied files

The following require confirmation before making them authoritative:

1.  **Faculty "Constitutional Category of Admission":** should this
    actually be an employee reservation/category field, or should it be
    removed from the faculty domain?
2.  **Faculty subject entry:** should faculty manually maintain a list,
    or should it always be derived from academic assignments? The
    architecture currently treats assignments as authoritative.
3.  **Faculty qualification history:** do you want passing year,
    percentage/CGPA, institution address and certificate/document for
    each qualification?
4.  **Faculty accreditation details:** do you want the AICTE format
    stored as individual records (recommended) or only as summary
    counts?
5.  **Course Scheme identity:** the workbook gives course/scheme rows
    but does not clearly provide the official scheme
    name/code/version/effective academic year. These values are needed
    for `schemes`.
6.  **Course Type / Level codes:** the workbook contains values such as
    AEC, DSC, SEC, VEC, DSE, INP and level values such as I--V. Their
    official definitions should be supplied rather than guessed.
7.  **Elective I/II:** the workbook defines elective slots but does not
    provide the actual elective option subjects. Those can be added
    later without changing the architecture.
8.  **Student scholarship:** confirm whether scholarship type is a
    controlled list maintained by Scholarship Staff or a free-text
    field.
9.  **Student PAN:** the faculty UI shows PAN, while the student UI
    supplied here does not. Student PAN should not be added unless the
    college requires it.
10. **Student bank details:** confirm whether every student is required
    to have a bank account or only students using scholarship/refund
    workflows.
11. **Aadhaar:** confirm whether the application must store the full
    Aadhaar number or only a masked/verified representation plus secure
    document.
12. **Government source identifiers:** confirm the official precedence
    among Application ID, Enrollment No., Board Enrollment/Seat No. when
    deduplicating imports.

Until these are answered, they should remain explicit architecture
decisions rather than assumptions.

------------------------------------------------------------------------

# 15. Final architecture rule for the coding agent

When implementing the application:

> **Never create a database column simply because a UI screen contains a
> field. First identify the business owner, lifecycle, cardinality,
> sensitivity, historical requirement and authoritative source. Then
> place the fact in the smallest correct domain table and expose it to
> the UI through an API projection.**

The supplied profile screens are therefore treated as **requirements for
information and workflows**, not as a direct relational schema.

The supplied Course Scheme workbook is treated as a **curriculum
definition source**, not as a single database table.

The supplied government admission workbook is treated as an **external
import source**, not as the production student table.

This keeps the system aligned with the original architecture principle:

**THE SIMPLEST DATABASE THAT CORRECTLY REPRESENTS THE REAL BUSINESS
DOMAIN AND REMAINS SAFE AS THE SYSTEM GROWS.**
