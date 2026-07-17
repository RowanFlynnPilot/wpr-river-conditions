import React, { useEffect, useState } from 'react';

// Sticky in-widget navigation. Inside the fixed-height WordPress iframe the
// page is many screens tall, so jump links replace scroll-past-everything.
// Sits directly below the (also sticky) chrome bar, whose height varies.
export default function SectionNav({ sections }) {
  const [top, setTop] = useState(41);

  useEffect(() => {
    const chrome = document.querySelector('.chrome-bar');
    if (!chrome || typeof ResizeObserver === 'undefined') return undefined;
    const update = () => setTop(Math.round(chrome.getBoundingClientRect().height));
    update();
    const ro = new ResizeObserver(update);
    ro.observe(chrome);
    return () => ro.disconnect();
  }, []);

  if (!sections || sections.length === 0) return null;

  const go = (id) => (e) => {
    e.preventDefault();
    document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };

  return (
    <nav className="section-nav" style={{ top }} aria-label="Jump to section">
      {sections.map((s) => (
        <a key={s.id} className="section-nav__link" href={`#${s.id}`} onClick={go(s.id)}>
          {s.label}
        </a>
      ))}
    </nav>
  );
}
