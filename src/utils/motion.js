// JS-driven scrolling honors the reader's reduced-motion preference
// (CSS animations are gated separately in index.css).
export function scrollBehavior() {
  return window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth';
}
