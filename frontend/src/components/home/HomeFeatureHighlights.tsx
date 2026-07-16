import React, { useEffect } from 'react';
import { View, Text, Platform, useWindowDimensions, TouchableOpacity } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { useTheme } from '../../context/ThemeContext';
import { useTranslation } from '../../hooks/useTranslation';
import { useGlobalPlatformState } from '../../hooks/useGlobalPlatformState';
import { useAccessControl } from '../../context/AccessControlContext';
import { BODY_FONT_FAMILY, DISPLAY_FONT_FAMILY } from '../../constants/appTypography';

const FEATURES_CSS = `
@keyframes feature-slide-in {
  from { opacity: 0; transform: translateY(20px); }
  to { opacity: 1; transform: translateY(0); }
}
.home-feature-card {
  animation: feature-slide-in 0.5s ease both;
  transition: transform 0.3s cubic-bezier(0.34, 1.56, 0.64, 1), border-color 0.3s ease, box-shadow 0.3s ease;
}
.home-feature-card:hover {
  transform: translateY(-6px) !important;
  box-shadow: 0 12px 32px rgba(0,0,0,0.3) !important;
}
.home-feature-icon {
  transition: transform 0.3s cubic-bezier(0.34, 1.56, 0.64, 1);
}
.home-feature-card:hover .home-feature-icon {
  transform: scale(1.15) rotate(5deg);
}
.home-feature-open {
  transition: gap 0.2s ease, color 0.2s ease;
}
.home-feature-card:hover .home-feature-open {
  gap: 8px;
}
`;

