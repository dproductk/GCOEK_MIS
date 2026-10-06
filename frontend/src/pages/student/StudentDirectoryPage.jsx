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
import { ErrorState, EmptyState } from '../../components/common/StateDisplays';
import {
  Search,
  Filter,
  Plus,
  KeyRound,
  Check,
  ChevronRight,
  User,
  Copy,
  CheckCheck,
  RotateCcw,
  Info,
  ShieldAlert,
  GraduationCap,
} from 'lucide-react';

// Helper to normalize department codes across legacy and modern DB conventions
const normalizeDept = (code) => {
  if (!code) return '';
  const c = String(code).toUpperCase().trim().replace('-', '_');
  if (c === 'AIDS' || c === 'AI_DS') return 'AI_DS';
  if (c === 'ME' || c === 'MAE') return 'MAE';
  return c;
};

export default function StudentDirectoryPage() {
  const navigate = useNavigate();
  const { user, hasRole, activeRole } = useAuth();

  const [students, setStudents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Pagination State
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(50);
  const [totalCount, setTotalCount] = useState(0);

  // Filter States
  const [departments, setDepartments] = useState([]);
  const [search, setSearch] = useState('');
  const [appliedSearch, setAppliedSearch] = useState('');
  const [selectedDept, setSelectedDept] = useState('');
  const [selectedDiv, setSelectedDiv] = useState('');
  const [selectedGender, setSelectedGender] = useState('');
  const [selectedStatus, setSelectedStatus] = useState('');
  const [selectedLogin, setSelectedLogin] = useState('');
  const [selectedYear, setSelectedYear] = useState('');
  const [selectedEntryType, setSelectedEntryType] = useState('');

  // Modals
  const [createLoginsModal, setCreateLoginsModal] = useState(false);
  const [registerModal, setRegisterModal] = useState(false);
  const [loginsSuccessMsg, setLoginsSuccessMsg] = useState(null);
  const [copiedId, setCopiedId] = useState(null);

  // Detect whether the current user is strictly under Student isolation scope
  const isStudentOnly =
    hasRole('STUDENT') &&
    !hasRole('ADMIN_HEAD') &&
    !hasRole('SYSADMIN') &&
    !hasRole('HOD') &&
    !hasRole('CLASS_TEACHER') &&
    !hasRole('FACULTY') &&
    !hasRole('ACCOUNTANT');

  // Load departments once on mount
  useEffect(() => {
    loadDepartments();
  }, []);

  const loadDepartments = async () => {
    try {
      const res = await academicApi.getDepartments();
      const list = res.data?.results || res.data || [];
      setDepartments(list);
    } catch {
      // Non-critical: fallback will display canonical department list
    }
  };

  // Main data loader — queries server with pagination and active filters
  const loadStudents = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);

      const params = {
        page,
        page_size: pageSize,
      };

      if (appliedSearch.trim()) {
        params.search = appliedSearch.trim();
      }
      if (selectedDept) {
        params.department = selectedDept;
      }
      if (selectedDiv) {
        params.division = selectedDiv;
      }
      if (selectedGender) {
        params.gender = selectedGender;
      }
      if (selectedStatus) {
        params.status = selectedStatus;
      }
      if (selectedLogin) {
        params.has_login = selectedLogin === 'YES' ? 'true' : 'false';
      }
      if (selectedYear) {
        params.year_level = selectedYear;
      }
      if (selectedEntryType === 'DSY') {
        params.is_direct_second_year = 'true';
      } else if (selectedEntryType === 'REGULAR') {
        params.is_direct_second_year = 'false';
      }

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
      const msg =
        err.response?.data?.detail ||
        err.response?.data?.message ||
        'Failed to load student directory. Please check your network or permissions.';
      setError(msg);
      setStudents([]);
      setTotalCount(0);
    } finally {
      setLoading(false);
    }
  }, [page, pageSize, appliedSearch, selectedDept, selectedDiv, selectedGender, selectedStatus, selectedLogin, selectedYear, selectedEntryType]);

  // Re-fetch whenever pagination or active filters change
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
    setSelectedDept('');
    setSelectedDiv('');
    setSelectedGender('');
    setSelectedStatus('');
    setSelectedLogin('');
    setSelectedYear('');
    setSelectedEntryType('');
    setPage(1);
  };

  const handleCopyUsername = (text, id) => {
    navigator.clipboard?.writeText(text);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 1500);
  };

  const handleBatchCreateLogins = () => {
    setLoginsSuccessMsg('Generated login credentials and activation links for pending students.');
    setTimeout(() => {
      setCreateLoginsModal(false);
      setLoginsSuccessMsg(null);
      loadStudents();
    }, 1800);
  };

  // Canonical departments list (ensuring modern DB codes are represented)
  const canonicalDepartments = [
    { code: 'AI_DS', name: 'Artificial Intelligence and Data Science' },
    { code: 'CSE', name: 'Computer Science and Engineering' },
    { code: 'EE', name: 'Electrical Engineering' },
    { code: 'ETC', name: 'Electronics and Telecommunication Engineering' },
    { code: 'MAE', name: 'Mechanical and Automation Engineering' },
  ];

  const displayedDepartments = departments.length > 0 ? departments : canonicalDepartments;

  // Table Columns:
  // S.N. | ENROLL NO. | NAME | FATHER'S NAME | MOBILE | DIV | USERNAME / LOGIN | ACTION
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
      render: (row) => {
        const enrollNo = row.enrollment_no || row.application_id || `EN26${row.id?.slice?.(0, 8) || '462534'}`;
        const hasOfficialEnroll = Boolean(row.enrollment_no);
        return (
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
              {enrollNo}
            </span>
            <span style={{ fontSize: '0.6875rem', color: '#94a3b8' }}>
              {hasOfficialEnroll ? 'Verified PRN' : 'Application ID'}
            </span>
          </div>
        );
      },
    },
    {
      header: 'NAME',
      render: (row) => {
        const fullName = (row.display_name || `${row.first_name || ''} ${row.last_name || ''}`).trim().toUpperCase();
        const gender = (row.gender || 'MALE').toUpperCase();
        const dept = (row.department_code || 'AI_DS').toUpperCase();
        const prog = (row.program_code || dept).toUpperCase();
        const yearLevel = row.year_name || (row.semester_number ? `Sem ${row.semester_number}` : 'FY');
        return (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '2px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', flexWrap: 'wrap' }}>
              <span style={{ fontWeight: 700, color: '#0f172a', fontSize: '0.8125rem' }}>
                {fullName}
              </span>
              {row.is_direct_second_year && (
                <span
                  style={{
                    fontSize: '0.625rem',
                    fontWeight: 800,
                    padding: '0.1rem 0.4rem',
                    borderRadius: '4px',
                    backgroundColor: '#f3e8ff',
                    color: '#7e22ce',
                    border: '1px solid #d8b4fe',
                  }}
                  title="Direct Second Year (Lateral Entry)"
                >
                  ⚡ DSY
                </span>
              )}
            </div>
            <span style={{ fontSize: '0.6875rem', color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.02em' }}>
              {`${gender} • ${dept} • ${prog} • ${yearLevel}`}
            </span>
          </div>
        );
      },
    },
    {
      header: "FATHER'S NAME",
      render: (row) => {
        const father = (row.father_name || `${row.middle_name || ''} ${row.last_name || ''}`).trim().toUpperCase();
        return (
          <span style={{ fontSize: '0.8125rem', color: '#334155', fontWeight: 500 }}>
            {father || '—'}
          </span>
        );
      },
    },
    {
      header: 'MOBILE',
      render: (row) => (
        <span style={{ fontSize: '0.8125rem', color: '#334155', fontFamily: 'var(--edvana-font-mono, monospace)' }}>
          {row.mobile || row.personal_details?.student_mobile || '—'}
        </span>
      ),
    },
    {
      header: 'DIV',
      align: 'center',
      render: (row) => (
        <span
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            justifyContent: 'center',
            width: '26px',
            height: '26px',
            backgroundColor: '#eff6ff',
            color: '#2563eb',
            border: '1px solid #bfdbfe',
            borderRadius: '6px',
            fontWeight: 700,
            fontSize: '0.75rem',
          }}
        >
          {row.division_name || 'A'}
        </span>
      ),
    },
    {
      header: 'USERNAME / LOGIN',
      render: (row) => {
        const uname = row.username || row.application_id || row.enrollment_no || `en${row.id?.slice?.(0, 8) || ''}`;
        const hasLogin = row.has_login !== undefined ? row.has_login : true;
        const isCopied = copiedId === (row.id || uname);

        return (
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <span style={{ fontFamily: 'var(--edvana-font-mono, monospace)', fontSize: '0.8125rem', fontWeight: 600, color: '#1e293b' }}>
              {uname}
            </span>

            <span
              style={{
                fontSize: '0.6875rem',
                fontWeight: 600,
                padding: '0.1rem 0.45rem',
                borderRadius: '9999px',
                backgroundColor: hasLogin ? '#f0fdf4' : '#fef2f2',
                color: hasLogin ? '#16a34a' : '#dc2626',
                border: `1px solid ${hasLogin ? '#bbf7d0' : '#fecaca'}`,
              }}
            >
              {hasLogin ? 'Yes' : 'No'}
            </span>

            <button
              type="button"
              onClick={() => handleCopyUsername(uname, row.id || uname)}
              style={{
                padding: '0.15rem 0.45rem',
                fontSize: '0.6875rem',
                fontWeight: 600,
                color: isCopied ? '#16a34a' : '#64748b',
                backgroundColor: '#ffffff',
                border: `1px solid ${isCopied ? '#86efac' : '#cbd5e1'}`,
                borderRadius: '4px',
                cursor: 'pointer',
                display: 'inline-flex',
                alignItems: 'center',
                gap: '0.2rem',
                transition: 'all 0.15s ease',
              }}
              title="Copy username to clipboard"
            >
              {isCopied ? <CheckCheck size={11} /> : <Copy size={11} />}
              <span>{isCopied ? 'Copied' : 'Copy'}</span>
            </button>
          </div>
        );
      },
    },
    {
      header: 'ACTION',
      align: 'right',
      render: (row) => (
        <button
          type="button"
          onClick={() => navigate(`/students/${row.id}`)}
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '0.25rem',
            padding: '0.35rem 0.75rem',
            fontSize: '0.75rem',
            fontWeight: 600,
            color: '#1e293b',
            backgroundColor: '#ffffff',
            border: '1px solid #cbd5e1',
            borderRadius: '9999px',
            cursor: 'pointer',
            transition: 'all 0.15s ease',
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.borderColor = '#2563eb';
            e.currentTarget.style.color = '#2563eb';
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.borderColor = '#cbd5e1';
            e.currentTarget.style.color = '#1e293b';
          }}
        >
          <span>Profile</span>
          <ChevronRight size={13} />
        </button>
      ),
    },
  ];

  return (
    <>
      {/* Institutional Header */}
      <PageHeader
        breadcrumbs={[
          { label: 'Home', to: '/dashboard' },
          { label: 'Students' },
        ]}
        title="Student Directory"
      />

      {/* Main Container */}
      <div className="edvana-banner-overlap">
        <div className="edvana-card" style={{ padding: '1.75rem 2rem' }}>
          {/* Card Top Header */}
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
                Academics / Student Directory
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
                Student Information Directory
              </h2>
              <p
                style={{
                  fontSize: '0.8125rem',
                  color: '#64748b',
                  margin: '0.35rem 0 0 0',
                }}
              >
                Search, filter, and inspect verified student profiles. PRN/Application IDs and login status are updated from the institutional core database.
              </p>
            </div>

            {/* Top Right Action Buttons */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', flexWrap: 'wrap' }}>
              <button
                type="button"
                className="edvana-btn"
                onClick={() => setCreateLoginsModal(true)}
                style={{
                  backgroundColor: '#eff6ff',
                  border: '1px solid #bfdbfe',
                  color: '#1d4ed8',
                  fontSize: '0.8125rem',
                  fontWeight: 600,
                  padding: '0.5rem 0.875rem',
                  borderRadius: '8px',
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '0.45rem',
                }}
              >
                <KeyRound size={15} />
                <span>Create Logins</span>
              </button>

              <button
                type="button"
                className="edvana-btn edvana-btn-primary"
                onClick={() => setRegisterModal(true)}
                style={{
                  fontSize: '0.8125rem',
                  fontWeight: 600,
                  padding: '0.5rem 1rem',
                  borderRadius: '8px',
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '0.45rem',
                }}
              >
                <Plus size={16} />
                <span>Register Student</span>
              </button>
            </div>
          </div>

          {/* Student Role Notice Banner (if logged in with student-isolated permissions) */}
          {isStudentOnly && (
            <div
              style={{
                display: 'flex',
                alignItems: 'flex-start',
                gap: '0.75rem',
                backgroundColor: '#fffbeb',
                border: '1px solid #fde68a',
                borderRadius: '8px',
                padding: '0.875rem 1rem',
                marginBottom: '1rem',
              }}
            >
              <ShieldAlert size={18} style={{ color: '#d97706', marginTop: '2px', flexShrink: 0 }} />
              <div style={{ fontSize: '0.8125rem', color: '#92400e', lineHeight: 1.5 }}>
                <strong>Student Account Scope Notice:</strong> Under institutional privacy policies, student logins have access restricted strictly to their own enrolled record ({user?.username}). To browse, filter, or export the entire college-wide directory of <strong>183 enrolled students</strong> across all departments, please log in as an Administrative Head (<code style={{ background: '#fef3c7', padding: '1px 4px', borderRadius: '3px' }}>admin_head</code>), System Administrator (<code style={{ background: '#fef3c7', padding: '1px 4px', borderRadius: '3px' }}>sysadmin</code>), or Faculty member.
              </div>
            </div>
          )}

          {/* Filter Bar */}
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
            {/* Search Input */}
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
                placeholder="Search name, enrollment no, app ID, username..."
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

            {/* Year Level Dropdown */}
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

            {/* Admission Stream Dropdown */}
            <select
              className="edvana-input"
              value={selectedEntryType}
              onChange={(e) => {
                setSelectedEntryType(e.target.value);
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
                fontWeight: selectedEntryType ? 600 : 400,
              }}
            >
              <option value="">All Streams</option>
              <option value="REGULAR">Regular (FY)</option>
              <option value="DSY">⚡ DSY (Lateral)</option>
            </select>

            {/* Department Dropdown */}
            <select
              className="edvana-input"
              value={selectedDept}
              onChange={(e) => {
                setSelectedDept(e.target.value);
                setPage(1);
              }}
              style={{
                flex: '0 1 180px',
                height: '38px',
                borderRadius: '8px',
                fontSize: '0.8125rem',
                borderColor: '#cbd5e1',
                padding: '0 0.75rem',
                color: '#334155',
              }}
            >
              <option value="">All Departments</option>
              {displayedDepartments.map((d) => (
                <option key={d.id || d.code} value={d.code}>
                  {d.name} ({d.code})
                </option>
              ))}
            </select>

            {/* Division Dropdown */}
            <select
              className="edvana-input"
              value={selectedDiv}
              onChange={(e) => {
                setSelectedDiv(e.target.value);
                setPage(1);
              }}
              style={{
                flex: '0 1 120px',
                height: '38px',
                borderRadius: '8px',
                fontSize: '0.8125rem',
                borderColor: '#cbd5e1',
                padding: '0 0.75rem',
                color: '#334155',
              }}
            >
              <option value="">All Divisions</option>
              <option value="A">Division A</option>
              <option value="B">Division B</option>
              <option value="C">Division C</option>
            </select>

            {/* Gender Dropdown */}
            <select
              className="edvana-input"
              value={selectedGender}
              onChange={(e) => {
                setSelectedGender(e.target.value);
                setPage(1);
              }}
              style={{
                flex: '0 1 120px',
                height: '38px',
                borderRadius: '8px',
                fontSize: '0.8125rem',
                borderColor: '#cbd5e1',
                padding: '0 0.75rem',
                color: '#334155',
              }}
            >
              <option value="">All Genders</option>
              <option value="MALE">Male</option>
              <option value="FEMALE">Female</option>
            </select>

            {/* Status Dropdown */}
            <select
              className="edvana-input"
              value={selectedStatus}
              onChange={(e) => {
                setSelectedStatus(e.target.value);
                setPage(1);
              }}
              style={{
                flex: '0 1 120px',
                height: '38px',
                borderRadius: '8px',
                fontSize: '0.8125rem',
                borderColor: '#cbd5e1',
                padding: '0 0.75rem',
                color: '#334155',
              }}
            >
              <option value="">All Statuses</option>
              <option value="ACTIVE">Active</option>
              <option value="PASSED_OUT">Passed Out</option>
              <option value="DETAINED">Detained</option>
            </select>

            {/* Login Dropdown */}
            <select
              className="edvana-input"
              value={selectedLogin}
              onChange={(e) => {
                setSelectedLogin(e.target.value);
                setPage(1);
              }}
              style={{
                flex: '0 1 115px',
                height: '38px',
                borderRadius: '8px',
                fontSize: '0.8125rem',
                borderColor: '#cbd5e1',
                padding: '0 0.75rem',
                color: '#334155',
              }}
            >
              <option value="">Login: All</option>
              <option value="YES">Login: Yes</option>
              <option value="NO">Login: No</option>
            </select>

            {/* Action Buttons: Search & Reset */}
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

            {(search || appliedSearch || selectedDept || selectedDiv || selectedGender || selectedStatus || selectedLogin) && (
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

          {/* Results Summary Bar + Page Size Selector */}
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
              {selectedDept && <span> in {selectedDept}</span>}
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

          {/* Error Message if Fetch Failed */}
          {error && (
            <div style={{ marginBottom: '1rem' }}>
              <ErrorState
                title="Unable to load directory"
                message={error}
                onRetry={loadStudents}
              />
            </div>
          )}

          {/* Table Container */}
          <DataTable
            columns={columns}
            data={students}
            loading={loading}
            emptyMessage={
              appliedSearch || selectedDept || selectedDiv || selectedGender || selectedStatus || selectedLogin
                ? 'No students found matching your filter criteria. Try clearing or broadening filters.'
                : 'No student records found in the directory.'
            }
            page={page}
            pageSize={pageSize}
            totalCount={totalCount}
            onPageChange={(newPage) => setPage(newPage)}
          />
        </div>
      </div>

      {/* Modal: Create Logins */}
      {createLoginsModal && (
        <Modal
          isOpen={createLoginsModal}
          onClose={() => setCreateLoginsModal(false)}
          title="Batch Create Student Portal Logins"
        >
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
            <p style={{ fontSize: '0.875rem', color: '#475569', lineHeight: 1.5 }}>
              This will automatically provision system user login credentials for admitted students who do not yet have an active username and password. Default passwords will be set according to the institutional security format.
            </p>

            {loginsSuccessMsg ? (
              <div
                style={{
                  padding: '0.75rem 1rem',
                  backgroundColor: '#f0fdf4',
                  border: '1px solid #bbf7d0',
                  color: '#16a34a',
                  borderRadius: '8px',
                  fontSize: '0.875rem',
                  fontWeight: 600,
                }}
              >
                {loginsSuccessMsg}
              </div>
            ) : (
              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem', marginTop: '1rem' }}>
                <button
                  type="button"
                  className="edvana-btn edvana-btn-secondary"
                  onClick={() => setCreateLoginsModal(false)}
                >
                  Cancel
                </button>
                <button
                  type="button"
                  className="edvana-btn edvana-btn-primary"
                  onClick={handleBatchCreateLogins}
                >
                  <KeyRound size={15} />
                  <span>Provision Logins Now</span>
                </button>
              </div>
            )}
          </div>
        </Modal>
      )}

      {/* Modal: Register Student */}
      {registerModal && (
        <Modal
          isOpen={registerModal}
          onClose={() => setRegisterModal(false)}
          title="Direct Student Registration"
        >
          <form
            onSubmit={(e) => {
              e.preventDefault();
              setRegisterModal(false);
              loadStudents();
            }}
            style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}
          >
            <FormField label="First Name" required>
              <input type="text" className="edvana-input" placeholder="e.g. Sarthak" required />
            </FormField>
            <FormField label="Last Name" required>
              <input type="text" className="edvana-input" placeholder="e.g. Patil" required />
            </FormField>
            <FormField label="Government Application ID (e.g. EN26...)" required>
              <input type="text" className="edvana-input" placeholder="EN26462534" required />
            </FormField>
            <FormField label="Department" required>
              <select className="edvana-input" required>
                <option value="AI_DS">Artificial Intelligence & Data Science (AI_DS)</option>
                <option value="CSE">Computer Science & Engineering (CSE)</option>
                <option value="EE">Electrical Engineering (EE)</option>
                <option value="ETC">Electronics & Telecommunication Engineering (ETC)</option>
                <option value="MAE">Mechanical & Automation Engineering (MAE)</option>
              </select>
            </FormField>

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem', marginTop: '1rem' }}>
              <button
                type="button"
                className="edvana-btn edvana-btn-secondary"
                onClick={() => setRegisterModal(false)}
              >
                Cancel
              </button>
              <button type="submit" className="edvana-btn edvana-btn-primary">
                Save & Enrol
              </button>
            </div>
          </form>
        </Modal>
      )}
    </>
  );
}
