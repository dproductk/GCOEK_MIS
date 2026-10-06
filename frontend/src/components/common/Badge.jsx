import React from 'react';

/**
 * Shared Badge component mapping to EDVANA design tokens.
 * Variants: success, warning, danger, info, neutral
 */
export default function Badge({
  variant = 'neutral',
  children,
  dot = false,
  className = '',
  style = {},
}) {
  const variantClass = {
    success: 'edvana-badge-success',
    warning: 'edvana-badge-warning',
    danger: 'edvana-badge-danger',
    info: 'edvana-badge-info',
    neutral: 'edvana-badge-neutral',
  }[variant] || 'edvana-badge-neutral';

  return (
    <span
      className={`edvana-badge ${variantClass} ${className}`}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: '0.35rem',
        ...style,
      }}
    >
      {dot && (
        <span
          style={{
            width: 5,
            height: 5,
            borderRadius: '50%',
            backgroundColor: 'currentColor',
          }}
        />
      )}
      {children}
    </span>
  );
}
