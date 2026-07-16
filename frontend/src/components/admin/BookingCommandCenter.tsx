import React, { useState } from 'react';
import { View, Text, ScrollView, ActivityIndicator, TouchableOpacity } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useExecTheme} from './ExecDashboardPanels';
import DataFreshnessIndicator from '../DataFreshnessIndicator';
import { BookingData, BookingFilter } from './booking-command/types';
import BookingKPIRow from './booking-command/BookingKPIRow';
import BookingCharts from './booking-command/BookingCharts';
import BookingHostsPanel from './booking-command/BookingHostsPanel';
import BookingUpcoming from './booking-command/BookingUpcoming';
import BookingTable from './booking-command/BookingTable';
import AutoFixBanner from './AutoFixBanner';
import { useAdminTheme } from '../../hooks/useAdminTheme';
import { useTranslation } from '../../hooks/useTranslation';
import { useLiveQuery } from '../../hooks/useLiveQuery';

interface Props { colors: any; }

const tx = (_key: string, fallback: string) => fallback;

export default function BookingCommandCenter({ colors: _propColors }: Props) {
  const { t } = useTranslation();
  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };

  const colors = useAdminTheme();
  const T = useExecTheme();
  const { data, loading, refetch: refresh, lastUpdated } = useLiveQuery<BookingData>('/admin/booking-dashboard', { entity: 'bookings', pollInterval: 30000 });
  const [search, setSearch] = useState('');
  const [filter, setFilter] = useState<BookingFilter>('all');

  if (loading) return <View style={{ paddingVertical: 40, alignItems: 'center' }}><ActivityIndicator size="large" color={T.primary} /></View>;
  if (!data) return <View style={{ padding: 20 }}><Text style={{ color: T.error }}>{tx('admin.bookingCommandCenter.auto.text.001', 'Failed to load booking data')}</Text></View>;

  return (
    <ScrollView style={{ flex: 1 }} showsVerticalScrollIndicator={false}>
      <AutoFixBanner domain="booking" />
      {/* Header */}
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
        <View>
          <Text style={{ fontSize: 20, fontWeight: '800', color: T.text }} data-testid="booking-cmd-title" testID="booking-cmd-title">{tx('admin.bookingCommandCenter.auto.text.002', 'Booking Command Center')}</Text>
          <Text style={{ fontSize: 12, color: T.textSec, marginTop: 2 }}>{tx('admin.bookingCommandCenter.auto.text.003', 'Real-time booking analytics & management')}</Text>
        </View>
        <TouchableOpacity onPress={refresh} style={{ padding: 8, borderRadius: 10, backgroundColor: T.primarySoft }} data-testid="booking-cmd-refresh" testID="booking-cmd-refresh">
          <Ionicons name="refresh" size={18} color={T.primary} />
        </TouchableOpacity>
      </View>
      <DataFreshnessIndicator lastUpdated={lastUpdated} onRefresh={refresh} isRefreshing={loading} accentColor={T.primary} textColor={T.textMuted} />

      <BookingKPIRow kpis={data.kpis} />
      <BookingCharts dailyChart={data.daily_chart || []} peakHours={data.peak_hours || []} />

      <View style={{ flexDirection: 'row', gap: 12, marginBottom: 20, flexWrap: 'wrap' }}>
        <BookingHostsPanel hosts={data.top_hosts || []} />
        <BookingUpcoming upcoming={data.upcoming || []} />
      </View>

      <BookingTable
        bookings={data.recent_bookings || []}
        filter={filter}
        setFilter={setFilter}
        search={search}
        setSearch={setSearch}
      />
    </ScrollView>
  );
}
