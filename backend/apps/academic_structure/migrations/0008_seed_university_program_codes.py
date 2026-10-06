"""Seed university-issued program codes on B.Tech programs (data, not logic)."""
from django.db import migrations


UNIVERSITY_CODES = {
    'CSE': '11242',
    'AI_DS': '11263',
    'EE': '11293',
    'ETC': '11372',
    'MAE': '11615',
}


def seed_codes(apps, schema_editor):
    Program = apps.get_model('academic_structure', 'Program')
    Department = apps.get_model('academic_structure', 'Department')
    for dept_code, uni_code in UNIVERSITY_CODES.items():
        try:
            dept = Department.objects.filter(code=dept_code).first()
            if dept is None:
                continue
            Program.objects.filter(
                department=dept, code=f'BTECH_{dept_code}'
            ).exclude(
                university_program_code=uni_code
            ).update(university_program_code=uni_code)
        except Exception:
            continue


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('academic_structure', '0007_program_university_program_code'),
    ]

    operations = [
        migrations.RunPython(seed_codes, noop),
    ]
