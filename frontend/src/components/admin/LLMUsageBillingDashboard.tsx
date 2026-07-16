import React from 'react';
import { View, Text, TouchableOpacity, ActivityIndicator, ScrollView } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useLiveQuery } from '../../hooks/useLiveQuery';
import { useTheme } from '../../context/ThemeContext';
import api from '../../services/api';
import { useTranslation } from '../../hooks/useTranslation';

export function LLMUsageBillingDashboard() {
  const { colors, darkMode } = useTheme();
  const { t } = useTranslation();
  const tx = React.useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);
  const usage = useLiveQuery('/ai/models/usage/dashboard?range=30d', { entity: 'ai-usage', pollInterval: 60000 });
  const budgets = useLiveQuery('/ai/models/budgets', { entity: 'ai-usage', pollInterval: 60000 });
  const recentLogs = useLiveQuery('/ai/models/logs/recent?limit=8', { entity: 'ai-usage', pollInterval: 60000 });
  const reports = useLiveQuery('/ai/models/reports?limit=6', { entity: 'ai-usage', pollInterval: 120000 });

  const runBudgetCheck = async () => {
    await api.post('/ai/models/budgets/check');
    await budgets.refetch();
  };

  const generateReport = async () => {
    await api.post('/ai/models/reports/generate');
    await reports.refetch();
  };

  if (usage.loading || budgets.loading || recentLogs.loading || reports.loading) {
    return <Loader colors={colors} testId="llm-usage-dashboard-loading" label="Loading LLM usage and billing…" />;
  }

  const summary = usage.data?.summary || {};
  const budgetRows = budgets.data?.budgets || [];
  const alerts = budgets.data?.alerts || [];
  const modelRows = usage.data?.by_model || [];
  const featureRows = usage.data?.by_feature || [];
  const jobRows = recentLogs.data?.logs || [];
  const reportRows = reports.data?.reports || [];

  return (
    <ScrollView contentContainerStyle={{ gap: 16, paddingBottom: 24 }} data-testid="llm-usage-billing-dashboard" testID="llm-usage-billing-dashboard">
      <View style={heroCard(colors, darkMode)} data-testid="llm-usage-billing-hero" testID="llm-usage-billing-hero">
        <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
          <View style={{ flex: 1, minWidth: 260 }}>
            <Text style={{ color: colors.text, fontSize: 24, fontWeight: '800', letterSpacing: -0.6 }} data-testid="llm-usage-billing-title" testID="llm-usage-billing-title">{tx('admin.llmUsageBilling.title', 'LLM Usage & Billing')}</Text>
            <Text style={{ color: colors.textSec, fontSize: 13, lineHeight: 20, marginTop: 6 }} data-testid="llm-usage-billing-subtitle" testID="llm-usage-billing-subtitle">{tx('admin.llmUsageBilling.subtitle', 'Track request volume, token spend, budget drift, and recent model jobs from the platform’s live AI usage log.')}</Text>
          </View>
          <View style={{ flexDirection: 'row', gap: 8, flexWrap: 'wrap' }}>
            <ActionButton label="Check budgets" icon="shield-checkmark" onPress={runBudgetCheck} colors={colors} testId="llm-usage-billing-check-budgets-button" />
            <ActionButton label="Generate report" icon="document-text" onPress={generateReport} colors={colors} testId="llm-usage-billing-generate-report-button" />
          </View>
        </View>

        <View style={{ flexDirection: 'row', gap: 12, flexWrap: 'wrap', marginTop: 16 }} data-testid="llm-usage-billing-kpis" testID="llm-usage-billing-kpis">
          <Metric label="Requests (30d)" value={summary.total_requests || 0} accent={colors.primary} testId="llm-usage-total-requests" />
          <Metric label="Tokens (30d)" value={summary.total_tokens || 0} accent={colors.info} testId="llm-usage-total-tokens" />
          <Metric label="Spend (30d)" value={`$${(summary.total_cost || 0).toFixed(2)}`} accent={colors.success} testId="llm-usage-total-cost" />
          <Metric label="Open Alerts" value={alerts.filter((alert: any) => !alert.acknowledged).length} accent={colors.warning} testId="llm-usage-open-alerts" />
        </View>
      </View>

      <View style={{ flexDirection: 'row', gap: 16, flexWrap: 'wrap', alignItems: 'flex-start' }}>
        <View style={{ flex: 2, minWidth: 330 }}>
          <SectionCard title="Spend by Model" subtitle="Which models are driving usage and cost right now." colors={colors} testId="llm-usage-model-card">
            {modelRows.length ? (
              <View style={{ gap: 10 }}>
                {modelRows.map((row: any, index: number) => (
                  <View key={`${row.model_id}-${index}`} style={{ borderRadius: 14, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bgSoft, padding: 14 }} data-testid={`llm-usage-model-row-${index}`} testID={`llm-usage-model-row-${index}`}>
                    <View style={{ flexDirection: 'row', justifyContent: 'space-between', gap: 12, alignItems: 'center' }}>
                      <View style={{ flex: 1 }}>
                        <Text style={{ color: colors.text, fontSize: 13, fontWeight: '700' }}>{row.model_id}</Text>
                        <Text style={{ color: colors.textMuted, fontSize: 11, marginTop: 3 }}>{row.requests} requests · {row.tokens || row.input_tokens + row.output_tokens || 0} tokens</Text>
                      </View>
                      <View style={{ alignItems: 'flex-end' }}>
                        <Text style={{ color: colors.successText, fontSize: 15, fontWeight: '800' }}>${(row.cost || 0).toFixed(4)}</Text>
                        <Text style={{ color: colors.textMuted, fontSize: 10 }}>{tx('admin.llmUsageBilling.labels.cost', 'cost')}</Text>
                      </View>
                    </View>
                  </View>
                ))}
              </View>
            ) : <EmptyState colors={colors} testId="llm-usage-empty-models" label="No model usage recorded yet." icon="flash-outline" />}
          </SectionCard>

          <SectionCard title="Top Features" subtitle="Feature flows consuming the most LLM requests." colors={colors} testId="llm-usage-feature-card">
            {featureRows.length ? (
              <View style={{ gap: 10 }}>
                {featureRows.map((row: any, index: number) => (
                  <View key={`${row.feature}-${index}`} style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }} data-testid={`llm-usage-feature-row-${index}`} testID={`llm-usage-feature-row-${index}`}>
                    <View style={{ flex: 1, height: 14, borderRadius: 999, backgroundColor: colors.bgSoft, overflow: 'hidden' }}>
                      <View style={{ width: `${Math.max(8, (row.count / Math.max(featureRows[0]?.count || 1, 1)) * 100)}%` as any, height: '100%', backgroundColor: `${colors.primary}66` }} />
                    </View>
                    <View style={{ width: 180 }}>
                      <Text style={{ color: colors.text, fontSize: 12, fontWeight: '700' }} numberOfLines={1}>{row.feature}</Text>
                      <Text style={{ color: colors.textMuted, fontSize: 10 }}>{row.count} jobs · ${(row.cost || 0).toFixed(4)}</Text>
                    </View>
                  </View>
                ))}
              </View>
            ) : <EmptyState colors={colors} testId="llm-usage-empty-features" label="No feature-level usage available." icon="layers-outline" />}
          </SectionCard>
        </View>

        <View style={{ flex: 1, minWidth: 300 }}>
          <SectionCard title="Budget Guardrails" subtitle="Monthly budget coverage from the AI budget engine." colors={colors} testId="llm-usage-budget-card">
            {budgetRows.length ? (
              <View style={{ gap: 10 }}>
                {budgetRows.map((budget: any, index: number) => {
                  const accent = budget.status === 'critical' ? colors.error : budget.status === 'warning' ? colors.warning : colors.success;
                  return (
                    <View key={`${budget.type}-${budget.model_id || 'global'}`} style={{ borderRadius: 14, borderWidth: 1, borderColor: `${accent}35`, backgroundColor: colors.bgSoft, padding: 14 }} data-testid={`llm-usage-budget-row-${index}`} testID={`llm-usage-budget-row-${index}`}>
                      <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 10 }}>
                        <View style={{ flex: 1 }}>
                          <Text style={{ color: colors.text, fontSize: 12, fontWeight: '700' }}>{budget.type === 'global' ? 'Global budget' : budget.model_id}</Text>
                          <Text style={{ color: colors.textMuted, fontSize: 10, marginTop: 2 }}>${(budget.current_spend || 0).toFixed(2)} of ${(budget.monthly_limit || 0).toFixed(2)} · {budget.current_requests || 0} jobs</Text>
                        </View>
                        <Text style={{ color: accent, fontSize: 14, fontWeight: '800' }}>{budget.usage_pct || 0}%</Text>
                      </View>
                      <View style={{ height: 8, borderRadius: 999, backgroundColor: colors.surface, marginTop: 10, overflow: 'hidden' }}>
                        <View style={{ width: `${Math.min(100, budget.usage_pct || 0)}%` as any, height: '100%', backgroundColor: accent }} />
                      </View>
                    </View>
                  );
                })}
              </View>
            ) : <EmptyState colors={colors} testId="llm-usage-empty-budgets" label="No active budgets configured." icon="wallet-outline" />}
          </SectionCard>

          <SectionCard title="Recent Billing Reports" subtitle="Generated budget reports and weekly summaries." colors={colors} testId="llm-usage-reports-card">
            {reportRows.length ? (
              <View style={{ gap: 8 }}>
                {reportRows.map((report: any, index: number) => (
                  <View key={report.report_id} style={{ borderRadius: 12, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bgSoft, padding: 12 }} data-testid={`llm-usage-report-row-${index}`} testID={`llm-usage-report-row-${index}`}>
                    <Text style={{ color: colors.text, fontSize: 12, fontWeight: '700' }}>{report.month || report.type}</Text>
                    <Text style={{ color: colors.textMuted, fontSize: 10, marginTop: 3 }}>${(report.current_week?.total_cost || 0).toFixed(2)} this week · {(report.current_week?.total_requests || 0)} jobs</Text>
                  </View>
                ))}
              </View>
            ) : <EmptyState colors={colors} testId="llm-usage-empty-reports" label="No billing reports have been generated yet." icon="document-text-outline" />}
          </SectionCard>
        </View>
      </View>

      <SectionCard title="Recent Model Jobs" subtitle="Latest request-level jobs with token and spend detail." colors={colors} testId="llm-usage-jobs-card">
        {jobRows.length ? (
          <View style={{ gap: 8 }}>
            {jobRows.map((job: any, index: number) => (
              <View key={job.log_id || index} style={{ borderRadius: 14, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bgSoft, padding: 14, flexDirection: 'row', gap: 12, flexWrap: 'wrap', alignItems: 'center' }} data-testid={`llm-usage-job-row-${index}`} testID={`llm-usage-job-row-${index}`}>
                <View style={{ flex: 2, minWidth: 180 }}>
                  <Text style={{ color: colors.text, fontSize: 12, fontWeight: '700' }}>{job.log_id}</Text>
                  <Text style={{ color: colors.textMuted, fontSize: 10, marginTop: 3 }}>{job.feature} · {job.model_id} · {job.provider}</Text>
                </View>
                <MetricInline label="Tokens" value={`${(job.input_tokens || 0) + (job.output_tokens || 0)}`} color={colors.info} testId={`llm-usage-job-tokens-${index}`} />
                <MetricInline label="Cost" value={`$${(job.cost || 0).toFixed(4)}`} color={colors.successText} testId={`llm-usage-job-cost-${index}`} />
                <MetricInline label="Latency" value={`${job.latency_ms || 0}ms`} color={colors.warningText} testId={`llm-usage-job-latency-${index}`} />
              </View>
            ))}
          </View>
        ) : <EmptyState colors={colors} testId="llm-usage-empty-jobs" label="No recent model jobs found." icon="time-outline" />}
      </SectionCard>
    </ScrollView>
  );
}

