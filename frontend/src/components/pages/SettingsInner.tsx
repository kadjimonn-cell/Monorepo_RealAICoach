import React, { useState, useEffect, useMemo, useCallback } from 'react';
import { useAutoRefresh } from '../../hooks/useAutoRefresh';
import { useAutoSave } from '../../hooks/useAutoSave';
import { View, Text, ScrollView, TouchableOpacity, Switch, Alert, Platform, useWindowDimensions, LayoutAnimation, Image } from 'react-native';
// eslint-disable-next-line @typescript-eslint/no-unused-vars
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { useAuth } from '../../context/AuthContext';
import api from '../../services/api';
import { useTheme } from '../../context/ThemeContext';
import { useAccessibility, AccessibilityPreferences } from '../../context/AccessibilityContext';
import { useTranslation } from '../../hooks/useTranslation';
import { getDisplayPlan, normalizeRole } from '../../utils/subscription';
import { PAGE_COLLECTIONS } from '../PageFloatingBackground';
import { useBackgroundBrightness, PRESET_OPTIONS, PRESET_COLLECTIONS, PAGE_VARIANT_INFO } from '../../context/BackgroundBrightnessContext';
import AppShell from '../AppShell';
import { SecuritySettingsSkeleton, usePageReady } from '../SkeletonLoaders';
import EnterpriseDisclaimerToken from '../tokens/EnterpriseDisclaimerToken';


const A11Y_ITEMS = [
  { section: 'Vision', icon: 'eye-outline', items: [
    { key: 'textSize', label: 'Text Size', type: 'segmented', options: ['small','medium','large','extra-large'], labels: ['S','M','L','XL'] },
    { key: 'dyslexiaFont', label: 'Dyslexia-Friendly Font', type: 'toggle', desc: 'OpenDyslexic typeface' },
    { key: 'highContrast', label: 'High Contrast', type: 'toggle', desc: 'Increases contrast by 35%' },
    { key: 'colorBlindMode', label: 'Color Blind Mode', type: 'select', options: ['none','protanopia','deuteranopia','tritanopia'], labels: ['Off','Protanopia','Deuteranopia','Tritanopia'] },
  ]},
  { section: 'Navigation', icon: 'navigate-outline', items: [
    { key: 'keyboardNavigation', label: 'Keyboard Navigation', type: 'toggle', desc: 'Enhanced tab-order' },
    { key: 'focusIndicators', label: 'Focus Indicators', type: 'toggle', desc: 'Visible focus outlines' },
    { key: 'motionReduction', label: 'Reduce Motion', type: 'toggle', desc: 'Disables animations' },
    { key: 'buttonSpacing', label: 'Larger Touch Targets', type: 'toggle', desc: 'Bigger buttons & spacing' },
  ]},
];

type Tab = 'account' | 'notifications' | 'appearance' | 'accessibility' | 'about';

function isPresetActive(prefs: any, settings: Record<string, any>): boolean {
  return Object.entries(settings).every(([k, v]) => prefs[k] === v);
}

