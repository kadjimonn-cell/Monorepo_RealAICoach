import React from 'react';
import { Platform, Text, TextInput, TouchableOpacity, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { getTestProps } from '../../utils/testProps';
import { PaymentSortKey } from './types';

type Props = {
  colors: any;
  tx: (key: string, fallback: string) => string;
  searchText: string;
  onChangeSearchText: (value: string) => void;
  gatewayFilter: string;
  onChangeGatewayFilter: (value: string) => void;
  availableGateways: string[];
  statusFilter: string;
  onChangeStatusFilter: (value: string) => void;
  startDate: string;
  endDate: string;
  onChangeStartDate: (value: string) => void;
  onChangeEndDate: (value: string) => void;
  quickRange: string;
  onChangeQuickRange: (value: string) => void;
  sortKey: PaymentSortKey;
  onChangeSortKey: (value: PaymentSortKey) => void;
  sortDirection: 'asc' | 'desc';
  onToggleSortDirection: () => void;
  onClearFilters: () => void;
};

const FilterChip = ({ label, active, onPress, testId, colors }: { label: string; active: boolean; onPress: () => void; testId: string; colors: any; }) => (
  <TouchableOpacity onPress={onPress} style={{ paddingHorizontal: 12, paddingVertical: 8, borderRadius: 10, backgroundColor: active ? colors.primary : colors.bgSoft, borderWidth: 1, borderColor: active ? colors.primary : colors.border }} {...getTestProps(testId)} accessibilityLabel="label">
    <Text style={{ color: active ? (colors.primaryText || colors.text) : colors.textMuted, fontSize: 12, fontWeight: '800' }}>{label}</Text>
  </TouchableOpacity>
);

export const PaymentHistoryFilters = ({ colors, tx, searchText, onChangeSearchText, gatewayFilter, onChangeGatewayFilter, availableGateways, statusFilter, onChangeStatusFilter, startDate, endDate, onChangeStartDate, onChangeEndDate, quickRange, onChangeQuickRange, sortKey, onChangeSortKey, sortDirection, onToggleSortDirection, onClearFilters }: Props) => {
  const renderDateInput = (value: string, onChange: (next: string) => void, placeholder: string, testId: string) => {
    if (Platform.OS === 'web') {
      return React.createElement('input', {
        type: 'date',
        value,
        onChange: (event: any) => onChange(event.target.value),
        ...getTestProps(testId),
        style: { width: '100%', padding: '10px 12px', borderRadius: 10, border: `1px solid ${colors.border}`, backgroundColor: colors.bg, color: colors.text, fontSize: 13, fontWeight: 700, minHeight: 42 },
      });
    }
    return <TextInput value={value} onChangeText={onChange} placeholder={placeholder} placeholderTextColor={colors.textMuted} style={{ minHeight: 42, borderRadius: 10, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bg, color: colors.text, paddingHorizontal: 12, paddingVertical: 10, fontSize: 13, fontWeight: '700' }} {...getTestProps(testId)} />;
  };

  const gatewayOptions = ['all', ...availableGateways];

  return (
    <View style={{ backgroundColor: colors.card, borderRadius: 20, padding: 16, borderWidth: 1, borderColor: colors.border, gap: 14 }} {...getTestProps('payment-history-filters-panel')}>
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
          <Ionicons name="search-outline" size={16} color={colors.textMuted} />
          <Text style={{ color: colors.text, fontSize: 14, fontWeight: '800' }}>{tx('paymentHistory.filters.title', 'Search, filter, and sort')}</Text>
        </View>
        <TouchableOpacity onPress={onClearFilters} {...getTestProps('payment-history-clear-filters-button')} accessibilityLabel="Clear Filters">
          <Text style={{ color: colors.primary, fontSize: 12, fontWeight: '800' }}>{tx('paymentHistory.filters.clear', 'Clear all')}</Text>
        </TouchableOpacity>
      </View>

      <TextInput value={searchText} onChangeText={onChangeSearchText} placeholder={tx('paymentHistory.filters.searchPlaceholder', 'Search by reference, provider, plan, status, or amount')} placeholderTextColor={colors.textMuted} style={{ minHeight: 46, borderRadius: 12, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bg, color: colors.text, paddingHorizontal: 14, paddingVertical: 12, fontSize: 14, fontWeight: '600' }} {...getTestProps('payment-history-search-input')} />

      <View style={{ gap: 8 }}>
        <Text style={{ color: colors.textMuted, fontSize: 11, fontWeight: '800', textTransform: 'uppercase', letterSpacing: 0.8 }} {...getTestProps('payment-history-quick-range-label')}>{tx('paymentHistory.filters.quickRange', 'Quick date range')}</Text>
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
          {[['all', tx('paymentHistory.filters.rangeAll', 'All')], ['30d', tx('paymentHistory.filters.range30d', '30D')], ['90d', tx('paymentHistory.filters.range90d', '90D')], ['ytd', tx('paymentHistory.filters.rangeYtd', 'YTD')]].map(([value, label]) => (
            <FilterChip key={value} label={label} active={quickRange === value} onPress={() => onChangeQuickRange(value)} testId={`payment-history-quick-range-${value}`} colors={colors} />
          ))}
        </View>
      </View>

      <View style={{ flexDirection: 'row', gap: 12, flexWrap: 'wrap' }}>
        <View style={{ flex: 1, minWidth: 180, gap: 8 }}>
          <Text style={{ color: colors.textMuted, fontSize: 11, fontWeight: '800', textTransform: 'uppercase', letterSpacing: 0.8 }}>{tx('paymentHistory.filters.gateway', 'Gateway')}</Text>
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
            {gatewayOptions.map((value) => <FilterChip key={value} label={value === 'all' ? tx('paymentHistory.filters.gatewayAll', 'All') : value === 'fedapay' ? 'FedaPay' : value === 'paypal' ? 'PayPal' : value === 'stripe' ? 'Stripe' : value} active={gatewayFilter === value} onPress={() => onChangeGatewayFilter(value)} testId={`payment-history-gateway-${value}`} colors={colors} />)}
          </View>
        </View>

        <View style={{ flex: 1, minWidth: 180, gap: 8 }}>
          <Text style={{ color: colors.textMuted, fontSize: 11, fontWeight: '800', textTransform: 'uppercase', letterSpacing: 0.8 }}>{tx('paymentHistory.filters.status', 'Status')}</Text>
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
            {[['all', tx('paymentHistory.filters.statusAll', 'All')], ['paid', tx('paymentHistory.filters.statusPaid', 'Paid')], ['pending', tx('paymentHistory.filters.statusPending', 'Pending')], ['failed', tx('paymentHistory.filters.statusFailed', 'Failed')]].map(([value, label]) => (
              <FilterChip key={value} label={label} active={statusFilter === value} onPress={() => onChangeStatusFilter(value)} testId={`payment-history-status-${value}`} colors={colors} />
            ))}
          </View>
        </View>
      </View>

      <View style={{ flexDirection: 'row', gap: 12, flexWrap: 'wrap' }}>
        <View style={{ flex: 1, minWidth: 180, gap: 6 }}>
          <Text style={{ color: colors.textMuted, fontSize: 11, fontWeight: '800', textTransform: 'uppercase', letterSpacing: 0.8 }}>{tx('paymentHistory.filters.startDate', 'Start date')}</Text>
          {renderDateInput(startDate, onChangeStartDate, 'YYYY-MM-DD', 'payment-history-start-date-input')}
        </View>
        <View style={{ flex: 1, minWidth: 180, gap: 6 }}>
          <Text style={{ color: colors.textMuted, fontSize: 11, fontWeight: '800', textTransform: 'uppercase', letterSpacing: 0.8 }}>{tx('paymentHistory.filters.endDate', 'End date')}</Text>
          {renderDateInput(endDate, onChangeEndDate, 'YYYY-MM-DD', 'payment-history-end-date-input')}
        </View>
        <View style={{ flex: 1, minWidth: 180, gap: 8 }}>
          <Text style={{ color: colors.textMuted, fontSize: 11, fontWeight: '800', textTransform: 'uppercase', letterSpacing: 0.8 }}>{tx('paymentHistory.filters.sortBy', 'Sort by')}</Text>
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
            {[['date', tx('paymentHistory.filters.sortDate', 'Date')], ['amount', tx('paymentHistory.filters.sortAmount', 'Amount')], ['status', tx('paymentHistory.filters.sortStatus', 'Status')], ['gateway', tx('paymentHistory.filters.sortGateway', 'Gateway')]].map(([value, label]) => (
              <FilterChip key={value} label={label} active={sortKey === value} onPress={() => onChangeSortKey(value as PaymentSortKey)} testId={`payment-history-sort-key-${value}`} colors={colors} />
            ))}
            <TouchableOpacity onPress={onToggleSortDirection} style={{ paddingHorizontal: 12, paddingVertical: 8, borderRadius: 10, backgroundColor: colors.bgSoft, borderWidth: 1, borderColor: colors.border, flexDirection: 'row', alignItems: 'center', gap: 6 }} {...getTestProps('payment-history-sort-direction-button')} accessibilityLabel="Toggle Sort Direction">
              <Ionicons name={sortDirection === 'desc' ? 'arrow-down-outline' : 'arrow-up-outline'} size={14} color={colors.textMuted} />
              <Text style={{ color: colors.textMuted, fontSize: 12, fontWeight: '800' }}>{sortDirection === 'desc' ? tx('paymentHistory.filters.desc', 'Desc') : tx('paymentHistory.filters.asc', 'Asc')}</Text>
            </TouchableOpacity>
          </View>
        </View>
      </View>
    </View>
  );
};

/* i18n-probe t('i18n.auto.probe') */
