"""
Seed initial roles, permissions, and default admin user for GCOEK MIS.

Usage:
    python manage.py seed_auth_roles
    python manage.py seed_auth_roles --create-admin
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.authentication.models import (
    Permission,
    Role,
    RoleAssignment,
    RolePermission,
    User,
)


class Command(BaseCommand):
    help = 'Seeds initial roles, permissions, and role-permission mappings.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--create-admin',
            action='store_true',
            help='Create default system administrator account if none exists.',
        )

    @transaction.atomic
    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE('Seeding roles and permissions...'))

        # 1. Define Permissions
        permissions_data = [
            # Student Module
            ('student.view', 'View student profile and records', 'student'),
            ('student.create', 'Create/onboard student records', 'student'),
            ('student.edit', 'Update student details', 'student'),
            ('student.sensitive_reveal', 'Reveal masked sensitive student data', 'student'),
            ('student.export', 'Export student lists', 'student'),
            # Faculty Module
            ('faculty.view', 'View faculty profile and biodata', 'faculty'),
            ('faculty.create', 'Create faculty profile', 'faculty'),
            ('faculty.edit', 'Update faculty profile', 'faculty'),
            ('faculty.sensitive_reveal', 'Reveal masked faculty bank data', 'faculty'),
            # Academic Structure Module
            ('academic.view', 'View departments, programs, divisions, and years', 'academic'),
            ('academic.manage', 'Manage departments, programs, divisions, and years', 'academic'),
            # Curriculum Module
            ('curriculum.view', 'View schemes, subjects, and teaching assignments', 'curriculum'),
            ('curriculum.manage', 'Manage schemes and subject configurations', 'curriculum'),
            # Admissions Module
            ('admissions.import', 'Upload and process government candidate lists', 'admissions'),
            ('admissions.view', 'View admission import batches and rows', 'admissions'),
            # Results & Eligibility Module
            ('results.view', 'View semester results, marks, and backlogs', 'results'),
            ('results.upload', 'Upload semester results with validation', 'results'),
            ('results.verify', 'Verify student exam eligibility', 'results'),
            # Finance Module
            ('finance.fee_view', 'View fee configurations and student ledgers', 'finance'),
            ('finance.fee_manage', 'Configure fee heads and amounts', 'finance'),
            ('finance.payment_record', 'Record candidate fee payments at desk', 'finance'),
            # Audit Module
            ('audit.view', 'View security audit log trail', 'audit'),
            # System Administration
            ('sysadmin.all', 'Full system administration capability', 'sysadmin'),
        ]

        permission_objs = {}
        for codename, name, module in permissions_data:
            perm, created = Permission.objects.get_or_create(
                codename=codename,
                defaults={'name': name, 'module': module},
            )
            permission_objs[codename] = perm

        self.stdout.write(self.style.SUCCESS(f'Verified {len(permission_objs)} permissions.'))

        # 2. Define Roles
        roles_data = [
            (
                'SYSADMIN',
                'System Administrator',
                'System-wide technical configuration, maintenance, and audit access.',
            ),
            (
                'ADMIN_HEAD',
                'Administrative Head',
                'College-wide administrative operations: student admissions import, verification oversight, fee structure configuration.',
            ),
            (
                'HOD',
                'Head of Department',
                'Department-scoped oversight of classes, divisions, faculty teaching assignments, and department eligibility verification.',
            ),
            (
                'CLASS_TEACHER',
                'Class Teacher',
                'Division-scoped class management, student monitoring, and primary exam eligibility verification.',
            ),
            (
                'FACULTY',
                'Faculty Member',
                'Teaching staff with access to own profile, assigned courses, student directory, and academic schemes.',
            ),
            (
                'ACCOUNTANT',
                'Accountant',
                'Financial operations: candidate fee desk, fee collection, receipt recording, and payment ledgers.',
            ),
            (
                'STUDENT',
                'Student',
                'Enrolled student with access to own academic records, results, profile, and fee statements.',
            ),
        ]

        role_objs = {}
        for codename, name, desc in roles_data:
            role, created = Role.objects.get_or_create(
                codename=codename,
                defaults={'name': name, 'description': desc},
            )
            role_objs[codename] = role

        self.stdout.write(self.style.SUCCESS(f'Verified {len(role_objs)} roles.'))

        # 3. Define Role-Permission Mappings
        role_permission_mappings = {
            'SYSADMIN': list(permission_objs.keys()),  # All permissions
            'ADMIN_HEAD': [
                'student.view',
                'student.create',
                'student.edit',
                'student.sensitive_reveal',
                'student.export',
                'faculty.view',
                'academic.view',
                'curriculum.view',
                'admissions.import',
                'admissions.view',
                'results.view',
                'finance.fee_view',
                'finance.fee_manage',
                'audit.view',
            ],
            'HOD': [
                'student.view',
                'faculty.view',
                'academic.view',
                'curriculum.view',
                'results.view',
                'results.verify',
            ],
            'CLASS_TEACHER': [
                'student.view',
                'academic.view',
                'curriculum.view',
                'results.view',
                'results.verify',
            ],
            'FACULTY': [
                'student.view',
                'faculty.view',
                'faculty.edit',
                'academic.view',
                'curriculum.view',
                'results.view',
            ],
            'ACCOUNTANT': [
                'student.view',
                'finance.fee_view',
                'finance.fee_manage',
                'finance.payment_record',
            ],
            'STUDENT': [
                'student.view',
                'results.view',
                'finance.fee_view',
                'academic.view',
                'curriculum.view',
            ],
        }

        mapping_count = 0
        for role_code, perm_codes in role_permission_mappings.items():
            role = role_objs[role_code]
            for perm_code in perm_codes:
                perm = permission_objs.get(perm_code)
                if perm:
                    _, created = RolePermission.objects.get_or_create(
                        role=role,
                        permission=perm,
                    )
                    if created:
                        mapping_count += 1

        self.stdout.write(
            self.style.SUCCESS(f'Role-permission mappings initialized ({mapping_count} created).')
        )

        # 4. Optional: Create default admin user
        if options.get('create_admin') or not User.objects.filter(is_superuser=True).exists():
            admin_user, created = User.objects.get_or_create(
                username='admin',
                defaults={
                    'email': 'admin@gcoek.ac.in',
                    'user_type': User.UserType.SYSADMIN,
                    'is_staff': True,
                    'is_superuser': True,
                    'must_change_password': False,
                },
            )
            if created:
                admin_user.set_password('Admin@Gceok2026!')
                admin_user.save()
                self.stdout.write(
                    self.style.SUCCESS('Created default sysadmin user: admin / Admin@Gceok2026!')
                )

            # Assign SYSADMIN role
            sysadmin_role = role_objs['SYSADMIN']
            RoleAssignment.objects.get_or_create(
                user=admin_user,
                role=sysadmin_role,
                defaults={'status': RoleAssignment.Status.ACTIVE},
            )
            self.stdout.write(self.style.SUCCESS('Assigned SYSADMIN role to admin user.'))

        self.stdout.write(self.style.SUCCESS('Role and permission seeding completed successfully.'))
