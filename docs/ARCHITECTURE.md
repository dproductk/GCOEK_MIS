# GCOE Kolhapur Student Management System — Production Architecture

## 0. Purpose

This document is the **canonical technical architecture contract** for the GCOE Kolhapur Student Management System.

It is derived from the approved `CONTEXT.md` product requirements and the finalized architectural principles previously established for this project.

The purpose of this file is to ensure that:

- the architecture remains stable as features are added;
- future roles can be added without redesigning the core;
- future modules can be added without breaking existing domains;
- historical academic and financial information is preserved;
- security and authorization are enforced server-side;
- AI coding agents cannot casually cross domain boundaries;
- implementation decisions remain consistent across development sessions.

> **IMPORTANT:** `CONTEXT.md` defines product requirements. This document defines the architectural rules for implementing those requirements.

---

# 1. Architectural Objective

Build a **production-grade modular monolith** that is:

- secure;
- maintainable;
- auditable;
- scalable enough for college-wide expansion;
- easy for humans to understand;
- safe for AI coding agents to modify;
- resistant to accidental data corruption;
- extensible without destructive redesign.

The architecture must remain a **modular monolith** unless a deliberate architectural decision is approved.

Do not introduce microservices merely because the system grows.

The first response to growth should normally be:

1. improve domain boundaries;
2. improve database design;
3. improve indexes;
4. improve query/read interfaces;
5. introduce background processing where justified;
6. introduce read projections where justified;
7. scale application/database infrastructure;
8. split a module only when there is strong evidence that the modular monolith can no longer satisfy the requirement.

---

# 2. Architecture Stability Rule

## 2.1 The architecture is a contract

AI coding agents MUST treat this document as an architectural contract.

A feature request must not automatically change:

- bounded contexts;
- domain ownership;
- dependency direction;
- database ownership;
- authorization model;
- audit architecture;
- historical-data rules;
- transaction boundaries;
- core identity model.

If a requested feature appears to require an architectural change:

1. identify the conflict;
2. explain the impact;
3. propose the smallest architectural change;
4. do not silently modify the architecture.

---

# 3. Product Context

The system is for:

**Government College of Engineering, Kolhapur (Autonomous)**

The college uses DBATU/university systems for university-side activities.

This application is a **college-level operational record and management system**.

It is not intended to replace the university platform.

Current major workflows:

- government admission import;
- student onboarding;
- academic/result tracking;
- eligibility verification;
- student promotion;
- fee configuration;
- fee assignment;
- payment recording;
- student/faculty directory;
- academic structure;
- audit;
- analytics.

Future modules are expected.

---

# 4. Core Architectural Principle

The system is built around:

```text
Domain Ownership
      ↓
Controlled Access
      ↓
Guarded Business Operation
      ↓
Transactional State Change
      ↓
Persistent History
      ↓
Auditability
      ↓
Correction / Reversal when required
```

The system must never rely on the frontend alone to protect business rules.

---

# 5. Bounded Contexts

The initial bounded-context map is:

```text
Identity & Access
Academic Structure
Curriculum
Students
Admissions
Results & Eligibility
Faculty
Finance
Reporting
Audit
Documents / Sensitive Data
```

These are **domain boundaries**, not necessarily separate deployable applications.

A bounded context owns its domain rules and authoritative data.

---

# 6. Domain Ownership Rules

## Identity & Access owns

- users;
- authentication identity;
- roles;
- permissions;
- role assignments;
- account lifecycle;
- authentication policies.

It does not own student academic business data.

## Academic Structure owns

- departments;
- programs;
- academic years;
- academic context;
- semesters;
- divisions;
- academic structure configuration.

## Curriculum owns

- schemes;
- scheme versions;
- subjects/courses;
- assessment components;
- marking rules;
- eligibility rules.

## Students owns

- student identity;
- student profile;
- student enrollment;
- student academic association/history;
- permitted student data.

