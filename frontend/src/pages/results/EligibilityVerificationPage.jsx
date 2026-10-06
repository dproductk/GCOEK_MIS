import { useState, useEffect } from 'react';
import { useAuth } from '../../context/AuthContext';
import resultsApi from '../../api/resultsApi';
import PageHeader from '../../components/common/PageHeader';
import DataTable from '../../components/common/DataTable';
import Badge from '../../components/common/Badge';
import Modal from '../../components/common/Modal';
import FormField from '../../components/common/FormField';
import { LoadingState, ErrorState, EmptyState } from '../../components/common/StateDisplays';
import {
  ClipboardCheck,
  CheckCircle2,
  AlertCircle,
  Clock,
  Filter,
  RefreshCw,
  Eye,
  ShieldCheck,
  Award,
  Lock,
  RotateCcw,
  Flag,
  Check,
  FileText,
  BookOpen,
  X,
} from 'lucide-react';

export default function EligibilityVerificationPage() {
  const { user, activeRole, hasRole } = useAuth();
  const isViewingAsTeacher = activeRole?.codename === 'CLASS_TEACHER';
  const isViewingAsHOD = activeRole?.codename === 'HOD';

  // Strict separation: If currently switched to Class Teacher role, user can only do Teacher Review
  const canEndorseHOD = !isViewingAsTeacher && (isViewingAsHOD || hasRole('HOD') || hasRole('ADMIN_HEAD') || user?.is_superuser);
  const canReviewTeacher = isViewingAsTeacher || hasRole('CLASS_TEACHER') || hasRole('ADMIN_HEAD') || user?.is_superuser;

  const [records, setRecords] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [initializing, setInitializing] = useState(false);
  const [notice, setNotice] = useState(null);
  const [gradList, setGradList] = useState([]);
  const [confirmingGradId, setConfirmingGradId] = useState(null);

  // Review modal state
  const [selectedRecord, setSelectedRecord] = useState(null);
  const [modalResults, setModalResults] = useState([]);
  const [loadingResults, setLoadingResults] = useState(false);
  const [actionType, setActionType] = useState('TEACHER_REVIEW'); // 'TEACHER_REVIEW' | 'HOD_ENDORSE'
  const [reviewMode, setReviewMode] = useState(null); // null | 'APPROVE' | 'FLAG'
  const [decision, setDecision] = useState('APPROVED');
  const [remarks, setRemarks] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [actionError, setActionError] = useState(null);

  useEffect(() => {
    loadEligibilityRecords();
    if (canEndorseHOD) {
      resultsApi.getGraduationPending()
        .then((res) => setGradList(res.data?.results || res.data || []))
        .catch(() => setGradList([]));
    }
  }, []);

  // Fetch or populate student's detailed marksheets when review modal opens
  useEffect(() => {
    if (selectedRecord) {
      setReviewMode(null);
      setActionError(null);
      setRemarks('');
      if (selectedRecord.semester_results && selectedRecord.semester_results.length > 0) {
        setModalResults(selectedRecord.semester_results);
      } else {
        setLoadingResults(true);
        resultsApi.getSemesterResults({ student_id: selectedRecord.student_id })
          .then((res) => {
            const list = res.data?.results || res.data || [];
            setModalResults(list);
          })
          .catch(() => setModalResults([]))
          .finally(() => setLoadingResults(false));
      }
    } else {
      setModalResults([]);
      setReviewMode(null);
    }
  }, [selectedRecord]);

  const loadEligibilityRecords = async () => {
    try {
      setLoading(true);
      setError(null);
      const res = await resultsApi.getEligibilities();
      setRecords(res.data.results || res.data || []);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to load eligibility workflow records.');
    } finally {
      setLoading(false);
    }
  };

  const handleInitialize = async () => {
    if (!window.confirm(
      'Load your class/department students into the verification queue?\n\n' +
      'Creates pending eligibility rows (system-calculated from current backlogs). ' +
      'Already-queued students are skipped.'
    )) {
      return;
    }
    try {
      setInitializing(true);
      setError(null);
      const res = await resultsApi.initializeEligibility();
      setNotice(res.data?.detail || 'Verification queue ready.');
      setTimeout(() => setNotice(null), 5000);
      loadEligibilityRecords();
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to initialize verifications.');
    } finally {
      setInitializing(false);
    }
  };

  const handleConfirmGraduation = async (row) => {
    if (!window.confirm(`Confirm graduation of ${row.student_name || 'this student'} after Sem 8 PASS?`)) return;
    try {
      setConfirmingGradId(row.id);
      const res = await resultsApi.confirmGraduation(row.id);
      setNotice(res.data?.detail || 'Graduation confirmed.');
      setTimeout(() => setNotice(null), 5000);
      const refreshed = await resultsApi.getGraduationPending();
      setGradList(refreshed.data?.results || refreshed.data || []);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to confirm graduation.');
    } finally {
      setConfirmingGradId(null);
    }
  };

  const handleReviewSubmit = async (targetDecision, targetRemarks) => {
    if (!selectedRecord) return;
    const finalDecision = targetDecision || decision;
    const finalRemarks = targetRemarks !== undefined ? targetRemarks : remarks;

    if (finalDecision === 'FLAGGED' && !finalRemarks.trim()) {
      setActionError('Please specify the reason for flagging so the student can correct their marks.');
      return;
    }

    try {
      setSubmitting(true);
      setActionError(null);

      // Submit strictly based on the action button clicked (HOD Endorse vs Teacher Review)
      if (actionType === 'HOD_ENDORSE') {
        await resultsApi.endorseHOD(selectedRecord.id, finalDecision, finalRemarks);
      } else {
        await resultsApi.reviewClassTeacher(selectedRecord.id, finalDecision, finalRemarks);
      }
      setSelectedRecord(null);
      setReviewMode(null);
      setRemarks('');
      loadEligibilityRecords();
    } catch (err) {
      const resData = err.response?.data;
      let msg = 'Failed to submit review.';
      if (typeof resData?.detail === 'string') {
        msg = resData.detail;
      } else if (Array.isArray(resData?.detail)) {
        msg = resData.detail.map(d => typeof d === 'string' ? d : (d.string || JSON.stringify(d))).join(' ');
      } else if (Array.isArray(resData)) {
        msg = resData.map(d => typeof d === 'string' ? d : (d.string || JSON.stringify(d))).join(' ');
      } else if (resData && typeof resData === 'object') {
        msg = Object.values(resData).flat().map(d => typeof d === 'string' ? d : (d.string || JSON.stringify(d))).join(' ');
      }
      setActionError(msg);
    } finally {
      setSubmitting(false);
    }
  };

  const getStatusBadgeVariant = (status) => {
    switch (status) {
      case 'APPROVED':
      case 'ELIGIBLE':
        return 'success';
      case 'FLAGGED':
      case 'PROVISIONAL':
        return 'warning';
      case 'REJECTED':
      case 'INELIGIBLE':
        return 'danger';
      default:
        return 'neutral';
    }
  };

  const columns = [
    {
      header: 'Candidate Name',
      render: (r) => (
        <div>
          <div style={{ fontWeight: 600, color: '#0f172a' }}>{r.student_name}</div>
          <div style={{ fontSize: '0.75rem', color: '#64748b' }}>Dept: {r.department_code}</div>
        </div>
      ),
    },
    {
      header: 'Enrollment No',
      accessor: 'enrollment_no',
      render: (r) => <span style={{ fontFamily: 'monospace', fontWeight: 600 }}>{r.enrollment_no}</span>,
    },
    {
      header: 'Target Sem',
      render: (r) => <span style={{ fontWeight: 500 }}>Semester {r.target_semester_number}</span>,
    },
    {
      header: 'Backlogs',
      render: (r) => (
        <span style={{ fontFamily: 'monospace', fontWeight: 700, color: r.active_backlog_count === 0 ? '#15803d' : '#b91c1c' }}>
          {r.active_backlog_count}
        </span>
      ),
    },
    {
      header: 'System Calculated',
      render: (r) => (
        <Badge variant={getStatusBadgeVariant(r.calculated_status)}>
          {r.calculated_status_display}
        </Badge>
      ),
    },
    {
      header: 'Class Teacher',
      render: (r) => (
        <Badge variant={getStatusBadgeVariant(r.class_teacher_status)}>
          {r.class_teacher_status_display}
        </Badge>
      ),
    },
    {
      header: 'HOD Endorsement',
      render: (r) => (
        <Badge variant={getStatusBadgeVariant(r.hod_status)}>
          {r.hod_status_display}
        </Badge>
      ),
    },
    {
      header: 'Action',
      align: 'right',
      render: (r) => {
        if (r.final_eligible) {
          return (
            <span
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '0.3rem',
                color: '#15803d',
                fontSize: '0.78rem',
                fontWeight: 600,
                background: '#f0fdf4',
                padding: '0.35rem 0.65rem',
                borderRadius: '6px',
                border: '1px solid #bbf7d0',
              }}
            >
              <CheckCircle2 size={12} /> HOD Endorsed (Eligible)
            </span>
          );
        }

        // HOD flagged/returned the candidate back to Class Teacher
        if (r.hod_status === 'FLAGGED') {
          // If viewing as HOD: HOD already returned it, awaiting Teacher to re-evaluate
          if (canEndorseHOD) {
            return (
              <span
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '0.3rem',
                  color: '#b45309',
                  fontSize: '0.78rem',
                  fontWeight: 600,
                  background: '#fffbeb',
                  padding: '0.35rem 0.65rem',
                  borderRadius: '6px',
                  border: '1px solid #fde68a',
                }}
                title={`Flagged by HOD: ${r.hod_remarks || 'Returned to teacher for re-evaluation'}`}
              >
                <RotateCcw size={12} /> Returned to Teacher
              </span>
            );
          }

          // If viewing as Class Teacher: Teacher can re-verify and adjust evaluation
          return (
            <button
              className="edvana-btn"
              style={{
                padding: '0.3rem 0.65rem',
                fontSize: '0.8rem',
                backgroundColor: '#fef2f2',
                color: '#b91c1c',
                border: '1px solid #fecaca',
                fontWeight: 600,
                display: 'inline-flex',
                alignItems: 'center',
                gap: '0.3rem',
                cursor: 'pointer',
              }}
              onClick={() => {
                setActionType('TEACHER_REVIEW');
                setSelectedRecord(r);
                setDecision(r.class_teacher_status);
                setRemarks(r.class_teacher_remarks || '');
              }}
              title="HOD returned this record with remarks. Click to re-verify."
            >
              <RotateCcw size={12} /> Re-verify (HOD Returned)
            </button>
          );
        }

        // Class Teacher has already approved:
        if (r.class_teacher_status === 'APPROVED') {
          // HOD can endorse candidate
          if (canEndorseHOD) {
            return (
              <button
                className="edvana-btn edvana-btn-primary"
                style={{ padding: '0.3rem 0.65rem', fontSize: '0.8rem' }}
                onClick={() => {
                  setActionType('HOD_ENDORSE');
                  setSelectedRecord(r);
                  setDecision(r.hod_status === 'PENDING' ? 'APPROVED' : r.hod_status);
                  setRemarks(r.hod_remarks || '');
                }}
              >
                HOD Endorse
              </button>
            );
          }

          // For Class Teacher: locked awaiting HOD
          return (
            <span
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '0.3rem',
                color: '#15803d',
                fontSize: '0.78rem',
                fontWeight: 600,
                background: '#f0fdf4',
                padding: '0.35rem 0.65rem',
                borderRadius: '6px',
                border: '1px solid #bbf7d0',
              }}
              title="Confirmed by Class Teacher. Locked awaiting HOD review."
            >
              <Lock size={12} /> Confirmed (Locked)
            </span>
          );
        }

        // Class Teacher has flagged to student:
        if (r.class_teacher_status === 'FLAGGED') {
          return (
            <span
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '0.3rem',
                color: '#b91c1c',
                fontSize: '0.78rem',
                fontWeight: 600,
                background: '#fef2f2',
                padding: '0.35rem 0.65rem',
                borderRadius: '6px',
                border: '1px solid #fecaca',
              }}
              title={`Flagged by teacher: ${r.class_teacher_remarks || 'Awaiting student correction'}`}
            >
              <Flag size={12} /> Flagged for Student
            </span>
          );
        }

        // If Class Teacher review is pending:
        if (canReviewTeacher) {
          return (
            <button
              className="edvana-btn edvana-btn-secondary"
              style={{ padding: '0.3rem 0.65rem', fontSize: '0.8rem' }}
              onClick={() => {
                setActionType('TEACHER_REVIEW');
                setSelectedRecord(r);
                setDecision(r.class_teacher_status === 'PENDING' ? 'APPROVED' : r.class_teacher_status);
                setRemarks(r.class_teacher_remarks || '');
              }}
            >
              Teacher Review
            </button>
          );
        }

        // For HOD when Class Teacher has not yet reviewed:
        return (
          <span
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '0.3rem',
              color: '#64748b',
              fontSize: '0.78rem',
              fontWeight: 600,
              background: '#f8fafc',
              padding: '0.35rem 0.65rem',
              borderRadius: '6px',
              border: '1px solid #e2e8f0',
            }}
            title="Awaiting Class Teacher verification first"
          >
            <Clock size={12} /> Awaiting Teacher
          </span>
        );
      },
    },
  ];

  return (
    <>
      <PageHeader
        breadcrumbs={[
          { label: 'Home', to: '/dashboard' },
          { label: 'Academics' },
          { label: 'Eligibility Verification' },
        ]}
        title="Academic Eligibility & Promotion Desk"
        subtitle="Multi-Tier Verification Workflow: Class Teacher Evaluation & HOD Promotion Governance."
        actions={
          <div style={{ display: 'flex', gap: '0.5rem' }}>
            {(canReviewTeacher || canEndorseHOD) && (
              <button
                className="edvana-btn"
                onClick={handleInitialize}
                disabled={initializing}
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '0.45rem',
                  background: '#ffffff',
                  color: '#1d4ed8',
                  borderRadius: '8px',
                  fontWeight: 600,
                  fontSize: '0.8125rem',
                  padding: '0.5rem 1rem',
                }}
              >
                <ClipboardCheck size={15} />
                <span>{initializing ? 'Loading…' : 'Load My Class'}</span>
              </button>
            )}
            <button
              className="edvana-btn"
              onClick={loadEligibilityRecords}
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '0.45rem',
                background: 'rgba(255, 255, 255, 0.16)',
                color: '#ffffff',
                border: '1px solid rgba(255, 255, 255, 0.3)',
                borderRadius: '8px',
                fontWeight: 600,
                fontSize: '0.8125rem',
                padding: '0.5rem 1rem',
              }}
            >
              <RefreshCw size={15} />
              <span>Refresh Records</span>
            </button>
          </div>
        }
      />

      <div className="edvana-banner-overlap">
        {notice && (
          <div style={{ marginBottom: '1rem', padding: '0.9rem 1.1rem', background: '#f0fdf4', border: '1px solid #bbf7d0', borderRadius: '8px', color: '#166534', fontSize: '0.875rem' }}>
            {notice}
          </div>
        )}
        <div className="edvana-card">
          <div className="edvana-card-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div>
              <h2 className="edvana-card-title">Candidate Eligibility Register ({records.length})</h2>
              <p className="edvana-card-description">
                Evaluates backlog thresholds, attendance compliance, and academic progression to next semester
              </p>
            </div>
          </div>
          <div className="edvana-card-body" style={{ padding: 0 }}>
            {loading ? (
              <div style={{ padding: '2.5rem' }}>
                <LoadingState message="Loading candidate eligibility register..." />
              </div>
            ) : error ? (
              <div style={{ padding: '2.5rem' }}>
                <ErrorState title="Error Loading Records" message={error} onRetry={loadEligibilityRecords} />
              </div>
            ) : (
              <DataTable
                columns={columns}
                data={records}
                keyExtractor={(r) => r.id}
                pageSize={10}
                emptyTitle="No Candidates Pending Verification"
                emptyMessage="Fresh admissions appear here after you click Load My Class, or after students submit their marks."
              />
            )}
          </div>
        </div>
      </div>

      {canEndorseHOD && (
        <div className="edvana-card" style={{ marginTop: '1.5rem' }}>
          <div className="edvana-card-header">
            <div>
              <h2 className="edvana-card-title">Graduation Confirmation ({gradList.length})</h2>
              <p className="edvana-card-description">
                Final-semester PASS students awaiting HOD graduation confirmation.
              </p>
            </div>
          </div>
          <div className="edvana-card-body" style={{ padding: 0 }}>
            <DataTable
              columns={[
                { header: 'Student', render: (r) => <span style={{ fontWeight: 600 }}>{r.student_name}</span> },
                { header: 'Session', accessor: 'exam_session' },
                { header: 'SGPA', accessor: 'sgpa' },
                {
                  header: 'Action',
                  align: 'right',
                  render: (r) => (
                    <button
                      className="edvana-btn edvana-btn-primary"
                      style={{ padding: '0.35rem 0.8rem', fontSize: '0.8rem' }}
                      disabled={confirmingGradId === r.id}
                      onClick={() => handleConfirmGraduation(r)}
                    >
                      {confirmingGradId === r.id ? 'Confirming…' : 'Confirm Graduation'}
                    </button>
                  ),
                },
              ]}
              data={gradList}
              emptyMessage="No final-semester students awaiting graduation."
            />
          </div>
        </div>
      )}

      {/* Review Modal */}
      {(() => {
        const isActingAsHOD = actionType === 'HOD_ENDORSE';

        return (
          <Modal
            isOpen={Boolean(selectedRecord)}
            onClose={() => {
              setSelectedRecord(null);
              setReviewMode(null);
            }}
            title={isActingAsHOD ? 'HOD Promotion Endorsement' : 'Class Teacher Academic Review'}
            size="xl"
            maxWidth="940px"
          >
            {selectedRecord && (
              <div>
                {/* 1. Candidate Overview Card */}
                <div
                  style={{
                    background: '#f8fafc',
                    padding: '1.1rem 1.25rem',
                    borderRadius: '8px',
                    marginBottom: '1.25rem',
                    border: '1px solid #e2e8f0',
                    fontSize: '0.875rem',
                    lineHeight: 1.7,
                  }}
                >
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '0.5rem' }}>
                    <div><strong>Candidate:</strong> {selectedRecord.student_name} (<span style={{ fontFamily: 'monospace' }}>{selectedRecord.enrollment_no}</span>)</div>
                    <div><strong>Target Term:</strong> Semester {selectedRecord.target_semester_number} ({selectedRecord.department_code})</div>
                    <div>
                      <strong>Active Backlogs:</strong>{' '}
                      <span style={{ fontWeight: 700, color: selectedRecord.active_backlog_count === 0 ? '#15803d' : '#b91c1c' }}>
                        {selectedRecord.active_backlog_count}
                      </span>
                    </div>
                    <div>
                      <strong>System Calculated:</strong>{' '}
                      <Badge variant={getStatusBadgeVariant(selectedRecord.calculated_status)}>
                        {selectedRecord.calculated_status_display}
                      </Badge>
                    </div>
                    <div>
                      <strong>Workflow Tier:</strong>{' '}
                      <span style={{ fontWeight: 600, color: isActingAsHOD ? '#2563eb' : '#0f172a' }}>
                        {isActingAsHOD ? 'HOD Endorsement Tier' : 'Class Teacher Review Tier'}
                      </span>
                    </div>
                  </div>
                </div>

                {/* HOD Flag Warning Banner if previously returned */}
                {selectedRecord.hod_status === 'FLAGGED' && (
                  <div style={{ padding: '0.75rem 1rem', background: '#fffbeb', border: '1px solid #fef3c7', borderRadius: '6px', color: '#92400e', fontSize: '0.85rem', marginBottom: '1.25rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                    <AlertCircle size={18} style={{ flexShrink: 0, color: '#d97706' }} />
                    <div>
                      <strong>Returned by HOD:</strong> {selectedRecord.hod_remarks || 'Discrepancy noted. Record unlocked for teacher re-evaluation.'}
                    </div>
                  </div>
                )}

                {/* Action Error Banner */}
                {actionError && (
                  <div style={{ padding: '0.75rem 1rem', background: '#fef2f2', border: '1px solid #fecaca', borderRadius: '6px', color: '#991b1b', fontSize: '0.85rem', marginBottom: '1.25rem' }}>
                    {actionError}
                  </div>
                )}

                {/* 2. Submitted Marksheet & Subject Marks Section */}
                <div style={{ marginBottom: '1.5rem' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.45rem', marginBottom: '0.75rem' }}>
                    <FileText size={18} style={{ color: '#2563eb' }} />
                    <h3 style={{ fontSize: '0.95rem', fontWeight: 700, color: '#0f172a', margin: 0 }}>
                      Candidate Marksheet & Subject Marks Evaluation
                    </h3>
                  </div>

                  {loadingResults ? (
                    <LoadingState message="Loading submitted marksheet..." />
                  ) : modalResults.length === 0 ? (
                    <div style={{ padding: '1.5rem', textAlign: 'center', background: '#f8fafc', border: '1px dashed #cbd5e1', borderRadius: '8px', color: '#64748b', fontSize: '0.875rem' }}>
                      No marksheet submitted yet for this student.
                    </div>
                  ) : (
                    modalResults.map((semRes) => (
                      <div
                        key={semRes.id || semRes.semester_number}
                        style={{
                          border: '1px solid #e2e8f0',
                          borderRadius: '8px',
                          overflow: 'hidden',
                          marginBottom: '1rem',
                        }}
                      >
                        {/* Semester Header Strip */}
                        <div
                          style={{
                            background: '#f1f5f9',
                            padding: '0.65rem 1rem',
                            display: 'flex',
                            justifyContent: 'space-between',
                            alignItems: 'center',
                            flexWrap: 'wrap',
                            gap: '0.5rem',
                            borderBottom: '1px solid #e2e8f0',
                          }}
                        >
                          <div style={{ fontWeight: 600, color: '#1e293b', fontSize: '0.875rem' }}>
                            Semester {semRes.semester_number} ({semRes.exam_session || 'Winter 2026'})
                          </div>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '0.85rem', fontSize: '0.8125rem' }}>
                            <span><strong>SGPA:</strong> <span style={{ color: '#2563eb', fontWeight: 700 }}>{semRes.sgpa ?? '—'}</span></span>
                            <span><strong>Credits:</strong> {semRes.total_credits_earned} / {semRes.total_credits_registered}</span>
                            <Badge variant={semRes.result_status === 'PASS' ? 'success' : semRes.result_status === 'ATKT' ? 'warning' : 'danger'}>
                              {semRes.result_status_display || semRes.result_status}
                            </Badge>
                          </div>
                        </div>

                        {/* Subject Score Table */}
                        <div style={{ overflowX: 'auto' }}>
                          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.8125rem' }}>
                            <thead>
                              <tr style={{ background: '#f8fafc', color: '#475569', textAlign: 'left', borderBottom: '1px solid #e2e8f0' }}>
                                <th style={{ padding: '0.55rem 0.85rem', fontWeight: 600 }}>Course / Subject</th>
                                <th style={{ padding: '0.55rem 0.65rem', fontWeight: 600, textAlign: 'center' }}>ESE (60)</th>
                                <th style={{ padding: '0.55rem 0.65rem', fontWeight: 600, textAlign: 'center' }}>ISE (40)</th>
                                <th style={{ padding: '0.55rem 0.65rem', fontWeight: 600, textAlign: 'center' }}>TOTAL (100)</th>
                                <th style={{ padding: '0.55rem 0.65rem', fontWeight: 600, textAlign: 'center' }}>GP</th>
                                <th style={{ padding: '0.55rem 0.65rem', fontWeight: 600, textAlign: 'center' }}>GRADE</th>
                                <th style={{ padding: '0.55rem 0.85rem', fontWeight: 600, textAlign: 'center' }}>STATUS</th>
                              </tr>
                            </thead>
                            <tbody>
                              {(semRes.subjects || []).map((sub, sIdx) => {
                                const isFail = sub.is_backlog || sub.grade_letter === 'F';
                                return (
                                  <tr
                                    key={sub.id || sub.course_code || sIdx}
                                    style={{
                                      borderBottom: '1px solid #f1f5f9',
                                      backgroundColor: isFail ? '#fef2f2' : '#ffffff',
                                    }}
                                  >
                                    <td style={{ padding: '0.55rem 0.85rem' }}>
                                      <div style={{ fontWeight: 600, color: '#0f172a' }}>{sub.course_code}</div>
                                      <div style={{ fontSize: '0.75rem', color: '#64748b' }}>{sub.course_name} ({sub.credits} cr)</div>
                                    </td>
                                    <td style={{ padding: '0.55rem 0.65rem', textAlign: 'center', fontFamily: 'monospace', fontWeight: 600 }}>
                                      {sub.theory_ese_marks ?? '—'}
                                    </td>
                                    <td style={{ padding: '0.55rem 0.65rem', textAlign: 'center', fontFamily: 'monospace', color: '#64748b' }}>
                                      {sub.theory_ise_marks ?? '—'}
                                    </td>
                                    <td style={{ padding: '0.55rem 0.65rem', textAlign: 'center', fontFamily: 'monospace', fontWeight: 700, color: isFail ? '#b91c1c' : '#0f172a' }}>
                                      {sub.total_marks ?? '—'}
                                    </td>
                                    <td style={{ padding: '0.55rem 0.65rem', textAlign: 'center', fontWeight: 700 }}>
                                      {sub.grade_point ?? 0}
                                    </td>
                                    <td style={{ padding: '0.55rem 0.65rem', textAlign: 'center' }}>
                                      <span
                                        style={{
                                          display: 'inline-block',
                                          padding: '0.15rem 0.5rem',
                                          borderRadius: '4px',
                                          fontWeight: 700,
                                          fontSize: '0.75rem',
                                          backgroundColor: isFail ? '#fee2e2' : '#dcfce7',
                                          color: isFail ? '#b91c1c' : '#15803d',
                                        }}
                                      >
                                        {sub.grade_letter}
                                      </span>
                                    </td>
                                    <td style={{ padding: '0.55rem 0.85rem', textAlign: 'center' }}>
                                      <span style={{ fontSize: '0.75rem', fontWeight: 600, color: isFail ? '#b91c1c' : '#15803d' }}>
                                        {isFail ? 'Backlog (F)' : 'Pass'}
                                      </span>
                                    </td>
                                  </tr>
                                );
                              })}
                            </tbody>
                          </table>
                        </div>
                      </div>
                    ))
                  )}
                </div>

                {/* 3. Decision & Action Workflow Controls */}
                <div style={{ borderTop: '1px solid #e2e8f0', paddingTop: '1.25rem' }}>
                  {reviewMode === null ? (
                    <div>
                      <div style={{ marginBottom: '0.9rem' }}>
                        <div style={{ fontWeight: 700, color: '#0f172a', fontSize: '0.9rem' }}>Review Action</div>
                        <div style={{ fontSize: '0.8125rem', color: '#64748b' }}>
                          {isActingAsHOD 
                            ? 'Approve to confirm final eligibility or flag to return to Class Teacher for correction.'
                            : 'Approve to confirm and forward to HOD, or flag to return to the student for mark correction.'}
                        </div>
                      </div>

                      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '1rem' }}>
                        {/* Red Flag Button */}
                        <button
                          type="button"
                          onClick={() => {
                            setReviewMode('FLAG');
                            setRemarks('');
                            setActionError(null);
                          }}
                          style={{
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            gap: '0.5rem',
                            padding: '0.75rem 1.25rem',
                            borderRadius: '8px',
                            fontWeight: 600,
                            fontSize: '0.875rem',
                            backgroundColor: '#fef2f2',
                            color: '#b91c1c',
                            border: '1.5px solid #f87171',
                            cursor: 'pointer',
                            transition: 'all 0.15s ease',
                          }}
                        >
                          <Flag size={16} />
                          <span>{isActingAsHOD ? 'Flag & Return to Class Teacher' : 'Flag Discrepancy for Student'}</span>
                        </button>

                        {/* Green Approve Button */}
                        <button
                          type="button"
                          onClick={() => {
                            setReviewMode('APPROVE');
                            setRemarks('Marks verified against original marksheet and attendance approved.');
                            setActionError(null);
                          }}
                          style={{
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            gap: '0.5rem',
                            padding: '0.75rem 1.25rem',
                            borderRadius: '8px',
                            fontWeight: 600,
                            fontSize: '0.875rem',
                            backgroundColor: '#f0fdf4',
                            color: '#15803d',
                            border: '1.5px solid #4ade80',
                            cursor: 'pointer',
                            transition: 'all 0.15s ease',
                          }}
                        >
                          <Check size={16} />
                          <span>{isActingAsHOD ? 'Approve & Endorse Promotion' : 'Approve & Confirm (Lock Record)'}</span>
                        </button>
                      </div>
                    </div>
                  ) : reviewMode === 'FLAG' ? (
                    /* Red Flag Submission Panel */
                    <div
                      style={{
                        backgroundColor: '#fef2f2',
                        border: '1.5px solid #fecaca',
                        borderRadius: '8px',
                        padding: '1.1rem',
                      }}
                    >
                      <div style={{ display: 'flex', alignItems: 'center', gap: '0.45rem', color: '#991b1b', fontWeight: 700, fontSize: '0.9rem', marginBottom: '0.25rem' }}>
                        <Flag size={16} />
                        <span>{isActingAsHOD ? 'Flag & Return to Class Teacher' : 'Flag Discrepancy for Student'}</span>
                      </div>
                      <div style={{ fontSize: '0.8125rem', color: '#b91c1c', marginBottom: '0.75rem' }}>
                        {isActingAsHOD 
                          ? 'This remark will be sent back to the Class Teacher so they can adjust the evaluation or notify the student.'
                          : 'This reason will be displayed directly to the student in their Results portal so they can edit their marks and re-submit.'}
                      </div>

                      <FormField label="Reason for Flagging (Required)" required>
                        <textarea
                          rows={3}
                          className="edvana-input"
                          style={{ width: '100%', padding: '0.65rem', borderColor: '#f87171' }}
                          placeholder="e.g. ESE theory marks entered as 0 in CS101. Please check your original marksheet and re-enter correct marks."
                          value={remarks}
                          onChange={(e) => setRemarks(e.target.value)}
                          autoFocus
                        />
                      </FormField>

                      <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem', marginTop: '1rem' }}>
                        <button
                          type="button"
                          className="edvana-btn edvana-btn-secondary"
                          onClick={() => {
                            setReviewMode(null);
                            setActionError(null);
                          }}
                          disabled={submitting}
                        >
                          Cancel
                        </button>
                        <button
                          type="button"
                          onClick={() => handleReviewSubmit('FLAGGED', remarks)}
                          className="edvana-btn"
                          disabled={submitting}
                          style={{
                            backgroundColor: '#dc2626',
                            color: '#ffffff',
                            fontWeight: 600,
                            display: 'inline-flex',
                            alignItems: 'center',
                            gap: '0.4rem',
                          }}
                        >
                          <Flag size={14} />
                          <span>{submitting ? 'Flagging...' : isActingAsHOD ? 'Confirm Flag to Teacher' : 'Confirm Flag & Return to Student'}</span>
                        </button>
                      </div>
                    </div>
                  ) : (
                    /* Green Approve Submission Panel */
                    <div
                      style={{
                        backgroundColor: '#f0fdf4',
                        border: '1.5px solid #bbf7d0',
                        borderRadius: '8px',
                        padding: '1.1rem',
                      }}
                    >
                      <div style={{ display: 'flex', alignItems: 'center', gap: '0.45rem', color: '#166534', fontWeight: 700, fontSize: '0.9rem', marginBottom: '0.25rem' }}>
                        <Check size={16} />
                        <span>{isActingAsHOD ? 'Approve & Endorse Promotion' : 'Approve & Confirm (Lock Record)'}</span>
                      </div>
                      <div style={{ fontSize: '0.8125rem', color: '#15803d', marginBottom: '0.75rem' }}>
                        {isActingAsHOD 
                          ? 'This candidate will officially become Eligible for Admission and will immediately appear in the Accountant Candidate Ledger.'
                          : 'This will confirm the marks and forward the candidate to the HOD for endorsement. The record will be locked from further edits.'}
                      </div>

                      <FormField label="Audit Remarks (Optional)">
                        <textarea
                          rows={2}
                          className="edvana-input"
                          style={{ width: '100%', padding: '0.65rem', borderColor: '#86efac' }}
                          value={remarks}
                          onChange={(e) => setRemarks(e.target.value)}
                        />
                      </FormField>

                      <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem', marginTop: '1rem' }}>
                        <button
                          type="button"
                          className="edvana-btn edvana-btn-secondary"
                          onClick={() => {
                            setReviewMode(null);
                            setActionError(null);
                          }}
                          disabled={submitting}
                        >
                          Cancel
                        </button>
                        <button
                          type="button"
                          onClick={() => handleReviewSubmit('APPROVED', remarks)}
                          className="edvana-btn"
                          disabled={submitting}
                          style={{
                            backgroundColor: '#16a34a',
                            color: '#ffffff',
                            fontWeight: 600,
                            display: 'inline-flex',
                            alignItems: 'center',
                            gap: '0.4rem',
                          }}
                        >
                          <Check size={14} />
                          <span>{submitting ? 'Approving...' : isActingAsHOD ? 'Confirm Endorsement' : 'Confirm & Lock Record'}</span>
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              </div>
            )}
          </Modal>
        );
      })()}
    </>
  );
}
