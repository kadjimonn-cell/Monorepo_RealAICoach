import React, { useCallback, useEffect, useState } from 'react';
import {
  ActivityIndicator,
  Platform,
  ScrollView,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useTheme } from '@/src/context/ThemeContext';
import NightlyAuditChip from './NightlyAuditChip';
import { useAdminTheme } from '../../hooks/useAdminTheme';
import { useTranslation } from '../../hooks/useTranslation';

const tx = (_key: string, fallback: string) => fallback;

const API = process.env.REACT_APP_BACKEND_URL || '';

// ── Types ─────────────────────────────────────────────────────────────────────
interface AuditIssue {
  line: number;
  pattern: string;
  severity: 'fail' | 'warn' | 'info';
  message: string;
  code: string;
}

interface AuditFile {
  file: string;
  fail_count: number;
  warn_count: number;
  info_count: number;
  total_issues: number;
  grade: string;
  issues: AuditIssue[];
  skipped?: boolean;
  error?: boolean;
}

interface AuditSummary {
  total_files_scanned: number;
  files_failing: number;
  files_warning: number;
  files_clean: number;
  total_fail_issues: number;
  total_warn_issues: number;
  total_info_issues: number;
}

interface AuditResult {
  overall_grade: string;
  summary: AuditSummary;
  files: AuditFile[];
  scanned_at: string;
  patterns_checked: string[];
}

interface HistoryRun {
  run_id: string;
  overall_grade: string;
  summary: AuditSummary;
  scanned_at: string;
}

// ── Helpers ───────────────────────────────────────────────────────────────────
function gradeColor(grade: string): string {
  if (grade === 'A' || grade === 'A-') return 'var(--app-success)' as any;
  if (grade === 'B') return 'var(--app-success)' as any;
  if (grade === 'C') return 'var(--app-warning)' as any;
  if (grade === 'D') return 'rgb(249,115,22)' as any;
  return 'var(--app-error)' as any;
}

function severityColor(sev: string): string {
  if (sev === 'fail') return 'var(--app-error)' as any;
  if (sev === 'warn') return 'var(--app-warning)' as any;
  return 'var(--app-info)' as any;
}

function formatTime(iso: string): string {
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

function shortFile(path: string): string {
  const parts = path.split('/');
  return parts.slice(-2).join('/');
}

// ── Sub-components ────────────────────────────────────────────────────────────
function GradeBadge({ grade, size = 64 }: { grade: string; size?: number }) {
  const color = gradeColor(grade);
  return (
    <View
      data-testid="audit-grade-badge"
      testID="audit-grade-badge"
      style={{
        width: size,
        height: size,
        borderRadius: size / 2,
        backgroundColor: (globalThis as any).__alphaColor(color, '22'),
        borderWidth: 3,
        borderColor: color,
        alignItems: 'center',
        justifyContent: 'center',
      }}
    >
      <Text style={{ color, fontSize: size * 0.45, fontWeight: '900', fontFamily: 'monospace' }}>
        {grade}
      </Text>
    </View>
  );
}

function StatChip({
  label,
  value,
  color,
  testId,
}: {
  label: string;
  value: number | string;
  color: string;
  testId?: string;
}) {
  return (
    <View
      data-testid={testId}
      testID={testId}
      style={{
        flex: 1,
        minWidth: 90,
        backgroundColor: (globalThis as any).__alphaColor(color, '15'),
        borderRadius: 10,
        padding: 12,
        alignItems: 'center',
        borderWidth: 1,
        borderColor: (globalThis as any).__alphaColor(color, '30'),
      }}
    >
      <Text style={{ color, fontSize: 22, fontWeight: '800', fontFamily: 'monospace' }}>
        {value}
      </Text>
      <Text style={{ color: color + 'BB', fontSize: 11, marginTop: 2 }}>{label}</Text>
    </View>
  );
}

function IssueRow({ issue, isDark }: { issue: AuditIssue; isDark: boolean }) {
  const colors = useAdminTheme();
  const sColor = severityColor(issue.severity);
  return (
    <View
      style={{
        marginBottom: 8,
        borderRadius: 8,
        borderLeftWidth: 3,
        borderLeftColor: sColor,
        backgroundColor: colors.bgSoft,
        padding: 10,
      }}
    >
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 4 }}>
        <View
          style={{
            backgroundColor: (globalThis as any).__alphaColor(sColor, '22'),
            paddingHorizontal: 6,
            paddingVertical: 2,
            borderRadius: 4,
          }}
        >
          <Text style={{ color: sColor, fontSize: 10, fontWeight: '700' }}>
            {issue.severity.toUpperCase()}
          </Text>
        </View>
        <Text style={{ color: colors.textMuted, fontSize: 11 }}>
          Line {issue.line} · {issue.pattern}
        </Text>
      </View>
      <Text style={{ color: colors.text, fontSize: 12, marginBottom: 6 }}>
        {issue.message}
      </Text>
      {issue.code ? (
        <View
          style={{
            backgroundColor: colors.surface,
            borderRadius: 6,
            padding: 8,
          }}
        >
          <Text
            style={{
              color: colors.text,
              fontSize: 11,
              fontFamily: 'monospace',
              ...(Platform.OS === 'web' ? { whiteSpace: 'pre-wrap' as any, wordBreak: 'break-all' as any } : {}),
            }}
            numberOfLines={3}
          >
            {issue.code}
          </Text>
        </View>
      ) : null}
    </View>
  );
}

