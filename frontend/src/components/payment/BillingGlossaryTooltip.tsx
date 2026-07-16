import React, { useMemo, useState } from 'react';
import { Modal, Text, TouchableOpacity, View, useWindowDimensions } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useTranslation } from '../../hooks/useTranslation';
import { useTheme } from '../../context/ThemeContext';

export const BILLING_GLOSSARY = {
  subtotal: {
    label: 'Base Subscription Price',
    description: 'The plan price before applicable tax and payment handling fees are added.',
  },
  applicable_tax: {
    label: 'Applicable Tax',
    description: 'The tax amount calculated from your checkout jurisdiction and the active compliance rules for this payment method.',
  },
  processing_fee: {
    label: 'Payment Processing Fee',
    description: 'The fee charged by the payment rail or app store for handling the transaction securely.',
  },
  total_you_pay: {
    label: 'Total You Pay',
    description: 'The full amount charged to the customer after combining the base subscription price, tax, and payment processing fee.',
  },
  customer_charge_total: {
    label: 'Customer Charge Total',
    description: 'The final amount charged to the customer for the transaction. This is the finance-facing label for the all-in customer total.',
  },
  net_settlement: {
    label: 'Net Settlement After Fee',
    description: 'The amount retained after processor fees are removed from the customer charge total. This helps finance teams reconcile platform settlement.',
  },
} as const;

export type BillingGlossaryKey = keyof typeof BILLING_GLOSSARY;

type TooltipProps = {
  accentColor?: string;
  dataTestId: string;
  glossaryKey: BillingGlossaryKey;
};

export const BillingGlossaryTooltip = ({ accentColor = 'var(--app-primary)', dataTestId, glossaryKey }: TooltipProps) => {
  const [open, setOpen] = useState(false);
  const { width } = useWindowDimensions();
  const compact = width < 480;
  const { t } = useTranslation();
  const { colors } = useTheme();
  const item = BILLING_GLOSSARY[glossaryKey];

  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };

  return (
    <>
      <TouchableOpacity
        onPress={() => setOpen(true)}
        data-testid={`${dataTestId}-trigger`} testID={`${dataTestId}-trigger`}
        accessibilityRole="button"
        accessibilityLabel={`${tx('payment.feeTransparency.explain', 'Explain')} ${item.label}`}
        style={{
          width: 20,
          height: 20,
          borderRadius: 999,
          alignItems: 'center',
          justifyContent: 'center',
          backgroundColor: `${accentColor}18`,
          borderWidth: 1,
          borderColor: `${accentColor}50`,
        }}
      >
        <Ionicons name="information-circle-outline" size={12} color={accentColor} />
      </TouchableOpacity>

      <Modal visible={open} transparent animationType="slide" onRequestClose={() => setOpen(false)}>
        <View style={{ flex: 1, backgroundColor: 'rgba(2,6,23,0.62)', flexDirection: 'row', justifyContent: 'flex-end' }}>
          <TouchableOpacity
            onPress={() => setOpen(false)}
            style={{ flex: 1 }}
            data-testid={`${dataTestId}-overlay-close`}
            testID={`${dataTestId}-overlay-close`}
          />
          <View
            style={{
              width: compact ? '100%' : '88%',
              maxWidth: 420,
              height: '100%',
              backgroundColor: colors.card,
              borderLeftWidth: 1,
              borderLeftColor: colors.border,
              paddingHorizontal: 18,
              paddingTop: compact ? 24 : 36,
              paddingBottom: 24,
            }}
            data-testid={`${dataTestId}-modal`}
            testID={`${dataTestId}-modal`}
          >
            <View style={{ flexDirection: 'row', alignItems: 'flex-start', justifyContent: 'space-between', gap: 12 }}>
              <View style={{ flex: 1 }}>
                <Text style={{ color: colors.infoText, fontSize: 11, fontWeight: '800', textTransform: 'uppercase', letterSpacing: 0.8 }}>{tx('payment.feeTransparency.billingGlossary', 'Billing Glossary')}</Text>
                <Text style={{ color: colors.text, fontSize: 18, fontWeight: '800', marginTop: 8 }} data-testid={`${dataTestId}-title`} testID={`${dataTestId}-title`}>{item.label}</Text>
              </View>
              <TouchableOpacity onPress={() => setOpen(false)} data-testid={`${dataTestId}-close`} testID={`${dataTestId}-close`} style={{ width: 34, height: 34, borderRadius: 999, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.bgSoft || colors.cardMuted || colors.bg }}>
                <Ionicons name="close" size={17} color={colors.textSec} />
              </TouchableOpacity>
            </View>

            <View style={{ marginTop: 16, borderRadius: 12, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bgSoft || colors.cardMuted || colors.bg, padding: 12 }}>
              <Text style={{ color: colors.textSec, fontSize: 13, lineHeight: 21 }} data-testid={`${dataTestId}-content`} testID={`${dataTestId}-content`}>
                {item.description}
              </Text>
            </View>

            <Text style={{ color: colors.textMuted, fontSize: 11, lineHeight: 18, marginTop: 14 }} data-testid={`${dataTestId}-footnote`} testID={`${dataTestId}-footnote`}>
              {tx('payment.feeTransparency.glossaryFootnote', 'This value is computed from platform checkout data before payment confirmation.')}
            </Text>
          </View>
        </View>
      </Modal>
    </>
  );
};

type LabelProps = {
  accentColor?: string;
  dataTestId: string;
  glossaryKey?: BillingGlossaryKey;
  label: string;
  textColor?: string;
};

export const BillingGlossaryLabel = ({ accentColor = 'var(--app-primary)', dataTestId, glossaryKey, label, textColor = undefined as any }: LabelProps) => {
  const resolvedKey = useMemo(() => glossaryKey, [glossaryKey]);

  return (
    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, flexShrink: 1 }}>
      <Text style={{ color: textColor, fontSize: 11, fontWeight: '700', flexShrink: 1 }}>{label}</Text>
      {resolvedKey ? (
        <BillingGlossaryTooltip accentColor={accentColor} dataTestId={dataTestId} glossaryKey={resolvedKey} />
      ) : null}
    </View>
  );
};