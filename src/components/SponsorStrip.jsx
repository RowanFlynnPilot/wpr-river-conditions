import React, { useState, useEffect } from 'react';
import { trackEvent } from '../utils/analytics';

const SPONSOR_URL = import.meta.env.DEV
  ? new URL('../../public/data/sponsor.json', import.meta.url).href
  : `${import.meta.env.BASE_URL}data/sponsor.json`;

const INQUIRY_EMAIL = 'rowan.flynn@wausaupilotandreview.com';
const INQUIRY_SUBJECT = 'Sponsorship inquiry: River Conditions widget';
const INQUIRY_BODY = `Hi Rowan,

I'd like to learn more about sponsoring the river conditions widget on Wausau Pilot & Review.

Thanks,`;

const MAILTO = `mailto:${INQUIRY_EMAIL}?subject=${encodeURIComponent(INQUIRY_SUBJECT)}&body=${encodeURIComponent(INQUIRY_BODY)}`;

export default function SponsorStrip() {
  const [sponsor, setSponsor] = useState(null);

  useEffect(() => {
    fetch(SPONSOR_URL)
      .then((r) => (r.ok ? r.json() : null))
      .then(setSponsor)
      .catch(() => setSponsor(null));
  }, []);

  const hasActiveSponsor =
    sponsor?.enabled && sponsor.name && sponsor.url;

  if (hasActiveSponsor) {
    return (
      <div className="sponsor-strip">
        <a
          className="sponsor-strip__link"
          href={sponsor.url}
          target="_blank"
          rel="noopener noreferrer sponsored"
          onClick={() => trackEvent('sponsor_click', { sponsor: sponsor.name })}
        >
          {sponsor.logo_url && (
            <img
              className="sponsor-strip__logo"
              src={sponsor.logo_url}
              alt={`${sponsor.name} logo`}
            />
          )}
          <span>
            Brought to you by <strong>{sponsor.name}</strong>
            {sponsor.tagline ? ` — ${sponsor.tagline}` : ''}
          </span>
        </a>
      </div>
    );
  }

  return (
    <div className="sponsor-strip sponsor-strip--cta">
      Interested in sponsoring this content?{' '}
      <a
        className="sponsor-strip__cta-link"
        href={MAILTO}
        onClick={() => trackEvent('sponsor_cta_click')}
      >
        Reach out →
      </a>
    </div>
  );
}
