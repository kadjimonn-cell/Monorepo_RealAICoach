export const DAYS_SHORT = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
export const MONTHS = ['January','February','March','April','May','June','July','August','September','October','November','December'];

export const EVENT_CATEGORIES: Record<string, { label: string; icon: string; color: string }> = {
  meeting: { label: 'Meeting', icon: 'people', color: '#0F766E' },
  personal: { label: 'Personal', icon: 'person', color: '#14B8A6' },
  work: { label: 'Work', icon: 'briefcase', color: '#F59E0B' },
  reminder: { label: 'Reminder', icon: 'alarm', color: '#EF4444' },
  health: { label: 'Health', icon: 'fitness', color: '#10B981' },
  social: { label: 'Social', icon: 'chatbubbles', color: '#EC4899' },
};

export const RECURRENCE_OPTIONS = [
  { key: 'none', label: 'No repeat', icon: 'close-circle-outline' },
  { key: 'daily', label: 'Daily', icon: 'today' },
  { key: 'weekly', label: 'Weekly', icon: 'calendar' },
  { key: 'monthly', label: 'Monthly', icon: 'calendar-outline' },
];

export const REMINDER_OPTIONS = [
  { key: 0, label: 'None', icon: 'notifications-off-outline' },
  { key: 5, label: '5 min', icon: 'notifications' },
  { key: 15, label: '15 min', icon: 'notifications' },
  { key: 30, label: '30 min', icon: 'notifications' },
  { key: 60, label: '1 hour', icon: 'time' },
  { key: 1440, label: '1 day', icon: 'calendar' },
];

export const HOURS = Array.from({ length: 24 }, (_, i) => i);
export const MINUTES_OPTIONS = ['00', '15', '30', '45'];

export type ViewMode = 'day' | 'week' | 'month';

export const pad = (n: number) => n.toString().padStart(2, '0');
export const isSameDay = (a: Date, b: Date) => a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();
export const fmtTime = (s: string) => { try { return new Date(s).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' }); } catch { return s; } };
export const fmtDateShort = (d: Date) => `${MONTHS[d.getMonth()].slice(0, 3)} ${d.getDate()}, ${d.getFullYear()}`;
export const getCatMeta = (cat: string) => EVENT_CATEGORIES[cat] || EVENT_CATEGORIES.meeting;

export function getMonthDays(year: number, month: number) {
  const first = new Date(year, month, 1);
  const last = new Date(year, month + 1, 0);
  const days: (Date | null)[] = [];
  for (let i = 0; i < first.getDay(); i++) days.push(null);
  for (let d = 1; d <= last.getDate(); d++) days.push(new Date(year, month, d));
  return days;
}

export function getWeekDays(date: Date) {
  const start = new Date(date);
  start.setDate(start.getDate() - start.getDay());
  return Array.from({ length: 7 }, (_, i) => {
    const d = new Date(start);
    d.setDate(d.getDate() + i);
    return d;
  });
}
