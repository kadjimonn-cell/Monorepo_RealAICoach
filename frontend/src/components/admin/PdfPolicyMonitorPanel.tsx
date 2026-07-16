import { useTranslation } from '../../hooks/useTranslation';
import React, { useCallback, useEffect, useState } from 'react';
import { View, Text, TouchableOpacity, ScrollView, ActivityIndicator } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import api from '../../services/api';
import { useTheme } from '../../context/ThemeContext';

type PdfOverview = {
  policy?: { target_pdf_version?: string; enabled?: boolean };
  window_hours?: number;
  generated_at?: string;
  totals?: { total?: number; already_v14?: number; normalized?: number; passthrough_error?: number; non_pdf?: number };
  top_endpoints?: Array<{
    route_path: string;
    method: string;
    total: number;
    mode_counts?: { already_v14?: number; normalized?: number; passthrough_error?: number; non_pdf?: number };
    last_seen_at?: string;
    last_mode?: string;
    last_status?: number;
  }>;
};

const tx = (_key: string, fallback: string) => fallback;

const MetricCard = ({ label, value, tone, valueColor }: { label: string; value: number | string; tone: string; valueColor: string }) => (
  <View
    style={{ borderWidth: 1, borderColor: `${tone}55`, backgroundColor: `${tone}15`, borderRadius: 10, padding: 10, minWidth: 120 }}
    data-testid={`pdf-policy-metric-${label.toLowerCase().replace(/\s+/g, '-')}`}
    testID={`pdf-policy-metric-${label.toLowerCase().replace(/\s+/g, '-')}`}
  >
    <Text style={{ color: tone, fontSize: 11, fontWeight: '800', textTransform: 'uppercase' }}>{label}</Text>
    <Text style={{ color: valueColor, fontSize: 22, fontWeight: '900', marginTop: 4 }}>{value}</Text>
  </View>
);

