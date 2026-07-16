import React, { useState, useCallback } from 'react';
import { View, Text, TouchableOpacity, ActivityIndicator} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { useAdminTheme } from '../../hooks/useAdminTheme';
import { useTranslation } from '../../hooks/useTranslation';

const SEV_COLOR: Record<string, string> = {
  critical: 'var(--app-error)', high: 'var(--app-warning)', moderate: 'var(--app-primary)', low: 'var(--app-text-muted)', info: 'var(--app-primary)',
};

function Badge({ label, color }: { label: string; color: string }) {
  return (
    <View style={{ paddingHorizontal: 8, paddingVertical: 3, borderRadius: 6, backgroundColor: (globalThis as any).__alphaColor(color, '22'), borderWidth: 1, borderColor: (globalThis as any).__alphaColor(color, '44') }}>
      <Text style={{ fontSize: 10, fontWeight: '700', color, letterSpacing: 0.5 }}>{label.toUpperCase()}</Text>
    </View>
  );
}

function SummaryCard({ label, value, color, testID }: { label: string; value: number; color: string; testID?: string }) {
  const colors = useAdminTheme();
  return (
    <View style={{ flex: 1, backgroundColor: (globalThis as any).__alphaColor(color, '12'), borderRadius: 12, padding: 14, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(color, '30'), alignItems: 'center' }} testID={testID}>
      <Text style={{ fontSize: 26, fontWeight: '800', color, letterSpacing: -1 }}>{value}</Text>
      <Text style={{ fontSize: 10, fontWeight: '600', color: colors.textMuted, marginTop: 2 }}>{label}</Text>
    </View>
  );
}

function VulnRow({ vuln, index, T }: { vuln: any; index: number; T: any }) {
  const [expanded, setExpanded] = useState(false);
  const sev = vuln.severity || (vuln.description?.toLowerCase().includes('critical') ? 'critical' : vuln.description?.toLowerCase().includes('high') ? 'high' : 'moderate');
  const color = SEV_COLOR[sev] || SEV_COLOR.moderate;
  return (
    <TouchableOpacity onPress={() => setExpanded(!expanded)} style={{ borderBottomWidth: 1, borderBottomColor: T.border, paddingVertical: 10, paddingHorizontal: 14 }} data-testid={`vuln-row-${index}`}>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
        <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: color }} />
        <Text style={{ flex: 1, fontSize: 12, fontWeight: '600', color: T.text }}>{vuln.package || vuln.module_name || '?'}</Text>
        <Text style={{ fontSize: 11, color: T.textMuted }}>{vuln.installed || vuln.version || ''}</Text>
        <Badge label={sev} color={color} />
        <Ionicons name={expanded ? 'chevron-up' : 'chevron-down'} size={14} color={T.textMuted} />
      </View>
      {expanded && (
        <View style={{ marginTop: 8, paddingLeft: 18, gap: 4 }}>
          {vuln.id && <Text style={{ fontSize: 11, color: T.textMuted }}>ID: <Text style={{ color: T.primary }}>{vuln.id}</Text></Text>}
          {vuln.title && <Text style={{ fontSize: 11, color: T.textMuted }}>Issue: <Text style={{ color: T.text }}>{vuln.title}</Text></Text>}
          {vuln.description && <Text style={{ fontSize: 11, color: T.textMuted, lineHeight: 16 }}>{vuln.description.slice(0, 280)}</Text>}
          {vuln.fix && vuln.fix !== 'N/A' && <Text style={{ fontSize: 11, color: SEV_COLOR.low }}>Fix in: {vuln.fix}</Text>}
          {vuln.patched && vuln.patched !== 'N/A' && <Text style={{ fontSize: 11, color: SEV_COLOR.low }}>Patched: {vuln.patched}</Text>}
          {vuln.path && <Text style={{ fontSize: 10, color: T.textMuted, fontFamily: 'monospace' }}>{vuln.path}</Text>}
        </View>
      )}
    </TouchableOpacity>
  );
}

