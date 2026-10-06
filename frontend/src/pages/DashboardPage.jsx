/**
 * Dashboard Page — role-based dispatcher.
 */
import { useAuth } from '../context/AuthContext';
import { LayoutDashboard } from 'lucide-react';
import StudentDashboardPage from './student/StudentDashboardPage';
import FacultyDashboardPage from './faculty/FacultyDashboardPage';
import HODDashboardPage from './hod/HODDashboardPage';
import AdminHeadDashboardPage from './admin_head/AdminHeadDashboardPage';
import PageHeader from '../components/common/PageHeader';

export default function DashboardPage() {
  const { user, activeRole, hasRole } = useAuth();

  if (activeRole?.codename === 'STUDENT' || user?.user_type === 'STUDENT') {
    return <StudentDashboardPage />;
  }

  // HOD users also hold a base FACULTY assignment — check HOD first via
  // hasRole (order-independent) so they always get the HOD dashboard.
  if (activeRole?.codename === 'HOD' || hasRole?.('HOD')) {
    return <HODDashboardPage />;
  }

  if (
    activeRole?.codename === 'FACULTY' ||
    activeRole?.codename === 'CLASS_TEACHER' ||
    user?.user_type === 'FACULTY'
  ) {
    return <FacultyDashboardPage />;
  }

  if (
    activeRole?.codename === 'ADMIN_HEAD' ||
    activeRole?.codename === 'ACCOUNTANT' ||
    activeRole?.codename === 'SYSADMIN' ||
    user?.user_type === 'ADMIN'
  ) {
    return <AdminHeadDashboardPage />;
  }

  const roleName = activeRole?.name || user?.user_type || 'User';

  return (
    <>
      <PageHeader
        breadcrumbs={[{ label: 'Home', to: '/dashboard' }, { label: 'Dashboard' }]}
        title="Institutional Dashboard"
        subtitle={`Logged in as ${roleName}`}
      />

      <div className="edvana-banner-overlap">
        <div className="edvana-card">
          <div className="edvana-card-header">
            <div>
              <h2 className="edvana-card-title">Welcome, {user?.username || 'User'}</h2>
              <p className="edvana-card-description">Active institutional role: {roleName}</p>
            </div>
          </div>
          <div className="edvana-card-body">
            <div className="state-container">
              <LayoutDashboard
                size={48}
                style={{ color: 'var(--edvana-brand)', marginBottom: '1rem' }}
              />
              <h3 className="state-title">System Foundation Active</h3>
              <p className="state-message">
                The GCOEK MIS portal is active. Select any section from the navigation sidebar to manage academic records, student directories, or financial ledgers.
              </p>
            </div>
          </div>
        </div>
      </div>
    </>
  );
}

