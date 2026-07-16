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

type SpeechProject = {
  project_id: string;
  title: string;
  brief?: string | null;
  objective?: string;
  analysis_count?: number;
  last_analysis?: string | null;
  last_analysis_at?: string | null;
};

type SpeechHistoryItem = {
  analysis_id: string;
  project_id: string;
  prompt: string;
  analysis: string;
  created_at: string;
};

type VoicePreset = {
  preset_id: string;
  voice: string;
  style_notes?: string | null;
  language?: string;
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
    marginBottom: 14,
    minHeight: 46,
  },
  textArea: {
    borderRadius: 12,
    paddingHorizontal: 14,
    paddingVertical: 12,
    fontSize: 14,
    borderWidth: 1,
    marginBottom: 14,
    minHeight: 100,
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

export default function AISpeechScreen() {
  const { t } = useTranslation();
  t('i18n.route.features.ai-speech.probe');
  const [analysisPrompt, setAnalysisPrompt] = useFeatureDraft('ai-speech');
  const [projectTitle, setProjectTitle] = useState('');
  const [projectBrief, setProjectBrief] = useState('');
  const [projects, setProjects] = useState<SpeechProject[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState('');
  const [history, setHistory] = useState<SpeechHistoryItem[]>([]);
  const [analysisResult, setAnalysisResult] = useState('');
  const [transcribeText, setTranscribeText] = useState('');
  const [synthesisText, setSynthesisText] = useState('');
  const [selectedVoice, setSelectedVoice] = useState('alloy');
  const [voicePresets, setVoicePresets] = useState<VoicePreset[]>([]);
  const [presetNotes, setPresetNotes] = useState('');
  const [presetLanguage, setPresetLanguage] = useState('en');
  const [lastAudioUrl, setLastAudioUrl] = useState('');
  const [lastExportPreview, setLastExportPreview] = useState('');
  const [plan, setPlan] = useState('free');
  const [scopeLabel, setScopeLabel] = useState('Limited access');
  const [limits, setLimits] = useState<Record<string, number>>({});
  const [usage, setUsage] = useState({ projects_this_month: 0, analyses_today: 0, transcriptions_today: 0, synthesis_today: 0 });
  const [bootstrapLoading, setBootstrapLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState<'create' | 'analyze' | 'transcribe' | 'synthesize' | 'preset' | 'export' | null>(null);
  const [uiError, setUiError] = useState('');

  const { user } = useAuth();
  const { colors } = useTheme();

  const guestIdRef = useRef(generateGuestId());
  const fallbackUserId = useMemo(() => user?.user_id || guestIdRef.current, [user?.user_id]);
  const selectedProject = projects.find((item) => item.project_id === selectedProjectId) || null;
  const accent = colors.primary;

  const loadHistory = useCallback(async (projectId: string) => {
    if (!projectId) return;
    const res = await api.get('/ai-speech-studio/history', {
      params: {
        fallback_user_id: fallbackUserId,
        project_id: projectId,
        limit: 30,
        offset: 0,
      },
    });
    const items: SpeechHistoryItem[] = Array.isArray(res.data?.history) ? res.data.history : [];
    setHistory(items);
    if (items[0]?.analysis) {
      setAnalysisResult(items[0].analysis);
    }
  }, [fallbackUserId]);

  const loadBootstrap = useCallback(async () => {
    setBootstrapLoading(true);
    setUiError('');
    try {
      const res = await api.get('/ai-speech-studio/bootstrap', {
        params: { fallback_user_id: fallbackUserId },
      });

      const nextProjects: SpeechProject[] = Array.isArray(res.data?.projects) ? res.data.projects : [];
      setProjects(nextProjects);
      setSelectedProjectId((prev) => prev || nextProjects[0]?.project_id || '');
      setHistory(Array.isArray(res.data?.recent_history) ? res.data.recent_history : []);
      setPlan(res.data?.plan || 'free');
      setScopeLabel(res.data?.scope_label || 'Limited access');
      setLimits(res.data?.limits || {});
      setUsage({
        projects_this_month: Number(res.data?.usage?.projects_this_month || 0),
        analyses_today: Number(res.data?.usage?.analyses_today || 0),
        transcriptions_today: Number(res.data?.usage?.transcriptions_today || 0),
        synthesis_today: Number(res.data?.usage?.synthesis_today || 0),
      });
    } catch (error: any) {
      setUiError(error?.response?.data?.detail?.message || 'Failed to load Voice Studio workspace.');
    } finally {
      setBootstrapLoading(false);
    }
  }, [fallbackUserId]);

  const loadVoicePresets = useCallback(async () => {
    try {
      const res = await api.get('/ai-speech-studio/voice-preset', { params: { fallback_user_id: fallbackUserId } });
      const rows = Array.isArray(res.data?.presets) ? res.data.presets : [];
      setVoicePresets(rows);
      if (rows[0]?.voice) {
        setSelectedVoice(rows[0].voice);
        setPresetNotes(rows[0].style_notes || '');
        setPresetLanguage(rows[0].language || 'en');
      }
    } catch {
      // non-blocking for main workspace
    }
  }, [fallbackUserId]);

  useEffect(() => {
    void loadBootstrap();
    void loadVoicePresets();
  }, [loadBootstrap, loadVoicePresets]);

  useEffect(() => {
    if (selectedProjectId) {
      void loadHistory(selectedProjectId);
    }
  }, [selectedProjectId, loadHistory]);

  const createProject = async () => {
    const title = projectTitle.trim();
    if (!title) {
      setUiError('Project title is required.');
      return;
    }
    setActionLoading('create');
    setUiError('');
    try {
      const res = await api.post('/ai-speech-studio/projects/create', {
        title,
        brief: projectBrief.trim() || undefined,
        objective: 'presentation',
        fallback_user_id: fallbackUserId,
      });
      const project: SpeechProject | undefined = res.data?.project;
      if (project?.project_id) {
        setProjects((prev) => [project, ...prev.filter((item) => item.project_id !== project.project_id)]);
        setSelectedProjectId(project.project_id);
        setProjectTitle('');
        setProjectBrief('');
      }
      setPlan(res.data?.plan || plan);
      setScopeLabel(res.data?.scope_label || scopeLabel);
      setLimits(res.data?.limits || limits);
      await loadBootstrap();
    } catch (error: any) {
      setUiError(error?.response?.data?.detail?.message || 'Project creation failed.');
    } finally {
      setActionLoading(null);
    }
  };

  const ensureProjectReady = async () => {
    if (selectedProjectId) return selectedProjectId;
    const res = await api.post('/ai-speech-studio/projects/create', {
      title: `Voice Sprint ${new Date().toLocaleDateString()}`,
      brief: projectBrief.trim() || undefined,
      objective: 'presentation',
      fallback_user_id: fallbackUserId,
    });
    const project: SpeechProject | undefined = res.data?.project;
    if (!project?.project_id) {
      throw new Error('Project create failed');
    }
    setProjects((prev) => [project, ...prev]);
    setSelectedProjectId(project.project_id);
    return project.project_id;
  };

  const analyzeSpeech = async () => {
    const prompt = analysisPrompt.trim();
    if (!prompt) {
      setUiError('Please enter speech context before analysis.');
      return;
    }
    setActionLoading('analyze');
    setUiError('');
    setAnalysisResult('');
    try {
      const projectId = await ensureProjectReady();
      const res = await api.post(`/ai-speech-studio/projects/${projectId}/analyze`, {
        prompt,
        target: 'project',
        fallback_user_id: fallbackUserId,
      });
      setAnalysisResult(res.data?.analysis || 'No analysis generated.');
      setPlan(res.data?.plan || plan);
      setScopeLabel(res.data?.scope_label || scopeLabel);
      setUsage((prev) => ({
        ...prev,
        analyses_today: Number(res.data?.usage?.analyses_today ?? prev.analyses_today),
      }));
      await loadHistory(projectId);
      await loadBootstrap();
    } catch (error: any) {
      setUiError(error?.response?.data?.detail?.message || 'Voice analysis failed.');
    } finally {
      setActionLoading(null);
    }
  };

  const transcribeSpeech = async () => {
    setActionLoading('transcribe');
    setUiError('');
    try {
      const projectId = await ensureProjectReady();
      const text = analysisPrompt.trim() || 'Voice Studio transcription probe sample for enterprise workflow verification.';
      const blob = new Blob([text], { type: 'audio/webm' });
      const formData = new FormData();
      formData.append('audio', blob, 'speech.webm');
      const idempotencyKey = `transcribe-${Date.now()}`;
      const res = await api.post(
        `/ai-speech-studio/projects/${projectId}/transcribe?fallback_user_id=${encodeURIComponent(fallbackUserId)}&idempotency_key=${encodeURIComponent(idempotencyKey)}`,
        formData,
      );
      setTranscribeText(res.data?.transcript || '');
      setUsage((prev) => ({ ...prev, transcriptions_today: Number(res.data?.usage?.transcriptions_today ?? prev.transcriptions_today) }));
    } catch (error: any) {
      setUiError(error?.response?.data?.detail?.message || 'Transcription failed.');
    } finally {
      setActionLoading(null);
      await loadBootstrap();
    }
  };

  const synthesizeSpeech = async () => {
    const text = synthesisText.trim() || transcribeText.trim() || analysisPrompt.trim();
    if (!text) {
      setUiError('Provide text for speech synthesis.');
      return;
    }
    setActionLoading('synthesize');
    setUiError('');
    try {
      const projectId = await ensureProjectReady();
      const res = await api.post(`/ai-speech-studio/projects/${projectId}/synthesize`, {
        text,
        voice: selectedVoice,
        format: 'mp3',
        idempotency_key: `synthesize-${Date.now()}`,
        fallback_user_id: fallbackUserId,
      });
      setLastAudioUrl(res.data?.audio_url || '');
      setUsage((prev) => ({ ...prev, synthesis_today: Number(res.data?.usage?.synthesis_today ?? prev.synthesis_today) }));
    } catch (error: any) {
      setUiError(error?.response?.data?.detail?.message || 'Synthesis failed.');
    } finally {
      setActionLoading(null);
      await loadBootstrap();
    }
  };

  const saveVoicePreset = async () => {
    setActionLoading('preset');
    setUiError('');
    try {
      await api.put('/ai-speech-studio/voice-preset', {
        voice: selectedVoice,
        style_notes: presetNotes,
        language: presetLanguage,
        fallback_user_id: fallbackUserId,
      });
      await loadVoicePresets();
    } catch (error: any) {
      setUiError(error?.response?.data?.detail?.message || 'Failed to save voice preset.');
    } finally {
      setActionLoading(null);
    }
  };

  const exportProjectData = async () => {
    setActionLoading('export');
    setUiError('');
    try {
      const projectId = await ensureProjectReady();
      const res = await api.get(`/ai-speech-studio/projects/${projectId}/exports`, {
        params: {
          fallback_user_id: fallbackUserId,
          include_analysis: true,
          include_transcripts: true,
          include_synthesis: true,
          limit: 10,
        },
      });
      const analysisCount = Array.isArray(res.data?.analyses) ? res.data.analyses.length : 0;
      const transcriptCount = Array.isArray(res.data?.transcripts) ? res.data.transcripts.length : 0;
      const synthesisCount = Array.isArray(res.data?.synthesis) ? res.data.synthesis.length : 0;
      setLastExportPreview(`Export ready • analyses: ${analysisCount}, transcripts: ${transcriptCount}, synthesis: ${synthesisCount}`);
    } catch (error: any) {
      setUiError(error?.response?.data?.detail?.message || 'Export failed.');
    } finally {
      setActionLoading(null);
    }
  };

  if (bootstrapLoading) {
    return (
      <FeatureLayout
        feature="ai-speech"
        title="Voice Studio"
        subtitle="Project-based speech coaching workspace with subscription-tier controls"
        icon="mic-circle"
        color={accent}
        showSecondaryTabs={false}
      >
        <AIFeatureSkeleton />
      </FeatureLayout>
    );
  }

  return (
    <FeatureLayout
      feature="ai-speech"
      title="Voice Studio"
      subtitle="Project-based speech coaching workspace with subscription-tier controls"
      icon="mic-circle"
      color={accent}
      showSecondaryTabs={false}
    >
      <View style={{ paddingHorizontal: 16, marginTop: 10 }}>
        <View
          style={[s.card, { backgroundColor: colors.card, borderColor: colors.border, marginHorizontal: 0, marginBottom: 0 }]}
          data-testid="ai-speech-plan-card"
          testID="ai-speech-plan-card"
        >
          <Text style={[s.title, { color: colors.text, marginBottom: 6 }]} data-testid="ai-speech-plan-value" testID="ai-speech-plan-value">
            {scopeLabel}
          </Text>
          <Text style={{ color: colors.textSec, fontSize: 12 }} data-testid="ai-speech-plan-name" testID="ai-speech-plan-name">
            Current plan: {plan}
          </Text>
          <Text style={{ color: colors.textSec, fontSize: 12, marginTop: 6 }} data-testid="ai-speech-plan-project-limit" testID="ai-speech-plan-project-limit">
            Monthly projects: {limits.projects_per_month && limits.projects_per_month >= 0 ? limits.projects_per_month : 'Unlimited'}
          </Text>
          <Text style={{ color: colors.textSec, fontSize: 12, marginTop: 6 }} data-testid="ai-speech-plan-analysis-limit" testID="ai-speech-plan-analysis-limit">
            Daily analyses: {limits.analyses_per_day && limits.analyses_per_day >= 0 ? limits.analyses_per_day : 'Unlimited'}
          </Text>
          <Text style={{ color: colors.textMuted, fontSize: 12, marginTop: 6 }} data-testid="ai-speech-plan-usage-projects" testID="ai-speech-plan-usage-projects">
            Projects this month: {usage.projects_this_month}
          </Text>
          <Text style={{ color: colors.textMuted, fontSize: 12, marginTop: 4 }} data-testid="ai-speech-plan-usage-analyses" testID="ai-speech-plan-usage-analyses">
            Analyses today: {usage.analyses_today}
          </Text>
          <Text style={{ color: colors.textMuted, fontSize: 12, marginTop: 4 }} data-testid="ai-speech-plan-usage-transcriptions" testID="ai-speech-plan-usage-transcriptions">
            Transcriptions today: {usage.transcriptions_today}
          </Text>
          <Text style={{ color: colors.textMuted, fontSize: 12, marginTop: 4 }} data-testid="ai-speech-plan-usage-synthesis" testID="ai-speech-plan-usage-synthesis">
            Synthesis today: {usage.synthesis_today}
          </Text>
          {uiError ? (
            <Text style={{ color: colors.error, fontSize: 12, marginTop: 8 }} data-testid="ai-speech-ui-error" testID="ai-speech-ui-error">
              {uiError}
            </Text>
          ) : null}
        </View>
      </View>

      <ScrollView contentContainerStyle={{ paddingVertical: 16 }}>
        <View style={[s.card, { backgroundColor: colors.card, borderColor: colors.border }]} data-testid="ai-speech-project-workspace-card" testID="ai-speech-project-workspace-card">
          <Text style={[s.title, { color: colors.text }]} data-testid="ai-speech-project-workspace-title" testID="ai-speech-project-workspace-title">Project Workspace</Text>
          <TextInput
            style={[s.input, { backgroundColor: colors.bgSoft, borderColor: colors.border, color: colors.text }]}
            value={projectTitle}
            onChangeText={setProjectTitle}
            placeholder="Project title (e.g., Q3 keynote rehearsal)"
            placeholderTextColor={colors.textMuted}
            data-testid="ai-speech-project-title-input"
            testID="ai-speech-project-title-input"
          />
          <TextInput
            style={[s.textArea, { minHeight: 70, backgroundColor: colors.bgSoft, borderColor: colors.border, color: colors.text }]}
            value={projectBrief}
            onChangeText={setProjectBrief}
            placeholder="Optional brief: audience, context, and speaking goal"
            placeholderTextColor={colors.textMuted}
            multiline
            data-testid="ai-speech-project-brief-input"
            testID="ai-speech-project-brief-input"
          />
          <TouchableOpacity
            style={[s.btn, { backgroundColor: colors.accent }]}
            onPress={createProject}
            disabled={actionLoading === 'create'}
            data-testid="ai-speech-create-project-button"
            testID="ai-speech-create-project-button"
            accessibilityRole="button"
          >
            {actionLoading === 'create' ? (
              <ActivityIndicator color={colors.primaryText} />
            ) : (
              <>
                <Ionicons name="add-circle" size={18} color={colors.primaryText} />
                <Text style={{ color: colors.primaryText, fontWeight: '700' }}>Create Project</Text>
              </>
            )}
          </TouchableOpacity>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ marginTop: 12 }} data-testid="ai-speech-project-chip-list" testID="ai-speech-project-chip-list">
            <View style={{ flexDirection: 'row', gap: 8 }}>
              {projects.map((project) => {
                const selected = selectedProjectId === project.project_id;
                return (
                  <TouchableOpacity
                    key={project.project_id}
                    style={{
                      paddingHorizontal: 12,
                      paddingVertical: 8,
                      borderRadius: 12,
                      borderWidth: 1,
                      borderColor: selected ? colors.primary : colors.border,
                      backgroundColor: selected ? colors.primarySoft : colors.bgSoft,
                    }}
                    onPress={() => setSelectedProjectId(project.project_id)}
                    data-testid={`ai-speech-project-chip-${project.project_id}`}
                    testID={`ai-speech-project-chip-${project.project_id}`}
                    accessibilityRole="button"
                  >
                    <Text style={{ color: selected ? colors.primary : colors.text, fontSize: 12, fontWeight: '700' }}>{project.title}</Text>
                    <Text style={{ color: colors.textMuted, fontSize: 10, marginTop: 2 }}>Analyses: {project.analysis_count || 0}</Text>
                  </TouchableOpacity>
                );
              })}
            </View>
          </ScrollView>
        </View>

        <View style={[s.card, { backgroundColor: colors.card, borderColor: colors.border }]} data-testid="ai-speech-analysis-card" testID="ai-speech-analysis-card">
          <Text style={[s.title, { color: colors.text }]} data-testid="ai-speech-analysis-title" testID="ai-speech-analysis-title">Speech Analysis Workspace</Text>
          <Text style={{ color: colors.textMuted, fontSize: 12, marginBottom: 8 }} data-testid="ai-speech-selected-project" testID="ai-speech-selected-project">
            Active project: {selectedProject?.title || 'Auto-create on first analysis'}
          </Text>
          <TextInput
            style={[s.textArea, { backgroundColor: colors.bgSoft, borderColor: colors.border, color: colors.text }]}
            value={analysisPrompt}
            onChangeText={setAnalysisPrompt}
            placeholder="Paste your speech draft or describe speaking scenario for AI coaching"
            placeholderTextColor={colors.textMuted}
            multiline
            data-testid="ai-speech-analysis-input"
            testID="ai-speech-analysis-input"
          />
          <TouchableOpacity
            style={[s.btn, { backgroundColor: accent }]}
            onPress={analyzeSpeech}
            disabled={actionLoading === 'analyze'}
            data-testid="ai-speech-analyze-button"
            testID="ai-speech-analyze-button"
            accessibilityRole="button"
          >
            {actionLoading === 'analyze' ? (
              <ActivityIndicator color={colors.primaryText} />
            ) : (
              <>
                <Ionicons name="analytics" size={18} color={colors.primaryText} />
                <Text style={{ color: colors.primaryText, fontWeight: '700' }}>Run Voice Analysis</Text>
              </>
            )}
          </TouchableOpacity>
          <TouchableOpacity
            style={[s.btn, { backgroundColor: colors.info, marginTop: 10 }]}
            onPress={transcribeSpeech}
            disabled={actionLoading === 'transcribe'}
            data-testid="ai-speech-transcribe-button"
            testID="ai-speech-transcribe-button"
            accessibilityRole="button"
          >
            {actionLoading === 'transcribe' ? (
              <ActivityIndicator color={colors.primaryText} />
            ) : (
              <>
                <Ionicons name="mic" size={18} color={colors.primaryText} />
                <Text style={{ color: colors.primaryText, fontWeight: '700' }}>Transcribe Audio</Text>
              </>
            )}
          </TouchableOpacity>
          <Text style={{ color: colors.textMuted, fontSize: 11, marginTop: 8 }} data-testid="ai-speech-transcribe-status" testID="ai-speech-transcribe-status">
            {transcribeText ? 'Transcription complete.' : 'Transcription ready.'}
          </Text>
          {transcribeText ? (
            <Text style={{ color: colors.textSec, fontSize: 12, marginTop: 6 }} data-testid="ai-speech-transcribe-result" testID="ai-speech-transcribe-result" numberOfLines={4}>
              {transcribeText}
            </Text>
          ) : null}
        </View>

        <View style={[s.card, { backgroundColor: colors.card, borderColor: colors.border }]} data-testid="ai-speech-synthesis-card" testID="ai-speech-synthesis-card">
          <Text style={[s.title, { color: colors.text }]} data-testid="ai-speech-synthesis-title" testID="ai-speech-synthesis-title">Speech Synthesis + Voice Preset</Text>
          <TextInput
            style={[s.textArea, { minHeight: 80, backgroundColor: colors.bgSoft, borderColor: colors.border, color: colors.text }]}
            value={synthesisText}
            onChangeText={setSynthesisText}
            placeholder="Text for generated voice output"
            placeholderTextColor={colors.textMuted}
            multiline
            data-testid="ai-speech-synthesis-input"
            testID="ai-speech-synthesis-input"
          />
          <TextInput
            style={[s.input, { backgroundColor: colors.bgSoft, borderColor: colors.border, color: colors.text }]}
            value={selectedVoice}
            onChangeText={setSelectedVoice}
            placeholder="Voice (alloy / nova / echo ...)"
            placeholderTextColor={colors.textMuted}
            data-testid="ai-speech-voice-input"
            testID="ai-speech-voice-input"
          />
          <TextInput
            style={[s.input, { backgroundColor: colors.bgSoft, borderColor: colors.border, color: colors.text }]}
            value={presetLanguage}
            onChangeText={setPresetLanguage}
            placeholder="Language code (en)"
            placeholderTextColor={colors.textMuted}
            data-testid="ai-speech-preset-language-input"
            testID="ai-speech-preset-language-input"
          />
          <TextInput
            style={[s.textArea, { minHeight: 70, backgroundColor: colors.bgSoft, borderColor: colors.border, color: colors.text }]}
            value={presetNotes}
            onChangeText={setPresetNotes}
            placeholder="Voice style notes"
            placeholderTextColor={colors.textMuted}
            multiline
            data-testid="ai-speech-preset-notes-input"
            testID="ai-speech-preset-notes-input"
          />
          <TouchableOpacity
            style={[s.btn, { backgroundColor: colors.success }]}
            onPress={saveVoicePreset}
            disabled={actionLoading === 'preset'}
            data-testid="ai-speech-save-preset-button"
            testID="ai-speech-save-preset-button"
            accessibilityRole="button"
          >
            {actionLoading === 'preset' ? <ActivityIndicator color={colors.primaryText} /> : <Text style={{ color: colors.primaryText, fontWeight: '700' }}>Save Voice Preset</Text>}
          </TouchableOpacity>
          <TouchableOpacity
            style={[s.btn, { backgroundColor: colors.warning, marginTop: 10 }]}
            onPress={synthesizeSpeech}
            disabled={actionLoading === 'synthesize'}
            data-testid="ai-speech-synthesize-button"
            testID="ai-speech-synthesize-button"
            accessibilityRole="button"
          >
            {actionLoading === 'synthesize' ? <ActivityIndicator color={colors.primaryText} /> : <Text style={{ color: colors.primaryText, fontWeight: '700' }}>Synthesize Speech</Text>}
          </TouchableOpacity>
          {lastAudioUrl ? (
            <Text style={{ color: colors.info, fontSize: 12, marginTop: 8 }} data-testid="ai-speech-audio-url" testID="ai-speech-audio-url">
              Audio file ready: {lastAudioUrl}
            </Text>
          ) : null}
          <Text style={{ color: colors.textMuted, fontSize: 11, marginTop: 8 }} data-testid="ai-speech-preset-count" testID="ai-speech-preset-count">
            Presets saved: {voicePresets.length}
          </Text>
        </View>

        <View style={[s.card, { backgroundColor: colors.card, borderColor: colors.border }]} data-testid="ai-speech-export-card" testID="ai-speech-export-card">
          <Text style={[s.title, { color: colors.text }]} data-testid="ai-speech-export-title" testID="ai-speech-export-title">Enterprise Export</Text>
          <TouchableOpacity
            style={[s.btn, { backgroundColor: colors.primary }]}
            onPress={exportProjectData}
            disabled={actionLoading === 'export'}
            data-testid="ai-speech-export-button"
            testID="ai-speech-export-button"
            accessibilityRole="button"
          >
            {actionLoading === 'export' ? <ActivityIndicator color={colors.primaryText} /> : <Text style={{ color: colors.primaryText, fontWeight: '700' }}>Generate Export</Text>}
          </TouchableOpacity>
          {lastExportPreview ? (
            <Text style={{ color: colors.textSec, fontSize: 12, marginTop: 8 }} data-testid="ai-speech-export-preview" testID="ai-speech-export-preview">
              {lastExportPreview}
            </Text>
          ) : null}
        </View>

        {analysisResult ? (
          <View style={[s.card, { backgroundColor: colors.card, borderColor: colors.border }]} data-testid="ai-speech-result-card" testID="ai-speech-result-card">
            <Text style={[s.title, { color: colors.text }]} data-testid="ai-speech-result-title" testID="ai-speech-result-title">Analysis Result</Text>
            <Text style={[s.result, { color: colors.textSec }]} data-testid="ai-speech-result-text" testID="ai-speech-result-text">
              {analysisResult}
            </Text>
            <FeatureToolbar content={analysisResult} featureKey="ai-speech" title="Voice Analysis" />
            <AIFeedbackBar feature="ai-speech" response={analysisResult} />
          </View>
        ) : null}

        <View style={[s.card, { backgroundColor: colors.card, borderColor: colors.border }]} data-testid="ai-speech-history-card" testID="ai-speech-history-card">
          <Text style={[s.title, { color: colors.text }]} data-testid="ai-speech-history-title" testID="ai-speech-history-title">Analysis History</Text>
          {history.length === 0 ? (
            <Text style={{ color: colors.textMuted, fontSize: 12 }} data-testid="ai-speech-history-empty" testID="ai-speech-history-empty">
              No analysis history yet for this project.
            </Text>
          ) : (
            <View style={{ gap: 10 }} data-testid="ai-speech-history-list" testID="ai-speech-history-list">
              {history.map((item) => (
                <TouchableOpacity
                  key={item.analysis_id}
                  style={{ borderWidth: 1, borderColor: colors.border, borderRadius: 12, padding: 10, backgroundColor: colors.bgSoft }}
                  onPress={() => setAnalysisResult(item.analysis)}
                  data-testid={`ai-speech-history-item-${item.analysis_id}`}
                  testID={`ai-speech-history-item-${item.analysis_id}`}
                  accessibilityRole="button"
                >
                  <Text style={{ color: colors.text, fontSize: 12, fontWeight: '700' }} numberOfLines={2}>
                    {item.prompt}
                  </Text>
                  <Text style={{ color: colors.textMuted, fontSize: 10, marginTop: 4 }}>
                    {new Date(item.created_at).toLocaleString()}
                  </Text>
                </TouchableOpacity>
              ))}
            </View>
          )}
        </View>
      </ScrollView>
    </FeatureLayout>
  );
}
