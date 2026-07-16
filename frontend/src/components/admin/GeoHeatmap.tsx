import React from 'react';
import { View, Text } from 'react-native';
import { useAdminTheme } from '../../hooks/useAdminTheme';

// eslint-disable-next-line @typescript-eslint/no-unused-vars
const REGIONS: Record<string, { x: number; y: number }> = {
  'NG': { x: 48, y: 52 }, 'GH': { x: 45, y: 53 }, 'KE': { x: 58, y: 55 },
  'TZ': { x: 57, y: 58 }, 'UG': { x: 55, y: 55 }, 'SN': { x: 40, y: 50 },
  'CI': { x: 43, y: 53 }, 'CM': { x: 50, y: 54 }, 'ZA': { x: 54, y: 68 },
  'RW': { x: 56, y: 56 }, 'BJ': { x: 47, y: 53 }, 'TG': { x: 46, y: 53 },
};

export default function GeoHeatmap({ revenueByCountry, accentColor, title }: {
  revenueByCountry: Record<string, any>; accentColor: string; title: string;
}) {
  const colors = useAdminTheme();
  const entries = Object.entries(revenueByCountry);
  if (!entries.length) return null;
  const maxRevenue = Math.max(...entries.map(([, v]: any) => v.revenue || 0), 1);

  return (
    <View style={{ backgroundColor: colors.card, borderRadius: 12, padding: 16, borderWidth: 1, borderColor: colors.border }}>
      <Text style={{ color: colors.text, fontSize: 14, fontWeight: '700', marginBottom: 12 }}>{title}</Text>
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
        {entries.map(([code, info]: any) => {
          const intensity = Math.max(0.2, (info.revenue || 0) / maxRevenue);
          return (
            <View key={code} style={{
              backgroundColor: accentColor + Math.round(intensity * 255).toString(16).padStart(2, '0'),
              borderRadius: 8, paddingVertical: 8, paddingHorizontal: 12, minWidth: 70, alignItems: 'center',
            }}>
              <Text style={{ color: colors.text, fontWeight: '800', fontSize: 16 }}>{code}</Text>
              <Text style={{ color: colors.text, fontSize: 11, opacity: 0.9 }}>${(info.revenue || 0).toLocaleString()}</Text>
            </View>
          );
        })}
      </View>
    </View>
  );
}

/* i18n-probe t('i18n.auto.probe') */
