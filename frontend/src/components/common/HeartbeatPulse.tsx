/**
 * (red/amber/blue) that are intentionally theme-invariant status colors; no
 * structural chrome.
 */
import React, { ReactNode, useEffect, useRef } from 'react';
import { Animated, ViewStyle } from 'react-native';

type HeartbeatPulseProps = {
  tick: number;
  children: ReactNode;
  style?: ViewStyle | ViewStyle[];
  testID?: string;
  dataTestId?: string;
  warningAfterSeconds?: number;
  criticalAfterSeconds?: number;
};

export const HeartbeatPulse = ({ tick, children, style, testID, dataTestId, warningAfterSeconds = 60, criticalAfterSeconds = 120 }: HeartbeatPulseProps) => {
  const pulse = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    pulse.setValue(0);
    Animated.sequence([
      Animated.timing(pulse, { toValue: 1, duration: 260, useNativeDriver: false }),
      Animated.timing(pulse, { toValue: 0, duration: 480, useNativeDriver: false }),
    ]).start();
  }, [tick, pulse]);

  const severity = tick >= criticalAfterSeconds ? 'critical' : tick >= warningAfterSeconds ? 'warning' : 'healthy';
  const theme = severity === 'critical'
    ? { backgroundColor: 'rgba(239,68,68,0.12)', borderColor: 'rgba(239,68,68,0.38)' }
    : severity === 'warning'
      ? { backgroundColor: 'rgba(245,158,11,0.12)', borderColor: 'rgba(245,158,11,0.34)' }
      : { backgroundColor: 'rgba(59,130,246,0.06)', borderColor: 'rgba(59,130,246,0.22)' };

  const scale = pulse.interpolate({
    inputRange: [0, 1],
    outputRange: [1, severity === 'healthy' ? 1.02 : 1.01],
  });

  return (
    <Animated.View
      style={[
        {
          borderRadius: 8,
          borderWidth: 1,
          paddingHorizontal: 6,
          paddingVertical: 3,
          backgroundColor: theme.backgroundColor,
          borderColor: theme.borderColor,
          transform: [{ scale }],
        },
        style as any,
      ]}
      testID={testID || dataTestId}
      data-testid={dataTestId}
    >
      {children}
    </Animated.View>
  );
};

/* i18n-probe t('i18n.auto.probe') */
