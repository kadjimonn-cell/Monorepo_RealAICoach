import React, { useEffect, useState, useCallback } from 'react';
import {
  View, Text, ScrollView, TouchableOpacity, ActivityIndicator,
  StyleSheet, useWindowDimensions, TextInput, Platform,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { useTheme } from '../../src/context/ThemeContext';
import { useAdminTheme } from '../../src/hooks/useAdminTheme';
import api from '../../src/services/api';
import Svg, { Rect, Line, Text as SvgText} from 'react-native-svg';
import { ExecutiveDashboardSkeleton } from '../../src/components/SkeletonLoaders';
import { useTranslation } from '../../src/hooks/useTranslation';

type Kpi = { cost: number; tokens: number; calls: number };
type Overview = {
  kpi: {
    today: Kpi; mtd: Kpi; last_7d: Kpi; last_30d: Kpi;
    error_rate_pct_30d: number; avg_latency_ms_30d: number;
  };
  budget: {
    monthly_budget_usd: number; mtd_cost_usd: number; burn_pct: number;
    projected_month_end_usd: number; over_budget: boolean;
  };
  trend_14d: { date: string; cost: number; tokens: number; calls: number }[];
  by_model: { model: string; cost: number; tokens: number; calls: number }[];
  by_feature: { feature: string; cost: number; tokens: number; calls: number }[];
  top_users: { user_id: string; cost: number; calls: number }[];
  generated_at: string;
};

const fmtUsd = (v: number) => `$${(v || 0).toLocaleString(undefined, { maximumFractionDigits: v < 10 ? 4 : 2 })}`;
const fmtNum = (n: number) => (n || 0).toLocaleString();
const short = (s: string, n = 22) => (s && s.length > n ? s.slice(0, n - 1) + '…' : s || '');

export default function LLMBillingDashboard() {
  const { t } = useTranslation();
  t('i18n.route.admin.llm-billing.probe');
  const C = useAdminTheme();
  const { darkMode: isDark } = useTheme();
  const router = useRouter();
  const { width } = useWindowDimensions();
  const isDesktop = width >= 1024;
  const isCompact = width < 860;

  const [loading, setLoading] = useState(true);
  const [data, setData] = useState<Overview | null>(null);
  const [recent, setRecent] = useState<any[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [budgetInput, setBudgetInput] = useState<string>('');
  const [savingBudget, setSavingBudget] = useState(false);
  const [digestBusy, setDigestBusy] = useState(false);
  const [digestToast, setDigestToast] = useState<string | null>(null);
  const [showAdvancedControls, setShowAdvancedControls] = useState(false);

  const sendDigestPreview = async () => {
    setDigestBusy(true);
    try {
      const r = await api.post('/admin/llm-billing/send-digest-now');
      const d = r.data || {};
      if (d.reason === 'email_not_configured') {
        setDigestToast('Email service not configured — set RESEND_API_KEY.');
      } else if (d.reason === 'no_admins') {
        setDigestToast('No admin recipients found.');
      } else {
        setDigestToast(`Digest sent to ${d.sent}/${d.recipients} admin(s) · burn ${d.burn_pct}% · yday $${d.yesterday_cost_usd}`);
      }
    } catch (e: any) {
      setDigestToast('Send failed: ' + (e?.response?.data?.detail || e?.message || 'unknown'));
    } finally {
      setDigestBusy(false);
      setTimeout(() => setDigestToast(null), 5000);
    }
  };

  const loadAll = useCallback(async () => {
    try {
      setError(null);
      const [o, r] = await Promise.all([
        api.get('/admin/llm-billing/overview'),
        api.get('/admin/llm-billing/recent?limit=20'),
      ]);
      setData(o.data);
      setRecent(r.data?.items || []);
      setBudgetInput(String(o.data?.budget?.monthly_budget_usd ?? ''));
    } catch (e: any) {
      setError(e?.response?.data?.detail || e?.message || 'Failed to load');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadAll(); }, [loadAll]);

  const seedDemo = async () => {
    try {
      await api.post('/admin/llm-billing/seed-demo');
      await loadAll();
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Seed failed');
    }
  };

  const saveBudget = async () => {
    const v = Number(budgetInput);
    if (!v || v <= 0) return;
    setSavingBudget(true);
    try {
      await api.put('/admin/llm-billing/budget', { monthly_budget_usd: v });
      await loadAll();
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Budget update failed');
    } finally {
      setSavingBudget(false);
    }
  };

  if (loading) return <ExecutiveDashboardSkeleton />;

  if (error) {
    return (
      <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center', backgroundColor: C.bg, padding: 24 }}>
        <Ionicons name="alert-circle-outline" size={48} color={C.error} />
        <Text style={{ color: C.text, fontSize: 18, fontWeight: '700', marginTop: 12 }} data-testid="llm-billing-error" testID="llm-billing-error">{error}</Text>
        <TouchableOpacity onPress={loadAll} style={{ marginTop: 16, paddingHorizontal: 20, paddingVertical: 10, borderRadius: 10, backgroundColor: C.primary }} data-testid="llm-billing-retry" testID="llm-billing-retry">
          <Text style={{ color: C.primaryText, fontWeight: '700' }}>Retry</Text>
        </TouchableOpacity>
      </View>
    );
  }

  if (!data) return null;

  const { kpi, budget, trend_14d, by_model, by_feature, top_users } = data;
  const burnColor = budget.over_budget ? C.error : budget.burn_pct > 75 ? C.warning : C.success;
  const maxTrendCost = Math.max(...trend_14d.map(d => d.cost), 0.01);
  const maxModelCost = Math.max(...by_model.map(m => m.cost), 0.01);
  const maxFeatureCost = Math.max(...by_feature.map(f => f.cost), 0.01);

  return (
    <View style={{ flex: 1, backgroundColor: C.bg }} data-testid="llm-billing-dashboard" testID="llm-billing-dashboard">
      <ScrollView contentContainerStyle={{ padding: isDesktop ? 32 : 16, paddingBottom: 80, width: '100%', maxWidth: 1440, alignSelf: 'center' }}>
        {/* Header */}
        <View style={[styles.header, { borderBottomColor: C.border }]}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 12, flex: 1 }}>
            <TouchableOpacity onPress={() => router.back()} data-testid="llm-billing-back" testID="llm-billing-back" style={[styles.backBtn, { borderColor: C.border, backgroundColor: C.surface }]}>
              <Ionicons name="arrow-back" size={18} color={C.text} />
            </TouchableOpacity>
            <View>
              <Text style={[styles.title, { color: C.text }]} data-testid="llm-billing-title" testID="llm-billing-title">LLM Usage & Billing</Text>
              <Text style={[styles.subtitle, { color: C.textMuted }]}>Model cost, burn rate & budget controls</Text>
            </View>
          </View>
          <View style={{ flexDirection: 'row', gap: 8, flexWrap: 'wrap', justifyContent: isCompact ? 'flex-start' : 'flex-end' }}>
            {(budget.burn_pct >= 70 || budget.over_budget) && (
              <TouchableOpacity
                onPress={() => router.push('/pricing')}
                style={[styles.secondaryBtn, { borderColor: (globalThis as any).__alphaColor((budget.over_budget ? C.error : C.warning), '66'), backgroundColor: (globalThis as any).__alphaColor((budget.over_budget ? C.error : C.warning), '14') }]}
                data-testid="llm-billing-upgrade-cta" testID="llm-billing-upgrade-cta"
              >
                <Ionicons name="rocket-outline" size={14} color={budget.over_budget ? C.error : C.warning} />
                <Text style={{ color: budget.over_budget ? C.error : C.warning, fontSize: 12, fontWeight: '800' }}>
                  {budget.over_budget ? 'Over budget — Upgrade plan' : 'Upgrade plan'}
                </Text>
              </TouchableOpacity>
            )}
            <TouchableOpacity onPress={sendDigestPreview} disabled={digestBusy} style={[styles.secondaryBtn, { borderColor: C.border, backgroundColor: C.surface, opacity: digestBusy ? 0.6 : 1 }]} data-testid="llm-billing-send-digest" testID="llm-billing-send-digest">
              {digestBusy ? <ActivityIndicator color={C.textSec} size="small" /> : <Ionicons name="mail-outline" size={14} color={C.textSec} />}
              <Text style={{ color: C.textSec, fontSize: 12, fontWeight: '700' }}>{digestBusy ? 'Sending…' : 'Send me a preview'}</Text>
            </TouchableOpacity>
            <TouchableOpacity
              onPress={() => setShowAdvancedControls((prev) => !prev)}
              style={[styles.secondaryBtn, { borderColor: C.border, backgroundColor: C.surface }]}
              data-testid="llm-billing-toggle-advanced"
              testID="llm-billing-toggle-advanced"
            >
              <Ionicons name={showAdvancedControls ? 'chevron-up-outline' : 'chevron-down-outline'} size={14} color={C.textSec} />
              <Text style={{ color: C.textSec, fontSize: 12, fontWeight: '700' }}>{showAdvancedControls ? 'Hide Advanced' : 'Advanced'}</Text>
            </TouchableOpacity>
            {showAdvancedControls && (
              <TouchableOpacity onPress={seedDemo} style={[styles.secondaryBtn, { borderColor: C.border, backgroundColor: C.surface }]} data-testid="llm-billing-seed-demo" testID="llm-billing-seed-demo">
                <Ionicons name="flask-outline" size={14} color={C.textSec} />
                <Text style={{ color: C.textSec, fontSize: 12, fontWeight: '700' }}>Seed Demo</Text>
              </TouchableOpacity>
            )}
            <TouchableOpacity onPress={loadAll} style={[styles.primaryBtn, { backgroundColor: C.primary }]} data-testid="llm-billing-refresh" testID="llm-billing-refresh">
              <Ionicons name="refresh" size={14} color={C.primaryText} />
              <Text style={{ color: C.primaryText, fontSize: 12, fontWeight: '700' }}>Refresh</Text>
            </TouchableOpacity>
          </View>
        </View>
        {digestToast && (
          <View style={{ marginTop: 12, padding: 10, borderRadius: 8, borderWidth: 1, borderColor: C.border, backgroundColor: C.surface }} data-testid="llm-billing-digest-toast" testID="llm-billing-digest-toast">
            <Text style={{ color: C.text, fontSize: 12 }}>{digestToast}</Text>
          </View>
        )}

        {/* KPI Row */}
        <View style={[styles.row, { flexWrap: 'wrap', gap: 12, marginTop: 20 }]}>
          <KpiCard C={C} label="Today's Cost" value={fmtUsd(kpi.today.cost)} sub={`${fmtNum(kpi.today.calls)} calls`} icon="calendar-outline" tone={C.primary} testId="kpi-today" />
          <KpiCard C={C} label="Month-to-date" value={fmtUsd(kpi.mtd.cost)} sub={`${fmtNum(kpi.mtd.calls)} calls • ${fmtNum(kpi.mtd.tokens)} tok`} icon="trending-up" tone={C.accent} testId="kpi-mtd" />
          <KpiCard C={C} label="Last 7 Days" value={fmtUsd(kpi.last_7d.cost)} sub={`${fmtNum(kpi.last_7d.calls)} calls`} icon="time-outline" tone={C.info} testId="kpi-7d" />
          <KpiCard C={C} label="Last 30 Days" value={fmtUsd(kpi.last_30d.cost)} sub={`${fmtNum(kpi.last_30d.calls)} calls`} icon="bar-chart-outline" tone={C.success} testId="kpi-30d" />
          <KpiCard C={C} label="Error Rate" value={`${kpi.error_rate_pct_30d}%`} sub="30-day window" icon="alert-circle-outline" tone={kpi.error_rate_pct_30d > 5 ? C.error : C.warning} testId="kpi-error" />
          <KpiCard C={C} label="Avg Latency" value={`${fmtNum(kpi.avg_latency_ms_30d)}ms`} sub="30-day window" icon="flash-outline" tone={C.indigo} testId="kpi-latency" />
        </View>

        {/* Budget Panel */}
        <View style={[styles.card, { backgroundColor: C.surface, borderColor: C.border, marginTop: 20 }]} data-testid="llm-billing-budget-card" testID="llm-billing-budget-card">
          <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
            <Text style={[styles.cardTitle, { color: C.text }]}>Monthly Budget</Text>
            <View style={[styles.pill, { backgroundColor: (globalThis as any).__alphaColor(burnColor, '22'), borderColor: (globalThis as any).__alphaColor(burnColor, '66') }]}>
              <Text style={{ color: burnColor, fontSize: 11, fontWeight: '800' }}>{budget.burn_pct}% BURNED</Text>
            </View>
          </View>
          <View style={{ flexDirection: isDesktop ? 'row' : 'column', gap: 16 }}>
            <View style={{ flex: 1 }}>
              <View style={[styles.progressTrack, { backgroundColor: C.border }]}>
                <View style={{ width: `${Math.min(100, budget.burn_pct)}%`, height: '100%', backgroundColor: burnColor, borderRadius: 999 }} />
              </View>
              <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginTop: 8 }}>
                <Text style={{ color: C.textSec, fontSize: 12 }}>{fmtUsd(budget.mtd_cost_usd)} used</Text>
                <Text style={{ color: C.textMuted, fontSize: 12 }}>of {fmtUsd(budget.monthly_budget_usd)}</Text>
              </View>
              <Text style={{ color: C.textMuted, fontSize: 12, marginTop: 10 }}>
                Projected month-end: <Text style={{ color: budget.over_budget ? C.error : C.text, fontWeight: '700' }} data-testid="llm-billing-projected" testID="llm-billing-projected">{fmtUsd(budget.projected_month_end_usd)}</Text>
              </Text>
            </View>
            <View style={{ flex: 1, gap: 8 }}>
              <Text style={{ color: C.textSec, fontSize: 12, fontWeight: '700' }}>Update monthly ceiling (USD)</Text>
              <View style={{ flexDirection: 'row', gap: 8, flexWrap: 'wrap' }}>
                <TextInput
                  value={budgetInput}
                  onChangeText={setBudgetInput}
                  keyboardType="numeric"
                  placeholder="500"
                  placeholderTextColor={C.textMuted}
                  style={[styles.input, { borderColor: C.border, color: C.text, backgroundColor: C.bg }]}
                  data-testid="llm-billing-budget-input"
                  testID="llm-billing-budget-input"
                />
                <TouchableOpacity onPress={saveBudget} disabled={savingBudget} style={[styles.primaryBtn, { backgroundColor: C.primary, opacity: savingBudget ? 0.6 : 1 }]} data-testid="llm-billing-budget-save" testID="llm-billing-budget-save">
                  {savingBudget ? <ActivityIndicator color={C.primaryText} size="small" /> : (
                    <><Ionicons name="save-outline" size={14} color={C.primaryText} />
                      <Text style={{ color: C.primaryText, fontSize: 12, fontWeight: '700' }}>Save</Text></>
                  )}
                </TouchableOpacity>
              </View>
            </View>
          </View>
        </View>

        {/* Trend chart */}
        <View style={[styles.card, { backgroundColor: C.surface, borderColor: C.border, marginTop: 20 }]} data-testid="llm-billing-trend" testID="llm-billing-trend">
          <Text style={[styles.cardTitle, { color: C.text, marginBottom: 10 }]}>14-day cost trend</Text>
          <TrendBars data={trend_14d} maxCost={maxTrendCost} C={C} isDark={isDark} />
        </View>

        {/* Two-column: by model / by feature */}
        <View style={{ flexDirection: isDesktop ? 'row' : 'column', gap: 16, marginTop: 20 }}>
          <View style={[styles.card, { backgroundColor: C.surface, borderColor: C.border, flex: 1 }]} data-testid="llm-billing-by-model" testID="llm-billing-by-model">
            <Text style={[styles.cardTitle, { color: C.text, marginBottom: 10 }]}>Cost by model (30d)</Text>
            {by_model.length === 0 && <Empty C={C} label="No LLM calls yet" />}
            {by_model.map(m => (
              <BarRow key={m.model} label={m.model} value={m.cost} subValue={`${fmtNum(m.calls)} calls • ${fmtNum(m.tokens)} tok`} max={maxModelCost} C={C} tone={C.primary} />
            ))}
          </View>
          <View style={[styles.card, { backgroundColor: C.surface, borderColor: C.border, flex: 1 }]} data-testid="llm-billing-by-feature" testID="llm-billing-by-feature">
            <Text style={[styles.cardTitle, { color: C.text, marginBottom: 10 }]}>Cost by feature (30d)</Text>
            {by_feature.length === 0 && <Empty C={C} label="No feature usage yet" />}
            {by_feature.map(f => (
              <BarRow key={f.feature} label={short(f.feature, 28)} value={f.cost} subValue={`${fmtNum(f.calls)} calls`} max={maxFeatureCost} C={C} tone={C.accent} />
            ))}
          </View>
        </View>

        {/* Top users + recent log */}
        <View style={{ flexDirection: isDesktop ? 'row' : 'column', gap: 16, marginTop: 20 }}>
          <View style={[styles.card, { backgroundColor: C.surface, borderColor: C.border, flex: 1 }]} data-testid="llm-billing-top-users" testID="llm-billing-top-users">
            <Text style={[styles.cardTitle, { color: C.text, marginBottom: 10 }]}>Top spenders (30d)</Text>
            {top_users.length === 0 && <Empty C={C} label="No user activity" />}
            {top_users.map((u, i) => (
              <View key={u.user_id + i} style={[styles.listRow, { borderBottomColor: C.border }]}>
                <View style={{ flex: 1 }}>
                  <Text style={{ color: C.text, fontSize: 13, fontWeight: '700' }}>{short(u.user_id, 28)}</Text>
                  <Text style={{ color: C.textMuted, fontSize: 11 }}>{fmtNum(u.calls)} calls</Text>
                </View>
                <Text style={{ color: C.primary, fontSize: 13, fontWeight: '800' }}>{fmtUsd(u.cost)}</Text>
              </View>
            ))}
          </View>
          <View style={[styles.card, { backgroundColor: C.surface, borderColor: C.border, flex: 1.2 }]} data-testid="llm-billing-recent-log" testID="llm-billing-recent-log">
            <Text style={[styles.cardTitle, { color: C.text, marginBottom: 10 }]}>Recent calls</Text>
            {recent.length === 0 && <Empty C={C} label="No recent calls logged" />}
            {recent.slice(0, 12).map((r, i) => (
              <View key={i} style={[styles.listRow, { borderBottomColor: C.border }]}>
                <View style={{ flex: 1, paddingRight: 8 }}>
                  <Text style={{ color: C.text, fontSize: 12, fontWeight: '700' }} numberOfLines={1}>{r.model} · {short(r.feature || '—', 18)}</Text>
                  <Text style={{ color: C.textMuted, fontSize: 10 }} numberOfLines={1}>
                    {r.timestamp?.slice(0, 16).replace('T', ' ')} · {fmtNum(r.total_tokens)} tok · {r.latency_ms || 0}ms
                  </Text>
                </View>
                <View style={{ alignItems: 'flex-end' }}>
                  <Text style={{ color: r.successText ? C.success : C.error, fontSize: 12, fontWeight: '800' }}>{fmtUsd(r.cost_usd)}</Text>
                  {!r.success && <Text style={{ color: C.error, fontSize: 10 }}>err</Text>}
                </View>
              </View>
            ))}
          </View>
        </View>

        <Text style={{ color: C.textMuted, fontSize: 11, textAlign: 'center', marginTop: 24 }}>
          Generated {data.generated_at?.slice(0, 19).replace('T', ' ')} UTC · Cost estimated from token counts using published model pricing.
        </Text>
      </ScrollView>
    </View>
  );
}

