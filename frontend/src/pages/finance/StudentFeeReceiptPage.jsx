import React, { useState, useEffect } from 'react';
import {
  IndianRupee, Printer, FileText,
  AlertCircle, ShieldCheck, X, ArrowRight, ReceiptText,
} from 'lucide-react';
import financeApi from '../../api/financeApi';
import clgLogo from '../../assets/icon.jpg';
import PageHeader from '../../components/common/PageHeader';
import Badge from '../../components/common/Badge';
import Modal from '../../components/common/Modal';
import { LoadingState, EmptyState } from '../../components/common/StateDisplays';

/* ── Small presentational bits, in EDVANA token style ─────────────── */

function StatusPill({ tone, children }) {
  const tones = {
    red: { bg: '#fde8e8', color: '#c62828', dot: '#f04438' },
    green: { bg: '#e6f7ec', color: '#1a7f37', dot: '#22a355' },
    amber: { bg: '#fef3c7', color: '#92400e', dot: '#d97706' },
  };
  const t = tones[tone] || tones.red;
  return (
    <span
      style={{
        display: 'inline-flex', alignItems: 'center', gap: '0.45rem',
        background: t.bg, color: t.color,
        fontSize: '0.78rem', fontWeight: 600,
        padding: '0.38rem 0.85rem', borderRadius: 999,
        whiteSpace: 'nowrap', lineHeight: 1.2,
      }}
    >
      <span style={{ width: 8, height: 8, borderRadius: '50%', background: t.dot, flexShrink: 0 }} />
      {children}
    </span>
  );
}

function FeeIcon() {
  return (
    <div
      style={{
        width: 48, height: 48, borderRadius: 14, flexShrink: 0,
        background: '#e8f1fe', color: '#1E60DC',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
      }}
    >
      <FileText size={24} strokeWidth={1.8} />
    </div>
  );
}

// Row card matching the reference: [icon | title | amount | status | action]
// Corners a touch rounder than the default edvana card (20px vs --edvana-radius-lg 14px,
// one step past --edvana-radius-xl 18px — same family, softer feel).
function FeeRowCard({ children }) {
  return (
    <div
      className="fee-row-card"
      style={{
        background: '#ffffff',
        border: '1px solid #e2e8f0',
        borderRadius: 20,
        boxShadow: '0 1px 2px rgba(16, 24, 40, 0.06), 0 10px 28px -12px rgba(15, 40, 90, 0.18)',
        padding: '1.15rem 1.75rem',
        display: 'flex', alignItems: 'center',
        gap: '2rem', flexWrap: 'wrap',
      }}
    >
      {children}
    </div>
  );
}

