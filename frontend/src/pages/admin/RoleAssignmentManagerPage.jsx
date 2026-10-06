import React, { useState, useEffect } from 'react';
import { 
  Users, Shield, Plus, Trash2, Search, Filter, 
  CheckCircle2, AlertCircle, RefreshCw, X, Building, Layers, Check
} from 'lucide-react';
import adminApi from '../../api/adminApi';
import academicApi from '../../api/academicApi';
import PageHeader from '../../components/common/PageHeader';
import DataTable from '../../components/common/DataTable';
import Badge from '../../components/common/Badge';
import Modal from '../../components/common/Modal';
import FormField from '../../components/common/FormField';
import { LoadingState, ErrorState, EmptyState } from '../../components/common/StateDisplays';

export default function RoleAssignmentManagerPage() {
  const [users, setUsers] = useState([]);
  const [roles, setRoles] = useState([]);
  const [departments, setDepartments] = useState([]);
  const [divisions, setDivisions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [successMsg, setSuccessMsg] = useState('');

  // Filters
  const [userTypeFilter, setUserTypeFilter] = useState('');
  const [searchTerm, setSearchTerm] = useState('');

  // Assign Modal
  const [showModal, setShowModal] = useState(false);
  const [formData, setFormData] = useState({
    user: '',
    role: '',
    department_id: '',
    division_id: '',
  });

  // Revoke Modal
  const [revokeTarget, setRevokeTarget] = useState(null);
  const [revokeReason, setRevokeReason] = useState('');

  // 5 Departments HOD Governance State
  const [deptHODs, setDeptHODs] = useState([]);
  const [facultyUsers, setFacultyUsers] = useState([]);
  const [hodDraft, setHodDraft] = useState({});
  const [savingHODs, setSavingHODs] = useState(false);

  const fetchData = async () => {
    setLoading(true);
    setError(null);
    try {
      const [usersRes, rolesRes, deptsRes, divsRes, hodRes] = await Promise.all([
        adminApi.getUsers({
          user_type: userTypeFilter || undefined,
          search: searchTerm || undefined,
        }),
        adminApi.getRoles(),
        academicApi.getDepartments(),
        academicApi.getDivisions(),
        adminApi.getDepartmentHODs(),
      ]);
      setUsers(usersRes.data?.results || usersRes.data || []);
      setRoles(rolesRes.data?.results || rolesRes.data || []);
      setDepartments(deptsRes.data?.results || deptsRes.data || []);
      setDivisions(divsRes.data?.results || divsRes.data || []);

      if (hodRes?.data) {
        setDeptHODs(hodRes.data.departments || []);
        setFacultyUsers(hodRes.data.faculty_users || []);
        const draft = {};
        (hodRes.data.departments || []).forEach((d) => {
          draft[d.department_id] = d.hod_user_id || '';
        });
        setHodDraft(draft);
      }
    } catch (err) {
      console.error('Failed to load user and role directory:', err);
      setError('Could not load user and role administration.');
    } finally {
      setLoading(false);
    }
  };

  const handleSaveAllHODs = async () => {
    setSavingHODs(true);
    try {
      const assignments = Object.entries(hodDraft).map(([department_id, user_id]) => ({
        department_id,
        user_id: user_id || null,
      }));
      const res = await adminApi.saveDepartmentHODs(assignments);
      setSuccessMsg(res.data?.detail || 'HOD roles updated across all 5 departments!');
      await fetchData();
      setTimeout(() => setSuccessMsg(''), 4000);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to update department HOD assignments.');
    } finally {
      setSavingHODs(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, [userTypeFilter]);

  const handleSearch = (e) => {
    e.preventDefault();
    fetchData();
  };

  const handleAssignRole = async (e) => {
    e.preventDefault();
    if (!formData.user || !formData.role) return;
    try {
      await adminApi.assignRole({
        user: formData.user,
        role: formData.role,
        department_id: formData.department_id || null,
        division_id: formData.division_id || null,
      });
      setSuccessMsg('Role assigned successfully.');
      setShowModal(false);
      setFormData({ user: '', role: '', department_id: '', division_id: '' });
      fetchData();
      setTimeout(() => setSuccessMsg(''), 3000);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to assign role.');
    }
  };

  const handleRevokeRole = async (e) => {
    e.preventDefault();
    if (!revokeTarget) return;
    try {
      await adminApi.revokeRole(revokeTarget.id, revokeReason || 'Administrative revocation');
      setSuccessMsg('Role revoked successfully.');
      setRevokeTarget(null);
      setRevokeReason('');
      fetchData();
      setTimeout(() => setSuccessMsg(''), 3000);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to revoke role.');
    }
  };

  const selectedRoleObj = roles.find(r => r.id === formData.role);

  const columns = [
    {
      header: 'Username',
      accessor: 'username',
      render: (u) => <span style={{ fontWeight: 600, color: '#0f172a' }}>{u.username}</span>,
    },
    {
      header: 'Account Type',
      render: (u) => (
        <Badge variant={u.user_type === 'SYSADMIN' ? 'danger' : u.user_type === 'FACULTY' ? 'primary' : 'neutral'}>
          {u.user_type}
        </Badge>
      ),
    },
    {
      header: 'Email Address',
      accessor: 'email',
      render: (u) => <span style={{ fontSize: '0.85rem', color: '#475569' }}>{u.email || '—'}</span>,
    },
    {
      header: 'Active Assigned Roles & Scopes',
      render: (u) => (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.4rem' }}>
          {(!u.roles || u.roles.length === 0) ? (
            <span style={{ color: '#94a3b8', fontStyle: 'italic', fontSize: '0.8rem' }}>No active roles</span>
          ) : (
            u.roles.map((r) => (
              <span
                key={r.id}
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '0.35rem',
                  padding: '0.2rem 0.6rem',
                  borderRadius: '12px',
                  fontSize: '0.75rem',
                  fontWeight: 600,
                  background: '#eff6ff',
                  color: '#1d4ed8',
                  border: '1px solid #bfdbfe',
                }}
              >
                {r.name}
                <button
                  onClick={() => setRevokeTarget(r)}
                  style={{ background: 'none', border: 'none', padding: 0, cursor: 'pointer', color: '#94a3b8', display: 'flex', alignItems: 'center' }}
                  title="Revoke Role"
                >
                  <X size={12} />
                </button>
              </span>
            ))
          )}
        </div>
      ),
    },
    {
      header: 'Status',
      align: 'center',
      render: (u) => (
        <Badge variant={u.is_active ? 'success' : 'neutral'}>
          {u.is_active ? 'Active' : 'Disabled'}
        </Badge>
      ),
    },
  ];

  return (
    <>
      <PageHeader
        breadcrumbs={[
          { label: 'Home', to: '/dashboard' },
          { label: 'Administration' },
          { label: 'Role Governance' },
        ]}
        title="Role & Scope Governance"
        subtitle="Manage user authorization scopes, Head of Department tenures, and class teacher allocations."
        actions={
          <button
            onClick={() => setShowModal(true)}
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
            <span>Assign New Role</span>
          </button>
        }
      />

      <div className="edvana-banner-overlap">
        {successMsg && (
          <div style={{ marginBottom: '1.5rem', padding: '1rem 1.25rem', background: '#f0fdf4', border: '1px solid #bbf7d0', borderRadius: '8px', color: '#166534', fontSize: '0.875rem', display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
            <CheckCircle2 size={20} style={{ flexShrink: 0 }} />
            <div>{successMsg}</div>
          </div>
        )}

        {error && (
          <div style={{ marginBottom: '1.5rem', padding: '1rem 1.25rem', background: '#fef2f2', border: '1px solid #fecaca', borderRadius: '8px', color: '#991b1b', fontSize: '0.875rem', display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
            <AlertCircle size={20} style={{ flexShrink: 0 }} />
            <div>{error}</div>
          </div>
        )}
        {/* 5-Department HOD Allocation Card */}
        <div className="edvana-card" style={{ marginBottom: '1.75rem', border: '1px solid #e2e8f0', boxShadow: '0 2px 4px rgba(0,0,0,0.04)' }}>
          <div className="edvana-card-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '1rem', borderBottom: '1px solid #f1f5f9', padding: '1.25rem 1.5rem' }}>
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.25rem' }}>
                <Building size={18} style={{ color: '#2563eb' }} />
                <h3 style={{ margin: 0, fontSize: '1.1rem', fontWeight: 700, color: '#0f172a' }}>
                  Department Head of Department (HOD) Allocations (5 Departments)
                </h3>
              </div>
              <p style={{ margin: 0, fontSize: '0.8125rem', color: '#64748b' }}>
                Assign and govern HOD roles across all 5 college departments. Sysadmin can assign or adjust all 5 roles simultaneously.
              </p>
            </div>
            <button
              type="button"
              className="edvana-btn edvana-btn-primary"
              onClick={handleSaveAllHODs}
              disabled={savingHODs || deptHODs.length === 0}
              style={{ display: 'inline-flex', alignItems: 'center', gap: '0.45rem', padding: '0.5rem 1.15rem' }}
            >
              <Check size={16} />
              <span>{savingHODs ? 'Saving Assignments...' : 'Save / Apply All 5 HOD Roles'}</span>
            </button>
          </div>

          <div className="edvana-card-body" style={{ padding: '1.25rem 1.5rem' }}>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '1rem' }}>
              {deptHODs.map((dept) => {
                const currentUserId = hodDraft[dept.department_id] ?? (dept.hod_user_id || '');
                const isChanged = (dept.hod_user_id || '') !== currentUserId;
                return (
                  <div
                    key={dept.department_id}
                    style={{
                      background: isChanged ? '#eff6ff' : '#f8fafc',
                      border: isChanged ? '1px solid #bfdbfe' : '1px solid #e2e8f0',
                      borderRadius: '8px',
                      padding: '1rem',
                      transition: 'all 0.2s ease',
                    }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '0.65rem' }}>
                      <div>
                        <span
                          style={{
                            fontWeight: 700,
                            fontSize: '0.82rem',
                            color: '#1e3a8a',
                            background: '#dbeafe',
                            padding: '0.2rem 0.5rem',
                            borderRadius: '4px',
                            display: 'inline-block',
                            marginBottom: '0.35rem',
                          }}
                        >
                          {dept.department_code}
                        </span>
                        <div style={{ fontSize: '0.875rem', fontWeight: 600, color: '#0f172a' }}>
                          {dept.department_name}
                        </div>
                      </div>
                      {dept.hod_username ? (
                        <span
                          style={{
                            fontSize: '0.72rem',
                            fontWeight: 600,
                            color: '#15803d',
                            background: '#dcfce7',
                            padding: '0.15rem 0.45rem',
                            borderRadius: '4px',
                          }}
                        >
                          Active HOD
                        </span>
                      ) : (
                        <span
                          style={{
                            fontSize: '0.72rem',
                            fontWeight: 600,
                            color: '#b45309',
                            background: '#fef3c7',
                            padding: '0.15rem 0.45rem',
                            borderRadius: '4px',
                          }}
                        >
                          Unassigned
                        </span>
                      )}
                    </div>

                    <div style={{ marginTop: '0.75rem' }}>
                      <label style={{ display: 'block', fontSize: '0.75rem', fontWeight: 600, color: '#475569', marginBottom: '0.3rem' }}>
                        Designated HOD Faculty Member:
                      </label>
                      <select
                        className="edvana-input"
                        style={{ width: '100%', fontSize: '0.8125rem', padding: '0.45rem 0.6rem' }}
                        value={currentUserId}
                        onChange={(e) => {
                          setHodDraft(prev => ({
                            ...prev,
                            [dept.department_id]: e.target.value,
                          }));
                        }}
                      >
                        <option value="">-- No HOD Assigned --</option>
                        {facultyUsers.map(f => (
                          <option key={f.id} value={f.id}>
                            {f.username} ({f.email})
                          </option>
                        ))}
                      </select>
                    </div>

                    <div style={{ marginTop: '0.5rem', fontSize: '0.75rem', color: '#64748b' }}>
                      Current: <strong>{dept.hod_display_name || dept.hod_username || 'None'}</strong>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>

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
                  placeholder="Search username or email..."
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                  className="edvana-input"
                  style={{ maxWidth: '220px' }}
                />
                <button type="submit" className="edvana-btn edvana-btn-primary" style={{ padding: '0.35rem 0.75rem', fontSize: '0.8rem' }}>
                  Search
                </button>
              </form>

              <select
                value={userTypeFilter}
                onChange={(e) => setUserTypeFilter(e.target.value)}
                className="edvana-input"
                style={{ maxWidth: '200px' }}
              >
                <option value="">All Account Types</option>
                <option value="FACULTY">Faculty</option>
                <option value="STUDENT">Student</option>
                <option value="SYSADMIN">System Administrator</option>
              </select>
            </div>
          </div>
        </div>

        {/* User Accounts & Roles Table */}
        <div className="edvana-card">
          <div className="edvana-card-header">
            <h2 className="edvana-card-title">User Accounts &amp; Privilege Registry ({users.length})</h2>
            <p className="edvana-card-description">Assigned roles and department/division scopes governing MIS module accessibility</p>
          </div>
          <div className="edvana-card-body" style={{ padding: 0 }}>
            {loading ? (
              <div style={{ padding: '2.5rem' }}>
                <LoadingState message="Loading user directory & roles..." />
              </div>
            ) : error ? (
              <div style={{ padding: '2.5rem' }}>
                <ErrorState title="Error Loading Users" message={error} onRetry={fetchData} />
              </div>
            ) : (
              <DataTable
                columns={columns}
                data={users}
                keyExtractor={(u) => u.id}
                pageSize={10}
                emptyTitle="No Users Found"
                emptyMessage="No users match the search criteria."
              />
            )}
          </div>
        </div>
      </div>

      {/* Assign Role Modal */}
      <Modal
        isOpen={showModal}
        onClose={() => setShowModal(false)}
        title="Assign Institutional Role & Scope"
        maxWidth="520px"
      >
        <form onSubmit={handleAssignRole}>
          <FormField label="Target User" required>
            <select
              required
              value={formData.user}
              onChange={(e) => setFormData({ ...formData, user: e.target.value })}
              className="edvana-input"
              style={{ width: '100%' }}
            >
              <option value="">Select User...</option>
              {users.map((u) => (
                <option key={u.id} value={u.id}>{u.username} ({u.user_type})</option>
              ))}
            </select>
          </FormField>

          <FormField label="Role to Assign" required>
            <select
              required
              value={formData.role}
              onChange={(e) => setFormData({ ...formData, role: e.target.value })}
              className="edvana-input"
              style={{ width: '100%' }}
            >
              <option value="">Select Role...</option>
              {roles.map((r) => (
                <option key={r.id} value={r.id}>{r.name} ({r.codename})</option>
              ))}
            </select>
          </FormField>

          {/* Department Scope */}
          {(selectedRoleObj?.codename === 'HOD' || selectedRoleObj?.codename === 'CLASS_TEACHER') && (
            <FormField label="Department Scope" required>
              <select
                value={formData.department_id}
                onChange={(e) => setFormData({ ...formData, department_id: e.target.value })}
                className="edvana-input"
                style={{ width: '100%' }}
              >
                <option value="">Select Department...</option>
                {departments.map((d) => (
                  <option key={d.id} value={d.id}>{d.name} ({d.code})</option>
                ))}
              </select>
            </FormField>
          )}

          {/* Division Scope */}
          {selectedRoleObj?.codename === 'CLASS_TEACHER' && (
            <FormField label="Division Scope" required>
              <select
                value={formData.division_id}
                onChange={(e) => setFormData({ ...formData, division_id: e.target.value })}
                className="edvana-input"
                style={{ width: '100%' }}
              >
                <option value="">Select Division...</option>
                {divisions.map((div) => (
                  <option key={div.id} value={div.id}>Division {div.name} (Sem {div.semester_number})</option>
                ))}
              </select>
            </FormField>
          )}

          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem', borderTop: '1px solid #e2e8f0', paddingTop: '1.25rem', marginTop: '1.5rem' }}>
            <button
              type="button"
              onClick={() => setShowModal(false)}
              className="edvana-btn edvana-btn-secondary"
            >
              Cancel
            </button>
            <button
              type="submit"
              className="edvana-btn edvana-btn-primary"
            >
              Assign Role
            </button>
          </div>
        </form>
      </Modal>

      {/* Revoke Role Modal */}
      <Modal
        isOpen={Boolean(revokeTarget)}
        onClose={() => setRevokeTarget(null)}
        title="Revoke Role Assignment"
        maxWidth="460px"
      >
        {revokeTarget && (
          <div>
            <p style={{ fontSize: '0.875rem', color: '#475569', marginBottom: '1rem', lineHeight: 1.5 }}>
              Are you sure you want to revoke the role <strong style={{ color: '#0f172a' }}>{revokeTarget.name}</strong>? This action will take effect immediately and will be logged in the permanent security audit trail.
            </p>

            <FormField label="Reason for Revocation" required>
              <textarea
                rows={2}
                required
                placeholder="e.g. Completed tenure, transfer, role re-allocation"
                value={revokeReason}
                onChange={(e) => setRevokeReason(e.target.value)}
                className="edvana-input"
                style={{ width: '100%', padding: '0.65rem' }}
              />
            </FormField>

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem', borderTop: '1px solid #e2e8f0', paddingTop: '1.25rem', marginTop: '1.5rem' }}>
              <button
                type="button"
                onClick={() => setRevokeTarget(null)}
                className="edvana-btn edvana-btn-secondary"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleRevokeRole}
                className="edvana-btn edvana-btn-danger"
              >
                Confirm Revocation
              </button>
            </div>
          </div>
        )}
      </Modal>
    </>
  );
}
