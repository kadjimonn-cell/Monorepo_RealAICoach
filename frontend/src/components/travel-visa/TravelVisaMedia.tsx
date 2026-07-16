import React, { useState, useEffect, useCallback } from 'react';
import { View, Text, TouchableOpacity, ScrollView, ActivityIndicator, Platform, useWindowDimensions } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useTheme } from '../../context/ThemeContext';
import { useLanguage } from '../../i18n/LanguageContext';
import api from '../../services/api';

const WEB_TRANSITION = Platform.OS === 'web' ? ({ transition: 'all 0.2s ease' } as any) : {};

export default function TravelVisaMedia({ userId, plan }: { userId: string; plan: string }) {
  const { colors, darkMode } = useTheme();
  const { t } = useLanguage();
  const tx = React.useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);
  const { width } = useWindowDimensions();
  const isMobile = width < 768;
  const [lessons, setLessons] = useState<any[]>([]);
  const [continueList, setContinueList] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [mediaType, setMediaType] = useState<'video' | 'audio'>('video');
  const [activeLesson, setActiveLesson] = useState<any>(null);
  const [playing, setPlaying] = useState(false);
  const [progress, setProgress] = useState(0);
  const [pageError, setPageError] = useState('');
  const [actionError, setActionError] = useState('');

  const loadData = useCallback(async () => {
    setLoading(true);
    setPageError('');
    try {
      const [lessonsRes, continueRes] = await Promise.all([
        api.get(`/travel-visa/media/lessons?media_type=${mediaType}${userId ? `&user_id=${userId}` : ''}`),
        userId ? api.get(`/travel-visa/media/continue/${userId}`).catch(() => ({ data: { lessons: [] } })) : Promise.resolve({ data: { lessons: [] } }),
      ]);
      setLessons(lessonsRes.data?.lessons || []);
      setContinueList(continueRes.data?.lessons || []);
    } catch (e: any) {
      setPageError(e?.response?.data?.detail || tx('travelVisa.media.errors.loadFailed', 'Media library is unavailable right now.'));
      setLessons([]);
      setContinueList([]);
    }
    setLoading(false);
  }, [mediaType, userId]);

  useEffect(() => { loadData(); }, [loadData]);

  const updateProgress = useCallback(async (lessonId: string, pct: number) => {
    if (!userId) return;
    setActionError('');
    try {
      await api.post('/travel-visa/media/progress', {
        user_id: userId, lesson_id: lessonId, progress_pct: pct, current_time: pct * 0.6,
      });
    } catch (e: any) {
      setActionError(e?.response?.data?.detail || tx('travelVisa.media.errors.progressSyncFailed', 'Progress sync failed.'));
    }
  }, [userId]);

  if (activeLesson) {
    const isVideo = activeLesson.type === 'video';
    return (
      <View data-testid="tv-media-player" style={{ borderRadius: 16, backgroundColor: colors.card, borderWidth: 1, borderColor: colors.border, overflow: 'hidden' }}>
        {/* Player Header */}
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, padding: 14, borderBottomWidth: 1, borderBottomColor: colors.border }}>
          <TouchableOpacity accessibilityLabel="activeLesson.title" onPress={() => setActiveLesson(null)}>
            <Ionicons name="arrow-back" size={20} color={colors.text} />
          </TouchableOpacity>
          <View style={{ flex: 1 }}>
            <Text style={{ fontSize: 14, fontWeight: '600', color: colors.text }} numberOfLines={1}>{activeLesson.title}</Text>
            <Text style={{ fontSize: 11, color: colors.textMuted }}>{activeLesson.type} | {activeLesson.duration_min} min | {activeLesson.difficulty}</Text>
          </View>
        </View>

        {/* Player Area */}
        <View style={{
          height: isVideo ? (isMobile ? 200 : 320) : 160,
          backgroundColor: isVideo ? colors.text : darkMode ? colors.surface : colors.primarySoft,
          alignItems: 'center', justifyContent: 'center',
        }}>
          {isVideo ? (
            <View style={{ alignItems: 'center' }}>
              <View style={{
                width: 64, height: 64, borderRadius: 32, backgroundColor: 'rgba(255,255,255,0.2)',
                alignItems: 'center', justifyContent: 'center',
              }}>
                <Ionicons name={playing ? 'pause' : 'play'} size={28} color={colors.primaryText} />
              </View>
              <Text style={{ color: colors.primaryText, fontSize: 12, marginTop: 8, opacity: 0.7 }}>
                {activeLesson.media_url ? tx('travelVisa.media.player.videoPlayer', 'Video Player') : tx('travelVisa.media.player.videoLoading', 'Video content loading...')}
              </Text>
            </View>
          ) : (
            <View style={{ alignItems: 'center' }}>
              <View style={{
                width: 80, height: 80, borderRadius: 40, backgroundColor: (globalThis as any).__alphaColor(colors.primary, '20'),
                alignItems: 'center', justifyContent: 'center', borderWidth: 3, borderColor: colors.primary,
              }}>
                <Ionicons name={playing ? 'pause' : 'play'} size={32} color={colors.primary} />
              </View>
              <Text style={{ color: colors.text, fontSize: 12, marginTop: 8, fontWeight: '600' }}>{tx('travelVisa.media.player.audioLesson', 'Audio Lesson')}</Text>
            </View>
          )}
        </View>

        {/* Playback Controls */}
        <View style={{ padding: 16 }}>
          {/* Progress Bar */}
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 12 }}>
            <Text style={{ fontSize: 10, color: colors.textMuted }}>{Math.round(progress * activeLesson.duration_min / 100)}m</Text>
            <View style={{ flex: 1, height: 6, borderRadius: 3, backgroundColor: colors.surfaceHover }}>
              <View style={{ height: 6, borderRadius: 3, backgroundColor: colors.primary, width: `${progress}%` as any, ...WEB_TRANSITION }} />
            </View>
            <Text style={{ fontSize: 10, color: colors.textMuted }}>{activeLesson.duration_min}m</Text>
          </View>

          {/* Control Buttons */}
          <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 16 }}>
            <TouchableOpacity onPress={() => setProgress(p => Math.max(0, p - 10))}
              style={{ width: 40, height: 40, borderRadius: 20, backgroundColor: colors.surfaceHover, alignItems: 'center', justifyContent: 'center' }}>
              <Ionicons name="play-back" size={18} color={colors.text} />
            </TouchableOpacity>
            <TouchableOpacity data-testid="tv-media-play-btn"
              onPress={() => {
                setPlaying(!playing);
                if (!playing) {
                  const interval = setInterval(() => {
                    setProgress(p => {
                      if (p >= 100) { clearInterval(interval); setPlaying(false); updateProgress(activeLesson.lesson_id, 100); return 100; }
                      const next = p + 2;
                      if (next % 20 === 0) updateProgress(activeLesson.lesson_id, next);
                      return next;
                    });
                  }, 600);
                }
              }}
              style={{
                width: 56, height: 56, borderRadius: 28, backgroundColor: colors.primary,
                alignItems: 'center', justifyContent: 'center',
                ...(Platform.OS === 'web' ? { boxShadow: `0 4px 12px ${colors.primary}40` } as any : {}),
              }}>
              <Ionicons name={playing ? 'pause' : 'play'} size={24} color={colors.primaryText} />
            </TouchableOpacity>
            <TouchableOpacity accessibilityLabel="play forward button" onPress={() => { const next = Math.min(100, progress + 10); setProgress(next); updateProgress(activeLesson.lesson_id, next); }}
              style={{ width: 40, height: 40, borderRadius: 20, backgroundColor: colors.surfaceHover, alignItems: 'center', justifyContent: 'center' }}>
              <Ionicons name="play-forward" size={18} color={colors.text} />
            </TouchableOpacity>
          </View>

          {/* Speed & Features */}
          <View style={{ flexDirection: 'row', justifyContent: 'center', gap: 12, marginTop: 14 }}>
            {['0.5x', '1x', '1.5x', '2x'].map(speed => (
              <TouchableOpacity key={speed} accessibilityLabel="speed"
                style={{ paddingHorizontal: 12, paddingVertical: 5, borderRadius: 8, backgroundColor: speed === '1x' ? colors.primarySoft : colors.surfaceHover }}>
                <Text style={{ fontSize: 11, fontWeight: '600', color: speed === '1x' ? colors.primary : colors.textMuted }}>{speed}</Text>
              </TouchableOpacity>
            ))}
          </View>

          {/* Content Info */}
          {activeLesson.content && (
            <View style={{ marginTop: 16, padding: 12, borderRadius: 10, backgroundColor: colors.surfaceHover }}>
              <Text style={{ fontSize: 12, fontWeight: '600', color: colors.text, marginBottom: 4 }}>{tx('travelVisa.media.player.aboutLesson', 'About this lesson')}</Text>
              <Text style={{ fontSize: 12, color: colors.textMuted, lineHeight: 18 }}>{activeLesson.content}</Text>
            </View>
          )}
          {activeLesson.transcript && (
            <View style={{ marginTop: 10, padding: 12, borderRadius: 10, backgroundColor: colors.surfaceHover }}>
              <Text style={{ fontSize: 12, fontWeight: '600', color: colors.text, marginBottom: 4 }}>{tx('travelVisa.media.player.transcript', 'Transcript')}</Text>
              <Text style={{ fontSize: 11, color: colors.textMuted, lineHeight: 16 }}>{activeLesson.transcript}</Text>
            </View>
          )}
        </View>
      </View>
    );
  }

  return (
    <View data-testid="tv-media-library">
      <Text style={{ fontSize: 16, fontWeight: '700', color: colors.text, marginBottom: 12 }}>{tx('travelVisa.media.header.title', 'Video & Audio Library')}</Text>

      {!!pageError && (
        <View data-testid="tv-media-load-error" style={{ borderRadius: 10, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(colors.error, '55'), backgroundColor: colors.errorSoft, padding: 10, marginBottom: 12 }}>
          <Text style={{ fontSize: 11, color: colors.errorText, fontWeight: '700', marginBottom: 8 }}>{pageError}</Text>
          <TouchableOpacity data-testid="tv-media-retry-load-btn" onPress={() => void loadData()} style={{ alignSelf: 'flex-start', borderRadius: 8, backgroundColor: colors.error, paddingHorizontal: 10, paddingVertical: 6 }}>
            <Text style={{ fontSize: 11, color: colors.errorTextInverse || colors.primaryText, fontWeight: '800' }}>{tx('common.retry', 'Retry')}</Text>
          </TouchableOpacity>
        </View>
      )}
      {!!actionError && (
        <View data-testid="tv-media-action-error" style={{ borderRadius: 10, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(colors.warning, '55'), backgroundColor: colors.warningSoft, padding: 10, marginBottom: 12 }}>
          <Text style={{ fontSize: 11, color: colors.warningText, fontWeight: '700' }}>{actionError}</Text>
        </View>
      )}

      {/* Type Toggle */}
      <View style={{ flexDirection: 'row', gap: 6, marginBottom: 14 }}>
        {([['video', 'videocam-outline', tx('travelVisa.media.tabs.videos', 'Videos')], ['audio', 'headset-outline', tx('travelVisa.media.tabs.audio', 'Audio')]] as const).map(([type, icon, label]) => (
          <TouchableOpacity key={type} data-testid={`tv-media-type-${type}`}
            onPress={() => setMediaType(type as any)}
            style={{
              flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6,
              paddingVertical: 10, borderRadius: 10,
              backgroundColor: mediaType === type ? colors.primary : colors.surfaceHover,
              borderWidth: 1, borderColor: mediaType === type ? colors.primary : colors.border, ...WEB_TRANSITION,
            }}>
            <Ionicons name={icon as any} size={16} color={mediaType === type ? colors.primaryText : colors.text} />
            <Text style={{ fontSize: 13, fontWeight: '600', color: mediaType === type ? colors.primaryText : colors.text }}>{label}</Text>
          </TouchableOpacity>
        ))}
      </View>

      {/* Continue Watching */}
      {continueList.length > 0 && (
        <View style={{ marginBottom: 16 }}>
          <Text style={{ fontSize: 14, fontWeight: '600', color: colors.text, marginBottom: 8 }}>{tx('travelVisa.media.sections.continueWatching', 'Continue Watching')}</Text>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 10 }}>
            {continueList.map((les, i) => (
              <TouchableOpacity key={les.lesson_id || i} accessibilityLabel="Set active lesson in travel visa media button" onPress={() => { setActiveLesson(les); setProgress(les.user_progress || 0); }}
                style={{
                  width: 200, padding: 12, borderRadius: 12, backgroundColor: colors.card, borderWidth: 1, borderColor: colors.border,
                }}>
                <View style={{
                  height: 80, borderRadius: 8, backgroundColor: les.type === 'video' ? colors.text : colors.primarySoft,
                  alignItems: 'center', justifyContent: 'center', marginBottom: 8,
                }}>
                  <Ionicons name={les.type === 'video' ? 'play-circle' : 'headset'} size={28} color={les.type === 'video' ? colors.primaryText : colors.primary} />
                </View>
                <Text style={{ fontSize: 12, fontWeight: '600', color: colors.text }} numberOfLines={2}>{les.title}</Text>
                <View style={{ height: 3, borderRadius: 2, backgroundColor: colors.surfaceHover, marginTop: 6 }}>
                  <View style={{ height: 3, borderRadius: 2, backgroundColor: colors.primary, width: `${les.user_progress || 0}%` as any }} />
                </View>
              </TouchableOpacity>
            ))}
          </ScrollView>
        </View>
      )}

      {loading ? (
        <ActivityIndicator size="large" color={colors.primary} style={{ padding: 40 }} />
      ) : lessons.length === 0 ? (
        <View style={{ padding: 30, alignItems: 'center', borderRadius: 16, backgroundColor: colors.card, borderWidth: 1, borderColor: colors.border }}>
          <Ionicons name={mediaType === 'video' ? 'videocam-off-outline' : 'headset-outline'} size={48} color={colors.textMuted} />
          <Text style={{ fontSize: 14, color: colors.textMuted, marginTop: 10 }}>{tx('travelVisa.media.states.noneAvailable', `No ${mediaType} lessons available`)}</Text>
        </View>
      ) : (
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10 }}>
          {lessons.slice(0, 20).map((les, i) => (
            <TouchableOpacity data-testid={`tv-media-card-${i}`} key={les.lesson_id || i}
              onPress={() => { setActiveLesson(les); setProgress(les.user_progress || 0); }}
              style={{
                width: isMobile ? '100%' : 'calc(50% - 5px)' as any, minWidth: isMobile ? undefined : 280,
                padding: 12, borderRadius: 12, backgroundColor: colors.card, borderWidth: 1, borderColor: colors.border,
                flexDirection: 'row', alignItems: 'center', gap: 12, ...WEB_TRANSITION,
              }}>
              <View style={{
                width: 56, height: 56, borderRadius: 10,
                backgroundColor: les.type === 'video' ? colors.primary : colors.primarySoft,
                alignItems: 'center', justifyContent: 'center',
              }}>
                <Ionicons name={les.type === 'video' ? 'play-circle' : 'headset'} size={24} color={les.type === 'video' ? colors.primaryText : colors.primary} />
              </View>
              <View style={{ flex: 1 }}>
                <Text style={{ fontSize: 13, fontWeight: '600', color: colors.text }} numberOfLines={2}>{les.title}</Text>
                <Text style={{ fontSize: 11, color: colors.textMuted, marginTop: 2 }}>
                  {les.duration_min} {tx('travelVisa.media.labels.minutes', 'min')} | {les.difficulty} | {les.xp} XP
                </Text>
                {(les.user_progress || 0) > 0 && (
                  <View style={{ height: 3, borderRadius: 2, backgroundColor: colors.surfaceHover, marginTop: 4 }}>
                    <View style={{ height: 3, borderRadius: 2, backgroundColor: les.user_completed ? colors.success : colors.primary, width: `${les.user_progress}%` as any }} />
                  </View>
                )}
              </View>
              {les.user_completed && <Ionicons name="checkmark-circle" size={18} color={colors.success} />}
            </TouchableOpacity>
          ))}
        </View>
      )}
    </View>
  );
}
