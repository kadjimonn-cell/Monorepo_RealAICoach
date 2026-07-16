import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  Platform,
  ScrollView,
  Switch,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useLocalSearchParams, useRouter } from 'expo-router';

import AppShell from '../AppShell';
import api from '../../services/api';
import { useTheme } from '../../context/ThemeContext';
import { useAuth } from '../../context/AuthContext';
import { useTranslation } from '../../hooks/useTranslation';
import { useAccessibility } from '../../context/AccessibilityContext';
import { PRESET_OPTIONS, useBackgroundBrightness } from '../../context/BackgroundBrightnessContext';
import { getDisplayPlan, normalizeRole } from '../../utils/subscription';
import { useGlobalPlatformState } from '../../hooks/useGlobalPlatformState';
import { GLSSection, useGLSBreakpoint } from '../layout/GlobalLayoutSystem';
import EnterpriseDisclaimerToken from '../tokens/EnterpriseDisclaimerToken';
import SettingsNovaAssistantPanel from '../settings/SettingsNovaAssistantPanel';

type SettingsSection =
  | 'workspace'
  | 'notifications'
  | 'aiBriefing'
  | 'novaAssistant'
  | 'security'
  | 'accessibility'
  | 'appearance'
  | 'platform';

interface NotificationPreferences {
  push_enabled: boolean;
  email_enabled: boolean;
  daily_briefing: boolean;
  practice_reminders: boolean;
  achievement_alerts: boolean;
  weekly_digest: boolean;
  team_updates: boolean;
  goal_reminders: boolean;
  coaching_nudges: boolean;
  quiet_hours_enabled: boolean;
  quiet_hours_start: string;
  quiet_hours_end: string;
}

interface BriefingPreferences {
  interests: string[];
  industry: string;
  briefing_time: string;
  include_news: boolean;
  include_tips: boolean;
  include_motivation: boolean;
}

type LayoutMode = 'centered' | 'full-width' | 'compact';

const DEFAULT_NOTIFICATION_PREFS: NotificationPreferences = {
  push_enabled: true,
  email_enabled: true,
  daily_briefing: true,
  practice_reminders: true,
  achievement_alerts: true,
  weekly_digest: true,
  team_updates: true,
  goal_reminders: true,
  coaching_nudges: true,
  quiet_hours_enabled: false,
  quiet_hours_start: '22:00',
  quiet_hours_end: '07:00',
};

const DEFAULT_BRIEFING_PREFS: BriefingPreferences = {
  interests: [],
  industry: '',
  briefing_time: '08:00',
  include_news: true,
  include_tips: true,
  include_motivation: true,
};

const formatDateTime = (value?: string | null) => {
  if (!value) return '—';
  try {
    return new Date(value).toLocaleString();
  } catch {
    return String(value);
  }
};

const normalizeError = (error: any, fallback: string) => {
  const detail = error?.response?.data?.detail;
  if (typeof detail === 'string') return detail;
  if (detail?.message) return String(detail.message);
  return error?.message || fallback;
};

