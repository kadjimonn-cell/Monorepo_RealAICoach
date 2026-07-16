import React from 'react';
import { View, Text, TouchableOpacity, ScrollView, ImageBackground, Platform, Modal } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useTheme } from '../../context/ThemeContext';
import { useTranslation } from '../../hooks/useTranslation';
import api from '../../services/api';
import { BODY_FONT_FAMILY as BF, DISPLAY_FONT_FAMILY as HF } from '../../constants/appTypography';

export const courseCoverUrl = (courseId: string, variant: 'full' | 'plain' = 'full') => {
  const base = String((api as any)?.defaults?.baseURL || '/api');
  const suffix = variant === 'plain' ? '?variant=plain' : '';
  return `${base}/ai-learn/course-cover/${encodeURIComponent(String(courseId || ''))}.jpg${suffix}`;
};

const CINEMA_CSS = `
@keyframes lh-card-in { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
@keyframes lh-confetti-fall { 0% { transform: translateY(-40px) rotate(0deg); opacity: 1; } 100% { transform: translateY(460px) rotate(540deg); opacity: 0; } }
@keyframes lh-pop { 0% { transform: scale(0.4); opacity: 0; } 70% { transform: scale(1.12); } 100% { transform: scale(1); opacity: 1; } }
@keyframes lh-flame { 0%, 100% { transform: scale(1); } 50% { transform: scale(1.18); } }
.lh-cinema-card { animation: lh-card-in 0.4s ease both; transition: transform 0.22s ease, box-shadow 0.22s ease; }
.lh-cinema-card:hover { transform: translateY(-4px) scale(1.02); box-shadow: 0 18px 40px rgba(0,0,0,0.35); }
.lh-celebrate-pop { animation: lh-pop 0.5s cubic-bezier(0.34, 1.56, 0.64, 1) both; }
.lh-flame { animation: lh-flame 1.6s ease-in-out infinite; display: inline-flex; }
`;

const useCinemaCss = () => {
  React.useEffect(() => {
    if (Platform.OS !== 'web') return;
    const id = 'lh-cinema-css';
    if (!document.getElementById(id)) {
      const s = document.createElement('style');
      s.id = id;
      s.textContent = CINEMA_CSS;
      document.head.appendChild(s);
    }
  }, []);
};

const webClass = (cls: string) => (Platform.OS === 'web' ? ({ className: cls } as any) : {});

