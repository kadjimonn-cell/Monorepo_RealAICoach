import React, { useEffect, useMemo, useState, useCallback } from 'react';
import { View, Text, ScrollView, TouchableOpacity, RefreshControl, Alert, Platform, useWindowDimensions, Image } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { useAuth } from '../../src/context/AuthContext';
import { useTheme } from '../../src/context/ThemeContext';
import { useRealtimeEvent } from '../../src/context/RealtimeContext';
import { useTranslation } from '../../src/hooks/useTranslation';
import AppShell from '../../src/components/AppShell';
import { useAppStore } from '../../src/store/appStore';
import { getProgress, getUserConversations } from '../../src/services/api';
import { ProfileFormSkeleton, FadeSlideIn, usePageReady } from '../../src/components/SkeletonLoaders';
import { ProtectedRouteGate } from '../../src/components/auth/ProtectedRouteGate';
import { handleAppRecoverableError } from '../../src/utils/appRecoverableError';

type ThemeMode = 'system' | 'light' | 'dark';

function ThemePreviewCard({
  mode,
  active,
  colors,
  onPress,
  isMobile,
  label,
  subtitle,
}: {
  mode: ThemeMode;
  active: boolean;
  colors: any;
  onPress: () => void;
  isMobile: boolean;
  label: string;
  subtitle: string;
}) {
  const cardBg = Platform.OS === 'web'
    ? (globalThis as any).__alphaColor(colors.card, 'B2')
    : colors.card;
  const icon = mode === 'light' ? 'sunny' : mode === 'dark' ? 'moon' : 'desktop-outline';
  return (
    <TouchableOpacity
      onPress={onPress}
      activeOpacity={0.7}
      data-testid={`theme-card-${mode}`}
      testID={`theme-card-${mode}`}
      style={{
        flex: 1,
        minWidth: isMobile ? '100%' as any : 170,
        borderRadius: 10,
        borderWidth: active ? 2 : 1,
        borderColor: active ? colors.primary : colors.border,
        backgroundColor: cardBg,
        padding: 12,
        ...(Platform.OS === 'web' ? { backdropFilter: 'blur(12px)', WebkitBackdropFilter: 'blur(12px)' } as any : {}),
      }}
    >
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
        <View style={{ width: 34, height: 34, borderRadius: 8, backgroundColor: active ? (globalThis as any).__alphaColor(colors.primary, '15') : colors.bgSoft, alignItems: 'center', justifyContent: 'center' }}>
          <Ionicons name={icon as any} size={16} color={active ? colors.primary : colors.textMuted} />
        </View>
        <View style={{ flex: 1 }}>
          <Text style={{ fontSize: 13, fontWeight: '700', color: colors.text }}>{label}</Text>
          <Text style={{ fontSize: 11, color: colors.textMuted }}>{subtitle}</Text>
        </View>
        {active ? <Ionicons name="checkmark-circle" size={18} color={colors.primary} /> : null}
      </View>
    </TouchableOpacity>
  );
}

