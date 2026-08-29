import React from 'react';
import Sparkline from './Sparkline';
import GaugeMap from './GaugeMap';
import LureSuggestions from './LureSuggestions';
import { computeTrend, trendText, TREND_ARROWS } from '../utils/trend';
import { tempStyle } from '../utils/waterTemp';

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

// "Today vs. normal" flow comparison, keyed to the USGS WaterWatch percentile class.
const NORMAL_FLOW_CONFIG = {
  much_below: { label: 'Much below normal', css: 'much-below' },
  below:      { label: 'Below normal',      css: 'below' },
  normal:     { label: 'Near normal',       css: 'normal' },
  above:      { label: 'Above normal',      css: 'above' },
  much_above: { label: 'Much above normal', css: 'much-above' },
};

function VsNormal({ normalFlow }) {
  if (!normalFlow || normalFlow.pct_of_median == null) return null;
  const conf = NORMAL_FLOW_CONFIG[normalFlow.class] || NORMAL_FLOW_CONFIG.normal;
  const tip = normalFlow.years
    ? `${normalFlow.years} median for today: ${normalFlow.median_cfs.toLocaleString('en-US')} cfs`
      + (normalFlow.count ? ` (${normalFlow.count} years of record)` : '')
    : undefined;
  return (
    <div className={`gauge-card__vs-normal vs-normal--${conf.css}`} title={tip}>
      <span className="vs-normal__dot" aria-hidden="true" />
      <span className="vs-normal__text">
        {conf.label} · <strong>{normalFlow.pct_of_median}%</strong> of normal flow for today
      </span>
    </div>
  );
}

function formatCrestTime(isoStr) {
  if (!isoStr) return '';
  try {
    const d = new Date(isoStr);
    return d.toLocaleString('en-US', {
      weekday: 'short',
      hour: 'numeric',
      minute: '2-digit',
    });
  } catch {
    return '';
  }
}

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

const TREND_LABELS = { rising: 'Rising', falling: 'Falling', steady: 'Steady' };

