import React from 'react';
import { View, Text, TouchableOpacity } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

type SubscriptionSuccessPanelProps = {
  amountText?: string | null;
  badgeText?: string | null;
  ctaLabel: string;
  colors: {
    success: string;
    successText: string;
    successSoft: string;
    text: string;
    textMuted: string;
    border: string;
    bgSoft: string;
    primaryText: string;
  };
  historyLabel: string;
  onPressCta: () => void;
  onPressHistory: () => void;
  preCtaContent?: React.ReactNode;
  subtitle: string;
  title: string;
};

export function SubscriptionSuccessPanel({
  amountText,
  badgeText,
  ctaLabel,
  colors,
  historyLabel,
  onPressCta,
  onPressHistory,
  preCtaContent,
  subtitle,
  title,
}: SubscriptionSuccessPanelProps) {
  return (
    <>
      <View style={{ alignItems: 'center' }}>
        <View style={{ width: 78, height: 78, borderRadius: 39, alignItems: 'center', justifyContent: 'center', backgroundColor: `${colors.success}18` }} data-testid="payment-success-icon-wrap" testID="payment-success-icon-wrap">
          <Ionicons name="checkmark-circle" size={68} color={colors.successText} />
        </View>
        <Text style={{ color: colors.text, fontSize: 22, fontWeight: '800', marginTop: 14, marginBottom: 8, textAlign: 'center' }} data-testid="payment-success-title" testID="payment-success-title">{title}</Text>
        <Text style={{ color: colors.textMuted, fontSize: 14, lineHeight: 22, marginBottom: 18, textAlign: 'center' }} data-testid="payment-success-subtitle" testID="payment-success-subtitle">{subtitle}</Text>
      </View>

      {amountText ? (
        <View data-testid="payment-success-amount" testID="payment-success-amount" style={{ backgroundColor: colors.successSoft, borderRadius: 12, paddingHorizontal: 20, paddingVertical: 10, marginBottom: 16, alignSelf: 'center' }}>
          <Text style={{ fontSize: 18, fontWeight: '800', color: colors.successText, textAlign: 'center' }}>{amountText}</Text>
        </View>
      ) : null}

      {badgeText ? (
        <View data-testid="payment-success-badge" testID="payment-success-badge" style={{ backgroundColor: colors.bgSoft, borderRadius: 8, paddingHorizontal: 14, paddingVertical: 8, marginBottom: 16, alignSelf: 'center' }}>
          <Text style={{ fontSize: 11, color: colors.textMuted, fontWeight: '600' }}>{badgeText}</Text>
        </View>
      ) : null}

      {preCtaContent ? (
        <View data-testid="payment-success-pre-cta-content" testID="payment-success-pre-cta-content" style={{ marginBottom: 16 }}>
          {preCtaContent}
        </View>
      ) : null}

      <TouchableOpacity style={{ backgroundColor: colors.success, borderRadius: 12, paddingVertical: 14, alignItems: 'center', marginTop: 8 }} onPress={onPressCta} data-testid="payment-success-primary-cta" testID="payment-success-primary-cta">
        <Text style={{ color: colors.primaryText, fontSize: 14, fontWeight: '700' }}>{ctaLabel}</Text>
      </TouchableOpacity>

      <TouchableOpacity style={{ marginTop: 10, borderRadius: 12, borderWidth: 1, borderColor: colors.border, backgroundColor: 'transparent', paddingVertical: 12, alignItems: 'center' }} onPress={onPressHistory} data-testid="payment-success-view-history" testID="payment-success-view-history">
        <Text style={{ color: colors.textMuted, fontSize: 13, fontWeight: '700' }}>{historyLabel}</Text>
      </TouchableOpacity>
    </>
  );
}