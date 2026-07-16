import React, { useEffect, useRef } from 'react';
import { View, Text, Animated } from 'react-native';
import Svg, { Polygon, Circle, Line, Text as SvgText } from 'react-native-svg';
import { useTheme } from '../../context/ThemeContext';

interface RadarChartProps {
  size?: number;
  skills: { label: string; value: number; color?: string }[];
  primaryColor?: string;
  gridColor?: string;
  testID?: string;
}

// eslint-disable-next-line @typescript-eslint/no-unused-vars
const _AnimatedPolygon = Animated.createAnimatedComponent(Polygon);

export default function RadarChart({
  size = 220,
  skills,
  primaryColor,
  gridColor,
  testID = 'radar-chart',
}: RadarChartProps) {
  const { colors } = useTheme();
  const cx = size / 2;
  const cy = size / 2;
  const maxR = size * 0.36;
  const gridLevels = [0.25, 0.5, 0.75, 1.0];
  const n = skills.length;
  const progress = useRef(new Animated.Value(0)).current;
  const chartPrimary = primaryColor || colors.chartLinePrimary || 'var(--app-primary)';
  const chartGrid = gridColor || 'var(--app-text)';
  const chartAxis = 'var(--app-text-muted)' || 'var(--app-text-muted)';
  const chartPillBg = colors.cardMuted || colors.bgSoft || colors.bgAlt;

  useEffect(() => {
    Animated.timing(progress, {
      toValue: 1,
      duration: 900,
      useNativeDriver: false,
    }).start();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Get angle for axis i: start from top (-90 deg), go clockwise
  const angle = (i: number) => (-Math.PI / 2) + (i * 2 * Math.PI) / n;

  // Grid polygon points at a given radius fraction
  const gridPoints = (fraction: number) =>
    Array.from({ length: n }, (_, i) => {
      const r = maxR * fraction;
      return `${cx + r * Math.cos(angle(i))},${cy + r * Math.sin(angle(i))}`;
    }).join(' ');

  // Skill polygon points based on value 0-100
  const skillPoints = skills.map((s, i) => {
    const r = maxR * Math.max(0.05, (s.value / 100));
    return `${cx + r * Math.cos(angle(i))},${cy + r * Math.sin(angle(i))}`;
  }).join(' ');

  // Label positions (slightly outside the chart)
  const labelR = maxR * 1.25;
  const labelPositions = skills.map((s, i) => ({
    x: cx + labelR * Math.cos(angle(i)),
    y: cy + labelR * Math.sin(angle(i)),
    label: s.label,
    value: s.value,
  }));

  return (
    <View testID={testID} >
      <Svg width={size} height={size}>
        {/* Grid polygons */}
        {gridLevels.map((level, li) => (
          <Polygon
            key={li}
            points={gridPoints(level)}
            fill="none"
            stroke={chartGrid}
            strokeWidth={1}
            opacity={0.5}
          />
        ))}

        {/* Axis lines */}
        {skills.map((_, i) => {
          const r = maxR;
          return (
            <Line
              key={i}
              x1={cx}
              y1={cy}
              x2={cx + r * Math.cos(angle(i))}
              y2={cy + r * Math.sin(angle(i))}
              stroke={chartGrid}
              strokeWidth={1}
              opacity={0.4}
            />
          );
        })}

        {/* Skill fill polygon */}
        <Polygon
          points={skillPoints}
          fill={chartPrimary + '30'}
          stroke={chartPrimary}
          strokeWidth={2.5}
          strokeLinejoin="round"
        />

        {/* Skill dots */}
        {skills.map((s, i) => {
          const r = maxR * Math.max(0.05, s.value / 100);
          return (
            <Circle
              key={i}
              cx={cx + r * Math.cos(angle(i))}
              cy={cy + r * Math.sin(angle(i))}
              r={4}
              fill={chartPrimary}
              stroke={'var(--app-primary)'}
              strokeWidth={2}
            />
          );
        })}

        {/* Center dot */}
        <Circle cx={cx} cy={cy} r={3} fill={chartGrid} opacity={0.6} />

        {/* Labels */}
        {labelPositions.map((lp, i) => {
          const textAnchor =
            Math.abs(lp.x - cx) < 10 ? 'middle' : lp.x < cx ? 'end' : 'start';
          return (
            <SvgText
              key={i}
              x={lp.x}
              y={lp.y + 4}
              textAnchor={textAnchor}
              fontSize={9}
              fontWeight="600"
              fill={chartAxis}
              letterSpacing={0.5}
            >
              {lp.label.toUpperCase()}
            </SvgText>
          );
        })}
      </Svg>

      {/* Skill value pills below */}
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', justifyContent: 'center', gap: 6, marginTop: 4 }}>
        {skills.map((s, i) => (
          <View
            key={i}
            style={{ flexDirection: 'row', alignItems: 'center', gap: 4, backgroundColor: chartPillBg, borderRadius: 20, paddingHorizontal: 8, paddingVertical: 3 }}
            testID={`radar-skill-${s.label}`}
          >
            <View style={{ width: 6, height: 6, borderRadius: 3, backgroundColor: chartPrimary }} />
            <Text style={{ fontSize: 10, color: chartAxis, fontWeight: '600' }}>{s.label}</Text>
            <Text style={{ fontSize: 10, color: colors.primaryText, fontWeight: '800' }}>{s.value}</Text>
          </View>
        ))}
      </View>
    </View>
  );
}

/* i18n-probe t('i18n.auto.probe') */
