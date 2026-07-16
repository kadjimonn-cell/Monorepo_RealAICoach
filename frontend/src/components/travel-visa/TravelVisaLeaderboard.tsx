import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { View, Text, TouchableOpacity, ScrollView, ActivityIndicator, Platform, Image } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useTheme } from '../../context/ThemeContext';
import { useLanguage } from '../../i18n/LanguageContext';
import api from '../../services/api';

const WEB_TRANSITION = Platform.OS === 'web' ? ({ transition: 'all 0.2s ease' } as any) : {};

export default function TravelVisaLeaderboard({ userId }: { userId: string }) {
  const { colors, darkMode } = useTheme();
  const { t } = useLanguage();
  const tx = React.useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);
  const tierConfig = useMemo<Record<string, { color: string; icon: string; label: string }>>(() => ({
    diamond: { color: colors.info, icon: 'diamond', label: 'Diamond' },
    platinum: { color: colors.primary, icon: 'star', label: 'Platinum' },
    gold: { color: colors.warning, icon: 'trophy', label: 'Gold' },
    silver: { color: colors.textMuted, icon: 'medal', label: 'Silver' },
    bronze: { color: colors.primary, icon: 'ribbon', label: 'Bronze' },
  }), [colors.info, colors.primary, colors.warning, colors.textMuted]);
  const [mode, setMode] = useState<'weekly' | 'alltime'>('weekly');
  const [leaders, setLeaders] = useState<any[]>([]);
  const [myPosition, setMyPosition] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [pageError, setPageError] = useState('');

  const loadData = useCallback(async () => {
    setLoading(true);
    setPageError('');
    const [lbRes, meRes] = await Promise.allSettled([
      api.get(`/travel-visa/leaderboard/${mode}`),
      userId ? api.get(`/travel-visa/leaderboard/me/${userId}`) : Promise.resolve({ data: null }),
    ]);

    if (lbRes.status === 'fulfilled') {
      setLeaders(lbRes.value.data?.leaderboard || []);
    } else {
      setLeaders([]);
      setPageError((lbRes.reason as any)?.response?.data?.detail || tx('travelVisa.leaderboard.errors.unavailable', 'Leaderboard is unavailable right now.'));
    }

    if (meRes.status === 'fulfilled') {
      setMyPosition(meRes.value?.data || null);
    } else {
      setMyPosition(null);
      setPageError((prev) => prev || ((meRes.reason as any)?.response?.data?.detail || tx('travelVisa.leaderboard.errors.positionUnavailable', 'Your leaderboard position could not be loaded.')));
    }
    setLoading(false);
  }, [mode, userId]);

  useEffect(() => { loadData(); }, [loadData]);

  const rankMedal = (rank: number) => {
    if (rank === 1) return { icon: 'trophy', color: colors.warning, bg: colors.primary };
    if (rank === 2) return { icon: 'medal', color: colors.textMuted, bg: colors.primaryText };
    if (rank === 3) return { icon: 'medal', color: colors.primary, bg: colors.primary };
    return null;
  };

  return (
    <View data-testid="tv-leaderboard">
      {/* My Position Card */}
      {myPosition && myPosition.rank > 0 && (
        <View data-testid="tv-leaderboard-my-position" style={{
          padding: 18, borderRadius: 16, marginBottom: 16,
          backgroundColor: (globalThis as any).__alphaColor(darkMode ? colors.primarySoft : colors.primary, '08'),
          borderWidth: 1.5, borderColor: (globalThis as any).__alphaColor(colors.primary, '25'),
          ...(Platform.OS === 'web' ? { boxShadow: `0 2px 12px ${colors.primary}15` } as any : {}),
        }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 14 }}>
            <View style={{
              width: 52, height: 52, borderRadius: 14, backgroundColor: colors.primary,
              alignItems: 'center', justifyContent: 'center',
            }}>
              <Text style={{ fontSize: 20, fontWeight: '900', color: colors.primaryText }}>#{myPosition.rank}</Text>
            </View>
            <View style={{ flex: 1 }}>
              <Text style={{ fontSize: 15, fontWeight: '700', color: colors.text }}>{tx('travelVisa.leaderboard.myRank', 'Your Rank')}</Text>
              <Text style={{ fontSize: 12, color: colors.textMuted }}>
                Top {myPosition.percentile}% | {myPosition.total_xp} XP | {myPosition.streak}d streak
              </Text>
            </View>
            <View style={{ alignItems: 'center' }}>
              <Ionicons
                name={(tierConfig[myPosition.tier]?.icon || 'ribbon') + '-outline' as any}
                size={24} color={tierConfig[myPosition.tier]?.color || colors.primary}
              />
              <Text style={{
                fontSize: 10, fontWeight: '700', marginTop: 2,
                color: tierConfig[myPosition.tier]?.color || colors.primary,
                textTransform: 'uppercase',
              }}>{myPosition.tier}</Text>
            </View>
          </View>
          <View style={{ flexDirection: 'row', gap: 8, marginTop: 12, flexWrap: 'wrap' }}>
            {[
              { label: tx('travelVisa.leaderboard.labels.lessons', 'Lessons'), value: myPosition.lessons_completed, icon: 'book-outline' },
              { label: tx('travelVisa.leaderboard.labels.quizzes', 'Quizzes'), value: myPosition.quizzes_passed, icon: 'checkmark-circle-outline' },
              { label: tx('travelVisa.leaderboard.labels.sims', 'Sims'), value: myPosition.simulations_completed, icon: 'videocam-outline' },
            ].map((s, i) => (
              <View key={i} style={{
                flexDirection: 'row', alignItems: 'center', gap: 4,
                paddingHorizontal: 10, paddingVertical: 5, borderRadius: 8,
                backgroundColor: colors.surfaceHover, borderWidth: 1, borderColor: colors.border,
              }}>
                <Ionicons name={s.icon as any} size={12} color={colors.primary} />
                <Text style={{ fontSize: 11, fontWeight: '600', color: colors.text }}>{s.value}</Text>
                <Text style={{ fontSize: 10, color: colors.textMuted }}>{s.label}</Text>
              </View>
            ))}
          </View>
        </View>
      )}

      {/* Mode Toggle */}
      <View style={{ flexDirection: 'row', gap: 6, marginBottom: 14 }}>
        {(['weekly', 'alltime'] as const).map(m => (
          <TouchableOpacity key={m} data-testid={`tv-lb-mode-${m}`}
            onPress={() => setMode(m)}
            style={{
              flex: 1, paddingVertical: 10, borderRadius: 10, alignItems: 'center',
              backgroundColor: mode === m ? colors.primary : colors.surfaceHover,
              borderWidth: 1, borderColor: mode === m ? colors.primary : colors.border,
              ...WEB_TRANSITION,
            }}>
            <Text style={{ fontSize: 13, fontWeight: '600', color: mode === m ? colors.primaryText : colors.text }}>
              {m === 'weekly' ? tx('travelVisa.leaderboard.filters.thisWeek', 'This Week') : tx('travelVisa.leaderboard.filters.allTime', 'All Time')}
            </Text>
          </TouchableOpacity>
        ))}
      </View>

      {!!pageError && (
        <View data-testid="tv-lb-error" style={{ borderRadius: 10, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(colors.error, '55'), backgroundColor: colors.errorSoft, padding: 10, marginBottom: 12 }}>
          <Text style={{ fontSize: 11, color: colors.errorText, fontWeight: '700', marginBottom: 8 }}>{pageError}</Text>
          <TouchableOpacity data-testid="tv-lb-retry-btn" onPress={() => void loadData()} style={{ alignSelf: 'flex-start', borderRadius: 8, backgroundColor: colors.error, paddingHorizontal: 10, paddingVertical: 6 }}>
            <Text style={{ fontSize: 11, color: colors.errorTextInverse || colors.primaryText, fontWeight: '800' }}>{tx('common.retry', 'Retry')}</Text>
          </TouchableOpacity>
        </View>
      )}

      {loading ? (
        <View style={{ padding: 40, alignItems: 'center' }}>
          <ActivityIndicator size="large" color={colors.primary} />
        </View>
      ) : leaders.length === 0 ? (
        <View data-testid="tv-lb-empty" style={{
          padding: 40, alignItems: 'center', borderRadius: 16,
          backgroundColor: colors.card, borderWidth: 1, borderColor: colors.border,
        }}>
          <Ionicons name="podium-outline" size={48} color={colors.textMuted} />
          <Text style={{ fontSize: 16, fontWeight: '600', color: colors.text, marginTop: 12 }}>{tx('travelVisa.leaderboard.states.noneYet', 'No leaders yet')}</Text>
          <Text style={{ fontSize: 13, color: colors.textMuted, marginTop: 4, textAlign: 'center' }}>
            {tx('travelVisa.leaderboard.states.noneYetDescription', 'Complete lessons, quizzes, and simulations to earn XP and climb the leaderboard!')}
          </Text>
        </View>
      ) : (
        <>
          {/* Top 3 Podium */}
          {leaders.length >= 3 && (
            <View data-testid="tv-lb-podium" style={{
              flexDirection: 'row', alignItems: 'flex-end', justifyContent: 'center',
              gap: 8, marginBottom: 16, paddingTop: 10,
            }}>
              {[leaders[1], leaders[0], leaders[2]].map((entry, i) => {
                const isCenter = i === 1;
                const medal = rankMedal(entry.rank);
                const tierCfg = tierConfig[entry.tier] || tierConfig.bronze;
                return (
                  <View key={entry.user_id || i} style={{
                    flex: 1, alignItems: 'center', padding: 14,
                    paddingTop: isCenter ? 24 : 16,
                    borderRadius: 14, backgroundColor: colors.card,
                    borderWidth: isCenter ? 2 : 1,
                    borderColor: isCenter ? colors.primary : colors.border,
                    minHeight: isCenter ? 160 : 140,
                    ...(Platform.OS === 'web' ? { boxShadow: isCenter ? `0 4px 16px ${colors.primary}20` : `0 2px 8px ${colors.shadowColor}` } as any : {}),
                  }}>
                    {medal && (
                      <View style={{
                        width: 28, height: 28, borderRadius: 14, backgroundColor: medal.bg,
                        alignItems: 'center', justifyContent: 'center', marginBottom: 6,
                      }}>
                        <Ionicons name={medal.icon as any} size={16} color={medal.color} />
                      </View>
                    )}
                    <View style={{
                      width: isCenter ? 48 : 40, height: isCenter ? 48 : 40,
                      borderRadius: isCenter ? 24 : 20,
                      backgroundColor: (globalThis as any).__alphaColor(colors.primary, '20'),
                      alignItems: 'center', justifyContent: 'center',
                      borderWidth: 2, borderColor: tierCfg.color,
                    }}>
                      {entry.avatar ? (
                        Platform.OS === 'web' ? (
                          <img accessibilityLabel="Decorative image"
                            src={entry.avatar}
                            aria-label="Decorative image"
                            style={{
                              width: isCenter ? 44 : 36,
                              height: isCenter ? 44 : 36,
                              borderRadius: isCenter ? 22 : 18,
                              objectFit: 'cover',
                            }}
                            alt=""
                          />
                        ) : (
                          <Image source={{ uri: entry.avatar }} accessibilityLabel="Decorative image" style={{
                            width: isCenter ? 44 : 36, height: isCenter ? 44 : 36,
                            borderRadius: isCenter ? 22 : 18,
                          }} />
                        )
                      ) : (
                        <Text style={{ fontSize: isCenter ? 18 : 14, fontWeight: '800', color: colors.primary }}>
                          {(entry.name || '?')[0].toUpperCase()}
                        </Text>
                      )}
                    </View>
                    <Text style={{ fontSize: 12, fontWeight: '700', color: colors.text, marginTop: 6, textAlign: 'center' }} numberOfLines={1}>
                      {entry.name}
                    </Text>
                    <Text style={{ fontSize: 16, fontWeight: '900', color: colors.primary, marginTop: 2 }}>
                      {entry.total_xp?.toLocaleString()} XP
                    </Text>
                    <View style={{
                      paddingHorizontal: 6, paddingVertical: 2, borderRadius: 4, marginTop: 4,
                      backgroundColor: (globalThis as any).__alphaColor(tierCfg.color, '20'),
                    }}>
                      <Text style={{ fontSize: 9, fontWeight: '700', color: tierCfg.color, textTransform: 'uppercase' }}>
                        {entry.tier}
                      </Text>
                    </View>
                  </View>
                );
              })}
            </View>
          )}

          {/* Remaining Leaders List */}
          {leaders.slice(3).map((entry, i) => {
            const tierCfg = tierConfig[entry.tier] || tierConfig.bronze;
            const isMe = entry.user_id === userId;
            return (
              <View data-testid={`tv-lb-row-${entry.rank}`} key={entry.user_id || i} style={{
                flexDirection: 'row', alignItems: 'center', gap: 12,
                padding: 12, borderRadius: 12, marginBottom: 6,
                backgroundColor: isMe ? colors.primarySoft : colors.card,
                borderWidth: 1, borderColor: isMe ? (globalThis as any).__alphaColor(colors.primary, '40') : colors.border,
                ...WEB_TRANSITION,
              }}>
                <Text style={{
                  width: 28, textAlign: 'center', fontSize: 14,
                  fontWeight: '700', color: colors.textMuted,
                }}>#{entry.rank}</Text>
                <View style={{
                  width: 36, height: 36, borderRadius: 18,
                  backgroundColor: (globalThis as any).__alphaColor(colors.primary, '20'),
                  alignItems: 'center', justifyContent: 'center',
                  borderWidth: 1.5, borderColor: (globalThis as any).__alphaColor(tierCfg.color, '40'),
                }}>
                  {entry.avatar ? (
                    Platform.OS === 'web' ? (
                      <img src={entry.avatar} style={{ width: 32, height: 32, borderRadius: 16, objectFit: 'cover' } as any} alt="" />
                    ) : (
                      <Image source={{ uri: entry.avatar }} style={{ width: 32, height: 32, borderRadius: 16 }} accessibilityLabel="Decorative image" />
                    )
                  ) : (
                    <Text style={{ fontSize: 13, fontWeight: '700', color: colors.primary }}>
                      {(entry.name || '?')[0].toUpperCase()}
                    </Text>
                  )}
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={{ fontSize: 13, fontWeight: '600', color: colors.text }} numberOfLines={1}>
                    {entry.name} {isMe ? `(${tx('travelVisa.leaderboard.labels.you', 'You')})` : ''}
                  </Text>
                  <Text style={{ fontSize: 11, color: colors.textMuted }}>
                    {entry.streak || 0}d streak | {entry.lessons_completed || 0} lessons
                  </Text>
                </View>
                <View style={{ alignItems: 'flex-end' }}>
                  <Text style={{ fontSize: 14, fontWeight: '800', color: colors.text }}>{entry.total_xp?.toLocaleString()}</Text>
                  <View style={{
                    paddingHorizontal: 6, paddingVertical: 1, borderRadius: 4, marginTop: 2,
                    backgroundColor: (globalThis as any).__alphaColor(tierCfg.color, '20'),
                  }}>
                    <Text style={{ fontSize: 9, fontWeight: '700', color: tierCfg.color, textTransform: 'uppercase' }}>{entry.tier}</Text>
                  </View>
                </View>
              </View>
            );
          })}
        </>
      )}
    </View>
  );
}
