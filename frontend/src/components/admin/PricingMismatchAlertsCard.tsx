import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { ActivityIndicator, Platform, Pressable, ScrollView, Text, View } from 'react-native';

import api from '../../services/api';
import { useTheme } from '../../context/ThemeContext';
import { useTranslation } from '../../hooks/useTranslation';

type PricingMismatchEvent = {
  event_id: string;
  status: 'open' | 'acknowledged' | string;
  context: string;
  reason: string;
  plan_id: string;
  billing_period: string;
  expected_amount: number;
  actual_amount: number;
  payment_id: string;
  created_at?: string;
  acked_at?: string;
};

type PricingMismatchResponse = {
  summary?: {
    total_recent?: number;
    open_recent?: number;
    acknowledged_recent?: number;
  };
  events?: PricingMismatchEvent[];
};

export default function PricingMismatchAlertsCard() {
  const { darkMode, colors } = useTheme();
  const { t } = useTranslation();
  const tx = useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [busyAction, setBusyAction] = useState('');
  const [onlyOpen, setOnlyOpen] = useState(true);
  const [error, setError] = useState('');
  const [payload, setPayload] = useState<PricingMismatchResponse | null>(null);

  const cardBg = darkMode ? colors.cardMuted : colors.card;
  const innerBg = darkMode ? colors.card : colors.bgSoft;
  const border = colors.border;
  const text = colors.text;
  const subtext = colors.textMuted;

  const summary = payload?.summary || {};
  const events = payload?.events || [];

  const load = useCallback(async (isRefresh = false) => {
    setError('');
    if (isRefresh) {
      setRefreshing(true);
    } else {
      setLoading(true);
    }
    try {
      const res = await api.get('/admin/pricing-mismatch-alerts', {
        params: { hours: 168, limit: 25, only_open: onlyOpen },
      });
      setPayload(res.data || null);
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Failed to load pricing mismatch alerts.');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [onlyOpen]);

  useEffect(() => {
    void load(false);
  }, [load]);

  const confirmAction = useCallback((message: string) => {
    if (Platform.OS === 'web' && typeof window !== 'undefined' && typeof window.confirm === 'function') {
      return window.confirm(message);
    }
    return true;
  }, []);

  const runAction = useCallback(async (actionId: string, fn: () => Promise<void>) => {
    setBusyAction(actionId);
    setError('');
    try {
      await fn();
      await load(true);
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Action failed for pricing mismatch alerts.');
    } finally {
      setBusyAction('');
    }
  }, [load]);

  const headerSubtitle = useMemo(() => {
    const openCount = Number(summary.open_recent || 0);
    const ackCount = Number(summary.acknowledged_recent || 0);
    return `${openCount} open · ${ackCount} acknowledged`;
  }, [summary]);

  if (loading) {
    return (
      <View style={{ backgroundColor: cardBg, borderRadius: 12, borderWidth: 1, borderColor: border, padding: 16, marginBottom: 16 }} data-testid="pricing-mismatch-card-loading" testID="pricing-mismatch-card-loading">
        <ActivityIndicator size="small" color={colors.warning} />
        <Text style={{ color: subtext, fontSize: 12, marginTop: 8 }} data-testid="pricing-mismatch-card-loading-text" testID="pricing-mismatch-card-loading-text">{tx('admin.pricingMismatchAlerts.states.loading', 'Loading pricing mismatch monitor...')}</Text>
      </View>
    );
  }

  return (
    <View style={{ backgroundColor: cardBg, borderRadius: 12, borderWidth: 1, borderColor: border, marginBottom: 16 }} data-testid="pricing-mismatch-card" testID="pricing-mismatch-card">
      <View style={{ padding: 14, borderBottomWidth: 1, borderBottomColor: border, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8, flexWrap: 'wrap' }}>
        <View>
          <Text style={{ fontSize: 14, fontWeight: '700', color: text }} data-testid="pricing-mismatch-card-title" testID="pricing-mismatch-card-title">{tx('admin.pricingMismatchAlerts.header.title', 'Pricing Mismatch Alerts')}</Text>
          <Text style={{ fontSize: 11, color: subtext, marginTop: 4 }} data-testid="pricing-mismatch-card-subtitle" testID="pricing-mismatch-card-subtitle">{headerSubtitle}</Text>
        </View>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
          <Pressable
            onPress={() => setOnlyOpen((prev) => !prev)}
            style={{ paddingHorizontal: 10, paddingVertical: 7, borderRadius: 8, borderWidth: 1, borderColor: onlyOpen ? colors.warning : border, backgroundColor: onlyOpen ? colors.warningSoft : innerBg }}
            data-testid="pricing-mismatch-toggle-open"
            testID="pricing-mismatch-toggle-open"
          >
            <Text style={{ fontSize: 11, color: onlyOpen ? colors.warning : subtext, fontWeight: '700' }}>{onlyOpen ? 'Open only' : 'Show all'}</Text>
          </Pressable>
          <Pressable
            onPress={() => void load(true)}
            disabled={refreshing || !!busyAction}
            style={{ paddingHorizontal: 10, paddingVertical: 7, borderRadius: 8, borderWidth: 1, borderColor: border, backgroundColor: innerBg }}
            data-testid="pricing-mismatch-refresh"
            testID="pricing-mismatch-refresh"
          >
            <Text style={{ fontSize: 11, color: text, fontWeight: '700' }}>{refreshing ? 'Refreshing...' : 'Refresh'}</Text>
          </Pressable>
        </View>
      </View>

      <View style={{ padding: 14 }}>
        {error ? (
          <View style={{ marginBottom: 12, borderWidth: 1, borderColor: colors.error, borderRadius: 8, backgroundColor: colors.errorSoft, padding: 10 }} data-testid="pricing-mismatch-error" testID="pricing-mismatch-error">
            <Text style={{ color: colors.errorText, fontSize: 11, fontWeight: '700' }}>{error}</Text>
          </View>
        ) : null}

        <View style={{ flexDirection: 'row', gap: 10, flexWrap: 'wrap', marginBottom: 12 }} data-testid="pricing-mismatch-summary-row" testID="pricing-mismatch-summary-row">
          {[
            { id: 'total', label: 'Total (7d)', value: Number(summary.total_recent || 0), tone: colors.info },
            { id: 'open', label: 'Open', value: Number(summary.open_recent || 0), tone: colors.warningText },
            { id: 'ack', label: 'Acknowledged', value: Number(summary.acknowledged_recent || 0), tone: colors.successText },
          ].map((item) => (
            <View key={item.id} style={{ flex: 1, minWidth: 110, borderWidth: 1, borderColor: border, borderRadius: 10, backgroundColor: innerBg, padding: 10 }} data-testid={`pricing-mismatch-summary-${item.id}`} testID={`pricing-mismatch-summary-${item.id}`}>
              <Text style={{ color: subtext, fontSize: 10, fontWeight: '700', textTransform: 'uppercase' }}>{item.label}</Text>
              <Text style={{ color: item.tone, fontSize: 20, fontWeight: '800', marginTop: 4 }} data-testid={`pricing-mismatch-summary-value-${item.id}`} testID={`pricing-mismatch-summary-value-${item.id}`}>{item.value}</Text>
            </View>
          ))}
        </View>

        <View style={{ flexDirection: 'row', gap: 8, flexWrap: 'wrap', marginBottom: 10 }}>
          <Pressable accessibilityLabel="Pricing mismatch ack all button"
            onPress={() => void runAction('ack-all', async () => {
              await api.post('/admin/pricing-mismatch-alerts/ack-all', null, { params: { hours: 168 } });
            })}
            disabled={!!busyAction}
            style={{ paddingHorizontal: 12, paddingVertical: 8, borderRadius: 8, backgroundColor: colors.successSoft, borderWidth: 1, borderColor: colors.success }}
            data-testid="pricing-mismatch-ack-all"
            testID="pricing-mismatch-ack-all"
          >
            <Text style={{ fontSize: 11, fontWeight: '700', color: colors.successText }}>{busyAction === 'ack-all' ? 'Acknowledging...' : 'Acknowledge Open'}</Text>
          </Pressable>
          <Pressable accessibilityLabel="Pricing mismatch clear acked button"
            onPress={() => {
              if (!confirmAction('Clear acknowledged pricing mismatch records from the last 30 days?')) return;
              void runAction('clear-acked', async () => {
                await api.post('/admin/pricing-mismatch-alerts/clear', null, { params: { scope: 'acked', hours: 720 } });
              });
            }}
            disabled={!!busyAction}
            style={{ paddingHorizontal: 12, paddingVertical: 8, borderRadius: 8, backgroundColor: colors.warningSoft, borderWidth: 1, borderColor: colors.warning }}
            data-testid="pricing-mismatch-clear-acked"
            testID="pricing-mismatch-clear-acked"
          >
            <Text style={{ fontSize: 11, fontWeight: '700', color: colors.warningText }}>{busyAction === 'clear-acked' ? 'Clearing...' : 'Clear Acked'}</Text>
          </Pressable>
          <Pressable accessibilityLabel="Pricing mismatch clear all button"
            onPress={() => {
              if (!confirmAction('This will permanently clear all recent pricing mismatch records. Continue?')) return;
              void runAction('clear-all', async () => {
                await api.post('/admin/pricing-mismatch-alerts/clear', null, { params: { scope: 'all', hours: 720 } });
              });
            }}
            disabled={!!busyAction}
            style={{ paddingHorizontal: 12, paddingVertical: 8, borderRadius: 8, backgroundColor: colors.errorSoft, borderWidth: 1, borderColor: colors.error }}
            data-testid="pricing-mismatch-clear-all"
            testID="pricing-mismatch-clear-all"
          >
            <Text style={{ fontSize: 11, fontWeight: '700', color: colors.error }}>{busyAction === 'clear-all' ? 'Clearing...' : 'Clear All'}</Text>
          </Pressable>
        </View>

        {events.length === 0 ? (
          <Text style={{ color: subtext, fontSize: 11 }} data-testid="pricing-mismatch-empty" testID="pricing-mismatch-empty">{tx('admin.pricingMismatchAlerts.states.empty', 'No pricing mismatch alerts found in this window.')}</Text>
        ) : (
          <ScrollView style={{ maxHeight: 280 }} contentContainerStyle={{ gap: 8 }} data-testid="pricing-mismatch-list" testID="pricing-mismatch-list">
            {events.map((event, idx) => {
              const isOpen = String(event.status).toLowerCase() !== 'acknowledged';
              return (
                <View key={`${event.event_id}-${idx}`} style={{ borderWidth: 1, borderColor: border, borderRadius: 10, backgroundColor: innerBg, padding: 10 }} data-testid={`pricing-mismatch-row-${idx}`} testID={`pricing-mismatch-row-${idx}`}>
                  <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 8, marginBottom: 6 }}>
                    <Text style={{ color: text, fontSize: 12, fontWeight: '700', flex: 1 }} numberOfLines={1} data-testid={`pricing-mismatch-row-title-${idx}`} testID={`pricing-mismatch-row-title-${idx}`}>
                      {event.plan_id?.toUpperCase()} {event.billing_period} · {event.context}
                    </Text>
                    <View style={{ paddingHorizontal: 8, paddingVertical: 3, borderRadius: 999, backgroundColor: isOpen ? colors.warningSoft : colors.successSoft }} data-testid={`pricing-mismatch-row-status-pill-${idx}`} testID={`pricing-mismatch-row-status-pill-${idx}`}>
                      <Text style={{ fontSize: 10, fontWeight: '800', color: isOpen ? colors.warningText : colors.successText }}>{isOpen ? 'OPEN' : 'ACK'}</Text>
                    </View>
                  </View>
                  <Text style={{ color: subtext, fontSize: 11 }} data-testid={`pricing-mismatch-row-reason-${idx}`} testID={`pricing-mismatch-row-reason-${idx}`}>
                    {event.reason} · expected ${Number(event.expected_amount || 0).toFixed(2)} vs actual ${Number(event.actual_amount || 0).toFixed(2)}
                  </Text>
                  <Text style={{ color: subtext, fontSize: 10, marginTop: 4 }} data-testid={`pricing-mismatch-row-meta-${idx}`} testID={`pricing-mismatch-row-meta-${idx}`}>
                    payment: {event.payment_id || 'n/a'} · {event.created_at || 'n/a'}
                  </Text>
                  {isOpen ? (
                    <Pressable accessibilityLabel="Run action in pricing mismatch alerts card"
                      onPress={() => void runAction(`ack-${event.event_id}`, async () => {
                        await api.post(`/admin/pricing-mismatch-alerts/${event.event_id}/ack`);
                      })}
                      disabled={!!busyAction}
                      style={{ marginTop: 8, alignSelf: 'flex-start', paddingHorizontal: 10, paddingVertical: 7, borderRadius: 8, borderWidth: 1, borderColor: colors.success, backgroundColor: colors.successSoft }}
                      data-testid={`pricing-mismatch-row-ack-${idx}`}
                      testID={`pricing-mismatch-row-ack-${idx}`}
                    >
                      <Text style={{ fontSize: 10, fontWeight: '800', color: colors.successText }}>{busyAction === `ack-${event.event_id}` ? 'Saving...' : 'Acknowledge'}</Text>
                    </Pressable>
                  ) : (
                    <Text style={{ color: subtext, fontSize: 10, marginTop: 6 }} data-testid={`pricing-mismatch-row-acked-at-${idx}`} testID={`pricing-mismatch-row-acked-at-${idx}`}>
                      acknowledged at {event.acked_at || 'n/a'}
                    </Text>
                  )}
                </View>
              );
            })}
          </ScrollView>
        )}
      </View>
    </View>
  );
}
