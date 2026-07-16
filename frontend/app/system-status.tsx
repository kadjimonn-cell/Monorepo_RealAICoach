import React, { useEffect, useState, useCallback } from 'react';
import { View, Text, ScrollView, TouchableOpacity, useWindowDimensions} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { AnalyticsSkeleton, FadeSlideIn } from '../src/components/SkeletonLoaders';
import { useTheme } from '../src/context/ThemeContext';
import { useTranslation } from '../src/hooks/useTranslation';
import { resolveRuntimeBaseUrl } from '../src/utils/runtimeBaseUrl';
import { handleAppRecoverableError } from '../src/utils/appRecoverableError';

const API_BASE = resolveRuntimeBaseUrl();


function getBarColor(pct: number, palette: any): string {
  if (pct >= 99.95) return palette.successText;
  if (pct >= 99.5) return palette.successText;
  if (pct >= 99.0) return palette.warningText;
  if (pct >= 95.0) return palette.warning;
  return palette.error;
}

function UptimeChart({ days, darkMode, palette }: { days: any[]; darkMode: boolean; palette: any }) {
  const { width } = useWindowDimensions();
  const isMed = width >= 768;
  const [hoveredIdx, setHoveredIdx] = useState<number | null>(null);
  const barCount = days.length;
  const gap = isMed ? 2 : 1;
  const chartWidth = isMed ? width - 96 - 40 : width - 40 - 16;
  const barW = Math.max(2, Math.floor((chartWidth - gap * barCount) / barCount));
  const chartBg = darkMode ? palette.cardMuted || palette.surfaceElevated : palette.card;
  const chartBorder = palette.border;
  const labelPrimary = palette.textSec;
  const labelMuted = palette.textMuted;
  const tipBg = darkMode ? palette.surfaceHover || palette.border : palette.bgSoft;

  return (
    <View style={{ marginBottom: 32 }} data-testid="uptime-chart" testID="uptime-chart">
      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14 }}>
        <Text style={{ color: labelPrimary, fontSize: 11, fontWeight: '700', textTransform: 'uppercase', letterSpacing: 0.5 }}>
          90-Day Uptime
        </Text>
        {days.length > 0 && (
          <Text style={{ color: labelMuted, fontSize: 11 }}>
            {days[0]?.date} — {days[days.length - 1]?.date}
          </Text>
        )}
      </View>

      <View style={{
        backgroundColor: chartBg, borderRadius: 16, borderWidth: 1, borderColor: chartBorder,
        padding: isMed ? 20 : 12, overflow: 'hidden',
      }}>
        {/* Bars */}
        <View style={{ flexDirection: 'row', alignItems: 'flex-end', height: 48, gap }}>
          {days.map((d, i) => {
            const color = getBarColor(d.uptime_pct, palette);
            const isHovered = hoveredIdx === i;
            const h = d.uptime_pct >= 99.5 ? 48 : Math.max(8, (d.uptime_pct / 100) * 48);
            return (
              <TouchableOpacity
                key={d.date}
                data-testid={`uptime-bar-${d.date}`} testID={`uptime-bar-${d.date}`}
                onPress={() => setHoveredIdx(isHovered ? null : i)}
                activeOpacity={0.7}
                style={{
                  width: barW,
                  height: h,
                  backgroundColor: isHovered ? palette.surfaceElevated || palette.cardMuted : color,
                  borderRadius: 2,
                  opacity: isHovered ? 1 : 0.85,
                }}
              />
            );
          })}
        </View>

        {/* Tooltip */}
        {hoveredIdx !== null && days[hoveredIdx] && (
          <View style={{
            marginTop: 12, backgroundColor: tipBg, borderRadius: 10, padding: 12,
            flexDirection: 'row', alignItems: 'center', gap: 16,
          }}>
            <View>
              <Text style={{ color: palette.text, fontSize: 13, fontWeight: '700' }}>
                {new Date(days[hoveredIdx].date + 'T00:00:00').toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}
              </Text>
            </View>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
              <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: getBarColor(days[hoveredIdx].uptime_pct, palette) }} />
              <Text style={{ color: getBarColor(days[hoveredIdx].uptime_pct, palette), fontSize: 14, fontWeight: '800' }}>
                {days[hoveredIdx].uptime_pct}%
              </Text>
            </View>
            {days[hoveredIdx].incidents > 0 && (
              <Text style={{ color: palette.warningText, fontSize: 12 }}>
                {days[hoveredIdx].incidents} incident{days[hoveredIdx].incidents > 1 ? 's' : ''}
              </Text>
            )}
          </View>
        )}

        {/* Legend */}
        <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginTop: 10 }}>
          <Text style={{ color: labelMuted, fontSize: 10 }}>90 days ago</Text>
          <View style={{ flexDirection: 'row', gap: 12 }}>
            {[
              { color: palette.successText, label: '100%' },
              { color: palette.warningText, label: '99-99.5%' },
              { color: palette.error, label: '<99%' },
            ].map(l => (
              <View key={l.label} style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}>
                <View style={{ width: 8, height: 8, borderRadius: 2, backgroundColor: l.color }} />
                <Text style={{ color: labelMuted, fontSize: 10 }}>{l.label}</Text>
              </View>
            ))}
          </View>
          <Text style={{ color: labelMuted, fontSize: 10 }}>Today</Text>
        </View>
      </View>
    </View>
  );
}

