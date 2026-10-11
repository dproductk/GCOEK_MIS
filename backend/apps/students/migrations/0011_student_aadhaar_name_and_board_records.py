# Student self-service: Aadhaar name + 10th/12th board records.

import uuid

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('students', '0010_student_scholarship'),
    ]

    operations = [
        migrations.AddField(
            model_name='studentaadhaardetail',
            name='name_as_per_aadhaar',
            field=models.CharField(blank=True, default='', help_text='Name printed on the Aadhaar card (editable by student, re-verified by staff).', max_length=255),
        ),
        migrations.CreateModel(
            name='StudentBoardRecord',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, help_text='Internal UUID primary key.', primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True, help_text='Record creation timestamp.')),
                ('updated_at', models.DateTimeField(auto_now=True, help_text='Last modification timestamp.')),
                ('level', models.CharField(choices=[('SSC', 'SSC (Class 10th)'), ('HSC', 'HSC (Class 12th)'), ('DIPLOMA', 'Polytechnic Diploma')], db_index=True, default='SSC', max_length=10)),
                ('stream', models.CharField(blank=True, default='', max_length=100)),
                ('board', models.CharField(blank=True, default='', max_length=150)),
                ('school_college', models.CharField(blank=True, default='', help_text='School name (SSC) or college/institute name (HSC/Diploma).', max_length=255)),
                ('passing_year', models.CharField(blank=True, default='', max_length=10)),
                ('seat_no', models.CharField(blank=True, default='', max_length=50)),
                ('marks_obtained', models.CharField(blank=True, default='', max_length=50)),
                ('percentage', models.CharField(blank=True, default='', max_length=20)),
                ('is_verified', models.BooleanField(default=False)),
                ('student', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='board_records', to='students.student')),
            ],
            options={
                'db_table': 'student_board_records',
                'ordering': ['student', 'level'],
                'unique_together': {('student', 'level')},
            },
        ),
    ]
