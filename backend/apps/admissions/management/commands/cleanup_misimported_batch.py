"""
Remove student records created by mis-imported admission batches.

A senior-student roster uploaded through the admissions pipeline creates
ghost fresher records (new Student + enrollment + login + role assignment).
This command reverses exactly that onboarding, with a full audit trail.

Safety:
- Dry-run by default; pass --execute to delete.
- Only students whose EVERY admission comes from the listed batches qualify.
- A student is SKIPPED (never deleted) when any of these hold:
  payments / online attempts / semester results / eligibility records /
  fee assessments / admissions from other batches / login ever used /
  user owns uploads, collections, or a faculty profile.
- ImportBatch + ImportRow records are KEPT as immutable evidence
  (ImportRow.student is SET_NULL on delete); a cleanup note is appended
  to each batch's summary_report (additive, never destructive).
- Every removal writes audit entries (ROLE_REVOKE + DELETE) attributed
  to --actor, who must hold system-wide (sysadmin) scope.

Usage:
    python manage.py cleanup_misimported_batch --batch CSE_Semester7_26-27.xls --actor sysadmin
    python manage.py cleanup_misimported_batch --batch <file-or-uuid> --actor sysadmin --execute
"""
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.admissions.models import ImportBatch
from apps.audit.models import AuditLog
from apps.audit.services import audit_log
from apps.authentication.models import User
from apps.authentication.permissions import get_user_scopes
from apps.finance.models import OnlinePaymentAttempt, PaymentLedger, StudentFeeAssessment
from apps.results.models import EligibilityVerification, SemesterResult
from apps.students.models import Student


