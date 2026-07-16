import React, { useEffect, useRef, useState } from 'react';
import { View, Text, Platform, useWindowDimensions } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useTheme } from '../../context/ThemeContext';
import { useTranslation } from '../../hooks/useTranslation';
import { withAlpha } from '../../utils/colorAlpha';
import { FALLBACK_WELCOME_TESTIMONIALS, buildCanonicalWelcomeTestimonials } from '../../content/welcomeTrustContent';
import { useGlobalPlatformState } from '../../hooks/useGlobalPlatformState';

const SOCIAL_CSS = `
@keyframes social-fade-in {
  from { opacity: 0; transform: translateY(16px); }
  to { opacity: 1; transform: translateY(0); }
}
.social-card { animation: social-fade-in 0.6s ease both; }
`;

type TestimonialColorKey = 'primary' | 'success' | 'accent';
type Testimonial = { name: string; role: string; text: string; outcome?: string; avatar: string; colorKey: TestimonialColorKey; rating: number };

const FALLBACK_TRUST_COMPANIES = Array.from(new Set(FALLBACK_WELCOME_TESTIMONIALS.map((t) => String(t.company || '').trim()).filter(Boolean))).slice(0, 8);

export default function HomeSocialProof({ responsiveWidth, trustCompanies }: { responsiveWidth?: number; trustCompanies?: string[] }) {
  const { width: windowWidth } = useWindowDimensions();
  const width = responsiveWidth || windowWidth;
  const isDesktop = width >= 768;
  const isTablet = width >= 768 && width < 1024;
  const isWide = width >= 1200;
  const { colors, darkMode } = useTheme();
  const { t, tx } = useTranslation();
  const { state: gpsState } = useGlobalPlatformState();

  const COLOR_KEYS: TestimonialColorKey[] = ['primary', 'success', 'accent'];
  const TESTIMONIALS: Testimonial[] = React.useMemo(() => {
    const canonical = buildCanonicalWelcomeTestimonials(gpsState?.messaging?.welcome_testimonials || [], 10);
    return canonical.map((entry, i) => ({
      name: entry.name,
      role: [entry.role, entry.company].filter(Boolean).join(', '),
      text: entry.quote,
      outcome: entry.outcome || '',
      avatar: entry.name.split(' ').map((p) => p[0]).join('').slice(0, 2).toUpperCase(),
      colorKey: COLOR_KEYS[i % COLOR_KEYS.length],
      rating: entry.rating || 5,
    }));
  }, [gpsState?.messaging?.welcome_testimonials]);

  const companies = (Array.isArray(trustCompanies) && trustCompanies.length ? trustCompanies : FALLBACK_TRUST_COMPANIES).slice(0, 8);
  const chipStyle = {
    borderRadius: 999,
    borderWidth: 1,
    borderColor: withAlpha(colors.border, 'C8'),
    backgroundColor: withAlpha(colors.bgSoft, darkMode ? 'AB' : 'EF'),
    paddingHorizontal: 12,
    paddingVertical: 8,
    opacity: 0.88,
  } as const;
  const chipTextStyle = {
    color: colors.textMuted,
    fontSize: 11,
    fontWeight: '800',
    letterSpacing: 0.6,
    textTransform: 'uppercase',
  } as const;

  const STATS = [
    { label: t('home.social.countriesServed'), value: tx('home.social.countriesServedValue', '45+'), icon: 'globe-outline' as const, color: colors.primary },
    { label: t('home.social.sessionsDelivered'), value: tx('home.social.sessionsDeliveredValue', '10K+'), icon: 'chatbubbles-outline' as const, color: colors.successText },
    { label: t('home.social.avgImprovement'), value: tx('home.social.avgImprovementValue', '94%'), icon: 'trending-up-outline' as const, color: colors.purpleText },
    { label: t('home.social.enterpriseClients'), value: tx('home.social.enterpriseClientsValue', '200+'), icon: 'business-outline' as const, color: colors.warningText },
  ];
  const [activeTestimonial, setActiveTestimonial] = useState(0);
  const timerRef = useRef<any>(null);

  const goTo = (index: number) => {
    clearInterval(timerRef.current);
    setActiveTestimonial((index + TESTIMONIALS.length) % TESTIMONIALS.length);
    timerRef.current = setInterval(() => setActiveTestimonial((p) => (p + 1) % Math.max(TESTIMONIALS.length, 1)), 8000);
  };

  useEffect(() => {
    if (Platform.OS === 'web') {
      const id = 'home-social-css';
      if (!document.getElementById(id)) {
        const s = document.createElement('style');
        s.id = id;
        s.textContent = SOCIAL_CSS;
        document.head.appendChild(s);
      }
    }
  }, []);

  useEffect(() => {
    timerRef.current = setInterval(() => setActiveTestimonial((p) => (p + 1) % Math.max(TESTIMONIALS.length, 1)), 6000);
    return () => clearInterval(timerRef.current);
  }, [TESTIMONIALS.length]);

  const safeIndex = TESTIMONIALS.length ? activeTestimonial % TESTIMONIALS.length : 0;
  const currentTestimonial = {
    ...(TESTIMONIALS[safeIndex] || TESTIMONIALS[0]),
    color: colors[(TESTIMONIALS[safeIndex] || TESTIMONIALS[0]).colorKey] || colors.primary,
  };
  const cardBg = darkMode ? colors.cardMuted : colors.card;
  const cardBorder = colors.border;
  const cardShadow = darkMode ? '0 4px 16px rgba(0,0,0,0.3)' : '0 12px 30px rgba(15,23,42,0.08)';

  return (
    <View data-testid="social-proof-section" testID="social-proof-section" style={{ paddingHorizontal: isWide ? 40 : isTablet ? 28 : isDesktop ? 40 : 20, paddingTop: 8, paddingBottom: 32 }}>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 8 }}>
        <View style={{ width: 3, height: 20, borderRadius: 2, backgroundColor: colors.warning }} />
        <Text style={{ fontSize: 18, fontWeight: '800', color: colors.text, letterSpacing: -0.5, fontFamily: Platform.OS === 'web' ? "'Inter', system-ui, sans-serif" : undefined }}>
          {t('home.social.title')}
        </Text>
      </View>
      <Text style={{ fontSize: 14, color: colors.textMuted, marginBottom: 28, lineHeight: 22, fontFamily: Platform.OS === 'web' ? "'Inter', system-ui, sans-serif" : undefined }}>
        {t('home.social.subtitle')}
      </Text>

      {Platform.OS === 'web' ? (
        <>
          <div data-testid="impact-stats" className="social-card" style={{ display: 'grid', gridTemplateColumns: isDesktop ? 'repeat(4, 1fr)' : 'repeat(2, 1fr)', gap: 14, marginBottom: 24, animationDelay: '0.1s' } as any}>
            {STATS.map((s) => (
              <div key={s.label} style={{ padding: '20px 16px', borderRadius: 16, textAlign: 'center', background: cardBg, border: `1px solid ${cardBorder}`, boxShadow: cardShadow } as any}>
                <div style={{ display: 'flex', justifyContent: 'center', marginBottom: 10 } as any}><Ionicons name={s.icon} size={22} color={s.color} /></div>
                <div style={{ color: colors.text, fontSize: 24, fontWeight: 800, letterSpacing: -0.5 } as any}>{s.value}</div>
                <div style={{ color: colors.textMuted, fontSize: 11, fontWeight: 600, marginTop: 4, letterSpacing: 0.3 } as any}>{s.label}</div>
              </div>
            ))}
          </div>

          <div data-testid="testimonial-carousel" className="social-card" style={{ padding: 28, borderRadius: 20, background: cardBg, border: `1px solid ${cardBorder}`, marginBottom: 24, animationDelay: '0.2s', position: 'relative', overflow: 'hidden', boxShadow: cardShadow } as any}>
            <div style={{ position: 'absolute', top: 16, right: 24, fontSize: 64, color: currentTestimonial.color + '15', fontFamily: 'Georgia, serif', lineHeight: '1' } as any}>“</div>
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 14, marginBottom: 18 } as any}>
                <div style={{ width: 48, height: 48, borderRadius: 14, backgroundColor: (globalThis as any).__alphaColor(currentTestimonial.color, '18'), display: 'flex', alignItems: 'center', justifyContent: 'center', border: `1px solid ${currentTestimonial.color}25` } as any}>
                  <span style={{ color: currentTestimonial.color, fontWeight: 800, fontSize: 16 } as any}>{currentTestimonial.avatar}</span>
                </div>
                <div>
                  <div style={{ color: colors.text, fontWeight: 700, fontSize: 15 } as any}>{currentTestimonial.name}</div>
                  <div style={{ color: colors.textMuted, fontSize: 12, marginTop: 2 } as any}>{currentTestimonial.role}</div>
                </div>
              </div>
              <div style={{ color: colors.textSec || colors.textSecondary, fontSize: 15, lineHeight: '24px', fontStyle: 'italic' } as any}>
                "{currentTestimonial.text}"
              </div>
              <div style={{ display: 'flex', gap: 3, marginTop: 14, alignItems: 'center', flexWrap: 'wrap' } as any}>
                {Array.from({ length: currentTestimonial.rating }).map((_, i) => <Ionicons key={i} name="star" size={14} color={colors.warningText} />)}
                {currentTestimonial.outcome ? (
                  <span data-testid="testimonial-outcome-chip" style={{ marginLeft: 10, padding: '3px 10px', borderRadius: 999, fontSize: 10, fontWeight: 800, letterSpacing: 0.4, color: currentTestimonial.color, background: (globalThis as any).__alphaColor(currentTestimonial.color, '12'), border: `1px solid ${(globalThis as any).__alphaColor(currentTestimonial.color, '28')}` } as any}>
                    {currentTestimonial.outcome}
                  </span>
                ) : null}
              </div>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12, marginTop: 20, flexWrap: 'wrap' } as any}>
              <div role="button" tabIndex={0} data-testid="testimonial-prev" onClick={() => goTo(safeIndex - 1)} style={{ width: 32, height: 32, borderRadius: 10, display: 'flex', alignItems: 'center', justifyContent: 'center', border: `1px solid ${cardBorder}`, background: darkMode ? colors.cardMuted : colors.bgSoft, cursor: 'pointer' } as any}>
                <Ionicons name="chevron-back" size={15} color={colors.textSec || colors.textSecondary} />
              </div>
              <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', gap: 6, flexWrap: 'wrap', flex: 1 } as any}>
                {TESTIMONIALS.map((_, i) => (
                  <div key={i} data-testid={`testimonial-dot-${i}`} role="button" tabIndex={0} onClick={() => goTo(i)} style={{ width: i === safeIndex ? 20 : 7, height: 7, borderRadius: 4, backgroundColor: i === safeIndex ? currentTestimonial.color : (darkMode ? 'rgba(255,255,255,0.15)' : colors.border), transition: 'all 0.3s ease', cursor: 'pointer' } as any} />
                ))}
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10 } as any}>
                <span data-testid="testimonial-counter" style={{ color: colors.textMuted, fontSize: 11, fontWeight: 800, letterSpacing: 0.6 } as any}>{safeIndex + 1}/{TESTIMONIALS.length}</span>
                <div role="button" tabIndex={0} data-testid="testimonial-next" onClick={() => goTo(safeIndex + 1)} style={{ width: 32, height: 32, borderRadius: 10, display: 'flex', alignItems: 'center', justifyContent: 'center', border: `1px solid ${cardBorder}`, background: darkMode ? colors.cardMuted : colors.bgSoft, cursor: 'pointer' } as any}>
                  <Ionicons name="chevron-forward" size={15} color={colors.textSec || colors.textSecondary} />
                </div>
              </div>
            </div>
          </div>

          <div data-testid="trust-logos" className="social-card" style={{ padding: '20px 24px', borderRadius: 16, background: cardBg, border: `1px solid ${cardBorder}`, animationDelay: '0.3s', boxShadow: cardShadow } as any}>
            <div style={{ color: colors.textMuted, fontSize: 11, fontWeight: 700, letterSpacing: 0.5, textTransform: 'uppercase', textAlign: 'center', marginBottom: 16 } as any}>{t('home.social.trustedBy')}</div>
            <div style={{ display: 'flex', flexWrap: 'wrap', justifyContent: 'center', alignItems: 'center', gap: 10 } as any}>
              {companies.map((company, i) => (
                <div key={`${company}-${i}`} data-testid={`home-trust-chip-${i}`} style={{ borderRadius: 999, border: `1px solid ${withAlpha(colors.border, 'C8')}`, background: withAlpha(colors.bgSoft, darkMode ? 'AB' : 'EF'), padding: '8px 12px', opacity: 0.88, color: colors.textMuted, fontSize: 11, fontWeight: 800, letterSpacing: 0.6, textTransform: 'uppercase' } as any}>{company}</div>
              ))}
            </div>
          </div>
        </>
      ) : (
        <View style={{ gap: 16 }}>
          <View data-testid="impact-stats" testID="impact-stats" style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 12 }}>
            {STATS.map((s) => (
              <View key={s.label} style={{ flex: 1, minWidth: '44%', padding: 16, borderRadius: 14, alignItems: 'center', backgroundColor: cardBg, borderWidth: 1, borderColor: cardBorder }}>
                <Ionicons name={s.icon} size={20} color={s.color} />
                <Text style={{ color: colors.text, fontSize: 22, fontWeight: '800', marginTop: 8 }}>{s.value}</Text>
                <Text style={{ color: colors.textMuted, fontSize: 10, fontWeight: '600', marginTop: 4 }}>{s.label}</Text>
              </View>
            ))}
          </View>
          <View data-testid="testimonial-carousel" testID="testimonial-carousel" style={{ padding: 22, borderRadius: 18, backgroundColor: cardBg, borderWidth: 1, borderColor: cardBorder }}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 12, marginBottom: 14 }}>
              <View style={{ width: 44, height: 44, borderRadius: 12, backgroundColor: (globalThis as any).__alphaColor(currentTestimonial.color, '18'), alignItems: 'center', justifyContent: 'center' }}>
                <Text style={{ color: currentTestimonial.color, fontWeight: '800', fontSize: 15 }}>{currentTestimonial.avatar}</Text>
              </View>
              <View>
                <Text style={{ color: colors.text, fontWeight: '700', fontSize: 14 }}>{currentTestimonial.name}</Text>
                <Text style={{ color: colors.textMuted, fontSize: 11 }}>{currentTestimonial.role}</Text>
              </View>
            </View>
            <Text style={{ color: colors.textSec || colors.textSecondary, fontSize: 14, lineHeight: 22, fontStyle: 'italic' }}>
              "{currentTestimonial.text}"
            </Text>
          </View>
          <View data-testid="trust-logos-native" testID="trust-logos-native" style={{ padding: 18, borderRadius: 16, backgroundColor: cardBg, borderWidth: 1, borderColor: cardBorder }}>
            <Text style={{ color: colors.textMuted, fontSize: 11, fontWeight: '700', letterSpacing: 0.5, textTransform: 'uppercase', textAlign: 'center', marginBottom: 12 }}>{t('home.social.trustedBy')}</Text>
            <View style={{ flexDirection: 'row', flexWrap: 'wrap', justifyContent: 'center', alignItems: 'center', gap: 10 }}>
              {companies.map((company, i) => (
                <View key={`${company}-${i}`} style={chipStyle} data-testid={`home-trust-chip-native-${i}`} testID={`home-trust-chip-native-${i}`}>
                  <Text style={chipTextStyle as any}>{company}</Text>
                </View>
              ))}
            </View>
          </View>
        </View>
      )}
    </View>
  );
}
