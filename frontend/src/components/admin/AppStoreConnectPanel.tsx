import React, { useState, useCallback } from 'react';
import { View, Text, ScrollView, ActivityIndicator, TouchableOpacity } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import AutoFixBanner from './AutoFixBanner';
import { useTheme } from '../../context/ThemeContext';
import { getAdminColors } from '../../hooks/useAdminTheme';
import { useTranslation } from '../../hooks/useTranslation';
import { useHybridPolling } from '../../hooks/useHybridPolling';

const getPalette = (darkMode: boolean) => {
  const AC = getAdminColors(darkMode);
  return {
    bg: AC.bg,
    card: AC.card,
    border: AC.border,
    text: AC.text,
    textSec: AC.textSec,
    textMuted: AC.textMuted,
    primary: AC.primary,
    success: AC.success,
    warning: AC.warning,
    error: AC.error,
    purple: AC.purple,
    purpleText: AC.purpleText,
    cyan: AC.info,
    apple: AC.textSec,
    warningText: AC.warningText,
    successSoft: AC.successSoft,
    errorSoft: AC.errorSoft,
    successBorder: AC.success,
    errorBorder: AC.error,
  };
};

type Tab = 'dashboard' | 'apps' | 'sales';

export default function AppStoreConnectPanel({ colors }: { colors: any }) {
  const { darkMode } = useTheme();
  const { t } = useTranslation();
  const tx = React.useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);
  const T = React.useMemo(() => getPalette(darkMode), [darkMode]);
  const [tab, setTab] = useState<Tab>('dashboard');
  const [loading, setLoading] = useState(true);
  const [dashboard, setDashboard] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const fetchDashboard = useCallback(async (silent = false) => {
    if (!silent) setLoading(true);
    else setRefreshing(true);
    try {
      const res = await api.get('/admin/appstore/dashboard');
      setDashboard(res.data);
      setError(null);
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Failed to connect to App Store Connect');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useHybridPolling({
    enabled: true,
    errorScope: 'admin/app-store-connect/hybrid-refresh',
    onTick: fetchDashboard,
    runOnMount: true,
    slowIntervalMs: 45000,
    fastIntervalMs: 15000,
  });

  if (loading) return (
    <View style={{ padding: 40, alignItems: 'center' }} data-testid="appstore-loading" testID="appstore-loading">
      <AutoFixBanner domain="appstore" />
      <ActivityIndicator size="large" color={T.primary} />
      <Text style={{ color: T.textSec, marginTop: 12, fontSize: 14 }}>{tx('admin.appStoreConnectPanel.states.connecting', 'Connecting to App Store Connect...')}</Text>
    </View>
  );

  const conn = dashboard?.connection;
  const apps = dashboard?.apps || [];
  const sales = dashboard?.recent_sales || [];

  const TABS: { id: Tab; label: string; icon: string }[] = [
    { id: 'dashboard', label: 'Overview', icon: 'grid' },
    { id: 'apps', label: `Apps (${apps.length})`, icon: 'apps' },
    { id: 'sales', label: 'Sales', icon: 'cash' },
  ];

  return (
    <ScrollView style={{ flex: 1 }} data-testid="appstore-connect-panel" testID="appstore-connect-panel">
      {/* Header */}
      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 20 }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
          <View style={{ width: 40, height: 40, borderRadius: 10, backgroundColor: T.bg, alignItems: 'center', justifyContent: 'center' }}>
            <Ionicons name="logo-apple" size={22} color="var(--app-primary)" />
          </View>
          <View>
            <Text style={{ color: T.text, fontSize: 18, fontWeight: '700' }}>{tx('admin.appStoreConnectPanel.header.title', 'App Store Connect')}</Text>
            <Text style={{ color: T.textSec, fontSize: 12 }}>{tx('admin.appStoreConnectPanel.header.subtitle', 'Real-time Apple Developer Data')}</Text>
          </View>
        </View>
        <TouchableOpacity
          data-testid="appstore-refresh-btn" testID="appstore-refresh-btn"
          onPress={() => fetchDashboard(true)}
          style={{ flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: T.card, borderRadius: 8, paddingHorizontal: 12, paddingVertical: 6, borderWidth: 1, borderColor: T.border }}
        >
          {refreshing ? <ActivityIndicator size="small" color={T.primary} /> : <Ionicons name="refresh" size={14} color={T.primary} />}
          <Text style={{ color: T.primary, fontSize: 12, fontWeight: '600' }}>{tx('admin.appStoreConnectPanel.actions.refresh', 'Refresh')}</Text>
        </TouchableOpacity>
      </View>

      {/* Connection Status */}
      <View data-testid="appstore-connection-status" testID="appstore-connection-status" style={{ backgroundColor: conn?.connected ? T.successSoft : T.errorSoft, borderRadius: 10, padding: 14, marginBottom: 16, borderWidth: 1, borderColor: conn?.connected ? T.successBorder : T.errorBorder }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
          <View style={{ width: 10, height: 10, borderRadius: 5, backgroundColor: conn?.connected ? T.success : T.error }} />
          <Text style={{ color: conn?.connected ? T.success : T.error, fontWeight: '600', fontSize: 14 }}>
            {conn?.connected ? 'Connected to App Store Connect' : 'Connection Failed'}
          </Text>
        </View>
        {conn?.connected && (
          <Text style={{ color: T.textMuted, fontSize: 11, marginTop: 4, marginLeft: 18 }}>
            {conn.apps_found} app{conn.apps_found !== 1 ? 's' : ''} found | Last checked: {new Date(conn.timestamp).toLocaleString()}
          </Text>
        )}
        {error && <Text style={{ color: T.error, fontSize: 12, marginTop: 4, marginLeft: 18 }}>{error}</Text>}
      </View>

      {/* Tabs */}
      <View style={{ flexDirection: 'row', gap: 8, marginBottom: 16 }}>
        {TABS.map(t => (
          <TouchableOpacity
            key={t.id}
            data-testid={`appstore-tab-${t.id}`} testID={`appstore-tab-${t.id}`}
            onPress={() => setTab(t.id)}
            style={{
              flexDirection: 'row', alignItems: 'center', gap: 6,
              paddingHorizontal: 14, paddingVertical: 8, borderRadius: 8,
              backgroundColor: tab === t.id ? (globalThis as any).__alphaColor(T.primary, '20') : T.card,
              borderWidth: 1, borderColor: tab === t.id ? (globalThis as any).__alphaColor(T.primary, '40') : T.border,
            }}
          >
            <Ionicons name={t.icon as any} size={14} color={tab === t.id ? T.primary : T.textMuted} />
            <Text style={{ color: tab === t.id ? T.primary : T.textSec, fontSize: 12, fontWeight: '600' }}>{t.label}</Text>
          </TouchableOpacity>
        ))}
      </View>

      {/* Tab Content */}
      {tab === 'dashboard' && <DashboardTab conn={conn} apps={apps} sales={sales} T={T} tx={tx} />}
      {tab === 'apps' && <AppsTab apps={apps} T={T} tx={tx} />}
      {tab === 'sales' && <SalesTab sales={sales} T={T} tx={tx} />}
    </ScrollView>
  );
}

