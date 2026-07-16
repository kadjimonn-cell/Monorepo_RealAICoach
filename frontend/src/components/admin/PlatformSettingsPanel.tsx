import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  ActivityIndicator,
  ScrollView,
  StyleSheet,
  Switch,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import { useExecTheme } from './ExecDashboardPanels';
import { useAdminTheme } from '../../hooks/useAdminTheme';
import { useTranslation } from '../../hooks/useTranslation';
import {
  createAnnouncementTemplate,
  disableAnnouncementTemplate,
  dispatchAnnouncementTemplate,
  exportPlatformControlAuditLogs,
  fetchPlatformControlAuditLogs,
  fetchPlatformControlAuditLogsFiltered,
  fetchSubscriptionPromptTelemetry,
  fetchPlatformControlState,
  listAnnouncementTemplates,
  PlatformControlState,
  PlatformSystemStatus,
  sendPlatformBroadcast,
  updateAnnouncementTemplate,
  updateEmergencyShutdown,
  updateFeatureToggles,
  updateMaintenanceMode,
  updateNotificationChannels,
  updateSystemStatus,
} from '../../services/platformControl';

const SYSTEM_STATUS_OPTIONS: PlatformSystemStatus[] = ['ONLINE', 'MAINTENANCE', 'DEGRADED', 'OUTAGE'];

const FEATURE_LABELS: Record<string, string> = {
  ai_modules: 'AI Modules',
  payments: 'Payments',
  tools: 'Tools & Utilities',
  experimental: 'Experimental Features',
};

const AUDIENCE_OPTIONS: Array<{ id: 'all_non_admin' | 'all_users' | 'staff_only'; label: string }> = [
  { id: 'all_non_admin', label: 'All non-admin users' },
  { id: 'all_users', label: 'All users' },
  { id: 'staff_only', label: 'Staff only' },
];

const SCHEDULE_OPTIONS = [
  { id: 'one_time', label: 'One-time' },
  { id: 'daily', label: 'Daily' },
  { id: 'weekly', label: 'Weekly' },
] as const;

const createEmptyState = (): PlatformControlState => ({
  system_status: 'ONLINE',
  system_status_reason: '',
  emergency_shutdown: {
    enabled: false,
    reason: '',
    activated_at: null,
    deactivated_at: null,
  },
  maintenance: {
    enabled: false,
    title: 'Scheduled Platform Maintenance',
    reason: '',
    starts_at: null,
    ends_at: null,
    allow_staff_read_only: true,
    window_id: null,
  },
  feature_toggles: {
    ai_modules: true,
    payments: true,
    tools: true,
    experimental: true,
  },
  notification_channels: {
    in_app: true,
    email: true,
    sms: false,
    push: false,
  },
  announcement: { title: '', message: '', updated_at: null },
  updated_at: null,
  updated_by: null,
});

const formatDateTime = (value?: string | null) => {
  if (!value) return '—';
  try {
    return new Date(value).toLocaleString();
  } catch {
    return String(value);
  }
};

const normalizeDetailError = (error: any, fallback: string) => {
  const detail = error?.response?.data?.detail;
  if (typeof detail === 'string') return detail;
  if (detail?.message) return String(detail.message);
  return error?.message || fallback;
};

const jsonEqual = (a: any, b: any) => JSON.stringify(a) === JSON.stringify(b);

