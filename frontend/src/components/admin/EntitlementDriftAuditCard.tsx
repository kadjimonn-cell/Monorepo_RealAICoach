import React, { useMemo } from 'react';
import { ActivityIndicator, Text, TouchableOpacity, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useLiveQuery } from '../../hooks/useLiveQuery';
import { useTranslation } from '../../hooks/useTranslation';

type DriftLatest = {
  generated_at?: string;
  status?: string;
  title?: string;
  new_finding_count?: number;
  new_high_risk_count?: number;
  files_scanned?: number;
  baseline_established?: boolean;
};

type DriftPayload = {
  latest?: DriftLatest | null;
  total?: number;
  attention_count?: number;
  status_breakdown?: { pass?: number; warning?: number; fail?: number };
};

const statusTone = (status: string | undefined, colors: any) => {
  if (status === 'fail') return { color: colors.error, bg: `${colors.error}16`, icon: 'alert-circle' };
  if (status === 'warning') return { color: colors.warning, bg: `${colors.warning}16`, icon: 'warning' };
  return { color: colors.successText || colors.success, bg: `${colors.successText || colors.success}16`, icon: 'checkmark-circle' };
};

export default function EntitlementDriftAuditCard({
  colors,
  onNavigate,
}: {
  colors: any;
  onNavigate?: () => void;
}) {
  const { t } = useTranslation();
  const tx = React.useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);
  const { data, loading } = useLiveQuery<DriftPayload>('/admin/code-health/entitlement-drift/history?limit=5', {
    entity: 'code_health',
    pollInterval: 120000,
  });

  const latest = data?.latest || null;
  const tone = useMemo(() => statusTone(latest?.status, colors), [latest?.status, colors]);
  const attention = data?.attention_count || 0;
  const passRuns = data?.status_breakdown?.pass || 0;
  const warningRuns = data?.status_breakdown?.warning || 0;
  const failRuns = data?.status_breakdown?.fail || 0;

  if (loading) {
    return (
      <View style={{ borderRadius: 14, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, padding: 18 }} data-testid="entitlement-drift-card-loading" testID="entitlement-drift-card-loading">
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
          <ActivityIndicator size="small" color={colors.primary} />
          <Text style={{ color: colors.textMuted, fontSize: 12 }}>{tx('operationsConsole.entitlementDrift.cardLoading', 'Loading entitlement drift history...')}</Text>
        </View>
      </View>
    );
  }

  return (
    <TouchableOpacity
      onPress={onNavigate}
      activeOpacity={0.88}
      style={{
        borderRadius: 14,
        borderWidth: 1,
        borderColor: attention > 0 ? tone.color : colors.border,
        backgroundColor: colors.card,
        padding: 16,
        gap: 12,
      }}
      data-testid="entitlement-drift-card"
      testID="entitlement-drift-card"
    >
      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 10 }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, flex: 1 }}>
          <View style={{ width: 34, height: 34, borderRadius: 17, backgroundColor: tone.bg, alignItems: 'center', justifyContent: 'center' }}>
            <Ionicons name={tone.icon as any} size={18} color={tone.color} />
          </View>
          <View style={{ flex: 1 }}>
            <Text style={{ color: colors.text, fontSize: 14, fontWeight: '800' }} data-testid="entitlement-drift-card-title" testID="entitlement-drift-card-title">
              {tx('operationsConsole.entitlementDrift.cardTitle', 'Entitlement Drift Audit')}
            </Text>
            <Text style={{ color: colors.textMuted, fontSize: 10, marginTop: 2 }} data-testid="entitlement-drift-card-time" testID="entitlement-drift-card-time">
              {latest?.generated_at ? new Date(latest.generated_at).toLocaleString() : tx('operationsConsole.entitlementDrift.never', 'No completed runs yet')}
            </Text>
          </View>
        </View>
        <View style={{ borderRadius: 999, backgroundColor: tone.bg, paddingHorizontal: 8, paddingVertical: 4 }} data-testid="entitlement-drift-card-status-pill" testID="entitlement-drift-card-status-pill">
          <Text style={{ color: tone.color, fontSize: 10, fontWeight: '800', textTransform: 'uppercase' }} data-testid="entitlement-drift-card-status-pill-text" testID="entitlement-drift-card-status-pill-text">
            {latest?.status || 'unknown'}
          </Text>
        </View>
      </View>

      <Text style={{ color: colors.text, fontSize: 12, lineHeight: 18 }} data-testid="entitlement-drift-card-summary" testID="entitlement-drift-card-summary">
        {latest?.title || tx('operationsConsole.entitlementDrift.cardSummary', 'Daily guardrail against raw plan-read regressions across sensitive files.')}
      </Text>

      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
        {[
          { id: 'attention', label: 'needs attention', value: attention, color: tone.color },
          { id: 'new-findings', label: 'new findings', value: latest?.new_finding_count || 0, color: colors.primary },
          { id: 'high-risk', label: 'high risk', value: latest?.new_high_risk_count || 0, color: colors.error },
          { id: 'files-scanned', label: 'files scanned', value: latest?.files_scanned || 0, color: colors.warning },
        ].map((chip) => (
          <View key={chip.id} style={{ flex: 1, minWidth: 110, borderRadius: 12, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bg, padding: 10 }} data-testid={`entitlement-drift-card-chip-${chip.id}`} testID={`entitlement-drift-card-chip-${chip.id}`}>
            <Text style={{ color: colors.textMuted, fontSize: 10, fontWeight: '700', textTransform: 'uppercase' }}>{chip.label}</Text>
            <Text style={{ color: chip.color, fontSize: 17, fontWeight: '900', marginTop: 4 }}>{chip.value}</Text>
          </View>
        ))}
      </View>

      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 10, flexWrap: 'wrap' }}>
        <Text style={{ color: colors.textMuted, fontSize: 10 }} data-testid="entitlement-drift-card-breakdown" testID="entitlement-drift-card-breakdown">
          {tx('operationsConsole.entitlementDrift.cardBreakdown', 'Recent runs')} · {passRuns} pass · {warningRuns} warning · {failRuns} fail
        </Text>
        {onNavigate ? (
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }} data-testid="entitlement-drift-card-open-link" testID="entitlement-drift-card-open-link">
            <Text style={{ color: colors.primary, fontSize: 11, fontWeight: '700' }}>{tx('operationsConsole.entitlementDrift.openHistory', 'Open history')}</Text>
            <Ionicons name="arrow-forward" size={12} color={colors.primary} />
          </View>
        ) : null}
      </View>

      {latest?.baseline_established ? (
        <Text style={{ color: colors.textMuted, fontSize: 10 }} data-testid="entitlement-drift-card-baseline-note" testID="entitlement-drift-card-baseline-note">
          {tx('operationsConsole.entitlementDrift.cardBaseline', 'Latest run preserved the current baseline for future comparisons.')}
        </Text>
      ) : null}
    </TouchableOpacity>
  );
}