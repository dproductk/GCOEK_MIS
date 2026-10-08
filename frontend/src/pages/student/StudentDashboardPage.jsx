import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import PageHeader from '../../components/common/PageHeader';
import CollegeIllustration from '../../components/common/CollegeIllustration';
import Reveal from '../../components/common/Reveal';
import { ArrowRight, GraduationCap, FileCheck } from 'lucide-react';
import studentApi from '../../api/studentApi';
import resultsApi from '../../api/resultsApi';

export default function StudentDashboardPage() {
  const navigate = useNavigate();
  const [semTitle, setSemTitle] = useState('');
  const [semSub, setSemSub] = useState('');
  const [admissionForm, setAdmissionForm] = useState(null);

  // Current semester pill and admission verification status
  useEffect(() => {
    let ignore = false;
    (async () => {
      try {
        const [profileRes, formRes] = await Promise.allSettled([
          studentApi.getMyProfile(),
          resultsApi.getAdmissionFormData(),
        ]);
        if (ignore) return;
        if (profileRes.status === 'fulfilled') {
          const enr = profileRes.value.data?.current_enrollment || {};
          if (enr.semester_number) {
            setSemTitle(`Sem ${enr.semester_number}${enr.division_name ? ` • Div ${enr.division_name}` : ''}`);
            setSemSub(enr.academic_year_code || '—');
          }
        }
        if (formRes.status === 'fulfilled') {
          setAdmissionForm(formRes.value.data);
        }
      } catch {
        /* pill stays hidden on failure */
      }
    })();
    return () => {
      ignore = true;
    };
  }, []);

  return (
    <>
      {/* Institutional Royal Blue Header matching Screenshot 1 */}
      <PageHeader
        breadcrumbs={[{ label: 'Home' }]}
        title="Dashboard"
        subtitle="Welcome to your student portal"
        actions={
          semTitle ? (
            <div
              className="edvana-banner-seal-badge"
              title="Your currently enrolled semester"
              style={{ gap: '0.6rem' }}
            >
              <span
                style={{
                  width: '34px',
                  height: '34px',
                  borderRadius: '50%',
                  background: 'rgba(255, 255, 255, 0.92)',
                  color: '#1E60DC',
                  display: 'inline-flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  flexShrink: 0,
                }}
              >
                <GraduationCap size={18} />
              </span>
              <div className="edvana-seal-text">
                <span className="edvana-seal-title">{semTitle}</span>
                <span className="edvana-seal-sub">{semSub}</span>
              </div>
            </div>
          ) : null
        }
      />

      {/* Main Content Overlap */}
      <div className="edvana-banner-overlap">
        {/* Admission Verification Status Card (when HOD initiates verification) */}
        {admissionForm?.has_verification && (
          <Reveal>
            <div
              style={{
                background: '#ffffff',
                border: '1px solid #e2e8f0',
                borderRadius: 20,
                boxShadow: '0 1px 2px rgba(16, 24, 40, 0.06), 0 10px 28px -12px rgba(15, 40, 90, 0.18)',
                padding: '1.15rem 1.75rem',
                marginBottom: '1.25rem',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                flexWrap: 'wrap',
                gap: '1.25rem',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', minWidth: '280px', flex: '1 1 auto' }}>
                <div
                  style={{
                    width: 48, height: 48, borderRadius: 14, flexShrink: 0,
                    background: admissionForm.final_eligible ? '#e6f7ec' : (admissionForm.verification_stage_tone === 'red' ? '#fee2e2' : '#fef3c7'),
                    color: admissionForm.final_eligible ? '#16a34a' : (admissionForm.verification_stage_tone === 'red' ? '#dc2626' : '#d97706'),
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                  }}
                >
                  <FileCheck size={24} strokeWidth={1.8} />
                </div>
                <div>
                  <div style={{ fontSize: '0.68rem', fontWeight: 600, letterSpacing: '0.05em', color: '#64748b', textTransform: 'uppercase' }}>
                    ADMISSION VERIFICATION & PROOF
                  </div>
                  <div style={{ fontSize: '1.02rem', fontWeight: 800, color: '#0f172a', marginTop: '0.1rem' }}>
                    {admissionForm.form_title || 'Admission Application Form'}
                  </div>
                  <div style={{ fontSize: '0.78rem', color: '#64748b', marginTop: '0.15rem' }}>
                    {admissionForm.final_eligible
                      ? 'Verified by Class Teacher & HOD — Official copy ready for counter fee payment'
                      : admissionForm.verification_stage === 'HOD_PENDING'
                      ? 'Class Teacher verified — Waiting for Head of Department endorsement'
                      : admissionForm.verification_stage === 'TEACHER_PENDING'
                      ? 'Verification initiated by Department — Under review by Class Teacher'
                      : admissionForm.verification_stage === 'FLAGGED'
                      ? `Clarification needed: "${admissionForm.remarks || 'Check with Class Teacher'}"`
                      : 'Verification in progress'}
                  </div>
                </div>
              </div>

              <div style={{ display: 'flex', alignItems: 'center', gap: '1.25rem', flexWrap: 'wrap' }}>
                <div>
                  <span
                    style={{
                      display: 'inline-flex', alignItems: 'center', gap: '0.45rem',
                      background: admissionForm.final_eligible ? '#e6f7ec' : (admissionForm.verification_stage_tone === 'red' ? '#fee2e2' : '#fef3c7'),
                      color: admissionForm.final_eligible ? '#1a7f37' : (admissionForm.verification_stage_tone === 'red' ? '#dc2626' : '#92400e'),
                      fontSize: '0.78rem', fontWeight: 600,
                      padding: '0.38rem 0.85rem', borderRadius: 999,
                    }}
                  >
                    <span style={{ width: 8, height: 8, borderRadius: '50%', background: admissionForm.final_eligible ? '#22a355' : (admissionForm.verification_stage_tone === 'red' ? '#dc2626' : '#d97706'), flexShrink: 0 }} />
                    {admissionForm.verification_stage_label || (admissionForm.final_eligible ? 'Verified by CT & HOD' : 'Pending Verification')}
                  </span>
                </div>

                <button
                  type="button"
                  onClick={() => navigate('/fees')}
                  className="edvana-btn edvana-btn-primary"
                  style={{
                    padding: '0.65rem 1.25rem', fontSize: '0.84rem', fontWeight: 700,
                    borderRadius: 12, background: '#1E60DC', color: '#ffffff',
                    border: '1px solid #1E60DC',
                    display: 'inline-flex', alignItems: 'center', gap: '0.45rem',
                  }}
                >
                  <span>View Form & Fees</span>
                  <ArrowRight size={15} />
                </button>
              </div>
            </div>
          </Reveal>
        )}

        {/* Signature Welcome Hero Card matching Screenshot 1 */}
        <Reveal>
        <div className="edvana-card edvana-welcome-hero-card">
          <div className="edvana-welcome-grid">
            {/* Left Content Column */}
            <div className="edvana-welcome-left">
              <h2 className="edvana-welcome-title">
                Welcome to Government College of Engineering, Kolhapur
              </h2>
              <p className="edvana-welcome-subtitle">
                This is your centralized hub for managing your academic activities.
              </p>

              <ul className="edvana-welcome-checklist">
                <li>
                  <span className="checklist-bullet">•</span>
                  <span>View and update your registration information, address, contact details, and bank details</span>
                </li>
                <li>
                  <span className="checklist-bullet">•</span>
                  <span>Register for your exams</span>
                </li>
                <li>
                  <span className="checklist-bullet">•</span>
                  <span>Download hall ticket</span>
                </li>
                <li>
                  <span className="checklist-bullet">•</span>
                  <span>Print your fee receipts</span>
                </li>
                <li>
                  <span className="checklist-bullet">•</span>
                  <span>Access your results and academic records</span>
                </li>
                <li>
                  <span className="checklist-bullet">•</span>
                  <span>And more</span>
                </li>
              </ul>

              <div style={{ marginTop: '1.75rem' }}>
                <button
                  className="edvana-btn edvana-btn-primary"
                  onClick={() => navigate('/profile')}
                  style={{
                    padding: '0.6875rem 1.35rem',
                    fontSize: '0.875rem',
                    fontWeight: 600,
                    borderRadius: '8px',
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '0.5rem',
                  }}
                >
                  <span>View Student Profile</span>
                  <ArrowRight size={16} />
                </button>
              </div>
            </div>

            {/* Right Classical Architecture Illustration & Quote */}
            <div className="edvana-welcome-right">
              <CollegeIllustration quote='"Engineering for a Better Tomorrow"' />
            </div>
          </div>
        </div>
        </Reveal>

      </div>
    </>
  );
}
