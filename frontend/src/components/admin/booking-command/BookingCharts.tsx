import React from 'react';
import { View, Text } from 'react-native';
import { useExecTheme} from '../ExecDashboardPanels';
import { useTranslation } from '../../../hooks/useTranslation';

interface Props {
  dailyChart: { date: string; count: number }[];
  peakHours: { hour: number; count: number }[];
}

export default function BookingCharts({ dailyChart, peakHours }: Props) {
  const T = useExecTheme();
  const { t } = useTranslation();
  const tx = React.useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);
  const maxHour = Math.max(...peakHours.map(h => h.count), 1);

  return (
    <View style={{ flexDirection: 'row', gap: 12, marginBottom: 20, flexWrap: 'wrap' }}>
      {/* Daily Bookings Chart */}
      <View style={{ flex: 1, minWidth: 300, backgroundColor: T.card, borderRadius: 16, padding: 16, borderWidth: 1, borderColor: T.border }}>
        <Text style={{ fontSize: 13, fontWeight: '700', color: T.text, marginBottom: 12 }}>{tx('admin.bookingCharts.dailyBookings14Days', 'Bookings (14 Days)')}</Text>
        <View style={{ flexDirection: 'row', alignItems: 'flex-end', gap: 4, height: 100 }}>
          {dailyChart.map((d, i) => {
            const maxC = Math.max(...dailyChart.map(x => x.count), 1);
            const h = Math.max((d.count / maxC) * 80, 2);
            return (
              <View key={i} style={{ flex: 1, alignItems: 'center' }}>
                <Text style={{ fontSize: 8, color: T.textMuted, marginBottom: 2 }}>{d.count || ''}</Text>
                <View style={{ width: '80%', height: h, backgroundColor: T.primary, borderRadius: 3, opacity: d.count > 0 ? 1 : 0.2 }} />
                <Text style={{ fontSize: 7, color: T.textMuted, marginTop: 2 }}>{d.date.slice(5)}</Text>
              </View>
            );
          })}
        </View>
      </View>

      {/* Peak Hours Heatmap */}
      <View style={{ flex: 1, minWidth: 300, backgroundColor: T.card, borderRadius: 16, padding: 16, borderWidth: 1, borderColor: T.border }}>
        <Text style={{ fontSize: 13, fontWeight: '700', color: T.text, marginBottom: 12 }}>{tx('admin.bookingCharts.peakBookingHours', 'Peak Booking Hours')}</Text>
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 3 }}>
          {peakHours.map(h => {
            const intensity = h.count / maxHour;
            const bg = intensity > 0.7 ? T.primary : intensity > 0.3 ? T.primarySoft : T.bgSoft;
            return (
              <View key={h.hour} style={{
                width: 38, height: 28, borderRadius: 6, backgroundColor: bg,
                alignItems: 'center', justifyContent: 'center', borderWidth: 1, borderColor: T.border,
              }}>
                <Text style={{ fontSize: 8, fontWeight: '700', color: intensity > 0.7 ? 'var(--app-primary-text)' : T.textMuted }}>{h.hour}h</Text>
                {h.count > 0 && <Text style={{ fontSize: 7, color: intensity > 0.7 ? 'var(--app-primary)' : T.textMuted }}>{h.count}</Text>}
              </View>
            );
          })}
        </View>
      </View>
    </View>
  );
}
