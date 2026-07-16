import React, { useCallback, useEffect, useState } from 'react';
import { ActivityIndicator, ScrollView, Text, View } from 'react-native';
import { useAuth } from '../../context/AuthContext';
import api from '../../services/api';
import { useTranslation } from '../../hooks/useTranslation';

type Props = { colors: any };

export const SportsSourceHealthOpsPanel = ({ colors }: Props) => {
  const { t } = useTranslation();
  t('i18n.route.admin.sports.source.health.probe');
  const { user } = useAuth();
  const [loading, setLoading] = useState(true);
  const [payload, setPayload] = useState<any>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.get('/sports/v2/admin/source-health');
      setPayload(res.data || null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  if (!user?.is_admin) {
    return (
      <View style={{ borderWidth: 1, borderColor: colors.border, borderRadius: 12, padding: 14, backgroundColor: colors.card }} data-testid="ops-sports-source-health-access-denied" testID="ops-sports-source-health-access-denied">
        <Text style={{ color: colors.errorText, fontWeight: '700' }}>Admin access required.</Text>
      </View>
    );
  }

  if (loading) {
    return (
      <View style={{ alignItems: 'center', justifyContent: 'center', padding: 28 }} data-testid="ops-sports-source-health-loading" testID="ops-sports-source-health-loading">
        <ActivityIndicator color={colors.primary} />
      </View>
    );
  }

  const summary = payload?.summary || {};
  const sources = Array.isArray(payload?.sources) ? payload.sources : [];

  return (
    <ScrollView style={{ flex: 1 }} contentContainerStyle={{ gap: 10, paddingBottom: 16 }} data-testid="ops-sports-source-health-panel" testID="ops-sports-source-health-panel">
      <View style={{ borderWidth: 1, borderColor: colors.border, borderRadius: 12, padding: 12, backgroundColor: colors.card }}>
        <Text style={{ color: colors.text, fontSize: 16, fontWeight: '800' }}>Sports Source Health</Text>
        <Text style={{ color: colors.textSec, marginTop: 4 }}>Source reliability and playable coverage from sports ingestion.</Text>
      </View>

      <View style={{ borderWidth: 1, borderColor: colors.border, borderRadius: 12, padding: 12, backgroundColor: colors.card }}>
        <Text style={{ color: colors.text, fontWeight: '800' }}>Summary</Text>
        <Text style={{ color: colors.textSec, marginTop: 6 }}>Playable ratio: {summary.playable_ratio_percent ?? 0}%</Text>
        <Text style={{ color: colors.textSec }}>Sources: {summary.source_count ?? 0} • Items: {summary.total_items ?? 0}</Text>
      </View>

      <View style={{ borderWidth: 1, borderColor: colors.border, borderRadius: 12, padding: 12, backgroundColor: colors.card }}>
        <Text style={{ color: colors.text, fontWeight: '800', marginBottom: 8 }}>Top Source Status</Text>
        {sources.slice(0, 12).map((row: any, idx: number) => (
          <View key={`${row.source_label}-${idx}`} style={{ borderTopWidth: idx === 0 ? 0 : 1, borderTopColor: colors.border, paddingVertical: 8 }}>
            <Text style={{ color: colors.text, fontWeight: '700' }}>{row.source_label}</Text>
            <Text style={{ color: colors.textSec, fontSize: 12 }}>{`${row.playable_items}/${row.items} playable • score ${row.health_score}`}</Text>
          </View>
        ))}
      </View>
    </ScrollView>
  );
};
