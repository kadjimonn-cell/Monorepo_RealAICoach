// eslint-disable-next-line @typescript-eslint/no-unused-vars
import React, { useEffect, useState, useCallback, useMemo } from 'react';
import { Platform } from 'react-native';
import api from '../../services/api';
import { useTheme } from '../../context/ThemeContext';
import { useTranslation } from '../../hooks/useTranslation';

const STEP_DEFS = [
  { id: 'home-hero-section', icon: '\u{1F680}', titleKey: 'home.tour.step1.title', titleFallback: 'Your Command Center', descKey: 'home.tour.step1.desc', descFallback: 'This is your AI-powered dashboard hub. See real-time stats, your AI system status, and quick-access actions all in one place.' },
  { id: 'hero-stats-grid', icon: '\u{1F4CA}', titleKey: 'home.tour.step2.title', titleFallback: 'Live Statistics', descKey: 'home.tour.step2.desc', descFallback: 'These counters update in real-time showing active users, AI sessions, performance metrics, and global coach availability.' },
  { id: 'dashboard-charts-section', icon: '\u{1F4C8}', titleKey: 'home.tour.step3.title', titleFallback: 'Performance Dashboard', descKey: 'home.tour.step3.desc', descFallback: 'Interactive charts showing AI session trends, user growth, and coaching category distribution. Data refreshes every 30 seconds automatically.' },
  { id: 'feature-highlights-section', icon: '\u2728', titleKey: 'home.tour.step4.title', titleFallback: 'Powerful AI Features', descKey: 'home.tour.step4.desc', descFallback: 'Explore our enterprise AI toolkit - from smart coaching and goal tracking to predictive insights and personalized roadmaps.' },
  { id: 'social-proof-section', icon: '\u{1F6E1}', titleKey: 'home.tour.step5.title', titleFallback: 'Trusted by Leaders', descKey: 'home.tour.step5.desc', descFallback: 'See how world-class organizations are accelerating with AI coaching. Check impact metrics and testimonials from industry leaders.' },
  { id: 'cta-section', icon: '\u26A1', titleKey: 'home.tour.step6.title', titleFallback: 'Ready to Start?', descKey: 'home.tour.step6.desc', descFallback: 'Jump into AI coaching right away or request an enterprise demo. Your transformation begins here!' },
];

interface TourStep { id: string; icon: string; title: string; desc: string }

interface TourLabels { stepOf: string; back: string; skip: string; next: string; finish: string }

interface TourPalette {
  bg: string;
  bgGradient: string;
  border: string;
  text: string;
  textMuted: string;
  textDim: string;
  primary: string;
  accent: string;
  trackBg: string;
  trackMuted: string;
  primaryText: string;
  accentRgb: string;
}

function escHtml(value: string): string {
  return String(value)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;');
}

function hexToRgbString(hex: string, fallback: string): string {
  const m = /^#?([0-9a-f]{6})$/i.exec(String(hex || '').trim());
  if (!m) return fallback;
  const n = parseInt(m[1], 16);
  return `${(n >> 16) & 255},${(n >> 8) & 255},${n & 255}`;
}

function buildTourCSS(accentRgb: string): string {
  return `
#tour-root { position:fixed; inset:0; z-index:999999; pointer-events:auto; animation:tfade .3s ease; }
@keyframes tfade { from{opacity:0} to{opacity:1} }
@keyframes tpulse { 0%,100%{box-shadow:0 0 0 4px rgba(${accentRgb},.30)} 50%{box-shadow:0 0 0 8px rgba(${accentRgb},.15)} }
@keyframes tslide { from{opacity:0;transform:translateY(12px) scale(.95)} to{opacity:1;transform:translateY(0) scale(1)} }
#tour-root .tour-tt { animation:tslide .4s cubic-bezier(.34,1.56,.64,1); }
#tour-root .tour-nb:hover { transform:translateY(-1px); box-shadow:0 6px 20px rgba(${accentRgb},.35); }
#tour-root .tour-sb:hover { opacity: 1 !important; }
`;
}