function FileRow({
  file,
  isDark,
}: {
  file: AuditFile;
  isDark: boolean;
}) {
  const colors = useAdminTheme();
  const [expanded, setExpanded] = useState(false);
  const hasFail = file.fail_count > 0;
  const hasWarn = file.warn_count > 0;
  const rowBg = colors.cardSoft;
  const border = hasFail ? colors.error : hasWarn ? colors.warning : colors.success;

  return (
    <View style={{ marginBottom: 4, borderRadius: 10, overflow: 'hidden' }}>
      <TouchableOpacity
        onPress={() => setExpanded((v) => !v)}
        data-testid={`audit-file-row-${file.file.replace(/[^a-z0-9]/gi, '-')}`}
        testID={`audit-file-row-${file.file.replace(/[^a-z0-9]/gi, '-')}`}
        style={{
          flexDirection: 'row',
          alignItems: 'center',
          backgroundColor: rowBg,
          paddingHorizontal: 14,
          paddingVertical: 10,
          borderLeftWidth: 3,
          borderLeftColor: border,
        }}
        accessibilityLabel={tx('admin.themeAuditPanel.auto.accessibility.001', 'Expand file audit row')}
      >
        <View style={{ flex: 1 }}>
          <Text
            style={{
              color: colors.text,
              fontSize: 12,
              fontFamily: 'monospace',
              fontWeight: '600',
            }}
          >
            {shortFile(file.file)}
          </Text>
          <Text style={{ color: colors.textMuted, fontSize: 10, marginTop: 1 }}>
            {file.file}
          </Text>
        </View>
        <View style={{ flexDirection: 'row', gap: 6, alignItems: 'center' }}>
          {file.fail_count > 0 && (
            <View
              style={{
                backgroundColor: (globalThis as any).__alphaColor(colors.error, '22'),
                borderRadius: 5,
                paddingHorizontal: 7,
                paddingVertical: 2,
              }}
            >
              <Text style={{ color: colors.error, fontSize: 11, fontWeight: '700' }}>
                {file.fail_count} FAIL
              </Text>
            </View>
          )}
          {file.warn_count > 0 && (
            <View
              style={{
                backgroundColor: (globalThis as any).__alphaColor(colors.warning, '22'),
                borderRadius: 5,
                paddingHorizontal: 7,
                paddingVertical: 2,
              }}
            >
              <Text style={{ color: colors.warningText, fontSize: 11, fontWeight: '700' }}>
                {file.warn_count} WARN
              </Text>
            </View>
          )}
          {file.fail_count === 0 && file.warn_count === 0 && (
            <View
              style={{
                backgroundColor: (globalThis as any).__alphaColor(colors.success, '22'),
                borderRadius: 5,
                paddingHorizontal: 7,
                paddingVertical: 2,
              }}
            >
              <Text style={{ color: colors.successText, fontSize: 11, fontWeight: '700' }}>{tx('admin.themeAuditPanel.auto.text.001', 'PASS')}</Text>
            </View>
          )}
          <Ionicons
            name={expanded ? 'chevron-up' : 'chevron-down'}
            size={14}
            color={colors.textMuted}
          />
        </View>
      </TouchableOpacity>
      {expanded && file.issues.length > 0 && (
        <View style={{ backgroundColor: colors.bgSoft, padding: 12 }}>
          {file.issues.map((issue, idx) => (
            <IssueRow key={idx} issue={issue} isDark={isDark} />
          ))}
        </View>
      )}
      {expanded && file.issues.length === 0 && (
        <View
          style={{
            backgroundColor: colors.bgSoft,
            padding: 16,
            alignItems: 'center',
          }}
        >
          <Text style={{ color: colors.successText, fontSize: 13 }}>{tx('admin.themeAuditPanel.auto.text.002', 'No issues detected in this file.')}</Text>
        </View>
      )}
    </View>
  );
}