## Admissions owns

- import batches;
- staging rows;
- validation;
- normalization;
- identity matching;
- import execution.

## Results & Eligibility owns

- semester results;
- subject results;
- marks;
- credits;
- backlogs;
- eligibility evaluation;
- verification workflow/history.

## Faculty owns

- faculty profiles;
- qualifications;
- experience;
- faculty-related records;
- faculty assignments.

## Finance owns

- fee heads;
- fee configurations;
- fee assessments;
- fee components;
- payment records;
- payment history;
- financial status.

## Reporting owns

- reporting queries;
- analytics;
- reporting projections when justified.

Reporting does NOT become the source of truth for another domain.

## Audit owns

- append-oriented audit records;
- audit metadata;
- audit visibility.

Audit is a cross-cutting supporting capability.

---

# 7. The Single-Owner Rule

Every authoritative business datum must have one clear owner.

Bad:

```text
Student table
Finance table
Reporting table
```

where all three independently store authoritative student information.

Good:

```text
Students
   ↓
authoritative student data

Reporting
   ↓
query interface
   ↓
Students
```

A module may cache or project data for read performance, but the projection is never the source of truth.

---

# 8. Dependency Rules

## 8.1 Allowed dependency

Dependencies should flow through domain/application contracts.

```text
Reporting
    ↓
Student Query Contract
    ↓
Students
```

## 8.2 Forbidden dependency

Do not allow modules to bypass boundaries:

```text
Reporting
    ↓
direct database table access
```

or:

```text
Finance service
    ↓
direct modification of Student tables
```

## 8.3 No circular dependencies

Never introduce:

```text
A → B → C → A
```

If two domains appear to require each other, introduce an appropriate contract, application workflow, domain event, or shared stable abstraction rather than creating a circular dependency.

---

# 9. Role Architecture

Current roles are only the first release.

Current profiles:

```text
Student
Faculty
Admin / Sysadmin
```

Current faculty operational roles:

```text
Class Teacher
HOD
Administrative Head
Accountant
```

Future roles are expected.

Therefore:

**NEVER hard-code role behavior into the database schema.**

Use:

```text
User
  ↓
Role Assignment
  ↓
Role
  ↓
Permission
  ↓
Scope
```

The authorization model must support future:

- additional faculty roles;
- multiple roles per person;
- new administrative roles;
- new operational roles.

The current restriction of one faculty role at a time is a **business rule**, not a reason to design an unextendable database.

Role assignment history must be preserved.

---

# 10. Authorization Model

Authorization is:

```text
WHO
+
WHAT
+
WHERE
+
WHEN
```

Conceptually:

```text
User
  ↓
Role
  ↓
Permission
  ↓
Scope
```

Examples:

```text
Class Teacher
→ verify_class_eligibility
→ assigned division

HOD
→ verify_eligibility
→ own department

Accountant
→ record_payment
→ financial records

Student
→ update_own_profile
→ own record
```

A hidden frontend route is NOT authorization.

Every sensitive operation must be authorized on the backend.

---

# 11. Scope-Based Access

Do not create separate implementations of the same feature for every role when only the scope changes.

Example:

```text
Student Directory
```

can be one domain capability with different scopes:

```text
Student → own record
Faculty → permitted general student records
Class Teacher → assigned division
HOD → own department
Administrative Head → college-wide
Accountant → permitted fee-related records
```

Prefer reusable domain/application logic with explicit scope policies.

---

# 12. Configuration Must Be Data-Driven

Do not hard-code business configuration.

Never hard-code as permanent application logic:

- departments;
- choice codes;
- programs;
- seat capacities;
- schemes;
- scheme versions;
- subjects;
- course codes;
- marking rules;
- eligibility rules;
- fee heads;
- fee presets;
- academic years;
- semesters;
- divisions;
- promotion rules.

These should be represented as managed data/configuration wherever practical.

Adding a department should not require changing Python/TypeScript business logic.

