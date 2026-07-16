import { resolveRuntimeBaseUrl } from './runtimeBaseUrl';

const API_BASE = resolveRuntimeBaseUrl();

type CareersTelemetryPayload = {
  event: string;
  source?: string;
  page?: string;
  ref?: string;
  job_slug?: string;
  metadata?: Record<string, any>;
};

export async function trackCareersEvent(payload: CareersTelemetryPayload): Promise<void> {
  const event = String(payload?.event || '').trim();
  if (!event) return;

  try {
    const params = new URLSearchParams();
    params.set('event', event);
    if (payload?.source) params.set('source', payload.source);
    if (payload?.page) params.set('page', payload.page);
    if (payload?.ref) params.set('ref', payload.ref);
    if (payload?.job_slug) params.set('job_slug', payload.job_slug);

    await fetch(`${API_BASE}/api/careers/telemetry?${params.toString()}`, {
      method: 'GET',
      headers: { 'X-Requested-With': 'XMLHttpRequest' },
      keepalive: true,
    });
  } catch {
    // best-effort telemetry only
  }
}
