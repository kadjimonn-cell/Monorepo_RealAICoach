import React, { useState, useCallback } from 'react';
import { useAdminTheme } from '../../hooks/useAdminTheme';
import { useTranslation } from '../../hooks/useTranslation';
import { View, Text, ScrollView, ActivityIndicator, TouchableOpacity, TextInput } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import AutoFixBanner from './AutoFixBanner';
import { useHybridPolling } from '../../hooks/useHybridPolling';

const tx = (_key: string, fallback: string) => fallback;

const T = {
  bg: 'var(--app-bg)', card: 'var(--app-card-bg)', border: 'var(--app-border)', text: 'var(--app-text)',
  textSec: 'var(--app-text-sec)', textMuted: 'var(--app-text-muted)', primary: 'var(--app-primary)', success: 'var(--app-success)',
  warning: 'var(--app-warning)', error: 'var(--app-error)', purple: 'var(--app-primary)', cyan: 'var(--app-primary)',
  green: 'var(--app-success)', // Google green
  purpleText: 'var(--app-primary)',
};

type Tab = 'dashboard' | 'reviews' | 'app-details';

export default function GooglePlayPanel({ colors }: { colors: any }) {
  const { t } = useTranslation();
  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };

  useAdminTheme();
  const [tab, setTab] = useState<Tab>('dashboard');
  const [loading, setLoading] = useState(true);
  const [dashboard, setDashboard] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [packageName, setPackageName] = useState('');
  const [reviews, setReviews] = useState<any[]>([]);
  const [reviewsLoading, setReviewsLoading] = useState(false);
  const [appDetails, setAppDetails] = useState<any>(null);
  const [appLoading, setAppLoading] = useState(false);

  const fetchDashboard = useCallback(async (silent = false) => {
    if (!silent) setLoading(true);
    else setRefreshing(true);
    try {
      const res = await api.get('/admin/google-play/dashboard');
      setDashboard(res.data);
      setError(null);
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Failed to connect to Google Play Console');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useHybridPolling({
    enabled: true,
    errorScope: 'admin/google-play/hybrid-refresh',
    onTick: fetchDashboard,
    runOnMount: true,
    slowIntervalMs: 45000,
    fastIntervalMs: 15000,
  });

  const fetchReviews = async () => {
    if (!packageName.trim()) return;
    setReviewsLoading(true);
    try {
      const res = await api.get(`/admin/google-play/reviews/${packageName.trim()}`);
      setReviews(res.data.reviews || []);
    // eslint-disable-next-line @typescript-eslint/no-unused-vars
    } catch (e: any) {
      setReviews([]);
    } finally {
      setReviewsLoading(false);
    }
  };

  const fetchAppDetails = async () => {
    if (!packageName.trim()) return;
    setAppLoading(true);
    try {
      const res = await api.get(`/admin/google-play/app/${packageName.trim()}`);
      setAppDetails(res.data);
    } catch (e: any) {
      setAppDetails({ status: 'error', detail: e?.response?.data?.detail || 'Failed to fetch' });
    } finally {
      setAppLoading(false);
    }
  };

  if (loading) return (
    <View style={{ padding: 40, alignItems: 'center' }} data-testid="google-play-loading" testID="google-play-loading">
      <AutoFixBanner domain="google_play" />
      <ActivityIndicator size="large" color={T.green} />
      <Text style={{ color: T.textSec, marginTop: 12, fontSize: 14 }}>{tx('admin.googlePlayPanel.auto.text.001', 'Connecting to Google Play Console...')}</Text>
    </View>
  );

  const conn = dashboard?.connection;
  const TABS: { id: Tab; label: string; icon: string }[] = [
    { id: 'dashboard', label: 'Overview', icon: 'grid' },
    { id: 'reviews', label: 'Reviews', icon: 'chatbubbles' },
    { id: 'app-details', label: 'App Details', icon: 'information-circle' },
  ];

  return (
    <ScrollView style={{ flex: 1 }} data-testid="google-play-panel" testID="google-play-panel">
      {/* Header */}
      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 20 }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
          <View style={{ width: 40, height: 40, borderRadius: 10, backgroundColor: `${T.green}22`, alignItems: 'center', justifyContent: 'center' }}>
            <Ionicons name="logo-google-playstore" size={22} color={T.green} />
          </View>
          <View>
            <Text style={{ color: T.text, fontSize: 18, fontWeight: '700' }}>{tx('admin.googlePlayPanel.auto.text.002', 'Google Play Console')}</Text>
            <Text style={{ color: T.textSec, fontSize: 12 }}>{tx('admin.googlePlayPanel.auto.text.003', 'Android Developer API v3')}</Text>
          </View>
        </View>
        <TouchableOpacity
          data-testid="google-play-refresh-btn" testID="google-play-refresh-btn"
          onPress={() => fetchDashboard(true)}
          style={{ flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: T.card, borderRadius: 8, paddingHorizontal: 12, paddingVertical: 6, borderWidth: 1, borderColor: T.border }}
        >
          {refreshing ? <ActivityIndicator size="small" color={T.green} /> : <Ionicons name="refresh" size={14} color={T.green} />}
          <Text style={{ color: T.green, fontSize: 12, fontWeight: '600' }}>{tx('admin.googlePlayPanel.auto.text.004', 'Refresh')}</Text>
        </TouchableOpacity>
      </View>

      {/* Connection Status */}
      <View data-testid="google-play-connection-status" testID="google-play-connection-status" style={{ backgroundColor: conn?.connected ? 'var(--app-primary)' : 'var(--app-primary)', borderRadius: 10, padding: 14, marginBottom: 16, borderWidth: 1, borderColor: conn?.connected ? 'var(--app-primary)' : 'var(--app-error)' }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
          <View style={{ width: 10, height: 10, borderRadius: 5, backgroundColor: conn?.connected ? T.success : T.error }} />
          <Text style={{ color: conn?.connected ? T.success : T.error, fontWeight: '600', fontSize: 14 }}>
            {conn?.connected ? 'Connected to Google Play Console' : 'Connection Failed'}
          </Text>
        </View>
        {conn?.connected && (
          <Text style={{ color: T.textMuted, fontSize: 11, marginTop: 4, marginLeft: 18 }}>
            Service account: {conn.service_account} | Last checked: {new Date(conn.timestamp).toLocaleString()}
          </Text>
        )}
        {error && <Text style={{ color: T.error, fontSize: 12, marginTop: 4, marginLeft: 18 }}>{error}</Text>}
      </View>

      {/* Package Name Input */}
      <View style={{ backgroundColor: T.card, borderRadius: 10, padding: 14, marginBottom: 16, borderWidth: 1, borderColor: T.border }}>
        <Text style={{ color: T.text, fontWeight: '600', fontSize: 13, marginBottom: 8 }}>{tx('admin.googlePlayPanel.auto.text.005', 'App Package Name')}</Text>
        <View style={{ flexDirection: 'row', gap: 8 }}>
          <TextInput
            data-testid="google-play-package-input" testID="google-play-package-input"
            value={packageName}
            onChangeText={setPackageName}
            placeholder={tx('admin.googlePlayPanel.auto.placeholder.001', 'com.realaicoach.app')}
            placeholderTextColor={T.textMuted}
            style={{
              flex: 1, backgroundColor: T.bg, borderRadius: 8, paddingHorizontal: 12, paddingVertical: 8,
              color: T.text, fontSize: 13, borderWidth: 1, borderColor: T.border,
            }}
          />
        </View>
        <Text style={{ color: T.textMuted, fontSize: 11, marginTop: 6 }}>{tx('admin.googlePlayPanel.auto.text.006', 'Enter your app\'s package name to fetch reviews and details from Google Play.')}</Text>
      </View>

      {/* Tabs */}
      <View style={{ flexDirection: 'row', gap: 8, marginBottom: 16 }}>
        {TABS.map(t => (
          <TouchableOpacity
            key={t.id}
            data-testid={`google-play-tab-${t.id}`} testID={`google-play-tab-${t.id}`}
            onPress={() => setTab(t.id)}
            style={{
              flexDirection: 'row', alignItems: 'center', gap: 6,
              paddingHorizontal: 14, paddingVertical: 8, borderRadius: 8,
              backgroundColor: tab === t.id ? (globalThis as any).__alphaColor(T.green, '20') : T.card,
              borderWidth: 1, borderColor: tab === t.id ? (globalThis as any).__alphaColor(T.green, '40') : T.border,
            }}
          >
            <Ionicons name={t.icon as any} size={14} color={tab === t.id ? T.green : T.textMuted} />
            <Text style={{ color: tab === t.id ? T.green : T.textSec, fontSize: 12, fontWeight: '600' }}>{t.label}</Text>
          </TouchableOpacity>
        ))}
      </View>

      {/* Tab Content */}
      {tab === 'dashboard' && <DashboardTab conn={conn} dashboard={dashboard} />}
      {tab === 'reviews' && (
        <ReviewsTab
          reviews={reviews}
          loading={reviewsLoading}
          onFetch={fetchReviews}
          packageName={packageName}
        />
      )}
      {tab === 'app-details' && (
        <AppDetailsTab
          details={appDetails}
          loading={appLoading}
          onFetch={fetchAppDetails}
          packageName={packageName}
        />
      )}
    </ScrollView>
  );
}

