import React, { useEffect, useState, useCallback } from 'react';
import {
  View, Text, ScrollView, TouchableOpacity, ActivityIndicator,
  StyleSheet, useWindowDimensions, RefreshControl, Platform,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../src/services/api';
import { useAuth } from '../src/context/AuthContext';
import AppShell from '../src/components/AppShell';
import { AdminRouteGate } from '../src/components/auth/AdminRouteGate';
import { AnalyticsSkeleton, FadeSlideIn } from '../src/components/SkeletonLoaders';
import { useTranslation } from '../src/hooks/useTranslation';

import { useAdminTheme } from '../src/hooks/useAdminTheme';
import { handleAppRecoverableError } from '../src/utils/appRecoverableError';
const C = {
  bg: 'transparent', surface: 'var(--app-card-bg)', surfaceAlt: 'var(--app-card-bg)',
  border: 'var(--app-border)', borderMd: 'var(--app-border-strong)',
  indigoText: 'var(--app-primary)' as any,
  purpleText: 'var(--app-info)' as any,
  white: 'var(--app-text)' as any,
  gray100: 'var(--app-text-sec)' as any,
  gray300: 'var(--app-text-muted)' as any,
  gray400: 'var(--app-text-muted)' as any,
  teal: 'var(--app-primary)', indigo: 'var(--app-primary)', gold: 'var(--app-warning)', rose: 'var(--app-primary)',
  sky: 'var(--app-primary)', emerald: 'var(--app-success)', purple: 'var(--app-primary)',
};

const glassBlurStyle = Platform.OS === 'web'
  ? ({ backdropFilter: 'blur(18px)', WebkitBackdropFilter: 'blur(18px)' } as any)
  : {};

interface HealthData { status: string; checks: { database: any; memory: any; cpu: any; uptime: any; websockets: any; collections: any } }
interface Scan { scan_id: string; timestamp: string; status: string; issues_count: number; issues: any[]; stats?: any }
interface Backup { backup_id: string; timestamp: string; status: string; collections: Record<string, { document_count: number }> }
interface NightlyDriftData {
  nightly?: {
    generated_at?: string;
    newly_missing_count?: number;
    resolved_from_baseline_count?: number;
    missing_now_count?: number;
    status?: string;
  };
  baseline?: {
    remaining_count?: number;
    generated_at?: string;
  };
  burndown?: {
    generated_at?: string;
    batch_size?: number;
    selected_count?: number;
    baseline_before_count?: number;
    next_baseline_count?: number;
  };
}

export default function AdminSystemDashboard() {
  const AC = useAdminTheme();
  const { t } = useTranslation();
  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };
  const { user } = useAuth();
  const { width } = useWindowDimensions();
  const isDesktop = width >= 1024;
  const cols = isDesktop ? 4 : width >= 600 ? 2 : 1;

  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [health, setHealth] = useState<HealthData | null>(null);
  const [scans, setScans] = useState<Scan[]>([]);
  const [backups, setBackups] = useState<Backup[]>([]);
  const [drift, setDrift] = useState<NightlyDriftData | null>(null);
  const [triggering, setTriggering] = useState<string | null>(null);
  const [recoverableError, setRecoverableError] = useState('');

  const fetchAll = useCallback(async () => {
    try {
      const [h, s, b] = await Promise.all([
        api.get('/system/health'),
        api.get('/admin/system/integrity'),
        api.get('/admin/system/backups'),
      ]);
      setHealth(h.data);
      setScans(s.data.scans || []);
      setBackups(b.data.backups || []);

      try {
        const d = await api.get('/admin/i18n/nightly-drift');
        setDrift(d.data || null);
      } catch {
        try {
          const publicDrift = await api.get('/public/i18n/nightly-drift-summary');
          setDrift(publicDrift.data || null);
        } catch (error) {
          handleAppRecoverableError({
            scope: 'admin-system.load-drift-fallback',
            error,
            message: tx('adminSystem.errors.driftSummaryUnavailable', 'Could not load drift summary right now.'),
            setError: setRecoverableError,
            onRetry: () => { void fetchAll(); },
          
        notifyMode: 'dialog',
        userInitiated: true,
      });
          setDrift(null);
        }
      }
      setRecoverableError('');
    } catch (e) {
      handleAppRecoverableError({
        scope: 'admin-system.fetch-all',
        error: e,
        message: tx('adminSystem.errors.loadFailed', 'Could not refresh admin system data.'),
        setError: setRecoverableError,
        onRetry: () => { void fetchAll(); },
      
        notifyMode: 'dialog',
        userInitiated: true,
      });
    }
    finally { setLoading(false); setRefreshing(false); }
  }, []);

  useEffect(() => { fetchAll(); const iv = setInterval(fetchAll, 30000); return () => clearInterval(iv); }, [fetchAll]);

  const trigger = async (type: 'integrity' | 'backups') => {
    setTriggering(type);
    try {
      await api.post(`/admin/system/${type}/run`);
      setTimeout(fetchAll, 3000);
    } catch (error) { handleAppRecoverableError({ scope: 'admin-system.tsx#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
    finally { setTriggering(null); }
  };

  const fmt = (iso: string) => { try { const d = new Date(iso); return d.toLocaleString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }); } catch { return iso; } };

  return (
    <AdminRouteGate returnTo="/admin-system">
    <AppShell>
      <View style={{ flex: 1, backgroundColor: AC.bg }}>
      <ScrollView
        style={{ flex: 1 }}
        contentContainerStyle={{ padding: isDesktop ? 32 : 16, paddingBottom: 80 }}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); fetchAll(); }} tintColor={C.teal} />}
      >
        {recoverableError ? (
          <View
            style={{ marginHorizontal: 20, marginBottom: 10, marginTop: 14, paddingHorizontal: 12, paddingVertical: 10, borderRadius: 10, borderWidth: 1, borderColor: AC.error + '35', backgroundColor: AC.errorSoft, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 10 }}
            data-testid="admin-system-recoverable-error-banner"
            testID="admin-system-recoverable-error-banner"
          >
            <Text style={{ color: AC.errorText, fontSize: 12, fontWeight: '700', flex: 1 }} data-testid="admin-system-recoverable-error-text" testID="admin-system-recoverable-error-text">{recoverableError}</Text>
            <TouchableOpacity
              onPress={() => { void fetchAll(); }}
              style={{ backgroundColor: AC.error, borderRadius: 8, paddingHorizontal: 10, paddingVertical: 8 }}
              data-testid="admin-system-recoverable-error-retry"
              testID="admin-system-recoverable-error-retry"
            >
              <Text style={{ color: AC.primaryText, fontSize: 11, fontWeight: '800' }}>{tx('common.retry', 'Retry')}</Text>
            </TouchableOpacity>
          </View>
        ) : null}
        {/* Header */}
        <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 24 }}>
          <View>
            <Text style={s.title} data-testid="admin-system-title" testID="admin-system-title">{tx('autofix.batch9.system.dashboard', 'System Dashboard')}</Text>
            <Text style={s.subtitle}>{tx('autofix.batch9.platform.health.integrity.scans.backups', 'Platform health, integrity scans & backups')}</Text>
          </View>
          <View style={{ flexDirection: 'row', gap: 10 }}>
            <TouchableOpacity style={[s.triggerBtn, { backgroundColor: (globalThis as any).__alphaColor(C.teal, '18'), borderColor: (globalThis as any).__alphaColor(C.teal, '40') }]} onPress={() => trigger('integrity')} disabled={triggering !== null} data-testid="trigger-scan-btn" testID="trigger-scan-btn">
              {triggering === 'integrity' ? <ActivityIndicator size="small" color={C.teal} /> : <Ionicons name="shield-checkmark" size={16} color={C.teal} />}
              <Text style={[s.triggerText, { color: C.teal }]}>{tx('autofix.batch9.run.scan', 'Run Scan')}</Text>
            </TouchableOpacity>
            <TouchableOpacity style={[s.triggerBtn, { backgroundColor: (globalThis as any).__alphaColor(C.indigo, '18'), borderColor: (globalThis as any).__alphaColor(C.indigo, '40') }]} onPress={() => trigger('backups')} disabled={triggering !== null} data-testid="trigger-backup-btn" testID="trigger-backup-btn">
              {triggering === 'backups' ? <ActivityIndicator size="small" color={C.indigoText} /> : <Ionicons name="cloud-upload" size={16} color={C.indigoText} />}
              <Text style={[s.triggerText, { color: C.indigoText }]}>{tx('autofix.batch9.run.backup', 'Run Backup')}</Text>
            </TouchableOpacity>
          </View>
        </View>

        {loading ? <AnalyticsSkeleton /> : (
          <FadeSlideIn>
            {/* Health KPI Cards */}
            {health && (
              <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 12, marginBottom: 24 }} data-testid="health-kpi-grid" testID="health-kpi-grid">
                <KpiCard icon="server" color={health.status === 'healthy' ? C.emerald : C.rose} label="Status" value={health.status === 'healthy' ? 'Healthy' : 'Degraded'} cols={cols} />
                <KpiCard icon="speedometer" color={C.sky} label="Database" value={health.checks.database?.status === 'up' ? 'Connected' : 'Down'} cols={cols} />
                <KpiCard icon="hardware-chip" color={C.purpleText} label="Memory" value={`${health.checks.memory?.percent || 0}%`} sub={`${health.checks.memory?.used_mb || 0} / ${health.checks.memory?.total_mb || 0} MB`} cols={cols} />
                <KpiCard icon="pulse" color={C.gold} label="CPU" value={`${health.checks.cpu?.percent || 0}%`} cols={cols} />
                <KpiCard icon="time" color={C.teal} label="Uptime" value={health.checks.uptime?.human || '—'} cols={cols} />
                <KpiCard icon="wifi" color={C.indigoText} label="WebSocket Users" value={String(health.checks.websockets?.authenticated_users || 0)} sub={`${health.checks.websockets?.total_connections || 0} total`} cols={cols} />
                <KpiCard icon="layers" color={C.emerald} label="Collections" value={String(health.checks.collections || 0)} cols={cols} />
                <KpiCard icon="globe" color={C.sky} label="Public Listeners" value={String(health.checks.websockets?.public_listeners || 0)} cols={cols} />
              </View>
            )}

            {/* i18n Drift Control */}
            <View style={s.card} data-testid="i18n-drift-control-card" testID="i18n-drift-control-card">
              <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
                <View>
                  <Text style={s.cardTitle} data-testid="i18n-drift-card-title" testID="i18n-drift-card-title">{tx('adminSystem.i18nDrift.title', 'i18n Drift Control')}</Text>
                  <Text style={s.cardTime} data-testid="i18n-drift-card-subtitle" testID="i18n-drift-card-subtitle">{tx('adminSystem.i18nDrift.subtitle', 'Nightly missing-key drift trend for Product & QA')}</Text>
                </View>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                  <View style={[s.statusDot, { backgroundColor: (drift?.nightly?.status || 'warning') === 'healthy' ? C.emerald : C.gold }]} />
                  <Text style={{ color: C.gray100, fontSize: 12, fontWeight: '700' }} data-testid="i18n-drift-status-label" testID="i18n-drift-status-label">
                    {(drift?.nightly?.status || 'warning') === 'healthy' ? tx('adminSystem.i18nDrift.healthy', 'Healthy') : tx('adminSystem.i18nDrift.attention', 'Attention')}
                  </Text>
                </View>
              </View>

              <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
                <StatPill label={tx('adminSystem.i18nDrift.newlyMissing', 'New Missing')} value={Number(drift?.nightly?.newly_missing_count || 0)} color={C.rose} dataTestId="i18n-drift-new-missing-pill" />
                <StatPill label={tx('adminSystem.i18nDrift.resolved', 'Resolved')} value={Number(drift?.nightly?.resolved_from_baseline_count || 0)} color={C.emerald} dataTestId="i18n-drift-resolved-pill" />
                <StatPill label={tx('adminSystem.i18nDrift.baselineRemaining', 'Baseline Remaining')} value={Number(drift?.baseline?.remaining_count || 0)} color={C.sky} dataTestId="i18n-drift-baseline-remaining-pill" />
                <StatPill label={tx('adminSystem.i18nDrift.weeklyBatch', 'Weekly Batch')} value={Number(drift?.burndown?.selected_count || 0)} color={C.gold} dataTestId="i18n-drift-weekly-batch-pill" />
              </View>

              <Text style={[s.cardTime, { marginTop: 10 }]} data-testid="i18n-drift-last-run" testID="i18n-drift-last-run">
                {tx('adminSystem.i18nDrift.lastRun', 'Last nightly run:')} {drift?.nightly?.generated_at ? fmt(drift.nightly.generated_at) : '—'}
              </Text>
            </View>

            {/* Integrity Scans */}
            <Text style={s.sectionTitle}>{tx('autofix.batch9.integrity.scans', 'Integrity Scans')}</Text>
            {scans.length === 0 ? (
              <View style={s.emptyCard}><Ionicons name="shield-outline" size={24} color={C.gray400} /><Text style={s.emptyText}>{tx('autofix.batch9.no.scans.yet.click.run.scan.to.start', 'No scans yet. Click "Run Scan" to start.')}</Text></View>
            ) : scans.map((scan, i) => (
              <View key={scan.scan_id} style={s.card} data-testid={`scan-card-${i}`} testID={`scan-card-${i}`}>
                <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                    <View style={[s.statusDot, { backgroundColor: scan.status === 'clean' ? C.emerald : C.gold }]} />
                    <Text style={s.cardTitle}>{scan.status === 'clean' ? 'Clean' : `${scan.issues_count} Issue(s)`}</Text>
                  </View>
                  <Text style={s.cardTime}>{fmt(scan.timestamp)}</Text>
                </View>
                {scan.stats && (
                  <View style={{ flexDirection: 'row', gap: 16, marginBottom: scan.issues.length ? 10 : 0 }}>
                    <StatPill label="Users" value={scan.stats.users} color={C.teal} />
                    <StatPill label="Payments" value={scan.stats.payments} color={C.indigoText} />
                    <StatPill label="Goals" value={scan.stats.goals} color={C.gold} />
                  </View>
                )}
                {scan.issues.length > 0 && scan.issues.map((iss: any, j: number) => (
                  <View key={j} style={s.issueRow}>
                    <Ionicons name={iss.action === 'cleaned' ? 'checkmark-circle' : 'alert-circle'} size={14} color={iss.action === 'cleaned' ? C.emerald : C.gold} />
                    <Text style={s.issueText}>{iss.type.replace(/_/g, ' ')} — {iss.count} ({iss.action})</Text>
                  </View>
                ))}
              </View>
            ))}

            {/* Backup History */}
            <Text style={[s.sectionTitle, { marginTop: 24 }]}>{tx('autofix.batch9.backup.history', 'Backup History')}</Text>
            {backups.length === 0 ? (
              <View style={s.emptyCard}><Ionicons name="cloud-outline" size={24} color={C.gray400} /><Text style={s.emptyText}>{tx('autofix.batch9.no.backups.yet.click.run.backup.to.start', 'No backups yet. Click "Run Backup" to start.')}</Text></View>
            ) : backups.map((bk, i) => (
              <View key={bk.backup_id} style={s.card} data-testid={`backup-card-${i}`} testID={`backup-card-${i}`}>
                <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                    <Ionicons name={bk.status === 'completed' ? 'checkmark-circle' : 'close-circle'} size={18} color={bk.status === 'completed' ? C.emerald : C.rose} />
                    <Text style={s.cardTitle}>{bk.backup_id}</Text>
                  </View>
                  <Text style={s.cardTime}>{fmt(bk.timestamp)}</Text>
                </View>
                <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
                  {Object.entries(bk.collections || {}).map(([name, info]) => (
                    <StatPill key={name} label={name.replace('ai_', '')} value={info.document_count} color={C.sky} />
                  ))}
                </View>
              </View>
            ))}
          </FadeSlideIn>
        )}
      </ScrollView>
      </View>
    </AppShell>
    </AdminRouteGate>
  );
}

