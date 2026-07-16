import React, { useState, useMemo, useEffect, Suspense, lazy } from 'react';
import {
  View, Text, StyleSheet, TouchableOpacity, useWindowDimensions, ScrollView, ActivityIndicator,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useRouter, usePathname } from 'expo-router';
import { useTheme } from '../context/ThemeContext';
import { useTranslation } from '../hooks/useTranslation';
import FeatureActionsBar from './FeatureActionsBar';
import { getRecentFeatures, setRecentFeatures } from '../utils/recentFeatures';
import AITransparencyBanner from './AITransparencyBanner';
import UpgradeBanner from './UpgradeBanner';
import PremiumGuard from './PremiumGuard';
import { useNavigationStore } from '../store/useNavigationStore';
import { clientLogger } from '../utils/clientLogger';

// Lazy-load heavy tab components (only loaded when user switches to chat/scan tab)
const AIChatPanel = lazy(() => import('./AIChatPanel'));
const AIScanner = lazy(() => import('./AIScanner'));

interface FeatureLayoutProps {
  feature: string;
  title: string;
  subtitle?: string;
  color: string;
  icon: string;
  children: React.ReactNode;
  showActions?: boolean;
  noPadding?: boolean;
  requiredPlan?: 'basic' | 'premium';
  showTransparencyBanner?: boolean;
  scanTabLabel?: string;
  chatTabLabel?: string;
  scanTabIcon?: string;
  chatTabIcon?: string;
  scanContent?: React.ReactNode;
  chatContent?: React.ReactNode;
  extraTabLabel?: string;
  extraTabIcon?: string;
  extraContent?: React.ReactNode;
  showSecondaryTabs?: boolean;
  selfScrolling?: boolean;
}

const RECENT_FEATURES_LIMIT = 8;