---

# 13. Stable Internal IDs

Government identifiers are business identifiers, not database primary keys.

Use a stable internal Student ID.

Government identifiers may include:

- Application ID;
- Enrollment Number;
- Board/University Enrollment Number.

Apply appropriate uniqueness constraints to each identifier according to its business rules.

Do not treat all government identifiers as interchangeable.

---

# 14. Historical Data Principle

The system must preserve important historical state.

Do not simply overwrite:

- academic year;
- semester;
- division;
- scheme;
- class teacher;
- role assignment;
- fee configuration;
- payment history;
- results;
- eligibility decisions.

Prefer temporal/history records.

Example:

```text
Teacher A
assigned: X → Y

Teacher B
assigned: Y → current
```

The previous state must remain reconstructable.

---

# 15. Immutable Source History

For externally supplied authoritative data:

```text
Original Source
      ↓
Preserved
      ↓
Normalized Value
      ↓
Correction if required
```

Never destroy the original source merely because the application cleaned or corrected it.

This applies especially to government admission data.

---

# 16. Correction Rule

Corrections are **additive, not destructive**.

Never silently rewrite important historical evidence.

General pattern:

```text
Original Record
      ↓
Correction / Replacement / Reversal
      ↓
New Authoritative State
```

The correction should retain, where applicable:

- actor;
- timestamp;
- reason;
- reference to original;
- audit information.

Do not create a generic `CorrectionService` that understands every domain.

Each domain owns its correction semantics.

Examples:

```text
Finance
→ financial reversal

Results
→ result supersession

Documents
→ document replacement

Students
→ controlled student-data correction
```

---

# 17. State Transition Rule

Important business operations must use explicit state transitions.

Do not allow arbitrary field updates to bypass workflow rules.

Example:

```text
Eligibility:
PENDING → ELIGIBLE
PENDING → NOT_ELIGIBLE
```

Invalid transitions must be rejected.

Example:

```text
PAID → PAID
```

must not create another payment.

Business state changes must be implemented as domain/application operations, not arbitrary CRUD.

---

# 18. Business Invariants

Critical invariants must be enforced at multiple appropriate levels:

```text
Frontend
+
API validation
+
Application/domain rules
+
Database constraints where possible
```

The frontend is never the only enforcement layer.

Important invariants include:

### Students

- appropriate government identifiers are unique;
- academic history is preserved;
- Administrative Head cannot delete students.

### Imports

- re-uploading the same file does not create duplicates;
- conflicting identity matches are never auto-merged;
- only validated rows reach final import;
- original source file is preserved;
- successful rows are not imported again during retry.

### Schemes

- historical results remain tied to the correct scheme version;
- old schemes remain available for applicable students;
- changed rules create a new scheme version.

### Divisions

- one Class Teacher per division in the current release;
- assignment history is preserved.

### Eligibility

- teacher changes require reasons;
- HOD verification is a separate step;
- verification history is preserved.

### Promotion

```text
Eligible
+
Fee Set
+
Fee Paid
=
Automatic Promotion
```

### Finance

- fee presets come from configured fee options;
- partial payment is not supported in the current scope;
- duplicate payment is blocked;
- paid records are immutable under current rules;
- historical fee configuration remains preserved.

---

# 19. Transactions

Multi-step business operations must have explicit transaction boundaries.

Examples:

### Student import

```text
validate
→ match
→ create/update student
→ create enrollment
→ create account
→ audit
```

must be designed so partial failure cannot leave the system in an invalid state.

### Promotion

```text
eligibility confirmed
→ fee confirmed
→ payment confirmed
→ academic progression created
```

must be handled atomically where the business operation requires atomicity.

Transactions belong to the application/workflow layer.

---

# 20. Idempotency

Operations that may be retried must be designed for safe retry.

Especially:

- government imports;
- payment recording;
- account provisioning;
- background jobs;
- external integrations;
- future university API calls.

