import React, { useEffect } from 'react';
import { View, Platform, useWindowDimensions } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
// eslint-disable-next-line @typescript-eslint/no-unused-vars
import api from '../../services/api';
import { useTheme } from '../../context/ThemeContext';
import { useLiveQuery } from '../../hooks/useLiveQuery';
import { useTranslation } from '../../hooks/useTranslation';

const BADGE_CSS = `
@keyframes badge-slide-in { from { opacity:0; transform:translateY(16px) scale(.95); } to { opacity:1; transform:translateY(0) scale(1); } }
@keyframes badge-glow { 0%,100% { box-shadow:0 0 12px var(--glow-color,rgba(59,130,246,.15)); } 50% { box-shadow:0 0 24px var(--glow-color,rgba(59,130,246,.25)); } }
@keyframes badge-unlock { 0% { transform:scale(0) rotate(-180deg); } 60% { transform:scale(1.15) rotate(10deg); } 100% { transform:scale(1) rotate(0deg); } }
@keyframes badge-shimmer { 0% { background-position:-200% 0; } 100% { background-position:200% 0; } }
.badge-card { animation: badge-slide-in .5s ease both; transition: transform .25s cubic-bezier(.34,1.56,.64,1), border-color .25s ease; }
.badge-card:hover { transform: translateY(-6px) !important; }
.badge-card-earned:hover { border-color: var(--badge-color,rgba(59,130,246,.4)) !important; }
.badge-icon-earned { animation: badge-glow 3s ease-in-out infinite; }
.badge-progress-bar { transition: width .6s cubic-bezier(.4,0,.2,1); }
`;

const ICON_MAP: Record<string, any> = {
  rocket: 'rocket-outline',
  flash: 'flash-outline',
  flag: 'flag-outline',
  flame: 'flame-outline',
  star: 'star-outline',
  trophy: 'trophy-outline',
};

const ICON_MAP_EARNED: Record<string, any> = {
  rocket: 'rocket',
  flash: 'flash',
  flag: 'flag',
  flame: 'flame',
  star: 'star',
  trophy: 'trophy',
};

interface Badge {
  id: string;
  title: string;
  desc: string;
  icon: string;
  color: string;
  threshold: number;
  progress: number;
  earned: boolean;
  earned_at: string | null;
}

export default function HomeTrophyCase({ responsiveWidth }: { responsiveWidth?: number }) {
  const { width: windowWidth } = useWindowDimensions();
  const width = responsiveWidth || windowWidth;
  const isDesktop = width >= 768;
  const isTablet = width >= 768 && width < 1024;
  const isWide = width >= 1200;
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const { colors, _darkMode } = useTheme();
  const { t } = useTranslation();

  useEffect(() => {
    if (Platform.OS === 'web') {
      const id = 'badge-css';
      if (!document.getElementById(id)) {
        const s = document.createElement('style');
        s.id = id;
        s.textContent = BADGE_CSS;
        document.head.appendChild(s);
      }
    }
  }, []);

  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const { data: badgeData, loading: badgeLoading, refetch: _loadBadges } = useLiveQuery('/home/badges', { entity: 'badges', pollInterval: 30000 });
  const badges = badgeData?.badges || [];
  const totalEarned = badgeData?.total_earned || 0;
  const loading = badgeLoading;

  const nextUpId = React.useMemo(() => {
    let best: string | null = null;
    let bestPct = -1;
    for (const b of badges as Badge[]) {
      if (b.earned) continue;
      const pct = b.threshold > 0 ? b.progress / b.threshold : 0;
      if (pct > bestPct) {
        bestPct = pct;
        best = b.id;
      }
    }
    return best;
  }, [badges]);

  if (loading || Platform.OS !== 'web') return null;

  return (
    <View data-testid="trophy-case-section" testID="trophy-case-section" style={{
      paddingHorizontal: isWide ? 40 : isTablet ? 28 : isDesktop ? 40 : 20,
      paddingTop: 8, paddingBottom: 32,
    }}>
      {/* Section Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 } as any}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 } as any}>
          <div style={{ width: 3, height: 20, borderRadius: 2, backgroundColor: colors.warning } as any} />
          <span style={{
            fontSize: 18, fontWeight: 800, color: colors.text, letterSpacing: -0.5,
            fontFamily: "'Inter', system-ui, sans-serif",
          } as any}>{t('home.trophy.title')}</span>
        </div>
        <div style={{
          display: 'flex', alignItems: 'center', gap: 6,
          padding: '4px 12px', borderRadius: 8,
          background: colors.warningSoft,
          border: `1px solid ${colors.warning}30`,
        } as any}>
          <Ionicons name="trophy" size={13} color={colors.warningText} />
          <span style={{ color: colors.warningText, fontSize: 12, fontWeight: 700 } as any}>{totalEarned}/{badges.length}</span>
        </div>
      </div>
      <div style={{
        color: colors.textMuted, fontSize: 13, lineHeight: '20px', marginBottom: 24,
        fontFamily: "'Inter', system-ui, sans-serif",
      } as any}>
        {t('home.trophy.subtitle')}
      </div>

      {/* Badges Grid */}
      <div data-testid="badges-grid" style={{
        display: 'grid',
        gridTemplateColumns: isWide ? 'repeat(3, 1fr)' : isTablet ? 'repeat(2, 1fr)' : isDesktop ? 'repeat(3, 1fr)' : 'repeat(2, 1fr)',
        gap: 14,
      } as any}>
        {badges.map((b, i) => (
          <BadgeCard key={b.id} badge={b} index={i} isNextUp={b.id === nextUpId} />
        ))}
      </div>
    </View>
  );
}

