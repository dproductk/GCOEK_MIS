# AGENTS.md

# AI Coding Agent Instructions

## College Student Management & Administrative Data System

> This file is the operating contract for AI coding agents working on
> this project. Read and follow it before modifying the codebase.

------------------------------------------------------------------------

# 1. Core Mission

Build the software according to the project's existing architecture,
security rules, database design, UI design language, and requirements.

The agent must:

-   Understand before changing.
-   Reuse existing functionality before creating new functionality.
-   Preserve architectural boundaries.
-   Protect data integrity and security.
-   Write efficient database queries.
-   Match the established UI/design language.
-   Keep the code maintainable and scalable.
-   Avoid unnecessary complexity.
-   Never silently redesign the system.

The goal is:

> **The simplest implementation that correctly satisfies the requirement
> without violating architecture, security, data integrity, performance,
> or design rules.**

------------------------------------------------------------------------

# 2. Project Rules Are Authoritative

Before making changes, determine which project documents apply.

Primary project documents:

-   `ARCHITECTURE.md` --- system architecture and domain rules
-   `DATABASE_ARCHITECTURE.md` --- database/domain model and data
    ownership
-   `SECURITY.md` --- security contract
-   `FILE_MAP.md` --- current project file/module map
-   `TASKS.md` --- planned and active work
-   `FULL_PROJECT_PROMPT.md` --- complete product requirements and
    context
-   `DESIGN/` --- UI screenshots, design references, visual language
-   `RUNBOOK.md` --- operational/deployment procedures

### Important

Do not assume that an old implementation is correct merely because it
already exists.

When documents and code conflict:

1.  Identify the conflict.
2.  Follow the higher-level project rule.
3.  Do not silently redesign architecture.
4.  If the conflict cannot be resolved safely, stop and ask for
    clarification.

------------------------------------------------------------------------

# 3. Mandatory Feature Development Cycle

Every meaningful feature must follow this workflow.

## Step 1 --- Understand the task

Before coding:

-   Read the complete feature request.
-   Identify the user/business problem.
-   Identify affected users/roles.
-   Identify affected domain(s).
-   Identify expected inputs, outputs, states, and workflows.
-   Identify whether the feature changes existing behavior.

Do not start coding immediately.

------------------------------------------------------------------------

## Step 2 --- Read `FILE_MAP.md`

Check:

-   Existing backend modules
-   Existing frontend modules
-   Existing models
-   Existing APIs
-   Existing services
-   Existing serializers
-   Existing components
-   Existing pages
-   Existing utilities
-   Existing tests

Use `FILE_MAP.md` to locate likely existing code before creating new
files.

------------------------------------------------------------------------

## Step 3 --- Identify Existing Functionality

Search the codebase for:

-   Similar features
-   Similar API endpoints
-   Similar models
-   Similar serializers
-   Similar services
-   Similar React components
-   Similar hooks
-   Similar validation logic
-   Similar queries
-   Similar permissions

### Mandatory rule

> **Never create duplicate functionality without first checking whether
> an equivalent implementation already exists.**

Prefer:

1.  Reuse
2.  Extend
3.  Refactor
4.  Create new functionality only when necessary

------------------------------------------------------------------------

# 4. Step 4 --- Read Relevant Project Rules

Before implementation, read the documents relevant to the feature.

At minimum, consider:

### Backend/data feature

-   `ARCHITECTURE.md`
-   `DATABASE_ARCHITECTURE.md`
-   `SECURITY.md`
-   `FULL_PROJECT_PROMPT.md`

### UI feature

Also read:

-   Relevant files in `DESIGN/`

### Operational/deployment feature

Also read:

-   `RUNBOOK.md`
-   `SECURITY.md`

### Task tracking

Read:

-   `TASKS.md`

Do not read every file unnecessarily. Read what is relevant to the
feature.

------------------------------------------------------------------------

# 5. Step 5 --- Inspect Existing Code

Before designing the implementation:

-   Open the relevant existing files.
-   Understand their responsibilities.
-   Understand current data flow.
-   Understand API contracts.
-   Understand existing relationships.
-   Understand authorization.
-   Understand existing query patterns.
-   Understand existing component patterns.

Do not modify code you have not understood.

------------------------------------------------------------------------

# 6. Step 6 --- Inspect `DESIGN/`

