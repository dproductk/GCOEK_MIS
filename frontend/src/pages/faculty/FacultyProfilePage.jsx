import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import facultyApi from '../../api/facultyApi';
import academicApi from '../../api/academicApi';
import PageHeader from '../../components/common/PageHeader';
import {
  User,
  Award,
  BookOpen,
  Landmark,
  FileText,
  CheckCircle2,
  AlertCircle,
  Calendar,
  Upload,
  Info,
  ChevronDown,
  ArrowLeft,
} from 'lucide-react';

const DAYS = Array.from({ length: 31 }, (_, i) => String(i + 1));
const MONTHS = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December'
];
const YEARS = Array.from({ length: 55 }, (_, i) => String(2005 - i));

// Departments are DB-driven only (no hardcoded placeholders).
// Loaded from GET /academic/departments/ in useEffect below.

const DESIGNATIONS = [
  'Assistant Professor',
  'Associate Professor',
  'Professor',
  'Lecturer',
  'Head of Department',
  'Principal',
  'Adjunct Professor',
  'Administrative Officer',
  'Office Superintendent',
  'Stenographer',
  'Steno-cum-Typist',
  'Head Clerk',
  'Senior Clerk',
  'Junior Clerk',
  'Instructor (Molder)',
  'Instructor (T.L.A.)',
  'Lab Assistant',
  'Non-Teaching Lab Assistant',
  'Lab Attendant',
  'Store Keeper',
  'Library Assistant',
  'Peon',
  'Hamal',
  'Co-ordinator',
  'Other',
];

const CATEGORIES = [
  'OPEN', 'OBC', 'SC', 'ST', 'VJ/DT(A)', 'NT(B)', 'NT(C)', 'NT(D)', 'SBC', 'EWS'
];

const RESERVATIONS = [
  'Not Applicable',
  'Physically Handicapped (PH)',
  'Defense Personnel',
  'Freedom Fighter',
];

const STATES = [
  'Maharashtra State',
  'Andhra Pradesh',
  'Goa',
  'Gujarat',
  'Karnataka',
  'Madhya Pradesh',
  'Tamil Nadu',
  'Delhi',
  'Other',
];

const CLASSES = [
  'First Class with Distinction',
  'First Class',
  'Higher Second Class',
  'Second Class',
  'Pass Class',
];

const UNIVERSITIES = [
  'Dr. Babasaheb Ambedkar Technological University (BATU)',
  'Savitribai Phule Pune University (SPPU)',
  'University of Mumbai',
  'Shivaji University, Kolhapur',
  'Autonomous / MSBTE',
  'Other',
];