function KpiCard({ C, label, value, sub, icon, tone, testId }: any) {
  return (
    <View style={[styles.kpi, { borderColor: C.border, backgroundColor: C.surface, borderLeftColor: tone, borderLeftWidth: 3 }]} data-testid={testId} testID={testId}>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
        <View style={[styles.kpiIcon, { backgroundColor: (globalThis as any).__alphaColor(tone, '22') }]}>
          <Ionicons name={icon} size={16} color={tone} />
        </View>
        <View style={{ flex: 1 }}>
          <Text style={{ color: C.textMuted, fontSize: 10, fontWeight: '700', letterSpacing: 1, textTransform: 'uppercase' }}>{label}</Text>
          <Text style={{ color: C.text, fontSize: 18, fontWeight: '800', marginTop: 2 }}>{value}</Text>
          {sub && <Text style={{ color: C.textMuted, fontSize: 10, marginTop: 2 }}>{sub}</Text>}
        </View>
      </View>
    </View>
  );
}

function BarRow({ label, value, subValue, max, C, tone }: any) {
  const pct = Math.max(2, Math.min(100, (value / max) * 100));
  return (
    <View style={{ marginBottom: 10 }}>
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginBottom: 4 }}>
        <Text style={{ color: C.text, fontSize: 12, fontWeight: '700' }} numberOfLines={1}>{label}</Text>
        <Text style={{ color: tone, fontSize: 12, fontWeight: '800' }}>{fmtUsd(value)}</Text>
      </View>
      <View style={{ height: 6, borderRadius: 999, backgroundColor: C.border, overflow: 'hidden' }}>
        <View style={{ width: `${pct}%`, height: '100%', backgroundColor: tone }} />
      </View>
      {subValue && <Text style={{ color: C.textMuted, fontSize: 10, marginTop: 3 }}>{subValue}</Text>}
    </View>
  );
}

