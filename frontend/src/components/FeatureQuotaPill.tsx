import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { View, Text, TouchableOpacity, Platform } from 'react-native';
import { usePathname, useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import api from '../services/api';
import { onFeatureQuotaLimit } from '../services/featureQuotaEvents';
import { useAccessControl } from '../context/AccessControlContext';
import { useTheme } from '../context/ThemeContext';
import { useTranslation } from '../hooks/useTranslation';

type MeterState = { limit: number; used: number; remaining: number };

const dayStamp = () => new Date().toISOString().slice(0, 10);

const isDismissed = (featureKey: string) => {
  if (Platform.OS !== 'web' || typeof window === 'undefined') return false;
  try {
    return window.localStorage.getItem(`fqp_dismiss_${featureKey}`) === dayStamp();
  } catch {
    return false;
  }
};

const markDismissed = (featureKey: string) => {
  if (Platform.OS !== 'web' || typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(`fqp_dismiss_${featureKey}`, dayStamp());
  } catch {}
};

export const FeatureQuotaPill = () => {
  const pathname = usePathname();
  const router = useRouter();
  const { session } = useAccessControl();
  const { darkMode, colors } = useTheme();
  const { tx } = useTranslation();
  const [meter, setMeter] = useState<MeterState | null>(null);
  const [dismissed, setDismissed] = useState(false);

  const featureEntry = useMemo(() => {
    const policy = session?.feature_entitlements?.canonical_feature_policy;
    if (!policy || !pathname) return null;
    const path = String(pathname).split(/[?#]/)[0] || '/';
    for (const [featureKey, raw] of Object.entries<any>(policy)) {
      const routes: string[] = Array.isArray(raw?.ui_routes) ? raw.ui_routes : [];
      const matches = routes.some((route) => path === route || path.startsWith(`${route}/`));
      if (matches) return { featureKey, limit: Number(raw?.daily_action_limit ?? -1), selfEnforced: Boolean(raw?.self_enforced) };
    }
    return null;
  }, [session, pathname]);

  const eligible = Boolean(featureEntry && featureEntry.limit > 0 && !featureEntry.selfEnforced);

  useEffect(() => {
    let cancelled = false;
    setMeter(null);
    if (!eligible || !featureEntry) return;
    setDismissed(isDismissed(featureEntry.featureKey));
    api.get(`/access-control/feature-meter/${featureEntry.featureKey}`, { silentLoading: true, timeout: 6000 } as any)
      .then((res: any) => {
        if (cancelled) return;
        const data = res?.data || {};
        if (Number(data.limit) > 0) {
          setMeter({ limit: Number(data.limit), used: Number(data.used || 0), remaining: Number(data.remaining || 0) });
        }
      })
      .catch(() => {});
    return () => { cancelled = true; };
  }, [eligible, featureEntry?.featureKey]);

  useEffect(() => {
    if (!featureEntry) return undefined;
    return onFeatureQuotaLimit((event) => {
      if (event.featureKey !== featureEntry.featureKey) return;
      setMeter({ limit: event.limit, used: event.used, remaining: 0 });
      setDismissed(false);
    });
  }, [featureEntry?.featureKey]);

  const handleUpgrade = useCallback(() => {
    router.push('/subscription/plans');
  }, [router]);

  const handleDismiss = useCallback(() => {
    if (featureEntry) markDismissed(featureEntry.featureKey);
    setDismissed(true);
  }, [featureEntry]);

  if (!eligible || !meter || dismissed) return null;

  const limitReached = meter.remaining <= 0;
  const remainingLabel = meter.remaining === 1
    ? tx('featureQuota.remainingOne', '1 free action left today')
    : tx('featureQuota.remaining', '{count} free actions left today').replace('{count}', String(meter.remaining));

  const pillBg = limitReached
    ? (darkMode ? 'rgba(127,29,29,0.96)' : 'rgba(254,226,226,0.98)')
    : (darkMode ? 'rgba(15,23,42,0.92)' : 'rgba(255,255,255,0.96)');
  const pillBorder = limitReached
    ? (darkMode ? 'rgba(248,113,113,0.55)' : 'rgba(220,38,38,0.35)')
    : (darkMode ? 'rgba(148,163,184,0.35)' : 'rgba(100,116,139,0.28)');
  const textColor = limitReached ? colors.errorText : colors.text;
  const accent = limitReached ? colors.error : colors.primary;

  return (
    <View
      pointerEvents="box-none"
      style={{
        position: Platform.OS === 'web' ? ('fixed' as any) : 'absolute',
        left: 0, right: 0, bottom: 22, zIndex: 70,
        alignItems: 'center',
      }}
    >
      <View
        data-testid={limitReached ? 'feature-quota-limit-pill' : 'feature-quota-pill'}
        testID={limitReached ? 'feature-quota-limit-pill' : 'feature-quota-pill'}
        style={{
          flexDirection: 'row', alignItems: 'center', gap: 8,
          paddingVertical: 8, paddingLeft: 14, paddingRight: 8,
          borderRadius: 999, borderWidth: 1, borderColor: pillBorder,
          backgroundColor: pillBg, maxWidth: 420,
          ...(Platform.OS === 'web' ? {
            backdropFilter: 'blur(14px)', WebkitBackdropFilter: 'blur(14px)',
            boxShadow: darkMode ? '0 10px 30px rgba(0,0,0,0.45)' : '0 10px 30px rgba(15,23,42,0.16)',
          } as any : {}),
        }}
      >
        <Ionicons name={limitReached ? 'lock-closed' : 'flash'} size={14} color={accent} />
        <Text
          data-testid="feature-quota-pill-label"
          testID="feature-quota-pill-label"
          style={{ color: textColor, fontSize: 13, fontWeight: '600' }}
          numberOfLines={1}
        >
          {limitReached ? tx('featureQuota.limitReached', 'Daily free limit reached') : remainingLabel}
        </Text>
        {limitReached && (
          <TouchableOpacity
            data-testid="feature-quota-upgrade-cta"
            testID="feature-quota-upgrade-cta"
            onPress={handleUpgrade}
            accessibilityRole="button"
            style={{
              backgroundColor: accent, borderRadius: 999,
              paddingVertical: 6, paddingHorizontal: 14,
              ...(Platform.OS === 'web' ? { cursor: 'pointer', transition: 'opacity 0.15s ease' } as any : {}),
            }}
          >
            <Text style={{ color: colors.primaryText, fontSize: 12.5, fontWeight: '700' }}>{/* @theme-ok white-on-accent CTA */}
              {tx('featureQuota.upgrade', 'Upgrade')}
            </Text>
          </TouchableOpacity>
        )}
        <TouchableOpacity
          data-testid="feature-quota-dismiss"
          testID="feature-quota-dismiss"
          onPress={handleDismiss}
          accessibilityRole="button"
          accessibilityLabel={tx('featureQuota.dismiss', 'Dismiss')}
          style={{ padding: 4, ...(Platform.OS === 'web' ? { cursor: 'pointer' } as any : {}) }}
        >
          <Ionicons name="close" size={14} color={colors.textMuted} />
        </TouchableOpacity>
      </View>
    </View>
  );
};

export default FeatureQuotaPill;
