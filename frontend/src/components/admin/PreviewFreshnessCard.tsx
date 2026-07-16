import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { ActivityIndicator, Text, TouchableOpacity, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useTranslation } from '../../hooks/useTranslation';
import { resolveRuntimeBaseUrl } from '../../utils/runtimeBaseUrl';

type Props = {
  colors: any;
};

type PreviewHealthPayload = {
  active_bundle_hash?: string;
  expected_preview_host?: string;
  build_state?: {
    built_at?: string;
    source_fingerprint?: string;
  };
  dist_runtime?: {
    last_reason?: string;
    last_result?: string;
    last_build_duration_ms?: number;
    last_updated_at?: string;
  };
};

const formatReason = (value: string) => {
  const normalized = String(value || '').trim();
  if (!normalized) return 'Unknown';
  return normalized.replace(/[_-]+/g, ' ').replace(/\b\w/g, (char) => char.toUpperCase());
};

const formatDuration = (value?: number) => {
  const totalMs = Number(value || 0);
  if (!Number.isFinite(totalMs) || totalMs <= 0) return '—';
  const totalSeconds = Math.round(totalMs / 1000);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return minutes <= 0 ? `${seconds}s` : `${minutes}m ${seconds}s`;
};

const formatDateTime = (value?: string) => {
  if (!value) return '—';
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString();
};

const readActiveBundleHashFallback = () => {
  if (typeof document === 'undefined') return '';
  const metaHash = String(document.querySelector('meta[name="rac-active-bundle-hash"]')?.getAttribute('content') || '').trim();
  if (metaHash) return metaHash;
  const scriptTags = Array.from(document.querySelectorAll('script[src]'));
  for (const tag of scriptTags) {
    const src = String(tag.getAttribute('src') || '');
    const match = src.match(/index-([a-f0-9]{8,})\.js/i);
    if (match?.[1]) {
      return match[1];
    }
  }
  return '';
};

const getFreshnessTone = (payload: PreviewHealthPayload, colors: any) => {
  const result = String(payload?.dist_runtime?.last_result || '').toLowerCase();
  const hasHash = Boolean(String(payload?.active_bundle_hash || '').trim());
  if (result === 'success' && hasHash) {
    return { label: 'Fresh', color: colors.successText, bg: `${colors.successText}20` };
  }
  if (result === 'failed') {
    return { label: 'Needs attention', color: colors.error, bg: `${colors.error}20` };
  }
  return { label: 'Checking', color: colors.warning, bg: `${colors.warning}20` };
};

