import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import studentApi from '../../api/studentApi';
import academicApi from '../../api/academicApi';
import PageHeader from '../../components/common/PageHeader';
import DataTable from '../../components/common/DataTable';
import Badge from '../../components/common/Badge';
import Modal from '../../components/common/Modal';
import FormField from '../../components/common/FormField';
import { ErrorState } from '../../components/common/StateDisplays';
import {
  Search,
  RotateCcw,
  KeyRound,
  Unlock,
  Eye,
  EyeOff,
  Lock,
  ChevronRight,
} from 'lucide-react';

/**
 * HOD Student Account Admin.
 *
 * Department student roster with search + filters, where the HOD can:
 *  1. Reset a student's login password (typed by the HOD; student is forced
 *     to change it at next login).
 *  2. Unlock a locked profile so the student gets one more self-service edit
 *     (the student re-locks their profile when done).
 *
 * Authorization is enforced server-side: a HOD can only act on students of
 * their own department; the UI simply reflects the server's decisions.
 */

const extractFieldErrors = (err) => {
  const data = err?.response?.data || {};
  const errors = {};
  if (data.detail) {
    errors.detail = data.detail;
  }
  for (const key of ['new_password', 'confirm_password', 'reason']) {
    if (data[key]) {
      errors[key] = Array.isArray(data[key]) ? data[key].join(' ') : String(data[key]);
    }
  }
  return errors;
};

