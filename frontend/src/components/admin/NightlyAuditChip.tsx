/**
 * NightlyAuditChip
 * ──────────────────
 * Compact at-a-glance chip showing the most recent nightly Theme Visibility Audit.
 * Pulls from GET /api/admin/platform-perf/theme-visibility-audit/history?limit=20
 * and prefers the latest run tagged `trigger: 'nightly_cron'` (falls back to newest run).
 *
 * Renders:  🌙 Nightly audit · A · 0 FAILs · 3h ago
 * Red soft-pulse when a regression is detected (grade < A or FAILs > 0).
 */
import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Animated, Platform, Text, TouchableOpacity, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useTheme } from '../../context/ThemeContext';
import { useTranslation } from '../../hooks/useTranslation';
import { useHybridPolling } from '../../hooks/useHybridPolling';

const API = process.env.REACT_APP_BACKEND_URL || '';

interface HistoryRun {
  run_id: string;
  overall_grade: string;
  summary: { total_fail_issues?: number };
  scanned_at: string;
  trigger?: string;
}

function timeAgo(iso: string): string {
  try {
    const then = new Date(iso).getTime();
    const diff = Math.max(0, Date.now() - then);
    const m = Math.floor(diff / 60000);
    if (m < 1) return 'just now';
    if (m < 60) return `${m}m ago`;
    const h = Math.floor(m / 60);
    if (h < 24) return `${h}h ago`;
    const d = Math.floor(h / 24);
    return `${d}d ago`;
  } catch {
    return '—';
  }
}

function gradeColor(g: string, palette: { success: string; warning: string; error: string; textMuted: string }): string {
  const up = (g || '').toUpperCase();
  if (up === 'A') return palette.success;
  if (up === 'A-' || up === 'B') return palette.warning;
  if (up === 'C' || up === 'D' || up === 'F') return palette.error;
  return palette.textMuted;
}

interface Props {
  onPress?: () => void;
  autoRefreshMs?: number; // default 5 min
  testID?: string;
}

export default function NightlyAuditChip({ onPress, autoRefreshMs = 300000, testID = 'nightly-audit-chip' }: Props) {
  const { colors } = useTheme();
  const { t } = useTranslation();
  const tx = useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);
  const [run, setRun] = useState<HistoryRun | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const pulseAnim = useRef(new Animated.Value(1)).current;

  const fetchLatest = useCallback(async () => {
    try {
      const token = (typeof localStorage !== 'undefined' ? localStorage.getItem('session_token') : '') || '';
      const res = await fetch(`${API}/api/admin/platform-perf/theme-visibility-audit/history?limit=20`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      const runs: HistoryRun[] = Array.isArray(data?.runs) ? data.runs : [];
      const nightly = runs.find(r => r.trigger === 'nightly_cron');
      setRun(nightly || runs[0] || null);
      setError(null);
    } catch (e: any) {
      setError(e?.message || 'Failed to load');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void fetchLatest();
  }, [fetchLatest]);

  useHybridPolling({
    enabled: true,
    errorScope: 'admin/nightly-audit-chip/hybrid-refresh',
    onTick: fetchLatest,
    runOnMount: false,
    slowIntervalMs: autoRefreshMs,
    fastIntervalMs: Math.max(15000, Math.floor(autoRefreshMs / 2)),
    wsEnabled: false,
  });

  const fails = Number(run?.summary?.total_fail_issues || 0);
  const grade = (run?.overall_grade || '').toUpperCase();
  const isRegression = !!run && (grade !== 'A' || fails > 0);

  useEffect(() => {
    if (!isRegression) {
      pulseAnim.stopAnimation();
      pulseAnim.setValue(1);
      return;
    }
    const loop = Animated.loop(
      Animated.sequence([
        Animated.timing(pulseAnim, { toValue: 1.04, duration: 900, useNativeDriver: Platform.OS !== 'web' }),
        Animated.timing(pulseAnim, { toValue: 1, duration: 900, useNativeDriver: Platform.OS !== 'web' }),
      ]),
    );
    loop.start();
    return () => loop.stop();
  }, [isRegression, pulseAnim]);

  const gColor = gradeColor(grade, { success: colors.success, warning: colors.warning, error: colors.error, textMuted: colors.textMuted });
  const borderCol = isRegression ? colors.error : colors.border;
  const isNightly = run?.trigger === 'nightly_cron';

  const body = (
    <Animated.View
      style={{
        transform: [{ scale: pulseAnim }],
        flexDirection: 'row',
        alignItems: 'center',
        gap: 8,
        paddingVertical: 7,
        paddingHorizontal: 12,
        borderRadius: 999,
        backgroundColor: isRegression ? colors.errorSoft : colors.surface,
        borderWidth: 1,
        borderColor: borderCol,
      }}
      data-testid={testID}
      testID={testID}
    >
      <Ionicons
        name={isNightly ? 'moon' : 'time-outline'}
        size={13}
        color={isRegression ? colors.error : colors.textSec}
      />
      <Text style={{ color: colors.textMuted, fontSize: 10, fontWeight: '700', textTransform: 'uppercase', letterSpacing: 0.6 }}>
        {isNightly ? 'Last nightly' : 'Last run'}
      </Text>
      {loading ? (
        <Text style={{ color: colors.textMuted, fontSize: 11 }}>…</Text>
      ) : error ? (
        <Text style={{ color: colors.error, fontSize: 11, fontWeight: '600' }} data-testid={`${testID}-error`} testID={`${testID}-error`}>{tx('admin.nightlyAuditChip.states.offline', 'offline')}</Text>
      ) : !run ? (
        <Text style={{ color: colors.textMuted, fontSize: 11 }}>{tx('admin.nightlyAuditChip.states.noRuns', 'no runs yet')}</Text>
      ) : (
        <>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}>
            <View style={{ width: 6, height: 6, borderRadius: 3, backgroundColor: gColor }} />
            <Text style={{ color: colors.text, fontSize: 12, fontWeight: '800' }} data-testid={`${testID}-grade`} testID={`${testID}-grade`}>
              {grade || '—'}
            </Text>
          </View>
          <Text style={{ color: colors.textSec, fontSize: 11, fontWeight: '600' }} data-testid={`${testID}-fails`} testID={`${testID}-fails`}>
            {fails} FAIL{fails === 1 ? '' : 's'}
          </Text>
          <Text style={{ color: colors.textMuted, fontSize: 11 }} data-testid={`${testID}-ago`} testID={`${testID}-ago`}>
            · {timeAgo(run.scanned_at)}
          </Text>
          {isRegression && (
            <Text style={{ color: colors.error, fontSize: 10, fontWeight: '800', letterSpacing: 0.4 }} data-testid={`${testID}-regression-badge`} testID={`${testID}-regression-badge`}>
              {tx('admin.nightlyAuditChip.badges.regression', '· REGRESSION')}
            </Text>
          )}
        </>
      )}
    </Animated.View>
  );

  if (onPress) {
    return (
      <TouchableOpacity onPress={onPress} activeOpacity={0.75} data-testid={`${testID}-button`} testID={`${testID}-button`}>
        {body}
      </TouchableOpacity>
    );
  }
  return body;
}
