import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { View, Text, ScrollView, TouchableOpacity, TextInput, ActivityIndicator, Image } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../src/services/api';
import FeatureLayout from '../../src/components/FeatureLayout';
import { useTheme } from '../../src/context/ThemeContext';
import { useAuth } from '../../src/context/AuthContext';
import FeatureToolbar from '../../src/components/FeatureToolbar';
import AIFeedbackBar from '../../src/components/AIFeedbackBar';
import { useFeatureDraft } from '../../src/hooks/useFeatureDraft';
import { AIFeatureSkeleton } from '../../src/components/SkeletonLoaders';
import { useTranslation } from '../../src/hooks/useTranslation';
import { handleAppRecoverableError } from '../../src/utils/appRecoverableError';

const s = {
  card: { borderRadius: 16, padding: 18, marginHorizontal: 16, marginBottom: 14, borderWidth: 1 },
  title: { fontSize: 16, fontWeight: '700', marginBottom: 12 },
  input: { borderRadius: 12, paddingHorizontal: 14, paddingVertical: 12, fontSize: 14, borderWidth: 1, marginBottom: 14, minHeight: 96, textAlignVertical: 'top' },
  btn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', borderRadius: 14, paddingVertical: 14, gap: 8 },
  result: { fontSize: 14, lineHeight: 22 },
};

const STYLE_OPTIONS = [
  { id: 'cinematic', label: 'Cinematic' },
  { id: 'studio', label: 'Studio' },
  { id: 'editorial', label: 'Editorial' },
  { id: 'illustration', label: 'Illustration' },
];

const QUALITY_OPTIONS = [
  { id: 'standard', label: 'Standard' },
  { id: 'ultra', label: 'Ultra' },
];

type StudioProject = {
  project_id: string;
  title: string;
  brief?: string;
  style_pack?: string;
  quality?: string;
  generation_count?: number;
};

type StudioGeneration = {
  generation_id: string;
  project_id: string;
  prompt: string;
  style_pack: string;
  quality: string;
  image_url?: string;
  created_at: string;
};

type BrandPreset = {
  name: string;
  primary_goal: string;
  audience?: string;
  visual_constraints?: string;
};

