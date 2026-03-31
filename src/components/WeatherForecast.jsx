import React from 'react';

function getWeatherIcon(code) {
  if (code === 0) return '\u2600\uFE0F';
  if (code <= 2) return '\u26C5';
  if (code === 3) return '\u2601\uFE0F';
  if (code === 45 || code === 48) return '\uD83C\uDF2B\uFE0F';
  if (code >= 51 && code <= 57) return '\uD83C\uDF26\uFE0F';
  if (code >= 61 && code <= 67) return '\uD83C\uDF27\uFE0F';
  if (code >= 71 && code <= 77) return '\uD83C\uDF28\uFE0F';
  if (code >= 80 && code <= 82) return '\uD83C\uDF27\uFE0F';
  if (code >= 85 && code <= 86) return '\uD83C\uDF28\uFE0F';
  if (code >= 95) return '\u26C8\uFE0F';
  return '\u2601\uFE0F';
}

function getWeatherLabel(code) {
  if (code === 0) return 'Clear';
  if (code === 1) return 'Mostly Clear';
  if (code === 2) return 'Partly Cloudy';
  if (code === 3) return 'Overcast';
  if (code === 45 || code === 48) return 'Fog';
  if (code >= 51 && code <= 57) return 'Drizzle';
  if (code >= 61 && code <= 65) return 'Rain';
  if (code === 66 || code === 67) return 'Freezing Rain';
  if (code >= 71 && code <= 77) return 'Snow';
  if (code >= 80 && code <= 82) return 'Showers';
  if (code >= 85 && code <= 86) return 'Snow Showers';
  if (code >= 95) return 'Thunderstorm';
  return 'Cloudy';
}

function formatDayName(dateStr, index) {
  if (index === 0) return 'Today';
  const d = new Date(dateStr + 'T12:00:00');
  return d.toLocaleDateString('en-US', { weekday: 'short' });
}

export default function WeatherForecast({ forecast }) {
  if (!forecast || forecast.length === 0) return null;

  return (
    <div className="weather-strip">
      <div className="weather-strip__grid">
        {forecast.map((day, i) => (
          <div key={day.date} className="weather-strip__day">
            <div className="weather-strip__day-name">{formatDayName(day.date, i)}</div>
            <div className="weather-strip__icon">{getWeatherIcon(day.weather_code)}</div>
            <div className="weather-strip__label">{getWeatherLabel(day.weather_code)}</div>
            <div className="weather-strip__temps">
              <span className="weather-strip__high">{day.high_f}°</span>
              <span className="weather-strip__low">{day.low_f}°</span>
            </div>
            {day.precip_pct > 0 && (
              <div className="weather-strip__precip">
                {'\uD83D\uDCA7'} {day.precip_pct}%
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
