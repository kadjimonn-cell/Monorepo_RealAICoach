import api from './api';

export type PlatformSystemStatus = 'ONLINE' | 'MAINTENANCE' | 'DEGRADED' | 'OUTAGE';

export type PlatformControlState = {
  system_status: PlatformSystemStatus;
  system_status_reason?: string;
  emergency_shutdown: {
    enabled: boolean;
    reason?: string;
    activated_at?: string | null;
    deactivated_at?: string | null;
  };
  maintenance: {
    enabled: boolean;
    title?: string;
    reason?: string;
    starts_at?: string | null;
    ends_at?: string | null;
    allow_staff_read_only: boolean;
    window_id?: string | null;
  };
  feature_toggles: Record<string, boolean>;
  notification_channels: {
    in_app: boolean;
    email: boolean;
    sms: boolean;
    push: boolean;
  };
  announcement?: {
    title?: string;
    message?: string;
    updated_at?: string | null;
  };
  updated_at?: string | null;
  updated_by?: string | null;
};

export async function fetchPlatformControlState() {
  const res = await api.get('/platform-control/admin/state', { silentLoading: true });
  return res.data as { state: PlatformControlState; public_state: Record<string, any> };
}

export async function updateMaintenanceMode(payload: {
  enabled: boolean;
  title?: string;
  reason?: string;
  starts_at?: string | null;
  ends_at?: string | null;
  allow_staff_read_only?: boolean;
  notify_users?: boolean;
  force_replace?: boolean;
}) {
  const res = await api.put('/platform-control/admin/maintenance', payload);
  return res.data;
}

export async function updateEmergencyShutdown(payload: { enabled: boolean; reason?: string; notify_users?: boolean }) {
  const res = await api.put('/platform-control/admin/emergency-shutdown', payload);
  return res.data;
}

export async function updateSystemStatus(payload: { status: PlatformSystemStatus; reason?: string; notify_users?: boolean }) {
  const res = await api.put('/platform-control/admin/system-status', payload);
  return res.data;
}

export async function updateFeatureToggles(feature_toggles: Record<string, boolean>) {
  const res = await api.put('/platform-control/admin/feature-toggles', { feature_toggles });
  return res.data;
}

export async function updateNotificationChannels(payload: { in_app?: boolean; email?: boolean; sms?: boolean; push?: boolean }) {
  const res = await api.put('/platform-control/admin/notification-channels', payload);
  return res.data;
}

export async function sendPlatformBroadcast(payload: { title: string; message: string; audience: 'all_non_admin' | 'all_users' | 'staff_only' }) {
  const res = await api.post('/platform-control/admin/broadcast', payload);
  return res.data;
}

export async function fetchPlatformControlAuditLogs(limit = 50) {
  const res = await api.get(`/platform-control/admin/audit-logs?limit=${encodeURIComponent(String(limit))}`, { silentLoading: true });
  return res.data as { logs: Array<Record<string, any>>; count: number };
}

export async function fetchPlatformControlAuditLogsFiltered(params: {
  limit?: number;
  action?: string;
  actor?: string;
  date_from?: string;
  date_to?: string;
  search?: string;
}) {
  const query = new URLSearchParams();
  query.set('limit', String(params.limit ?? 50));
  if (params.action) query.set('action', params.action);
  if (params.actor) query.set('actor', params.actor);
  if (params.date_from) query.set('date_from', params.date_from);
  if (params.date_to) query.set('date_to', params.date_to);
  if (params.search) query.set('search', params.search);
  const res = await api.get(`/platform-control/admin/audit-logs?${query.toString()}`, { silentLoading: true });
  return res.data as { logs: Array<Record<string, any>>; count: number; filters_applied?: Record<string, any> };
}

export async function exportPlatformControlAuditLogs(format: 'csv' | 'json', params: {
  limit?: number;
  action?: string;
  actor?: string;
  date_from?: string;
  date_to?: string;
  search?: string;
}) {
  const query = new URLSearchParams();
  query.set('format', format);
  query.set('limit', String(params.limit ?? 1000));
  if (params.action) query.set('action', params.action);
  if (params.actor) query.set('actor', params.actor);
  if (params.date_from) query.set('date_from', params.date_from);
  if (params.date_to) query.set('date_to', params.date_to);
  if (params.search) query.set('search', params.search);

  const res = await fetch(`${api.defaults.baseURL}/platform-control/admin/audit-logs/export?${query.toString()}`, {
    method: 'GET',
    headers: {
      Authorization: `Bearer ${localStorage.getItem('session_token') || ''}`,
      'X-Requested-With': 'XMLHttpRequest',
    },
  });

  if (!res.ok) {
    throw new Error(`Export failed with status ${res.status}`);
  }

  const blob = await res.blob();
  return blob;
}

export async function listAnnouncementTemplates(params?: { include_disabled?: boolean; search?: string }) {
  const query = new URLSearchParams();
  query.set('include_disabled', String(params?.include_disabled ?? true));
  if (params?.search) query.set('search', params.search);
  const res = await api.get(`/platform-control/admin/announcement-templates?${query.toString()}`, { silentLoading: true });
  return res.data as { templates: Array<Record<string, any>>; count: number };
}

export async function createAnnouncementTemplate(payload: {
  name: string;
  title: string;
  message: string;
  audience: 'all_non_admin' | 'all_users' | 'staff_only';
  schedule_type: 'one_time' | 'daily' | 'weekly';
  scheduled_for?: string | null;
  daily_time_utc?: string | null;
  weekly_day_utc?: number | null;
  weekly_time_utc?: string | null;
  channels: { in_app: boolean; email: boolean };
  enabled: boolean;
}) {
  const res = await api.post('/platform-control/admin/announcement-templates', payload);
  return res.data;
}

export async function updateAnnouncementTemplate(template_id: string, payload: Record<string, any>) {
  const res = await api.put(`/platform-control/admin/announcement-templates/${encodeURIComponent(template_id)}`, payload);
  return res.data;
}

export async function dispatchAnnouncementTemplate(template_id: string) {
  const res = await api.post(`/platform-control/admin/announcement-templates/${encodeURIComponent(template_id)}/dispatch`, { notify_immediately: true });
  return res.data;
}

export async function disableAnnouncementTemplate(template_id: string) {
  const res = await api.delete(`/platform-control/admin/announcement-templates/${encodeURIComponent(template_id)}`);
  return res.data;
}

export async function fetchSubscriptionPromptTelemetry(hours = 24) {
  const res = await api.get(`/admin/subscription-prompt/telemetry?hours=${encodeURIComponent(String(hours))}`, { silentLoading: true });
  return res.data as {
    hours: number;
    since_iso: string;
    total_events: number;
    unique_sessions: number;
    by_plan: Array<{ plan: string; count: number }>;
    by_source: Array<{ source: string; count: number }>;
    top_endpoints: Array<{ endpoint: string; count: number }>;
    latest_events: Array<Record<string, any>>;
    monitor_state?: Record<string, any> | null;
    monitor_recent_alerts?: Array<Record<string, any>>;
  };
}

export async function fetchPlatformControlPublicState() {
  const res = await api.get('/platform-control/public/state', { silentLoading: true });
  return res.data as Record<string, any>;
}
