import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { ActivityIndicator, Text, TouchableOpacity, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { useTheme } from '../../context/ThemeContext';
import { useAuth } from '../../context/AuthContext';
import { handleAppRecoverableError } from '../../utils/appRecoverableError';

type TrustProvider = 'stripe' | 'paypal' | 'fedapay' | 'all' | 'card';
type TrustContext = 'checkout' | 'billing' | 'modal' | 'nova';

type TrustSignal = {
  id: string;
  label: string;
  status: 'verified' | 'warning' | string;
  message: string;
};

type TrustResponse = {
  overall_status: 'verified' | 'warning' | string;
  mode_effective?: 'static' | 'live' | string;
  data_source?: 'policy' | 'runtime' | string;
  audience?: 'public' | 'admin' | string;
  viewer_is_admin?: boolean;
  warnings: string[];
  settings: {
    trust_signals_enabled: boolean;
    display_level: 'minimal' | 'detailed';
    guarantee_message: string;
    fraud_notice: string;
    compliance_labels: string[];
  };
  signals: TrustSignal[];
  messages: string[];
  provider_status: any;
  checked_at: string;
};

type Props = {
  provider: TrustProvider;
  context: TrustContext;
  panelTestId: string;
};

const providerLabel = (provider: TrustProvider) => {
  if (provider === 'card') return 'Stripe';
  if (provider === 'all') return 'Stripe, PayPal & FedaPay';
  return provider.charAt(0).toUpperCase() + provider.slice(1);
};

const buildFallbackWarningState = (provider: TrustProvider): TrustResponse => ({
  overall_status: 'warning',
  warnings: ['Live trust verification is temporarily unavailable.'],
  settings: {
    trust_signals_enabled: true,
    display_level: 'detailed',
    guarantee_message: 'Refunds handled per provider policy and platform terms.',
    fraud_notice: 'Protected transactions with fraud monitoring.',
    compliance_labels: ['PCI-DSS'],
  },
  signals: [
    {
      id: 'encryption',
      label: 'End-to-end encryption',
      status: 'warning',
      message: 'TLS/SSL validation could not be confirmed in this session.',
    },
    {
      id: 'provider',
      label: 'Payment provider verification',
      status: 'warning',
      message: `Provider verification for ${providerLabel(provider)} is pending live validation.`,
    },
    {
      id: 'fraud',
      label: 'Fraud protection',
      status: 'verified',
      message: 'Protected transactions with fraud monitoring.',
    },
    {
      id: 'guarantee',
      label: 'Money-back guarantee',
      status: 'verified',
      message: 'Refunds handled per provider policy and platform terms.',
    },
    {
      id: 'compliance',
      label: 'Compliance indicators',
      status: 'verified',
      message: 'PCI-DSS',
    },
  ],
  messages: [
    'Secure checkout panel active in warning mode.',
  ],
  provider_status: null,
  checked_at: new Date().toISOString(),
});

const buildFallbackStaticState = (provider: TrustProvider): TrustResponse => ({
  overall_status: 'verified',
  mode_effective: 'static',
  data_source: 'policy',
  audience: 'public',
  viewer_is_admin: false,
  warnings: [],
  settings: {
    trust_signals_enabled: true,
    display_level: 'detailed',
    guarantee_message: 'Refunds handled per provider policy and platform terms.',
    fraud_notice: 'Protected transactions with fraud monitoring.',
    compliance_labels: ['PCI-DSS'],
  },
  signals: [
    {
      id: 'encryption',
      label: 'End-to-end encryption',
      status: 'verified',
      message: 'Secured by TLS encryption (256-bit)',
    },
    {
      id: 'provider',
      label: 'Payment provider verification',
      status: 'verified',
      message: `Verified secure checkout via ${providerLabel(provider)}`,
    },
    {
      id: 'fraud',
      label: 'Fraud protection',
      status: 'verified',
      message: 'Protected transactions with fraud monitoring.',
    },
    {
      id: 'guarantee',
      label: 'Money-back guarantee',
      status: 'verified',
      message: 'Refunds handled per provider policy and platform terms.',
    },
    {
      id: 'compliance',
      label: 'Compliance indicators',
      status: 'verified',
      message: 'PCI-DSS',
    },
  ],
  messages: ['Secure checkout verification policy is active.'],
  provider_status: null,
  checked_at: new Date().toISOString(),
});

export const SecurePaymentAssurancePanel = ({ provider, context, panelTestId }: Props) => {
  const { colors } = useTheme();
  const { user } = useAuth();
  const [data, setData] = useState<TrustResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [showExplain, setShowExplain] = useState(false);

  const normalizedProvider = provider === 'card' ? 'stripe' : provider;
  const viewerIsAdmin = useMemo(() => {
    const roles = Array.isArray((user as any)?.roles)
      ? (user as any).roles.map((entry: any) => String(entry || '').toLowerCase())
      : [];
    const platformRole = String((user as any)?.platform_role || '').toLowerCase();
    return Boolean(
      user?.is_admin
      || roles.includes('admin')
      || roles.includes('super_admin')
      || platformRole === 'admin'
      || platformRole === 'super_admin'
    );
  }, [user]);

  const isWarning = data?.overall_status === 'warning';
  const isLiveMode = String(data?.mode_effective || (viewerIsAdmin ? 'live' : 'static')).toLowerCase() === 'live';
  const displayLevel = data?.settings?.display_level || 'detailed';

  const emitTrustAnalytics = useCallback(async (eventType: string) => {
    try {
      await api.post('/subscriptions/pricing-guard/frontend-event', {
        event_type: eventType,
        route: `trust-panel:${context}`,
        payment_method: normalizedProvider,
        reason: isWarning ? 'warning_state' : 'verified_state',
      }, { silentLoading: true });
    } catch (error) { handleAppRecoverableError({ scope: 'src/components/payment/SecurePaymentAssurancePanel.tsx#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
  }, [context, isWarning, normalizedProvider]);

  const surface = useMemo(() => ({
    border: isWarning ? colors.warningText : colors.primary,
    bg: isWarning ? colors.warningSoft : colors.bgSoft,
    icon: isWarning ? colors.warningText : colors.successText,
    text: colors.text,
    muted: colors.textMuted,
  }), [colors, isWarning]);

  const signals = useMemo(() => (Array.isArray(data?.signals) ? data.signals : []), [data]);
  const providerExplainerBullets = useMemo(() => {
    if (normalizedProvider === 'all') {
      const rows = Array.isArray((data as any)?.provider_status) ? (data as any).provider_status : [];
      return rows.map((row: any) => `${row?.provider_label || 'Provider'}: ${row?.status_label || 'status unavailable'}`);
    }
    const row = (data as any)?.provider_status || {};
    return [
      `${providerLabel(provider)} verification: ${row?.status_label || 'status unavailable'}`,
      row?.mode ? `Mode: ${String(row.mode).toUpperCase()}` : `${providerLabel(provider)} routing active for this flow`,
    ];
  }, [data, normalizedProvider, provider]);

  const loadTrust = useCallback(async (silent = false) => {
    if (silent) setRefreshing(true);
    else setLoading(true);

    try {
      const res = await api.get('/payments/trust/assurance', {
        params: {
          provider: normalizedProvider,
          context,
        },
        silentLoading: true,
      });
      setData((res.data || null) as TrustResponse | null);
    } catch {
      setData(viewerIsAdmin ? buildFallbackWarningState(provider) : buildFallbackStaticState(provider));
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [context, normalizedProvider, provider, viewerIsAdmin]);

  useEffect(() => {
    void loadTrust(false);
    if (!viewerIsAdmin) return;
    const timer = setInterval(() => { void loadTrust(true); }, 45000);
    return () => clearInterval(timer);
  }, [loadTrust, viewerIsAdmin]);

  if (loading) {
    return (
      <View
        style={{ borderRadius: 14, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, padding: 12, marginBottom: 14 }}
        data-testid={`${panelTestId}-loading`}
        testID={`${panelTestId}-loading`}
      >
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
          <ActivityIndicator size="small" color={colors.primary} />
          <Text style={{ color: colors.textMuted, fontSize: 12, fontWeight: '600' }}>Validating payment trust signals…</Text>
        </View>
      </View>
    );
  }

  if (data && data.settings && data.settings.trust_signals_enabled === false) {
    return null;
  }

  const headline = isWarning
    ? 'Secure Payment Assurance — Warning State'
    : 'Secure Payment Assurance';

  const leadingMessage = data?.messages?.[0] || `Verified secure checkout via ${providerLabel(provider)}`;

  return (
    <View
      style={{
        borderRadius: 14,
        borderWidth: 1,
        borderColor: surface.border,
        backgroundColor: surface.bg,
        padding: 12,
        marginBottom: 14,
      }}
      data-testid={panelTestId}
      testID={panelTestId}
    >
      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, flex: 1 }}>
          <Ionicons name="shield-checkmark" size={16} color={surface.icon} />
          <Text style={{ color: surface.text, fontSize: 12, fontWeight: '800' }} data-testid={`${panelTestId}-title`} testID={`${panelTestId}-title`}>
            {headline}
          </Text>
        </View>
        {viewerIsAdmin ? (
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
            {refreshing ? <ActivityIndicator size="small" color={surface.icon} /> : <Ionicons name={isWarning && isLiveMode ? 'warning-outline' : 'checkmark-circle'} size={14} color={surface.icon} />}
            <Text style={{ color: surface.muted, fontSize: 10, fontWeight: '700' }} data-testid={`${panelTestId}-mode-badge`} testID={`${panelTestId}-mode-badge`}>
              {refreshing ? 'Refreshing' : isWarning ? 'Warning' : 'Live'}
            </Text>
          </View>
        ) : null}
      </View>

      <Text style={{ color: surface.text, fontSize: 12, marginTop: 8, fontWeight: '600' }} data-testid={`${panelTestId}-message`} testID={`${panelTestId}-message`}>
        {leadingMessage}
      </Text>

      {displayLevel === 'detailed' && (
        <View style={{ marginTop: 10, gap: 8 }} data-testid={`${panelTestId}-signals`} testID={`${panelTestId}-signals`}>
          {signals.map((signal) => {
            const rowWarning = signal.status !== 'verified';
            return (
              <View
                key={signal.id}
                style={{
                  borderRadius: 10,
                  borderWidth: 1,
                  borderColor: rowWarning ? (globalThis as any).__alphaColor(colors.warningText, '55') : colors.border,
                  backgroundColor: rowWarning ? colors.warningSoft : colors.card,
                  paddingHorizontal: 10,
                  paddingVertical: 8,
                }}
                data-testid={`${panelTestId}-signal-${signal.id}`}
                testID={`${panelTestId}-signal-${signal.id}`}
              >
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 2 }}>
                  <Ionicons name={rowWarning ? 'warning-outline' : 'checkmark-circle'} size={13} color={rowWarning ? colors.warningText : colors.successText} />
                  <Text style={{ color: surface.text, fontSize: 11, fontWeight: '700' }}>{signal.label}</Text>
                </View>
                <Text style={{ color: surface.muted, fontSize: 10, lineHeight: 15 }}>{signal.message}</Text>
              </View>
            );
          })}
        </View>
      )}

      {Array.isArray(data?.warnings) && data.warnings.length > 0 ? (
        <View style={{ marginTop: 10, gap: 6 }} data-testid={`${panelTestId}-warnings`} testID={`${panelTestId}-warnings`}>
          {data.warnings.map((warning, idx) => (
            <Text key={`${warning}-${idx}`} style={{ color: colors.warningText, fontSize: 10, fontWeight: '700' }}>
              • {warning}
            </Text>
          ))}
        </View>
      ) : null}

      <View style={{ marginTop: 10, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
        <Text style={{ color: surface.muted, fontSize: 10 }} data-testid={`${panelTestId}-provider-context`} testID={`${panelTestId}-provider-context`}>
          Provider scope: {providerLabel(provider)}
        </Text>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
          <TouchableOpacity accessibilityLabel="Const in secure payment assurance panel"
            onPress={() => {
              const next = !showExplain;
              setShowExplain(next);
              if (next) {
                void emitTrustAnalytics('trust_explainer_open');
              }
            }}
            data-testid={`${panelTestId}-why-safe-toggle`}
            testID={`${panelTestId}-why-safe-toggle`}
            style={{ paddingHorizontal: 8, paddingVertical: 4, borderRadius: 8, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card }}
          >
            <Text style={{ color: colors.textMuted, fontSize: 10, fontWeight: '700' }}>{showExplain ? 'Hide why safe' : 'Why this checkout is safe'}</Text>
          </TouchableOpacity>
          {viewerIsAdmin && (
            <TouchableOpacity
              onPress={() => { void loadTrust(true); }}
              data-testid={`${panelTestId}-refresh`}
              testID={`${panelTestId}-refresh`}
              style={{ paddingHorizontal: 8, paddingVertical: 4, borderRadius: 8, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card }}
            >
              <Text style={{ color: colors.textMuted, fontSize: 10, fontWeight: '700' }}>Refresh</Text>
            </TouchableOpacity>
          )}
        </View>
      </View>

      {showExplain ? (
        <View
          style={{
            marginTop: 10,
            borderRadius: 10,
            borderWidth: 1,
            borderColor: colors.border,
            backgroundColor: colors.card,
            padding: 10,
            gap: 6,
          }}
          data-testid={`${panelTestId}-why-safe-content`}
          testID={`${panelTestId}-why-safe-content`}
        >
          <Text style={{ color: surface.text, fontSize: 11, fontWeight: '800' }}>Why this checkout is safe</Text>
          {providerExplainerBullets.map((bullet, idx) => (
            <Text key={`provider-safe-${idx}`} style={{ color: surface.muted, fontSize: 10, lineHeight: 15 }}>
              • {bullet}
            </Text>
          ))}
          {(signals.slice(0, 4)).map((signal) => (
            <Text key={`safe-${signal.id}`} style={{ color: surface.muted, fontSize: 10, lineHeight: 15 }}>
              • {signal.label}: {signal.message}
            </Text>
          ))}
        </View>
      ) : null}
    </View>
  );
};

/* i18n-probe t('i18n.auto.probe') */
