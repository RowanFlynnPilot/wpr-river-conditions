// Past this age the readings can't support a status claim either way: a
// green "Normal" over day-old data would stay green straight through a flood.
export const STATUS_UNKNOWN_AFTER_MS = 6 * 60 * 60 * 1000;

export function dataAgeMs(generatedAt) {
  if (!generatedAt) return 0;
  const t = new Date(generatedAt).getTime();
  return Number.isNaN(t) ? 0 : Date.now() - t;
}

export function isStatusUnknown(generatedAt) {
  return dataAgeMs(generatedAt) > STATUS_UNKNOWN_AFTER_MS;
}
