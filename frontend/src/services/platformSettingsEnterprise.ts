import api from './api';

const withAuthHeaders = () => {
  const token = typeof window !== 'undefined' && window.localStorage
    ? window.localStorage.getItem('session_token') || ''
    : '';
  return {
    Authorization: `Bearer ${token}`,
  'X-Requested-With': 'XMLHttpRequest',
  };
};

export const fetchPlatformStatusBundle = async () => {
  const [
    control,
    systemStatus,
    instanceMarker,
    systemHealth,
    systemMetrics,
    observability,
    liveServices,
    enterpriseStandard,
    parityAudit,
  ] = await Promise.allSettled([
    api.get('/platform-control/admin/state', { silentLoading: true }),
    api.get('/system/status', { silentLoading: true }),
    api.get('/system/instance-marker', { silentLoading: true }),
    api.get('/system/health/detailed', { silentLoading: true }),
    api.get('/admin/system/metrics', { silentLoading: true }),
    api.get('/admin/observability/overview', { silentLoading: true }),
    api.get('/admin/platform-health/live-services', { silentLoading: true }),
    api.get('/admin/platform-health/enterprise-standard/status', { silentLoading: true }),
    api.get('/admin/platform-health/global-parity-audit/latest', { silentLoading: true }),
  ]);

  const [
    securitySummary,
    securityTimeline,
    securityRecent,
    securityAlertConfig,
    notificationRules,
    featureFlags,
    announcements,
    templates,
    auditLogs,
    legalBroadcasts,
    securityBroadcasts,
    previewAdapterCheck,
  ] = await Promise.allSettled([
    api.get('/admin/security-incidents/summary?hours=24', { silentLoading: true }),
    api.get('/admin/security-incidents/timeline?hours=24', { silentLoading: true }),
    api.get('/admin/security-incidents/recent?limit=30', { silentLoading: true }),
    api.get('/admin/security-incidents/alert-config', { silentLoading: true }),
    api.get('/admin/notification-rules', { silentLoading: true }),
    api.get('/admin/feature-flags', { silentLoading: true }),
    api.get('/admin/announcements', { silentLoading: true }),
    api.get('/platform-control/admin/announcement-templates?include_disabled=true', { silentLoading: true }),
    api.get('/platform-control/admin/audit-logs?limit=120', { silentLoading: true }),
    api.get('/admin/legal-notice/broadcasts?limit=40', { silentLoading: true }),
    api.get('/admin/security-incident/broadcasts?limit=40', { silentLoading: true }),
    api.get('/admin/platform-health/preview-adapter-live-check', { silentLoading: true }),
  ]);

  return {
    control,
    systemStatus,
    instanceMarker,
    systemHealth,
    systemMetrics,
    observability,
    liveServices,
    enterpriseStandard,
    parityAudit,
    securitySummary,
    securityTimeline,
    securityRecent,
    securityAlertConfig,
    notificationRules,
    featureFlags,
    announcements,
    templates,
    auditLogs,
    legalBroadcasts,
    securityBroadcasts,
    previewAdapterCheck,
  };
};

export const saveSystemStatus = async (payload: { status: 'ONLINE' | 'MAINTENANCE' | 'DEGRADED' | 'OUTAGE'; reason?: string; notify_users?: boolean }) => {
  const res = await api.put('/platform-control/admin/system-status', payload);
  return res.data;
};

export const saveMaintenanceWindow = async (payload: {
  enabled: boolean;
  title?: string;
  reason?: string;
  starts_at?: string | null;
  ends_at?: string | null;
  allow_staff_read_only?: boolean;
  notify_users?: boolean;
  force_replace?: boolean;
}) => {
  const res = await api.put('/platform-control/admin/maintenance', payload);
  return res.data;
};

export const saveFeatureToggles = async (feature_toggles: Record<string, boolean>) => {
  const res = await api.put('/platform-control/admin/feature-toggles', { feature_toggles });
  return res.data;
};