export default function ProfileScreen() {
  const { t } = useTranslation();
  t('i18n.route.(tabs).profile.probe');
  const router = useRouter();
  const { user, logout, loading: authLoading } = useAuth();
  const { userId, hasHydrated } = useAppStore();
  const { themeMode, setThemeMode, colors } = useTheme();
  const [progress, setProgress] = useState<any>(null);
  const [recentSessions, setRecentSessions] = useState<any[]>([]);
  const [refreshing, setRefreshing] = useState(false);
  const [dataLoaded, setDataLoaded] = useState(false);
  const [profileDataError, setProfileDataError] = useState('');
  const pageReady = usePageReady(dataLoaded);
  const { width } = useWindowDimensions();
  const isMobile = width < 768;
  const isTablet = width >= 768 && width < 1160;

  const C = useMemo(() => ({
    ...colors,
    primary: colors.primary,
    bg: colors.bg,
    bgSoft: colors.bgSoft,
    card: colors.card,
    text: colors.text,
    textMuted: colors.textMuted,
    border: colors.border,
    green: colors.success,
    red: colors.error,
    yellow: colors.warning,
    blue: colors.primary,
    cyan: colors.info,
    pink: colors.accent,
    orangeText: colors.orangeText,
  }), [colors]);

  const tt = useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);

  const loadData = useCallback(async () => {
    const uid = user?.user_id || userId;
    if (!uid) {
      setDataLoaded(true);
      setRefreshing(false);
      return;
    }
    try {
      setProfileDataError('');
      const [pd, cd] = await Promise.all([getProgress(uid), getUserConversations(uid)]);
      setProgress(pd);
      setRecentSessions(cd.conversations?.slice(0, 4) || []);
    } catch (error) {
      handleAppRecoverableError({
        scope: 'profile.load-data',
        error,
        message: tt('profile.errors.loadFailed', 'Could not load your latest profile stats.'),
        setError: setProfileDataError,
        onRetry: () => { void loadData(); },
      
        notifyMode: 'dialog',
        userInitiated: true,
      });
      setProgress(null);
      setRecentSessions([]);
    }
    setDataLoaded(true);
    setRefreshing(false);
  }, [user?.user_id, userId]);

  useEffect(() => {
    if (!hasHydrated) return;
    void loadData();
  }, [hasHydrated, loadData]);
  useRealtimeEvent('sessions', loadData);
  useRealtimeEvent('goals', loadData);

  useEffect(() => {
    const timer = setInterval(() => { void loadData(); }, 30000);
    return () => clearInterval(timer);
  }, [loadData]);

  const score = useMemo(() => {
    if (!progress?.skills) return 50;
    const values = Object.values(progress.skills) as number[];
    return values.length ? Math.round(values.reduce((a, b) => a + b, 0) / values.length) : 50;
  }, [progress]);

  const level = useMemo(() => {
    if (score >= 90) return { name: tt('profile.level.master', 'Master'), color: C.primary, icon: 'diamond' };
    if (score >= 75) return { name: tt('profile.level.expert', 'Expert'), color: C.green, icon: 'star' };
    if (score >= 60) return { name: tt('profile.level.skilled', 'Skilled'), color: C.yellow, icon: 'flash' };
    return { name: tt('profile.level.beginner', 'Beginner'), color: C.textMuted, icon: 'leaf' };
  }, [score, C, tt]);

  const plan = (user?.subscription_plan || 'free').toLowerCase();
  const planColors: Record<string, string> = { free: C.textMuted, basic: C.yellow, premium: C.primary, pro: C.green };
  const planColor = planColors[plan] || C.textMuted;
  const totalSessions = progress?.total_sessions || recentSessions.length || 0;
  const streak = progress?.streak_days || 0;

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

  const handleLogout = () => {
    if (typeof window !== 'undefined') {
      void performLogout();
      return;
    }
    Alert.alert(tt('profile.logout', 'Sign Out'), tt('profile.logout.confirm', 'Are you sure?'), [
      { text: tt('common.cancel', 'Cancel'), style: 'cancel' },
      { text: tt('profile.logout', 'Sign Out'), style: 'destructive', onPress: () => { void performLogout(); } },
    ]);
  };

  if (!hasHydrated || !pageReady) return <AppShell><ProfileFormSkeleton /></AppShell>;

  const menuItems = [
    { icon: 'create-outline', iconColor: C.blue, title: tt('profile.menu.editProfile', 'Edit Profile'), sub: tt('profile.menu.editProfile.subtitle', 'Update your info'), route: '/edit-profile', testId: 'profile-menu-edit-profile' },
    { icon: 'diamond-outline', iconColor: planColor, title: tt('profile.menu.subscription.title', 'Subscription'), sub: `${tt('profile.menu.subscription.currentPrefix', 'Current plan:')} ${plan}`, route: '/subscription/plans', testId: 'profile-menu-subscription' },
    { icon: 'receipt-outline', iconColor: C.cyan, title: tt('profile.menu.paymentHistory.title', 'Payment History'), sub: tt('profile.menu.paymentHistory.subtitle', 'Transactions & receipts'), route: '/payment-history', testId: 'profile-menu-payment-history' },
    { icon: 'notifications-outline', iconColor: C.pink, title: tt('profile.menu.notification.title', 'Notification Preferences'), sub: tt('profile.menu.notification.subtitle', 'Manage alerts & emails'), route: '/settings', testId: 'profile-menu-notification-prefs' },
    { icon: 'time-outline', iconColor: C.orangeText, title: tt('profile.menu.sessionHistory.title', 'Session History'), sub: tt('profile.menu.sessionHistory.subtitle', 'View your practice sessions'), route: '/session-history', testId: 'profile-menu-session-history' },
    { icon: 'help-circle-outline', iconColor: C.green, title: tt('profile.menu.helpSupport.title', 'Help & Support'), sub: tt('profile.menu.helpSupport.subtitle', 'FAQs and guides'), route: '/help', testId: 'profile-menu-help-support' },
  ];

  return (
    <ProtectedRouteGate isLoading={authLoading} isAllowed={Boolean(user?.user_id)} returnTo="/profile">
      <AppShell>
        <FadeSlideIn>
          <View style={{ flex: 1, backgroundColor: 'transparent' }} data-testid="profile-screen" testID="profile-screen">
            <ScrollView showsVerticalScrollIndicator={false} refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); void loadData(); }} tintColor={C.primary} />} contentContainerStyle={{ paddingBottom: 36 }}>
            {profileDataError ? (
              <View
                style={{
                  marginHorizontal: isMobile ? 16 : 24,
                  marginTop: 12,
                  paddingHorizontal: 12,
                  paddingVertical: 10,
                  borderRadius: 10,
                  borderWidth: 1,
                  borderColor: C.error + '35',
                  backgroundColor: C.bgSoft,
                  flexDirection: 'row',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  gap: 10,
                }}
                data-testid="profile-recoverable-error-banner"
                testID="profile-recoverable-error-banner"
              >
                <Text
                  style={{ color: C.red, fontSize: 12, fontWeight: '700', flex: 1 }}
                  data-testid="profile-recoverable-error-text"
                  testID="profile-recoverable-error-text"
                >
                  {profileDataError}
                </Text>
                <TouchableOpacity
                  onPress={() => { void loadData(); }}
                  style={{ paddingHorizontal: 10, paddingVertical: 7, borderRadius: 8, backgroundColor: C.red }}
                  data-testid="profile-recoverable-error-retry"
                  testID="profile-recoverable-error-retry"
                >
                  <Text style={{ color: C.primaryText, fontSize: 11, fontWeight: '800' }}>{tt('common.retry', 'Retry')}</Text>
                </TouchableOpacity>
              </View>
            ) : null}
            <View style={{ backgroundColor: Platform.OS === 'web' ? (globalThis as any).__alphaColor(C.card, 'B0') : C.card, borderBottomWidth: 1, borderBottomColor: C.border, paddingHorizontal: isMobile ? 16 : 24, paddingTop: 16, paddingBottom: 20, ...(Platform.OS === 'web' ? { backdropFilter: 'blur(12px)', WebkitBackdropFilter: 'blur(12px)' } as any : {}) }} data-testid="profile-hero-section" testID="profile-hero-section">
              <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
                <Text style={{ fontSize: isMobile ? 34 : 40, fontWeight: '900', color: C.text, letterSpacing: -1 }} data-testid="profile-header-title" testID="profile-header-title">{tt('profile.title', 'Profile')}</Text>
                <TouchableOpacity onPress={() => router.push('/settings')} data-testid="profile-settings-btn" testID="profile-settings-btn" style={{ width: 42, height: 42, borderRadius: 8, backgroundColor: C.bgSoft, borderWidth: 1, borderColor: C.border, alignItems: 'center', justifyContent: 'center' }}>
                  <Ionicons name="settings-outline" size={18} color={C.textMuted} />
                </TouchableOpacity>
              </View>

              {user ? (
                <View style={{ flexDirection: isMobile ? 'column' : 'row', alignItems: isMobile ? 'flex-start' : 'center', gap: 14 }}>
                  <TouchableOpacity onPress={() => router.push('/edit-profile')} data-testid="profile-avatar" testID="profile-avatar">
                    <View style={{ width: 84, height: 84, borderRadius: 10, backgroundColor: (globalThis as any).__alphaColor(C.primary, '12'), borderWidth: 1, borderColor: C.border, overflow: 'hidden' as const, alignItems: 'center', justifyContent: 'center' }}>
                      {(user as any).profile_image ? (
                        Platform.OS === 'web'
                          ? <img src={(user as any).profile_image} style={{ width: 84, height: 84, objectFit: 'cover' } as any} alt="" />
                          : <Image source={{ uri: (user as any).profile_image }} style={{ width: 84, height: 84 }} />
                      ) : (
                        <Text style={{ fontSize: 30, fontWeight: '900', color: C.primary }}>{(user.name || 'U').charAt(0).toUpperCase()}</Text>
                      )}
                    </View>
                  </TouchableOpacity>

                  <View style={{ flex: 1 }}>
                    <Text style={{ fontSize: isMobile ? 24 : 30, fontWeight: '900', color: C.text }} data-testid="profile-user-name" testID="profile-user-name">{user.name || tt('profile.userFallback', 'User')}</Text>
                    <Text style={{ fontSize: 13, color: C.textMuted, marginTop: 2 }} data-testid="profile-user-email" testID="profile-user-email">{user.email}</Text>
                    <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 10 }}>
                      <View style={{ paddingHorizontal: 10, paddingVertical: 6, borderRadius: 8, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(planColor, '40'), backgroundColor: (globalThis as any).__alphaColor(planColor, '12'), flexDirection: 'row', alignItems: 'center', gap: 6 }} data-testid="profile-plan-badge" testID="profile-plan-badge">
                        <Ionicons name="diamond" size={11} color={planColor} />
                        <Text style={{ fontSize: 11, fontWeight: '700', color: planColor, textTransform: 'capitalize' }}>{plan}</Text>
                      </View>
                      <View style={{ paddingHorizontal: 10, paddingVertical: 6, borderRadius: 8, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(level.color, '40'), backgroundColor: (globalThis as any).__alphaColor(level.color, '12'), flexDirection: 'row', alignItems: 'center', gap: 6 }} data-testid="profile-level-badge" testID="profile-level-badge">
                        <Ionicons name={level.icon as any} size={11} color={level.color} />
                        <Text style={{ fontSize: 11, fontWeight: '700', color: level.color }}>{level.name}</Text>
                      </View>
                    </View>
                  </View>
                </View>
              ) : null}
            </View>

            {user ? (
              <View style={{ maxWidth: 1240, width: '100%', alignSelf: 'center', paddingHorizontal: isMobile ? 12 : 20, paddingTop: 16 }}>
                <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10, marginBottom: 14 }} data-testid="account-health-kpis" testID="account-health-kpis">
                  {[{ key: 'score', label: tt('profile.stats.score', 'Your Score'), value: `${score}/100`, icon: 'pulse', color: C.primary }, { key: 'sessions', label: tt('profile.stats.sessions', 'Sessions'), value: String(totalSessions), icon: 'play-circle-outline', color: C.cyan }, { key: 'streak', label: tt('profile.stats.streak', 'Streak'), value: String(streak), icon: 'flame-outline', color: C.orangeText }, { key: 'plan', label: tt('profile.stats.plan', 'Plan'), value: plan, icon: 'diamond-outline', color: planColor }].map((kpi) => (
                    <View key={kpi.key} style={{ flex: 1, minWidth: isMobile ? 150 : 220, borderWidth: 1, borderColor: C.border, backgroundColor: Platform.OS === 'web' ? (globalThis as any).__alphaColor(C.card, 'AE') : C.card, borderRadius: 10, padding: 14, ...(Platform.OS === 'web' ? { backdropFilter: 'blur(12px)', WebkitBackdropFilter: 'blur(12px)' } as any : {}) }} data-testid={`profile-kpi-${kpi.key}`} testID={`profile-kpi-${kpi.key}`}>
                      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
                        <Text style={{ fontSize: 10, color: C.textMuted, fontWeight: '800', letterSpacing: 1, textTransform: 'uppercase' }}>{kpi.label}</Text>
                        <Ionicons name={kpi.icon as any} size={14} color={kpi.color} />
                      </View>
                      <Text style={{ fontSize: 27, fontWeight: '900', color: C.text, marginTop: 8, textTransform: kpi.key === 'plan' ? 'capitalize' : 'none' }}>{kpi.value}</Text>
                    </View>
                  ))}
                </View>

                <View style={{ flexDirection: isMobile || isTablet ? 'column' : 'row', gap: 14 }}>
                  <View style={{ flex: 1.3, gap: 14 }}>
                    <View style={{ borderWidth: 1, borderColor: C.border, borderRadius: 10, backgroundColor: Platform.OS === 'web' ? (globalThis as any).__alphaColor(C.card, 'AE') : C.card, padding: 14, ...(Platform.OS === 'web' ? { backdropFilter: 'blur(12px)', WebkitBackdropFilter: 'blur(12px)' } as any : {}) }} data-testid="theme-selector-toggle" testID="theme-selector-toggle">
                      <Text style={{ fontSize: 11, fontWeight: '800', letterSpacing: 1.2, textTransform: 'uppercase', color: C.textMuted, marginBottom: 10 }}>{tt('profile.appearance.title', 'Appearance')}</Text>
                      <View style={{ flexDirection: isMobile ? 'column' : 'row', gap: 10 }}>
                        <ThemePreviewCard mode="light" active={themeMode === 'light'} colors={colors} onPress={() => setThemeMode('light')} isMobile={isMobile} label={tt('profile.theme.light', 'Light')} subtitle={tt('profile.theme.lightSub', 'Always bright')} />
                        <ThemePreviewCard mode="dark" active={themeMode === 'dark'} colors={colors} onPress={() => setThemeMode('dark')} isMobile={isMobile} label={tt('profile.theme.dark', 'Dark')} subtitle={tt('profile.theme.darkSub', 'Always dark')} />
                        <ThemePreviewCard mode="system" active={themeMode === 'system'} colors={colors} onPress={() => setThemeMode('system')} isMobile={isMobile} label={tt('profile.theme.system', 'Auto')} subtitle={tt('profile.theme.systemSub', 'Follow device')} />
                      </View>
                    </View>

                    <View style={{ borderWidth: 1, borderColor: C.border, borderRadius: 10, backgroundColor: Platform.OS === 'web' ? (globalThis as any).__alphaColor(C.card, 'AE') : C.card, padding: 14, ...(Platform.OS === 'web' ? { backdropFilter: 'blur(12px)', WebkitBackdropFilter: 'blur(12px)' } as any : {}) }} data-testid="recent-sessions-list" testID="recent-sessions-list">
                      <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
                        <Text style={{ fontSize: 11, fontWeight: '800', letterSpacing: 1.2, textTransform: 'uppercase', color: C.textMuted }}>{tt('profile.menu.sessionHistory.title', 'Session History')}</Text>
                        <TouchableOpacity onPress={() => router.push('/session-history')} data-testid="profile-view-all-sessions" testID="profile-view-all-sessions">
                          <Text style={{ fontSize: 12, fontWeight: '700', color: C.primary }}>{tt('common.viewAll', 'View All')}</Text>
                        </TouchableOpacity>
                      </View>
                      {recentSessions.length === 0 ? (
                        <Text style={{ fontSize: 12, color: C.textMuted }}>{tt('profile.sessions.empty', 'No recent sessions yet.')}</Text>
                      ) : (
                        recentSessions.map((session, index) => (
                          <View key={session.conversation_id || index} style={{ flexDirection: 'row', alignItems: 'center', gap: 10, paddingVertical: 10, borderBottomWidth: index < recentSessions.length - 1 ? 1 : 0, borderBottomColor: C.border }}>
                            <View style={{ width: 34, height: 34, borderRadius: 8, backgroundColor: (globalThis as any).__alphaColor(C.primary, '12'), alignItems: 'center', justifyContent: 'center' }}>
                              <Ionicons name="chatbubble-outline" size={14} color={C.primary} />
                            </View>
                            <View style={{ flex: 1 }}>
                              <Text style={{ fontSize: 13, fontWeight: '700', color: C.text }} numberOfLines={1}>{session.scenario || session.title || tt('profile.session.defaultName', 'Coaching Session')}</Text>
                              <Text style={{ fontSize: 11, color: C.textMuted }}>{session.created_at ? new Date(session.created_at).toLocaleDateString() : ''}{session.score ? ` • ${tt('profile.stats.score', 'Your Score')}: ${session.score}%` : ''}</Text>
                            </View>
                          </View>
                        ))
                      )}
                    </View>
                  </View>

                  <View style={{ flex: 1, gap: 14 }}>
                    <View style={{ borderWidth: 1, borderColor: C.border, borderRadius: 10, backgroundColor: Platform.OS === 'web' ? (globalThis as any).__alphaColor(C.card, 'AE') : C.card, overflow: 'hidden', ...(Platform.OS === 'web' ? { backdropFilter: 'blur(12px)', WebkitBackdropFilter: 'blur(12px)' } as any : {}) }} data-testid="profile-menu-actions" testID="profile-menu-actions">
                      {menuItems.map((item, idx) => (
                        <TouchableOpacity key={item.testId} onPress={() => router.push(item.route)} data-testid={item.testId} testID={item.testId} style={{ flexDirection: 'row', alignItems: 'center', gap: 12, paddingHorizontal: 14, paddingVertical: 13, borderBottomWidth: idx < menuItems.length - 1 ? 1 : 0, borderBottomColor: C.border }}>
                          <View style={{ width: 34, height: 34, borderRadius: 8, backgroundColor: (globalThis as any).__alphaColor(item.iconColor, '12'), alignItems: 'center', justifyContent: 'center' }}>
                            <Ionicons name={item.icon as any} size={15} color={item.iconColor} />
                          </View>
                          <View style={{ flex: 1 }}>
                            <Text style={{ fontSize: 13, fontWeight: '700', color: C.text }}>{item.title}</Text>
                            <Text style={{ fontSize: 11, color: C.textMuted, marginTop: 2 }}>{item.sub}</Text>
                          </View>
                          <Ionicons name="chevron-forward" size={14} color={C.textMuted} />
                        </TouchableOpacity>
                      ))}
                    </View>

                    <TouchableOpacity onPress={handleLogout} data-testid="profile-logout-button" testID="profile-logout-button" style={{ minHeight: 50, borderRadius: 10, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(C.red, '35'), backgroundColor: (globalThis as any).__alphaColor(C.red, '10'), flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8 }}>
                      <Ionicons name="log-out-outline" size={17} color={C.red} />
                      <Text style={{ fontSize: 14, fontWeight: '800', color: C.red }}>{tt('profile.logout', 'Sign Out')}</Text>
                    </TouchableOpacity>
                  </View>
                </View>
              </View>
            ) : null}
            </ScrollView>
          </View>
        </FadeSlideIn>
      </AppShell>
    </ProtectedRouteGate>
  );
}
