import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import facultyApi from '../../api/facultyApi';
import { LoadingState } from '../../components/common/StateDisplays';
import PageHeader from '../../components/common/PageHeader';
import Badge from '../../components/common/Badge';
import DataTable from '../../components/common/DataTable';
import CollegeIllustration from '../../components/common/CollegeIllustration';
import {
  User,
  BookOpen,
  Award,
  Users,
  Clock,
  ArrowRight,
  ClipboardList,
  GraduationCap,
  Building2,
  FileCheck,
} from 'lucide-react';

export default function FacultyDashboardPage() {
  const { user, activeRole } = useAuth();
  const navigate = useNavigate();

  const [profile, setProfile] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadMyProfile();
  }, []);

  const loadMyProfile = async () => {
    try {
      setLoading(true);
      const res = await facultyApi.getMyProfile();
      setProfile(res.data);
    } catch {
      // Fallback gracefully
    } finally {
      setLoading(false);
    }
  };

  const assignments = profile?.teaching_assignments || [];
  const isClassTeacher = activeRole?.codename === 'CLASS_TEACHER';
  const displayName = profile?.display_name || user?.username || 'Faculty Member';

  if (loading) {
    return (
      <div style={{ padding: '2rem' }}>
        <LoadingState message="Loading faculty portal dashboard..." />
      </div>
    );
  }

  const assignmentColumns = [
    {
      header: 'COURSE CODE',
      accessor: 'subject_code',
      render: (row) => (
        <span style={{ fontFamily: 'var(--edvana-font-mono)', fontWeight: 700, color: '#2563eb' }}>
          {row.subject_code}
        </span>
      ),
    },
    {
      header: 'SUBJECT TITLE',
      accessor: 'subject_name',
      render: (row) => <span style={{ fontWeight: 600, color: '#0f172a' }}>{row.subject_name}</span>,
    },
    {
      header: 'SEMESTER',
      accessor: 'semester_number',
      render: (row) => <span>Semester {row.semester_number}</span>,
    },
    {
      header: 'ROLE / RESPONSIBILITY',
      accessor: 'role_display',
      render: (row) => (
        <Badge variant={row.role_display?.includes('Primary') ? 'brand' : 'neutral'}>
          {row.role_display}
        </Badge>
      ),
    },
    {
      header: 'ACTION',
      align: 'right',
      render: () => (
        <button
          className="edvana-btn edvana-btn-outline edvana-btn-sm"
          onClick={() => navigate('/students')}
          style={{ borderRadius: '9999px', fontSize: '0.75rem', padding: '0.25rem 0.75rem' }}
        >
          <span>Course Roster &gt;</span>
        </button>
      ),
    },
  ];

  const fallbackAssignments = [
    {
      id: 1,
      subject_code: 'CS201',
      subject_name: 'Data Structures & Algorithms',
      semester_number: 3,
      role_display: 'Primary Instructor',
    },
    {
      id: 2,
      subject_code: 'CS202',
      subject_name: 'Database Management Systems',
      semester_number: 4,
      role_display: 'Course Co-incharge',
    },
  ];

  return (
    <>
      <PageHeader
        breadcrumbs={[
          { label: 'Home', to: '/dashboard' },
          { label: 'Faculty Portal' },
          { label: 'Dashboard' },
        ]}
        title={`Welcome, ${displayName}!`}
        subtitle={`${profile?.designation_display || 'Faculty'} — Department of ${profile?.department_name || 'Computer Science & Engineering'}`}
      />

      <div className="edvana-banner-overlap">
        {/* Welcome Hero Card */}
        <div className="edvana-card edvana-welcome-hero-card">
          <div className="edvana-welcome-grid">
            <div className="edvana-welcome-left">
              <h2 className="edvana-welcome-title">
                Faculty Academic & Course Console
              </h2>
              <p className="edvana-welcome-subtitle">
                Centralized portal for classroom teaching allocations, student advisement, and autonomous continuous assessment.
              </p>

              <ul className="edvana-welcome-checklist">
                <li>
                  <span className="checklist-bullet">•</span>
                  <span>Manage assigned course syllabus, continuous internal evaluation, and attendance</span>
                </li>
                <li>
                  <span className="checklist-bullet">•</span>
                  <span>Inspect departmental student directory and student profile bio-data</span>
                </li>
                <li>
                  <span className="checklist-bullet">•</span>
                  <span>Verify autonomous exam eligibility and term promotion status</span>
                </li>
                <li>
                  <span className="checklist-bullet">•</span>
                  <span>Update faculty portfolio, research publications, and professional credentials</span>
                </li>
              </ul>

              <div style={{ marginTop: '1.75rem', display: 'flex', gap: '0.75rem', flexWrap: 'wrap' }}>
                <button
                  className="edvana-btn edvana-btn-primary"
                  onClick={() => navigate('/students')}
                  style={{
                    padding: '0.6875rem 1.35rem',
                    fontSize: '0.875rem',
                    fontWeight: 600,
                    borderRadius: '8px',
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '0.5rem',
                  }}
                >
                  <span>Student Directory</span>
                  <ArrowRight size={16} />
                </button>
                <button
                  className="edvana-btn edvana-btn-secondary"
                  onClick={() => navigate('/profile')}
                  style={{
                    padding: '0.6875rem 1.25rem',
                    fontSize: '0.875rem',
                    fontWeight: 600,
                    borderRadius: '8px',
                  }}
                >
                  <span>My Profile</span>
                </button>
              </div>
            </div>

            <div className="edvana-welcome-right">
              <CollegeIllustration quote='"Excellence in Engineering Education"' />
            </div>
          </div>
        </div>

        {/* Workload Table */}
        <div className="edvana-card" style={{ padding: '1.5rem 2rem' }}>
          <div style={{ marginBottom: '1.25rem' }}>
            <div style={{ fontSize: '0.8125rem', fontWeight: 600, color: '#2563eb', marginBottom: '0.25rem' }}>
              Academic Load / Curriculum Allocation
            </div>
            <h2 style={{ fontSize: '1.35rem', fontWeight: 700, color: '#0f172a', margin: 0 }}>
              Current Teaching Allocations
            </h2>
            <p style={{ fontSize: '0.8125rem', color: '#64748b', margin: '0.25rem 0 0 0' }}>
              Autonomous Term Summer 2026 course schedule and instructor roles.
            </p>
          </div>

          <DataTable
            columns={assignmentColumns}
            data={assignments.length > 0 ? assignments : fallbackAssignments}
            keyField="id"
          />
        </div>
      </div>
    </>
  );
}
