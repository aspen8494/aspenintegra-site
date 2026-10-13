/** Format a date as e.g. "October 13, 2026" */
export function formatDate(date: Date): string {
  return date.toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
  });
}

/** Format a date compactly as e.g. "2026-10-13" */
export function formatDateISO(date: Date): string {
  return date.toISOString().slice(0, 10);
}