function BadgeCard({ badge: b, index, isNextUp }: { badge: Badge; index: number; isNextUp?: boolean }) {
  const { colors, darkMode } = useTheme();
  const { t, tx } = useTranslation();
  const pct = b.threshold > 0 ? Math.round((b.progress / b.threshold) * 100) : 0;
  const localizedTitle = tx(`home.trophy.badge.${b.id}.title`, b.title);
  const localizedDesc = tx(`home.trophy.badge.${b.id}.desc`, b.desc);

  return (
    <div
      className={`badge-card ${b.earned ? 'badge-card-earned' : ''}`}
      data-testid={`badge-${b.id}`}
      style={{
        '--badge-color': b.color + '40',
        '--glow-color': b.color + '20',
        padding: 20,
        borderRadius: 18,
        background: b.earned
          ? `linear-gradient(145deg, ${b.color}15 0%, ${colors.card} 100%)`
          : colors.card,
        border: `1px solid ${b.earned ? b.color + '20' : colors.border}`,
        boxShadow: darkMode ? 'none' : '0 12px 28px rgba(15,23,42,0.08)',
        animationDelay: `${index * 0.08}s`,
        position: 'relative',
        overflow: 'hidden',
        cursor: 'default',
      } as any}
    >
      {/* Shimmer effect for locked badges */}
      {!b.earned && pct > 0 && (
        <div style={{
          position: 'absolute', inset: 0,
          background: `linear-gradient(90deg, transparent 0%, ${b.color}05 50%, transparent 100%)`,
          backgroundSize: '200% 100%',
          animation: 'badge-shimmer 3s ease-in-out infinite',
          pointerEvents: 'none',
        } as any} />
      )}

      {/* Badge icon */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14 } as any}>
        <div
          className={b.earned ? 'badge-icon-earned' : ''}
          style={{
            width: 48, height: 48, borderRadius: 14,
            background: b.earned
              ? `linear-gradient(135deg, ${b.color}20 0%, ${b.color}08 100%)`
              : (darkMode ? colors.cardMuted : colors.bgSoft),
            border: `1.5px solid ${b.earned ? b.color + '30' : colors.border}`,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            transition: 'all .3s ease',
            '--glow-color': b.color + '20',
          } as any}
        >
          <Ionicons
            name={(b.earned ? ICON_MAP_EARNED[b.icon] : ICON_MAP[b.icon]) || 'ellipse-outline'}
            size={22}
            color={b.earned ? b.color : b.color}
            style={b.earned ? undefined : ({ opacity: 0.55 } as any)}
          />
        </div>

        {/* Status badge */}
        {b.earned ? (
          <div style={{
            padding: '3px 8px', borderRadius: 6,
            background: `${b.color}15`,
            border: `1px solid ${b.color}20`,
          } as any}>
            <span style={{ color: b.color, fontSize: 10, fontWeight: 700, letterSpacing: 0.3 } as any}>{t('home.trophy.earned')}</span>
          </div>
        ) : isNextUp ? (
          <div data-testid={`badge-${b.id}-next-up`} style={{
            display: 'flex', alignItems: 'center', gap: 4,
            padding: '3px 8px', borderRadius: 6,
            background: `${b.color}15`,
            border: `1px solid ${b.color}30`,
          } as any}>
            <Ionicons name="arrow-up-circle" size={11} color={b.color} />
            <span style={{ color: b.color, fontSize: 10, fontWeight: 800, letterSpacing: 0.3, textTransform: 'uppercase' } as any}>{tx('home.trophy.nextUp', 'Next up')}</span>
          </div>
        ) : (
          <div style={{
            display: 'flex', alignItems: 'center', gap: 4,
            opacity: 0.5,
          } as any}>
            <Ionicons name="lock-closed" size={12} color={colors.textMuted} />
          </div>
        )}
      </div>

      {/* Title & Description */}
      <div style={{
        color: b.earned ? colors.text : colors.textSecondary,
        fontSize: 15, fontWeight: 700, letterSpacing: -0.3, marginBottom: 4,
        fontFamily: "'Inter', system-ui, sans-serif",
      } as any}>{localizedTitle}</div>
      <div style={{
        color: b.earned ? colors.textSecondary : colors.textMuted,
        fontSize: 12, lineHeight: '18px', marginBottom: 12,
        fontFamily: "'Inter', system-ui, sans-serif",
      } as any}>{localizedDesc}</div>

      {/* Progress bar */}
      {!b.earned && (
        <div style={{ marginTop: 'auto' } as any}>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 } as any}>
            <span style={{ color: colors.textMuted, fontSize: 11, fontWeight: 600 } as any}>{b.progress}/{b.threshold}</span>
            <span style={{ color: colors.textMuted, fontSize: 11, fontWeight: 600 } as any}>{pct}%</span>
          </div>
          <div style={{
            height: 4, borderRadius: 2, background: colors.border, overflow: 'hidden',
          } as any}>
            <div className="badge-progress-bar" style={{
              height: '100%', borderRadius: 2,
              background: pct > 0 ? `linear-gradient(90deg, ${b.color}80, ${b.color})` : 'transparent',
              width: `${pct}%`,
            } as any} />
          </div>
        </div>
      )}

      {/* Earned date */}
      {b.earned && b.earned_at && (
        <div style={{ color: colors.textMuted, fontSize: 10, fontWeight: 600, marginTop: 4 } as any}>
          {tx('home.trophy.earnedOn', 'Earned')} {new Date(b.earned_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}
        </div>
      )}
    </div>
  );
}
