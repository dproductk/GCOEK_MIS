/**
 * Spinner — loading indicator.
 * Uses EDVANA design tokens via CSS classes.
 */
export default function Spinner({ size = 'md', className = '' }) {
  const sizeClass = size === 'sm' ? 'spinner-sm' : size === 'lg' ? 'spinner-lg' : '';
  return <div className={`spinner ${sizeClass} ${className}`} role="status" aria-label="Loading" />;
}