/* ── Momentum Strip (addiction layer) ── */
export const MomentumStrip = ({ streakDays, weeklyMinutes, missions, multiplier, insuranceTokens, onOpenJourney }: {
  streakDays: number; weeklyMinutes: number; missions: any[]; multiplier: string; insuranceTokens: number; onOpenJourney: () => void;
}) => {
  const { colors, darkMode } = useTheme();
  const { tx } = useTranslation();
  useCinemaCss();
  const missionsDone = (missions || []).filter((m: any) => m?.completed).length;
  const missionsTotal = (missions || []).length;
  const goal = 90;
  const minutesPct = Math.min(100, (Number(weeklyMinutes) / goal) * 100);
  const tiles = [
    { key: 'streak', icon: 'flame', color: colors.warning, value: `${streakDays}`, label: tx('learningHub.cinema.momentum.streak', 'Day streak'), sub: `x${multiplier} ${tx('learningHub.cinema.momentum.multiplier', 'XP boost')}`, flame: true },
    { key: 'missions', icon: 'checkmark-done-outline', color: colors.success, value: `${missionsDone}/${missionsTotal || 4}`, label: tx('learningHub.cinema.momentum.missions', 'Missions today'), sub: missionsDone >= missionsTotal && missionsTotal > 0 ? tx('learningHub.cinema.momentum.missionsDone', 'All done — streak safe!') : tx('learningHub.cinema.momentum.missionsHint', 'Finish to protect your streak'), pct: missionsTotal > 0 ? (missionsDone / missionsTotal) * 100 : 0 },
    { key: 'minutes', icon: 'time-outline', color: colors.primary, value: `${Math.round(Number(weeklyMinutes) || 0)}`, label: tx('learningHub.cinema.momentum.minutes', 'Minutes this week'), sub: `${tx('learningHub.cinema.momentum.goal', 'Goal')} ${goal}m`, pct: minutesPct },
    { key: 'insurance', icon: 'shield-checkmark-outline', color: colors.accent, value: `${insuranceTokens}`, label: tx('learningHub.cinema.momentum.insurance', 'Streak shields'), sub: tx('learningHub.cinema.momentum.insuranceHint', 'Auto-saves a missed day') },
  ];
  return (
    <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10, marginBottom: 20 }} data-testid="ai-learning-hub-momentum-strip" testID="ai-learning-hub-momentum-strip">
      {tiles.map((tile) => (
        <TouchableOpacity
          key={tile.key}
          onPress={onOpenJourney}
          style={{ flexGrow: 1, flexBasis: 160, minWidth: 150, backgroundColor: colors.card, borderRadius: 12, borderWidth: 1, borderColor: `${tile.color}44`, padding: 12 }}
          data-testid={`ai-learning-hub-momentum-${tile.key}`} testID={`ai-learning-hub-momentum-${tile.key}`}
        >
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
            {tile.flame && Platform.OS === 'web' ? (
              <span {...webClass('lh-flame')}><Ionicons name={tile.icon as any} size={20} color={tile.color} /></span>
            ) : (
              <Ionicons name={tile.icon as any} size={20} color={tile.color} />
            )}
            <Text style={{ color: colors.text, fontSize: 20, fontWeight: '900', fontFamily: HF }}>{tile.value}</Text>
          </View>
          <Text style={{ color: colors.textSec, fontSize: 11, fontWeight: '800', textTransform: 'uppercase', letterSpacing: 0.6, fontFamily: BF, marginTop: 4 }}>{tile.label}</Text>
          <Text style={{ color: colors.textMuted, fontSize: 10, fontFamily: BF, marginTop: 2 }} numberOfLines={1}>{tile.sub}</Text>
          {typeof tile.pct === 'number' && (
            <View style={{ height: 4, backgroundColor: darkMode ? 'rgba(255,255,255,0.08)' : 'rgba(15,23,42,0.08)', borderRadius: 99, overflow: 'hidden', marginTop: 8 }}>
              <View style={{ height: '100%', width: `${Math.max(0, Math.min(100, tile.pct))}%`, backgroundColor: tile.color, borderRadius: 99 }} />
            </View>
          )}
        </TouchableOpacity>
      ))}
    </View>
  );
};

