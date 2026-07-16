import React from 'react';
import { View, Text, ScrollView } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useExecTheme, MiniSparkline} from '../ExecDashboardPanels';
import { BookingData } from './types';

function KPI({ icon, label, value, color, sub, spark }: { icon: string; label: string; value: number; color: string; sub?: string; spark?: number[] }) {
  const T = useExecTheme();
  return (
    <View style={{
      width: 160, backgroundColor: T.card, borderRadius: 14, padding: 14,
      borderWidth: 1, borderColor: T.border, borderLeftWidth: 3, borderLeftColor: color,
    }} data-testid={`booking-kpi-${label.replace(/\s+/g, '-').toLowerCase()}`} testID={`booking-kpi-${label.replace(/\s+/g, '-').toLowerCase()}`}>
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
        <View style={{ width: 28, height: 28, borderRadius: 8, backgroundColor: (globalThis as any).__alphaColor(color, '18'), alignItems: 'center', justifyContent: 'center' }}>
          <Ionicons name={icon as any} size={14} color={color} />
        </View>
        {spark && <MiniSparkline data={spark} color={color} width={50} height={20} />}
      </View>
      <Text style={{ fontSize: 22, fontWeight: '800', color: T.text }}>{value}</Text>
      <Text style={{ fontSize: 10, color: T.textMuted, marginTop: 2 }}>{label}</Text>
      {sub && <Text style={{ fontSize: 9, color: color, marginTop: 2, fontWeight: '600' }}>{sub}</Text>}
    </View>
  );
}

interface Props {
  kpis: BookingData['kpis'];
}

export default function BookingKPIRow({ kpis }: Props) {
  const T = useExecTheme();
  const k = kpis;
  return (
    <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ marginBottom: 20 }}>
      <View style={{ flexDirection: 'row', gap: 12 }}>
        <KPI icon="calendar" label="Total Bookings" value={k.total_bookings} color={T.primary} spark={k.weekly_sparkline} />
        <KPI icon="checkmark-circle" label="Confirmed" value={k.confirmed} color={T.successText} sub={`${k.conversion_rate}% rate`} />
        <KPI icon="close-circle" label="Cancelled" value={k.cancelled} color={T.error} sub={`${k.cancel_rate}% rate`} />
        <KPI icon="today" label="Today" value={k.today_bookings} color={T.warningText} />
        <KPI icon="time" label="This Week" value={k.week_bookings} color={T.cyan} />
        <KPI icon="globe" label="Active Pages" value={k.active_pages} color={T.purpleText} sub={`${k.total_pages} total`} />
        <KPI icon="arrow-forward-circle" label="Upcoming" value={k.upcoming_count} color={T.teal} />
        <KPI icon="notifications" label="Reminders Sent" value={k.reminders_sent} color={T.orangeText} />
      </View>
    </ScrollView>
  );
}

/* i18n-probe t('i18n.auto.probe') */