For every UI feature, inspect the relevant screenshots/reference files
in `DESIGN/`.

Determine:

-   Layout
-   Spacing
-   Typography
-   Colors
-   Cards
-   Tables
-   Buttons
-   Forms
-   Navigation
-   Sidebar/header patterns
-   Icons
-   Status indicators
-   Modal/drawer patterns
-   Responsive behavior
-   Empty/loading/error states
-   Page hierarchy

### Mandatory UI rule

> **Do not invent a new visual style when an existing design reference
> exists.**

The implementation should feel like it belongs to the same application.

If a screenshot does not specify something, reuse an established project
pattern rather than inventing a completely different pattern.

Only introduce a new visual pattern when the requirement genuinely needs
one.

------------------------------------------------------------------------

# 7. Step 7 --- Design Before Implementation

Before writing substantial code, determine:

### Backend

-   Which domain owns the feature?
-   Which existing models are involved?
-   Are new models actually required?
-   Which service/business logic is required?
-   Which API endpoints are required?
-   Which permissions/scopes apply?
-   Which states/transitions apply?

### Database

-   Is the existing schema sufficient?
-   Does a new table represent a genuinely new domain entity?
-   Are relationships normalized?
-   Are historical records preserved?
-   Are constraints required?
-   Are indexes required based on actual queries?

### Frontend

-   Which existing page/component should be extended?
-   Which reusable components can be used?
-   What API data is required?
-   What loading/error/empty states are required?
-   How does the UI match the existing design?

### Security

-   Who can access it?
-   What data is sensitive?
-   Can the request expose another user's data?
-   Are object-level and scope checks required?
-   Does the operation need audit logging?
-   Can duplicate requests cause corruption?

------------------------------------------------------------------------

# 8. Do Not Over-Engineer

Do not introduce:

-   Microservices
-   Event sourcing
-   CQRS
-   Kafka
-   Unnecessary caching
-   Unnecessary abstraction layers
-   Unnecessary design patterns
-   Duplicate repositories/services
-   Generic frameworks for one simple use case

unless explicitly required by the project architecture or task.

Use the existing modular-monolith architecture.

------------------------------------------------------------------------

# 9. Database Rules

Follow `DATABASE_ARCHITECTURE.md`.

Never:

-   Create duplicate sources of truth.
-   Store the same business fact in multiple authoritative places.
-   Create giant domain tables.
-   Put unrelated domain entities into one table.
-   Use comma-separated values for relationships.
-   Use JSONB where a relational structure is required.
-   Delete historical academic/financial records to fix a mistake.
-   Modify historical definitions in a way that changes past meaning.

Before adding a model/table, ask:

> **Is this a real domain entity, or am I creating a table because the
> implementation is inconvenient?**

------------------------------------------------------------------------

# 10. Django Query Performance Rules

Database performance is a mandatory design concern.

The system is expected to grow substantially, so query patterns must be
written with scale in mind.

## 10.1 Never Assume ORM Queries Are Free

Every ORM operation can become a database query.

Before writing code, consider:

-   Number of queries
-   Number of rows returned
-   Joins
-   Related-object access
-   Pagination
-   Indexes
-   Aggregations
-   Serialization cost

------------------------------------------------------------------------

## 10.2 Prevent N+1 Queries

Never write code that causes one query for the parent list and another
query for every item.

Bad pattern:

``` python
students = Student.objects.all()

for student in students:
    print(student.department.name)
```

If `department` is not loaded efficiently, this can produce many
queries.

Use:

``` python
students = Student.objects.select_related("department")
```

For reverse or many-to-many relationships:

``` python
students = Student.objects.prefetch_related("documents")
```

------------------------------------------------------------------------

## 10.3 `select_related()` vs `prefetch_related()`

Use:

### `select_related()`

For:

-   `ForeignKey`
-   `OneToOneField`

Example:

``` python
Student.objects.select_related(
    "admission",
    "department",
    "program",
)
```

### `prefetch_related()`

For:

-   Reverse ForeignKey
-   Many-to-many relationships

Example:

``` python
Student.objects.prefetch_related(
    "documents",
    "enrollments",
)
```

Do not use either blindly. Load only relationships actually required by
the endpoint.

------------------------------------------------------------------------

# 11. Query Only What You Need

Avoid unnecessarily loading large records.

Use:

``` python
.values(...)
.values_list(...)
.only(...)
.defer(...)
```

when appropriate.

Example:

``` python
Student.objects.values(
    "id",
    "enrollment_no",
    "full_name",
)
```

Do not load:

-   Large document metadata
-   Unneeded sensitive fields
-   Large text fields
-   Unrelated relationships

unless required.

------------------------------------------------------------------------

# 12. Filter in the Database

Do not retrieve thousands of rows and filter them in Python when
PostgreSQL can filter them.

Bad:

``` python
students = list(Student.objects.all())

active = [
    student for student in students
    if student.status == "ACTIVE"
]
```

Better:

``` python
students = Student.objects.filter(status="ACTIVE")
```

Prefer database-side:

-   Filtering
-   Ordering
-   Aggregation
-   Annotation
-   Counting
-   Existence checks

over Python-side processing when practical.

------------------------------------------------------------------------

# 13. Avoid Loading Entire Tables

Never use unrestricted large-table queries for API responses.

Avoid:

``` python
Student.objects.all()
```

when the endpoint could return thousands of students.

Use:

-   Filtering
-   Pagination
-   Search constraints
-   Appropriate ordering
-   Field selection

Large lists must be paginated.

------------------------------------------------------------------------

# 14. Use `exists()` Correctly

If only existence matters:

Use:

``` python
queryset.exists()
```

instead of loading records.

Example:

``` python
if Student.objects.filter(enrollment_no=value).exists():
    ...
```

------------------------------------------------------------------------

# 15. Use `count()` Correctly

If only the database count is required:

``` python
queryset.count()
```

Avoid:

``` python
len(queryset)
```

when the QuerySet does not need to be loaded into memory.

Do not call `count()` repeatedly on the same queryset unnecessarily.

------------------------------------------------------------------------

# 16. Use Database Aggregation

Do not retrieve thousands of records just to calculate:

-   Count
-   Sum
-   Average
-   Minimum
-   Maximum
-   Grouped statistics

Prefer:

``` python
from django.db.models import Count

Department.objects.annotate(
    student_count=Count("students")
)
```

Use PostgreSQL for work PostgreSQL can perform efficiently.

------------------------------------------------------------------------

# 17. Avoid Queries Inside Loops

This is a critical rule.

Bad:

``` python
for student in students:
    fees = FeeCharge.objects.filter(student=student)
```

This can create N+1 queries.

Instead, determine the required relationship/queryset and fetch the data
efficiently.

------------------------------------------------------------------------

# 18. QuerySet Reuse

Do not accidentally evaluate the same QuerySet repeatedly.

Understand when QuerySets are evaluated.

Avoid unnecessary:

``` python
list(queryset)
len(queryset)
queryset.count()
queryset.exists()
```

combinations when one operation could satisfy the requirement.

------------------------------------------------------------------------

# 19. Serializer Query Rules

DRF serializers can accidentally create N+1 queries.

Before returning nested/related data:

-   Inspect serializer relationships.
-   Add `select_related()` / `prefetch_related()` in the queryset.
-   Avoid database queries inside serializer methods.
-   Avoid calling `.objects.get()` inside `SerializerMethodField` for
    every object.
-   Avoid expensive calculations repeatedly during serialization.

Prefer preparing required data in the queryset/service layer.

------------------------------------------------------------------------

# 20. Search Query Rules

For searchable lists:

-   Filter in PostgreSQL.
-   Paginate results.
-   Use indexes appropriate to the search pattern.
-   Do not load all records into Python for searching.
-   Use PostgreSQL/trigram search only when justified.
-   Do not add indexes blindly.

For frequently queried business identifiers, enforce appropriate
`UNIQUE` constraints/indexes.

------------------------------------------------------------------------

# 21. Index Rules

Add indexes based on real query patterns.

Consider indexes for fields commonly used in:

-   Foreign-key filtering
-   Search
-   Ordering
-   Unique business identifiers
-   Status + scope combinations
-   Date-range filtering

Do not create an index for every column.

Every index has costs:

-   Storage
-   Write overhead
-   Migration cost
-   Maintenance

Before adding an index, identify the query it improves.

For slow/important queries, use:

``` sql
EXPLAIN ANALYZE
```

to investigate actual database behavior.

------------------------------------------------------------------------

# 22. Pagination

Any potentially large API collection must use pagination.