function TrendBars({ data, maxCost, C, isDark }: any) {
  const { width } = useWindowDimensions();
  const cw = Math.min(width - 80, 900);
  const height = 160;
  const barW = Math.max(10, (cw - 60) / data.length - 6);
  return (
    <View style={{ alignItems: 'center' }}>
      <Svg width={cw} height={height + 34}>
        <Line x1="40" y1="0" x2="40" y2={height} stroke={C.border} strokeWidth="1" />
        <Line x1="40" y1={height} x2={cw - 4} y2={height} stroke={C.border} strokeWidth="1" />
        {data.map((d: any, i: number) => {
          const h = (d.cost / maxCost) * (height - 16);
          const x = 48 + i * ((cw - 60) / data.length);
          return (
            <React.Fragment key={d.date}>
              <Rect x={x} y={height - h} width={barW} height={h} rx={3} fill={C.primary} opacity={0.9} />
              <SvgText x={x + barW / 2} y={height + 14} fill={C.textMuted} fontSize="9" textAnchor="middle">{d.date.slice(5)}</SvgText>
              <SvgText x={x + barW / 2} y={height + 26} fill={C.textDim} fontSize="8" textAnchor="middle">{`$${d.cost.toFixed(2)}`}</SvgText>
            </React.Fragment>
          );
        })}
        <SvgText x={20} y={12} fill={C.textMuted} fontSize="9" textAnchor="middle">{`$${maxCost.toFixed(2)}`}</SvgText>
        <SvgText x={20} y={height} fill={C.textMuted} fontSize="9" textAnchor="middle">$0</SvgText>
      </Svg>
    </View>
  );
}

