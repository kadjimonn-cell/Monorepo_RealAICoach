import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { ActivityIndicator, AppState, Linking, Platform, ScrollView, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { LinearGradient } from 'expo-linear-gradient';
import { Ionicons } from '@expo/vector-icons';
import { useLocalSearchParams, useRouter } from 'expo-router';
import api, { clearCache } from '../services/api';
import { useTranslation } from '../hooks/useTranslation';
import { useTheme } from '../context/ThemeContext';
import { BillingHeroPill } from './BillingRoutePrimitives';
import { IAPCheckoutReviewModal } from './iap/IAPCheckoutReviewModal';
import { IAPReadinessMatrix } from './iap/IAPReadinessMatrix';
import { IAPStatusOverview } from './iap/IAPStatusOverview';
import { IAPPlansGrid } from './iap/IAPPlansGrid';
import { IAPTimelineHistory } from './iap/IAPTimelineHistory';
import { SubscriptionUnlockedDestinationSummary } from './payment/SubscriptionUnlockedDestinationSummary';
import { SubscriptionSuccessPanel } from './payment/SubscriptionSuccessPanel';
import { formatAmount } from './paymentHistory/utils';
import { normalizeReturnTarget } from '../utils/subscriptionReturnTarget';
import { stashSubscriptionReturnToast } from '../utils/subscriptionReturnToast';
import { notificationEvents } from '../utils/notificationEvents';
import { getTestProps } from '../utils/testProps';
import { getPaymentFailureCopy, normalizePaymentFailureState } from '../utils/paymentFailureCopy';

const IAP_REFRESH_MS = 60000;

export default function MobileSubscriptionsViewV2() {
  const router = useRouter();
  const params = useLocalSearchParams<{
    billingPeriod?: string;
    origin?: string;
    planId?: string;
    planName?: string;
    provider?: string;
    return_to?: string;
  }>();
  const { colors } = useTheme();
  const { t } = useTranslation();
  const tx = useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);
  const palette = useMemo(() => ({
    ...colors,
    heroStart: colors.text,
    heroMid: colors.primary,
    heroEnd: colors.info,
  }), [colors]);
  const [status, setStatus] = useState<any>(null);
  const [history, setHistory] = useState<any[]>([]);
  const [products, setProducts] = useState<any[]>([]);
  const [timeline, setTimeline] = useState<any[]>([]);
  const [manageLinks, setManageLinks] = useState<{ apple?: string; google?: string }>({});
  const [iapReadiness, setIapReadiness] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [selectedCheckout, setSelectedCheckout] = useState<any | null>(null);

  const loadData = useCallback(async (refreshMode = false) => {
    try {
      if (!refreshMode) setLoading(true);
      ['/iap/status', '/iap/history', '/iap/products', '/iap/manage-links', '/iap/timeline', '/iap/readiness'].forEach((path) => clearCache(path));
      const cacheBust = Date.now();
      const [statusRes, historyRes, productsRes, manageRes, timelineRes, readinessRes] = await Promise.all([
        api.get(`/iap/status?cb=${cacheBust}`, { skipDedupe: true }),
        api.get(`/iap/history?cb=${cacheBust}`, { skipDedupe: true }),
        api.get(`/iap/products?cb=${cacheBust}`, { skipDedupe: true }),
        api.get(`/iap/manage-links?cb=${cacheBust}`, { skipDedupe: true }).catch(() => ({ data: {} })),
        api.get(`/iap/timeline?cb=${cacheBust}`, { skipDedupe: true }).catch(() => ({ data: { events: [] } })),
        api.get(`/iap/readiness?cb=${cacheBust}`, { skipDedupe: true }).catch(() => ({ data: null })),
      ]);
      setStatus(statusRes.data || null);
      setHistory(historyRes.data?.transactions || []);
      setProducts(productsRes.data?.products || []);
      setManageLinks({ apple: manageRes.data?.apple, google: manageRes.data?.google });
      setTimeline(timelineRes.data?.events || []);
      setIapReadiness(readinessRes.data || null);
    } catch (error) {
      console.error('In-App Purchases load error:', error);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  useEffect(() => {
    const timer = setInterval(() => {
      if (Platform.OS === 'web' && typeof document !== 'undefined' && document.hidden) return;
      void loadData(true);
    }, IAP_REFRESH_MS);
    return () => clearInterval(timer);
  }, [loadData]);

  useEffect(() => {
    const appStateSubscription = AppState.addEventListener('change', (nextState) => {
      if (nextState === 'active') {
        void loadData(true);
      }
    });

    const handleVisibilityChange = () => {
      if (typeof document !== 'undefined' && !document.hidden) {
        void loadData(true);
      }
    };

    if (Platform.OS === 'web' && typeof document !== 'undefined') {
      document.addEventListener('visibilitychange', handleVisibilityChange);
    }

    return () => {
      appStateSubscription.remove();
      if (Platform.OS === 'web' && typeof document !== 'undefined') {
        document.removeEventListener('visibilitychange', handleVisibilityChange);
      }
    };
  }, [loadData]);

  const readinessRows = Array.isArray(iapReadiness?.matrix)
    ? iapReadiness.matrix
    : [iapReadiness?.providers?.apple, iapReadiness?.providers?.google].filter(Boolean);
  const routeProvider = String(params.provider || '').toLowerCase() === 'google' ? 'google' : String(params.provider || '').toLowerCase() === 'apple' ? 'apple' : null;
  const routeOrigin = String(params.origin || '');
  const requestedPlanId = String(params.planId || '').toLowerCase();
  const requestedPlanName = String(params.planName || '').trim();
  const requestedBillingPeriod = String(params.billingPeriod || '').toLowerCase();
  const smartReturnTarget = useMemo(() => normalizeReturnTarget(String(params.return_to || '/dashboard')), [params.return_to]);
  const requestedProduct = useMemo(() => products.find((product) => {
    const matchesPlan = requestedPlanId ? String(product?.plan || '').toLowerCase() === requestedPlanId : true;
    const matchesPeriod = requestedBillingPeriod ? String(product?.period || '').toLowerCase() === requestedBillingPeriod : true;
    return matchesPlan && matchesPeriod;
  }) || null, [products, requestedBillingPeriod, requestedPlanId]);
  const activePlanLabel = `${String(status?.plan || 'free').charAt(0).toUpperCase()}${String(status?.plan || 'free').slice(1)}`;
  const refreshNote = `${tx('iap.header.refreshWindow', 'Live status refreshes every')} ${IAP_REFRESH_MS / 1000}s`;
  const routePlanLabel = requestedPlanName
    || requestedProduct?.display_name
    || `${requestedPlanId ? `${requestedPlanId.charAt(0).toUpperCase()}${requestedPlanId.slice(1)}` : activePlanLabel} ${tx('mobileSubscriptions.status.planSuffix', 'Plan')}`;
  const routeProviderLabel = routeProvider === 'apple'
    ? tx('mobileSubscriptions.providers.apple', 'Apple App Store')
    : routeProvider === 'google'
      ? tx('mobileSubscriptions.providers.googleStore', 'Google Play Store')
      : tx('mobileSubscriptions.status.noStoreAttached', 'No store receipt attached');
  const requestedEstimate = routeProvider && requestedProduct ? requestedProduct?.checkout_estimates?.[routeProvider] || null : null;
  const requestedAmountText = requestedEstimate
    ? formatAmount(Number(requestedEstimate?.final_total || requestedEstimate?.total_amount || requestedProduct?.price || 0), requestedProduct?.currency || 'USD')
    : requestedProduct?.price
      ? formatAmount(Number(requestedProduct.price || 0), requestedProduct?.currency || 'USD')
      : null;
  const isStoreCheckoutJourney = routeOrigin === 'subscribe_pay' && Boolean(routeProvider);
  const hasActivatedRequestedStorePlan = isStoreCheckoutJourney
    && String(status?.status || '').toLowerCase() === 'active'
    && String(status?.platform || '').toLowerCase() === routeProvider
    && (!requestedPlanId || String(status?.plan || '').toLowerCase() === requestedPlanId);
  const hasObservedInactiveStoreStatus = isStoreCheckoutJourney
    && Boolean(routeProvider)
    && String(status?.platform || '').toLowerCase() === routeProvider
    && ['expired', 'cancelled', 'canceled', 'revoked'].includes(String(status?.status || '').toLowerCase());

  const openStoreLink = useCallback(async (url: string) => {
    if (!url) return;
    try {
      const supported = await Linking.canOpenURL(url);
      if (supported) await Linking.openURL(url);
    } catch (error) {
      console.error('Failed opening external store link', error);
    }
  }, []);

  const getStoreLink = useCallback((provider: 'apple' | 'google') => {
    const fallback = provider === 'apple'
      ? 'https://apps.apple.com/account/subscriptions'
      : 'https://play.google.com/store/account/subscriptions';
    const candidate = provider === 'apple' ? manageLinks.apple : manageLinks.google;
    return candidate && /^https:\/\//i.test(candidate) ? candidate : fallback;
  }, [manageLinks.apple, manageLinks.google]);

  const openManageLink = useCallback((provider: 'apple' | 'google') => {
    void openStoreLink(getStoreLink(provider));
  }, [getStoreLink, openStoreLink]);

  const openCheckoutReview = useCallback((product: any, provider: 'apple' | 'google') => {
    setSelectedCheckout({
      product,
      provider,
      estimate: product?.checkout_estimates?.[provider] || {},
      manageUrl: getStoreLink(provider),
      readiness: iapReadiness?.providers?.[provider],
    });
  }, [getStoreLink, iapReadiness?.providers]);

  const handoffPanelConfig = useMemo(() => {
    if (!isStoreCheckoutJourney || !routeProvider) return null;

    if (hasActivatedRequestedStorePlan) {
      return {
        title: tx('iap.success.title', 'Subscription activated'),
        subtitle: tx('iap.success.subtitle', 'Your store purchase is now synced with RealAICoach. You can return to your upgraded destination now.'),
        ctaLabel: tx('payment.success.startExploring', 'Start Exploring'),
        amountText: requestedAmountText,
        badgeText: `${tx('autofix.batch9.paid.via', 'Paid via')} ${routeProviderLabel}`,
        onPressCta: () => {
          stashSubscriptionReturnToast(smartReturnTarget, routePlanLabel);
          router.replace(smartReturnTarget as any);
        },
      };
    }

    return {
      title: tx('iap.handoff.title', 'Store checkout ready'),
      subtitle: tx('iap.handoff.subtitle', 'Continue in {provider} to complete the purchase. When you come back, this page will refresh and confirm your access.').replace('{provider}', routeProviderLabel),
      ctaLabel: tx('mobileSubscriptions.pricing.continueToStore', 'Continue to store'),
      amountText: requestedAmountText,
      badgeText: `${routePlanLabel} • ${routeProviderLabel}`,
      onPressCta: () => {
        void openStoreLink(getStoreLink(routeProvider));
      },
    };
  }, [getStoreLink, hasActivatedRequestedStorePlan, isStoreCheckoutJourney, openStoreLink, requestedAmountText, routePlanLabel, routeProvider, routeProviderLabel, router, smartReturnTarget, tx]);

  useEffect(() => {
    if (!hasObservedInactiveStoreStatus || !routeProvider) return;
    const reason = normalizePaymentFailureState(String(status?.status || '').toLowerCase());
    const copy = getPaymentFailureCopy(reason === 'refunded' ? 'refunded' : reason === 'expired' ? 'expired' : reason === 'cancelled' ? 'cancelled' : 'failed', routeProviderLabel, tx);
    notificationEvents.emit('toast', {
      title: copy.title,
      message: copy.message,
      type: copy.tone === 'error' ? 'payment_failed' : 'warning',
      actionLabel: tx('common.tryAgain', 'Try Again'),
      actionRoute: '/subscription/mobile',
    });
  }, [hasObservedInactiveStoreStatus, routeProvider, routeProviderLabel, status?.status, tx]);

  if (loading) {
    return (
      <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center', padding: 60 }} {...getTestProps('iap-page-loading-state')}>
        <ActivityIndicator size="large" color={palette.primary} />
      </View>
    );
  }

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: palette.bg }} edges={['top']}>
      <ScrollView contentContainerStyle={{ padding: 16, paddingBottom: 40, gap: 12 }} {...getTestProps('iap-page-scroll')}>
        <LinearGradient colors={[palette.heroStart, palette.heroMid, palette.heroEnd]} start={{ x: 0, y: 0 }} end={{ x: 1, y: 1 }} style={{ borderRadius: 24, padding: 20, borderWidth: 1, borderColor: palette.border }} {...getTestProps('iap-page-header')}>
          <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start', gap: 16, flexWrap: 'wrap' }}>
            <View style={{ flex: 1, minWidth: 220 }}>
              <Text style={{ color: palette.primaryText + 'D9', fontSize: 11, fontWeight: '800', textTransform: 'uppercase', letterSpacing: 1 }}>{tx('mobileSubscriptions.header.eyebrow', 'Enterprise subscription command center')}</Text>
              <Text style={{ color: palette.primaryText, fontSize: 30, fontWeight: '900', marginTop: 10, letterSpacing: -0.8 }} {...getTestProps('mobile-subs-title')}>
                {tx('mobileSubscriptions.header.title', 'In-App Purchases')}
              </Text>
              <Text style={{ color: palette.primaryText + 'D9', fontSize: 13, lineHeight: 20, marginTop: 8 }} {...getTestProps('mobile-subs-subtitle')}>
                {tx('mobileSubscriptions.header.subtitle', 'Manage store-linked subscriptions, checkout estimates, readiness states, and billing history using platform data only.')}
              </Text>
            </View>
            <View style={{ flexDirection: 'row', gap: 10, flexWrap: 'wrap' }}>
              <BillingHeroPill label={tx('mobileSubscriptions.header.activePlan', 'Current plan')} value={activePlanLabel} colors={palette} testId="iap-header-plan-pill" />
            </View>
          </View>
          <View style={{ flexDirection: 'row', gap: 8, alignItems: 'center', marginTop: 16 }}>
            <Ionicons name="pulse-outline" size={15} color={palette.primaryText} />
            <Text style={{ color: palette.primaryText + 'D9', fontSize: 11, fontWeight: '700' }}>{refreshNote}</Text>
          </View>
        </LinearGradient>

        {handoffPanelConfig ? (
          <View
            style={{ borderRadius: 24, borderWidth: 1, borderColor: hasActivatedRequestedStorePlan ? `${palette.success}55` : palette.border, backgroundColor: palette.card, padding: 20 }}
            {...getTestProps(hasActivatedRequestedStorePlan ? 'iap-native-success-card' : 'iap-store-handoff-card')}
          >
            <SubscriptionSuccessPanel
              amountText={handoffPanelConfig.amountText}
              badgeText={handoffPanelConfig.badgeText}
              ctaLabel={handoffPanelConfig.ctaLabel}
              colors={{
                success: hasActivatedRequestedStorePlan ? palette.success : palette.primary,
                successText: hasActivatedRequestedStorePlan ? palette.successText : palette.primary,
                successSoft: hasActivatedRequestedStorePlan ? palette.successSoft : palette.primarySoft,
                text: palette.text,
                textMuted: palette.textMuted,
                border: palette.border,
                bgSoft: palette.bgSoft,
                primaryText: palette.primaryText,
              }}
              historyLabel={tx('paymentResult.actions.viewHistory', 'View Payment History')}
              onPressCta={handoffPanelConfig.onPressCta}
              onPressHistory={() => router.push('/payment-history' as any)}
              preCtaContent={hasActivatedRequestedStorePlan ? (
                <SubscriptionUnlockedDestinationSummary
                  colors={{
                    success: palette.success,
                    successText: palette.successText,
                    text: palette.text,
                    textMuted: palette.textMuted,
                    bgSoft: palette.bgSoft,
                  }}
                  planName={routePlanLabel}
                  providerKey={routeProvider || 'unknown'}
                  providerLabel={routeProviderLabel}
                  returnTarget={smartReturnTarget}
                  testIdPrefix="iap-native-unlocked"
                  tx={tx}
                />
              ) : null}
              subtitle={handoffPanelConfig.subtitle}
              title={handoffPanelConfig.title}
            />
            <View style={{ flexDirection: 'row', gap: 8, alignItems: 'center', marginTop: 14 }} {...getTestProps('iap-store-handoff-refresh-note')}>
              <Ionicons name={hasActivatedRequestedStorePlan ? 'checkmark-done-circle-outline' : 'sync-outline'} size={16} color={hasActivatedRequestedStorePlan ? palette.successText : palette.textMuted} />
              <Text style={{ color: palette.textMuted, fontSize: 12, lineHeight: 18, flex: 1 }}>
                {hasActivatedRequestedStorePlan
                  ? tx('iap.success.helper', 'Your store receipt is attached. Payment history and your upgraded destination are ready.')
                  : tx('iap.handoff.helper', 'After finishing in the store, come back here or reopen this page. RealAICoach will refresh your linked subscription automatically.')}
              </Text>
            </View>
          </View>
        ) : null}

        <View style={{ flexDirection: 'row', gap: 12, flexWrap: 'wrap' }}>
          <IAPStatusOverview colors={palette} status={status} historyCount={history.length} manageLinks={manageLinks} tx={tx} onRefresh={() => { setLoading(true); loadData(); }} onOpenManageLink={openManageLink} />
          <IAPReadinessMatrix colors={palette} readinessRows={readinessRows} tx={tx} />
        </View>

        <IAPPlansGrid colors={palette} products={products} status={status} tx={tx} onOpenReview={openCheckoutReview} />
        <IAPTimelineHistory colors={palette} timeline={timeline} history={history} tx={tx} />
      </ScrollView>

      <IAPCheckoutReviewModal
        visible={Boolean(selectedCheckout)}
        selection={selectedCheckout}
        colors={palette}
        tx={tx}
        onClose={() => setSelectedCheckout(null)}
        onContinue={(selection) => {
          setSelectedCheckout(null);
          void openStoreLink(selection.manageUrl);
        }}
      />
    </SafeAreaView>
  );
}