function UptimeStats({ avgUptime, totalIncidents, periodDays, palette }: { avgUptime: number; totalIncidents: number; periodDays: number; palette: any }) {
  const cardBg = palette.card;
  return (
    <View style={{ flexDirection: 'row', gap: 12, marginBottom: 28 }} data-testid="uptime-stats" testID="uptime-stats">
      {[
        { label: 'Avg Uptime', value: `${avgUptime}%`, color: avgUptime >= 99.9 ? palette.successText : palette.warningText },
        { label: 'Incidents', value: `${totalIncidents}`, color: totalIncidents === 0 ? palette.successText : palette.warningText },
        { label: 'Period', value: `${periodDays} days`, color: palette.primary },
      ].map(s => (
        <View key={s.label} style={{
          flex: 1, backgroundColor: cardBg, borderRadius: 14, padding: 16,
          borderWidth: 1, borderColor: palette.border, alignItems: 'center',
        }}>
          <Text style={{ color: s.color, fontSize: 22, fontWeight: '800' }}>{s.value}</Text>
          <Text style={{ color: palette.textMuted, fontSize: 11, marginTop: 4, fontWeight: '600' }}>{s.label}</Text>
        </View>
      ))}
    </View>
  );
}

export default function StatusPage() {
  const { colors, darkMode } = useTheme();
  const { t } = useTranslation();
  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };

  // @autofix-moved: was module-level const STATUS_CONFIG
  const STATUS_CONFIG: Record<string, { label: string; color: string; icon: string }> = {
    operational: { label: 'Operational', color: colors.successText, icon: 'checkmark-circle' },
    degraded: { label: 'Degraded Performance', color: colors.warningText, icon: 'alert-circle' },
    partial_outage: { label: 'Partial Outage', color: colors.warningText, icon: 'warning' },
    major_outage: { label: 'Major Outage', color: colors.error, icon: 'close-circle' },
    maintenance: { label: 'Under Maintenance', color: colors.primary, icon: 'construct' },
  };
  // @autofix-moved: was module-level const SEVERITY_CONFIG
  const SEVERITY_CONFIG: Record<string, { color: string; icon: string }> = {
    minor: { color: colors.warningText, icon: 'alert-circle' },
    major: { color: colors.warningText, icon: 'warning' },
    critical: { color: colors.error, icon: 'close-circle' },
  };
  const { width } = useWindowDimensions();
  const isMed = width >= 768;
  const [data, setData] = useState<any>(null);
  const [uptimeData, setUptimeData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [recoverableError, setRecoverableError] = useState('');
  const pageBg = colors.bg;
  const headerBorder = colors.border;
  const panelBg = darkMode ? colors.cardMuted || colors.surfaceElevated : colors.card;
  const panelBorder = colors.border;
  const titleColor = colors.text;
  const subtitleColor = colors.textMuted;
  const labelColor = colors.textSec;
  const rowBorder = colors.border;
  const softSurface = darkMode ? colors.cardMuted || colors.surfaceElevated : colors.card;
  const softSurfaceAlt = darkMode ? colors.surfaceHover || colors.border : colors.bgSoft;

  const load = useCallback(async () => {
    try {
      const [statusRes, uptimeRes] = await Promise.all([
        fetch(`${API_BASE}/api/status/public`),
        fetch(`${API_BASE}/api/status/uptime-history?days=90`),
      ]);
      if (statusRes.ok) setData(await statusRes.json());
      if (uptimeRes.ok) setUptimeData(await uptimeRes.json());
      setRecoverableError('');
    } catch (error) {
      handleAppRecoverableError({
        scope: 'system-status.load',
        error,
        message: 'Unable to refresh system status right now.',
        setError: setRecoverableError,
        onRetry: () => { void load(); },
      
        notifyMode: 'dialog',
        userInitiated: true,
      });
    }
    setLoading(false);
  }, []);

  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    const interval = setInterval(load, 30000);
    return () => clearInterval(interval);
  }, [load]);

  const overall = data?.overall_status || 'operational';
  const overallCfg = STATUS_CONFIG[overall] || STATUS_CONFIG.operational;

  const formatTime = (ts: string) => {
    if (!ts) return '';
    const d = new Date(ts);
    const now = new Date();
    const diff = now.getTime() - d.getTime();
    const mins = Math.floor(diff / 60000);
    if (mins < 1) return 'Just now';
    if (mins < 60) return `${mins}m ago`;
    const hrs = Math.floor(mins / 60);
    if (hrs < 24) return `${hrs}h ago`;
    const days = Math.floor(hrs / 24);
    if (days < 30) return `${days}d ago`;
    return d.toLocaleDateString();
  };

  const formatDate = (ts: string) => {
    if (!ts) return '';
    return new Date(ts).toLocaleString();
  };

  return (
    <View style={{ flex: 1, backgroundColor: pageBg }}>
      <ScrollView contentContainerStyle={{ paddingBottom: 80 }} data-testid="status-page" testID="status-page">
        {/* Header */}
        <View style={{
          paddingTop: 48, paddingBottom: 36, paddingHorizontal: isMed ? 48 : 20,
          borderBottomWidth: 1, borderBottomColor: headerBorder,
        }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 8 }}>
            <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: colors.purple }} />
            <Text style={{ color: labelColor, fontSize: 12, fontWeight: '600', letterSpacing: 1, textTransform: 'uppercase' }}>{tx('autofix.batch9.realaicoach', 'RealAICoach')}</Text>
          </View>
          <Text style={{ color: titleColor, fontSize: 32, fontWeight: '800', letterSpacing: -0.5 }} data-testid="status-page-title" testID="status-page-title">
            {tx('autofix.batch9.system.status', 'System Status')}
          </Text>
          <Text style={{ color: subtitleColor, fontSize: 14, marginTop: 6 }}>
            {tx('autofix.batch9.real.time.operational.status.of.all.platform.services', 'Real-time operational status of all platform services')}
          </Text>
        </View>

        <View style={{ paddingHorizontal: isMed ? 48 : 20, paddingTop: 28 }}>
          {loading ? (
            <AnalyticsSkeleton />
          ) : (
            <FadeSlideIn>
              {/* Overall Status Banner */}
              <View style={{
                backgroundColor: (globalThis as any).__alphaColor(overallCfg.color, '10'),
                borderRadius: 16, padding: 24,
                borderWidth: 1, borderColor: (globalThis as any).__alphaColor(overallCfg.color, '30'),
                marginBottom: 28,
              }} data-testid="overall-status-banner" testID="overall-status-banner">
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 12 }}>
                  <View style={{
                    width: 48, height: 48, borderRadius: 14,
                    backgroundColor: (globalThis as any).__alphaColor(overallCfg.color, '20'),
                    alignItems: 'center', justifyContent: 'center',
                  }}>
                    <Ionicons name={overallCfg.icon as any} size={24} color={overallCfg.color} />
                  </View>
                  <View>
                    <Text style={{ color: overallCfg.color, fontSize: 20, fontWeight: '800' }}>{overallCfg.label}</Text>
                    <Text style={{ color: colors.textMuted, fontSize: 12, marginTop: 2 }}>
                      Updated {formatTime(data?.updated_at || '')} {data?.uptime_days ? `\u2022 ${data.uptime_days} days without major incident` : ''}
                    </Text>
                  </View>
                </View>
              </View>

              {/* Uptime Stats */}
              {uptimeData && (
                <UptimeStats
                  avgUptime={uptimeData.avg_uptime_pct}
                  totalIncidents={uptimeData.total_incidents}
                  periodDays={uptimeData.period_days}
                  palette={colors}
                />
              )}

              {data?.platform_control ? (
                <View
                  style={{
                    backgroundColor: panelBg,
                    borderRadius: 16,
                    borderWidth: 1,
                    borderColor: panelBorder,
                    padding: 20,
                    marginBottom: 26,
                    gap: 10,
                  }}
                  data-testid="status-page-platform-control-card"
                  testID="status-page-platform-control-card"
                >
                  <Text style={{ color: labelColor, fontSize: 11, fontWeight: '700', textTransform: 'uppercase', letterSpacing: 0.5 }}>
                    {tx('autofix.batch9.platform.control.center', 'Platform Control Center')}
                  </Text>
                  <Text style={{ color: titleColor, fontSize: 18, fontWeight: '800' }} data-testid="status-page-platform-control-mode" testID="status-page-platform-control-mode">
                    {String(data.platform_control.active_mode || data.platform_control.system_status || 'ONLINE').toUpperCase()}
                  </Text>
                  {!!data?.platform_control?.maintenance?.reason && (
                    <Text style={{ color: subtitleColor, fontSize: 12, lineHeight: 18 }} data-testid="status-page-platform-control-reason" testID="status-page-platform-control-reason">
                      {data.platform_control.maintenance.reason}
                    </Text>
                  )}
                  {!!data?.platform_control?.emergency_shutdown?.reason && (
                    <Text style={{ color: colors.error, fontSize: 12, lineHeight: 18 }} data-testid="status-page-platform-control-emergency-reason" testID="status-page-platform-control-emergency-reason">
                      {data.platform_control.emergency_shutdown.reason}
                    </Text>
                  )}
                  <Text style={{ color: subtitleColor, fontSize: 11 }} data-testid="status-page-platform-control-updated-at" testID="status-page-platform-control-updated-at">
                    {tx('autofix.batch9.last.control.update', 'Last control update:')} {formatDate(data?.platform_control?.updated_at || '') || '—'}
                  </Text>
                </View>
              ) : null}

              {/* Uptime Chart */}
              {uptimeData?.days?.length > 0 && (
                <UptimeChart days={uptimeData.days} darkMode={darkMode} palette={colors} />
              )}

              {/* Service List */}
              <View style={{ marginBottom: 32 }}>
                <Text style={{ color: labelColor, fontSize: 11, fontWeight: '700', textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 14 }}>{tx('autofix.batch9.services', 'Services')}</Text>
                <View style={{ backgroundColor: panelBg, borderRadius: 16, borderWidth: 1, borderColor: panelBorder, overflow: 'hidden' }}>
                  {(data?.services || []).map((svc: any, i: number) => {
                    const cfg = STATUS_CONFIG[svc.status] || STATUS_CONFIG.operational;
                    return (
                      <View key={svc.key} data-testid={`service-${svc.key}`} testID={`service-${svc.key}`}
                        style={{
                          flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
                          paddingHorizontal: 20, paddingVertical: 16,
                          borderBottomWidth: i < (data?.services?.length || 0) - 1 ? 1 : 0,
                          borderBottomColor: rowBorder,
                        }}>
                        <View style={{ flex: 1 }}>
                          <Text style={{ color: titleColor, fontSize: 14, fontWeight: '600' }}>{svc.name}</Text>
                          <Text style={{ color: subtitleColor, fontSize: 11, marginTop: 2 }}>{svc.description}</Text>
                          {svc.message ? <Text style={{ color: cfg.color, fontSize: 11, marginTop: 4 }}>{svc.message}</Text> : null}
                        </View>
                        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: (globalThis as any).__alphaColor(cfg.color, '12'), paddingHorizontal: 12, paddingVertical: 6, borderRadius: 8 }}>
                          <View style={{ width: 7, height: 7, borderRadius: 4, backgroundColor: cfg.color }} />
                          <Text style={{ color: cfg.color, fontSize: 11, fontWeight: '700' }}>{cfg.label}</Text>
                        </View>
                      </View>
                    );
                  })}
                </View>
              </View>

              {/* Scheduled Maintenance */}
              {(data?.maintenance || []).length > 0 && (
                <View style={{ marginBottom: 32 }}>
                  <Text style={{ color: labelColor, fontSize: 11, fontWeight: '700', textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 14 }}>{tx('autofix.batch9.scheduled.maintenance', 'Scheduled Maintenance')}</Text>
                  {data.maintenance.map((m: any) => (
                    <View key={m.maintenance_id} data-testid={`maintenance-${m.maintenance_id}`} testID={`maintenance-${m.maintenance_id}`}
                      style={{ backgroundColor: softSurface, borderRadius: 14, padding: 20, marginBottom: 10, borderWidth: 1, borderColor: colors.primarySoft }}>
                      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 8 }}>
                        <Ionicons name="construct" size={16} color={colors.primary} />
                        <Text style={{ color: titleColor, fontSize: 14, fontWeight: '700' }}>{m.title}</Text>
                      </View>
                      <Text style={{ color: labelColor, fontSize: 12, lineHeight: 18 }}>{m.message}</Text>
                      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginTop: 10 }}>
                        <Ionicons name="time-outline" size={13} color={subtitleColor} />
                        <Text style={{ color: subtitleColor, fontSize: 11 }}>
                          {formatDate(m.scheduled_start)} — {formatDate(m.scheduled_end)}
                        </Text>
                      </View>
                      {m.affected_services?.length > 0 && (
                        <View style={{ flexDirection: 'row', gap: 4, marginTop: 8, flexWrap: 'wrap' }}>
                          {m.affected_services.map((s: string) => (
                            <View key={s} style={{ backgroundColor: softSurfaceAlt, paddingHorizontal: 8, paddingVertical: 3, borderRadius: 5 }}>
                              <Text style={{ color: labelColor, fontSize: 10, fontWeight: '600' }}>{s}</Text>
                            </View>
                          ))}
                        </View>
                      )}
                    </View>
                  ))}
                </View>
              )}

              {/* Recent Incidents */}
              <View style={{ marginBottom: 32 }}>
                <Text style={{ color: labelColor, fontSize: 11, fontWeight: '700', textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 14 }}>Recent Incidents</Text>
                {(data?.incidents || []).length === 0 ? (
                  <View style={{ backgroundColor: softSurface, borderRadius: 14, padding: 32, alignItems: 'center', borderWidth: 1, borderColor: panelBorder }}>
                    <Ionicons name="shield-checkmark" size={32} color={colors.successText} />
                    <Text style={{ color: titleColor, fontSize: 15, fontWeight: '700', marginTop: 12 }}>No recent incidents</Text>
                    <Text style={{ color: subtitleColor, fontSize: 12, marginTop: 4 }}>All systems have been operating normally</Text>
                  </View>
                ) : (
                  data.incidents.map((inc: any) => {
                    const sevCfg = SEVERITY_CONFIG[inc.severity] || SEVERITY_CONFIG.minor;
                    const isResolved = inc.status === 'resolved';
                    return (
                      <View key={inc.incident_id} data-testid={`incident-${inc.incident_id}`} testID={`incident-${inc.incident_id}`}
                        style={{
                          backgroundColor: softSurface, borderRadius: 14, padding: 20, marginBottom: 10,
                          borderWidth: 1, borderColor: (globalThis as any).__alphaColor(isResolved ? panelBorder : sevCfg.color, '25'),
                        }}>
                        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 8 }}>
                          <View style={{ width: 24, height: 24, borderRadius: 7, backgroundColor: (globalThis as any).__alphaColor((isResolved ? colors.success : sevCfg.color), '15'), alignItems: 'center', justifyContent: 'center' }}>
                            <Ionicons name={(isResolved ? 'checkmark-circle' : sevCfg.icon) as any} size={14} color={isResolved ? colors.success : sevCfg.color} />
                          </View>
                          <Text style={{ color: titleColor, fontSize: 14, fontWeight: '700', flex: 1 }}>{inc.title}</Text>
                          <View style={{ backgroundColor: (globalThis as any).__alphaColor((isResolved ? colors.success : sevCfg.color), '12'), paddingHorizontal: 10, paddingVertical: 4, borderRadius: 6 }}>
                            <Text style={{ color: isResolved ? colors.success : sevCfg.color, fontSize: 10, fontWeight: '800' }}>
                              {isResolved ? 'RESOLVED' : inc.status?.toUpperCase()}
                            </Text>
                          </View>
                        </View>
                        {(inc.updates || []).map((upd: any, j: number) => (
                          <View key={j} style={{ flexDirection: 'row', gap: 10, marginTop: 10, paddingLeft: 4 }}>
                            <View style={{ width: 2, backgroundColor: panelBorder, marginTop: 6 }} />
                            <View style={{ flex: 1 }}>
                              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                                <Text style={{ color: subtitleColor, fontSize: 10, fontWeight: '600', textTransform: 'uppercase' }}>{upd.status}</Text>
                                <Text style={{ color: subtitleColor, fontSize: 10 }}>{formatTime(upd.timestamp)}</Text>
                              </View>
                              <Text style={{ color: labelColor, fontSize: 12, marginTop: 3, lineHeight: 18 }}>{upd.message}</Text>
                            </View>
                          </View>
                        ))}
                        {inc.affected_services?.length > 0 && (
                          <View style={{ flexDirection: 'row', gap: 4, marginTop: 12, flexWrap: 'wrap' }}>
                            {inc.affected_services.map((s: string) => (
                              <View key={s} style={{ backgroundColor: softSurfaceAlt, paddingHorizontal: 8, paddingVertical: 3, borderRadius: 5 }}>
                                <Text style={{ color: labelColor, fontSize: 10, fontWeight: '600' }}>{s}</Text>
                              </View>
                            ))}
                          </View>
                        )}
                      </View>
                    );
                  })
                )}
              </View>
            </FadeSlideIn>
          )}
        </View>
        {recoverableError ? (
          <View
            style={{
              marginHorizontal: isMed ? 20 : 12,
              marginTop: 12,
              marginBottom: 8,
              paddingHorizontal: 12,
              paddingVertical: 10,
              borderRadius: 10,
              borderWidth: 1,
              borderColor: colors.error + '35',
              backgroundColor: colors.errorSoft,
              flexDirection: 'row',
              alignItems: 'center',
              justifyContent: 'space-between',
              gap: 10,
            }}
            data-testid="system-status-recoverable-error-banner"
            testID="system-status-recoverable-error-banner"
          >
            <Text
              style={{ color: colors.errorText, fontSize: 12, fontWeight: '700', flex: 1 }}
              data-testid="system-status-recoverable-error-text"
              testID="system-status-recoverable-error-text"
            >
              {recoverableError}
            </Text>
            <TouchableOpacity
              onPress={() => { void load(); }}
              style={{ backgroundColor: colors.error, borderRadius: 8, paddingHorizontal: 10, paddingVertical: 8 }}
              data-testid="system-status-recoverable-error-retry"
              testID="system-status-recoverable-error-retry"
            >
              <Text style={{ color: colors.primaryText, fontSize: 11, fontWeight: '800' }}>{tx('common.retry', 'Retry')}</Text>
            </TouchableOpacity>
          </View>
        ) : null}

        {/* Footer */}
        <View style={{ paddingHorizontal: isMed ? 48 : 20, paddingTop: 20, paddingBottom: 40, borderTopWidth: 1, borderTopColor: headerBorder }}>
          <Text style={{ color: subtitleColor, fontSize: 11, textAlign: 'center' }}>
            Powered by RealAICoach — Auto-refreshes every 30 seconds
          </Text>
        </View>
      </ScrollView>
    </View>
  );
}
