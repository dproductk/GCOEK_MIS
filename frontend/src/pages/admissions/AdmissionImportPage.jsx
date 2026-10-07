import { useState, useEffect, useRef } from 'react';
import admissionsApi from '../../api/admissionsApi';
import academicApi from '../../api/academicApi';
import PageHeader from '../../components/common/PageHeader';
import StatCard from '../../components/common/StatCard';
import DataTable from '../../components/common/DataTable';
import Badge from '../../components/common/Badge';
import { LoadingState, ErrorState, EmptyState } from '../../components/common/StateDisplays';
import {
  Upload,
  FileSpreadsheet,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  Clock,
  ArrowRight,
  Database,
  RefreshCw,
  FileCheck,
  Layers,
  AlertCircle,
  Users,
  Trash2,
} from 'lucide-react';

export default function AdmissionImportPage() {
  const fileInputRef = useRef(null);

  const [batches, setBatches] = useState([]);
  const [activeBatch, setActiveBatch] = useState(null);
  // Single unified upload: the entry stream (FY Sem 1 vs DSY Sem 3) is resolved
  // server-side — explicit admission_type if ever passed, else auto-detect from
  // DSE/DSY filename markers, else FIRST_YEAR default (admissions/services.py).
  const [deptNameByCode, setDeptNameByCode] = useState({});
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [committing, setCommitting] = useState(false);
  const [deletingId, setDeletingId] = useState(null);
  const [rowPage, setRowPage] = useState(1);
  const ROWS_PER_PAGE = 25;
  const [error, setError] = useState(null);
  const [successMsg, setSuccessMsg] = useState(null);

  useEffect(() => {
    loadBatches();
    loadDepartmentNames();
  }, []);

  // Department code → full branch name for the Branch column. Read-only
  // academic config (WF-003); failure falls back to showing the raw code.
  const loadDepartmentNames = async () => {
    try {
      const res = await academicApi.getDepartments();
      const list = res.data.results || res.data || [];
      const map = {};
      list.forEach((d) => {
        if (d.code) map[d.code] = d.name || d.code;
      });
      setDeptNameByCode(map);
    } catch {
      // Silent fallback: Branch column renders the stored department code.
    }
  };

  const loadBatches = async () => {
    try {
      setLoading(true);
      const res = await admissionsApi.getBatches();
      const list = res.data.results || res.data || [];
      setBatches(list);
      if (list.length > 0 && !activeBatch) {
        const detailRes = await admissionsApi.getBatchDetails(list[0].id);
        setActiveBatch(detailRes.data);
      }
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to load admission batches.');
    } finally {
      setLoading(false);
    }
  };

  const handleFileSelect = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;

    const formData = new FormData();
    formData.append('file', file);
    // Backend resolves the true stream (FY vs DSY auto-detect); the staged
    // batch badge + history Stream column always show the resolved value.
    formData.append('admission_type', 'FIRST_YEAR');

    try {
      setUploading(true);
      setError(null);
      setSuccessMsg(null);
      const res = await admissionsApi.uploadFile(formData);
      setActiveBatch(res.data);
      setRowPage(1);
      const streamLabel = res.data.admission_type === 'DIRECT_SECOND_YEAR' ? 'Direct Second Year (DSY)' : 'First Year (FY)';
      setSuccessMsg(`File '${file.name}' staged as ${streamLabel}! Analyzed ${res.data.total_rows} student candidate rows.`);
      loadBatches();
    } catch (err) {
      setError(err.response?.data?.detail || 'Upload failed. Ensure file is a valid government candidate list (.xlsx, .xls, .csv).');
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  };

  const handleCommit = async () => {
    if (!activeBatch) return;
    if (!window.confirm(`Commit ${activeBatch.valid_rows} valid student candidate records into the core GCOEK database?`)) {
      return;
    }

    try {
      setCommitting(true);
      setError(null);
      const res = await admissionsApi.commitBatch(activeBatch.id);
      setActiveBatch(res.data);
      setRowPage(1);
      setSuccessMsg(`Batch committed successfully! Created ${res.data.imported_rows} core student records.`);
      loadBatches();
    } catch (err) {
      setError(err.response?.data?.detail || 'Commit execution failed.');
    } finally {
      setCommitting(false);
    }
  };

  const selectBatch = async (batchId) => {
    try {
      const res = await admissionsApi.getBatchDetails(batchId);
      setActiveBatch(res.data);
      setRowPage(1);
    } catch (err) {
      setError('Unable to load batch details.');
    }
  };

  const handleDeleteBatch = async (batch) => {
    if (batch.imported_rows > 0) return;
    if (!window.confirm(
      `Delete failed batch '${batch.file_name}'?\n\n` +
      `${batch.total_rows} staged rows will be removed so you can re-upload a fixed file. ` +
      `The deletion is recorded in the audit trail (Audit Logs) with file name, checksum and row counts.`
    )) {
      return;
    }
    try {
      setDeletingId(batch.id);
      setError(null);
      setSuccessMsg(null);
      const res = await admissionsApi.deleteBatch(batch.id, 'Failed batch cleanup before re-upload');
      if (activeBatch?.id === batch.id) setActiveBatch(null);
      setSuccessMsg(res.data?.detail || `Batch '${batch.file_name}' deleted. Audit entry retained.`);
      loadBatches();
    } catch (err) {
      setError(err.response?.data?.detail || 'Batch deletion failed.');
    } finally {
      setDeletingId(null);
    }
  };

  const getValidationBadgeVariant = (status) => {
    switch (status) {
      case 'VALID':
      case 'IMPORTED':
        return 'success';
      case 'DUPLICATE':
        return 'warning';
      case 'INVALID':
        return 'danger';
      default:
        return 'neutral';
    }
  };

  const previewColumns = [
    {
      header: '#',
      accessor: 'row_number',
      render: (r) => <span style={{ fontFamily: 'monospace', fontWeight: 600 }}>{r.row_number}</span>,
    },
    {
      header: 'PRN',
      accessor: 'enrollment_no',
      render: (r) => (
        <span style={{ fontFamily: 'monospace', fontWeight: 500, fontSize: '0.8125rem', color: '#334155' }}>
          {r.enrollment_no || '—'}
        </span>
      ),
    },
    {
      header: 'Candidate Name',
      accessor: 'candidate_name',
      render: (r) => <span style={{ fontWeight: 600, color: '#0f172a' }}>{r.candidate_name || '—'}</span>,
    },
    {
      header: 'Branch',
      render: (r) => {
        const deptCode = r.normalized_data?.department_code || '';
        const fullName = deptNameByCode[deptCode] || deptCode;
        return fullName ? (
          <span style={{ fontSize: '0.85rem', fontWeight: 400, color: '#475569', maxWidth: '280px', display: 'inline-block' }}>
            {fullName}
          </span>
        ) : (
          <span style={{ fontSize: '0.85rem', color: '#94a3b8' }}>—</span>
        );
      },
    },
    {
      header: 'Validation Status',
      render: (r) => (
        <Badge variant={getValidationBadgeVariant(r.validation_status)}>
          {r.validation_status_display}
        </Badge>
      ),
    },
    {
      header: 'Validation Notes',
      render: (r) => (
        <span style={{ fontSize: '0.8rem', color: r.validation_errors?.length ? '#b91c1c' : '#64748b' }}>
          {(r.validation_errors || []).join(', ') || 'Ready for core database ingestion'}
        </span>
      ),
    },
  ];

  const batchColumns = [
    {
      header: 'File Name',
      render: (b) => (
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <FileSpreadsheet size={16} style={{ color: 'var(--edvana-primary)' }} />
          <span style={{ fontWeight: 600, color: '#1e293b' }}>{b.file_name}</span>
        </div>
      ),
    },
    {
      header: 'Academic Term',
      accessor: 'academic_year_code',
      render: (b) => <span style={{ fontWeight: 500 }}>{b.academic_year_code || '2025-2026'}</span>,
    },
    {
      header: 'Stream',
      render: (b) => (
        <span
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '0.25rem',
            fontSize: '0.75rem',
            fontWeight: 700,
            padding: '0.2rem 0.55rem',
            borderRadius: '9999px',
            whiteSpace: 'nowrap',
            backgroundColor: b.admission_type === 'DIRECT_SECOND_YEAR' ? '#f3e8ff' : '#eff6ff',
            color: b.admission_type === 'DIRECT_SECOND_YEAR' ? '#7e22ce' : '#1d4ed8',
            border: `1px solid ${b.admission_type === 'DIRECT_SECOND_YEAR' ? '#d8b4fe' : '#bfdbfe'}`,
          }}
        >
          {b.admission_type === 'DIRECT_SECOND_YEAR' ? '⚡ DSY (Sem 3)' : '🎓 FY (Sem 1)'}
        </span>
      ),
    },
    {
      header: 'Status',
      render: (b) => (
        <span style={{ whiteSpace: 'nowrap' }}>
          <Badge variant={b.status === 'COMPLETED' ? 'success' : b.status === 'FAILED' ? 'danger' : b.status === 'VALIDATED' ? 'primary' : 'warning'}>
            {b.status_display}
          </Badge>
        </span>
      ),
    },
    {
      header: 'Import Ratio',
      render: (b) => (
        <span style={{ fontWeight: 600, fontFamily: 'monospace' }}>
          {b.imported_rows} / {b.total_rows}
        </span>
      ),
    },
    {
      header: 'Uploaded By',
      accessor: 'uploaded_by_name',
    },
    {
      header: 'Ingestion Date',
      render: (b) => <span style={{ fontSize: '0.85rem', color: '#64748b' }}>{b.created_at?.slice(0, 10)}</span>,
    },
    {
      header: 'Actions',
      align: 'right',
      render: (b) => (
        <div style={{ display: 'flex', gap: '0.5rem', justifyContent: 'flex-end' }}>
          <button
            className="edvana-btn edvana-btn-secondary"
            style={{ padding: '0.3rem 0.65rem', fontSize: '0.8rem' }}
            onClick={() => selectBatch(b.id)}
          >
            View Batch
          </button>
          {b.imported_rows === 0 && (
            <button
              title="Delete this failed batch (deletion is kept in the audit trail)"
              onClick={() => handleDeleteBatch(b)}
              disabled={deletingId === b.id}
              style={{
                background: 'none',
                border: 'none',
                padding: '0.3rem',
                cursor: deletingId === b.id ? 'default' : 'pointer',
                color: '#b91c1c',
                display: 'inline-flex',
                alignItems: 'center',
                opacity: deletingId === b.id ? 0.4 : 1,
              }}
            >
              <Trash2 size={15} />
            </button>
          )}
        </div>
      ),
    },
  ];

  return (
    <>
      <PageHeader
        breadcrumbs={[
          { label: 'Home', to: '/dashboard' },
          { label: 'Admissions' },
          { label: 'Excel Ingestion' },
        ]}
        title="Government Excel Ingestion"
        subtitle="Upload, schema validation, and normalization engine for DTE Maharashtra admitted candidate lists."
        actions={
          <button
            className="edvana-btn"
            onClick={loadBatches}
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
            <span>Refresh Batches</span>
          </button>
        }
      />

      <div className="edvana-banner-overlap">
        {error && (
          <div style={{ marginBottom: '1.5rem', padding: '1rem 1.25rem', background: '#fef2f2', border: '1px solid #fecaca', borderRadius: '8px', color: '#991b1b', fontSize: '0.875rem', display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
            <AlertCircle size={20} style={{ flexShrink: 0 }} />
            <div>{error}</div>
          </div>
        )}

        {successMsg && (
          <div style={{ marginBottom: '1.5rem', padding: '1rem 1.25rem', background: '#f0fdf4', border: '1px solid #bbf7d0', borderRadius: '8px', color: '#166534', fontSize: '0.875rem', display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
            <CheckCircle2 size={20} style={{ flexShrink: 0 }} />
            <div>{successMsg}</div>
          </div>
        )}

        {/* Upload Zone Card */}
        <div className="edvana-card" style={{ marginBottom: '1.5rem' }}>
          <div className="edvana-card-header">
            <h2 className="edvana-card-title">Upload Admitted Candidate List (.xlsx, .xls, .csv)</h2>
            <p className="edvana-card-description">
              Upload authoritative government seat allotment report with 59 standardized attributes
            </p>
          </div>
          <div className="edvana-card-body">
            <div
              style={{
                border: '2px dashed var(--edvana-border, #cbd5e1)',
                borderRadius: '8px',
                padding: '2.5rem 1.5rem',
                textAlign: 'center',
                background: '#f8fafc',
                cursor: 'pointer',
                transition: 'border-color 0.15s ease',
              }}
              onClick={() => fileInputRef.current?.click()}
            >
              <FileSpreadsheet
                size={52}
                style={{ color: 'var(--edvana-primary, #1d4ed8)', margin: '0 auto 1rem', display: 'block' }}
              />
              <div style={{ fontWeight: 700, fontSize: '1.05rem', color: '#0f172a' }}>
                {uploading
                  ? 'Validating & staging records...'
                  : 'Click or Drag Candidate List Here'}
              </div>
              <p style={{ color: 'var(--edvana-text-muted, #64748b)', fontSize: '0.875rem', margin: '0.5rem 0 1.25rem' }}>
                Fully compatible with DTE Maharashtra exports (.xls, .xlsx, .csv) with standardized candidate attributes.
                FY and DSY lists are detected automatically.
              </p>
              <input
                ref={fileInputRef}
                type="file"
                accept=".xls,.xlsx,.csv"
                style={{ display: 'none' }}
                onChange={handleFileSelect}
                disabled={uploading}
              />
              <button
                type="button"
                className="edvana-btn edvana-btn-primary"
                disabled={uploading}
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '0.5rem',
                  margin: '0 auto',
                }}
              >
                <Upload size={16} /> Select Candidate File
              </button>
            </div>
          </div>
        </div>

        {/* Staging & Validation Results */}
        {activeBatch && (
          <div className="edvana-card" style={{ marginBottom: '1.5rem' }}>
            <div className="edvana-card-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '1rem' }}>
              <div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', flexWrap: 'wrap' }}>
                  <h2 className="edvana-card-title">Batch Review: {activeBatch.file_name}</h2>
                  <span
                    style={{
                      display: 'inline-flex',
                      alignItems: 'center',
                      gap: '0.3rem',
                      fontSize: '0.78rem',
                      fontWeight: 700,
                      padding: '0.2rem 0.65rem',
                      borderRadius: '9999px',
                      backgroundColor: activeBatch.admission_type === 'DIRECT_SECOND_YEAR' ? '#f3e8ff' : '#eff6ff',
                      color: activeBatch.admission_type === 'DIRECT_SECOND_YEAR' ? '#6b21a8' : '#1d4ed8',
                      border: `1px solid ${activeBatch.admission_type === 'DIRECT_SECOND_YEAR' ? '#d8b4fe' : '#bfdbfe'}`,
                    }}
                  >
                    {activeBatch.admission_type === 'DIRECT_SECOND_YEAR' ? '⚡ Direct Second Year (Sem 3)' : '🎓 First Year (Sem 1)'}
                  </span>
                  <Badge variant={activeBatch.status === 'COMPLETED' ? 'success' : 'primary'}>
                    {activeBatch.status_display}
                  </Badge>
                </div>
                <p className="edvana-card-description">
                  Uploaded on {activeBatch.created_at?.slice(0, 10)} by {activeBatch.uploaded_by_name}
                </p>
              </div>

              {(activeBatch.status === 'VALIDATED' || activeBatch.status === 'FAILED' || activeBatch.status === 'IMPORTING') && (
                <button
                  className="edvana-btn edvana-btn-primary"
                  onClick={handleCommit}
                  disabled={committing || activeBatch.valid_rows === 0}
                  style={{ display: 'inline-flex', alignItems: 'center', gap: '0.5rem', background: '#166534', borderColor: '#166534' }}
                >
                  <Database size={16} />
                  {committing
                    ? 'Ingesting to Core DB...'
                    : activeBatch.status === 'FAILED' || activeBatch.status === 'IMPORTING'
                    ? `Retry Ingestion (${activeBatch.valid_rows} Records)`
                    : `Commit ${activeBatch.valid_rows} Records to Core DB`}
                </button>
              )}
            </div>

            <div className="edvana-card-body">
              {/* Metric Counters with StatCard */}
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(170px, 1fr))', gap: '1rem', marginBottom: '1.75rem' }}>
                <StatCard
                  label="Total Rows"
                  value={activeBatch.total_rows}
                  hint="Parsed from document"
                  icon={Layers}
                  color="var(--edvana-brand)"
                  style={{ borderRadius: '20px' }}
                />
                <StatCard
                  label="Valid Candidates"
                  value={activeBatch.valid_rows}
                  hint="Ready for core import"
                  icon={CheckCircle2}
                  color="var(--edvana-success)"
                  style={{ borderRadius: '20px' }}
                />
                <StatCard
                  label="Invalid Records"
                  value={activeBatch.invalid_rows}
                  hint="Schema or format issues"
                  icon={XCircle}
                  color="var(--edvana-danger)"
                  style={{ borderRadius: '20px' }}
                />
                <StatCard
                  label="Duplicate Entries"
                  value={activeBatch.duplicate_rows}
                  hint="Already enrolled"
                  icon={AlertTriangle}
                  color="var(--edvana-warning)"
                  style={{ borderRadius: '20px' }}
                />
                <StatCard
                  label="Imported to DB"
                  value={activeBatch.imported_rows}
                  hint="Active student accounts"
                  icon={Database}
                  color="var(--edvana-info)"
                  style={{ borderRadius: '20px' }}
                />
              </div>

              {/* Rows Preview Table */}
              <h3 style={{ fontSize: '1rem', fontWeight: 600, marginBottom: '0.75rem', color: '#1e293b' }}>
                Staged Candidate Rows ({(activeBatch.rows || []).length})
              </h3>
              <DataTable
                columns={previewColumns}
                data={(activeBatch.rows || []).slice((rowPage - 1) * ROWS_PER_PAGE, rowPage * ROWS_PER_PAGE)}
                page={rowPage}
                pageSize={ROWS_PER_PAGE}
                totalCount={(activeBatch.rows || []).length}
                onPageChange={setRowPage}
                emptyMessage="No candidate records found in this batch."
              />
            </div>
          </div>
        )}

        {/* Previous Ingestion History */}
        <div className="edvana-card">
          <div className="edvana-card-header">
            <h2 className="edvana-card-title">Previous Ingestion Batches ({batches.length})</h2>
            <p className="edvana-card-description">Permanent audit trail of candidate lists processed into the system</p>
          </div>
          <div className="edvana-card-body" style={{ padding: 0 }}>
            <DataTable
              columns={batchColumns}
              data={batches}
              keyExtractor={(b) => b.id}
              pageSize={5}
              emptyTitle="No Batches Uploaded Yet"
              emptyMessage="Upload your first government candidate allotment list above."
            />
          </div>
        </div>
      </div>
    </>
  );
}
