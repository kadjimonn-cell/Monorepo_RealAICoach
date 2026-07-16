import React, { useEffect, useState, useCallback } from 'react';
import {
  View, Text, ScrollView, TouchableOpacity, ActivityIndicator,
  StyleSheet, useWindowDimensions, TextInput,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { useAdminTheme } from '../../src/hooks/useAdminTheme';
import api from '../../src/services/api';
import { useTranslation } from '../../src/hooks/useTranslation';
import AgentPortfolioTab from '../../src/components/admin/AgentPortfolioTab';
import AgentRoutingTab from '../../src/components/admin/AgentRoutingTab';
import AgentKnowledgeTab from '../../src/components/admin/AgentKnowledgeTab';
import AgentAnalyticsTab from '../../src/components/admin/AgentAnalyticsTab';

type Agent = {
  agent_key: string; name: string; role: string; category?: string; subcategory?: string;
  description: string; provider: string; model: string; allowed_tools: string[];
  version: number; enabled: boolean; status?: string; availability?: string;
  feature_mappings?: string[]; dependencies?: string[]; tags?: string[];
};
type Workflow = { workflow_id: string; name: string; description: string; steps: any[]; version: number; enabled: boolean };
type Execution = {
  execution_id: string; workflow_name: string; status: string; created_at: string;
  pending_approval?: { step_id: string; prompt: string } | null; error?: string;
};
type Tool = { name: string; description: string; permission: string };

const TABS = ['portfolio', 'agents', 'workflows', 'executions', 'tools', 'routing', 'knowledge', 'analytics'] as const;
type Tab = typeof TABS[number];

const STATUS_TONE: Record<string, 'success' | 'warning' | 'error' | 'info'> = {
  completed: 'success', running: 'info', waiting_human: 'warning', failed: 'error', rejected: 'error',
};

const AGENT_STATUS_TONE: Record<string, 'success' | 'warning' | 'error' | 'info'> = {
  active: 'success', beta: 'info', experimental: 'warning', disabled: 'error',
};

const PAGE_SIZE = 30;

export default function AIAgentsPanel() {
  const { t } = useTranslation();
  t('i18n.route.admin.ai-agents.probe');
  const C = useAdminTheme();
  const router = useRouter();
  const { width } = useWindowDimensions();
  const isCompact = width < 860;

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>('agents');
  const [overview, setOverview] = useState<any>(null);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [workflows, setWorkflows] = useState<Workflow[]>([]);
  const [executions, setExecutions] = useState<Execution[]>([]);
  const [tools, setTools] = useState<Tool[]>([]);

  const [runAgentKey, setRunAgentKey] = useState<string | null>(null);
  const [runInput, setRunInput] = useState('');
  const [runBusy, setRunBusy] = useState(false);
  const [runOutput, setRunOutput] = useState<string | null>(null);
  const [wfBusy, setWfBusy] = useState<string | null>(null);
  const [hitlBusy, setHitlBusy] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const [categoryFilter, setCategoryFilter] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<string | null>(null);
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE);
  const [selectMode, setSelectMode] = useState(false);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [bulkBusy, setBulkBusy] = useState(false);
  const [cloneBusy, setCloneBusy] = useState<string | null>(null);

  const categories = React.useMemo(() => {
    const counts: Record<string, number> = {};
    agents.forEach((a) => {
      const c = a.category || 'Uncategorized';
      counts[c] = (counts[c] || 0) + 1;
    });
    return Object.entries(counts).sort((x, y) => x[0].localeCompare(y[0]));
  }, [agents]);

  const agentStatus = (a: Agent) => (!a.enabled ? 'disabled' : (a.status || 'active'));

  const filteredAgents = React.useMemo(() => {
    const q = search.trim().toLowerCase();
    return agents.filter((a) => {
      if (categoryFilter && (a.category || 'Uncategorized') !== categoryFilter) return false;
      if (statusFilter && agentStatus(a) !== statusFilter) return false;
      if (!q) return true;
      return [a.name, a.role, a.category, a.subcategory, a.description, a.agent_key, ...(a.tags || [] as any)]
        .some((f: any) => (f || '').toLowerCase().includes(q));
    });
  }, [agents, search, categoryFilter, statusFilter]);

  useEffect(() => { setVisibleCount(PAGE_SIZE); }, [search, categoryFilter, statusFilter]);

  const showToast = (msg: string) => { setToast(msg); setTimeout(() => setToast(null), 4000); };

  const loadAll = useCallback(async () => {
    try {
      setError(null);
      const [o, a, w, e, tl] = await Promise.all([
        api.get('/agent-framework/overview'),
        api.get('/agent-framework/agents'),
        api.get('/agent-framework/workflows'),
        api.get('/agent-framework/executions?limit=30'),
        api.get('/agent-framework/tools'),
      ]);
      setOverview(o.data);
      setAgents(a.data?.agents || []);
      setWorkflows(w.data?.workflows || []);
      setExecutions(e.data?.executions || []);
      setTools(tl.data?.tools || []);
    } catch (err: any) {
      setError(err?.response?.data?.detail || err?.message || 'Failed to load');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadAll(); }, [loadAll]);

  const runAgent = async (agentKey: string) => {
    if (!runInput.trim()) return;
    setRunBusy(true); setRunOutput(null);
    try {
      const r = await api.post(`/agent-framework/agents/${agentKey}/execute`, { input: runInput });
      setRunOutput(r.data?.output || '(empty response)');
    } catch (err: any) {
      setRunOutput('Error: ' + (err?.response?.data?.detail || err?.message));
    } finally {
      setRunBusy(false);
    }
  };

  const runWorkflow = async (workflowId: string) => {
    setWfBusy(workflowId);
    try {
      await api.post(`/agent-framework/workflows/${workflowId}/execute`, { input: 'Manual run from Operations Console' });
      showToast('Workflow execution started');
      setTab('executions');
      await loadAll();
    } catch (err: any) {
      showToast('Run failed: ' + (err?.response?.data?.detail || err?.message));
    } finally {
      setWfBusy(null);
    }
  };

  const decideHitl = async (executionId: string, approve: boolean) => {
    setHitlBusy(executionId);
    try {
      await api.post(`/agent-framework/executions/${executionId}/${approve ? 'approve' : 'reject'}`, { note: 'Via Operations Console' });
      showToast(approve ? 'Approved — resuming workflow' : 'Rejected');
      await loadAll();
    } catch (err: any) {
      showToast('Action failed: ' + (err?.response?.data?.detail || err?.message));
    } finally {
      setHitlBusy(null);
    }
  };

  const toggleSelect = (key: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key); else next.add(key);
      return next;
    });
  };

  const runBulk = async (changes: Record<string, any>) => {
    if (!selected.size) return;
    setBulkBusy(true);
    try {
      const r = await api.post('/agent-framework/marketplace/bulk-status', {
        agent_keys: Array.from(selected), changes,
      });
      showToast(`Updated ${r.data?.modified ?? 0} agents`);
      await loadAll();
    } catch (err: any) {
      showToast('Bulk update failed: ' + (err?.response?.data?.detail || err?.message));
    } finally {
      setBulkBusy(false);
    }
  };

  const cloneAgent = async (agentKey: string) => {
    setCloneBusy(agentKey);
    try {
      const suffix = Math.random().toString(36).slice(2, 6);
      await api.post(`/agent-framework/marketplace/agents/${agentKey}/clone`, {
        new_key: `${agentKey}_clone_${suffix}`, new_name: '',
      });
      showToast('Agent cloned (status: experimental)');
      await loadAll();
    } catch (err: any) {
      showToast('Clone failed: ' + (err?.response?.data?.detail || err?.message));
    } finally {
      setCloneBusy(null);
    }
  };

  const s = makeStyles(C, isCompact);

  if (loading) {
    return (
      <View style={[s.page, { justifyContent: 'center', alignItems: 'center' }]} testID="ai-agents-loading">
        <ActivityIndicator size="large" color={C.primary} />
      </View>
    );
  }

  const badge = (status: string) => {
    const tone = STATUS_TONE[status] || 'info';
    const bg = { success: C.successSoft, warning: C.warningSoft, error: C.errorSoft, info: C.infoSoft }[tone];
    const fg = { success: C.successText, warning: C.warningText, error: C.errorText, info: C.infoText }[tone];
    return (
      <View style={[s.badge, { backgroundColor: bg }]}>
        <Text style={[s.badgeText, { color: fg }]}>{status.replace('_', ' ')}</Text>
      </View>
    );
  };

  const agentBadge = (agent: Agent) => {
    const status = agentStatus(agent);
    const tone = AGENT_STATUS_TONE[status] || 'info';
    const bg = { success: C.successSoft, warning: C.warningSoft, error: C.errorSoft, info: C.infoSoft }[tone];
    const fg = { success: C.successText, warning: C.warningText, error: C.errorText, info: C.infoText }[tone];
    return (
      <View style={[s.badge, { backgroundColor: bg }]} testID={`agent-status-badge-${agent.agent_key}`}>
        <Text style={[s.badgeText, { color: fg }]}>{status}</Text>
      </View>
    );
  };

  return (
    <ScrollView style={s.page} contentContainerStyle={s.content} testID="ai-agents-panel">
      <View style={s.headerRow}>
        <TouchableOpacity onPress={() => router.back()} style={s.backBtn} testID="ai-agents-back-button">
          <Ionicons name="arrow-back" size={20} color={C.text} />
        </TouchableOpacity>
        <View style={{ flex: 1 }}>
          <Text style={s.title} testID="ai-agents-title">AI Agent Marketplace</Text>
          <Text style={s.subtitle}>Native provider-agnostic agent ecosystem, workflows & governance</Text>
        </View>
        <TouchableOpacity onPress={loadAll} style={s.iconBtn} testID="ai-agents-refresh-button">
          <Ionicons name="refresh" size={18} color={C.primary} />
        </TouchableOpacity>
      </View>

      {toast ? <View style={s.toast}><Text style={s.toastText} testID="ai-agents-toast">{toast}</Text></View> : null}
      {error ? <View style={s.errorBox}><Text style={{ color: C.errorText }} testID="ai-agents-error">{error}</Text></View> : null}

      {overview ? (
        <View style={s.statsRow} testID="ai-agents-overview-stats">
          {[
            { label: 'Agents', value: overview.agents, icon: 'people' },
            { label: 'Workflows', value: overview.workflows, icon: 'git-branch' },
            { label: 'Executions', value: overview.executions, icon: 'play-circle' },
            { label: 'Pending Approvals', value: overview.waiting_approvals, icon: 'hand-left' },
            { label: 'Tools', value: overview.tools, icon: 'construct' },
          ].map((st) => (
            <View key={st.label} style={s.statCard}>
              <Ionicons name={st.icon as any} size={16} color={C.primary} />
              <Text style={s.statValue}>{st.value}</Text>
              <Text style={s.statLabel}>{st.label}</Text>
            </View>
          ))}
        </View>
      ) : null}

      <View style={s.tabsRow}>
        {TABS.map((tb) => (
          <TouchableOpacity
            key={tb}
            onPress={() => setTab(tb)}
            style={[s.tabBtn, tab === tb && s.tabBtnActive]}
            testID={`ai-agents-tab-${tb}`}
          >
            <Text style={[s.tabText, tab === tb && s.tabTextActive]}>
              {tb.charAt(0).toUpperCase() + tb.slice(1)}
            </Text>
          </TouchableOpacity>
        ))}
      </View>

      {tab === 'portfolio' && <AgentPortfolioTab C={C} isCompact={isCompact} />}
      {tab === 'routing' && <AgentRoutingTab C={C} isCompact={isCompact} />}
      {tab === 'knowledge' && <AgentKnowledgeTab C={C} isCompact={isCompact} />}
      {tab === 'analytics' && <AgentAnalyticsTab C={C} isCompact={isCompact} />}

      {tab === 'agents' && (
        <>
          <View style={s.filterBar}>
            <View style={s.searchBox}>
              <Ionicons name="search" size={15} color={C.textDim} />
              <TextInput
                style={s.searchInput}
                value={search}
                onChangeText={setSearch}
                placeholder="Search agents by name, role, or category…"
                placeholderTextColor={C.textDim}
                testID="agent-search-input"
              />
              {search ? (
                <TouchableOpacity onPress={() => setSearch('')} testID="agent-search-clear">
                  <Ionicons name="close-circle" size={16} color={C.textDim} />
                </TouchableOpacity>
              ) : null}
            </View>
          </View>
          <View style={s.controlsRow}>
            {['active', 'beta', 'experimental', 'disabled'].map((st) => (
              <TouchableOpacity
                key={st}
                onPress={() => setStatusFilter(statusFilter === st ? null : st)}
                style={[s.chip, statusFilter === st && s.chipActive]}
                testID={`agent-status-filter-${st}`}
              >
                <Text style={[s.chipText, statusFilter === st && s.chipTextActive]}>{st}</Text>
              </TouchableOpacity>
            ))}
            <TouchableOpacity
              onPress={() => { setSelectMode(!selectMode); setSelected(new Set()); }}
              style={[s.chip, selectMode && s.chipActive, { marginLeft: 'auto' }]}
              testID="agent-bulk-select-toggle"
            >
              <Text style={[s.chipText, selectMode && s.chipTextActive]}>{selectMode ? 'Cancel select' : 'Bulk select'}</Text>
            </TouchableOpacity>
          </View>
          {selectMode ? (
            <View style={s.bulkBar} testID="agent-bulk-bar">
              <Text style={s.bulkCount}>{selected.size} selected</Text>
              {[
                { label: 'Enable', changes: { status: 'active' } },
                { label: 'Disable', changes: { status: 'disabled' } },
                { label: 'Set Beta', changes: { status: 'beta' } },
              ].map((action) => (
                <TouchableOpacity
                  key={action.label}
                  disabled={bulkBusy || !selected.size}
                  onPress={() => runBulk(action.changes)}
                  style={[s.bulkBtn, { opacity: bulkBusy || !selected.size ? 0.5 : 1 }]}
                  testID={`agent-bulk-${action.label.toLowerCase().replace(/\s+/g, '-')}`}
                >
                  <Text style={s.bulkBtnText}>{action.label}</Text>
                </TouchableOpacity>
              ))}
            </View>
          ) : null}
          <ScrollView horizontal showsHorizontalScrollIndicator={false} style={s.chipsRow} contentContainerStyle={{ gap: 8, paddingBottom: 4 }}>
            <TouchableOpacity
              onPress={() => setCategoryFilter(null)}
              style={[s.chip, !categoryFilter && s.chipActive]}
              testID="agent-category-all"
            >
              <Text style={[s.chipText, !categoryFilter && s.chipTextActive]}>All ({agents.length})</Text>
            </TouchableOpacity>
            {categories.map(([cat, count]) => (
              <TouchableOpacity
                key={cat}
                onPress={() => setCategoryFilter(categoryFilter === cat ? null : cat)}
                style={[s.chip, categoryFilter === cat && s.chipActive]}
                testID={`agent-category-${cat.toLowerCase().replace(/[^a-z0-9]+/g, '-')}`}
              >
                <Text style={[s.chipText, categoryFilter === cat && s.chipTextActive]}>{cat} ({count})</Text>
              </TouchableOpacity>
            ))}
          </ScrollView>
          {filteredAgents.length === 0 ? (
            <View style={s.emptyBox} testID="agents-empty">
              <Ionicons name="people-outline" size={28} color={C.textDim} />
              <Text style={s.emptyText}>No agents match your search.</Text>
            </View>
          ) : null}
          {filteredAgents.slice(0, visibleCount).map((agent) => (
        <View key={agent.agent_key} style={s.card} testID={`agent-card-${agent.agent_key}`}>
          <View style={s.cardHeader}>
            {selectMode ? (
              <TouchableOpacity onPress={() => toggleSelect(agent.agent_key)} testID={`agent-select-${agent.agent_key}`}>
                <Ionicons
                  name={selected.has(agent.agent_key) ? 'checkbox' : 'square-outline'}
                  size={20} color={selected.has(agent.agent_key) ? C.primary : C.textDim}
                />
              </TouchableOpacity>
            ) : null}
            <View style={{ flex: 1 }}>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                <Text style={s.cardTitle}>{agent.name}</Text>
                {agentBadge(agent)}
              </View>
              <Text style={s.cardMeta}>
                {agent.category ? `${agent.category} · ` : ''}{agent.subcategory && agent.subcategory !== agent.role ? `${agent.subcategory} · ` : ''}{agent.role} · {agent.provider}:{agent.model} · v{agent.version} · {agent.availability || 'global'}
              </Text>
            </View>
            <TouchableOpacity
              style={s.cloneBtn}
              disabled={cloneBusy === agent.agent_key}
              onPress={() => cloneAgent(agent.agent_key)}
              testID={`agent-clone-${agent.agent_key}`}
            >
              {cloneBusy === agent.agent_key
                ? <ActivityIndicator size="small" color={C.primary} />
                : <Ionicons name="copy-outline" size={15} color={C.primary} />}
            </TouchableOpacity>
            <TouchableOpacity
              style={s.runBtn}
              onPress={() => { setRunAgentKey(runAgentKey === agent.agent_key ? null : agent.agent_key); setRunOutput(null); setRunInput(''); }}
              testID={`agent-run-toggle-${agent.agent_key}`}
            >
              <Ionicons name="play" size={14} color={C.primaryText} />
              <Text style={s.runBtnText}>Run</Text>
            </TouchableOpacity>
          </View>
          <Text style={s.cardDesc}>{agent.description}</Text>
          {agent.feature_mappings?.length ? (
            <Text style={s.cardTools}>Features: {agent.feature_mappings.join(', ')}</Text>
          ) : null}
          {agent.dependencies?.length ? (
            <Text style={s.cardTools}>Depends on: {agent.dependencies.join(', ')}</Text>
          ) : null}
          {agent.allowed_tools?.length ? (
            <Text style={s.cardTools}>Tools: {agent.allowed_tools.join(', ')}</Text>
          ) : null}
          {runAgentKey === agent.agent_key ? (
            <View style={s.runBox}>
              <TextInput
                style={s.input}
                value={runInput}
                onChangeText={setRunInput}
                placeholder="Enter task for this agent…"
                placeholderTextColor={C.textDim}
                multiline
                testID={`agent-run-input-${agent.agent_key}`}
              />
              <TouchableOpacity
                style={[s.runBtn, { alignSelf: 'flex-start', opacity: runBusy || !runInput.trim() ? 0.5 : 1 }]}
                disabled={runBusy || !runInput.trim()}
                onPress={() => runAgent(agent.agent_key)}
                testID={`agent-run-submit-${agent.agent_key}`}
              >
                {runBusy ? <ActivityIndicator size="small" color={C.primaryText} /> : (
                  <>
                    <Ionicons name="send" size={13} color={C.primaryText} />
                    <Text style={s.runBtnText}>Execute</Text>
                  </>
                )}
              </TouchableOpacity>
              {runOutput ? (
                <View style={s.outputBox}>
                  <Text style={s.outputText} testID={`agent-run-output-${agent.agent_key}`}>{runOutput}</Text>
                </View>
              ) : null}
            </View>
          ) : null}
        </View>
          ))}
          {filteredAgents.length > visibleCount ? (
            <TouchableOpacity
              onPress={() => setVisibleCount(visibleCount + PAGE_SIZE)}
              style={s.showMoreBtn}
              testID="agents-show-more"
            >
              <Text style={s.showMoreText}>Show more ({filteredAgents.length - visibleCount} remaining)</Text>
            </TouchableOpacity>
          ) : null}
        </>
      )}

      {tab === 'workflows' && (
        workflows.length === 0 ? (
          <View style={s.emptyBox} testID="workflows-empty">
            <Ionicons name="git-branch-outline" size={28} color={C.textDim} />
            <Text style={s.emptyText}>No workflows yet. Create one via POST /api/agent-framework/workflows — supports sequential, parallel, conditional and human-in-the-loop steps.</Text>
          </View>
        ) : workflows.map((wf) => (
          <View key={wf.workflow_id} style={s.card} testID={`workflow-card-${wf.workflow_id}`}>
            <View style={s.cardHeader}>
              <View style={{ flex: 1 }}>
                <Text style={s.cardTitle}>{wf.name}</Text>
                <Text style={s.cardMeta}>{wf.steps?.length || 0} steps · v{wf.version} · {wf.enabled ? 'enabled' : 'disabled'}</Text>
              </View>
              <TouchableOpacity
                style={[s.runBtn, { opacity: wfBusy === wf.workflow_id ? 0.5 : 1 }]}
                disabled={wfBusy === wf.workflow_id}
                onPress={() => runWorkflow(wf.workflow_id)}
                testID={`workflow-run-${wf.workflow_id}`}
              >
                {wfBusy === wf.workflow_id ? <ActivityIndicator size="small" color={C.primaryText} /> : (
                  <>
                    <Ionicons name="play" size={14} color={C.primaryText} />
                    <Text style={s.runBtnText}>Run</Text>
                  </>
                )}
              </TouchableOpacity>
            </View>
            {wf.description ? <Text style={s.cardDesc}>{wf.description}</Text> : null}
          </View>
        ))
      )}

      {tab === 'executions' && (
        executions.length === 0 ? (
          <View style={s.emptyBox} testID="executions-empty">
            <Ionicons name="play-circle-outline" size={28} color={C.textDim} />
            <Text style={s.emptyText}>No executions yet. Run an agent or workflow to see history here.</Text>
          </View>
        ) : executions.map((ex) => (
          <View key={ex.execution_id} style={s.card} testID={`execution-card-${ex.execution_id}`}>
            <View style={s.cardHeader}>
              <View style={{ flex: 1 }}>
                <Text style={s.cardTitle}>{ex.workflow_name || 'Workflow'}</Text>
                <Text style={s.cardMeta}>{new Date(ex.created_at).toLocaleString()} · {ex.execution_id.slice(0, 8)}</Text>
              </View>
              {badge(ex.status)}
            </View>
            {ex.error ? <Text style={[s.cardDesc, { color: C.errorText }]}>{ex.error}</Text> : null}
            {ex.status === 'waiting_human' && ex.pending_approval ? (
              <View style={s.hitlBox}>
                <Text style={s.hitlPrompt} testID={`hitl-prompt-${ex.execution_id}`}>
                  <Ionicons name="hand-left" size={13} color={C.warningText} /> {ex.pending_approval.prompt}
                </Text>
                <View style={{ flexDirection: 'row', gap: 8 }}>
                  <TouchableOpacity
                    style={[s.approveBtn, { opacity: hitlBusy === ex.execution_id ? 0.5 : 1 }]}
                    disabled={hitlBusy === ex.execution_id}
                    onPress={() => decideHitl(ex.execution_id, true)}
                    testID={`hitl-approve-${ex.execution_id}`}
                  >
                    <Text style={{ color: C.primaryText, fontWeight: '700', fontSize: 12 }}>Approve</Text>
                  </TouchableOpacity>
                  <TouchableOpacity
                    style={[s.rejectBtn, { opacity: hitlBusy === ex.execution_id ? 0.5 : 1 }]}
                    disabled={hitlBusy === ex.execution_id}
                    onPress={() => decideHitl(ex.execution_id, false)}
                    testID={`hitl-reject-${ex.execution_id}`}
                  >
                    <Text style={{ color: C.primaryText, fontWeight: '700', fontSize: 12 }}>Reject</Text>
                  </TouchableOpacity>
                </View>
              </View>
            ) : null}
          </View>
        ))
      )}

      {tab === 'tools' && tools.map((tool) => (
        <View key={tool.name} style={s.card} testID={`tool-card-${tool.name}`}>
          <View style={s.cardHeader}>
            <View style={{ flex: 1 }}>
              <Text style={s.cardTitle}>{tool.name}</Text>
              <Text style={s.cardMeta}>permission: {tool.permission}</Text>
            </View>
            <Ionicons name="construct-outline" size={18} color={C.primary} />
          </View>
          <Text style={s.cardDesc}>{tool.description}</Text>
        </View>
      ))}
    </ScrollView>
  );
}

