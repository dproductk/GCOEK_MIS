import React, { useState, useEffect, useCallback } from 'react';
import {
  ShieldCheck, Search, Filter, RefreshCw, Eye,
  Clock, AlertTriangle, User, Globe, FileCode, X, Shield, Download
} from 'lucide-react';
import auditApi from '../../api/auditApi';
import PageHeader from '../../components/common/PageHeader';
import DataTable from '../../components/common/DataTable';
import Badge from '../../components/common/Badge';
import Modal from '../../components/common/Modal';
import { LoadingState, ErrorState, EmptyState } from '../../components/common/StateDisplays';

const PAGE_SIZE = 25;

const ACTION_OPTIONS = [
  { value: '', label: 'All Action Types' },
  { value: 'PAYMENT', label: 'Fee Payment (ledger + online)' },
  { value: 'CREATE', label: 'Record Creation' },
  { value: 'UPDATE', label: 'Record Update' },
  { value: 'DELETE', label: 'Record Deletion' },
  { value: 'VERIFY', label: 'Verification (CT / HOD)' },
  { value: 'IMPORT', label: 'Data Import (admissions)' },
  { value: 'EXPORT', label: 'Data Export (incl. audit CSV)' },
  { value: 'STATUS_CHANGE', label: 'Status Change' },
  { value: 'SENSITIVE_REVEAL', label: 'Sensitive Reveal (Aadhaar/Bank)' },
  { value: 'ROLE_ASSIGN', label: 'Role Assignment' },
  { value: 'ROLE_REVOKE', label: 'Role Revocation' },
  { value: 'LOGIN', label: 'User Login' },
  { value: 'LOGIN_FAILED', label: 'Failed Login' },
  { value: 'LOGOUT', label: 'User Logout' },
  { value: 'PASSWORD_CHANGE', label: 'Password Change' },
];

const TARGET_OPTIONS = [
  { value: '', label: 'All Target Types' },
  { value: 'PaymentLedger', label: 'Fee Payments (ledger)' },
  { value: 'OnlinePaymentAttempt', label: 'Online Payment Attempts' },
  { value: 'StudentFeeAssessment', label: 'Fee Assessments (Set Fee)' },
  { value: 'FeeHead', label: 'Fee Heads' },
  { value: 'GatewayRawEvent', label: 'Gateway Events (callback/webhook)' },
  { value: 'ImportBatch', label: 'Admission Batches' },
  { value: 'EligibilityVerification', label: 'Eligibility Verifications' },
  { value: 'SubjectResult', label: 'Subject Results (marks)' },
  { value: 'Student', label: 'Student Records' },
  { value: 'StudentEnrollment', label: 'Student Enrollments' },
  { value: 'Faculty', label: 'Faculty Records' },
  { value: 'RoleAssignment', label: 'Role Assignments' },
  { value: 'Division', label: 'Divisions' },
  { value: 'LabBatch', label: 'Lab Batches' },
  { value: 'Scheme', label: 'Schemes' },
  { value: 'Subject', label: 'Subjects' },
  { value: 'SchemeSubject', label: 'Scheme Subjects' },
  { value: 'AssessmentComponent', label: 'Assessment Splits' },
  { value: 'User', label: 'User Accounts' },
  { value: 'AuditLog', label: 'Audit Exports' },
];

