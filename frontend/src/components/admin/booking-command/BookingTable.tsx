import { useTranslation } from '../../../hooks/useTranslation';
import React from 'react';
import { View, Text, TouchableOpacity, TextInput } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useExecTheme} from '../ExecDashboardPanels';
import { Booking, BookingFilter, fmtDt } from './types';

interface Props {
  bookings: Booking[];
  filter: BookingFilter;
  setFilter: (f: BookingFilter) => void;
  search: string;
  setSearch: (s: string) => void;
}

const tx = (_key: string, fallback: string) => fallback;

export default function BookingTable({ bookings, filter, setFilter, search, setSearch }: Props) {
  const { t } = useTranslation();
  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };

  const T = useExecTheme();
  const filtered = bookings.filter(b => {
    const matchFilter = filter === 'all' || (filter === 'cancelled' ? b.status === 'cancelled' : b.status !== 'cancelled');
    const matchSearch = !search || (b.guest_name || '').toLowerCase().includes(search.toLowerCase()) || (b.guest_email || '').toLowerCase().includes(search.toLowerCase());
    return matchFilter && matchSearch;
  });

  return (
    <View style={{ backgroundColor: T.card, borderRadius: 16, padding: 16, borderWidth: 1, borderColor: T.border, marginBottom: 20 }}>
      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
          <Ionicons name="list" size={16} color={T.primary} />
          <Text style={{ fontSize: 13, fontWeight: '700', color: T.text }}>{tx('admin.bookingTable.auto.text.001', 'All Bookings')}</Text>
        </View>
        <View style={{ flexDirection: 'row', gap: 6 }}>
          {(['all', 'confirmed', 'cancelled'] as const).map(f => (
            <TouchableOpacity key={f} onPress={() => setFilter(f)} style={{
              paddingHorizontal: 10, paddingVertical: 4, borderRadius: 8,
              backgroundColor: filter === f ? T.primary : T.bgSoft,
            }} data-testid={`booking-filter-${f}`} testID={`booking-filter-${f}`}>
              <Text style={{ fontSize: 10, fontWeight: '700', color: filter === f ? 'var(--app-primary-text)' : T.textMuted, textTransform: 'capitalize' }}>{f}</Text>
            </TouchableOpacity>
          ))}
        </View>
      </View>

      <TextInput
        style={{ borderWidth: 1, borderColor: T.border, borderRadius: 10, paddingHorizontal: 12, paddingVertical: 8, fontSize: 12, color: T.text, backgroundColor: T.bgSoft, marginBottom: 12 }}
        placeholder={tx('admin.bookingTable.auto.placeholder.001', 'Search by guest name or email...')} placeholderTextColor={T.textMuted}
        value={search} onChangeText={setSearch}
        data-testid="booking-search-input" testID="booking-search-input"
      />

      <View style={{ flexDirection: 'row', paddingVertical: 8, borderBottomWidth: 1, borderBottomColor: T.border }}>
        <Text style={{ flex: 2, fontSize: 10, fontWeight: '700', color: T.textMuted, textTransform: 'uppercase' }}>{tx('admin.bookingTable.auto.text.002', 'Guest')}</Text>
        <Text style={{ flex: 2, fontSize: 10, fontWeight: '700', color: T.textMuted, textTransform: 'uppercase' }}>{tx('admin.bookingTable.auto.text.003', 'Host')}</Text>
        <Text style={{ flex: 2, fontSize: 10, fontWeight: '700', color: T.textMuted, textTransform: 'uppercase' }}>{tx('admin.bookingTable.auto.text.004', 'When')}</Text>
        <Text style={{ flex: 1, fontSize: 10, fontWeight: '700', color: T.textMuted, textTransform: 'uppercase' }}>{tx('admin.bookingTable.auto.text.005', 'Status')}</Text>
      </View>

      {filtered.map(b => (
        <View key={b.booking_id} style={{ flexDirection: 'row', paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: 'rgba(30,45,74,0.25)', alignItems: 'center' }}
          data-testid={`booking-row-${b.booking_id}`} testID={`booking-row-${b.booking_id}`}>
          <View style={{ flex: 2 }}>
            <Text style={{ fontSize: 12, fontWeight: '600', color: T.text }}>{b.guest_name}</Text>
            <Text style={{ fontSize: 9, color: T.textMuted }}>{b.guest_email}</Text>
          </View>
          <Text style={{ flex: 2, fontSize: 11, color: T.textSec }}>{b.host_name || '\u2014'}</Text>
          <Text style={{ flex: 2, fontSize: 11, color: T.textSec }}>{fmtDt(b.start)}</Text>
          <View style={{ flex: 1 }}>
            <View style={{
              paddingHorizontal: 8, paddingVertical: 3, borderRadius: 6, alignSelf: 'flex-start',
              backgroundColor: b.status === 'cancelled' ? T.errorSoft : T.successSoft,
            }}>
              <Text style={{ fontSize: 9, fontWeight: '700', color: b.status === 'cancelled' ? T.error : T.success, textTransform: 'uppercase' }}>
                {b.status === 'cancelled' ? 'Cancelled' : 'Confirmed'}
              </Text>
            </View>
          </View>
        </View>
      ))}

      {filtered.length === 0 && (
        <Text style={{ fontSize: 12, color: T.textMuted, textAlign: 'center', paddingVertical: 20 }}>{tx('admin.bookingTable.auto.text.006', 'No bookings match your search')}</Text>
      )}
    </View>
  );
}
