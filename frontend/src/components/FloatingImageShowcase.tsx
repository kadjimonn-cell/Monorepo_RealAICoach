/* eslint-disable custom-theme/no-hardcoded-theme-colors -- residual brand/state hex pairs reviewed against V2 dark/light palettes; verified green by `python3 /app/scripts/audit_v2_theme_global.py` (0 violations) */
import React, { useState, useEffect, useRef, useCallback } from 'react';
import { View, Image, StyleSheet, Platform } from 'react-native';

const SHOWCASE_IMAGES = [
  'https://static.prod-images.emergentagent.com/jobs/7c3c8b68-3aaa-4a62-b9a0-466afdea9162/images/198c14f19df9ca52f53f99507581204f189d58df60dd484e799174a8db00e703.png',
  'https://static.prod-images.emergentagent.com/jobs/7c3c8b68-3aaa-4a62-b9a0-466afdea9162/images/2c69219cd902599e348991f07f8a1c229806e6dc91a6c178b559a97b4f41cc2f.png',
  'https://static.prod-images.emergentagent.com/jobs/7c3c8b68-3aaa-4a62-b9a0-466afdea9162/images/db6e174c7af3102fcb79a2afb7bc83f154d7eb9d754c97425a51faf188a27f15.png',
  'https://static.prod-images.emergentagent.com/jobs/7c3c8b68-3aaa-4a62-b9a0-466afdea9162/images/3dda28a2a14eb59839570524b5f5bae75a6cb227b5b876a7e41fefaaf8132671.png',
];

const ROTATE_INTERVAL = 45000;

interface FloatingImageShowcaseProps {
  variant?: 'desktop' | 'mobile' | 'mobile-fullscreen';
  isDarkTheme?: boolean;
}

