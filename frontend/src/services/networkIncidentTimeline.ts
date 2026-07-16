import { handleAppRecoverableError } from '../utils/appRecoverableError';
const STORAGE_KEY = 'shell_network_incidents_v1';
const MAX_INCIDENTS = 120;

function canUseStorage() {
  return typeof window !== 'undefined' && typeof window.localStorage !== 'undefined';
}

function readIncidents() {
  if (!canUseStorage()) return [];
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    const parsed = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function writeIncidents(items) {
  if (!canUseStorage()) return;
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(items.slice(0, MAX_INCIDENTS)));
  } catch (error) { handleAppRecoverableError({ scope: 'src/services/networkIncidentTimeline.ts#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
}

export function recordNetworkIncident(type, detail = {}) {
  const incident = {
    id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    type,
    detail,
    timestamp: new Date().toISOString(),
  };

  const next = [incident, ...readIncidents()].slice(0, MAX_INCIDENTS);
  writeIncidents(next);

  if (typeof window !== 'undefined') {
    try {
      window.dispatchEvent(new CustomEvent('app-network-incident', { detail: incident }));
    } catch (error) { handleAppRecoverableError({ scope: 'src/services/networkIncidentTimeline.ts#catch2', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
  }

  return incident;
}

export function getNetworkIncidents(limit = 20) {
  return readIncidents().slice(0, Math.max(1, limit));
}

export function subscribeNetworkIncidents(listener) {
  if (typeof window === 'undefined') return () => {};

  const handler = (event) => {
    listener(event?.detail || null);
  };
  window.addEventListener('app-network-incident', handler);

  return () => {
    window.removeEventListener('app-network-incident', handler);
  };
}
