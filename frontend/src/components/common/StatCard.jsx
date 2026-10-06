import React from 'react';

/**
 * Shared StatCard component for dashboard KPIs and quick metrics.
 * Styled with EDVANA tokens.
 */
export default function StatCard({
  label,
  value,
  hint,
  icon: Icon,
  color = 'var(--edvana-brand)',
  trend,
  style = {},
  onClick,
}) {
  return (
    <div
      className={`edvana-stat-card${onClick ? ' pressable' : ''}`}
      onClick={onClick}
      style={{
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'space-between',
        cursor: onClick ? 'pointer' : 'default',
        position: 'relative',
        overflow: 'hidden',
        ...style,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: '0.75rem' }}>
        <div className="edvana-stat-label">{label}</div>
        {Icon && (
          <div
            style={{
              width: 36,
              height: 36,
              borderRadius: 'var(--edvana-radius-md)',
              backgroundColor: 'var(--edvana-panel-bg)',
              color: color,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              flexShrink: 0,
            }}
          >
            <Icon size={18} />
          </div>
        )}
      </div>

      <div style={{ marginTop: '0.75rem' }}>
        <div className="edvana-stat-value" style={{ color: 'var(--edvana-text-primary)' }}>
          {value !== undefined && value !== null ? value : '—'}
        </div>
        {(hint || trend) && (
          <div
            className="edvana-stat-hint"
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '0.5rem',
              marginTop: '0.35rem',
            }}
          >
            {trend && (
              <span style={{ fontWeight: 600, color: color }}>
                {trend}
              </span>
            )}
            {hint && <span>{hint}</span>}
          </div>
        )}
      </div>
    </div>
  );
}
