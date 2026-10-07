/**
 * App — root application component.
 *
 * Sets up:
 * - AuthProvider for authentication context
 * - Routes: login (public) + protected app layout with nested routes
 */
import { Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider } from './context/AuthContext';
import ProtectedRoute from './routes/ProtectedRoute';
import AppLayout from './layouts/AppLayout';
import LoginPage from './pages/LoginPage';
import ChangePasswordPage from './pages/ChangePasswordPage';
import DashboardPage from './pages/DashboardPage';
import AcademicStructurePage from './pages/academic/AcademicStructurePage';
import StudentProfilePage from './pages/student/StudentProfilePage';
import StudentDirectoryPage from './pages/student/StudentDirectoryPage';
import FacultyProfilePage from './pages/faculty/FacultyProfilePage';
import FacultyDirectoryPage from './pages/faculty/FacultyDirectoryPage';
import ProfileDispatcher from './pages/ProfileDispatcher';
import AdmissionImportPage from './pages/admissions/AdmissionImportPage';
import ResultHistoryPage from './pages/results/ResultHistoryPage';
import EligibilityVerificationPage from './pages/results/EligibilityVerificationPage';
import MyClassPage from './pages/class_teacher/MyClassPage';
import HODDivisionsBatchesPage from './pages/hod/HODDivisionsBatchesPage';
import FeeHeadConfigPage from './pages/finance/FeeHeadConfigPage';
import FeeDeskPage from './pages/finance/FeeDeskPage';
import CandidateFeeSetPage from './pages/finance/CandidateFeeSetPage';
import FeeAnalyticsPage from './pages/finance/FeeAnalyticsPage';
import StudentFeeReceiptPage from './pages/finance/StudentFeeReceiptPage';
import PaymentStatusPage from './pages/finance/PaymentStatusPage';

import AdminHeadDashboardPage from './pages/admin_head/AdminHeadDashboardPage';
import SchemesSubjectsPage from './pages/curriculum/SchemesSubjectsPage';
import AuditLogViewerPage from './pages/admin/AuditLogViewerPage';
import RoleAssignmentManagerPage from './pages/admin/RoleAssignmentManagerPage';

export default function App() {
  return (
    <AuthProvider>
      <Routes>
        {/* Public routes */}
        <Route path="/login" element={<LoginPage />} />

        {/* First-login or user password change route */}
        <Route
          path="/change-password"
          element={
            <ProtectedRoute>
              <ChangePasswordPage />
            </ProtectedRoute>
          }
        />

        {/* Protected routes — wrapped in AppLayout */}
        <Route
          element={
            <ProtectedRoute>
              <AppLayout />
            </ProtectedRoute>
          }
        >
          <Route path="/dashboard" element={<DashboardPage />} />
          <Route path="/profile" element={<ProfileDispatcher />} />
          {/* Per-profile password pages — same ChangePasswordPage (same UX as
              first-login) for every role. /profile/security is canonical;
              /account/security kept as a backward-compatible alias. */}
          <Route path="/profile/security" element={<ChangePasswordPage />} />
          <Route path="/profile/password" element={<Navigate to="/profile/security" replace />} />
          <Route path="/account/security" element={<ChangePasswordPage />} />
          <Route path="/account/password" element={<Navigate to="/account/security" replace />} />
          
          {/* Students */}
          <Route path="/students" element={<StudentDirectoryPage />} />
          <Route path="/students/:id" element={<StudentProfilePage />} />
          <Route path="/department/students" element={<StudentDirectoryPage />} />
          
          {/* Faculty */}
          <Route path="/faculty" element={<FacultyDirectoryPage />} />
          <Route path="/faculty/:id" element={<FacultyProfilePage />} />
          <Route path="/admin/faculty" element={<FacultyDirectoryPage />} />
          
          {/* Admissions */}
          <Route path="/admissions/import" element={<AdmissionImportPage />} />
          
          {/* Results & Eligibility */}
          <Route path="/results" element={<ResultHistoryPage />} />
          <Route path="/eligibility" element={<EligibilityVerificationPage />} />
          
          {/* Classes & Divisions — rebuilt flow (pending imports, create
              class, merge DSE, subject teachers) lives in
              HODDivisionsBatchesPage. Department Dashboard (HOD home)
              keeps stats + intake overview. */}
          <Route path="/my-class" element={<MyClassPage />} />
          <Route path="/department/classes" element={<HODDivisionsBatchesPage />} />
          <Route path="/department/divisions" element={<Navigate to="/department/classes" replace />} />
          <Route path="/classes" element={<Navigate to="/department/classes" replace />} />
          <Route path="/divisions" element={<Navigate to="/department/classes" replace />} />
          
          {/* Finance & Fee Desk */}
          <Route path="/finance/fee-config" element={<FeeHeadConfigPage />} />
          <Route path="/finance/fee-desk" element={<FeeDeskPage />} />
          <Route path="/finance/candidate-ledger" element={<FeeDeskPage />} />
          <Route path="/finance/set-fee/:studentId" element={<CandidateFeeSetPage />} />
          <Route path="/finance/fee-desk/set-fee/:studentId" element={<CandidateFeeSetPage />} />
          <Route path="/finance/analytics" element={<FeeAnalyticsPage />} />
          <Route path="/fees" element={<StudentFeeReceiptPage />} />
          <Route path="/my-fees" element={<StudentFeeReceiptPage />} />
          <Route path="/fees/payment/:attemptId" element={<PaymentStatusPage />} />
          <Route path="/fees/payment/mock-checkout" element={<PaymentStatusPage />} />
          <Route path="/fees/payment/error" element={<PaymentStatusPage />} />


          {/* Admin Head Executive Dashboard */}
          <Route path="/admin-head" element={<AdminHeadDashboardPage />} />
          <Route path="/admin-head/dashboard" element={<AdminHeadDashboardPage />} />

          {/* Sysadmin Security & Governance */}
          <Route path="/admin/audit" element={<AuditLogViewerPage />} />
          <Route path="/admin/audit-logs" element={<AuditLogViewerPage />} />
          <Route path="/admin/users" element={<RoleAssignmentManagerPage />} />
          <Route path="/admin/roles" element={<RoleAssignmentManagerPage />} />
          
          {/* Academic Structure */}
          <Route path="/departments" element={<AcademicStructurePage />} />
          <Route path="/schemes" element={<SchemesSubjectsPage />} />
          <Route path="/admin/departments" element={<AcademicStructurePage />} />
          <Route path="/admin/schemes" element={<SchemesSubjectsPage />} />
          <Route path="/admin/academic-year" element={<AcademicStructurePage />} />

          {/* Redirect root to dashboard */}
          <Route path="/" element={<Navigate to="/dashboard" replace />} />

          {/* Catch-all for unimplemented routes */}
          <Route
            path="*"
            element={
              <div style={{ padding: '2rem' }}>
                <div className="edvana-banner">
                  <div className="edvana-banner-breadcrumb">
                    <span>Home</span>
                    <span>›</span>
                    <span>Page</span>
                  </div>
                  <h1 className="edvana-banner-title">Coming Soon</h1>
                </div>
                <div className="edvana-banner-overlap">
                  <div className="edvana-card">
                    <div className="edvana-card-body">
                      <div className="state-container">
                        <h3 className="state-title">Under Construction</h3>
                        <p className="state-message">
                          This page is being built. Check back after the relevant
                          phase is completed.
                        </p>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            }
          />
        </Route>
      </Routes>
    </AuthProvider>
  );
}
