type MinimalTokens = { text3: string; error: string; warning: string; cyan: string; success: string };
const DARK_FALLBACK: MinimalTokens = { text3: '#64748B', error: '#EF4444', warning: '#F59E0B', cyan: '#14B8A6', success: '#10B981' };

export const getStrength = (pw: string, T?: MinimalTokens): { score: number; label: string; color: string } => {
  const t = T || DARK_FALLBACK;
  if (!pw) return { score: 0, label: '', color: t.text3 };
  let s = 0;
  if (pw.length >= 6) s++;
  if (pw.length >= 10) s++;
  if (/[A-Z]/.test(pw)) s++;
  if (/[0-9]/.test(pw)) s++;
  if (/[^A-Za-z0-9]/.test(pw)) s++;
  if (s <= 1) return { score: 1, label: 'Weak', color: t.error };
  if (s <= 2) return { score: 2, label: 'Fair', color: t.warningText };
  if (s <= 3) return { score: 3, label: 'Good', color: t.cyan };
  return { score: 4, label: 'Strong', color: t.successText };
};
