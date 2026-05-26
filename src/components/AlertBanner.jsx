import React from 'react';

const SEVERITY_CLASS = {
  Extreme:  'alert-banner--extreme',
  Severe:   'alert-banner--severe',
  Moderate: 'alert-banner--moderate',
  Minor:    'alert-banner--minor',
};

const CATEGORY_LABEL = {
  flood:  'Flood Alert',
  severe: 'Severe Weather',
  winter: 'Winter Alert',
  fire:   'Fire Weather',
  wind:   'Wind Alert',
  heat:   'Heat Alert',
};

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
      {alerts.map((alert, i) => {
        const sevClass = SEVERITY_CLASS[alert.severity] || '';
        const label = CATEGORY_LABEL[alert.category] || 'Weather Alert';
        return (
          <div className={`alert-banner ${sevClass}`} key={i}>
            <div className="alert-banner__label">{label}</div>
            <div className="alert-banner__headline">
              {alert.headline || alert.event}
            </div>
            {alert.expires && (
              <div className="alert-banner__meta">
                Until {formatAlertTime(alert.expires)}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
