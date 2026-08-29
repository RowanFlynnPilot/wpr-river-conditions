import React from 'react';

export default function SkeletonPage() {
  return (
    // Mirrors the real above-the-fold order: hero, glance table, gauge cards
    // (the map and weather live several screens down in the actual layout).
    <div className="skeleton-page" aria-busy="true" role="status">
      <span className="visually-hidden">Loading river conditions</span>
      <div className="skeleton skeleton-page__hero" />
      <div className="skeleton skeleton-page__table" />
      <div className="skeleton-page__gauges">
        {Array.from({ length: 6 }).map((_, i) => (
          <div key={i} className="skeleton skeleton-page__card" />
        ))}
      </div>
    </div>
  );
}
