import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import facultyApi from '../../api/facultyApi';
import academicApi from '../../api/academicApi';
import { useAuth } from '../../context/AuthContext';
import PageHeader from '../../components/common/PageHeader';
import DataTable from '../../components/common/DataTable';
import Badge from '../../components/common/Badge';
import FormField from '../../components/common/FormField';
import Modal from '../../components/common/Modal';
import { LoadingState, ErrorState, EmptyState } from '../../components/common/StateDisplays';
import {
  Users,
  Search,
  Filter,
  Eye,
  RefreshCw,
  Mail,
  Building,
  Briefcase,
  Plus,
} from 'lucide-react';

export default function FacultyDirectoryPage() {
  const navigate = useNavigate();
  const { hasRole } = useAuth();
  const isSysadmin = hasRole('SYSADMIN');

  const [faculties, setFaculties] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [successMsg, setSuccessMsg] = useState('');

  // Filters
  const [departments, setDepartments] = useState([]);
  const [divisions, setDivisions] = useState([]);
  const [search, setSearch] = useState('');
  const [selectedDept, setSelectedDept] = useState('');
  const [selectedDesig, setSelectedDesig] = useState('');

  // Add Faculty (sysadmin only)
  const [showAdd, setShowAdd] = useState(false);
  const [saving, setSaving] = useState(false);
  const [fieldErrors, setFieldErrors] = useState({});
  const [form, setForm] = useState({
    employee_code: '',
    username: '',
    first_name: '',
    middle_name: '',
    last_name: '',
    official_email: '',
    mobile: '',
    department_id: '',
    designation: 'ASSISTANT_PROFESSOR',
    employment_type: 'REGULAR',
    date_of_joining: '',
    initial_role: 'FACULTY',
    division_id: '',
  });

  useEffect(() => {
    loadDepartments();
    loadFaculties();
  }, []);

  const loadDepartments = async () => {
    try {
      const res = await academicApi.getDepartments();
      setDepartments(res.data.results || res.data || []);
    } catch {
      // Non-fatal
    }
    try {
      const res = await academicApi.getDivisions();
      setDivisions(res.data.results || res.data || []);
    } catch {
      // Non-fatal — only needed for CLASS_TEACHER scope
    }
  };

  const loadFaculties = async () => {
    try {
      setLoading(true);
      setError(null);
      const params = {};
      if (search.trim()) params.search = search.trim();
      if (selectedDept) params.department_id = selectedDept;
      if (selectedDesig) params.designation = selectedDesig;

      const res = await facultyApi.getFacultyList(params);
      setFaculties(res.data.results || res.data || []);
    } catch (err) {
      setError(
        err.response?.data?.detail ||
          'Failed to load faculty directory.'
      );
    } finally {
      setLoading(false);
    }
  };

  const handleSearchSubmit = (e) => {
    e.preventDefault();
    loadFaculties();
  };

  const setFormField = (key, value) => {
    setForm((prev) => ({ ...prev, [key]: value }));
  };

  const parseApiErrors = (data) => {
    if (!data || typeof data !== 'object') return {};
    const out = {};
    Object.entries(data).forEach(([k, v]) => {
      out[k] = Array.isArray(v) ? v.join(' ') : String(v);
    });
    return out;
  };

  const handleCreateFaculty = async (e) => {
    e.preventDefault();
    setSaving(true);
    setFieldErrors({});
    setError(null);
    try {
      const payload = {
        employee_code: form.employee_code.trim(),
        username: form.username.trim() || undefined,
        first_name: form.first_name.trim(),
        middle_name: form.middle_name.trim(),
        last_name: form.last_name.trim(),
        official_email: form.official_email.trim(),
        mobile: form.mobile.trim(),
        department_id: form.department_id,
        designation: form.designation,
        employment_type: form.employment_type,
        date_of_joining: form.date_of_joining,
        initial_role: form.initial_role,
        division_id: form.division_id || null,
      };
      const res = await facultyApi.createFaculty(payload);
      const createdName = res.data?.display_name || payload.employee_code;
      const createdUser = res.data?.username || payload.employee_code;
      setShowAdd(false);
      setForm({
        employee_code: '',
        username: '',
        first_name: '',
        middle_name: '',
        last_name: '',
        official_email: '',
        mobile: '',
        department_id: '',
        designation: 'ASSISTANT_PROFESSOR',
        employment_type: 'REGULAR',
        date_of_joining: '',
        initial_role: 'FACULTY',
        division_id: '',
      });
      setSuccessMsg(
        `Faculty ${createdName} onboarded. Login: ${createdUser} / initial password = employee code (must change on first login).`
      );
      setTimeout(() => setSuccessMsg(''), 6000);
      loadFaculties();
    } catch (err) {
      const data = err.response?.data;
      const parsed = parseApiErrors(data);
      if (Object.keys(parsed).length > 0 && !data?.detail) {
        setFieldErrors(parsed);
      } else {
        setError(data?.detail || Object.values(parsed).join(' ') || 'Failed to add faculty member.');
      }
    } finally {
      setSaving(false);
    }
  };

  const getDesignationBadgeVariant = (desig) => {
    switch (desig) {
      case 'HOD':
        return 'warning';
      case 'PROFESSOR':
        return 'info';
      case 'ASSOCIATE_PROFESSOR':
        return 'primary';
      case 'ASSISTANT_PROFESSOR':
        return 'neutral';
      default:
        return 'neutral';
    }
  };

  const columns = [
    {
      header: 'Faculty Member',
      render: (f) => (
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
          <div
            style={{
              width: 36,
              height: 36,
              borderRadius: '50%',
              background: 'linear-gradient(135deg, var(--edvana-primary-light, #eff6ff), #dbeafe)',
              color: 'var(--edvana-primary, #1d4ed8)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontWeight: 700,
              fontSize: '0.875rem',
              border: '1px solid rgba(29, 78, 216, 0.15)',
              flexShrink: 0,
            }}
          >
            {f.first_name?.[0] || 'F'}
          </div>
          <div>
            <div style={{ fontWeight: 600, color: 'var(--edvana-text-main, #0f172a)' }}>
              {f.display_name}
            </div>
            <div style={{ fontSize: '0.775rem', color: 'var(--edvana-text-muted, #64748b)' }}>
              {f.employment_type_display || 'Regular'}
            </div>
          </div>
        </div>
      ),
    },
    {
      header: 'Employee Code',
      accessor: 'employee_code',
      render: (f) => (
        <span style={{ fontFamily: 'monospace', fontWeight: 600, color: '#334155' }}>
          {f.employee_code}
        </span>
      ),
    },
    {
      header: 'Department',
      render: (f) => (
        <span style={{ fontWeight: 500, color: '#1e293b' }}>
          {f.department_code || f.department_name}
        </span>
      ),
    },
    {
      header: 'Designation',
      render: (f) => (
        <Badge variant={getDesignationBadgeVariant(f.designation)}>
          {f.designation_display}
        </Badge>
      ),
    },
    {
      header: 'Official Email',
      render: (f) => (
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: '0.35rem', fontSize: '0.85rem', color: '#475569' }}>
          <Mail size={13} style={{ color: 'var(--edvana-text-muted)' }} /> {f.official_email}
        </span>
      ),
    },
    {
      header: 'Actions',
      align: 'right',
      render: (f) => (
        <button
          className="edvana-btn edvana-btn-secondary"
          style={{ padding: '0.35rem 0.75rem', fontSize: '0.8rem', display: 'inline-flex', alignItems: 'center', gap: '0.35rem' }}
          onClick={() => navigate(`/faculty/${f.id}`)}
        >
          <Eye size={14} /> View Portfolio
        </button>
      ),
    },
  ];

  return (
    <>
      <PageHeader
        breadcrumbs={[
          { label: 'Home', to: '/dashboard' },
          { label: 'Faculty & Staff' },
          { label: 'Faculty Directory' },
        ]}
        title="Faculty & Staff Directory"
        subtitle="Academic professors, department heads, and instructional staff across GCOEK autonomous faculties."
        actions={
          <div style={{ display: 'flex', gap: '0.5rem' }}>
            {isSysadmin && (
              <button
                className="edvana-btn"
                onClick={() => { setFieldErrors({}); setShowAdd(true); }}
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '0.45rem',
                  background: '#ffffff',
                  color: '#1d4ed8',
                  borderRadius: '8px',
                  fontWeight: 600,
                  fontSize: '0.8125rem',
                  padding: '0.5rem 1rem',
                }}
              >
                <Plus size={15} />
                <span>Add Faculty</span>
              </button>
            )}
            <button
              className="edvana-btn"
              onClick={loadFaculties}
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
              <span>Refresh Directory</span>
            </button>
          </div>
        }
      />

      <div className="edvana-banner-overlap">
        {successMsg && (
          <div style={{ marginBottom: '1rem', padding: '0.9rem 1.1rem', background: '#f0fdf4', border: '1px solid #bbf7d0', borderRadius: '8px', color: '#166534', fontSize: '0.875rem' }}>
            {successMsg}
          </div>
        )}
        {/* Search & Filter Toolbar */}
        <div className="edvana-card" style={{ marginBottom: '1.5rem' }}>
          <div className="edvana-card-body">
            <form onSubmit={handleSearchSubmit}>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '1rem', alignItems: 'flex-end' }}>
                {/* Search */}
                <div style={{ gridColumn: 'span 2' }}>
                  <FormField label="Search Faculty Member">
                    <div style={{ position: 'relative' }}>
                      <Search
                        size={16}
                        style={{ position: 'absolute', left: '0.75rem', top: '50%', transform: 'translateY(-50%)', color: 'var(--edvana-text-muted)' }}
                      />
                      <input
                        type="text"
                        className="edvana-input"
                        placeholder="Search by faculty name or employee code..."
                        style={{ width: '100%', paddingLeft: '2.25rem' }}
                        value={search}
                        onChange={(e) => setSearch(e.target.value)}
                      />
                    </div>
                  </FormField>
                </div>

                {/* Department */}
                <FormField label="Department">
                  <select
                    className="edvana-input"
                    style={{ width: '100%' }}
                    value={selectedDept}
                    onChange={(e) => setSelectedDept(e.target.value)}
                  >
                    <option value="">All Departments</option>
                    {departments.map((d) => (
                      <option key={d.id} value={d.id}>
                        {d.name} ({d.code})
                      </option>
                    ))}
                  </select>
                </FormField>

                {/* Designation */}
                <FormField label="Designation">
                  <select
                    className="edvana-input"
                    style={{ width: '100%' }}
                    value={selectedDesig}
                    onChange={(e) => setSelectedDesig(e.target.value)}
                  >
                    <option value="">All Designations</option>
                    <option value="HOD">Head of Department (HOD)</option>
                    <option value="PROFESSOR">Professor</option>
                    <option value="ASSOCIATE_PROFESSOR">Associate Professor</option>
                    <option value="ASSISTANT_PROFESSOR">Assistant Professor</option>
                    <option value="LECTURER">Lecturer</option>
                  </select>
                </FormField>

                {/* Submit */}
                <div>
                  <button
                    type="submit"
                    className="edvana-btn edvana-btn-primary"
                    style={{ width: '100%', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: '0.5rem', height: '38px' }}
                  >
                    <Filter size={16} /> Filter Records
                  </button>
                </div>
              </div>
            </form>
          </div>
        </div>

        {/* Directory Results Table */}
        <div className="edvana-card">
          <div className="edvana-card-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div>
              <h2 className="edvana-card-title">Teaching Staff Register ({faculties.length})</h2>
              <p className="edvana-card-description">
                Institutional roster of teaching faculty and researchers
              </p>
            </div>
          </div>
          <div className="edvana-card-body" style={{ padding: 0 }}>
            {loading ? (
              <div style={{ padding: '2rem' }}>
                <LoadingState message="Loading faculty directory..." />
              </div>
            ) : error ? (
              <div style={{ padding: '2rem' }}>
                <ErrorState title="Error Loading Directory" message={error} onRetry={loadFaculties} />
              </div>
            ) : (
              <DataTable
                columns={columns}
                data={faculties}
                keyExtractor={(f) => f.id}
                pageSize={10}
                emptyTitle="No Faculty Records Found"
                emptyMessage="No faculty records match your criteria."
              />
            )}
          </div>
        </div>
      </div>

      <Modal
        isOpen={showAdd}
        onClose={() => setShowAdd(false)}
        title="Add Faculty Member (Sysadmin)"
        size="lg"
        footer={
          <>
            <button className="edvana-btn edvana-btn-secondary" onClick={() => setShowAdd(false)} disabled={saving}>
              Cancel
            </button>
            <button className="edvana-btn edvana-btn-primary" onClick={handleCreateFaculty} disabled={saving}>
              {saving ? 'Creating...' : 'Create Faculty Login'}
            </button>
          </>
        }
      >
        <form onSubmit={handleCreateFaculty}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '1rem' }}>
            <FormField label="Employee Code" required error={fieldErrors.employee_code}>
              <input className="edvana-input" style={{ width: '100%' }} placeholder="FAC_CSE_010"
                value={form.employee_code} onChange={(e) => setFormField('employee_code', e.target.value)} />
            </FormField>
            <FormField label="Login Username" help="Defaults to employee code" error={fieldErrors.username}>
              <input className="edvana-input" style={{ width: '100%' }} placeholder="Defaults to employee code"
                value={form.username} onChange={(e) => setFormField('username', e.target.value)} />
            </FormField>
            <FormField label="First Name" required error={fieldErrors.first_name}>
              <input className="edvana-input" style={{ width: '100%' }}
                value={form.first_name} onChange={(e) => setFormField('first_name', e.target.value)} />
            </FormField>
            <FormField label="Middle Name" error={fieldErrors.middle_name}>
              <input className="edvana-input" style={{ width: '100%' }}
                value={form.middle_name} onChange={(e) => setFormField('middle_name', e.target.value)} />
            </FormField>
            <FormField label="Last Name" required error={fieldErrors.last_name}>
              <input className="edvana-input" style={{ width: '100%' }}
                value={form.last_name} onChange={(e) => setFormField('last_name', e.target.value)} />
            </FormField>
            <FormField label="Official Email" required error={fieldErrors.official_email}>
              <input type="email" className="edvana-input" style={{ width: '100%' }} placeholder="name@gceok.ac.in"
                value={form.official_email} onChange={(e) => setFormField('official_email', e.target.value)} />
            </FormField>
            <FormField label="Mobile" error={fieldErrors.mobile}>
              <input className="edvana-input" style={{ width: '100%' }} placeholder="9822XXXXXX"
                value={form.mobile} onChange={(e) => setFormField('mobile', e.target.value)} />
            </FormField>
            <FormField label="Department" required error={fieldErrors.department_id}>
              <select className="edvana-input" style={{ width: '100%' }}
                value={form.department_id} onChange={(e) => setFormField('department_id', e.target.value)}>
                <option value="">Select department</option>
                {departments.map((d) => (
                  <option key={d.id} value={d.id}>{d.name} ({d.code})</option>
                ))}
              </select>
            </FormField>
            <FormField label="Designation" required error={fieldErrors.designation}>
              <select className="edvana-input" style={{ width: '100%' }}
                value={form.designation} onChange={(e) => setFormField('designation', e.target.value)}>
                <option value="ASSISTANT_PROFESSOR">Assistant Professor</option>
                <option value="ASSOCIATE_PROFESSOR">Associate Professor</option>
                <option value="PROFESSOR">Professor</option>
                <option value="LECTURER">Lecturer</option>
                <option value="HOD">Head of Department</option>
                <option value="PRINCIPAL">Principal</option>
                <option value="ADJUNCT_PROFESSOR">Adjunct Professor</option>
              </select>
            </FormField>
            <FormField label="Employment Type" error={fieldErrors.employment_type}>
              <select className="edvana-input" style={{ width: '100%' }}
                value={form.employment_type} onChange={(e) => setFormField('employment_type', e.target.value)}>
                <option value="REGULAR">Regular / Permanent</option>
                <option value="CONTRACT">Contractual</option>
                <option value="AD_HOC">Ad-hoc</option>
                <option value="VISITING">Visiting</option>
              </select>
            </FormField>
            <FormField label="Date of Joining" required error={fieldErrors.date_of_joining}>
              <input type="date" className="edvana-input" style={{ width: '100%' }}
                value={form.date_of_joining} onChange={(e) => setFormField('date_of_joining', e.target.value)} />
            </FormField>
            <FormField label="Initial Role" required error={fieldErrors.initial_role}
              help="Operational role; base FACULTY is auto-added">
              <select className="edvana-input" style={{ width: '100%' }}
                value={form.initial_role} onChange={(e) => setFormField('initial_role', e.target.value)}>
                <option value="FACULTY">Faculty</option>
                <option value="HOD">HOD</option>
                <option value="CLASS_TEACHER">Class Teacher</option>
                <option value="ACCOUNTANT">Accountant</option>
                <option value="ADMIN_HEAD">Administrative Head</option>
              </select>
            </FormField>
            {form.initial_role === 'CLASS_TEACHER' && (
              <FormField label="Division (required for Class Teacher)" required error={fieldErrors.division_id}>
                <select className="edvana-input" style={{ width: '100%' }}
                  value={form.division_id} onChange={(e) => setFormField('division_id', e.target.value)}>
                  <option value="">Select division</option>
                  {divisions.map((d) => (
                    <option key={d.id} value={d.id}>
                      {d.name} ({d.department_code || d.department_name || ''})
                    </option>
                  ))}
                </select>
              </FormField>
            )}
          </div>
          <p style={{ marginTop: '1rem', fontSize: '0.8rem', color: '#64748b' }}>
            Login is created immediately. Initial password = employee code; faculty must change it on first login.
          </p>
        </form>
      </Modal>
    </>
  );
}
