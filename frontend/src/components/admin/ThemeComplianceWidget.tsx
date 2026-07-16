import { useTranslation } from '../../hooks/useTranslation';
import React, { useEffect, useState, useCallback } from 'react';
import { View, Text, TouchableOpacity, ActivityIndicator } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useTheme } from '../../context/ThemeContext';
import api from '../../services/api';

const tx = (_key: string, fallback: string) => fallback;

const GRADE_COLORS: Record<string, string> = {
  A: 'var(--app-primary)',
  'A-': 'var(--app-primary)',
  B: 'var(--app-warning)',
  C: 'var(--app-warning)',
  D: 'var(--app-error)',
  F: 'var(--app-error)',
};

interface ComplianceData {
  current: {
    grade: string;
    warns: number;
    fails: number;
    infos: number;
    files_scanned: number;
    files_clean: number;
    compliance_pct: number;
    scanned_at: string;
  };
  deltas: { warn_delta: number; fail_delta: number };
  trend: {
    run_id: string;
    grade: string;
    warns: number;
    fails: number;
    scanned_at: string;
    trigger: string;
  }[];
  drift_alert: boolean;
  drift_reason: string;
  auto_run: {
    nightly_cron: string;
    safe_interval: string;
    total_historical_runs: number;
  };
  enforcement?: {
    active: boolean;
    mode: string;
    gate: string;
    violations: string[];
    baseline: { grade: string; warns: number; fails: number; locked_at: string } | null;
    open_tickets: number;
  };
}

function DeltaArrow({ value, inverse, colors }: { value: number; inverse?: boolean; colors: any }) {
  if (value === 0) return <Text style={{ color: colors.textMuted, fontSize: 10 }}>--</Text>;
  const isGood = inverse ? value > 0 : value < 0;
  const icon = value > 0 ? 'arrow-up' : 'arrow-down';
  const color = isGood ? colors.success : colors.error;
  return (
    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 2 }}>
      <Ionicons name={icon as any} size={10} color={color} />
      <Text style={{ color, fontSize: 10, fontWeight: '700' }}>{Math.abs(value)}</Text>
    </View>
  );
}

function MiniSparkline({ trend, colors }: { trend: ComplianceData['trend']; colors: any }) {
  if (!trend || trend.length < 2) {
    return <Text style={{ color: colors.textMuted, fontSize: 10 }}>{tx('admin.themeComplianceWidget.auto.text.001', 'No trend data yet')}</Text>;
  }

  const maxWarns = Math.max(...trend.map(t => t.warns), 1);
  const barWidth = Math.max(4, Math.floor(120 / trend.length));

  return (
    <View style={{ flexDirection: 'row', alignItems: 'flex-end', gap: 2, height: 32 }} data-testid="theme-compliance-sparkline" testID="theme-compliance-sparkline">
      {trend.map((point, i) => {
        const h = Math.max(2, (point.warns / maxWarns) * 28);
        const barColor = point.warns === 0 ? colors.success : point.warns > 50 ? colors.error : colors.warning;
        return (
          <View
            key={point.run_id || i}
            style={{
              width: barWidth,
              height: h,
              backgroundColor: barColor,
              borderRadius: 2,
              opacity: i === trend.length - 1 ? 1 : 0.6,
            }}
          />
        );
      })}
    </View>
  );
}

