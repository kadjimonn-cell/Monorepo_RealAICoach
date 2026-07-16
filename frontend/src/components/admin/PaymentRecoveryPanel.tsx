import React, { useEffect, useState, useCallback } from 'react';
import { View, Text, TouchableOpacity, ScrollView, ActivityIndicator, Platform } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';

import { useAdminTheme } from '../../hooks/useAdminTheme';
import { useTranslation } from '../../hooks/useTranslation';
const AC = {
  bg: 'var(--app-bg)' as any, bgAlt: 'var(--app-surface)' as any, card: 'var(--app-card-bg)' as any, surface: 'var(--app-surface)' as any, surfaceHover: 'var(--app-surface-hover)' as any, border: 'var(--app-border)' as any, borderStrong: 'var(--app-border-strong)' as any,
  text: 'var(--app-text)' as any, textSec: 'var(--app-text-sec)' as any, textMuted: 'var(--app-text-muted)' as any, textDim: 'var(--app-text-muted)' as any,
  primary: 'var(--app-primary)' as any, success: 'var(--app-success)' as any, warning: 'var(--app-warning)' as any, error: 'var(--app-error)' as any,
};
interface RecoveryStats {
  overview: {
    total_tokens: number;
    active: number;
    recovered: number;
    expired: number;
    recovery_rate: number;
    revenue_saved_usd: number;
    revenue_at_risk_usd: number;
    total_emails_sent: number;
  };
  by_stage: { day1: number; day3: number; day7: number };
  by_method: Record<string, number>;
  by_currency: { currency: string; count: number; total_usd: number }[];
  recent_tokens: {
    token: string; user_id: string; plan_id: string; currency: string;
    amount_usd: number; status: string; emails_sent: number;
    created_at: string; recovered: boolean;
  }[];
}

const tx = (_key: string, fallback: string) => fallback;

function StatCard({ label, value, sub, color, icon, colors }: any) {
  return (
    <View data-testid={`recovery-stat-${label.toLowerCase().replace(/\s/g, '-')}`} testID={`recovery-stat-${label.toLowerCase().replace(/\s/g, '-')}`} style={{
      flex: 1, minWidth: 160, backgroundColor: colors?.card || AC.border,
      borderRadius: 12, padding: 16, borderWidth: 1,
      borderColor: colors?.border || 'rgba(148,163,184,0.1)',
      ...(Platform.OS === 'web' ? { boxShadow: '0 2px 8px rgba(0,0,0,0.08)' } as any : {}),
    }}>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 8 }}>
        <View style={{ width: 32, height: 32, borderRadius: 8, backgroundColor: `${color}18`, alignItems: 'center', justifyContent: 'center' }}>
          <Ionicons name={icon} size={16} color={color} />
        </View>
        <Text style={{ fontSize: 12, fontWeight: '500', color: colors?.textMuted || AC.textMuted }}>{label}</Text>
      </View>
      <Text style={{ fontSize: 24, fontWeight: '700', color: colors?.text || AC.text, marginBottom: 2 }}>{value}</Text>
      {sub && <Text style={{ fontSize: 11, color: colors?.textMuted || AC.textMuted }}>{sub}</Text>}
    </View>
  );
}

function StageBar({ stage, count, total, color, colors }: any) {
  const pct = total > 0 ? (count / total) * 100 : 0;
  return (
    <View style={{ marginBottom: 12 }}>
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginBottom: 4 }}>
        <Text style={{ fontSize: 13, fontWeight: '600', color: colors?.text || AC.text }}>{stage}</Text>
        <Text style={{ fontSize: 13, fontWeight: '600', color }}>{count} recovered ({pct.toFixed(0)}%)</Text>
      </View>
      <View style={{ height: 8, borderRadius: 4, backgroundColor: colors?.border || 'rgba(148,163,184,0.1)' }}>
        <View style={{ height: 8, borderRadius: 4, backgroundColor: color, width: `${Math.min(pct, 100)}%` } as any} />
      </View>
    </View>
  );
}

