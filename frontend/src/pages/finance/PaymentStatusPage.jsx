import React, { useState, useEffect } from 'react';
import { useParams, useNavigate, useSearchParams, Link } from 'react-router-dom';
import { 
  CheckCircle2, AlertCircle, Clock, RotateCcw, 
  Receipt, ArrowLeft, Printer, ShieldCheck, IndianRupee, ExternalLink
} from 'lucide-react';
import financeApi from '../../api/financeApi';
import PageHeader from '../../components/common/PageHeader';
import Modal from '../../components/common/Modal';
import Badge from '../../components/common/Badge';

export default function PaymentStatusPage() {
  const { attemptId } = useParams();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();

  const isMockCheckout = window.location.pathname.includes('mock-checkout');
  const mockTxnId = searchParams.get('txnid');
  const mockAccessKey = searchParams.get('access_key');
  const errorReason = searchParams.get('reason');

  const [attempt, setAttempt] = useState(null);
  const [receipt, setReceipt] = useState(null);
  const [loading, setLoading] = useState(!isMockCheckout && !errorReason);
  const [verifying, setVerifying] = useState(false);
  const [error, setError] = useState(errorReason ? `Payment callback returned: ${errorReason}` : null);
  const [selectedReceiptModal, setSelectedReceiptModal] = useState(false);

  useEffect(() => {
    if (attemptId && !isMockCheckout) {
      pollAttemptStatus();
    }
  }, [attemptId]);

  const pollAttemptStatus = async () => {
    try {
      setLoading(true);
      const res = await financeApi.getPaymentAttempt(attemptId);
      setAttempt(res.data);
      if (res.data?.receipt) {
        setReceipt(res.data.receipt);
      }
    } catch (err) {
      setError('Could not retrieve payment attempt status.');
    } finally {
      setLoading(false);
    }
  };

  const handleManualVerify = async () => {
    setVerifying(true);
    try {
      const res = await financeApi.verifyPaymentAttempt(attemptId);
      await pollAttemptStatus();
    } catch (err) {
      setError('Verification inquiry failed. Please retry in a few moments.');
    } finally {
      setVerifying(false);
    }
  };

  // Mock sandbox completion for local testing
  const handleSimulateMockResult = (statusValue) => {
    const form = document.createElement('form');
    form.method = 'POST';
    form.action = '/api/v1/finance/online-payment/callback/';

    const addField = (name, val) => {
      const inp = document.createElement('input');
      inp.type = 'hidden';
      inp.name = name;
      inp.value = val;
      form.appendChild(inp);
    };

    addField('txnid', mockTxnId);
    addField('status', statusValue);
    addField('easepayid', `MOCK_EASEPAY_${Date.now()}`);
    addField('amount', '45000.00');
    addField('mode', 'UPI');
    addField('hash', 'mock_verified_hash');

    document.body.appendChild(form);
    form.submit();
  };

  if (isMockCheckout) {
    return (
      <div style={{ padding: '2rem', maxWidth: '600px', margin: '3rem auto' }}>
        <div className="edvana-card" style={{ padding: '2rem', textAlign: 'center' }}>
          <div style={{ display: 'inline-flex', padding: '0.75rem', background: '#eff6ff', borderRadius: '50%', color: '#1E60DC', marginBottom: '1rem' }}>
            <ShieldCheck size={36} />
          </div>
          <h2 style={{ fontSize: '1.4rem', fontWeight: 700, color: '#0f172a', marginBottom: '0.5rem' }}>
            Easebuzz Sandbox Payment Simulator
          </h2>
          <p style={{ fontSize: '0.875rem', color: '#64748b', marginBottom: '1.5rem' }}>
            Transaction Ref: <code style={{ color: '#1E60DC', fontWeight: 700 }}>{mockTxnId}</code>
          </p>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.85rem' }}>
            <button
              onClick={() => handleSimulateMockResult('success')}
              className="edvana-btn edvana-btn-primary"
              style={{ padding: '0.75rem', fontSize: '0.9rem', fontWeight: 600, background: '#16a34a' }}
            >
              Simulate Successful Payment (Authorize ₹45,000)
            </button>
            <button
              onClick={() => handleSimulateMockResult('userCancelled')}
              className="edvana-btn edvana-btn-secondary"
              style={{ padding: '0.75rem', fontSize: '0.9rem', color: '#dc2626' }}
            >
              Simulate User Cancellation / Decline
            </button>
          </div>
        </div>
      </div>
    );
  }

  const isSuccess = attempt?.status === 'SUCCESS';
  const isFailed = attempt?.status === 'FAILED' || attempt?.status === 'CANCELLED' || attempt?.status === 'EXPIRED';
  const isPending = attempt?.status === 'PENDING' || attempt?.status === 'REDIRECTED' || attempt?.status === 'INITIATED';

  return (
    <>
      <PageHeader
        breadcrumbs={[
          { label: 'Home', to: '/dashboard' },
          { label: 'Payment History', to: '/my-fees' },
          { label: 'Payment Status' },
        ]}
        title="Online Fee Payment Status"
        subtitle="Government College of Engineering, Kolhapur — Gateway Reconciliation & Receipt Verification."
      />

      <div className="edvana-banner-overlap" style={{ maxWidth: '680px', margin: '0 auto' }}>
        <div className="edvana-card" style={{ padding: '2.5rem 2rem', textAlign: 'center' }}>
          {loading ? (
            <div style={{ padding: '2rem 0' }}>
              <div style={{ display: 'inline-block', width: '40px', height: '40px', border: '3px solid #e2e8f0', borderTopColor: '#1E60DC', borderRadius: '50%', animation: 'spin 1s linear infinite' }} />
              <div style={{ marginTop: '1rem', color: '#64748b', fontSize: '0.9rem' }}>
                Verifying transaction with Easebuzz gateway...
              </div>
            </div>
          ) : isSuccess ? (
            <div>
              <div style={{ display: 'inline-flex', padding: '1rem', background: '#dcfce7', borderRadius: '50%', color: '#16a34a', marginBottom: '1.25rem' }}>
                <CheckCircle2 size={48} />
              </div>

              <h2 style={{ fontSize: '1.5rem', fontWeight: 800, color: '#0f172a', marginBottom: '0.5rem' }}>
                Payment Successfully Completed!
              </h2>
              <p style={{ fontSize: '0.9rem', color: '#64748b', marginBottom: '1.75rem' }}>
                Your institutional admission fee has been officially recorded and an official college receipt has been generated.
              </p>

              {/* Transaction Summary Card */}
              <div style={{ background: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: '10px', padding: '1.25rem', textAlign: 'left', marginBottom: '1.75rem' }}>
                <div style={{ display: 'grid', gridTemplateColumns: '160px 1fr', rowGap: '0.65rem', fontSize: '0.875rem' }}>
                  <span style={{ color: '#64748b' }}>Candidate:</span>
                  <strong style={{ color: '#0f172a' }}>{attempt.student_name}</strong>

                  <span style={{ color: '#64748b' }}>Official Receipt No:</span>
                  <span style={{ fontFamily: 'monospace', fontWeight: 700, color: '#1E60DC' }}>
                    {receipt?.receipt_no || 'GCOEK Receipt Generated'}
                  </span>

                  <span style={{ color: '#64748b' }}>Amount Paid:</span>
                  <strong style={{ color: '#166534', fontSize: '1rem' }}>
                    ₹{parseFloat(attempt.amount).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                  </strong>

                  <span style={{ color: '#64748b' }}>Easebuzz Ref:</span>
                  <span style={{ fontFamily: 'monospace', color: '#475569' }}>
                    {attempt.easebuzz_txn_id || attempt.transaction_id}
                  </span>

                  <span style={{ color: '#64748b' }}>Payment Mode:</span>
                  <span>{attempt.payment_mode || 'Online Gateway'}</span>
                </div>
              </div>

              {/* Actions */}
              <div style={{ display: 'flex', flexWrap: 'wrap', justifyContent: 'center', gap: '1rem' }}>
                <Link
                  to="/my-fees"
                  className="edvana-btn edvana-btn-primary"
                  style={{ display: 'inline-flex', alignItems: 'center', gap: '0.5rem', padding: '0.6rem 1.5rem', background: '#1E60DC' }}
                >
                  <Receipt size={16} /> View & Print Receipt
                </Link>
                <Link
                  to="/dashboard"
                  className="edvana-btn edvana-btn-secondary"
                  style={{ padding: '0.6rem 1.5rem' }}
                >
                  Go to Dashboard
                </Link>
              </div>
            </div>
          ) : isPending ? (
            <div>
              <div style={{ display: 'inline-flex', padding: '1rem', background: '#fef3c7', borderRadius: '50%', color: '#d97706', marginBottom: '1.25rem' }}>
                <Clock size={48} />
              </div>

              <h2 style={{ fontSize: '1.4rem', fontWeight: 700, color: '#0f172a', marginBottom: '0.5rem' }}>
                Payment Verification Pending
              </h2>
              <p style={{ fontSize: '0.875rem', color: '#64748b', marginBottom: '1.5rem', lineHeight: 1.5 }}>
                We are awaiting confirmation from your bank or the Easebuzz gateway. If money was debited from your account, it will be automatically confirmed within a few minutes.
              </p>

              <div style={{ display: 'flex', justifyContent: 'center', gap: '1rem' }}>
                <button
                  onClick={handleManualVerify}
                  disabled={verifying}
                  className="edvana-btn edvana-btn-primary"
                  style={{ display: 'inline-flex', alignItems: 'center', gap: '0.5rem' }}
                >
                  <RotateCcw size={15} />
                  {verifying ? 'Inquiring...' : 'Re-Check Status with Bank'}
                </button>
                <Link to="/my-fees" className="edvana-btn edvana-btn-secondary">
                  Back to Fees
                </Link>
              </div>
            </div>
          ) : (
            <div>
              <div style={{ display: 'inline-flex', padding: '1rem', background: '#fee2e2', borderRadius: '50%', color: '#dc2626', marginBottom: '1.25rem' }}>
                <AlertCircle size={48} />
              </div>

              <h2 style={{ fontSize: '1.4rem', fontWeight: 700, color: '#0f172a', marginBottom: '0.5rem' }}>
                Payment Failed or Cancelled
              </h2>
              <p style={{ fontSize: '0.875rem', color: '#64748b', marginBottom: '1.5rem' }}>
                {attempt?.failure_reason || error || 'The transaction could not be completed.'}
              </p>

              <div style={{ display: 'flex', justifyContent: 'center', gap: '1rem' }}>
                <Link
                  to="/my-fees"
                  className="edvana-btn edvana-btn-primary"
                  style={{ display: 'inline-flex', alignItems: 'center', gap: '0.5rem' }}
                >
                  <RotateCcw size={15} /> Return to Fees & Retry
                </Link>
              </div>
            </div>
          )}
        </div>
      </div>
    </>
  );
}
