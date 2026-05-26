import React, { useState } from 'react';
import { trackEvent } from '../utils/analytics';

/**
 * Inline email contact panel. Clicking the trigger reveals the email
 * address with a "Copy" button + a "Try email app" mailto link. Designed
 * to work even when the user's browser has no default mail handler
 * registered (extremely common on desktop), in which case the user can
 * still copy the address and write the email manually.
 */
export default function EmailCTA({
  triggerLabel,
  triggerClassName = '',
  email,
  subject,
  body,
  analyticsEvent,
  analyticsProps,
}) {
  const [open, setOpen] = useState(false);
  const [copied, setCopied] = useState(false);

  const mailto = `mailto:${email}?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`;

  const handleTrigger = (e) => {
    e.preventDefault();
    setOpen(true);
    setCopied(false);
    if (analyticsEvent) trackEvent(analyticsEvent, analyticsProps || {});
  };

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(email);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Fallback: select the text via execCommand-style hack
      const el = document.createElement('textarea');
      el.value = email;
      document.body.appendChild(el);
      el.select();
      try { document.execCommand('copy'); setCopied(true); } catch {}
      document.body.removeChild(el);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  if (!open) {
    return (
      <a
        href={mailto}
        target="_blank"
        rel="noopener noreferrer"
        className={triggerClassName}
        onClick={handleTrigger}
      >
        {triggerLabel}
      </a>
    );
  }

  return (
    <div className="email-cta">
      <div className="email-cta__row">
        <span className="email-cta__label">Email:</span>
        <code className="email-cta__address">{email}</code>
        <button
          type="button"
          className="email-cta__btn email-cta__btn--copy"
          onClick={handleCopy}
        >
          {copied ? 'Copied ✓' : 'Copy'}
        </button>
      </div>
      <div className="email-cta__actions">
        <a
          className="email-cta__btn email-cta__btn--open"
          href={mailto}
          target="_blank"
          rel="noopener noreferrer"
        >
          Open in email app
        </a>
        <button
          type="button"
          className="email-cta__btn email-cta__btn--close"
          onClick={() => setOpen(false)}
        >
          Close
        </button>
      </div>
      <div className="email-cta__hint">
        If "Open in email app" doesn't work, copy the address and use your
        preferred email service. Suggested subject: <em>{subject}</em>
      </div>
    </div>
  );
}