export default function PaymentRecoveryPanel({ colors }: { colors: any }) {
  const { t } = useTranslation();
  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };

  const AC = useAdminTheme();
  const [stats, setStats] = useState<RecoveryStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const fetchStats = useCallback(async () => {
    try {
      setLoading(true);
      setError('');
      const { data } = await api.get('/subscriptions/recovery-stats');
      setStats(data);
    } catch (e: any) {
      setError(e?.response?.data?.error || 'Failed to load recovery stats');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchStats(); }, [fetchStats]);

  if (loading) {
    return (
      <View style={{ padding: 40, alignItems: 'center' }}>
        <ActivityIndicator size="large" color={'var(--app-primary)'} />
        <Text style={{ color: colors?.textMuted || AC.textMuted, marginTop: 12 }}>{tx('admin.paymentRecoveryPanel.auto.text.001', 'Loading recovery analytics...')}</Text>
      </View>
    );
  }

  if (error || !stats) {
    return (
      <View style={{ padding: 24 }}>
        <Text style={{ color: colors.error, fontSize: 14, marginBottom: 12 }}>{error || 'No data available'}</Text>
        <TouchableOpacity onPress={fetchStats} style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }} accessibilityLabel={tx('admin.paymentRecoveryPanel.auto.accessibility.001', 'Retry')}>
          <Ionicons name="refresh" size={16} color={'var(--app-primary)'} />
          <Text style={{ color: colors.accent, fontWeight: '600' }}>{tx('admin.paymentRecoveryPanel.auto.text.002', 'Retry')}</Text>
        </TouchableOpacity>
      </View>
    );
  }

  const { overview, by_stage, by_method, by_currency, recent_tokens } = stats;
  const totalRecovered = by_stage.day1 + by_stage.day3 + by_stage.day7;

  return (
    <ScrollView style={{ flex: 1 }} contentContainerStyle={{ padding: 20, gap: 20 }}>
      {/* Header */}
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
        <View>
          <Text data-testid="recovery-panel-title" testID="recovery-panel-title" style={{ fontSize: 20, fontWeight: '700', color: colors?.text || AC.text }}>{tx('admin.paymentRecoveryPanel.auto.text.003', 'Payment Recovery Analytics')}</Text>
          <Text style={{ fontSize: 13, color: colors?.textMuted || AC.textMuted, marginTop: 2 }}>{tx('admin.paymentRecoveryPanel.auto.text.004', 'Automated failure recovery with escalating emails')}</Text>
        </View>
        <TouchableOpacity onPress={fetchStats} data-testid="recovery-refresh-btn" testID="recovery-refresh-btn" style={{
          flexDirection: 'row', alignItems: 'center', gap: 6,
          backgroundColor: 'rgba(45,212,191,0.1)', paddingHorizontal: 14, paddingVertical: 8, borderRadius: 8,
        }}>
          <Ionicons name="refresh" size={14} color={'var(--app-primary)'} />
          <Text style={{ color: colors.accent, fontWeight: '600', fontSize: 13 }}>{tx('admin.paymentRecoveryPanel.auto.text.005', 'Refresh')}</Text>
        </TouchableOpacity>
      </View>

      {/* KPI Cards */}
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 12 }}>
        <StatCard label="Recovery Rate" value={`${overview.recovery_rate}%`} sub={`${overview.recovered} of ${overview.total_tokens} recovered`} color={'var(--app-success)'} icon="trending-up" colors={colors} />
        <StatCard label="Revenue Saved" value={`$${overview.revenue_saved_usd.toLocaleString()}`} sub="Total recovered payments" color={'var(--app-primary)'} icon="cash" colors={colors} />
        <StatCard label="Revenue at Risk" value={`$${overview.revenue_at_risk_usd.toLocaleString()}`} sub={`${overview.active} active recovery tokens`} color={'var(--app-warning)'} icon="alert-circle" colors={colors} />
        <StatCard label="Emails Sent" value={overview.total_emails_sent.toString()} sub="Across all recovery stages" color={'var(--app-primary)'} icon="mail" colors={colors} />
      </View>

      {/* Recovery by Email Stage */}
      <View style={{
        backgroundColor: colors?.card || AC.border, borderRadius: 12, padding: 20,
        borderWidth: 1, borderColor: colors?.border || 'rgba(148,163,184,0.1)',
      }}>
        <Text style={{ fontSize: 16, fontWeight: '700', color: colors?.text || AC.text, marginBottom: 16 }}>{tx('admin.paymentRecoveryPanel.auto.text.006', 'Recovery by Email Stage')}</Text>
        <StageBar stage="Day 1 - Immediate" count={by_stage.day1} total={totalRecovered || 1} color={'var(--app-success)'} colors={colors} />
        <StageBar stage="Day 3 - Reminder" count={by_stage.day3} total={totalRecovered || 1} color={'var(--app-warning)'} colors={colors} />
        <StageBar stage="Day 7 - Final Warning" count={by_stage.day7} total={totalRecovered || 1} color={'var(--app-error)'} colors={colors} />
        <Text style={{ fontSize: 11, color: colors?.textMuted || AC.textMuted, marginTop: 8 }}>{tx('admin.paymentRecoveryPanel.auto.text.007', 'Typically, 60-70% of recoveries happen at Day 1, 20% at Day 3, and 10% at Day 7.')}</Text>
      </View>

      {/* Recovery by Payment Method & Currency */}
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 12 }}>
        {/* By Method */}
        <View style={{
          flex: 1, minWidth: 250, backgroundColor: colors?.card || AC.border, borderRadius: 12, padding: 20,
          borderWidth: 1, borderColor: colors?.border || 'rgba(148,163,184,0.1)',
        }}>
          <Text style={{ fontSize: 16, fontWeight: '700', color: colors?.text || AC.text, marginBottom: 12 }}>{tx('admin.paymentRecoveryPanel.auto.text.008', 'By Payment Method')}</Text>
          {Object.keys(by_method).length === 0 ? (
            <Text style={{ color: colors?.textMuted || AC.textMuted, fontSize: 13 }}>{tx('admin.paymentRecoveryPanel.auto.text.009', 'No recovered payments yet')}</Text>
          ) : (
            Object.entries(by_method).map(([method, count]) => (
              <View key={method} style={{ flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 8, borderBottomWidth: 1, borderBottomColor: colors?.border || 'rgba(148,163,184,0.06)' }}>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                  <Ionicons name={method === 'stripe' ? 'card' : method === 'paypal' ? 'logo-paypal' : 'wallet'} size={14} color={'var(--app-primary)'} />
                  <Text style={{ color: colors?.text || AC.text, fontWeight: '600', fontSize: 14, textTransform: 'capitalize' }}>{method}</Text>
                </View>
                <Text style={{ color: colors.successText, fontWeight: '700', fontSize: 14 }}>{count as number}</Text>
              </View>
            ))
          )}
        </View>

        {/* By Currency */}
        <View style={{
          flex: 1, minWidth: 250, backgroundColor: colors?.card || AC.border, borderRadius: 12, padding: 20,
          borderWidth: 1, borderColor: colors?.border || 'rgba(148,163,184,0.1)',
        }}>
          <Text style={{ fontSize: 16, fontWeight: '700', color: colors?.text || AC.text, marginBottom: 12 }}>{tx('admin.paymentRecoveryPanel.auto.text.010', 'By Currency')}</Text>
          {by_currency.length === 0 ? (
            <Text style={{ color: colors?.textMuted || AC.textMuted, fontSize: 13 }}>{tx('admin.paymentRecoveryPanel.auto.text.011', 'No recovered payments yet')}</Text>
          ) : (
            by_currency.map(c => (
              <View key={c.currency} style={{ flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 8, borderBottomWidth: 1, borderBottomColor: colors?.border || 'rgba(148,163,184,0.06)' }}>
                <Text style={{ color: colors?.text || AC.text, fontWeight: '600', fontSize: 14 }}>{c.currency}</Text>
                <View style={{ alignItems: 'flex-end' }}>
                  <Text style={{ color: colors.successText, fontWeight: '700', fontSize: 14 }}>{c.count} recovered</Text>
                  <Text style={{ color: colors?.textMuted || AC.textMuted, fontSize: 11 }}>${c.total_usd.toLocaleString()} USD</Text>
                </View>
              </View>
            ))
          )}
        </View>
      </View>

      {/* Recent Recovery Tokens */}
      <View style={{
        backgroundColor: colors?.card || AC.border, borderRadius: 12, padding: 20,
        borderWidth: 1, borderColor: colors?.border || 'rgba(148,163,184,0.1)',
      }}>
        <Text style={{ fontSize: 16, fontWeight: '700', color: colors?.text || AC.text, marginBottom: 12 }}>{tx('admin.paymentRecoveryPanel.auto.text.012', 'Recent Recovery Tokens')}</Text>
        {recent_tokens.length === 0 ? (
          <View style={{ alignItems: 'center', paddingVertical: 24 }}>
            <Ionicons name="checkmark-circle" size={40} color={'var(--app-success)'} />
            <Text style={{ color: colors?.textMuted || AC.textMuted, marginTop: 8, fontSize: 14 }}>{tx('admin.paymentRecoveryPanel.auto.text.013', 'No payment failures yet')}</Text>
          </View>
        ) : (
          recent_tokens.map((t, i) => (
            <View key={t.token} data-testid={`recovery-token-${i}`} testID={`recovery-token-${i}`} style={{
              flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center',
              paddingVertical: 10, borderBottomWidth: i < recent_tokens.length - 1 ? 1 : 0,
              borderBottomColor: colors?.border || 'rgba(148,163,184,0.06)',
            }}>
              <View style={{ flex: 1 }}>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                  <Text style={{ fontSize: 13, fontWeight: '600', color: colors?.text || AC.text }}>
                    {t.plan_id?.charAt(0).toUpperCase() + t.plan_id?.slice(1)} Plan
                  </Text>
                  <View style={{
                    paddingHorizontal: 8, paddingVertical: 2, borderRadius: 10,
                    backgroundColor: t.recovered ? 'rgba(16,185,129,0.15)' : t.status === 'expired' ? 'rgba(239,68,68,0.15)' : 'rgba(245,158,11,0.15)',
                  }}>
                    <Text style={{
                      fontSize: 10, fontWeight: '700', textTransform: 'uppercase',
                      color: t.recovered ? 'var(--app-success)' : t.status === 'expired' ? 'var(--app-error)' : 'var(--app-warning)',
                    }}>
                      {t.recovered ? 'Recovered' : t.status === 'expired' ? 'Expired' : 'Active'}
                    </Text>
                  </View>
                </View>
                <Text style={{ fontSize: 11, color: colors?.textMuted || AC.textMuted, marginTop: 2 }}>
                  {t.currency} ${t.amount_usd.toFixed(2)} via {t.token?.slice(0, 16)}...
                </Text>
              </View>
              <View style={{ alignItems: 'flex-end' }}>
                <Text style={{ fontSize: 12, fontWeight: '600', color: colors?.text || AC.text }}>
                  {t.emails_sent} email{t.emails_sent !== 1 ? 's' : ''}
                </Text>
                <Text style={{ fontSize: 10, color: colors?.textMuted || AC.textMuted }}>
                  {new Date(t.created_at).toLocaleDateString()}
                </Text>
              </View>
            </View>
          ))
        )}
      </View>
    </ScrollView>
  );
}
