import React, { useState, useCallback, useEffect } from 'react';
import { View, Text, TouchableOpacity, ActivityIndicator, ScrollView, Platform } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useLiveQuery } from '../../hooks/useLiveQuery';
import api from '../../services/api';

import { useAdminTheme } from '../../hooks/useAdminTheme';
import { useTranslation } from '../../hooks/useTranslation';
function makeC(AC: any) {
  return {
    ...AC,
    bg: AC.bg,
    card: AC.card,
    border: AC.border,
    text: AC.text,
    muted: AC.textDim,
    green: AC.success,
    red: AC.error,
    yellow: AC.warning,
    orange: AC.orange,
    blue: AC.primary,
    purple: AC.purple,
    purpleText: AC.purpleText,
    cyan: AC.info,
    overlay: AC.overlay,
  };
}

// Module-level fallback palette used by the helper sub-components that
// render OUTSIDE the main component function body (ScoreRing, StatCard,
// CheckRow). The main component shadows this with a theme-aware copy
// via `const C = makeC(AC)` inside its own scope.
const C = {
  bg: 'var(--app-bg)' as any,
  card: 'var(--app-card-bg)' as any,
  border: 'var(--app-border)' as any,
  text: 'var(--app-text)' as any,
  muted: 'var(--app-text-muted)' as any,
  green: 'var(--app-success)' as any,
  red: 'var(--app-error)' as any,
  yellow: 'var(--app-warning)' as any,
  orange: 'rgb(249,115,22)' as any,
  blue: 'var(--app-primary)' as any,
  purple: 'var(--app-primary)' as any,
  purpleText: 'var(--app-primary)' as any,
  cyan: 'var(--app-info)' as any,
  overlay: 'rgba(8,14,36,0.72)' as any,
};

const tx = (_key: string, fallback: string) => fallback;

const GRADE_COLORS: Record<string, string> = { A: C.green, B: C.green, C: C.yellow, D: C.orange, F: C.red };

function ScoreRing({ score, grade }: { score: number; grade: string }) {
  const color = GRADE_COLORS[grade] || C.muted;
  const circumference = 2 * Math.PI * 54;
  const dashoffset = circumference * (1 - score / 100);
  return (
    <View style={{ alignItems: 'center', justifyContent: 'center', width: 140, height: 140 }} data-testid="security-score-ring" testID="security-score-ring">
      {Platform.OS === 'web' ? (
        <svg width="140" height="140" viewBox="0 0 140 140" style={{ position: 'absolute' } as any}>
          <circle cx="70" cy="70" r="54" fill="none" stroke={C.border} strokeWidth="8" />
          <circle cx="70" cy="70" r="54" fill="none" stroke={color} strokeWidth="8" strokeLinecap="round" strokeDasharray={circumference} strokeDashoffset={dashoffset} transform="rotate(-90 70 70)" style={{ transition: 'stroke-dashoffset 1s ease' } as any} />
        </svg>
      ) : null}
      <View style={{ alignItems: 'center' }}>
        <Text style={{ fontSize: 32, fontWeight: '900', color }}>{score}</Text>
        <Text style={{ fontSize: 12, fontWeight: '700', color: C.muted, marginTop: -2 }}>/ 100</Text>
        <View style={{ marginTop: 4, backgroundColor: (globalThis as any).__alphaColor(color, '20'), paddingHorizontal: 10, paddingVertical: 2, borderRadius: 8 }}>
          <Text style={{ fontSize: 13, fontWeight: '800', color }}>Grade {grade}</Text>
        </View>
      </View>
    </View>
  );
}

function StatCard({ icon, label, value, color }: { icon: string; label: string; value: number | string; color: string }) {
  return (
    <View style={{ flex: 1, backgroundColor: C.card, borderRadius: 12, padding: 14, borderWidth: 1, borderColor: C.border, alignItems: 'center', minWidth: 100 }}>
      <Ionicons name={icon as any} size={18} color={color} />
      <Text style={{ fontSize: 20, fontWeight: '800', color, marginTop: 6 }}>{value}</Text>
      <Text style={{ fontSize: 10, color: C.muted, marginTop: 2, textAlign: 'center' }}>{label}</Text>
    </View>
  );
}

