import React, { useCallback, useState } from 'react';
import { View, Text, TouchableOpacity, ActivityIndicator } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { useLiveQuery } from '../../hooks/useLiveQuery';
import { useTranslation } from '../../hooks/useTranslation';
import { useTheme } from '../../context/ThemeContext';

export function ThemeTokenRemediationPanel() {
  const { colors } = useTheme();
  const { t } = useTranslation();
  const tx = useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);
  const [running, setRunning] = useState(false);
  const [dryRunning, setDryRunning] = useState(false);
  const [note, setNote] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  const { data: latest, refetch } = useLiveQuery('/admin/autonomous-engine/theme-token-remediation/latest', {
    entity: 'theme-remediation-latest',
    pollInterval: 60000,
  });

  const { data: historyData, refetch: refetchHistory } = useLiveQuery('/admin/autonomous-engine/theme-token-remediation/history?limit=5', {
    entity: 'theme-remediation-history',
    pollInterval: 60000,
  });

  const runs = Array.isArray(historyData?.runs) ? historyData.runs : [];

  const runRemediation = useCallback(async (dryRun: boolean) => {
    dryRun ? setDryRunning(true) : setRunning(true);
    setNote(null);
    try {
      const res = await api.post('/admin/autonomous-engine/theme-token-remediation/run', { dry_run: dryRun, max_fixes: 50 });
      const d = res.data || {};
      setNote({
        type: 'success',
        text: `${dryRun ? 'Dry run' : 'Remediation'} complete: ${d.total_findings || 0} findings, ${d.total_applied || 0} fixed across ${d.files_with_fixes || 0} files`,
      });
      await Promise.all([refetch(), refetchHistory()]);
    } catch (e: any) {
      setNote({ type: 'error', text: e?.response?.data?.detail || 'Remediation failed.' });
    }
    dryRun ? setDryRunning(false) : setRunning(false);
  }, [refetch, refetchHistory]);

  const fmtDate = (v?: string) => {
    if (!v) return '--';
    const d = new Date(v);
    return isNaN(d.getTime()) ? '--' : d.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
  };

  return (
    <View style={{ backgroundColor: colors.card, borderRadius: 18, borderWidth: 1, borderColor: colors.border, padding: 18, gap: 14 }} data-testid="theme-remediation-panel" testID="theme-remediation-panel">
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12, flexWrap: 'wrap' }}>
        <View style={{ flex: 1, minWidth: 220 }}>
          <Text style={{ color: colors.text, fontSize: 15, fontWeight: '800' }} data-testid="theme-remediation-title" testID="theme-remediation-title">{tx('admin.themeTokenRemediationPanel.auto.text.001', 'Auto-Remediation Engine')}</Text>
          <Text style={{ color: colors.textMuted, fontSize: 11, marginTop: 3 }}>{tx('admin.themeTokenRemediationPanel.auto.text.002', 'Scans files for hardcoded dark tokens and auto-replaces with dynamic theme tokens. Runs automatically during nightly drift detection.')}</Text>
        </View>
        <View style={{ flexDirection: 'row', gap: 6 }}>
          <TouchableOpacity
            onPress={() => runRemediation(true)}
            disabled={dryRunning || running}
            style={{ flexDirection: 'row', alignItems: 'center', gap: 5, paddingHorizontal: 12, paddingVertical: 7, borderRadius: 10, backgroundColor: colors.bgSoft, borderWidth: 1, borderColor: colors.border, opacity: dryRunning ? 0.6 : 1 }}
            data-testid="theme-remediation-dry-run-btn" testID="theme-remediation-dry-run-btn"
          >
            {dryRunning ? <ActivityIndicator size="small" color={colors.textSec} /> : <Ionicons name="eye-outline" size={13} color={colors.textSec} />}
            <Text style={{ color: colors.textSec, fontSize: 11, fontWeight: '700' }}>{dryRunning ? 'Scanning...' : 'Preview'}</Text>
          </TouchableOpacity>
          <TouchableOpacity
            onPress={() => runRemediation(false)}
            disabled={running || dryRunning}
            style={{ flexDirection: 'row', alignItems: 'center', gap: 5, paddingHorizontal: 12, paddingVertical: 7, borderRadius: 10, backgroundColor: running ? `${colors.primary}44` : colors.primary, opacity: running ? 0.7 : 1 }}
            data-testid="theme-remediation-fix-btn" testID="theme-remediation-fix-btn"
          >
            {running ? <ActivityIndicator size="small" color={colors.primaryText} /> : <Ionicons name="hammer-outline" size={13} color={colors.primaryText} />}
            <Text style={{ color: colors.primaryText, fontSize: 11, fontWeight: '800' }}>{running ? 'Fixing...' : 'Auto-Fix Now'}</Text>
          </TouchableOpacity>
        </View>
      </View>

      {note && (
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, padding: 10, borderRadius: 10, backgroundColor: note.type === 'success' ? `${colors.success || colors.success}14` : `${colors.error || colors.error}14`, borderWidth: 1, borderColor: note.type === 'success' ? `${colors.success}35` : `${colors.error}35` }} data-testid="theme-remediation-note" testID="theme-remediation-note">
          <Ionicons name={note.type === 'success' ? 'checkmark-circle' : 'alert-circle'} size={14} color={note.type === 'success' ? colors.success : colors.error} />
          <Text style={{ color: colors.text, fontSize: 11, fontWeight: '600', flex: 1 }}>{note.text}</Text>
          <TouchableOpacity onPress={() => setNote(null)} accessibilityLabel={tx('admin.themeTokenRemediationPanel.auto.accessibility.001', 'Close remediation note')}><Ionicons name="close" size={12} color={colors.textMuted} /></TouchableOpacity>
        </View>
      )}

      {/* Latest run stats */}
      {latest?.run_id && (
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }} data-testid="theme-remediation-latest-stats" testID="theme-remediation-latest-stats">
          {[
            { label: 'Last Run', value: fmtDate(latest.completed_at), color: colors.text },
            { label: 'Findings', value: String(latest.total_findings || 0), color: (latest.total_findings || 0) > 0 ? (colors.warning || colors.warning) : (colors.success || colors.success) },
            { label: 'Applied', value: String(latest.total_applied || 0), color: (latest.total_applied || 0) > 0 ? (colors.success || colors.success) : colors.textSec },
            { label: 'Files Fixed', value: String(latest.files_with_fixes || 0), color: colors.text },
            { label: 'Mode', value: latest.dry_run ? 'Preview' : 'Live', color: latest.dry_run ? (colors.warning || colors.warning) : (colors.success || colors.success) },
          ].map((item, i) => (
            <View key={i} style={{ flex: 1, minWidth: 90, backgroundColor: colors.bgSoft, borderRadius: 10, padding: 10, borderWidth: 1, borderColor: colors.border }}>
              <Text style={{ color: colors.textMuted, fontSize: 9, fontWeight: '700', textTransform: 'uppercase' }}>{item.label}</Text>
              <Text style={{ color: item.color, fontSize: 14, fontWeight: '800', marginTop: 3 }}>{item.value}</Text>
            </View>
          ))}
        </View>
      )}

      {/* Token breakdown */}
      {latest?.token_stats && Object.keys(latest.token_stats).some((k: string) => (latest.token_stats as any)[k] > 0) && (
        <View style={{ gap: 6 }}>
          <Text style={{ color: colors.textMuted, fontSize: 10, fontWeight: '700', textTransform: 'uppercase' }}>{tx('admin.themeTokenRemediationPanel.auto.text.003', 'Token Breakdown')}</Text>
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6 }}>
            {Object.entries(latest.token_stats as Record<string, number>)
              .filter(([, count]) => count > 0)
              .sort(([, a], [, b]) => b - a)
              .map(([token, count]) => (
                <View key={token} style={{ flexDirection: 'row', alignItems: 'center', gap: 4, paddingHorizontal: 8, paddingVertical: 4, borderRadius: 8, backgroundColor: colors.bgSoft, borderWidth: 1, borderColor: colors.border }}>
                  <View style={{ width: 10, height: 10, borderRadius: 3, backgroundColor: token }} />
                  <Text style={{ color: colors.textSec, fontSize: 10, fontWeight: '600' }}>{token}</Text>
                  <Text style={{ color: colors.warningText || colors.warning, fontSize: 10, fontWeight: '800' }}>{count}</Text>
                </View>
              ))}
          </View>
        </View>
      )}

      {/* History */}
      {runs.length > 0 && (
        <View style={{ gap: 6 }} data-testid="theme-remediation-history" testID="theme-remediation-history">
          <Text style={{ color: colors.textMuted, fontSize: 10, fontWeight: '700', textTransform: 'uppercase' }}>{tx('admin.themeTokenRemediationPanel.auto.text.004', 'Recent Runs')}</Text>
          {runs.slice(0, 4).map((run: any, idx: number) => (
            <View key={run.run_id || idx} style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingVertical: 5, borderBottomWidth: idx < Math.min(runs.length, 4) - 1 ? 1 : 0, borderBottomColor: colors.border }} data-testid={`theme-remediation-run-${idx}`} testID={`theme-remediation-run-${idx}`}>
              <Text style={{ color: colors.textSec, fontSize: 10, flex: 1 }}>{fmtDate(run.completed_at)}</Text>
              <Text style={{ color: colors.textSec, fontSize: 10, width: 70, textAlign: 'center' }}>{run.total_findings || 0} found</Text>
              <Text style={{ color: (run.total_applied || 0) > 0 ? (colors.success || colors.success) : colors.textMuted, fontSize: 10, width: 60, textAlign: 'center', fontWeight: '700' }}>{run.total_applied || 0} fixed</Text>
              <View style={{ paddingHorizontal: 6, paddingVertical: 2, borderRadius: 999, backgroundColor: run.dry_run ? `${colors.warning || colors.warning}18` : `${colors.success || colors.success}18` }}>
                <Text style={{ color: run.dry_run ? colors.warning : colors.success, fontSize: 9, fontWeight: '800' }}>{run.dry_run ? 'PREVIEW' : 'LIVE'}</Text>
              </View>
            </View>
          ))}
        </View>
      )}
    </View>
  );
}
