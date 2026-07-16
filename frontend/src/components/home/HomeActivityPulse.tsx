import React, { useEffect, useMemo, useState } from 'react';
import { View, Text, Platform, useWindowDimensions, TouchableOpacity } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { useTheme } from '../../context/ThemeContext';
import { useTranslation } from '../../hooks/useTranslation';
import { useLiveQuery } from '../../hooks/useLiveQuery';
import { BODY_FONT_FAMILY, DISPLAY_FONT_FAMILY } from '../../constants/appTypography';

const PULSE_CSS = `
@keyframes pulse-item-in {
  from { opacity: 0; transform: translateY(14px); }
  to { opacity: 1; transform: translateY(0); }
}
@keyframes pulse-dot-beat {
  0%, 100% { transform: scale(1); opacity: 1; }
  50% { transform: scale(1.6); opacity: 0.55; }
}
.home-pulse-item {
  animation: pulse-item-in 0.45s ease both;
  transition: transform 0.2s ease, border-color 0.2s ease, box-shadow 0.2s ease;
  cursor: pointer;
}
.home-pulse-item:hover {
  transform: translateX(4px);
}
@keyframes pulse-skeleton-fade {
  0%, 100% { opacity: 0.35; }
  50% { opacity: 0.7; }
}
.home-pulse-dot {
  animation: pulse-dot-beat 2s ease-in-out infinite;
}
`;

const FILTERS = ['all', 'milestones', 'coaching', 'learning', 'system'] as const;
type FilterKey = typeof FILTERS[number];

type PulseItem = {
  type: string;
  title: string;
  message: string;
  time: string;
  category?: string;
  icon?: string;
  route?: string;
};

