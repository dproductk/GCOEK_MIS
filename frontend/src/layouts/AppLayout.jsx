import { useState } from 'react';
import { NavLink, Outlet, useLocation } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import TopHeader from '../components/common/TopHeader';
import {
  LayoutDashboard,
  Users,
  GraduationCap,
  BookOpen,
  Building2,
  Settings,
  Shield,
  CreditCard,
  FileText,
  UserCircle,
  LogOut,
  ClipboardList,
  BarChart3,
  FolderOpen,
  UserCog,
  ChevronRight,
  Mail,
  Award,
} from 'lucide-react';

/**
 * Navigation structure matching exact institutional reference designs.
 */
const NAV_CONFIG = {
  STUDENT: {
    sections: [
      {
        label: 'STUDENT PORTAL',
        links: [
          { to: '/dashboard', label: 'Dashboard', icon: LayoutDashboard },
          { to: '/fees', label: 'Payment History', icon: CreditCard },
          { to: '/results', label: 'Results', icon: Award },
          { to: '/profile', label: 'View/Update Profile', icon: UserCircle },
        ],
      },
    ],
  },
  ADMIN_HEAD: {
    sections: [
      {
        label: 'STUDENTS & ADMISSIONS',
        links: [
          { to: '/admissions/import', label: 'Government Excel Ingestion', icon: FolderOpen },
          { to: '/students', label: 'Student Directory & Filters', icon: Users },
          { to: '/classes', label: 'Class Divisions & Batches', icon: GraduationCap },
          { to: '/admin/audit', label: 'Verification Audit Trail', icon: ClipboardList },
          { to: '/admissions/import', label: 'Services & Requests', icon: FileText },
        ],
      },
      {
        label: 'FEES & FINANCE',
        links: [
          { to: '/finance/fee-config', label: 'Fee Head Configuration', icon: Settings },
          { to: '/finance/fee-desk', label: 'Fee Desk & Payment Ledger', icon: CreditCard },
          { to: '/finance/analytics', label: 'Fee & Admission Analytics', icon: BarChart3 },
        ],
      },
      {
        label: 'ACADEMIC & PROFILE',
        links: [
          { to: '/departments', label: 'Academic Structure', icon: Building2 },
          { to: '/schemes', label: 'Schemes & Subjects', icon: BookOpen },
          { to: '/profile', label: 'Profile', icon: UserCircle },
        ],
      },
    ],
  },
  FACULTY: {
    sections: [
      {
        label: 'FACULTY PORTAL',
        links: [
          { to: '/dashboard', label: 'Dashboard', icon: LayoutDashboard },
          { to: '/students', label: 'Student Directory', icon: Users },
          { to: '/eligibility', label: 'Student Result Verification', icon: ClipboardList },
          { to: '/departments', label: 'Academic Structure', icon: Building2 },
          { to: '/schemes', label: 'Schemes & Subjects', icon: BookOpen },
          { to: '/profile', label: 'Profile', icon: UserCircle },
        ],
      },
    ],
  },
  CLASS_TEACHER: {
    sections: [
      {
        label: 'CLASS TEACHER PORTAL',
        links: [
          { to: '/dashboard', label: 'Dashboard', icon: LayoutDashboard },
          { to: '/my-class', label: 'My Class Roster', icon: GraduationCap },
          { to: '/students', label: 'Student Directory', icon: Users },
          { to: '/eligibility', label: 'Student Result Verification', icon: ClipboardList },
          { to: '/departments', label: 'Academic Structure', icon: Building2 },
          { to: '/schemes', label: 'Schemes & Subjects', icon: BookOpen },
          { to: '/profile', label: 'Profile', icon: UserCircle },
        ],
      },
    ],
  },
  HOD: {
    sections: [
      {
        label: 'DEPARTMENT GOVERNANCE',
        links: [
          { to: '/dashboard', label: 'Department Dashboard', icon: LayoutDashboard },
          { to: '/department/students', label: 'Student Directory', icon: Users },
          { to: '/department/classes', label: 'Classes & Divisions', icon: GraduationCap },
          { to: '/eligibility', label: 'Student Result Verification', icon: ClipboardList },
          { to: '/departments', label: 'Academic Structure', icon: Building2 },
          { to: '/schemes', label: 'Schemes & Subjects', icon: BookOpen },
          { to: '/profile', label: 'Profile', icon: UserCircle },
        ],
      },
    ],
  },
  ACCOUNTANT: {
    sections: [
      {
        label: 'FEES & FINANCE',
        links: [
          { to: '/dashboard', label: 'Dashboard', icon: LayoutDashboard },
          { to: '/finance/fee-desk', label: 'Candidate Ledger & Fee Desk', icon: CreditCard },
          { to: '/finance/analytics', label: 'Fee Analytics', icon: BarChart3 },
        ],
      },
      {
        label: 'STUDENTS & ACADEMIC',
        links: [
          { to: '/students', label: 'Student Directory', icon: Users },
          { to: '/departments', label: 'Academic Structure', icon: Building2 },
          { to: '/schemes', label: 'Schemes & Subjects', icon: BookOpen },
          { to: '/profile', label: 'Profile', icon: UserCircle },
        ],
      },
    ],
  },
  SYSADMIN: {
    sections: [
      {
        label: 'ADMINISTRATION',
        links: [
          { to: '/dashboard', label: 'Dashboard', icon: LayoutDashboard },
          { to: '/admin/users', label: 'Users & Roles', icon: Users },
          { to: '/admin/faculty', label: 'Faculty Directory', icon: UserCog },
          { to: '/admin/audit', label: 'Audit & Access Trail', icon: Shield },
        ],
      },
      {
        label: 'ACADEMIC CONFIGURATION',
        links: [
          { to: '/admin/departments', label: 'Academic Structure', icon: Building2 },
          { to: '/admin/schemes', label: 'Schemes & Subjects', icon: BookOpen },
          { to: '/profile', label: 'Profile', icon: UserCircle },
        ],
      },
    ],
  },
};