export default function PlatformSettingsPanel() {
  const colors = useAdminTheme();
  const T = useExecTheme();
  const { t } = useTranslation();
  const tx = useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);

  const styles = StyleSheet.create({
    screen: { flex: 1, backgroundColor: 'transparent' },
    content: { padding: 16, paddingBottom: 40, gap: 14 },
    loaderWrap: { padding: 40, alignItems: 'center', gap: 10 },
    loaderText: { color: T.textMuted, fontSize: 12 },
    card: {
      backgroundColor: T.card,
      borderRadius: 18,
      borderWidth: 1,
      borderColor: T.border,
      padding: 16,
      gap: 12,
    },
    row: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8, flexWrap: 'wrap' },
    title: { color: T.text, fontSize: 24, fontWeight: '800' },
    subtitle: { color: T.textSec, fontSize: 13, lineHeight: 20 },
    badge: {
      borderRadius: 999,
      borderWidth: 1,
      borderColor: T.border,
      backgroundColor: T.bgSoft,
      paddingHorizontal: 10,
      paddingVertical: 6,
    },
    badgeText: { color: T.textMuted, fontSize: 11, fontWeight: '700' },
    statusBanner: {
      borderRadius: 12,
      borderWidth: 1,
      paddingHorizontal: 12,
      paddingVertical: 10,
      flexDirection: 'row',
      alignItems: 'center',
      gap: 8,
    },
    statusText: { color: T.text, fontSize: 12, fontWeight: '600', flex: 1 },
    sectionTitle: { color: T.text, fontSize: 16, fontWeight: '800' },
    sectionHint: { color: T.textMuted, fontSize: 12, lineHeight: 18 },
    buttonRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
    actionButton: {
      borderRadius: 999,
      borderWidth: 1,
      borderColor: T.border,
      paddingHorizontal: 12,
      paddingVertical: 9,
      backgroundColor: T.bgSoft,
    },
    actionButtonActive: { borderColor: T.primary, backgroundColor: `${T.primary}1A` },
    actionButtonText: { color: T.textSec, fontSize: 12, fontWeight: '700' },
    actionButtonTextActive: { color: T.text, fontWeight: '800' },
    primaryButton: {
      borderRadius: 999,
      backgroundColor: T.primary,
      paddingHorizontal: 14,
      paddingVertical: 10,
      alignItems: 'center',
      justifyContent: 'center',
      minWidth: 120,
    },
    neutralButton: {
      borderRadius: 999,
      borderWidth: 1,
      borderColor: T.border,
      paddingHorizontal: 14,
      paddingVertical: 10,
      alignItems: 'center',
      justifyContent: 'center',
      minWidth: 120,
      backgroundColor: T.bgSoft,
    },
    dangerButton: { backgroundColor: T.error },
    buttonDisabled: { opacity: 0.6 },
    buttonText: { color: colors.primaryText, fontSize: 12, fontWeight: '800' },
    neutralButtonText: { color: T.text, fontSize: 12, fontWeight: '800' },
    input: {
      borderRadius: 12,
      borderWidth: 1,
      borderColor: T.border,
      backgroundColor: T.bgSoft,
      color: T.text,
      fontSize: 13,
      paddingHorizontal: 12,
      paddingVertical: 10,
    },
    textarea: {
      minHeight: 86,
      textAlignVertical: 'top',
    },
    fieldLabel: { color: T.textSec, fontSize: 11, fontWeight: '700', textTransform: 'uppercase' },
    fieldWrap: { gap: 8 },
    switchRow: {
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'space-between',
      gap: 10,
      borderWidth: 1,
      borderColor: T.border,
      borderRadius: 12,
      backgroundColor: T.bgSoft,
      paddingHorizontal: 12,
      paddingVertical: 10,
    },
    switchLabel: { color: T.text, fontSize: 13, fontWeight: '700', flex: 1 },
    switchHint: { color: T.textMuted, fontSize: 11, marginTop: 2 },
    tiny: { color: T.textMuted, fontSize: 11 },
    divider: { height: 1, backgroundColor: T.border, marginVertical: 4 },
    logItem: {
      borderWidth: 1,
      borderColor: T.border,
      backgroundColor: T.bgSoft,
      borderRadius: 12,
      padding: 10,
      gap: 6,
    },
    logTitle: { color: T.text, fontSize: 12, fontWeight: '800' },
    logMeta: { color: T.textMuted, fontSize: 11 },
    modeAlert: {
      borderRadius: 12,
      borderWidth: 1,
      paddingHorizontal: 12,
      paddingVertical: 10,
      backgroundColor: `${T.warning}14`,
      borderColor: `${T.warning}55`,
    },
    modeAlertText: { color: T.warningText, fontSize: 12, lineHeight: 18, fontWeight: '700' },
  });

  const [state, setState] = useState<PlatformControlState>(createEmptyState());
  const [draft, setDraft] = useState<PlatformControlState>(createEmptyState());
  const [publicState, setPublicState] = useState<Record<string, any>>({});
  const [auditLogs, setAuditLogs] = useState<Array<Record<string, any>>>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [savingKey, setSavingKey] = useState('');
  const [status, setStatus] = useState<{ type: 'success' | 'error'; message: string } | null>(null);
  const [broadcastDraft, setBroadcastDraft] = useState({ title: '', message: '', audience: 'all_non_admin' as const });
  const [auditFilters, setAuditFilters] = useState({ action: '', actor: '', date_from: '', date_to: '', search: '' });
  const [auditLoading, setAuditLoading] = useState(false);
  const [announcementTemplates, setAnnouncementTemplates] = useState<Array<Record<string, any>>>([]);
  const [templatesLoading, setTemplatesLoading] = useState(false);
  const [subscriptionPromptTelemetry, setSubscriptionPromptTelemetry] = useState<{
    total_events: number;
    unique_sessions: number;
    by_plan: Array<{ plan: string; count: number }>;
    by_source: Array<{ source: string; count: number }>;
    top_endpoints: Array<{ endpoint: string; count: number }>;
    monitor_state?: Record<string, any> | null;
    monitor_recent_alerts?: Array<Record<string, any>>;
  } | null>(null);
  const [templateForm, setTemplateForm] = useState({
    template_id: '',
    name: '',
    title: '',
    message: '',
    audience: 'all_non_admin' as 'all_non_admin' | 'all_users' | 'staff_only',
    schedule_type: 'one_time' as 'one_time' | 'daily' | 'weekly',
    scheduled_for: '',
    daily_time_utc: '09:00',
    weekly_day_utc: '1',
    weekly_time_utc: '09:00',
    channels: { in_app: true, email: true },
    enabled: true,
  });

  const hydrateFromResponse = useCallback((responseData: any) => {
    const next = responseData?.state || createEmptyState();
    setState(next);
    setDraft(next);
    if (responseData?.public_state) {
      setPublicState(responseData.public_state);
    }
  }, []);

  const load = useCallback(async (mode: 'initial' | 'refresh' = 'initial') => {
    if (mode === 'refresh') setRefreshing(true);
    if (mode === 'initial') setLoading(true);
    try {
      const [controlRes, auditRes, telemetryRes] = await Promise.all([
        fetchPlatformControlState(),
        fetchPlatformControlAuditLogs(30),
        fetchSubscriptionPromptTelemetry(24),
      ]);
      hydrateFromResponse(controlRes);
      setAuditLogs(auditRes?.logs || []);
      setSubscriptionPromptTelemetry({
        total_events: Number(telemetryRes?.total_events || 0),
        unique_sessions: Number(telemetryRes?.unique_sessions || 0),
        by_plan: telemetryRes?.by_plan || [],
        by_source: telemetryRes?.by_source || [],
        top_endpoints: telemetryRes?.top_endpoints || [],
        monitor_state: telemetryRes?.monitor_state || null,
        monitor_recent_alerts: telemetryRes?.monitor_recent_alerts || [],
      });
      setStatus(null);
    } catch (error: any) {
      setStatus({ type: 'error', message: normalizeDetailError(error, 'Failed to load platform control state.') });
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [hydrateFromResponse]);

  useEffect(() => {
    load('initial');
  }, [load]);

  const setDraftPath = useCallback((path: string, value: any) => {
    setDraft((prev) => {
      const next: any = JSON.parse(JSON.stringify(prev || createEmptyState()));
      const segments = path.split('.');
      let cursor = next;
      segments.forEach((segment, index) => {
        if (index === segments.length - 1) {
          cursor[segment] = value;
          return;
        }
        if (!cursor[segment] || typeof cursor[segment] !== 'object') {
          cursor[segment] = {};
        }
        cursor = cursor[segment];
      });
      return next;
    });
    setStatus(null);
  }, []);

  const dirtyMap = useMemo(() => ({
    status: state.system_status !== draft.system_status || (state.system_status_reason || '') !== (draft.system_status_reason || ''),
    maintenance: !jsonEqual(state.maintenance, draft.maintenance),
    emergency: !jsonEqual(state.emergency_shutdown, draft.emergency_shutdown),
    features: !jsonEqual(state.feature_toggles, draft.feature_toggles),
    channels: !jsonEqual(state.notification_channels, draft.notification_channels),
  }), [draft, state]);

  const saveSystemStatus = useCallback(async () => {
    setSavingKey('system-status');
    try {
      const data = await updateSystemStatus({
        status: draft.system_status,
        reason: draft.system_status_reason || '',
        notify_users: true,
      });
      hydrateFromResponse(data);
      setStatus({ type: 'success', message: 'System status updated.' });
    } catch (error: any) {
      setStatus({ type: 'error', message: normalizeDetailError(error, 'Failed to update system status.') });
    } finally {
      setSavingKey('');
    }
  }, [draft.system_status, draft.system_status_reason, hydrateFromResponse]);

  const saveMaintenance = useCallback(async () => {
    setSavingKey('maintenance');
    try {
      const data = await updateMaintenanceMode({
        enabled: Boolean(draft.maintenance.enabled),
        title: draft.maintenance.title || 'Scheduled Platform Maintenance',
        reason: draft.maintenance.reason || '',
        starts_at: draft.maintenance.starts_at || null,
        ends_at: draft.maintenance.ends_at || null,
        allow_staff_read_only: Boolean(draft.maintenance.allow_staff_read_only),
        notify_users: true,
        force_replace: false,
      });
      hydrateFromResponse(data);
      setStatus({ type: 'success', message: draft.maintenance.enabled ? 'Maintenance mode is now active/scheduled.' : 'Maintenance mode disabled.' });
    } catch (error: any) {
      setStatus({ type: 'error', message: normalizeDetailError(error, 'Failed to update maintenance mode.') });
    } finally {
      setSavingKey('');
    }
  }, [draft.maintenance, hydrateFromResponse]);

  const toggleEmergency = useCallback(async () => {
    const nextEnabled = !Boolean(draft.emergency_shutdown.enabled);
    setSavingKey('emergency');
    try {
      const data = await updateEmergencyShutdown({
        enabled: nextEnabled,
        reason: draft.emergency_shutdown.reason || 'Emergency platform lockdown in progress.',
        notify_users: true,
      });
      hydrateFromResponse(data);
      setStatus({ type: 'success', message: nextEnabled ? 'Emergency shutdown is active.' : 'Emergency shutdown has been lifted.' });
    } catch (error: any) {
      setStatus({ type: 'error', message: normalizeDetailError(error, 'Failed to update emergency shutdown.') });
    } finally {
      setSavingKey('');
    }
  }, [draft.emergency_shutdown, hydrateFromResponse]);

  const saveFeatureToggles = useCallback(async () => {
    setSavingKey('features');
    try {
      const data = await updateFeatureToggles(draft.feature_toggles || {});
      hydrateFromResponse(data);
      setStatus({ type: 'success', message: 'Feature toggles updated.' });
    } catch (error: any) {
      setStatus({ type: 'error', message: normalizeDetailError(error, 'Failed to update feature toggles.') });
    } finally {
      setSavingKey('');
    }
  }, [draft.feature_toggles, hydrateFromResponse]);

  const saveChannels = useCallback(async () => {
    setSavingKey('channels');
    try {
      const data = await updateNotificationChannels(draft.notification_channels || {});
      hydrateFromResponse(data);
      setStatus({ type: 'success', message: 'Notification channels updated.' });
    } catch (error: any) {
      setStatus({ type: 'error', message: normalizeDetailError(error, 'Failed to update notification channels.') });
    } finally {
      setSavingKey('');
    }
  }, [draft.notification_channels, hydrateFromResponse]);

  const sendBroadcast = useCallback(async () => {
    if (!broadcastDraft.title.trim() || !broadcastDraft.message.trim()) {
      setStatus({ type: 'error', message: 'Broadcast title and message are required.' });
      return;
    }
    setSavingKey('broadcast');
    try {
      const data = await sendPlatformBroadcast({
        title: broadcastDraft.title.trim(),
        message: broadcastDraft.message.trim(),
        audience: broadcastDraft.audience,
      });
      hydrateFromResponse(data);
      setBroadcastDraft({ title: '', message: '', audience: 'all_non_admin' });
      setStatus({ type: 'success', message: 'Broadcast sent successfully.' });
      const logs = await fetchPlatformControlAuditLogs(30);
      setAuditLogs(logs.logs || []);
    } catch (error: any) {
      setStatus({ type: 'error', message: normalizeDetailError(error, 'Failed to send broadcast.') });
    } finally {
      setSavingKey('');
    }
  }, [broadcastDraft, hydrateFromResponse]);

  const loadTemplates = useCallback(async () => {
    setTemplatesLoading(true);
    try {
      const res = await listAnnouncementTemplates({ include_disabled: true });
      setAnnouncementTemplates(res.templates || []);
    } catch (error: any) {
      setStatus({ type: 'error', message: normalizeDetailError(error, 'Failed to load announcement templates.') });
    } finally {
      setTemplatesLoading(false);
    }
  }, []);

  const refreshAuditLogs = useCallback(async () => {
    setAuditLoading(true);
    try {
      const res = await fetchPlatformControlAuditLogsFiltered({
        limit: 200,
        action: auditFilters.action || undefined,
        actor: auditFilters.actor || undefined,
        date_from: auditFilters.date_from || undefined,
        date_to: auditFilters.date_to || undefined,
        search: auditFilters.search || undefined,
      });
      setAuditLogs(res.logs || []);
    } catch (error: any) {
      setStatus({ type: 'error', message: normalizeDetailError(error, 'Failed to load filtered audit logs.') });
    } finally {
      setAuditLoading(false);
    }
  }, [auditFilters]);

  const exportAuditLogs = useCallback(async (format: 'csv' | 'json') => {
    setSavingKey(`audit-export-${format}`);
    try {
      const blob = await exportPlatformControlAuditLogs(format, {
        limit: 1000,
        action: auditFilters.action || undefined,
        actor: auditFilters.actor || undefined,
        date_from: auditFilters.date_from || undefined,
        date_to: auditFilters.date_to || undefined,
        search: auditFilters.search || undefined,
      });

      if (typeof document === 'undefined') {
        setStatus({ type: 'success', message: `Export prepared (${format.toUpperCase()}).` });
        return;
      }

      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `platform-audit-logs.${format}`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
      setStatus({ type: 'success', message: `Audit logs exported as ${format.toUpperCase()}.` });
    } catch (error: any) {
      setStatus({ type: 'error', message: normalizeDetailError(error, `Failed to export ${format.toUpperCase()}.`) });
    } finally {
      setSavingKey('');
    }
  }, [auditFilters]);

  const resetTemplateForm = useCallback(() => {
    setTemplateForm({
      template_id: '',
      name: '',
      title: '',
      message: '',
      audience: 'all_non_admin',
      schedule_type: 'one_time',
      scheduled_for: '',
      daily_time_utc: '09:00',
      weekly_day_utc: '1',
      weekly_time_utc: '09:00',
      channels: { in_app: true, email: true },
      enabled: true,
    });
  }, []);

  const refreshSubscriptionPromptTelemetry = useCallback(async () => {
    try {
      const telemetryRes = await fetchSubscriptionPromptTelemetry(24);
      setSubscriptionPromptTelemetry({
        total_events: Number(telemetryRes?.total_events || 0),
        unique_sessions: Number(telemetryRes?.unique_sessions || 0),
        by_plan: telemetryRes?.by_plan || [],
        by_source: telemetryRes?.by_source || [],
        top_endpoints: telemetryRes?.top_endpoints || [],
        monitor_state: telemetryRes?.monitor_state || null,
        monitor_recent_alerts: telemetryRes?.monitor_recent_alerts || [],
      });
    } catch (error: any) {
      setStatus({ type: 'error', message: normalizeDetailError(error, 'Failed to refresh subscription prompt telemetry.') });
    }
  }, []);

  const saveAnnouncementTemplate = useCallback(async () => {
    if (!templateForm.name.trim() || !templateForm.title.trim() || !templateForm.message.trim()) {
      setStatus({ type: 'error', message: 'Template name, title, and message are required.' });
      return;
    }

    setSavingKey('template-save');
    try {
      const payload = {
        name: templateForm.name.trim(),
        title: templateForm.title.trim(),
        message: templateForm.message.trim(),
        audience: templateForm.audience,
        schedule_type: templateForm.schedule_type,
        scheduled_for: templateForm.schedule_type === 'one_time' ? (templateForm.scheduled_for || null) : null,
        daily_time_utc: templateForm.schedule_type === 'daily' ? (templateForm.daily_time_utc || null) : null,
        weekly_day_utc: templateForm.schedule_type === 'weekly' ? Number(templateForm.weekly_day_utc || '1') : null,
        weekly_time_utc: templateForm.schedule_type === 'weekly' ? (templateForm.weekly_time_utc || null) : null,
        channels: templateForm.channels,
        enabled: templateForm.enabled,
      };

      if (templateForm.template_id) {
        await updateAnnouncementTemplate(templateForm.template_id, payload);
        setStatus({ type: 'success', message: 'Announcement template updated.' });
      } else {
        await createAnnouncementTemplate(payload);
        setStatus({ type: 'success', message: 'Announcement template created.' });
      }
      await loadTemplates();
      resetTemplateForm();
    } catch (error: any) {
      setStatus({ type: 'error', message: normalizeDetailError(error, 'Failed to save announcement template.') });
    } finally {
      setSavingKey('');
    }
  }, [loadTemplates, resetTemplateForm, templateForm]);

  const editTemplate = useCallback((template: Record<string, any>) => {
    setTemplateForm({
      template_id: template.template_id || '',
      name: template.name || '',
      title: template.title || '',
      message: template.message || '',
      audience: template.audience || 'all_non_admin',
      schedule_type: template.schedule_type || 'one_time',
      scheduled_for: template.scheduled_for || '',
      daily_time_utc: template.daily_time_utc || '09:00',
      weekly_day_utc: String(template.weekly_day_utc ?? '1'),
      weekly_time_utc: template.weekly_time_utc || '09:00',
      channels: {
        in_app: Boolean(template?.channels?.in_app ?? true),
        email: Boolean(template?.channels?.email ?? true),
      },
      enabled: Boolean(template.enabled ?? true),
    });
  }, []);

  useEffect(() => {
    loadTemplates();
  }, [loadTemplates]);

  const activeMode = publicState?.active_mode || 'ONLINE';

  if (loading) {
    return (
      <View style={styles.loaderWrap} data-testid="platform-control-loading" testID="platform-control-loading">
        <ActivityIndicator size="large" color={T.primary} />
        <Text style={styles.loaderText}>{tx('admin.platformSettings.auto.text.001', 'Loading Platform Operations Control Center…')}</Text>
      </View>
    );
  }

  return (
    <ScrollView style={styles.screen} contentContainerStyle={styles.content} data-testid="platform-control-panel" testID="platform-control-panel">
      <View style={styles.card} data-testid="platform-control-hero-card" testID="platform-control-hero-card">
        <View style={styles.row}>
          <View style={{ flex: 1, minWidth: 260 }}>
            <Text style={styles.title} data-testid="platform-control-title" testID="platform-control-title">{tx('admin.platformSettings.auto.text.002', 'Platform Operations Control Center')}</Text>
            <Text style={styles.subtitle} data-testid="platform-control-subtitle" testID="platform-control-subtitle">{tx('admin.platformSettings.auto.text.003', 'Live control surface for maintenance windows, emergency shutdown, feature toggles, and global user communication.')}</Text>
          </View>
          <TouchableOpacity
            style={[styles.primaryButton, refreshing && styles.buttonDisabled]}
            onPress={() => load('refresh')}
            disabled={refreshing}
            data-testid="platform-control-refresh-button"
            testID="platform-control-refresh-button"
          >
            <Text style={styles.buttonText}>{refreshing ? 'Refreshing…' : 'Refresh'}</Text>
          </TouchableOpacity>
        </View>

        <View style={styles.row}>
          <View style={styles.badge} data-testid="platform-control-active-mode-badge" testID="platform-control-active-mode-badge">
            <Text style={styles.badgeText}>Active mode: {activeMode}</Text>
          </View>
          <View style={styles.badge} data-testid="platform-control-updated-at-badge" testID="platform-control-updated-at-badge">
            <Text style={styles.badgeText}>Last update: {formatDateTime(state.updated_at)}</Text>
          </View>
          <View style={styles.badge} data-testid="platform-control-updated-by-badge" testID="platform-control-updated-by-badge">
            <Text style={styles.badgeText}>Updated by: {state.updated_by || '—'}</Text>
          </View>
        </View>
      </View>

      {status ? (
        <View
          style={[
            styles.statusBanner,
            status.type === 'success'
              ? { backgroundColor: T.successSoft, borderColor: `${T.success}40` }
              : { backgroundColor: T.errorSoft, borderColor: `${T.error}40` },
          ]}
          data-testid="platform-control-status-banner"
          testID="platform-control-status-banner"
        >
          <Ionicons name={status.type === 'success' ? 'checkmark-circle' : 'alert-circle'} size={16} color={status.type === 'success' ? T.success : T.error} />
          <Text style={styles.statusText}>{status.message}</Text>
        </View>
      ) : null}

      <View style={styles.card} data-testid="platform-control-system-status-card" testID="platform-control-system-status-card">
        <Text style={styles.sectionTitle}>{tx('admin.platformSettings.auto.text.004', 'System Status Management')}</Text>
        <Text style={styles.sectionHint}>{tx('admin.platformSettings.auto.text.005', 'Set global status state for operations visibility.')}</Text>
        <View style={styles.buttonRow}>
          {SYSTEM_STATUS_OPTIONS.map((option) => (
            <TouchableOpacity
              key={option}
              style={[styles.actionButton, draft.system_status === option && styles.actionButtonActive]}
              onPress={() => setDraftPath('system_status', option)}
              data-testid={`platform-control-status-option-${option.toLowerCase()}`}
              testID={`platform-control-status-option-${option.toLowerCase()}`}
            >
              <Text style={[styles.actionButtonText, draft.system_status === option && styles.actionButtonTextActive]}>{option}</Text>
            </TouchableOpacity>
          ))}
        </View>

        <View style={styles.fieldWrap}>
          <Text style={styles.fieldLabel}>{tx('admin.platformSettings.auto.text.006', 'Status reason')}</Text>
          <TextInput
            style={styles.input}
            value={draft.system_status_reason || ''}
            onChangeText={(value) => setDraftPath('system_status_reason', value)}
            placeholder={tx('admin.platformSettings.auto.placeholder.001', 'Optional reason shown in status surfaces')}
            placeholderTextColor={T.textMuted}
            data-testid="platform-control-system-status-reason-input"
            testID="platform-control-system-status-reason-input"
          />
        </View>

        <TouchableOpacity
          style={[styles.primaryButton, (!dirtyMap.status || savingKey === 'system-status') && styles.buttonDisabled]}
          onPress={saveSystemStatus}
          disabled={!dirtyMap.status || savingKey === 'system-status'}
          data-testid="platform-control-system-status-save-button"
          testID="platform-control-system-status-save-button"
        >
          <Text style={styles.buttonText}>{savingKey === 'system-status' ? 'Saving…' : 'Save system status'}</Text>
        </TouchableOpacity>
      </View>

      <View style={styles.card} data-testid="platform-control-maintenance-card" testID="platform-control-maintenance-card">
        <Text style={styles.sectionTitle}>{tx('admin.platformSettings.auto.text.007', 'Maintenance Mode')}</Text>
        <Text style={styles.sectionHint}>{tx('admin.platformSettings.auto.text.008', 'Schedule or activate downtime while preserving admin and staff read-only flows.')}</Text>

        <View style={styles.switchRow} data-testid="platform-control-maintenance-enable-row" testID="platform-control-maintenance-enable-row">
          <View style={{ flex: 1 }}>
            <Text style={styles.switchLabel}>{tx('admin.platformSettings.auto.text.009', 'Enable maintenance mode')}</Text>
            <Text style={styles.switchHint}>{tx('admin.platformSettings.auto.text.010', 'Blocks non-admin traffic and serves global maintenance response payload.')}</Text>
          </View>
          <Switch
            value={Boolean(draft.maintenance.enabled)}
            onValueChange={(value) => setDraftPath('maintenance.enabled', value)}
            trackColor={{ false: T.border, true: `${T.warning}66` }}
            thumbColor={draft.maintenance.enabled ? T.warning : T.textMuted}
            data-testid="platform-control-maintenance-enable-switch"
            testID="platform-control-maintenance-enable-switch"
          />
        </View>

        <View style={styles.switchRow} data-testid="platform-control-maintenance-staff-row" testID="platform-control-maintenance-staff-row">
          <View style={{ flex: 1 }}>
            <Text style={styles.switchLabel}>{tx('admin.platformSettings.auto.text.011', 'Allow staff read-only during maintenance')}</Text>
            <Text style={styles.switchHint}>{tx('admin.platformSettings.auto.text.012', 'Staff can access safe GET/HEAD endpoints while users are blocked.')}</Text>
          </View>
          <Switch
            value={Boolean(draft.maintenance.allow_staff_read_only)}
            onValueChange={(value) => setDraftPath('maintenance.allow_staff_read_only', value)}
            trackColor={{ false: T.border, true: `${T.success}66` }}
            thumbColor={draft.maintenance.allow_staff_read_only ? T.success : T.textMuted}
            data-testid="platform-control-maintenance-staff-switch"
            testID="platform-control-maintenance-staff-switch"
          />
        </View>

        <View style={styles.fieldWrap}>
          <Text style={styles.fieldLabel}>{tx('admin.platformSettings.auto.text.013', 'Maintenance title')}</Text>
          <TextInput
            style={styles.input}
            value={draft.maintenance.title || ''}
            onChangeText={(value) => setDraftPath('maintenance.title', value)}
            placeholder={tx('admin.platformSettings.auto.placeholder.002', 'Scheduled Platform Maintenance')}
            placeholderTextColor={T.textMuted}
            data-testid="platform-control-maintenance-title-input"
            testID="platform-control-maintenance-title-input"
          />
        </View>

        <View style={styles.fieldWrap}>
          <Text style={styles.fieldLabel}>{tx('admin.platformSettings.auto.text.014', 'Maintenance reason')}</Text>
          <TextInput accessibilityLabel={tx('admin.platformSettings.auto.accessibility.001', 'Explain why downtime is required and expected impact.')}
            multiline
            style={[styles.input, styles.textarea]}
            value={draft.maintenance.reason || ''}
            onChangeText={(value) => setDraftPath('maintenance.reason', value)}
            placeholder={tx('admin.platformSettings.auto.placeholder.003', 'Explain why downtime is required and expected impact.')}
            placeholderTextColor={T.textMuted}
            data-testid="platform-control-maintenance-reason-input"
            testID="platform-control-maintenance-reason-input"
          />
        </View>

        <View style={styles.fieldWrap}>
          <Text style={styles.fieldLabel}>{tx('admin.platformSettings.auto.text.015', 'Start time (ISO, UTC)')}</Text>
          <TextInput
            style={styles.input}
            value={draft.maintenance.starts_at || ''}
            onChangeText={(value) => setDraftPath('maintenance.starts_at', value)}
            placeholder={tx('admin.platformSettings.auto.placeholder.004', '2026-04-28T08:00:00+00:00')}
            placeholderTextColor={T.textMuted}
            data-testid="platform-control-maintenance-start-input"
            testID="platform-control-maintenance-start-input"
          />
        </View>

        <View style={styles.fieldWrap}>
          <Text style={styles.fieldLabel}>{tx('admin.platformSettings.auto.text.016', 'End time (ISO, UTC)')}</Text>
          <TextInput
            style={styles.input}
            value={draft.maintenance.ends_at || ''}
            onChangeText={(value) => setDraftPath('maintenance.ends_at', value)}
            placeholder={tx('admin.platformSettings.auto.placeholder.005', '2026-04-28T10:00:00+00:00')}
            placeholderTextColor={T.textMuted}
            data-testid="platform-control-maintenance-end-input"
            testID="platform-control-maintenance-end-input"
          />
        </View>

        <View style={styles.row}>
          <Text style={styles.tiny} data-testid="platform-control-maintenance-active-window" testID="platform-control-maintenance-active-window">
            Active window: {formatDateTime(state.maintenance?.starts_at)} → {formatDateTime(state.maintenance?.ends_at)}
          </Text>
          <TouchableOpacity
            style={[styles.primaryButton, (!dirtyMap.maintenance || savingKey === 'maintenance') && styles.buttonDisabled]}
            onPress={saveMaintenance}
            disabled={!dirtyMap.maintenance || savingKey === 'maintenance'}
            data-testid="platform-control-maintenance-save-button"
            testID="platform-control-maintenance-save-button"
          >
            <Text style={styles.buttonText}>{savingKey === 'maintenance' ? 'Saving…' : 'Save maintenance'}</Text>
          </TouchableOpacity>
        </View>
      </View>

      <View style={styles.card} data-testid="platform-control-emergency-card" testID="platform-control-emergency-card">
        <Text style={styles.sectionTitle}>{tx('admin.platformSettings.auto.text.017', 'Emergency Shutdown')}</Text>
        <Text style={styles.sectionHint}>{tx('admin.platformSettings.auto.text.018', 'Instant lockdown for non-admin users with outage signaling.')}</Text>

        <View style={styles.modeAlert} data-testid="platform-control-emergency-alert" testID="platform-control-emergency-alert">
          <Text style={styles.modeAlertText}>Current state: {draft.emergency_shutdown.enabled ? 'ENABLED' : 'DISABLED'}</Text>
        </View>

        <View style={styles.fieldWrap}>
          <Text style={styles.fieldLabel}>{tx('admin.platformSettings.auto.text.019', 'Emergency reason')}</Text>
          <TextInput accessibilityLabel={tx('admin.platformSettings.auto.accessibility.002', 'Urgent reason shown to blocked users')}
            multiline
            style={[styles.input, styles.textarea]}
            value={draft.emergency_shutdown.reason || ''}
            onChangeText={(value) => setDraftPath('emergency_shutdown.reason', value)}
            placeholder={tx('admin.platformSettings.auto.placeholder.006', 'Urgent reason shown to blocked users')}
            placeholderTextColor={T.textMuted}
            data-testid="platform-control-emergency-reason-input"
            testID="platform-control-emergency-reason-input"
          />
        </View>

        <TouchableOpacity accessibilityLabel={tx('admin.platformSettings.auto.accessibility.003', 'Toggle global feature switch')}
          style={[
            styles.primaryButton,
            draft.emergency_shutdown.enabled ? styles.neutralButton : styles.dangerButton,
            savingKey === 'emergency' && styles.buttonDisabled,
          ]}
          onPress={toggleEmergency}
          disabled={savingKey === 'emergency'}
          data-testid="platform-control-emergency-toggle-button"
          testID="platform-control-emergency-toggle-button"
        >
          <Text style={draft.emergency_shutdown.enabled ? styles.neutralButtonText : styles.buttonText}>
            {savingKey === 'emergency'
              ? 'Updating…'
              : draft.emergency_shutdown.enabled
                ? 'Disable emergency shutdown'
                : 'Enable emergency shutdown'}
          </Text>
        </TouchableOpacity>
      </View>

      <View style={styles.card} data-testid="platform-control-features-card" testID="platform-control-features-card">
        <Text style={styles.sectionTitle}>{tx('admin.platformSettings.auto.text.020', 'Global Feature Toggles')}</Text>
        <Text style={styles.sectionHint}>{tx('admin.platformSettings.auto.text.021', 'Enable or disable platform modules instantly.')}</Text>

        {Object.entries(draft.feature_toggles || {}).map(([key, value]) => (
          <View key={key} style={styles.switchRow} data-testid={`platform-control-feature-row-${key}`} testID={`platform-control-feature-row-${key}`}>
            <Text style={styles.switchLabel}>{FEATURE_LABELS[key] || key}</Text>
            <Switch
              value={Boolean(value)}
              onValueChange={(nextValue) => setDraftPath(`feature_toggles.${key}`, nextValue)}
              trackColor={{ false: T.border, true: `${T.primary}66` }}
              thumbColor={value ? T.primary : T.textMuted}
              data-testid={`platform-control-feature-switch-${key}`}
              testID={`platform-control-feature-switch-${key}`}
            />
          </View>
        ))}

        <TouchableOpacity
          style={[styles.primaryButton, (!dirtyMap.features || savingKey === 'features') && styles.buttonDisabled]}
          onPress={saveFeatureToggles}
          disabled={!dirtyMap.features || savingKey === 'features'}
          data-testid="platform-control-features-save-button"
          testID="platform-control-features-save-button"
        >
          <Text style={styles.buttonText}>{savingKey === 'features' ? 'Saving…' : 'Save feature toggles'}</Text>
        </TouchableOpacity>
      </View>

      <View style={styles.card} data-testid="platform-control-channels-card" testID="platform-control-channels-card">
        <Text style={styles.sectionTitle}>{tx('admin.platformSettings.auto.text.022', 'User Notification Channels')}</Text>
        <Text style={styles.sectionHint}>{tx('admin.platformSettings.auto.text.023', 'Selected path: in-app + email enabled immediately.')}</Text>

        {Object.entries(draft.notification_channels || {}).map(([key, value]) => (
          <View key={key} style={styles.switchRow} data-testid={`platform-control-channel-row-${key}`} testID={`platform-control-channel-row-${key}`}>
            <View style={{ flex: 1 }}>
              <Text style={styles.switchLabel}>{key.toUpperCase()}</Text>
              {(key === 'sms' || key === 'push') ? (
                <Text style={styles.switchHint}>{tx('admin.platformSettings.auto.text.024', 'Delivery requires external provider configuration.')}</Text>
              ) : null}
            </View>
            <Switch
              value={Boolean(value)}
              onValueChange={(nextValue) => setDraftPath(`notification_channels.${key}`, nextValue)}
              trackColor={{ false: T.border, true: `${T.primary}66` }}
              thumbColor={value ? T.primary : T.textMuted}
              data-testid={`platform-control-channel-switch-${key}`}
              testID={`platform-control-channel-switch-${key}`}
            />
          </View>
        ))}

        <TouchableOpacity
          style={[styles.primaryButton, (!dirtyMap.channels || savingKey === 'channels') && styles.buttonDisabled]}
          onPress={saveChannels}
          disabled={!dirtyMap.channels || savingKey === 'channels'}
          data-testid="platform-control-channels-save-button"
          testID="platform-control-channels-save-button"
        >
          <Text style={styles.buttonText}>{savingKey === 'channels' ? 'Saving…' : 'Save channels'}</Text>
        </TouchableOpacity>
      </View>

      <View style={styles.card} data-testid="platform-control-broadcast-card" testID="platform-control-broadcast-card">
        <Text style={styles.sectionTitle}>{tx('admin.platformSettings.auto.text.025', 'Broadcast Announcement')}</Text>
        <Text style={styles.sectionHint}>{tx('admin.platformSettings.auto.text.026', 'Send platform-wide announcement via selected channels.')}</Text>

        <View style={styles.fieldWrap}>
          <Text style={styles.fieldLabel}>{tx('admin.platformSettings.auto.text.027', 'Announcement title')}</Text>
          <TextInput
            style={styles.input}
            value={broadcastDraft.title}
            onChangeText={(value) => setBroadcastDraft((prev) => ({ ...prev, title: value }))}
            placeholder={tx('admin.platformSettings.auto.placeholder.007', 'Platform update')}
            placeholderTextColor={T.textMuted}
            data-testid="platform-control-broadcast-title-input"
            testID="platform-control-broadcast-title-input"
          />
        </View>

        <View style={styles.fieldWrap}>
          <Text style={styles.fieldLabel}>{tx('admin.platformSettings.auto.text.028', 'Announcement message')}</Text>
          <TextInput accessibilityLabel={tx('admin.platformSettings.auto.accessibility.004', 'Message shown in in-app and email notifications')}
            multiline
            style={[styles.input, styles.textarea]}
            value={broadcastDraft.message}
            onChangeText={(value) => setBroadcastDraft((prev) => ({ ...prev, message: value }))}
            placeholder={tx('admin.platformSettings.auto.placeholder.008', 'Message shown in in-app and email notifications')}
            placeholderTextColor={T.textMuted}
            data-testid="platform-control-broadcast-message-input"
            testID="platform-control-broadcast-message-input"
          />
        </View>

        <View style={styles.buttonRow}>
          {AUDIENCE_OPTIONS.map((option) => (
            <TouchableOpacity
              key={option.id}
              style={[styles.actionButton, broadcastDraft.audience === option.id && styles.actionButtonActive]}
              onPress={() => setBroadcastDraft((prev) => ({ ...prev, audience: option.id }))}
              data-testid={`platform-control-broadcast-audience-${option.id}`}
              testID={`platform-control-broadcast-audience-${option.id}`}
            >
              <Text style={[styles.actionButtonText, broadcastDraft.audience === option.id && styles.actionButtonTextActive]}>{option.label}</Text>
            </TouchableOpacity>
          ))}
        </View>

        <TouchableOpacity
          style={[styles.primaryButton, savingKey === 'broadcast' && styles.buttonDisabled]}
          onPress={sendBroadcast}
          disabled={savingKey === 'broadcast'}
          data-testid="platform-control-broadcast-send-button"
          testID="platform-control-broadcast-send-button"
        >
          <Text style={styles.buttonText}>{savingKey === 'broadcast' ? 'Sending…' : 'Send broadcast'}</Text>
        </TouchableOpacity>
      </View>

      <View style={styles.card} data-testid="subscription-prompt-telemetry-card" testID="subscription-prompt-telemetry-card">
        <View style={styles.row}>
          <Text style={styles.sectionTitle}>{tx('admin.platformSettings.auto.text.029', 'Subscription Prompt Telemetry (24h)')}</Text>
          <TouchableOpacity
            style={styles.neutralButton}
            onPress={refreshSubscriptionPromptTelemetry}
            data-testid="subscription-prompt-telemetry-refresh-button"
            testID="subscription-prompt-telemetry-refresh-button"
          >
            <Text style={styles.neutralButtonText}>{tx('admin.platformSettings.auto.text.030', 'Refresh telemetry')}</Text>
          </TouchableOpacity>
        </View>

        <View style={styles.buttonRow}>
          <View style={styles.badge} data-testid="subscription-prompt-telemetry-total-events" testID="subscription-prompt-telemetry-total-events">
            <Text style={styles.badgeText}>Total prompts: {Number(subscriptionPromptTelemetry?.total_events || 0)}</Text>
          </View>
          <View style={styles.badge} data-testid="subscription-prompt-telemetry-unique-sessions" testID="subscription-prompt-telemetry-unique-sessions">
            <Text style={styles.badgeText}>Unique sessions: {Number(subscriptionPromptTelemetry?.unique_sessions || 0)}</Text>
          </View>
          <View style={styles.badge} data-testid="subscription-prompt-telemetry-monitor-status" testID="subscription-prompt-telemetry-monitor-status">
            <Text style={styles.badgeText}>Monitor: {String(subscriptionPromptTelemetry?.monitor_state?.anomaly ? 'ANOMALY' : 'STABLE')}</Text>
          </View>
        </View>

        {!!subscriptionPromptTelemetry?.monitor_state ? (
          <Text style={styles.tiny} data-testid="subscription-prompt-telemetry-monitor-detail" testID="subscription-prompt-telemetry-monitor-detail">
            Last check: {formatDateTime(subscriptionPromptTelemetry.monitor_state?.updated_at)} · current 1h: {Number(subscriptionPromptTelemetry.monitor_state?.current_window?.count || 0)} · baseline avg: {Number(subscriptionPromptTelemetry.monitor_state?.baseline_window?.avg_per_hour || 0).toFixed(2)}
          </Text>
        ) : null}

        <Text style={styles.fieldLabel}>{tx('admin.platformSettings.auto.text.031', 'Recent Monitor Alerts')}</Text>
        {((subscriptionPromptTelemetry?.monitor_recent_alerts || []).length === 0) ? (
          <Text style={styles.tiny} data-testid="subscription-prompt-telemetry-monitor-alerts-empty" testID="subscription-prompt-telemetry-monitor-alerts-empty">{tx('admin.platformSettings.auto.text.032', 'No monitor alerts in recent history.')}</Text>
        ) : (
          (subscriptionPromptTelemetry?.monitor_recent_alerts || []).slice(0, 5).map((row, idx) => (
            <View key={`mon-alert-${idx}`} style={styles.logItem} data-testid={`subscription-prompt-telemetry-monitor-alert-row-${idx}`} testID={`subscription-prompt-telemetry-monitor-alert-row-${idx}`}>
              <Text style={styles.logTitle}>{String(row.reason || 'alert').toUpperCase()}</Text>
              <Text style={styles.logMeta}>Time: {formatDateTime(row.created_at)} · current: {Number(row.current_count || 0)} · baseline: {Number(row.baseline_avg || 0).toFixed(2)}</Text>
            </View>
          ))
        )}

        <Text style={styles.fieldLabel}>{tx('admin.platformSettings.auto.text.033', 'By Plan')}</Text>
        {((subscriptionPromptTelemetry?.by_plan || []).length === 0) ? (
          <Text style={styles.tiny} data-testid="subscription-prompt-telemetry-by-plan-empty" testID="subscription-prompt-telemetry-by-plan-empty">{tx('admin.platformSettings.auto.text.034', 'No prompt telemetry events yet.')}</Text>
        ) : (
          (subscriptionPromptTelemetry?.by_plan || []).map((row, idx) => (
            <View key={`plan-${idx}`} style={styles.logItem} data-testid={`subscription-prompt-telemetry-plan-row-${idx}`} testID={`subscription-prompt-telemetry-plan-row-${idx}`}>
              <Text style={styles.logTitle}>{String(row.plan || 'unknown').toUpperCase()}</Text>
              <Text style={styles.logMeta}>Count: {Number(row.count || 0)}</Text>
            </View>
          ))
        )}

        <Text style={styles.fieldLabel}>{tx('admin.platformSettings.auto.text.035', 'Top Trigger Endpoints')}</Text>
        {((subscriptionPromptTelemetry?.top_endpoints || []).length === 0) ? (
          <Text style={styles.tiny} data-testid="subscription-prompt-telemetry-top-endpoints-empty" testID="subscription-prompt-telemetry-top-endpoints-empty">{tx('admin.platformSettings.auto.text.036', 'No endpoint telemetry yet.')}</Text>
        ) : (
          (subscriptionPromptTelemetry?.top_endpoints || []).slice(0, 6).map((row, idx) => (
            <View key={`endpoint-${idx}`} style={styles.logItem} data-testid={`subscription-prompt-telemetry-endpoint-row-${idx}`} testID={`subscription-prompt-telemetry-endpoint-row-${idx}`}>
              <Text style={styles.logTitle}>{row.endpoint || '(none)'}</Text>
              <Text style={styles.logMeta}>Count: {Number(row.count || 0)}</Text>
            </View>
          ))
        )}
      </View>

      <View style={styles.card} data-testid="platform-control-audit-card" testID="platform-control-audit-card">
        <View style={styles.row}>
          <Text style={styles.sectionTitle}>{tx('admin.platformSettings.auto.text.037', 'Audit Logs (Filters + Export)')}</Text>
          <TouchableOpacity
            style={styles.neutralButton}
            onPress={refreshAuditLogs}
            data-testid="platform-control-audit-refresh-button"
            testID="platform-control-audit-refresh-button"
          >
            <Text style={styles.neutralButtonText}>{auditLoading ? 'Loading…' : 'Apply filters'}</Text>
          </TouchableOpacity>
        </View>

        <View style={styles.fieldWrap}>
          <Text style={styles.fieldLabel}>{tx('admin.platformSettings.auto.text.038', 'Action filter')}</Text>
          <TextInput
            style={styles.input}
            value={auditFilters.action}
            onChangeText={(value) => setAuditFilters((prev) => ({ ...prev, action: value }))}
            placeholder={tx('admin.platformSettings.auto.placeholder.009', 'e.g. maintenance_mode_updated')}
            placeholderTextColor={T.textMuted}
            data-testid="platform-control-audit-filter-action-input"
            testID="platform-control-audit-filter-action-input"
          />
        </View>

        <View style={styles.fieldWrap}>
          <Text style={styles.fieldLabel}>{tx('admin.platformSettings.auto.text.039', 'Actor email filter')}</Text>
          <TextInput
            style={styles.input}
            value={auditFilters.actor}
            onChangeText={(value) => setAuditFilters((prev) => ({ ...prev, actor: value }))}
            placeholder={tx('admin.platformSettings.auto.placeholder.010', 'admin@realaicoach.app')}
            placeholderTextColor={T.textMuted}
            data-testid="platform-control-audit-filter-actor-input"
            testID="platform-control-audit-filter-actor-input"
          />
        </View>

        <View style={styles.fieldWrap}>
          <Text style={styles.fieldLabel}>{tx('admin.platformSettings.auto.text.040', 'Search text')}</Text>
          <TextInput
            style={styles.input}
            value={auditFilters.search}
            onChangeText={(value) => setAuditFilters((prev) => ({ ...prev, search: value }))}
            placeholder={tx('admin.platformSettings.auto.placeholder.011', 'search action/actor/metadata')}
            placeholderTextColor={T.textMuted}
            data-testid="platform-control-audit-filter-search-input"
            testID="platform-control-audit-filter-search-input"
          />
        </View>

        <View style={styles.fieldWrap}>
          <Text style={styles.fieldLabel}>{tx('admin.platformSettings.auto.text.041', 'Date from (ISO)')}</Text>
          <TextInput
            style={styles.input}
            value={auditFilters.date_from}
            onChangeText={(value) => setAuditFilters((prev) => ({ ...prev, date_from: value }))}
            placeholder={tx('admin.platformSettings.auto.placeholder.012', '2026-04-27T00:00:00+00:00')}
            placeholderTextColor={T.textMuted}
            data-testid="platform-control-audit-filter-date-from-input"
            testID="platform-control-audit-filter-date-from-input"
          />
        </View>

        <View style={styles.fieldWrap}>
          <Text style={styles.fieldLabel}>{tx('admin.platformSettings.auto.text.042', 'Date to (ISO)')}</Text>
          <TextInput
            style={styles.input}
            value={auditFilters.date_to}
            onChangeText={(value) => setAuditFilters((prev) => ({ ...prev, date_to: value }))}
            placeholder={tx('admin.platformSettings.auto.placeholder.013', '2026-04-28T00:00:00+00:00')}
            placeholderTextColor={T.textMuted}
            data-testid="platform-control-audit-filter-date-to-input"
            testID="platform-control-audit-filter-date-to-input"
          />
        </View>

        <View style={styles.buttonRow}>
          <TouchableOpacity
            style={[styles.primaryButton, savingKey === 'audit-export-csv' && styles.buttonDisabled]}
            onPress={() => exportAuditLogs('csv')}
            disabled={savingKey === 'audit-export-csv'}
            data-testid="platform-control-audit-export-csv-button"
            testID="platform-control-audit-export-csv-button"
          >
            <Text style={styles.buttonText}>{tx('admin.platformSettings.auto.text.043', 'Export CSV')}</Text>
          </TouchableOpacity>
          <TouchableOpacity
            style={[styles.neutralButton, savingKey === 'audit-export-json' && styles.buttonDisabled]}
            onPress={() => exportAuditLogs('json')}
            disabled={savingKey === 'audit-export-json'}
            data-testid="platform-control-audit-export-json-button"
            testID="platform-control-audit-export-json-button"
          >
            <Text style={styles.neutralButtonText}>{tx('admin.platformSettings.auto.text.044', 'Export JSON')}</Text>
          </TouchableOpacity>
        </View>

        {auditLogs.length === 0 ? (
          <Text style={styles.tiny} data-testid="platform-control-audit-empty" testID="platform-control-audit-empty">{tx('admin.platformSettings.auto.text.045', 'No audit events yet.')}</Text>
        ) : (
          auditLogs.slice(0, 40).map((row, index) => (
            <View
              key={row.audit_id || `audit-${index}`}
              style={styles.logItem}
              data-testid={`platform-control-audit-item-${index}`}
              testID={`platform-control-audit-item-${index}`}
            >
              <Text style={styles.logTitle}>{String(row.action || 'action').replace(/_/g, ' ').toUpperCase()}</Text>
              <Text style={styles.logMeta}>Actor: {row.actor_email || row.actor_user_id || 'system'}</Text>
              <Text style={styles.logMeta}>Time: {formatDateTime(row.created_at)}</Text>
              <Text style={styles.logMeta}>Status: {row.status || 'n/a'}</Text>
            </View>
          ))
        )}
      </View>

      <View style={styles.card} data-testid="platform-control-announcement-template-card" testID="platform-control-announcement-template-card">
        <Text style={styles.sectionTitle}>{tx('admin.platformSettings.auto.text.046', 'Announcement Scheduler Templates')}</Text>
        <Text style={styles.sectionHint}>{tx('admin.platformSettings.auto.text.047', 'Create one-time or recurring announcement templates (in-app + email).')}</Text>

        <View style={styles.fieldWrap}>
          <Text style={styles.fieldLabel}>{tx('admin.platformSettings.auto.text.048', 'Template name')}</Text>
          <TextInput
            style={styles.input}
            value={templateForm.name}
            onChangeText={(value) => setTemplateForm((prev) => ({ ...prev, name: value }))}
            placeholder={tx('admin.platformSettings.auto.placeholder.014', 'Weekly maintenance reminder')}
            placeholderTextColor={T.textMuted}
            data-testid="platform-control-template-name-input"
            testID="platform-control-template-name-input"
          />
        </View>

        <View style={styles.fieldWrap}>
          <Text style={styles.fieldLabel}>{tx('admin.platformSettings.auto.text.049', 'Template title')}</Text>
          <TextInput
            style={styles.input}
            value={templateForm.title}
            onChangeText={(value) => setTemplateForm((prev) => ({ ...prev, title: value }))}
            placeholder={tx('admin.platformSettings.auto.placeholder.015', 'Scheduled Platform Update')}
            placeholderTextColor={T.textMuted}
            data-testid="platform-control-template-title-input"
            testID="platform-control-template-title-input"
          />
        </View>

        <View style={styles.fieldWrap}>
          <Text style={styles.fieldLabel}>{tx('admin.platformSettings.auto.text.050', 'Template message')}</Text>
          <TextInput accessibilityLabel={tx('admin.platformSettings.auto.accessibility.005', 'Template body for scheduled announcement dispatch.')}
            multiline
            style={[styles.input, styles.textarea]}
            value={templateForm.message}
            onChangeText={(value) => setTemplateForm((prev) => ({ ...prev, message: value }))}
            placeholder={tx('admin.platformSettings.auto.placeholder.016', 'Template body for scheduled announcement dispatch.')}
            placeholderTextColor={T.textMuted}
            data-testid="platform-control-template-message-input"
            testID="platform-control-template-message-input"
          />
        </View>

        <View style={styles.buttonRow}>
          {SCHEDULE_OPTIONS.map((option) => (
            <TouchableOpacity
              key={option.id}
              style={[styles.actionButton, templateForm.schedule_type === option.id && styles.actionButtonActive]}
              onPress={() => setTemplateForm((prev) => ({ ...prev, schedule_type: option.id }))}
              data-testid={`platform-control-template-schedule-${option.id}`}
              testID={`platform-control-template-schedule-${option.id}`}
            >
              <Text style={[styles.actionButtonText, templateForm.schedule_type === option.id && styles.actionButtonTextActive]}>{option.label}</Text>
            </TouchableOpacity>
          ))}
        </View>

        {templateForm.schedule_type === 'one_time' ? (
          <View style={styles.fieldWrap}>
            <Text style={styles.fieldLabel}>{tx('admin.platformSettings.auto.text.051', 'Scheduled at (ISO UTC)')}</Text>
            <TextInput
              style={styles.input}
              value={templateForm.scheduled_for}
              onChangeText={(value) => setTemplateForm((prev) => ({ ...prev, scheduled_for: value }))}
              placeholder={tx('admin.platformSettings.auto.placeholder.017', '2026-05-01T09:30:00+00:00')}
              placeholderTextColor={T.textMuted}
              data-testid="platform-control-template-scheduled-for-input"
              testID="platform-control-template-scheduled-for-input"
            />
          </View>
        ) : null}

        {templateForm.schedule_type === 'daily' ? (
          <View style={styles.fieldWrap}>
            <Text style={styles.fieldLabel}>{tx('admin.platformSettings.auto.text.052', 'Daily time UTC (HH:MM)')}</Text>
            <TextInput
              style={styles.input}
              value={templateForm.daily_time_utc}
              onChangeText={(value) => setTemplateForm((prev) => ({ ...prev, daily_time_utc: value }))}
              placeholder="09:00"
              placeholderTextColor={T.textMuted}
              data-testid="platform-control-template-daily-time-input"
              testID="platform-control-template-daily-time-input"
            />
          </View>
        ) : null}

        {templateForm.schedule_type === 'weekly' ? (
          <>
            <View style={styles.fieldWrap}>
              <Text style={styles.fieldLabel}>{tx('admin.platformSettings.auto.text.053', 'Weekly day UTC (0=Mon … 6=Sun)')}</Text>
              <TextInput
                style={styles.input}
                value={templateForm.weekly_day_utc}
                onChangeText={(value) => setTemplateForm((prev) => ({ ...prev, weekly_day_utc: value }))}
                placeholder="1"
                placeholderTextColor={T.textMuted}
                data-testid="platform-control-template-weekly-day-input"
                testID="platform-control-template-weekly-day-input"
              />
            </View>
            <View style={styles.fieldWrap}>
              <Text style={styles.fieldLabel}>{tx('admin.platformSettings.auto.text.054', 'Weekly time UTC (HH:MM)')}</Text>
              <TextInput
                style={styles.input}
                value={templateForm.weekly_time_utc}
                onChangeText={(value) => setTemplateForm((prev) => ({ ...prev, weekly_time_utc: value }))}
                placeholder="09:00"
                placeholderTextColor={T.textMuted}
                data-testid="platform-control-template-weekly-time-input"
                testID="platform-control-template-weekly-time-input"
              />
            </View>
          </>
        ) : null}

        <View style={styles.switchRow} data-testid="platform-control-template-channel-inapp-row" testID="platform-control-template-channel-inapp-row">
          <Text style={styles.switchLabel}>{tx('admin.platformSettings.auto.text.055', 'In-app notifications')}</Text>
          <Switch
            value={Boolean(templateForm.channels.in_app)}
            onValueChange={(value) => setTemplateForm((prev) => ({ ...prev, channels: { ...prev.channels, in_app: value } }))}
            trackColor={{ false: T.border, true: `${T.primary}66` }}
            thumbColor={templateForm.channels.in_app ? T.primary : T.textMuted}
            data-testid="platform-control-template-channel-inapp-switch"
            testID="platform-control-template-channel-inapp-switch"
          />
        </View>

        <View style={styles.switchRow} data-testid="platform-control-template-channel-email-row" testID="platform-control-template-channel-email-row">
          <Text style={styles.switchLabel}>{tx('admin.platformSettings.auto.text.056', 'Email notifications')}</Text>
          <Switch
            value={Boolean(templateForm.channels.email)}
            onValueChange={(value) => setTemplateForm((prev) => ({ ...prev, channels: { ...prev.channels, email: value } }))}
            trackColor={{ false: T.border, true: `${T.primary}66` }}
            thumbColor={templateForm.channels.email ? T.primary : T.textMuted}
            data-testid="platform-control-template-channel-email-switch"
            testID="platform-control-template-channel-email-switch"
          />
        </View>

        <View style={styles.buttonRow}>
          <TouchableOpacity
            style={[styles.primaryButton, savingKey === 'template-save' && styles.buttonDisabled]}
            onPress={saveAnnouncementTemplate}
            disabled={savingKey === 'template-save'}
            data-testid="platform-control-template-save-button"
            testID="platform-control-template-save-button"
          >
            <Text style={styles.buttonText}>{templateForm.template_id ? 'Update template' : 'Create template'}</Text>
          </TouchableOpacity>
          <TouchableOpacity
            style={styles.neutralButton}
            onPress={resetTemplateForm}
            data-testid="platform-control-template-reset-button"
            testID="platform-control-template-reset-button"
          >
            <Text style={styles.neutralButtonText}>{tx('admin.platformSettings.auto.text.057', 'Clear form')}</Text>
          </TouchableOpacity>
          <TouchableOpacity
            style={styles.neutralButton}
            onPress={loadTemplates}
            data-testid="platform-control-template-refresh-button"
            testID="platform-control-template-refresh-button"
          >
            <Text style={styles.neutralButtonText}>{templatesLoading ? 'Refreshing…' : 'Refresh templates'}</Text>
          </TouchableOpacity>
        </View>

        {announcementTemplates.length === 0 ? (
          <Text style={styles.tiny} data-testid="platform-control-template-empty" testID="platform-control-template-empty">{tx('admin.platformSettings.auto.text.058', 'No templates created yet.')}</Text>
        ) : (
          announcementTemplates.slice(0, 20).map((tpl, idx) => (
            <View key={tpl.template_id || idx} style={styles.logItem} data-testid={`platform-control-template-item-${idx}`} testID={`platform-control-template-item-${idx}`}>
              <Text style={styles.logTitle}>{tpl.name || 'Template'}</Text>
              <Text style={styles.logMeta}>Schedule: {tpl.schedule_type} • Next run: {formatDateTime(tpl.next_run_at)}</Text>
              <Text style={styles.logMeta}>Audience: {tpl.audience} • Enabled: {String(tpl.enabled)}</Text>
              <View style={styles.buttonRow}>
                <TouchableOpacity
                  style={styles.neutralButton}
                  onPress={() => editTemplate(tpl)}
                  data-testid={`platform-control-template-edit-button-${idx}`}
                  testID={`platform-control-template-edit-button-${idx}`}
                >
                  <Text style={styles.neutralButtonText}>{tx('admin.platformSettings.auto.text.059', 'Edit')}</Text>
                </TouchableOpacity>
                <TouchableOpacity accessibilityLabel={tx('admin.platformSettings.auto.accessibility.006', 'Dispatch template now')}
                  style={styles.primaryButton}
                  onPress={async () => {
                    setSavingKey(`template-dispatch-${tpl.template_id}`);
                    try {
                      await dispatchAnnouncementTemplate(String(tpl.template_id));
                      setStatus({ type: 'success', message: 'Template dispatched now.' });
                      await Promise.all([loadTemplates(), refreshAuditLogs()]);
                    } catch (error: any) {
                      setStatus({ type: 'error', message: normalizeDetailError(error, 'Failed to dispatch template.') });
                    } finally {
                      setSavingKey('');
                    }
                  }}
                  data-testid={`platform-control-template-dispatch-button-${idx}`}
                  testID={`platform-control-template-dispatch-button-${idx}`}
                >
                  <Text style={styles.buttonText}>{tx('admin.platformSettings.auto.text.060', 'Dispatch now')}</Text>
                </TouchableOpacity>
                <TouchableOpacity accessibilityLabel={tx('admin.platformSettings.auto.accessibility.007', 'Disable announcement template')}
                  style={styles.neutralButton}
                  onPress={async () => {
                    setSavingKey(`template-disable-${tpl.template_id}`);
                    try {
                      await disableAnnouncementTemplate(String(tpl.template_id));
                      setStatus({ type: 'success', message: 'Template disabled.' });
                      await Promise.all([loadTemplates(), refreshAuditLogs()]);
                    } catch (error: any) {
                      setStatus({ type: 'error', message: normalizeDetailError(error, 'Failed to disable template.') });
                    } finally {
                      setSavingKey('');
                    }
                  }}
                  data-testid={`platform-control-template-disable-button-${idx}`}
                  testID={`platform-control-template-disable-button-${idx}`
                  }
                >
                  <Text style={styles.neutralButtonText}>{tx('admin.platformSettings.auto.text.061', 'Disable')}</Text>
                </TouchableOpacity>
              </View>
            </View>
          ))
        )}
      </View>
    </ScrollView>
  );
}
