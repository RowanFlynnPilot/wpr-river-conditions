import React from 'react';

export default function LureSuggestions({ lures }) {
  if (!lures || lures.length === 0) return null;

  return (
    <div className="lure-suggestions">
      <div className="lure-suggestions__header">🎣 Right now, try</div>
      <div className="lure-suggestions__list">
        {lures.map((l, i) => (
          <div key={i} className="lure-suggestion">
            <span className="lure-suggestion__species">{l.species}:</span>{' '}
            {l.lure}
            {l.why && (
              <div className="lure-suggestion__why">{l.why}</div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