function buildTourDOM(step: number, rect: DOMRect | null, palette: TourPalette, steps: TourStep[], labels: TourLabels) {
  const s = steps[step];
  const isLast = step === steps.length - 1;
  const progress = ((step + 1) / steps.length) * 100;

  // Clip-path for spotlight
  let clip = 'none';
  if (rect) {
    const p = 12, r = 16;
    const x = rect.left - p, y = rect.top - p, w = rect.width + p*2, h = rect.height + p*2;
    clip = `polygon(0% 0%, 0% 100%, ${x}px 100%, ${x}px ${y+r}px, ${x+r}px ${y}px, ${x+w-r}px ${y}px, ${x+w}px ${y+r}px, ${x+w}px ${y+h-r}px, ${x+w-r}px ${y+h}px, ${x+r}px ${y+h}px, ${x}px ${y+h-r}px, ${x}px 100%, 100% 100%, 100% 0%)`;
  }

  // Tooltip positioning
  let ttop = '50%', tleft = '50%', ttransform = 'translate(-50%,-50%)';
  if (rect) {
    const vw = window.innerWidth, vh = window.innerHeight;
    const tw = Math.min(380, Math.max(280, vw - 32));
    let t = rect.bottom + 16;
    let l = rect.left + rect.width/2 - tw/2;
    if (t + 220 > vh) t = rect.top - 230;
    if (t < 16) t = 16;
    if (l < 16) l = 16;
    if (l + tw > vw - 16) l = vw - tw - 16;
    ttop = `${t}px`; tleft = `${l}px`; ttransform = 'none';
  }

  const accentRgb = palette.accentRgb;
  const stepOfLabel = escHtml(labels.stepOf.replace('{num}', String(step + 1)).replace('{total}', String(steps.length)));
  return `
    <div style="position:fixed;inset:0;background:rgba(0,0,0,.75);clip-path:${clip};transition:clip-path .4s cubic-bezier(.4,0,.2,1)"></div>
    ${rect ? `<div style="position:fixed;top:${rect.top-12}px;left:${rect.left-12}px;width:${rect.width+24}px;height:${rect.height+24}px;border-radius:16px;border:2px solid rgba(${accentRgb},.45);animation:tpulse 2s ease-in-out infinite;pointer-events:none;transition:all .4s cubic-bezier(.4,0,.2,1)"></div>` : ''}
    <div class="tour-tt" data-testid="tour-tooltip" style="position:fixed;top:${ttop};left:${tleft};transform:${ttransform};width:min(380px, calc(100vw - 32px));max-width:calc(100vw - 32px);padding:24px;border-radius:20px;background:${palette.bgGradient};border:1px solid ${palette.border};box-shadow:0 20px 60px rgba(0,0,0,.5),0 0 0 1px ${palette.border};z-index:100000;box-sizing:border-box">
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:16px">
        <div style="display:flex;align-items:center;gap:8px">
          <div style="width:36px;height:36px;border-radius:10px;background:linear-gradient(135deg,rgba(${accentRgb},.22),rgba(${accentRgb},.10));display:flex;align-items:center;justify-content:center;border:1px solid rgba(${accentRgb},.30);font-size:16px">${s.icon}</div>
          <span style="color:${palette.textMuted};font-size:12px;font-weight:600">${stepOfLabel}</span>
        </div>
        <div data-testid="tour-close-btn" role="button" tabindex="0" onclick="window.__tourSkip()" style="width:28px;height:28px;border-radius:8px;display:flex;align-items:center;justify-content:center;cursor:pointer;background:${palette.trackBg};color:${palette.textDim};font-size:14px;transition:background .15s ease"
          onmouseenter="this.style.background='${palette.trackMuted}'" onmouseleave="this.style.background='${palette.trackBg}'">&times;</div>
      </div>
      <div style="height:3px;border-radius:2px;background:${palette.trackBg};margin-bottom:18px;overflow:hidden">
        <div style="height:100%;border-radius:2px;background:linear-gradient(90deg,${palette.primary},${palette.accent});width:${progress}%;transition:width .4s cubic-bezier(.4,0,.2,1)"></div>
      </div>
      <div style="color:${palette.text};font-size:18px;font-weight:800;letter-spacing:-0.5px;margin-bottom:8px;font-family:'Manrope',system-ui,sans-serif">${escHtml(s.title)}</div>
      <div style="color:${palette.textDim};font-size:14px;line-height:22px;margin-bottom:24px;font-family:'Manrope',system-ui,sans-serif">${escHtml(s.desc)}</div>
      <div style="display:flex;align-items:center;justify-content:space-between">
        <div style="display:flex;gap:8px">
          ${step > 0 ? `<div data-testid="tour-back-btn" role="button" tabindex="0" onclick="window.__tourBack()" style="padding:10px 16px;border-radius:10px;cursor:pointer;background:${palette.trackBg};border:1px solid ${palette.trackMuted};display:flex;align-items:center;gap:6px;transition:background .15s ease;color:${palette.textDim};font-size:13px;font-weight:600"
            onmouseenter="this.style.background='${palette.trackMuted}'" onmouseleave="this.style.background='${palette.trackBg}'">\u2190 ${escHtml(labels.back)}</div>` : ''}
          <div class="tour-sb" data-testid="tour-skip-btn" role="button" tabindex="0" onclick="window.__tourSkip()" style="padding:10px 16px;border-radius:10px;cursor:pointer;color:${palette.textMuted};font-size:13px;font-weight:600;display:flex;align-items:center">${escHtml(labels.skip)}</div>
        </div>
        <div class="tour-nb" data-testid="tour-next-btn" role="button" tabindex="0" onclick="window.__tourNext()" style="padding:10px 22px;border-radius:10px;cursor:pointer;background:linear-gradient(135deg,${palette.primary},${palette.accent});box-shadow:0 4px 12px rgba(${accentRgb},.35);display:flex;align-items:center;gap:6px;color:${palette.primaryText};font-size:13px;font-weight:700;transition:transform .15s ease,box-shadow .15s ease">
          ${isLast ? `${escHtml(labels.finish)} \u2713` : `${escHtml(labels.next)} \u2192`}
        </div>
      </div>
      <div style="display:flex;justify-content:center;gap:6px;margin-top:18px">
        ${steps.map((_,i) => `<div data-testid="tour-dot-${i}" role="button" tabindex="0" onclick="window.__tourGo(${i})" style="width:${i===step?20:6}px;height:6px;border-radius:3px;background:${i===step?palette.primary:i<step?`rgba(${accentRgb},.5)`:palette.trackMuted};transition:all .3s ease;cursor:pointer"></div>`).join('')}
      </div>
    </div>
  `;
}

