import React, { useCallback, useEffect, useState } from 'react';
import { View, Text, TouchableOpacity, ScrollView, TextInput } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import api from '../../services/api';
import { useAutoRefresh } from '../../hooks/useAutoRefresh';

import { useAdminTheme } from '../../hooks/useAdminTheme';
import { useTranslation } from '../../hooks/useTranslation';
import { useTheme } from '../../context/ThemeContext';
const AC_FALLBACK = {
  bg: 'var(--app-bg)', bgAlt: 'var(--app-bg)', card: 'var(--app-card-bg)', surface: 'var(--app-card-bg)', surfaceHover: 'var(--app-surface-hover)', border: 'var(--app-border)', borderStrong: 'var(--app-border-strong)',
  text: 'var(--app-text)', textSec: 'var(--app-text-sec)', textMuted: 'var(--app-text-muted)', textDim: 'var(--app-text-muted)',
  primary: 'var(--app-primary)', success: 'var(--app-success)', warning: 'var(--app-warning)', error: 'var(--app-error)',
};
const statusColor = (status: string) => {
  if (status === 'healthy') return 'var(--app-success)';
  if (status === 'warning') return 'var(--app-warning)';
  if (status === 'critical') return 'var(--app-error)';
  return AC_FALLBACK.textDim;
};

const tx = (_key: string, fallback: string) => fallback;

const num = (value: any) => {
  const n = Number(value);
  return Number.isFinite(n) ? n.toLocaleString() : '0';
};

