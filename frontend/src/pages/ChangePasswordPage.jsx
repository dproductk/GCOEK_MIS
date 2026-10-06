/**
 * ChangePasswordPage — EDVANA styled password update page.
 *
 * Used for:
 * 1. First-login mandatory password change (when must_change_password is true)
 * 2. Regular user-initiated password change
 *
 * Enforces:
 * - Current password verification
 * - Minimum 12 characters
 * - Confirmation match
 * - Server-enforced password history of 5
 */
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { Lock, Eye, EyeOff, ShieldAlert, CheckCircle, ArrowRight, ShieldCheck } from 'lucide-react';
import FormField from '../components/common/FormField';
import Spinner from '../components/common/Spinner';

export default function ChangePasswordPage() {
  const { user, changePassword } = useAuth();
  const navigate = useNavigate();

  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [showCurrent, setShowCurrent] = useState(false);
  const [showNew, setShowNew] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);

  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState('');
  const [successMessage, setSuccessMessage] = useState('');

  const isMandatory = user?.must_change_password;

  const handleSubmit = async (e) => {
    e.preventDefault();
    setErrorMessage('');
    setSuccessMessage('');

    if (newPassword.length < 12) {
      setErrorMessage('New password must be at least 12 characters long.');
      return;
    }

    if (newPassword !== confirmPassword) {
      setErrorMessage('New password and confirmation do not match.');
      return;
    }

    if (currentPassword === newPassword) {
      setErrorMessage('New password must be different from current password.');
      return;
    }

    setIsSubmitting(true);
    try {
      const result = await changePassword(currentPassword, newPassword, confirmPassword);
      if (result.success) {
        setSuccessMessage('Password changed successfully! Redirecting...');
        setTimeout(() => {
          navigate('/dashboard');
        }, 1500);
      } else {
        setErrorMessage(result.error || 'Failed to update password.');
      }
    } catch {
      setErrorMessage('An unexpected error occurred. Please try again.');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div
      style={{
        minHeight: '80vh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '2rem 1rem',
      }}
    >
      <div
        className="edvana-card"
        style={{
          width: '100%',
          maxWidth: '480px',
          boxShadow: 'var(--edvana-shadow-elevated)',
        }}
      >
        <div
          style={{
            padding: '2rem 2rem 1.25rem 2rem',
            textAlign: 'center',
            borderBottom: '1px solid var(--edvana-border)',
          }}
        >
          <div
            style={{
              width: 52,
              height: 52,
              borderRadius: '50%',
              backgroundColor: 'var(--edvana-brand-soft)',
              color: 'var(--edvana-brand)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              margin: '0 auto 1rem',
              border: '1px solid var(--edvana-brand-soft-border)',
            }}
          >
            <Lock size={24} />
          </div>
          <h1 className="edvana-card-title" style={{ fontSize: '1.25rem', marginBottom: '0.35rem' }}>
            {isMandatory ? 'Set New Password' : 'Change Password'}
          </h1>
          <p className="edvana-card-description">
            {isMandatory
              ? 'First-time login: Please update your password to secure your account.'
              : 'Choose a strong, unique password for your account.'}
          </p>
        </div>

        <div className="edvana-card-body" style={{ padding: '1.75rem 2rem' }}>
          {errorMessage && (
            <div
              className="edvana-badge-danger"
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '0.5rem',
                marginBottom: '1.25rem',
                padding: '0.75rem 1rem',
                borderRadius: 'var(--edvana-radius-md)',
                fontSize: '0.8125rem',
                width: '100%',
              }}
            >
              <ShieldAlert size={18} style={{ flexShrink: 0 }} />
              <span>{errorMessage}</span>
            </div>
          )}

          {successMessage && (
            <div
              className="edvana-badge-success"
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '0.5rem',
                marginBottom: '1.25rem',
                padding: '0.75rem 1rem',
                borderRadius: 'var(--edvana-radius-md)',
                fontSize: '0.8125rem',
                width: '100%',
              }}
            >
              <CheckCircle size={18} style={{ flexShrink: 0 }} />
              <span>{successMessage}</span>
            </div>
          )}

          <form onSubmit={handleSubmit}>
            <FormField label="Current Password" required id="currentPassword">
              <div style={{ position: 'relative' }}>
                <input
                  id="currentPassword"
                  type={showCurrent ? 'text' : 'password'}
                  className="edvana-input"
                  placeholder="Enter current password"
                  value={currentPassword}
                  onChange={(e) => setCurrentPassword(e.target.value)}
                  required
                  style={{ paddingRight: '40px' }}
                />
                <button
                  type="button"
                  onClick={() => setShowCurrent(!showCurrent)}
                  style={{
                    position: 'absolute',
                    right: '10px',
                    top: '50%',
                    transform: 'translateY(-50%)',
                    background: 'none',
                    border: 'none',
                    cursor: 'pointer',
                    color: 'var(--edvana-text-muted)',
                  }}
                  aria-label="Toggle current password visibility"
                >
                  {showCurrent ? <EyeOff size={18} /> : <Eye size={18} />}
                </button>
              </div>
            </FormField>

            <FormField label="New Password" required id="newPassword" help="Minimum 12 characters">
              <div style={{ position: 'relative' }}>
                <input
                  id="newPassword"
                  type={showNew ? 'text' : 'password'}
                  className="edvana-input"
                  placeholder="Enter new password (min. 12 characters)"
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  required
                  style={{ paddingRight: '40px' }}
                />
                <button
                  type="button"
                  onClick={() => setShowNew(!showNew)}
                  style={{
                    position: 'absolute',
                    right: '10px',
                    top: '50%',
                    transform: 'translateY(-50%)',
                    background: 'none',
                    border: 'none',
                    cursor: 'pointer',
                    color: 'var(--edvana-text-muted)',
                  }}
                  aria-label="Toggle new password visibility"
                >
                  {showNew ? <EyeOff size={18} /> : <Eye size={18} />}
                </button>
              </div>
            </FormField>

            <FormField label="Confirm New Password" required id="confirmPassword">
              <div style={{ position: 'relative' }}>
                <input
                  id="confirmPassword"
                  type={showConfirm ? 'text' : 'password'}
                  className="edvana-input"
                  placeholder="Re-enter new password"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  required
                  style={{ paddingRight: '40px' }}
                />
                <button
                  type="button"
                  onClick={() => setShowConfirm(!showConfirm)}
                  style={{
                    position: 'absolute',
                    right: '10px',
                    top: '50%',
                    transform: 'translateY(-50%)',
                    background: 'none',
                    border: 'none',
                    cursor: 'pointer',
                    color: 'var(--edvana-text-muted)',
                  }}
                  aria-label="Toggle confirm password visibility"
                >
                  {showConfirm ? <EyeOff size={18} /> : <Eye size={18} />}
                </button>
              </div>
            </FormField>

            <div
              style={{
                backgroundColor: 'var(--edvana-panel-bg)',
                borderRadius: 'var(--edvana-radius-md)',
                padding: '0.75rem 1rem',
                fontSize: '0.75rem',
                color: 'var(--edvana-text-secondary)',
                marginBottom: '1.5rem',
                border: '1px solid var(--edvana-border)',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', fontWeight: 600, color: 'var(--edvana-text-primary)' }}>
                <ShieldCheck size={14} />
                <span>Security Policy</span>
              </div>
              <ul style={{ margin: '6px 0 0 16px', padding: 0 }}>
                <li>At least 12 characters in length</li>
                <li>Cannot be the same as your current password</li>
                <li>Cannot reuse any of your last 5 passwords</li>
              </ul>
            </div>

            <button
              type="submit"
              className="edvana-btn edvana-btn-primary"
              disabled={isSubmitting || !!successMessage}
              style={{ width: '100%', padding: '0.625rem 1rem' }}
            >
              {isSubmitting ? (
                <>
                  <Spinner size="sm" />
                  <span>Updating Password...</span>
                </>
              ) : (
                <>
                  <span>Update Password</span>
                  <ArrowRight size={16} />
                </>
              )}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}