Example:

```text
Same import
      ↓
retry
      ↓
no duplicate students
```

Do not assume a request will only ever arrive once.

---

# 21. Government Excel Import Architecture

Never import Excel directly into final Student records.

Required pipeline:

```text
Upload
  ↓
Import Batch
  ↓
Staging Rows
  ↓
Validation
  ↓
Normalization
  ↓
Matching
  ↓
Preview
  ↓
Confirmation
  ↓
Final Import
  ↓
Student + Enrollment + Account
```

The original file must remain preserved.

Staging rows must retain:

- raw data;
- normalized data;
- source row;
- validation result;
- validation reason;
- matching result;
- final import status.

Conflicts must go to manual resolution.

---

# 22. Matching Rules

Matching precedence:

```text
1. Application ID
2. Enrollment Number
3. Board/University Enrollment Number
```

Outcomes:

```text
No match
→ new student

One valid match
→ existing student

Conflicting matches
→ CONFLICT
→ MANUAL REVIEW
→ EXPLICIT RESOLUTION
```

Never automatically merge conflicting students.

---

# 23. Scheme Architecture

Students remain associated with the scheme under which they entered.

If a scheme changes:

```text
Scheme G v1
        ↓
Scheme G v2
```

Do not mutate v1 in a way that changes historical results.

Historical results must reference the applicable scheme/version.

This is mandatory for backlog correctness.

---

# 24. Results Architecture

Results are historical academic evidence.

A published result should not be silently overwritten.

Use versioning/supersession when correction is required.

Conceptually:

```text
Result V1
   ↓ correction
Review
   ↓ approval
Result V2
   ↓
supersedes V1
```

V1 remains historical evidence.

---

# 25. Backlog Architecture

Backlogs are first-class academic records.

Example:

```text
Semester 1
→ Mathematics
→ BACKLOG
```

Later:

```text
Mathematics
→ CLEARED
```

The original backlog must remain visible.

The clearing attempt/result must be associated with the appropriate subject and scheme context.

---

# 26. Eligibility Architecture

Eligibility is a domain workflow.

Conceptually:

```text
Result Evaluation
      ↓
Class Teacher Review
      ↓
HOD Verification
      ↓
Eligible / Not Eligible
```

Current states:

```text
PENDING
ELIGIBLE
NOT_ELIGIBLE
```

Teacher/HOD actions that change or flag information must be auditable and reasoned where required.

---

# 27. Promotion Architecture

Promotion is not simply:

```text
student.year += 1
```

Instead:

```text
Eligibility Approved
      ↓
Fee Set
      ↓
Fee Paid
      ↓
Create Next Academic Enrollment
```

The previous enrollment remains historical.

Never delete the previous academic state.

---

# 28. Finance Architecture

Finance is its own domain.

Fee lifecycle:

```text
Fee Configuration
      ↓
Applicable Fee
      ↓
Student Fee Assessment
      ↓
Payment
```

Payment is a financial record, not merely:

```text
paid = true
```

Current scope:

- full payment only;
- no partial payment;
- duplicate payment blocked;
- paid records immutable.

Future corrections should use reversal/correction records rather than destructive editing.

---

# 29. Candidate Fee Desk

The accountant's primary workflow is:

```text
Candidate Fee Desk
```

Do not split the primary workflow into unrelated top-level features such as:

```text
Eligible Students
Set Fee
Mark Payment
```

The workflow should remain unified:

```text
Eligible Student
      ↓
Set Fee
      ↓
Payment
      ↓
History
```

Fee Analytics remains a separate reporting capability.

---

# 30. Sensitive Data

Sensitive information must be protected by default.

Examples:

- Aadhaar;
- bank details;
- sensitive personal information;
- restricted documents.

Default:

```text
MASKED
```

Explicit reveal:

```text
Authorized User
      ↓
Explicit Reveal Action
      ↓
Permission Check
      ↓
Decrypt
      ↓
Temporary Display
      ↓
Audit Event
```