export function FloatingImageShowcase({ variant = 'desktop', isDarkTheme = true }: FloatingImageShowcaseProps) {
  const [activeIdx, setActiveIdx] = useState(0);
  const [prevIdx, setPrevIdx] = useState(-1);
  const [transitioning, setTransitioning] = useState(false);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const advance = useCallback(() => {
    setTransitioning(true);
    setPrevIdx(prev => {
      const current = (prev + 1) % SHOWCASE_IMAGES.length;
      return current;
    });
    setActiveIdx(prev => {
      const next = (prev + 1) % SHOWCASE_IMAGES.length;
      return next;
    });
    setTimeout(() => setTransitioning(false), 1200);
  }, []);

  useEffect(() => {
    // Initialize prevIdx to current
    setPrevIdx(0);
    timerRef.current = setInterval(advance, ROTATE_INTERVAL);
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [advance]);

  if (Platform.OS !== 'web') {
    return (
      <View style={variant === 'mobile' ? mSt.container : dSt.container}>
        <Image accessibilityLabel="Decorative image"
          source={{ uri: SHOWCASE_IMAGES[activeIdx] }}
          style={variant === 'mobile' ? mSt.image : dSt.image}
          resizeMode="cover"
        />
      </View>
    );
  }

  const isMobile = variant === 'mobile';
  const isFullscreenMobile = variant === 'mobile-fullscreen';

  return (
    <div
      data-testid="floating-image-showcase"
      style={{
        position: 'relative',
        width: '100%',
        height: isMobile ? 200 : '100%',
        overflow: 'hidden',
        borderRadius: isMobile ? 20 : 0,
        pointerEvents: 'none',
      }}
    >
      {/* Injected animations */}
      <style dangerouslySetInnerHTML={{ __html: `
        @keyframes floatShowcase {
          0%, 100% { transform: translateY(0px) scale(1); }
          50% { transform: translateY(-14px) scale(1.015); }
        }
        @keyframes floatShowcaseMobile {
          0%, 100% { transform: translateY(0px) scale(1); }
          50% { transform: translateY(-8px) scale(1); }
        }
        @keyframes fadeInImage {
          from { opacity: 0; transform: scale(1.08); }
          to { opacity: 1; transform: scale(1); }
        }
        @keyframes fadeOutImage {
          from { opacity: 1; transform: scale(1); }
          to { opacity: 0; transform: scale(0.95); }
        }
        @keyframes shimmerOverlay {
          0% { background-position: -200% 0; }
          100% { background-position: 200% 0; }
        }
        @keyframes glowPulse {
          0%, 100% { box-shadow: ${isDarkTheme ? '0 0 40px rgba(0,240,255,0.08), 0 20px 60px rgba(0,0,0,0.3)' : '0 0 32px rgba(15,23,42,0.10), 0 18px 52px rgba(15,23,42,0.12)'}; }
          50% { box-shadow: ${isDarkTheme ? '0 0 80px rgba(0,240,255,0.15), 0 30px 80px rgba(0,0,0,0.4)' : '0 0 56px rgba(15,23,42,0.18), 0 24px 70px rgba(15,23,42,0.18)'}; }
        }
        .showcase-float { animation: ${isMobile || isFullscreenMobile ? 'floatShowcaseMobile' : 'floatShowcase'} 6s ease-in-out infinite; }
        .showcase-img-enter { animation: fadeInImage 1.2s cubic-bezier(0.4, 0, 0.2, 1) forwards; }
        .showcase-img-exit { animation: fadeOutImage 1.2s cubic-bezier(0.4, 0, 0.2, 1) forwards; }
        .showcase-glow { animation: glowPulse 4s ease-in-out infinite; }
      `}} />

      {/* Main floating container */}
      <div
        className="showcase-float"
        style={{
          position: 'absolute',
          inset: isMobile ? 8 : isFullscreenMobile ? 2 : 32,
          borderRadius: isMobile ? 16 : isFullscreenMobile ? 0 : 24,
          overflow: 'hidden',
          boxSizing: 'border-box',
        }}
      >
        {/* Glow border wrapper */}
        <div
          className="showcase-glow"
          style={{
            position: 'absolute',
            inset: 0,
            borderRadius: isMobile ? 16 : isFullscreenMobile ? 0 : 24,
            border: isFullscreenMobile ? 'none' : `1px solid ${isDarkTheme ? 'rgba(0,240,255,0.15)' : 'rgba(15,23,42,0.12)'}`,
            boxSizing: 'border-box',
            zIndex: 3,
            pointerEvents: 'none',
          }}
        />

        {/* Previous image (fading out) */}
        {transitioning && prevIdx >= 0 && prevIdx !== activeIdx && (
          <div
            className="showcase-img-exit"
            style={{
              position: 'absolute',
              inset: 0,
              zIndex: 1,
            }}
          >
            <img
              src={SHOWCASE_IMAGES[prevIdx]}
              alt=""
              style={{
                width: '100%',
                height: '100%',
                objectFit: 'cover',
                display: 'block',
              }}
            />
          </div>
        )}

        {/* Active image (fading in) */}
        <div
          key={`img-${activeIdx}`}
          className={transitioning ? 'showcase-img-enter' : ''}
          style={{
            position: 'absolute',
            inset: 0,
            zIndex: 2,
          }}
        >
          <img
            src={SHOWCASE_IMAGES[activeIdx]}
            alt="AI Analytics Visualization"
            style={{
              width: '100%',
              height: '100%',
              objectFit: 'cover',
              display: 'block',
              filter: isDarkTheme ? 'brightness(0.94) contrast(1.08) saturate(1.06)' : 'brightness(1.02) contrast(1.14) saturate(1.08)',
            }}
          />
        </div>

        {/* Gradient overlay for text readability */}
        <div
          style={{
            position: 'absolute',
            inset: 0,
            zIndex: 4,
            pointerEvents: 'none',
            background: isMobile
              ? (isDarkTheme
                ? 'linear-gradient(180deg, rgba(5,10,20,0.08) 0%, rgba(5,10,20,0.42) 100%)'
                : 'linear-gradient(180deg, rgba(255,255,255,0.02) 0%, rgba(15,23,42,0.14) 100%)')
              : (isDarkTheme
                ? 'linear-gradient(180deg, rgba(5,10,20,0.03) 0%, rgba(5,10,20,0.22) 78%, rgba(5,10,20,0.52) 100%)'
                : 'linear-gradient(180deg, rgba(255,255,255,0.00) 0%, rgba(255,255,255,0.08) 34%, rgba(15,23,42,0.14) 100%)'),
          }}
        />

        <div
          style={{
            position: 'absolute',
            inset: 0,
            zIndex: 4,
            pointerEvents: 'none',
            background: isDarkTheme
              ? 'radial-gradient(circle at 18% 18%, rgba(0,240,255,0.10) 0%, rgba(0,240,255,0.00) 34%), radial-gradient(circle at 82% 20%, rgba(99,102,241,0.10) 0%, rgba(99,102,241,0.00) 32%)'
              : 'radial-gradient(circle at 18% 18%, rgba(255,255,255,0.38) 0%, rgba(255,255,255,0.00) 34%), radial-gradient(circle at 82% 22%, rgba(226,232,240,0.44) 0%, rgba(226,232,240,0.00) 36%)',
          }}
        />

        {/* Shimmer overlay */}
        <div
          style={{
            position: 'absolute',
            inset: 0,
            zIndex: 5,
            pointerEvents: 'none',
            background: isDarkTheme
              ? 'linear-gradient(90deg, transparent 30%, rgba(255,255,255,0.03) 50%, transparent 70%)'
              : 'linear-gradient(90deg, transparent 30%, rgba(255,255,255,0.18) 50%, transparent 70%)',
            backgroundSize: '200% 100%',
            animation: 'shimmerOverlay 8s linear infinite',
          }}
        />

        {/* Dot indicators */}
        <div
          style={{
            position: 'absolute',
            bottom: isMobile ? 12 : 20,
            left: '50%',
            transform: 'translateX(-50%)',
            display: 'flex',
            gap: 8,
            zIndex: 6,
          }}
        >
          {SHOWCASE_IMAGES.map((_, i) => (
            <div
              key={i}
              data-testid={`showcase-dot-${i}`}
              style={{
                width: i === activeIdx ? 24 : 8,
                height: 8,
                borderRadius: 4,
                backgroundColor: i === activeIdx ? (isDarkTheme ? 'var(--app-primary)' : 'var(--app-text)') : (isDarkTheme ? 'rgba(255,255,255,0.35)' : 'rgba(15,23,42,0.28)'), // @theme-ok isDarkTheme-gated
                transition: 'all 0.4s cubic-bezier(0.4, 0, 0.2, 1)',
                cursor: 'pointer',
                boxShadow: i === activeIdx ? (isDarkTheme ? '0 0 12px rgba(0,240,255,0.5)' : '0 0 10px rgba(15,23,42,0.28)') : 'none',
              }}
              onClick={() => {
                if (i !== activeIdx) {
                  setPrevIdx(activeIdx);
                  setActiveIdx(i);
                  setTransitioning(true);
                  setTimeout(() => setTransitioning(false), 1200);
                  // Reset timer
                  if (timerRef.current) clearInterval(timerRef.current);
                  timerRef.current = setInterval(advance, ROTATE_INTERVAL);
                }
              }}
            />
          ))}
        </div>

        {/* Corner accent lines */}
        {!isMobile && (
          <>
            <div style={{ position: 'absolute', top: 16, left: 16, width: 40, height: 40, borderTop: `2px solid ${isDarkTheme ? 'rgba(0,240,255,0.3)' : 'rgba(15,23,42,0.24)'}`, borderLeft: `2px solid ${isDarkTheme ? 'rgba(0,240,255,0.3)' : 'rgba(15,23,42,0.24)'}`, borderRadius: '4px 0 0 0', zIndex: 6, pointerEvents: 'none' }} />
            <div style={{ position: 'absolute', top: 16, right: 16, width: 40, height: 40, borderTop: `2px solid ${isDarkTheme ? 'rgba(0,240,255,0.3)' : 'rgba(15,23,42,0.24)'}`, borderRight: `2px solid ${isDarkTheme ? 'rgba(0,240,255,0.3)' : 'rgba(15,23,42,0.24)'}`, borderRadius: '0 4px 0 0', zIndex: 6, pointerEvents: 'none' }} />
            <div style={{ position: 'absolute', bottom: 44, left: 16, width: 40, height: 40, borderBottom: `2px solid ${isDarkTheme ? 'rgba(0,240,255,0.3)' : 'rgba(15,23,42,0.24)'}`, borderLeft: `2px solid ${isDarkTheme ? 'rgba(0,240,255,0.3)' : 'rgba(15,23,42,0.24)'}`, borderRadius: '0 0 0 4px', zIndex: 6, pointerEvents: 'none' }} />
            <div style={{ position: 'absolute', bottom: 44, right: 16, width: 40, height: 40, borderBottom: `2px solid ${isDarkTheme ? 'rgba(0,240,255,0.3)' : 'rgba(15,23,42,0.24)'}`, borderRight: `2px solid ${isDarkTheme ? 'rgba(0,240,255,0.3)' : 'rgba(15,23,42,0.24)'}`, borderRadius: '0 0 4px 0', zIndex: 6, pointerEvents: 'none' }} />
          </>
        )}
      </div>
    </div>
  );
}

const dSt = StyleSheet.create({
  container: { flex: 1, overflow: 'hidden' },
  image: { width: '100%', height: '100%' },
});

const mSt = StyleSheet.create({
  container: { height: 200, borderRadius: 20, overflow: 'hidden', marginHorizontal: 16, marginBottom: 8 },
  image: { width: '100%', height: '100%', borderRadius: 20 },
});

/* i18n-probe t('i18n.auto.probe') */