export default function SettingsEnterprise() {
  const router = useRouter();
  const params = useLocalSearchParams<{ section?: string }>();
  const theme = useTheme();
  const { t } = useTranslation();
  const { user, isAuthenticated, logout } = useAuth();
  const { prefs, updatePref, resetAll, activeCount } = useAccessibility();
  const { brightness, setBrightness, preset, setPreset } = useBackgroundBrightness();
  const { state: gpsState, counts: gpsCounts, label } = useGlobalPlatformState();
  const { isMobile, isTablet } = useGLSBreakpoint();

  const C = theme.colors;
  const displayPlan = getDisplayPlan(user);
  const isAdmin = normalizeRole(user?.role) === 'admin' || user?.is_admin;

  const tx = useCallback(
    (key: string, fallback: string) => {
      const localized = t(key);
      const safeFallback = localized === key ? fallback : localized;
      return label(key, safeFallback);
    },
    [label, t],
  );

  const sectionItems = useMemo(
    () => [
      { key: 'workspace' as const, icon: 'grid-outline', title: tx('settingsV2.sidebar.workspace', 'Workspace') },
      { key: 'notifications' as const, icon: 'notifications-outline', title: tx('settingsV2.sidebar.notifications', 'Notifications') },
      { key: 'aiBriefing' as const, icon: 'sparkles-outline', title: tx('settingsV2.sidebar.aiBriefing', 'AI Briefing') },
      { key: 'novaAssistant' as const, icon: 'chatbubble-ellipses-outline', title: tx('settingsV2.sidebar.novaAssistant', 'Nova Assistant') },
      { key: 'security' as const, icon: 'shield-checkmark-outline', title: tx('settingsV2.sidebar.security', 'Security') },
      { key: 'accessibility' as const, icon: 'accessibility-outline', title: tx('settingsV2.sidebar.accessibility', 'Accessibility') },
      { key: 'appearance' as const, icon: 'color-palette-outline', title: tx('settingsV2.sidebar.appearance', 'Appearance') },
      { key: 'platform' as const, icon: 'construct-outline', title: tx('settingsV2.sidebar.platform', 'Platform') },
    ],
    [tx],
  );

  const visibleSectionItems = useMemo(
    () => sectionItems.filter((item) => item.key !== 'platform' || isAdmin),
    [isAdmin, sectionItems],
  );

  const [activeSection, setActiveSection] = useState<SettingsSection>('workspace');
  const [loading, setLoading] = useState(false);
  const [notifSaving, setNotifSaving] = useState(false);
  const [briefingSaving, setBriefingSaving] = useState(false);
  const [layoutSaving, setLayoutSaving] = useState(false);

  const [notificationPrefs, setNotificationPrefs] = useState<NotificationPreferences>(DEFAULT_NOTIFICATION_PREFS);
  const [briefingPrefs, setBriefingPrefs] = useState<BriefingPreferences>(DEFAULT_BRIEFING_PREFS);
  const [interestsInput, setInterestsInput] = useState('');
  const [mfaEnabled, setMfaEnabled] = useState(false);

  const [layoutMode, setLayoutMode] = useState<LayoutMode>('centered');
  const [layoutResponsiveEnabled, setLayoutResponsiveEnabled] = useState(true);
  const [layoutUpdatedAt, setLayoutUpdatedAt] = useState<string | null>(null);

  const [settingsIntegrationsLoading, setSettingsIntegrationsLoading] = useState(false);
  const [settingsIntegrationsError, setSettingsIntegrationsError] = useState<string | null>(null);
  const [settingsAvailableIntegrations, setSettingsAvailableIntegrations] = useState<any[]>([]);
  const [settingsConnectedIntegrations, setSettingsConnectedIntegrations] = useState<any[]>([]);
  const [settingsIntegrationStats, setSettingsIntegrationStats] = useState<any>(null);

  const [status, setStatus] = useState<{ type: 'success' | 'error'; message: string } | null>(null);

  useEffect(() => {
    const requested = String(params.section || '').trim();
    if (!requested) return;
    if (visibleSectionItems.some((item) => item.key === requested)) {
      setActiveSection(requested as SettingsSection);
    }
  }, [params.section, visibleSectionItems]);

  const loadNotificationPreferences = useCallback(async () => {
    try {
      const response = await api.get('/notifications/preferences');
      return response.data;
    } catch {
      const response = await api.get('/notifications/settings');
      return response.data;
    }
  }, []);

  const loadBriefingPreferences = useCallback(async () => {
    try {
      const response = await api.get('/ai-briefing/preferences');
      return response.data;
    } catch {
      return null;
    }
  }, []);

  const loadMfaStatus = useCallback(async () => {
    try {
      const response = await api.get('/auth/mfa/status');
      return Boolean(response.data?.mfa_enabled);
    } catch {
      return false;
    }
  }, []);

  const loadLayoutConfig = useCallback(async () => {
    if (!isAdmin) return null;
    try {
      const response = await api.get('/gps/admin/layout-config');
      return response.data;
    } catch {
      return null;
    }
  }, [isAdmin]);

  const loadSettingsIntegrations = useCallback(async () => {
    try {
      const [availableRes, connectedRes, statsRes] = await Promise.allSettled([
        api.get('/integrations/available'),
        api.get('/integrations/'),
        api.get('/integrations/dashboard/stats'),
      ]);

      return {
        available:
          availableRes.status === 'fulfilled' && Array.isArray(availableRes.value.data?.integrations)
            ? availableRes.value.data.integrations
            : [],
        connected:
          connectedRes.status === 'fulfilled' && Array.isArray(connectedRes.value.data?.integrations)
            ? connectedRes.value.data.integrations
            : [],
        stats: statsRes.status === 'fulfilled' ? statsRes.value.data || null : null,
        failed:
          availableRes.status === 'rejected' &&
          connectedRes.status === 'rejected' &&
          statsRes.status === 'rejected',
      };
    } catch {
      return {
        available: [],
        connected: [],
        stats: null,
        failed: true,
      };
    }
  }, []);

  const withSoftFallback = useCallback(async <T,>(loader: () => Promise<T>, fallback: T): Promise<T> => {
    try {
      return await loader();
    } catch {
      return fallback;
    }
  }, []);

  useEffect(() => {
    let mounted = true;

    const load = async () => {
      if (!isAuthenticated || !user?.user_id) {
        setLoading(false);
        return;
      }

      setLoading(true);
      setStatus(null);

      try {
        const [notifData, briefingData, mfaData, layoutData, integrationsData] = await Promise.all([
          withSoftFallback(loadNotificationPreferences, DEFAULT_NOTIFICATION_PREFS),
          withSoftFallback(loadBriefingPreferences, null),
          withSoftFallback(loadMfaStatus, false),
          withSoftFallback(loadLayoutConfig, null),
          withSoftFallback(loadSettingsIntegrations, { available: [], connected: [], stats: null, failed: true }),
        ]);

        if (!mounted) return;

        setNotificationPrefs({ ...DEFAULT_NOTIFICATION_PREFS, ...(notifData || {}) });

        const mergedBriefing = {
          ...DEFAULT_BRIEFING_PREFS,
          ...(briefingData || {}),
          interests: Array.isArray(briefingData?.interests) ? briefingData.interests : [],
        };
        setBriefingPrefs(mergedBriefing);
        setInterestsInput((mergedBriefing.interests || []).join(', '));
        setMfaEnabled(Boolean(mfaData));

        if (layoutData) {
          const nextMode = String(layoutData.layout_mode || 'centered').toLowerCase();
          if (nextMode === 'full-width' || nextMode === 'compact' || nextMode === 'centered') {
            setLayoutMode(nextMode);
          }
          setLayoutResponsiveEnabled(Boolean(layoutData.responsive_enabled ?? true));
          setLayoutUpdatedAt(layoutData.updated_at || null);
        }

        setSettingsAvailableIntegrations(integrationsData.available || []);
        setSettingsConnectedIntegrations(integrationsData.connected || []);
        setSettingsIntegrationStats(integrationsData.stats || null);
        setSettingsIntegrationsError(
          integrationsData.failed
            ? tx('settingsV2.workspace.integrations.loadError', 'Unable to load integrations telemetry right now.')
            : null,
        );
      } catch (error: any) {
        if (!mounted) return;
        setStatus({
          type: 'error',
          message: normalizeError(error, tx('settingsV2.common.loadError', 'Unable to load settings right now.')),
        });
      } finally {
        if (mounted) setLoading(false);
      }
    };

    load();

    return () => {
      mounted = false;
    };
  }, [
    isAuthenticated,
    loadBriefingPreferences,
    loadLayoutConfig,
    loadMfaStatus,
    loadNotificationPreferences,
    loadSettingsIntegrations,
    tx,
    user?.user_id,
    withSoftFallback,
  ]);

  const refreshSettingsIntegrations = useCallback(async () => {
    if (!user?.user_id) return;
    setSettingsIntegrationsLoading(true);
    const data = await loadSettingsIntegrations();
    setSettingsAvailableIntegrations(data.available || []);
    setSettingsConnectedIntegrations(data.connected || []);
    setSettingsIntegrationStats(data.stats || null);
    setSettingsIntegrationsError(
      data.failed ? tx('settingsV2.workspace.integrations.loadError', 'Unable to load integrations telemetry right now.') : null,
    );
    setSettingsIntegrationsLoading(false);
  }, [loadSettingsIntegrations, tx, user?.user_id]);

  useEffect(() => {
    if (!user?.user_id) return;
    const interval = setInterval(() => {
      void refreshSettingsIntegrations();
    }, 45000);
    return () => clearInterval(interval);
  }, [refreshSettingsIntegrations, user?.user_id]);

  useEffect(() => {
    if (!visibleSectionItems.find((item) => item.key === activeSection)) {
      setActiveSection(visibleSectionItems[0]?.key || 'workspace');
    }
  }, [activeSection, visibleSectionItems]);

  const handleLogout = useCallback(async () => {
    try {
      await logout();
    } finally {
      if (typeof window !== 'undefined') {
        window.location.href = '/auth/login?logout=1';
        return;
      }
      router.replace('/auth/login?logout=1');
    }
  }, [logout, router]);

  const saveNotifications = useCallback(async () => {
    setNotifSaving(true);
    setStatus(null);
    try {
      try {
        await api.post('/notifications/preferences', notificationPrefs);
      } catch {
        await api.put('/notifications/settings', notificationPrefs);
      }
      setStatus({
        type: 'success',
        message: tx('settingsV2.common.notificationsSaved', 'Notification preferences updated.'),
      });
    } catch (error: any) {
      setStatus({
        type: 'error',
        message: normalizeError(error, tx('settingsV2.common.saveError', 'Unable to save changes.')),
      });
    } finally {
      setNotifSaving(false);
    }
  }, [notificationPrefs, tx]);

  const saveBriefing = useCallback(async () => {
    setBriefingSaving(true);
    setStatus(null);
    try {
      const payload = {
        ...briefingPrefs,
        interests: interestsInput
          .split(',')
          .map((entry) => entry.trim())
          .filter(Boolean),
      };
      await api.post('/ai-briefing/preferences', payload);
      setBriefingPrefs((prev) => ({ ...prev, interests: payload.interests }));
      setInterestsInput(payload.interests.join(', '));
      setStatus({ type: 'success', message: tx('settingsV2.common.briefingSaved', 'Briefing preferences updated.') });
    } catch (error: any) {
      setStatus({
        type: 'error',
        message: normalizeError(error, tx('settingsV2.common.saveError', 'Unable to save changes.')),
      });
    } finally {
      setBriefingSaving(false);
    }
  }, [briefingPrefs, interestsInput, tx]);

  const saveLayoutConfig = useCallback(async () => {
    if (!isAdmin) return;
    setLayoutSaving(true);
    setStatus(null);
    try {
      const response = await api.put('/gps/admin/layout-config', {
        layout_mode: layoutMode,
        responsive_enabled: layoutResponsiveEnabled,
        reason: 'Settings enterprise panel update',
      });
      setLayoutUpdatedAt(response.data?.config?.updated_at || response.data?.updated_at || null);
      setStatus({ type: 'success', message: tx('settingsV2.common.layoutSaved', 'Platform layout settings updated.') });
    } catch (error: any) {
      setStatus({
        type: 'error',
        message: normalizeError(error, tx('settingsV2.common.saveError', 'Unable to save changes.')),
      });
    } finally {
      setLayoutSaving(false);
    }
  }, [isAdmin, layoutMode, layoutResponsiveEnabled, tx]);

  const toggleNotification = useCallback((key: keyof NotificationPreferences, value: boolean | string) => {
    setNotificationPrefs((prev) => ({ ...prev, [key]: value }));
  }, []);

  const updateBriefing = useCallback((key: keyof BriefingPreferences, value: any) => {
    setBriefingPrefs((prev) => ({ ...prev, [key]: value }));
  }, []);

  const quickActions = useMemo(
    () => [
      {
        id: 'edit-profile',
        icon: 'person-circle-outline' as const,
        title: tx('settings.item.editProfile.title', 'Edit Profile'),
        subtitle: tx('settings.item.editProfile.subtitle', 'Update your personal information'),
        onPress: () => router.push('/edit-profile'),
      },
      {
        id: 'privacy-security',
        icon: 'shield-checkmark-outline' as const,
        title: tx('settings.item.privacySecurity.title', 'Privacy & Security'),
        subtitle: tx('settings.item.privacySecurity.subtitle', 'Password, 2FA, data'),
        onPress: () => router.push('/privacy-security'),
      },
      {
        id: 'language',
        icon: 'language-outline' as const,
        title: tx('settings.item.language', 'Language'),
        subtitle: theme.language,
        onPress: () => router.push('/language-selector'),
      },
      {
        id: 'currency',
        icon: 'cash-outline' as const,
        title: tx('settingsV2.workspace.currency', 'Currency'),
        subtitle: String((user as any)?.currency_preference || 'USD').toUpperCase(),
        onPress: () => router.push('/currency-selector'),
      },
      {
        id: 'subscription',
        icon: 'diamond-outline' as const,
        title: tx('settings.item.subscription.title', 'Subscription'),
        subtitle: tx('settings.item.subscription.subtitle', 'Manage your plan'),
        onPress: () => router.push('/subscription/plans'),
      },
      {
        id: 'nova-assistant',
        icon: 'chatbubble-ellipses-outline' as const,
        title: tx('settingsV2.workspace.novaAssistant.title', 'Nova Assistant'),
        subtitle: tx('settingsV2.workspace.novaAssistant.subtitle', 'Open voice, attachments, and live GPS-backed chat'),
        onPress: () => setActiveSection('novaAssistant'),
      },
      {
        id: 'support',
        icon: 'help-circle-outline' as const,
        title: tx('settings.item.contactSupport.title', 'Contact Support'),
        subtitle: tx('settings.item.contactSupport.subtitle', 'Get help from our team'),
        onPress: () => router.push('/help'),
      },
    ],
    [router, setActiveSection, theme.language, tx, user],
  );

  const settingsConnectedMap = useMemo(() => {
    const map: Record<string, any> = {};
    settingsConnectedIntegrations.forEach((item: any) => {
      const key = String(item?.integration_id || '');
      if (key) map[key] = item;
    });
    return map;
  }, [settingsConnectedIntegrations]);

  const settingsMergedIntegrations = useMemo(() => {
    return settingsAvailableIntegrations.map((integration: any) => {
      const id = String(integration?.id || '');
      const connected = settingsConnectedMap[id];
      return {
        id,
        name: integration?.name || id,
        icon: integration?.icon || 'link-outline',
        category: integration?.category || tx('settingsV2.workspace.integrations.category.general', 'General'),
        connected: Boolean(connected),
        mode: connected?.test_mode
          ? tx('settingsV2.workspace.integrations.mode.test', 'Test')
          : tx('settingsV2.workspace.integrations.mode.live', 'Live'),
      };
    });
  }, [settingsAvailableIntegrations, settingsConnectedMap, tx]);

  const settingsRecentSyncs = useMemo(() => {
    return Array.isArray(settingsIntegrationStats?.recent_syncs)
      ? settingsIntegrationStats.recent_syncs.slice(0, 3)
      : [];
  }, [settingsIntegrationStats?.recent_syncs]);

  const settingsCatalogPreview = useMemo(() => {
    const names = settingsAvailableIntegrations
      .map((item: any) => String(item?.name || '').trim())
      .filter(Boolean)
      .slice(0, 3);
    if (names.length === 0) return tx('settingsV2.workspace.integrations.catalog.empty', 'Open integrations command center');
    return names.join(', ');
  }, [settingsAvailableIntegrations, tx]);

  const renderSidebar = () => (
    <View
      style={{
        width: isMobile ? '100%' : isTablet ? 240 : 270,
        borderRadius: 20,
        borderWidth: 1,
        borderColor: C.border,
        backgroundColor: C.card,
        padding: 16,
        gap: 10,
      }}
      data-testid="settings-v2-sidebar"
      testID="settings-v2-sidebar"
    >
      <Text
        style={{ fontSize: 12, color: C.textMuted, letterSpacing: 1, textTransform: 'uppercase', fontWeight: '700' }}
        data-testid="settings-v2-sidebar-title"
        testID="settings-v2-sidebar-title"
      >
        {tx('settingsV2.sidebar.title', 'Settings Areas')}
      </Text>

      {visibleSectionItems.map((section) => {
        const active = activeSection === section.key;
        return (
          <TouchableOpacity accessibilityLabel="Set active section in settings enterprise button"
            key={section.key}
            onPress={() => setActiveSection(section.key)}
            style={{
              flexDirection: 'row',
              alignItems: 'center',
              gap: 10,
              borderRadius: 12,
              paddingHorizontal: 12,
              paddingVertical: 11,
              backgroundColor: active ? `${C.primary}14` : C.bgSoft,
              borderWidth: 1,
              borderColor: active ? `${C.primary}66` : C.border,
            }}
            data-testid={`settings-v2-sidebar-${section.key}-button`}
            testID={`settings-v2-sidebar-${section.key}-button`}
          >
            <Ionicons name={section.icon} size={16} color={active ? C.primary : C.textMuted} />
            <Text
              style={{
                flex: 1,
                fontSize: 13,
                color: active ? C.primary : C.text,
                fontWeight: active ? '700' : '600',
              }}
              data-testid={`settings-v2-sidebar-${section.key}-label`}
              testID={`settings-v2-sidebar-${section.key}-label`}
            >
              {section.title}
            </Text>
            {active ? <Ionicons name="chevron-forward" size={14} color={C.primary} /> : null}
          </TouchableOpacity>
        );
      })}

      <View
        style={{
          borderRadius: 12,
          borderWidth: 1,
          borderColor: `${C.info}44`,
          backgroundColor: `${C.info}12`,
          padding: 10,
          marginTop: 6,
        }}
        data-testid="settings-v2-sidebar-helper"
        testID="settings-v2-sidebar-helper"
      >
        <Text style={{ color: C.info, fontSize: 11, lineHeight: 16 }}>
          {tx('settingsV2.sidebar.helper', 'All controls are synced with your live platform profile.')}
        </Text>
      </View>
    </View>
  );

  const renderPanelHeader = (title: string, subtitle: string, testId: string) => (
    <View style={{ marginBottom: 18 }} data-testid={`${testId}-header`} testID={`${testId}-header`}>
      <Text style={{ color: C.text, fontSize: 22, fontWeight: '800' }} data-testid={`${testId}-title`} testID={`${testId}-title`}>
        {title}
      </Text>
      <Text
        style={{ color: C.textMuted, fontSize: 12, marginTop: 4, lineHeight: 18 }}
        data-testid={`${testId}-subtitle`}
        testID={`${testId}-subtitle`}
      >
        {subtitle}
      </Text>
    </View>
  );

  const renderActionButton = (
    id: string,
    icon: keyof typeof Ionicons.glyphMap,
    title: string,
    subtitle: string,
    onPress: () => void,
  ) => (
    <TouchableOpacity accessibilityLabel="On press in settings enterprise button"
      key={id}
      onPress={onPress}
      style={{
        width: isMobile ? '100%' : '48%',
        borderRadius: 14,
        borderWidth: 1,
        borderColor: C.border,
        backgroundColor: C.bgSoft,
        padding: 12,
        gap: 6,
      }}
      data-testid={`settings-v2-workspace-action-${id}-button`}
      testID={`settings-v2-workspace-action-${id}-button`}
    >
      <Ionicons name={icon} size={16} color={C.primary} />
      <Text style={{ fontSize: 13, color: C.text, fontWeight: '700' }}>{title}</Text>
      <Text style={{ fontSize: 11, color: C.textMuted, lineHeight: 16 }}>{subtitle}</Text>
    </TouchableOpacity>
  );

  const renderWorkspaceIntegrationsBlock = () => (
    <View style={{ marginTop: 16 }} data-testid="settings-v2-workspace-integrations-block" testID="settings-v2-workspace-integrations-block">
      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10, gap: 8, flexWrap: 'wrap' }}>
        <View>
          <Text style={{ color: C.text, fontSize: 14, fontWeight: '800' }} data-testid="settings-v2-workspace-integrations-title" testID="settings-v2-workspace-integrations-title">
            {tx('settingsV2.workspace.integrations.title', 'Integrations Health')}
          </Text>
          <Text style={{ color: C.textMuted, fontSize: 11, marginTop: 2 }} data-testid="settings-v2-workspace-integrations-subtitle" testID="settings-v2-workspace-integrations-subtitle">
            {tx('settingsV2.workspace.integrations.subtitle', 'Live connector status and sync readiness from platform telemetry.')}
          </Text>
        </View>

        <TouchableOpacity accessibilityLabel="Settings v2 workspace integrations refresh button"
          onPress={() => void refreshSettingsIntegrations()}
          style={{
            borderRadius: 999,
            borderWidth: 1,
            borderColor: `${C.primary}55`,
            backgroundColor: `${C.primary}12`,
            paddingHorizontal: 10,
            paddingVertical: 6,
            flexDirection: 'row',
            alignItems: 'center',
            gap: 5,
          }}
          data-testid="settings-v2-workspace-integrations-refresh-button"
          testID="settings-v2-workspace-integrations-refresh-button"
        >
          <Ionicons name="refresh-outline" size={12} color={C.primary} />
          <Text style={{ color: C.primary, fontSize: 10, fontWeight: '700' }}>
            {tx('settingsV2.workspace.integrations.refresh', 'Refresh')}
          </Text>
        </TouchableOpacity>
      </View>

      <View style={{ flexDirection: 'row', gap: 8, flexWrap: 'wrap' }}>
        {[
          {
            id: 'active',
            label: tx('settingsV2.workspace.integrations.kpi.active', 'Active'),
            value: settingsIntegrationStats?.active_integrations ?? settingsConnectedIntegrations.length,
            tone: C.primary,
          },
          {
            id: 'candidates',
            label: tx('settingsV2.workspace.integrations.kpi.candidates', 'Candidates'),
            value: settingsIntegrationStats?.total_candidates ?? 0,
            tone: C.info,
          },
          {
            id: 'jobs',
            label: tx('settingsV2.workspace.integrations.kpi.jobs', 'Jobs'),
            value: settingsIntegrationStats?.total_jobs ?? 0,
            tone: C.success,
          },
          {
            id: 'catalog',
            label: tx('settingsV2.workspace.integrations.kpi.catalog', 'Catalog'),
            value: settingsAvailableIntegrations.length,
            tone: C.warning,
          },
        ].map((kpi) => (
          <View
            key={kpi.id}
            style={{
              borderRadius: 10,
              borderWidth: 1,
              borderColor: `${kpi.tone}45`,
              backgroundColor: `${kpi.tone}15`,
              paddingHorizontal: 10,
              paddingVertical: 8,
              minWidth: isMobile ? '47%' as any : 120,
              flex: isMobile ? 0 : 1,
            }}
            data-testid={`settings-v2-workspace-integrations-kpi-${kpi.id}`}
            testID={`settings-v2-workspace-integrations-kpi-${kpi.id}`}
          >
            <Text style={{ color: kpi.tone, fontSize: 10, fontWeight: '800', textTransform: 'uppercase' }}>{kpi.label}</Text>
            <Text style={{ color: C.text, fontSize: 15, fontWeight: '900', marginTop: 2 }}>{String(kpi.value || 0)}</Text>
          </View>
        ))}
      </View>

      {settingsIntegrationsLoading ? (
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginTop: 10 }} data-testid="settings-v2-workspace-integrations-loading" testID="settings-v2-workspace-integrations-loading">
          <ActivityIndicator size="small" color={C.primary} />
          <Text style={{ color: C.textMuted, fontSize: 11 }}>{tx('settingsV2.workspace.integrations.loading', 'Loading integration telemetry...')}</Text>
        </View>
      ) : null}

      {settingsIntegrationsError ? (
        <Text style={{ color: C.error, fontSize: 11, marginTop: 8 }} data-testid="settings-v2-workspace-integrations-error" testID="settings-v2-workspace-integrations-error">
          {settingsIntegrationsError}
        </Text>
      ) : null}

      <View style={{ gap: 8, marginTop: 10 }} data-testid="settings-v2-workspace-integrations-connectors" testID="settings-v2-workspace-integrations-connectors">
        {settingsMergedIntegrations.slice(0, 4).map((item, idx) => (
          <View
            key={item.id || idx}
            style={{
              borderRadius: 12,
              borderWidth: 1,
              borderColor: C.border,
              backgroundColor: C.bgSoft,
              paddingHorizontal: 10,
              paddingVertical: 9,
              flexDirection: 'row',
              alignItems: 'center',
              gap: 10,
            }}
            data-testid={`settings-v2-workspace-integrations-connector-${item.id || idx}`}
            testID={`settings-v2-workspace-integrations-connector-${item.id || idx}`}
          >
            <Ionicons name={(item.icon || 'link-outline') as any} size={14} color={item.connected ? C.success : C.textMuted} />
            <View style={{ flex: 1 }}>
              <Text style={{ color: C.text, fontSize: 12, fontWeight: '700' }}>{item.name}</Text>
              <Text style={{ color: C.textMuted, fontSize: 10 }}>{item.category}</Text>
            </View>
            <View
              style={{
                borderRadius: 999,
                borderWidth: 1,
                borderColor: item.connected ? `${C.success}45` : `${C.warning}45`,
                backgroundColor: item.connected ? `${C.success}12` : `${C.warning}12`,
                paddingHorizontal: 8,
                paddingVertical: 4,
              }}
            >
              <Text style={{ color: item.connected ? C.successText : C.warningText, fontSize: 10, fontWeight: '800' }}>
                {item.connected
                  ? tx('settingsV2.workspace.integrations.connected', 'CONNECTED')
                  : tx('settingsV2.workspace.integrations.notConnected', 'NOT CONNECTED')}
              </Text>
            </View>
          </View>
        ))}
      </View>

      {settingsRecentSyncs.length > 0 ? (
        <View style={{ marginTop: 10 }} data-testid="settings-v2-workspace-integrations-recent-sync" testID="settings-v2-workspace-integrations-recent-sync">
          <Text style={{ color: C.textSec, fontSize: 11, fontWeight: '700', marginBottom: 4 }}>
            {tx('settingsV2.workspace.integrations.recentSync', 'Recent Sync Activity')}
          </Text>
          {settingsRecentSyncs.map((sync: any, idx: number) => (
            <Text key={`${sync?.config_id || idx}`} style={{ color: C.textMuted, fontSize: 10 }} data-testid={`settings-v2-workspace-integrations-sync-item-${idx}`} testID={`settings-v2-workspace-integrations-sync-item-${idx}`}>
              • {sync?.integration_id || tx('settingsV2.workspace.integrations.connector', 'Connector')} · {sync?.status || tx('settingsV2.workspace.integrations.statusUnknown', 'status unknown')}
            </Text>
          ))}
        </View>
      ) : null}

      <View style={{ flexDirection: isMobile ? 'column' : 'row', gap: 8, marginTop: 10 }}>
        <TouchableOpacity accessibilityLabel="Settings v2 workspace integrations open command center button"
          onPress={() => router.push('/integrations')}
          style={{
            flex: 1,
            borderRadius: 10,
            borderWidth: 1,
            borderColor: `${C.primary}55`,
            backgroundColor: `${C.primary}12`,
            paddingVertical: 10,
            alignItems: 'center',
            flexDirection: 'row',
            justifyContent: 'center',
            gap: 6,
          }}
          data-testid="settings-v2-workspace-integrations-open-command-center"
          testID="settings-v2-workspace-integrations-open-command-center"
        >
          <Ionicons name="git-network-outline" size={13} color={C.primary} />
          <Text style={{ color: C.primary, fontSize: 11, fontWeight: '800' }}>
            {tx('settingsV2.workspace.integrations.openCommandCenter', 'Open Integrations Command Center')}
          </Text>
        </TouchableOpacity>
        <TouchableOpacity accessibilityLabel="Settings v2 workspace integrations calendar button"
          onPress={() => router.push('/calendar')}
          style={{
            flex: 1,
            borderRadius: 10,
            borderWidth: 1,
            borderColor: C.border,
            backgroundColor: C.card,
            paddingVertical: 10,
            alignItems: 'center',
            flexDirection: 'row',
            justifyContent: 'center',
            gap: 6,
          }}
          data-testid="settings-v2-workspace-integrations-calendar"
          testID="settings-v2-workspace-integrations-calendar"
        >
          <Ionicons name="calendar-outline" size={13} color={C.textMuted} />
          <Text style={{ color: C.text, fontSize: 11, fontWeight: '700' }}>
            {tx('settingsV2.workspace.integrations.calendar', 'Google Calendar')}: {settingsCatalogPreview}
          </Text>
        </TouchableOpacity>
      </View>
    </View>
  );

  const renderSwitchRow = (
    id: string,
    title: string,
    subtitle: string,
    value: boolean,
    onToggle: (next: boolean) => void,
  ) => (
    <View
      key={id}
      style={{
        borderRadius: 12,
        borderWidth: 1,
        borderColor: C.border,
        backgroundColor: C.bgSoft,
        paddingHorizontal: 12,
        paddingVertical: 10,
        flexDirection: 'row',
        alignItems: 'center',
        gap: 8,
      }}
      data-testid={`settings-v2-row-${id}`}
      testID={`settings-v2-row-${id}`}
    >
      <View style={{ flex: 1 }}>
        <Text style={{ color: C.text, fontSize: 13, fontWeight: '700' }} data-testid={`settings-v2-row-${id}-title`} testID={`settings-v2-row-${id}-title`}>
          {title}
        </Text>
        <Text
          style={{ color: C.textMuted, fontSize: 11, marginTop: 2, lineHeight: 16 }}
          data-testid={`settings-v2-row-${id}-subtitle`}
          testID={`settings-v2-row-${id}-subtitle`}
        >
          {subtitle}
        </Text>
      </View>
      <Switch
        value={value}
        onValueChange={onToggle}
        trackColor={{ false: C.border, true: `${C.primary}66` }}
        thumbColor={value ? C.primary : C.textMuted}
        data-testid={`settings-v2-row-${id}-switch`}
        testID={`settings-v2-row-${id}-switch`}
      />
    </View>
  );

  const renderWorkspacePanel = () => (
    <>
      {renderPanelHeader(
        tx('settingsV2.workspace.title', 'Workspace & Account'),
        tx('settingsV2.workspace.subtitle', 'Manage your profile identity, language, currency, and subscription paths.'),
        'settings-v2-workspace',
      )}

      {!isAuthenticated ? (
        <View
          style={{
            borderWidth: 1,
            borderColor: `${C.warning}55`,
            backgroundColor: `${C.warning}12`,
            borderRadius: 14,
            padding: 14,
            gap: 8,
          }}
          data-testid="settings-v2-workspace-auth-required"
          testID="settings-v2-workspace-auth-required"
        >
          <Text style={{ color: C.warningText, fontSize: 14, fontWeight: '700' }}>
            {tx('settingsV2.workspace.authRequired', 'Sign in required')}
          </Text>
          <Text style={{ color: C.textMuted, fontSize: 12, lineHeight: 17 }}>
            {tx('settingsV2.workspace.authHint', 'Log in to sync your workspace preferences across devices.')}
          </Text>
          <TouchableOpacity accessibilityLabel="Settings v2 workspace login button"
            onPress={() => router.push('/auth/login')}
            style={{
              alignSelf: 'flex-start',
              borderRadius: 999,
              backgroundColor: C.primary,
              paddingHorizontal: 14,
              paddingVertical: 9,
            }}
            data-testid="settings-v2-workspace-login-button"
            testID="settings-v2-workspace-login-button"
          >
            <Text style={{ color: C.primaryText, fontSize: 12, fontWeight: '700' }}>
              {tx('settingsV2.header.signInCta', 'Go to login')}
            </Text>
          </TouchableOpacity>
        </View>
      ) : (
        <>
          <View
            style={{
              borderWidth: 1,
              borderColor: C.border,
              backgroundColor: C.bgSoft,
              borderRadius: 14,
              padding: 14,
              marginBottom: 16,
              flexDirection: 'row',
              alignItems: 'center',
              gap: 12,
            }}
            data-testid="settings-v2-workspace-profile-card"
            testID="settings-v2-workspace-profile-card"
          >
            <View
              style={{
                width: 44,
                height: 44,
                borderRadius: 12,
                backgroundColor: `${C.primary}1A`,
                alignItems: 'center',
                justifyContent: 'center',
              }}
              data-testid="settings-v2-workspace-avatar"
              testID="settings-v2-workspace-avatar"
            >
              <Text style={{ color: C.primary, fontSize: 17, fontWeight: '800' }}>{String(user?.name || 'U').charAt(0).toUpperCase()}</Text>
            </View>

            <View style={{ flex: 1 }}>
              <Text style={{ color: C.text, fontSize: 14, fontWeight: '700' }} data-testid="settings-v2-workspace-user-name" testID="settings-v2-workspace-user-name">
                {user?.name || 'User'}
              </Text>
              <Text style={{ color: C.textMuted, fontSize: 11, marginTop: 2 }} data-testid="settings-v2-workspace-user-email" testID="settings-v2-workspace-user-email">
                {user?.email || '—'}
              </Text>
            </View>

            <View
              style={{
                borderRadius: 999,
                borderWidth: 1,
                borderColor: `${C.primary}55`,
                backgroundColor: `${C.primary}18`,
                paddingHorizontal: 10,
                paddingVertical: 4,
              }}
              data-testid="settings-v2-workspace-plan-badge"
              testID="settings-v2-workspace-plan-badge"
            >
              <Text style={{ color: C.primary, fontSize: 11, fontWeight: '700', textTransform: 'capitalize' }}>{displayPlan || 'free'}</Text>
            </View>
          </View>

          <View
            style={{ flexDirection: 'row', flexWrap: 'wrap', justifyContent: 'space-between', gap: 10 }}
            data-testid="settings-v2-workspace-actions"
            testID="settings-v2-workspace-actions"
          >
            {quickActions.map((action) => renderActionButton(action.id, action.icon, action.title, action.subtitle, action.onPress))}
          </View>

          {renderWorkspaceIntegrationsBlock()}

          <View
            style={{ marginTop: 14 }}
            data-testid="settings-v2-workspace-tenant-disclaimer-slot"
            testID="settings-v2-workspace-tenant-disclaimer-slot"
          >
            <EnterpriseDisclaimerToken
              context="banner"
              testIdPrefix="settings-workspace-ai-disclaimer"
              maxWidth={1040}
            />
          </View>
        </>
      )}
    </>
  );

  const renderNotificationsPanel = () => (
    <>
      {renderPanelHeader(
        tx('settingsV2.notifications.title', 'Notifications'),
        tx('settingsV2.notifications.subtitle', 'Tune channels, smart reminders, and quiet-hour windows.'),
        'settings-v2-notifications',
      )}

      <View style={{ gap: 10 }} data-testid="settings-v2-notifications-rows" testID="settings-v2-notifications-rows">
        {renderSwitchRow(
          'push-enabled',
          tx('settingsV2.notifications.push.title', 'Push notifications'),
          tx('settingsV2.notifications.push.subtitle', 'Instant device alerts for time-sensitive activity.'),
          Boolean(notificationPrefs.push_enabled),
          (value) => toggleNotification('push_enabled', value),
        )}
        {renderSwitchRow(
          'email-enabled',
          tx('settingsV2.notifications.email.title', 'Email notifications'),
          tx('settingsV2.notifications.email.subtitle', 'Deliver updates and summaries to your inbox.'),
          Boolean(notificationPrefs.email_enabled),
          (value) => toggleNotification('email_enabled', value),
        )}
        {renderSwitchRow(
          'daily-briefing',
          tx('settingsV2.notifications.dailyBriefing.title', 'Daily briefing'),
          tx('settingsV2.notifications.dailyBriefing.subtitle', 'Get a personalized kickoff summary every day.'),
          Boolean(notificationPrefs.daily_briefing),
          (value) => toggleNotification('daily_briefing', value),
        )}
        {renderSwitchRow(
          'practice-reminders',
          tx('settingsV2.notifications.practiceReminders.title', 'Practice reminders'),
          tx('settingsV2.notifications.practiceReminders.subtitle', 'Stay consistent with your coaching cadence.'),
          Boolean(notificationPrefs.practice_reminders),
          (value) => toggleNotification('practice_reminders', value),
        )}
        {renderSwitchRow(
          'achievement-alerts',
          tx('settingsV2.notifications.achievements.title', 'Achievement alerts'),
          tx('settingsV2.notifications.achievements.subtitle', 'Celebrate streaks, badges, and milestones.'),
          Boolean(notificationPrefs.achievement_alerts),
          (value) => toggleNotification('achievement_alerts', value),
        )}
        {renderSwitchRow(
          'weekly-digest',
          tx('settingsV2.notifications.weeklyDigest.title', 'Weekly digest'),
          tx('settingsV2.notifications.weeklyDigest.subtitle', 'Track weekly movement in one concise report.'),
          Boolean(notificationPrefs.weekly_digest),
          (value) => toggleNotification('weekly_digest', value),
        )}
        {renderSwitchRow(
          'team-updates',
          tx('settingsV2.notifications.teamUpdates.title', 'Team updates'),
          tx('settingsV2.notifications.teamUpdates.subtitle', 'Receive collaboration and access notifications.'),
          Boolean(notificationPrefs.team_updates),
          (value) => toggleNotification('team_updates', value),
        )}
        {renderSwitchRow(
          'goal-reminders',
          tx('settingsV2.notifications.goalReminders.title', 'Goal reminders'),
          tx('settingsV2.notifications.goalReminders.subtitle', 'Stay on track with milestone reminders.'),
          Boolean(notificationPrefs.goal_reminders),
          (value) => toggleNotification('goal_reminders', value),
        )}
        {renderSwitchRow(
          'coaching-nudges',
          tx('settingsV2.notifications.coachingNudges.title', 'Coaching nudges'),
          tx('settingsV2.notifications.coachingNudges.subtitle', 'Receive AI nudges based on your recent activity.'),
          Boolean(notificationPrefs.coaching_nudges),
          (value) => toggleNotification('coaching_nudges', value),
        )}
      </View>

      <View
        style={{
          marginTop: 14,
          borderWidth: 1,
          borderColor: C.border,
          backgroundColor: C.bgSoft,
          borderRadius: 14,
          padding: 12,
          gap: 10,
        }}
        data-testid="settings-v2-notifications-quiet-hours-card"
        testID="settings-v2-notifications-quiet-hours-card"
      >
        {renderSwitchRow(
          'quiet-hours-enabled',
          tx('settingsV2.notifications.quietHours.title', 'Quiet hours'),
          tx('settingsV2.notifications.quietHours.subtitle', 'Pause push alerts during your focus or sleep window.'),
          Boolean(notificationPrefs.quiet_hours_enabled),
          (value) => toggleNotification('quiet_hours_enabled', value),
        )}

        {notificationPrefs.quiet_hours_enabled ? (
          <View style={{ gap: 10 }} data-testid="settings-v2-notifications-quiet-hours-window" testID="settings-v2-notifications-quiet-hours-window">
            <Text style={{ color: C.textSec, fontSize: 12, fontWeight: '700' }}>
              {tx('settingsV2.notifications.quietHours.start', 'Start')} / {tx('settingsV2.notifications.quietHours.end', 'End')}
            </Text>

            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
              {['21:00', '22:00', '23:00'].map((value) => {
                const active = notificationPrefs.quiet_hours_start === value;
                return (
                  <TouchableOpacity accessibilityLabel="Toggle notification in settings enterprise button"
                    key={`start-${value}`}
                    onPress={() => toggleNotification('quiet_hours_start', value)}
                    style={{
                      borderRadius: 10,
                      borderWidth: 1,
                      borderColor: active ? C.primary : C.border,
                      backgroundColor: active ? `${C.primary}1A` : C.card,
                      paddingHorizontal: 10,
                      paddingVertical: 8,
                    }}
                    data-testid={`settings-v2-notifications-quiet-start-${value}`}
                    testID={`settings-v2-notifications-quiet-start-${value}`}
                  >
                    <Text style={{ color: active ? C.primary : C.textMuted, fontSize: 11, fontWeight: active ? '700' : '600' }}>{value}</Text>
                  </TouchableOpacity>
                );
              })}
            </View>

            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
              {['06:00', '07:00', '08:00'].map((value) => {
                const active = notificationPrefs.quiet_hours_end === value;
                return (
                  <TouchableOpacity accessibilityLabel="Toggle notification in settings enterprise button"
                    key={`end-${value}`}
                    onPress={() => toggleNotification('quiet_hours_end', value)}
                    style={{
                      borderRadius: 10,
                      borderWidth: 1,
                      borderColor: active ? C.primary : C.border,
                      backgroundColor: active ? `${C.primary}1A` : C.card,
                      paddingHorizontal: 10,
                      paddingVertical: 8,
                    }}
                    data-testid={`settings-v2-notifications-quiet-end-${value}`}
                    testID={`settings-v2-notifications-quiet-end-${value}`}
                  >
                    <Text style={{ color: active ? C.primary : C.textMuted, fontSize: 11, fontWeight: active ? '700' : '600' }}>{value}</Text>
                  </TouchableOpacity>
                );
              })}
            </View>
          </View>
        ) : null}
      </View>

      <TouchableOpacity accessibilityLabel="Settings v2 notifications save button"
        onPress={saveNotifications}
        disabled={notifSaving}
        style={{
          marginTop: 16,
          alignSelf: 'flex-start',
          borderRadius: 999,
          backgroundColor: C.primary,
          opacity: notifSaving ? 0.7 : 1,
          paddingHorizontal: 16,
          paddingVertical: 10,
        }}
        data-testid="settings-v2-notifications-save-button"
        testID="settings-v2-notifications-save-button"
      >
        <Text style={{ color: C.primaryText, fontWeight: '700', fontSize: 12 }}>
          {notifSaving
            ? tx('settingsV2.notifications.saving', 'Saving notification settings...')
            : tx('settingsV2.notifications.save', 'Save notification settings')}
        </Text>
      </TouchableOpacity>
    </>
  );

  const renderAIBriefingPanel = () => (
    <>
      {renderPanelHeader(
        tx('settingsV2.aiBriefing.title', 'AI Daily Briefing'),
        tx('settingsV2.aiBriefing.subtitle', 'Control what your morning AI briefing includes.'),
        'settings-v2-ai-briefing',
      )}

      <View style={{ gap: 12 }} data-testid="settings-v2-ai-briefing-form" testID="settings-v2-ai-briefing-form">
        <View style={{ gap: 6 }}>
          <Text style={{ color: C.textSec, fontSize: 11, fontWeight: '700', textTransform: 'uppercase' }}>
            {tx('settingsV2.aiBriefing.interests', 'Interests')}
          </Text>
          <TextInput
            value={interestsInput}
            onChangeText={setInterestsInput}
            placeholder={tx('settingsV2.aiBriefing.interestsPlaceholder', 'career growth, productivity, leadership')}
            placeholderTextColor={C.textMuted}
            style={{
              borderRadius: 12,
              borderWidth: 1,
              borderColor: C.border,
              backgroundColor: C.bgSoft,
              color: C.text,
              paddingHorizontal: 12,
              paddingVertical: 10,
              fontSize: 13,
            }}
            data-testid="settings-v2-ai-briefing-interests-input"
            testID="settings-v2-ai-briefing-interests-input"
          />
        </View>

        <View style={{ gap: 6 }}>
          <Text style={{ color: C.textSec, fontSize: 11, fontWeight: '700', textTransform: 'uppercase' }}>
            {tx('settingsV2.aiBriefing.industry', 'Industry')}
          </Text>
          <TextInput
            value={briefingPrefs.industry}
            onChangeText={(value) => updateBriefing('industry', value)}
            placeholder={tx('settingsV2.aiBriefing.industryPlaceholder', 'Technology')}
            placeholderTextColor={C.textMuted}
            style={{
              borderRadius: 12,
              borderWidth: 1,
              borderColor: C.border,
              backgroundColor: C.bgSoft,
              color: C.text,
              paddingHorizontal: 12,
              paddingVertical: 10,
              fontSize: 13,
            }}
            data-testid="settings-v2-ai-briefing-industry-input"
            testID="settings-v2-ai-briefing-industry-input"
          />
        </View>

        <View style={{ gap: 8 }}>
          <Text style={{ color: C.textSec, fontSize: 11, fontWeight: '700', textTransform: 'uppercase' }}>
            {tx('settingsV2.aiBriefing.time', 'Briefing time')}
          </Text>
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
            {['06:00', '07:00', '08:00', '09:00'].map((value) => {
              const active = briefingPrefs.briefing_time === value;
              return (
                <TouchableOpacity accessibilityLabel="Update briefing in settings enterprise button"
                  key={value}
                  onPress={() => updateBriefing('briefing_time', value)}
                  style={{
                    borderRadius: 10,
                    borderWidth: 1,
                    borderColor: active ? C.primary : C.border,
                    backgroundColor: active ? `${C.primary}1A` : C.bgSoft,
                    paddingHorizontal: 10,
                    paddingVertical: 8,
                  }}
                  data-testid={`settings-v2-ai-briefing-time-${value}`}
                  testID={`settings-v2-ai-briefing-time-${value}`}
                >
                  <Text style={{ color: active ? C.primary : C.textMuted, fontSize: 11, fontWeight: active ? '700' : '600' }}>{value}</Text>
                </TouchableOpacity>
              );
            })}
          </View>
        </View>

        {renderSwitchRow(
          'ai-briefing-news',
          tx('settingsV2.aiBriefing.includeNews', 'Include industry news'),
          tx('settingsV2.aiBriefing.includeNewsSubtitle', 'Curated headlines relevant to your selected interests.'),
          Boolean(briefingPrefs.include_news),
          (value) => updateBriefing('include_news', value),
        )}
        {renderSwitchRow(
          'ai-briefing-tips',
          tx('settingsV2.aiBriefing.includeTips', 'Include coaching tips'),
          tx('settingsV2.aiBriefing.includeTipsSubtitle', 'Actionable recommendations for daily execution.'),
          Boolean(briefingPrefs.include_tips),
          (value) => updateBriefing('include_tips', value),
        )}
        {renderSwitchRow(
          'ai-briefing-motivation',
          tx('settingsV2.aiBriefing.includeMotivation', 'Include motivation'),
          tx('settingsV2.aiBriefing.includeMotivationSubtitle', 'Add a personalized motivational segment to each briefing.'),
          Boolean(briefingPrefs.include_motivation),
          (value) => updateBriefing('include_motivation', value),
        )}

        <TouchableOpacity accessibilityLabel="Settings v2 ai briefing save button"
          onPress={saveBriefing}
          disabled={briefingSaving}
          style={{
            marginTop: 2,
            alignSelf: 'flex-start',
            borderRadius: 999,
            backgroundColor: C.primary,
            opacity: briefingSaving ? 0.7 : 1,
            paddingHorizontal: 16,
            paddingVertical: 10,
          }}
          data-testid="settings-v2-ai-briefing-save-button"
          testID="settings-v2-ai-briefing-save-button"
        >
          <Text style={{ color: C.primaryText, fontWeight: '700', fontSize: 12 }}>
            {briefingSaving
              ? tx('settingsV2.aiBriefing.saving', 'Saving briefing preferences...')
              : tx('settingsV2.aiBriefing.save', 'Save briefing preferences')}
          </Text>
        </TouchableOpacity>
      </View>
    </>
  );

  const renderSecurityPanel = () => (
    <>
      {renderPanelHeader(
        tx('settingsV2.security.title', 'Security Posture'),
        tx('settingsV2.security.subtitle', 'Review authentication and privacy controls in one place.'),
        'settings-v2-security',
      )}

      <View
        style={{
          borderWidth: 1,
          borderColor: C.border,
          backgroundColor: C.bgSoft,
          borderRadius: 14,
          padding: 12,
          gap: 10,
        }}
        data-testid="settings-v2-security-mfa-card"
        testID="settings-v2-security-mfa-card"
      >
        <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
          <Text style={{ color: C.text, fontSize: 14, fontWeight: '700' }} data-testid="settings-v2-security-mfa-title" testID="settings-v2-security-mfa-title">
            {tx('settingsV2.security.mfa', 'Multi-factor authentication')}
          </Text>
          <View
            style={{
              borderRadius: 999,
              borderWidth: 1,
              borderColor: mfaEnabled ? `${C.success}66` : `${C.warning}66`,
              backgroundColor: mfaEnabled ? `${C.success}14` : `${C.warning}14`,
              paddingHorizontal: 10,
              paddingVertical: 4,
            }}
            data-testid="settings-v2-security-mfa-status"
            testID="settings-v2-security-mfa-status"
          >
            <Text style={{ color: mfaEnabled ? C.successText : C.warningText, fontSize: 11, fontWeight: '700' }}>
              {mfaEnabled
                ? tx('settingsV2.security.mfaEnabled', 'Enabled')
                : tx('settingsV2.security.mfaDisabled', 'Not enabled')}
            </Text>
          </View>
        </View>

        <Text style={{ color: C.textMuted, fontSize: 12, lineHeight: 18 }} data-testid="settings-v2-security-mfa-subtitle" testID="settings-v2-security-mfa-subtitle">
          {tx('settingsV2.security.mfaSubtitle', 'Enable MFA to reduce account takeover risk and protect privileged access.')}
        </Text>

        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
          <TouchableOpacity accessibilityLabel="Settings v2 security open security center button"
            onPress={() => router.push('/security')}
            style={{
              borderRadius: 999,
              backgroundColor: C.primary,
              paddingHorizontal: 14,
              paddingVertical: 9,
            }}
            data-testid="settings-v2-security-open-security-center-button"
            testID="settings-v2-security-open-security-center-button"
          >
            <Text style={{ color: C.primaryText, fontSize: 12, fontWeight: '700' }}>
              {tx('settingsV2.security.openSecurityCenter', 'Open security center')}
            </Text>
          </TouchableOpacity>

          <TouchableOpacity accessibilityLabel="Settings v2 security open privacy center button"
            onPress={() => router.push('/privacy-security')}
            style={{
              borderRadius: 999,
              borderWidth: 1,
              borderColor: C.border,
              backgroundColor: C.card,
              paddingHorizontal: 14,
              paddingVertical: 9,
            }}
            data-testid="settings-v2-security-open-privacy-center-button"
            testID="settings-v2-security-open-privacy-center-button"
          >
            <Text style={{ color: C.text, fontSize: 12, fontWeight: '700' }}>
              {tx('settingsV2.security.openPrivacyCenter', 'Open privacy center')}
            </Text>
          </TouchableOpacity>
        </View>
      </View>
    </>
  );

  const renderAccessibilityPanel = () => (
    <>
      {renderPanelHeader(
        tx('settingsV2.accessibility.title', 'Accessibility'),
        tx('settingsV2.accessibility.subtitle', 'Adapt typography, contrast, and navigation aids to your needs.'),
        'settings-v2-accessibility',
      )}

      <View style={{ gap: 10 }}>
        <View
          style={{
            borderRadius: 12,
            borderWidth: 1,
            borderColor: `${C.primary}44`,
            backgroundColor: `${C.primary}12`,
            padding: 10,
          }}
          data-testid="settings-v2-accessibility-active-count"
          testID="settings-v2-accessibility-active-count"
        >
          <Text style={{ color: C.primary, fontSize: 12, fontWeight: '700' }}>
            {tx('settingsV2.accessibility.activeRules', 'Active accessibility rules')}: {activeCount}
          </Text>
        </View>

        <View style={{ gap: 7 }}>
          <Text style={{ color: C.textSec, fontSize: 11, fontWeight: '700', textTransform: 'uppercase' }}>
            {tx('settingsV2.accessibility.textSize', 'Text size')}
          </Text>
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
            {[
              { id: 'small', label: 'S' },
              { id: 'medium', label: 'M' },
              { id: 'large', label: 'L' },
              { id: 'extra-large', label: 'XL' },
            ].map((item) => {
              const active = prefs.textSize === item.id;
              return (
                <TouchableOpacity accessibilityLabel="Update pref in settings enterprise button"
                  key={item.id}
                  onPress={() => updatePref('textSize', item.id as any)}
                  style={{
                    borderRadius: 10,
                    borderWidth: 1,
                    borderColor: active ? C.primary : C.border,
                    backgroundColor: active ? `${C.primary}1A` : C.bgSoft,
                    paddingHorizontal: 12,
                    paddingVertical: 8,
                  }}
                  data-testid={`settings-v2-accessibility-text-size-${item.id}`}
                  testID={`settings-v2-accessibility-text-size-${item.id}`}
                >
                  <Text style={{ color: active ? C.primary : C.textMuted, fontSize: 12, fontWeight: '700' }}>{item.label}</Text>
                </TouchableOpacity>
              );
            })}
          </View>
        </View>

        {renderSwitchRow(
          'a11y-dyslexia-font',
          tx('settingsV2.accessibility.dyslexiaFont', 'Dyslexia-friendly font'),
          tx('settingsV2.accessibility.dyslexiaFontSubtitle', 'Enable OpenDyslexic typography for improved readability.'),
          Boolean(prefs.dyslexiaFont),
          (value) => updatePref('dyslexiaFont', value),
        )}
        {renderSwitchRow(
          'a11y-high-contrast',
          tx('settingsV2.accessibility.highContrast', 'High contrast mode'),
          tx('settingsV2.accessibility.highContrastSubtitle', 'Increase contrast to improve visual distinction.'),
          Boolean(prefs.highContrast),
          (value) => updatePref('highContrast', value),
        )}
        {renderSwitchRow(
          'a11y-focus-indicators',
          tx('settingsV2.accessibility.focusIndicators', 'Focus indicators'),
          tx('settingsV2.accessibility.focusIndicatorsSubtitle', 'Show stronger keyboard focus outlines.'),
          Boolean(prefs.focusIndicators),
          (value) => updatePref('focusIndicators', value),
        )}
        {renderSwitchRow(
          'a11y-motion-reduction',
          tx('settingsV2.accessibility.reduceMotion', 'Reduce motion'),
          tx('settingsV2.accessibility.reduceMotionSubtitle', 'Limit animations and transitions across the app.'),
          Boolean(prefs.motionReduction),
          (value) => updatePref('motionReduction', value),
        )}
        {renderSwitchRow(
          'a11y-keyboard-navigation',
          tx('settingsV2.accessibility.keyboardNavigation', 'Keyboard navigation'),
          tx('settingsV2.accessibility.keyboardNavigationSubtitle', 'Optimize tab order for keyboard-driven navigation.'),
          Boolean(prefs.keyboardNavigation),
          (value) => updatePref('keyboardNavigation', value),
        )}
        {renderSwitchRow(
          'a11y-text-to-speech',
          tx('settingsV2.accessibility.textToSpeech', 'Text to speech'),
          tx('settingsV2.accessibility.textToSpeechSubtitle', 'Allow supported sections to read content aloud.'),
          Boolean(prefs.textToSpeech),
          (value) => updatePref('textToSpeech', value),
        )}

        <TouchableOpacity accessibilityLabel="Settings v2 accessibility reset button"
          onPress={() => {
            resetAll();
            setStatus({ type: 'success', message: tx('settingsV2.common.accessibilityReset', 'Accessibility settings reset.') });
          }}
          style={{
            marginTop: 2,
            alignSelf: 'flex-start',
            borderRadius: 999,
            borderWidth: 1,
            borderColor: C.border,
            backgroundColor: C.card,
            paddingHorizontal: 14,
            paddingVertical: 9,
          }}
          data-testid="settings-v2-accessibility-reset-button"
          testID="settings-v2-accessibility-reset-button"
        >
          <Text style={{ color: C.text, fontSize: 12, fontWeight: '700' }}>{tx('settingsV2.accessibility.reset', 'Reset accessibility preferences')}</Text>
        </TouchableOpacity>
      </View>
    </>
  );

  const renderAppearancePanel = () => (
    <>
      {renderPanelHeader(
        tx('settingsV2.appearance.title', 'Appearance'),
        tx('settingsV2.appearance.subtitle', 'Apply your preferred theme mode and visual intensity globally.'),
        'settings-v2-appearance',
      )}

      <View style={{ gap: 12 }}>
        <View style={{ gap: 8 }}>
          <Text style={{ color: C.textSec, fontSize: 11, fontWeight: '700', textTransform: 'uppercase' }}>
            {tx('settingsV2.appearance.themeMode', 'Theme mode')}
          </Text>
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
            {[
              { id: 'system', title: tx('settings.theme.system', 'System') },
              { id: 'light', title: tx('settings.theme.light', 'Light') },
              { id: 'dark', title: tx('settings.theme.dark', 'Dark') },
            ].map((option) => {
              const active = theme.themeMode === option.id;
              return (
                <TouchableOpacity accessibilityLabel="Theme in settings enterprise button"
                  key={option.id}
                  onPress={() => theme.setThemeMode(option.id as any)}
                  style={{
                    borderRadius: 10,
                    borderWidth: 1,
                    borderColor: active ? C.primary : C.border,
                    backgroundColor: active ? `${C.primary}1A` : C.bgSoft,
                    paddingHorizontal: 12,
                    paddingVertical: 8,
                  }}
                  data-testid={`settings-v2-appearance-theme-${option.id}`}
                  testID={`settings-v2-appearance-theme-${option.id}`}
                >
                  <Text style={{ color: active ? C.primary : C.textMuted, fontSize: 12, fontWeight: active ? '700' : '600' }}>{option.title}</Text>
                </TouchableOpacity>
              );
            })}
          </View>
        </View>

        <View style={{ gap: 8 }}>
          <Text style={{ color: C.textSec, fontSize: 11, fontWeight: '700', textTransform: 'uppercase' }}>
            {tx('settingsV2.appearance.backgroundIntensity', 'Background intensity')}
          </Text>
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
            {[0, 15, 30, 50, 75, 100].map((value) => {
              const active = brightness === value;
              return (
                <TouchableOpacity accessibilityLabel="Set brightness in settings enterprise button"
                  key={value}
                  onPress={() => setBrightness(value)}
                  style={{
                    borderRadius: 10,
                    borderWidth: 1,
                    borderColor: active ? C.primary : C.border,
                    backgroundColor: active ? `${C.primary}1A` : C.bgSoft,
                    paddingHorizontal: 10,
                    paddingVertical: 8,
                  }}
                  data-testid={`settings-v2-appearance-brightness-${value}`}
                  testID={`settings-v2-appearance-brightness-${value}`}
                >
                  <Text style={{ color: active ? C.primary : C.textMuted, fontSize: 11, fontWeight: active ? '700' : '600' }}>{value}%</Text>
                </TouchableOpacity>
              );
            })}
          </View>
        </View>

        <View style={{ gap: 8 }}>
          <Text style={{ color: C.textSec, fontSize: 11, fontWeight: '700', textTransform: 'uppercase' }}>
            {tx('settingsV2.appearance.backgroundPreset', 'Background preset')}
          </Text>
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
            {PRESET_OPTIONS.map((option) => {
              const active = preset === option.id;
              return (
                <TouchableOpacity accessibilityLabel="Set preset in settings enterprise button"
                  key={option.id}
                  onPress={() => setPreset(option.id)}
                  style={{
                    borderRadius: 10,
                    borderWidth: 1,
                    borderColor: active ? C.primary : C.border,
                    backgroundColor: active ? `${C.primary}1A` : C.bgSoft,
                    paddingHorizontal: 10,
                    paddingVertical: 8,
                  }}
                  data-testid={`settings-v2-appearance-preset-${option.id}`}
                  testID={`settings-v2-appearance-preset-${option.id}`}
                >
                  <Text style={{ color: active ? C.primary : C.textMuted, fontSize: 11, fontWeight: active ? '700' : '600' }}>{option.label}</Text>
                </TouchableOpacity>
              );
            })}
          </View>
        </View>

        <View style={{ gap: 8 }}>
          <Text style={{ color: C.textSec, fontSize: 11, fontWeight: '700', textTransform: 'uppercase' }}>{tx('settings.item.fontSize', 'Font Size')}</Text>
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
            {['Small', 'Medium', 'Large'].map((size) => {
              const active = theme.fontSize === size;
              return (
                <TouchableOpacity accessibilityLabel="Theme in settings enterprise button"
                  key={size}
                  onPress={() => theme.setFontSize(size)}
                  style={{
                    borderRadius: 10,
                    borderWidth: 1,
                    borderColor: active ? C.primary : C.border,
                    backgroundColor: active ? `${C.primary}1A` : C.bgSoft,
                    paddingHorizontal: 10,
                    paddingVertical: 8,
                  }}
                  data-testid={`settings-v2-appearance-font-size-${size.toLowerCase()}`}
                  testID={`settings-v2-appearance-font-size-${size.toLowerCase()}`}
                >
                  <Text style={{ color: active ? C.primary : C.textMuted, fontSize: 11, fontWeight: active ? '700' : '600' }}>{size}</Text>
                </TouchableOpacity>
              );
            })}
          </View>
        </View>

        <View style={{ gap: 8 }}>
          {renderSwitchRow(
            'appearance-preview',
            tx('settings.item.preview.title', 'Theme Preview'),
            tx('settings.item.preview.subtitle', 'Preview accent & language before saving'),
            theme.previewEnabled,
            (value) => {
              theme.setPreviewEnabled(value);
              if (!value) {
                theme.cancelPreviewChanges();
              }
            },
          )}

          {theme.previewEnabled ? (
            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
              <TouchableOpacity accessibilityLabel="Settings v2 appearance preview cancel button"
                onPress={theme.cancelPreviewChanges}
                style={{
                  borderRadius: 999,
                  borderWidth: 1,
                  borderColor: C.border,
                  backgroundColor: C.card,
                  paddingHorizontal: 12,
                  paddingVertical: 8,
                }}
                data-testid="settings-v2-appearance-preview-cancel-button"
                testID="settings-v2-appearance-preview-cancel-button"
              >
                <Text style={{ color: C.text, fontSize: 12, fontWeight: '700' }}>{tx('settings.preview.cancel', 'Discard')}</Text>
              </TouchableOpacity>
              <TouchableOpacity accessibilityLabel="Settings v2 appearance preview save button"
                onPress={theme.savePreviewChanges}
                style={{
                  borderRadius: 999,
                  backgroundColor: C.primary,
                  paddingHorizontal: 12,
                  paddingVertical: 8,
                }}
                data-testid="settings-v2-appearance-preview-save-button"
                testID="settings-v2-appearance-preview-save-button"
              >
                <Text style={{ color: C.primaryText, fontSize: 12, fontWeight: '700' }}>{tx('settings.preview.save', 'Save Changes')}</Text>
              </TouchableOpacity>
            </View>
          ) : null}
        </View>
      </View>
    </>
  );

  const renderPlatformPanel = () => {
    if (!isAdmin) {
      return (
        <>
          {renderPanelHeader(
            tx('settingsV2.platform.title', 'Platform controls'),
            tx('settingsV2.platform.subtitle', 'Admin-only runtime controls for layout and governance.'),
            'settings-v2-platform',
          )}
          <View
            style={{
              borderWidth: 1,
              borderColor: `${C.warning}55`,
              backgroundColor: `${C.warning}12`,
              borderRadius: 14,
              padding: 14,
            }}
            data-testid="settings-v2-platform-admin-only"
            testID="settings-v2-platform-admin-only"
          >
            <Text style={{ color: C.warningText, fontSize: 12, lineHeight: 18 }}>
              {tx('settingsV2.platform.adminOnly', 'Only admins can access platform layout controls.')}
            </Text>
          </View>
        </>
      );
    }

    return (
      <>
        {renderPanelHeader(
          tx('settingsV2.platform.title', 'Platform controls'),
          tx('settingsV2.platform.subtitle', 'Control runtime layout mode and monitor global platform counts.'),
          'settings-v2-platform',
        )}

        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
          {[
            { id: 'version', label: tx('settingsV2.platform.gpsVersion', 'GPS Version'), value: String(gpsState.version || 1) },
            { id: 'features', label: tx('settingsV2.platform.featureCount', 'Features'), value: String(gpsCounts.features || 0) },
            { id: 'plans', label: tx('settingsV2.platform.planCount', 'Plans'), value: String(gpsCounts.plans || 0) },
          ].map((metric) => (
            <View
              key={metric.id}
              style={{
                minWidth: isMobile ? '100%' : 140,
                borderRadius: 12,
                borderWidth: 1,
                borderColor: C.border,
                backgroundColor: C.bgSoft,
                padding: 10,
              }}
              data-testid={`settings-v2-platform-metric-${metric.id}`}
              testID={`settings-v2-platform-metric-${metric.id}`}
            >
              <Text style={{ color: C.textMuted, fontSize: 11 }}>{metric.label}</Text>
              <Text style={{ color: C.text, fontSize: 17, fontWeight: '800', marginTop: 4 }}>{metric.value}</Text>
            </View>
          ))}
        </View>

        <View
          style={{
            marginTop: 12,
            borderRadius: 12,
            borderWidth: 1,
            borderColor: C.border,
            backgroundColor: C.bgSoft,
            padding: 12,
            gap: 10,
          }}
          data-testid="settings-v2-platform-layout-card"
          testID="settings-v2-platform-layout-card"
        >
          <Text style={{ color: C.text, fontSize: 13, fontWeight: '700' }}>
            {tx('settingsV2.platform.layoutMode', 'Layout mode')}
          </Text>

          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
            {[
              { id: 'centered' as const, label: tx('settingsV2.platform.layoutModeCentered', 'Centered') },
              { id: 'full-width' as const, label: tx('settingsV2.platform.layoutModeFullWidth', 'Full width') },
              { id: 'compact' as const, label: tx('settingsV2.platform.layoutModeCompact', 'Compact') },
            ].map((option) => {
              const active = layoutMode === option.id;
              return (
                <TouchableOpacity accessibilityLabel="Set layout mode in settings enterprise button"
                  key={option.id}
                  onPress={() => setLayoutMode(option.id)}
                  style={{
                    borderRadius: 10,
                    borderWidth: 1,
                    borderColor: active ? C.primary : C.border,
                    backgroundColor: active ? `${C.primary}1A` : C.card,
                    paddingHorizontal: 10,
                    paddingVertical: 8,
                  }}
                  data-testid={`settings-v2-platform-layout-mode-${option.id}`}
                  testID={`settings-v2-platform-layout-mode-${option.id}`}
                >
                  <Text style={{ color: active ? C.primary : C.textMuted, fontSize: 11, fontWeight: active ? '700' : '600' }}>{option.label}</Text>
                </TouchableOpacity>
              );
            })}
          </View>

          {renderSwitchRow(
            'platform-responsive-enabled',
            tx('settingsV2.platform.responsiveEnabled', 'Responsive layout contract'),
            tx('settingsV2.platform.responsiveEnabledSubtitle', 'Enable adaptive spacing and breakpoints from GLS runtime tokens.'),
            layoutResponsiveEnabled,
            (value) => setLayoutResponsiveEnabled(value),
          )}

          <TouchableOpacity accessibilityLabel="Settings v2 platform save button"
            onPress={saveLayoutConfig}
            disabled={layoutSaving}
            style={{
              alignSelf: 'flex-start',
              borderRadius: 999,
              backgroundColor: C.primary,
              opacity: layoutSaving ? 0.7 : 1,
              paddingHorizontal: 14,
              paddingVertical: 9,
            }}
            data-testid="settings-v2-platform-save-button"
            testID="settings-v2-platform-save-button"
          >
            <Text style={{ color: C.primaryText, fontSize: 12, fontWeight: '700' }}>
              {layoutSaving
                ? tx('settingsV2.platform.saving', 'Saving platform settings...')
                : tx('settingsV2.platform.save', 'Save platform settings')}
            </Text>
          </TouchableOpacity>

          <Text
            style={{ color: C.textMuted, fontSize: 11 }}
            data-testid="settings-v2-platform-updated-at"
            testID="settings-v2-platform-updated-at"
          >
            {tx('settingsV2.platform.updatedAt', 'Last platform update')}: {formatDateTime(layoutUpdatedAt)}
          </Text>
        </View>
      </>
    );
  };

  const renderNovaAssistantPanel = () => (
    <>
      {renderPanelHeader(
        tx('settingsV2.novaAssistant.title', 'Nova Assistant Workspace'),
        tx('settingsV2.novaAssistant.subtitle', 'Live GPS-aware Nova with voice, attachments, and per-response feedback.'),
        'settings-v2-nova-assistant',
      )}

      <View
        style={{
          borderRadius: 14,
          borderWidth: 1,
          borderColor: `${C.primary}33`,
          backgroundColor: C.bgSoft,
          padding: 10,
        }}
        data-testid="settings-v2-nova-assistant-wrapper"
        testID="settings-v2-nova-assistant-wrapper"
      >
        <SettingsNovaAssistantPanel />
      </View>
    </>
  );

  const renderActivePanel = () => {
    if (activeSection === 'workspace') return renderWorkspacePanel();
    if (activeSection === 'notifications') return renderNotificationsPanel();
    if (activeSection === 'aiBriefing') return renderAIBriefingPanel();
    if (activeSection === 'novaAssistant') return renderNovaAssistantPanel();
    if (activeSection === 'security') return renderSecurityPanel();
    if (activeSection === 'accessibility') return renderAccessibilityPanel();
    if (activeSection === 'appearance') return renderAppearancePanel();
    return renderPlatformPanel();
  };

  return (
    <AppShell>
      <View style={{ flex: 1, backgroundColor: 'transparent' }} data-testid="settings-screen" testID="settings-screen">
        <ScrollView
          showsVerticalScrollIndicator={false}
          contentContainerStyle={{ paddingBottom: 80 }}
          data-testid="settings-v2-scroll-root"
          testID="settings-v2-scroll-root"
        >
          <GLSSection noVerticalPadding style={{ paddingTop: isMobile ? 18 : 28, paddingBottom: 18 }} testID="settings-v2-header-section">
            <View
              style={{
                borderRadius: 22,
                borderWidth: 1,
                borderColor: C.border,
                backgroundColor: Platform.OS === 'web' ? (globalThis as any).__alphaColor(C.card, theme.darkMode ? 'A8' : 'DA') : C.card,
                padding: isMobile ? 14 : 18,
                gap: 12,
                ...(Platform.OS === 'web' ? { backdropFilter: 'blur(12px)', WebkitBackdropFilter: 'blur(12px)' } as any : {}),
              }}
              data-testid="settings-v2-header-card"
              testID="settings-v2-header-card"
            >
              <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 10 }}>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, flex: 1 }}>
                  <TouchableOpacity accessibilityLabel="Settings v2 back button"
                    onPress={() => router.back()}
                    style={{
                      width: 36,
                      height: 36,
                      borderRadius: 10,
                      borderWidth: 1,
                      borderColor: C.border,
                      backgroundColor: C.bgSoft,
                      alignItems: 'center',
                      justifyContent: 'center',
                    }}
                    data-testid="settings-v2-back-button"
                    testID="settings-v2-back-button"
                  >
                    <Ionicons name="arrow-back" size={16} color={C.text} />
                  </TouchableOpacity>

                  <View style={{ flex: 1 }}>
                    <Text style={{ fontSize: 11, color: C.textMuted, textTransform: 'uppercase', letterSpacing: 0.8 }} data-testid="settings-v2-header-badge" testID="settings-v2-header-badge">
                      {tx('settingsV2.header.badge', 'Enterprise settings')}
                    </Text>
                    <Text style={{ fontSize: 30, fontWeight: '800', color: C.text, marginTop: 2 }} data-testid="settings-header-title" testID="settings-header-title">
                      {tx('settings.title', 'Settings')}
                    </Text>
                    <Text style={{ fontSize: 12, color: C.textMuted, marginTop: 2 }} data-testid="settings-v2-header-subtitle" testID="settings-v2-header-subtitle">
                      {tx('settingsV2.header.subtitle', 'Dynamic controls powered by your live platform state.')}
                    </Text>
                  </View>
                </View>

                {isAuthenticated ? (
                  <TouchableOpacity accessibilityLabel="Settings v2 header logout button"
                    onPress={handleLogout}
                    style={{
                      borderRadius: 999,
                      borderWidth: 1,
                      borderColor: `${C.error}44`,
                      backgroundColor: `${C.error}12`,
                      paddingHorizontal: 12,
                      paddingVertical: 8,
                    }}
                    data-testid="settings-v2-header-logout-button"
                    testID="settings-v2-header-logout-button"
                  >
                    <Text style={{ color: C.error, fontSize: 12, fontWeight: '700' }}>{tx('settingsV2.header.logout', 'Sign out')}</Text>
                  </TouchableOpacity>
                ) : (
                  <TouchableOpacity accessibilityLabel="Settings v2 header login button"
                    onPress={() => router.push('/auth/login')}
                    style={{
                      borderRadius: 999,
                      borderWidth: 1,
                      borderColor: C.border,
                      backgroundColor: C.bgSoft,
                      paddingHorizontal: 12,
                      paddingVertical: 8,
                    }}
                    data-testid="settings-v2-header-login-button"
                    testID="settings-v2-header-login-button"
                  >
                    <Text style={{ color: C.text, fontSize: 12, fontWeight: '700' }}>{tx('settingsV2.header.signInCta', 'Go to login')}</Text>
                  </TouchableOpacity>
                )}
              </View>

              <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }} data-testid="settings-v2-header-metrics" testID="settings-v2-header-metrics">
                {[
                  {
                    id: 'plan',
                    label: tx('settingsV2.header.metricPlan', 'Current plan'),
                    value: String(displayPlan || 'free').toUpperCase(),
                  },
                  {
                    id: 'features',
                    label: tx('settingsV2.header.metricFeatures', 'Live features'),
                    value: String(gpsCounts.features || 0),
                  },
                  {
                    id: 'version',
                    label: tx('settingsV2.header.metricVersion', 'GPS version'),
                    value: String(gpsState.version || 1),
                  },
                ].map((metric) => (
                  <View
                    key={metric.id}
                    style={{
                      minWidth: isMobile ? '100%' : 128,
                      borderRadius: 12,
                      borderWidth: 1,
                      borderColor: C.border,
                      backgroundColor: C.bgSoft,
                      padding: 10,
                    }}
                    data-testid={`settings-v2-header-metric-${metric.id}`}
                    testID={`settings-v2-header-metric-${metric.id}`}
                  >
                    <Text style={{ color: C.textMuted, fontSize: 11 }}>{metric.label}</Text>
                    <Text style={{ color: C.text, fontSize: 16, fontWeight: '800', marginTop: 3 }}>{metric.value}</Text>
                  </View>
                ))}
              </View>
            </View>
          </GLSSection>

          <GLSSection noVerticalPadding style={{ paddingBottom: 10 }} testID="settings-v2-status-section">
            {status ? (
              <View
                style={{
                  borderRadius: 12,
                  borderWidth: 1,
                  borderColor: status.type === 'success' ? `${C.success}55` : `${C.error}55`,
                  backgroundColor: status.type === 'success' ? `${C.success}12` : `${C.error}12`,
                  paddingHorizontal: 12,
                  paddingVertical: 10,
                  flexDirection: 'row',
                  alignItems: 'center',
                  gap: 8,
                }}
                data-testid="settings-v2-status-banner"
                testID="settings-v2-status-banner"
              >
                <Ionicons name={status.type === 'success' ? 'checkmark-circle' : 'alert-circle'} size={16} color={status.type === 'success' ? C.success : C.error} />
                <Text style={{ color: status.type === 'success' ? C.successText : C.error, fontSize: 12, flex: 1 }}>{status.message}</Text>
              </View>
            ) : null}
          </GLSSection>

          <GLSSection noVerticalPadding style={{ paddingBottom: 24 }} testID="settings-v2-main-section">
            {loading ? (
              <View
                style={{
                  borderRadius: 20,
                  borderWidth: 1,
                  borderColor: C.border,
                  backgroundColor: Platform.OS === 'web' ? (globalThis as any).__alphaColor(C.card, theme.darkMode ? 'A8' : 'D8') : C.card,
                  padding: 28,
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: 10,
                  ...(Platform.OS === 'web' ? { backdropFilter: 'blur(12px)', WebkitBackdropFilter: 'blur(12px)' } as any : {}),
                }}
                data-testid="settings-v2-loading-state"
                testID="settings-v2-loading-state"
              >
                <ActivityIndicator size="large" color={C.primary} />
                <Text style={{ color: C.textMuted, fontSize: 12 }}>{tx('settingsV2.common.loading', 'Loading settings...')}</Text>
              </View>
            ) : (
              <View
                style={{
                  flexDirection: isMobile ? 'column' : 'row',
                  alignItems: 'flex-start',
                  gap: 14,
                }}
                data-testid="settings-v2-layout"
                testID="settings-v2-layout"
              >
                {renderSidebar()}

                <View
                  style={{
                    flex: 1,
                    width: isMobile ? '100%' : undefined,
                    borderRadius: 20,
                    borderWidth: 1,
                    borderColor: C.border,
                    backgroundColor: Platform.OS === 'web' ? (globalThis as any).__alphaColor(C.card, theme.darkMode ? 'A8' : 'DA') : C.card,
                    padding: isMobile ? 14 : 18,
                    ...(Platform.OS === 'web' ? { backdropFilter: 'blur(12px)', WebkitBackdropFilter: 'blur(12px)' } as any : {}),
                  }}
                  data-testid="settings-v2-active-panel"
                  testID="settings-v2-active-panel"
                >
                  {renderActivePanel()}
                </View>
              </View>
            )}
          </GLSSection>
        </ScrollView>
      </View>
    </AppShell>
  );
}
