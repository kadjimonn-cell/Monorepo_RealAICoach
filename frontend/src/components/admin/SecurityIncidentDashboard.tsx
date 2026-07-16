import React, { useState, useEffect, useCallback } from 'react';
import { View, Text, TouchableOpacity, ScrollView, ActivityIndicator, useWindowDimensions } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useExecTheme} from './ExecDashboardPanels';
import api from '../../services/api';
import { useAdminTheme } from '../../hooks/useAdminTheme';
import { useTranslation } from '../../hooks/useTranslation';

/* ── Types ── */
interface Breakdown { status: number; code: string; count: number }
interface TimelinePoint { hour: string; count_401: number; count_403: number }
interface PathEntry { path: string; status: number; code: string; count: number; last_seen: string }
interface IpEntry { ip: string; count: number; codes: string[]; last_seen: string }

/* ── Stat Card ── */
function StatCard({ label, value, color, icon, T }: { label: string; value: string | number; color: string; icon: string; T: any }) {
  return (
    <View style={{ flex: 1, minWidth: 130, backgroundColor: T.card, borderRadius: 14, padding: 16, borderWidth: 1, borderColor: T.border }} data-testid={`sec-stat-${label.toLowerCase().replace(/\s/g, '-')}`}>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 8 }}>
        <View style={{ width: 30, height: 30, borderRadius: 8, backgroundColor: (globalThis as any).__alphaColor(color, '18'), alignItems: 'center', justifyContent: 'center' }}>
          <Ionicons name={icon as any} size={14} color={color} />
        </View>
        <Text style={{ color: T.textMuted, fontSize: 10, fontWeight: '700', textTransform: 'uppercase', letterSpacing: 0.5 }}>{label}</Text>
      </View>
      <Text style={{ color: T.text, fontSize: 24, fontWeight: '800' }}>{value}</Text>
    </View>
  );
}

/* ── Bar Chart (CSS-only) ── */
function MiniBarChart({ data, T }: { data: TimelinePoint[]; T: any }) {
  if (!data.length) return <Text style={{ color: T.textMuted, fontSize: 12, textAlign: 'center', padding: 20 }}>{tx('admin.securityIncidentDashboard.auto.text.001', 'No data yet')}</Text>;
  const max = Math.max(...data.map(d => d.count_401 + d.count_403), 1);
  const last12 = data.slice(-12);

  return (
    <View style={{ flexDirection: 'row', alignItems: 'flex-end', gap: 3, height: 80, paddingTop: 4 }} data-testid="sec-timeline-chart">
      {last12.map((d, i) => {
        const h401 = (d.count_401 / max) * 70;
        const h403 = (d.count_403 / max) * 70;
        const hour = d.hour.slice(-2) + ':00';
        return (
          <View key={i} style={{ flex: 1, alignItems: 'center', gap: 2 }}>
            <View style={{ width: '80%', borderRadius: 3 }}>
              {h403 > 0 && <View style={{ height: h403, backgroundColor: T.warning, borderTopLeftRadius: 3, borderTopRightRadius: 3 }} />}
              {h401 > 0 && <View style={{ height: h401, backgroundColor: T.error, borderBottomLeftRadius: 3, borderBottomRightRadius: 3 }} />}
            </View>
            <Text style={{ color: T.textMuted, fontSize: 8 }}>{hour}</Text>
          </View>
        );
      })}
    </View>
  );
}

/* ── Table Row ── */
function TableRow({ children, header, T }: { children: React.ReactNode; header?: boolean; T: any }) {
  return (
    <View style={{
      flexDirection: 'row', paddingVertical: header ? 8 : 10, paddingHorizontal: 12,
      borderBottomWidth: 1, borderBottomColor: T.border,
      backgroundColor: header ? T.bgSoft : 'transparent',
    }}>
      {children}
    </View>
  );
}

const tx = (_key: string, fallback: string) => fallback;

