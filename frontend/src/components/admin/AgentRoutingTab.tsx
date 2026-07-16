import React, { useEffect, useState, useCallback } from 'react';
import { View, Text, TouchableOpacity, ActivityIndicator, TextInput, StyleSheet } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';

type Props = { C: any; isCompact: boolean };

export const AgentRoutingTab: React.FC<Props> = ({ C, isCompact }) => {
  const [intent, setIntent] = useState('');
  const [routing, setRouting] = useState<any>(null);
  const [routeBusy, setRouteBusy] = useState(false);
  const [routeError, setRouteError] = useState<string | null>(null);
  const [log, setLog] = useState<any[]>([]);
  const [triggers, setTriggers] = useState<any[]>([]);
  const [events, setEvents] = useState<any[]>([]);
  const [capabilities, setCapabilities] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      const [l, tr, ev, cap] = await Promise.all([
        api.get('/agent-framework/route/log?limit=15'),
        api.get('/agent-framework/events/triggers'),
        api.get('/agent-framework/events?limit=10'),
        api.get('/agent-framework/capabilities'),
      ]);
      setLog(l.data?.routing_log || []);
      setTriggers(tr.data?.triggers || []);
      setEvents(ev.data?.events || []);
      setCapabilities(cap.data);
    } catch {
      // silent — panels degrade gracefully
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const runRoute = async () => {
    if (!intent.trim()) return;
    setRouteBusy(true); setRouteError(null); setRouting(null);
    try {
      const r = await api.post('/agent-framework/route', { intent, team_size: 4 });
      setRouting(r.data);
      await load();
    } catch (err: any) {
      setRouteError(err?.response?.data?.detail || err?.message || 'Routing failed');
    } finally {
      setRouteBusy(false);
    }
  };

  const s = makeStyles(C, isCompact);

  if (loading) {
    return <View style={s.center} testID="routing-loading"><ActivityIndicator size="large" color={C.primary} /></View>;
  }

  return (
    <View testID="agent-routing-tab">
      {/* Intent router */}
      <View style={s.panel} testID="routing-intent-panel">
        <Text style={s.panelTitle}>Intelligent Routing</Text>
        <Text style={s.hint}>Describe a user intent — the router selects the best agent and suggests a multi-agent team.</Text>
        <TextInput
          style={s.input}
          value={intent}
          onChangeText={setIntent}
          placeholder="e.g. Help me prepare for a software engineering interview"
          placeholderTextColor={C.textDim}
          multiline
          testID="routing-intent-input"
        />
        <TouchableOpacity onPress={runRoute} disabled={routeBusy} style={s.primaryBtn} testID="routing-route-button" accessibilityLabel="Route intent">
          {routeBusy ? <ActivityIndicator size="small" color={C.primaryText} /> : (
            <Text style={s.primaryBtnText}>Route intent</Text>
          )}
        </TouchableOpacity>
        {routeError ? <Text style={{ color: C.errorText, fontSize: 12, marginTop: 8 }} testID="routing-error">{routeError}</Text> : null}
        {routing ? (
          <View style={s.resultBox} testID="routing-result">
            {routing.selected_agent ? (
              <View style={s.lineRow}>
                <Ionicons name="navigate" size={15} color={C.primary} />
                <Text style={s.resultTitle} testID="routing-selected-agent">
                  {routing.selected_agent.name} <Text style={s.meta}>({routing.selected_agent.category} · score {routing.selected_agent.score})</Text>
                </Text>
              </View>
            ) : <Text style={s.meta}>No matching agent found</Text>}
            {(routing.team || []).length > 1 ? (
              <View style={{ marginTop: 6 }}>
                <Text style={s.subLabel}>Suggested team</Text>
                {routing.team.map((m: any) => (
                  <View key={m.agent_key} style={s.lineRow} testID={`routing-team-${m.agent_key}`}>
                    <Ionicons name="person" size={13} color={C.textDim} />
                    <Text style={s.lineLabel} numberOfLines={1}>{m.name}</Text>
                    <Text style={s.lineValue}>{m.score}</Text>
                  </View>
                ))}
              </View>
            ) : null}
            <Text style={s.meta}>{routing.candidates_evaluated} candidates evaluated</Text>
          </View>
        ) : null}
      </View>

      {/* Event triggers */}
      <View style={s.panel} testID="routing-triggers-panel">
        <Text style={s.panelTitle}>Event Triggers ({triggers.length})</Text>
        <Text style={s.hint}>Enabled triggers start their workflow automatically when the platform emits the event.</Text>
        {triggers.length === 0 ? <Text style={s.meta}>No event triggers configured yet.</Text> : triggers.map((tr) => (
          <View key={tr.trigger_id} style={s.lineRow} testID={`trigger-row-${tr.trigger_id}`}>
            <Ionicons name={tr.enabled ? 'flash' : 'flash-off'} size={14} color={tr.enabled ? C.primary : C.textDim} />
            <Text style={s.lineLabel} numberOfLines={1}>{tr.event_name}</Text>
            <Text style={s.lineValue} numberOfLines={1}>→ {tr.workflow_name}</Text>
          </View>
        ))}
      </View>

      {/* Recent events + routing log */}
      <View style={s.rowWrap}>
        <View style={s.panel} testID="routing-events-panel">
          <Text style={s.panelTitle}>Recent Events</Text>
          {events.length === 0 ? <Text style={s.meta}>No events emitted yet.</Text> : events.map((ev) => (
            <View key={ev.event_id} style={s.lineRow}>
              <Ionicons name="radio" size={13} color={C.primary} />
              <Text style={s.lineLabel} numberOfLines={1}>{ev.event_name}</Text>
              <Text style={s.lineValue}>{(ev.executions_started || []).length} runs</Text>
            </View>
          ))}
        </View>
        <View style={s.panel} testID="routing-log-panel">
          <Text style={s.panelTitle}>Routing Log</Text>
          {log.length === 0 ? <Text style={s.meta}>No routing decisions yet.</Text> : log.map((r) => (
            <View key={r.routing_id} style={s.lineRow}>
              <Ionicons name="git-network" size={13} color={C.textDim} />
              <Text style={s.lineLabel} numberOfLines={1}>{r.intent}</Text>
              <Text style={s.lineValue} numberOfLines={1}>{r.selected_agent_key || '—'}</Text>
            </View>
          ))}
        </View>
      </View>

      {/* Capability discovery */}
      {capabilities ? (
        <View style={s.panel} testID="routing-capabilities-panel">
          <Text style={s.panelTitle}>Capability Discovery</Text>
          <Text style={s.subLabel}>Step types</Text>
          <Text style={s.meta}>{(capabilities.step_types || []).join(' · ')}</Text>
          <Text style={s.subLabel}>Conflict resolution strategies</Text>
          <Text style={s.meta}>{(capabilities.resolution_strategies || []).join(' · ')}</Text>
          <Text style={s.subLabel}>Providers</Text>
          <Text style={s.meta}>{(capabilities.providers || []).join(' · ')}</Text>
          <Text style={s.subLabel}>Tools</Text>
          <Text style={s.meta}>{(capabilities.tools || []).join(' · ')}</Text>
        </View>
      ) : null}
    </View>
  );
};

