import React, { useEffect, useState, useRef } from 'react';
import { View, Text, ActivityIndicator, ScrollView, useWindowDimensions, TouchableOpacity, ImageBackground, Animated } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { getTestProps } from '../../utils/testProps';
import { useLiveQuery } from '../../hooks/useLiveQuery';
import AutoFixBanner from './AutoFixBanner';
import { useAdminTheme } from '../../hooks/useAdminTheme';
import { useTranslation } from '../../hooks/useTranslation';
import { handleAppRecoverableError } from '../../utils/appRecoverableError';

function makeC(AC: any) { return {
  bg: AC.bg, card: AC.card, border: AC.border,
  text: AC.text, muted: AC.textMuted, sec: AC.textSec,
  green: 'var(--app-success)', red: 'var(--app-error)', blue: 'var(--app-primary)',
  yellow: 'var(--app-warning)', purple: 'var(--app-primary)', cyan: 'var(--app-primary)',
  teal: 'var(--app-primary)', orange: 'var(--app-warning)',
  accent: 'var(--app-primary)',
}; }

// Module-scope fallback for helper components (they can't access the component-scoped C)
const C = {
  orangeText: 'var(--app-warning)',
  purpleText: 'var(--app-info)',
  bg: 'var(--app-bg)', card: 'var(--app-card-bg)', border: 'var(--app-border)',
  text: 'var(--app-text)', muted: 'var(--app-text-muted)', sec: 'var(--app-primary)',
  green: 'var(--app-success)', red: 'var(--app-error)', blue: 'var(--app-primary)',
  yellow: 'var(--app-warning)', purple: 'var(--app-primary)', cyan: 'var(--app-primary)',
  teal: 'var(--app-primary)', orange: 'var(--app-warning)',
  accent: 'var(--app-primary)',
};

const tx = (_key: string, fallback: string) => fallback;

function KPICard({ label, value, icon, color, sub }: any) {
  return (
    <View style={{ flex: 1, minWidth: 150, backgroundColor: (globalThis as any).__alphaColor(color, '10'), borderRadius: 14, padding: 16, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(color, '20') }}>
      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
        <Text style={{ fontSize: 11, color: C.muted, fontWeight: '600', textTransform: 'uppercase', letterSpacing: 0.5 }}>{label}</Text>
        <Ionicons name={icon} size={16} color={color} />
      </View>
      <Text style={{ fontSize: 28, fontWeight: '800', color, letterSpacing: -0.5 }}>{value}</Text>
      {sub && <Text style={{ fontSize: 11, color: C.sec, marginTop: 4 }}>{sub}</Text>}
    </View>
  );
}

function BarChart({ data, height = 130 }: { data: any[]; height?: number }) {
  if (!data?.length) return <Text style={{ color: C.muted, fontSize: 12 }}>{tx('admin.campaignDashboardPanel.auto.text.001', 'No campaigns yet')}</Text>;
  const max = Math.max(...data.map((d: any) => d.sent || 0), 1);
  return (
    <View>
      <View style={{ flexDirection: 'row', alignItems: 'flex-end', height, gap: 8 }}>
        {data.map((d: any, i: number) => {
          const barH = Math.max(4, (d.sent / max) * (height - 40));
          const failH = d.failed > 0 ? Math.max(2, (d.failed / max) * (height - 40)) : 0;
          return (
            <View key={i} style={{ flex: 1, alignItems: 'center' }}>
              <Text style={{ fontSize: 10, color: C.accent, fontWeight: '700', marginBottom: 4 }}>{d.sent}</Text>
              <View style={{ width: '80%', maxWidth: 40 }}>
                <View style={{ height: barH, backgroundColor: (globalThis as any).__alphaColor(C.accent, '50'), borderTopLeftRadius: 6, borderTopRightRadius: 6, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(C.accent, '30') }} />
                {failH > 0 && <View style={{ height: failH, backgroundColor: (globalThis as any).__alphaColor(C.red, '40'), borderBottomLeftRadius: 6, borderBottomRightRadius: 6, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(C.red, '20'), borderTopWidth: 0 }} />}
              </View>
            </View>
          );
        })}
      </View>
      <View style={{ flexDirection: 'row', gap: 8, marginTop: 8 }}>
        {data.map((d: any, i: number) => (
          <View key={i} style={{ flex: 1, alignItems: 'center' }}>
            <Text style={{ fontSize: 9, color: C.muted, fontWeight: '500' }} numberOfLines={1}>{d.month?.split(' ')[0]?.substring(0, 3) || `C${i + 1}`}</Text>
          </View>
        ))}
      </View>
    </View>
  );
}

