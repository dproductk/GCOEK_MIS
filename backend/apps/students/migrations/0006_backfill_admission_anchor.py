"""Backfill Student.admission_year/type/repeat_count for pre-existing rows."""
from django.db import migrations


def backfill(apps, schema_editor):
    Student = apps.get_model('students', 'Student')
    StudentAdmission = apps.get_model('admissions', 'StudentAdmission')
    for student in Student.objects.filter(admission_year__isnull=True).only(
            'id', 'is_direct_second_year'):
        adm = (StudentAdmission.objects.filter(student_id=student.id)
               .order_by('academic_year__start_date', 'created_at').first())
        if adm is None:
            continue
        is_dse = (adm.admission_type == 'DIRECT_SECOND_YEAR'
                  or student.is_direct_second_year)
        Student.objects.filter(id=student.id).update(
            admission_year_id=adm.academic_year_id,
            admission_type='DSE' if is_dse else 'FY',
        )


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('students', '0005_studentenrollment_placement_confirmed'),
    ]

    operations = [
        migrations.RunPython(backfill, noop),
    ]
