import React, { useEffect, useState } from 'react';
import { scrollBehavior } from '../utils/motion';

// Sticky in-widget navigation. Inside the fixed-height WordPress iframe the
// page is many screens tall, so jump links replace scroll-past-everything.
// Sits directly below the (also sticky) chrome bar, whose height varies.
// The tab tracking the reader's current section fills in (scrollspy) —
// computed directly in the scroll handler (no rAF) so it also works in
// backgrounded/embedded documents where frame callbacks stall.
export default function SectionNav({ sections }) {
  const [top, setTop] = useState(41);
  const [active, setActive] = useState(null);

  useEffect(() => {
    const chrome = document.querySelector('.chrome-bar');
    if (!chrome || typeof ResizeObserver === 'undefined') return undefined;
    const update = () => setTop(Math.round(chrome.getBoundingClientRect().height));
    update();
    const ro = new ResizeObserver(update);
    ro.observe(chrome);
    return () => ro.disconnect();
  }, []);

  useEffect(() => {
    if (!sections || sections.length === 0) return undefined;
    let ticking = false;
    const compute = () => {
      ticking = false;
      let current = null;
      for (const s of sections) {
        const el = document.getElementById(s.id);
        if (!el) continue;
        if (el.getBoundingClientRect().top <= 140) current = s.id;
      }
      setActive(current);
    };
    const onScroll = () => {
      if (ticking) return;
      ticking = true;
      // Micro-debounce via timeout (not rAF — see component comment).
      setTimeout(compute, 60);
    };
    compute();
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => window.removeEventListener('scroll', onScroll);
  }, [sections]);

  if (!sections || sections.length === 0) return null;

  const go = (id) => (e) => {
    e.preventDefault();
    document.getElementById(id)?.scrollIntoView({ behavior: scrollBehavior(), block: 'start' });
  };

  return (
    <nav className="section-nav" style={{ top }} aria-label="Jump to section">
      {sections.map((s) => (
        <a
          key={s.id}
          className={`section-nav__link ${active === s.id ? 'section-nav__link--active' : ''}`}
          href={`#${s.id}`}
          aria-current={active === s.id ? 'true' : undefined}
          onClick={go(s.id)}
        >
          {s.label}
        </a>
      ))}
    </nav>
  );
}
