import React from 'react';

export default function CommunityBar({ links }) {
  if (!links) return null;

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
          >
            {'\uD83C\uDFA3'} Share Your Catch
          </a>
        )}
        {links.social_url && (
          <a
            className="community-bar__link"
            href={links.social_url}
            target="_blank"
            rel="noopener noreferrer"
          >
            {'\uD83D\uDCF7'} {links.photo_hashtag || 'Follow Us'}
          </a>
        )}
        {links.email && (
          <a
            className="community-bar__link"
            href={`mailto:${links.email}?subject=Fishing Report`}
          >
            {'\uD83D\uDCE7'} Send a Tip
          </a>
        )}
      </div>
    </div>
  );
}
