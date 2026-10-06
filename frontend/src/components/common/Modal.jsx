import React, { useEffect } from 'react';
import { createPortal } from 'react-dom';
import { X } from 'lucide-react';

/**
 * Shared Modal dialog component with backdrop, ESC listener, and clean animation.
 */
export default function Modal({
  isOpen,
  onClose,
  title,
  children,
  footer,
  size = 'md',
  maxWidth,
  style,
  closeOnOverlayClick = true,
}) {
  useEffect(() => {
    if (!isOpen) return;
    const handleKeyDown = (e) => {
      if (e.key === 'Escape') {
        onClose?.();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  const sizeClass = size === 'xl' ? 'edvana-modal-xl' : size === 'lg' ? 'edvana-modal-lg' : '';
  const modalStyle = {
    ...(maxWidth ? { maxWidth } : {}),
    ...(style || {}),
  };

  // Portal to document.body: escapes any ancestor with a retained
  // transform/filter (e.g. entrance animations), which would otherwise
  // hijack `position: fixed` and render the dialog off-screen.
  return createPortal(
    <div
      className="edvana-modal-overlay"
      onClick={closeOnOverlayClick ? onClose : undefined}
      role="dialog"
      aria-modal="true"
    >
      <div
        className={`edvana-modal ${sizeClass}`}
        style={modalStyle}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="edvana-modal-header">
          {typeof title === 'string' ? (
            <h3 className="edvana-modal-title">{title}</h3>
          ) : (
            title
          )}
          <button
            className="edvana-modal-close"
            onClick={onClose}
            aria-label="Close dialog"
            title="Close"
          >
            <X size={20} />
          </button>
        </div>

        <div className="edvana-modal-body">{children}</div>

        {footer && <div className="edvana-modal-footer">{footer}</div>}
      </div>
    </div>,
    document.body
  );
}
