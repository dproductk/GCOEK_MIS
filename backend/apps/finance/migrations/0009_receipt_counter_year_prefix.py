"""Receipt counters become per (academic year, roman year-level prefix).

Supports the new receipt number format <ROMAN>-<year.code>-<nnnn>
(e.g. IV-2026-27-0001): each year level keeps its own sequence per year.
The legacy GCOEK/<year>/FEE/<nnnn> counters remain as rows with an empty
prefix so old data still satisfies uniqueness constraints.
"""
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('academic_structure', '0008_seed_university_program_codes'),
        ('finance', '0008_ledger_fee_snapshot'),
    ]

    operations = [
        migrations.AddField(
            model_name='feereceiptcounter',
            name='prefix',
            field=models.CharField(default='', max_length=8),
        ),
        migrations.AlterField(
            model_name='feereceiptcounter',
            name='academic_year',
            field=models.ForeignKey(
                db_index=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='receipt_counters',
                to='academic_structure.academicyear',
            ),
        ),
        migrations.AddConstraint(
            model_name='feereceiptcounter',
            constraint=models.UniqueConstraint(
                fields=('academic_year', 'prefix'),
                name='uniq_receipt_counter_year_prefix',
            ),
        ),
    ]