function Empty({ C, label }: any) {
  return (
    <View style={{ paddingVertical: 24, alignItems: 'center' }}>
      <Ionicons name="document-text-outline" size={28} color={C.textMuted} />
      <Text style={{ color: C.textMuted, marginTop: 6, fontSize: 12 }}>{label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingBottom: 18, borderBottomWidth: 1 },
  title: { fontSize: 22, fontWeight: '800', letterSpacing: -0.4 },
  subtitle: { fontSize: 12, marginTop: 2 },
  backBtn: { width: 36, height: 36, borderRadius: 10, borderWidth: 1, alignItems: 'center', justifyContent: 'center' },
  primaryBtn: { flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 14, paddingVertical: 9, borderRadius: 10 },
  secondaryBtn: { flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 12, paddingVertical: 9, borderRadius: 10, borderWidth: 1 },
  row: { flexDirection: 'row' },
  card: { borderRadius: 14, borderWidth: 1, padding: 18 },
  cardTitle: { fontSize: 14, fontWeight: '800', letterSpacing: -0.2 },
  kpi: { flexGrow: 1, minWidth: 200, borderRadius: 12, borderWidth: 1, padding: 14 },
  kpiIcon: { width: 32, height: 32, borderRadius: 10, alignItems: 'center', justifyContent: 'center' },
  pill: { paddingHorizontal: 10, paddingVertical: 4, borderRadius: 999, borderWidth: 1 },
  progressTrack: { height: 10, borderRadius: 999, overflow: 'hidden' },
  input: { flex: 1, borderWidth: 1, borderRadius: 10, paddingHorizontal: 12, paddingVertical: Platform.OS === 'web' ? 10 : 8, fontSize: 14 },
  listRow: { flexDirection: 'row', alignItems: 'center', paddingVertical: 8, borderBottomWidth: 1 },
});