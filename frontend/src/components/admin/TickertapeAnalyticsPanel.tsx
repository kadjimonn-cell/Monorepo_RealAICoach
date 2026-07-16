// Tickertape CTR analytics — reads /api/admin/tickertape-analytics and
// renders per-fact impression/click/CTR bars. Answers: "which
// Welcome-page social-proof line actually earns the signup click?"
import { useTranslation } from '../../hooks/useTranslation';
import React, { useCallback, useEffect, useState } from 'react';
import { View, Text, TouchableOpacity, ActivityIndicator, ScrollView } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';

const tx = (_key: string, fallback: string) => fallback;

const C = {
  bg: 'var(--app-bg)' as any,
  bgSoft: 'var(--app-surface)' as any,
  card: 'var(--app-card-bg)' as any,
  border: 'var(--app-border)' as any,
  text: 'var(--app-text)' as any,
  textSec: 'var(--app-text-sec)' as any,
  textMuted: 'var(--app-text-muted)' as any,
  primaryText: 'rgb(255,255,255)' as any,
  error: 'var(--app-error)' as any,
  primary: 'var(--app-primary)' as any, primarySoft: 'var(--app-primary-soft)',
  accent: 'var(--app-primary)' as any, warning: 'var(--app-warning)', success: 'var(--app-success)',
};

type Row = {
  fact_testid: string;
  label: string;
  impressions: number;
  clicks: number;
  ctr_pct: number;
};

type Resp = {
  window_days: number;
  since_iso: string;
  per_fact: Row[];
  totals: { impressions: number; clicks: number; ctr_pct: number };
};

