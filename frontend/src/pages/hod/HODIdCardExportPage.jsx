import { useCallback, useEffect, useState } from 'react';
import {
  AlertTriangle,
  CheckCircle2,
  Download,
  IdCard,
  Lock,
  RefreshCw,
  Search,
  Users,
  XCircle,
} from 'lucide-react';
import studentApi from '../../api/studentApi';
import PageHeader from '../../components/common/PageHeader';
import DataTable from '../../components/common/DataTable';
import { ErrorState } from '../../components/common/StateDisplays';

/**
 * HOD — ID Card Export.
 *
 * One-stop screen for building ID card data packs:
 *  - Stats + per-student board for FIRST-YEAR students of the HOD's
 *    department: who locked their profile, who still hasn't, and who is
 *    locked but missing their photo / signature ("Needs attention").
 *  - "Download ZIP" packs a ready ID Card ZIP (Excel info sheet +
 *    FILES/<PRN>/<PRN>_photo / _sign) containing ONLY locked students
 *    with both images on file, matching the institutional sample layout.
 *
 * Authorization is server-enforced (HOD → own department only); the page
 * just renders what the API allows.
 */

const STATUS_META = {
  READY: {
    label: 'Ready to Export',
    variant: 'success',
    color: '#16a34a',
    bg: '#f0fdf4',
    border: '#bbf7d0',
  },
  LOCKED_INCOMPLETE: {
    label: 'Needs Attention',
    variant: 'warning',
    color: '#b45309',
    bg: '#fffbeb',
    border: '#fde68a',
  },
  PENDING: {
    label: 'Not Locked Yet',
    variant: 'neutral',
    color: '#475569',
    bg: '#f8fafc',
    border: '#e2e8f0',
  },
};

function StatTile({ icon: Icon, label, value, tone, hint }) {
  const tones = {
    blue: { bg: '#eff6ff', border: '#dbeafe', color: '#1d4ed8' },
    green: { bg: '#f0fdf4', border: '#bbf7d0', color: '#15803d' },
    amber: { bg: '#fffbeb', border: '#fde68a', color: '#b45309' },
    slate: { bg: '#f8fafc', border: '#e2e8f0', color: '#475569' },
  };
  const t = tones[tone] || tones.blue;
  return (
    <div
      style={{
        flex: '1 1 180px',
        background: t.bg,
        border: `1px solid ${t.border}`,
        borderRadius: '12px',
        padding: '0.9rem 1.1rem',
        display: 'flex',
        alignItems: 'center',
        gap: '0.8rem',
        minWidth: '170px',
      }}
    >
      <div
        style={{
          width: 38,
          height: 38,
          borderRadius: '10px',
          background: '#ffffff',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          border: `1px solid ${t.border}`,
          flexShrink: 0,
        }}
      >
        <Icon size={19} color={t.color} />
      </div>
      <div>
        <div style={{ fontSize: '1.35rem', fontWeight: 700, color: t.color, lineHeight: 1.15 }}>
          {value}
        </div>
        <div style={{ fontSize: '0.72rem', fontWeight: 600, color: '#475569', letterSpacing: '0.03em' }}>
          {label}
        </div>
        {hint && (
          <div style={{ fontSize: '0.66rem', color: '#94a3b8' }}>{hint}</div>
        )}
      </div>
    </div>
  );
}

function statusBadge(statusCode) {
  const meta = STATUS_META[statusCode] || STATUS_META.PENDING;
  const dotStyle = {
    width: 7,
    height: 7,
    borderRadius: '50%',
    backgroundColor: meta.color,
    flexShrink: 0,
  };
  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: '0.4rem',
        padding: '0.3rem 0.7rem',
        borderRadius: '9999px',
        fontSize: '0.72rem',
        fontWeight: 700,
        color: meta.color,
        backgroundColor: meta.bg,
        border: `1px solid ${meta.border}`,
        whiteSpace: 'nowrap',
      }}
    >
      <span style={dotStyle} />
      {meta.label}
    </span>
  );
}

function imageTag(state, label) {
  const ok = state === 'OK';
  const unknown = state === 'UNKNOWN';
  const text = ok ? label : state === 'NO_IMAGE' ? `${label} missing` : `${label} file lost`;
  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: '0.3rem',
        fontSize: '0.7rem',
        fontWeight: 600,
        color: ok ? '#15803d' : unknown ? '#94a3b8' : '#b91c1c',
        backgroundColor: ok ? '#f0fdf4' : '#fef2f2',
        border: `1px solid ${ok ? '#bbf7d0' : '#fecaca'}`,
        borderRadius: '9999px',
        padding: '0.2rem 0.55rem',
        whiteSpace: 'nowrap',
      }}
    >
      {ok ? '✓' : unknown ? '–' : '✕'}
      {text}
    </span>
  );
}

