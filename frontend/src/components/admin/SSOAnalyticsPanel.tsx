import React, { useEffect, useState, useRef } from 'react';
import {
  View, Text, TouchableOpacity, Animated,
  useWindowDimensions, Platform, ImageBackground,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useLiveQuery } from '../../hooks/useLiveQuery';
import { useAdminTheme } from '../../hooks/useAdminTheme';
import { useTranslation } from '../../hooks/useTranslation';
import { useTheme } from '../../context/ThemeContext';

function makeTHEME(AC: any) { return {
  bg: AC.bg, card: AC.card, cardGlass: AC.surface,
  border: AC.border, text: AC.text, textSec: AC.textSec, textMuted: AC.textMuted,
  primary: AC.primary, success: AC.success, error: AC.error, warning: AC.warning,
  purple: AC.purple, cyan: AC.info,
}; }

const tx = (_key: string, fallback: string) => fallback;

const PROVIDER_COLORS: Record<string, string> = {
  email: 'var(--app-primary)', google: 'var(--app-primary)', microsoft: 'var(--app-primary)', apple: 'var(--app-primary)', // @theme-ok brand/role/state identifier
};
const PROVIDER_ICONS: Record<string, string> = {
  email: 'mail', google: 'logo-google', microsoft: 'logo-microsoft', apple: 'logo-apple',
};
const PROVIDER_LABELS: Record<string, string> = {
  email: 'Email/Password', google: 'Google', microsoft: 'Microsoft', apple: 'Apple',
};

const BG_IMAGES = [
  'https://images.unsplash.com/photo-1771793231904-a516cd3baff4?w=1920&q=60&auto=format',
  'https://images.unsplash.com/photo-1772050138764-2b1925e0c6b2?w=1920&q=60&auto=format',
  'https://images.unsplash.com/photo-1772050138768-2107c6e62a03?w=1920&q=60&auto=format',
  'https://images.unsplash.com/photo-1737505599162-d9932323a889?w=1920&q=60&auto=format',
];

// Donut chart rendered via CSS conic-gradient
function DonutChart({ data }: { data: any[] }) {
  const total = data.reduce((s, d) => s + d.count, 0) || 1;
  let cumPct = 0;
  const stops = data.map(d => {
    const pct = (d.count / total) * 100;
    const start = cumPct;
    cumPct += pct;
    return `${d.color} ${start}% ${cumPct}%`;
  }).join(', ');

  const webStyle = Platform.OS === 'web' ? {
    background: `conic-gradient(${stops})`,
    WebkitMask: 'radial-gradient(circle at center, transparent 55%, black 56%)',
    mask: 'radial-gradient(circle at center, transparent 55%, black 56%)',
  } : {};

  return (
    <View style={{ alignItems: 'center' }}>
      <View style={[{ width: 160, height: 160, borderRadius: 80, position: 'relative' }, webStyle as any]}>
        <View style={{ position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, justifyContent: 'center', alignItems: 'center' }}>
          <Text style={{ fontSize: 28, fontWeight: '900', color: THEME.text }}>{total}</Text>
          <Text style={{ fontSize: 10, fontWeight: '600', color: THEME.textMuted }}>{tx('admin.sSOAnalyticsPanel.auto.text.001', 'TOTAL USERS')}</Text>
        </View>
      </View>
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', justifyContent: 'center', gap: 12, marginTop: 16 }}>
        {data.map(d => (
          <View key={d.provider} style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
            <View style={{ width: 10, height: 10, borderRadius: 3, backgroundColor: d.color }} />
            <Text style={{ fontSize: 11, color: THEME.textSec, fontWeight: '600' }}>
              {PROVIDER_LABELS[d.provider] || d.provider} ({d.percentage}%)
            </Text>
          </View>
        ))}
      </View>
    </View>
  );
}

