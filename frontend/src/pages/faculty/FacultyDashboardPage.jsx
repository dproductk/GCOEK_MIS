import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import facultyApi from '../../api/facultyApi';
import { LoadingState } from '../../components/common/StateDisplays';
import PageHeader from '../../components/common/PageHeader';

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

  const displayName = profile?.display_name || user?.username || 'Faculty Member';
  const subtitle = profile
    ? `${profile.designation_display || 'Faculty'} — Department of ${profile.department_name || '—'}`
    : `${activeRole?.name || 'Faculty Portal'}`;

  if (loading) {
    return (
      <div style={{ padding: '2rem' }}>
        <LoadingState message="Loading faculty portal dashboard..." />
      </div>
    );
  }

  const hubLinks = [
    { text: 'View and update your personal information, address, contact details, and bank details, etc.', to: '/profile' },
    { text: 'Browse the student directory and verify student profiles.', to: '/students' },
    ...(activeRole?.codename === 'CLASS_TEACHER' || activeRole?.codename === 'HOD'
      ? [{ text: 'Review your class, verify results and endorse promotions.', to: '/my-class' }]
      : []),
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
        subtitle={subtitle}
      />

      <div className="edvana-banner-overlap">
        <div className="edvana-card" style={{ padding: '1.75rem 2rem', borderRadius: '18px' }}>
          <div style={{ fontSize: '0.8125rem', color: '#475569', marginBottom: '0.9rem', lineHeight: 1.6 }}>
            This is your central hub for managing your teaching and non-teaching activities, as well as viewing and updating your personal information.
          </div>
          <ul style={{ margin: 0, paddingLeft: '1.1rem', display: 'flex', flexDirection: 'column', gap: '0.45rem', fontSize: '0.85rem', color: '#1e293b' }}>
            {hubLinks.map((l) => (
              <li key={l.text}>
                {l.to ? (
                  <button
                    type="button"
                    onClick={() => navigate(l.to)}
                    style={{
                      background: 'none', border: 'none', padding: 0, cursor: 'pointer',
                      color: '#1E60DC', fontWeight: 600, fontSize: '0.85rem', textAlign: 'left',
                    }}
                  >
                    {l.text}
                  </button>
                ) : (
                  <span>{l.text}</span>
                )}
              </li>
            ))}
          </ul>
        </div>

      </div>
    </>
  );
}
