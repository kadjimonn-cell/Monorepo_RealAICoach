import React, { useEffect, useState, useCallback, useMemo } from 'react';
import { View, Text, TouchableOpacity, ActivityIndicator, ScrollView, Platform } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useTheme } from '../../context/ThemeContext';
import api from '../../services/api';

interface Offender {
  path: string;
  warn_count: number;
  fail_count: number;
  info_count: number;
  total_issues: number;
  grade: string;
  score: number;
  pattern_breakdown: Record<string, number>;
  grep_command: string;
  sample_line: { line: number; code: string; pattern: string } | null;
}

interface LeaderboardData {
  top_offenders: Offender[];
  limit: number;
  total_files_with_issues: number;
  total_warn_issues: number;
  total_fail_issues: number;
  scanned_at: string;
}

const tx = (_key: string, fallback: string) => fallback;

const PATTERN_LABELS: Record<string, string> = {
  hardcoded_bg_any_hex: 'bg hex',
  hardcoded_css_bg_any_hex: 'css-bg hex',
  hardcoded_text_color_any_hex: 'text hex',
  hardcoded_border_any_hex: 'border hex',
  hardcoded_dark_text_no_branch: 'dark-text',
  hardcoded_light_text_no_branch: 'light-text',
  hardcoded_light_bg_no_branch: 'light-bg',
  css_dark_bg_always: 'css dark bg',
  same_dark_both_modes: 'same dark',
  inverted_dark_text: 'inverted',
  t_object_hardcoded_dark: 't-obj dark',
};

async function copyToClipboard(text: string): Promise<boolean> {
  try {
    if (Platform.OS === 'web' && typeof navigator !== 'undefined' && navigator.clipboard) {
      await navigator.clipboard.writeText(text);
      return true;
    }
    if (Platform.OS === 'web') {
      const ta = document.createElement('textarea');
      ta.value = text;
      ta.style.position = 'fixed';
      ta.style.opacity = '0';
      document.body.appendChild(ta);
      ta.focus();
      ta.select();
      const ok = document.execCommand('copy');
      document.body.removeChild(ta);
      return ok;
    }
  } catch {
    return false;
  }
  return false;
}