Normal student APIs must not automatically return sensitive values.

Do not expose sensitive data merely because a user can view a Student profile.

---

# 31. Audit Architecture

Audit is mandatory.

Important actions should capture, where applicable:

- actor;
- role;
- action;
- target;
- timestamp;
- old value;
- new value;
- reason;
- request/source context.

Audit:

- imports;
- validation;
- student changes;
- account creation;
- role changes;
- teacher assignments;
- eligibility;
- result changes;
- teacher flags;
- HOD verification;
- fee configuration;
- fee assignment;
- payment;
- important system configuration.

Audit records must be append-oriented and protected from normal users.

---

# 32. Accountable Actor Pattern

Sensitive operations follow:

```text
Actor
+
Action
+
Target
+
Timestamp
+
Reason where applicable
```

Do not create different incompatible audit patterns in different modules.

The audit infrastructure should be reusable while domain semantics remain owned by the relevant domain.

---

# 33. Reporting Architecture

Reporting must access domain data through owned query interfaces.

Preferred:

```text
Reporting
   ↓
Domain Query Interface
   ↓
Authoritative Domain
```

Not:

```text
Reporting
   ↓
Other module's database tables
```

If actual load evidence later shows that live queries are too expensive:

```text
Authoritative Domain
      ↓
Read Projection
      ↓
Reporting
```

A projection is derived data, never a source of truth.

---

# 34. Layered Application Architecture

Within the modular monolith, use clear layers.

Conceptually:

```text
API / Presentation
        ↓
Application
        ↓
Domain
        ↓
Persistence / Infrastructure
```

### API

Responsible for:

- request parsing;
- API validation;
- authentication boundary;
- response formatting;
- HTTP/API errors.

### Application

Responsible for:

- workflows;
- orchestration;
- transactions;
- authorization coordination;
- idempotency;
- use cases.

### Domain

Responsible for:

- business rules;
- invariants;
- state transitions;
- domain validation.

### Infrastructure

Responsible for:

- database implementation;
- external data sources;
- file storage;
- external integrations.

Do not put core business rules inside UI components.

---

# 35. SOLID Rules

## Single Responsibility

A class/service/module should have one coherent reason to change.

Do not create giant services such as:

```text
EverythingService
StudentAndFeeAndResultService
GenericCorrectionService
```

## Open/Closed

New roles, eligibility strategies, and business configurations should generally be extendable without rewriting unrelated domains.

## Dependency Inversion

Depend on stable contracts/query interfaces rather than database implementation details.

## Interface Segregation

Prefer focused interfaces over enormous universal interfaces.

## Liskov Substitution

If abstractions are introduced, implementations must preserve the expected contract.

---

# 36. Strategy Pattern

Eligibility rules and similar variable business policies should be modeled as strategies/configurable rules rather than one giant conditional function.

Avoid:

```python
if scheme == ...
elif department == ...
elif year == ...
elif category == ...
```

when the rules are expected to grow.

Prefer a domain policy/strategy architecture that can accommodate new rule sets.

---

# 37. No Generic "God Service"

Do not create a universal service that understands every domain.

Bad:

```text
SystemService
CorrectionService
ManagementService
AdminService
```

with hundreds of unrelated operations.

Prefer:

```text
ImportService
EligibilityService
PromotionService
PaymentService
ResultCorrectionService
StudentCorrectionService
```

where each service belongs to an appropriate domain/application workflow.

---

# 38. Database Rules

The database is part of the integrity boundary.

Use:

- primary keys;
- foreign keys;
- unique constraints;
- check constraints where appropriate;
- indexes;
- appropriate nullability;
- transactional integrity;
- carefully designed deletion behavior.

Do not rely exclusively on application code for critical uniqueness/integrity rules when the database can enforce them.

---

# 39. Database Evolution

Never manually modify production database structure.