export default function TickertapeAnalyticsPanel() {
  const { t } = useTranslation();
  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };

  const [data, setData] = useState<Resp | null>(null);
  const [days, setDays] = useState(7);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState('');

  const load = useCallback(async () => {
    setLoading(true); setErr('');
    try {
      const { data } = await api.get('/admin/tickertape-analytics', { params: { days } });
      setData(data);
    } catch (e: any) {
      setErr(e?.response?.data?.detail || e?.message || 'Failed to load analytics');
    } finally { setLoading(false); }
  }, [days]);

  useEffect(() => { load(); }, [load]);

  const maxImpressions = data?.per_fact.reduce((m, r) => Math.max(m, r.impressions), 0) || 0;

  return (
    <View style={{ padding: 16, backgroundColor: C.bg, minHeight: '100%' }} data-testid="tickertape-analytics-panel" testID="tickertape-analytics-panel">
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
        <View>
          <Text style={{ color: C.text, fontSize: 20, fontWeight: '800' }}>{tx('admin.tickertapeAnalyticsPanel.auto.text.001', 'Welcome Tickertape · CTR Analytics')}</Text>
          <Text style={{ color: C.textMuted, fontSize: 11, marginTop: 2 }}>
            Which social-proof fact earns the signup click · past {data?.window_days ?? days} days
          </Text>
        </View>
        <View style={{ flexDirection: 'row', gap: 4 }}>
          {[1, 7, 30].map((d) => (
            <TouchableOpacity key={d} onPress={() => setDays(d)}
              style={{ paddingHorizontal: 10, paddingVertical: 5, borderRadius: 999, backgroundColor: days === d ? C.primary : C.bgSoft, borderColor: days === d ? C.primary : C.border, borderWidth: 1 }}
              data-testid={`tickertape-analytics-days-${d}`} testID={`tickertape-analytics-days-${d}`}
            >
              <Text style={{ color: days === d ? C.primaryText : C.textSec, fontSize: 10, fontWeight: '700' }}>{d}d</Text>
            </TouchableOpacity>
          ))}
          <TouchableOpacity onPress={load}
            style={{ flexDirection: 'row', alignItems: 'center', gap: 4, paddingHorizontal: 10, paddingVertical: 5, borderRadius: 999, backgroundColor: C.primarySoft, borderColor: C.primary, borderWidth: 1 }}
            data-testid="tickertape-analytics-refresh" testID="tickertape-analytics-refresh"
          >
            <Ionicons name="refresh" size={11} color={C.primary} />
            <Text style={{ color: C.primary, fontSize: 10, fontWeight: '700' }}>{tx('admin.tickertapeAnalyticsPanel.auto.text.002', 'Refresh')}</Text>
          </TouchableOpacity>
        </View>
      </View>

      {/* Totals */}
      <View style={{ flexDirection: 'row', gap: 8, marginBottom: 12 }}>
        {[
          { label: 'Impressions', value: data?.totals.impressions ?? 0, color: C.accent },
          { label: 'Clicks', value: data?.totals.clicks ?? 0, color: C.success },
          { label: 'Overall CTR', value: `${data?.totals.ctr_pct ?? 0}%`, color: C.warning },
        ].map((card, i) => (
          <View key={i} style={{ flex: 1, backgroundColor: C.card, borderColor: C.border, borderWidth: 1, borderRadius: 10, padding: 12 }}
            data-testid={`tickertape-analytics-total-${i}`} testID={`tickertape-analytics-total-${i}`}>
            <Text style={{ color: C.textMuted, fontSize: 10, fontWeight: '700' }}>{card.label}</Text>
            <Text style={{ color: card.color, fontSize: 22, fontWeight: '800', marginTop: 4 }}>{card.value}</Text>
          </View>
        ))}
      </View>

      {loading ? <ActivityIndicator color={C.primary} /> :
        err ? <Text style={{ color: C.error, fontSize: 11 }}>{err}</Text> :
        (
          <ScrollView>
            <View style={{ backgroundColor: C.card, borderColor: C.border, borderWidth: 1, borderRadius: 12, padding: 12 }}
              data-testid="tickertape-analytics-table" testID="tickertape-analytics-table">
              <Text style={{ color: C.text, fontSize: 13, fontWeight: '700', marginBottom: 8 }}>{tx('admin.tickertapeAnalyticsPanel.auto.text.003', 'Per-fact breakdown (ranked by clicks)')}</Text>
              {(data?.per_fact || []).map((r, i) => {
                const barPct = maxImpressions > 0 ? (r.impressions / maxImpressions) * 100 : 0;
                return (
                  <View key={r.fact_testid} style={{ marginBottom: 10 }}
                    data-testid={`tickertape-analytics-row-${r.fact_testid}`} testID={`tickertape-analytics-row-${r.fact_testid}`}>
                    <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 3 }}>
                      <Text style={{ color: C.text, fontSize: 11, fontWeight: '700' }}>
                        {i === 0 && r.clicks > 0 ? '🏆 ' : ''}{r.label}
                      </Text>
                      <Text style={{ color: C.textSec, fontSize: 10 }}>
                        <Text style={{ color: C.accent, fontWeight: '800' }}>{r.impressions.toLocaleString()}</Text> imp · <Text style={{ color: C.success, fontWeight: '800' }}>{r.clicks.toLocaleString()}</Text> clk · <Text style={{ color: C.warning, fontWeight: '800' }}>{r.ctr_pct}%</Text> CTR
                      </Text>
                    </View>
                    <View style={{ height: 6, backgroundColor: C.bgSoft, borderRadius: 4, overflow: 'hidden' }}>
                      <View style={{ width: `${barPct}%`, height: '100%', backgroundColor: r.clicks > 0 ? C.success : C.accent, opacity: 0.7 }} />
                    </View>
                  </View>
                );
              })}
              {(data?.per_fact || []).length === 0 && (
                <Text style={{ color: C.textMuted, fontSize: 11 }}>{tx('admin.tickertapeAnalyticsPanel.auto.text.004', 'No tickertape activity yet in this window.')}</Text>
              )}
            </View>
          </ScrollView>
        )
      }
    </View>
  );
}