function DashboardTab({ conn, dashboard }: any) {
  const stats = [
    { label: 'API Status', value: conn?.connected ? 'Active' : 'Error', icon: 'cloud-done', color: conn?.connected ? T.success : T.error },
    { label: 'Service Account', value: conn?.service_account?.split('.')[0] || '—', icon: 'person-circle', color: T.green },
    { label: 'Cached Reviews', value: dashboard?.cached_reviews?.length ?? 0, icon: 'chatbubbles', color: T.purpleText },
    { label: 'Cached Apps', value: dashboard?.cached_apps?.length ?? 0, icon: 'apps', color: T.cyan },
  ];

  return (
    <View data-testid="google-play-dashboard-tab" testID="google-play-dashboard-tab">
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10, marginBottom: 20 }}>
        {stats.map((s, i) => (
          <View key={i} style={{ flex: 1, minWidth: 140, backgroundColor: T.card, borderRadius: 10, padding: 14, borderWidth: 1, borderColor: T.border }}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 8 }}>
              <Ionicons name={s.icon as any} size={16} color={s.color} />
              <Text style={{ color: T.textMuted, fontSize: 11 }}>{s.label}</Text>
            </View>
            <Text style={{ color: T.text, fontSize: 18, fontWeight: '700' }}>{s.value}</Text>
          </View>
        ))}
      </View>

      <View style={{ backgroundColor: T.card, borderRadius: 10, padding: 16, borderWidth: 1, borderColor: T.border }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 12 }}>
          <Ionicons name="information-circle" size={18} color={T.cyan} />
          <Text style={{ color: T.text, fontWeight: '600', fontSize: 14 }}>{tx('admin.googlePlayPanel.auto.text.007', 'Integration Details')}</Text>
        </View>
        <View style={{ gap: 8 }}>
          <DetailRow label="Authentication" value="Service Account (OAuth2)" />
          <DetailRow label="API" value="androidpublisher v3" />
          <DetailRow label="Scopes" value="androidpublisher" />
          <DetailRow label="Features" value="Reviews, App Details, Reply to Reviews" />
        </View>
      </View>
    </View>
  );
}

