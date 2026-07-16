import React from 'react';
import { Text, TouchableOpacity, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import type { PaymentMethodAvailability, PaymentMethodId } from '../../services/subscriptionPaymentMethods';
import { useTheme } from '../../context/ThemeContext';

type SelectorColors = {
  surface: string;
  border: string;
  text: string;
  textMuted: string;
  primary: string;
  warningText: string;
  successText: string;
};

type PaymentMethodOption = {
  id: PaymentMethodId;
  title: string;
  subtitle: string;
  iconName: keyof typeof Ionicons.glyphMap;
  iconColor: string;
  iconBg: string;
  testId: string;
  unavailableNoteTestId?: string;
  inlineNote?: string;
};

type Props = {
  mode: 'navigate' | 'select';
  options: PaymentMethodOption[];
  availability: Record<PaymentMethodId, PaymentMethodAvailability>;
  selected?: PaymentMethodId | null;
  onSelect: (id: PaymentMethodId) => void;
  colors: SelectorColors;
  containerTestId: string;
};

export const PaymentMethodSelector = ({
  mode,
  options,
  availability,
  selected,
  onSelect,
  colors,
  containerTestId,
}: Props) => {
  const { colors: themeColors } = useTheme();
  const mutedText = colors.textMuted || themeColors.textMuted;

  return (
    <View style={{ gap: 8 }} data-testid={containerTestId} testID={containerTestId}>
      {options.map((option) => {
        const isSelected = selected === option.id;
        const available = availability[option.id]?.available !== false;
        const unavailableReason = availability[option.id]?.reason || 'Unavailable';

        return (
          <TouchableOpacity accessibilityLabel="On select in payment method selector button"
            key={option.id}
            style={{
              flexDirection: 'row',
              alignItems: 'center',
              gap: 12,
              backgroundColor: colors.surface,
              borderRadius: 14,
              padding: 16,
              borderWidth: 1.5,
              borderColor: isSelected ? colors.primary : colors.border,
              opacity: available ? 1 : 0.55,
            }}
            onPress={() => onSelect(option.id)}
            disabled={!available}
            data-testid={option.testId}
            testID={option.testId}
          >
            <View
              style={{
                width: 40,
                height: 40,
                borderRadius: 10,
                backgroundColor: option.iconBg,
                alignItems: 'center',
                justifyContent: 'center',
              }}
            >
              <Ionicons name={option.iconName} size={20} color={option.iconColor} />
            </View>

            <View style={{ flex: 1 }}>
              <Text style={{ fontWeight: isSelected ? '800' : '700', color: colors.text, fontSize: 14 }}>{option.title}</Text>
              <Text style={{ color: mutedText, fontSize: 11 }}>{option.subtitle}</Text>
              {option.inlineNote ? <Text style={{ color: option.iconColor, fontSize: 10, marginTop: 2 }}>{option.inlineNote}</Text> : null}
              {!available ? (
                <Text
                  style={{ color: colors.warningText, fontSize: 10, marginTop: 2 }}
                  data-testid={option.unavailableNoteTestId || `${option.testId}-unavailable-note`}
                  testID={option.unavailableNoteTestId || `${option.testId}-unavailable-note`}
                >
                  {unavailableReason}
                </Text>
              ) : null}
            </View>

            {mode === 'navigate' ? (
              <Ionicons name="chevron-forward" size={18} color={mutedText} />
            ) : isSelected ? (
              <Ionicons name="checkmark-circle" size={22} color={colors.primary} />
            ) : null}
          </TouchableOpacity>
        );
      })}
    </View>
  );
};

/* i18n-probe t('i18n.auto.probe') */