export default function HODStudentAdminPage() {
  const navigate = useNavigate();
  const { user } = useAuth();

  const [students, setStudents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [notice, setNotice] = useState(null);

  // Pagination
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(50);
  const [totalCount, setTotalCount] = useState(0);

  // Filters
  const [departments, setDepartments] = useState([]);
  const [search, setSearch] = useState('');
  const [appliedSearch, setAppliedSearch] = useState('');
  const [selectedYear, setSelectedYear] = useState('');
  const [selectedDiv, setSelectedDiv] = useState('');
  const [selectedStatus, setSelectedStatus] = useState('');

  // Action modal state: null | { student, mode: 'unlock' | 'reset-password' }
  const [actionModal, setActionModal] = useState(null);

  // Is the viewer scoped to a single department? (HOD role assignment carries it.)
  const hodDeptId = (user?.roles || [])
    .filter((r) => r.status === 'ACTIVE')
    .find((r) => r.codename === 'HOD')?.department_id || '';
  const [selectedDept, setSelectedDept] = useState(hodDeptId);

  useEffect(() => {
    // Non-critical: dropdown options only; server scopes actions regardless.
    academicApi.getDepartments()
      .then((res) => setDepartments(res.data?.results || res.data || []))
      .catch(() => setDepartments([]));
  }, []);

  const loadStudents = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);

      const params = { page, page_size: pageSize };
      if (appliedSearch.trim()) params.search = appliedSearch.trim();
      if (selectedDept) params.department = selectedDept;
      if (selectedYear) params.year_level = selectedYear;
      if (selectedDiv) params.division = selectedDiv;
      if (selectedStatus) params.status = selectedStatus;

      const res = await studentApi.getStudents(params);

      if (res.data?.results !== undefined) {
        setStudents(res.data.results);
        setTotalCount(res.data.count || 0);
      } else if (Array.isArray(res.data)) {
        setStudents(res.data);
        setTotalCount(res.data.length);
      } else {
        setStudents([]);
        setTotalCount(0);
      }
    } catch (err) {
      setError(
        err.response?.data?.detail ||
          err.response?.data?.message ||
          'Failed to load student list. Please check your network or permissions.'
      );
      setStudents([]);
      setTotalCount(0);
    } finally {
      setLoading(false);
    }
  }, [page, pageSize, appliedSearch, selectedDept, selectedYear, selectedDiv, selectedStatus]);

  useEffect(() => {
    loadStudents();
  }, [loadStudents]);

  const handleSearchSubmit = (e) => {
    if (e) e.preventDefault();
    setPage(1);
    setAppliedSearch(search.trim());
  };

  const handleResetFilters = () => {
    setSearch('');
    setAppliedSearch('');
    setSelectedYear('');
    setSelectedDiv('');
    setSelectedStatus('');
    setSelectedDept(hodDeptId);
    setPage(1);
  };

  const buttonFocus = (e, direction) => {
    e.currentTarget.style.borderColor = direction === 'in' ? '#2563eb' : '#cbd5e1';
    e.currentTarget.style.color = direction === 'in' ? '#2563eb' : '#1e293b';
  };

  // ─── Columns ───
  const columns = [
    {
      header: 'S.N.',
      width: '56px',
      align: 'center',
      render: (_, idx) => (
        <span style={{ fontSize: '0.8125rem', color: '#64748b', fontWeight: 600 }}>
          {(page - 1) * pageSize + idx + 1}
        </span>
      ),
    },
    {
      header: 'ENROLL NO.',
      render: (row) => (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '2px' }}>
          <span
            onClick={() => navigate(`/students/${row.id}`)}
            style={{
              color: '#2563eb',
              fontWeight: 700,
              fontSize: '0.8125rem',
              cursor: 'pointer',
              fontFamily: 'var(--edvana-font-mono, monospace)',
            }}
            title="Click to view student record"
          >
            {row.enrollment_no || row.application_id || '—'}
          </span>
          <span style={{ fontSize: '0.6875rem', color: '#94a3b8' }}>
            {row.has_login === false ? 'No login account' : (row.department_code || '').toUpperCase()}
          </span>
        </div>
      ),
    },
    {
      header: 'NAME',
      render: (row) => {
        const fullName = (row.display_name || `${row.first_name || ''} ${row.last_name || ''}`.trim() || '—').toUpperCase();
        const sub = [
          row.division_name ? `Div ${row.division_name}` : null,
          row.year_name || (row.semester_number ? `Sem ${row.semester_number}` : null),
        ].filter(Boolean).join(' • ') || '—';
        return (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '2px' }}>
            <span style={{ fontWeight: 700, color: '#0f172a', fontSize: '0.8125rem' }}>
              {fullName}
            </span>
            <span
              style={{
                fontSize: '0.6875rem',
                color: '#64748b',
                textTransform: 'uppercase',
                letterSpacing: '0.02em',
              }}
            >
              {sub}
            </span>
          </div>
        );
      },
    },
    {
      header: 'USERNAME',
      render: (row) => (
        <span
          style={{
            fontSize: '0.8125rem',
            color: '#334155',
            fontFamily: 'var(--edvana-font-mono, monospace)',
          }}
        >
          {row.username || '—'}
        </span>
      ),
    },
    {
      header: 'PROFILE STATUS',
      align: 'center',
      render: (row) =>
        row.profile_locked === false ? (
          <Badge variant="warning" dot>Open for edit</Badge>
        ) : (
          <Badge variant="neutral" dot>Locked</Badge>
        ),
    },
    {
      header: 'ACTIONS',
      align: 'right',
      render: (row) => {
        const noLogin = row.has_login === false;
        return (
          <div
            style={{
              display: 'flex',
              justifyContent: 'flex-end',
              gap: '0.5rem',
              flexWrap: 'wrap',
            }}
          >
            <button
              type="button"
              disabled={noLogin}
              onClick={() => setActionModal({ student: row, mode: 'reset-password' })}
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '0.3rem',
                padding: '0.35rem 0.75rem',
                fontSize: '0.75rem',
                fontWeight: 600,
                color: noLogin ? '#cbd5e1' : '#1e293b',
                backgroundColor: '#ffffff',
                border: '1px solid #cbd5e1',
                borderRadius: '9999px',
                cursor: noLogin ? 'not-allowed' : 'pointer',
                opacity: noLogin ? 0.55 : 1,
                transition: 'all 0.15s ease',
              }}
              onMouseEnter={(e) => !noLogin && buttonFocus(e, 'in')}
              onMouseLeave={(e) => !noLogin && buttonFocus(e, 'out')}
              title={noLogin ? 'Student has no login account yet' : 'Set a new password for this student'}
            >
              <KeyRound size={13} />
              <span>Reset Password</span>
            </button>
            <button
              type="button"
              disabled={row.profile_locked === false}
              onClick={() => setActionModal({ student: row, mode: 'unlock' })}
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '0.3rem',
                padding: '0.35rem 0.75rem',
                fontSize: '0.75rem',
                fontWeight: 600,
                color: '#1e293b',
                backgroundColor: '#ffffff',
                border: '1px solid #cbd5e1',
                borderRadius: '9999px',
                cursor: row.profile_locked === false ? 'not-allowed' : 'pointer',
                opacity: row.profile_locked === false ? 0.55 : 1,
                transition: 'all 0.15s ease',
              }}
              onMouseEnter={(e) => row.profile_locked !== false && buttonFocus(e, 'in')}
              onMouseLeave={(e) => row.profile_locked !== false && buttonFocus(e, 'out')}
              title={
                row.profile_locked === false
                  ? 'Profile is already open for editing'
                  : 'Allow the student one more profile edit'
              }
            >
              <Unlock size={13} />
              <span>Unlock Profile</span>
            </button>
          </div>
        );
      },
    },
  ];

  const fadeNotice = (msg) => {
    setNotice(msg);
    setTimeout(() => setNotice(null), 6000);
  };

  const hasAnyFilter =
    search || appliedSearch || selectedDept || selectedYear || selectedDiv || selectedStatus;

  return (
    <>
      <PageHeader
        breadcrumbs={[
          { label: 'Home', to: '/dashboard' },
          { label: 'Student Admin' },
        ]}
        title="Student Account Admin"
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
              <div
                style={{
                  fontSize: '0.8125rem',
                  fontWeight: 600,
                  color: '#2563eb',
                  marginBottom: '0.25rem',
                }}
              >
                Academics / Student Account Admin
              </div>
              <h2
                style={{
                  fontSize: '1.5rem',
                  fontWeight: 700,
                  color: '#0f172a',
                  margin: 0,
                  lineHeight: 1.25,
                }}
              >
                Student Account &amp; Profile Administration
              </h2>
              <p
                style={{
                  fontSize: '0.8125rem',
                  color: '#64748b',
                  margin: '0.35rem 0 0 0',
                }}
              >
                Reset a forgotten student password or unlock a locked profile for one
                more edit. The student must change the reset password at their next
                login. Every action requires a written reason and is recorded in the
                security audit trail.
              </p>
            </div>
          </div>

          {/* Notice banner (post-action feedback) */}
          {notice && (
            <div
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
              role="status"
            >
              {notice}
            </div>
          )}

          {/* Filter bar */}
          <form
            onSubmit={handleSearchSubmit}
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
            {/* Search */}
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
                placeholder="Search name, enrollment no, username..."
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

            {/* Year */}
            <select
              className="edvana-input"
              value={selectedYear}
              onChange={(e) => {
                setSelectedYear(e.target.value);
                setPage(1);
              }}
              style={{
                flex: '0 1 135px',
                height: '38px',
                borderRadius: '8px',
                fontSize: '0.8125rem',
                borderColor: '#cbd5e1',
                padding: '0 0.75rem',
                color: '#334155',
                fontWeight: selectedYear ? 600 : 400,
              }}
            >
              <option value="">All Class Years</option>
              <option value="1">FY (1st Year)</option>
              <option value="2">SY (2nd Year)</option>
              <option value="3">TY (3rd Year)</option>
              <option value="4">Final Year</option>
            </select>

            {/* Department */}
            <select
              className="edvana-input"
              value={selectedDept}
              onChange={(e) => {
                setSelectedDept(e.target.value);
                setPage(1);
              }}
              style={{
                flex: '0 1 200px',
                height: '38px',
                borderRadius: '8px',
                fontSize: '0.8125rem',
                borderColor: '#cbd5e1',
                padding: '0 0.75rem',
                color: '#334155',
              }}
            >
              <option value="">All Departments</option>
              {departments.map((d) => (
                <option key={d.id || d.code} value={d.id}>
                  {d.name} ({d.code})
                </option>
              ))}
            </select>

            {/* Division */}
            <select
              className="edvana-input"
              value={selectedDiv}
              onChange={(e) => {
                setSelectedDiv(e.target.value);
                setPage(1);
              }}
              style={{
                flex: '0 1 130px',
                height: '38px',
                borderRadius: '8px',
                fontSize: '0.8125rem',
                borderColor: '#cbd5e1',
                padding: '0 0.75rem',
                color: '#334155',
                fontWeight: selectedDiv ? 600 : 400,
              }}
            >
              <option value="">All Divisions</option>
              <option value="A">Division A</option>
              <option value="B">Division B</option>
              <option value="C">Division C</option>
            </select>

            {/* Status */}
            <select
              className="edvana-input"
              value={selectedStatus}
              onChange={(e) => {
                setSelectedStatus(e.target.value);
                setPage(1);
              }}
              style={{
                flex: '0 1 125px',
                height: '38px',
                borderRadius: '8px',
                fontSize: '0.8125rem',
                borderColor: '#cbd5e1',
                padding: '0 0.75rem',
                color: '#334155',
                fontWeight: selectedStatus ? 600 : 400,
              }}
            >
              <option value="">All Statuses</option>
              <option value="ACTIVE">Active</option>
              <option value="PASSED_OUT">Passed Out</option>
              <option value="DETAINED">Detained</option>
            </select>

            <button
              type="submit"
              className="edvana-btn edvana-btn-primary"
              style={{
                height: '38px',
                padding: '0 0.875rem',
                fontSize: '0.8125rem',
                borderRadius: '8px',
                display: 'inline-flex',
                alignItems: 'center',
                gap: '0.35rem',
              }}
            >
              <Search size={14} />
              <span>Search</span>
            </button>

            {hasAnyFilter && (
              <button
                type="button"
                onClick={handleResetFilters}
                className="edvana-btn"
                style={{
                  height: '38px',
                  padding: '0 0.75rem',
                  fontSize: '0.8125rem',
                  borderRadius: '8px',
                  backgroundColor: '#f8fafc',
                  border: '1px solid #cbd5e1',
                  color: '#64748b',
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '0.35rem',
                }}
                title="Clear all filters"
              >
                <RotateCcw size={13} />
                <span>Reset</span>
              </button>
            )}
          </form>

          {/* Results summary */}
          <div
            style={{
              padding: '0.75rem 0',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              flexWrap: 'wrap',
              gap: '0.75rem',
              fontSize: '0.8125rem',
              color: '#64748b',
            }}
          >
            <div>
              <strong>{totalCount}</strong> student{totalCount === 1 ? '' : 's'} found
              {appliedSearch && <span> matching &ldquo;{appliedSearch}&rdquo;</span>}
              {selectedDiv && <span>, Div {selectedDiv}</span>}
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <span>Show:</span>
              <select
                className="edvana-input"
                value={pageSize}
                onChange={(e) => {
                  setPageSize(Number(e.target.value));
                  setPage(1);
                }}
                style={{
                  height: '30px',
                  padding: '0 0.5rem',
                  fontSize: '0.75rem',
                  borderRadius: '6px',
                  borderColor: '#cbd5e1',
                }}
              >
                <option value={25}>25 per page</option>
                <option value={50}>50 per page</option>
                <option value={100}>100 per page</option>
                <option value={250}>250 (All)</option>
              </select>
            </div>
          </div>

          {/* Error */}
          {error && (
            <div style={{ marginBottom: '1rem' }}>
              <ErrorState
                title="Unable to load students"
                message={error}
                onRetry={loadStudents}
              />
            </div>
          )}

          <DataTable
            columns={columns}
            data={students}
            loading={loading}
            emptyMessage={
              hasAnyFilter
                ? 'No students found matching your filter criteria. Try clearing or broadening filters.'
                : 'No student records found in your department.'
            }
            page={page}
            pageSize={pageSize}
            totalCount={totalCount}
            onPageChange={(newPage) => setPage(newPage)}
          />
        </div>
      </div>

      {actionModal && (
        <StudentActionModal
          mode={actionModal.mode}
          student={actionModal.student}
          onClose={() => setActionModal(null)}
          onSuccess={(msg) => {
            setActionModal(null);
            fadeNotice(msg);
            loadStudents();
          }}
        />
      )}
    </>
  );
}

