# Generated for scholarship self-service (profile Admission Details card).

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('students', '0009_studentpersonaldetail_abc_id_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='student',
            name='scholarship_applied',
            field=models.BooleanField(default=False, help_text='Whether the student has applied for a scholarship.'),
        ),
        migrations.AddField(
            model_name='student',
            name='scholarship_type',
            field=models.CharField(choices=[('NONE', 'None'), ('EBC', 'EBC (Economically Backward Class)'), ('OBC_FREESHIP', 'OBC Freeship'), ('SC', 'SC Scholarship'), ('ST', 'ST Scholarship'), ('NT_C', 'NT-C'), ('MINORITY', 'Minority Scholarship')], default='NONE', help_text='Scholarship scheme applied for (NONE when not applied).', max_length=20),
        ),
    ]
