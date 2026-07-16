import React from 'react';
import { Ionicons } from '@expo/vector-icons';
import { ScrollView, Text, TouchableOpacity, View } from 'react-native';
import { BillingActionButton, BillingSectionCard } from '../paymentHistory/BillingRoutePrimitives';

type TabItem = { key: string; label: string; icon: string; desc: string };

type Props = {
  colors: any;
  tx: (key: string, fallback: string) => string;
  activeTab: string;
  tabs: TabItem[];
  lastSyncLabel: string;
  funnelHint: string;
  onRefresh: () => void;
  onTabSwitch: (key: string) => void;
  children: React.ReactNode;
};

export const JobsPortalTabsFrame = ({
  colors,
  tx,
  activeTab,
  tabs,
  lastSyncLabel,
  funnelHint,
  onRefresh,
  onTabSwitch,
  children,
}: Props) => {
  return (
    <BillingSectionCard colors={colors} testId="jobs-portal-tab-frame">
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 12, flexWrap: 'wrap', marginBottom: 12 }}>
        <View>
          <Text style={{ color: colors.text, fontSize: 16, fontWeight: '900' }}>{tx('jobsPortal.tabs.title', 'Portal workstreams')}</Text>
          <Text style={{ color: colors.textMuted, fontSize: 12, lineHeight: 18, marginTop: 4 }}>{tx('jobsPortal.tabs.subtitle', 'Switch between candidate, search, and employer workflows without leaving the jobs route.')}</Text>
        </View>
        <BillingActionButton label={`${tx('jobsPortal.summary.lastSync', 'Last sync')}: ${lastSyncLabel || '—'}`} onPress={onRefresh} icon="refresh-outline" colors={colors} testId="jobs-portal-refresh-summary-button" variant="subtle" />
      </View>

      {!!funnelHint && (
        <View style={{ marginBottom: 12, borderRadius: 14, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(colors.primary, '33'), backgroundColor: colors.primarySoft, padding: 12 }} data-testid="jobs-portal-funnel-hint" testID="jobs-portal-funnel-hint">
          <Text style={{ color: colors.primary, fontSize: 12, fontWeight: '700' }}>{funnelHint}</Text>
        </View>
      )}

      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ flexDirection: 'row', gap: 8, paddingBottom: 2 }} data-testid="jobs-portal-tab-scroll" testID="jobs-portal-tab-scroll">
        {tabs.map((tab) => {
          const active = tab.key === activeTab;
          return (
            <TouchableOpacity
              key={tab.key}
              onPress={() => onTabSwitch(tab.key)}
              style={{ width: '100%', maxWidth: 960, borderRadius: 12, borderWidth: 1, borderColor: active ? (globalThis as any).__alphaColor(colors.primary, '55') : colors.border, backgroundColor: active ? colors.primarySoft : colors.bgSoft, paddingHorizontal: 10, paddingVertical: 9, flexDirection: 'row', alignItems: 'center', gap: 8 }}
              data-testid={`jobs-portal-tab-${tab.key}`}
              testID={`jobs-portal-tab-${tab.key}`}
            >
              <Ionicons name={tab.icon as any} size={16} color={active ? colors.primary : colors.textMuted} />
              <View style={{ flex: 1 }}>
                <Text style={{ color: active ? colors.primary : colors.textSec, fontSize: 12, fontWeight: '800' }}>{tab.label}</Text>
                <Text style={{ color: colors.textMuted, fontSize: 10, marginTop: 1 }}>{tab.desc}</Text>
              </View>
            </TouchableOpacity>
          );
        })}
      </ScrollView>

      <View style={{ flex: 1, marginTop: 12 }} data-testid="jobs-portal-content-area" testID="jobs-portal-content-area">
        {children}
      </View>
    </BillingSectionCard>
  );
};
