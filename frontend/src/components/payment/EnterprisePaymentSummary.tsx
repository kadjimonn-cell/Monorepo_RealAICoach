import React, { useMemo, useState } from 'react';
import { ActivityIndicator, Modal, ScrollView, Text, TouchableOpacity, View, useWindowDimensions } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { BillingGlossaryLabel } from './BillingGlossaryTooltip';
import { useTranslation } from '../../hooks/useTranslation';
import { useViewportWidth } from '../../hooks/useViewportWidth';

type SummaryColors = {
  text: string;
  textSecondary: string;
  textMuted: string;
  border: string;
  surface: string;
  cardAlt: string;
};

type SummaryRow = {
  key: string;
  label: string;
  value: string;
  icon?: string;
  tone?: string;
  valueColor?: string;
  glossaryKey?: 'subtotal' | 'applicable_tax' | 'processing_fee' | 'total_you_pay';
};

type LocalizationData = {
  jurisdiction: string;
  languageLabel: string;
  fxLabel: string;
};

type FeeText = {
  title: string;
  line1: string;
  line2: string;
  line3: string;
  line4: string;
};

type ProviderMetaRow = {
  key: string;
  label: string;
  value: string;
};

export const EnterprisePaymentSummary = ({
  prefix,
  title,
  colors,
  feeText,
  loading,
  error,
  rows,
  totalValue,
  feeNote,
  localization,
  policyText,
  headerBadges,
  providerKey,
  providerLabel,
  providerFormula,
  providerMetaRows,
  hideProviderCard,
}: {
  prefix: string;
  title: string;
  colors: SummaryColors;
  feeText: FeeText;
  loading: boolean;
  error?: string;
  rows: SummaryRow[];
  totalValue: string;
  feeNote: string;
  localization?: LocalizationData | null;
  policyText?: string;
  headerBadges?: React.ReactNode;
  providerKey?: 'stripe' | 'paypal' | 'fedapay' | 'unknown';
  providerLabel?: string;
  providerFormula?: string;
  providerMetaRows?: ProviderMetaRow[];
  hideProviderCard?: boolean;
}) => {
  const [showDrawer, setShowDrawer] = useState(false);
  const { t } = useTranslation();
  const { width: rnWidth } = useWindowDimensions();
  const viewportWidth = useViewportWidth();
  const width = typeof viewportWidth === 'number' && viewportWidth > 0 ? viewportWidth : rnWidth;
  const compact = width < 760;
  const provider = (providerKey || 'unknown').toLowerCase() as 'stripe' | 'paypal' | 'fedapay' | 'unknown';

  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };

  const accent = useMemo(() => {
    if (provider === 'stripe') return 'var(--app-primary)';
    if (provider === 'paypal') return 'var(--app-primary)';
    if (provider === 'fedapay') return 'var(--app-primary)';
    return colors.text;
  }, [colors.text, provider]);

  const providerName = providerLabel || (provider === 'stripe' ? 'Stripe' : provider === 'paypal' ? 'PayPal' : provider === 'fedapay' ? 'FedaPay' : 'Provider');
  const metaRows = Array.isArray(providerMetaRows) ? providerMetaRows.filter((item) => String(item?.value || '').trim().length > 0) : [];

  const resolveRowSurface = (tone?: string) => {
    const value = String(tone || '').trim();
    if (!value) return colors.surface;

    const normalized = value.toLowerCase();
    const textLikeColors = [
      String(colors.text || '').toLowerCase(),
      String(colors.textSecondary || '').toLowerCase(),
      String(colors.textMuted || '').toLowerCase(),
    ];

    if (textLikeColors.includes(normalized)) {
      return colors.cardAlt;
    }

    return value;
  };

  return (
    <>
      <View
        style={{
          marginTop: 12,
          borderRadius: 16,
          borderWidth: 1,
          borderColor: colors.border,
          backgroundColor: colors.surface,
          overflow: 'hidden',
        }}
        data-testid={`${prefix}-summary-card`}
        testID={`${prefix}-summary-card`}
      >
        <View style={{ height: 3, backgroundColor: accent }} data-testid={`${prefix}-summary-accent`} testID={`${prefix}-summary-accent`} />

        <View style={{ padding: compact ? 12 : 16 }}>
          <View style={{ flexDirection: 'row', flexWrap: compact ? 'wrap' : 'nowrap', justifyContent: 'space-between', alignItems: 'center', gap: 10 }}>
            <View style={{ flex: 1, minWidth: compact ? '100%' : undefined }}>
              <Text style={{ color: colors.text, fontSize: compact ? 13 : 15, fontWeight: '900', flexShrink: 1 }} data-testid={`${prefix}-summary-title`} testID={`${prefix}-summary-title`}>
                {title}
              </Text>
              <Text style={{ color: colors.textMuted, fontSize: 11, marginTop: 4 }} data-testid={`${prefix}-summary-subtitle`} testID={`${prefix}-summary-subtitle`}>
                {tx('payment.feeTransparency.subtitle', 'Platform-calculated fees shown before checkout confirmation.')}
              </Text>
            </View>

            <TouchableOpacity
              onPress={() => setShowDrawer(true)}
              data-testid={`${prefix}-explainer-open`}
              testID={`${prefix}-explainer-open`}
              style={{ borderWidth: 1, borderColor: colors.border, backgroundColor: colors.cardAlt, borderRadius: 999, paddingHorizontal: 10, paddingVertical: 6 }}
            >
              <Text style={{ color: colors.text, fontSize: 10, fontWeight: '800' }}>{tx('payment.feeTransparency.viewDetails', 'View fee details')}</Text>
            </TouchableOpacity>
          </View>

          {!hideProviderCard ? (
            <View
              style={{
                marginTop: 12,
                borderRadius: 12,
                borderWidth: 1,
                borderColor: `${accent}55`,
                backgroundColor: `${accent}14`,
                paddingHorizontal: 12,
                paddingVertical: 10,
              }}
              data-testid={`${prefix}-provider-card`}
              testID={`${prefix}-provider-card`}
            >
              <View style={{ flexDirection: compact ? 'column' : 'row', justifyContent: 'space-between', gap: 8 }}>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, flex: 1 }}>
                  <View style={{ width: 10, height: 10, borderRadius: 99, backgroundColor: accent }} />
                  <Text style={{ color: colors.text, fontSize: 12, fontWeight: '900' }} data-testid={`${prefix}-provider-name`} testID={`${prefix}-provider-name`}>
                    {providerName}
                  </Text>
                </View>
                <Text style={{ color: colors.textSecondary, fontSize: 11, fontWeight: '700' }} data-testid={`${prefix}-provider-formula`} testID={`${prefix}-provider-formula`}>
                  {providerFormula || tx('payment.feeTransparency.dynamicFormula', 'Live formula from platform policy')}
                </Text>
              </View>
              {policyText ? (
                <Text style={{ color: colors.textMuted, fontSize: 10, marginTop: 6 }} data-testid={`${prefix}-provider-policy`} testID={`${prefix}-provider-policy`}>
                  {policyText}
                </Text>
              ) : null}
            </View>
          ) : null}

          {headerBadges ? <View style={{ marginTop: 10 }}>{headerBadges}</View> : null}

          {metaRows.length > 0 ? (
            <View style={{ marginTop: 10, gap: 6 }} data-testid={`${prefix}-provider-meta-list`} testID={`${prefix}-provider-meta-list`}>
              {metaRows.map((item) => (
                <View key={item.key} style={{ borderRadius: 10, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.cardAlt, paddingHorizontal: 10, paddingVertical: 8, flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 8 }} data-testid={`${prefix}-provider-meta-${item.key}`} testID={`${prefix}-provider-meta-${item.key}`}>
                  <Text style={{ color: colors.textMuted, fontSize: 10, fontWeight: '700' }}>{item.label}</Text>
                  <Text style={{ color: colors.text, fontSize: 10, fontWeight: '800', textAlign: 'right', flexShrink: 1 }}>{item.value}</Text>
                </View>
              ))}
            </View>
          ) : null}

          {loading ? (
            <View style={{ marginTop: 12, alignItems: 'flex-start' }} data-testid={`${prefix}-summary-loading`} testID={`${prefix}-summary-loading`}>
              <ActivityIndicator color={colors.text} size="small" />
            </View>
          ) : (
            <View style={{ marginTop: 12, gap: 8 }}>
              {error ? (
                <Text style={{ color: colors.textSecondary, fontSize: 11, fontWeight: '700' }} data-testid={`${prefix}-summary-error`} testID={`${prefix}-summary-error`}>
                  {error}
                </Text>
              ) : null}

              {rows.map((row) => (
                <View key={row.key} style={{ borderWidth: 1, borderColor: colors.border, backgroundColor: resolveRowSurface(row.tone), borderRadius: 12, paddingHorizontal: 12, paddingVertical: compact ? 10 : 12 }} data-testid={`${prefix}-summary-row-${row.key}`} testID={`${prefix}-summary-row-${row.key}`}>
                  <View style={{ flexDirection: compact ? 'column' : 'row', justifyContent: 'space-between', alignItems: compact ? 'flex-start' : 'center', gap: 9 }}>
                    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, flex: 1, minWidth: 0 }}>
                      {row.icon ? <Ionicons name={row.icon as any} size={14} color={accent} /> : null}
                      {row.glossaryKey ? (
                        <BillingGlossaryLabel
                          accentColor={accent}
                          dataTestId={`${prefix}-summary-row-${row.key}-glossary`}
                          glossaryKey={row.glossaryKey}
                          label={row.label}
                          textColor={colors.text}
                        />
                      ) : (
                        <Text style={{ color: colors.text, fontSize: 11, fontWeight: '800', flexShrink: 1 }}>{row.label}</Text>
                      )}
                    </View>
                    <Text style={{ color: row.valueColor || colors.text, fontSize: 12, fontWeight: '900', textAlign: compact ? 'left' : 'right', alignSelf: compact ? 'flex-start' : 'center', flexShrink: 1, maxWidth: compact ? '100%' : '52%' }} data-testid={`${prefix}-summary-value-${row.key}`} testID={`${prefix}-summary-value-${row.key}`}>
                      {row.value}
                    </Text>
                  </View>
                </View>
              ))}

              <View style={{ borderWidth: 1.5, borderColor: accent, backgroundColor: `${accent}12`, borderRadius: 14, paddingHorizontal: 14, paddingVertical: 12 }} data-testid={`${prefix}-summary-row-total`} testID={`${prefix}-summary-row-total`}>
                <View style={{ flexDirection: compact ? 'column' : 'row', justifyContent: 'space-between', alignItems: compact ? 'flex-start' : 'center', gap: 8 }}>
                  <BillingGlossaryLabel
                    accentColor={accent}
                    dataTestId={`${prefix}-summary-row-total-glossary`}
                    glossaryKey="total_you_pay"
                    label={tx('payment.feeTransparency.totalLabel', 'Total You Pay')}
                    textColor={colors.text}
                  />
                  <Text style={{ color: accent, fontSize: compact ? 16 : 18, fontWeight: '900' }} data-testid={`${prefix}-summary-total-value`} testID={`${prefix}-summary-total-value`}>
                    {totalValue}
                  </Text>
                </View>
              </View>

              <Text style={{ color: colors.textMuted, fontSize: 10 }} data-testid={`${prefix}-summary-fee-note`} testID={`${prefix}-summary-fee-note`}>
                {feeNote}
              </Text>

            </View>
          )}
        </View>
      </View>

      <Modal visible={showDrawer} transparent animationType="slide" onRequestClose={() => setShowDrawer(false)}>
        <View style={{ flex: 1, backgroundColor: 'rgba(2,6,23,0.56)', flexDirection: 'row', justifyContent: 'flex-end' }}>
          <TouchableOpacity
            onPress={() => setShowDrawer(false)}
            style={{ flex: 1 }}
            data-testid={`${prefix}-explainer-overlay-close`}
            testID={`${prefix}-explainer-overlay-close`}
          />

          <View
            style={{
              width: compact ? '100%' : '88%',
              maxWidth: 460,
              height: '100%',
              borderLeftWidth: 1,
              borderLeftColor: colors.border,
              backgroundColor: colors.surface,
              paddingTop: compact ? 20 : 28,
              paddingHorizontal: 16,
              paddingBottom: 18,
            }}
            data-testid={`${prefix}-explainer-modal`}
            testID={`${prefix}-explainer-modal`}
          >
            <View style={{ flexDirection: 'row', alignItems: 'flex-start', justifyContent: 'space-between', gap: 10 }}>
              <View style={{ flex: 1 }}>
                <Text style={{ color: colors.textMuted, fontSize: 10, fontWeight: '800', textTransform: 'uppercase' }}>{tx('payment.feeTransparency.drawerKicker', 'Fee Details')}</Text>
                <Text style={{ color: colors.text, fontSize: 17, fontWeight: '900', marginTop: 6 }} data-testid={`${prefix}-explainer-title`} testID={`${prefix}-explainer-title`}>
                  {feeText.title}
                </Text>
              </View>
              <TouchableOpacity onPress={() => setShowDrawer(false)} data-testid={`${prefix}-explainer-close`} testID={`${prefix}-explainer-close`} style={{ width: 34, height: 34, borderRadius: 999, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.cardAlt, alignItems: 'center', justifyContent: 'center' }}>
                <Ionicons name="close" size={17} color={colors.text} />
              </TouchableOpacity>
            </View>

            <ScrollView showsVerticalScrollIndicator={false} contentContainerStyle={{ paddingBottom: 20 }}>
              <View style={{ marginTop: 14, borderRadius: 12, borderWidth: 1, borderColor: `${accent}60`, backgroundColor: `${accent}14`, padding: 10 }} data-testid={`${prefix}-explainer-provider-block`} testID={`${prefix}-explainer-provider-block`}>
                <Text style={{ color: colors.text, fontSize: 12, fontWeight: '900' }}>{providerName}</Text>
                <Text style={{ color: colors.textSecondary, fontSize: 11, marginTop: 4 }}>{providerFormula || tx('payment.feeTransparency.dynamicFormula', 'Live formula from platform policy')}</Text>
                {policyText ? <Text style={{ color: colors.textMuted, fontSize: 10, marginTop: 4 }} data-testid={`${prefix}-explainer-policy`} testID={`${prefix}-explainer-policy`}>{policyText}</Text> : null}
              </View>

              <View style={{ marginTop: 14, borderRadius: 12, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.cardAlt, padding: 10, gap: 8 }}>
                {[feeText.line1, feeText.line2, feeText.line3, feeText.line4].map((line, idx) => (
                  <Text key={`line-${idx}`} style={{ color: colors.text, fontSize: 12, lineHeight: 18 }} data-testid={`${prefix}-explainer-line-${idx + 1}`} testID={`${prefix}-explainer-line-${idx + 1}`}>
                    • {line}
                  </Text>
                ))}
              </View>

              <View style={{ marginTop: 14, borderRadius: 12, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface, padding: 10 }} data-testid={`${prefix}-explainer-snapshot`} testID={`${prefix}-explainer-snapshot`}>
                <Text style={{ color: colors.text, fontSize: 12, fontWeight: '900' }}>
                  {tx('payment.feeTransparency.snapshotTitle', 'Line Item Snapshot')}
                </Text>
                <View style={{ marginTop: 8, gap: 6 }}>
                  {rows.map((row) => (
                    <View key={`drawer-${row.key}`} style={{ flexDirection: 'row', justifyContent: 'space-between', gap: 8 }} data-testid={`${prefix}-explainer-snapshot-${row.key}`} testID={`${prefix}-explainer-snapshot-${row.key}`}>
                      <Text style={{ color: colors.textMuted, fontSize: 10, flex: 1 }}>{row.label}</Text>
                      <Text style={{ color: colors.text, fontSize: 10, fontWeight: '800', textAlign: 'right', flexShrink: 1 }}>{row.value}</Text>
                    </View>
                  ))}
                </View>
              </View>

              <TouchableOpacity
                onPress={() => setShowDrawer(false)}
                data-testid={`${prefix}-explainer-got-it`}
                testID={`${prefix}-explainer-got-it`}
                style={{ marginTop: 16, borderRadius: 10, backgroundColor: colors.cardAlt, borderWidth: 1, borderColor: colors.border, alignItems: 'center', paddingVertical: 10 }}
              >
                <Text style={{ color: colors.text, fontSize: 12, fontWeight: '800' }}>{tx('common.gotIt', 'Got it')}</Text>
              </TouchableOpacity>
            </ScrollView>
          </View>
        </View>
      </Modal>
    </>
  );
};
