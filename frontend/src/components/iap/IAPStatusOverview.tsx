import React from 'react';
import { Text, TouchableOpacity, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { getTestProps } from '../../utils/testProps';
import { BillingActionButton, BillingMetricCard, BillingSectionCard } from '../paymentHistory/BillingRoutePrimitives';

type Props = {
  colors: any;
  status: any;
  historyCount: number;
  manageLinks: { apple?: string; google?: string };
  tx: (key: string, fallback: string) => string;
  onRefresh: () => void;
  onOpenManageLink: (provider: 'apple' | 'google') => void;
};

export const IAPStatusOverview = ({ colors, status, historyCount, manageLinks, tx, onRefresh, onOpenManageLink }: Props) => {
  const hasStoreLinkedSubscription = Boolean(status?.platform);
  const hasActivePlatformPlan = String(status?.plan || 'free') !== 'free' && String(status?.status || '').toLowerCase() === 'active';
  const storeLabel = status?.platform === 'apple'
    ? tx('mobileSubscriptions.providers.apple', 'Apple App Store')
    : status?.platform === 'google'
      ? tx('mobileSubscriptions.providers.googleStore', 'Google Play Store')
      : tx('mobileSubscriptions.status.noStoreAttached', 'No store receipt attached');
  const statusTone = hasStoreLinkedSubscription
    ? String(status?.status || '').toLowerCase() === 'active' ? colors.success : colors.warning
    : hasActivePlatformPlan ? colors.primary : colors.textMuted;
  const planLabel = `${String(status?.plan || 'free').charAt(0).toUpperCase()}${String(status?.plan || 'free').slice(1)} ${tx('mobileSubscriptions.status.planSuffix', 'Plan')}`;
  const renewalLabel = status?.expires_at
    ? new Date(status.expires_at).toLocaleDateString(undefined, { year: 'numeric', month: 'long', day: 'numeric' })
    : tx('mobileSubscriptions.defaults.na', 'N/A');

  return (
    <View style={{ flexDirection: 'row', gap: 12, flexWrap: 'wrap' }}>
      <BillingSectionCard colors={colors} testId="iap-status-card" style={{ flex: 1.6, minWidth: 320 }}>
        <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12, flexWrap: 'wrap' }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 12, flex: 1 }}>
            <View style={{ width: 52, height: 52, borderRadius: 16, backgroundColor: `${statusTone}18`, alignItems: 'center', justifyContent: 'center' }}>
              <Ionicons name={status?.platform === 'apple' ? 'logo-apple' : status?.platform === 'google' ? 'logo-google-playstore' : 'phone-portrait-outline'} size={24} color={statusTone} />
            </View>
            <View style={{ flex: 1 }}>
              <Text style={{ color: colors.text, fontSize: 18, fontWeight: '900' }} {...getTestProps('iap-status-plan-label')}>{planLabel}</Text>
              <Text style={{ color: colors.textMuted, fontSize: 12, marginTop: 4 }} {...getTestProps('iap-status-store-label')}>
                {hasStoreLinkedSubscription
                  ? `${tx('mobileSubscriptions.common.via', 'via')} ${storeLabel}`
                  : hasActivePlatformPlan
                    ? tx('mobileSubscriptions.status.activeWithoutStore', 'Platform subscription is active, but no Apple/Google receipt is currently attached to this account.')
                    : tx('mobileSubscriptions.status.purchaseHint', 'Purchase from the mobile app to activate a store-linked subscription.')}
              </Text>
            </View>
          </View>

          <View style={{ flexDirection: 'row', gap: 8, alignItems: 'center' }}>
            <View style={{ paddingHorizontal: 10, paddingVertical: 6, borderRadius: 999, backgroundColor: `${statusTone}18`, borderWidth: 1, borderColor: `${statusTone}44` }} {...getTestProps('iap-status-badge')}>
              <Text style={{ color: statusTone, fontSize: 11, fontWeight: '800' }}>{hasStoreLinkedSubscription ? (String(status?.status || '').toLowerCase() === 'active' ? tx('mobileSubscriptions.status.active', 'Active') : tx('mobileSubscriptions.status.expired', 'Expired')) : tx('mobileSubscriptions.status.unattached', 'Unattached')}</Text>
            </View>
            <TouchableOpacity onPress={onRefresh} style={{ width: 38, height: 38, borderRadius: 12, backgroundColor: colors.bgSoft, borderWidth: 1, borderColor: colors.border, alignItems: 'center', justifyContent: 'center' }} {...getTestProps('iap-status-refresh-button')} accessibilityLabel="refresh button">
              <Ionicons name="refresh" size={16} color={colors.text} />
            </TouchableOpacity>
          </View>
        </View>

        <View style={{ flexDirection: 'row', gap: 12, flexWrap: 'wrap', marginTop: 16 }}>
          <BillingMetricCard label={tx('mobileSubscriptions.details.autoRenewal', 'Auto-Renewal')} value={status?.auto_renewing ? tx('mobileSubscriptions.common.on', 'On') : tx('mobileSubscriptions.common.off', 'Off')} helper={tx('iap.status.autoRenewHelper', 'Derived from the latest store-linked subscription status payload.')} colors={colors} icon="sync-outline" testId="iap-status-auto-renew-card" />
          <BillingMetricCard label={hasStoreLinkedSubscription ? tx('mobileSubscriptions.details.renewsOn', 'Renews on') : tx('mobileSubscriptions.details.lastTransaction', 'Last Transaction')} value={hasStoreLinkedSubscription ? renewalLabel : (status?.latest_transaction?.created_at ? new Date(status.latest_transaction.created_at).toLocaleDateString() : tx('mobileSubscriptions.defaults.na', 'N/A'))} helper={hasStoreLinkedSubscription ? tx('iap.status.renewalHelper', 'Shown only when the account is linked to an App Store or Google Play subscription.') : tx('iap.status.transactionHelper', 'No store-linked subscription yet, so the latest known IAP transaction date is shown instead.')} colors={colors} icon="calendar-outline" testId="iap-status-renewal-card" />
          <BillingMetricCard label={tx('mobileSubscriptions.history.title', 'Purchase History')} value={String(historyCount)} helper={tx('iap.status.historyHelper', 'Real in-app purchase transaction rows currently attached to this account.')} colors={colors} icon="receipt-outline" testId="iap-status-history-count-card" />
        </View>

        <View style={{ marginTop: 16 }}>
          <Text style={{ color: colors.text, fontSize: 13, fontWeight: '900', marginBottom: 10 }}>{tx('mobileSubscriptions.manage.title', 'Upgrade • Downgrade • Cancel')}</Text>
          <View style={{ flexDirection: 'row', gap: 10, flexWrap: 'wrap' }}>
            <BillingActionButton label={tx('mobileSubscriptions.manage.apple', 'Manage in Apple')} onPress={() => onOpenManageLink('apple')} icon="logo-apple" colors={colors} testId="iap-manage-apple-button" variant={manageLinks.apple ? 'secondary' : 'subtle'} />
            <BillingActionButton label={tx('mobileSubscriptions.manage.google', 'Manage in Google Play')} onPress={() => onOpenManageLink('google')} icon="logo-google-playstore" colors={colors} testId="iap-manage-google-button" variant={manageLinks.google ? 'primary' : 'subtle'} />
          </View>
          <Text style={{ color: colors.textMuted, fontSize: 11, lineHeight: 17, marginTop: 10 }} {...getTestProps('iap-manage-note')}>
            {tx('mobileSubscriptions.manage.subtitle', 'Subscription upgrades, downgrades, and cancellations must be completed in the originating app store. This dashboard reflects those changes once the store/webhook cycle finishes.')}
          </Text>
        </View>
      </BillingSectionCard>
    </View>
  );
};

/* i18n-probe t('i18n.auto.probe') */