function getNavRole(activeRole, user) {
  // Priority order — HOD / CLASS_TEACHER users also hold a base FACULTY
  // assignment, so always pick the highest-privilege active role instead
  // of relying on array order from /auth/me/ (which is -assigned_at).
  const ROLE_PRIORITY = [
    'SYSADMIN',
    'ADMIN_HEAD',
    'HOD',
    'CLASS_TEACHER',
    'ACCOUNTANT',
    'FACULTY',
    'STUDENT',
  ];
  const activeCodenames = new Set(
    (user?.roles || []).filter((r) => r.status === 'ACTIVE').map((r) => r.codename)
  );
  if (activeRole?.codename) activeCodenames.add(activeRole.codename);
  for (const codename of ROLE_PRIORITY) {
    if (activeCodenames.has(codename) && NAV_CONFIG[codename]) return codename;
  }
  return user?.user_type || 'STUDENT';
}

export default function AppLayout() {
  const { user, logout, activeRole } = useAuth();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const location = useLocation();

  const navRole = getNavRole(activeRole, user);
  const navConfig = NAV_CONFIG[navRole] || NAV_CONFIG.STUDENT;

  // Compute initials (e.g. RK for Rohit Kumar or AH for Administrative Head)
  let initials = 'U';
  if (user?.first_name && user?.last_name) {
    initials = `${user.first_name[0]}${user.last_name[0]}`.toUpperCase();
  } else if (activeRole?.name) {
    const parts = activeRole.name.split(' ');
    initials = parts.length > 1
      ? `${parts[0][0]}${parts[1][0]}`.toUpperCase()
      : activeRole.name.slice(0, 2).toUpperCase();
  } else if (user?.username) {
    initials = user.username.slice(0, 2).toUpperCase();
  }

  const roleName = activeRole?.name || user?.user_type?.replace(/_/g, ' ') || 'User';
  
  // Format display name in uppercase as shown in reference
  const displayName = user?.first_name
    ? `${user.first_name} ${user.last_name || ''}`.trim().toUpperCase()
    : (activeRole?.name || user?.username || 'USER').toUpperCase();

  const userEmail = user?.email || (
    navRole === 'STUDENT'
      ? 'student01@university.edu'
      : `${user?.username || 'user'}@university.edu`
  );

  const handleLogout = async () => {
    await logout();
  };

  return (
    <div className="app-shell">
      {/* Institutional Top Header */}
      <TopHeader
        onToggleSidebar={() => setSidebarOpen(!sidebarOpen)}
        user={user}
        activeRole={activeRole}
      />

      <div className="app-layout">
        {/* Sidebar overlay for mobile */}
        {sidebarOpen && (
          <div
            onClick={() => setSidebarOpen(false)}
            style={{
              position: 'fixed',
              inset: 0,
              background: 'rgba(15, 23, 42, 0.45)',
              zIndex: 39,
              backdropFilter: 'blur(2px)',
            }}
          />
        )}

        {/* Sidebar matching screenshots */}
        <aside className={`app-sidebar ${sidebarOpen ? 'open' : ''}`}>
          {/* User Profile Card Section in Sidebar (Exact match to Screenshots) */}
          <div className="app-sidebar-profile">
            <div className="app-sidebar-profile-avatar">{initials}</div>
            <div className="app-sidebar-profile-name">{displayName}</div>
            <div className="app-sidebar-profile-role">{roleName}</div>
            <div className="app-sidebar-profile-id">ID: {user?.username || 'ENR2025COMP002'}</div>
            
            <div className="app-sidebar-profile-status">
              <span className="app-sidebar-profile-status-dot" />
              <span>Active</span>
            </div>

            <div className="app-sidebar-profile-email">
              <Mail size={13} style={{ opacity: 0.7 }} />
              <span>{userEmail}</span>
            </div>
          </div>

          {/* Navigation Links */}
          <nav className="app-sidebar-nav">
            {navConfig.sections.map((section, sIdx) => (
              <div className="app-sidebar-section" key={sIdx}>
                <div className="app-sidebar-section-label">{section.label}</div>
                {section.links.map((link, lIdx) => (
                  <NavLink
                    key={`${link.to}-${lIdx}`}
                    to={link.to}
                    className={({ isActive }) =>
                      `app-sidebar-link ${isActive ? 'active' : ''}`
                    }
                    onClick={() => setSidebarOpen(false)}
                  >
                    <link.icon size={18} />
                    <span style={{ flex: 1 }}>{link.label}</span>
                    {link.hasArrow && (
                      <ChevronRight size={14} style={{ opacity: 0.5 }} />
                    )}
                  </NavLink>
                ))}
              </div>
            ))}
          </nav>

          {/* Sidebar Footer with Logout Button */}
          <div className="app-sidebar-footer">
            <button
              onClick={handleLogout}
              className="app-sidebar-logout-btn"
              title="Sign out of your account"
            >
              <LogOut size={16} />
              <span>Sign Out</span>
            </button>
          </div>
        </aside>

        {/* Main Content Area */}
        <main className="app-main">
          <div className="app-page-content page-transition" key={location.pathname}>
            <Outlet />
          </div>

          {/* Institutional Footer */}
          <footer className="app-footer">
            <span className="app-footer-left">Design & Developed by Space Monkeys</span>
            <span className="app-footer-right">© 2026. All rights reserved.</span>
          </footer>
        </main>
      </div>
    </div>
  );
}
