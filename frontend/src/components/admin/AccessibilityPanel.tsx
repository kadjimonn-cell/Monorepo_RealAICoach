import React, { useState, useCallback } from 'react';
import { useAdminTheme } from '../../hooks/useAdminTheme';
import { useTranslation } from '../../hooks/useTranslation';
import { View, Text, ScrollView, TouchableOpacity, ActivityIndicator } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { useLiveQuery } from '../../hooks/useLiveQuery';
import AutoFixBanner from './AutoFixBanner';

const tx = (_key: string, fallback: string) => fallback;

function makeC(AC: any) { return {
  bg: AC.bg, card: AC.surfaceElevated, border: AC.border,
  text: AC.text, muted: AC.textMuted, sec: AC.textSec,
  green: AC.success, red: AC.error, blue: AC.primary,
  yellow: AC.warning, purple: AC.purple, cyan: AC.cyan,
  orange: AC.orange,
}; }

function TabBtn({ active, label, icon, onPress, testId }: { active: boolean; label: string; icon: string; onPress: () => void; testId: string }) {
  const AC = useAdminTheme();
  const C = React.useMemo(() => makeC(AC), [AC]);
  return (
    <TouchableOpacity data-testid={testId} testID={testId} onPress={onPress} style={{
      flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 14, paddingVertical: 8, borderRadius: 8,
      backgroundColor: active ? (globalThis as any).__alphaColor(C.blue, '20') : 'transparent', borderWidth: 1, borderColor: active ? (globalThis as any).__alphaColor(C.blue, '40') : C.border,
    }}>
      <Ionicons name={icon as any} size={14} color={active ? C.blue : C.muted} />
      <Text style={{ color: active ? C.blue : C.muted, fontSize: 12, fontWeight: '600' }}>{label}</Text>
    </TouchableOpacity>
  );
}

function ColorSwatch({ hex, label }: { hex: string; label?: string }) {
  const AC = useAdminTheme();
  const C = React.useMemo(() => makeC(AC), [AC]);
  return (
    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
      <View style={{ width: 18, height: 18, borderRadius: 4, backgroundColor: hex, borderWidth: 1, borderColor: C.border }} />
      <Text style={{ color: C.sec, fontSize: 11, fontFamily: 'monospace' }}>{hex}</Text>
      {label && <Text style={{ color: C.muted, fontSize: 10 }}>({label})</Text>}
    </View>
  );
}