export default function AIPhotoScreen() {
  const [input, setInput] = useFeatureDraft('ai-photo');
  const [projectTitle, setProjectTitle] = useState('');
  const [stylePreset, setStylePreset] = useState('cinematic');
  const [qualityPreset, setQualityPreset] = useState('ultra');
  const [projects, setProjects] = useState<StudioProject[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState('');
  const [history, setHistory] = useState<StudioGeneration[]>([]);
  const [activeGeneration, setActiveGeneration] = useState<StudioGeneration | null>(null);
  const [analysisText, setAnalysisText] = useState('');
  const [uiError, setUiError] = useState('');
  const [bootstrapLoading, setBootstrapLoading] = useState(true);
  const [creatingProject, setCreatingProject] = useState(false);
  const [actionInFlight, setActionInFlight] = useState<'generate' | 'analyze' | 'brand' | null>(null);

  const [loading, setLoading] = useState(false);
  const [imgLoading, setImgLoading] = useState(false);
  const [planScope, setPlanScope] = useState('free');
  const [dailyLimit, setDailyLimit] = useState<number | null>(null);
  const [usageCount, setUsageCount] = useState(0);
  const [brandPreset, setBrandPreset] = useState<BrandPreset>({
    name: '',
    primary_goal: '',
    audience: '',
    visual_constraints: '',
  });

  const { colors } = useTheme();
  const { t } = useTranslation();
  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };

  const { user } = useAuth();
  const accent = colors.primary;
  const guestIdRef = useRef(`user_${Math.random().toString(36).slice(2)}${Date.now().toString(36)}`.slice(0, 26));
  const fallbackUserId = useMemo(() => user?.user_id || guestIdRef.current, [user?.user_id]);

  const resolveAbsoluteImageUrl = useCallback((relativeUrl?: string) => {
    if (!relativeUrl) return '';
    if (relativeUrl.startsWith('http') || relativeUrl.startsWith('data:image')) return relativeUrl;
    const base = (api.defaults.baseURL || '').replace(/\/api\/?$/, '');
    return `${base}${relativeUrl}`;
  }, []);

  const hydrateFromBootstrap = useCallback((payload: any) => {
    const nextProjects: StudioProject[] = Array.isArray(payload?.projects) ? payload.projects : [];
    const nextHistory: StudioGeneration[] = Array.isArray(payload?.recent_generations) ? payload.recent_generations : [];
    setProjects(nextProjects);
    setHistory(nextHistory as StudioGeneration[]);
    setSelectedProjectId((current) => current || nextProjects[0]?.project_id || '');
    setPlanScope(payload?.plan || 'free');
    setDailyLimit(typeof payload?.limits?.generations_per_day === 'number' ? payload.limits.generations_per_day : null);
    const usage = payload?.usage || {};
    setUsageCount(typeof usage.generations === 'number' ? usage.generations : 0);
    const preset = payload?.brand_preset || {};
    setBrandPreset({
      name: preset.name || '',
      primary_goal: preset.primary_goal || '',
      audience: preset.audience || '',
      visual_constraints: preset.visual_constraints || '',
    });
    if (nextHistory.length > 0) {
      const latest = { ...nextHistory[0], image_url: resolveAbsoluteImageUrl(nextHistory[0].image_url) };
      setActiveGeneration(latest as StudioGeneration);
    }
  }, [resolveAbsoluteImageUrl]);

  const fetchBootstrap = useCallback(async () => {
    setBootstrapLoading(true);
    setUiError('');
    try {
      const res = await api.get('/ai-photo-studio/bootstrap', { params: { fallback_user_id: fallbackUserId } });
      hydrateFromBootstrap(res.data);
    } catch (error) {
      handleAppRecoverableError({
        scope: 'app/features/ai-photo.tsx#bootstrap',
        error,
        message: tx('aiPhoto.alerts.bootstrapFailed', 'Failed to load studio workspace. Please retry.'),
        notifyMode: 'dialog',
        userInitiated: true,
        setError: setUiError,
        onRetry: () => { void fetchBootstrap(); },
      });
    } finally {
      setBootstrapLoading(false);
    }
  }, [fallbackUserId, hydrateFromBootstrap, tx]);

  const loadHistory = useCallback(async (projectId: string) => {
    if (!projectId) return;
    const res = await api.get('/ai-photo-studio/history', {
      params: { fallback_user_id: fallbackUserId, project_id: projectId, limit: 24, offset: 0 },
    });
    const nextHistory = (res.data?.history || []).map((item: StudioGeneration) => ({
      ...item,
      image_url: resolveAbsoluteImageUrl(item.image_url),
    }));
    setHistory(nextHistory);
    if (nextHistory.length > 0) {
      setActiveGeneration(nextHistory[0]);
    }
  }, [fallbackUserId, resolveAbsoluteImageUrl]);

  useEffect(() => {
    void fetchBootstrap();
  }, [fetchBootstrap]);

  const createProject = async () => {
    const title = projectTitle.trim();
    if (!title) {
      handleAppRecoverableError({
        scope: 'app/features/ai-photo.tsx#create-project-validation',
        message: tx('aiPhoto.alerts.projectTitleRequired', 'Please enter a project title.'),
        notifyMode: 'dialog',
        userInitiated: true,
      });
      return;
    }
    setCreatingProject(true);
    setUiError('');
    try {
      const res = await api.post('/ai-photo-studio/projects/create', {
        title,
        brief: input,
        style_pack: stylePreset,
        quality: qualityPreset,
        fallback_user_id: fallbackUserId,
      });
      const project = res.data?.project as StudioProject;
      if (project?.project_id) {
        setProjects((prev) => [project, ...prev.filter((item) => item.project_id !== project.project_id)]);
        setSelectedProjectId(project.project_id);
        setProjectTitle('');
        await loadHistory(project.project_id);
      }
      setPlanScope(res.data?.plan || planScope);
    } catch (error) {
      handleAppRecoverableError({
        scope: 'app/features/ai-photo.tsx#create-project',
        error,
        message: tx('aiPhoto.alerts.projectCreateFailed', 'Failed to create project. Please retry.'),
        notifyMode: 'dialog',
        userInitiated: true,
        setError: setUiError,
        onRetry: () => { void createProject(); },
      });
    } finally {
      setCreatingProject(false);
    }
  };

  const ensureProjectReady = async () => {
    if (selectedProjectId) return selectedProjectId;
    const autoTitle = `Visual Sprint ${new Date().toLocaleDateString()}`;
    const res = await api.post('/ai-photo-studio/projects/create', {
      title: autoTitle,
      brief: input,
      style_pack: stylePreset,
      quality: qualityPreset,
      fallback_user_id: fallbackUserId,
    });
    const project = res.data?.project as StudioProject;
    if (!project?.project_id) {
      throw new Error('Project creation failed');
    }
    setProjects((prev) => [project, ...prev]);
    setSelectedProjectId(project.project_id);
    return project.project_id;
  };

  const handleAnalyze = async () => {
    if (!input.trim()) {
      handleAppRecoverableError({
        scope: 'app/features/ai-photo.tsx#analyze-validation',
        message: tx('aiPhoto.alerts.describeRequest', 'Please describe what you want analyzed.'),
        notifyMode: 'dialog',
        userInitiated: true,
      });
      return;
    }
    setActionInFlight('analyze');
    setUiError('');
    setAnalysisText('');
    setLoading(true);
    try {
      const projectId = await ensureProjectReady();
      const res = await api.post(`/ai-photo-studio/projects/${projectId}/analyze`, {
        prompt: input,
        fallback_user_id: fallbackUserId,
      });
      setAnalysisText(res.data.analysis || tx('aiPhoto.alerts.emptyAnalysis', 'No analysis response received.'));
      setPlanScope(res.data.plan || 'free');
      setDailyLimit(typeof res.data.daily_limit === 'number' ? res.data.daily_limit : dailyLimit);
      const usage = res.data.usage || {};
      setUsageCount(typeof usage.analyses === 'number' ? usage.analyses : usageCount);
    } catch (error) {
      handleAppRecoverableError({
        scope: 'app/features/ai-photo.tsx#analyze',
        error,
        message: tx('aiPhoto.alerts.analyzeFailed', 'Image strategy analysis failed. Please retry.'),
        notifyMode: 'dialog',
        userInitiated: true,
        setError: setUiError,
        onRetry: () => { void handleAnalyze(); },
      });
    } finally {
      setActionInFlight(null);
      setLoading(false);
    }
  };

  const handleGenerateImage = async () => {
    if (!input.trim()) {
      handleAppRecoverableError({
        scope: 'app/features/ai-photo.tsx#generate-validation',
        message: tx('aiPhoto.alerts.describeImage', 'Please describe the image you want to create.'),
        notifyMode: 'dialog',
        userInitiated: true,
      });
      return;
    }

    setActionInFlight('generate');
    setUiError('');
    setImgLoading(true);
    try {
      const projectId = await ensureProjectReady();
      const res = await api.post(`/ai-photo-studio/projects/${projectId}/generate`, {
        prompt: input,
        style_pack: stylePreset,
        quality: qualityPreset,
        fallback_user_id: fallbackUserId,
        idempotency_key: `${projectId}-${Date.now()}`,
      }, { timeout: 70000 });

      const generation = res.data?.generation;
      if (generation?.generation_id) {
        const hydratedGeneration = {
          ...generation,
          image_url: resolveAbsoluteImageUrl(generation.image_url),
        } as StudioGeneration;
        setActiveGeneration(hydratedGeneration);
        setHistory((prev) => [hydratedGeneration, ...prev.filter((item) => item.generation_id !== hydratedGeneration.generation_id)].slice(0, 24));
        await loadHistory(projectId);
      }

      setPlanScope(res.data.plan || 'free');
      setDailyLimit(typeof res.data.daily_limit === 'number' ? res.data.daily_limit : dailyLimit);
      const usage = res.data.usage || {};
      setUsageCount(typeof usage.generations === 'number' ? usage.generations : usageCount);
    } catch (error) {
      handleAppRecoverableError({
        scope: 'app/features/ai-photo.tsx#generate',
        error,
        message: tx('aiPhoto.alerts.generateFailed', 'Image generation failed. Please try a different prompt.'),
        notifyMode: 'dialog',
        userInitiated: true,
        setError: setUiError,
        onRetry: () => { void handleGenerateImage(); },
      });
    } finally {
      setActionInFlight(null);
      setImgLoading(false);
    }
  };

  const handleSaveBrandPreset = async () => {
    if (!brandPreset.name.trim() || !brandPreset.primary_goal.trim()) {
      handleAppRecoverableError({
        scope: 'app/features/ai-photo.tsx#brand-validation',
        message: tx('aiPhoto.alerts.brandRequired', 'Brand preset name and objective are required.'),
        notifyMode: 'dialog',
        userInitiated: true,
      });
      return;
    }
    setActionInFlight('brand');
    setUiError('');
    try {
      await api.put('/ai-photo-studio/brand-preset', {
        ...brandPreset,
        fallback_user_id: fallbackUserId,
      });
    } catch (error) {
      handleAppRecoverableError({
        scope: 'app/features/ai-photo.tsx#save-brand',
        error,
        message: tx('aiPhoto.alerts.brandSaveFailed', 'Failed to save brand preset. Please retry.'),
        notifyMode: 'dialog',
        userInitiated: true,
        setError: setUiError,
        onRetry: () => { void handleSaveBrandPreset(); },
      });
    } finally {
      setActionInFlight(null);
    }
  };

  const remixFromGeneration = async (generation: StudioGeneration) => {
    setInput(generation.prompt);
    setStylePreset(generation.style_pack || stylePreset);
    setQualityPreset(generation.quality || qualityPreset);
    setSelectedProjectId(generation.project_id || selectedProjectId);
    await handleGenerateImage();
  };

  const planScopeLabel = planScope === 'premium'
    ? 'Full unlimited access'
    : planScope === 'basic'
      ? 'Almost unlimited access'
      : 'Limited access';

  const selectedProject = projects.find((item) => item.project_id === selectedProjectId);

  if (bootstrapLoading) {
    return (
      <FeatureLayout
        feature="ai-photo"
        title={tx('aiPhoto.page.title', 'Image & Design Studio')}
        subtitle={tx('aiPhoto.page.subtitle', 'Enterprise visual workspace with projects, remix history, and plan-aware limits')}
        icon="image"
        color={accent}
        showSecondaryTabs={false}
      >
        <AIFeatureSkeleton />
      </FeatureLayout>
    );
  }

  return (
    <FeatureLayout
      feature="ai-photo"
      title={tx('aiPhoto.page.title', 'Image & Design Studio')}
      subtitle={tx('aiPhoto.page.subtitle', 'Enterprise visual workspace with projects, remix history, and plan-aware limits')}
      icon="image"
      color={accent}
      showSecondaryTabs={false}
    >
      <View style={{ paddingHorizontal: 16, marginTop: 10 }}>
        <View style={[s.card, { backgroundColor: colors.card, borderColor: colors.border, marginHorizontal: 0, marginBottom: 0 }]} data-testid="ai-photo-plan-scope-card" testID="ai-photo-plan-scope-card">
          <Text style={[s.title, { color: colors.text, marginBottom: 6 }]} data-testid="ai-photo-plan-scope-value" testID="ai-photo-plan-scope-value">{planScopeLabel} • {tx('aiPhoto.metrics.workspace', 'Workspace Active')}</Text>
          <Text style={{ color: colors.textSec, fontSize: 12 }} data-testid="ai-photo-plan-scope-limit" testID="ai-photo-plan-scope-limit">
            {dailyLimit === null || dailyLimit < 0 ? 'Daily render capacity: Unlimited' : `Daily render limit: ${dailyLimit}`}
          </Text>
          <Text style={{ color: colors.textMuted, fontSize: 12, marginTop: 6 }} data-testid="ai-photo-plan-scope-usage" testID="ai-photo-plan-scope-usage">
            {tx('aiPhoto.metrics.generatedToday', 'Generated today')}: {usageCount}
          </Text>
          {uiError ? (
            <Text style={{ color: colors.error, fontSize: 12, marginTop: 8 }} data-testid="ai-photo-ui-error" testID="ai-photo-ui-error">{uiError}</Text>
          ) : null}
        </View>
      </View>

      <ScrollView contentContainerStyle={{ paddingVertical: 16 }}>
        <View style={[s.card, { backgroundColor: colors.card, borderColor: colors.border }]}>
          <Text style={[s.title, { color: colors.text }]} data-testid="ai-photo-projects-title" testID="ai-photo-projects-title">{tx('aiPhoto.projects.title', 'Project Workspace')}</Text>
          <View style={{ flexDirection: 'row', gap: 8, marginBottom: 10 }}>
            <TextInput
              style={[s.input, { flex: 1, minHeight: 46, marginBottom: 0, backgroundColor: colors.bgSoft, borderColor: colors.border, color: colors.text }]}
              value={projectTitle}
              onChangeText={setProjectTitle}
              placeholder={tx('aiPhoto.projects.placeholder', 'Create a new project name (e.g., Summer Campaign Hero)')}
              placeholderTextColor={colors.textMuted}
              data-testid="ai-photo-project-title-input"
              testID="ai-photo-project-title-input"
            />
            <TouchableOpacity
              style={[s.btn, { paddingHorizontal: 14, backgroundColor: colors.accent }]}
              onPress={createProject}
              disabled={creatingProject}
              data-testid="ai-photo-create-project-button"
              testID="ai-photo-create-project-button"
              accessibilityRole="button"
            >
              {creatingProject ? <ActivityIndicator color={colors.primaryText} /> : <Ionicons name="add-circle" size={18} color={colors.primaryText} />}
            </TouchableOpacity>
          </View>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} data-testid="ai-photo-project-list" testID="ai-photo-project-list">
            <View style={{ flexDirection: 'row', gap: 8 }}>
              {projects.map((project) => {
                const selected = selectedProjectId === project.project_id;
                return (
                  <TouchableOpacity
                    key={project.project_id}
                    onPress={() => {
                      setSelectedProjectId(project.project_id);
                      void loadHistory(project.project_id);
                    }}
                    style={{
                      paddingHorizontal: 12,
                      paddingVertical: 9,
                      borderRadius: 12,
                      backgroundColor: selected ? colors.primarySoft : colors.bgSoft,
                      borderWidth: 1,
                      borderColor: selected ? colors.primary : colors.border,
                    }}
                    data-testid={`ai-photo-project-chip-${project.project_id}`}
                    testID={`ai-photo-project-chip-${project.project_id}`}
                    accessibilityRole="button"
                  >
                    <Text style={{ color: selected ? colors.primary : colors.text, fontSize: 12, fontWeight: '700' }}>{project.title}</Text>
                    <Text style={{ color: colors.textMuted, fontSize: 10, marginTop: 2 }}>
                      {tx('aiPhoto.projects.renders', 'Renders')}: {project.generation_count || 0}
                    </Text>
                  </TouchableOpacity>
                );
              })}
            </View>
          </ScrollView>
        </View>

        <View style={[s.card, { backgroundColor: colors.card, borderColor: colors.border }]}>
            <Text style={[s.title, { color: colors.text }]} data-testid="ai-photo-prompt-title" testID="ai-photo-prompt-title">{tx('aiPhoto.editor.prompt', 'Describe Your Visual Goal')}</Text>
            <TextInput
              style={[s.input, { backgroundColor: colors.bgSoft, borderColor: colors.border, color: colors.text }]}
              multiline
              placeholder={tx('aiPhoto.editor.placeholder', 'E.g. SaaS hero image with modern gradients, clean typography-safe composition, premium lighting...')}
              placeholderTextColor={colors.textMuted}
              value={input}
              onChangeText={setInput}
              data-testid="ai-photo-prompt-input" testID="ai-photo-prompt-input"
            />

            <Text style={{ color: colors.textMuted, marginBottom: 8, fontSize: 12 }} data-testid="ai-photo-selected-project" testID="ai-photo-selected-project">
              {tx('aiPhoto.projects.activeProject', 'Active Project')}: {selectedProject?.title || tx('aiPhoto.projects.none', 'Auto-create on first generation')}
            </Text>

            <Text style={[s.title, { color: colors.text, fontSize: 13, marginBottom: 8 }]}>{tx('aiPhoto.editor.style', 'Style Pack')}</Text>
            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginBottom: 12 }} data-testid="ai-photo-style-options" testID="ai-photo-style-options">
              {STYLE_OPTIONS.map((option) => {
                const active = stylePreset === option.id;
                return (
                  <TouchableOpacity
                    key={option.id}
                    style={{
                      paddingHorizontal: 12,
                      paddingVertical: 8,
                      borderRadius: 12,
                      backgroundColor: active ? accent : colors.bgSoft,
                      borderWidth: 1,
                      borderColor: active ? accent : colors.border,
                    }}
                    onPress={() => setStylePreset(option.id)}
                    data-testid={`ai-photo-style-${option.id}`} testID={`ai-photo-style-${option.id}`}
                    accessibilityRole="button"
                  >
                    <Text style={{ fontSize: 12, fontWeight: '700', color: active ? colors.primaryText : colors.textMuted }}>{option.label}</Text>
                  </TouchableOpacity>
                );
              })}
            </View>

            <Text style={[s.title, { color: colors.text, fontSize: 13, marginBottom: 8 }]}>{tx('aiPhoto.editor.quality', 'Render Quality')}</Text>
            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginBottom: 14 }} data-testid="ai-photo-quality-options" testID="ai-photo-quality-options">
              {QUALITY_OPTIONS.map((option) => {
                const active = qualityPreset === option.id;
                return (
                  <TouchableOpacity
                    key={option.id}
                    style={{
                      paddingHorizontal: 12,
                      paddingVertical: 8,
                      borderRadius: 12,
                      backgroundColor: active ? colors.info : colors.bgSoft,
                      borderWidth: 1,
                      borderColor: active ? colors.info : colors.border,
                    }}
                    onPress={() => setQualityPreset(option.id)}
                    data-testid={`ai-photo-quality-${option.id}`} testID={`ai-photo-quality-${option.id}`}
                    accessibilityRole="button"
                  >
                    <Text style={{ fontSize: 12, fontWeight: '700', color: active ? colors.primaryText : colors.textMuted }}>{option.label}</Text>
                  </TouchableOpacity>
                );
              })}
            </View>
            <View style={{ flexDirection: 'row', gap: 10 }}>
              <TouchableOpacity
                style={[s.btn, { backgroundColor: accent, flex: 1 }]}
                onPress={handleGenerateImage}
                disabled={imgLoading}
                data-testid="ai-photo-generate-button" testID="ai-photo-generate-button"
                accessibilityRole="button"
              >
                {imgLoading ? <ActivityIndicator color={colors.primaryText} /> : <><Ionicons name="color-palette" size={18} color={colors.primaryText} /><Text style={{ color: colors.primaryText, fontWeight: '700' }}>{tx('aiPhoto.actions.generate', 'Generate Image')}</Text></>}
              </TouchableOpacity>
              <TouchableOpacity
                style={[s.btn, { backgroundColor: colors.accent, flex: 1 }]}
                onPress={handleAnalyze}
                disabled={loading}
                data-testid="ai-photo-analyze-button" testID="ai-photo-analyze-button"
                accessibilityRole="button"
              >
                {loading ? <ActivityIndicator color={colors.primaryText} /> : <><Ionicons name="chatbubble" size={18} color={colors.primaryText} /><Text style={{ color: colors.primaryText, fontWeight: '700' }}>{tx('aiPhoto.actions.analyze', 'AI Analysis')}</Text></>}
              </TouchableOpacity>
            </View>

            {actionInFlight ? (
              <Text style={{ color: colors.textMuted, marginTop: 8, fontSize: 11 }} data-testid="ai-photo-action-status" testID="ai-photo-action-status">
                {tx('aiPhoto.actions.processing', 'Processing')} {actionInFlight}...
              </Text>
            ) : null}
          </View>

          {imgLoading ? <AIFeatureSkeleton /> : null}

          {activeGeneration?.image_url ? (
            <View style={[s.card, { backgroundColor: colors.card, borderColor: colors.border }]} testID="generated-image-wrapper" data-testid="generated-image-wrapper">
              <Text style={[s.title, { color: colors.text }]} data-testid="ai-photo-latest-render-title" testID="ai-photo-latest-render-title">{tx('aiPhoto.results.latestRender', 'Latest Render')}</Text>
              <Image
                source={{ uri: activeGeneration.image_url }}
                style={{ width: '100%', height: 300, borderRadius: 12, backgroundColor: colors.bgSoft }}
                resizeMode="contain"
                accessibilityLabel="generated-image"
                data-testid="generated-image" testID="generated-image"
              />
              <Text style={{ color: colors.textMuted, fontSize: 12, marginTop: 8 }} data-testid="ai-photo-active-prompt" testID="ai-photo-active-prompt">
                {activeGeneration.prompt}
              </Text>
              <View style={{ flexDirection: 'row', gap: 8, marginTop: 10 }}>
                <TouchableOpacity
                  style={[s.btn, { flex: 1, backgroundColor: colors.info }]}
                  onPress={() => { void remixFromGeneration(activeGeneration); }}
                  data-testid="ai-photo-remix-latest-button"
                  testID="ai-photo-remix-latest-button"
                  accessibilityRole="button"
                >
                  <Ionicons name="refresh" size={16} color={colors.primaryText} />
                  <Text style={{ color: colors.primaryText, fontWeight: '700', fontSize: 12 }}>{tx('aiPhoto.actions.remix', 'Remix')}</Text>
                </TouchableOpacity>
              </View>
              <FeatureToolbar content={activeGeneration.image_url} featureKey="ai-photo" title="Generated Image" showShare={true} />
              <AIFeedbackBar feature="ai-photo" response={analysisText} />
            </View>
          ) : null}

          {analysisText ? (
            <View style={[s.card, { backgroundColor: colors.card, borderColor: colors.border }]}>
              <Text style={[s.title, { color: colors.text }]} data-testid="ai-photo-analysis-title" testID="ai-photo-analysis-title">{tx('aiPhoto.analysis.title', 'AI Analysis')}</Text>
              <Text style={[s.result, { color: colors.textSec }]} data-testid="ai-photo-analysis-result" testID="ai-photo-analysis-result">{analysisText}</Text>
            </View>
          ) : null}

          <View style={[s.card, { backgroundColor: colors.card, borderColor: colors.border }]} data-testid="ai-photo-history-card" testID="ai-photo-history-card">
            <Text style={[s.title, { color: colors.text }]}>{tx('aiPhoto.history.title', 'Generation History')}</Text>
            <ScrollView horizontal showsHorizontalScrollIndicator={false} data-testid="ai-photo-history-list" testID="ai-photo-history-list">
              <View style={{ flexDirection: 'row', gap: 12 }}>
                {history.map((item) => (
                  <TouchableOpacity
                    key={item.generation_id}
                    style={{ width: 170, borderRadius: 12, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bgSoft, padding: 8 }}
                    onPress={() => setActiveGeneration(item)}
                    data-testid={`ai-photo-history-item-${item.generation_id}`}
                    testID={`ai-photo-history-item-${item.generation_id}`}
                    accessibilityRole="button"
                  >
                    <Image
                      source={{ uri: item.image_url }}
                      style={{ width: '100%', height: 95, borderRadius: 8, backgroundColor: colors.card }}
                      resizeMode="cover"
                      data-testid={`ai-photo-history-image-${item.generation_id}`}
                      testID={`ai-photo-history-image-${item.generation_id}`}
                    />
                    <Text style={{ color: colors.text, fontSize: 11, marginTop: 7 }} numberOfLines={2}>{item.prompt}</Text>
                    <Text style={{ color: colors.textMuted, fontSize: 10, marginTop: 4 }}>{item.style_pack} • {item.quality}</Text>
                  </TouchableOpacity>
                ))}
              </View>
            </ScrollView>
          </View>

          <View style={[s.card, { backgroundColor: colors.card, borderColor: colors.border }]} data-testid="ai-photo-brand-card" testID="ai-photo-brand-card">
            <Text style={[s.title, { color: colors.text }]}>{tx('aiPhoto.brand.title', 'Brand Preset')}</Text>
            <TextInput
              style={[s.input, { minHeight: 46, backgroundColor: colors.bgSoft, borderColor: colors.border, color: colors.text }]}
              value={brandPreset.name}
              onChangeText={(value) => setBrandPreset((prev) => ({ ...prev, name: value }))}
              placeholder={tx('aiPhoto.brand.name', 'Preset name (e.g., Clean B2B Launch)')}
              placeholderTextColor={colors.textMuted}
              data-testid="ai-photo-brand-name"
              testID="ai-photo-brand-name"
            />
            <TextInput
              style={[s.input, { minHeight: 58, backgroundColor: colors.bgSoft, borderColor: colors.border, color: colors.text }]}
              value={brandPreset.primary_goal}
              onChangeText={(value) => setBrandPreset((prev) => ({ ...prev, primary_goal: value }))}
              placeholder={tx('aiPhoto.brand.goal', 'Primary objective (conversion, trust, retention, etc.)')}
              placeholderTextColor={colors.textMuted}
              data-testid="ai-photo-brand-goal"
              testID="ai-photo-brand-goal"
            />
            <TextInput
              style={[s.input, { minHeight: 46, backgroundColor: colors.bgSoft, borderColor: colors.border, color: colors.text }]}
              value={brandPreset.audience}
              onChangeText={(value) => setBrandPreset((prev) => ({ ...prev, audience: value }))}
              placeholder={tx('aiPhoto.brand.audience', 'Audience (optional)')}
              placeholderTextColor={colors.textMuted}
              data-testid="ai-photo-brand-audience"
              testID="ai-photo-brand-audience"
            />
            <TextInput
              style={[s.input, { minHeight: 70, backgroundColor: colors.bgSoft, borderColor: colors.border, color: colors.text }]}
              value={brandPreset.visual_constraints}
              onChangeText={(value) => setBrandPreset((prev) => ({ ...prev, visual_constraints: value }))}
              placeholder={tx('aiPhoto.brand.constraints', 'Visual constraints, no-go styles, or compliance notes')}
              placeholderTextColor={colors.textMuted}
              multiline
              data-testid="ai-photo-brand-constraints"
              testID="ai-photo-brand-constraints"
            />
            <TouchableOpacity
              style={[s.btn, { backgroundColor: colors.primary }]}
              onPress={handleSaveBrandPreset}
              disabled={actionInFlight === 'brand'}
              data-testid="ai-photo-brand-save-button"
              testID="ai-photo-brand-save-button"
              accessibilityRole="button"
            >
              {actionInFlight === 'brand' ? <ActivityIndicator color={colors.primaryText} /> : <><Ionicons name="save" size={16} color={colors.primaryText} /><Text style={{ color: colors.primaryText, fontWeight: '700' }}>{tx('aiPhoto.brand.save', 'Save Brand Preset')}</Text></>}
            </TouchableOpacity>
          </View>

      </ScrollView>
    </FeatureLayout>
  );
}