export default function GaugeCard({ gauge }) {
  const { current, history, flood_status, flood_stages } = gauge;
  const hasData = current && (current.gage_height_ft != null || current.streamflow_cfs != null);
  const statusConf = STATUS_CONFIG[flood_status] || STATUS_CONFIG.normal;
  const isAlert = ['minor', 'moderate', 'major'].includes(flood_status);
  const trend = computeTrend(history);

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
              const ts = tempStyle(current.water_temp_f);
              const fromWvic = current.water_temp_source === 'wvic';
              const tip = fromWvic
                ? `Daily reading from WVIC (provisional)${current.water_temp_date ? `, ${current.water_temp_date}` : ''}`
                : undefined;
              return (
                <div className="gauge-card__reading" title={tip}>
                  <div className="gauge-card__reading-label">
                    Water Temp{fromWvic ? ' (daily)' : ''}
                  </div>
                  <div className="gauge-card__reading-value" style={{ color: ts.color }}>
                    {formatNumber(current.water_temp_f, 1)}
                    <span className="gauge-card__reading-unit">&deg;F</span>
                  </div>
                  <div className="gauge-card__temp-context" style={{ color: ts.color }}>
                    {ts.label}
                  </div>
                  {fromWvic && (
                    <div className="gauge-card__reading-source">WVIC · provisional</div>
                  )}
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

          {trend && (
            <div className={`gauge-card__trend gauge-card__trend--${trend.dir}`}>
              <span aria-hidden="true">{TREND_ARROWS[trend.dir]}</span>{' '}
              {TREND_LABELS[trend.dir]}
              {trend.dir !== 'steady' && <> · {trendText(trend)}</>}
            </div>
          )}

          {gauge.nwm_forecast?.next24h_pct != null && (() => {
            const f = gauge.nwm_forecast;
            const dir = f.class || 'steady';
            const tip = `NOAA National Water Model flow forecast${
              f.issued ? `, issued ${formatCrestTime(f.issued)}` : ''
            }${f.carried_forward ? ` — latest run available (${f.age_h}h old)` : ''}${
              f.baseline === 'model' ? ' (vs. the model’s own current estimate)' : ''
            }`;
            return (
              <div className={`gauge-card__nwm gauge-card__nwm--${dir}`} title={tip}>
                <span className="gauge-card__nwm-label">Forecast</span>
                <span aria-hidden="true">{TREND_ARROWS[dir]}</span>{' '}
                {(() => {
                  if (dir === 'steady') return 'Holding steady';
                  const horizon = f.horizon_h || 24;
                  // Percentages off a tiny base read as alarming ("+245%" on
                  // a 4 cfs trout stream is a 10 cfs ripple) — show the
                  // absolute target instead on very low flows.
                  const flow = current.streamflow_cfs;
                  const cfsVals = (f.points || []).map((p) => p.cfs).filter((v) => v != null);
                  if (flow != null && flow < 25 && cfsVals.length) {
                    const target = f.next24h_pct > 0 ? Math.max(...cfsVals) : Math.min(...cfsVals);
                    return `to ~${Math.round(target)} cfs next ${horizon}h`;
                  }
                  return `${f.next24h_pct > 0 ? '+' : ''}${f.next24h_pct}% next ${horizon}h`;
                })()}
                {f.carried_forward && (
                  <span className="gauge-card__nwm-age"> · model run {f.age_h}h old</span>
                )}
              </div>
            );
          })()}

          {gauge.upstream_rain?.inches >= 0.1 && (
            <div
              className={`gauge-card__rain${gauge.upstream_rain.inches >= 0.75 ? ' gauge-card__rain--heavy' : ''}`}
              title={`24-hour rainfall forecast for the ${gauge.upstream_rain.label}, upstream of this gauge`}
            >
              <span aria-hidden="true">🌧️</span> {gauge.upstream_rain.inches.toFixed(2)} in
              forecast upstream (24h)
            </div>
          )}

          {current.precip_24h_in != null && current.precip_24h_in > 0 && (
            <div className="gauge-card__precip">
              <span aria-hidden="true">💧</span> Last 24h precip:{' '}
              <span className="gauge-card__precip-value">
                {formatNumber(current.precip_24h_in, 2)} in
              </span>
            </div>
          )}

          <VsNormal normalFlow={gauge.normal_flow} />

          <FloodStageBar gageHeight={current.gage_height_ft} stages={flood_stages} />

          {gauge.nws_forecast && (
            <div className="gauge-card__forecast">
              <span className="gauge-card__forecast-label">NWS Forecast</span>
              <span className="gauge-card__forecast-value">
                Crest {formatNumber(gauge.nws_forecast.peak_stage, 1)}{' '}
                {gauge.nws_forecast.units || 'ft'}
              </span>
              {gauge.nws_forecast.peak_time && (
                <span className="gauge-card__forecast-time">
                  {formatCrestTime(gauge.nws_forecast.peak_time)}
                </span>
              )}
            </div>
          )}

          {history && history.length >= 2 && (() => {
            const hasFlow = history.some((h) => h.streamflow_cfs != null);
            const sparkKey = hasFlow ? 'streamflow_cfs' : 'gage_height_ft';
            const vals = history.map((h) => h[sparkKey]).filter((v) => v != null);
            if (vals.length < 2) return null;
            // NWM forecast tail (flow plots only — the forecast is cfs).
            const fcst = hasFlow
              ? (gauge.nwm_forecast?.points || []).map((p) => p.cfs)
              : [];
            const sparkLabel = hasFlow
              ? (fcst.length ? '7-day flow + 3-day outlook' : '7-day flow trend')
              : '7-day gage height trend';
            const lo = Math.min(...vals, ...(fcst.length ? fcst : [Infinity]));
            const hi = Math.max(...vals, ...(fcst.length ? fcst : [-Infinity]));
            const fmtV = (v) =>
              hasFlow ? Math.round(v).toLocaleString('en-US') : v.toFixed(1);
            // Dashed action-stage reference line (stage plots only — flow
            // plots can't share the ft-based threshold axis).
            const refValue = !hasFlow && flood_stages ? flood_stages.action : null;
            return (
              <div className="gauge-card__sparkline-wrap">
                <div className="gauge-card__sparkline-label">
                  <span>{sparkLabel}</span>
                  <span className="gauge-card__sparkline-range">
                    {fmtV(lo)}–{fmtV(hi)} {hasFlow ? 'cfs' : 'ft'}
                  </span>
                </div>
                <div className="gauge-card__sparkline">
                  <Sparkline
                    data={history}
                    valueKey={sparkKey}
                    refValue={refValue}
                    forecast={fcst}
                  />
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

          {gauge.current_lures && gauge.current_lures.length > 0 && (
            <LureSuggestions lures={gauge.current_lures} />
          )}

          <GaugeMap gauge={gauge} />

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
          {gauge.nwm_forecast?.next24h_pct != null && (
            <div className={`gauge-card__nwm gauge-card__nwm--${gauge.nwm_forecast.class || 'steady'}`}
              title="NOAA National Water Model estimate — no live gauge here">
              <span className="gauge-card__nwm-label">Model</span>
              <span aria-hidden="true">{TREND_ARROWS[gauge.nwm_forecast.class || 'steady']}</span>{' '}
              {gauge.nwm_forecast.class === 'steady'
                ? 'Holding steady'
                : `${gauge.nwm_forecast.next24h_pct > 0 ? '+' : ''}${gauge.nwm_forecast.next24h_pct}% next ${gauge.nwm_forecast.horizon_h || 24}h`}
            </div>
          )}
          <div className="gauge-card__timestamp" style={{ marginTop: '0.5rem' }}>
            <span>
              {gauge.discontinued
                ? 'USGS discontinued real-time reporting at this site'
                : 'Gauge may be offline or seasonal'}
            </span>
            <a className="gauge-card__usgs-link" href={gauge.usgs_url} target="_blank" rel="noopener noreferrer">USGS &rarr;</a>
          </div>
        </div>
      )}
    </div>
  );
}
