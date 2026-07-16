import React from 'react';
import { View, Text, TouchableOpacity } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useTranslation } from '../../hooks/useTranslation';

interface PlatformDataStatusPanelProps {
  consoleType: 'executive' | 'operations';
  tabId: string;
  tabLabel: string;
  phase: 'C';
  colors: any;
  compact?: boolean;
  onOpenVerifiedTab?: () => void;
}

export const PlatformDataStatusPanel: React.FC<PlatformDataStatusPanelProps> = ({
  consoleType,
  tabId,
  tabLabel,
  phase,
  colors,
  compact = false,
  onOpenVerifiedTab,
}) => {
  const { t } = useTranslation();
  const tx = React.useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);

  const statusColor = colors.info;
  const statusBg = `${colors.info}12`;
  const title = tx('platformData.status.phaseC.title', 'Live-wired tab running in safe mode pending full E2E evidence tag');
  const subtitle = tx(
    'platformData.status.phaseC.subtitle',
    'This tab remains accessible with live wiring while explicit tab-level E2E evidence is being finalized in the current cycle.',
  );

  return (
    <View
      style={{
        borderRadius: 14,
        borderWidth: 1,
        borderColor: statusColor,
        backgroundColor: statusBg,
        padding: compact ? 12 : 16,
        gap: 8,
        width: '100%',
      }}
      data-testid={`platform-data-status-panel-${consoleType}-${tabId}`}
      testID={`platform-data-status-panel-${consoleType}-${tabId}`}
    >
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
        <View
          style={{
            borderRadius: 999,
            paddingHorizontal: 8,
            paddingVertical: 4,
            backgroundColor: `${statusColor}1F`,
          }}
          data-testid={`platform-data-status-badge-${consoleType}-${tabId}`}
          testID={`platform-data-status-badge-${consoleType}-${tabId}`}
        >
          <Text style={{ color: statusColor, fontSize: 10, fontWeight: '900' }}>
            PHASE C (SAFE MODE · E2E PENDING)
          </Text>
        </View>
        <Text
          style={{ color: colors.text, fontSize: compact ? 12 : 13, fontWeight: '800', flexShrink: 1 }}
          data-testid={`platform-data-status-title-${consoleType}-${tabId}`}
          testID={`platform-data-status-title-${consoleType}-${tabId}`}
        >
          {title}
        </Text>
      </View>

      <Text
        style={{ color: colors.textMuted, fontSize: compact ? 11 : 12, lineHeight: compact ? 16 : 18 }}
        data-testid={`platform-data-status-subtitle-${consoleType}-${tabId}`}
        testID={`platform-data-status-subtitle-${consoleType}-${tabId}`}
      >
        {subtitle}
      </Text>

      <Text
        style={{ color: colors.text, fontSize: 11, fontWeight: '700' }}
        data-testid={`platform-data-status-context-${consoleType}-${tabId}`}
        testID={`platform-data-status-context-${consoleType}-${tabId}`}
      >
        {tx('platformData.status.context', 'Console')}: {consoleType} · {tx('platformData.status.tab', 'Tab')}: {tabLabel} ({tabId})
      </Text>

      {onOpenVerifiedTab ? (
        <TouchableOpacity accessibilityLabel="On open verified tab in platform data status panel"
          onPress={onOpenVerifiedTab}
          style={{
            marginTop: 2,
            alignSelf: 'flex-start',
            borderRadius: 10,
            borderWidth: 1,
            borderColor: colors.primary,
            backgroundColor: `${colors.primary}12`,
            paddingHorizontal: 10,
            paddingVertical: 8,
            flexDirection: 'row',
            alignItems: 'center',
            gap: 6,
          }}
          data-testid={`platform-data-status-open-verified-tab-${consoleType}-${tabId}`}
          testID={`platform-data-status-open-verified-tab-${consoleType}-${tabId}`}
        >
          <Ionicons name="checkmark-circle" size={13} color={colors.primary} />
          <Text style={{ color: colors.primary, fontSize: 11, fontWeight: '800' }}>
            {tx('platformData.status.openVerified', 'Open verified live-data tab')}
          </Text>
        </TouchableOpacity>
      ) : null}
    </View>
  );
};