function CheckRow({ check }: { check: any }) {
  const statusIcon = check.status === 'pass' ? 'checkmark-circle' : check.status === 'warn' ? 'warning' : 'close-circle';
  const statusColor = check.status === 'pass' ? C.green : check.status === 'warn' ? C.yellow : C.red;
  const severityColor = check.severity === 'critical' ? C.red : check.severity === 'high' ? C.orange : C.yellow;
  return (
    <View style={{ flexDirection: 'row', alignItems: 'center', paddingVertical: 10, paddingHorizontal: 14, borderBottomWidth: 1, borderBottomColor: (globalThis as any).__alphaColor(C.border, '60'), gap: 10 }} data-testid={`check-${check.id}`} testID={`check-${check.id}`}>
      <Ionicons name={statusIcon as any} size={18} color={statusColor} />
      <View style={{ flex: 1 }}>
        <Text style={{ fontSize: 13, fontWeight: '600', color: C.text }}>{check.name}</Text>
        <Text style={{ fontSize: 11, color: C.muted, marginTop: 2 }}>{check.detail}</Text>
      </View>
      <View style={{ backgroundColor: (globalThis as any).__alphaColor(severityColor, '18'), paddingHorizontal: 8, paddingVertical: 2, borderRadius: 6 }}>
        <Text style={{ fontSize: 9, fontWeight: '700', color: severityColor, textTransform: 'uppercase' }}>{check.severity}</Text>
      </View>
      {check.fixed && (
        <View style={{ backgroundColor: (globalThis as any).__alphaColor(C.green, '18'), paddingHorizontal: 6, paddingVertical: 2, borderRadius: 6 }}>
          <Text style={{ fontSize: 9, fontWeight: '700', color: C.green }}>{tx('admin.securityPosturePanel.auto.text.001', 'FIXED')}</Text>
        </View>
      )}
    </View>
  );
}

