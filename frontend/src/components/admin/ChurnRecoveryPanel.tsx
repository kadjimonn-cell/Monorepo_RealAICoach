import React, { useState } from 'react';
import { View, Text, TouchableOpacity, ActivityIndicator, useWindowDimensions } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { useExecTheme} from './ExecDashboardPanels';
import { useLiveQuery } from '../../hooks/useLiveQuery';
import AutoFixBanner from './AutoFixBanner';
import { useAdminTheme } from '../../hooks/useAdminTheme';
import { useTranslation } from '../../hooks/useTranslation';

/* ─── Mini Area Chart ─── */
function AreaChart({ data, color, height = 80 }: { data: { label: string; value: number }[]; color: string; height?: number }) {
  if (!data.length) return null;
  const max = Math.max(...data.map(d => d.value), 1);
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const _w = 100 / data.length;
  return (
    <View style={{ height, flexDirection: 'row', alignItems: 'flex-end', gap: 1 }}>
      {data.map((d, i) => (
        <View key={i} style={{ flex: 1, alignItems: 'center', justifyContent: 'flex-end', height: '100%' }}>
          <View style={{
            width: '80%', borderRadius: 3,
            height: `${Math.max((d.value / max) * 100, 4)}%`,
            backgroundColor: color + (d.value > 0 ? '60' : '15'),
          }} />
        </View>
      ))}
    </View>
  );
}

/* ─── Donut Ring ─── */
function DonutStat({ value, total, color, label, size = 80 }: any) {
  const T = useExecTheme();
  const pct = total > 0 ? (value / total) * 100 : 0;
  const circumference = 2 * Math.PI * 32;
  const offset = circumference - (pct / 100) * circumference;
  return (
    <View style={{ alignItems: 'center' }}>
      <svg width={size} height={size} viewBox="0 0 80 80">
        <circle cx="40" cy="40" r="32" fill="none" stroke={T.border} strokeWidth="6" />
        <circle cx="40" cy="40" r="32" fill="none" stroke={color} strokeWidth="6"
          strokeLinecap="round" strokeDasharray={circumference} strokeDashoffset={offset}
          transform="rotate(-90 40 40)" />
        <text x="40" y="37" textAnchor="middle" fill={T.text} fontSize="16" fontWeight="800">{Math.round(pct)}%</text>
        <text x="40" y="50" textAnchor="middle" fill={T.textMuted} fontSize="8">{value}/{total}</text>
      </svg>
      <Text style={{ color: T.textMuted, fontSize: 10, fontWeight: '600', marginTop: 4 }}>{label}</Text>
    </View>
  );
}

const STATUS_COLORS: Record<string, string> = {
  churned: 'var(--app-error)', // @theme-ok brand/role/state identifier
  winback_sent: 'var(--app-warning)', // @theme-ok brand/role/state identifier
  recovered: 'var(--app-success)', // @theme-ok brand/role/state identifier
  expired: 'var(--app-text)', // @theme-ok brand/role/state identifier
};

const STATUS_LABELS: Record<string, string> = {
  churned: 'Cancelled',
  winback_sent: 'Win-back Active',
  recovered: 'Recovered',
  expired: 'Campaign Ended',
};

