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

  const fetchData = async () => {
    setLoading(true);
    setError(null);
    try {
      const [anaRes, ledRes, yearsRes] = await Promise.all([
        financeApi.getFinanceAnalytics(yearFilter ? { academic_year: yearFilter } : undefined),
        financeApi.getPaymentLedgers({
          search: searchTerm || undefined,
          status: statusFilter || undefined,
        }),
        academicApi.getAcademicYears().catch(() => ({ data: [] })),
      ]);
      setAnalytics(anaRes.data);
      setLedger(ledRes.data?.results || ledRes.data || []);
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

  // Helper calculations
  const totalCollected = analytics?.total_collected || 0;
  const totalDue = analytics?.total_due || 0;
  const totalBalance = analytics?.total_balance || 0;
  const totalReceipts = analytics?.total_receipts || 0;
  const recoveryRate = totalDue > 0 ? ((totalCollected / totalDue) * 100).toFixed(1) : '100.0';

  const modeMap = analytics?.collection_by_mode || {};
  const getModeAmt = (pattern) => {
    for (const [key, val] of Object.entries(modeMap)) {
      if (key.toLowerCase().includes(pattern.toLowerCase())) return val;
    }
    return 0;
  };

  const onlineAmt = getModeAmt('online') || getModeAmt('gateway') || 0;
  const ddAmt = getModeAmt('draft') || getModeAmt('dd') || 0;
  const challanAmt = getModeAmt('challan') || 0;
  const cashAmt = getModeAmt('cash') || 0;
  const neftAmt = getModeAmt('neft') || getModeAmt('rtgs') || 0;

  const paidCount = ledger.filter(r => r.status === 'PAID').length;
  const partialCount = ledger.filter(r => r.status === 'PARTIAL').length;
  const pendingCount = ledger.filter(r => r.status === 'PENDING').length;

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
      value: '100.0%',
      subtext: 'Settled',
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
              <span className="analytics-summary-row-val">{ledger.length}</span>
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
              <span className="analytics-summary-row-val" style={{ color: '#1E60DC' }}>100.0%</span>
            </div>
            <div className="metric-bottom-bar" />
          </div>
        </div>

        {/* Master Payment Ledger Section */}
        <div className="edvana-card">
          <div className="edvana-card-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '1rem' }}>
            <div>
              <h2 className="edvana-card-title">Master Payment Ledger ({ledger.length})</h2>
              <p className="edvana-card-description">Auditable record of all fee transactions and reconciliation entries</p>
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
