# Replace the short scholarship type catalog with the detailed Maharashtra
# scholarship scheme list (long display names, new short codes). Existing rows
# written with the old codes are remapped to the closest new scheme.

from django.db import migrations, models


# old code -> new code
LEGACY_MAP = {
    'EBC': 'DTE_EBC_RCS',          # EBC -> Rajarshi Shahu Maharaj Yojna (EBC)
    'OBC_FREESHIP': 'OBC_TF_EF',   # OBC freeship -> tuition/exam fee (OBC)
    'SC': 'SC_GOI_PMS',            # SC Scholarship -> GoI Post-Matric (SC)
    'ST': 'ST_GOI_PMS',            # ST Scholarship -> GoI Post-Matric (ST)
    'NT_C': 'VJNT_TF_EF',          # NT-C -> tuition/exam fee (VJNT)
    'MINORITY': 'DTE_MINORITY',    # Minority -> DTE minority scheme
}


def remap_legacy_codes(apps, schema_editor):
    Student = apps.get_model('students', 'Student')
    for old, new in LEGACY_MAP.items():
        Student.objects.filter(scholarship_type=old).update(scholarship_type=new)


def restore_legacy_codes(apps, schema_editor):
    Student = apps.get_model('students', 'Student')
    reverse = {new: old for old, new in LEGACY_MAP.items()}
    for new, old in reverse.items():
        Student.objects.filter(scholarship_type=new).update(scholarship_type=old)


class Migration(migrations.Migration):

    dependencies = [
        ('students', '0012_student_profile_lock'),
    ]

    operations = [
        migrations.RunPython(remap_legacy_codes, restore_legacy_codes),
        migrations.AlterField(
            model_name='student',
            name='scholarship_type',
            field=models.CharField(
                choices=[
                    ('NONE', 'None'),
                    ('DTE_MINORITY', 'Directorate of Technical Education - Scholarship for students of minority communities pursuing Higher and Professional courses (DTE)'),
                    ('DTE_EBC_RCS', 'Directorate of Technical Education - Rajarshi Chhatrapati Shahu Maharaj Shikshan Shulk Shishyavrutti Yojna (EBC)'),
                    ('OBC_VJNT_SBC_MAINT', 'OBC, SEBC, VJNT & SBC Welfare Department - Payment of Maintenance Allowance to VJNT and SBC Students Studying in Professional Courses and Living in Hostel Attached to Professional Colleges'),
                    ('OBC_GIRLS_TF_EF', 'OBC, SEBC, VJNT & SBC Welfare Department - Payment of Tuition Fees and Examination Fees to OBC Girls Pursuing Professional Courses'),
                    ('OBC_PMS', 'OBC, SEBC, VJNT & SBC Welfare Department - Post Matric Scholarship to OBC Students'),
                    ('SBC_PMS', 'OBC, SEBC, VJNT & SBC Welfare Department - Post Matric Scholarship to SBC Students'),
                    ('OBC_GIRLS_PMS', 'OBC, SEBC, VJNT & SBC Welfare Department - Post Matric Scholarship to the Girls Belonging to Other Backward Classes taking admission in Professional Courses'),
                    ('VJNT_PMS', 'OBC, SEBC, VJNT & SBC Welfare Department - Post Matric Scholarship to VJNT Students'),
                    ('OBC_TF_EF', 'OBC, SEBC, VJNT & SBC Welfare Department - Tuition Fees and Examination Fees to OBC Students'),
                    ('SBC_TF_EF', 'OBC, SEBC, VJNT & SBC Welfare Department - Tuition Fees and Examination Fees to SBC Students'),
                    ('VJNT_TF_EF', 'OBC, SEBC, VJNT & SBC Welfare Department - Tuition Fees and Examination Fees to VJNT Students'),
                    ('PWD_PMS', 'Persons with Disabilities Welfare Department - Post-Matric Scholarship for persons with disability'),
                    ('SC_GOI_PMS', 'Social Justice and Special Assistance Department (SC) - Government of India Post-Matric Scholarship'),
                    ('SC_MAINT', 'Social Justice and Special Assistance Department (SC) - Maintenance Allowance for student Studying in professional courses'),
                    ('SC_FREESHIP', 'Social Justice and Special Assistance Department (SC) - Post-Matric Tuition Fee and Examination Fee (Freeship)'),
                    ('ST_GOI_PMS', 'Tribal Development Department (ST) - Post Matric Scholarship Scheme (Government Of India)'),
                    ('ST_FREESHIP', 'Tribal Development Department (ST) - Tuition Fee & Exam Fee for Tribal Students (Freeship)'),
                    ('NSP_TOPCLASS_PWD', 'NSP - Scholarship for Top Class Education for students with Disabilities'),
                    ('NSP_PRAGATI', 'NSP - Pragati Scholarship Scheme (Diploma/Degree)'),
                    ('NSP_SAKSHAM', 'NSP - Saksham Scholarship Scheme (Diploma/Degree)'),
                    ('NSP_SWANATH', 'NSP - Swanath Scholarship Scheme Diploma /Degree)'),
                ],
                default='NONE',
                help_text='Scholarship scheme applied for (NONE when not applied).',
                max_length=32,
            ),
        ),
    ]
