import React from 'react';

export default function ConditionsSummary({ summary, seasonal }) {
  if ((!summary || summary.length === 0) && !seasonal) return null;

  return (
    <div className="conditions-summary">
      {/* Recent conditions narrative */}
      {summary && summary.length > 0 && (
        <div className="conditions-summary__section">
          <div className="conditions-summary__label">Recent Conditions</div>
          <div className="conditions-summary__text">
            {summary.map((s, i) => (
              <p key={i}>{s}</p>
            ))}
          </div>
        </div>
      )}

      {/* Seasonal activity */}
      {seasonal && (
        <div className="conditions-summary__section">
          <div className="conditions-summary__label">
            What's Happening in {seasonal.label}
          </div>
          <ul className="conditions-summary__list">
            {seasonal.activity.map((item, i) => (
              <li key={i}>{item}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
