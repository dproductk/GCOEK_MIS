/**
 * PasswordChangeForm — reusable password update form.
 *
 * Single source of truth for password changes across the app.
 * Used by:
 * 1. ChangePasswordPage (first-login mandatory flow at /change-password
 *    + self-service at /account/security and /profile/security)
 * 2. StudentProfilePage "Security" tab (own profile)
 * 3. FacultyProfilePage "Security" tab (own profile — covers Faculty,
 *    Class Teacher, HOD, Accountant, Admin Head, Sysadmin via
 *    ProfileDispatcher)
 *
 * Domain owner: Identity & Access (backend: POST /api/v1/auth/change-password/).
 * No new backend endpoint — this form calls AuthContext.changePassword(),
 * which enforces server-side: current-password verification, min 12 chars,
 * last-5 password history, and audit logging (SECURITY.md Sec 2.2 + 12).
 *
 * Props:
 * - embedded (bool): when true, renders only the form body (alerts + fields
 *   + policy + submit) so the caller can wrap it in its own profile card.
 *   When false (default), renders the full centered EDVANA card identical
 *   to the first-login experience.
 * - onSuccess (func): optional callback invoked with the success message
 *   after a successful change (e.g. to navigate away).
 */
import { useState } from 'react';
import { useAuth } from '../../context/AuthContext';
import { Eye, EyeOff, ShieldAlert, CheckCircle, ArrowRight, ShieldCheck } from 'lucide-react';
import FormField from '../common/FormField';
import Spinner from '../common/Spinner';

export default function PasswordChangeForm({ embedded = false, onSuccess = null }) {
  const { changePassword } = useAuth();

  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [showCurrent, setShowCurrent] = useState(false);
  const [showNew, setShowNew] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);

  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState('');
  const [successMessage, setSuccessMessage] = useState('');

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
        const msg = 'Password changed successfully!';
        setSuccessMessage(embedded ? msg : `${msg} Redirecting...`);
        setCurrentPassword('');
        setNewPassword('');
        setConfirmPassword('');
        if (onSuccess) {
          onSuccess(result.message || msg);
        }
      } else {
        setErrorMessage(result.error || 'Failed to update password.');
      }
    } catch {
      setErrorMessage('An unexpected error occurred. Please try again.');
    } finally {
      setIsSubmitting(false);
    }
  };

  const eyeButtonStyle = {
    position: 'absolute',
    right: '10px',
    top: '50%',
    transform: 'translateY(-50%)',
    background: 'none',
    border: 'none',
    cursor: 'pointer',
    color: 'var(--edvana-text-muted)',
  };

  const formBody = (
    <>
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
          role="alert"
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
          role="status"
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
              autoComplete="current-password"
              style={{ paddingRight: '40px' }}
            />
            <button
              type="button"
              onClick={() => setShowCurrent(!showCurrent)}
              style={eyeButtonStyle}
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
              autoComplete="new-password"
              style={{ paddingRight: '40px' }}
            />
            <button
              type="button"
              onClick={() => setShowNew(!showNew)}
              style={eyeButtonStyle}
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
              autoComplete="new-password"
              style={{ paddingRight: '40px' }}
            />
            <button
              type="button"
              onClick={() => setShowConfirm(!showConfirm)}
              style={eyeButtonStyle}
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
          disabled={isSubmitting || (!embedded && !!successMessage)}
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
    </>
  );

  // Embedded mode: caller provides the surrounding profile card.
  if (embedded) {
    return formBody;
  }

  // Standalone page mode is handled by ChangePasswordPage's card chrome;
  // this fallback renders the bare form for any direct usage.
  return formBody;
}
