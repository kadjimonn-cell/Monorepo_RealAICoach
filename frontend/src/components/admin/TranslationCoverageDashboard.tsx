import React, { useState, useEffect, useCallback } from 'react';
import { View, Text, TouchableOpacity, ActivityIndicator, Platform} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import AutoFixBanner from './AutoFixBanner';
import RouteI18nReportCardWidget from './RouteI18nReportCardWidget';
import { useAdminTheme } from '../../hooks/useAdminTheme';
import { useTranslation } from '../../hooks/useTranslation';
import { handleAppRecoverableError } from '../../utils/appRecoverableError';
import { useHybridPolling } from '../../hooks/useHybridPolling';

// ── Types ──────────────────────────────────────────────────────────────────────

interface PageCoverage {
  name: string;
  total: number;
  translated: number;
  missing_count: number;
  coverage_pct: number;
  status: 'complete' | 'partial' | 'missing';
  missing_keys: string[];
}

interface LangCoverage {
  code: string;
  name: string;
  total_keys: number;
  translated_keys: number;
  missing_keys: number;
  coverage_pct: number;
  pages: PageCoverage[];
}

interface CoverageData {
  total_keys: number;
  total_pages: number;
  total_languages: number;
  avg_coverage: number;
  pages_summary: { name: string; key_count: number }[];
  languages: LangCoverage[];
}

interface ApiTableCoverage {
  label: string;
  strings: number;
  languages: number;
  filled: number;
  total_cells: number;
  coverage_pct: number;
}

interface DomEngineInfo {
  version: string;
  scope: string;
  cache_entries: number;
  cached_languages: number;
  mode: string;
  public_debounce_ms: number;
  auth_debounce_ms: number;
}

interface SafeAutoStatus {
  engine_active: boolean;
  mode: string;
  last_scan: string | null;
  total_auto_fixes: number;
  recent_fixes: { timestamp: string; fixes_applied: number; detail: any[] }[];
}

interface TrendSnapshot {
  timestamp: string;
  avg_coverage: number;
  total_keys: number;
  languages: number;
}

// ── Shared UI helpers ──────────────────────────────────────────────────────────

function ProgressBar({ pct, color, bg }: { pct: number; color: string; bg: string }) {
  return (
    <View style={{ height: 6, borderRadius: 3, backgroundColor: bg, overflow: 'hidden', flex: 1 }}>
      <View style={{ height: '100%', width: `${Math.min(pct, 100)}%`, backgroundColor: color, borderRadius: 3 }} />
    </View>
  );
}

function StatusDot({ status }: { status: string }) {
  const color = status === 'complete' ? 'var(--app-success)' : status === 'partial' ? 'var(--app-warning)' : 'var(--app-error)';
  return <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: color }} />;
}

function LivePulse({ color }: { color: string }) {
  return (
    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}>
      <View style={{ width: 6, height: 6, borderRadius: 3, backgroundColor: color }} />
      <Text style={{ color, fontSize: 9, fontWeight: '700', letterSpacing: 0.8 }}>{tx('admin.translationCoverageDashboard.auto.text.001', 'LIVE')}</Text>
    </View>
  );
}

function TrendMiniChart({ data, color, width = 120, height = 32 }: { data: number[]; color: string; width?: number; height?: number }) {
  if (!data || data.length < 2) return <Text style={{ color: 'var(--app-primary)', fontSize: 9 }}>{tx('admin.translationCoverageDashboard.auto.text.002', 'No trend data')}</Text>; // @theme-ok reviewed semantic hex
  if (Platform.OS !== 'web') return null;

  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min || 1;
  const bars = data.map((v) => ((v - min) / range) * (height - 4) + 2);

  return (
    <View style={{ width, height, flexDirection: 'row', alignItems: 'flex-end', gap: 1 }}>
      {bars.map((h, i) => (
        <View
          key={i}
          style={{
            flex: 1,
            height: h,
            backgroundColor: (globalThis as any).__alphaColor(i === bars.length - 1 ? color : color, '60'),
            borderRadius: 1,
          }}
        />
      ))}
    </View>
  );
}