function HistoryBar({ scans, T }: { scans: any[]; T: any }) {
  if (!scans.length) return null;
  const maxV = Math.max(...scans.map(s => s.total_vulns || 0), 1);
  return (
    <View style={{ marginTop: 16, gap: 6 }}>
      <Text style={{ fontSize: 11, fontWeight: '700', color: T.textMuted, letterSpacing: 0.5 }}>SCAN HISTORY (LAST {scans.length})</Text>
      <View style={{ flexDirection: 'row', alignItems: 'flex-end', gap: 6, height: 64 }}>
        {[...scans].reverse().map((s, i) => {
          const h = Math.max(((s.total_vulns || 0) / maxV) * 56, 4);
          const c = s.risk_level === 'critical' ? SEV_COLOR.critical : s.risk_level === 'high' ? SEV_COLOR.high : s.risk_level === 'medium' ? SEV_COLOR.moderate : 'var(--app-success)';
          const label = new Date(s.timestamp).toLocaleDateString('en', { month: 'short', day: 'numeric' });
          return (
            <View key={i} style={{ flex: 1, alignItems: 'center', gap: 4 }}>
              <Text style={{ fontSize: 8, color: T.textMuted }}>{s.total_vulns || 0}</Text>
              <View style={{ width: '100%', height: h, backgroundColor: (globalThis as any).__alphaColor(c, '88'), borderRadius: 3, borderTopWidth: 2, borderTopColor: c }} />
              <Text style={{ fontSize: 7, color: T.textMuted }}>{label}</Text>
            </View>
          );
        })}
      </View>
    </View>
  );
}

