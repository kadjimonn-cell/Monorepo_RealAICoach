import React, { useEffect } from 'react';
import { View, Text, Platform, useWindowDimensions } from 'react-native';
import { useTheme } from '../../context/ThemeContext';
import { useTranslation } from '../../hooks/useTranslation';

const CTA_CSS = `
@keyframes cta-gradient {
  0% { background-position: 0% 50%; }
  50% { background-position: 100% 50%; }
  100% { background-position: 0% 50%; }
}
@keyframes cta-slide-up {
  from { opacity: 0; transform: translateY(20px); }
  to { opacity: 1; transform: translateY(0); }
}
.cta-btn-primary { transition: transform 0.2s ease, box-shadow 0.2s ease; }
.cta-btn-primary:hover { transform: translateY(-2px); box-shadow: 0 8px 24px rgba(37,99,235,0.4); }
.cta-btn-secondary { transition: transform 0.2s ease, background 0.2s ease, border-color 0.2s ease; }
`;

interface CTAProps {
  responsiveWidth?: number;
  onStartCoaching: () => void;
  onRequestDemo: () => void;
}

export default function HomeCTA({ responsiveWidth, onStartCoaching, onRequestDemo }: CTAProps) {
  const { width: windowWidth } = useWindowDimensions();
  const width = responsiveWidth || windowWidth;
  const isDesktop = width >= 768;
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const _isTablet = width >= 768 && width < 1024;
  const { colors, darkMode } = useTheme();
  const { t } = useTranslation();

  useEffect(() => {
    if (Platform.OS === 'web') {
      const id = 'home-cta-css';
      if (!document.getElementById(id)) {
        const s = document.createElement('style');
        s.id = id;
        s.textContent = CTA_CSS;
        document.head.appendChild(s);
      }
    }
  }, []);

  const panelGradient = darkMode
    ? `linear-gradient(135deg, ${colors.card} 0%, ${colors.bg} 35%, ${colors.cardMuted} 70%, ${colors.card} 100%)`
    : `linear-gradient(135deg, ${colors.card} 0%, ${colors.bgSoft} 35%, ${colors.bg} 100%)`;

  return (
    <View data-testid="cta-section" testID="cta-section" style={{ paddingHorizontal: isDesktop ? 40 : 20, paddingTop: 8, paddingBottom: 40 }}>
      {Platform.OS === 'web' ? (
        <div style={{ position: 'relative', overflow: 'hidden', padding: isDesktop ? '48px 40px' : '36px 24px', borderRadius: 24, background: panelGradient, backgroundSize: '300% 300%', animation: 'cta-gradient 10s ease infinite', border: `1px solid ${colors.border}`, boxShadow: darkMode ? 'none' : '0 18px 42px rgba(15,23,42,0.10)' } as any}>
          <div style={{ position: 'absolute', top: -40, right: -40, width: 200, height: 200, borderRadius: '50%', background: `radial-gradient(circle, ${colors.primarySoft} 0%, transparent 70%)`, filter: 'blur(40px)' } as any} />
          <div style={{ position: 'absolute', bottom: -30, left: -30, width: 160, height: 160, borderRadius: '50%', background: `radial-gradient(circle, ${colors.accentSoft} 0%, transparent 70%)`, filter: 'blur(30px)' } as any} />

          <div style={{ position: 'relative', zIndex: 1, textAlign: 'center', animation: 'cta-slide-up 0.6s ease' } as any}>
            <div style={{ display: 'inline-flex', alignItems: 'center', gap: 6, padding: '5px 12px', borderRadius: 20, background: colors.primarySoft, border: `1px solid ${colors.primary}33`, marginBottom: 20 } as any}>
              <span style={{ fontSize: 12 }}>⚡</span>
              <span style={{ color: colors.primary, fontSize: 11, fontWeight: 700, letterSpacing: 0.5 } as any}>{t('home.cta.badge')}</span>
            </div>

            <div style={{ color: colors.text, fontSize: isDesktop ? 32 : 24, fontWeight: 900, letterSpacing: -1, lineHeight: isDesktop ? '40px' : '32px', marginBottom: 14, fontFamily: "'Inter', system-ui, sans-serif" } as any}>
              {t('home.cta.title')}<br />
              <span style={{ background: `linear-gradient(135deg, ${colors.primary}, ${colors.accent})`, WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' } as any}>{t('home.cta.titleAccent')}</span>
            </div>

            <div style={{ color: colors.textSec || colors.textSecondary, fontSize: isDesktop ? 16 : 14, lineHeight: '24px', maxWidth: 540, margin: '0 auto 28px', fontFamily: "'Inter', system-ui, sans-serif" } as any}>
              {t('home.cta.description')}
            </div>

            <div style={{ display: 'flex', flexDirection: isDesktop ? 'row' : 'column', justifyContent: 'center', gap: 14 } as any}>
              <div data-testid="cta-start-coaching" className="cta-btn-primary" role="button" tabIndex={0} onClick={onStartCoaching} style={{ padding: '16px 36px', borderRadius: 14, cursor: 'pointer', background: `linear-gradient(135deg, ${colors.primary} 0%, ${colors.indigo} 50%, ${colors.accent} 100%)`, display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: 8, boxShadow: `0 4px 14px ${colors.primary}4D` } as any}>
                <span style={{ color: colors.primaryText, fontSize: 15, fontWeight: 700 }}>{t('home.cta.startCoaching')}</span>
                <span style={{ fontSize: 16, color: colors.primaryText }}>→</span>
              </div>
              <div data-testid="cta-request-demo" className="cta-btn-secondary" role="button" tabIndex={0} onClick={onRequestDemo} style={{ padding: '16px 36px', borderRadius: 14, cursor: 'pointer', background: darkMode ? colors.card : colors.bgSoft, border: `1px solid ${colors.border}`, display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: 8 } as any}>
                <span style={{ color: colors.textSecondary, fontSize: 15, fontWeight: 600 }}>{t('home.cta.requestDemo')}</span>
              </div>
            </div>
          </div>
        </div>
      ) : (
        <View style={{ padding: 32, borderRadius: 22, backgroundColor: colors.card, borderWidth: 1, borderColor: colors.border, alignItems: 'center' }}>
          <View style={{ paddingHorizontal: 12, paddingVertical: 5, borderRadius: 20, backgroundColor: colors.primarySoft, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(colors.primary, '33'), marginBottom: 20 }}>
            <Text style={{ color: colors.primary, fontSize: 11, fontWeight: '700', letterSpacing: 0.5 }}>{t('home.cta.badge')}</Text>
          </View>
          <Text style={{ color: colors.text, fontSize: 24, fontWeight: '900', letterSpacing: -1, lineHeight: 32, textAlign: 'center', marginBottom: 14 }}>
            {t('home.cta.title')}{`\n`}{t('home.cta.titleAccent')}
          </Text>
          <Text style={{ color: colors.textSec || colors.textSecondary, fontSize: 14, lineHeight: 22, textAlign: 'center', marginBottom: 28 }}>
            {t('home.cta.description')}
          </Text>
          <View data-testid="cta-start-coaching" testID="cta-start-coaching" style={{ width: '100%', padding: 16, borderRadius: 14, backgroundColor: colors.primary, alignItems: 'center', marginBottom: 12 }}>
            <Text style={{ color: colors.primaryText, fontSize: 15, fontWeight: '700' }}>{t('home.cta.startCoaching')} →</Text>
          </View>
          <View data-testid="cta-request-demo" testID="cta-request-demo" style={{ width: '100%', padding: 16, borderRadius: 14, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceHover, alignItems: 'center' }}>
            <Text style={{ color: colors.textSecondary, fontSize: 15, fontWeight: '600' }}>{t('home.cta.requestDemo')}</Text>
          </View>
        </View>
      )}
    </View>
  );
}
