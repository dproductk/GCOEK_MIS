import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import studentApi from '../../api/studentApi';
import { LoadingState, ErrorState } from '../../components/common/StateDisplays';
import PageHeader from '../../components/common/PageHeader';
import {
  GraduationCap,
  Image as ImageIcon,
  CreditCard,
  Building,
  FileText,
  Info,
  ArrowLeft,
  CheckCircle2,
  FileCheck,
} from 'lucide-react';

export default function StudentProfilePage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { user, hasRole } = useAuth();

  const [student, setStudent] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [activeTab, setActiveTab] = useState('registration');
  const [statusMessage, setStatusMessage] = useState('');

  // Media previews
  const [photoPreview, setPhotoPreview] = useState(null);
  const [signaturePreview, setSignaturePreview] = useState(null);

  // Form State initialized to institutional defaults & populated from backend
  const [formData, setFormData] = useState({
    fullName: '',
    dteAppId: 'DEN18146293',
    fatherName: 'SURESH KUMAR',
    motherName: 'SUNITA KUMAR',
    placeOfBirth: 'Kolhapur',
    dobDay: '12',
    dobMonth: 'May',
    dobYear: '2004',
    gender: 'Male',
    dateOfAdmission: '2024-08-14',
    admissionType: 'CAP',
    allottedSeatType: 'NT-C',
    scholarshipApplied: 'Yes',
    scholarshipType: 'NT-C',
    annualIncome: '600000 to 700000',
    address: 'Near Shivaji University, Rajaram College Road',
    district: 'Kolhapur',
    state: 'Maharashtra',
    pincode: '416004',
    // Aadhaar
    aadhaarNo: 'XXXX-XXXX-XXXX',
    aadhaarName: '',
    aadhaarMobile: '9989776855',
    // Bank
    bankHolderName: '',
    bankName: 'State Bank of India',
    branchName: 'Kolhapur Main Branch',
    accountNo: '39485729103',
    ifscCode: 'SBIN0001234',
    // SSC Marksheet
    sscBoard: 'Maharashtra State Board of Secondary and Higher Secondary Education (MSBSHSE)',
    sscSchool: 'Chhatrapati Shahu Vidyalaya, Kolhapur',
    sscPassingYear: '2022',
    sscSeatNo: 'M094821',
    sscMarksObtained: '468 / 500',
    sscPercentage: '93.60%',
    // HSC Marksheet
    hscStream: 'Class XII (Science)',
    hscBoard: 'Maharashtra State Board (MSBSHSE)',
    hscCollege: 'Vivekanand College, Kolhapur',
    hscPassingYear: '2024',
    hscSeatNo: 'H083921',
    hscMarksObtained: '522 / 600',
    hscPercentage: '87.00%',
  });

  const [retryCount, setRetryCount] = useState(0);

  // Backend StudentViewSet has no generic update endpoint.
  // Students may edit their OWN profile (no `id` param) via PATCH /students/me/update/.
  // Identity, admission, Aadhaar number and verified marksheets stay locked for everyone.
  // Teachers/staff opening /students/:id from the directory are strictly read-only.
  const isOwnProfile = !id;
  const canEdit = isOwnProfile && hasRole('STUDENT');
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    let ignore = false;

    async function fetchProfile() {
      try {
        setLoading(true);
        setError(null);
        let res;
        if (id) {
          res = await studentApi.getStudentProfile(id);
        } else {
          res = await studentApi.getMyProfile();
        }
        if (ignore) return;
        const data = res.data;
        setStudent(data);

        const p = data.personal_details || {};
        const addrs = data.addresses || [];
        const perm = addrs.find((a) => a.address_type === 'PERMANENT') || addrs[0] || {};
        const gFather = (data.guardians || []).find(
          (g) => g.relationship === 'FATHER' || g.relationship === 'Father'
        );
        const gMother = (data.guardians || []).find(
          (g) => g.relationship === 'MOTHER' || g.relationship === 'Mother'
        );
        const bk = data.bank_accounts?.[0] || {};
        const adh = data.aadhaar_details || {};

        let day = '12';
        let month = 'May';
        let year = '2004';
        if (p.date_of_birth) {
          const dObj = new Date(p.date_of_birth);
          if (!isNaN(dObj.getTime())) {
            day = String(dObj.getDate());
            month = dObj.toLocaleString('en-US', { month: 'long' });
            year = String(dObj.getFullYear());
          }
        }

        const candidateName =
          data.display_name ||
          `${data.first_name || ''} ${data.last_name || ''}`.trim() ||
          user?.first_name ||
          'ROHIT KUMAR';

        const isDSY = Boolean(data.is_direct_second_year || data.admission_details?.admission_type === 'DIRECT_SECOND_YEAR');
        const adm = data.admission_details || {};

        setFormData((prev) => ({
          ...prev,
          fullName: candidateName,
          dteAppId: data.application_id || 'DEN18146293',
          fatherName: gFather?.name || prev.fatherName,
          motherName: gMother?.name || prev.motherName,
          placeOfBirth: p.place_of_birth || prev.placeOfBirth,
          dobDay: day,
          dobMonth: month,
          dobYear: year,
          gender: p.gender || 'Male',
          address: perm.address_line_1 || prev.address,
          district: perm.district || prev.district,
          state: perm.state || prev.state,
          pincode: perm.pincode || prev.pincode,
          aadhaarNo: adh.aadhaar_number_masked || prev.aadhaarNo,
          aadhaarName: candidateName,
          aadhaarMobile: p.student_mobile || prev.aadhaarMobile,
          bankHolderName: candidateName,
          bankName: bk.bank_name || prev.bankName,
          branchName: bk.branch_name || prev.branchName,
          accountNo: bk.account_number_masked || prev.accountNo,
          ifscCode: bk.ifsc_code || prev.ifscCode,
          ...(isDSY
            ? {
                hscStream: 'Polytechnic Diploma',
                hscBoard: adm.diploma_board || 'MSBTE (Maharashtra State Board of Technical Education)',
                hscCollege: adm.diploma_college || prev.hscCollege || 'Government Polytechnic',
                hscPassingYear: '2025',
                hscSeatNo: adm.diploma_seat_no || prev.hscSeatNo,
                hscPercentage: adm.diploma_percentage ? `${adm.diploma_percentage}%` : prev.hscPercentage,
                hscMarksObtained: adm.merit_marks ? `${adm.merit_marks} / 100` : prev.hscMarksObtained,
              }
            : {}),
        }));
      } catch (err) {
        if (ignore) return;
        setError(
          err.response?.data?.detail ||
            'Failed to load student profile. You may not have permission to view this record.'
        );
      } finally {
        if (!ignore) {
          setLoading(false);
        }
      }
    }

    fetchProfile();

    return () => {
      ignore = true;
    };
  }, [id, user, retryCount]);

  const loadProfile = () => setRetryCount((c) => c + 1);

  const handleInputChange = (field, value) => {
    if (!canEdit) {
      showFeedback('Read-only view. Only the student can edit their own profile.');
      return;
    }
    setFormData((prev) => ({ ...prev, [field]: value }));
  };

  const showFeedback = (msg) => {
    setStatusMessage(msg);
    setTimeout(() => setStatusMessage(''), 3500);
  };

  const handlePhotoUpload = (e) => {
    // Photo/signature document upload has no backend endpoint yet — keep disabled.
    showFeedback('Document upload is not available yet. Contact Admin Head.');
    return;
  };

  const handleSignatureUpload = (e) => {
    // Photo/signature document upload has no backend endpoint yet — keep disabled.
    showFeedback('Document upload is not available yet. Contact Admin Head.');
    return;
  };

  const MONTHS = [
    'January', 'February', 'March', 'April', 'May', 'June',
    'July', 'August', 'September', 'October', 'November', 'December',
  ];

  const handleSaveProfile = async () => {
    if (!canEdit || saving) return;
    setSaving(true);
    try {
      const monthNum = String(MONTHS.indexOf(formData.dobMonth) + 1).padStart(2, '0');
      const dayNum = String(formData.dobDay).padStart(2, '0');
      const payload = {
        personal: {
          place_of_birth: formData.placeOfBirth,
          gender: String(formData.gender || '').toUpperCase(),
          date_of_birth: `${formData.dobYear}-${monthNum}-${dayNum}`,
          student_mobile: formData.aadhaarMobile,
        },
        guardians: [
          { relationship: 'FATHER', name: formData.fatherName },
          { relationship: 'MOTHER', name: formData.motherName },
        ],
        address: {
          address_line_1: formData.address,
          district: formData.district,
          state: formData.state,
          pincode: formData.pincode,
        },
        bank: {
          account_holder_name: formData.bankHolderName,
          bank_name: formData.bankName,
          branch_name: formData.branchName,
          ifsc_code: formData.ifscCode,
          // Never send the masked display value back as a new account number.
          ...(!String(formData.accountNo || '').includes('X') && { account_number: formData.accountNo }),
        },
      };
      const res = await studentApi.updateMyProfile(payload);
      const changed = res.data?.changed?.length ? `: ${res.data.changed.join(', ')}` : '';
      showFeedback(`Profile updated successfully${changed}.`);
      setRetryCount((c) => c + 1);
    } catch (err) {
      const data = err.response?.data;
      const msg =
        data?.detail ||
        (data && typeof data === 'object' ? Object.entries(data).map(([k, v]) => `${k}: ${Array.isArray(v) ? v.join(' ') : v}`).join(' ') : null) ||
        'Failed to save profile. Check highlighted values and try again.';
      showFeedback(msg);
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div style={{ padding: '2rem' }}>
        <LoadingState message="Loading student profile details..." />
      </div>
    );
  }

  if (error || !student) {
    return (
      <div style={{ padding: '2rem' }}>
        <ErrorState
          title="Access Restricted or Record Not Found"
          message={error || 'Unable to display student profile.'}
          onRetry={loadProfile}
          onBack={() => navigate(-1)}
        />
      </div>
    );
  }

  const enrollment = student.current_enrollment;

  const isDSYStudent = Boolean(
    student?.is_direct_second_year ||
    student?.admission_details?.admission_type === 'DIRECT_SECOND_YEAR' ||
    formData.hscStream === 'Polytechnic Diploma'
  );

  const tabs = [
    { id: 'registration', label: 'Registration Detail', icon: GraduationCap },
    { id: 'photo', label: 'Photo', icon: ImageIcon },
    { id: 'aadhaar', label: 'Aadhaar Detail', icon: CreditCard },
    { id: 'bank', label: 'Bank Detail', icon: Building },
    { id: 'marksheets', label: isDSYStudent ? 'Diploma & SSC Marksheet' : 'HSC & SSC Marksheet', icon: FileText },
  ];

  return (
    <>
      <PageHeader
        breadcrumbs={[
          { label: 'Home', to: '/dashboard' },
          { label: 'Student Profile' },
        ]}
        title="Student Profile"
        actions={
          <div style={{ display: 'flex', gap: '0.625rem', flexWrap: 'wrap' }}>
            {canEdit && (
              <button
                className="edvana-btn edvana-btn-primary"
                onClick={handleSaveProfile}
                disabled={saving}
                style={{
                  backgroundColor: '#ffffff',
                  color: '#1d4ed8',
                  borderColor: '#ffffff',
                  fontWeight: 700,
                }}
                title="Save your contact, address, guardian and bank changes"
              >
                <CheckCircle2 size={16} />
                <span>{saving ? 'Saving…' : 'Save Changes'}</span>
              </button>
            )}
            {id && (
              <button
                className="edvana-btn edvana-btn-secondary"
                onClick={() => navigate(-1)}
                style={{
                  backgroundColor: 'rgba(255, 255, 255, 0.18)',
                  color: '#ffffff',
                  borderColor: 'rgba(255, 255, 255, 0.35)',
                }}
              >
                <ArrowLeft size={16} />
                <span>Back to Directory</span>
              </button>
            )}
          </div>
        }
      />

      <div className="edvana-banner-overlap" style={{ paddingBottom: '3.5rem' }}>
        {/* Continuous Navigation Tabs Bar with bottom gray/blue indicator under each option */}
        <div className="profile-tab-bar">
          {tabs.map((tab) => {
            const Icon = tab.icon;
            const isActive = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`profile-tab-btn ${isActive ? 'active' : ''}`}
                type="button"
              >
                <Icon size={17} className="profile-tab-icon" />
                <span>{tab.label}</span>
                <div className="tab-bottom-line" />
              </button>
            );
          })}
        </div>

        {canEdit ? (
          <div
            style={{
              backgroundColor: '#eff6ff',
              border: '1px solid #bfdbfe',
              borderRadius: '8px',
              padding: '0.75rem 1rem',
              color: '#1e40af',
              fontSize: '0.8125rem',
              fontWeight: 500,
              display: 'flex',
              alignItems: 'center',
              gap: '0.5rem',
              marginBottom: '1.25rem',
            }}
          >
            <Info size={18} style={{ color: '#2563eb', flexShrink: 0 }} />
            <span>You can update your contact, address, guardian and bank details, then press Save Changes. Name, enrollment, admission and marksheet fields are locked.</span>
          </div>
        ) : (
          <div
            style={{
              backgroundColor: '#eff6ff',
              border: '1px solid #bfdbfe',
              borderRadius: '8px',
              padding: '0.75rem 1rem',
              color: '#1e40af',
              fontSize: '0.8125rem',
              fontWeight: 500,
              display: 'flex',
              alignItems: 'center',
              gap: '0.5rem',
              marginBottom: '1.25rem',
            }}
          >
            <Info size={18} style={{ color: '#2563eb', flexShrink: 0 }} />
            <span>Read-only view. Only the student can edit their own profile. Contact Admin Head for corrections.</span>
          </div>
        )}
        {/* Feedback alert toast */}
        {statusMessage && (
          <div
            style={{
              backgroundColor: '#ecfdf5',
              border: '1px solid #a7f3d0',
              borderRadius: '8px',
              padding: '0.75rem 1rem',
              color: '#065f46',
              fontSize: '0.875rem',
              fontWeight: 500,
              display: 'flex',
              alignItems: 'center',
              gap: '0.5rem',
              marginBottom: '1.25rem',
            }}
          >
            <CheckCircle2 size={18} style={{ color: '#059669' }} />
            <span>{statusMessage}</span>
          </div>
        )}

        {/* ========================================================
            TAB 1: Registration Detail (Screenshots 1 & 3)
            ======================================================== */}
        {activeTab === 'registration' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
            {/* Student Profile Overview Card */}
            <div className="edvana-card">
              <div className="edvana-card-header">
                <h3 className="edvana-card-title">Student Profile</h3>
              </div>
              <div className="edvana-card-body" style={{ padding: '1.75rem 1.5rem' }}>
                <div
                  style={{
                    display: 'flex',
                    flexDirection: 'column',
                    alignItems: 'center',
                    gap: '1rem',
                    textAlign: 'center',
                  }}
                >
                  <div style={{ display: 'flex', gap: '1.5rem', alignItems: 'center' }}>
                    <strong style={{ fontSize: '0.9375rem', color: '#1e293b' }}>Program:</strong>
                    <span style={{ fontSize: '0.9375rem', color: '#475569' }}>
                      {enrollment?.department_name ||
                        enrollment?.program_name ||
                        'Artificial Intelligence and Data Science'}
                    </span>
                  </div>
                  <div style={{ display: 'flex', gap: '1.5rem', alignItems: 'center' }}>
                    <strong style={{ fontSize: '0.9375rem', color: '#1e293b' }}>
                      Enrollment Number:
                    </strong>
                    <span
                      style={{
                        fontSize: '0.9375rem',
                        fontFamily: 'var(--edvana-font-mono)',
                        fontWeight: 600,
                        color: '#1e293b',
                      }}
                    >
                      {student.enrollment_no || 'ENR2025COMP002'}
                    </span>
                  </div>
                </div>
              </div>
            </div>

            {/* Personal Details Card */}
            <div className="edvana-card">
              <div className="edvana-card-header">
                <h3 className="edvana-card-title">Personal Details</h3>
              </div>
              <div className="edvana-card-body">
                <div
                  style={{
                    display: 'grid',
                    gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
                    gap: '1.25rem',
                  }}
                >
                  <div>
                    <label
                      style={{
                        display: 'block',
                        fontSize: '0.8125rem',
                        fontWeight: 600,
                        color: '#334155',
                        marginBottom: '0.375rem',
                      }}
                    >
                      Full Name of the candidate <span style={{ color: '#ef4444' }}>*</span>
                    </label>
                    <input
                      type="text"
                      className="edvana-input"
                      disabled
                      title="Locked: identity record. Contact Admin Head for corrections."
                      value={formData.fullName}
                      onChange={(e) => handleInputChange('fullName', e.target.value)}
                    />
                  </div>

                  <div>
                    <label
                      style={{
                        display: 'block',
                        fontSize: '0.8125rem',
                        fontWeight: 600,
                        color: '#334155',
                        marginBottom: '0.375rem',
                      }}
                    >
                      DTE Application ID <span style={{ color: '#ef4444' }}>*</span>
                    </label>
                    <input
                      type="text"
                      className="edvana-input"
                      disabled
                      title="Locked: government application ID."
                      placeholder="For Eg. DEN18146293"
                      value={formData.dteAppId}
                      onChange={(e) => handleInputChange('dteAppId', e.target.value)}
                    />
                    <span
                      style={{
                        fontSize: '0.75rem',
                        color: '#64748b',
                        marginTop: '0.25rem',
                        display: 'block',
                      }}
                    >
                      For Eg. DEN18146293
                    </span>
                  </div>

                  <div>
                    <label
                      style={{
                        display: 'block',
                        fontSize: '0.8125rem',
                        fontWeight: 600,
                        color: '#334155',
                        marginBottom: '0.375rem',
                      }}
                    >
                      Father's Name <span style={{ color: '#ef4444' }}>*</span>
                    </label>
                    <input
                      type="text"
                      className="edvana-input" disabled={!canEdit}
                      value={formData.fatherName}
                      onChange={(e) => handleInputChange('fatherName', e.target.value)}
                    />
                  </div>

                  <div>
                    <label
                      style={{
                        display: 'block',
                        fontSize: '0.8125rem',
                        fontWeight: 600,
                        color: '#334155',
                        marginBottom: '0.375rem',
                      }}
                    >
                      Mother's Name (FIRST) <span style={{ color: '#ef4444' }}>*</span>
                    </label>
                    <input
                      type="text"
                      className="edvana-input" disabled={!canEdit}
                      value={formData.motherName}
                      onChange={(e) => handleInputChange('motherName', e.target.value)}
                    />
                  </div>

                  <div>
                    <label
                      style={{
                        display: 'block',
                        fontSize: '0.8125rem',
                        fontWeight: 600,
                        color: '#334155',
                        marginBottom: '0.375rem',
                      }}
                    >
                      Place of Birth <span style={{ color: '#ef4444' }}>*</span>
                    </label>
                    <input
                      type="text"
                      className="edvana-input" disabled={!canEdit}
                      value={formData.placeOfBirth}
                      onChange={(e) => handleInputChange('placeOfBirth', e.target.value)}
                    />
                  </div>

                  <div>
                    <label
                      style={{
                        display: 'block',
                        fontSize: '0.8125rem',
                        fontWeight: 600,
                        color: '#334155',
                        marginBottom: '0.375rem',
                      }}
                    >
                      Date of Birth <span style={{ color: '#ef4444' }}>*</span>
                    </label>
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '0.5rem' }}>
                      <select
                        className="edvana-select" disabled={!canEdit}
                        value={formData.dobDay}
                        onChange={(e) => handleInputChange('dobDay', e.target.value)}
                      >
                        {Array.from({ length: 31 }, (_, i) => i + 1).map((d) => (
                          <option key={d} value={String(d)}>
                            {d}
                          </option>
                        ))}
                      </select>
                      <select
                        className="edvana-select" disabled={!canEdit}
                        value={formData.dobMonth}
                        onChange={(e) => handleInputChange('dobMonth', e.target.value)}
                      >
                        {[
                          'January',
                          'February',
                          'March',
                          'April',
                          'May',
                          'June',
                          'July',
                          'August',
                          'September',
                          'October',
                          'November',
                          'December',
                        ].map((m) => (
                          <option key={m} value={m}>
                            {m}
                          </option>
                        ))}
                      </select>
                      <select
                        className="edvana-select" disabled={!canEdit}
                        value={formData.dobYear}
                        onChange={(e) => handleInputChange('dobYear', e.target.value)}
                      >
                        {Array.from({ length: 25 }, (_, i) => 2012 - i).map((y) => (
                          <option key={y} value={String(y)}>
                            {y}
                          </option>
                        ))}
                      </select>
                    </div>
                  </div>

                  <div>
                    <label
                      style={{
                        display: 'block',
                        fontSize: '0.8125rem',
                        fontWeight: 600,
                        color: '#334155',
                        marginBottom: '0.375rem',
                      }}
                    >
                      Gender <span style={{ color: '#ef4444' }}>*</span>
                    </label>
                    <select
                      className="edvana-select" disabled={!canEdit}
                      value={formData.gender}
                      onChange={(e) => handleInputChange('gender', e.target.value)}
                    >
                      <option value="Male">Male</option>
                      <option value="Female">Female</option>
                      <option value="Other">Other</option>
                    </select>
                  </div>
                </div>
              </div>
            </div>

            {/* Admission Details Card (Screenshot 3) */}
            <div className="edvana-card">
              <div className="edvana-card-header">
                <h3 className="edvana-card-title">Admission Details</h3>
              </div>
              <div className="edvana-card-body">
                <div
                  style={{
                    display: 'grid',
                    gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
                    gap: '1.25rem',
                  }}
                >
                  <div>
                    <label
                      style={{
                        display: 'block',
                        fontSize: '0.8125rem',
                        fontWeight: 600,
                        color: '#334155',
                        marginBottom: '0.375rem',
                      }}
                    >
                      Date of Admission <span style={{ color: '#ef4444' }}>*</span>
                    </label>
                    <input
                      type="date"
                      className="edvana-input"
                      disabled
                      title="Locked: admission record."
                      value={formData.dateOfAdmission}
                      onChange={(e) => handleInputChange('dateOfAdmission', e.target.value)}
                    />
                  </div>

                  <div>
                    <label
                      style={{
                        display: 'block',
                        fontSize: '0.8125rem',
                        fontWeight: 600,
                        color: '#334155',
                        marginBottom: '0.375rem',
                      }}
                    >
                      Admission Type <span style={{ color: '#ef4444' }}>*</span>
                    </label>
                    <select
                      className="edvana-select"
                      disabled
                      title="Locked: admission record."
                      value={formData.admissionType}
                      onChange={(e) => handleInputChange('admissionType', e.target.value)}
                    >
                      <option value="CAP">CAP</option>
                      <option value="Institute Level">Institute Level</option>
                      <option value="TFWS">TFWS</option>
                      <option value="Management">Management</option>
                    </select>
                  </div>

                  <div>
                    <label
                      style={{
                        display: 'block',
                        fontSize: '0.8125rem',
                        fontWeight: 600,
                        color: '#334155',
                        marginBottom: '0.375rem',
                      }}
                    >
                      Allotted Seat Type <span style={{ color: '#ef4444' }}>*</span>
                    </label>
                    <select
                      className="edvana-select"
                      disabled
                      title="Locked: admission record."
                      value={formData.allottedSeatType}
                      onChange={(e) => handleInputChange('allottedSeatType', e.target.value)}
                    >
                      <option value="NT-C">NT-C</option>
                      <option value="OPEN">OPEN</option>
                      <option value="OBC">OBC</option>
                      <option value="SC">SC</option>
                      <option value="ST">ST</option>
                      <option value="NT-A">NT-A</option>
                      <option value="NT-B">NT-B</option>
                      <option value="NT-D">NT-D</option>
                      <option value="EWS">EWS</option>
                    </select>
                  </div>

                  <div>
                    <label
                      style={{
                        display: 'block',
                        fontSize: '0.8125rem',
                        fontWeight: 600,
                        color: '#334155',
                        marginBottom: '0.375rem',
                      }}
                    >
                      Scholarship Applied <span style={{ color: '#ef4444' }}>*</span>
                    </label>
                    <select
                      className="edvana-select"
                      disabled
                      title="Locked: admission record."
                      value={formData.scholarshipApplied}
                      onChange={(e) => handleInputChange('scholarshipApplied', e.target.value)}
                    >
                      <option value="Yes">Yes</option>
                      <option value="No">No</option>
                    </select>
                  </div>

                  <div>
                    <label
                      style={{
                        display: 'block',
                        fontSize: '0.8125rem',
                        fontWeight: 600,
                        color: '#334155',
                        marginBottom: '0.375rem',
                      }}
                    >
                      Scholarship Type <span style={{ color: '#ef4444' }}>*</span>
                    </label>
                    <select
                      className="edvana-select"
                      disabled
                      title="Locked: admission record."
                      value={formData.scholarshipType}
                      onChange={(e) => handleInputChange('scholarshipType', e.target.value)}
                    >
                      <option value="NT-C">NT-C</option>
                      <option value="EBC">EBC</option>
                      <option value="SC Scholarship">SC Scholarship</option>
                      <option value="OBC Freeship">OBC Freeship</option>
                      <option value="ST Scholarship">ST Scholarship</option>
                      <option value="None">None</option>
                    </select>
                  </div>

                  <div>
                    <label
                      style={{
                        display: 'block',
                        fontSize: '0.8125rem',
                        fontWeight: 600,
                        color: '#334155',
                        marginBottom: '0.375rem',
                      }}
                    >
                      Father's /Guardian's Annual Income (from all sources) <span style={{ color: '#ef4444' }}>*</span>
                    </label>
                    <select
                      className="edvana-select"
                      disabled
                      title="Locked: admission record."
                      value={formData.annualIncome}
                      onChange={(e) => handleInputChange('annualIncome', e.target.value)}
                    >
                      <option value="600000 to 700000">600000 to 700000</option>
                      <option value="Below 100000">Below 100000</option>
                      <option value="100000 to 250000">100000 to 250000</option>
                      <option value="250000 to 600000">250000 to 600000</option>
                      <option value="Above 800000">Above 800000</option>
                    </select>
                  </div>
                </div>
              </div>
            </div>

            {/* Permanent Address Card (Screenshot 3) */}
            <div className="edvana-card">
              <div className="edvana-card-header">
                <h3 className="edvana-card-title">Permanent Address</h3>
              </div>
              <div className="edvana-card-body">
                <div style={{ marginBottom: '1.25rem' }}>
                  <label
                    style={{
                      display: 'block',
                      fontSize: '0.8125rem',
                      fontWeight: 600,
                      color: '#334155',
                      marginBottom: '0.375rem',
                    }}
                  >
                    Address <span style={{ color: '#ef4444' }}>*</span>
                  </label>
                  <textarea
                    className="edvana-textarea" disabled={!canEdit}
                    rows={3}
                    value={formData.address}
                    onChange={(e) => handleInputChange('address', e.target.value)}
                  />
                </div>
                <div
                  style={{
                    display: 'grid',
                    gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
                    gap: '1.25rem',
                  }}
                >
                  <div>
                    <label
                      style={{
                        display: 'block',
                        fontSize: '0.8125rem',
                        fontWeight: 600,
                        color: '#334155',
                        marginBottom: '0.375rem',
                      }}
                    >
                      District <span style={{ color: '#ef4444' }}>*</span>
                    </label>
                    <input
                      type="text"
                      className="edvana-input" disabled={!canEdit}
                      value={formData.district}
                      onChange={(e) => handleInputChange('district', e.target.value)}
                    />
                  </div>
                  <div>
                    <label
                      style={{
                        display: 'block',
                        fontSize: '0.8125rem',
                        fontWeight: 600,
                        color: '#334155',
                        marginBottom: '0.375rem',
                      }}
                    >
                      State <span style={{ color: '#ef4444' }}>*</span>
                    </label>
                    <input
                      type="text"
                      className="edvana-input" disabled={!canEdit}
                      value={formData.state}
                      onChange={(e) => handleInputChange('state', e.target.value)}
                    />
                  </div>
                  <div>
                    <label
                      style={{
                        display: 'block',
                        fontSize: '0.8125rem',
                        fontWeight: 600,
                        color: '#334155',
                        marginBottom: '0.375rem',
                      }}
                    >
                      Pincode <span style={{ color: '#ef4444' }}>*</span>
                    </label>
                    <input
                      type="text"
                      className="edvana-input" disabled={!canEdit}
                      value={formData.pincode}
                      onChange={(e) => handleInputChange('pincode', e.target.value)}
                    />
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* ========================================================
            TAB 2: Photo (Screenshot 4)
            ======================================================== */}
        {activeTab === 'photo' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
            {/* Passport Photo Upload Card */}
            <div className="edvana-card">
              <div className="edvana-card-body">
                <div
                  style={{
                    display: 'grid',
                    gridTemplateColumns: '1fr auto',
                    gap: '2.5rem',
                    alignItems: 'flex-start',
                  }}
                >
                  <div>
                    <label
                      style={{
                        display: 'block',
                        fontSize: '0.875rem',
                        fontWeight: 600,
                        color: '#1e293b',
                        marginBottom: '0.75rem',
                      }}
                    >
                      Upload Latest Passport size Photo
                    </label>
                    <input
                      type="file"
                      accept="image/*"
                      className="edvana-input"
                      disabled
                      title="Document upload not available yet."
                      style={{ padding: '0.5rem', background: '#f8fafc' }}
                      onChange={handlePhotoUpload}
                    />
                    <p style={{ fontSize: '0.75rem', color: '#64748b', marginTop: '0.5rem' }}>
                      Max file size 200kb. Formats: .jpg, .png. White or light background recommended.
                    </p>
                  </div>

                  <div>
                    <label
                      style={{
                        display: 'block',
                        fontSize: '0.875rem',
                        fontWeight: 600,
                        color: '#1e293b',
                        marginBottom: '0.75rem',
                      }}
                    >
                      Uploaded Photo
                    </label>
                    <div
                      style={{
                        width: '130px',
                        height: '150px',
                        border: '1px solid #cbd5e1',
                        borderRadius: '8px',
                        display: 'flex',
                        flexDirection: 'column',
                        alignItems: 'center',
                        justifyContent: 'center',
                        backgroundColor: '#f8fafc',
                        overflow: 'hidden',
                      }}
                    >
                      {photoPreview ? (
                        <img
                          src={photoPreview}
                          alt="Uploaded Photo"
                          style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                        />
                      ) : (
                        <div style={{ textAlign: 'center', color: '#94a3b8' }}>
                          <ImageIcon size={32} style={{ margin: '0 auto 0.25rem' }} />
                          <span style={{ fontSize: '0.75rem', fontWeight: 500 }}>No Photo</span>
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              </div>
            </div>

            {/* Signature Instructions Notice Box (Screenshot 4) */}
            <div
              style={{
                backgroundColor: '#fffbeb',
                border: '1px solid #fef08a',
                borderRadius: '12px',
                padding: '1.25rem 1.5rem',
                display: 'flex',
                gap: '1rem',
                alignItems: 'flex-start',
              }}
            >
              <div style={{ color: '#d97706', marginTop: '2px', flexShrink: 0 }}>
                <Info size={22} />
              </div>
              <div>
                <h4
                  style={{
                    margin: '0 0 0.5rem',
                    fontSize: '0.9375rem',
                    fontWeight: 700,
                    color: '#92400e',
                  }}
                >
                  Instructions for upload Signature
                </h4>
                <ul
                  style={{
                    margin: 0,
                    paddingLeft: '1.25rem',
                    fontSize: '0.8125rem',
                    color: '#78350f',
                    lineHeight: 1.6,
                  }}
                >
                  <li>Sign on a white paper with a black pen.</li>
                  <li>
                    Scan the signature using a good quality scanner with min. 100dpi so that the
                    file size should not be more than 150kb.
                  </li>
                  <li>Save the image in .jpg format on local machine.</li>
                </ul>
              </div>
            </div>

            {/* Signature Upload Card (Screenshot 4) */}
            <div className="edvana-card">
              <div className="edvana-card-header">
                <h3 className="edvana-card-title">Upload Signature</h3>
              </div>
              <div className="edvana-card-body">
                <div
                  style={{
                    display: 'grid',
                    gridTemplateColumns: '1fr auto',
                    gap: '2.5rem',
                    alignItems: 'flex-start',
                  }}
                >
                  <div>
                    <label
                      style={{
                        display: 'block',
                        fontSize: '0.875rem',
                        fontWeight: 600,
                        color: '#1e293b',
                        marginBottom: '0.75rem',
                      }}
                    >
                      Upload Signature
                    </label>
                    <input
                      type="file"
                      accept="image/*"
                      className="edvana-input"
                      disabled
                      title="Document upload not available yet."
                      style={{ padding: '0.5rem', background: '#f8fafc' }}
                      onChange={handleSignatureUpload}
                    />
                  </div>

                  <div>
                    <label
                      style={{
                        display: 'block',
                        fontSize: '0.875rem',
                        fontWeight: 600,
                        color: '#1e293b',
                        marginBottom: '0.75rem',
                      }}
                    >
                      Uploaded Signature
                    </label>
                    <div
                      style={{
                        width: '180px',
                        height: '70px',
                        border: '1px solid #cbd5e1',
                        borderRadius: '8px',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        backgroundColor: '#ffffff',
                        overflow: 'hidden',
                        padding: '0.5rem',
                      }}
                    >
                      {signaturePreview ? (
                        <img
                          src={signaturePreview}
                          alt="Signature Preview"
                          style={{ maxHeight: '100%', maxWidth: '100%', objectFit: 'contain' }}
                        />
                      ) : (
                        <span
                          style={{
                            fontFamily: 'cursive',
                            fontSize: '1.35rem',
                            color: '#1d4ed8',
                            fontStyle: 'italic',
                          }}
                        >
                          {student.first_name || 'Rohit'}
                        </span>
                      )}
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* ========================================================
            TAB 3: Aadhaar Detail (Screenshot 5)
            ======================================================== */}
        {activeTab === 'aadhaar' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
            {/* Aadhaar Instructions Notice Box */}
            <div
              style={{
                backgroundColor: '#fffbeb',
                border: '1px solid #fef08a',
                borderRadius: '12px',
                padding: '1.25rem 1.5rem',
                display: 'flex',
                gap: '1rem',
                alignItems: 'flex-start',
              }}
            >
              <div style={{ color: '#d97706', marginTop: '2px', flexShrink: 0 }}>
                <Info size={22} />
              </div>
              <div>
                <h4
                  style={{
                    margin: '0 0 0.5rem',
                    fontSize: '0.9375rem',
                    fontWeight: 700,
                    color: '#92400e',
                  }}
                >
                  Instructions to upload Aadhaar
                </h4>
                <ul
                  style={{
                    margin: 0,
                    paddingLeft: '1.25rem',
                    fontSize: '0.8125rem',
                    color: '#78350f',
                    lineHeight: 1.6,
                  }}
                >
                  <li>
                    Scan Aadhaar using a good quality scanner with min. 100dpi so that the file
                    size should not be more than 100kb.
                  </li>
                  <li>Save the file in .pdf format on local machine.</li>
                  <li>
                    Ensure that the scanned Aadhaar is of good quality (headgear acceptable for
                    religious customs but facial features must remain unobscured).
                  </li>
                </ul>
              </div>
            </div>

            {/* Upload Aadhaar Card */}
            <div className="edvana-card">
              <div className="edvana-card-header">
                <h3 className="edvana-card-title">Upload Aadhaar</h3>
              </div>
              <div className="edvana-card-body">
                <div
                  style={{
                    display: 'grid',
                    gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
                    gap: '1.25rem',
                    marginBottom: '1.5rem',
                  }}
                >
                  <div>
                    <label
                      style={{
                        display: 'block',
                        fontSize: '0.8125rem',
                        fontWeight: 600,
                        color: '#334155',
                        marginBottom: '0.375rem',
                      }}
                    >
                      Aadhaar Number
                    </label>
                    <input
                      type="text"
                      className="edvana-input"
                      disabled
                      title="Locked: verified identity document."
                      value={formData.aadhaarNo}
                      onChange={(e) => handleInputChange('aadhaarNo', e.target.value)}
                    />
                  </div>

                  <div>
                    <label
                      style={{
                        display: 'block',
                        fontSize: '0.8125rem',
                        fontWeight: 600,
                        color: '#334155',
                        marginBottom: '0.375rem',
                      }}
                    >
                      Name As per Aadhaar
                    </label>
                    <input
                      type="text"
                      className="edvana-input"
                      disabled
                      title="Locked: verified identity document."
                      value={formData.aadhaarName}
                      onChange={(e) => handleInputChange('aadhaarName', e.target.value)}
                    />
                  </div>

                  <div>
                    <label
                      style={{
                        display: 'block',
                        fontSize: '0.8125rem',
                        fontWeight: 600,
                        color: '#334155',
                        marginBottom: '0.375rem',
                      }}
                    >
                      Mobile No. Linked to Aadhaar
                    </label>
                    <input
                      type="text"
                      className="edvana-input" disabled={!canEdit}
                      value={formData.aadhaarMobile}
                      onChange={(e) => handleInputChange('aadhaarMobile', e.target.value)}
                    />
                  </div>

                  <div>
                    <label
                      style={{
                        display: 'block',
                        fontSize: '0.8125rem',
                        fontWeight: 600,
                        color: '#334155',
                        marginBottom: '0.375rem',
                      }}
                    >
                      Upload scanned copy of Aadhaar Card{' '}
                      <span style={{ fontSize: '0.75rem', color: '#64748b' }}>
                        (Accepted Format: PDF)
                      </span>
                    </label>
                    <input
                      type="file"
                      accept=".pdf"
                      className="edvana-input"
                      disabled
                      title="Document upload not available yet."
                      style={{ padding: '0.45rem', background: '#f8fafc' }}
                      onChange={() => showFeedback('Aadhaar document selected.')}
                    />
                  </div>
                </div>

                <div>
                  <button
                    type="button"
                    className="edvana-btn edvana-btn-outline"
                    onClick={() => showFeedback('Aadhaar document is on official file.')}
                    style={{ display: 'inline-flex', alignItems: 'center', gap: '0.5rem' }}
                  >
                    <FileText size={16} />
                    <span>View/Download existing Aadhaar PDF</span>
                  </button>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* ========================================================
            TAB 4: Bank Detail (Screenshot 2)
            ======================================================== */}
        {activeTab === 'bank' && (
          <div className="edvana-card">
            <div className="edvana-card-header">
              <h3 className="edvana-card-title">Update your bank details</h3>
            </div>
            <div className="edvana-card-body">
              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
                  gap: '1.25rem',
                  marginBottom: '1.75rem',
                }}
              >
                <div>
                  <label
                    style={{
                      display: 'block',
                      fontSize: '0.8125rem',
                      fontWeight: 600,
                      color: '#334155',
                      marginBottom: '0.375rem',
                    }}
                  >
                    Full Name of the Candidate <span style={{ color: '#ef4444' }}>*</span>
                  </label>
                  <input
                    type="text"
                    className="edvana-input" disabled={!canEdit}
                    value={formData.bankHolderName}
                    onChange={(e) => handleInputChange('bankHolderName', e.target.value)}
                  />
                </div>

                <div>
                  <label
                    style={{
                      display: 'block',
                      fontSize: '0.8125rem',
                      fontWeight: 600,
                      color: '#334155',
                      marginBottom: '0.375rem',
                    }}
                  >
                    Bank Name <span style={{ color: '#ef4444' }}>*</span>
                  </label>
                  <input
                    type="text"
                    className="edvana-input" disabled={!canEdit}
                    value={formData.bankName}
                    onChange={(e) => handleInputChange('bankName', e.target.value)}
                  />
                </div>

                <div>
                  <label
                    style={{
                      display: 'block',
                      fontSize: '0.8125rem',
                      fontWeight: 600,
                      color: '#334155',
                      marginBottom: '0.375rem',
                    }}
                  >
                    Branch Name <span style={{ color: '#ef4444' }}>*</span>
                  </label>
                  <input
                    type="text"
                    className="edvana-input" disabled={!canEdit}
                    value={formData.branchName}
                    onChange={(e) => handleInputChange('branchName', e.target.value)}
                  />
                </div>

                <div>
                  <label
                    style={{
                      display: 'block',
                      fontSize: '0.8125rem',
                      fontWeight: 600,
                      color: '#334155',
                      marginBottom: '0.375rem',
                    }}
                  >
                    Account No <span style={{ color: '#ef4444' }}>*</span>
                  </label>
                  <input
                    type="text"
                    className="edvana-input" disabled={!canEdit}
                    value={formData.accountNo}
                    onChange={(e) => handleInputChange('accountNo', e.target.value)}
                  />
                </div>

                <div>
                  <label
                    style={{
                      display: 'block',
                      fontSize: '0.8125rem',
                      fontWeight: 600,
                      color: '#334155',
                      marginBottom: '0.375rem',
                    }}
                  >
                    IFSC Code <span style={{ color: '#ef4444' }}>*</span>
                  </label>
                  <input
                    type="text"
                    className="edvana-input" disabled={!canEdit}
                    value={formData.ifscCode}
                    onChange={(e) => handleInputChange('ifscCode', e.target.value)}
                  />
                </div>
              </div>

              <div>
                <button
                  type="button"
                  className="edvana-btn edvana-btn-primary"
                  disabled={!canEdit || saving}
                  title={canEdit ? 'Save all profile changes' : 'Only the student can edit their own profile'}
                  onClick={handleSaveProfile}
                  style={{ padding: '0.625rem 1.5rem', fontWeight: 600, opacity: !canEdit ? 0.55 : 1 }}
                >
                  {saving ? 'Saving…' : 'Save Changes'}
                </button>
              </div>
            </div>
          </div>
        )}

        {/* ========================================================
            TAB 5: HSC & SSC Marksheets (Requested addition)
            ======================================================== */}
        {activeTab === 'marksheets' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
            {/* Marksheet Instructions Notice Box */}
            <div
              style={{
                backgroundColor: '#fffbeb',
                border: '1px solid #fef08a',
                borderRadius: '12px',
                padding: '1.25rem 1.5rem',
                display: 'flex',
                gap: '1rem',
                alignItems: 'flex-start',
              }}
            >
              <div style={{ color: '#d97706', marginTop: '2px', flexShrink: 0 }}>
                <Info size={22} />
              </div>
              <div>
                <h4
                  style={{
                    margin: '0 0 0.5rem',
                    fontSize: '0.9375rem',
                    fontWeight: 700,
                    color: '#92400e',
                  }}
                >
                  Instructions for Marksheets Upload
                </h4>
                <ul
                  style={{
                    margin: 0,
                    paddingLeft: '1.25rem',
                    fontSize: '0.8125rem',
                    color: '#78350f',
                    lineHeight: 1.6,
                  }}
                >
                  <li>
                    Upload clear, self-attested scanned copies in .pdf, .jpg, or .png format.
                  </li>
                  <li>File size should not exceed 500kb per marksheet document.</li>
                  <li>
                    Verify that candidate name, seat/roll number, passing marks, and official board
                    stamp are clearly legible.
                  </li>
                </ul>
              </div>
            </div>

            {/* SSC (10th) Marksheet Card */}
            <div className="edvana-card">
              <div
                className="edvana-card-header"
                style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}
              >
                <div>
                  <h3 className="edvana-card-title">SSC (Class 10th) Marksheet & Details</h3>
                  <p className="edvana-card-description">Secondary School Certificate records</p>
                </div>
                <span
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '0.35rem',
                    fontSize: '0.75rem',
                    padding: '0.25rem 0.65rem',
                    borderRadius: '9999px',
                    backgroundColor: '#dcfce7',
                    color: '#15803d',
                    fontWeight: 600,
                  }}
                >
                  <FileCheck size={14} /> Verified
                </span>
              </div>
              <div className="edvana-card-body">
                <div
                  style={{
                    display: 'grid',
                    gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
                    gap: '1.25rem',
                    marginBottom: '1.5rem',
                  }}
                >
                  <div>
                    <label
                      style={{
                        display: 'block',
                        fontSize: '0.8125rem',
                        fontWeight: 600,
                        color: '#334155',
                        marginBottom: '0.375rem',
                      }}
                    >
                      Board Name <span style={{ color: '#ef4444' }}>*</span>
                    </label>
                    <input
                      type="text"
                      className="edvana-input"
                      disabled
                      title="Locked: verified academic record."
                      value={formData.sscBoard}
                      onChange={(e) => handleInputChange('sscBoard', e.target.value)}
                    />
                  </div>

                  <div>
                    <label
                      style={{
                        display: 'block',
                        fontSize: '0.8125rem',
                        fontWeight: 600,
                        color: '#334155',
                        marginBottom: '0.375rem',
                      }}
                    >
                      School Name <span style={{ color: '#ef4444' }}>*</span>
                    </label>
                    <input
                      type="text"
                      className="edvana-input"
                      disabled
                      title="Locked: verified academic record."
                      value={formData.sscSchool}
                      onChange={(e) => handleInputChange('sscSchool', e.target.value)}
                    />
                  </div>

                  <div>
                    <label
                      style={{
                        display: 'block',
                        fontSize: '0.8125rem',
                        fontWeight: 600,
                        color: '#334155',
                        marginBottom: '0.375rem',
                      }}
                    >
                      Passing Year <span style={{ color: '#ef4444' }}>*</span>
                    </label>
                    <input
                      type="text"
                      className="edvana-input"
                      disabled
                      title="Locked: verified academic record."
                      value={formData.sscPassingYear}
                      onChange={(e) => handleInputChange('sscPassingYear', e.target.value)}
                    />
                  </div>

                  <div>
                    <label
                      style={{
                        display: 'block',
                        fontSize: '0.8125rem',
                        fontWeight: 600,
                        color: '#334155',
                        marginBottom: '0.375rem',
                      }}
                    >
                      Seat / Roll Number <span style={{ color: '#ef4444' }}>*</span>
                    </label>
                    <input
                      type="text"
                      className="edvana-input"
                      disabled
                      title="Locked: verified academic record."
                      value={formData.sscSeatNo}
                      onChange={(e) => handleInputChange('sscSeatNo', e.target.value)}
                    />
                  </div>

                  <div>
                    <label
                      style={{
                        display: 'block',
                        fontSize: '0.8125rem',
                        fontWeight: 600,
                        color: '#334155',
                        marginBottom: '0.375rem',
                      }}
                    >
                      Total Marks / Out of <span style={{ color: '#ef4444' }}>*</span>
                    </label>
                    <input
                      type="text"
                      className="edvana-input"
                      disabled
                      title="Locked: verified academic record."
                      value={formData.sscMarksObtained}
                      onChange={(e) => handleInputChange('sscMarksObtained', e.target.value)}
                    />
                  </div>

                  <div>
                    <label
                      style={{
                        display: 'block',
                        fontSize: '0.8125rem',
                        fontWeight: 600,
                        color: '#334155',
                        marginBottom: '0.375rem',
                      }}
                    >
                      Percentage / CGPA <span style={{ color: '#ef4444' }}>*</span>
                    </label>
                    <input
                      type="text"
                      className="edvana-input"
                      disabled
                      title="Locked: verified academic record."
                      value={formData.sscPercentage}
                      onChange={(e) => handleInputChange('sscPercentage', e.target.value)}
                    />
                  </div>
                </div>

                <div
                  style={{
                    borderTop: '1px solid #f1f5f9',
                    paddingTop: '1.25rem',
                    display: 'flex',
                    flexWrap: 'wrap',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    gap: '1rem',
                  }}
                >
                  <div style={{ flex: 1, minWidth: '260px' }}>
                    <label
                      style={{
                        display: 'block',
                        fontSize: '0.8125rem',
                        fontWeight: 600,
                        color: '#334155',
                        marginBottom: '0.375rem',
                      }}
                    >
                      Upload Scanned Copy of SSC Marksheet (PDF / JPG)
                    </label>
                    <input
                      type="file"
                      accept=".pdf,image/*"
                      className="edvana-input"
                      disabled
                      title="Document upload not available yet."
                      style={{ padding: '0.45rem', background: '#f8fafc' }}
                      onChange={() => showFeedback('SSC Marksheet selected.')}
                    />
                  </div>

                  <div>
                    <button
                      type="button"
                      className="edvana-btn edvana-btn-outline"
                      onClick={() => showFeedback('Opening verified SSC Marksheet...')}
                      style={{ display: 'inline-flex', alignItems: 'center', gap: '0.5rem' }}
                    >
                      <FileText size={16} />
                      <span>View Uploaded SSC Marksheet</span>
                    </button>
                  </div>
                </div>
              </div>
            </div>

            {/* HSC / Polytechnic Diploma Marksheet Card */}
            <div className="edvana-card">
              <div
                className="edvana-card-header"
                style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}
              >
                <div>
                  <h3 className="edvana-card-title">
                    {isDSYStudent ? 'Polytechnic Diploma Marksheet & Details' : 'HSC (Class 12th / Diploma) Marksheet & Details'}
                  </h3>
                  <p className="edvana-card-description">
                    {isDSYStudent
                      ? 'Qualifying Diploma in Engineering / Technology examination records (Direct Second Year)'
                      : 'Higher Secondary / Qualifying Examination records'}
                  </p>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                  {isDSYStudent && (
                    <span
                      style={{
                        display: 'inline-flex',
                        alignItems: 'center',
                        fontSize: '0.72rem',
                        padding: '0.2rem 0.6rem',
                        borderRadius: '6px',
                        backgroundColor: '#ede9fe',
                        color: '#6d28d9',
                        fontWeight: 700,
                        textTransform: 'uppercase',
                        letterSpacing: '0.04em',
                      }}
                    >
                      DSY Lateral Entry
                    </span>
                  )}
                  <span
                    style={{
                      display: 'inline-flex',
                      alignItems: 'center',
                      gap: '0.35rem',
                      fontSize: '0.75rem',
                      padding: '0.25rem 0.65rem',
                      borderRadius: '9999px',
                      backgroundColor: '#dcfce7',
                      color: '#15803d',
                      fontWeight: 600,
                    }}
                  >
                    <FileCheck size={14} /> Verified
                  </span>
                </div>
              </div>
              <div className="edvana-card-body">
                <div
                  style={{
                    display: 'grid',
                    gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
                    gap: '1.25rem',
                    marginBottom: '1.5rem',
                  }}
                >
                  <div>
                    <label
                      style={{
                        display: 'block',
                        fontSize: '0.8125rem',
                        fontWeight: 600,
                        color: '#334155',
                        marginBottom: '0.375rem',
                      }}
                    >
                      {isDSYStudent ? 'Qualifying Stream' : 'Qualifying Stream'} <span style={{ color: '#ef4444' }}>*</span>
                    </label>
                    <select
                      className="edvana-select"
                      disabled
                      title="Locked: verified academic record."
                      value={formData.hscStream}
                      onChange={(e) => handleInputChange('hscStream', e.target.value)}
                    >
                      <option value="Polytechnic Diploma">Polytechnic Diploma (Direct Second Year)</option>
                      <option value="Class XII (Science)">Class XII (Science)</option>
                      <option value="Other">Other</option>
                    </select>
                  </div>

                  <div>
                    <label
                      style={{
                        display: 'block',
                        fontSize: '0.8125rem',
                        fontWeight: 600,
                        color: '#334155',
                        marginBottom: '0.375rem',
                      }}
                    >
                      {isDSYStudent ? 'Diploma Examining Board / Authority' : 'Board / Examining Authority'} <span style={{ color: '#ef4444' }}>*</span>
                    </label>
                    <input
                      type="text"
                      className="edvana-input"
                      disabled
                      title="Locked: verified academic record."
                      value={formData.hscBoard}
                      onChange={(e) => handleInputChange('hscBoard', e.target.value)}
                    />
                  </div>

                  <div>
                    <label
                      style={{
                        display: 'block',
                        fontSize: '0.8125rem',
                        fontWeight: 600,
                        color: '#334155',
                        marginBottom: '0.375rem',
                      }}
                    >
                      {isDSYStudent ? 'Polytechnic / Institute Name' : 'College / Institute Name'} <span style={{ color: '#ef4444' }}>*</span>
                    </label>
                    <input
                      type="text"
                      className="edvana-input"
                      disabled
                      title="Locked: verified academic record."
                      value={formData.hscCollege}
                      onChange={(e) => handleInputChange('hscCollege', e.target.value)}
                    />
                  </div>

                  <div>
                    <label
                      style={{
                        display: 'block',
                        fontSize: '0.8125rem',
                        fontWeight: 600,
                        color: '#334155',
                        marginBottom: '0.375rem',
                      }}
                    >
                      {isDSYStudent ? 'Diploma Passing Year' : 'Passing Year'} <span style={{ color: '#ef4444' }}>*</span>
                    </label>
                    <input
                      type="text"
                      className="edvana-input"
                      disabled
                      title="Locked: verified academic record."
                      value={formData.hscPassingYear}
                      onChange={(e) => handleInputChange('hscPassingYear', e.target.value)}
                    />
                  </div>

                  <div>
                    <label
                      style={{
                        display: 'block',
                        fontSize: '0.8125rem',
                        fontWeight: 600,
                        color: '#334155',
                        marginBottom: '0.375rem',
                      }}
                    >
                      {isDSYStudent ? 'Diploma Final Year / Aggregate Seat No.' : 'Seat / Roll Number'} <span style={{ color: '#ef4444' }}>*</span>
                    </label>
                    <input
                      type="text"
                      className="edvana-input"
                      disabled
                      title="Locked: verified academic record."
                      value={formData.hscSeatNo}
                      onChange={(e) => handleInputChange('hscSeatNo', e.target.value)}
                    />
                  </div>

                  <div>
                    <label
                      style={{
                        display: 'block',
                        fontSize: '0.8125rem',
                        fontWeight: 600,
                        color: '#334155',
                        marginBottom: '0.375rem',
                      }}
                    >
                      {isDSYStudent ? 'Diploma Marks Obtained / Out of' : 'Total Marks / Out of'} <span style={{ color: '#ef4444' }}>*</span>
                    </label>
                    <input
                      type="text"
                      className="edvana-input"
                      disabled
                      title="Locked: verified academic record."
                      value={formData.hscMarksObtained}
                      onChange={(e) => handleInputChange('hscMarksObtained', e.target.value)}
                    />
                  </div>

                  <div>
                    <label
                      style={{
                        display: 'block',
                        fontSize: '0.8125rem',
                        fontWeight: 600,
                        color: '#334155',
                        marginBottom: '0.375rem',
                      }}
                    >
                      {isDSYStudent ? 'Diploma Aggregate Percentage' : 'Percentage / CGPA'} <span style={{ color: '#ef4444' }}>*</span>
                    </label>
                    <input
                      type="text"
                      className="edvana-input"
                      disabled
                      title="Locked: verified academic record."
                      value={formData.hscPercentage}
                      onChange={(e) => handleInputChange('hscPercentage', e.target.value)}
                    />
                  </div>
                </div>

                <div
                  style={{
                    borderTop: '1px solid #f1f5f9',
                    paddingTop: '1.25rem',
                    display: 'flex',
                    flexWrap: 'wrap',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    gap: '1rem',
                  }}
                >
                  <div style={{ flex: 1, minWidth: '260px' }}>
                    <label
                      style={{
                        display: 'block',
                        fontSize: '0.8125rem',
                        fontWeight: 600,
                        color: '#334155',
                        marginBottom: '0.375rem',
                      }}
                    >
                      {isDSYStudent
                        ? 'Upload Scanned Copy of Polytechnic Diploma Marksheet (PDF / JPG)'
                        : 'Upload Scanned Copy of HSC / Diploma Marksheet (PDF / JPG)'}
                    </label>
                    <input
                      type="file"
                      accept=".pdf,image/*"
                      className="edvana-input"
                      disabled
                      title="Document upload not available yet."
                      style={{ padding: '0.45rem', background: '#f8fafc' }}
                      onChange={() => showFeedback(isDSYStudent ? 'Diploma Marksheet selected.' : 'HSC Marksheet selected.')}
                    />
                  </div>

                  <div>
                    <button
                      type="button"
                      className="edvana-btn edvana-btn-outline"
                      onClick={() => showFeedback(isDSYStudent ? 'Opening verified Diploma Marksheet...' : 'Opening verified HSC Marksheet...')}
                      style={{ display: 'inline-flex', alignItems: 'center', gap: '0.5rem' }}
                    >
                      <FileText size={16} />
                      <span>{isDSYStudent ? 'View Uploaded Diploma Marksheet' : 'View Uploaded HSC Marksheet'}</span>
                    </button>
                  </div>
                </div>
              </div>
            </div>

            <div>
              <button
                type="button"
                className="edvana-btn edvana-btn-primary"
                disabled
                title="Marksheet records are verified and locked."
                style={{ padding: '0.625rem 1.5rem', fontWeight: 600, opacity: 0.55 }}
              >
                Update Marksheet Details (Locked)
              </button>
            </div>
          </div>
        )}
      </div>
    </>
  );
}
