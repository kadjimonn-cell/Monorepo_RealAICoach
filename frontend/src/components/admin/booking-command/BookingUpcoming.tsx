import React from 'react';
import { View, Text } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useExecTheme} from '../ExecDashboardPanels';
import { fmtDt } from './types';
import { useTranslation } from '../../../hooks/useTranslation';

interface UpcomingBooking {
  booking_id: string;
  guest_name: string;
  guest_email: string;
  start: string;
}

interface Props {
  upcoming: UpcomingBooking[];
}

export default function BookingUpcoming({ upcoming }: Props) {
  const T = useExecTheme();
  const { t } = useTranslation();
  const tx = React.useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);
  return (
    <View style={{ flex: 1, minWidth: 280, backgroundColor: T.card, borderRadius: 16, padding: 16, borderWidth: 1, borderColor: T.border }}>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 12 }}>
        <Ionicons name="arrow-forward-circle" size={16} color={T.teal} />
        <Text style={{ fontSize: 13, fontWeight: '700', color: T.text }}>{tx('admin.bookingUpcoming.title', 'Upcoming Meetings')}</Text>
      </View>
      {upcoming.slice(0, 6).map(b => (
        <View key={b.booking_id} style={{ paddingVertical: 8, borderBottomWidth: 1, borderBottomColor: T.border }}>
          <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
            <Text style={{ fontSize: 12, fontWeight: '600', color: T.text }}>{b.guest_name}</Text>
            <Text style={{ fontSize: 10, color: T.teal, fontWeight: '600' }}>{fmtDt(b.start)}</Text>
          </View>
          <Text style={{ fontSize: 10, color: T.textMuted, marginTop: 2 }}>{b.guest_email}</Text>
        </View>
      ))}
      {upcoming.length === 0 && (
        <Text style={{ fontSize: 12, color: T.textMuted, textAlign: 'center', paddingVertical: 20 }}>{tx('admin.bookingUpcoming.states.none', 'No upcoming meetings')}</Text>
      )}
    </View>
  );
}
