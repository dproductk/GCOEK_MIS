import React, { useState } from 'react';
import { Menu, Sun, Moon } from 'lucide-react';
import iconImg from '../../assets/icon.jpg';

/**
 * TopHeader — persistent institutional top header bar.
 * Matches reference screenshots:
 * - Brand: GOVERNMENT COLLEGE OF ENGINEERING KOLHAPUR (AUTONOMOUS)
 * - Center: Hamburger menu icon + Government College of Engineering, Kolhapur
 * - Right: Term: SUMMER 2026 badge, Theme toggle (Sun), and Circular Avatar
 */
export default function TopHeader({ onToggleSidebar, user, activeRole }) {
  const [isDark, setIsDark] = useState(false);

  // Compute initials (e.g., RK for Rohit Kumar or AH for Administrative Head)
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

  const toggleTheme = () => {
    const nextDark = !isDark;
    setIsDark(nextDark);
    if (nextDark) {
      document.documentElement.classList.add('dark');
      document.documentElement.setAttribute('data-theme', 'dark');
    } else {
      document.documentElement.classList.remove('dark');
      document.documentElement.removeAttribute('data-theme');
    }
  };

  return (
    <header className="app-topbar" role="banner">
      {/* Left: Official College Brand & Seal */}
      <div className="app-topbar-left">
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.625rem' }}>
          <div className="app-topbar-logo-circle">
            <img src={iconImg} alt="GCE Kolhapur Emblem" />
          </div>
          <span className="app-topbar-brand">
            GOVERNMENT COLLEGE OF ENGINEERING KOLHAPUR (DBATU)
          </span>
        </div>
      </div>

      {/* Center: Hamburger Toggle & Institutional Subtitle */}
      <div className="app-topbar-center-section">
        <button
          className="app-topbar-toggle"
          onClick={onToggleSidebar}
          aria-label="Toggle navigation menu"
          title="Toggle sidebar"
        >
          <Menu size={18} />
        </button>
        <span className="app-topbar-college-name">
          Government College of Engineering, Kolhapur
        </span>
      </div>

      {/* Right: Term Badge, Sun Icon, Avatar Initials */}
      <div className="app-topbar-right">
        {/* Term Badge matching screenshot */}
        <div className="app-topbar-term-badge">
          <span>Term:</span>
          <strong>SUMMER 2026</strong>
        </div>

        {/* Theme Toggle Sun Icon */}
        <button
          className="app-topbar-icon-btn"
          onClick={toggleTheme}
          title={isDark ? 'Switch to Light Mode' : 'Switch to Dark Mode'}
          aria-label="Toggle theme"
        >
          {isDark ? <Moon size={16} /> : <Sun size={17} />}
        </button>

        {/* Circular Avatar with User Initials */}
        <div
          className="app-topbar-avatar"
          title={`${user?.username || 'User'} (${roleName})`}
        >
          {initials}
        </div>
      </div>
    </header>
  );
}
