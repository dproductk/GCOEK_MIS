import React from 'react';
import Spinner from './Spinner';
import { EmptyState } from './StateDisplays';

/**
 * Standard EDVANA DataTable component.
 * Features:
 * - Clean headers with uppercase letter-spacing
 * - Hover highlights
 * - Integrated loading spinner and empty states
 * - Optional pagination bar
 */
export default function DataTable({
  columns = [],
  data = [],
  loading = false,
  emptyMessage = 'No records found in this view',
  onRowClick,
  keyField = 'id',
  page,
  pageSize,
  totalCount,
  onPageChange,
  toolbar,
  className = '',
}) {
  const showPagination =
    page !== undefined &&
    pageSize !== undefined &&
    totalCount !== undefined &&
    totalCount > pageSize;

  const totalPages = Math.ceil((totalCount || 0) / (pageSize || 1));

  return (
    <div className={`edvana-datatable-wrapper ${className}`}>
      {toolbar && <div style={{ marginBottom: '1rem' }}>{toolbar}</div>}

      <div className="edvana-table-container">
        <table className="edvana-table">
          <thead>
            <tr>
              {columns.map((col, idx) => (
                <th
                  key={idx}
                  style={{
                    width: col.width,
                    textAlign: col.align || 'left',
                  }}
                >
                  {col.header}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={columns.length} style={{ padding: '3rem 1rem', textAlign: 'center' }}>
                  <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '0.75rem' }}>
                    <Spinner size="md" />
                    <span style={{ fontSize: '0.8125rem', color: 'var(--edvana-text-muted)' }}>
                      Loading records...
                    </span>
                  </div>
                </td>
              </tr>
            ) : data && data.length > 0 ? (
              data.map((row, rowIdx) => {
                const rowKey = row[keyField] !== undefined ? row[keyField] : rowIdx;
                return (
                  <tr
                    key={rowKey}
                    onClick={() => onRowClick && onRowClick(row)}
                    style={{ cursor: onRowClick ? 'pointer' : 'default' }}
                  >
                    {columns.map((col, colIdx) => {
                      const cellValue = col.accessor ? row[col.accessor] : undefined;
                      return (
                        <td
                          key={colIdx}
                          style={{
                            textAlign: col.align || 'left',
                          }}
                        >
                          {col.render ? col.render(row, rowIdx) : (cellValue !== undefined && cellValue !== null ? cellValue : '—')}
                        </td>
                      );
                    })}
                  </tr>
                );
              })
            ) : (
              <tr>
                <td colSpan={columns.length} style={{ padding: '2rem 1rem' }}>
                  <EmptyState title="No records" message={emptyMessage} />
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {showPagination && (
        <div className="edvana-pagination">
          <span>
            Showing {(page - 1) * pageSize + 1} to{' '}
            {Math.min(page * pageSize, totalCount)} of {totalCount} records
          </span>
          <div className="edvana-pagination-controls">
            <button
              className="edvana-pagination-btn"
              disabled={page <= 1}
              onClick={() => onPageChange?.(page - 1)}
            >
              Previous
            </button>
            <span style={{ padding: '0.375rem 0.5rem', fontWeight: 600 }}>
              Page {page} of {totalPages || 1}
            </span>
            <button
              className="edvana-pagination-btn"
              disabled={page >= totalPages}
              onClick={() => onPageChange?.(page + 1)}
            >
              Next
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
