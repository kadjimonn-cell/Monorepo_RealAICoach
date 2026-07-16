import React, { useState } from 'react';
import { View, Text, TouchableOpacity, ActivityIndicator, Platform, Pressable } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useExecTheme} from './ExecDashboardPanels';
import api from '../../services/api';
import { useAdminTheme } from '../../hooks/useAdminTheme';
import { useTranslation } from '../../hooks/useTranslation';

// Recharts (web only)
let AreaChart: any, Area: any, XAxis: any, YAxis: any, CartesianGrid: any, Tooltip: any, ResponsiveContainer: any, Legend: any;
if (Platform.OS === 'web') {
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  const rc = require('recharts');
  AreaChart = rc.AreaChart; Area = rc.Area; XAxis = rc.XAxis; YAxis = rc.YAxis;
  CartesianGrid = rc.CartesianGrid; Tooltip = rc.Tooltip; ResponsiveContainer = rc.ResponsiveContainer; Legend = rc.Legend;
}

const RankBadge = ({ rank, prevRank }: { rank: number; prevRank: number }) => {
  const T = useExecTheme();
  const diff = prevRank - rank;
  const color = diff > 0 ? T.success : diff < 0 ? T.error : T.textMuted;
  const icon = diff > 0 ? 'caret-up' : diff < 0 ? 'caret-down' : 'remove';
  return (
    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}>
      <Text style={{ color: T.text, fontSize: 16, fontWeight: '800' }}>#{rank}</Text>
      <View style={{ flexDirection: 'row', alignItems: 'center' }}>
        <Ionicons name={icon as any} size={12} color={color} />
        {diff !== 0 && <Text style={{ color, fontSize: 10, fontWeight: '700' }}>{Math.abs(diff)}</Text>}
      </View>
    </View>
  );
};

const VolBadge = ({ vol }: { vol: string }) => {
  const T = useExecTheme();
  const colors: Record<string, string> = { high: T.success, medium: T.warning, low: T.textMuted };
  return (
    <View style={{ paddingHorizontal: 6, paddingVertical: 2, borderRadius: 6, backgroundColor: (globalThis as any).__alphaColor((colors[vol] || T.textMuted), '20') }}>
      <Text style={{ color: colors[vol] || T.textMuted, fontSize: 9, fontWeight: '700', textTransform: 'uppercase' }}>{vol}</Text>
    </View>
  );
};

interface KeywordRowProps {
  kw: any;
  isExpanded: boolean;
  isDesktop: boolean;
  onToggle: (keyword: string) => void;
  onRemove: (keyword: string) => void;
}

