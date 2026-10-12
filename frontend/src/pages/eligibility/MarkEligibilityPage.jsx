import { useState, useEffect, useRef } from 'react';
import { useAuth } from '../../context/AuthContext';
import resultsApi from '../../api/resultsApi';
import academicApi from '../../api/academicApi';
import PageHeader from '../../components/common/PageHeader';
import Modal from '../../components/common/Modal';
import { LoadingState, ErrorState, EmptyState } from '../../components/common/StateDisplays';
import {
  CheckCircle2,
  Check,
  Search,
  Play,
  RefreshCw,
  ArrowLeft,
  ChevronRight,
  ShieldCheck,
  XCircle,
  Pencil,
  X,
  GraduationCap,
} from 'lucide-react';

/**
 * MarkEligibilityPage — temporary profile-only eligibility flow (results frozen).
 *
 * - CT sees own class, HOD sees all dept classes (backend scopes getClasses).
 * - Start Verification: same rules as results flow (year-change 2/4/6 + teacher assigned).
 * - Roster: Eligible / Not Eligible / Profile Not Locked + 2 buttons.
 * - Gate: profile_locked only. CT must mark first, then HOD. Both APPROVED
 *   => final_eligible => Candidate Ledger + admission PDF unlock.
 * - FY Sem-1 / DSE Sem-3 freshers stay auto-eligible (no rows needed).
 */