export default function HODIdCardExportPage() {
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [notice, setNotice] = useState(null);
  const [statusFilter, setStatusFilter] = useState('');
  const [search, setSearch] = useState('');
  const [appliedSearch, setAppliedSearch] = useState('');
  const [downloading, setDownloading] = useState(false);

  const loadSummary = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const params = {};
      if (statusFilter) params.export_status = statusFilter;
      const res = await studentApi.getIDCardSummary(params);
      setSummary(res.data);
    } catch (err) {
      setError(
        err.response?.data?.detail ||
          err.response?.data?.message ||
          'Failed to load the ID card summary. Check your permissions or try again.'
      );
      setSummary(null);
    } finally {
      setLoading(false);
    }
  }, [statusFilter]);

  useEffect(() => {
    loadSummary();
  }, [loadSummary]);

  const fadeNotice = (msg) => {
    setNotice(msg);
    window.setTimeout(() => setNotice(null), 8000);
  };

  const handleDownload = async () => {
    try {
      setDownloading(true);
      const res = await studentApi.downloadIDCardExport();

      // A JSON blob means the server rejected the export (403/400) — surface it.
      if (res.data instanceof Blob && res.data.type.includes('json')) {
        const text = await res.data.text();
        let detail = 'Export was rejected by the server.';
        try {
          detail = JSON.parse(text).detail || detail;
        } catch {
          /* keep default */
        }
        setError(detail);
        return;
      }

      const blob = res.data instanceof Blob ? res.data : new Blob([res.data]);
      const fallbackName = summary?.departments?.[0]?.code || 'ALL';
      const stamp = new Date().toISOString().slice(0, 16).replace(/[-:T]/g, '').replace(/(\d{8})(\d{4})/, '$1_$2');
      let filename = `ID_Card_Data_${fallbackName}_FY_${stamp}.zip`;
      const disposition = res.headers?.['content-disposition'] || '';
      const match = disposition.match(/filename="?([^"\r\n;]+)"?/i);
      if (match) filename = match[1];

      const url = URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = filename;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(url);

      const included = Number(res.headers?.['x-id-card-included'] ?? NaN);
      const skipped = Number(res.headers?.['x-id-card-skipped'] ?? NaN);
      const parts = [];
      if (!Number.isNaN(included)) parts.push(`${included} student${included === 1 ? '' : 's'} packed`);
      if (!Number.isNaN(skipped) && skipped > 0) {
        parts.push(
          `${skipped} not ready (profile pending or photo/signature missing) — see the Needs Attention / Not Locked rows below`
        );
      }
      fadeNotice(
        `${filename} downloaded successfully${parts.length ? ' — ' + parts.join('; ') : ''}.`
      );
      loadSummary();
    } catch (err) {
      setError(
        err.response?.data?.detail ||
          'Download failed. Please try again — if it repeats, contact the system administrator.'
      );
    } finally {
      setDownloading(false);
    }
  };

  const stats = summary?.stats || { total: 0, locked: 0, not_locked: 0, ready: 0, locked_incomplete: 0 };
  const departments = summary?.departments || [];
  const deptLabel = departments.length
    ? departments.length === 1
      ? departments[0].name
      : departments.length + ' departments'
    : 'your department';

  const students = summary?.students || [];
  const visibleStudents = students.filter((row) => {
    if (!appliedSearch) return true;
    const q = appliedSearch.toLowerCase();
    return (
      (row.prn || '').toLowerCase().includes(q) ||
      (row.display_name || '').toLowerCase().includes(q) ||
      (row.roll_number || '').toLowerCase().includes(q)
    );
  });

  const columns = [
    {
      header: 'PRN',
      width: '130px',
      render: (row) => (
        <span
          style={{
            fontFamily: 'var(--edvana-font-mono, monospace)',
            fontWeight: 700,
            fontSize: '0.8125rem',
            color: '#0f172a',
          }}
        >
          {row.prn || '—'}
        </span>
      ),
    },
    {
      header: 'Student',
      render: (row) => (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '2px' }}>
          <span style={{ fontWeight: 700, fontSize: '0.8125rem', color: '#0f172a' }}>
            {(row.display_name || '—').toUpperCase()}
          </span>
          <span style={{ fontSize: '0.6875rem', color: '#94a3b8' }}>
            {[
              row.division_name ? `Div ${row.division_name}` : null,
              row.semester_number ? `Sem ${row.semester_number}` : null,
              row.roll_number ? `Roll ${row.roll_number}` : null,
            ].filter(Boolean).join(' • ') || '—'}
          </span>
        </div>
      ),
    },
    {
      header: 'Images',
      render: (row) => (
        <div style={{ display: 'flex', gap: '0.35rem', flexWrap: 'wrap' }}>
          {imageTag(row.photo_status, 'Photo')}
          {imageTag(row.signature_status, 'Signature')}
        </div>
      ),
    },
    {
      header: 'Profile Status',
      align: 'center',
      width: '220px',
      render: (row) => statusBadge(row.export_status),
    },
    {
      header: 'Locked On',
      width: '170px',
      render: (row) => (
        <span style={{ fontSize: '0.75rem', color: '#64748b' }}>
          {row.profile_locked_at
            ? new Date(row.profile_locked_at).toLocaleString('en-IN', { dateStyle: 'medium', timeStyle: 'short' })
            : row.profile_locked
              ? 'Locked'
              : 'Not yet locked'}
        </span>
      ),
    },
  ];

  return (
    <>
      <PageHeader
        breadcrumbs={[
          { label: 'Home', to: '/dashboard' },
          { label: 'ID Card Export' },
        ]}
        title="ID Card Export"
      />

      <div className="edvana-banner-overlap">
        <div className="edvana-card" style={{ padding: '1.75rem 2rem' }}>
          {/* Card header */}
          <div
            style={{
              display: 'flex',
              flexWrap: 'wrap',
              alignItems: 'flex-start',
              justifyContent: 'space-between',
              gap: '1rem',
              marginBottom: '1.25rem',
            }}
          >
            <div>
              <div style={{ fontSize: '0.8125rem', fontWeight: 600, color: '#2563eb', marginBottom: '0.25rem' }}>
                Academics / ID Card Export
              </div>
              <h2 style={{ fontSize: '1.5rem', fontWeight: 700, color: '#0f172a', margin: 0, lineHeight: 1.25 }}>
                First-Year ID Card Data Pack
              </h2>
              <p style={{ fontSize: '0.8125rem', color: '#64748b', margin: '0.35rem 0 0 0', maxWidth: '720px' }}>
                Downloads a ZIP with one folder per first-year student of {deptLabel}, named by PRN, containing
                the student's photo and signature plus an Excel information sheet. Only students whose profiles
                are locked <em>and</em> whose photo + signature files are present get packaged.
              </p>
            </div>
            <div style={{ display: 'flex', gap: '0.6rem', flexWrap: 'wrap' }}>
              <button
                type="button"
                onClick={loadSummary}
                disabled={loading || downloading}
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '0.4rem',
                  padding: '0.5rem 1rem',
                  fontSize: '0.8125rem',
                  fontWeight: 600,
                  borderRadius: '8px',
                  border: '1px solid #cbd5e1',
                  background: '#ffffff',
                  color: '#1e293b',
                  cursor: loading || downloading ? 'wait' : 'pointer',
                }}
              >
                <RefreshCw size={15} />
                Refresh
              </button>
              <button
                type="button"
                onClick={handleDownload}
                disabled={downloading || loading || stats.ready === 0}
                title={
                  stats.ready === 0
                    ? 'No first-year student is fully ready yet — nothing to export'
                    : 'Download the ID card data pack ZIP'
                }
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '0.45rem',
                  padding: '0.5rem 1.15rem',
                  fontSize: '0.8125rem',
                  fontWeight: 700,
                  borderRadius: '8px',
                  border: '1px solid #1d4ed8',
                  background: stats.ready === 0 ? '#e2e8f0' : '#1d4ed8',
                  color: stats.ready === 0 ? '#94a3b8' : '#ffffff',
                  cursor: downloading ? 'progress' : stats.ready === 0 ? 'not-allowed' : 'pointer',
                  opacity: downloading ? 0.8 : 1,
                }}
              >
                <Download size={15} />
                {downloading ? 'Building ZIP...' : 'Download ZIP'}
              </button>
            </div>
          </div>

          {/* Notice banner */}
          {notice && (
            <div
              role="status"
              style={{
                padding: '0.75rem 1rem',
                backgroundColor: '#f0fdf4',
                border: '1px solid #bbf7d0',
                color: '#16a34a',
                borderRadius: '8px',
                fontSize: '0.8125rem',
                fontWeight: 600,
                marginBottom: '1rem',
              }}
            >
              {notice}
            </div>
          )}

          {/* Error banner */}
          {error && (
            <div
              style={{
                padding: '0.75rem 1rem',
                backgroundColor: '#fef2f2',
                border: '1px solid #fecaca',
                color: '#b91c1c',
                borderRadius: '8px',
                fontSize: '0.8125rem',
                fontWeight: 600,
                marginBottom: '1rem',
              }}
            >
              {error}
            </div>
          )}

          {/* Stats */}
          <div style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap', marginBottom: '1.25rem' }}>
            <StatTile icon={Users} label="TOTAL FIRST-YEAR" value={stats.total} tone="blue" hint={deptLabel} />
            <StatTile
              icon={Lock}
              label="PROFILE LOCKED"
              value={stats.locked}
              tone="green"
              hint="students may be exported"
            />
            <StatTile
              icon={XCircle}
              label="NOT LOCKED"
              value={stats.not_locked}
              tone="slate"
              hint="student must lock profile first"
            />
            <StatTile
              icon={AlertTriangle}
              label="NEEDS ATTENTION"
              value={stats.locked_incomplete}
              tone="amber"
              hint="locked but photo/signature missing"
            />
            <StatTile
              icon={CheckCircle2}
              label="READY TO EXPORT"
              value={stats.ready}
              tone="green"
              hint="will be packaged in the ZIP"
            />
          </div>

          {/* Filter bar */}
          <form
            onSubmit={(e) => {
              e.preventDefault();
              setAppliedSearch(search.trim());
            }}
            style={{
              display: 'flex',
              flexWrap: 'wrap',
              gap: '0.625rem',
              alignItems: 'center',
              backgroundColor: '#ffffff',
              padding: '0.75rem 0',
              borderBottom: '1px solid #f1f5f9',
            }}
          >
            <div style={{ position: 'relative', flex: '1 1 260px', minWidth: '200px' }}>
              <Search
                size={16}
                style={{
                  position: 'absolute',
                  left: '12px',
                  top: '50%',
                  transform: 'translateY(-50%)',
                  color: '#94a3b8',
                }}
              />
              <input
                type="text"
                className="edvana-input"
                placeholder="Search PRN, name or roll number..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                style={{
                  paddingLeft: '36px',
                  borderRadius: '8px',
                  height: '38px',
                  fontSize: '0.8125rem',
                  borderColor: '#cbd5e1',
                  width: '100%',
                }}
              />
            </div>
            <select
              className="edvana-input"
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              style={{
                flex: '0 1 190px',
                height: '38px',
                borderRadius: '8px',
                fontSize: '0.8125rem',
                borderColor: '#cbd5e1',
                padding: '0 0.75rem',
                color: '#334155',
                fontWeight: statusFilter ? 600 : 400,
              }}
            >
              <option value="">All Statuses</option>
              <option value="READY">Ready to Export</option>
              <option value="LOCKED_INCOMPLETE">Needs Attention</option>
              <option value="PENDING">Not Locked Yet</option>
            </select>
            <button
              type="button"
              onClick={() => {
                setSearch('');
                setAppliedSearch('');
                setStatusFilter('');
              }}
              disabled={!search && !appliedSearch && !statusFilter}
              style={{
                padding: '0.45rem 0.9rem',
                fontSize: '0.75rem',
                fontWeight: 600,
                borderRadius: '8px',
                border: '1px solid #cbd5e1',
                background: '#ffffff',
                color: '#475569',
                cursor: 'pointer',
                opacity: !search && !appliedSearch && !statusFilter ? 0.5 : 1,
              }}
            >
              Clear Filters
            </button>
          </form>

          {error && !summary ? (
            <div style={{ padding: '2rem 1rem' }}>
              <ErrorState message={error} onRetry={loadSummary} />
            </div>
          ) : (
            <>
              {!loading && summary && summary.count > (summary.students?.length || 0) && (
                <div
                  style={{
                    padding: '0.55rem 1rem',
                    backgroundColor: '#fafbfc',
                    border: '1px solid #e2e8f0',
                    color: '#475569',
                    borderRadius: '8px',
                    fontSize: '0.75rem',
                    margin: '0.75rem 0 0.5rem 0',
                  }}
                >
                  Showing {summary.students?.length || 0} of {summary.count} students (page{' '}
                  {summary.page} of {summary.num_pages}) — use the filters to narrow the view.
                </div>
              )}
              <DataTable
                columns={columns}
                data={visibleStudents}
                loading={loading && !summary}
                keyField="id"
                emptyMessage={
                  statusFilter || appliedSearch
                    ? 'No students match the current filters'
                    : 'No first-year students found for your department yet'
                }
              />
            </>
          )}

          {/* Export legend */}
          <div
            style={{
              marginTop: '1rem',
              display: 'flex',
              gap: '0.6rem',
              background: '#eff6ff',
              border: '1px solid #dbeafe',
              borderRadius: '12px',
              padding: '0.8rem 1rem',
              fontSize: '0.8rem',
              color: '#1e40af',
              lineHeight: 1.55,
            }}
          >
            <IdCard size={16} style={{ flexShrink: 0, marginTop: 2 }} />
            <span>
              <strong>Who gets packaged:</strong> first-year students whose profile is locked and whose photo and
              signature files are present. Locked students missing an image need an unlock → upload → re-lock cycle
              (Student Account Admin page), while not-locked students simply complete and lock their profiles.
              Aadhaar numbers and bank details are never exported.
            </span>
          </div>
        </div>
      </div>
    </>
  );
}
