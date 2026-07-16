import React, { useCallback, useEffect, useMemo, useState } from 'react';
// @gls-exempt — intentional fixed-width UI element (sidebar/chat/label/toast)
import { ActivityIndicator, ScrollView, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import api from '../../services/api';
import { useAdminTheme } from '../../hooks/useAdminTheme';
import { useHybridPolling } from '../../hooks/useHybridPolling';
import { useTranslation } from '../../hooks/useTranslation';
import { humanizeAdminToken, normalizeAdminRuntimeCopy, normalizeAdminStatusTone } from '../../i18n/adminCopyGuard';

type Props = {
  colors?: any;
  compact?: boolean;
};

const SEMANTIC = {
  success: 'var(--app-success)',
  warning: 'var(--app-warning)',
  error: 'var(--app-error)',
  info: 'var(--app-primary)',
  cyan: 'var(--app-primary)',
};

function getStatusTone(status: string) {
  switch (String(status || '').toUpperCase()) {
    case 'PASS':
      return SEMANTIC.success;
    case 'WARNING':
      return SEMANTIC.warning;
    case 'FAIL':
      return SEMANTIC.error;
    default:
      return 'var(--app-text-muted)';
  }
}

function formatCheckedAt(value?: string | null) {
  if (!value) return 'Unknown';
  try {
    return new Date(value).toLocaleString();
  } catch {
    return value;
  }
}

export const AdminSurfaceHealthMatrix = ({ colors: _colors, compact = false }: Props) => {
  const colors = useAdminTheme();
  const router = useRouter();
  const { tx } = useTranslation();
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [snapshot, setSnapshot] = useState<any>(null);
  const [error, setError] = useState('');

  const cardBg = colors?.card;
  const softBg = colors?.bgSoft;
  const border = colors?.border;
  const text = colors?.text;
  const textMuted = colors?.textMuted;
  const textSec = colors?.textSec;

  const snapshotView = useMemo(() => {
    const surfaces = Array.isArray(snapshot?.surfaces)
      ? snapshot.surfaces.map((row: any, idx: number) => ({
          ...row,
          feature_key: String(row?.feature_key || `surface-${idx}`),
          status: normalizeAdminStatusTone(row?.status, 'UNKNOWN'),
          label: normalizeAdminRuntimeCopy(row?.label, tx('admin.adminSurfaceHealthMatrix.surface.fallback', 'Admin surface')),
          surface_type: humanizeAdminToken(row?.surface_type, tx('admin.adminSurfaceHealthMatrix.type.fallback', 'Route')),
          details: normalizeAdminRuntimeCopy(row?.details, tx('admin.adminSurfaceHealthMatrix.details.fallback', 'Watchdog details unavailable.')),
        }))
      : [];

    const alerts = Array.isArray(snapshot?.alerts)
      ? snapshot.alerts.map((alert: any, idx: number) => ({
          ...alert,
          status: normalizeAdminStatusTone(alert?.status, 'WARNING'),
          label: normalizeAdminRuntimeCopy(alert?.label, tx('admin.adminSurfaceHealthMatrix.alert.fallback', `Watchdog alert ${idx + 1}`)),
          details: normalizeAdminRuntimeCopy(alert?.details, tx('admin.adminSurfaceHealthMatrix.details.fallback', 'Watchdog details unavailable.')),
        }))
      : [];

    const notes = Array.isArray(snapshot?.notes)
      ? snapshot.notes.map((note: unknown, idx: number) => normalizeAdminRuntimeCopy(note, tx('admin.adminSurfaceHealthMatrix.notes.fallback', `Watchdog note ${idx + 1}`)))
      : [];

    return {
      ...snapshot,
      status: normalizeAdminStatusTone(snapshot?.status, 'UNKNOWN'),
      staleness_label: normalizeAdminRuntimeCopy(snapshot?.staleness_label, tx('admin.adminSurfaceHealthMatrix.staleness.unknown', 'Unknown age')),
      summary: normalizeAdminRuntimeCopy(snapshot?.summary, tx('admin.adminSurfaceHealthMatrix.summary.fallback', 'Latest admin audit snapshot found.')),
      surfaces,
      alerts,
      notes,
    };
  }, [snapshot, tx]);

  const loadSnapshot = useCallback(async (silent = false) => {
    if (!silent) setLoading(true);
    else setRefreshing(true);
    setError('');
    try {
      const res = await api.get('/admin/executive/admin-surface-watchdog', { silentLoading: true });
      setSnapshot(res.data || null);
    } catch (e: any) {
      setError(e?.response?.data?.detail || e?.message || 'Unable to load admin watchdog snapshot.');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    loadSnapshot();
  }, [loadSnapshot]);

  useHybridPolling({
    enabled: true,
    errorScope: 'admin/admin-surface-health/hybrid-refresh',
    onTick: () => loadSnapshot(true),
    runOnMount: false,
    slowIntervalMs: 45000,
    fastIntervalMs: 15000,
  });

  const summaryCards = useMemo(() => {
    return [
      {
        id: 'status',
        label: tx('admin.adminSurfaceHealthMatrix.summary.status', 'Watchdog Status'),
        value: snapshotView?.status || 'UNKNOWN',
        tone: getStatusTone(snapshotView?.status),
        icon: 'shield-checkmark',
      },
      {
        id: 'coverage',
        label: tx('admin.adminSurfaceHealthMatrix.summary.coverage', 'Passing Surfaces'),
        value: `${snapshotView?.passing_surfaces ?? 0}/${snapshotView?.total_surfaces ?? 0}`,
        tone: SEMANTIC.info,
        icon: 'grid',
      },
      {
        id: 'freshness',
        label: tx('admin.adminSurfaceHealthMatrix.summary.freshness', 'Audit Freshness'),
        value: snapshotView?.staleness_label || tx('admin.adminSurfaceHealthMatrix.staleness.unknown', 'Unknown age'),
        tone: snapshotView?.staleness_label === 'Fresh' ? SEMANTIC.success : snapshotView?.staleness_label === 'Aging' ? SEMANTIC.warning : SEMANTIC.error,
        icon: 'time',
      },
      {
        id: 'report',
        label: tx('admin.adminSurfaceHealthMatrix.summary.report', 'Source Report'),
        value: snapshotView?.report_id || 'n/a',
        tone: SEMANTIC.cyan,
        icon: 'document-text',
      },
    ];
  }, [snapshotView, tx]);

  const openRoute = useCallback((route: string) => {
    if (!route) return;
    router.push(route as any);
  }, [router]);

  return (
    <View style={[styles.card, { backgroundColor: cardBg, borderColor: border }]} data-testid="admin-surface-health-matrix" testID="admin-surface-health-matrix">
      <View style={styles.headerRow}>
        <View style={styles.headerTitleWrap}>
          <View style={[styles.iconBadge, { backgroundColor: `${SEMANTIC.info}20` }]}>
            <Ionicons name="pulse" size={16} color={SEMANTIC.info} />
          </View>
          <View style={{ flex: 1 }}>
            <Text style={[styles.title, { color: text }]} data-testid="admin-surface-health-matrix-title" testID="admin-surface-health-matrix-title">{tx('admin.adminSurfaceHealthMatrix.auto.text.001', 'Admin Surface Health Matrix')}</Text>
            <Text style={[styles.subtitle, { color: textMuted }]} data-testid="admin-surface-health-matrix-subtitle" testID="admin-surface-health-matrix-subtitle">{tx('admin.adminSurfaceHealthMatrix.auto.text.002', 'Scheduled in-app watchdog snapshot for admin-only routes, tabs, theme integrity, freshness, and live update behavior.')}</Text>
          </View>
        </View>

        <TouchableOpacity
          onPress={() => loadSnapshot(true)}
          disabled={refreshing}
          style={[styles.refreshButton, { borderColor: border, backgroundColor: softBg }, refreshing && { opacity: 0.7 }]}
          data-testid="admin-surface-health-refresh-button"
          testID="admin-surface-health-refresh-button"
        >
          <Ionicons name="refresh" size={13} color={text} />
          <Text style={[styles.refreshButtonText, { color: text }]}>{refreshing ? tx('admin.adminSurfaceHealthMatrix.actions.refreshing', 'Refreshing…') : tx('admin.adminSurfaceHealthMatrix.actions.refresh', 'Refresh')}</Text>
        </TouchableOpacity>
      </View>

      {loading ? (
        <View style={styles.loadingWrap} data-testid="admin-surface-health-loading" testID="admin-surface-health-loading">
          <ActivityIndicator color={SEMANTIC.info} />
          <Text style={{ color: textMuted, fontSize: 12, marginTop: 10 }}>{tx('admin.adminSurfaceHealthMatrix.auto.text.003', 'Loading admin watchdog snapshot…')}</Text>
        </View>
      ) : error ? (
        <View style={[styles.messageBox, { borderColor: `${SEMANTIC.error}35`, backgroundColor: `${SEMANTIC.error}15` }]} data-testid="admin-surface-health-error" testID="admin-surface-health-error">
          <Ionicons name="alert-circle" size={16} color={SEMANTIC.error} />
          <Text style={{ color: text, fontSize: 12, fontWeight: '600', flex: 1 }}>{error}</Text>
        </View>
      ) : (
        <>
          <View style={styles.summaryGrid}>
            {summaryCards.map((item) => (
              <View key={item.id} style={[styles.summaryCard, { backgroundColor: softBg, borderColor: border, borderLeftColor: item.tone }]} data-testid={`admin-surface-health-summary-${item.id}`} testID={`admin-surface-health-summary-${item.id}`}>
                <View style={styles.summaryLabelRow}>
                  <Ionicons name={item.icon as any} size={14} color={item.tone} />
                  <Text style={[styles.summaryLabel, { color: textMuted }]}>{item.label}</Text>
                </View>
                <Text style={[styles.summaryValue, { color: text }]} numberOfLines={1}>{item.value}</Text>
              </View>
            ))}
          </View>

          <View style={[styles.messageBox, { borderColor: `${getStatusTone(snapshotView?.status)}35`, backgroundColor: `${getStatusTone(snapshotView?.status)}15` }]} data-testid="admin-surface-health-status-banner" testID="admin-surface-health-status-banner">
            <Ionicons name={snapshotView?.status === 'PASS' ? 'checkmark-circle' : snapshotView?.status === 'WARNING' ? 'warning' : 'alert-circle'} size={16} color={getStatusTone(snapshotView?.status)} />
            <View style={{ flex: 1 }}>
              <Text style={{ color: text, fontSize: 12, fontWeight: '700' }}>{snapshotView?.summary || tx('admin.adminSurfaceHealthMatrix.summary.fallback', 'Latest admin audit snapshot found.')}</Text>
              <Text style={{ color: textSec, fontSize: 11, marginTop: 4 }}>{tx('admin.adminSurfaceHealthMatrix.meta.lastChecked', 'Last checked:')} {formatCheckedAt(snapshotView?.checked_at)} • {tx('admin.adminSurfaceHealthMatrix.meta.autoRefresh', 'Auto-refresh: every 30 seconds')}</Text>
            </View>
          </View>

          {(snapshotView?.alerts || []).length > 0 && (
            <View style={[styles.alertList, { backgroundColor: softBg, borderColor: border }]} data-testid="admin-surface-health-alert-list" testID="admin-surface-health-alert-list">
              <Text style={{ color: text, fontSize: 12, fontWeight: '800' }}>{tx('admin.adminSurfaceHealthMatrix.auto.text.004', 'Watchdog Alerts')}</Text>
              {(snapshotView?.alerts || []).map((alert: any, idx: number) => (
                <View key={`${alert?.label}-${idx}`} style={[styles.alertRow, { borderColor: border }]} data-testid={`admin-surface-health-alert-${idx}`} testID={`admin-surface-health-alert-${idx}`}>
                  <Text style={{ color: getStatusTone(alert?.status), fontSize: 10, fontWeight: '800' }}>{alert?.status}</Text>
                  <Text style={{ color: text, fontSize: 11, fontWeight: '700', flex: 1 }}>{alert?.label}</Text>
                  <TouchableOpacity onPress={() => openRoute(alert?.route)} data-testid={`admin-surface-health-alert-open-${idx}`} testID={`admin-surface-health-alert-open-${idx}`}>
                    <Text style={{ color: SEMANTIC.info, fontSize: 11, fontWeight: '700' }}>{tx('admin.adminSurfaceHealthMatrix.auto.text.005', 'Open')}</Text>
                  </TouchableOpacity>
                </View>
              ))}
            </View>
          )}

          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ paddingBottom: 2 }} data-testid="admin-surface-health-scroll" testID="admin-surface-health-scroll">
            <View style={[styles.matrixTable, { minWidth: compact ? 780 : 920 }]}> 
              <View style={[styles.tableHeader, { borderColor: border, backgroundColor: softBg }]}>
                <Text style={[styles.headerCell, styles.statusCell, { color: textMuted }]}>{tx('admin.adminSurfaceHealthMatrix.auto.text.006', 'Status')}</Text>
                <Text style={[styles.headerCell, styles.labelCell, { color: textMuted }]}>{tx('admin.adminSurfaceHealthMatrix.auto.text.007', 'Surface')}</Text>
                <Text style={[styles.headerCell, styles.typeCell, { color: textMuted }]}>{tx('admin.adminSurfaceHealthMatrix.auto.text.008', 'Type')}</Text>
                <Text style={[styles.headerCell, styles.detailsCell, { color: textMuted }]}>{tx('admin.adminSurfaceHealthMatrix.auto.text.009', 'Details')}</Text>
                <Text style={[styles.headerCell, styles.actionCell, { color: textMuted }]}>{tx('admin.adminSurfaceHealthMatrix.auto.text.010', 'Action')}</Text>
              </View>

              {(snapshotView?.surfaces || []).map((row: any, idx: number) => (
                <View key={`${row?.feature_key}-${idx}`} style={[styles.tableRow, { borderColor: border, backgroundColor: idx % 2 === 0 ? 'transparent' : softBg }]} data-testid={`admin-surface-health-row-${row?.feature_key}`} testID={`admin-surface-health-row-${row?.feature_key}`}>
                  <View style={[styles.statusCell, styles.cell]}>
                    <View style={[styles.statusPill, { backgroundColor: `${getStatusTone(row?.status)}18`, borderColor: `${getStatusTone(row?.status)}35` }]}>
                      <Text style={{ color: getStatusTone(row?.status), fontSize: 10, fontWeight: '800' }}>{row?.status || 'UNKNOWN'}</Text>
                    </View>
                  </View>
                  <View style={[styles.labelCell, styles.cell]}>
                    <Text style={{ color: text, fontSize: 11, fontWeight: '700' }}>{row?.label}</Text>
                    <Text style={{ color: textMuted, fontSize: 10, marginTop: 3 }}>{formatCheckedAt(row?.checked_at)}</Text>
                  </View>
                  <View style={[styles.typeCell, styles.cell]}>
                    <Text style={{ color: textSec, fontSize: 10 }}>{row?.surface_type}</Text>
                  </View>
                  <View style={[styles.detailsCell, styles.cell]}>
                    <Text style={{ color: textMuted, fontSize: 10, lineHeight: 16 }}>{row?.details}</Text>
                  </View>
                  <View style={[styles.actionCell, styles.cell]}>
                    <TouchableOpacity onPress={() => openRoute(row?.route)} style={[styles.inlineButton, { backgroundColor: `${SEMANTIC.info}16`, borderColor: `${SEMANTIC.info}30` }]} data-testid={`admin-surface-health-open-${row?.feature_key}`} testID={`admin-surface-health-open-${row?.feature_key}`}>
                      <Text style={{ color: SEMANTIC.info, fontSize: 10, fontWeight: '800' }}>{tx('admin.adminSurfaceHealthMatrix.auto.text.011', 'Open')}</Text>
                    </TouchableOpacity>
                  </View>
                </View>
              ))}
            </View>
          </ScrollView>

          {(snapshotView?.notes || []).length > 0 && (
            <View style={[styles.notesBox, { backgroundColor: softBg, borderColor: border }]} data-testid="admin-surface-health-notes" testID="admin-surface-health-notes">
              <Text style={{ color: text, fontSize: 12, fontWeight: '800' }}>{tx('admin.adminSurfaceHealthMatrix.auto.text.012', 'Latest Watchdog Notes')}</Text>
              {(snapshotView?.notes || []).map((note: string, idx: number) => (
                <Text key={`${note}-${idx}`} style={{ color: textMuted, fontSize: 10, marginTop: 6, lineHeight: 16 }} data-testid={`admin-surface-health-note-${idx}`} testID={`admin-surface-health-note-${idx}`}>• {note}</Text>
              ))}
            </View>
          )}
        </>
      )}
    </View>
  );
};