/**
 * Popup modal for the two actions. Handles typing + validation of:
 *  - 'reset-password': new password + confirm (>= 12 chars, != username)
 *  - 'unlock': written reason (>= 5 chars)
 * Server errors map back onto the individual fields.
 */
function StudentActionModal({ mode, student, onClose, onSuccess }) {
  const isReset = mode === 'reset-password';

  const [form, setForm] = useState({ new_password: '', confirm_password: '', reason: '' });
  const [errors, setErrors] = useState({});
  const [showPassword, setShowPassword] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const studentName = (
    student.display_name || `${student.first_name || ''} ${student.last_name || ''}`.trim()
  ).toUpperCase();

  const setField = (key, value) => {
    setForm((f) => ({ ...f, [key]: value }));
    setErrors((e) => ({ ...e, [key]: undefined, detail: undefined }));
  };

  const validateLocal = () => {
    const next = {};
    if (isReset) {
      if ((form.new_password || '').length < 12) {
        next.new_password = 'Password must be at least 12 characters.';
      } else if (form.new_password === (student.username || student.enrollment_no || '')) {
        next.new_password = 'Password cannot be the same as the login username.';
      }
      if (form.new_password !== form.confirm_password) {
        next.confirm_password = 'Passwords do not match.';
      }
    }
    if ((form.reason || '').trim().length < 5) {
      next.reason = 'A short written reason (at least 5 characters) is required and is audited.';
    }
    setErrors(next);
    return Object.keys(next).length === 0;
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!validateLocal()) return;
    setSubmitting(true);
    try {
      if (isReset) {
        await studentApi.resetStudentPassword(student.id, {
          new_password: form.new_password,
          reason: form.reason.trim(),
        });
        onSuccess(
          <>Password reset for <strong>{studentName}</strong>. Share it with the student directly — they must change it at their next login.</>
        );
      } else {
        await studentApi.unlockStudentProfile(student.id, form.reason.trim());
        onSuccess(
          <>Profile unlocked for <strong>{studentName}</strong> — the student may now edit once more and should lock their profile when done.</>
        );
      }
    } catch (err) {
      const next = extractFieldErrors(err);
      if (!Object.keys(next).length) {
        next.detail = err?.message || 'Action failed. Please try again.';
      }
      setErrors(next);
      setSubmitting(false);
    }
  };

  const modalInput = {
    height: '38px',
    borderRadius: '8px',
    fontSize: '0.8125rem',
    borderColor: '#cbd5e1',
    width: '100%',
  };

  return (
    <Modal isOpen onClose={onClose} title={isReset ? 'Reset Student Password' : 'Unlock Student Profile'}>
      <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
        {/* Student context */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '0.75rem',
            padding: '0.75rem 1rem',
            backgroundColor: '#f8fafc',
            border: '1px solid #e2e8f0',
            borderRadius: '8px',
          }}
        >
          <span
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              justifyContent: 'center',
              width: '36px',
              height: '36px',
              borderRadius: '50%',
              backgroundColor: '#eff6ff',
              color: '#2563eb',
              fontWeight: 700,
              fontSize: '0.8125rem',
              flexShrink: 0,
            }}
          >
            {(studentName.split(' ')[0] || 'S').slice(0, 2).toUpperCase()}
          </span>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1px' }}>
            <span style={{ fontWeight: 700, fontSize: '0.8125rem', color: '#0f172a' }}>
              {studentName}
            </span>
            <span
              style={{
                fontSize: '0.6875rem',
                color: '#64748b',
                fontFamily: 'var(--edvana-font-mono, monospace)',
              }}
            >
              {student.username || student.enrollment_no || '—'} •{' '}
              {(student.department_code || '').toUpperCase()}{' '}
              {student.division_name ? `Div ${student.division_name}` : ''}
            </span>
          </div>
        </div>

        {isReset ? (
          <>
            <FormField label="New Password" required error={errors.new_password}>
              <div style={{ position: 'relative' }}>
                <input
                  type={showPassword ? 'text' : 'password'}
                  className="edvana-input"
                  placeholder="At least 12 characters"
                  value={form.new_password}
                  onChange={(e) => setField('new_password', e.target.value)}
                  autoComplete="new-password"
                  style={{ ...modalInput, paddingRight: '38px' }}
                />
                <button
                  type="button"
                  onClick={() => setShowPassword((v) => !v)}
                  aria-label={showPassword ? 'Hide password' : 'Show password'}
                  title={showPassword ? 'Hide password' : 'Show password'}
                  style={{
                    position: 'absolute',
                    right: '6px',
                    top: '50%',
                    transform: 'translateY(-50%)',
                    padding: '0.25rem',
                    color: '#64748b',
                    background: 'transparent',
                    border: 'none',
                    cursor: 'pointer',
                    display: 'inline-flex',
                  }}
                >
                  {showPassword ? <EyeOff size={15} /> : <Eye size={15} />}
                </button>
              </div>
            </FormField>

            <FormField
              label="Confirm Password"
              required
              error={errors.confirm_password}
            >
              <input
                type={showPassword ? 'text' : 'password'}
                className="edvana-input"
                placeholder="Re-enter the new password"
                value={form.confirm_password}
                onChange={(e) => setField('confirm_password', e.target.value)}
                autoComplete="new-password"
                style={modalInput}
              />
            </FormField>

            <p style={{ fontSize: '0.75rem', color: '#64748b', margin: 0, lineHeight: 1.5 }}>
              The student will be required to change this password the first time they
              log in again. The password is never stored in logs and is visible only
              while you type it here.
            </p>
          </>
        ) : (
          <p style={{ fontSize: '0.8125rem', color: '#475569', margin: 0, lineHeight: 1.5 }}>
            This will let <strong>{studentName}</strong> edit their profile once more
            (corrections/upload included). Earlier teacher reviews and HOD endorsements
            stay on record. The student should lock the profile again when finished.
          </p>
        )}

        {errors.detail && (
          <div
            style={{
              padding: '0.65rem 0.85rem',
              backgroundColor: '#fef2f2',
              border: '1px solid #fecaca',
              color: '#dc2626',
              borderRadius: '8px',
              fontSize: '0.8125rem',
            }}
            role="alert"
          >
            {errors.detail}
          </div>
        )}

        <FormField label="Reason (audited)" required error={errors.reason}>
          <textarea
            className="edvana-input"
            rows={2}
            placeholder={isReset ? 'e.g. Student reported forgotten password at help desk' : 'e.g. Student needs to correct misspelled father name'}
            value={form.reason}
            onChange={(e) => setField('reason', e.target.value)}
            style={{ ...modalInput, height: 'auto', resize: 'vertical' }}
          />
        </FormField>

        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem', marginTop: '0.5rem' }}>
          <button
            type="button"
            className="edvana-btn edvana-btn-secondary"
            onClick={onClose}
            disabled={submitting}
          >
            Cancel
          </button>
          <button type="submit" className="edvana-btn edvana-btn-primary" disabled={submitting}>
            {isReset ? <KeyRound size={15} /> : <Lock size={15} />}
            <span>{submitting ? 'Working…' : isReset ? 'Reset Password' : 'Unlock for Edit'}</span>
          </button>
        </div>
      </form>
    </Modal>
  );
}
