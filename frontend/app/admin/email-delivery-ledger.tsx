import React, { useEffect, useMemo, useState } from 'react';
import { View, Text, ScrollView, TouchableOpacity, TextInput, ActivityIndicator, Alert, useWindowDimensions } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import AppShell from '../../src/components/AppShell';
import { useAuth } from '../../src/context/AuthContext';
import { useTheme } from '../../src/context/ThemeContext';
import api from '../../src/services/api';
import { hasAdminConsoleVisibility } from '../../src/utils/adminAccess';
import { AdminRouteGate } from '../../src/components/auth/AdminRouteGate';

type LedgerEntry = {
  timestamp?: string;
  recipient?: string;
  template_key?: string;
  idempotency_key?: string | null;
  dedupe_seed?: string | null;
  status?: string;
  email_id?: string | null;
  subject?: string | null;
  sent_at?: string | null;
  source?: string;
  anomaly_level?: string;
  anomaly_flags?: string[];
};

type LedgerAnomalies = {
  duplicate_idempotency_keys: Array<{ idempotency_key?: string; count?: number }>;
  high_volume_recipient_templates: Array<{ recipient?: string; template_key?: string; send_count?: number }>;
  total_flagged_rows: number;
};

export default function EmailDeliveryLedgerPage() {
  const router = useRouter();
  const { user } = useAuth();
  const { colors } = useTheme();
  const { width } = useWindowDimensions();
  const isCompact = width < 768;
  const isAdmin = hasAdminConsoleVisibility(user as any);

  const [recipient, setRecipient] = useState('');
  const [event, setEvent] = useState('');
  const [idempotency, setIdempotency] = useState('');
  const [limit, setLimit] = useState('100');
  const [loading, setLoading] = useState(false);
  const [rows, setRows] = useState<LedgerEntry[]>([]);
  const [summary, setSummary] = useState({ idempotency_matches: 0, send_matches: 0 });
  const [anomalyMode, setAnomalyMode] = useState(false);
  const [anomalyWindowHours, setAnomalyWindowHours] = useState('24');
  const [anomalyVolumeThreshold, setAnomalyVolumeThreshold] = useState('5');
  const [anomalies, setAnomalies] = useState<LedgerAnomalies>({
    duplicate_idempotency_keys: [],
    high_volume_recipient_templates: [],
    total_flagged_rows: 0,
  });

  const C = useMemo(() => ({
    bg: colors.bg,
    card: colors.card,
    border: colors.border,
    text: colors.text,
    muted: colors.textMuted,
    primary: colors.primary,
    primaryText: colors.primaryText || colors.buttonText || colors.text,
    success: colors.success,
    warning: colors.warning,
    error: colors.error,
  }), [colors]);

  const loadLedger = async () => {
    if (!isAdmin) return;
    setLoading(true);
    try {
      const res = await api.get('/admin/manage/email-delivery-ledger', {
        params: {
          user: recipient.trim(),
          event: event.trim(),
          idempotency_key: idempotency.trim(),
          limit: Number(limit || 100),
          anomaly_mode: anomalyMode,
          anomaly_window_hours: Number(anomalyWindowHours || 24),
          anomaly_volume_threshold: Number(anomalyVolumeThreshold || 5),
        },
        silentLoading: true,
      });
      setRows(Array.isArray(res.data?.entries) ? res.data.entries : []);
      setSummary({
        idempotency_matches: Number(res.data?.idempotency_matches || 0),
        send_matches: Number(res.data?.send_matches || 0),
      });
      setAnomalies({
        duplicate_idempotency_keys: Array.isArray(res.data?.anomalies?.duplicate_idempotency_keys) ? res.data.anomalies.duplicate_idempotency_keys : [],
        high_volume_recipient_templates: Array.isArray(res.data?.anomalies?.high_volume_recipient_templates) ? res.data.anomalies.high_volume_recipient_templates : [],
        total_flagged_rows: Number(res.data?.anomalies?.total_flagged_rows || 0),
      });
    } catch {
      setRows([]);
      setSummary({ idempotency_matches: 0, send_matches: 0 });
      setAnomalies({ duplicate_idempotency_keys: [], high_volume_recipient_templates: [], total_flagged_rows: 0 });
      Alert.alert('Ledger unavailable', 'Failed to fetch email delivery ledger.');
    } finally {
      setLoading(false);
    }
  };

  const exportCsv = async () => {
    try {
      const response = await api.get('/admin/manage/email-delivery-ledger.csv', {
        params: {
          user: recipient.trim(),
          event: event.trim(),
          idempotency_key: idempotency.trim(),
          limit: Number(limit || 500),
          anomaly_mode: anomalyMode,
          anomaly_window_hours: Number(anomalyWindowHours || 24),
          anomaly_volume_threshold: Number(anomalyVolumeThreshold || 5),
        },
        responseType: 'blob',
        silentLoading: true,
      });
      const blob = new Blob([response.data], { type: 'text/csv;charset=utf-8;' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `email_delivery_ledger_${Date.now()}.csv`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch {
      Alert.alert('Export failed', 'Could not export ledger CSV.');
    }
  };

  useEffect(() => {
    void loadLedger();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isAdmin]);

  return (
    <AdminRouteGate returnTo="/admin/email-delivery-ledger">
    <AppShell>
      <ScrollView
        style={{ flex: 1, backgroundColor: C.bg }}
        contentContainerStyle={{ padding: isCompact ? 12 : 16, gap: 12, width: '100%', maxWidth: 1240, alignSelf: 'center' }}
        data-testid="email-delivery-ledger-page"
        testID="email-delivery-ledger-page"
      >
        <View style={{ borderWidth: 1, borderColor: C.border, borderRadius: 14, backgroundColor: C.card, padding: 14, gap: 10 }} data-testid="email-delivery-ledger-header-card" testID="email-delivery-ledger-header-card">
          <View style={{ flexDirection: 'row', alignItems: isCompact ? 'flex-start' : 'center', justifyContent: 'space-between', gap: 8, flexWrap: 'wrap' }}>
            <View style={{ flex: 1, minWidth: isCompact ? '100%' : 220 }}>
              <Text style={{ color: C.text, fontSize: 16, fontWeight: '800' }}>Email Delivery Ledger</Text>
              <Text style={{ color: C.muted, fontSize: 11, marginTop: 2 }}>Search by recipient, template event, or idempotency key.</Text>
            </View>
            <TouchableOpacity onPress={() => router.back()} style={{ paddingHorizontal: 10, paddingVertical: 8, borderRadius: 8, borderWidth: 1, borderColor: C.border }} data-testid="email-delivery-ledger-back-button" testID="email-delivery-ledger-back-button">
              <Text style={{ color: C.muted, fontSize: 11, fontWeight: '700' }}>Back</Text>
            </TouchableOpacity>
          </View>

          <View style={{ gap: 8 }}>
            <TextInput value={recipient} onChangeText={setRecipient} placeholder="Recipient email" placeholderTextColor={C.muted} style={{ borderWidth: 1, borderColor: C.border, borderRadius: 10, backgroundColor: C.bg, color: C.text, paddingHorizontal: 10, paddingVertical: 8 }} data-testid="email-ledger-recipient-input" testID="email-ledger-recipient-input" />
            <TextInput value={event} onChangeText={setEvent} placeholder="Template key / event" placeholderTextColor={C.muted} style={{ borderWidth: 1, borderColor: C.border, borderRadius: 10, backgroundColor: C.bg, color: C.text, paddingHorizontal: 10, paddingVertical: 8 }} data-testid="email-ledger-event-input" testID="email-ledger-event-input" />
            <TextInput value={idempotency} onChangeText={setIdempotency} placeholder="Idempotency key" placeholderTextColor={C.muted} style={{ borderWidth: 1, borderColor: C.border, borderRadius: 10, backgroundColor: C.bg, color: C.text, paddingHorizontal: 10, paddingVertical: 8 }} data-testid="email-ledger-idempotency-input" testID="email-ledger-idempotency-input" />
            <TextInput value={limit} onChangeText={setLimit} keyboardType="number-pad" placeholder="Limit" placeholderTextColor={C.muted} style={{ borderWidth: 1, borderColor: C.border, borderRadius: 10, backgroundColor: C.bg, color: C.text, paddingHorizontal: 10, paddingVertical: 8 }} data-testid="email-ledger-limit-input" testID="email-ledger-limit-input" />
          </View>

          <View style={{ borderWidth: 1, borderColor: C.border, borderRadius: 12, backgroundColor: C.bg, padding: 10, gap: 8 }} data-testid="email-ledger-anomaly-controls" testID="email-ledger-anomaly-controls">
            <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8, flexWrap: 'wrap' }}>
              <View>
                <Text style={{ color: C.text, fontSize: 12, fontWeight: '800' }} data-testid="email-ledger-anomaly-mode-label" testID="email-ledger-anomaly-mode-label">Anomaly mode</Text>
                <Text style={{ color: C.muted, fontSize: 10, marginTop: 2 }} data-testid="email-ledger-anomaly-mode-caption" testID="email-ledger-anomaly-mode-caption">Highlights repeated idempotency keys and high-volume send bursts.</Text>
              </View>
              <TouchableOpacity
                onPress={() => setAnomalyMode((value) => !value)}
                style={{ paddingHorizontal: 12, paddingVertical: 8, borderRadius: 999, borderWidth: 1, borderColor: anomalyMode ? C.warning : C.border, backgroundColor: anomalyMode ? C.warning : C.card }}
                data-testid="email-ledger-anomaly-toggle-button"
                testID="email-ledger-anomaly-toggle-button"
              >
                <Text style={{ color: anomalyMode ? C.primaryText : C.text, fontSize: 11, fontWeight: '800' }} data-testid="email-ledger-anomaly-toggle-label" testID="email-ledger-anomaly-toggle-label">
                  {anomalyMode ? 'Anomaly mode: ON' : 'Anomaly mode: OFF'}
                </Text>
              </TouchableOpacity>
            </View>

            <View style={{ flexDirection: 'row', gap: 8, flexWrap: 'wrap' }}>
              <View style={{ flex: 1, minWidth: isCompact ? '100%' : 160 }}>
                <Text style={{ color: C.muted, fontSize: 10, marginBottom: 4 }} data-testid="email-ledger-anomaly-window-label" testID="email-ledger-anomaly-window-label">Window (hours)</Text>
                <TextInput value={anomalyWindowHours} onChangeText={setAnomalyWindowHours} keyboardType="number-pad" placeholder="24" placeholderTextColor={C.muted} style={{ borderWidth: 1, borderColor: C.border, borderRadius: 10, backgroundColor: C.card, color: C.text, paddingHorizontal: 10, paddingVertical: 8 }} data-testid="email-ledger-anomaly-window-input" testID="email-ledger-anomaly-window-input" />
              </View>
              <View style={{ flex: 1, minWidth: isCompact ? '100%' : 180 }}>
                <Text style={{ color: C.muted, fontSize: 10, marginBottom: 4 }} data-testid="email-ledger-anomaly-threshold-label" testID="email-ledger-anomaly-threshold-label">High-volume threshold</Text>
                <TextInput value={anomalyVolumeThreshold} onChangeText={setAnomalyVolumeThreshold} keyboardType="number-pad" placeholder="5" placeholderTextColor={C.muted} style={{ borderWidth: 1, borderColor: C.border, borderRadius: 10, backgroundColor: C.card, color: C.text, paddingHorizontal: 10, paddingVertical: 8 }} data-testid="email-ledger-anomaly-threshold-input" testID="email-ledger-anomaly-threshold-input" />
              </View>
            </View>
          </View>

          <View style={{ flexDirection: 'row', gap: 8, flexWrap: 'wrap' }}>
            <TouchableOpacity onPress={() => { void loadLedger(); }} style={{ flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 12, paddingVertical: 9, borderRadius: 999, backgroundColor: C.primary }} data-testid="email-ledger-search-button" testID="email-ledger-search-button">
              {loading ? <ActivityIndicator size="small" color={C.primaryText} /> : <Ionicons name="search" size={13} color={C.primaryText} />}
              <Text style={{ color: C.primaryText, fontSize: 11, fontWeight: '800' }}>{loading ? 'Searching…' : 'Search Ledger'}</Text>
            </TouchableOpacity>
            <TouchableOpacity onPress={() => { void exportCsv(); }} style={{ flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 12, paddingVertical: 9, borderRadius: 999, borderWidth: 1, borderColor: C.border }} data-testid="email-ledger-export-csv-button" testID="email-ledger-export-csv-button">
              <Ionicons name="download" size={13} color={C.text} />
              <Text style={{ color: C.text, fontSize: 11, fontWeight: '800' }}>Export CSV</Text>
            </TouchableOpacity>
          </View>

          <Text style={{ color: C.muted, fontSize: 11 }} data-testid="email-ledger-summary" testID="email-ledger-summary">
            idempotency matches: {summary.idempotency_matches} • send log matches: {summary.send_matches} • rows: {rows.length}
          </Text>
          {anomalyMode ? (
            <Text style={{ color: C.warning, fontSize: 11, fontWeight: '700' }} data-testid="email-ledger-anomaly-summary" testID="email-ledger-anomaly-summary">
              flagged rows: {anomalies.total_flagged_rows} • duplicate keys: {anomalies.duplicate_idempotency_keys.length} • high-volume pairs: {anomalies.high_volume_recipient_templates.length}
            </Text>
          ) : null}
        </View>

        <View style={{ borderWidth: 1, borderColor: C.border, borderRadius: 14, backgroundColor: C.card, padding: 12 }} data-testid="email-delivery-ledger-table" testID="email-delivery-ledger-table">
          {rows.length === 0 ? (
            <Text style={{ color: C.muted, fontSize: 11 }} data-testid="email-ledger-empty" testID="email-ledger-empty">No ledger rows found for the current filters.</Text>
          ) : (
            <View style={{ gap: 8 }}>
              {rows.map((row, index) => (
                <View key={`${row.idempotency_key || row.email_id || 'row'}-${index}`} style={{ borderWidth: 1, borderColor: row.anomaly_level === 'warning' ? C.warning : C.border, borderRadius: 10, padding: 10, backgroundColor: C.bg }} data-testid={`email-ledger-row-${index}`} testID={`email-ledger-row-${index}`}>
                  <Text style={{ color: C.text, fontSize: 11, fontWeight: '700' }}>{row.recipient || 'unknown recipient'} • {row.template_key || 'unknown template'}</Text>
                  <Text style={{ color: C.muted, fontSize: 10, marginTop: 2 }}>status: {row.status || 'n/a'} • source: {row.source || 'n/a'}</Text>
                  <Text style={{ color: C.muted, fontSize: 10, marginTop: 2 }}>idempotency: {row.idempotency_key || '—'}</Text>
                  <Text style={{ color: C.muted, fontSize: 10, marginTop: 2 }}>email_id: {row.email_id || '—'} • sent_at: {row.sent_at || '—'}</Text>
                  <Text style={{ color: C.muted, fontSize: 10, marginTop: 2 }}>timestamp: {row.timestamp || '—'}</Text>
                  {Array.isArray(row.anomaly_flags) && row.anomaly_flags.length > 0 ? (
                    <Text style={{ color: C.warning, fontSize: 10, marginTop: 4, fontWeight: '700' }} data-testid={`email-ledger-row-anomaly-${index}`} testID={`email-ledger-row-anomaly-${index}`}>
                      anomaly: {row.anomaly_flags.join(', ')}
                    </Text>
                  ) : null}
                </View>
              ))}
            </View>
          )}
        </View>
      </ScrollView>
    </AppShell>
    </AdminRouteGate>
  );
}

/* i18n-probe t('i18n.auto.probe') */
