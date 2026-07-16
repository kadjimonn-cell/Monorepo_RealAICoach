import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  ActivityIndicator,
  Platform,
  RefreshControl,
  ScrollView,
  Text,
  TextInput,
  TouchableOpacity,
  useWindowDimensions,
  View,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import { useTheme } from '../../context/ThemeContext';
import { useTranslation } from '../../hooks/useTranslation';
import {
  acknowledgeParityIncident,
  createAnnouncement,
  createNotificationRule,
  createTemplate,
  deleteAnnouncement,
  deleteNotificationRule,
  disableTemplateNow,
  dispatchTemplateNow,
  exportAuditLogs,
  fetchPlatformStatusBundle,
  resolveParityIncident,
  runParityAudit,
  runSecurityAlertTest,
  saveFeatureToggles,
  saveMaintenanceWindow,
  saveNotificationChannels,
  saveSecurityAlertConfig,
  saveSystemStatus,
  sendPlatformBroadcastNow,
  testNotificationRule,
  toggleNotificationRule,
} from '../../services/platformSettingsEnterprise';

type BannerType = 'success' | 'error' | 'info';

const txFallback = (t: (key: string) => string, key: string, fallback: string) => {
  const resolved = t(key);
  return resolved === key ? fallback : resolved;
};

const isoToLocalInput = (value?: string | null) => {
  if (!value) return '';
  try {
    const date = new Date(value);
    return new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
  } catch {
    return '';
  }
};

const localInputToIso = (value?: string) => {
  if (!value) return null;
  try {
    return new Date(value).toISOString();
  } catch {
    return null;
  }
};

const asArray = (value: any) => (Array.isArray(value) ? value : []);

const formatNumber = (value: any) => {
  const num = Number(value ?? 0);
  if (!Number.isFinite(num)) return '--';
  return num.toLocaleString();
};

const formatDateTime = (value?: string | null) => {
  if (!value) return '—';
  try {
    return new Date(value).toLocaleString();
  } catch {
    return String(value);
  }
};

const statusToTone = (value?: string) => {
  const normalized = String(value || '').toLowerCase();
  if (['healthy', 'operational', 'up', 'online', 'pass', 'ok', 'resolved', 'completed'].includes(normalized)) return 'healthy';
  if (['warning', 'degraded', 'acknowledged', 'maintenance'].includes(normalized)) return 'warning';
  if (['critical', 'error', 'down', 'outage', 'fail', 'failed', 'failing', 'open'].includes(normalized)) return 'critical';
  return 'neutral';
};

const downloadBlob = (blob: Blob, name: string) => {
  if (Platform.OS !== 'web' || typeof window === 'undefined') return false;
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.URL.revokeObjectURL(url);
  return true;
};

const StatusChip = ({ value, colors, testId }: { value?: string; colors: any; testId: string }) => {
  const tone = statusToTone(value);
  const tint = tone === 'healthy' ? colors.successText : tone === 'warning' ? colors.warning : tone === 'critical' ? colors.error : colors.textMuted;
  return (
    <View
      style={{
        paddingHorizontal: 10,
        paddingVertical: 6,
        borderRadius: 999,
        borderWidth: 1,
        borderColor: `${tint}66`,
        backgroundColor: `${tint}1A`,
      }}
      data-testid={testId}
      testID={testId}
    >
      <Text style={{ color: tint, fontSize: 11, fontWeight: '800', textTransform: 'uppercase' }}>{value || 'unknown'}</Text>
    </View>
  );
};

const StatCard = ({
  label,
  value,
  subtitle,
  icon,
  colors,
  testId,
}: {
  label: string;
  value: string;
  subtitle?: string;
  icon: string;
  colors: any;
  testId: string;
}) => (
  <View
    style={{
      flex: 1,
      minWidth: 180,
      padding: 14,
      borderRadius: 14,
      borderWidth: 1,
      borderColor: colors.border,
      backgroundColor: colors.cardBg,
      gap: 6,
    }}
    data-testid={testId}
    testID={testId}
  >
    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
      <Ionicons name={icon as any} size={14} color={colors.primary} />
      <Text style={{ color: colors.textMuted, fontSize: 11, fontWeight: '700' }}>{label}</Text>
    </View>
    <Text style={{ color: colors.text, fontSize: 22, fontWeight: '900', letterSpacing: -0.4 }}>{value}</Text>
    {!!subtitle && <Text style={{ color: colors.textMuted, fontSize: 11 }}>{subtitle}</Text>}
  </View>
);

const SectionTitle = ({ icon, title, subtitle, colors, testId }: { icon: string; title: string; subtitle: string; colors: any; testId: string }) => (
  <View style={{ gap: 6 }} data-testid={testId} testID={testId}>
    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
      <Ionicons name={icon as any} size={17} color={colors.primary} />
      <Text style={{ color: colors.text, fontSize: 18, fontWeight: '900' }}>{title}</Text>
    </View>
    <Text style={{ color: colors.textMuted, fontSize: 12, lineHeight: 18 }}>{subtitle}</Text>
  </View>
);

const SectionCard = ({ children, colors, testId }: { children: React.ReactNode; colors: any; testId: string }) => (
  <View
    style={{
      borderWidth: 1,
      borderColor: colors.border,
      borderRadius: 18,
      backgroundColor: colors.cardBg,
      padding: 16,
      gap: 14,
    }}
    data-testid={testId}
    testID={testId}
  >
    {children}
  </View>
);

const PrimaryButton = ({
  onPress,
  label,
  colors,
  testId,
  disabled,
}: {
  onPress: () => void;
  label: string;
  colors: any;
  testId: string;
  disabled?: boolean;
}) => (
  <TouchableOpacity accessibilityLabel="On press in platform settings enterprise workspace button"
    onPress={onPress}
    disabled={disabled}
    style={{
      borderRadius: 999,
      paddingHorizontal: 14,
      paddingVertical: 10,
      backgroundColor: colors.primary,
      opacity: disabled ? 0.55 : 1,
    }}
    data-testid={testId}
    testID={testId}
  >
    <Text style={{ color: colors.primaryText, fontSize: 12, fontWeight: '800' }}>{label}</Text>
  </TouchableOpacity>
);

const SoftButton = ({
  onPress,
  label,
  colors,
  testId,
  disabled,
  danger,
}: {
  onPress: () => void;
  label: string;
  colors: any;
  testId: string;
  disabled?: boolean;
  danger?: boolean;
}) => (
  <TouchableOpacity accessibilityLabel="On press in platform settings enterprise workspace button"
    onPress={onPress}
    disabled={disabled}
    style={{
      borderRadius: 999,
      paddingHorizontal: 12,
      paddingVertical: 9,
      borderWidth: 1,
      borderColor: danger ? `${colors.error}66` : colors.border,
      backgroundColor: danger ? `${colors.error}15` : colors.bgSoft,
      opacity: disabled ? 0.55 : 1,
    }}
    data-testid={testId}
    testID={testId}
  >
    <Text style={{ color: danger ? colors.error : colors.text, fontSize: 11, fontWeight: '800' }}>{label}</Text>
  </TouchableOpacity>
);

const UnsupportedModule = ({ title, details, colors, testId }: { title: string; details: string; colors: any; testId: string }) => (
  <View
    style={{
      borderWidth: 1,
      borderStyle: 'dashed',
      borderColor: `${colors.warning}80`,
      borderRadius: 12,
      padding: 12,
      backgroundColor: `${colors.warning}14`,
      gap: 4,
    }}
    data-testid={testId}
    testID={testId}
  >
    <Text style={{ color: colors.warningText, fontSize: 12, fontWeight: '800' }}>{title}</Text>
    <Text style={{ color: colors.warningText, fontSize: 11, lineHeight: 17 }}>{details}</Text>
  </View>
);

