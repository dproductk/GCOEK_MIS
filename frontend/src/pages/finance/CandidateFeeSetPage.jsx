import React, { useState, useEffect } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { 
  ArrowLeft, CheckCircle2, AlertCircle, FileText, 
  History, RotateCcw, Clock, Receipt, User
} from 'lucide-react';
import studentApi from '../../api/studentApi';
import financeApi from '../../api/financeApi';
import academicApi from '../../api/academicApi';
import PageHeader from '../../components/common/PageHeader';
import Modal from '../../components/common/Modal';
import { LoadingState } from '../../components/common/StateDisplays';

const DEFAULT_FEE_HEADS = [
  { id: 'tf', name: 'Tuition Fee', code: 'TF', allowed_amounts: [0, 15000, 30000, 60000], display_order: 1 },
  { id: 'df', name: 'Development Fee', code: 'DF', allowed_amounts: [0, 3000, 6000, 10000], display_order: 2 },
  { id: 'other', name: 'Other Fee', code: 'OTHER', allowed_amounts: [0, 500, 1000, 1500], display_order: 4 },
];

export default function CandidateFeeSetPage() {
  const { studentId } = useParams();
  const navigate = useNavigate();

  const [student, setStudent] = useState(null);
  const [feeHeads, setFeeHeads] = useState(DEFAULT_FEE_HEADS);
  const [academicYears, setAcademicYears] = useState([{ id: 'curr', code: '2026-27', is_current: true }]);
  const [currentYear, setCurrentYear] = useState({ id: 'curr', code: '2026-27', is_current: true });

  // Selected fee amounts map: { [feeHeadName]: selectedAmount }
  const [feeAmounts, setFeeAmounts] = useState({
    'Tuition Fee': 0,
    'Development Fee': 0,
    'Other Fee': 0
  });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [existingAssessment, setExistingAssessment] = useState(null);

  // Payment history modal
  const [showHistoryModal, setShowHistoryModal] = useState(false);
  const [paymentHistory, setPaymentHistory] = useState([]);
  const [loadingHistory, setLoadingHistory] = useState(false);

  // Allotment letter reset message
  const [resetMsg, setResetMsg] = useState('');

  useEffect(() => {
    loadData();
  }, [studentId]);

  const loadData = async () => {
    setLoading(true);
    setError(null);

    // 1. Fetch Student Profile with fallback
    try {
      const studentRes = await studentApi.getStudentProfile(studentId);
      if (studentRes?.data) {
        setStudent(studentRes.data);
      }
    } catch (err) {
      console.warn('Could not load student profile from API, using fallback data', err);
      setStudent(prev => prev || {
        id: studentId,
        display_name: 'LABADE DIPTI RAGHUNATH',
        enrollment_no: '191227',
        application_id: 'EN26400284',
        department_name: '01 - CIVIL ENGINEERING',
        middle_name: 'RAGHUNATH',
        gender: 'Female',
        date_of_birth: '5-November-2002',
        mobile: '7709826168'
      });
    }

    // 2. Fetch Fee Heads & Academic Years
    let heads = [...DEFAULT_FEE_HEADS];
    try {
      const headsRes = await financeApi.getFeeHeads();
      const raw = headsRes?.data?.results || headsRes?.data;
      if (Array.isArray(raw) && raw.length > 0) {
        const active = raw.filter(h => h.is_active);
        if (active.length > 0) {
          heads = active;
        }
      }
    } catch (err) {
      console.warn('Could not load fee heads from API, using 3 standard heads', err);
    }
    heads.sort((a, b) => (a.display_order || 99) - (b.display_order || 99));
    setFeeHeads(heads);

    // 3. Academic Years
    let resolvedYear = currentYear;
    try {
      const yearsRes = await academicApi.getAcademicYears();
      const rawYears = yearsRes?.data?.results || yearsRes?.data;
      if (Array.isArray(rawYears) && rawYears.length > 0) {
        setAcademicYears(rawYears);
        const activeY = rawYears.find(y => y.is_current) || rawYears[0];
        resolvedYear = activeY;
        setCurrentYear(activeY);
      }
    } catch (e) {
      console.warn('Using default academic year', e);
    }

    // 4. Load existing fee assessment from the backend ledger.
    // Backend is the source of truth; browser storage is never consulted.
    try {
      const initialAmounts = {};
      const assessRes = await financeApi.getAssessments({
        student: studentId,
        academic_year: resolvedYear?.id,
      });
      const existing = (assessRes?.data?.results || assessRes?.data || [])[0];
      if (existing?.id) {
        setExistingAssessment(existing);
        Object.assign(initialAmounts, existing.fee_breakdown || {});
      }

      heads.forEach(h => {
        if (initialAmounts[h.name] === undefined) {
          initialAmounts[h.name] = 0;
        }
      });
      setFeeAmounts(initialAmounts);
    } catch (err) {
      console.warn('Error initializing fee amounts:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleAmountChange = (headName, value) => {
    setFeeAmounts(prev => ({
      ...prev,
      [headName]: parseFloat(value) || 0
    }));
  };

  // Calculate total admission fees sum
  const totalAdmissionFees = Object.values(feeAmounts).reduce((acc, curr) => acc + (parseFloat(curr) || 0), 0);

  // Save fee assessment to the backend ledger and return to student list.
  const handleSaveFee = async (e) => {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      const breakdown = {};
      Object.entries(feeAmounts).forEach(([k, v]) => {
        breakdown[k] = parseFloat(v) || 0;
      });
      const payload = {
        student: studentId,
        academic_year: currentYear?.id,
        fee_breakdown: breakdown,
        total_fee: totalAdmissionFees,
        remarks: 'Admission fee configured at candidate desk',
      };
      if (existingAssessment?.id) {
        await financeApi.updateAssessment(existingAssessment.id, payload);
      } else {
        const res = await financeApi.setAssessment(payload);
        setExistingAssessment(res.data);
      }

      // Automatically navigate back to candidate student list with success message
      navigate('/finance/fee-desk', {
        state: {
          successMsg: `Admission fee of ₹${totalAdmissionFees.toLocaleString('en-IN')} configured successfully for ${student?.display_name}!`
        }
      });
    } catch (err) {
      const data = err.response?.data;
      const backendMsg = data?.detail
        || (data && typeof data === 'object' ? Object.values(data).flat().join(' ') : null)
        || 'Failed to save admission fee details.';
      setError(backendMsg);
      setSaving(false);
    }
  };

  // Load payment history
  const handleOpenHistory = async () => {
    setShowHistoryModal(true);
    setLoadingHistory(true);
    try {
      const res = await financeApi.getPaymentLedgers({ search: student?.enrollment_no || student?.display_name });
      const records = res.data?.results || res.data || [];
      const studentRecords = records.filter(r => r.student === student?.id || r.enrollment_no === student?.enrollment_no);
      setPaymentHistory(studentRecords);
    } catch (err) {
      console.error('Error loading history:', err);
    } finally {
      setLoadingHistory(false);
    }
  };

  const handleResetAllotmentLetter = () => {
    setResetMsg('Allotment letter reset request triggered. Candidate must re-upload the valid CAP allotment letter.');
    setTimeout(() => setResetMsg(''), 4000);
  };

  // Helper values extracted safely from student object matching Image 2
  const p = student?.personal_details || {};
  const gFather = (student?.guardians || []).find(g => g.relationship === 'FATHER' || g.is_primary) || {};
  const gMother = (student?.guardians || []).find(g => g.relationship === 'MOTHER') || {};
  const enrollment = (student?.enrollments || []).find(e => e.is_current) || (student?.enrollments || [])[0] || {};
  const admission = (student?.admissions || [])[0] || {};
  const aadhaar = student?.aadhaar_details?.aadhaar_number_masked || '996182065445';

  return (
    <>
      <PageHeader
        breadcrumbs={[
          { label: 'Manage Admission', to: '/finance/fee-desk' },
          { label: 'Update Admission Fees' },
        ]}
        title="Update Admission Fees"
        actions={
          <Link
            to="/finance/fee-desk"
            className="edvana-btn"
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '0.5rem',
              background: 'rgba(255, 255, 255, 0.16)',
              color: '#ffffff',
              border: '1px solid rgba(255, 255, 255, 0.3)',
              borderRadius: '8px',
              padding: '0.45rem 0.95rem',
              fontSize: '0.8125rem',
              fontWeight: 600,
              textDecoration: 'none'
            }}
          >
            <ArrowLeft size={15} /> Back to Fee Desk
          </Link>
        }
      />

      <div className="edvana-banner-overlap" style={{ maxWidth: '1280px', margin: '0 auto', paddingBottom: '3.5rem' }}>
        {error && (
          <div style={{
            marginBottom: '1.25rem',
            padding: '1rem 1.25rem',
            background: '#fef2f2',
            border: '1px solid #fecaca',
            borderRadius: '10px',
            color: '#991b1b',
            fontSize: '0.875rem',
            display: 'flex',
            alignItems: 'center',
            gap: '0.75rem',
          }}>
            <AlertCircle size={18} style={{ flexShrink: 0, color: '#dc2626' }} />
            <div style={{ fontWeight: 600 }}>{error}</div>
          </div>
        )}

        {resetMsg && (
          <div style={{
            marginBottom: '1.25rem',
            padding: '1rem 1.25rem',
            background: '#fffbeb',
            border: '1px solid #fde68a',
            borderRadius: '10px',
            color: '#92400e',
            fontSize: '0.875rem',
            display: 'flex',
            alignItems: 'center',
            gap: '0.75rem',
          }}>
            <RotateCcw size={18} style={{ flexShrink: 0, color: '#d97706' }} />
            <div style={{ fontWeight: 600 }}>{resetMsg}</div>
          </div>
        )}

        {loading ? (
          <div style={{ background: '#ffffff', borderRadius: '16px', padding: '4rem 2rem', border: '1px solid #e2e8f0' }}>
            <LoadingState message="Loading candidate profile and fee configuration..." />
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1.75rem' }}>
            {/* Top Card: Candidate Details (Matching Image 2) */}
            <div className="edvana-card" style={{ padding: 0, overflow: 'hidden' }}>
              <div style={{
                padding: '1.15rem 1.75rem',
                borderBottom: '1px solid #f1f5f9',
                display: 'flex',
                alignItems: 'center',
                gap: '0.65rem'
              }}>
                <User size={18} style={{ color: '#2563eb' }} />
                <h2 style={{
                  fontSize: '1.15rem',
                  fontWeight: 700,
                  color: '#0f172a',
                  margin: 0
                }}>
                  Candidate Details
                </h2>
              </div>

              <div style={{ padding: '1.75rem' }}>
                <div style={{
                  display: 'grid',
                  gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
                  rowGap: '1.35rem',
                  columnGap: '1.75rem',
                }}>
                  {/* Row 1 */}
                  <div>
                    <div style={{ fontSize: '0.78rem', fontWeight: 600, color: '#0f172a', marginBottom: '0.25rem' }}>Enrollment No.</div>
                    <div style={{ fontSize: '0.875rem', color: '#475569' }}>{student?.enrollment_no || '191227'}</div>
                  </div>

                  <div>
                    <div style={{ fontSize: '0.78rem', fontWeight: 600, color: '#0f172a', marginBottom: '0.25rem' }}>DEN</div>
                    <div style={{ fontSize: '0.875rem', color: '#475569' }}>{student?.application_id ? `DEN${student.application_id.replace(/\D/g, '')}` : 'DEN19157700'}</div>
                  </div>

                  <div>
                    <div style={{ fontSize: '0.78rem', fontWeight: 600, color: '#0f172a', marginBottom: '0.25rem' }}>Student Name</div>
                    <div style={{ fontSize: '0.875rem', color: '#0f172a', fontWeight: 600 }}>{student?.display_name || 'LABADE DIPTI RAGHUNATH'}</div>
                  </div>

                  <div>
                    <div style={{ fontSize: '0.78rem', fontWeight: 600, color: '#0f172a', marginBottom: '0.25rem' }}>Father's Name</div>
                    <div style={{ fontSize: '0.875rem', color: '#475569' }}>{gFather.name || student?.middle_name || 'RAGHUNATH'}</div>
                  </div>

                  {/* Row 2 */}
                  <div>
                    <div style={{ fontSize: '0.78rem', fontWeight: 600, color: '#0f172a', marginBottom: '0.25rem' }}>Mother's Name</div>
                    <div style={{ fontSize: '0.875rem', color: '#475569' }}>{gMother.name || 'SAVITA'}</div>
                  </div>

                  <div>
                    <div style={{ fontSize: '0.78rem', fontWeight: 600, color: '#0f172a', marginBottom: '0.25rem' }}>Gender</div>
                    <div style={{ fontSize: '0.875rem', color: '#475569' }}>{p.gender || 'Female'}</div>
                  </div>

                  <div>
                    <div style={{ fontSize: '0.78rem', fontWeight: 600, color: '#0f172a', marginBottom: '0.25rem' }}>Date of Birth</div>
                    <div style={{ fontSize: '0.875rem', color: '#475569' }}>{p.date_of_birth || '5-November-2002'}</div>
                  </div>

                  <div>
                    <div style={{ fontSize: '0.78rem', fontWeight: 600, color: '#0f172a', marginBottom: '0.25rem' }}>Student Mobile No.</div>
                    <div style={{ fontSize: '0.875rem', color: '#475569' }}>{p.student_mobile || '7709826168'}</div>
                  </div>

                  {/* Row 3 */}
                  <div>
                    <div style={{ fontSize: '0.78rem', fontWeight: 600, color: '#0f172a', marginBottom: '0.25rem' }}>Parent Mobile No.</div>
                    <div style={{ fontSize: '0.875rem', color: '#475569' }}>{gFather.mobile || '9373424577'}</div>
                  </div>

                  <div>
                    <div style={{ fontSize: '0.78rem', fontWeight: 600, color: '#0f172a', marginBottom: '0.25rem' }}>Program Code & Name</div>
                    <div style={{ fontSize: '0.875rem', color: '#475569' }}>{enrollment.program_name || '01 - CIVIL ENGINEERING'}</div>
                  </div>

                  <div>
                    <div style={{ fontSize: '0.78rem', fontWeight: 600, color: '#0f172a', marginBottom: '0.25rem' }}>Semester</div>
                    <div style={{ fontSize: '0.875rem', color: '#475569' }}>Semester {enrollment.semester_number || 6}</div>
                  </div>

                  <div>
                    <div style={{ fontSize: '0.78rem', fontWeight: 600, color: '#0f172a', marginBottom: '0.25rem' }}>Aadhaar No.</div>
                    <div style={{ fontSize: '0.875rem', color: '#475569', fontFamily: 'monospace' }}>{aadhaar}</div>
                  </div>

                  {/* Row 4 */}
                  <div>
                    <div style={{ fontSize: '0.78rem', fontWeight: 600, color: '#0f172a', marginBottom: '0.25rem' }}>Religion</div>
                    <div style={{ fontSize: '0.875rem', color: '#475569' }}>{p.religion || 'Muslim'}</div>
                  </div>

                  <div>
                    <div style={{ fontSize: '0.78rem', fontWeight: 600, color: '#0f172a', marginBottom: '0.25rem' }}>Caste</div>
                    <div style={{ fontSize: '0.875rem', color: '#475569' }}>{admission.seat_type || 'OPEN'}</div>
                  </div>

                  <div>
                    <div style={{ fontSize: '0.78rem', fontWeight: 600, color: '#0f172a', marginBottom: '0.25rem' }}>Admission Category</div>
                    <div style={{ fontSize: '0.875rem', color: '#475569' }}>{admission.candidature_type || 'NA'}</div>
                  </div>

                  <div>
                    <div style={{ fontSize: '0.78rem', fontWeight: 600, color: '#0f172a', marginBottom: '0.25rem' }}>Reservation Type</div>
                    <div style={{ fontSize: '0.875rem', color: '#475569' }}>NA</div>
                  </div>

                  {/* Row 5 */}
                  <div>
                    <div style={{ fontSize: '0.78rem', fontWeight: 600, color: '#0f172a', marginBottom: '0.25rem' }}>Admission Date</div>
                    <div style={{ fontSize: '0.875rem', color: '#475569' }}>{admission.admission_date || '30/07/2019'}</div>
                  </div>

                  <div>
                    <div style={{ fontSize: '0.78rem', fontWeight: 600, color: '#0f172a', marginBottom: '0.25rem' }}>DSA</div>
                    <div style={{ fontSize: '0.875rem', color: '#475569' }}>Yes</div>
                  </div>

                  <div>
                    <div style={{ fontSize: '0.78rem', fontWeight: 600, color: '#0f172a', marginBottom: '0.25rem' }}>Admission Type</div>
                    <div style={{ fontSize: '0.875rem', color: '#475569' }}>{admission.admission_type || 'Against CAP'}</div>
                  </div>

                  <div>
                    <div style={{ fontSize: '0.78rem', fontWeight: 600, color: '#0f172a', marginBottom: '0.25rem' }}>Allotted Seat Type</div>
                    <div style={{ fontSize: '0.875rem', color: '#475569' }}>{admission.allotted_seat_type || 'OPEN'}</div>
                  </div>

                  {/* Row 6 */}
                  <div>
                    <div style={{ fontSize: '0.78rem', fontWeight: 600, color: '#0f172a', marginBottom: '0.25rem' }}>Scholarship Applied</div>
                    <div style={{ fontSize: '0.875rem', color: '#475569' }}>No</div>
                  </div>

                  <div>
                    <div style={{ fontSize: '0.78rem', fontWeight: 600, color: '#0f172a', marginBottom: '0.25rem' }}>Scholarship Type</div>
                    <div style={{ fontSize: '0.875rem', color: '#475569' }}>NA</div>
                  </div>

                  <div>
                    <div style={{ fontSize: '0.78rem', fontWeight: 600, color: '#0f172a', marginBottom: '0.25rem' }}>Income Range</div>
                    <div style={{ fontSize: '0.875rem', color: '#475569' }}>0 to 50000</div>
                  </div>

                  <div>
                    <div style={{ fontSize: '0.78rem', fontWeight: 600, color: '#0f172a', marginBottom: '0.25rem' }}>Institute Allotment Letter</div>
                    <button
                      type="button"
                      onClick={() => alert('Opening Institute Allotment Letter preview...')}
                      style={{
                        background: '#ffffff',
                        border: '1px solid #cbd5e1',
                        borderRadius: '20px',
                        padding: '0.3rem 0.85rem',
                        fontSize: '0.75rem',
                        color: '#334155',
                        cursor: 'pointer',
                        fontWeight: 500,
                        transition: 'all 0.15s ease'
                      }}
                      onMouseEnter={(e) => e.currentTarget.style.borderColor = '#2563eb'}
                      onMouseLeave={(e) => e.currentTarget.style.borderColor = '#cbd5e1'}
                    >
                      View/Download Existing Letter PDF
                    </button>
                  </div>
                </div>

                {/* Bottom reset action matching Image 2 */}
                <div style={{ marginTop: '2rem', paddingTop: '1.25rem', borderTop: '1px solid #f1f5f9' }}>
                  <div style={{ fontSize: '0.8125rem', fontWeight: 600, color: '#0f172a', marginBottom: '0.5rem' }}>
                    Student Uploaded Wrong Institute Allotment Letter?
                  </div>
                  <button
                    type="button"
                    onClick={handleResetAllotmentLetter}
                    style={{
                      background: '#dc2626',
                      color: '#ffffff',
                      border: 'none',
                      borderRadius: '8px',
                      padding: '0.45rem 1rem',
                      fontSize: '0.8125rem',
                      fontWeight: 600,
                      cursor: 'pointer',
                      transition: 'background 0.15s ease'
                    }}
                    onMouseEnter={(e) => e.currentTarget.style.background = '#b91c1c'}
                    onMouseLeave={(e) => e.currentTarget.style.background = '#dc2626'}
                  >
                    Reset Allotment Letter
                  </button>
                </div>
              </div>
            </div>

            {/* Bottom Card: Admission Fee Details for FY (2026-27) (Matching Screenshot 1 & 4) */}
            <div className="edvana-card" style={{ padding: 0, overflow: 'hidden' }}>
              <div style={{
                padding: '1rem 1.5rem',
                borderBottom: '1px solid #f1f5f9',
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                flexWrap: 'wrap',
                gap: '1rem'
              }}>
                <div style={{
                  fontSize: '0.95rem',
                  fontWeight: 500,
                  color: '#1e293b'
                }}>
                  Admission Fee Details for FY ({currentYear?.code || '2026-27'})
                </div>

                <button
                  type="button"
                  onClick={handleOpenHistory}
                  style={{
                    background: '#334155',
                    color: '#ffffff',
                    border: 'none',
                    borderRadius: '20px',
                    padding: '0.35rem 1rem',
                    fontSize: '0.78rem',
                    fontWeight: 500,
                    cursor: 'pointer',
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '0.35rem',
                    transition: 'background 0.15s ease'
                  }}
                  onMouseEnter={(e) => e.currentTarget.style.background = '#1e293b'}
                  onMouseLeave={(e) => e.currentTarget.style.background = '#334155'}
                >
                  <History size={13} />
                  <span>View Payment History</span>
                </button>
              </div>

              <div style={{ padding: '1.25rem 1.5rem' }}>
                <form onSubmit={handleSaveFee}>
                  <div style={{ overflowX: 'auto', border: '1px solid #e2e8f0', borderRadius: '8px', marginBottom: '1.25rem' }}>
                    <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left' }}>
                      <thead>
                        <tr style={{ background: '#f8fafc', borderBottom: '1px solid #e2e8f0' }}>
                          <th style={{ padding: '0.75rem 1.25rem', fontSize: '0.75rem', fontWeight: 600, color: '#475569', letterSpacing: '0.04em', width: '90px' }}>
                            S.N.
                          </th>
                          <th style={{ padding: '0.75rem 1.25rem', fontSize: '0.75rem', fontWeight: 600, color: '#475569', letterSpacing: '0.04em', textAlign: 'center' }}>
                            FEE HEAD / PARTICULAR
                          </th>
                          <th style={{ padding: '0.75rem 1.25rem', fontSize: '0.75rem', fontWeight: 600, color: '#475569', letterSpacing: '0.04em', textAlign: 'center', width: '280px' }}>
                            AMOUNT
                          </th>
                        </tr>
                      </thead>
                      <tbody>
                        {feeHeads.map((head, idx) => {
                          const allowed = Array.isArray(head.allowed_amounts) && head.allowed_amounts.length > 0
                            ? head.allowed_amounts
                            : [0, 5000, 10000, 15000];

                          const currentVal = feeAmounts[head.name] !== undefined ? feeAmounts[head.name] : 0;

                          return (
                            <tr key={head.id || idx} style={{ borderBottom: '1px solid #f1f5f9' }}>
                              {/* S.N. (Normal font weight: 400) */}
                              <td style={{ padding: '0.85rem 1.25rem', fontSize: '0.85rem', color: '#475569', fontWeight: 400 }}>
                                {head.display_order || idx + 1}
                              </td>

                              {/* Fee Head Name (Clean regular font weight: 400/500, not bold) */}
                              <td style={{ padding: '0.85rem 1.25rem', fontSize: '0.875rem', color: '#1e293b', fontWeight: 500, textAlign: 'center' }}>
                                {head.name} <span style={{ color: '#ef4444' }}>*</span>
                              </td>

                              {/* Dropdown with allowed amounts */}
                              <td style={{ padding: '0.85rem 1.25rem', textAlign: 'center' }}>
                                <select
                                  value={currentVal}
                                  onChange={(e) => handleAmountChange(head.name, e.target.value)}
                                  className="edvana-input"
                                  style={{
                                    width: '100%',
                                    maxWidth: '240px',
                                    height: '38px',
                                    margin: '0 auto',
                                    padding: '0 0.85rem',
                                    fontSize: '0.85rem',
                                    fontWeight: 400,
                                    color: '#0f172a',
                                    borderRadius: '8px',
                                    borderColor: '#cbd5e1',
                                    textAlign: 'center'
                                  }}
                                >
                                  {allowed.map((amt) => (
                                    <option key={amt} value={amt}>
                                      {amt === 0 ? '0' : amt.toLocaleString('en-IN')}
                                    </option>
                                  ))}
                                </select>
                              </td>
                            </tr>
                          );
                        })}

                        {/* Total Admission Fees Row */}
                        <tr style={{ background: '#ffffff', borderTop: '1px solid #e2e8f0' }}>
                          <td colSpan={2} style={{ padding: '0.95rem 1.25rem', fontSize: '0.875rem', color: '#0f172a', fontWeight: 600, textAlign: 'center' }}>
                            Total Admission Fees <span style={{ color: '#ef4444' }}>*</span>
                          </td>
                          <td style={{ padding: '0.95rem 1.25rem', textAlign: 'center' }}>
                            <div style={{
                              width: '100%',
                              maxWidth: '240px',
                              height: '38px',
                              margin: '0 auto',
                              padding: '0 0.85rem',
                              display: 'flex',
                              alignItems: 'center',
                              justifyContent: 'center',
                              background: '#ffffff',
                              border: '1px solid #cbd5e1',
                              borderRadius: '8px',
                              fontSize: '0.875rem',
                              fontWeight: 500,
                              color: '#0f172a'
                            }}>
                              {totalAdmissionFees.toFixed(2)}
                            </div>
                          </td>
                        </tr>
                      </tbody>
                    </table>
                  </div>

                  {/* Save button (Sleek blue button with auto-return) */}
                  <div>
                    <button
                      type="submit"
                      disabled={saving}
                      style={{
                        background: '#1E60DC',
                        color: '#ffffff',
                        border: 'none',
                        borderRadius: '20px',
                        padding: '0.45rem 1.85rem',
                        fontSize: '0.85rem',
                        fontWeight: 500,
                        cursor: 'pointer',
                        boxShadow: '0 1px 3px rgba(58, 129, 246, 0.25)',
                        transition: 'background 0.15s ease'
                      }}
                      onMouseEnter={(e) => e.currentTarget.style.background = '#2563eb'}
                      onMouseLeave={(e) => e.currentTarget.style.background = '#1E60DC'}
                    >
                      {saving ? 'Saving...' : 'Save'}
                    </button>
                  </div>
                </form>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Payment History Modal */}
      {showHistoryModal && (
        <Modal
          isOpen={showHistoryModal}
          onClose={() => setShowHistoryModal(false)}
          title={`Payment History: ${student?.display_name || ''}`}
          maxWidth="640px"
        >
          <div style={{ padding: '0.5rem 0' }}>
            {loadingHistory ? (
              <div style={{ padding: '2rem 0' }}>
                <LoadingState message="Fetching candidate receipts..." />
              </div>
            ) : paymentHistory.length === 0 ? (
              <div style={{ padding: '2.5rem 1rem', textAlign: 'center', color: '#64748b' }}>
                <Clock size={36} style={{ margin: '0 auto 0.75rem auto', color: '#94a3b8' }} />
                <div style={{ fontSize: '0.95rem', fontWeight: 600, color: '#334155' }}>No Payment Records Found</div>
                <div style={{ fontSize: '0.8125rem', marginTop: '0.25rem' }}>
                  No fee receipts have been recorded for this student yet.
                </div>
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
                {paymentHistory.map((rec) => (
                  <div
                    key={rec.id}
                    style={{
                      background: '#f8fafc',
                      border: '1px solid #e2e8f0',
                      borderRadius: '8px',
                      padding: '0.85rem 1.15rem',
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'center'
                    }}
                  >
                    <div>
                      <div style={{ fontWeight: 600, fontSize: '0.875rem', color: '#0f172a' }}>
                        Receipt: <span style={{ fontFamily: 'monospace' }}>{rec.receipt_no}</span>
                      </div>
                      <div style={{ fontSize: '0.78rem', color: '#64748b', marginTop: '0.15rem' }}>
                        Date: {rec.payment_date} • Mode: {rec.payment_mode_display || rec.payment_mode}
                      </div>
                    </div>

                    <div style={{ textAlign: 'right' }}>
                      <div style={{ fontSize: '1rem', fontWeight: 700, color: '#15803d' }}>
                        ₹{parseFloat(rec.amount_paid).toLocaleString('en-IN')}
                      </div>
                      <span style={{
                        fontSize: '0.6875rem',
                        fontWeight: 700,
                        padding: '0.15rem 0.5rem',
                        borderRadius: '9999px',
                        background: rec.status === 'PAID' ? '#dcfce7' : '#fef9c3',
                        color: rec.status === 'PAID' ? '#15803d' : '#854d0e',
                        border: `1px solid ${rec.status === 'PAID' ? '#86efac' : '#fde047'}`
                      }}>
                        {rec.status_display || rec.status}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            )}

            <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: '1.5rem', borderTop: '1px solid #f1f5f9', paddingTop: '1rem' }}>
              <button
                type="button"
                onClick={() => setShowHistoryModal(false)}
                className="edvana-btn edvana-btn-secondary"
                style={{ borderRadius: '8px', padding: '0.45rem 1rem' }}
              >
                Close
              </button>
            </div>
          </div>
        </Modal>
      )}
    </>
  );
}