export default function HomeFeatureHighlights({ responsiveWidth }: { responsiveWidth?: number }) {
  const { width: windowWidth } = useWindowDimensions();
  const width = responsiveWidth || windowWidth;
  const isDesktop = width >= 768;
  const isTablet = width >= 768 && width < 1024;
  const isWide = width >= 1200;
  const { colors, darkMode } = useTheme();
  const { t, tx } = useTranslation();
  const { state: gpsState, label } = useGlobalPlatformState();
  const { canAccessRoute } = useAccessControl();
  const router = useRouter();

  useEffect(() => {
    if (Platform.OS === 'web') {
      const id = 'home-features-css';
      const existing = document.getElementById(id);
      if (existing) existing.remove();
      const s = document.createElement('style');
      s.id = id;
      s.textContent = FEATURES_CSS;
      document.head.appendChild(s);
    }
  }, []);

  const resolvedFeatures = (gpsState?.features || [])
    .filter((f) => f.enabled !== false && f.soft_deactivated !== true)
    .slice(0, 6)
    .map((f) => {
      const route = f.route || `/features/${f.feature_id}`;
      const decision = canAccessRoute(route);
      const planTier: 'included' | 'basic' | 'premium' =
        String(f.availability || 'all') === 'premium' || decision?.reason === 'premium_required'
          ? 'premium'
          : decision && decision.allowed === false
            ? 'basic'
            : 'included';
      return {
        id: f.feature_id,
        title: f.title,
        description: f.description || '',
        icon: (f.icon || 'apps') as any,
        color: f.color || colors.primary,
        route,
        category: f.category || 'general',
        planTier,
      };
    });

  const openFeature = (route: string) => router.push(route as any);
  const openPlans = () => router.push('/subscription/plans' as any);

  const PLAN_CHIP_META: Record<string, { icon: any; color: string; text: string; locked: boolean }> = {
    included: { icon: 'checkmark-circle', color: colors.successText, text: tx('home.features.includedBadge', 'Included'), locked: false },
    basic: { icon: 'lock-open', color: colors.primary, text: tx('home.features.basicBadge', 'Basic'), locked: true },
    premium: { icon: 'star', color: colors.warningText, text: tx('home.features.premiumBadge', 'Premium'), locked: true },
  };

  const renderPlanChip = (planTier: string, id: string) => {
    const chip = PLAN_CHIP_META[planTier] || PLAN_CHIP_META.included;
    const inner = (
      <>
        <Ionicons name={chip.icon} size={9} color={chip.color} />
        <Text style={{ color: chip.color, fontSize: 9, fontWeight: '800', letterSpacing: 0.5, textTransform: 'uppercase', fontFamily: BODY_FONT_FAMILY }}>{chip.text}</Text>
      </>
    );
    const chipStyle = {
      flexDirection: 'row' as const, alignItems: 'center' as const, gap: 4, paddingHorizontal: 8, paddingVertical: 3, borderRadius: 999,
      backgroundColor: (globalThis as any).__alphaColor(chip.color, '14'),
      borderWidth: 1, borderColor: (globalThis as any).__alphaColor(chip.color, '30'),
    };
    return chip.locked ? (
      <TouchableOpacity onPress={openPlans} data-testid={`feature-card-plan-${id}`} testID={`feature-card-plan-${id}`} style={chipStyle}>
        {inner}
      </TouchableOpacity>
    ) : (
      <View data-testid={`feature-card-plan-${id}`} testID={`feature-card-plan-${id}`} style={chipStyle}>
        {inner}
      </View>
    );
  };

  return (
    <View data-testid="feature-highlights-section" testID="feature-highlights-section" style={{
      paddingHorizontal: isWide ? 40 : isTablet ? 28 : isDesktop ? 40 : 20,
      paddingTop: 8, paddingBottom: 32,
    }}>
      {/* Section Header */}
      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 10, flexWrap: 'wrap', marginBottom: 8 }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
          <View style={{ width: 3, height: 20, borderRadius: 2, backgroundColor: colors.purple }} />
          <Text style={{ fontSize: 18, fontWeight: '800', color: colors.text, letterSpacing: -0.5, fontFamily: DISPLAY_FONT_FAMILY }}>
            {label('home.features.title', t('home.features.title'))}
          </Text>
        </View>
        <TouchableOpacity onPress={() => router.push('/features' as any)} data-testid="features-view-all" testID="features-view-all"
          style={{ flexDirection: 'row', alignItems: 'center', gap: 5, paddingHorizontal: 12, paddingVertical: 6, borderRadius: 999, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card }}>
          <Text style={{ color: colors.primary, fontSize: 11, fontWeight: '800', fontFamily: BODY_FONT_FAMILY }}>{tx('home.features.viewAll', 'View all features')}</Text>
          <Ionicons name="arrow-forward" size={12} color={colors.primary} />
        </TouchableOpacity>
      </View>
      <Text style={{ fontSize: 14, color: colors.textMuted, marginBottom: 24, lineHeight: 22, fontFamily: BODY_FONT_FAMILY }}>
        {label('home.features.subtitle', t('home.features.subtitle'))}
      </Text>

      {Platform.OS === 'web' ? (
        <div data-testid="feature-cards-grid" style={{
          display: 'grid',
          gridTemplateColumns: isWide ? 'repeat(3, minmax(0, 1fr))' : isDesktop ? 'repeat(2, minmax(0, 1fr))' : 'minmax(0, 1fr)',
          gap: isTablet ? 12 : 14,
        } as any}>
          {resolvedFeatures.map((f, i) => (
            <div key={f.id} className="home-feature-card" data-testid={`feature-card-${f.id}`} role="button" tabIndex={0} onClick={() => openFeature(f.route)} style={{
              padding: 22, borderRadius: 18, cursor: 'pointer',
              display: 'flex', flexDirection: 'column', minWidth: 0,
              background: darkMode ? `linear-gradient(135deg, ${f.color}14 0%, ${f.color}04 100%), ${colors.card}` : colors.card,
              border: `1px solid ${colors.border}`,
              boxShadow: darkMode ? 'none' : '0 12px 30px rgba(15,23,42,0.08)',
              animationDelay: `${i * 0.08}s`,
              position: 'relative', overflow: 'hidden',
            } as any}>
              <div style={{
                position: 'absolute', top: -24, right: -24, width: 90, height: 90, borderRadius: '50%',
                background: `radial-gradient(circle, ${f.color}10 0%, transparent 70%)`,
              } as any} />
              <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 8, marginBottom: 14 } as any}>
                <div className="home-feature-icon" style={{
                  width: 48, height: 48, borderRadius: 14,
                  backgroundColor: (globalThis as any).__alphaColor(f.color, '15'),
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  border: `1px solid ${f.color}25`,
                } as any}>
                  <Ionicons name={f.icon} size={22} color={f.color} />
                </div>
                <div role="button" tabIndex={0} onClick={(e: any) => e.stopPropagation()} style={{ display: 'flex' } as any}>
                  {renderPlanChip(f.planTier, f.id)}
                </div>
              </div>
              <div style={{ color: colors.text, fontSize: 16, fontWeight: 700, marginBottom: 6, letterSpacing: -0.3, fontFamily: DISPLAY_FONT_FAMILY } as any}>{f.title}</div>
              <div style={{ fontSize: 9, fontWeight: 800, letterSpacing: 0.8, textTransform: 'uppercase', color: colors.textMuted, marginBottom: 8, fontFamily: BODY_FONT_FAMILY } as any} data-testid={`feature-card-category-${f.id}`}>{f.category}</div>
              <div style={{ color: colors.textSec || colors.textSecondary, fontSize: 13, lineHeight: '20px', flex: 1, display: '-webkit-box', WebkitLineClamp: 3, WebkitBoxOrient: 'vertical', overflow: 'hidden', fontFamily: BODY_FONT_FAMILY } as any}>{f.description}</div>
              <div className="home-feature-open" data-testid={`feature-card-open-${f.id}`} style={{ display: 'flex', alignItems: 'center', gap: 5, marginTop: 14, color: f.color, fontSize: 12, fontWeight: 800, fontFamily: BODY_FONT_FAMILY } as any}>
                {tx('home.features.open', 'Open')}
                <Ionicons name="arrow-forward" size={13} color={f.color} />
              </div>
            </div>
          ))}
        </div>
      ) : (
        <View style={{ gap: 14 }}>
          {resolvedFeatures.map((f) => (
            <TouchableOpacity key={f.id} data-testid={`feature-card-${f.id}`} testID={`feature-card-${f.id}`} onPress={() => openFeature(f.route)} activeOpacity={0.85} style={{
              padding: 20, borderRadius: 16,
              backgroundColor: colors.card,
              borderWidth: 1, borderColor: colors.border,
            }}>
              <View style={{ flexDirection: 'row', alignItems: 'flex-start', justifyContent: 'space-between', gap: 8, marginBottom: 12 }}>
                <View style={{
                  width: 44, height: 44, borderRadius: 12,
                  backgroundColor: (globalThis as any).__alphaColor(f.color, '15'),
                  alignItems: 'center', justifyContent: 'center',
                  borderWidth: 1, borderColor: (globalThis as any).__alphaColor(f.color, '20'),
                }}>
                  <Ionicons name={f.icon} size={20} color={f.color} />
                </View>
                {renderPlanChip(f.planTier, f.id)}
              </View>
              <Text style={{ color: colors.text, fontSize: 15, fontWeight: '700', marginBottom: 6 }}>{f.title}</Text>
              <Text style={{ color: colors.textSec || colors.textSecondary, fontSize: 13, lineHeight: 20 }} numberOfLines={3}>{f.description}</Text>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 5, marginTop: 12 }}>
                <Text style={{ color: f.color, fontSize: 12, fontWeight: '800' }}>{tx('home.features.open', 'Open')}</Text>
                <Ionicons name="arrow-forward" size={13} color={f.color} />
              </View>
            </TouchableOpacity>
          ))}
        </View>
      )}
    </View>
  );
}
