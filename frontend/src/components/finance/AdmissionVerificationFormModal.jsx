import React, { useRef } from 'react';
import { Download, Printer, CheckCircle2, ShieldCheck, X, FileCheck, Building } from 'lucide-react';
import Modal from '../common/Modal';

export default function AdmissionVerificationFormModal({
  isOpen,
  onClose,
  formData,
  onDownloadPdf,
  downloading,
}) {
  const printAreaRef = useRef(null);

  if (!formData) return null;

  const handlePrint = () => {
    window.print();
  };

  const ct = formData.class_teacher_verification || {};
  const hod = formData.hod_verification || {};
  const office = formData.office_use || {};

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title="Admission Verification & Application Form"
      maxWidth="860px"
    >
      <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
        {/* Top toolbar */}
        <div style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          flexWrap: 'wrap',
          gap: '0.75rem',
          padding: '0.85rem 1.25rem',
          background: '#f8fafc',
          border: '1px solid #e2e8f0',
          borderRadius: 14,
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.65rem' }}>
            <div style={{
              width: 36, height: 36, borderRadius: '50%',
              background: '#e6f7ec', color: '#16a34a',
              display: 'flex', alignItems: 'center', justifyContent: 'center'
            }}>
              <FileCheck size={20} />
            </div>
            <div>
              <div style={{ fontSize: '0.88rem', fontWeight: 700, color: '#0f172a' }}>
                Accountant Copy — Verified for Admission
              </div>
              <div style={{ fontSize: '0.75rem', color: '#64748b' }}>
                Signed and endorsed with timestamps by Class Teacher and HOD
              </div>
            </div>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
            <button
              type="button"
              onClick={handlePrint}
              className="edvana-btn edvana-btn-secondary"
              style={{ display: 'inline-flex', alignItems: 'center', gap: '0.45rem', fontSize: '0.84rem' }}
            >
              <Printer size={15} /> Print Form
            </button>
            <button
              type="button"
              onClick={onDownloadPdf}
              disabled={downloading}
              className="edvana-btn edvana-btn-primary"
              style={{
                display: 'inline-flex', alignItems: 'center', gap: '0.45rem',
                fontSize: '0.84rem', background: '#1E60DC', border: '1px solid #1E60DC'
              }}
            >
              <Download size={15} /> {downloading ? 'Generating PDF...' : 'Download PDF'}
            </button>
          </div>
        </div>

        {/* Printable Paper Form Preview */}
        <div
          ref={printAreaRef}
          className="admission-form-printable"
          style={{
            background: '#ffffff',
            border: '2px solid #0f172a',
            borderRadius: 8,
            padding: '1.75rem 2rem',
            color: '#090d16',
            fontFamily: "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
            fontSize: '0.85rem',
            lineHeight: 1.5,
          }}
        >
          {/* Header block with Photo container */}
          <div style={{
            display: 'grid',
            gridTemplateColumns: '1fr 105px',
            gap: '1.25rem',
            borderBottom: '2px solid #0f172a',
            paddingBottom: '1rem',
            marginBottom: '1rem',
          }}>
            <div style={{ textAlign: 'center', display: 'flex', flexDirection: 'column', justifyContent: 'center' }}>
              <div style={{
                fontSize: '1.22rem',
                fontWeight: 900,
                color: '#0f172a',
                letterSpacing: '0.02em',
                textTransform: 'uppercase'
              }}>
                Government College Of Engineering, Kolhapur
              </div>
              <div style={{
                fontSize: '0.98rem',
                fontWeight: 700,
                color: '#1e293b',
                marginTop: '0.2rem'
              }}>
                {formData.form_title || '—'}
              </div>
              <div style={{
                fontSize: '0.9rem',
                fontWeight: 800,
                color: '#0f172a',
                marginTop: '0.4rem',
                textAlign: 'left'
              }}>
                Academic Year {formData.academic_year_code}
              </div>
            </div>

            {/* Passport Photo Box */}
            <div style={{
              width: 100,
              height: 115,
              border: '1.5px solid #475569',
              background: '#f8fafc',
              borderRadius: 4,
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              justifyContent: 'center',
              textAlign: 'center',
              padding: '0.35rem',
              color: '#64748b',
              fontSize: '0.68rem',
              lineHeight: 1.25,
            }}>
              <span style={{ fontWeight: 600 }}>Affix Passport</span>
              <span>Size Photograph</span>
              <span>Here</span>
            </div>
          </div>

          {/* 18 Numbered Form Items - Prefilled identity items and blank underlines for manual handwriting */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.65rem', marginBottom: '1.25rem' }}>
            <FieldPrefilledRow number="1" label="Full Name of Student:" value={formData.full_name} />
            <FieldPrefilledRow number="2" label="PRN Number :" value={formData.prn_number} />
            <FieldPrefilledRow number="3" label="Branch :" value={formData.branch} />
            <FieldPrefilledRow number="4" label="Caste:" value={formData.caste} />
            <FieldBlankRow number="5" label="Category (Open/SC/ST/OBC/VJ/NT-1/NT-2/NT-3/SEBC/EWS/TFWS):" />
            
            <div style={{ display: 'grid', gridTemplateColumns: '240px 1fr 140px 1fr', alignItems: 'baseline', fontSize: '0.84rem' }}>
              <span style={{ fontWeight: 600, color: '#1e293b' }}>6. Gender (Male/ Female/Other):</span>
              <div style={{
                borderBottom: '1.5px solid #64748b',
                height: '1.65rem',
                marginRight: '1rem',
                color: '#090d16',
                fontWeight: 700,
                display: 'flex',
                alignItems: 'center',
                paddingLeft: '0.25rem',
              }}>
                {formData.gender && formData.gender !== '—' ? formData.gender : ''}
              </div>
              <span style={{ fontWeight: 600, color: '#1e293b' }}>7. Religion :</span>
              <div style={{ borderBottom: '1.5px solid #64748b', height: '1.65rem' }} />
            </div>

            <FieldBlankRow number="8" label="Whether Student is Physically Disabled (Yes/No):" />
            <FieldBlankRow number="9" label="Mobile Number of Student:" />
            <FieldBlankRow number="10" label="Mobile Number of Parent:" />
            <FieldBlankRow number="11" label="ABC ID of Student:" />
            
            {/* 12. Local Address (2 lines for ample handwriting space) */}
            <div style={{ display: 'grid', gridTemplateColumns: '260px 1fr', alignItems: 'flex-start', fontSize: '0.84rem' }}>
              <span style={{ fontWeight: 600, color: '#1e293b', paddingTop: '0.2rem' }}>12. Local Address:</span>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.65rem' }}>
                <div style={{ borderBottom: '1.5px solid #64748b', height: '1.5rem' }} />
                <div style={{ borderBottom: '1.5px solid #64748b', height: '1.5rem' }} />
              </div>
            </div>

            {/* 13. Permanent Address (2 lines for ample handwriting space) */}
            <div style={{ display: 'grid', gridTemplateColumns: '260px 1fr', alignItems: 'flex-start', fontSize: '0.84rem' }}>
              <span style={{ fontWeight: 600, color: '#1e293b', paddingTop: '0.2rem' }}>13. Permanent Address:</span>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.65rem' }}>
                <div style={{ borderBottom: '1.5px solid #64748b', height: '1.5rem' }} />
                <div style={{ borderBottom: '1.5px solid #64748b', height: '1.5rem' }} />
              </div>
            </div>

            <FieldBlankRow number="14" label="Income Certificate Number:" />
            <FieldBlankRow number="15" label="Parent's Annual Income:" />
            <FieldBlankRow number="16" label="Whether Student has Non-Creamy Layer Certificate (Yes/No):" />
            <FieldBlankRow number="17" label="First Year admission Fees Receipt Number And Date:" />
            
            {/* 18 Credits with 1st, 2nd, 3rd year and Total */}
            <div style={{
              display: 'grid',
              gridTemplateColumns: '260px 1fr',
              alignItems: 'baseline',
              fontSize: '0.84rem',
            }}>
              <span style={{ fontWeight: 600, color: '#1e293b' }}>
                18. Total Credits Earned:
              </span>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', flexWrap: 'wrap', color: '#1e293b' }}>
                <span>First Year:</span>
                <span style={{ borderBottom: '1.5px solid #64748b', display: 'inline-block', width: '65px', height: '1.65rem' }} />
                <span>Second Year:</span>
                <span style={{ borderBottom: '1.5px solid #64748b', display: 'inline-block', width: '65px', height: '1.65rem' }} />
                <span>Third Year:</span>
                <span style={{ borderBottom: '1.5px solid #64748b', display: 'inline-block', width: '65px', height: '1.65rem' }} />
                <span>Total Credits:</span>
                <span style={{ borderBottom: '1.5px solid #64748b', display: 'inline-block', width: '75px', height: '1.65rem' }} />
              </div>
            </div>
          </div>

          {/* Student Declaration & Signature */}
          <div style={{
            display: 'grid',
            gridTemplateColumns: '1fr 1fr',
            gap: '1.5rem',
            padding: '0.75rem 0',
            borderTop: '1px solid #cbd5e1',
            marginBottom: '1rem',
            fontSize: '0.82rem',
          }}>
            <div>
              <span style={{ fontWeight: 600 }}>Signature of Student:</span> ________________________________
            </div>
            <div>
              <span style={{ fontWeight: 600 }}>Full Name of Student:</span> <span style={{ fontWeight: 700, color: '#090d16', textDecoration: 'underline' }}>{formData.full_name}</span>
            </div>
          </div>

          {/* Verification Stamps: Class Teacher & HOD with Timestamps (Confirming Eligibility) */}
          <div style={{
            display: 'grid',
            gridTemplateColumns: '1fr 1fr',
            gap: '1.25rem',
            marginBottom: '1.25rem',
          }}>
            {/* Class Teacher Seal */}
            <div style={{
              border: ct.is_approved ? '1.5px solid #16a34a' : '1.5px solid #d97706',
              background: ct.is_approved ? '#f0fdf4' : '#fffbeb',
              borderRadius: 8,
              padding: '0.75rem 1rem',
              display: 'flex',
              flexDirection: 'column',
              gap: '0.2rem',
            }}>
              <div style={{ fontSize: '0.78rem', fontWeight: 700, color: '#334155' }}>
                Signature of Class Teacher
              </div>
              <div style={{
                display: 'flex', alignItems: 'center', gap: '0.35rem',
                fontSize: '0.84rem', fontWeight: 800,
                color: ct.is_approved ? '#166534' : '#92400e',
                marginTop: '0.15rem'
              }}>
                <CheckCircle2 size={16} /> {ct.is_approved ? 'APPROVED & VERIFIED' : 'PENDING REVIEW'}
              </div>
              <div style={{ fontSize: '0.82rem', fontWeight: 700, color: '#0f172a' }}>
                Teacher: {ct.name || '—'}
              </div>
              <div style={{ fontSize: '0.74rem', color: '#475569' }}>
                Timestamp: <b>{ct.timestamp || '—'}</b>
              </div>
              {ct.remarks && (
                <div style={{ fontSize: '0.7rem', color: '#64748b', fontStyle: 'italic', marginTop: '0.1rem' }}>
                  Remarks: "{ct.remarks}"
                </div>
              )}
            </div>

            {/* HOD Seal */}
            <div style={{
              border: hod.is_approved ? '1.5px solid #16a34a' : '1.5px solid #d97706',
              background: hod.is_approved ? '#f0fdf4' : '#fffbeb',
              borderRadius: 8,
              padding: '0.75rem 1rem',
              display: 'flex',
              flexDirection: 'column',
              gap: '0.2rem',
            }}>
              <div style={{ fontSize: '0.78rem', fontWeight: 700, color: '#334155' }}>
                Signature of HOD
              </div>
              <div style={{
                display: 'flex', alignItems: 'center', gap: '0.35rem',
                fontSize: '0.84rem', fontWeight: 800,
                color: hod.is_approved ? '#166534' : '#92400e',
                marginTop: '0.15rem'
              }}>
                <ShieldCheck size={16} /> {hod.is_approved ? 'APPROVED & ENDORSED' : 'PENDING REVIEW'}
              </div>
              <div style={{ fontSize: '0.82rem', fontWeight: 700, color: '#0f172a' }}>
                HOD: {hod.name || '—'}
              </div>
              <div style={{ fontSize: '0.74rem', color: '#475569' }}>
                Timestamp: <b>{hod.timestamp || '—'}</b>
              </div>
              {hod.remarks && (
                <div style={{ fontSize: '0.7rem', color: '#64748b', fontStyle: 'italic', marginTop: '0.1rem' }}>
                  Remarks: "{hod.remarks}"
                </div>
              )}
            </div>
          </div>

          {/* For Office Use Only Box (Blank for cashier & clerk) */}
          <div style={{
            border: '1.5px solid #475569',
            background: '#f8fafc',
            borderRadius: 6,
            padding: '0.85rem 1.15rem',
            display: 'flex',
            flexDirection: 'column',
            gap: '0.65rem',
            fontSize: '0.82rem',
          }}>
            <div style={{ fontWeight: 800, textDecoration: 'underline', color: '#0f172a' }}>
              For Office Use Only:
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
              <div>
                1. <b>Eligible for Admission:</b> {formData.final_eligible ? (
                  <span style={{ color: '#166534', fontWeight: 800 }}>Yes</span>
                ) : (
                  <span style={{ color: '#dc2626', fontWeight: 800 }}>No</span>
                )}
              </div>
              <div>
                2. <b>Admission Fee Amount:</b> ___________________________
              </div>
            </div>

            <div style={{ marginTop: '0.2rem' }}>
              <span>(Signature of Student Section Clerk)</span> ________________________________
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', marginTop: '0.35rem' }}>
              <div>
                3. <b>Admission Fee Receipt Number:</b> ___________________________
              </div>
              <div>
                4. <b>UTR No:</b> ___________________________
              </div>
            </div>

            <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: '0.2rem' }}>
              <span>(Signature of Cashier)</span> ________________________________
            </div>
          </div>
        </div>

        {/* Modal footer */}
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem', paddingTop: '0.5rem' }}>
          <button
            type="button"
            onClick={onClose}
            className="edvana-btn edvana-btn-secondary"
          >
            Close
          </button>
          <button
            type="button"
            onClick={onDownloadPdf}
            disabled={downloading}
            className="edvana-btn edvana-btn-primary"
            style={{ display: 'inline-flex', alignItems: 'center', gap: '0.45rem' }}
          >
            <Download size={15} /> {downloading ? 'Downloading...' : 'Download Official PDF'}
          </button>
        </div>
      </div>
    </Modal>
  );
}

