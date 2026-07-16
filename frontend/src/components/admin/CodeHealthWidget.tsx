import React from 'react';
import { View, Text, TouchableOpacity, Platform } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useLiveQuery } from '../../hooks/useLiveQuery';

import { getAdminColors } from '../../hooks/useAdminTheme';
import { useTranslation } from '../../hooks/useTranslation';
function getC(dark) {
  const A = getAdminColors(dark);
  return { bg: A.bg, card: A.card, card2: A.cardSoft, border: A.border, text: A.text, muted: A.textDim, sec: A.textMuted, green: 'var(--app-success)', red: 'var(--app-error)', blue: 'var(--app-primary)', yellow: 'var(--app-warning)', purple: 'var(--app-primary)', cyan: 'var(--app-primary)', orange: 'var(--app-warning)', indigo: 'var(--app-primary)', pink: 'var(--app-primary)', lime: 'var(--app-primary)', teal: 'var(--app-primary)' };
}
const C = getC(true);

const tx = (_key: string, fallback: string) => fallback;

function timeAgo(ts: string | null): string {
  if (!ts) return 'Never';
  const diff = Date.now() - new Date(ts).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'Just now';
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

export default function CodeHealthWidget({ colors, onNavigate }: { colors: any; onNavigate?: () => void }) {
  const { data, loading } = useLiveQuery('/admin/code-health/widget', { entity: 'code-health-widget', pollInterval: 120000 });

  if (loading || !data) {
    return (
      <View style={{ backgroundColor: C.card, borderRadius: 14, padding: 20, borderWidth: 1, borderColor: C.border }} data-testid="code-health-widget-loading" testID="code-health-widget-loading">
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
          <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: C.muted }} />
          <Text style={{ fontSize: 14, fontWeight: '700', color: C.text }}>{tx('admin.codeHealthWidget.auto.text.001', 'Code Health')}</Text>
        </View>
        <Text style={{ fontSize: 12, color: C.muted, marginTop: 8 }}>{tx('admin.codeHealthWidget.auto.text.002', 'Loading...')}</Text>
      </View>
    );
  }

  const ruff = data.ruff || {};
  const js = data.js_scanner || {};
  const gate = data.deploy_gate || {};

  const hasCritical = !ruff.critical_passed || (js.critical || 0) > 0;
  const gateBlocked = !gate.passed;
  const allClear = !hasCritical && !gateBlocked;

  const statusColor = allClear ? C.green : gateBlocked ? C.red : C.yellow;
  const statusLabel = allClear ? 'All Clear' : gateBlocked ? 'Deploy Blocked' : 'Issues Found';
  const statusIcon = allClear ? 'checkmark-circle' : gateBlocked ? 'close-circle' : 'warning';

  const lastScan = ruff.timestamp || js.timestamp;

  return (
    <TouchableOpacity accessibilityLabel={tx('admin.codeHealthWidget.auto.accessibility.001', 'Open code health details')}
      activeOpacity={0.8}
      onPress={onNavigate}
      style={{
        backgroundColor: C.card,
        borderRadius: 14,
        padding: 20,
        borderWidth: 1,
        borderColor: allClear ? (globalThis as any).__alphaColor(C.green, '30') : gateBlocked ? C.red + '30' : C.yellow + '30',
        ...(Platform.OS === 'web' ? { cursor: 'pointer' as any } : {}),
      }}
      data-testid="code-health-widget" testID="code-health-widget"
    >
      {/* Header */}
      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14 }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
          <View style={{ width: 32, height: 32, borderRadius: 8, backgroundColor: (globalThis as any).__alphaColor(statusColor, '18'), alignItems: 'center', justifyContent: 'center' }}>
            <Ionicons name={statusIcon as any} size={18} color={statusColor} />
          </View>
          <View>
            <Text style={{ fontSize: 14, fontWeight: '700', color: C.text }}>{tx('admin.codeHealthWidget.auto.text.003', 'Code Health')}</Text>
            <Text style={{ fontSize: 10, color: C.muted, marginTop: 1 }}>Last scan: {timeAgo(lastScan)}</Text>
          </View>
        </View>
        <View style={{ backgroundColor: (globalThis as any).__alphaColor(statusColor, '18'), paddingHorizontal: 10, paddingVertical: 4, borderRadius: 8 }}>
          <Text style={{ fontSize: 11, fontWeight: '700', color: statusColor }} data-testid="code-health-widget-status" testID="code-health-widget-status">{statusLabel}</Text>
        </View>
      </View>

      {/* Metrics row */}
      <View style={{ flexDirection: 'row', gap: 8 }}>
        {/* Deploy Gate */}
        <View style={{ flex: 1, backgroundColor: C.bg, borderRadius: 10, padding: 12, alignItems: 'center' }} data-testid="code-health-deploy-gate" testID="code-health-deploy-gate">
          <Ionicons name={gate.passed ? 'rocket' : 'hand-left'} size={16} color={gate.passed ? C.green : C.red} />
          <Text style={{ fontSize: 16, fontWeight: '800', color: gate.passed ? C.green : C.red, marginTop: 4 }}>
            {gate.passed ? 'PASS' : gate.blocker_count || 0}
          </Text>
          <Text style={{ fontSize: 9, color: C.muted, marginTop: 2 }}>{tx('admin.codeHealthWidget.auto.text.004', 'Deploy Gate')}</Text>
        </View>

        {/* JS/TDZ Critical */}
        <View style={{ flex: 1, backgroundColor: C.bg, borderRadius: 10, padding: 12, alignItems: 'center' }} data-testid="code-health-js-critical" testID="code-health-js-critical">
          <Ionicons name="code-slash" size={16} color={(js.critical || 0) === 0 ? C.green : C.red} />
          <Text style={{ fontSize: 16, fontWeight: '800', color: (js.critical || 0) === 0 ? C.green : C.red, marginTop: 4 }}>
            {js.critical || 0}
          </Text>
          <Text style={{ fontSize: 9, color: C.muted, marginTop: 2 }}>{tx('admin.codeHealthWidget.auto.text.005', 'TDZ Critical')}</Text>
        </View>

        {/* Ruff Errors */}
        <View style={{ flex: 1, backgroundColor: C.bg, borderRadius: 10, padding: 12, alignItems: 'center' }} data-testid="code-health-ruff-errors" testID="code-health-ruff-errors">
          <Ionicons name="bug" size={16} color={(ruff.error_count || 0) === 0 ? C.green : C.yellow} />
          <Text style={{ fontSize: 16, fontWeight: '800', color: (ruff.error_count || 0) === 0 ? C.green : C.yellow, marginTop: 4 }}>
            {ruff.error_count || 0}
          </Text>
          <Text style={{ fontSize: 9, color: C.muted, marginTop: 2 }}>{tx('admin.codeHealthWidget.auto.text.006', 'Ruff Errors')}</Text>
        </View>

        {/* Files Scanned */}
        <View style={{ flex: 1, backgroundColor: C.bg, borderRadius: 10, padding: 12, alignItems: 'center' }} data-testid="code-health-files-scanned" testID="code-health-files-scanned">
          <Ionicons name="document-text" size={16} color={C.cyan} />
          <Text style={{ fontSize: 16, fontWeight: '800', color: C.cyan, marginTop: 4 }}>
            {js.files_scanned || 0}
          </Text>
          <Text style={{ fontSize: 9, color: C.muted, marginTop: 2 }}>{tx('admin.codeHealthWidget.auto.text.007', 'Files Scanned')}</Text>
        </View>
      </View>

      {/* Footer link */}
      {onNavigate && (
        <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'flex-end', marginTop: 12, gap: 4 }}>
          <Text style={{ fontSize: 11, color: C.blue, fontWeight: '600' }}>{tx('admin.codeHealthWidget.auto.text.008', 'View Details')}</Text>
          <Ionicons name="chevron-forward" size={12} color={C.blue} />
        </View>
      )}
    </TouchableOpacity>
  );
}

/* i18n-probe t('i18n.auto.probe') */
