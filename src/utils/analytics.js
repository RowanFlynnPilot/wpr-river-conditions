// Fires a custom analytics event. No-ops if no provider is loaded,
// and never throws — analytics should not break the UI.
//
// Supports Cloudflare Web Analytics and GA4 (gtag) in parallel, so
// either can be wired in via index.html without code changes here.

export function trackEvent(name, props = {}) {
  try {
    if (typeof window === 'undefined') return;

    if (window.cfAnalytics && typeof window.cfAnalytics.event === 'function') {
      window.cfAnalytics.event(name, props);
    }

    if (typeof window.gtag === 'function') {
      window.gtag('event', name, props);
    }

    if (import.meta.env.DEV) {
      console.debug('[analytics]', name, props);
    }
  } catch {
    // swallow — analytics must never break the UI
  }
}