export default function StudentFeeReceiptPage() {
  const [payments, setPayments] = useState([]);
  const [onlineStatus, setOnlineStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [selectedReceipt, setSelectedReceipt] = useState(null);
  const [showBill, setShowBill] = useState(false);
  const [initiating, setInitiating] = useState(false);
  const [initError, setInitError] = useState(null);

  useEffect(() => {
    loadFeeData();
  }, []);

  const loadFeeData = async () => {
    setLoading(true);
    setError(null);
    try {
      const [paymentsRes, statusRes] = await Promise.allSettled([
        financeApi.getMyPayments(),
        financeApi.getOnlinePaymentStatus(),
      ]);

      if (paymentsRes.status === 'fulfilled') {
        setPayments(paymentsRes.value.data || []);
      }

      if (statusRes.status === 'fulfilled') {
        setOnlineStatus(statusRes.value.data);
      }
    } catch (err) {
      console.error('Failed to load fee payments:', err);
      setError('Could not retrieve fee receipts.');
    } finally {
      setLoading(false);
    }
  };

  const handleInitiatePayment = async () => {
    if (initiating) return; // Strict lock against rapid double-clicks
    setInitiating(true);
    setInitError(null);
    try {
      const assessId = onlineStatus?.assessment?.id || 'TERM';
      const res = await financeApi.initiateOnlinePayment(
        {},
        { 'Idempotency-Key': `IDEMP_FEE_${assessId}` }
      );
      if (res.data?.checkout_url) {
        // Redirect browser to Easebuzz hosted checkout
        window.location.href = res.data.checkout_url;
      } else {
        setInitError('Could not obtain payment gateway checkout URL.');
        setInitiating(false);
      }
    } catch (err) {
      const msg = err.response?.data?.detail || 'Failed to initiate payment. Please contact the accounts desk.';
      setInitError(msg);
      setInitiating(false);
    }
  };

  const totalPaid = payments.reduce((acc, p) => acc + parseFloat(p.amount_paid || 0), 0);
  const assessedTotal = onlineStatus?.assessment?.total_fee
    ? parseFloat(onlineStatus.assessment.total_fee)
    : payments.length > 0 ? parseFloat(payments[0].total_fee_due || 0) : 0;
  const balanceRemaining = Math.max(0, assessedTotal - totalPaid);
  const termCode = onlineStatus?.academic_year?.code
    || onlineStatus?.assessment?.academic_year_code
    || payments[0]?.academic_year_code
    || '2026-27';

  const hasDue = balanceRemaining > 0 && onlineStatus?.assessment;
  const isPartial = hasDue && totalPaid > 0;

  const feeBreakdown = onlineStatus?.assessment?.fee_breakdown || {};
  const breakdownEntries = Object.entries(feeBreakdown);

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

  const inr = (n) => `₹${parseFloat(n || 0).toLocaleString('en-IN', { minimumFractionDigits: 2 })}`;

  return (
    <>
      <PageHeader
        breadcrumbs={[
          { label: 'Home', to: '/dashboard' },
          { label: 'Student Portal' },
          { label: 'Payment History' },
        ]}
        title="Fee Payment"
        subtitle="Government College of Engineering, Kolhapur — Official Student Fee Ledger & Receipts."
      />

      <style>{`
        .fee-row-card .fee-title-block { flex: 1.6 1 280px; min-width: 0; }
        .fee-row-card .fee-amount-block { flex: 0.8 1 150px; min-width: 120px; }
        .fee-row-card .fee-status-block { flex: 0.9 1 170px; min-width: 140px; }
        .fee-row-card .fee-action-block { margin-left: auto; flex-shrink: 0; min-width: 170px; text-align: right; }
        @media (max-width: 720px) {
          .fee-row-card { gap: 1rem !important; padding: 1.1rem 1.2rem !important; }
          .fee-row-card .fee-action-block { margin-left: 0; width: 100%; }
          .fee-row-card .fee-action-block .edvana-btn { width: 100%; justify-content: center; }
        }
      `}</style>

      <div className="edvana-banner-overlap" style={{ paddingBottom: '3rem' }}>
        {error && (
          <div style={{ marginBottom: '1.5rem', padding: '1rem 1.25rem', background: '#fef2f2', border: '1px solid #fecaca', borderRadius: 16, color: '#991b1b', fontSize: '0.875rem', display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
            <AlertCircle size={20} style={{ flexShrink: 0 }} />
            <div>{error}</div>
          </div>
        )}

        {loading ? (
          <div className="edvana-card" style={{ borderRadius: 20, padding: '2.5rem' }}>
            <LoadingState message="Retrieving fee status..." />
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem', marginBottom: '0.5rem', background: '#eaeef4', borderRadius: 24, padding: '0.9rem' }}>
            {/* ── Outstanding due card (like reference row 1) ── */}
            {hasDue && (
              <FeeRowCard>
                <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }} className="fee-title-block">
                  <FeeIcon />
                  <div style={{ minWidth: 0 }}>
                    <div style={{ fontSize: '0.68rem', fontWeight: 600, letterSpacing: '0.05em', color: '#64748b' }}>
                      ACADEMIC YEAR {termCode}
                    </div>
                    <div style={{ fontSize: '1.02rem', fontWeight: 800, color: '#0f172a', marginTop: '0.1rem' }}>
                      Admission Fee
                    </div>
                  </div>
                </div>

                <div className="fee-amount-block">
                  <div style={{ fontSize: '0.75rem', color: '#64748b' }}>Amount Due</div>
                  <div style={{ fontSize: '1.25rem', fontWeight: 800, color: '#0f172a', marginTop: '0.1rem' }}>
                    {inr(balanceRemaining)}
                  </div>
                </div>

                <div className="fee-status-block">
                  {isPartial
                    ? <StatusPill tone="amber">Partially paid</StatusPill>
                    : <StatusPill tone="red">Payment Pending</StatusPill>}
                  {isPartial && (
                    <div style={{ fontSize: '0.75rem', color: '#64748b', marginTop: '0.4rem' }}>
                      Paid {inr(totalPaid)} of {inr(assessedTotal)}
                    </div>
                  )}
                </div>

                <div className="fee-action-block">
                  {onlineStatus.can_pay ? (
                    <button
                      type="button"
                      onClick={() => { setInitError(null); setShowBill(true); }}
                      className="edvana-btn edvana-btn-primary"
                      style={{
                        padding: '0.65rem 1.7rem', fontSize: '0.88rem', fontWeight: 700,
                        display: 'inline-flex', alignItems: 'center', gap: '0.5rem',
                        borderRadius: 12, background: '#1E60DC', border: '1px solid #1E60DC',
                        boxShadow: '0 4px 14px rgba(30, 96, 220, 0.30)',
                      }}
                    >
                      Pay Now <ArrowRight size={16} />
                    </button>
                  ) : onlineStatus.in_flight_attempt ? (
                    <a
                      href={`/fees/payment/${onlineStatus.in_flight_attempt.id}`}
                      className="edvana-btn edvana-btn-secondary"
                      style={{ padding: '0.65rem 1.3rem', fontSize: '0.85rem', borderRadius: 12 }}
                    >
                      Check Pending Payment
                    </a>
                  ) : (
                    <span style={{ fontSize: '0.8rem', color: '#b45309', fontWeight: 500, maxWidth: 220, display: 'inline-block' }}>
                      {onlineStatus.reason || 'Online payment is currently disabled.'}
                    </span>
                  )}
                </div>
              </FeeRowCard>
            )}

            {/* ── Paid cards (like reference row 2) ── */}

            {payments.map((p) => (
              <FeeRowCard key={p.id}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }} className="fee-title-block">
                  <FeeIcon />
                  <div style={{ minWidth: 0 }}>
                    <div style={{ fontSize: '0.68rem', fontWeight: 600, letterSpacing: '0.05em', color: '#64748b' }}>
                      ACADEMIC YEAR {p.academic_year_code || termCode}
                    </div>
                    <div style={{ fontSize: '1.02rem', fontWeight: 800, color: '#0f172a', marginTop: '0.1rem' }}>
                      Admission Fee
                    </div>
                    <div style={{ fontSize: '0.78rem', color: '#64748b', marginTop: '0.15rem' }}>
                      {p.academic_year_code || termCode} &nbsp;|&nbsp; {p.payment_mode_display || 'Regular Admission'}
                    </div>
                  </div>
                </div>

                <div className="fee-amount-block">
                  <div style={{ fontSize: '0.75rem', color: '#64748b' }}>Amount Due</div>
                  <div style={{ fontSize: '1.25rem', fontWeight: 800, color: '#0f172a', marginTop: '0.1rem' }}>
                    ₹{parseFloat(p.amount_paid).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                  </div>
                </div>

                <div className="fee-status-block">
                  <StatusPill tone="green">Paid</StatusPill>
                  <div style={{ fontSize: '0.75rem', color: '#64748b', marginTop: '0.4rem' }}>
                    Paid on {p.payment_date || '—'}
                  </div>
                </div>

                <div className="fee-action-block">
                  <button
                    type="button"
                    onClick={() => setSelectedReceipt(p)}
                    className="edvana-btn"
                    style={{
                      padding: '0.65rem 1.4rem', fontSize: '0.85rem', fontWeight: 700,
                      display: 'inline-flex', alignItems: 'center', gap: '0.5rem',
                      borderRadius: 12, background: '#ffffff', color: '#1E60DC',
                      border: '1px solid #bfd0ee',
                    }}
                  >
                    <ReceiptText size={16} /> View Receipt
                  </button>
                </div>
              </FeeRowCard>
            ))}

            {/* ── Empty state ── */}
            {!hasDue && payments.length === 0 && (
              <div className="edvana-card" style={{ borderRadius: 20, padding: '2.5rem' }}>
                <EmptyState
                  title="No Fee Records Found"
                  message="If you recently completed payment, please allow the accounts desk up to 24 hours to reconcile and issue the receipt."
                />
              </div>
            )}

            {/* ── All-clear note ── */}
            {!hasDue && payments.length > 0 && (
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.8rem', color: '#94a3b8', padding: '0.25rem 0.4rem' }}>
                <ShieldCheck size={14} />
                <span>All dues settled · Secure payment via Easebuzz · SSL 256-bit encrypted</span>
              </div>
            )}
          </div>
        )}
      </div>

      {/* ── Detailed bill popup (Pay Now flow) ─────────────────────── */}
      <Modal
        isOpen={showBill}
        onClose={() => { if (!initiating) setShowBill(false); }}
        title={`Fee Bill — Term ${termCode}`}
        maxWidth="560px"
      >
        <div style={{ paddingTop: '0.25rem' }}>
          <div style={{
            display: 'flex', justifyContent: 'space-between', alignItems: 'center',
            background: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: 16,
            padding: '1rem 1.25rem', marginBottom: '1.25rem',
          }}>
            <div>
              <div style={{ fontSize: '0.72rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.06em', color: '#64748b' }}>
                Total payable
              </div>
              <div style={{ fontSize: '1.5rem', fontWeight: 800, color: '#0f172a', marginTop: '0.15rem' }}>
                {inr(onlineStatus?.assessment?.total_fee)}
              </div>
            </div>
            <div style={{ textAlign: 'right', fontSize: '0.78rem', color: '#64748b', lineHeight: 1.6 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', justifyContent: 'flex-end', color: '#1e40af', fontWeight: 600 }}>
                <FileText size={14} /> Admission Fee
              </div>
              <div>Already paid: {inr(totalPaid)}</div>
            </div>
          </div>

          {initError && (
            <div style={{ marginBottom: '1rem', padding: '0.75rem 1rem', background: '#fef2f2', border: '1px solid #fecaca', borderRadius: 12, color: '#991b1b', fontSize: '0.85rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <AlertCircle size={16} style={{ flexShrink: 0 }} />
              <div>{initError}</div>
            </div>
          )}

          {/* Breakdown */}
          <div style={{ border: '1px solid #eef2f7', borderRadius: 16, overflow: 'hidden', marginBottom: '1.25rem' }}>
            {breakdownEntries.map(([head, amt], i) => (
              <div
                key={head}
                style={{
                  display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                  padding: '0.85rem 1.2rem', fontSize: '0.9rem',
                  background: i % 2 === 0 ? '#ffffff' : '#f8fafc',
                  borderBottom: i === breakdownEntries.length - 1 ? 'none' : '1px solid #f1f5f9',
                }}
              >
                <span style={{ color: '#334155' }}>{head}</span>
                <span style={{ fontWeight: 700, color: '#0f172a' }}>₹{parseFloat(amt).toLocaleString('en-IN', { minimumFractionDigits: 2 })}</span>
              </div>
            ))}
            <div style={{
              display: 'flex', justifyContent: 'space-between', alignItems: 'center',
              padding: '0.95rem 1.2rem', background: '#f0fdf4',
              borderTop: '1px solid #dcfce7', fontWeight: 800,
            }}>
              <span style={{ color: '#0f172a' }}>Total</span>
              <span style={{ color: '#166534', fontSize: '1.05rem' }}>{inr(onlineStatus?.assessment?.total_fee)}</span>
            </div>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.78rem', color: '#94a3b8', marginBottom: '1.4rem' }}>
            <ShieldCheck size={14} />
            <span>You will be redirected to the secure Easebuzz checkout. An official receipt is generated automatically after payment.</span>
          </div>

          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem' }}>
            <button
              type="button"
              onClick={() => { if (!initiating) setShowBill(false); }}
              className="edvana-btn edvana-btn-secondary"
              style={{ padding: '0.65rem 1.3rem', borderRadius: 12 }}
              disabled={initiating}
            >
              <span style={{ display: 'inline-flex', alignItems: 'center', gap: '0.4rem' }}>
                <X size={15} /> Cancel
              </span>
            </button>
            <button
              type="button"
              onClick={handleInitiatePayment}
              disabled={initiating}
              className="edvana-btn edvana-btn-primary"
              style={{
                padding: '0.65rem 1.8rem', fontWeight: 700, borderRadius: 12,
                display: 'inline-flex', alignItems: 'center', gap: '0.5rem',
                background: '#1E60DC', opacity: initiating ? 0.75 : 1,
              }}
            >
              <IndianRupee size={16} />
              {initiating ? 'Connecting…' : `Pay Now ${inr(onlineStatus?.assessment?.total_fee)}`}
            </button>
          </div>
        </div>
      </Modal>

      {/* Printable Receipt Modal */}
      <Modal
        isOpen={Boolean(selectedReceipt)}
        onClose={() => setSelectedReceipt(null)}
        title="Official Institutional Fee Receipt"
        maxWidth="540px"
      >
        {selectedReceipt && (
          <div>
            <div style={{ padding: '1rem 1.1rem', background: '#f8fafc', borderRadius: 12, border: '1px solid #e2e8f0', marginBottom: '1.25rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.85rem' }}>
                <img
                  src={clgLogo}
                  alt="GCE Kolhapur emblem"
                  style={{ width: 52, height: 52, borderRadius: '50%', objectFit: 'cover', border: '1px solid #e2e8f0', background: '#ffffff', flexShrink: 0 }}
                />
                <div style={{ minWidth: 0 }}>
                  <div style={{ fontSize: '0.88rem', fontWeight: 800, color: '#0f172a', lineHeight: 1.3 }}>
                    Government College of Engineering, Kolhapur
                  </div>
                  <div style={{ fontSize: '0.72rem', color: '#64748b', marginTop: '0.15rem' }}>
                    DBATU Institute · Official Fee Receipt
                  </div>
                </div>
              </div>
              <div style={{ borderTop: '1px dashed #e2e8f0', marginTop: '0.85rem', paddingTop: '0.7rem', textAlign: 'center' }}>
                <div style={{ fontSize: '0.65rem', fontWeight: 700, color: '#64748b', textTransform: 'uppercase', letterSpacing: '1px' }}>
                  Receipt No.
                </div>
                <div style={{ fontSize: '1.15rem', fontFamily: 'monospace', fontWeight: 700, color: 'var(--edvana-primary)', marginTop: '0.2rem' }}>
                  {selectedReceipt.receipt_no}
                </div>
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
