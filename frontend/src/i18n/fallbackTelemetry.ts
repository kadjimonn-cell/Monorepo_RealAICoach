import api from '../services/api';

const sentFallbackHits = new Set<string>();
const pendingFallbackHits: { language: string; key: string; route: string; source: string }[] = [];
let flushTimer: ReturnType<typeof setTimeout> | null = null;

const getCurrentRoute = () => {
  if (typeof window === 'undefined') return 'native';
  return `${window.location.pathname || '/'}${window.location.search || ''}`;
};

const flushFallbackHits = () => {
  if (!pendingFallbackHits.length) return;
  const hits = pendingFallbackHits.splice(0, 25);
  api.post('/i18n/fallback-hit/batch', {
    hits,
  }, { silentLoading: true }).catch(() => {});
};

const scheduleFlush = () => {
  if (flushTimer) clearTimeout(flushTimer);
  flushTimer = setTimeout(() => {
    flushTimer = null;
    flushFallbackHits();
  }, 1200);
};

export const trackTranslationFallbackHit = (language: string, key: string) => {
  if (!language || language === 'en' || !key) return;
  const route = getCurrentRoute();
  const dedupeKey = `${language}:${key}:${route}`;
  if (sentFallbackHits.has(dedupeKey)) return;
  sentFallbackHits.add(dedupeKey);

  pendingFallbackHits.push({
    language,
    key,
    route,
    source: 'runtime_fallback',
  });

  if (pendingFallbackHits.length >= 10) {
    if (flushTimer) {
      clearTimeout(flushTimer);
      flushTimer = null;
    }
    flushFallbackHits();
    return;
  }

  scheduleFlush();
};