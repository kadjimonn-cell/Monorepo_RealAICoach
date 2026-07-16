import React from 'react';
import { Platform, Text, TouchableOpacity, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { getTestProps } from '../utils/testProps';

export const BillingSectionCard = ({ children, colors, testId, style }: { children: React.ReactNode; colors: any; testId: string; style?: any }) => (
  <View
    style={{
      backgroundColor: colors.card,
      borderRadius: 20,
      borderWidth: 1,
      borderColor: colors.border,
      padding: 16,
      ...style,
    }}
    {...getTestProps(testId)}
  >
    {children}
  </View>
);

export const BillingMetricCard = ({ label, value, helper, colors, icon, testId }: { label: string; value: string; helper?: string; colors: any; icon: keyof typeof Ionicons.glyphMap; testId: string }) => (
  <View
    style={{
      flex: 1,
      minWidth: 150,
      borderRadius: 18,
      borderWidth: 1,
      borderColor: colors.border,
      backgroundColor: colors.bgSoft,
      padding: 14,
    }}
    {...getTestProps(testId)}
  >
    <View style={{ width: 38, height: 38, borderRadius: 12, backgroundColor: colors.primarySoft, alignItems: 'center', justifyContent: 'center' }}>
      <Ionicons name={icon} size={17} color={colors.primary} />
    </View>
    <Text style={{ color: colors.textMuted, fontSize: 10, fontWeight: '800', textTransform: 'uppercase', letterSpacing: 0.8, marginTop: 10 }}>{label}</Text>
    <Text style={{ color: colors.text, fontSize: 22, fontWeight: '900', marginTop: 5 }}>{value}</Text>
    {!!helper && <Text style={{ color: colors.textMuted, fontSize: 11, lineHeight: 16, marginTop: 6 }}>{helper}</Text>}
  </View>
);

export const BillingHeroPill = ({ label, value, colors, testId }: { label: string; value: string; colors: any; testId: string }) => (
  <View
    style={{
      paddingHorizontal: 14,
      paddingVertical: 10,
      borderRadius: 14,
      borderWidth: 1,
      borderColor: (globalThis as any).__alphaColor(colors.primaryText, '2E'),
      backgroundColor: (globalThis as any).__alphaColor(colors.primaryText, '12'),
      minWidth: 138,
    }}
    {...getTestProps(testId)}
  >
    <Text style={{ color: colors.primaryText + 'CC', fontSize: 10, fontWeight: '800', textTransform: 'uppercase', letterSpacing: 0.9 }}>{label}</Text>
    <Text style={{ color: colors.primaryText, fontSize: 17, fontWeight: '900', marginTop: 4 }}>{value}</Text>
  </View>
);

export const BillingActionButton = ({ label, onPress, icon, colors, testId, variant = 'primary', disabled = false }: { label: string; onPress: () => void; icon: keyof typeof Ionicons.glyphMap; colors: any; testId: string; variant?: 'primary' | 'secondary' | 'subtle' | 'success'; disabled?: boolean }) => {
  const backgroundColor = variant === 'primary'
    ? colors.text
    : variant === 'secondary'
      ? colors.primary
      : variant === 'success'
        ? colors.successSoft
        : colors.bgSoft;
  const textColor = variant === 'primary'
    ? colors.bg
    : variant === 'secondary'
      ? colors.primaryText
      : variant === 'success'
        ? colors.successText
        : colors.text;
  const borderColor = variant === 'subtle'
    ? colors.border
    : variant === 'success'
      ? colors.success + '44'
      : 'transparent';

  return (
    <TouchableOpacity accessibilityLabel="On press in billing route primitives button"
      onPress={onPress}
      disabled={disabled}
      style={{
        minHeight: 44,
        paddingHorizontal: 16,
        paddingVertical: 12,
        borderRadius: 12,
        borderWidth: 1,
        borderColor,
        backgroundColor,
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 8,
        opacity: disabled ? 0.65 : 1,
        ...(Platform.OS === 'web' ? { transition: 'opacity 160ms ease, transform 160ms ease' } as any : {}),
      }}
      {...getTestProps(testId)}
    >
      <Ionicons name={icon} size={16} color={textColor} />
      <Text style={{ color: textColor, fontSize: 12, fontWeight: '800' }}>{label}</Text>
    </TouchableOpacity>
  );
};
/* i18n-probe t('i18n.auto.probe') */