All schema changes must use migrations.

Migration rules:

1. make the smallest safe change;
2. preserve existing data;
3. consider backward compatibility;
4. test migration on representative data;
5. never casually drop historical columns/tables;
6. never destroy production history merely to simplify a migration.

---

# 40. Deletion Rules

Important academic, financial, and audit data should not be physically deleted as a normal business operation.

Prefer lifecycle states, archival, deactivation, replacement, or supersession.

Destructive operations must:

- be strongly restricted;
- be explicitly authorized;
- be audited;
- preserve evidence where required.

---

# 41. Security Rules

Minimum requirements:

- secure password hashing;
- forced first-login password change where required;
- backend authorization;
- role + permission + scope enforcement;
- input validation;
- server-side business validation;
- database constraints;
- CSRF protection where applicable;
- secure session/token architecture;
- rate limiting where appropriate;
- safe file uploads;
- restricted document access;
- secure error handling;
- environment-based secrets;
- no secrets in source control;
- safe migrations;
- backups;
- monitoring;
- least privilege.

Never trust:

```text
frontend role
frontend route
frontend button
frontend hidden field
```

as security controls.

---

# 42. File Upload Security

Government Excel and future documents are untrusted input.

Upload processing must consider:

- file type validation;
- size limits;
- safe storage;
- filename safety;
- malware/security scanning where appropriate;
- parser failure handling;
- checksum/hash where useful;
- source preservation;
- access control.

Never execute uploaded content.

---

# 43. Error Handling

Do not expose:

- stack traces;
- database errors;
- internal implementation details;
- secrets;
- sensitive data.

Expected business failures should become explicit domain/application errors.

API responses should use a consistent error structure.

---

# 44. Observability

Production operation should support:

- structured application logs;
- error tracking;
- health checks;
- database monitoring;
- background-job monitoring where used;
- audit visibility;
- performance monitoring;
- operational alerts where justified.

Logs and audit events are different:

```text
Logs
→ technical/system diagnostics

Audit
→ business accountability
```

Do not use ordinary application logs as a replacement for audit history.

---

# 45. Performance and Scaling Rules

Do not prematurely introduce infrastructure complexity.

First use:

- correct indexes;
- efficient queries;
- pagination;
- scoped queries;
- database constraints;
- efficient ORM usage;
- background processing for genuinely long operations.

Only introduce:

- caching;
- materialized views;
- read replicas;
- queues;
- projections;
- service extraction;

when actual requirements/evidence justify them.

---

# 46. Future Extension Rules

The architecture must accommodate:

- subject teacher assignment;
- additional faculty roles;
- multiple roles per person;
- HOD analytics;
- examinations;
- attendance;
- certificates;
- additional finance workflows;
- university API integration;
- notifications;
- advanced reporting;
- document workflows;
- alumni;
- graduation/exit;
- additional academic rules;
- more departments/programs;
- additional fee types.

A new feature should normally be added by extending an existing bounded context or introducing a clearly justified new bounded context.

Do not redesign unrelated domains.

---

# 47. Architecture Change Protocol

An AI coding agent MUST NOT change architecture silently.

Before an architectural change, document:

```text
1. Current architecture
2. Problem
3. Why current architecture is insufficient
4. Proposed change
5. Affected domains
6. Database impact
7. Security impact
8. Migration impact
9. Backward compatibility
10. Alternatives considered
```

The change should be recorded as an Architecture Decision Record.

---

# 48. Architecture Decision Records

Important architectural decisions should be recorded in `DECISIONS.md`.

Each decision should contain:

```text
Decision
Context
Problem
Options
Chosen approach
Reason
Consequences
Date
Status
```

Do not silently reverse an existing architectural decision.

If a decision must change, create a new decision that supersedes the previous one.

---

# 49. AI Coding Agent Operating Rules

Before changing code, the AI agent MUST:

