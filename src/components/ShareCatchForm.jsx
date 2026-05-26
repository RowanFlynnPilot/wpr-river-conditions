import React, { useState } from 'react';
import { trackEvent } from '../utils/analytics';

// Web3Forms access key — safe to expose client-side (it's a routing key,
// not a secret credential). Generate at https://web3forms.com/. Replace
// the placeholder below with the actual key from the dashboard.
const WEB3FORMS_KEY = 'cde5b31f-8574-4764-a486-d701ac823f1a';
const SUBMIT_URL = 'https://api.web3forms.com/submit';
const MAX_FILE_MB = 10;

export default function ShareCatchForm({ onClose }) {
  const [status, setStatus] = useState('idle'); // idle | submitting | success | error
  const [errorMsg, setErrorMsg] = useState('');

  const handleSubmit = async (e) => {
    e.preventDefault();
    setStatus('submitting');
    setErrorMsg('');

    const form = e.target;
    const fd = new FormData(form);

    // Honeypot — bots fill it, humans don't
    if (fd.get('botcheck')) {
      setStatus('error');
      setErrorMsg('Spam detected.');
      return;
    }

    // Validate file sizes
    const files = fd.getAll('photos');
    for (const f of files) {
      if (f && f.size && f.size > MAX_FILE_MB * 1024 * 1024) {
        setStatus('error');
        setErrorMsg(`Photo "${f.name}" exceeds the ${MAX_FILE_MB} MB limit.`);
        return;
      }
    }

    fd.append('access_key', WEB3FORMS_KEY);
    fd.append('subject', `New catch report from ${fd.get('name') || 'reader'}`);
    fd.append('from_name', 'WPR River Conditions Widget');

    try {
      const res = await fetch(SUBMIT_URL, { method: 'POST', body: fd });
      const data = await res.json().catch(() => null);
      if (res.ok && data && data.success) {
        setStatus('success');
        trackEvent('catch_submitted');
        form.reset();
      } else {
        setStatus('error');
        setErrorMsg(data?.message || 'Submission failed. Please try again.');
      }
    } catch (err) {
      setStatus('error');
      setErrorMsg('Network error. Please try again.');
    }
  };

  if (status === 'success') {
    return (
      <div className="catch-form catch-form--success">
        <h3 className="catch-form__title">Thanks for sharing! 🎣</h3>
        <p className="catch-form__body">
          Your catch report has been sent to the WPR editors. We may reach out
          if we'd like to feature it.
        </p>
        <button
          type="button"
          className="catch-form__close"
          onClick={onClose}
        >
          Close
        </button>
      </div>
    );
  }

  return (
    <form className="catch-form" onSubmit={handleSubmit}>
      <div className="catch-form__header">
        <h3 className="catch-form__title">Share Your Catch</h3>
        <button
          type="button"
          className="catch-form__close-x"
          onClick={onClose}
          aria-label="Close form"
        >
          ×
        </button>
      </div>

      <p className="catch-form__intro">
        Got a good day on the water? Tell us about it. We'll consider featuring
        reports in upcoming WPR fishing coverage.
      </p>

      {/* Honeypot field — hidden from real users via CSS */}
      <input
        type="checkbox"
        name="botcheck"
        className="catch-form__honeypot"
        tabIndex="-1"
        autoComplete="off"
      />

      <div className="catch-form__grid">
        <label className="catch-form__field">
          <span className="catch-form__label">Your name <em>(required)</em></span>
          <input type="text" name="name" required maxLength={80} />
        </label>

        <label className="catch-form__field">
          <span className="catch-form__label">Email <em>(optional)</em></span>
          <input
            type="email"
            name="email"
            maxLength={120}
            placeholder="So we can reach out if we feature it"
          />
        </label>

        <label className="catch-form__field catch-form__field--wide">
          <span className="catch-form__label">Where you fished <em>(required)</em></span>
          <input
            type="text"
            name="location"
            required
            maxLength={120}
            placeholder="e.g. Rothschild boat landing, Big Eau Pleine"
          />
        </label>

        <label className="catch-form__field">
          <span className="catch-form__label">Species</span>
          <input
            type="text"
            name="species"
            maxLength={60}
            placeholder="Walleye, smallmouth, musky…"
          />
        </label>

        <label className="catch-form__field">
          <span className="catch-form__label">Date caught</span>
          <input type="date" name="date_caught" />
        </label>

        <label className="catch-form__field catch-form__field--wide">
          <span className="catch-form__label">Lure or bait</span>
          <input
            type="text"
            name="lure"
            maxLength={100}
            placeholder="e.g. 1/4 oz chartreuse jig + minnow"
          />
        </label>

        <label className="catch-form__field catch-form__field--wide">
          <span className="catch-form__label">
            Caption / story <em>(optional)</em>
          </span>
          <textarea
            name="caption"
            rows={3}
            maxLength={600}
            placeholder="Tell us about the day, the bite, anything you'd want a reader to know."
          />
        </label>

        <label className="catch-form__field catch-form__field--wide">
          <span className="catch-form__label">
            Photos <em>(optional, up to {MAX_FILE_MB} MB each)</em>
          </span>
          <input
            type="file"
            name="photos"
            accept="image/*"
            multiple
          />
        </label>
      </div>

      {status === 'error' && (
        <div className="catch-form__error" role="alert">
          {errorMsg}
        </div>
      )}

      <div className="catch-form__actions">
        <button
          type="submit"
          className="catch-form__submit"
          disabled={status === 'submitting'}
        >
          {status === 'submitting' ? 'Sending…' : 'Send catch report'}
        </button>
        <button
          type="button"
          className="catch-form__cancel"
          onClick={onClose}
        >
          Cancel
        </button>
      </div>
    </form>
  );
}