// Bar chart for trends
function TrendsChart({ data }: { data: any[] }) {
  const last14 = data.slice(-14);
  const maxVal = Math.max(...last14.map(d => d.email + d.google + d.microsoft + d.apple + d.failed), 1);

  return (
    <View>
      <View style={{ flexDirection: 'row', alignItems: 'flex-end', height: 140, gap: 2 }}>
        {last14.map((d, i) => {
          const total = d.email + d.google + d.microsoft + d.apple;
          const h = Math.max((total / maxVal) * 120, 2);
          const failH = Math.max((d.failed / maxVal) * 120, 0);
          return (
            <View key={i} style={{ flex: 1, alignItems: 'center', justifyContent: 'flex-end', height: 140 }}>
              {failH > 0 && <View style={{ width: '70%', height: failH, backgroundColor: (globalThis as any).__alphaColor(THEME.error, '60'), borderRadius: 2, marginBottom: 1 }} />}
              <View style={{ width: '70%', height: h, borderRadius: 3, overflow: 'hidden' }}>
                {d.email > 0 && <View style={{ height: `${(d.email / Math.max(total, 1)) * 100}%`, backgroundColor: PROVIDER_COLORS.email }} />}
                {d.google > 0 && <View style={{ height: `${(d.google / Math.max(total, 1)) * 100}%`, backgroundColor: PROVIDER_COLORS.google }} />}
                {d.microsoft > 0 && <View style={{ height: `${(d.microsoft / Math.max(total, 1)) * 100}%`, backgroundColor: PROVIDER_COLORS.microsoft }} />}
                {d.apple > 0 && <View style={{ height: `${(d.apple / Math.max(total, 1)) * 100}%`, backgroundColor: PROVIDER_COLORS.apple }} />}
              </View>
              <Text style={{ fontSize: 7, color: THEME.textMuted, marginTop: 4, transform: [{ rotate: '-45deg' }] }}>{d.date.slice(5)}</Text>
            </View>
          );
        })}
      </View>
      <View style={{ flexDirection: 'row', justifyContent: 'center', gap: 14, marginTop: 14 }}>
        {['email', 'google', 'microsoft', 'apple', 'failed'].map(p => (
          <View key={p} style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}>
            <View style={{ width: 8, height: 8, borderRadius: 2, backgroundColor: p === 'failed' ? THEME.error : PROVIDER_COLORS[p] }} />
            <Text style={{ fontSize: 9, color: THEME.textMuted, fontWeight: '600' }}>{p === 'failed' ? 'Failed' : PROVIDER_LABELS[p]}</Text>
          </View>
        ))}
      </View>
    </View>
  );
}

// Heatmap for peak hours
function HourHeatmap({ data, maxCount }: { data: any[]; maxCount: number }) {
  return (
    <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 3 }}>
      {data.map(d => {
        const intensity = maxCount > 0 ? d.count / maxCount : 0;
        const bg = intensity > 0.75 ? 'var(--app-primary)' : intensity > 0.5 ? 'var(--app-primary)' : intensity > 0.25 ? 'var(--app-primary)' : intensity > 0 ? 'var(--app-primary-soft)' : 'var(--app-text)';
        return (
          <View key={d.hour} style={{ width: 38, height: 38, borderRadius: 6, backgroundColor: bg, alignItems: 'center', justifyContent: 'center' }}>
            <Text style={{ fontSize: 9, fontWeight: '800', color: intensity > 0.25 ? 'var(--app-primary-text)' : THEME.textMuted }}>{String(d.hour).padStart(2, '0')}</Text>
            <Text style={{ fontSize: 7, color: intensity > 0.25 ? 'var(--app-primary-text)' + 'CC' : THEME.textMuted }}>{d.count}</Text>
          </View>
        );
      })}
    </View>
  );
}