function ActionButton({ label, icon, onPress, colors, testId }: { label: string; icon: string; onPress: () => void; colors: any; testId: string }) {
  return (
    <TouchableOpacity onPress={() => { void onPress(); }} style={{ flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 12, paddingVertical: 9, borderRadius: 999, backgroundColor: colors.bgSoft, borderWidth: 1, borderColor: colors.border }} data-testid={testId} testID={testId}>
      <Ionicons name={icon as any} size={14} color={colors.textSec} />
      <Text style={{ color: colors.textSec, fontSize: 12, fontWeight: '700' }}>{label}</Text>
    </TouchableOpacity>
  );
}

function Metric({ label, value, accent, testId }: { label: string; value: string | number; accent: string; testId: string }) {    const { colors } = useTheme();
  return (
    <View style={{ flex: 1, minWidth: 180, borderRadius: 14, borderWidth: 1, borderColor: `${accent}30`, backgroundColor: colors.bgSoft, padding: 14 }} data-testid={testId} testID={testId}>
      <Text style={{ color: colors.textMuted, fontSize: 11, fontWeight: '700', textTransform: 'uppercase', letterSpacing: 0.6 }}>{label}</Text>
      <Text style={{ color: accent, fontSize: 28, fontWeight: '800', marginTop: 8 }}>{value}</Text>
    </View>
  );
}