export default function AuthComplianceDashboardPanel({ colors, darkMode: darkModeProp }: { colors: any; darkMode?: boolean }) {
  const { t } = useTranslation();
  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };


  const _AC = useAdminTheme();
  const { darkMode: themeDark } = useTheme();
  const _darkMode = darkModeProp ?? themeDark;
  // Theme-driven palette — resolves both light and dark modes via `colors.*`
  // (from useTheme). No more hardcoded dark hex — if a token is missing the
  // fallback uses another theme token, never a raw hex.
  const C = {
    bg: colors.bg,
    card: colors.card,
    border: colors.border,
    text: colors.text,
    muted: colors.textMuted,
    surface: colors.surface,
    surfaceAlt: colors.surfaceHover,
    borderSoft: colors.borderSoft || colors.border,
    textSoft: colors.textSec,
    inputBg: colors.surface,
    actionBg: colors.primary,
    actionText: colors.primaryText || colors.text,
    neutralButtonBg: colors.surfaceHover,
    neutralButtonText: colors.text,
    dangerBg: colors.errorSoft,
    dangerBorder: colors.errorSoft,
    dangerText: colors.errorText || colors.error,
    warningBg: colors.warningSoft,
    warningBorder: colors.warningSoft,
    warningText: colors.warningText || colors.warning,
    warningSubText: colors.warningText || colors.warning,
  };

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [data, setData] = useState<any>(null);
  const [timeRangeInput, setTimeRangeInput] = useState('24h');
  const [routePrefixInput, setRoutePrefixInput] = useState('');
  const [countryInput, setCountryInput] = useState('');
  const [fingerprintInput, setFingerprintInput] = useState('');
  const [appliedFilters, setAppliedFilters] = useState({
    time_range: '24h',
    route_prefix: '',
    country: '',
    fingerprint: '',
  });

  const TIME_RANGE_OPTIONS = ['1h', '24h', '7d', '30d'];

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setError('');
      const response = await api.get('/auth-compliance/admin/overview', {
        params: {
          time_range: appliedFilters.time_range,
          route_prefix: appliedFilters.route_prefix || undefined,
          country: appliedFilters.country || undefined,
          fingerprint: appliedFilters.fingerprint || undefined,
        },
      });
      setData(response.data || null);
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Unable to load auth compliance metrics.');
    } finally {
      setLoading(false);
    }
  }, [appliedFilters]);

  useEffect(() => {
    load();
  }, [load]);

  useAutoRefresh(load, { intervalMs: 20000 });

  const overview = data?.overview || {};
  const filteredOverview = data?.filtered_overview || {};
  const applied = data?.applied_filters || appliedFilters;
  const topRoutes = data?.top_blocked_routes || [];
  const geoSummary = data?.geo_summary || [];
  const spikes = data?.suspicious_spikes || [];
  const latestEvents = data?.latest_events || [];
  const complianceStatus = String(data?.status || 'unknown');

  const applyFilters = () => {
    setAppliedFilters({
      time_range: TIME_RANGE_OPTIONS.includes(timeRangeInput) ? timeRangeInput : '24h',
      route_prefix: routePrefixInput.trim(),
      country: countryInput.trim().toUpperCase(),
      fingerprint: fingerprintInput.trim().toLowerCase(),
    });
  };

  const clearFilters = () => {
    setTimeRangeInput('24h');
    setRoutePrefixInput('');
    setCountryInput('');
    setFingerprintInput('');
    setAppliedFilters({ time_range: '24h', route_prefix: '', country: '', fingerprint: '' });
  };

  return (
    <View style={{ flex: 1, padding: 16 }} data-testid="admin-auth-compliance-dashboard-panel" testID="admin-auth-compliance-dashboard-panel">
      <View style={{ backgroundColor: C.surface, borderWidth: 1, borderColor: C.borderSoft, borderRadius: 12, padding: 14 }}>
        <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
          <View>
            <Text style={{ color: C.text, fontSize: 17, fontWeight: '900' }} data-testid="admin-auth-compliance-title" testID="admin-auth-compliance-title">{tx('admin.authComplianceDashboardPanel.auto.text.001', 'Auth Compliance Dashboard')}</Text>
            <Text style={{ color: C.muted, fontSize: 11, marginTop: 2 }} data-testid="admin-auth-compliance-subtitle" testID="admin-auth-compliance-subtitle">{tx('admin.authComplianceDashboardPanel.auto.text.002', 'Real-time unauthorized route block telemetry and anomaly indicators.')}</Text>
          </View>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
            <View style={{ backgroundColor: `${statusColor(complianceStatus)}22`, borderRadius: 999, borderWidth: 1, borderColor: `${statusColor(complianceStatus)}66`, paddingHorizontal: 10, paddingVertical: 5 }} data-testid="admin-auth-compliance-status-pill" testID="admin-auth-compliance-status-pill">
              <Text style={{ color: statusColor(complianceStatus), fontSize: 10, fontWeight: '800' }} data-testid="admin-auth-compliance-status-pill-value" testID="admin-auth-compliance-status-pill-value">{complianceStatus.toUpperCase()}</Text>
            </View>
            <TouchableOpacity onPress={load} style={{ backgroundColor: C.actionBg, borderRadius: 8, paddingHorizontal: 10, paddingVertical: 6 }} data-testid="admin-auth-compliance-refresh-button" testID="admin-auth-compliance-refresh-button">
              <Text style={{ color: C.actionText, fontSize: 11, fontWeight: '700' }}>{tx('admin.authComplianceDashboardPanel.auto.text.003', 'Refresh')}</Text>
            </TouchableOpacity>
          </View>
        </View>

        {error ? (
          <View style={{ marginTop: 10, borderWidth: 1, borderColor: C.dangerBorder, backgroundColor: C.dangerBg, borderRadius: 10, padding: 10 }} data-testid="admin-auth-compliance-error-banner" testID="admin-auth-compliance-error-banner">
            <Text style={{ color: C.dangerText, fontSize: 11, fontWeight: '700' }} data-testid="admin-auth-compliance-error-text" testID="admin-auth-compliance-error-text">{error}</Text>
          </View>
        ) : null}

        {loading ? (
          <Text style={{ marginTop: 10, color: C.muted, fontSize: 12 }} data-testid="admin-auth-compliance-loading-text" testID="admin-auth-compliance-loading-text">{tx('admin.authComplianceDashboardPanel.auto.text.004', 'Loading auth telemetry...')}</Text>
        ) : null}

        <View style={{ marginTop: 10, borderWidth: 1, borderColor: C.borderSoft, borderRadius: 10, backgroundColor: C.surfaceAlt, padding: 10 }} data-testid="admin-auth-compliance-filters-panel" testID="admin-auth-compliance-filters-panel">
          <Text style={{ color: C.text, fontSize: 12, fontWeight: '800' }} data-testid="admin-auth-compliance-filters-title" testID="admin-auth-compliance-filters-title">{tx('admin.authComplianceDashboardPanel.auto.text.005', 'Forensics Drill-down Filters')}</Text>

          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 8 }} data-testid="admin-auth-compliance-time-range-options" testID="admin-auth-compliance-time-range-options">
            {TIME_RANGE_OPTIONS.map((option) => (
              <TouchableOpacity accessibilityLabel={tx('admin.authComplianceDashboardPanel.auto.accessibility.001', 'Select auth compliance time range')}
                key={option}
                onPress={() => setTimeRangeInput(option)}
                style={{
                  borderRadius: 999,
                  borderWidth: 1,
                  borderColor: timeRangeInput === option ? C.actionBg : C.border,
                  backgroundColor: timeRangeInput === option ? C.actionBg : C.inputBg,
                  paddingHorizontal: 10,
                  paddingVertical: 5,
                }}
                data-testid={`admin-auth-compliance-time-range-${option}`} testID={`admin-auth-compliance-time-range-${option}`}
              >
                <Text style={{ color: timeRangeInput === option ? C.actionText : C.textSoft, fontSize: 10, fontWeight: '800' }}>{option.toUpperCase()}</Text>
              </TouchableOpacity>
            ))}
          </View>

          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 8 }}>
            <TextInput
              value={routePrefixInput}
              onChangeText={setRoutePrefixInput}
              placeholder={tx('admin.authComplianceDashboardPanel.auto.placeholder.001', 'Route prefix (e.g. /admin)')}
              placeholderTextColor={C.muted}
              style={{ flex: 1, minWidth: 220, borderWidth: 1, borderColor: C.border, borderRadius: 8, backgroundColor: C.inputBg, color: C.text, paddingHorizontal: 10, paddingVertical: 8, fontSize: 11 }}
              data-testid="admin-auth-compliance-filter-route-prefix" testID="admin-auth-compliance-filter-route-prefix"
            />
            <TextInput
              value={countryInput}
              onChangeText={setCountryInput}
              placeholder={tx('admin.authComplianceDashboardPanel.auto.placeholder.002', 'Country (e.g. US)')}
              placeholderTextColor={C.muted}
              style={{ width: 150, borderWidth: 1, borderColor: C.border, borderRadius: 8, backgroundColor: C.inputBg, color: C.text, paddingHorizontal: 10, paddingVertical: 8, fontSize: 11 }}
              data-testid="admin-auth-compliance-filter-country" testID="admin-auth-compliance-filter-country"
            />
            <TextInput
              value={fingerprintInput}
              onChangeText={setFingerprintInput}
              placeholder={tx('admin.authComplianceDashboardPanel.auto.placeholder.003', 'Fingerprint prefix')}
              placeholderTextColor={C.muted}
              style={{ flex: 1, minWidth: 220, borderWidth: 1, borderColor: C.border, borderRadius: 8, backgroundColor: C.inputBg, color: C.text, paddingHorizontal: 10, paddingVertical: 8, fontSize: 11 }}
              data-testid="admin-auth-compliance-filter-fingerprint" testID="admin-auth-compliance-filter-fingerprint"
            />
          </View>

          <View style={{ marginTop: 8, flexDirection: 'row', gap: 8 }}>
            <TouchableOpacity onPress={applyFilters} style={{ backgroundColor: C.actionBg, borderRadius: 8, paddingHorizontal: 12, paddingVertical: 7 }} data-testid="admin-auth-compliance-apply-filters-button" testID="admin-auth-compliance-apply-filters-button">
              <Text style={{ color: C.actionText, fontSize: 10, fontWeight: '800' }}>{tx('admin.authComplianceDashboardPanel.auto.text.006', 'Apply filters')}</Text>
            </TouchableOpacity>
            <TouchableOpacity onPress={clearFilters} style={{ backgroundColor: C.neutralButtonBg, borderRadius: 8, paddingHorizontal: 12, paddingVertical: 7 }} data-testid="admin-auth-compliance-clear-filters-button" testID="admin-auth-compliance-clear-filters-button">
              <Text style={{ color: C.neutralButtonText, fontSize: 10, fontWeight: '800' }}>{tx('admin.authComplianceDashboardPanel.auto.text.007', 'Clear')}</Text>
            </TouchableOpacity>
          </View>
        </View>

        {!loading && !error ? (
          <ScrollView style={{ marginTop: 10 }} contentContainerStyle={{ paddingBottom: 24 }} data-testid="admin-auth-compliance-content-scroll" testID="admin-auth-compliance-content-scroll">
            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10 }} data-testid="admin-auth-compliance-kpi-cards" testID="admin-auth-compliance-kpi-cards">
              {[
                { key: 'filtered-blocks', label: `Unauthorized blocks (${String(applied.time_range || '24h').toUpperCase()})`, value: num(filteredOverview.unauthorized_route_blocks), icon: 'shield' },
                { key: 'filtered-fingerprints', label: `Unique fingerprints (${String(applied.time_range || '24h').toUpperCase()})`, value: num(filteredOverview.unique_fingerprints), icon: 'finger-print' },
                { key: 'filtered-spikes', label: 'Suspicious spikes (1h)', value: num(filteredOverview.suspicious_retry_spikes_1h), icon: 'warning' },
                { key: 'global-24h', label: 'Global blocks (24h)', value: num(overview.unauthorized_route_blocks_24h), icon: 'shield-checkmark' },
              ].map((metric) => (
                <View key={metric.key} style={{ flex: 1, minWidth: 190, backgroundColor: C.surfaceAlt, borderWidth: 1, borderColor: C.borderSoft, borderRadius: 10, padding: 10 }} data-testid={`admin-auth-compliance-kpi-${metric.key}`} testID={`admin-auth-compliance-kpi-${metric.key}`}>
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                    <Ionicons name={metric.icon as any} size={13} color={C.textSoft} />
                    <Text style={{ color: C.muted, fontSize: 10, fontWeight: '800', textTransform: 'uppercase' }}>{metric.label}</Text>
                  </View>
                  <Text style={{ color: C.text, marginTop: 5, fontSize: 23, fontWeight: '900' }} data-testid={`admin-auth-compliance-kpi-${metric.key}-value`} testID={`admin-auth-compliance-kpi-${metric.key}-value`}>{metric.value}</Text>
                </View>
              ))}
            </View>

            <View style={{ marginTop: 10, flexDirection: 'row', flexWrap: 'wrap', gap: 10 }}>
              <View style={{ flex: 1, minWidth: 280, borderWidth: 1, borderColor: C.borderSoft, borderRadius: 10, backgroundColor: C.surface, padding: 10 }} data-testid="admin-auth-compliance-top-routes-section" testID="admin-auth-compliance-top-routes-section">
                <Text style={{ color: C.text, fontSize: 12, fontWeight: '800' }} data-testid="admin-auth-compliance-top-routes-title" testID="admin-auth-compliance-top-routes-title">Top Blocked Routes ({String(applied.time_range || '24h').toUpperCase()})</Text>
                {topRoutes.length === 0 ? <Text style={{ color: C.muted, marginTop: 7, fontSize: 11 }}>{tx('admin.authComplianceDashboardPanel.auto.text.008', 'No blocked route data yet.')}</Text> : null}
                {topRoutes.map((route: any, idx: number) => (
                  <View key={`${route.path}-${idx}`} style={{ marginTop: 7, backgroundColor: C.surfaceAlt, borderWidth: 1, borderColor: C.borderSoft, borderRadius: 8, padding: 8 }} data-testid={`admin-auth-compliance-top-route-${idx}`} testID={`admin-auth-compliance-top-route-${idx}`}>
                    <Text style={{ color: C.text, fontSize: 11, fontWeight: '700' }} numberOfLines={1}>{route.path}</Text>
                    <Text style={{ color: C.muted, marginTop: 2, fontSize: 10 }}>Hits {num(route.hits)}</Text>
                  </View>
                ))}
              </View>

              <View style={{ flex: 1, minWidth: 280, borderWidth: 1, borderColor: C.borderSoft, borderRadius: 10, backgroundColor: C.surface, padding: 10 }} data-testid="admin-auth-compliance-geo-summary-section" testID="admin-auth-compliance-geo-summary-section">
                <Text style={{ color: C.text, fontSize: 12, fontWeight: '800' }} data-testid="admin-auth-compliance-geo-summary-title" testID="admin-auth-compliance-geo-summary-title">Geo Summary ({String(applied.time_range || '24h').toUpperCase()})</Text>
                {geoSummary.length === 0 ? <Text style={{ color: C.muted, marginTop: 7, fontSize: 11 }}>{tx('admin.authComplianceDashboardPanel.auto.text.009', 'No geo telemetry yet.')}</Text> : null}
                {geoSummary.map((row: any, idx: number) => (
                  <View key={`${row.country_code}-${idx}`} style={{ marginTop: 7, flexDirection: 'row', justifyContent: 'space-between', backgroundColor: C.surfaceAlt, borderWidth: 1, borderColor: C.borderSoft, borderRadius: 8, padding: 8 }} data-testid={`admin-auth-compliance-geo-row-${idx}`} testID={`admin-auth-compliance-geo-row-${idx}`}>
                    <Text style={{ color: C.text, fontSize: 11, fontWeight: '700' }}>{row.country_code}</Text>
                    <Text style={{ color: C.muted, fontSize: 11, fontWeight: '700' }}>{num(row.hits)}</Text>
                  </View>
                ))}
              </View>
            </View>

            <View style={{ marginTop: 10, borderWidth: 1, borderColor: C.borderSoft, borderRadius: 10, backgroundColor: C.surface, padding: 10 }} data-testid="admin-auth-compliance-spikes-section" testID="admin-auth-compliance-spikes-section">
              <Text style={{ color: C.text, fontSize: 12, fontWeight: '800' }} data-testid="admin-auth-compliance-spikes-title" testID="admin-auth-compliance-spikes-title">{tx('admin.authComplianceDashboardPanel.auto.text.010', 'Suspicious Retry Spikes (1h · filtered)')}</Text>
              {spikes.length === 0 ? <Text style={{ color: C.muted, marginTop: 7, fontSize: 11 }}>{tx('admin.authComplianceDashboardPanel.auto.text.011', 'No suspicious spikes detected.')}</Text> : null}
              {spikes.map((spike: any, idx: number) => (
                <View key={`${spike.fingerprint_hash}-${idx}`} style={{ marginTop: 7, backgroundColor: C.warningBg, borderWidth: 1, borderColor: C.warningBorder, borderRadius: 8, padding: 8 }} data-testid={`admin-auth-compliance-spike-row-${idx}`} testID={`admin-auth-compliance-spike-row-${idx}`}>
                  <Text style={{ color: C.warningText, fontSize: 11, fontWeight: '700' }}>{spike.sample_path}</Text>
                  <Text style={{ color: C.warningSubText, marginTop: 2, fontSize: 10 }}>Hits {num(spike.hits)} · {spike.country_code} · fp {String(spike.fingerprint_hash || '').slice(0, 12)}...</Text>
                </View>
              ))}
            </View>

            <View style={{ marginTop: 10, borderWidth: 1, borderColor: C.borderSoft, borderRadius: 10, backgroundColor: C.surface, padding: 10 }} data-testid="admin-auth-compliance-latest-events-section" testID="admin-auth-compliance-latest-events-section">
              <Text style={{ color: C.text, fontSize: 12, fontWeight: '800' }} data-testid="admin-auth-compliance-latest-events-title" testID="admin-auth-compliance-latest-events-title">{tx('admin.authComplianceDashboardPanel.auto.text.012', 'Latest Block Events')}</Text>
              {latestEvents.length === 0 ? <Text style={{ color: C.muted, marginTop: 7, fontSize: 11 }}>{tx('admin.authComplianceDashboardPanel.auto.text.013', 'No recent events yet.')}</Text> : null}
              {latestEvents.slice(0, 8).map((event: any, idx: number) => (
                <View key={`${event.event_id}-${idx}`} style={{ marginTop: 7, backgroundColor: C.surfaceAlt, borderWidth: 1, borderColor: C.borderSoft, borderRadius: 8, padding: 8 }} data-testid={`admin-auth-compliance-event-row-${idx}`} testID={`admin-auth-compliance-event-row-${idx}`}>
                  <Text style={{ color: C.text, fontSize: 11, fontWeight: '700' }}>{event.path}</Text>
                  <Text style={{ color: C.muted, marginTop: 2, fontSize: 10 }}>Hits {num(event.hits)} · {event.reason} · {event.country_code} · {event.last_seen_at}</Text>
                </View>
              ))}
            </View>
          </ScrollView>
        ) : null}
      </View>
    </View>
  );
}