const tx = (_key: string, fallback: string) => fallback;

const getPctColor = (pct: number) => pct === 100 ? 'var(--app-success)' : pct >= 70 ? 'var(--app-warning)' : 'var(--app-error)';

// ── Main Component ─────────────────────────────────────────────────────────────

export default function TranslationCoverageDashboard({ colors: _colors }: { colors: any }) {
  const { t } = useTranslation();
  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };

  const colors = useAdminTheme();
  const [data, setData] = useState<CoverageData | null>(null);
  const [loading, setLoading] = useState(true);
  const [expandedLang, setExpandedLang] = useState<string | null>(null);
  const [expandedPage, setExpandedPage] = useState<string | null>(null);
  const [translating, setTranslating] = useState(false);
  const [translateResult, setTranslateResult] = useState<any>(null);

  // Enhanced state
  const [safeAuto, setSafeAuto] = useState<SafeAutoStatus | null>(null);
  const [apiCoverage, setApiCoverage] = useState<{ api_tables: ApiTableCoverage[]; api_overall_pct: number; dom_engine: DomEngineInfo } | null>(null);
  const [trend, setTrend] = useState<TrendSnapshot[]>([]);
  const [safeAutoRunning, setSafeAutoRunning] = useState(false);
  const [lastRefresh, setLastRefresh] = useState<Date | null>(null);
  // ── Data fetching ──

  const fetchAll = useCallback(async () => {
    try {
      const [coverageRes, safeAutoRes, apiCovRes, trendRes] = await Promise.all([
        api.get('/i18n/coverage'),
        api.get('/i18n/safe-auto/status').catch(() => ({ data: null })),
        api.get('/i18n/coverage/api-data').catch(() => ({ data: null })),
        api.get('/i18n/coverage/trend').catch(() => ({ data: { snapshots: [] } })),
      ]);
      setData(coverageRes.data);
      if (safeAutoRes.data) setSafeAuto(safeAutoRes.data);
      if (apiCovRes.data) setApiCoverage(apiCovRes.data);
      if (trendRes.data?.snapshots) setTrend(trendRes.data.snapshots);
      setLastRefresh(new Date());
    } catch (error) { handleAppRecoverableError({ scope: 'src/components/admin/TranslationCoverageDashboard.tsx#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchAll();
  }, [fetchAll]);

  useHybridPolling({
    enabled: true,
    errorScope: 'admin/translation-coverage/hybrid-refresh',
    onTick: fetchAll,
    runOnMount: false,
    slowIntervalMs: 45000,
    fastIntervalMs: 20000,
  });

  // ── Safe-Auto trigger ──

  const runSafeAuto = useCallback(async () => {
    setSafeAutoRunning(true);
    try {
      await api.post('/i18n/safe-auto/run');
      await fetchAll();
    } catch (error) { handleAppRecoverableError({ scope: 'src/components/admin/TranslationCoverageDashboard.tsx#catch2', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
    setSafeAutoRunning(false);
  }, [fetchAll]);

  // ── Auto-Translate ──

  const handleAutoTranslate = useCallback(async (langs?: string[]) => {
    try {
      setTranslating(true);
      setTranslateResult(null);
      const targetLangs = langs || (data?.languages.filter(l => l.coverage_pct < 100).map(l => l.code) || []);
      const allResults: Record<string, any> = {};
      let totalCount = 0;
      for (const lang of targetLangs) {
        try {
          const res = await api.post('/i18n/auto-translate/jobs', { languages: [lang] }, { timeout: 180000 });
          const jobId = res?.data?.job_id;
          if (!jobId) {
            allResults[lang] = { status: 'error', error: 'Missing translation job id' };
            continue;
          }

          let statusPayload: any = null;
          let pollAttempts = 0;
          while (pollAttempts < 120) {
            pollAttempts += 1;
            await new Promise((resolve) => setTimeout(resolve, 1000));
            const statusRes = await api.get(`/i18n/auto-translate/jobs/status/${jobId}`, { silentLoading: true, timeout: 30000 });
            statusPayload = statusRes?.data || null;
            if (statusPayload?.status === 'completed' || statusPayload?.status === 'error') {
              break;
            }
          }

          const langResult = statusPayload?.results?.[lang];
          allResults[lang] = langResult || { status: statusPayload?.status || 'unknown' };
          totalCount += Number(langResult?.translated || 0);
        } catch (e: any) {
          allResults[lang] = { status: 'error', error: e?.message || 'Request timeout' };
        }
      }
      setTranslateResult({ success: true, total_translated: totalCount, languages: allResults });
      await fetchAll();
    } catch (e: any) {
      setTranslateResult({ success: false, error: e?.response?.data?.detail || 'Translation failed' });
    } finally {
      setTranslating(false);
    }
  }, [fetchAll, data]);

  if (loading) return <ActivityIndicator color={'var(--app-primary)'} style={{ marginVertical: 20 }} />;
  if (!data) return <Text style={{ color: colors.textMuted }}>{tx('admin.translationCoverageDashboard.auto.text.003', 'Failed to load coverage data')}</Text>;

  const domEngine = apiCoverage?.dom_engine;
  const apiTables = apiCoverage?.api_tables || [];
  const trendValues = trend.map(s => s.avg_coverage);

  return (
    <View data-testid="translation-coverage-dashboard" testID="translation-coverage-dashboard">
      <AutoFixBanner domain="languages" />

      <View style={{ marginBottom: 16 }}>
        <RouteI18nReportCardWidget />
      </View>

      {/* ── Header with Live indicator ── */}
      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
        <View>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
            <Text style={{ color: colors.text, fontSize: 18, fontWeight: '800' }}>{tx('admin.translationCoverageDashboard.auto.text.004', 'Translation Coverage')}</Text>
            <LivePulse color={'var(--app-success)'} />
          </View>
          <Text style={{ color: colors.textMuted, fontSize: 11, marginTop: 2 }}>
            Real-time i18n monitoring with Safe-Auto engine {lastRefresh ? `\u00b7 Updated ${lastRefresh.toLocaleTimeString()}` : ''}
          </Text>
        </View>
        <View style={{ flexDirection: 'row', gap: 8 }}>
          <TouchableOpacity onPress={fetchAll} data-testid="coverage-refresh-btn" testID="coverage-refresh-btn"
            style={{ padding: 8, borderRadius: 8, backgroundColor: (globalThis as any).__alphaColor(colors.primary, '15') }}>
            <Ionicons name="refresh" size={16} color={'var(--app-primary)'} />
          </TouchableOpacity>
        </View>
      </View>

      {/* ── Safe-Auto Engine Status ── */}
      <View style={{
        flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
        padding: 14, borderRadius: 12, marginBottom: 16,
        backgroundColor: colors.successSoft, borderWidth: 1, borderColor: colors.successSoft,
      }} data-testid="safe-auto-engine-status" testID="safe-auto-engine-status">
        <View style={{ flex: 1 }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 4 }}>
            <Ionicons name="shield-checkmark" size={16} color={'var(--app-success)'} />
            <Text style={{ color: colors.text, fontSize: 13, fontWeight: '700' }}>{tx('admin.translationCoverageDashboard.auto.text.005', 'Safe-Auto Engine')}</Text>
            <View style={{ paddingHorizontal: 6, paddingVertical: 1, borderRadius: 4, backgroundColor: colors.successSoft }}>
              <Text style={{ color: colors.successText, fontSize: 9, fontWeight: '800' }}>{tx('admin.translationCoverageDashboard.auto.text.006', 'ACTIVE')}</Text>
            </View>
          </View>
          <Text style={{ color: colors.textMuted, fontSize: 11 }}>
            Auto-detects and fixes translation gaps in real-time. {safeAuto?.total_auto_fixes ? `${safeAuto.total_auto_fixes} fixes applied.` : 'No gaps detected.'}
            {safeAuto?.last_scan ? ` Last scan: ${new Date(safeAuto.last_scan).toLocaleTimeString()}` : ''}
          </Text>
        </View>
        <TouchableOpacity
          onPress={runSafeAuto}
          disabled={safeAutoRunning}
          data-testid="safe-auto-run-btn" testID="safe-auto-run-btn"
          style={{
            flexDirection: 'row', alignItems: 'center', gap: 4,
            paddingHorizontal: 12, paddingVertical: 8, borderRadius: 8,
            backgroundColor: safeAutoRunning ? 'var(--app-success-soft)' : 'var(--app-success)',
          }}
        >
          {safeAutoRunning ? <ActivityIndicator size="small" color={colors.primaryText} /> : <Ionicons name="flash" size={14} color={colors.primaryText} />}
          <Text style={{ color: colors.primaryText, fontSize: 11, fontWeight: '700' }}>{safeAutoRunning ? 'Scanning...' : 'Scan Now'}</Text>
        </TouchableOpacity>
      </View>

      {/* ── Summary Stats Row ── */}
      <View style={{ flexDirection: 'row', gap: 8, marginBottom: 16, flexWrap: 'wrap' }}>
        {[
          { label: 'Total Keys', value: data.total_keys, color: colors.primary, icon: 'key' as const },
          { label: 'Pages', value: data.total_pages, color: colors.accent, icon: 'layers' as const },
          { label: 'Languages', value: data.total_languages, color: colors.successText, icon: 'language' as const },
          { label: 'Avg Coverage', value: `${data.avg_coverage}%`, color: getPctColor(data.avg_coverage), icon: 'pie-chart' as const },
        ].map(s => (
          <View key={s.label} style={{ flex: 1, minWidth: 100, backgroundColor: (globalThis as any).__alphaColor(s.color, '10'), borderRadius: 10, padding: 12, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(s.color, '20'), alignItems: 'center' }}>
            <Ionicons name={s.icon} size={16} color={s.color} style={{ marginBottom: 4 }} />
            <Text style={{ color: s.color, fontSize: 18, fontWeight: '800' }}>{s.value}</Text>
            <Text style={{ color: colors.textMuted, fontSize: 9, fontWeight: '600', textAlign: 'center' }}>{s.label}</Text>
          </View>
        ))}
      </View>

      {/* ── Coverage Trend Chart ── */}
      {trendValues.length > 0 && (
        <View style={{
          padding: 14, borderRadius: 12, marginBottom: 16,
          backgroundColor: colors.surfaceHover, borderWidth: 1, borderColor: colors.border,
        }} data-testid="coverage-trend-section" testID="coverage-trend-section">
          <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
            <Text style={{ color: colors.text, fontSize: 13, fontWeight: '700' }}>{tx('admin.translationCoverageDashboard.auto.text.007', 'Coverage Trend')}</Text>
            <Text style={{ color: colors.textMuted, fontSize: 10 }}>{trend.length} snapshots</Text>
          </View>
          <View style={{ flexDirection: 'row', alignItems: 'flex-end', gap: 12 }}>
            <TrendMiniChart data={trendValues} color={'var(--app-success)'} width={200} height={40} />
            <View>
              <Text style={{ color: colors.successText, fontSize: 18, fontWeight: '800' }}>{trendValues[trendValues.length - 1]}%</Text>
              <Text style={{ color: colors.textMuted, fontSize: 9 }}>{tx('admin.translationCoverageDashboard.auto.text.008', 'current')}</Text>
            </View>
            {trendValues.length >= 2 && (
              <View>
                {(() => {
                  const diff = trendValues[trendValues.length - 1] - trendValues[0];
                  const diffColor = diff > 0 ? 'var(--app-success)' : diff < 0 ? 'var(--app-error)' : colors.textMuted;
                  return (
                    <>
                      <Text style={{ color: diffColor, fontSize: 14, fontWeight: '700' }}>{diff > 0 ? '+' : ''}{diff}%</Text>
                      <Text style={{ color: colors.textMuted, fontSize: 9 }}>{tx('admin.translationCoverageDashboard.auto.text.009', 'change')}</Text>
                    </>
                  );
                })()}
              </View>
            )}
          </View>
        </View>
      )}

      {/* ── DOM Engine & API Data Coverage ── */}
      <View style={{ flexDirection: 'row', gap: 10, marginBottom: 16, flexWrap: 'wrap' }}>
        {/* DOM Engine Health */}
        {domEngine && (
          <View style={{
            flex: 1, minWidth: 200, padding: 14, borderRadius: 12,
            backgroundColor: colors.primarySoft, borderWidth: 1, borderColor: colors.primarySoft,
          }} data-testid="dom-engine-health" testID="dom-engine-health">
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 8 }}>
              <Ionicons name="globe" size={14} color={'var(--app-primary)'} />
              <Text style={{ color: colors.text, fontSize: 13, fontWeight: '700' }}>{tx('admin.translationCoverageDashboard.auto.text.010', 'DOM Translation Engine')}</Text>
              <View style={{ paddingHorizontal: 5, paddingVertical: 1, borderRadius: 3, backgroundColor: colors.successSoft }}>
                <Text style={{ color: colors.successText, fontSize: 8, fontWeight: '800' }}>{domEngine.version.toUpperCase()}</Text>
              </View>
            </View>
            <View style={{ gap: 3 }}>
              <Text style={{ color: colors.textMuted, fontSize: 11 }}>Scope: <Text style={{ color: colors.text, fontWeight: '600' }}>{domEngine.scope}</Text></Text>
              <Text style={{ color: colors.textMuted, fontSize: 11 }}>Mode: <Text style={{ color: colors.text, fontWeight: '600' }}>{domEngine.mode}</Text></Text>
              <Text style={{ color: colors.textMuted, fontSize: 11 }}>Cache: <Text style={{ color: colors.primary, fontWeight: '700' }}>{domEngine.cache_entries.toLocaleString()}</Text> entries across <Text style={{ fontWeight: '600', color: colors.text }}>{domEngine.cached_languages}</Text> langs</Text>
              <Text style={{ color: colors.textMuted, fontSize: 11 }}>Debounce: <Text style={{ fontWeight: '600', color: colors.text }}>{domEngine.public_debounce_ms}ms</Text> public / <Text style={{ fontWeight: '600', color: colors.text }}>{domEngine.auth_debounce_ms}ms</Text> auth</Text>
            </View>
          </View>
        )}

        {/* API Data Coverage */}
        {apiTables.length > 0 && (
          <View style={{
            flex: 1, minWidth: 200, padding: 14, borderRadius: 12,
            backgroundColor: colors.accentSoft, borderWidth: 1, borderColor: colors.accentSoft,
          }} data-testid="api-data-coverage" testID="api-data-coverage">
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 8 }}>
              <Ionicons name="server" size={14} color={'var(--app-primary)'} />
              <Text style={{ color: colors.text, fontSize: 13, fontWeight: '700' }}>{tx('admin.translationCoverageDashboard.auto.text.011', 'API Data Coverage')}</Text>
              <View style={{ paddingHorizontal: 5, paddingVertical: 1, borderRadius: 3, backgroundColor: (globalThis as any).__alphaColor(getPctColor(apiCoverage?.api_overall_pct || 0), '20') }}>
                <Text style={{ color: getPctColor(apiCoverage?.api_overall_pct || 0), fontSize: 9, fontWeight: '800' }}>{apiCoverage?.api_overall_pct}%</Text>
              </View>
            </View>
            <View style={{ gap: 6 }}>
              {apiTables.map(t => (
                <View key={t.label} style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                  <StatusDot status={t.coverage_pct === 100 ? 'complete' : t.coverage_pct >= 50 ? 'partial' : 'missing'} />
                  <Text style={{ color: colors.text, fontSize: 11, flex: 1 }}>{t.label}</Text>
                  <Text style={{ color: colors.textMuted, fontSize: 10 }}>{t.strings}s x {t.languages}L</Text>
                  <View style={{ paddingHorizontal: 4, paddingVertical: 1, borderRadius: 3, backgroundColor: (globalThis as any).__alphaColor(getPctColor(t.coverage_pct), '15') }}>
                    <Text style={{ color: getPctColor(t.coverage_pct), fontSize: 9, fontWeight: '700' }}>{t.coverage_pct}%</Text>
                  </View>
                </View>
              ))}
            </View>
          </View>
        )}
      </View>

      {/* ── Auto-Translate CTA ── */}
      {data.avg_coverage < 100 && (
        <View style={{
          flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
          padding: 14, borderRadius: 12, marginBottom: 16,
          backgroundColor: colors.accentSoft, borderWidth: 1, borderColor: colors.accentSoft,
        }}>
          <View style={{ flex: 1, marginRight: 12 }}>
            <Text style={{ color: colors.text, fontSize: 13, fontWeight: '700' }}>
              {translating ? 'AI Translating...' : `${100 - data.avg_coverage}% of translations missing`}
            </Text>
            <Text style={{ color: colors.textMuted, fontSize: 11, marginTop: 2 }}>
              {translating ? 'Using GPT-4o-mini to generate translations for all missing keys...'
                : 'Use AI to auto-translate all missing keys across all languages'}
            </Text>
          </View>
          <TouchableOpacity
            onPress={() => handleAutoTranslate()}
            disabled={translating}
            data-testid="auto-translate-all-btn" testID="auto-translate-all-btn"
            style={{
              flexDirection: 'row', alignItems: 'center', gap: 6,
              paddingHorizontal: 16, paddingVertical: 10, borderRadius: 10,
              backgroundColor: translating ? 'var(--app-primary-soft)' : 'var(--app-primary)',
            }}
          >
            {translating ? <ActivityIndicator size="small" color={colors.primaryText} /> : <Ionicons name="sparkles" size={14} color={colors.primaryText} />}
            <Text style={{ color: colors.primaryText, fontSize: 12, fontWeight: '700' }}>{translating ? 'Translating...' : 'Auto-Translate All'}</Text>
          </TouchableOpacity>
        </View>
      )}

      {/* ── Auto-Translate Result ── */}
      {translateResult && (
        <View style={{
          padding: 14, borderRadius: 12, marginBottom: 16,
          backgroundColor: translateResult.success ? 'var(--app-success-soft)' : 'var(--app-error-soft)',
          borderWidth: 1, borderColor: translateResult.success ? 'var(--app-success-soft)' : 'var(--app-error-soft)',
        }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 6 }}>
            <Ionicons name={translateResult.success ? 'checkmark-circle' : 'alert-circle'} size={16} color={translateResult.success ? 'var(--app-success)' : 'var(--app-error)'} />
            <Text style={{ color: colors.text, fontSize: 13, fontWeight: '700' }}>
              {translateResult.success ? `Translated ${translateResult.total_translated} keys` : `Failed: ${translateResult.error}`}
            </Text>
          </View>
          {translateResult.success && translateResult.languages && (
            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginTop: 4 }}>
              {Object.entries(translateResult.languages as Record<string, any>).map(([lang, info]: [string, any]) => (
                <View key={lang} style={{
                  paddingHorizontal: 8, paddingVertical: 3, borderRadius: 6,
                  backgroundColor: info.status === 'success' ? 'var(--app-success-soft)' : info.status === 'already_complete' ? 'var(--app-primary-soft)' : 'var(--app-warning-soft)',
                }}>
                  <Text style={{ fontSize: 10, fontWeight: '600', color: info.status === 'success' ? 'var(--app-success)' : info.status === 'already_complete' ? 'var(--app-primary)' : 'var(--app-warning)' }}>
                    {lang.toUpperCase()}: {info.status === 'already_complete' ? 'Complete' : info.status === 'success' ? `+${info.translated}` : 'Error'}
                  </Text>
                </View>
              ))}
            </View>
          )}
          <TouchableOpacity onPress={() => setTranslateResult(null)} accessibilityLabel={tx('admin.translationCoverageDashboard.auto.accessibility.001', 'Dismiss translation result')} style={{ marginTop: 8 }}>
            <Text style={{ color: colors.textMuted, fontSize: 11 }}>{tx('admin.translationCoverageDashboard.auto.text.012', 'Dismiss')}</Text>
          </TouchableOpacity>
        </View>
      )}

      {/* ── Language Coverage Cards ── */}
      <Text style={{ color: colors.text, fontSize: 14, fontWeight: '700', marginBottom: 10 }}>{tx('admin.translationCoverageDashboard.auto.text.013', 'Coverage by Language')}</Text>
      <View style={{ gap: 8, marginBottom: 20 }}>
        {data.languages.map(lang => {
          const isExpanded = expandedLang === lang.code;
          const pctColor = getPctColor(lang.coverage_pct);
          const completePages = lang.pages.filter(p => p.status === 'complete').length;
          const partialPages = lang.pages.filter(p => p.status === 'partial').length;
          const missingPages = lang.pages.filter(p => p.status === 'missing').length;

          return (
            <View key={lang.code} style={{
              backgroundColor: colors.surfaceHover, borderRadius: 12, borderWidth: 1,
              borderColor: isExpanded ? (globalThis as any).__alphaColor(colors.primary, '40') : colors.border,
              overflow: 'hidden',
            }}>
              <TouchableOpacity
                onPress={() => setExpandedLang(isExpanded ? null : lang.code)}
                data-testid={`coverage-lang-${lang.code}`} testID={`coverage-lang-${lang.code}`}
                style={{ padding: 14, flexDirection: 'row', alignItems: 'center', gap: 12 }}
              >
                <View style={{ width: 32, height: 32, borderRadius: 8, backgroundColor: (globalThis as any).__alphaColor(pctColor, '15'), alignItems: 'center', justifyContent: 'center' }}>
                  <Text style={{ color: pctColor, fontSize: 11, fontWeight: '800' }}>{lang.code.toUpperCase()}</Text>
                </View>
                <View style={{ flex: 1 }}>
                  <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 4 }}>
                    <Text style={{ color: colors.text, fontSize: 13, fontWeight: '700' }}>{lang.name}</Text>
                    <Text style={{ color: pctColor, fontSize: 13, fontWeight: '800' }}>{lang.coverage_pct}%</Text>
                  </View>
                  <ProgressBar pct={lang.coverage_pct} color={pctColor} bg={colors.border} />
                  <View style={{ flexDirection: 'row', gap: 10, marginTop: 6 }}>
                    <Text style={{ color: colors.successText, fontSize: 10, fontWeight: '600' }}>{completePages} complete</Text>
                    <Text style={{ color: colors.warningText, fontSize: 10, fontWeight: '600' }}>{partialPages} partial</Text>
                    <Text style={{ color: colors.error, fontSize: 10, fontWeight: '600' }}>{missingPages} missing</Text>
                  </View>
                </View>
                <Ionicons name={isExpanded ? 'chevron-up' : 'chevron-down'} size={16} color={colors.textMuted} />
              </TouchableOpacity>

              {lang.coverage_pct < 100 && isExpanded && (
                <View style={{ paddingHorizontal: 14, paddingBottom: 10 }}>
                  <TouchableOpacity
                    onPress={() => handleAutoTranslate([lang.code])}
                    disabled={translating}
                    data-testid={`auto-translate-${lang.code}-btn`} testID={`auto-translate-${lang.code}-btn`}
                    style={{
                      flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6,
                      paddingVertical: 8, borderRadius: 8,
                      backgroundColor: colors.accentSoft, borderWidth: 1, borderColor: colors.accentSoft,
                    }}
                  >
                    <Ionicons name="sparkles" size={12} color={'var(--app-primary)'} />
                    <Text style={{ color: colors.accent, fontSize: 11, fontWeight: '600' }}>Auto-translate {lang.missing_keys} missing keys for {lang.name}</Text>
                  </TouchableOpacity>
                </View>
              )}

              {isExpanded && (
                <View style={{ paddingHorizontal: 14, paddingBottom: 14, borderTopWidth: 1, borderTopColor: (globalThis as any).__alphaColor(colors.border, '40') }}>
                  <View style={{ flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 8, borderBottomWidth: 1, borderBottomColor: (globalThis as any).__alphaColor(colors.border, '30') }}>
                    <Text style={{ color: colors.textMuted, fontSize: 10, fontWeight: '700', flex: 2 }}>{tx('admin.translationCoverageDashboard.auto.text.014', 'PAGE / COMPONENT')}</Text>
                    <Text style={{ color: colors.textMuted, fontSize: 10, fontWeight: '700', width: 50, textAlign: 'center' }}>{tx('admin.translationCoverageDashboard.auto.text.015', 'KEYS')}</Text>
                    <Text style={{ color: colors.textMuted, fontSize: 10, fontWeight: '700', width: 60, textAlign: 'right' }}>{tx('admin.translationCoverageDashboard.auto.text.016', 'STATUS')}</Text>
                  </View>
                  {lang.pages.map(page => {
                    const pageKey = `${lang.code}-${page.name}`;
                    const isPageExpanded = expandedPage === pageKey;
                    const pagePctColor = getPctColor(page.coverage_pct);
                    return (
                      <View key={page.name}>
                        <TouchableOpacity
                          onPress={() => page.missing_keys.length > 0 ? setExpandedPage(isPageExpanded ? null : pageKey) : null}
                          data-testid={`coverage-page-${lang.code}-${page.name.replace(/\s/g, '-').toLowerCase()}`} testID={`coverage-page-${lang.code}-${page.name.replace(/\s/g, '-').toLowerCase()}`}
                          style={{ flexDirection: 'row', alignItems: 'center', paddingVertical: 8, borderBottomWidth: 1, borderBottomColor: (globalThis as any).__alphaColor(colors.border, '15') }}
                        >
                          <View style={{ flex: 2, flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                            <StatusDot status={page.status} />
                            <Text style={{ color: colors.text, fontSize: 12, fontWeight: '500' }}>{page.name}</Text>
                          </View>
                          <Text style={{ width: 50, textAlign: 'center', color: colors.textMuted, fontSize: 11 }}>{page.translated}/{page.total}</Text>
                          <View style={{ width: 60, alignItems: 'flex-end' }}>
                            <View style={{ paddingHorizontal: 6, paddingVertical: 2, borderRadius: 4, backgroundColor: (globalThis as any).__alphaColor(pagePctColor, '15') }}>
                              <Text style={{ color: pagePctColor, fontSize: 10, fontWeight: '700' }}>{page.coverage_pct}%</Text>
                            </View>
                          </View>
                        </TouchableOpacity>
                        {isPageExpanded && page.missing_keys.length > 0 && (
                          <View style={{ paddingLeft: 24, paddingVertical: 6, backgroundColor: colors.errorSoft, borderRadius: 6, marginBottom: 4 }}>
                            <Text style={{ color: colors.error, fontSize: 10, fontWeight: '600', marginBottom: 4 }}>{tx('admin.translationCoverageDashboard.auto.text.017', 'Missing keys:')}</Text>
                            {page.missing_keys.map(k => (
                              <Text key={k} style={{ color: colors.textMuted, fontSize: 10, fontFamily: Platform.OS === 'web' ? 'monospace' : undefined, marginBottom: 2 }}>{k}</Text>
                            ))}
                            {page.missing_count > page.missing_keys.length && (
                              <Text style={{ color: colors.textMuted, fontSize: 10, fontStyle: 'italic' }}>... and {page.missing_count - page.missing_keys.length} more</Text>
                            )}
                          </View>
                        )}
                      </View>
                    );
                  })}
                </View>
              )}
            </View>
          );
        })}
      </View>

      {/* ── Pages Overview ── */}
      <Text style={{ color: colors.text, fontSize: 14, fontWeight: '700', marginBottom: 10 }}>Pages Overview ({data.total_pages} pages, {data.total_keys} keys)</Text>
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6 }}>
        {data.pages_summary.map(p => (
          <View key={p.name} style={{ paddingHorizontal: 10, paddingVertical: 6, borderRadius: 8, backgroundColor: colors.surfaceHover, borderWidth: 1, borderColor: colors.border }}>
            <Text style={{ color: colors.text, fontSize: 11, fontWeight: '600' }}>{p.name}</Text>
            <Text style={{ color: colors.textMuted, fontSize: 9 }}>{p.key_count} keys</Text>
          </View>
        ))}
      </View>
    </View>
  );
}
