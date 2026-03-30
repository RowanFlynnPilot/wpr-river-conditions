import React from 'react';

function formatAlertTime(isoStr) {
  if (!isoStr) return '';
  try {
    const d = new Date(isoStr);
    return d.toLocaleString('en-US', {
      month: 'short',
      day: 'numeric',
      hour: 'numeric',
      minute: '2-digit',
      timeZoneName: 'short',
    });
  } catch {
    return isoStr;
  }
}

export default function AlertBanner({ alerts }) {
  if (!alerts || alerts.length === 0) return null;

  return (
    <div role="alert">
      {alerts.map((alert, i) => (
        <div className="alert-banner" key={i}>
          <div className="alert-banner__label">
            {alert.severity === 'Severe' ? 'Severe Alert' : 'Flood Alert'}
          </div>
          <div className="alert-banner__headline">
            {alert.headline || alert.event}
          </div>
          {alert.expires && (
            <div className="alert-banner__meta">
              Until {formatAlertTime(alert.expires)}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