export default function MarkEligibilityPage() {
  const { user, activeRole, hasRole } = useAuth();
  const isViewingAsTeacher = activeRole?.codename === 'CLASS_TEACHER';
  const isViewingAsHOD = activeRole?.codename === 'HOD';

  const canMarkTeacher =
    isViewingAsTeacher || hasRole('CLASS_TEACHER') || user?.is_superuser;
  const canMarkHod =
    !isViewingAsTeacher &&
    (isViewingAsHOD || hasRole('HOD') || hasRole('ADMIN_HEAD') || user?.is_superuser);

  // One hat at a time: CT view acts as TEACHER, everyone else on this page
  // acts as HOD (even if they also hold a CT role). This is why there is only
  // one pair of buttons — Eligible / Not Eligible — never T- + H- together.
  const actingSide = isViewingAsTeacher ? 'TEACHER' : 'HOD';

  const [classes, setClasses] = useState([]);
  const [loadingClasses, setLoadingClasses] = useState(true);
  const [classesError, setClassesError] = useState(null);
  const [startingDivId, setStartingDivId] = useState(null);
  const [promotingDivId, setPromotingDivId] = useState(null);
  const [notice, setNotice] = useState(null);
  const noticeTimer = useRef(null);

  const [selectedClass, setSelectedClass] = useState(null);
  const [rosterData, setRosterData] = useState(null);
  const [loadingRoster, setLoadingRoster] = useState(false);
  const [rosterError, setRosterError] = useState(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState('ALL');
  const [markingKey, setMarkingKey] = useState(null); // `${studentId}:${side}`
  // Decided rows collapse to a single pill + pen (prevents accidental re-taps).
  // Pen re-opens the two buttons for that student only.
  const [editingId, setEditingId] = useState(null);
  const [bulkApproving, setBulkApproving] = useState(false);

  // Promote Class state (same flow as Result Verification: dry-run preview
  // modal with ready/unpaid/failed/blocked buckets + repeater class).
  const [promoteTarget, setPromoteTarget] = useState(null);
  const [promotePreview, setPromotePreview] = useState(null);
  const [executingPromote, setExecutingPromote] = useState(false);
  const [selectedRepeaterStudents, setSelectedRepeaterStudents] = useState([]);

  const showNotice = (msg, ms = 5000) => {
    setNotice(msg);
    if (noticeTimer.current) clearTimeout(noticeTimer.current);
    noticeTimer.current = setTimeout(() => setNotice(null), ms);
  };

  useEffect(
    () => () => {
      if (noticeTimer.current) clearTimeout(noticeTimer.current);
    },
    []
  );

  useEffect(() => {
    loadClasses();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeRole?.codename]);

  const loadClasses = async () => {
    try {
      setLoadingClasses(true);
      setClassesError(null);
      const res = await resultsApi.getClasses();
      setClasses(res.data?.results || res.data || []);
    } catch (err) {
      setClassesError(err.response?.data?.detail || 'Failed to load classes.');
    } finally {
      setLoadingClasses(false);
    }
  };

  const loadClassRoster = async (divisionId, retried = false) => {
    try {
      setLoadingRoster(true);
      setRosterError(null);
      const res = await resultsApi.getClassRoster(divisionId);
      setRosterData(res.data);
      if (res.data?.warning) showNotice(res.data.warning, 6000);
    } catch (err) {
      const statusCode = err.response?.status;
      if (!retried && (statusCode >= 500 || !err.response)) {
        await new Promise((r) => setTimeout(r, 800));
        return loadClassRoster(divisionId, true);
      }
      setRosterError(err.response?.data?.detail || 'Failed to load students.');
    } finally {
      setLoadingRoster(false);
    }
  };

  const handleSelectClass = (cls) => {
    setSelectedClass(cls);
    setSearchQuery('');
    setStatusFilter('ALL');
    setEditingId(null);
    loadClassRoster(cls.division_id);
  };

  const handleStartVerification = async (e, cls) => {
    e.stopPropagation();
    if (
      !window.confirm(
        `Start Eligibility Marking for ${cls.class_name}?\n\nThis creates the pending list for all ${cls.total_students} students. No results needed — only profile lock is checked.`
      )
    )
      return;
    try {
      setStartingDivId(cls.division_id);
      const res = await resultsApi.startClassVerification(cls.division_id);
      showNotice(res.data?.detail || `Marking started for ${cls.class_name}.`);
      await loadClasses();
      if (selectedClass && selectedClass.division_id === cls.division_id) {
        await loadClassRoster(cls.division_id);
      }
    } catch (err) {
      showNotice(err.response?.data?.detail || 'Failed to start marking.', 6000);
    } finally {
      setStartingDivId(null);
    }
  };

  const simpleStatus = (s) => {
    if (!s.profile_locked) return 'PROFILE_UNLOCKED';
    if (!s.eligibility_id) return 'NOT_STARTED';
    if (s.final_eligible) return 'ELIGIBLE';
    if (s.hod_status === 'REJECTED' || s.class_teacher_status === 'REJECTED')
      return 'NOT_ELIGIBLE';
    if (s.class_teacher_status === 'PENDING') return 'TEACHER_PENDING';
    if (s.hod_status === 'PENDING' && s.class_teacher_status === 'APPROVED')
      return 'HOD_PENDING';
    return 'PENDING';
  };

  const statusMeta = {
    ELIGIBLE: { label: 'Eligible', bg: '#f0fdf4', fg: '#15803d', bd: '#bbf7d0' },
    NOT_ELIGIBLE: { label: 'Not Eligible', bg: '#fef2f2', fg: '#b91c1c', bd: '#fecaca' },
    PROFILE_UNLOCKED: { label: 'Profile Not Locked', bg: '#fffbeb', fg: '#b45309', bd: '#fde68a' },
    TEACHER_PENDING: { label: 'Needs Teacher Mark', bg: '#eff6ff', fg: '#1d4ed8', bd: '#bfdbfe' },
    HOD_PENDING: { label: 'Needs HOD Mark', bg: '#faf5ff', fg: '#7c3aed', bd: '#ddd6fe' },
    NOT_STARTED: { label: 'Not Started', bg: '#f8fafc', fg: '#64748b', bd: '#e2e8f0' },
    PENDING: { label: 'Pending', bg: '#f8fafc', fg: '#64748b', bd: '#e2e8f0' },
  };

  // Teacher never locks: profile locked + row exists is enough.
  // Re-marking resets HOD to PENDING (backend), so the button always works.
  const canTeacherMark = (s) => {
    if (!canMarkTeacher || s.moved_up) return false;
    if (!s.eligibility_id || !s.profile_locked) return false;
    return true;
  };

  const canHodMark = (s) => {
    if (!canMarkHod || s.moved_up) return false;
    if (!s.eligibility_id || !s.profile_locked) return false;
    if (s.class_teacher_status === 'PENDING' || s.class_teacher_status === 'NOT_STARTED')
      return false;
    return true;
  };

  const handleMark = async (s, side, decision) => {
    const key = `${s.student_id}:${side}`;
    try {
      setMarkingKey(key);
      if (side === 'TEACHER') {
        await resultsApi.markTeacherSimple(s.eligibility_id, decision);
      } else {
        await resultsApi.markHodSimple(s.eligibility_id, decision);
      }
      showNotice(
        `${s.student_name} marked ${decision === 'APPROVED' ? 'Eligible' : 'Not Eligible'} (${side === 'TEACHER' ? 'Teacher' : 'HOD'}).`
      );
      setEditingId(null);
      if (selectedClass) await loadClassRoster(selectedClass.division_id);
      await loadClasses();
    } catch (err) {
      showNotice(err.response?.data?.detail || 'Failed to mark eligibility.', 6000);
    } finally {
      setMarkingKey(null);
    }
  };

  const filteredStudents = (rosterData?.students || []).filter((s) => {
    const q = (searchQuery || '').trim().toLowerCase();
    const match =
      !q ||
      (s.student_name || '').toLowerCase().includes(q) ||
      (s.enrollment_no && s.enrollment_no.toLowerCase().includes(q)) ||
      (s.roll_number && s.roll_number.toLowerCase().includes(q));
    if (!match) return false;
    const st = simpleStatus(s);
    if (statusFilter === 'ALL') return true;
    if (statusFilter === 'UNLOCKED') return st === 'PROFILE_UNLOCKED';
    if (statusFilter === 'TEACHER_PENDING') return st === 'TEACHER_PENDING';
    if (statusFilter === 'HOD_PENDING') return st === 'HOD_PENDING';
    if (statusFilter === 'ELIGIBLE') return st === 'ELIGIBLE';
    if (statusFilter === 'NOT_ELIGIBLE') return st === 'NOT_ELIGIBLE';
    return true;
  });

  // Bulk-ready: locked profile + teacher Eligible + HOD still pending.
  // Mirrors the backend bulk gate so the button count is exact.
  const bulkReadyCount = (rosterData?.students || []).filter(
    (s) =>
      !s.moved_up &&
      s.eligibility_id &&
      s.profile_locked &&
      s.class_teacher_status === 'APPROVED' &&
      s.hod_status === 'PENDING'
  ).length;

  const handleBulkApprove = async () => {
    if (!selectedClass || bulkApproving || bulkReadyCount === 0) return;
    if (
      !window.confirm(
        `Approve ALL ${bulkReadyCount} teacher-eligible student(s) in ${selectedClass.class_name}?\n\nOnly profile-locked + teacher-Eligible students are marked. Everything else is skipped. This unlocks them for the Candidate Ledger.`
      )
    )
      return;
    try {
      setBulkApproving(true);
      const res = await resultsApi.bulkMarkHodSimple(selectedClass.division_id);
      showNotice(
        res.data?.detail || `${res.data?.approved ?? bulkReadyCount} student(s) marked Eligible.`,
        6000
      );
      setEditingId(null);
      await loadClassRoster(selectedClass.division_id);
      await loadClasses();
    } catch (err) {
      showNotice(err.response?.data?.detail || 'Bulk approval failed.', 6000);
    } finally {
      setBulkApproving(false);
    }
  };

  const handlePromoteClass = async (e, cls) => {
    e.stopPropagation();
    try {
      setPromotingDivId(cls.division_id);
      const preview = await academicApi.promoteClass(cls.division_id, { dry_run: true });
      const data = preview.data || {};
      setPromoteTarget(cls);
      setPromotePreview(data);
      // Pre-select failed students for the repeater class (backend preselection),
      // falling back to the failed bucket when preselection is absent.
      const preselected =
        data.default_repeater?.preselected_student_ids ||
        data.buckets?.failed?.map((s) => s.id) ||
        [];
      setSelectedRepeaterStudents(preselected);
    } catch (err) {
      showNotice(err.response?.data?.detail || 'Failed to preview promotion.', 6000);
    } finally {
      setPromotingDivId(null);
    }
  };

  const handlePromoteConfirm = async () => {
    if (!promoteTarget || !promotePreview) return;
    const readyCount = promotePreview.ready_to_move_count ?? promotePreview.buckets?.ready_to_move?.length ?? 0;
    const willPromote = promotePreview.will_promote ?? readyCount;
    // Allow repeater-only promotion (ready == 0 but repeater students selected).
    if ((promotePreview.blocked || 0) > 0) return;
    if (readyCount === 0 && selectedRepeaterStudents.length === 0 && !willPromote) return;
    const cls = promoteTarget;
    try {
      setExecutingPromote(true);
      const res = await academicApi.promoteClass(cls.division_id, {
        repeater_student_ids: selectedRepeaterStudents,
      });
      showNotice(res.data?.detail || 'Class promoted.');
      setPromoteTarget(null);
      setPromotePreview(null);
      setSelectedRepeaterStudents([]);
      await loadClasses();
      if (selectedClass && selectedClass.division_id === cls.division_id) {
        await loadClassRoster(cls.division_id);
      }
    } catch (err) {
      showNotice(err.response?.data?.detail || 'Failed to promote class.', 6000);
    } finally {
      setExecutingPromote(false);
    }
  };

  const teacherDone = (rosterData?.students || []).filter(
    (s) => s.class_teacher_status === 'APPROVED'
  ).length;
  const hodDone = (rosterData?.students || []).filter((s) => s.hod_status === 'APPROVED').length;
  const eligibleCount = (rosterData?.students || []).filter((s) => s.final_eligible).length;
  const unlockedCount = (rosterData?.students || []).filter((s) => !s.profile_locked).length;

  // No top padding: the banner sits flush under the top bar (no white gap).
  return (
    <div style={{ maxWidth: '1400px', margin: '0 auto', padding: '0 1rem 1.5rem 1rem' }}>
      <PageHeader
        title="Mark Student Eligibility"
        subtitle="Profile-lock only (results paused). Teacher marks first, then HOD — both Eligible unlocks Candidate Ledger + admission form."
        actions={
          <button
            type="button"
            className="edvana-btn edvana-btn-secondary"
            onClick={() => {
              if (selectedClass) loadClassRoster(selectedClass.division_id);
              loadClasses();
            }}
            style={{ display: 'inline-flex', alignItems: 'center', gap: '0.4rem', fontSize: '0.85rem' }}
          >
            <RefreshCw size={14} className={loadingClasses || loadingRoster ? 'animate-spin' : ''} />
            <span>Refresh</span>
          </button>
        }
      />

      {notice && (
        <div
          className="animate-fade-in"
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

      {!selectedClass ? (
        <div style={{ marginTop: '1.25rem' }}>
          <h2 style={{ fontSize: '1.15rem', fontWeight: 700, color: '#0f172a', margin: '0 0 0.25rem 0' }}>
            Classes
          </h2>
          <p style={{ fontSize: '0.8125rem', color: '#64748b', margin: '0 0 1.25rem 0' }}>
            {isViewingAsTeacher
              ? 'Your assigned class. Start marking once verification is started.'
              : 'All department classes. Start verification on year-change classes (Sem 2, 4, 6), then open the class to mark.'}
          </p>

          {loadingClasses ? (
            <LoadingState message="Loading classes..." />
          ) : classesError ? (
            <ErrorState message={classesError} onRetry={loadClasses} />
          ) : classes.length === 0 ? (
            <EmptyState title="No Classes" description="No classes found in your scope." />
          ) : (
            <div className="stagger" style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
              {classes.map((cls) => {
                const isStarting = startingDivId === cls.division_id;
                return (
                  <div
                    key={cls.division_id}
                    onClick={() => handleSelectClass(cls)}
                    className="pressable"
                    style={{
                      backgroundColor: '#fff',
                      borderRadius: '18px',
                      border: '1.5px solid #e2e8f0',
                      padding: '1.25rem 1.5rem',
                      cursor: 'pointer',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      gap: '1.25rem',
                      flexWrap: 'wrap',
                    }}
                  >
                    <div style={{ flex: '1 1 260px' }}>
                      <div style={{ display: 'flex', gap: '0.45rem', marginBottom: '0.35rem', flexWrap: 'wrap' }}>
                        <span style={{ fontSize: '0.72rem', fontWeight: 700, background: '#f1f5f9', padding: '0.15rem 0.55rem', borderRadius: '6px', color: '#334155' }}>
                          {cls.department_code}
                        </span>
                        <span style={{ fontSize: '0.72rem', fontWeight: 600, background: '#f8fafc', border: '1px solid #e2e8f0', padding: '0.15rem 0.55rem', borderRadius: '6px', color: '#475569' }}>
                          Sem {cls.semester_number}
                          {cls.target_semester_number ? ` → Sem ${cls.target_semester_number}` : ''}
                        </span>
                        {cls.is_verification_started ? (
                          <span style={{ fontSize: '0.72rem', fontWeight: 700, background: '#f0fdf4', color: '#16a34a', border: '1px solid #bbf7d0', padding: '0.15rem 0.55rem', borderRadius: '6px' }}>
                            MARKING ACTIVE
                          </span>
                        ) : cls.is_year_change_class ? (
                          <span style={{ fontSize: '0.72rem', fontWeight: 700, background: '#eff6ff', color: '#2563eb', border: '1px solid #bfdbfe', padding: '0.15rem 0.55rem', borderRadius: '6px' }}>
                            READY TO START
                          </span>
                        ) : null}
                      </div>
                      <h3 style={{ fontSize: '1.1rem', fontWeight: 800, color: '#0f172a', margin: '0 0 0.25rem 0' }}>
                        {cls.class_name}
                      </h3>
                      <div style={{ fontSize: '0.8125rem', color: '#64748b' }}>
                        Teacher: <strong style={{ color: '#1e293b' }}>{cls.class_teacher_name}</strong>
                        {'  •  '}Eligible: <strong style={{ color: '#1e293b' }}>{cls.final_eligible_count}/{cls.total_students}</strong>
                      </div>
                    </div>
                    <div style={{ display: 'flex', gap: '0.6rem', alignItems: 'center', flexWrap: 'wrap' }}>
                      {(cls.has_class_teacher === false || cls.class_teacher_name === 'Unassigned') && (
                        <span style={{ fontSize: '0.78rem', fontWeight: 700, background: '#fffbeb', color: '#b45309', border: '1px solid #fde68a', padding: '0.55rem 0.9rem', borderRadius: '10px' }}>
                          Assign teacher first
                        </span>
                      )}
                      {cls.can_start_verification && !cls.is_verification_started && (
                        <button
                          type="button"
                          onClick={(e) => handleStartVerification(e, cls)}
                          disabled={isStarting}
                          className="edvana-btn"
                          style={{ display: 'inline-flex', alignItems: 'center', gap: '0.45rem', padding: '0.55rem 1rem', borderRadius: '10px', fontSize: '0.85rem', fontWeight: 700, backgroundColor: '#2563eb', color: '#fff', border: 'none', cursor: isStarting ? 'not-allowed' : 'pointer' }}
                        >
                          {isStarting ? <RefreshCw size={14} className="animate-spin" /> : <Play size={14} />}
                          <span>{isStarting ? 'Starting...' : 'Start Verification'}</span>
                        </button>
                      )}
                      {/* Promote Class Button */}
                      {cls.can_promote_class && cls.is_verification_started && (
                        <button
                          type="button"
                          onClick={(e) => handlePromoteClass(e, cls)}
                          disabled={promotingDivId === cls.division_id}
                          className="edvana-btn"
                          style={{
                            display: 'inline-flex',
                            alignItems: 'center',
                            gap: '0.45rem',
                            padding: '0.55rem 1rem',
                            borderRadius: '10px',
                            fontSize: '0.85rem',
                            fontWeight: 700,
                            backgroundColor: '#16a34a',
                            color: '#ffffff',
                            border: 'none',
                            boxShadow: '0 2px 6px rgba(22,163,74,0.25)',
                            cursor: promotingDivId === cls.division_id ? 'not-allowed' : 'pointer',
                            transition: 'all 0.15s ease',
                          }}
                        >
                          {promotingDivId === cls.division_id ? (
                            <RefreshCw size={14} className="animate-spin" />
                          ) : (
                            <GraduationCap size={14} />
                          )}
                          <span>
                            {promotingDivId === cls.division_id ? 'Promoting...' : `Promote to Sem ${cls.target_semester_number}`}
                          </span>
                        </button>
                      )}
                      <button
                        type="button"
                        onClick={() => handleSelectClass(cls)}
                        className="edvana-btn edvana-btn-secondary"
                        style={{ display: 'inline-flex', alignItems: 'center', gap: '0.4rem', padding: '0.55rem 0.95rem', fontSize: '0.85rem', fontWeight: 600, borderRadius: '10px' }}
                      >
                        <span>Open Students</span>
                        <ChevronRight size={15} />
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      ) : (
        <div style={{ marginTop: '1.25rem' }}>
          <div className="edvana-card animate-fade-in" style={{ background: '#fff', borderRadius: '18px', border: '1.5px solid #e2e8f0', padding: '1.25rem 1.5rem', marginBottom: '1.25rem' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '0.75rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                <button
                  type="button"
                  onClick={() => setSelectedClass(null)}
                  className="edvana-btn edvana-btn-secondary"
                  style={{ display: 'inline-flex', alignItems: 'center', gap: '0.4rem', padding: '0.45rem 0.85rem', fontSize: '0.85rem', fontWeight: 600, borderRadius: '10px' }}
                >
                  <ArrowLeft size={16} />
                  <span>Back</span>
                </button>
                <div>
                  <h2 style={{ fontSize: '1.2rem', fontWeight: 800, color: '#0f172a', margin: 0 }}>
                    {selectedClass.class_name}
                  </h2>
                  <div style={{ fontSize: '0.8rem', color: '#64748b' }}>
                    Teacher: <strong>{selectedClass.class_teacher_name}</strong>
                  </div>
                </div>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', flexWrap: 'wrap' }}>
                {actingSide === 'HOD' && canMarkHod && bulkReadyCount > 0 && (
                  <button
                    type="button"
                    onClick={handleBulkApprove}
                    disabled={bulkApproving || loadingRoster}
                    title={`One click: mark Eligible all ${bulkReadyCount} teacher-approved, profile-locked student(s). Skips everything else.`}
                    className="animate-scale-in"
                    style={{
                      display: 'inline-flex', alignItems: 'center', gap: '0.45rem',
                      padding: '0.55rem 1.05rem', borderRadius: '10px',
                      fontSize: '0.85rem', fontWeight: 700,
                      backgroundColor: '#7c3aed', color: '#fff', border: 'none',
                      boxShadow: '0 2px 6px rgba(124,58,237,0.3)',
                      cursor: bulkApproving || loadingRoster ? 'not-allowed' : 'pointer',
                      opacity: bulkApproving || loadingRoster ? 0.65 : 1,
                    }}
                  >
                    {bulkApproving ? <RefreshCw size={14} className="animate-spin" /> : <ShieldCheck size={14} />}
                    <span>{bulkApproving ? 'Approving...' : `Approve All Eligible (${bulkReadyCount})`}</span>
                  </button>
                )}
                {selectedClass.is_verification_started || (rosterData?.students || []).some((s) => s.eligibility_id) ? (
                  <span style={{ fontSize: '0.78rem', fontWeight: 700, background: '#f0fdf4', color: '#16a34a', border: '1px solid #bbf7d0', padding: '0.35rem 0.85rem', borderRadius: '9999px', display: 'inline-flex', alignItems: 'center', gap: '0.35rem' }}>
                    <CheckCircle2 size={14} /> Marking Active
                  </span>
                ) : selectedClass.can_start_verification ? (
                  <button
                    type="button"
                    onClick={(e) => handleStartVerification(e, selectedClass)}
                    disabled={startingDivId === selectedClass.division_id}
                    className="edvana-btn edvana-btn-primary"
                    style={{ display: 'inline-flex', alignItems: 'center', gap: '0.4rem', fontSize: '0.85rem', fontWeight: 600, borderRadius: '10px', padding: '0.5rem 1rem' }}
                  >
                    <Play size={14} />
                    <span>Start Verification</span>
                  </button>
                ) : null}
              </div>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: '0.6rem', marginTop: '1rem' }}>
              {[
                { label: 'Total', value: rosterData?.total_students ?? 0 },
                { label: 'Profile Not Locked', value: unlockedCount },
                { label: 'Teacher Marked', value: teacherDone },
                { label: 'HOD Marked', value: hodDone },
                { label: 'Eligible (Ledger)', value: eligibleCount },
              ].map((s, i) => (
                <div key={i} style={{ background: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: '12px', padding: '0.6rem 0.9rem' }}>
                  <div style={{ fontSize: '0.72rem', fontWeight: 600, color: '#64748b' }}>{s.label}</div>
                  <div style={{ fontSize: '1.3rem', fontWeight: 800, color: '#0f172a' }}>{s.value}</div>
                </div>
              ))}
            </div>
          </div>

          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '1rem', marginBottom: '1rem' }}>
            <div style={{ position: 'relative', width: '300px', maxWidth: '100%' }}>
              <Search size={16} style={{ position: 'absolute', left: '0.75rem', top: '50%', transform: 'translateY(-50%)', color: '#94a3b8' }} />
              <input
                type="text"
                placeholder="Search name or PRN..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="edvana-input"
                style={{ paddingLeft: '2.25rem', width: '100%', fontSize: '0.85rem', borderRadius: '10px' }}
              />
            </div>
            <div style={{ display: 'flex', gap: '0.4rem', flexWrap: 'wrap' }}>
              {[
                { id: 'ALL', label: 'All' },
                { id: 'UNLOCKED', label: 'Profile Not Locked' },
                { id: 'TEACHER_PENDING', label: 'Needs Teacher' },
                { id: 'HOD_PENDING', label: 'Needs HOD' },
                { id: 'ELIGIBLE', label: 'Eligible' },
                { id: 'NOT_ELIGIBLE', label: 'Not Eligible' },
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
                    backgroundColor: statusFilter === f.id ? '#0f172a' : '#fff',
                    color: statusFilter === f.id ? '#fff' : '#475569',
                    border: '1px solid',
                    borderColor: statusFilter === f.id ? '#0f172a' : '#cbd5e1',
                    cursor: 'pointer',
                  }}
                >
                  {f.label}
                </button>
              ))}
            </div>
          </div>

          {loadingRoster ? (
            <LoadingState message="Loading students..." />
          ) : rosterError ? (
            <ErrorState message={rosterError} onRetry={() => loadClassRoster(selectedClass.division_id)} />
          ) : filteredStudents.length === 0 ? (
            <EmptyState title="No Students" description="No students match the current filter." />
          ) : (
            <div className="edvana-card animate-fade-in" style={{ borderRadius: '18px', border: '1.5px solid #e2e8f0', overflow: 'hidden' }}>
              <div style={{ overflowX: 'auto' }}>
                <table className="edvana-table" style={{ margin: 0, width: '100%', minWidth: '860px' }}>
                  <thead>
                    <tr>
                      <th style={{ width: 60, textAlign: 'center' }}>Roll</th>
                      <th>Student</th>
                      <th style={{ textAlign: 'center' }}>Status</th>
                      <th style={{ textAlign: 'center' }}>Teacher</th>
                      <th style={{ textAlign: 'center' }}>HOD</th>
                      <th style={{ textAlign: 'center', width: 220 }}>Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredStudents.map((s) => {
                      const st = simpleStatus(s);
                      const meta = statusMeta[st] || statusMeta.PENDING;
                      const tMarking = markingKey === `${s.student_id}:TEACHER`;
                      const hMarking = markingKey === `${s.student_id}:HOD`;
                      const marking = tMarking || hMarking;
                      const tOk = canTeacherMark(s);
                      const hOk = canHodMark(s);
                      const myOk = actingSide === 'TEACHER' ? tOk : hOk;
                      // My decided state on this side (drives the collapsed pill + pen).
                      const myStatus = actingSide === 'TEACHER' ? s.class_teacher_status : s.hod_status;
                      const iDecided = myStatus === 'APPROVED' || myStatus === 'REJECTED';
                      const iEligible = actingSide === 'TEACHER'
                        ? s.class_teacher_status === 'APPROVED'
                        : s.final_eligible;
                      const isEditing = editingId === s.student_id;
                      const blockedReason = !s.profile_locked
                        ? 'Profile not locked — ask student to lock profile'
                        : !s.eligibility_id
                          ? 'Start verification first'
                          : actingSide === 'HOD' && (s.class_teacher_status === 'PENDING' || s.class_teacher_status === 'NOT_STARTED')
                            ? 'Teacher must mark first'
                            : null;
                      return (
                        <tr key={s.student_id}>
                          <td style={{ textAlign: 'center', fontWeight: 700, color: '#334155' }}>{s.roll_number}</td>
                          <td>
                            <div style={{ fontWeight: 700, color: '#0f172a', fontSize: '0.875rem' }}>{s.student_name}</div>
                            <div style={{ fontSize: '0.75rem', color: '#64748b' }}>PRN: {s.enrollment_no || '—'}</div>
                            {!s.profile_locked && (
                              <div style={{ fontSize: '0.72rem', color: '#b45309', fontWeight: 600 }}>
                                Ask student to lock profile (teacher notice)
                              </div>
                            )}
                            {!s.eligibility_id && s.profile_locked && (
                              <div style={{ fontSize: '0.72rem', color: '#64748b' }}>
                                No marking row yet — press Start Verification. FY/DSE freshers may already be auto-eligible on ledger.
                              </div>
                            )}
                          </td>
                          <td style={{ textAlign: 'center' }}>
                            <span style={{ display: 'inline-block', fontSize: '0.75rem', fontWeight: 700, padding: '0.25rem 0.7rem', borderRadius: '9999px', backgroundColor: meta.bg, color: meta.fg, border: `1px solid ${meta.bd}` }}>
                              {meta.label}
                            </span>
                          </td>
                          <td style={{ textAlign: 'center', fontSize: '0.78rem', fontWeight: 600, color: '#334155' }}>
                            {s.class_teacher_status || '—'}
                          </td>
                          <td style={{ textAlign: 'center', fontSize: '0.78rem', fontWeight: 600, color: '#334155' }}>
                            {s.hod_status || '—'}
                          </td>
                          <td style={{ textAlign: 'center' }}>
                            {myOk && iDecided && !isEditing ? (
                              // Decided: single pill + pen. No accidental re-taps.
                              <div style={{ display: 'inline-flex', alignItems: 'center', gap: '0.45rem', justifyContent: 'center' }}>
                                <span
                                  style={{
                                    display: 'inline-flex', alignItems: 'center', gap: '0.35rem',
                                    fontSize: '0.78rem', fontWeight: 700,
                                    padding: '0.45rem 0.9rem', borderRadius: '8px',
                                    backgroundColor: iEligible ? '#16a34a' : '#dc2626',
                                    color: '#fff',
                                    border: `1px solid ${iEligible ? '#16a34a' : '#dc2626'}`,
                                  }}
                                >
                                  {iEligible ? <ShieldCheck size={13} /> : <XCircle size={13} />}
                                  {iEligible ? 'Eligible' : 'Not Eligible'}
                                </span>
                                <button
                                  type="button"
                                  onClick={() => setEditingId(s.student_id)}
                                  title="Edit marking"
                                  aria-label={`Edit marking for ${s.student_name}`}
                                  style={{
                                    display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                                    width: '30px', height: '30px', borderRadius: '8px',
                                    backgroundColor: '#fff', color: '#475569',
                                    border: '1px solid #cbd5e1', cursor: 'pointer',
                                  }}
                                >
                                  <Pencil size={14} />
                                </button>
                              </div>
                            ) : (
                              <div style={{ display: 'flex', gap: '0.35rem', justifyContent: 'center', flexWrap: 'wrap', alignItems: 'center' }}>
                                <button
                                  type="button"
                                  disabled={!myOk || marking}
                                  onClick={() => handleMark(s, actingSide, 'APPROVED')}
                                  title={blockedReason || 'Mark Eligible'}
                                  style={{
                                    display: 'inline-flex', alignItems: 'center', gap: '0.3rem',
                                    padding: '0.45rem 0.9rem', borderRadius: '8px', fontSize: '0.78rem', fontWeight: 700,
                                    backgroundColor: '#f0fdf4', color: '#15803d',
                                    border: '1px solid #bbf7d0',
                                    cursor: !myOk || marking ? 'not-allowed' : 'pointer',
                                    opacity: !myOk ? 0.55 : 1,
                                  }}
                                >
                                  <ShieldCheck size={13} /> {marking ? '...' : 'Eligible'}
                                </button>
                                <button
                                  type="button"
                                  disabled={!myOk || marking}
                                  onClick={() => handleMark(s, actingSide, 'REJECTED')}
                                  title={blockedReason || 'Mark Not Eligible'}
                                  style={{
                                    display: 'inline-flex', alignItems: 'center', gap: '0.3rem',
                                    padding: '0.45rem 0.9rem', borderRadius: '8px', fontSize: '0.78rem', fontWeight: 700,
                                    backgroundColor: '#fef2f2', color: '#b91c1c',
                                    border: '1px solid #fecaca',
                                    cursor: !myOk || marking ? 'not-allowed' : 'pointer',
                                    opacity: !myOk ? 0.55 : 1,
                                  }}
                                >
                                  <XCircle size={13} /> {marking ? '...' : 'Not Eligible'}
                                </button>
                                {isEditing && (
                                  <button
                                    type="button"
                                    onClick={() => setEditingId(null)}
                                    title="Done editing"
                                    aria-label="Done editing"
                                    style={{
                                      display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                                      width: '30px', height: '30px', borderRadius: '8px',
                                      backgroundColor: '#0f172a', color: '#fff',
                                      border: '1px solid #0f172a', cursor: 'pointer',
                                    }}
                                  >
                                    <X size={14} />
                                  </button>
                                )}
                              </div>
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Promote Class confirmation */}
      <Modal
        isOpen={Boolean(promoteTarget && promotePreview)}
        onClose={() => {
          if (!executingPromote) {
            setPromoteTarget(null);
            setPromotePreview(null);
            setSelectedRepeaterStudents([]);
          }
        }}
        title={`Promote class to Sem ${(promotePreview?.target_semester || promotePreview?.to_semester) ?? ''}`}
        maxWidth="680px"
        footer={
          <>
            <button
              type="button"
              className="edvana-btn edvana-btn-secondary"
              disabled={executingPromote}
              onClick={() => {
                setPromoteTarget(null);
                setPromotePreview(null);
                setSelectedRepeaterStudents([]);
              }}
              style={{ padding: '0.55rem 1rem', borderRadius: '10px', fontWeight: 600 }}
            >
              Cancel
            </button>
            <button
              type="button"
              className="edvana-btn"
              disabled={
                executingPromote ||
                (promotePreview?.blocked || 0) > 0 ||
                ((promotePreview?.ready_to_move_count || 0) === 0 && selectedRepeaterStudents.length === 0 && !promotePreview?.will_promote)
              }
              onClick={handlePromoteConfirm}
              style={{
                padding: '0.55rem 1.1rem',
                borderRadius: '10px',
                fontWeight: 700,
                backgroundColor: '#16a34a',
                color: '#ffffff',
                border: 'none',
                cursor: (executingPromote || (promotePreview?.blocked || 0) > 0 || ((promotePreview?.ready_to_move_count || 0) === 0 && selectedRepeaterStudents.length === 0 && !promotePreview?.will_promote)) ? 'not-allowed' : 'pointer',
                opacity: (promotePreview?.blocked || 0) > 0 || ((promotePreview?.ready_to_move_count || 0) === 0 && selectedRepeaterStudents.length === 0 && !promotePreview?.will_promote) ? 0.55 : 1,
              }}
            >
              {executingPromote
                ? 'Processing...'
                : (promotePreview?.blocked || 0) > 0
                ? `Blocked (${promotePreview.blocked} pending decision)`
                : selectedRepeaterStudents.length > 0 && (promotePreview?.ready_to_move_count || 0) > 0
                ? `Promote (${promotePreview.ready_to_move_count}) & Repeat (${selectedRepeaterStudents.length})`
                : selectedRepeaterStudents.length > 0
                ? `Move to Repeater (${selectedRepeaterStudents.length}) & Flip`
                : `Promote (${promotePreview?.ready_to_move_count || (promotePreview?.will_promote ? 'Class' : 0)})`}
            </button>
          </>
        }
      >
        {promotePreview && (() => {
          const readyCount = promotePreview.ready_to_move_count ?? (promotePreview.buckets?.ready_to_move?.length || 0);
          const alreadyCount = promotePreview.already_promoted_count ?? (promotePreview.buckets?.already_promoted?.length || 0);
          const unpaidCount = promotePreview.fees_pending_count ?? (promotePreview.buckets?.fees_pending?.length || 0);
          const failedCount = promotePreview.failed_count ?? (promotePreview.buckets?.failed?.length || 0);
          const blockedCount = promotePreview.blocked ?? (promotePreview.buckets?.blocked?.length || 0);
          const targetSem = promotePreview.target_semester || promotePreview.to_semester;
          const fromSem = promotePreview.from_semester;

          const failedList = promotePreview.buckets?.failed || [];
          const unpaidList = promotePreview.buckets?.fees_pending || [];
          const repeaterCandidates = [...failedList, ...unpaidList];

          const activeBefore =
            promotePreview.total_students != null
              ? promotePreview.total_students - alreadyCount
              : readyCount + unpaidCount + failedCount + blockedCount;
          // Active = ready + unpaid + failed + blocked (already-promoted are a separate cohort).
          // Remaining = those not promoted and not moved to repeater.
          const remainingActive = activeBefore - readyCount - (selectedRepeaterStudents?.length || 0);
          const willFlip = remainingActive === 0 && blockedCount === 0;

          const toggleRepeaterStudent = (id) => {
            setSelectedRepeaterStudents((prev) =>
              prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]
            );
          };

          return (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
              {/* 5 Distinct Bucket Stat Cards */}
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(110px, 1fr))', gap: '0.5rem' }}>
                <div style={{ backgroundColor: '#f0fdf4', border: '1px solid #bbf7d0', borderRadius: '10px', padding: '0.65rem 0.5rem', textAlign: 'center' }}>
                  <div style={{ fontSize: '1.35rem', fontWeight: 800, color: '#15803d' }}>{readyCount}</div>
                  <div style={{ fontSize: '0.72rem', fontWeight: 600, color: '#166534' }}>Ready to move</div>
                </div>
                <div style={{ backgroundColor: '#eff6ff', border: '1px solid #bfdbfe', borderRadius: '10px', padding: '0.65rem 0.5rem', textAlign: 'center' }}>
                  <div style={{ fontSize: '1.35rem', fontWeight: 800, color: '#1d4ed8' }}>{alreadyCount}</div>
                  <div style={{ fontSize: '0.72rem', fontWeight: 600, color: '#1e40af' }}>Already in Sem {targetSem}</div>
                </div>
                <div style={{ backgroundColor: '#fffbeb', border: '1px solid #fde68a', borderRadius: '10px', padding: '0.65rem 0.5rem', textAlign: 'center' }}>
                  <div style={{ fontSize: '1.35rem', fontWeight: 800, color: '#b45309' }}>{unpaidCount}</div>
                  <div style={{ fontSize: '0.72rem', fontWeight: 600, color: '#92400e' }}>Fees pending</div>
                </div>
                <div style={{ backgroundColor: '#fff1f2', border: '1px solid #fecdd3', borderRadius: '10px', padding: '0.65rem 0.5rem', textAlign: 'center' }}>
                  <div style={{ fontSize: '1.35rem', fontWeight: 800, color: '#e11d48' }}>{failedCount}</div>
                  <div style={{ fontSize: '0.72rem', fontWeight: 600, color: '#9f1239' }}>Failed</div>
                </div>
                <div style={{ backgroundColor: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: '10px', padding: '0.65rem 0.5rem', textAlign: 'center' }}>
                  <div style={{ fontSize: '1.35rem', fontWeight: 800, color: '#475569' }}>{blockedCount}</div>
                  <div style={{ fontSize: '0.72rem', fontWeight: 600, color: '#334155' }}>Blocked</div>
                </div>
              </div>

              {/* Class Flip Rule Status Banner */}
              {willFlip ? (
                <div style={{ backgroundColor: '#f0fdf4', border: '1px solid #86efac', borderRadius: '10px', padding: '0.75rem 1rem', fontSize: '0.82rem', color: '#166534' }}>
                  <div style={{ fontWeight: 800, marginBottom: '0.2rem', display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                    <Check size={16} /> Strict 0-Active Student Flip Met
                  </div>
                  <div>
                    All active Sem {fromSem} students will move to Sem {targetSem} or to the repeater class (Div R).
                    This class will flip to <strong>Sem {targetSem}</strong> in-place!
                  </div>
                </div>
              ) : (
                <div style={{ backgroundColor: '#fef2f2', border: '1px solid #fecaca', borderRadius: '10px', padding: '0.75rem 1rem', fontSize: '0.82rem', color: '#991b1b' }}>
                  <div style={{ fontWeight: 800, marginBottom: '0.2rem' }}>
                    Note: {remainingActive} student(s) will remain active in Sem {fromSem}.
                  </div>
                  <div>
                    In accordance with college rules, the class remains in Sem {fromSem} until all active students either promote or move to a repeater class.
                  </div>
                </div>
              )}

              {/* Repeater Class Creation Section */}
              {repeaterCandidates.length > 0 && (
                <div style={{ backgroundColor: '#f8fafc', border: '1.5px solid #cbd5e1', borderRadius: '12px', padding: '1rem' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
                    <div>
                      <div style={{ fontSize: '0.9rem', fontWeight: 800, color: '#0f172a' }}>
                        Create Repeater Class
                      </div>
                      <div style={{ fontSize: '0.78rem', color: '#64748b' }}>
                        Sem {fromSem} · Div {promotePreview.default_repeater?.division_name || 'R'}
                        {promotePreview.default_repeater?.class_teacher_name ? ` · Teacher: ${promotePreview.default_repeater.class_teacher_name}` : ''}
                      </div>
                    </div>
                    <div style={{ fontSize: '0.75rem', fontWeight: 700, color: '#0369a1', backgroundColor: '#e0f2fe', padding: '0.2rem 0.6rem', borderRadius: '6px' }}>
                      {selectedRepeaterStudents.length} selected for Repeater
                    </div>
                  </div>
                  <div style={{ fontSize: '0.78rem', color: '#475569', marginBottom: '0.75rem' }}>
                    Move failed and unpaid students into the repeater division so they don't block the class transition.
                    Failed students are pre-selected; unpaid students can optionally be moved.
                  </div>

                  <div style={{ maxHeight: '180px', overflowY: 'auto', border: '1px solid #e2e8f0', borderRadius: '8px', backgroundColor: '#ffffff' }}>
                    {repeaterCandidates.map((s) => {
                      const isFailed = failedList.some((f) => f.id === s.id);
                      const isChecked = selectedRepeaterStudents.includes(s.id);
                      return (
                        <label
                          key={s.id}
                          style={{
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'space-between',
                            gap: '0.75rem',
                            padding: '0.5rem 0.85rem',
                            borderBottom: '1px solid #f1f5f9',
                            fontSize: '0.8rem',
                            cursor: 'pointer',
                            backgroundColor: isChecked ? '#f8fafc' : '#ffffff',
                          }}
                        >
                          <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
                            <input
                              type="checkbox"
                              checked={isChecked}
                              onChange={() => toggleRepeaterStudent(s.id)}
                              style={{ cursor: 'pointer' }}
                            />
                            <span style={{ fontWeight: 600, color: '#0f172a' }}>{s.name}</span>
                            <span style={{ fontSize: '0.75rem', color: '#64748b' }}>
                              ({s.enrollment_no || s.roll_number || 'No ID'})
                            </span>
                          </div>
                          <span
                            style={{
                              fontSize: '0.72rem',
                              fontWeight: 700,
                              padding: '0.1rem 0.45rem',
                              borderRadius: '4px',
                              backgroundColor: isFailed ? '#ffe4e6' : '#fef3c7',
                              color: isFailed ? '#be123c' : '#92400e',
                            }}
                          >
                            {isFailed ? 'Failed' : 'Eligible, Unpaid'}
                          </span>
                        </label>
                      );
                    })}
                  </div>
                </div>
              )}

              {/* Blocked students alert */}
              {blockedCount > 0 && (
                <div>
                  <div style={{ backgroundColor: '#fef2f2', border: '1.5px solid #f87171', borderRadius: '10px', padding: '0.75rem 1rem', fontSize: '0.82rem', color: '#991b1b' }}>
                    <div style={{ fontWeight: 800, marginBottom: '0.35rem' }}>
                      Blocked: Verification undecided for {blockedCount} student(s).
                    </div>
                    <div style={{ fontWeight: 500 }}>
                      Every student must be either eligible or failed before the class can move. Complete teacher approval or HOD endorsement first.
                    </div>
                  </div>
                  <div style={{ maxHeight: '140px', overflowY: 'auto', border: '1px solid #e2e8f0', borderRadius: '8px', marginTop: '0.5rem' }}>
                    {(promotePreview.buckets?.blocked || promotePreview.blocked_students || []).map((s) => (
                      <div key={s.id} style={{ display: 'flex', justifyContent: 'space-between', gap: '0.75rem', padding: '0.45rem 0.8rem', borderBottom: '1px solid #f1f5f9', fontSize: '0.78rem' }}>
                        <span style={{ fontWeight: 600, color: '#0f172a' }}>{s.name}</span>
                        <span style={{ color: '#b91c1c', textAlign: 'right' }}>{s.reason || 'Verification incomplete'}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          );
        })()}
      </Modal>
    </div>
  );
}
