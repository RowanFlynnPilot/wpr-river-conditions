import React, { useEffect, useRef, useState } from 'react';

// Defers mounting children until the placeholder nears the viewport.
// Used to keep Leaflet (and its tile requests) out of the initial load —
// inside the 900px embed the overview map starts several screens down.
export default function LazyMount({ children, minHeight = 280, rootMargin = '400px' }) {
  const ref = useRef(null);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    if (visible) return undefined;
    const el = ref.current;
    if (!el) return undefined;
    if (typeof IntersectionObserver === 'undefined') {
      setVisible(true);
      return undefined;
    }
    const io = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting)) setVisible(true);
      },
      { rootMargin }
    );
    io.observe(el);
    return () => io.disconnect();
  }, [visible, rootMargin]);

  if (visible) return children;
  return <div ref={ref} style={{ minHeight }} aria-hidden="true" />;
}