function HistoryChart({ C: colors }: { C: any }) {
  const [history, setHistory] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [hoveredIdx, setHoveredIdx] = useState<number | null>(null);

  useEffect(() => {
    let mounted = true;
    (async () => {
      try {
        const res = await api.get('/admin/security-posture/history?limit=30');
        if (mounted) setHistory((res.data?.scans || []).reverse());
      } catch { /* ignore */ }
      if (mounted) setLoading(false);
    })();
    return () => { mounted = false; };
  }, []);

  if (loading) return <ActivityIndicator size="small" color={colors.blue} style={{ padding: 20 }} />;
  if (!history.length) return (
    <View style={{ padding: 20, alignItems: 'center' }}>
      <Text style={{ color: colors.muted, fontSize: 12 }}>{tx('admin.securityPosturePanel.auto.text.002', 'No scan history yet. First nightly scan runs at 3:00 AM UTC.')}</Text>
    </View>
  );

  const W = 520, H = 140, PX = 36, PY = 16;
  const cW = W - PX * 2, cH = H - PY * 2 - 16;
  const minS = Math.min(...history.map(s => s.score));
  const lo = Math.max(0, Math.floor(minS / 10) * 10 - 10);
  const hi = 100;
  const pts = history.map((s, i) => {
    const x = PX + (history.length > 1 ? (i / (history.length - 1)) * cW : cW / 2);
    const y = PY + cH - ((s.score - lo) / (hi - lo)) * cH;
    return { x, y, s };
  });
  const polyline = pts.map(p => `${p.x},${p.y}`).join(' ');
  const areaPath = `M${pts[0].x},${PY + cH} ${pts.map(p => `L${p.x},${p.y}`).join(' ')} L${pts[pts.length - 1].x},${PY + cH} Z`;

  const gridLines = [lo, lo + (hi - lo) * 0.25, lo + (hi - lo) * 0.5, lo + (hi - lo) * 0.75, hi].map(v => Math.round(v));

  const gradeOf = (sc: number) => sc >= 90 ? 'A' : sc >= 80 ? 'B' : sc >= 70 ? 'C' : sc >= 60 ? 'D' : 'F';
  const colorOf = (sc: number) => { const g = gradeOf(sc); return g === 'A' ? colors.green : g === 'B' ? colors.green : g === 'C' ? colors.yellow : g === 'D' ? colors.orange : colors.red; };
  const latestScore = history[history.length - 1]?.score ?? 0;
  const prevScore = history.length > 1 ? history[history.length - 2]?.score ?? latestScore : latestScore;
  const delta = latestScore - prevScore;
  const fmtDate = (ts: string) => { const d = new Date(ts); return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')} ${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}`; };

  if (Platform.OS !== 'web') return null;

  const hp = hoveredIdx !== null ? pts[hoveredIdx] : null;
  const hs = hp?.s;

  return (
    <View style={{ backgroundColor: colors.card, borderRadius: 14, borderWidth: 1, borderColor: colors.border, padding: 16, marginBottom: 20 }} data-testid="security-history-chart" testID="security-history-chart">
      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
          <Ionicons name="trending-up" size={16} color={colors.cyan} />
          <Text style={{ fontSize: 14, fontWeight: '700', color: colors.text }}>{tx('admin.securityPosturePanel.auto.text.003', 'Score Trend')}</Text>
          <Text style={{ fontSize: 11, color: colors.muted }}>Last {history.length} scans</Text>
        </View>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
          {delta !== 0 && (
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 3, backgroundColor: delta > 0 ? (globalThis as any).__alphaColor(colors.green, '18') : colors.red + '18', paddingHorizontal: 8, paddingVertical: 2, borderRadius: 6 }}>
              <Ionicons name={delta > 0 ? 'arrow-up' : 'arrow-down'} size={10} color={delta > 0 ? colors.green : colors.red} />
              <Text style={{ fontSize: 10, fontWeight: '700', color: delta > 0 ? colors.green : colors.red }}>{delta > 0 ? '+' : ''}{delta}%</Text>
            </View>
          )}
          <View style={{ backgroundColor: (globalThis as any).__alphaColor(colorOf(latestScore), '18'), paddingHorizontal: 8, paddingVertical: 2, borderRadius: 6 }}>
            <Text style={{ fontSize: 10, fontWeight: '700', color: colorOf(latestScore) }}>{latestScore}% ({gradeOf(latestScore)})</Text>
          </View>
        </View>
      </View>
      <div style={{ width: '100%', overflow: 'visible', position: 'relative' }} onMouseLeave={() => setHoveredIdx(null)}>
        <svg width="100%" height={H} viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" style={{ display: 'block' }}>
          {gridLines.map((v, i) => {
            const y = PY + cH - ((v - lo) / (hi - lo)) * cH;
            return (
              <g key={i}>
                <line x1={PX} y1={y} x2={W - PX} y2={y} stroke={colors.border} strokeWidth="0.5" strokeDasharray="4 3" />
                <text x={PX - 6} y={y + 3} textAnchor="end" fill={colors.muted} fontSize="9" fontWeight="600">{v}</text>
              </g>
            );
          })}
          <defs>
            <linearGradient id="areaGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={colors.cyan} stopOpacity="0.25" />
              <stop offset="100%" stopColor={colors.cyan} stopOpacity="0" />
            </linearGradient>
          </defs>
          <path d={areaPath} fill="url(#areaGrad)" />
          <polyline points={polyline} fill="none" stroke={colors.cyan} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
          {/* Hover crosshair */}
          {hp && (
            <line x1={hp.x} y1={PY} x2={hp.x} y2={PY + cH} stroke={colors.cyan} strokeWidth="1" strokeDasharray="3 2" opacity="0.5" />
          )}
          {/* Data points */}
          {pts.map((p, i) => (
            <circle key={i} cx={p.x} cy={p.y} r={hoveredIdx === i ? 5 : (history.length <= 15 ? 3.5 : 2)} fill={colorOf(p.s.score)} stroke={hoveredIdx === i ? colors.text : colors.card} strokeWidth={hoveredIdx === i ? 2 : 1.5} style={{ transition: 'r 0.15s ease, stroke-width 0.15s ease' } as any} />
          ))}
          {/* Score degradation annotations */}
          {pts.map((p, i) => {
            if (i === 0) return null;
            const prev = pts[i - 1];
            const drop = prev.s.score - p.s.score;
            if (drop <= 0) return null;
            const mx = (prev.x + p.x) / 2;
            const my = (prev.y + p.y) / 2;
            const isCritical = drop >= 5;
            const flagColor = isCritical ? colors.red : colors.yellow;
            return (
              <g key={`drop${i}`}>
                <line x1={prev.x} y1={prev.y} x2={p.x} y2={p.y} stroke={flagColor} strokeWidth="2" strokeDasharray="4 2" opacity="0.6" />
                <polygon points={`${mx},${my - 3} ${mx - 4},${my - 10} ${mx + 4},${my - 10}`} fill={flagColor} />
                <rect x={mx - 22} y={my - 24} width={44} height={14} rx={4} fill={flagColor} opacity="0.9" />
                <text x={mx} y={my - 14} textAnchor="middle" fill={colors.primaryText} fontSize="8" fontWeight="700">-{drop}%</text>
              </g>
            );
          })}
          {/* Score recovery annotations */}
          {pts.map((p, i) => {
            if (i < 2) return null;
            const prev = pts[i - 1];
            const prevPrev = pts[i - 2];
            const prevDrop = prevPrev.s.score - prev.s.score;
            const recovery = p.s.score - prev.s.score;
            if (prevDrop <= 0 || recovery <= 0) return null;
            const mx = (prev.x + p.x) / 2;
            const my = (prev.y + p.y) / 2;
            return (
              <g key={`rec${i}`}>
                <line x1={prev.x} y1={prev.y} x2={p.x} y2={p.y} stroke={colors.green} strokeWidth="2" strokeDasharray="4 2" opacity="0.6" />
                <polygon points={`${mx},${my + 3} ${mx - 4},${my + 10} ${mx + 4},${my + 10}`} fill={colors.green} transform={`rotate(180 ${mx} ${my + 6.5})`} />
                <rect x={mx - 28} y={my - 24} width={56} height={14} rx={4} fill={colors.green} opacity="0.9" />
                <text x={mx} y={my - 14} textAnchor="middle" fill={colors.primaryText} fontSize="8" fontWeight="700">+{recovery}% rec</text>
              </g>
            );
          })}
          {/* Invisible hover hit areas */}
          {pts.map((p, i) => {
            const hitW = history.length > 1 ? cW / (history.length - 1) : cW;
            return (
              <rect key={`h${i}`} x={p.x - hitW / 2} y={0} width={hitW} height={H} fill="transparent" style={{ cursor: 'pointer' } as any} onMouseEnter={() => setHoveredIdx(i)} />
            );
          })}
          {/* Date labels */}
          {pts.length > 0 && history.length <= 15 && pts.map((p, i) => {
            const d = new Date(p.s.timestamp);
            const label = `${d.getMonth() + 1}/${d.getDate()}`;
            return <text key={`l${i}`} x={p.x} y={PY + cH + 14} textAnchor="middle" fill={colors.muted} fontSize="8" fontWeight="500">{label}</text>;
          })}
        </svg>
        {/* Tooltip */}
        {hp && hs && (
          <div style={{
            position: 'absolute',
            left: Math.min(Math.max(hp.x * (100 / W), 5), 70) + '%',
            top: Math.max(hp.y * (100 / H) - 55, 2) + '%',
            transform: 'translateX(-50%)',
            background: colors.card,
            border: `1px solid ${colors.border}`,
            borderRadius: 10,
            padding: '8px 12px',
            boxShadow: `0 4px 20px ${colors.overlay}`,
            zIndex: 50,
            pointerEvents: 'none' as any,
            minWidth: 160,
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
              <span style={{ display: 'inline-block', width: 8, height: 8, borderRadius: 4, background: colorOf(hs.score) }} />
              <span style={{ fontSize: 15, fontWeight: 800, color: colorOf(hs.score) }}>{hs.score}%</span>
              <span style={{ fontSize: 11, fontWeight: 700, color: colors.muted }}>Grade {gradeOf(hs.score)}</span>
            </div>
            <div style={{ fontSize: 10, color: colors.muted, marginBottom: 6 }}>{fmtDate(hs.timestamp)}</div>
            <div style={{ display: 'flex', gap: 8, fontSize: 10, fontWeight: 600 }}>
              <span style={{ color: colors.green }}>{hs.passed ?? '?'} pass</span>
              <span style={{ color: colors.yellow }}>{hs.warnings ?? 0} warn</span>
              <span style={{ color: colors.red }}>{hs.failed ?? 0} fail</span>
            </div>
            <div style={{ fontSize: 9, color: colors.muted, marginTop: 4 }}>
              {hs.source === 'nightly_cron' ? 'Nightly auto-scan' : hs.source === 'auto_fix' ? 'Auto-fix scan' : 'Manual scan'}
            </div>
          </div>
        )}
      </div>
    </View>
  );
}

export default function SecurityPosturePanel({ colors }: { colors: any }) {
  const { t } = useTranslation();
  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };


  const AC = useAdminTheme();
  const C = React.useMemo(() => makeC(AC), [AC]);
  const { data, loading, refetch } = useLiveQuery('/admin/security-posture/scan', { entity: 'security-posture', pollInterval: 300000 });
  const [fixing, setFixing] = useState(false);

  const handleAutoFix = useCallback(async () => {
    setFixing(true);
    try {
      await api.get('/admin/security-posture/scan?auto_fix=true');
      refetch();
    } catch (e) {
      console.error('Auto-fix failed:', e);
    } finally {
      setFixing(false);
    }
  }, [refetch]);

  if (loading || !data) {
    return (
      <View style={{ flex: 1, padding: 24, alignItems: 'center', justifyContent: 'center' }}>
        <ActivityIndicator size="large" color={C.blue} />
        <Text style={{ color: C.muted, marginTop: 12, fontSize: 13 }}>{tx('admin.securityPosturePanel.auto.text.004', 'Running security scan...')}</Text>
      </View>
    );
  }

  const categories = data.categories || {};
  const threats = data.threat_summary || {};

  return (
    <ScrollView style={{ flex: 1, backgroundColor: C.bg }} contentContainerStyle={{ padding: 20 }}>
      {/* Header */}
      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 24 }} data-testid="security-posture-header" testID="security-posture-header">
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 12 }}>
          <View style={{ width: 36, height: 36, borderRadius: 10, backgroundColor: (globalThis as any).__alphaColor(C.green, '18'), alignItems: 'center', justifyContent: 'center' }}>
            <Ionicons name="shield-checkmark" size={20} color={C.green} />
          </View>
          <View>
            <Text style={{ fontSize: 18, fontWeight: '800', color: C.text }}>{tx('admin.securityPosturePanel.auto.text.005', 'Security Posture')}</Text>
            <Text style={{ fontSize: 11, color: C.muted }}>{tx('admin.securityPosturePanel.auto.text.006', 'Automated security audit with Safe Auto-Fix')}</Text>
          </View>
        </View>
        <View style={{ flexDirection: 'row', gap: 8 }}>
          {(data.fixable || 0) > 0 && (
            <TouchableOpacity
              onPress={handleAutoFix}
              disabled={fixing}
              style={{ flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: C.green, paddingHorizontal: 14, paddingVertical: 8, borderRadius: 8 }}
              data-testid="auto-fix-btn" testID="auto-fix-btn"
            >
              {fixing ? <ActivityIndicator size="small" color={colors.primaryText} /> : <Ionicons name="construct" size={14} color={colors.primaryText} />}
              <Text style={{ fontSize: 12, fontWeight: '700', color: colors.primaryText }}>Auto-Fix ({data.fixable})</Text>
            </TouchableOpacity>
          )}
          <TouchableOpacity
            onPress={refetch}
            style={{ flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: C.card, borderWidth: 1, borderColor: C.border, paddingHorizontal: 14, paddingVertical: 8, borderRadius: 8 }}
            data-testid="rescan-btn" testID="rescan-btn"
          >
            <Ionicons name="refresh" size={14} color={C.blue} />
            <Text style={{ fontSize: 12, fontWeight: '700', color: C.blue }}>{tx('admin.securityPosturePanel.auto.text.007', 'Re-Scan')}</Text>
          </TouchableOpacity>
        </View>
      </View>

      {/* Score + Summary Row */}
      <View style={{ flexDirection: 'row', gap: 16, marginBottom: 20, flexWrap: 'wrap' }}>
        {/* Score Ring */}
        <View style={{ backgroundColor: C.card, borderRadius: 16, padding: 20, borderWidth: 1, borderColor: C.border, alignItems: 'center', justifyContent: 'center', minWidth: 180 }}>
          <ScoreRing score={data.score || 0} grade={data.grade || 'F'} />
          <Text style={{ fontSize: 11, color: C.muted, marginTop: 10 }}>{data.total_checks} checks run</Text>
        </View>
        {/* Stats Cards */}
        <View style={{ flex: 1, gap: 10, minWidth: 280 }}>
          <View style={{ flexDirection: 'row', gap: 10 }}>
            <StatCard icon="checkmark-circle" label="Passed" value={data.passed || 0} color={C.green} />
            <StatCard icon="warning" label="Warnings" value={data.warnings || 0} color={C.yellow} />
            <StatCard icon="close-circle" label="Failed" value={data.failed || 0} color={C.red} />
          </View>
          <View style={{ flexDirection: 'row', gap: 10 }}>
            <StatCard icon="shield" label="WAF Blocks 24h" value={threats.waf_blocks_24h || 0} color={C.purpleText} />
            <StatCard icon="ban" label="Blocked IPs" value={threats.blocked_ips || 0} color={C.red} />
            <StatCard icon="log-in" label="Login Fails 24h" value={threats.login_failures_24h || 0} color={C.yellow} />
          </View>
        </View>
      </View>

      {/* Score Trend Chart */}
      <HistoryChart C={C} />

      {/* Category Sections */}
      {Object.entries(categories).map(([catName, catData]: [string, any]) => (
        <View key={catName} style={{ backgroundColor: C.card, borderRadius: 14, marginBottom: 16, borderWidth: 1, borderColor: C.border, overflow: 'hidden' }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', padding: 14, backgroundColor: (globalThis as any).__alphaColor(C.border, '30') }}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
              <Ionicons name={catName === 'Authentication' ? 'lock-closed' : catName === 'Network' ? 'globe' : catName === 'Data Protection' ? 'key' : catName === 'Monitoring' ? 'eye' : catName === 'Route Exposure' ? 'scan' : 'server'} size={16} color={C.cyan} />
              <Text style={{ fontSize: 14, fontWeight: '700', color: C.text }}>{catName}</Text>
            </View>
            <View style={{ backgroundColor: catData.passed === catData.total ? (globalThis as any).__alphaColor(C.green, '18') : C.yellow + '18', paddingHorizontal: 10, paddingVertical: 3, borderRadius: 8 }}>
              <Text style={{ fontSize: 11, fontWeight: '700', color: catData.passed === catData.total ? C.green : C.yellow }}>{catData.passed}/{catData.total}</Text>
            </View>
          </View>
          {(catData.checks || []).map((check: any) => (
            <CheckRow key={check.id} check={check} />
          ))}
        </View>
      ))}
    </ScrollView>
  );
}