export default function FeatureLayout({
  feature,
  title,
  subtitle,
  color,
  icon,
  children,
  showActions = true,
  noPadding = false,
  requiredPlan,
  showTransparencyBanner = true,
  scanTabLabel,
  chatTabLabel,
  scanTabIcon,
  chatTabIcon,
  scanContent,
  chatContent,
  extraTabLabel,
  extraTabIcon,
  extraContent,
  showSecondaryTabs = true,
  selfScrolling = false,
}: FeatureLayoutProps) {
  const router = useRouter();
  const pathname = usePathname();
  const { width: sw } = useWindowDimensions();
  const { colors, darkMode, setThemeMode } = useTheme();
  const { t } = useTranslation();

  const { canGoForward, goForward } = useNavigationStore();

  const recentFeatureId = useMemo(() => {
    if (!pathname) return feature;
    const parts = pathname.split('/').filter(Boolean);
    const featuresIndex = parts.indexOf('features');
    if (featuresIndex >= 0 && parts[featuresIndex + 1]) {
      return parts[featuresIndex + 1];
    }
    return parts[parts.length - 1] || feature;
  }, [pathname, feature]);
  const translatedTitle = useMemo(() => {
    const key = `features.items.${feature}.title`;
    const value = t(key);
    return value && value !== key ? value : title;
  }, [feature, t, title]);
  const [tab, setTab] = useState('main');

  useEffect(() => {
    setTab('main');
  }, [feature]);

  useEffect(() => {
    let active = true;
    const saveRecent = async () => {
      try {
        const parsed = await getRecentFeatures();
        const updated = [
          { id: recentFeatureId, openedAt: new Date().toISOString() },
          ...parsed.filter((item: { id: string }) => item.id !== recentFeatureId)
        ].slice(0, RECENT_FEATURES_LIMIT);
        if (active) {
          await setRecentFeatures(updated);
          if (typeof window !== 'undefined' && typeof window.localStorage !== 'undefined') {
            window.localStorage.setItem('recent_features', JSON.stringify(updated));
          }
        }
      } catch (e) {
        clientLogger.log('Failed to store recent feature', e);
      }
    };
    if (recentFeatureId) {
      saveRecent();
    }
    return () => {
      active = false;
    };
  }, [recentFeatureId]);

  const C = useMemo(() => ({
    bg: colors.bg,
    bgSoft: colors.bgSoft,
    card: colors.card,
    text: colors.text,
    textSec: colors.textSec,
    textMuted: colors.textMuted,
    border: colors.border,
    accent: colors.accent,
  }), [colors]);

  const s = useMemo(() => createStyles(C), [C]);

  const pad = sw < 360 ? 12 : sw >= 1024 ? 24 : sw >= 768 ? 20 : sw >= 414 ? 18 : 16;
  const fs = (b: number) => sw < 360 ? b - 1 : sw >= 414 ? b + 1 : b;
  const contentPad = noPadding ? 0 : pad;

  const TABS = showSecondaryTabs
    ? [
      { id: 'main', label: translatedTitle, icon: icon },
      { id: 'scan', label: scanTabLabel || t('feature.tabs.scan'), icon: scanTabIcon || 'scan' },
      { id: 'chat', label: chatTabLabel || t('feature.tabs.chat'), icon: chatTabIcon || 'chatbubble-ellipses' },
      ...(extraTabLabel ? [{ id: 'extra', label: extraTabLabel, icon: extraTabIcon || 'apps' }] : []),
    ]
    : [
      { id: 'main', label: translatedTitle, icon: icon },
    ];

  useEffect(() => {
    if (!showSecondaryTabs && tab !== 'main') {
      setTab('main');
    }
  }, [showSecondaryTabs, tab]);

  return (
    <SafeAreaView style={s.container} edges={['top']} testID={`feature-layout-${feature}`} accessibilityLabel={`${translatedTitle} feature screen`}>
      <View style={[s.header, { paddingHorizontal: pad }]} testID={`feature-layout-header-${feature}`} accessibilityRole="header">
        <TouchableOpacity style={s.backBtn} onPress={() => router.back()} testID={`feature-layout-back-${feature}`} accessibilityLabel="Go back" accessibilityRole="button">
          <Ionicons name="arrow-back" size={20} color={C.text} />
        </TouchableOpacity>
        <View style={s.headerCenter}>
          <View style={[s.headerIcon, { backgroundColor: (globalThis as any).__alphaColor(color, '15') }]}
            data-testid={`feature-layout-icon-${feature}`} testID={`feature-layout-icon-${feature}`}
          >
            <Ionicons name={icon as any} size={16} color={color} />
          </View>
          <Text style={[s.headerTitle, { fontSize: fs(16) }]} testID={`feature-layout-title-${feature}`}>
            {translatedTitle}
          </Text>
        </View>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
          <TouchableOpacity style={s.fwdBtn}
            onPress={() => setThemeMode(darkMode ? 'light' : 'dark')}
            testID="theme-toggle"
            data-testid="theme-toggle"
            accessibilityLabel={darkMode ? 'Switch to light mode' : 'Switch to dark mode'}
            accessibilityRole="button"
          >
            <Ionicons name={darkMode ? 'sunny-outline' : 'moon-outline'} size={18} color={C.text} />
          </TouchableOpacity>
          {typeof window !== 'undefined' ? (
            <TouchableOpacity style={[s.fwdBtn, !canGoForward && { opacity: 0.35 }]}
              onPress={goForward}
              disabled={!canGoForward}
              testID={`feature-layout-forward-${feature}`}
              data-testid={`feature-layout-forward-${feature}`}
              accessibilityLabel="Go forward"
              accessibilityRole="button"
            >
              <Ionicons name="arrow-forward" size={18} color={canGoForward ? C.text : C.textMuted} />
            </TouchableOpacity>
          ) : (
            <View style={{ width: 36 }} />
          )}
        </View>
      </View>

      {TABS.length > 1 && (
      <View style={[s.tabBar, { paddingHorizontal: pad }]} testID={`feature-layout-tabs-${feature}`}>
        {TABS.map(t => (
          <TouchableOpacity key={t.id}
            style={[s.tab, tab === t.id && { backgroundColor: (globalThis as any).__alphaColor(C.accent, '12'), borderColor: (globalThis as any).__alphaColor(C.accent, '30'), borderWidth: 1 }]}
            onPress={() => setTab(t.id)}
            data-testid={`feature-layout-tab-${feature}-${t.id}`} testID={`feature-layout-tab-${feature}-${t.id}`}
          >
            <Ionicons name={t.icon as any} size={16} color={tab === t.id ? C.accent : C.textMuted} />
            <Text
              style={[s.tabText, { fontSize: fs(12) }, tab === t.id && { color: C.accent, fontWeight: '700' }]}
              testID={`feature-layout-tab-label-${feature}-${t.id}`}
              data-testid={`feature-layout-tab-label-${feature}-${t.id}`}
            >
              {t.label}
            </Text>
          </TouchableOpacity>
        ))}
      </View>
      )}

      {tab === 'main' && selfScrolling && (
        <View key={`content-${darkMode ? 'dark' : 'light'}`} style={s.content} data-testid={`feature-layout-self-scroll-${feature}`}>
          <UpgradeBanner featureName={translatedTitle} variant="banner" requiredPlan={requiredPlan} />
          {requiredPlan ? (
            <PremiumGuard featureName={translatedTitle} requiredPlan={requiredPlan}>
              {children}
            </PremiumGuard>
          ) : children}
        </View>
      )}
      {tab === 'main' && !selfScrolling && (
        <ScrollView key={`content-${darkMode ? 'dark' : 'light'}`} style={s.content} contentContainerStyle={{ paddingHorizontal: contentPad, paddingBottom: 32, width: '100%', maxWidth: 1240, alignSelf: 'center' }} showsVerticalScrollIndicator={false}>
          <View style={[s.hero, { borderColor: C.border }]} data-testid={`feature-layout-hero-${feature}`} testID={`feature-layout-hero-${feature}`}>
            <View style={[s.heroIcon, { backgroundColor: (globalThis as any).__alphaColor(color, '18') }]}
              data-testid={`feature-layout-hero-icon-${feature}`} testID={`feature-layout-hero-icon-${feature}`}
            >
              <Ionicons name={icon as any} size={20} color={color} />
            </View>
            <View style={{ flex: 1 }}>
              <Text style={[s.heroTitle, { fontSize: fs(20) }]}
                data-testid={`feature-layout-hero-title-${feature}`} testID={`feature-layout-hero-title-${feature}`}
              >
                {translatedTitle}
              </Text>
              {subtitle ? (
                <Text style={[s.heroSubtitle, { fontSize: fs(13) }]} data-testid={`feature-layout-hero-subtitle-${feature}`} testID={`feature-layout-hero-subtitle-${feature}`}>
                  {subtitle}
                </Text>
              ) : null}
            </View>
          </View>
          {showTransparencyBanner ? <AITransparencyBanner testId={`feature-layout-transparency-${feature}`} /> : null}
          <UpgradeBanner featureName={translatedTitle} variant="banner" requiredPlan={requiredPlan} />
          {requiredPlan ? (
            <PremiumGuard featureName={translatedTitle} requiredPlan={requiredPlan}>
              {children}
            </PremiumGuard>
          ) : children}
          {showActions && feature !== 'ai-video' ? <FeatureActionsBar featureKey={feature} /> : null}
        </ScrollView>
      )}
      {showSecondaryTabs && tab === 'scan' && (
        <View style={[s.content, { paddingHorizontal: contentPad, backgroundColor: C.bg, width: '100%', maxWidth: 1240, alignSelf: 'center' }]}>
          {scanContent ? (
            scanContent
          ) : (
            <Suspense fallback={<View style={{ flex: 1, justifyContent: 'center', alignItems: 'center' }}><ActivityIndicator size="large" color={color} /></View>}>
              <AIScanner feature={feature} themeColors={colors} />
            </Suspense>
          )}
        </View>
      )}
      {showSecondaryTabs && tab === 'chat' && (
        <View style={[s.content, { paddingHorizontal: contentPad, backgroundColor: C.bg, width: '100%', maxWidth: 1240, alignSelf: 'center' }]}>
          {chatContent ? (
            chatContent
          ) : (
            <Suspense fallback={<View style={{ flex: 1, justifyContent: 'center', alignItems: 'center' }}><ActivityIndicator size="large" color={color} /></View>}>
              <AIChatPanel feature={feature} themeColors={colors} />
            </Suspense>
          )}
        </View>
      )}
      {showSecondaryTabs && tab === 'extra' && (
        <View style={[s.content, { paddingHorizontal: contentPad, backgroundColor: C.bg, width: '100%', maxWidth: 1240, alignSelf: 'center' }]}>
          {extraContent ? (
            extraContent
          ) : (
            <View style={{ flex: 1, justifyContent: 'center', alignItems: 'center' }} data-testid={`feature-layout-extra-empty-${feature}`} testID={`feature-layout-extra-empty-${feature}`}>
              <Text style={{ color: C.textSec, fontSize: 12.5 }}>Extra tab content is not configured yet.</Text>
            </View>
          )}
        </View>
      )}
    </SafeAreaView>
  );
}

