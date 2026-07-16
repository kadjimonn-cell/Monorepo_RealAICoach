import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { View, Text, TouchableOpacity, ScrollView, Platform, useWindowDimensions } from 'react-native';
import { usePathname, useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import api from '../services/api';
import { useAccessControl } from '../context/AccessControlContext';
import { useTheme } from '../context/ThemeContext';
import { useTranslation } from '../hooks/useTranslation';

type Specialist = { agent_key: string; name: string; role: string; category: string; description: string };

const dayStamp = () => new Date().toISOString().slice(0, 10);

const isDismissed = (featureKey: string) => {
  if (Platform.OS !== 'web' || typeof window === 'undefined') return false;
  try {
    return window.localStorage.getItem(`sss_dismiss_${featureKey}`) === dayStamp();
  } catch {
    return false;
  }
};

const markDismissed = (featureKey: string) => {
  if (Platform.OS !== 'web' || typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(`sss_dismiss_${featureKey}`, dayStamp());
  } catch {}
};

export const SuggestedSpecialistsStrip = () => {
  const pathname = usePathname();
  const router = useRouter();
  const { session } = useAccessControl();
  const { darkMode, colors } = useTheme();
  const { tx } = useTranslation();
  const { width: winWidth } = useWindowDimensions();
  const [specialists, setSpecialists] = useState<Specialist[]>([]);
  const [dismissed, setDismissed] = useState(false);

  const featureKey = useMemo(() => {
    const policy = session?.feature_entitlements?.canonical_feature_policy;
    if (!policy || !pathname) return null;
    const path = String(pathname).split(/[?#]/)[0] || '/';
    if (path.startsWith('/ai-coaching-team') || path.startsWith('/admin')) return null;
    for (const [key, raw] of Object.entries<any>(policy)) {
      const routes: string[] = Array.isArray(raw?.ui_routes) ? raw.ui_routes : [];
      if (routes.some((route) => path === route || path.startsWith(`${route}/`))) return key;
    }
    return null;
  }, [session, pathname]);

  useEffect(() => {
    let cancelled = false;
    setSpecialists([]);
    if (!featureKey) return;
    const wasDismissed = isDismissed(featureKey);
    setDismissed(wasDismissed);
    if (wasDismissed) return;
    api.get(`/access-control/feature-specialists/${featureKey}`, { silentLoading: true, timeout: 8000 } as any)
      .then((res: any) => {
        if (!cancelled) setSpecialists(Array.isArray(res?.data?.specialists) ? res.data.specialists.slice(0, 4) : []);
      })
      .catch(() => {});
    return () => { cancelled = true; };
  }, [featureKey]);

  const handleTap = useCallback((agentKey: string) => {
    if (featureKey) {
      api.post(`/access-control/feature-specialists/${featureKey}/click`, { agent_key: agentKey }, { silentLoading: true } as any).catch(() => {});
    }
    router.push('/ai-coaching-team');
  }, [featureKey, router]);

  const handleDismiss = useCallback(() => {
    if (featureKey) markDismissed(featureKey);
    setDismissed(true);
  }, [featureKey]);

  if (!featureKey || dismissed || specialists.length === 0) return null;

  const stripBg = darkMode ? 'rgba(15,23,42,0.92)' : 'rgba(255,255,255,0.96)';
  const stripBorder = darkMode ? 'rgba(148,163,184,0.35)' : 'rgba(100,116,139,0.28)';
  const titleColor = colors.textMuted;
  const chipBg = darkMode ? 'rgba(20,184,166,0.14)' : 'rgba(20,184,166,0.10)';
  const chipText = colors.primary;

  return (
    <View
      pointerEvents="box-none"
      style={{
        position: Platform.OS === 'web' ? ('fixed' as any) : 'absolute',
        left: 0, right: 0, bottom: 74, zIndex: 69,
        alignItems: 'center',
      }}
    >
      <View
        data-testid="suggested-specialists-strip"
        testID="suggested-specialists-strip"
        style={{
          flexDirection: 'row', alignItems: 'center', gap: 8,
          paddingVertical: 8, paddingLeft: 14, paddingRight: 8,
          borderRadius: 999, borderWidth: 1, borderColor: stripBorder,
          backgroundColor: stripBg, maxWidth: Math.min(600, winWidth - 24), marginHorizontal: 12,
          ...(Platform.OS === 'web' ? {
            backdropFilter: 'blur(14px)', WebkitBackdropFilter: 'blur(14px)',
            boxShadow: darkMode ? '0 10px 30px rgba(0,0,0,0.45)' : '0 10px 30px rgba(15,23,42,0.16)',
          } as any : {}),
        }}
      >
        <Ionicons name="sparkles" size={13} color={colors.primary} />
        <Text
          data-testid="suggested-specialists-title"
          testID="suggested-specialists-title"
          style={{ color: titleColor, fontSize: 11.5, fontWeight: '700', flexShrink: 0 }}
          numberOfLines={1}
        >
          {tx('featureSpecialists.title', 'Suggested AI specialists')}
        </Text>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ flexGrow: 0, flexShrink: 1, maxWidth: Math.min(420, winWidth - 210) }} contentContainerStyle={{ gap: 6, alignItems: 'center' }}>
          {specialists.map((sp) => (
            <TouchableOpacity
              key={sp.agent_key}
              data-testid={`specialist-chip-${sp.agent_key}`}
              testID={`specialist-chip-${sp.agent_key}`}
              onPress={() => handleTap(sp.agent_key)}
              accessibilityRole="button"
              style={{
                backgroundColor: chipBg, borderRadius: 999,
                paddingVertical: 5, paddingHorizontal: 11,
                ...(Platform.OS === 'web' ? { cursor: 'pointer', transition: 'opacity 0.15s ease' } as any : {}),
              }}
            >
              <Text style={{ color: chipText, fontSize: 12, fontWeight: '600' }} numberOfLines={1}>{sp.name}</Text>
            </TouchableOpacity>
          ))}
        </ScrollView>
        <TouchableOpacity
          data-testid="suggested-specialists-dismiss"
          testID="suggested-specialists-dismiss"
          onPress={handleDismiss}
          accessibilityRole="button"
          accessibilityLabel={tx('featureSpecialists.dismiss', 'Dismiss')}
          style={{ padding: 4, ...(Platform.OS === 'web' ? { cursor: 'pointer' } as any : {}) }}
        >
          <Ionicons name="close" size={14} color={colors.textMuted} />
        </TouchableOpacity>
      </View>
    </View>
  );
};

export default SuggestedSpecialistsStrip;
