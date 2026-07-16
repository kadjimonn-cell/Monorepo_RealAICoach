import React from 'react';
import { View, Text } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useExecTheme} from '../ExecDashboardPanels';
import { useTranslation } from '../../../hooks/useTranslation';

interface Host {
  user_id: string;
  name: string;
  email: string;
  total: number;
  confirmed: number;
  cancelled: number;
}

interface Props {
  hosts: Host[];
}

export default function BookingHostsPanel({ hosts }: Props) {
  const T = useExecTheme();
  const { t } = useTranslation();
  const tx = React.useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);
  return (
    <View style={{ flex: 1, minWidth: 280, backgroundColor: T.card, borderRadius: 16, padding: 16, borderWidth: 1, borderColor: T.border }}>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 12 }}>
        <Ionicons name="trophy" size={16} color={T.warningText} />
        <Text style={{ fontSize: 13, fontWeight: '700', color: T.text }}>{tx('admin.bookingHosts.topHosts', 'Top Hosts')}</Text>
      </View>
      {hosts.slice(0, 5).map((h, i) => (
        <View key={h.user_id} style={{ flexDirection: 'row', alignItems: 'center', paddingVertical: 8, borderBottomWidth: i < 4 ? 1 : 0, borderBottomColor: T.border }}>
          <View style={{ width: 24, height: 24, borderRadius: 12, backgroundColor: i === 0 ? (globalThis as any).__alphaColor(T.warning, '30') : T.bgSoft, alignItems: 'center', justifyContent: 'center', marginRight: 10 }}>
            <Text style={{ fontSize: 10, fontWeight: '800', color: i === 0 ? T.warning : T.textMuted }}>{i + 1}</Text>
          </View>
          <View style={{ flex: 1 }}>
            <Text style={{ fontSize: 12, fontWeight: '600', color: T.text }}>{h.name || 'Unknown'}</Text>
            <Text style={{ fontSize: 10, color: T.textMuted }}>{h.email}</Text>
          </View>
          <View style={{ alignItems: 'flex-end' }}>
            <Text style={{ fontSize: 14, fontWeight: '800', color: T.primary }}>{h.total}</Text>
            <Text style={{ fontSize: 9, color: T.textMuted }}>{h.confirmed} conf / {h.cancelled} canc</Text>
          </View>
        </View>
      ))}
      {hosts.length === 0 && (
        <Text style={{ fontSize: 12, color: T.textMuted, textAlign: 'center', paddingVertical: 20 }}>{tx('admin.bookingHosts.states.noHostsYet', 'No hosts yet')}</Text>
      )}
    </View>
  );
}