export default function AccessibilityPanel({ colors }: { colors: any }) {
  const { t } = useTranslation();
  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };

  const AC = useAdminTheme();
  const C = React.useMemo(() => makeC(AC), [AC]);
  const [auditing, setAuditing] = useState(false);
  const [fixing, setFixing] = useState(false);
  const [lastFixResult, setLastFixResult] = useState<any>(null);
  const [tab, setTab] = useState<'overview' | 'violations' | 'history'>('overview');

  const { data: latestData, loading: loadingLatest, refetch: refetchLatest } = useLiveQuery('/admin/accessibility/latest', { entity: 'accessibility', pollInterval: 60000 });
  const { data: histData, refetch: refetchHist } = useLiveQuery('/admin/accessibility/fix-history?limit=20', { entity: 'accessibility', pollInterval: 60000 });
  const report = latestData?.has_report ? latestData : null;
  const fixHistory = histData?.history || [];
  const loading = loadingLatest;

  const runAudit = useCallback(async () => {
    setAuditing(true);
    try {
      await api.post('/admin/accessibility/audit');
      await refetchLatest();
    } catch (e) { console.error(e); }
    setAuditing(false);
  }, [refetchLatest]);

  const runAutoFix = useCallback(async () => {
    setFixing(true);
    setLastFixResult(null);
    try {
      const res = await api.post('/admin/accessibility/auto-fix');
      setLastFixResult(res.data);
      await Promise.all([refetchLatest(), refetchHist()]);
    } catch (e) { console.error(e); }
    setFixing(false);
  }, [refetchLatest, refetchHist]);

  if (loading) {
    return (
      <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center', padding: 40 }}>
      <AutoFixBanner domain="web_vitals" />
        <ActivityIndicator size="large" color={C.blue} />
        <Text style={{ color: C.muted, marginTop: 12 }}>{tx('admin.accessibilityPanel.auto.text.001', 'Loading accessibility data...')}</Text>
      </View>
    );
  }

  return (
    <ScrollView data-testid="accessibility-panel" testID="accessibility-panel" style={{ flex: 1 }} contentContainerStyle={{ padding: 16, gap: 16 }}>
      {/* Header */}
      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 8 }}>
        <View style={{ flex: 1, minWidth: 200 }}>
          <Text style={{ color: C.text, fontSize: 20, fontWeight: '800', letterSpacing: -0.5 }}>{tx('admin.accessibilityPanel.auto.text.002', 'WCAG Accessibility')}</Text>
          <Text style={{ color: C.muted, fontSize: 12, marginTop: 2 }}>{tx('admin.accessibilityPanel.auto.text.003', 'Automated contrast checker + auto-fix — runs daily at 6:30 AM UTC')}</Text>
        </View>
        <View style={{ flexDirection: 'row', gap: 8 }}>
          <TouchableOpacity data-testid="run-audit-btn" testID="run-audit-btn" onPress={runAudit} disabled={auditing || fixing} style={{
            flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 14, paddingVertical: 8, borderRadius: 8,
            backgroundColor: (globalThis as any).__alphaColor(auditing ? C.border : C.cyan, '20'), borderWidth: 1, borderColor: (globalThis as any).__alphaColor(auditing ? C.border : C.cyan, '40'),
          }}>
            {auditing ? <ActivityIndicator size="small" color={C.cyan} /> : <Ionicons name="search" size={14} color={C.cyan} />}
            <Text style={{ color: auditing ? C.muted : C.cyan, fontSize: 12, fontWeight: '700' }}>{auditing ? 'Scanning...' : 'Run Audit'}</Text>
          </TouchableOpacity>
          <TouchableOpacity data-testid="run-autofix-btn" testID="run-autofix-btn" onPress={runAutoFix} disabled={fixing || auditing} style={{
            flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 14, paddingVertical: 8, borderRadius: 8,
            backgroundColor: (globalThis as any).__alphaColor(fixing ? C.border : C.purple, '20'), borderWidth: 1, borderColor: (globalThis as any).__alphaColor(fixing ? C.border : C.purple, '40'),
          }}>
            {fixing ? <ActivityIndicator size="small" color={C.purpleText} /> : <Ionicons name="color-wand" size={14} color={C.purpleText} />}
            <Text style={{ color: fixing ? C.muted : C.purple, fontSize: 12, fontWeight: '700' }}>{fixing ? 'Fixing...' : 'Auto-Fix'}</Text>
          </TouchableOpacity>
        </View>
      </View>

      {/* Tabs */}
      <View style={{ flexDirection: 'row', gap: 8, flexWrap: 'wrap' }}>
        <TabBtn active={tab === 'overview'} label="Overview" icon="eye" onPress={() => setTab('overview')} testId="a11y-tab-overview" />
        <TabBtn active={tab === 'violations'} label="Violations" icon="warning" onPress={() => setTab('violations')} testId="a11y-tab-violations" />
        <TabBtn active={tab === 'history'} label="Fix History" icon="time" onPress={() => setTab('history')} testId="a11y-tab-history" />
      </View>

      {/* Fix Result Banner */}
      {lastFixResult && (
        <View data-testid="a11y-fix-banner" testID="a11y-fix-banner" style={{
          padding: 16, borderRadius: 12, backgroundColor: (globalThis as any).__alphaColor(C.purple, '10'), borderWidth: 1, borderColor: (globalThis as any).__alphaColor(C.purple, '30'),
        }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 10 }}>
            <View style={{ width: 36, height: 36, borderRadius: 18, alignItems: 'center', justifyContent: 'center', backgroundColor: (globalThis as any).__alphaColor(C.purple, '20') }}>
              <Ionicons name="checkmark-done" size={18} color={C.purpleText} />
            </View>
            <View style={{ flex: 1 }}>
              <Text style={{ color: C.text, fontSize: 14, fontWeight: '700' }}>
                Auto-Fix Complete — {lastFixResult.fixes_applied} fix{lastFixResult.fixes_applied !== 1 ? 'es' : ''} applied
              </Text>
              <Text style={{ color: C.muted, fontSize: 11, marginTop: 2 }}>
                {lastFixResult.before_violations} → {lastFixResult.after_violations} violations ({lastFixResult.violations_fixed} resolved)
              </Text>
            </View>
            <TouchableOpacity accessibilityLabel={tx('admin.accessibilityPanel.auto.accessibility.001', 'Files Modified')} onPress={() => setLastFixResult(null)} >
              <Ionicons name="close" size={18} color={C.muted} />
            </TouchableOpacity>
          </View>
          <View style={{ flexDirection: 'row', gap: 8 }}>
            <View style={{ flex: 1, backgroundColor: C.card, borderRadius: 8, padding: 10, alignItems: 'center', borderWidth: 1, borderColor: C.border }}>
              <Text style={{ color: C.muted, fontSize: 9, textTransform: 'uppercase', fontWeight: '700' }}>{tx('admin.accessibilityPanel.auto.text.004', 'Files Modified')}</Text>
              <Text style={{ color: C.cyan, fontSize: 18, fontWeight: '800' }}>{lastFixResult.files_modified}</Text>
            </View>
            <View style={{ flex: 1, backgroundColor: C.card, borderRadius: 8, padding: 10, alignItems: 'center', borderWidth: 1, borderColor: C.border }}>
              <Text style={{ color: C.muted, fontSize: 9, textTransform: 'uppercase', fontWeight: '700' }}>{tx('admin.accessibilityPanel.auto.text.005', 'Fixes Applied')}</Text>
              <Text style={{ color: C.green, fontSize: 18, fontWeight: '800' }}>{lastFixResult.fixes_applied}</Text>
            </View>
            <View style={{ flex: 1, backgroundColor: C.card, borderRadius: 8, padding: 10, alignItems: 'center', borderWidth: 1, borderColor: C.border }}>
              <Text style={{ color: C.muted, fontSize: 9, textTransform: 'uppercase', fontWeight: '700' }}>{tx('admin.accessibilityPanel.auto.text.006', 'Remaining')}</Text>
              <Text style={{ color: lastFixResult.after_violations === 0 ? C.green : C.yellow, fontSize: 18, fontWeight: '800' }}>{lastFixResult.after_violations}</Text>
            </View>
          </View>
        </View>
      )}

      {/* ═══ OVERVIEW TAB ═══ */}
      {tab === 'overview' && (
        <>
          {/* Status Banner */}
          {report && (
            <View data-testid="a11y-status-banner" testID="a11y-status-banner" style={{
              flexDirection: 'row', alignItems: 'center', gap: 12, padding: 16, borderRadius: 12,
              backgroundColor: report.passed ? (globalThis as any).__alphaColor(C.green, '10') : C.red + '10',
              borderWidth: 1, borderColor: report.passed ? (globalThis as any).__alphaColor(C.green, '30') : C.red + '30',
            }}>
              <View style={{
                width: 44, height: 44, borderRadius: 22, alignItems: 'center', justifyContent: 'center',
                backgroundColor: report.passed ? (globalThis as any).__alphaColor(C.green, '20') : C.red + '20',
              }}>
                <Ionicons name={report.passed ? 'accessibility' : 'warning'} size={22} color={report.passed ? C.green : C.red} />
              </View>
              <View style={{ flex: 1 }}>
                <Text style={{ color: report.passed ? C.green : C.red, fontSize: 16, fontWeight: '800' }}>
                  {report.passed ? 'WCAG AA Compliant' : `${report.total_violations} Accessibility Violations`}
                </Text>
                <Text style={{ color: C.muted, fontSize: 11, marginTop: 2 }}>
                  {report.files_scanned} files scanned | Last: {new Date(report.timestamp).toLocaleString()}
                </Text>
              </View>
            </View>
          )}

          {/* KPI Cards */}
          {report && (
            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10 }}>
              {[
                { label: 'Total Violations', value: report.total_violations, icon: 'warning', color: report.passed ? C.green : C.red },
                { label: 'Critical', value: report.critical_count, icon: 'alert-circle', color: C.red },
                { label: 'Warning', value: report.warning_count, icon: 'information-circle', color: C.yellow },
                { label: 'Files Scanned', value: report.files_scanned, icon: 'document-text', color: C.blue },
              ].map(c => (
                <View key={c.label} data-testid={`a11y-stat-${c.label.toLowerCase().replace(/[^a-z]/g, '-')}`} testID={`a11y-stat-${c.label.toLowerCase().replace(/[^a-z]/g, '-')}`} style={{
                  flex: 1, minWidth: 140, backgroundColor: C.card, borderRadius: 12, padding: 14, borderWidth: 1, borderColor: C.border,
                }}>
                  <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 6 }}>
                    <Text style={{ color: C.sec, fontSize: 11, fontWeight: '600', textTransform: 'uppercase' }}>{c.label}</Text>
                    <Ionicons name={c.icon as any} size={14} color={c.color} />
                  </View>
                  <Text style={{ color: C.text, fontSize: 22, fontWeight: '800' }}>{c.value}</Text>
                </View>
              ))}
            </View>
          )}

          {/* Category Breakdown */}
          {report?.categories && (
            <View data-testid="a11y-category-breakdown" testID="a11y-category-breakdown" style={{ backgroundColor: C.card, borderRadius: 12, borderWidth: 1, borderColor: C.border, overflow: 'hidden' }}>
              <View style={{ paddingHorizontal: 16, paddingVertical: 12, borderBottomWidth: 1, borderBottomColor: C.border }}>
                <Text style={{ color: C.text, fontSize: 14, fontWeight: '700' }}>{tx('admin.accessibilityPanel.auto.text.007', 'WCAG 2.1 Category Breakdown')}</Text>
              </View>
              {[
                { key: 'contrast', label: 'Contrast Ratios', icon: 'color-palette', desc: 'Text color vs background meets 4.5:1 / 3:1', color: C.cyan },
                { key: 'aria', label: 'ARIA Labels', icon: 'text', desc: 'Interactive elements have accessibilityLabel or data-testid', color: C.purpleText },
                { key: 'keyboard', label: 'Keyboard Navigation', icon: 'keypad', desc: 'Clickable elements have role and tabIndex for keyboard access', color: C.blue },
                { key: 'focus', label: 'Focus Indicators', icon: 'scan', desc: 'outline:none has replacement focus style (boxShadow/ring)', color: C.orangeText },
              ].map((cat) => {
                const data = report.categories[cat.key] || { count: 0, passed: true };
                return (
                  <View key={cat.key} style={{ flexDirection: 'row', alignItems: 'center', paddingHorizontal: 16, paddingVertical: 12, borderBottomWidth: 1, borderBottomColor: C.border, gap: 12 }}>
                    <View style={{ width: 36, height: 36, borderRadius: 18, alignItems: 'center', justifyContent: 'center', backgroundColor: (globalThis as any).__alphaColor(cat.color, '18') }}>
                      <Ionicons name={cat.icon as any} size={16} color={cat.color} />
                    </View>
                    <View style={{ flex: 1 }}>
                      <Text style={{ color: C.text, fontSize: 13, fontWeight: '700' }}>{cat.label}</Text>
                      <Text style={{ color: C.muted, fontSize: 10, marginTop: 2 }}>{cat.desc}</Text>
                    </View>
                    <View style={{ alignItems: 'flex-end', gap: 4 }}>
                      <View style={{ paddingHorizontal: 10, paddingVertical: 3, borderRadius: 8, backgroundColor: data.passed ? (globalThis as any).__alphaColor(C.green, '18') : C.red + '18' }}>
                        <Text style={{ color: data.passed ? C.green : C.red, fontSize: 11, fontWeight: '700' }}>
                          {data.passed ? 'PASS' : `${data.count} issues`}
                        </Text>
                      </View>
                    </View>
                  </View>
                );
              })}
            </View>
          )}

          {/* Automation Pipeline Info */}
          <View data-testid="a11y-automation-info" testID="a11y-automation-info" style={{ backgroundColor: C.card, borderRadius: 12, padding: 16, borderWidth: 1, borderColor: C.border }}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 14 }}>
              <View style={{ width: 36, height: 36, borderRadius: 18, alignItems: 'center', justifyContent: 'center', backgroundColor: (globalThis as any).__alphaColor(C.cyan, '20') }}>
                <Ionicons name="cog" size={18} color={C.cyan} />
              </View>
              <View>
                <Text style={{ color: C.text, fontSize: 15, fontWeight: '700' }}>{tx('admin.accessibilityPanel.auto.text.008', 'Automated WCAG Engine')}</Text>
                <Text style={{ color: C.muted, fontSize: 11, marginTop: 2 }}>{tx('admin.accessibilityPanel.auto.text.009', 'Runs daily at 6:30 AM UTC via APScheduler')}</Text>
              </View>
            </View>
            <View style={{ gap: 10 }}>
              {[
                { icon: 'search', color: C.cyan, title: 'Scan', desc: 'Parses all .tsx files for dark-mode color pairs' },
                { icon: 'calculator', color: C.blue, title: 'Calculate', desc: 'Computes WCAG 2.1 contrast ratios (relative luminance)' },
                { icon: 'warning', color: C.yellow, title: 'Flag', desc: 'Identifies violations: <4.5:1 (normal text) or <3:1 (large text)' },
                { icon: 'color-wand', color: C.purpleText, title: 'Auto-Fix', desc: 'Lightens/darkens text colors until contrast meets threshold' },
                { icon: 'mail', color: C.green, title: 'Alert', desc: 'Sends WCAG compliance report to platform admins' },
              ].map((step, i) => (
                <View key={i} style={{ flexDirection: 'row', alignItems: 'center', gap: 12 }}>
                  <View style={{ width: 28, height: 28, borderRadius: 14, alignItems: 'center', justifyContent: 'center', backgroundColor: (globalThis as any).__alphaColor(step.color, '18') }}>
                    <Ionicons name={step.icon as any} size={14} color={step.color} />
                  </View>
                  <View style={{ flex: 1 }}>
                    <Text style={{ color: C.text, fontSize: 12, fontWeight: '700' }}>{i + 1}. {step.title}</Text>
                    <Text style={{ color: C.muted, fontSize: 11 }}>{step.desc}</Text>
                  </View>
                </View>
              ))}
            </View>
          </View>

          {/* WCAG Info */}
          <View style={{ backgroundColor: C.card, borderRadius: 12, padding: 16, borderWidth: 1, borderColor: C.border }}>
            <Text style={{ color: C.text, fontSize: 14, fontWeight: '700', marginBottom: 10 }}>{tx('admin.accessibilityPanel.auto.text.010', 'WCAG 2.1 AA Thresholds')}</Text>
            <View style={{ gap: 8 }}>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
                <View style={{ paddingHorizontal: 10, paddingVertical: 4, borderRadius: 6, backgroundColor: (globalThis as any).__alphaColor(C.red, '18') }}>
                  <Text style={{ color: C.red, fontSize: 12, fontWeight: '700' }}>4.5:1</Text>
                </View>
                <Text style={{ color: C.sec, fontSize: 12 }}>{tx('admin.accessibilityPanel.auto.text.011', 'Normal text (below 18pt / 14pt bold)')}</Text>
              </View>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
                <View style={{ paddingHorizontal: 10, paddingVertical: 4, borderRadius: 6, backgroundColor: (globalThis as any).__alphaColor(C.yellow, '18') }}>
                  <Text style={{ color: C.yellow, fontSize: 12, fontWeight: '700' }}>3.0:1</Text>
                </View>
                <Text style={{ color: C.sec, fontSize: 12 }}>{tx('admin.accessibilityPanel.auto.text.012', 'Large text (18pt+ / 14pt bold+) and UI components')}</Text>
              </View>
            </View>
          </View>

          {!report && (
            <View style={{ backgroundColor: C.card, borderRadius: 12, padding: 32, alignItems: 'center', borderWidth: 1, borderColor: C.border }}>
              <Ionicons name="accessibility-outline" size={40} color={C.muted} />
              <Text style={{ color: C.text, fontSize: 15, fontWeight: '600', marginTop: 12 }}>{tx('admin.accessibilityPanel.auto.text.013', 'No Audits Yet')}</Text>
              <Text style={{ color: C.muted, fontSize: 12, marginTop: 4, textAlign: 'center' }}>{tx('admin.accessibilityPanel.auto.text.014', 'Click "Run Audit" to scan for WCAG contrast violations.')}</Text>
            </View>
          )}
        </>
      )}

      {/* ═══ VIOLATIONS TAB ═══ */}
      {tab === 'violations' && (
        <>
          {report?.violations?.length > 0 ? (
            <>
              {/* Group violations by category */}
              {(['contrast', 'aria', 'keyboard', 'focus'] as const).map(cat => {
                const catViols = report.violations.filter((v: any) => {
                  if (cat === 'contrast') return !v.category || v.category === 'contrast';
                  return v.category === cat;
                });
                if (catViols.length === 0) return null;
                const catMeta: Record<string, { label: string; color: string; icon: string }> = {
                  contrast: { label: 'Contrast Violations', color: C.cyan, icon: 'color-palette' },
                  aria: { label: 'ARIA Label Violations', color: C.purpleText, icon: 'text' },
                  keyboard: { label: 'Keyboard Navigation', color: C.blue, icon: 'keypad' },
                  focus: { label: 'Focus Indicators', color: C.orangeText, icon: 'scan' },
                };
                const meta = catMeta[cat];
                return (
                  <View key={cat} data-testid={`a11y-violations-${cat}`} testID={`a11y-violations-${cat}`} style={{ backgroundColor: C.card, borderRadius: 12, borderWidth: 1, borderColor: C.border, overflow: 'hidden' }}>
                    <View style={{ paddingHorizontal: 16, paddingVertical: 12, borderBottomWidth: 1, borderBottomColor: C.border, flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                      <Ionicons name={meta.icon as any} size={14} color={meta.color} />
                      <Text style={{ color: C.text, fontSize: 14, fontWeight: '700', flex: 1 }}>{meta.label}</Text>
                      <View style={{ paddingHorizontal: 8, paddingVertical: 2, borderRadius: 6, backgroundColor: (globalThis as any).__alphaColor(meta.color, '18') }}>
                        <Text style={{ color: meta.color, fontSize: 11, fontWeight: '700' }}>{catViols.length}</Text>
                      </View>
                    </View>
                    {cat === 'contrast' ? (
                      <>
                        <View style={{ flexDirection: 'row', paddingHorizontal: 16, paddingVertical: 8, backgroundColor: C.bg, borderBottomWidth: 1, borderBottomColor: C.border }}>
                          <Text style={{ flex: 2, color: C.muted, fontSize: 10, fontWeight: '700' }}>{tx('admin.accessibilityPanel.auto.text.015', 'FILE')}</Text>
                          <Text style={{ flex: 1, color: C.muted, fontSize: 10, fontWeight: '700', textAlign: 'center' }}>{tx('admin.accessibilityPanel.auto.text.016', 'LINE')}</Text>
                          <Text style={{ flex: 1, color: C.muted, fontSize: 10, fontWeight: '700' }}>{tx('admin.accessibilityPanel.auto.text.017', 'FG')}</Text>
                          <Text style={{ flex: 1, color: C.muted, fontSize: 10, fontWeight: '700' }}>{tx('admin.accessibilityPanel.auto.text.018', 'BG')}</Text>
                          <Text style={{ flex: 1, color: C.muted, fontSize: 10, fontWeight: '700', textAlign: 'center' }}>{tx('admin.accessibilityPanel.auto.text.019', 'RATIO')}</Text>
                        </View>
                        {catViols.slice(0, 20).map((v: any, i: number) => (
                          <View key={i} data-testid={`violation-contrast-${i}`} testID={`violation-contrast-${i}`} style={{ flexDirection: 'row', alignItems: 'center', paddingHorizontal: 16, paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: C.border }}>
                            <Text style={{ flex: 2, color: C.cyan, fontSize: 11 }} numberOfLines={1}>{v.file}</Text>
                            <Text style={{ flex: 1, color: C.sec, fontSize: 11, textAlign: 'center' }}>{v.line}</Text>
                            <View style={{ flex: 1, flexDirection: 'row', alignItems: 'center', gap: 4 }}>
                              <View style={{ width: 12, height: 12, borderRadius: 3, backgroundColor: v.fg_color, borderWidth: 1, borderColor: C.border }} />
                              <Text style={{ color: C.sec, fontSize: 10, fontFamily: 'monospace' }}>{v.fg_color}</Text>
                            </View>
                            <View style={{ flex: 1, flexDirection: 'row', alignItems: 'center', gap: 4 }}>
                              <View style={{ width: 12, height: 12, borderRadius: 3, backgroundColor: v.bg_color, borderWidth: 1, borderColor: C.border }} />
                              <Text style={{ color: C.sec, fontSize: 10, fontFamily: 'monospace' }}>{v.bg_color}</Text>
                            </View>
                            <Text style={{ flex: 1, color: v.ratio < 3 ? C.red : C.yellow, fontSize: 12, fontWeight: '700', textAlign: 'center' }}>{v.ratio}:1</Text>
                          </View>
                        ))}
                      </>
                    ) : (
                      <>
                        <View style={{ flexDirection: 'row', paddingHorizontal: 16, paddingVertical: 8, backgroundColor: C.bg, borderBottomWidth: 1, borderBottomColor: C.border }}>
                          <Text style={{ flex: 2, color: C.muted, fontSize: 10, fontWeight: '700' }}>{tx('admin.accessibilityPanel.auto.text.020', 'FILE')}</Text>
                          <Text style={{ flex: 1, color: C.muted, fontSize: 10, fontWeight: '700', textAlign: 'center' }}>{tx('admin.accessibilityPanel.auto.text.021', 'LINE')}</Text>
                          <Text style={{ flex: 1, color: C.muted, fontSize: 10, fontWeight: '700' }}>{tx('admin.accessibilityPanel.auto.text.022', 'ELEMENT')}</Text>
                          <Text style={{ flex: 2, color: C.muted, fontSize: 10, fontWeight: '700' }}>{tx('admin.accessibilityPanel.auto.text.023', 'ISSUE')}</Text>
                          <Text style={{ flex: 1, color: C.muted, fontSize: 10, fontWeight: '700', textAlign: 'center' }}>{tx('admin.accessibilityPanel.auto.text.024', 'FIXABLE')}</Text>
                        </View>
                        {catViols.slice(0, 20).map((v: any, i: number) => (
                          <View key={i} data-testid={`violation-${cat}-${i}`} testID={`violation-${cat}-${i}`} style={{ flexDirection: 'row', alignItems: 'center', paddingHorizontal: 16, paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: C.border }}>
                            <Text style={{ flex: 2, color: meta.color, fontSize: 11 }} numberOfLines={1}>{v.file}</Text>
                            <Text style={{ flex: 1, color: C.sec, fontSize: 11, textAlign: 'center' }}>{v.line}</Text>
                            <View style={{ flex: 1 }}>
                              <View style={{ paddingHorizontal: 6, paddingVertical: 2, borderRadius: 4, backgroundColor: (globalThis as any).__alphaColor(meta.color, '15'), alignSelf: 'flex-start' }}>
                                <Text style={{ color: meta.color, fontSize: 10, fontWeight: '600' }}>{v.element}</Text>
                              </View>
                            </View>
                            <Text style={{ flex: 2, color: C.sec, fontSize: 10 }} numberOfLines={2}>{v.message}</Text>
                            <View style={{ flex: 1, alignItems: 'center' }}>
                              <Ionicons name={v.fixable ? 'checkmark-circle' : 'close-circle'} size={14} color={v.fixable ? C.green : C.muted} />
                            </View>
                          </View>
                        ))}
                      </>
                    )}
                    {catViols.length > 20 && (
                      <View style={{ padding: 10, alignItems: 'center' }}>
                        <Text style={{ color: C.muted, fontSize: 11 }}>...and {catViols.length - 20} more</Text>
                      </View>
                    )}
                  </View>
                );
              })}
            </>
          ) : (
            <View style={{ backgroundColor: C.card, borderRadius: 12, padding: 32, alignItems: 'center', borderWidth: 1, borderColor: C.border }}>
              <Ionicons name="checkmark-circle" size={40} color={C.green} />
              <Text style={{ color: C.text, fontSize: 15, fontWeight: '600', marginTop: 12 }}>{tx('admin.accessibilityPanel.auto.text.025', 'No Violations Found')}</Text>
              <Text style={{ color: C.muted, fontSize: 12, marginTop: 4, textAlign: 'center' }}>
                {report ? 'All checks pass WCAG AA accessibility requirements.' : 'Run an audit to check for violations.'}
              </Text>
            </View>
          )}
        </>
      )}

      {/* ═══ HISTORY TAB ═══ */}
      {tab === 'history' && (
        <>
          {fixHistory.length > 0 ? (
            <View data-testid="a11y-fix-history" testID="a11y-fix-history" style={{ backgroundColor: C.card, borderRadius: 12, borderWidth: 1, borderColor: C.border, overflow: 'hidden' }}>
              <View style={{ paddingHorizontal: 16, paddingVertical: 12, borderBottomWidth: 1, borderBottomColor: C.border, flexDirection: 'row', justifyContent: 'space-between' }}>
                <Text style={{ color: C.text, fontSize: 14, fontWeight: '700' }}>{tx('admin.accessibilityPanel.auto.text.026', 'Fix History')}</Text>
                <Text style={{ color: C.muted, fontSize: 11 }}>{fixHistory.length} runs</Text>
              </View>
              <View style={{ flexDirection: 'row', paddingHorizontal: 16, paddingVertical: 8, backgroundColor: C.bg, borderBottomWidth: 1, borderBottomColor: C.border }}>
                <Text style={{ flex: 2, color: C.muted, fontSize: 10, fontWeight: '700' }}>{tx('admin.accessibilityPanel.auto.text.027', 'DATE')}</Text>
                <Text style={{ flex: 1, color: C.muted, fontSize: 10, fontWeight: '700', textAlign: 'center' }}>{tx('admin.accessibilityPanel.auto.text.028', 'SOURCE')}</Text>
                <Text style={{ flex: 1, color: C.muted, fontSize: 10, fontWeight: '700', textAlign: 'center' }}>{tx('admin.accessibilityPanel.auto.text.029', 'BEFORE')}</Text>
                <Text style={{ flex: 1, color: C.muted, fontSize: 10, fontWeight: '700', textAlign: 'center' }}>{tx('admin.accessibilityPanel.auto.text.030', 'AFTER')}</Text>
                <Text style={{ flex: 1, color: C.muted, fontSize: 10, fontWeight: '700', textAlign: 'center' }}>{tx('admin.accessibilityPanel.auto.text.031', 'FIXED')}</Text>
                <Text style={{ flex: 1, color: C.muted, fontSize: 10, fontWeight: '700', textAlign: 'center' }}>{tx('admin.accessibilityPanel.auto.text.032', 'FILES')}</Text>
              </View>
              {fixHistory.map((fix: any, i: number) => (
                <View key={i} data-testid={`a11y-fix-row-${i}`} testID={`a11y-fix-row-${i}`} style={{
                  flexDirection: 'row', alignItems: 'center', paddingHorizontal: 16, paddingVertical: 10,
                  borderBottomWidth: 1, borderBottomColor: C.border,
                }}>
                  <View style={{ flex: 2 }}>
                    <Text style={{ color: C.sec, fontSize: 11 }}>{new Date(fix.timestamp).toLocaleString()}</Text>
                  </View>
                  <View style={{ flex: 1, alignItems: 'center' }}>
                    <View style={{ paddingHorizontal: 8, paddingVertical: 2, borderRadius: 6, backgroundColor: fix.source === 'scheduled' ? (globalThis as any).__alphaColor(C.cyan, '18') : C.purple + '18' }}>
                      <Text style={{ color: fix.source === 'scheduled' ? C.cyan : C.purple, fontSize: 10, fontWeight: '600' }}>{fix.source}</Text>
                    </View>
                  </View>
                  <Text style={{ flex: 1, color: C.sec, fontSize: 12, fontWeight: '600', textAlign: 'center' }}>{fix.before_violations}</Text>
                  <Text style={{ flex: 1, color: C.text, fontSize: 12, fontWeight: '700', textAlign: 'center' }}>{fix.after_violations}</Text>
                  <Text style={{ flex: 1, color: C.green, fontSize: 12, fontWeight: '800', textAlign: 'center' }}>{fix.fixes_applied}</Text>
                  <Text style={{ flex: 1, color: C.sec, fontSize: 12, fontWeight: '600', textAlign: 'center' }}>{fix.files_modified}</Text>
                </View>
              ))}
            </View>
          ) : (
            <View style={{ backgroundColor: C.card, borderRadius: 12, padding: 32, alignItems: 'center', borderWidth: 1, borderColor: C.border }}>
              <Ionicons name="time-outline" size={40} color={C.muted} />
              <Text style={{ color: C.text, fontSize: 15, fontWeight: '600', marginTop: 12 }}>{tx('admin.accessibilityPanel.auto.text.033', 'No Fix History Yet')}</Text>
              <Text style={{ color: C.muted, fontSize: 12, marginTop: 4, textAlign: 'center' }}>{tx('admin.accessibilityPanel.auto.text.034', 'Click "Auto-Fix" or wait for the daily scheduled run.')}</Text>
            </View>
          )}

          {/* Fix Details (latest) */}
          {fixHistory.length > 0 && fixHistory[0].fix_details?.length > 0 && (
            <View data-testid="a11y-fix-details" testID="a11y-fix-details" style={{ backgroundColor: C.card, borderRadius: 12, borderWidth: 1, borderColor: C.border, overflow: 'hidden' }}>
              <View style={{ paddingHorizontal: 16, paddingVertical: 12, borderBottomWidth: 1, borderBottomColor: C.border }}>
                <Text style={{ color: C.text, fontSize: 14, fontWeight: '700' }}>{tx('admin.accessibilityPanel.auto.text.035', 'Latest Fix Details')}</Text>
              </View>
              {fixHistory[0].fix_details.map((d: any, i: number) => (
                <View key={i} style={{ paddingHorizontal: 16, paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: C.border }}>
                  <Text style={{ color: C.cyan, fontSize: 11 }}>{d.file}:{d.line}</Text>
                  {d.category === 'aria' ? (
                    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginTop: 6 }}>
                      <View style={{ paddingHorizontal: 6, paddingVertical: 2, borderRadius: 4, backgroundColor: (globalThis as any).__alphaColor(C.purple, '18') }}>
                        <Text style={{ color: C.purpleText, fontSize: 10, fontWeight: '600' }}>{d.element || 'ARIA'}</Text>
                      </View>
                      <Text style={{ color: C.sec, fontSize: 11, flex: 1 }} numberOfLines={1}>{d.fix}</Text>
                    </View>
                  ) : d.category === 'keyboard' ? (
                    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginTop: 6 }}>
                      <View style={{ paddingHorizontal: 6, paddingVertical: 2, borderRadius: 4, backgroundColor: (globalThis as any).__alphaColor(C.blue, '18') }}>
                        <Text style={{ color: C.blue, fontSize: 10, fontWeight: '600' }}>{tx('admin.accessibilityPanel.auto.text.036', 'Keyboard')}</Text>
                      </View>
                      <Text style={{ color: C.sec, fontSize: 11, flex: 1 }} numberOfLines={1}>{d.fix}</Text>
                    </View>
                  ) : d.category === 'focus' ? (
                    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginTop: 6 }}>
                      <View style={{ paddingHorizontal: 6, paddingVertical: 2, borderRadius: 4, backgroundColor: (globalThis as any).__alphaColor(C.orange, '18') }}>
                        <Text style={{ color: C.orangeText, fontSize: 10, fontWeight: '600' }}>{tx('admin.accessibilityPanel.auto.text.037', 'Focus')}</Text>
                      </View>
                      <Text style={{ color: C.sec, fontSize: 11, flex: 1 }} numberOfLines={1}>{d.fix}</Text>
                    </View>
                  ) : (
                    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginTop: 6 }}>
                      {d.old_color && <ColorSwatch hex={d.old_color} />}
                      {d.old_ratio && <Text style={{ color: C.muted, fontSize: 11 }}>({d.old_ratio}:1)</Text>}
                      <Ionicons name="arrow-forward" size={12} color={C.green} />
                      {d.new_color && <ColorSwatch hex={d.new_color} />}
                      {d.new_ratio && <Text style={{ color: C.green, fontSize: 11 }}>({d.new_ratio}:1)</Text>}
                      {d.bg_color && <><Text style={{ color: C.muted, fontSize: 10 }}>{tx('admin.accessibilityPanel.auto.text.038', 'on')}</Text><ColorSwatch hex={d.bg_color} /></>}
                    </View>
                  )}
                </View>
              ))}
            </View>
          )}
        </>
      )}
    </ScrollView>
  );
}
