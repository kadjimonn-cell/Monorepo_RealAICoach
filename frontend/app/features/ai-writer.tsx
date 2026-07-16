import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { View, Text, ScrollView, TouchableOpacity, TextInput, ActivityIndicator, Alert, useWindowDimensions } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../src/services/api';
import FeatureLayout from '../../src/components/FeatureLayout';
import MarkdownDisplay from '../../src/components/MarkdownDisplay';
import { useTheme } from '../../src/context/ThemeContext';
import { useAuth } from '../../src/context/AuthContext';
import FeatureToolbar from '../../src/components/FeatureToolbar';
import AIFeedbackBar from '../../src/components/AIFeedbackBar';
import { useTranslation } from '../../src/hooks/useTranslation';
import { useAppStore } from '../../src/store/appStore';
import { handleAppRecoverableError } from '../../src/utils/appRecoverableError';

const TASKS = [
  { id: 'draft', label: 'Draft', icon: 'sparkles-outline' },
  { id: 'rewrite', label: 'Rewrite', icon: 'create-outline' },
  { id: 'shorten', label: 'Shorten', icon: 'remove-outline' },
  { id: 'expand', label: 'Expand', icon: 'add-outline' },
  { id: 'tone_shift', label: 'Tone Shift', icon: 'color-wand-outline' },
  { id: 'grammar_polish', label: 'Grammar', icon: 'checkmark-done-outline' },
  { id: 'seo_optimize', label: 'SEO', icon: 'trending-up-outline' },
];

const TONES = ['professional', 'concise', 'friendly', 'persuasive', 'executive', 'empathetic'];