function ReviewsTab({ reviews, loading, onFetch, packageName }: any) {
  const colors = useAdminTheme();
  return (
    <View data-testid="google-play-reviews-tab" testID="google-play-reviews-tab">
      <TouchableOpacity
        data-testid="google-play-fetch-reviews-btn" testID="google-play-fetch-reviews-btn"
        onPress={onFetch}
        disabled={loading || !packageName.trim()}
        style={{
          flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8,
          backgroundColor: packageName.trim() ? T.green : T.textMuted, borderRadius: 8,
          paddingVertical: 10, marginBottom: 16, opacity: loading ? 0.6 : 1,
        }}
      >
        {loading ? <ActivityIndicator size="small" color="var(--app-primary-text)" /> : <Ionicons name="download" size={16} color="var(--app-primary-text)" />}
        <Text style={{ color: colors.primaryText, fontWeight: '600', fontSize: 13 }}>
          {loading ? 'Fetching Reviews...' : 'Fetch Reviews'}
        </Text>
      </TouchableOpacity>

      {!packageName.trim() && (
        <View style={{ padding: 20, alignItems: 'center' }}>
          <Text style={{ color: T.textMuted, fontSize: 12, textAlign: 'center' }}>{tx('admin.googlePlayPanel.auto.text.008', 'Enter a package name above to fetch reviews.')}</Text>
        </View>
      )}

      {reviews.length === 0 && packageName.trim() && !loading && (
        <View style={{ padding: 30, alignItems: 'center' }}>
          <Ionicons name="chatbubble-ellipses-outline" size={40} color={T.textMuted} />
          <Text style={{ color: T.textSec, fontSize: 14, fontWeight: '600', marginTop: 10 }}>{tx('admin.googlePlayPanel.auto.text.009', 'No Reviews Found')}</Text>
          <Text style={{ color: T.textMuted, fontSize: 12, marginTop: 4, textAlign: 'center' }}>{tx('admin.googlePlayPanel.auto.text.010', 'No reviews available for this package, or the service account may not have access.')}</Text>
        </View>
      )}

      {reviews.map((r: any, i: number) => (
        <View key={i} style={{ backgroundColor: T.card, borderRadius: 10, padding: 14, borderWidth: 1, borderColor: T.border, marginBottom: 10 }}>
          <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
            <Text style={{ color: T.text, fontWeight: '600', fontSize: 13 }}>{r.author}</Text>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}>
              {Array.from({ length: 5 }).map((_, si) => (
                <Ionicons key={si} name={si < (r.user_comment?.star_rating || 0) ? 'star' : 'star-outline'} size={12} color={T.warningText} />
              ))}
            </View>
          </View>
          <Text style={{ color: T.textSec, fontSize: 12 }}>{r.user_comment?.text || 'No comment'}</Text>
          {r.user_comment?.app_version && (
            <Text style={{ color: T.textMuted, fontSize: 11, marginTop: 4 }}>v{r.user_comment.app_version} | {r.user_comment.device || 'Unknown device'}</Text>
          )}
          {r.developer_comment?.text && (
            <View style={{ marginTop: 8, backgroundColor: T.bg, borderRadius: 6, padding: 8 }}>
              <Text style={{ color: T.green, fontSize: 11, fontWeight: '600' }}>{tx('admin.googlePlayPanel.auto.text.011', 'Developer Reply:')}</Text>
              <Text style={{ color: T.textSec, fontSize: 11, marginTop: 2 }}>{r.developer_comment.text}</Text>
            </View>
          )}
        </View>
      ))}
    </View>
  );
}

