import React, { useState } from 'react';
import { trackEvent } from '../utils/analytics';
import ShareCatchForm from './ShareCatchForm';
import EmailCTA from './EmailCTA';

const TIP_SUBJECT = 'Fishing report — Wausau area';
const TIP_BODY = `Hi WPR editor,

I'd like to share a fishing report or tip from the Wausau area.

Where:
What I caught (or saw):
Lure / bait:
Date / time:

Thanks,`;

export default function CommunityBar({ links }) {
  const [showForm, setShowForm] = useState(false);
  if (!links) return null;

  const openForm = () => {
    setShowForm(true);
    trackEvent('community_link_click', { kind: 'share_catch_open' });
  };

  return (
    <div className="community-bar">
      <div className="community-bar__title">Get Involved</div>
      <div className="community-bar__links">
        <button
          type="button"
          className="community-bar__link community-bar__link--button"
          onClick={openForm}
        >
          🎣 Share Your Catch
        </button>
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
        {links.email && (
          <EmailCTA
            triggerLabel="📧 Send a Tip"
            triggerClassName="community-bar__link"
            email={links.email}
            subject={TIP_SUBJECT}
            body={TIP_BODY}
            analyticsEvent="community_link_click"
            analyticsProps={{ kind: 'send_tip' }}
          />
        )}
      </div>

      {showForm && (
        <ShareCatchForm onClose={() => setShowForm(false)} />
      )}
    </div>
  );
}