/* ── Cover card (unique image per course) ── */
export const CourseCoverCard = ({ course, enrolled, progressPct, busy, onEnroll, onOpen, width }: {
  course: any; enrolled: boolean; progressPct?: number; busy?: boolean; onEnroll: () => void; onOpen: () => void; width: number;
}) => {
  const { colors } = useTheme();
  const { tx } = useTranslation();
  const id = String(course?.course_id || '');
  const pct = Math.max(0, Math.min(100, Number(progressPct ?? course?.progress_pct ?? 0)));
  return (
    <View
      style={{ width, backgroundColor: colors.card, borderRadius: 14, borderWidth: 1, borderColor: colors.border, overflow: 'hidden' }}
      {...webClass('lh-cinema-card')}
      data-testid={`ai-learning-hub-course-card-${id}`} testID={`ai-learning-hub-course-card-${id}`}
    >
      <TouchableOpacity onPress={enrolled ? onOpen : onEnroll} activeOpacity={0.85} accessibilityLabel={String(course?.title || 'Course')}>
        <ImageBackground source={{ uri: courseCoverUrl(id, 'plain') }} style={{ width: '100%', height: 150, justifyContent: 'flex-end' }} resizeMode="cover">
          <View style={{ backgroundColor: 'rgba(4,8,16,0.55)', paddingHorizontal: 12, paddingVertical: 10 }}>
            <View style={{ flexDirection: 'row', gap: 6, marginBottom: 4 }}>
              <Text style={{ color: '#7dd3fc' /* @theme-ok fixed-dark-canvas */, fontSize: 9, fontWeight: '900', letterSpacing: 1, textTransform: 'uppercase', fontFamily: BF }}>{course?.category || 'General'}</Text>
              <Text style={{ color: 'rgba(226,232,240,0.75)', fontSize: 9, fontWeight: '700', textTransform: 'uppercase', fontFamily: BF }}>· {course?.difficulty || 'intermediate'}</Text>
            </View>
            <Text style={{ color: '#f8fafc' /* @theme-ok fixed-dark-canvas */, fontSize: 14, fontWeight: '900', fontFamily: HF, lineHeight: 18 }} numberOfLines={2}>{course?.title || 'Course'}</Text>
          </View>
          {enrolled && pct > 0 && (
            <View style={{ height: 4, backgroundColor: 'rgba(255,255,255,0.18)' }}>
              <View style={{ height: '100%', width: `${pct}%`, backgroundColor: colors.success }} />
            </View>
          )}
        </ImageBackground>
      </TouchableOpacity>
      <View style={{ padding: 12, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4, flex: 1 }}>
          <Ionicons name="layers-outline" size={12} color={colors.textMuted} />
          <Text style={{ color: colors.textMuted, fontSize: 11, fontFamily: BF }} numberOfLines={1}>
            {course?.module_count || course?.modules?.length || 5} {tx('learningHub.discover.modules', 'modules')}
          </Text>
        </View>
        {enrolled ? (
          <TouchableOpacity onPress={onOpen} style={{ flexDirection: 'row', alignItems: 'center', gap: 5, borderWidth: 1, borderColor: colors.success, borderRadius: 999, paddingHorizontal: 12, paddingVertical: 6 }} data-testid={`ai-learning-hub-enrolled-${id}`} testID={`ai-learning-hub-enrolled-${id}`}>
            <Ionicons name="play" size={11} color={colors.success} />
            <Text style={{ color: colors.success, fontSize: 11, fontWeight: '800', fontFamily: BF }}>{tx('learningHub.cinema.resume', 'Resume')}</Text>
          </TouchableOpacity>
        ) : (
          <TouchableOpacity onPress={onEnroll} disabled={busy} style={{ flexDirection: 'row', alignItems: 'center', gap: 5, backgroundColor: colors.primary, borderRadius: 999, paddingHorizontal: 12, paddingVertical: 6, opacity: busy ? 0.6 : 1 }} data-testid={`ai-learning-hub-enroll-${id}`} testID={`ai-learning-hub-enroll-${id}`}>
            <Ionicons name="add" size={12} color={colors.primaryText || '#fff'} />
            <Text style={{ color: colors.primaryText || '#fff', fontSize: 11, fontWeight: '800', fontFamily: BF }}>{busy ? '...' : tx('learningHub.discover.enrollNow', 'Enroll Now')}</Text>
          </TouchableOpacity>
        )}
      </View>
    </View>
  );
};

/* ── Horizontal rail ── */
export const CinemaRail = ({ title, icon, courses, enrolledIds, busyId, onEnroll, onOpen, isMobile, railId }: {
  title: string; icon: string; courses: any[]; enrolledIds: Set<string>; busyId: string; onEnroll: (id: string) => void; onOpen: () => void; isMobile: boolean; railId: string;
}) => {
  const { colors } = useTheme();
  useCinemaCss();
  if (!courses.length) return null;
  const cardWidth = isMobile ? 230 : 268;
  return (
    <View style={{ marginBottom: 4 }} data-testid={`ai-learning-hub-rail-${railId}`} testID={`ai-learning-hub-rail-${railId}`}>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 10 }}>
        <Ionicons name={icon as any} size={16} color={colors.primary} />
        <Text style={{ color: colors.text, fontSize: 16, fontWeight: '900', fontFamily: HF }}>{title}</Text>
        <Text style={{ color: colors.textMuted, fontSize: 11, fontFamily: BF }}>({courses.length})</Text>
      </View>
      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 14, paddingBottom: 6, paddingRight: 8 }}>
        {courses.map((course: any) => {
          const id = String(course?.course_id || '');
          return (
            <CourseCoverCard
              key={id}
              course={course}
              enrolled={enrolledIds.has(id)}
              busy={busyId === `enroll-${id}`}
              onEnroll={() => onEnroll(id)}
              onOpen={onOpen}
              width={cardWidth}
            />
          );
        })}
      </ScrollView>
    </View>
  );
};