function HistorySparkline({
  runs,
  isDark,
}: {
  runs: HistoryRun[];
  isDark: boolean;
}) {
  const colors = useAdminTheme();
  if (runs.length < 2) return null;
  return (
    <View style={{ marginTop: 16 }}>
      <Text
        style={{
          color: colors.textMuted,
          fontSize: 11,
          fontWeight: '600',
          marginBottom: 8,
          textTransform: 'uppercase',
          letterSpacing: 0.8,
        }}
      >
        Audit History — Last {runs.length} Runs
      </Text>
      <View style={{ flexDirection: 'row', gap: 6, flexWrap: 'wrap' }}>
        {[...runs].reverse().map((r, i) => (
          <View
            key={r.run_id}
            style={{
              alignItems: 'center',
              backgroundColor: colors.cardSoft,
              borderRadius: 8,
              padding: 8,
              minWidth: 64,
            }}
          >
            <View
              style={{
                width: 32,
                height: 32,
                borderRadius: 16,
                backgroundColor: (globalThis as any).__alphaColor(gradeColor(r.overall_grade), '22'),
                borderWidth: 2,
                borderColor: gradeColor(r.overall_grade),
                alignItems: 'center',
                justifyContent: 'center',
                marginBottom: 4,
              }}
            >
              <Text
                style={{
                  color: gradeColor(r.overall_grade),
                  fontSize: 12,
                  fontWeight: '900',
                }}
              >
                {r.overall_grade}
              </Text>
            </View>
            <Text style={{ color: colors.textMuted, fontSize: 9 }}>
              {new Date(r.scanned_at).toLocaleDateString()}
            </Text>
            <Text style={{ color: colors.textMuted, fontSize: 9 }}>
              {r.summary?.total_fail_issues ?? 0}F·{r.summary?.total_warn_issues ?? 0}W
            </Text>
          </View>
        ))}
      </View>
    </View>
  );
}