Especially:

-   Students
-   Faculty
-   Results
-   Attendance
-   Fees
-   Payments
-   Documents
-   Imports
-   Audit logs
-   Reports

Do not return an unbounded list simply because it works with test data.

------------------------------------------------------------------------

# 23. Transactions & Concurrency

Use `transaction.atomic()` for operations that must succeed or fail as
one unit.

Examples:

-   Payment recording
-   Result publication
-   Critical state transitions
-   Multi-table student import operations
-   Financial corrections

Use `select_for_update()` only where row-level locking is genuinely
required.

Do not add locking everywhere.

Think about:

> What happens if two requests execute this operation at exactly the
> same time?

Critical financial and academic operations must be designed against race
conditions and duplicate requests.

------------------------------------------------------------------------

# 24. Performance Validation

For important endpoints:

-   Measure query count.
-   Check response size.
-   Check database execution time.
-   Test with realistic dataset sizes.
-   Inspect slow queries.
-   Verify pagination.
-   Verify indexes.

Do not declare a feature performant merely because it works with 20 test
records.

------------------------------------------------------------------------

# 25. Security Rules

Follow `SECURITY.md`.

At minimum:

-   Backend authorization is mandatory.
-   Frontend authorization is not sufficient.
-   Enforce object-level and scope-level permissions.
-   Never expose sensitive data by default.
-   Never log secrets.
-   Never hardcode credentials.
-   Validate all external input.
-   Protect file uploads.
-   Protect financial operations.
-   Protect result publication.
-   Audit sensitive operations.
-   Never create authentication bypasses.

If a feature conflicts with a security rule, do not weaken the security
rule without explicit approval.

------------------------------------------------------------------------

# 26. API Rules

Before creating an endpoint:

1.  Check whether an existing endpoint already serves the purpose.
2.  Define who can access it.
3.  Define its scope.
4.  Define input validation.
5.  Define response shape.
6.  Define pagination if needed.
7.  Consider rate limiting.
8.  Consider idempotency.
9.  Check whether audit logging is required.

Do not create endpoints that expose unrestricted query capabilities.

------------------------------------------------------------------------

# 27. Frontend Rules

Follow existing React patterns.

Before creating a component:

-   Search for reusable components.
-   Check `DESIGN/`.
-   Follow existing spacing/layout/typography.
-   Follow existing state/loading/error patterns.
-   Avoid duplicate components.

Do not put business authorization logic only in React.

The backend remains authoritative.

------------------------------------------------------------------------

# 28. UI State Requirements

For meaningful pages/features, consider:

-   Loading state
-   Empty state
-   Error state
-   Success state
-   Disabled state
-   Permission-denied state
-   Validation errors
-   Pagination state

Do not design only the successful/default state.

------------------------------------------------------------------------

# 29. File Creation Rules

Before creating a new file:

1.  Check `FILE_MAP.md`.
2.  Search for an existing equivalent.
3.  Determine the correct module/domain.
4.  Follow existing folder structure.
5.  Create the file only if necessary.
6.  Add/update tests where appropriate.
7.  Update `FILE_MAP.md`.

Do not create random folders or files at the project root.

------------------------------------------------------------------------

# 30. Migration Rules

Any database schema change must use Django migrations.

Never:

-   Manually modify production tables as a shortcut.
-   Delete columns containing historical data without an approved
    migration strategy.
-   Change a field type blindly.
-   Remove constraints without understanding dependent code.

After schema changes:

-   Review the migration.
-   Test migration forward.
-   Test relevant application behavior.
-   Consider existing production data.

------------------------------------------------------------------------

# 31. Testing Cycle

After implementation:

### Backend

Test:

-   Model behavior
-   Services/business rules
-   API endpoints
-   Permissions
-   Scope restrictions
-   Validation
-   Transactions
-   Important query behavior

### Frontend

Test:

-   Component behavior
-   User flows
-   Protected routes
-   API states
-   Form validation
-   Error/loading/empty states

### Security

Check:

-   Unauthorized access
-   Cross-user access
-   Cross-department access
-   Sensitive data exposure
-   IDOR/BOLA
-   Authentication edge cases

### Performance

Check:

-   Query count
-   N+1 queries
-   Pagination
-   Large dataset behavior
-   Expensive serializer operations

------------------------------------------------------------------------