function KpiCard({ icon, color, label, value, sub, cols }: { icon: string; color: string; label: string; value: string; sub?: string; cols: number }) {
  const w = cols === 4 ? '23.5%' : cols === 2 ? '48%' : '100%';
  return (
    <View style={[s.kpiCard, { width: w as any, borderColor: (globalThis as any).__alphaColor(color, '20') }]}>
      <Ionicons name={icon as any} size={20} color={color} />
      <Text style={s.kpiValue}>{value}</Text>
      <Text style={s.kpiLabel}>{label}</Text>
      {sub && <Text style={s.kpiSub}>{sub}</Text>}
    </View>
  );
}

function StatPill({ label, value, color, dataTestId }: { label: string; value: number; color: string; dataTestId?: string }) {
  return (
    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: (globalThis as any).__alphaColor(color, '12'), paddingHorizontal: 10, paddingVertical: 4, borderRadius: 12 }} data-testid={dataTestId} testID={dataTestId}>
      <Text style={{ fontSize: 12, fontWeight: '700', color }}>{value.toLocaleString()}</Text>
      <Text style={{ fontSize: 11, color: C.gray300 }}>{label}</Text>
    </View>
  );
}

const s = StyleSheet.create({
  center: { flex: 1, justifyContent: 'center', alignItems: 'center', minHeight: 300 },
  title: { fontSize: 24, fontWeight: '800', color: C.white, fontFamily: 'Manrope' },
  subtitle: { fontSize: 13, color: C.gray400, marginTop: 4 },
  sectionTitle: { fontSize: 16, fontWeight: '700', color: C.gray100, marginBottom: 12 },
  triggerBtn: { flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 14, paddingVertical: 10, borderRadius: 10, borderWidth: 1 },
  triggerText: { fontSize: 13, fontWeight: '600' },
  card: { backgroundColor: C.surface, borderRadius: 14, padding: 16, marginBottom: 10, borderWidth: 1, borderColor: C.border, ...glassBlurStyle },
  emptyCard: { backgroundColor: C.surface, borderRadius: 14, padding: 32, marginBottom: 10, borderWidth: 1, borderColor: C.border, alignItems: 'center', gap: 10 },
  emptyText: { fontSize: 13, color: C.gray400 },
  cardTitle: { fontSize: 14, fontWeight: '700', color: C.white },
  cardTime: { fontSize: 11, color: C.gray400 },
  statusDot: { width: 8, height: 8, borderRadius: 4 },
  issueRow: { flexDirection: 'row', alignItems: 'center', gap: 6, paddingVertical: 4 },
  issueText: { fontSize: 12, color: C.gray300, textTransform: 'capitalize' },
  kpiCard: { backgroundColor: C.surface, borderRadius: 14, padding: 16, borderWidth: 1, alignItems: 'center', gap: 6, ...glassBlurStyle },
  kpiValue: { fontSize: 22, fontWeight: '800', color: C.white },
  kpiLabel: { fontSize: 11, fontWeight: '600', color: C.gray400, textTransform: 'uppercase', letterSpacing: 0.5 },
  kpiSub: { fontSize: 10, color: C.gray400 },
});