function AppDetailsTab({ details, loading, onFetch, packageName }: any) {
  const colors = useAdminTheme();
  return (
    <View data-testid="google-play-app-details-tab" testID="google-play-app-details-tab">
      <TouchableOpacity
        data-testid="google-play-fetch-details-btn" testID="google-play-fetch-details-btn"
        onPress={onFetch}
        disabled={loading || !packageName.trim()}
        style={{
          flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8,
          backgroundColor: packageName.trim() ? T.green : T.textMuted, borderRadius: 8,
          paddingVertical: 10, marginBottom: 16, opacity: loading ? 0.6 : 1,
        }}
      >
        {loading ? <ActivityIndicator size="small" color="var(--app-primary-text)" /> : <Ionicons name="search" size={16} color="var(--app-primary-text)" />}
        <Text style={{ color: colors.primaryText, fontWeight: '600', fontSize: 13 }}>
          {loading ? 'Fetching...' : 'Fetch App Details'}
        </Text>
      </TouchableOpacity>

      {!details && !loading && (
        <View style={{ padding: 30, alignItems: 'center' }}>
          <Ionicons name="information-circle-outline" size={40} color={T.textMuted} />
          <Text style={{ color: T.textSec, fontSize: 14, fontWeight: '600', marginTop: 10 }}>{tx('admin.googlePlayPanel.auto.text.012', 'No Data Yet')}</Text>
          <Text style={{ color: T.textMuted, fontSize: 12, marginTop: 4 }}>{tx('admin.googlePlayPanel.auto.text.013', 'Enter a package name and click fetch.')}</Text>
        </View>
      )}

      {details && details.status === 'error' && (
        <View style={{ backgroundColor: (globalThis as any).__alphaColor(T.error, '22'), borderRadius: 10, padding: 14, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(T.error, '55') }}>
          <Text style={{ color: T.error, fontWeight: '600', fontSize: 13 }}>{tx('admin.googlePlayPanel.auto.text.014', 'Error fetching app details')}</Text>
          <Text style={{ color: T.textMuted, fontSize: 12, marginTop: 4 }}>{details.detail}</Text>
        </View>
      )}

      {details && details.status === 'ok' && (
        <View style={{ backgroundColor: T.card, borderRadius: 10, padding: 16, borderWidth: 1, borderColor: T.border }}>
          <Text style={{ color: T.text, fontWeight: '700', fontSize: 16, marginBottom: 12 }}>{details.package_name}</Text>
          <View style={{ gap: 8 }}>
            <DetailRow label="Default Language" value={details.default_language || '—'} />
            <DetailRow label="Contact Email" value={details.contact_email || '—'} />
            <DetailRow label="Contact Website" value={details.contact_website || '—'} />
            <DetailRow label="Listings" value={`${details.listings?.length || 0} languages`} />
          </View>

          {details.listings?.map((l: any, i: number) => (
            <View key={i} style={{ marginTop: 12, backgroundColor: T.bg, borderRadius: 8, padding: 10 }}>
              <Text style={{ color: T.green, fontWeight: '600', fontSize: 12 }}>{l.language}: {l.title}</Text>
              <Text style={{ color: T.textMuted, fontSize: 11, marginTop: 2 }}>{l.short_description}</Text>
            </View>
          ))}
        </View>
      )}
    </View>
  );
}

function DetailRow({ label, value }: { label: string; value: string }) {
  return (
    <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
      <Text style={{ color: T.textMuted, fontSize: 12 }}>{label}</Text>
      <Text style={{ color: T.textSec, fontSize: 12, fontWeight: '500' }}>{value}</Text>
    </View>
  );
}