export default function SettingsScreen() {
  const theme = useTheme();

  // @autofix-moved: was module-level const ACCENT_COLORS
  const _ACCENT_COLORS = [
    { id: 'blue', color: theme.colors.accent }, { id: 'indigo', color: theme.colors.primary },
    { id: 'purple', color: theme.colors.accent }, { id: 'pink', color: theme.colors.accent },
    { id: 'red', color: theme.colors.error }, { id: 'orange', color: theme.colors.warningText },
    { id: 'green', color: theme.colors.successText }, { id: 'teal', color: theme.colors.accent },
  ];
  // @autofix-moved: was module-level const A11Y_PRESETS
  const A11Y_PRESETS = [
    { id: 'low-vision', name: 'Low Vision', desc: 'Large text, high contrast', icon: 'eye-outline', color: theme.colors.primary,
      settings: { textSize: 'extra-large' as const, highContrast: true, focusIndicators: true, buttonSpacing: true, contrastMode: 'ultra-contrast' as const } },
    { id: 'motor-impairment', name: 'Motor Impairment', desc: 'Large targets, keyboard nav', icon: 'hand-left-outline', color: theme.colors.successText,
      settings: { buttonSpacing: true, keyboardNavigation: true, focusIndicators: true, easyNavMode: true, textSize: 'large' as const } },
    { id: 'dyslexia', name: 'Dyslexia', desc: 'OpenDyslexic font, reading guide', icon: 'book-outline', color: theme.colors.accent,
      settings: { dyslexiaFont: true, readingGuide: true, textSize: 'large' as const, motionReduction: true } },
    { id: 'sensory', name: 'Sensory Sensitivity', desc: 'Reduced motion, calm UI', icon: 'leaf-outline', color: theme.colors.warningText,
      settings: { motionReduction: true, simplifiedNav: true, contrastMode: 'light' as const } },
  ];
  const pageReady = usePageReady();
  const router = useRouter();
  const { user, isAuthenticated, logout } = useAuth();
  const { brightness, setBrightness, preset, setPreset, pageOverrides, setPageOverride } = useBackgroundBrightness();
  const { t } = useTranslation();
  const tx = useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);
  const { prefs, updatePref, resetAll, applyPreset, activeCount } = useAccessibility();
  const displayPlan = getDisplayPlan(user);
  const isAdmin = normalizeRole(user?.role) === 'admin' || user?.is_admin;
  const [tab, setTab] = useState<Tab>('account');
  const { width } = useWindowDimensions();
  const isMobile = width < 768;
  const currentCurrency = String((user as any)?.currency_preference || (typeof window !== 'undefined' ? window.localStorage.getItem('currency_preference') : '') || 'USD').toUpperCase();

  const C = useMemo(() => ({
    ...theme.colors,
    primary: theme.colors.primary, bg: theme.colors.bg, bgSoft: theme.colors.bgSoft,
    card: theme.colors.card, text: theme.colors.text, textSec: theme.colors.textSec,
    textMuted: theme.colors.textMuted, border: theme.colors.border,
    green: theme.colors.success, red: theme.colors.error, yellow: theme.colors.warning, purple: theme.colors.purple, blue: theme.colors.primary, cyan: theme.colors.info,
  }), [theme.colors]);
  const colors = C;

  // Notification states
  const [pushNotifications, setPushNotifications] = useState(true);
  const [emailNotifications, setEmailNotifications] = useState(true);
  const [dailyBriefing, setDailyBriefing] = useState(true);
  const [practiceReminders, setPracticeReminders] = useState(true);
  const [achievementAlerts, setAchievementAlerts] = useState(true);
  const [weeklyDigest, setWeeklyDigest] = useState(true);
  const [teamUpdates, setTeamUpdates] = useState(true);
  const [goalReminders, setGoalReminders] = useState(true);
  const [coachingNudges, setCoachingNudges] = useState(true);
  const [soundEnabled, setSoundEnabled] = useState(true);
  const [quietHoursEnabled, setQuietHoursEnabled] = useState(false);
  const [quietStart, setQuietStart] = useState('22:00');
  const [quietEnd, setQuietEnd] = useState('07:00');

  // Linked accounts
  const [linkedProviders, setLinkedProviders] = useState<any[]>([]);
  const [primaryProvider, setPrimaryProvider] = useState('email');
  const [unlinkingProvider, setUnlinkingProvider] = useState<string | null>(null);

  // Settings integrations health
  const [settingsIntegrationsLoading, setSettingsIntegrationsLoading] = useState(false);
  const [settingsIntegrationsError, setSettingsIntegrationsError] = useState<string | null>(null);
  const [settingsAvailableIntegrations, setSettingsAvailableIntegrations] = useState<any[]>([]);
  const [settingsConnectedIntegrations, setSettingsConnectedIntegrations] = useState<any[]>([]);
  const [settingsIntegrationStats, setSettingsIntegrationStats] = useState<any>(null);

  // Account merge
  const [mergeCandidates, setMergeCandidates] = useState<any[]>([]);
  const [merging, setMerging] = useState(false);
  const [mergeResult, setMergeResult] = useState<any>(null);

  useEffect(() => {
    if (user?.user_id) {
      api.get('/notifications/settings').then(r => {
        const s = r.data;
        setPushNotifications(s.push_enabled ?? true);
        setEmailNotifications(s.email_enabled ?? true);
        setDailyBriefing(s.daily_briefing ?? true);
        setPracticeReminders(s.practice_reminders ?? true);
        setAchievementAlerts(s.achievement_alerts ?? true);
        setWeeklyDigest(s.weekly_digest ?? true);
        setTeamUpdates(s.team_updates ?? true);
        setGoalReminders(s.goal_reminders ?? true);
        setCoachingNudges(s.coaching_nudges ?? true);
        setQuietHoursEnabled(s.quiet_hours_enabled ?? false);
        setQuietStart(s.quiet_hours_start ?? '22:00');
        setQuietEnd(s.quiet_hours_end ?? '07:00');
      }).catch(() => {});
      api.get('/auth/linked-accounts').then(r => {
        setLinkedProviders(r.data.providers || []);
        setPrimaryProvider(r.data.primary_provider || 'email');
      }).catch(() => {});
      api.get('/auth/merge/candidates').then(r => {
        setMergeCandidates(r.data.candidates || []);
      }).catch(() => {});
      AsyncStorage.getItem('app_settings').then(v => {
        if (v) { const s = JSON.parse(v); setSoundEnabled(s.soundEnabled ?? true); }
      }).catch(() => {});
    }
  }, [user?.user_id]);

  const loadSettingsIntegrationData = useCallback(async () => {
    setSettingsIntegrationsLoading(true);
    setSettingsIntegrationsError(null);
    try {
      const [availableRes, connectedRes, statsRes] = await Promise.allSettled([
        api.get('/integrations/available'),
        api.get('/integrations/'),
        api.get('/integrations/dashboard/stats'),
      ]);

      if (availableRes.status === 'fulfilled') {
        setSettingsAvailableIntegrations(Array.isArray(availableRes.value.data?.integrations) ? availableRes.value.data.integrations : []);
      } else {
        setSettingsAvailableIntegrations([]);
      }

      if (connectedRes.status === 'fulfilled') {
        setSettingsConnectedIntegrations(Array.isArray(connectedRes.value.data?.integrations) ? connectedRes.value.data.integrations : []);
      } else {
        setSettingsConnectedIntegrations([]);
      }

      if (statsRes.status === 'fulfilled') {
        setSettingsIntegrationStats(statsRes.value.data || null);
      } else {
        setSettingsIntegrationStats(null);
      }

      if (
        availableRes.status === 'rejected' &&
        connectedRes.status === 'rejected' &&
        statsRes.status === 'rejected'
      ) {
        setSettingsIntegrationsError(tx('settings.integrations.error', 'Unable to load integration status.'));
      }
    } catch {
      setSettingsAvailableIntegrations([]);
      setSettingsConnectedIntegrations([]);
      setSettingsIntegrationStats(null);
      setSettingsIntegrationsError(tx('settings.integrations.error', 'Unable to load integration status.'));
    } finally {
      setSettingsIntegrationsLoading(false);
    }
  }, [tx]);

  useEffect(() => {
    if (user?.user_id) {
      void loadSettingsIntegrationData();
    }
  }, [user?.user_id, loadSettingsIntegrationData]);

  useAutoRefresh(() => {
    if (!user?.user_id) return;
    api.get('/notifications/settings').then(r => {
      const s = r.data;
      setPushNotifications(s.push_enabled ?? true);
      setEmailNotifications(s.email_enabled ?? true);
    }).catch(() => {});
  }, { intervalMs: 30000 });

  useAutoRefresh(() => {
    if (!user?.user_id) return;
    void loadSettingsIntegrationData();
  }, { intervalMs: 45000 });

  // Auto-save notification settings
  const settingsData = React.useMemo(() => ({
    push_enabled: pushNotifications,
    email_enabled: emailNotifications,
  }), [pushNotifications, emailNotifications]);
  useAutoSave('/notifications/settings', settingsData, { enabled: !!user?.user_id, method: 'put' });

  const updateNotif = (field: string, value: any) => { api.put('/notifications/settings', { [field]: value }).catch(() => {}); };
  const saveLocal = (key: string, value: any) => {
    AsyncStorage.getItem('app_settings').then(v => {
      const s = v ? JSON.parse(v) : {};
      s[key] = value;
      AsyncStorage.setItem('app_settings', JSON.stringify(s));
    }).catch(() => {});
  };

  const switchTab = (t: Tab) => {
    if (Platform.OS !== 'web') LayoutAnimation.configureNext(LayoutAnimation.Presets.easeInEaseOut);
    setTab(t);
  };

  const performLogout = async () => {
    try {
      await logout();
    } finally {
      if (typeof window !== 'undefined') {
        window.location.href = '/auth/login?logout=1';
        return;
      }
      router.replace('/auth/login?logout=1');
    }
  };

  const handleUnlink = async (provider: string) => {
    setUnlinkingProvider(provider);
    try {
      await api.post(`/auth/unlink-account/${provider}`);
      const r = await api.get('/auth/linked-accounts');
      setLinkedProviders(r.data.providers || []);
      setPrimaryProvider(r.data.primary_provider || 'email');
    } catch (e: any) {
      if (Platform.OS === 'web') alert(e?.response?.data?.detail || 'Failed to unlink');
    } finally { setUnlinkingProvider(null); }
  };

  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const _handleLinkMicrosoft = () => {
    const apiBase = (((process.env.REACT_APP_BACKEND_URL || process.env.EXPO_PUBLIC_BACKEND_URL) || (typeof window !== 'undefined' ? (`https://${window.location.host}`) : '')) || '').replace(/\/+$/, '');
    if (Platform.OS === 'web') {
      const target = window.top || window;
      target.location.href = `${apiBase}/api/auth/link/microsoft`;
    }
  };

  const handleMerge = async (secondaryUserId: string) => {
    if (Platform.OS === 'web') {
      const ok = window.confirm('Are you sure you want to merge this account? This action cannot be undone. All data from the duplicate account will be transferred to your current account.');
      if (!ok) return;
    }
    setMerging(true);
    setMergeResult(null);
    try {
      const r = await api.post('/auth/merge/execute', { secondary_user_id: secondaryUserId });
      setMergeResult(r.data);
      setMergeCandidates(prev => prev.filter(c => c.user_id !== secondaryUserId));
      // Refresh linked accounts
      const la = await api.get('/auth/linked-accounts');
      setLinkedProviders(la.data.providers || []);
      setPrimaryProvider(la.data.primary_provider || 'email');
    } catch (e: any) {
      if (Platform.OS === 'web') alert(e?.response?.data?.detail || 'Merge failed');
    } finally { setMerging(false); }
  };

  const TABS: { key: Tab; label: string; icon: string }[] = [
    { key: 'account', label: t('settings.section.account'), icon: 'person-outline' },
    { key: 'notifications', label: t('settings.section.notifications'), icon: 'notifications-outline' },
    { key: 'appearance', label: t('settings.item.theme'), icon: 'color-palette-outline' },
    { key: 'accessibility', label: 'A11y', icon: 'accessibility-outline' },
    { key: 'about', label: t('settings.section.about'), icon: 'information-circle-outline' },
  ];

  /* ── Reusable components ── */
  const Card = ({ children, style }: any) => (
    <View style={[{
      backgroundColor: C.card, borderRadius: 20, borderWidth: 1, borderColor: C.border,
      overflow: 'hidden', marginBottom: 20,
      ...(Platform.OS === 'web' ? { transition: 'all 0.2s ease' } as any : {}),
    }, style]}>
      {children}
    </View>
  );

  const Row = ({ icon, iconColor, iconBg, title, sub, right, onPress, testId, last }: any) => (
    <TouchableOpacity disabled={!onPress} onPress={onPress} activeOpacity={onPress ? 0.7 : 1} accessibilityLabel="Press"
      style={{
        flexDirection: 'row', alignItems: 'center', padding: 16, gap: 14,
        borderBottomWidth: last ? 0 : 1, borderBottomColor: (globalThis as any).__alphaColor(C.border, '60'),
        ...(Platform.OS === 'web' ? { transition: 'background-color 0.15s ease' } as any : {}),
      }}
      data-testid={testId} testID={testId}
      >
      <View style={{ width: 40, height: 40, borderRadius: 12, backgroundColor: (globalThis as any).__alphaColor(iconBg || C.primary, '12'), alignItems: 'center', justifyContent: 'center' }}>
        <Ionicons name={icon} size={18} color={iconColor || C.primary} />
      </View>
      <View style={{ flex: 1 }}>
        <Text style={{ fontSize: 14, fontWeight: '600', color: C.text, letterSpacing: -0.1 }}>{title}</Text>
        {sub && <Text style={{ fontSize: 11, color: C.textMuted, marginTop: 3, lineHeight: 15 }}>{sub}</Text>}
      </View>
      {right}
      {onPress && !right && <Ionicons name="chevron-forward" size={16} color={C.textMuted} />}
    </TouchableOpacity>
  );

  const Toggle = ({ value, onChange, testId }: any) => (
    <Switch value={value} onValueChange={onChange}
      trackColor={{ false: C.border, true: C.primary + '50' }}
                              thumbColor={value ? C.primary : C.surface}
      data-testid={testId} testID={testId}
      style={Platform.OS === 'web' ? { transform: [{ scale: 0.85 }] } as any : {}} />
  );

  const SectionHead = ({ title, icon, extra }: any) => (
    <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12, marginTop: 4 }}>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
        {icon && <Ionicons name={icon} size={15} color={C.primary} />}
        <Text style={{ fontSize: 11, fontWeight: '800', textTransform: 'uppercase', letterSpacing: 1.4, color: C.textMuted }}>{title}</Text>
      </View>
      {extra}
    </View>
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
        category: integration?.category || tx('settings.integrations.category.general', 'General'),
        connected: Boolean(connected),
        mode: connected?.test_mode ? tx('settings.integrations.mode.test', 'Test') : tx('settings.integrations.mode.live', 'Live'),
        lastSync: connected?.sync_status?.last_sync,
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
    if (names.length === 0) {
      return tx('settings.integrations.catalog.empty', 'Open integrations command center');
    }
    return names.join(', ');
  }, [settingsAvailableIntegrations, tx]);

  if (!pageReady) return <AppShell><SecuritySettingsSkeleton /></AppShell>;
  return (
    <AppShell>
      <View style={{ flex: 1, backgroundColor: C.bg }} data-testid="settings-screen" testID="settings-screen">
        {/* Header */}
        <View style={{
          backgroundColor: C.card, borderBottomWidth: 1, borderBottomColor: C.border,
          paddingHorizontal: isMobile ? 16 : 24, paddingTop: 16, paddingBottom: 0,
        }} data-testid="settings-header" testID="settings-header">
          <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 14 }}>
              <TouchableOpacity onPress={() => router.back()}
                style={{ width: 38, height: 38, borderRadius: 12, backgroundColor: C.bgSoft, alignItems: 'center', justifyContent: 'center' }}
                data-testid="settings-back-button" testID="settings-back-button">
                <Ionicons name="arrow-back" size={18} color={C.text} />
              </TouchableOpacity>
              <View>
                <Text style={{ fontSize: 22, fontWeight: '800', color: C.text, letterSpacing: -0.5 }} data-testid="settings-header-title" testID="settings-header-title">{t('settings.title')}</Text>
                <Text style={{ fontSize: 12, color: C.textMuted, marginTop: 2 }}>{t('settings.subtitle')}</Text>
              </View>
            </View>
            {isAuthenticated && (
              <TouchableOpacity onPress={performLogout}
                style={{ flexDirection: 'row', alignItems: 'center', gap: 5, paddingHorizontal: 14, paddingVertical: 8, borderRadius: 10, backgroundColor: (globalThis as any).__alphaColor(C.red, '10') }}
                data-testid="settings-header-logout-button" testID="settings-header-logout-button">
                <Ionicons name="log-out-outline" size={14} color={C.red} />
                <Text style={{ fontSize: 12, fontWeight: '600', color: C.red }}>{t('profile.logout')}</Text>
              </TouchableOpacity>
            )}
          </View>

          <View style={{ flexDirection: 'row', gap: 8, marginBottom: 12 }} data-testid="settings-locale-quick-actions" testID="settings-locale-quick-actions">
            <TouchableOpacity
              onPress={() => router.push('/language-selector')}
              style={{ flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 12, paddingVertical: 8, borderRadius: 10, borderWidth: 1, borderColor: C.border, backgroundColor: C.bgSoft }}
              data-testid="settings-language-button" testID="settings-language-button"
            >
              <Ionicons name="language-outline" size={14} color={C.textMuted} />
              <Text style={{ fontSize: 12, fontWeight: '700', color: C.text }}>{t('settings.item.language')}</Text>
            </TouchableOpacity>
            <TouchableOpacity
              onPress={() => router.push('/currency-selector')}
              style={{ flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 12, paddingVertical: 8, borderRadius: 10, borderWidth: 1, borderColor: C.border, backgroundColor: C.bgSoft }}
              data-testid="settings-currency-button" testID="settings-currency-button"
            >
              <Ionicons name="cash-outline" size={14} color={C.textMuted} />
              <Text style={{ fontSize: 12, fontWeight: '700', color: C.text }}>{currentCurrency}</Text>
            </TouchableOpacity>
          </View>

          {/* Pill Tab Bar */}
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 8, paddingBottom: 14 }}>
            {TABS.map(t => {
              const active = tab === t.key;
              return (
                <TouchableOpacity key={t.key} onPress={() => switchTab(t.key)} data-testid={`settings-tab-${t.key}`} testID={`settings-tab-${t.key}`}
                  style={{
                    flexDirection: 'row', alignItems: 'center', gap: 6,
                    paddingHorizontal: 16, paddingVertical: 10, borderRadius: 12,
                    backgroundColor: active ? C.primary : 'transparent',
                    borderWidth: active ? 0 : 1,
                    borderColor: C.border,
                    ...(Platform.OS === 'web' ? { transition: 'all 0.2s ease' } as any : {}),
                  }}>
                <Ionicons name={t.icon as any} size={15} color={active ? C.primaryText : C.textMuted} />
                <Text style={{ fontSize: 13, fontWeight: active ? '700' : '500', color: active ? C.primaryText : C.textMuted }}>{t.label}</Text>
                </TouchableOpacity>
              );
            })}
          </ScrollView>
        </View>

        <ScrollView showsVerticalScrollIndicator={false}
          contentContainerStyle={{ padding: isMobile ? 16 : 24, paddingBottom: 60, maxWidth: 960, alignSelf: 'center', width: '100%' }}>

          {/* ─── ACCOUNT TAB ─── */}
          {tab === 'account' && (
            <>
              {/* Profile Quick Card */}
              {isAuthenticated && user && (
                <TouchableOpacity onPress={() => router.push('/profile')} activeOpacity={0.8} data-testid="settings-profile-card" testID="settings-profile-card"
                  style={{
                    flexDirection: 'row', alignItems: 'center', backgroundColor: C.card,
                    borderRadius: 20, padding: 18, marginBottom: 20, borderWidth: 1, borderColor: C.border,
                  }}>
                  <View style={{ width: 56, height: 56, borderRadius: 16, backgroundColor: (globalThis as any).__alphaColor(C.primary, '15'), alignItems: 'center', justifyContent: 'center', overflow: 'hidden' as const }}>
                    {(user as any).profile_image ? (
                      Platform.OS === 'web' ? (
                        <img src={(user as any).profile_image} style={{ width: 56, height: 56, borderRadius: 16, objectFit: 'cover' } as any} alt="" />
                      ) : (
                        <Image source={{ uri: (user as any).profile_image }} style={{ width: 56, height: 56, borderRadius: 16 }} accessibilityLabel="Decorative image" />
                      )
                    ) : (
                      <Text style={{ fontSize: 22, fontWeight: '800', color: C.primary }}>{(user.name || 'U').charAt(0).toUpperCase()}</Text>
                    )}
                  </View>
                  <View style={{ flex: 1, marginLeft: 16 }}>
                    <Text style={{ fontSize: 17, fontWeight: '700', color: C.text, letterSpacing: -0.2 }}>{user.name || 'User'}</Text>
                    <Text style={{ fontSize: 12, color: C.textMuted, marginTop: 3 }}>{user.email}</Text>
                  </View>
                  <View style={{ backgroundColor: C.primary, paddingHorizontal: 12, paddingVertical: 5, borderRadius: 10, marginRight: 8 }}>
                    <Text style={{ fontSize: 10, fontWeight: '700', color: colors.primaryText, textTransform: 'capitalize' }}>{displayPlan || 'free'}</Text>
                  </View>
                  <Ionicons name="chevron-forward" size={18} color={C.textMuted} />
                </TouchableOpacity>
              )}

              <SectionHead title="Account" icon="person-circle-outline" />
              <Card>
                <Row icon="create-outline" title="Edit Profile" sub="Name, bio, photo" onPress={() => router.push('/edit-profile')} testId="settings-edit-profile-button" />
              <Row icon="diamond-outline" iconColor={C.success} iconBg={`${C.success}15`} title="Subscription" sub="Manage your plan" onPress={() => router.push('/subscription/plans')} testId="settings-subscription-button" />
              <Row icon="card-outline" iconColor={C.primary} iconBg={`${C.primary}15`} title="Payment Cards" sub="Saved payment methods" onPress={() => router.push('/settings/payment-cards')} testId="settings-payment-cards-button" />
                <Row icon="shield-checkmark-outline" iconColor={C.green} iconBg={C.green + '15'} title="Privacy & Security" sub="Password, 2FA, data" onPress={() => router.push('/privacy-security')} testId="settings-privacy-security-button" />
                <Row icon="lock-closed-outline" iconColor={C.cyan} iconBg={C.cyan + '15'} title="Security Settings" sub="2FA, PIN, Passkey, Biometrics" onPress={() => router.push('/security')} testId="settings-security-button" last />
              </Card>

              <View
                style={{ marginTop: 14, marginBottom: 6 }}
                data-testid="settings-v1-workspace-tenant-disclaimer-slot"
                testID="settings-v1-workspace-tenant-disclaimer-slot"
              >
                <EnterpriseDisclaimerToken
                  context="banner"
                  testIdPrefix="settings-workspace-ai-disclaimer"
                  maxWidth={960}
                />
              </View>

              <SectionHead title="Integrations" icon="git-network-outline" />

              {/* Linked Accounts Section */}
              <SectionHead title="Linked Accounts" icon="link-outline" />
              <Card>
                {linkedProviders.map((p: any, i: number) => {
                  const isLast = i === linkedProviders.length - 1;
                  const providerConfig: Record<string, { icon: string; color: string; label: string; bg: string }> = {
              email: { icon: 'mail-outline', color: colors.primary, label: 'Email & Password', bg: `${colors.primary}15` },
              google: { icon: 'logo-google', color: colors.error, label: 'Google', bg: `${colors.error}15` },
              microsoft: { icon: 'logo-microsoft', color: colors.info, label: 'Microsoft', bg: `${colors.info}15` },
                    apple: { icon: 'logo-apple', color: C.text, label: 'Apple', bg: C.text + '10' },
                  };
                  const cfg = providerConfig[p.provider] || { icon: 'help-outline', color: C.textSec, label: p.provider, bg: C.bgSoft };
                  return (
                    <View key={p.provider} style={{ flexDirection: 'row', alignItems: 'center', paddingVertical: 14, paddingHorizontal: 16, borderBottomWidth: isLast ? 0 : 1, borderBottomColor: C.border }} data-testid={`linked-account-${p.provider}`} testID={`linked-account-${p.provider}`}>
                      <View style={{ width: 36, height: 36, borderRadius: 10, backgroundColor: cfg.bg, alignItems: 'center', justifyContent: 'center', marginRight: 12 }}>
                        <Ionicons name={cfg.icon as any} size={18} color={cfg.color} />
                      </View>
                      <View style={{ flex: 1 }}>
                        <Text style={{ fontSize: 14, fontWeight: '600', color: C.text }}>{cfg.label}</Text>
                        <Text style={{ fontSize: 11, color: C.textMuted, marginTop: 2 }}>
                          {p.linked ? (p.provider === 'email' ? user?.email : `Connected${primaryProvider === p.provider ? ' (Primary)' : ''}`) : 'Not connected'}
                        </Text>
                      </View>
                      {p.provider !== 'email' && (
                        p.linked ? (
                          <TouchableOpacity
                            style={{ paddingHorizontal: 12, paddingVertical: 6, borderRadius: 8, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(C.red, '40'), backgroundColor: (globalThis as any).__alphaColor(C.red, '10'), opacity: unlinkingProvider === p.provider ? 0.5 : 1 }}
                            onPress={() => handleUnlink(p.provider)}
                            disabled={unlinkingProvider !== null}
                            data-testid={`unlink-${p.provider}-btn`} testID={`unlink-${p.provider}-btn`}
                          >
                            <Text style={{ fontSize: 12, fontWeight: '600', color: C.red }}>{unlinkingProvider === p.provider ? 'Unlinking...' : 'Unlink'}</Text>
                          </TouchableOpacity>
                        ) : (
                          <TouchableOpacity accessibilityLabel="Const in settings inner button"
                            style={{ paddingHorizontal: 12, paddingVertical: 6, borderRadius: 8, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(cfg.color, '40'), backgroundColor: (globalThis as any).__alphaColor(cfg.color, '10') }}
                            onPress={() => {
                              const apiBase = (((process.env.REACT_APP_BACKEND_URL || process.env.EXPO_PUBLIC_BACKEND_URL) || (typeof window !== 'undefined' ? (`https://${window.location.host}`) : '')) || '').replace(/\/+$/, '');
                              const target = (Platform.OS === 'web' ? (window.top || window) : window) as any;
                              if (p.provider === 'microsoft') {
                                target.location.href = `${apiBase}/api/auth/link/microsoft`;
                              } else if (p.provider === 'apple') {
                                target.location.href = `${apiBase}/api/auth/link/apple`;
                              } else {
                                target.location.href = `${apiBase}/api/auth/link/google`;
                              }
                            }}
                            data-testid={`link-${p.provider}-btn`} testID={`link-${p.provider}-btn`}
                          >
                            <Text style={{ fontSize: 12, fontWeight: '600', color: cfg.color }}>Link</Text>
                          </TouchableOpacity>
                        )
                      )}
                    </View>
                  );
                })}
              </Card>

              <SectionHead
                title={tx('settings.integrations.health.title', 'Platform Integration Health')}
                icon="analytics-outline"
                extra={
                  <TouchableOpacity accessibilityLabel="Settings integrations refresh button"
                    onPress={() => void loadSettingsIntegrationData()}
                    style={{
                      flexDirection: 'row',
                      alignItems: 'center',
                      gap: 4,
                      paddingHorizontal: 10,
                      paddingVertical: 5,
                      borderRadius: 999,
                      borderWidth: 1,
                      borderColor: (globalThis as any).__alphaColor(C.primary, '50'),
                      backgroundColor: (globalThis as any).__alphaColor(C.primary, '12'),
                    }}
                    data-testid="settings-integrations-refresh-button"
                    testID="settings-integrations-refresh-button"
                  >
                    <Ionicons name="refresh-outline" size={12} color={C.primary} />
                    <Text style={{ fontSize: 10, fontWeight: '700', color: C.primary }}>
                      {tx('settings.integrations.refresh', 'Refresh')}
                    </Text>
                  </TouchableOpacity>
                }
              />
              <Card>
                <View style={{ padding: 14, gap: 12 }} data-testid="settings-integrations-enterprise-block" testID="settings-integrations-enterprise-block">
                  <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
                    {[
                      {
                        id: 'active',
                        label: tx('settings.integrations.kpi.active', 'Active'),
                        value: settingsIntegrationStats?.active_integrations ?? settingsConnectedIntegrations.length,
                        tone: C.primary,
                      },
                      {
                        id: 'candidates',
                        label: tx('settings.integrations.kpi.candidates', 'Candidates'),
                        value: settingsIntegrationStats?.total_candidates ?? 0,
                        tone: C.info,
                      },
                      {
                        id: 'jobs',
                        label: tx('settings.integrations.kpi.jobs', 'Jobs'),
                        value: settingsIntegrationStats?.total_jobs ?? 0,
                        tone: C.green,
                      },
                      {
                        id: 'catalog',
                        label: tx('settings.integrations.kpi.catalog', 'Catalog'),
                        value: settingsAvailableIntegrations.length,
                        tone: C.warning,
                      },
                    ].map((item) => (
                      <View
                        key={item.id}
                        style={{
                          minWidth: 120,
                          borderRadius: 10,
                          borderWidth: 1,
                          borderColor: `${item.tone}45`,
                          backgroundColor: `${item.tone}15`,
                          paddingHorizontal: 10,
                          paddingVertical: 8,
                          flex: 1,
                        }}
                        data-testid={`settings-integrations-kpi-${item.id}`}
                        testID={`settings-integrations-kpi-${item.id}`}
                      >
                        <Text style={{ fontSize: 10, fontWeight: '800', color: item.tone, textTransform: 'uppercase' }}>{item.label}</Text>
                        <Text style={{ fontSize: 15, fontWeight: '900', color: C.text, marginTop: 2 }}>{String(item.value || 0)}</Text>
                      </View>
                    ))}
                  </View>

                  {settingsIntegrationsLoading ? (
                    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, paddingVertical: 4 }} data-testid="settings-integrations-loading-row" testID="settings-integrations-loading-row">
                      <Ionicons name="hourglass-outline" size={14} color={C.primary} />
                      <Text style={{ fontSize: 11, color: C.textMuted }}>{tx('settings.integrations.loading', 'Loading integration telemetry...')}</Text>
                    </View>
                  ) : null}

                  {settingsIntegrationsError ? (
                    <Text style={{ fontSize: 11, color: C.red }} data-testid="settings-integrations-error-text" testID="settings-integrations-error-text">
                      {settingsIntegrationsError}
                    </Text>
                  ) : null}

                  <View style={{ gap: 8 }}>
                    {settingsMergedIntegrations.slice(0, 4).map((item: any, idx: number) => (
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
                        data-testid={`settings-integrations-connector-row-${item.id || idx}`}
                        testID={`settings-integrations-connector-row-${item.id || idx}`}
                      >
                        <Ionicons name={(item.icon || 'link-outline') as any} size={14} color={item.connected ? C.green : C.textMuted} />
                        <View style={{ flex: 1 }}>
                          <Text style={{ fontSize: 12, fontWeight: '700', color: C.text }}>{item.name}</Text>
                          <Text style={{ fontSize: 10, color: C.textMuted }}>{item.category}</Text>
                        </View>
                        <View style={{ borderRadius: 999, borderWidth: 1, borderColor: item.connected ? (globalThis as any).__alphaColor(C.green, '45') : C.warning + '45', backgroundColor: item.connected ? (globalThis as any).__alphaColor(C.green, '12') : C.warning + '12', paddingHorizontal: 8, paddingVertical: 4 }}>
                          <Text style={{ fontSize: 10, fontWeight: '800', color: item.connected ? C.green : C.warningText }}>
                            {item.connected ? tx('settings.integrations.connected', 'CONNECTED') : tx('settings.integrations.notConnected', 'NOT CONNECTED')}
                          </Text>
                        </View>
                      </View>
                    ))}
                  </View>

                  {settingsRecentSyncs.length > 0 ? (
                    <View style={{ gap: 6 }} data-testid="settings-integrations-recent-syncs" testID="settings-integrations-recent-syncs">
                      <Text style={{ fontSize: 11, fontWeight: '700', color: C.textSec }}>
                        {tx('settings.integrations.recentSyncs', 'Recent Sync Activity')}
                      </Text>
                      {settingsRecentSyncs.map((sync: any, idx: number) => (
                        <Text key={`${sync?.config_id || idx}`} style={{ fontSize: 10, color: C.textMuted }} data-testid={`settings-integrations-sync-item-${idx}`} testID={`settings-integrations-sync-item-${idx}`}>
                          • {sync?.integration_id || tx('settings.integrations.connector', 'Connector')} · {sync?.status || tx('settings.integrations.statusUnknown', 'status unknown')}
                        </Text>
                      ))}
                    </View>
                  ) : null}

                  <TouchableOpacity accessibilityLabel="Settings integrations open command center button"
                    onPress={() => router.push('/integrations')}
                    style={{
                      flexDirection: 'row',
                      alignItems: 'center',
                      justifyContent: 'center',
                      gap: 8,
                      borderRadius: 12,
                      borderWidth: 1,
                      borderColor: (globalThis as any).__alphaColor(C.primary, '50'),
                      backgroundColor: (globalThis as any).__alphaColor(C.primary, '12'),
                      paddingVertical: 10,
                    }}
                    data-testid="settings-integrations-open-command-center"
                    testID="settings-integrations-open-command-center"
                  >
                    <Ionicons name="git-network-outline" size={14} color={C.primary} />
                    <Text style={{ fontSize: 12, fontWeight: '800', color: C.primary }}>
                      {tx('settings.integrations.openCommandCenter', 'Open Integrations Command Center')}
                    </Text>
                  </TouchableOpacity>
                </View>
              </Card>

              {/* Account Merge Section */}
              {mergeCandidates.length > 0 && (
                <>
                  <SectionHead title="Merge Duplicate Accounts" icon="git-merge-outline" />
                  <Card>
                    <View style={{ padding: 16 }}>
                      <View style={{ flexDirection: 'row', alignItems: 'center', marginBottom: 12, gap: 8 }}>
                    <Ionicons name="warning-outline" size={18} color={C.warning} />
                        <Text style={{ fontSize: 13, color: colors.warningText, fontWeight: '600' }}>Duplicate accounts detected</Text>
                      </View>
                      <Text style={{ fontSize: 12, color: C.textMuted, marginBottom: 16, lineHeight: 18 }}>
                        We found account(s) with the same email that can be merged into your current account. Merging transfers all data and linked providers.
                      </Text>
                      {mergeCandidates.map((c: any) => {
                        const provIcons: Record<string, string> = { email: 'mail-outline', google: 'logo-google', microsoft: 'logo-microsoft', apple: 'logo-apple' };
                        return (
                          <View key={c.user_id} style={{ backgroundColor: C.bgSoft, borderRadius: 12, padding: 14, marginBottom: 10, borderWidth: 1, borderColor: C.border }} data-testid={`merge-candidate-${c.user_id}`} testID={`merge-candidate-${c.user_id}`}>
                            <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
                              <View style={{ flex: 1 }}>
                                <Text style={{ fontSize: 14, fontWeight: '600', color: C.text }}>{c.name}</Text>
                                <Text style={{ fontSize: 11, color: C.textMuted, marginTop: 2 }}>Signed in via {c.auth_provider} · {c.subscription_plan}</Text>
                                <View style={{ flexDirection: 'row', gap: 6, marginTop: 6 }}>
                                  {c.providers.map((p: string) => (
                                    <View key={p} style={{ width: 24, height: 24, borderRadius: 6, backgroundColor: C.border, alignItems: 'center', justifyContent: 'center' }}>
                                      <Ionicons name={(provIcons[p] || 'help-outline') as any} size={12} color={C.textMuted} />
                                    </View>
                                  ))}
                                </View>
                              </View>
                              <TouchableOpacity
                                style={{ paddingHorizontal: 14, paddingVertical: 8, borderRadius: 10, backgroundColor: colors.warning, opacity: merging ? 0.5 : 1 }}
                                onPress={() => handleMerge(c.user_id)}
                                disabled={merging}
                                data-testid={`merge-btn-${c.user_id}`} testID={`merge-btn-${c.user_id}`}
                              >
                        <Text style={{ fontSize: 12, fontWeight: '700', color: C.text }}>{merging ? 'Merging...' : 'Merge'}</Text>
                              </TouchableOpacity>
                            </View>
                          </View>
                        );
                      })}
                    </View>
                  </Card>
                </>
              )}

              {mergeResult && (
                <Card>
                  <View style={{ padding: 16, flexDirection: 'row', alignItems: 'center', gap: 10 }}>
                    <Ionicons name="checkmark-circle" size={20} color={C.green} />
                    <View style={{ flex: 1 }}>
                      <Text style={{ fontSize: 13, fontWeight: '600', color: C.green }}>Account merged successfully</Text>
                      <Text style={{ fontSize: 11, color: C.textMuted, marginTop: 2 }}>
                        {mergeResult.records_migrated} records transferred{mergeResult.sso_transferred?.length > 0 ? ` · ${mergeResult.sso_transferred.join(', ')} linked` : ''}
                      </Text>
                    </View>
                  </View>
                </Card>
              )}

              <Card>
            <Row icon="calendar-outline" iconColor={C.success} iconBg={`${C.success}15`} title="Google Calendar" sub="Sync events & interviews" onPress={() => router.push('/calendar')} testId="settings-calendar-button" />
            <Row icon="git-network-outline" iconColor={C.primary} iconBg={`${C.primary}15`} title="ATS & HRIS" sub={settingsCatalogPreview} onPress={() => router.push('/integrations')} testId="settings-ats-hris-button" last />
              </Card>

              {isAdmin && (
                <>
                  <SectionHead title="Admin" icon="shield-checkmark-outline" />
                  <Card>
              <Row icon="rocket-outline" iconColor={C.success} iconBg={`${C.success}15`} title="Safe Deployment" sub="Admin rollout strategy" onPress={() => router.push('/safe-deployment')} testId="settings-safe-deployment-button" last />
                  </Card>
                </>
              )}

              {isAuthenticated && (
                <>
                  <SectionHead title="Danger Zone" icon="warning-outline" />
                  <Card style={{ borderColor: (globalThis as any).__alphaColor(C.red, '30') }}>
                    <Row icon="log-out-outline" iconColor={C.yellow} iconBg={C.yellow + '15'} title="Sign Out" sub="You can sign back in anytime" onPress={performLogout} testId="settings-sign-out-button" />
                    <Row icon="trash-outline" iconColor={C.red} iconBg={C.red + '15'} title="Delete Account" sub="Permanently remove your data" testId="settings-delete-account-button" last
                      onPress={() => Alert.alert('Delete Account', 'This action cannot be undone.', [
                        { text: 'Cancel', style: 'cancel' },
                        { text: 'Delete', style: 'destructive', onPress: () => Alert.alert('Contact Support', 'Please contact support@realaicoach.app') }
                      ])} />
                  </Card>
                </>
              )}
            </>
          )}

          {/* ─── NOTIFICATIONS TAB ─── */}
          {tab === 'notifications' && (
            <>
              <SectionHead title="Channels" icon="megaphone-outline" />
              <Card>
                <Row icon="notifications-outline" title="Push Notifications" sub="Real-time alerts on your device" testId="settings-push-notifications-button"
                  right={<Toggle value={pushNotifications} onChange={(v: boolean) => { setPushNotifications(v); updateNotif('push_enabled', v); }} testId="settings-push-notifications-switch" />} />
                <Row icon="mail-outline" title="Email Notifications" sub="Important updates via email" testId="settings-email-notifications-button"
                  right={<Toggle value={emailNotifications} onChange={(v: boolean) => { setEmailNotifications(v); updateNotif('email_enabled', v); }} testId="settings-email-notifications-switch" />} />
                <Row icon="volume-high-outline" title="Sound Effects" sub="In-app notification sounds" testId="settings-sound-effects-button"
                  right={<Toggle value={soundEnabled} onChange={(v: boolean) => { setSoundEnabled(v); saveLocal('soundEnabled', v); }} testId="settings-sound-effects-switch" />} last />
              </Card>

              <SectionHead title="Activity & Content" icon="document-text-outline" />
              <Card>
                <Row icon="today-outline" iconColor={C.yellow} iconBg={C.yellow + '15'} title="Daily Briefing" sub="Personalized daily summary" testId="settings-daily-briefing-button"
                  right={<Toggle value={dailyBriefing} onChange={(v: boolean) => { setDailyBriefing(v); updateNotif('daily_briefing', v); }} testId="settings-daily-briefing-switch" />} />
                <Row icon="fitness-outline" iconColor={C.green} iconBg={C.green + '15'} title="Practice Reminders" sub="Keep your streak going" testId="settings-practice-reminders-button"
                  right={<Toggle value={practiceReminders} onChange={(v: boolean) => { setPracticeReminders(v); updateNotif('practice_reminders', v); }} testId="settings-practice-reminders-switch" />} />
            <Row icon="trophy-outline" iconColor={C.warning} iconBg={`${C.warning}15`} title="Achievements" sub="Earn badges & rewards" testId="settings-achievement-alerts-button"
                  right={<Toggle value={achievementAlerts} onChange={(v: boolean) => { setAchievementAlerts(v); updateNotif('achievement_alerts', v); }} testId="settings-achievement-alerts-switch" />} />
                <Row icon="analytics-outline" iconColor={C.purpleText} iconBg={C.purple + '15'} title="Weekly Digest" sub="Progress summary & insights" testId="settings-weekly-digest-button"
                  right={<Toggle value={weeklyDigest} onChange={(v: boolean) => { setWeeklyDigest(v); updateNotif('weekly_digest', v); }} testId="settings-weekly-digest-switch" />} last />
              </Card>

              <SectionHead title="Teams & Goals" icon="people-outline" />
              <Card>
            <Row icon="people-outline" iconColor={C.primary} iconBg={`${C.primary}15`} title="Team Updates" sub="Invites, events & announcements" testId="settings-team-updates-button"
                  right={<Toggle value={teamUpdates} onChange={(v: boolean) => { setTeamUpdates(v); updateNotif('team_updates', v); }} testId="settings-team-updates-switch" />} />
                <Row icon="flag-outline" iconColor={C.blue} iconBg={C.blue + '15'} title="Goal Reminders" sub="Deadline & milestone alerts" testId="settings-goal-reminders-button"
                  right={<Toggle value={goalReminders} onChange={(v: boolean) => { setGoalReminders(v); updateNotif('goal_reminders', v); }} testId="settings-goal-reminders-switch" />} />
                <Row icon="sparkles-outline" iconColor={C.cyan} iconBg={C.cyan + '15'} title="Coaching Nudges" sub="AI-powered tips & suggestions" testId="settings-coaching-nudges-button"
                  right={<Toggle value={coachingNudges} onChange={(v: boolean) => { setCoachingNudges(v); updateNotif('coaching_nudges', v); }} testId="settings-coaching-nudges-switch" />} last />
              </Card>

              <SectionHead title="Quiet Hours" icon="moon-outline" />
              <Card>
                <Row icon="moon-outline" iconColor={C.purpleText} iconBg={C.purple + '15'} title="Quiet Hours" sub={quietHoursEnabled ? `${quietStart} - ${quietEnd}` : 'Pause push during rest'} testId="settings-quiet-hours-button"
                  right={<Toggle value={quietHoursEnabled} onChange={(v: boolean) => { setQuietHoursEnabled(v); updateNotif('quiet_hours_enabled', v); }} testId="settings-quiet-hours-switch" />} last={!quietHoursEnabled} />
                {quietHoursEnabled && (
                  <View style={{ flexDirection: 'row', justifyContent: 'space-between', paddingHorizontal: 18, paddingBottom: 18 }}>
                    {[{ label: 'Start', val: quietStart, set: setQuietStart, key: 'quiet_hours_start', opts: ['21:00','22:00','23:00'] },
                      { label: 'End', val: quietEnd, set: setQuietEnd, key: 'quiet_hours_end', opts: ['06:00','07:00','08:00'] }].map(g => (
                      <View key={g.label} style={{ flex: 1, marginHorizontal: 4 }}>
                        <Text style={{ fontSize: 11, color: C.textSec, marginBottom: 8, fontWeight: '600' }}>{g.label}</Text>
                        <View style={{ flexDirection: 'row', gap: 6 }}>
                          {g.opts.map(o => (
                            <TouchableOpacity key={o} accessibilityLabel="G in settings inner button" onPress={() => { g.set(o); updateNotif(g.key, o); }}
                              style={{
                                paddingHorizontal: 12, paddingVertical: 8, borderRadius: 10,
                                backgroundColor: g.val === o ? C.primary : C.bgSoft,
                                borderWidth: 1, borderColor: g.val === o ? C.primary : C.border,
                              }}
                              data-testid={`quiet-${g.label.toLowerCase()}-${o}`} testID={`quiet-${g.label.toLowerCase()}-${o}`}>
                      <Text style={{ fontSize: 12, color: g.val === o ? C.primaryText : C.text, fontWeight: '600' }}>{o}</Text>
                            </TouchableOpacity>
                          ))}
                        </View>
                      </View>
                    ))}
                  </View>
                )}
              </Card>
            </>
          )}

          {/* ─── APPEARANCE TAB ─── */}
          {tab === 'appearance' && (
            <>
              <SectionHead title="Theme Mode" icon="contrast-outline" />
              <Card>
                <View style={{ padding: 18 }}>
                  <View style={{ flexDirection: 'row', gap: 10 }}>
                    {[{ id: 'system', label: 'Auto', icon: 'phone-portrait-outline' },
                      { id: 'light', label: 'Light', icon: 'sunny-outline' },
                      { id: 'dark', label: 'Dark', icon: 'moon-outline' }].map(m => {
                      const active = theme.themeMode === m.id;
                      return (
                        <TouchableOpacity key={m.id} accessibilityLabel="Theme in settings inner button" onPress={() => theme.setThemeMode(m.id as any)}
                          style={{
                            flex: 1, flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 8,
                            paddingVertical: 16, borderRadius: 14,
                            backgroundColor: active ? (globalThis as any).__alphaColor(C.primary, '12') : C.bgSoft,
                            borderWidth: 2, borderColor: active ? C.primary : 'transparent',
                            ...(Platform.OS === 'web' ? { transition: 'all 0.2s ease' } as any : {}),
                          }}
                          data-testid={`settings-theme-mode-option-${m.id}`} testID={`settings-theme-mode-option-${m.id}`}>
                          <View style={{
                            width: 44, height: 44, borderRadius: 14,
                            backgroundColor: active ? (globalThis as any).__alphaColor(C.primary, '20') : C.card,
                            alignItems: 'center', justifyContent: 'center',
                          }}>
                            <Ionicons name={m.icon as any} size={20} color={active ? C.primary : C.textMuted} />
                          </View>
                          <Text style={{ fontSize: 13, fontWeight: active ? '700' : '500', color: active ? C.primary : C.textMuted }}>{m.label}</Text>
                          {active && <View style={{ width: 6, height: 6, borderRadius: 3, backgroundColor: C.primary }} />}
                        </TouchableOpacity>
                      );
                    })}
                  </View>
                </View>
              </Card>

              {/* Theme Preview Button */}
              <TouchableOpacity accessibilityLabel="Settings theme preview button"
                onPress={theme.isThemePreview ? theme.exitThemePreview : theme.toggleThemePreview}
                style={{
                  flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 10,
                  paddingVertical: 14, borderRadius: 14, marginTop: 10, marginBottom: 4,
                  backgroundColor: theme.isThemePreview ? (globalThis as any).__alphaColor(C.primary, '18') : C.card,
                  borderWidth: 1.5,
                  borderColor: theme.isThemePreview ? C.primary : C.border,
                  ...(Platform.OS === 'web' ? { transition: 'all 0.25s ease', cursor: 'pointer' } as any : {}),
                }}
                data-testid="settings-theme-preview-btn" testID="settings-theme-preview-btn"
              >
                <Ionicons
                  name={theme.isThemePreview ? 'close-circle-outline' : (theme.darkMode ? 'sunny-outline' : 'moon-outline')}
                  size={18}
                  color={theme.isThemePreview ? C.primary : C.textSec}
                />
                <Text style={{
                  fontSize: 14, fontWeight: '600',
                  color: theme.isThemePreview ? C.primary : C.text,
                }}>
                  {theme.isThemePreview
                    ? 'Exit Preview'
                    : `Preview ${theme.darkMode ? 'Light' : 'Dark'} Mode`}
                </Text>
                {theme.isThemePreview && (
                  <View style={{
                    paddingHorizontal: 8, paddingVertical: 2, borderRadius: 6,
                    backgroundColor: (globalThis as any).__alphaColor(C.primary, '20'),
                  }}>
                    <Text style={{ fontSize: 10, fontWeight: '700', color: C.primary }}>PREVIEW</Text>
                  </View>
                )}
              </TouchableOpacity>

              <SectionHead title="Brand Accent" icon="color-palette-outline" />
              <Card>
                <View style={{ padding: 18, gap: 14 }}>
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 12 }}>
                    <View style={{ width: 44, height: 44, borderRadius: 14, backgroundColor: C.primary, alignItems: 'center', justifyContent: 'center' }} data-testid="settings-brand-accent-swatch" testID="settings-brand-accent-swatch">
                      <Ionicons name="checkmark" size={18} color={C.primaryText} />
                    </View>
                    <View style={{ flex: 1 }}>
                      <Text style={{ fontSize: 14, fontWeight: '700', color: C.text }} data-testid="settings-brand-accent-title" testID="settings-brand-accent-title">RealAICoach teal is now enforced globally</Text>
                      <Text style={{ fontSize: 12, lineHeight: 18, color: C.textMuted, marginTop: 4 }} data-testid="settings-brand-accent-copy" testID="settings-brand-accent-copy">
                        Accent customization is locked so every page stays aligned with the permanent V2 enterprise design system.
                      </Text>
                    </View>
                  </View>
                  <TouchableOpacity
                    onPress={() => theme.setAccentColor(C.primary)}
                    style={{ alignSelf: 'flex-start', paddingHorizontal: 12, paddingVertical: 8, borderRadius: 10, borderWidth: 1, borderColor: C.border, backgroundColor: C.surfaceHover }}
                    data-testid="settings-brand-accent-enforce-button"
                    testID="settings-brand-accent-enforce-button"
                  >
                    <Text style={{ color: C.primary, fontSize: 12, fontWeight: '700' }}>Re-apply brand accent</Text>
                  </TouchableOpacity>
                </View>
              </Card>

              <SectionHead title="Background Brightness" icon="image-outline" />
              <Card>
                <View style={{ padding: 18 }}>
                  <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
                    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                      <Ionicons name="sunny-outline" size={16} color={C.textMuted} />
                      <Text style={{ fontSize: 13, color: C.textSec }}>Image Intensity</Text>
                    </View>
                    <View style={{ backgroundColor: (globalThis as any).__alphaColor(C.primary, '15'), paddingHorizontal: 10, paddingVertical: 4, borderRadius: 8 }}>
                      <Text style={{ fontSize: 12, fontWeight: '700', color: C.primary }} data-testid="bg-brightness-value" testID="bg-brightness-value">{brightness}%</Text>
                    </View>
                  </View>
                  {Platform.OS === 'web' ? (
                    <View style={{ position: 'relative' as any }}>
                      {/* @ts-ignore */}
                      <input aria-label="Text input"
                        type="range"
                        min={0}
                        max={100}
                        step={5}
                        value={brightness}
                        onChange={(e: any) => setBrightness(Number(e.target.value))}
                        data-testid="bg-brightness-slider"
                        style={{
                          width: '100%',
                          height: 6,
                          borderRadius: 3,
                          appearance: 'none' as any,
                          WebkitAppearance: 'none' as any,
                          background: `linear-gradient(to right, ${C.primary} ${brightness}%, ${C.border} ${brightness}%)`,
                          outline: 'none',
                          cursor: 'pointer',
                          accentColor: C.primary,
                        }}
                      />
                    </View>
                  ) : (
                    <View style={{ flexDirection: 'row', gap: 8, justifyContent: 'space-between' }}>
                      {[0, 15, 30, 50, 75, 100].map(v => (
                        <TouchableOpacity key={v} accessibilityLabel="Set brightness in settings inner button" onPress={() => setBrightness(v)}
                          style={{
                            flex: 1, paddingVertical: 10, borderRadius: 10, alignItems: 'center',
                            backgroundColor: brightness === v ? (globalThis as any).__alphaColor(C.primary, '15') : C.bgSoft,
                            borderWidth: brightness === v ? 2 : 1, borderColor: brightness === v ? C.primary : C.border,
                          }}>
                          <Text style={{ fontSize: 11, fontWeight: brightness === v ? '700' : '500', color: brightness === v ? C.primary : C.textMuted }}>{v}%</Text>
                        </TouchableOpacity>
                      ))}
                    </View>
                  )}
                  <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginTop: 8 }}>
                    <Text style={{ fontSize: 10, color: C.textMuted }}>Off</Text>
                    <Text style={{ fontSize: 10, color: C.textMuted }}>Maximum</Text>
                  </View>
                </View>
              </Card>

              <SectionHead title="Background Preset" icon="images-outline" />
              <Card>
                <View style={{ padding: 14 }}>
                  <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10 }}>
                    {PRESET_OPTIONS.map(opt => {
                      const active = preset === opt.id;
                      return (
                        <TouchableOpacity
                          key={opt.id}
                          onPress={() => setPreset(opt.id)}
                          data-testid={`preset-${opt.id}`} testID={`preset-${opt.id}`}
                          style={{
                            flex: 1, minWidth: 100,
                            paddingVertical: 14, paddingHorizontal: 12,
                            borderRadius: 12, alignItems: 'center', gap: 6,
                            backgroundColor: active ? (globalThis as any).__alphaColor(C.primary, '15') : C.bgSoft,
                            borderWidth: 2,
                            borderColor: (globalThis as any).__alphaColor(active ? C.primary : C.border, '60'),
                          }}
                        >
                          <Ionicons name={opt.icon} size={22} color={active ? C.primary : C.textMuted} />
                          <Text style={{ fontSize: 12, fontWeight: active ? '700' : '600', color: active ? C.primary : C.text }}>{opt.label}</Text>
                          <Text style={{ fontSize: 9, color: C.textMuted, textAlign: 'center' }}>{opt.desc}</Text>
                        </TouchableOpacity>
                      );
                    })}
                  </View>
                </View>
              </Card>

              <SectionHead title="Page Backgrounds" icon="layers-outline" />
              <Card>
                <View style={{ padding: 14 }}>
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 12, paddingHorizontal: 4 }}>
                    <Ionicons name="information-circle-outline" size={14} color={C.textMuted} />
                    <Text style={{ fontSize: 11, color: C.textMuted, flex: 1 }}>
                      Override the global preset for specific page groups. Set to "Global" to follow the global preset above.
                    </Text>
                  </View>
                  <View style={{ gap: 8 }}>
                    {Object.entries(PAGE_VARIANT_INFO).map(([variantKey, info]) => {
                      const override = pageOverrides[variantKey];
                      // eslint-disable-next-line @typescript-eslint/no-unused-vars
                      const _effectiveLabel = override
                        ? (PRESET_OPTIONS.find(p => p.id === override)?.label || override)
                        : 'Global';
                      const hasOverride = !!override;
                      // Resolve the preview image: override > global preset > page-specific
                      const resolvedPreset = override || preset;
                      const previewImages = (resolvedPreset !== 'default' && PRESET_COLLECTIONS[resolvedPreset])
                        ? PRESET_COLLECTIONS[resolvedPreset]
                        : (PAGE_COLLECTIONS[variantKey] || PAGE_COLLECTIONS.default);
                      const thumbSrc = previewImages[0]?.replace('w=1920', 'w=200') || '';
                      return (
                        <View
                          key={variantKey}
                          data-testid={`page-bg-row-${variantKey}`} testID={`page-bg-row-${variantKey}`}
                          style={{
                            flexDirection: 'column', gap: isMobile ? 8 : 0,
                            paddingVertical: 10, paddingHorizontal: 10,
                            backgroundColor: hasOverride ? (globalThis as any).__alphaColor(C.primary, '08') : 'transparent',
                            borderRadius: 12,
                            borderWidth: hasOverride ? 1 : 0,
                            borderColor: hasOverride ? (globalThis as any).__alphaColor(C.primary, '20') : 'transparent',
                          }}
                        >
                          {/* Top row: thumbnail + label */}
                          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
                          {Platform.OS === 'web' ? (
                            <div style={{
                              width: 52, height: 34, borderRadius: 8, overflow: 'hidden',
                              flexShrink: 0, position: 'relative' as any,
                              border: `1.5px solid ${hasOverride ? C.primary + '40' : C.border + '50'}`,
                              boxShadow: '0 1px 4px rgba(0,0,0,0.1)',
                              transition: 'border-color 0.2s ease, transform 0.2s ease',
                            }}>
                              <img
                                src={thumbSrc}
                                alt={info.label}
                                style={{
                                  width: '100%', height: '100%', objectFit: 'cover',
                                  display: 'block',
                                }}
                              />
                              <div style={{
                                position: 'absolute', bottom: 0, left: 0, right: 0,
                                height: '60%',
                                background: 'linear-gradient(to top, rgba(0,0,0,0.45), transparent)',
                                display: 'flex', alignItems: 'flex-end', justifyContent: 'center',
                                paddingBottom: 2,
                              }}>
                                <span style={{ fontSize: 10, color: colors.primaryText, filter: 'drop-shadow(0 1px 1px rgba(0,0,0,0.5))' }}>
                                  {React.createElement(Ionicons as any, { name: info.icon, size: 11, color: colors.primaryText })}
                                </span>
                              </div>
                            </div>
                          ) : (
                            <View style={{ width: 52, height: 34, borderRadius: 8, backgroundColor: hasOverride ? (globalThis as any).__alphaColor(C.primary, '18') : C.bgSoft, alignItems: 'center', justifyContent: 'center' }}>
                              <Ionicons name={info.icon as any} size={16} color={hasOverride ? C.primary : C.textMuted} />
                            </View>
                          )}
                          <View style={{ flex: 1, minWidth: 0 }}>
                            <Text style={{ fontSize: 13, fontWeight: '600', color: C.text }}>{info.label}</Text>
                            <Text style={{ fontSize: 10, color: C.textMuted, marginTop: 1 }} numberOfLines={1}>{info.pages.join(' · ')}</Text>
                          </View>
                          </View>
                          {/* Preset pills - wrap on mobile */}
                          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: isMobile ? 6 : 4, marginLeft: isMobile ? 0 : 62 }}>
                            {[
                              { id: 'global', label: 'Global', icon: 'globe-outline' },
                              ...PRESET_OPTIONS.filter(p => p.id !== 'default'),
                              { id: 'default', label: 'Own', icon: 'apps-outline' },
                            ].map(opt => {
                              const isActive = opt.id === 'global'
                                ? !hasOverride
                                : override === opt.id;
                              return (
                                <TouchableOpacity
                                  key={opt.id}
                                  onPress={() => setPageOverride(variantKey, opt.id)}
                                  data-testid={`page-bg-${variantKey}-${opt.id}`} testID={`page-bg-${variantKey}-${opt.id}`}
                                  style={{
                                    paddingHorizontal: isMobile ? 10 : 8, paddingVertical: isMobile ? 6 : 5,
                                    borderRadius: 8,
                                    backgroundColor: isActive ? (globalThis as any).__alphaColor(C.primary, '18') : C.bgSoft,
                                    borderWidth: 1.5,
                                    borderColor: (globalThis as any).__alphaColor(isActive ? C.primary : C.border, '40'),
                                    ...(Platform.OS === 'web' ? { transition: 'all 0.15s ease', cursor: 'pointer' } as any : {}),
                                  }}
                                >
                                  <Text style={{ fontSize: isMobile ? 10 : 9, fontWeight: isActive ? '700' : '500', color: isActive ? C.primary : C.textMuted }}>
                                    {opt.label}
                                  </Text>
                                </TouchableOpacity>
                              );
                            })}
                          </View>
                        </View>
                      );
                    })}
                  </View>
                  {Object.keys(pageOverrides).length > 0 && (
                    <TouchableOpacity
                      onPress={() => {
                        Object.keys(pageOverrides).forEach(k => setPageOverride(k, 'global'));
                      }}
                      data-testid="page-bg-reset-all" testID="page-bg-reset-all"
                      style={{
                        marginTop: 14, alignSelf: 'center',
                        flexDirection: 'row', alignItems: 'center', gap: 6,
                        paddingHorizontal: 14, paddingVertical: 8,
                        borderRadius: 10, backgroundColor: (globalThis as any).__alphaColor(C.red, '10'),
                        borderWidth: 1, borderColor: (globalThis as any).__alphaColor(C.red, '30'),
                      }}
                    >
                      <Ionicons name="refresh-outline" size={14} color={C.red} />
                      <Text style={{ fontSize: 12, fontWeight: '600', color: C.red }}>Reset All to Global</Text>
                    </TouchableOpacity>
                  )}
                </View>
              </Card>

              <SectionHead title={t('settings.item.language') + ' & ' + t('settings.item.fontSize')} icon="globe-outline" />
              <Card>
          <Row icon="globe-outline" iconColor={C.primary} iconBg={`${C.primary}15`} title={t('settings.item.language')} sub={theme.language} onPress={() => router.push('/language-selector')} testId="settings-language-button" />
          <Row icon="cash-outline" iconColor={C.success} iconBg={`${C.success}15`} title="Currency" sub={currentCurrency} onPress={() => router.push('/currency-selector')} testId="settings-currency-button" />
                <View style={{ padding: 16, borderTopWidth: 0 }}>
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 12 }}>
              <View style={{ width: 34, height: 34, borderRadius: 10, backgroundColor: `${C.accent}15`, alignItems: 'center', justifyContent: 'center' }}>
                <Ionicons name="text-outline" size={17} color={C.accent} />
                    </View>
                    <Text style={{ fontSize: 14, fontWeight: '600', color: C.text }}>{t('settings.item.fontSize')}</Text>
                  </View>
                  <View style={{ flexDirection: 'row', borderRadius: 12, borderWidth: 1, borderColor: C.border, overflow: 'hidden', backgroundColor: C.bgSoft }} data-testid="font-size-picker" testID="font-size-picker">
                    {(['Small', 'Medium', 'Large'] as const).map((size) => {
                      const active = theme.fontSize === size;
                      const labels: Record<string, string> = { Small: 'A', Medium: 'A', Large: 'A' };
                      const fontSizes: Record<string, number> = { Small: 12, Medium: 15, Large: 18 };
                      return (
                        <TouchableOpacity key={size} onPress={() => theme.setFontSize(size)}
                          data-testid={`font-size-${size.toLowerCase()}`} testID={`font-size-${size.toLowerCase()}`}
                          style={{
                            flex: 1, paddingVertical: 12, alignItems: 'center', justifyContent: 'center',
                            backgroundColor: active ? C.primary : 'transparent',
                            ...(Platform.OS === 'web' ? { transition: 'all 0.2s ease' } as any : {}),
                          }}>
                      <Text style={{ fontSize: fontSizes[size], fontWeight: active ? '800' : '600', color: active ? C.primaryText : C.textSec }}>{labels[size]}</Text>
                      <Text style={{ fontSize: 10, fontWeight: '500', color: active ? C.primaryText : C.textMuted, marginTop: 2 }}>{size}</Text>
                        </TouchableOpacity>
                      );
                    })}
                  </View>
                </View>
              </Card>

              <SectionHead title="Preview Mode" icon="eye-outline" />
              <Card>
                <Row icon="eye-outline" title="Preview Changes" sub="See changes before saving" testId="settings-preview-toggle"
                  right={<Toggle value={theme.previewEnabled} onChange={() => { const next = !theme.previewEnabled; if (!next) theme.cancelPreviewChanges(); theme.setPreviewEnabled(next); }} />} last={!theme.previewEnabled} />
                {theme.previewEnabled && (
                  <View style={{ flexDirection: 'row', padding: 16, gap: 12 }}>
                    <TouchableOpacity onPress={theme.cancelPreviewChanges} style={{ flex: 1, paddingVertical: 12, borderRadius: 12, alignItems: 'center', borderWidth: 1, borderColor: C.border }} data-testid="settings-preview-cancel" testID="settings-preview-cancel">
                      <Text style={{ fontSize: 13, fontWeight: '600', color: C.text }}>Cancel</Text>
                    </TouchableOpacity>
                    <TouchableOpacity onPress={theme.savePreviewChanges} disabled={!theme.hasPendingPreviewChanges}
                      style={{ flex: 1, paddingVertical: 12, borderRadius: 12, alignItems: 'center', backgroundColor: C.primary, opacity: theme.hasPendingPreviewChanges ? 1 : 0.5 }} data-testid="settings-preview-save" testID="settings-preview-save">
                      <Text style={{ fontSize: 13, fontWeight: '600', color: colors.primaryText }}>Save</Text>
                    </TouchableOpacity>
                  </View>
                )}
              </Card>
            </>
          )}

          {/* ─── ACCESSIBILITY TAB ─── */}
          {tab === 'accessibility' && (
            <>
              <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                <Ionicons name="accessibility" size={18} color={C.warning} />
                  <Text style={{ fontSize: 15, fontWeight: '800', color: C.text }}>Accessibility</Text>
                {activeCount > 0 && <View style={{ backgroundColor: C.warning, paddingHorizontal: 8, paddingVertical: 3, borderRadius: 8 }}>
                    <Text style={{ fontSize: 10, fontWeight: '700', color: colors.primaryText }}>{activeCount} active</Text>
                  </View>}
                </View>
                {activeCount > 0 && (
                  <TouchableOpacity onPress={resetAll} style={{ flexDirection: 'row', alignItems: 'center', gap: 4, paddingHorizontal: 12, paddingVertical: 7, borderRadius: 10, borderWidth: 1, borderColor: C.border }} data-testid="a11y-reset-all" testID="a11y-reset-all">
                    <Ionicons name="refresh" size={12} color={C.textSec} />
                    <Text style={{ fontSize: 11, fontWeight: '600', color: C.textSec }}>Reset All</Text>
                  </TouchableOpacity>
                )}
              </View>

              <SectionHead title="Quick Presets" icon="flash-outline" />
              <View style={{ gap: 10, marginBottom: 20 }}>
                {A11Y_PRESETS.map(p => {
                  const active = isPresetActive(prefs, p.settings);
                  return (
                    <TouchableOpacity key={p.id} onPress={() => active ? resetAll() : applyPreset(p.settings)} data-testid={`a11y-preset-${p.id}`} testID={`a11y-preset-${p.id}`}
                      style={{
                        flexDirection: 'row', alignItems: 'center', gap: 14, padding: 16,
                        borderRadius: 16, borderWidth: 1,
                    backgroundColor: active ? `${C.warning}10` : C.card,
                    borderColor: active ? C.warning : C.border,
                      }}>
                      <View style={{ width: 44, height: 44, borderRadius: 12, backgroundColor: (globalThis as any).__alphaColor(p.color, '18'), alignItems: 'center', justifyContent: 'center' }}>
                        <Ionicons name={p.icon as any} size={20} color={p.color} />
                      </View>
                      <View style={{ flex: 1 }}>
                    <Text style={{ fontSize: 14, fontWeight: '700', color: active ? C.warning : C.text }}>{p.name}</Text>
                        <Text style={{ fontSize: 11, color: C.textMuted, marginTop: 3 }}>{p.desc}</Text>
                      </View>
                    {active && <View style={{ width: 24, height: 24, borderRadius: 12, backgroundColor: C.warning, alignItems: 'center', justifyContent: 'center' }}>
                      <Ionicons name="checkmark" size={13} color={C.primaryText} />
                      </View>}
                    </TouchableOpacity>
                  );
                })}
              </View>

              {A11Y_ITEMS.map(section => (
                <View key={section.section}>
                  <SectionHead title={section.section} icon={section.icon as any} />
                  <Card>
                    {section.items.map((item, idx) => {
                      const val = prefs[item.key as keyof AccessibilityPreferences];
                      const last = idx === section.items.length - 1;
                      if (item.type === 'toggle') {
                        return <Row key={item.key} icon="toggle-outline" title={item.label} sub={item.desc} testId={`a11y-toggle-${item.key}`} last={last}
                          right={<Toggle value={val === true} onChange={(v: boolean) => updatePref(item.key as any, v)} />} />;
                      }
                      if (item.type === 'segmented') {
                        return (
                          <View key={item.key} style={{ padding: 16, borderBottomWidth: last ? 0 : 1, borderBottomColor: (globalThis as any).__alphaColor(C.border, '60') }}>
                            <Text style={{ fontSize: 13, fontWeight: '600', color: C.text, marginBottom: 12 }}>{item.label}</Text>
                            <View style={{ flexDirection: 'row', borderRadius: 12, borderWidth: 1, borderColor: C.border, overflow: 'hidden', backgroundColor: C.bgSoft }}>
                              {(item.options || []).map((opt: string, i: number) => (
                                <TouchableOpacity key={opt} onPress={() => updatePref(item.key as any, opt)} data-testid={`a11y-textsize-${opt}`} testID={`a11y-textsize-${opt}`}
                        style={{ flex: 1, paddingVertical: 12, alignItems: 'center', backgroundColor: val === opt ? C.warning : 'transparent' }}>
                        <Text style={{ fontSize: 13, fontWeight: val === opt ? '800' : '600', color: val === opt ? C.primaryText : C.textSec }}>{(item.labels || [])[i] || opt}</Text>
                                </TouchableOpacity>
                              ))}
                            </View>
                          </View>
                        );
                      }
                      if (item.type === 'select') {
                        return (
                          <View key={item.key} style={{ padding: 16, borderBottomWidth: last ? 0 : 1, borderBottomColor: (globalThis as any).__alphaColor(C.border, '60') }}>
                            <Text style={{ fontSize: 13, fontWeight: '600', color: C.text, marginBottom: 12 }}>{item.label}</Text>
                            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
                              {(item.options || []).map((opt: string, i: number) => (
                                <TouchableOpacity key={opt} onPress={() => updatePref(item.key as any, opt)} data-testid={`a11y-${item.key}-${opt}`} testID={`a11y-${item.key}-${opt}`}
                      style={{ paddingHorizontal: 14, paddingVertical: 8, borderRadius: 10, borderWidth: 1, borderColor: val === opt ? C.warning : C.border, backgroundColor: val === opt ? `${C.warning}10` : 'transparent' }}>
                      <Text style={{ fontSize: 12, fontWeight: '600', color: val === opt ? C.warning : C.textSec }}>{(item.labels || [])[i] || opt}</Text>
                                </TouchableOpacity>
                              ))}
                            </View>
                          </View>
                        );
                      }
                      return null;
                    })}
                  </Card>
                </View>
              ))}
            </>
          )}

          {/* ─── ABOUT TAB ─── */}
          {tab === 'about' && (
            <>
              <SectionHead title="Support" icon="help-circle-outline" />
              <Card>
                <Row icon="help-circle-outline" iconColor={C.green} iconBg={C.green + '15'} title="Help Center" sub="FAQs, guides & tutorials" onPress={() => router.push('/help')} testId="settings-help-center-button" />
          <Row icon="chatbox-ellipses-outline" iconColor={C.info} iconBg={`${C.info}15`} title="Send Feedback" sub="Ideas, bugs or suggestions" onPress={() => router.push('/feedback')} testId="settings-feedback-button" />
                <Row icon="scan-outline" iconColor={C.primary} iconBg={C.primary + '15'} title="Scan History" sub="Previous AI scans" onPress={() => router.push('/scan-history')} testId="settings-scan-history-button" />
                <Row icon="library-outline" iconColor={C.green} iconBg={C.green + '15'} title="Content Library" sub="Insights, filters & bookmarks" onPress={() => router.push('/content-library')} testId="settings-content-library-button" last />
              </Card>

              <SectionHead title="Legal" icon="document-text-outline" />
              <Card>
          <Row icon="document-text-outline" iconColor={C.primary} iconBg={`${C.primary}15`} title="Terms of Service" onPress={() => router.push('/terms')} testId="settings-terms-button" />
                <Row icon="lock-closed-outline" iconColor={C.green} iconBg={C.green + '15'} title="Privacy Policy" onPress={() => router.push('/privacy-policy')} testId="settings-privacy-button" last />
              </Card>

              <Card>
                <View style={{ alignItems: 'center', paddingVertical: 32 }}>
                  <View style={{
                    width: 56, height: 56, borderRadius: 18, backgroundColor: (globalThis as any).__alphaColor(C.primary, '12'),
                    alignItems: 'center', justifyContent: 'center', marginBottom: 14,
                  }}>
                    <Ionicons name="sparkles" size={26} color={C.primary} />
                  </View>
                  <Text style={{ fontSize: 20, fontWeight: '800', color: C.text, letterSpacing: -0.3 }}>RealAICoach</Text>
                  <Text style={{ fontSize: 13, color: C.textMuted, marginTop: 6 }}>Your AI-powered career companion</Text>
                  <View style={{ flexDirection: 'row', alignItems: 'center', marginTop: 14, gap: 8, paddingHorizontal: 14, paddingVertical: 6, borderRadius: 20, backgroundColor: C.bgSoft, borderWidth: 1, borderColor: C.border }}>
                    <Text style={{ fontSize: 13, fontWeight: '700', color: C.text }}>v3.3.0</Text>
                    <View style={{ width: 6, height: 6, borderRadius: 3, backgroundColor: C.green }} />
                    <Text style={{ fontSize: 10, fontWeight: '600', color: C.textSec, textTransform: 'uppercase', letterSpacing: 0.5 }}>Production</Text>
                  </View>
                  <Text style={{ fontSize: 10, color: C.textMuted, marginTop: 14 }}>2026-2030 RealAICoach LLC. All rights reserved.</Text>
                </View>
              </Card>
            </>
          )}
        </ScrollView>
      </View>
    </AppShell>
  );
}
