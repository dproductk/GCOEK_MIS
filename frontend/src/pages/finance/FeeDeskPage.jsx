import React, { useState, useEffect } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { 
  Search, RefreshCw, FileText, History, 
  CheckCircle2, AlertCircle, X, Users, ChevronLeft, ChevronRight, Lock
} from 'lucide-react';
import studentApi from '../../api/studentApi';
import financeApi from '../../api/financeApi';
import academicApi from '../../api/academicApi';
import PageHeader from '../../components/common/PageHeader';
import Modal from '../../components/common/Modal';
import FormField from '../../components/common/FormField';
import { LoadingState, EmptyState } from '../../components/common/StateDisplays';

export default function FeeDeskPage() {
  const navigate = useNavigate();
  const location = useLocation();

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

  // Filters (matching StudentDirectoryPage layout)
  const [search, setSearch] = useState('');
  const [selectedDept, setSelectedDept] = useState('');
  const [selectedFeeStatus, setSelectedFeeStatus] = useState('');
  const [selectedYear, setSelectedYear] = useState('');
  const [onlyEligible, setOnlyEligible] = useState(true);

  // Pagination State (20 candidates per page)
  const PAGE_SIZE = 20;
  const [currentPage, setCurrentPage] = useState(1);

  // Local fees map { [studentId]: { totalFee, isSet, breakdown } }
  const [feesMap, setFeesMap] = useState({});

  // Reset to first page when any filter criteria changes
  useEffect(() => {
    setCurrentPage(1);
  }, [search, selectedDept, selectedFeeStatus, selectedYear, onlyEligible]);

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

  // History Modal State
  const [showHistoryModal, setShowHistoryModal] = useState(false);
  const [historyStudent, setHistoryStudent] = useState(null);
  const [paymentRecords, setPaymentRecords] = useState([]);
  const [loadingHistory, setLoadingHistory] = useState(false);

  useEffect(() => {
    if (location.state?.successMsg) {
      setSuccessMsg(location.state.successMsg);
      // Clear state in history so toast doesn't re-appear on reload
      window.history.replaceState({}, document.title);
      const timer = setTimeout(() => setSuccessMsg(''), 4500);
      return () => clearTimeout(timer);
    }
  }, [location.state]);

  const fetchData = async (isManual = false) => {
    if (isManual) setRefreshing(true);
    else setLoading(true);
    setError(null);

    try {
      // Fee status comes from the backend ledger only: assessments say a
      // fee was set, payment rows say it was paid. No browser storage.
      const [stuRes, deptsRes, yearsRes, ledgerRes, assessRes] = await Promise.allSettled([
        studentApi.getStudents({ 
          search: search.trim() || undefined, 
          page_size: 100,
          eligible_only: onlyEligible ? 'true' : undefined,
        }),
        academicApi.getDepartments(),
        academicApi.getAcademicYears(),
        financeApi.getPaymentLedgers(),
        financeApi.getAssessments()
      ]);

      if (stuRes.status === 'fulfilled') {
        const rawStu = stuRes.value.data?.results || stuRes.value.data || [];
        setStudents(rawStu);
        setTotalCandidates(
          stuRes.value.data?.count ?? (Array.isArray(rawStu) ? rawStu.length : 0)
        );
      }

      if (deptsRes.status === 'fulfilled') {
        const rawDepts = deptsRes.value.data?.results || deptsRes.value.data || [];
        setDepartments(rawDepts);
      }

      if (yearsRes.status === 'fulfilled') {
        const rawYears = yearsRes.value.data?.results || yearsRes.value.data || [];
        setAcademicYears(rawYears);
      }

      // Build the desk map from backend truth: assessments (fee set)
      // overlaid with payment rows (fee paid).
      const builtMap = {};
      if (assessRes.status === 'fulfilled') {
        const assessments = assessRes.value.data?.results || assessRes.value.data || [];
        assessments.forEach(a => {
          if (a.student) {
            builtMap[a.student] = {
              totalFee: parseFloat(a.total_fee),
              breakdown: a.fee_breakdown || {},
              isSet: true,
              assessmentId: a.id,
            };
          }
        });
      }

      // Check payment ledgers to mark paid candidates
      if (ledgerRes.status === 'fulfilled') {
        const ledgers = ledgerRes.value.data?.results || ledgerRes.value.data || [];
        ledgers.forEach(l => {
          if (l.student && l.total_fee_due > 0) {
            builtMap[l.student] = {
              ...(builtMap[l.student] || {}),
              totalFee: parseFloat(l.total_fee_due),
              isSet: true,
              isPaid: l.status === 'PAID',
              amountPaid: parseFloat(l.amount_paid)
            };
          }
        });
      }
      setFeesMap(builtMap);

    } catch (err) {
      console.error('Error loading candidate fee desk:', err);
      setError('Failed to fetch eligible students for fee desk.');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, [search, onlyEligible]);

  // Client-side filtering across departments & fee statuses
  const filteredStudents = students.filter(s => {
    if (selectedDept && s.department_code !== selectedDept) {
      return false;
    }
    const feeInfo = feesMap[s.id];
    const isFeeSet = Boolean(feeInfo && feeInfo.totalFee > 0);
    const isPaid = Boolean(feeInfo && feeInfo.isPaid);

    if (selectedFeeStatus === 'SET' && !isFeeSet) return false;
    if (selectedFeeStatus === 'UNSET' && isFeeSet) return false;
    if (selectedFeeStatus === 'PAID' && !isPaid) return false;
    return true;
  });

  const hasActiveFilters = Boolean(search.trim() || selectedDept || selectedFeeStatus || selectedYear);
  const totalPages = Math.ceil(filteredStudents.length / PAGE_SIZE) || 1;
  const startIndex = (currentPage - 1) * PAGE_SIZE;
  const endIndex = Math.min(startIndex + PAGE_SIZE, filteredStudents.length);
  const currentStudents = filteredStudents.slice(startIndex, endIndex);

  const handleClearFilters = () => {
    setSearch('');
    setSelectedDept('');
    setSelectedFeeStatus('');
    setSelectedYear('');
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

    const activeYear = academicYears.find(y => y.is_current) || academicYears[0];
    const amountVal = parseFloat(markForm.amountPaid) || 0;

    try {
      // No client receipt: the server sequences GCOEK/<year>/FEE/<nnnn>.
      const payload = {
        student: markingStudent.id,
        academic_year: activeYear?.id,
        total_fee_due: amountVal,
        amount_paid: amountVal,
        payment_mode: markForm.paymentMode,
        transaction_ref: markForm.transactionRef || `OFFLINE-${Date.now()}`,
        payment_date: new Date().toISOString().split('T')[0],
        remarks: markForm.remarks,
      };

      const created = await financeApi.recordPayment(payload);

      // Refresh from backend truth (assessments + ledgers)
      await fetchData();

      const receiptNo = created.data?.receipt_no || 'issued';
      setSuccessMsg(`Fee marked and receipt ${receiptNo} issued for ${markingStudent.display_name}!`);
      setShowMarkModal(false);
      setTimeout(() => setSuccessMsg(''), 4000);
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

  // Action: Open History Modal
  const handleOpenHistory = async (student) => {
    setHistoryStudent(student);
    setShowHistoryModal(true);
    setLoadingHistory(true);
    try {
      const res = await financeApi.getPaymentLedgers({ search: student.enrollment_no || student.display_name });
      const records = res.data?.results || res.data || [];
      const studentRecords = records.filter(r => r.student === student.id || r.enrollment_no === student.enrollment_no);
      setPaymentRecords(studentRecords);
    } catch (err) {
      console.error('Error fetching history:', err);
    } finally {
      setLoadingHistory(false);
    }
  };

  return (
    <>
      <PageHeader
        breadcrumbs={[
          { label: 'Home', to: '/dashboard' },
          { label: 'Finance' },
          { label: 'Candidate Ledger & Fee Desk' },
        ]}
        title="Candidate Ledger & Fee Desk"
        subtitle="Review HOD-approved eligible candidates for next year admission, configure admission fees, and record fee collections."
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

        {/* Main Card (Styled exactly like StudentDirectoryPage) */}
        <div className="edvana-card" style={{ padding: '1.5rem 1.75rem' }}>
          {/* Card Top Title & Stats Header */}
          <div style={{
            display: 'flex',
            flexWrap: 'wrap',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: '1rem',
            marginBottom: '1rem'
          }}>
            <div>
              <div style={{ fontSize: '0.78rem', fontWeight: 600, color: '#2563eb', marginBottom: '0.2rem', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                Finance / Admission Desk
              </div>
              <h2 style={{ fontSize: '1.35rem', fontWeight: 700, color: '#0f172a', margin: 0, lineHeight: 1.25 }}>
                Candidate Admission Fee Roster
              </h2>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <span style={{
                background: '#eff6ff',
                color: '#1E60DC',
                border: '1px solid #bfdbfe',
                borderRadius: '9999px',
                padding: '0.35rem 0.95rem',
                fontSize: '0.78rem',
                fontWeight: 700,
                display: 'inline-flex',
                alignItems: 'center',
                gap: '0.35rem'
              }}>
                <Users size={14} />
                <span>
                  {hasActiveFilters
                    ? `${filteredStudents.length} Results (${totalCandidates} Total)`
                    : onlyEligible
                      ? `${totalCandidates} Eligible Candidates`
                      : `${totalCandidates} Candidates`}
                </span>
              </span>
            </div>
          </div>

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
                placeholder="Search name, enrollment no, app ID..."
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

            {/* HOD-Verified Eligible Candidates Toggle */}
            <button
              type="button"
              onClick={() => setOnlyEligible(!onlyEligible)}
              style={{
                height: '38px',
                padding: '0 0.85rem',
                fontSize: '0.8125rem',
                fontWeight: 600,
                borderRadius: '8px',
                border: onlyEligible ? '1px solid #16a34a' : '1px solid #cbd5e1',
                backgroundColor: onlyEligible ? '#f0fdf4' : '#ffffff',
                color: onlyEligible ? '#15803d' : '#64748b',
                display: 'inline-flex',
                alignItems: 'center',
                gap: '0.4rem',
                cursor: 'pointer',
                transition: 'all 0.15s ease',
              }}
              title={onlyEligible ? 'Showing only HOD-verified eligible candidates' : 'Showing all students'}
            >
              <CheckCircle2 size={15} style={{ color: onlyEligible ? '#16a34a' : '#94a3b8' }} />
              <span>{onlyEligible ? 'Eligible Candidates Only' : 'All Students'}</span>
            </button>

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
                      <th style={{ padding: '0.85rem 1.15rem', fontSize: '0.72rem', fontWeight: 700, color: '#475569', letterSpacing: '0.05em', width: '55px' }}>
                        S.N.
                      </th>
                      <th style={{ padding: '0.85rem 1.15rem', fontSize: '0.72rem', fontWeight: 700, color: '#475569', letterSpacing: '0.05em', width: '130px' }}>
                        ENROLL NO.
                      </th>
                      <th style={{ padding: '0.85rem 1.15rem', fontSize: '0.72rem', fontWeight: 700, color: '#475569', letterSpacing: '0.05em', minWidth: '220px' }}>
                        NAME
                      </th>
                      <th style={{ padding: '0.85rem 1.15rem', fontSize: '0.72rem', fontWeight: 700, color: '#475569', letterSpacing: '0.05em', minWidth: '180px' }}>
                        FATHER'S NAME
                      </th>
                      <th style={{ padding: '0.85rem 1.15rem', fontSize: '0.72rem', fontWeight: 700, color: '#475569', letterSpacing: '0.05em', width: '130px' }}>
                        MOBILE
                      </th>
                      <th style={{ padding: '0.85rem 1.15rem', fontSize: '0.72rem', fontWeight: 700, color: '#475569', letterSpacing: '0.05em', textAlign: 'center', width: '160px' }}>
                        FEE MARKED / STATUS
                      </th>
                      <th style={{ padding: '0.85rem 1.15rem', fontSize: '0.72rem', fontWeight: 700, color: '#475569', letterSpacing: '0.05em', textAlign: 'center', minWidth: '290px' }}>
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

                      const shortPrn = stu.enrollment_no ? (stu.enrollment_no.slice(-6).replace(/\D/g, '') || stu.enrollment_no) : '191227';
                      const appNo = stu.application_id || 'EN26400284';
                      const genderDept = `${(stu.gender || 'FEMALE').toUpperCase()} • ${stu.department_code || 'AIDS'}`;

                      return (
                        <tr 
                          key={stu.id} 
                          style={{ 
                            borderBottom: '1px solid #f1f5f9',
                            transition: 'background 0.15s ease'
                          }}
                          onMouseEnter={(e) => e.currentTarget.style.background = '#f8fafc'}
                          onMouseLeave={(e) => e.currentTarget.style.background = '#ffffff'}
                        >
                          {/* S.N. (Paginated) */}
                          <td style={{ padding: '0.85rem 1.15rem', fontSize: '0.85rem', color: '#64748b', fontWeight: 500 }}>
                            {startIndex + index + 1}
                          </td>

                          {/* ENROLL NO. */}
                          <td style={{ padding: '0.85rem 1.15rem' }}>
                            <div style={{ color: '#1E60DC', fontWeight: 700, fontSize: '0.875rem' }}>
                              {shortPrn}
                            </div>
                            <div style={{ color: '#64748b', fontSize: '0.75rem', fontFamily: 'monospace', marginTop: '0.15rem' }}>
                              {appNo}
                            </div>
                          </td>

                          {/* NAME */}
                          <td style={{ padding: '0.85rem 1.15rem' }}>
                            <div style={{ fontWeight: 700, color: '#0f172a', fontSize: '0.875rem' }}>
                              {stu.display_name}
                            </div>
                            <div style={{ color: '#64748b', fontSize: '0.75rem', fontWeight: 500, marginTop: '0.15rem', textTransform: 'uppercase' }}>
                              {genderDept}
                            </div>
                          </td>

                          {/* FATHER'S NAME */}
                          <td style={{ padding: '0.85rem 1.15rem', fontSize: '0.85rem', color: '#334155', fontWeight: 500, textTransform: 'uppercase' }}>
                            {stu.father_name || '—'}
                          </td>

                          {/* MOBILE */}
                          <td style={{ padding: '0.85rem 1.15rem', fontSize: '0.85rem', color: '#334155', fontFamily: 'monospace' }}>
                            {stu.mobile || '—'}
                          </td>

                          {/* FEE MARKED / STATUS */}
                          <td style={{ padding: '0.85rem 1.15rem', textAlign: 'center' }}>
                            {isFeeSet ? (
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
                                ₹{feeAmount.toLocaleString('en-IN')}
                              </span>
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
                          <td style={{ padding: '0.85rem 1.15rem', textAlign: 'center', whiteSpace: 'nowrap' }}>
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
                                    padding: '0 0.95rem',
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
                                    padding: '0 0.95rem',
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
                                    padding: '0 1rem',
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
                                    padding: '0 0.95rem',
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
                                    padding: '0 0.95rem',
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
                                    padding: '0 0.95rem',
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

                              {/* 3. History Button */}
                              <button
                                type="button"
                                onClick={() => handleOpenHistory(stu)}
                                style={{
                                  background: '#ffffff',
                                  color: '#475569',
                                  border: '1px solid #cbd5e1',
                                  borderRadius: '20px',
                                  padding: '0 0.85rem',
                                  height: '30px',
                                  fontSize: '0.75rem',
                                  fontWeight: 600,
                                  cursor: 'pointer',
                                  whiteSpace: 'nowrap',
                                  display: 'inline-flex',
                                  alignItems: 'center',
                                  justifyContent: 'center',
                                  gap: '0.3rem',
                                  transition: 'all 0.15s ease'
                                }}
                                onMouseEnter={(e) => {
                                  e.currentTarget.style.background = '#f8fafc';
                                  e.currentTarget.style.borderColor = '#94a3b8';
                                }}
                                onMouseLeave={(e) => {
                                  e.currentTarget.style.background = '#ffffff';
                                  e.currentTarget.style.borderColor = '#cbd5e1';
                                }}
                                title="View payment receipt history"
                              >
                                <History size={12} style={{ color: '#64748b' }} />
                                <span>History</span>
                              </button>
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
                PRN: {markingStudent.enrollment_no || 'Pending'} • App ID: {markingStudent.application_id || 'N/A'} • Dept: {markingStudent.department_code || 'General'}
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

      {/* History Modal */}
      {showHistoryModal && historyStudent && (
        <Modal
          isOpen={showHistoryModal}
          onClose={() => setShowHistoryModal(false)}
          title={`Payment History: ${historyStudent.display_name}`}
          maxWidth="640px"
        >
          <div style={{ padding: '0.5rem 0' }}>
            {loadingHistory ? (
              <div style={{ padding: '2rem 0' }}>
                <LoadingState message="Loading payment ledger records..." />
              </div>
            ) : paymentRecords.length === 0 ? (
              <div style={{ padding: '2.5rem 1rem', textAlign: 'center', color: '#64748b' }}>
                <History size={36} style={{ margin: '0 auto 0.75rem auto', color: '#94a3b8' }} />
                <div style={{ fontSize: '1rem', fontWeight: 600, color: '#334155' }}>No Payment Records Found</div>
                <div style={{ fontSize: '0.85rem', marginTop: '0.25rem' }}>
                  No fee receipts have been recorded for this student yet.
                </div>
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
                {paymentRecords.map((rec) => (
                  <div
                    key={rec.id}
                    style={{
                      background: '#f8fafc',
                      border: '1px solid #e2e8f0',
                      borderRadius: '10px',
                      padding: '1rem 1.25rem',
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'center'
                    }}
                  >
                    <div>
                      <div style={{ fontWeight: 700, fontSize: '0.9rem', color: '#0f172a' }}>
                        Receipt: <span style={{ fontFamily: 'monospace' }}>{rec.receipt_no}</span>
                      </div>
                      <div style={{ fontSize: '0.8rem', color: '#64748b', marginTop: '0.2rem' }}>
                        Date: {rec.payment_date} • Mode: {rec.payment_mode_display || rec.payment_mode}
                      </div>
                    </div>

                    <div style={{ textAlign: 'right' }}>
                      <div style={{ fontSize: '1.05rem', fontWeight: 800, color: '#15803d' }}>
                        ₹{parseFloat(rec.amount_paid).toLocaleString('en-IN')}
                      </div>
                      <span style={{
                        fontSize: '0.7rem',
                        fontWeight: 800,
                        padding: '0.15rem 0.5rem',
                        borderRadius: '9999px',
                        background: '#dcfce7',
                        color: '#15803d',
                        border: '1px solid #86efac'
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
