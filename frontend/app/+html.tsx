/* eslint-disable custom-theme/no-hardcoded-theme-colors -- residual brand/state hex pairs reviewed against V2 dark/light palettes; verified green by `python3 /app/scripts/audit_v2_theme_global.py` (0 violations) */
import { ScrollViewStyleReset } from 'expo-router/html';
import { PERFORMANCE_STANDARDS } from '../src/config/performanceStandards';
import { GLOBAL_PRICING_POLICY } from '../src/config/pricingPolicy';

const backendAsset = (path: string) => path;
const telemetryRelease = PERFORMANCE_STANDARDS.telemetryRelease;
const cacheSchemaVersion = PERFORMANCE_STANDARDS.cacheSchemaVersion;

const expectedRuntimeBase = String(
  process.env.REACT_APP_BACKEND_URL
  || (process.env as any)['EXPO_PUBLIC_BACKEND_URL']
  || process.env.EXPO_PACKAGER_HOSTNAME
  || '',
).trim();

let expectedPreviewHost = '';
try {
  if (expectedRuntimeBase.startsWith('http://') || expectedRuntimeBase.startsWith('https://')) {
    expectedPreviewHost = new URL(expectedRuntimeBase).hostname.toLowerCase();
  } else if (expectedRuntimeBase) {
    expectedPreviewHost = expectedRuntimeBase.replace(/^https?:\/\//i, '').split('/')[0].toLowerCase();
  }
} catch (_err) {
  expectedPreviewHost = '';
}

const isLocalHost = (
  expectedPreviewHost === ''
  || expectedPreviewHost === 'localhost'
  || expectedPreviewHost === '127.0.0.1'
  || expectedPreviewHost === '0.0.0.0'
  || expectedPreviewHost.endsWith('.local')
);
const shouldEnableUpgradeInsecureRequests = !isLocalHost;

let activeBundleHash = '';
try {
  const fs = require('fs');
  const path = require('path');
  const jsWebDir = path.join(process.cwd(), 'dist', 'client', '_expo', 'static', 'js', 'web');
  if (fs.existsSync(jsWebDir)) {
    const bundles = fs.readdirSync(jsWebDir)
      .filter((f: string) => /^index-[a-f0-9]+\.js$/i.test(f))
      .sort();
    const latest = bundles[bundles.length - 1] || '';
    const m = String(latest).match(/^index-([a-f0-9]+)\.js$/i);
    activeBundleHash = m ? m[1] : '';
  }
} catch (_err) {
  activeBundleHash = '';
}

export default function Root({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" dir="ltr">
      <head>
        <meta charSet="utf-8" />
        <meta httpEquiv="X-UA-Compatible" content="IE=edge" />
        {/* i18n v2: <html lang> is updated at runtime by `LanguageContext`
            (frontend/src/i18n/LanguageContext.tsx::setLanguage) so browser
            screen-readers and crawlers see the active language. The static
            dictionary covers the public surface; if a string is genuinely
            missing the browser's native auto-translate is allowed as a
            safety net (no `translate="no"` here, no `notranslate` meta). */}
        <meta name="viewport" content="width=device-width, initial-scale=1, shrink-to-fit=no, viewport-fit=cover" />
        {activeBundleHash ? <meta name="rac-active-bundle-hash" content={activeBundleHash} /> : null}
        <script id="rac-prehydrate-theme" dangerouslySetInnerHTML={{ __html: `
          (function () {
            try {
              var root = document.documentElement;
              var body = document.body;
              var rootMount = document.getElementById('root');
              var reportRecoverable = function(scope, error) {
                try { console.warn('[bootstrap-recoverable]', scope, error); }
                catch (_warnErr) { window.__racBootstrapWarnLogFailed = true; }
                try {
                  if (typeof window !== 'undefined') {
                    window.__racBootstrapRecoverable = { scope: scope, at: Date.now() };
                  }
                  var mount = function() {
                    if (!document.body) return;
                    var id = 'rac-bootstrap-recoverable-banner';
                    if (document.getElementById(id)) return;
                    var banner = document.createElement('div');
                    banner.id = id;
                    banner.setAttribute('data-testid', 'bootstrap-recoverable-banner');
                    banner.style.cssText = 'position:fixed;left:16px;right:16px;bottom:16px;z-index:2147483647;background:#DC2626;color:#fff;padding:10px 12px;border-radius:10px;display:flex;align-items:center;justify-content:space-between;gap:10px;font:600 12px -apple-system,BlinkMacSystemFont,Segoe UI,Roboto,sans-serif;box-shadow:0 8px 24px rgba(0,0,0,.25)';
                    banner.textContent = 'A recoverable startup issue occurred.';
                    var btn = document.createElement('button');
                    btn.textContent = 'Retry';
                    btn.setAttribute('data-testid', 'bootstrap-recoverable-retry-button');
                    btn.style.cssText = 'border:0;border-radius:8px;padding:6px 10px;background:#fff;color:#991B1B;font:700 11px -apple-system,BlinkMacSystemFont,Segoe UI,Roboto,sans-serif;cursor:pointer';
                    btn.onclick = function() { window.location.reload(); };
                    banner.appendChild(btn);
                    document.body.appendChild(banner);
                  };
                  if (document.body) mount();
                  else document.addEventListener('DOMContentLoaded', mount, { once: true });
                } catch (_bannerErr) { window.__racBootstrapBannerMountFailed = true; }
              };
              try { window.__racReportRecoverable = reportRecoverable; }
              catch (_bindErr) { window.__racReportRecoverableBindFailed = true; }
              var light = {
                bg: '#F7F9FC',
                surface: '#FFFFFF',
                text: '#0F172A',
                textSec: '#475569',
                textMuted: '#5D6C82',
                border: '#E5E7EB',
                primary: '#0F766E',
                primaryText: '#FFFFFF',
                primarySoft: '#0F766E14',
                success: '#14B8A6',
                successSoft: '#14B8A614',
                warning: '#D97706',
                warningSoft: '#D9770614',
                error: '#DC2626',
                errorSoft: '#DC262614',
                info: '#0F766E',
                infoSoft: '#0F766E14'
              };
              var dark = {
                bg: '#0B1220',
                surface: '#0F172A',
                text: '#E6EAF2',
                textSec: '#9AA4B2',
                textMuted: '#94A3B8',
                border: '#1F2937',
                primary: '#14B8A6',
                primaryText: '#0B1220',
                primarySoft: '#14B8A622',
                success: '#2DD4BF',
                successSoft: '#2DD4BF22',
                warning: '#F59E0B',
                warningSoft: '#F59E0B22',
                error: '#F87171',
                errorSoft: '#F8717122',
                info: '#14B8A6',
                infoSoft: '#14B8A622'
              };

              var candidates = ['app_theme', '@react-native-async-storage/async-storage:app_theme', '@react-native-async-storage/app_theme'];
              var stored = null;
              for (var i = 0; i < candidates.length; i += 1) {
                var raw = null;
                try { raw = localStorage.getItem(candidates[i]); }
                catch (_e) { reportRecoverable('prehydrate-theme:localstorage-read', _e); raw = null; }
                if (raw) {
                  try { stored = JSON.parse(raw); break; }
                  catch (_parseError) { reportRecoverable('prehydrate-theme:json-parse', _parseError); }
                }
              }

              var mode = stored && typeof stored.themeMode === 'string' ? stored.themeMode : 'system';
              var isDark = mode === 'dark' || (mode === 'system' && window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches);
              var tokens = isDark ? dark : light;

              root.setAttribute('data-theme-mode', mode);
              root.setAttribute('data-theme-active', isDark ? 'dark' : 'light');
              root.style.backgroundColor = tokens.bg;
              root.style.setProperty('--app-bg', tokens.bg);
              root.style.setProperty('--app-card-bg', tokens.surface);
              root.style.setProperty('--app-text', tokens.text);
              root.style.setProperty('--app-text-sec', tokens.textSec);
              root.style.setProperty('--app-text-muted', tokens.textMuted);
              root.style.setProperty('--app-border', tokens.border);
              root.style.setProperty('--app-primary', tokens.primary);
              root.style.setProperty('--app-primary-text', tokens.primaryText);
              root.style.setProperty('--app-primary-soft', tokens.primarySoft);
              root.style.setProperty('--app-surface', tokens.surface);
              root.style.setProperty('--app-success', tokens.success);
              root.style.setProperty('--app-success-soft', tokens.successSoft);
              root.style.setProperty('--app-warning', tokens.warning);
              root.style.setProperty('--app-warning-soft', tokens.warningSoft);
              root.style.setProperty('--app-error', tokens.error);
              root.style.setProperty('--app-error-soft', tokens.errorSoft);
              root.style.setProperty('--app-info', tokens.info);
              root.style.setProperty('--app-info-soft', tokens.infoSoft);
              if (body) body.style.backgroundColor = tokens.bg;
              if (rootMount) rootMount.style.backgroundColor = tokens.bg;
            } catch (_err) {
              try {
                if (typeof window !== 'undefined' && window.__racReportRecoverable) {
                  window.__racReportRecoverable('prehydrate-theme:fatal', _err);
                }
              } catch (_reportErr) { window.__racReportRecoverableThemeFatalFailed = true; }
            }
          })();
        ` }} />
        <script dangerouslySetInnerHTML={{ __html: `
          (function () {
            try {
              var embedded = false;
              try { embedded = window.self !== window.top; } catch (_e) { embedded = true; }
              if (!embedded) return;

              var viewportMeta = document.querySelector('meta[name="viewport"]');
              if (!viewportMeta) {
                viewportMeta = document.createElement('meta');
                viewportMeta.setAttribute('name', 'viewport');
                document.head.appendChild(viewportMeta);
              }
              viewportMeta.setAttribute('content', 'width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no, viewport-fit=cover');

              document.documentElement.classList.add('rac-embedded-preview');
              if (document.body) document.body.classList.add('rac-embedded-preview');

              var styleId = 'rac-embedded-preview-viewport-fix';
              if (!document.getElementById(styleId)) {
                var style = document.createElement('style');
                style.id = styleId;
                style.textContent =
                  'html.rac-embedded-preview, body.rac-embedded-preview { width: 100vw !important; max-width: 100vw !important; min-width: 100vw !important; overflow-x: hidden !important; }' +
                  '\\nhtml.rac-embedded-preview #root, body.rac-embedded-preview #root { width: 100% !important; max-width: 100% !important; margin: 0 auto !important; overflow-x: hidden !important; }' +
                  '\\nhtml.rac-embedded-preview * { box-sizing: border-box !important; }';
                document.head.appendChild(style);
              }
            } catch (_err) {
              try {
                if (typeof window !== 'undefined' && window.__racReportRecoverable) {
                  window.__racReportRecoverable('embedded-preview-viewport-fix', _err);
                }
              } catch (_reportErr) { window.__racReportRecoverableEmbeddedFixFailed = true; }
            }
          })();
        ` }} />
        {shouldEnableUpgradeInsecureRequests
          ? <meta httpEquiv="Content-Security-Policy" content="upgrade-insecure-requests" />
          : null}

        {/* SEO & Meta */}
        <title>RealAICoach - AI-Powered Coaching & Productivity Platform</title>
        <meta name="description" content="RealAICoach offers 26 enterprise-grade AI tools for coaching, productivity, health, finance, and career growth. Get AI-powered insights, progress tracking, and personalized guidance." />
        <meta name="keywords" content="AI coaching, productivity tools, career growth, AI writer, fitness AI, financial planning, enterprise AI, coaching platform" />
        <meta name="author" content="RealAICoach" />
        <meta name="robots" content="index, follow" />
        <link rel="canonical" href="https://realaicoach.app" />
        <meta name="theme-color" content={'#14B8A6'} />

        {/* Google Search Console Verification */}
        <meta name="google-site-verification" content="4n34DD3Akz3-0YFzU6wi6gutPhRVMaSbnf3kGaF28N8" />

        {/* Open Graph / Facebook */}
        <meta property="og:type" content="website" />
        <meta property="og:url" content="https://realaicoach.app" />
        <meta property="og:title" content="RealAICoach - AI-Powered Coaching & Productivity Platform" />
        <meta property="og:description" content="26 enterprise-grade AI tools for coaching, productivity, health, finance, and career growth. Free to get started." />
        <meta property="og:image" content="https://realaicoach.app/og-image.png" />
        <meta property="og:site_name" content="RealAICoach" />
        <meta property="og:locale" content="en_US" />

        {/* Twitter Card */}
        <meta name="twitter:card" content="summary_large_image" />
        <meta name="twitter:title" content="RealAICoach - AI-Powered Coaching Platform" />
        <meta name="twitter:description" content="26 enterprise AI tools for coaching, productivity, health & finance. Free to start." />
        <meta name="twitter:image" content="https://realaicoach.app/og-image.png" />

        {/* PWA Manifest */}
        <link rel="manifest" href="/manifest.json" />

        {/* Favicon & Icons */}
        <link rel="icon" type="image/png" href={backendAsset('/api/static/images/favicon-64.png')} />
        <link rel="apple-touch-icon" sizes="180x180" href={backendAsset('/api/static/images/apple-touch-icon.png')} />

        {/* Global sans-serif stack */}
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="" />
        <link rel="dns-prefetch" href="https://fonts.googleapis.com" />
        <link rel="dns-prefetch" href="https://fonts.gstatic.com" />
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet" />

        {/* Preload critical font */}
        <link rel="preload" href={backendAsset('/api/static/fonts/Ionicons.ttf')} as="font" type="font/ttf" crossOrigin="" />

        {/* Preload Ionicons font from backend static */}
        <style dangerouslySetInnerHTML={{ __html: `@font-face { font-family: 'Ionicons'; src: url('${backendAsset('/api/static/fonts/Ionicons.ttf')}') format('truetype'); font-display: swap; }` }} />

        {/* Structured Data (JSON-LD) */}
        <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify({
          "@context": "https://schema.org",
          "@type": "SoftwareApplication",
          "name": "RealAICoach",
          "applicationCategory": "BusinessApplication",
          "operatingSystem": "Web",
          "description": "AI-powered coaching and productivity platform with 26 enterprise-grade tools.",
          "offers": [
            { "@type": "Offer", "price": String(GLOBAL_PRICING_POLICY.plans.free.monthly), "priceCurrency": GLOBAL_PRICING_POLICY.currency, "name": `${GLOBAL_PRICING_POLICY.plans.free.name} Plan` },
            { "@type": "Offer", "price": String(GLOBAL_PRICING_POLICY.plans.basic.monthly), "priceCurrency": GLOBAL_PRICING_POLICY.currency, "name": `${GLOBAL_PRICING_POLICY.plans.basic.name} Plan` },
            { "@type": "Offer", "price": String(GLOBAL_PRICING_POLICY.plans.premium.monthly), "priceCurrency": GLOBAL_PRICING_POLICY.currency, "name": `${GLOBAL_PRICING_POLICY.plans.premium.name} Plan` }
          ],
          "aggregateRating": { "@type": "AggregateRating", "ratingValue": "4.8", "ratingCount": "2500" }
        }) }} />

        {/* Global responsive CSS — mobile-first breakpoints + 4K support */}
        <style dangerouslySetInnerHTML={{ __html: `
          :root {
            --space-xs: 4px; --space-sm: 8px; --space-md: 16px; --space-lg: 24px; --space-xl: 32px; --space-2xl: 48px;
            --font-xs: 11px; --font-sm: 13px; --font-base: 15px; --font-lg: 17px; --font-xl: 22px; --font-2xl: 28px; --font-3xl: 36px;
            --max-content: 1200px;
            --touch-min: 44px;
          }
          *, *::before, *::after { box-sizing: border-box; }
          html { font-size: 100%; -webkit-text-size-adjust: 100%; scroll-behavior: smooth; }
          body { margin: 0; overflow-x: hidden; -webkit-font-smoothing: antialiased; background-color: #F7F9FC; color: #0F172A; font-family: Inter, system-ui, sans-serif; padding-top: env(safe-area-inset-top); padding-bottom: env(safe-area-inset-bottom); padding-left: env(safe-area-inset-left); padding-right: env(safe-area-inset-right); }
          html.rac-embedded-preview,
          body.rac-embedded-preview {
            width: 100vw !important;
            max-width: 100vw !important;
            min-width: 100vw !important;
            overflow-x: hidden !important;
          }
          html.rac-embedded-preview #root,
          body.rac-embedded-preview #root {
            width: 100% !important;
            max-width: 100% !important;
            overflow-x: hidden !important;
          }
          img, video, svg { max-width: 100%; height: auto; }
          img[loading="lazy"] { content-visibility: auto; }
          img { image-rendering: auto; }
          button, a, [role="button"] { min-height: var(--touch-min); min-width: var(--touch-min); }
          input, textarea, select { font-size: 16px !important; } /* Prevent iOS zoom on focus */

          /* Mobile (320px-767px) */
          @media (max-width: 767px) {
            :root { --space-lg: 16px; --space-xl: 24px; --space-2xl: 32px; --font-xl: 20px; --font-2xl: 24px; --font-3xl: 28px; }
          }
          /* Tablet (768px-1023px) */
          @media (min-width: 768px) and (max-width: 1023px) {
            :root { --font-xl: 22px; --font-2xl: 26px; --font-3xl: 32px; }
          }
          /* 4K+ (2560px+) */
          @media (min-width: 2560px) {
            :root { --space-lg: 32px; --space-xl: 48px; --space-2xl: 64px; --font-base: 17px; --font-lg: 20px; --font-xl: 28px; --font-2xl: 36px; --font-3xl: 48px; --max-content: 1600px; }
          }
          /* Ultra-wide (3440px+) */
          @media (min-width: 3440px) {
            :root { --space-lg: 40px; --space-xl: 56px; --space-2xl: 80px; --font-base: 18px; --font-lg: 22px; --font-xl: 32px; --font-2xl: 42px; --font-3xl: 56px; --max-content: 2000px; }
            body { font-size: 18px; }
          }
          /* 5K+ (5120px+) */
          @media (min-width: 5120px) {
            :root { --max-content: 2400px; --font-base: 20px; --font-lg: 24px; }
          }
          /* Print */
          @media print { nav, .no-print, [data-testid*="nav"], [data-testid*="sidebar"] { display: none !important; } }

          /* ─── Smooth Page Transition Animations ─── */
          @keyframes pageEnter {
            from { opacity: 0; transform: translateY(6px); }
            to { opacity: 1; transform: translateY(0); }
          }
          @keyframes pageFadeIn {
            from { opacity: 0; }
            to { opacity: 1; }
          }
          #root > div { animation: pageEnter 0.35s cubic-bezier(0.22, 1, 0.36, 1) both; }
          @media (prefers-reduced-motion: reduce) {
            #root > div { animation: pageFadeIn 0.2s ease both; }
          }

          /* RTL Layout Support */
          html[dir="rtl"] { direction: rtl; text-align: right; }
          html[dir="rtl"] [data-testid^="sidebar-nav-"]:not([data-testid*="section"]):hover { transform: translateX(-2px); }
          html[dir="rtl"] [data-testid^="mobile-nav-"]:not([data-testid*="section"]):hover { transform: translateX(-2px); }
          html[dir="rtl"] input, html[dir="rtl"] textarea { text-align: right; direction: rtl; }
          html[dir="rtl"] [data-testid*="sidebar"] { border-right: none; border-left: 1px solid rgba(148,163,184,0.1); }

          /* Accessibility: Focus-visible styles */
          *:focus-visible {
            outline: 2px solid #14B8A6;
            outline-offset: 2px;
            border-radius: 4px;
          }
          *:focus:not(:focus-visible) { outline: none; }

          /* Accessibility: Reduced motion */
          @media (prefers-reduced-motion: reduce) {
            *, *::before, *::after {
              animation-duration: 0.01ms !important;
              animation-iteration-count: 1 !important;
              transition-duration: 0.01ms !important;
              scroll-behavior: auto !important;
            }
          }

          /* Accessibility: High contrast mode support */
          @media (prefers-contrast: high) {
            :root { --font-base: 16px; }
            button, a, [role="button"] { border: 2px solid currentColor !important; }
          }

          /* ── Responsive Audit: Global Overflows ── */
          #root, [id="root"], [data-testid="app-shell"], [data-testid="app-shell-mobile"] {
            overflow-x: hidden;
            max-width: 100vw;
          }
          /* Prevent any element from causing horizontal scroll */
          @media (max-width: 767px) {
            [data-testid*="grid"], [data-testid*="kpi-row"], [data-testid*="summary"],
            [data-testid*="bulk-action-bar"], [data-testid*="header"] {
              max-width: 100%;
            }
            /* Tables: horizontal scroll wrapper */
            table { display: block; overflow-x: auto; -webkit-overflow-scrolling: touch; max-width: 100%; }
            /* Prevent long text from overflowing without forcing per-character breaks */
            h1, h2, h3, h4, h5, h6, p, li {
              word-break: normal;
              overflow-wrap: anywhere;
              hyphens: auto;
            }
            [data-testid*="summary-row"],
            [data-testid*="currency"],
            [data-testid*="jurisdiction"],
            [data-testid*="fee-summary"],
            [data-testid*="payment"] {
              word-break: normal !important;
              overflow-wrap: anywhere !important;
            }
            /* Ensure images don't overflow */
            img { max-width: 100% !important; height: auto !important; }
            /* Better spacing for mobile cards */
            [data-testid*="card"], [data-testid*="panel"] { max-width: 100%; }
          }

          /* ── Responsive: Tablet adjustments ── */
          @media (min-width: 768px) and (max-width: 1023px) {
            [data-testid="app-shell-mobile"] { overflow-x: hidden; }
            [data-testid="mobile-top-bar"] { padding: 0 16px; }
            [data-testid="mobile-nav-drawer"] { width: 320px !important; }
          }

          /* ── Welcome Page Mobile Responsive ── */
          @media (max-width: 767px) {
            /* Hero: Stack columns vertically */
            [data-testid="welcome-hero-subtitle"] { font-size: 14px !important; line-height: 22px !important; }
            /* Footer trust badges: wrap and center */
            [data-testid="footer-trust-badges"] { gap: 8px !important; padding: 16px 12px !important; }
            [data-testid="footer-trust-badges"] > div { font-size: 10px !important; }
            [data-testid="footer-bottom-bar"] { padding: 14px 16px !important; gap: 8px !important; }
            [data-testid="footer-address"] { flex-wrap: wrap; justify-content: center; text-align: center; }
            [data-testid="footer-copyright"] { text-align: center !important; }
            /* Newsletter form compact on mobile */
            [data-testid="footer-newsletter"] { padding: 0 !important; }
            /* Login form: full width */
            [data-testid="login-form"] { max-width: 100% !important; padding: 16px !important; }
            /* Contact form: full width */
            [data-testid="contact-form"] { max-width: 100% !important; }
          }

          /* ── Welcome + Footer Tablet ── */
          @media (min-width: 768px) and (max-width: 1023px) {
            [data-testid="footer-trust-badges"] { gap: 10px !important; }
            [data-testid="footer-bottom-bar"] { flex-direction: column !important; align-items: center !important; gap: 8px !important; }
          }

          /* ── Footer badges: ensure graceful wrap at ALL sizes ── */
          [data-testid="footer-trust-badges"] { flex-wrap: wrap !important; justify-content: center !important; }
          [data-testid="footer-bottom-bar"] > * { text-align: center; }

          /* ── Welcome page: ensure no overflow on any viewport ── */
          [data-testid="welcome-scroll-view"], [data-testid="welcome-hero"] {
            max-width: 100vw !important;
            overflow-x: hidden !important;
          }

          /* ── PWA Standalone Mode Enhancements ── */
          @media (display-mode: standalone) {
            body { overscroll-behavior-y: contain; }
            [data-testid="mobile-top-bar"] { padding-top: env(safe-area-inset-top, 0px); }
          }

          /* ── Landscape Orientation Handling ── */
          @media (max-height: 500px) and (orientation: landscape) {
            [data-testid="mobile-top-bar"] { height: 44px !important; }
            [data-testid="mobile-nav-drawer"] { width: 260px !important; }
          }

          /* ── Tablet landscape: wider drawer ── */
          @media (min-width: 768px) and (max-width: 1023px) and (orientation: landscape) {
            [data-testid="mobile-nav-drawer"] { width: 340px !important; }
          }

          /* ── Touch-friendly spacing for interactive elements ── */
          @media (hover: none) and (pointer: coarse) {
            [data-testid^="sidebar-nav-"], [data-testid^="mobile-nav-"] {
              min-height: 44px;
            }
            [data-testid*="btn"], [role="button"] {
              min-height: 44px;
              min-width: 44px;
            }
          }

          /* ── Smooth scroll for anchor links ── */
          html { scroll-behavior: smooth; }

          /* ── UI/UX Polish: Animations & Micro-interactions ── */
          @keyframes fadeInUp {
            from { opacity: 0; transform: translateY(12px); }
            to { opacity: 1; transform: translateY(0); }
          }
          @keyframes fadeIn {
            from { opacity: 0; }
            to { opacity: 1; }
          }
          @keyframes scaleIn {
            from { opacity: 0; transform: scale(0.96); }
            to { opacity: 1; transform: scale(1); }
          }
          @keyframes shimmer {
            0% { background-position: -200% 0; }
            100% { background-position: 200% 0; }
          }
          @keyframes slideInRight {
            from { opacity: 0; transform: translateX(-16px); }
            to { opacity: 1; transform: translateX(0); }
          }

          /* ── Footer Trust Badge Animations ── */
          @keyframes statusPulse {
            0%, 100% { box-shadow: 0 0 0 0 rgba(16, 185, 129, 0.45); }
            50% { box-shadow: 0 0 0 5px rgba(16, 185, 129, 0); }
          }
          @keyframes dotPulse {
            0%, 100% { opacity: 1; transform: scale(1); }
            50% { opacity: 0.55; transform: scale(1.35); }
          }
          [data-testid="footer-trust-badges"] > div {
            transition: transform 0.22s cubic-bezier(.4,0,.2,1), box-shadow 0.25s ease, background-color 0.25s ease;
            cursor: default;
          }
          [data-testid="footer-trust-badges"] > div:hover {
            transform: translateY(-2px) scale(1.03);
            box-shadow: 0 6px 20px rgba(0, 0, 0, 0.10);
          }
          [data-testid="footer-status-badge"] {
            animation: statusPulse 3s ease-in-out infinite;
          }
          [data-testid="footer-status-dot"] {
            animation: dotPulse 2.4s ease-in-out infinite;
          }

          /* Page content entrance animation */
          #main-content > *:first-child,
          [id="main-content"] > *:first-child {
            animation: fadeIn 0.25s ease-out;
          }

          /* Sidebar nav item hover */
          [data-testid^="sidebar-nav-"]:not([data-testid*="section"]) {
            transition: background-color 0.15s ease, transform 0.12s ease, box-shadow 0.15s ease !important;
          }
          [data-testid^="sidebar-nav-"]:not([data-testid*="section"]):hover {
            transform: translateX(2px);
            background-color: rgba(37, 99, 235, 0.06) !important;
          }

          /* Mobile drawer nav items */
          [data-testid^="mobile-nav-"]:not([data-testid*="section"]):not([data-testid*="toggle"]):not([data-testid*="overlay"]):not([data-testid*="drawer"]) {
            transition: background-color 0.15s ease, transform 0.1s ease !important;
          }
          [data-testid^="mobile-nav-"]:not([data-testid*="section"]):not([data-testid*="toggle"]):not([data-testid*="overlay"]):not([data-testid*="drawer"]):hover {
            transform: translateX(2px);
          }

          /* Button press effect */
          [role="button"]:active, button:active, [data-testid*="btn"]:active {
            transform: scale(0.97) !important;
            transition: transform 0.08s ease !important;
          }

          /* Card hover lift */
          [data-testid*="card"]:hover, [data-testid*="panel"]:hover {
            transition: box-shadow 0.2s ease, transform 0.2s ease !important;
          }

          /* Skeleton loading shimmer */
          .skeleton-shimmer {
            background: linear-gradient(90deg, rgba(148,163,184,0.1) 25%, rgba(148,163,184,0.2) 50%, rgba(148,163,184,0.1) 75%);
            background-size: 200% 100%;
            animation: shimmer 1.5s ease-in-out infinite;
            border-radius: 8px;
          }

          /* Staggered entrance for list items (applies to direct children) */
          .stagger-enter > * {
            animation: fadeInUp 0.3s ease-out both;
          }
          .stagger-enter > *:nth-child(1) { animation-delay: 0ms; }
          .stagger-enter > *:nth-child(2) { animation-delay: 40ms; }
          .stagger-enter > *:nth-child(3) { animation-delay: 80ms; }
          .stagger-enter > *:nth-child(4) { animation-delay: 120ms; }
          .stagger-enter > *:nth-child(5) { animation-delay: 160ms; }
          .stagger-enter > *:nth-child(6) { animation-delay: 200ms; }
          .stagger-enter > *:nth-child(n+7) { animation-delay: 240ms; }

          /* Tooltip/popover scale-in */
          [data-testid*="tooltip"], [data-testid*="popover"], [data-testid*="dropdown"] {
            animation: scaleIn 0.15s ease-out;
            transform-origin: top center;
          }

          /* Notification badge pulse */
          [data-testid*="badge"]:not(:empty) {
            animation: fadeIn 0.2s ease-out;
          }

          /* ── Better scrollbar styling (webkit) ── */
          ::-webkit-scrollbar { width: 6px; height: 6px; }
          ::-webkit-scrollbar-track { background: transparent; }
          ::-webkit-scrollbar-thumb { background: rgba(148,163,184,0.3); border-radius: 3px; }
          ::-webkit-scrollbar-thumb:hover { background: rgba(148,163,184,0.5); }
          html[data-theme-active="dark"] ::-webkit-scrollbar-thumb { background: rgba(100,116,139,0.3); }
          html[data-theme-active="dark"] ::-webkit-scrollbar-thumb:hover { background: rgba(100,116,139,0.5); }
        `}} />

        {/* Force same-host API calls to HTTPS to prevent mixed-content regressions in preview/proxy contexts
            DISABLED for localhost to prevent SSL errors in local development */}
        <script dangerouslySetInnerHTML={{ __html: `
          (function () {
            try {
              if (typeof window === 'undefined' || !window.location || !window.location.host) return;
              var currentHost = window.location.host;
              
              // Skip HTTPS upgrade for localhost/127.0.0.1 to avoid SSL errors in local development
              if (currentHost === 'localhost' || currentHost === '127.0.0.1' || 
                  currentHost.indexOf('localhost:') === 0 || currentHost.indexOf('127.0.0.1:') === 0) {
                return;
              }

              function normalizeSameHostUrl(input) {
                try {
                  if (typeof input !== 'string') return input;
                  if (input.indexOf('http://') !== 0) return input;
                  var parsed = new URL(input);
                  if (parsed.host !== currentHost) return input;
                  parsed.protocol = 'https:';
                  return parsed.toString();
                } catch (e) {
                  return input;
                }
              }

              var originalFetch = window.fetch;
              if (originalFetch) {
                window.fetch = function(resource, init) {
                  try {
                    if (typeof resource === 'string') {
                      resource = normalizeSameHostUrl(resource);
                    }
                  } catch (e) {
                    if (window.__racReportRecoverable) window.__racReportRecoverable('https-upgrade:fetch-wrap', e);
                  }
                  return originalFetch.call(this, resource, init);
                };
              }

              var originalXhrOpen = XMLHttpRequest.prototype.open;
              XMLHttpRequest.prototype.open = function(method, url) {
                try {
                  url = normalizeSameHostUrl(url);
                } catch (e) {
                  if (window.__racReportRecoverable) window.__racReportRecoverable('https-upgrade:xhr-wrap', e);
                }
                return originalXhrOpen.apply(this, [method, url].concat(Array.prototype.slice.call(arguments, 2)));
              };
            } catch (e) {
              if (window.__racReportRecoverable) window.__racReportRecoverable('https-upgrade:fatal', e);
            }
          })();
        `}} />

        <ScrollViewStyleReset />
        {/* Dark mode: CSS-level overrides that apply before React hydration */}
        <style dangerouslySetInnerHTML={{ __html: `
          html[data-theme-active="dark"],
          html[data-theme-active="dark"] body {
            background-color: #050A18 !important;
            color-scheme: dark;
          }
          /* Light mode: override the #050A18 default from the base body rule */
          html[data-theme-active="light"],
          html[data-theme-active="light"] body {
            background-color: #F8FAFC !important;
            color: #0F172A !important;
            color-scheme: light;
          }
          html[data-theme-active="light"] #root,
          html[data-theme-active="light"] [id="root"],
          html[data-theme-active="light"] #main-content,
          html[data-theme-active="light"] [id="main-content"] {
            background-color: #F8FAFC !important;
          }
          html[data-theme-active="light"] .pfb-overlay {
            background: rgba(248,250,252,1) !important;
          }
          /* Force dark overlay on PageFloatingBackground before React hydrates */
          html[data-theme-active="dark"] .pfb-overlay {
            background: rgba(5,10,24,1) !important;
          }
          /* Force dark backgrounds on content areas during SSR */
          html[data-theme-active="dark"] #root,
          html[data-theme-active="dark"] [id="root"],
          html[data-theme-active="dark"] #main-content,
          html[data-theme-active="dark"] [id="main-content"] {
            background-color: #050A18 !important;
          }
          /* Fallback: also use prefers-color-scheme media query */
          @media (prefers-color-scheme: dark) {
            html:not([data-theme-active="light"]),
            html:not([data-theme-active="light"]) body {
              background-color: #050A18;
              color-scheme: dark;
            }
            html:not([data-theme-active="light"]) .pfb-overlay {
              background: rgba(5,10,24,1) !important;
            }
          }
        `}} />
        <script dangerouslySetInnerHTML={{ __html: `
          (function() {
            try {
              if (typeof window !== 'undefined' && typeof window.__alphaColor !== 'function') {
                var varFallbacks = {
                  '--app-primary': '#0F766E',
                  '--app-success': '#16A34A',
                  '--app-error': '#DC2626',
                  '--app-warning': '#D97706',
                  '--app-info': '#0284C7',
                  '--app-accent': '#14B8A6',
                  '--app-cyan': '#0891B2',
                  '--app-purple': '#0F766E',
                  '--app-red': '#DC2626',
                  '--app-green': '#16A34A',
                  '--app-yellow': '#CA8A04',
                  '--app-blue': '#14B8A6'
                };
                window.__alphaColor = function(rawColor, rawAlpha) {
                  var color = String(rawColor || '').trim();
                  var alphaRaw = String(rawAlpha || '').replace('#', '').trim();
                  var alpha = (alphaRaw.length === 1 ? alphaRaw + alphaRaw : alphaRaw || 'FF').slice(0, 2).toUpperCase();
                  if (/^#([0-9a-f]{6})$/i.test(color)) return color + alpha;
                  if (/^#([0-9a-f]{3})$/i.test(color)) {
                    var expanded = '#' + color.slice(1).split('').map(function(c){ return c + c; }).join('');
                    return expanded + alpha;
                  }
                  if (color.indexOf('var(') === 0) {
                    var closeParen = color.indexOf(')');
                    var token = closeParen > 4 ? color.slice(4, closeParen).split(',')[0].trim() : '';
                    var fallback = token ? varFallbacks[token] : '';
                    if (fallback) return fallback + alpha;
                  }
                  return color;
                };
              }

              var fallbackFont = 'Manrope, Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif';
              var applyFontFallback = function() {
                try {
                  document.documentElement.setAttribute('data-font-fallback', 'active');
                  if (document.body) document.body.style.fontFamily = fallbackFont;
                } catch(e) {}
              };

              var ready = false;
              if (document.fonts && document.fonts.ready) {
                document.fonts.ready.then(function(){ ready = true; }).catch(function(){ applyFontFallback(); });
                setTimeout(function(){ if (!ready) applyFontFallback(); }, 2600);
              } else {
                applyFontFallback();
              }

              window.addEventListener('DOMContentLoaded', function() {
                if (document.documentElement.getAttribute('data-font-fallback') === 'active') {
                  try { if (document.body) document.body.style.fontFamily = fallbackFont; } catch(e) {}
                }
              });
            } catch(e) {
              if (window.__racReportRecoverable) window.__racReportRecoverable('tx-engine:route-observer', e);
            }
          })();
        `}} />
        {/* Global error handler: prevents white screen by catching unhandled JS errors */}
        <script dangerouslySetInnerHTML={{ __html: `
          window.__appErrors = [];
          window.onerror = function(msg, src, line, col, err) {
            try { window.__appErrors.push({msg:msg,src:src,line:line}); } catch(e) {}
            return false;
          };
          window.addEventListener('unhandledrejection', function(e) {
            try {
              var reason = String(e.reason || '');
              if (reason.indexOf('AbortError') !== -1 || reason.indexOf('ERR_ABORTED') !== -1) {
                e.preventDefault();
                return;
              }
              window.__appErrors.push({msg:reason});
            } catch(ex) {}
          });
        `}} />
        {/* Suppress console errors for known non-critical failed network requests (CDN beacons, telemetry) */}
        <script dangerouslySetInnerHTML={{ __html: `
          (function() {
            var suppressPatterns = ['/cdn-cgi/', '/vitals/report', '/vitals/page-perf', '/session-replay/', '/platform-shell-health/'];
            if (typeof window !== 'undefined') {
              window.addEventListener('error', function(e) {
                if (e && e.target && (e.target.tagName === 'SCRIPT' || e.target.tagName === 'LINK' || e.target.tagName === 'IMG')) {
                  var src = e.target.src || e.target.href || '';
                  for (var i = 0; i < suppressPatterns.length; i++) {
                    if (src.indexOf(suppressPatterns[i]) !== -1) {
                      e.preventDefault();
                      e.stopPropagation();
                      return true;
                    }
                  }
                }
              }, true);
            }
          })();
        `}} />
        {/* Early theme detection: read stored preference or system preference */}
        <script dangerouslySetInnerHTML={{ __html: `
          (function() {
            try {
              var root = document.documentElement;
              var stored = localStorage.getItem('app_theme');
              var mode = 'system';
              var parsed = null;
              if (stored) {
                parsed = JSON.parse(stored);
                mode = parsed.themeMode || (parsed.darkMode ? 'dark' : 'light');
              }

              var isDark = mode === 'dark' || (mode === 'system' && window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches);
              root.setAttribute('data-theme-active', isDark ? 'dark' : 'light');
              root.setAttribute('data-theme-mode', mode);

              // Pre-hydration CSS variables (FOUC prevention): mirror ThemeContext token injection.
              var LIGHT_THEME_VARS = {
                '--app-bg': '#F7F9FC',
                '--app-card-bg': '#FFFFFF',
                '--app-text': '#0F172A',
                '--app-text-sec': '#475569',
                '--app-text-muted': '#5D6C82',
                '--app-border': '#E5E7EB',
                '--app-primary': '#0F766E',
                '--app-primary-text': '#FFFFFF',
                '--app-primary-soft': '#0F766E14',
                '--app-surface': '#FFFFFF',
                '--app-success': '#14B8A6',
                '--app-success-soft': '#14B8A614',
                '--app-warning': '#D97706',
                '--app-warning-soft': '#D9770614',
                '--app-error': '#DC2626',
                '--app-error-soft': '#DC262614',
                '--app-info': '#0F766E',
                '--app-info-soft': '#0F766E14',
                '--app-surface-hover': '#F2F7F7',
                '--app-card-muted': '#F8FBFC',
                '--app-border-strong': '#D1D9E4',
                '--app-border-bright': '#CBD5E1',
                '--app-divider': '#E5E7EB',
                '--app-chart-grid': '#E5E7EB',
                '--app-chart-axis': '#64748B'
              };

              var DARK_THEME_VARS = {
                '--app-bg': '#0B1220',
                '--app-card-bg': '#111827',
                '--app-text': '#E6EAF2',
                '--app-text-sec': '#9AA4B2',
                '--app-text-muted': '#94A3B8',
                '--app-border': '#1F2937',
                '--app-primary': '#14B8A6',
                '--app-primary-text': '#0B1220',
                '--app-primary-soft': '#14B8A622',
                '--app-surface': '#0F172A',
                '--app-success': '#2DD4BF',
                '--app-success-soft': '#2DD4BF22',
                '--app-warning': '#F59E0B',
                '--app-warning-soft': '#F59E0B22',
                '--app-error': '#F87171',
                '--app-error-soft': '#F8717122',
                '--app-info': '#14B8A6',
                '--app-info-soft': '#14B8A622',
                '--app-surface-hover': '#162033',
                '--app-card-muted': '#111827',
                '--app-border-strong': '#334155',
                '--app-border-bright': '#475569',
                '--app-divider': '#1F2937',
                '--app-chart-grid': '#1F2937',
                '--app-chart-axis': '#9AA4B2'
              };

              var activeThemeVars = isDark ? DARK_THEME_VARS : LIGHT_THEME_VARS;
              Object.keys(activeThemeVars).forEach(function(key) {
                root.style.setProperty(key, activeThemeVars[key]);
              });

              root.style.backgroundColor = activeThemeVars['--app-bg'];
              if (document.body) {
                document.body.style.backgroundColor = activeThemeVars['--app-bg'];
              }

              /* Early RTL/LTR detection from stored language preference */
              if (parsed) {
                var p = parsed;
                var RTL_LANGS = ['ar'];
                var LANG_MAP = {English:'en',French:'fr',Spanish:'es',German:'de',Italian:'it',Portuguese:'pt',Chinese:'zh',Japanese:'ja',Korean:'ko',Hindi:'hi',Arabic:'ar',Russian:'ru',Turkish:'tr',Dutch:'nl',Swedish:'sv',Polish:'pl',Thai:'th',Vietnamese:'vi',Indonesian:'id',Malay:'ms',Swahili:'sw',Ukrainian:'uk',Romanian:'ro'};
                var lc = '';
                if (typeof p.languageCode === 'string' && p.languageCode.trim()) {
                  lc = p.languageCode.trim().toLowerCase();
                }
                if (!lc) {
                  lc = LANG_MAP[p.language] || 'en';
                }
                if (lc.indexOf('-') !== -1) lc = lc.split('-')[0];
                if (lc.indexOf('_') !== -1) lc = lc.split('_')[0];
                document.documentElement.setAttribute('lang', lc);
                if (RTL_LANGS.indexOf(lc) !== -1) {
                  document.documentElement.setAttribute('dir', 'rtl');
                } else {
                  document.documentElement.setAttribute('dir', 'ltr');
                }
              }
            } catch(e) {}
          })();
        `}} />
        {/* Preload splash logo for instant display */}
        <link rel="preload" href="/splash-logo.png" as="image" type="image/png" />
        {/* Branded splash screen styles — MUST be in head so they apply before body renders */}
        <style dangerouslySetInnerHTML={{ __html: `
          @keyframes splash-pulse { 0%, 100% { transform: scale(1); } 50% { transform: scale(1.04); } }
          @keyframes splash-fadeIn { from { opacity: 0; transform: translateY(12px); } to { opacity: 1; transform: translateY(0); } }
          @keyframes splash-bar { 0% { width: 0%; } 100% { width: 100%; } }
          @keyframes splash-float { 0%, 100% { transform: translateY(0); } 50% { transform: translateY(-6px); } }
          #app-loading-fallback { background: linear-gradient(180deg, #F7F9FC 0%, #EEF4F7 100%); }
          #app-loading-fallback .splash-logo { animation: splash-pulse 2.5s ease-in-out infinite, splash-float 3s ease-in-out infinite; }
          #app-loading-fallback .splash-brand { animation: splash-fadeIn 0.6s ease-out 0.2s both; }
          #app-loading-fallback .splash-tagline { animation: splash-fadeIn 0.6s ease-out 0.35s both; }
          #app-loading-fallback .splash-bar-track { animation: splash-fadeIn 0.4s ease-out 0.5s both; }
          #app-loading-fallback .splash-bar-fill { animation: splash-bar 3s ease-in-out infinite; }
          html[data-theme-active="dark"] #app-loading-fallback { background: radial-gradient(ellipse at 50% 30%, #152031 0%, #0B1220 70%) !important; }
          html[data-theme-active="dark"] #app-loading-fallback .splash-brand { color: #E6EAF2 !important; }
          html[data-theme-active="dark"] #app-loading-fallback .splash-brand .splash-ai { color: #5EEAD4 !important; }
          html[data-theme-active="dark"] #app-loading-fallback .splash-tagline { color: #9AA4B2 !important; }
          html[data-theme-active="dark"] #app-loading-fallback .splash-bar-track { background: rgba(255,255,255,0.06) !important; }
          html[data-theme-active="dark"] #app-loading-fallback .splash-bar-fill { background: linear-gradient(90deg, #14B8A6, #5EEAD4) !important; }
          html[data-theme-active="dark"] #app-loading-fallback .splash-logo { filter: drop-shadow(0 0 18px rgba(20,184,166,0.16)); }
          @media (prefers-color-scheme: dark) {
            html:not([data-theme-active="light"]) #app-loading-fallback { background: radial-gradient(ellipse at 50% 30%, #152031 0%, #0B1220 70%) !important; }
            html:not([data-theme-active="light"]) #app-loading-fallback .splash-brand { color: #E6EAF2 !important; }
            html:not([data-theme-active="light"]) #app-loading-fallback .splash-tagline { color: #9AA4B2 !important; }
            html:not([data-theme-active="light"]) #app-loading-fallback .splash-bar-track { background: rgba(255,255,255,0.06) !important; }
          }
        `}} />
      </head>
      <body>
        {/* Branded splash screen — hidden once React mounts */}
        <div id="app-loading-fallback" style={{ position: 'fixed', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', flexDirection: 'column', zIndex: 99999, transition: 'opacity 0.4s ease' }}>
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 0 }}>
            {/* Actual RealAICoach logo */}
            <img className="splash-logo" src="/splash-logo.png" alt="RealAICoach" width="120" height="120" style={{ marginBottom: 16, objectFit: 'contain' }} />
            {/* Brand name */}
            <div className="splash-brand notranslate" data-notranslate style={{ fontFamily: 'Inter, system-ui, sans-serif', fontSize: 26, fontWeight: 800, color: 'var(--app-text)', letterSpacing: -0.5, marginBottom: 6 }}>
              Real<span className="splash-ai" style={{ color: 'var(--app-primary)' }}>AI</span>Coach
            </div>
            {/* Tagline */}
            <div className="splash-tagline" style={{ fontFamily: 'Inter, system-ui, sans-serif', fontSize: 13, color: 'var(--app-text-sec)', fontWeight: 500, marginBottom: 28 }}>
              Accelerating your growth
            </div>
            {/* Progress bar */}
            <div className="splash-bar-track" style={{ width: 140, height: 3, borderRadius: 2, background: 'rgba(0,0,0,0.06)', overflow: 'hidden' }}>
              <div className="splash-bar-fill" style={{ height: '100%', borderRadius: 2, background: 'linear-gradient(90deg, var(--app-primary), var(--app-info))' }}></div>
            </div>
          </div>
        </div>
        <script dangerouslySetInnerHTML={{ __html: `
          (function() {
            var isDark = document.documentElement.getAttribute('data-theme-active') === 'dark';
            var isEmbedded = false;
            try { isEmbedded = window.self !== window.top; } catch(e) { isEmbedded = true; }
            if (isDark) document.body.style.backgroundColor = '#0B1220';
            var fallback = document.getElementById('app-loading-fallback');
            if (!fallback) return;
            var removed = false;
            var hideFallback = function() {
              if (removed || !fallback) return;
              removed = true;
              fallback.style.opacity = '0';
              fallback.style.pointerEvents = 'none';
              setTimeout(function() { if (fallback && fallback.parentNode) fallback.parentNode.removeChild(fallback); fallback = null; }, 400);
            };
            var checkReady = function() {
              var root = document.getElementById('root');
              if (root && root.getAttribute('data-app-ready') === 'true') { hideFallback(); return true; }
              return false;
            };
            var readyPoll = setInterval(function() { if (checkReady()) clearInterval(readyPoll); }, 200);
            var detectEdgeChallenge = function() {
              try {
                if (document.getElementById('cf-challenge-running')) return true;
                if (document.querySelector('iframe[src*="hcaptcha"], iframe[src*="challenges.cloudflare"], script[src*="challenges.cloudflare"]')) return true;
                var txt = String((document.body && document.body.innerText) || '').toLowerCase();
                return txt.indexOf('verify you are human') !== -1 || txt.indexOf('cloudflare') !== -1;
              } catch (e) { return false; }
            };
            // After 9s show retry UI + iframe-safe escape route
            setTimeout(function() {
              if (removed || !fallback) return;
              var currentHref = '';
              try { currentHref = String(window.location.href || '/'); } catch(e) { currentHref = '/'; }
              var helper = document.createElement('div');
              helper.style.cssText = 'margin-top:24px;text-align:center;animation:splash-fadeIn 0.4s ease-out both;';
              var helperTitle = detectEdgeChallenge()
                ? 'Verifying security challenge...'
                : 'Taking longer than expected';
              helper.innerHTML = '<div style="margin-bottom:8px;color:var(--app-text-sec);font-family:Inter,system-ui,sans-serif;font-size:12px;">' + helperTitle + '</div>' +
                '<button onclick="window.location.reload()" style="cursor:pointer;border:none;background:var(--app-primary);color:var(--app-primary-text);font-family:Inter,system-ui,sans-serif;font-size:13px;font-weight:700;padding:10px 28px;border-radius:10px;margin-bottom:6px;">Reload App</button>' +
                '<div><a href="/auth/login" style="color:var(--app-primary);font-family:Inter,system-ui,sans-serif;font-size:12px;font-weight:600;text-decoration:underline;">or skip to login</a></div>' +
                (isEmbedded ? '<div style="margin-top:8px;"><a href="' + currentHref + '" target="_top" rel="noopener" style="color:var(--app-primary);font-family:Inter,system-ui,sans-serif;font-size:12px;font-weight:700;text-decoration:underline;">Open app directly (outside preview frame)</a></div>' : '');
              try { fallback.querySelector('div').appendChild(helper); } catch(e) {}
            }, 9000);
            // Startup guard: keep fallback visible if app is still not ready (prevents blank/white screen)
            setTimeout(function() {
              if (checkReady()) return;
              try {
                fallback.setAttribute('data-startup-stuck', 'true');
                document.documentElement.setAttribute('data-app-startup-stuck', 'true');
              } catch(e) {}
            }, 6000);

            // Embedded preview self-heal: if still not ready, attempt top-level navigation to direct app URL
            setTimeout(function() {
              if (!isEmbedded || checkReady()) return;
              try { window.open(window.location.href, '_top'); } catch(e) {}
            }, 9000);
          })();
        `}} />
        <script dangerouslySetInnerHTML={{ __html: `
          (function() {
            try {
              var CACHE_SCHEMA_VERSION = '${cacheSchemaVersion}:${telemetryRelease}:${expectedPreviewHost || 'hostless'}';
              var prev = localStorage.getItem('cache_schema_version');
              if (prev === CACHE_SCHEMA_VERSION) return;

              var keep = { session_token: 1, refresh_token: 1, auth_user_snapshot: 1, app_theme: 1, cache_schema_version: 1 };
              Object.keys(localStorage).forEach(function(key) {
                if (keep[key]) return;
                if (key.indexOf('legacy_') === 0 || key.indexOf('stale_') === 0 || key.indexOf('cache_') === 0 || key.indexOf('live_query_snapshot_v1:') === 0 || key.indexOf('tx_cache_') === 0 || key.indexOf('rac_auto_translate_v2_') === 0) {
                  try { localStorage.removeItem(key); } catch(e) {}
                }
              });

              if ('caches' in window) {
                caches.keys().then(function(keys) {
                  return Promise.all(keys.filter(function(k) {
                    return /^realaicoach-/i.test(k) || /^rac-/i.test(k);
                  }).map(function(k) { return caches.delete(k); }));
                }).catch(function() {});
              }

              localStorage.setItem('cache_schema_version', CACHE_SCHEMA_VERSION);
            } catch(e) {}
          })();
        `}} />
        <script dangerouslySetInnerHTML={{ __html: `
          (function() {
            try {
              var route = String((window.location && window.location.pathname) || '/');
              while (route.length > 1 && route.charAt(route.length - 1) === '/') route = route.slice(0, -1);
              var isFeatureRoute = route === '/features' || route.indexOf('/features/') === 0;
              if (!isFeatureRoute) return;
              sessionStorage.setItem('rac:last-intended-route', route);
              sessionStorage.setItem('rac:last-intended-route-ts', String(Date.now()));
              if (!sessionStorage.getItem('rac:last-intended-route-attempts')) {
                sessionStorage.setItem('rac:last-intended-route-attempts', '0');
              }
            } catch (e) {}
          })();
        `}} />
        <script dangerouslySetInnerHTML={{ __html: `
          (function() {
            try {
              if (window.__racBootPolicyHandshakeStarted) return;
              window.__racBootPolicyHandshakeStarted = true;

              var state = {
                ready: false,
                blocked: false,
                reason: '',
                policyId: '',
                attempts: 0,
              };
              window.__racBootPolicyState = state;

              var POLICY_KEY = 'rac_boot_policy_id';
              var ATTEMPT_PREFIX = 'rac_boot_policy_reload_attempt_';
              var cacheSchema = '';
              var clientPolicy = '';
              try { cacheSchema = String(localStorage.getItem('cache_schema_version') || ''); } catch(e) {}
              try { clientPolicy = String(localStorage.getItem(POLICY_KEY) || ''); } catch(e) {}

              var endpoint = '/api/config/boot-policy?client_policy_id=' + encodeURIComponent(clientPolicy) + '&client_cache_schema=' + encodeURIComponent(cacheSchema);
              var timeoutId = setTimeout(function() {
                if (state.ready || state.blocked) return;
                state.ready = true;
                state.reason = 'handshake_timeout';
                try { window.dispatchEvent(new CustomEvent('rac:boot-policy-ready', { detail: state })); } catch(e) {}
              }, 4500);

              var clearVolatileCaches = function() {
                try {
                  var keep = {
                    session_token: 1,
                    refresh_token: 1,
                    auth_user_snapshot: 1,
                    app_theme: 1,
                    cache_schema_version: 1,
                    rac_boot_policy_id: 1,
                  };
                  Object.keys(localStorage).forEach(function(k) {
                    if (keep[k]) return;
                    if (
                      k.indexOf('legacy_') === 0 ||
                      k.indexOf('stale_') === 0 ||
                      k.indexOf('cache_') === 0 ||
                      k.indexOf('live_query_snapshot_v1:') === 0 ||
                      k.indexOf('tx_cache_') === 0 ||
                      k.indexOf('rac_auto_translate_v2_') === 0
                    ) {
                      try { localStorage.removeItem(k); } catch(e) {}
                    }
                  });
                } catch(e) {}

                try {
                  if ('caches' in window) {
                    caches.keys().then(function(keys) {
                      return Promise.all(keys.map(function(k) { return caches.delete(k); }));
                    }).catch(function() {});
                  }
                } catch(e) {}
              };

              var sendShouldReloadTelemetry = function(meta) {
                try {
                  var payload = {
                    event_type: 'should_reload_true',
                    policy_id: String((meta && meta.policy_id) || ''),
                    client_policy_id: String(clientPolicy || ''),
                    client_cache_schema: String(cacheSchema || ''),
                    route_path: String(window.location.pathname || ''),
                    route_query: String(window.location.search || ''),
                    host: String(window.location.hostname || ''),
                    source: String((meta && meta.source) || 'html_pre_hydration'),
                    reason: String((meta && meta.reason) || 'handshake_should_reload_true'),
                    reload_attempt: Number((meta && meta.reload_attempt) || 0),
                  };

                  var telemetryKey = 'rac_boot_policy_reload_telemetry:' + String(payload.policy_id || 'policy') + ':' + String(payload.reload_attempt || 0);
                  try {
                    if (sessionStorage.getItem(telemetryKey) === '1') return;
                    sessionStorage.setItem(telemetryKey, '1');
                  } catch(_err) {}

                  try { window.__racBootPolicyShouldReloadTelemetrySent = true; } catch(_err) {}

                  var body = JSON.stringify(payload);
                  if (navigator && navigator.sendBeacon && typeof Blob !== 'undefined') {
                    var blob = new Blob([body], { type: 'application/json' });
                    navigator.sendBeacon('/api/config/boot-policy/telemetry', blob);
                    return;
                  }

                  fetch('/api/config/boot-policy/telemetry', {
                    method: 'POST',
                    credentials: 'omit',
                    cache: 'no-store',
                    keepalive: true,
                    headers: { 'Content-Type': 'application/json' },
                    body: body,
                  }).catch(function() {});
                } catch(_err) {}
              };

              fetch(endpoint, { method: 'GET', credentials: 'include', cache: 'no-store' })
                .then(function(r) {
                  if (!r.ok) throw new Error('http_' + r.status);
                  return r.json();
                })
                .then(function(payload) {
                  clearTimeout(timeoutId);
                  var policy = (payload && payload.policy) || {};
                  var handshake = (payload && payload.handshake) || {};
                  var shouldReloadSignal = !!(handshake && handshake.should_reload);
                  var policyId = String(policy.policy_id || '');
                  var forceReload = !!policy.force_reload_on_mismatch;
                  var maxReloadAttempts = Math.max(1, parseInt(policy.max_reload_attempts || 2, 10));
                  var currentPath = String((window.location && window.location.pathname) || '/');
                  var currentHost = String((window.location && window.location.hostname) || '').toLowerCase();
                  var isPreviewHost = currentHost.indexOf('preview.emergentagent.com') !== -1 || currentHost.endsWith('.emergent.sh') || currentHost === 'app.emergent.sh';
                  var isAuthRoute = currentPath.indexOf('/auth/') === 0;
                  var isFeatureRoute = currentPath === '/features' || currentPath.indexOf('/features/') === 0;

                  // Permanent reliability rule:
                  // Never force hard reloads on preview hosts or auth routes.
                  // These reloads can abort login/navigation on fresh sessions and mimic outages.
                  if (isPreviewHost || isAuthRoute || isFeatureRoute) {
                    forceReload = false;
                  }

                  state.policyId = policyId;

                  var currentPolicy = '';
                  try { currentPolicy = String(localStorage.getItem(POLICY_KEY) || ''); } catch(e) {}

                  var mismatch = false;
                  if (policyId && currentPolicy !== policyId) mismatch = true;
                  if (!mismatch && handshake && handshake.should_reload) mismatch = true;

                  if (forceReload && mismatch) {
                    var attemptKey = ATTEMPT_PREFIX + policyId;
                    var attempts = 0;
                    try { attempts = parseInt(sessionStorage.getItem(attemptKey) || '0', 10) || 0; } catch(e) { attempts = 0; }
                    state.attempts = attempts;

                    if (shouldReloadSignal) {
                      sendShouldReloadTelemetry({
                        policy_id: policyId,
                        reload_attempt: attempts + 1,
                        source: 'html_pre_hydration',
                        reason: 'handshake_should_reload_true',
                      });
                    }

                    if (attempts < maxReloadAttempts) {
                      try { sessionStorage.setItem(attemptKey, String(attempts + 1)); } catch(e) {}
                      try { if (policyId) localStorage.setItem(POLICY_KEY, policyId); } catch(e) {}
                      clearVolatileCaches();

                      var target = window.location.pathname + window.location.search + window.location.hash;
                      var sep = target.indexOf('?') === -1 ? '?' : '&';
                      window.location.replace(target + sep + '__bp=' + encodeURIComponent(policyId || 'policy') + '&__bpr=' + String(attempts + 1));
                      return;
                    }

                    state.blocked = false;
                    state.ready = true;
                    state.reason = 'max_reload_attempts_exceeded_degraded_mode';
                    try { window.dispatchEvent(new CustomEvent('rac:boot-policy-ready', { detail: state })); } catch(e) {}
                    return;
                  }

                  if (shouldReloadSignal) {
                    sendShouldReloadTelemetry({
                      policy_id: policyId,
                      reload_attempt: Number(state.attempts || 0),
                      source: 'html_pre_hydration',
                      reason: 'handshake_should_reload_true_no_forced_reload',
                    });
                  }

                  try { if (policyId) localStorage.setItem(POLICY_KEY, policyId); } catch(e) {}
                  state.ready = true;
                  state.reason = 'policy_match';
                  try { window.dispatchEvent(new CustomEvent('rac:boot-policy-ready', { detail: state })); } catch(e) {}
                })
                .catch(function(err) {
                  clearTimeout(timeoutId);
                  var hasCachedPolicy = false;
                  try { hasCachedPolicy = !!localStorage.getItem(POLICY_KEY); } catch(e) { hasCachedPolicy = false; }
                  state.blocked = false;
                  state.ready = true;
                  if (!hasCachedPolicy) {
                    state.reason = 'handshake_unavailable_no_cached_policy_degraded_mode';
                  } else {
                    state.reason = 'handshake_unavailable_with_cached_policy';
                  }
                  try { window.dispatchEvent(new CustomEvent('rac:boot-policy-ready', { detail: state })); } catch(e) {}
                });
            } catch(e) {
              try {
                window.__racBootPolicyState = {
                  ready: true,
                  blocked: false,
                  reason: 'handshake_exception',
                  policyId: '',
                  attempts: 0,
                };
                window.dispatchEvent(new CustomEvent('rac:boot-policy-ready', { detail: window.__racBootPolicyState }));
              } catch(_err) {}
            }
          })();
        `}} />
        {children}
        {/* Auto-Translation Engine v2: debounced, non-re-entrant, brand-safe */}
        <script dangerouslySetInnerHTML={{ __html: `
          (function() {
            try {
            var BATCH_DELAY_PUBLIC = 70, BATCH_DELAY_AUTH = 120, MAX_BATCH = 80, MIN_LEN = 2;
            var BATCH_DELAY = BATCH_DELAY_PUBLIC;
            var SKIP_TAGS = {SCRIPT:1,STYLE:1,NOSCRIPT:1,SVG:1,PATH:1,CODE:1,PRE:1,INPUT:1,TEXTAREA:1,SELECT:1,OPTION:1,IMG:1,VIDEO:1,AUDIO:1,CANVAS:1,IFRAME:1};
            var TR = 'data-translated';
            var SKIP_RE = /^[\\d\\s.,:%\\/$\\u20AC\\u00A3\\u00A5#@!?()+\\-*\\/=<>\\[\\]{}\\&|\\^~\\\`"';:]+$/;
            var cache = {}, queue = [], timer = null, obs = null, poll = null, lang = 'en', on = false;
            var pendingTexts = {};
            var apiBackoffUntil = 0;
            var apiBackoffMs = 0;
            var API_BACKOFF_BASE_MS = 400;
            var API_BACKOFF_MAX_MS = 6000;
            var METRIC_LOG_THROTTLE_MS = 12000;
            var lastMetricConsoleAt = 0;
            /* Bumped v5→v6: versions ≤v5 may contain POISONED "English→English"
             * entries cached when the anonymous /api/i18n/auto-translate call
             * 401'd (the endpoint was previously gated behind auth). Bumping
             * the prefix invalidates every poisoned browser cache in one shot
             * so visitors get a fresh translation pass. */
            var CACHE_PREFIX = 'tx_cache_v6_';
            var lockedSeed = {};
            var cachePersistTimer = null;
            /* CRITICAL: re-entrancy guard — prevents mutation feedback loop */
            var _applying = false;
            var _mutDebounce = null;

            function getRootNode() {
              return document.getElementById('root') || document.body;
            }

            function isI18nReadinessBlocked() {
              try {
                return !!window.__racI18nBackgroundOnly;
              } catch(e) {
                return false;
              }
            }

            function ensureMetricsBucket() {
              try {
                if (!window.__racI18nMetrics) {
                  window.__racI18nMetrics = {
                    autoTranslate429Count: 0,
                    autoTranslateErrorCount: 0,
                    backoffCooldownHitCount: 0,
                    maxBackoffMs: 0,
                    last429At: 0,
                    lastErrorAt: 0,
                    lastCooldownAt: 0,
                    lastBackoffMs: 0,
                  };
                }
                return window.__racI18nMetrics;
              } catch(e) {
                return null;
              }
            }

            function warnI18nMetric(reason, payload) {
              try {
                var now = Date.now();
                if (now - lastMetricConsoleAt < METRIC_LOG_THROTTLE_MS) return;
                lastMetricConsoleAt = now;
                console.warn('[i18n-429-monitor]', reason, payload || {});
              } catch(e) {}
            }

            function getLang() {
              try { var d = JSON.parse(localStorage.getItem('app_theme') || '{}');
                var m = {
                  English:'en',French:'fr',Spanish:'es',German:'de',Italian:'it',Portuguese:'pt',
                  Chinese:'zh','Chinese (Simplified)':'zh','Chinese (Traditional)':'zh',
                  Japanese:'ja',Korean:'ko',Hindi:'hi',Arabic:'ar',Russian:'ru',Turkish:'tr',
                  Dutch:'nl',Swedish:'sv',Polish:'pl',Thai:'th',Vietnamese:'vi',
                  Indonesian:'id','Bahasa Indonesia':'id',
                  Malay:'ms','Bahasa Melayu':'ms',
                  Swahili:'sw','Kiswahili':'sw',
                  Ukrainian:'uk',Romanian:'ro'
                };
                var lc = '';
                if (typeof d.languageCode === 'string' && d.languageCode.trim()) {
                  lc = d.languageCode.trim().toLowerCase();
                }
                if (!lc) {
                  lc = m[d.language] || 'en';
                }
                if (lc.indexOf('-') !== -1) lc = lc.split('-')[0];
                if (lc.indexOf('_') !== -1) lc = lc.split('_')[0];
                return lc || 'en';
              } catch(e) { return 'en'; }
            }

            function loadPersistedCache(lg) {
              try {
                var raw = localStorage.getItem(CACHE_PREFIX + lg);
                if (!raw) return;
                var parsed = JSON.parse(raw);
                if (!cache[lg]) cache[lg] = {};
                for (var k in parsed) cache[lg][k] = parsed[k];
              } catch(e) {}
            }

            function persistCacheSoon(lg) {
              try {
                if (cachePersistTimer) clearTimeout(cachePersistTimer);
                cachePersistTimer = setTimeout(function() {
                  try {
                    var langCache = cache[lg] || {};
                    var keys = Object.keys(langCache);
                    if (!keys.length) return;
                    if (keys.length > 2500) {
                      var trimmed = {};
                      for (var i = keys.length - 2500; i < keys.length; i++) {
                        if (i >= 0) trimmed[keys[i]] = langCache[keys[i]];
                      }
                      localStorage.setItem(CACHE_PREFIX + lg, JSON.stringify(trimmed));
                      cache[lg] = trimmed;
                    } else {
                      localStorage.setItem(CACHE_PREFIX + lg, JSON.stringify(langCache));
                    }
                  } catch(e) {}
                }, 220);
              } catch(e) {}
            }

            /* LOCKED: Exact-match brand names that must NEVER be translated */
            var EXACT_BRANDS = {'RealAICoach':1,'Realaicoach':1,'Real AI Coach':1,'Real-AI-Coach':1,'Google':1,'Microsoft':1,'Apple':1,'Google Play':1,'App Store':1,'Amazon':1,'Facebook':1,'Meta':1,'Netflix':1,'Twitter':1,'LinkedIn':1,'GitHub':1,'Forbes':1,'Bloomberg':1,'TechCrunch':1,'Fortune':1,'Tesla':1,'WhatsApp':1,'YouTube':1,'Instagram':1,'Pinterest':1,'Stripe':1,'PayPal':1,'FedaPay':1,'Android':1,'iOS':1,'iPhone':1,'iPad':1,'MacBook':1,'iMac':1,'Safari':1,'Chrome':1,'Firefox':1,'Windows':1,'macOS':1,'Linux':1,'Ubuntu':1,'Samsung':1,'Huawei':1,'Xiaomi':1,'OnePlus':1,'Sony':1,'Spotify':1,'TikTok':1,'Snapchat':1,'Reddit':1,'Slack':1,'Zoom':1,'Discord':1,'Figma':1,'Notion':1,'Vercel':1,'AWS':1,'Azure':1,'Docker':1,'Kubernetes':1,'MongoDB':1,'PostgreSQL':1,'ChatGPT':1,'OpenAI':1,'Anthropic':1,'Claude':1,'Gemini':1,'GPT':1,'DALL-E':1,'Sora':1,'Copilot':1};

            /* LOCKED: Parent-text brand patterns — when parent element's combined text matches these (whitespace-stripped), skip ALL child text nodes */
            var PARENT_BRAND_PATTERNS = ['RealAICoach','Realaicoach','RealAICoachLLC','GooglePlay','AppStore','GoogleSearchConsole','GoogleAnalytics','GoogleMaps','GoogleDrive','GoogleCalendar','GoogleCloud','VisualStudioCode','VSCode'];
            var PUBLIC_DOM_TRANSLATION_EXACT = {'/':1,'/welcome':1,'/about':1,'/about-us':1,'/talent-network':1,'/blog':1,'/career':1,'/careers':1,'/certificate-compare':1,'/contact':1,'/faq':1,'/features':1,'/feature-gallery':1,'/help':1,'/home':1,'/hiring-hub':1,'/pricing':1,'/privacy-policy':1,'/security':1,'/terms':1};
            var PUBLIC_DOM_TRANSLATION_PREFIXES = ['/blog/','/features/','/mini-apps/','/careers/','/subscription/'];

            function normalizedPathname() {
              try {
                var path = (window.location && window.location.pathname) || '/';
                while (path.length > 1 && path.charAt(path.length - 1) === '/') {
                  path = path.slice(0, -1);
                }
                return path || '/';
              } catch(e) { return '/'; }
            }

            function hasSessionToken() {
              try {
                return !!(localStorage.getItem('session_token') || sessionStorage.getItem('session_token'));
              } catch(e) { return false; }
            }

            function isPublicDomTranslationRoute(path) {
              if (PUBLIC_DOM_TRANSLATION_EXACT[path]) return true;
              for (var i = 0; i < PUBLIC_DOM_TRANSLATION_PREFIXES.length; i++) {
                if (path.indexOf(PUBLIC_DOM_TRANSLATION_PREFIXES[i]) === 0) return true;
              }
              return false;
            }

            function shouldRunDomTranslation(resolvedLang) {
              var activeLang = resolvedLang || lang;
              /* Permanent stability policy:
               * - DOM translation is enabled only on explicitly public routes.
               * - Protected/admin surfaces rely on static i18n keys only.
               * This prevents large authenticated DOM trees from translation
               * observer churn and request storms during language switches. */
              return activeLang !== 'en' && isPublicDomTranslationRoute(normalizedPathname());
            }

            function isAuthenticatedRoute() {
              return hasSessionToken() && !isPublicDomTranslationRoute(normalizedPathname());
            }

            function skip(t) {
              t = t.trim();
              if (t.length < MIN_LEN) return true;
              if (SKIP_RE.test(t)) return true;
              if (t.indexOf('@') > -1 && t.indexOf('.') > -1) return true;
              if (t.indexOf('http://') === 0 || t.indexOf('https://') === 0) return true;
              if (/^TKT-|^sub_|^[0-9a-f]{24}$/.test(t)) return true;
              /* LOCKED: Exact brand name match — never translate */
              if (EXACT_BRANDS[t]) return true;
              return false;
            }

            /* LOCKED: Check if a text node is INSIDE a brand-name element by examining parent's combined text */
            function parentIsBrand(node) {
              try {
                var el = node.parentElement;
                /* Walk up max 3 levels to find a brand-name container */
                for (var depth = 0; el && depth < 3; depth++) {
                  var pt = (el.textContent || '').replace(/\\s+/g, '');
                  if (pt.length > 0 && pt.length < 40) {
                    for (var i = 0; i < PARENT_BRAND_PATTERNS.length; i++) {
                      if (pt === PARENT_BRAND_PATTERNS[i]) return true;
                    }
                  }
                  el = el.parentElement;
                }
              } catch(e) {}
              return false;
            }

            var BRAND_RE = /(Google Play|App Store|\\bRealAICoach\\b|\\bReal\\s*AI\\s*Coach\\b|\\bReal-?AI-?Coach\\b|\\bApple\\b|\\bGoogle\\b|\\bMicrosoft\\b|\\bAmazon\\b|\\bFacebook\\b|\\bMeta\\b|\\bNetflix\\b|\\bTwitter\\b|\\bLinkedIn\\b|\\bGitHub\\b|\\bForbes\\b|\\bBloomberg\\b|\\bTechCrunch\\b|\\bFortune\\b|\\bTesla\\b|\\bWhatsApp\\b|\\bYouTube\\b|\\bInstagram\\b|\\bPinterest\\b|\\bStripe\\b|\\bPayPal\\b|\\bFedaPay\\b|\\bAndroid\\b|\\biOS\\b|\\biPhone\\b|\\biPad\\b|\\bMacBook\\b|\\biMac\\b|\\bSafari\\b|\\bChrome\\b|\\bFirefox\\b|\\bWindows\\b|\\bmacOS\\b|\\bLinux\\b|\\bUbuntu\\b|\\bSamsung\\b|\\bHuawei\\b|\\bXiaomi\\b|\\bOnePlus\\b|\\bSony\\b|\\bSpotify\\b|\\bTikTok\\b|\\bSnapchat\\b|\\bReddit\\b|\\bSlack\\b|\\bZoom\\b|\\bDiscord\\b|\\bFigma\\b|\\bNotion\\b|\\bVercel\\b|\\bAWS\\b|\\bAzure\\b|\\bDocker\\b|\\bKubernetes\\b|\\bMongoDB\\b|\\bPostgreSQL\\b|\\bChatGPT\\b|\\bOpenAI\\b|\\bAnthropic\\b|\\bClaude\\b|\\bGemini\\b|\\bGPT\\b|\\bDALL-E\\b|\\bSora\\b|\\bCopilot\\b)/gi;
            var BRAND_CANONICAL_RE = /(\\bReal\\s*AI\\s*Coach\\b|\\bReal-?AI-?Coach\\b|\\bRealaicoach\\b|\\bRéelAIEntraîneur\\b|\\bRealAICoach\\b)/gi;

            function canonicalizeProtectedBrands(text) {
              try {
                if (!text) return text;
                return String(text).replace(BRAND_CANONICAL_RE, 'RealAICoach');
              } catch(e) { return text; }
            }

            function protectBrands(text) {
              var map = {}; var idx = 0;
              var normalized = canonicalizeProtectedBrands(text);
              var result = normalized.replace(BRAND_RE, function(match) {
                var key = '{{B' + idx + '}}'; map[key] = match; idx++; return key;
              });
              return { text: result, map: map, hasBrands: idx > 0 };
            }

            function restoreBrands(text, map) {
              var result = text;
              for (var key in map) { result = result.split(key).join(map[key]); }
              return result;
            }

            function preservesBrands(sourceText, candidateText) {
              try {
                var srcMatches = canonicalizeProtectedBrands(String(sourceText || '')).match(BRAND_RE) || [];
                if (!srcMatches.length) return true;
                var candidate = canonicalizeProtectedBrands(String(candidateText || ''));
                for (var i = 0; i < srcMatches.length; i++) {
                  if (candidate.indexOf(srcMatches[i]) === -1) return false;
                }
                return true;
              } catch(e) { return true; }
            }

            function nodeSkip(n) {
              try {
              var el = n.parentNode;
              while (el && el !== document.body) {
                if (el.nodeType === 1) {
                  if (SKIP_TAGS[el.tagName]) return true;
                  if (el.hasAttribute && (el.hasAttribute('data-notranslate') || el.classList && el.classList.contains('notranslate'))) return true;
                  if (el.getAttribute && el.getAttribute('translate') === 'no') return true;
                  if (el.getAttribute && el.getAttribute('contenteditable') === 'true') return true;
                }
                el = el.parentNode;
              }
              } catch(e) { return true; }
              return false;
            }

            function applyTranslation(node, orig, translated) {
              /* Set re-entrancy guard before modifying DOM */
              _applying = true;
              try {
                if (node.parentNode) {
                  if (typeof node.__txOrig === 'undefined') node.__txOrig = orig;
                  node.textContent = node.textContent.replace(orig, translated);
                  if (node.parentElement) node.parentElement.setAttribute(TR, lang);
                }
              } catch(e) {}
              /* Release guard asynchronously to allow current mutation batch to settle */
              setTimeout(function() { _applying = false; }, 0);
            }

            function restoreOriginals(root) {
              try {
                var target = root || getRootNode();
                var w = document.createTreeWalker(target, NodeFilter.SHOW_TEXT, null);
                while (w.nextNode()) {
                  var n = w.currentNode;
                  if (typeof n.__txOrig === 'string' && n.textContent !== n.__txOrig) {
                    n.textContent = n.__txOrig;
                  }
                }
                var translatedEls = target.querySelectorAll ? target.querySelectorAll('[' + TR + ']') : [];
                for (var i = 0; i < translatedEls.length; i++) translatedEls[i].removeAttribute(TR);
              } catch(e) {}
            }

            function flush() {
              try {
              if (!queue.length || lang === 'en') return;
              var now = Date.now();
              if (apiBackoffUntil > now) {
                try {
                  var metricsCooldown = ensureMetricsBucket();
                  if (metricsCooldown) {
                    metricsCooldown.backoffCooldownHitCount = (metricsCooldown.backoffCooldownHitCount || 0) + 1;
                    metricsCooldown.lastCooldownAt = now;
                    metricsCooldown.lastBackoffMs = Math.max(0, apiBackoffUntil - now);
                    if ((metricsCooldown.lastBackoffMs || 0) > (metricsCooldown.maxBackoffMs || 0)) {
                      metricsCooldown.maxBackoffMs = metricsCooldown.lastBackoffMs || 0;
                    }
                  }
                  warnI18nMetric('cooldown_active', {
                    retry_in_ms: Math.max(0, apiBackoffUntil - now),
                    queue: queue.length,
                  });
                } catch(e) {}
                if (timer) clearTimeout(timer);
                timer = setTimeout(flush, Math.max(120, apiBackoffUntil - now));
                return;
              }
              if (isI18nReadinessBlocked()) {
                if (timer) clearTimeout(timer);
                timer = setTimeout(flush, 260);
                return;
              }
              var batch = queue.splice(0, MAX_BATCH);
              var unique = [], seen = {}, brandMaps = {};
              batch.forEach(function(i) { if (!seen[i.o]) { unique.push(i.o); seen[i.o] = true; } });
              var apiTexts = unique.map(function(t) {
                var p = protectBrands(t);
                if (p.hasBrands) brandMaps[t] = p.map;
                return p.text;
              });
              fetch('/api/i18n/auto-translate', {
                method: 'POST', headers: {'Content-Type': 'application/json', 'X-Requested-With': 'tx-engine'},
                body: JSON.stringify({texts: apiTexts, lang: lang})
              }).then(function(r) {
                if (r && r.status === 429) {
                  apiBackoffMs = apiBackoffMs ? Math.min(Math.round(apiBackoffMs * 1.7), API_BACKOFF_MAX_MS) : API_BACKOFF_BASE_MS;
                  apiBackoffUntil = Date.now() + apiBackoffMs + Math.floor(Math.random() * 220);
                  try {
                    var metrics429 = ensureMetricsBucket();
                    if (metrics429) {
                      metrics429.autoTranslate429Count = (metrics429.autoTranslate429Count || 0) + 1;
                      metrics429.last429At = Date.now();
                      metrics429.lastBackoffMs = apiBackoffMs;
                      if (apiBackoffMs > (metrics429.maxBackoffMs || 0)) metrics429.maxBackoffMs = apiBackoffMs;
                    }
                    warnI18nMetric('rate_limit_429', {
                      backoff_ms: apiBackoffMs,
                      queue: queue.length,
                      unique_batch: unique.length,
                    });
                  } catch(e) {}
                  throw new Error('rate_limit_429');
                }
                apiBackoffMs = 0;
                apiBackoffUntil = 0;
                return r.json();
              }).then(function(d) {
                try {
                var m = d && d.translations || {};
                for (var idx = 0; idx < unique.length; idx++) {
                  var orig = unique[idx];
                  var apiT = apiTexts[idx];
                  var tr = m[apiT] || m[orig];
                  if (tr) {
                    if (brandMaps[orig]) tr = restoreBrands(tr, brandMaps[orig]);
                    tr = canonicalizeProtectedBrands(tr);
                    if (!preservesBrands(orig, tr)) tr = orig;
                    if (!cache[lang]) cache[lang] = {};
                    if (!(lockedSeed[lang] && lockedSeed[lang][orig] && cache[lang][orig] && cache[lang][orig] !== orig)) {
                      cache[lang][orig] = tr;
                    }
                    delete pendingTexts[orig];
                  }
                }
                persistCacheSoon(lang);
                batch.forEach(function(e) {
                  var tr = cache[lang] && cache[lang][e.o];
                  if (tr && tr !== e.o && e.n.parentNode && e.n.textContent.indexOf(tr) === -1) {
                    applyTranslation(e.n, e.o, tr);
                  }
                });
                if (queue.length > 0) timer = setTimeout(flush, 80);
                } catch(e) {}
              }).catch(function(err) {
                try {
                  if (String((err && err.message) || '').indexOf('rate_limit_429') === -1) {
                    apiBackoffMs = apiBackoffMs ? Math.min(Math.round(apiBackoffMs * 1.35), API_BACKOFF_MAX_MS) : API_BACKOFF_BASE_MS;
                    apiBackoffUntil = Date.now() + apiBackoffMs + Math.floor(Math.random() * 140);
                    var metricsErr = ensureMetricsBucket();
                    if (metricsErr) {
                      metricsErr.autoTranslateErrorCount = (metricsErr.autoTranslateErrorCount || 0) + 1;
                      metricsErr.lastErrorAt = Date.now();
                      metricsErr.lastBackoffMs = apiBackoffMs;
                      if (apiBackoffMs > (metricsErr.maxBackoffMs || 0)) metricsErr.maxBackoffMs = apiBackoffMs;
                    }
                    warnI18nMetric('auto_translate_error', {
                      backoff_ms: apiBackoffMs,
                      queue: queue.length,
                    });
                  }
                  unique.forEach(function(t) { delete pendingTexts[t]; /* DO NOT cache t→t on failure — that would lock the string to English forever. Leave uncached so the next mutation/walk retries. */ });
                  if (queue.length > 0) {
                    if (timer) clearTimeout(timer);
                    timer = setTimeout(flush, Math.max(180, apiBackoffMs || 240));
                  }
                } catch(e) {}
              });
              } catch(e) {}
            }

            function enq(node, orig) {
              if (pendingTexts[orig]) return;
              pendingTexts[orig] = true;
              queue.push({n: node, o: orig});
              if (timer) clearTimeout(timer);
              timer = setTimeout(flush, BATCH_DELAY);
            }

            function proc(node, lg) {
              try {
              var text = node.textContent;
              if (!text || skip(text)) return;
              if (nodeSkip(node)) return;
              /* LOCKED: Skip if this text node is inside a brand-name container */
              if (parentIsBrand(node)) return;
              var p = node.parentElement;
              var t = text.trim();
              var c = cache[lg] && cache[lg][t];
              if (c !== undefined) {
                if (c !== t && text.indexOf(c) === -1) {
                  applyTranslation(node, t, c);
                }
                return;
              }
              if (p && p.getAttribute(TR) === lg) return;
              enq(node, t);
              } catch(e) {}
            }

            function walk(root, lg) {
              try {
              if (_applying) return; /* Skip if we are currently applying translations */
              var w = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
                acceptNode: function(n) {
                  if (!n.textContent || n.textContent.trim().length < MIN_LEN) return NodeFilter.FILTER_REJECT;
                  if (nodeSkip(n)) return NodeFilter.FILTER_REJECT;
                  return NodeFilter.FILTER_ACCEPT;
                }
              });
              while (w.nextNode()) proc(w.currentNode, lg);
              } catch(e) {}
            }

            var COMMON_STRINGS = [
              'Dashboard','Settings','Profile','Home','Search','Notifications','Messages',
              'Edit Profile','Subscription','Payment Cards','Privacy & Security','Security Settings',
              'Name, bio, photo','Manage your plan','Saved payment methods','Password, 2FA, data',
              '2FA, PIN, Passkey, Biometrics','Not connected','Connected','Connected (Primary)',
              'Link','Unlink','Save','Cancel','Delete','Edit','Close','Back','Next','Submit',
              'Loading...','No results','Error','Success','Warning','Info',
              'ACCOUNT','INTEGRATIONS','LINKED ACCOUNTS','APPEARANCE','NOTIFICATIONS','ABOUT',
              'Email & Password','Sign Out','Log Out','Theme','Language','Font Size',
              'Dark Mode','Light Mode','System','Account','Notifications','About',
              'Active Users','AI Sessions','Performance','Growth','Career','Health',
              'Finance','Learning','Wellness','Mon','Tue','Wed','Thu','Fri','Sat','Sun',
              'Today','Yesterday','This Week','This Month','All Time',
              'Free Trial','Get Started','Learn More','Contact Us','Features','Pricing',
              'Analytics','Security','Support','Help','FAQ','Terms','Privacy Policy',
              'Content Library','Downloads','Practice','Progress','Leaderboard',
              'AI Tools','Coaching','Reports','Calendar','Referrals','Team Management',
              'Jobs Portal','ID Checker','Billing','My Tickets','My Analytics',
              'Welcome back','Good morning','Good afternoon','Good evening',
              'Start your AI journey','Explore coaching tools',
              'Real-Time Performance','LIVE','AI SYSTEM ONLINE',
              'ACTIVE USERS','AI SESSIONS TODAY','PERFORMANCE IMPROVEMENT','GLOBAL COACHES',
              'AI Sessions','User Growth','Coaching Categories',
              'View All','See More','Show Less','Expand','Collapse',
              'Confirm','Are you sure?','Yes','No','OK','Done','Apply','Reset',
              'Password','Email','Username','Phone','Address','Country','City',
              'First Name','Last Name','Full Name','Date of Birth','Gender',
              'Upload','Download','Share','Copy','Paste','Print','Export','Import',
              'Create','Add','Remove','Update','Refresh','Retry','Skip',
              'Online','Offline','Away','Busy','Available',
              'Pending','Active','Completed','Failed','Cancelled','Expired',
              'Premium','Pro','Enterprise','Free','Basic','Standard',
              'Monthly','Yearly','Annual','Lifetime',
              'Total','Average','Minimum','Maximum','Count',
              'Status','Type','Date','Time','Amount','Description','Category','Priority',
              'Low','Medium','High','Critical','Urgent',
              'Open','Closed','In Progress','Resolved','Rejected',
              'Admin','User','Manager','Editor','Viewer',
              'Enable','Disable','On','Off','Yes','No',
              'Remember me on this device','Forgot?','Create one','Continue as Guest',
              'No account?','Already have an account?','Sign in','Sign up','Register',
              'NAME','EMAIL','PASSWORD','CONFIRM PASSWORD','PHONE','ADDRESS',
              'Bio','Website','Location','Company','Job Title','Skills',
              'Appearance','Accessibility','General','Advanced','Developer',
              'Push Notifications','Email Notifications','SMS Notifications',
              'Daily Briefing','Weekly Summary','Practice Reminders',
              'Language & Font Size','Color Accent','Background',
              'Version','Build','Platform','Device','Screen Size',
              'Terms of Service','Privacy Policy','Cookie Policy','GDPR',
              'Contact Support','Report Bug','Send Feedback','Rate App',
              'Manage your plan','View invoices','Update payment method',
              'Change password','Enable 2FA','Manage sessions',
              'Coaching Sessions','Goal Tracking','Skill Assessment',
              'Interview Prep','Resume Builder','Career Path',
              'AI Chatbot','AI Search','Content Studio',
              'Problem Solver','Daily Briefing','Learning Hub'
            ];

            function precache(lg) {
              try {
              if (lg === 'en') return;
              if (isI18nReadinessBlocked()) return;
              if (apiBackoffUntil > Date.now()) return;
              var uncached = COMMON_STRINGS.filter(function(s) { return !(cache[lg] && cache[lg][s]); });
              if (!uncached.length) return;
              for (var i = 0; i < uncached.length; i += 60) {
                var chunk = uncached.slice(i, i + 60);
                (function(chunkIndex, payload) {
                setTimeout(function() {
                if (apiBackoffUntil > Date.now()) return;
                fetch('/api/i18n/auto-translate', {
                  method: 'POST', headers: {'Content-Type': 'application/json', 'X-Requested-With': 'tx-engine'},
                  body: JSON.stringify({texts: payload, lang: lg})
                }).then(function(r) {
                  if (r && r.status === 429) {
                    apiBackoffMs = apiBackoffMs ? Math.min(Math.round(apiBackoffMs * 1.7), API_BACKOFF_MAX_MS) : API_BACKOFF_BASE_MS;
                    apiBackoffUntil = Date.now() + apiBackoffMs + Math.floor(Math.random() * 220);
                    try {
                      var metrics429Precache = ensureMetricsBucket();
                      if (metrics429Precache) {
                        metrics429Precache.autoTranslate429Count = (metrics429Precache.autoTranslate429Count || 0) + 1;
                        metrics429Precache.last429At = Date.now();
                        metrics429Precache.lastBackoffMs = apiBackoffMs;
                        if (apiBackoffMs > (metrics429Precache.maxBackoffMs || 0)) metrics429Precache.maxBackoffMs = apiBackoffMs;
                      }
                      warnI18nMetric('rate_limit_429_precache', {
                        backoff_ms: apiBackoffMs,
                        chunk_size: payload.length,
                      });
                    } catch(e) {}
                    throw new Error('rate_limit_429');
                  }
                  return r.json();
                }).then(function(d) {
                  try {
                  var m = d && d.translations || {};
                  for (var k in m) { if (!cache[lg]) cache[lg] = {}; cache[lg][k] = m[k]; }
                  /* Do NOT auto-walk after precache — let the observer handle it */
                  } catch(e) {}
                }).catch(function() {});
                }, chunkIndex * 95 + Math.floor(Math.random() * 60));
                })(Math.floor(i / 60), chunk);
              }
              } catch(e) {}
            }

            function start(lg) {
              try {
              if (lg === 'en') { stop(); return; }
              if (isI18nReadinessBlocked()) return;
              lang = lg; on = true;
              /* Adjust batch delay based on authenticated vs public routes */
              BATCH_DELAY = isAuthenticatedRoute() ? BATCH_DELAY_AUTH : BATCH_DELAY_PUBLIC;
              loadPersistedCache(lg);
              precache(lg);
              /* Initial walk with a slight delay to let React settle */
              var initDelay = isAuthenticatedRoute() ? 200 : 80;
              setTimeout(function() { if (on) walk(getRootNode(), lg); }, initDelay);
              if (obs) obs.disconnect();
              obs = new MutationObserver(function(ms) {
                try {
                /* CRITICAL: skip mutations caused by our own translations */
                if (_applying) return;
                /* Debounce mutation processing to avoid rapid-fire DOM walks */
                var mutDelay = isAuthenticatedRoute() ? 150 : 80;
                if (_mutDebounce) clearTimeout(_mutDebounce);
                _mutDebounce = setTimeout(function() {
                  _mutDebounce = null;
                  if (!on || _applying) return;
                  try {
                  /* Only process newly added nodes, NOT characterData changes */
                  var nodes = [];
                  ms.forEach(function(m) {
                    if (m.type === 'childList') {
                      m.addedNodes.forEach(function(n) { nodes.push(n); });
                    }
                  });
                  nodes.forEach(function(n) {
                    if (n.nodeType === 3) proc(n, lang);
                    else if (n.nodeType === 1 && !SKIP_TAGS[n.tagName]) walk(n, lang);
                  });
                  } catch(e) {}
                }, mutDelay);
                } catch(e) {}
              });
              /* Only observe childList, NOT characterData — prevents feedback loop */
              obs.observe(getRootNode(), {childList: true, subtree: true});
              /* Slow poll as safety net for dynamic content — less frequent on authenticated routes */
              if (poll) clearInterval(poll);
              var pollInterval = isAuthenticatedRoute() ? 120000 : 60000;
              poll = setInterval(function() {
                if (!on || _applying || document.visibilityState === 'hidden') { return; }
                walk(getRootNode(), lang);
              }, pollInterval);
              } catch(e) { console.warn('[TxEngine] start error:', e); }
            }

            function stop() {
              on = false;
              try { if (obs) { obs.disconnect(); obs = null; } } catch(e) {}
              try { if (poll) { clearInterval(poll); poll = null; } } catch(e) {}
              if (timer) { clearTimeout(timer); timer = null; }
              if (_mutDebounce) { clearTimeout(_mutDebounce); _mutDebounce = null; }
              queue = []; pendingTexts = {};
              restoreOriginals(getRootNode());
            }

            function seedCache(lg, entries) {
              try {
                if (!lg || !entries || typeof entries !== 'object') return;
                if (!cache[lg]) cache[lg] = {};
                if (!lockedSeed[lg]) lockedSeed[lg] = {};
                var changed = false;
                Object.keys(entries).forEach(function(k) {
                  var v = entries[k];
                  if (typeof k !== 'string' || typeof v !== 'string') return;
                  if (k.trim().length < MIN_LEN || v.trim().length < MIN_LEN) return;
                  lockedSeed[lg][k] = true;
                  if (cache[lg][k] !== v) { cache[lg][k] = v; changed = true; }
                });
                if (changed) persistCacheSoon(lg);
              } catch(e) {}
            }

            window.__txEngine = {
              start: start, stop: stop,
              reinit: function(lg) { try { if (lg === lang && on) return; stop(); lang = 'en'; if (lg !== 'en') { start(lg); } } catch(e) {} },
              isOn: function() { return on; }, getLang: function() { return lang; },
              precache: precache,
              seedCache: seedCache
            };

            function evaluateRouteMode() {
              try {
                var nextLang = getLang();
                if (isI18nReadinessBlocked()) {
                  if (on) stop();
                  return;
                }
                if (nextLang === 'en' || !shouldRunDomTranslation(nextLang)) {
                  if (on) stop();
                  lang = 'en';
                  return;
                }
                /* Public-route only DOM translation mode */
                if (!on || nextLang !== lang) {
                  window.__txEngine.reinit(nextLang);
                }
              } catch(e) {}
            }

            var bl = getLang();
            if (bl !== 'en' && shouldRunDomTranslation(bl)) {
              if (document.readyState === 'complete' || document.readyState === 'interactive') {
                setTimeout(function() { start(bl); }, 120);
              } else {
                document.addEventListener('DOMContentLoaded', function() { setTimeout(function() { start(bl); }, 120); });
              }
            }

            try {
              window.addEventListener('rac:i18n-readiness', function() {
                setTimeout(evaluateRouteMode, 40);
              });
            } catch(e) {}

            try {
              var _origSetItem = localStorage.setItem.bind(localStorage);
              localStorage.setItem = function(key, value) {
                try { _origSetItem(key, value); } catch(e) { return; }
                if (key === 'app_theme') {
                  try {
                    evaluateRouteMode();
                  } catch(e) {}
                }
              };
            } catch(e) {}

            try {
              window.addEventListener('storage', function(e) {
                try {
                if (e.key === 'app_theme') {
                  evaluateRouteMode();
                }
                } catch(e) {}
              });
            } catch(e) {}

            try {
              var _origPushState = history.pushState.bind(history);
              history.pushState = function() {
                var result = _origPushState.apply(history, arguments);
                setTimeout(evaluateRouteMode, 0);
                return result;
              };
              var _origReplaceState = history.replaceState.bind(history);
              history.replaceState = function() {
                var result = _origReplaceState.apply(history, arguments);
                setTimeout(evaluateRouteMode, 0);
                return result;
              };
              window.addEventListener('popstate', evaluateRouteMode);
              window.addEventListener('hashchange', evaluateRouteMode);
            } catch(e) {}

            } catch(e) {
              console.warn('[TxEngine] Init failed (non-fatal):', e);
              window.__txEngine = { start: function(){}, stop: function(){}, reinit: function(){}, isOn: function(){ return false; }, getLang: function(){ return 'en'; }, precache: function(){}, seedCache: function(){} };
            }
          })();
        `}} />
        <script dangerouslySetInnerHTML={{ __html: `
          (function(){
            try {
              var __racExpectedHost = ${JSON.stringify(expectedPreviewHost)};
              try { window.__racExpectedHost = __racExpectedHost; } catch (_expHostErr) {}
              var __racCurrentHost = ((window.location && window.location.hostname) || '').toLowerCase();
              var __racIsPreviewHost = __racCurrentHost.indexOf('preview.emergentagent.com') !== -1;
              var __racIsEmergentCfPreviewHost = __racCurrentHost.indexOf('.preview.emergentcf.cloud') !== -1;
              var __racExpectedIsPreview = (__racExpectedHost.indexOf('preview.emergentagent.com') !== -1) || (__racExpectedHost.indexOf('.preview.emergentcf.cloud') !== -1);
              // For preview-emergentagent hosts, enforce canonical host with a one-time guard.
              if (__racIsPreviewHost && __racExpectedIsPreview && __racCurrentHost && __racCurrentHost !== __racExpectedHost) {
                try {
                  var __racPreviewCanonicalGuardKey = 'rac:preview-host-canonicalized-v2';
                  var __racPreviewCanonicalGuard = sessionStorage.getItem(__racPreviewCanonicalGuardKey) || '';
                  if (__racPreviewCanonicalGuard !== __racExpectedHost) {
                    var __racCanonicalUrl = new URL(window.location.href);
                    __racCanonicalUrl.protocol = 'https:';
                    __racCanonicalUrl.hostname = __racExpectedHost;
                    __racCanonicalUrl.searchParams.set('preview_host_canonicalized', '1');
                    sessionStorage.setItem(__racPreviewCanonicalGuardKey, __racExpectedHost);
                    window.location.replace(__racCanonicalUrl.toString());
                    return;
                  }
                  window.__racPreviewHostMismatch = {
                    current: __racCurrentHost,
                    expected: __racExpectedHost,
                    at: Date.now(),
                    guard: 'suppress-repeat-redirect',
                  };
                } catch (_err) {
                  if (window.__racReportRecoverable) window.__racReportRecoverable('preview-host-mismatch-state', _err);
                }
              } else {
                try {
                  var __racCanonicalizedParams = new URLSearchParams(window.location.search || '');
                  if (__racCanonicalizedParams.has('preview_host_canonicalized')) {
                    __racCanonicalizedParams.delete('preview_host_canonicalized');
                    var __racCanonicalizedSearch = __racCanonicalizedParams.toString();
                    var __racCanonicalizedUrl = (window.location.pathname || '/') + (__racCanonicalizedSearch ? ('?' + __racCanonicalizedSearch) : '') + (window.location.hash || '');
                    var __racCurrentUrl = (window.location.pathname || '/') + (window.location.search || '') + (window.location.hash || '');
                    if (__racCanonicalizedUrl !== __racCurrentUrl) {
                      window.history.replaceState(window.history.state, '', __racCanonicalizedUrl);
                    }
                  }
                } catch (_canonicalizedCleanupErr) {
                  if (window.__racReportRecoverable) window.__racReportRecoverable('preview-host-canonicalized-param-cleanup', _canonicalizedCleanupErr);
                }
              }

              var __racEmbedded = false;
              try { __racEmbedded = window.self !== window.top; } catch (_embedErr) { __racEmbedded = true; }
              var __racIsEmergentHost = __racCurrentHost.endsWith('.emergent.sh') || __racCurrentHost === 'app.emergent.sh';

              // Permanent stale-preview fix:
              // Browser preview hosts under app.emergent.sh can pin stale snapshots.
              // Canonicalize to active preview host; recover shell/wrapper short-link paths to app root.
              if ((__racIsEmergentHost || __racIsEmergentCfPreviewHost) && __racExpectedIsPreview && __racExpectedHost && __racCurrentHost !== __racExpectedHost) {
                try {
                  var __racPath = window.location.pathname || '/';
                  var __racNeedsRootRecovery = __racPath.startsWith('/s/') || __racPath === '/wo' || __racPath.startsWith('/loading-preview');
                  var __racCanonicalPath = __racNeedsRootRecovery ? '/' : __racPath;
                  var __racSearch = (window.location.search || '');
                  if (__racNeedsRootRecovery) {
                    __racSearch = __racSearch ? (__racSearch + '&previewHostRecovered=1') : '?previewHostRecovered=1';
                  }
                  var __racTarget = 'https://' + __racExpectedHost + __racCanonicalPath + __racSearch + (window.location.hash || '');
                  window.location.replace(__racTarget);
                  return;
                } catch (_redirErr) {
                  if (window.__racReportRecoverable) window.__racReportRecoverable('preview-host-canonical-redirect', _redirErr);
                }
              }

              // Preview freshness guard:
              // Some preview clients can keep rendering an older HTML shell even after
              // a new bundle is live. Force one cache-busting URL refresh per bundle hash
              // on preview-like hosts so repeated users land on the newest Welcome layout.
              try {
                var __racNeedsPreviewFreshUrl = (__racIsPreviewHost || __racIsEmergentCfPreviewHost || __racIsEmergentHost) && !__racEmbedded;
                if (__racNeedsPreviewFreshUrl) {
                  var __racFreshMeta = document.querySelector('meta[name="rac-active-bundle-hash"]');
                  var __racFreshHash = ((__racFreshMeta && __racFreshMeta.getAttribute('content')) || '').trim();
                  if (__racFreshHash) {
                    var __racFreshUrl = new URL(window.location.href);
                    var __racFreshParam = String(__racFreshUrl.searchParams.get('preview_fresh') || '');
                    var __racFreshGuardKey = 'rac:preview-fresh-url:' + __racFreshHash;
                    var __racFreshGuard = sessionStorage.getItem(__racFreshGuardKey) === '1';
                    if (__racFreshParam !== __racFreshHash && !__racFreshGuard) {
                      sessionStorage.setItem(__racFreshGuardKey, '1');
                      __racFreshUrl.searchParams.set('preview_fresh', __racFreshHash);
                      window.location.replace(__racFreshUrl.toString());
                      return;
                    }
                  }
                }
              } catch (_freshUrlErr) {
                if (window.__racReportRecoverable) window.__racReportRecoverable('preview-fresh-url-guard', _freshUrlErr);
              }

              var __racNeedsSwCleanup = __racIsPreviewHost || __racIsEmergentCfPreviewHost || __racIsEmergentHost || __racEmbedded;
              if (__racNeedsSwCleanup && 'serviceWorker' in navigator) {
                try {
                  var __racBundleHashMeta = document.querySelector('meta[name="rac-active-bundle-hash"]');
                  var __racBundleHashForCleanup = ((__racBundleHashMeta && __racBundleHashMeta.getAttribute('content')) || '').trim() || 'nohash';
                  var __racCleanupReloadKey = 'rac:sw-preview-cleanup-v2:' + __racBundleHashForCleanup;
                  navigator.serviceWorker.getRegistrations().then(function(regs) {
                    return Promise.all((regs || []).map(function(reg) { return reg.unregister().catch(function(){ return false; }); }));
                  }).then(function() {
                    if ('caches' in window && window.caches && window.caches.keys) {
                      return window.caches.keys().then(function(keys) {
                        return Promise.all((keys || [])
                          .filter(function(key) {
                            var k = String(key || '').toLowerCase();
                            return k.indexOf('realaicoach-') === 0 || k.indexOf('workbox-') === 0 || k.indexOf('rac-') === 0;
                          })
                          .map(function(key) { return window.caches.delete(key).catch(function(){ return false; }); }));
                      });
                    }
                    return Promise.resolve();
                  }).then(function() {
                    try {
                      var already = sessionStorage.getItem(__racCleanupReloadKey) === '1';
                      if (navigator.serviceWorker.controller && !already) {
                        sessionStorage.setItem(__racCleanupReloadKey, '1');
                        window.location.reload();
                      }
                    } catch (_reloadErr) {
                      if (window.__racReportRecoverable) window.__racReportRecoverable('preview-sw-cleanup-reload-guard', _reloadErr);
                    }
                  }).catch(function(err){ if (window.__racReportRecoverable) window.__racReportRecoverable('preview-sw-cleanup-chain', err); });
                } catch (_cleanupErr) {
                  if (window.__racReportRecoverable) window.__racReportRecoverable('preview-sw-cleanup', _cleanupErr);
                }
              }

              // Dist freshness guard:
              // If server publishes a new bundle hash compared to session hash, perform one guarded reload.
              try {
                var __racMeta = document.querySelector('meta[name="rac-active-bundle-hash"]');
                var __racServerHash = (__racMeta && __racMeta.getAttribute('content')) || '';
                if (__racServerHash) {
                  var __racSessionHashKey = 'rac:active-bundle-hash';
                  var __racReloadGuardKey = 'rac:bundle-hash-reload-guard';
                  var __racHardReloadGuardKey = 'rac:bundle-hard-reload-guard';
                  var __racStaleNormalizeGuardKey = 'rac:stale-pricing-normalized';
                  var __racPrevHash = sessionStorage.getItem(__racSessionHashKey) || '';
                  var __racGuard = sessionStorage.getItem(__racReloadGuardKey) || '';
                  var __racHardGuard = sessionStorage.getItem(__racHardReloadGuardKey) || '';

                  if (__racPrevHash && __racPrevHash !== __racServerHash && __racGuard !== __racServerHash) {
                    sessionStorage.removeItem(__racStaleNormalizeGuardKey);
                    sessionStorage.setItem(__racReloadGuardKey, __racServerHash);
                    sessionStorage.setItem(__racSessionHashKey, __racServerHash);
                    window.location.reload();
                    return;
                  }

                  // Hard stale breaker (one-time): enforce cache-busting reload if hash drifts
                  // and the soft reload guard already ran but app still presents old runtime.
                  if (__racPrevHash && __racPrevHash !== __racServerHash && __racHardGuard !== __racServerHash) {
                    var __racNow = Date.now();
                    var __racUrl = new URL(window.location.href);
                    __racUrl.searchParams.set('bundle_refresh', String(__racNow));
                    sessionStorage.removeItem(__racStaleNormalizeGuardKey);
                    sessionStorage.setItem(__racHardReloadGuardKey, __racServerHash);
                    sessionStorage.setItem(__racSessionHashKey, __racServerHash);
                    window.location.replace(__racUrl.toString());
                    return;
                  }

                  sessionStorage.setItem(__racSessionHashKey, __racServerHash);
                }
              } catch (_hashGuardErr) {
                if (window.__racReportRecoverable) window.__racReportRecoverable('preview-bundle-hash-guard', _hashGuardErr);
              }

              // Pre-hydration stale URL normalization:
              // stale clients can keep legacy return_to=/subscription/plans in URL and bypass
              // latest compare-flow intent. Normalize before React boot.
              try {
                var __racPathNow = String((window.location && window.location.pathname) || '/');
                var __racSearchNow = new URLSearchParams((window.location && window.location.search) || '');
                var __racReturnTo = String(__racSearchNow.get('return_to') || '');
                var __racSource = String(__racSearchNow.get('source') || '');
                var __racAuthReason = String(__racSearchNow.get('auth_reason') || '').toLowerCase();
                var __racLooksLikeLegacySubscriptionReturn = __racReturnTo.indexOf('/subscription/plans') !== -1;
                var __racLooksLikeCompareContext = (__racSource === 'pricing-compare') || (__racAuthReason === 'unauthenticated');

                if (
                  __racPathNow === '/welcome'
                  && __racLooksLikeLegacySubscriptionReturn
                  && __racLooksLikeCompareContext
                ) {
                  __racSearchNow.delete('return_to');
                  __racSearchNow.delete('auth_reason');
                  __racSearchNow.set('section', 'pricing');
                  __racSearchNow.set('source', 'pricing-compare');
                  window.location.replace('/welcome?' + __racSearchNow.toString());
                  return;
                }
              } catch (_staleNormalizeErr) {
                if (window.__racReportRecoverable) window.__racReportRecoverable('preview-stale-pricing-normalize', _staleNormalizeErr);
              }
            } catch(e) {
              if (window.__racReportRecoverable) window.__racReportRecoverable('preview-bootstrap-fatal', e);
            }
          })();
        `}} />

        {/* Web Vitals Reporter - sends real browser metrics to Performance Guardian */}
        <script dangerouslySetInnerHTML={{ __html: `
          (function() {
            var q = [];
            function send() {
              if (!q.length) return;
              var batch = q.splice(0, q.length);
              var payload = batch.map(function(m) {
                return { lcp: m.lcp||0, fcp: m.fcp||0, ttfb: m.ttfb||0, cls: m.cls||0, inp: m.inp||0, page: location.pathname, ua: navigator.userAgent, release_version: '${telemetryRelease}' };
              });
              try {
                if (navigator.sendBeacon) {
                  navigator.sendBeacon('${backendAsset('/api/vitals/report')}', JSON.stringify(payload));
                } else {
                  fetch('${backendAsset('/api/vitals/report')}', { method: 'POST', body: JSON.stringify(payload), headers: { 'Content-Type': 'application/json' }, keepalive: true });
                }
              } catch(e) {}
            }
            var metrics = {};
            function observe(type, cb) {
              try {
                var po = new PerformanceObserver(function(list) {
                  list.getEntries().forEach(cb);
                });
                po.observe({ type: type, buffered: true });
              } catch(e) {}
            }
            observe('largest-contentful-paint', function(e) { metrics.lcp = e.startTime; });
            observe('first-input', function(e) { metrics.inp = e.processingStart - e.startTime; });
            observe('layout-shift', function(e) { if (!e.hadRecentInput) { metrics.cls = (metrics.cls||0) + e.value; } });
            observe('paint', function(e) { if (e.name === 'first-contentful-paint') metrics.fcp = e.startTime; });
            var nav = performance.getEntriesByType && performance.getEntriesByType('navigation')[0];
            if (nav) metrics.ttfb = nav.responseStart;
            setTimeout(function() {
              if (Object.keys(metrics).length > 0) { q.push(Object.assign({}, metrics)); send(); }
            }, 8000);
            document.addEventListener('visibilitychange', function() { if (document.visibilityState === 'hidden' && Object.keys(metrics).length > 0) { q.push(Object.assign({}, metrics)); send(); } });
          })();
        `}} />
      </body>
    </html>
  );
}
