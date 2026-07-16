// Live stat tickertape — just-in-time social proof above the Welcome CTA.
// Rotates through up to 8 facts drawn from the SAME SSE stream the Home
// dashboard + Welcome hero use, plus the "+N joined" micro-badge and a
// daily coaching TIP OF THE DAY. Click-tracked via
// POST /api/public/tickertape-event so admins can see which fact
// converts best in the CTR analytics panel.
//
// for tips, `#F472B6` pink for signup pulses, etc.) that remain constant
// across themes. Structural chrome uses `colors.*` from useTheme().
//
// Props:
//   dark — when true, renders on the dark hero (higher-contrast chip).
//   onPress — optional callback fired when the user taps the chip.
//             Used by WelcomeHero to scroll to the primary CTA.
import React, { useEffect, useState, useMemo, useRef, useCallback } from 'react';
import { View, Text, Pressable } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useLiveMetrics } from '../../hooks/useLiveMetrics';
import { useTheme } from '../../context/ThemeContext';
import { useLanguage } from '../../i18n/LanguageContext';
import { resolveRuntimeBaseUrl } from '../../utils/runtimeBaseUrl';
import { withAlpha } from '../../utils/colorAlpha';

const API = `${resolveRuntimeBaseUrl()}/api`;

type Fact = {
  icon: keyof typeof Ionicons.glyphMap;
  color: string;
  text: string;
  testid: string;
};

// Fire-and-forget telemetry. Never throws, never awaits critical-path code.
function logTickertapeEvent(fact_testid: string, event_type: 'impression' | 'click', session_id?: string) {
  try {
    fetch(`${API}/public/tickertape-event`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Requested-With': 'XMLHttpRequest',
        'Accept': 'application/json',
      },
      body: JSON.stringify({ fact_testid, event_type, session_id }),
      keepalive: true,
    }).catch(() => { /* silent */ });
  } catch { /* silent */ }
}

function getSessionId(): string {
  try {
    if (typeof window === 'undefined') return '';
    const k = 'welcome-tickertape-session';
    let s = window.sessionStorage.getItem(k);
    if (!s) {
      s = Math.random().toString(36).slice(2, 10) + Date.now().toString(36).slice(-6);
      window.sessionStorage.setItem(k, s);
    }
    return s;
  } catch {
    return '';
  }
}

