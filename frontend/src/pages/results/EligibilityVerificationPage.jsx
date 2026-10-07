import { useState, useEffect, useRef } from 'react';
import { useAuth } from '../../context/AuthContext';
import resultsApi from '../../api/resultsApi';
import PageHeader from '../../components/common/PageHeader';
import Badge from '../../components/common/Badge';
import Modal from '../../components/common/Modal';
import FormField from '../../components/common/FormField';
import { LoadingState, ErrorState, EmptyState } from '../../components/common/StateDisplays';
import {
  Users,
  ArrowLeft,
  CheckCircle2,
  Clock,
  AlertTriangle,
  ShieldCheck,
  Check,
  Flag,
  Search,
  Filter,
  Play,
  RefreshCw,
  Eye,
  BookOpen,
  GraduationCap,
  ChevronRight,
  Award,
  Lock,
} from 'lucide-react';

export default function EligibilityVerificationPage() {
  const { user, activeRole, hasRole } = useAuth();
  const isViewingAsTeacher = activeRole?.codename === 'CLASS_TEACHER';
  const isViewingAsHOD = activeRole?.codename === 'HOD';

  const canEndorseHOD = !isViewingAsTeacher && (isViewingAsHOD || hasRole('HOD') || hasRole('ADMIN_HEAD') || user?.is_superuser);
  const canReviewTeacher = isViewingAsTeacher || hasRole('CLASS_TEACHER') || hasRole('ADMIN_HEAD') || user?.is_superuser;

  // Class cards state
  const [classes, setClasses] = useState([]);
  const [loadingClasses, setLoadingClasses] = useState(true);
  const [classesError, setClassesError] = useState(null);
  const [startingDivId, setStartingDivId] = useState(null);
  const [notice, setNotice] = useState(null);
  const noticeTimer = useRef(null);

  const showNotice = (msg, ms = 5000) => {
    setNotice(msg);
    if (noticeTimer.current) clearTimeout(noticeTimer.current);
    noticeTimer.current = setTimeout(() => setNotice(null), ms);
  };

  useEffect(() => () => {
    if (noticeTimer.current) clearTimeout(noticeTimer.current);
  }, []);

  // Selected class & student roster drill-down state
  const [selectedClass, setSelectedClass] = useState(null);
  const [rosterData, setRosterData] = useState(null);
  const [loadingRoster, setLoadingRoster] = useState(false);
  const [rosterError, setRosterError] = useState(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState('ALL');

  // Review / Marksheet Modal state
  const [selectedStudent, setSelectedStudent] = useState(null);
  const [studentResults, setStudentResults] = useState([]);
  const [loadingStudentResults, setLoadingStudentResults] = useState(false);
  const [actionType, setActionType] = useState('TEACHER_REVIEW'); // 'TEACHER_REVIEW' | 'HOD_ENDORSE' | 'VIEW_ONLY'
  const [reviewMode, setReviewMode] = useState(null); // null | 'APPROVE' | 'FLAG' | 'REJECT'
  const [decisionRemarks, setDecisionRemarks] = useState('');
  const [submittingReview, setSubmittingReview] = useState(false);
  const [reviewError, setReviewError] = useState(null);

  // Graduation queue (Sem 8 PASS students)
  const [gradList, setGradList] = useState([]);
  const [showGradModal, setShowGradModal] = useState(false);
  const [confirmingGradId, setConfirmingGradId] = useState(null);

  useEffect(() => {
    loadClasses();
    if (canEndorseHOD) {
      resultsApi.getGraduationPending()
        .then((res) => setGradList(res.data?.results || res.data || []))
        .catch(() => setGradList([]));
    }
    // Reload when the viewed role changes (role switcher), not just on mount.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeRole?.codename]);

  const loadClasses = async () => {
    try {
      setLoadingClasses(true);
      setClassesError(null);
      const res = await resultsApi.getClasses();
      // Accept both list and paginated shapes (forward-compatible).
      setClasses(res.data?.results || res.data || []);
    } catch (err) {
      setClassesError(err.response?.data?.detail || 'Failed to load class list.');
    } finally {
      setLoadingClasses(false);
    }
  };

  const handleSelectClass = async (cls) => {
    setSelectedClass(cls);
    setSearchQuery('');
    setStatusFilter('ALL');
    loadClassRoster(cls.division_id);
  };

  const loadClassRoster = async (divisionId) => {
    try {
      setLoadingRoster(true);
      setRosterError(null);
      const res = await resultsApi.getClassRoster(divisionId);
      setRosterData(res.data);
    } catch (err) {
      setRosterError(err.response?.data?.detail || 'Failed to load students for this class.');
    } finally {
      setLoadingRoster(false);
    }
  };

  const handleStartVerification = async (e, cls) => {
    e.stopPropagation();
    if (!window.confirm(
      `Start Result Verification for ${cls.class_name}?\n\n` +
      `This opens the upload window for current semester results and initializes the review queue for all ${cls.total_students} students.`
    )) {
      return;
    }

    try {
      setStartingDivId(cls.division_id);
      const res = await resultsApi.startClassVerification(cls.division_id);
      showNotice(res.data?.detail || `Verification initiated for ${cls.class_name}.`);
      await loadClasses();
      if (selectedClass && selectedClass.division_id === cls.division_id) {
        await loadClassRoster(cls.division_id);
      }
    } catch (err) {
      showNotice(err.response?.data?.detail || 'Failed to start verification.', 6000);
    } finally {
      setStartingDivId(null);
    }
  };

  // Open Review / Marksheet Modal
  const handleOpenReviewModal = (student, mode) => {
    setSelectedStudent(student);
    setActionType(mode);
    setReviewMode(null);
    setDecisionRemarks('');
    setReviewError(null);

    // Fetch complete semester results for this student
    setLoadingStudentResults(true);
    resultsApi.getSemesterResults({ student_id: student.student_id })
      .then((res) => {
        setStudentResults(res.data?.results || res.data || []);
      })
      .catch(() => setStudentResults([]))
      .finally(() => setLoadingStudentResults(false));
  };

  const handleReviewSubmit = async (statusChoice, remarksText) => {
    if (!selectedStudent || !selectedStudent.eligibility_id) return;
    if (statusChoice === 'FLAGGED' && !remarksText.trim()) {
      setReviewError('Please specify the reason for flagging so the student/teacher can rectify it.');
      return;
    }

    try {
      setSubmittingReview(true);
      setReviewError(null);

      if (actionType === 'HOD_ENDORSE') {
        await resultsApi.endorseHOD(selectedStudent.eligibility_id, statusChoice, remarksText);
      } else {
        await resultsApi.reviewClassTeacher(selectedStudent.eligibility_id, statusChoice, remarksText);
      }

      setSelectedStudent(null);
      setReviewMode(null);
      setDecisionRemarks('');
      showNotice(`Review recorded successfully: ${statusChoice}`, 4000);

      // Refresh roster and class stats
      if (selectedClass) {
        loadClassRoster(selectedClass.division_id);
      }
      loadClasses();
    } catch (err) {
      const resData = err.response?.data;
      setReviewError(resData?.detail || 'Failed to submit review.');
    } finally {
      setSubmittingReview(false);
    }
  };

  const handleConfirmGraduation = async (row) => {
    if (!window.confirm(`Confirm graduation of ${row.student_name || 'this student'} after Sem 8 PASS?`)) return;
    try {
      setConfirmingGradId(row.id);
      const res = await resultsApi.confirmGraduation(row.id);
      showNotice(res.data?.detail || 'Graduation confirmed.');
      const refreshed = await resultsApi.getGraduationPending();
      setGradList(refreshed.data?.results || refreshed.data || []);
    } catch (err) {
      showNotice(err.response?.data?.detail || 'Failed to confirm graduation.', 6000);
    } finally {
      setConfirmingGradId(null);
    }
  };

  // Filter students in the roster view
  const filteredStudents = (rosterData?.students || []).filter((s) => {
    const query = (searchQuery || '').trim().toLowerCase();
    const matchesSearch =
      !query ||
      (s.student_name || '').toLowerCase().includes(query) ||
      (s.enrollment_no && s.enrollment_no.toLowerCase().includes(query)) ||
      (s.roll_number && s.roll_number.toLowerCase().includes(query));

    if (!matchesSearch) return false;

    if (statusFilter === 'ALL') return true;
    if (statusFilter === 'RESULT_PENDING') return !s.result_filled;
    if (statusFilter === 'TEACHER_PENDING') return s.result_filled && s.class_teacher_status === 'PENDING';
    if (statusFilter === 'HOD_PENDING') return s.class_teacher_status === 'APPROVED' && s.hod_status === 'PENDING';
    if (statusFilter === 'FLAGGED') return s.class_teacher_status === 'FLAGGED' || s.hod_status === 'FLAGGED';
    if (statusFilter === 'ELIGIBLE') return s.final_eligible;

    return true;
  });

  return (
    <div style={{ maxWidth: '1400px', margin: '0 auto', padding: '1.5rem 1rem' }}>
      {/* ─── Header Section ─── */}
      <PageHeader
        title="Result Verification & Annual Progression"
        subtitle="Manage class result submissions, two-tier verification workflows, and progression eligibility."
        actions={
          <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center' }}>
            {canEndorseHOD && gradList.length > 0 && (
              <button
                type="button"
                onClick={() => setShowGradModal(true)}
                className="edvana-btn"
                style={{
                  backgroundColor: '#7c3aed',
                  color: '#ffffff',
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '0.5rem',
                  padding: '0.55rem 1rem',
                  fontSize: '0.85rem',
                  fontWeight: 600,
                  borderRadius: '8px',
                }}
              >
                <GraduationCap size={16} />
                <span>Graduation Queue ({gradList.length})</span>
              </button>
            )}
            <button
              type="button"
              className="edvana-btn edvana-btn-secondary"
              onClick={() => {
                if (selectedClass) loadClassRoster(selectedClass.division_id);
                loadClasses();
              }}
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '0.4rem',
                fontSize: '0.85rem',
                padding: '0.55rem 0.9rem',
              }}
            >
              <RefreshCw size={14} className={loadingClasses || loadingRoster ? 'animate-spin' : ''} />
              <span>Refresh</span>
            </button>
          </div>
        }
      />

      {/* Global Notice Alert */}
      {notice && (
        <div
          style={{
            margin: '1rem 0',
            padding: '0.85rem 1.25rem',
            backgroundColor: '#f0fdf4',
            border: '1px solid #bbf7d0',
            borderRadius: '10px',
            color: '#166534',
            fontSize: '0.875rem',
            display: 'flex',
            alignItems: 'center',
            gap: '0.6rem',
            fontWeight: 500,
          }}
        >
          <CheckCircle2 size={18} style={{ color: '#16a34a', flexShrink: 0 }} />
          <span>{notice}</span>
        </div>
      )}

      {/* ─────────────────────────────────────────────────────────────
          VIEW 1: CLASS CARDS GRID (When no class is selected)
         ───────────────────────────────────────────────────────────── */}
      {!selectedClass ? (
        <div>
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              marginBottom: '1.25rem',
              flexWrap: 'wrap',
              gap: '0.75rem',
            }}
          >
            <div>
              <h2 style={{ fontSize: '1.15rem', fontWeight: 700, color: '#0f172a', margin: 0 }}>
                Academic Classes Roster
              </h2>
              <p style={{ fontSize: '0.8125rem', color: '#64748b', margin: '0.2rem 0 0 0' }}>
                Select a class to drill down into student result status and conduct reviews.
              </p>
            </div>
          </div>

          {loadingClasses ? (
            <LoadingState message="Loading departmental class rosters..." />
          ) : classesError ? (
            <ErrorState message={classesError} onRetry={loadClasses} />
          ) : classes.length === 0 ? (
            <EmptyState
              title="No Classes Assigned"
              description="No classes or divisions found within your current role and department scope."
            />
          ) : (
            <div
              style={{
                display: 'flex',
                flexDirection: 'column',
                gap: '1rem',
                width: '100%',
              }}
            >
              {classes.map((cls) => {
                const filledPct = cls.total_students ? Math.round((cls.results_filled_count / cls.total_students) * 100) : 0;
                const eligiblePct = cls.total_students ? Math.round((cls.final_eligible_count / cls.total_students) * 100) : 0;
                const isStarting = startingDivId === cls.division_id;

                return (
                  <div
                    key={cls.division_id}
                    onClick={() => handleSelectClass(cls)}
                    style={{
                      backgroundColor: '#ffffff',
                      borderRadius: '18px',
                      border: '1.5px solid #e2e8f0',
                      padding: '1.25rem 1.75rem',
                      boxShadow: '0 1px 3px rgba(0,0,0,0.03)',
                      cursor: 'pointer',
                      transition: 'all 0.2s ease',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      gap: '1.5rem',
                      flexWrap: 'wrap',
                      position: 'relative',
                      overflow: 'hidden',
                    }}
                    onMouseEnter={(e) => {
                      e.currentTarget.style.borderColor = '#3b82f6';
                      e.currentTarget.style.boxShadow = '0 6px 18px rgba(59,130,246,0.08)';
                      e.currentTarget.style.transform = 'translateY(-1px)';
                    }}
                    onMouseLeave={(e) => {
                      e.currentTarget.style.borderColor = '#e2e8f0';
                      e.currentTarget.style.boxShadow = '0 1px 3px rgba(0,0,0,0.03)';
                      e.currentTarget.style.transform = 'translateY(0)';
                    }}
                  >
                    {/* Left Accent Stripe based on Year Level */}
                    <div
                      style={{
                        position: 'absolute',
                        left: 0,
                        top: 0,
                        bottom: 0,
                        width: '5px',
                        backgroundColor:
                          cls.year_level === 1 ? '#0ea5e9' :
                          cls.year_level === 2 ? '#3b82f6' :
                          cls.year_level === 3 ? '#8b5cf6' : '#f59e0b',
                      }}
                    />

                    {/* 1. Left Section: Class Identity & Teacher */}
                    <div style={{ flex: '1 1 280px', minWidth: '240px' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '0.45rem', marginBottom: '0.35rem' }}>
                        <span
                          style={{
                            fontSize: '0.75rem',
                            fontWeight: 700,
                            textTransform: 'uppercase',
                            padding: '0.15rem 0.55rem',
                            borderRadius: '6px',
                            backgroundColor: '#f1f5f9',
                            color: '#334155',
                          }}
                        >
                          {cls.department_code}
                        </span>
                        <span
                          style={{
                            fontSize: '0.75rem',
                            fontWeight: 600,
                            padding: '0.15rem 0.55rem',
                            borderRadius: '6px',
                            backgroundColor: '#f8fafc',
                            color: '#475569',
                            border: '1px solid #e2e8f0',
                          }}
                        >
                          Sem {cls.semester_number} {cls.target_semester_number ? `→ Sem ${cls.target_semester_number}` : ''}
                        </span>
                        {cls.is_year_change_class && (
                          <span
                            style={{
                              fontSize: '0.72rem',
                              fontWeight: 700,
                              padding: '0.15rem 0.5rem',
                              borderRadius: '6px',
                              backgroundColor: '#fef3c7',
                              color: '#92400e',
                              border: '1px solid #fde68a',
                            }}
                          >
                            YEAR CHANGE
                          </span>
                        )}
                      </div>

                      <h3 style={{ fontSize: '1.125rem', fontWeight: 800, color: '#0f172a', margin: '0 0 0.35rem 0' }}>
                        {cls.class_name}
                      </h3>

                      <div style={{ fontSize: '0.8125rem', color: '#64748b', display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                        <span>Class Teacher:</span>
                        <strong style={{ color: '#1e293b' }}>{cls.class_teacher_name}</strong>
                      </div>
                    </div>

                    {/* 2. Middle Section: Pipeline Metrics & Progress Bar */}
                    <div style={{ flex: '1.5 1 360px', minWidth: '300px' }}>
                      <div
                        style={{
                          display: 'grid',
                          gridTemplateColumns: 'repeat(4, 1fr)',
                          gap: '0.5rem',
                          backgroundColor: '#f8fafc',
                          padding: '0.65rem 0.85rem',
                          borderRadius: '14px',
                          border: '1px solid #e2e8f0',
                          marginBottom: '0.6rem',
                          textAlign: 'center',
                        }}
                      >
                        <div>
                          <div style={{ fontSize: '0.7rem', fontWeight: 600, color: '#64748b' }}>Students</div>
                          <div style={{ fontSize: '1.05rem', fontWeight: 800, color: '#0f172a' }}>{cls.total_students}</div>
                        </div>
                        <div>
                          <div style={{ fontSize: '0.7rem', fontWeight: 600, color: '#64748b' }}>Filled</div>
                          <div style={{ fontSize: '1.05rem', fontWeight: 800, color: '#0f172a' }}>{cls.results_filled_count}</div>
                        </div>
                        <div>
                          <div style={{ fontSize: '0.7rem', fontWeight: 600, color: '#64748b' }}>Teacher ✓</div>
                          <div style={{ fontSize: '1.05rem', fontWeight: 800, color: '#0f172a' }}>{cls.teacher_approved_count}</div>
                        </div>
                        <div>
                          <div style={{ fontSize: '0.7rem', fontWeight: 600, color: '#64748b' }}>Eligible</div>
                          <div style={{ fontSize: '1.05rem', fontWeight: 800, color: '#0f172a' }}>{cls.final_eligible_count}</div>
                        </div>
                      </div>

                      {/* Progress Bar */}
                      <div>
                        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.73rem', color: '#64748b', marginBottom: '0.25rem' }}>
                          <span>Eligible for Promotion</span>
                          <strong style={{ color: '#16a34a' }}>{cls.final_eligible_count} of {cls.total_students} ({eligiblePct}%)</strong>
                        </div>
                        <div style={{ height: '6px', width: '100%', backgroundColor: '#e2e8f0', borderRadius: '9999px', overflow: 'hidden', display: 'flex' }}>
                          <div style={{ width: `${eligiblePct}%`, backgroundColor: '#16a34a', transition: 'width 0.3s ease' }} />
                          <div style={{ width: `${Math.max(0, filledPct - eligiblePct)}%`, backgroundColor: '#94a3b8', transition: 'width 0.3s ease' }} />
                        </div>
                      </div>
                    </div>

                    {/* 3. Right Section: Status Pill & Action Buttons */}
                    <div style={{ flex: '0 0 auto', display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: '0.65rem' }}>
                      {/* Status Badge */}
                      <div>
                        {cls.is_year_change_class ? (
                          cls.is_verification_started ? (
                            <span
                              style={{
                                display: 'inline-flex',
                                alignItems: 'center',
                                gap: '0.35rem',
                                fontSize: '0.78rem',
                                fontWeight: 700,
                                padding: '0.25rem 0.65rem',
                                borderRadius: '9999px',
                                backgroundColor: '#f0fdf4',
                                color: '#16a34a',
                                border: '1px solid #bbf7d0',
                              }}
                            >
                              <CheckCircle2 size={13} />
                              Verification Active
                            </span>
                          ) : (
                            <span
                              style={{
                                display: 'inline-flex',
                                alignItems: 'center',
                                gap: '0.35rem',
                                fontSize: '0.78rem',
                                fontWeight: 700,
                                padding: '0.25rem 0.65rem',
                                borderRadius: '9999px',
                                backgroundColor: '#eff6ff',
                                color: '#2563eb',
                                border: '1px solid #bfdbfe',
                              }}
                            >
                              <Clock size={13} />
                              Ready to Start
                            </span>
                          )
                        ) : (
                          <span
                            style={{
                              fontSize: '0.75rem',
                              fontWeight: 500,
                              padding: '0.25rem 0.6rem',
                              borderRadius: '9999px',
                              backgroundColor: '#f8fafc',
                              color: '#64748b',
                              border: '1px solid #e2e8f0',
                            }}
                          >
                            Intra-Year Term
                          </span>
                        )}
                      </div>

                      {/* Action Buttons Row */}
                      <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
                        {/* Start Verification Button */}
                        {cls.can_start_verification && !cls.is_verification_started && (
                          <button
                            type="button"
                            onClick={(e) => handleStartVerification(e, cls)}
                            disabled={isStarting}
                            className="edvana-btn"
                            style={{
                              display: 'inline-flex',
                              alignItems: 'center',
                              gap: '0.45rem',
                              padding: '0.55rem 1rem',
                              borderRadius: '10px',
                              fontSize: '0.85rem',
                              fontWeight: 700,
                              backgroundColor: cls.is_verification_started ? '#eff6ff' : '#2563eb',
                              color: cls.is_verification_started ? '#1d4ed8' : '#ffffff',
                              border: cls.is_verification_started ? '1.5px solid #bfdbfe' : 'none',
                              boxShadow: cls.is_verification_started ? 'none' : '0 2px 6px rgba(37,99,235,0.25)',
                              cursor: isStarting ? 'not-allowed' : 'pointer',
                              transition: 'all 0.15s ease',
                            }}
                          >
                            {isStarting ? (
                              <RefreshCw size={14} className="animate-spin" />
                            ) : (
                              <Play size={14} />
                            )}
                            <span>
                              {isStarting ? 'Starting...' : cls.is_verification_started ? 'Re-sync Queue' : 'Start Verification'}
                            </span>
                          </button>
                        )}

                        <button
                          type="button"
                          onClick={() => handleSelectClass(cls)}
                          className="edvana-btn edvana-btn-secondary"
                          style={{
                            display: 'inline-flex',
                            alignItems: 'center',
                            gap: '0.4rem',
                            padding: '0.55rem 0.95rem',
                            fontSize: '0.85rem',
                            fontWeight: 600,
                            borderRadius: '10px',
                          }}
                        >
                          <span>View Students</span>
                          <ChevronRight size={15} />
                        </button>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      ) : (
        /* ─────────────────────────────────────────────────────────────
            VIEW 2: CLASS DRILL-DOWN STUDENT ROSTER
           ───────────────────────────────────────────────────────────── */
        <div>
          {/* Back Navigation & Class Header */}
          {/* Back Navigation & Class Header */}
          <div
            style={{
              backgroundColor: '#ffffff',
              borderRadius: '18px',
              border: '1.5px solid #e2e8f0',
              padding: '1.4rem 1.6rem',
              marginBottom: '1.5rem',
              display: 'flex',
              flexDirection: 'column',
              gap: '1.15rem',
              boxShadow: '0 1px 3px rgba(0,0,0,0.03)',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '0.75rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                <button
                  type="button"
                  onClick={() => setSelectedClass(null)}
                  className="edvana-btn edvana-btn-secondary"
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '0.4rem',
                    padding: '0.45rem 0.85rem',
                    fontSize: '0.85rem',
                    fontWeight: 600,
                    borderRadius: '10px',
                  }}
                >
                  <ArrowLeft size={16} />
                  <span>Back to Classes</span>
                </button>
                <div>
                  <h2 style={{ fontSize: '1.25rem', fontWeight: 800, color: '#0f172a', margin: 0 }}>
                    {selectedClass.class_name}
                  </h2>
                  <div style={{ fontSize: '0.8125rem', color: '#64748b', display: 'flex', gap: '0.75rem', marginTop: '0.2rem' }}>
                    <span>Department: <strong>{selectedClass.department_name}</strong></span>
                    <span>•</span>
                    <span>Class Teacher: <strong>{selectedClass.class_teacher_name}</strong></span>
                    <span>•</span>
                    <span>Target Sem: <strong>Sem {selectedClass.target_semester_number || selectedClass.semester_number}</strong></span>
                  </div>
                </div>
              </div>

              {selectedClass.is_verification_started ? (
                <span
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '0.4rem',
                    fontSize: '0.8rem',
                    fontWeight: 700,
                    padding: '0.35rem 0.85rem',
                    borderRadius: '9999px',
                    backgroundColor: '#f0fdf4',
                    color: '#16a34a',
                    border: '1px solid #bbf7d0',
                  }}
                >
                  <CheckCircle2 size={14} />
                  Verification Active
                </span>
              ) : selectedClass.can_start_verification ? (
                <button
                  type="button"
                  onClick={(e) => handleStartVerification(e, selectedClass)}
                  disabled={startingDivId === selectedClass.division_id}
                  className="edvana-btn edvana-btn-primary"
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '0.4rem',
                    fontSize: '0.85rem',
                    fontWeight: 600,
                    borderRadius: '10px',
                    padding: '0.5rem 1rem',
                  }}
                >
                  <Play size={14} />
                  <span>Start Verification</span>
                </button>
              ) : null}
            </div>

            {/* Class Stats Row */}
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))',
                gap: '0.75rem',
                borderTop: '1px solid #f1f5f9',
                paddingTop: '1rem',
              }}
            >
              {[
                { label: 'Total Students', value: rosterData?.total_students || 0 },
                { label: '1. Results Filled', value: rosterData?.students?.filter((s) => s.result_filled).length || 0 },
                { label: '2. Teacher Approved', value: rosterData?.students?.filter((s) => s.class_teacher_status === 'APPROVED').length || 0 },
                { label: '3. HOD Endorsed', value: rosterData?.students?.filter((s) => s.hod_status === 'APPROVED').length || 0 },
                { label: '4. Added to Eligible List', value: rosterData?.students?.filter((s) => s.final_eligible).length || 0 },
              ].map((stat, idx) => (
                <div
                  key={idx}
                  style={{
                    padding: '0.75rem 1rem',
                    backgroundColor: '#f8fafc',
                    borderRadius: '14px',
                    border: '1px solid #e2e8f0',
                  }}
                >
                  <div style={{ fontSize: '0.75rem', fontWeight: 600, color: '#64748b', marginBottom: '0.2rem' }}>
                    {stat.label}
                  </div>
                  <div style={{ fontSize: '1.35rem', fontWeight: 800, color: '#0f172a' }}>
                    {stat.value}
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Search & Filter Bar */}
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              flexWrap: 'wrap',
              gap: '1rem',
              marginBottom: '1rem',
            }}
          >
            {/* Search Input */}
            <div style={{ position: 'relative', width: '320px', maxWidth: '100%' }}>
              <Search size={16} style={{ position: 'absolute', left: '0.75rem', top: '50%', transform: 'translateY(-50%)', color: '#94a3b8' }} />
              <input
                type="text"
                placeholder="Search by student name or PRN..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="edvana-input"
                style={{ paddingLeft: '2.25rem', width: '100%', fontSize: '0.85rem', borderRadius: '10px' }}
              />
            </div>

            {/* Pipeline Stage Filter Pills */}
            <div style={{ display: 'flex', gap: '0.4rem', flexWrap: 'wrap' }}>
              {[
                { id: 'ALL', label: 'All Students' },
                { id: 'RESULT_PENDING', label: 'Result Pending' },
                { id: 'TEACHER_PENDING', label: 'Needs Teacher Review' },
                { id: 'HOD_PENDING', label: 'Needs HOD Review' },
                { id: 'FLAGGED', label: 'Flagged' },
                { id: 'ELIGIBLE', label: 'Eligible List' },
              ].map((f) => (
                <button
                  key={f.id}
                  type="button"
                  onClick={() => setStatusFilter(f.id)}
                  style={{
                    padding: '0.4rem 0.85rem',
                    borderRadius: '9999px',
                    fontSize: '0.78rem',
                    fontWeight: statusFilter === f.id ? 700 : 500,
                    backgroundColor: statusFilter === f.id ? '#0f172a' : '#ffffff',
                    color: statusFilter === f.id ? '#ffffff' : '#475569',
                    border: '1px solid',
                    borderColor: statusFilter === f.id ? '#0f172a' : '#cbd5e1',
                    cursor: 'pointer',
                    transition: 'all 0.15s ease',
                  }}
                >
                  {f.label}
                </button>
              ))}
            </div>
          </div>

          {/* Student Roster Table */}
          {loadingRoster ? (
            <LoadingState message="Loading class student records..." />
          ) : rosterError ? (
            <ErrorState message={rosterError} onRetry={() => loadClassRoster(selectedClass.division_id)} />
          ) : filteredStudents.length === 0 ? (
            <EmptyState
              title="No Students Matching Filters"
              description="No student records match the active search query or status filter."
            />
          ) : (
            <div className="edvana-card" style={{ borderRadius: '18px', border: '1.5px solid #e2e8f0', overflow: 'hidden' }}>
              <div style={{ overflowX: 'auto' }}>
                <table className="edvana-table" style={{ margin: 0, width: '100%' }}>
                  <thead>
                    <tr>
                      <th style={{ width: 60, textAlign: 'center' }}>Roll</th>
                      <th>Student Details</th>
                      <th style={{ textAlign: 'center' }}>1. Result Filled</th>
                      <th style={{ textAlign: 'center' }}>2. Teacher Review</th>
                      <th style={{ textAlign: 'center' }}>3. HOD Endorsement</th>
                      <th style={{ textAlign: 'center' }}>4. Eligible List</th>
                      <th style={{ textAlign: 'center', width: 150 }}>Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredStudents.map((s) => (
                      <tr key={s.student_id}>
                        {/* Roll Number */}
                        <td style={{ textAlign: 'center', fontWeight: 700, color: '#334155', fontFamily: 'var(--edvana-font-mono)' }}>
                          {s.roll_number}
                        </td>

                        {/* Student Details */}
                        <td>
                          <div style={{ fontWeight: 700, color: '#0f172a', fontSize: '0.875rem' }}>
                            {s.student_name}
                          </div>
                          <div style={{ fontSize: '0.75rem', color: '#64748b', fontFamily: 'var(--edvana-font-mono)' }}>
                            PRN: {s.enrollment_no || '—'}
                          </div>
                        </td>

                        {/* 1. Result Filled */}
                        <td style={{ textAlign: 'center' }}>
                          {s.result_filled ? (
                            <div>
                              <span
                                style={{
                                  display: 'inline-flex',
                                  alignItems: 'center',
                                  gap: '0.3rem',
                                  fontSize: '0.75rem',
                                  fontWeight: 700,
                                  padding: '0.25rem 0.55rem',
                                  borderRadius: '6px',
                                  backgroundColor: '#f0fdf4',
                                  color: '#16a34a',
                                  border: '1px solid #bbf7d0',
                                }}
                              >
                                <Check size={12} />
                                Filled (SGPA: {s.semester_result?.sgpa})
                              </span>
                              {s.semester_result?.backlog_count > 0 && (
                                <div style={{ fontSize: '0.7rem', color: '#dc2626', fontWeight: 600, marginTop: '2px' }}>
                                  {s.semester_result.backlog_count} Backlog(s)
                                </div>
                              )}
                            </div>
                          ) : (
                            <span
                              style={{
                                display: 'inline-flex',
                                alignItems: 'center',
                                gap: '0.3rem',
                                fontSize: '0.75rem',
                                fontWeight: 500,
                                padding: '0.25rem 0.55rem',
                                borderRadius: '6px',
                                backgroundColor: '#fef3c7',
                                color: '#b45309',
                                border: '1px solid #fde68a',
                              }}
                            >
                              <Clock size={12} />
                              Pending Upload
                            </span>
                          )}
                        </td>

                        {/* 2. Teacher Verification */}
                        <td style={{ textAlign: 'center' }}>
                          {s.class_teacher_status === 'APPROVED' ? (
                            <div>
                              <span
                                style={{
                                  display: 'inline-flex',
                                  alignItems: 'center',
                                  gap: '0.3rem',
                                  fontSize: '0.75rem',
                                  fontWeight: 700,
                                  padding: '0.25rem 0.55rem',
                                  borderRadius: '6px',
                                  backgroundColor: '#f0fdf4',
                                  color: '#15803d',
                                }}
                              >
                                <CheckCircle2 size={12} />
                                Approved
                              </span>
                              {s.class_teacher_name && (
                                <div style={{ fontSize: '0.68rem', color: '#64748b' }}>by {s.class_teacher_name}</div>
                              )}
                            </div>
                          ) : s.class_teacher_status === 'FLAGGED' ? (
                            <div>
                              <span
                                style={{
                                  display: 'inline-flex',
                                  alignItems: 'center',
                                  gap: '0.3rem',
                                  fontSize: '0.75rem',
                                  fontWeight: 700,
                                  padding: '0.25rem 0.55rem',
                                  borderRadius: '6px',
                                  backgroundColor: '#fef2f2',
                                  color: '#b91c1c',
                                  border: '1px solid #fecaca',
                                }}
                              >
                                <Flag size={11} />
                                Flagged
                              </span>
                              {s.class_teacher_remarks && (
                                <div style={{ fontSize: '0.68rem', color: '#b91c1c', maxWidth: '140px', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }} title={s.class_teacher_remarks}>
                                  "{s.class_teacher_remarks}"
                                </div>
                              )}
                            </div>
                          ) : s.class_teacher_status === 'PENDING' ? (
                            <span style={{ fontSize: '0.75rem', fontWeight: 600, color: '#d97706' }}>
                              Pending Review
                            </span>
                          ) : (
                            <span style={{ fontSize: '0.75rem', color: '#94a3b8' }}>Not Started</span>
                          )}
                        </td>

                        {/* 3. HOD Verification */}
                        <td style={{ textAlign: 'center' }}>
                          {s.hod_status === 'APPROVED' ? (
                            <div>
                              <span
                                style={{
                                  display: 'inline-flex',
                                  alignItems: 'center',
                                  gap: '0.3rem',
                                  fontSize: '0.75rem',
                                  fontWeight: 700,
                                  padding: '0.25rem 0.55rem',
                                  borderRadius: '6px',
                                  backgroundColor: '#faf5ff',
                                  color: '#7c3aed',
                                }}
                              >
                                <CheckCircle2 size={12} />
                                Endorsed
                              </span>
                              {s.hod_name && (
                                <div style={{ fontSize: '0.68rem', color: '#64748b' }}>by {s.hod_name}</div>
                              )}
                            </div>
                          ) : s.hod_status === 'FLAGGED' ? (
                            <div>
                              <span
                                style={{
                                  display: 'inline-flex',
                                  alignItems: 'center',
                                  gap: '0.3rem',
                                  fontSize: '0.75rem',
                                  fontWeight: 700,
                                  padding: '0.25rem 0.55rem',
                                  borderRadius: '6px',
                                  backgroundColor: '#fff7ed',
                                  color: '#c2410c',
                                }}
                              >
                                <Flag size={11} />
                                Flagged Back
                              </span>
                            </div>
                          ) : s.hod_status === 'REJECTED' ? (
                            <span style={{ fontSize: '0.75rem', fontWeight: 700, color: '#dc2626' }}>
                              Rejected
                            </span>
                          ) : s.hod_status === 'PENDING' ? (
                            <span style={{ fontSize: '0.75rem', fontWeight: 500, color: '#64748b' }}>
                              {s.class_teacher_status === 'APPROVED' ? 'Awaiting Endorsement' : 'Waiting for Teacher'}
                            </span>
                          ) : (
                            <span style={{ fontSize: '0.75rem', color: '#94a3b8' }}>Not Started</span>
                          )}
                        </td>

                        {/* 4. Eligible List */}
                        <td style={{ textAlign: 'center' }}>
                          {s.final_eligible ? (
                            <span
                              style={{
                                display: 'inline-flex',
                                alignItems: 'center',
                                gap: '0.35rem',
                                fontSize: '0.78rem',
                                fontWeight: 700,
                                padding: '0.3rem 0.65rem',
                                borderRadius: '9999px',
                                backgroundColor: '#dcfce7',
                                color: '#15803d',
                                border: '1px solid #86efac',
                              }}
                            >
                              <ShieldCheck size={13} />
                              Added to Eligible List
                            </span>
                          ) : (
                            <span style={{ fontSize: '0.75rem', color: '#94a3b8', fontStyle: 'italic' }}>
                              Pending Approval
                            </span>
                          )}
                        </td>

                        {/* Actions */}
                        <td style={{ textAlign: 'center' }}>
                          <div style={{ display: 'inline-flex', gap: '0.4rem', justifyContent: 'center' }}>
                            {canReviewTeacher && s.can_review_teacher ? (
                              <button
                                type="button"
                                onClick={() => handleOpenReviewModal(s, 'TEACHER_REVIEW')}
                                className="edvana-btn"
                                style={{
                                  padding: '0.35rem 0.75rem',
                                  fontSize: '0.78rem',
                                  fontWeight: 600,
                                  backgroundColor: '#eff6ff',
                                  color: '#1d4ed8',
                                  border: '1px solid #bfdbfe',
                                }}
                              >
                                Review
                              </button>
                            ) : canEndorseHOD && s.can_endorse_hod ? (
                              <button
                                type="button"
                                onClick={() => handleOpenReviewModal(s, 'HOD_ENDORSE')}
                                className="edvana-btn"
                                style={{
                                  padding: '0.35rem 0.75rem',
                                  fontSize: '0.78rem',
                                  fontWeight: 600,
                                  backgroundColor: '#faf5ff',
                                  color: '#7c3aed',
                                  border: '1px solid #ddd6fe',
                                }}
                              >
                                Endorse
                              </button>
                            ) : (
                              <button
                                type="button"
                                onClick={() => handleOpenReviewModal(s, 'VIEW_ONLY')}
                                className="edvana-btn edvana-btn-secondary"
                                style={{
                                  padding: '0.35rem 0.65rem',
                                  fontSize: '0.78rem',
                                  display: 'inline-flex',
                                  alignItems: 'center',
                                  gap: '0.3rem',
                                }}
                              >
                                <Eye size={12} />
                                View
                              </button>
                            )}
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      )}

      {/* ─────────────────────────────────────────────────────────────
          MODAL 1: STUDENT RESULTS & TEACHER/HOD REVIEW MODAL
         ───────────────────────────────────────────────────────────── */}
      {selectedStudent && (
        <Modal
          isOpen={Boolean(selectedStudent)}
          onClose={() => {
            setSelectedStudent(null);
            setReviewMode(null);
          }}
          title={
            actionType === 'HOD_ENDORSE'
              ? 'HOD Promotion Endorsement'
              : actionType === 'TEACHER_REVIEW'
              ? 'Class Teacher Result Verification'
              : 'Student Academic Results Inspection'
          }
          size="xl"
        >
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
            {/* Student Overview Banner */}
            <div
              style={{
                backgroundColor: '#f8fafc',
                borderRadius: '10px',
                padding: '1rem 1.25rem',
                border: '1px solid #e2e8f0',
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                flexWrap: 'wrap',
                gap: '0.75rem',
              }}
            >
              <div>
                <div style={{ fontSize: '1.1rem', fontWeight: 800, color: '#0f172a' }}>
                  {selectedStudent.student_name}
                </div>
                <div style={{ fontSize: '0.8125rem', color: '#64748b' }}>
                  PRN: {selectedStudent.enrollment_no || '—'} • Roll No: {selectedStudent.roll_number}
                </div>
              </div>

              <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                <span
                  style={{
                    fontSize: '0.75rem',
                    fontWeight: 700,
                    padding: '0.25rem 0.65rem',
                    borderRadius: '6px',
                    backgroundColor:
                      selectedStudent.calculated_status === 'ELIGIBLE' ? '#dcfce7' :
                      selectedStudent.calculated_status === 'PROVISIONAL' ? '#fef3c7' : '#fee2e2',
                    color:
                      selectedStudent.calculated_status === 'ELIGIBLE' ? '#166534' :
                      selectedStudent.calculated_status === 'PROVISIONAL' ? '#92400e' : '#991b1b',
                  }}
                >
                  System Status: {selectedStudent.calculated_status_display || 'Evaluating'}
                </span>
                {selectedStudent.final_eligible && (
                  <span
                    style={{
                      fontSize: '0.75rem',
                      fontWeight: 700,
                      padding: '0.25rem 0.65rem',
                      borderRadius: '6px',
                      backgroundColor: '#15803d',
                      color: '#ffffff',
                    }}
                  >
                    Final Eligible
                  </span>
                )}
              </div>
            </div>

            {/* Semester Results Marksheets */}
            <div>
              <h4 style={{ fontSize: '0.95rem', fontWeight: 700, color: '#0f172a', marginBottom: '0.75rem' }}>
                Published Semester Marksheets
              </h4>

              {loadingStudentResults ? (
                <LoadingState message="Fetching student marksheets..." />
              ) : studentResults.length === 0 ? (
                <div
                  style={{
                    padding: '1.5rem',
                    textAlign: 'center',
                    background: '#f8fafc',
                    borderRadius: '8px',
                    color: '#64748b',
                    fontSize: '0.875rem',
                  }}
                >
                  No published marksheet found for this student yet.
                </div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem', maxHeight: '360px', overflowY: 'auto' }}>
                  {studentResults.map((sr) => (
                    <div
                      key={sr.id}
                      style={{
                        border: '1px solid #e2e8f0',
                        borderRadius: '8px',
                        overflow: 'hidden',
                      }}
                    >
                      <div
                        style={{
                          backgroundColor: '#f1f5f9',
                          padding: '0.65rem 1rem',
                          display: 'flex',
                          justifyContent: 'space-between',
                          alignItems: 'center',
                          fontSize: '0.8125rem',
                          fontWeight: 700,
                          color: '#1e293b',
                        }}
                      >
                        <span>Semester {sr.semester_number} ({sr.exam_session})</span>
                        <div style={{ display: 'flex', gap: '1rem' }}>
                          <span>SGPA: <strong style={{ color: '#2563eb' }}>{sr.sgpa ?? '—'}</strong></span>
                          <span>Earned Credits: <strong>{sr.total_credits_earned} / {sr.total_credits_registered}</strong></span>
                          <span>Status: <strong>{sr.result_status_display}</strong></span>
                        </div>
                      </div>

                      <table className="edvana-table" style={{ margin: 0, fontSize: '0.78rem' }}>
                        <thead>
                          <tr>
                            <th>Course</th>
                            <th>Title</th>
                            <th style={{ textAlign: 'center' }}>Credits</th>
                            <th style={{ textAlign: 'center' }}>Theory (ESE)</th>
                            <th style={{ textAlign: 'center' }}>ISE / Mid</th>
                            <th style={{ textAlign: 'center' }}>Total</th>
                            <th style={{ textAlign: 'center' }}>Grade</th>
                          </tr>
                        </thead>
                        <tbody>
                          {(sr.subjects || []).map((sub) => (
                            <tr key={sub.id}>
                              <td style={{ fontFamily: 'var(--edvana-font-mono)', fontWeight: 600 }}>{sub.course_code}</td>
                              <td>{sub.course_name}</td>
                              <td style={{ textAlign: 'center' }}>{sub.credits}</td>
                              <td style={{ textAlign: 'center', fontWeight: sub.theory_marks < 20 ? 700 : 400, color: sub.theory_marks < 20 ? '#dc2626' : 'inherit' }}>
                                {sub.theory_marks ?? '—'}
                              </td>
                              <td style={{ textAlign: 'center' }}>{sub.theory_ise_marks ?? '—'}</td>
                              <td style={{ textAlign: 'center', fontWeight: 600 }}>{sub.total_marks ?? '—'}</td>
                              <td style={{ textAlign: 'center' }}>
                                <span
                                  style={{
                                    fontWeight: 700,
                                    color: sub.grade_letter === 'F' ? '#dc2626' : '#16a34a',
                                  }}
                                >
                                  {sub.grade_letter}
                                </span>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Review Error Display */}
            {reviewError && (
              <div
                style={{
                  padding: '0.75rem',
                  backgroundColor: '#fef2f2',
                  border: '1px solid #fecaca',
                  borderRadius: '6px',
                  color: '#b91c1c',
                  fontSize: '0.8125rem',
                }}
              >
                {reviewError}
              </div>
            )}

            {/* Action Workflow Controls (Teacher or HOD) */}
            {actionType !== 'VIEW_ONLY' && (
              <div style={{ borderTop: '1px solid #e2e8f0', paddingTop: '1rem' }}>
                {reviewMode === null ? (
                  <div>
                    <div style={{ fontSize: '0.85rem', fontWeight: 700, color: '#0f172a', marginBottom: '0.75rem' }}>
                      {actionType === 'HOD_ENDORSE' ? 'HOD Endorsement Action' : 'Class Teacher Verification Action'}
                    </div>
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '0.75rem' }}>
                      <button
                        type="button"
                        onClick={() => {
                          setReviewMode('FLAG');
                          setDecisionRemarks('');
                          setReviewError(null);
                        }}
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          gap: '0.4rem',
                          padding: '0.75rem 1rem',
                          borderRadius: '8px',
                          fontWeight: 600,
                          fontSize: '0.85rem',
                          backgroundColor: '#fef2f2',
                          color: '#b91c1c',
                          border: '1.5px solid #f87171',
                          cursor: 'pointer',
                        }}
                      >
                        <Flag size={15} />
                        <span>{actionType === 'HOD_ENDORSE' ? 'Flag Back to Teacher' : 'Flag Discrepancy for Student'}</span>
                      </button>

                      <button
                        type="button"
                        onClick={() => {
                          setReviewMode('APPROVE');
                          setDecisionRemarks('Marks verified and approved.');
                          setReviewError(null);
                        }}
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          gap: '0.4rem',
                          padding: '0.75rem 1rem',
                          borderRadius: '8px',
                          fontWeight: 600,
                          fontSize: '0.85rem',
                          backgroundColor: '#f0fdf4',
                          color: '#15803d',
                          border: '1.5px solid #4ade80',
                          cursor: 'pointer',
                        }}
                      >
                        <Check size={15} />
                        <span>{actionType === 'HOD_ENDORSE' ? 'Approve & Endorse (Add to Eligible)' : 'Approve & Lock Record'}</span>
                      </button>
                    </div>
                  </div>
                ) : reviewMode === 'FLAG' ? (
                  /* Flag remarks form */
                  <div style={{ backgroundColor: '#fef2f2', border: '1.5px solid #fecaca', borderRadius: '8px', padding: '1rem' }}>
                    <div style={{ fontWeight: 700, color: '#991b1b', fontSize: '0.875rem', marginBottom: '0.3rem', display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                      <Flag size={15} />
                      <span>Specify Flag Remarks (Required)</span>
                    </div>
                    <textarea
                      rows={2}
                      className="edvana-input"
                      style={{ width: '100%', borderColor: '#f87171', fontSize: '0.85rem' }}
                      placeholder="e.g. Theory marks discrepancy in subject CS201. Please check original marksheet."
                      value={decisionRemarks}
                      onChange={(e) => setDecisionRemarks(e.target.value)}
                      autoFocus
                    />
                    <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.6rem', marginTop: '0.75rem' }}>
                      <button
                        type="button"
                        className="edvana-btn edvana-btn-secondary"
                        onClick={() => setReviewMode(null)}
                        disabled={submittingReview}
                      >
                        Cancel
                      </button>
                      <button
                        type="button"
                        onClick={() => handleReviewSubmit('FLAGGED', decisionRemarks)}
                        disabled={submittingReview}
                        className="edvana-btn"
                        style={{ backgroundColor: '#dc2626', color: '#ffffff', fontWeight: 600 }}
                      >
                        {submittingReview ? 'Submitting...' : 'Confirm Flag'}
                      </button>
                    </div>
                  </div>
                ) : (
                  /* Approve remarks form */
                  <div style={{ backgroundColor: '#f0fdf4', border: '1.5px solid #bbf7d0', borderRadius: '8px', padding: '1rem' }}>
                    <div style={{ fontWeight: 700, color: '#166534', fontSize: '0.875rem', marginBottom: '0.3rem', display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                      <Check size={15} />
                      <span>{actionType === 'HOD_ENDORSE' ? 'Confirm Promotion Endorsement' : 'Confirm Teacher Approval'}</span>
                    </div>
                    <textarea
                      rows={2}
                      className="edvana-input"
                      style={{ width: '100%', borderColor: '#86efac', fontSize: '0.85rem' }}
                      value={decisionRemarks}
                      onChange={(e) => setDecisionRemarks(e.target.value)}
                      placeholder="Optional audit remarks..."
                    />
                    <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.6rem', marginTop: '0.75rem' }}>
                      <button
                        type="button"
                        className="edvana-btn edvana-btn-secondary"
                        onClick={() => setReviewMode(null)}
                        disabled={submittingReview}
                      >
                        Cancel
                      </button>
                      <button
                        type="button"
                        onClick={() => handleReviewSubmit('APPROVED', decisionRemarks)}
                        disabled={submittingReview}
                        className="edvana-btn"
                        style={{ backgroundColor: '#16a34a', color: '#ffffff', fontWeight: 600 }}
                      >
                        {submittingReview ? 'Submitting...' : 'Confirm Approval'}
                      </button>
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        </Modal>
      )}

      {/* ─────────────────────────────────────────────────────────────
          MODAL 2: HOD GRADUATION CONFIRMATION (Sem 8 PASS students)
         ───────────────────────────────────────────────────────────── */}
      {showGradModal && (
        <Modal
          isOpen={showGradModal}
          onClose={() => setShowGradModal(false)}
          title="Graduation Confirmation (Sem 8 PASS Students)"
          size="lg"
        >
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
            <p style={{ fontSize: '0.85rem', color: '#64748b', margin: 0 }}>
              The following Final Year students have passed all examinations including Semester 8 and are eligible for degree completion.
            </p>

            <table className="edvana-table" style={{ margin: 0, fontSize: '0.8125rem' }}>
              <thead>
                <tr>
                  <th>Student Name</th>
                  <th>PRN / Seat</th>
                  <th style={{ textAlign: 'center' }}>CGPA</th>
                  <th style={{ textAlign: 'center' }}>Action</th>
                </tr>
              </thead>
              <tbody>
                {gradList.map((g) => (
                  <tr key={g.id}>
                    <td><strong>{g.student_name}</strong></td>
                    <td>{g.enrollment_no || g.seat_number}</td>
                    <td style={{ textAlign: 'center', fontWeight: 700, color: '#2563eb' }}>{g.cgpa || '—'}</td>
                    <td style={{ textAlign: 'center' }}>
                      <button
                        type="button"
                        onClick={() => handleConfirmGraduation(g)}
                        disabled={confirmingGradId === g.id}
                        className="edvana-btn"
                        style={{
                          backgroundColor: '#16a34a',
                          color: '#ffffff',
                          fontSize: '0.78rem',
                          fontWeight: 600,
                          padding: '0.35rem 0.75rem',
                        }}
                      >
                        {confirmingGradId === g.id ? 'Confirming...' : 'Confirm Graduation'}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Modal>
      )}
    </div>
  );
}