# 32. Update `FILE_MAP.md`

After creating, deleting, moving, or substantially changing files:

Update `FILE_MAP.md`.

The map should remain useful for future AI agents.

For a new feature, document:

-   File path
-   Purpose
-   Domain/module
-   Important dependencies
-   API/component role where relevant

Do not allow `FILE_MAP.md` to become stale.

------------------------------------------------------------------------

# 33. Update `TASKS.md`

After completing work:

-   Mark completed work appropriately.
-   Record remaining work.
-   Do not mark a feature complete if required tests or security checks
    are missing.
-   Keep task descriptions aligned with the actual implementation.

------------------------------------------------------------------------

# 34. No Silent Architecture Changes

The agent must NOT silently:

-   Move a domain to another module.
-   Create a new architectural pattern.
-   Change database ownership.
-   Introduce a new authentication system.
-   Replace existing infrastructure.
-   Add major dependencies.
-   Change API contracts.
-   Change security boundaries.

If such a change is necessary:

1.  Explain the reason.
2.  Identify affected files/domains.
3.  Identify risks.
4.  Ask for approval when the change is material.

------------------------------------------------------------------------

# 35. Do Not Hide Problems

Never make a feature appear complete by:

-   Disabling validation
-   Returning fake data
-   Hardcoding values
-   Adding default credentials
-   Suppressing errors
-   Ignoring failing tests
-   Bypassing authorization
-   Swallowing exceptions
-   Creating temporary backdoors

If something cannot be implemented correctly, report the blocker.

------------------------------------------------------------------------

# 36. Code Quality Rules

Prefer:

-   Small focused functions
-   Clear names
-   Explicit business logic
-   Reusable components
-   Thin API views
-   Domain/business logic in appropriate services
-   Database operations that are easy to reason about
-   Tests for important behavior

Avoid:

-   Giant functions
-   God classes
-   Duplicate logic
-   Hidden side effects
-   Unnecessary abstraction
-   Deeply nested conditionals
-   Business logic scattered across serializers, views, and components
    without a clear reason

------------------------------------------------------------------------

# 37. Final Feature Verification

Before declaring a feature complete, verify:

### Requirements

-   [ ] The requested behavior is implemented.
-   [ ] Existing behavior was not unintentionally broken.

### Architecture

-   [ ] Correct domain/module ownership.
-   [ ] No duplicate source of truth.
-   [ ] No unnecessary architecture changes.

### Database

-   [ ] Relationships are correct.
-   [ ] Constraints are correct.
-   [ ] Historical data is protected.
-   [ ] Migration exists where required.

### Security

-   [ ] Authentication checked.
-   [ ] Authorization checked.
-   [ ] Scope checked.
-   [ ] Sensitive data protected.
-   [ ] Audit requirements satisfied.

### Performance

-   [ ] No obvious N+1 queries.
-   [ ] `select_related()` / `prefetch_related()` used where
    appropriate.
-   [ ] Large collections paginated.
-   [ ] Filtering/aggregation performed in the database.
-   [ ] No unnecessary full-table loads.
-   [ ] Important queries considered for indexing.
-   [ ] Query count/performance checked where relevant.

### UI

-   [ ] Relevant `DESIGN/` references inspected.
-   [ ] Existing design language followed.
-   [ ] Loading/empty/error states handled.
-   [ ] Responsive behavior considered.

### Documentation

-   [ ] `FILE_MAP.md` updated.
-   [ ] `TASKS.md` updated if applicable.
-   [ ] Relevant project documentation updated.

------------------------------------------------------------------------

# 38. Required Final Response From the Agent

When reporting completed work, provide a concise summary containing:

1.  What was changed.
2.  Important files changed.
3.  Database/API changes.
4.  Security considerations.
5.  Performance/query considerations.
6.  Tests performed.
7.  Remaining issues or limitations.

Do not claim something was tested if it was not actually tested.

------------------------------------------------------------------------

# 39. Golden Rule

> **Understand → Locate → Read Rules → Inspect Design → Design → Check
> for Reuse/Conflicts → Implement → Test → Security Review → Performance
> Review → Update FILE_MAP/TASKS → Verify.**

The agent is expected to preserve the system's architecture and design
while continuously improving the implementation.

**Never optimize for "code written quickly." Optimize for "correct,
secure, maintainable, efficient software."**
