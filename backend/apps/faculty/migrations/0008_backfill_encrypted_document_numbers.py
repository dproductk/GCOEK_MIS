# Repeatable equivalent of the dev-database manual backfill: encrypt legacy
# plaintext FacultyDocument.document_number values into the encrypted/masked
# columns and clear the plaintext column. Production still holds the two
# legacy plaintext rows until this migration runs — it must run at deploy.
from django.db import migrations


def backfill_encrypted_numbers(apps, schema_editor):
    FacultyDocument = apps.get_model('faculty', 'FacultyDocument')
    try:
        from apps.common.encryption import encrypt_value, is_encryption_configured
    except Exception:
        return
    if not is_encryption_configured():
        # No FIELD_ENCRYPTION_KEY in this environment: leave rows untouched
        # rather than writing plaintext into the encrypted column.
        return

    def _mask(doc_type, number):
        if not number:
            return ''
        if doc_type == 'AADHAAR':
            return f'XXXX-XXXX-{number[-4:]}'
        if doc_type == 'PAN':
            return f'XXXXX{number[-4:]}'
        return ''

    qs = FacultyDocument.objects.exclude(document_number='').exclude(
        document_number__isnull=True
    )
    for doc in qs.iterator():
        legacy = str(doc.document_number or '').strip()
        if not legacy:
            continue
        if getattr(doc, 'document_number_encrypted', ''):
            # Encrypted value is the source of truth for all new writes;
            # the leftover plaintext is stale — drop it.
            doc.document_number = ''
        else:
            doc.document_number_encrypted = encrypt_value(legacy)
            doc.document_number_masked = _mask(doc.document_type, legacy)
            doc.document_number = ''
        doc.save(update_fields=[
            'document_number', 'document_number_encrypted',
            'document_number_masked', 'updated_at',
        ])


def noop_reverse(apps, schema_editor):
    # Irreversible by design: plaintext must never be restored.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('faculty', '0007_facultydocument_document_number_encrypted_and_more'),
    ]

    operations = [
        migrations.RunPython(backfill_encrypted_numbers, noop_reverse),
    ]