1. Read `CONTEXT.md`.
2. Read this architecture document.
3. Identify the affected bounded context.
4. Identify the owner of the affected data.
5. Inspect existing models.
6. Inspect migrations.
7. Inspect APIs/services.
8. Inspect tests.
9. Check authorization.
10. Check business invariants.
11. Check historical-data implications.
12. Check dependencies.
13. Check whether the change violates an existing architecture rule.

The agent must not jump directly into coding.

---

# 50. AI Agent Forbidden Behaviors

The AI agent MUST NOT:

- invent business rules marked TBD;
- bypass authorization;
- rely only on frontend authorization;
- directly edit another domain's tables;
- create duplicate sources of truth;
- silently change core entity semantics;
- delete historical data for convenience;
- overwrite financial history;
- overwrite result history;
- automatically merge conflicting students;
- hard-code configurable business data;
- create giant generic services;
- create circular dependencies;
- introduce microservices without architectural approval;
- introduce unnecessary caching;
- expose sensitive fields by default;
- store passwords in plaintext;
- place secrets in source control;
- manually alter production schema;
- skip migrations;
- ignore failing tests;
- remove tests merely to make a change pass;
- silently alter an approved workflow.

---

# 51. AI Agent Change Checklist

For every non-trivial change, answer:

```text
[ ] Which bounded context owns this feature?
[ ] Which data does it own?
[ ] Am I modifying another domain's data directly?
[ ] Does this introduce a new source of truth?
[ ] Does this affect historical records?
[ ] Does this introduce a new state transition?
[ ] Are invariants enforced?
[ ] Is the operation transactional?
[ ] Is it idempotent where necessary?
[ ] Is authorization enforced server-side?
[ ] Is scope enforced?
[ ] Does the action require audit logging?
[ ] Does it expose sensitive data?
[ ] Does it require a migration?
[ ] Could the change break future roles?
[ ] Could the change break future modules?
[ ] Does it introduce a circular dependency?
[ ] Does it violate an existing ADR?
[ ] Are tests updated?
```

---

# 52. Future Role Rule

Adding a role should normally require:

```text
New Role
   ↓
Role Assignment
   ↓
Existing Permissions
   +
New Permissions if necessary
   ↓
Scope Policy
   ↓
UI/navigation
```

It should NOT require:

```text
rewrite Student model
rewrite Finance model
rewrite Results model
rewrite authentication
```

---

# 53. Future Module Rule

A future module such as Attendance should look conceptually like:

```text
Attendance
    ↓
Student Query Contract
    ↓
Students
```

not:

```text
Attendance
    ↓
directly modify Student database
```

Likewise, Examination should consume academic/curriculum contracts rather than duplicating schemes and subjects.

---

# 54. UI Architecture Rule

UI is a representation of domain capabilities.

Do not let the UI define business authority.

For example:

```text
Button hidden
```

does not mean:

```text
permission denied
```

The backend must independently determine whether the operation is allowed.

Reusable UI components should be preferred when the underlying capability is shared.

---

# 55. Current vs Future Requirements

The architecture must distinguish:

### Current requirement

Something explicitly required for the first release.

### Future extension

Something expected later.

### TBD

A business decision that has not been finalized.

For TBD requirements:

**Do not invent a permanent business rule.**

The architecture should provide extension points without pretending the business decision has already been made.

---

# 56. What "Scalable" Means Here

Scalability does NOT mean adding maximum infrastructure now.

For this system, scalability primarily means:

```text
More students
More departments
More roles
More permissions
More academic years
More schemes
More subjects
More workflows
More financial records
More reports
More AI coding agents
```

without corrupting the core model.

The first scalability target is therefore **architectural scalability**, followed by infrastructure scalability when actual usage requires it.

---

# 57. Canonical Domain Model

The conceptual domain map is:

