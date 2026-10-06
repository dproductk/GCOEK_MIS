import { useNavigate } from 'react-router-dom';
import PageHeader from '../../components/common/PageHeader';
import CollegeIllustration from '../../components/common/CollegeIllustration';
import Reveal from '../../components/common/Reveal';
import { ArrowRight } from 'lucide-react';

export default function StudentDashboardPage() {
  const navigate = useNavigate();

  return (
    <>
      {/* Institutional Royal Blue Header matching Screenshot 1 */}
      <PageHeader
        breadcrumbs={[{ label: 'Home' }]}
        title="Dashboard"
        subtitle="Welcome to your student portal"
      />

      {/* Main Content Overlap */}
      <div className="edvana-banner-overlap">
        {/* Signature Welcome Hero Card matching Screenshot 1 */}
        <Reveal>
        <div className="edvana-card edvana-welcome-hero-card">
          <div className="edvana-welcome-grid">
            {/* Left Content Column */}
            <div className="edvana-welcome-left">
              <h2 className="edvana-welcome-title">
                Welcome to Government College of Engineering, Kolhapur
              </h2>
              <p className="edvana-welcome-subtitle">
                This is your centralized hub for managing your academic activities.
              </p>

              <ul className="edvana-welcome-checklist">
                <li>
                  <span className="checklist-bullet">•</span>
                  <span>View and update your registration information, address, contact details, and bank details</span>
                </li>
                <li>
                  <span className="checklist-bullet">•</span>
                  <span>Register for your exams</span>
                </li>
                <li>
                  <span className="checklist-bullet">•</span>
                  <span>Download hall ticket</span>
                </li>
                <li>
                  <span className="checklist-bullet">•</span>
                  <span>Print your fee receipts</span>
                </li>
                <li>
                  <span className="checklist-bullet">•</span>
                  <span>Access your results and academic records</span>
                </li>
                <li>
                  <span className="checklist-bullet">•</span>
                  <span>And more</span>
                </li>
              </ul>

              <div style={{ marginTop: '1.75rem' }}>
                <button
                  className="edvana-btn edvana-btn-primary"
                  onClick={() => navigate('/profile')}
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
                  <span>View Student Profile</span>
                  <ArrowRight size={16} />
                </button>
              </div>
            </div>

            {/* Right Classical Architecture Illustration & Quote */}
            <div className="edvana-welcome-right">
              <CollegeIllustration quote='"Engineering for a Better Tomorrow"' />
            </div>
          </div>
        </div>
        </Reveal>

      </div>
    </>
  );
}
