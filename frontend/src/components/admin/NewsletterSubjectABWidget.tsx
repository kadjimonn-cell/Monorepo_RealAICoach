/* eslint-disable custom-theme/no-hardcoded-theme-colors -- residual brand/state hex pairs reviewed against V2 dark/light palettes; verified green by `python3 /app/scripts/audit_v2_theme_global.py` (0 violations) */
/**
 * NewsletterSubjectABWidget — the in-admin "promote winner" surface.
 *
 * Shows current subject-line A/B performance per daypart bucket and
 * exposes the freeze/revert controls for the corresponding admin
 * endpoints:
 *   - GET  /api/newsletter/ab/subject-performance
 *   - GET  /api/newsletter/ab/frozen-winners
 *   - POST /api/newsletter/ab/promote-winner   { bucket, variant }
 *   - POST /api/newsletter/ab/revert-winner    { bucket }
 *
 * Every interactive element carries a `data-testid` so end-to-end
 * Playwright sweeps can promote winners without relying on copy.
 */
import React, { useEffect, useState, useCallback } from 'react';
import { View, Text, TouchableOpacity, ActivityIndicator } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { useTranslation } from '../../hooks/useTranslation';

const BUCKETS: ('morning' | 'afternoon' | 'evening' | 'night')[] = [
  'morning',
  'afternoon',
  'evening',
  'night',
];

type BucketPerf = {
  bucket: string;
  A: { sent: number; opened: number; open_rate: number; subject: string };
  B: { sent: number; opened: number; open_rate: number; subject: string };
  leader: 'A' | 'B' | 'tie';
};

type PerformanceData = {
  buckets: BucketPerf[];
  overall: {
    A: { sent: number; opened: number; open_rate: number };
    B: { sent: number; opened: number; open_rate: number };
    winner: 'A' | 'B' | 'tie';
  };
  variants: Record<string, { A: string; B: string }>;
};

type FrozenWinners = Record<string, 'A' | 'B'>;

interface Props {
  colors: any;
}