export function ThemeComplianceWidget() {
  const { colors, darkMode } = useTheme();
  const [data, setData] = useState<ComplianceData | null>(null);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState('');

  const fetchData = useCallback(async () => {
    try {
      setLoading(true);
      const res = await api.get('/admin/platform-perf/theme-compliance-summary', { silentLoading: true });
      setData(res.data || res);
      setError('');
    } catch (_e: any) {
      setError('Unable to load compliance data');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const [locking, setLocking] = useState(false);

  const lockBaseline = useCallback(async () => {
    try {
      setLocking(true);
      await api.post('/admin/platform-perf/theme-compliance-enforcement/lock-baseline');
      await fetchData();
    } catch (_e: any) {
      setError('Lock baseline failed');
    } finally {
      setLocking(false);
    }
  }, [fetchData]);

  const runAudit = useCallback(async () => {
    try {
      setRunning(true);
      await api.post('/admin/platform-perf/theme-visibility-audit/run');
      await fetchData();
    } catch (_e: any) {
      setError('Audit run failed');
    } finally {
      setRunning(false);
    }
  }, [fetchData]);

  if (loading && !data) {
    return (
      <View
        style={{
          backgroundColor: colors.card,
          borderWidth: 1,
          borderColor: colors.border,
          borderRadius: 12,
          padding: 14,
          minWidth: 280,
          maxWidth: 420,
          flex: 1,
        }}
        data-testid="theme-compliance-widget-loading"
        testID="theme-compliance-widget-loading"
      >
        <ActivityIndicator size="small" color={colors.primary} />
      </View>
    );
  }

  if (error && !data) {
    return (
      <View
        style={{
          backgroundColor: colors.card,
          borderWidth: 1,
          borderColor: colors.border,
          borderRadius: 12,
          padding: 14,
          minWidth: 280,
          maxWidth: 420,
          flex: 1,
        }}
        data-testid="theme-compliance-widget-error"
        testID="theme-compliance-widget-error"
      >
        <Text style={{ color: colors.error, fontSize: 12 }}>{error}</Text>
      </View>
    );
  }

  if (!data) return null;

  const { current, deltas, trend, drift_alert, drift_reason, auto_run } = data;
  const enforcement = data.enforcement;
  const gradeColor = GRADE_COLORS[current.grade] || colors.textMuted;
  const lastScan = current.scanned_at
    ? new Date(current.scanned_at).toLocaleString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
    : '--';

  return (
    <View
      style={{
        backgroundColor: colors.card,
        borderWidth: 1,
        borderColor: drift_alert ? colors.error : colors.border,
        borderRadius: 12,
        padding: 14,
        minWidth: 280,
        maxWidth: 420,
        flex: 1,
      }}
      data-testid="theme-compliance-widget"
      testID="theme-compliance-widget"
    >
      {/* Header row */}
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
          <Ionicons name="shield-checkmark" size={14} color={gradeColor} />
          <Text style={{ color: colors.text, fontSize: 12, fontWeight: '700' }} data-testid="theme-compliance-title" testID="theme-compliance-title">{tx('admin.themeComplianceWidget.auto.text.002', 'Theme Compliance')}</Text>
        </View>
        <TouchableOpacity accessibilityLabel={tx('admin.themeComplianceWidget.auto.accessibility.001', 'Run theme compliance audit')}
          onPress={runAudit}
          disabled={running}
          style={{
            flexDirection: 'row',
            alignItems: 'center',
            gap: 4,
            backgroundColor: colors.bgSoft,
            paddingHorizontal: 8,
            paddingVertical: 4,
            borderRadius: 6,
            opacity: running ? 0.5 : 1,
          }}
          data-testid="theme-compliance-run-audit-btn"
          testID="theme-compliance-run-audit-btn"
        >
          {running ? (
            <ActivityIndicator size={10} color={colors.primary} />
          ) : (
            <Ionicons name="refresh" size={10} color={colors.primary} />
          )}
          <Text style={{ color: colors.primary, fontSize: 10, fontWeight: '600' }}>
            {running ? 'Running...' : 'Run Audit'}
          </Text>
        </TouchableOpacity>
      </View>

      {/* Drift Alert */}
      {drift_alert && (
        <View
          style={{
            backgroundColor: colors.errorSoft,
            borderWidth: 1,
            borderColor: colors.error,
            borderRadius: 8,
            paddingHorizontal: 10,
            paddingVertical: 6,
            marginBottom: 10,
            flexDirection: 'row',
            alignItems: 'center',
            gap: 6,
          }}
          data-testid="theme-compliance-drift-alert"
          testID="theme-compliance-drift-alert"
        >
          <Ionicons name="warning" size={12} color={colors.error} />
          <Text style={{ color: colors.errorText, fontSize: 10, fontWeight: '600', flex: 1 }}>
            Drift Detected: {drift_reason}
          </Text>
        </View>
      )}

      {/* Grade + Stats row */}
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 12, marginBottom: 10 }}>
        {/* Grade badge */}
        <View
          style={{
            width: 44,
            height: 44,
            borderRadius: 22,
            backgroundColor: gradeColor,
            alignItems: 'center',
            justifyContent: 'center',
          }}
          data-testid="theme-compliance-grade-badge"
          testID="theme-compliance-grade-badge"
        >
          <Text style={{ color: colors.primaryText, fontSize: 18, fontWeight: '900' }}>{current.grade}</Text>
        </View>

        {/* Metrics */}
        <View style={{ flex: 1, gap: 3 }}>
          <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
            <View style={{ alignItems: 'center', flex: 1 }}>
              <Text style={{ color: current.warns === 0 ? colors.success : colors.warning, fontSize: 16, fontWeight: '800' }}
                data-testid="theme-compliance-warn-count" testID="theme-compliance-warn-count"
              >
                {current.warns}
              </Text>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 3 }}>
                <Text style={{ color: colors.textMuted, fontSize: 9, fontWeight: '600' }}>{tx('admin.themeComplianceWidget.auto.text.003', 'Warns')}</Text>
                <DeltaArrow value={deltas.warn_delta} colors={colors} />
              </View>
            </View>
            <View style={{ alignItems: 'center', flex: 1 }}>
              <Text style={{ color: current.fails === 0 ? colors.success : colors.error, fontSize: 16, fontWeight: '800' }}
                data-testid="theme-compliance-fail-count" testID="theme-compliance-fail-count"
              >
                {current.fails}
              </Text>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 3 }}>
                <Text style={{ color: colors.textMuted, fontSize: 9, fontWeight: '600' }}>{tx('admin.themeComplianceWidget.auto.text.004', 'Fails')}</Text>
                <DeltaArrow value={deltas.fail_delta} colors={colors} />
              </View>
            </View>
            <View style={{ alignItems: 'center', flex: 1 }}>
              <Text style={{ color: colors.primary, fontSize: 16, fontWeight: '800' }}
                data-testid="theme-compliance-pct" testID="theme-compliance-pct"
              >
                {current.compliance_pct}%
              </Text>
              <Text style={{ color: colors.textMuted, fontSize: 9, fontWeight: '600' }}>{tx('admin.themeComplianceWidget.auto.text.005', 'Clean')}</Text>
            </View>
          </View>
        </View>
      </View>

      {/* Trend sparkline */}
      <View style={{ marginBottom: 8 }}>
        <Text style={{ color: colors.textMuted, fontSize: 9, fontWeight: '600', marginBottom: 4 }}>
          Warning Trend (last {trend.length} runs)
        </Text>
        <MiniSparkline trend={trend} colors={colors} />
      </View>

      {/* Enforcement Status */}
      <View
        style={{
          backgroundColor: enforcement?.active
            ? (enforcement.gate === 'pass' ? colors.successSoft : colors.errorSoft)
            : colors.bgSoft,
          borderRadius: 8,
          paddingHorizontal: 10,
          paddingVertical: 6,
          marginBottom: 8,
          flexDirection: 'row',
          alignItems: 'center',
          justifyContent: 'space-between',
        }}
        data-testid="theme-enforcement-status"
        testID="theme-enforcement-status"
      >
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 5, flex: 1 }}>
          <Ionicons
            name={enforcement?.active ? (enforcement.gate === 'pass' ? 'lock-closed' : 'alert-circle') : 'lock-open'}
            size={11}
            color={enforcement?.active ? (enforcement.gate === 'pass' ? colors.success : colors.error) : colors.textMuted}
          />
          <Text style={{ color: enforcement?.active ? (enforcement.gate === 'pass' ? colors.success : colors.error) : colors.textMuted, fontSize: 9, fontWeight: '700' }}>
            {enforcement?.active
              ? (enforcement.gate === 'pass'
                ? `Enforced: No regressions (Baseline ${enforcement.baseline?.grade})`
                : `BLOCKED: ${enforcement.violations?.length || 0} violation(s)`)
              : 'Not enforced'}
          </Text>
        </View>
        {!enforcement?.active && (
          <TouchableOpacity accessibilityLabel={tx('admin.themeComplianceWidget.auto.accessibility.002', 'Lock theme baseline')}
            onPress={lockBaseline}
            disabled={locking}
            style={{
              backgroundColor: colors.success,
              paddingHorizontal: 8,
              paddingVertical: 3,
              borderRadius: 5,
              opacity: locking ? 0.5 : 1,
            }}
            data-testid="theme-enforcement-lock-btn"
            testID="theme-enforcement-lock-btn"
          >
            <Text style={{ color: colors.primaryText, fontSize: 9, fontWeight: '700' }}>
              {locking ? 'Locking...' : 'Lock Baseline'}
            </Text>
          </TouchableOpacity>
        )}
      </View>

      {/* Footer: Auto-run info + last scan */}
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}>
          <Ionicons name="timer-outline" size={10} color={colors.textMuted} />
          <Text style={{ color: colors.textMuted, fontSize: 9 }}>
            Auto: {auto_run.safe_interval}
          </Text>
        </View>
        <Text style={{ color: colors.textMuted, fontSize: 9 }} data-testid="theme-compliance-last-scan" testID="theme-compliance-last-scan">
          Last: {lastScan}
        </Text>
      </View>
    </View>
  );
}

export default ThemeComplianceWidget;

/* i18n-probe t('i18n.auto.probe') */
