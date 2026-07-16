import React, { useCallback, useEffect, useState } from 'react';
import { ActivityIndicator, ScrollView, Text, TouchableOpacity, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { useTheme } from '../../context/ThemeContext';
import { useTranslation } from '../../hooks/useTranslation';

type Report = any;

export function V2ComplianceGuardrailPanel() {
  const { colors } = useTheme();
  const { t } = useTranslation();
  const tx = useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);
  const [report, setReport] = useState<Report | null>(null);
  const [history, setHistory] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [reportRes, historyRes] = await Promise.all([
        api.get('/admin/platform-perf/v2-compliance/report', { silentLoading: true }),
        api.get('/admin/platform-perf/v2-compliance/report/history?limit=5', { silentLoading: true }),
      ]);
      setReport(reportRes.data || null);
      setHistory(Array.isArray(historyRes.data?.runs) ? historyRes.data.runs : []);
      setMessage(null);
    } catch (e: any) {
      setMessage({ type: 'error', text: e?.response?.data?.detail || 'Unable to load V2 compliance report.' });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  const runReport = useCallback(async () => {
    setRunning(true);
    try {
      const res = await api.post('/admin/platform-perf/v2-compliance/report/run', {}, { silentLoading: true });
      setReport(res.data || null);
      setMessage({ type: 'success', text: 'Fresh V2 compliance scan completed.' });
      await load();
    } catch (e: any) {
      setMessage({ type: 'error', text: e?.response?.data?.detail || 'Unable to run V2 compliance scan.' });
    } finally {
      setRunning(false);
    }
  }, [load]);

  const statusTone = report?.status === 'healthy' ? colors.success : report?.status === 'warning' ? colors.warning : colors.error;

  return (
    <View style={{ backgroundColor: colors.card, borderRadius: 18, borderWidth: 1, borderColor: colors.border, padding: 18, gap: 14 }} data-testid="v2-compliance-guardrail-panel" testID="v2-compliance-guardrail-panel">
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12, flexWrap: 'wrap' }}>
        <View style={{ flex: 1, minWidth: 220 }}>
          <Text style={{ color: colors.text, fontSize: 15, fontWeight: '800' }} data-testid="v2-compliance-guardrail-title" testID="v2-compliance-guardrail-title">{tx('admin.v2ComplianceGuardrail.header.title', 'V2 Compliance Guardrail')}</Text>
          <Text style={{ color: colors.textMuted, fontSize: 12, marginTop: 4 }} data-testid="v2-compliance-guardrail-copy" testID="v2-compliance-guardrail-copy">
            {tx('admin.v2ComplianceGuardrail.header.subtitle', 'Reusable fail-fast checker for off-brand colors, route blockers, and theme-token drift signals.')}
          </Text>
        </View>
        <View style={{ flexDirection: 'row', gap: 8, flexWrap: 'wrap' }}>
          <TouchableOpacity onPress={() => void load()} style={{ paddingHorizontal: 12, paddingVertical: 8, borderRadius: 10, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bgSoft }} data-testid="v2-compliance-refresh-button" testID="v2-compliance-refresh-button">
            <Text style={{ color: colors.text, fontSize: 11, fontWeight: '700' }}>{tx('admin.v2ComplianceGuardrail.actions.refresh', 'Refresh')}</Text>
          </TouchableOpacity>
          <TouchableOpacity onPress={() => void runReport()} disabled={running} style={{ paddingHorizontal: 12, paddingVertical: 8, borderRadius: 10, backgroundColor: colors.primary, opacity: running ? 0.7 : 1 }} data-testid="v2-compliance-run-button" testID="v2-compliance-run-button">
            <Text style={{ color: colors.primaryText, fontSize: 11, fontWeight: '800' }}>{running ? 'Scanning…' : 'Run Scan'}</Text>
          </TouchableOpacity>
        </View>
      </View>

      {message ? (
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, padding: 10, borderRadius: 10, borderWidth: 1, borderColor: `${message.type === 'success' ? colors.success : colors.error}35`, backgroundColor: `${message.type === 'success' ? colors.success : colors.error}14` }} data-testid="v2-compliance-message" testID="v2-compliance-message">
          <Ionicons name={message.type === 'success' ? 'checkmark-circle' : 'alert-circle'} size={15} color={message.type === 'success' ? colors.success : colors.error} />
          <Text style={{ color: colors.text, fontSize: 11, fontWeight: '600', flex: 1 }}>{message.text}</Text>
        </View>
      ) : null}

      {loading ? (
        <View style={{ paddingVertical: 18, alignItems: 'center' }} data-testid="v2-compliance-loading" testID="v2-compliance-loading">
          <ActivityIndicator color={colors.primary} />
        </View>
      ) : (
        <>
          <View style={{ flexDirection: 'row', gap: 10, flexWrap: 'wrap' }}>
            {[
              { id: 'status', label: 'Status', value: String(report?.status || 'unknown').toUpperCase(), tone: statusTone },
              { id: 'score', label: 'Score', value: String(report?.score ?? '--'), tone: colors.text },
              { id: 'blockers', label: 'Blocking Files', value: String(report?.summary?.files_with_blockers ?? 0), tone: colors.error },
              { id: 'routes', label: 'Blocked Routes', value: String(report?.summary?.blocking_routes_count ?? 0), tone: colors.warning },
              { id: 'tokens', label: 'Theme Drift Warnings', value: String(report?.summary?.theme_visibility_warn_count ?? 0), tone: colors.textSec },
            ].map((item) => (
              <View key={item.id} style={{ flex: 1, minWidth: 140, backgroundColor: colors.bgSoft, borderRadius: 12, borderWidth: 1, borderColor: colors.border, padding: 12 }} data-testid={`v2-compliance-metric-${item.id}`} testID={`v2-compliance-metric-${item.id}`}>
                <Text style={{ color: colors.textMuted, fontSize: 10, fontWeight: '700', textTransform: 'uppercase' }}>{item.label}</Text>
                <Text style={{ color: item.tone, fontSize: 18, fontWeight: '800', marginTop: 6 }}>{item.value}</Text>
              </View>
            ))}
          </View>

          <View style={{ gap: 10 }}>
            <Text style={{ color: colors.text, fontSize: 13, fontWeight: '800' }} data-testid="v2-compliance-routes-title" testID="v2-compliance-routes-title">{tx('admin.v2ComplianceGuardrail.routes.title', 'Runtime blocked routes')}</Text>
            <View style={{ flexDirection: 'row', gap: 8, flexWrap: 'wrap' }} data-testid="v2-compliance-routes-list" testID="v2-compliance-routes-list">
              {(report?.blocking_routes || []).length === 0 ? (
                <Text style={{ color: colors.textMuted, fontSize: 12 }}>{tx('admin.v2ComplianceGuardrail.routes.empty', 'No route-level blockers right now.')}</Text>
              ) : (report?.blocking_routes || []).map((route: string) => (
                <View key={route} style={{ paddingHorizontal: 10, paddingVertical: 6, borderRadius: 999, backgroundColor: `${colors.error}14`, borderWidth: 1, borderColor: `${colors.error}35` }} data-testid={`v2-compliance-route-${route.replace(/[^a-z0-9]+/gi, '-').toLowerCase()}`} testID={`v2-compliance-route-${route.replace(/[^a-z0-9]+/gi, '-').toLowerCase()}`}>
                  <Text style={{ color: colors.error, fontSize: 10, fontWeight: '800' }}>{route}</Text>
                </View>
              ))}
            </View>
          </View>

          <ScrollView style={{ maxHeight: 240 }} contentContainerStyle={{ gap: 10 }} data-testid="v2-compliance-blockers-list" testID="v2-compliance-blockers-list">
            {(report?.top_blockers || []).length === 0 ? (
              <Text style={{ color: colors.textMuted, fontSize: 12 }}>{tx('admin.v2ComplianceGuardrail.blockers.empty', 'No blocking files found in the latest scan.')}</Text>
            ) : (report?.top_blockers || []).map((item: any, index: number) => (
              <View key={`${item.file}-${index}`} style={{ backgroundColor: colors.bgSoft, borderRadius: 12, borderWidth: 1, borderColor: colors.border, padding: 12 }} data-testid={`v2-compliance-blocker-${index}`} testID={`v2-compliance-blocker-${index}`}>
                <View style={{ flexDirection: 'row', justifyContent: 'space-between', gap: 10 }}>
                  <Text style={{ color: colors.text, fontSize: 12, fontWeight: '700', flex: 1 }}>{item.file}</Text>
                  <Text style={{ color: colors.error, fontSize: 11, fontWeight: '800' }}>{item.fail_count} fails</Text>
                </View>
                {(item.issues || []).slice(0, 2).map((issue: any, issueIndex: number) => (
                  <Text key={`${item.file}-${issueIndex}`} style={{ color: colors.textMuted, fontSize: 11, marginTop: 6 }}>
                    Line {issue.line}: {issue.message}
                  </Text>
                ))}
              </View>
            ))}
          </ScrollView>

          <View style={{ gap: 8 }}>
            <Text style={{ color: colors.text, fontSize: 13, fontWeight: '800' }} data-testid="v2-compliance-history-title" testID="v2-compliance-history-title">{tx('admin.v2ComplianceGuardrail.history.title', 'Recent scans')}</Text>
            {(history || []).length === 0 ? (
              <Text style={{ color: colors.textMuted, fontSize: 12 }}>{tx('admin.v2ComplianceGuardrail.history.empty', 'No persisted scans yet. Run the checker once to create history.')}</Text>
            ) : history.map((run, index) => (
              <View key={run.run_id || index} style={{ flexDirection: 'row', justifyContent: 'space-between', gap: 10, paddingVertical: 8, borderBottomWidth: index < history.length - 1 ? 1 : 0, borderBottomColor: colors.border }} data-testid={`v2-compliance-history-${index}`} testID={`v2-compliance-history-${index}`}>
                <Text style={{ color: colors.textSec, fontSize: 11, flex: 1 }}>{run.run_id}</Text>
                <Text style={{ color: run.status === 'healthy' ? colors.success : run.status === 'warning' ? colors.warning : colors.error, fontSize: 11, fontWeight: '800' }}>{String(run.status || 'unknown').toUpperCase()}</Text>
                <Text style={{ color: colors.textMuted, fontSize: 11 }}>Score {run.score ?? '--'}</Text>
              </View>
            ))}
          </View>
        </>
      )}
    </View>
  );
}