/* ── Featured hero spotlight ── */
export const CinemaHero = ({ course, enrolled, busy, onEnroll, onResume, isMobile }: {
  course: any; enrolled: boolean; busy: boolean; onEnroll: () => void; onResume: () => void; isMobile: boolean;
}) => {
  const { colors } = useTheme();
  const { tx } = useTranslation();
  useCinemaCss();
  if (!course) return null;
  const id = String(course.course_id || '');
  return (
    <View style={{ borderRadius: 18, overflow: 'hidden', borderWidth: 1, borderColor: colors.border }} data-testid="ai-learning-hub-cinema-hero" testID="ai-learning-hub-cinema-hero">
      <ImageBackground source={{ uri: courseCoverUrl(id, 'plain') }} style={{ width: '100%', minHeight: isMobile ? 240 : 300, justifyContent: 'flex-end' }} resizeMode="cover">
        <View style={{ backgroundColor: 'rgba(3,7,14,0.62)', padding: isMobile ? 16 : 26 }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 8 }}>
            <View style={{ backgroundColor: 'rgba(125,211,252,0.16)', borderWidth: 1, borderColor: 'rgba(125,211,252,0.45)', borderRadius: 999, paddingHorizontal: 10, paddingVertical: 3 }}>
              <Text style={{ color: '#7dd3fc' /* @theme-ok fixed-dark-canvas */, fontSize: 10, fontWeight: '900', letterSpacing: 1.4, textTransform: 'uppercase', fontFamily: BF }}>{tx('learningHub.cinema.featured', 'Featured course')}</Text>
            </View>
            <Text style={{ color: 'rgba(226,232,240,0.8)', fontSize: 11, fontWeight: '700', textTransform: 'uppercase', fontFamily: BF }}>{course.category || 'General'} · {course.difficulty || 'intermediate'}</Text>
          </View>
          <Text style={{ color: '#f8fafc' /* @theme-ok fixed-dark-canvas */, fontSize: isMobile ? 20 : 28, fontWeight: '900', fontFamily: HF, letterSpacing: -0.6 }} numberOfLines={2} data-testid="ai-learning-hub-cinema-hero-title" testID="ai-learning-hub-cinema-hero-title">{course.title}</Text>
          <Text style={{ color: 'rgba(226,232,240,0.78)', fontSize: 12, fontFamily: BF, marginTop: 6, paddingRight: isMobile ? 0 : 120 }} numberOfLines={2}>
            {course.overview || course.description || tx('learningHub.discover.courseDescriptionFallback', 'Practical, project-driven learning path.')}
          </Text>
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', gap: 10, marginTop: 14 }}>
            {enrolled ? (
              <TouchableOpacity onPress={onResume} style={{ flexDirection: 'row', alignItems: 'center', gap: 8, backgroundColor: colors.success, borderRadius: 999, paddingHorizontal: 22, paddingVertical: 11 }} data-testid="ai-learning-hub-cinema-hero-resume" testID="ai-learning-hub-cinema-hero-resume">
                <Ionicons name="play" size={16} color={colors.primaryText || '#fff'} />
                <Text style={{ color: colors.primaryText || '#fff', fontSize: 13, fontWeight: '900', fontFamily: BF }}>{tx('learningHub.cinema.resume', 'Resume')}</Text>
              </TouchableOpacity>
            ) : (
              <TouchableOpacity onPress={onEnroll} disabled={busy} style={{ flexDirection: 'row', alignItems: 'center', gap: 8, backgroundColor: colors.primary, borderRadius: 999, paddingHorizontal: 22, paddingVertical: 11, opacity: busy ? 0.6 : 1 }} data-testid="ai-learning-hub-cinema-hero-enroll" testID="ai-learning-hub-cinema-hero-enroll">
                <Ionicons name="play" size={16} color={colors.primaryText || '#fff'} />
                <Text style={{ color: colors.primaryText || '#fff', fontSize: 13, fontWeight: '900', fontFamily: BF }}>{busy ? '...' : tx('learningHub.cinema.startCourse', 'Start this course')}</Text>
              </TouchableOpacity>
            )}
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 5 }}>
              <Ionicons name="layers-outline" size={13} color="rgba(226,232,240,0.75)" />
              <Text style={{ color: 'rgba(226,232,240,0.75)', fontSize: 11, fontFamily: BF }}>{course.module_count || course.modules?.length || 5} {tx('learningHub.discover.modules', 'modules')} · {(course.video_lessons || []).length || 5} {tx('learningHub.cinema.videoLessons', 'video lessons')}</Text>
            </View>
          </View>
        </View>
      </ImageBackground>
    </View>
  );
};