export default function SSOAnalyticsPanel() {
  const { t } = useTranslation();
  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };

  const { colors } = useTheme();
  const AC = useAdminTheme();
  const THEME = React.useMemo(() => makeTHEME(AC), [AC]);
  const { data, loading } = useLiveQuery('/auth/sso-analytics', { entity: 'sso', pollInterval: 30000 });
  const [bgIndex, setBgIndex] = useState(0);
  const fadeAnim = useRef(new Animated.Value(1)).current;
  const { width } = useWindowDimensions();
  const isWide = width >= 900;

  // Rotate background every 35s
  useEffect(() => {
    const iv = setInterval(() => {
      Animated.timing(fadeAnim, { toValue: 0, duration: 800, useNativeDriver: true }).start(() => {
        setBgIndex(prev => (prev + 1) % BG_IMAGES.length);
        Animated.timing(fadeAnim, { toValue: 1, duration: 800, useNativeDriver: true }).start();
      });
    }, 35000);
    return () => clearInterval(iv);
  }, [fadeAnim]);

  if (!data || loading) {
    return (
      <View style={{ padding: 40, alignItems: 'center' }}>
        <Text style={{ color: THEME.textMuted, fontSize: 13 }}>{tx('admin.sSOAnalyticsPanel.auto.text.002', 'Loading SSO Analytics...')}</Text>
      </View>
    );
  }

  const glass = {
    backgroundColor: THEME.cardGlass,
    borderRadius: 16,
    borderWidth: 1,
    borderColor: THEME.border,
    padding: 20,
    ...(Platform.OS === 'web' ? { backdropFilter: 'blur(16px)', WebkitBackdropFilter: 'blur(16px)' } : {}),
  };

  return (
    <View testID="sso-analytics-panel">
      {/* Rotating Hero Background */}
      <Animated.View style={{ opacity: fadeAnim, borderRadius: 16, overflow: 'hidden', marginBottom: 20 }}>
        <ImageBackground
          source={{ uri: BG_IMAGES[bgIndex] }}
          style={{ minHeight: 200, justifyContent: 'flex-end', padding: 24 }}
          imageStyle={{ borderRadius: 16, opacity: 0.4 }}
        >
          <View style={{ ...(Platform.OS === 'web' ? { backdropFilter: 'blur(4px)' } : {}), backgroundColor: 'rgba(0,0,0,0.5)', borderRadius: 12, padding: 20 } as any}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 8 }}>
              <Ionicons name="finger-print" size={24} color={THEME.primary} />
              <Text style={{ fontSize: 22, fontWeight: '900', color: THEME.text, letterSpacing: -0.5 }}>{tx('admin.sSOAnalyticsPanel.auto.text.003', 'SSO Authentication Analytics')}</Text>
            </View>
            <Text style={{ fontSize: 13, color: THEME.textSec, lineHeight: 20 }}>{tx('admin.sSOAnalyticsPanel.auto.text.004', 'Real-time authentication insights across all sign-in methods. Auto-refreshes every 30 seconds.')}</Text>
            {/* Inline image indicator dots */}
            <View style={{ flexDirection: 'row', gap: 6, marginTop: 12 }}>
              {BG_IMAGES.map((_, i) => (
                <View key={i} style={{ width: i === bgIndex ? 20 : 8, height: 4, borderRadius: 2, backgroundColor: (globalThis as any).__alphaColor(i === bgIndex ? THEME.primary : THEME.textMuted, '40'), transition: 'all 0.3s' } as any} />
              ))}
            </View>
          </View>
        </ImageBackground>
      </Animated.View>

      {/* KPI Cards Row */}
      <View style={{ flexDirection: isWide ? 'row' : 'column', gap: 12, marginBottom: 20 }} testID="sso-kpi-cards">
        {[
          { label: 'Sign-ins Today', value: data.kpis.signins_today, icon: 'log-in', color: THEME.primary },
          { label: 'Failed Today', value: data.kpis.failed_today, icon: 'close-circle', color: THEME.error },
          { label: 'Success Rate', value: `${data.kpis.success_rate}%`, icon: 'checkmark-circle', color: THEME.successText },
          { label: 'New Users Today', value: data.kpis.new_users_today, icon: 'person-add', color: THEME.cyan },
          { label: 'Most Popular', value: PROVIDER_LABELS[data.kpis.most_popular] || data.kpis.most_popular, icon: 'trophy', color: THEME.warningText },
        ].map((kpi, i) => (
          <View key={i} style={[glass as any, { flex: isWide ? 1 : undefined }]} testID={`sso-kpi-${i}`}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 8 }}>
              <View style={{ width: 32, height: 32, borderRadius: 10, backgroundColor: (globalThis as any).__alphaColor(kpi.color, '18'), alignItems: 'center', justifyContent: 'center' }}>
                <Ionicons name={kpi.icon as any} size={16} color={kpi.color} />
              </View>
              <Text style={{ fontSize: 11, fontWeight: '600', color: THEME.textMuted }}>{kpi.label}</Text>
            </View>
            <Text style={{ fontSize: 26, fontWeight: '900', color: THEME.text }}>{kpi.value}</Text>
          </View>
        ))}
      </View>

      {/* Main Grid: Distribution + Trends */}
      <View style={{ flexDirection: isWide ? 'row' : 'column', gap: 16, marginBottom: 20 }}>
        {/* Donut Chart */}
        <View style={[glass as any, { flex: isWide ? 1 : undefined }]} testID="sso-distribution-chart">
          <Text style={{ fontSize: 15, fontWeight: '800', color: THEME.text, marginBottom: 16 }}>{tx('admin.sSOAnalyticsPanel.auto.text.005', 'Auth Method Distribution')}</Text>
          <DonutChart data={data.distribution} />
        </View>

        {/* Trends Chart */}
        <View style={[glass as any, { flex: isWide ? 1.5 : undefined }]} testID="sso-trends-chart">
          <Text style={{ fontSize: 15, fontWeight: '800', color: THEME.text, marginBottom: 4 }}>{tx('admin.sSOAnalyticsPanel.auto.text.006', 'Sign-in Trends (14 Days)')}</Text>
          <Text style={{ fontSize: 11, color: THEME.textMuted, marginBottom: 16 }}>{tx('admin.sSOAnalyticsPanel.auto.text.007', 'Stacked by authentication method')}</Text>
          <TrendsChart data={data.trends} />
        </View>
      </View>

      {/* Success Rates + Active Sessions */}
      <View style={{ flexDirection: isWide ? 'row' : 'column', gap: 16, marginBottom: 20 }}>
        {/* Success Rates */}
        <View style={[glass as any, { flex: isWide ? 1 : undefined }]} testID="sso-success-rates">
          <Text style={{ fontSize: 15, fontWeight: '800', color: THEME.text, marginBottom: 16 }}>{tx('admin.sSOAnalyticsPanel.auto.text.008', 'Success Rate by Provider (7d)')}</Text>
          {data.success_rates.map((sr: any) => (
            <View key={sr.provider} style={{ marginBottom: 14 }}>
              <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 6 }}>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                  <Ionicons name={PROVIDER_ICONS[sr.provider] as any} size={14} color={sr.color} />
                  <Text style={{ fontSize: 12, fontWeight: '700', color: THEME.text }}>{PROVIDER_LABELS[sr.provider]}</Text>
                </View>
                <Text style={{ fontSize: 12, fontWeight: '800', color: sr.rate >= 95 ? THEME.success : sr.rate >= 80 ? THEME.warning : THEME.error }}>
                  {sr.rate}%
                </Text>
              </View>
              <View style={{ height: 6, backgroundColor: THEME.border, borderRadius: 3, overflow: 'hidden' }}>
                <View style={{ width: `${sr.rate}%`, height: '100%', backgroundColor: sr.color, borderRadius: 3 }} />
              </View>
              <View style={{ flexDirection: 'row', gap: 12, marginTop: 4 }}>
                <Text style={{ fontSize: 9, color: THEME.textMuted }}>{sr.success} success</Text>
                <Text style={{ fontSize: 9, color: THEME.error }}>{sr.failed} failed</Text>
              </View>
            </View>
          ))}
        </View>

        {/* Active Sessions */}
        <View style={[glass as any, { flex: isWide ? 1 : undefined }]} testID="sso-active-sessions">
          <Text style={{ fontSize: 15, fontWeight: '800', color: THEME.text, marginBottom: 16 }}>{tx('admin.sSOAnalyticsPanel.auto.text.009', 'Users by Provider')}</Text>
          {data.active_sessions.map((sess: any) => {
            const total = data.total_users || 1;
            const pct = Math.round((sess.count / total) * 100);
            return (
              <TouchableOpacity key={sess.provider} style={{ flexDirection: 'row', alignItems: 'center', gap: 12, paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: THEME.border }}  accessibilityLabel={tx('admin.sSOAnalyticsPanel.auto.accessibility.001', 'PROVIDER_LABELS[sess.provider]')}>
                <View style={{ width: 40, height: 40, borderRadius: 12, backgroundColor: (globalThis as any).__alphaColor(sess.color, '18'), alignItems: 'center', justifyContent: 'center' }}>
                  <Ionicons name={PROVIDER_ICONS[sess.provider] as any} size={20} color={sess.color} />
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={{ fontSize: 13, fontWeight: '700', color: THEME.text }}>{PROVIDER_LABELS[sess.provider]}</Text>
                  <View style={{ height: 4, backgroundColor: THEME.border, borderRadius: 2, marginTop: 4, overflow: 'hidden' }}>
                    <View style={{ width: `${pct}%`, height: '100%', backgroundColor: sess.color, borderRadius: 2 }} />
                  </View>
                </View>
                <View style={{ alignItems: 'flex-end' }}>
                  <Text style={{ fontSize: 18, fontWeight: '900', color: THEME.text }}>{sess.count}</Text>
                  <Text style={{ fontSize: 9, color: THEME.textMuted }}>{pct}%</Text>
                </View>
              </TouchableOpacity>
            );
          })}
        </View>
      </View>

      {/* Peak Hours Heatmap */}
      <View style={glass as any} testID="sso-peak-hours">
        <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
          <View>
            <Text style={{ fontSize: 15, fontWeight: '800', color: THEME.text }}>{tx('admin.sSOAnalyticsPanel.auto.text.010', 'Peak Sign-in Hours (7d)')}</Text>
            <Text style={{ fontSize: 11, color: THEME.textMuted, marginTop: 2 }}>{tx('admin.sSOAnalyticsPanel.auto.text.011', 'UTC timezone - darker = more activity')}</Text>
          </View>
          <View style={{ flexDirection: 'row', gap: 4, alignItems: 'center' }}>
            <View style={{ width: 12, height: 12, borderRadius: 3, backgroundColor: colors.borderStrong || colors.border }} />
            <Text style={{ fontSize: 9, color: THEME.textMuted }}>{tx('admin.sSOAnalyticsPanel.auto.text.012', 'Low')}</Text>
            <View style={{ width: 12, height: 12, borderRadius: 3, backgroundColor: colors.purpleSoft }} />
            <View style={{ width: 12, height: 12, borderRadius: 3, backgroundColor: colors.indigo }} />
            <View style={{ width: 12, height: 12, borderRadius: 3, backgroundColor: colors.primary }} />
            <Text style={{ fontSize: 9, color: THEME.textMuted }}>{tx('admin.sSOAnalyticsPanel.auto.text.013', 'High')}</Text>
          </View>
        </View>
        <HourHeatmap data={data.peak_hours} maxCount={data.max_hour_count} />
      </View>
    </View>
  );
}
