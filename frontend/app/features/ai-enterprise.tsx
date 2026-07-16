import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { View, Text, ScrollView, TouchableOpacity, TextInput, ActivityIndicator } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import api from '../../src/services/api';
import FeatureLayout from '../../src/components/FeatureLayout';
import FeatureToolbar from '../../src/components/FeatureToolbar';
import AIFeedbackBar from '../../src/components/AIFeedbackBar';
import { AIFeatureSkeleton } from '../../src/components/SkeletonLoaders';
import { useTheme } from '../../src/context/ThemeContext';
import { useAuth } from '../../src/context/AuthContext';
import { useFeatureDraft } from '../../src/hooks/useFeatureDraft';
import { useTranslation } from '../../src/hooks/useTranslation';
import { parseStructuredSections } from '../../src/utils/aiEnterpriseParser';

type EnterpriseWorkspace = {
  workspace_id: string;
  title: string;
  context?: string | null;
  focus?: string;
  run_count?: number;
  last_output?: string | null;
  last_run_at?: string | null;
};

type EnterpriseRun = {
  run_id: string;
  workspace_id: string;
  command: string;
  objective?: string;
  session_id: string;
  output: string;
  created_at: string;
};

type EnterprisePlaybook = {
  playbook_id: string;
  workspace_id: string;
  name: string;
  summary: string;
  actions?: string[];
  updated_at?: string;
};

const s = {
  card: { borderRadius: 16, padding: 18, marginHorizontal: 16, marginBottom: 14, borderWidth: 1 },
  title: { fontSize: 16, fontWeight: '700' as const, marginBottom: 12 },
  input: {
    borderRadius: 12,
    paddingHorizontal: 14,
    paddingVertical: 12,
    fontSize: 14,
    borderWidth: 1,
    marginBottom: 12,
    minHeight: 46,
  },
  textArea: {
    borderRadius: 12,
    paddingHorizontal: 14,
    paddingVertical: 12,
    fontSize: 14,
    borderWidth: 1,
    marginBottom: 12,
    minHeight: 110,
    textAlignVertical: 'top' as const,
  },
  btn: {
    flexDirection: 'row' as const,
    alignItems: 'center' as const,
    justifyContent: 'center' as const,
    borderRadius: 14,
    paddingVertical: 14,
    gap: 8,
  },
  result: { fontSize: 14, lineHeight: 22 },
};

function generateGuestId() {
  return `user_${Math.random().toString(36).slice(2)}${Date.now().toString(36)}`.slice(0, 28);
}

