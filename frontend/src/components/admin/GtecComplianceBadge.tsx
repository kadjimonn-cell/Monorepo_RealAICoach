import React, { useEffect, useState } from 'react';
import { View, Text, ActivityIndicator } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { useAdminTheme } from '../../hooks/useAdminTheme';
import { useTranslation } from '../../hooks/useTranslation';

type ComplianceRuntime = {
  run_id?: string;
  status?: 'pass' | 'warn' | 'fail' | string;
  score?: number;
  enforcement_mode?: string;
  global_block?: boolean;
  scanned_at?: string;
  summary?: Record<string, number>;
};

/**
 * GTEC ✓ 100% compliance badge for the admin footer.
 *
 * Reads the live runtime report from `/api/config/v2-compliance/runtime`
 * and renders a compact status pill (color-coded by score). Hidden
 * gracefully on fetch failure — this is footer chrome, not critical UI.
 */
export const GtecComplianceBadge: React.FC = () => {
  const AC = useAdminTheme();
  const { t } = useTranslation();
  const tx = React.useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);
  const [data, setData] = useState<ComplianceRuntime | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await api.get('/config/v2-compliance/runtime');
        if (!cancelled) setData(res.data || null);
      } catch {
        if (!cancelled) setData(null);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  if (loading) {
    return (
      <View
        style={{
          flexDirection: 'row', alignItems: 'center', gap: 6,
          alignSelf: 'center', paddingVertical: 6, paddingHorizontal: 10,
          marginTop: 20, marginBottom: 12,
          borderRadius: 999,
          backgroundColor: AC.surfaceAlt,
          borderWidth: 1, borderColor: AC.border,
        }}
        data-testid="gtec-badge-loading"
        testID="gtec-badge-loading"
      >
        <ActivityIndicator size="small" color={AC.textDim} />
        <Text style={{ color: AC.textDim, fontSize: 10, fontWeight: '700' }}>{tx('admin.gtecComplianceBadge.scanning', 'GTEC scanning…')}</Text>
      </View>
    );
  }

  if (!data) return null;

  const score = typeof data.score === 'number' ? Math.round(data.score) : null;
  const status = String(data.status || '').toLowerCase();
  const isPerfect = score === 100 && status === 'pass';
  const isPassing = status === 'pass';
  const accent = isPerfect ? 'var(--app-success)' : isPassing ? 'var(--app-primary)' : status === 'warn' ? 'var(--app-warning)' : 'var(--app-error)';
  const label = isPerfect
    ? 'GTEC ✓ 100%'
    : isPassing
      ? `GTEC ${score ?? '?'}%`
      : status === 'warn'
        ? `GTEC warn (${score ?? '?'}%)`
        : `GTEC fail (${score ?? '?'}%)`;

  return (
    <View
      style={{
        flexDirection: 'row', alignItems: 'center', gap: 6,
        alignSelf: 'center', paddingVertical: 6, paddingHorizontal: 12,
        marginTop: 20, marginBottom: 12,
        borderRadius: 999,
        backgroundColor: AC.surfaceAlt,
        borderWidth: 1, borderColor: accent,
      }}
      accessibilityLabel={`GTEC compliance score ${score ?? 'unknown'} percent — ${status}`}
      data-testid={`gtec-badge-${isPerfect ? 'perfect' : status || 'unknown'}`}
      testID={`gtec-badge-${isPerfect ? 'perfect' : status || 'unknown'}`}
    >
      <Ionicons
        name={isPerfect ? 'shield-checkmark' : isPassing ? 'shield' : status === 'warn' ? 'warning' : 'close-circle'}
        size={11}
        color={accent}
      />
      <Text style={{ color: accent, fontSize: 10, fontWeight: '800', letterSpacing: 0.3 }}>
        {label}
      </Text>
      {data.enforcement_mode ? (
        <Text style={{ color: AC.textDim, fontSize: 9, fontWeight: '600' }}>
          · {data.enforcement_mode}
        </Text>
      ) : null}
    </View>
  );
};

export default GtecComplianceBadge;
