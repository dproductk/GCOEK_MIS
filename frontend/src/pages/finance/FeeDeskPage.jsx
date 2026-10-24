import React, { useState, useEffect, useRef } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { 
  Search, RefreshCw, FileText, Printer,
  CheckCircle2, AlertCircle, X, Users, ChevronLeft, ChevronRight, Lock,
  Globe, RotateCcw
} from 'lucide-react';
import studentApi from '../../api/studentApi';
import financeApi from '../../api/financeApi';
import academicApi from '../../api/academicApi';
import PageHeader from '../../components/common/PageHeader';
import Modal from '../../components/common/Modal';
import FormField from '../../components/common/FormField';
import { LoadingState, EmptyState, ErrorState } from '../../components/common/StateDisplays';
import FeeReceiptPdfModal from '../../components/finance/FeeReceiptPdfModal';
import { fetchAllListPages } from '../../utils/listPages';

export default function FeeDeskPage() {
  const navigate = useNavigate();
  const location = useLocation();

  // Tab State: 'desk' (Candidate Fee Desk) vs 'online_tracker' (Online Payment Tracker)
  const [activeTab, setActiveTab] = useState('desk');

  const [students, setStudents] = useState([]);
  // Server-side total for the current roster query (eligible count when
  // the Eligible toggle is on). The list itself is page-capped.
  const [totalCandidates, setTotalCandidates] = useState(0);
  const [departments, setDepartments] = useState([]);
  const [academicYears, setAcademicYears] = useState([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState(null);
  const [successMsg, setSuccessMsg] = useState(location.state?.successMsg || '');

  // Online Payment Tracker State
  const [trackerData, setTrackerData] = useState([]);
  const [loadingTracker, setLoadingTracker] = useState(false);
  const [trackerSearch, setTrackerSearch] = useState('');
  const [trackerOnlyOnline, setTrackerOnlyOnline] = useState(true);
  const [togglingStudentId, setTogglingStudentId] = useState(null);
  const [reconcilingTxnId, setReconcilingTxnId] = useState(null);


  // Filters (matching StudentDirectoryPage layout)
  const [search, setSearch] = useState('');
  const [selectedDept, setSelectedDept] = useState('');
  const [selectedFeeStatus, setSelectedFeeStatus] = useState('');
  const [selectedYear, setSelectedYear] = useState('');
  // Candidate ledger is ALWAYS eligible-only (HOD + class-teacher verified).
  // No toggle: the backend eligible_only filter is forced on every fetch.

  // Pagination State (20 candidates per page)
  const PAGE_SIZE = 20;
  const [currentPage, setCurrentPage] = useState(1);

  // Local fees map { [studentId]: { totalFee, isSet, breakdown } }
  const [feesMap, setFeesMap] = useState({});

  // Set when any list page failed mid-fetch. The desk renders what it did
  // load, but must warn that paid/unpaid status could be incomplete — a
  // missing page must never print as "unpaid" at the counter.
  const [listDataWarning, setListDataWarning] = useState('');
  // A page-level load failure (403/500/network) is NOT the same as "no
  // candidates": silently empty made a broken desk indistinguishable from
  // an empty queue. loadError replaces the roster with a Retry screen.
  const [loadError, setLoadError] = useState('');

  // Only the newest fetchData run may apply state: fast successive searches
  // would otherwise let an older multi-page run overwrite fresher results.
  const fetchSeqRef = useRef(0);

  // Reset to first page when any filter criteria changes
  useEffect(() => {
    setCurrentPage(1);
  }, [search, selectedDept, selectedFeeStatus, selectedYear]);

  // Mark Fee Modal State
  const [showMarkModal, setShowMarkModal] = useState(false);
  const [markingStudent, setMarkingStudent] = useState(null);
  const [markForm, setMarkForm] = useState({
    amountPaid: '',
    paymentMode: 'ONLINE',
    transactionRef: '',
    remarks: 'Admission fee collected'
  });
  const [submittingPayment, setSubmittingPayment] = useState(false);

  // Official Receipt Modal State (fee-desk-only printing)
  const [showReceiptModal, setShowReceiptModal] = useState(false);
  const [receiptStudent, setReceiptStudent] = useState(null);
  const [receiptRecord, setReceiptRecord] = useState(null);
  const [loadingReceipt, setLoadingReceipt] = useState(false);
  // Receipt-lookup failure is NOT the same as "no receipt yet": if the ledger
  // API call errors, say so, so the accounts desk never tells a parent
  // "not found" because of a server hiccup.
  const [receiptLookupError, setReceiptLookupError] = useState('');

  // Student whose fee was just set (from Set Fee page) pins at the top of
  // the desk so Mark Fee is one click away. Cleared via Clear Filters.
  const [pinnedId, setPinnedId] = useState(null);

  useEffect(() => {
    if (location.state?.successMsg) {
      setSuccessMsg(location.state.successMsg);
      const timer = setTimeout(() => setSuccessMsg(''), 4500);
      return () => clearTimeout(timer);
    }
  }, [location.state]);

  useEffect(() => {
    if (location.state?.justSetStudentId) {
      setPinnedId(String(location.state.justSetStudentId));
      setCurrentPage(1);
      // Clear state in history so toast/pin don't re-apply on reload
      window.history.replaceState({}, document.title);
    }
  }, [location.state]);

  const fetchData = async (isManual = false) => {
    if (isManual) setRefreshing(true);
    else setLoading(true);
    setError(null);
    setLoadError('');
    const seq = ++fetchSeqRef.current;

    try {
      // Fee status comes from the backend ledger only: assessments say a
      // fee was set, payment rows say it was paid. No browser storage.
      //
      // Data completeness: backend list APIs are page-capped (students 500,
      // finance 1000). The roster still walks every server page via
      // fetchAllListPages. The fee verdicts come from the compact
      // /ledger/fee-status-map/ endpoint, which folds the COMPLETE
      // assessment+ledger history server-side into one response — one
      // finance request no matter how long history grows, and no client
      // truncation mistakes ever again. If that endpoint is unavailable
      // (older backend / transient failure), we fall back to walking every
      // ledger+assessment page — complete, just heavier.
      const [mapRes, stuRes, deptsRes, yearsRes] = await Promise.allSettled([
        financeApi.getFeeStatusMap(),
        // Eligible-only is mandatory here: HOD + class-teacher verified
        // candidates (final_eligible) plus seated freshers with a teacher.
        fetchAllListPages(studentApi.getStudents, {
          search: search.trim() || undefined,
          page_size: 500,
          eligible_only: 'true',
        }),
        fetchAllListPages(academicApi.getDepartments, {}),
        fetchAllListPages(academicApi.getAcademicYears, {}),
      ]);

      // A newer search/refresh superseded this run — drop these results so a
      // slow older fetch can never overwrite fresher data.
      if (fetchSeqRef.current !== seq) return;

      // Primary path: server-folded verdict map.
      const mapUsable = mapRes.status === 'fulfilled'
        && mapRes.value?.data
        && typeof mapRes.value.data === 'object'
        && mapRes.value.data.data !== null
        && typeof mapRes.value.data.data === 'object';

      let builtMap = {};
      let mapIncomplete = false;
      let verdictBroken = false;

      if (mapUsable) {
        builtMap = mapRes.value.data.data;
      } else {
        // Fallback (older backend / summary unavailable): walk every
        // ledger+assessment page. Semantics identical to the server fold:
        // assessments first (their list order), then ledgers overwrite
        // (their list order), ₹0-due rows skipped.
        console.error(
          'Fee desk: fee-status-map unavailable; falling back to page walks.',
          mapRes.status === 'rejected' ? mapRes.reason : mapRes.value?.data
        );
        const [ledgerPages, assessPages] = await Promise.allSettled([
          fetchAllListPages(financeApi.getPaymentLedgers, { page_size: 1000 }),
          fetchAllListPages(financeApi.getAssessments, { page_size: 1000 }),
        ]);
        if (ledgerPages.status === 'rejected' || assessPages.status === 'rejected') {
          // Bug-level throw — the walker usually fulfils instead.
          verdictBroken = true;
          console.error('Fee desk: fallback page walk rejected.', ledgerPages.reason, assessPages.reason);
        } else {
          // A walk is BROKEN when it failed while yielding zero rows
          // (page-1 failure). Empty-but-clean (fresh college, no fee data
          // yet) is a legitimate result, not a failure. Partial failures
          // (some rows loaded, a later page failed) degrade to a warning.
          const ledgerBroken = ledgerPages.value.incomplete
            && ledgerPages.value.results.length === 0;
          const assessBroken = assessPages.value.incomplete
            && assessPages.value.results.length === 0;
          mapIncomplete = ledgerPages.value.incomplete || assessPages.value.incomplete;
          if (ledgerBroken || assessBroken) {
            verdictBroken = true;
          }
          assessPages.value.results.forEach(a => {
            if (a.student) {
              builtMap[a.student] = {
                totalFee: parseFloat(a.total_fee),
                breakdown: a.fee_breakdown || {},
                isSet: true,
                assessmentId: a.id,
                allowOnlinePayment: Boolean(a.allow_online_payment),
                academicYearId: a.academic_year || null,
                academicYearCode: a.academic_year_code || '',
              };
            }
          });
          ledgerPages.value.results.forEach(l => {
            if (l.student && l.total_fee_due > 0) {
              builtMap[l.student] = {
                ...(builtMap[l.student] || {}),
                totalFee: parseFloat(l.total_fee_due),
                isSet: true,
                isPaid: l.status === 'PAID',
                amountPaid: parseFloat(l.amount_paid),
                academicYearId: l.academic_year || builtMap[l.student]?.academicYearId || null,
                academicYearCode: l.academic_year_code || builtMap[l.student]?.academicYearCode || '',
              };
            }
          });
        }
      }

      // Critical-load failure gate. Promise.allSettled never rejects, so the
      // catch below was unreachable — every load failure (403/429/500/network)
      // used to render as an empty roster: "No Eligible Candidates Found",
      // indistinguishable from a college with zero candidates. The desk
      // decides money on students + assessments + ledgers, so if ANY of those
      // calls fails, stop and say so instead of showing a lying roster
      // (a missing-fee overlay would mislabel paid students as unpaid).
      // With the walkers never rejecting, "failed" means: fulfilled but with
      // zero rows while flagged incomplete — a page-1 failure surfaces there.
      const studentRosterBroken = stuRes.status === 'rejected' || (
        stuRes.status === 'fulfilled'
        && stuRes.value.incomplete
        && stuRes.value.results.length === 0
      );
      const criticalFailed = studentRosterBroken
        // A broken verdict read (fallback mode only) is just as unreliable
        // as a missing ledger — the desk decides money on it.
        || verdictBroken;
      if (criticalFailed) {
        // Don't apply partial data — a students-only load would show every
        // candidate unpaid. Clear to a known-empty state behind a Retry screen.
        setStudents([]);
        setFeesMap({});
        setTotalCandidates(0);
        setListDataWarning('');
        setLoadError(
          'Could not load fee desk data — a server request failed ' +
          '(session may have expired or the service is down). ' +
          'The list below is not reliable right now; press Retry. ' +
          'Do not record payments until the desk loads.'
        );
        return;
      }
      setLoadError('');

      if (stuRes.status === 'fulfilled') {
        setStudents(stuRes.value.results);
        setTotalCandidates(stuRes.value.count ?? stuRes.value.results.length);
      }

      if (deptsRes.status === 'fulfilled') {
        setDepartments(deptsRes.value.results);
      }

      if (yearsRes.status === 'fulfilled') {
        setAcademicYears(yearsRes.value.results);
      }

      setFeesMap(builtMap);

      // Page-level failures: warn instead of silently rendering a truncated
      // view — a truncated view mislabels paid students as unpaid. Includes
      // partially-failed fallback walks (fee-status-map succeeded ⇒ map is
      // complete server-side, then mapIncomplete stays false).
      const anyIncomplete = mapIncomplete || [stuRes, deptsRes, yearsRes]
        .some(res => res.status === 'fulfilled' && res.value.incomplete);
      // Filter dropdowns (departments/years) may fail independently of the
      // critical data — degrade with a warning instead of hiding it.
      const filterDataFailed = deptsRes.status === 'rejected' || yearsRes.status === 'rejected';
      setListDataWarning(anyIncomplete || filterDataFailed
        ? 'Some list or filter data failed to load. Paid/unpaid status may look incomplete — press Refresh to retry.'
        : '');

    } catch (err) {
      console.error('Error loading candidate fee desk:', err);
      // Unreachable through allSettled rejection, but a thrown bug (e.g. in
      // state processing) must also fail visibly, never as an empty roster.
      setLoadError('Failed to fetch fee desk data. Press Retry — the list is not reliable right now.');
      setStudents([]);
      setFeesMap({});
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  // Load online payment tracker data
  const loadTrackerData = async () => {
    setLoadingTracker(true);
    try {
      const res = await financeApi.getOnlinePaymentTracker({
        online_only: trackerOnlyOnline ? 'true' : 'false',
        search: trackerSearch.trim() || undefined,
      });
      setTrackerData(res.data || []);
    } catch (err) {
      console.error('Failed to load online payment tracker:', err);
    } finally {
      setLoadingTracker(false);
    }
  };

  useEffect(() => {
    if (activeTab === 'online_tracker') {
      loadTrackerData();
    }
  }, [activeTab, trackerSearch, trackerOnlyOnline]);

  // Toggle online payment permission directly from desk or tracker
  const handleToggleOnline = async (studentId, assessmentId, currentVal) => {
    if (!assessmentId) {
      setError('Please set the admission fee first before configuring online payment.');
      setTimeout(() => setError(null), 4000);
      return;
    }
    setTogglingStudentId(studentId);
    try {
      const nextVal = !currentVal;
      await financeApi.toggleOnlinePayment(assessmentId, { allow_online_payment: nextVal });
      setFeesMap(prev => ({
        ...prev,
        [studentId]: {
          ...prev[studentId],
          allowOnlinePayment: nextVal,
        }
      }));
      setSuccessMsg(`Online payment ${nextVal ? 'enabled' : 'disabled'} for candidate.`);
      setTimeout(() => setSuccessMsg(''), 3500);
      if (activeTab === 'online_tracker') {
        loadTrackerData();
      }
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to update online payment preference.');
      setTimeout(() => setError(null), 4000);
    } finally {
      setTogglingStudentId(null);
    }
  };

  // Manual reconciliation inquiry with bank
  const handleReconcileAttempt = async (attemptId) => {
    if (!attemptId) return;
    setReconcilingTxnId(attemptId);
    try {
      const res = await financeApi.verifyPaymentAttempt(attemptId);
      setSuccessMsg(`Gateway status verified: ${res.data?.detail || res.data?.status}`);
      setTimeout(() => setSuccessMsg(''), 4500);
      loadTrackerData();
      fetchData();
    } catch (err) {
      setError('Status inquiry failed. Gateway may be unreachable.');
      setTimeout(() => setError(null), 4000);
    } finally {
      setReconcilingTxnId(null);
    }
  };

  useEffect(() => {
    // Debounced backend search: filters stay live without spamming the API.
    const t = setTimeout(() => {
      fetchData();
    }, search.trim() ? 400 : 0);
    return () => clearTimeout(t);
  }, [search]);

  // Client-side filtering across departments, academic year & fee statuses
  // NOTE: Candidates enabled for online payment gateway are routed exclusively
  // to the "Online Payment Gateway" tab so they are not duplicated here.
  const filteredStudents = students.filter(s => {
    const feeInfo = feesMap[s.id];
    // If online payment is enabled for this candidate, they belong to the Online Gateway tab
    if (feeInfo?.allowOnlinePayment) {
      return false;
    }

    if (selectedDept && s.department_code !== selectedDept) {
      return false;
    }
    // Academic year filter: match the assessment/ledger year. Students with
    // no fee record yet (UNSET) are shown under any selected year as pending.
    if (selectedYear && feeInfo?.academicYearId && String(feeInfo.academicYearId) !== String(selectedYear)) {
      return false;
    }
    const isFeeSet = Boolean(feeInfo && feeInfo.totalFee > 0);
    const isPaid = Boolean(feeInfo && feeInfo.isPaid);

    if (selectedFeeStatus === 'SET' && !isFeeSet) return false;
    if (selectedFeeStatus === 'UNSET' && isFeeSet) return false;
    if (selectedFeeStatus === 'PAID' && !isPaid) return false;
    return true;
  });

  // Pin the just-fee-set student first (when visible under current filters).
  const sortedStudents = [...filteredStudents].sort((a, b) => {
    if (!pinnedId) return 0;
    if (String(a.id) === String(pinnedId)) return -1;
    if (String(b.id) === String(pinnedId)) return 1;
    return 0;
  });

  // Count of manual desk candidates (excluding online payment enabled)
  const manualCandidatesCount = students.filter(s => !feesMap[s.id]?.allowOnlinePayment).length;
  const onlineCandidatesCount = students.filter(s => feesMap[s.id]?.allowOnlinePayment).length;

  const hasActiveFilters = Boolean(search.trim() || selectedDept || selectedFeeStatus || selectedYear);
  const totalPages = Math.ceil(sortedStudents.length / PAGE_SIZE) || 1;
  const startIndex = (currentPage - 1) * PAGE_SIZE;
  const endIndex = Math.min(startIndex + PAGE_SIZE, sortedStudents.length);
  const currentStudents = sortedStudents.slice(startIndex, endIndex);

  const handleClearFilters = () => {
    setSearch('');
    setSelectedDept('');
    setSelectedFeeStatus('');
    setSelectedYear('');
    setPinnedId(null);
    setCurrentPage(1);
  };

  // Action: Open Mark Fee Modal — blocked if already paid (single mark only).
  const handleOpenMarkFee = (student) => {
    const feeInfo = feesMap[student.id];
    if (feeInfo && feeInfo.isPaid) {
      setError(`Fee already marked paid for ${student.display_name}. Duplicate payment blocked.`);
      setTimeout(() => setError(null), 4000);
      return;
    }
    if (!feeInfo?.isSet || !feeInfo?.totalFee) {
      setError(`Set the admission fee first for ${student.display_name} before marking payment.`);
      setTimeout(() => setError(null), 4000);
      return;
    }
    const defaultAmount = feeInfo.totalFee;
    setMarkingStudent(student);
    setMarkForm({
      amountPaid: String(defaultAmount),
      paymentMode: 'ONLINE',
      transactionRef: `TXN-${Date.now().toString().slice(-6)}`,
      remarks: 'Admission fee counter collection'
    });
    setShowMarkModal(true);
  };

  // Submit Mark Fee Payment
  const handleSubmitMarkFee = async (e) => {
    e.preventDefault();
    if (!markingStudent) return;
    setSubmittingPayment(true);
    setError(null);

    // The ledger must attach to the SAME year the fee was assessed in — read
    // from the fee data itself, not guessed as "the current year". In the
    // normal same-day flow (Set Fee → pay immediately) both are identical, so
    // behavior is unchanged; at a year transition this stops the 400
    // "Set the admission fee first" mismatch for a prior-year assessment.
    const feeYearId =
      feesMap[markingStudent.id]?.academicYearId
      || academicYears.find(y => y.is_current)?.id
      || academicYears[0]?.id
      || null;
    const amountVal = parseFloat(markForm.amountPaid) || 0;

    try {
      // No client receipt: the server sequences <ROMAN><YY><YY>-<nnnn> (e.g. IV2627-0001).
      const payload = {
        student: markingStudent.id,
        academic_year: feeYearId,
        total_fee_due: amountVal,
        amount_paid: amountVal,
        payment_mode: markForm.paymentMode,
        transaction_ref: markForm.transactionRef || `OFFLINE-${Date.now()}`,
        // IST local date for the official receipt. toISOString() is UTC and
        // stamps collections made 00:00–05:30 IST with the previous day.
        payment_date: new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Kolkata' }).format(new Date()),
        remarks: markForm.remarks,
      };

      const created = await financeApi.recordPayment(payload);

      // Refresh from backend truth (assessments + ledgers)
      await fetchData();

      const receiptNo = created.data?.receipt_no || 'issued';
      // Promotion outcome rides the receipt response: a non-promoted result
      // after payment is a visible deferral, never a silent misfire.
      const promo = created.data?.promotion;
      if (promo && promo.attempted && !promo.promoted) {
        setSuccessMsg(
          `Fee marked and receipt ${receiptNo} issued for ${markingStudent.display_name}. ` +
          `Note: auto-promotion deferred (${promo.message || 'requirements pending'}) — use Promote Class.`
        );
      } else {
        setSuccessMsg(`Fee marked and receipt ${receiptNo} issued for ${markingStudent.display_name}!`);
      }
      setShowMarkModal(false);
      setTimeout(() => setSuccessMsg(''), 6000);
    } catch (err) {
      console.error('Error recording fee:', err);
      // Surface the real backend error (e.g. duplicate blocked) — never fake success.
      const backendMsg =
        err.response?.data?.detail ||
        (typeof err.response?.data === 'object'
          ? Object.values(err.response.data).flat().join(' ')
          : null) ||
        'Failed to record fee. Duplicate payment blocked — this student already has a paid receipt.';
      setError(backendMsg);
      setTimeout(() => setError(null), 5000);
    } finally {
      setSubmittingPayment(false);
    }
  };

  // Official Receipt Printer (fee-desk-only)
  const handleOpenReceipt = async (student) => {
    setReceiptStudent(student);
    setShowReceiptModal(true);
    setLoadingReceipt(true);
    setReceiptRecord(null);
    setReceiptLookupError('');
    try {
      const res = await financeApi.getPaymentLedgers({ search: student.enrollment_no || student.display_name });
      const records = res.data?.results || res.data || [];
      const studentRecords = records
        .filter(r => r.student === student.id || r.enrollment_no === student.enrollment_no)
        .sort((a, b) => new Date(b.payment_date) - new Date(a.payment_date));
      setReceiptRecord(studentRecords[0] || null);
    } catch (err) {
      console.error('Error fetching receipt:', err);
      // A failed lookup must never read as "No Paid Receipt Found".
      setReceiptLookupError('receipt lookup failed');
    } finally {
      setLoadingReceipt(false);
    }
  };

  return (
    <>
      <PageHeader
        breadcrumbs={[
          { label: 'Home', to: '/dashboard' },
          { label: 'Finance' },
          { label: 'Candidate Fee Collection Desk' },
        ]}
        title="Candidate Fee Collection Desk"
        subtitle="Record manual counter fee receipts or manage students using the online payment gateway."
      />

      <div className="edvana-banner-overlap">
        {successMsg && (
          <div style={{
            marginBottom: '1.25rem',
            padding: '1rem 1.25rem',
            background: '#f0fdf4',
            border: '1px solid #bbf7d0',
            borderRadius: '10px',
            color: '#166534',
            fontSize: '0.875rem',
            display: 'flex',
            alignItems: 'center',
            gap: '0.75rem',
            boxShadow: '0 1px 3px rgba(0,0,0,0.04)'
          }}>
            <CheckCircle2 size={18} style={{ flexShrink: 0, color: '#16a34a' }} />
            <div style={{ fontWeight: 600 }}>{successMsg}</div>
          </div>
        )}

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

        {listDataWarning && !error && (
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
            <AlertCircle size={18} style={{ flexShrink: 0, color: '#d97706' }} />
            <div style={{ fontWeight: 600 }}>{listDataWarning}</div>
          </div>
        )}

        {/* Main Card (Styled exactly like StudentDirectoryPage) */}
        <div className="edvana-card" style={{ padding: '1.5rem 1.75rem' }}>
          {/* Top Navigation & View Switcher Slider */}
          <div style={{
            display: 'flex',
            flexWrap: 'wrap',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: '1rem',
            marginBottom: '1.25rem',
            paddingBottom: '1rem',
            borderBottom: '1px solid #f1f5f9'
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', flexWrap: 'wrap' }}>
              {/* Pill Tabs */}
              <div style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '4px',
                background: '#f1f5f9',
                padding: '4px',
                borderRadius: '999px',
                border: '1px solid #e2e8f0',
                boxShadow: 'inset 0 1px 2px rgba(0,0,0,0.03)',
                userSelect: 'none',
              }}>
                <button
                  type="button"
                  onClick={() => setActiveTab('desk')}
                  style={{
                    padding: '0.35rem 1rem',
                    fontSize: '0.75rem',
                    fontWeight: activeTab === 'desk' ? 700 : 500,
                    color: activeTab === 'desk' ? '#1E60DC' : '#64748b',
                    background: activeTab === 'desk' ? '#ffffff' : 'transparent',
                    border: 'none',
                    borderRadius: '999px',
                    boxShadow: activeTab === 'desk'
                      ? '0 2px 8px rgba(30, 96, 220, 0.14), 0 1px 3px rgba(0,0,0,0.06)'
                      : 'none',
                    cursor: 'pointer',
                    transition: 'all 0.2s ease',
                    display: 'inline-flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    gap: '0.45rem',
                    whiteSpace: 'nowrap',
                    lineHeight: 1.5,
                  }}
                >
                  <Users size={14} strokeWidth={2.2} style={{ flexShrink: 0, display: 'block', color: activeTab === 'desk' ? '#1E60DC' : '#94a3b8' }} />
                  <span>Manual Fee Desk</span>
                  <span style={{
                    fontSize: '0.65rem',
                    fontWeight: 700,
                    background: activeTab === 'desk' ? '#eff6ff' : '#e2e8f0',
                    color: activeTab === 'desk' ? '#1E60DC' : '#64748b',
                    padding: '0.12rem 0.55rem',
                    borderRadius: '999px',
                    lineHeight: 1.5,
                  }}>
                    {manualCandidatesCount}
                  </span>
                </button>

                <button
                  type="button"
                  onClick={() => setActiveTab('online_tracker')}
                  style={{
                    padding: '0.35rem 1rem',
                    fontSize: '0.75rem',
                    fontWeight: activeTab === 'online_tracker' ? 700 : 500,
                    color: activeTab === 'online_tracker' ? '#15803d' : '#64748b',
                    background: activeTab === 'online_tracker' ? '#ffffff' : 'transparent',
                    border: 'none',
                    borderRadius: '999px',
                    boxShadow: activeTab === 'online_tracker'
                      ? '0 2px 8px rgba(22, 163, 74, 0.16), 0 1px 3px rgba(0,0,0,0.06)'
                      : 'none',
                    cursor: 'pointer',
                    transition: 'all 0.2s ease',
                    display: 'inline-flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    gap: '0.45rem',
                    whiteSpace: 'nowrap',
                    lineHeight: 1.5,
                  }}
                >
                  <Globe size={14} strokeWidth={2.2} style={{ flexShrink: 0, display: 'block', color: activeTab === 'online_tracker' ? '#16a34a' : '#94a3b8' }} />
                  <span>Online Payment Gateway</span>
                  <span style={{
                    fontSize: '0.65rem',
                    fontWeight: 700,
                    background: activeTab === 'online_tracker' ? '#dcfce7' : '#e2e8f0',
                    color: activeTab === 'online_tracker' ? '#15803d' : '#64748b',
                    padding: '0.12rem 0.55rem',
                    borderRadius: '999px',
                    border: activeTab === 'online_tracker' ? '1px solid #bbf7d0' : '1px solid transparent',
                    lineHeight: 1.5,
                  }}>
                    {onlineCandidatesCount > 0 ? onlineCandidatesCount : 'Easebuzz'}
                  </span>
                </button>
              </div>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              {activeTab === 'desk' ? (
                <span style={{
                  background: '#f8fafc',
                  color: '#475569',
                  border: '1px solid #e2e8f0',
                  borderRadius: '20px',
                  padding: '0.35rem 0.85rem',
                  fontSize: '0.75rem',
                  fontWeight: 600,
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '0.4rem'
                }}>
                  <Users size={13} style={{ color: '#1E60DC' }} />
                  <span>
                    {hasActiveFilters
                      ? `${filteredStudents.length} Results (${manualCandidatesCount} Manual)`
                      : `${manualCandidatesCount} Manual Counter Candidates`}
                  </span>
                </span>
              ) : (
                <button
                  type="button"
                  onClick={loadTrackerData}
                  disabled={loadingTracker}
                  className="edvana-btn edvana-btn-secondary"
                  style={{
                    height: '32px',
                    padding: '0 0.85rem',
                    fontSize: '0.78rem',
                    borderRadius: '18px',
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '0.35rem'
                  }}
                >
                  <RefreshCw size={13} className={loadingTracker ? 'animate-spin' : ''} />
                  <span>{loadingTracker ? 'Refreshing...' : 'Refresh Gateway'}</span>
                </button>
              )}
            </div>
          </div>


          {activeTab === 'desk' ? (
            <div key="manual_desk" className="animate-fade-up">
              {/* Filter Bar — EXACT MATCH TO StudentDirectoryPage */}
              <div
                style={{
                  display: 'flex',
                  flexWrap: 'wrap',
                  gap: '0.625rem',
                  alignItems: 'center',
                  backgroundColor: '#ffffff',
                  padding: '0.75rem 0 1.25rem 0',
                  borderBottom: '1px solid #f1f5f9',
                  marginBottom: '1rem'
                }}
              >
                {/* Search Input */}
                <div style={{ position: 'relative', flex: '1 1 260px', minWidth: '220px' }}>
                  <Search
                    size={16}
                    style={{
                      position: 'absolute',
                      left: '12px',
                      top: '50%',
                      transform: 'translateY(-50%)',
                      color: '#94a3b8',
                    }}
                  />
                  <input
                    type="text"
                    className="edvana-input"
                    placeholder="Search name, PRN, app ID..."
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                    style={{
                      paddingLeft: '36px',
                      borderRadius: '8px',
                      height: '38px',
                      fontSize: '0.8125rem',
                      borderColor: '#cbd5e1',
                      width: '100%',
                    }}
                  />
                </div>

                {/* Department Dropdown */}
                <select
                  className="edvana-input"
                  value={selectedDept}
                  onChange={(e) => setSelectedDept(e.target.value)}
                  style={{
                    flex: '0 1 180px',
                    height: '38px',
                    borderRadius: '8px',
                    fontSize: '0.8125rem',
                    borderColor: '#cbd5e1',
                    padding: '0 0.75rem',
                    color: '#334155',
                  }}
                >
                  <option value="">All Departments</option>
                  {departments.map((d) => (
                    <option key={d.id || d.code} value={d.code}>
                      {d.code} - {d.name}
                    </option>
                  ))}
                </select>

                {/* Fee Status Dropdown */}
                <select
                  className="edvana-input"
                  value={selectedFeeStatus}
                  onChange={(e) => setSelectedFeeStatus(e.target.value)}
                  style={{
                    flex: '0 1 150px',
                    height: '38px',
                    borderRadius: '8px',
                    fontSize: '0.8125rem',
                    borderColor: '#cbd5e1',
                    padding: '0 0.75rem',
                    color: '#334155',
                  }}
                >
                  <option value="">All Fee Statuses</option>
                  <option value="SET">Fee Set</option>
                  <option value="UNSET">Fee Pending (-)</option>
                  <option value="PAID">Paid / Marked</option>
                </select>

                {/* Academic Year Dropdown */}
                <select
                  className="edvana-input"
                  value={selectedYear}
                  onChange={(e) => setSelectedYear(e.target.value)}
                  style={{
                    flex: '0 1 160px',
                    height: '38px',
                    borderRadius: '8px',
                    fontSize: '0.8125rem',
                    borderColor: '#cbd5e1',
                    padding: '0 0.75rem',
                    color: '#334155',
                  }}
                >
                  <option value="">All Academic Years</option>
                  {academicYears.map((ay) => (
                    <option key={ay.id} value={ay.id}>{ay.code} {ay.is_current ? '(Current)' : ''}</option>
                  ))}
                </select>

                {/* Locked scope badge: ledger always shows HOD-verified eligible candidates */}
                <span
                  style={{
                    height: '38px',
                    padding: '0 0.85rem',
                    fontSize: '0.8125rem',
                    fontWeight: 600,
                    borderRadius: '8px',
                    border: '1px solid #16a34a',
                    backgroundColor: '#f0fdf4',
                    color: '#15803d',
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '0.4rem',
                    whiteSpace: 'nowrap',
                  }}
                  title="Locked: only HOD + class-teacher verified eligible candidates are listed here"
                >
                  <CheckCircle2 size={15} style={{ color: '#16a34a' }} />
                  <span>Eligible Candidates Only</span>
                </span>

                {/* Refresh Button */}
                <button
                  type="button"
                  onClick={() => fetchData(true)}
                  style={{
                    height: '38px',
                    width: '38px',
                    borderRadius: '8px',
                    border: '1px solid #cbd5e1',
                    background: '#ffffff',
                    color: '#475569',
                    display: 'inline-flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    cursor: 'pointer',
                    transition: 'all 0.15s ease',
                  }}
                  onMouseEnter={(e) => e.currentTarget.style.background = '#f8fafc'}
                  onMouseLeave={(e) => e.currentTarget.style.background = '#ffffff'}
                  title="Refresh Records"
                >
                  <RefreshCw size={15} className={refreshing ? 'animate-spin' : ''} />
                </button>
              </div>

              {/* Active Filter Results Notification Bar */}
              {hasActiveFilters && (
                <div style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  padding: '0.55rem 0.85rem',
                  marginBottom: '1rem',
                  background: '#eff6ff',
                  border: '1px solid #bfdbfe',
                  borderRadius: '8px',
                  fontSize: '0.8rem',
                  color: '#1e40af'
                }}>
                  <div>
                    Filters active: Showing <strong>{filteredStudents.length}</strong> matching candidates out of {students.length} total. (Page {currentPage} of {totalPages})
                  </div>
                  <button
                    type="button"
                    onClick={handleClearFilters}
                    style={{
                      background: 'transparent',
                      border: 'none',
                      color: '#1E60DC',
                      fontWeight: 700,
                      cursor: 'pointer',
                      fontSize: '0.78rem',
                      display: 'inline-flex',
                      alignItems: 'center',
                      gap: '0.25rem'
                    }}
                  >
                    <X size={13} />
                    <span>Clear Filters</span>
                  </button>
                </div>
              )}

              {/* Table Container */}
              {loading ? (
                <div style={{ padding: '4rem 2rem' }}>
                  <LoadingState message="Loading eligible student candidates..." />
                </div>
              ) : loadError ? (
                // A failed load must own the table region with an explicit
                // error + retry; the empty state below means "loaded fine,
                // genuinely zero matches" — never "the server was down".
                <div style={{ padding: '3.5rem 1rem' }}>
                  <ErrorState
                    title="Failed to Load Fee Desk"
                    message={loadError}
                    onRetry={() => fetchData()}
                  />
                </div>
              ) : filteredStudents.length === 0 ? (
                <div style={{ padding: '3.5rem 1rem' }}>
                  <EmptyState
                    title="No Eligible Candidates Found"
                    message="No candidate records matched your search or filter options."
                  />
                </div>
              ) : (
                <>
                  <div style={{ overflowX: 'auto', border: '1px solid #f1f5f9', borderRadius: '10px' }}>
                    <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left' }}>
                      <thead>
                        <tr style={{ background: '#f8fafc', borderBottom: '1px solid #e2e8f0' }}>
                          <th style={{ padding: '0.7rem 0.65rem', fontSize: '0.72rem', fontWeight: 700, color: '#475569', letterSpacing: '0.05em', width: '50px' }}>
                            S.N.
                          </th>
                          <th style={{ padding: '0.7rem 0.65rem', fontSize: '0.72rem', fontWeight: 700, color: '#475569', letterSpacing: '0.05em', width: '160px' }}>
                            PRN
                          </th>
                          <th style={{ padding: '0.7rem 0.65rem', fontSize: '0.72rem', fontWeight: 700, color: '#475569', letterSpacing: '0.05em', minWidth: '180px' }}>
                            NAME
                          </th>
                          <th style={{ padding: '0.7rem 0.65rem', fontSize: '0.72rem', fontWeight: 700, color: '#475569', letterSpacing: '0.05em', minWidth: '150px' }}>
                            FATHER'S NAME
                          </th>
                          <th style={{ padding: '0.7rem 0.65rem', fontSize: '0.72rem', fontWeight: 700, color: '#475569', letterSpacing: '0.05em', width: '120px' }}>
                            MOBILE
                          </th>
                          <th style={{ padding: '0.7rem 0.65rem', fontSize: '0.72rem', fontWeight: 700, color: '#475569', letterSpacing: '0.05em', textAlign: 'center', width: '145px' }}>
                            FEE MARKED / STATUS
                          </th>
                          <th style={{ padding: '0.7rem 0.65rem', fontSize: '0.72rem', fontWeight: 700, color: '#475569', letterSpacing: '0.05em', textAlign: 'center', minWidth: '230px' }}>
                            ACTIONS
                          </th>
                        </tr>
                      </thead>
                      <tbody>
                        {currentStudents.map((stu, index) => {
                          const feeInfo = feesMap[stu.id];
                          const isFeeSet = Boolean(feeInfo && feeInfo.totalFee > 0);
                          const feeAmount = isFeeSet ? feeInfo.totalFee : null;
                          // Paid fee is locked: Mark/Set Fee allowed only once (backend also blocks duplicates).
                          const isPaid = Boolean(feeInfo && feeInfo.isPaid);

                          // Never show fake sample data: missing values render as '—'.
                          // PRN is the full university enrollment number (never truncated).
                          const prn = stu.enrollment_no || '—';
                          // Semester is DB truth: StudentEnrollment(is_current=True).
                          // Promotion rewrites that row, so this updates everywhere on reload.
                          const semLabel = stu.semester_number ? `Sem ${stu.semester_number}` : '—';
                          const genderPart = (stu.gender || '').trim();
                          const deptPart = (stu.department_code || '').trim();
                          const genderDept = [genderPart.toUpperCase(), deptPart.toUpperCase()]
                            .filter(Boolean).join(' • ') || '—';

                          const isPinned = pinnedId && String(stu.id) === String(pinnedId);
                          return (
                            <tr
                              key={stu.id}
                              style={{
                                borderBottom: '1px solid #f1f5f9',
                                transition: 'background 0.15s ease',
                                background: isPinned ? '#f0fdf4' : '#ffffff',
                                boxShadow: isPinned ? 'inset 3px 0 0 #16a34a' : 'none',
                              }}
                              onMouseEnter={(e) => e.currentTarget.style.background = isPinned ? '#dcfce7' : '#f8fafc'}
                              onMouseLeave={(e) => e.currentTarget.style.background = isPinned ? '#f0fdf4' : '#ffffff'}
                            >
                              {/* S.N. (Paginated) */}
                              <td style={{ padding: '0.7rem 0.65rem', fontSize: '0.85rem', color: '#64748b', fontWeight: 500 }}>
                                {startIndex + index + 1}
                              </td>

                              {/* PRN */}
                              <td style={{ padding: '0.7rem 0.65rem' }}>
                                <div style={{ color: '#1E60DC', fontWeight: 700, fontSize: '0.78rem', fontFamily: 'monospace', whiteSpace: 'nowrap' }}>
                                  {prn}
                                </div>
                                <div style={{ color: '#64748b', fontSize: '0.75rem', fontFamily: 'monospace', marginTop: '0.15rem', whiteSpace: 'nowrap' }}>
                                  {semLabel}
                                </div>
                              </td>

                              {/* NAME */}
                              <td style={{ padding: '0.7rem 0.65rem' }}>
                                <div style={{ fontWeight: 700, color: '#0f172a', fontSize: '0.8rem', whiteSpace: 'nowrap' }}>
                                  {stu.display_name}
                                </div>
                                <div style={{ color: '#64748b', fontSize: '0.75rem', fontWeight: 500, marginTop: '0.15rem', textTransform: 'uppercase' }}>
                                  {genderDept}
                                </div>
                                {isPinned && (
                                  <div style={{
                                    display: 'inline-block',
                                    marginTop: '0.3rem',
                                    background: '#16a34a',
                                    color: '#ffffff',
                                    borderRadius: '9999px',
                                    padding: '0.1rem 0.6rem',
                                    fontSize: '0.68rem',
                                    fontWeight: 700,
                                  }}>
                                    Fee just set — ready to Mark Fee
                                  </div>
                                )}
                              </td>

                              {/* FATHER'S NAME */}
                              <td style={{ padding: '0.7rem 0.65rem', fontSize: '0.85rem', color: '#334155', fontWeight: 500, textTransform: 'uppercase' }}>
                                {stu.father_name || '—'}
                              </td>

                              {/* MOBILE */}
                              <td style={{ padding: '0.7rem 0.65rem', fontSize: '0.85rem', color: '#334155', fontFamily: 'monospace' }}>
                                {stu.mobile || '—'}
                              </td>

                              {/* FEE MARKED / STATUS */}
                              <td style={{ padding: '0.7rem 0.65rem', textAlign: 'center' }}>
                                {isFeeSet ? (
                                  <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '0.3rem' }}>
                                    <span style={{
                                      display: 'inline-block',
                                      background: isPaid ? '#f0fdf4' : '#eff6ff',
                                      color: isPaid ? '#15803d' : '#1E60DC',
                                      border: `1px solid ${isPaid ? '#bbf7d0' : '#bfdbfe'}`,
                                      borderRadius: '9999px',
                                      padding: '0.25rem 0.85rem',
                                      fontWeight: 700,
                                      fontSize: '0.8125rem',
                                    }}>
                                      ₹{feeAmount.toLocaleString('en-IN')}
                                    </span>
                                  </div>
                                ) : (
                                  <span style={{
                                    display: 'inline-block',
                                    background: '#f8fafc',
                                    color: '#94a3b8',
                                    border: '1px solid #e2e8f0',
                                    borderRadius: '9999px',
                                    padding: '0.25rem 0.85rem',
                                    fontWeight: 600,
                                    fontSize: '0.8125rem',
                                  }}>
                                    -
                                  </span>
                                )}
                              </td>

                              {/* ACTIONS (Single line, sleek elongated pill buttons with round 20px corners) */}
                              <td style={{ padding: '0.7rem 0.65rem', textAlign: 'center', whiteSpace: 'nowrap' }}>
                                <div style={{
                                  display: 'inline-flex',
                                  alignItems: 'center',
                                  justifyContent: 'center',
                                  gap: '0.45rem',
                                  whiteSpace: 'nowrap',
                                }}>
                                  {/* 1. Set Fee / Edit Fee — locked once paid */}
                                  {isPaid ? (
                                    <button
                                      type="button"
                                      disabled
                                      style={{
                                        background: '#f0fdf4',
                                        color: '#15803d',
                                        border: '1px solid #bbf7d0',
                                        borderRadius: '20px',
                                        padding: '0 0.7rem',
                                        height: '30px',
                                        fontSize: '0.75rem',
                                        fontWeight: 600,
                                        cursor: 'not-allowed',
                                        whiteSpace: 'nowrap',
                                        display: 'inline-flex',
                                        alignItems: 'center',
                                        justifyContent: 'center',
                                        opacity: 0.9
                                      }}
                                      title="Fee already paid — locked. Duplicate marking blocked."
                                    >
                                      <span>Paid ✓</span>
                                    </button>
                                  ) : isFeeSet ? (
                                    /* When fee IS set: changes to gray and white */
                                    <button
                                      type="button"
                                      onClick={() => navigate(`/finance/set-fee/${stu.id}`)}
                                      style={{
                                        background: '#ffffff',
                                        color: '#475569',
                                        border: '1px solid #cbd5e1',
                                        borderRadius: '20px',
                                        padding: '0 0.7rem',
                                        height: '30px',
                                        fontSize: '0.75rem',
                                        fontWeight: 600,
                                        cursor: 'pointer',
                                        whiteSpace: 'nowrap',
                                        display: 'inline-flex',
                                        alignItems: 'center',
                                        justifyContent: 'center',
                                        transition: 'all 0.15s ease'
                                      }}
                                      onMouseEnter={(e) => {
                                        e.currentTarget.style.borderColor = '#1E60DC';
                                        e.currentTarget.style.color = '#1E60DC';
                                        e.currentTarget.style.background = '#f0f7ff';
                                      }}
                                      onMouseLeave={(e) => {
                                        e.currentTarget.style.borderColor = '#cbd5e1';
                                        e.currentTarget.style.color = '#475569';
                                        e.currentTarget.style.background = '#ffffff';
                                      }}
                                      title="Edit fee assessment for this candidate"
                                    >
                                      <span>Edit Fee</span>
                                    </button>
                                  ) : (
                                    /* When fee is NOT set: blue #1E60DC with white text */
                                    <button
                                      type="button"
                                      onClick={() => navigate(`/finance/set-fee/${stu.id}`)}
                                      style={{
                                        background: '#1E60DC',
                                        color: '#ffffff',
                                        border: 'none',
                                        borderRadius: '20px',
                                        padding: '0 0.75rem',
                                        height: '30px',
                                        fontSize: '0.75rem',
                                        fontWeight: 600,
                                        cursor: 'pointer',
                                        whiteSpace: 'nowrap',
                                        display: 'inline-flex',
                                        alignItems: 'center',
                                        justifyContent: 'center',
                                        boxShadow: '0 1px 2px rgba(58, 129, 246, 0.25)',
                                        transition: 'background 0.15s ease'
                                      }}
                                      onMouseEnter={(e) => e.currentTarget.style.background = '#2563eb'}
                                      onMouseLeave={(e) => e.currentTarget.style.background = '#1E60DC'}
                                      title="Configure admission fee for this candidate"
                                    >
                                      <span>Set Fee</span>
                                    </button>
                                  )}

                                  {/* 2. Mark Fee Button — disabled once paid */}
                                  {isPaid ? (
                                    <button
                                      type="button"
                                      disabled
                                      style={{
                                        background: '#f0fdf4',
                                        color: '#15803d',
                                        border: '1px solid #bbf7d0',
                                        borderRadius: '20px',
                                        padding: '0 0.7rem',
                                        height: '30px',
                                        fontSize: '0.75rem',
                                        fontWeight: 600,
                                        cursor: 'not-allowed',
                                        whiteSpace: 'nowrap',
                                        display: 'inline-flex',
                                        alignItems: 'center',
                                        justifyContent: 'center',
                                        gap: '0.35rem',
                                        opacity: 0.9
                                      }}
                                      title="Fee already marked paid. Duplicate payment blocked."
                                    >
                                      <CheckCircle2 size={12} />
                                      <span>Paid ✓</span>
                                    </button>
                                  ) : isFeeSet ? (
                                    /* When fee IS set: unlocked and blue #1E60DC */
                                    <button
                                      type="button"
                                      onClick={() => handleOpenMarkFee(stu)}
                                      style={{
                                        background: '#1E60DC',
                                        color: '#ffffff',
                                        border: 'none',
                                        borderRadius: '20px',
                                        padding: '0 0.7rem',
                                        height: '30px',
                                        fontSize: '0.75rem',
                                        fontWeight: 600,
                                        cursor: 'pointer',
                                        whiteSpace: 'nowrap',
                                        display: 'inline-flex',
                                        alignItems: 'center',
                                        justifyContent: 'center',
                                        gap: '0.35rem',
                                        boxShadow: '0 1px 2px rgba(58, 129, 246, 0.25)',
                                        transition: 'background 0.15s ease'
                                      }}
                                      onMouseEnter={(e) => e.currentTarget.style.background = '#2563eb'}
                                      onMouseLeave={(e) => e.currentTarget.style.background = '#1E60DC'}
                                      title="Record payment and mark admission fee"
                                    >
                                      <FileText size={12} />
                                      <span>Mark Fee</span>
                                    </button>
                                  ) : (
                                    /* When fee is NOT set: locked in gray and white */
                                    <button
                                      type="button"
                                      disabled
                                      style={{
                                        background: '#f8fafc',
                                        color: '#94a3b8',
                                        border: '1px solid #e2e8f0',
                                        borderRadius: '20px',
                                        padding: '0 0.7rem',
                                        height: '30px',
                                        fontSize: '0.75rem',
                                        fontWeight: 600,
                                        cursor: 'not-allowed',
                                        whiteSpace: 'nowrap',
                                        display: 'inline-flex',
                                        alignItems: 'center',
                                        justifyContent: 'center',
                                        gap: '0.35rem',
                                        opacity: 0.85
                                      }}
                                      title="Fee not set yet. Click 'Set Fee' first to unlock."
                                    >
                                      <Lock size={11} style={{ color: '#94a3b8' }} />
                                      <span>Mark Fee</span>
                                    </button>
                                  )}

                                  {/* 3. Print Receipt Button (fee marked = receipt printable) */}
                                  {isPaid ? (
                                    <button
                                      type="button"
                                      onClick={() => handleOpenReceipt(stu)}
                                      style={{
                                        background: '#15803d',
                                        color: '#ffffff',
                                        border: 'none',
                                        borderRadius: '20px',
                                        padding: '0 0.55rem',
                                        height: '30px',
                                        fontSize: '0.75rem',
                                        fontWeight: 600,
                                        cursor: 'pointer',
                                        whiteSpace: 'nowrap',
                                        display: 'inline-flex',
                                        alignItems: 'center',
                                        justifyContent: 'center',
                                        gap: '0.3rem',
                                        transition: 'background 0.15s ease'
                                      }}
                                      onMouseEnter={(e) => e.currentTarget.style.background = '#166534'}
                                      onMouseLeave={(e) => e.currentTarget.style.background = '#15803d'}
                                      title="Print / download the official fee receipt"
                                    >
                                      <Printer size={14} />
                                    </button>
                                  ) : (
                                    <button
                                      type="button"
                                      disabled
                                      style={{
                                        background: '#f8fafc',
                                        color: '#94a3b8',
                                        border: '1px solid #e2e8f0',
                                        borderRadius: '20px',
                                        padding: '0 0.55rem',
                                        height: '30px',
                                        fontSize: '0.75rem',
                                        fontWeight: 600,
                                        cursor: 'not-allowed',
                                        whiteSpace: 'nowrap',
                                        display: 'inline-flex',
                                        alignItems: 'center',
                                        justifyContent: 'center',
                                        gap: '0.3rem',
                                        opacity: 0.85
                                      }}
                                      title="Receipt unlocks once the fee is marked paid."
                                    >
                                      <Lock size={12} style={{ color: '#94a3b8' }} />
                                    </button>
                                  )}
                                </div>
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>

                  {/* Pagination Controls Bar (20 candidates per page) */}
                  <div style={{
                    display: 'flex',
                    flexWrap: 'wrap',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    gap: '1rem',
                    padding: '1rem 0.25rem 0.25rem 0.25rem',
                    borderTop: '1px solid #f1f5f9',
                    marginTop: '0.75rem'
                  }}>
                    <div style={{ fontSize: '0.8125rem', color: '#64748b', fontWeight: 500 }}>
                      Showing <strong style={{ color: '#0f172a' }}>{startIndex + 1}</strong> to <strong style={{ color: '#0f172a' }}>{endIndex}</strong> of <strong style={{ color: '#0f172a' }}>{filteredStudents.length}</strong> candidates
                      {hasActiveFilters && (
                        <span style={{ marginLeft: '0.35rem', color: '#94a3b8' }}>
                          (filtered from {students.length} total)
                        </span>
                      )}
                    </div>

                    {totalPages > 1 && (
                      <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
                        <button
                          type="button"
                          disabled={currentPage === 1}
                          onClick={() => setCurrentPage(prev => Math.max(prev - 1, 1))}
                          style={{
                            height: '32px',
                            padding: '0 0.85rem',
                            borderRadius: '20px',
                            border: '1px solid #e2e8f0',
                            background: currentPage === 1 ? '#f8fafc' : '#ffffff',
                            color: currentPage === 1 ? '#cbd5e1' : '#334155',
                            fontSize: '0.75rem',
                            fontWeight: 600,
                            cursor: currentPage === 1 ? 'not-allowed' : 'pointer',
                            display: 'inline-flex',
                            alignItems: 'center',
                            gap: '0.25rem',
                            transition: 'all 0.15s ease'
                          }}
                        >
                          <ChevronLeft size={14} />
                          <span>Previous</span>
                        </button>

                        {Array.from({ length: totalPages }, (_, i) => i + 1).map(pageNum => {
                          if (
                            pageNum === 1 || 
                            pageNum === totalPages || 
                            (pageNum >= currentPage - 1 && pageNum <= currentPage + 1)
                          ) {
                            const isActive = pageNum === currentPage;
                            return (
                              <button
                                key={pageNum}
                                type="button"
                                onClick={() => setCurrentPage(pageNum)}
                                style={{
                                  height: '32px',
                                  minWidth: '32px',
                                  padding: '0 0.5rem',
                                  borderRadius: '20px',
                                  border: isActive ? '1px solid #1E60DC' : '1px solid #e2e8f0',
                                  background: isActive ? '#1E60DC' : '#ffffff',
                                  color: isActive ? '#ffffff' : '#475569',
                                  fontSize: '0.75rem',
                                  fontWeight: 700,
                                  cursor: 'pointer',
                                  transition: 'all 0.15s ease'
                                }}
                              >
                                {pageNum}
                              </button>
                            );
                          } else if (
                            (pageNum === currentPage - 2 && pageNum > 1) ||
                            (pageNum === currentPage + 2 && pageNum < totalPages)
                          ) {
                            return (
                              <span key={pageNum} style={{ padding: '0 0.25rem', color: '#94a3b8', fontSize: '0.75rem' }}>
                                ...
                              </span>
                            );
                          }
                          return null;
                        })}

                        <button
                          type="button"
                          disabled={currentPage >= totalPages}
                          onClick={() => setCurrentPage(prev => Math.min(prev + 1, totalPages))}
                          style={{
                            height: '32px',
                            padding: '0 0.85rem',
                            borderRadius: '20px',
                            border: '1px solid #e2e8f0',
                            background: currentPage >= totalPages ? '#f8fafc' : '#ffffff',
                            color: currentPage >= totalPages ? '#cbd5e1' : '#334155',
                            fontSize: '0.75rem',
                            fontWeight: 600,
                            cursor: currentPage >= totalPages ? 'not-allowed' : 'pointer',
                            display: 'inline-flex',
                            alignItems: 'center',
                            gap: '0.25rem',
                            transition: 'all 0.15s ease'
                          }}
                        >
                          <span>Next</span>
                          <ChevronRight size={14} />
                        </button>
                      </div>
                    )}
                  </div>
                </>
              )}
            </div>
          ) : (
            /* Online Payment Tracker View */
            <div key="online_tracker" className="animate-fade-up">
              {/* Tracker Controls & KPI Bar */}
              <div style={{
                display: 'flex',
                flexWrap: 'wrap',
                gap: '0.75rem',
                alignItems: 'center',
                justifyContent: 'space-between',
                backgroundColor: '#ffffff',
                padding: '0.5rem 0 1.25rem 0',
                borderBottom: '1px solid #f1f5f9',
                marginBottom: '1.25rem'
              }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', flex: '1 1 320px', minWidth: '240px' }}>
                  <div style={{ position: 'relative', width: '100%', maxWidth: '380px' }}>
                    <Search
                      size={16}
                      style={{
                        position: 'absolute',
                        left: '12px',
                        top: '50%',
                        transform: 'translateY(-50%)',
                        color: '#94a3b8',
                      }}
                    />
                    <input
                      type="text"
                      className="edvana-input"
                      placeholder="Search candidate, PRN, or Easebuzz ID..."
                      value={trackerSearch}
                      onChange={(e) => setTrackerSearch(e.target.value)}
                      style={{
                        paddingLeft: '36px',
                        borderRadius: '8px',
                        height: '38px',
                        fontSize: '0.8125rem',
                        borderColor: '#cbd5e1',
                        width: '100%',
                      }}
                    />
                  </div>

                  <button
                    type="button"
                    onClick={() => setTrackerOnlyOnline(!trackerOnlyOnline)}
                    style={{
                      height: '38px',
                      padding: '0 0.85rem',
                      fontSize: '0.8125rem',
                      fontWeight: 600,
                      borderRadius: '8px',
                      border: trackerOnlyOnline ? '1px solid #16a34a' : '1px solid #cbd5e1',
                      backgroundColor: trackerOnlyOnline ? '#f0fdf4' : '#ffffff',
                      color: trackerOnlyOnline ? '#15803d' : '#64748b',
                      display: 'inline-flex',
                      alignItems: 'center',
                      gap: '0.4rem',
                      cursor: 'pointer',
                      whiteSpace: 'nowrap',
                      transition: 'all 0.15s ease',
                    }}
                    title={trackerOnlyOnline ? 'Showing only candidates with online payment enabled' : 'Showing all assessed candidates'}
                  >
                    <Globe size={15} style={{ color: trackerOnlyOnline ? '#16a34a' : '#94a3b8' }} />
                    <span>{trackerOnlyOnline ? 'Online Enabled Only' : 'All Assessed'}</span>
                  </button>
                </div>

                {/* KPI Counters */}
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.625rem', flexWrap: 'wrap' }}>
                  <div style={{
                    background: '#f8fafc',
                    border: '1px solid #e2e8f0',
                    borderRadius: '8px',
                    padding: '0.35rem 0.75rem',
                    fontSize: '0.75rem',
                    color: '#475569'
                  }}>
                    Total Monitored: <strong style={{ color: '#0f172a' }}>{trackerData.length}</strong>
                  </div>
                  <div style={{
                    background: '#f0fdf4',
                    border: '1px solid #bbf7d0',
                    borderRadius: '8px',
                    padding: '0.35rem 0.75rem',
                    fontSize: '0.75rem',
                    color: '#166534'
                  }}>
                    Online Allowed: <strong style={{ color: '#15803d' }}>{trackerData.filter(d => d.allow_online_payment).length}</strong>
                  </div>
                  <div style={{
                    background: '#eff6ff',
                    border: '1px solid #bfdbfe',
                    borderRadius: '8px',
                    padding: '0.35rem 0.75rem',
                    fontSize: '0.75rem',
                    color: '#1e40af'
                  }}>
                    Paid: <strong style={{ color: '#1d4ed8' }}>{trackerData.filter(d => d.is_paid).length}</strong>
                  </div>
                </div>
              </div>

              {/* Table View */}
              {loadingTracker ? (
                <div style={{ padding: '4rem 2rem' }}>
                  <LoadingState message="Loading online payment statuses and gateway records..." />
                </div>
              ) : trackerData.length === 0 ? (
                <div style={{ padding: '3.5rem 1rem' }}>
                  <EmptyState
                    title="No Online Payment Records Found"
                    message={trackerSearch ? "No records match your search criteria." : "No candidates have been enabled for online payment gateway yet."}
                  />
                </div>
              ) : (
                <div style={{ overflowX: 'auto', border: '1px solid #f1f5f9', borderRadius: '10px' }}>
                  <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left' }}>
                    <thead>
                      <tr style={{ background: '#f8fafc', borderBottom: '1px solid #e2e8f0' }}>
                        <th style={{ padding: '0.7rem 0.65rem', fontSize: '0.72rem', fontWeight: 700, color: '#475569', letterSpacing: '0.05em', width: '50px' }}>
                          S.N.
                        </th>
                        <th style={{ padding: '0.7rem 0.65rem', fontSize: '0.72rem', fontWeight: 700, color: '#475569', letterSpacing: '0.05em', minWidth: '220px' }}>
                          CANDIDATE / ENROLLMENT
                        </th>
                        <th style={{ padding: '0.7rem 0.65rem', fontSize: '0.72rem', fontWeight: 700, color: '#475569', letterSpacing: '0.05em', width: '140px', textAlign: 'center' }}>
                          ASSESSED FEE
                        </th>
                        <th style={{ padding: '0.7rem 0.65rem', fontSize: '0.72rem', fontWeight: 700, color: '#475569', letterSpacing: '0.05em', width: '170px', textAlign: 'center' }}>
                          GATEWAY PERMISSION
                        </th>
                        <th style={{ padding: '0.7rem 0.65rem', fontSize: '0.72rem', fontWeight: 700, color: '#475569', letterSpacing: '0.05em', minWidth: '180px' }}>
                          GATEWAY STATUS
                        </th>
                        <th style={{ padding: '0.7rem 0.65rem', fontSize: '0.72rem', fontWeight: 700, color: '#475569', letterSpacing: '0.05em', minWidth: '180px' }}>
                          TRANSACTION DETAILS
                        </th>
                        <th style={{ padding: '0.7rem 0.65rem', fontSize: '0.72rem', fontWeight: 700, color: '#475569', letterSpacing: '0.05em', textAlign: 'center', width: '150px' }}>
                          ACTIONS
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {trackerData.map((row, idx) => {
                        const attempt = row.latest_attempt;
                        const isPaid = Boolean(row.is_paid);
                        const feeNum = parseFloat(row.total_fee || 0);
                        const isToggling = togglingStudentId === row.student;
                        const isReconciling = reconcilingTxnId === attempt?.id;

                        return (
                          <tr
                            key={row.id}
                            style={{
                              borderBottom: '1px solid #f1f5f9',
                              transition: 'background 0.15s ease'
                            }}
                            onMouseEnter={(e) => e.currentTarget.style.background = '#f8fafc'}
                            onMouseLeave={(e) => e.currentTarget.style.background = '#ffffff'}
                          >
                            <td style={{ padding: '0.7rem 0.65rem', fontSize: '0.85rem', color: '#64748b', fontWeight: 500 }}>
                              {idx + 1}
                            </td>

                            <td style={{ padding: '0.7rem 0.65rem' }}>
                              <div style={{ fontWeight: 700, color: '#0f172a', fontSize: '0.875rem' }}>
                                {row.student_name}
                              </div>
                              <div style={{ color: '#64748b', fontSize: '0.75rem', fontFamily: 'monospace', marginTop: '0.15rem' }}>
                                PRN: {row.enrollment_no || '—'} • {row.department_name || '—'}
                              </div>
                            </td>

                            <td style={{ padding: '0.7rem 0.65rem', textAlign: 'center' }}>
                              <span style={{
                                display: 'inline-block',
                                background: '#eff6ff',
                                color: '#1E60DC',
                                border: '1px solid #bfdbfe',
                                borderRadius: '9999px',
                                padding: '0.25rem 0.85rem',
                                fontWeight: 700,
                                fontSize: '0.8125rem',
                              }}>
                                ₹{feeNum.toLocaleString('en-IN')}
                              </span>
                            </td>

                            {/* GATEWAY PERMISSION TOGGLE (Accountant can edit tick directly here!) */}
                            <td style={{ padding: '0.7rem 0.65rem', textAlign: 'center' }}>
                              {isPaid ? (
                                <span style={{
                                  display: 'inline-flex',
                                  alignItems: 'center',
                                  gap: '0.25rem',
                                  background: '#f0fdf4',
                                  color: '#15803d',
                                  border: '1px solid #bbf7d0',
                                  borderRadius: '9999px',
                                  padding: '0.2rem 0.65rem',
                                  fontSize: '0.72rem',
                                  fontWeight: 700,
                                }}>
                                  <CheckCircle2 size={12} />
                                  <span>Paid ✓</span>
                                </span>
                              ) : row.allow_online_payment ? (
                                <button
                                  type="button"
                                  disabled={isToggling}
                                  onClick={() => handleToggleOnline(row.student, row.id, true)}
                                  title="Online payment enabled. Click to toggle OFF (switch to counter only)."
                                  style={{
                                    display: 'inline-flex',
                                    alignItems: 'center',
                                    gap: '0.3rem',
                                    background: '#f0fdf4',
                                    color: '#166534',
                                    border: '1px solid #86efac',
                                    borderRadius: '9999px',
                                    padding: '0.25rem 0.75rem',
                                    fontSize: '0.72rem',
                                    fontWeight: 700,
                                    cursor: isToggling ? 'wait' : 'pointer',
                                    transition: 'all 0.15s ease',
                                    boxShadow: '0 1px 2px rgba(22, 101, 52, 0.08)'
                                  }}
                                >
                                  <Globe size={12} style={{ color: '#16a34a' }} />
                                  <span>{isToggling ? 'Saving...' : 'Enabled ✓'}</span>
                                </button>
                              ) : (
                                <button
                                  type="button"
                                  disabled={isToggling}
                                  onClick={() => handleToggleOnline(row.student, row.id, false)}
                                  title="Counter only. Click to toggle ON (allow Easebuzz online payment)."
                                  style={{
                                    display: 'inline-flex',
                                    alignItems: 'center',
                                    gap: '0.3rem',
                                    background: '#f8fafc',
                                    color: '#64748b',
                                    border: '1px solid #cbd5e1',
                                    borderRadius: '9999px',
                                    padding: '0.25rem 0.75rem',
                                    fontSize: '0.72rem',
                                    fontWeight: 600,
                                    cursor: isToggling ? 'wait' : 'pointer',
                                    transition: 'all 0.15s ease'
                                  }}
                                >
                                  <span>{isToggling ? 'Saving...' : 'Counter Only'}</span>
                                </button>
                              )}
                            </td>

                            {/* GATEWAY STATUS */}
                            <td style={{ padding: '0.7rem 0.65rem' }}>
                              {isPaid ? (
                                <div>
                                  <span style={{
                                    display: 'inline-flex',
                                    alignItems: 'center',
                                    gap: '0.25rem',
                                    background: '#dcfce7',
                                    color: '#15803d',
                                    border: '1px solid #86efac',
                                    borderRadius: '9999px',
                                    padding: '0.15rem 0.6rem',
                                    fontSize: '0.72rem',
                                    fontWeight: 800,
                                  }}>
                                    <CheckCircle2 size={12} />
                                    <span>SUCCESS / PAID</span>
                                  </span>
                                  {row.receipt_no && (
                                    <div style={{ fontSize: '0.72rem', color: '#166534', fontFamily: 'monospace', marginTop: '0.2rem', fontWeight: 600 }}>
                                      Receipt: {row.receipt_no}
                                    </div>
                                  )}
                                </div>
                              ) : attempt ? (
                                <div>
                                  {attempt.status === 'SUCCESS' ? (
                                    <span style={{
                                      display: 'inline-flex',
                                      alignItems: 'center',
                                      gap: '0.25rem',
                                      background: '#dcfce7',
                                      color: '#15803d',
                                      border: '1px solid #86efac',
                                      borderRadius: '9999px',
                                      padding: '0.15rem 0.6rem',
                                      fontSize: '0.72rem',
                                      fontWeight: 800,
                                    }}>
                                      <CheckCircle2 size={12} />
                                      <span>SUCCESS</span>
                                    </span>
                                  ) : ['PENDING', 'REDIRECTED', 'INITIATED'].includes(attempt.status) ? (
                                    <span style={{
                                      display: 'inline-flex',
                                      alignItems: 'center',
                                      gap: '0.25rem',
                                      background: '#fef3c7',
                                      color: '#b45309',
                                      border: '1px solid #fde68a',
                                      borderRadius: '9999px',
                                      padding: '0.15rem 0.6rem',
                                      fontSize: '0.72rem',
                                      fontWeight: 800,
                                    }}>
                                      <RefreshCw size={11} className="animate-spin" />
                                      <span>{attempt.status_display || attempt.status}</span>
                                    </span>
                                  ) : (
                                    <span style={{
                                      display: 'inline-flex',
                                      alignItems: 'center',
                                      gap: '0.25rem',
                                      background: '#fee2e2',
                                      color: '#b91c1c',
                                      border: '1px solid #fecaca',
                                      borderRadius: '9999px',
                                      padding: '0.15rem 0.6rem',
                                      fontSize: '0.72rem',
                                      fontWeight: 800,
                                    }}>
                                      <AlertCircle size={12} />
                                      <span>{attempt.status_display || attempt.status}</span>
                                    </span>
                                  )}
                                  <div style={{ fontSize: '0.7rem', color: '#64748b', marginTop: '0.2rem' }}>
                                    Mode: {attempt.payment_mode || 'GATEWAY'}
                                  </div>
                                </div>
                              ) : (
                                <span style={{
                                  display: 'inline-block',
                                  background: '#f8fafc',
                                  color: '#94a3b8',
                                  border: '1px solid #e2e8f0',
                                  borderRadius: '9999px',
                                  padding: '0.15rem 0.55rem',
                                  fontSize: '0.72rem',
                                  fontWeight: 600,
                                }}>
                                  Not Attempted
                                </span>
                              )}
                            </td>

                            {/* TRANSACTION DETAILS */}
                            <td style={{ padding: '0.7rem 0.65rem' }}>
                              {attempt ? (
                                <div>
                                  {attempt.easebuzz_txn_id && (
                                    <div style={{ fontSize: '0.75rem', fontFamily: 'monospace', fontWeight: 600, color: '#0f172a' }}>
                                      EB: {attempt.easebuzz_txn_id}
                                    </div>
                                  )}
                                  <div style={{ fontSize: '0.72rem', fontFamily: 'monospace', color: '#64748b' }}>
                                    Ref: {attempt.transaction_id}
                                  </div>
                                  {attempt.initiated_at && (
                                    <div style={{ fontSize: '0.68rem', color: '#94a3b8', marginTop: '0.15rem' }}>
                                      {new Date(attempt.initiated_at).toLocaleString('en-IN', {
                                        day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit'
                                      })}
                                    </div>
                                  )}
                                </div>
                              ) : (
                                <span style={{ color: '#94a3b8', fontSize: '0.8rem' }}>—</span>
                              )}
                            </td>

                            {/* ACTIONS */}
                            <td style={{ padding: '0.7rem 0.65rem', textAlign: 'center', whiteSpace: 'nowrap' }}>
                              <div style={{ display: 'inline-flex', alignItems: 'center', gap: '0.4rem' }}>
                                {attempt && ['PENDING', 'REDIRECTED', 'INITIATED'].includes(attempt.status) && (
                                  <button
                                    type="button"
                                    disabled={isReconciling}
                                    onClick={() => handleReconcileAttempt(attempt.id)}
                                    style={{
                                      height: '28px',
                                      padding: '0 0.75rem',
                                      fontSize: '0.72rem',
                                      fontWeight: 600,
                                      borderRadius: '16px',
                                      border: '1px solid #bfdbfe',
                                      background: '#eff6ff',
                                      color: '#1E60DC',
                                      cursor: isReconciling ? 'wait' : 'pointer',
                                      display: 'inline-flex',
                                      alignItems: 'center',
                                      gap: '0.3rem',
                                      transition: 'all 0.15s ease'
                                    }}
                                    title="Inquire transaction status directly with Easebuzz bank servers"
                                  >
                                    <RotateCcw size={11} className={isReconciling ? 'animate-spin' : ''} />
                                    <span>{isReconciling ? 'Verifying...' : 'Verify Bank'}</span>
                                  </button>
                                )}

                                <button
                                  type="button"
                                  onClick={() => navigate(`/finance/set-fee/${row.student}`)}
                                  style={{
                                    height: '28px',
                                    padding: '0 0.75rem',
                                    fontSize: '0.72rem',
                                    fontWeight: 600,
                                    borderRadius: '16px',
                                    border: '1px solid #cbd5e1',
                                    background: '#ffffff',
                                    color: '#475569',
                                    cursor: 'pointer',
                                    display: 'inline-flex',
                                    alignItems: 'center',
                                    gap: '0.25rem',
                                    transition: 'all 0.15s ease'
                                  }}
                                  title="Configure admission fee & online payment settings"
                                >
                                  <span>Edit Fee</span>
                                </button>
                              </div>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Mark Fee Payment Modal */}
      {showMarkModal && markingStudent && (
        <Modal
          isOpen={showMarkModal}
          onClose={() => setShowMarkModal(false)}
          title={`Mark Fee Collection: ${markingStudent.display_name}`}
          maxWidth="540px"
        >
          <form onSubmit={handleSubmitMarkFee} style={{ padding: '0.5rem 0' }}>
            <div style={{ background: '#f8fafc', padding: '1rem', borderRadius: '10px', border: '1px solid #e2e8f0', marginBottom: '1.25rem' }}>
              <div style={{ fontSize: '0.8rem', color: '#64748b', fontWeight: 600 }}>CANDIDATE</div>
              <div style={{ fontSize: '1rem', fontWeight: 700, color: '#0f172a' }}>{markingStudent.display_name}</div>
              <div style={{ fontSize: '0.8rem', color: '#475569', marginTop: '0.2rem', fontFamily: 'monospace' }}>
                PRN: {markingStudent.enrollment_no || '—'} • App ID: {markingStudent.application_id || '—'} • Dept: {markingStudent.department_code || '—'}
              </div>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', marginBottom: '1rem' }}>
              <FormField label="Assessed Fee (₹) — fixed" required>
                <input
                  type="text"
                  readOnly
                  disabled
                  value={Number(markForm.amountPaid || 0).toLocaleString('en-IN')}
                  className="edvana-input"
                  style={{ width: '100%', fontWeight: 700, fontSize: '1.05rem', color: '#15803d', background: '#f8fafc' }}
                />
              </FormField>

              <FormField label="Payment Mode" required>
                <select
                  value={markForm.paymentMode}
                  onChange={(e) => setMarkForm({ ...markForm, paymentMode: e.target.value })}
                  className="edvana-input"
                  style={{ width: '100%', height: '42px', fontWeight: 500 }}
                >
                  <option value="ONLINE">Online Gateway / UPI</option>
                  <option value="DD">Demand Draft (DD)</option>
                  <option value="CHALLAN">Bank Challan</option>
                  <option value="CASH">Cash Counter</option>
                  <option value="NEFT">NEFT / RTGS Transfer</option>
                </select>
              </FormField>
            </div>

            <div style={{ marginBottom: '1rem' }}>
              <FormField label="Transaction Ref / Bank Challan No">
                <input
                  type="text"
                  placeholder="e.g. UPI-99882211 or DD-445566"
                  value={markForm.transactionRef}
                  onChange={(e) => setMarkForm({ ...markForm, transactionRef: e.target.value })}
                  className="edvana-input"
                  style={{ width: '100%', fontFamily: 'monospace' }}
                />
              </FormField>
            </div>

            <div style={{ marginBottom: '1.5rem' }}>
              <FormField label="Remarks">
                <input
                  type="text"
                  value={markForm.remarks}
                  onChange={(e) => setMarkForm({ ...markForm, remarks: e.target.value })}
                  className="edvana-input"
                  style={{ width: '100%' }}
                />
              </FormField>
            </div>

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem', borderTop: '1px solid #f1f5f9', paddingTop: '1.25rem' }}>
              <button
                type="button"
                onClick={() => setShowMarkModal(false)}
                className="edvana-btn edvana-btn-secondary"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={submittingPayment}
                style={{
                  background: '#15803d',
                  color: '#ffffff',
                  border: 'none',
                  borderRadius: '8px',
                  padding: '0.55rem 1.35rem',
                  fontSize: '0.85rem',
                  fontWeight: 600,
                  cursor: 'pointer',
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '0.45rem'
                }}
              >
                <CheckCircle2 size={16} />
                <span>{submittingPayment ? 'Recording...' : 'Record Payment & Mark Fee'}</span>
              </button>
            </div>
          </form>
        </Modal>
      )}

      {/* Official Fee Receipt PDF (fee-desk-only printing) */}
      <FeeReceiptPdfModal
        isOpen={showReceiptModal}
        onClose={() => setShowReceiptModal(false)}
        record={receiptRecord}
        loadingRecord={loadingReceipt}
        studentName={receiptStudent?.display_name || ''}
        lookupError={receiptLookupError}
      />

    </>
  );
}
