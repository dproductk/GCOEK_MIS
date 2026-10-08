import React, { useState, useEffect } from 'react';
import { 
  BarChart3, IndianRupee, CreditCard, Layers, 
  Search, Filter, CheckCircle2, AlertCircle, RefreshCw, 
  ArrowUpRight, Clock, UserCheck, ShieldCheck, Wallet
} from 'lucide-react';
import financeApi from '../../api/financeApi';
import academicApi from '../../api/academicApi';
import PageHeader from '../../components/common/PageHeader';
import DataTable from '../../components/common/DataTable';
import Badge from '../../components/common/Badge';
import { LoadingState, ErrorState, EmptyState } from '../../components/common/StateDisplays';

export default function FeeAnalyticsPage() {
  const [analytics, setAnalytics] = useState(null);
  const [ledger, setLedger] = useState([]);
  const [ledgerTotalCount, setLedgerTotalCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [activeCards, setActiveCards] = useState({});

  // Filters
  const [searchTerm, setSearchTerm] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [years, setYears] = useState([]);
  const [yearFilter, setYearFilter] = useState('');

  const toggleCard = (id) => {
    setActiveCards(prev => ({
      ...prev,
      [id]: !prev[id]
    }));
  };

  const fetchData = async (yearOverride) => {
    setLoading(true);
    setError(null);
    try {
      const effectiveYear = yearOverride !== undefined ? yearOverride : yearFilter;
      const [anaRes, ledRes, yearsRes] = await Promise.all([
        financeApi.getFinanceAnalytics(effectiveYear ? { academic_year: effectiveYear } : undefined),
        financeApi.getPaymentLedgers({
          search: searchTerm || undefined,
          status: statusFilter || undefined,
          academic_year: effectiveYear || undefined,
          // FinancePagination allows up to 1000 rows so a full college
          // roster fits in one request (see backend FinancePagination).
          page_size: 1000,
        }),
        academicApi.getAcademicYears().catch(() => ({ data: [] })),
      ]);
      setAnalytics(anaRes.data);
      const rows = ledRes.data?.results || ledRes.data || [];
      setLedger(Array.isArray(rows) ? rows : []);
      // Authoritative total from pagination (rows may be capped at page_size).
      setLedgerTotalCount(
        typeof ledRes.data?.count === 'number' ? ledRes.data.count : (Array.isArray(rows) ? rows.length : 0)
      );
      const rawYears = yearsRes.data?.results || yearsRes.data || [];
      if (rawYears.length > 0) setYears(rawYears);
    } catch (err) {
      console.error('Failed to fetch finance analytics:', err);
      setError('Could not load financial analytics data.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData(yearFilter || undefined);
  }, [statusFilter, yearFilter]);

  const handleSearch = (e) => {
    e.preventDefault();
    fetchData();
  };

  const getStatusBadgeVariant = (status) => {
    switch (status) {
      case 'PAID':
        return 'success';
      case 'PARTIAL':
        return 'warning';
      case 'PENDING':
      default:
        return 'danger';
    }
  };

  // Helper calculations (authoritative KPIs come from /analytics/ aggregates;
  // the ledger table below is the same year-filtered, paginated slice).
  const totalCollected = Number(analytics?.total_collected || 0);
  const totalDue = Number(analytics?.total_due || 0);
  const totalBalance = Number(analytics?.total_balance || 0);
  // Authoritative receipt count from the backend aggregate, not page length.
  const totalReceipts = analytics?.total_receipts ?? ledgerTotalCount ?? ledger.length ?? 0;
  const recoveryRate = totalDue > 0 ? ((totalCollected / totalDue) * 100).toFixed(1) : '0.0';
  // Treasury clearance = share of billed fees actually collected.
  const treasuryClearance = `${recoveryRate}%`;

  const modeMap = analytics?.collection_by_mode || {};
  // Exact backend labels (PaymentLedger.PaymentMode.choices) first,
  // fuzzy substring match only as a fallback for future labels.
  const getModeAmt = (pattern) => {
    if (modeMap[pattern] !== undefined) return Number(modeMap[pattern]) || 0;
    for (const [key, val] of Object.entries(modeMap)) {
      if (key.toLowerCase().includes(pattern.toLowerCase())) return Number(val) || 0;
    }
    return 0;
  };

  const onlineAmt = getModeAmt('Online Gateway (UPI/Netbanking)') || getModeAmt('online') || 0;
  const ddAmt = getModeAmt('Demand Draft') || getModeAmt('draft') || 0;
  const challanAmt = getModeAmt('Bank Challan') || getModeAmt('challan') || 0;
  const cashAmt = getModeAmt('Cash Counter') || getModeAmt('cash') || 0;
  const neftAmt = getModeAmt('NEFT / RTGS Transfer') || getModeAmt('neft') || getModeAmt('rtgs') || 0;

  const paidCount = ledger.filter(r => r.status === 'PAID').length;
  const partialCount = ledger.filter(r => r.status === 'PARTIAL').length;
  const pendingCount = ledger.filter(r => r.status === 'PENDING').length;
  // Share of receipts fully settled. Only exact when the full filtered
  // set fits in one page (page_size=1000); otherwise it is a lower-bound
  // estimate from the loaded slice.
  const ledgerCoversAll = ledgerTotalCount > 0 ? ledger.length >= ledgerTotalCount : true;
  const auditSettlement = totalReceipts > 0
    ? ((paidCount / totalReceipts) * 100).toFixed(1) + '%'
    : '0.0%';

  // Online payment gateway stats (from backend analytics.online_payment)
  const online = analytics?.online_payment || {};
  const onlineEnabledStudents = online.enabled_students || 0;
  const onlineSuccessCount = online.successful_payments || 0;
  const onlineSuccessStudents = online.successful_students || 0;
  const onlineSuccessAmt = online.successful_amount || online.ledger_online_amount || 0;
  const onlinePendingCount = online.pending_count || 0;
  const onlinePendingStudents = online.pending_students || 0;
  const onlinePendingAmt = online.pending_amount || 0;
  const onlineFailedCount = online.failed_count || 0;
  const onlineCancelledCount = online.cancelled_count || 0;
  const onlineExpiredCount = online.expired_count || 0;
  const onlineTotalAttempts = online.total_attempts || 0;

  // 12 metric boxes arranged in two 6-box rows matching the reference dashboard
  const metricBoxesRow1 = [
    {
      id: 'kpi_collections',
      label: 'Total Collections',
      value: `₹${totalCollected.toLocaleString('en-IN', { minimumFractionDigits: 0 })}`,
      subtext: 'All sources',
    },
    {
      id: 'kpi_due',
      label: 'Total Assessed Dues',
      value: `₹${totalDue.toLocaleString('en-IN', { minimumFractionDigits: 0 })}`,
      subtext: 'Billed',
    },
    {
      id: 'kpi_balance',
      label: 'Pending Balance',
      value: `₹${totalBalance.toLocaleString('en-IN', { minimumFractionDigits: 0 })}`,
      subtext: 'Receivable',
    },
    {
      id: 'kpi_recovery',
      label: 'Recovery Rate',
      value: `${recoveryRate}%`,
      subtext: 'Audited',
    },
    {
      id: 'kpi_receipts',
      label: 'Total Receipts',
      value: totalReceipts.toLocaleString('en-IN'),
      subtext: 'Vouchers',
    },
    {
      id: 'kpi_clearance',
      label: 'Treasury Clearance',
      value: treasuryClearance,
      subtext: 'Collected / Billed',
    },
  ];

  const metricBoxesRow2 = [
    {
      id: 'mode_online',
      label: 'Online Gateway',
      value: `₹${onlineAmt.toLocaleString('en-IN', { minimumFractionDigits: 0 })}`,
      subtext: 'UPI / NetBanking',
    },
    {
      id: 'mode_dd',
      label: 'Demand Draft',
      value: `₹${ddAmt.toLocaleString('en-IN', { minimumFractionDigits: 0 })}`,
      subtext: 'DD slips',
    },
    {
      id: 'mode_challan',
      label: 'Bank Challan',
      value: `₹${challanAmt.toLocaleString('en-IN', { minimumFractionDigits: 0 })}`,
      subtext: 'Challan slips',
    },
    {
      id: 'mode_cash',
      label: 'Cash Counter',
      value: `₹${cashAmt.toLocaleString('en-IN', { minimumFractionDigits: 0 })}`,
      subtext: 'Counter desk',
    },
    {
      id: 'mode_neft',
      label: 'NEFT / RTGS Transfer',
      value: `₹${neftAmt.toLocaleString('en-IN', { minimumFractionDigits: 0 })}`,
      subtext: 'Direct credits',
    },
    {
      id: 'mode_settled',
      label: 'Settled Accounts',
      value: paidCount.toString(),
      subtext: 'Verified',
    },
  ];

  const onlineGatewayBoxes = [
    {
      id: 'online_enabled',
      label: 'Online Enabled Students',
      value: onlineEnabledStudents.toLocaleString('en-IN'),
      subtext: 'Allowed by desk',
    },
    {
      id: 'online_success',
      label: 'Successful Online Payments',
      value: onlineSuccessCount.toLocaleString('en-IN'),
      subtext: `${onlineSuccessStudents.toLocaleString('en-IN')} students`,
    },
    {
      id: 'online_collected',
      label: 'Total Online Collected',
      value: `₹${Number(onlineSuccessAmt).toLocaleString('en-IN', { minimumFractionDigits: 0 })}`,
      subtext: 'Easebuzz verified',
    },
    {
      id: 'online_pending',
      label: 'Pending / In-Flight',
      value: onlinePendingCount.toLocaleString('en-IN'),
      subtext: `${onlinePendingStudents.toLocaleString('en-IN')} students • ₹${Number(onlinePendingAmt).toLocaleString('en-IN', { minimumFractionDigits: 0 })}`,
    },
    {
      id: 'online_failed',
      label: 'Failed Attempts',
      value: onlineFailedCount.toLocaleString('en-IN'),
      subtext: 'Bank / gateway failed',
    },
    {
      id: 'online_cancelled',
      label: 'Cancelled / Expired',
      value: (onlineCancelledCount + onlineExpiredCount).toLocaleString('en-IN'),
      subtext: `${onlineTotalAttempts.toLocaleString('en-IN')} total attempts`,
    },
  ];

  const columns = [
    {
      header: 'Receipt No',
      accessor: 'receipt_no',
      render: (row) => <span style={{ fontFamily: 'monospace', fontWeight: 600, color: 'var(--edvana-primary)' }}>{row.receipt_no}</span>,
    },
    {
      header: 'Student Name',
      accessor: 'student_name',
      render: (row) => <span style={{ fontWeight: 600, color: '#0f172a' }}>{row.student_name}</span>,
    },
    {
      header: 'PRN',
      accessor: 'enrollment_no',
      render: (row) => <span style={{ fontFamily: 'monospace', color: '#475569' }}>{row.enrollment_no || 'N/A'}</span>,
    },
    {
      header: 'Total Due (₹)',
      align: 'right',
      render: (row) => <span>₹{parseFloat(row.total_fee_due).toLocaleString('en-IN')}</span>,
    },
    {
      header: 'Amount Paid (₹)',
      align: 'right',
      render: (row) => <span style={{ fontWeight: 700, color: '#166534' }}>₹{parseFloat(row.amount_paid).toLocaleString('en-IN')}</span>,
    },
    {
      header: 'Balance (₹)',
      align: 'right',
      render: (row) => <span style={{ fontWeight: 600, color: parseFloat(row.balance_due) > 0 ? '#b45309' : '#166534' }}>₹{parseFloat(row.balance_due).toLocaleString('en-IN')}</span>,
    },
    {
      header: 'Mode',
      accessor: 'payment_mode_display',
    },
    {
      header: 'Status',
      align: 'center',
      render: (row) => (
        <Badge variant={getStatusBadgeVariant(row.status)}>
          {row.status_display}
        </Badge>
      ),
    },
    {
      header: 'Date',
      accessor: 'payment_date',
    },
  ];

  return (
    <>
      <PageHeader
        breadcrumbs={[
          { label: 'Home', to: '/dashboard' },
          { label: 'Finance' },
          { label: 'Fee Analytics' },
        ]}
        title="Fee Ledger & Institutional Analytics"
        subtitle="Comprehensive real-time tracking of tuition revenue collections, balance recovery, and treasury receipts."
        actions={
          <button
            onClick={fetchData}
            className="edvana-btn"
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
            <span>Refresh Analytics</span>
          </button>
        }
      />

      <div className="edvana-banner-overlap">
        {error && (
          <div style={{ marginBottom: '1.5rem', padding: '1rem 1.25rem', background: '#fef2f2', border: '1px solid #fecaca', borderRadius: '8px', color: '#991b1b', fontSize: '0.875rem', display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
            <AlertCircle size={20} style={{ flexShrink: 0 }} />
            <div>{error}</div>
          </div>
        )}

        {/* 6-box Row 1: Key Financial KPIs */}
        <div className="analytics-metric-grid">
          {metricBoxesRow1.map((box) => (
            <div
              key={box.id}
              className={`analytics-metric-box ${activeCards[box.id] ? 'active' : ''}`}
              onClick={() => toggleCard(box.id)}
              role="button"
              tabIndex={0}
              onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') toggleCard(box.id); }}
            >
              <div className="metric-label">{box.label}</div>
              <div className="metric-value-row">
                <div className="metric-value">{box.value}</div>
                {box.subtext && <div className="metric-subtext">{box.subtext}</div>}
              </div>
              <div className="metric-bottom-bar" />
            </div>
          ))}
        </div>

        {/* 6-box Row 2: Inflow by Payment Channels */}
        <div className="analytics-metric-grid">
          {metricBoxesRow2.map((box) => (
            <div
              key={box.id}
              className={`analytics-metric-box ${activeCards[box.id] ? 'active' : ''}`}
              onClick={() => toggleCard(box.id)}
              role="button"
              tabIndex={0}
              onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') toggleCard(box.id); }}
            >
              <div className="metric-label">{box.label}</div>
              <div className="metric-value-row">
                <div className="metric-value">{box.value}</div>
                {box.subtext && <div className="metric-subtext">{box.subtext}</div>}
              </div>
              <div className="metric-bottom-bar" />
            </div>
          ))}
        </div>

        {/* Online Payment Gateway section */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', margin: '1.75rem 0 0.85rem 0' }}>
          <Wallet size={16} style={{ color: '#15803d' }} />
          <h3 style={{ fontSize: '0.95rem', fontWeight: 700, color: '#0f172a', margin: 0 }}>
            Online Payment Gateway (Easebuzz)
          </h3>
          <span style={{ fontSize: '0.72rem', fontWeight: 600, color: '#64748b' }}>
            attempts by status • students • total fees
          </span>
        </div>
        <div className="analytics-metric-grid">
          {onlineGatewayBoxes.map((box) => (
            <div
              key={box.id}
              className={`analytics-metric-box ${activeCards[box.id] ? 'active' : ''}`}
              onClick={() => toggleCard(box.id)}
              role="button"
              tabIndex={0}
              onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') toggleCard(box.id); }}
            >
              <div className="metric-label">{box.label}</div>
              <div className="metric-value-row">
                <div className="metric-value">{box.value}</div>
                {box.subtext && <div className="metric-subtext">{box.subtext}</div>}
              </div>
              <div className="metric-bottom-bar" />
            </div>
          ))}
        </div>

        {/* 3 Summary Cards matching Reference UI */}
        <div className="analytics-summary-grid">
          {/* Card 1: Admission & Collection Lifecycle */}
          <div 
            className={`analytics-summary-card ${activeCards['summary_lifecycle'] ? 'active' : ''}`}
            onClick={() => toggleCard('summary_lifecycle')}
          >
            <h3 style={{ fontSize: '1rem', fontWeight: 700, color: '#0f172a', marginBottom: '1rem' }}>
              Collection Lifecycle
            </h3>
            <div className="analytics-summary-row">
              <span className="analytics-summary-row-label">Assessed Fee Billed</span>
              <span className="analytics-summary-row-val">₹{totalDue.toLocaleString('en-IN', { minimumFractionDigits: 0 })}</span>
            </div>
            <div className="analytics-summary-row">
              <span className="analytics-summary-row-label">Net Fee Collected</span>
              <span className="analytics-summary-row-val" style={{ color: '#166534' }}>₹{totalCollected.toLocaleString('en-IN', { minimumFractionDigits: 0 })}</span>
            </div>
            <div className="analytics-summary-row">
              <span className="analytics-summary-row-label">Outstanding Balance</span>
              <span className="analytics-summary-row-val" style={{ color: totalBalance > 0 ? '#b45309' : '#166534' }}>
                ₹{totalBalance.toLocaleString('en-IN', { minimumFractionDigits: 0 })}
              </span>
            </div>
            <div className="analytics-summary-row">
              <span className="analytics-summary-row-label">Recovery Percentage</span>
              <span className="analytics-summary-row-val" style={{ color: '#1E60DC' }}>{recoveryRate}%</span>
            </div>
            <div className="analytics-summary-row">
              <span className="analytics-summary-row-label">Total Fee Records</span>
              <span className="analytics-summary-row-val">{totalReceipts}</span>
            </div>
            <div className="metric-bottom-bar" />
          </div>

          {/* Card 2: Payment Channel Breakdown */}
          <div 
            className={`analytics-summary-card ${activeCards['summary_channels'] ? 'active' : ''}`}
            onClick={() => toggleCard('summary_channels')}
          >
            <h3 style={{ fontSize: '1rem', fontWeight: 700, color: '#0f172a', marginBottom: '1rem' }}>
              Payment Channel Breakdown
            </h3>
            <div className="analytics-summary-row">
              <span className="analytics-summary-row-label">Online Gateway</span>
              <span className="analytics-summary-row-val">₹{onlineAmt.toLocaleString('en-IN', { minimumFractionDigits: 0 })}</span>
            </div>
            <div className="analytics-summary-row">
              <span className="analytics-summary-row-label">Online Success ({onlineSuccessStudents} students)</span>
              <span className="analytics-summary-row-val" style={{ color: '#166534' }}>{onlineSuccessCount} • ₹{Number(onlineSuccessAmt).toLocaleString('en-IN', { minimumFractionDigits: 0 })}</span>
            </div>
            <div className="analytics-summary-row">
              <span className="analytics-summary-row-label">Online Pending ({onlinePendingStudents} students)</span>
              <span className="analytics-summary-row-val" style={{ color: '#b45309' }}>{onlinePendingCount} • ₹{Number(onlinePendingAmt).toLocaleString('en-IN', { minimumFractionDigits: 0 })}</span>
            </div>
            <div className="analytics-summary-row">
              <span className="analytics-summary-row-label">Online Failed / Cancelled</span>
              <span className="analytics-summary-row-val">{onlineFailedCount + onlineCancelledCount + onlineExpiredCount}</span>
            </div>
            <div className="analytics-summary-row">
              <span className="analytics-summary-row-label">Demand Draft (DD)</span>
              <span className="analytics-summary-row-val">₹{ddAmt.toLocaleString('en-IN', { minimumFractionDigits: 0 })}</span>
            </div>
            <div className="analytics-summary-row">
              <span className="analytics-summary-row-label">Bank Challan</span>
              <span className="analytics-summary-row-val">₹{challanAmt.toLocaleString('en-IN', { minimumFractionDigits: 0 })}</span>
            </div>
            <div className="analytics-summary-row">
              <span className="analytics-summary-row-label">Cash Counter</span>
              <span className="analytics-summary-row-val">₹{cashAmt.toLocaleString('en-IN', { minimumFractionDigits: 0 })}</span>
            </div>
            <div className="analytics-summary-row">
              <span className="analytics-summary-row-label">NEFT / RTGS Transfer</span>
              <span className="analytics-summary-row-val">₹{neftAmt.toLocaleString('en-IN', { minimumFractionDigits: 0 })}</span>
            </div>
            <div className="metric-bottom-bar" />
          </div>

          {/* Card 3: Reconciliation & Audit */}
          <div 
            className={`analytics-summary-card ${activeCards['summary_audit'] ? 'active' : ''}`}
            onClick={() => toggleCard('summary_audit')}
          >
            <h3 style={{ fontSize: '1rem', fontWeight: 700, color: '#0f172a', marginBottom: '1rem' }}>
              Reconciliation & Audit Status
            </h3>
            <div className="analytics-summary-row">
              <span className="analytics-summary-row-label">Receipts Issued</span>
              <span className="analytics-summary-row-val">{totalReceipts}</span>
            </div>
            <div className="analytics-summary-row">
              <span className="analytics-summary-row-label">Fully Settled Accounts</span>
              <span className="analytics-summary-row-val" style={{ color: '#166534' }}>{paidCount}</span>
            </div>
            <div className="analytics-summary-row">
              <span className="analytics-summary-row-label">Partial Balance Pending</span>
              <span className="analytics-summary-row-val" style={{ color: partialCount > 0 ? '#b45309' : '#64748b' }}>{partialCount}</span>
            </div>
            <div className="analytics-summary-row">
              <span className="analytics-summary-row-label">Pending Verification</span>
              <span className="analytics-summary-row-val">{pendingCount}</span>
            </div>
            <div className="analytics-summary-row">
              <span className="analytics-summary-row-label">Audit Settlement</span>
              <span className="analytics-summary-row-val" style={{ color: '#1E60DC' }}>
                {auditSettlement}{!ledgerCoversAll ? '*' : ''}
              </span>
            </div>
            <div className="metric-bottom-bar" />
          </div>
        </div>

        {/* Master Payment Ledger Section */}
        <div className="edvana-card">
          <div className="edvana-card-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '1rem' }}>
            <div>
              <h2 className="edvana-card-title">Master Payment Ledger ({ledgerTotalCount || ledger.length})</h2>
              <p className="edvana-card-description">Auditable record of all fee transactions and reconciliation entries{!ledgerCoversAll ? ' — showing first 1000 of ' + ledgerTotalCount : ''}</p>
            </div>

            <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: '0.75rem' }}>
              <form onSubmit={handleSearch} style={{ display: 'flex', gap: '0.5rem' }}>
                <div style={{ position: 'relative' }}>
                  <Search size={14} style={{ position: 'absolute', left: '0.65rem', top: '50%', transform: 'translateY(-50%)', color: '#94a3b8' }} />
                  <input
                    type="text"
                    placeholder="Search PRN, Receipt No..."
                    value={searchTerm}
                    onChange={(e) => setSearchTerm(e.target.value)}
                    className="edvana-input"
                    style={{ paddingLeft: '2rem', maxWidth: '200px' }}
                  />
                </div>
                <button
                  type="submit"
                  className="edvana-btn edvana-btn-primary"
                  style={{ padding: '0.35rem 0.75rem', fontSize: '0.8rem' }}
                >
                  Search
                </button>
              </form>

              <select
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value)}
                className="edvana-input"
                style={{ maxWidth: '160px' }}
              >
                <option value="">All Statuses</option>
                <option value="PAID">Fully Paid</option>
                <option value="PARTIAL">Partially Paid</option>
                <option value="PENDING">Pending</option>
              </select>

              <select
                value={yearFilter}
                onChange={(e) => setYearFilter(e.target.value)}
                className="edvana-input"
                style={{ maxWidth: '170px' }}
                title="Academic year (defaults to all years)"
              >
                <option value="">All Years</option>
                {years.map((y) => (
                  <option key={y.id} value={y.id}>
                    {y.code}{y.is_current ? ' (current)' : ''}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div className="edvana-card-body" style={{ padding: 0 }}>
            {loading ? (
              <div style={{ padding: '2.5rem' }}>
                <LoadingState message="Loading payment ledger..." />
              </div>
            ) : error ? (
              <div style={{ padding: '2.5rem' }}>
                <ErrorState title="Error Loading Ledger" message={error} onRetry={fetchData} />
              </div>
            ) : (
              <DataTable
                columns={columns}
                data={ledger}
                keyExtractor={(row) => row.id}
                pageSize={10}
                emptyTitle="No Payment Records Found"
                emptyMessage="No payment transactions match the query."
              />
            )}
          </div>
        </div>
      </div>
    </>
  );
}
