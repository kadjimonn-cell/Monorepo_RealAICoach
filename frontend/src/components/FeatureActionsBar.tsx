import React, { useState, useMemo, useCallback } from 'react';
import { View, Text, TouchableOpacity, Alert, Share, Platform, Modal, ScrollView, TextInput, ActivityIndicator } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { useTheme } from '../context/ThemeContext';
import { useAuth } from '../context/AuthContext';
import { useAccessControl } from '../context/AccessControlContext';
import api from '../services/api';
import { useLiveQuery } from '../hooks/useLiveQuery';
import { useFocusTrap } from '../hooks/useFocusTrap';
import { handleAppRecoverableError } from '../utils/appRecoverableError';

interface FeatureActionsBarProps {
  featureKey: string;
  content?: string;
  title?: string;
}

export default function FeatureActionsBar({ featureKey, content = '', title = '' }: FeatureActionsBarProps) {
  const { colors } = useTheme();

  // @autofix-moved: was module-level const EXPORT_FORMATS
  const EXPORT_FORMATS = [
    { id: 'txt', icon: 'document-text', color: colors.successText, label: 'TXT', desc: 'Plain text file', tier: 'basic' },
    { id: 'csv', icon: 'grid', color: colors.primary, label: 'CSV', desc: 'Spreadsheet data', tier: 'basic' },
    { id: 'pdf', icon: 'document', color: colors.error, label: 'PDF', desc: 'Formatted report', tier: 'premium' },
    { id: 'docx', icon: 'reader', color: colors.accent, label: 'DOCX', desc: 'Word document', tier: 'premium' },
  ];
  const { user } = useAuth();
  const { effectivePlan } = useAccessControl();
  const router = useRouter();

  const [showExportModal, setShowExportModal] = useState(false);
  const [showScheduleModal, setShowScheduleModal] = useState(false);
  const [showHistoryModal, setShowHistoryModal] = useState(false);
  const [showShareModal, setShowShareModal] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [history, setHistory] = useState<any[]>([]);
  const [historyTotal, setHistoryTotal] = useState(0);
  const [historyPage, setHistoryPage] = useState(0);
  const [historySearch, setHistorySearch] = useState('');
  const [historyLoading, setHistoryLoading] = useState(false);
  const [scheduleDate, setScheduleDate] = useState('');
  const [scheduleType, setScheduleType] = useState('once');
  const [scheduling, setScheduling] = useState(false);
  const [saving, setSaving] = useState(false);
  const [sharing, setSharing] = useState(false);
  const [shareLink, setShareLink] = useState('');
  const [shareExpiry, setShareExpiry] = useState('');
  const [toast, setToast] = useState('');

  // Focus trap for modals
  const { setRef: shareModalRef } = useFocusTrap(showShareModal, () => setShowShareModal(false));
  const { setRef: exportModalRef } = useFocusTrap(showExportModal, () => setShowExportModal(false));
  const { setRef: scheduleModalRef } = useFocusTrap(showScheduleModal, () => setShowScheduleModal(false));
  const { setRef: historyModalRef } = useFocusTrap(showHistoryModal, () => setShowHistoryModal(false));

  const plan = effectivePlan || 'free';
  const isPrivileged = !!(user?.full_access || user?.is_admin);
  const isPremium = isPrivileged || plan === 'premium';
  const isBasicPlus = isPrivileged || plan === 'basic' || plan === 'premium';

  // Real-time action status via useLiveQuery
  const { data: liveStatus } = useLiveQuery(
    user?.user_id ? `/actions/history/${user.user_id}?feature_key=${featureKey}&limit=5&skip=0` : '',
    { entity: 'actions', pollInterval: 60000, skip: !user?.user_id }
  );
  const recentActionCount = liveStatus?.total ?? 0;

  const C = useMemo(() => ({
    ...colors,
    bg: colors.bg,
    bgSoft: colors.bgSoft,
    card: colors.card,
    text: colors.text,
    textSec: colors.textSec,
    textMuted: colors.textMuted,
    border: colors.border,
    primary: colors.primary,
    primaryText: colors.primaryText,
    success: colors.success,
    successSoft: colors.successSoft,
    warning: colors.warning,
    error: colors.error,
  }), [colors]);

  const showToast = (msg: string) => {
    setToast(msg);
    setTimeout(() => setToast(''), 2500);
  };

  const logAction = useCallback(async (action: string, details?: any) => {
    if (!user) return;
    try { await api.post('/actions/log', { user_id: user.user_id, feature_key: featureKey, action, details }); } catch (error) { handleAppRecoverableError({ scope: 'src/components/FeatureActionsBar.tsx#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
  }, [user, featureKey]);

  if (featureKey === 'ai-video') return null;

  const showUpgrade = (action: string) => {
    Alert.alert('Subscription Required', `${action} requires a Basic or Premium subscription.`,
      [{ text: 'Not Now', style: 'cancel' }, { text: 'View Plans', onPress: () => router.push('/subscription/plans') }]);
  };

  // ═══ PREDICTIONS ═══
  const handlePredictions = async () => {
    logAction('predictions');
    showToast('AI analyzing patterns...');
  };

  // ═══ AUTOMATE ═══
  const handleAutomation = () => {
    if (!isBasicPlus) { showUpgrade('Automation'); return; }
    logAction('automation');
    setShowScheduleModal(true);
  };

  // ═══ SHARE ═══
  const handleShare = async () => {
    if (!user) { Alert.alert('Login Required', 'Please login to share content'); return; }
    logAction('share');
    setSharing(true);
    setShareLink('');
    setShareExpiry('');
    setShowShareModal(true);
    try {
      const shareContent = content || `Check out ${title || featureKey} on RealAICoach!`;
      const res = await api.post('/share/create', {
        user_id: user.user_id,
        feature_key: featureKey,
        content: shareContent,
        title: title || featureKey,
        expires_in_hours: 72,
      });
      const baseUrl = Platform.OS === 'web' && typeof window !== 'undefined'
        ? (`https://${window.location.host}`)
        : 'https://realaicoach.app';
      const link = `${baseUrl}/shared/${res.data.token}`;
      setShareLink(link);
      setShareExpiry(res.data.expires_at);
    } catch {
      Alert.alert('Error', 'Failed to generate share link');
      setShowShareModal(false);
    } finally {
      setSharing(false);
    }
  };

  const copyShareLink = async () => {
    if (!shareLink) return;
    if (Platform.OS === 'web' && navigator.clipboard) {
      await navigator.clipboard.writeText(shareLink);
      showToast('Share link copied!');
    }
  };

  const nativeShare = async () => {
    if (!shareLink) return;
    if (Platform.OS === 'web' && navigator.share) {
      try {
        await navigator.share({ title: title || featureKey, text: `Check out ${title || featureKey} on RealAICoach`, url: shareLink });
      } catch (error) { handleAppRecoverableError({ scope: 'src/components/FeatureActionsBar.tsx#catch2', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
    } else {
      try { await Share.share({ message: shareLink, title: title || featureKey }); } catch (error) { handleAppRecoverableError({ scope: 'src/components/FeatureActionsBar.tsx#catch3', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
    }
  };

  // ═══ COPY ═══
  const handleCopy = async () => {
    logAction('copy');
    const text = content || (typeof window !== 'undefined' ? window.location.href : featureKey);
    if (Platform.OS === 'web' && navigator.clipboard) {
      await navigator.clipboard.writeText(text);
      showToast('Copied to clipboard!');
    }
  };

  // ═══ SAVE ═══
  const handleSave = async () => {
    if (!user) { Alert.alert('Login Required', 'Please login to save content'); return; }
    setSaving(true);
    try {
      await api.post('/content/save-generated', { user_id: user.user_id, content: content || `${featureKey} saved`, feature_key: featureKey, title: title || 'Saved from Actions' });
      logAction('save');
      showToast('Saved successfully!');
    } catch { Alert.alert('Error', 'Failed to save'); }
    finally { setSaving(false); }
  };

  // ═══ NEW TAB ═══
  const handleNewTab = () => {
    logAction('newtab');
    if (Platform.OS === 'web' && typeof window !== 'undefined') window.open(window.location.href, '_blank');
    showToast('Opened in new tab');
  };

  // ═══ EXPORT ═══
  const doExport = async (format: string) => {
    const allowedFormats = isPremium ? ['txt', 'csv', 'pdf', 'docx'] : isBasicPlus ? ['txt', 'csv'] : [];
    if (!allowedFormats.includes(format)) { showUpgrade(`Export as ${format.toUpperCase()}`); return; }
    setExporting(true);
    logAction('export', { format });
    try {
      if (Platform.OS === 'web' && typeof window !== 'undefined') {
        const mimeMap: Record<string, string> = { csv: 'text/csv', pdf: 'application/pdf', txt: 'text/plain', docx: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' };
        const resp = await api.post('/actions/export', { content: content || `No content for ${featureKey}`, format, title: title || featureKey, feature_key: featureKey }, { responseType: 'blob' });
        const blob = new Blob([resp.data], { type: mimeMap[format] || 'application/octet-stream' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a'); a.href = url; a.download = `${featureKey}_export.${format}`; a.click();
        URL.revokeObjectURL(url);
      }
      showToast(`${format.toUpperCase()} exported!`);
    } catch { Alert.alert('Error', 'Export failed'); }
    finally { setExporting(false); setShowExportModal(false); }
  };

  // ═══ PRINT ═══
  const handlePrint = () => {
    if (!isPremium) { showUpgrade('Print'); return; }
    logAction('print');
    if (Platform.OS === 'web' && typeof window !== 'undefined') {
      const printContent = content || document.body.innerText;
      const printWindow = window.open('', '_blank');
      if (printWindow) {
        printWindow.document.write(`<!DOCTYPE html><html><head><title>${title || featureKey}</title>
          <style>body{font-family:system-ui,sans-serif;padding:40px;color:var(--app-primary);line-height:1.7;max-width:800px;margin:0 auto}
          h1{color:var(--app-primary);border-bottom:2px solid var(--app-primary);padding-bottom:8px;font-size:24px}
          .meta{color:var(--app-primary);font-size:12px;margin-bottom:24px;border-bottom:1px solid var(--app-primary);padding-bottom:8px}
          .content{white-space:pre-wrap;font-size:14px}
          .footer{margin-top:40px;color:var(--app-text-muted);font-size:10px;text-align:center;border-top:1px solid var(--app-primary);padding-top:12px}
          @media print{body{padding:20px}}</style></head>
          <body><h1>${title || featureKey}</h1>
          <div class="meta">RealAICoach | ${new Date().toLocaleString()}</div>
          <div class="content">${printContent.replace(/\n/g, '<br>')}</div>
          <div class="footer">Generated by RealAICoach - AI Coaching Platform</div></body></html>`);
        printWindow.document.close();
        setTimeout(() => printWindow.print(), 300);
      }
    }
    showToast('Print dialog opened');
  };

  // ═══ HISTORY ═══
  const loadHistory = async (page = 0, search = '') => {
    if (!user) return;
    setHistoryLoading(true);
    try {
      const params = new URLSearchParams({ feature_key: featureKey, limit: '20', skip: String(page * 20) });
      if (search) params.append('search', search);
      const r = await api.get(`/actions/history/${user.user_id}?${params}`);
      setHistory(r.data.history || []);
      setHistoryTotal(r.data.total || 0);
    } catch (error) { handleAppRecoverableError({ scope: 'src/components/FeatureActionsBar.tsx#catch4', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); } finally { setHistoryLoading(false); }
  };

  const deleteHistoryItem = async (actionId: string) => {
    try {
      await api.delete(`/actions/history/${actionId}`);
      setHistory(h => h.filter(i => i.action_id !== actionId));
      setHistoryTotal(t => t - 1);
      showToast('Deleted');
    } catch { Alert.alert('Error', 'Failed to delete'); }
  };

  const exportHistory = async () => {
    if (!user) return;
    try {
      const resp = await api.post('/actions/export-history', { user_id: user.user_id }, { responseType: 'blob' });
      if (Platform.OS === 'web') {
        const blob = new Blob([resp.data], { type: 'text/csv' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a'); a.href = url; a.download = 'action_history.csv'; a.click();
        URL.revokeObjectURL(url);
        showToast('History exported!');
      }
    } catch { Alert.alert('Error', 'Export failed'); }
  };

  const handleSchedule = async () => {
    if (!user || !scheduleDate) { Alert.alert('Error', 'Please enter a date'); return; }
    setScheduling(true);
    try {
      await api.post('/actions/schedule', { user_id: user.user_id, feature_key: featureKey, action: 'automation', schedule_type: scheduleType, scheduled_at: scheduleDate });
      logAction('schedule', { schedule_type: scheduleType, scheduled_at: scheduleDate });
      showToast(`Scheduled (${scheduleType})!`);
      setShowScheduleModal(false);
    } catch { Alert.alert('Error', 'Scheduling failed'); }
    finally { setScheduling(false); }
  };

  const actions = [
    { id: 'predictions', icon: 'analytics', label: 'Predictions', color: C.primary, onPress: handlePredictions },
    { id: 'automation', icon: 'time', label: 'Automate', color: C.warningText, locked: !isBasicPlus, onPress: handleAutomation },
    { id: 'share', icon: 'share-social', label: 'Share', color: C.primary, onPress: handleShare },
    { id: 'copy', icon: 'copy', label: 'Copy', color: colors.cyan, onPress: handleCopy },
    { id: 'save', icon: 'bookmark', label: saving ? 'Saving...' : 'Save', color: C.successText, onPress: handleSave },
    { id: 'newtab', icon: 'open-outline', label: 'New Tab', color: colors.cyan, onPress: handleNewTab },
    { id: 'export', icon: 'download-outline', label: 'Export', color: C.successText, locked: !isBasicPlus, onPress: () => setShowExportModal(true) },
    { id: 'print', icon: 'print', label: 'Print', color: C.primary, locked: !isPremium, onPress: handlePrint },
    { id: 'history', icon: 'time-outline', label: 'History', color: colors.textMuted, onPress: () => { setShowHistoryModal(true); setHistoryPage(0); loadHistory(0, ''); } },
  ];

  const iconColor = (color: string, locked?: boolean) => locked ? C.textMuted : color;

  return (
    <View style={{ paddingVertical: 16, borderTopWidth: 1, borderTopColor: C.border, backgroundColor: C.bg, marginTop: 16 }} data-testid="feature-actions-bar" testID="feature-actions-bar" accessibilityRole="toolbar">
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 10 }}>
        <Text style={{ fontSize: 12, fontWeight: '700', color: C.textMuted, textTransform: 'uppercase', letterSpacing: 0.5 }}>Actions</Text>
        {recentActionCount > 0 && (
          <View style={{ backgroundColor: (globalThis as any).__alphaColor(C.primary, '15'), borderRadius: 10, paddingHorizontal: 7, paddingVertical: 2 }} data-testid="action-count-badge" testID="action-count-badge">
            <Text style={{ fontSize: 9, fontWeight: '700', color: C.primary }}>{recentActionCount} recent</Text>
          </View>
        )}
      </View>
      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 8, paddingRight: 16 }}>
        {actions.map(a => (
          <TouchableOpacity key={a.id} onPress={a.onPress} activeOpacity={0.7}
            style={{ flexDirection: 'row', alignItems: 'center', gap: 5, paddingHorizontal: 14, paddingVertical: 10, borderRadius: 10,
              backgroundColor: (globalThis as any).__alphaColor(a.locked ? C.bgSoft : a.color, '10'), borderWidth: 1, borderColor: (globalThis as any).__alphaColor(a.locked ? C.border : a.color, '25'),
              minHeight: 40 }}
            data-testid={`action-${a.id}`} testID={`action-${a.id}`}
            accessibilityRole="button"
            accessibilityLabel={`${a.label} action`}>
            <Ionicons name={a.icon as any} size={15} color={iconColor(a.color, a.locked)} />
            <Text style={{ fontSize: 12, fontWeight: '600', color: iconColor(a.color, a.locked) }}>{a.label}</Text>
            {a.locked && <Ionicons name="lock-closed" size={10} color={C.textMuted} />}
          </TouchableOpacity>
        ))}
      </ScrollView>

      {/* Toast */}
      {toast !== '' && (
        <View style={{ position: 'absolute', top: -40, left: 0, right: 0, backgroundColor: C.success, borderRadius: 10, paddingVertical: 10, paddingHorizontal: 16, flexDirection: 'row', alignItems: 'center', gap: 8, zIndex: 999 }} data-testid="toast-message" testID="toast-message">
          <Ionicons name="checkmark-circle" size={16} color="var(--app-primary-text)" />
          <Text style={{ color: colors.primaryText, fontSize: 13, fontWeight: '600', flex: 1 }}>{toast}</Text>
        </View>
      )}

      {/* Share Modal */}
      <Modal visible={showShareModal} transparent animationType="fade" onRequestClose={() => setShowShareModal(false)}>
        <View style={{ flex: 1, backgroundColor: colors.overlay, justifyContent: 'center', alignItems: 'center', padding: 20 }}>
          <View ref={shareModalRef} role="dialog" aria-modal={true} style={{ backgroundColor: C.card, borderRadius: 16, padding: 24, width: '100%', maxWidth: 420, borderWidth: 1, borderColor: C.border }}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 16 }}>
              <View style={{ width: 40, height: 40, borderRadius: 12, backgroundColor: (globalThis as any).__alphaColor(C.primary, '15'), alignItems: 'center', justifyContent: 'center' }}>
                <Ionicons name="share-social" size={20} color={C.primary} />
              </View>
              <View style={{ flex: 1 }}>
                <Text style={{ color: C.text, fontSize: 16, fontWeight: '800' }} data-testid="share-modal-title" testID="share-modal-title">Share Content</Text>
                <Text style={{ color: C.textMuted, fontSize: 11 }}>Generate a secure link with 72h expiration</Text>
              </View>
              <TouchableOpacity onPress={() => setShowShareModal(false)} data-testid="share-modal-close" testID="share-modal-close">
                <Ionicons name="close" size={22} color={C.textMuted} />
              </TouchableOpacity>
            </View>

            {sharing ? (
              <View style={{ alignItems: 'center', paddingVertical: 30 }}>
                <ActivityIndicator color={C.primary} size="large" />
                <Text style={{ color: C.textMuted, fontSize: 13, marginTop: 12 }}>Generating secure link...</Text>
              </View>
            ) : shareLink ? (
              <View style={{ gap: 12 }}>
                <View style={{ backgroundColor: C.bgSoft, borderRadius: 10, padding: 12, borderWidth: 1, borderColor: C.border }}>
                  <Text style={{ color: C.text, fontSize: 12, fontFamily: 'monospace' }} selectable data-testid="share-link-text" testID="share-link-text">{shareLink}</Text>
                </View>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                  <Ionicons name="time-outline" size={13} color={C.textMuted} />
                  <Text style={{ color: C.textMuted, fontSize: 11 }}>
                    Expires: {shareExpiry ? new Date(shareExpiry).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric', hour: '2-digit', minute: '2-digit' }) : '72 hours'}
                  </Text>
                </View>
                <View style={{ flexDirection: 'row', gap: 10, marginTop: 4 }}>
                  <TouchableOpacity onPress={copyShareLink}
                    style={{ flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, paddingVertical: 12, borderRadius: 10, backgroundColor: C.primary }}
                    data-testid="share-copy-btn" testID="share-copy-btn" accessibilityRole="button">
                    <Ionicons name="copy" size={16} color={C.primaryText} />
                    <Text style={{ color: C.primaryText, fontSize: 13, fontWeight: '700' }}>Copy Link</Text>
                  </TouchableOpacity>
                  <TouchableOpacity onPress={nativeShare}
                    style={{ flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, paddingVertical: 12, borderRadius: 10, backgroundColor: C.bgSoft, borderWidth: 1, borderColor: C.border }}
                    data-testid="share-native-btn" testID="share-native-btn" accessibilityRole="button">
                    <Ionicons name="share-outline" size={16} color={C.text} />
                    <Text style={{ color: C.text, fontSize: 13, fontWeight: '700' }}>Share</Text>
                  </TouchableOpacity>
                </View>
              </View>
            ) : null}
          </View>
        </View>
      </Modal>

      {/* Export Modal */}
      <Modal visible={showExportModal} transparent animationType="fade" onRequestClose={() => setShowExportModal(false)}>
        <View style={{ flex: 1, backgroundColor: colors.overlay, justifyContent: 'center', alignItems: 'center', padding: 20 }}>
          <View ref={exportModalRef} role="dialog" aria-modal={true} style={{ backgroundColor: C.card, borderRadius: 16, padding: 24, width: '100%', maxWidth: 400, borderWidth: 1, borderColor: C.border }}>
            <Text style={{ color: C.text, fontSize: 16, fontWeight: '800', marginBottom: 4 }} data-testid="export-modal-title" testID="export-modal-title">Export Content</Text>
            <Text style={{ color: C.textMuted, fontSize: 12, marginBottom: 16 }}>Choose format to download</Text>
            {exporting ? <ActivityIndicator color={C.primary} style={{ marginVertical: 20 }} /> : (
              <View style={{ gap: 8 }}>
                {EXPORT_FORMATS.map(f => {
                  const locked = f.tier === 'premium' ? !isPremium : f.tier === 'basic' ? !isBasicPlus : false;
                  return (
                    <TouchableOpacity key={f.id} onPress={() => locked ? showUpgrade(`${f.label} export`) : doExport(f.id)} data-testid={`export-${f.id}-btn`} testID={`export-${f.id}-btn`}
                      accessibilityRole="button"
                      style={{ flexDirection: 'row', alignItems: 'center', gap: 10, padding: 14, backgroundColor: C.bgSoft, borderRadius: 12, borderWidth: 1, borderColor: C.border, opacity: locked ? 0.5 : 1 }}>
                      <View style={{ width: 36, height: 36, borderRadius: 10, backgroundColor: (globalThis as any).__alphaColor(f.color, '15'), alignItems: 'center', justifyContent: 'center' }}>
                        <Ionicons name={f.icon as any} size={18} color={f.color} />
                      </View>
                      <View style={{ flex: 1 }}>
                        <Text style={{ color: C.text, fontSize: 13, fontWeight: '700' }}>{f.label}</Text>
                        <Text style={{ color: C.textMuted, fontSize: 10 }}>{f.desc}</Text>
                      </View>
                      {locked && <Ionicons name="lock-closed" size={14} color={C.textMuted} />}
                    </TouchableOpacity>
                  );
                })}
              </View>
            )}
            <TouchableOpacity onPress={() => setShowExportModal(false)} style={{ marginTop: 12, alignItems: 'center', paddingVertical: 10 }} data-testid="export-cancel-btn" testID="export-cancel-btn" accessibilityRole="button">
              <Text style={{ color: C.textMuted, fontSize: 13 }}>Cancel</Text>
            </TouchableOpacity>
          </View>
        </View>
      </Modal>

      {/* Schedule Modal */}
      <Modal visible={showScheduleModal} transparent animationType="fade" onRequestClose={() => setShowScheduleModal(false)}>
        <View style={{ flex: 1, backgroundColor: colors.overlay, justifyContent: 'center', alignItems: 'center', padding: 20 }}>
          <View ref={scheduleModalRef} role="dialog" aria-modal={true} style={{ backgroundColor: C.card, borderRadius: 16, padding: 24, width: '100%', maxWidth: 360, borderWidth: 1, borderColor: C.border }}>
            <Text style={{ color: C.text, fontSize: 16, fontWeight: '800', marginBottom: 4 }}>Schedule Automation</Text>
            <Text style={{ color: C.textMuted, fontSize: 12, marginBottom: 16 }}>Set when this task should run</Text>
            <View style={{ flexDirection: 'row', gap: 6, marginBottom: 12 }}>
              {['once', 'daily', 'weekly', 'monthly'].map(t => (
                <TouchableOpacity key={t} onPress={() => setScheduleType(t)} data-testid={`schedule-${t}`} testID={`schedule-${t}`} accessibilityRole="button"
                  style={{ flex: 1, paddingVertical: 8, borderRadius: 8, backgroundColor: scheduleType === t ? C.primary : C.bgSoft, alignItems: 'center', borderWidth: 1, borderColor: scheduleType === t ? C.primary : C.border }}>
                  <Text style={{ color: scheduleType === t ? 'var(--app-primary-text)' : C.textMuted, fontSize: 10, fontWeight: '700', textTransform: 'capitalize' }}>{t}</Text>
                </TouchableOpacity>
              ))}
            </View>
            <TextInput value={scheduleDate} onChangeText={setScheduleDate} placeholder="YYYY-MM-DD HH:MM" placeholderTextColor={C.textMuted}
              style={{ backgroundColor: C.bgSoft, borderRadius: 10, padding: 12, color: C.text, fontSize: 14, borderWidth: 1, borderColor: C.border, marginBottom: 16 }}
              data-testid="schedule-date-input" testID="schedule-date-input" />
            <View style={{ flexDirection: 'row', gap: 10 }}>
              <TouchableOpacity onPress={() => setShowScheduleModal(false)} style={{ flex: 1, paddingVertical: 12, borderRadius: 10, backgroundColor: C.bgSoft, alignItems: 'center' }} accessibilityRole="button">
                <Text style={{ color: C.textMuted, fontSize: 13, fontWeight: '600' }}>Cancel</Text>
              </TouchableOpacity>
              <TouchableOpacity onPress={handleSchedule} disabled={scheduling} data-testid="schedule-confirm-btn" testID="schedule-confirm-btn" accessibilityRole="button"
                style={{ flex: 1, paddingVertical: 12, borderRadius: 10, backgroundColor: C.warning, alignItems: 'center' }}>
                {scheduling ? <ActivityIndicator color="var(--app-primary-text)" size="small" /> : <Text style={{ color: colors.primaryText, fontSize: 13, fontWeight: '700' }}>Schedule</Text>}
              </TouchableOpacity>
            </View>
          </View>
        </View>
      </Modal>

      {/* History Modal */}
      <Modal visible={showHistoryModal} transparent animationType="slide" onRequestClose={() => setShowHistoryModal(false)}>
        <View style={{ flex: 1, backgroundColor: colors.overlay, justifyContent: 'flex-end' }}>
          <View ref={historyModalRef} role="dialog" aria-modal={true} style={{ backgroundColor: C.card, borderTopLeftRadius: 20, borderTopRightRadius: 20, padding: 20, maxHeight: '80%' }}>
            <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
              <Text style={{ color: C.text, fontSize: 16, fontWeight: '800' }}>Action History</Text>
              <View style={{ flexDirection: 'row', gap: 10 }}>
                <TouchableOpacity onPress={exportHistory} data-testid="history-export-btn" testID="history-export-btn" accessibilityRole="button" style={{ paddingHorizontal: 10, paddingVertical: 6, borderRadius: 8, backgroundColor: C.successSoft }}>
                  <Text style={{ color: C.successText, fontSize: 11, fontWeight: '700' }}>Export</Text>
                </TouchableOpacity>
                <TouchableOpacity onPress={() => setShowHistoryModal(false)} data-testid="history-close-btn" testID="history-close-btn" accessibilityRole="button">
                  <Ionicons name="close-circle" size={24} color={C.textMuted} />
                </TouchableOpacity>
              </View>
            </View>

            {/* Search */}
            <View style={{ flexDirection: 'row', alignItems: 'center', backgroundColor: C.bgSoft, borderRadius: 10, paddingHorizontal: 12, height: 38, borderWidth: 1, borderColor: C.border, marginBottom: 10 }}>
              <Ionicons name="search" size={14} color={C.textMuted} />
              <TextInput
                style={{ flex: 1, color: C.text, marginLeft: 8, fontSize: 13 }}
                placeholder="Search actions..."
                placeholderTextColor={C.textMuted}
                value={historySearch}
                onChangeText={t => { setHistorySearch(t); loadHistory(0, t); }}
                data-testid="history-search-input" testID="history-search-input"
              />
            </View>

            <Text style={{ color: C.textMuted, fontSize: 11, marginBottom: 8 }}>{historyTotal} total actions</Text>

            <ScrollView style={{ maxHeight: 400 }}>
              {historyLoading ? <ActivityIndicator color={C.primary} style={{ marginTop: 20 }} /> : history.length === 0 ? (
                <View style={{ alignItems: 'center', paddingVertical: 30 }}>
                  <Ionicons name="time-outline" size={32} color={C.textMuted} />
                  <Text style={{ color: C.textMuted, fontSize: 13, marginTop: 8 }}>No actions yet</Text>
                </View>
              ) : history.map((h: any) => {
                const icons: Record<string, string> = { predictions: 'analytics', automation: 'time', share: 'share-social', export: 'download', print: 'print', copy: 'copy', save: 'bookmark', schedule: 'calendar', newtab: 'open-outline' };
                const actionColors: Record<string, string> = { predictions: C.primary, automation: C.warning, share: C.primary, export: C.success, print: C.primary, copy: colors.cyan, save: C.success, schedule: C.warning, newtab: colors.cyan };
                return (
                  <View key={h.action_id} style={{ flexDirection: 'row', alignItems: 'center', gap: 10, paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: C.border }} data-testid={`history-item-${h.action_id}`} testID={`history-item-${h.action_id}`}>
                    <View style={{ width: 32, height: 32, borderRadius: 16, backgroundColor: (globalThis as any).__alphaColor((actionColors[h.action] || 'var(--app-text-muted)'), '20'), alignItems: 'center', justifyContent: 'center' }}>
                      <Ionicons name={(icons[h.action] || 'ellipse') as any} size={14} color={actionColors[h.action] || 'var(--app-text-muted)'} />
                    </View>
                    <View style={{ flex: 1 }}>
                      <Text style={{ color: C.text, fontSize: 12, fontWeight: '600', textTransform: 'capitalize' }}>{h.action?.replace('_', ' ')}</Text>
                      <Text style={{ color: C.textMuted, fontSize: 9 }}>{h.timestamp?.slice(0, 16).replace('T', ' ')}</Text>
                    </View>
                    <TouchableOpacity onPress={() => deleteHistoryItem(h.action_id)} data-testid={`history-delete-${h.action_id}`} testID={`history-delete-${h.action_id}`} accessibilityRole="button" style={{ padding: 6 }}>
                      <Ionicons name="trash-outline" size={14} color={C.error} />
                    </TouchableOpacity>
                  </View>
                );
              })}
            </ScrollView>

            {/* Pagination */}
            {historyTotal > 20 && (
              <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 16, marginTop: 12 }}>
                <TouchableOpacity disabled={historyPage <= 0} onPress={() => { setHistoryPage(p => p - 1); loadHistory(historyPage - 1, historySearch); }} style={{ opacity: historyPage <= 0 ? 0.3 : 1 }} accessibilityRole="button">
                  <Ionicons name="chevron-back" size={20} color={C.text} />
                </TouchableOpacity>
                <Text style={{ color: C.textSec, fontSize: 12, fontWeight: '600' }}>
                  Page {historyPage + 1} of {Math.ceil(historyTotal / 20)}
                </Text>
                <TouchableOpacity disabled={(historyPage + 1) * 20 >= historyTotal} onPress={() => { setHistoryPage(p => p + 1); loadHistory(historyPage + 1, historySearch); }} style={{ opacity: (historyPage + 1) * 20 >= historyTotal ? 0.3 : 1 }} accessibilityRole="button">
                  <Ionicons name="chevron-forward" size={20} color={C.text} />
                </TouchableOpacity>
              </View>
            )}
          </View>
        </View>
      </Modal>
    </View>
  );
}

/* i18n-probe t('i18n.auto.probe') */
