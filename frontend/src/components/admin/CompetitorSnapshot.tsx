import React from 'react';
import { View, Text } from 'react-native';
import { useExecTheme} from './ExecDashboardPanels';
import { useTranslation } from '../../hooks/useTranslation';

interface CompetitorSnapshotProps {
  keywords: any[];
  isDesktop: boolean;
}

export function CompetitorSnapshot({ keywords, isDesktop: d }: CompetitorSnapshotProps) {
  const T = useExecTheme();
  const { t } = useTranslation();
  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };
  if (keywords.length === 0) return null;

  return (
    <View style={{ marginTop: 16, backgroundColor: T.card, borderRadius: 14, padding: 16, borderWidth: 1, borderColor: T.border }} data-testid="competitor-comparison" testID="competitor-comparison">
      <Text style={{ color: T.text, fontSize: 14, fontWeight: '700', marginBottom: 12 }}>{tx('admin.competitorSnapshot.title', 'Competitor Snapshot')}</Text>
      <View style={{ flexDirection: d ? 'row' : 'column', gap: 10 }}>
        {['BetterUp', 'CoachHub', 'Torch'].map((comp, ci) => {
          const avgApple = keywords.reduce((sum, kw) => sum + (kw.competitors?.[ci]?.apple_rank || 50), 0) / Math.max(1, keywords.length);
          const avgGoogle = keywords.reduce((sum, kw) => sum + (kw.competitors?.[ci]?.google_rank || 50), 0) / Math.max(1, keywords.length);
          return (
            <View key={comp} style={{ flex: d ? 1 : undefined, padding: 14, borderRadius: 10, backgroundColor: T.bg, borderWidth: 1, borderColor: T.border }}>
              <Text style={{ color: T.text, fontSize: 13, fontWeight: '700', marginBottom: 8 }}>{comp}</Text>
              <View style={{ flexDirection: 'row', gap: 16 }}>
                <View>
                  <Text style={{ color: T.textMuted, fontSize: 9 }}>{tx('admin.competitorSnapshot.avgAppStore', 'Avg App Store')}</Text>
                  <Text style={{ color: T.textSec, fontSize: 15, fontWeight: '800' }}>#{Math.round(avgApple)}</Text>
                </View>
                <View>
                  <Text style={{ color: T.textMuted, fontSize: 9 }}>{tx('admin.competitorSnapshot.avgGooglePlay', 'Avg Google Play')}</Text>
                  <Text style={{ color: T.success, fontSize: 15, fontWeight: '800' }}>#{Math.round(avgGoogle)}</Text>
                </View>
              </View>
            </View>
          );
        })}
      </View>
    </View>
  );
}
