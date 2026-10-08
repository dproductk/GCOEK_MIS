import { useState, useEffect, useCallback } from 'react';
import { useAuth } from '../../context/AuthContext';
import apiClient from '../../api/client';
import {
  Building2,
  GraduationCap,
  Calendar,
  Plus,
  CheckCircle2,
  Users,
  Layers,
  BookOpen,
  Filter,
  Check,
} from 'lucide-react';
import PageHeader from '../../components/common/PageHeader';
import DataTable from '../../components/common/DataTable';
import Badge from '../../components/common/Badge';
import Modal from '../../components/common/Modal';
import FormField from '../../components/common/FormField';
import { LoadingState, ErrorState, EmptyState } from '../../components/common/StateDisplays';

export default function AcademicStructurePage() {
  const { hasRole, user } = useAuth();
  const isSysadmin = user?.user_type === 'SYSADMIN' || hasRole('SYSADMIN');

  const [activeTab, setActiveTab] = useState('departments'); // 'departments' | 'divisions' | 'calendar'

  // Data states
  const [departments, setDepartments] = useState([]);
  const [programs, setPrograms] = useState([]);
  const [divisions, setDivisions] = useState([]);
  const [semesters, setSemesters] = useState([]);
  const [academicYears, setAcademicYears] = useState([]);
  const [currentContext, setCurrentContext] = useState(null);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Filters
  const [deptFilter, setDeptFilter] = useState('');
  const [semFilter, setSemFilter] = useState('');

  // Modals
  const [showAddDeptModal, setShowAddDeptModal] = useState(false);
  const [newDept, setNewDept] = useState({ name: '', code: '', choice_code: '', seat_capacity: 60, description: '' });
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [actionError, setActionError] = useState('');

  // Create Academic Year (Sysadmin, Academic Calendar tab)
  const [showAddYearModal, setShowAddYearModal] = useState(false);
  const [newYear, setNewYear] = useState({ code: '', name: '', start_date: '', end_date: '', set_current: false });
  const [yearFieldErrors, setYearFieldErrors] = useState({});
  const [yearActionError, setYearActionError] = useState('');
  const [isCreatingYear, setIsCreatingYear] = useState(false);
  const [settingCurrentId, setSettingCurrentId] = useState(null);
  const [yearSuccess, setYearSuccess] = useState('');

  const fetchData = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);

      const [deptRes, progRes, divRes, semRes, yearRes, contextRes] = await Promise.allSettled([
        apiClient.get('/academic/departments/'),
        apiClient.get('/academic/programs/'),
        apiClient.get('/academic/divisions/'),
        apiClient.get('/academic/semesters/'),
        apiClient.get('/academic/years/'),
        apiClient.get('/academic/contexts/current/'),
      ]);

      if (deptRes.status === 'fulfilled') setDepartments(deptRes.value.data.results || deptRes.value.data);
      if (progRes.status === 'fulfilled') setPrograms(progRes.value.data.results || progRes.value.data);
      if (divRes.status === 'fulfilled') setDivisions(divRes.value.data.results || divRes.value.data);
      if (semRes.status === 'fulfilled') setSemesters(semRes.value.data.results || semRes.value.data);
      if (yearRes.status === 'fulfilled') setAcademicYears(yearRes.value.data.results || yearRes.value.data);
      if (contextRes.status === 'fulfilled') setCurrentContext(contextRes.value.data);
    } catch (err) {
      setError('Failed to load academic structure data.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleCreateDept = async (e) => {
    e.preventDefault();
    setActionError('');
    setIsSubmitting(true);
    try {
      await apiClient.post('/academic/departments/', newDept);
      setShowAddDeptModal(false);
      setNewDept({ name: '', code: '', choice_code: '', seat_capacity: 60, description: '' });
      fetchData();
    } catch (err) {
      setActionError(err.response?.data?.detail || 'Failed to create department.');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleSetCurrentYear = async (year) => {
    const yearId = typeof year === 'object' ? year.id : year;
    const code = typeof year === 'object' ? year.code : 'this year';
    if (!window.confirm(`Set academic year ${code} as the current term? This switches the college-wide active year.`)) return;
    setSettingCurrentId(yearId);
    try {
      await apiClient.post(`/academic/years/${yearId}/set_current/`);
      await fetchData();
    } catch (err) {
      alert(err.response?.data?.detail || 'Failed to update current academic year.');
    } finally {
      setSettingCurrentId(null);
    }
  };

  const suggestNextYear = (years = academicYears) => {
    let maxStart = null;
    years.forEach((y) => {
      const m = String(y.code || '').match(/^(19|20)(\d{2})-(\d{2})$/);
      if (m) {
        const full = parseInt(`20${m[2]}`, 10);
        // Handle 1999-style codes conservatively: fall back to start_date year.
        const candidate = Number.isFinite(full) ? full : null;
        if (candidate && (maxStart === null || candidate > maxStart)) maxStart = candidate;
      } else if (y.start_date) {
        const sy = parseInt(String(y.start_date).slice(0, 4), 10);
        if (Number.isFinite(sy) && (maxStart === null || sy > maxStart)) maxStart = sy;
      }
    });
    const next = maxStart === null ? new Date().getFullYear() : maxStart + 1;
    const suffix = String((next + 1) % 100).padStart(2, '0');
    return {
      code: `${next}-${suffix}`,
      name: `Academic Year ${next}-${next + 1}`,
      start_date: `${next}-07-01`,
      end_date: `${next + 1}-06-30`,
    };
  };

  const openAddYearModal = () => {
    const suggestion = suggestNextYear();
    // Don't suggest a code that already exists (e.g. after deletions/gaps).
    const exists = new Set((academicYears || []).map((y) => String(y.code).trim()));
    let seed = suggestion;
    let guard = 0;
    while (exists.has(seed.code) && guard < 10) {
      const start = parseInt(seed.code.slice(0, 4), 10) + 1;
      const suffix = String((start + 1) % 100).padStart(2, '0');
      seed = {
        code: `${start}-${suffix}`,
        name: `Academic Year ${start}-${start + 1}`,
        start_date: `${start}-07-01`,
        end_date: `${start + 1}-06-30`,
      };
      guard += 1;
    }
    setNewYear({ ...seed, set_current: false });
    setYearFieldErrors({});
    setYearActionError('');
    setShowAddYearModal(true);
  };

  const handleYearCodeChange = (value) => {
    const code = value.toUpperCase().replace(/\s+/g, '');
    setNewYear((prev) => {
      const next = { ...prev, code };
      // Auto-fill July->June dates + display name when the code looks like YYYY-YY.
      const m = code.match(/^(19|20)\d{2}-\d{2}$/);
      if (m) {
        const startYear = parseInt(code.slice(0, 4), 10);
        const expectedSuffix = String((startYear + 1) % 100).padStart(2, '0');
        if (code.slice(5, 7) === expectedSuffix) {
          if (!prev.start_date) next.start_date = `${startYear}-07-01`;
          if (!prev.end_date) next.end_date = `${startYear + 1}-06-30`;
          if (!prev.name) next.name = `Academic Year ${startYear}-${startYear + 1}`;
        }
      }
      return next;
    });
  };

  const parseYearErrors = (data) => {
    if (!data || typeof data !== 'object') return {};
    const out = {};
    Object.entries(data).forEach(([k, v]) => {
      out[k] = Array.isArray(v) ? v.join(' ') : String(v);
    });
    return out;
  };

  const handleCreateYear = async (e) => {
    e?.preventDefault?.();
    setYearActionError('');
    setYearFieldErrors({});
    const code = (newYear.code || '').trim();
    const start_date = newYear.start_date || '';
    const end_date = newYear.end_date || '';
    const localErrors = {};
    if (!code) localErrors.code = 'Year code is required (e.g. 2027-28).';
    else if (!/^(19|20)\d{2}-\d{2}$/.test(code)) localErrors.code = 'Use format YYYY-YY, e.g. 2027-28.';
    if (!start_date) localErrors.start_date = 'Commencement date is required.';
    if (!end_date) localErrors.end_date = 'Conclusion date is required.';
    if (start_date && end_date && start_date >= end_date) localErrors.end_date = 'Conclusion must be after commencement.';
    if (Object.keys(localErrors).length) {
      setYearFieldErrors(localErrors);
      return;
    }
    setIsCreatingYear(true);
    try {
      const payload = {
        code,
        name: (newYear.name || '').trim() || `Academic Year ${code}`,
        start_date,
        end_date,
        is_current: Boolean(newYear.set_current),
      };
      const res = await apiClient.post('/academic/years/', payload);
      setShowAddYearModal(false);
      setNewYear({ code: '', name: '', start_date: '', end_date: '', set_current: false });
      setYearFieldErrors({});
      setYearSuccess(`Academic year ${res.data?.code || code} created successfully.`);
      setTimeout(() => setYearSuccess(''), 5000);
      await fetchData();
    } catch (err) {
      const data = err.response?.data;
      const parsed = parseYearErrors(data);
      const fieldKeys = ['code', 'name', 'start_date', 'end_date', 'is_current', 'non_field_errors'];
      const fields = {};
      fieldKeys.forEach((k) => { if (parsed[k]) fields[k] = parsed[k]; });
      if (Object.keys(fields).length) setYearFieldErrors(fields);
      setYearActionError(
        data?.detail
        || parsed.non_field_errors
        || Object.values(fields).join(' ')
        || 'Failed to create academic year.'
      );
    } finally {
      setIsCreatingYear(false);
    }
  };

  const filteredDivisions = divisions.filter((div) => {
    if (deptFilter && div.department !== deptFilter) return false;
    if (semFilter && String(div.semester_number) !== String(semFilter)) return false;
    return true;
  });

  const divisionColumns = [
    {
      header: 'Division',
      render: (div) => (
        <span style={{ fontWeight: 700, color: 'var(--edvana-primary)' }}>
          Division {div.name}
        </span>
      ),
    },
    {
      header: 'Department',
      render: (div) => (
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <Badge variant="neutral">{div.department_code}</Badge>
          <span style={{ fontWeight: 500 }}>{div.department_name}</span>
        </div>
      ),
    },
    {
      header: 'Semester',
      render: (div) => <span>Semester {div.semester_number}</span>,
    },
    {
      header: 'Academic Year',
      accessor: 'academic_year_code',
    },
    {
      header: 'Class Teacher',
      render: (div) => (
        div.class_teacher_name ? (
          <span style={{ fontWeight: 600, color: '#0f172a' }}>{div.class_teacher_name}</span>
        ) : (
          <span style={{ color: '#94a3b8', fontStyle: 'italic' }}>Unassigned</span>
        )
      ),
    },
    {
      header: 'Capacity',
      render: (div) => <span>{div.seat_capacity} Students</span>,
    },
    {
      header: 'Status',
      align: 'center',
      render: () => <Badge variant="success">Active</Badge>,
    },
  ];

  return (
    <>
      <PageHeader
        breadcrumbs={[
          { label: 'Home', to: '/dashboard' },
          { label: 'Academics' },
          { label: 'Academic Structure' },
        ]}
        title="Departments & Degree Programs"
        subtitle="Autonomous degree branches, curricula schemes, class divisions, and academic calendars."
        actions={
          isSysadmin && (
            <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
              {activeTab === 'calendar' ? (
                <button
                  onClick={openAddYearModal}
                  className="edvana-btn"
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
                  <Plus size={16} />
                  <span>New Academic Year</span>
                </button>
              ) : (
                <button
                  onClick={() => setShowAddDeptModal(true)}
                  className="edvana-btn"
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
                  <Plus size={16} />
                  <span>Add Department</span>
                </button>
              )}
            </div>
          )
        }
      />

      <div className="edvana-banner-overlap">
        {/* Navigation Tabs — white card so dark text stays readable over blue banner */}
        <div
          className="edvana-tabs"
          style={{
            marginBottom: '1.5rem',
            backgroundColor: '#ffffff',
            border: '1px solid #e2e8f0',
            borderRadius: '12px',
            boxShadow: '0 1px 3px rgba(0, 0, 0, 0.05)',
            padding: '0.35rem 0.5rem',
          }}
        >
          <button
            onClick={() => setActiveTab('departments')}
            className={`edvana-tab ${activeTab === 'departments' ? 'active' : ''}`}
            style={{ display: 'inline-flex', alignItems: 'center', gap: '0.5rem' }}
          >
            <Building2 size={16} />
            <span>Departments &amp; Programs</span>
            <Badge variant="primary">{departments.length}</Badge>
          </button>

          <button
            onClick={() => setActiveTab('divisions')}
            className={`edvana-tab ${activeTab === 'divisions' ? 'active' : ''}`}
            style={{ display: 'inline-flex', alignItems: 'center', gap: '0.5rem' }}
          >
            <GraduationCap size={16} />
            <span>Classes &amp; Divisions</span>
            <Badge variant="neutral">{divisions.length}</Badge>
          </button>

          <button
            onClick={() => setActiveTab('calendar')}
            className={`edvana-tab ${activeTab === 'calendar' ? 'active' : ''}`}
            style={{ display: 'inline-flex', alignItems: 'center', gap: '0.5rem' }}
          >
            <Calendar size={16} />
            <span>Academic Calendar</span>
          </button>
        </div>

        {loading ? (
          <div className="edvana-card" style={{ padding: '3rem' }}>
            <LoadingState message="Loading academic structure details..." />
          </div>
        ) : error ? (
          <div className="edvana-card" style={{ padding: '3rem' }}>
            <ErrorState title="Unable to Load Data" message={error} onRetry={fetchData} />
          </div>
        ) : activeTab === 'departments' ? (
          /* TAB 1: DEPARTMENTS & PROGRAMS */
          <div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: '1.25rem' }}>
              {departments.map((dept) => {
                const deptPrograms = programs.filter((p) => p.department === dept.id);
                return (
                  <div
                    key={dept.id}
                    className="edvana-card"
                    style={{
                      display: 'flex',
                      flexDirection: 'column',
                      justifyContent: 'space-between',
                      border: '1px solid #e2e8f0',
                    }}
                  >
                    <div className="edvana-card-body">
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '0.75rem' }}>
                        <Badge variant="primary" style={{ fontSize: '0.85rem' }}>
                          {dept.code}
                        </Badge>
                        {dept.choice_code && (
                          <span style={{ fontSize: '0.75rem', color: '#64748b' }}>
                            Choice: <strong>{dept.choice_code}</strong>
                          </span>
                        )}
                      </div>
                      <h3 style={{ margin: '0.5rem 0', fontSize: '1.15rem', fontWeight: 700, color: '#0f172a' }}>
                        {dept.name}
                      </h3>
                      <p style={{ fontSize: '0.85rem', color: '#64748b', marginBottom: '1rem', lineHeight: 1.5 }}>
                        {dept.description || 'Department of Government College of Engineering, Kolhapur.'}
                      </p>

                      <div style={{ borderTop: '1px solid #f1f5f9', paddingTop: '0.85rem' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.85rem', marginBottom: '0.5rem' }}>
                          <span style={{ color: '#64748b' }}>Intake Capacity:</span>
                          <strong style={{ color: '#0f172a' }}>{dept.seat_capacity} Seats</strong>
                        </div>

                        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.85rem' }}>
                          <span style={{ color: '#64748b' }}>Programs:</span>
                          <span style={{ fontWeight: 600 }}>{deptPrograms.length} Degree Program(s)</span>
                        </div>

                        {deptPrograms.length > 0 && (
                          <div style={{ marginTop: '0.5rem', paddingLeft: '0.65rem', borderLeft: '2px solid var(--edvana-primary-light, #bfdbfe)' }}>
                            {deptPrograms.map((p) => (
                              <div key={p.id} style={{ fontSize: '0.8rem', color: '#475569', margin: '3px 0' }}>
                                • {p.name} ({p.duration_years} Years)
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        ) : activeTab === 'divisions' ? (
          /* TAB 2: DIVISIONS & COHORTS */
          <div className="edvana-card">
            <div className="edvana-card-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '1rem' }}>
              <div>
                <h2 className="edvana-card-title">Division &amp; Class Cohorts ({filteredDivisions.length})</h2>
                <p className="edvana-card-description">
                  Student cohorts organized by department and semester with designated class teachers
                </p>
              </div>

              {/* Filters */}
              <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', flexWrap: 'wrap' }}>
                <Filter size={16} style={{ color: '#94a3b8' }} />
                <select
                  className="edvana-input"
                  style={{ maxWidth: '200px' }}
                  value={deptFilter}
                  onChange={(e) => setDeptFilter(e.target.value)}
                >
                  <option value="">All Departments</option>
                  {departments.map((d) => (
                    <option key={d.id} value={d.id}>
                      {d.code} - {d.name}
                    </option>
                  ))}
                </select>

                <select
                  className="edvana-input"
                  style={{ maxWidth: '180px' }}
                  value={semFilter}
                  onChange={(e) => setSemFilter(e.target.value)}
                >
                  <option value="">All Semesters</option>
                  {semesters.map((s) => (
                    <option key={s.id} value={s.number}>
                      {s.name} (Year {s.year_level})
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <div className="edvana-card-body" style={{ padding: 0 }}>
              <DataTable
                columns={divisionColumns}
                data={filteredDivisions}
                keyExtractor={(div) => div.id}
                pageSize={10}
                emptyTitle="No Divisions Found"
                emptyMessage="No class divisions match the selected criteria."
              />
            </div>
          </div>
        ) : (
          /* TAB 3: ACADEMIC CALENDAR & TERMS */
          <div>
            {yearSuccess && (
              <div style={{ marginBottom: '1rem', padding: '0.9rem 1.1rem', background: '#f0fdf4', border: '1px solid #bbf7d0', borderRadius: '8px', color: '#166534', fontSize: '0.875rem', display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                <CheckCircle2 size={18} />{yearSuccess}
              </div>
            )}
            <div className="edvana-card" style={{ marginBottom: '1.25rem' }}>
              <div className="edvana-card-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '1rem' }}>
                <div>
                  <h2 className="edvana-card-title">Academic Years ({academicYears.length})</h2>
                  <p className="edvana-card-description">
                    College-wide academic calendar. Only one year is current at a time — new admissions, fees and contexts follow it.
                  </p>
                </div>
                {isSysadmin && (
                  <button
                    onClick={openAddYearModal}
                    className="edvana-btn edvana-btn-primary"
                    style={{ display: 'inline-flex', alignItems: 'center', gap: '0.45rem', fontSize: '0.8125rem', padding: '0.5rem 1rem' }}
                  >
                    <Plus size={15} />
                    <span>New Academic Year</span>
                  </button>
                )}
              </div>
            </div>
            {academicYears.length === 0 ? (
              <div className="edvana-card" style={{ padding: '3rem' }}>
                <EmptyState
                  title="No Academic Years Yet"
                  message={isSysadmin ? 'Create the first academic year (e.g. 2027-28, 1 July – 30 June) to start the calendar.' : 'No academic years have been configured yet.'}
                />
                {isSysadmin && (
                  <div style={{ display: 'flex', justifyContent: 'center', marginTop: '1rem' }}>
                    <button onClick={openAddYearModal} className="edvana-btn edvana-btn-primary">
                      <Plus size={15} /> Create Academic Year
                    </button>
                  </div>
                )}
              </div>
            ) : (
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: '1.25rem' }}>
                {academicYears.map((year) => (
                  <div
                    key={year.id}
                    className="edvana-card"
                    style={{
                      border: year.is_current ? '2px solid var(--edvana-primary, #1d4ed8)' : '1px solid #e2e8f0',
                      background: year.is_current ? '#f8fafc' : '#fff',
                    }}
                  >
                    <div className="edvana-card-body">
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem' }}>
                        <h3 style={{ margin: 0, fontSize: '1.15rem', fontWeight: 700, color: '#0f172a' }}>{year.code}</h3>
                        {year.is_current ? (
                          <Badge variant="success">Current Term</Badge>
                        ) : isSysadmin ? (
                          <button
                            onClick={() => handleSetCurrentYear(year)}
                            disabled={settingCurrentId === year.id}
                            className="edvana-btn edvana-btn-secondary"
                            style={{ padding: '0.25rem 0.65rem', fontSize: '0.75rem' }}
                          >
                            {settingCurrentId === year.id ? 'Setting…' : 'Set Current'}
                          </button>
                        ) : null}
                      </div>

                      <p style={{ fontSize: '0.9rem', color: '#475569', margin: '4px 0 1rem', fontWeight: 500 }}>
                        {year.name}
                      </p>

                      <div style={{ fontSize: '0.825rem', color: '#64748b', borderTop: '1px solid #f1f5f9', paddingTop: '0.75rem' }}>
                        <div>
                          <strong>Commencement:</strong> {year.start_date}
                        </div>
                        <div style={{ marginTop: '0.25rem' }}>
                          <strong>Conclusion:</strong> {year.end_date}
                        </div>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Add Department Modal (Sysadmin) */}
      <Modal
        isOpen={showAddDeptModal}
        onClose={() => setShowAddDeptModal(false)}
        title="Add New Academic Department"
        maxWidth="500px"
      >
        {actionError && (
          <div style={{ marginBottom: '1rem', padding: '0.75rem 1rem', background: '#fef2f2', border: '1px solid #fecaca', borderRadius: '6px', color: '#991b1b', fontSize: '0.85rem' }}>
            {actionError}
          </div>
        )}

        <form onSubmit={handleCreateDept}>
          <FormField label="Department Name" required>
            <input
              type="text"
              className="edvana-input"
              required
              placeholder="e.g. Chemical Engineering"
              value={newDept.name}
              onChange={(e) => setNewDept({ ...newDept, name: e.target.value })}
              style={{ width: '100%' }}
            />
          </FormField>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
            <FormField label="Code" required>
              <input
                type="text"
                className="edvana-input"
                required
                placeholder="e.g. CHEM"
                value={newDept.code}
                onChange={(e) => setNewDept({ ...newDept, code: e.target.value.toUpperCase() })}
                style={{ width: '100%', fontFamily: 'monospace' }}
              />
            </FormField>

            <FormField label="Choice Code">
              <input
                type="text"
                className="edvana-input"
                placeholder="DTE choice code"
                value={newDept.choice_code}
                onChange={(e) => setNewDept({ ...newDept, choice_code: e.target.value })}
                style={{ width: '100%' }}
              />
            </FormField>
          </div>

          <FormField label="Intake Capacity">
            <input
              type="number"
              className="edvana-input"
              min="1"
              value={newDept.seat_capacity}
              onChange={(e) => setNewDept({ ...newDept, seat_capacity: parseInt(e.target.value) || 60 })}
              style={{ width: '100%' }}
            />
          </FormField>

          <FormField label="Description (Optional)">
            <textarea
              className="edvana-input"
              rows={3}
              value={newDept.description}
              onChange={(e) => setNewDept({ ...newDept, description: e.target.value })}
              style={{ width: '100%', padding: '0.65rem' }}
            />
          </FormField>

          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem', borderTop: '1px solid #e2e8f0', paddingTop: '1.25rem', marginTop: '1.5rem' }}>
            <button
              type="button"
              onClick={() => setShowAddDeptModal(false)}
              className="edvana-btn edvana-btn-secondary"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isSubmitting}
              className="edvana-btn edvana-btn-primary"
            >
              {isSubmitting ? 'Creating...' : 'Create Department'}
            </button>
          </div>
        </form>
      </Modal>

      {/* Create Academic Year Modal (Sysadmin) */}
      <Modal
        isOpen={showAddYearModal}
        onClose={() => { if (!isCreatingYear) setShowAddYearModal(false); }}
        title="Create New Academic Year"
        maxWidth="560px"
      >
        {(yearActionError || yearFieldErrors.non_field_errors) && (
          <div style={{ marginBottom: '1rem', padding: '0.75rem 1rem', background: '#fef2f2', border: '1px solid #fecaca', borderRadius: '6px', color: '#991b1b', fontSize: '0.85rem' }}>
            {yearFieldErrors.non_field_errors || yearActionError}
          </div>
        )}

        <form onSubmit={handleCreateYear}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
            <FormField label="Year Code" required error={yearFieldErrors.code} help="e.g. 2027-28">
              <input
                type="text"
                className="edvana-input"
                required
                placeholder="2027-28"
                value={newYear.code}
                onChange={(e) => handleYearCodeChange(e.target.value)}
                style={{ width: '100%', fontFamily: 'monospace' }}
              />
            </FormField>

            <FormField label="Display Name" error={yearFieldErrors.name} help="Auto-filled if left blank">
              <input
                type="text"
                className="edvana-input"
                placeholder="Academic Year 2027-2028"
                value={newYear.name}
                onChange={(e) => setNewYear({ ...newYear, name: e.target.value })}
                style={{ width: '100%' }}
              />
            </FormField>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', marginTop: '1rem' }}>
            <FormField label="Commencement" required error={yearFieldErrors.start_date}>
              <input
                type="date"
                className="edvana-input"
                required
                value={newYear.start_date}
                onChange={(e) => setNewYear({ ...newYear, start_date: e.target.value })}
                style={{ width: '100%' }}
              />
            </FormField>

            <FormField label="Conclusion" required error={yearFieldErrors.end_date}>
              <input
                type="date"
                className="edvana-input"
                required
                value={newYear.end_date}
                onChange={(e) => setNewYear({ ...newYear, end_date: e.target.value })}
                style={{ width: '100%' }}
              />
            </FormField>
          </div>

          <label style={{ display: 'flex', alignItems: 'flex-start', gap: '0.6rem', marginTop: '1rem', fontSize: '0.85rem', color: '#334155', cursor: 'pointer' }}>
            <input
              type="checkbox"
              checked={Boolean(newYear.set_current)}
              onChange={(e) => setNewYear({ ...newYear, set_current: e.target.checked })}
              style={{ marginTop: '0.2rem' }}
            />
            <span>
              <strong>Set as current academic year immediately.</strong>
              <br />
              <span style={{ color: '#64748b' }}>
                Switches the college-wide active year on creation. Leave unchecked to create as a future/planning year and switch later with “Set Current”.
              </span>
            </span>
          </label>
          {yearFieldErrors.is_current && (
            <div style={{ marginTop: '0.5rem', fontSize: '0.8rem', color: '#b91c1c' }}>{yearFieldErrors.is_current}</div>
          )}

          <p style={{ marginTop: '1rem', fontSize: '0.78rem', color: '#64748b', background: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: '6px', padding: '0.6rem 0.8rem' }}>
            Academic years run July → June (e.g. 2027-07-01 to 2028-06-30) and must not overlap. Codes must be consecutive (2027-28, not 2027-29).
          </p>

          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem', borderTop: '1px solid #e2e8f0', paddingTop: '1.25rem', marginTop: '1.25rem' }}>
            <button
              type="button"
              onClick={() => setShowAddYearModal(false)}
              disabled={isCreatingYear}
              className="edvana-btn edvana-btn-secondary"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isCreatingYear}
              className="edvana-btn edvana-btn-primary"
            >
              {isCreatingYear ? 'Creating...' : 'Create Academic Year'}
            </button>
          </div>
        </form>
      </Modal>
    </>
  );
}
