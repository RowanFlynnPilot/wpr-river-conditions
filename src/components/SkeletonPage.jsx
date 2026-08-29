import React from 'react';

export default function SkeletonPage() {
  return (
    <div className="skeleton-page" aria-busy="true" role="status">
      <span className="visually-hidden">Loading river conditions</span>
      <div className="skeleton skeleton-page__weather" />
      <div className="skeleton skeleton-page__hero" />
      <div className="skeleton skeleton-page__map" />
      <div className="skeleton-page__gauges">
        {Array.from({ length: 6 }).map((_, i) => (
          <div key={i} className="skeleton skeleton-page__card" />
        ))}
      </div>
    </div>
  );
}
