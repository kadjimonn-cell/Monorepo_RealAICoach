import React from 'react';
import { View, Text, Platform, useWindowDimensions, TouchableOpacity } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { useTheme } from '../../context/ThemeContext';
import { useTranslation } from '../../hooks/useTranslation';
import { useLiveQuery } from '../../hooks/useLiveQuery';
import { BODY_FONT_FAMILY, DISPLAY_FONT_FAMILY } from '../../constants/appTypography';

type ArcadeChallengeData = {
  target: number;
  completed_today: boolean;
  streak: number;
  personal_best: number;
};

export default function HomeArcadeChallenge({ responsiveWidth }: { responsiveWidth?: number }) {
  const { width: windowWidth } = useWindowDimensions();
  const width = responsiveWidth || windowWidth;
  const isDesktop = width >= 768;
  const { colors, darkMode } = useTheme();
  const { tx } = useTranslation();
  const router = useRouter();

  const { data } = useLiveQuery('/flappy-bird/daily-challenge', { entity: 'flappy_daily_challenge', pollInterval: 120000 });
  const challenge: ArcadeChallengeData | null = data || null;

  const alpha = (c: string, a: string) => (globalThis as any).__alphaColor?.(c, a) || c;
  const surfaceBorder = darkMode ? 'rgba(255,255,255,0.06)' : colors.border;

  if (!challenge) return null;

  const done = Boolean(challenge.completed_today);
  const title = done
    ? tx('home.arcade.doneTitle', 'Daily challenge complete!')
    : tx('home.arcade.title', 'Score {target}+ in Flappy Bird').replace('{target}', String(challenge.target));
  const subtitle = done
    ? tx('home.arcade.doneSubtitle', 'Come back tomorrow to keep your streak alive.')
    : tx('home.arcade.subtitle', 'One run is all it takes — beat the target to earn a +20 XP bonus.');

  if (Platform.OS !== 'web') {
    return (
      <View data-testid="home-arcade-challenge" testID="home-arcade-challenge" style={{ paddingHorizontal: 20, paddingBottom: 24 }}>
        <View style={{ padding: 16, borderRadius: 16, backgroundColor: colors.card, borderWidth: 1, borderColor: colors.border }}>
          <Text style={{ fontSize: 17, fontWeight: '800', color: colors.text }}>{title}</Text>
          <TouchableOpacity onPress={() => router.push('/features/flappy-bird')} style={{ marginTop: 10 }} data-testid="home-arcade-cta" testID="home-arcade-cta">
            <Text style={{ color: colors.primary, fontWeight: '700', fontSize: 13 }}>{tx('home.arcade.cta', 'Play now')}</Text>
          </TouchableOpacity>
        </View>
      </View>
    );
  }

  return (
    <View data-testid="home-arcade-challenge" testID="home-arcade-challenge" style={{ paddingHorizontal: isDesktop ? 40 : 20, paddingBottom: 32 }}>
      <div style={{
        padding: 22, borderRadius: 18,
        background: colors.card,
        border: `1px solid ${done ? alpha(colors.success, '40') : surfaceBorder}`,
        boxShadow: darkMode ? '0 18px 40px rgba(0,0,0,0.26)' : '0 14px 30px rgba(15,23,42,0.08)',
      } as any}>
        <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', justifyContent: 'space-between', gap: 12 } as any}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 14, minWidth: 0 } as any}>
            <div style={{
              width: 46, height: 46, borderRadius: 14, flexShrink: 0,
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              background: alpha(done ? colors.success : colors.warning, '14'),
              border: `1px solid ${alpha(done ? colors.success : colors.warning, '30')}`,
            } as any}>
              <Ionicons name={done ? 'checkmark-circle' : 'game-controller'} size={22} color={done ? colors.successText : colors.warningText} />
            </div>
            <div style={{ minWidth: 0 } as any}>
              <span style={{ color: colors.textMuted, fontSize: 10, fontWeight: 800, letterSpacing: 1.8, textTransform: 'uppercase', fontFamily: BODY_FONT_FAMILY } as any} data-testid="home-arcade-kicker">
                {tx('home.arcade.kicker', "Today's arcade challenge")}
              </span>
              <div style={{ color: colors.text, fontSize: 17, fontWeight: 800, letterSpacing: -0.4, marginTop: 4, fontFamily: DISPLAY_FONT_FAMILY } as any} data-testid="home-arcade-title">
                {title}
              </div>
              <div style={{ color: colors.textMuted, fontSize: 12, marginTop: 3, fontFamily: BODY_FONT_FAMILY } as any} data-testid="home-arcade-subtitle">
                {subtitle}
              </div>
            </div>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' } as any}>
            <span data-testid="home-arcade-streak" style={{
              display: 'inline-flex', alignItems: 'center', gap: 6,
              padding: '6px 12px', borderRadius: 999, fontSize: 12, fontWeight: 800,
              color: colors.warningText, fontFamily: BODY_FONT_FAMILY,
              background: alpha(colors.warning, '12'), border: `1px solid ${alpha(colors.warning, '2E')}`,
            } as any}>
              <Ionicons name="flame" size={13} color={colors.warningText} />
              {challenge.streak} {tx('home.arcade.streak', 'day streak')}
            </span>
            {challenge.personal_best > 0 && (
              <span data-testid="home-arcade-best" style={{
                display: 'inline-flex', alignItems: 'center', gap: 6,
                padding: '6px 12px', borderRadius: 999, fontSize: 12, fontWeight: 800,
                color: colors.textMuted, fontFamily: BODY_FONT_FAMILY,
                border: `1px solid ${surfaceBorder}`,
              } as any}>
                <Ionicons name="trophy-outline" size={13} color={colors.warningText} />
                {tx('home.arcade.best', 'Best')}: {challenge.personal_best}
              </span>
            )}
            <button
              onClick={() => router.push('/features/flappy-bird')}
              data-testid="home-arcade-cta"
              style={{
                padding: '9px 18px', borderRadius: 999, fontSize: 12, fontWeight: 800, cursor: 'pointer',
                fontFamily: BODY_FONT_FAMILY, background: colors.primary, color: colors.primaryText,
                border: `1px solid ${colors.primary}`, transition: 'opacity 0.2s ease',
              } as any}
            >
              {done ? tx('home.arcade.playMore', 'Play again') : tx('home.arcade.cta', 'Play now')}
            </button>
          </div>
        </div>
      </div>
    </View>
  );
}