export default function DependencyScanPanel({ T }: { T: any }) {
  const colors = useAdminTheme();
  const { t } = useTranslation();
  const tx = React.useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);
  const [scanResult, setScanResult] = useState<any>(null);
  const [history, setHistory] = useState<any[]>([]);
  const [scanning, setScanning] = useState(false);
  const [loadingHistory, setLoadingHistory] = useState(false);
  const [beTab, setBeTab] = useState(true);
  const [error, setError] = useState('');

  const loadHistory = useCallback(async () => {
    setLoadingHistory(true);
    try {
      const r = await api.get('/admin/security/dependency-scan/history');
      setHistory(r.data.history || []);
    } catch { /* silent */ } finally {
      setLoadingHistory(false);
    }
  }, []);

  React.useEffect(() => { loadHistory(); }, [loadHistory]);

  const runScan = useCallback(async () => {
    setScanning(true);
    setError('');
    try {
      const r = await api.get('/admin/security/dependency-scan');
      setScanResult(r.data);
      loadHistory();
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Scan failed. Check server logs.');
    } finally {
      setScanning(false);
    }
  }, [loadHistory]);

  const lastScan = scanResult || history[0];
  const overall = lastScan?.overall || {};
  const risk = overall.risk_level || lastScan?.risk_level || 'unknown';
  const riskColor = SEV_COLOR[risk === 'medium' ? 'moderate' : risk] || 'var(--app-text-muted)';
  const beVulns: any[] = (scanResult || history[0])?.backend_vulns || [];
  const feVulns: any[] = (scanResult || history[0])?.frontend_vulns || [];
  const beSummary = (scanResult || history[0])?.backend_summary || {};
  const feSummary = (scanResult || history[0])?.frontend_summary || {};
  const scanTime = lastScan?.timestamp || lastScan?.scan_timestamp;

  // Next scheduled: 1st of next month
  const now = new Date();
  const nextScan = new Date(now.getFullYear(), now.getMonth() + 1, 1, 4, 0, 0);

  return (
    <View style={{ flex: 1 }} data-testid="dependency-scan-panel">
      {/* Header */}
      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
        <View style={{ gap: 2 }}>
          <Text style={{ fontSize: 16, fontWeight: '800', color: T.text }}>{tx('admin.dependencyScan.title', 'Dependency Scan')}</Text>
          <Text style={{ fontSize: 11, color: T.textMuted }}>
            {scanTime ? `Last run: ${new Date(scanTime).toLocaleString()}` : 'No scans yet'}
            {'  ·  '}Next: {nextScan.toLocaleDateString('en', { month: 'short', day: 'numeric', year: 'numeric' })} 04:00 UTC
          </Text>
        </View>
        <TouchableOpacity
          onPress={runScan}
          disabled={scanning}
          style={{ flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 14, paddingVertical: 8, borderRadius: 10, backgroundColor: scanning ? T.border : T.primary, opacity: scanning ? 0.7 : 1 }}
          data-testid="run-scan-button" testID="run-scan-button"
        >
          {scanning ? <ActivityIndicator size="small" color="var(--app-primary-text)" /> : <Ionicons name="shield-checkmark-outline" size={15} color="var(--app-primary-text)" />}
          <Text style={{ fontSize: 12, fontWeight: '700', color: colors.primaryText }}>{scanning ? 'Scanning…' : 'Run Scan Now'}</Text>
        </TouchableOpacity>
      </View>

      {error ? (
        <View style={{ backgroundColor: colors.errorSoft, borderRadius: 10, padding: 12, marginBottom: 12, borderWidth: 1, borderColor: colors.errorSoft }}>
          <Text style={{ fontSize: 12, color: colors.error }}>{error}</Text>
        </View>
      ) : null}

      {scanning && (
        <View style={{ alignItems: 'center', paddingVertical: 32, gap: 10 }}>
          <ActivityIndicator size="large" color={T.primary} />
          <Text style={{ fontSize: 13, color: T.textMuted }}>{tx('admin.dependencyScan.running', 'Running pip-audit and yarn audit…')}</Text>
          <Text style={{ fontSize: 11, color: T.textMuted }}>{tx('admin.dependencyScan.runningHint', 'This may take 60–120 seconds')}</Text>
        </View>
      )}

      {!scanning && lastScan && (
        <>
          {/* Risk badge + summary cards */}
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 14 }}>
            <Badge label={`${risk} risk`} color={riskColor} />
            <Text style={{ fontSize: 11, color: T.textMuted }}>
              {overall.total_vulnerabilities ?? lastScan?.total_vulns ?? 0} total  ·  {overall.critical_count ?? lastScan?.critical ?? 0} critical  ·  {overall.high_count ?? lastScan?.high ?? 0} high
            </Text>
          </View>

          <View style={{ flexDirection: 'row', gap: 10, marginBottom: 16 }}>
            <SummaryCard label="Backend" value={beSummary.total ?? beVulns.length} color={beSummary.total > 0 ? SEV_COLOR.high : 'var(--app-success)'} testID="backend-vuln-count" />
            <SummaryCard label="Frontend Critical" value={feSummary.critical ?? 0} color={feSummary.critical > 0 ? SEV_COLOR.critical : 'var(--app-success)'} testID="frontend-critical-count" />
            <SummaryCard label="Frontend High" value={feSummary.high ?? 0} color={feSummary.high > 0 ? SEV_COLOR.high : 'var(--app-success)'} testID="frontend-high-count" />
            <SummaryCard label="Frontend Moderate" value={feSummary.moderate ?? 0} color={feSummary.moderate > 0 ? SEV_COLOR.moderate : 'var(--app-success)'} testID="frontend-moderate-count" />
          </View>

          {/* Vuln tabs: backend / frontend */}
          <View style={{ flexDirection: 'row', gap: 8, marginBottom: 8 }}>
            {[['Backend (pip)', true], ['Frontend (yarn)', false]].map(([label, isBe]) => (
              <TouchableOpacity
                key={String(label)}
                onPress={() => setBeTab(isBe as boolean)}
                style={{ paddingHorizontal: 14, paddingVertical: 6, borderRadius: 8, backgroundColor: beTab === isBe ? (globalThis as any).__alphaColor(T.primary, '22') : 'transparent', borderWidth: 1, borderColor: beTab === isBe ? T.primary : T.border }}
                data-testid={`dep-tab-${isBe ? 'backend' : 'frontend'}`}
              >
                <Text style={{ fontSize: 12, fontWeight: '600', color: beTab === isBe ? T.primary : T.textMuted }}>{label as string}</Text>
              </TouchableOpacity>
            ))}
          </View>

          {/* Vulnerability list */}
          <View style={{ backgroundColor: T.card, borderRadius: 12, borderWidth: 1, borderColor: T.border, overflow: 'hidden', marginBottom: 16 }}>
            {(beTab ? beVulns : feVulns).length === 0 ? (
              <View style={{ padding: 24, alignItems: 'center', gap: 8 }}>
                <Ionicons name="checkmark-circle" size={32} color={'var(--app-success)'} />
                <Text style={{ fontSize: 13, color: colors.successText, fontWeight: '600' }}>{tx('admin.dependencyScan.states.noVulnerabilities', 'No vulnerabilities found')}</Text>
              </View>
            ) : (
              (beTab ? beVulns : feVulns).map((v: any, i: number) => (
                <VulnRow key={i} vuln={v} index={i} T={T} />
              ))
            )}
          </View>
        </>
      )}

      {/* History chart */}
      {history.length > 1 && <HistoryBar scans={history.slice(0, 10)} T={T} />}

      {/* Empty state */}
      {!scanning && !lastScan && (
        <View style={{ alignItems: 'center', paddingVertical: 48, gap: 12 }}>
          <Ionicons name="shield-outline" size={48} color={T.textMuted} />
          <Text style={{ fontSize: 14, fontWeight: '600', color: T.text }}>{tx('admin.dependencyScan.states.noScansYet', 'No scans yet')}</Text>
          <Text style={{ fontSize: 12, color: T.textMuted, textAlign: 'center' }}>Click "Run Scan Now" to check for vulnerabilities.{'\n'}Scans run automatically on the 1st of each month at 04:00 UTC.</Text>
        </View>
      )}

      {loadingHistory && !history.length && (
        <View style={{ alignItems: 'center', padding: 16 }}>
          <ActivityIndicator size="small" color={T.primary} />
        </View>
      )}
    </View>
  );
}
