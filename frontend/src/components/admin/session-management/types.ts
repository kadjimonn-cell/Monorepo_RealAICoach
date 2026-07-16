export type Tab = 'security' | 'sessions' | 'suspicious' | 'policies' | 'alerts' | 'map' | 'blocklist';
export type ConfirmAction = { type: string; target: string; label: string } | null;

export const RISK_COLORS: Record<string, { bg: string; text: string; icon: string }> = {
  critical: { bg: '#EF444420', text: '#EF4444', icon: 'skull' }, // @theme-ok brand/role/state identifier
  high: { bg: '#F9731620', text: '#F97316', icon: 'alert-circle' }, // @theme-ok brand/role/state identifier
  medium: { bg: '#EAB30820', text: '#EAB308', icon: 'warning' }, // @theme-ok brand/role/state identifier
  low: { bg: '#0F766E20', text: '#0F766E', icon: 'information-circle' }, // @theme-ok brand/role/state identifier
};

export const FLAG_ICONS: Record<string, string> = {
  multi_ip: 'globe', rapid_creation: 'flash', excessive_sessions: 'layers',
  tor_exit: 'skull', datacenter_ip: 'server', suspicious_ua: 'bug', impossible_travel: 'airplane',
};

export const fmtDate = (d: string) => {
  if (!d) return '-';
  try { return new Date(d).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }); }
  catch { return d; }
};

export const parseUA = (ua: string) => {
  if (!ua || ua === 'N/A') return 'Unknown';
  if (ua.includes('Chrome')) return 'Chrome';
  if (ua.includes('Firefox')) return 'Firefox';
  if (ua.includes('Safari')) return 'Safari';
  if (ua.includes('curl')) return 'API/CLI';
  return ua.slice(0, 30);
};