const createStyles = (C: any) => StyleSheet.create({
  container: { flex: 1, backgroundColor: C.bg },
  header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: C.border },
  backBtn: { width: 36, height: 36, borderRadius: 12, backgroundColor: C.bgSoft, alignItems: 'center', justifyContent: 'center' },
  fwdBtn: { width: 36, height: 36, borderRadius: 12, backgroundColor: C.bgSoft, alignItems: 'center', justifyContent: 'center', opacity: 0.6 },
  headerCenter: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  headerIcon: { width: 28, height: 28, borderRadius: 8, alignItems: 'center', justifyContent: 'center' },
  headerTitle: { fontWeight: '700', color: C.text },
  tabBar: { flexDirection: 'row', paddingVertical: 8, gap: 6 },
  tab: { flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', paddingVertical: 9, borderRadius: 10, backgroundColor: C.bgSoft, gap: 5 },
  tabText: { fontWeight: '600', color: C.textMuted },
  content: { flex: 1 },
  hero: { flexDirection: 'row', gap: 12, borderRadius: 16, borderWidth: 1, padding: 14, marginBottom: 16, backgroundColor: C.card },
  heroIcon: { width: 44, height: 44, borderRadius: 14, alignItems: 'center', justifyContent: 'center' },
  heroTitle: { fontWeight: '700', color: C.text },
  heroSubtitle: { marginTop: 4, color: C.textSec, lineHeight: 18 },
});
