import React, { useState, useEffect, useCallback } from 'react';
import { View, Text, TouchableOpacity, ActivityIndicator, ScrollView, Platform, Linking } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api, { clearCache } from '../services/api';
import { useAuth } from '../context/AuthContext';
import { useTranslation } from '../hooks/useTranslation';
import { useTheme } from '../context/ThemeContext';
import MobileSubscriptionsViewV2 from './MobileSubscriptionsViewV2';

function LegacyMobileSubscriptionsView() {
  const { colors } = useTheme();
  const C = {
    bg: colors.bg,
    card: colors.card,
    cardHover: colors.bgSoft,
    cardAlt: colors.bgSoft,
    surface: colors.bg,
    border: colors.border,
    text: colors.text,
    textSec: colors.textSec || colors.textSecondary || colors.text,
    textMuted: colors.textMuted,
    dim: colors.textMuted,
    primary: colors.primary, success: colors.success, warning: colors.warning, error: colors.error,
    purple: colors.purple, cyan: colors.info,
    successText: colors.successText || colors.success,
    primaryText: colors.primaryText || 'var(--app-primary-text)',
  };
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const { _user } = useAuth();
  const { t } = useTranslation();
  const tx = useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);
  const [status, setStatus] = useState<any>(null);
  const [history, setHistory] = useState<any[]>([]);
  const [products, setProducts] = useState<any[]>([]);
  const [timeline, setTimeline] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [showIapFeeExplainer, setShowIapFeeExplainer] = useState(false);
  const [manageLinks, setManageLinks] = useState<{ apple?: string; google?: string }>({});
  const [iapReadiness, setIapReadiness] = useState<any>(null);
  const [jurisdictionContext, setJurisdictionContext] = useState<any>(null);
  const [confirmationMap, setConfirmationMap] = useState<Record<string, boolean>>({});

  const feeText = React.useMemo(() => {
    const safe = (key: string, fallback: string) => {
      const value = t(key);
      return value === key ? fallback : value;
    };
    return {
      title: safe('fees.explainer.title', 'Why these fees?'),
      line1: safe('fees.explainer.line1', 'Base Subscription Price: the plan amount before taxes and payment handling fees.'),
      line2: safe('fees.explainer.line2', 'Applicable Tax: calculated from your checkout jurisdiction and provider policy.'),
      line3: safe('fees.explainer.line3', 'Payment Processing Fee: charged by the payment/store channel for handling the transaction.'),
      line4: safe('fees.explainer.line4', 'Total You Pay: Base Subscription Price + Applicable Tax + Payment Processing Fee.'),
    };
  }, [t]);

  const loadData = useCallback(async () => {
    try {
      clearCache('/iap/status');
      clearCache('/iap/history');
      clearCache('/iap/products');
      clearCache('/iap/manage-links');
      clearCache('/iap/timeline');
      clearCache('/iap/readiness');

      const cacheBust = Date.now();
      const [statusRes, historyRes, prodRes, manageRes, timelineRes, readinessRes] = await Promise.all([
        api.get(`/iap/status?cb=${cacheBust}`),
        api.get(`/iap/history?cb=${cacheBust}`),
        api.get(`/iap/products?cb=${cacheBust}`),
        api.get(`/iap/manage-links?cb=${cacheBust}`).catch(() => ({ data: {} })),
        api.get(`/iap/timeline?cb=${cacheBust}`).catch(() => ({ data: { events: [] } })),
        api.get(`/iap/readiness?cb=${cacheBust}`).catch(() => ({ data: null })),
      ]);
      setStatus(statusRes.data);
      setHistory(historyRes.data.transactions || []);
      setProducts(prodRes.data.products || []);
      setManageLinks({ apple: manageRes.data?.apple, google: manageRes.data?.google });
      setTimeline(timelineRes.data?.events || []);
      setIapReadiness(readinessRes.data || null);
      setJurisdictionContext(prodRes.data?.jurisdiction_context || statusRes.data?.jurisdiction_context || null);
    } catch (e) {
      console.error('In-App Purchases load error:', e);
    } finally {
      setLoading(false);
    }
  }, []);

  const toggleConfirmation = useCallback((key: string) => {
    setConfirmationMap((prev) => ({ ...prev, [key]: !prev[key] }));
  }, []);

  const openStoreLink = useCallback(async (url: string) => {
    if (!url) return;
    try {
      const supported = await Linking.canOpenURL(url);
      if (supported) {
        await Linking.openURL(url);
      }
    } catch (e) {
      console.error('Failed opening external store link', e);
    }
  }, []);

  const getStoreLink = useCallback((provider: 'apple' | 'google') => {
    const fallback = provider === 'apple'
      ? 'https://apps.apple.com/account/subscriptions'
      : 'https://play.google.com/store/account/subscriptions';
    const candidate = provider === 'apple' ? manageLinks.apple : manageLinks.google;
    if (candidate && /^https:\/\//i.test(candidate)) return candidate;
    return fallback;
  }, [manageLinks.apple, manageLinks.google]);

  useEffect(() => { loadData(); }, [loadData]);
  useEffect(() => {
    const iv = setInterval(() => {
      loadData();
    }, 15000);
    return () => clearInterval(iv);
  }, [loadData]);

  if (loading) {
    return (
      <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center', padding: 60 }}>
        <ActivityIndicator size="large" color={C.primary} />
      </View>
    );
  }

  const hasMobileSub = status?.platform && status.platform !== null;
  const isActive = status?.status === 'active' && status?.plan !== 'free';
  const platformLabel = status?.platform === 'apple'
    ? tx('mobileSubscriptions.providers.apple', 'Apple App Store')
    : status?.platform === 'google'
      ? tx('mobileSubscriptions.providers.googleStore', 'Google Play Store')
      : null;
  const platformIcon = status?.platform === 'apple' ? 'logo-apple' : status?.platform === 'google' ? 'logo-google-playstore' : 'phone-portrait-outline';
  const planColor = status?.plan === 'premium' ? C.purple : status?.plan === 'basic' ? C.primary : C.textMuted;
  const readinessRows = Array.isArray(iapReadiness?.matrix)
    ? iapReadiness.matrix
    : [
        iapReadiness?.providers?.apple,
        iapReadiness?.providers?.google,
      ].filter(Boolean);

  return (
    <ScrollView style={{ flex: 1 }} contentContainerStyle={{ padding: 20, gap: 20 }}>
      {/* Header */}
      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
        <View>
          <Text style={{ color: C.text, fontSize: 22, fontWeight: '700' }} data-testid="mobile-subs-title" testID="mobile-subs-title">{tx('mobileSubscriptions.header.title', 'In-App Purchases')}</Text>
          <Text style={{ color: C.textMuted, fontSize: 13, marginTop: 2 }}>{tx('mobileSubscriptions.header.subtitle', 'Manage your App Store & Google Play purchases')}</Text>
        </View>
        <TouchableOpacity onPress={() => { setLoading(true); loadData(); }} style={{ width: 36, height: 36, borderRadius: 10, backgroundColor: C.card, alignItems: 'center', justifyContent: 'center', borderWidth: 1, borderColor: C.border }} data-testid="mobile-subs-refresh" testID="mobile-subs-refresh">
          <Ionicons name="refresh" size={16} color={C.textSec} />
        </TouchableOpacity>
      </View>

      {/* Current Status Card */}
      <View style={{ backgroundColor: C.card, borderRadius: 14, padding: 20, borderWidth: 1, borderColor: C.border }} data-testid="mobile-subs-status-card" testID="mobile-subs-status-card">
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 12, marginBottom: 16 }}>
          <View style={{ width: 48, height: 48, borderRadius: 14, backgroundColor: (globalThis as any).__alphaColor(planColor, '18'), alignItems: 'center', justifyContent: 'center' }}>
            <Ionicons name={platformIcon as any} size={24} color={planColor} />
          </View>
          <View style={{ flex: 1 }}>
            <Text style={{ color: C.text, fontSize: 16, fontWeight: '700' }}>
              {hasMobileSub
                ? `${(status.plan || tx('mobileSubscriptions.defaults.free', 'Free')).charAt(0).toUpperCase() + (status.plan || 'free').slice(1)} ${tx('mobileSubscriptions.status.planSuffix', 'Plan')}`
                : tx('mobileSubscriptions.status.none', 'No In-App Purchases')}
            </Text>
            <Text style={{ color: C.textMuted, fontSize: 12, marginTop: 2 }}>
              {hasMobileSub ? `${tx('mobileSubscriptions.common.via', 'via')} ${platformLabel}` : tx('mobileSubscriptions.status.purchaseHint', 'Purchase from the mobile app to activate')}
            </Text>
          </View>
          {hasMobileSub && (
            <View style={{ paddingHorizontal: 10, paddingVertical: 5, borderRadius: 8, backgroundColor: isActive ? (globalThis as any).__alphaColor(C.success, '18') : C.error + '18' }}>
              <Text style={{ color: isActive ? C.success : C.error, fontSize: 11, fontWeight: '700' }}>
                {isActive ? tx('mobileSubscriptions.status.active', 'Active') : tx('mobileSubscriptions.status.expired', 'Expired')}
              </Text>
            </View>
          )}
        </View>

        {hasMobileSub && (
          <View style={{ gap: 10, borderTopWidth: 1, borderTopColor: C.border, paddingTop: 14 }}>
            <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
              <Text style={{ color: C.textMuted, fontSize: 12 }}>{tx('mobileSubscriptions.details.product', 'Product')}</Text>
              <Text style={{ color: C.textSec, fontSize: 12 }}>{status.product_id || tx('mobileSubscriptions.defaults.na', 'N/A')}</Text>
            </View>
            {status.expires_at && (
              <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
                <Text style={{ color: C.textMuted, fontSize: 12 }}>{isActive ? tx('mobileSubscriptions.details.renewsOn', 'Renews on') : tx('mobileSubscriptions.details.expiredOn', 'Expired on')}</Text>
                <Text style={{ color: C.textSec, fontSize: 12 }}>{new Date(status.expires_at).toLocaleDateString(undefined, { year: 'numeric', month: 'long', day: 'numeric' })}</Text>
              </View>
            )}
            <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
              <Text style={{ color: C.textMuted, fontSize: 12 }}>{tx('mobileSubscriptions.details.autoRenewal', 'Auto-Renewal')}</Text>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}>
                <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: status.auto_renewing ? C.success : C.warning }} />
                <Text style={{ color: C.textSec, fontSize: 12 }}>{status.auto_renewing ? tx('mobileSubscriptions.common.on', 'On') : tx('mobileSubscriptions.common.off', 'Off')}</Text>
              </View>
            </View>
            {status.latest_transaction && (
              <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
                <Text style={{ color: C.textMuted, fontSize: 12 }}>{tx('mobileSubscriptions.details.lastTransaction', 'Last Transaction')}</Text>
                <Text style={{ color: C.textSec, fontSize: 12 }}>{status.latest_transaction.created_at ? new Date(status.latest_transaction.created_at).toLocaleDateString() : tx('mobileSubscriptions.defaults.na', 'N/A')}</Text>
              </View>
            )}
          </View>
        )}
      </View>

      <View style={{ backgroundColor: C.card, borderRadius: 14, padding: 16, borderWidth: 1, borderColor: C.border }} data-testid="iap-gateway-readiness-matrix-card" testID="iap-gateway-readiness-matrix-card">
        <Text style={{ color: C.text, fontSize: 14, fontWeight: '800', marginBottom: 4 }} data-testid="iap-gateway-readiness-title" testID="iap-gateway-readiness-title">{tx('mobileSubscriptions.readiness.title', 'Gateway Readiness Matrix')}</Text>
        <Text style={{ color: C.textMuted, fontSize: 11, marginBottom: 10 }}>
          {tx('mobileSubscriptions.readiness.subtitle', 'Apple App Store + Google Play readiness states with explicit Live/Test/Sandbox visibility.')}
        </Text>
        <View style={{ gap: 8 }}>
          {readinessRows.map((row: any, idx: number) => {
            const state = String(row?.readiness_state || '').toLowerCase();
            const tone = state.includes('live') ? C.success : state.includes('sandbox') || state.includes('test') ? C.warning : C.error;
            const icon = String(row?.provider || '').includes('apple') ? 'logo-apple' : 'logo-google-playstore';
            return (
              <View key={`${row?.provider || idx}`} style={{ borderRadius: 10, borderWidth: 1, borderColor: `${tone}66`, backgroundColor: `${tone}1A`, padding: 10, flexDirection: 'row', alignItems: 'center', gap: 10 }} data-testid={`iap-readiness-row-${row?.provider || idx}`} testID={`iap-readiness-row-${row?.provider || idx}`}>
                <Ionicons name={icon as any} size={18} color={tone} />
                <View style={{ flex: 1 }}>
                  <Text style={{ color: tone, fontSize: 11, fontWeight: '800' }}>{row?.label || row?.provider || tx('mobileSubscriptions.readiness.providerFallback', 'IAP Provider')}: {row?.status_label || tx('mobileSubscriptions.readiness.unavailable', 'Unavailable')}</Text>
                  <Text style={{ color: C.textSec, fontSize: 10, marginTop: 2 }}>{row?.message || tx('mobileSubscriptions.readiness.signalUnavailable', 'Readiness signal unavailable.')}</Text>
                </View>
                <View style={{ borderRadius: 999, borderWidth: 1, borderColor: `${tone}88`, backgroundColor: `${tone}22`, paddingHorizontal: 8, paddingVertical: 4 }}>
                  <Text style={{ color: tone, fontSize: 9, fontWeight: '800', textTransform: 'uppercase' }}>{row?.mode || tx('mobileSubscriptions.defaults.unknown', 'unknown')}</Text>
                </View>
              </View>
            );
          })}
          {readinessRows.length === 0 ? (
            <Text style={{ color: C.textMuted, fontSize: 11 }} data-testid="iap-readiness-empty-state" testID="iap-readiness-empty-state">{tx('mobileSubscriptions.readiness.empty', 'No provider readiness data available.')}</Text>
          ) : null}
        </View>
      </View>

      {hasMobileSub && platformLabel && (
        <View style={{ backgroundColor: C.card, borderRadius: 14, padding: 16, borderWidth: 1, borderColor: C.border }} data-testid="mobile-subs-manage-actions-card" testID="mobile-subs-manage-actions-card">
          <Text style={{ color: C.text, fontSize: 14, fontWeight: '700', marginBottom: 6 }}>{tx('mobileSubscriptions.manage.title', 'Upgrade • Downgrade • Cancel')}</Text>
          <Text style={{ color: C.textMuted, fontSize: 11, marginBottom: 10 }}>
            {tx('mobileSubscriptions.manage.subtitle', 'Manage subscription changes securely in {platform}. Actions are synced back to this platform via store webhooks.').replace('{platform}', String(platformLabel))}
          </Text>
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
            {[
              tx('mobileSubscriptions.manage.actions.upgrade', 'Upgrade'),
              tx('mobileSubscriptions.manage.actions.downgrade', 'Downgrade'),
              tx('mobileSubscriptions.manage.actions.cancel', 'Cancel'),
            ].map((action) => (
              <TouchableOpacity
                key={action}
                onPress={() => openStoreLink(status?.platform === 'apple' ? getStoreLink('apple') : getStoreLink('google'))}
                style={{ borderWidth: 1, borderColor: C.border, borderRadius: 999, paddingHorizontal: 10, paddingVertical: 6, backgroundColor: C.cardHover }}
                data-testid={`mobile-subs-manage-${action.toLowerCase()}-button`} testID={`mobile-subs-manage-${action.toLowerCase()}-button`}
              >
                <Text style={{ color: C.textSec, fontSize: 11, fontWeight: '700' }}>{action}</Text>
              </TouchableOpacity>
            ))}
          </View>
        </View>
      )}

      <View style={{ backgroundColor: C.card, borderRadius: 14, padding: 16, borderWidth: 1, borderColor: C.border }} data-testid="mobile-subscription-timeline-card" testID="mobile-subscription-timeline-card">
        <Text style={{ color: C.text, fontSize: 14, fontWeight: '700', marginBottom: 8 }}>{tx('mobileSubscriptions.timeline.title', 'Subscription Timeline')}</Text>
        {(timeline || []).length === 0 ? (
          <Text style={{ color: C.textMuted, fontSize: 11 }}>{tx('mobileSubscriptions.timeline.empty', 'No timeline events yet.')}</Text>
        ) : (
          <View style={{ gap: 8 }}>
            {timeline.slice(0, 8).map((event: any, idx: number) => (
              <View key={`${event.event_id || idx}`} style={{ borderWidth: 1, borderColor: C.border, backgroundColor: C.cardAlt, borderRadius: 10, padding: 10 }} data-testid={`mobile-subscription-timeline-event-${idx}`} testID={`mobile-subscription-timeline-event-${idx}`}>
                <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
                  <Text style={{ color: C.textSec, fontSize: 11, fontWeight: '800', textTransform: 'uppercase' }}>{event.event_type || tx('mobileSubscriptions.timeline.defaults.update', 'update')}</Text>
                  <Text style={{ color: C.textMuted, fontSize: 10 }}>{event.platform || tx('mobileSubscriptions.timeline.defaults.store', 'store')}</Text>
                </View>
                <Text style={{ color: C.textMuted, fontSize: 11 }}>{tx('mobileSubscriptions.timeline.changeLine', 'From: {from} → To: {to} • Status: {status}')
                  .replace('{from}', String(event.from_plan || tx('mobileSubscriptions.defaults.freeLower', 'free')))
                  .replace('{to}', String(event.to_plan || tx('mobileSubscriptions.defaults.freeLower', 'free')))
                  .replace('{status}', String(event.status || tx('mobileSubscriptions.status.activeLower', 'active')))}</Text>
                <Text style={{ color: C.dim, fontSize: 10, marginTop: 3 }}>{tx('mobileSubscriptions.timeline.effective', 'Effective')}: {event.effective_at ? new Date(event.effective_at).toLocaleString() : '-'}</Text>
              </View>
            ))}
          </View>
        )}
      </View>

      {/* Info Banner */}
      {!hasMobileSub && (
        <View style={{ backgroundColor: (globalThis as any).__alphaColor(C.primary, '10'), borderRadius: 12, padding: 16, flexDirection: 'row', gap: 12, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(C.primary, '30') }} data-testid="mobile-subs-info-banner" testID="mobile-subs-info-banner">
          <Ionicons name="information-circle-outline" size={22} color={C.primary} />
          <View style={{ flex: 1 }}>
            <Text style={{ color: C.text, fontSize: 13, fontWeight: '600', marginBottom: 4 }}>{tx('mobileSubscriptions.info.title', 'How to subscribe via in-app purchases')}</Text>
            <Text style={{ color: C.textSec, fontSize: 12, lineHeight: 18 }}>
              {tx('mobileSubscriptions.info.subtitle', 'Download the RealAICoach app from the App Store or Google Play, then navigate to Subscription Plans within the app to purchase a plan. Your subscription will sync automatically with your web account.')}
            </Text>
          </View>
        </View>
      )}

      {/* Available Plans */}
      <View style={{ backgroundColor: C.card, borderRadius: 14, padding: 16, borderWidth: 1, borderColor: C.border }} data-testid="mobile-subs-plans" testID="mobile-subs-plans">
        {Platform.OS === 'web' ? <div data-testid="mobile-subs-plans" /> : null}
        <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14, gap: 8 }}>
          {Platform.OS === 'web' ? <div data-testid="mobile-subs-title" /> : null}
          <Text style={{ color: C.text, fontSize: 15, fontWeight: '700' }}>{tx('mobileSubscriptions.plans.title', 'Available In-App Purchase Plans')}</Text>
          <TouchableOpacity
            onPress={() => setShowIapFeeExplainer((v) => !v)}
            data-testid="mobile-subs-fee-explainer-toggle" testID="mobile-subs-fee-explainer-toggle"
            style={{ borderWidth: 1, borderColor: C.border, borderRadius: 999, backgroundColor: C.surface || C.card, paddingHorizontal: 8, paddingVertical: 4 }}
          >
            {Platform.OS === 'web' ? <div data-testid="mobile-subs-fee-explainer-toggle" /> : null}
            <Text style={{ color: C.textSec, fontSize: 10, fontWeight: '700' }}>{tx('fees.explainer.title', 'Why these fees?')}</Text>
          </TouchableOpacity>
        </View>

        {showIapFeeExplainer && (
          <View style={{ backgroundColor: C.cardHover, borderRadius: 10, borderWidth: 1, borderColor: C.border, padding: 10, marginBottom: 12 }} data-testid="mobile-subs-fee-explainer-card" testID="mobile-subs-fee-explainer-card">
            {Platform.OS === 'web' ? <div data-testid="mobile-subs-fee-explainer-card" /> : null}
            <Text style={{ color: C.text, fontSize: 11, fontWeight: '700', marginBottom: 6 }}>{tx('mobileSubscriptions.plans.feeTransparency', 'Fee transparency for in-app purchases')}</Text>
            <Text style={{ color: C.text, fontSize: 11, fontWeight: '700', marginBottom: 6 }}>{feeText.title}</Text>
            <Text style={{ color: C.textSec, fontSize: 10, lineHeight: 16 }}>• {feeText.line1}</Text>
            <Text style={{ color: C.textSec, fontSize: 10, lineHeight: 16 }}>• {feeText.line2}</Text>
            <Text style={{ color: C.textSec, fontSize: 10, lineHeight: 16 }}>• {feeText.line3}</Text>
            <Text style={{ color: C.textSec, fontSize: 10, lineHeight: 16 }}>• {feeText.line4}</Text>
          </View>
        )}

        {jurisdictionContext ? (
          <View style={{ backgroundColor: C.cardAlt, borderRadius: 10, borderWidth: 1, borderColor: C.border, padding: 10, marginBottom: 12 }} data-testid="mobile-subs-jurisdiction-card" testID="mobile-subs-jurisdiction-card">
            {Platform.OS === 'web' ? <div data-testid="mobile-subs-jurisdiction-card" /> : null}
            <Text style={{ color: C.text, fontSize: 11, fontWeight: '700' }} data-testid="mobile-subs-jurisdiction-label" testID="mobile-subs-jurisdiction-label">{tx('mobileSubscriptions.jurisdiction.label', 'Tax Jurisdiction')}: {jurisdictionContext?.label || tx('mobileSubscriptions.defaults.na', 'N/A')}</Text>
            <Text style={{ color: C.textMuted, fontSize: 10, marginTop: 4 }} data-testid="mobile-subs-jurisdiction-note" testID="mobile-subs-jurisdiction-note">
              {tx('mobileSubscriptions.jurisdiction.note', 'Applicable taxes are automatically calculated from this jurisdiction before final payment.')}
            </Text>
          </View>
        ) : null}

        <View style={{ gap: 10 }}>
          {products.map((p, i) => {
            const isCurrentPlan = status?.product_id === p.product_id;
            return (
              <View key={i} style={{ flexDirection: 'row', alignItems: 'center', gap: 12, padding: 12, borderRadius: 10, backgroundColor: isCurrentPlan ? (globalThis as any).__alphaColor(planColor, '10') : C.cardAlt, borderWidth: 1, borderColor: isCurrentPlan ? (globalThis as any).__alphaColor(planColor, '40') : C.border }} data-testid={`mobile-plan-${p.plan}-${p.period}`} testID={`mobile-plan-${p.plan}-${p.period}`}>
                <View style={{ width: 40, height: 40, borderRadius: 10, backgroundColor: (globalThis as any).__alphaColor((p.plan === 'premium' ? C.purple : C.primary), '18'), alignItems: 'center', justifyContent: 'center' }}>
                  <Ionicons name={p.plan === 'premium' ? 'diamond-outline' : 'star-outline'} size={20} color={p.plan === 'premium' ? C.purple : C.primary} />
                </View>
                <View style={{ flex: 1 }}>
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                    <Text style={{ color: C.text, fontSize: 14, fontWeight: '600' }}>{p.display_name}</Text>
                    {isCurrentPlan && (
                      <View style={{ paddingHorizontal: 6, paddingVertical: 2, borderRadius: 4, backgroundColor: (globalThis as any).__alphaColor(C.success, '18') }}>
                        <Text style={{ color: C.successText, fontSize: 9, fontWeight: '700' }}>{tx('mobileSubscriptions.plans.current', 'CURRENT')}</Text>
                      </View>
                    )}
                  </View>
                  <Text style={{ color: C.textMuted, fontSize: 11, marginTop: 2 }}>{p.product_id}</Text>
                  {['apple', 'google'].map((provider) => {
                    const est = p?.checkout_estimates?.[provider] || {};
                    const providerLabel = provider === 'apple'
                      ? tx('mobileSubscriptions.providers.apple', 'Apple App Store')
                      : tx('mobileSubscriptions.providers.google', 'Google Play');
                    const providerKey = `${p.product_id}-${provider}`;
                    const confirmed = Boolean(confirmationMap[providerKey]);
                    const linkUrl = provider === 'apple' ? getStoreLink('apple') : getStoreLink('google');
                    const providerReadiness = iapReadiness?.providers?.[provider];
                    const providerState = String(providerReadiness?.readiness_state || '').toLowerCase();
                    const providerTone = providerState.includes('live') ? C.success : providerState.includes('sandbox') || providerState.includes('test') ? C.warning : C.error;
                    return (
                      <View key={providerKey} style={{ marginTop: 8, borderWidth: 1, borderColor: C.border, borderRadius: 10, backgroundColor: C.surface || C.card, padding: 9 }} data-testid={`mobile-plan-${provider}-breakdown-${p.product_id}`} testID={`mobile-plan-${provider}-breakdown-${p.product_id}`}>
                        <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
                          <Text style={{ color: providerTone, fontSize: 10, fontWeight: '800' }}>{providerLabel}</Text>
                          <Text style={{ color: providerTone, fontSize: 9, fontWeight: '800' }} data-testid={`mobile-plan-${provider}-readiness-${p.product_id}`} testID={`mobile-plan-${provider}-readiness-${p.product_id}`}>
                            {providerReadiness?.status_label || tx('mobileSubscriptions.readiness.unavailable', 'Unavailable')}
                          </Text>
                        </View>
                        <Text style={{ color: C.textSec, fontSize: 10 }} data-testid={`mobile-plan-${provider}-base-${p.product_id}`} testID={`mobile-plan-${provider}-base-${p.product_id}`}>{tx('mobileSubscriptions.pricing.basePlanPrice', 'Base Plan Price')}: ${Number(est?.base_plan_price || est?.subtotal || 0).toFixed(2)}</Text>
                        <Text style={{ color: C.textSec, fontSize: 10 }} data-testid={`mobile-plan-${provider}-platform-fee-${p.product_id}`} testID={`mobile-plan-${provider}-platform-fee-${p.product_id}`}>{tx('mobileSubscriptions.pricing.platformFee', 'Platform Fee (IAP Commission)')}: ${Number(est?.platform_fee || est?.processing_fee || 0).toFixed(2)} ({Number(est?.platform_fee_rate_pct || 0)}%)</Text>
                        <Text style={{ color: C.textSec, fontSize: 10 }} data-testid={`mobile-plan-${provider}-tax-${p.product_id}`} testID={`mobile-plan-${provider}-tax-${p.product_id}`}>{tx('mobileSubscriptions.pricing.applicableTaxes', 'Applicable Taxes')}: ${Number(est?.tax_fee || 0).toFixed(2)} ({Number(est?.tax_rate_pct || 0)}%)</Text>
                        <Text style={{ color: C.textMuted, fontSize: 10 }} data-testid={`mobile-plan-${provider}-jurisdiction-${p.product_id}`} testID={`mobile-plan-${provider}-jurisdiction-${p.product_id}`}>
                          {tx('mobileSubscriptions.pricing.jurisdiction', 'Jurisdiction')}: {est?.jurisdiction?.country || tx('mobileSubscriptions.defaults.us', 'US')}{est?.jurisdiction?.state ? `-${est?.jurisdiction?.state}` : ''}
                        </Text>
                        {Array.isArray(est?.tax_breakdown) && est.tax_breakdown.length > 0 ? (
                          <View style={{ marginTop: 2 }} data-testid={`mobile-plan-${provider}-tax-breakdown-${p.product_id}`} testID={`mobile-plan-${provider}-tax-breakdown-${p.product_id}`}>
                            {est.tax_breakdown.map((line: any, idx: number) => (
                              <Text key={`${providerKey}-tax-line-${idx}`} style={{ color: C.textMuted, fontSize: 9 }}>
                                • {line?.tax_name || line?.tax_type || tx('mobileSubscriptions.pricing.tax', 'Tax')}: ${Number(line?.tax_amount || 0).toFixed(2)} ({Number((line?.tax_rate || 0) * 100).toFixed(2)}%)
                              </Text>
                            ))}
                          </View>
                        ) : null}
                        <Text style={{ color: C.text, fontSize: 10, fontWeight: '800', marginTop: 2 }} data-testid={`mobile-plan-${provider}-total-${p.product_id}`} testID={`mobile-plan-${provider}-total-${p.product_id}`}>{tx('mobileSubscriptions.pricing.finalTotal', 'Final Total')}: ${Number(est?.final_total || est?.total_amount || 0).toFixed(2)}</Text>
                        <Text style={{ color: C.textMuted, fontSize: 9, marginTop: 2 }} data-testid={`mobile-plan-${provider}-tax-note-${p.product_id}`} testID={`mobile-plan-${provider}-tax-note-${p.product_id}`}>
                          {est?.tax_disclosure || tx('mobileSubscriptions.pricing.taxDisclosure', 'Taxes shown here are calculated before payment to ensure transparency.')}
                        </Text>

                        <TouchableOpacity
                          onPress={() => toggleConfirmation(providerKey)}
                          style={{ marginTop: 6, flexDirection: 'row', alignItems: 'center', gap: 6 }}
                          data-testid={`mobile-plan-${provider}-confirm-toggle-${p.product_id}`} testID={`mobile-plan-${provider}-confirm-toggle-${p.product_id}`}
                        >
                          <Ionicons name={confirmed ? 'checkbox' : 'square-outline'} size={14} color={confirmed ? C.success : C.textMuted} />
                          <Text style={{ color: C.textSec, fontSize: 10 }}>{tx('mobileSubscriptions.pricing.confirmToggle', 'I confirm this pricing breakdown before payment.')}</Text>
                        </TouchableOpacity>

                        <TouchableOpacity
                          disabled={!confirmed}
                          onPress={() => openStoreLink(linkUrl)}
                          style={{ marginTop: 8, borderRadius: 8, paddingVertical: 7, alignItems: 'center', backgroundColor: confirmed ? C.primary : C.cardAlt, borderWidth: 1, borderColor: confirmed ? `${C.primary}AA` : C.border }}
                          data-testid={`mobile-plan-${provider}-continue-button-${p.product_id}`} testID={`mobile-plan-${provider}-continue-button-${p.product_id}`}
                        >
                          <Text style={{ color: confirmed ? C.primaryText : C.textMuted, fontSize: 10, fontWeight: '800' }}>
                            {confirmed
                              ? tx('mobileSubscriptions.pricing.continueIn', 'Continue in {provider}').replace('{provider}', providerLabel)
                              : tx('mobileSubscriptions.pricing.confirmToContinue', 'Confirm pricing to continue')}
                          </Text>
                        </TouchableOpacity>
                      </View>
                    );
                  })}
                </View>
                <Text style={{ color: C.text, fontSize: 18, fontWeight: '700' }}>${p.price}</Text>
                <Text style={{ color: C.textMuted, fontSize: 11 }}>/{p.period === 'yearly' ? tx('mobileSubscriptions.period.yr', 'yr') : tx('mobileSubscriptions.period.mo', 'mo')}</Text>
              </View>
            );
          })}
        </View>
      </View>

      {/* Transaction History */}
      <View style={{ backgroundColor: C.card, borderRadius: 14, padding: 16, borderWidth: 1, borderColor: C.border }} data-testid="mobile-subs-history" testID="mobile-subs-history">
        <Text style={{ color: C.text, fontSize: 15, fontWeight: '700', marginBottom: 14 }}>{tx('mobileSubscriptions.history.title', 'Purchase History')}</Text>
        {history.length === 0 ? (
          <View style={{ alignItems: 'center', paddingVertical: 30 }}>
            <Ionicons name="receipt-outline" size={36} color={C.textMuted} />
            <Text style={{ color: C.textMuted, fontSize: 13, marginTop: 8 }}>{tx('mobileSubscriptions.history.empty', 'No in-app purchases yet')}</Text>
          </View>
        ) : (
          <View style={{ gap: 8 }}>
            {history.map((item, i) => (
              <View key={i} style={{ flexDirection: 'row', alignItems: 'center', gap: 10, padding: 12, backgroundColor: C.surface || C.card, borderRadius: 8, borderWidth: 1, borderColor: C.border }} data-testid={`mobile-tx-${i}`} testID={`mobile-tx-${i}`}>
                <Ionicons name={item.platform === 'apple' ? 'logo-apple' : 'logo-google-playstore'} size={18} color={item.platform === 'apple' ? 'var(--app-primary)' : C.success} />
                <View style={{ flex: 1 }}>
                  <Text style={{ color: C.text, fontSize: 13, fontWeight: '600' }}>{(item.plan || tx('mobileSubscriptions.defaults.free', 'Free')).charAt(0).toUpperCase() + (item.plan || '').slice(1)} - {(item.period || '').charAt(0).toUpperCase() + (item.period || '').slice(1)}</Text>
                  <Text style={{ color: C.textMuted, fontSize: 11, marginTop: 2 }}>{item.transaction_id || tx('mobileSubscriptions.defaults.na', 'N/A')}</Text>
                </View>
                <View style={{ alignItems: 'flex-end' }}>
                  <View style={{ paddingHorizontal: 8, paddingVertical: 3, borderRadius: 6, backgroundColor: (globalThis as any).__alphaColor((item.status === 'active' ? C.success : C.error), '18') }}>
                    <Text style={{ color: item.status === 'active' ? C.success : C.error, fontSize: 10, fontWeight: '600' }}>{item.status}</Text>
                  </View>
                  <Text style={{ color: C.textMuted, fontSize: 10, marginTop: 4 }}>{item.created_at ? new Date(item.created_at).toLocaleDateString() : ''}</Text>
                </View>
              </View>
            ))}
          </View>
        )}
      </View>
    </ScrollView>
  );
}

export default function MobileSubscriptionsView() {
  return <MobileSubscriptionsViewV2 />;
}