const styles = StyleSheet.create({
  card: {
    borderRadius: 16,
    borderWidth: 1,
    padding: 16,
    gap: 12,
  },
  headerRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    justifyContent: 'space-between',
    gap: 10,
    flexWrap: 'wrap',
  },
  headerTitleWrap: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 10,
    flex: 1,
    minWidth: 220,
  },
  iconBadge: {
    width: 32,
    height: 32,
    borderRadius: 10,
    alignItems: 'center',
    justifyContent: 'center',
  },
  title: {
    fontSize: 14,
    fontWeight: '800',
  },
  subtitle: {
    fontSize: 11,
    marginTop: 4,
    lineHeight: 17,
  },
  refreshButton: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    borderRadius: 8,
    borderWidth: 1,
    paddingHorizontal: 12,
    paddingVertical: 7,
  },
  refreshButtonText: {
    fontSize: 11,
    fontWeight: '700',
  },
  loadingWrap: {
    paddingVertical: 30,
    alignItems: 'center',
  },
  summaryGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 10,
  },
  summaryCard: {
    flex: 1,
    minWidth: 155,
    borderRadius: 12,
    borderWidth: 1,
    borderLeftWidth: 3,
    padding: 12,
  },
  summaryLabelRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  summaryLabel: {
    fontSize: 10,
    fontWeight: '700',
    textTransform: 'uppercase',
  },
  summaryValue: {
    fontSize: 18,
    fontWeight: '800',
    marginTop: 8,
  },
  messageBox: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    borderRadius: 12,
    borderWidth: 1,
    paddingHorizontal: 12,
    paddingVertical: 10,
  },
  alertList: {
    borderRadius: 12,
    borderWidth: 1,
    padding: 12,
    gap: 8,
  },
  alertRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    borderWidth: 1,
    borderRadius: 10,
    paddingHorizontal: 10,
    paddingVertical: 8,
  },
  matrixTable: {
    borderRadius: 12,
    overflow: 'hidden',
  },
  tableHeader: {
    flexDirection: 'row',
    borderWidth: 1,
  },
  tableRow: {
    flexDirection: 'row',
    borderLeftWidth: 1,
    borderRightWidth: 1,
    borderBottomWidth: 1,
  },
  headerCell: {
    paddingHorizontal: 10,
    paddingVertical: 10,
    fontSize: 10,
    fontWeight: '700',
    textTransform: 'uppercase',
  },
  cell: {
    paddingHorizontal: 10,
    paddingVertical: 10,
    justifyContent: 'center',
  },
  statusCell: { width: 96 },
  labelCell: { width: 190 },
  typeCell: { width: 170 },
  detailsCell: { width: 350 },
  actionCell: { width: 100 },
  statusPill: {
    alignSelf: 'flex-start',
    borderRadius: 999,
    borderWidth: 1,
    paddingHorizontal: 8,
    paddingVertical: 4,
  },
  inlineButton: {
    alignSelf: 'flex-start',
    borderRadius: 8,
    borderWidth: 1,
    paddingHorizontal: 10,
    paddingVertical: 6,
  },
  notesBox: {
    borderRadius: 12,
    borderWidth: 1,
    padding: 12,
  },
});

export default AdminSurfaceHealthMatrix;
/* i18n-probe t('i18n.auto.probe') */
