import { useState, useEffect, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import studentApi from '../../api/studentApi';
import { LoadingState, ErrorState } from '../../components/common/StateDisplays';
import PageHeader from '../../components/common/PageHeader';
import Modal from '../../components/common/Modal';
import PasswordChangeForm from '../../components/auth/PasswordChangeForm';
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
  Lock,
} from 'lucide-react';

// Scholarship types mirror backend Student.ScholarshipType codes.
// Server enforces: Applied=No -> NONE; Applied=Yes requires a real type.
const SCHOLARSHIP_OPTIONS = [
  { value: 'NONE', label: 'None' },
  { value: 'EBC', label: 'EBC (Economically Backward Class)' },
  { value: 'OBC_FREESHIP', label: 'OBC Freeship' },
  { value: 'SC', label: 'SC Scholarship' },
  { value: 'ST', label: 'ST Scholarship' },
  { value: 'NT_C', label: 'NT-C' },
  { value: 'MINORITY', label: 'Minority Scholarship' },
];
const SCHOLARSHIP_CODE_VALUES = new Set(SCHOLARSHIP_OPTIONS.map((o) => o.value));
// Map legacy label values (previously stored/selected) to codes.
const normalizeScholarshipLabel = (v) => {
  const key = String(v || '').trim().toUpperCase();
  const map = {
    'NONE': 'NONE', '': 'NONE',
    'EBC': 'EBC',
    'OBC FREESHIP': 'OBC_FREESHIP', 'OBC_FREESHIP': 'OBC_FREESHIP',
    'SC SCHOLARSHIP': 'SC', 'SC': 'SC',
    'ST SCHOLARSHIP': 'ST', 'ST': 'ST',
    'NT-C': 'NT_C', 'NT_C': 'NT_C', 'NTC': 'NT_C',
    'MINORITY SCHOLARSHIP': 'MINORITY', 'MINORITY': 'MINORITY',
  };
  return map[key] || 'NONE';
};

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

  // Form State initialized empty (no fake defaults) & populated from backend
  const [formData, setFormData] = useState({
    fullName: '',
    prn: '',
    dteAppId: '',
    studentEmail: '',
    fatherName: '',
    parentMobile: '',
    motherName: '',
    placeOfBirth: '',
    dobDay: '',
    dobMonth: '',
    dobYear: '',
    gender: '',
    caste: '',
    maritalStatus: '',
    abcId: '',
    admittedYear: '',
    admissionType: '',
    category: '',
    allottedSeatType: '',
    scholarshipApplied: 'No',
    scholarshipType: 'NONE',
    annualIncome: '',
    address: '',
    district: '',
    state: '',
    pincode: '',
    // Aadhaar
    aadhaarNo: '',
    aadhaarName: '',
    aadhaarMobile: '',
    // Bank
    bankHolderName: '',
    bankName: '',
    branchName: '',
    accountNo: '',
    ifscCode: '',
    // SSC Marksheet
    sscBoard: '',
    sscSchool: '',
    sscPassingYear: '',
    sscSeatNo: '',
    sscMarksObtained: '',
    sscPercentage: '',
    // HSC / Diploma Marksheet
    hscStream: '',
    hscBoard: '',
    hscCollege: '',
    hscPassingYear: '',
    hscSeatNo: '',
    hscMarksObtained: '',
    hscPercentage: '',
  });

  const [retryCount, setRetryCount] = useState(0);

  // Backend StudentViewSet has no generic update endpoint.
  // Students may edit their OWN profile (no `id` param) via PATCH /students/me/update/.
  // Locked for everyone: enrollment, admission, gender, caste, verified flags.
  // Editable by owner: full name, contact, Aadhaar number + name, address,
  // guardians, bank, SSC/HSC board records.
  // Teachers/staff opening /students/:id from the directory are strictly read-only.
  // Edit-lock: everything starts locked; owner clicks Edit to unlock, Lock finalizes permanently.
  // One-time rule: once student.profile_locked is True, Edit never appears again
  // (backend also rejects update/upload with 403 — no re-edit possible).
  const isOwnProfile = !id;
  const profileLocked = Boolean(student?.profile_locked);
  const canEdit = isOwnProfile && hasRole('STUDENT') && !profileLocked;
  const [isEditing, setIsEditing] = useState(false);
  const [snapshot, setSnapshot] = useState(null);
  const fieldsLocked = !canEdit || !isEditing;
  // One-time lock modal (renamed Save -> Lock).
  const [showLockModal, setShowLockModal] = useState(false);
  const [lockEmptyFields, setLockEmptyFields] = useState([]);
  const [isLocking, setIsLocking] = useState(false);
  const [lockError, setLockError] = useState('');
  const [isSavingDraft, setIsSavingDraft] = useState(false);
  // Ref mirror of isEditing so the async fetchProfile closure never
  // overwrites unsaved typing with stale DB values (e.g. after a
  // document upload bumps retryCount mid-edit).
  const isEditingRef = useRef(false);
  useEffect(() => {
    isEditingRef.current = isEditing;
  }, [isEditing]);

  // Switching between own profile and directory records always re-locks.
  useEffect(() => {
    setIsEditing(false);
    setSnapshot(null);
    setShowLockModal(false);
    setLockEmptyFields([]);
    setLockError('');
  }, [id]);

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
        // Always refresh server metadata (docs list, lock flag) but never
        // clobber unsaved typing mid-edit — a refetch (doc upload, retry)
        // would otherwise overwrite formData with stale DB empties.
        setStudent(data);
        if (isEditingRef.current) return;

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

        let day = '';
        let month = '';
        let year = '';
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
          `${data.first_name || ''} ${data.middle_name || ''} ${data.last_name || ''}`.replace(/\s+/g, ' ').trim() ||
          '';

        const isDSY = Boolean(data.is_direct_second_year || data.admission_details?.admission_type === 'DIRECT_SECOND_YEAR');
        const adm = data.admission_details || {};
        const enr = data.current_enrollment || {};
        const boards = data.board_records || [];
        const sscRec = boards.find((b) => String(b.level || '').toUpperCase() === 'SSC') || {};
        const hscRec = boards.find((b) => ['HSC', 'DIPLOMA'].includes(String(b.level || '').toUpperCase())) || {};

        setFormData((prev) => ({
          ...prev,
          fullName: candidateName,
          prn: data.enrollment_no || '',
          dteAppId: data.application_id || '',
          studentEmail: p.student_email || '',
          fatherName: gFather?.name || '',
          parentMobile: gFather?.mobile || '',
          motherName: gMother?.name || '',
          placeOfBirth: p.place_of_birth || '',
          dobDay: day,
          dobMonth: month,
          dobYear: year,
          gender: p.gender === 'FEMALE' ? 'Female' : p.gender === 'OTHER' ? 'Other' : p.gender === 'MALE' ? 'Male' : '',
          caste: p.caste || '',
          maritalStatus: p.marital_status || '',
          abcId: p.abc_id || '',
          admittedYear: adm.admission_year || enr.academic_year_code || '',
          admissionType: adm.admission_type || (isDSY ? 'DIRECT_SECOND_YEAR' : ''),
          category: adm.category || '',
          allottedSeatType: adm.allotted_seat_type || adm.seat_type || '',
          scholarshipApplied: data.scholarship_applied ? 'Yes' : 'No',
          scholarshipType: SCHOLARSHIP_CODE_VALUES.has(String(data.scholarship_type || '').toUpperCase())
            ? String(data.scholarship_type).toUpperCase()
            : normalizeScholarshipLabel(data.scholarship_type),
          annualIncome: gFather?.annual_income ? String(gFather.annual_income) : '',
          address: perm.address_line_1 || '',
          district: perm.district || '',
          state: perm.state || '',
          pincode: perm.pincode || '',
          aadhaarNo: adh.aadhaar_number_masked || '',
          aadhaarName: adh.name_as_per_aadhaar || '',
          aadhaarMobile: p.student_mobile || '',
          bankHolderName: bk.account_holder_name || '',
          bankName: bk.bank_name || '',
          branchName: bk.branch_name || '',
          accountNo: bk.account_number_masked || '',
          ifscCode: bk.ifsc_code || '',
          sscBoard: sscRec.board || '',
          sscSchool: sscRec.school_college || '',
          sscPassingYear: sscRec.passing_year || '',
          sscSeatNo: sscRec.seat_no || '',
          sscMarksObtained: sscRec.marks_obtained || '',
          sscPercentage: sscRec.percentage || '',
          hscStream: hscRec.stream || (isDSY && !hscRec.board ? 'Polytechnic Diploma' : ''),
          hscBoard: hscRec.board || adm.diploma_board || '',
          hscCollege: hscRec.school_college || adm.diploma_college || '',
          hscPassingYear: hscRec.passing_year || '',
          hscSeatNo: hscRec.seat_no || adm.diploma_seat_no || '',
          hscPercentage: hscRec.percentage || (adm.diploma_percentage ? `${adm.diploma_percentage}%` : ''),
          hscMarksObtained: hscRec.marks_obtained || (adm.merit_marks ? `${adm.merit_marks} / 100` : ''),
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

  const startEditing = () => {
    if (!canEdit || isEditing) return;
    setSnapshot({ ...formData });
    setIsEditing(true);
  };

  const cancelEditing = () => {
    // Snapshot restore wipes everything typed since Edit — confirm so a
    // misclick never silently discards the student's filled fields.
    if (isEditing && !window.confirm('Discard unsaved changes and revert to the last saved values?')) return;
    if (snapshot) setFormData(snapshot);
    setIsEditing(false);
    setSnapshot(null);
  };

  const handleInputChange = (field, value) => {
    if (!canEdit) {
      showFeedback('Read-only view. Only the student can edit their own profile.');
      return;
    }
    if (!isEditing) {
      showFeedback('Profile is locked. Click Edit Profile to start editing.');
      return;
    }
    setFormData((prev) => ({ ...prev, [field]: value }));
  };

  const showFeedback = (msg) => {
    setStatusMessage(msg);
    setTimeout(() => setStatusMessage(''), 3500);
  };

  // ─── Student document uploads ───
  // Policy: ALLOTMENT_LETTER max 200 KB, all other images/documents max 150 KB.
  const [uploadingDoc, setUploadingDoc] = useState(null);
  const docs = student?.documents || [];
  const latestDocOf = (type) =>
    docs.filter((d) => d.document_type === type).sort((a, b) => (b.version || 0) - (a.version || 0))[0] || null;
  const allotmentDoc = latestDocOf('ALLOTMENT_LETTER');

  const validateDocFile = (file, docType) => {
    const limit = docType === 'ALLOTMENT_LETTER' ? 200 * 1024 : 150 * 1024;
    if (file.size > limit) {
      showFeedback(`${docType} exceeds ${(limit / 1024).toFixed(0)} KB (selected ${(file.size / 1024).toFixed(1)} KB). Please compress and retry.`);
      return false;
    }
    return true;
  };

  const handleDocumentUpload = async (e, docType) => {
    const file = e.target?.files?.[0];
    if (!file) return;
    if (!validateDocFile(file, docType)) {
      e.target.value = '';
      return;
    }
    if (!canEdit) {
      showFeedback(profileLocked ? 'Profile is locked permanently. Contact Admin Head for corrections.' : 'Read-only view. Only the student can upload to their own profile.');
      e.target.value = '';
      return;
    }
    try {
      setUploadingDoc(docType);
      if (id) {
        await studentApi.uploadStudentDocument(id, file, docType, `${docType} upload`);
      } else {
        await studentApi.uploadMyDocument(file, docType, `${docType} upload`);
      }
      showFeedback(`${docType} uploaded successfully.`);
      setRetryCount((c) => c + 1);
    } catch (err) {
      const data = err.response?.data;
      showFeedback(data?.file?.join?.(' ') || data?.detail || data?.document_type?.join?.(' ') || 'Upload failed. Check file size/type.');
    } finally {
      setUploadingDoc(null);
      if (e.target) e.target.value = '';
    }
  };

  const handleDownloadDoc = async (doc) => {
    if (!doc) return;
    try {
      const res = id
        ? await studentApi.downloadStudentDocument(id, doc.id)
        : await studentApi.downloadMyDocument(doc.id);
      const blob = new Blob([res.data], { type: doc.mime_type || 'application/octet-stream' });
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${doc.document_type}.${(doc.mime_type || '').includes('pdf') ? 'pdf' : 'jpg'}`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
    } catch {
      showFeedback('Download failed. File may be missing on server.');
    }
  };

  const handlePhotoUpload = (e) => handleDocumentUpload(e, 'PHOTO');
  const handleSignatureUpload = (e) => handleDocumentUpload(e, 'SIGNATURE');

  const MONTHS = [
    'January', 'February', 'March', 'April', 'May', 'June',
    'July', 'August', 'September', 'October', 'November', 'December',
  ];

  // ---- One-time lock helpers ----
  // Editable-field labels for the empty-fields warning (locked identity/
  // admission fields are excluded — never the student's responsibility).
  const getEmptyEditableFields = () => {
    const empty = [];
    const blank = (v) => !String(v || '').trim();
    if (blank(formData.fullName)) empty.push('Full Name');
    if (blank(formData.studentEmail)) empty.push('Student Email');
    if (blank(formData.fatherName)) empty.push("Father's Name");
    if (blank(formData.parentMobile)) empty.push('Parent Mobile No.');
    if (blank(formData.motherName)) empty.push("Mother's Name");
    if (blank(formData.placeOfBirth)) empty.push('Place of Birth');
    if (!formData.dobDay || !formData.dobMonth || !formData.dobYear) empty.push('Date of Birth');
    if (blank(formData.maritalStatus)) empty.push('Marital Status');
    if (blank(formData.abcId)) empty.push('ABC ID');
    if (blank(formData.annualIncome)) empty.push("Parent's Annual Income");
    if (formData.scholarshipApplied === 'Yes' && !SCHOLARSHIP_CODE_VALUES.has(formData.scholarshipType)) empty.push('Scholarship Type');
    if (blank(formData.address)) empty.push('Address');
    if (blank(formData.district)) empty.push('District');
    if (blank(formData.state)) empty.push('State');
    if (blank(formData.pincode)) empty.push('Pincode');
    if (blank(formData.aadhaarNo)) empty.push('Aadhaar Number');
    if (blank(formData.aadhaarName)) empty.push('Name As per Aadhaar');
    if (blank(formData.aadhaarMobile)) empty.push('Mobile No. Linked to Aadhaar');
    if (blank(formData.bankHolderName)) empty.push('Bank Account Holder Name');
    if (blank(formData.bankName)) empty.push('Bank Name');
    if (blank(formData.branchName)) empty.push('Branch Name');
    if (blank(formData.accountNo)) empty.push('Account No');
    if (blank(formData.ifscCode)) empty.push('IFSC Code');
    if (blank(formData.sscBoard)) empty.push('SSC Board Name');
    if (blank(formData.sscSchool)) empty.push('SSC School Name');
    if (blank(formData.sscPassingYear)) empty.push('SSC Passing Year');
    if (blank(formData.sscSeatNo)) empty.push('SSC Seat / Roll Number');
    if (blank(formData.sscMarksObtained)) empty.push('SSC Total Marks');
    if (blank(formData.sscPercentage)) empty.push('SSC Percentage / CGPA');
    if (blank(formData.hscStream)) empty.push('HSC / Diploma Stream');
    if (blank(formData.hscBoard)) empty.push('HSC / Diploma Board');
    if (blank(formData.hscCollege)) empty.push('HSC / Diploma College');
    if (blank(formData.hscPassingYear)) empty.push('HSC / Diploma Passing Year');
    if (blank(formData.hscSeatNo)) empty.push('HSC / Diploma Seat No.');
    if (blank(formData.hscMarksObtained)) empty.push('HSC / Diploma Marks');
    if (blank(formData.hscPercentage)) empty.push('HSC / Diploma Percentage');
    return empty;
  };

  // Shared frontend validation + payload build. Returns { payload } or { error }.
  // Never touches the network — safe to call before opening the warning modal.
  const buildSavePayload = () => {
    const parentMobile = String(formData.parentMobile || '').trim().replace(/[\s-]/g, '');
    if (parentMobile && !/^\+?\d{10,15}$/.test(parentMobile)) {
      return { error: 'Enter a valid 10-digit Parent Mobile No.' };
    }
    const scholarshipYes = formData.scholarshipApplied === 'Yes';
    if (scholarshipYes && !SCHOLARSHIP_CODE_VALUES.has(formData.scholarshipType)) {
      return { error: 'Select a Scholarship Type when Scholarship Applied is Yes.' };
    }
    const annualIncomeRaw = String(formData.annualIncome || '').replace(/[,₹\s]/g, '');
    if (annualIncomeRaw && !/^\d+$/.test(annualIncomeRaw)) {
      return { error: 'Enter Parent Annual Income as a number.' };
    }
    const studentEmailRaw = String(formData.studentEmail || '').trim();
    if (studentEmailRaw && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(studentEmailRaw)) {
      return { error: 'Enter a valid Student Email address.' };
    }
    const dobFilled = [formData.dobDay, formData.dobMonth, formData.dobYear].filter(Boolean).length;
    let dobIso = null;
    if (dobFilled > 0) {
      if (dobFilled < 3) {
        return { error: 'Select day, month and year for Date of Birth, or leave all blank.' };
      }
      const monthNum = String(MONTHS.indexOf(formData.dobMonth) + 1).padStart(2, '0');
      const dayNum = String(formData.dobDay).padStart(2, '0');
      dobIso = `${formData.dobYear}-${monthNum}-${dayNum}`;
    }
    const addressLine = String(formData.address || '').trim();
    const districtRaw = String(formData.district || '').trim();
    const stateRaw = String(formData.state || '').trim();
    const pincodeRaw = String(formData.pincode || '').trim();
    if (!addressLine && (districtRaw || stateRaw || pincodeRaw)) {
      return { error: 'Main address is empty — please fill Address before locking. Nothing was saved.' };
    }
    if (pincodeRaw && !/^\d{6}$/.test(pincodeRaw)) {
      return { error: 'Pincode must be 6 digits.' };
    }
    const fullNameRaw = String(formData.fullName || '').trim();
    const aadhaarDigits = String(formData.aadhaarNo || '').replace(/\D/g, '');
    const aadhaarSendNumber = formData.aadhaarNo && !String(formData.aadhaarNo).includes('X') && aadhaarDigits
      ? String(formData.aadhaarNo).trim()
      : '';
    const aadhaarNameRaw = String(formData.aadhaarName || '').trim();
    const sscBlock = [formData.sscBoard, formData.sscSchool, formData.sscPassingYear, formData.sscSeatNo, formData.sscMarksObtained, formData.sscPercentage].some((v) => String(v || '').trim())
      ? {
          board: String(formData.sscBoard || '').trim(),
          school_college: String(formData.sscSchool || '').trim(),
          passing_year: String(formData.sscPassingYear || '').trim(),
          seat_no: String(formData.sscSeatNo || '').trim(),
          marks_obtained: String(formData.sscMarksObtained || '').trim(),
          percentage: String(formData.sscPercentage || '').trim(),
        }
      : null;
    const hscLevel = student?.is_direct_second_year ? 'DIPLOMA' : 'HSC';
    const hscBlock = [formData.hscStream, formData.hscBoard, formData.hscCollege, formData.hscPassingYear, formData.hscSeatNo, formData.hscMarksObtained, formData.hscPercentage].some((v) => String(v || '').trim())
      ? {
          level: hscLevel,
          stream: String(formData.hscStream || '').trim(),
          board: String(formData.hscBoard || '').trim(),
          school_college: String(formData.hscCollege || '').trim(),
          passing_year: String(formData.hscPassingYear || '').trim(),
          seat_no: String(formData.hscSeatNo || '').trim(),
          marks_obtained: String(formData.hscMarksObtained || '').trim(),
          percentage: String(formData.hscPercentage || '').trim(),
        }
      : null;
    const payload = {
      ...(fullNameRaw ? { full_name: fullNameRaw } : {}),
      personal: {
        place_of_birth: formData.placeOfBirth,
        ...(dobIso ? { date_of_birth: dobIso } : {}),
        student_mobile: formData.aadhaarMobile,
        student_email: studentEmailRaw,
        ...(formData.maritalStatus ? { marital_status: formData.maritalStatus } : {}),
        abc_id: formData.abcId,
      },
      scholarship_applied: scholarshipYes,
      scholarship_type: scholarshipYes ? formData.scholarshipType : 'NONE',
      guardians: [
        ...(formData.fatherName || parentMobile || annualIncomeRaw ? [{
          relationship: 'FATHER',
          name: formData.fatherName || undefined,
          mobile: parentMobile || undefined,
          ...(annualIncomeRaw ? { annual_income: annualIncomeRaw } : {}),
        }] : []),
        ...(formData.motherName ? [{ relationship: 'MOTHER', name: formData.motherName }] : []),
      ],
      ...(addressLine ? {
        address: {
          address_line_1: addressLine,
          district: districtRaw,
          state: stateRaw,
          pincode: pincodeRaw,
        },
      } : {}),
      ...(formData.bankName || formData.accountNo ? {
        bank: {
          account_holder_name: formData.bankHolderName,
          bank_name: formData.bankName,
          branch_name: formData.branchName,
          ifsc_code: formData.ifscCode,
          ...(!String(formData.accountNo || '').includes('X') && formData.accountNo ? { account_number: formData.accountNo } : {}),
        },
      } : {}),
      ...((aadhaarSendNumber || aadhaarNameRaw) ? {
        aadhaar: {
          ...(aadhaarSendNumber ? { aadhaar_number: aadhaarSendNumber } : {}),
          ...(aadhaarNameRaw ? { name_as_per_aadhaar: aadhaarNameRaw } : {}),
        },
      } : {}),
      ...(sscBlock ? { ssc: sscBlock } : {}),
      ...(hscBlock ? { hsc: hscBlock } : {}),
    };
    return { payload };
  };

  // Step 1: student clicks "Lock Profile" — validate, list empty fields,
  // then show the warning modal. Nothing is saved yet (no accidental lock).
  const openLockModal = () => {
    if (!canEdit || isLocking) return;
    if (!isEditing) {
      showFeedback('Click Edit Profile first to make changes.');
      return;
    }
    const { error } = buildSavePayload();
    if (error) {
      showFeedback(error);
      return;
    }
    setLockEmptyFields(getEmptyEditableFields());
    setLockError('');
    setShowLockModal(true);
  };

  // Kept for compatibility: the old Save entry now opens the lock warning.
  const handleSaveProfile = () => openLockModal();

  // Keep Editing: persist what the student already typed as a draft
  // (no lock), then close the modal. formData is never cleared here —
  // even if the save fails the modal stays open with the reason and the
  // typing stays on screen. Success also bumps the snapshot so a later
  // top-bar Cancel can't revert the just-saved draft.
  const handleKeepEditing = async () => {
    if (!canEdit || isLocking || isSavingDraft) return;
    const { payload, error } = buildSavePayload();
    if (error) {
      setLockError(error);
      return;
    }
    setIsSavingDraft(true);
    setLockError('');
    try {
      await studentApi.updateMyProfile(payload);
      setSnapshot({ ...formData });
      try {
        const res = await studentApi.getMyProfile();
        if (res?.data) setStudent(res.data);
      } catch {
        // Draft is already saved — a refresh failure must not wipe typing.
      }
      setShowLockModal(false);
      showFeedback('Draft saved. Keep editing — nothing was locked.');
    } catch (err) {
      const data = err.response?.data;
      setLockError(
        data?.detail ||
        (data && typeof data === 'object' ? Object.entries(data).map(([k, v]) => `${k}: ${Array.isArray(v) ? v.join(' ') : v}`).join(' ') : null) ||
        'Could not save draft. Your typing is kept — fix the values and try again.'
      );
    } finally {
      setIsSavingDraft(false);
    }
  };

  // Step 2: student confirms "Lock" inside the modal — save first, then
  // lock permanently. Any failure keeps the modal open with the reason;
  // nothing is locked on failure (no accidental / partial lock).
  const handleConfirmLock = async () => {
    if (!canEdit || isLocking) return;
    setIsLocking(true);
    setLockError('');
    try {
      const { payload, error } = buildSavePayload();
      if (error) {
        setLockError(error);
        setIsLocking(false);
        return;
      }
      try {
        await studentApi.updateMyProfile(payload);
      } catch (err) {
        const data = err.response?.data;
        setLockError(
          data?.detail ||
          (data && typeof data === 'object' ? Object.entries(data).map(([k, v]) => `${k}: ${Array.isArray(v) ? v.join(' ') : v}`).join(' ') : null) ||
          'Failed to save profile. Fix the values and try again.'
        );
        setIsLocking(false);
        return;
      }
      try {
        const lockRes = await studentApi.lockMyProfile();
        setShowLockModal(false);
        setIsEditing(false);
        setSnapshot(null);
        const lockedProfile = lockRes.data?.profile;
        if (lockedProfile) setStudent(lockedProfile);
        else setRetryCount((c) => c + 1);
        showFeedback('Profile locked permanently. No further edits are allowed.');
      } catch (err) {
        const data = err.response?.data;
        setLockError(data?.detail || 'Saved, but lock failed. Your edits are saved — try Lock again. Nothing was locked accidentally.');
      }
    } finally {
      setIsLocking(false);
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

  // Password change is strictly self-service: the backend ChangePasswordView
  // only ever updates request.user, so expose the Security tab solely on the
  // student's OWN profile (/profile), never on another student's record
  // (/students/:id) opened from the directory.
  const visibleTabs = isOwnProfile
    ? [...tabs, { id: 'security', label: 'Security', icon: Lock }]
    : tabs;

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
            {canEdit && !isEditing && (
              <button
                className="edvana-btn edvana-btn-primary"
                onClick={startEditing}
                style={{
                  backgroundColor: '#ffffff',
                  color: '#1d4ed8',
                  borderColor: '#ffffff',
                  fontWeight: 700,
                }}
                title="Unlock editable fields"
              >
                <span>Edit Profile</span>
              </button>
            )}
            {canEdit && isEditing && (
              <>
                <button
                  className="edvana-btn edvana-btn-secondary"
                  onClick={cancelEditing}
                  disabled={isLocking || isSavingDraft}
                  style={{
                    backgroundColor: 'rgba(255, 255, 255, 0.18)',
                    color: '#ffffff',
                    borderColor: 'rgba(255, 255, 255, 0.35)',
                  }}
                  title="Discard changes and lock again"
                >
                  <span>Cancel</span>
                </button>
                <button
                  className="edvana-btn edvana-btn-primary"
                  onClick={handleSaveProfile}
                  disabled={isLocking}
                  style={{
                    backgroundColor: '#ffffff',
                    color: '#1d4ed8',
                    borderColor: '#ffffff',
                    fontWeight: 700,
                  }}
                  title="Review empty fields, then lock your profile permanently"
                >
                  <CheckCircle2 size={16} />
                  <span>{isLocking ? 'Locking…' : 'Lock Profile'}</span>
                </button>
              </>
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
          {visibleTabs.map((tab) => {
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
              backgroundColor: isEditing ? '#eff6ff' : '#f8fafc',
              border: `1px solid ${isEditing ? '#bfdbfe' : '#e2e8f0'}`,
              borderRadius: '8px',
              padding: '0.75rem 1rem',
              color: isEditing ? '#1e40af' : '#475569',
              fontSize: '0.8125rem',
              fontWeight: 500,
              display: 'flex',
              alignItems: 'center',
              gap: '0.5rem',
              marginBottom: '1.25rem',
            }}
          >
            <Info size={18} style={{ color: isEditing ? '#2563eb' : '#64748b', flexShrink: 0 }} />
            <span>
              {isEditing
                ? 'Editing unlocked (one-time). Update your details, then press Lock Profile to review and lock permanently. Enrollment, admission, gender and caste stay locked.'
                : 'Profile is locked for editing. Click Edit Profile to start your one-time edit.'}
            </span>
          </div>
        ) : profileLocked && isOwnProfile ? (
          <div
            style={{
              backgroundColor: '#fef2f2',
              border: '1px solid #fecaca',
              borderRadius: '8px',
              padding: '0.75rem 1rem',
              color: '#991b1b',
              fontSize: '0.8125rem',
              fontWeight: 600,
              display: 'flex',
              alignItems: 'center',
              gap: '0.5rem',
              marginBottom: '1.25rem',
            }}
          >
            <Lock size={18} style={{ color: '#dc2626', flexShrink: 0 }} />
            <span>Profile locked permanently{student?.profile_locked_at ? ` on ${new Date(student.profile_locked_at).toLocaleDateString()}` : ''}. No further edits are allowed. Contact Admin Head for corrections.</span>
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
                        '—'}
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
                      {student.enrollment_no || '—'}
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
                      disabled={fieldsLocked}
                      title={fieldsLocked ? 'Click Edit Profile to edit your full name.' : 'Your full name as per records.'}
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
                      University PRN (Enrollment No) <span style={{ color: '#ef4444' }}>*</span>
                    </label>
                    <input
                      type="text"
                      className="edvana-input"
                      disabled
                      title="Locked: University Permanent Registration Number (PRN)."
                      value={formData.prn || student.enrollment_no || ''}
                    />
                    <span
                      style={{
                        fontSize: '0.75rem',
                        color: '#64748b',
                        marginTop: '0.25rem',
                        display: 'block',
                      }}
                    >
                      DBATU University Permanent Registration Number
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
                      Student Email
                    </label>
                    <input
                      type="email"
                      className="edvana-input"
                      disabled={fieldsLocked}
                      placeholder="e.g. student@example.com"
                      value={formData.studentEmail}
                      onChange={(e) => handleInputChange('studentEmail', e.target.value)}
                    />
                    <span
                      style={{
                        fontSize: '0.75rem',
                        color: '#64748b',
                        marginTop: '0.25rem',
                        display: 'block',
                      }}
                    >
                      Shown in the sidebar next to the mail icon. Leave blank to show –.
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
                      Father's Name
                    </label>
                    <input
                      type="text"
                      className="edvana-input"
                      disabled={fieldsLocked}
                      placeholder="Father's full name"
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
                      Parent Mobile No.
                    </label>
                    <input
                      type="tel"
                      className="edvana-input"
                      disabled={fieldsLocked}
                      placeholder="10-digit parent mobile"
                      inputMode="numeric"
                      maxLength={15}
                      value={formData.parentMobile}
                      onChange={(e) => handleInputChange('parentMobile', e.target.value.replace(/[^\d+]/g, '').slice(0, 15))}
                    />
                    <span
                      style={{
                        fontSize: '0.75rem',
                        color: '#64748b',
                        marginTop: '0.25rem',
                        display: 'block',
                      }}
                    >
                      Shown on the fee-desk Candidate Details card.
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
                      Mother's Name
                    </label>
                    <input
                      type="text"
                      className="edvana-input"
                      disabled={fieldsLocked}
                      placeholder="Mother's name"
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
                      Sub-Caste (जात)
                    </label>
                    <input
                      type="text"
                      className="edvana-input"
                      disabled
                      title="Locked: sub-caste from your admission record. Contact Admin Head for corrections."
                      placeholder="e.g. Maratha, Kunbi, Sutar"
                      value={formData.caste}
                      onChange={(e) => handleInputChange('caste', e.target.value)}
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
                      Marital Status
                    </label>
                    <select
                      className="edvana-select"
                      disabled={fieldsLocked}
                      value={formData.maritalStatus}
                      onChange={(e) => handleInputChange('maritalStatus', e.target.value)}
                    >
                      <option value="">Select marital status</option>
                      <option value="Unmarried">Unmarried</option>
                      <option value="Married">Married</option>
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
                      ABC ID (Academic Bank of Credits)
                    </label>
                    <input
                      type="text"
                      className="edvana-input"
                      disabled={fieldsLocked}
                      placeholder="e.g. 123-456-789-012"
                      value={formData.abcId}
                      onChange={(e) => handleInputChange('abcId', e.target.value)}
                    />
                    <span
                      style={{
                        fontSize: '0.75rem',
                        color: '#64748b',
                        marginTop: '0.25rem',
                        display: 'block',
                      }}
                    >
                      NEP 2020 DigiLocker / APAAR ID
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
                      Place of Birth
                    </label>
                    <input
                      type="text"
                      className="edvana-input"
                      disabled={fieldsLocked}
                      placeholder="e.g. Kolhapur"
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
                        className="edvana-select" disabled={fieldsLocked}
                        value={formData.dobDay}
                        onChange={(e) => handleInputChange('dobDay', e.target.value)}
                      >
                        <option value="">Day</option>
                        {Array.from({ length: 31 }, (_, i) => i + 1).map((d) => (
                          <option key={d} value={String(d)}>
                            {d}
                          </option>
                        ))}
                      </select>
                      <select
                        className="edvana-select" disabled={fieldsLocked}
                        value={formData.dobMonth}
                        onChange={(e) => handleInputChange('dobMonth', e.target.value)}
                      >
                        <option value="">Month</option>
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
                        className="edvana-select" disabled={fieldsLocked}
                        value={formData.dobYear}
                        onChange={(e) => handleInputChange('dobYear', e.target.value)}
                      >
                        <option value="">Year</option>
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
                      className="edvana-select" disabled
                      title="Locked: gender from your admission record. Contact Admin Head for corrections."
                      value={formData.gender}
                      onChange={(e) => handleInputChange('gender', e.target.value)}
                    >
                      <option value="">Select</option>
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
                      Admitted Academic Year <span style={{ color: '#ef4444' }}>*</span>
                    </label>
                    <input
                      type="text"
                      className="edvana-input"
                      disabled
                      title="Locked: authoritative admission year."
                      value={formData.admittedYear || student.admission_year_code || ''}
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
                    <input
                      type="text"
                      className="edvana-input"
                      disabled
                      title="Locked: admission record."
                      value={formData.admissionType || ''}
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
                      Candidate Category <span style={{ color: '#ef4444' }}>*</span>
                    </label>
                    <input
                      type="text"
                      className="edvana-input"
                      disabled
                      title="Locked: official candidate category."
                      value={formData.category || ''}
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
                      Allotted Seat Type / Quota <span style={{ color: '#ef4444' }}>*</span>
                    </label>
                    <input
                      type="text"
                      className="edvana-input"
                      disabled
                      title="Locked: admission allotment quota."
                      value={formData.allottedSeatType || formData.category || ''}
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
                      Scholarship Applied
                    </label>
                    <select
                      className="edvana-select"
                      disabled={fieldsLocked}
                      value={formData.scholarshipApplied}
                      onChange={(e) => {
                        const v = e.target.value;
                        // Applied=No forces type back to None (server enforces too).
                        setFormData((prev) => ({
                          ...prev,
                          scholarshipApplied: v,
                          scholarshipType: v === 'No' ? 'NONE' : prev.scholarshipType === 'NONE' ? '' : prev.scholarshipType,
                        }));
                      }}
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
                      Scholarship Type
                    </label>
                    <select
                      className="edvana-select"
                      disabled={fieldsLocked || formData.scholarshipApplied === 'No'}
                      title={formData.scholarshipApplied === 'No' ? 'Set Scholarship Applied to Yes to choose a type.' : undefined}
                      value={formData.scholarshipType}
                      onChange={(e) => handleInputChange('scholarshipType', e.target.value)}
                    >
                      {formData.scholarshipApplied === 'Yes' && !SCHOLARSHIP_CODE_VALUES.has(formData.scholarshipType) && (
                        <option value="">Select scholarship type</option>
                      )}
                      {SCHOLARSHIP_OPTIONS.map((o) => (
                        <option key={o.value} value={o.value} disabled={o.value === 'NONE' && formData.scholarshipApplied === 'Yes'}>
                          {o.label}
                        </option>
                      ))}
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
                      Parent's / Guardian's Annual Income
                    </label>
                    <input
                      type="text"
                      className="edvana-input"
                      disabled={fieldsLocked}
                      placeholder="e.g. ₹ 1,50,000"
                      value={formData.annualIncome}
                      onChange={(e) => handleInputChange('annualIncome', e.target.value)}
                    />
                  </div>
                </div>

                {/* Upload Allotment Letter (CAP) — max 200 KB */}
                <div style={{ borderTop: '1px solid #f1f5f9', marginTop: '1.25rem', paddingTop: '1.25rem' }}>
                  <label
                    style={{
                      display: 'block',
                      fontSize: '0.8125rem',
                      fontWeight: 600,
                      color: '#334155',
                      marginBottom: '0.375rem',
                    }}
                  >
                    Upload Institute Allotment Letter <span style={{ color: '#ef4444' }}>*</span>{' '}
                    <span style={{ fontSize: '0.75rem', color: '#64748b', fontWeight: 400 }}>
                      (PDF / JPG / PNG, max 200 KB)
                    </span>
                  </label>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.75rem', alignItems: 'center' }}>
                    <input
                      type="file"
                      accept=".pdf,.jpg,.jpeg,.png"
                      className="edvana-input"
                      disabled={!canEdit || uploadingDoc === 'ALLOTMENT_LETTER'}
                      title={canEdit ? 'Upload CAP allotment letter (max 200 KB)' : 'Read-only view'}
                      style={{ padding: '0.45rem', background: '#f8fafc', maxWidth: '360px' }}
                      onChange={(e) => handleDocumentUpload(e, 'ALLOTMENT_LETTER')}
                    />
                    {uploadingDoc === 'ALLOTMENT_LETTER' && (
                      <span style={{ fontSize: '0.8rem', color: '#2563eb' }}>Uploading…</span>
                    )}
                    {allotmentDoc && (
                      <button
                        type="button"
                        className="edvana-btn edvana-btn-outline"
                        onClick={() => handleDownloadDoc(allotmentDoc)}
                        style={{ display: 'inline-flex', alignItems: 'center', gap: '0.5rem' }}
                      >
                        <FileText size={16} />
                        <span>View/Download (v{allotmentDoc.version}, {(allotmentDoc.file_size / 1024).toFixed(1)} KB)</span>
                      </button>
                    )}
                  </div>
                  {!allotmentDoc && (
                    <div style={{ fontSize: '0.75rem', color: '#64748b', marginTop: '0.35rem' }}>
                      No allotment letter on file yet.
                    </div>
                  )}
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
                    className="edvana-textarea" disabled={fieldsLocked}
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
                      className="edvana-input" disabled={fieldsLocked}
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
                      className="edvana-input" disabled={fieldsLocked}
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
                      className="edvana-input" disabled={fieldsLocked}
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
                      accept=".jpg,.jpeg,.png"
                      className="edvana-input"
                      disabled={!canEdit || uploadingDoc === 'PHOTO'}
                      title={canEdit ? 'Upload passport photo (max 150 KB)' : 'Read-only view'}
                      style={{ padding: '0.5rem', background: '#f8fafc' }}
                      onChange={handlePhotoUpload}
                    />
                    <p style={{ fontSize: '0.75rem', color: '#64748b', marginTop: '0.5rem' }}>
                      Max file size 150 KB. Formats: .jpg, .png. White or light background recommended.
                      {latestDocOf('PHOTO') && ` On file: v${latestDocOf('PHOTO').version} (${(latestDocOf('PHOTO').file_size / 1024).toFixed(1)} KB).`}
                    </p>
                    {latestDocOf('PHOTO') && (
                      <button type="button" className="edvana-btn edvana-btn-outline" onClick={() => handleDownloadDoc(latestDocOf('PHOTO'))} style={{ marginTop: '0.5rem' }}>
                        <span>View/Download Photo</span>
                      </button>
                    )}
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
                      accept=".jpg,.jpeg,.png"
                      className="edvana-input"
                      disabled={!canEdit || uploadingDoc === 'SIGNATURE'}
                      title={canEdit ? 'Upload signature (max 150 KB)' : 'Read-only view'}
                      style={{ padding: '0.5rem', background: '#f8fafc' }}
                      onChange={handleSignatureUpload}
                    />
                    <p style={{ fontSize: '0.75rem', color: '#64748b', marginTop: '0.5rem' }}>
                      Max file size 150 KB. Formats: .jpg, .png.
                      {latestDocOf('SIGNATURE') && ` On file: v${latestDocOf('SIGNATURE').version}.`}
                    </p>
                    {latestDocOf('SIGNATURE') && (
                      <button type="button" className="edvana-btn edvana-btn-outline" onClick={() => handleDownloadDoc(latestDocOf('SIGNATURE'))} style={{ marginTop: '0.5rem' }}>
                        <span>View/Download Signature</span>
                      </button>
                    )}
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
                          {student.first_name || '—'}
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
                    size should not be more than 150 KB.
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
                      disabled={fieldsLocked}
                      title={fieldsLocked ? 'Click Edit Profile to edit.' : '12-digit Aadhaar number. Re-verified by staff after change.'}
                      placeholder="12-digit Aadhaar number"
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
                      disabled={fieldsLocked}
                      title={fieldsLocked ? 'Click Edit Profile to edit.' : 'Name printed on Aadhaar.'}
                      placeholder="Name as printed on Aadhaar"
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
                      className="edvana-input" disabled={fieldsLocked}
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
                      accept=".pdf,.jpg,.jpeg,.png"
                      className="edvana-input"
                      disabled={!canEdit || uploadingDoc === 'AADHAAR'}
                      title={canEdit ? 'Upload Aadhaar (max 150 KB)' : 'Read-only view'}
                      style={{ padding: '0.45rem', background: '#f8fafc' }}
                      onChange={(e) => handleDocumentUpload(e, 'AADHAAR')}
                    />
                    <p style={{ fontSize: '0.75rem', color: '#64748b', marginTop: '0.35rem' }}>
                      Max 150 KB. {latestDocOf('AADHAAR') ? `On file: v${latestDocOf('AADHAAR').version}.` : 'No file yet.'}
                    </p>
                  </div>
                </div>

                <div>
                  <button
                    type="button"
                    className="edvana-btn edvana-btn-outline"
                    disabled={!latestDocOf('AADHAAR')}
                    onClick={() => latestDocOf('AADHAAR') && handleDownloadDoc(latestDocOf('AADHAAR'))}
                    style={{ display: 'inline-flex', alignItems: 'center', gap: '0.5rem' }}
                  >
                    <FileText size={16} />
                    <span>{latestDocOf('AADHAAR') ? 'View/Download existing Aadhaar' : 'No Aadhaar on file'}</span>
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
                    className="edvana-input" disabled={fieldsLocked}
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
                    className="edvana-input" disabled={fieldsLocked}
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
                    className="edvana-input" disabled={fieldsLocked}
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
                    className="edvana-input" disabled={fieldsLocked}
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
                    className="edvana-input" disabled={fieldsLocked}
                    value={formData.ifscCode}
                    onChange={(e) => handleInputChange('ifscCode', e.target.value)}
                  />
                </div>
              </div>

              <div style={{ fontSize: '0.78rem', color: '#64748b' }}>
                {fieldsLocked
                  ? 'Click Edit Profile at the top to make changes.'
                  : 'One lock for the whole profile — use Lock Profile at the top to review and lock all tabs together.'}
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
                  <li>File size should not exceed 150 KB per marksheet document.</li>
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
                      disabled={fieldsLocked}
                      title={fieldsLocked ? 'Click Edit Profile to edit.' : undefined}
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
                      disabled={fieldsLocked}
                      title={fieldsLocked ? 'Click Edit Profile to edit.' : undefined}
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
                      disabled={fieldsLocked}
                      title={fieldsLocked ? 'Click Edit Profile to edit.' : undefined}
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
                      disabled={fieldsLocked}
                      title={fieldsLocked ? 'Click Edit Profile to edit.' : undefined}
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
                      disabled={fieldsLocked}
                      title={fieldsLocked ? 'Click Edit Profile to edit.' : undefined}
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
                      disabled={fieldsLocked}
                      title={fieldsLocked ? 'Click Edit Profile to edit.' : undefined}
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
                      accept=".pdf,.jpg,.jpeg,.png"
                      className="edvana-input"
                      disabled={!canEdit || uploadingDoc === 'SSC_MARKSHEET'}
                      title={canEdit ? 'Upload SSC marksheet (max 150 KB)' : 'Read-only view'}
                      style={{ padding: '0.45rem', background: '#f8fafc' }}
                      onChange={(e) => handleDocumentUpload(e, 'SSC_MARKSHEET')}
                    />
                    <p style={{ fontSize: '0.75rem', color: '#64748b', marginTop: '0.35rem' }}>
                      Max 150 KB. {latestDocOf('SSC_MARKSHEET') ? `On file: v${latestDocOf('SSC_MARKSHEET').version}.` : 'No file yet.'}
                    </p>
                  </div>

                  <div>
                    <button
                      type="button"
                      className="edvana-btn edvana-btn-outline"
                      disabled={!latestDocOf('SSC_MARKSHEET')}
                      onClick={() => latestDocOf('SSC_MARKSHEET') && handleDownloadDoc(latestDocOf('SSC_MARKSHEET'))}
                      style={{ display: 'inline-flex', alignItems: 'center', gap: '0.5rem' }}
                    >
                      <FileText size={16} />
                      <span>{latestDocOf('SSC_MARKSHEET') ? 'View Uploaded SSC Marksheet' : 'No SSC on file'}</span>
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
                      disabled={fieldsLocked}
                      title={fieldsLocked ? 'Click Edit Profile to edit.' : undefined}
                      value={formData.hscStream}
                      onChange={(e) => handleInputChange('hscStream', e.target.value)}
                    >
                      <option value="">Select stream</option>
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
                      disabled={fieldsLocked}
                      title={fieldsLocked ? 'Click Edit Profile to edit.' : undefined}
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
                      disabled={fieldsLocked}
                      title={fieldsLocked ? 'Click Edit Profile to edit.' : undefined}
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
                      disabled={fieldsLocked}
                      title={fieldsLocked ? 'Click Edit Profile to edit.' : undefined}
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
                      disabled={fieldsLocked}
                      title={fieldsLocked ? 'Click Edit Profile to edit.' : undefined}
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
                      disabled={fieldsLocked}
                      title={fieldsLocked ? 'Click Edit Profile to edit.' : undefined}
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
                      disabled={fieldsLocked}
                      title={fieldsLocked ? 'Click Edit Profile to edit.' : undefined}
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
                      accept=".pdf,.jpg,.jpeg,.png"
                      className="edvana-input"
                      disabled={!canEdit || uploadingDoc === (isDSYStudent ? 'DIPLOMA_MARKSHEET' : 'HSC_MARKSHEET')}
                      title={canEdit ? 'Upload marksheet (max 150 KB)' : 'Read-only view'}
                      style={{ padding: '0.45rem', background: '#f8fafc' }}
                      onChange={(e) => handleDocumentUpload(e, isDSYStudent ? 'DIPLOMA_MARKSHEET' : 'HSC_MARKSHEET')}
                    />
                    <p style={{ fontSize: '0.75rem', color: '#64748b', marginTop: '0.35rem' }}>
                      Max 150 KB. {(() => { const d = latestDocOf(isDSYStudent ? 'DIPLOMA_MARKSHEET' : 'HSC_MARKSHEET'); return d ? `On file: v${d.version}.` : 'No file yet.'; })()}
                    </p>
                  </div>

                  <div>
                    <button
                      type="button"
                      className="edvana-btn edvana-btn-outline"
                      disabled={!latestDocOf(isDSYStudent ? 'DIPLOMA_MARKSHEET' : 'HSC_MARKSHEET')}
                      onClick={() => { const d = latestDocOf(isDSYStudent ? 'DIPLOMA_MARKSHEET' : 'HSC_MARKSHEET'); if (d) handleDownloadDoc(d); }}
                      style={{ display: 'inline-flex', alignItems: 'center', gap: '0.5rem' }}
                    >
                      <FileText size={16} />
                      <span>{(latestDocOf(isDSYStudent ? 'DIPLOMA_MARKSHEET' : 'HSC_MARKSHEET')) ? (isDSYStudent ? 'View Uploaded Diploma Marksheet' : 'View Uploaded HSC Marksheet') : 'No marksheet on file'}</span>
                    </button>
                  </div>
                </div>
              </div>
            </div>

            <div style={{ fontSize: '0.78rem', color: '#64748b' }}>
              {fieldsLocked
                ? 'Click Edit Profile at the top to make changes.'
                : 'One lock for the whole profile — use Lock Profile at the top to review and lock all tabs together.'}
            </div>
          </div>
        )}

        {/* ========================================================
            TAB 6: Security — update password (same experience as
            first-login password change; self-service only)
            ======================================================== */}
        {activeTab === 'security' && isOwnProfile && (
          <div style={{ display: 'flex', justifyContent: 'center' }}>
            <div className="edvana-card" style={{ width: '100%', maxWidth: '560px' }}>
              <div className="edvana-card-header">
                <h3 className="edvana-card-title">Update Password</h3>
                <p className="edvana-card-description">
                  Choose a strong, unique password for your account. Same security
                  policy as your first-login password setup.
                </p>
              </div>
              <div className="edvana-card-body">
                <PasswordChangeForm embedded />
              </div>
            </div>
          </div>
        )}
      </div>

      {/* One-time lock warning modal — explicit confirm, no accidental lock */}
      <Modal
        isOpen={showLockModal}
        onClose={() => { if (!isLocking && !isSavingDraft) setShowLockModal(false); }}
        title="Lock Profile Permanently?"
        maxWidth="560px"
      >
        {lockError && (
          <div style={{ marginBottom: '1rem', padding: '0.75rem 1rem', background: '#fef2f2', border: '1px solid #fecaca', borderRadius: '6px', color: '#991b1b', fontSize: '0.85rem' }}>
            {lockError}
          </div>
        )}

        <p style={{ fontSize: '0.875rem', color: '#334155', lineHeight: 1.6, margin: '0 0 0.75rem' }}>
          Once you lock, <strong>all changes become permanent and you can never edit again</strong>.
          The Edit option will disappear. Only Admin Head can fix mistakes after that.
        </p>

        {lockEmptyFields.length > 0 ? (
          <div style={{ background: '#fffbeb', border: '1px solid #fde68a', borderRadius: '8px', padding: '0.75rem 1rem', marginBottom: '1rem' }}>
            <div style={{ fontSize: '0.8125rem', fontWeight: 700, color: '#92400e', marginBottom: '0.4rem' }}>
              {lockEmptyFields.length} field{lockEmptyFields.length === 1 ? '' : 's'} left empty — they will stay empty forever:
            </div>
            <ul style={{ margin: 0, paddingLeft: '1.2rem', fontSize: '0.8125rem', color: '#78350f', lineHeight: 1.6, maxHeight: '180px', overflowY: 'auto' }}>
              {lockEmptyFields.map((label) => (
                <li key={label}>{label}</li>
              ))}
            </ul>
          </div>
        ) : (
          <div style={{ background: '#f0fdf4', border: '1px solid #bbf7d0', borderRadius: '8px', padding: '0.75rem 1rem', marginBottom: '1rem', fontSize: '0.8125rem', color: '#166534', fontWeight: 600 }}>
            All editable fields are filled. You can still lock now — it will be permanent.
          </div>
        )}

        <p style={{ fontSize: '0.78rem', color: '#64748b', margin: '0 0 1rem' }}>
          Locked identity fields (enrollment, admission, gender, caste) were never editable and are not listed here.
        </p>

        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem', borderTop: '1px solid #e2e8f0', paddingTop: '1.25rem' }}>
          <button
            type="button"
            onClick={handleKeepEditing}
            disabled={isLocking || isSavingDraft}
            className="edvana-btn edvana-btn-secondary"
            title="Save what you typed and keep editing — nothing gets locked"
          >
            {isSavingDraft ? 'Saving…' : 'Keep Editing'}
          </button>
          <button
            type="button"
            onClick={handleConfirmLock}
            disabled={isLocking || isSavingDraft}
            className="edvana-btn edvana-btn-primary"
            style={{ backgroundColor: '#dc2626', borderColor: '#dc2626', color: '#ffffff', fontWeight: 700 }}
          >
            {isLocking ? 'Locking…' : 'Lock Permanently'}
          </button>
        </div>
      </Modal>
    </>
  );
}
