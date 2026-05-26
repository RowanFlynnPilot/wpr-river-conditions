import React from 'react';
import { trackEvent } from '../utils/analytics';

const TIP_SUBJECT = 'Fishing report — Wausau area';
const TIP_BODY = `Hi WPR editor,

I'd like to share a fishing report or tip from the Wausau area.

Where:
What I caught (or saw):
Lure / bait:
Date / time:

Thanks,`;

export default function CommunityBar({ links }) {
  if (!links) return null;

  const tipMailto = links.email
    ? `mailto:${links.email}?subject=${encodeURIComponent(TIP_SUBJECT)}&body=${encodeURIComponent(TIP_BODY)}`
    : null;

  return (
    <div className="community-bar">
      <div className="community-bar__title">Get Involved</div>
      <div className="community-bar__links">
        {links.fishing_report_form && (
          <a
            className="community-bar__link"
            href={links.fishing_report_form}
            target="_blank"
            rel="noopener noreferrer"
            onClick={() => trackEvent('community_link_click', { kind: 'share_catch' })}
          >
            🎣 Share Your Catch
          </a>
        )}
        {links.social_url && (
          <a
            className="community-bar__link"
            href={links.social_url}
            target="_blank"
            rel="noopener noreferrer"
            onClick={() => trackEvent('community_link_click', { kind: 'social' })}
          >
            📷 {links.photo_hashtag || 'Follow Us'}
          </a>
        )}
        {tipMailto && (
          <a
            className="community-bar__link"
            href={tipMailto}
            target="_blank"
            rel="noopener noreferrer"
            onClick={() => trackEvent('community_link_click', { kind: 'send_tip' })}
          >
            📧 Send a Tip
          </a>
        )}
      </div>
    </div>
  );
}
