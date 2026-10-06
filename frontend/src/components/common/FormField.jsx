import React from 'react';

/**
 * Shared FormField wrapper component.
 * Provides uniform label, required asterisk, input slot, helper text, and error messaging.
 */
export default function FormField({
  label,
  required = false,
  error,
  help,
  children,
  className = '',
  style = {},
  id,
}) {
  return (
    <div className={`edvana-form-group ${className}`} style={style}>
      {label && (
        <label htmlFor={id} className="edvana-field-label">
          <span>{label}</span>
          {required && <span className="edvana-field-required" aria-hidden="true">*</span>}
        </label>
      )}

      {children}

      {error ? (
        <span className="edvana-form-error" role="alert">
          {error}
        </span>
      ) : help ? (
        <span className="edvana-form-help">{help}</span>
      ) : null}
    </div>
  );
}
