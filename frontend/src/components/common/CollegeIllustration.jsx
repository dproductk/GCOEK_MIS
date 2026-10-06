import React from 'react';

/**
 * CollegeIllustration — institutional neoclassical vector illustration
 * matching Screenshot 1:
 * - Neoclassical college building with columns, pediment, and steps
 * - Stylized foliage / cloud shapes in soft blues
 * - Official motto quote: "Engineering for a Better Tomorrow"
 * - Royal blue accent underline bar
 */
export default function CollegeIllustration({
  quote = '"Engineering for a Better Tomorrow"',
  accentColor = '#2563eb',
  className = '',
}) {
  return (
    <div
      className={`college-illustration-wrapper ${className}`}
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        gap: '2rem',
        padding: '0.5rem',
      }}
    >
      {/* Classical University Building Vector Graphic */}
      <div style={{ position: 'relative', width: '220px', height: '140px', flexShrink: 0 }}>
        <svg
          viewBox="0 0 240 160"
          fill="none"
          xmlns="http://www.w3.org/2000/svg"
          style={{ width: '100%', height: '100%', overflow: 'visible' }}
        >
          <defs>
            <linearGradient id="cloudGrad1" x1="0" y1="0" x2="1" y2="1">
              <stop offset="0%" stopColor="#93c5fd" stopOpacity="0.8" />
              <stop offset="1%" stopColor="#60a5fa" stopOpacity="0.9" />
            </linearGradient>
            <linearGradient id="cloudGrad2" x1="0" y1="0" x2="1" y2="1">
              <stop offset="0%" stopColor="#bfdbfe" stopOpacity="0.9" />
              <stop offset="1%" stopColor="#93c5fd" stopOpacity="0.95" />
            </linearGradient>
            <linearGradient id="buildingGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#ffffff" />
              <stop offset="100%" stopColor="#f8fafc" />
            </linearGradient>
            <linearGradient id="roofGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#60a5fa" />
              <stop offset="100%" stopColor="#3b82f6" />
            </linearGradient>
          </defs>

          {/* Background Soft Blue Cloud Foliage (Left) */}
          <path
            d="M 25 130 C 15 130 10 118 16 108 C 10 98 20 86 32 90 C 38 78 54 78 62 88 C 72 84 82 94 78 106 C 85 116 78 130 65 130 Z"
            fill="url(#cloudGrad1)"
          />
          <path
            d="M 40 135 C 30 135 25 125 32 115 C 38 105 52 105 58 114 C 66 112 74 120 70 128 C 75 134 70 135 60 135 Z"
            fill="url(#cloudGrad2)"
          />

          {/* Background Soft Blue Cloud Foliage (Right) */}
          <path
            d="M 175 130 C 165 130 160 116 168 106 C 162 94 174 84 186 88 C 194 76 210 78 218 88 C 228 86 236 96 232 108 C 238 118 230 130 215 130 Z"
            fill="url(#cloudGrad1)"
          />
          <path
            d="M 180 135 C 170 135 166 125 174 116 C 180 106 195 106 200 115 C 208 114 216 122 212 130 C 218 135 210 135 200 135 Z"
            fill="url(#cloudGrad2)"
          />

          {/* Building Base Steps */}
          <rect x="45" y="132" width="150" height="6" rx="2" fill="#3b82f6" />
          <rect x="52" y="126" width="136" height="6" rx="1.5" fill="#60a5fa" />
          <rect x="58" y="121" width="124" height="5" rx="1" fill="#93c5fd" />

          {/* Main Hall Back Wall */}
          <rect
            x="64"
            y="65"
            width="112"
            height="56"
            fill="url(#buildingGrad)"
            stroke="#93c5fd"
            strokeWidth="1.5"
          />

          {/* Hall Windows / Arches in Deep Blue */}
          <rect x="74" y="80" width="10" height="24" rx="3" fill="#60a5fa" />
          <rect x="96" y="80" width="10" height="24" rx="3" fill="#60a5fa" />
          <rect x="134" y="80" width="10" height="24" rx="3" fill="#60a5fa" />
          <rect x="156" y="80" width="10" height="24" rx="3" fill="#60a5fa" />

          {/* Center Arched Entrance Door */}
          <path
            d="M 112 121 V 86 C 112 80 128 80 128 86 V 121 Z"
            fill="#2563eb"
          />
          <line x1="120" y1="84" x2="120" y2="121" stroke="#ffffff" strokeWidth="1" opacity="0.6" />

          {/* Neoclassical Columns (4 Pillars) */}
          {/* Pillar 1 */}
          <rect x="68" y="65" width="8" height="56" fill="#bfdbfe" />
          <rect x="66" y="63" width="12" height="4" rx="1" fill="#3b82f6" />
          <rect x="66" y="119" width="12" height="3" rx="1" fill="#3b82f6" />

          {/* Pillar 2 */}
          <rect x="104" y="65" width="8" height="56" fill="#bfdbfe" />
          <rect x="102" y="63" width="12" height="4" rx="1" fill="#3b82f6" />
          <rect x="102" y="119" width="12" height="3" rx="1" fill="#3b82f6" />

          {/* Pillar 3 */}
          <rect x="128" y="65" width="8" height="56" fill="#bfdbfe" />
          <rect x="126" y="63" width="12" height="4" rx="1" fill="#3b82f6" />
          <rect x="126" y="119" width="12" height="3" rx="1" fill="#3b82f6" />

          {/* Pillar 4 */}
          <rect x="164" y="65" width="8" height="56" fill="#bfdbfe" />
          <rect x="162" y="63" width="12" height="4" rx="1" fill="#3b82f6" />
          <rect x="162" y="119" width="12" height="3" rx="1" fill="#3b82f6" />

          {/* Entablature (Architrave & Cornice) */}
          <rect x="60" y="58" width="120" height="7" rx="1.5" fill="#3b82f6" />
          <rect x="56" y="52" width="128" height="6" rx="1.5" fill="#60a5fa" />

          {/* Triangular Pediment (Roof) */}
          <path
            d="M 54 52 L 120 18 L 186 52 Z"
            fill="url(#roofGrad)"
            stroke="#2563eb"
            strokeWidth="1.5"
          />

          {/* Center Oculus (Circular Window / Clock) */}
          <circle cx="120" cy="38" r="6" fill="#ffffff" stroke="#2563eb" strokeWidth="1.5" />
          <circle cx="120" cy="38" r="2.5" fill="#3b82f6" />

          {/* Peak Finial / Flag */}
          <line x1="120" y1="18" x2="120" y2="8" stroke="#1d4ed8" strokeWidth="2" strokeLinecap="round" />
          <path d="M 120 8 L 128 12 L 120 16 Z" fill="#2563eb" />

          {/* Subtle Ground Horizon Shadow */}
          <line x1="30" y1="138" x2="210" y2="138" stroke="#dbeafe" strokeWidth="2" strokeLinecap="round" />
        </svg>
      </div>

      {/* Quote & Accent Underline */}
      <div style={{ display: 'flex', flexDirection: 'column', maxWidth: '180px' }}>
        <p
          style={{
            margin: 0,
            fontFamily: 'var(--edvana-font-sans)',
            fontStyle: 'italic',
            fontSize: '1rem',
            lineHeight: 1.35,
            fontWeight: 600,
            color: '#334155',
            letterSpacing: '-0.01em',
          }}
        >
          {quote}
        </p>
        <div
          style={{
            width: '38px',
            height: '3.5px',
            backgroundColor: accentColor,
            borderRadius: '2px',
            marginTop: '8px',
          }}
        />
      </div>
    </div>
  );
}