export default function AIWriterScreen() {
  const { t } = useTranslation();
  t('i18n.route.features.ai-writer.probe');

  const { width } = useWindowDimensions();
  const { colors } = useTheme();
  const { user } = useAuth();
  const { userId, initializeUser } = useAppStore();

  const [documents, setDocuments] = useState([]);
  const [activeDocument, setActiveDocument] = useState(null);
  const [editorValue, setEditorValue] = useState('');
  const [newDocTitle, setNewDocTitle] = useState('');
  const [task, setTask] = useState('rewrite');
  const [tone, setTone] = useState('professional');
  const [audience, setAudience] = useState('general audience');
  const [readingLevel, setReadingLevel] = useState('general');
  const [lengthTarget, setLengthTarget] = useState('');
  const [loadingBootstrap, setLoadingBootstrap] = useState(true);
  const [runLoading, setRunLoading] = useState(false);
  const [saveLoading, setSaveLoading] = useState(false);
  const [brandSaving, setBrandSaving] = useState(false);
  const [errorMessage, setErrorMessage] = useState('');
  const [resultContent, setResultContent] = useState('');
  const [brandProfile, setBrandProfile] = useState({
    brand_name: '',
    voice_summary: '',
    preferred_phrases: [],
    do_not_use: [],
  });
  const [preferredPhrasesInput, setPreferredPhrasesInput] = useState('');
  const [doNotUseInput, setDoNotUseInput] = useState('');
  const [stats, setStats] = useState({ documents_count: 0, runs_7d: 0, avg_quality: 0 });
  const [templates, setTemplates] = useState([]);
  const [selectedTemplate, setSelectedTemplate] = useState(null);
  const [templateTopic, setTemplateTopic] = useState('');
  const [templatesLoading, setTemplatesLoading] = useState(false);
  const [exportFormat, setExportFormat] = useState('txt');
  const [exportLoading, setExportLoading] = useState(false);

  const fallbackUserId = useMemo(() => user?.user_id || userId || '', [user?.user_id, userId]);
  const isWide = width >= 1040;

  const s = {
    card: {
      backgroundColor: colors.card,
      borderRadius: 16,
      padding: 16,
      marginBottom: 12,
      borderWidth: 1,
      borderColor: colors.border,
    },
    cardTitle: { color: colors.text, fontSize: 15, fontWeight: '800', marginBottom: 10 },
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
    buttonPrimary: {
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'center',
      borderRadius: 12,
      paddingVertical: 12,
      gap: 8,
      backgroundColor: colors.primary,
    },
    buttonSecondary: {
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'center',
      borderRadius: 12,
      paddingVertical: 12,
      borderWidth: 1,
      borderColor: colors.border,
      backgroundColor: colors.bgSoft,
      gap: 8,
    },
  };

  const syncSummaryFromDocument = useCallback((doc) => {
    setDocuments((prev) => {
      const nextSummary = {
        doc_id: doc.doc_id,
        title: doc.title,
        updated_at: new Date().toISOString(),
        version_count: (doc.versions || []).length,
        latest_quality: doc.last_quality_scores?.overall,
      };
      const existingWithout = prev.filter((item) => item.doc_id !== doc.doc_id);
      return [nextSummary, ...existingWithout].slice(0, 20);
    });
  }, []);

  const loadDocument = useCallback(async (docId) => {
    if (!fallbackUserId) return;
    try {
      const res = await api.get(`/writing-studio/documents/${docId}`, {
        params: { fallback_user_id: fallbackUserId },
      });
      const doc = res?.data?.document;
      if (!doc) return;
      setActiveDocument(doc);
      setEditorValue(doc.current_content || '');
      setResultContent('');
      setErrorMessage('');
    } catch (error) {
      handleAppRecoverableError({
        scope: 'app/features/ai-writer.tsx#loadDocument',
        error,
        message: 'Failed to load document. Please retry.',
      
        notifyMode: 'silent',
      });
      setErrorMessage('Unable to load the selected document.');
    }
  }, [fallbackUserId]);

  const loadBootstrap = useCallback(async () => {
    if (!fallbackUserId) return;
    setLoadingBootstrap(true);
    try {
      const res = await api.get('/writing-studio/bootstrap', {
        params: { fallback_user_id: fallbackUserId },
      });
      const incomingDocs = res?.data?.documents || [];
      const profile = res?.data?.brand_profile || {};
      setDocuments(incomingDocs);
      setBrandProfile({
        brand_name: profile.brand_name || '',
        voice_summary: profile.voice_summary || '',
        preferred_phrases: profile.preferred_phrases || [],
        do_not_use: profile.do_not_use || [],
      });
      setPreferredPhrasesInput((profile.preferred_phrases || []).join(', '));
      setDoNotUseInput((profile.do_not_use || []).join(', '));
      setStats({
        documents_count: Number(res?.data?.stats?.documents_count || incomingDocs.length || 0),
        runs_7d: Number(res?.data?.stats?.runs_7d || 0),
        avg_quality: Number(res?.data?.stats?.avg_quality || 0),
      });

      if (incomingDocs.length > 0) {
        await loadDocument(incomingDocs[0].doc_id);
      } else {
        setActiveDocument(null);
        setEditorValue('');
      }
    } catch (error) {
      handleAppRecoverableError({
        scope: 'app/features/ai-writer.tsx#loadBootstrap',
        error,
        message: 'Failed to initialize Smart Writing Studio. Please retry.',
      
        notifyMode: 'silent',
      });
      setErrorMessage('Could not load Smart Writing Studio data.');
    } finally {
      setLoadingBootstrap(false);
    }
  }, [fallbackUserId, loadDocument]);

  useEffect(() => {
    initializeUser();
  }, [initializeUser]);

  useEffect(() => {
    if (!fallbackUserId) return;
    const bootstrapTimer = setTimeout(() => {
      void loadBootstrap();
    }, 0);
    return () => clearTimeout(bootstrapTimer);
  }, [fallbackUserId, loadBootstrap]);

  const handleCreateDocument = useCallback(async () => {
    if (!fallbackUserId) {
      setErrorMessage('Session identity unavailable. Please refresh and retry.');
      return null;
    }

    const title = (newDocTitle || `Untitled Draft ${new Date().toLocaleDateString()}`).trim();
    try {
      const res = await api.post('/writing-studio/documents', {
        title,
        content: editorValue,
        fallback_user_id: fallbackUserId,
      });
      const doc = res?.data?.document;
      if (!doc) return null;
      setNewDocTitle('');
      setActiveDocument(doc);
      setEditorValue(doc.current_content || '');
      setErrorMessage('');
      syncSummaryFromDocument(doc);
      return doc;
    } catch (error) {
      handleAppRecoverableError({
        scope: 'app/features/ai-writer.tsx#handleCreateDocument',
        error,
        message: 'Failed to create document. Please retry.',
        notifyMode: 'dialog',
        userInitiated: true,
        onRetry: () => { void handleCreateDocument(); },
      });
      setErrorMessage('Could not create document. Retry in a moment.');
      return null;
    }
  }, [editorValue, fallbackUserId, newDocTitle, syncSummaryFromDocument]);

  const handleSaveDraft = async () => {
    if (!activeDocument?.doc_id || !fallbackUserId) return;
    setSaveLoading(true);
    try {
      const res = await api.patch(`/writing-studio/documents/${activeDocument.doc_id}`, {
        title: activeDocument.title,
        content: editorValue,
        fallback_user_id: fallbackUserId,
      });
      const updated = res?.data?.document;
      if (!updated) return;
      setActiveDocument(updated);
      syncSummaryFromDocument(updated);
      setErrorMessage('');
      Alert.alert('Saved', 'Draft saved successfully.');
    } catch (error) {
      handleAppRecoverableError({
        scope: 'app/features/ai-writer.tsx#handleSaveDraft',
        error,
        message: 'Failed to save draft. Please retry.',
        notifyMode: 'dialog',
        userInitiated: true,
        onRetry: () => { void handleSaveDraft(); },
      });
      setErrorMessage('Unable to save draft right now.');
    } finally {
      setSaveLoading(false);
    }
  };

  const handleSaveBrandProfile = useCallback(async () => {
    if (!fallbackUserId) return;
    setBrandSaving(true);
    try {
      const res = await api.put('/writing-studio/brand-profile', {
        brand_name: brandProfile.brand_name,
        voice_summary: brandProfile.voice_summary,
        preferred_phrases: preferredPhrasesInput.split(',').map((item) => item.trim()).filter(Boolean),
        do_not_use: doNotUseInput.split(',').map((item) => item.trim()).filter(Boolean),
        fallback_user_id: fallbackUserId,
      });
      const next = res?.data?.brand_profile || {};
      setBrandProfile({
        brand_name: next.brand_name || '',
        voice_summary: next.voice_summary || '',
        preferred_phrases: next.preferred_phrases || [],
        do_not_use: next.do_not_use || [],
      });
      setPreferredPhrasesInput((next.preferred_phrases || []).join(', '));
      setDoNotUseInput((next.do_not_use || []).join(', '));
      setErrorMessage('');
    } catch (error) {
      handleAppRecoverableError({
        scope: 'app/features/ai-writer.tsx#handleSaveBrandProfile',
        error,
        message: 'Failed to save brand profile. Please retry.',
        notifyMode: 'dialog',
        userInitiated: true,
        onRetry: () => { void handleSaveBrandProfile(); },
      });
      setErrorMessage('Unable to save brand profile settings.');
    } finally {
      setBrandSaving(false);
    }
  }, [brandProfile.brand_name, brandProfile.voice_summary, doNotUseInput, fallbackUserId, preferredPhrasesInput]);

  const loadTemplates = useCallback(async () => {
    if (!fallbackUserId) return;
    setTemplatesLoading(true);
    try {
      const res = await api.get('/writing-studio/templates', {
        params: { fallback_user_id: fallbackUserId },
      });
      setTemplates(res?.data?.templates || []);
    } catch (error) {
      handleAppRecoverableError({
        scope: 'app/features/ai-writer.tsx#loadTemplates',
        error,
        message: 'Failed to load templates. Please retry.',
      
        notifyMode: 'silent',
      });
    } finally {
      setTemplatesLoading(false);
    }
  }, [fallbackUserId]);

  const applyTemplate = useCallback(async () => {
    if (!selectedTemplate || !templateTopic.trim() || !fallbackUserId) return;
    setTemplatesLoading(true);
    try {
      const res = await api.post('/writing-studio/templates/apply', {
        template_id: selectedTemplate.id,
        topic: templateTopic,
        audience,
        tone,
        fallback_user_id: fallbackUserId,
      });
      const prompt = res?.data?.generated_prompt || '';
      setEditorValue(prompt);
      setTemplateTopic('');
      Alert.alert('Template Applied', 'Template content added to editor. Click "Run Task" to generate.');
    } catch (error) {
      handleAppRecoverableError({
        scope: 'app/features/ai-writer.tsx#applyTemplate',
        error,
        message: 'Failed to apply template. Please retry.',
        notifyMode: 'dialog',
        userInitiated: true,
        onRetry: () => { void applyTemplate(); },
      });
      if (error?.response?.data?.detail?.upgrade_prompt) {
        const detail = error.response.data.detail;
        Alert.alert('Upgrade Required', detail.message || 'This template requires a paid plan.');
      }
    } finally {
      setTemplatesLoading(false);
    }
  }, [selectedTemplate, templateTopic, fallbackUserId, audience, tone]);

  const handleExportDocument = useCallback(async () => {
    if (!activeDocument?.doc_id || !fallbackUserId) {
      Alert.alert('Error', 'No active document to export.');
      return;
    }
    setExportLoading(true);
    try {
      const res = await api.post(`/writing-studio/documents/${activeDocument.doc_id}/export`, {
        export_format: exportFormat,
        fallback_user_id: fallbackUserId,
      }, {
        responseType: 'blob',
      });
      
      // For web: trigger download
      if (typeof window !== 'undefined') {
        const blob = new Blob([res.data]);
        const url = window.URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = `${activeDocument.title.replace(/\s/g, '_')}.${exportFormat}`;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        window.URL.revokeObjectURL(url);
        Alert.alert('Success', `Document exported as ${exportFormat.toUpperCase()}`);
      }
    } catch (error) {
      handleAppRecoverableError({
        scope: 'app/features/ai-writer.tsx#handleExportDocument',
        error,
        message: 'Failed to export document. Please retry.',
        notifyMode: 'dialog',
        userInitiated: true,
        onRetry: () => { void handleExportDocument(); },
      });
      if (error?.response?.data?.detail?.upgrade_prompt) {
        const detail = error.response.data.detail;
        Alert.alert('Upgrade Required', detail.message || 'This export format requires a paid plan.');
      }
    } finally {
      setExportLoading(false);
    }
  }, [activeDocument, exportFormat, fallbackUserId]);

  useEffect(() => {
    if (fallbackUserId) {
      void loadTemplates();
    }
  }, [fallbackUserId, loadTemplates]);

  const runStudioTask = useCallback(async () => {
    setErrorMessage('');
    setRunLoading(true);
    try {
      let currentDoc = activeDocument;
      if (!currentDoc) {
        currentDoc = await handleCreateDocument();
      }
      if (!currentDoc?.doc_id) {
        setRunLoading(false);
        return;
      }

      const idempotencyKey = `${currentDoc.doc_id}:${task}:${Date.now()}`;
      const res = await api.post('/writing-studio/runs', {
        document_id: currentDoc.doc_id,
        task,
        instructions: editorValue,
        tone,
        audience,
        reading_level: readingLevel,
        length_target: lengthTarget || null,
        fallback_user_id: fallbackUserId,
        idempotency_key: idempotencyKey,
      });
      const nextDoc = res?.data?.document;
      const output = String(res?.data?.run?.output || '').trim();
      if (nextDoc) {
        setActiveDocument(nextDoc);
        setEditorValue(nextDoc.current_content || editorValue);
        syncSummaryFromDocument(nextDoc);
      }
      setResultContent(output || nextDoc?.current_content || '');
    } catch (error) {
      handleAppRecoverableError({
        scope: 'app/features/ai-writer.tsx#runStudioTask',
        error,
        message: 'Smart Writing Studio run failed. Please retry.',
        notifyMode: 'dialog',
        userInitiated: true,
        onRetry: () => { void runStudioTask(); },
      });
      setErrorMessage('Generation failed. Use Retry to run the task again.');
    } finally {
      setRunLoading(false);
    }
  }, [activeDocument, audience, editorValue, fallbackUserId, handleCreateDocument, lengthTarget, readingLevel, syncSummaryFromDocument, task, tone]);

  const handleRestoreVersion = async (versionId) => {
    if (!activeDocument?.doc_id || !fallbackUserId) return;
    try {
      const res = await api.post(`/writing-studio/documents/${activeDocument.doc_id}/restore/${versionId}`, null, {
        params: { fallback_user_id: fallbackUserId },
      });
      const doc = res?.data?.document;
      if (!doc) return;
      setActiveDocument(doc);
      setEditorValue(doc.current_content || '');
      setResultContent(doc.current_content || '');
      syncSummaryFromDocument(doc);
      setErrorMessage('');
    } catch (error) {
      handleAppRecoverableError({
        scope: 'app/features/ai-writer.tsx#handleRestoreVersion',
        error,
        message: 'Failed to restore this version. Please retry.',
        notifyMode: 'dialog',
        userInitiated: true,
        onRetry: () => { void handleRestoreVersion(versionId); },
      });
      setErrorMessage('Could not restore selected version.');
    }
  };

  const qualityOverall = activeDocument?.last_quality_scores?.overall;
  const versionRows = useMemo(() => {
    const versions = activeDocument?.versions || [];
    return [...versions].reverse().slice(0, 8);
  }, [activeDocument?.versions]);

  const renderDocumentList = (
    <View style={[s.card, { flex: isWide ? 0.32 : 1 }]} data-testid="smart-writing-studio-doc-list-card" testID="smart-writing-studio-doc-list-card">
      <Text style={s.cardTitle} data-testid="smart-writing-studio-doc-list-title" testID="smart-writing-studio-doc-list-title">Workspace Documents</Text>
      <View style={{ flexDirection: 'row', gap: 8, marginBottom: 10 }}>
        <TextInput
          value={newDocTitle}
          onChangeText={setNewDocTitle}
          placeholder="New document title"
          placeholderTextColor={colors.textMuted}
          style={[s.input, { flex: 1 }]}
          data-testid="smart-writing-studio-new-doc-title-input"
          testID="smart-writing-studio-new-doc-title-input"
        />
        <TouchableOpacity
          style={[s.buttonSecondary, { width: 48 }]}
          onPress={() => void handleCreateDocument()}
          data-testid="smart-writing-studio-create-doc-button"
          testID="smart-writing-studio-create-doc-button"
          accessibilityRole="button"
        >
          <Ionicons name="add" size={18} color={colors.text} />
        </TouchableOpacity>
      </View>

      <View style={{ gap: 8 }}>
        {documents.length === 0 ? (
          <Text style={{ color: colors.textMuted, fontSize: 12 }} data-testid="smart-writing-studio-empty-doc-message" testID="smart-writing-studio-empty-doc-message">
            No documents yet. Create your first writing workspace draft.
          </Text>
        ) : documents.map((doc) => {
          const selected = activeDocument?.doc_id === doc.doc_id;
          return (
            <TouchableOpacity
              key={doc.doc_id}
              onPress={() => void loadDocument(doc.doc_id)}
              style={{
                borderWidth: 1,
                borderColor: selected ? colors.primary : colors.border,
                backgroundColor: selected ? colors.primarySoft : colors.bg,
                borderRadius: 10,
                paddingHorizontal: 10,
                paddingVertical: 8,
              }}
              data-testid={`smart-writing-studio-doc-item-${doc.doc_id}`}
              testID={`smart-writing-studio-doc-item-${doc.doc_id}`}
              accessibilityRole="button"
            >
              <Text style={{ color: selected ? colors.primary : colors.text, fontWeight: '700', fontSize: 12 }}>{doc.title}</Text>
              <Text style={{ color: colors.textMuted, fontSize: 11, marginTop: 2 }}>
                {doc.version_count || 0} versions • quality {doc.latest_quality ?? '--'}
              </Text>
            </TouchableOpacity>
          );
        })}
      </View>
    </View>
  );

  return (
    <FeatureLayout
      feature="ai-writer"
      title="Smart Writing Studio"
      subtitle="Enterprise writing workspace with version history, brand voice controls, and quality scoring"
      icon="create"
      color={colors.success}
    >
      <ScrollView contentContainerStyle={{ paddingVertical: 14, paddingBottom: 40 }} data-testid="smart-writing-studio-v2-root" testID="smart-writing-studio-v2-root">
        <View style={[s.card, { marginBottom: 10 }]} data-testid="smart-writing-studio-kpi-strip" testID="smart-writing-studio-kpi-strip">
          <Text style={s.cardTitle} data-testid="smart-writing-studio-kpi-title" testID="smart-writing-studio-kpi-title">Studio Momentum</Text>
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
            <View style={{ backgroundColor: colors.bgSoft, borderRadius: 999, paddingHorizontal: 10, paddingVertical: 6 }} data-testid="smart-writing-studio-kpi-documents" testID="smart-writing-studio-kpi-documents"><Text style={{ color: colors.text, fontSize: 11, fontWeight: '700' }}>Docs: {stats.documents_count}</Text></View>
            <View style={{ backgroundColor: colors.bgSoft, borderRadius: 999, paddingHorizontal: 10, paddingVertical: 6 }} data-testid="smart-writing-studio-kpi-runs" testID="smart-writing-studio-kpi-runs"><Text style={{ color: colors.text, fontSize: 11, fontWeight: '700' }}>Runs (7d): {stats.runs_7d}</Text></View>
            <View style={{ backgroundColor: colors.bgSoft, borderRadius: 999, paddingHorizontal: 10, paddingVertical: 6 }} data-testid="smart-writing-studio-kpi-quality" testID="smart-writing-studio-kpi-quality"><Text style={{ color: colors.text, fontSize: 11, fontWeight: '700' }}>Avg Quality: {stats.avg_quality}</Text></View>
            <View style={{ backgroundColor: colors.bgSoft, borderRadius: 999, paddingHorizontal: 10, paddingVertical: 6 }} data-testid="smart-writing-studio-kpi-current-quality" testID="smart-writing-studio-kpi-current-quality"><Text style={{ color: colors.text, fontSize: 11, fontWeight: '700' }}>Current Quality: {qualityOverall ?? '--'}</Text></View>
          </View>
        </View>

        {loadingBootstrap ? (
          <View style={[s.card, { alignItems: 'center', justifyContent: 'center', paddingVertical: 24 }]} data-testid="smart-writing-studio-bootstrap-loading" testID="smart-writing-studio-bootstrap-loading">
            <ActivityIndicator size="small" color={colors.primary} />
            <Text style={{ color: colors.textMuted, marginTop: 8 }}>Loading Smart Writing Studio workspace...</Text>
          </View>
        ) : null}

        {errorMessage ? (
          <View style={[s.card, { borderColor: colors.errorSoft, backgroundColor: colors.errorSoft }]} data-testid="smart-writing-studio-error-banner" testID="smart-writing-studio-error-banner">
            <Text style={{ color: colors.error, fontSize: 13, fontWeight: '700' }} data-testid="smart-writing-studio-error-message" testID="smart-writing-studio-error-message">{errorMessage}</Text>
            <TouchableOpacity
              onPress={() => void runStudioTask()}
              style={[s.buttonSecondary, { marginTop: 10, borderColor: colors.error, backgroundColor: colors.card }]}
              data-testid="smart-writing-studio-error-retry-button"
              testID="smart-writing-studio-error-retry-button"
              accessibilityRole="button"
            >
              <Ionicons name="refresh" size={15} color={colors.error} />
              <Text style={{ color: colors.error, fontWeight: '700' }}>Retry</Text>
            </TouchableOpacity>
          </View>
        ) : null}

        {isWide ? (
          <View style={{ flexDirection: 'row', gap: 12, alignItems: 'flex-start' }}>
            {renderDocumentList}
            <View style={{ flex: 0.68, gap: 12 }}>
              <View style={s.card} data-testid="smart-writing-studio-editor-card" testID="smart-writing-studio-editor-card">
                <Text style={s.cardTitle} data-testid="smart-writing-studio-editor-title" testID="smart-writing-studio-editor-title">Document Editor</Text>
                <TextInput
                  style={[s.input, { marginBottom: 8 }]}
                  value={activeDocument?.title || ''}
                  onChangeText={(value) => setActiveDocument((prev) => (prev ? { ...prev, title: value } : prev))}
                  placeholder="Document title"
                  placeholderTextColor={colors.textMuted}
                  data-testid="smart-writing-studio-doc-title-input"
                  testID="smart-writing-studio-doc-title-input"
                />
                <TextInput
                  style={[s.input, { minHeight: 220, textAlignVertical: 'top' }]}
                  value={editorValue}
                  onChangeText={setEditorValue}
                  multiline
                  placeholder="Write a brief or paste your draft. Use task controls below to rewrite, polish, and optimize."
                  placeholderTextColor={colors.textMuted}
                  data-testid="smart-writing-studio-editor-input"
                  testID="smart-writing-studio-editor-input"
                />
                <View style={{ flexDirection: 'row', gap: 8, marginTop: 10 }}>
                  <TouchableOpacity style={[s.buttonSecondary, { flex: 1 }]} onPress={() => void handleSaveDraft()} disabled={saveLoading} data-testid="smart-writing-studio-save-draft-button" testID="smart-writing-studio-save-draft-button" accessibilityRole="button">
                    {saveLoading ? <ActivityIndicator size="small" color={colors.text} /> : <><Ionicons name="save-outline" size={16} color={colors.text} /><Text style={{ color: colors.text, fontWeight: '700' }}>Save Draft</Text></>}
                  </TouchableOpacity>
                  <TouchableOpacity style={[s.buttonPrimary, { flex: 1 }]} onPress={() => void runStudioTask()} disabled={runLoading} data-testid="smart-writing-studio-run-button" testID="smart-writing-studio-run-button" accessibilityRole="button">
                    {runLoading ? <ActivityIndicator size="small" color={colors.primaryText} /> : <><Ionicons name="sparkles-outline" size={16} color={colors.primaryText} /><Text style={{ color: colors.primaryText, fontWeight: '800' }}>Run Task</Text></>}
                  </TouchableOpacity>
                </View>
              </View>
            </View>
          </View>
        ) : (
          <>
            {renderDocumentList}
            <View style={s.card} data-testid="smart-writing-studio-editor-card" testID="smart-writing-studio-editor-card">
              <Text style={s.cardTitle}>Document Editor</Text>
              <TextInput
                style={[s.input, { marginBottom: 8 }]}
                value={activeDocument?.title || ''}
                onChangeText={(value) => setActiveDocument((prev) => (prev ? { ...prev, title: value } : prev))}
                placeholder="Document title"
                placeholderTextColor={colors.textMuted}
                data-testid="smart-writing-studio-doc-title-input"
                testID="smart-writing-studio-doc-title-input"
              />
              <TextInput
                style={[s.input, { minHeight: 180, textAlignVertical: 'top' }]}
                value={editorValue}
                onChangeText={setEditorValue}
                multiline
                placeholder="Write a brief or paste your draft."
                placeholderTextColor={colors.textMuted}
                data-testid="smart-writing-studio-editor-input"
                testID="smart-writing-studio-editor-input"
              />
              <View style={{ flexDirection: 'row', gap: 8, marginTop: 10 }}>
                <TouchableOpacity style={[s.buttonSecondary, { flex: 1 }]} onPress={() => void handleSaveDraft()} disabled={saveLoading} data-testid="smart-writing-studio-save-draft-button" testID="smart-writing-studio-save-draft-button" accessibilityRole="button">
                  {saveLoading ? <ActivityIndicator size="small" color={colors.text} /> : <><Ionicons name="save-outline" size={16} color={colors.text} /><Text style={{ color: colors.text, fontWeight: '700' }}>Save Draft</Text></>}
                </TouchableOpacity>
                <TouchableOpacity style={[s.buttonPrimary, { flex: 1 }]} onPress={() => void runStudioTask()} disabled={runLoading} data-testid="smart-writing-studio-run-button" testID="smart-writing-studio-run-button" accessibilityRole="button">
                  {runLoading ? <ActivityIndicator size="small" color={colors.primaryText} /> : <><Ionicons name="sparkles-outline" size={16} color={colors.primaryText} /><Text style={{ color: colors.primaryText, fontWeight: '800' }}>Run Task</Text></>}
                </TouchableOpacity>
              </View>
            </View>
          </>
        )}

        <View style={s.card} data-testid="smart-writing-studio-task-controls-card" testID="smart-writing-studio-task-controls-card">
          <Text style={s.cardTitle} data-testid="smart-writing-studio-task-controls-title" testID="smart-writing-studio-task-controls-title">Run Configuration</Text>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 8, paddingBottom: 6 }} data-testid="smart-writing-studio-task-scroll" testID="smart-writing-studio-task-scroll">
            {TASKS.map((item) => {
              const selected = item.id === task;
              return (
                <TouchableOpacity
                  key={item.id}
                  onPress={() => setTask(item.id)}
                  style={{
                    flexDirection: 'row',
                    alignItems: 'center',
                    gap: 6,
                    paddingHorizontal: 10,
                    paddingVertical: 8,
                    borderRadius: 999,
                    borderWidth: 1,
                    borderColor: selected ? colors.primary : colors.border,
                    backgroundColor: selected ? colors.primarySoft : colors.bg,
                  }}
                  data-testid={`smart-writing-studio-task-${item.id}`}
                  testID={`smart-writing-studio-task-${item.id}`}
                  accessibilityRole="button"
                >
                  <Ionicons name={item.icon} size={14} color={selected ? colors.primary : colors.textMuted} />
                  <Text style={{ color: selected ? colors.primary : colors.text, fontWeight: '700', fontSize: 12 }}>{item.label}</Text>
                </TouchableOpacity>
              );
            })}
          </ScrollView>

          <View style={{ gap: 8, marginTop: 10 }}>
            <TextInput
              value={audience}
              onChangeText={setAudience}
              style={s.input}
              placeholder="Audience (e.g., founders, marketing managers, students)"
              placeholderTextColor={colors.textMuted}
              data-testid="smart-writing-studio-audience-input"
              testID="smart-writing-studio-audience-input"
            />
            <TextInput
              value={readingLevel}
              onChangeText={setReadingLevel}
              style={s.input}
              placeholder="Reading level (general, professional, executive...)"
              placeholderTextColor={colors.textMuted}
              data-testid="smart-writing-studio-reading-level-input"
              testID="smart-writing-studio-reading-level-input"
            />
            <TextInput
              value={lengthTarget}
              onChangeText={setLengthTarget}
              style={s.input}
              placeholder="Length target (optional, e.g. 400 words)"
              placeholderTextColor={colors.textMuted}
              data-testid="smart-writing-studio-length-target-input"
              testID="smart-writing-studio-length-target-input"
            />

            <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 8 }} data-testid="smart-writing-studio-tone-scroll" testID="smart-writing-studio-tone-scroll">
              {TONES.map((toneItem) => {
                const selected = toneItem === tone;
                return (
                  <TouchableOpacity
                    key={toneItem}
                    onPress={() => setTone(toneItem)}
                    style={{
                      borderRadius: 999,
                      paddingHorizontal: 10,
                      paddingVertical: 7,
                      borderWidth: 1,
                      borderColor: selected ? colors.primary : colors.border,
                      backgroundColor: selected ? colors.primarySoft : colors.bg,
                    }}
                    data-testid={`smart-writing-studio-tone-${toneItem}`}
                    testID={`smart-writing-studio-tone-${toneItem}`}
                    accessibilityRole="button"
                  >
                    <Text style={{ color: selected ? colors.primary : colors.text, fontSize: 12, fontWeight: '700' }}>{toneItem}</Text>
                  </TouchableOpacity>
                );
              })}
            </ScrollView>
          </View>
        </View>

        <View style={s.card} data-testid="smart-writing-studio-templates-card" testID="smart-writing-studio-templates-card">
          <Text style={s.cardTitle} data-testid="smart-writing-studio-templates-title" testID="smart-writing-studio-templates-title">📑 Templates Library</Text>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 8, paddingBottom: 6 }} data-testid="smart-writing-studio-templates-scroll" testID="smart-writing-studio-templates-scroll">
            {templates.slice(0, 10).map((template) => {
              const selected = selectedTemplate?.id === template.id;
              return (
                <TouchableOpacity
                  key={template.id}
                  onPress={() => setSelectedTemplate(template)}
                  style={{
                    paddingHorizontal: 12,
                    paddingVertical: 8,
                    borderRadius: 10,
                    borderWidth: 1,
                    borderColor: selected ? colors.primary : colors.border,
                    backgroundColor: selected ? colors.primarySoft : colors.bg,
                    minWidth: 140,
                  }}
                  data-testid={`smart-writing-studio-template-${template.id}`}
                  testID={`smart-writing-studio-template-${template.id}`}
                  accessibilityRole="button"
                >
                  <Text style={{ color: selected ? colors.primary : colors.text, fontWeight: '700', fontSize: 12 }}>{template.name}</Text>
                  <Text style={{ color: colors.textMuted, fontSize: 10, marginTop: 2 }}>{template.category}</Text>
                </TouchableOpacity>
              );
            })}
          </ScrollView>
          {selectedTemplate ? (
            <View style={{ marginTop: 10, gap: 8 }}>
              <Text style={{ color: colors.textMuted, fontSize: 11 }}>{selectedTemplate.description}</Text>
              <TextInput
                value={templateTopic}
                onChangeText={setTemplateTopic}
                style={s.input}
                placeholder="Enter topic (e.g., New product launch, Quarterly earnings...)"
                placeholderTextColor={colors.textMuted}
                data-testid="smart-writing-studio-template-topic-input"
                testID="smart-writing-studio-template-topic-input"
              />
              <TouchableOpacity
                onPress={() => void applyTemplate()}
                style={[s.buttonSecondary]}
                disabled={templatesLoading || !templateTopic.trim()}
                data-testid="smart-writing-studio-apply-template-button"
                testID="smart-writing-studio-apply-template-button"
                accessibilityRole="button"
              >
                {templatesLoading ? <ActivityIndicator size="small" color={colors.text} /> : <><Ionicons name="document-text-outline" size={16} color={colors.text} /><Text style={{ color: colors.text, fontWeight: '700' }}>Apply Template</Text></>}
              </TouchableOpacity>
            </View>
          ) : (
            <Text style={{ color: colors.textMuted, fontSize: 11, marginTop: 8 }}>Select a template above to get started with professional writing structures.</Text>
          )}
        </View>

        <View style={s.card} data-testid="smart-writing-studio-export-card" testID="smart-writing-studio-export-card">
          <Text style={s.cardTitle} data-testid="smart-writing-studio-export-title" testID="smart-writing-studio-export-title">💾 Export Document</Text>
          <View style={{ flexDirection: 'row', gap: 8, flexWrap: 'wrap', marginBottom: 10 }}>
            {['txt', 'csv', 'pdf', 'docx'].map((format) => {
              const selected = exportFormat === format;
              return (
                <TouchableOpacity
                  key={format}
                  onPress={() => setExportFormat(format)}
                  style={{
                    paddingHorizontal: 12,
                    paddingVertical: 8,
                    borderRadius: 999,
                    borderWidth: 1,
                    borderColor: selected ? colors.primary : colors.border,
                    backgroundColor: selected ? colors.primarySoft : colors.bg,
                  }}
                  data-testid={`smart-writing-studio-export-format-${format}`}
                  testID={`smart-writing-studio-export-format-${format}`}
                  accessibilityRole="button"
                >
                  <Text style={{ color: selected ? colors.primary : colors.text, fontSize: 12, fontWeight: '700' }}>{format.toUpperCase()}</Text>
                </TouchableOpacity>
              );
            })}
          </View>
          <TouchableOpacity
            onPress={() => void handleExportDocument()}
            style={[s.buttonPrimary]}
            disabled={exportLoading || !activeDocument}
            data-testid="smart-writing-studio-export-button"
            testID="smart-writing-studio-export-button"
            accessibilityRole="button"
          >
            {exportLoading ? <ActivityIndicator size="small" color={colors.primaryText} /> : <><Ionicons name="download-outline" size={16} color={colors.primaryText} /><Text style={{ color: colors.primaryText, fontWeight: '800' }}>Export as {exportFormat.toUpperCase()}</Text></>}
          </TouchableOpacity>
          {!activeDocument ? (
            <Text style={{ color: colors.textMuted, fontSize: 11, marginTop: 8 }}>Create or select a document to enable export.</Text>
          ) : null}
        </View>

        <View style={s.card} data-testid="smart-writing-studio-brand-profile-card" testID="smart-writing-studio-brand-profile-card">
          <Text style={s.cardTitle} data-testid="smart-writing-studio-brand-profile-title" testID="smart-writing-studio-brand-profile-title">Brand Governance</Text>
          <TextInput
            value={brandProfile.brand_name}
            onChangeText={(value) => setBrandProfile((prev) => ({ ...prev, brand_name: value }))}
            style={[s.input, { marginBottom: 8 }]}
            placeholder="Brand name"
            placeholderTextColor={colors.textMuted}
            data-testid="smart-writing-studio-brand-name-input"
            testID="smart-writing-studio-brand-name-input"
          />
          <TextInput
            value={brandProfile.voice_summary}
            onChangeText={(value) => setBrandProfile((prev) => ({ ...prev, voice_summary: value }))}
            style={[s.input, { marginBottom: 8, minHeight: 80, textAlignVertical: 'top' }]}
            multiline
            placeholder="Voice summary (tone, personality, message discipline)"
            placeholderTextColor={colors.textMuted}
            data-testid="smart-writing-studio-brand-voice-input"
            testID="smart-writing-studio-brand-voice-input"
          />
          <TextInput
            value={preferredPhrasesInput}
            onChangeText={setPreferredPhrasesInput}
            style={[s.input, { marginBottom: 8 }]}
            placeholder="Preferred phrases (comma separated)"
            placeholderTextColor={colors.textMuted}
            data-testid="smart-writing-studio-preferred-phrases-input"
            testID="smart-writing-studio-preferred-phrases-input"
          />
          <TextInput
            value={doNotUseInput}
            onChangeText={setDoNotUseInput}
            style={s.input}
            placeholder="Do-not-use phrases (comma separated)"
            placeholderTextColor={colors.textMuted}
            data-testid="smart-writing-studio-do-not-use-input"
            testID="smart-writing-studio-do-not-use-input"
          />
          <TouchableOpacity
            onPress={() => void handleSaveBrandProfile()}
            style={[s.buttonSecondary, { marginTop: 10 }]}
            disabled={brandSaving}
            data-testid="smart-writing-studio-save-brand-button"
            testID="smart-writing-studio-save-brand-button"
            accessibilityRole="button"
          >
            {brandSaving ? <ActivityIndicator size="small" color={colors.text} /> : <><Ionicons name="shield-checkmark-outline" size={16} color={colors.text} /><Text style={{ color: colors.text, fontWeight: '700' }}>Save Brand Profile</Text></>}
          </TouchableOpacity>
        </View>

        <View style={s.card} data-testid="smart-writing-studio-versions-card" testID="smart-writing-studio-versions-card">
          <Text style={s.cardTitle} data-testid="smart-writing-studio-versions-title" testID="smart-writing-studio-versions-title">Version Timeline</Text>
          {versionRows.length === 0 ? (
            <Text style={{ color: colors.textMuted, fontSize: 12 }} data-testid="smart-writing-studio-empty-versions-message" testID="smart-writing-studio-empty-versions-message">No versions yet. Run a task to create tracked versions.</Text>
          ) : versionRows.map((version) => (
            <View key={version.version_id} style={{ borderWidth: 1, borderColor: colors.border, borderRadius: 10, padding: 10, marginBottom: 8 }} data-testid={`smart-writing-studio-version-row-${version.version_id}`} testID={`smart-writing-studio-version-row-${version.version_id}`}>
              <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
                <Text style={{ color: colors.text, fontSize: 12, fontWeight: '700' }}>{version.task}</Text>
                <TouchableOpacity
                  onPress={() => void handleRestoreVersion(version.version_id)}
                  style={{ paddingHorizontal: 8, paddingVertical: 6, borderWidth: 1, borderColor: colors.border, borderRadius: 8, backgroundColor: colors.bgSoft }}
                  data-testid={`smart-writing-studio-restore-version-${version.version_id}`}
                  testID={`smart-writing-studio-restore-version-${version.version_id}`}
                  accessibilityRole="button"
                >
                  <Text style={{ color: colors.text, fontSize: 11, fontWeight: '700' }}>Restore</Text>
                </TouchableOpacity>
              </View>
              <Text style={{ color: colors.textMuted, marginTop: 4, fontSize: 11 }}>
                {new Date(version.created_at).toLocaleString()} • quality {version.quality_scores?.overall ?? '--'}
              </Text>
            </View>
          ))}
        </View>

        {resultContent ? (
          <View style={s.card} data-testid="smart-writing-studio-result-card" testID="smart-writing-studio-result-card">
            <Text style={s.cardTitle} data-testid="smart-writing-studio-result-title" testID="smart-writing-studio-result-title">Generated Output</Text>
            <MarkdownDisplay content={resultContent} />
            <FeatureToolbar content={resultContent} featureKey="ai-writer" title={activeDocument?.title || 'Smart Writing Studio Output'} onClear={() => setResultContent('')} />
            <AIFeedbackBar feature="ai-writer" response={resultContent} />
          </View>
        ) : null}
      </ScrollView>
    </FeatureLayout>
  );
}