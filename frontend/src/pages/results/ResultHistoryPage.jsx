import { useState, useEffect } from 'react';
import studentApi from '../../api/studentApi';
import resultsApi from '../../api/resultsApi';
import curriculumApi from '../../api/curriculumApi';
import PageHeader from '../../components/common/PageHeader';
import Badge from '../../components/common/Badge';
import Modal from '../../components/common/Modal';
import { LoadingState, ErrorState, EmptyState } from '../../components/common/StateDisplays';
import {
  Eye,
  Edit3,
  CheckCircle2,
  XCircle,
  Clock,
  GraduationCap,
  Save,
  AlertCircle,
  BookOpen,
  Lock,
  Unlock,
} from 'lucide-react';

/**
 * ELIGIBILITY_THRESHOLD — minimum percentage of credits earned
 * vs registered to be considered "Pass" for that semester.
 * Standard college / sysadmin eligibility criteria (80%).
 */
const ELIGIBILITY_THRESHOLD = 80;

/**
 * DBATU NEP 2020 — Passing Rules:
 * - Theory minimum: 20 out of 60 marks
 * - Mid Sem 1: max 20 marks
 * - Mid Sem 2: max 20 marks
 * - Aggregate minimum: 40 out of 100 marks
 * If theory < 20 OR total < 40 => Subject FAIL (0 credits earned, Grade F).
 */
const PASSING_RULES = {
  MIN_THEORY: 20,
  MAX_THEORY: 60,
  MAX_MID1: 20,
  MAX_MID2: 20,
  MIN_TOTAL: 40,
  MAX_TOTAL: 100,
};

/**
 * DBATU NEP 2020 — B.Tech AI & Allied Curriculum
 * Pre-populated subject scheme per semester (theory only, excluding practicals).
 */
const CURRICULUM = {
  1: [
    { code: 'CS101', name: 'Engineering Mathematics I', credits: 4 },
    { code: 'CS102', name: 'Engineering Physics', credits: 4 },
    { code: 'CS103', name: 'Structured Programming with C', credits: 4 },
    { code: 'CS104', name: 'Basic Electrical & Electronics', credits: 3 },
    { code: 'CS105', name: 'Indian Constitution & Ethics', credits: 2 },
  ],
  2: [
    { code: '25AF1000BS201', name: 'Engineering Mathematics II', credits: 3 },
    { code: '25AF1000BS202', name: 'Engineering Chemistry', credits: 3 },
    { code: '25AF1245PC203', name: 'Object Oriented Programming with Java', credits: 3 },
    { code: '25AF1245PC204', name: 'Data Communication', credits: 2 },
    { code: '25AF1000HS205', name: 'Universal Human Values', credits: 2 },
    { code: '25AF1000BS206', name: 'Environmental Science & Sustainability', credits: 2 },
  ],
  3: [
    { code: '25AF1000BS301', name: 'Engineering Mathematics-III', credits: 3 },
    { code: '25AF1245PC302', name: 'Data Structures', credits: 3 },
    { code: '25AF1245PC303', name: 'Discrete Mathematics', credits: 3 },
    { code: '25AFAIPC304', name: 'Artificial Intelligence', credits: 2 },
    { code: '25AFAIPC305', name: 'Prompt Engineering', credits: 2 },
  ],
  4: [
    { code: '25AF1000BS401', name: 'Probability & Statistics', credits: 3 },
    { code: '25AF1245PC402', name: 'Design & Analysis of Algorithms', credits: 3 },
    { code: '25AF1245PC403', name: 'Database Management Systems', credits: 3 },
    { code: '25AFAIPC404', name: 'Machine Learning', credits: 3 },
    { code: '25AFAIPC405', name: 'Computer Networks', credits: 2 },
  ],
  5: [
    { code: '25AFAIPC501', name: 'Deep Learning', credits: 3 },
    { code: '25AFAIPC502', name: 'Natural Language Processing', credits: 3 },
    { code: '25AFAIPC503', name: 'Cloud Computing', credits: 3 },
    { code: '25AFAIPC504', name: 'Software Engineering', credits: 3 },
  ],
  6: [
    { code: '25AFAIPC601', name: 'Computer Vision', credits: 3 },
    { code: '25AFAIPC602', name: 'Big Data Analytics', credits: 3 },
    { code: '25AFAIPC603', name: 'Information Security', credits: 3 },
    { code: '25AFAIPC604', name: 'AI Ethics & Governance', credits: 2 },
  ],
  7: [
    { code: '25AFAIPC701', name: 'Reinforcement Learning', credits: 3 },
    { code: '25AFAIPC702', name: 'IoT & Edge Computing', credits: 3 },
    { code: '25AFAIOE703', name: 'Open Elective I', credits: 3 },
  ],
  8: [
    { code: '25AFAIPC801', name: 'Project Work', credits: 6 },
    { code: '25AFAIOE802', name: 'Open Elective II', credits: 3 },
  ],
};

