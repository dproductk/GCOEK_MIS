import { useEffect, useRef, useState } from 'react';

/**
 * Reveal — scroll-triggered micro-animation wrapper.
 * Fades + slides content in on first visibility, with optional stagger delay.
 *
 * Usage:
 *   <Reveal delay={80}><StatCard … /></Reveal>
 *   <Reveal.Group>…children stagger automatically via CSS…</Reveal.Group>
 */
export default function Reveal({
  children,
  delay = 0,
  as: Tag = 'div',
  className = '',
  style = {},
}) {
  const ref = useRef(null);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    // Honor reduced-motion: show immediately, no observer needed.
    if (window.matchMedia?.('(prefers-reduced-motion: reduce)').matches) {
      setVisible(true);
      return;
    }
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            setVisible(true);
            observer.disconnect();
          }
        });
      },
      { threshold: 0.12, rootMargin: '0px 0px -8px 0px' }
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  return (
    <Tag
      ref={ref}
      className={`reveal ${visible ? 'is-visible' : ''} ${className}`}
      style={{ '--reveal-delay': `${delay}ms`, ...style }}
    >
      {children}
    </Tag>
  );
}
