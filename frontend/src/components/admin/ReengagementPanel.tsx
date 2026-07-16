import React, { useMemo, useState } from 'react';
import { View, Text, TouchableOpacity, ScrollView, ActivityIndicator, Platform } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { useTheme } from '../../context/ThemeContext';
import { useLiveQuery } from '../../hooks/useLiveQuery';
import { useTranslation } from '../../hooks/useTranslation';
import AutoFixBanner from './AutoFixBanner';
import { handleAppRecoverableError } from '../../utils/appRecoverableError';

const tx = (_key: string, fallback: string) => fallback;

const TIER_COLORS: Record<string, string> = { tier1: 'var(--app-primary)', tier2: 'var(--app-warning)', tier3: 'var(--app-error)' };
const TIER_ICONS: Record<string, string> = { tier1: 'notifications-outline', tier2: 'warning-outline', tier3: 'gift-outline' };

interface Analytics {
  buckets: Record<string, number>;
  email_trend: { week: string; tier1: number; tier2: number; tier3: number; total: number }[];
  tier_stats: { id: string; label: string; color: string; days: number; sent: number }[];
  promo_stats: { total: number; redeemed: number };
  return_rate: number;
  returned_users: number;
  total_sent_90d: number;
  recent_emails: any[];
  at_risk_users: any[];
  dau_trend: { date: string; count: number }[];
}