function DashboardTab({ conn, apps, sales, T, tx }: any) {
  const stats = [
    { label: 'Total Apps', value: conn?.apps_found ?? 0, icon: 'apps', color: T.primary },
    { label: 'API Status', value: conn?.connected ? 'Active' : 'Error', icon: 'cloud-done', color: conn?.connected ? T.success : T.error },
    { label: 'Sales Reports', value: sales?.length ?? 0, icon: 'receipt', color: T.purpleText },
    { label: 'Key ID', value: '34YP...M8', icon: 'key', color: T.warningText },
  ];

  return (
    <View data-testid="appstore-dashboard-tab" testID="appstore-dashboard-tab">
      {/* Stats Grid */}
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10, marginBottom: 20 }}>
        {stats.map((s, i) => (
          <View key={i} style={{ flex: 1, minWidth: 140, backgroundColor: T.card, borderRadius: 10, padding: 14, borderWidth: 1, borderColor: T.border }}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 8 }}>
              <Ionicons name={s.icon as any} size={16} color={s.color} />
              <Text style={{ color: T.textMuted, fontSize: 11 }}>{s.label}</Text>
            </View>
            <Text style={{ color: T.text, fontSize: 20, fontWeight: '700' }}>{s.value}</Text>
          </View>
        ))}
      </View>

      {/* Info Card */}
      <View style={{ backgroundColor: T.card, borderRadius: 10, padding: 16, borderWidth: 1, borderColor: T.border, marginBottom: 16 }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 12 }}>
          <Ionicons name="information-circle" size={18} color={T.cyan} />
          <Text style={{ color: T.text, fontWeight: '600', fontSize: 14 }}>{tx('admin.appStoreConnectPanel.dashboard.integrationDetails', 'Integration Details')}</Text>
        </View>
        <View style={{ gap: 8 }}>
          <DetailRow label="Authentication" value="JWT ES256" T={T} />
          <DetailRow label="API Base" value="api.appstoreconnect.apple.com/v1" T={T} />
          <DetailRow label="Token Expiry" value="20 minutes (auto-refresh)" T={T} />
          <DetailRow label="Data Sources" value="Apps, Sales Reports, Finance Reports" T={T} />
        </View>
      </View>

      {apps.length === 0 && (
        <View style={{ backgroundColor: T.bg, borderRadius: 10, padding: 20, alignItems: 'center', borderWidth: 1, borderColor: T.border }}>
          <Ionicons name="storefront-outline" size={40} color={T.textMuted} />
          <Text style={{ color: T.textSec, fontSize: 14, fontWeight: '600', marginTop: 10 }}>{tx('admin.appStoreConnectPanel.dashboard.noAppsFound', 'No Apps Found')}</Text>
          <Text style={{ color: T.textMuted, fontSize: 12, textAlign: 'center', marginTop: 4, maxWidth: 300 }}>
            {tx('admin.appStoreConnectPanel.dashboard.noAppsHelp', 'Your App Store Connect account is connected but has no apps. Publish an app to see real-time analytics here.')}
          </Text>
        </View>
      )}
    </View>
  );
}

