"""
Idempotent onboarding helper: link an existing login account to a Faculty
card (repeatable equivalent of the one-off ADMIN_HEAD01 dev-DB row).

Prod-safe by design:
- NEVER creates User accounts, passwords, or role assignments. The login
  account and its roles must already exist (created by the admin onboarding
  workflow). This command only creates the Faculty profile row.
- get_or_create semantics: running twice is a no-op success.
- Refuses to hijack: a mismatched employee_code on an existing card is an
  error, never an overwrite.

Example:
    python manage.py ensure_staff_faculty_card \\
        --username admin_head --employee-code ADMIN_HEAD01 \\
        --department-code CSE --date-of-joining 2020-06-01
"""
import datetime

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.academic_structure.models import Department
from apps.authentication.models import User
from apps.faculty.models import Faculty


class Command(BaseCommand):
    help = 'Idempotently create a Faculty card for an existing staff login.'

    def add_arguments(self, parser):
        parser.add_argument('--username', required=True)
        parser.add_argument('--employee-code', required=True)
        parser.add_argument('--department-code', required=True)
        parser.add_argument('--date-of-joining', required=True,
                            help='YYYY-MM-DD')
        parser.add_argument('--first-name', default='')
        parser.add_argument('--last-name', default='')
        parser.add_argument('--email', default='')

    @transaction.atomic
    def handle(self, *args, **options):
        try:
            user = User.objects.get(username=options['username'])
        except User.DoesNotExist:
            raise CommandError(
                f"User '{options['username']}' does not exist. "
                'Create the login account first; this command never creates users.'
            )
        try:
            dept = Department.objects.get(code__iexact=options['department_code'].strip())
        except Department.DoesNotExist:
            raise CommandError(
                f"Department '{options['department_code']}' not found."
            )
        try:
            doj = datetime.date.fromisoformat(options['date_of_joining'])
        except ValueError:
            raise CommandError('--date-of-joining must be YYYY-MM-DD.')

        existing = Faculty.objects.filter(user_id=user.id).first()
        if existing is not None:
            if existing.employee_code != options['employee_code']:
                raise CommandError(
                    f'Faculty card already exists for {user.username} with '
                    f"employee_code '{existing.employee_code}'; refusing to overwrite."
                )
            self.stdout.write(self.style.SUCCESS(
                f'Faculty card already present: {existing} (no change).'
            ))
            return

        if Faculty.objects.filter(employee_code=options['employee_code']).exists():
            raise CommandError(
                f"employee_code '{options['employee_code']}' is already used by another card."
            )
        email = (options['email'] or getattr(user, 'email', '') or '').strip()
        if not email:
            raise CommandError('An email is required (--email or the user account email).')
        faculty = Faculty.objects.create(
            user=user,
            employee_code=options['employee_code'].strip(),
            first_name=(options['first_name'] or (user.first_name or 'Staff')).strip(),
            last_name=(options['last_name'] or (user.last_name or 'Member')).strip(),
            department=dept,
            date_of_joining=doj,
            official_email=email,
        )
        self.stdout.write(self.style.SUCCESS(f'Faculty card created: {faculty}.'))
