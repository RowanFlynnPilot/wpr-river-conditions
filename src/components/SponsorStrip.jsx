import React from 'react';
import { trackEvent } from '../utils/analytics';
import EmailCTA from './EmailCTA';

const INQUIRY_EMAIL = 'rowan.flynn@wausaupilotandreview.com';
const INQUIRY_SUBJECT = 'Sponsorship inquiry: River Conditions widget';
const INQUIRY_BODY = `Hi Rowan,

I'd like to learn more about sponsoring the river conditions widget on Wausau Pilot & Review.

Thanks,`;

export default function SponsorStrip({ sponsor }) {
  const hasActiveSponsor = sponsor?.enabled && sponsor.name && sponsor.url;

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
      <EmailCTA
        triggerLabel="Reach out →"
        triggerClassName="sponsor-strip__cta-link"
        email={INQUIRY_EMAIL}
        subject={INQUIRY_SUBJECT}
        body={INQUIRY_BODY}
        analyticsEvent="sponsor_cta_click"
      />
    </div>
  );
}