function FieldBlankRow({ number, label }) {
  return (
    <div style={{
      display: 'grid',
      gridTemplateColumns: '260px 1fr',
      alignItems: 'baseline',
      fontSize: '0.84rem',
      rowGap: '0.2rem',
    }}>
      <span style={{ fontWeight: 600, color: '#1e293b' }}>
        {number}. {label}
      </span>
      <div style={{
        borderBottom: '1.5px solid #64748b',
        height: '1.65rem',
      }} />
    </div>
  );
}

function FieldPrefilledRow({ number, label, value }) {
  return (
    <div style={{
      display: 'grid',
      gridTemplateColumns: '260px 1fr',
      alignItems: 'baseline',
      fontSize: '0.84rem',
      rowGap: '0.2rem',
    }}>
      <span style={{ fontWeight: 600, color: '#1e293b' }}>
        {number}. {label}
      </span>
      <div style={{
        borderBottom: '1.5px solid #64748b',
        height: '1.65rem',
        color: '#090d16',
        fontWeight: 700,
        display: 'flex',
        alignItems: 'center',
        paddingLeft: '0.25rem',
      }}>
        {value && value !== '—' ? value : ''}
      </div>
    </div>
  );
}

function FieldRow({ number, label, value, isBold = false, isMono = false }) {
  return (
    <div style={{
      display: 'grid',
      gridTemplateColumns: '260px 1fr',
      alignItems: 'baseline',
      fontSize: '0.82rem',
      rowGap: '0.2rem',
    }}>
      <span style={{ fontWeight: 600, color: '#1e293b' }}>
        {number}. {label}
      </span>
      <div style={{
        borderBottom: '1px solid #64748b',
        paddingBottom: '0.1rem',
        fontWeight: isBold ? 700 : 500,
        fontFamily: isMono ? 'monospace' : 'inherit',
        color: '#090d16',
        minHeight: '1.25rem',
      }}>
        {value || ''}
      </div>
    </div>
  );
}
