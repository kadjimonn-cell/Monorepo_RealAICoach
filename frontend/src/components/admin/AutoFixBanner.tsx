import React, { useEffect, useState, useCallback } from 'react';
import { View, Text, ActivityIndicator } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';

import { useAdminTheme } from '../../hooks/useAdminTheme';
import { useTranslation } from '../../hooks/useTranslation';
import { useHybridPolling } from '../../hooks/useHybridPolling';
interface AutoFixBannerProps {
  domain: string;
  refreshInterval?: number; // ms, default 30s
}

function makeC(AC: any) { return {
  bg: AC.bgAlt, card: AC.border, border: AC.borderStrong,
  text: AC.text, muted: AC.textMuted, dim: AC.textDim,
  green: 'var(--app-success)', red: 'var(--app-error)', amber: 'var(--app-warning)', blue: 'var(--app-primary)',
}; }

// Static colors for STATUS_CONFIG (module-level)
const STATUS_COLORS = {
  green: 'var(--app-success)', red: 'var(--app-error)', amber: 'var(--app-warning)', blue: 'var(--app-primary)', dim: 'var(--app-text-muted)', // @theme-ok brand/role/state identifier
};

const STATUS_CONFIG: Record<string, { color: string; icon: string; label: string }> = {
  healthy: { color: STATUS_COLORS.green, icon: 'shield-checkmark', label: 'Healthy' },
  fixed: { color: STATUS_COLORS.blue, icon: 'construct', label: 'Auto-Fixed' },
  warning: { color: STATUS_COLORS.amber, icon: 'alert-circle', label: 'Warning' },
  stale: { color: STATUS_COLORS.dim, icon: 'time', label: 'Awaiting Scan' },
  error: { color: STATUS_COLORS.red, icon: 'close-circle', label: 'Error' },
  unknown: { color: STATUS_COLORS.dim, icon: 'help-circle', label: 'Unknown' },
};

export default function AutoFixBanner({ domain, refreshInterval = 30000 }: AutoFixBannerProps) {
  const AC = useAdminTheme();
  const { t } = useTranslation();
  const tx = React.useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);
  const C = React.useMemo(() => makeC(AC), [AC]);
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  const fetchStatus = useCallback(async () => {
    try {
      const res = await api.get(`/admin/auto-fix-engine/status/${domain}`);
      setData(res.data);
    } catch {
      setData({ status: 'error', issues_found: 0, fixes_applied: 0, last_run: null, label: domain });
    } finally {
      setLoading(false);
    }
  }, [domain]);

  useEffect(() => {
    fetchStatus();
  }, [fetchStatus]);

  useHybridPolling({
    enabled: true,
    errorScope: `admin/auto-fix-banner/${domain}/hybrid-refresh`,
    onTick: fetchStatus,
    runOnMount: false,
    slowIntervalMs: refreshInterval,
    fastIntervalMs: Math.max(15000, Math.floor(refreshInterval / 2)),
    wsEnabled: false,
  });

  if (loading) {
    return (
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, padding: 10, backgroundColor: C.card, borderRadius: 8, marginBottom: 12, borderWidth: 1, borderColor: C.border }}>
        <ActivityIndicator size="small" color={C.blue} />
        <Text style={{ color: C.muted, fontSize: 11 }}>{tx('admin.autoFixBanner.scanning', 'Auto-Fix Engine scanning...')}</Text>
      </View>
    );
  }

  const status = data?.status || 'unknown';
  const cfg = STATUS_CONFIG[status] || STATUS_CONFIG.unknown;
  const issues = data?.issues_found || 0;
  const fixes = data?.fixes_applied || 0;
  const lastRun = data?.last_run;
  const action = data?.fix_action || '';

  const timeAgo = lastRun ? _timeAgo(lastRun) : 'Never';

  return (
    <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', padding: 10, backgroundColor: C.card, borderRadius: 8, marginBottom: 12, borderWidth: 1, borderColor: C.border, borderLeftWidth: 3, borderLeftColor: cfg.color }} data-testid={`autofix-banner-${domain}`} testID={`autofix-banner-${domain}`}>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, flex: 1 }}>
        <Ionicons name={cfg.icon as any} size={16} color={cfg.color} />
        <View>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
            <Text style={{ color: cfg.color, fontSize: 11, fontWeight: '700' }}>{cfg.label}</Text>
            {issues > 0 && (
              <Text style={{ color: C.muted, fontSize: 10 }}>
                {fixes}/{issues} fixed
              </Text>
            )}
          </View>
          <Text style={{ color: C.dim, fontSize: 9, marginTop: 1 }}>
            Last scan: {timeAgo} {action ? `\u00B7 ${action.replace(/_/g, ' ')}` : ''}
          </Text>
        </View>
      </View>
      <View style={{ backgroundColor: (globalThis as any).__alphaColor(cfg.color, '15'), paddingHorizontal: 8, paddingVertical: 3, borderRadius: 4 }}>
        <Text style={{ color: cfg.color, fontSize: 9, fontWeight: '700' }}>AUTO</Text>
      </View>
    </View>
  );
}

function _timeAgo(isoStr: string): string {
  try {
    const d = new Date(isoStr);
    const now = new Date();
    const diff = Math.floor((now.getTime() - d.getTime()) / 1000);
    if (diff < 60) return 'Just now';
    if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
    if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
    return `${Math.floor(diff / 86400)}d ago`;
  } catch {
    return 'Unknown';
  }
}