export default function FacultyProfilePage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { user, hasRole } = useAuth();

  // Option A (strict): student-only logins cannot open any faculty portfolio.
  const isStudentOnly =
    hasRole('STUDENT') &&
    !hasRole('SYSADMIN') &&
    !hasRole('ADMIN_HEAD') &&
    !hasRole('HOD') &&
    !hasRole('CLASS_TEACHER') &&
    !hasRole('FACULTY') &&
    !hasRole('EMPLOYEE') &&
    !hasRole('ACCOUNTANT');

  const [activeTab, setActiveTab] = useState('profile-info');
  const [loading, setLoading] = useState(true);
  const [successMessage, setSuccessMessage] = useState('');
  const [errorMessage, setErrorMessage] = useState('');
  const [sameAsPermanent, setSameAsPermanent] = useState(false);
  // Edit-lock mode: everything stays read-only until the owner clicks Edit.
  // Save persists via PATCH /faculty/me/update/ and re-locks the form.
  // Directory views (/faculty/:id) are always read-only.
  const [isEditing, setIsEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [snapshot, setSnapshot] = useState(null);

  // Form states start blank: every visible value must come from the backend.
  // No sample-person data may live here (production rule).
  // NOTE: only fields with a real backend column are editable here.
  // SubjectsTaught (from TeachingAssignment), qualifications, publications,
  // documents are read-only server data — no fake editable inputs.
  const [departments, setDepartments] = useState([]);
  const [serverProfile, setServerProfile] = useState(null);
  // Non-faculty accounts (e.g. seed admin_head with no Faculty row) get 404
  // from GET /faculty/me/ — show an honest empty-state instead of a blank form.
  const [noProfile, setNoProfile] = useState(false);
  const [profileInfo, setProfileInfo] = useState({
    department: '',
    designation: '',
    facultyName: '',
    dobDay: '',
    dobMonth: '',
    dobYear: '',
    gender: '',
    nationality: '',
    domicileState: '',
    dateOfAppointment: '',
    category: '',
    email: '',
    mobile: '',
    resTelephoneStd: '',
    resTelephoneNum: '',
    officialEmail: '',
    permanentAddress: {
      address: '',
      district: '',
      state: '',
      pincode: '',
    },
    correspondenceAddress: {
      address: '',
      district: '',
      state: '',
      pincode: '',
    },
  });

  const [qualifications, setQualifications] = useState({
    graduation: {
      course: '',
      otherCourse: '',
      branchName: '',
      classObtained: '',
      university: '',
      otherUniversity: '',
      passingYear: '',
    },
    postGraduation: {
      course: '',
      otherCourse: '',
      branchName: '',
      classObtained: '',
      university: '',
      otherUniversity: '',
      passingYear: '',
    },
    phd: {
      course: '',
      branchName: '',
      classObtained: '',
      university: '',
      passingYear: '',
    },
    other: {
      course: '',
      branchName: '',
      classObtained: '',
      university: '',
      passingYear: '',
    },
  });

  const [academicDetail, setAcademicDetail] = useState({
    nationalPapers: '',
    internationalPapers: '',
    conferenceNational: '',
    conferenceInternational: '',
    booksPatents: '',
    professionalMembership: '',
    consultancyActivities: '',
    awards: '',
    grantsFetched: '',
    interactionInstitution: '',
  });

  const [bankDetail, setBankDetail] = useState({
    bankName: '',
    branchName: '',
    accountNo: '',
    ifscCode: '',
  });

  const [documents, setDocuments] = useState({
    passportPhotoName: '',
    signatureName: '',
    aadhaarNumber: '',
    aadhaarFileName: '',
    panNumber: '',
    panFileName: '',
    aadhaarMasked: '',
    panMasked: '',
    passportPhotoFile: null,
    signatureFile: null,
    aadhaarFile: null,
    panFile: null,
    _docIds: { PHOTO: null, SIGNATURE: null, AADHAAR: null, PAN: null },
  });

  useEffect(() => {
    setIsEditing(false);
    setSnapshot(null);
    setSuccessMessage('');
    setErrorMessage('');
    setNoProfile(false);
    loadFacultyData();
    // Departments for the select: backend is source of truth, fallback is static.
    academicApi.getDepartments().then((r) => {
      const list = r?.data?.results || r?.data || [];
      if (Array.isArray(list) && list.length) setDepartments(list);
    }).catch(() => {});
  }, [id]);

  const loadFacultyData = async () => {
    // Staff-only gate (UX). Backend also returns 403 for student-only.
    if (id && isStudentOnly) {
      setLoading(false);
      setErrorMessage('Not allowed. Faculty directory is staff-only.');
      return;
    }
    try {
      setLoading(true);
      let res;
      if (id) {
        res = await facultyApi.getFacultyProfile(id);
      } else {
        res = await facultyApi.getMyProfile();
      }

      if (res?.data) {
        const d = res.data;
        setServerProfile(d);
        setProfileInfo((prev) => {
          // Backend stores one telephone string; split STD-number on load.
          let std = prev.resTelephoneStd;
          let num = prev.resTelephoneNum;
          if (d.residential_telephone) {
            const parts = String(d.residential_telephone).split('-');
            if (parts.length > 1) {
              std = parts[0].trim();
              num = parts.slice(1).join('-').trim();
            } else if (/^\d+$/.test(String(d.residential_telephone).replace(/\s/g, ''))) {
              num = String(d.residential_telephone).trim();
            } else {
              num = String(d.residential_telephone).trim();
            }
          }
          return {
            ...prev,
            department: d.department_name || d.department?.name || prev.department,
            designation: d.designation_display || d.designation || prev.designation,
            facultyName: d.display_name || `${d.first_name || ''} ${d.last_name || ''}`.trim() || prev.facultyName,
            email: d.personal_email || d.user?.email || prev.email,
            officialEmail: d.official_email || d.user?.email || prev.officialEmail,
            mobile: d.mobile || prev.mobile,
            resTelephoneStd: std,
            resTelephoneNum: num,
            dateOfAppointment: d.date_of_joining || prev.dateOfAppointment,
          };
        });

        // Populate bank tab from the masked primary account (never echo the
        // masked value back as a new account number on save).
        if (d.bank_accounts && d.bank_accounts.length > 0) {
          const primary = d.bank_accounts.find((b) => b.is_primary) || d.bank_accounts[0];
          setBankDetail((prev) => ({
            ...prev,
            bankName: primary.bank_name || prev.bankName,
            branchName: primary.branch_name || prev.branchName,
            accountNo: primary.account_number_masked || prev.accountNo,
            ifscCode: primary.ifsc_code || prev.ifscCode,
          }));
        }

        if (d.personal_details) {
          const pd = d.personal_details;
          setProfileInfo((prev) => {
            let bDay = prev.dobDay, bMonth = prev.dobMonth, bYear = prev.dobYear;
            if (pd.date_of_birth) {
              const dt = new Date(pd.date_of_birth);
              if (!isNaN(dt.getTime())) {
                bDay = String(dt.getDate());
                bMonth = MONTHS[dt.getMonth()];
                bYear = String(dt.getFullYear());
              }
            }
            return {
              ...prev,
              dobDay: bDay,
              dobMonth: bMonth,
              dobYear: bYear,
              gender: pd.gender === 'FEMALE' ? 'Female' : pd.gender === 'OTHER' ? 'Other' : pd.gender === 'MALE' ? 'Male' : '',
              nationality: pd.nationality || '',
              domicileState: pd.domicile_state || '',
              category: pd.constitutional_category || '',
            };
          });
        }

        if (d.addresses && d.addresses.length > 0) {
          const perm = d.addresses.find((a) => a.address_type === 'PERMANENT') || d.addresses[0];
          const corr = d.addresses.find((a) => a.address_type === 'CORRESPONDENCE') || perm;
          if (perm) {
            setProfileInfo((prev) => ({
              ...prev,
              permanentAddress: {
                address: perm.address_line_1 + (perm.address_line_2 ? ', ' + perm.address_line_2 : ''),
                district: perm.district,
                state: perm.state,
                pincode: perm.pincode,
              },
              correspondenceAddress: {
                address: corr.address_line_1 + (corr.address_line_2 ? ', ' + corr.address_line_2 : ''),
                district: corr.district,
                state: corr.state,
                pincode: corr.pincode,
              },
            }));
          }
        }

        // Qualifications: map UG/PG/PHD/OTHER rows back to the 4 cards.
        if (Array.isArray(d.qualifications) && d.qualifications.length) {
          const byLevel = {};
          d.qualifications.forEach((q) => { byLevel[q.qualification_level] = q; });
          setQualifications((prev) => {
            const next = { ...prev };
            const fill = (key, row) => {
              if (!row) return;
              next[key] = {
                ...next[key],
                course: row.degree_name || next[key].course,
                branchName: row.specialization || '',
                classObtained: row.class_or_grade || '',
                university: row.institution_university || '',
                passingYear: row.passing_year ? String(row.passing_year) : '',
              };
            };
            fill('graduation', byLevel.UG);
            fill('postGraduation', byLevel.PG);
            fill('phd', byLevel.PHD);
            fill('other', byLevel.OTHER);
            return next;
          });
        }

        // Research profile: counts + texts.
        if (d.research_profile) {
          const rp = d.research_profile;
          setAcademicDetail({
            nationalPapers: rp.national_journal_papers ?? '',
            internationalPapers: rp.international_journal_papers ?? '',
            conferenceNational: rp.national_conference_papers ?? '',
            conferenceInternational: rp.international_conference_papers ?? '',
            booksPatents: rp.books_patents || '',
            professionalMembership: rp.professional_membership || '',
            consultancyActivities: rp.consultancy_activities || '',
            awards: rp.awards || '',
            grantsFetched: rp.grants_fetched || '',
            interactionInstitution: rp.interaction_institution || '',
          });
        }

        // Documents: map PHOTO/SIGNATURE/AADHAAR/PAN rows back to inputs.
        if (Array.isArray(d.documents) && d.documents.length) {
          const byType = {};
          d.documents.forEach((doc) => { byType[doc.document_type] = doc; });
          const baseName = (p) => (p ? String(p).split('/').pop() : '');
          setDocuments({
            passportPhotoName: baseName(byType.PHOTO?.file_path) || '',
            signatureName: baseName(byType.SIGNATURE?.file_path) || '',
            aadhaarNumber: '',
            aadhaarFileName: baseName(byType.AADHAAR?.file_path) || '',
            panNumber: '',
            panFileName: baseName(byType.PAN?.file_path) || '',
            aadhaarMasked: byType.AADHAAR?.document_number_masked || '',
            panMasked: byType.PAN?.document_number_masked || '',
            _docIds: {
              PHOTO: byType.PHOTO?.id || null,
              SIGNATURE: byType.SIGNATURE?.id || null,
              AADHAAR: byType.AADHAAR?.id || null,
              PAN: byType.PAN?.id || null,
            },
          });
        }
      }
      setNoProfile(false);
    } catch (err) {
      // 404 = account has no Faculty row (e.g. seed admin_head). Show an
      // honest empty-state instead of a blank form; Security tab still works.
      if (!id && err?.response?.status === 404) setNoProfile(true);
    } finally {
      setLoading(false);
    }
  };

  const showSuccess = (msg) => {
    setSuccessMessage(msg);
    setErrorMessage('');
    setTimeout(() => setSuccessMessage(''), 4000);
  };

  const showError = (msg) => {
    setErrorMessage(msg);
    setSuccessMessage('');
    setTimeout(() => setErrorMessage(''), 5000);
  };

  const startEditing = () => {
    if (!isOwnProfile || isEditing) return;
    setSnapshot({ profileInfo, qualifications, academicDetail, bankDetail, documents });
    setIsEditing(true);
    setSuccessMessage('');
    setErrorMessage('');
  };

  const cancelEditing = () => {
    if (snapshot) {
      setProfileInfo(snapshot.profileInfo);
      setQualifications(snapshot.qualifications);
      setAcademicDetail(snapshot.academicDetail);
      setBankDetail(snapshot.bankDetail);
      setDocuments(snapshot.documents);
    }
    setIsEditing(false);
    setSaving(false);
    setErrorMessage('');
  };

  const buildAddressBlock = (addr) => {
    const line1 = String(addr?.address || '').trim();
    if (!line1) return undefined; // all-blank = omit, backend treats as no-change
    const block = { address_line_1: line1 };
    const district = String(addr?.district || '').trim();
    const state = String(addr?.state || '').trim();
    const pincode = String(addr?.pincode || '').trim();
    if (district) block.district = district;
    if (state) block.state = state;
    if (pincode) {
      if (!/^\d{6}$/.test(pincode)) throw new Error('Pincode must be 6 digits.');
      block.pincode = pincode;
    }
    return block;
  };

  const buildProfilePayload = () => {
    // DOB: all-empty = omit (no change); partial = frontend error, never "-00-00".
    const hasDob = profileInfo.dobDay || profileInfo.dobMonth || profileInfo.dobYear;
    let dobStr;
    if (hasDob) {
      if (!profileInfo.dobDay || !profileInfo.dobMonth || !profileInfo.dobYear) {
        throw new Error('Select complete Date of Birth (day, month and year).');
      }
      const mIdx = MONTHS.indexOf(profileInfo.dobMonth);
      if (mIdx < 0) throw new Error('Select a valid birth month.');
      const monthNum = String(mIdx + 1).padStart(2, '0');
      const dayNum = String(profileInfo.dobDay).padStart(2, '0');
      dobStr = `${profileInfo.dobYear}-${monthNum}-${dayNum}`;
      if (!/^\d{4}-\d{2}-\d{2}$/.test(dobStr)) throw new Error('Select a valid Date of Birth.');
    }
    const telephone = [profileInfo.resTelephoneStd, profileInfo.resTelephoneNum]
      .map((s) => String(s || '').trim())
      .filter(Boolean)
      .join('-');
    const payload = {};
    const name = String(profileInfo.facultyName || '').trim();
    if (name) payload.display_name = name;
    const dept = String(profileInfo.department || '').trim();
    if (dept) payload.department = dept;
    const desig = String(profileInfo.designation || '').trim();
    if (desig) payload.designation = desig;
    const mobile = String(profileInfo.mobile || '').trim().replace(/\s/g, '');
    if (mobile) {
      if (!/^\+?\d{10,15}$/.test(mobile)) throw new Error('Enter a valid 10-15 digit mobile number.');
      payload.mobile = mobile;
    }
    const pEmail = String(profileInfo.email || '').trim();
    if (pEmail) payload.personal_email = pEmail;
    const oEmail = String(profileInfo.officialEmail || '').trim();
    if (oEmail) payload.official_email = oEmail;
    if (telephone) payload.residential_telephone = telephone;
    if (profileInfo.dateOfAppointment) payload.date_of_joining = profileInfo.dateOfAppointment;

    const personal = {};
    if (dobStr) personal.date_of_birth = dobStr;
    const gender = String(profileInfo.gender || '').trim().toUpperCase();
    if (gender) personal.gender = gender;
    const nat = String(profileInfo.nationality || '').trim();
    if (nat) personal.nationality = nat;
    const dom = String(profileInfo.domicileState || '').trim();
    if (dom) personal.domicile_state = dom;
    const cat = String(profileInfo.category || '').trim();
    if (cat) personal.constitutional_category = cat;
    if (Object.keys(personal).length) payload.personal = personal;

    const perm = buildAddressBlock(profileInfo.permanentAddress);
    if (perm) payload.permanent_address = perm;
    const corr = buildAddressBlock(profileInfo.correspondenceAddress);
    if (corr) payload.correspondence_address = corr;
    return payload;
  };

  const buildBankPayload = () => {
    const payload = buildProfilePayload();
    const bankName = String(bankDetail.bankName || '').trim();
    const branch = String(bankDetail.branchName || '').trim();
    const ifsc = String(bankDetail.ifscCode || '').trim().toUpperCase();
    const accRaw = String(bankDetail.accountNo || '').trim();
    const hasAccount = accRaw && !accRaw.includes('X');
    if (!bankName && !branch && !ifsc && !hasAccount) return payload; // nothing to save
    if (ifsc && !/^[A-Z]{4}0[A-Z0-9]{6}$/.test(ifsc)) throw new Error('IFSC must look like SBIN0001234.');
    if (hasAccount && !/^\d{9,18}$/.test(accRaw.replace(/\D/g, ''))) {
      throw new Error('Account number must be 9-18 digits.');
    }
    payload.bank = {};
    const holder = String(profileInfo.facultyName || '').trim();
    if (holder) payload.bank.account_holder_name = holder;
    if (bankName) payload.bank.bank_name = bankName;
    if (branch) payload.bank.branch_name = branch;
    if (ifsc) payload.bank.ifsc_code = ifsc;
    // Never send the masked display value back as a new account number.
    if (hasAccount) payload.bank.account_number = accRaw;
    return payload;
  };

  const persistAndLock = async (payload, tabName) => {
    if (!isOwnProfile || !isEditing || saving) return;
    setSaving(true);
    try {
      const res = await facultyApi.updateMyProfile(payload);
      const changed = res.data?.changed?.length ? `: ${res.data.changed.join(', ')}` : '';
      showSuccess(`${tabName} updated successfully${changed}.`);
      setIsEditing(false);
      setSnapshot(null);
      await loadFacultyData();
    } catch (err) {
      const data = err.response?.data;
      const msg =
        data?.detail ||
        (data && typeof data === 'object'
          ? Object.entries(data)
              .map(([k, v]) => `${k}: ${Array.isArray(v) ? v.join(' ') : v}`)
              .join(' ')
          : null) ||
        'Failed to save profile. Check highlighted values and try again.';
      showError(msg);
    } finally {
      setSaving(false);
    }
  };

  const buildQualificationBlock = (q) => {
    const course = String(q.course === 'Other' ? q.otherCourse : q.course || '').trim();
    const branch = String(q.branchName || '').trim();
    const cls = String(q.classObtained || '').trim();
    const uni = String(q.university === 'Other' ? q.otherUniversity : q.university || '').trim();
    const py = String(q.passingYear || '').trim();
    if (!course && !branch && !cls && !uni && !py) return undefined; // untouched = omit
    if (!course) throw new Error('Qualification course is required.');
    if (!uni || uni.toLowerCase() === 'select') throw new Error('Qualification university is required.');
    if (!py) throw new Error('Qualification passing year is required.');
    if (!/^\d{4}$/.test(py)) throw new Error('Passing year must be YYYY.');
    const y = Number(py);
    const cy = new Date().getFullYear();
    if (y < 1950 || y > cy + 1) throw new Error(`Passing year must be 1950-${cy + 1}.`);
    return {
      degree_name: course,
      specialization: branch,
      class_or_grade: cls,
      institution_university: uni,
      passing_year: py,
    };
  };

  const buildQualificationsPayload = () => {
    const out = {};
    const g = buildQualificationBlock(qualifications.graduation);
    if (g) out.graduation = g;
    const pg = buildQualificationBlock(qualifications.postGraduation);
    if (pg) out.post_graduation = pg;
    const phd = buildQualificationBlock(qualifications.phd);
    if (phd) out.phd = phd;
    const oth = buildQualificationBlock(qualifications.other);
    if (oth) out.other = oth;
    if (!Object.keys(out).length) throw new Error('Fill at least one qualification block (course + university + passing year).');
    return { qualifications: out };
  };

  const buildResearchPayload = () => {
    const num = (v, label) => {
      const s = String(v ?? '').trim();
      if (s === '') return undefined;
      const n = Number(s);
      if (!Number.isInteger(n) || n < 0 || n > 100000) throw new Error(`${label} must be 0-100000.`);
      return n;
    };
    const rp = {};
    const n1 = num(academicDetail.nationalPapers, 'National papers');
    if (n1 !== undefined) rp.national_journal_papers = n1;
    const n2 = num(academicDetail.internationalPapers, 'International papers');
    if (n2 !== undefined) rp.international_journal_papers = n2;
    const n3 = num(academicDetail.conferenceNational, 'Conference national papers');
    if (n3 !== undefined) rp.national_conference_papers = n3;
    const n4 = num(academicDetail.conferenceInternational, 'Conference international papers');
    if (n4 !== undefined) rp.international_conference_papers = n4;
    ['booksPatents', 'professionalMembership', 'consultancyActivities', 'awards', 'grantsFetched', 'interactionInstitution'].forEach((k) => {
      const map = {
        booksPatents: 'books_patents', professionalMembership: 'professional_membership',
        consultancyActivities: 'consultancy_activities', awards: 'awards',
        grantsFetched: 'grants_fetched', interactionInstitution: 'interaction_institution',
      };
      const v = String(academicDetail[k] || '').trim();
      if (v) {
        if (v.length > 5000) throw new Error(`${k} too long (max 5000 chars).`);
        rp[map[k]] = v;
      }
    });
    if (!Object.keys(rp).length) throw new Error('Fill at least one research field.');
    return { research_profile: rp };
  };

  const buildDocumentsPayload = () => {
    // Numbers go via PATCH (encrypted at rest); files go via multipart upload
    // after PATCH (see handleSaveAll). Filenames in state are just picker labels.
    const aad = String(documents.aadhaarNumber || '').trim().replace(/\s/g, '');
    const pan = String(documents.panNumber || '').trim().toUpperCase();
    const hasFile = documents.passportPhotoFile || documents.signatureFile || documents.aadhaarFile || documents.panFile;
    if (!aad && !pan && !hasFile) {
      throw new Error('Fill Aadhaar/PAN numbers or pick files.');
    }
    if (aad && !/^[2-9]\d{11}$/.test(aad)) throw new Error('Aadhaar must be 12 digits starting 2-9.');
    if (pan && !/^[A-Z]{5}[0-9]{4}[A-Z]$/.test(pan)) throw new Error('PAN must look like ABCDE1234F.');
    const id = {};
    if (aad) id.aadhaar_number = aad;
    if (pan) id.pan_number = pan;
    if (!Object.keys(id).length) return null; // files only — PATCH has nothing to do
    return { identity_documents: id };
  };

  // Single-save: one Edit unlocks every tab, one header Save persists
  // profile + bank + qualifications + research + documents atomically.
  // Untouched sections are omitted (not errors); partial/invalid input aborts.
  const buildFullPayload = () => {
    const payload = buildProfilePayload();
    // Bank (omit when untouched; never echo masked X number).
    try {
      const bankOnly = buildBankPayload();
      if (bankOnly.bank && Object.keys(bankOnly.bank).length) payload.bank = bankOnly.bank;
    } catch (e) {
      throw e;
    }
    const soft = (fn) => {
      try {
        return fn();
      } catch (e) {
        const msg = e?.message || '';
        if (/Fill at least one|Fill Aadhaar\/PAN/.test(msg)) return null; // untouched section
        throw e;
      }
    };
    const q = soft(buildQualificationsPayload);
    if (q?.qualifications) payload.qualifications = q.qualifications;
    const r = soft(buildResearchPayload);
    if (r?.research_profile) payload.research_profile = r.research_profile;
    const d = soft(buildDocumentsPayload);
    if (d?.identity_documents) payload.identity_documents = d.identity_documents;
    return payload;
  };

  const handleSaveAll = async () => {
    if (!isEditing) {
      showError('Click Edit Profile first to make changes.');
      return;
    }
    let payload;
    try {
      payload = buildFullPayload();
    } catch (e) {
      showError(e?.message || 'Fix the highlighted values and try again.');
      return;
    }
    const pendingFiles = [
      documents.passportPhotoFile ? ['PHOTO', documents.passportPhotoFile] : null,
      documents.signatureFile ? ['SIGNATURE', documents.signatureFile] : null,
      documents.aadhaarFile ? ['AADHAAR', documents.aadhaarFile] : null,
      documents.panFile ? ['PAN', documents.panFile] : null,
    ].filter(Boolean);
    if ((!payload || !Object.keys(payload).length) && !pendingFiles.length) {
      showError('Nothing to save — fill at least one field or pick a file.');
      return;
    }
    if (!isOwnProfile || saving) return;
    setSaving(true);
    try {
      const changed = [];
      if (payload && Object.keys(payload).length) {
        const res = await facultyApi.updateMyProfile(payload);
        changed.push(...(res.data?.changed || []));
      }
      const failedUploads = [];
      for (const [docType, file] of pendingFiles) {
        try {
          await facultyApi.uploadMyDocument(docType, file);
          changed.push(`documents.${docType.toLowerCase()}_file`);
        } catch (uerr) {
          const ud = uerr.response?.data;
          const umsg = ud?.file
            ? `${docType}: ${Array.isArray(ud.file) ? ud.file.join(' ') : ud.file}`
            : ud?.detail || `${docType} upload failed.`;
          failedUploads.push(umsg);
        }
      }
      if (failedUploads.length) {
        showError(`Profile saved but uploads failed: ${failedUploads.join(' | ')}`);
      } else if (!changed.length) {
        showSuccess('Already up to date — no changes detected.');
      } else {
        showSuccess(`Profile saved successfully: ${changed.join(', ')}.`);
      }
      setIsEditing(false);
      setSnapshot(null);
      await loadFacultyData();
    } catch (err) {
      const data = err.response?.data;
      const msg =
        data?.detail ||
        (data && typeof data === 'object'
          ? Object.entries(data)
              .map(([k, v]) => `${k}: ${Array.isArray(v) ? v.join(' ') : v}`)
              .join(' ')
          : null) ||
        'Failed to save profile. Check highlighted values and try again.';
      showError(msg);
    } finally {
      setSaving(false);
    }
  };

  const handleSameAsPermanentToggle = (checked) => {
    if (!isEditing) return;
    setSameAsPermanent(checked);
    if (checked) {
      setProfileInfo((prev) => ({
        ...prev,
        correspondenceAddress: { ...prev.permanentAddress },
      }));
    }
  };

  const tabs = [
    { id: 'profile-info', label: 'Profile Information', icon: User },
    { id: 'qualification-detail', label: 'Qualification Detail', icon: Award },
    { id: 'academic-detail', label: 'Academic Detail', icon: BookOpen },
    { id: 'bank-detail', label: 'Bank Detail', icon: Landmark },
    { id: 'documents', label: 'Documents', icon: FileText },
  ];

  // Password change is strictly self-service: the backend ChangePasswordView
  // only ever updates request.user. The Security tab moved out of the tabs
  // and now lives at /profile/security (sidebar link), which every
  // non-student role reaches through its own sidebar entry.
  const isOwnProfile = !id;
  // Option A (strict): student-only cannot open directory portfolios.
  // Backend also returns 403. Own-profile path (!id) never happens for
  // students (ProfileDispatcher sends them to StudentProfilePage).
  if (id && isStudentOnly) {
    return (
      <>
        <PageHeader
          breadcrumbs={[
            { label: 'Home', to: '/dashboard' },
            { label: 'Faculty Directory', to: '/admin/faculty' },
            { label: 'Faculty Profile' },
          ]}
          title="Faculty Profile"
        />
        <div className="edvana-banner-overlap">
          <div className="edvana-card">
            <div className="edvana-card-body" style={{ padding: '2rem', textAlign: 'center' }}>
              <h3 style={{ fontSize: '1rem', fontWeight: 700, color: '#0f172a' }}>Not allowed</h3>
              <p style={{ fontSize: '0.875rem', color: '#64748b', marginTop: '0.5rem' }}>
                Faculty directory is staff-only. Student logins cannot view faculty contact details.
              </p>
            </div>
          </div>
        </div>
      </>
    );
  }
  // Edit-lock: directory views are always read-only; own profile starts
  // locked and only unlocks after Edit is clicked. Accounts with no Faculty
  // row (404) can never edit.
  const canEdit = isOwnProfile && !noProfile;
  const fieldsLocked = !isEditing;
  const visibleTabs = tabs;

  return (
    <>
      <PageHeader
        breadcrumbs={[
          { label: 'Home', to: '/dashboard' },
          ...(id ? [{ label: 'Faculty Directory', to: '/admin/faculty' }] : []),
          { label: 'Faculty Profile' },
        ]}
        title="Faculty Profile"
        actions={
          <div style={{ display: 'flex', gap: '0.625rem', flexWrap: 'wrap' }}>
            {canEdit && !isEditing && (
              <button
                className="edvana-btn edvana-btn-primary"
                onClick={startEditing}
                style={{ backgroundColor: '#ffffff', color: '#1d4ed8', borderColor: '#ffffff', fontWeight: 700 }}
                title="Unlock all fields for editing"
              >
                <span>Edit Profile</span>
              </button>
            )}
            {canEdit && isEditing && (
              <>
                <button
                  className="edvana-btn edvana-btn-primary"
                  onClick={cancelEditing}
                  disabled={saving}
                  style={{ backgroundColor: 'rgba(255,255,255,0.18)', color: '#ffffff', borderColor: 'rgba(255,255,255,0.35)' }}
                  title="Discard changes and lock again"
                >
                  <span>Cancel</span>
                </button>
                <button
                  className="edvana-btn edvana-btn-primary"
                  onClick={handleSaveAll}
                  disabled={saving}
                  style={{ backgroundColor: '#ffffff', color: '#1d4ed8', borderColor: '#ffffff', fontWeight: 700 }}
                  title="Save everything across all tabs and lock the profile"
                >
                  <CheckCircle2 size={16} />
                  <span>{saving ? 'Saving…' : 'Save All Changes'}</span>
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

      {/* Main Container Overlapping Banner matching Student Profile */}
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

        {/* Lock-state banner */}
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
            marginTop: '1rem',
          }}
        >
          <Info size={18} style={{ color: isEditing ? '#2563eb' : '#64748b', flexShrink: 0 }} />
          <span>
            {id
              ? 'Read-only view. This faculty record can only be edited by its owner from their own profile.'
              : noProfile
                ? `No faculty record is linked to this login (${user?.username || 'account'}). Use the Security tab to change your password; ask Sysadmin to onboard a faculty profile (POST /faculty/) if this account needs one.`
                : isEditing
                  ? 'Editing unlocked. Change anything on any tab, then press Save All Changes at the top once to save everything and lock again.'
                  : 'Profile is locked. Click Edit Profile to start editing.'}
          </span>
        </div>

        {/* Success Toast */}
        {successMessage && (
          <div
            style={{
              backgroundColor: '#ECFDF5',
              border: '1px solid #10B981',
              color: '#065F46',
              padding: '0.875rem 1.25rem',
              borderRadius: '8px',
              marginTop: '1rem',
              display: 'flex',
              alignItems: 'center',
              gap: '0.75rem',
              fontWeight: 500,
              fontSize: '0.875rem',
            }}
          >
            <CheckCircle2 size={18} color="#10B981" />
            <span>{successMessage}</span>
          </div>
        )}

        {/* Error Toast */}
        {errorMessage && (
          <div
            style={{
              backgroundColor: '#FEF2F2',
              border: '1px solid #FCA5A5',
              color: '#991B1B',
              padding: '0.875rem 1.25rem',
              borderRadius: '8px',
              marginTop: '1rem',
              display: 'flex',
              alignItems: 'center',
              gap: '0.75rem',
              fontWeight: 500,
              fontSize: '0.875rem',
            }}
          >
            <AlertCircle size={18} color="#DC2626" />
            <span>{errorMessage}</span>
          </div>
        )}

        {/* Tab 1: Profile Information */}
        {activeTab === 'profile-info' && (
          <div style={{ marginTop: '1.25rem', display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
            <fieldset disabled={fieldsLocked || saving} style={{ border: 'none', padding: 0, margin: 0, minWidth: 0, display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
            {/* Card 1: Department & Designation */}
            <div className="profile-section-card">
              <h2 className="profile-section-title">Department & Designation</h2>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '1.25rem' }}>
                <div>
                  <label className="profile-field-label">
                    Department <span className="req-star">*</span>
                  </label>
                  <div style={{ position: 'relative' }}>
                    <select
                      className="profile-field-select"
                      value={profileInfo.department}
                      onChange={(e) => setProfileInfo({ ...profileInfo, department: e.target.value })}
                    >
                      <option value="">{departments.length ? 'Select Department' : 'Loading departments…'}</option>
                      {departments.map((d) => {
                        const name = typeof d === 'string' ? d : d.name;
                        return (
                          <option key={typeof d === 'string' ? d : d.id || d.name} value={name}>{name}</option>
                        );
                      })}
                    </select>
                    <ChevronDown size={16} className="profile-select-icon" />
                  </div>
                </div>

                <div>
                  <label className="profile-field-label">
                    Designation <span className="req-star">*</span>
                  </label>
                  <div style={{ position: 'relative' }}>
                    <select
                      className="profile-field-select"
                      value={profileInfo.designation}
                      onChange={(e) => setProfileInfo({ ...profileInfo, designation: e.target.value })}
                    >
                      <option value="">Select Designation</option>
                      {DESIGNATIONS.map((des) => (
                        <option key={des} value={des}>{des}</option>
                      ))}
                    </select>
                    <ChevronDown size={16} className="profile-select-icon" />
                  </div>
                </div>
              </div>
            </div>

            {/* Card 2: Personal Information */}
            <div className="profile-section-card">
              <h2 className="profile-section-title">Personal Information</h2>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
                {/* Faculty Name & DOB */}
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '1.25rem' }}>
                  <div>
                    <label className="profile-field-label">
                      Faculty Name <span className="req-star">*</span>
                    </label>
                    <input
                      type="text"
                      className="profile-field-input"
                      value={profileInfo.facultyName}
                      onChange={(e) => setProfileInfo({ ...profileInfo, facultyName: e.target.value })}
                    />
                  </div>

                  <div>
                    <label className="profile-field-label">
                      Date of Birth <span className="req-star">*</span>
                    </label>
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1.5fr 1fr', gap: '0.5rem' }}>
                      <div style={{ position: 'relative' }}>
                        <select
                          className="profile-field-select"
                          value={profileInfo.dobDay}
                          onChange={(e) => setProfileInfo({ ...profileInfo, dobDay: e.target.value })}
                        >
                          <option value="">Day</option>
                          {DAYS.map((d) => (
                            <option key={d} value={d}>{d}</option>
                          ))}
                        </select>
                        <ChevronDown size={14} className="profile-select-icon" />
                      </div>
                      <div style={{ position: 'relative' }}>
                        <select
                          className="profile-field-select"
                          value={profileInfo.dobMonth}
                          onChange={(e) => setProfileInfo({ ...profileInfo, dobMonth: e.target.value })}
                        >
                          <option value="">Month</option>
                          {MONTHS.map((m) => (
                            <option key={m} value={m}>{m}</option>
                          ))}
                        </select>
                        <ChevronDown size={14} className="profile-select-icon" />
                      </div>
                      <div style={{ position: 'relative' }}>
                        <select
                          className="profile-field-select"
                          value={profileInfo.dobYear}
                          onChange={(e) => setProfileInfo({ ...profileInfo, dobYear: e.target.value })}
                        >
                          <option value="">Year</option>
                          {YEARS.map((y) => (
                            <option key={y} value={y}>{y}</option>
                          ))}
                        </select>
                        <ChevronDown size={14} className="profile-select-icon" />
                      </div>
                    </div>
                  </div>
                </div>

                {/* Gender, Nationality, Domicile */}
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: '1.25rem' }}>
                  <div>
                    <label className="profile-field-label">
                      Gender
                    </label>
                    <div style={{ position: 'relative' }}>
                      <select
                        className="profile-field-select"
                        value={profileInfo.gender}
                        onChange={(e) => setProfileInfo({ ...profileInfo, gender: e.target.value })}
                      >
                        <option value="">Select Gender</option>
                        <option value="Male">Male</option>
                        <option value="Female">Female</option>
                        <option value="Other">Other</option>
                      </select>
                      <ChevronDown size={16} className="profile-select-icon" />
                    </div>
                  </div>

                  <div>
                    <label className="profile-field-label">
                      Nationality
                    </label>
                    <div style={{ position: 'relative' }}>
                      <select
                        className="profile-field-select"
                        value={profileInfo.nationality}
                        onChange={(e) => setProfileInfo({ ...profileInfo, nationality: e.target.value })}
                      >
                        <option value="">Select Nationality</option>
                        <option value="Indian">Indian</option>
                        <option value="Other">Other</option>
                      </select>
                      <ChevronDown size={16} className="profile-select-icon" />
                    </div>
                  </div>

                  <div>
                    <label className="profile-field-label">
                      Domicile State
                    </label>
                    <div style={{ position: 'relative' }}>
                      <select
                        className="profile-field-select"
                        value={profileInfo.domicileState}
                        onChange={(e) => setProfileInfo({ ...profileInfo, domicileState: e.target.value })}
                      >
                        <option value="">Select State</option>
                        {STATES.map((st) => (
                          <option key={st} value={st}>{st}</option>
                        ))}
                      </select>
                      <ChevronDown size={16} className="profile-select-icon" />
                    </div>
                  </div>
                </div>

                {/* Current subjects: read-only server truth (assigned by HOD).
                    No self-typed Subjects Taught box — it had no storage and
                    never survived refresh. */}
                <div className="profile-section-card" style={{ backgroundColor: '#F8FAFC' }}>
                  <h2 className="profile-section-title" style={{ marginBottom: '0.5rem' }}>Current Subjects (assigned by HOD)</h2>
                  {(serverProfile?.teaching_assignments || []).filter((a) => a.is_active).length ? (
                    <ul style={{ margin: 0, paddingLeft: '1.25rem', fontSize: '0.875rem', color: '#0F172A' }}>
                      {(serverProfile.teaching_assignments || []).filter((a) => a.is_active).map((a) => (
                        <li key={a.id}>{a.subject_code} — {a.subject_name} ({a.division_name || a.division})</li>
                      ))}
                    </ul>
                  ) : (
                    <p style={{ margin: 0, fontSize: '0.8125rem', color: '#64748B' }}>
                      No active subject assignments. Your HOD assigns subjects from Academic Structure.
                    </p>
                  )}
                </div>

                {/* Date of Appointment, Category */}
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: '1.25rem' }}>
                  <div>
                    <label className="profile-field-label">
                      Date of Appointment <span className="req-star">*</span>
                    </label>
                    <input
                      type="date"
                      className="profile-field-input"
                      value={profileInfo.dateOfAppointment}
                      onChange={(e) => setProfileInfo({ ...profileInfo, dateOfAppointment: e.target.value })}
                    />
                  </div>

                  <div>
                    <label className="profile-field-label">
                      Constitutional Category
                    </label>
                    <div style={{ position: 'relative' }}>
                      <select
                        className="profile-field-select"
                        value={profileInfo.category}
                        onChange={(e) => setProfileInfo({ ...profileInfo, category: e.target.value })}
                      >
                        <option value="">Select Category</option>
                        {CATEGORIES.map((cat) => (
                          <option key={cat} value={cat}>{cat}</option>
                        ))}
                      </select>
                      <ChevronDown size={16} className="profile-select-icon" />
                    </div>
                  </div>
                </div>

                {/* Email, Mobile, Residential Telephone */}
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: '1.25rem' }}>
                  <div>
                    <label className="profile-field-label">
                      Email ID <span className="req-star">*</span>
                    </label>
                    <input
                      type="email"
                      className="profile-field-input"
                      value={profileInfo.email}
                      onChange={(e) => setProfileInfo({ ...profileInfo, email: e.target.value })}
                    />
                  </div>

                  <div>
                    <label className="profile-field-label">
                      Mobile No. <span className="req-star">*</span>
                    </label>
                    <input
                      type="tel"
                      className="profile-field-input"
                      value={profileInfo.mobile}
                      onChange={(e) => setProfileInfo({ ...profileInfo, mobile: e.target.value })}
                    />
                  </div>

                  <div>
                    <label className="profile-field-label">
                      Residential Telephone No. <span className="req-star">*</span>
                    </label>
                    <div style={{ display: 'grid', gridTemplateColumns: '80px 1fr', gap: '0.5rem' }}>
                      <input
                        type="text"
                        placeholder="STD"
                        className="profile-field-input"
                        value={profileInfo.resTelephoneStd}
                        onChange={(e) => setProfileInfo({ ...profileInfo, resTelephoneStd: e.target.value })}
                      />
                      <input
                        type="text"
                        placeholder="Telephone Number"
                        className="profile-field-input"
                        value={profileInfo.resTelephoneNum}
                        onChange={(e) => setProfileInfo({ ...profileInfo, resTelephoneNum: e.target.value })}
                      />
                    </div>
                  </div>
                </div>

                {/* Official Email */}
                <div style={{ maxWidth: '420px' }}>
                  <label className="profile-field-label">
                    Official Email ID <span className="req-star">*</span>
                  </label>
                  <input
                    type="email"
                    className="profile-field-input"
                    value={profileInfo.officialEmail}
                    onChange={(e) => setProfileInfo({ ...profileInfo, officialEmail: e.target.value })}
                  />
                </div>
              </div>
            </div>

            {/* Card 3: Permanent Address (optional — leave blank to keep existing) */}
            <div className="profile-section-card">
              <h2 className="profile-section-title">Permanent Address</h2>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
                <div>
                  <label className="profile-field-label">
                    Address
                  </label>
                  <textarea
                    rows={3}
                    className="profile-field-textarea"
                    value={profileInfo.permanentAddress.address}
                    onChange={(e) => {
                      const newAddress = e.target.value;
                      setProfileInfo((prev) => {
                        const updated = {
                          ...prev,
                          permanentAddress: { ...prev.permanentAddress, address: newAddress },
                        };
                        if (sameAsPermanent) {
                          updated.correspondenceAddress = { ...updated.permanentAddress };
                        }
                        return updated;
                      });
                    }}
                  />
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: '1.25rem' }}>
                  <div>
                    <label className="profile-field-label">
                      District
                    </label>
                    <input
                      type="text"
                      className="profile-field-input"
                      value={profileInfo.permanentAddress.district}
                      onChange={(e) => {
                        const val = e.target.value;
                        setProfileInfo((prev) => {
                          const updated = {
                            ...prev,
                            permanentAddress: { ...prev.permanentAddress, district: val },
                          };
                          if (sameAsPermanent) {
                            updated.correspondenceAddress = { ...updated.permanentAddress };
                          }
                          return updated;
                        });
                      }}
                    />
                  </div>

                  <div>
                    <label className="profile-field-label">
                      State
                    </label>
                    <div style={{ position: 'relative' }}>
                      <select
                        className="profile-field-select"
                        value={profileInfo.permanentAddress.state}
                        onChange={(e) => {
                          const val = e.target.value;
                          setProfileInfo((prev) => {
                            const updated = {
                              ...prev,
                              permanentAddress: { ...prev.permanentAddress, state: val },
                            };
                            if (sameAsPermanent) {
                              updated.correspondenceAddress = { ...updated.permanentAddress };
                            }
                            return updated;
                          });
                        }}
                      >
                        <option value="">Select State</option>
                        {STATES.map((st) => (
                          <option key={st} value={st}>{st}</option>
                        ))}
                      </select>
                      <ChevronDown size={16} className="profile-select-icon" />
                    </div>
                  </div>

                  <div>
                    <label className="profile-field-label">
                      Pincode
                    </label>
                    <input
                      type="text"
                      className="profile-field-input"
                      value={profileInfo.permanentAddress.pincode}
                      onChange={(e) => {
                        const val = e.target.value;
                        setProfileInfo((prev) => {
                          const updated = {
                            ...prev,
                            permanentAddress: { ...prev.permanentAddress, pincode: val },
                          };
                          if (sameAsPermanent) {
                            updated.correspondenceAddress = { ...updated.permanentAddress };
                          }
                          return updated;
                        });
                      }}
                    />
                  </div>
                </div>
              </div>
            </div>

            {/* Card 4: Correspondence Address */}
            <div className="profile-section-card">
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
                <h2 className="profile-section-title" style={{ margin: 0 }}>Correspondence Address</h2>
                <label style={{ display: 'flex', alignItems: 'center', gap: '0.625rem', cursor: 'pointer', userSelect: 'none' }}>
                  <input
                    type="checkbox"
                    checked={sameAsPermanent}
                    onChange={(e) => handleSameAsPermanentToggle(e.target.checked)}
                    style={{
                      width: '18px',
                      height: '18px',
                      accentColor: '#1E60DC',
                      cursor: 'pointer',
                    }}
                  />
                  <span style={{ fontSize: '0.85rem', color: '#475569', fontWeight: 500 }}>
                    Correspondence Address is same as Permanent Address
                  </span>
                </label>
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
                <div>
                  <label className="profile-field-label">
                    Address
                  </label>
                  <textarea
                    rows={3}
                    disabled={sameAsPermanent}
                    className="profile-field-textarea"
                    value={profileInfo.correspondenceAddress.address}
                    onChange={(e) =>
                      setProfileInfo({
                        ...profileInfo,
                        correspondenceAddress: { ...profileInfo.correspondenceAddress, address: e.target.value },
                      })
                    }
                  />
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: '1.25rem' }}>
                  <div>
                    <label className="profile-field-label">
                      District
                    </label>
                    <input
                      type="text"
                      disabled={sameAsPermanent}
                      className="profile-field-input"
                      value={profileInfo.correspondenceAddress.district}
                      onChange={(e) =>
                        setProfileInfo({
                          ...profileInfo,
                          correspondenceAddress: { ...profileInfo.correspondenceAddress, district: e.target.value },
                        })
                      }
                    />
                  </div>

                  <div>
                    <label className="profile-field-label">
                      State
                    </label>
                    <div style={{ position: 'relative' }}>
                      <select
                        disabled={sameAsPermanent}
                        className="profile-field-select"
                        value={profileInfo.correspondenceAddress.state}
                        onChange={(e) =>
                          setProfileInfo({
                            ...profileInfo,
                            correspondenceAddress: { ...profileInfo.correspondenceAddress, state: e.target.value },
                          })
                        }
                      >
                        <option value="">Select State</option>
                        {STATES.map((st) => (
                          <option key={st} value={st}>{st}</option>
                        ))}
                      </select>
                      <ChevronDown size={16} className="profile-select-icon" />
                    </div>
                  </div>

                  <div>
                    <label className="profile-field-label">
                      Pincode
                    </label>
                    <input
                      type="text"
                      disabled={sameAsPermanent}
                      className="profile-field-input"
                      value={profileInfo.correspondenceAddress.pincode}
                      onChange={(e) =>
                        setProfileInfo({
                          ...profileInfo,
                          correspondenceAddress: { ...profileInfo.correspondenceAddress, pincode: e.target.value },
                        })
                      }
                    />
                  </div>
                </div>
              </div>
            </div>

            </fieldset>

            <div style={{ display: 'flex', justifyContent: 'center', marginTop: '0.5rem' }}>
              <p style={{ fontSize: '0.8125rem', color: '#64748B', margin: 0 }}>
                Edit anything on any tab, then press <strong>Save All Changes</strong> at the top once — everything saves together.
              </p>
            </div>
          </div>
        )}

        {/* Tab 2: Qualification Detail */}
        {activeTab === 'qualification-detail' && (
          <div style={{ marginTop: '1.25rem', display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
            <fieldset disabled={fieldsLocked || saving} style={{ border: 'none', padding: 0, margin: 0, minWidth: 0, display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
            {/* Card 1: Graduation Degree detail */}
            <div className="profile-section-card">
              <h2 className="profile-section-title">Graduation Degree detail</h2>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '1.25rem' }}>
                <div>
                  <label className="profile-field-label">Course</label>
                  <div style={{ position: 'relative' }}>
                    <select
                      className="profile-field-select"
                      value={qualifications.graduation.course}
                      onChange={(e) =>
                        setQualifications({
                          ...qualifications,
                          graduation: { ...qualifications.graduation, course: e.target.value },
                        })
                      }
                    >
                      <option value="">Select Course</option>
                      <option value="B.E.">B.E.</option>
                      <option value="B.Tech">B.Tech</option>
                      <option value="B.Sc">B.Sc</option>
                      <option value="Other">Other</option>
                    </select>
                    <ChevronDown size={16} className="profile-select-icon" />
                  </div>
                  {qualifications.graduation.course === 'Other' && (
                    <input
                      type="text"
                      placeholder="ENTER COURSE NAME"
                      className="profile-field-input"
                      style={{ marginTop: '0.75rem' }}
                      value={qualifications.graduation.otherCourse}
                      onChange={(e) =>
                        setQualifications({
                          ...qualifications,
                          graduation: { ...qualifications.graduation, otherCourse: e.target.value },
                        })
                      }
                    />
                  )}
                </div>

                <div>
                  <label className="profile-field-label">Branch Name</label>
                  <input
                    type="text"
                    className="profile-field-input"
                    value={qualifications.graduation.branchName}
                    onChange={(e) =>
                      setQualifications({
                        ...qualifications,
                        graduation: { ...qualifications.graduation, branchName: e.target.value },
                      })
                    }
                  />
                </div>

                <div>
                  <label className="profile-field-label">Class Obtained</label>
                  <div style={{ position: 'relative' }}>
                    <select
                      className="profile-field-select"
                      value={qualifications.graduation.classObtained}
                      onChange={(e) =>
                        setQualifications({
                          ...qualifications,
                          graduation: { ...qualifications.graduation, classObtained: e.target.value },
                        })
                      }
                    >
                      <option value="">Select Class</option>
                      {CLASSES.map((c) => (
                        <option key={c} value={c}>{c}</option>
                      ))}
                    </select>
                    <ChevronDown size={16} className="profile-select-icon" />
                  </div>
                </div>

                <div>
                  <label className="profile-field-label">University / Board</label>
                  <div style={{ position: 'relative' }}>
                    <select
                      className="profile-field-select"
                      value={qualifications.graduation.university}
                      onChange={(e) =>
                        setQualifications({
                          ...qualifications,
                          graduation: { ...qualifications.graduation, university: e.target.value },
                        })
                      }
                    >
                      <option value="">Select University</option>
                      {UNIVERSITIES.map((u) => (
                        <option key={u} value={u}>{u}</option>
                      ))}
                    </select>
                    <ChevronDown size={16} className="profile-select-icon" />
                  </div>
                  {qualifications.graduation.university === 'Other' && (
                    <input
                      type="text"
                      placeholder="ENTER UNIVERSITY/BOARD NAME"
                      className="profile-field-input"
                      style={{ marginTop: '0.75rem' }}
                      value={qualifications.graduation.otherUniversity}
                      onChange={(e) =>
                        setQualifications({
                          ...qualifications,
                          graduation: { ...qualifications.graduation, otherUniversity: e.target.value },
                        })
                      }
                    />
                  )}
                </div>

                <div>
                  <label className="profile-field-label">Passing Year <span className="req-star">*</span></label>
                  <input
                    type="number"
                    min="1950"
                    max={new Date().getFullYear() + 1}
                    placeholder="YYYY"
                    className="profile-field-input"
                    value={qualifications.graduation.passingYear}
                    onChange={(e) =>
                      setQualifications({
                        ...qualifications,
                        graduation: { ...qualifications.graduation, passingYear: e.target.value },
                      })
                    }
                  />
                </div>
              </div>
            </div>

            {/* Card 2: Post Graduation detail */}
            <div className="profile-section-card">
              <h2 className="profile-section-title">Post Graduation detail</h2>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '1.25rem' }}>
                <div>
                  <label className="profile-field-label">Course</label>
                  <div style={{ position: 'relative' }}>
                    <select
                      className="profile-field-select"
                      value={qualifications.postGraduation.course}
                      onChange={(e) =>
                        setQualifications({
                          ...qualifications,
                          postGraduation: { ...qualifications.postGraduation, course: e.target.value },
                        })
                      }
                    >
                      <option value="">Select Course</option>
                      <option value="M.E.">M.E.</option>
                      <option value="M.Tech">M.Tech</option>
                      <option value="M.S.">M.S.</option>
                      <option value="Other">Other</option>
                    </select>
                    <ChevronDown size={16} className="profile-select-icon" />
                  </div>
                  {qualifications.postGraduation.course === 'Other' && (
                    <input
                      type="text"
                      placeholder="ENTER COURSE NAME"
                      className="profile-field-input"
                      style={{ marginTop: '0.75rem' }}
                      value={qualifications.postGraduation.otherCourse}
                      onChange={(e) =>
                        setQualifications({
                          ...qualifications,
                          postGraduation: { ...qualifications.postGraduation, otherCourse: e.target.value },
                        })
                      }
                    />
                  )}
                </div>

                <div>
                  <label className="profile-field-label">Branch Name</label>
                  <input
                    type="text"
                    className="profile-field-input"
                    value={qualifications.postGraduation.branchName}
                    onChange={(e) =>
                      setQualifications({
                        ...qualifications,
                        postGraduation: { ...qualifications.postGraduation, branchName: e.target.value },
                      })
                    }
                  />
                </div>

                <div>
                  <label className="profile-field-label">Class Obtained</label>
                  <div style={{ position: 'relative' }}>
                    <select
                      className="profile-field-select"
                      value={qualifications.postGraduation.classObtained}
                      onChange={(e) =>
                        setQualifications({
                          ...qualifications,
                          postGraduation: { ...qualifications.postGraduation, classObtained: e.target.value },
                        })
                      }
                    >
                      <option value="">Select Class</option>
                      {CLASSES.map((c) => (
                        <option key={c} value={c}>{c}</option>
                      ))}
                    </select>
                    <ChevronDown size={16} className="profile-select-icon" />
                  </div>
                </div>

                <div>
                  <label className="profile-field-label">University / Board</label>
                  <div style={{ position: 'relative' }}>
                    <select
                      className="profile-field-select"
                      value={qualifications.postGraduation.university}
                      onChange={(e) =>
                        setQualifications({
                          ...qualifications,
                          postGraduation: { ...qualifications.postGraduation, university: e.target.value },
                        })
                      }
                    >
                      <option value="">Select University</option>
                      {UNIVERSITIES.map((u) => (
                        <option key={u} value={u}>{u}</option>
                      ))}
                    </select>
                    <ChevronDown size={16} className="profile-select-icon" />
                  </div>
                  {qualifications.postGraduation.university === 'Other' && (
                    <input
                      type="text"
                      placeholder="ENTER UNIVERSITY/BOARD NAME"
                      className="profile-field-input"
                      style={{ marginTop: '0.75rem' }}
                      value={qualifications.postGraduation.otherUniversity}
                      onChange={(e) =>
                        setQualifications({
                          ...qualifications,
                          postGraduation: { ...qualifications.postGraduation, otherUniversity: e.target.value },
                        })
                      }
                    />
                  )}
                </div>

                <div>
                  <label className="profile-field-label">Passing Year <span className="req-star">*</span></label>
                  <input
                    type="number"
                    min="1950"
                    max={new Date().getFullYear() + 1}
                    placeholder="YYYY"
                    className="profile-field-input"
                    value={qualifications.postGraduation.passingYear}
                    onChange={(e) =>
                      setQualifications({
                        ...qualifications,
                        postGraduation: { ...qualifications.postGraduation, passingYear: e.target.value },
                      })
                    }
                  />
                </div>
              </div>
            </div>

            {/* Card 3: PhD detail */}
            <div className="profile-section-card">
              <h2 className="profile-section-title">PhD detail</h2>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '1.25rem' }}>
                <div>
                  <label className="profile-field-label">Course</label>
                  <input
                    type="text"
                    className="profile-field-input"
                    value={qualifications.phd.course}
                    onChange={(e) =>
                      setQualifications({
                        ...qualifications,
                        phd: { ...qualifications.phd, course: e.target.value },
                      })
                    }
                  />
                </div>

                <div>
                  <label className="profile-field-label">Branch Name</label>
                  <input
                    type="text"
                    className="profile-field-input"
                    value={qualifications.phd.branchName}
                    onChange={(e) =>
                      setQualifications({
                        ...qualifications,
                        phd: { ...qualifications.phd, branchName: e.target.value },
                      })
                    }
                  />
                </div>

                <div>
                  <label className="profile-field-label">Class Obtained</label>
                  <div style={{ position: 'relative' }}>
                    <select
                      className="profile-field-select"
                      value={qualifications.phd.classObtained}
                      onChange={(e) =>
                        setQualifications({
                          ...qualifications,
                          phd: { ...qualifications.phd, classObtained: e.target.value },
                        })
                      }
                    >
                      <option value="">Select Status</option>
                      <option value="Awarded">Awarded</option>
                      <option value="Pursuing">Pursuing</option>
                      <option value="Submitted">Thesis Submitted</option>
                    </select>
                    <ChevronDown size={16} className="profile-select-icon" />
                  </div>
                </div>

                <div>
                  <label className="profile-field-label">University / Board</label>
                  <input
                    type="text"
                    className="profile-field-input"
                    value={qualifications.phd.university}
                    onChange={(e) =>
                      setQualifications({
                        ...qualifications,
                        phd: { ...qualifications.phd, university: e.target.value },
                      })
                    }
                  />
                </div>

                <div>
                  <label className="profile-field-label">Passing Year <span className="req-star">*</span></label>
                  <input
                    type="number"
                    min="1950"
                    max={new Date().getFullYear() + 1}
                    placeholder="YYYY"
                    className="profile-field-input"
                    value={qualifications.phd.passingYear}
                    onChange={(e) =>
                      setQualifications({
                        ...qualifications,
                        phd: { ...qualifications.phd, passingYear: e.target.value },
                      })
                    }
                  />
                </div>
              </div>
            </div>

            {/* Card 4: Other detail */}
            <div className="profile-section-card">
              <h2 className="profile-section-title">Other detail</h2>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '1.25rem' }}>
                <div>
                  <label className="profile-field-label">Course</label>
                  <input
                    type="text"
                    className="profile-field-input"
                    value={qualifications.other.course}
                    onChange={(e) =>
                      setQualifications({
                        ...qualifications,
                        other: { ...qualifications.other, course: e.target.value },
                      })
                    }
                  />
                </div>

                <div>
                  <label className="profile-field-label">Branch Name</label>
                  <input
                    type="text"
                    className="profile-field-input"
                    value={qualifications.other.branchName}
                    onChange={(e) =>
                      setQualifications({
                        ...qualifications,
                        other: { ...qualifications.other, branchName: e.target.value },
                      })
                    }
                  />
                </div>

                <div>
                  <label className="profile-field-label">Class Obtained</label>
                  <div style={{ position: 'relative' }}>
                    <select
                      className="profile-field-select"
                      value={qualifications.other.classObtained}
                      onChange={(e) =>
                        setQualifications({
                          ...qualifications,
                          other: { ...qualifications.other, classObtained: e.target.value },
                        })
                      }
                    >
                      <option value="">Select Class</option>
                      <option value="Distinction">Distinction</option>
                      <option value="First Class">First Class</option>
                      <option value="Pass">Pass</option>
                    </select>
                    <ChevronDown size={16} className="profile-select-icon" />
                  </div>
                </div>

                <div>
                  <label className="profile-field-label">University / Board</label>
                  <input
                    type="text"
                    className="profile-field-input"
                    value={qualifications.other.university}
                    onChange={(e) =>
                      setQualifications({
                        ...qualifications,
                        other: { ...qualifications.other, university: e.target.value },
                      })
                    }
                  />
                </div>

                <div>
                  <label className="profile-field-label">Passing Year <span className="req-star">*</span></label>
                  <input
                    type="number"
                    min="1950"
                    max={new Date().getFullYear() + 1}
                    placeholder="YYYY"
                    className="profile-field-input"
                    value={qualifications.other.passingYear}
                    onChange={(e) =>
                      setQualifications({
                        ...qualifications,
                        other: { ...qualifications.other, passingYear: e.target.value },
                      })
                    }
                  />
                </div>
              </div>
            </div>

            </fieldset>

            <div style={{ display: 'flex', justifyContent: 'center', marginTop: '0.5rem' }}>
              <p style={{ fontSize: '0.8125rem', color: '#64748B', margin: 0 }}>
                Edit anything on any tab, then press <strong>Save All Changes</strong> at the top once — everything saves together.
              </p>
            </div>
          </div>
        )}

        {/* Tab 3: Academic Detail */}
        {activeTab === 'academic-detail' && (
          <div style={{ marginTop: '1.25rem', display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
            <fieldset disabled={fieldsLocked || saving} style={{ border: 'none', padding: 0, margin: 0, minWidth: 0, display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
            {/* Card 1: Papers Published */}
            <div className="profile-section-card">
              <h2 className="profile-section-title">Papers Published</h2>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '1.25rem' }}>
                <div>
                  <label className="profile-field-label">No. of National Papers</label>
                  <input
                    type="number"
                    min="0"
                    className="profile-field-input"
                    value={academicDetail.nationalPapers}
                    onChange={(e) =>
                      setAcademicDetail({ ...academicDetail, nationalPapers: e.target.value })
                    }
                  />
                </div>

                <div>
                  <label className="profile-field-label">No. of International Papers</label>
                  <input
                    type="number"
                    min="0"
                    className="profile-field-input"
                    value={academicDetail.internationalPapers}
                    onChange={(e) =>
                      setAcademicDetail({ ...academicDetail, internationalPapers: e.target.value })
                    }
                  />
                </div>
              </div>
            </div>

            {/* Card 2: Conference Papers Presented */}
            <div className="profile-section-card">
              <h2 className="profile-section-title">Conference Papers Presented</h2>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '1.25rem' }}>
                <div>
                  <label className="profile-field-label">No. of National Papers</label>
                  <input
                    type="number"
                    min="0"
                    className="profile-field-input"
                    value={academicDetail.conferenceNational}
                    onChange={(e) =>
                      setAcademicDetail({ ...academicDetail, conferenceNational: e.target.value })
                    }
                  />
                </div>

                <div>
                  <label className="profile-field-label">No. of International Papers</label>
                  <input
                    type="number"
                    min="0"
                    className="profile-field-input"
                    value={academicDetail.conferenceInternational}
                    onChange={(e) =>
                      setAcademicDetail({ ...academicDetail, conferenceInternational: e.target.value })
                    }
                  />
                </div>
              </div>
            </div>

            {/* Card 3: Others */}
            <div className="profile-section-card">
              <h2 className="profile-section-title">Others</h2>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '1.25rem' }}>
                <div>
                  <label className="profile-field-label">Books Published/IPRS/Patents</label>
                  <textarea
                    rows={4}
                    className="profile-field-textarea"
                    value={academicDetail.booksPatents}
                    onChange={(e) =>
                      setAcademicDetail({ ...academicDetail, booksPatents: e.target.value })
                    }
                  />
                </div>

                <div>
                  <label className="profile-field-label">Professional Membership</label>
                  <textarea
                    rows={4}
                    className="profile-field-textarea"
                    value={academicDetail.professionalMembership}
                    onChange={(e) =>
                      setAcademicDetail({ ...academicDetail, professionalMembership: e.target.value })
                    }
                  />
                </div>

                <div>
                  <label className="profile-field-label">Consultancy Activities</label>
                  <textarea
                    rows={4}
                    className="profile-field-textarea"
                    value={academicDetail.consultancyActivities}
                    onChange={(e) =>
                      setAcademicDetail({ ...academicDetail, consultancyActivities: e.target.value })
                    }
                  />
                </div>

                <div>
                  <label className="profile-field-label">Awards</label>
                  <textarea
                    rows={4}
                    className="profile-field-textarea"
                    value={academicDetail.awards}
                    onChange={(e) =>
                      setAcademicDetail({ ...academicDetail, awards: e.target.value })
                    }
                  />
                </div>

                <div>
                  <label className="profile-field-label">Grants Fetched</label>
                  <textarea
                    rows={4}
                    className="profile-field-textarea"
                    value={academicDetail.grantsFetched}
                    onChange={(e) =>
                      setAcademicDetail({ ...academicDetail, grantsFetched: e.target.value })
                    }
                  />
                </div>

                <div>
                  <label className="profile-field-label">Interaction With Professional Institution</label>
                  <textarea
                    rows={4}
                    className="profile-field-textarea"
                    value={academicDetail.interactionInstitution}
                    onChange={(e) =>
                      setAcademicDetail({ ...academicDetail, interactionInstitution: e.target.value })
                    }
                  />
                </div>
              </div>
            </div>

            </fieldset>

            <div style={{ display: 'flex', justifyContent: 'center', marginTop: '0.5rem' }}>
              <p style={{ fontSize: '0.8125rem', color: '#64748B', margin: 0, textAlign: 'center' }}>
                Edit anything on any tab, then press <strong>Save All Changes</strong> at the top once — everything saves together.
              </p>
            </div>
          </div>
        )}

        {/* Tab 4: Bank Detail */}
        {activeTab === 'bank-detail' && (
          <div style={{ marginTop: '1.25rem', display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
            <fieldset disabled={fieldsLocked || saving} style={{ border: 'none', padding: 0, margin: 0, minWidth: 0, display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
            <div className="profile-section-card">
              <h2 className="profile-section-title">Update your bank details</h2>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '1.25rem' }}>
                <div>
                  <label className="profile-field-label">
                    Bank Name <span className="req-star">*</span>
                  </label>
                  <input
                    type="text"
                    className="profile-field-input"
                    value={bankDetail.bankName}
                    onChange={(e) => setBankDetail({ ...bankDetail, bankName: e.target.value })}
                  />
                </div>

                <div>
                  <label className="profile-field-label">
                    Branch Name <span className="req-star">*</span>
                  </label>
                  <input
                    type="text"
                    className="profile-field-input"
                    value={bankDetail.branchName}
                    onChange={(e) => setBankDetail({ ...bankDetail, branchName: e.target.value })}
                  />
                </div>

                <div>
                  <label className="profile-field-label">
                    Account No <span className="req-star">*</span>
                  </label>
                  <input
                    type="text"
                    className="profile-field-input"
                    value={bankDetail.accountNo}
                    onChange={(e) => setBankDetail({ ...bankDetail, accountNo: e.target.value })}
                  />
                </div>

                <div>
                  <label className="profile-field-label">
                    IFSC Code <span className="req-star">*</span>
                  </label>
                  <input
                    type="text"
                    className="profile-field-input"
                    value={bankDetail.ifscCode}
                    onChange={(e) => setBankDetail({ ...bankDetail, ifscCode: e.target.value.toUpperCase() })}
                  />
                </div>
              </div>
            </div>

            </fieldset>

            {/* Bottom Save Changes Button */}
            <div style={{ display: 'flex', justifyContent: 'center', marginTop: '0.5rem' }}>
              <p style={{ fontSize: '0.8125rem', color: '#64748B', margin: 0 }}>
                Edit anything on any tab, then press <strong>Save All Changes</strong> at the top once — everything saves together.
              </p>
            </div>
          </div>
        )}

        {/* Tab 5: Documents */}
        {activeTab === 'documents' && (
          <div style={{ marginTop: '1.25rem', display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
            <fieldset disabled={fieldsLocked || saving} style={{ border: 'none', padding: 0, margin: 0, minWidth: 0, display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
            {/* Instructions for upload Photo */}
            <div className="profile-instruction-box">
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontWeight: 600, fontSize: '0.9rem', marginBottom: '0.5rem' }}>
                <Info size={18} color="#D97706" />
                <span>Instructions for upload Photo</span>
              </div>
              <ul style={{ margin: 0, paddingLeft: '1.5rem', fontSize: '0.85rem', lineHeight: '1.6' }}>
                <li>Recent colour photo.</li>
                <li>Photograph must be 3.5 cm in width by 4.5 cm in height without border.</li>
                <li>Photograph has to be taken full face without headgear (unless the applicant habitually wears a headgear in accordance with his/her racial/religious custom but the headgear should not hide the applicant's features).</li>
                <li>Save the image in .jpg format on local machine.</li>
              </ul>
            </div>

            {/* Upload Photo Card */}
            <div className="profile-section-card">
              <h2 className="profile-section-title">Upload Photo</h2>
              <div>
                <label className="profile-field-label">
                  Upload Latest Passport Size Photo <span className="req-star">*</span>
                </label>
                <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', flexWrap: 'wrap' }}>
                  <label className="profile-file-btn">
                    Choose File
                    <input
                      type="file"
                      accept=".jpg,.jpeg,.png"
                      style={{ display: 'none' }}
                      onChange={(e) => {
                        const f = e.target.files[0];
                        if (f) {
                          if (f.size > 150 * 1024) {
                            showError(`Photo too large (${Math.round(f.size / 1024)} KB). Max 150 KB (same as student side).`);
                            e.target.value = '';
                            return;
                          }
                          setDocuments({ ...documents, passportPhotoName: f.name, passportPhotoFile: f });
                        }
                      }}
                    />
                  </label>
                  <span style={{ fontSize: '0.875rem', color: documents.passportPhotoName ? '#0F172A' : '#94A3B8' }}>
                    {documents.passportPhotoName || 'No file chosen'}
                  </span>
                </div>
              </div>
            </div>

            {/* Instructions for upload Signature */}
            <div className="profile-instruction-box">
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontWeight: 600, fontSize: '0.9rem', marginBottom: '0.5rem' }}>
                <Info size={18} color="#D97706" />
                <span>Instructions for upload Signature</span>
              </div>
              <ul style={{ margin: 0, paddingLeft: '1.5rem', fontSize: '0.85rem', lineHeight: '1.6' }}>
                <li>Sign on a white paper with a black pen.</li>
                <li>Scan the signature using a good quality scanner with min. 100dpi so that the file size should not be more than 150kb.</li>
                <li>Save the image in .jpg format on local machine.</li>
              </ul>
            </div>

            {/* Upload Signature Card */}
            <div className="profile-section-card">
              <h2 className="profile-section-title">Upload Signature</h2>
              <div>
                <label className="profile-field-label">
                  Upload Signature <span className="req-star">*</span>
                </label>
                <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', flexWrap: 'wrap' }}>
                  <label className="profile-file-btn">
                    Choose File
                    <input
                      type="file"
                      accept=".jpg,.jpeg,.png"
                      style={{ display: 'none' }}
                      onChange={(e) => {
                        const f = e.target.files[0];
                        if (f) {
                          if (f.size > 150 * 1024) {
                            showError(`Signature too large (${Math.round(f.size / 1024)} KB). Max 150 KB (same as student side).`);
                            e.target.value = '';
                            return;
                          }
                          setDocuments({ ...documents, signatureName: f.name, signatureFile: f });
                        }
                      }}
                    />
                  </label>
                  <span style={{ fontSize: '0.875rem', color: documents.signatureName ? '#0F172A' : '#94A3B8' }}>
                    {documents.signatureName || 'No file chosen'}
                  </span>
                </div>
              </div>
            </div>

            {/* Instructions to upload Aadhaar and PAN */}
            <div className="profile-instruction-box">
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontWeight: 600, fontSize: '0.9rem', marginBottom: '0.5rem' }}>
                <Info size={18} color="#D97706" />
                <span>Instructions to upload Aadhaar and PAN</span>
              </div>
              <ul style={{ margin: 0, paddingLeft: '1.5rem', fontSize: '0.85rem', lineHeight: '1.6' }}>
                <li>Scan Aadhaar/PAN using a good quality scanner with min. 100dpi so that the file size should not be more than 300kb.</li>
                <li>Save the file in .pdf format on local machine.</li>
                <li>Ensure that the scanned Aadhaar/PAN is of good quality.</li>
              </ul>
            </div>

            {/* Upload Aadhaar Card */}
            <div className="profile-section-card">
              <h2 className="profile-section-title">Upload Aadhaar</h2>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '1.25rem' }}>
                <div>
                  <label className="profile-field-label">
                    Aadhaar Number <span className="req-star">*</span>
                  </label>
                  <input
                    type="text"
                    inputMode="numeric"
                    placeholder={documents.aadhaarMasked || '12-digit Aadhaar'}
                    className="profile-field-input"
                    value={documents.aadhaarNumber}
                    onChange={(e) => setDocuments({ ...documents, aadhaarNumber: e.target.value.replace(/\D/g, '').slice(0, 12) })}
                  />
                  {documents.aadhaarMasked && (
                    <p style={{ fontSize: '0.75rem', color: '#64748B', margin: '0.25rem 0 0' }}>Stored: {documents.aadhaarMasked} (encrypted, unverified until admin checks)</p>
                  )}
                </div>

                <div>
                  <label className="profile-field-label">
                    Upload scanned copy of Aadhaar Card <span style={{ fontSize: '0.75rem', color: '#64748B' }}>(Accepted Format: PDF)</span> <span className="req-star">*</span>
                  </label>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', flexWrap: 'wrap', marginTop: '0.25rem' }}>
                    <label className="profile-file-btn">
                      Choose File
                      <input
                        type="file"
                        accept=".pdf"
                        style={{ display: 'none' }}
                        onChange={(e) => {
                          const f = e.target.files[0];
                          if (f) {
                            if (f.size > 300 * 1024) {
                              showError(`Aadhaar file too large (${Math.round(f.size / 1024)} KB). Max 300 KB.`);
                              e.target.value = '';
                              return;
                            }
                            setDocuments({ ...documents, aadhaarFileName: f.name, aadhaarFile: f });
                          }
                        }}
                      />
                    </label>
                    <span style={{ fontSize: '0.875rem', color: documents.aadhaarFileName ? '#0F172A' : '#94A3B8' }}>
                      {documents.aadhaarFileName || 'No file chosen'}
                    </span>
                  </div>
                </div>
              </div>
            </div>

            {/* Upload PAN Card */}
            <div className="profile-section-card">
              <h2 className="profile-section-title">Upload PAN</h2>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '1.25rem' }}>
                <div>
                  <label className="profile-field-label">
                    PAN <span className="req-star">*</span>
                  </label>
                  <input
                    type="text"
                    placeholder={documents.panMasked || 'ABCDE1234F'}
                    className="profile-field-input"
                    value={documents.panNumber}
                    onChange={(e) => setDocuments({ ...documents, panNumber: e.target.value.toUpperCase().replace(/[^A-Z0-9]/g, '').slice(0, 10) })}
                  />
                  {documents.panMasked && (
                    <p style={{ fontSize: '0.75rem', color: '#64748B', margin: '0.25rem 0 0' }}>Stored: {documents.panMasked} (encrypted, unverified until admin checks)</p>
                  )}
                </div>

                <div>
                  <label className="profile-field-label">
                    Upload scanned copy of PAN Card <span style={{ fontSize: '0.75rem', color: '#64748B' }}>(Accepted Format: PDF)</span> <span className="req-star">*</span>
                  </label>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', flexWrap: 'wrap', marginTop: '0.25rem' }}>
                    <label className="profile-file-btn">
                      Choose File
                      <input
                        type="file"
                        accept=".pdf"
                        style={{ display: 'none' }}
                        onChange={(e) => {
                          const f = e.target.files[0];
                          if (f) {
                            if (f.size > 300 * 1024) {
                              showError(`PAN file too large (${Math.round(f.size / 1024)} KB). Max 300 KB.`);
                              e.target.value = '';
                              return;
                            }
                            setDocuments({ ...documents, panFileName: f.name, panFile: f });
                          }
                        }}
                      />
                    </label>
                    <span style={{ fontSize: '0.875rem', color: documents.panFileName ? '#0F172A' : '#94A3B8' }}>
                      {documents.panFileName || 'No file chosen'}
                    </span>
                  </div>
                </div>
              </div>
            </div>

            </fieldset>

            <div style={{ display: 'flex', justifyContent: 'center', marginTop: '0.5rem' }}>
              <p style={{ fontSize: '0.8125rem', color: '#64748B', margin: 0 }}>
                Edit anything on any tab, then press <strong>Save All Changes</strong> at the top once — everything saves together.
              </p>
            </div>
          </div>
        )}

        {/* Security/password-change tab removed — moved to /profile/security
            (sidebar link). Same ChangePasswordPage + endpoint for all roles. */}
      </div>

      {/* Embedded scoped styling for profile controls */}
      <style>{`
        .profile-section-card {
          background-color: #ffffff;
          border-radius: 12px;
          border: 1px solid #E2E8F0;
          box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);
          padding: 1.5rem;
        }

        .profile-section-title {
          font-size: 1.05rem;
          font-weight: 600;
          color: #0F172A;
          margin: 0 0 1.25rem 0;
          padding-bottom: 0.75rem;
          border-bottom: 1px solid #F1F5F9;
        }

        .profile-field-label {
          display: block;
          font-size: 0.8125rem;
          font-weight: 600;
          color: #1E293B;
          margin-bottom: 0.375rem;
        }

        .req-star {
          color: #EF4444;
          margin-left: 2px;
        }

        .profile-field-input {
          width: 100%;
          padding: 0.625rem 0.875rem;
          border: 1px solid #CBD5E1;
          border-radius: 8px;
          font-size: 0.875rem;
          color: #0F172A;
          background-color: #ffffff;
          outline: none;
          transition: border-color 0.15s ease, box-shadow 0.15s ease;
          box-sizing: border-box;
        }

        .profile-field-input:focus {
          border-color: #1E60DC;
          box-shadow: 0 0 0 3px rgba(58, 129, 246, 0.12);
        }

        .profile-field-input:disabled {
          background-color: #F8FAFC;
          color: #64748B;
          cursor: not-allowed;
        }

        .profile-field-select {
          width: 100%;
          padding: 0.625rem 2.25rem 0.625rem 0.875rem;
          border: 1px solid #CBD5E1;
          border-radius: 8px;
          font-size: 0.875rem;
          color: #0F172A;
          background-color: #ffffff;
          outline: none;
          appearance: none;
          cursor: pointer;
          transition: border-color 0.15s ease;
          box-sizing: border-box;
        }

        .profile-field-select:focus {
          border-color: #1E60DC;
          box-shadow: 0 0 0 3px rgba(58, 129, 246, 0.12);
        }

        .profile-field-select:disabled {
          background-color: #F8FAFC;
          color: #64748B;
          cursor: not-allowed;
        }

        .profile-select-icon {
          position: absolute;
          right: 0.875rem;
          top: 50%;
          transform: translateY(-50%);
          pointer-events: none;
          color: #64748B;
        }

        .profile-field-textarea {
          width: 100%;
          padding: 0.625rem 0.875rem;
          border: 1px solid #CBD5E1;
          border-radius: 8px;
          font-size: 0.875rem;
          color: #0F172A;
          background-color: #ffffff;
          outline: none;
          resize: vertical;
          box-sizing: border-box;
          transition: border-color 0.15s ease;
        }

        .profile-field-textarea:focus {
          border-color: #1E60DC;
          box-shadow: 0 0 0 3px rgba(58, 129, 246, 0.12);
        }

        .profile-field-textarea:disabled {
          background-color: #F8FAFC;
          color: #64748B;
          cursor: not-allowed;
        }

        .profile-action-btn {
          background-color: #1E60DC;
          color: #ffffff;
          border: none;
          border-radius: 9999px;
          padding: 0.6875rem 2.5rem;
          font-size: 0.9375rem;
          font-weight: 600;
          cursor: pointer;
          transition: background-color 0.15s ease, transform 0.1s ease;
          box-shadow: 0 2px 4px rgba(58, 129, 246, 0.25);
        }

        .profile-action-btn:hover {
          background-color: #2563EB;
          transform: translateY(-1px);
        }

        .profile-action-btn:disabled {
          opacity: 0.55;
          cursor: not-allowed;
          transform: none;
        }

        fieldset:disabled .profile-field-input,
        fieldset:disabled .profile-field-select,
        fieldset:disabled .profile-field-textarea {
          background-color: #F8FAFC;
          color: #64748B;
          cursor: not-allowed;
        }

        fieldset {
          min-width: 0;
        }

        .profile-instruction-box {
          background-color: #FEF3C7;
          border: 1px solid #FDE68A;
          border-radius: 10px;
          padding: 1.125rem 1.25rem;
          color: #92400E;
        }

        .profile-file-btn {
          display: inline-block;
          padding: 0.5rem 1.25rem;
          background-color: #F1F5F9;
          border: 1px solid #CBD5E1;
          border-radius: 6px;
          font-size: 0.8125rem;
          font-weight: 600;
          color: #334155;
          cursor: pointer;
          transition: background-color 0.15s ease;
        }

        .profile-file-btn:hover {
          background-color: #E2E8F0;
        }
      `}</style>
    </>
  );
}