class Command(BaseCommand):
    help = 'Remove ghost student records created by mis-imported admission batches (dry-run by default).'

    def add_arguments(self, parser):
        parser.add_argument(
            '--batch',
            action='append',
            required=True,
            help='Mis-imported batch file name or UUID. Repeatable.',
        )
        parser.add_argument(
            '--actor',
            required=True,
            help='Username attributed in the audit trail. Must be sysadmin.',
        )
        parser.add_argument(
            '--execute',
            action='store_true',
            help='Perform the deletion. Without it, only a dry-run report is printed.',
        )

    def handle(self, *args, **options):
        actor = User.objects.filter(username=options['actor']).first()
        if actor is None:
            raise CommandError(f"Actor user '{options['actor']}' not found.")
        scopes = get_user_scopes(actor)
        if not (scopes.get('is_system_wide') or actor.is_superuser):
            raise CommandError(f"Actor '{actor.username}' is not sysadmin. Refusing destructive cleanup.")

        batches = []
        for ident in options['batch']:
            batch = (
                ImportBatch.objects.filter(id=ident).first()
                if len(str(ident)) == 36
                else ImportBatch.objects.filter(file_name=str(ident)).order_by('-created_at').first()
            )
            if batch is None:
                raise CommandError(f'Batch not found: {ident}')
            batches.append(batch)

        batch_ids = [b.id for b in batches]
        candidates = (
            Student.objects.filter(admissions__source_import_row__batch__in=batch_ids)
            .distinct()
            .select_related('user', 'admission_year')
            .prefetch_related('admissions__source_import_row__batch')
        )

        removable, skipped = [], []
        for student in candidates:
            reason = self._skip_reason(student, batch_ids)
            (skipped if reason else removable).append((student, reason))

        self.stdout.write(f'Batches: {[b.file_name for b in batches]}')
        self.stdout.write(f'Ghost candidates: {candidates.count()} | removable: {len(removable)} | skipped: {len(skipped)}')
        for student, reason in skipped:
            self.stdout.write(self.style.WARNING(f'  SKIP {student.enrollment_no} {student.display_name}: {reason}'))
        for student, _ in removable[:15]:
            self.stdout.write(f'  REMOVE {student.enrollment_no} {student.display_name}')
        if len(removable) > 15:
            self.stdout.write(f'  ... and {len(removable) - 15} more')

        if not options['execute']:
            self.stdout.write(self.style.NOTICE('Dry-run only. Re-run with --execute to delete.'))
            return

        if not removable:
            self.stdout.write(self.style.SUCCESS('Nothing to remove.'))
            return

        with transaction.atomic():
            for student, _ in removable:
                self._remove_student(student, batches, actor)
            stamp = timezone.now().isoformat()
            for batch in batches:
                report = dict(batch.summary_report or {})
                report['cleanup'] = {
                    'actor': actor.username,
                    'at': stamp,
                    'reason': 'Senior roster mis-imported as fresh admissions; ghost records reversed.',
                }
                batch.summary_report = report
                batch.save(update_fields=['summary_report', 'updated_at'])
                audit_log(
                    actor=actor,
                    action=AuditLog.Action.DELETE,
                    target_type='ImportBatch',
                    target_id=str(batch.id),
                    target_display=f"Cleanup of mis-import '{batch.file_name}'",
                    reason='Ghost onboarding reversal',
                    description=(
                        f"Removed ghost student records created by batch '{batch.file_name}'. "
                        'Batch and staging rows retained as evidence.'
                    ),
                )

        self.stdout.write(self.style.SUCCESS(f'Removed {len(removable)} ghost students ({len(skipped)} skipped).'))

    def _skip_reason(self, student, batch_ids):
        """Return a reason string when the student must NOT be deleted, else None."""
        if SemesterResult.objects.filter(student=student).exists():
            return 'has semester results'
        if EligibilityVerification.objects.filter(student=student).exists():
            return 'has eligibility records'
        if PaymentLedger.objects.filter(student=student).exists():
            return 'has payment records'
        if OnlinePaymentAttempt.objects.filter(student=student).exists():
            return 'has online payment attempts'
        if StudentFeeAssessment.objects.filter(student=student).exists():
            return 'has fee assessments'
        if student.admissions.exclude(source_import_row__batch__in=batch_ids).exists():
            return 'has admissions from other batches'
        user = student.user
        if user is not None:
            if user.last_login is not None:
                return 'login was used'
            if user.uploaded_admission_batches.exists():
                return 'user uploaded batches'
            if user.collected_payments.exists() or user.assessed_fees.exists():
                return 'user has financial actions'
            if hasattr(user, 'faculty_profile'):
                return 'user has faculty profile'
        return None

    def _remove_student(self, student, batches, actor):
        batch_names = sorted({
            adm.source_import_row.batch.file_name
            for adm in student.admissions.all()
            if adm.source_import_row is not None
        })
        snapshot = {
            'display_name': student.display_name,
            'enrollment_no': student.enrollment_no,
            'application_id': student.application_id,
            'admission_year': student.admission_year.code if student.admission_year_id else '',
            'source_batches': batch_names,
        }
        username = student.user.username if student.user else ''
        student_id = str(student.id)

        for assignment in student.user.role_assignments.all() if student.user else []:
            audit_log(
                actor=actor,
                action=AuditLog.Action.ROLE_REVOKE,
                target_type='RoleAssignment',
                target_id=str(assignment.id),
                target_display=f'{username} -> {assignment.role.name if assignment.role else "?"}',
                reason='Ghost onboarding reversal',
                description=f"Revoked onboarding role for ghost student '{student.display_name}'.",
            )

        audit_log(
            actor=actor,
            action=AuditLog.Action.DELETE,
            target_type='Student',
            target_id=student_id,
            target_display=f"{student.display_name} ({student.enrollment_no})",
            old_value=snapshot,
            reason='Ghost onboarding reversal',
            description=(
                f"Removed ghost student '{student.display_name}' created by mis-imported "
                f'batch(es): {", ".join(batch_names)}.'
            ),
        )
        student.delete()

        if username:
            user = User.objects.filter(username=username).first()
            if user is not None:
                audit_log(
                    actor=actor,
                    action=AuditLog.Action.DELETE,
                    target_type='User',
                    target_id=str(user.id),
                    target_display=username,
                    old_value={'username': username},
                    reason='Ghost onboarding reversal',
                    description=f"Removed ghost login '{username}'.",
                )
                user.delete()
