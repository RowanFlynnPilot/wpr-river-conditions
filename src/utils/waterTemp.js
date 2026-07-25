// Shared water-temperature banding for display (°F).
// Used by the gauge cards and the fishing panel so the color/label
// language stays identical everywhere a temp appears.
export function tempStyle(tempF) {
  if (tempF < 40) return { color: '#78716c', label: 'Cold' };
  if (tempF < 55) return { color: '#2563eb', label: 'Cool' };
  if (tempF < 70) return { color: '#0d7377', label: 'Moderate' };
  if (tempF < 80) return { color: '#ea580c', label: 'Warm' };
  return { color: '#dc2626', label: 'Hot' };
}
