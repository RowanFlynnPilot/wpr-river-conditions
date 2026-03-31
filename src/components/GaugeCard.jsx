import React from 'react';
import Sparkline from './Sparkline';

function getTempStyle(tempF) {
  if (tempF < 40) return { color: '#78716c', label: 'Cold' };
  if (tempF < 55) return { color: '#2563eb', label: 'Cool' };
  if (tempF < 70) return { color: '#0d7377', label: 'Moderate' };
  if (tempF < 80) return { color: '#ea580c', label: 'Warm' };
  return { color: '#dc2626', label: 'Hot' };
}

const REC_STATUS = {
  ideal:     { label: 'Ideal', css: 'ideal' },
  caution:   { label: 'Caution', css: 'caution' },
  dangerous: { label: 'Dangerous', css: 'dangerous' },
  low:       { label: 'Low Flow', css: 'low' },
};

const ACTIVITY_LABELS = {
  kayaking: 'Kayaking',
  tubing: 'Tubing',
};

const CLARITY_CONFIG = {
  clear:    { label: 'Clear', css: 'clear' },
  good:     { label: 'Good', css: 'good' },
  moderate: { label: 'Moderate', css: 'moderate' },
  murky:    { label: 'Murky', css: 'murky' },
  poor:     { label: 'Poor', css: 'poor' },
};

const STATUS_CONFIG = {
  normal:   { label: 'Normal',      css: 'normal' },
  action:   { label: 'Action',      css: 'action' },
  minor:    { label: 'Minor Flood', css: 'minor' },
  moderate: { label: 'Moderate',    css: 'moderate' },
  major:    { label: 'Major Flood', css: 'major' },
};

