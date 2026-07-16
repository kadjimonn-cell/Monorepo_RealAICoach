import React from 'react';
import { View, Text } from 'react-native';
import { useTranslation } from '../../hooks/useTranslation';
import { useTheme } from '../../context/ThemeContext';

type MiniSparklineProps = {
  data: number[];
  color: string;
  width?: number;
  height?: number;
  testId: string;
};

export const MiniSparkline = ({
  data,
  color,
  width = 200,
  height = 44,
  testId,
}: MiniSparklineProps) => {
  const { t } = useTranslation();
  const { colors } = useTheme();
  const tx = React.useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);
  if (!data || data.length < 2) {
    return (
      <Text style={{ fontSize: 11, color: colors.textMuted }} data-testid={`${testId}-empty`} testID={`${testId}-empty`}>
        {tx('admin.miniSparkline.trendUnavailable', 'Trend unavailable')}
      </Text>
    );
  }

  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min || 1;
  const points = data
    .map((value, index) => {
      const x = (index / (data.length - 1)) * width;
      const y = height - ((value - min) / range) * (height - 6) - 3;
      return `${x},${y}`;
    })
    .join(' ');

  return (
    <View style={{ width, height }} data-testid={testId} testID={testId}>
      <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`}>
        <polyline fill="none" stroke={color} strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" points={points} />
        <polyline fill={`${color}22`} stroke="none" points={`0,${height} ${points} ${width},${height}`} />
      </svg>
    </View>
  );
};

export default MiniSparkline;