function CountdownTimer({ days }: { days: number }) {
  const hrs = (days % 1) * 24;
  return (
    <View style={{ flexDirection: 'row', gap: 12, justifyContent: 'center' }}>
      {[
        { val: Math.floor(days), label: 'Days' },
        { val: Math.floor(hrs), label: 'Hours' },
      ].map(({ val, label }) => (
        <View key={label} style={{ alignItems: 'center' }}>
          <View style={{ backgroundColor: (globalThis as any).__alphaColor(C.accent, '15'), borderRadius: 10, paddingHorizontal: 14, paddingVertical: 8, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(C.accent, '25') }}>
            <Text style={{ fontSize: 24, fontWeight: '800', color: C.accent }}>{val}</Text>
          </View>
          <Text style={{ fontSize: 10, color: C.muted, marginTop: 4, fontWeight: '600', textTransform: 'uppercase', letterSpacing: 0.5 }}>{label}</Text>
        </View>
      ))}
    </View>
  );
}

export default function CampaignDashboardPanel({ colors }: { colors: any }) {
  const { t } = useTranslation();
  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };

  const AC = useAdminTheme();
  const C = React.useMemo(() => makeC(AC), [AC]);
  const { width } = useWindowDimensions();
  const isWide = width >= 768;
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const _isTablet = width >= 768 && width < 1024;
  const { data, loading: dLoading, error: fetchErr } = useLiveQuery('/newsletter/campaigns/dashboard', { entity: 'campaigns', pollInterval: 60000 });
  const { data: segments, loading: sLoading } = useLiveQuery('/newsletter/segments', { entity: 'campaigns', pollInterval: 60000 });
  const loading = dLoading || sLoading;
  const error = fetchErr ? 'Failed to load' : '';
  const [sending, setSending] = useState(false);
  const [segSending, setSegSending] = useState('');
  const [bgIndex, setBgIndex] = useState(0);
  const fadeAnim = useRef(new Animated.Value(1)).current;

  // Rotate background every 30s
  useEffect(() => {
    if (!data?.bg_images?.length) return;
    const timer = setInterval(() => {
      Animated.timing(fadeAnim, { toValue: 0, duration: 800, useNativeDriver: false }).start(() => {
        setBgIndex(prev => (prev + 1) % data.bg_images.length);
        Animated.timing(fadeAnim, { toValue: 1, duration: 800, useNativeDriver: false }).start();
      });
    }, 30000);
    return () => clearInterval(timer);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data?.bg_images]);

  const handleManualSend = async () => {
    setSending(true);
    try {
      const res = await api.post('/newsletter/campaigns/trigger');
      if (res.data.action === 'sent') {
        const refresh = await api.get('/newsletter/campaigns/dashboard');
        setData(refresh.data);
      }
    } catch (error) { handleAppRecoverableError({ scope: 'src/components/admin/CampaignDashboardPanel.tsx#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
    setSending(false);
  };

  const handleSegmentSend = async (segId: string) => {
    setSegSending(segId);
    try {
      await api.post(`/newsletter/campaigns/trigger?segment=${segId}`);
      const [dashRes, segRes] = await Promise.all([
        api.get('/newsletter/campaigns/dashboard'),
        api.get('/newsletter/segments'),
      ]);
      setData(dashRes.data);
      setSegments(segRes.data);
    } catch (error) { handleAppRecoverableError({ scope: 'src/components/admin/CampaignDashboardPanel.tsx#catch2', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
    setSegSending('');
  };

  if (loading) return <View style={{ padding: 40, alignItems: 'center' }}><ActivityIndicator size="large" color={C.accent} /></View>;
      // eslint-disable-next-line no-unused-expressions
      <AutoFixBanner domain="campaigns" />
  if (error) return <View style={{ padding: 24 }}><Text style={{ color: C.red }}>{error}</Text></View>;
  if (!data) return null;

  const bgImages = data.bg_images || [];
  const currentBg = bgImages[bgIndex] || bgImages[0] || '';

  return (
    <ScrollView style={{ flex: 1 }} {...getTestProps('campaign-dashboard-panel')}>

      {/* Hero Banner with Rotating Background */}
      <Animated.View style={{ opacity: fadeAnim, borderRadius: 16, overflow: 'hidden', marginBottom: 20 }}>
        <ImageBackground
          source={{ uri: currentBg }}
          style={{ minHeight: 180 }}
          imageStyle={{ borderRadius: 16 }}
          {...getTestProps('campaign-hero-banner')}
        >
          <View style={{ backgroundColor: 'rgba(11,15,26,0.75)', padding: 28, borderRadius: 16, minHeight: 180, justifyContent: 'center' }}>
            <View style={{ flexDirection: isWide ? 'row' : 'column', alignItems: isWide ? 'center' : 'flex-start', justifyContent: 'space-between', gap: 16 }}>
              <View style={{ flex: 1 }}>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 8 }}>
                  <View style={{ width: 40, height: 40, borderRadius: 12, backgroundColor: (globalThis as any).__alphaColor(C.accent, '25'), alignItems: 'center', justifyContent: 'center' }}>
                    <Ionicons name="rocket" size={20} color={C.accent} />
                  </View>
                  <View>
                    <Text style={{ fontSize: 20, fontWeight: '800', color: AC.text, letterSpacing: -0.3 }}>{tx('admin.campaignDashboardPanel.auto.text.002', 'Campaign Command Center')}</Text>
                    <Text style={{ fontSize: 12, color: AC.textMuted }}>{tx('admin.campaignDashboardPanel.auto.text.003', 'Automated monthly digest system')}</Text>
                  </View>
                </View>
                <View style={{ flexDirection: 'row', gap: 12, marginTop: 8, flexWrap: 'wrap' }}>
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 5, backgroundColor: (globalThis as any).__alphaColor(C.green, '20'), paddingHorizontal: 10, paddingVertical: 5, borderRadius: 8 }}>
                    <View style={{ width: 6, height: 6, borderRadius: 3, backgroundColor: C.green }} />
                    <Text style={{ fontSize: 11, color: C.green, fontWeight: '600' }}>{tx('admin.campaignDashboardPanel.auto.text.004', 'System Active')}</Text>
                  </View>
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 5, backgroundColor: (globalThis as any).__alphaColor(C.blue, '20'), paddingHorizontal: 10, paddingVertical: 5, borderRadius: 8 }}>
                    <Ionicons name="timer-outline" size={12} color={C.blue} />
                    <Text style={{ fontSize: 11, color: C.blue, fontWeight: '600' }}>Every {data.campaign_interval_days} days</Text>
                  </View>
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 5, backgroundColor: (globalThis as any).__alphaColor(C.purple, '20'), paddingHorizontal: 10, paddingVertical: 5, borderRadius: 8 }}>
                    <Ionicons name="people-outline" size={12} color={C.purpleText} />
                    <Text style={{ fontSize: 11, color: C.purpleText, fontWeight: '600' }}>{data.active_subscribers} subscribers</Text>
                  </View>
                </View>
              </View>

              {/* Next Send Countdown */}
              <View style={{ alignItems: 'center', gap: 8 }}>
                <Text style={{ fontSize: 11, color: AC.textMuted, fontWeight: '600', textTransform: 'uppercase', letterSpacing: 0.5 }}>{tx('admin.campaignDashboardPanel.auto.text.005', 'Next Campaign In')}</Text>
                <CountdownTimer days={data.days_until_next} />
              </View>
            </View>
          </View>
        </ImageBackground>
      </Animated.View>

      {/* KPI Row */}
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 12, marginBottom: 20 }} {...getTestProps('campaign-kpi-row')}>
        <KPICard label="Campaigns Sent" value={data.total_campaigns} icon="send" color={C.accent} sub="All-time" />
        <KPICard label="Emails Delivered" value={data.total_emails_sent.toLocaleString()} icon="mail" color={C.blue} sub="Total delivered" />
        <KPICard label="Delivery Rate" value={`${data.delivery_rate}%`} icon="checkmark-circle" color={C.green} sub="Success rate" />
        <KPICard label="Active Subscribers" value={data.active_subscribers} icon="people" color={C.purpleText} sub="Current list" />
      </View>

      {/* Charts + Controls Row */}
      <View style={{ flexDirection: isWide ? 'row' : 'column', gap: 16, marginBottom: 20 }}>
        {/* Delivery Trend */}
        <View style={{ flex: 2, backgroundColor: C.card, borderRadius: 14, padding: 20, borderWidth: 1, borderColor: C.border }} {...getTestProps('campaign-delivery-chart')}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 16 }}>
            <Ionicons name="bar-chart" size={16} color={C.accent} />
            <Text style={{ fontSize: 14, fontWeight: '700', color: C.text }}>{tx('admin.campaignDashboardPanel.auto.text.006', 'Delivery Performance')}</Text>
            <Text style={{ fontSize: 11, color: C.muted, marginLeft: 'auto' }}>Last {data.delivery_trend?.length || 0} campaigns</Text>
          </View>
          <BarChart data={data.delivery_trend} />
          <View style={{ flexDirection: 'row', gap: 16, marginTop: 12 }}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
              <View style={{ width: 10, height: 10, borderRadius: 2, backgroundColor: (globalThis as any).__alphaColor(C.accent, '50') }} />
              <Text style={{ fontSize: 10, color: C.muted }}>{tx('admin.campaignDashboardPanel.auto.text.007', 'Delivered')}</Text>
            </View>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
              <View style={{ width: 10, height: 10, borderRadius: 2, backgroundColor: (globalThis as any).__alphaColor(C.red, '40') }} />
              <Text style={{ fontSize: 10, color: C.muted }}>{tx('admin.campaignDashboardPanel.auto.text.008', 'Failed')}</Text>
            </View>
          </View>
        </View>

        {/* Automation Controls */}
        <View style={{ flex: 1, backgroundColor: C.card, borderRadius: 14, padding: 20, borderWidth: 1, borderColor: C.border }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 16 }}>
            <Ionicons name="settings" size={16} color={C.yellow} />
            <Text style={{ fontSize: 14, fontWeight: '700', color: C.text }}>{tx('admin.campaignDashboardPanel.auto.text.009', 'Automation')}</Text>
          </View>

          <View style={{ gap: 12 }}>
            <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingVertical: 8, borderBottomWidth: 1, borderBottomColor: C.border }}>
              <Text style={{ fontSize: 12, color: C.sec }}>{tx('admin.campaignDashboardPanel.auto.text.010', 'Frequency')}</Text>
              <Text style={{ fontSize: 12, color: C.text, fontWeight: '700' }}>Every {data.campaign_interval_days} days</Text>
            </View>
            <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingVertical: 8, borderBottomWidth: 1, borderBottomColor: C.border }}>
              <Text style={{ fontSize: 12, color: C.sec }}>{tx('admin.campaignDashboardPanel.auto.text.011', 'Template')}</Text>
              <Text style={{ fontSize: 12, color: C.accent, fontWeight: '700' }}>{tx('admin.campaignDashboardPanel.auto.text.012', 'Monthly Digest')}</Text>
            </View>
            <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingVertical: 8, borderBottomWidth: 1, borderBottomColor: C.border }}>
              <Text style={{ fontSize: 12, color: C.sec }}>{tx('admin.campaignDashboardPanel.auto.text.013', 'Status')}</Text>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 5 }}>
                <View style={{ width: 6, height: 6, borderRadius: 3, backgroundColor: C.green }} />
                <Text style={{ fontSize: 12, color: C.green, fontWeight: '700' }}>{tx('admin.campaignDashboardPanel.auto.text.014', 'Active')}</Text>
              </View>
            </View>
            <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingVertical: 8 }}>
              <Text style={{ fontSize: 12, color: C.sec }}>{tx('admin.campaignDashboardPanel.auto.text.015', 'Next Send')}</Text>
              <Text style={{ fontSize: 12, color: C.text, fontWeight: '700' }}>{data.days_until_next}d</Text>
            </View>
          </View>

          <TouchableOpacity accessibilityLabel={tx('admin.campaignDashboardPanel.auto.accessibility.001', 'Send campaign now')}
            style={{ marginTop: 16, backgroundColor: C.accent, borderRadius: 10, paddingVertical: 12, alignItems: 'center', flexDirection: 'row', justifyContent: 'center', gap: 8, opacity: sending ? 0.6 : 1 }}
            onPress={handleManualSend}
            disabled={sending}
            activeOpacity={0.8}
            {...getTestProps('campaign-send-now-btn')}
          >
            {sending ? (
              <ActivityIndicator size="small" color={AC.primaryText || AC.bg} />
            ) : (
              <>
                <Ionicons name="send" size={14} color={AC.primaryText || AC.bg} />
                <Text style={{ fontSize: 13, fontWeight: '700', color: AC.primaryText }}>{tx('admin.campaignDashboardPanel.auto.text.016', 'Send Now')}</Text>
              </>
            )}
          </TouchableOpacity>
        </View>
      </View>

      {/* Subscriber Segments */}
      {segments?.segments?.length > 0 && (
        <View style={{ backgroundColor: C.card, borderRadius: 14, padding: 20, borderWidth: 1, borderColor: C.border, marginBottom: 20 }} {...getTestProps('campaign-segments')}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 4 }}>
            <Ionicons name="git-branch" size={16} color={C.orangeText} />
            <Text style={{ fontSize: 14, fontWeight: '700', color: C.text }}>{tx('admin.campaignDashboardPanel.auto.text.017', 'Subscriber Segments')}</Text>
            <Text style={{ fontSize: 11, color: C.muted, marginLeft: 'auto' }}>{segments.total_subscribers} total</Text>
          </View>
          <Text style={{ fontSize: 11, color: C.sec, marginBottom: 16 }}>{tx('admin.campaignDashboardPanel.auto.text.018', 'Auto-tagged by recency, platform activity, and feature usage. Send targeted campaigns to any segment.')}</Text>

          {/* Segment Distribution Bar */}
          <View style={{ flexDirection: 'row', height: 8, borderRadius: 4, overflow: 'hidden', marginBottom: 16 }}>
            {segments.segments.filter((s: any) => s.count > 0).map((s: any, i: number) => (
              <View key={s.id} style={{ flex: s.count, backgroundColor: s.color, opacity: 0.7 }} />
            ))}
          </View>

          {/* Segment Cards Grid */}
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10 }}>
            {segments.segments.map((seg: any) => (
              <View key={seg.id} style={{ minWidth: isWide ? 200 : '100%', flex: 1, backgroundColor: (globalThis as any).__alphaColor(seg.color, '10'), borderRadius: 12, padding: 14, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(seg.color, '20') }} {...getTestProps(`segment-card-${seg.id}`)}>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 8 }}>
                  <View style={{ width: 28, height: 28, borderRadius: 8, backgroundColor: (globalThis as any).__alphaColor(seg.color, '25'), alignItems: 'center', justifyContent: 'center' }}>
                    <Ionicons name={seg.icon} size={14} color={seg.color} />
                  </View>
                  <View style={{ flex: 1 }}>
                    <Text style={{ fontSize: 12, fontWeight: '700', color: C.text }}>{seg.label}</Text>
                    <Text style={{ fontSize: 10, color: C.muted }} numberOfLines={1}>{seg.description}</Text>
                  </View>
                </View>
                <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
                  <View>
                    <Text style={{ fontSize: 20, fontWeight: '800', color: seg.color }}>{seg.count}</Text>
                    <Text style={{ fontSize: 10, color: C.muted }}>{seg.percentage}% of list</Text>
                  </View>
                  <TouchableOpacity accessibilityLabel={tx('admin.campaignDashboardPanel.auto.accessibility.002', 'Send campaign to segment')}
                    style={{ flexDirection: 'row', alignItems: 'center', gap: 4, backgroundColor: (globalThis as any).__alphaColor(seg.color, '20'), paddingHorizontal: 10, paddingVertical: 6, borderRadius: 8, opacity: segSending === seg.id ? 0.6 : 1 }}
                    onPress={() => handleSegmentSend(seg.id)}
                    disabled={segSending === seg.id || seg.count === 0}
                    activeOpacity={0.7}
                    {...getTestProps(`segment-send-${seg.id}`)}
                  >
                    {segSending === seg.id ? (
                      <ActivityIndicator size="small" color={seg.color} />
                    ) : (
                      <>
                        <Ionicons name="send" size={11} color={seg.color} />
                        <Text style={{ fontSize: 10, fontWeight: '700', color: seg.color }}>{tx('admin.campaignDashboardPanel.auto.text.019', 'Send')}</Text>
                      </>
                    )}
                  </TouchableOpacity>
                </View>
              </View>
            ))}
          </View>
        </View>
      )}

      {/* Campaign History */}
      <View style={{ backgroundColor: C.card, borderRadius: 14, padding: 20, borderWidth: 1, borderColor: C.border, marginBottom: 20 }} {...getTestProps('campaign-history')}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 16 }}>
          <Ionicons name="time" size={16} color={C.cyan} />
          <Text style={{ fontSize: 14, fontWeight: '700', color: C.text }}>{tx('admin.campaignDashboardPanel.auto.text.020', 'Campaign History')}</Text>
          <Text style={{ fontSize: 11, color: C.muted, marginLeft: 'auto' }}>{data.campaigns?.length || 0} campaigns</Text>
        </View>

        {data.campaigns?.length > 0 ? data.campaigns.map((c: any, i: number) => {
          const sentAt = c.sent_at ? new Date(c.sent_at) : null;
          const dateStr = sentAt ? sentAt.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' }) : '';
          const successRate = c.subscriber_count > 0 ? Math.round((c.sent_count / c.subscriber_count) * 100) : 0;
          return (
            <View key={c.campaign_id || i} style={{ flexDirection: isWide ? 'row' : 'column', alignItems: isWide ? 'center' : 'flex-start', justifyContent: 'space-between', paddingVertical: 12, borderBottomWidth: i < data.campaigns.length - 1 ? 1 : 0, borderBottomColor: C.border, gap: 8 }}>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, flex: 1 }}>
                <View style={{ width: 36, height: 36, borderRadius: 10, backgroundColor: (globalThis as any).__alphaColor(C.accent, '15'), alignItems: 'center', justifyContent: 'center' }}>
                  <Ionicons name="mail" size={16} color={C.accent} />
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={{ fontSize: 13, color: C.text, fontWeight: '600' }} numberOfLines={1}>{c.month_label || 'Campaign'}</Text>
                  <Text style={{ fontSize: 11, color: C.muted }}>{dateStr}</Text>
                </View>
              </View>
              <View style={{ flexDirection: 'row', gap: 16, alignItems: 'center' }}>
                <View style={{ alignItems: 'center' }}>
                  <Text style={{ fontSize: 14, fontWeight: '700', color: C.accent }}>{c.sent_count}</Text>
                  <Text style={{ fontSize: 10, color: C.muted }}>{tx('admin.campaignDashboardPanel.auto.text.021', 'Sent')}</Text>
                </View>
                <View style={{ alignItems: 'center' }}>
                  <Text style={{ fontSize: 14, fontWeight: '700', color: c.failed_count > 0 ? C.red : C.green }}>{c.failed_count}</Text>
                  <Text style={{ fontSize: 10, color: C.muted }}>{tx('admin.campaignDashboardPanel.auto.text.022', 'Failed')}</Text>
                </View>
                <View style={{ backgroundColor: successRate === 100 ? (globalThis as any).__alphaColor(C.green, '20') : C.yellow + '20', paddingHorizontal: 10, paddingVertical: 4, borderRadius: 8 }}>
                  <Text style={{ fontSize: 11, fontWeight: '700', color: successRate === 100 ? C.green : C.yellow }}>{successRate}%</Text>
                </View>
              </View>
            </View>
          );
        }) : (
          <View style={{ alignItems: 'center', paddingVertical: 32, gap: 8 }}>
            <Ionicons name="mail-unread-outline" size={32} color={C.muted} />
            <Text style={{ fontSize: 13, color: C.muted }}>{tx('admin.campaignDashboardPanel.auto.text.023', 'No campaigns sent yet')}</Text>
            <Text style={{ fontSize: 11, color: C.sec }}>{tx('admin.campaignDashboardPanel.auto.text.024', 'The first digest will be sent automatically')}</Text>
          </View>
        )}
      </View>

      <View style={{ height: 32 }} />
    </ScrollView>
  );
}
