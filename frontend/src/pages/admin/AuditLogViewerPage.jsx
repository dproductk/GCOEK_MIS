import React, { useState, useEffect } from 'react';
import { 
  ShieldCheck, Search, Filter, RefreshCw, Eye, 
  Clock, AlertTriangle, User, Globe, FileCode, X, Shield 
} from 'lucide-react';
import auditApi from '../../api/auditApi';
import PageHeader from '../../components/common/PageHeader';
import DataTable from '../../components/common/DataTable';
import Badge from '../../components/common/Badge';
import Modal from '../../components/common/Modal';
import { LoadingState, ErrorState, EmptyState } from '../../components/common/StateDisplays';

export default function AuditLogViewerPage() {
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Filters
  const [actionFilter, setActionFilter] = useState('');
  const [targetFilter, setTargetFilter] = useState('');
  const [actorSearch, setActorSearch] = useState('');

  // Selected Log Detail Modal
  const [selectedLog, setSelectedLog] = useState(null);

  const fetchLogs = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await auditApi.getAuditLogs({
        action: actionFilter || undefined,
        target_type: targetFilter || undefined,
        actor: actorSearch || undefined,
      });
      setLogs(res.data?.results || res.data || []);
    } catch (err) {
      console.error('Failed to load audit logs:', err);
      setError('Could not retrieve audit logs. Sysadmin authorization required.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchLogs();
  }, [actionFilter, targetFilter]);

  const handleSearch = (e) => {
    e.preventDefault();
    fetchLogs();
  };

  const getActionBadgeVariant = (action) => {
    switch (action) {
      case 'SENSITIVE_REVEAL':
        return 'warning';
      case 'ROLE_ASSIGN':
      case 'CREATE':
        return 'success';
      case 'ROLE_REVOKE':
      case 'DELETE':
        return 'danger';
      case 'UPDATE':
        return 'info';
      case 'LOGIN':
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
        subtitle="Immutable forensic log of all administrative actions, data unmasking events, and privilege modifications."
        actions={
          <button
            onClick={fetchLogs}
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
            <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: '1rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: 'var(--edvana-text-muted)', fontSize: '0.875rem', fontWeight: 600 }}>
                <Filter size={16} /> Filters:
              </div>

              <form onSubmit={handleSearch} style={{ display: 'flex', gap: '0.5rem' }}>
                <input
                  type="text"
                  placeholder="Search actor username..."
                  value={actorSearch}
                  onChange={(e) => setActorSearch(e.target.value)}
                  className="edvana-input"
                  style={{ maxWidth: '200px' }}
                />
                <button type="submit" className="edvana-btn edvana-btn-primary" style={{ padding: '0.35rem 0.75rem', fontSize: '0.8rem' }}>
                  Search
                </button>
              </form>

              <select
                value={actionFilter}
                onChange={(e) => setActionFilter(e.target.value)}
                className="edvana-input"
                style={{ maxWidth: '240px' }}
              >
                <option value="">All Action Types</option>
                <option value="SENSITIVE_REVEAL">Sensitive Reveal (Aadhaar/Bank)</option>
                <option value="ROLE_ASSIGN">Role Assignment</option>
                <option value="ROLE_REVOKE">Role Revocation</option>
                <option value="CREATE">Record Creation</option>
                <option value="UPDATE">Record Update</option>
                <option value="LOGIN">User Login</option>
                <option value="PASSWORD_CHANGE">Password Change</option>
              </select>

              <select
                value={targetFilter}
                onChange={(e) => setTargetFilter(e.target.value)}
                className="edvana-input"
                style={{ maxWidth: '200px' }}
              >
                <option value="">All Target Types</option>
                <option value="Student">Student Records</option>
                <option value="Faculty">Faculty Records</option>
                <option value="RoleAssignment">Role Assignments</option>
                <option value="PaymentLedger">Fee Payments</option>
                <option value="User">User Accounts</option>
              </select>
            </div>
          </div>
        </div>

        {/* Audit Log Table */}
        <div className="edvana-card">
          <div className="edvana-card-header">
            <h2 className="edvana-card-title">Audit Log Register ({logs.length})</h2>
            <p className="edvana-card-description">Tamper-evident chronological transaction ledger with origin IP and user agent tracking</p>
          </div>
          <div className="edvana-card-body" style={{ padding: 0 }}>
            {loading ? (
              <div style={{ padding: '2.5rem' }}>
                <LoadingState message="Loading security audit trail..." />
              </div>
            ) : error ? (
              <div style={{ padding: '2.5rem' }}>
                <ErrorState title="Error Loading Logs" message={error} onRetry={fetchLogs} />
              </div>
            ) : (
              <DataTable
                columns={columns}
                data={logs}
                keyExtractor={(log) => log.id}
                pageSize={10}
                emptyTitle="No Audit Logs Found"
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
