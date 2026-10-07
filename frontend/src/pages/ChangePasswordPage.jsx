/**
 * ChangePasswordPage — EDVANA styled password update page.
 *
 * Used for:
 * 1. First-login mandatory password change (when must_change_password is true)
 *    at /change-password (outside AppLayout — forced by ProtectedRoute)
 * 2. Regular user-initiated password change at /account/security and
 *    /profile/security (inside AppLayout)
 *
 * The form itself lives in components/auth/PasswordChangeForm.jsx so that
 * each profile's Security tab renders the IDENTICAL experience (same fields,
 * same validation, same policy, same backend endpoint).
 *
 * Backend: POST /api/v1/auth/change-password/ (Identity & Access owns it).
 * No per-profile endpoint — one endpoint serves all roles.
 */
import { useNavigate, useLocation, Link } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { Lock, ArrowLeft } from 'lucide-react';
import PasswordChangeForm from '../components/auth/PasswordChangeForm';

export default function ChangePasswordPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const isMandatory = Boolean(user?.must_change_password);
  // Inside AppLayout when visited via /account/security or /profile/security.
  const isEmbeddedRoute =
    location.pathname.startsWith('/account/') || location.pathname.startsWith('/profile/');

  const handleSuccess = () => {
    // First-login forced flow: leave the gate and land on the dashboard.
    // Self-service flow (already inside the layout): stay and show success.
    if (!isEmbeddedRoute) {
      setTimeout(() => {
        navigate('/dashboard');
      }, 1500);
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
          <PasswordChangeForm embedded={isEmbeddedRoute} onSuccess={handleSuccess} />
          {isEmbeddedRoute && (
            <Link
              to="/profile"
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '0.4rem',
                marginTop: '1.25rem',
                fontSize: '0.8125rem',
                fontWeight: 600,
                color: 'var(--edvana-brand)',
                textDecoration: 'none',
              }}
            >
              <ArrowLeft size={14} />
              <span>Back to My Profile</span>
            </Link>
          )}
        </div>
      </div>
    </div>
  );
}

