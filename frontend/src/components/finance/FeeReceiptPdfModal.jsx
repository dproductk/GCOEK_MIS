import React, { useEffect, useState } from 'react';
import { AlertCircle, Download, ExternalLink, Printer } from 'lucide-react';
import Modal from '../common/Modal';
import { LoadingState } from '../common/StateDisplays';
import financeApi from '../../api/financeApi';

/**
 * Official fee receipt preview.
 *
 * The receipt itself is a server-rendered PDF (A4 landscape, three copies).
 * This dialog only previews the bytes and offers Download / Print; it does
 * not contain an HTML receipt template, so browser print settings cannot
 * change the layout of the official challan.
 */
export default function FeeReceiptPdfModal({
  isOpen,
  onClose,
  record,
  loadingRecord = false,
  studentName = '',
}) {
  const [pdf, setPdf] = useState(null);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!isOpen || loadingRecord || !record?.id) {
      return undefined;
    }

    let cancelled = false;
    let objectUrl = null;

    financeApi.getReceiptPdf(record.id)
      .then((response) => {
        if (cancelled) return;
        const blob = new Blob([response.data], { type: 'application/pdf' });
        objectUrl = URL.createObjectURL(blob);
        const safeNo = String(record.receipt_no || 'receipt').replace(/[^A-Za-z0-9._-]+/g, '-');
        setPdf((previous) => {
          if (previous?.url) URL.revokeObjectURL(previous.url);
          return { url: objectUrl, filename: `Fee_Receipt_${safeNo}.pdf` };
        });
      })
      .catch((err) => {
        if (cancelled) return;
        const detail = err?.response?.data?.detail;
        setError(
          typeof detail === 'string'
            ? detail
            : 'Could not prepare the official receipt PDF. Please try again.',
        );
      });

    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [isOpen, loadingRecord, record?.id, record?.receipt_no]);

  const title = `Official Fee Receipt${studentName ? `: ${studentName}` : ''}`;
  const loading = Boolean(isOpen && record?.id && !pdf && !error);

  return (
    <Modal isOpen={isOpen} onClose={onClose} title={title} maxWidth="1120px">
      <div style={{ minHeight: 260 }}>
        {loadingRecord || loading ? (
          <LoadingState message="Preparing official receipt..." />
        ) : !record ? (
          <div style={{ padding: '2.5rem 1rem', textAlign: 'center', color: '#64748b' }}>
            <Printer size={36} style={{ margin: '0 auto 0.75rem auto', color: '#94a3b8' }} />
            <div style={{ fontSize: '1rem', fontWeight: 600, color: '#334155' }}>
              No Paid Receipt Found
            </div>
            <div style={{ fontSize: '0.85rem', marginTop: '0.25rem' }}>
              This candidate has no marked (paid) fee receipt yet.
            </div>
          </div>
        ) : error ? (
          <div style={{ padding: '2rem 1rem', textAlign: 'center', color: '#b91c1c' }}>
            <AlertCircle size={34} style={{ margin: '0 auto 0.65rem auto' }} />
            <div style={{ fontWeight: 600 }}>{error}</div>
            <div style={{ color: '#64748b', fontSize: '0.82rem', marginTop: '0.35rem' }}>
              The receipt is generated only after the fee is marked PAID at the accounts desk.
            </div>
          </div>
        ) : pdf ? (
          <div>
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                gap: '0.75rem',
                flexWrap: 'wrap',
                marginBottom: '0.85rem',
              }}
            >
              <div>
                <div style={{ fontSize: '0.82rem', color: '#64748b' }}>
                  Receipt No. <b style={{ color: '#0f172a' }}>{record.receipt_no}</b>
                </div>
                <div style={{ fontSize: '0.72rem', color: '#94a3b8', marginTop: '0.15rem' }}>
                  A4 landscape · three copies · print at 100% (no browser scaling)
                </div>
              </div>
              <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
                <a
                  href={pdf.url}
                  download={pdf.filename}
                  className="edvana-btn edvana-btn-secondary"
                  style={{ display: 'inline-flex', alignItems: 'center', gap: '0.4rem', textDecoration: 'none' }}
                >
                  <Download size={15} /> Download PDF
                </a>
                <a
                  href={pdf.url}
                  target="_blank"
                  rel="noreferrer"
                  className="edvana-btn edvana-btn-primary"
                  style={{ display: 'inline-flex', alignItems: 'center', gap: '0.4rem', textDecoration: 'none' }}
                >
                  <Printer size={15} /> Print / Save
                </a>
                <a
                  href={pdf.url}
                  target="_blank"
                  rel="noreferrer"
                  className="edvana-btn edvana-btn-secondary"
                  style={{ display: 'inline-flex', alignItems: 'center', gap: '0.4rem', textDecoration: 'none' }}
                  title="Open the PDF in a new tab"
                >
                  <ExternalLink size={15} /> Open
                </a>
              </div>
            </div>

            <iframe
              src={pdf.url}
              title="Official fee receipt PDF preview"
              style={{
                width: '100%',
                height: 'min(68vh, 760px)',
                minHeight: 430,
                border: '1px solid #e2e8f0',
                borderRadius: 10,
                background: '#f8fafc',
              }}
            />
          </div>
        ) : null}
      </div>
    </Modal>
  );
}
