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

  const handleSetCurrentYear = async (yearId) => {
    try {
      await apiClient.post(`/academic/years/${yearId}/set_current/`);
      fetchData();
    } catch {
      alert('Failed to update current academic year.');
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
                          onClick={() => handleSetCurrentYear(year.id)}
                          className="edvana-btn edvana-btn-secondary"
                          style={{ padding: '0.25rem 0.65rem', fontSize: '0.75rem' }}
                        >
                          Set Current
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
    </>
  );
}