export default function AIEnterpriseScreen() {
  const { t } = useTranslation();
  t('i18n.route.features.ai-enterprise.probe');
  const [commandDraft, setCommandDraft] = useFeatureDraft('ai-enterprise');
  const [workspaceTitle, setWorkspaceTitle] = useState('');
  const [workspaceContext, setWorkspaceContext] = useState('');
  const [workspaceFocus, setWorkspaceFocus] = useState('operations');
  const [objective, setObjective] = useState('Operational growth, risk control, and execution clarity');
  const [workspaces, setWorkspaces] = useState<EnterpriseWorkspace[]>([]);
  const [selectedWorkspaceId, setSelectedWorkspaceId] = useState('');
  const [runs, setRuns] = useState<EnterpriseRun[]>([]);
  const [playbooks, setPlaybooks] = useState<EnterprisePlaybook[]>([]);
  const [latestOutput, setLatestOutput] = useState('');
  const [exportSummary, setExportSummary] = useState('');
  const [downloadLinks, setDownloadLinks] = useState({ json: '', csv: '' });
  const [plan, setPlan] = useState('free');
  const [scopeLabel, setScopeLabel] = useState('Limited access');
  const [limits, setLimits] = useState<Record<string, number>>({});
  const [usage, setUsage] = useState({ workspaces_this_month: 0, runs_today: 0, exports_today: 0, playbooks_total: 0 });
  const [bootstrapLoading, setBootstrapLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState<'create' | 'run' | 'playbook' | 'export' | null>(null);
  const [downloadLoading, setDownloadLoading] = useState<'json' | 'csv' | null>(null);
  const [uiError, setUiError] = useState('');

  const { user } = useAuth();
  const { colors } = useTheme();

  const guestIdRef = useRef(generateGuestId());
  const fallbackUserId = useMemo(() => user?.user_id || guestIdRef.current, [user?.user_id]);
  const selectedWorkspace = workspaces.find((item) => item.workspace_id === selectedWorkspaceId) || null;
  const structuredSections = useMemo(() => parseStructuredSections(latestOutput), [latestOutput]);
  const accent = colors.primary;

  const loadWorkspaceRuns = useCallback(async (workspaceId: string) => {
    if (!workspaceId) return;
    const res = await api.get(`/ai-enterprise/workspaces/${workspaceId}/runs`, {
      params: { fallback_user_id: fallbackUserId, limit: 30 },
    });
    const rows: EnterpriseRun[] = Array.isArray(res.data?.runs) ? res.data.runs : [];
    setRuns(rows);
    if (rows[0]?.output) {
      setLatestOutput(rows[0].output);
    }
  }, [fallbackUserId]);

  const loadPlaybooks = useCallback(async () => {
    const res = await api.get('/ai-enterprise/playbooks', { params: { fallback_user_id: fallbackUserId, limit: 40 } });
    const rows: EnterprisePlaybook[] = Array.isArray(res.data?.playbooks) ? res.data.playbooks : [];
    setPlaybooks(rows);
  }, [fallbackUserId]);

  const loadBootstrap = useCallback(async () => {
    setBootstrapLoading(true);
    setUiError('');
    try {
      const res = await api.get('/ai-enterprise/bootstrap', { params: { fallback_user_id: fallbackUserId } });
      const workspaceRows: EnterpriseWorkspace[] = Array.isArray(res.data?.workspaces) ? res.data.workspaces : [];
      setWorkspaces(workspaceRows);
      setSelectedWorkspaceId((prev) => prev || workspaceRows[0]?.workspace_id || '');
      setRuns(Array.isArray(res.data?.recent_runs) ? res.data.recent_runs : []);
      setPlaybooks(Array.isArray(res.data?.playbooks) ? res.data.playbooks : []);
      setPlan(res.data?.plan || 'free');
      setScopeLabel(res.data?.scope_label || 'Limited access');
      setLimits(res.data?.limits || {});
      setUsage({
        workspaces_this_month: Number(res.data?.usage?.workspaces_this_month || 0),
        runs_today: Number(res.data?.usage?.runs_today || 0),
        exports_today: Number(res.data?.usage?.exports_today || 0),
        playbooks_total: Number(res.data?.usage?.playbooks_total || 0),
      });
    } catch (error: any) {
      setUiError(error?.response?.data?.detail?.message || 'Failed to load Business Operations Copilot workspace.');
    } finally {
      setBootstrapLoading(false);
    }
  }, [fallbackUserId]);

  useEffect(() => {
    void loadBootstrap();
  }, [loadBootstrap]);

  useEffect(() => {
    if (selectedWorkspaceId) {
      void loadWorkspaceRuns(selectedWorkspaceId);
    }
  }, [selectedWorkspaceId, loadWorkspaceRuns]);

  const ensureWorkspaceReady = async () => {
    if (selectedWorkspaceId) return selectedWorkspaceId;
    const res = await api.post('/ai-enterprise/workspaces/create', {
      title: workspaceTitle.trim() || `Ops Workspace ${new Date().toLocaleDateString()}`,
      context: workspaceContext.trim() || undefined,
      focus: workspaceFocus,
      fallback_user_id: fallbackUserId,
    });
    const workspace: EnterpriseWorkspace | undefined = res.data?.workspace;
    if (!workspace?.workspace_id) throw new Error('Workspace create failed');
    setWorkspaces((prev) => [workspace, ...prev]);
    setSelectedWorkspaceId(workspace.workspace_id);
    return workspace.workspace_id;
  };

  const createWorkspace = async () => {
    const title = workspaceTitle.trim();
    if (!title) {
      setUiError('Workspace title is required.');
      return;
    }
    setActionLoading('create');
    setUiError('');
    try {
      const res = await api.post('/ai-enterprise/workspaces/create', {
        title,
        context: workspaceContext.trim() || undefined,
        focus: workspaceFocus,
        fallback_user_id: fallbackUserId,
      });
      const workspace: EnterpriseWorkspace | undefined = res.data?.workspace;
      if (workspace?.workspace_id) {
        setWorkspaces((prev) => [workspace, ...prev.filter((item) => item.workspace_id !== workspace.workspace_id)]);
        setSelectedWorkspaceId(workspace.workspace_id);
        setWorkspaceTitle('');
        setWorkspaceContext('');
      }
      await loadBootstrap();
    } catch (error: any) {
      setUiError(error?.response?.data?.detail?.message || 'Workspace creation failed.');
    } finally {
      setActionLoading(null);
    }
  };

  const runEnterpriseCommand = async () => {
    const command = commandDraft.trim();
    if (!command) {
      setUiError('Please enter a command for the copilot run.');
      return;
    }
    setActionLoading('run');
    setUiError('');
    try {
      const workspaceId = await ensureWorkspaceReady();
      const res = await api.post(`/ai-enterprise/workspaces/${workspaceId}/run`, {
        command,
        objective: objective.trim() || undefined,
        session_id: `ai-enterprise-${Date.now()}`,
        idempotency_key: `run-${Date.now()}`,
        fallback_user_id: fallbackUserId,
      });
      setLatestOutput(res.data?.output || 'No output generated.');
      setUsage((prev) => ({ ...prev, runs_today: Number(res.data?.usage?.runs_today ?? prev.runs_today) }));
      await loadWorkspaceRuns(workspaceId);
      await loadBootstrap();
    } catch (error: any) {
      setUiError(error?.response?.data?.detail?.message || 'Copilot run failed.');
    } finally {
      setActionLoading(null);
    }
  };

  const saveCurrentAsPlaybook = async () => {
    const summary = latestOutput.trim();
    if (!summary || !selectedWorkspaceId) {
      setUiError('Run a command first to save a playbook.');
      return;
    }
    setActionLoading('playbook');
    setUiError('');
    try {
      const actions = summary
        .split('\n')
        .map((line) => line.replace(/^[-*\d.\s]+/, '').trim())
        .filter(Boolean)
        .slice(0, 8);
      await api.post('/ai-enterprise/playbooks/save', {
        workspace_id: selectedWorkspaceId,
        name: `${selectedWorkspace?.title || 'Ops'} Playbook ${new Date().toLocaleDateString()}`,
        summary,
        actions,
        fallback_user_id: fallbackUserId,
      });
      await loadPlaybooks();
      await loadBootstrap();
    } catch (error: any) {
      setUiError(error?.response?.data?.detail?.message || 'Failed to save playbook.');
    } finally {
      setActionLoading(null);
    }
  };

  const exportWorkspace = async () => {
    if (!selectedWorkspaceId) {
      setUiError('Select a workspace before export.');
      return;
    }
    setActionLoading('export');
    setUiError('');
    try {
      const res = await api.get(`/ai-enterprise/workspaces/${selectedWorkspaceId}/export`, {
        params: {
          fallback_user_id: fallbackUserId,
          include_runs: true,
          include_playbooks: true,
          limit: 20,
        },
      });
      const runCount = Array.isArray(res.data?.runs) ? res.data.runs.length : 0;
      const playbookCount = Array.isArray(res.data?.playbooks) ? res.data.playbooks.length : 0;
      setExportSummary(`Export ready • runs: ${runCount}, playbooks: ${playbookCount}, export: ${res.data?.export_id || '-'}`);
      const base = `${api.baseURL}/ai-enterprise/workspaces/${selectedWorkspaceId}/export`;
      const queryBase = `fallback_user_id=${encodeURIComponent(fallbackUserId)}&include_runs=true&include_playbooks=true&limit=20`;
      setDownloadLinks({
        json: `${base}?${queryBase}&format=json`,
        csv: `${base}?${queryBase}&format=csv`,
      });
      setUsage((prev) => ({ ...prev, exports_today: Number(res.data?.usage?.exports_today ?? prev.exports_today) }));
    } catch (error: any) {
      setUiError(error?.response?.data?.detail?.message || 'Export failed.');
    } finally {
      setActionLoading(null);
    }
  };

  const downloadExportArtifact = async (format: 'json' | 'csv') => {
    if (!selectedWorkspaceId) {
      setUiError('Select a workspace before downloading export artifacts.');
      return;
    }
    setDownloadLoading(format);
    setUiError('');
    try {
      const response = await api.get(`/ai-enterprise/workspaces/${selectedWorkspaceId}/export`, {
        params: {
          fallback_user_id: fallbackUserId,
          include_runs: true,
          include_playbooks: true,
          limit: 20,
          format,
        },
        responseType: 'text',
      } as any);

      const contentDisposition = String(response?.headers?.['content-disposition'] || '');
      const filenameMatch = contentDisposition.match(/filename="?([^";]+)"?/i);
      const filename = filenameMatch?.[1] || `ai-enterprise-export.${format}`;
      const content = typeof response.data === 'string' ? response.data : JSON.stringify(response.data, null, 2);

      if (typeof window !== 'undefined' && typeof document !== 'undefined') {
        const blob = new Blob([content], { type: format === 'csv' ? 'text/csv' : 'application/json' });
        const url = window.URL.createObjectURL(blob);
        const anchor = document.createElement('a');
        anchor.href = url;
        anchor.download = filename;
        document.body.appendChild(anchor);
        anchor.click();
        document.body.removeChild(anchor);
        window.URL.revokeObjectURL(url);
      }

      setExportSummary(`Downloaded ${format.toUpperCase()} export artifact: ${filename}`);
    } catch (error: any) {
      setUiError(error?.response?.data?.detail?.message || `Failed to download ${format.toUpperCase()} export.`);
    } finally {
      setDownloadLoading(null);
    }
  };

  if (bootstrapLoading) {
    return (
      <FeatureLayout
        feature="ai-enterprise"
        title="Business Operations Copilot"
        subtitle="Enterprise command workspace for strategy execution and operational planning"
        icon="business"
        color={accent}
      >
        <AIFeatureSkeleton />
      </FeatureLayout>
    );
  }

  return (
    <FeatureLayout
      feature="ai-enterprise"
      title="Business Operations Copilot"
      subtitle="Enterprise command workspace for strategy execution and operational planning"
      icon="business"
      color={accent}
    >
      <ScrollView contentContainerStyle={{ paddingVertical: 16 }} data-testid="ai-enterprise-scroll-root" testID="ai-enterprise-scroll-root">
        <View style={[s.card, { backgroundColor: colors.card, borderColor: colors.border }]} data-testid="ai-enterprise-plan-card" testID="ai-enterprise-plan-card">
          <Text style={[s.title, { color: colors.text, marginBottom: 6 }]} data-testid="ai-enterprise-scope-label" testID="ai-enterprise-scope-label">{scopeLabel}</Text>
          <Text style={{ color: colors.textSec, marginBottom: 4 }} data-testid="ai-enterprise-plan-value" testID="ai-enterprise-plan-value">Plan: {plan}</Text>
          <Text style={{ color: colors.textMuted, fontSize: 12 }} data-testid="ai-enterprise-usage-value" testID="ai-enterprise-usage-value">
            Runs today: {usage.runs_today} • Workspaces this month: {usage.workspaces_this_month} • Exports today: {usage.exports_today} • Playbooks: {usage.playbooks_total}
          </Text>
          <Text style={{ color: colors.textMuted, fontSize: 12, marginTop: 6 }} data-testid="ai-enterprise-limits-value" testID="ai-enterprise-limits-value">
            Limits — runs/day: {limits.runs_per_day ?? '-'} • workspaces/month: {limits.workspaces_per_month ?? '-'} • prompt chars: {limits.max_prompt_chars ?? '-'}
          </Text>
        </View>

        <View style={[s.card, { backgroundColor: colors.card, borderColor: colors.border }]} data-testid="ai-enterprise-workspace-card" testID="ai-enterprise-workspace-card">
          <Text style={[s.title, { color: colors.text }]} data-testid="ai-enterprise-workspace-title" testID="ai-enterprise-workspace-title">Workspace Setup</Text>
          <TextInput
            style={[s.input, { backgroundColor: colors.bgSoft, borderColor: colors.border, color: colors.text }]}
            value={workspaceTitle}
            onChangeText={setWorkspaceTitle}
            placeholder="Workspace title"
            placeholderTextColor={colors.textMuted}
            data-testid="ai-enterprise-workspace-title-input"
            testID="ai-enterprise-workspace-title-input"
          />
          <TextInput
            style={[s.textArea, { backgroundColor: colors.bgSoft, borderColor: colors.border, color: colors.text }]}
            value={workspaceContext}
            onChangeText={setWorkspaceContext}
            placeholder="Context: market, team, current bottlenecks"
            placeholderTextColor={colors.textMuted}
            multiline
            data-testid="ai-enterprise-workspace-context-input"
            testID="ai-enterprise-workspace-context-input"
          />
          <TextInput
            style={[s.input, { backgroundColor: colors.bgSoft, borderColor: colors.border, color: colors.text }]}
            value={workspaceFocus}
            onChangeText={setWorkspaceFocus}
            placeholder="Focus area (operations, revenue, retention, GTM)"
            placeholderTextColor={colors.textMuted}
            data-testid="ai-enterprise-workspace-focus-input"
            testID="ai-enterprise-workspace-focus-input"
          />
          <TouchableOpacity
            style={[s.btn, { backgroundColor: accent }]}
            onPress={createWorkspace}
            disabled={actionLoading === 'create'}
            data-testid="ai-enterprise-create-workspace-button"
            testID="ai-enterprise-create-workspace-button"
            accessibilityRole="button"
          >
            {actionLoading === 'create' ? (
              <ActivityIndicator color={colors.primaryText} />
            ) : (
              <>
                <Ionicons name="briefcase" size={18} color={colors.primaryText} />
                <Text style={{ color: colors.primaryText, fontWeight: '700' }}>Create Workspace</Text>
              </>
            )}
          </TouchableOpacity>
          <Text style={{ color: colors.textMuted, marginTop: 10, fontSize: 12 }} data-testid="ai-enterprise-selected-workspace" testID="ai-enterprise-selected-workspace">
            Selected workspace: {selectedWorkspace?.title || 'None'}
          </Text>
        </View>

        <View style={[s.card, { backgroundColor: colors.card, borderColor: colors.border }]} data-testid="ai-enterprise-command-card" testID="ai-enterprise-command-card">
          <Text style={[s.title, { color: colors.text }]} data-testid="ai-enterprise-command-title" testID="ai-enterprise-command-title">Command Mode</Text>
          <TextInput
            style={[s.input, { backgroundColor: colors.bgSoft, borderColor: colors.border, color: colors.text }]}
            value={objective}
            onChangeText={setObjective}
            placeholder="Objective"
            placeholderTextColor={colors.textMuted}
            data-testid="ai-enterprise-objective-input"
            testID="ai-enterprise-objective-input"
          />
          <TextInput
            style={[s.textArea, { backgroundColor: colors.bgSoft, borderColor: colors.border, color: colors.text }]}
            value={commandDraft}
            onChangeText={setCommandDraft}
            placeholder="Describe the decision scenario, constraints, and desired outcome"
            placeholderTextColor={colors.textMuted}
            multiline
            data-testid="ai-enterprise-command-input"
            testID="ai-enterprise-command-input"
          />
          <TouchableOpacity
            style={[s.btn, { backgroundColor: accent }]}
            onPress={runEnterpriseCommand}
            disabled={actionLoading === 'run'}
            data-testid="ai-enterprise-run-command-button"
            testID="ai-enterprise-run-command-button"
            accessibilityRole="button"
          >
            {actionLoading === 'run' ? (
              <ActivityIndicator color={colors.primaryText} />
            ) : (
              <>
                <Ionicons name="rocket" size={18} color={colors.primaryText} />
                <Text style={{ color: colors.primaryText, fontWeight: '700' }}>Run Copilot Command</Text>
              </>
            )}
          </TouchableOpacity>
        </View>

        {latestOutput ? (
          <View style={[s.card, { backgroundColor: colors.card, borderColor: colors.border }]} data-testid="ai-enterprise-output-card" testID="ai-enterprise-output-card">
            <Text style={[s.title, { color: colors.text }]} data-testid="ai-enterprise-output-title" testID="ai-enterprise-output-title">Latest Strategic Output</Text>
            <Text style={[s.result, { color: colors.textSec }]} data-testid="ai-enterprise-output-text" testID="ai-enterprise-output-text">{latestOutput}</Text>
            <FeatureToolbar content={latestOutput} featureKey="ai-enterprise" title="Business Operations Copilot Output" onClear={() => setLatestOutput('')} />
            <AIFeedbackBar feature="ai-enterprise" response={latestOutput} />
            <View style={{ flexDirection: 'row', gap: 10, marginTop: 12 }}>
              <TouchableOpacity
                style={[s.btn, { backgroundColor: colors.bgSoft, borderColor: colors.border, borderWidth: 1, flex: 1 }]}
                onPress={saveCurrentAsPlaybook}
                disabled={actionLoading === 'playbook'}
                data-testid="ai-enterprise-save-playbook-button"
                testID="ai-enterprise-save-playbook-button"
                accessibilityRole="button"
              >
                {actionLoading === 'playbook' ? <ActivityIndicator color={colors.text} /> : <Text style={{ color: colors.text, fontWeight: '700' }}>Save Playbook</Text>}
              </TouchableOpacity>
              <TouchableOpacity
                style={[s.btn, { backgroundColor: colors.bgSoft, borderColor: colors.border, borderWidth: 1, flex: 1 }]}
                onPress={exportWorkspace}
                disabled={actionLoading === 'export'}
                data-testid="ai-enterprise-export-button"
                testID="ai-enterprise-export-button"
                accessibilityRole="button"
              >
                {actionLoading === 'export' ? <ActivityIndicator color={colors.text} /> : <Text style={{ color: colors.text, fontWeight: '700' }}>Export Workspace</Text>}
              </TouchableOpacity>
            </View>
          </View>
        ) : null}

        {latestOutput ? (
          <View style={[s.card, { backgroundColor: colors.card, borderColor: colors.border }]} data-testid="ai-enterprise-structured-sections-card" testID="ai-enterprise-structured-sections-card">
            <Text style={[s.title, { color: colors.text }]} data-testid="ai-enterprise-structured-sections-title" testID="ai-enterprise-structured-sections-title">Structured Strategy Sections</Text>

            <View style={{ marginBottom: 10 }} data-testid="ai-enterprise-section-executive-summary" testID="ai-enterprise-section-executive-summary">
              <Text style={{ color: colors.text, fontWeight: '700', marginBottom: 4 }}>Executive Summary</Text>
              <Text style={{ color: colors.textSec }}>{structuredSections.executiveSummary || 'Section not explicitly detected in output yet.'}</Text>
            </View>

            <View style={{ marginBottom: 10 }} data-testid="ai-enterprise-section-objective-tree" testID="ai-enterprise-section-objective-tree">
              <Text style={{ color: colors.text, fontWeight: '700', marginBottom: 4 }}>Objective Tree</Text>
              <Text style={{ color: colors.textSec }}>{structuredSections.objectiveTree || 'Section not explicitly detected in output yet.'}</Text>
            </View>

            <View style={{ marginBottom: 10 }} data-testid="ai-enterprise-section-kpi-pack" testID="ai-enterprise-section-kpi-pack">
              <Text style={{ color: colors.text, fontWeight: '700', marginBottom: 4 }}>KPI Pack</Text>
              <Text style={{ color: colors.textSec }}>{structuredSections.kpiPack || 'Section not explicitly detected in output yet.'}</Text>
            </View>

            <View style={{ marginBottom: 10 }} data-testid="ai-enterprise-section-risk-register" testID="ai-enterprise-section-risk-register">
              <Text style={{ color: colors.text, fontWeight: '700', marginBottom: 4 }}>Risk Register</Text>
              <Text style={{ color: colors.textSec }}>{structuredSections.riskRegister || 'Section not explicitly detected in output yet.'}</Text>
            </View>

            <View data-testid="ai-enterprise-section-30-60-90" testID="ai-enterprise-section-30-60-90">
              <Text style={{ color: colors.text, fontWeight: '700', marginBottom: 4 }}>30/60/90 Plan</Text>
              <Text style={{ color: colors.textSec }}>{structuredSections.plan306090 || 'Section not explicitly detected in output yet.'}</Text>
            </View>
          </View>
        ) : null}

        {exportSummary ? (
          <View style={[s.card, { backgroundColor: colors.card, borderColor: colors.border }]} data-testid="ai-enterprise-export-card" testID="ai-enterprise-export-card">
            <Text style={[s.title, { color: colors.text }]} data-testid="ai-enterprise-export-title" testID="ai-enterprise-export-title">Export Summary</Text>
            <Text style={{ color: colors.textSec }} data-testid="ai-enterprise-export-summary" testID="ai-enterprise-export-summary">{exportSummary}</Text>
            <Text style={{ color: colors.textMuted, marginTop: 8 }} data-testid="ai-enterprise-export-json-link" testID="ai-enterprise-export-json-link">JSON download: {downloadLinks.json || '-'}</Text>
            <Text style={{ color: colors.textMuted }} data-testid="ai-enterprise-export-csv-link" testID="ai-enterprise-export-csv-link">CSV download: {downloadLinks.csv || '-'}</Text>
            <View style={{ flexDirection: 'row', gap: 10, marginTop: 12 }}>
              <TouchableOpacity
                style={[s.btn, { backgroundColor: colors.bgSoft, borderColor: colors.border, borderWidth: 1, flex: 1 }]}
                onPress={() => downloadExportArtifact('json')}
                disabled={downloadLoading === 'json'}
                data-testid="ai-enterprise-download-json-button"
                testID="ai-enterprise-download-json-button"
                accessibilityRole="button"
              >
                {downloadLoading === 'json' ? <ActivityIndicator color={colors.text} /> : <Text style={{ color: colors.text, fontWeight: '700' }}>Download JSON</Text>}
              </TouchableOpacity>
              <TouchableOpacity
                style={[s.btn, { backgroundColor: colors.bgSoft, borderColor: colors.border, borderWidth: 1, flex: 1 }]}
                onPress={() => downloadExportArtifact('csv')}
                disabled={downloadLoading === 'csv'}
                data-testid="ai-enterprise-download-csv-button"
                testID="ai-enterprise-download-csv-button"
                accessibilityRole="button"
              >
                {downloadLoading === 'csv' ? <ActivityIndicator color={colors.text} /> : <Text style={{ color: colors.text, fontWeight: '700' }}>Download CSV</Text>}
              </TouchableOpacity>
            </View>
          </View>
        ) : null}

        <View style={[s.card, { backgroundColor: colors.card, borderColor: colors.border }]} data-testid="ai-enterprise-runs-card" testID="ai-enterprise-runs-card">
          <Text style={[s.title, { color: colors.text }]} data-testid="ai-enterprise-runs-title" testID="ai-enterprise-runs-title">Run Timeline</Text>
          {runs.length ? runs.slice(0, 6).map((run) => (
            <View key={run.run_id} style={{ paddingVertical: 8, borderBottomWidth: 1, borderBottomColor: colors.border }} data-testid={`ai-enterprise-run-item-${run.run_id}`}>
              <Text style={{ color: colors.text, fontWeight: '600', marginBottom: 4 }} data-testid={`ai-enterprise-run-session-${run.run_id}`}>Session: {run.session_id}</Text>
              <Text style={{ color: colors.textSec, marginBottom: 4 }} numberOfLines={2} data-testid={`ai-enterprise-run-command-${run.run_id}`}>{run.command}</Text>
              <Text style={{ color: colors.textMuted, fontSize: 12 }} data-testid={`ai-enterprise-run-created-${run.run_id}`}>{run.created_at}</Text>
            </View>
          )) : <Text style={{ color: colors.textMuted }} data-testid="ai-enterprise-runs-empty" testID="ai-enterprise-runs-empty">No runs yet.</Text>}
        </View>

        <View style={[s.card, { backgroundColor: colors.card, borderColor: colors.border }]} data-testid="ai-enterprise-playbooks-card" testID="ai-enterprise-playbooks-card">
          <Text style={[s.title, { color: colors.text }]} data-testid="ai-enterprise-playbooks-title" testID="ai-enterprise-playbooks-title">Saved Playbooks</Text>
          {playbooks.length ? playbooks.slice(0, 6).map((playbook) => (
            <View key={playbook.playbook_id} style={{ paddingVertical: 8, borderBottomWidth: 1, borderBottomColor: colors.border }} data-testid={`ai-enterprise-playbook-item-${playbook.playbook_id}`}>
              <Text style={{ color: colors.text, fontWeight: '600', marginBottom: 4 }} data-testid={`ai-enterprise-playbook-name-${playbook.playbook_id}`}>{playbook.name}</Text>
              <Text style={{ color: colors.textSec }} numberOfLines={2} data-testid={`ai-enterprise-playbook-summary-${playbook.playbook_id}`}>{playbook.summary}</Text>
            </View>
          )) : <Text style={{ color: colors.textMuted }} data-testid="ai-enterprise-playbooks-empty" testID="ai-enterprise-playbooks-empty">No playbooks yet.</Text>}
        </View>

        {uiError ? (
          <View style={[s.card, { borderColor: colors.error, backgroundColor: colors.errorSoft }]} data-testid="ai-enterprise-error-card" testID="ai-enterprise-error-card">
            <Text style={{ color: colors.errorText }} data-testid="ai-enterprise-error-text" testID="ai-enterprise-error-text">{uiError}</Text>
          </View>
        ) : null}
      </ScrollView>
    </FeatureLayout>
  );
}