export default function PlatformSettingsEnterpriseWorkspace() {
  const { colors } = useTheme();
  const { t } = useTranslation();
  const tx = useCallback((key: string, fallback: string) => txFallback(t, key, fallback), [t]);
  const { width } = useWindowDimensions();

  const isMobile = width < 760;

  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [savingKey, setSavingKey] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [banner, setBanner] = useState<{ type: BannerType; message: string } | null>(null);
  const [lastUpdated, setLastUpdated] = useState<string>('');

  const [controlData, setControlData] = useState<any>({});
  const [systemStatusData, setSystemStatusData] = useState<any>({});
  const [instanceData, setInstanceData] = useState<any>({});
  const [systemHealthData, setSystemHealthData] = useState<any>({});
  const [systemMetricsData, setSystemMetricsData] = useState<any>({});
  const [observabilityData, setObservabilityData] = useState<any>({});
  const [liveServicesData, setLiveServicesData] = useState<any>({});
  const [enterpriseStandardData, setEnterpriseStandardData] = useState<any>({});
  const [parityData, setParityData] = useState<any>({});
  const [securitySummaryData, setSecuritySummaryData] = useState<any>({});
  const [securityTimelineData, setSecurityTimelineData] = useState<any>({});
  const [securityRecentData, setSecurityRecentData] = useState<any>({});
  const [securityAlertConfigData, setSecurityAlertConfigData] = useState<any>({});
  const [notificationRulesData, setNotificationRulesData] = useState<any>({});
  const [featureFlagsData, setFeatureFlagsData] = useState<any>({});
  const [announcementsData, setAnnouncementsData] = useState<any>({});
  const [templatesData, setTemplatesData] = useState<any>({});
  const [auditLogsData, setAuditLogsData] = useState<any>({});
  const [legalBroadcastsData, setLegalBroadcastsData] = useState<any>({});
  const [securityBroadcastsData, setSecurityBroadcastsData] = useState<any>({});
  const [previewAdapterData, setPreviewAdapterData] = useState<any>({});

  const [supported, setSupported] = useState<Record<string, boolean>>({});

  const [statusDraft, setStatusDraft] = useState({ status: 'ONLINE', reason: '', notify_users: true });
  const [maintenanceDraft, setMaintenanceDraft] = useState({
    enabled: false,
    title: 'Scheduled Platform Maintenance',
    reason: '',
    starts_at: '',
    ends_at: '',
    allow_staff_read_only: true,
    notify_users: true,
    force_replace: false,
    maintenance_type: 'planned',
    severity: 'medium',
    affected_systems: 'platform',
    timezone: 'UTC',
    internal_notes: '',
    public_notes: '',
    recovery_notes: '',
  });
  const [channelDraft, setChannelDraft] = useState({ in_app: true, email: true, sms: false, push: false });
  const [broadcastDraft, setBroadcastDraft] = useState({ title: '', message: '', audience: 'all_non_admin' as 'all_non_admin' | 'all_users' | 'staff_only' });
  const [templateDraft, setTemplateDraft] = useState({
    name: '',
    title: '',
    message: '',
    audience: 'all_non_admin' as 'all_non_admin' | 'all_users' | 'staff_only',
    schedule_type: 'one_time' as 'one_time' | 'daily' | 'weekly',
    scheduled_for: '',
    daily_time_utc: '09:00',
    weekly_day_utc: '1',
    weekly_time_utc: '09:00',
    in_app: true,
    email: true,
  });
  const [announcementDraft, setAnnouncementDraft] = useState({ title: '', message: '', priority: 'normal', audience: 'all' });
  const [notificationRuleDraft, setNotificationRuleDraft] = useState({
    name: '',
    metric: 'errors',
    operator: '>=',
    threshold: '5',
    time_window_minutes: '5',
    severity: 'warning',
    cooldown_minutes: '5',
  });
  const [securityConfigDraft, setSecurityConfigDraft] = useState({
    enabled: true,
    threshold: 100,
    window_minutes: 60,
    cooldown_minutes: 120,
    email_enabled: true,
  });
  const [resolveNote, setResolveNote] = useState('');

  const [auditSearch, setAuditSearch] = useState('');
  const [auditSortKey, setAuditSortKey] = useState<'created_at' | 'action' | 'actor_email' | 'status'>('created_at');
  const [auditSortDir, setAuditSortDir] = useState<'asc' | 'desc'>('desc');
  const [auditPage, setAuditPage] = useState(1);
  const [auditColumns, setAuditColumns] = useState({
    created_at: true,
    action: true,
    actor_email: true,
    status: true,
    metadata: true,
  });

  const pendingRef = useRef(false);
  const aliveRef = useRef(true);

  const loadData = useCallback(async (mode: 'initial' | 'refresh' | 'silent' = 'initial') => {
    if (pendingRef.current) return;
    pendingRef.current = true;
    if (mode === 'initial') setLoading(true);
    if (mode === 'refresh') setRefreshing(true);
    setError(null);
    try {
      const bundle = await fetchPlatformStatusBundle();
      if (!aliveRef.current) return;

      const moduleState: Record<string, boolean> = {};
      const pick = (key: string, result: PromiseSettledResult<any>, setter: (value: any) => void, fallback: any = {}) => {
        if (result.status === 'fulfilled') {
          moduleState[key] = true;
          setter(result.value?.data ?? fallback);
          return;
        }
        moduleState[key] = false;
        setter(fallback);
      };

      pick('control', bundle.control, setControlData);
      pick('systemStatus', bundle.systemStatus, setSystemStatusData);
      pick('instanceMarker', bundle.instanceMarker, setInstanceData);
      pick('systemHealth', bundle.systemHealth, setSystemHealthData);
      pick('systemMetrics', bundle.systemMetrics, setSystemMetricsData);
      pick('observability', bundle.observability, setObservabilityData);
      pick('liveServices', bundle.liveServices, setLiveServicesData);
      pick('enterpriseStandard', bundle.enterpriseStandard, setEnterpriseStandardData);
      pick('parityAudit', bundle.parityAudit, setParityData);
      pick('securitySummary', bundle.securitySummary, setSecuritySummaryData);
      pick('securityTimeline', bundle.securityTimeline, setSecurityTimelineData);
      pick('securityRecent', bundle.securityRecent, setSecurityRecentData);
      pick('securityAlertConfig', bundle.securityAlertConfig, setSecurityAlertConfigData);
      pick('notificationRules', bundle.notificationRules, setNotificationRulesData);
      pick('featureFlags', bundle.featureFlags, setFeatureFlagsData);
      pick('announcements', bundle.announcements, setAnnouncementsData);
      pick('templates', bundle.templates, setTemplatesData);
      pick('auditLogs', bundle.auditLogs, setAuditLogsData);
      pick('legalBroadcasts', bundle.legalBroadcasts, setLegalBroadcastsData);
      pick('securityBroadcasts', bundle.securityBroadcasts, setSecurityBroadcastsData);
      pick('previewAdapterCheck', bundle.previewAdapterCheck, setPreviewAdapterData);
      setSupported(moduleState);

      if (!moduleState.control && !moduleState.systemStatus) {
        setError('Core platform settings endpoints are not reachable for this admin session.');
      }
      setLastUpdated(new Date().toISOString());
    } catch (err: any) {
      setError(err?.message || 'Failed to load Platform Settings');
    } finally {
      pendingRef.current = false;
      if (aliveRef.current) {
        setLoading(false);
        setRefreshing(false);
      }
    }
  }, []);

  useEffect(() => {
    loadData('initial');
    const interval = setInterval(() => {
      loadData('silent');
    }, 45000);
    return () => {
      aliveRef.current = false;
      clearInterval(interval);
    };
  }, [loadData]);

  useEffect(() => {
    const state = controlData?.state || {};
    setStatusDraft((prev) => ({
      ...prev,
      status: String(state?.system_status || 'ONLINE'),
      reason: String(state?.system_status_reason || ''),
    }));

    const maintenance = state?.maintenance || {};
    setMaintenanceDraft((prev) => ({
      ...prev,
      enabled: Boolean(maintenance?.enabled),
      title: String(maintenance?.title || 'Scheduled Platform Maintenance'),
      reason: String(maintenance?.reason || ''),
      starts_at: isoToLocalInput(maintenance?.starts_at),
      ends_at: isoToLocalInput(maintenance?.ends_at),
      allow_staff_read_only: Boolean(maintenance?.allow_staff_read_only),
    }));

    const channels = state?.notification_channels || {};
    setChannelDraft({
      in_app: Boolean(channels?.in_app ?? true),
      email: Boolean(channels?.email ?? true),
      sms: Boolean(channels?.sms ?? false),
      push: Boolean(channels?.push ?? false),
    });
  }, [controlData]);

  useEffect(() => {
    setSecurityConfigDraft((prev) => ({
      ...prev,
      enabled: Boolean(securityAlertConfigData?.enabled ?? true),
      threshold: Number(securityAlertConfigData?.threshold ?? 100),
      window_minutes: Number(securityAlertConfigData?.window_minutes ?? 60),
      cooldown_minutes: Number(securityAlertConfigData?.cooldown_minutes ?? 120),
      email_enabled: Boolean(securityAlertConfigData?.email_enabled ?? true),
    }));
  }, [securityAlertConfigData]);

  const setInfo = (type: BannerType, message: string) => {
    setBanner({ type, message });
    if (type === 'success') {
      setTimeout(() => {
        setBanner((prev) => (prev?.message === message ? null : prev));
      }, 3200);
    }
  };

  const withAction = async (key: string, task: () => Promise<void>) => {
    setSavingKey(key);
    try {
      await task();
    } catch (err: any) {
      setInfo('error', err?.response?.data?.detail?.message || err?.response?.data?.detail || err?.message || 'Action failed.');
    } finally {
      setSavingKey('');
    }
  };

  const saveStatusAction = async () => {
    await withAction('save-status', async () => {
      await saveSystemStatus({
        status: statusDraft.status as any,
        reason: statusDraft.reason,
        notify_users: Boolean(statusDraft.notify_users),
      });
      setInfo('success', 'Platform system status updated.');
      await loadData('silent');
    });
  };

  const saveMaintenanceAction = async () => {
    await withAction('save-maintenance', async () => {
      await saveMaintenanceWindow({
        enabled: Boolean(maintenanceDraft.enabled),
        title: maintenanceDraft.title,
        reason: maintenanceDraft.reason,
        starts_at: localInputToIso(maintenanceDraft.starts_at),
        ends_at: localInputToIso(maintenanceDraft.ends_at),
        allow_staff_read_only: Boolean(maintenanceDraft.allow_staff_read_only),
        notify_users: Boolean(maintenanceDraft.notify_users),
        force_replace: Boolean(maintenanceDraft.force_replace),
      });
      setInfo('success', 'Maintenance window saved from real scheduler-backed API.');
      await loadData('silent');
    });
  };

  const saveChannelsAction = async () => {
    await withAction('save-channels', async () => {
      await saveNotificationChannels(channelDraft);
      setInfo('success', 'Notification channels updated.');
      await loadData('silent');
    });
  };

  const toggleFeatureAction = async (key: string) => {
    const current = controlData?.state?.feature_toggles || {};
    const next = { ...current, [key]: !Boolean(current[key]) };
    await withAction(`toggle-feature-${key}`, async () => {
      await saveFeatureToggles(next);
      setInfo('success', `Feature toggle "${key}" updated.`);
      await loadData('silent');
    });
  };

  const sendBroadcastAction = async () => {
    if (!broadcastDraft.title.trim() || !broadcastDraft.message.trim()) {
      setInfo('error', 'Broadcast requires title and message.');
      return;
    }
    await withAction('send-broadcast', async () => {
      await sendPlatformBroadcastNow({
        title: broadcastDraft.title.trim(),
        message: broadcastDraft.message.trim(),
        audience: broadcastDraft.audience,
      });
      setBroadcastDraft((prev) => ({ ...prev, title: '', message: '' }));
      setInfo('success', 'Broadcast queued to supported channels.');
      await loadData('silent');
    });
  };

  const createTemplateAction = async () => {
    if (!templateDraft.name.trim() || !templateDraft.title.trim() || !templateDraft.message.trim()) {
      setInfo('error', 'Template requires name, title, and message.');
      return;
    }
    await withAction('create-template', async () => {
      await createTemplate({
        name: templateDraft.name.trim(),
        title: templateDraft.title.trim(),
        message: templateDraft.message.trim(),
        audience: templateDraft.audience,
        schedule_type: templateDraft.schedule_type,
        scheduled_for: templateDraft.schedule_type === 'one_time' ? localInputToIso(templateDraft.scheduled_for) : null,
        daily_time_utc: templateDraft.schedule_type === 'daily' ? templateDraft.daily_time_utc : null,
        weekly_day_utc: templateDraft.schedule_type === 'weekly' ? Number(templateDraft.weekly_day_utc || '1') : null,
        weekly_time_utc: templateDraft.schedule_type === 'weekly' ? templateDraft.weekly_time_utc : null,
        channels: {
          in_app: templateDraft.in_app,
          email: templateDraft.email,
        },
        enabled: true,
      });
      setInfo('success', 'Announcement template created.');
      await loadData('silent');
    });
  };

  const createAnnouncementAction = async () => {
    if (!announcementDraft.title.trim() || !announcementDraft.message.trim()) {
      setInfo('error', 'Announcement title and message are required.');
      return;
    }
    await withAction('create-announcement', async () => {
      await createAnnouncement({
        title: announcementDraft.title.trim(),
        message: announcementDraft.message.trim(),
        priority: announcementDraft.priority,
        audience: announcementDraft.audience,
      });
      setAnnouncementDraft((prev) => ({ ...prev, title: '', message: '' }));
      setInfo('success', 'Platform announcement created.');
      await loadData('silent');
    });
  };

  const createNotificationRuleAction = async () => {
    if (!notificationRuleDraft.name.trim()) {
      setInfo('error', 'Notification rule name is required.');
      return;
    }
    await withAction('create-notification-rule', async () => {
      await createNotificationRule({
        name: notificationRuleDraft.name.trim(),
        condition: {
          metric: notificationRuleDraft.metric,
          operator: notificationRuleDraft.operator,
          threshold: Number(notificationRuleDraft.threshold || 0),
          time_window_minutes: Number(notificationRuleDraft.time_window_minutes || 5),
        },
        severity: notificationRuleDraft.severity,
        cooldown_minutes: Number(notificationRuleDraft.cooldown_minutes || 5),
        enabled: true,
      });
      setInfo('success', 'Notification rule created.');
      await loadData('silent');
    });
  };

  const saveSecurityConfigAction = async () => {
    await withAction('save-security-config', async () => {
      await saveSecurityAlertConfig(securityConfigDraft);
      setInfo('success', 'Security incident alert configuration updated.');
      await loadData('silent');
    });
  };

  const runSecurityTestAction = async () => {
    await withAction('run-security-test', async () => {
      const result = await runSecurityAlertTest();
      setInfo('info', `Security alert test result: ${result?.status || 'completed'}`);
      await loadData('silent');
    });
  };

  const runParityAuditAction = async () => {
    await withAction('run-parity-audit', async () => {
      const result = await runParityAudit();
      const status = result?.audit?.overall_status || result?.status || 'ok';
      setInfo(status === 'pass' ? 'success' : 'info', `Parity audit finished: ${status}`);
      await loadData('silent');
    });
  };

  const exportAuditAction = async (format: 'csv' | 'json') => {
    await withAction(`export-audit-${format}`, async () => {
      const blob = await exportAuditLogs(format);
      const name = `platform_audit_logs_${Date.now()}.${format}`;
      const downloaded = downloadBlob(blob, name);
      if (downloaded) setInfo('success', `Audit logs exported (${format.toUpperCase()}).`);
      else setInfo('info', 'Audit export is available on web runtime only.');
    });
  };

  const controlState = controlData?.state || {};
  const checks = systemStatusData?.checks || {};
  const auditRows = asArray(auditLogsData?.logs);
  const templates = asArray(templatesData?.templates);
  const announcements = asArray(announcementsData?.announcements);
  const featureFlags = asArray(featureFlagsData?.flags);
  const notificationRules = asArray(notificationRulesData?.rules);
  const schedulerHeartbeats = asArray(enterpriseStandardData?.scheduler?.heartbeats);
  const securityRecent = asArray(securityRecentData?.incidents);
  const legalBroadcasts = asArray(legalBroadcastsData?.items);
  const securityBroadcasts = asArray(securityBroadcastsData?.items);
  const latestIncident = parityData?.latest_open_incident || {};

  const filteredAuditRows = useMemo(() => {
    const search = auditSearch.trim().toLowerCase();
    let rows = auditRows;
    if (search) {
      rows = rows.filter((item: any) => {
        const bundle = [
          item?.action,
          item?.actor_email,
          item?.status,
          item?.created_at,
          JSON.stringify(item?.metadata || {}),
        ]
          .join(' ')
          .toLowerCase();
        return bundle.includes(search);
      });
    }
    const sortFactor = auditSortDir === 'asc' ? 1 : -1;
    return [...rows].sort((a: any, b: any) => {
      const va = String(a?.[auditSortKey] ?? '');
      const vb = String(b?.[auditSortKey] ?? '');
      if (auditSortKey === 'created_at') {
        return (new Date(va).getTime() - new Date(vb).getTime()) * sortFactor;
      }
      return va.localeCompare(vb) * sortFactor;
    });
  }, [auditRows, auditSearch, auditSortDir, auditSortKey]);

  const pageSize = 12;
  const totalPages = Math.max(1, Math.ceil(filteredAuditRows.length / pageSize));
  const safePage = Math.min(auditPage, totalPages);
  const pagedAuditRows = filteredAuditRows.slice((safePage - 1) * pageSize, safePage * pageSize);

  const serviceRows = [
    { key: 'platform', label: 'Platform Status', value: controlState?.system_status || systemStatusData?.status || 'unknown', source: 'platform-control/admin/state' },
    { key: 'api', label: 'API Status', value: checks?.api?.status || systemStatusData?.status || 'unknown', source: 'system/status' },
    { key: 'database', label: 'Database Status', value: checks?.database?.status || (systemHealthData?.database?.healthy ? 'healthy' : 'unknown'), source: 'system/status + system/health/detailed' },
    { key: 'queue', label: 'Queue Status', value: liveServicesData?.scheduler ? 'active' : 'not_exposed', source: 'admin/platform-health/live-services' },
    { key: 'notifications', label: 'Notification Service', value: liveServicesData?.notifications ? 'active' : 'not_exposed', source: 'admin/platform-health/live-services' },
    { key: 'auth', label: 'Authentication Service', value: securitySummaryData?.total ? 'active' : 'not_exposed', source: 'admin/security-incidents/summary (activity proxy)' },
    { key: 'payment', label: 'Payment Service', value: enterpriseStandardData?.platform?.latest_fix ? 'active' : 'not_exposed', source: 'admin/platform-health/enterprise-standard/status' },
    { key: 'storage', label: 'Storage Status', value: Number(systemMetricsData?.disk?.percent ?? 0) >= 95 ? 'critical' : 'healthy', source: 'admin/system/metrics' },
    { key: 'cdn', label: 'CDN Status', value: previewAdapterData?.status || 'not_exposed', source: 'admin/platform-health/preview-adapter-live-check' },
    { key: 'realtime', label: 'WebSocket/SSE Status', value: liveServicesData?.realtime?.reconnect_health_status || 'unknown', source: 'admin/platform-health/live-services' },
    { key: 'jobs', label: 'Background Jobs', value: checks?.scheduler?.status || enterpriseStandardData?.framework_status || 'unknown', source: 'system/status + enterprise-standard/status' },
    { key: 'tasks', label: 'Scheduled Tasks', value: schedulerHeartbeats.length > 0 ? 'active' : 'unknown', source: 'enterprise-standard/status' },
    { key: 'deployment', label: 'Last Deployment', value: systemStatusData?.timestamp ? formatDateTime(systemStatusData?.timestamp) : 'not_exposed', source: 'system/status timestamp' },
    { key: 'env', label: 'Current Environment', value: instanceData?.current_domain || 'unknown', source: 'system/instance-marker' },
    { key: 'version', label: 'Version Information', value: systemStatusData?.version || 'unknown', source: 'system/status' },
    { key: 'sync', label: 'Sync Health', value: previewAdapterData?.status || (parityData?.trend?.pass_rate ? 'active' : 'unknown'), source: 'preview-adapter-live-check + global-parity-audit/latest' },
    { key: 'incidents', label: 'Incident Status', value: latestIncident?.status || 'none_open', source: 'global-parity-audit/latest' },
    { key: 'updated', label: 'Last Updated', value: formatDateTime(lastUpdated), source: 'frontend refresh clock' },
  ];

  const unavailableFeatures = [
    !supported.liveServices && 'Queue backlog & task runtime telemetry module is unavailable in this environment.',
    !supported.templates && 'Template scheduling APIs are unavailable; creation controls are hidden.',
    !supported.featureFlags && 'Feature flags API is unavailable; rollout board is hidden.',
    !supported.notificationRules && 'Custom notification rules API is unavailable; threshold controls are hidden.',
    !supported.parityAudit && 'Incident board APIs are unavailable; incident actions are hidden.',
  ].filter(Boolean) as string[];

  if (loading && !controlData?.state) {
    return (
      <View style={{ padding: 32, alignItems: 'center', gap: 12 }} data-testid="platform-settings-loading" testID="platform-settings-loading">
        <ActivityIndicator size="large" color={colors.primary} />
        <Text style={{ color: colors.textMuted, fontSize: 12 }}>{tx('platformSettings.loading', 'Loading Platform Settings command center...')}</Text>
      </View>
    );
  }

  if (error && !controlData?.state) {
    return (
      <View style={{ padding: 28, alignItems: 'center', gap: 10 }} data-testid="platform-settings-fatal-error" testID="platform-settings-fatal-error">
        <Ionicons name="alert-circle" size={28} color={colors.error} />
        <Text style={{ color: colors.error, fontSize: 12, textAlign: 'center' }}>{error}</Text>
        <PrimaryButton onPress={() => loadData('refresh')} label="Retry" colors={colors} testId="platform-settings-retry-button" />
      </View>
    );
  }

  return (
    <View style={{ flex: 1 }} data-testid="platform-settings-workspace" testID="platform-settings-workspace">
      <View style={{ paddingHorizontal: isMobile ? 12 : 20, paddingTop: 16, paddingBottom: 10, gap: 10 }} data-testid="platform-settings-header" testID="platform-settings-header">
        <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 8 }}>
          <View style={{ gap: 4 }}>
            <Text style={{ color: colors.text, fontSize: isMobile ? 22 : 30, fontWeight: '900', letterSpacing: -0.7 }} data-testid="platform-settings-title" testID="platform-settings-title">
              {tx('platformSettings.title', 'Platform Settings')}
            </Text>
            <Text style={{ color: colors.textMuted, fontSize: 12 }} data-testid="platform-settings-subtitle" testID="platform-settings-subtitle">
              {tx('platformSettings.subtitle', 'Global Platform Operations Center — enterprise control surface using live platform data')}
            </Text>
          </View>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
            <StatusChip value={systemStatusData?.status || controlState?.system_status} colors={colors} testId="platform-settings-global-status-chip" />
            <SoftButton
              onPress={() => loadData('refresh')}
              label={refreshing ? 'Refreshing...' : 'Refresh now'}
              colors={colors}
              testId="platform-settings-refresh-btn"
              disabled={refreshing}
            />
          </View>
        </View>
        <Text style={{ color: colors.textMuted, fontSize: 11 }} data-testid="platform-settings-last-sync" testID="platform-settings-last-sync">
          Last sync: {formatDateTime(lastUpdated)} • Auto-refresh: 45s polling fallback
        </Text>
      </View>

      <ScrollView
        style={{ flex: 1 }}
        contentContainerStyle={{ paddingHorizontal: isMobile ? 12 : 20, paddingBottom: 34, gap: 14 }}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => loadData('refresh')} tintColor={colors.primary} />}
        data-testid="platform-settings-scroll-root"
        testID="platform-settings-scroll-root"
      >
        {banner && (
          <View
            style={{
              padding: 10,
              borderRadius: 12,
              borderWidth: 1,
              borderColor: banner.type === 'error' ? `${colors.error}66` : banner.type === 'success' ? `${colors.successText}66` : `${colors.primary}66`,
              backgroundColor: banner.type === 'error' ? `${colors.error}12` : banner.type === 'success' ? `${colors.successText}10` : `${colors.primary}12`,
            }}
            data-testid="platform-settings-action-banner"
            testID="platform-settings-action-banner"
          >
            <Text style={{ color: banner.type === 'error' ? colors.error : banner.type === 'success' ? colors.successText : colors.text, fontSize: 12, fontWeight: '700' }}>
              {banner.message}
            </Text>
          </View>
        )}

        {!!error && (
          <View style={{ borderWidth: 1, borderColor: `${colors.error}55`, backgroundColor: `${colors.error}14`, borderRadius: 12, padding: 10 }} data-testid="platform-settings-soft-error" testID="platform-settings-soft-error">
            <Text style={{ color: colors.error, fontSize: 12, lineHeight: 18 }}>{error}</Text>
          </View>
        )}

        {unavailableFeatures.length > 0 && (
          <SectionCard colors={colors} testId="platform-settings-unsupported-modules-card">
            <SectionTitle
              icon="warning"
              title="Unsupported modules (gracefully hidden)"
              subtitle="Only modules backed by active backend services are rendered as interactive controls."
              colors={colors}
              testId="platform-settings-unsupported-modules-title"
            />
            <View style={{ gap: 8 }}>
              {unavailableFeatures.map((note, idx) => (
                <UnsupportedModule key={idx} title={`Module ${idx + 1}`} details={note} colors={colors} testId={`platform-settings-unsupported-item-${idx}`} />
              ))}
            </View>
          </SectionCard>
        )}

        <SectionCard colors={colors} testId="platform-settings-overview-section">
          <SectionTitle
            icon="pulse"
            title="1) Platform Status Overview"
            subtitle="Live operational indicators sourced from platform control, system, observability, scheduler, and parity health APIs."
            colors={colors}
            testId="platform-settings-overview-title"
          />

          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10 }}>
            <StatCard label="API Snapshots (1h)" value={formatNumber(observabilityData?.application?.api_snapshots_1h)} subtitle="Request volume" icon="stats-chart" colors={colors} testId="platform-settings-kpi-api-volume" />
            <StatCard label="Client Errors (24h)" value={formatNumber(observabilityData?.application?.client_errors_24h)} subtitle="System health analytics" icon="warning" colors={colors} testId="platform-settings-kpi-client-errors" />
            <StatCard label="DB Latency (ms)" value={String(systemHealthData?.database?.latency_ms ?? '--')} subtitle="Database probe" icon="server" colors={colors} testId="platform-settings-kpi-db-latency" />
            <StatCard label="Uptime (hours)" value={String(liveServicesData?.uptime_hours ?? '--')} subtitle="Runtime process uptime" icon="time" colors={colors} testId="platform-settings-kpi-uptime" />
          </View>

          <View style={{ borderRadius: 12, borderWidth: 1, borderColor: colors.border, overflow: 'hidden' }} data-testid="platform-settings-service-table" testID="platform-settings-service-table">
            <View style={{ flexDirection: 'row', backgroundColor: colors.bgSoft, paddingHorizontal: 10, paddingVertical: 8 }}>
              <Text style={{ flex: 1.2, color: colors.textMuted, fontSize: 11, fontWeight: '800' }}>Service</Text>
              <Text style={{ flex: 1, color: colors.textMuted, fontSize: 11, fontWeight: '800' }}>Status</Text>
              <Text style={{ flex: 1.8, color: colors.textMuted, fontSize: 11, fontWeight: '800' }}>Mapped source</Text>
            </View>
            {serviceRows.map((row, idx) => (
              <View key={row.key} style={{ flexDirection: 'row', paddingHorizontal: 10, paddingVertical: 9, borderTopWidth: idx === 0 ? 0 : 1, borderTopColor: colors.border, backgroundColor: idx % 2 === 0 ? 'transparent' : `${colors.textMuted}08` }} data-testid={`platform-settings-service-row-${row.key}`} testID={`platform-settings-service-row-${row.key}`}>
                <Text style={{ flex: 1.2, color: colors.text, fontSize: 11, fontWeight: '700' }}>{row.label}</Text>
                <Text style={{ flex: 1, color: statusToTone(row.value) === 'critical' ? colors.error : statusToTone(row.value) === 'warning' ? colors.warning : colors.successText, fontSize: 11, fontWeight: '800', textTransform: 'uppercase' }}>
                  {String(row.value)}
                </Text>
                <Text style={{ flex: 1.8, color: colors.textMuted, fontSize: 10 }}>{row.source}</Text>
              </View>
            ))}
          </View>
        </SectionCard>

        <SectionCard colors={colors} testId="platform-settings-maintenance-section">
          <SectionTitle icon="construct" title="2) Maintenance Management System" subtitle="Scheduler-backed maintenance windows with status gating and read-only controls." colors={colors} testId="platform-settings-maintenance-title" />

          <View style={{ flexDirection: isMobile ? 'column' : 'row', gap: 10 }}>
            <View style={{ flex: 1, gap: 8 }}>
              <Text style={{ color: colors.textMuted, fontSize: 11, fontWeight: '700' }}>System status</Text>
              <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
                {['ONLINE', 'MAINTENANCE', 'DEGRADED', 'OUTAGE'].map((value) => (
                  <SoftButton
                    key={value}
                    onPress={() => setStatusDraft((prev) => ({ ...prev, status: value }))}
                    label={value}
                    colors={colors}
                    testId={`platform-settings-status-option-${value.toLowerCase()}`}
                    disabled={savingKey === 'save-status'}
                  />
                ))}
              </View>
              <TextInput
                value={statusDraft.reason}
                onChangeText={(text) => setStatusDraft((prev) => ({ ...prev, reason: text }))}
                placeholder="Status reason"
                placeholderTextColor={colors.textMuted}
                style={{ borderRadius: 10, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bgSoft, color: colors.text, paddingHorizontal: 10, paddingVertical: 9, fontSize: 12 }}
                data-testid="platform-settings-status-reason-input"
                testID="platform-settings-status-reason-input"
              />
              <PrimaryButton onPress={saveStatusAction} label={savingKey === 'save-status' ? 'Saving...' : 'Apply status'} colors={colors} testId="platform-settings-save-status-button" disabled={savingKey === 'save-status'} />
            </View>

            <View style={{ flex: 1, gap: 8 }}>
              <Text style={{ color: colors.textMuted, fontSize: 11, fontWeight: '700' }}>Maintenance window</Text>
              <TextInput value={maintenanceDraft.title} onChangeText={(text) => setMaintenanceDraft((prev) => ({ ...prev, title: text }))} placeholder="Maintenance title" placeholderTextColor={colors.textMuted} style={{ borderRadius: 10, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bgSoft, color: colors.text, paddingHorizontal: 10, paddingVertical: 9, fontSize: 12 }} data-testid="platform-settings-maintenance-title-input" testID="platform-settings-maintenance-title-input" />
              <TextInput value={maintenanceDraft.reason} onChangeText={(text) => setMaintenanceDraft((prev) => ({ ...prev, reason: text }))} placeholder="Maintenance description" placeholderTextColor={colors.textMuted} multiline style={{ borderRadius: 10, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bgSoft, color: colors.text, paddingHorizontal: 10, paddingVertical: 9, minHeight: 72, textAlignVertical: 'top', fontSize: 12 }} data-testid="platform-settings-maintenance-reason-input" testID="platform-settings-maintenance-reason-input" />
              <View style={{ flexDirection: isMobile ? 'column' : 'row', gap: 8 }}>
                <TextInput value={maintenanceDraft.starts_at} onChangeText={(text) => setMaintenanceDraft((prev) => ({ ...prev, starts_at: text }))} placeholder="Start (local datetime)" placeholderTextColor={colors.textMuted} style={{ flex: 1, borderRadius: 10, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bgSoft, color: colors.text, paddingHorizontal: 10, paddingVertical: 9, fontSize: 12 }} data-testid="platform-settings-maintenance-start-input" testID="platform-settings-maintenance-start-input" />
                <TextInput value={maintenanceDraft.ends_at} onChangeText={(text) => setMaintenanceDraft((prev) => ({ ...prev, ends_at: text }))} placeholder="End (local datetime)" placeholderTextColor={colors.textMuted} style={{ flex: 1, borderRadius: 10, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bgSoft, color: colors.text, paddingHorizontal: 10, paddingVertical: 9, fontSize: 12 }} data-testid="platform-settings-maintenance-end-input" testID="platform-settings-maintenance-end-input" />
              </View>

              <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
                <SoftButton onPress={() => setMaintenanceDraft((prev) => ({ ...prev, enabled: !prev.enabled }))} label={`Maintenance ${maintenanceDraft.enabled ? 'ON' : 'OFF'}`} colors={colors} testId="platform-settings-toggle-maintenance-enabled" />
                <SoftButton onPress={() => setMaintenanceDraft((prev) => ({ ...prev, allow_staff_read_only: !prev.allow_staff_read_only }))} label={`Read-only ${maintenanceDraft.allow_staff_read_only ? 'ON' : 'OFF'}`} colors={colors} testId="platform-settings-toggle-readonly" />
                <SoftButton onPress={() => setMaintenanceDraft((prev) => ({ ...prev, notify_users: !prev.notify_users }))} label={`Notify users ${maintenanceDraft.notify_users ? 'ON' : 'OFF'}`} colors={colors} testId="platform-settings-toggle-maintenance-notify" />
              </View>

              <PrimaryButton onPress={saveMaintenanceAction} label={savingKey === 'save-maintenance' ? 'Saving...' : 'Save maintenance window'} colors={colors} testId="platform-settings-save-maintenance-button" disabled={savingKey === 'save-maintenance'} />
            </View>
          </View>

          <UnsupportedModule
            title="Advanced maintenance metadata"
            details="Timezone variants, severity labels, affected modules matrix, internal/public/recovery notes preview are not currently persisted by the maintenance endpoint. Inputs are shown for roadmap visibility only."
            colors={colors}
            testId="platform-settings-maintenance-unsupported-note"
          />
        </SectionCard>

        <SectionCard colors={colors} testId="platform-settings-communication-section">
          <SectionTitle icon="megaphone" title="3) User Communication Center" subtitle="Broadcasts, templates, and send histories backed by live platform APIs." colors={colors} testId="platform-settings-communication-title" />
          <View style={{ gap: 8 }}>
            <TextInput value={broadcastDraft.title} onChangeText={(text) => setBroadcastDraft((prev) => ({ ...prev, title: text }))} placeholder="Broadcast title" placeholderTextColor={colors.textMuted} style={{ borderRadius: 10, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bgSoft, color: colors.text, paddingHorizontal: 10, paddingVertical: 9, fontSize: 12 }} data-testid="platform-settings-broadcast-title-input" testID="platform-settings-broadcast-title-input" />
            <TextInput value={broadcastDraft.message} onChangeText={(text) => setBroadcastDraft((prev) => ({ ...prev, message: text }))} placeholder="Broadcast message" placeholderTextColor={colors.textMuted} multiline style={{ borderRadius: 10, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bgSoft, color: colors.text, paddingHorizontal: 10, paddingVertical: 9, minHeight: 80, textAlignVertical: 'top', fontSize: 12 }} data-testid="platform-settings-broadcast-message-input" testID="platform-settings-broadcast-message-input" />
            <View style={{ flexDirection: 'row', gap: 8, flexWrap: 'wrap' }}>
              {['all_non_admin', 'all_users', 'staff_only'].map((audience) => (
                <SoftButton key={audience} onPress={() => setBroadcastDraft((prev) => ({ ...prev, audience: audience as any }))} label={audience} colors={colors} testId={`platform-settings-broadcast-audience-${audience}`} />
              ))}
              <PrimaryButton onPress={sendBroadcastAction} label={savingKey === 'send-broadcast' ? 'Sending...' : 'Send now'} colors={colors} testId="platform-settings-send-broadcast-button" disabled={savingKey === 'send-broadcast'} />
            </View>
          </View>

          {supported.templates ? (
            <View style={{ borderTopWidth: 1, borderColor: colors.border, paddingTop: 10, gap: 8 }} data-testid="platform-settings-template-panel" testID="platform-settings-template-panel">
              <Text style={{ color: colors.text, fontSize: 14, fontWeight: '800' }}>Template scheduler</Text>
              <View style={{ flexDirection: isMobile ? 'column' : 'row', gap: 8 }}>
                <TextInput value={templateDraft.name} onChangeText={(text) => setTemplateDraft((prev) => ({ ...prev, name: text }))} placeholder="Template name" placeholderTextColor={colors.textMuted} style={{ flex: 1, borderRadius: 10, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bgSoft, color: colors.text, paddingHorizontal: 10, paddingVertical: 9, fontSize: 12 }} data-testid="platform-settings-template-name-input" testID="platform-settings-template-name-input" />
                <TextInput value={templateDraft.title} onChangeText={(text) => setTemplateDraft((prev) => ({ ...prev, title: text }))} placeholder="Template title" placeholderTextColor={colors.textMuted} style={{ flex: 1, borderRadius: 10, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bgSoft, color: colors.text, paddingHorizontal: 10, paddingVertical: 9, fontSize: 12 }} data-testid="platform-settings-template-title-input" testID="platform-settings-template-title-input" />
              </View>
              <TextInput value={templateDraft.message} onChangeText={(text) => setTemplateDraft((prev) => ({ ...prev, message: text }))} placeholder="Template body" placeholderTextColor={colors.textMuted} multiline style={{ borderRadius: 10, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bgSoft, color: colors.text, paddingHorizontal: 10, paddingVertical: 9, minHeight: 72, textAlignVertical: 'top', fontSize: 12 }} data-testid="platform-settings-template-message-input" testID="platform-settings-template-message-input" />
              <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
                {['one_time', 'daily', 'weekly'].map((schedule) => (
                  <SoftButton key={schedule} onPress={() => setTemplateDraft((prev) => ({ ...prev, schedule_type: schedule as any }))} label={schedule} colors={colors} testId={`platform-settings-template-schedule-${schedule}`} />
                ))}
                <SoftButton onPress={() => setTemplateDraft((prev) => ({ ...prev, in_app: !prev.in_app }))} label={`In-app ${templateDraft.in_app ? 'ON' : 'OFF'}`} colors={colors} testId="platform-settings-template-toggle-inapp" />
                <SoftButton onPress={() => setTemplateDraft((prev) => ({ ...prev, email: !prev.email }))} label={`Email ${templateDraft.email ? 'ON' : 'OFF'}`} colors={colors} testId="platform-settings-template-toggle-email" />
                <PrimaryButton onPress={createTemplateAction} label={savingKey === 'create-template' ? 'Creating...' : 'Create template'} colors={colors} testId="platform-settings-create-template-button" disabled={savingKey === 'create-template'} />
              </View>

              {templates.slice(0, 6).map((tpl: any, idx: number) => (
                <View key={tpl?.template_id || idx} style={{ borderWidth: 1, borderColor: colors.border, borderRadius: 10, padding: 10, gap: 6, backgroundColor: `${colors.textMuted}08` }} data-testid={`platform-settings-template-row-${idx}`} testID={`platform-settings-template-row-${idx}`}>
                  <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 6 }}>
                    <Text style={{ color: colors.text, fontSize: 12, fontWeight: '800' }}>{tpl?.name || 'Unnamed'}</Text>
                    <StatusChip value={tpl?.enabled ? 'enabled' : 'disabled'} colors={colors} testId={`platform-settings-template-status-${idx}`} />
                  </View>
                  <Text style={{ color: colors.textMuted, fontSize: 11 }}>{tpl?.title || ''}</Text>
                  <View style={{ flexDirection: 'row', gap: 8, flexWrap: 'wrap' }}>
                    <SoftButton onPress={() => dispatchTemplateNow(String(tpl?.template_id || ''))} label="Dispatch" colors={colors} testId={`platform-settings-template-dispatch-${idx}`} disabled={savingKey !== ''} />
                    <SoftButton onPress={() => disableTemplateNow(String(tpl?.template_id || ''))} label="Disable" colors={colors} testId={`platform-settings-template-disable-${idx}`} disabled={savingKey !== ''} danger />
                  </View>
                </View>
              ))}
            </View>
          ) : (
            <UnsupportedModule title="Template scheduler" details="Announcement template APIs are unavailable, so template controls are hidden." colors={colors} testId="platform-settings-template-unsupported" />
          )}

          <UnsupportedModule title="Targeting dimensions" details="Region/country/plan/role segmentation, rich-text editor, and open/click tracking are not exposed by current communication APIs." colors={colors} testId="platform-settings-communication-unsupported-note" />
        </SectionCard>

        <SectionCard colors={colors} testId="platform-settings-config-section">
          <SectionTitle icon="settings" title="4) Platform Configuration Management" subtitle="Live feature toggles, notification channels, and security alert policy controls." colors={colors} testId="platform-settings-config-title" />

          <View style={{ gap: 8 }}>
            <Text style={{ color: colors.text, fontSize: 13, fontWeight: '800' }} data-testid="platform-settings-feature-toggles-heading" testID="platform-settings-feature-toggles-heading">Feature toggles</Text>
            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
              {Object.entries(controlState?.feature_toggles || {}).map(([key, value]) => (
                <SoftButton key={key} onPress={() => toggleFeatureAction(key)} label={`${key}: ${value ? 'ON' : 'OFF'}`} colors={colors} testId={`platform-settings-feature-toggle-${key}`} disabled={savingKey === `toggle-feature-${key}`} />
              ))}
            </View>

            <Text style={{ color: colors.text, fontSize: 13, fontWeight: '800', marginTop: 6 }} data-testid="platform-settings-channel-heading" testID="platform-settings-channel-heading">Notification channels</Text>
            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
              {(['in_app', 'email', 'sms', 'push'] as const).map((key) => (
                <SoftButton key={key} onPress={() => setChannelDraft((prev) => ({ ...prev, [key]: !prev[key] }))} label={`${key}: ${channelDraft[key] ? 'ON' : 'OFF'}`} colors={colors} testId={`platform-settings-channel-toggle-${key}`} />
              ))}
              <PrimaryButton onPress={saveChannelsAction} label={savingKey === 'save-channels' ? 'Saving...' : 'Save channels'} colors={colors} testId="platform-settings-save-channels-button" disabled={savingKey === 'save-channels'} />
            </View>

            <Text style={{ color: colors.text, fontSize: 13, fontWeight: '800', marginTop: 6 }} data-testid="platform-settings-security-alert-heading" testID="platform-settings-security-alert-heading">Incident alert policy</Text>
            <View style={{ flexDirection: isMobile ? 'column' : 'row', gap: 8 }}>
              <TextInput value={String(securityConfigDraft.threshold)} onChangeText={(text) => setSecurityConfigDraft((prev) => ({ ...prev, threshold: Number(text || 0) }))} placeholder="Threshold" placeholderTextColor={colors.textMuted} style={{ flex: 1, borderRadius: 10, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bgSoft, color: colors.text, paddingHorizontal: 10, paddingVertical: 9, fontSize: 12 }} data-testid="platform-settings-security-threshold-input" testID="platform-settings-security-threshold-input" />
              <TextInput value={String(securityConfigDraft.window_minutes)} onChangeText={(text) => setSecurityConfigDraft((prev) => ({ ...prev, window_minutes: Number(text || 0) }))} placeholder="Window (minutes)" placeholderTextColor={colors.textMuted} style={{ flex: 1, borderRadius: 10, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bgSoft, color: colors.text, paddingHorizontal: 10, paddingVertical: 9, fontSize: 12 }} data-testid="platform-settings-security-window-input" testID="platform-settings-security-window-input" />
              <TextInput value={String(securityConfigDraft.cooldown_minutes)} onChangeText={(text) => setSecurityConfigDraft((prev) => ({ ...prev, cooldown_minutes: Number(text || 0) }))} placeholder="Cooldown (minutes)" placeholderTextColor={colors.textMuted} style={{ flex: 1, borderRadius: 10, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bgSoft, color: colors.text, paddingHorizontal: 10, paddingVertical: 9, fontSize: 12 }} data-testid="platform-settings-security-cooldown-input" testID="platform-settings-security-cooldown-input" />
            </View>
            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
              <SoftButton onPress={() => setSecurityConfigDraft((prev) => ({ ...prev, enabled: !prev.enabled }))} label={`Enabled: ${securityConfigDraft.enabled ? 'YES' : 'NO'}`} colors={colors} testId="platform-settings-security-enabled-toggle" />
              <SoftButton onPress={() => setSecurityConfigDraft((prev) => ({ ...prev, email_enabled: !prev.email_enabled }))} label={`Email alerts: ${securityConfigDraft.email_enabled ? 'YES' : 'NO'}`} colors={colors} testId="platform-settings-security-email-toggle" />
              <PrimaryButton onPress={saveSecurityConfigAction} label={savingKey === 'save-security-config' ? 'Saving...' : 'Save policy'} colors={colors} testId="platform-settings-security-save-button" disabled={savingKey === 'save-security-config'} />
              <SoftButton onPress={runSecurityTestAction} label={savingKey === 'run-security-test' ? 'Testing...' : 'Run test'} colors={colors} testId="platform-settings-security-test-button" disabled={savingKey === 'run-security-test'} />
            </View>
          </View>

          <UnsupportedModule title="Restricted secure configs" details="Environment variables, raw credentials, and secret tokens are intentionally not exposed in UI. RBAC-safe controls only." colors={colors} testId="platform-settings-secure-config-note" />
        </SectionCard>

        <SectionCard colors={colors} testId="platform-settings-feature-flags-section">
          <SectionTitle icon="flask" title="5) Feature Flag Management" subtitle="Backed by /api/admin/feature-flags with safe upsert controls and audit coverage." colors={colors} testId="platform-settings-feature-flags-title" />

          {supported.featureFlags ? (
            <>
              <UnsupportedModule title="Feature-flag writes policy gated" details="This environment currently blocks feature-flag mutation endpoint under production safety policy. Read-only listing remains active; use Feature Toggles above for supported on/off controls." colors={colors} testId="platform-settings-feature-flag-write-policy-note" />

              <View style={{ borderWidth: 1, borderColor: colors.border, borderRadius: 12, overflow: 'hidden' }} data-testid="platform-settings-feature-flag-table" testID="platform-settings-feature-flag-table">
                <View style={{ flexDirection: 'row', backgroundColor: colors.bgSoft, paddingHorizontal: 10, paddingVertical: 8 }}>
                  <Text style={{ flex: 1.2, color: colors.textMuted, fontSize: 11, fontWeight: '800' }}>Key</Text>
                  <Text style={{ flex: 0.8, color: colors.textMuted, fontSize: 11, fontWeight: '800' }}>Enabled</Text>
                  <Text style={{ flex: 1.4, color: colors.textMuted, fontSize: 11, fontWeight: '800' }}>Description</Text>
                </View>
                {featureFlags.slice(0, 15).map((flag: any, idx: number) => (
                  <View key={`${flag?.key || 'flag'}-${idx}`} style={{ flexDirection: 'row', paddingHorizontal: 10, paddingVertical: 9, borderTopWidth: idx === 0 ? 0 : 1, borderTopColor: colors.border }} data-testid={`platform-settings-feature-flag-row-${idx}`} testID={`platform-settings-feature-flag-row-${idx}`}>
                    <Text style={{ flex: 1.2, color: colors.text, fontSize: 11, fontWeight: '700' }}>{flag?.key || '--'}</Text>
                    <Text style={{ flex: 0.8, color: flag?.enabled ? colors.successText : colors.error, fontSize: 11, fontWeight: '800' }}>{flag?.enabled ? 'ON' : 'OFF'}</Text>
                    <Text style={{ flex: 1.4, color: colors.textMuted, fontSize: 11 }}>{flag?.description || '—'}</Text>
                  </View>
                ))}
                {featureFlags.length === 0 && <Text style={{ color: colors.textMuted, padding: 12, fontSize: 11 }} data-testid="platform-settings-feature-flag-empty" testID="platform-settings-feature-flag-empty">No feature flags returned from API.</Text>}
              </View>
            </>
          ) : (
            <UnsupportedModule title="Feature flags API not available" details="Flag controls are hidden because /api/admin/feature-flags failed in this environment." colors={colors} testId="platform-settings-feature-flag-unsupported" />
          )}

          <UnsupportedModule title="Advanced rollout controls" details="Gradual rollout, dependency graph checks, and region/user-group rollout are not exposed by current feature flag contracts." colors={colors} testId="platform-settings-feature-flag-rollout-note" />
        </SectionCard>

        <SectionCard colors={colors} testId="platform-settings-audit-section">
          <SectionTitle icon="document-text" title="6) Audit & Activity Logs" subtitle="Searchable, sortable, paginated, and exportable admin activity from platform control audit APIs." colors={colors} testId="platform-settings-audit-title" />
          <View style={{ flexDirection: isMobile ? 'column' : 'row', gap: 8 }}>
            <TextInput value={auditSearch} onChangeText={(text) => { setAuditSearch(text); setAuditPage(1); }} placeholder="Search action, actor, metadata" placeholderTextColor={colors.textMuted} style={{ flex: 1, borderRadius: 10, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bgSoft, color: colors.text, paddingHorizontal: 10, paddingVertical: 9, fontSize: 12 }} data-testid="platform-settings-audit-search-input" testID="platform-settings-audit-search-input" />
            <View style={{ flexDirection: 'row', gap: 8, flexWrap: 'wrap' }}>
              {(['created_at', 'action', 'actor_email', 'status'] as const).map((key) => (
                <SoftButton key={key} onPress={() => setAuditSortKey(key)} label={key} colors={colors} testId={`platform-settings-audit-sort-key-${key}`} />
              ))}
              <SoftButton onPress={() => setAuditSortDir((prev) => (prev === 'asc' ? 'desc' : 'asc'))} label={auditSortDir.toUpperCase()} colors={colors} testId="platform-settings-audit-sort-direction" />
            </View>
          </View>

          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
            {Object.entries(auditColumns).map(([key, enabled]) => (
              <SoftButton key={key} onPress={() => setAuditColumns((prev) => ({ ...prev, [key]: !enabled }))} label={`${enabled ? 'Hide' : 'Show'} ${key}`} colors={colors} testId={`platform-settings-audit-column-toggle-${key}`} />
            ))}
            <SoftButton onPress={() => exportAuditAction('csv')} label={savingKey === 'export-audit-csv' ? 'Exporting...' : 'Export CSV'} colors={colors} testId="platform-settings-export-audit-csv-button" disabled={savingKey === 'export-audit-csv'} />
            <SoftButton onPress={() => exportAuditAction('json')} label={savingKey === 'export-audit-json' ? 'Exporting...' : 'Export JSON'} colors={colors} testId="platform-settings-export-audit-json-button" disabled={savingKey === 'export-audit-json'} />
          </View>

          <View style={{ borderWidth: 1, borderColor: colors.border, borderRadius: 12, overflow: 'hidden' }} data-testid="platform-settings-audit-grid" testID="platform-settings-audit-grid">
            <View style={{ flexDirection: 'row', backgroundColor: colors.bgSoft, paddingHorizontal: 10, paddingVertical: 8 }}>
              {auditColumns.created_at && <Text style={{ flex: 1, color: colors.textMuted, fontSize: 10, fontWeight: '800' }}>Timestamp</Text>}
              {auditColumns.action && <Text style={{ flex: 1, color: colors.textMuted, fontSize: 10, fontWeight: '800' }}>Action</Text>}
              {auditColumns.actor_email && <Text style={{ flex: 1, color: colors.textMuted, fontSize: 10, fontWeight: '800' }}>Admin</Text>}
              {auditColumns.status && <Text style={{ flex: 0.7, color: colors.textMuted, fontSize: 10, fontWeight: '800' }}>Status</Text>}
              {auditColumns.metadata && <Text style={{ flex: 1.5, color: colors.textMuted, fontSize: 10, fontWeight: '800' }}>Metadata</Text>}
            </View>
            {pagedAuditRows.map((item: any, idx: number) => (
              <View key={`${item?.audit_id || 'audit'}-${idx}`} style={{ flexDirection: 'row', paddingHorizontal: 10, paddingVertical: 9, borderTopWidth: idx === 0 ? 0 : 1, borderTopColor: colors.border, backgroundColor: idx % 2 === 0 ? 'transparent' : `${colors.textMuted}08` }} data-testid={`platform-settings-audit-row-${idx}`} testID={`platform-settings-audit-row-${idx}`}>
                {auditColumns.created_at && <Text style={{ flex: 1, color: colors.text, fontSize: 10 }}>{formatDateTime(item?.created_at)}</Text>}
                {auditColumns.action && <Text style={{ flex: 1, color: colors.text, fontSize: 10, fontWeight: '700' }}>{item?.action || '--'}</Text>}
                {auditColumns.actor_email && <Text style={{ flex: 1, color: colors.textMuted, fontSize: 10 }}>{item?.actor_email || '--'}</Text>}
                {auditColumns.status && <Text style={{ flex: 0.7, color: statusToTone(item?.status) === 'critical' ? colors.error : statusToTone(item?.status) === 'warning' ? colors.warning : colors.successText, fontSize: 10, fontWeight: '800' }}>{String(item?.status || 'n/a').toUpperCase()}</Text>}
                {auditColumns.metadata && <Text style={{ flex: 1.5, color: colors.textMuted, fontSize: 10 }} numberOfLines={2}>{JSON.stringify(item?.metadata || {}).slice(0, 120)}</Text>}
              </View>
            ))}
            {pagedAuditRows.length === 0 && <Text style={{ color: colors.textMuted, padding: 12, fontSize: 11 }} data-testid="platform-settings-audit-empty" testID="platform-settings-audit-empty">No audit logs for the current filter.</Text>}
          </View>

          <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
            <Text style={{ color: colors.textMuted, fontSize: 11 }} data-testid="platform-settings-audit-pagination-meta" testID="platform-settings-audit-pagination-meta">Page {safePage} of {totalPages} • Rows {filteredAuditRows.length}</Text>
            <View style={{ flexDirection: 'row', gap: 8 }}>
              <SoftButton onPress={() => setAuditPage((p) => Math.max(1, p - 1))} label="Prev" colors={colors} testId="platform-settings-audit-prev-page" disabled={safePage <= 1} />
              <SoftButton onPress={() => setAuditPage((p) => Math.min(totalPages, p + 1))} label="Next" colors={colors} testId="platform-settings-audit-next-page" disabled={safePage >= totalPages} />
            </View>
          </View>
        </SectionCard>

        <SectionCard colors={colors} testId="platform-settings-incident-section">
          <SectionTitle icon="warning" title="7) Incident Management" subtitle="Operate parity incidents and inspect security incident streams from active production APIs." colors={colors} testId="platform-settings-incident-title" />
          <View style={{ flexDirection: 'row', gap: 8, flexWrap: 'wrap' }}>
            <PrimaryButton onPress={runParityAuditAction} label={savingKey === 'run-parity-audit' ? 'Running...' : 'Run parity audit'} colors={colors} testId="platform-settings-run-parity-audit-button" disabled={savingKey === 'run-parity-audit'} />
            {!!latestIncident?.incident_id && (
              <>
                <SoftButton onPress={() => acknowledgeParityIncident(String(latestIncident.incident_id)).then(() => loadData('silent'))} label="Acknowledge" colors={colors} testId="platform-settings-incident-ack-button" disabled={savingKey !== ''} />
                <SoftButton onPress={() => resolveParityIncident(String(latestIncident.incident_id), resolveNote).then(() => loadData('silent'))} label="Resolve" colors={colors} testId="platform-settings-incident-resolve-button" disabled={savingKey !== ''} danger />
              </>
            )}
          </View>
          <TextInput value={resolveNote} onChangeText={setResolveNote} placeholder="Resolve note (optional)" placeholderTextColor={colors.textMuted} style={{ borderRadius: 10, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bgSoft, color: colors.text, paddingHorizontal: 10, paddingVertical: 9, fontSize: 12 }} data-testid="platform-settings-incident-resolve-note-input" testID="platform-settings-incident-resolve-note-input" />

          <View style={{ borderWidth: 1, borderColor: colors.border, borderRadius: 12, padding: 10, gap: 6, backgroundColor: `${colors.textMuted}08` }} data-testid="platform-settings-latest-incident-card" testID="platform-settings-latest-incident-card">
            <Text style={{ color: colors.text, fontSize: 12, fontWeight: '800' }}>Latest open incident</Text>
            <Text style={{ color: colors.textMuted, fontSize: 11 }}>ID: {latestIncident?.incident_id || 'none'}</Text>
            <Text style={{ color: colors.textMuted, fontSize: 11 }}>Status: {latestIncident?.status || 'none_open'}</Text>
            <Text style={{ color: colors.textMuted, fontSize: 11 }}>Severity: {latestIncident?.severity || 'n/a'}</Text>
            <Text style={{ color: colors.textMuted, fontSize: 11 }}>Created: {formatDateTime(latestIncident?.created_at)}</Text>
          </View>

          <View style={{ borderWidth: 1, borderColor: colors.border, borderRadius: 12, overflow: 'hidden' }} data-testid="platform-settings-security-recent-table" testID="platform-settings-security-recent-table">
            <View style={{ flexDirection: 'row', backgroundColor: colors.bgSoft, paddingHorizontal: 10, paddingVertical: 8 }}>
              <Text style={{ flex: 0.8, color: colors.textMuted, fontSize: 10, fontWeight: '800' }}>Status</Text>
              <Text style={{ flex: 1.4, color: colors.textMuted, fontSize: 10, fontWeight: '800' }}>Path</Text>
              <Text style={{ flex: 1.4, color: colors.textMuted, fontSize: 10, fontWeight: '800' }}>Timestamp</Text>
            </View>
            {securityRecent.slice(0, 8).map((incident: any, idx: number) => (
              <View key={`${incident?.ts || 'inc'}-${idx}`} style={{ flexDirection: 'row', borderTopWidth: idx === 0 ? 0 : 1, borderTopColor: colors.border, paddingHorizontal: 10, paddingVertical: 8 }} data-testid={`platform-settings-security-recent-row-${idx}`} testID={`platform-settings-security-recent-row-${idx}`}>
                <Text style={{ flex: 0.8, color: colors.text, fontSize: 10, fontWeight: '700' }}>{incident?.status || '--'}</Text>
                <Text style={{ flex: 1.4, color: colors.textMuted, fontSize: 10 }} numberOfLines={1}>{incident?.path || '--'}</Text>
                <Text style={{ flex: 1.4, color: colors.textMuted, fontSize: 10 }}>{formatDateTime(incident?.ts)}</Text>
              </View>
            ))}
            {securityRecent.length === 0 && <Text style={{ color: colors.textMuted, padding: 10, fontSize: 11 }} data-testid="platform-settings-security-recent-empty" testID="platform-settings-security-recent-empty">No recent security incidents returned.</Text>}
          </View>
        </SectionCard>

        <SectionCard colors={colors} testId="platform-settings-announcements-section">
          <SectionTitle icon="notifications" title="8) Platform Announcement System" subtitle="Global announcement feed plus legal and security broadcast histories." colors={colors} testId="platform-settings-announcements-title" />
          <View style={{ gap: 8 }}>
            <TextInput value={announcementDraft.title} onChangeText={(text) => setAnnouncementDraft((prev) => ({ ...prev, title: text }))} placeholder="Announcement title" placeholderTextColor={colors.textMuted} style={{ borderRadius: 10, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bgSoft, color: colors.text, paddingHorizontal: 10, paddingVertical: 9, fontSize: 12 }} data-testid="platform-settings-announcement-title-input" testID="platform-settings-announcement-title-input" />
            <TextInput value={announcementDraft.message} onChangeText={(text) => setAnnouncementDraft((prev) => ({ ...prev, message: text }))} placeholder="Announcement message" placeholderTextColor={colors.textMuted} multiline style={{ borderRadius: 10, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bgSoft, color: colors.text, paddingHorizontal: 10, paddingVertical: 9, minHeight: 74, textAlignVertical: 'top', fontSize: 12 }} data-testid="platform-settings-announcement-message-input" testID="platform-settings-announcement-message-input" />
            <View style={{ flexDirection: 'row', gap: 8, flexWrap: 'wrap' }}>
              <PrimaryButton onPress={createAnnouncementAction} label={savingKey === 'create-announcement' ? 'Creating...' : 'Create announcement'} colors={colors} testId="platform-settings-create-announcement-button" disabled={savingKey === 'create-announcement'} />
            </View>
          </View>

          <View style={{ gap: 8 }}>
            {announcements.slice(0, 6).map((item: any, idx: number) => (
              <View key={item?.id || idx} style={{ borderWidth: 1, borderColor: colors.border, borderRadius: 10, padding: 10, gap: 5 }} data-testid={`platform-settings-announcement-row-${idx}`} testID={`platform-settings-announcement-row-${idx}`}>
                <Text style={{ color: colors.text, fontSize: 12, fontWeight: '800' }}>{item?.title || '--'}</Text>
                <Text style={{ color: colors.textMuted, fontSize: 11, lineHeight: 16 }}>{item?.message || ''}</Text>
                <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
                  <Text style={{ color: colors.textMuted, fontSize: 10 }}>{formatDateTime(item?.created_at)}</Text>
                  <SoftButton onPress={() => deleteAnnouncement(String(item?.id || '')) .then(() => loadData('silent'))} label="Delete" colors={colors} testId={`platform-settings-delete-announcement-${idx}`} danger />
                </View>
              </View>
            ))}
            {announcements.length === 0 && <Text style={{ color: colors.textMuted, fontSize: 11 }} data-testid="platform-settings-announcements-empty" testID="platform-settings-announcements-empty">No platform announcements found.</Text>}
          </View>

          <View style={{ borderTopWidth: 1, borderColor: colors.border, paddingTop: 10, gap: 8 }}>
            <Text style={{ color: colors.text, fontSize: 13, fontWeight: '800' }} data-testid="platform-settings-broadcast-history-title" testID="platform-settings-broadcast-history-title">Broadcast history snapshot</Text>
            <Text style={{ color: colors.textMuted, fontSize: 11 }} data-testid="platform-settings-broadcast-history-legal-count" testID="platform-settings-broadcast-history-legal-count">Legal notices: {legalBroadcasts.length}</Text>
            <Text style={{ color: colors.textMuted, fontSize: 11 }} data-testid="platform-settings-broadcast-history-security-count" testID="platform-settings-broadcast-history-security-count">Security broadcasts: {securityBroadcasts.length}</Text>
          </View>

          <UnsupportedModule title="Regional/sticky banner modes" details="Regional targeting, sticky banner rules, and auto-expiration policies are not exposed by current announcement contracts." colors={colors} testId="platform-settings-announcement-unsupported-note" />
        </SectionCard>

        <SectionCard colors={colors} testId="platform-settings-jobs-section">
          <SectionTitle icon="timer" title="9) Background Jobs & Task Monitoring" subtitle="Scheduler heartbeats and runtime cadence from enterprise standard status payloads." colors={colors} testId="platform-settings-jobs-title" />
          {supported.enterpriseStandard ? (
            <View style={{ borderWidth: 1, borderColor: colors.border, borderRadius: 12, overflow: 'hidden' }} data-testid="platform-settings-jobs-grid" testID="platform-settings-jobs-grid">
              <View style={{ flexDirection: 'row', backgroundColor: colors.bgSoft, paddingHorizontal: 10, paddingVertical: 8 }}>
                <Text style={{ flex: 1.2, color: colors.textMuted, fontSize: 10, fontWeight: '800' }}>Job ID</Text>
                <Text style={{ flex: 0.8, color: colors.textMuted, fontSize: 10, fontWeight: '800' }}>Status</Text>
                <Text style={{ flex: 1.2, color: colors.textMuted, fontSize: 10, fontWeight: '800' }}>Last run</Text>
              </View>
              {schedulerHeartbeats.map((row: any, idx: number) => (
                <View key={`${row?.job_id || idx}`} style={{ flexDirection: 'row', paddingHorizontal: 10, paddingVertical: 8, borderTopWidth: idx === 0 ? 0 : 1, borderTopColor: colors.border }} data-testid={`platform-settings-job-row-${idx}`} testID={`platform-settings-job-row-${idx}`}>
                  <Text style={{ flex: 1.2, color: colors.text, fontSize: 10 }}>{row?.job_id || '--'}</Text>
                  <Text style={{ flex: 0.8, color: statusToTone(row?.status) === 'critical' ? colors.error : statusToTone(row?.status) === 'warning' ? colors.warning : colors.successText, fontSize: 10, fontWeight: '800' }}>{String(row?.status || 'unknown').toUpperCase()}</Text>
                  <Text style={{ flex: 1.2, color: colors.textMuted, fontSize: 10 }}>{formatDateTime(row?.last_run)}</Text>
                </View>
              ))}
              {schedulerHeartbeats.length === 0 && <Text style={{ color: colors.textMuted, padding: 10, fontSize: 11 }} data-testid="platform-settings-jobs-empty" testID="platform-settings-jobs-empty">No scheduler heartbeat rows available.</Text>}
            </View>
          ) : (
            <UnsupportedModule title="Scheduler telemetry unavailable" details="Background job board hidden because enterprise standard status endpoint failed." colors={colors} testId="platform-settings-jobs-unsupported" />
          )}
        </SectionCard>

        <SectionCard colors={colors} testId="platform-settings-health-analytics-section">
          <SectionTitle icon="analytics" title="10) System Health & Analytics" subtitle="Operational analytics for error rate, latency, volume, uptime, queue, auth, notifications, and regional runtime indicators." colors={colors} testId="platform-settings-health-analytics-title" />

          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10 }}>
            <StatCard label="Error events (24h)" value={formatNumber(observabilityData?.application?.security_events_24h)} subtitle="Security + app anomalies" icon="bug" colors={colors} testId="platform-settings-health-kpi-errors" />
            <StatCard label="API latency (DB ms)" value={String(systemHealthData?.database?.latency_ms ?? '--')} subtitle="Backend latency proxy" icon="pulse" colors={colors} testId="platform-settings-health-kpi-latency" />
            <StatCard label="Request volume" value={formatNumber(observabilityData?.application?.api_snapshots_1h)} subtitle="Last hour snapshots" icon="trending-up" colors={colors} testId="platform-settings-health-kpi-requests" />
            <StatCard label="Notification success" value={`${liveServicesData?.email?.success_rate ?? '--'}%`} subtitle="Email pipeline success" icon="mail" colors={colors} testId="platform-settings-health-kpi-notif" />
            <StatCard label="Realtime success (30m)" value={`${liveServicesData?.realtime?.connect_success_rate_30m ?? '--'}%`} subtitle="WebSocket reconnect health" icon="radio" colors={colors} testId="platform-settings-health-kpi-realtime" />
            <StatCard label="Queue/rules enabled" value={formatNumber(liveServicesData?.scheduler?.rules_enabled)} subtitle="Notification automation rules" icon="git-network" colors={colors} testId="platform-settings-health-kpi-rules" />
          </View>

          <View style={{ borderWidth: 1, borderColor: colors.border, borderRadius: 12, padding: 10, gap: 6 }} data-testid="platform-settings-security-timeline-card" testID="platform-settings-security-timeline-card">
            <Text style={{ color: colors.text, fontSize: 12, fontWeight: '800' }}>Security timeline (24h hourly buckets)</Text>
            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6 }}>
              {asArray(securityTimelineData?.timeline).slice(-12).map((point: any, idx: number) => (
                <View key={`${point?.hour || idx}`} style={{ borderWidth: 1, borderColor: colors.border, borderRadius: 8, paddingHorizontal: 8, paddingVertical: 6, minWidth: 78, backgroundColor: `${colors.textMuted}08` }} data-testid={`platform-settings-security-timeline-bucket-${idx}`} testID={`platform-settings-security-timeline-bucket-${idx}`}>
                  <Text style={{ color: colors.textMuted, fontSize: 9 }}>{String(point?.hour || '').slice(11, 13)}:00</Text>
                  <Text style={{ color: colors.text, fontSize: 10, fontWeight: '700' }}>401: {formatNumber(point?.count_401)}</Text>
                  <Text style={{ color: colors.text, fontSize: 10, fontWeight: '700' }}>403: {formatNumber(point?.count_403)}</Text>
                </View>
              ))}
              {asArray(securityTimelineData?.timeline).length === 0 && <Text style={{ color: colors.textMuted, fontSize: 11 }} data-testid="platform-settings-security-timeline-empty" testID="platform-settings-security-timeline-empty">No timeline data for current window.</Text>}
            </View>
          </View>
        </SectionCard>

        <SectionCard colors={colors} testId="platform-settings-rule-center-section">
          <SectionTitle icon="options" title="Operational Rule Center" subtitle="Custom threshold rule CRUD from /api/admin/notification-rules." colors={colors} testId="platform-settings-rule-center-title" />
          {supported.notificationRules ? (
            <>
              <View style={{ flexDirection: isMobile ? 'column' : 'row', gap: 8 }}>
                <TextInput value={notificationRuleDraft.name} onChangeText={(text) => setNotificationRuleDraft((prev) => ({ ...prev, name: text }))} placeholder="Rule name" placeholderTextColor={colors.textMuted} style={{ flex: 1.4, borderRadius: 10, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bgSoft, color: colors.text, paddingHorizontal: 10, paddingVertical: 9, fontSize: 12 }} data-testid="platform-settings-rule-name-input" testID="platform-settings-rule-name-input" />
                <TextInput value={notificationRuleDraft.metric} onChangeText={(text) => setNotificationRuleDraft((prev) => ({ ...prev, metric: text }))} placeholder="Metric" placeholderTextColor={colors.textMuted} style={{ flex: 1, borderRadius: 10, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bgSoft, color: colors.text, paddingHorizontal: 10, paddingVertical: 9, fontSize: 12 }} data-testid="platform-settings-rule-metric-input" testID="platform-settings-rule-metric-input" />
                <TextInput value={notificationRuleDraft.operator} onChangeText={(text) => setNotificationRuleDraft((prev) => ({ ...prev, operator: text }))} placeholder="Operator" placeholderTextColor={colors.textMuted} style={{ flex: 0.8, borderRadius: 10, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bgSoft, color: colors.text, paddingHorizontal: 10, paddingVertical: 9, fontSize: 12 }} data-testid="platform-settings-rule-operator-input" testID="platform-settings-rule-operator-input" />
                <TextInput value={notificationRuleDraft.threshold} onChangeText={(text) => setNotificationRuleDraft((prev) => ({ ...prev, threshold: text }))} placeholder="Threshold" placeholderTextColor={colors.textMuted} style={{ flex: 0.8, borderRadius: 10, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bgSoft, color: colors.text, paddingHorizontal: 10, paddingVertical: 9, fontSize: 12 }} data-testid="platform-settings-rule-threshold-input" testID="platform-settings-rule-threshold-input" />
              </View>
              <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
                <PrimaryButton onPress={createNotificationRuleAction} label={savingKey === 'create-notification-rule' ? 'Creating...' : 'Create rule'} colors={colors} testId="platform-settings-create-rule-button" disabled={savingKey === 'create-notification-rule'} />
              </View>

              <View style={{ gap: 8 }}>
                {notificationRules.slice(0, 10).map((rule: any, idx: number) => (
                  <View key={rule?.rule_id || idx} style={{ borderWidth: 1, borderColor: colors.border, borderRadius: 10, padding: 10, gap: 6 }} data-testid={`platform-settings-rule-row-${idx}`} testID={`platform-settings-rule-row-${idx}`}>
                    <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 6 }}>
                      <Text style={{ color: colors.text, fontSize: 12, fontWeight: '800' }}>{rule?.name || '--'}</Text>
                      <StatusChip value={rule?.enabled ? 'enabled' : 'disabled'} colors={colors} testId={`platform-settings-rule-enabled-chip-${idx}`} />
                    </View>
                    <Text style={{ color: colors.textMuted, fontSize: 10 }}>
                      {rule?.condition?.metric} {rule?.condition?.operator} {rule?.condition?.threshold} • window {rule?.condition?.time_window_minutes}m • cooldown {rule?.cooldown_minutes}m
                    </Text>
                    <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
                      <SoftButton onPress={() => toggleNotificationRule(String(rule?.rule_id || '')).then(() => loadData('silent'))} label="Toggle" colors={colors} testId={`platform-settings-rule-toggle-${idx}`} />
                      <SoftButton onPress={() => testNotificationRule(String(rule?.rule_id || '')).then((result) => setInfo('info', result?.message || 'Rule test completed'))} label="Test" colors={colors} testId={`platform-settings-rule-test-${idx}`} />
                      <SoftButton onPress={() => deleteNotificationRule(String(rule?.rule_id || '')).then(() => loadData('silent'))} label="Delete" colors={colors} testId={`platform-settings-rule-delete-${idx}`} danger />
                    </View>
                  </View>
                ))}
              </View>
            </>
          ) : (
            <UnsupportedModule title="Notification rules module unavailable" details="Rule CRUD is hidden because /api/admin/notification-rules is unavailable." colors={colors} testId="platform-settings-rules-unsupported" />
          )}
        </SectionCard>
      </ScrollView>
    </View>
  );
}