const makeStyles = (C: any, isCompact: boolean) => StyleSheet.create({
  center: { padding: 40, alignItems: 'center' },
  panel: {
    flex: 1, backgroundColor: C.card, borderRadius: 14, borderWidth: 1, borderColor: C.border,
    padding: 16, marginBottom: 12,
  },
  panelTitle: { fontSize: 14, fontWeight: '700', color: C.text, marginBottom: 6 },
  hint: { fontSize: 11, color: C.textDim, marginBottom: 10, lineHeight: 16 },
  input: {
    borderWidth: 1, borderColor: C.border, borderRadius: 10, padding: 10, minHeight: 60,
    color: C.text, backgroundColor: C.bgSoft, fontSize: 13, textAlignVertical: 'top', marginBottom: 10,
  },
  primaryBtn: {
    alignSelf: 'flex-start', backgroundColor: C.primary, paddingVertical: 8,
    paddingHorizontal: 18, borderRadius: 999,
  },
  primaryBtnText: { color: C.primaryText, fontSize: 12, fontWeight: '700' },
  resultBox: { marginTop: 12, backgroundColor: C.bgSoft, borderRadius: 10, padding: 12, borderWidth: 1, borderColor: C.border, gap: 4 },
  resultTitle: { fontSize: 13, fontWeight: '700', color: C.text, flexShrink: 1 },
  subLabel: { fontSize: 11, fontWeight: '700', color: C.textSecondary, marginTop: 8 },
  meta: { fontSize: 11, color: C.textDim, marginTop: 2, lineHeight: 16 },
  rowWrap: { flexDirection: isCompact ? 'column' : 'row', gap: 12 },
  lineRow: { flexDirection: 'row', alignItems: 'center', gap: 8, paddingVertical: 4 },
  lineLabel: { fontSize: 12, color: C.textSecondary, flexShrink: 1 },
  lineValue: { fontSize: 12, fontWeight: '700', color: C.text, marginLeft: 'auto' },
});

export default AgentRoutingTab;