function Cell({ children, flex, align, T }: { children: React.ReactNode; flex?: number; align?: 'left' | 'right' | 'center'; T: any }) {
  return (
    <Text style={{ flex: flex || 1, color: T.textSec, fontSize: 12, textAlign: align || 'left' }} numberOfLines={1}>
      {children}
    </Text>
  );
}

function HeaderCell({ children, flex, align, T }: { children: string; flex?: number; align?: 'left' | 'right' | 'center'; T: any }) {
  return (
    <Text style={{ flex: flex || 1, color: T.textMuted, fontSize: 10, fontWeight: '700', textTransform: 'uppercase', letterSpacing: 0.4, textAlign: align || 'left' }}>
      {children}
    </Text>
  );
}

/* ── Code Badge ── */
function CodeBadge({ code, T }: { code: string; T: any }) {
  const color = code.includes('403') || code.includes('ADMIN') ? 'var(--app-warning)' : 'var(--app-error)';
  return (
    <View style={{ paddingHorizontal: 6, paddingVertical: 2, borderRadius: 4, backgroundColor: (globalThis as any).__alphaColor(color, '18'), alignSelf: 'flex-start' }}>
      <Text style={{ color, fontSize: 9, fontWeight: '800' }}>{code}</Text>
    </View>
  );
}