export default function PdfPolicyMonitorPanel() {
  const { t } = useTranslation();
  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };

  const { colors } = useTheme();
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState('');
  const [data, setData] = useState<PdfOverview | null>(null);

  const C = {
    bg: colors.bgSoft,
    card: colors.card,
    text: colors.text,
    textSec: colors.textMuted,
    border: colors.border,
    cyan: colors.info,
    teal: colors.primary,
    green: colors.success,
    amber: colors.warning,
    rose: colors.error,
  };

  const load = useCallback(async (isRefresh = false) => {
    setError('');
    if (isRefresh) setRefreshing(true); else setLoading(true);
    try {
      const res = await api.get('/admin/pdf-policy/overview?hours=24&limit=20');
      setData(res.data || null);
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Failed to load PDF policy metrics.');
    } finally {
      setRefreshing(false);
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(false); }, [load]);

  if (loading) {
    return (
      <View style={{ padding: 20, alignItems: 'center' }} data-testid="pdf-policy-monitor-loading" testID="pdf-policy-monitor-loading">
        <ActivityIndicator size="large" color={C.teal} />
        <Text style={{ color: C.textSec, marginTop: 8 }}>{tx('admin.pdfPolicyMonitorPanel.auto.text.001', 'Loading PDF policy monitor…')}</Text>
      </View>
    );
  }

  const totals = data?.totals || {};
  const endpoints = data?.top_endpoints || [];

  return (
    <View style={{ backgroundColor: C.bg, padding: 12 }} data-testid="pdf-policy-monitor-panel" testID="pdf-policy-monitor-panel">
      <View style={{ backgroundColor: C.card, borderWidth: 1, borderColor: C.border, borderRadius: 14, padding: 14 }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
          <View>
            <Text style={{ color: C.text, fontSize: 18, fontWeight: '900' }} data-testid="pdf-policy-monitor-title" testID="pdf-policy-monitor-title">{tx('admin.pdfPolicyMonitorPanel.auto.text.002', 'PDF Policy Monitor')}</Text>
            <Text style={{ color: C.textSec, fontSize: 12 }} data-testid="pdf-policy-monitor-subtitle" testID="pdf-policy-monitor-subtitle">
              Target version: {data?.policy?.target_pdf_version || '1.4'} · Window: {data?.window_hours || 24}h
            </Text>
          </View>
          <TouchableOpacity
            onPress={() => void load(true)}
            disabled={refreshing}
            style={{ paddingHorizontal: 12, paddingVertical: 8, borderRadius: 10, borderWidth: 1, borderColor: C.border, backgroundColor: colors.bgSoft }}
            data-testid="pdf-policy-refresh-button"
            testID="pdf-policy-refresh-button"
          >
            <Text style={{ color: C.text, fontWeight: '800', fontSize: 12 }}>{refreshing ? 'Refreshing…' : 'Refresh'}</Text>
          </TouchableOpacity>
        </View>

        {!!error && (
          <View style={{ borderWidth: 1, borderColor: `${C.rose}55`, backgroundColor: `${C.rose}15`, borderRadius: 10, padding: 10, marginBottom: 12 }} data-testid="pdf-policy-error-banner" testID="pdf-policy-error-banner">
            <Text style={{ color: C.rose, fontSize: 12, fontWeight: '700' }}>{error}</Text>
          </View>
        )}

        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 8, paddingBottom: 12 }} data-testid="pdf-policy-metrics-row" testID="pdf-policy-metrics-row">
          <MetricCard label="Total" value={Number(totals.total || 0)} tone={C.cyan} valueColor={C.text} />
          <MetricCard label="Already v1.4" value={Number(totals.already_v14 || 0)} tone={C.green} valueColor={C.text} />
          <MetricCard label="Normalized" value={Number(totals.normalized || 0)} tone={C.teal} valueColor={C.text} />
          <MetricCard label="Errors" value={Number(totals.passthrough_error || 0)} tone={C.amber} valueColor={C.text} />
        </ScrollView>

        <Text style={{ color: C.text, fontSize: 13, fontWeight: '800', marginBottom: 8 }} data-testid="pdf-policy-top-endpoints-title" testID="pdf-policy-top-endpoints-title">{tx('admin.pdfPolicyMonitorPanel.auto.text.003', 'Top Endpoints')}</Text>

        {endpoints.length === 0 ? (
          <Text style={{ color: C.textSec, fontSize: 12 }} data-testid="pdf-policy-no-data" testID="pdf-policy-no-data">{tx('admin.pdfPolicyMonitorPanel.auto.text.004', 'No PDF telemetry yet.')}</Text>
        ) : (
          <View style={{ gap: 8 }} data-testid="pdf-policy-top-endpoints-list" testID="pdf-policy-top-endpoints-list">
            {endpoints.slice(0, 12).map((ep, idx) => (
              <View key={`${ep.method}-${ep.route_path}-${idx}`} style={{ borderWidth: 1, borderColor: C.border, borderRadius: 10, padding: 10, backgroundColor: colors.bgSoft }} data-testid={`pdf-policy-endpoint-row-${idx}`} testID={`pdf-policy-endpoint-row-${idx}`}>
                <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
                  <Text style={{ color: C.text, fontSize: 12, fontWeight: '700', flex: 1 }} numberOfLines={1}>{ep.method} {ep.route_path}</Text>
                  <Text style={{ color: C.textSec, fontSize: 11, fontWeight: '700' }}>#{ep.total}</Text>
                </View>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, marginTop: 6 }}>
                  <Text style={{ color: C.green, fontSize: 11 }}>v1.4: {Number(ep.mode_counts?.already_v14 || 0)}</Text>
                  <Text style={{ color: C.teal, fontSize: 11 }}>normalized: {Number(ep.mode_counts?.normalized || 0)}</Text>
                  <Text style={{ color: C.amber, fontSize: 11 }}>errors: {Number(ep.mode_counts?.passthrough_error || 0)}</Text>
                </View>
                <Text style={{ color: C.textSec, fontSize: 10, marginTop: 4 }}>
                  Last mode: {ep.last_mode || '—'} · Status: {ep.last_status || 0}
                </Text>
              </View>
            ))}
          </View>
        )}

        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginTop: 12 }}>
          <Ionicons name="shield-checkmark" size={14} color={C.teal} />
          <Text style={{ color: C.textSec, fontSize: 11 }} data-testid="pdf-policy-governance-note" testID="pdf-policy-governance-note">{tx('admin.pdfPolicyMonitorPanel.auto.text.005', 'CI gate active: PDF responses must carry policy headers and resolve to PDF 1.4.')}</Text>
        </View>
      </View>
    </View>
  );
}