function MetricInline({ label, value, color, testId }: { label: string; value: string; color: string; testId: string }) {    const { colors } = useTheme();
  return (
    <View style={{ minWidth: 96 }} data-testid={testId} testID={testId}>
      <Text style={{ color: colors.textMuted, fontSize: 10, fontWeight: '700' }}>{label}</Text>
      <Text style={{ color, fontSize: 13, fontWeight: '800', marginTop: 3 }}>{value}</Text>
    </View>
  );
}

function SectionCard({ title, subtitle, children, colors, testId }: { title: string; subtitle: string; children: React.ReactNode; colors: any; testId: string }) {
  return (
    <View style={{ borderRadius: 18, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface, padding: 18, gap: 14 }} data-testid={testId} testID={testId}>
      <View>
        <Text style={{ color: colors.text, fontSize: 16, fontWeight: '700' }}>{title}</Text>
        <Text style={{ color: colors.textMuted, fontSize: 12, marginTop: 4 }}>{subtitle}</Text>
      </View>
      {children}
    </View>
  );
}

function EmptyState({ colors, label, icon, testId }: { colors: any; label: string; icon: string; testId: string }) {
  return (
    <View style={{ alignItems: 'center', paddingVertical: 20 }} data-testid={testId} testID={testId}>
      <Ionicons name={icon as any} size={28} color={colors.textMuted} />
      <Text style={{ color: colors.textMuted, fontSize: 12, marginTop: 8 }}>{label}</Text>
    </View>
  );
}

function Loader({ colors, label, testId }: { colors: any; label: string; testId: string }) {
  return (
    <View style={{ alignItems: 'center', justifyContent: 'center', paddingVertical: 48 }} data-testid={testId} testID={testId}>
      <ActivityIndicator size="large" color={colors.primary} />
      <Text style={{ color: colors.textMuted, fontSize: 12, marginTop: 12 }}>{label}</Text>
    </View>
  );
}

function heroCard(colors: any, darkMode: boolean) {
  return {
    borderRadius: 22,
    borderWidth: 1,
    borderColor: `${colors.primary}32`,
    padding: 20,
    backgroundColor: colors.surface,
    ...(darkMode ? { boxShadow: '0 8px 30px rgba(0,0,0,0.28)' } : { boxShadow: '0 10px 32px rgba(15,118,110,0.10)' }),
  } as any;
}