export const DAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
export const ALL_DAYS = [0, 1, 2, 3, 4, 5, 6];
export const WEEKDAYS = [0, 1, 2, 3, 4];
export const WEEKENDS = [5, 6];

const COLORS = ["c1", "c2", "c3", "c4", "c5"];

export function avatarClass(name) {
  let sum = 0;
  for (const char of name) sum += char.charCodeAt(0);
  return COLORS[sum % COLORS.length];
}

export function lateText(minutes) {
  return minutes >= 60
    ? `${Math.floor(minutes / 60)} hours past the grace window`
    : `${minutes} minutes past the grace window`;
}