export default function AuditLogViewerPage() {
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [totalCount, setTotalCount] = useState(0);
  const [page, setPage] = useState(1);
  const [exporting, setExporting] = useState(false);

  // Filters
  const [actionFilter, setActionFilter] = useState('');
  const [targetFilter, setTargetFilter] = useState('');
  const [actorSearch, setActorSearch] = useState('');
  const [targetIdSearch, setTargetIdSearch] = useState('');
  const [textSearch, setTextSearch] = useState('');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');

  // Selected Log Detail Modal
  const [selectedLog, setSelectedLog] = useState(null);

  const buildParams = useCallback((pageNo) => {
    const params = { page: pageNo };
    if (actionFilter) params.action = actionFilter;
    if (targetFilter) params.target_type = targetFilter;
    if (actorSearch.trim()) params.actor = actorSearch.trim();
    if (targetIdSearch.trim()) params.target_id = targetIdSearch.trim();
    if (textSearch.trim()) params.search = textSearch.trim();
    if (dateFrom) params.date_from = dateFrom;
    if (dateTo) params.date_to = dateTo;
    return params;
  }, [actionFilter, targetFilter, actorSearch, targetIdSearch, textSearch, dateFrom, dateTo]);

  const fetchLogs = useCallback(async (pageNo = 1) => {
    setLoading(true);
    setError(null);
    try {
      const res = await auditApi.getAuditLogs(buildParams(pageNo));
      const payload = res.data || {};
      const rows = payload.results || payload || [];
      setLogs(Array.isArray(rows) ? rows : []);
      setTotalCount(typeof payload.count === 'number' ? payload.count : (Array.isArray(rows) ? rows.length : 0));
      setPage(pageNo);
    } catch (err) {
      setError('Could not retrieve audit logs. Sysadmin authorization required.');
    } finally {
      setLoading(false);
    }
  }, [buildParams]);

  useEffect(() => {
    fetchLogs(1);
  }, [actionFilter, targetFilter]);

  const handleSearch = (e) => {
    e.preventDefault();
    fetchLogs(1);
  };

  const handleClear = async () => {
    // Single fetch with cleared params — no watcher effect, so typing or
    // clearing text inputs never auto-searches and mount never double-fetches.
    setActionFilter('');
    setTargetFilter('');
    setActorSearch('');
    setTargetIdSearch('');
    setTextSearch('');
    setDateFrom('');
    setDateTo('');
    setLoading(true);
    setError(null);
    try {
      const res = await auditApi.getAuditLogs({ page: 1 });
      const payload = res.data || {};
      const rows = payload.results || payload || [];
      setLogs(Array.isArray(rows) ? rows : []);
      setTotalCount(typeof payload.count === 'number' ? payload.count : (Array.isArray(rows) ? rows.length : 0));
      setPage(1);
    } catch (err) {
      setError('Could not retrieve audit logs. Sysadmin authorization required.');
    } finally {
      setLoading(false);
    }
  };

  const handleExport = async () => {
    setExporting(true);
    try {
      const res = await auditApi.exportAuditLogs(buildParams(1));
      const blob = new Blob([res.data], { type: 'text/csv' });
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      const stamp = new Date().toISOString().slice(0, 19).replace(/[:T]/g, '-');
      link.href = url;
      link.setAttribute('download', `audit_logs_${stamp}.csv`);
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
    } catch (err) {
      setError('Export failed. Narrow the date range and retry. Sysadmin authorization required.');
    } finally {
      setExporting(false);
    }
  };

  const getActionBadgeVariant = (action) => {
    switch (action) {
      case 'SENSITIVE_REVEAL':
        return 'warning';
      case 'ROLE_ASSIGN':
      case 'CREATE':
      case 'PAYMENT':
      case 'IMPORT':
        return 'success';
      case 'ROLE_REVOKE':
      case 'DELETE':
        return 'danger';
      case 'UPDATE':
      case 'VERIFY':
        return 'info';
      case 'LOGIN':
      case 'EXPORT':
      default:
        return 'neutral';
    }
  };

  const columns = [
    {
      header: 'Timestamp (Local)',
      accessor: 'timestamp',
      render: (log) => (
        <span style={{ fontFamily: 'monospace', fontSize: '0.8rem', color: '#475569' }}>
          {new Date(log.timestamp).toLocaleString()}
        </span>
      ),
    },
    {
      header: 'Actor',
      render: (log) => (
        <div>
          <div style={{ fontWeight: 600, color: '#0f172a' }}>{log.actor_username || 'SYSTEM'}</div>
          {log.actor_role && (
            <div style={{ fontSize: '0.75rem', color: '#64748b' }}>{log.actor_role}</div>
          )}
        </div>
      ),
    },
    {
      header: 'Action',
      render: (log) => (
        <Badge variant={getActionBadgeVariant(log.action)}>
          {log.action}
        </Badge>
      ),
    },
    {
      header: 'Target Entity',
      render: (log) => (
        <div>
          <span style={{ fontWeight: 600, color: '#1e293b' }}>{log.target_type}</span>
          {log.target_display && (
            <span style={{ display: 'block', fontSize: '0.75rem', color: '#64748b', maxWidth: '200px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {log.target_display}
            </span>
          )}
        </div>
      ),
    },
    {
      header: 'Description',
      render: (log) => (
        <span style={{ fontSize: '0.85rem', color: '#475569', maxWidth: '280px', display: 'inline-block', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {log.description || log.reason || '—'}
        </span>
      ),
    },
    {
      header: 'Origin IP',
      accessor: 'ip_address',
      render: (log) => (
        <span style={{ fontFamily: 'monospace', fontSize: '0.75rem', color: '#64748b' }}>
          {log.ip_address || 'Internal'}
        </span>
      ),
    },
    {
      header: 'Inspect',
      align: 'center',
      render: (log) => (
        <button
          onClick={() => setSelectedLog(log)}
          className="edvana-btn edvana-btn-secondary"
          style={{ padding: '0.25rem 0.5rem', fontSize: '0.75rem', display: 'inline-flex', alignItems: 'center', gap: '0.35rem' }}
          title="View Forensic Audit Entry"
        >
          <Eye size={13} /> View
        </button>
      ),
    },
  ];

  return (
    <>
      <PageHeader
        breadcrumbs={[
          { label: 'Home', to: '/dashboard' },
          { label: 'Administration' },
          { label: 'Audit Trail' },
        ]}
        title="Security & System Audit Trail"
        subtitle="Immutable forensic log of all administrative actions, fee payments, data unmasking events, and privilege modifications. Export CSV for archival — rows are never deleted."
        actions={
          <div style={{ display: 'flex', gap: '0.5rem' }}>
            <button
              onClick={handleExport}
              disabled={exporting}
              className="edvana-btn"
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '0.45rem',
                background: 'rgba(255, 255, 255, 0.16)',
                color: '#ffffff',
                border: '1px solid rgba(255, 255, 255, 0.3)',
                borderRadius: '8px',
                fontWeight: 600,
                fontSize: '0.8125rem',
                padding: '0.5rem 1rem',
                opacity: exporting ? 0.6 : 1,
              }}
              title="Download filtered logs as CSV (max 10,000 newest rows)"
            >
              <Download size={15} />
              <span>{exporting ? 'Exporting…' : 'Download CSV'}</span>
            </button>
            <button
              onClick={() => fetchLogs(page)}
              className="edvana-btn"
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '0.45rem',
                background: 'rgba(255, 255, 255, 0.16)',
                color: '#ffffff',
                border: '1px solid rgba(255, 255, 255, 0.3)',
                borderRadius: '8px',
                fontWeight: 600,
                fontSize: '0.8125rem',
                padding: '0.5rem 1rem',
              }}
            >
              <RefreshCw size={15} />
              <span>Refresh Trail</span>
            </button>
          </div>
        }
      />

      <div className="edvana-banner-overlap">
        {error && (
          <div style={{ marginBottom: '1.5rem', padding: '1rem 1.25rem', background: '#fef2f2', border: '1px solid #fecaca', borderRadius: '8px', color: '#991b1b', fontSize: '0.875rem', display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
            <AlertTriangle size={20} style={{ flexShrink: 0 }} />
            <div>{error}</div>
          </div>
        )}

        {/* Filter Bar */}
        <div className="edvana-card" style={{ marginBottom: '1.5rem' }}>
          <div className="edvana-card-body" style={{ padding: '1.25rem' }}>
            <form onSubmit={handleSearch} style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: '0.75rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: 'var(--edvana-text-muted)', fontSize: '0.875rem', fontWeight: 600 }}>
                <Filter size={16} /> Filters:
              </div>

              <input
                type="text"
                placeholder="Actor username..."
                value={actorSearch}
                onChange={(e) => setActorSearch(e.target.value)}
                className="edvana-input"
                style={{ maxWidth: '170px' }}
              />
              <input
                type="text"
                placeholder="Target ID / receipt..."
                value={targetIdSearch}
                onChange={(e) => setTargetIdSearch(e.target.value)}
                className="edvana-input"
                style={{ maxWidth: '170px' }}
                title="Match against target ID (receipt no, transaction ID)"
              />
              <input
                type="text"
                placeholder="Search description..."
                value={textSearch}
                onChange={(e) => setTextSearch(e.target.value)}
                className="edvana-input"
                style={{ maxWidth: '190px' }}
              />
              <input
                type="date"
                value={dateFrom}
                onChange={(e) => setDateFrom(e.target.value)}
                className="edvana-input"
                style={{ maxWidth: '150px' }}
                title="From date (inclusive)"
              />
              <input
                type="date"
                value={dateTo}
                onChange={(e) => setDateTo(e.target.value)}
                className="edvana-input"
                style={{ maxWidth: '150px' }}
                title="To date (inclusive)"
              />

              <select
                value={actionFilter}
                onChange={(e) => setActionFilter(e.target.value)}
                className="edvana-input"
                style={{ maxWidth: '230px' }}
              >
                {ACTION_OPTIONS.map((o) => (
                  <option key={o.value || 'all'} value={o.value}>{o.label}</option>
                ))}
              </select>

              <select
                value={targetFilter}
                onChange={(e) => setTargetFilter(e.target.value)}
                className="edvana-input"
                style={{ maxWidth: '230px' }}
              >
                {TARGET_OPTIONS.map((o) => (
                  <option key={o.value || 'all'} value={o.value}>{o.label}</option>
                ))}
              </select>

              <button type="submit" className="edvana-btn edvana-btn-primary" style={{ padding: '0.35rem 0.75rem', fontSize: '0.8rem' }}>
                Search
              </button>
              <button type="button" onClick={handleClear} className="edvana-btn edvana-btn-secondary" style={{ padding: '0.35rem 0.75rem', fontSize: '0.8rem' }}>
                Clear
              </button>
            </form>
            <div style={{ marginTop: '0.6rem', fontSize: '0.75rem', color: '#64748b' }}>
              Server paginated ({PAGE_SIZE}/page). Use date filters + Download CSV to archive old logs without deleting them — the trail stays append-only.
            </div>
          </div>
        </div>

        {/* Audit Log Table */}
        <div className="edvana-card">
          <div className="edvana-card-header">
            <h2 className="edvana-card-title">Audit Log Register ({totalCount})</h2>
            <p className="edvana-card-description">Tamper-evident chronological transaction ledger with origin IP and user agent tracking</p>
          </div>
          <div className="edvana-card-body" style={{ padding: 0 }}>
            {loading ? (
              <div style={{ padding: '2.5rem' }}>
                <LoadingState message="Loading security audit trail..." />
              </div>
            ) : error ? (
              <div style={{ padding: '2.5rem' }}>
                <ErrorState title="Error Loading Logs" message={error} onRetry={() => fetchLogs(page)} />
              </div>
            ) : (
              <DataTable
                columns={columns}
                data={logs}
                keyField="id"
                page={page}
                pageSize={PAGE_SIZE}
                totalCount={totalCount}
                onPageChange={(p) => fetchLogs(p)}
                emptyMessage="No audit log entries match the filter criteria."
              />
            )}
          </div>
        </div>
      </div>

      {/* Forensic Detail Modal */}
      <Modal
        isOpen={Boolean(selectedLog)}
        onClose={() => setSelectedLog(null)}
        title="Forensic Audit Log Inspector"
        maxWidth="640px"
      >
        {selectedLog && (
          <div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', marginBottom: '1.25rem' }}>
              <div style={{ background: '#f8fafc', padding: '0.85rem 1rem', borderRadius: '6px', border: '1px solid #e2e8f0' }}>
                <div style={{ fontSize: '0.75rem', color: '#64748b', fontWeight: 600 }}>Actor Username</div>
                <div style={{ fontSize: '1rem', fontWeight: 700, color: '#0f172a', marginTop: '0.25rem' }}>{selectedLog.actor_username || 'SYSTEM'}</div>
                <div style={{ fontSize: '0.75rem', color: '#64748b' }}>Role: {selectedLog.actor_role || 'Unspecified'}</div>
              </div>

              <div style={{ background: '#f8fafc', padding: '0.85rem 1rem', borderRadius: '6px', border: '1px solid #e2e8f0' }}>
                <div style={{ fontSize: '0.75rem', color: '#64748b', fontWeight: 600 }}>Action & Target</div>
                <div style={{ fontSize: '1rem', fontWeight: 700, color: '#0f172a', marginTop: '0.25rem' }}>{selectedLog.action_display || selectedLog.action}</div>
                <div style={{ fontSize: '0.75rem', color: '#64748b' }}>{selectedLog.target_type}: {selectedLog.target_display}</div>
              </div>

              <div style={{ background: '#f8fafc', padding: '0.85rem 1rem', borderRadius: '6px', border: '1px solid #e2e8f0' }}>
                <div style={{ fontSize: '0.75rem', color: '#64748b', fontWeight: 600 }}>Timestamp (UTC)</div>
                <div style={{ fontSize: '0.85rem', fontFamily: 'monospace', color: '#0f172a', marginTop: '0.25rem' }}>{new Date(selectedLog.timestamp).toUTCString()}</div>
              </div>

              <div style={{ background: '#f8fafc', padding: '0.85rem 1rem', borderRadius: '6px', border: '1px solid #e2e8f0' }}>
                <div style={{ fontSize: '0.75rem', color: '#64748b', fontWeight: 600 }}>IP Address & Origin</div>
                <div style={{ fontSize: '0.85rem', fontFamily: 'monospace', color: '#0f172a', marginTop: '0.25rem' }}>{selectedLog.ip_address || 'Loopback / Internal'}</div>
              </div>
            </div>

            {selectedLog.reason && (
              <div style={{ padding: '0.85rem 1rem', background: '#fffbeb', border: '1px solid #fef3c7', borderRadius: '6px', marginBottom: '1.25rem', fontSize: '0.85rem' }}>
                <div style={{ fontWeight: 700, color: '#92400e', marginBottom: '0.25rem' }}>Stated Justification for Access:</div>
                <div style={{ color: '#78350f' }}>{selectedLog.reason}</div>
              </div>
            )}

            <div style={{ marginBottom: '1.25rem' }}>
              <div style={{ fontSize: '0.75rem', fontWeight: 600, color: '#64748b', marginBottom: '0.35rem' }}>Client User-Agent</div>
              <div style={{ padding: '0.65rem 0.85rem', background: '#f8fafc', borderRadius: '6px', border: '1px solid #e2e8f0', fontFamily: 'monospace', fontSize: '0.75rem', color: '#475569', wordBreak: 'break-all' }}>
                {selectedLog.user_agent || 'Unknown'}
              </div>
            </div>

            {(selectedLog.old_value || selectedLog.new_value) && (
              <div style={{ marginBottom: '1.25rem' }}>
                <div style={{ fontSize: '0.75rem', fontWeight: 600, color: '#64748b', marginBottom: '0.5rem' }}>Payload Delta State Change</div>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
                  <div>
                    <span style={{ fontSize: '0.75rem', fontWeight: 700, color: '#64748b', textTransform: 'uppercase' }}>Previous State</span>
                    <pre style={{ padding: '0.75rem', background: '#0f172a', color: '#f8fafc', borderRadius: '6px', fontSize: '0.7rem', overflowX: 'auto', maxHeight: '160px', marginTop: '0.25rem' }}>
                      {JSON.stringify(selectedLog.old_value, null, 2) || 'null'}
                    </pre>
                  </div>
                  <div>
                    <span style={{ fontSize: '0.75rem', fontWeight: 700, color: '#64748b', textTransform: 'uppercase' }}>New State</span>
                    <pre style={{ padding: '0.75rem', background: '#0f172a', color: '#f8fafc', borderRadius: '6px', fontSize: '0.7rem', overflowX: 'auto', maxHeight: '160px', marginTop: '0.25rem' }}>
                      {JSON.stringify(selectedLog.new_value, null, 2) || 'null'}
                    </pre>
                  </div>
                </div>
              </div>
            )}

            <div style={{ display: 'flex', justifyContent: 'flex-end', borderTop: '1px solid #e2e8f0', paddingTop: '1rem' }}>
              <button
                type="button"
                onClick={() => setSelectedLog(null)}
                className="edvana-btn edvana-btn-secondary"
              >
                Close Inspector
              </button>
            </div>
          </div>
        )}
      </Modal>
    </>
  );
}
