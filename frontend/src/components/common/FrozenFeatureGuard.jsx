import { useEffect, useState } from 'react';

const THROTTLE_MS = 30 * 1000;

function shouldShowPopup(key) {
  try {
    const last = Number(localStorage.getItem(key) || '0');
    const now = Date.now();
    if (now - last < THROTTLE_MS) return false;
    localStorage.setItem(key, String(now));
    return true;
  } catch {
    return true;
  }
}

/**
 * FrozenFeatureGuard — frontend-only freeze notice.
 * Shows "Feature under development" popup at most once per 30s per key,
 * plus a persistent inline banner. No backend calls (no spam).
 */
export default function FrozenFeatureGuard({ storageKey, title, message }) {
  const [showPopup, setShowPopup] = useState(false);

  useEffect(() => {
    if (shouldShowPopup(storageKey)) setShowPopup(true);
  }, [storageKey]);

  return (
    <>
      {showPopup && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(15,23,42,0.5)',
            zIndex: 100,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            padding: '1rem',
          }}
          onClick={() => setShowPopup(false)}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            style={{
              background: '#fff',
              borderRadius: '14px',
              padding: '1.5rem',
              maxWidth: '420px',
              width: '100%',
              textAlign: 'center',
              boxShadow: '0 20px 60px rgba(0,0,0,0.25)',
            }}
          >
            <div style={{ fontSize: '2rem', marginBottom: '0.5rem' }}>🚧</div>
            <h3 style={{ margin: '0 0 0.5rem 0', fontSize: '1.05rem', fontWeight: 800, color: '#0f172a' }}>
              {title || 'Feature under development'}
            </h3>
            <p style={{ margin: '0 0 1rem 0', fontSize: '0.875rem', color: '#64748b' }}>
              {message || 'Results are paused while eligibility runs on profile-lock only. Please use Mark Student Eligibility for now.'}
            </p>
            <button
              type="button"
              onClick={() => setShowPopup(false)}
              className="edvana-btn edvana-btn-primary"
              style={{ padding: '0.55rem 1.5rem', borderRadius: '10px', fontWeight: 700 }}
            >
              OK
            </button>
          </div>
        </div>
      )}
      <div
        style={{
          margin: '0 0 1rem 0',
          padding: '0.85rem 1.1rem',
          background: '#fffbeb',
          border: '1px solid #fde68a',
          borderRadius: '12px',
          color: '#92400e',
          fontSize: '0.85rem',
          fontWeight: 600,
        }}
      >
        🚧 {title || 'Feature under development'} — {message || 'results are paused while eligibility runs on profile-lock only.'}
      </div>
    </>
  );
}
