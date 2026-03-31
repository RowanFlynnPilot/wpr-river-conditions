import React from 'react';

const CATEGORY_CONFIG = {
  season: { label: 'Season', css: 'season' },
  event:  { label: 'Event', css: 'event' },
};

function formatEventDate(dateStr) {
  const d = new Date(dateStr + 'T12:00:00');
  const now = new Date();
  const diffMs = d - now;
  const diffDays = Math.ceil(diffMs / (1000 * 60 * 60 * 24));

  const formatted = d.toLocaleDateString('en-US', {
    weekday: 'short',
    month: 'short',
    day: 'numeric',
  });

  if (diffDays === 0) return { text: formatted, badge: 'Today' };
  if (diffDays === 1) return { text: formatted, badge: 'Tomorrow' };
  if (diffDays <= 7) return { text: formatted, badge: `${diffDays} days` };
  return { text: formatted, badge: null };
}

export default function EventsCalendar({ events }) {
  if (!events || events.length === 0) return null;

  return (
    <>
      <div className="section-header" style={{ marginTop: 'var(--space-lg)' }}>
        <h2 className="section-header__title">Upcoming Events</h2>
        <span className="section-header__subtitle">
          {events.length} event{events.length !== 1 ? 's' : ''} on the calendar
        </span>
      </div>

      <div className="events-list">
        {events.map((event, i) => {
          const dateInfo = formatEventDate(event.date);
          const cat = CATEGORY_CONFIG[event.category] || CATEGORY_CONFIG.event;

          return (
            <div key={i} className="events-list__item">
              <div className="events-list__date-col">
                <div className="events-list__date">{dateInfo.text}</div>
                {dateInfo.badge && (
                  <span className="events-list__countdown">{dateInfo.badge}</span>
                )}
              </div>
              <div className="events-list__detail">
                <div className="events-list__header">
                  <span className={`events-list__category events-list__category--${cat.css}`}>
                    {cat.label}
                  </span>
                  <span className="events-list__name">
                    {event.url ? (
                      <a href={event.url} target="_blank" rel="noopener noreferrer">
                        {event.name}
                      </a>
                    ) : (
                      event.name
                    )}
                  </span>
                </div>
                <div className="events-list__description">{event.description}</div>
                <div className="events-list__location">{event.location}</div>
              </div>
            </div>
          );
        })}
      </div>
    </>
  );
}