export default function ReengagementPanel({ colors: propColors }: { colors: any }) {
  const { t } = useTranslation();
  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };

  const { colors: themeColors } = useTheme();
  const colors = propColors || themeColors;
  const { data, loading, refetch: fetchData } = useLiveQuery<Analytics>('/reengagement/analytics', { entity: 'reengagement', pollInterval: 60000 });
  const [sending, setSending] = useState<string | null>(null);
  const [previewHtml, setPreviewHtml] = useState('');
  const [previewTier, setPreviewTier] = useState('tier2');
  const [showPreview, setShowPreview] = useState(false);

  const palette = useMemo(() => ({
    page: colors.bg || colors.background,
    card: colors.surface,
    cardAlt: colors.surfaceHover,
    border: colors.border,
    text: colors.text,
    textSec: colors.textSec,
    textMuted: colors.textMuted,
    primaryText: colors.primaryText,
    success: colors.success,
    warning: colors.warning,
    error: colors.error,
    overlay: colors.overlay || 'rgba(15,23,42,0.58)',
  }), [colors]);

  const handleManualSend = async (userId: string, tier: string) => {
    setSending(userId);
    try {
      await api.post('/reengagement/send-manual', { user_id: userId, tier });
      await fetchData();
    } catch (error) { handleAppRecoverableError({ scope: 'src/components/admin/ReengagementPanel.tsx#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); } finally {
      setSending(null);
    }
  };

  const handlePreview = async (tier: string) => {
    try {
      const response = await api.get(`/reengagement/preview-email?tier=${tier}`);
      setPreviewHtml(response.data.html);
      setPreviewTier(tier);
      setShowPreview(true);
    } catch (error) { handleAppRecoverableError({ scope: 'src/components/admin/ReengagementPanel.tsx#catch2', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
  };

  if (loading) {
    return (
      <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center', padding: 60 }}>
        <ActivityIndicator size="large" color={TIER_COLORS.tier1} />
        <Text style={{ color: palette.textMuted, fontSize: 13, marginTop: 12 }}>{tx('admin.reengagementPanel.auto.text.001', 'Loading analytics...')}</Text>
      </View>
    );
  }

  if (!data) {
    return null;
  }

  const buckets = data.buckets;
  const maxDau = Math.max(...data.dau_trend.map((day) => day.count), 1);
  const maxEmail = Math.max(...data.email_trend.map((week) => week.total), 1);

  return (
    <ScrollView style={{ flex: 1 }} contentContainerStyle={{ padding: 16, paddingBottom: 40 }} data-testid="reengagement-panel" testID="reengagement-panel">
      <AutoFixBanner domain="reengagement" />

      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 20, flexWrap: 'wrap', gap: 10 }}>
        <View>
          <Text style={{ fontSize: 20, fontWeight: '800', color: palette.text, letterSpacing: -0.4 }}>{tx('admin.reengagementPanel.auto.text.002', 'User Re-engagement')}</Text>
          <Text style={{ fontSize: 12, color: palette.textMuted, marginTop: 2 }}>{tx('admin.reengagementPanel.auto.text.003', 'Multi-tier automated outreach with win-back offers')}</Text>
        </View>

        <View style={{ flexDirection: 'row', gap: 8, flexWrap: 'wrap' }}>
          {[{ t: 'tier1', l: '30d' }, { t: 'tier2', l: '60d' }, { t: 'tier3', l: '90d' }].map((preview) => (
            <TouchableOpacity
              key={preview.t}
              onPress={() => { void handlePreview(preview.t); }}
              style={{ flexDirection: 'row', alignItems: 'center', gap: 5, paddingHorizontal: 12, paddingVertical: 7, borderRadius: 10, backgroundColor: `${TIER_COLORS[preview.t]}12`, borderWidth: 1, borderColor: `${TIER_COLORS[preview.t]}30` }}
              data-testid={`reengagement-preview-${preview.t}`}
              testID={`reengagement-preview-${preview.t}`}
            >
              <Ionicons name="eye" size={12} color={TIER_COLORS[preview.t]} />
              <Text style={{ fontSize: 11, fontWeight: '700', color: TIER_COLORS[preview.t] }}>Preview {preview.l}</Text>
            </TouchableOpacity>
          ))}

          <TouchableOpacity
            onPress={() => { void fetchData(); }}
            style={{ flexDirection: 'row', alignItems: 'center', gap: 5, paddingHorizontal: 12, paddingVertical: 7, borderRadius: 10, backgroundColor: `${palette.success}15`, borderWidth: 1, borderColor: `${palette.success}24` }}
            data-testid="reengagement-refresh-btn"
            testID="reengagement-refresh-btn"
          >
            <Ionicons name="refresh" size={12} color={palette.successText} />
            <Text style={{ fontSize: 11, fontWeight: '700', color: palette.successText }}>{tx('admin.reengagementPanel.auto.text.004', 'Refresh')}</Text>
          </TouchableOpacity>
        </View>
      </View>

      <View style={{ flexDirection: 'row', gap: 10, marginBottom: 20, flexWrap: 'wrap' }}>
        {data.tier_stats.map((tier) => (
          <StatCard key={tier.id} accent={tier.color} palette={palette} testId={`reengagement-tier-${tier.id}`}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 8 }}>
              <View style={{ width: 28, height: 28, borderRadius: 8, backgroundColor: `${tier.color}15`, alignItems: 'center', justifyContent: 'center' }}>
                <Ionicons name={TIER_ICONS[tier.id] as any} size={14} color={tier.color} />
              </View>
              <View>
                <Text style={{ fontSize: 10, fontWeight: '800', color: tier.color, textTransform: 'uppercase', letterSpacing: 0.5 }}>{tier.label}</Text>
                <Text style={{ fontSize: 9, color: palette.textMuted }}>{tier.days}+ days inactive</Text>
              </View>
            </View>
            <Text style={{ fontSize: 28, fontWeight: '900', color: tier.color }}>{tier.sent}</Text>
            <Text style={{ fontSize: 10, color: palette.textMuted, marginTop: 2 }}>{tx('admin.reengagementPanel.auto.text.005', 'emails sent')}</Text>
          </StatCard>
        ))}

        <StatCard accent="var(--app-primary)" palette={palette} testId="reengagement-promo-stats">
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 8 }}>
            <View style={{ width: 28, height: 28, borderRadius: 8, backgroundColor: colors.accentSoft, alignItems: 'center', justifyContent: 'center' }}>
              <Ionicons name="ticket" size={14} color={'var(--app-primary)'} />
            </View>
            <View>
              <Text style={{ fontSize: 10, fontWeight: '800', color: colors.accent, textTransform: 'uppercase', letterSpacing: 0.5 }}>{tx('admin.reengagementPanel.auto.text.006', 'Win-Back Promos')}</Text>
              <Text style={{ fontSize: 9, color: palette.textMuted }}>{tx('admin.reengagementPanel.auto.text.007', '1 Month Free Premium')}</Text>
            </View>
          </View>
          <Text style={{ fontSize: 28, fontWeight: '900', color: colors.accent }}>{data.promo_stats.total}</Text>
          <Text style={{ fontSize: 10, color: palette.textMuted, marginTop: 2 }}>{data.promo_stats.redeemed} redeemed</Text>
        </StatCard>
      </View>

      <View style={{ flexDirection: 'row', gap: 10, marginBottom: 20, flexWrap: 'wrap' }}>
        {[
          { label: 'Total Users', value: buckets.total_users, color: colors.primary, icon: 'people' },
          { label: 'Active (30d)', value: buckets.active_30d, color: palette.successText, icon: 'pulse' },
          { label: 'Inactive (30d+)', value: buckets.inactive_30d, color: palette.warningText, icon: 'warning' },
          { label: 'Inactive (90d+)', value: buckets.inactive_90d, color: palette.error, icon: 'alert-circle' },
          { label: 'Emails Sent (90d)', value: data.total_sent_90d, color: colors.accent, icon: 'mail' },
          { label: 'Return Rate', value: `${data.return_rate}%`, color: colors.accent, icon: 'trending-up' },
        ].map((item) => (
          <View key={item.label} style={{ flex: 1, minWidth: 130, padding: 14, borderRadius: 12, backgroundColor: palette.card, borderWidth: 1, borderColor: palette.border }} data-testid={`reengagement-stat-${item.label.toLowerCase().replace(/[^a-z0-9]/g, '-')}`} testID={`reengagement-stat-${item.label.toLowerCase().replace(/[^a-z0-9]/g, '-')}`}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 5, marginBottom: 6 }}>
              <Ionicons name={item.icon as any} size={12} color={item.color} />
              <Text style={{ fontSize: 9, fontWeight: '700', color: palette.textMuted, textTransform: 'uppercase', letterSpacing: 0.5 }}>{item.label}</Text>
            </View>
            <Text style={{ fontSize: 20, fontWeight: '900', color: item.color }}>{item.value}</Text>
          </View>
        ))}
      </View>

      <PanelCard title="User Activity Funnel" palette={palette} testId="reengagement-funnel">
        {[
          { label: 'Total Registered', value: buckets.total_users, pct: 100, color: colors.primary },
          { label: 'Active Last 7 Days', value: buckets.active_7d, pct: buckets.total_users > 0 ? Math.round((buckets.active_7d / buckets.total_users) * 100) : 0, color: palette.successText },
          { label: 'Active Last 14 Days', value: buckets.active_14d, pct: buckets.total_users > 0 ? Math.round((buckets.active_14d / buckets.total_users) * 100) : 0, color: colors.accent },
          { label: 'Active Last 30 Days', value: buckets.active_30d, pct: buckets.total_users > 0 ? Math.round((buckets.active_30d / buckets.total_users) * 100) : 0, color: colors.accent },
          { label: 'Tier 1 Zone (30d+)', value: buckets.inactive_30d, pct: buckets.total_users > 0 ? Math.round((buckets.inactive_30d / buckets.total_users) * 100) : 0, color: colors.primary },
          { label: 'Tier 2 Zone (60d+)', value: buckets.inactive_60d, pct: buckets.total_users > 0 ? Math.round((buckets.inactive_60d / buckets.total_users) * 100) : 0, color: palette.warningText },
          { label: 'Tier 3 Zone (90d+)', value: buckets.inactive_90d, pct: buckets.total_users > 0 ? Math.round((buckets.inactive_90d / buckets.total_users) * 100) : 0, color: palette.error },
        ].map((item, index) => (
          <View key={item.label} style={{ marginBottom: index < 6 ? 10 : 0 }}>
            <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginBottom: 5 }}>
              <Text style={{ fontSize: 12, fontWeight: '600', color: palette.text }}>{item.label}</Text>
              <Text style={{ fontSize: 12, fontWeight: '800', color: item.color }}>{item.value} ({item.pct}%)</Text>
            </View>
            <View style={{ height: 8, borderRadius: 4, backgroundColor: palette.cardAlt, overflow: 'hidden' }}>
              <View style={{ height: '100%' as any, width: `${Math.max(item.pct, 1)}%` as any, borderRadius: 4, backgroundColor: item.color }} />
            </View>
          </View>
        ))}
      </PanelCard>

      <View style={{ flexDirection: 'row', gap: 14, marginBottom: 20, flexWrap: 'wrap' }}>
        <PanelCard title="Daily Active Users" palette={palette} testId="reengagement-dau-chart" style={{ flex: 1, minWidth: 280 }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
            <View />
            <View style={{ paddingHorizontal: 8, paddingVertical: 3, borderRadius: 6, backgroundColor: `${palette.success}15` }}>
              <Text style={{ fontSize: 9, fontWeight: '800', color: palette.successText }}>{tx('admin.reengagementPanel.auto.text.008', 'LAST 30 DAYS')}</Text>
            </View>
          </View>
          <View style={{ flexDirection: 'row', alignItems: 'flex-end', gap: 2, height: 100 }}>
            {data.dau_trend.map((day, index) => (
              <View key={index} style={{ flex: 1, alignItems: 'center' }}>
                <View style={{ width: '80%' as any, backgroundColor: colors.primary, height: Math.max(maxDau > 0 ? (day.count / maxDau) * 80 : 2, 2), borderRadius: 3, opacity: day.count > 0 ? 1 : 0.15 }} />
              </View>
            ))}
          </View>
          <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginTop: 6 }}>
            <Text style={{ fontSize: 9, color: palette.textMuted }}>{data.dau_trend[0]?.date}</Text>
            <Text style={{ fontSize: 9, color: palette.textMuted }}>{data.dau_trend[data.dau_trend.length - 1]?.date}</Text>
          </View>
        </PanelCard>

        <PanelCard title="Emails by Tier" palette={palette} testId="reengagement-email-chart" style={{ flex: 1, minWidth: 280 }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
            <View style={{ flexDirection: 'row', gap: 12, flexWrap: 'wrap' }}>
              {[{ id: 'tier1', l: '30d', c: 'var(--app-primary)' }, { id: 'tier2', l: '60d', c: palette.warning }, { id: 'tier3', l: '90d', c: palette.error }].map((tier) => (
                <View key={tier.id} style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}>
                  <View style={{ width: 8, height: 8, borderRadius: 2, backgroundColor: tier.c }} />
                  <Text style={{ fontSize: 9, color: palette.textMuted }}>{tier.l}</Text>
                </View>
              ))}
            </View>
            <View style={{ paddingHorizontal: 8, paddingVertical: 3, borderRadius: 6, backgroundColor: colors.accentSoft }}>
              <Text style={{ fontSize: 9, fontWeight: '800', color: colors.accent }}>{tx('admin.reengagementPanel.auto.text.009', '12 WEEKS')}</Text>
            </View>
          </View>
          <View style={{ flexDirection: 'row', alignItems: 'flex-end', gap: 4, height: 100 }}>
            {data.email_trend.map((week, index) => (
              <View key={index} style={{ flex: 1, alignItems: 'center', justifyContent: 'flex-end', height: '100%' as any }}>
                <View style={{ width: '70%' as any }}>
                  {['tier3', 'tier2', 'tier1'].map((tierId) => {
                    const value = (week as any)[tierId] || 0;
                    const height = maxEmail > 0 ? (value / maxEmail) * 70 : 0;
                    return height > 0 ? <View key={tierId} style={{ height, backgroundColor: TIER_COLORS[tierId], borderRadius: tierId === 'tier1' ? 3 : 0, ...(tierId === 'tier3' ? { borderTopLeftRadius: 3, borderTopRightRadius: 3 } : {}) }} /> : null;
                  })}
                  {week.total === 0 ? <View style={{ height: 2, backgroundColor: palette.border, borderRadius: 1, opacity: 0.3 }} /> : null}
                </View>
              </View>
            ))}
          </View>
          <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginTop: 6 }}>
            <Text style={{ fontSize: 9, color: palette.textMuted }}>{data.email_trend[0]?.week}</Text>
            <Text style={{ fontSize: 9, color: palette.textMuted }}>{data.email_trend[data.email_trend.length - 1]?.week}</Text>
          </View>
        </PanelCard>
      </View>

      <View style={{ flexDirection: 'row', gap: 14, marginBottom: 20, flexWrap: 'wrap' }}>
        <PanelCard title="Re-engagement Success (90d)" palette={palette} testId="reengagement-return-rate" style={{ flex: 2, minWidth: 280 }}>
          <View style={{ flexDirection: 'row', gap: 20, alignItems: 'center', flexWrap: 'wrap' }}>
            <View style={{ width: 100, height: 100, borderRadius: 50, borderWidth: 8, borderColor: palette.border, alignItems: 'center', justifyContent: 'center', ...(Platform.OS === 'web' ? { background: `conic-gradient(${palette.success} ${data.return_rate * 3.6}deg, ${palette.border} 0deg)` } as any : {}) }}>
              <View style={{ width: 76, height: 76, borderRadius: 38, backgroundColor: palette.card, alignItems: 'center', justifyContent: 'center' }}>
                <Text style={{ fontSize: 22, fontWeight: '900', color: palette.successText }}>{data.return_rate}%</Text>
              </View>
            </View>
            <View style={{ flex: 1, gap: 8 }}>
              {[
                { label: 'Emails sent (90d)', value: data.total_sent_90d, icon: 'mail-outline', color: colors.accent },
                { label: 'Users returned', value: data.returned_users, icon: 'arrow-undo-outline', color: palette.successText },
                { label: 'Promos generated', value: data.promo_stats.total, icon: 'ticket-outline', color: palette.warningText },
                { label: 'Promos redeemed', value: data.promo_stats.redeemed, icon: 'checkmark-done-outline', color: colors.primary },
              ].map((item) => (
                <View key={item.label} style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
                  <View style={{ width: 28, height: 28, borderRadius: 7, backgroundColor: `${item.color}12`, alignItems: 'center', justifyContent: 'center' }}>
                    <Ionicons name={item.icon as any} size={13} color={item.color} />
                  </View>
                  <View style={{ flex: 1 }}>
                    <Text style={{ fontSize: 10, color: palette.textMuted, textTransform: 'uppercase', letterSpacing: 0.4 }}>{item.label}</Text>
                    <Text style={{ fontSize: 15, fontWeight: '800', color: palette.text }}>{item.value}</Text>
                  </View>
                </View>
              ))}
            </View>
          </View>
        </PanelCard>
      </View>

      <PanelCard title="At-Risk Users" palette={palette} testId="reengagement-at-risk">
        <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14 }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
            <View style={{ width: 28, height: 28, borderRadius: 8, backgroundColor: `${palette.warning}15`, alignItems: 'center', justifyContent: 'center' }}>
              <Ionicons name="warning" size={14} color={palette.warningText} />
            </View>
            <Text style={{ fontSize: 14, fontWeight: '700', color: palette.text }}>{tx('admin.reengagementPanel.auto.text.010', 'At-Risk Users')}</Text>
          </View>
          <View style={{ paddingHorizontal: 10, paddingVertical: 4, borderRadius: 8, backgroundColor: `${palette.warning}15` }}>
            <Text style={{ fontSize: 12, fontWeight: '800', color: palette.warningText }}>{data.at_risk_users.length}</Text>
          </View>
        </View>

        {data.at_risk_users.length === 0 ? (
          <View style={{ padding: 24, alignItems: 'center' }}>
            <Ionicons name="checkmark-circle" size={32} color={palette.successText} />
            <Text style={{ fontSize: 13, fontWeight: '600', color: palette.textMuted, marginTop: 8 }}>{tx('admin.reengagementPanel.auto.text.011', 'No at-risk users right now')}</Text>
          </View>
        ) : (
          <View style={{ gap: 8 }}>
            {data.at_risk_users.map((user) => {
              const tierColor = TIER_COLORS[user.tier] || palette.border;
              return (
                <View key={`${user.user_id}-${user.tier}`} style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', padding: 12, borderRadius: 10, backgroundColor: palette.cardAlt, borderWidth: 1, borderColor: palette.border, borderLeftWidth: 3, borderLeftColor: tierColor }} data-testid={`at-risk-user-${user.user_id}`} testID={`at-risk-user-${user.user_id}`}>
                  <View style={{ flex: 1 }}>
                    <Text style={{ fontSize: 13, fontWeight: '700', color: palette.text }}>{user.name}</Text>
                    <Text style={{ fontSize: 11, color: palette.textMuted }}>{user.email}</Text>
                  </View>

                  <View style={{ paddingHorizontal: 8, paddingVertical: 3, borderRadius: 6, backgroundColor: `${tierColor}12`, marginRight: 8 }}>
                    <Text style={{ fontSize: 9, fontWeight: '800', color: tierColor }}>{user.tier_label}</Text>
                  </View>
                  <View style={{ paddingHorizontal: 6, paddingVertical: 3, borderRadius: 6, backgroundColor: `${palette.error}15`, marginRight: 8 }}>
                    <Text style={{ fontSize: 10, fontWeight: '800', color: palette.error }}>{user.days_inactive}d</Text>
                  </View>

                  {user.email_sent ? (
                    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4, paddingHorizontal: 10, paddingVertical: 6, borderRadius: 8, backgroundColor: `${palette.success}15` }}>
                      <Ionicons name="checkmark-circle" size={12} color={palette.successText} />
                      <Text style={{ fontSize: 10, fontWeight: '700', color: palette.successText }}>{tx('admin.reengagementPanel.auto.text.012', 'Sent')}</Text>
                    </View>
                  ) : (
                    <TouchableOpacity onPress={() => { void handleManualSend(user.user_id, user.tier); }} disabled={sending === user.user_id} style={{ flexDirection: 'row', alignItems: 'center', gap: 4, paddingHorizontal: 10, paddingVertical: 6, borderRadius: 8, backgroundColor: tierColor, opacity: sending === user.user_id ? 0.5 : 1 }} data-testid={`send-email-${user.user_id}`} testID={`send-email-${user.user_id}`}>
                      {sending === user.user_id ? <ActivityIndicator size="small" color={palette.primaryText} /> : <Ionicons name="mail" size={12} color={palette.primaryText} />}
                      <Text style={{ fontSize: 10, fontWeight: '700', color: palette.primaryText }}>{tx('admin.reengagementPanel.auto.text.013', 'Send')}</Text>
                    </TouchableOpacity>
                  )}
                </View>
              );
            })}
          </View>
        )}
      </PanelCard>

      <PanelCard title="Recent Email Log" palette={palette} testId="reengagement-email-log">
        {data.recent_emails.length === 0 ? (
          <View style={{ padding: 24, alignItems: 'center' }}>
            <Ionicons name="mail-open-outline" size={32} color={palette.textMuted} />
            <Text style={{ fontSize: 13, fontWeight: '600', color: palette.textMuted, marginTop: 8 }}>{tx('admin.reengagementPanel.auto.text.014', 'No emails sent yet')}</Text>
            <Text style={{ fontSize: 11, color: palette.textMuted, marginTop: 3 }}>{tx('admin.reengagementPanel.auto.text.015', 'Automated emails run daily at 9:30 AM UTC across 3 tiers')}</Text>
          </View>
        ) : (
          <View style={{ gap: 6 }}>
            {data.recent_emails.slice(0, 25).map((email: any, index: number) => {
              const tierColor = TIER_COLORS[email.tier] || palette.textMuted;
              return (
                <View key={index} style={{ flexDirection: 'row', alignItems: 'center', padding: 10, borderRadius: 8, backgroundColor: palette.cardAlt, borderWidth: 1, borderColor: palette.border, gap: 8, borderLeftWidth: 3, borderLeftColor: tierColor }}>
                  <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: email.success ? palette.success : palette.error }} />
                  <View style={{ flex: 1 }}>
                    <Text style={{ fontSize: 12, fontWeight: '600', color: palette.text }}>{email.email}</Text>
                  </View>
                  <View style={{ paddingHorizontal: 6, paddingVertical: 2, borderRadius: 4, backgroundColor: `${tierColor}12` }}>
                    <Text style={{ fontSize: 8, fontWeight: '800', color: tierColor }}>{email.tier_label || email.tier}</Text>
                  </View>
                  {email.promo_code ? (
                    <View style={{ paddingHorizontal: 6, paddingVertical: 2, borderRadius: 4, backgroundColor: colors.accentSoft }}>
                      <Text style={{ fontSize: 8, fontWeight: '700', color: colors.accent }}>{email.promo_code}</Text>
                    </View>
                  ) : null}
                  <View style={{ paddingHorizontal: 6, paddingVertical: 2, borderRadius: 4, backgroundColor: `${palette.warning}15` }}>
                    <Text style={{ fontSize: 9, fontWeight: '700', color: palette.warningText }}>{email.days_inactive}d</Text>
                  </View>
                  {email.manual ? (
                    <View style={{ paddingHorizontal: 5, paddingVertical: 2, borderRadius: 4, backgroundColor: colors.primarySoft }}>
                      <Text style={{ fontSize: 8, fontWeight: '700', color: colors.primary }}>{tx('admin.reengagementPanel.auto.text.016', 'Manual')}</Text>
                    </View>
                  ) : null}
                  <Text style={{ fontSize: 10, color: palette.textMuted }}>
                    {new Date(email.sent_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}
                  </Text>
                </View>
              );
            })}
          </View>
        )}
      </PanelCard>

      {showPreview && Platform.OS === 'web' ? (
        <View style={{ ...(Platform.OS === 'web' ? { position: 'fixed' as any, top: 0, left: 0, right: 0, bottom: 0, zIndex: 9999 } as any : {}), backgroundColor: palette.overlay, alignItems: 'center', justifyContent: 'center' }}>
          <View style={{ width: '90%' as any, maxWidth: 960, maxHeight: '85%' as any, backgroundColor: palette.card, borderRadius: 20, overflow: 'hidden', borderWidth: 1, borderColor: palette.border }}>
            <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', padding: 16, borderBottomWidth: 1, borderBottomColor: palette.border }}>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                <Text style={{ fontSize: 15, fontWeight: '700', color: palette.text }}>{tx('admin.reengagementPanel.auto.text.017', 'Email Preview')}</Text>
                <View style={{ paddingHorizontal: 8, paddingVertical: 3, borderRadius: 6, backgroundColor: `${TIER_COLORS[previewTier]}15` }}>
                  <Text style={{ fontSize: 10, fontWeight: '800', color: TIER_COLORS[previewTier] }}>{previewTier === 'tier1' ? '30d Gentle' : previewTier === 'tier2' ? '60d Urgent' : '90d Win-Back'}</Text>
                </View>
              </View>
              <TouchableOpacity onPress={() => setShowPreview(false)} data-testid="reengagement-close-preview" testID="reengagement-close-preview">
                <Ionicons name="close-circle" size={24} color={palette.textMuted} />
              </TouchableOpacity>
            </View>
            <ScrollView style={{ flex: 1 }}>
              <iframe
                sandbox=""
                srcDoc={previewHtml}
                title="reengagement-email-preview"
                data-testid="reengagement-email-preview-iframe"
                style={{ width: '100%', minHeight: 520, border: 'none', background: colors.surfaceHover || 'var(--app-primary-text)' }}
              />
            </ScrollView>
          </View>
        </View>
      ) : null}
    </ScrollView>
  );
}

function PanelCard({ title, palette, testId, children, style }: { title: string; palette: any; testId: string; children: React.ReactNode; style?: any }) {
  return (
    <View style={[{ marginBottom: 20, padding: 20, borderRadius: 16, backgroundColor: palette.card, borderWidth: 1, borderColor: palette.border }, style]} data-testid={testId} testID={testId}>
      <Text style={{ fontSize: 14, fontWeight: '700', color: palette.text, marginBottom: 14 }}>{title}</Text>
      {children}
    </View>
  );
}

function StatCard({ accent, palette, testId, children }: { accent: string; palette: any; testId: string; children: React.ReactNode }) {
  return (
    <View style={{ flex: 1, minWidth: 160, padding: 16, borderRadius: 14, backgroundColor: `${accent}08`, borderWidth: 1, borderColor: `${accent}20`, borderLeftWidth: 4, borderLeftColor: accent }} data-testid={testId} testID={testId}>
      {children}
    </View>
  );
}