export default function ResultHistoryPage() {
  const [results, setResults] = useState([]);
  const [profile, setProfile] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  /* Backend published results are the only record source. */

  /* Fill-result modal state */
  const [fillSemester, setFillSemester] = useState(null);
  const [formSubjects, setFormSubjects] = useState([]);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState('');
  const [formSuccess, setFormSuccess] = useState('');

  /* View modal state */
  const [viewResult, setViewResult] = useState(null);

  const [eligibilityRecords, setEligibilityRecords] = useState([]);

  /* ──────────────── Data Fetching ──────────────── */

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    try {
      setLoading(true);
      setError(null);
      const [resultsRes, profileRes, eligRes] = await Promise.allSettled([
        resultsApi.getMyResults(),
        studentApi.getMyProfile(),
        resultsApi.getEligibilities(),
      ]);
      if (resultsRes.status === 'fulfilled') {
        setResults(resultsRes.value.data || []);
      }
      if (profileRes.status === 'fulfilled') {
        setProfile(profileRes.value.data);
      }
      if (eligRes.status === 'fulfilled') {
        setEligibilityRecords(eligRes.value.data?.results || eligRes.value.data || []);
      }
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to load results data.');
    } finally {
      setLoading(false);
    }
  };

  /* ──────────────── Semester Row Builder ──────────────── */

  const buildSemesterRows = () => {
    if (!profile) return [];

    const isDSY = Boolean(profile.is_direct_second_year);
    const currentSemNumber = profile.current_enrollment?.semester_number || (isDSY ? 3 : 1);
    const rows = [];

    for (let sem = 1; sem <= currentSemNumber; sem++) {
      // Direct Second Year students start from Semester 3; Sem 1 and 2 are exempted
      if (isDSY && sem <= 2) {
        rows.push({
          semester: sem,
          isCurrent: false,
          isLocked: true,
          isExemptedDSY: true,
          isFlaggedByTeacher: false,
          teacherRemarks: '',
          isFinalEligible: false,
          examSession: '—',
          totalCredits: '—',
          creditsEarned: '—',
          sgpa: '—',
          eligibility: 'exempted',
          result: null,
        });
        continue;
      }

      // Priority: backend published results only.
      const backendResult = results.find((r) => r.semester_number === sem);
      const result = backendResult || null;
      const isCurrent = sem === currentSemNumber;

      // Check eligibility workflow state for target semester
      const targetSemEligibility = eligibilityRecords.find(e => e.target_semester_number === sem + 1);
      const isVerificationStarted = Boolean(targetSemEligibility);
      const isFlaggedByTeacher = targetSemEligibility?.class_teacher_status === 'FLAGGED';
      const isConfirmedByTeacher = targetSemEligibility?.class_teacher_status === 'APPROVED';
      const isFinalEligible = targetSemEligibility?.final_eligible === true;
      const teacherRemarks = targetSemEligibility?.class_teacher_remarks || '';

      const isLocked = Boolean((isConfirmedByTeacher && !isFlaggedByTeacher) || (backendResult && !isFlaggedByTeacher));

      // Current even semesters (2, 4, 6) require HOD/Teacher to initiate verification before current marks can be uploaded
      const isEvenSem = sem % 2 === 0;
      const isUploadAllowed = !isCurrent || !isEvenSem || isVerificationStarted;

      let eligibility = 'pending';
      if (isFinalEligible) {
        eligibility = 'final_eligible';
      } else if (isConfirmedByTeacher) {
        eligibility = 'teacher_approved';
      } else if (isFlaggedByTeacher) {
        eligibility = 'teacher_flagged';
      } else if (result && result.result_status !== 'NOT_YET_HELD') {
        const earned = Number(result.total_credits_earned) || 0;
        const registered = Number(result.total_credits_registered) || 1;
        const pct = (earned / registered) * 100;
        eligibility = pct >= ELIGIBILITY_THRESHOLD ? 'pass' : 'fail';
      }

      rows.push({
        semester: sem,
        isCurrent,
        isLocked,
        isUploadAllowed,
        isVerificationStarted,
        isFlaggedByTeacher,
        teacherRemarks,
        isFinalEligible,
        examSession: result?.exam_session || (isCurrent ? 'In Progress' : '—'),
        totalCredits: result?.total_credits_registered ?? '—',
        creditsEarned: result?.total_credits_earned ?? '—',
        sgpa: result?.sgpa ?? '—',
        eligibility,
        result,
      });
    }

    return rows;
  };

  /* ──────────────── Marks Input Handler with Strict Clamping ──────────────── */

  const handleMarksInputChange = (index, field, rawValue, maxVal) => {
    if (rawValue === '') {
      setFormSubjects((prev) =>
        prev.map((s, i) => (i === index ? { ...s, [field]: '' } : s))
      );
      return;
    }

    // Clamp numeric input between 0 and maxVal (allowing decimal marks if entered)
    let val = parseFloat(rawValue);
    if (isNaN(val)) return;
    if (val < 0) val = 0;
    if (val > maxVal) val = maxVal;

    setFormSubjects((prev) =>
      prev.map((s, i) => (i === index ? { ...s, [field]: val } : s))
    );
  };

  /* ──────────────── Subject Marks Pre-Population Helper ──────────────── */

  const getExistingSubjectMarks = (semNumber, schemeList) => {
    // 1. Check if backend results has this semester
    const backendRes = results.find((r) => r.semester_number === semNumber);

    const curriculumSubjects = (schemeList && schemeList.length > 0)
      ? schemeList.map((s) => ({
          code: s.course_code,
          name: s.subject_title || s.subject_code,
          credits: s.credits,
        }))
      : (CURRICULUM[semNumber] || []);

    return curriculumSubjects.map((cur) => {
      const fromBackend = backendRes?.subjects?.find((s) => (s.course_code || s.code) === cur.code);

      let m1 = '';
      let m2 = '';
      let th = '';

      if (fromBackend) {
        if (fromBackend.mid1_marks !== undefined && fromBackend.mid1_marks !== null && fromBackend.mid1_marks !== '') {
          m1 = fromBackend.mid1_marks;
        }
        if (fromBackend.mid2_marks !== undefined && fromBackend.mid2_marks !== null && fromBackend.mid2_marks !== '') {
          m2 = fromBackend.mid2_marks;
        }
        if (fromBackend.theory_marks !== undefined && fromBackend.theory_marks !== null && fromBackend.theory_marks !== '') {
          th = fromBackend.theory_marks;
        } else if (fromBackend.theory_ese_marks !== undefined && fromBackend.theory_ese_marks !== null && fromBackend.theory_ese_marks !== '') {
          th = fromBackend.theory_ese_marks;
        }
      }

      // Fallback: if m1/m2 still empty but theory_ise_marks exists on backend
      if ((m1 === '' || m2 === '') && fromBackend?.theory_ise_marks !== undefined && fromBackend.theory_ise_marks !== null && fromBackend.theory_ise_marks !== '') {
        const ise = Number(fromBackend.theory_ise_marks);
        if (!isNaN(ise)) {
          m1 = Math.min(20, Math.round(ise / 2));
          m2 = Math.max(0, Math.round(ise - m1));
        }
      }

      const formatVal = (v) => {
        if (v === '' || v === undefined || v === null) return '';
        const n = Number(v);
        return isNaN(n) ? '' : n;
      };

      return {
        code: cur.code,
        name: cur.name,
        credits: cur.credits,
        mid1_marks: formatVal(m1),
        mid2_marks: formatVal(m2),
        theory_marks: formatVal(th),
      };
    });
  };

  /* ──────────────── Fill Result Handlers ──────────────── */

  const openFillForm = async (semNumber, forceEdit = false) => {
    // If published on the backend and not flagged, open in view mode directly.
    // Exact target-semester match only — no fallback: a stale first-record
    // fallback previously misread other semesters' FLAGGED status.
    const targetSemEligibility = eligibilityRecords.find(e => e.target_semester_number === semNumber + 1);
    const isFlagged = targetSemEligibility?.class_teacher_status === 'FLAGGED';
    const publishedRes = results.find((r) => r.semester_number === semNumber);

    if (!forceEdit && !isFlagged && publishedRes) {
      setViewResult(publishedRes);
      return;
    }

    setFillSemester(semNumber);
    setFormError('');
    setFormSuccess('');

    // Prefer the student's own scheme subject list; fall back to the
    // built-in table for students without a scheme (old records).
    let schemeList = [];
    try {
      const res = await curriculumApi.getMySubjects(semNumber);
      schemeList = res.data?.results || res.data || [];
    } catch {
      schemeList = [];
    }
    // Pre-populate with all previously saved / submitted marks
    const initialSubjects = getExistingSubjectMarks(semNumber, schemeList);
    setFormSubjects(initialSubjects);
  };

  const handleFillSubmit = async () => {
    // Validate each subject has numbers entered
    const incomplete = formSubjects.some(
      (s) => s.mid1_marks === '' || s.mid2_marks === '' || s.theory_marks === ''
    );
    if (incomplete) {
      setFormError('Please enter Mid Sem 1, Mid Sem 2, and Theory marks for all subjects.');
      return;
    }

    try {
      setSaving(true);
      setFormError('');

      // Submit marks to authoritative backend results API (no browser cache).
      const res = await resultsApi.submitMarks({
        semester_number: fillSemester,
        exam_session: 'Winter 2026',
        subjects: formSubjects.map(s => ({
          course_code: s.code,
          course_name: s.name,
          credits: s.credits,
          theory_marks: Number(s.theory_marks) || 0,
          mid1_marks: Number(s.mid1_marks) || 0,
          mid2_marks: Number(s.mid2_marks) || 0,
          total_marks: (Number(s.mid1_marks) || 0) + (Number(s.mid2_marks) || 0) + (Number(s.theory_marks) || 0),
        }))
      });

      setFormSuccess(res.data?.message || 'Result saved and submitted to Class Teacher for verification!');
      await loadData();
      setTimeout(() => {
        closeFillForm();
      }, 900);
    } catch (err) {
      setFormError(err.response?.data?.detail || 'Failed to submit marks. Please try again.');
    } finally {
      setSaving(false);
    }
  };

  const closeFillForm = () => {
    setFillSemester(null);
    setFormSubjects([]);
    setFormError('');
    setFormSuccess('');
  };

  /* Unlock handler for editing/testing marks */
  const handleUnlockAndEdit = (semNumber) => {
    setViewResult(null);
    openFillForm(semNumber, true);
  };

  /* ──────────────── Eligibility Badge ──────────────── */

  const renderEligibilityBadge = (eligibility) => {
    switch (eligibility) {
      case 'exempted':
        return (
          <span style={{ color: '#94a3b8', fontWeight: 600, fontSize: '0.875rem' }}>—</span>
        );
      case 'final_eligible':
        return (
          <Badge variant="success">
            <CheckCircle2 size={12} />
            <span>Eligible (HOD Approved)</span>
          </Badge>
        );
      case 'teacher_approved':
        return (
          <Badge variant="info">
            <Lock size={12} />
            <span>Teacher Confirmed</span>
          </Badge>
        );
      case 'teacher_flagged':
        return (
          <Badge variant="danger">
            <AlertCircle size={12} />
            <span>Flagged by Teacher</span>
          </Badge>
        );
      case 'pass':
        return (
          <Badge variant="success">
            <CheckCircle2 size={12} />
            <span>Pass</span>
          </Badge>
        );
      case 'fail':
        return (
          <Badge variant="danger">
            <XCircle size={12} />
            <span>Fail</span>
          </Badge>
        );
      default:
        return (
          <Badge variant="neutral">
            <Clock size={12} />
            <span>Pending</span>
          </Badge>
        );
    }
  };

  /* ──────────────── Loading / Error ──────────────── */

  if (loading) {
    return (
      <div className="edvana-page" style={{ padding: '3rem 1.5rem' }}>
        <LoadingState message="Loading your semester results..." />
      </div>
    );
  }

  if (error) {
    return (
      <div className="edvana-page" style={{ padding: '3rem 1.5rem' }}>
        <ErrorState title="Unable to Load Results" message={error} onRetry={loadData} />
      </div>
    );
  }

  const semesterRows = buildSemesterRows();
  const formTotalCredits = formSubjects.reduce((sum, s) => sum + (Number(s.credits) || 0), 0);

  /* ──────────────── Main Render ──────────────── */

  return (
    <>
      <PageHeader
        breadcrumbs={[
          { label: 'Home', to: '/dashboard' },
          { label: 'Student Portal' },
          { label: 'Results' },
        ]}
        title="Results"
        subtitle="View your semester-wise academic results and verify eligibility."
      />

      <div className="edvana-banner-overlap">

        {/* ───── Info Banner ───── */}
        <div
          style={{
            display: 'flex',
            alignItems: 'flex-start',
            gap: '0.75rem',
            padding: '1rem 1.25rem',
            background: '#eff6ff',
            border: '1px solid #bfdbfe',
            borderRadius: '10px',
            marginBottom: profile?.is_direct_second_year ? '0.75rem' : '1.5rem',
            fontSize: '0.8125rem',
            color: '#1e40af',
            lineHeight: 1.55,
          }}
        >
          <AlertCircle size={18} style={{ flexShrink: 0, marginTop: '1px' }} />
          <span>
            <strong>Passing Criteria:</strong> Minimum <strong>20/60</strong> marks in Theory exam and <strong>40/100</strong> total marks per subject.
            Students must earn at least <strong>{ELIGIBILITY_THRESHOLD}%</strong> of registered semester credits to qualify as <strong>Pass</strong>.
          </span>
        </div>

        {/* ───── DSY Lateral Entry Banner (if applicable) ───── */}
        {profile?.is_direct_second_year && (
          <div
            style={{
              display: 'flex',
              alignItems: 'flex-start',
              gap: '0.75rem',
              padding: '0.9rem 1.25rem',
              background: '#f5f3ff',
              border: '1px solid #ddd6fe',
              borderRadius: '10px',
              marginBottom: '1.5rem',
              fontSize: '0.8125rem',
              color: '#6d28d9',
              lineHeight: 1.55,
            }}
          >
            <GraduationCap size={18} style={{ color: '#7c3aed', flexShrink: 0, marginTop: '1px' }} />
            <span>
              <strong>Direct Second Year (Lateral Entry):</strong> Semesters 1 and 2 are exempted based on qualifying Polytechnic Diploma credentials. Semester results start from <strong>Semester III (Second Year)</strong>.
            </span>
          </div>
        )}

        {/* ───── Semester Results Table Card ───── */}
        <div className="edvana-card" style={{ borderRadius: '12px', border: '1px solid #e2e8f0', overflow: 'hidden' }}>

          {/* Card Header */}
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              padding: '1.25rem 1.5rem',
              borderBottom: '1px solid #f1f5f9',
            }}
          >
            <div>
              <h2
                style={{
                  fontSize: '1.05rem',
                  fontWeight: 700,
                  color: '#0f172a',
                  margin: 0,
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.5rem',
                }}
              >
                <GraduationCap size={20} style={{ color: '#1E60DC' }} />
                Semester Results Overview
              </h2>
              <p style={{ fontSize: '0.8125rem', color: '#64748b', margin: '0.25rem 0 0 0', display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap' }}>
                <span>{profile?.display_name || 'Student'} — {profile?.current_enrollment?.department_name || 'Department'} — Semester {profile?.current_enrollment?.semester_number || '—'}</span>
                {profile?.is_direct_second_year && (
                  <span
                    style={{
                      background: '#ede9fe',
                      color: '#6d28d9',
                      fontSize: '0.7rem',
                      fontWeight: 700,
                      padding: '0.15rem 0.5rem',
                      borderRadius: '4px',
                      textTransform: 'uppercase',
                      letterSpacing: '0.04em',
                    }}
                  >
                    DSY Lateral Entry
                  </span>
                )}
              </p>
            </div>
          </div>

          {/* Flagged Remarks Alert Banner */}
          {semesterRows.some(r => r.isFlaggedByTeacher) && (
            <div
              style={{
                margin: '1rem 1.5rem 0.5rem 1.5rem',
                padding: '1rem 1.25rem',
                backgroundColor: '#fef2f2',
                border: '1.5px solid #fecaca',
                borderRadius: '8px',
                display: 'flex',
                alignItems: 'flex-start',
                gap: '0.85rem',
              }}
            >
              <AlertCircle size={22} style={{ color: '#dc2626', flexShrink: 0, marginTop: '2px' }} />
              <div style={{ flex: 1 }}>
                <div style={{ fontWeight: 700, color: '#991b1b', fontSize: '0.9rem' }}>
                  Action Required: Result Flagged by Class Teacher
                </div>
                <div style={{ fontSize: '0.84rem', color: '#b91c1c', marginTop: '0.25rem', lineHeight: 1.5 }}>
                  <strong>Teacher Remark:</strong> "{semesterRows.find(r => r.isFlaggedByTeacher)?.teacherRemarks || 'Discrepancy noted in your entered marks. Please correct and re-submit.'}"
                </div>
                <div style={{ marginTop: '0.65rem' }}>
                  <button
                    type="button"
                    onClick={() => {
                      const flaggedRow = semesterRows.find(r => r.isFlaggedByTeacher);
                      if (flaggedRow) {
                        openFillForm(flaggedRow.semester, true);
                      }
                    }}
                    style={{
                      display: 'inline-flex',
                      alignItems: 'center',
                      gap: '0.35rem',
                      padding: '0.4rem 0.9rem',
                      fontSize: '0.8125rem',
                      fontWeight: 600,
                      borderRadius: '6px',
                      background: '#dc2626',
                      color: '#ffffff',
                      border: 'none',
                      cursor: 'pointer',
                    }}
                  >
                    <Edit3 size={14} />
                    <span>Correct & Re-submit Marks Now</span>
                  </button>
                </div>
              </div>
            </div>
          )}

          {/* Table */}
          {semesterRows.length === 0 ? (
            <div style={{ padding: '3rem' }}>
              <EmptyState
                icon={BookOpen}
                title="No Semester Data"
                message="Your enrollment records are being processed. Please check back later."
              />
            </div>
          ) : (
            <div style={{ overflowX: 'auto' }}>
              <table className="edvana-table" style={{ margin: 0 }}>
                <thead>
                  <tr>
                    <th style={{ width: 120 }}>Semester</th>
                    <th>Exam Session</th>
                    <th style={{ textAlign: 'center' }}>Total Credits</th>
                    <th style={{ textAlign: 'center' }}>Credits Earned</th>
                    <th style={{ textAlign: 'center' }}>SGPA</th>
                    <th style={{ textAlign: 'center' }}>Eligibility</th>
                    <th style={{ textAlign: 'center', width: 140 }}>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {semesterRows.map((row) => (
                    <tr key={row.semester}>
                      {/* Semester */}
                      <td>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                          <span
                            style={{
                              width: 30,
                              height: 30,
                              borderRadius: '8px',
                              background: row.isCurrent ? '#1E60DC' : '#f1f5f9',
                              color: row.isCurrent ? '#ffffff' : '#475569',
                              display: 'flex',
                              alignItems: 'center',
                              justifyContent: 'center',
                              fontSize: '0.8125rem',
                              fontWeight: 700,
                              flexShrink: 0,
                            }}
                          >
                            {row.semester}
                          </span>
                          <span style={{ fontWeight: 600, color: '#0f172a', fontSize: '0.8125rem' }}>
                            Sem {toRoman(row.semester)}
                          </span>
                        </div>
                      </td>

                      {/* Exam Session */}
                      <td style={{ color: '#475569', fontSize: '0.8125rem' }}>
                        {row.isCurrent && !row.result ? (
                          <Badge variant="info">
                            <Clock size={11} />
                            <span>In Progress</span>
                          </Badge>
                        ) : (
                          row.examSession
                        )}
                      </td>

                      {/* Total Credits */}
                      <td style={{ textAlign: 'center', fontWeight: 600, fontFamily: 'var(--edvana-font-mono)', color: '#0f172a' }}>
                        {row.totalCredits}
                      </td>

                      {/* Credits Earned */}
                      <td style={{ textAlign: 'center', fontWeight: 600, fontFamily: 'var(--edvana-font-mono)', color: '#0f172a' }}>
                        {row.creditsEarned}
                      </td>

                      {/* SGPA */}
                      <td style={{ textAlign: 'center', fontWeight: 700, color: '#1E60DC', fontFamily: 'var(--edvana-font-mono)' }}>
                        {row.sgpa}
                      </td>

                      {/* Eligibility */}
                      <td style={{ textAlign: 'center' }}>
                        {renderEligibilityBadge(row.eligibility)}
                      </td>

                      {/* Action */}
                      <td style={{ textAlign: 'center' }}>
                        {row.isExemptedDSY ? (
                          <span style={{ color: '#94a3b8', fontWeight: 600, fontSize: '0.875rem' }}>—</span>
                        ) : (
                          <div style={{ display: 'inline-flex', gap: '0.4rem', justifyContent: 'center' }}>
                            {row.isFlaggedByTeacher && (
                              <button
                                onClick={() => {
                                  openFillForm(row.semester, true);
                                }}
                                style={{
                                  display: 'inline-flex',
                                  alignItems: 'center',
                                  gap: '0.35rem',
                                  padding: '0.375rem 0.875rem',
                                  fontSize: '0.8rem',
                                  fontWeight: 600,
                                  borderRadius: '7px',
                                  background: '#fef2f2',
                                  color: '#b91c1c',
                                  border: '1px solid #fecaca',
                                  cursor: 'pointer',
                                  transition: 'all 0.15s ease',
                                }}
                                title="Class teacher flagged your marks. Click to correct."
                              >
                                <Edit3 size={14} />
                                Correct Marks
                              </button>
                            )}

                            {row.result ? (
                              <button
                                onClick={() => setViewResult(row.result)}
                                style={{
                                  display: 'inline-flex',
                                  alignItems: 'center',
                                  gap: '0.35rem',
                                  padding: '0.375rem 0.875rem',
                                  fontSize: '0.8rem',
                                  fontWeight: 600,
                                  borderRadius: '7px',
                                  background: '#eff6ff',
                                  color: '#2563eb',
                                  border: '1px solid #bfdbfe',
                                  cursor: 'pointer',
                                  transition: 'all 0.15s ease',
                                }}
                              >
                                {row.isLocked && <Lock size={12} style={{ color: '#64748b' }} />}
                                <Eye size={14} />
                                View
                              </button>
                            ) : !row.isUploadAllowed ? (
                              <span
                                style={{
                                  fontSize: '0.75rem',
                                  color: '#64748b',
                                  padding: '0.35rem 0.65rem',
                                  background: '#f8fafc',
                                  borderRadius: '6px',
                                  border: '1px dashed #cbd5e1',
                                  display: 'inline-flex',
                                  alignItems: 'center',
                                  gap: '0.3rem',
                                }}
                                title="Verification window opens once HOD or Class Teacher initiates annual result verification."
                              >
                                <Lock size={12} />
                                Verification Not Started
                              </span>
                            ) : (
                              <button
                                onClick={() => openFillForm(row.semester)}
                                style={{
                                  display: 'inline-flex',
                                  alignItems: 'center',
                                  gap: '0.35rem',
                                  padding: '0.375rem 0.875rem',
                                  fontSize: '0.8rem',
                                  fontWeight: 600,
                                  borderRadius: '7px',
                                  background: '#f0fdf4',
                                  color: '#15803d',
                                  border: '1px solid #bbf7d0',
                                  cursor: 'pointer',
                                  transition: 'all 0.15s ease',
                                }}
                              >
                                <Edit3 size={14} />
                                Fill Result
                              </button>
                            )}
                          </div>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>

      {/* ════════════════════════════════════════════════ */}
      {/*  Fill Result Modal (Scheme-based Marks Entry)    */}
      {/* ════════════════════════════════════════════════ */}
      <Modal
        isOpen={fillSemester !== null}
        onClose={closeFillForm}
        title={`Fill Result — Semester ${toRoman(fillSemester || 0)}`}
        size="xl"
      >
        {fillSemester && (
          <div>

            {/* Success message */}
            {formSuccess && (
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.5rem',
                  padding: '0.85rem 1rem',
                  background: '#f0fdf4',
                  border: '1px solid #bbf7d0',
                  borderRadius: '8px',
                  marginBottom: '1rem',
                  fontSize: '0.8125rem',
                  color: '#15803d',
                  fontWeight: 600,
                }}
              >
                <CheckCircle2 size={18} />
                {formSuccess}
              </div>
            )}

            {!formSuccess && (
              <>
                <div
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    marginBottom: '1rem',
                    flexWrap: 'wrap',
                    gap: '0.5rem',
                  }}
                >
                  <p style={{ fontSize: '0.8125rem', color: '#64748b', margin: 0, lineHeight: 1.5 }}>
                    Enter your examination marks for <strong>Semester {toRoman(fillSemester)}</strong> subjects.
                    Passing criteria: <strong>&ge; 20/60 in Theory</strong> AND <strong>&ge; 40/100 Total</strong>.
                  </p>
                  <span
                    style={{
                      display: 'inline-flex',
                      alignItems: 'center',
                      gap: '0.35rem',
                      fontSize: '0.75rem',
                      color: '#64748b',
                      background: '#f1f5f9',
                      padding: '0.25rem 0.6rem',
                      borderRadius: '6px',
                      fontWeight: 600,
                    }}
                  >
                    <Lock size={12} />
                    Locks upon submission
                  </span>
                </div>

                {/* Subject Scheme Table */}
                <div style={{ overflowX: 'auto', border: '1px solid #e2e8f0', borderRadius: '8px' }}>
                  <table className="edvana-table" style={{ margin: 0, fontSize: '0.8rem' }}>
                    <thead>
                      <tr>
                        <th style={{ width: 140 }}>Course Code</th>
                        <th style={{ minWidth: 200 }}>Course Title</th>
                        <th style={{ textAlign: 'center', width: 95 }}>Mid Sem 1 (20)</th>
                        <th style={{ textAlign: 'center', width: 95 }}>Mid Sem 2 (20)</th>
                        <th style={{ textAlign: 'center', width: 110 }}>Theory (60)</th>
                        <th style={{ textAlign: 'center', width: 95 }}>Total Marks</th>
                        <th style={{ textAlign: 'center', width: 75 }}>Credits</th>
                        <th style={{ textAlign: 'center', width: 95 }}>Pass / Fail</th>
                      </tr>
                    </thead>
                    <tbody>
                      {formSubjects.map((subject, idx) => {
                        const m1 = subject.mid1_marks !== '' ? Number(subject.mid1_marks) : null;
                        const m2 = subject.mid2_marks !== '' ? Number(subject.mid2_marks) : null;
                        const th = subject.theory_marks !== '' ? Number(subject.theory_marks) : null;
                        const hasEntered = m1 !== null || m2 !== null || th !== null;
                        const total = (m1 || 0) + (m2 || 0) + (th || 0);
                        const isComplete = m1 !== null && m2 !== null && th !== null;
                        const isPass = isComplete ? (total >= PASSING_RULES.MIN_TOTAL && th >= PASSING_RULES.MIN_THEORY) : null;

                        return (
                          <tr key={subject.code || idx}>
                            {/* Course Code (read-only from scheme) */}
                            <td>
                              <div
                                style={{
                                  padding: '0.4rem 0.55rem',
                                  fontSize: '0.775rem',
                                  fontFamily: 'var(--edvana-font-mono)',
                                  fontWeight: 700,
                                  color: '#0f172a',
                                  background: '#f8fafc',
                                  border: '1px solid #e2e8f0',
                                  borderRadius: '6px',
                                  display: 'inline-block',
                                  whiteSpace: 'nowrap',
                                }}
                              >
                                {subject.code}
                              </div>
                            </td>

                            {/* Course Title (read-only from scheme) */}
                            <td>
                              <div
                                style={{
                                  padding: '0.4rem 0.65rem',
                                  fontSize: '0.8125rem',
                                  fontWeight: 600,
                                  color: '#1e293b',
                                  background: '#f8fafc',
                                  border: '1px solid #e2e8f0',
                                  borderRadius: '6px',
                                }}
                              >
                                {subject.name}
                              </div>
                            </td>

                            {/* Mid Sem 1 Marks (Clamped 0-20) */}
                            <td style={{ textAlign: 'center' }}>
                              <input
                                type="number"
                                min="0"
                                max={PASSING_RULES.MAX_MID1}
                                step="any"
                                value={subject.mid1_marks ?? ''}
                                onChange={(e) => handleMarksInputChange(idx, 'mid1_marks', e.target.value, PASSING_RULES.MAX_MID1)}
                                placeholder="0–20"
                                style={{
                                  width: '74px',
                                  padding: '0.4rem 0.4rem',
                                  fontSize: '0.8rem',
                                  fontWeight: 600,
                                  textAlign: 'center',
                                  border: '1px solid #e2e8f0',
                                  borderRadius: '6px',
                                  outline: 'none',
                                  background: '#ffffff',
                                  color: '#0f172a',
                                }}
                              />
                            </td>

                            {/* Mid Sem 2 Marks (Clamped 0-20) */}
                            <td style={{ textAlign: 'center' }}>
                              <input
                                type="number"
                                min="0"
                                max={PASSING_RULES.MAX_MID2}
                                step="any"
                                value={subject.mid2_marks ?? ''}
                                onChange={(e) => handleMarksInputChange(idx, 'mid2_marks', e.target.value, PASSING_RULES.MAX_MID2)}
                                placeholder="0–20"
                                style={{
                                  width: '74px',
                                  padding: '0.4rem 0.4rem',
                                  fontSize: '0.8rem',
                                  fontWeight: 600,
                                  textAlign: 'center',
                                  border: '1px solid #e2e8f0',
                                  borderRadius: '6px',
                                  outline: 'none',
                                  background: '#ffffff',
                                  color: '#0f172a',
                                }}
                              />
                            </td>

                            {/* Theory Marks (Clamped 0-60) */}
                            <td style={{ textAlign: 'center' }}>
                              <input
                                type="number"
                                min="0"
                                max={PASSING_RULES.MAX_THEORY}
                                step="any"
                                value={subject.theory_marks ?? ''}
                                onChange={(e) => handleMarksInputChange(idx, 'theory_marks', e.target.value, PASSING_RULES.MAX_THEORY)}
                                placeholder="0–60"
                                style={{
                                  width: '80px',
                                  padding: '0.4rem 0.4rem',
                                  fontSize: '0.8rem',
                                  fontWeight: 600,
                                  textAlign: 'center',
                                  border: '1px solid #e2e8f0',
                                  borderRadius: '6px',
                                  outline: 'none',
                                  background: '#ffffff',
                                  color: '#0f172a',
                                }}
                              />
                            </td>

                            {/* Total Marks (Auto Calculated) */}
                            <td style={{ textAlign: 'center' }}>
                              <span
                                style={{
                                  fontFamily: 'var(--edvana-font-mono)',
                                  fontWeight: 700,
                                  fontSize: '0.85rem',
                                  color: hasEntered ? '#0f172a' : '#94a3b8',
                                }}
                              >
                                {hasEntered ? total : '—'}
                              </span>
                            </td>

                            {/* Credits (From scheme) */}
                            <td style={{ textAlign: 'center' }}>
                              <span
                                style={{
                                  fontFamily: 'var(--edvana-font-mono)',
                                  fontWeight: 700,
                                  fontSize: '0.85rem',
                                  color: '#0f172a',
                                }}
                              >
                                {subject.credits}
                              </span>
                            </td>

                            {/* Pass / Fail (Requires both Theory >= 20 and Total >= 40) */}
                            <td style={{ textAlign: 'center' }}>
                              {isComplete ? (
                                <Badge variant={isPass ? 'success' : 'danger'}>
                                  {isPass ? 'Pass' : 'Fail'}
                                </Badge>
                              ) : (
                                <span style={{ color: '#94a3b8', fontSize: '0.8rem' }}>—</span>
                              )}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>

                {/* Footer Credits Summary */}
                <div
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    marginTop: '0.75rem',
                    padding: '0.25rem 0.5rem',
                  }}
                >
                  <span style={{ fontSize: '0.75rem', color: '#64748b' }}>
                    * In theory courses, minimum 20 marks in Theory and 40 marks in Total are required to pass.
                  </span>
                  <span style={{ fontSize: '0.8125rem', color: '#64748b', fontWeight: 600 }}>
                    Total Scheme Credits: <span style={{ color: '#0f172a', fontFamily: 'var(--edvana-font-mono)' }}>{formTotalCredits}</span>
                  </span>
                </div>

                {/* Error Banner */}
                {formError && (
                  <div
                    style={{
                      marginTop: '0.75rem',
                      padding: '0.6rem 0.85rem',
                      background: '#fef2f2',
                      border: '1px solid #fecaca',
                      borderRadius: '6px',
                      fontSize: '0.8125rem',
                      color: '#991b1b',
                      fontWeight: 500,
                    }}
                  >
                    {formError}
                  </div>
                )}

                {/* Actions */}
                <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem', marginTop: '1.25rem' }}>
                  <button
                    type="button"
                    onClick={closeFillForm}
                    disabled={saving}
                    style={{
                      padding: '0.5rem 1rem',
                      fontSize: '0.8125rem',
                      fontWeight: 600,
                      borderRadius: '8px',
                      background: '#ffffff',
                      color: '#475569',
                      border: '1px solid #e2e8f0',
                      cursor: 'pointer',
                    }}
                  >
                    Cancel
                  </button>
                  <button
                    type="button"
                    onClick={handleFillSubmit}
                    disabled={saving}
                    style={{
                      padding: '0.5rem 1.25rem',
                      fontSize: '0.8125rem',
                      fontWeight: 600,
                      borderRadius: '8px',
                      display: 'inline-flex',
                      alignItems: 'center',
                      gap: '0.4rem',
                      background: '#1E60DC',
                      color: '#ffffff',
                      border: 'none',
                      cursor: 'pointer',
                    }}
                  >
                    {saving ? (
                      <>
                        <span className="spinner spinner-sm" style={{ width: 14, height: 14, borderWidth: 2 }} />
                        <span>Saving & Locking...</span>
                      </>
                    ) : (
                      <>
                        <Save size={14} />
                        <span>Save Result</span>
                      </>
                    )}
                  </button>
                </div>
              </>
            )}
          </div>
        )}
      </Modal>

      {/* ════════════════════════════════════════════════ */}
      {/*  View Result Modal (Marksheet Detail)           */}
      {/* ════════════════════════════════════════════════ */}
      <Modal
        isOpen={viewResult !== null}
        onClose={() => setViewResult(null)}
        title={`Semester ${viewResult?.semester_number || ''} — Grade Card`}
        size="xl"
      >
        {viewResult && (
          <div>
            {/* Institutional header */}
            <div
              style={{
                textAlign: 'center',
                padding: '1.25rem 1rem',
                borderBottom: '2px solid #1E60DC',
                background: '#f8fafc',
                borderRadius: '8px 8px 0 0',
                marginBottom: '1rem',
              }}
            >
              <div style={{ fontSize: '0.7rem', fontWeight: 700, color: '#64748b', textTransform: 'uppercase', letterSpacing: '1.5px' }}>
                Government of Maharashtra
              </div>
              <h3 style={{ fontSize: '1.1rem', fontWeight: 800, margin: '0.2rem 0', color: '#0f172a' }}>
                GOVERNMENT COLLEGE OF ENGINEERING, KOLHAPUR
              </h3>
              <div style={{ fontSize: '0.75rem', color: '#64748b' }}>
                (An Autonomous Institute | Affiliated to DBATU)
              </div>
              <div style={{ fontSize: '0.85rem', fontWeight: 700, marginTop: '0.5rem', color: '#1E60DC' }}>
                STATEMENT OF GRADES — {viewResult.exam_session?.toUpperCase()}
              </div>
            </div>

            {/* Student info row */}
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
                gap: '1rem',
                padding: '0.75rem 0',
                marginBottom: '1rem',
                fontSize: '0.8125rem',
              }}
            >
              <div>
                <span style={{ color: '#64748b', fontSize: '0.7rem', fontWeight: 600, textTransform: 'uppercase', display: 'block' }}>Candidate</span>
                <strong style={{ color: '#0f172a' }}>{viewResult.student_name}</strong>
              </div>
              <div>
                <span style={{ color: '#64748b', fontSize: '0.7rem', fontWeight: 600, textTransform: 'uppercase', display: 'block' }}>Enrollment No</span>
                <strong style={{ fontFamily: 'var(--edvana-font-mono)', color: '#0f172a' }}>{viewResult.enrollment_no}</strong>
              </div>
              <div>
                <span style={{ color: '#64748b', fontSize: '0.7rem', fontWeight: 600, textTransform: 'uppercase', display: 'block' }}>Semester</span>
                <strong style={{ color: '#0f172a' }}>Semester {viewResult.semester_number}</strong>
              </div>
              {viewResult.is_locked && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
                  <span style={{ color: '#64748b', fontSize: '0.7rem', fontWeight: 600, textTransform: 'uppercase', display: 'block' }}>Status</span>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                    <Badge variant="neutral">
                      <Lock size={11} />
                      <span>Locked & Submitted</span>
                    </Badge>
                    <button
                      type="button"
                      onClick={() => handleUnlockAndEdit(viewResult.semester_number)}
                      title="Unlock and re-edit marks"
                      style={{
                        display: 'inline-flex',
                        alignItems: 'center',
                        gap: '0.25rem',
                        padding: '0.2rem 0.5rem',
                        fontSize: '0.725rem',
                        fontWeight: 600,
                        color: '#d97706',
                        background: '#fef3c7',
                        border: '1px solid #fde68a',
                        borderRadius: '5px',
                        cursor: 'pointer',
                      }}
                    >
                      <Unlock size={11} />
                      Edit
                    </button>
                  </div>
                </div>
              )}
            </div>

            {/* Subject table (Supports both student filled schema & backend marksheet) */}
            <div style={{ overflowX: 'auto', border: '1px solid #e2e8f0', borderRadius: '8px' }}>
              <table className="edvana-table" style={{ margin: 0, fontSize: '0.8rem' }}>
                <thead>
                  {viewResult.subjects?.[0]?.mid1_marks !== undefined ? (
                    <tr>
                      <th style={{ width: 140 }}>Course Code</th>
                      <th>Course Title</th>
                      <th style={{ textAlign: 'center', width: 95 }}>Mid Sem 1</th>
                      <th style={{ textAlign: 'center', width: 95 }}>Mid Sem 2</th>
                      <th style={{ textAlign: 'center', width: 105 }}>Theory Marks</th>
                      <th style={{ textAlign: 'center', width: 95 }}>Total Marks</th>
                      <th style={{ textAlign: 'center', width: 75 }}>Credits</th>
                      <th style={{ textAlign: 'center', width: 95 }}>Pass / Fail</th>
                    </tr>
                  ) : (
                    <tr>
                      <th>Course Code</th>
                      <th>Course Title</th>
                      <th style={{ textAlign: 'center' }}>Credits</th>
                      <th style={{ textAlign: 'center' }}>ESE</th>
                      <th style={{ textAlign: 'center' }}>ISE</th>
                      <th style={{ textAlign: 'center' }}>Total</th>
                      <th style={{ textAlign: 'center' }}>GP</th>
                      <th style={{ textAlign: 'center' }}>Grade</th>
                    </tr>
                  )}
                </thead>
                <tbody>
                  {(viewResult.subjects || []).map((s) => {
                    if (s.mid1_marks !== undefined) {
                      return (
                        <tr key={s.id || s.course_code}>
                          <td style={{ fontFamily: 'var(--edvana-font-mono)', fontWeight: 700, color: '#0f172a', fontSize: '0.775rem' }}>
                            {s.course_code}
                          </td>
                          <td style={{ fontWeight: 600, color: '#1e293b' }}>{s.course_name}</td>
                          <td style={{ textAlign: 'center', fontWeight: 600, color: '#0f172a' }}>{s.mid1_marks}</td>
                          <td style={{ textAlign: 'center', fontWeight: 600, color: '#0f172a' }}>{s.mid2_marks}</td>
                          <td style={{ textAlign: 'center', fontWeight: 600, color: '#0f172a' }}>{s.theory_marks}</td>
                          <td style={{ textAlign: 'center', fontWeight: 700, color: '#0f172a', fontFamily: 'var(--edvana-font-mono)' }}>{s.total_marks}</td>
                          <td style={{ textAlign: 'center', fontWeight: 700, color: '#0f172a', fontFamily: 'var(--edvana-font-mono)' }}>{s.credits}</td>
                          <td style={{ textAlign: 'center' }}>
                            <Badge variant={s.is_passed ? 'success' : 'danger'}>
                              {s.is_passed ? 'Pass' : 'Fail'}
                            </Badge>
                          </td>
                        </tr>
                      );
                    }

                    return (
                      <tr key={s.id}>
                        <td style={{ fontFamily: 'var(--edvana-font-mono)', fontWeight: 700, color: '#1E60DC', fontSize: '0.775rem' }}>
                          {s.course_code}
                        </td>
                        <td style={{ fontWeight: 600, color: '#1e293b' }}>{s.course_name}</td>
                        <td style={{ textAlign: 'center', fontWeight: 600 }}>{s.credits}</td>
                        <td style={{ textAlign: 'center' }}>{s.theory_ese_marks ?? '—'}</td>
                        <td style={{ textAlign: 'center' }}>{s.theory_ise_marks ?? '—'}</td>
                        <td style={{ textAlign: 'center', fontWeight: 700, color: '#0f172a' }}>{s.total_marks ?? '—'}</td>
                        <td style={{ textAlign: 'center', fontFamily: 'var(--edvana-font-mono)', fontWeight: 600 }}>{s.grade_point}</td>
                        <td style={{ textAlign: 'center' }}>
                          <Badge variant={s.grade_letter === 'F' ? 'danger' : 'success'}>
                            {s.grade_letter}
                          </Badge>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            {/* Summary footer */}
            <div
              style={{
                display: 'flex',
                flexWrap: 'wrap',
                justifyContent: 'space-between',
                alignItems: 'center',
                gap: '1.25rem',
                padding: '1.25rem 0.5rem 0.5rem',
                marginTop: '1rem',
                borderTop: '1px solid #e2e8f0',
              }}
            >
              <div style={{ display: 'flex', gap: '2rem', flexWrap: 'wrap' }}>
                <div>
                  <div style={{ fontSize: '0.7rem', color: '#64748b', fontWeight: 700, textTransform: 'uppercase' }}>Credits Earned</div>
                  <div style={{ fontSize: '1.15rem', fontWeight: 700, color: '#0f172a' }}>
                    {viewResult.total_credits_earned} / {viewResult.total_credits_registered}
                  </div>
                </div>
                <div>
                  <div style={{ fontSize: '0.7rem', color: '#64748b', fontWeight: 700, textTransform: 'uppercase' }}>SGPA</div>
                  <div style={{ fontSize: '1.15rem', fontWeight: 800, color: '#1E60DC' }}>{viewResult.sgpa || '0.00'}</div>
                </div>
                {viewResult.backlog_count !== undefined && (
                  <div>
                    <div style={{ fontSize: '0.7rem', color: '#64748b', fontWeight: 700, textTransform: 'uppercase' }}>Backlogs</div>
                    <div style={{ fontSize: '1.15rem', fontWeight: 700, color: viewResult.backlog_count === 0 ? '#15803d' : '#b91c1c' }}>
                      {viewResult.backlog_count}
                    </div>
                  </div>
                )}
              </div>

              <Badge variant={viewResult.result_status === 'PASS' ? 'success' : 'danger'}>
                {viewResult.result_status_display?.toUpperCase() || viewResult.result_status}
              </Badge>
            </div>
          </div>
        )}
      </Modal>
    </>
  );
}

/* ──────────────── Helper: Number → Roman Numeral ──────────────── */

function toRoman(num) {
  if (!num || num <= 0) return '';
  const lookup = [
    [1000, 'M'], [900, 'CM'], [500, 'D'], [400, 'CD'],
    [100, 'C'], [90, 'XC'], [50, 'L'], [40, 'XL'],
    [10, 'X'], [9, 'IX'], [5, 'V'], [4, 'IV'], [1, 'I'],
  ];
  let result = '';
  for (const [value, numeral] of lookup) {
    while (num >= value) {
      result += numeral;
      num -= value;
    }
  }
  return result;
}