// ── Main Panel ────────────────────────────────────────────────────────────────
export default function ThemeAuditPanel() {
  const { t } = useTranslation();
  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };

  const { darkMode, colors } = useTheme();
  const isDark = darkMode;
  const adminColors = useAdminTheme();

  const [result, setResult] = useState<AuditResult | null>(null);
  const [history, setHistory] = useState<HistoryRun[]>([]);
  const [loading, setLoading] = useState(false);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<'all' | 'fail' | 'warn' | 'pass'>('all');
  const [historyLoaded, setHistoryLoaded] = useState(false);

  const cardBg = colors.card;
  const sectionBg = colors.bg;
  const textPrimary = colors.text;
  const textSec = colors.textSec;
  const border = colors.border;
  const accent = colors.accent;

  const getAuthHeader = useCallback((): Record<string, string> => {
    try {
      const raw = localStorage.getItem('session_token') || localStorage.getItem('session') || localStorage.getItem('auth_token') || '';
      if (!raw) return {};
      try {
        const parsed = JSON.parse(raw);
        const tok = parsed?.session_token || parsed?.token || raw;
        return tok ? { Authorization: `Bearer ${tok}` } : {};
      } catch {
        return { Authorization: `Bearer ${raw}` };
      }
    } catch {
      return {};
    }
  }, []);

  const fetchLatest = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const res = await fetch(`${API}/api/admin/platform-perf/theme-visibility-audit`, {
        headers: getAuthHeader(),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data: AuditResult = await res.json();
      setResult(data);
    } catch (e: any) {
      setError(e?.message || 'Failed to load audit');
    } finally {
      setLoading(false);
    }
  }, [getAuthHeader]);

  const fetchHistory = useCallback(async () => {
    try {
      const res = await fetch(`${API}/api/admin/platform-perf/theme-visibility-audit/history?limit=8`, {
        headers: getAuthHeader(),
      });
      if (!res.ok) return;
      const data = await res.json();
      setHistory(data.runs || []);
      setHistoryLoaded(true);
    } catch {
      /* silent */
    }
  }, [getAuthHeader]);

  const runAudit = useCallback(async () => {
    try {
      setRunning(true);
      setError(null);
      const res = await fetch(`${API}/api/admin/platform-perf/theme-visibility-audit/run`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Requested-With': 'XMLHttpRequest',
          ...getAuthHeader(),
        },
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data: AuditResult = await res.json();
      setResult(data);
      await fetchHistory();
    } catch (e: any) {
      setError(e?.message || 'Audit failed');
    } finally {
      setRunning(false);
    }
  }, [getAuthHeader, fetchHistory]);

  useEffect(() => {
    fetchLatest();
    fetchHistory();
  }, [fetchLatest, fetchHistory]);

  const filteredFiles = (result?.files || []).filter((f) => {
    if (f.skipped || f.error) return false;
    if (filter === 'fail') return f.fail_count > 0;
    if (filter === 'warn') return f.warn_count > 0 && f.fail_count === 0;
    if (filter === 'pass') return f.total_issues === 0;
    return true;
  });

  return (
    <ScrollView
      style={{ flex: 1, backgroundColor: sectionBg }}
      contentContainerStyle={{ padding: 20 }}
      data-testid="theme-audit-panel"
      testID="theme-audit-panel"
    >
      {/* ── Header ─────────────────────────────────────────── */}
      <View
        style={{
          flexDirection: 'row',
          alignItems: 'center',
          justifyContent: 'space-between',
          marginBottom: 20,
          flexWrap: 'wrap',
          gap: 12,
        }}
      >
        <View style={{ flex: 1 }}>
          <Text style={{ color: textPrimary, fontSize: 22, fontWeight: '800' }}>{tx('admin.themeAuditPanel.auto.text.003', 'Theme Visibility Audit')}</Text>
          <Text style={{ color: textSec, fontSize: 13, marginTop: 3 }}>{tx('admin.themeAuditPanel.auto.text.004', 'System-level static code scan for dark/light mode colour issues')}</Text>
          <View style={{ marginTop: 10, flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', gap: 10 }}>
            <NightlyAuditChip />
            {result?.scanned_at && (
              <Text style={{ color: textSec, fontSize: 11 }}>
                Last scan: {formatTime(result.scanned_at)}
              </Text>
            )}
          </View>
        </View>
        <TouchableOpacity
          onPress={runAudit}
          disabled={running}
          data-testid="audit-run-btn"
          testID="audit-run-btn"
          style={{
            backgroundColor: running ? (globalThis as any).__alphaColor(accent, '44') : accent,
            borderRadius: 12,
            paddingHorizontal: 18,
            paddingVertical: 12,
            flexDirection: 'row',
            alignItems: 'center',
            gap: 8,
          }}
          accessibilityLabel={tx('admin.themeAuditPanel.auto.accessibility.002', 'Run theme audit now')}
        >
          {running ? <ActivityIndicator color={colors.primaryText} size="small" /> : <Ionicons name="scan" size={16} color={colors.primaryText} />}
          <Text style={{ color: colors.primaryText, fontWeight: '700', fontSize: 13 }}>
            {running ? 'Scanning…' : 'Run Audit Now'}
          </Text>
        </TouchableOpacity>
      </View>

      {/* ── Error ─────────────────────────────────────────── */}
      {error && (
        <View
          style={{
            backgroundColor: colors.errorSoft,
            borderRadius: 10,
            padding: 14,
            marginBottom: 16,
            borderWidth: 1,
            borderColor: (globalThis as any).__alphaColor(colors.error, '40'),
          }}
        >
          <Text style={{ color: colors.error, fontSize: 13 }}>{error}</Text>
        </View>
      )}

      {/* ── Loading ──────────────────────────────────────── */}
      {loading && !result && (
        <View style={{ alignItems: 'center', paddingVertical: 48 }}>
          <ActivityIndicator color={accent} size="large" />
          <Text style={{ color: textSec, marginTop: 12 }}>{tx('admin.themeAuditPanel.auto.text.005', 'Scanning platform source files…')}</Text>
        </View>
      )}

      {result && (
        <>
          {/* ── Grade + Summary ───────────────────────────── */}
          <View
            style={{
              backgroundColor: cardBg,
              borderRadius: 16,
              padding: 20,
              marginBottom: 16,
              borderWidth: 1,
              borderColor: border,
              ...(Platform.OS === 'web'
                ? { boxShadow: `0 2px 16px ${adminColors.overlay}` }
                : {}),
            }}
            data-testid="audit-summary-card"
            testID="audit-summary-card"
          >
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 20, flexWrap: 'wrap' }}>
              <GradeBadge grade={result.overall_grade} size={76} />
              <View style={{ flex: 1 }}>
                <Text style={{ color: gradeColor(result.overall_grade), fontSize: 16, fontWeight: '800' }}>
                  Platform Grade: {result.overall_grade}
                </Text>
                <Text style={{ color: textSec, fontSize: 12, marginTop: 2 }}>
                  {result.summary.total_files_scanned} files scanned · {result.patterns_checked?.length ?? 0} patterns checked
                </Text>
              </View>
            </View>
            <View style={{ flexDirection: 'row', gap: 8, marginTop: 16, flexWrap: 'wrap' }}>
              <StatChip
                label="FAIL Issues"
                value={result.summary.total_fail_issues}
                color={colors.error}
                testId="audit-stat-fail"
              />
              <StatChip
                label="WARN Issues"
                value={result.summary.total_warn_issues}
                color={colors.warning}
                testId="audit-stat-warn"
              />
              <StatChip
                label="Failing Files"
                value={result.summary.files_failing}
                color={colors.orange}
                testId="audit-stat-files-fail"
              />
              <StatChip
                label="Clean Files"
                value={result.summary.files_clean}
                color={colors.success}
                testId="audit-stat-files-clean"
              />
            </View>
          </View>

          {/* ── History Sparkline ─────────────────────────── */}
          {historyLoaded && history.length > 0 && (
            <View
              style={{
                backgroundColor: cardBg,
                borderRadius: 16,
                padding: 16,
                marginBottom: 16,
                borderWidth: 1,
                borderColor: border,
              }}
              data-testid="audit-history-card"
              testID="audit-history-card"
            >
              <HistorySparkline runs={history} isDark={isDark} />
            </View>
          )}

          {/* ── Pattern Legend ────────────────────────────── */}
          <View
            style={{
              backgroundColor: cardBg,
              borderRadius: 16,
              padding: 16,
              marginBottom: 16,
              borderWidth: 1,
              borderColor: border,
            }}
            data-testid="audit-legend-card"
            testID="audit-legend-card"
          >
            <Text
              style={{
                color: textSec,
                fontSize: 11,
                fontWeight: '600',
                textTransform: 'uppercase',
                letterSpacing: 0.8,
                marginBottom: 10,
              }}
            >{tx('admin.themeAuditPanel.auto.text.006', 'Pattern Legend')}</Text>
            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
              {[
                { label: 'inverted_dark_text', sev: 'fail', desc: 'Dark text in dark-mode ternary slot' },
                { label: 'same_dark_both_modes', sev: 'fail', desc: 'Both branches are dark' },
                { label: 'css_dark_bg_always', sev: 'warn', desc: 'Hardcoded dark bg, no branch' },
                { label: 'hardcoded_dark_text', sev: 'warn', desc: 'Hardcoded dark text, no branch' },
                { label: 'hardcoded_light_text', sev: 'warn', desc: 'Hardcoded light text, no branch' },
                { label: 't_object_hardcoded', sev: 'info', desc: 'T-object uses dark literal' },
              ].map((p) => (
                <View
                  key={p.label}
                  style={{
                    flexDirection: 'row',
                    alignItems: 'center',
                    gap: 6,
                    backgroundColor: colors.cardSoft,
                    borderRadius: 8,
                    paddingHorizontal: 10,
                    paddingVertical: 6,
                  }}
                >
                  <View
                    style={{
                      width: 8,
                      height: 8,
                      borderRadius: 4,
                      backgroundColor: severityColor(p.sev),
                    }}
                  />
                  <Text style={{ color: colors.text, fontSize: 11, fontFamily: 'monospace' }}>
                    {p.label}
                  </Text>
                  <Text style={{ color: textSec, fontSize: 10 }}>{p.desc}</Text>
                </View>
              ))}
            </View>
          </View>

          {/* ── File Results ──────────────────────────────── */}
          <View
            style={{
              backgroundColor: cardBg,
              borderRadius: 16,
              padding: 16,
              borderWidth: 1,
              borderColor: border,
            }}
            data-testid="audit-files-card"
            testID="audit-files-card"
          >
            {/* Filter tabs */}
            <View
              style={{
                flexDirection: 'row',
                gap: 8,
                marginBottom: 14,
                flexWrap: 'wrap',
                alignItems: 'center',
              }}
            >
              <Text
                style={{
                  color: textSec,
                  fontSize: 11,
                  fontWeight: '600',
                  textTransform: 'uppercase',
                  letterSpacing: 0.8,
                  flex: 1,
                }}
              >
                File Results ({filteredFiles.length})
              </Text>
              {(['all', 'fail', 'warn', 'pass'] as const).map((f) => (
                <TouchableOpacity
                  key={f}
                  onPress={() => setFilter(f)}
                  data-testid={`audit-filter-${f}`}
                  testID={`audit-filter-${f}`}
                  style={{
                    backgroundColor:
                      filter === f
                        ? (f === 'fail' ? colors.error : f === 'warn' ? colors.warning : f === 'pass' ? colors.success : accent)
                        : colors.cardSoft,
                    borderRadius: 8,
                    paddingHorizontal: 10,
                    paddingVertical: 5,
                  }}
                  accessibilityLabel={`Filter by ${f}`}
                >
                  <Text
                    style={{
                      color: filter === f ? colors.primaryText : textSec,
                      fontSize: 12,
                      fontWeight: '600',
                      textTransform: 'uppercase',
                    }}
                  >
                    {f}
                  </Text>
                </TouchableOpacity>
              ))}
            </View>

            {filteredFiles.length === 0 ? (
              <View style={{ alignItems: 'center', paddingVertical: 32 }}>
                <Ionicons name="checkmark-circle" size={40} color={colors.success} />
                <Text style={{ color: colors.successText, fontSize: 15, fontWeight: '700', marginTop: 8 }}>{tx('admin.themeAuditPanel.auto.text.007', 'No files match this filter')}</Text>
              </View>
            ) : (
              filteredFiles.map((file) => (
                <FileRow key={file.file} file={file} isDark={isDark} />
              ))
            )}
          </View>
        </>
      )}
    </ScrollView>
  );
}