function AppsTab({ apps, T, tx }: { apps: any[]; T: any; tx: (key: string, fallback: string) => string }) {
  if (!apps.length) return (
    <View style={{ padding: 40, alignItems: 'center' }} data-testid="appstore-apps-empty" testID="appstore-apps-empty">
      <Ionicons name="apps-outline" size={48} color={T.textMuted} />
      <Text style={{ color: T.textSec, marginTop: 12, fontSize: 14, fontWeight: '600' }}>{tx('admin.appStoreConnectPanel.apps.emptyTitle', 'No Apps Available')}</Text>
      <Text style={{ color: T.textMuted, fontSize: 12, marginTop: 4, textAlign: 'center' }}>
        {tx('admin.appStoreConnectPanel.apps.emptySubtitle', 'Apps will appear here once published to the App Store.')}
      </Text>
    </View>
  );

  return (
    <View data-testid="appstore-apps-tab" testID="appstore-apps-tab" style={{ gap: 10 }}>
      {apps.map((app: any, i: number) => (
        <View key={i} style={{ backgroundColor: T.card, borderRadius: 10, padding: 14, borderWidth: 1, borderColor: T.border }}>
          <Text style={{ color: T.text, fontWeight: '700', fontSize: 15 }}>{app.name || 'Unnamed App'}</Text>
          <Text style={{ color: T.textMuted, fontSize: 12, marginTop: 4 }}>Bundle ID: {app.bundle_id || '—'}</Text>
          <Text style={{ color: T.textMuted, fontSize: 12, marginTop: 2 }}>SKU: {app.sku || '—'}</Text>
          <Text style={{ color: T.textMuted, fontSize: 12, marginTop: 2 }}>Locale: {app.primary_locale || '—'}</Text>
        </View>
      ))}
    </View>
  );
}

function SalesTab({ sales, T, tx }: { sales: any[]; T: any; tx: (key: string, fallback: string) => string }) {
  if (!sales.length) return (
    <View style={{ padding: 40, alignItems: 'center' }} data-testid="appstore-sales-empty" testID="appstore-sales-empty">
      <Ionicons name="receipt-outline" size={48} color={T.textMuted} />
      <Text style={{ color: T.textSec, marginTop: 12, fontSize: 14, fontWeight: '600' }}>{tx('admin.appStoreConnectPanel.sales.emptyTitle', 'No Sales Data')}</Text>
      <Text style={{ color: T.textMuted, fontSize: 12, marginTop: 4, textAlign: 'center' }}>
        {tx('admin.appStoreConnectPanel.sales.emptySubtitle', 'Sales reports will appear once your app generates revenue. Use the API to fetch reports with your vendor number.')}
      </Text>
    </View>
  );

  return (
    <View data-testid="appstore-sales-tab" testID="appstore-sales-tab" style={{ gap: 10 }}>
      {sales.map((s: any, i: number) => (
        <View key={i} style={{ backgroundColor: T.card, borderRadius: 10, padding: 14, borderWidth: 1, borderColor: T.border }}>
          <Text style={{ color: T.text, fontWeight: '600', fontSize: 13 }}>Report: {s.report_date} ({s.frequency})</Text>
          <Text style={{ color: T.textMuted, fontSize: 12, marginTop: 4 }}>Rows: {s.count || 0}</Text>
          {s.fetched_at && <Text style={{ color: T.textMuted, fontSize: 11, marginTop: 2 }}>Fetched: {new Date(s.fetched_at).toLocaleString()}</Text>}
        </View>
      ))}
    </View>
  );
}

function DetailRow({ label, value, T }: { label: string; value: string; T: any }) {
  return (
    <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
      <Text style={{ color: T.textMuted, fontSize: 12 }}>{label}</Text>
      <Text style={{ color: T.textSec, fontSize: 12, fontWeight: '500' }}>{value}</Text>
    </View>
  );
}
