"""Fix department choice codes to DTE-issued FY + DSE/TFWS alternates."""
from django.db import migrations


CORRECT_CODES = {
    'CSE': ('603624210', ['0603624211T']),
    'AI_DS': ('603626310', ['0603626311T']),
    'EE': ('603629310', ['0603629311T']),
    'ETC': ('603637210', ['0603637211T']),
    'MAE': ('603661510', ['0603661511T']),
}


def fix_codes(apps, schema_editor):
    Department = apps.get_model('academic_structure', 'Department')
    for code, (primary, alternates) in CORRECT_CODES.items():
        Department.objects.filter(code=code).update(
            choice_code=primary, alternate_choice_codes=alternates
        )


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('academic_structure', '0005_department_alternate_choice_codes'),
    ]

    operations = [
        migrations.RunPython(fix_codes, noop),
    ]