export function KeywordRow({ kw, isExpanded, isDesktop: d, onToggle, onRemove }: KeywordRowProps) {
  const colors = useAdminTheme();
  const T = useExecTheme();
  const { t } = useTranslation();
  const tx = React.useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);
  const [expandedTab, setExpandedTab] = useState<'results' | 'trend'>('results');
  const [trendData, setTrendData] = useState<any[]>([]);
  const [trendLoading, setTrendLoading] = useState(false);
  const topComp = kw.competitors?.[0];
  const appleTop = kw.apple?.top_results || [];
  const googleTop = kw.google?.top_results || [];

  const handleToggle = async () => {
    if (!isExpanded) {
      setTrendData([]);
      setTrendLoading(true);
      try {
        const res = await api.get(`/admin/aso-unified/keywords/${encodeURIComponent(kw.keyword)}/history`);
        setTrendData(res.data.history || []);
      } catch (e) { console.error(e); }
      finally { setTrendLoading(false); }
    }
    onToggle(kw.keyword);
  };

  return (
    <View data-testid={`keyword-row-${kw.keyword}`} testID={`keyword-row-${kw.keyword}`}>
      <TouchableOpacity onPress={handleToggle} accessibilityLabel="kw.keyword"
        style={{ flexDirection: 'row', alignItems: 'center', paddingHorizontal: 14, paddingVertical: 12, backgroundColor: T.card, borderRadius: isExpanded ? 12 : 12, borderBottomLeftRadius: isExpanded ? 0 : 12, borderBottomRightRadius: isExpanded ? 0 : 12, borderWidth: 1, borderColor: isExpanded ? (globalThis as any).__alphaColor(T.primary, '40') : T.border, borderBottomWidth: isExpanded ? 0 : 1 }}>
        <View style={{ flex: 2 }}>
          <Text style={{ color: T.text, fontSize: 13, fontWeight: '700' }}>{kw.keyword}</Text>
          <View style={{ flexDirection: 'row', gap: 4, alignItems: 'center', marginTop: 2 }}>
            <VolBadge vol={kw.apple?.search_volume || 'low'} />
            {kw.data_source === 'live' && (
              <View style={{ paddingHorizontal: 4, paddingVertical: 1, borderRadius: 3, backgroundColor: (globalThis as any).__alphaColor(colors.success, '15') }}>
                <Text style={{ color: colors.successText, fontSize: 7, fontWeight: '700' }}>{tx('admin.keywordRow.badges.live', 'LIVE')}</Text>
              </View>
            )}
          </View>
        </View>
        <View style={{ flex: 1, alignItems: 'center' }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}>
            <Ionicons name="logo-apple" size={12} color="var(--app-primary)" />
            {kw.apple?.rank ? <RankBadge rank={kw.apple.rank} prevRank={kw.apple?.prev_rank || 0} /> : <Text style={{ color: T.textMuted, fontSize: 11 }}>{tx('admin.keywordRow.labels.notRanked', 'N/R')}</Text>}
          </View>
        </View>
        <View style={{ flex: 1, alignItems: 'center' }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}>
            <Ionicons name="logo-google" size={12} color="var(--app-success)" />
            {kw.google?.rank ? <RankBadge rank={kw.google.rank} prevRank={kw.google?.prev_rank || 0} /> : <Text style={{ color: T.textMuted, fontSize: 11 }}>{tx('admin.keywordRow.labels.notRanked', 'N/R')}</Text>}
          </View>
        </View>
        {d && (
          <View style={{ flex: 1, alignItems: 'center' }}>
            <View style={{ height: 4, width: '80%', borderRadius: 2, backgroundColor: T.border }}>
              <View style={{ height: 4, borderRadius: 2, width: `${Math.min(100, kw.apple?.difficulty || 0)}%`, backgroundColor: (kw.apple?.difficulty || 0) > 70 ? T.error : (kw.apple?.difficulty || 0) > 40 ? T.warning : T.success }} />
            </View>
            <Text style={{ color: T.textMuted, fontSize: 9, marginTop: 3 }}>{kw.apple?.difficulty || 0}/100</Text>
          </View>
        )}
        {d && topComp && (
          <View style={{ flex: 1.5, alignItems: 'center' }}>
            <Text style={{ color: T.textSec, fontSize: 11, fontWeight: '600' }}>{topComp.name}</Text>
            <Text style={{ color: T.textMuted, fontSize: 9 }}>
              {topComp.apple_rank ? `#${topComp.apple_rank}` : 'N/R'} / {topComp.google_rank ? `#${topComp.google_rank}` : 'N/R'}
            </Text>
          </View>
        )}
        <View style={{ width: 50, flexDirection: 'row', alignItems: 'center', gap: 4 }}>
          <Ionicons name={isExpanded ? 'chevron-up' : 'chevron-down'} size={12} color={T.textMuted} />
          <TouchableOpacity onPress={() => onRemove(kw.keyword)} data-testid={`keyword-delete-${kw.keyword}`} testID={`keyword-delete-${kw.keyword}`}>
            <Ionicons name="trash-outline" size={14} color={T.error} />
          </TouchableOpacity>
        </View>
      </TouchableOpacity>

      {/* Expanded Content */}
      {isExpanded && (
        <View style={{ backgroundColor: T.card, borderWidth: 1, borderTopWidth: 0, borderColor: (globalThis as any).__alphaColor(T.primary, '40'), borderBottomLeftRadius: 12, borderBottomRightRadius: 12, padding: 14 }}
          data-testid={`keyword-details-${kw.keyword}`} testID={`keyword-details-${kw.keyword}`}>
          {/* Tab Bar */}
          <View style={{ flexDirection: 'row', gap: 4, marginBottom: 14, borderBottomWidth: 1, borderBottomColor: (globalThis as any).__alphaColor(T.border, '50'), paddingBottom: 8 }}>
            {(['results', 'trend'] as const).map(tab => (
              <Pressable key={tab} onPress={() => setExpandedTab(tab)} accessibilityRole="button" testID={`keyword-tab-${tab}`}
                style={{ paddingHorizontal: 14, paddingVertical: 6, borderRadius: 8, backgroundColor: expandedTab === tab ? (globalThis as any).__alphaColor(T.primary, '15') : 'transparent', borderWidth: 1, borderColor: expandedTab === tab ? (globalThis as any).__alphaColor(T.primary, '30') : 'transparent', cursor: 'pointer' } as any}>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 5 }}>
                  <Ionicons name={tab === 'results' ? 'list' : 'trending-up'} size={13} color={expandedTab === tab ? T.primary : T.textMuted} />
                  <Text style={{ color: expandedTab === tab ? T.primary : T.textMuted, fontSize: 11, fontWeight: '700' }}>{tab === 'results' ? 'Search Results' : 'Ranking Trend'}</Text>
                </View>
              </Pressable>
            ))}
          </View>

          {/* Results Tab */}
          {expandedTab === 'results' && (appleTop.length > 0 || googleTop.length > 0) && (
            <View style={{ flexDirection: d ? 'row' : 'column', gap: 12 }}>
              {appleTop.length > 0 && (
                <View style={{ flex: 1 }}>
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 8 }}>
                    <Ionicons name="logo-apple" size={14} color="var(--app-primary)" />
                    <Text style={{ color: T.text, fontSize: 12, fontWeight: '700' }}>{tx('admin.keywordRow.results.appStoreTop', 'App Store Top Results')}</Text>
                    <Text style={{ color: T.textMuted, fontSize: 9 }}>({kw.apple?.total_results || 0} total)</Text>
                  </View>
                  {appleTop.map((app: any, j: number) => (
                    <View key={j} style={{ flexDirection: 'row', alignItems: 'center', paddingVertical: 6, borderBottomWidth: j < appleTop.length - 1 ? 1 : 0, borderBottomColor: (globalThis as any).__alphaColor(T.border, '50'), gap: 8 }}>
                      <Text style={{ color: T.textMuted, fontSize: 10, fontWeight: '800', width: 20 }}>#{app.rank}</Text>
                      <View style={{ flex: 1 }}>
                        <Text style={{ color: T.text, fontSize: 11, fontWeight: '600' }} numberOfLines={1}>{app.name}</Text>
                        <Text style={{ color: T.textMuted, fontSize: 9 }}>{app.developer}</Text>
                      </View>
                      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 2 }}>
                        <Ionicons name="star" size={9} color={'var(--app-warning)'} />
                        <Text style={{ color: T.textSec, fontSize: 10, fontWeight: '600' }}>{app.rating || '—'}</Text>
                      </View>
                    </View>
                  ))}
                </View>
              )}
              {googleTop.length > 0 && (
                <View style={{ flex: 1 }}>
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 8 }}>
                    <Ionicons name="logo-google" size={14} color="var(--app-success)" />
                    <Text style={{ color: T.text, fontSize: 12, fontWeight: '700' }}>{tx('admin.keywordRow.results.googlePlayTop', 'Google Play Top Results')}</Text>
                    <Text style={{ color: T.textMuted, fontSize: 9 }}>({kw.google?.total_results || 0} total)</Text>
                  </View>
                  {googleTop.map((app: any, j: number) => (
                    <View key={j} style={{ flexDirection: 'row', alignItems: 'center', paddingVertical: 6, borderBottomWidth: j < googleTop.length - 1 ? 1 : 0, borderBottomColor: (globalThis as any).__alphaColor(T.border, '50'), gap: 8 }}>
                      <Text style={{ color: T.textMuted, fontSize: 10, fontWeight: '800', width: 20 }}>#{app.rank}</Text>
                      <View style={{ flex: 1 }}>
                        <Text style={{ color: T.text, fontSize: 11, fontWeight: '600' }} numberOfLines={1}>{app.name}</Text>
                        <Text style={{ color: T.textMuted, fontSize: 9 }}>{app.developer}</Text>
                      </View>
                      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 2 }}>
                        <Ionicons name="star" size={9} color={'var(--app-warning)'} />
                        <Text style={{ color: T.textSec, fontSize: 10, fontWeight: '600' }}>{app.rating || '—'}</Text>
                      </View>
                    </View>
                  ))}
                </View>
              )}
            </View>
          )}
          {expandedTab === 'results' && appleTop.length === 0 && googleTop.length === 0 && (
            <View style={{ padding: 20, alignItems: 'center' }}>
              <Text style={{ color: T.textMuted, fontSize: 12 }}>{tx('admin.keywordRow.results.empty', 'No search results cached. Refresh to fetch live data.')}</Text>
            </View>
          )}

          {/* Trend Tab */}
          {expandedTab === 'trend' && (
            <View data-testid={`keyword-trend-${kw.keyword}`} testID={`keyword-trend-${kw.keyword}`}>
              {trendLoading ? (
                <View style={{ padding: 30, alignItems: 'center' }}>
                  <ActivityIndicator size="small" color={T.primary} />
                  <Text style={{ color: T.textMuted, fontSize: 11, marginTop: 8 }}>{tx('admin.keywordRow.trend.loading', 'Loading trend data...')}</Text>
                </View>
              ) : trendData.length >= 2 && Platform.OS === 'web' ? (
                <View>
                  <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
                    <Text style={{ color: T.text, fontSize: 12, fontWeight: '700' }}>{tx('admin.keywordRow.trend.title', 'Ranking Position Over Time')}</Text>
                    <Text style={{ color: T.textMuted, fontSize: 9 }}>{trendData.length} data points (lower is better)</Text>
                  </View>
                  <View style={{ height: 220, width: '100%' }}>
                    <ResponsiveContainer width="100%" height="100%">
                      <AreaChart data={trendData.map((p: any) => ({
                        date: p.date,
                        apple: p.apple_rank || null,
                        google: p.google_rank || null,
                        difficulty: p.apple_difficulty || 0,
                      }))}>
                        <defs>
                          <linearGradient id="appleGrad" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="5%" stopColor="var(--app-primary)" stopOpacity={0.3} />
                            <stop offset="95%" stopColor="var(--app-primary)" stopOpacity={0} />
                          </linearGradient>
                          <linearGradient id="googleGrad" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="5%" stopColor="var(--app-success)" stopOpacity={0.3} />
                            <stop offset="95%" stopColor="var(--app-success)" stopOpacity={0} />
                          </linearGradient>
                        </defs>
                        <CartesianGrid strokeDasharray="3 3" stroke={T.border + '40'} />
                        <XAxis dataKey="date" tick={{ fill: T.textMuted, fontSize: 9 }} tickLine={false} axisLine={{ stroke: T.border + '40' }} />
                        <YAxis reversed tick={{ fill: T.textMuted, fontSize: 9 }} tickLine={false} axisLine={{ stroke: T.border + '40' }} label={{ value: 'Rank', angle: -90, position: 'insideLeft', fill: T.textMuted, fontSize: 9 }} />
                        <Tooltip
                          contentStyle={{ backgroundColor: T.card, border: `1px solid ${T.border}`, borderRadius: 8, fontSize: 11 }}
                          labelStyle={{ color: T.text, fontWeight: '700' }}
                          formatter={(value: number, name: string) => [value ? `#${value}` : 'N/R', name === 'apple' ? 'App Store' : 'Google Play']}
                        />
                        <Legend wrapperStyle={{ fontSize: 10, color: T.textMuted }} formatter={(value: string) => value === 'apple' ? 'App Store' : 'Google Play'} />
                        <Area type="monotone" dataKey="apple" stroke="var(--app-primary)" strokeWidth={2} fill="url(#appleGrad)" dot={{ r: 3, fill: 'var(--app-primary)' }} connectNulls />
                        <Area type="monotone" dataKey="google" stroke="var(--app-success)" strokeWidth={2} fill="url(#googleGrad)" dot={{ r: 3, fill: 'var(--app-success)' }} connectNulls />
                      </AreaChart>
                    </ResponsiveContainer>
                  </View>
                </View>
              ) : (
                <View style={{ padding: 24, alignItems: 'center', backgroundColor: T.bg, borderRadius: 10, borderWidth: 1, borderColor: T.border }}>
                  <Ionicons name="trending-up-outline" size={28} color={T.textMuted} />
                  <Text style={{ color: T.textSec, fontSize: 12, fontWeight: '600', marginTop: 8 }}>{tx('admin.keywordRow.trend.notEnoughData', 'Not enough data for trend chart')}</Text>
                  <Text style={{ color: T.textMuted, fontSize: 10, marginTop: 4, textAlign: 'center' }}>
                    {trendData.length === 0
                      ? 'Rankings are auto-refreshed daily at 6 AM UTC. Check back tomorrow for your first data point.'
                      : `${trendData.length} data point${trendData.length > 1 ? 's' : ''} collected. Need at least 2 for a trend line.`}
                  </Text>
                </View>
              )}
            </View>
          )}
        </View>
      )}
    </View>
  );
}
