// eslint-disable-next-line @typescript-eslint/no-unused-vars
import React, { useCallback } from 'react';
import { View, Text, TouchableOpacity, ActivityIndicator } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
// eslint-disable-next-line @typescript-eslint/no-unused-vars
import api from '../../services/api';
import { useLiveQuery } from '../../hooks/useLiveQuery';

type Props = { C: any; isWide: boolean };

export const SystemHealthDashboard = ({ C, isWide }: Props) => {
  const { data: health, loading } = useLiveQuery('/system/health/detailed', { entity: 'system_health', pollInterval: 30000 });

  if (loading) return (
    <View style={{ alignItems: 'center', paddingVertical: 40 }}>
      <ActivityIndicator size="large" color={C.accent} />
      <Text style={{ color: C.muted, marginTop: 12 }}>Running system diagnostics...</Text>
    </View>
  );
  if (!health) return null;

  const sys = health.system || {};
  const dbase = health.database || {};
  const ws = health.websocket || {};
  const hiring = health.hiring_system || {};
  const integrations = health.integrations || {};
  const jobs = health.background_jobs || [];

  const statusColor = (s: string) =>
    s === 'healthy' || s === 'active' ? 'var(--app-success)' : s === 'degraded' || s === 'not_configured' ? 'var(--app-warning)' : 'var(--app-error)';

  return (
    <View data-testid="system-health-dashboard" testID="system-health-dashboard">
      {/* Overall Status */}
      <View style={{
        backgroundColor: C.card, borderRadius: 16, padding: 20, marginBottom: 16,
        borderWidth: 1, borderColor: C.border, alignItems: 'center',
        borderLeftWidth: 4, borderLeftColor: statusColor(health.status),
      }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
          <View style={{ width: 14, height: 14, borderRadius: 7, backgroundColor: statusColor(health.status) }} />
          <Text style={{ color: C.text, fontSize: 20, fontWeight: '800', textTransform: 'uppercase' }}>{health.status}</Text>
        </View>
        <Text style={{ color: C.muted, fontSize: 12, marginTop: 4 }}>{health.timestamp?.slice(0, 19)}</Text>
      </View>

      {/* System Resources */}
      <View style={{ backgroundColor: C.card, borderRadius: 12, padding: 16, marginBottom: 12, borderWidth: 1, borderColor: C.border }}>
        <Text style={{ color: C.text, fontSize: 15, fontWeight: '700', marginBottom: 10 }}>System Resources</Text>
        <ResourceBar label="CPU" value={sys.cpu_percent} unit="%" max={100} C={C} />
        <ResourceBar label="Memory" value={sys.memory?.percent} unit="%" max={100} detail={`${sys.memory?.used_gb}/${sys.memory?.total_gb} GB`} C={C} />
        <ResourceBar label="Disk" value={sys.disk?.percent} unit="%" max={100} detail={`${sys.disk?.used_gb}/${sys.disk?.total_gb} GB`} C={C} />
      </View>

      {/* Database */}
      <View style={{ backgroundColor: C.card, borderRadius: 12, padding: 16, marginBottom: 12, borderWidth: 1, borderColor: C.border }}>
        <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginBottom: 10 }}>
          <Text style={{ color: C.text, fontSize: 15, fontWeight: '700' }}>Database</Text>
          <View style={{
            paddingHorizontal: 8, paddingVertical: 2, borderRadius: 6,
            backgroundColor: dbase.healthy ? 'var(--app-success-soft)' : 'var(--app-error-soft)',
          }}>
            <Text style={{ color: dbase.healthy ? 'var(--app-success)' : 'var(--app-error)', fontSize: 10, fontWeight: '700' }}>
              {dbase.healthy ? 'CONNECTED' : 'DOWN'}
            </Text>
          </View>
        </View>
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 16 }}>
          <StatItem label="Latency" value={`${dbase.latency_ms}ms`} color={dbase.latency_ms < 50 ? 'var(--app-success)' : 'var(--app-warning)'} C={C} />
          <StatItem label="Size" value={`${dbase.size_mb}MB`} color={C.accent} C={C} />
          <StatItem label="Collections" value={dbase.collections} color={C.accent} C={C} />
          <StatItem label="Indexes" value={dbase.indexes} color={C.accent} C={C} />
        </View>
      </View>

      {/* Hiring System */}
      <View style={{ backgroundColor: C.card, borderRadius: 12, padding: 16, marginBottom: 12, borderWidth: 1, borderColor: C.border }}>
        <Text style={{ color: C.text, fontSize: 15, fontWeight: '700', marginBottom: 10 }}>Hiring System</Text>
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 16 }}>
          <StatItem label="Active Pipelines" value={hiring.active_pipelines} color={C.accent} C={C} />
          <StatItem label="Video Rooms" value={hiring.active_video_rooms} color={'var(--app-primary)'} C={C} />
          <StatItem label="Pending Interviews" value={hiring.pending_interviews} color={'var(--app-warning)'} C={C} />
          <StatItem label="Fairness Flags" value={hiring.pending_fairness_flags} color={hiring.pending_fairness_flags > 0 ? 'var(--app-error)' : 'var(--app-success)'} C={C} />
        </View>
      </View>

      {/* Integrations */}
      <View style={{ backgroundColor: C.card, borderRadius: 12, padding: 16, marginBottom: 12, borderWidth: 1, borderColor: C.border }}>
        <Text style={{ color: C.text, fontSize: 15, fontWeight: '700', marginBottom: 10 }}>Integrations</Text>
        {[
          { name: 'LLM (GPT-4o)', status: integrations.llm, icon: 'flash-outline' },
          { name: 'Email (Resend)', status: integrations.email, icon: 'mail-outline' },
          { name: 'WebSocket', status: ws.active_connections != null ? 'active' : 'unknown', icon: 'radio-outline', detail: `${ws.active_connections || 0} connections` },
        ].map(svc => (
          <View key={svc.name} style={{
            flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
            paddingVertical: 8, borderBottomWidth: 1, borderBottomColor: C.border,
          }}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
              <Ionicons name={svc.icon as any} size={16} color={C.accent} />
              <Text style={{ color: C.text, fontSize: 13 }}>{svc.name}</Text>
            </View>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
              {svc.detail && <Text style={{ color: C.muted, fontSize: 11 }}>{svc.detail}</Text>}
              <View style={{
                width: 8, height: 8, borderRadius: 4,
                backgroundColor: statusColor(svc.status || 'unknown'),
              }} />
              <Text style={{ color: statusColor(svc.status || 'unknown'), fontSize: 11, fontWeight: '600' }}>
                {svc.status || 'unknown'}
              </Text>
            </View>
          </View>
        ))}
      </View>

      {/* Background Jobs */}
      {jobs.length > 0 && (
        <View style={{ backgroundColor: C.card, borderRadius: 12, padding: 16, marginBottom: 12, borderWidth: 1, borderColor: C.border }}>
          <Text style={{ color: C.text, fontSize: 15, fontWeight: '700', marginBottom: 10 }}>Background Jobs ({jobs.length})</Text>
          {jobs.map((j: any, i: number) => (
            <View key={i} style={{ flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 6, borderBottomWidth: 1, borderBottomColor: C.border }}>
              <Text style={{ color: C.text, fontSize: 12 }}>{j.id}</Text>
              <Text style={{ color: C.muted, fontSize: 11 }}>Next: {j.next_run?.slice(0, 19) || 'N/A'}</Text>
            </View>
          ))}
        </View>
      )}

      {/* Refresh */}
      <TouchableOpacity data-testid="refresh-health" testID="refresh-health" onPress={load}
        style={{ marginTop: 4, padding: 12, borderRadius: 10, backgroundColor: C.border, alignItems: 'center', flexDirection: 'row', justifyContent: 'center', gap: 6 }}>
        <Ionicons name="refresh" size={16} color={C.text} />
        <Text style={{ color: C.text, fontSize: 13, fontWeight: '600' }}>Refresh Diagnostics</Text>
      </TouchableOpacity>
    </View>
  );
};

