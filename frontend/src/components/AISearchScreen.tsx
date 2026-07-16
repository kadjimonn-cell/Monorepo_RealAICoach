import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  View,
  Text,
  TextInput,
  TouchableOpacity,
  ScrollView,
  ActivityIndicator,
  useWindowDimensions,
  Linking,
} from 'react-native';
import { FontAwesome5 } from '@expo/vector-icons';

import { useTheme } from '../context/ThemeContext';
import { useAuth } from '../context/AuthContext';
import api from '../services/api';
import FeatureToolbar from './FeatureToolbar';
import AIFeedbackBar from './AIFeedbackBar';
import MarkdownDisplay from './MarkdownDisplay';
import { useAppStore } from '../store/appStore';
import { handleAppRecoverableError } from '../utils/appRecoverableError';

export default function AISearchScreen() {
  const { width } = useWindowDimensions();
  const { colors } = useTheme();
  const { user } = useAuth();
  const { userId, initializeUser } = useAppStore();

  const [localGuestId] = useState(() => `user_${Math.random().toString(36).slice(2)}${Date.now().toString(36)}`.slice(0, 78));
  const fallbackUserId = useMemo(() => user?.user_id || userId || localGuestId || '', [localGuestId, user?.user_id, userId]);

  const [projects, setProjects] = useState([]);
  const [activeProjectId, setActiveProjectId] = useState('');
  const [runs, setRuns] = useState([]);
  const [insights, setInsights] = useState([]);
  const [query, setQuery] = useState('');
  const [projectTitle, setProjectTitle] = useState('');
  const [projectTopic, setProjectTopic] = useState('');
  const [insightTitle, setInsightTitle] = useState('');
  const [insightBody, setInsightBody] = useState('');
  const [errorMessage, setErrorMessage] = useState('');
  const [loadingBootstrap, setLoadingBootstrap] = useState(true);
  const [running, setRunning] = useState(false);
  const [creatingProject, setCreatingProject] = useState(false);
  const [savingInsight, setSavingInsight] = useState(false);
  const [stats, setStats] = useState({ project_count: 0, insight_count: 0, avg_runs_per_project: 0 });
  const [usage, setUsage] = useState({ can_run: true, runs_used_today: 0, daily_limit: 5, tier: 'free', limit_reached: false });
  const [showUpgradeModal, setShowUpgradeModal] = useState(false);
  const [upgradeMessage, setUpgradeMessage] = useState('');

  const isWide = width >= 1080;
  const latestRun = runs[0] || null;

  // Helper: Get source category badge with emoji, label, and color
  const getSourceBadge = (sourceType) => {
    const badges = {
      reference: { emoji: '📚', label: 'Reference', color: colors.primary },
      search: { emoji: '🔍', label: 'Search', color: colors.primary },
      academic: { emoji: '🔬', label: 'Academic', color: colors.success },
      medical: { emoji: '🏥', label: 'Medical', color: colors.error },
      financial: { emoji: '💼', label: 'Financial', color: colors.warning },
      fallback: { emoji: '📄', label: 'Source', color: colors.textMuted },
    };
    return badges[sourceType] || badges.fallback;
  };

  // Helper: Format published date for display
  const formatPublishedDate = (dateStr) => {
    if (!dateStr) return null;
    try {
      const date = new Date(dateStr);
      if (isNaN(date.getTime())) return dateStr; // Invalid date, return raw string
      return date.toLocaleDateString('en-US', {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
      });
    } catch {
      return dateStr; // Fallback to raw string
    }
  };

  const s = {
    card: {
      backgroundColor: colors.card,
      borderRadius: 16,
      padding: 16,
      marginBottom: 12,
      borderWidth: 1,
      borderColor: colors.border,
    },
    title: { color: colors.text, fontSize: 15, fontWeight: '800', marginBottom: 10 },
    input: {
      backgroundColor: colors.bg,
      borderRadius: 10,
      borderWidth: 1,
      borderColor: colors.border,
      color: colors.text,
      paddingHorizontal: 12,
      paddingVertical: 10,
      fontSize: 14,
    },
    primaryButton: {
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'center',
      gap: 8,
      borderRadius: 12,
      backgroundColor: colors.primary,
      paddingVertical: 11,
    },
    secondaryButton: {
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'center',
      gap: 8,
      borderRadius: 12,
      backgroundColor: colors.bgSoft,
      borderWidth: 1,
      borderColor: colors.border,
      paddingVertical: 11,
    },
  };

  const ensureIdentity = useCallback(async () => {
    const current = fallbackUserId || localGuestId;
    if (current) return current;
    const initialized = await initializeUser();
    return initialized || useAppStore.getState().userId || localGuestId;
  }, [fallbackUserId, initializeUser, localGuestId]);

  const loadProject = useCallback(async (projectId, identity) => {
    if (!projectId || !identity) return;
    try {
      const res = await api.get(`/research-navigator/projects/${projectId}`, {
        params: { fallback_user_id: identity },
      });
      setRuns(res?.data?.runs || []);
      setInsights(res?.data?.insight_notes || []);
      setActiveProjectId(projectId);
      setErrorMessage('');
    } catch (error) {
      handleAppRecoverableError({
        scope: 'components/AISearchScreen.tsx#loadProject',
        error,
        message: 'Failed to load project details.',
      
        notifyMode: 'silent',
      });
      setErrorMessage('Unable to load selected project.');
    }
  }, []);

  const loadBootstrap = useCallback(async () => {
    const identity = await ensureIdentity();
    if (!identity) return;
    setLoadingBootstrap(true);
    try {
      const res = await api.get('/research-navigator/bootstrap', {
        params: { fallback_user_id: identity },
      });
      const incomingProjects = res?.data?.projects || [];
      setProjects(incomingProjects);
      setInsights(res?.data?.insight_notes || []);
      setStats(res?.data?.stats || { project_count: 0, insight_count: 0, avg_runs_per_project: 0 });
      
      // Set usage data from response
      const usageData = res?.data?.usage;
      console.log('[AISearchScreen] Bootstrap response usage data:', usageData);
      if (usageData) {
        console.log('[AISearchScreen] Setting usage state:', usageData);
        setUsage(usageData);
      } else {
        console.warn('[AISearchScreen] No usage data in bootstrap response, setting default');
        setUsage({
          can_run: true,
          runs_used_today: 0,
          daily_limit: 5,
          tier: 'free',
          limit_reached: false,
        });
      }

      setErrorMessage('');

      if (incomingProjects.length > 0) {
        await loadProject(incomingProjects[0].project_id, identity);
      } else {
        setRuns([]);
        setActiveProjectId('');
      }
    } catch (error) {
      handleAppRecoverableError({
        scope: 'components/AISearchScreen.tsx#loadBootstrap',
        error,
        message: 'Failed to initialize Deep Research Navigator workspace.',
      
        notifyMode: 'silent',
      });
      setErrorMessage('Workspace initialization failed.');
      // Set default usage even on error so badge always shows
      setUsage({
        can_run: true,
        runs_used_today: 0,
        daily_limit: 5,
        tier: 'free',
        limit_reached: false,
      });
    } finally {
      setLoadingBootstrap(false);
    }
  }, [ensureIdentity, loadProject]);

  useEffect(() => {
    initializeUser();
  }, [initializeUser]);

  useEffect(() => {
    const timer = setTimeout(() => {
      void loadBootstrap();
    }, 0);
    return () => clearTimeout(timer);
  }, [loadBootstrap]);

  const createProject = async () => {
    const identity = await ensureIdentity();
    if (!identity) return;
    setCreatingProject(true);
    try {
      const title = (projectTitle || 'Research Project').trim();
      const topic = projectTopic.trim();
      const res = await api.post('/research-navigator/projects', {
        title,
        topic,
        fallback_user_id: identity,
      });
      const project = res?.data?.project;
      if (project) {
        setProjects((prev) => [project, ...prev.filter((p) => p.project_id !== project.project_id)]);
        setProjectTitle('');
        setProjectTopic('');
        await loadProject(project.project_id, identity);
      }
    } catch (error) {
      handleAppRecoverableError({
        scope: 'components/AISearchScreen.tsx#createProject',
        error,
        message: 'Could not create research project.',
      
        notifyMode: 'silent',
      });
      setErrorMessage('Project creation failed.');
    } finally {
      setCreatingProject(false);
    }
  };

  const runResearch = async () => {
    if (!query.trim()) return;
    const identity = await ensureIdentity();
    if (!identity) return;
    
    // Check if at limit before running
    if (usage && usage.limit_reached) {
      const tier = usage.tier || 'free';
      const nextTier = tier === 'free' ? 'Basic' : 'Premium';
      setUpgradeMessage(`You've reached your daily limit of ${usage.daily_limit} research runs. Upgrade to ${nextTier} for ${tier === 'free' ? '20 runs/day' : 'unlimited research'}!`);
      setShowUpgradeModal(true);
      return;
    }
    
    setRunning(true);
    setErrorMessage('');
    try {
      let projectId = activeProjectId;
      if (!projectId) {
        const res = await api.post('/research-navigator/projects', {
          title: `Research: ${query.slice(0, 48)}`,
          topic: query.slice(0, 220),
          fallback_user_id: identity,
        });
        const project = res?.data?.project;
        if (!project?.project_id) {
          setRunning(false);
          return;
        }
        projectId = project.project_id;
        setProjects((prev) => [project, ...prev.filter((p) => p.project_id !== project.project_id)]);
        setActiveProjectId(projectId);
      }

      const runRes = await api.post(`/research-navigator/projects/${projectId}/runs`, {
        query: query.trim(),
        fallback_user_id: identity,
        idempotency_key: `${projectId}:${Date.now()}`,
      });
      const run = runRes?.data?.run;
      if (run) {
        setRuns((prev) => [run, ...prev]);
      }
      await loadProject(projectId, identity);
    } catch (error) {
      // Check if it's a limit error
      if (error?.response?.status === 403 && error?.response?.data?.detail?.upgrade_prompt) {
        const detail = error.response.data.detail;
        setUpgradeMessage(detail.message || 'Upgrade to continue researching.');
        setShowUpgradeModal(true);
      } else {
        handleAppRecoverableError({
          scope: 'components/AISearchScreen.tsx#runResearch',
          error,
          message: 'Research run failed. Retry.',
        
        notifyMode: 'silent',
      });
        setErrorMessage('Research run failed. Retry your query.');
      }
    } finally {
      setRunning(false);
    }
  };

  const saveInsight = async () => {
    if (!activeProjectId || !insightTitle.trim() || !insightBody.trim()) return;
    const identity = await ensureIdentity();
    if (!identity) return;
    setSavingInsight(true);
    try {
      const res = await api.post(`/research-navigator/projects/${activeProjectId}/insights`, {
        title: insightTitle.trim(),
        content: insightBody.trim(),
        fallback_user_id: identity,
      });
      const note = res?.data?.insight;
      if (note) {
        setInsights((prev) => [note, ...prev]);
        setInsightTitle('');
        setInsightBody('');
      }
    } catch (error) {
      handleAppRecoverableError({
        scope: 'components/AISearchScreen.tsx#saveInsight',
        error,
        message: 'Failed to save insight note.',
      
        notifyMode: 'silent',
      });
      setErrorMessage('Could not save insight note.');
    } finally {
      setSavingInsight(false);
    }
  };

  const projectListCard = (
    <View style={[s.card, { flex: isWide ? 0.34 : 1 }]} data-testid="deep-research-projects-card" testID="deep-research-projects-card">
      <Text style={s.title} data-testid="deep-research-projects-title" testID="deep-research-projects-title">Research Projects</Text>
      <View style={{ gap: 8, marginBottom: 10 }}>
        <TextInput value={projectTitle} onChangeText={setProjectTitle} style={s.input} placeholder="Project title" placeholderTextColor={colors.textMuted} data-testid="deep-research-new-project-title-input" testID="deep-research-new-project-title-input" />
        <TextInput value={projectTopic} onChangeText={setProjectTopic} style={s.input} placeholder="Project topic (optional)" placeholderTextColor={colors.textMuted} data-testid="deep-research-new-project-topic-input" testID="deep-research-new-project-topic-input" />
        <TouchableOpacity style={s.secondaryButton} onPress={() => void createProject()} disabled={creatingProject} data-testid="deep-research-create-project-button" testID="deep-research-create-project-button" accessibilityRole="button">
          {creatingProject ? <ActivityIndicator size="small" color={colors.text} /> : <><FontAwesome5 name="plus" size={14} color={colors.text} /><Text style={{ color: colors.text, fontWeight: '700' }}>Create Project</Text></>}
        </TouchableOpacity>
      </View>
      <View style={{ gap: 8 }}>
        {projects.length === 0 ? (
          <Text style={{ color: colors.textMuted, fontSize: 12 }} data-testid="deep-research-empty-projects-message" testID="deep-research-empty-projects-message">No projects yet.</Text>
        ) : projects.map((project) => {
          const selected = project.project_id === activeProjectId;
          return (
            <TouchableOpacity key={project.project_id} onPress={() => void loadProject(project.project_id, fallbackUserId)} style={{ borderWidth: 1, borderColor: selected ? colors.primary : colors.border, borderRadius: 10, backgroundColor: selected ? colors.primarySoft : colors.bg, paddingHorizontal: 10, paddingVertical: 8 }} data-testid={`deep-research-project-item-${project.project_id}`} testID={`deep-research-project-item-${project.project_id}`} accessibilityRole="button">
              <Text style={{ color: selected ? colors.primary : colors.text, fontWeight: '700', fontSize: 12 }}>{project.title}</Text>
              <Text style={{ color: colors.textMuted, fontSize: 11 }}>{project.run_count || 0} runs</Text>
            </TouchableOpacity>
          );
        })}
      </View>
    </View>
  );

  return (
    <View style={{ flex: 1 }} data-testid="deep-research-navigator-v2-root" testID="deep-research-navigator-v2-root">
      <View style={[s.card, { marginHorizontal: 0 }]} data-testid="deep-research-kpi-strip" testID="deep-research-kpi-strip">
        <Text style={s.title}>Navigator Momentum</Text>
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
          <View style={{ backgroundColor: colors.bgSoft, borderRadius: 999, paddingHorizontal: 10, paddingVertical: 6 }} data-testid="deep-research-kpi-projects" testID="deep-research-kpi-projects"><Text style={{ color: colors.text, fontSize: 11, fontWeight: '700' }}>Projects: {stats.project_count}</Text></View>
          <View style={{ backgroundColor: colors.bgSoft, borderRadius: 999, paddingHorizontal: 10, paddingVertical: 6 }} data-testid="deep-research-kpi-insights" testID="deep-research-kpi-insights"><Text style={{ color: colors.text, fontSize: 11, fontWeight: '700' }}>Insights: {stats.insight_count}</Text></View>
          <View style={{ backgroundColor: colors.bgSoft, borderRadius: 999, paddingHorizontal: 10, paddingVertical: 6 }} data-testid="deep-research-kpi-runs" testID="deep-research-kpi-runs"><Text style={{ color: colors.text, fontSize: 11, fontWeight: '700' }}>Avg Runs/Project: {stats.avg_runs_per_project}</Text></View>
          <View 
            style={{ 
              backgroundColor: usage?.limit_reached ? colors.errorSoft : colors.primarySoft, 
              borderRadius: 999, 
              paddingHorizontal: 10, 
              paddingVertical: 6 
            }} 
            data-testid="deep-research-usage-badge" 
            testID="deep-research-usage-badge"
          >
            <Text style={{ color: usage?.limit_reached ? colors.error : colors.primary, fontSize: 11, fontWeight: '700' }}>
              Research Usage: {usage?.runs_used_today || 0}/{usage?.daily_limit === -1 ? '∞' : (usage?.daily_limit || 5)} ({usage?.tier || 'free'})
            </Text>
          </View>
        </View>
      </View>

      {loadingBootstrap ? (
        <View style={[s.card, { alignItems: 'center', justifyContent: 'center', paddingVertical: 20 }]} data-testid="deep-research-bootstrap-loading" testID="deep-research-bootstrap-loading">
          <ActivityIndicator size="small" color={colors.primary} />
          <Text style={{ color: colors.textMuted, marginTop: 8 }}>Loading research workspace...</Text>
        </View>
      ) : null}

      {errorMessage ? (
        <View style={[s.card, { borderColor: colors.errorSoft, backgroundColor: colors.errorSoft }]} data-testid="deep-research-error-banner" testID="deep-research-error-banner">
          <Text style={{ color: colors.error, fontWeight: '700' }} data-testid="deep-research-error-text" testID="deep-research-error-text">{errorMessage}</Text>
        </View>
      ) : null}

      <ScrollView contentContainerStyle={{ paddingBottom: 24 }}>
        {isWide ? (
          <View style={{ flexDirection: 'row', gap: 12, alignItems: 'flex-start' }}>
            {projectListCard}
            <View style={{ flex: 0.66 }}>
              <View style={s.card} data-testid="deep-research-runner-card" testID="deep-research-runner-card">
                <Text style={s.title}>Research Runner</Text>
                <TextInput value={query} onChangeText={setQuery} style={[s.input, { minHeight: 90, textAlignVertical: 'top' }]} multiline placeholder="Enter a research question (market analysis, policy impact, competitor landscape, etc.)" placeholderTextColor={colors.textMuted} data-testid="deep-research-query-input" testID="deep-research-query-input" />
                <TouchableOpacity style={[s.primaryButton, { marginTop: 10 }]} onPress={() => void runResearch()} disabled={running} data-testid="deep-research-run-button" testID="deep-research-run-button" accessibilityRole="button">
                  {running ? <ActivityIndicator size="small" color={colors.primaryText} /> : <><FontAwesome5 name="search" size={14} color={colors.primaryText} /><Text style={{ color: colors.primaryText, fontWeight: '800' }}>Run Deep Research</Text></>}
                </TouchableOpacity>
              </View>

              {latestRun ? (
                <>
                  <View style={s.card} data-testid="deep-research-latest-run-card" testID="deep-research-latest-run-card">
                    <Text style={s.title}>Latest Research Synthesis</Text>
                    <MarkdownDisplay content={latestRun.answer || ''} />
                    <FeatureToolbar content={latestRun.answer || ''} featureKey="ai-search" title="Research Synthesis" onClear={() => {}} />
                    <AIFeedbackBar feature="ai-search" response={latestRun.answer || ''} />
                  </View>

                  <View style={s.card} data-testid="deep-research-steps-card" testID="deep-research-steps-card">
                    <Text style={s.title}>Execution Timeline</Text>
                    <View style={{ gap: 8 }}>
                      {(latestRun.steps || []).map((step, idx) => (
                        <View key={`${step.step}-${idx}`} style={{ borderWidth: 1, borderColor: colors.border, borderRadius: 10, paddingHorizontal: 10, paddingVertical: 8, backgroundColor: colors.bg }} data-testid={`deep-research-step-${step.step}`} testID={`deep-research-step-${step.step}`}>
                          <Text style={{ color: colors.text, fontWeight: '700', fontSize: 12 }}>{step.step}</Text>
                          <Text style={{ color: colors.textMuted, fontSize: 11 }}>{step.status} • {step.updated_at}</Text>
                        </View>
                      ))}
                    </View>
                  </View>

                  <View style={s.card} data-testid="deep-research-sources-card" testID="deep-research-sources-card">
                    <Text style={s.title}>Evidence Sources</Text>
                    <View style={{ gap: 8 }}>
                      {(latestRun.sources || []).map((source) => {
                        const badge = getSourceBadge(source.source_type);
                        const publishedDate = formatPublishedDate(source.published_at);
                        return (
                          <TouchableOpacity
                            key={source.source_id} 
                            onPress={() => source.url && Linking.openURL(source.url)} 
                            style={{ 
                              borderWidth: 1, 
                              borderColor: colors.border, 
                              borderLeftWidth: 3,
                              borderLeftColor: badge.color,
                              borderRadius: 10, 
                              backgroundColor: colors.bg, 
                              paddingHorizontal: 10, 
                              paddingVertical: 8 
                            }} 
                            data-testid={`deep-research-source-item-${source.source_id}`} 
                            testID={`deep-research-source-item-${source.source_id}`} 
                            accessibilityRole="button"
                          >
                            {/* Category Badge Row */}
                            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 4 }}>
                              <Text style={{ fontSize: 14 }}>{badge.emoji}</Text>
                              <Text style={{ fontSize: 10, fontWeight: '600', color: badge.color }}>
                                {badge.label}
                              </Text>
                              {publishedDate && (
                                <>
                                  <Text style={{ fontSize: 10, color: colors.textMuted }}>•</Text>
                                  <Text style={{ fontSize: 10, color: colors.textMuted }}>
                                    {publishedDate}
                                  </Text>
                                </>
                              )}
                            </View>
                            {/* Source Content */}
                            <Text style={{ color: colors.primary, fontWeight: '700', fontSize: 12 }}>{source.title}</Text>
                            <Text style={{ color: colors.textMuted, fontSize: 11, marginTop: 2 }}>{source.url}</Text>
                            <Text style={{ color: colors.text, fontSize: 12, marginTop: 4 }}>{source.snippet}</Text>
                            <Text style={{ color: colors.textMuted, fontSize: 11, marginTop: 4 }}>Confidence: {source.confidence}</Text>
                          </TouchableOpacity>
                        );
                      })}
                    </View>
                  </View>

                  <View style={s.card} data-testid="deep-research-followups-card" testID="deep-research-followups-card">
                    <Text style={s.title}>Follow-up Questions</Text>
                    <View style={{ gap: 8 }}>
                      {(latestRun.follow_up_questions || []).map((fq, idx) => (
                        <TouchableOpacity key={`${idx}-${fq}`} onPress={() => setQuery(fq)} style={{ borderWidth: 1, borderColor: colors.border, borderRadius: 10, backgroundColor: colors.bgSoft, paddingHorizontal: 10, paddingVertical: 8 }} data-testid={`deep-research-followup-item-${idx}`} testID={`deep-research-followup-item-${idx}`} accessibilityRole="button">
                          <Text style={{ color: colors.text, fontSize: 12 }}>{fq}</Text>
                        </TouchableOpacity>
                      ))}
                    </View>
                  </View>
                </>
              ) : null}
            </View>
          </View>
        ) : (
          <>
            {projectListCard}
            <View style={s.card}>
              <Text style={s.title}>Research Runner</Text>
              <TextInput value={query} onChangeText={setQuery} style={[s.input, { minHeight: 90, textAlignVertical: 'top' }]} multiline placeholder="Enter research question" placeholderTextColor={colors.textMuted} data-testid="deep-research-query-input" testID="deep-research-query-input" />
              <TouchableOpacity style={[s.primaryButton, { marginTop: 10 }]} onPress={() => void runResearch()} disabled={running} data-testid="deep-research-run-button" testID="deep-research-run-button" accessibilityRole="button">
                {running ? <ActivityIndicator size="small" color={colors.primaryText} /> : <Text style={{ color: colors.primaryText, fontWeight: '800' }}>Run Deep Research</Text>}
              </TouchableOpacity>
            </View>
          </>
        )}

        <View style={s.card} data-testid="deep-research-insights-card" testID="deep-research-insights-card">
          <Text style={s.title}>Insight Board</Text>
          <View style={{ gap: 8 }}>
            <TextInput value={insightTitle} onChangeText={setInsightTitle} style={s.input} placeholder="Insight title" placeholderTextColor={colors.textMuted} data-testid="deep-research-insight-title-input" testID="deep-research-insight-title-input" />
            <TextInput value={insightBody} onChangeText={setInsightBody} style={[s.input, { minHeight: 80, textAlignVertical: 'top' }]} multiline placeholder="Document a validated insight for this project" placeholderTextColor={colors.textMuted} data-testid="deep-research-insight-body-input" testID="deep-research-insight-body-input" />
            <TouchableOpacity style={s.secondaryButton} onPress={() => void saveInsight()} disabled={savingInsight} data-testid="deep-research-save-insight-button" testID="deep-research-save-insight-button" accessibilityRole="button">
              {savingInsight ? <ActivityIndicator size="small" color={colors.text} /> : <><FontAwesome5 name="save" size={14} color={colors.text} /><Text style={{ color: colors.text, fontWeight: '700' }}>Save Insight</Text></>}
            </TouchableOpacity>
          </View>
          <View style={{ gap: 8, marginTop: 10 }}>
            {insights.length === 0 ? (
              <Text style={{ color: colors.textMuted, fontSize: 12 }} data-testid="deep-research-empty-insights-message" testID="deep-research-empty-insights-message">No insights saved yet.</Text>
            ) : insights.slice(0, 12).map((insight) => (
              <View key={insight.note_id} style={{ borderWidth: 1, borderColor: colors.border, borderRadius: 10, backgroundColor: colors.bg, paddingHorizontal: 10, paddingVertical: 8 }} data-testid={`deep-research-insight-item-${insight.note_id}`} testID={`deep-research-insight-item-${insight.note_id}`}>
                <Text style={{ color: colors.text, fontWeight: '700', fontSize: 12 }}>{insight.title}</Text>
                <Text style={{ color: colors.text, fontSize: 12, marginTop: 4 }}>{insight.content}</Text>
              </View>
            ))}
          </View>
        </View>
      </ScrollView>
      
      {showUpgradeModal && (
        <View style={{ position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, backgroundColor: 'rgba(0,0,0,0.6)', justifyContent: 'center', alignItems: 'center', zIndex: 1000 }} data-testid="deep-research-upgrade-modal" testID="deep-research-upgrade-modal">
          <View style={{ backgroundColor: colors.card, borderRadius: 16, padding: 20, marginHorizontal: 20, maxWidth: 480, width: '100%', borderWidth: 2, borderColor: colors.primary }}>
            <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
              <Text style={{ fontSize: 18, fontWeight: '800', color: colors.text }}>🚀 Upgrade Required</Text>
              <TouchableOpacity onPress={() => setShowUpgradeModal(false)} data-testid="deep-research-upgrade-modal-close" testID="deep-research-upgrade-modal-close" accessibilityRole="button">
                <FontAwesome5 name="times" size={20} color={colors.textMuted} />
              </TouchableOpacity>
            </View>
            <Text style={{ fontSize: 14, color: colors.text, lineHeight: 22, marginBottom: 16 }}>{upgradeMessage || 'Daily research limit reached. Upgrade for more!'}</Text>
            <View style={{ flexDirection: 'row', gap: 8 }}>
              <TouchableOpacity onPress={() => setShowUpgradeModal(false)} style={{ flex: 1, paddingVertical: 12, borderRadius: 10, backgroundColor: colors.bgSoft, alignItems: 'center', borderWidth: 1, borderColor: colors.border }} data-testid="deep-research-upgrade-modal-cancel" testID="deep-research-upgrade-modal-cancel" accessibilityRole="button">
                <Text style={{ color: colors.text, fontWeight: '700' }}>Maybe Later</Text>
              </TouchableOpacity>
              <TouchableOpacity onPress={() => {
                setShowUpgradeModal(false);
                // Navigate to subscriptions
              }} style={{ flex: 1, paddingVertical: 12, borderRadius: 10, backgroundColor: colors.primary, alignItems: 'center' }} data-testid="deep-research-upgrade-modal-confirm" testID="deep-research-upgrade-modal-confirm" accessibilityRole="button">
                <Text style={{ color: colors.primaryText, fontWeight: '800' }}>Upgrade Now</Text>
              </TouchableOpacity>
            </View>
          </View>
        </View>
      )}
    </View>
  );
}