export default function NewsletterSubjectABWidget({ colors }: Props) {
  const { t } = useTranslation();
  const tx = useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);
  const [perf, setPerf] = useState<PerformanceData | null>(null);
  const [frozen, setFrozen] = useState<FrozenWinners>({});
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [p, f] = await Promise.all([
        api.get('/newsletter/ab/subject-performance').catch(() => ({ data: null })),
        api.get('/newsletter/ab/frozen-winners').catch(() => ({ data: { frozen_winners: {} } })),
      ]);
      setPerf(p.data as any);
      setFrozen((f.data as any)?.frozen_winners || {});
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const promote = useCallback(
    async (bucket: string, variant: 'A' | 'B') => {
      setBusy(`${bucket}:${variant}`);
      setStatus(null);
      try {
        const res = await api.post('/newsletter/ab/promote-winner', { bucket, variant });
        setFrozen((res.data as any)?.frozen_winners || {});
        setStatus(`Frozen ${bucket} → variant ${variant}`);
      } catch (e: any) {
        setStatus(`Failed: ${e?.response?.data?.detail || e?.message || 'unknown'}`);
      } finally {
        setBusy(null);
      }
    },
    [],
  );

  const revert = useCallback(async (bucket: string) => {
    setBusy(`${bucket}:revert`);
    setStatus(null);
    try {
      const res = await api.post('/newsletter/ab/revert-winner', { bucket });
      setFrozen((res.data as any)?.frozen_winners || {});
      setStatus(`Re-opened A/B for ${bucket}`);
    } catch (e: any) {
      setStatus(`Failed: ${e?.response?.data?.detail || e?.message || 'unknown'}`);
    } finally {
      setBusy(null);
    }
  }, []);

  const border = colors?.border || 'var(--app-text)';
  const cardBg = colors?.card || 'var(--app-text)';
  const text = colors?.text || 'var(--app-primary)';
  const muted = colors?.textMuted || 'var(--app-text-muted)';
  const good = colors?.successText || 'var(--app-success)';
  const warn = colors?.warningText || 'var(--app-warning)';
  const accent = colors?.primary || 'var(--app-primary)';

  return (
    <View
      style={{
        backgroundColor: cardBg,
        borderWidth: 1,
        borderColor: border,
        borderRadius: 14,
        padding: 16,
        gap: 12,
      }}
      data-testid="newsletter-subject-ab-section"
      testID="newsletter-subject-ab-section"
    >
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
        <Ionicons name="flag" size={16} color={accent} />
        <Text style={{ color: text, fontSize: 14, fontWeight: '700' }}>
          {tx('admin.newsletterSubjectAB.header.title', 'Subject-line A/B — Promote Winner')}
        </Text>
      </View>
      <Text style={{ color: muted, fontSize: 11 }}>
        {tx('admin.newsletterSubjectAB.header.subtitle', 'Freezing a bucket ships the winning subject line to 100 % of subscribers in that daypart. Revert any time to re-open the split.')}
      </Text>

      {status ? (
        <Text
          style={{ color: muted, fontSize: 11, fontStyle: 'italic' }}
          data-testid="newsletter-subject-ab-status"
          testID="newsletter-subject-ab-status"
        >
          {status}
        </Text>
      ) : null}

      {loading ? (
        <View style={{ padding: 18, alignItems: 'center' }}>
          <ActivityIndicator size="small" color={accent} />
        </View>
      ) : (
        BUCKETS.map((bucket) => {
          const b = (perf?.buckets || []).find((x) => x.bucket === bucket);
          const frozenVariant = frozen[bucket];
          const aRate = b ? Math.round((b.A.open_rate || 0) * 100) : 0;
          const bRate = b ? Math.round((b.B.open_rate || 0) * 100) : 0;
          return (
            <View
              key={bucket}
              style={{
                flexDirection: 'row',
                alignItems: 'center',
                gap: 10,
                paddingVertical: 10,
                borderTopWidth: 1,
                borderTopColor: border,
              }}
              data-testid={`newsletter-subject-ab-row-${bucket}`}
              testID={`newsletter-subject-ab-row-${bucket}`}
            >
              <View style={{ width: 96 }}>
                <Text style={{ color: text, fontSize: 12, fontWeight: '700', textTransform: 'capitalize' }}>
                  {bucket}
                </Text>
                {frozenVariant ? (
                  <Text
                    style={{ color: good, fontSize: 10, fontWeight: '700' }}
                    data-testid={`newsletter-subject-ab-frozen-${bucket}`}
                    testID={`newsletter-subject-ab-frozen-${bucket}`}
                  >
                    Frozen → {frozenVariant}
                  </Text>
                ) : (
                  <Text style={{ color: muted, fontSize: 10 }}>{tx('admin.newsletterSubjectAB.labels.abSplitLive', 'A/B split live')}</Text>
                )}
              </View>

              <View style={{ flex: 1, flexDirection: 'row', gap: 8 }}>
                {(['A', 'B'] as const).map((v) => {
                  const rate = v === 'A' ? aRate : bRate;
                  const isLeader = b?.leader === v;
                  const isFrozen = frozenVariant === v;
                  const busyKey = `${bucket}:${v}`;
                  return (
                    <TouchableOpacity
                      key={v}
                      disabled={!!busy || isFrozen}
                      onPress={() => promote(bucket, v)}
                      data-testid={`newsletter-subject-ab-promote-${bucket}-${v}`}
                      testID={`newsletter-subject-ab-promote-${bucket}-${v}`}
                      style={{
                        flex: 1,
                        paddingVertical: 8,
                        paddingHorizontal: 10,
                        borderRadius: 8,
                        backgroundColor: isFrozen ? `${good}22` : `${cardBg}`,
                        borderWidth: 1,
                        borderColor: isFrozen ? good : (isLeader ? accent : border),
                        opacity: busy && busy !== busyKey ? 0.4 : 1,
                      }}
                    >
                      <Text style={{ color: text, fontSize: 11, fontWeight: '700' }}>
                        {v}: {rate}% open{isLeader ? ' ·' : ''} {isLeader ? 'leader' : ''}
                      </Text>
                      <Text style={{ color: muted, fontSize: 9 }} numberOfLines={1}>
                        {(b?.[v]?.subject) || '—'}
                      </Text>
                      <Text
                        style={{
                          color: isFrozen ? good : accent,
                          fontSize: 10,
                          fontWeight: '700',
                          marginTop: 2,
                        }}
                      >
                        {busy === busyKey ? 'Working…' : isFrozen ? 'Winner frozen' : 'Promote'}
                      </Text>
                    </TouchableOpacity>
                  );
                })}
              </View>

              {frozenVariant ? (
                <TouchableOpacity
                  disabled={!!busy}
                  onPress={() => revert(bucket)}
                  data-testid={`newsletter-subject-ab-revert-${bucket}`}
                  testID={`newsletter-subject-ab-revert-${bucket}`}
                  style={{
                    paddingVertical: 6,
                    paddingHorizontal: 10,
                    borderRadius: 8,
                    borderWidth: 1,
                    borderColor: warn,
                  }}
                >
                  <Text style={{ color: warn, fontSize: 11, fontWeight: '700' }}>
                    {busy === `${bucket}:revert` ? 'Reverting…' : 'Revert'}
                  </Text>
                </TouchableOpacity>
              ) : null}
            </View>
          );
        })
      )}
    </View>
  );
}