```text
                    COLLEGE SYSTEM
                         │
        ┌────────────────┼────────────────┐
        │                │                │
     PEOPLE           ACADEMICS         FINANCE
        │                │                │
   Identity           Departments       Fee Heads
   Roles              Programs          Assessments
   Faculty            Schemes           Payments
   Students            Subjects          Ledger
        │                │                │
        └────────────────┼────────────────┘
                         │
                      WORKFLOWS
                         │
       ┌─────────────────┼─────────────────┐
       │                 │                 │
    Admission         Results         Eligibility
       │                 │                 │
    Excel →            Marks →        Teacher →
    Staging            Backlogs       HOD
       │                 │                 │
       └─────────────────┼─────────────────┘
                         │
                     Promotion
                         │
                   Fee Set + Paid
                         │
                  Next Enrollment
```

This is the conceptual architecture, not a mandatory one-table-per-box schema.

---

# 58. The Most Important Rules

If an AI agent remembers nothing else, it must remember these:

### Rule 1
**One domain owns its data.**

### Rule 2
**Never create duplicate sources of truth.**

### Rule 3
**Never destroy important history to simplify implementation.**

### Rule 4
**Corrections are additive, not destructive.**

### Rule 5
**Authorization is User + Role + Permission + Scope.**

### Rule 6
**Frontend restrictions are never sufficient security.**

### Rule 7
**Business invariants must be enforced server-side and, where possible, in the database.**

### Rule 8
**Important workflows are guarded state transitions, not arbitrary CRUD.**

### Rule 9
**Important multi-step operations require transaction boundaries.**

### Rule 10
**Retryable operations must be idempotent where necessary.**

### Rule 11
**Business configuration should be data-driven.**

### Rule 12
**New roles must not require redesigning the core identity model.**

### Rule 13
**New features must not casually cross bounded-context boundaries.**

### Rule 14
**Reporting reads through contracts, not another domain's tables.**

### Rule 15
**Sensitive data is masked by default and explicitly revealed only when authorized.**

### Rule 16
**Every important administrative/financial/academic action must be attributable and auditable.**

### Rule 17
**Do not introduce microservices or infrastructure complexity without evidence.**

### Rule 18
**Do not silently change architecture.**

### Rule 19
**When requirements are ambiguous, do not invent a business rule.**

### Rule 20
**Optimize for long-term correctness and extensibility, not the fastest short-term implementation.**

---

# 59. Final Architecture Contract

The system should remain:

```text
MODULAR MONOLITH
      +
BOUNDED DOMAINS
      +
CLEAR DATA OWNERSHIP
      +
USER → ROLE → PERMISSION → SCOPE
      +
BUSINESS INVARIANTS
      +
GUARDED STATE TRANSITIONS
      +
TRANSACTIONAL WORKFLOWS
      +
IDEMPOTENT OPERATIONS
      +
IMMUTABLE / HISTORICAL EVIDENCE
      +
AUDITABILITY
      +
SENSITIVE-DATA PROTECTION
      +
QUERY CONTRACTS
      +
DATA-DRIVEN CONFIGURATION
      +
AI-AGENT GUARDRAILS
```

The architecture should evolve by **extension**, not by repeatedly rewriting the foundation.

The current roles and workflows are the first release, not the permanent limit of the system.

The architectural goal is:

> **A simple modular monolith that can grow into a complete college management platform without sacrificing data integrity, security, historical correctness, maintainability, or domain boundaries.**

---

# 60. Source of Authority

For future development:

```text
CONTEXT.md
    ↓
Product requirements and business rules

ARCHITECTURE.md
    ↓
Technical architecture and engineering rules

DECISIONS.md
    ↓
Approved architectural decisions and changes

Actual codebase
    ↓
Current implementation source of truth
```

When these conflict:

1. Do not silently choose one.
2. Identify the conflict.
3. Determine whether it is a product requirement, architecture rule, implementation issue, or approved exception.
4. Resolve/document the decision before making a destructive change.

**The architecture is intended to remain stable while the product grows.**