export const saveNotificationChannels = async (payload: { in_app?: boolean; email?: boolean; sms?: boolean; push?: boolean }) => {
  const res = await api.put('/platform-control/admin/notification-channels', payload);
  return res.data;
};

export const sendPlatformBroadcastNow = async (payload: { title: string; message: string; audience: 'all_non_admin' | 'all_users' | 'staff_only' }) => {
  const res = await api.post('/platform-control/admin/broadcast', payload);
  return res.data;
};

export const createTemplate = async (payload: {
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
}) => {
  const res = await api.post('/platform-control/admin/announcement-templates', payload);
  return res.data;
};

export const dispatchTemplateNow = async (templateId: string) => {
  const res = await api.post(`/platform-control/admin/announcement-templates/${encodeURIComponent(templateId)}/dispatch`, {
    notify_immediately: true,
  });
  return res.data;
};

export const disableTemplateNow = async (templateId: string) => {
  const res = await api.delete(`/platform-control/admin/announcement-templates/${encodeURIComponent(templateId)}`);
  return res.data;
};

export const createAnnouncement = async (payload: {
  title: string;
  message: string;
  priority: string;
  audience: string;
}) => {
  const res = await api.post('/admin/announcements', payload);
  return res.data;
};

export const deleteAnnouncement = async (id: string) => {
  const res = await api.delete(`/admin/announcements/${encodeURIComponent(id)}`);
  return res.data;
};

export const saveFeatureFlag = async (payload: { key: string; enabled: boolean; description?: string }) => {
  const res = await api.post('/admin/feature-flags', payload);
  return res.data;
};

export const createNotificationRule = async (payload: {
  name: string;
  condition: { metric: string; operator: string; threshold: number; time_window_minutes: number };
  severity: string;
  cooldown_minutes: number;
  enabled: boolean;
}) => {
  const res = await api.post('/admin/notification-rules', payload);
  return res.data;
};

export const toggleNotificationRule = async (ruleId: string) => {
  const res = await api.put(`/admin/notification-rules/${encodeURIComponent(ruleId)}/toggle`, {});
  return res.data;
};

export const deleteNotificationRule = async (ruleId: string) => {
  const res = await api.delete(`/admin/notification-rules/${encodeURIComponent(ruleId)}`);
  return res.data;
};

export const testNotificationRule = async (ruleId: string) => {
  const res = await api.post(`/admin/notification-rules/test/${encodeURIComponent(ruleId)}`, {});
  return res.data;
};

export const saveSecurityAlertConfig = async (payload: {
  enabled?: boolean;
  threshold?: number;
  window_minutes?: number;
  cooldown_minutes?: number;
  email_enabled?: boolean;
}) => {
  const res = await api.put('/admin/security-incidents/alert-config', payload);
  return res.data;
};

export const runSecurityAlertTest = async () => {
  const res = await api.post('/admin/security-incidents/alert-test', {});
  return res.data;
};

export const runParityAudit = async () => {
  const res = await api.post('/admin/platform-health/global-parity-audit/run?run_admin_checks=true&triggered_by=manual:platform-settings', {});
  return res.data;
};

export const acknowledgeParityIncident = async (incidentId: string) => {
  const res = await api.post(`/admin/platform-health/global-parity-audit/incidents/${encodeURIComponent(incidentId)}/ack`, {});
  return res.data;
};

export const resolveParityIncident = async (incidentId: string, note: string) => {
  const res = await api.post(`/admin/platform-health/global-parity-audit/incidents/${encodeURIComponent(incidentId)}/resolve`, null, {
    params: { note },
  });
  return res.data;
};

export const exportAuditLogs = async (format: 'csv' | 'json') => {
  const res = await fetch(
    `${api.defaults.baseURL}/platform-control/admin/audit-logs/export?format=${encodeURIComponent(format)}&limit=2000`,
    {
      method: 'GET',
      headers: withAuthHeaders(),
    },
  );
  if (!res.ok) {
    throw new Error(`Export failed (${res.status})`);
  }
  return await res.blob();
};