export default function HomeActivityPulse({ responsiveWidth }: { responsiveWidth?: number }) {
  const { width: windowWidth } = useWindowDimensions();
  const width = responsiveWidth || windowWidth;
  const isDesktop = width >= 768;
  const isWide = width >= 1200;
  const { colors, darkMode, languageCode } = useTheme();
  const { t, tx } = useTranslation();
  const router = useRouter();
  const [filter, setFilter] = useState<FilterKey>('all');

  const langParam = languageCode && languageCode !== 'en' ? `?lang=${languageCode}` : '';
  const { data: feedRawData } = useLiveQuery(`/home/activity-feed${langParam}`, { entity: 'home_activity', pollInterval: 30000, deps: [languageCode] });
  const feed: PulseItem[] = useMemo(() => feedRawData?.feed || [], [feedRawData]);
  const feedLoaded = !!feedRawData;

  useEffect(() => {
    if (Platform.OS === 'web') {
      const id = 'home-pulse-css';
      if (!document.getElementById(id)) {
        const s = document.createElement('style');
        s.id = id;
        s.textContent = PULSE_CSS;
        document.head.appendChild(s);
      }
    }
  }, []);

  const categoryMeta: Record<string, { color: string; icon: string; label: string }> = {
    milestones: { color: colors.warningText, icon: 'trophy', label: tx('home.pulse.filter.milestones', 'Milestones') },
    coaching: { color: colors.successText, icon: 'sparkles', label: tx('home.pulse.filter.coaching', 'Coaching') },
    learning: { color: colors.primary, icon: 'school', label: tx('home.pulse.filter.learning', 'Learning') },
    system: { color: colors.indigoText || colors.purple, icon: 'megaphone', label: tx('home.pulse.filter.system', 'Platform') },
  };

  const filtered = useMemo(
    () => (filter === 'all' ? feed : feed.filter((item) => (item.category || 'system') === filter)).slice(0, 6),
    [feed, filter],
  );

  const todayCount = useMemo(() => {
    const dayStart = new Date();
    dayStart.setHours(0, 0, 0, 0);
    return feed.filter((item) => new Date(item.time).getTime() >= dayStart.getTime()).length;
  }, [feed]);

  const relTime = (iso: string): string => {
    const diffMs = Date.now() - new Date(iso).getTime();
    if (!Number.isFinite(diffMs)) return '';
    const minutes = Math.max(1, Math.round(diffMs / 60000));
    try {
      const rtf = new Intl.RelativeTimeFormat(languageCode || 'en', { numeric: 'auto', style: 'short' });
      if (minutes < 60) return rtf.format(-minutes, 'minute');
      const hours = Math.round(minutes / 60);
      if (hours < 24) return rtf.format(-hours, 'hour');
      return rtf.format(-Math.round(hours / 24), 'day');
    } catch {
      return minutes < 60 ? `${minutes}m` : `${Math.round(minutes / 60)}h`;
    }
  };

  const surfaceBorder = darkMode ? 'rgba(255,255,255,0.06)' : colors.border;

  if (Platform.OS !== 'web') {
    return (
      <View data-testid="home-activity-pulse" testID="home-activity-pulse" style={{ paddingHorizontal: 20, paddingBottom: 24, gap: 10 }}>
        <Text style={{ fontSize: 18, fontWeight: '800', color: colors.text }}>{tx('home.pulse.title', 'Activity Pulse')}</Text>
        {filtered.map((item, i) => (
          <TouchableOpacity key={i} onPress={() => item.route && router.push(item.route as any)} style={{ padding: 14, borderRadius: 14, backgroundColor: colors.card, borderWidth: 1, borderColor: colors.border }} data-testid={`pulse-item-${i}`} testID={`pulse-item-${i}`}>
            <Text style={{ color: colors.text, fontSize: 13, fontWeight: '700' }}>{item.title}</Text>
            <Text style={{ color: colors.textMuted, fontSize: 11, marginTop: 4 }}>{item.message}</Text>
          </TouchableOpacity>
        ))}
      </View>
    );
  }

  return (
    <View data-testid="home-activity-pulse" testID="home-activity-pulse" style={{ paddingHorizontal: isDesktop ? 40 : 20, paddingBottom: 32 }}>
      <div style={{
        padding: 22, borderRadius: 18,
        background: colors.card,
        border: `1px solid ${surfaceBorder}`,
        boxShadow: darkMode ? '0 18px 40px rgba(0,0,0,0.26)' : '0 14px 30px rgba(15,23,42,0.08)',
      } as any}>
        {/* Header */}
        <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', justifyContent: 'space-between', gap: 12, marginBottom: 14 } as any}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 } as any}>
              <div className="home-pulse-dot" style={{ width: 8, height: 8, borderRadius: '50%', backgroundColor: colors.success } as any} />
              <span style={{ color: colors.textMuted, fontSize: 10, fontWeight: 800, letterSpacing: 1.8, textTransform: 'uppercase', fontFamily: BODY_FONT_FAMILY } as any} data-testid="home-pulse-kicker">
                {tx('home.pulse.kicker', 'Live pulse')}
              </span>
            </div>
            <div style={{ color: colors.text, fontSize: 18, fontWeight: 800, letterSpacing: -0.5, marginTop: 6, fontFamily: DISPLAY_FONT_FAMILY } as any} data-testid="home-pulse-title">
              {tx('home.pulse.title', 'Activity Pulse')}
            </div>
            <div style={{ color: colors.textMuted, fontSize: 12, marginTop: 4, fontFamily: BODY_FONT_FAMILY } as any}>
              {tx('home.pulse.subtitle', 'Your milestones, coaching moments, and platform highlights — as they happen.')}
            </div>
          </div>
          <div style={{ padding: '6px 12px', borderRadius: 999, backgroundColor: (globalThis as any).__alphaColor(colors.success, '10'), border: `1px solid ${(globalThis as any).__alphaColor(colors.success, '25')}` } as any} data-testid="home-pulse-today-count">
            <span style={{ color: colors.successText, fontSize: 11, fontWeight: 800, fontFamily: BODY_FONT_FAMILY } as any}>
              {todayCount} {tx('home.pulse.today', 'today')}
            </span>
          </div>
        </div>

        {/* Filter chips */}
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 16 } as any} data-testid="home-pulse-filters">
          {FILTERS.map((key) => {
            const activeChip = filter === key;
            const chipLabel = key === 'all' ? tx('home.pulse.filter.all', 'All') : categoryMeta[key]?.label || key;
            return (
              <button
                key={key}
                onClick={() => setFilter(key)}
                data-testid={`home-pulse-filter-${key}`}
                style={{
                  padding: '6px 14px', borderRadius: 999, fontSize: 11, fontWeight: 800, cursor: 'pointer',
                  fontFamily: BODY_FONT_FAMILY, letterSpacing: 0.3,
                  background: activeChip ? colors.primary : (darkMode ? colors.cardMuted : colors.bgSoft),
                  color: activeChip ? (colors.primaryText) : colors.textSec,
                  border: `1px solid ${activeChip ? colors.primary : surfaceBorder}`,
                  transition: 'background-color 0.2s ease, color 0.2s ease, border-color 0.2s ease',
                } as any}
              >
                {chipLabel}
              </button>
            );
          })}
        </div>

        {/* Timeline */}
        {!feedLoaded ? (
          <div style={{ display: 'grid', gridTemplateColumns: isWide ? 'repeat(2, minmax(0, 1fr))' : '1fr', gap: 10 } as any} data-testid="home-pulse-skeleton">
            {[0, 1, 2, 3].map((i) => (
              <div key={i} style={{
                height: 74, borderRadius: 12,
                border: `1px solid ${surfaceBorder}`,
                background: darkMode ? colors.cardMuted : colors.bgSoft,
                opacity: 0.55, animation: 'pulse-skeleton-fade 1.6s ease-in-out infinite', animationDelay: `${i * 0.15}s`,
              } as any} />
            ))}
          </div>
        ) : filtered.length === 0 ? (
          <div style={{ padding: '22px 14px', borderRadius: 12, border: `1px dashed ${surfaceBorder}`, color: colors.textMuted, fontSize: 12, textAlign: 'center', fontFamily: BODY_FONT_FAMILY } as any} data-testid="home-pulse-empty">
            {tx('home.pulse.empty', 'No recent activity for this filter yet — your next milestone will land here.')}
          </div>
        ) : (
          <div style={{ display: 'grid', gridTemplateColumns: isWide ? 'repeat(2, minmax(0, 1fr))' : '1fr', gap: 10 } as any} data-testid="home-pulse-list">
            {filtered.map((item, i) => {
              const cat = categoryMeta[item.category || 'system'] || categoryMeta.system;
              const iconName = (item.icon || cat.icon) as any;
              return (
                <div
                  key={`${item.time}-${i}`}
                  className="home-pulse-item"
                  data-testid={`pulse-item-${i}`}
                  onClick={() => item.route && router.push(item.route as any)}
                  style={{
                    display: 'flex', alignItems: 'flex-start', gap: 12,
                    padding: '12px 14px', borderRadius: 12,
                    background: darkMode ? colors.cardMuted : colors.card,
                    border: `1px solid ${surfaceBorder}`,
                    animationDelay: `${i * 0.07}s`,
                  } as any}
                  onMouseEnter={(e: any) => { e.currentTarget.style.borderColor = (globalThis as any).__alphaColor(cat.color, '55'); }}
                  onMouseLeave={(e: any) => { e.currentTarget.style.borderColor = surfaceBorder; }}
                >
                  <div style={{
                    width: 36, height: 36, borderRadius: 11, flexShrink: 0,
                    backgroundColor: (globalThis as any).__alphaColor(cat.color, '14'),
                    border: `1px solid ${(globalThis as any).__alphaColor(cat.color, '28')}`,
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                  } as any}>
                    <Ionicons name={iconName} size={16} color={cat.color} />
                  </div>
                  <div style={{ flex: 1, minWidth: 0 } as any}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' } as any}>
                      <span style={{ color: colors.text, fontSize: 13, fontWeight: 700, lineHeight: 1.35, overflowWrap: 'anywhere', fontFamily: BODY_FONT_FAMILY } as any}>{item.title}</span>
                      <span style={{ fontSize: 9, fontWeight: 800, letterSpacing: 0.6, textTransform: 'uppercase', color: cat.color, padding: '2px 8px', borderRadius: 999, backgroundColor: (globalThis as any).__alphaColor(cat.color, '12'), fontFamily: BODY_FONT_FAMILY } as any} data-testid={`pulse-item-${i}-category`}>
                        {cat.label}
                      </span>
                    </div>
                    <div style={{ color: colors.textMuted, fontSize: 11, marginTop: 4, lineHeight: 1.45, overflowWrap: 'anywhere', display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden', fontFamily: BODY_FONT_FAMILY } as any}>{item.message}</div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 4, marginTop: 6 } as any}>
                      <Ionicons name="time-outline" size={11} color={colors.textMuted} />
                      <span style={{ color: colors.textMuted, fontSize: 10, fontFamily: BODY_FONT_FAMILY } as any} data-testid={`pulse-item-${i}-time`}>{relTime(item.time)}</span>
                    </div>
                  </div>
                  <Ionicons name="chevron-forward" size={14} color={colors.textMuted} style={{ marginTop: 10 } as any} />
                </div>
              );
            })}
          </div>
        )}
      </div>
    </View>
  );
}
