import { useTranslation } from '../../../hooks/useTranslation';
import React from 'react';
import { View, Text, TouchableOpacity, ActivityIndicator, Modal, TextInput } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useExecTheme, useExecStyles } from '../ExecDashboardPanels';
import api from '../../../services/api';
import { fmtDate } from './types';

const tx = (_key: string, fallback: string) => fallback;

const RULE_TYPES = [
  { id: 'max_age_days', label: 'Max Session Age (days)', icon: 'time', desc: 'Delete sessions older than X days' },
  { id: 'max_sessions_per_user', label: 'Max Sessions per User', icon: 'people', desc: 'Keep only the newest X sessions per user' },
  { id: 'inactive_days', label: 'Inactive Days', icon: 'moon', desc: 'Delete sessions inactive for X days' },
];

interface PoliciesPanelProps {
  polLoading: boolean;
  policies: any[];
  polHistory: any[];
  showNewPolicy: boolean;
  setShowNewPolicy: (b: boolean) => void;
  newPol: { name: string; rule_type: string; threshold: string };
  setNewPol: (fn: (p: any) => any) => void;
  runningPolicy: string;
  setRunningPolicy: (s: string) => void;
  loadPolicies: () => void;
}

export default function PoliciesPanel({
  polLoading, policies, polHistory, showNewPolicy, setShowNewPolicy,
  newPol, setNewPol, runningPolicy, setRunningPolicy, loadPolicies,
}: PoliciesPanelProps) {
  const { t } = useTranslation();
  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };

  const s = useExecStyles();
  const T = useExecTheme();
  const createPolicy = async () => {
    try {
      await api.post('/admin/session-policies', { name: newPol.name, rule_type: newPol.rule_type, threshold: parseInt(newPol.threshold), enabled: true });
      setShowNewPolicy(false);
      setNewPol(() => ({ name: '', rule_type: 'max_age_days', threshold: '30' }));
      loadPolicies();
    } catch (e) { console.error(e); }
  };

  const togglePolicy = async (id: string, enabled: boolean) => {
    try { await api.put(`/admin/session-policies/${id}`, { enabled: !enabled }); loadPolicies(); } catch (e) { console.error(e); }
  };

  const deletePolicy = async (id: string) => {
    try { await api.delete(`/admin/session-policies/${id}`); loadPolicies(); } catch (e) { console.error(e); }
  };

  const runPolicy = async (id: string) => {
    setRunningPolicy(id);
    try { await api.post(`/admin/session-policies/${id}/run`); loadPolicies(); } catch (e) { console.error(e); }
    finally { setRunningPolicy(''); }
  };

  if (polLoading) return <ActivityIndicator size="small" color={T.primary} style={{ paddingVertical: 30 }} />;

  return (
    <View data-testid="cleanup-policies-panel" testID="cleanup-policies-panel">
      <View style={s.panel}>
        <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14 }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
            <Ionicons name="trash" size={18} color={T.warningText} />
            <Text style={s.chartTitle}>{tx('admin.policiesPanel.auto.text.001', 'Session Cleanup Policies')}</Text>
          </View>
          <TouchableOpacity onPress={() => setShowNewPolicy(true)}
            style={{ flexDirection: 'row', alignItems: 'center', gap: 4, backgroundColor: T.primarySoft, paddingHorizontal: 10, paddingVertical: 6, borderRadius: 8 }}
            data-testid="create-policy-btn" testID="create-policy-btn"
          >
            <Ionicons name="add" size={14} color={T.primary} />
            <Text style={{ color: T.primary, fontSize: 11, fontWeight: '700' }}>{tx('admin.policiesPanel.auto.text.002', 'New Policy')}</Text>
          </TouchableOpacity>
        </View>
        <Text style={{ color: T.textMuted, fontSize: 11, marginBottom: 12 }}>{tx('admin.policiesPanel.auto.text.003', 'Automated cleanup runs every hour. Create policies to keep sessions tidy.')}</Text>

        {policies.length === 0 ? (
          <Text style={{ color: T.textMuted, textAlign: 'center', paddingVertical: 20, fontSize: 12 }}>{tx('admin.policiesPanel.auto.text.004', 'No policies yet. Create one to get started.')}</Text>
        ) : policies.map((pol: any, i: number) => (
          <View key={pol.policy_id} style={{ flexDirection: 'row', alignItems: 'center', padding: 12, backgroundColor: pol.enabled ? T.bgSoft : T.card, borderRadius: 10, marginBottom: 6, borderWidth: 1, borderColor: pol.enabled ? (globalThis as any).__alphaColor(T.primary, '30') : T.border }}
            data-testid={`policy-row-${i}`} testID={`policy-row-${i}`}
          >
            <TouchableOpacity onPress={() => togglePolicy(pol.policy_id, pol.enabled)}
              style={{ width: 36, height: 20, borderRadius: 10, backgroundColor: pol.enabled ? T.success : T.border, justifyContent: 'center', padding: 2 }}
              data-testid={`policy-toggle-${i}`} testID={`policy-toggle-${i}`}
            >
              <View style={{ width: 16, height: 16, borderRadius: 8, backgroundColor: T.primaryText, alignSelf: pol.enabled ? 'flex-end' : 'flex-start' }} />
            </TouchableOpacity>
            <View style={{ flex: 1, marginLeft: 12 }}>
              <Text style={{ color: T.text, fontSize: 12, fontWeight: '700' }}>{pol.name}</Text>
              <Text style={{ color: T.textMuted, fontSize: 10 }}>
                {RULE_TYPES.find(r => r.id === pol.rule_type)?.label || pol.rule_type} = {pol.threshold}
                {pol.last_run ? ` | Last run: ${fmtDate(pol.last_run)} (${pol.last_run_deleted} deleted)` : ''}
              </Text>
            </View>
            <View style={{ flexDirection: 'row', gap: 6 }}>
              <TouchableOpacity onPress={() => runPolicy(pol.policy_id)} disabled={runningPolicy === pol.policy_id}
                style={{ backgroundColor: T.primarySoft, paddingHorizontal: 8, paddingVertical: 4, borderRadius: 6 }}
                data-testid={`policy-run-${i}`} testID={`policy-run-${i}`}
              >
                <Text style={{ color: T.primary, fontSize: 9, fontWeight: '700' }}>{runningPolicy === pol.policy_id ? '...' : 'Run Now'}</Text>
              </TouchableOpacity>
              <TouchableOpacity onPress={() => deletePolicy(pol.policy_id)}
                style={{ backgroundColor: T.errorSoft, paddingHorizontal: 8, paddingVertical: 4, borderRadius: 6 }}
                data-testid={`policy-delete-${i}`} testID={`policy-delete-${i}`}
              >
                <Text style={{ color: T.error, fontSize: 9, fontWeight: '700' }}>{tx('admin.policiesPanel.auto.text.005', 'Delete')}</Text>
              </TouchableOpacity>
            </View>
          </View>
        ))}
      </View>

      {polHistory.length > 0 && (
        <View style={s.panel}>
          <Text style={[s.chartTitle, { marginBottom: 12 }]}>{tx('admin.policiesPanel.auto.text.006', 'Cleanup History')}</Text>
          {polHistory.slice(0, 10).map((h: any, i: number) => (
            <View key={i} style={{ flexDirection: 'row', alignItems: 'center', paddingVertical: 8, borderBottomWidth: 1, borderBottomColor: T.border }} data-testid={`history-row-${i}`} testID={`history-row-${i}`}>
              <Ionicons name="checkmark-circle" size={14} color={h.deleted > 0 ? T.success : T.textMuted} style={{ marginRight: 8 }} />
              <Text style={{ color: T.text, fontSize: 11, fontWeight: '600', flex: 1 }}>{h.policy_name}</Text>
              <Text style={{ color: h.deleted > 0 ? T.success : T.textMuted, fontSize: 11, fontWeight: '700', marginRight: 12 }}>{h.deleted} deleted</Text>
              <Text style={{ color: T.textMuted, fontSize: 10 }}>{fmtDate(h.executed_at)}</Text>
            </View>
          ))}
        </View>
      )}

      <Modal visible={showNewPolicy} transparent animationType="fade" onRequestClose={() => setShowNewPolicy(false)}>
        <View style={{ flex: 1, backgroundColor: 'rgba(0,0,0,0.7)', justifyContent: 'center', alignItems: 'center' }}>
          <View style={{ backgroundColor: T.card, borderRadius: 16, padding: 24, maxWidth: 420, width: '90%', borderWidth: 1, borderColor: T.border }}
            data-testid="new-policy-modal" testID="new-policy-modal"
          >
            <Text style={{ color: T.text, fontSize: 16, fontWeight: '700', marginBottom: 16 }}>{tx('admin.policiesPanel.auto.text.007', 'Create Cleanup Policy')}</Text>
            <Text style={{ color: T.textMuted, fontSize: 11, marginBottom: 4 }}>{tx('admin.policiesPanel.auto.text.008', 'Policy Name')}</Text>
            <TextInput value={newPol.name} onChangeText={t => setNewPol((p: any) => ({ ...p, name: t }))} placeholder={tx('admin.policiesPanel.auto.placeholder.001', 'e.g., Expire old sessions')}
              placeholderTextColor={T.textMuted} style={{ backgroundColor: T.bgSoft, color: T.text, borderRadius: 8, padding: 10, fontSize: 13, marginBottom: 12, borderWidth: 1, borderColor: T.border }}
              data-testid="new-policy-name" testID="new-policy-name"
            />
            <Text style={{ color: T.textMuted, fontSize: 11, marginBottom: 6 }}>{tx('admin.policiesPanel.auto.text.009', 'Rule Type')}</Text>
            <View style={{ gap: 6, marginBottom: 12 }}>
              {RULE_TYPES.map(rt => (
                <TouchableOpacity key={rt.id} onPress={() => setNewPol((p: any) => ({ ...p, rule_type: rt.id }))}
                  style={{ flexDirection: 'row', alignItems: 'center', gap: 8, padding: 10, borderRadius: 8,
                    backgroundColor: newPol.rule_type === rt.id ? T.primarySoft : T.bgSoft, borderWidth: 1,
                    borderColor: newPol.rule_type === rt.id ? T.primary : T.border }}
                  data-testid={`rule-type-${rt.id}`} testID={`rule-type-${rt.id}`}
                >
                  <Ionicons name={rt.icon as any} size={16} color={newPol.rule_type === rt.id ? T.primary : T.textMuted} />
                  <View style={{ flex: 1 }}>
                    <Text style={{ color: T.text, fontSize: 12, fontWeight: '600' }}>{rt.label}</Text>
                    <Text style={{ color: T.textMuted, fontSize: 10 }}>{rt.desc}</Text>
                  </View>
                </TouchableOpacity>
              ))}
            </View>
            <Text style={{ color: T.textMuted, fontSize: 11, marginBottom: 4 }}>{tx('admin.policiesPanel.auto.text.010', 'Threshold')}</Text>
            <TextInput value={newPol.threshold} onChangeText={t => setNewPol((p: any) => ({ ...p, threshold: t }))} keyboardType="numeric"
              placeholder="30" placeholderTextColor={T.textMuted}
              style={{ backgroundColor: T.bgSoft, color: T.text, borderRadius: 8, padding: 10, fontSize: 13, marginBottom: 16, borderWidth: 1, borderColor: T.border }}
              data-testid="new-policy-threshold" testID="new-policy-threshold"
            />
            <View style={{ flexDirection: 'row', gap: 10 }}>
              <TouchableOpacity onPress={() => setShowNewPolicy(false)}
                style={{ flex: 1, paddingVertical: 10, borderRadius: 10, backgroundColor: T.bgSoft, alignItems: 'center' }}
                data-testid="new-policy-cancel" testID="new-policy-cancel"
              >
                <Text style={{ color: T.textSec, fontWeight: '600', fontSize: 13 }}>{tx('admin.policiesPanel.auto.text.011', 'Cancel')}</Text>
              </TouchableOpacity>
              <TouchableOpacity onPress={createPolicy} disabled={!newPol.name.trim()}
                style={{ flex: 1, paddingVertical: 10, borderRadius: 10, backgroundColor: newPol.name.trim() ? T.primary : T.bgSoft, alignItems: 'center' }}
                data-testid="new-policy-create" testID="new-policy-create"
              >
                <Text style={{ color: newPol.name.trim() ? 'var(--app-primary-text)' : T.textMuted, fontWeight: '700', fontSize: 13 }}>{tx('admin.policiesPanel.auto.text.012', 'Create Policy')}</Text>
              </TouchableOpacity>
            </View>
          </View>
        </View>
      </Modal>
    </View>
  );
}
