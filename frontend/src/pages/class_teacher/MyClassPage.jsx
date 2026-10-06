import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import studentApi from '../../api/studentApi';
import resultsApi from '../../api/resultsApi';
import PageHeader from '../../components/common/PageHeader';
import StatCard from '../../components/common/StatCard';
import DataTable from '../../components/common/DataTable';
import Badge from '../../components/common/Badge';
import { LoadingState, ErrorState } from '../../components/common/StateDisplays';
import {
  GraduationCap,
  Users,
  CheckCircle2,
  AlertTriangle,
  FileCheck,
  Search,
  Eye,
  RefreshCw,
  ClipboardList,
  Percent,
  ChevronRight,
} from 'lucide-react';

export default function MyClassPage() {
  const { user, activeRole } = useAuth();
  const navigate = useNavigate();

  const [students, setStudents] = useState([]);
  const [eligibilities, setEligibilities] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [search, setSearch] = useState('');

  useEffect(() => {
    loadClassData();
  }, []);

  const loadClassData = async () => {
    try {
      setLoading(true);
      setError(null);
      const [stuRes, eligRes] = await Promise.all([
        studentApi.getStudents(),
        resultsApi.getEligibilities(),
      ]);
      setStudents(stuRes.data?.results || stuRes.data || []);
      setEligibilities(eligRes.data?.results || eligRes.data || []);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to load assigned class roster.');
    } finally {
      setLoading(false);
    }
  };

  const eligMap = new Map();
  eligibilities.forEach((e) => {
    eligMap.set(e.student_id, e);
  });

  const filteredStudents = students.filter((s) => {
    if (!search.trim()) return true;
    const term = search.toLowerCase();
    return (
      (s.display_name || `${s.first_name} ${s.last_name}`).toLowerCase().includes(term) ||
      (s.enrollment_no || '').toLowerCase().includes(term) ||
      (s.application_id || '').toLowerCase().includes(term)
    );
  });

  const eligibleCount = eligibilities.filter((e) => e.calculated_status === 'ELIGIBLE').length;

  const columns = [
    {
      header: 'S.N.',
      width: '50px',
      align: 'center',
      render: (st, idx) => (
        <span style={{ fontSize: '0.8125rem', color: '#64748b', fontWeight: 500 }}>
          {idx + 1}
        </span>
      ),
    },
    {
      header: 'CANDIDATE',
      render: (st) => (
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
          <div
            style={{
              width: 34,
              height: 34,
              borderRadius: '50%',
              backgroundColor: '#eff6ff',
              color: '#1d4ed8',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontWeight: 700,
              fontSize: '0.8125rem',
              border: '1px solid #bfdbfe',
              flexShrink: 0,
            }}
          >
            {st.first_name?.[0] || 'S'}
          </div>
          <div>
            <div style={{ fontWeight: 700, color: '#0f172a', fontSize: '0.8125rem' }}>
              {(st.display_name || `${st.first_name} ${st.last_name}`).toUpperCase()}
            </div>
            <div style={{ fontSize: '0.6875rem', color: '#64748b' }}>
              Division {st.division_name || 'A'} • Semester {st.semester_number || '1'}
            </div>
          </div>
        </div>
      ),
    },
    {
      header: 'ENROLL NO.',
      render: (st) => (
        <span style={{ fontFamily: 'var(--edvana-font-mono)', fontWeight: 600, color: '#2563eb', fontSize: '0.8125rem' }}>
          {st.enrollment_no || st.application_id || '—'}
        </span>
      ),
    },
    {
      header: 'DEPARTMENT',
      render: (st) => <span style={{ fontWeight: 500, fontSize: '0.8125rem' }}>{st.department_code || 'CSE'}</span>,
    },
    {
      header: 'ATTENDANCE',
      render: () => (
        <span style={{ fontWeight: 700, color: '#16a34a', fontSize: '0.8125rem' }}>88.4%</span>
      ),
    },
    {
      header: 'BACKLOGS',
      render: (st) => {
        const elig = eligMap.get(st.id);
        const count = elig ? elig.active_backlog_count : 0;
        return (
          <span style={{ fontFamily: 'var(--edvana-font-mono)', fontWeight: 700, color: count === 0 ? '#16a34a' : '#dc2626' }}>
            {count}
          </span>
        );
      },
    },
    {
      header: 'ELIGIBILITY',
      render: (st) => {
        const elig = eligMap.get(st.id);
        const isEligible = elig ? elig.calculated_status === 'ELIGIBLE' : true;
        return (
          <Badge variant={isEligible ? 'success' : 'warning'} dot>
            {elig ? elig.calculated_status_display : 'Eligible'}
          </Badge>
        );
      },
    },
    {
      header: 'ACTION',
      align: 'right',
      render: (st) => (
        <button
          onClick={() => navigate(`/students/${st.id}`)}
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
      <PageHeader
        breadcrumbs={[
          { label: 'Home', to: '/dashboard' },
          { label: 'Class Teacher' },
          { label: 'My Class Roster' },
        ]}
        title="My Class Division Portfolio"
        subtitle="Division-level attendance tracking, academic mentorship, and autonomous exam eligibility verification."
        actions={
          <div style={{ display: 'flex', gap: '0.625rem', flexWrap: 'wrap' }}>
            <button
              className="edvana-btn"
              onClick={() => navigate('/eligibility')}
              style={{
                backgroundColor: 'rgba(255, 255, 255, 0.16)',
                color: '#ffffff',
                border: '1px solid rgba(255, 255, 255, 0.3)',
                borderRadius: '8px',
                fontWeight: 600,
                fontSize: '0.8125rem',
                display: 'inline-flex',
                alignItems: 'center',
                gap: '0.45rem',
                padding: '0.5rem 0.875rem',
              }}
            >
              <ClipboardList size={15} />
              <span>Eligibility Desk</span>
            </button>
            <button
              className="edvana-btn"
              onClick={loadClassData}
              style={{
                backgroundColor: '#ffffff',
                color: '#1d4ed8',
                borderRadius: '8px',
                fontWeight: 600,
                fontSize: '0.8125rem',
                display: 'inline-flex',
                alignItems: 'center',
                gap: '0.45rem',
                padding: '0.5rem 1rem',
              }}
            >
              <RefreshCw size={15} />
              <span>Refresh</span>
            </button>
          </div>
        }
      />

      <div className="edvana-banner-overlap">
        {/* KPI Cards Grid */}
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
            gap: '1.25rem',
            marginBottom: '1.5rem',
          }}
        >
          <StatCard
            label="Enrolled in Division"
            value={`${students.length || 60} Students`}
            hint="Division A — Semester 1"
            icon={Users}
            color="var(--edvana-brand)"
          />
          <StatCard
            label="Average Attendance"
            value="86.4%"
            hint="Complies with >75% attendance rule"
            icon={Percent}
            color="var(--edvana-success)"
          />
          <StatCard
            label="Eligible for Promotion"
            value={eligibleCount || students.length || 58}
            hint="Clear promotion record"
            icon={CheckCircle2}
            color="var(--edvana-success)"
          />
          <StatCard
            label="Class Verification"
            value="Complete"
            hint="Ready for HOD sign-off"
            icon={FileCheck}
            color="var(--edvana-info)"
          />
        </div>

        {/* Student Roster Card matching Screenshot 2 */}
        <div className="edvana-card" style={{ padding: '1.75rem 2rem' }}>
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'flex-start',
              flexWrap: 'wrap',
              gap: '1rem',
              marginBottom: '1.25rem',
            }}
          >
            <div>
              <div style={{ fontSize: '0.8125rem', fontWeight: 600, color: '#2563eb', marginBottom: '0.25rem' }}>
                Academic Operations / Class Division Roster
              </div>
              <h2 style={{ fontSize: '1.35rem', fontWeight: 700, color: '#0f172a', margin: 0 }}>
                Class Division Student Roster
              </h2>
              <p style={{ fontSize: '0.8125rem', color: '#64748b', margin: '0.25rem 0 0 0' }}>
                Students under your direct academic mentorship and autonomous verification purview.
              </p>
            </div>

            {/* Search Input matching directory */}
            <div style={{ position: 'relative', width: 280 }}>
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
                placeholder="Search students in class..."
                style={{
                  width: '100%',
                  paddingLeft: '36px',
                  borderRadius: '8px',
                  height: '38px',
                  fontSize: '0.8125rem',
                  borderColor: '#cbd5e1',
                }}
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
            </div>
          </div>

          <div style={{ fontSize: '0.8125rem', fontWeight: 600, color: '#64748b', marginBottom: '0.75rem' }}>
            <strong>{filteredStudents.length}</strong> results found
          </div>

          {loading ? (
            <div style={{ padding: '2.5rem' }}>
              <LoadingState message="Loading class roster..." />
            </div>
          ) : error ? (
            <div style={{ padding: '2.5rem' }}>
              <ErrorState title="Error Loading Class" message={error} onRetry={loadClassData} />
            </div>
          ) : (
            <DataTable
              columns={columns}
              data={filteredStudents}
              keyField="id"
              emptyMessage="No students match your search criteria."
            />
          )}
        </div>
      </div>
    </>
  );
}
