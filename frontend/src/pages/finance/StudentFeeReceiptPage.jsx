import React, { useState, useEffect } from 'react';
import { 
  Receipt, IndianRupee, Printer, Download, CheckCircle2, 
  Clock, AlertCircle, FileText, ShieldCheck, X, Award
} from 'lucide-react';
import financeApi from '../../api/financeApi';
import PageHeader from '../../components/common/PageHeader';
import StatCard from '../../components/common/StatCard';
import DataTable from '../../components/common/DataTable';
import Badge from '../../components/common/Badge';
import Modal from '../../components/common/Modal';
import { LoadingState, ErrorState, EmptyState } from '../../components/common/StateDisplays';

export default function StudentFeeReceiptPage() {
  const [payments, setPayments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [selectedReceipt, setSelectedReceipt] = useState(null);

  useEffect(() => {
    financeApi.getMyPayments()
      .then((res) => {
        setPayments(res.data || []);
      })
      .catch((err) => {
        console.error('Failed to load fee payments:', err);
        setError('Could not retrieve fee receipts.');
      })
      .finally(() => {
        setLoading(false);
      });
  }, []);

  const totalPaid = payments.reduce((acc, p) => acc + parseFloat(p.amount_paid || 0), 0);
  const totalDue = payments.length > 0 ? parseFloat(payments[0].total_fee_due || 0) : 0;
  const balanceRemaining = Math.max(0, totalDue - totalPaid);

  const getStatusBadgeVariant = (status) => {
    switch (status) {
      case 'PAID':
        return 'success';
      case 'PARTIAL':
        return 'warning';
      default:
        return 'danger';
    }
  };

  const columns = [
    {
      header: 'Receipt Number',
      accessor: 'receipt_no',
      render: (p) => <span style={{ fontFamily: 'monospace', fontWeight: 600, color: 'var(--edvana-primary)' }}>{p.receipt_no}</span>,
    },
    {
      header: 'Academic Term',
      accessor: 'academic_year_code',
      render: (p) => <span style={{ fontWeight: 500 }}>{p.academic_year_code}</span>,
    },
    {
      header: 'Amount Paid (₹)',
      align: 'right',
      render: (p) => (
        <span style={{ fontWeight: 700, color: '#166534' }}>
          ₹{parseFloat(p.amount_paid).toLocaleString('en-IN')}
        </span>
      ),
    },
    {
      header: 'Balance Due (₹)',
      align: 'right',
      render: (p) => (
        <span style={{ fontWeight: 500, color: parseFloat(p.balance_due) > 0 ? '#b45309' : '#64748b' }}>
          ₹{parseFloat(p.balance_due).toLocaleString('en-IN')}
        </span>
      ),
    },
    {
      header: 'Payment Mode',
      accessor: 'payment_mode_display',
    },
    {
      header: 'Date',
      accessor: 'payment_date',
      render: (p) => <span style={{ fontSize: '0.85rem', color: '#64748b' }}>{p.payment_date}</span>,
    },
    {
      header: 'Status',
      align: 'center',
      render: (p) => (
        <Badge variant={getStatusBadgeVariant(p.status)}>
          {p.status_display}
        </Badge>
      ),
    },
    {
      header: 'Action',
      align: 'right',
      render: (p) => (
        <button
          onClick={() => setSelectedReceipt(p)}
          className="edvana-btn edvana-btn-secondary"
          style={{ padding: '0.25rem 0.65rem', fontSize: '0.8rem' }}
        >
          View Receipt
        </button>
      ),
    },
  ];

  return (
    <>
      <PageHeader
        breadcrumbs={[
          { label: 'Home', to: '/dashboard' },
          { label: 'Student Portal' },
          { label: 'Payment History' },
        ]}
        title="Fee Payment History & Statements"
        subtitle="Government College of Engineering, Kolhapur — Official Student Fee Ledger & Receipts."
      />

      <div className="edvana-banner-overlap">
        {error && (
          <div style={{ marginBottom: '1.5rem', padding: '1rem 1.25rem', background: '#fef2f2', border: '1px solid #fecaca', borderRadius: '8px', color: '#991b1b', fontSize: '0.875rem', display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
            <AlertCircle size={20} style={{ flexShrink: 0 }} />
            <div>{error}</div>
          </div>
        )}

        {/* Summary Cards */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '1.25rem', marginBottom: '1.5rem' }}>
          <StatCard
            label="Annual Fee Assessed"
            value={`₹${totalDue.toLocaleString('en-IN', { minimumFractionDigits: 2 })}`}
            hint="Academic Term Assessment"
            icon={FileText}
            color="var(--edvana-brand)"
          />
          <StatCard
            label="Total Amount Paid"
            value={`₹${totalPaid.toLocaleString('en-IN', { minimumFractionDigits: 2 })}`}
            hint="Verified by Accounts Section"
            icon={CheckCircle2}
            color="var(--edvana-success)"
          />
          <StatCard
            label="Outstanding Balance"
            value={`₹${balanceRemaining.toLocaleString('en-IN', { minimumFractionDigits: 2 })}`}
            hint={balanceRemaining === 0 ? 'No pending institutional dues' : 'Payable at college fee desk'}
            icon={balanceRemaining === 0 ? ShieldCheck : Clock}
            color={balanceRemaining === 0 ? 'var(--edvana-success)' : 'var(--edvana-warning)'}
          />
        </div>

        {/* Receipts Table */}
        <div className="edvana-card">
          <div className="edvana-card-header">
            <h2 className="edvana-card-title">Issued Payment Receipts ({payments.length})</h2>
            <p className="edvana-card-description">Official institutional challans and payment receipts with verifiable audit codes</p>
          </div>
          <div className="edvana-card-body" style={{ padding: 0 }}>
            {loading ? (
              <div style={{ padding: '2.5rem' }}>
                <LoadingState message="Retrieving payment receipts..." />
              </div>
            ) : payments.length === 0 ? (
              <div style={{ padding: '2.5rem' }}>
                <EmptyState
                  title="No Fee Payment Records Found"
                  message="If you recently completed payment, please allow the accounts desk up to 24 hours to reconcile and issue the receipt."
                />
              </div>
            ) : (
              <DataTable
                columns={columns}
                data={payments}
                keyExtractor={(p) => p.id}
                pageSize={5}
                emptyTitle="No Receipts"
                emptyMessage="No receipts available."
              />
            )}
          </div>
        </div>
      </div>

      {/* Printable Receipt Modal */}
      <Modal
        isOpen={Boolean(selectedReceipt)}
        onClose={() => setSelectedReceipt(null)}
        title="Official Institutional Fee Receipt"
        maxWidth="540px"
      >
        {selectedReceipt && (
          <div>
            <div style={{ textAlign: 'center', padding: '1rem', background: '#f8fafc', borderRadius: '8px', border: '1px solid #e2e8f0', marginBottom: '1.25rem' }}>
              <div style={{ fontSize: '0.75rem', fontWeight: 700, color: '#64748b', textTransform: 'uppercase', letterSpacing: '1px' }}>
                Government College of Engineering, Kolhapur
              </div>
              <div style={{ fontSize: '1.15rem', fontFamily: 'monospace', fontWeight: 700, color: 'var(--edvana-primary)', marginTop: '0.25rem' }}>
                {selectedReceipt.receipt_no}
              </div>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '140px 1fr', rowGap: '0.75rem', fontSize: '0.875rem', paddingBottom: '1.25rem', borderBottom: '1px solid #e2e8f0' }}>
              <div style={{ color: '#64748b' }}>Candidate Name:</div>
              <div style={{ fontWeight: 600, color: '#0f172a' }}>{selectedReceipt.student_name}</div>

              <div style={{ color: '#64748b' }}>PRN / Enrollment:</div>
              <div style={{ fontFamily: 'monospace', fontWeight: 600 }}>{selectedReceipt.enrollment_no || 'Pending'}</div>

              <div style={{ color: '#64748b' }}>Academic Session:</div>
              <div>{selectedReceipt.academic_year_code}</div>

              <div style={{ color: '#64748b' }}>Payment Date:</div>
              <div>{selectedReceipt.payment_date}</div>

              <div style={{ color: '#64748b' }}>Payment Channel:</div>
              <div>{selectedReceipt.payment_mode_display} ({selectedReceipt.transaction_ref || 'Counter'})</div>

              <div style={{ color: '#64748b' }}>Status:</div>
              <div>
                <Badge variant={getStatusBadgeVariant(selectedReceipt.status)}>
                  {selectedReceipt.status_display}
                </Badge>
              </div>
            </div>

            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '1rem 0', borderBottom: '1px solid #e2e8f0' }}>
              <span style={{ fontWeight: 600, color: '#334155' }}>Amount Paid:</span>
              <span style={{ fontSize: '1.25rem', fontWeight: 800, color: '#166534' }}>
                ₹{parseFloat(selectedReceipt.amount_paid).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
              </span>
            </div>

            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '0.75rem 0', fontSize: '0.875rem', color: '#64748b' }}>
              <span>Remaining Balance Due:</span>
              <span style={{ fontWeight: 600, color: '#0f172a' }}>
                ₹{parseFloat(selectedReceipt.balance_due).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
              </span>
            </div>

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem', paddingTop: '1.25rem', marginTop: '0.5rem' }}>
              <button
                type="button"
                onClick={() => setSelectedReceipt(null)}
                className="edvana-btn edvana-btn-secondary"
              >
                Close
              </button>
              <button
                type="button"
                onClick={() => window.print()}
                className="edvana-btn edvana-btn-primary"
                style={{ display: 'inline-flex', alignItems: 'center', gap: '0.5rem' }}
              >
                <Printer size={15} /> Print Receipt
              </button>
            </div>
          </div>
        )}
      </Modal>
    </>
  );
}
