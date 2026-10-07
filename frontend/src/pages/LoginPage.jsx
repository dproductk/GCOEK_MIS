/**
 * Login Page — Pixel-perfect match to official GCOEK design reference.
 *
 * Implements:
 * - Ambient neoclassical campus architectural background with soft vignette
 * - Top tagline (KNOWLEDGE | INNOVATION | SOCIETY) with active innovation indicator
 * - Bottom footer (ESTD. 1960 — | Transforming Ideas Into a Better Tomorrow)
 * - Left institutional blue showcase with college seal, features list, and bottom motto
 * - Right panel with inputs, password toggle, and submit
 * - Robust Vanilla CSS (login.css) eliminating broken uncompiled Tailwind dependencies
 */
import { useState } from 'react';
import { useNavigate, Navigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { 
  User, Lock, Eye, EyeOff, HelpCircle, ArrowRight,
  GraduationCap, Users, FileText, Shield
} from 'lucide-react';
import iconImg from '../assets/icon.jpg';
import campusBg from '../assets/campus_bg.jpg';
import '../assets/styles/login.css';

export default function LoginPage() {
  const { login, isAuthenticated, loading: authLoading } = useAuth();
  const navigate = useNavigate();

  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [rememberMe, setRememberMe] = useState(true);
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  // If already authenticated, redirect to dashboard
  if (authLoading) {
    return (
      <div className="login-page-container" style={{ alignItems: 'center', justifyContent: 'center' }}>
        <div style={{ background: '#ffffff', padding: '2rem', borderRadius: '1rem', boxShadow: '0 20px 25px -5px rgba(0,0,0,0.1)', textAlign: 'center' }}>
          <div className="login-loading-spinner" style={{ borderColor: 'rgba(37,99,235,0.3)', borderTopColor: '#2563eb', margin: '0 auto 1rem' }} />
          <p style={{ fontSize: '0.875rem', fontWeight: 500, color: '#64748b' }}>Restoring session...</p>
        </div>
      </div>
    );
  }

  if (isAuthenticated) {
    return <Navigate to="/dashboard" replace />;
  }

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!username.trim() || !password) {
      setError('Please enter both username and password.');
      return;
    }

    setLoading(true);
    setError('');

    const result = await login(username.trim(), password);

    setLoading(false);

    if (result.success) {
      if (result.must_change_password) {
        navigate('/change-password', { replace: true });
      } else {
        navigate('/dashboard', { replace: true });
      }
    } else {
      setError(result.error);
    }
  };

  return (
    <div className="login-page-container">
      {/* Background Campus Architectural Layer */}
      <div className="login-bg-backdrop">
        <img src={campusBg} alt="Campus Building" className="login-bg-image" />
        <div className="login-bg-overlay" />
      </div>

      {/* Top Header Tagline */}
      <div className="login-top-bar">
        <span className="tag-item">KNOWLEDGE</span>
        <span className="tag-divider">|</span>
        <div className="innovation-tag-wrap">
          <span className="tag-item">INNOVATION</span>
          <div className="innovation-tag-line" />
        </div>
        <span className="tag-divider">|</span>
        <span className="tag-item">SOCIETY</span>
      </div>

      {/* Main Centered Login Card */}
      <div className="login-card-center">
        <div className="login-card-main">
          {/* Left Panel: Blue Institutional Showcase */}
          <div className="login-blue-showcase">
            {/* Campus Watermark blended into bottom of card */}
            <div 
              className="login-showcase-bg-image" 
              style={{ backgroundImage: `url(${campusBg})` }}
            />

            <div className="login-showcase-content">
              {/* College Emblem / Seal */}
              <div className="login-seal-wrapper">
                <img 
                  src={iconImg} 
                  alt="Government College of Engineering, Kolhapur Official Seal" 
                  className="login-seal-img"
                />
              </div>

              {/* Title & Autonomous Badge */}
              <h1 className="login-college-title">
                Government College<br />of Engineering, Kolhapur
              </h1>
              <div className="login-autonomous-badge">
                (DBATU)
              </div>
              <div className="login-affiliation-badge">
                AFFILIATED TO DBATU, LONERE
              </div>

              {/* 4 Feature Items */}
              <div className="login-features-list">
                <div className="login-feature-item">
                  <div className="login-feature-icon">
                    <GraduationCap size={19} />
                  </div>
                  <div className="login-feature-text">
                    <h4 className="login-feature-heading">Academic Management</h4>
                    <p className="login-feature-subtext">Admissions • Examinations • Results</p>
                  </div>
                </div>

                <div className="login-feature-item">
                  <div className="login-feature-icon">
                    <Users size={19} />
                  </div>
                  <div className="login-feature-text">
                    <h4 className="login-feature-heading">Multi-Role Access</h4>
                    <p className="login-feature-subtext">Students • Faculty • Staff</p>
                  </div>
                </div>

                <div className="login-feature-item">
                  <div className="login-feature-icon">
                    <FileText size={19} />
                  </div>
                  <div className="login-feature-text">
                    <h4 className="login-feature-heading">Fee Management</h4>
                    <p className="login-feature-subtext">Challans • Payments • Reports</p>
                  </div>
                </div>

                <div className="login-feature-item">
                  <div className="login-feature-icon">
                    <Shield size={19} />
                  </div>
                  <div className="login-feature-text">
                    <h4 className="login-feature-heading">Secure & Reliable</h4>
                    <p className="login-feature-subtext">Your data is safe with us</p>
                  </div>
                </div>
              </div>
            </div>

            {/* Bottom Left Slogan */}
            <div className="login-bottom-motto">
              ENGINEERING MINDS<br />FOR A BETTER TOMORROW
            </div>
          </div>

          {/* Right Panel: Sign In Form */}
          <div className="login-form-side">
            <div>
              {/* Header: Sign In & Need Help */}
              <div className="login-form-header">
                <div>
                  <h2 className="login-signin-title">Sign In</h2>
                  <p className="login-signin-desc">
                    Enter your credentials to access the administrative portal.
                  </p>
                </div>
                <button 
                  type="button" 
                  onClick={() => alert("For help with GCOEK MIS login, contact the Administrative Office or Systems Administrator at admin@gcoek.ac.in.")}
                  className="login-need-help-btn"
                  title="Need help?"
                >
                  <span>Need help?</span>
                  <HelpCircle size={15} />
                </button>
              </div>

              {error && (
                <div className="login-error-alert">
                  {error}
                </div>
              )}

              {/* Login Form */}
              <form onSubmit={handleSubmit} className="login-form-container">
                <div className="login-input-group">
                  <label 
                    htmlFor="login-username" 
                    className="login-input-label"
                  >
                    Username
                  </label>
                  <div className="login-input-relative-wrap">
                    <div className="login-field-left-icon">
                      <User size={18} />
                    </div>
                    <input
                      id="login-username"
                      type="text"
                      required
                      value={username}
                      onChange={(e) => setUsername(e.target.value)}
                      placeholder="Enter your username or Application ID"
                      disabled={loading}
                      className="login-text-input"
                      autoComplete="username"
                    />
                  </div>
                </div>

                <div className="login-input-group">
                  <label 
                    htmlFor="login-password" 
                    className="login-input-label"
                  >
                    Password
                  </label>
                  <div className="login-input-relative-wrap">
                    <div className="login-field-left-icon">
                      <Lock size={18} />
                    </div>
                    <input
                      id="login-password"
                      type={showPassword ? 'text' : 'password'}
                      required
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      placeholder="••••••••"
                      disabled={loading}
                      className="login-text-input with-toggle"
                      autoComplete="current-password"
                    />
                    <button
                      type="button"
                      onClick={() => setShowPassword(!showPassword)}
                      className="login-pwd-toggle-btn"
                      aria-label={showPassword ? 'Hide password' : 'Show password'}
                      tabIndex={-1}
                    >
                      {showPassword ? <EyeOff size={17} /> : <Eye size={17} />}
                    </button>
                  </div>
                </div>

                {/* Remember me & Forgot Password */}
                <div className="login-meta-options-row">
                  <label className="login-remember-checkbox-label">
                    <input
                      type="checkbox"
                      checked={rememberMe}
                      onChange={(e) => setRememberMe(e.target.checked)}
                      className="login-custom-checkbox"
                    />
                    <span>Remember me</span>
                  </label>
                  <button
                    type="button"
                    onClick={() => alert("Please contact the MIS admin at admin@gcoek.ac.in to reset your password.")}
                    className="login-forgot-pwd-btn"
                  >
                    Forgot password?
                  </button>
                </div>

                {/* Submit Button */}
                <button
                  type="submit"
                  disabled={loading}
                  className="login-submit-action-btn"
                >
                  {loading ? (
                    <>
                      <div className="login-loading-spinner" />
                      <span>Signing In...</span>
                    </>
                  ) : (
                    <>
                      <ArrowRight size={18} />
                      <span>Sign In</span>
                    </>
                  )}
                </button>
              </form>
            </div>

            {/* Bottom Institutional Seal Footer */}
            <div className="login-bottom-institutional-footer">
              <div className="login-inst-name">
                Government College of Engineering, Kolhapur
              </div>
              <div className="login-inst-sub">
                (DBATU)
              </div>
              <div className="login-inst-underline" />
            </div>
          </div>
        </div>
      </div>

      {/* Bottom Page Footer Bar */}
      <div className="login-bottom-bar">
        <div className="estd-text">
          <span>ESTD. 1960</span>
          <span className="estd-line" />
        </div>
        <div>
          Transforming Ideas Into a Better Tomorrow
        </div>
      </div>
    </div>
  );
}