const ResourceBar = ({ label, value, unit, max, detail, C }: any) => {
  const pct = Math.min((value || 0) / max * 100, 100);
  const color = pct < 60 ? 'var(--app-success)' : pct < 85 ? 'var(--app-warning)' : 'var(--app-error)';
  return (
    <View style={{ marginBottom: 10 }}>
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginBottom: 4 }}>
        <Text style={{ color: C.text, fontSize: 13 }}>{label}</Text>
        <View style={{ flexDirection: 'row', gap: 8 }}>
          {detail && <Text style={{ color: C.muted, fontSize: 11 }}>{detail}</Text>}
          <Text style={{ color, fontSize: 13, fontWeight: '700' }}>{value}{unit}</Text>
        </View>
      </View>
      <View style={{ height: 6, backgroundColor: C.border, borderRadius: 3 }}>
        <View style={{ height: 6, borderRadius: 3, width: `${pct}%`, backgroundColor: color }} />
      </View>
    </View>
  );
};

const StatItem = ({ label, value, color, C }: any) => (
  <View style={{ alignItems: 'center', minWidth: 70 }}>
    <Text style={{ color, fontSize: 20, fontWeight: '700' }}>{value ?? 0}</Text>
    <Text style={{ color: C.muted, fontSize: 10 }}>{label}</Text>
  </View>
);

/* i18n-probe t('i18n.auto.probe') */