const makeStyles = (C: any, isCompact: boolean) => StyleSheet.create({
  page: { flex: 1, backgroundColor: C.bg },
  content: { padding: isCompact ? 14 : 24, paddingBottom: 60, maxWidth: 1240, width: '100%', alignSelf: 'center' },
  headerRow: { flexDirection: 'row', alignItems: 'center', gap: 12, marginBottom: 16 },
  backBtn: { padding: 8, borderRadius: 10, backgroundColor: C.card, borderWidth: 1, borderColor: C.border },
  iconBtn: { padding: 8, borderRadius: 10, backgroundColor: C.primarySoft },
  title: { fontSize: isCompact ? 20 : 24, fontWeight: '800', color: C.text },
  subtitle: { fontSize: 12, color: C.textSecondary, marginTop: 2 },
  toast: { backgroundColor: C.infoSoft, borderRadius: 10, padding: 10, marginBottom: 12 },
  toastText: { color: C.infoText, fontSize: 12, fontWeight: '600' },
  errorBox: { backgroundColor: C.errorSoft, borderRadius: 10, padding: 12, marginBottom: 12 },
  statsRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 10, marginBottom: 18 },
  statCard: {
    flexGrow: 1, minWidth: isCompact ? 100 : 140, backgroundColor: C.card, borderRadius: 12,
    borderWidth: 1, borderColor: C.border, padding: 12, alignItems: 'flex-start', gap: 4,
  },
  statValue: { fontSize: 20, fontWeight: '800', color: C.text },
  statLabel: { fontSize: 11, color: C.textSecondary },
  tabsRow: { flexDirection: 'row', gap: 8, marginBottom: 14, flexWrap: 'wrap' },
  filterBar: { marginBottom: 10 },
  searchBox: {
    flexDirection: 'row', alignItems: 'center', gap: 8, backgroundColor: C.card,
    borderWidth: 1, borderColor: C.border, borderRadius: 999, paddingVertical: 8, paddingHorizontal: 14,
  },
  searchInput: { flex: 1, color: C.text, fontSize: 13, padding: 0 },
  chipsRow: { marginBottom: 12, flexGrow: 0 },
  chip: {
    paddingVertical: 6, paddingHorizontal: 12, borderRadius: 999,
    backgroundColor: C.card, borderWidth: 1, borderColor: C.border,
  },
  chipActive: { backgroundColor: C.primarySoft, borderColor: C.primary },
  chipText: { fontSize: 12, fontWeight: '600', color: C.textSecondary },
  chipTextActive: { color: C.accentText },
  controlsRow: { flexDirection: 'row', gap: 8, marginBottom: 10, flexWrap: 'wrap', alignItems: 'center' },
  bulkBar: {
    flexDirection: 'row', alignItems: 'center', gap: 10, backgroundColor: C.primarySoft,
    borderRadius: 12, padding: 10, marginBottom: 12, flexWrap: 'wrap',
  },
  bulkCount: { fontSize: 12, fontWeight: '700', color: C.accentText },
  bulkBtn: { backgroundColor: C.primary, paddingVertical: 6, paddingHorizontal: 14, borderRadius: 999 },
  bulkBtnText: { color: C.primaryText, fontSize: 12, fontWeight: '700' },
  cloneBtn: {
    padding: 8, borderRadius: 999, backgroundColor: C.primarySoft,
    borderWidth: 1, borderColor: C.border,
  },
  showMoreBtn: {
    alignSelf: 'center', paddingVertical: 10, paddingHorizontal: 24, borderRadius: 999,
    backgroundColor: C.card, borderWidth: 1, borderColor: C.border, marginBottom: 12,
  },
  showMoreText: { fontSize: 13, fontWeight: '700', color: C.text },
  tabBtn: {
    paddingVertical: 8, paddingHorizontal: 16, borderRadius: 999,
    backgroundColor: C.card, borderWidth: 1, borderColor: C.border,
  },
  tabBtnActive: { backgroundColor: C.primary, borderColor: C.primary },
  tabText: { fontSize: 13, fontWeight: '600', color: C.textSecondary },
  tabTextActive: { color: C.primaryText },
  card: {
    backgroundColor: C.card, borderRadius: 14, borderWidth: 1, borderColor: C.border,
    padding: 16, marginBottom: 12,
  },
  cardHeader: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  cardTitle: { fontSize: 15, fontWeight: '700', color: C.text },
  cardMeta: { fontSize: 11, color: C.textDim, marginTop: 2 },
  cardDesc: { fontSize: 13, color: C.textSecondary, marginTop: 8, lineHeight: 19 },
  cardTools: { fontSize: 11, color: C.textDim, marginTop: 6, fontStyle: 'italic' },
  runBtn: {
    flexDirection: 'row', alignItems: 'center', gap: 5, backgroundColor: C.primary,
    paddingVertical: 7, paddingHorizontal: 14, borderRadius: 999,
  },
  runBtnText: { color: C.primaryText, fontSize: 12, fontWeight: '700' },
  runBox: { marginTop: 12, gap: 10 },
  input: {
    borderWidth: 1, borderColor: C.border, borderRadius: 10, padding: 10, minHeight: 70,
    color: C.text, backgroundColor: C.bgSoft, fontSize: 13, textAlignVertical: 'top',
  },
  outputBox: { backgroundColor: C.bgSoft, borderRadius: 10, padding: 12, borderWidth: 1, borderColor: C.border },
  outputText: { fontSize: 13, color: C.text, lineHeight: 20 },
  badge: { paddingVertical: 4, paddingHorizontal: 10, borderRadius: 999 },
  badgeText: { fontSize: 11, fontWeight: '700', textTransform: 'capitalize' },
  hitlBox: { marginTop: 12, backgroundColor: C.warningSoft, borderRadius: 10, padding: 12, gap: 10 },
  hitlPrompt: { fontSize: 13, color: C.warningText, fontWeight: '600' },
  approveBtn: { backgroundColor: C.success, paddingVertical: 8, paddingHorizontal: 18, borderRadius: 999 },
  rejectBtn: { backgroundColor: C.error, paddingVertical: 8, paddingHorizontal: 18, borderRadius: 999 },
  emptyBox: { alignItems: 'center', padding: 32, gap: 10 },
  emptyText: { fontSize: 13, color: C.textDim, textAlign: 'center', maxWidth: 480, lineHeight: 19 },
});
