/**
 * Shared UI state components — Loading, Error, Empty.
 * Consistent state representations across all pages.
 */
import { AlertCircle, Inbox, RefreshCw, ArrowLeft } from 'lucide-react';
import Spinner from './Spinner';

/**
 * Full-page or section loading state.
 */
export function LoadingState({ message = 'Loading details, please wait...', fullHeight = false }) {
  return (
    <div
      className="state-container"
      style={{
        minHeight: fullHeight ? '60vh' : '260px',
        backgroundColor: 'var(--edvana-card-bg)',
        borderRadius: 'var(--edvana-radius-lg)',
        border: '1px solid var(--edvana-border)',
        margin: '1rem 0',
      }}
    >
      <Spinner size="lg" />
      <p
        className="state-message"
        style={{
          marginTop: '1.25rem',
          fontWeight: 500,
          color: 'var(--edvana-text-secondary)',
        }}
      >
        {message}
      </p>
    </div>
  );
}

/**
 * Error state with retry action and optional back navigation.
 */
export function ErrorState({
  title = 'Something went wrong',
  message = '',
  onRetry,
  onBack,
  fullHeight = false,
}) {
  return (
    <div
      className="state-container"
      style={{
        minHeight: fullHeight ? '60vh' : '260px',
        backgroundColor: 'var(--edvana-card-bg)',
        borderRadius: 'var(--edvana-radius-lg)',
        border: '1px solid var(--edvana-border)',
        margin: '1rem 0',
        padding: '2.5rem 1.5rem',
      }}
    >
      <div
        style={{
          width: 56,
          height: 56,
          borderRadius: '50%',
          backgroundColor: 'var(--edvana-danger-soft)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          marginBottom: '1rem',
          border: '1px solid var(--edvana-danger-border)',
        }}
      >
        <AlertCircle size={28} style={{ color: 'var(--edvana-danger)' }} />
      </div>
      <h3 className="state-title" style={{ color: 'var(--edvana-text-primary)', marginBottom: '0.35rem' }}>
        {title}
      </h3>
      {message && (
        <p className="state-message" style={{ color: 'var(--edvana-text-secondary)', maxWidth: 440 }}>
          {message}
        </p>
      )}
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginTop: '1.25rem' }}>
        {onBack && (
          <button className="edvana-btn edvana-btn-outline" onClick={onBack}>
            <ArrowLeft size={16} />
            Go Back
          </button>
        )}
        {onRetry && (
          <button className="edvana-btn edvana-btn-primary" onClick={onRetry}>
            <RefreshCw size={16} />
            Try Again
          </button>
        )}
      </div>
    </div>
  );
}

/**
 * Empty state when no data is available.
 */
export function EmptyState({
  title = 'No records found',
  message = '',
  icon: Icon = Inbox,
  action,
}) {
  return (
    <div
      className="state-container"
      style={{
        minHeight: '240px',
        backgroundColor: 'var(--edvana-card-bg)',
        borderRadius: 'var(--edvana-radius-lg)',
        border: '1px solid var(--edvana-border)',
        margin: '1rem 0',
        padding: '2.5rem 1.5rem',
      }}
    >
      <div
        style={{
          width: 52,
          height: 52,
          borderRadius: '50%',
          backgroundColor: 'var(--edvana-panel-bg)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          marginBottom: '1rem',
          border: '1px solid var(--edvana-border)',
        }}
      >
        <Icon size={26} style={{ color: 'var(--edvana-text-muted)' }} />
      </div>
      <h3 className="state-title" style={{ fontSize: '1rem', marginBottom: '0.25rem' }}>
        {title}
      </h3>
      {message && (
        <p className="state-message" style={{ fontSize: '0.8125rem' }}>
          {message}
        </p>
      )}
      {action && <div className="state-action" style={{ marginTop: '1rem' }}>{action}</div>}
    </div>
  );
}