interface Props {
  visible: boolean;
  onComplete: () => void;
}

export default function HomeOnboardingTour({ visible, onComplete }: Props) {
  const [step, setStep] = useState(0);
  const { colors, darkMode } = useTheme();
  const { tx } = useTranslation();

  const steps = useMemo<TourStep[]>(() => STEP_DEFS.map((def) => ({
    id: def.id,
    icon: def.icon,
    title: tx(def.titleKey, def.titleFallback),
    desc: tx(def.descKey, def.descFallback),
  })), [tx]);

  const labels = useMemo<TourLabels>(() => ({
    stepOf: tx('home.tour.stepOf', 'Step {num} of {total}'),
    back: tx('home.tour.back', 'Back'),
    skip: tx('home.tour.skip', 'Skip tour'),
    next: tx('home.tour.next', 'Next'),
    finish: tx('home.tour.finish', 'Finish Tour'),
  }), [tx]);

  const palette = useMemo<TourPalette>(() => ({
    bg: darkMode ? colors.card : colors.bg,
    bgGradient: darkMode
      ? `linear-gradient(145deg, ${colors.cardMuted}, ${colors.bg})`
      : `linear-gradient(145deg, ${colors.card}, ${colors.bgSoft})`,
    border: darkMode ? colors.border : colors.borderMd,
    text: colors.text,
    textMuted: colors.textMuted,
    textDim: colors.textDim || colors.textSecondary,
    primary: colors.primary,
    accent: colors.accent,
    trackBg: darkMode ? 'rgba(255,255,255,.06)' : 'rgba(15,23,42,.08)',
    trackMuted: darkMode ? 'rgba(255,255,255,.12)' : 'rgba(15,23,42,.14)',
    primaryText: colors.primaryText,
    accentRgb: hexToRgbString(colors.accent, '20,184,166'),
  }), [colors, darkMode]);

  const cleanup = useCallback(() => {
    if (Platform.OS !== 'web') return;
    const el = document.getElementById('tour-root');
    if (el) el.remove();
    delete (window as any).__tourNext;
    delete (window as any).__tourBack;
    delete (window as any).__tourSkip;
    delete (window as any).__tourGo;
  }, []);

  const completeTour = useCallback(() => {
    api.post('/home/tour-complete').catch(() => {});
    cleanup();
    setStep(0);
    onComplete();
  }, [cleanup, onComplete]);

  const renderTour = useCallback((currentStep: number) => {
    if (Platform.OS !== 'web') return;

    // Inject / refresh theme-aware CSS
    let style = document.getElementById('tour-css-el') as HTMLStyleElement | null;
    if (!style) {
      style = document.createElement('style');
      style.id = 'tour-css-el';
      document.head.appendChild(style);
    }
    style.textContent = buildTourCSS(palette.accentRgb);

    const target = document.querySelector(`[data-testid="${steps[currentStep].id}"]`) as HTMLElement;
    if (target) {
      target.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }

    setTimeout(() => {
      const rect = target ? target.getBoundingClientRect() : null;
      let root = document.getElementById('tour-root');
      if (!root) {
        root = document.createElement('div');
        root.id = 'tour-root';
        root.setAttribute('data-testid', 'onboarding-tour-overlay');
        document.body.appendChild(root);
      }
      root.innerHTML = buildTourDOM(currentStep, rect, palette, steps, labels);
    }, target ? 450 : 0);
  }, [palette, steps, labels]);

  // Wire global handlers
  useEffect(() => {
    if (Platform.OS !== 'web' || !visible) return;

    (window as any).__tourNext = () => {
      const next = step >= steps.length - 1 ? -1 : step + 1;
      if (next === -1) { completeTour(); }
      else { setStep(next); }
    };
    (window as any).__tourBack = () => {
      if (step > 0) setStep(step - 1);
    };
    (window as any).__tourSkip = () => { completeTour(); };
    (window as any).__tourGo = (i: number) => { setStep(i); };

    // Keyboard
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') completeTour();
      if (e.key === 'ArrowRight' || e.key === 'Enter') (window as any).__tourNext();
      if (e.key === 'ArrowLeft') (window as any).__tourBack();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [visible, step, steps.length, completeTour]);

  // Render/update tour DOM when step or visibility changes
  useEffect(() => {
    if (!visible || Platform.OS !== 'web') {
      cleanup();
      return;
    }
    renderTour(step);
  }, [visible, step, renderTour, cleanup]);

  // Cleanup on unmount
  useEffect(() => () => cleanup(), [cleanup]);

  return null; // All rendering is via direct DOM manipulation
}

/* i18n-probe t('i18n.auto.probe') */