/* ── Lesson completion celebration ── */
const CONFETTI_COLORS = ['#38bdf8', '#f59e0b', '#22c55e', '#f472b6', '#a78bfa', '#fb7185'];

export const CelebrationOverlay = ({ payload, onNext, onClose }: {
  payload: { lessonTitle?: string; nextLesson?: any } | null; onNext: () => void; onClose: () => void;
}) => {
  const { colors } = useTheme();
  const { tx } = useTranslation();
  useCinemaCss();
  if (!payload) return null;
  return (
    <Modal visible transparent animationType="fade" onRequestClose={onClose}>
      <View style={{ flex: 1, backgroundColor: 'rgba(2,6,12,0.72)', justifyContent: 'center', alignItems: 'center', padding: 20 }} data-testid="ai-learning-hub-celebration-overlay" testID="ai-learning-hub-celebration-overlay">
        {Platform.OS === 'web' && (
          <div style={{ position: 'absolute', top: 0, left: 0, right: 0, height: 0, pointerEvents: 'none' } as any}>
            {Array.from({ length: 26 }).map((_, i) => (
              <div key={i} style={{
                position: 'absolute', left: `${(i * 37) % 100}%`, top: -20, width: 8, height: 12,
                background: CONFETTI_COLORS[i % CONFETTI_COLORS.length], borderRadius: 2,
                animation: `lh-confetti-fall ${1.6 + (i % 5) * 0.35}s ease-in ${(i % 7) * 0.12}s both`,
              } as any} />
            ))}
          </div>
        )}
        <View style={{ width: '100%', maxWidth: 420, backgroundColor: colors.card, borderRadius: 20, borderWidth: 1, borderColor: colors.border, padding: 28, alignItems: 'center' }} {...webClass('lh-celebrate-pop')}>
          <View style={{ width: 68, height: 68, borderRadius: 34, backgroundColor: `${colors.success}22`, borderWidth: 2, borderColor: colors.success, alignItems: 'center', justifyContent: 'center' }}>
            <Ionicons name="checkmark" size={36} color={colors.success} />
          </View>
          <Text style={{ color: colors.text, fontSize: 20, fontWeight: '900', fontFamily: HF, marginTop: 14 }} data-testid="ai-learning-hub-celebration-title" testID="ai-learning-hub-celebration-title">
            {tx('learningHub.cinema.celebration.title', 'Lesson complete!')}
          </Text>
          <Text style={{ color: colors.textSec, fontSize: 13, fontFamily: BF, marginTop: 6, textAlign: 'center' }} numberOfLines={2}>{payload.lessonTitle || ''}</Text>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginTop: 10 }}>
            <Ionicons name="flash" size={14} color={colors.warning} />
            <Text style={{ color: colors.warning, fontSize: 12, fontWeight: '900', fontFamily: BF }}>{tx('learningHub.cinema.celebration.xp', '+XP earned — streak protected for today')}</Text>
          </View>
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', justifyContent: 'center', gap: 10, marginTop: 20 }}>
            {payload.nextLesson ? (
              <TouchableOpacity onPress={onNext} style={{ flexDirection: 'row', alignItems: 'center', gap: 7, backgroundColor: colors.primary, borderRadius: 999, paddingHorizontal: 20, paddingVertical: 11 }} data-testid="ai-learning-hub-celebration-next" testID="ai-learning-hub-celebration-next">
                <Ionicons name="play-skip-forward" size={14} color={colors.primaryText || '#fff'} />
                <Text style={{ color: colors.primaryText || '#fff', fontSize: 13, fontWeight: '900', fontFamily: BF }}>{tx('learningHub.cinema.celebration.next', 'Next lesson')}</Text>
              </TouchableOpacity>
            ) : null}
            <TouchableOpacity onPress={onClose} style={{ borderWidth: 1, borderColor: colors.border, borderRadius: 999, paddingHorizontal: 20, paddingVertical: 11 }} data-testid="ai-learning-hub-celebration-close" testID="ai-learning-hub-celebration-close">
              <Text style={{ color: colors.text, fontSize: 13, fontWeight: '800', fontFamily: BF }}>{tx('learningHub.cinema.celebration.close', 'Keep going')}</Text>
            </TouchableOpacity>
          </View>
        </View>
      </View>
    </Modal>
  );
};
