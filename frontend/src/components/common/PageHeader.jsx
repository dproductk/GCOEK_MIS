import React from 'react';
import { Link } from 'react-router-dom';
import { ChevronRight } from 'lucide-react';
import iconImg from '../../assets/icon.jpg';

/**
 * Standard EDVANA PageHeader component.
 * Renders the signature royal-blue institutional banner matching screenshots:
 * - Breadcrumb trail with subtle '>' separator
 * - Large bold page title
 * - Subtitle
 * - Right side: Official frosted glass seal badge:
 *   [ (Seal) GCE KOLHAPUR / Autonomous Institute ]
 * - Optional custom actions
 */
export default function PageHeader({
  breadcrumbs = [],
  title,
  subtitle,
  actions,
  badge = true,
  category,
}) {
  return (
    <div className="edvana-banner">
      <div
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          alignItems: 'flex-start',
          justifyContent: 'space-between',
          gap: '1.25rem',
          position: 'relative',
          zIndex: 2,
        }}
      >
        <div>
          {/* Category or Breadcrumb Trail */}
          {breadcrumbs && breadcrumbs.length > 0 && (
            <nav className="edvana-banner-breadcrumb" aria-label="Breadcrumb">
              {breadcrumbs.map((crumb, idx) => {
                const isLast = idx === breadcrumbs.length - 1;
                const path = crumb.to || crumb.link;
                return (
                  <React.Fragment key={idx}>
                    {idx > 0 && (
                      <ChevronRight size={13} style={{ opacity: 0.6, flexShrink: 0, margin: '0 2px' }} />
                    )}
                    {path && !isLast ? (
                      <Link to={path}>{crumb.label || crumb}</Link>
                    ) : (
                      <span style={{ fontWeight: isLast ? 600 : 400, opacity: isLast ? 1 : 0.85 }}>
                        {crumb.label || crumb}
                      </span>
                    )}
                  </React.Fragment>
                );
              })}
            </nav>
          )}

          {/* Optional small category label */}
          {category && (
            <div
              style={{
                fontSize: '0.8125rem',
                color: 'rgba(255, 255, 255, 0.8)',
                marginBottom: '0.25rem',
                fontWeight: 500,
              }}
            >
              {category}
            </div>
          )}

          {/* Page Title */}
          <h1 className="edvana-banner-title">{title}</h1>

          {/* Subtitle */}
          {subtitle && (
            <p
              style={{
                margin: '0.35rem 0 0 0',
                fontSize: '0.9375rem',
                color: 'rgba(255, 255, 255, 0.88)',
                maxWidth: '680px',
                lineHeight: 1.4,
              }}
            >
              {subtitle}
            </p>
          )}
        </div>

        {/* Right side: Frosted Seal Badge and optional actions */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.875rem', flexWrap: 'wrap' }}>
          {actions}

          {badge && (
            <div className="edvana-banner-seal-badge">
              <div className="edvana-seal-circle">
                <img src={iconImg} alt="GCE Kolhapur Emblem" />
              </div>
              <div className="edvana-seal-text">
                <span className="edvana-seal-title">GCE KOLHAPUR</span>
                <span className="edvana-seal-sub">DBATU Institute</span>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
