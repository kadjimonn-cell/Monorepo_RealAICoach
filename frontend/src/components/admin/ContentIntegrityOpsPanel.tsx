import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { ActivityIndicator, ScrollView, Text, TouchableOpacity, View } from 'react-native';
import api from '../../services/api';
import { useTranslation } from '../../hooks/useTranslation';

type Props = { colors: any };

export const ContentIntegrityOpsPanel = ({ colors }: Props) => {
  const { t } = useTranslation();
  t('i18n.route.admin.content.integrity.probe');
  const [loading, setLoading] = useState(true);
  const [scanning, setScanning] = useState(false);
  const [dashboard, setDashboard] = useState<any>(null);
  const [alerts, setAlerts] = useState<any[]>([]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [dashRes, alertsRes] = await Promise.all([
        api.get('/admin/content-integrity/dashboard'),
        api.get('/admin/content-integrity/alerts?limit=20'),
      ]);
      setDashboard(dashRes.data || null);
      setAlerts(alertsRes.data?.alerts || []);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const runScan = useCallback(async () => {
    setScanning(true);
    try {
      await api.post('/admin/content-integrity/scan', { scope: 'all', limit: 500 });
      await load();
    } finally {
      setScanning(false);
    }
  }, [load]);

  const openCount = useMemo(() => alerts.filter((a) => a.status === 'open').length, [alerts]);

  if (loading) {
    return (
      <View style={{ alignItems: 'center', justifyContent: 'center', padding: 28 }} data-testid="ops-content-integrity-loading" testID="ops-content-integrity-loading">
        <ActivityIndicator color={colors.primary} />
      </View>
    );
  }

  return (
    <ScrollView style={{ flex: 1 }} contentContainerStyle={{ gap: 10, paddingBottom: 16 }} data-testid="ops-content-integrity-panel" testID="ops-content-integrity-panel">
      <View style={{ borderWidth: 1, borderColor: colors.border, borderRadius: 12, padding: 12, backgroundColor: colors.card }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
          <View style={{ flex: 1 }}>
            <Text style={{ color: colors.text, fontSize: 16, fontWeight: '800' }}>Content Integrity</Text>
            <Text style={{ color: colors.textSec, marginTop: 4 }}>Contamination, alerting, and remediation oversight.</Text>
          </View>
          <TouchableOpacity accessibilityLabel="Ops content integrity run scan button"
            onPress={() => {
              void runScan();
            }}
            disabled={scanning}
            style={{ paddingHorizontal: 12, paddingVertical: 8, borderRadius: 8, backgroundColor: colors.primary, opacity: scanning ? 0.7 : 1 }}
            data-testid="ops-content-integrity-run-scan"
            testID="ops-content-integrity-run-scan"
          >
            <Text style={{ color: colors.primaryText, fontSize: 12, fontWeight: '800' }}>{scanning ? 'Scanning…' : 'Run Scan'}</Text>
          </TouchableOpacity>
        </View>
      </View>

      <View style={{ borderWidth: 1, borderColor: colors.border, borderRadius: 12, padding: 12, backgroundColor: colors.card }}>
        <Text style={{ color: colors.text, fontWeight: '800' }}>Health Snapshot</Text>
        <Text style={{ color: colors.textSec, marginTop: 6 }}>Platform health: {dashboard?.health_score ?? 0}%</Text>
        <Text style={{ color: colors.textSec }}>Open alerts: {openCount}</Text>
      </View>

      <View style={{ borderWidth: 1, borderColor: colors.border, borderRadius: 12, padding: 12, backgroundColor: colors.card }}>
        <Text style={{ color: colors.text, fontWeight: '800', marginBottom: 8 }}>Recent Alerts</Text>
        {alerts.slice(0, 10).map((alert, idx) => (
          <View key={`${alert.id || idx}`} style={{ borderTopWidth: idx === 0 ? 0 : 1, borderTopColor: colors.border, paddingVertical: 8 }}>
            <Text style={{ color: colors.text, fontWeight: '700', textTransform: 'capitalize' }}>{String(alert.severity || 'info')} • {String(alert.category || 'general').replace(/_/g, ' ')}</Text>
            <Text numberOfLines={2} style={{ color: colors.textSec, fontSize: 12, marginTop: 3 }}>{alert.excerpt || alert.message || 'No excerpt available'}</Text>
          </View>
        ))}
        {alerts.length === 0 && (
          <Text style={{ color: colors.textMuted, fontSize: 12 }}>No active integrity alerts.</Text>
        )}
      </View>
    </ScrollView>
  );
};