function formatTimestamp(isoStr) {
  if (!isoStr) return 'No data';
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

function formatNumber(val, decimals = 1) {
  if (val == null) return '\u2014';
  return Number(val).toLocaleString('en-US', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

function FloodStageBar({ gageHeight, stages }) {
  if (!stages || gageHeight == null) return null;

  const maxVal = stages.major * 1.15;
  const pct = (v) => Math.min(100, Math.max(0, (v / maxVal) * 100));

  const currentPct = pct(gageHeight);
  const actionPct = pct(stages.action);
  const minorPct = pct(stages.minor);

  let fillClass = 'stage-bar__fill--normal';
  if (gageHeight >= stages.major) fillClass = 'stage-bar__fill--major';
  else if (gageHeight >= stages.moderate) fillClass = 'stage-bar__fill--moderate';
  else if (gageHeight >= stages.minor) fillClass = 'stage-bar__fill--minor';
  else if (gageHeight >= stages.action) fillClass = 'stage-bar__fill--action';

  return (
    <div className="stage-bar">
      <div className="stage-bar__track">
        <div className="stage-bar__marker stage-bar__marker--action" style={{ left: `${actionPct}%` }} title={`Action: ${stages.action} ft`} />
        <div className="stage-bar__marker stage-bar__marker--minor" style={{ left: `${minorPct}%` }} title={`Minor flood: ${stages.minor} ft`} />
        <div className={`stage-bar__fill ${fillClass}`} style={{ width: `${currentPct}%` }} />
        <div className="stage-bar__current" style={{ left: `${currentPct}%` }} />
      </div>
      <div className="stage-bar__labels">
        <span className="stage-bar__label-left">{formatNumber(gageHeight, 1)} ft</span>
        <span className="stage-bar__label-right">Action {stages.action} &middot; Flood {stages.minor} ft</span>
      </div>
    </div>
  );
}

export default function GaugeCard({ gauge }) {
  const { current, history, flood_status, flood_stages } = gauge;
  const hasData = current && (current.gage_height_ft != null || current.streamflow_cfs != null);
  const statusConf = STATUS_CONFIG[flood_status] || STATUS_CONFIG.normal;
  const isAlert = ['minor', 'moderate', 'major'].includes(flood_status);

  const cardClass = [
    'gauge-card',
    flood_status !== 'normal' ? `gauge-card--${statusConf.css}` : '',
  ].filter(Boolean).join(' ');

  return (
    <div className={cardClass}>
      <div className="gauge-card__header">
        <div>
          <div className="gauge-card__name">{gauge.short_name}</div>
          <div className="gauge-card__description">{gauge.description}</div>
        </div>
        {hasData && flood_stages && (
          <span className={`gauge-card__status-badge badge--${statusConf.css}`}>
            {statusConf.label}
          </span>
        )}
      </div>

      {hasData ? (
        <>
          <div className="gauge-card__readings">
            {current.gage_height_ft != null && (
              <div className="gauge-card__reading">
                <div className="gauge-card__reading-label">Gage Height</div>
                <div className={`gauge-card__reading-value ${isAlert ? 'reading-value--alert' : ''}`}>
                  {formatNumber(current.gage_height_ft, 2)}
                  <span className="gauge-card__reading-unit">ft</span>
                </div>
              </div>
            )}
            {current.streamflow_cfs != null && (
              <div className="gauge-card__reading">
                <div className="gauge-card__reading-label">Streamflow</div>
                <div className="gauge-card__reading-value">
                  {formatNumber(current.streamflow_cfs, 0)}
                  <span className="gauge-card__reading-unit">cfs</span>
                </div>
              </div>
            )}
            {current.water_temp_f != null && (() => {
              const tempStyle = getTempStyle(current.water_temp_f);
              return (
                <div className="gauge-card__reading">
                  <div className="gauge-card__reading-label">Water Temp</div>
                  <div className="gauge-card__reading-value" style={{ color: tempStyle.color }}>
                    {formatNumber(current.water_temp_f, 1)}
                    <span className="gauge-card__reading-unit">&deg;F</span>
                  </div>
                  <div className="gauge-card__temp-context" style={{ color: tempStyle.color }}>
                    {tempStyle.label}
                  </div>
                </div>
              );
            })()}
            {current.water_temp_f == null && gauge.has_temp_sensor && (
              <div className="gauge-card__reading">
                <div className="gauge-card__reading-label">Water Temp</div>
                <div className="gauge-card__reading-value" style={{ color: 'var(--wpr-ink-muted)', fontSize: '0.85rem' }}>
                  Offline
                </div>
              </div>
            )}
          </div>

          <FloodStageBar gageHeight={current.gage_height_ft} stages={flood_stages} />

          {history && history.length >= 2 && (() => {
            const hasFlow = history.some((h) => h.streamflow_cfs != null);
            const sparkKey = hasFlow ? 'streamflow_cfs' : 'gage_height_ft';
            const sparkLabel = hasFlow ? '7-day flow trend' : '7-day gage height trend';
            return (
              <div className="gauge-card__sparkline-wrap">
                <div className="gauge-card__sparkline-label">{sparkLabel}</div>
                <div className="gauge-card__sparkline">
                  <Sparkline data={history} valueKey={sparkKey} />
                </div>
              </div>
            );
          })()}

          {(gauge.recreation || gauge.water_clarity) && (
            <div className="gauge-card__recreation">
              {gauge.water_clarity && (() => {
                const cl = CLARITY_CONFIG[gauge.water_clarity.rating] || CLARITY_CONFIG.moderate;
                return (
                  <span className={`gauge-card__rec-badge gauge-card__rec-badge--${cl.css}`}
                    title={gauge.water_clarity.description}>
                    Clarity: {cl.label}
                  </span>
                );
              })()}
              {gauge.recreation && Object.entries(gauge.recreation).map(([activity, status]) => {
                const conf = REC_STATUS[status] || REC_STATUS.caution;
                return (
                  <span key={activity} className={`gauge-card__rec-badge gauge-card__rec-badge--${conf.css}`}>
                    {ACTIVITY_LABELS[activity] || activity}: {conf.label}
                  </span>
                );
              })}
            </div>
          )}

          <div className="gauge-card__timestamp">
            <span>{formatTimestamp(current.timestamp)}</span>
            <span className="gauge-card__links">
              <a className="gauge-card__usgs-link" href={gauge.usgs_url} target="_blank" rel="noopener noreferrer">USGS</a>
              {gauge.nws_url && (
                <>{' \u00b7 '}<a className="gauge-card__usgs-link" href={gauge.nws_url} target="_blank" rel="noopener noreferrer">NWS</a></>
              )}
            </span>
          </div>
        </>
      ) : (
        <div className="gauge-card__reading gauge-card__reading--na">
          <div className="gauge-card__reading-value" style={{ color: 'var(--wpr-ink-muted)', fontSize: '1rem' }}>No current data</div>
          <div className="gauge-card__timestamp" style={{ marginTop: '0.5rem' }}>
            <span>Gauge may be offline or seasonal</span>
            <a className="gauge-card__usgs-link" href={gauge.usgs_url} target="_blank" rel="noopener noreferrer">USGS &rarr;</a>
          </div>
        </div>
      )}
    </div>
  );
}
