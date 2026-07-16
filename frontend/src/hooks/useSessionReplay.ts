import { useEffect, useRef, useCallback } from 'react';
import { Platform } from 'react-native';
import api from '../services/api';
import { resolveRuntimeBaseUrl } from '../utils/runtimeBaseUrl';
import { handleAppRecoverableError } from '../utils/appRecoverableError';

const BATCH_SIZE = 50;
const FLUSH_INTERVAL = 30000;

function genId(): string {
  return `rs_${Date.now()}_${Math.random().toString(36).substring(2, 10)}`;
}

function postSessionReplayKeepalive(payload: Record<string, any>) {
  const base = resolveRuntimeBaseUrl();
  const token = Platform.OS === 'web' && typeof window !== 'undefined'
    ? (window.localStorage.getItem('session_token') || window.localStorage.getItem('auth_token') || '')
    : '';
  const suffix = token ? `?token=${encodeURIComponent(token)}` : '';
  const url = base ? `${base}/api/admin/session-replay/record${suffix}` : `/api/admin/session-replay/record${suffix}`;
  try {
    if (Platform.OS === 'web' && typeof navigator !== 'undefined' && typeof navigator.sendBeacon === 'function') {
      navigator.sendBeacon(url, JSON.stringify(payload));
      return true;
    }
  } catch (error) { handleAppRecoverableError({ scope: 'src/hooks/useSessionReplay.ts#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
  return false;
}

export function useSessionReplay(userId?: string, userEmail?: string) {
  const sessionId = useRef<string>(genId());
  const eventBuffer = useRef<any[]>([]);
  const flushTimer = useRef<any>(null);
  const enabled = Boolean(userId);

  const flush = useCallback(async () => {
    if (!enabled) return;
    if (eventBuffer.current.length === 0) return;
    const events = [...eventBuffer.current];
    eventBuffer.current = [];
    try {
      if (postSessionReplayKeepalive({ session_id: sessionId.current, events })) {
        return;
      }
      await api.post('/admin/session-replay/record', {
        session_id: sessionId.current,
        events,
      });
    } catch {
      eventBuffer.current = [...events, ...eventBuffer.current].slice(0, 200);
    }
  }, [enabled]);

  const record = useCallback((type: string, data: Record<string, any> = {}) => {
    if (!enabled) return;
    eventBuffer.current.push({
      type,
      data,
      timestamp: new Date().toISOString(),
    });
    if (eventBuffer.current.length >= BATCH_SIZE) flush();
  }, [enabled, flush]);

  useEffect(() => {
    if (Platform.OS !== 'web') return;
    if (!enabled) {
      eventBuffer.current = [];
      return;
    }

    flushTimer.current = setInterval(flush, FLUSH_INTERVAL);

    const handleClick = (e: MouseEvent) => {
      const t = e.target as HTMLElement;
      const testId = t?.getAttribute?.('data-testid') || '';
      const tag = t?.tagName || '';
      const text = (t?.textContent || '').substring(0, 50);
      record('click', {
        target: testId || `${tag.toLowerCase()}:${text}`,
        url: window.location.pathname,
        x: e.clientX,
        y: e.clientY,
      });
    };

    const handlePopState = () => {
      record('navigate', { url: window.location.pathname });
    };

    let scrollTimeout: any = null;
    const handleScroll = () => {
      if (scrollTimeout) return;
      scrollTimeout = setTimeout(() => {
        record('scroll', { url: window.location.pathname, y: window.scrollY });
        scrollTimeout = null;
      }, 1000);
    };

    const handleVisibility = () => {
      record('visibility', { state: document.visibilityState });
    };

    document.addEventListener('click', handleClick, { passive: true });
    window.addEventListener('popstate', handlePopState);
    window.addEventListener('scroll', handleScroll, { passive: true });
    document.addEventListener('visibilitychange', handleVisibility);
    window.addEventListener('beforeunload', () => {
      const events = [...eventBuffer.current];
      eventBuffer.current = [];
      if (events.length > 0) {
        postSessionReplayKeepalive({ session_id: sessionId.current, events });
      }
    });

    record('session_start', { url: window.location.pathname });

    return () => {
      const events = [...eventBuffer.current];
      eventBuffer.current = [];
      if (events.length > 0) {
        postSessionReplayKeepalive({ session_id: sessionId.current, events });
      }
      clearInterval(flushTimer.current);
      document.removeEventListener('click', handleClick);
      window.removeEventListener('popstate', handlePopState);
      window.removeEventListener('scroll', handleScroll);
      document.removeEventListener('visibilitychange', handleVisibility);
    };
  }, [enabled, flush, record]);

  useEffect(() => {
    if (enabled && userId) {
      const endPrev = async () => {
        try { await api.post('/admin/session-replay/end', { session_id: sessionId.current }); } catch (error) { handleAppRecoverableError({ scope: 'src/hooks/useSessionReplay.ts#catch2', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
      };
      endPrev();
      sessionId.current = genId();
      record('session_start', { url: Platform.OS === 'web' ? window.location.pathname : '' });
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [userId]);

  const endSession = useCallback(async () => {
    if (!enabled) return;
    await flush();
    try { await api.post('/admin/session-replay/end', { session_id: sessionId.current }); } catch (error) { handleAppRecoverableError({ scope: 'src/hooks/useSessionReplay.ts#catch3', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
  }, [enabled, flush]);

  return { record, endSession, sessionId };
}
