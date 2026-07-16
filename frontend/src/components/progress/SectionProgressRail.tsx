import React from 'react';
import { Text, TouchableOpacity, View } from 'react-native';
import { useTranslation } from '../../hooks/useTranslation';

type RailItem = {
  id: string;
  label: string;
};

type SectionProgressRailProps = {
  items: RailItem[];
  activeId: string;
  onSelect: (id: string) => void;
  colors: any;
  visible?: boolean;
  railTestId: string;
  top?: number;
  right?: number;
  maxWidth?: number;
};

export const SectionProgressRail = ({
  items,
  activeId,
  onSelect,
  colors,
  visible = true,
  railTestId,
  top = 124,
  right = 12,
  maxWidth = 170,
}: SectionProgressRailProps) => {
  const { tx } = useTranslation();
  if (!visible || !Array.isArray(items) || items.length === 0) return null;

  return (
    <View
      style={{
        position: 'absolute',
        right,
        top,
        zIndex: 8,
        borderRadius: 18,
        borderWidth: 1,
        borderColor: colors.border,
        backgroundColor: `${colors.card}F2`,
        paddingHorizontal: 10,
        paddingVertical: 12,
        gap: 8,
        maxWidth,
        boxShadow: '0 18px 40px rgba(15, 23, 42, 0.08)',
      }}
      data-testid={railTestId}
      testID={railTestId}
    >
      <Text
        style={{
          color: colors.textMuted,
          fontSize: 9,
          fontWeight: '800',
          letterSpacing: 1.4,
          textTransform: 'uppercase',
          paddingHorizontal: 4,
        }}
        data-testid={`${railTestId}-label`}
        testID={`${railTestId}-label`}
      >
        {tx('home.progressRail.title', 'Progress map')}
      </Text>
      {items.map((item) => {
        const active = activeId === item.id;
        return (
          <TouchableOpacity accessibilityLabel="On select in section progress rail button"
            key={item.id}
            onPress={() => onSelect(item.id)}
            style={{
              borderRadius: 12,
              borderWidth: 1,
              borderColor: active ? colors.primary : colors.border,
              backgroundColor: active ? `${colors.primary}18` : `${colors.surface}F2`,
              paddingHorizontal: 12,
              paddingVertical: 8,
              boxShadow: active ? '0 10px 24px rgba(15, 23, 42, 0.08)' : 'none',
            }}
            data-testid={`${railTestId}-item-${item.id}`}
            testID={`${railTestId}-item-${item.id}`}
          >
            <Text style={{ color: active ? colors.primary : colors.textMuted, fontSize: 10, fontWeight: '800', letterSpacing: 0.2 }} numberOfLines={1}>
              {item.label}
            </Text>
          </TouchableOpacity>
        );
      })}
    </View>
  );
};

/* i18n-probe t('i18n.auto.probe') */