export default function PreviewFreshnessCard({ colors }: Props) {
  const { t } = useTranslation();
  const tx = useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);

  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState('');
  const [payload, setPayload] = useState<PreviewHealthPayload>({});

  const load = useCallback(async (manual = false) => {
    if (manual) setRefreshing(true);
    else setLoading(true);
    setError('');
    try {
      const base = resolveRuntimeBaseUrl().replace(/\/+$/, '');
      const res = await fetch(`${base || ''}/_preview/health`, {
        method: 'GET',
        headers: { 'X-Requested-With': 'XMLHttpRequest' },
      });
      if (!res.ok) throw new Error(`preview-health-http-${res.status}`);
      const data = (await res.json()) || {};
      setPayload({
        ...data,
        active_bundle_hash: String(data?.active_bundle_hash || '').trim() || readActiveBundleHashFallback(),
      });
    } catch (fetchError: any) {
      setError(String(fetchError?.message || tx('operationsConsole.previewFreshness.error', 'Could not load preview freshness.')));
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [tx]);

  useEffect(() => {
    void load(false);
  }, [load]);

  const tone = useMemo(() => getFreshnessTone(payload, colors), [colors, payload]);
  const bundleHash = String(payload?.active_bundle_hash || '').trim();
  const shortHash = bundleHash ? `${bundleHash.slice(0, 8)}…${bundleHash.slice(-6)}` : 'Unavailable';
  const reasonCode = String(payload?.dist_runtime?.last_reason || '').trim();
  const builtAt = payload?.build_state?.built_at || payload?.dist_runtime?.last_updated_at || '';
  const fingerprint = String(payload?.build_state?.source_fingerprint || '').trim();

  return (
    <View style={{ backgroundColor: colors.card, borderWidth: 1, borderColor: colors.border, borderRadius: 14, padding: 16, gap: 10 }} data-testid="preview-freshness-card" testID="preview-freshness-card">
      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 10 }}>
        <View style={{ flex: 1 }}>
          <Text style={{ color: colors.text, fontSize: 14, fontWeight: '800' }} data-testid="preview-freshness-card-title" testID="preview-freshness-card-title">
            {tx('operationsConsole.previewFreshness.title', 'Preview Freshness')}
          </Text>
          <Text style={{ color: colors.textMuted, fontSize: 11, marginTop: 2 }} data-testid="preview-freshness-card-subtitle" testID="preview-freshness-card-subtitle">
            {tx('operationsConsole.previewFreshness.subtitle', 'Live bundle identity and latest rebuild cause from the preview runtime.')}
          </Text>
        </View>
        <View style={{ paddingHorizontal: 10, paddingVertical: 5, borderRadius: 999, backgroundColor: tone.bg }} data-testid="preview-freshness-card-status-pill" testID="preview-freshness-card-status-pill">
          <Text style={{ color: tone.color, fontSize: 10, fontWeight: '800' }} data-testid="preview-freshness-card-status-text" testID="preview-freshness-card-status-text">{tone.label}</Text>
        </View>
      </View>

      {loading ? (
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }} data-testid="preview-freshness-card-loading" testID="preview-freshness-card-loading">
          <ActivityIndicator size="small" color={colors.primary} />
          <Text style={{ color: colors.textMuted, fontSize: 11 }}>{tx('operationsConsole.previewFreshness.loading', 'Loading preview runtime state...')}</Text>
        </View>
      ) : (
        <>
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10 }}>
            <View style={{ flex: 1, minWidth: 220, borderWidth: 1, borderColor: colors.border, borderRadius: 12, padding: 12, backgroundColor: colors.surface }} data-testid="preview-freshness-card-bundle-block" testID="preview-freshness-card-bundle-block">
              <Text style={{ color: colors.textMuted, fontSize: 10, fontWeight: '700' }} data-testid="preview-freshness-card-bundle-label" testID="preview-freshness-card-bundle-label">{tx('operationsConsole.previewFreshness.bundleLabel', 'Active bundle hash')}</Text>
              <Text style={{ color: colors.text, fontSize: 15, fontWeight: '900', marginTop: 6 }} data-testid="preview-freshness-card-bundle-value" testID="preview-freshness-card-bundle-value">{shortHash}</Text>
              <Text style={{ color: colors.textMuted, fontSize: 10, marginTop: 4 }} numberOfLines={1} data-testid="preview-freshness-card-bundle-full" testID="preview-freshness-card-bundle-full">{bundleHash || 'No active bundle hash published yet.'}</Text>
            </View>

            <View style={{ flex: 1, minWidth: 220, borderWidth: 1, borderColor: colors.border, borderRadius: 12, padding: 12, backgroundColor: colors.surface }} data-testid="preview-freshness-card-reason-block" testID="preview-freshness-card-reason-block">
              <Text style={{ color: colors.textMuted, fontSize: 10, fontWeight: '700' }} data-testid="preview-freshness-card-reason-label" testID="preview-freshness-card-reason-label">{tx('operationsConsole.previewFreshness.reasonLabel', 'Last rebuild reason')}</Text>
              <Text style={{ color: colors.text, fontSize: 15, fontWeight: '900', marginTop: 6 }} data-testid="preview-freshness-card-reason-value" testID="preview-freshness-card-reason-value">{formatReason(reasonCode)}</Text>
              <Text style={{ color: colors.textMuted, fontSize: 10, marginTop: 4 }} numberOfLines={1} data-testid="preview-freshness-card-reason-code" testID="preview-freshness-card-reason-code">{reasonCode || 'unknown'}</Text>
            </View>
          </View>

          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 12 }}>
            <Text style={{ color: colors.textMuted, fontSize: 11 }} data-testid="preview-freshness-card-built-at" testID="preview-freshness-card-built-at">{tx('operationsConsole.previewFreshness.builtAt', 'Built at')}: {formatDateTime(builtAt)}</Text>
            <Text style={{ color: colors.textMuted, fontSize: 11 }} data-testid="preview-freshness-card-build-duration" testID="preview-freshness-card-build-duration">{tx('operationsConsole.previewFreshness.buildDuration', 'Build duration')}: {formatDuration(payload?.dist_runtime?.last_build_duration_ms)}</Text>
            <Text style={{ color: colors.textMuted, fontSize: 11 }} data-testid="preview-freshness-card-build-result" testID="preview-freshness-card-build-result">{tx('operationsConsole.previewFreshness.buildResult', 'Runtime result')}: {String(payload?.dist_runtime?.last_result || 'unknown').toUpperCase()}</Text>
          </View>

          <Text style={{ color: colors.textMuted, fontSize: 10 }} numberOfLines={1} data-testid="preview-freshness-card-fingerprint" testID="preview-freshness-card-fingerprint">{tx('operationsConsole.previewFreshness.fingerprint', 'Source fingerprint')}: {fingerprint || 'Unavailable'}</Text>
          <Text style={{ color: colors.textMuted, fontSize: 10 }} numberOfLines={1} data-testid="preview-freshness-card-host" testID="preview-freshness-card-host">{tx('operationsConsole.previewFreshness.host', 'Expected preview host')}: {String(payload?.expected_preview_host || 'Unavailable')}</Text>
        </>
      )}

      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
        {error ? <Text style={{ color: colors.warning, fontSize: 10, flex: 1 }} data-testid="preview-freshness-card-error" testID="preview-freshness-card-error">{error}</Text> : <View style={{ flex: 1 }} />}
        <TouchableOpacity onPress={() => void load(true)} disabled={refreshing} style={{ borderRadius: 10, paddingHorizontal: 12, paddingVertical: 8, backgroundColor: `${colors.primary}16`, borderWidth: 1, borderColor: `${colors.primary}45`, flexDirection: 'row', alignItems: 'center', gap: 6, opacity: refreshing ? 0.7 : 1 }} data-testid="preview-freshness-card-refresh-button" testID="preview-freshness-card-refresh-button">
          {refreshing ? <ActivityIndicator size="small" color={colors.primary} /> : <Ionicons name="refresh-outline" size={14} color={colors.primary} />}
          <Text style={{ color: colors.primary, fontSize: 11, fontWeight: '800' }} data-testid="preview-freshness-card-refresh-button-text" testID="preview-freshness-card-refresh-button-text">{refreshing ? tx('operationsConsole.previewFreshness.refreshing', 'Refreshing...') : tx('operationsConsole.previewFreshness.refresh', 'Refresh Freshness')}</Text>
        </TouchableOpacity>
      </View>
    </View>
  );
}