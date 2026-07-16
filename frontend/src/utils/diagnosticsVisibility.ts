export const DIAGNOSTICS_BANNERS_STORAGE_KEY = 'ops:show-diagnostics-banners';

export function shouldShowDiagnosticsBanners(): boolean {
  if (typeof window === 'undefined') return false;
  try {
    return window.localStorage.getItem(DIAGNOSTICS_BANNERS_STORAGE_KEY) === '1';
  } catch {
    return false;
  }
}