/* ── Time ago ── */
function timeAgo(ts: string): string {
  const diff = Date.now() - new Date(ts).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

/* ── Main Dashboard ── */
export default function SecurityIncidentDashboard() {
  const { t } = useTranslation();
  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };

  const colors = useAdminTheme();
  const T = useExecTheme();
  const { width } = useWindowDimensions();
  const m = width < 768;

  const [hours, setHours] = useState(24);
  const [loading, setLoading] = useState(true);
  const [summary, setSummary] = useState<{ total: number; total_401: number; total_403: number; breakdown: Breakdown[] } | null>(null);
  const [timeline, setTimeline] = useState<TimelinePoint[]>([]);
  const [topPaths, setTopPaths] = useState<PathEntry[]>([]);
  const [topIps, setTopIps] = useState<IpEntry[]>([]);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const [sRes, tRes, pRes, iRes] = await Promise.all([
        api.get(`/admin/security-incidents/summary?hours=${hours}`),
        api.get(`/admin/security-incidents/timeline?hours=${hours}`),
        api.get(`/admin/security-incidents/top-paths?hours=${hours}`),
        api.get(`/admin/security-incidents/top-ips?hours=${hours}`),
      ]);
      setSummary(sRes.data);
      setTimeline(tRes.data?.timeline || []);
      setTopPaths(pRes.data?.paths || []);
      setTopIps(iRes.data?.ips || []);
    } catch (e) {
      console.error('Security incidents fetch error:', e);
    }
    setLoading(false);
  }, [hours]);

  useEffect(() => { fetchData(); }, [fetchData]);

  if (loading) {
    return (
      <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center', padding: 40 }} data-testid="sec-loading">
        <ActivityIndicator size="large" color={T.primary} />
        <Text style={{ color: T.textSec, fontSize: 13, marginTop: 12 }}>{tx('admin.securityIncidentDashboard.auto.text.002', 'Loading security incidents...')}</Text>
      </View>
    );
  }

  return (
    <ScrollView style={{ flex: 1 }} contentContainerStyle={{ padding: m ? 16 : 24 }} data-testid="security-incident-dashboard">
      {/* Header */}
      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 20, flexWrap: 'wrap', gap: 12 }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
          <View style={{ width: 40, height: 40, borderRadius: 12, backgroundColor: (globalThis as any).__alphaColor(colors.error, '18'), alignItems: 'center', justifyContent: 'center' }}>
            <Ionicons name="shield-half" size={20} color={colors.error} />
          </View>
          <View>
            <Text style={{ color: T.text, fontSize: 20, fontWeight: '800' }} data-testid="sec-panel-title">{tx('admin.securityIncidentDashboard.auto.text.003', 'Security Incidents')}</Text>
            <Text style={{ color: T.textMuted, fontSize: 12 }}>{tx('admin.securityIncidentDashboard.auto.text.004', '401/403 blocked request monitoring')}</Text>
          </View>
        </View>
        <View style={{ flexDirection: 'row', gap: 6 }}>
          {[1, 6, 24, 72].map(h => (
            <TouchableOpacity accessibilityLabel={tx('admin.securityIncidentDashboard.auto.accessibility.001', 'Set incident time window')}
              key={h}
              onPress={() => setHours(h)}
              style={{
                paddingHorizontal: 12, paddingVertical: 6, borderRadius: 8,
                backgroundColor: hours === h ? T.primary : T.bgSoft,
                borderWidth: 1, borderColor: hours === h ? T.primary : T.border,
              }}
              data-testid={`sec-filter-${h}h`}
            >
              <Text style={{ color: hours === h ? 'var(--app-primary-text)' : T.textSec, fontSize: 12, fontWeight: '700' }}>{h}h</Text>
            </TouchableOpacity>
          ))}
          <TouchableOpacity onPress={fetchData} style={{ paddingHorizontal: 10, paddingVertical: 6, borderRadius: 8, backgroundColor: T.bgSoft, borderWidth: 1, borderColor: T.border }} data-testid="sec-refresh-btn">
            <Ionicons name="refresh" size={14} color={T.textSec} />
          </TouchableOpacity>
        </View>
      </View>

      {/* Stats Row */}
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 12, marginBottom: 24 }} data-testid="sec-stats-row">
        <StatCard label="Total Blocked" value={summary?.total || 0} color={colors.error} icon="ban" T={T} />
        <StatCard label="401 Auth" value={summary?.total_401 || 0} color={colors.error} icon="lock-closed" T={T} />
        <StatCard label="403 Forbidden" value={summary?.total_403 || 0} color={colors.warningText} icon="hand-left" T={T} />
        <StatCard label="Unique IPs" value={topIps.length} color={colors.purpleText} icon="globe" T={T} />
        <StatCard label="Unique Paths" value={topPaths.length} color={colors.primary} icon="git-branch" T={T} />
      </View>

      {/* Timeline Chart */}
      <View style={{ backgroundColor: T.card, borderRadius: 14, padding: 16, marginBottom: 20, borderWidth: 1, borderColor: T.border }} data-testid="sec-timeline-section">
        <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
          <Text style={{ color: T.text, fontSize: 14, fontWeight: '700' }}>{tx('admin.securityIncidentDashboard.auto.text.005', 'Incident Timeline')}</Text>
          <View style={{ flexDirection: 'row', gap: 12 }}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}>
              <View style={{ width: 8, height: 8, borderRadius: 2, backgroundColor: colors.error }} />
              <Text style={{ color: T.textMuted, fontSize: 10 }}>401</Text>
            </View>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}>
              <View style={{ width: 8, height: 8, borderRadius: 2, backgroundColor: colors.warning }} />
              <Text style={{ color: T.textMuted, fontSize: 10 }}>403</Text>
            </View>
          </View>
        </View>
        <MiniBarChart data={timeline} T={T} />
      </View>

      {/* Two Column: Top Paths + Top IPs */}
      <View style={{ flexDirection: m ? 'column' : 'row', gap: 16, marginBottom: 20 }}>
        {/* Top Blocked Paths */}
        <View style={{ flex: 1, backgroundColor: T.card, borderRadius: 14, borderWidth: 1, borderColor: T.border, overflow: 'hidden' }} data-testid="sec-top-paths">
          <View style={{ padding: 14, borderBottomWidth: 1, borderBottomColor: T.border }}>
            <Text style={{ color: T.text, fontSize: 14, fontWeight: '700' }}>{tx('admin.securityIncidentDashboard.auto.text.006', 'Top Blocked Paths')}</Text>
          </View>
          <TableRow header T={T}>
            <HeaderCell flex={3} T={T}>Path</HeaderCell>
            <HeaderCell flex={1} align="center" T={T}>Code</HeaderCell>
            <HeaderCell flex={1} align="right" T={T}>Count</HeaderCell>
          </TableRow>
          {topPaths.length === 0 ? (
            <View style={{ padding: 24, alignItems: 'center' }}>
              <Text style={{ color: T.textMuted, fontSize: 12 }}>{tx('admin.securityIncidentDashboard.auto.text.007', 'No blocked paths in this period')}</Text>
            </View>
          ) : topPaths.slice(0, 10).map((p, i) => (
            <TableRow key={i} T={T}>
              <Cell flex={3} T={T}>{p.path.length > 40 ? p.path.slice(0, 40) + '...' : p.path}</Cell>
              <View style={{ flex: 1, alignItems: 'center' }}><CodeBadge code={p.code} T={T} /></View>
              <Cell flex={1} align="right" T={T}>{p.count}</Cell>
            </TableRow>
          ))}
        </View>

        {/* Top Offending IPs */}
        <View style={{ flex: 1, backgroundColor: T.card, borderRadius: 14, borderWidth: 1, borderColor: T.border, overflow: 'hidden' }} data-testid="sec-top-ips">
          <View style={{ padding: 14, borderBottomWidth: 1, borderBottomColor: T.border }}>
            <Text style={{ color: T.text, fontSize: 14, fontWeight: '700' }}>{tx('admin.securityIncidentDashboard.auto.text.008', 'Top Offending IPs')}</Text>
          </View>
          <TableRow header T={T}>
            <HeaderCell flex={2} T={T}>IP Address</HeaderCell>
            <HeaderCell flex={2} T={T}>Codes</HeaderCell>
            <HeaderCell flex={1} align="right" T={T}>Count</HeaderCell>
            <HeaderCell flex={1} align="right" T={T}>Last</HeaderCell>
          </TableRow>
          {topIps.length === 0 ? (
            <View style={{ padding: 24, alignItems: 'center' }}>
              <Text style={{ color: T.textMuted, fontSize: 12 }}>{tx('admin.securityIncidentDashboard.auto.text.009', 'No offending IPs in this period')}</Text>
            </View>
          ) : topIps.slice(0, 10).map((ip, i) => (
            <TableRow key={i} T={T}>
              <Cell flex={2} T={T}>{ip.ip}</Cell>
              <View style={{ flex: 2, flexDirection: 'row', flexWrap: 'wrap', gap: 3 }}>
                {ip.codes.map((c, j) => <CodeBadge key={j} code={c} T={T} />)}
              </View>
              <Cell flex={1} align="right" T={T}>{ip.count}</Cell>
              <Cell flex={1} align="right" T={T}>{timeAgo(ip.last_seen)}</Cell>
            </TableRow>
          ))}
        </View>
      </View>

      {/* Breakdown by Code */}
      {summary?.breakdown && summary.breakdown.length > 0 && (
        <View style={{ backgroundColor: T.card, borderRadius: 14, borderWidth: 1, borderColor: T.border, overflow: 'hidden' }} data-testid="sec-breakdown">
          <View style={{ padding: 14, borderBottomWidth: 1, borderBottomColor: T.border }}>
            <Text style={{ color: T.text, fontSize: 14, fontWeight: '700' }}>{tx('admin.securityIncidentDashboard.auto.text.010', 'Breakdown by Incident Code')}</Text>
          </View>
          <TableRow header T={T}>
            <HeaderCell flex={1} T={T}>Status</HeaderCell>
            <HeaderCell flex={2} T={T}>Code</HeaderCell>
            <HeaderCell flex={1} align="right" T={T}>Count</HeaderCell>
          </TableRow>
          {summary.breakdown.map((b, i) => (
            <TableRow key={i} T={T}>
              <Cell flex={1} T={T}>{b.status}</Cell>
              <View style={{ flex: 2 }}><CodeBadge code={b.code} T={T} /></View>
              <Cell flex={1} align="right" T={T}>{b.count}</Cell>
            </TableRow>
          ))}
        </View>
      )}
    </ScrollView>
  );
}
