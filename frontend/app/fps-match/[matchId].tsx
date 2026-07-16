import React, { useCallback, useEffect, useState } from 'react';
import { ActivityIndicator, Platform, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';

import api from '../../src/services/api';
import { useTheme } from '../../src/context/ThemeContext';
import { useLanguage } from '../../src/i18n/LanguageContext';

type MatchCard = {
  match_id: string;
  player_name: string;
  kills: number;
  deaths: number;
  kd_ratio: number;
  best_streak: number;
  won: boolean;
  room_name: string;
  duration_ms: number;
  created_at: string;
  share_joins?: number;
};

// Official brand colors — exempt from theme tokenization (same convention as certificate verifier).
const SHARE_TARGETS: Array<{ id: string; label: string; icon: string; color: string; build: (url: string, text: string) => string }> = [
  { id: 'x', label: 'X', icon: 'logo-twitter', color: '#0F1419' /* @theme-ok brand-fixed-palette */, build: (u, t) => `https://twitter.com/intent/tweet?text=${t}&url=${u}` },
  { id: 'facebook', label: 'Facebook', icon: 'logo-facebook', color: '#1877F2' /* @theme-ok brand-fixed-palette */, build: (u) => `https://www.facebook.com/sharer/sharer.php?u=${u}` },
  { id: 'linkedin', label: 'LinkedIn', icon: 'logo-linkedin', color: '#0A66C2' /* @theme-ok brand-fixed-palette */, build: (u) => `https://www.linkedin.com/sharing/share-offsite/?url=${u}` },
  { id: 'whatsapp', label: 'WhatsApp', icon: 'logo-whatsapp', color: '#25D366' /* @theme-ok brand-fixed-palette */, build: (u, t) => `https://wa.me/?text=${t}%20${u}` },
  { id: 'telegram', label: 'Telegram', icon: 'paper-plane', color: '#26A5E4' /* @theme-ok brand-fixed-palette */, build: (u, t) => `https://t.me/share/url?url=${u}&text=${t}` },
  { id: 'reddit', label: 'Reddit', icon: 'logo-reddit', color: '#FF4500' /* @theme-ok brand-fixed-palette */, build: (u, t) => `https://www.reddit.com/submit?url=${u}&title=${t}` },
  { id: 'email', label: 'Email', icon: 'mail', color: '#64748B' /* @theme-ok brand-fixed-palette */, build: (u, t) => `mailto:?subject=${t}&body=${u}` },
];

const upsertOgMeta = (attr: 'property' | 'name', key: string, content: string) => {
  if (typeof document === 'undefined') return;
  let el = document.head.querySelector(`meta[${attr}="${key}"]`) as HTMLElement | null;
  if (!el) {
    el = document.createElement('meta');
    el.setAttribute(attr, key);
    document.head.appendChild(el);
  }
  el.setAttribute('content', content);
};

function formatDuration(ms: number): string {
  const total = Math.max(0, Math.round(ms / 1000));
  const m = Math.floor(total / 60);
  const s = total % 60;
  return m > 0 ? `${m}m ${s}s` : `${s}s`;
}

export default function FpsMatchCardPage() {
  const { matchId } = useLocalSearchParams<{ matchId: string }>();
  const router = useRouter();
  const { colors, darkMode } = useTheme();
  const { t } = useLanguage();
  const tx = useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);

  const [loading, setLoading] = useState(true);
  const [match, setMatch] = useState<MatchCard | null>(null);
  const [notFound, setNotFound] = useState(false);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const resp = await api.get(`/games-station/match-card/${encodeURIComponent(String(matchId || ''))}`);
        if (active) setMatch(resp.data);
      } catch {
        if (active) setNotFound(true);
      } finally {
        if (active) setLoading(false);
      }
    })();
    return () => { active = false; };
  }, [matchId]);

  const copyLink = useCallback(() => {
    if (typeof window === 'undefined') return;
    navigator.clipboard?.writeText(window.location.href).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2500);
    }).catch(() => { /* clipboard unavailable */ });
  }, []);

  const canNativeShare = Platform.OS === 'web' && typeof navigator !== 'undefined' && typeof (navigator as any).share === 'function';

  const shareUrl = useCallback(() => {
    if (typeof window === 'undefined') return '';
    const id = String(match?.match_id || matchId || '');
    return `${window.location.origin}/fps-match/${encodeURIComponent(id)}`;
  }, [match?.match_id, matchId]);

  const shareText = tx('fpsMatch.shareText', 'Check out my FPS match result on RealAICoach!');

  const openShare = useCallback((build: (url: string, text: string) => string) => {
    if (typeof window === 'undefined') return;
    const target = build(encodeURIComponent(shareUrl()), encodeURIComponent(shareText));
    window.open(target, '_blank', 'noopener,noreferrer');
  }, [shareUrl, shareText]);

  const nativeShare = useCallback(async () => {
    try {
      await (navigator as any).share({ title: tx('fpsMatch.title', 'FPS Match Card'), text: shareText, url: shareUrl() });
    } catch { /* dismissed */ }
  }, [shareUrl, shareText, tx]);

  useEffect(() => {
    if (!match || typeof window === 'undefined') return;
    const pageUrl = `${window.location.origin}/fps-match/${encodeURIComponent(match.match_id)}`;
    const imageUrl = `${window.location.origin}/api/games-station/match-card/${encodeURIComponent(match.match_id)}/social-preview.png`;
    upsertOgMeta('property', 'og:type', 'website');
    upsertOgMeta('property', 'og:title', `${tx('fpsMatch.title', 'FPS Match Card')} — ${match.player_name}`);
    upsertOgMeta('property', 'og:description', tx('fpsMatch.subtitle', 'Public match result from the RealAICoach FPS Arena'));
    upsertOgMeta('property', 'og:url', pageUrl);
    upsertOgMeta('property', 'og:image', imageUrl);
    upsertOgMeta('name', 'twitter:card', 'summary_large_image');
    upsertOgMeta('name', 'twitter:image', imageUrl);
  }, [match, tx]);

  const subText = darkMode ? 'rgba(226,232,240,0.72)' : 'rgba(15,23,42,0.62)';

  return (
    <ScrollView
      style={{ flex: 1, backgroundColor: colors.background }}
      contentContainerStyle={styles.pageWrap}
      data-testid="fps-match-page" testID="fps-match-page"
    >
      <Text style={[styles.pageTitle, { color: colors.text }]} data-testid="fps-match-title" testID="fps-match-title">
        {tx('fpsMatch.title', 'FPS Match Card')}
      </Text>
      <Text style={{ color: subText, marginBottom: 20, textAlign: 'center' }}>
        {tx('fpsMatch.subtitle', 'Public match result from the RealAICoach FPS Arena')}
      </Text>

      {loading && (
        <View style={styles.center} data-testid="fps-match-loading" testID="fps-match-loading">
          <ActivityIndicator size="large" color={colors.primary} />
        </View>
      )}

      {!loading && notFound && (
        <View style={styles.card} data-testid="fps-match-not-found" testID="fps-match-not-found">
          <Ionicons name="alert-circle-outline" size={40} color="#f87171" />
          <Text style={styles.notFoundText}>{tx('fpsMatch.notFound', 'Match not found or link expired.')}</Text>
        </View>
      )}

      {!loading && match && (
        <View style={styles.card} data-testid="fps-match-card" testID="fps-match-card">
          <View style={[styles.outcomePill, { backgroundColor: match.won ? 'rgba(34,197,94,0.18)' : 'rgba(248,113,113,0.16)' }]}>
            <Text style={[styles.outcomeText, { color: match.won ? '#4ade80' : '#f87171' }]} data-testid="fps-match-outcome" testID="fps-match-outcome">
              {match.won ? tx('fpsMatch.victory', 'Victory') : tx('fpsMatch.defeat', 'Defeat')}
            </Text>
          </View>
          <Text style={styles.playerName} data-testid="fps-match-player" testID="fps-match-player">{match.player_name}</Text>
          <Text style={styles.roomLine}>
            {tx('fpsMatch.room', 'Room')}: {match.room_name} · {tx('fpsMatch.duration', 'Duration')}: {formatDuration(match.duration_ms)}
          </Text>

          <View style={styles.statsRow} data-testid="fps-match-stats" testID="fps-match-stats">
            <View style={styles.statBox}>
              <Text style={styles.statValue}>{match.kills}</Text>
              <Text style={styles.statLabel}>{tx('fpsMatch.kills', 'Kills')}</Text>
            </View>
            <View style={styles.statBox}>
              <Text style={styles.statValue}>{match.deaths}</Text>
              <Text style={styles.statLabel}>{tx('fpsMatch.deaths', 'Deaths')}</Text>
            </View>
            <View style={styles.statBox}>
              <Text style={styles.statValue}>{match.kd_ratio}</Text>
              <Text style={styles.statLabel}>{tx('fpsMatch.kd', 'K/D')}</Text>
            </View>
            <View style={styles.statBox}>
              <Text style={[styles.statValue, { color: '#fbbf24' /* @theme-ok fixed-dark-canvas */ }]}>{match.best_streak}</Text>
              <Text style={styles.statLabel}>{tx('fpsMatch.bestStreak', 'Best streak')}</Text>
            </View>
          </View>

          {(match.share_joins || 0) > 0 && (
            <View style={styles.joinProofPill} data-testid="fps-match-share-joins" testID="fps-match-share-joins">
              <Ionicons name="people" size={13} color="#4ade80" />
              <Text style={styles.joinProofText}>
                {match.share_joins} {tx('fpsMatch.shareJoins', 'players joined from this card')}
              </Text>
            </View>
          )}

          <Pressable onPress={copyLink} style={styles.copyBtn} data-testid="fps-match-copy-link" testID="fps-match-copy-link">
            <Ionicons name="link-outline" size={15} color="#e2e8f0" />
            <Text style={styles.copyBtnText}>
              {copied ? tx('fpsMatch.linkCopied', 'Link copied') : tx('fpsMatch.copyLink', 'Copy link')}
            </Text>
          </Pressable>

          <Text style={styles.shareTitle} data-testid="fps-match-share-title" testID="fps-match-share-title">
            {tx('fpsMatch.shareTitle', 'Share this match')}
          </Text>
          <View style={styles.shareRow} data-testid="fps-match-share-row" testID="fps-match-share-row">
            {SHARE_TARGETS.map((s) => (
              <Pressable
                key={s.id}
                onPress={() => openShare(s.build)}
                style={[styles.shareBtn, { backgroundColor: s.color }, s.id === 'x' && styles.shareBtnOutlined]}
                accessibilityLabel={s.label}
                data-testid={`fps-match-share-${s.id}`} testID={`fps-match-share-${s.id}`}
              >
                <Ionicons name={s.icon as any} size={17} color="#fff" />
              </Pressable>
            ))}
            {canNativeShare && (
              <Pressable
                onPress={nativeShare}
                style={[styles.shareBtn, styles.shareMoreBtn]}
                accessibilityLabel={tx('fpsMatch.shareMore', 'More')}
                data-testid="fps-match-share-more" testID="fps-match-share-more"
              >
                <Ionicons name="share-social" size={16} color="#fff" />
                <Text style={styles.shareMoreText}>{tx('fpsMatch.shareMore', 'More')}</Text>
              </Pressable>
            )}
          </View>
          <Text style={styles.shareHint}>
            {tx('fpsMatch.shareHint', 'TikTok, YouTube, Instagram and other apps are available via your device share menu (More).')}
          </Text>
        </View>
      )}

      <View style={styles.ctaWrap}>
        <Pressable
          onPress={() => {
            try {
              window.localStorage?.setItem('fps_share_ref', String(match?.match_id || matchId || ''));
            } catch { /* storage unavailable */ }
            router.push('/auth');
          }}
          style={[styles.ctaBtn, { backgroundColor: colors.primary }]}
          data-testid="fps-match-signin-cta" testID="fps-match-signin-cta"
        >
          <Ionicons name="log-in-outline" size={18} color="#fff" />
          <Text style={styles.ctaText}>{tx('fpsMatch.cta', 'Sign in to play')}</Text>
        </Pressable>
        <Text style={{ color: subText, fontSize: 12, marginTop: 10, textAlign: 'center' }} data-testid="fps-match-cta-hint" testID="fps-match-cta-hint">
          {tx('fpsMatch.ctaHint', 'Game access requires a RealAICoach account.')}
        </Text>
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  pageWrap: { alignItems: 'center', paddingHorizontal: 20, paddingVertical: 40, maxWidth: 960, width: '100%', alignSelf: 'center' },
  pageTitle: { fontSize: 30, fontWeight: '900', marginBottom: 8, textAlign: 'center' },
  center: { alignItems: 'center', justifyContent: 'center', paddingVertical: 60 },
  card: { width: '100%', backgroundColor: '#0b1420' /* @theme-ok fixed-dark-canvas */, borderRadius: 20, padding: 26, alignItems: 'center', borderWidth: 1, borderColor: 'rgba(148,163,184,0.25)' },
  outcomePill: { borderRadius: 999, paddingHorizontal: 18, paddingVertical: 6, marginBottom: 14 },
  outcomeText: { fontSize: 15, fontWeight: '900', textTransform: 'uppercase', letterSpacing: 2 },
  playerName: { color: '#e2e8f0' /* @theme-ok fixed-dark-canvas */, fontSize: 26, fontWeight: '900', marginBottom: 6, textAlign: 'center' },
  roomLine: { color: 'rgba(226,232,240,0.65)', fontSize: 13, marginBottom: 20, textAlign: 'center' },
  statsRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 12, justifyContent: 'center', marginBottom: 20 },
  statBox: { backgroundColor: 'rgba(255,255,255,0.05)', borderRadius: 14, paddingHorizontal: 20, paddingVertical: 14, alignItems: 'center', minWidth: 90 },
  statValue: { color: '#e2e8f0' /* @theme-ok fixed-dark-canvas */, fontSize: 24, fontWeight: '900' },
  statLabel: { color: 'rgba(226,232,240,0.6)', fontSize: 11, fontWeight: '700', textTransform: 'uppercase', letterSpacing: 0.8, marginTop: 4 },
  copyBtn: { flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: 'rgba(255,255,255,0.08)', borderRadius: 999, paddingHorizontal: 16, paddingVertical: 9 },
  joinProofPill: { flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: 'rgba(34,197,94,0.12)', borderWidth: 1, borderColor: 'rgba(74,222,128,0.35)', borderRadius: 999, paddingHorizontal: 14, paddingVertical: 6, marginBottom: 16 },
  joinProofText: { color: '#4ade80' /* @theme-ok fixed-dark-canvas */, fontSize: 12, fontWeight: '800' },
  copyBtnText: { color: '#e2e8f0' /* @theme-ok fixed-dark-canvas */, fontSize: 13, fontWeight: '700' },
  shareTitle: { color: 'rgba(226,232,240,0.75)', fontSize: 12, fontWeight: '800', textTransform: 'uppercase', letterSpacing: 1, marginTop: 22, marginBottom: 10 },
  shareRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 10, justifyContent: 'center' },
  shareBtn: { width: 40, height: 40, borderRadius: 20, alignItems: 'center', justifyContent: 'center' },
  shareBtnOutlined: { borderWidth: 1, borderColor: 'rgba(226,232,240,0.35)' },
  shareMoreBtn: { width: undefined, flexDirection: 'row', gap: 6, paddingHorizontal: 14, backgroundColor: 'rgba(255,255,255,0.14)' },
  shareMoreText: { color: '#fff' /* @theme-ok fixed-dark-canvas */, fontSize: 12, fontWeight: '800' },
  shareHint: { color: 'rgba(226,232,240,0.45)', fontSize: 11, marginTop: 12, textAlign: 'center', maxWidth: 420 },
  notFoundText: { color: '#f87171' /* @theme-ok fixed-dark-canvas */, fontSize: 15, fontWeight: '700', marginTop: 10, textAlign: 'center' },
  ctaWrap: { marginTop: 26, alignItems: 'center', width: '100%' },
  ctaBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, borderRadius: 999, paddingHorizontal: 28, paddingVertical: 14 },
  ctaText: { color: '#fff' /* @theme-ok fixed-dark-canvas */, fontWeight: '800', fontSize: 15 },
});