export default function WelcomeLiveTickertape({ dark = false, onPress, centered = false }: { dark?: boolean; onPress?: () => void; centered?: boolean }) {
  const { vanity } = useLiveMetrics(4000);
  const { colors } = useTheme();
  const { t } = useLanguage();
  const [idx, setIdx] = useState(0);
  const [signupsRecent, setSignupsRecent] = useState<number>(0);
  const [tipOfDay, setTipOfDay] = useState<{ title: string; content: string } | null>(null);
  const sessionIdRef = useRef<string>('');
  if (!sessionIdRef.current) sessionIdRef.current = getSessionId();

  useEffect(() => {
    let cancelled = false;
    const fetchSignups = async () => {
      try {
        const res = await fetch(`${API}/public/signups-recent?minutes=60`, {
          headers: { 'X-Requested-With': 'XMLHttpRequest', 'Accept': 'application/json' },
        });
        if (!res.ok) return;
        const body = await res.json();
        if (!cancelled) setSignupsRecent(Number(body?.count) || 0);
      } catch { /* silent */ }
    };
    fetchSignups();
    const id = setInterval(fetchSignups, 60000);
    return () => { cancelled = true; clearInterval(id); };
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch(`${API}/public/coaching-tip-of-the-day`, {
          headers: { 'X-Requested-With': 'XMLHttpRequest', 'Accept': 'application/json' },
        });
        if (!res.ok) return;
        const body = await res.json();
        if (!cancelled && body?.title && body?.content) {
          setTipOfDay({ title: String(body.title), content: String(body.content) });
        }
      } catch { /* silent */ }
    })();
    return () => { cancelled = true; };
  }, []);

  const facts: Fact[] = useMemo(() => {
    const template = (key: string, vars: Record<string, string | number> = {}) => {
      let text = t(key) || '';
      Object.entries(vars).forEach(([k, v]) => { text = text.replace(`{${k}}`, String(v)); });
      return text;
    };
    const v = vanity || {};
    const online = Number(v.users_online ?? 0);
    const sessions = Number(v.ai_sessions_today ?? 0);
    const active = Number(v.active_users ?? 0);
    const perf = Number(v.performance_boost ?? 0);
    const coaches = Number(v.global_coaches ?? 0);
    const health = Number(v.system_health ?? 0);

    const out: Fact[] = [];
    if (online > 0) out.push({ icon: 'pulse', color: colors.success, text: template('welcome.tickertape.online', { count: online.toLocaleString() }), testid: 'welcome-tickertape-fact-online' });
    if (sessions > 0) out.push({ icon: 'sparkles', color: colors.warning, text: template('welcome.tickertape.sessions', { count: sessions.toLocaleString() }), testid: 'welcome-tickertape-fact-sessions' });
    if (active > 0) out.push({ icon: 'people', color: colors.info, text: template('welcome.tickertape.active', { count: active.toLocaleString() }), testid: 'welcome-tickertape-fact-active' });
    if (perf > 0) out.push({ icon: 'trending-up', color: colors.purple, text: template('welcome.tickertape.perf', { count: perf }), testid: 'welcome-tickertape-fact-perf' });
    if (coaches > 0) out.push({ icon: 'ribbon', color: colors.primary, text: template('welcome.tickertape.coaches', { count: coaches.toLocaleString() }), testid: 'welcome-tickertape-fact-coaches' });
    if (health > 90) out.push({ icon: 'shield-checkmark', color: colors.success, text: template('welcome.tickertape.health', { count: health }), testid: 'welcome-tickertape-fact-health' });
    if (signupsRecent > 0) out.push({ icon: 'person-add', color: colors.purple, text: template(signupsRecent === 1 ? 'welcome.tickertape.signupsOne' : 'welcome.tickertape.signupsMany', { count: signupsRecent }), testid: 'welcome-tickertape-fact-signups' });
    if (tipOfDay) out.push({ icon: 'bulb', color: colors.warning, text: template('welcome.tickertape.tip', { title: tipOfDay.title, content: tipOfDay.content }), testid: 'welcome-tickertape-fact-tip' });
    return out;
  }, [vanity, signupsRecent, tipOfDay, colors.info, colors.primary, colors.purple, colors.success, colors.warning, t]);

  // Rotate every 4s. Reset to 0 whenever the facts list shrinks.
  useEffect(() => {
    if (facts.length === 0) return;
    if (idx >= facts.length) setIdx(0);
    const id = setInterval(() => setIdx((i) => (i + 1) % facts.length), 4000);
    return () => clearInterval(id);
  }, [facts.length, idx]);

  // ── CTR instrumentation ────────────────────────────────────────────
  // Log an IMPRESSION the first time each fact becomes the visible chip
  // within a session. Dedupe is persisted to sessionStorage so a React
  // remount (e.g. parent re-render, HMR) doesn't re-emit — backend
  // analytics tolerate over-count but we want clean numbers.
  const impressionSentRef = useRef<Set<string>>(new Set());
  useEffect(() => {
    // Rehydrate the sent-set from sessionStorage on first effect run so
    // the dedupe survives remounts within the same session.
    try {
      if (typeof window !== 'undefined' && impressionSentRef.current.size === 0) {
        const raw = window.sessionStorage.getItem('welcome-tickertape-impressions');
        if (raw) JSON.parse(raw).forEach((k: string) => impressionSentRef.current.add(k));
      }
    } catch { /* ignore */ }
  }, []);
  useEffect(() => {
    if (facts.length === 0) return;
    const f = facts[idx % facts.length];
    if (!f) return;
    const key = `${sessionIdRef.current}::${f.testid}`;
    if (impressionSentRef.current.has(key)) return;
    impressionSentRef.current.add(key);
    try {
      if (typeof window !== 'undefined') {
        window.sessionStorage.setItem(
          'welcome-tickertape-impressions',
          JSON.stringify(Array.from(impressionSentRef.current)),
        );
      }
    } catch { /* ignore */ }
    logTickertapeEvent(f.testid, 'impression', sessionIdRef.current);
  }, [idx, facts]);

  const handlePress = useCallback(() => {
    if (facts.length === 0) return;
    const f = facts[idx % facts.length];
    if (f) logTickertapeEvent(f.testid, 'click', sessionIdRef.current);
    if (onPress) { try { onPress(); } catch { /* ignore */ } }
  }, [facts, idx, onPress]);

  if (facts.length === 0) return null;
  const f = facts[idx % facts.length];

  // V2 theme-aware surface: opaque card background so the pill is always
  // legible regardless of what (gradient, image, green glow) sits behind
  // the hero. The emerald "live" accent now lives only in the dot + icon
  // + border — text uses the theme's primary text token, guaranteeing
  // AAA contrast in both light and dark modes.
  const bg = colors.surface;
  const border = withAlpha(colors.success, dark ? '73' : '59');
  const textColor = colors.text;
  const dotColor = colors.success;

  return (
    <Pressable
      onPress={handlePress}
      accessibilityRole="button"
      accessibilityLabel={(t('welcome.tickertape.accessibility') || '').replace('{fact}', f.text)}
      style={({ hovered, pressed }: any) => ({
        flexDirection: 'row', alignItems: 'center', gap: 8,
        paddingHorizontal: 12, paddingVertical: 8,
        borderRadius: 999, backgroundColor: bg,
        borderWidth: 1, borderColor: border,
        alignSelf: centered ? 'center' : 'flex-start', marginBottom: 16, maxWidth: '100%',
        opacity: pressed ? 0.8 : 1,
        transform: hovered ? [{ scale: 1.01 }] : undefined,
      })}
      data-testid="welcome-tickertape" testID="welcome-tickertape"
    >
      <View
        style={{ flexDirection: 'row', alignItems: 'center', gap: 8, flex: 1, minWidth: 0 }}
        accessibilityLiveRegion="polite"
        accessibilityRole="status"
      >
        <View style={{ width: 7, height: 7, borderRadius: 999, backgroundColor: dotColor, flexShrink: 0 }} />
        <Ionicons name={f.icon} size={13} color={f.color} />
        <Text
          // flex+minWidth:0 lets the fact line truncate with an ellipsis
          // so the trailing progress-dot indicator NEVER clips off the
          // right edge of the pill on narrow viewports (iPhone 14 Pro etc.).
          style={{ fontSize: 11, fontWeight: '700', color: textColor, letterSpacing: 0.2, flex: 1, flexShrink: 1, minWidth: 0 }}
          data-testid={f.testid} testID={f.testid}
          numberOfLines={1}
          ellipsizeMode="tail"
        >
          {f.text}
        </Text>
        <View style={{ flexDirection: 'row', gap: 3, marginLeft: 4, flexShrink: 0 }}
          data-testid="welcome-tickertape-progress-dots" testID="welcome-tickertape-progress-dots">
          {facts.map((_, i) => (
            <View
              key={i}
              style={{ width: 4, height: 4, borderRadius: 999, backgroundColor: i === (idx % facts.length) ? dotColor : border }}
            />
          ))}
        </View>
      </View>
    </Pressable>
  );
}
