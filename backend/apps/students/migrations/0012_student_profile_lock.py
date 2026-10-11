# One-time student self-service profile lock.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('students', '0011_student_aadhaar_name_and_board_records'),
    ]

    operations = [
        migrations.AddField(
            model_name='student',
            name='profile_locked',
            field=models.BooleanField(db_index=True, default=False, help_text='One-time self-service lock. When True the student can no longer edit their profile or upload own documents.'),
        ),
        migrations.AddField(
            model_name='student',
            name='profile_locked_at',
            field=models.DateTimeField(blank=True, help_text='When the student locked their profile.', null=True),
        ),
    ]