export default function ChurnRecoveryPanel() {
  const { t } = useTranslation();
  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };

  const colors = useAdminTheme();
  const T = useExecTheme();
  const { data, loading, refetch: loadData } = useLiveQuery('/churn-recovery/admin/dashboard', { entity: 'churn', pollInterval: 60000 });
  const [activeAction, setActiveAction] = useState<string | null>(null);
  const [previewHtml, setPreviewHtml] = useState<string | null>(null);
  const [previewType, setPreviewType] = useState<string>('cancellation');
  const { width } = useWindowDimensions();
  const isMobile = width < 768;

  const sendWinback = async (churnId: string) => {
    setActiveAction(churnId);
    try {
      await api.post(`/churn-recovery/admin/send-winback/${churnId}`);
      loadData();
    } catch (e) { console.error(e); }
    setActiveAction(null);
  };

  const markRecovered = async (churnId: string) => {
    setActiveAction(churnId);
    try {
      await api.post(`/churn-recovery/admin/mark-recovered/${churnId}`);
      loadData();
    } catch (e) { console.error(e); }
    setActiveAction(null);
  };

  const previewEmail = async (type: string) => {
    try {
      const res = await api.get(`/churn-recovery/admin/email-preview/${type}`);
      setPreviewHtml(res.data.html);
      setPreviewType(type);
    } catch (e) { console.error(e); }
  };

  if (loading) return (
    <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center', padding: 60 }}>
      <AutoFixBanner domain="churn" />
      <ActivityIndicator size="large" color={T.primary} />
      <Text style={{ color: T.textMuted, fontSize: 12, marginTop: 12 }}>{tx('admin.churnRecoveryPanel.auto.text.001', 'Loading churn recovery data...')}</Text>
    </View>
  );

  const k = data?.kpis || {};
  const churnTrend = (data?.churn_trend || []).map((d: any) => ({ label: d.date, value: d.churns }));
  const recoveryTrend = (data?.recovery_trend || []).map((d: any) => ({ label: d.date, value: d.recoveries }));
  const funnel = data?.funnel || {};
  const users = data?.users || [];

  return (
    <View style={{ flex: 1 }} data-testid="churn-recovery-panel" testID="churn-recovery-panel">
      {/* Header */}
      <View style={{ flexDirection: isMobile ? 'column' : 'row', alignItems: isMobile ? 'flex-start' : 'center', justifyContent: 'space-between', marginBottom: 20, gap: 12 }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 12 }}>
          <View style={{ width: 40, height: 40, borderRadius: 12, backgroundColor: colors.errorSoft, alignItems: 'center', justifyContent: 'center' }}>
            <Ionicons name="heart-dislike" size={20} color={colors.error} />
          </View>
          <View>
            <Text style={{ color: T.text, fontSize: 18, fontWeight: '800', letterSpacing: -0.5 }}>{tx('admin.churnRecoveryPanel.auto.text.002', 'Churn Recovery')}</Text>
            <Text style={{ color: T.textMuted, fontSize: 11 }}>{tx('admin.churnRecoveryPanel.auto.text.003', 'Automated win-back campaigns & analytics')}</Text>
          </View>
        </View>
        <View style={{ flexDirection: 'row', gap: 8 }}>
          <TouchableOpacity
            onPress={() => previewEmail('cancellation')}
            style={{ flexDirection: 'row', alignItems: 'center', gap: 4, backgroundColor: (globalThis as any).__alphaColor(T.primary, '15'), paddingHorizontal: 12, paddingVertical: 7, borderRadius: 8, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(T.primary, '25') }}
            data-testid="preview-cancellation-email-btn" testID="preview-cancellation-email-btn">
            <Ionicons name="mail" size={13} color={T.primary} />
            <Text style={{ color: T.primary, fontSize: 11, fontWeight: '700' }}>{tx('admin.churnRecoveryPanel.auto.text.004', 'Preview Emails')}</Text>
          </TouchableOpacity>
          <TouchableOpacity
            onPress={loadData}
            style={{ flexDirection: 'row', alignItems: 'center', gap: 4, backgroundColor: T.bgSoft, paddingHorizontal: 12, paddingVertical: 7, borderRadius: 8, borderWidth: 1, borderColor: T.border }}
            data-testid="refresh-churn-btn" testID="refresh-churn-btn">
            <Ionicons name="refresh" size={13} color={T.textSec} />
            <Text style={{ color: T.textSec, fontSize: 11, fontWeight: '600' }}>{tx('admin.churnRecoveryPanel.auto.text.005', 'Refresh')}</Text>
          </TouchableOpacity>
        </View>
      </View>

      {/* Email Preview Modal */}
      {previewHtml && (
        <View style={{ backgroundColor: T.card, borderRadius: 16, padding: 16, marginBottom: 20, borderWidth: 1, borderColor: T.border }} data-testid="email-preview-modal" testID="email-preview-modal">
          <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
            <View style={{ flexDirection: 'row', gap: 8 }}>
              {['cancellation', 'reminder1', 'reminder3', 'reminder6'].map(t => (
                <TouchableOpacity key={t} accessibilityLabel={tx('admin.churnRecoveryPanel.auto.accessibility.001', 'Preview recovery email')}
                  onPress={() => previewEmail(t)}
                  style={{ paddingHorizontal: 10, paddingVertical: 5, borderRadius: 6, backgroundColor: previewType === t ? (globalThis as any).__alphaColor(T.primary, '20') : 'transparent', borderWidth: 1, borderColor: previewType === t ? (globalThis as any).__alphaColor(T.primary, '30') : T.border }}>
                  <Text style={{ color: previewType === t ? T.primary : T.textMuted, fontSize: 10, fontWeight: '700', textTransform: 'capitalize' }}>{t.replace('reminder', 'Reminder ')}</Text>
                </TouchableOpacity>
              ))}
            </View>
            <TouchableOpacity onPress={() => setPreviewHtml(null)} data-testid="close-email-preview" testID="close-email-preview">
              <Ionicons name="close" size={20} color={T.textMuted} />
            </TouchableOpacity>
          </View>
          <View style={{ borderRadius: 12, overflow: 'hidden', borderWidth: 1, borderColor: T.border, maxHeight: 400 }}>
            <iframe
              sandbox=""
              srcDoc={previewHtml}
              title="churn-email-preview"
              data-testid="churn-email-preview-iframe"
              style={{ width: '100%', height: 380, border: 'none', background: T.surfaceElevated || T.card }}
            />
          </View>
        </View>
      )}

      {/* KPI Cards */}
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10, marginBottom: 20 }} data-testid="churn-kpi-cards" testID="churn-kpi-cards">
        {[
          { label: 'Total Churned', value: k.total_churned, icon: 'person-remove' as const, color: colors.error, sub: `${k.recent_churns_30d || 0} in 30d` },
          { label: 'Recovered', value: k.recovered, icon: 'heart' as const, color: colors.successText, sub: `${k.recent_recovered_30d || 0} in 30d` },
          { label: 'Recovery Rate', value: `${k.recovery_rate || 0}%`, icon: 'trending-up' as const, color: colors.primary, sub: 'All time' },
          { label: 'Active Campaigns', value: k.active_campaigns, icon: 'mail-unread' as const, color: colors.warningText, sub: `${k.total_emails_sent || 0} emails sent` },
          { label: 'Revenue Recovered', value: `$${(k.estimated_recovered_revenue || 0).toLocaleString()}`, icon: 'wallet' as const, color: colors.purpleText, sub: 'Est. 3mo LTV' },
          { label: 'Codes Redeemed', value: k.codes_redeemed, icon: 'pricetag' as const, color: colors.info, sub: '10% discount' },
        ].map(c => (
          <View key={c.label} style={{
            flex: 1, minWidth: isMobile ? '45%' : 140, backgroundColor: T.card, borderRadius: 14, padding: isMobile ? 14 : 16,
            borderWidth: 1, borderColor: T.border, borderLeftWidth: 3, borderLeftColor: c.color,
          }} data-testid={`churn-kpi-${c.label.replace(/\s+/g, '-').toLowerCase()}`} testID={`churn-kpi-${c.label.replace(/\s+/g, '-').toLowerCase()}`}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 8 }}>
              <View style={{ width: 28, height: 28, borderRadius: 7, backgroundColor: (globalThis as any).__alphaColor(c.color, '12'), alignItems: 'center', justifyContent: 'center' }}>
                <Ionicons name={c.icon} size={13} color={c.color} />
              </View>
              <Text style={{ color: T.textMuted, fontSize: 9, fontWeight: '700', textTransform: 'uppercase', flex: 1 }}>{c.label}</Text>
            </View>
            <Text style={{ color: T.text, fontSize: 22, fontWeight: '800', letterSpacing: -0.5 }}>{c.value}</Text>
            <Text style={{ color: T.textMuted, fontSize: 9, marginTop: 2 }}>{c.sub}</Text>
          </View>
        ))}
      </View>

      {/* Charts Row */}
      <View style={{ flexDirection: isMobile ? 'column' : 'row', gap: 12, marginBottom: 20 }}>
        {/* Churn Trend */}
        <View style={{ flex: 1, backgroundColor: T.card, borderRadius: 14, padding: 16, borderWidth: 1, borderColor: T.border }} data-testid="churn-trend-chart" testID="churn-trend-chart">
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 12 }}>
            <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: colors.error }} />
            <Text style={{ color: T.text, fontSize: 13, fontWeight: '700' }}>{tx('admin.churnRecoveryPanel.auto.text.006', 'Cancellation Trend')}</Text>
            <Text style={{ color: T.textMuted, fontSize: 10, marginLeft: 'auto' }}>{tx('admin.churnRecoveryPanel.auto.text.007', '30 days')}</Text>
          </View>
          <AreaChart data={churnTrend} color={colors.error} height={70} />
          <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginTop: 6 }}>
            <Text style={{ color: T.textMuted, fontSize: 8 }}>{churnTrend[0]?.label?.slice(5) || ''}</Text>
            <Text style={{ color: T.textMuted, fontSize: 8 }}>{churnTrend[churnTrend.length - 1]?.label?.slice(5) || ''}</Text>
          </View>
        </View>

        {/* Recovery Trend */}
        <View style={{ flex: 1, backgroundColor: T.card, borderRadius: 14, padding: 16, borderWidth: 1, borderColor: T.border }} data-testid="recovery-trend-chart" testID="recovery-trend-chart">
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 12 }}>
            <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: colors.success }} />
            <Text style={{ color: T.text, fontSize: 13, fontWeight: '700' }}>{tx('admin.churnRecoveryPanel.auto.text.008', 'Recovery Trend')}</Text>
            <Text style={{ color: T.textMuted, fontSize: 10, marginLeft: 'auto' }}>{tx('admin.churnRecoveryPanel.auto.text.009', '30 days')}</Text>
          </View>
          <AreaChart data={recoveryTrend} color={colors.successText} height={70} />
          <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginTop: 6 }}>
            <Text style={{ color: T.textMuted, fontSize: 8 }}>{recoveryTrend[0]?.label?.slice(5) || ''}</Text>
            <Text style={{ color: T.textMuted, fontSize: 8 }}>{recoveryTrend[recoveryTrend.length - 1]?.label?.slice(5) || ''}</Text>
          </View>
        </View>

        {/* Recovery Funnel */}
        <View style={{ flex: 1, backgroundColor: T.card, borderRadius: 14, padding: 16, borderWidth: 1, borderColor: T.border }} data-testid="recovery-funnel" testID="recovery-funnel">
          <Text style={{ color: T.text, fontSize: 13, fontWeight: '700', marginBottom: 14 }}>{tx('admin.churnRecoveryPanel.auto.text.010', 'Recovery Funnel')}</Text>
          <DonutStat value={k.recovered || 0} total={k.total_churned || 0} color={colors.successText} label="Recovery Rate" size={90} />
          <View style={{ marginTop: 14, gap: 6 }}>
            {[
              { label: 'Cancelled', value: funnel.total_cancelled, color: colors.error },
              { label: 'Emails Sent', value: funnel.emails_sent, color: colors.primary },
              { label: 'Active Campaigns', value: funnel.active_campaigns, color: colors.warningText },
              { label: 'Recovered', value: funnel.recovered, color: colors.successText },
            ].map(f => (
              <View key={f.label} style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                <View style={{ width: 6, height: 6, borderRadius: 3, backgroundColor: f.color }} />
                <Text style={{ color: T.textMuted, fontSize: 10, flex: 1 }}>{f.label}</Text>
                <Text style={{ color: T.text, fontSize: 11, fontWeight: '700' }}>{f.value || 0}</Text>
              </View>
            ))}
          </View>
        </View>
      </View>

      {/* Automation Info */}
      <View style={{ backgroundColor: T.bgSoft, borderRadius: 12, padding: 14, marginBottom: 20, borderWidth: 1, borderColor: T.border, flexDirection: isMobile ? 'column' : 'row', gap: 16 }} data-testid="automation-info" testID="automation-info">
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, flex: 1 }}>
          <View style={{ width: 32, height: 32, borderRadius: 8, backgroundColor: colors.successSoft, alignItems: 'center', justifyContent: 'center' }}>
            <Ionicons name="flash" size={16} color={colors.successText} />
          </View>
          <View>
            <Text style={{ color: T.text, fontSize: 12, fontWeight: '700' }}>{tx('admin.churnRecoveryPanel.auto.text.011', 'Fully Automated')}</Text>
            <Text style={{ color: T.textMuted, fontSize: 10 }}>{tx('admin.churnRecoveryPanel.auto.text.012', 'Cancellation emails sent instantly, win-back every 14 days')}</Text>
          </View>
        </View>
        <View style={{ flexDirection: 'row', gap: 12, flexWrap: 'wrap' }}>
          {[
            { label: 'Goodbye Email', icon: 'mail', color: colors.error },
            { label: '6 Reminders', icon: 'notifications', color: colors.warningText },
            { label: '10% Discount', icon: 'pricetag', color: colors.successText },
            { label: 'Auto-Stop', icon: 'stop-circle', color: colors.textDim },
          ].map(a => (
            <View key={a.label} style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}>
              <Ionicons name={a.icon as any} size={11} color={a.color} />
              <Text style={{ color: T.textSec, fontSize: 10, fontWeight: '600' }}>{a.label}</Text>
            </View>
          ))}
        </View>
      </View>

      {/* Churned Users Table */}
      <View style={{ backgroundColor: T.card, borderRadius: 16, borderWidth: 1, borderColor: T.border, overflow: 'hidden' }} data-testid="churned-users-table" testID="churned-users-table">
        <View style={{ padding: 16, borderBottomWidth: 1, borderBottomColor: T.border, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
          <View>
            <Text style={{ color: T.text, fontSize: 14, fontWeight: '700' }}>{tx('admin.churnRecoveryPanel.auto.text.013', 'Churned Users')}</Text>
            <Text style={{ color: T.textMuted, fontSize: 10 }}>{users.length} total records</Text>
          </View>
          <View style={{ flexDirection: 'row', gap: 6 }}>
            {Object.entries(STATUS_COLORS).map(([k, c]) => (
              <View key={k} style={{ flexDirection: 'row', alignItems: 'center', gap: 3 }}>
                <View style={{ width: 6, height: 6, borderRadius: 3, backgroundColor: c }} />
                <Text style={{ color: T.textMuted, fontSize: 8 }}>{STATUS_LABELS[k]}</Text>
              </View>
            ))}
          </View>
        </View>

        {users.length === 0 ? (
          <View style={{ padding: 40, alignItems: 'center' }}>
            <Ionicons name="checkmark-circle" size={40} color={T.successText} />
            <Text style={{ color: T.text, fontSize: 14, fontWeight: '700', marginTop: 12 }}>{tx('admin.churnRecoveryPanel.auto.text.014', 'No churned users')}</Text>
            <Text style={{ color: T.textMuted, fontSize: 12, marginTop: 4 }}>{tx('admin.churnRecoveryPanel.auto.text.015', 'All subscribers are active. Great job!')}</Text>
          </View>
        ) : (
          users.map((u: any, i: number) => {
            const sc = STATUS_COLORS[u.status] || colors.textDim;
            return (
              <View key={u.churn_id} style={{
                flexDirection: isMobile ? 'column' : 'row', alignItems: isMobile ? 'flex-start' : 'center',
                padding: isMobile ? 12 : 14, gap: isMobile ? 10 : 14,
                borderTopWidth: i === 0 ? 0 : 1, borderTopColor: T.border,
                backgroundColor: u.status === 'recovered' ? colors.successSoft : 'transparent',
              }} data-testid={`churn-user-${u.churn_id}`} testID={`churn-user-${u.churn_id}`}>
                {/* User Info */}
                <View style={{ flex: 1, minWidth: 0 }}>
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                    <View style={{ width: 32, height: 32, borderRadius: 16, backgroundColor: (globalThis as any).__alphaColor(sc, '15'), alignItems: 'center', justifyContent: 'center' }}>
                      <Ionicons name={u.status === 'recovered' ? 'heart' : 'person'} size={14} color={sc} />
                    </View>
                    <View style={{ flex: 1 }}>
                      <Text style={{ color: T.text, fontSize: 12, fontWeight: '700' }} numberOfLines={1}>{u.user_name}</Text>
                      <Text style={{ color: T.textMuted, fontSize: 10 }} numberOfLines={1}>{u.user_email}</Text>
                    </View>
                  </View>
                </View>

                {/* Status Badge */}
                <View style={{ backgroundColor: (globalThis as any).__alphaColor(sc, '15'), paddingHorizontal: 10, paddingVertical: 4, borderRadius: 8, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(sc, '25') }}>
                  <Text style={{ color: sc, fontSize: 10, fontWeight: '700' }}>{STATUS_LABELS[u.status] || u.status}</Text>
                </View>

                {/* Stats */}
                <View style={{ flexDirection: 'row', gap: 12 }}>
                  <View style={{ alignItems: 'center' }}>
                    <Text style={{ color: T.text, fontSize: 12, fontWeight: '700' }}>{u.reminders_sent}</Text>
                    <Text style={{ color: T.textMuted, fontSize: 8 }}>{tx('admin.churnRecoveryPanel.auto.text.016', 'Reminders')}</Text>
                  </View>
                  <View style={{ alignItems: 'center' }}>
                    <Text style={{ color: T.text, fontSize: 12, fontWeight: '700' }}>{u.emails_sent}</Text>
                    <Text style={{ color: T.textMuted, fontSize: 8 }}>{tx('admin.churnRecoveryPanel.auto.text.017', 'Emails')}</Text>
                  </View>
                </View>

                {/* Actions */}
                {u.status !== 'recovered' && u.status !== 'expired' && (
                  <View style={{ flexDirection: 'row', gap: 6 }}>
                    <TouchableOpacity
                      onPress={() => sendWinback(u.churn_id)}
                      disabled={activeAction === u.churn_id}
                      style={{ flexDirection: 'row', alignItems: 'center', gap: 3, backgroundColor: (globalThis as any).__alphaColor(T.primary, '12'), paddingHorizontal: 10, paddingVertical: 6, borderRadius: 8, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(T.primary, '20') }}
                      data-testid={`send-winback-${u.churn_id}`} testID={`send-winback-${u.churn_id}`}>
                      <Ionicons name="mail" size={11} color={T.primary} />
                      <Text style={{ color: T.primary, fontSize: 10, fontWeight: '700' }}>{tx('admin.churnRecoveryPanel.auto.text.018', 'Send Win-back')}</Text>
                    </TouchableOpacity>
                    <TouchableOpacity
                      onPress={() => markRecovered(u.churn_id)}
                      disabled={activeAction === u.churn_id}
                      style={{ flexDirection: 'row', alignItems: 'center', gap: 3, backgroundColor: colors.successSoft, paddingHorizontal: 10, paddingVertical: 6, borderRadius: 8, borderWidth: 1, borderColor: colors.successSoft }}
                      data-testid={`mark-recovered-${u.churn_id}`} testID={`mark-recovered-${u.churn_id}`}>
                      <Ionicons name="checkmark" size={11} color={colors.successText} />
                      <Text style={{ color: colors.successText, fontSize: 10, fontWeight: '700' }}>{tx('admin.churnRecoveryPanel.auto.text.019', 'Recovered')}</Text>
                    </TouchableOpacity>
                  </View>
                )}

                {/* Dates */}
                <View>
                  <Text style={{ color: T.textMuted, fontSize: 9 }}>Cancelled: {u.cancelled_at ? new Date(u.cancelled_at).toLocaleDateString() : '-'}</Text>
                  {u.recovered_at && <Text style={{ color: colors.successText, fontSize: 9 }}>Recovered: {new Date(u.recovered_at).toLocaleDateString()}</Text>}
                  {u.next_reminder_at && u.status !== 'recovered' && <Text style={{ color: T.textMuted, fontSize: 9 }}>Next: {new Date(u.next_reminder_at).toLocaleDateString()}</Text>}
                </View>
              </View>
            );
          })
        )}
      </View>

      {/* Discount Code Info */}
      <View style={{ backgroundColor: T.bgSoft, borderRadius: 12, padding: 14, marginTop: 16, flexDirection: 'row', alignItems: 'center', gap: 10, borderWidth: 1, borderColor: T.border }}>
        <Ionicons name="information-circle" size={16} color={T.textMuted} />
        <Text style={{ color: T.textMuted, fontSize: 11, flex: 1 }}>{tx('admin.churnRecoveryPanel.auto.text.020', 'Each cancelled user receives a unique 10% discount code valid for 30 days. Win-back reminders are sent bi-weekly, up to 6 times (3 months). Campaigns auto-stop when the user resubscribes.')}</Text>
      </View>
    </View>
  );
}
