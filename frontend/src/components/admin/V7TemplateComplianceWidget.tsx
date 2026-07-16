import { useTranslation } from '../../hooks/useTranslation';
import React, { useEffect, useState, useCallback } from 'react';
import { View, Text, TouchableOpacity, ActivityIndicator } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useTheme } from '../../context/ThemeContext';
import api from '../../services/api';
import { handleAppRecoverableError } from '../../utils/appRecoverableError';

interface V7SummaryData {
  v7_active: boolean;
  total_open: number;
  total_resolved: number;
  by_severity: Record<string, number>;
  baseline: { locked_at: string } | null;
  isolation: string;
  domains: { v2: string; v7: string };
}

interface V7Violation {
  template_name: string;
  rule: string;
  message: string;
  severity: string;
  created_at: string;
}

interface ComplianceCounterData {
  catalog: { total_templates: number; total_palettes: number; by_category: Record<string, number> };
  bypass_scan: { compliant_senders: number; bypass_senders: number; compliance_pct: number; bypass_files: string[] };
  guardrail: { active: boolean; mode: string; fingerprint_check: boolean; template_key_required: boolean };
  violations: { open: number; resolved: number };
  grade: string;
}

export function V7TemplateComplianceWidget() {
  const { colors, darkMode } = useTheme();
  const { t } = useTranslation();
  const tx = useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);
  const [data, setData] = useState<V7SummaryData | null>(null);
  const [counter, setCounter] = useState<ComplianceCounterData | null>(null);
  const [violations, setViolations] = useState<V7Violation[]>([]);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState(false);

  const fetchData = useCallback(async () => {
    try {
      setLoading(true);
      const [summaryRes, violRes, counterRes] = await Promise.all([
        api.get('/admin/v7-templates/summary', { silentLoading: true }),
        api.get('/admin/v7-templates/violations?limit=5', { silentLoading: true }),
        api.get('/admin/v7-templates/compliance-counter', { silentLoading: true }),
      ]);
      setData(summaryRes.data || summaryRes);
      const vData = violRes.data || violRes;
      setViolations(vData.violations || []);
      setCounter(counterRes.data || counterRes);
    } catch (error) { handleAppRecoverableError({ scope: 'src/components/admin/V7TemplateComplianceWidget.tsx#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);

  const resolveAll = useCallback(async () => {
    try {
      await api.post('/admin/v7-templates/resolve', { all: true });
      await fetchData();
    } catch { /* silent */ }
  }, [fetchData]);

  if (loading && !data) {
    return (
      <View style={{ backgroundColor: colors.card, borderWidth: 1, borderColor: colors.border, borderRadius: 12, padding: 14 }}
        data-testid="v7-compliance-widget-loading" testID="v7-compliance-widget-loading">
        <ActivityIndicator size="small" color={colors.primary} />
      </View>
    );
  }

  if (!data) return null;

  const hasViolations = data.total_open > 0;
  const criticalCount = data.by_severity?.critical || 0;
  const highCount = data.by_severity?.high || 0;
  const warnCount = data.by_severity?.warn || 0;

  const statusColor = hasViolations
    ? (criticalCount > 0 ? colors.error : highCount > 0 ? colors.warning : colors.primary)
    : colors.success;

  return (
    <View
      style={{
        backgroundColor: colors.card,
        borderWidth: 1,
        borderColor: hasViolations ? statusColor : colors.border,
        borderRadius: 12,
        padding: 14,
        minWidth: 280,
        maxWidth: 420,
        flex: 1,
      }}
      data-testid="v7-compliance-widget"
      testID="v7-compliance-widget"
    >
      {/* Header */}
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
          <View style={{ width: 18, height: 18, borderRadius: 9, backgroundColor: colors.info, alignItems: 'center', justifyContent: 'center' }}>
            <Text style={{ color: colors.primaryText, fontSize: 8, fontWeight: '900' }}>V7</Text>
          </View>
          <Text style={{ color: colors.text, fontSize: 12, fontWeight: '700' }}
            data-testid="v7-compliance-title" testID="v7-compliance-title">{tx('admin.v7TemplateComplianceWidget.auto.text.001', 'Template Compliance')}</Text>
        </View>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4,
          backgroundColor: (globalThis as any).__alphaColor(statusColor, '18'), paddingHorizontal: 7, paddingVertical: 3, borderRadius: 6 }}>
          <View style={{ width: 6, height: 6, borderRadius: 3, backgroundColor: statusColor }} />
          <Text style={{ color: statusColor, fontSize: 9, fontWeight: '700' }}
            data-testid="v7-compliance-status-label" testID="v7-compliance-status-label">
            {hasViolations ? 'Violations Found' : 'Compliant'}
          </Text>
        </View>
      </View>

      {/* Isolation badge */}
      <View style={{
        flexDirection: 'row', alignItems: 'center', gap: 8,
        backgroundColor: colors.card,
        borderRadius: 8, padding: 8, marginBottom: 10,
      }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4, flex: 1 }}>
          <Ionicons name="git-branch-outline" size={11} color={colors.primary} />
          <Text style={{ color: colors.textMuted, fontSize: 9, fontWeight: '600' }}>{tx('admin.v7TemplateComplianceWidget.auto.text.002', 'V7 Templates')}</Text>
        </View>
        <View style={{ width: 1, height: 12, backgroundColor: colors.border }} />
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4, flex: 1 }}>
          <Ionicons name="lock-closed" size={9} color={colors.textMuted} />
          <Text style={{ color: colors.textMuted, fontSize: 9, fontWeight: '600' }}>{tx('admin.v7TemplateComplianceWidget.auto.text.003', 'Isolated from V2')}</Text>
        </View>
      </View>

      {/* Metrics row */}
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginBottom: 10 }}>
        <View style={{ alignItems: 'center', flex: 1 }}>
          <Text style={{ color: hasViolations ? statusColor : colors.success, fontSize: 20, fontWeight: '800' }}
            data-testid="v7-compliance-open-count" testID="v7-compliance-open-count">
            {data.total_open}
          </Text>
          <Text style={{ color: colors.textMuted, fontSize: 9, fontWeight: '600' }}>{tx('admin.v7TemplateComplianceWidget.auto.text.004', 'Open')}</Text>
        </View>
        <View style={{ alignItems: 'center', flex: 1 }}>
          <Text style={{ color: colors.success, fontSize: 20, fontWeight: '800' }}
            data-testid="v7-compliance-resolved-count" testID="v7-compliance-resolved-count">
            {data.total_resolved}
          </Text>
          <Text style={{ color: colors.textMuted, fontSize: 9, fontWeight: '600' }}>{tx('admin.v7TemplateComplianceWidget.auto.text.005', 'Resolved')}</Text>
        </View>
        <View style={{ alignItems: 'center', flex: 1 }}>
          <Text style={{ color: criticalCount > 0 ? colors.error : colors.textMuted, fontSize: 20, fontWeight: '800' }}
            data-testid="v7-compliance-critical-count" testID="v7-compliance-critical-count">
            {criticalCount}
          </Text>
          <Text style={{ color: colors.textMuted, fontSize: 9, fontWeight: '600' }}>{tx('admin.v7TemplateComplianceWidget.auto.text.006', 'Critical')}</Text>
        </View>
      </View>

      {/* Severity breakdown bar */}
      {hasViolations && (
        <View style={{ marginBottom: 10 }}>
          <Text style={{ color: colors.textMuted, fontSize: 9, fontWeight: '600', marginBottom: 4 }}>{tx('admin.v7TemplateComplianceWidget.auto.text.007', 'By Severity')}</Text>
          <View style={{ flexDirection: 'row', gap: 6 }}>
            {criticalCount > 0 && (
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 3, backgroundColor: (globalThis as any).__alphaColor(colors.error, '18'), paddingHorizontal: 6, paddingVertical: 2, borderRadius: 4 }}>
                <View style={{ width: 5, height: 5, borderRadius: 3, backgroundColor: colors.error }} />
                <Text style={{ color: colors.error, fontSize: 9, fontWeight: '700' }}>{criticalCount} critical</Text>
              </View>
            )}
            {highCount > 0 && (
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 3, backgroundColor: (globalThis as any).__alphaColor(colors.warning, '18'), paddingHorizontal: 6, paddingVertical: 2, borderRadius: 4 }}>
                <View style={{ width: 5, height: 5, borderRadius: 3, backgroundColor: colors.warning }} />
                <Text style={{ color: colors.warning, fontSize: 9, fontWeight: '700' }}>{highCount} high</Text>
              </View>
            )}
            {warnCount > 0 && (
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 3, backgroundColor: (globalThis as any).__alphaColor(colors.info, '18'), paddingHorizontal: 6, paddingVertical: 2, borderRadius: 4 }}>
                <View style={{ width: 5, height: 5, borderRadius: 3, backgroundColor: colors.info }} />
                <Text style={{ color: colors.info, fontSize: 9, fontWeight: '700' }}>{warnCount} warn</Text>
              </View>
            )}
          </View>
        </View>
      )}

      {/* Compliance Counter */}
      {counter && (
        <View style={{ marginBottom: 10 }} data-testid="v7-compliance-counter" testID="v7-compliance-counter">
          <View style={{
            flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center',
            backgroundColor: counter.grade === 'A' ? colors.successSoft : colors.errorSoft,
            borderRadius: 8, padding: 8, marginBottom: 6,
          }}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
              <View style={{
                width: 28, height: 28, borderRadius: 14,
                backgroundColor: counter.grade === 'A' ? colors.success : counter.grade === 'B' ? colors.warning : colors.error,
                alignItems: 'center', justifyContent: 'center',
              }}>
                <Text style={{ color: colors.primaryText, fontSize: 12, fontWeight: '900' }}
                  data-testid="v7-counter-grade" testID="v7-counter-grade">
                  {counter.grade}
                </Text>
              </View>
              <View>
                <Text style={{ color: counter.grade === 'A' ? colors.success : colors.error, fontSize: 10, fontWeight: '700' }}>
                  {counter.bypass_scan.compliance_pct}% Compliant
                </Text>
                <Text style={{ color: colors.textMuted, fontSize: 8 }}>
                  {counter.catalog.total_templates} templates / {counter.catalog.total_palettes} palettes
                </Text>
              </View>
            </View>
            <View style={{ alignItems: 'flex-end' }}>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 3 }}>
                <Ionicons name={counter.guardrail.active ? 'lock-closed' : 'lock-open'} size={9} color={counter.guardrail.active ? colors.success : colors.error} />
                <Text style={{ color: counter.guardrail.active ? colors.success : colors.error, fontSize: 8, fontWeight: '700' }}>
                  {counter.guardrail.mode.toUpperCase()}
                </Text>
              </View>
              <Text style={{ color: colors.textMuted, fontSize: 8 }}>
                {counter.bypass_scan.compliant_senders} senders / {counter.bypass_scan.bypass_senders} bypass
              </Text>
            </View>
          </View>
        </View>
      )}

      {/* Recent violations (expandable) */}
      {violations.length > 0 && (
        <View style={{ marginBottom: 8 }}>
          <TouchableOpacity
            onPress={() => setExpanded(v => !v)}
            style={{ flexDirection: 'row', alignItems: 'center', gap: 4, marginBottom: 4 }}
            data-testid="v7-compliance-toggle-violations" testID="v7-compliance-toggle-violations"
          >
            <Ionicons name={expanded ? 'chevron-down' : 'chevron-forward'} size={10} color={colors.textMuted} />
            <Text style={{ color: colors.textMuted, fontSize: 9, fontWeight: '600' }}>
              Recent Violations ({violations.length})
            </Text>
          </TouchableOpacity>
          {expanded && violations.map((v, i) => (
            <View key={i} style={{
              backgroundColor: colors.card,
              borderRadius: 6, padding: 6, marginBottom: 3,
              borderLeftWidth: 3,
              borderLeftColor: v.severity === 'critical' ? colors.error : v.severity === 'high' ? colors.warning : colors.primary,
            }}
              data-testid={`v7-violation-item-${i}`} testID={`v7-violation-item-${i}`}
            >
              <Text style={{ color: colors.text, fontSize: 10, fontWeight: '600' }} numberOfLines={1}>
                {v.template_name}
              </Text>
              <Text style={{ color: colors.textMuted, fontSize: 9 }} numberOfLines={1}>
                {v.message}
              </Text>
            </View>
          ))}
        </View>
      )}

      {/* Footer: actions + isolation info */}
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
        {hasViolations ? (
          <TouchableOpacity accessibilityLabel={tx('admin.v7TemplateComplianceWidget.auto.accessibility.001', 'Resolve all template issues')}
            onPress={resolveAll}
            style={{
              flexDirection: 'row', alignItems: 'center', gap: 4,
              backgroundColor: (globalThis as any).__alphaColor(colors.success, '18'), paddingHorizontal: 8, paddingVertical: 3, borderRadius: 6,
            }}
            data-testid="v7-compliance-resolve-all-btn" testID="v7-compliance-resolve-all-btn"
          >
            <Ionicons name="checkmark-circle" size={10} color={colors.success} />
            <Text style={{ color: colors.success, fontSize: 9, fontWeight: '700' }}>{tx('admin.v7TemplateComplianceWidget.auto.text.008', 'Resolve All')}</Text>
          </TouchableOpacity>
        ) : (
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}>
            <Ionicons name="shield-checkmark" size={10} color={colors.success} />
            <Text style={{ color: colors.success, fontSize: 9, fontWeight: '700' }}>{tx('admin.v7TemplateComplianceWidget.auto.text.009', 'All templates clean')}</Text>
          </View>
        )}
        <Text style={{ color: colors.textMuted, fontSize: 8 }}
          data-testid="v7-compliance-domain-label" testID="v7-compliance-domain-label">
          Domain: {data.domains?.v7 || 'templates'}
        </Text>
      </View>
    </View>
  );
}

export default V7TemplateComplianceWidget;