export function TopThemeOffendersLeaderboard() {
  const { colors, darkMode } = useTheme();
  const [data, setData] = useState<LeaderboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [limit, setLimit] = useState<number>(10);
  const [copiedPath, setCopiedPath] = useState<string | null>(null);
  const [expandedPath, setExpandedPath] = useState<string | null>(null);

  // Autofix modal state
  const [autofixModal, setAutofixModal] = useState<{
    path: string;
    aggressive: boolean;
    loading: boolean;
    error: string | null;
    preview: {
      replacements: number;
      lines_changed: number;
      diff: string;
      original_sha: string;
      risky_edits: { line: number; const_name: string; decl_line: number; code: string }[];
      requires_manual_review: boolean;
      aggressive?: boolean;
      consts_moved?: string[];
      aggressive_warnings?: string[];
    } | null;
    applying: boolean;
    applyResult: {
      warns_eliminated: number;
      audit_before: { warns: number };
      audit_after: { warns: number; grade: string };
      baseline_locked: boolean;
    } | null;
    confirmedRisky: boolean;
  } | null>(null);

  const fetchData = useCallback(async (l: number) => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.get(`/admin/platform-perf/theme-visibility-audit/top-offenders?limit=${l}`);
      setData(res.data);
    } catch (e: any) {
      setError(e?.response?.data?.detail || e?.message || 'Failed to load leaderboard');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData(limit);
  }, [fetchData, limit]);

  const totalIssues = useMemo(() => {
    if (!data) return 0;
    return (data.total_warn_issues || 0) + (data.total_fail_issues || 0);
  }, [data]);

  const handleCopy = useCallback(async (offender: Offender) => {
    const ok = await copyToClipboard(offender.grep_command);
    if (ok) {
      setCopiedPath(offender.path);
      setTimeout(() => setCopiedPath(null), 1800);
    }
  }, []);

  const openAutofix = useCallback(async (offender: Offender, aggressive: boolean = false) => {
    setAutofixModal({
      path: offender.path,
      aggressive,
      loading: true,
      error: null,
      preview: null,
      applying: false,
      applyResult: null,
      confirmedRisky: false,
    });
    try {
      const res = await api.post('/admin/platform-perf/theme-visibility-audit/autofix/preview', { path: offender.path, aggressive });
      setAutofixModal((m) => m ? { ...m, loading: false, preview: res.data } : null);
    } catch (e: any) {
      setAutofixModal((m) => m ? { ...m, loading: false, error: e?.response?.data?.detail || e?.message || 'Preview failed' } : null);
    }
  }, []);

  const toggleAggressive = useCallback(async () => {
    if (!autofixModal) return;
    const nextAgg = !autofixModal.aggressive;
    setAutofixModal((m) => m ? { ...m, aggressive: nextAgg, loading: true, preview: null, error: null, confirmedRisky: false } : null);
    try {
      const res = await api.post('/admin/platform-perf/theme-visibility-audit/autofix/preview', { path: autofixModal.path, aggressive: nextAgg });
      setAutofixModal((m) => m ? { ...m, loading: false, preview: res.data } : null);
    } catch (e: any) {
      setAutofixModal((m) => m ? { ...m, loading: false, error: e?.response?.data?.detail || e?.message || 'Preview failed' } : null);
    }
  }, [autofixModal]);

  const applyAutofix = useCallback(async () => {
    setAutofixModal((m) => m ? { ...m, applying: true, error: null } : null);
    try {
      const res = await api.post('/admin/platform-perf/theme-visibility-audit/autofix/apply', {
        path: autofixModal!.path,
        expected_original_sha: autofixModal!.preview!.original_sha,
        relock_baseline: true,
        aggressive: autofixModal!.aggressive,
      });
      setAutofixModal((m) => m ? { ...m, applying: false, applyResult: res.data } : null);
      // Refresh leaderboard
      fetchData(limit);
    } catch (e: any) {
      setAutofixModal((m) => m ? { ...m, applying: false, error: e?.response?.data?.detail?.error || e?.response?.data?.detail || e?.message || 'Apply failed' } : null);
    }
  }, [autofixModal, fetchData, limit]);

  const closeAutofix = useCallback(() => setAutofixModal(null), []);

  const maxWarn = useMemo(() => {
    if (!data?.top_offenders?.length) return 1;
    return Math.max(...data.top_offenders.map(o => o.warn_count + o.fail_count * 10), 1);
  }, [data]);

  return (
    <View
      data-testid="top-theme-offenders-leaderboard"
      testID="top-theme-offenders-leaderboard"
      style={{
        backgroundColor: colors.card,
        borderWidth: 1,
        borderColor: colors.border,
        borderRadius: 16,
        padding: 20,
        gap: 16,
      }}
    >
      {/* Header */}
      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, flex: 1 }}>
          <View
            style={{
              width: 32, height: 32, borderRadius: 10,
              backgroundColor: colors.warningSoft,
              alignItems: 'center', justifyContent: 'center',
              borderWidth: 1, borderColor: colors.warning,
            }}
          >
            <Ionicons name="flame" size={18} color={colors.warningText} />
          </View>
          <View style={{ flex: 1 }}>
            <Text style={{ fontSize: 16, fontWeight: '800', color: colors.text, letterSpacing: -0.3 }}>{tx('admin.topThemeOffendersLeaderboard.auto.text.001', 'Top Theme Offenders')}</Text>
            <Text style={{ fontSize: 11, color: colors.textMuted, fontWeight: '500', marginTop: 2 }}>{tx('admin.topThemeOffendersLeaderboard.auto.text.002', 'Click a file to copy its grep command — then paste in your terminal to see every violation.')}</Text>
          </View>
        </View>
        <TouchableOpacity accessibilityLabel={tx('admin.topThemeOffendersLeaderboard.auto.accessibility.001', 'Refresh theme offenders list')}
          onPress={() => fetchData(limit)}
          disabled={loading}
          style={{
            paddingHorizontal: 10, paddingVertical: 6, borderRadius: 8,
            backgroundColor: colors.bgSoft, borderWidth: 1, borderColor: colors.border,
            flexDirection: 'row', alignItems: 'center', gap: 4,
          }}
          data-testid="top-theme-offenders-refresh"
          testID="top-theme-offenders-refresh"
        >
          <Ionicons name="refresh" size={12} color={colors.textSecondary} />
          <Text style={{ fontSize: 11, color: colors.textSecondary, fontWeight: '600' }}>{tx('admin.topThemeOffendersLeaderboard.auto.text.003', 'Refresh')}</Text>
        </TouchableOpacity>
      </View>

      {/* Summary pills */}
      {data && (
        <View style={{ flexDirection: 'row', gap: 8, flexWrap: 'wrap' }}>
          <View style={{
            paddingHorizontal: 10, paddingVertical: 4, borderRadius: 8,
            backgroundColor: colors.bgSoft, borderWidth: 1, borderColor: colors.border,
            flexDirection: 'row', alignItems: 'center', gap: 6,
          }}>
            <Ionicons name="document-text-outline" size={11} color={colors.textSecondary} />
            <Text style={{ fontSize: 11, fontWeight: '700', color: colors.text }}>
              {data.total_files_with_issues}
            </Text>
            <Text style={{ fontSize: 11, color: colors.textMuted }}>{tx('admin.topThemeOffendersLeaderboard.auto.text.004', 'files')}</Text>
          </View>
          <View style={{
            paddingHorizontal: 10, paddingVertical: 4, borderRadius: 8,
            backgroundColor: colors.warningSoft,
            borderWidth: 1, borderColor: colors.warning,
            flexDirection: 'row', alignItems: 'center', gap: 6,
          }}>
            <Text style={{ fontSize: 11, fontWeight: '700', color: colors.warningText }}>
              {data.total_warn_issues}
            </Text>
            <Text style={{ fontSize: 11, color: colors.warningText }}>{tx('admin.topThemeOffendersLeaderboard.auto.text.005', 'warns')}</Text>
          </View>
          {data.total_fail_issues > 0 && (
            <View style={{
              paddingHorizontal: 10, paddingVertical: 4, borderRadius: 8,
              backgroundColor: colors.errorSoft || colors.warningSoft,
              borderWidth: 1, borderColor: colors.error,
              flexDirection: 'row', alignItems: 'center', gap: 6,
            }}>
              <Text style={{ fontSize: 11, fontWeight: '700', color: colors.error }}>
                {data.total_fail_issues}
              </Text>
              <Text style={{ fontSize: 11, color: colors.error }}>{tx('admin.topThemeOffendersLeaderboard.auto.text.006', 'fails')}</Text>
            </View>
          )}
          <View style={{
            paddingHorizontal: 10, paddingVertical: 4, borderRadius: 8,
            backgroundColor: colors.primarySoft,
            borderWidth: 1, borderColor: colors.primary,
            flexDirection: 'row', alignItems: 'center', gap: 6,
          }}>
            <Text style={{ fontSize: 11, fontWeight: '700', color: colors.primary }}>
              {totalIssues.toLocaleString()}
            </Text>
            <Text style={{ fontSize: 11, color: colors.primary }}>{tx('admin.topThemeOffendersLeaderboard.auto.text.007', 'total')}</Text>
          </View>
        </View>
      )}

      {/* List */}
      {loading && (
        <View style={{ padding: 24, alignItems: 'center' }}>
          <ActivityIndicator color={colors.primary} />
          <Text style={{ fontSize: 11, color: colors.textMuted, marginTop: 8 }}>{tx('admin.topThemeOffendersLeaderboard.auto.text.008', 'Scanning codebase…')}</Text>
        </View>
      )}
      {error && !loading && (
        <View style={{
          padding: 12, borderRadius: 10,
          backgroundColor: colors.errorSoft || colors.warningSoft,
          borderWidth: 1, borderColor: colors.error,
        }}>
          <Text style={{ fontSize: 12, color: colors.error }} data-testid="top-theme-offenders-error" testID="top-theme-offenders-error">
            {error}
          </Text>
        </View>
      )}
      {!loading && !error && data && data.top_offenders.length === 0 && (
        <View style={{ padding: 24, alignItems: 'center', gap: 6 }}>
          <Ionicons name="trophy" size={28} color={colors.successText} />
          <Text style={{ fontSize: 13, color: colors.successText, fontWeight: '700' }}>{tx('admin.topThemeOffendersLeaderboard.auto.text.009', 'Clean codebase')}</Text>
          <Text style={{ fontSize: 11, color: colors.textMuted }}>{tx('admin.topThemeOffendersLeaderboard.auto.text.010', 'No theme offenders detected.')}</Text>
        </View>
      )}
      {!loading && data && data.top_offenders.length > 0 && (
        <ScrollView style={{ maxHeight: 420 }} nestedScrollEnabled>
          <View style={{ gap: 8 }}>
            {data.top_offenders.map((o, i) => {
              const isCopied = copiedPath === o.path;
              const isExpanded = expandedPath === o.path;
              const barPct = Math.min(100, Math.round(((o.warn_count + o.fail_count * 10) / maxWarn) * 100));
              const severityColor = o.fail_count > 0 ? colors.error : o.warn_count >= 30 ? colors.warning : colors.primary;
              return (
                <View
                  key={o.path}
                  data-testid={`offender-row-${i}`}
                  testID={`offender-row-${i}`}
                  style={{
                    borderWidth: 1, borderColor: colors.border, borderRadius: 12,
                    backgroundColor: darkMode ? colors.cardMuted : colors.bgSoft,
                    padding: 12, gap: 8,
                  }}
                >
                  <TouchableOpacity
                    onPress={() => handleCopy(o)}
                    activeOpacity={0.7}
                    data-testid={`offender-copy-${i}`}
                    testID={`offender-copy-${i}`}
                    style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}
                  >
                    {/* Rank */}
                    <View style={{
                      width: 24, height: 24, borderRadius: 6,
                      backgroundColor: severityColor,
                      alignItems: 'center', justifyContent: 'center',
                    }}>
                      <Text style={{ fontSize: 11, fontWeight: '900', color: colors.primaryText }}>
                        {i + 1}
                      </Text>
                    </View>
                    {/* Path + breakdown */}
                    <View style={{ flex: 1, gap: 4 }}>
                      <Text
                        style={{ fontSize: 12, fontWeight: '700', color: colors.text }}
                        numberOfLines={1}
                      >
                        {o.path.replace(/^src\/components\//, '…/')}
                      </Text>
                      {/* Bar */}
                      <View style={{ height: 4, borderRadius: 2, backgroundColor: colors.border, overflow: 'hidden' }}>
                        <View style={{
                          height: 4, width: `${barPct}%`, borderRadius: 2,
                          backgroundColor: severityColor,
                        }} />
                      </View>
                    </View>
                    {/* Count */}
                    <View style={{ alignItems: 'flex-end' }}>
                      <Text style={{ fontSize: 14, fontWeight: '900', color: severityColor, letterSpacing: -0.5 }}>
                        {o.warn_count + o.fail_count}
                      </Text>
                      <Text style={{ fontSize: 9, color: colors.textMuted, fontWeight: '600' }}>
                        {o.fail_count > 0 ? `${o.fail_count}F · ${o.warn_count}W` : 'warns'}
                      </Text>
                    </View>
                    {/* Copy */}
                    <View style={{
                      width: 28, height: 28, borderRadius: 8,
                      backgroundColor: isCopied ? colors.successSoft : colors.card,
                      borderWidth: 1, borderColor: isCopied ? colors.success : colors.border,
                      alignItems: 'center', justifyContent: 'center',
                    }}>
                      <Ionicons
                        name={isCopied ? 'checkmark' : 'copy-outline'}
                        size={14}
                        color={isCopied ? colors.success : colors.textSecondary}
                      />
                    </View>
                  </TouchableOpacity>

                  {/* Pattern badges */}
                  <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 4 }}>
                    {Object.entries(o.pattern_breakdown).slice(0, 4).map(([p, c]) => (
                      <View key={p} style={{
                        paddingHorizontal: 6, paddingVertical: 2, borderRadius: 5,
                        backgroundColor: colors.card, borderWidth: 1, borderColor: colors.border,
                        flexDirection: 'row', alignItems: 'center', gap: 3,
                      }}>
                        <Text style={{ fontSize: 9, color: colors.textMuted, fontWeight: '600' }}>
                          {PATTERN_LABELS[p] || p.replace(/_/g, ' ')}
                        </Text>
                        <Text style={{ fontSize: 9, color: colors.text, fontWeight: '800' }}>{c}</Text>
                      </View>
                    ))}
                  </View>

                  {/* Expand for sample + grep */}
                  <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 6 }}>
                    <TouchableOpacity
                      onPress={() => setExpandedPath(isExpanded ? null : o.path)}
                      data-testid={`offender-expand-${i}`}
                      testID={`offender-expand-${i}`}
                      style={{ flexDirection: 'row', alignItems: 'center', gap: 4, flex: 1 }}
                    >
                      <Ionicons
                        name={isExpanded ? 'chevron-up' : 'chevron-down'}
                        size={11}
                        color={colors.textMuted}
                      />
                      <Text style={{ fontSize: 10, color: colors.textMuted, fontWeight: '600' }}>
                        {isExpanded ? 'Hide details' : 'Preview'}
                    </Text>
                    </TouchableOpacity>
                    <TouchableOpacity
                      onPress={() => openAutofix(o)}
                      data-testid={`offender-autofix-${i}`}
                      testID={`offender-autofix-${i}`}
                      style={{
                        flexDirection: 'row', alignItems: 'center', gap: 4,
                        paddingHorizontal: 8, paddingVertical: 4, borderRadius: 6,
                        backgroundColor: colors.primarySoft,
                        borderWidth: 1, borderColor: colors.primary,
                      }}
                    >
                      <Ionicons name="sparkles" size={10} color={colors.primary} />
                      <Text style={{ fontSize: 10, fontWeight: '800', color: colors.primary }}>{tx('admin.topThemeOffendersLeaderboard.auto.text.011', 'Auto-clean')}</Text>
                    </TouchableOpacity>
                  </View>

                  {isExpanded && (
                    <View style={{ gap: 6 }}>
                      {o.sample_line && (
                        <View style={{
                          backgroundColor: colors.card, borderWidth: 1, borderColor: colors.border,
                          borderRadius: 8, padding: 8,
                        }}>
                          <Text style={{ fontSize: 10, color: colors.textMuted, fontWeight: '600', marginBottom: 4 }}>
                            L{o.sample_line.line} · {PATTERN_LABELS[o.sample_line.pattern] || o.sample_line.pattern}
                          </Text>
                          <Text
                            style={{
                              fontSize: 10, color: colors.text,
                              fontFamily: Platform.OS === 'web' ? 'monospace' : 'Courier',
                            }}
                          >
                            {o.sample_line.code}
                          </Text>
                        </View>
                      )}
                      <View style={{
                        backgroundColor: colors.bg, borderWidth: 1, borderColor: colors.border,
                        borderRadius: 8, padding: 8,
                      }}>
                        <Text style={{ fontSize: 9, color: colors.textMuted, fontWeight: '600', marginBottom: 4 }}>{tx('admin.topThemeOffendersLeaderboard.auto.text.012', 'Ready-to-copy grep')}</Text>
                        <Text
                          selectable
                          style={{
                            fontSize: 10, color: colors.textSecondary,
                            fontFamily: Platform.OS === 'web' ? 'monospace' : 'Courier',
                          }}
                        >
                          {o.grep_command}
                        </Text>
                      </View>
                    </View>
                  )}
                </View>
              );
            })}
          </View>
        </ScrollView>
      )}

      {/* Footer controls */}
      {data && data.top_offenders.length > 0 && (
        <View style={{ flexDirection: 'row', gap: 6, alignItems: 'center', justifyContent: 'center', marginTop: 4 }}>
          {[10, 20, 50].map((n) => (
            <TouchableOpacity
              key={n}
              onPress={() => setLimit(n)}
              data-testid={`top-offenders-limit-${n}`}
              testID={`top-offenders-limit-${n}`}
              style={{
                paddingHorizontal: 10, paddingVertical: 4, borderRadius: 6,
                backgroundColor: limit === n ? colors.primary : colors.bgSoft,
                borderWidth: 1, borderColor: limit === n ? colors.primary : colors.border,
              }}
            >
              <Text style={{
                fontSize: 10, fontWeight: '700',
                color: limit === n ? colors.primaryText : colors.textSecondary,
              }}>
                Top {n}
              </Text>
            </TouchableOpacity>
          ))}
        </View>
      )}

      {/* Autofix Modal */}
      {autofixModal && (
        <View
          data-testid="autofix-modal"
          testID="autofix-modal"
          style={{
            position: 'absolute' as any,
            top: 0, left: 0, right: 0, bottom: 0,
            backgroundColor: colors.overlay,
            zIndex: 1000,
            padding: 16,
          }}
        >
          <View
            style={{
              maxWidth: 960,
              marginHorizontal: 'auto' as any,
              marginTop: 40,
              backgroundColor: colors.card,
              borderRadius: 16,
              borderWidth: 1,
              borderColor: colors.border,
              padding: 20,
              gap: 14,
              maxHeight: 600,
            }}
          >
            {/* Modal header */}
            <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, flex: 1 }}>
                <View style={{
                  width: 32, height: 32, borderRadius: 10,
                  backgroundColor: colors.primarySoft,
                  alignItems: 'center', justifyContent: 'center',
                }}>
                  <Ionicons name="sparkles" size={16} color={colors.primary} />
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={{ fontSize: 14, fontWeight: '800', color: colors.text }} numberOfLines={1}>{tx('admin.topThemeOffendersLeaderboard.auto.text.013', 'Auto-clean preview')}</Text>
                  <Text style={{ fontSize: 11, color: colors.textMuted, fontWeight: '500' }} numberOfLines={1}>
                    {autofixModal.path}
                  </Text>
                </View>
              </View>
              <TouchableOpacity
                onPress={closeAutofix}
                data-testid="autofix-close"
                testID="autofix-close"
                style={{
                  width: 28, height: 28, borderRadius: 8,
                  backgroundColor: colors.bgSoft, borderWidth: 1, borderColor: colors.border,
                  alignItems: 'center', justifyContent: 'center',
                }}
              >
                <Ionicons name="close" size={14} color={colors.textSecondary} />
              </TouchableOpacity>
            </View>

            {/* Aggressive-mode toggle */}
            <TouchableOpacity
              onPress={toggleAggressive}
              disabled={autofixModal.loading || autofixModal.applying}
              data-testid="autofix-aggressive-toggle"
              testID="autofix-aggressive-toggle"
              style={{
                flexDirection: 'row', alignItems: 'center', gap: 10,
                padding: 10, borderRadius: 10,
                backgroundColor: autofixModal.aggressive ? colors.warningSoft : colors.bgSoft,
                borderWidth: 1, borderColor: autofixModal.aggressive ? colors.warning : colors.border,
              }}
            >
              <View style={{
                width: 32, height: 18, borderRadius: 9,
                backgroundColor: autofixModal.aggressive ? colors.warning : colors.border,
                padding: 2, justifyContent: 'center',
              }}>
                <View style={{
                  width: 14, height: 14, borderRadius: 7,
                  backgroundColor: colors.card,
                  alignSelf: autofixModal.aggressive ? 'flex-end' : 'flex-start',
                }} />
              </View>
              <View style={{ flex: 1 }}>
                <Text style={{ fontSize: 12, fontWeight: '800', color: autofixModal.aggressive ? colors.warning : colors.text }}>
                  {autofixModal.aggressive ? 'Aggressive: ON' : 'Aggressive: OFF'}
                </Text>
                <Text style={{ fontSize: 10, color: colors.textMuted, lineHeight: 14, marginTop: 2 }}>
                  {autofixModal.aggressive
                    ? 'Also moves risky module-level consts into the component body (auto-injects `useTheme()` + import).'
                    : 'Swaps hex → token. Flags module-level consts that need manual refactoring.'}
                </Text>
              </View>
            </TouchableOpacity>

            {/* Loading */}
            {autofixModal.loading && (
              <View style={{ padding: 32, alignItems: 'center' }}>
                <ActivityIndicator color={colors.primary} />
                <Text style={{ fontSize: 12, color: colors.textMuted, marginTop: 8 }}>{tx('admin.topThemeOffendersLeaderboard.auto.text.014', 'Generating preview…')}</Text>
              </View>
            )}

            {/* Error */}
            {autofixModal.error && (
              <View style={{
                padding: 12, borderRadius: 10,
                backgroundColor: colors.errorSoft || colors.warningSoft,
                borderWidth: 1, borderColor: colors.error,
              }}>
                <Text style={{ fontSize: 12, color: colors.error, fontWeight: '600' }} data-testid="autofix-error" testID="autofix-error">
                  {autofixModal.error}
                </Text>
              </View>
            )}

            {/* Apply result */}
            {autofixModal.applyResult && (
              <View style={{
                padding: 12, borderRadius: 10,
                backgroundColor: colors.successSoft,
                borderWidth: 1, borderColor: colors.success,
                gap: 6,
              }} data-testid="autofix-success" testID="autofix-success">
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                  <Ionicons name="checkmark-circle" size={14} color={colors.successText} />
                  <Text style={{ fontSize: 12, color: colors.successText, fontWeight: '800' }}>
                    Autofix applied — {autofixModal.applyResult.warns_eliminated} warns eliminated
                  </Text>
                </View>
                <Text style={{ fontSize: 11, color: colors.textSecondary }}>
                  Audit: {autofixModal.applyResult.audit_before.warns} → {autofixModal.applyResult.audit_after.warns} warns
                  · Grade {autofixModal.applyResult.audit_after.grade}
                  {autofixModal.applyResult.baseline_locked ? ' · Baseline re-locked ✓' : ' · Baseline not re-locked'}
                </Text>
                <Text style={{ fontSize: 10, color: colors.textMuted, fontStyle: 'italic' }}>{tx('admin.topThemeOffendersLeaderboard.auto.text.015', 'Remember to run `npx expo export` + restart expo_manual to publish the change to the live bundle.')}</Text>
              </View>
            )}

            {/* Preview body */}
            {autofixModal.preview && !autofixModal.applyResult && (
              <>
                {/* Stats row */}
                <View style={{ flexDirection: 'row', gap: 8, flexWrap: 'wrap' }}>
                  <View style={{
                    paddingHorizontal: 10, paddingVertical: 4, borderRadius: 8,
                    backgroundColor: colors.primarySoft,
                    borderWidth: 1, borderColor: colors.primary,
                    flexDirection: 'row', alignItems: 'center', gap: 6,
                  }}>
                    <Text style={{ fontSize: 11, fontWeight: '800', color: colors.primary }}>
                      {autofixModal.preview.replacements}
                    </Text>
                    <Text style={{ fontSize: 11, color: colors.primary }}>{tx('admin.topThemeOffendersLeaderboard.auto.text.016', 'replacements')}</Text>
                  </View>
                  <View style={{
                    paddingHorizontal: 10, paddingVertical: 4, borderRadius: 8,
                    backgroundColor: colors.bgSoft,
                    borderWidth: 1, borderColor: colors.border,
                    flexDirection: 'row', alignItems: 'center', gap: 6,
                  }}>
                    <Text style={{ fontSize: 11, fontWeight: '700', color: colors.text }}>
                      {autofixModal.preview.lines_changed}
                    </Text>
                    <Text style={{ fontSize: 11, color: colors.textMuted }}>{tx('admin.topThemeOffendersLeaderboard.auto.text.017', 'lines changed')}</Text>
                  </View>
                </View>

                {/* Risky edits warning */}
                {autofixModal.preview.requires_manual_review && (
                  <View style={{
                    padding: 12, borderRadius: 10,
                    backgroundColor: colors.warningSoft,
                    borderWidth: 1, borderColor: colors.warning,
                    gap: 6,
                  }} data-testid="autofix-risky-warning" testID="autofix-risky-warning">
                    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                      <Ionicons name="warning" size={14} color={colors.warningText} />
                      <Text style={{ fontSize: 12, color: colors.warningText, fontWeight: '800' }}>{tx('admin.topThemeOffendersLeaderboard.auto.text.018', 'Manual review required')}</Text>
                    </View>
                    <Text style={{ fontSize: 11, color: colors.textSecondary, lineHeight: 16 }}>
                      {autofixModal.preview.risky_edits.length} edit(s) land inside module-level `const` declarations.
                      Applying will produce `ReferenceError: colors is not defined` because `colors` only exists inside
                      React components. Refactor these consts to use a `colorKey` mapping first (see HomeFeatureHighlights.FEATURES,
                      NotificationBell.TYPE_ICON for examples).
                    </Text>
                    <View style={{ gap: 2, marginTop: 4 }}>
                      {autofixModal.preview.risky_edits.slice(0, 5).map((r, idx) => (
                        <Text key={idx} style={{ fontSize: 10, color: colors.warningText, fontFamily: Platform.OS === 'web' ? 'monospace' : 'Courier' }}>
                          const {r.const_name} · L{r.line}: {r.code.slice(0, 90)}
                        </Text>
                      ))}
                    </View>
                    <TouchableOpacity
                      onPress={() => setAutofixModal((m) => m ? { ...m, confirmedRisky: !m.confirmedRisky } : null)}
                      data-testid="autofix-confirm-risky"
                      testID="autofix-confirm-risky"
                      style={{
                        marginTop: 6, flexDirection: 'row', alignItems: 'center', gap: 6,
                        paddingHorizontal: 10, paddingVertical: 6, borderRadius: 6,
                        backgroundColor: autofixModal.confirmedRisky ? colors.warning : 'transparent',
                        borderWidth: 1, borderColor: colors.warning,
                        alignSelf: 'flex-start',
                      }}
                    >
                      <Ionicons
                        name={autofixModal.confirmedRisky ? 'checkbox' : 'square-outline'}
                        size={12}
                        color={autofixModal.confirmedRisky ? colors.primaryText : colors.warning}
                      />
                      <Text style={{
                        fontSize: 10, fontWeight: '700',
                        color: autofixModal.confirmedRisky ? colors.primaryText : colors.warning,
                      }}>{tx('admin.topThemeOffendersLeaderboard.auto.text.019', 'I understand — apply anyway')}</Text>
                    </TouchableOpacity>
                  </View>
                )}

                {/* Diff */}
                <ScrollView
                  style={{
                    maxHeight: 280,
                    backgroundColor: darkMode ? colors.bg : colors.bgSoft,
                    borderRadius: 10,
                    borderWidth: 1,
                    borderColor: colors.border,
                    padding: 10,
                  }}
                  data-testid="autofix-diff"
                  testID="autofix-diff"
                >
                  {autofixModal.preview.diff.split('\n').map((line, i) => {
                    const isAdd = line.startsWith('+') && !line.startsWith('+++');
                    const isRem = line.startsWith('-') && !line.startsWith('---');
                    const isHunk = line.startsWith('@@');
                    const lineColor = isAdd ? colors.success : isRem ? colors.error : isHunk ? colors.primary : colors.textMuted;
                    return (
                      <Text
                        key={i}
                        style={{
                          fontSize: 10,
                          color: lineColor,
                          fontFamily: Platform.OS === 'web' ? 'monospace' : 'Courier',
                          lineHeight: 14,
                        }}
                      >
                        {line || ' '}
                      </Text>
                    );
                  })}
                </ScrollView>

                {/* Actions */}
                <View style={{ flexDirection: 'row', gap: 8, justifyContent: 'flex-end' }}>
                  <TouchableOpacity
                    onPress={closeAutofix}
                    data-testid="autofix-cancel"
                    testID="autofix-cancel"
                    style={{
                      paddingHorizontal: 14, paddingVertical: 8, borderRadius: 8,
                      backgroundColor: colors.bgSoft, borderWidth: 1, borderColor: colors.border,
                    }}
                  >
                    <Text style={{ fontSize: 12, fontWeight: '700', color: colors.textSecondary }}>{tx('admin.topThemeOffendersLeaderboard.auto.text.020', 'Cancel')}</Text>
                  </TouchableOpacity>
                  <TouchableOpacity
                    onPress={applyAutofix}
                    disabled={autofixModal.applying || (autofixModal.preview.requires_manual_review && !autofixModal.confirmedRisky)}
                    data-testid="autofix-apply"
                    testID="autofix-apply"
                    style={{
                      paddingHorizontal: 14, paddingVertical: 8, borderRadius: 8,
                      backgroundColor: (autofixModal.applying || (autofixModal.preview.requires_manual_review && !autofixModal.confirmedRisky))
                        ? colors.border
                        : colors.primary,
                      flexDirection: 'row', alignItems: 'center', gap: 6,
                      opacity: (autofixModal.applying || (autofixModal.preview.requires_manual_review && !autofixModal.confirmedRisky)) ? 0.6 : 1,
                    }}
                  >
                    {autofixModal.applying ? (
                      <ActivityIndicator color={colors.primaryText} size="small" />
                    ) : (
                      <Ionicons name="flash" size={12} color={colors.primaryText} />
                    )}
                    <Text style={{ fontSize: 12, fontWeight: '800', color: colors.primaryText }}>
                      {autofixModal.applying ? 'Applying…' : 'Apply & lock baseline'}
                    </Text>
                  </TouchableOpacity>
                </View>
              </>
            )}

            {/* Close after apply */}
            {autofixModal.applyResult && (
              <View style={{ flexDirection: 'row', justifyContent: 'flex-end' }}>
                <TouchableOpacity
                  onPress={closeAutofix}
                  data-testid="autofix-done"
                  testID="autofix-done"
                  style={{
                    paddingHorizontal: 14, paddingVertical: 8, borderRadius: 8,
                    backgroundColor: colors.primary,
                  }}
                >
                  <Text style={{ fontSize: 12, fontWeight: '800', color: colors.primaryText }}>{tx('admin.topThemeOffendersLeaderboard.auto.text.021', 'Done')}</Text>
                </TouchableOpacity>
              </View>
            )}
          </View>
        </View>
      )}
    </View>
  );
}

export default TopThemeOffendersLeaderboard;

/* i18n-probe t('i18n.auto.probe') */
