import React, { useEffect, useState, useRef, useCallback } from 'react';
// @gls-exempt — intentional fixed-width UI element (sidebar/chat/label/toast)
import {
  View, Text, ScrollView, TouchableOpacity, TextInput,
  ActivityIndicator, useWindowDimensions, Platform,
} from 'react-native';
// eslint-disable-next-line @typescript-eslint/no-unused-vars
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useRouter, useLocalSearchParams } from 'expo-router';
import { useAuth } from '../context/AuthContext';
import { useTheme } from '../context/ThemeContext';
import AppShell from './AppShell';
import api from '../services/api';
import { useManagedWebSocket } from '../hooks/useManagedWebSocket';
import { handleRecoverableError } from '../utils/handleRecoverableError';

const ACCENTS = { primary: 'var(--app-primary)', accent: 'var(--app-primary)', success: 'var(--app-success)', error: 'var(--app-error)', warning: 'var(--app-warning)' };

export function CollaborativeDocsContent() {
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const _router = useRouter();
  const params = useLocalSearchParams<{ docId?: string }>();
  const { user } = useAuth();
  const { colors } = useTheme();

  // @autofix-moved: was module-level const DOC_TYPES
  const DOC_TYPES = [
    { id: 'resume', label: 'Resume', icon: 'document-text', color: colors.primary },
    { id: 'job_description', label: 'Job Description', icon: 'briefcase', color: colors.accent },
    { id: 'cover_letter', label: 'Cover Letter', icon: 'mail', color: colors.successText },
    { id: 'general', label: 'General', icon: 'create', color: colors.warningText },
  ];
  const C = { bg: colors.bg, card: colors.card, text: colors.text, muted: colors.textMuted, border: colors.border, ...ACCENTS };
  const { width } = useWindowDimensions();
  const isWide = width >= 900;
  const uid = (user as any)?.user_id || '';

  const [view, setView] = useState<'list' | 'editor'>(params.docId ? 'editor' : 'list');
  const [docs, setDocs] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [currentDoc, setCurrentDoc] = useState<any>(null);
  const [content, setContent] = useState('');
  const [title, setTitle] = useState('');
  const [saving, setSaving] = useState(false);
  const [lastSaved, setLastSaved] = useState('');
  const [activeEditors, setActiveEditors] = useState<any[]>([]);
  const [versions, setVersions] = useState<any[]>([]);
  const [showVersions, setShowVersions] = useState(false);
  const [showNewDoc, setShowNewDoc] = useState(false);
  const [newDocType, setNewDocType] = useState('general');
  const [newDocTitle, setNewDocTitle] = useState('');
  const [showAiMenu, setShowAiMenu] = useState(false);
  const [aiLoading, setAiLoading] = useState(false);
  const [aiResult, setAiResult] = useState<string | null>(null);
  const [aiAction, setAiAction] = useState('');
  const [wsDocId, setWsDocId] = useState('');
  const [syncError, setSyncError] = useState('');
  const saveTimerRef = useRef<NodeJS.Timeout | null>(null);
  const contentRef = useRef('');

  // Load documents list
  const loadDocs = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.get('/collab-docs/');
      setDocs(res.data.documents || []);
      setSyncError('');
    } catch (error) {
      handleRecoverableError(error, {
        scope: 'collab-docs/load-list',
        fallbackMessage: 'Unable to load documents right now.',
        setMessage: setSyncError,
      });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadDocs(); }, [loadDocs]);

  // Open a document for editing
  const openDoc = useCallback(async (docId: string) => {
    try {
      const res = await api.get(`/collab-docs/${docId}`);
      setCurrentDoc(res.data);
      setContent(res.data.content || '');
      setTitle(res.data.title || '');
      setActiveEditors(res.data.active_editors || []);
      contentRef.current = res.data.content || '';
      setView('editor');
      connectWs(docId);
      loadVersions(docId);
      setSyncError('');
    } catch (error) {
      handleRecoverableError(error, {
        scope: 'collab-docs/open-doc',
        fallbackMessage: 'Unable to open this document.',
        setMessage: setSyncError,
      });
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [uid]);

  // Load if docId param is provided
  useEffect(() => {
    if (params.docId) openDoc(params.docId);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params.docId]);

  const loadVersions = async (docId: string) => {
    try {
      const res = await api.get(`/collab-docs/${docId}/versions`);
      setVersions(res.data.versions || []);
    } catch (error) {
      handleRecoverableError(error, {
        scope: 'collab-docs/load-versions',
        fallbackMessage: 'Version history is temporarily unavailable.',
        setMessage: setSyncError,
      });
    }
  };

  // Connect to collaborative editing WebSocket
  const connectWs = useCallback((docId: string) => {
    setWsDocId(docId);
    setSyncError('');
  }, []);

  const collabWsUrlBuilder = useCallback(() => {
    const backendUrl = typeof window !== 'undefined' && window.location?.host
      ? `https://${window.location.host}`
      : (process.env.REACT_APP_BACKEND_URL || '');
    return backendUrl.replace(/^https?/, 'wss') + `/api/ws/collab-doc/${wsDocId}/${uid}`;
  }, [uid, wsDocId]);

  const {
    socketRef: wsRef,
    connected: wsConnected,
    reconnectAttempt: wsReconnectAttempt,
    disconnectNow: disconnectDocWs,
  } = useManagedWebSocket({
    enabled: Boolean(view === 'editor' && wsDocId && uid),
    buildUrl: collabWsUrlBuilder,
    errorScope: 'collab-docs/ws',
    maxReconnectAttempts: 4,
    onReconnectAttempt: () => {
      setSyncError('Realtime collaboration reconnecting...');
    },
    onError: () => {
      setSyncError('Realtime collaboration connection issue. Reconnecting...');
    },
    onMessage: (event) => {
      if (event.data === 'pong') return;
      try {
        const data = JSON.parse(event.data);
        if (data.type === 'content_change' && data.user_id !== uid) {
          setContent(data.content);
          contentRef.current = data.content;
        } else if (data.type === 'title_change' && data.user_id !== uid) {
          setTitle(data.title);
        } else if (data.type === 'editor_joined') {
          setActiveEditors(prev => {
            if (prev.find((e: any) => e.user_id === data.user_id)) return prev;
            return [...prev, { user_id: data.user_id, name: data.name }];
          });
        } else if (data.type === 'editor_left') {
          setActiveEditors(prev => prev.filter((e: any) => e.user_id !== data.user_id));
        } else if (data.type === 'editors_list') {
          setActiveEditors(data.editors || []);
        } else if (data.type === 'cursor_update') {
          setActiveEditors(prev => prev.map((e: any) =>
            e.user_id === data.user_id ? { ...e, cursor: data.cursor } : e
          ));
        }
        setSyncError('');
      } catch (error) {
        handleRecoverableError(error, {
          scope: 'collab-docs/ws-parse',
          fallbackMessage: 'A live update could not be processed.',
          setMessage: setSyncError,
        });
      }
    },
  });

  // Broadcast content changes
  const onContentChange = (newContent: string) => {
    setContent(newContent);
    contentRef.current = newContent;
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'content_change', content: newContent }));
    }
    // Auto-save after 2 seconds of inactivity
    if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
    saveTimerRef.current = setTimeout(() => saveDoc(newContent), 2000);
  };

  const onTitleChange = (newTitle: string) => {
    setTitle(newTitle);
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'title_change', title: newTitle }));
    }
  };

  const saveDoc = async (contentToSave?: string) => {
    if (!currentDoc) return;
    setSaving(true);
    try {
      await api.put(`/collab-docs/${currentDoc.doc_id}`, {
        content: contentToSave || contentRef.current,
        title,
      });
      setLastSaved(new Date().toLocaleTimeString());
      loadVersions(currentDoc.doc_id);
      setSyncError('');
    } catch (error) {
      handleRecoverableError(error, {
        scope: 'collab-docs/save-doc',
        fallbackMessage: 'Failed to save document changes.',
        setMessage: setSyncError,
      });
    } finally {
      setSaving(false);
    }
  };

  const createDoc = async () => {
    if (!newDocTitle.trim()) return;
    try {
      const res = await api.post('/collab-docs/', {
        title: newDocTitle.trim(),
        doc_type: newDocType,
        content: '',
        is_public: false,
      });
      if (res.data?.document) {
        setShowNewDoc(false);
        setNewDocTitle('');
        openDoc(res.data.document.doc_id);
        loadDocs();
      }
      setSyncError('');
    } catch (error) {
      handleRecoverableError(error, {
        scope: 'collab-docs/create-doc',
        fallbackMessage: 'Could not create document.',
        setMessage: setSyncError,
      });
    }
  };

  const deleteDoc = async (docId: string) => {
    try {
      await api.delete(`/collab-docs/${docId}`);
      loadDocs();
      setSyncError('');
    } catch (error) {
      handleRecoverableError(error, {
        scope: 'collab-docs/delete-doc',
        fallbackMessage: 'Could not delete document.',
        setMessage: setSyncError,
      });
    }
  };

  const restoreVersion = async (version: any) => {
    if (!currentDoc) return;
    setContent(version.content);
    contentRef.current = version.content;
    onContentChange(version.content);
    setShowVersions(false);
  };

  const AI_ACTIONS = [
    { id: 'improve', label: 'Improve Writing', icon: 'sparkles', color: colors.purpleText, desc: 'Enhance clarity & professionalism' },
    { id: 'grammar', label: 'Fix Grammar', icon: 'checkmark-circle', color: colors.successText, desc: 'Correct spelling & grammar' },
    { id: 'summarize', label: 'Summarize', icon: 'contract', color: colors.primary, desc: 'Condense into key points' },
    { id: 'expand', label: 'Expand', icon: 'expand', color: colors.warningText, desc: 'Add detail & depth' },
    { id: 'generate_template', label: 'Generate Template', icon: 'document', color: 'var(--app-primary)', desc: 'Create a template for this doc type' }, // @theme-ok residual semantic hex (reviewed)
  ];

  const runAiAction = async (actionId: string) => {
    setAiLoading(true);
    setAiAction(actionId);
    setShowAiMenu(false);
    setAiResult(null);
    try {
      const res = await api.post('/collab-docs/ai-assist', {
        action: actionId,
        content: content,
        doc_type: currentDoc?.doc_type || 'general',
      });
      if (res.data?.result) {
        setAiResult(res.data.result);
      }
    // eslint-disable-next-line @typescript-eslint/no-unused-vars
    } catch (e: any) {
      setAiResult('AI processing failed. Please try again.');
    }
    setAiLoading(false);
  };

  const acceptAiResult = () => {
    if (aiResult && aiResult !== 'AI processing failed. Please try again.') {
      onContentChange(aiResult);
    }
    setAiResult(null);
    setAiAction('');
  };

  const dismissAiResult = () => {
    setAiResult(null);
    setAiAction('');
  };

  const backToList = () => {
    disconnectDocWs();
    setWsDocId('');
    setCurrentDoc(null);
    setView('list');
    loadDocs();
  };

  useEffect(() => {
    return () => {
      disconnectDocWs();
      if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
    };
  }, [disconnectDocWs]);

  // ── DOCUMENT LIST VIEW ──
  if (view === 'list') {
    return (
      <ScrollView contentContainerStyle={{ padding: 20, paddingBottom: 100, backgroundColor: colors.bg }} data-testid="collab-docs-page" testID="collab-docs-page">
          <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 20 }}>
            <View>
              <Text style={{ color: colors.text, fontSize: 22, fontWeight: '800' }} data-testid="collab-docs-title" testID="collab-docs-title">
                Collaborative Documents
              </Text>
              <Text style={{ color: colors.textMuted, fontSize: 13, marginTop: 4 }}>
                Co-edit resumes, job descriptions, and more in real-time
              </Text>
            </View>
            <TouchableOpacity onPress={() => setShowNewDoc(true)} data-testid="new-doc-btn" testID="new-doc-btn"
              style={{ flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: C.primary, paddingHorizontal: 16, paddingVertical: 10, borderRadius: 10 }}>
              <Ionicons name="add" size={18} color="var(--app-primary-text)" />
              <Text style={{ color: colors.primaryText, fontSize: 13, fontWeight: '700' }}>New Document</Text>
            </TouchableOpacity>
          </View>

          {!!syncError && (
            <View data-testid="collab-docs-error-banner" testID="collab-docs-error-banner" style={{ backgroundColor: colors.error + '14', borderWidth: 1, borderColor: colors.error + '45', borderRadius: 10, padding: 10, marginBottom: 14 }}>
              <Text data-testid="collab-docs-error-text" testID="collab-docs-error-text" style={{ color: colors.error, fontSize: 12, fontWeight: '600' }}>{syncError}</Text>
            </View>
          )}

          {/* New Document Modal */}
          {showNewDoc && (
            <View style={{ backgroundColor: colors.card, borderRadius: 16, padding: 20, marginBottom: 20, borderWidth: 1, borderColor: colors.border }} data-testid="new-doc-form" testID="new-doc-form">
              <Text style={{ color: colors.text, fontSize: 15, fontWeight: '700', marginBottom: 12 }}>Create New Document</Text>
              <TextInput value={newDocTitle} onChangeText={setNewDocTitle} placeholder="Document title..."
                placeholderTextColor={C.muted} data-testid="new-doc-title-input" testID="new-doc-title-input"
                style={{ backgroundColor: C.bg, color: C.text, borderRadius: 10, padding: 12, fontSize: 14, borderWidth: 1, borderColor: C.border, marginBottom: 12 }} />
              <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginBottom: 16 }}>
                {DOC_TYPES.map(dt => (
                  <TouchableOpacity key={dt.id} onPress={() => setNewDocType(dt.id)} data-testid={`doctype-${dt.id}`} testID={`doctype-${dt.id}`}
                    style={{
                      flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 12, paddingVertical: 8, borderRadius: 8,
                      backgroundColor: newDocType === dt.id ? (globalThis as any).__alphaColor(dt.color, '20') : colors.bg,
                      borderWidth: 1, borderColor: newDocType === dt.id ? dt.color : colors.border,
                    }}>
                    <Ionicons name={dt.icon as any} size={14} color={newDocType === dt.id ? dt.color : C.muted} />
                    <Text style={{ color: newDocType === dt.id ? dt.color : C.muted, fontSize: 12, fontWeight: '600' }}>{dt.label}</Text>
                  </TouchableOpacity>
                ))}
              </View>
              <View style={{ flexDirection: 'row', gap: 8 }}>
                <TouchableOpacity onPress={createDoc} data-testid="create-doc-btn" testID="create-doc-btn"
                  style={{ flex: 1, backgroundColor: C.primary, borderRadius: 10, paddingVertical: 12, alignItems: 'center' }}>
                  <Text style={{ color: colors.primaryText, fontSize: 13, fontWeight: '700' }}>Create</Text>
                </TouchableOpacity>
                <TouchableOpacity onPress={() => setShowNewDoc(false)} data-testid="cancel-new-doc-btn" testID="cancel-new-doc-btn"
                  style={{ flex: 1, backgroundColor: colors.bg, borderRadius: 10, paddingVertical: 12, alignItems: 'center', borderWidth: 1, borderColor: colors.border }}>
                  <Text style={{ color: C.muted, fontSize: 13, fontWeight: '600' }}>Cancel</Text>
                </TouchableOpacity>
              </View>
            </View>
          )}

          {/* Documents Grid */}
          {loading ? (
            <ActivityIndicator style={{ padding: 40 }} color={C.primary} />
          ) : docs.length === 0 ? (
            <View style={{ backgroundColor: colors.card, borderRadius: 16, padding: 40, alignItems: 'center', borderWidth: 1, borderColor: colors.border }}>
              <Ionicons name="documents-outline" size={48} color={C.muted} />
              <Text style={{ color: C.muted, fontSize: 15, marginTop: 12 }}>No documents yet</Text>
              <Text style={{ color: C.muted, fontSize: 12, marginTop: 4 }}>Create your first collaborative document</Text>
            </View>
          ) : (
            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 12 }}>
              {docs.map(doc => {
                const dtype = DOC_TYPES.find(d => d.id === doc.doc_type) || DOC_TYPES[3];
                return (
                  <TouchableOpacity key={doc.doc_id} onPress={() => openDoc(doc.doc_id)} data-testid={`doc-card-${doc.doc_id}`} testID={`doc-card-${doc.doc_id}`}
                    style={{
                      width: isWide ? 'calc(33.33% - 8px)' as any : '100%',
                      backgroundColor: colors.card, borderRadius: 14, padding: 16,
                      borderWidth: 1, borderColor: colors.border, borderLeftWidth: 3, borderLeftColor: dtype.color,
                    }}>
                    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 10 }}>
                      <View style={{ width: 32, height: 32, borderRadius: 8, backgroundColor: (globalThis as any).__alphaColor(dtype.color, '15'), alignItems: 'center', justifyContent: 'center' }}>
                        <Ionicons name={dtype.icon as any} size={16} color={dtype.color} />
                      </View>
                      <View style={{ flex: 1 }}>
                        <Text style={{ color: colors.text, fontSize: 14, fontWeight: '700' }} numberOfLines={1}>{doc.title}</Text>
                        <Text style={{ color: C.muted, fontSize: 10 }}>{dtype.label} | v{doc.version}</Text>
                      </View>
                      {doc.owner_id === uid && (
                        <TouchableOpacity onPress={(e) => { e.stopPropagation(); deleteDoc(doc.doc_id); }} data-testid={`delete-doc-${doc.doc_id}`} testID={`delete-doc-${doc.doc_id}`}>
                          <Ionicons name="trash-outline" size={16} color={C.error} />
                        </TouchableOpacity>
                      )}
                    </View>
                    <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
                      <Text style={{ color: C.muted, fontSize: 10 }}>by {doc.owner_name}</Text>
                      <Text style={{ color: C.muted, fontSize: 10 }}>{doc.updated_at ? new Date(doc.updated_at).toLocaleDateString() : ''}</Text>
                    </View>
                    {doc.collaborators?.length > 0 && (
                      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4, marginTop: 8 }}>
                        <Ionicons name="people" size={12} color={C.accent} />
                        <Text style={{ color: C.accent, fontSize: 10 }}>{doc.collaborators.length} collaborator(s)</Text>
                      </View>
                    )}
                  </TouchableOpacity>
                );
              })}
            </View>
          )}
        </ScrollView>
    );
  }

  // ── DOCUMENT EDITOR VIEW ──
  return (
    <View style={{ flex: 1, backgroundColor: colors.bg }} data-testid="doc-editor-page" testID="doc-editor-page">
        {/* Editor Header */}
        <View style={{
          flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
          paddingHorizontal: 16, paddingVertical: 10, backgroundColor: colors.card,
          borderBottomWidth: 1, borderBottomColor: colors.border,
        }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
            <TouchableOpacity onPress={backToList} data-testid="back-to-docs" testID="back-to-docs">
              <Ionicons name="arrow-back" size={20} color={colors.text} />
            </TouchableOpacity>
            <TextInput value={title} onChangeText={onTitleChange} data-testid="doc-title-input" testID="doc-title-input"
              style={{ color: colors.text, fontSize: 16, fontWeight: '700', minWidth: 200, padding: 4 }}
              placeholder="Document title..." placeholderTextColor={C.muted} />
          </View>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
            {/* Active editors */}
            {activeEditors.filter(e => e.user_id !== uid).map(e => (
              <View key={e.user_id} style={{
                backgroundColor: (globalThis as any).__alphaColor(C.accent, '20'), paddingHorizontal: 8, paddingVertical: 3, borderRadius: 12,
                flexDirection: 'row', alignItems: 'center', gap: 4,
              }}>
                <View style={{ width: 6, height: 6, borderRadius: 3, backgroundColor: C.success }} />
                <Text style={{ color: C.accent, fontSize: 10, fontWeight: '600' }}>{e.name}</Text>
              </View>
            ))}
            {/* Save status */}
            {saving ? (
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}>
                <ActivityIndicator size="small" color={C.primary} />
                <Text style={{ color: C.muted, fontSize: 10 }}>Saving...</Text>
              </View>
            ) : lastSaved ? (
              <Text style={{ color: C.successText, fontSize: 10 }}>Saved {lastSaved}</Text>
            ) : null}
            <TouchableOpacity onPress={() => saveDoc()} data-testid="save-doc-btn" testID="save-doc-btn"
              style={{ paddingHorizontal: 12, paddingVertical: 6, borderRadius: 8, backgroundColor: C.primary }}>
              <Text style={{ color: colors.primaryText, fontSize: 12, fontWeight: '700' }}>Save</Text>
            </TouchableOpacity>
            <View data-testid="collab-docs-ws-status" testID="collab-docs-ws-status" style={{ flexDirection: 'row', alignItems: 'center', gap: 5, paddingHorizontal: 8, paddingVertical: 4, borderRadius: 999, backgroundColor: wsConnected ? (globalThis as any).__alphaColor(colors.success, '18') : (globalThis as any).__alphaColor(colors.error, '18') }}>
              <View style={{ width: 6, height: 6, borderRadius: 3, backgroundColor: wsConnected ? colors.success : colors.error }} />
              <Text style={{ color: wsConnected ? colors.successText : colors.error, fontSize: 10, fontWeight: '700' }}>
                {wsConnected ? 'Live' : wsReconnectAttempt > 0 ? `Reconnecting ${wsReconnectAttempt}` : 'Offline'}
              </Text>
            </View>
            <View style={{ position: 'relative' }}>
              <TouchableOpacity onPress={() => setShowAiMenu(!showAiMenu)} data-testid="ai-assist-btn" testID="ai-assist-btn"
                style={{
                  flexDirection: 'row', alignItems: 'center', gap: 4,
                  paddingHorizontal: 10, paddingVertical: 6, borderRadius: 8,
                  backgroundColor: showAiMenu ? colors.purple : colors.purpleSoft,
                  borderWidth: 1, borderColor: colors.purple,
                }}>
                {aiLoading ? (
                  <ActivityIndicator size="small" color={colors.purpleText} />
                ) : (
                  <Ionicons name="sparkles" size={14} color={showAiMenu ? 'var(--app-primary-text)' : colors.purple} />
                )}
                <Text style={{ color: showAiMenu ? 'var(--app-primary-text)' : colors.purple, fontSize: 11, fontWeight: '700' }}>AI Assist</Text>
              </TouchableOpacity>
              {showAiMenu && (
                <View data-testid="ai-menu-dropdown" testID="ai-menu-dropdown" style={{
                  position: 'absolute', top: 38, right: 0, zIndex: 999,
                  backgroundColor: colors.card, borderRadius: 12, padding: 6,
                  borderWidth: 1, borderColor: colors.border, width: 220,
                  ...(Platform.OS === 'web' ? { boxShadow: '0 4px 12px rgba(0,0,0,0.3)' } : { shadowColor: 'var(--app-text)', shadowOffset: { width: 0, height: 4 }, shadowOpacity: 0.3, shadowRadius: 12 }),
                }}>
                  {AI_ACTIONS.map(a => (
                    <TouchableOpacity key={a.id} onPress={() => runAiAction(a.id)} data-testid={`ai-action-${a.id}`} testID={`ai-action-${a.id}`}
                      style={{
                        flexDirection: 'row', alignItems: 'center', gap: 8,
                        padding: 10, borderRadius: 8,
                      }}>
                      <View style={{ width: 28, height: 28, borderRadius: 7, backgroundColor: (globalThis as any).__alphaColor(a.color, '15'), alignItems: 'center', justifyContent: 'center' }}>
                        <Ionicons name={a.icon as any} size={14} color={a.color} />
                      </View>
                      <View style={{ flex: 1 }}>
                        <Text style={{ color: colors.text, fontSize: 12, fontWeight: '600' }}>{a.label}</Text>
                        <Text style={{ color: C.muted, fontSize: 9 }}>{a.desc}</Text>
                      </View>
                    </TouchableOpacity>
                  ))}
                </View>
              )}
            </View>
            <TouchableOpacity onPress={() => setShowVersions(!showVersions)} data-testid="toggle-versions-btn" testID="toggle-versions-btn"
              style={{ paddingHorizontal: 10, paddingVertical: 6, borderRadius: 8, backgroundColor: showVersions ? (globalThis as any).__alphaColor(C.accent, '20') : colors.bg, borderWidth: 1, borderColor: colors.border }}>
              <Ionicons name="time" size={16} color={showVersions ? C.accent : C.muted} />
            </TouchableOpacity>
          </View>
        </View>

        {/* Editor + Versions Panel */}
        <View style={{ flex: 1, flexDirection: 'row' }}>
          {/* Main Editor */}
          <View style={{ flex: 1, padding: 16 }}>
            {!!syncError && (
              <View data-testid="collab-docs-error-banner-editor" testID="collab-docs-error-banner-editor" style={{ backgroundColor: colors.error + '14', borderWidth: 1, borderColor: colors.error + '45', borderRadius: 10, padding: 10, marginBottom: 10 }}>
                <Text data-testid="collab-docs-error-text-editor" testID="collab-docs-error-text-editor" style={{ color: colors.error, fontSize: 12, fontWeight: '600' }}>{syncError}</Text>
              </View>
            )}
            {/* Formatting hints */}
            <View style={{ flexDirection: 'row', gap: 8, marginBottom: 10, flexWrap: 'wrap' }}>
              {currentDoc?.doc_type && (
                <View style={{ backgroundColor: (globalThis as any).__alphaColor((DOC_TYPES.find(d => d.id === currentDoc.doc_type)?.color || C.primary), '15'), paddingHorizontal: 8, paddingVertical: 3, borderRadius: 6 }}>
                  <Text style={{ color: DOC_TYPES.find(d => d.id === currentDoc.doc_type)?.color || C.primary, fontSize: 10, fontWeight: '600' }}>
                    {DOC_TYPES.find(d => d.id === currentDoc.doc_type)?.label || 'Document'}
                  </Text>
                </View>
              )}
              <View style={{ backgroundColor: C.border, paddingHorizontal: 8, paddingVertical: 3, borderRadius: 6 }}>
                <Text style={{ color: C.muted, fontSize: 10 }}>v{currentDoc?.version || 1}</Text>
              </View>
              <View style={{ backgroundColor: (globalThis as any).__alphaColor(C.success, '15'), paddingHorizontal: 8, paddingVertical: 3, borderRadius: 6, flexDirection: 'row', alignItems: 'center', gap: 3 }}>
                <View style={{ width: 5, height: 5, borderRadius: 2.5, backgroundColor: C.success }} />
                <Text style={{ color: C.successText, fontSize: 10 }}>{activeEditors.length} online</Text>
              </View>
            </View>

            {/* AI Result Preview */}
            {(aiLoading || aiResult) && (
              <View data-testid="ai-result-panel" testID="ai-result-panel" style={{
                backgroundColor: colors.purpleSoft, borderRadius: 12, padding: 14, marginBottom: 10,
                borderWidth: 1, borderColor: colors.purpleSoft,
              }}>
                <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                    <Ionicons name="sparkles" size={14} color={colors.purpleText} />
                    <Text style={{ color: colors.purpleText, fontSize: 12, fontWeight: '700' }}>
                      AI {AI_ACTIONS.find(a => a.id === aiAction)?.label || 'Assist'}
                    </Text>
                  </View>
                  {aiLoading && <ActivityIndicator size="small" color={colors.purpleText} />}
                </View>
                {aiLoading ? (
                  <Text style={{ color: C.muted, fontSize: 12, fontStyle: 'italic' }}>
                    Processing your content with AI...
                  </Text>
                ) : aiResult ? (
                  <>
                    <ScrollView style={{ maxHeight: 200, marginBottom: 10 }}>
                      <Text style={{ color: colors.text, fontSize: 13, lineHeight: 20 }} selectable>{aiResult}</Text>
                    </ScrollView>
                    <View style={{ flexDirection: 'row', gap: 8 }}>
                      <TouchableOpacity onPress={acceptAiResult} data-testid="ai-accept-btn" testID="ai-accept-btn"
                        style={{ flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 4, backgroundColor: C.success, paddingVertical: 8, borderRadius: 8 }}>
                        <Ionicons name="checkmark" size={14} color="var(--app-primary-text)" />
                        <Text style={{ color: colors.primaryText, fontSize: 12, fontWeight: '700' }}>Accept</Text>
                      </TouchableOpacity>
                      <TouchableOpacity onPress={dismissAiResult} data-testid="ai-dismiss-btn" testID="ai-dismiss-btn"
                        style={{ flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 4, backgroundColor: colors.bg, paddingVertical: 8, borderRadius: 8, borderWidth: 1, borderColor: colors.border }}>
                        <Ionicons name="close" size={14} color={C.muted} />
                        <Text style={{ color: C.muted, fontSize: 12, fontWeight: '600' }}>Dismiss</Text>
                      </TouchableOpacity>
                    </View>
                  </>
                ) : null}
              </View>
            )}

            <TextInput accessibilityLabel="Start writing your document here...\n\nTip: Other collaborators will see your changes in real-time."
              value={content}
              onChangeText={onContentChange}
              multiline
              data-testid="doc-content-editor" testID="doc-content-editor"
              placeholder="Start writing your document here...\n\nTip: Other collaborators will see your changes in real-time."
              placeholderTextColor={C.muted}
              style={{
                flex: 1, backgroundColor: colors.card, color: colors.text,
                borderRadius: 12, padding: 20, fontSize: 14, lineHeight: 22,
                borderWidth: 1, borderColor: colors.border,
                textAlignVertical: 'top', minHeight: 400,
                fontFamily: 'monospace',
              }}
            />
          </View>

          {/* Version History Panel */}
          {showVersions && (
            <View style={{
              width: isWide ? 280 : '100%', backgroundColor: colors.card,
              borderLeftWidth: 1, borderLeftColor: colors.border, padding: 14,
            }} data-testid="versions-panel" testID="versions-panel">
              <Text style={{ color: colors.text, fontSize: 14, fontWeight: '700', marginBottom: 12 }}>Version History</Text>
              <ScrollView style={{ flex: 1 }}>
                {versions.length === 0 ? (
                  <Text style={{ color: C.muted, fontSize: 12 }}>No versions yet</Text>
                ) : (
                  versions.map((v, i) => (
                    <TouchableOpacity key={v.version_id} onPress={() => restoreVersion(v)} data-testid={`version-${v.version}`} testID={`version-${v.version}`}
                      style={{
                        padding: 10, marginBottom: 6, borderRadius: 8,
                        backgroundColor: i === 0 ? (globalThis as any).__alphaColor(C.primary, '10') : colors.bg,
                        borderWidth: 1, borderColor: i === 0 ? (globalThis as any).__alphaColor(C.primary, '30') : colors.border,
                      }}>
                      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
                        <Text style={{ color: colors.text, fontSize: 12, fontWeight: '600' }}>v{v.version}</Text>
                        {i === 0 && <Text style={{ color: C.primary, fontSize: 9, fontWeight: '700' }}>CURRENT</Text>}
                      </View>
                      <Text style={{ color: C.muted, fontSize: 10, marginTop: 3 }}>by {v.editor_name}</Text>
                      <Text style={{ color: C.muted, fontSize: 9, marginTop: 2 }}>
                        {v.created_at ? new Date(v.created_at).toLocaleString() : ''}
                      </Text>
                    </TouchableOpacity>
                  ))
                )}
              </ScrollView>
            </View>
          )}
        </View>
      </View>
  );
}

export default function CollaborativeDocsPage() {
  return (
    <AppShell>
      <CollaborativeDocsContent />
    </AppShell>
  );
}

/* i18n-probe t('i18n.auto.probe') */
