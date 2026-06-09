import React, { useState } from 'react';
import { trackEvent } from '../utils/analytics';

// Reuses the same Web3Forms routing key as the catch-report form — submissions
// land in the WPR inbox. The key is a routing key, not a secret credential, so
// it's safe client-side. Generate/replace at https://web3forms.com/.
const WEB3FORMS_KEY = 'cde5b31f-8574-4764-a486-d701ac823f1a';
const SUBMIT_URL = 'https://api.web3forms.com/submit';

export default function FloodAlertSignup() {
  const [status, setStatus] = useState('idle'); // idle | submitting | success | error
  const [errorMsg, setErrorMsg] = useState('');

  const handleSubmit = async (e) => {
    e.preventDefault();
    setStatus('submitting');
    setErrorMsg('');

    const form = e.target;
    const fd = new FormData(form);

    // Honeypot — bots fill it, humans don't.
    if (fd.get('botcheck')) {
      setStatus('error');
      setErrorMsg('Spam detected.');
      return;
    }

    fd.append('access_key', WEB3FORMS_KEY);
    fd.append('subject', 'River Conditions — flood alert signup');
    fd.append('from_name', 'WPR River Conditions Widget');

    try {
      const res = await fetch(SUBMIT_URL, { method: 'POST', body: fd });
      const data = await res.json().catch(() => null);
      if (res.ok && data && data.success) {
        setStatus('success');
        trackEvent('flood_alert_signup');
        form.reset();
      } else {
        setStatus('error');
        setErrorMsg(data?.message || 'Signup failed. Please try again.');
      }
    } catch {
      setStatus('error');
      setErrorMsg('Network error. Please try again.');
    }
  };

  if (status === 'success') {
    return (
      <div className="flood-signup flood-signup--success" role="status">
        <span className="flood-signup__check" aria-hidden="true">✓</span>
        <div>
          <strong>You&rsquo;re on the list.</strong> We&rsquo;ll email you when
          central Wisconsin rivers approach flood stage.
        </div>
      </div>
    );
  }

  return (
    <form className="flood-signup" onSubmit={handleSubmit}>
      <div className="flood-signup__pitch">
        <span className="flood-signup__icon" aria-hidden="true">🔔</span>
        <div>
          <div className="flood-signup__title">Get flood alerts by email</div>
          <div className="flood-signup__sub">
            We&rsquo;ll notify you when local rivers approach flood stage.
          </div>
        </div>
      </div>

      {/* Honeypot — visually hidden via CSS */}
      <input
        type="checkbox"
        name="botcheck"
        className="flood-signup__honeypot"
        tabIndex="-1"
        autoComplete="off"
      />

      <div className="flood-signup__controls">
        <label className="flood-signup__visually-hidden" htmlFor="flood-signup-email">
          Email address
        </label>
        <input
          id="flood-signup-email"
          type="email"
          name="email"
          required
          maxLength={120}
          placeholder="you@example.com"
          className="flood-signup__input"
          autoComplete="email"
        />
        <button
          type="submit"
          className="flood-signup__submit"
          disabled={status === 'submitting'}
        >
          {status === 'submitting' ? 'Signing up…' : 'Notify me'}
        </button>
      </div>

      {status === 'error' && (
        <div className="flood-signup__error" role="alert">
          {errorMsg}
        </div>
      )}
    </form>
  );
}
