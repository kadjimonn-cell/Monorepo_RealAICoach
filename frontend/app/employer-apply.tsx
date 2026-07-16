import React, { useEffect, useState, useCallback, useRef } from 'react';
import { View, Text, ScrollView, TextInput, TouchableOpacity, ActivityIndicator, Platform } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import AppShell from '@/src/components/AppShell';
import { useAuth } from '@/src/context/AuthContext';
import { useTheme } from '@/src/context/ThemeContext';
import api from '@/src/services/api';
import { useAutoRefresh } from '../src/hooks/useAutoRefresh';
import { CareerSkeleton } from '../src/components/SkeletonLoaders';
import { useTranslation } from '../src/hooks/useTranslation';
import { EmployerPipelineBoard } from '../src/components/jobs/EmployerPipelineBoard';
import { EmployerKpiHeader } from '../src/components/jobs/EmployerKpiHeader';
import { handleAppRecoverableError } from '../src/utils/appRecoverableError';

const INDUSTRIES = [
  'Technology', 'Finance', 'Healthcare', 'Education', 'Retail', 'Manufacturing',
  'Agriculture', 'Energy', 'Construction', 'Transportation', 'Telecommunications',
  'Media', 'Hospitality', 'Legal', 'Consulting', 'Real Estate', 'Non-Profit', 'Other',
];

const STEPS = [
  { key: 'identity', label: 'Business Identity', icon: 'business' },
  { key: 'contact', label: 'Contact Info', icon: 'person' },
  { key: 'profile', label: 'Profile', icon: 'document-text' },
  { key: 'review', label: 'Review & Submit', icon: 'checkmark-done' },
];

type KycUploadResponse = {
  success: boolean;
  document: {
    document_key: string;
    doc_id: string;
    filename: string;
    original_filename: string;
    content_type: string;
    file_size: number;
    storage_path: string;
  };
};

async function uploadEmployerDocument(
  file: File,
  documentKey: 'business_registration' | 'id_front' | 'id_back',
): Promise<KycUploadResponse> {
  const allowed = ['application/pdf', 'image/jpeg', 'image/png', 'image/webp'];
  const normalizedType = file.type === 'image/jpg' ? 'image/jpeg' : file.type;
  if (!allowed.includes(normalizedType)) {
    throw new Error('Invalid file type. Allowed: PDF, JPG, PNG, WebP');
  }
  if (file.size > 10 * 1024 * 1024) {
    throw new Error('File too large. Maximum: 10MB');
  }
  if (file.size < 1024) {
    throw new Error('File too small or empty');
  }

  const formData = new FormData();
  formData.append('document_type', documentKey);
  formData.append('document_role', 'employer_application');
  formData.append('file', file);

  const response = await fetch(`${process.env.REACT_APP_BACKEND_URL}/api/employer/upload-document`, {
    method: 'POST',
    body: formData,
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Upload failed' }));
    throw new Error(error.detail || 'Upload failed');
  }

  return await response.json();
}


/* ─── Stepper ─── */
function Stepper({ step, colors, darkMode }: { step: number; colors: any; darkMode: boolean }) {
  const accent = colors.primary;
  return (
    <View style={{ flexDirection: 'row', alignItems: 'center', paddingVertical: 24, paddingHorizontal: 4 }} data-testid="employer-stepper" testID="employer-stepper">
      {STEPS.map((s, i) => {
        const isActive = i === step;
        const isDone = i < step;
        const stepColor = isDone ? colors.success : isActive ? accent: colors.border;
        return (
          <React.Fragment key={s.key}>
            {i > 0 && (
              <View style={{ flex: 1, height: 2, backgroundColor: isDone ? colors.success : colors.border, marginHorizontal: 4 }} />
            )}
            <View style={{ alignItems: 'center', minWidth: 70 }}>
              <View style={{
                width: 40, height: 40, borderRadius: 20,
                backgroundColor: isDone ? colors.success : isActive ? accent : 'transparent',
                borderWidth: isDone || isActive ? 0 : 2, borderColor: stepColor,
                alignItems: 'center', justifyContent: 'center',
              }}>
                {isDone ? (
                  <Ionicons name="checkmark" size={20} color={colors.primaryText} />
                ) : (
                  <Ionicons name={s.icon as any} size={18} color={isActive ? colors.primaryText: colors.textSec} />
                )}
              </View>
              <Text style={{
                color: isDone ? colors.success : isActive ? accent: colors.textSec,
                fontSize: 10, fontWeight: isActive ? '700' : '500', marginTop: 6, textAlign: 'center',
              }}>{s.label}</Text>
            </View>
          </React.Fragment>
        );
      })}
    </View>
  );
}

/* ─── Field ─── */
function Field({ label, value, setter, placeholder, testId, multiline, colors, darkMode: _darkMode, required }: any) {
  return (
    <View style={{ marginBottom: 16 }}>
      <Text style={{ color: colors.textSec, fontSize: 13, fontWeight: '600', marginBottom: 6 }}>
        {label}{required && <Text style={{ color: colors.error }}> *</Text>}
      </Text>
      <TextInput
        value={value} onChangeText={setter} placeholder={placeholder}
        placeholderTextColor={colors.placeholder}
        multiline={multiline} numberOfLines={multiline ? 3 : 1}
        data-testid={testId} testID={testId}
        style={{
          backgroundColor: colors.input, color: colors.inputText,
          borderRadius: 10, padding: 14, paddingTop: multiline ? 14 : undefined,
          fontSize: 15, borderWidth: 1, borderColor: colors.inputBorder,
          minHeight: multiline ? 90 : 48, textAlignVertical: multiline ? 'top' : 'center',
        }}
      />
    </View>
  );
}

/* ─── Industry Picker ─── */
function IndustryPicker({ value, onChange, colors, darkMode }: any) {
  const { t } = useTranslation();
  const accent = colors.primary;
  return (
    <View style={{ marginBottom: 16 }}>
      <Text style={{ color: colors.textSec, fontSize: 13, fontWeight: '600', marginBottom: 8 }}>{t("jobPlatform.employer.industry")}<Text style={{ color: colors.error }}> *</Text>
      </Text>
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
        {INDUSTRIES.map(ind => {
          const sel = value === ind;
          return (
            <TouchableOpacity key={ind} onPress={() => onChange(ind)} data-testid={`emp-industry-${ind}`} testID={`emp-industry-${ind}`}
              style={{
                paddingVertical: 8, paddingHorizontal: 14, borderRadius: 8,
                backgroundColor: sel ? accent : 'transparent',
                borderWidth: 1, borderColor: sel ? accent: colors.border,
              }}>
              <Text style={{ color: sel ? colors.primaryText: colors.textSec, fontSize: 13, fontWeight: '600' }}>{ind}</Text>
            </TouchableOpacity>
          );
        })}
      </View>
    </View>
  );
}

function RequiredAttachmentField({
  title,
  subtitle,
  testId,
  value,
  onPick,
  onCapture,
  onClear,
  error,
  colors,
  allowCapture,
}: {
  title: string;
  subtitle: string;
  testId: string;
  value: KycUploadDraft | null;
  onPick: () => void;
  onCapture?: () => void;
  onClear: () => void;
  error?: string;
  colors: any;
  allowCapture?: boolean;
}) {
  const { t } = useTranslation();
  return (
    <View style={{ marginBottom: 16 }} data-testid={`${testId}-field`} testID={`${testId}-field`}>
      <Text style={{ color: colors.textSec, fontSize: 13, fontWeight: '600', marginBottom: 8 }}>
        {title}<Text style={{ color: colors.error }}> *</Text>
      </Text>
      <View style={{ backgroundColor: colors.card, borderRadius: 12, borderWidth: 1, borderColor: value ? colors.success : colors.border, padding: 12 }}>
        <Text style={{ color: colors.textSec, fontSize: 11, marginBottom: 8 }}>{subtitle}</Text>
        {value ? (
          <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 10 }}>
            <View style={{ flex: 1 }}>
              <Text style={{ color: colors.text, fontSize: 13, fontWeight: '700' }} numberOfLines={1} data-testid={`${testId}-name`} testID={`${testId}-name`}>
                {value.filename}
              </Text>
              <Text style={{ color: colors.textSec, fontSize: 11 }} data-testid={`${testId}-meta`} testID={`${testId}-meta`}>
                {(value.file_size / 1024).toFixed(0)}{t("autofix.watchSweep1.kb")}{value.content_type}
              </Text>
            </View>
            <TouchableOpacity
              onPress={onClear}
              style={{ backgroundColor: (globalThis as any).__alphaColor(colors.error, '20'), borderWidth: 1, borderColor: (globalThis as any).__alphaColor(colors.error, '30'), borderRadius: 8, paddingHorizontal: 10, paddingVertical: 7 }}
              data-testid={`${testId}-clear-btn`}
              testID={`${testId}-clear-btn`}
            >
              <Text style={{ color: colors.error, fontSize: 11, fontWeight: '700' }}>{t("securityDashboard.knownDevices.actions.remove")}</Text>
            </TouchableOpacity>
          </View>
        ) : (
          <View style={{ flexDirection: 'row', gap: 8, flexWrap: 'wrap' }}>
            <TouchableOpacity
              onPress={onPick}
              style={{ backgroundColor: (globalThis as any).__alphaColor(colors.primary, '15'), borderWidth: 1, borderColor: (globalThis as any).__alphaColor(colors.primary, '30'), borderRadius: 8, paddingHorizontal: 12, paddingVertical: 8, flexDirection: 'row', alignItems: 'center', gap: 6 }}
              data-testid={`${testId}-upload-btn`}
              testID={`${testId}-upload-btn`}
            >
              <Ionicons name="cloud-upload" size={14} color={colors.primary} />
              <Text style={{ color: colors.primary, fontSize: 12, fontWeight: '700' }}>{t("autofix.watchSweep1.upload.file")}</Text>
            </TouchableOpacity>
            {allowCapture && !!onCapture && (
              <TouchableOpacity
                onPress={onCapture}
                style={{ backgroundColor: (globalThis as any).__alphaColor(colors.accent, '15'), borderWidth: 1, borderColor: (globalThis as any).__alphaColor(colors.accent, '30'), borderRadius: 8, paddingHorizontal: 12, paddingVertical: 8, flexDirection: 'row', alignItems: 'center', gap: 6 }}
                data-testid={`${testId}-capture-btn`}
                testID={`${testId}-capture-btn`}
              >
                <Ionicons name="camera" size={14} color={colors.accent} />
                <Text style={{ color: colors.accent, fontSize: 12, fontWeight: '700' }}>{t("autofix.precision12.take.photo")}</Text>
              </TouchableOpacity>
            )}
          </View>
        )}
      </View>
      {!!error && <Text style={{ color: colors.error, fontSize: 12, marginTop: 6 }}>{error}</Text>}
    </View>
  );
}

/* ─── Document Upload ─── */
function DocumentUpload({ employerId, documents, onRefresh, colors, darkMode }: any) {
  const { t } = useTranslation();
  const [uploading, setUploading] = useState(false);
  const [downloadingDocId, setDownloadingDocId] = useState('');
  const [docType, setDocType] = useState('business_license');
  const fileRef = useRef<HTMLInputElement>(null);
  const accent = colors.primary;

  const DOC_TYPES = [
    { key: 'business_license', label: 'Business License', icon: 'document' },
    { key: 'tax_certificate', label: 'Tax Certificate', icon: 'receipt' },
    { key: 'registration_proof', label: 'Registration Proof', icon: 'ribbon' },
    { key: 'id_document', label: 'ID Document', icon: 'card' },
    { key: 'other', label: 'Other', icon: 'attach' },
  ];

  const handleUpload = async (file: File) => {
    setUploading(true);
    try {
      const formData = new FormData();
      formData.append('file', file);
      formData.append('document_type', docType);
      await api.post('/hiring/v2/employer/application/upload-document', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      onRefresh();
    } catch (e: any) {
      alert(e?.response?.data?.detail || 'Upload failed');
    }
    setUploading(false);
  };

  const handleDownload = async (doc: any) => {
    if (!employerId || !doc?.doc_id) return;
    setDownloadingDocId(String(doc.doc_id));
    try {
      const res = await api.get(`/employers/documents/${employerId}/${doc.doc_id}/download`, { responseType: 'blob' as any });
      if (Platform.OS === 'web' && typeof window !== 'undefined') {
        const blob = res.data instanceof Blob ? res.data : new Blob([res.data], { type: doc.content_type || 'application/octet-stream' });
        const url = window.URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = doc.original_filename || doc.filename || `${doc.doc_id}`;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        window.URL.revokeObjectURL(url);
      }
    } catch (e: any) {
      alert(e?.response?.data?.detail || 'Failed to download document');
    } finally {
      setDownloadingDocId('');
    }
  };

  return (
    <View data-testid="employer-docs-section" testID="employer-docs-section">
      {documents.length > 0 && (
        <View style={{ gap: 8, marginBottom: 20 }}>
          <Text style={{ color: colors.textSec, fontSize: 13, fontWeight: '600', marginBottom: 4 }}>{t("autofix.watchSweep1.uploaded.documents")}</Text>
          {documents.map((doc: any) => (
            <View key={doc.doc_id} style={{
              flexDirection: 'row', alignItems: 'center', gap: 12,
              backgroundColor: colors.card, borderRadius: 10, padding: 14,
              borderWidth: 1, borderColor: colors.border,
            }}>
              <View style={{ width: 36, height: 36, borderRadius: 8, backgroundColor: (globalThis as any).__alphaColor(colors.success, '15'), alignItems: 'center', justifyContent: 'center' }}>
                <Ionicons name={doc.content_type?.includes('pdf') ? 'document-text' : 'image'} size={18} color={colors.success} />
              </View>
              <View style={{ flex: 1 }}>
                <Text style={{ color: colors.text, fontSize: 14, fontWeight: '600' }}>{doc.type?.replace(/_/g, ' ')}</Text>
                <Text style={{ color: colors.textSec, fontSize: 12 }}>{doc.filename} · {(doc.file_size / 1024).toFixed(0)} KB</Text>
              </View>
              <TouchableOpacity
                onPress={() => handleDownload(doc)}
                disabled={downloadingDocId === String(doc.doc_id)}
                style={{ backgroundColor: (globalThis as any).__alphaColor(accent, '15'), borderRadius: 6, paddingHorizontal: 10, paddingVertical: 7, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(accent, '30') }}
                data-testid={`employer-doc-download-${doc.doc_id}`}
                testID={`employer-doc-download-${doc.doc_id}`}
              >
                {downloadingDocId === String(doc.doc_id) ? (
                  <ActivityIndicator size="small" color={accent} />
                ) : (
                  <Text style={{ color: accent, fontSize: 11, fontWeight: '700' }}>{t("autofix.precision12.download")}</Text>
                )}
              </TouchableOpacity>
            </View>
          ))}
        </View>
      )}

      <Text style={{ color: colors.textSec, fontSize: 13, fontWeight: '600', marginBottom: 8 }}>{t("autofix.watchSweep1.document.type")}</Text>
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginBottom: 16 }}>
        {DOC_TYPES.map(dt => {
          const sel = docType === dt.key;
          return (
            <TouchableOpacity key={dt.key} onPress={() => setDocType(dt.key)} data-testid={`doc-type-${dt.key}`} testID={`doc-type-${dt.key}`}
              style={{
                flexDirection: 'row', alignItems: 'center', gap: 6,
                paddingVertical: 8, paddingHorizontal: 12, borderRadius: 8,
                backgroundColor: sel ? accent : 'transparent',
                borderWidth: 1, borderColor: sel ? accent: colors.border,
              }}>
              <Ionicons name={dt.icon as any} size={14} color={sel ? colors.primaryText: colors.textSec} />
              <Text style={{ color: sel ? colors.primaryText: colors.textSec, fontSize: 12, fontWeight: '600' }}>{dt.label}</Text>
            </TouchableOpacity>
          );
        })}
      </View>

      {Platform.OS === 'web' && (
        <>
          <input
            ref={fileRef} type="file" accept=".pdf,.jpg,.jpeg,.png,.webp"
            style={{ display: 'none' }}
            onChange={(e) => { const f = e.target.files?.[0]; if (f) handleUpload(f); }}
          />
          <TouchableOpacity
            onPress={() => fileRef.current?.click()} disabled={uploading}
            data-testid="employer-upload-doc-btn" testID="employer-upload-doc-btn"
            style={{
              backgroundColor: colors.card, borderRadius: 12, padding: 24,
              alignItems: 'center', borderWidth: 2, borderColor: (globalThis as any).__alphaColor(accent, '40'),
              borderStyle: 'dashed', opacity: uploading ? 0.6 : 1,
            }}>
            {uploading ? <ActivityIndicator color={accent} /> : (
              <View style={{ alignItems: 'center' }}>
                <View style={{ width: 48, height: 48, borderRadius: 24, backgroundColor: (globalThis as any).__alphaColor(accent, '10'), alignItems: 'center', justifyContent: 'center', marginBottom: 10 }}>
                  <Ionicons name="cloud-upload" size={24} color={accent} />
                </View>
                <Text style={{ color: colors.text, fontSize: 14, fontWeight: '700' }}>{t("autofix.watchSweep1.upload.document")}</Text>
                <Text style={{ color: colors.textSec, fontSize: 12, marginTop: 4 }}>{t("autofix.watchSweep1.pdf.jpg.png.max.10.mb")}</Text>
              </View>
            )}
          </TouchableOpacity>
        </>
      )}
    </View>
  );
}

/* ─── Review Card ─── */
function ReviewCard({ label, value, icon, darkMode, colors }: { label: string; value: string; icon: string; darkMode: boolean; colors: any }) {
  if (!value) return null;
  return (
    <View style={{
      flexDirection: 'row', alignItems: 'center', gap: 12, paddingVertical: 12,
      borderBottomWidth: 1, borderBottomColor: colors.border,
    }}>
      <View style={{ width: 32, height: 32, borderRadius: 8, backgroundColor: (globalThis as any).__alphaColor(colors.primary, '10'), alignItems: 'center', justifyContent: 'center' }}>
        <Ionicons name={icon as any} size={16} color={colors.primary} />
      </View>
      <View style={{ flex: 1 }}>
        <Text style={{ color: colors.textSec, fontSize: 11, fontWeight: '600', textTransform: 'uppercase', letterSpacing: 0.5 }}>{label}</Text>
        <Text style={{ color: colors.text, fontSize: 14, fontWeight: '500', marginTop: 2 }}>{value}</Text>
      </View>
    </View>
  );
}

/* ─── Message Thread ─── */
function MessageThread({ messages, newMsg, setNewMsg, sendMessage, sendingMsg, darkMode, colors }: any) {
  const { t } = useTranslation();
  const accent = colors.primary;
  return (
    <View data-testid="employer-messages-section" testID="employer-messages-section" style={{
      backgroundColor: colors.card, borderRadius: 16, padding: 20,
      borderWidth: 1, borderColor: colors.border,
    }}>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 16 }}>
        <Ionicons name="chatbubbles" size={18} color={accent} />
        <Text style={{ color: colors.text, fontSize: 16, fontWeight: '700' }}>{t("autofix.watchSweep1.communication.thread")}</Text>
      </View>
      {messages.length === 0 ? (
        <View style={{ backgroundColor: colors.card, borderRadius: 10, padding: 20, alignItems: 'center', marginBottom: 16 }}>
          <Ionicons name="chatbubble-ellipses-outline" size={32} color={colors.placeholder} />
          <Text style={{ color: colors.textSec, fontSize: 13, marginTop: 8 }}>{t("autofix.watchSweep1.no.messages.yet.send.a.message.to.the")}</Text>
        </View>
      ) : (
        <View style={{ gap: 8, marginBottom: 16 }}>
          {messages.map((m: any) => {
            const isAdmin = m.sender_role === 'admin';
            return (
              <View key={m.message_id} style={{
                backgroundColor: isAdmin ? (globalThis as any).__alphaColor(accent, '08') : colors.bgSoft,
                borderRadius: 12, padding: 14, borderWidth: 1,
                borderColor: isAdmin ? (globalThis as any).__alphaColor(accent, '20') : colors.border,
                marginLeft: isAdmin ? 0 : 24, marginRight: isAdmin ? 24 : 0,
              }}>
                <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginBottom: 4 }}>
                  <Text style={{ color: isAdmin ? accent : (colors.text), fontSize: 12, fontWeight: '700' }}>
                    {isAdmin ? 'Admin' : 'You'}
                  </Text>
                  <Text style={{ color: colors.placeholder, fontSize: 10 }}>
                    {new Date(m.created_at).toLocaleDateString()} {new Date(m.created_at).toLocaleTimeString()}
                  </Text>
                </View>
                <Text style={{ color: colors.text, fontSize: 13, lineHeight: 20 }}>{m.message}</Text>
              </View>
            );
          })}
        </View>
      )}
      <View style={{ flexDirection: 'row', gap: 8 }}>
        <TextInput value={newMsg} onChangeText={setNewMsg} placeholder="Type a message..." data-testid="employer-message-input" testID="employer-message-input"
          placeholderTextColor={colors.placeholder}
          style={{
            flex: 1, backgroundColor: colors.card, color: colors.text,
            borderRadius: 10, padding: 14, fontSize: 14, borderWidth: 1, borderColor: colors.border,
          }} />
        <TouchableOpacity onPress={sendMessage} disabled={sendingMsg || !newMsg.trim()} data-testid="employer-send-message-btn" testID="employer-send-message-btn"
          style={{
            backgroundColor: accent, borderRadius: 10, paddingHorizontal: 18, justifyContent: 'center',
            opacity: sendingMsg || !newMsg.trim() ? 0.4 : 1,
          }}>
          <Ionicons name="send" size={18} color={colors.primaryText} />
        </TouchableOpacity>
      </View>
    </View>
  );
}

/* ─── Re-verification ─── */
function ReverifySection({ onSuccess, darkMode, colors }: { onSuccess: () => void; darkMode: boolean; colors: any }) {
  const { t } = useTranslation();
  const [status, setStatus] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const accent = colors.primary;

  useEffect(() => {
    (async () => {
      try { const res = await api.get('/employers/reverify-status'); setStatus(res.data); } catch (error) { handleAppRecoverableError({ scope: 'employer-apply.tsx#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
      setLoading(false);
    })();
  }, []);

  const startReverification = async () => {
    setSubmitting(true);
    try {
      await api.post('/hiring/v2/employer/application/reverify');
      alert('Re-verification started! Your application is now under review.');
      onSuccess();
    } catch (e: any) { alert(e?.response?.data?.detail || 'Failed to start re-verification'); }
    setSubmitting(false);
  };

  if (loading) return <ActivityIndicator color={accent} style={{ padding: 20 }} />;
  if (!status) return null;

  return (
    <View style={{
      backgroundColor: colors.card, borderRadius: 16, padding: 20,
      borderWidth: 1, borderColor: (globalThis as any).__alphaColor(colors.error, '30'), marginBottom: 20,
    }} data-testid="employer-reverify-section" testID="employer-reverify-section">
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 12 }}>
        <Ionicons name="refresh-circle" size={20} color={colors.error} />
        <Text style={{ color: colors.text, fontSize: 16, fontWeight: '700' }}>{t("autofix.watchSweep1.re.verification")}</Text>
      </View>
      <Text style={{ color: colors.textSec, fontSize: 13, lineHeight: 20, marginBottom: 16 }}>{status.reason}</Text>
      {status.can_reverify ? (
        <TouchableOpacity onPress={startReverification} disabled={submitting} data-testid="employer-reverify-btn" testID="employer-reverify-btn"
          style={{ backgroundColor: accent, borderRadius: 12, paddingVertical: 16, alignItems: 'center' }}>
          {submitting ? <ActivityIndicator color={colors.primaryText} /> : (
            <Text style={{ color: colors.primaryText, fontSize: 15, fontWeight: '700' }}>{t("autofix.watchSweep1.re.apply.now")}</Text>
          )}
        </TouchableOpacity>
      ) : (
        <View style={{ backgroundColor: colors.card, borderRadius: 10, padding: 14 }}>
          <Text style={{ color: colors.warningText, fontSize: 13, fontWeight: '600' }}>{t("autofix.watchSweep1.re.verification.unlocks.in")}{status.remaining_days}{t("careerEnhancements.stalled.days")}</Text>
          {status.unlock_at && (
            <Text style={{ color: colors.textSec, fontSize: 11, marginTop: 4 }}>{t("autofix.watchSweep1.available")}{new Date(status.unlock_at).toLocaleDateString()}
            </Text>
          )}
        </View>
      )}
    </View>
  );
}

/* ════════════════════════════════════════════════════
   MAIN CONTENT
   ════════════════════════════════════════════════════ */
type EmployerPortalContentProps = {
  funnelFocusStage?: 'interviews' | 'offers' | 'time-to-hire' | 'active-bottlenecks' | null;
  focusSignal?: number;
  routeSource?: string;
};

export function EmployerPortalContent({ funnelFocusStage = null, focusSignal = 0 }: EmployerPortalContentProps) {
  const { _user, user } = useAuth() as any;
  const router = useRouter();
  const { darkMode , colors} = useTheme();
  const { t } = useTranslation();
  const tx = useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);

  // @autofix-moved: was module-level const STATUS_CONFIG
  const STATUS_CONFIG: Record<string, { color: string; icon: string; label: string }> = {
    pending: { color: colors.warningText, icon: 'time', label: tx('employerApply.status.pendingReview', 'Pending Review') },
    in_review: { color: colors.accent, icon: 'eye', label: tx('employerApply.status.inReview', 'In Review') },
    approved: { color: colors.successText, icon: 'checkmark-circle', label: tx('employerApply.status.approved', 'Approved') },
    rejected: { color: colors.error, icon: 'close-circle', label: tx('employerApply.status.rejected', 'Rejected') },
    on_hold: { color: colors.textMuted, icon: 'pause-circle', label: tx('employerApply.status.onHold', 'On Hold') },
    needs_info: { color: colors.warningText, icon: 'alert-circle', label: tx('employerApply.status.moreInfoRequired', 'More Info Required') },
    escalated: { color: colors.accent, icon: 'arrow-up-circle', label: tx('employerApply.status.underSeniorReview', 'Under Senior Review') },
  };
  const accent = colors.primary;

  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [application, setApplication] = useState<any>(null);
  const [permissions, setPermissions] = useState<any>(null);
  const [messages, setMessages] = useState<any[]>([]);
  const [newMsg, setNewMsg] = useState('');
  const [sendingMsg, setSendingMsg] = useState(false);
  const [activeTab, setActiveTab] = useState('status');
  const [kpiDrilldownFilter, setKpiDrilldownFilter] = useState<'all' | 'time-to-hire' | 'stage-conversion' | 'offer-acceptance' | 'active-bottlenecks'>('all');
  const approvedScrollRef = useRef<ScrollView>(null);
  const [pipelineSectionY, setPipelineSectionY] = useState(0);
  const [funnelFocusBanner, setFunnelFocusBanner] = useState('');
  const [pipelineFocusActive, setPipelineFocusActive] = useState(false);
  const canApplyEmployerFunnelFocus = Boolean(permissions?.is_employer || _user?.is_admin || user?.is_admin);

  // Wizard step
  const [step, setStep] = useState(0);

  // Form state
  const [businessName, setBusinessName] = useState('');
  const [regNumber, setRegNumber] = useState('');
  const [country, setCountry] = useState('');
  const [businessEmail, setBusinessEmail] = useState('');
  const [industry, setIndustry] = useState('');
  const [website, setWebsite] = useState('');
  const [contactName, setContactName] = useState('');
  const [contactPhone, setContactPhone] = useState('');
  const [contactRole, setContactRole] = useState('');
  const [description, setDescription] = useState('');
  const [businessDocument, setBusinessDocument] = useState<KycUploadDraft | null>(null);
  const [idFrontDocument, setIdFrontDocument] = useState<KycUploadDraft | null>(null);
  const [idBackDocument, setIdBackDocument] = useState<KycUploadDraft | null>(null);

  const businessDocInputRef = useRef<HTMLInputElement>(null);
  const idFrontUploadInputRef = useRef<HTMLInputElement>(null);
  const idFrontCaptureInputRef = useRef<HTMLInputElement>(null);
  const idBackUploadInputRef = useRef<HTMLInputElement>(null);
  const idBackCaptureInputRef = useRef<HTMLInputElement>(null);

  // Validation
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [submitError, setSubmitError] = useState('');
  const [submitSuccess, setSubmitSuccess] = useState('');
  const pageTitle = t('employerApply.header.title');

  const loadData = useCallback(async () => {
    try {
      const [appRes, permRes] = await Promise.all([
        api.get('/employers/my-application'),
        api.get('/employers/my-permissions'),
      ]);
      setApplication(appRes.data.application);
      setPermissions(permRes.data);
      if (appRes.data.application?.employer_id) {
        const msgRes = await api.get(`/employers/messages/${appRes.data.application.employer_id}`).catch(() => ({ data: { messages: [] } }));
        setMessages(msgRes.data.messages || []);
      }
    } catch (e) {
      handleAppRecoverableError({
        scope: 'employer-apply.load-data',
        error: e,
        message: tx('employerApply.errors.loadDataFailed', 'Could not load employer application data right now.'),
        setError: setSubmitError,
        onRetry: () => { void loadData(); },
      
        notifyMode: 'dialog',
        userInitiated: true,
      });
    }
    finally { setLoading(false); }
  }, []);

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { loadData(); }, []);
  useAutoRefresh(loadData, { intervalMs: 30000 });

  useEffect(() => {
    if (!canApplyEmployerFunnelFocus || !funnelFocusStage) {
      setPipelineFocusActive(false);
      setFunnelFocusBanner('');
      return;
    }
    const focusConfig = funnelFocusStage === 'offers'
      ? {
          filter: 'offer-acceptance' as const,
          message: tx('jobsPortal.funnel.employerOfferFocus', 'Funnel focus: Offer Acceptance drilldown applied in hiring command center.'),
        }
      : funnelFocusStage === 'time-to-hire'
        ? {
            filter: 'time-to-hire' as const,
            message: tx('jobsPortal.funnel.employerTimeToHireFocus', 'Funnel focus: Time-to-Hire drilldown applied for completed journey velocity.'),
          }
        : funnelFocusStage === 'active-bottlenecks'
          ? {
              filter: 'active-bottlenecks' as const,
              message: tx('jobsPortal.funnel.employerBottleneckFocus', 'Funnel focus: Active Bottlenecks drilldown applied to prioritize stalled candidates.'),
            }
          : {
              filter: 'stage-conversion' as const,
              message: tx('jobsPortal.funnel.employerInterviewFocus', 'Funnel focus: Stage Conversion drilldown applied for interview progression.'),
            };

    setKpiDrilldownFilter(focusConfig.filter);
    setFunnelFocusBanner(focusConfig.message);
    setPipelineFocusActive(true);
    approvedScrollRef.current?.scrollTo({ y: Math.max(0, pipelineSectionY - 14), animated: true });
  }, [canApplyEmployerFunnelFocus, funnelFocusStage, focusSignal, pipelineSectionY, tx]);

  const validateStep = (s: number): boolean => {
    const errs: Record<string, string> = {};
    if (s === 0) {
      if (!businessName.trim()) errs.businessName = 'Business name is required';
      if (!regNumber.trim()) errs.regNumber = 'Registration number is required';
      if (!country.trim()) errs.country = 'Country is required';
      if (!businessEmail.trim()) errs.businessEmail = 'Business email is required';
      else if (!/\S+@\S+\.\S+/.test(businessEmail)) errs.businessEmail = 'Invalid email format';
      if (!businessDocument) errs.businessDocument = 'Business registration document is required';
    } else if (s === 1) {
      if (!contactName.trim()) errs.contactName = 'Contact name is required';
      if (!contactPhone.trim()) errs.contactPhone = 'Phone number is required';
      if (!idFrontDocument) errs.idFrontDocument = 'ID front document/photo is required';
      if (!idBackDocument) errs.idBackDocument = 'ID back document/photo is required';
    } else if (s === 2) {
      if (!industry) errs.industry = 'Please select an industry';
    }
    setErrors(errs);
    return Object.keys(errs).length === 0;
  };

  const handleKycFileSelected = useCallback(
    async (file: File | undefined, key: 'business_registration' | 'id_front' | 'id_back') => {
      if (!file) return;
      try {
        const result = await uploadEmployerDocument(file, key);
        const uploadedDoc = result.document;
        if (key === 'business_registration') setBusinessDocument(uploadedDoc);
        if (key === 'id_front') setIdFrontDocument(uploadedDoc);
        if (key === 'id_back') setIdBackDocument(uploadedDoc);
        setSubmitError('');
        setErrors((prev) => {
          const next = { ...prev };
          if (key === 'business_registration') delete next.businessDocument;
          if (key === 'id_front') delete next.idFrontDocument;
          if (key === 'id_back') delete next.idBackDocument;
          return next;
        });
      } catch (e: any) {
        setSubmitError(e?.message || 'Unable to upload file');
      }
    },
    [],
  );

  const nextStep = () => {
    setSubmitError('');
    setSubmitUpgradeUrl('');
    if (validateStep(step)) {
      setStep(s => Math.min(s + 1, 3));
      return;
    }
    setSubmitError('Please complete all required fields and mandatory document uploads before continuing.');
  };
  const prevStep = () => {
    setSubmitError('');
    setSubmitUpgradeUrl('');
    setStep(s => Math.max(s - 1, 0));
  };

  const submitApplication = async () => {
    setSubmitError('');
    setSubmitUpgradeUrl('');
    setSubmitSuccess('');
    if (!validateStep(0) || !validateStep(1) || !validateStep(2)) {
      setSubmitError('Please fill all required fields and upload all mandatory documents.');
      return;
    }
    setSubmitting(true);
    try {
      const payload = {
        business_name: businessName, registration_number: regNumber, country,
        business_email: businessEmail, industry, website: website || undefined,
        contact_person_name: contactName, contact_person_phone: contactPhone,
        contact_person_role: contactRole || undefined, description: description || undefined,
        documents: [businessDocument, idFrontDocument, idBackDocument].filter(Boolean),
      };
      const response = await api.post('/hiring/v2/employer/application/apply', payload);
      setSubmitSuccess('Application submitted successfully. Your documents are now queued for admin review.');
      setApplication(response.data?.application || null);
      setStep(0);
      loadData();
    } catch (e: any) {
      const payload = e?.response?.data || {};
      const detail = payload?.detail;
      if (payload?.error === 'Subscription Required') {
        setSubmitError('Employer Console is free for authenticated users. Please retry in a few seconds while access policy refreshes.');
      } else if (typeof detail === 'object' && detail?.message) {
        const missingKeys = Array.isArray(detail?.missing_document_keys) ? detail.missing_document_keys : [];
        const nextErrors: Record<string, string> = {};
        if (missingKeys.includes('business_registration')) nextErrors.businessDocument = 'Business registration document is required';
        if (missingKeys.includes('id_front')) nextErrors.idFrontDocument = 'ID front document/photo is required';
        if (missingKeys.includes('id_back')) nextErrors.idBackDocument = 'ID back document/photo is required';
        if (Object.keys(nextErrors).length) {
          setErrors(prev => ({ ...prev, ...nextErrors }));
        }
        setSubmitError(String(detail.message || 'Submission failed. Please verify required fields and documents.'));
      } else {
        const fallbackMessage = typeof detail === 'string' ? detail : (payload?.message || payload?.error || 'Submission failed. Please verify all required fields and documents.');
        setSubmitError(fallbackMessage);
      }
    }
    finally { setSubmitting(false); }
  };

  const resubmitInfo = async () => {
    setSubmitting(true);
    try {
      await api.post('/hiring/v2/employer/application/resubmit-info', {
        business_name: businessName || application?.business_name,
        registration_number: regNumber || application?.registration_number,
        country: country || application?.country,
        business_email: businessEmail || application?.business_email,
        industry: industry || application?.industry,
        website: website || application?.website,
        contact_person_name: contactName || application?.contact_person_name,
        contact_person_phone: contactPhone || application?.contact_person_phone,
        contact_person_role: contactRole || application?.contact_person_role,
        description: description || application?.description,
      });
      alert('Updated information submitted for review!');
      loadData();
    } catch (e: any) { alert(e?.response?.data?.detail || 'Resubmission failed'); }
    finally { setSubmitting(false); }
  };

  const sendMessage = async () => {
    if (!newMsg.trim() || !application?.employer_id) return;
    setSendingMsg(true);
    try {
      await api.post(`/hiring/v2/employer/application/messages/${application.employer_id}`, { message: newMsg.trim() });
      setNewMsg('');
      loadData();
    } catch (error) { handleAppRecoverableError({ scope: 'employer-apply.tsx#catch2', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
    setSendingMsg(false);
  };

  const cardBg = darkMode ? colors.bg : colors.card;
  const border = colors.border;
  const textPrimary = colors.text;
  const textSec = colors.textSec;
  const textMuted = colors.textMuted;
  const bgAlt = darkMode ? colors.card : colors.card;

  if (loading) return (
    <CareerSkeleton />
  );

  /* ═══════════════════════════════════════
     APPROVED EMPLOYER VIEW
     ═══════════════════════════════════════ */
  if (permissions?.is_employer) {
    return (
      <ScrollView ref={approvedScrollRef} contentContainerStyle={{ padding: 24, paddingBottom: 60 }}>
        <View style={{ maxWidth: 960, width: '100%', alignSelf: 'center' }}>
          {/* Success Banner */}
          <View style={{
            backgroundColor: (globalThis as any).__alphaColor(colors.success, '0A'), borderRadius: 16, padding: 28, marginBottom: 24,
            borderWidth: 1, borderColor: (globalThis as any).__alphaColor(colors.success, '25'),
          }} data-testid="employer-approved-banner" testID="employer-approved-banner">
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 14 }}>
              <View style={{ width: 52, height: 52, borderRadius: 26, backgroundColor: (globalThis as any).__alphaColor(colors.success, '15'), alignItems: 'center', justifyContent: 'center' }}>
                <Ionicons name="shield-checkmark" size={28} color={colors.successText} />
              </View>
              <View style={{ flex: 1 }}>
                <Text style={{ color: colors.successText, fontSize: 20, fontWeight: '800', letterSpacing: -0.5 }}>{t("autofix.watchSweep1.employer.verified")}</Text>
                <Text style={{ color: textSec, fontSize: 14, marginTop: 2 }}>{permissions.business_name}</Text>
              </View>
            </View>
          </View>

          {!!funnelFocusBanner && (
            <View style={{ marginBottom: 16, borderRadius: 12, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(colors.primary, '33'), backgroundColor: colors.primarySoft, padding: 10 }} data-testid="employer-funnel-focus-banner" testID="employer-funnel-focus-banner">
              <Text style={{ color: colors.primary, fontSize: 12, fontWeight: '700' }}>{funnelFocusBanner}</Text>
            </View>
          )}

          <Text style={{ color: textPrimary, fontSize: 18, fontWeight: '800', marginBottom: 16, letterSpacing: -0.5 }}>{t("autofix.watchSweep1.unlocked.features")}</Text>
          <View style={{ gap: 10, marginBottom: 28 }}>
            {[
              { perm: 'post_job', label: 'Job Posting', icon: 'add-circle', desc: 'Create and publish job listings' },
              { perm: 'manage_jobs', label: 'Job Management', icon: 'settings', desc: 'Edit, pause, and close listings' },
              { perm: 'view_applicants', label: 'View Applicants', icon: 'people', desc: 'Review candidate applications' },
              { perm: 'hire_candidate', label: 'Hire Candidates', icon: 'person-add', desc: 'Extend offers and onboard' },
              { perm: 'employer_analytics', label: 'Analytics', icon: 'bar-chart', desc: 'Track hiring performance' },
            ].filter(f => (permissions.permissions || []).includes(f.perm)).map(f => (
              <View key={f.perm} style={{
                flexDirection: 'row', alignItems: 'center', gap: 14,
                backgroundColor: cardBg, borderRadius: 12, padding: 16,
                borderWidth: 1, borderColor: border,
              }}>
                <View style={{ width: 44, height: 44, borderRadius: 10, backgroundColor: (globalThis as any).__alphaColor(accent, '0A'), alignItems: 'center', justifyContent: 'center' }}>
                  <Ionicons name={f.icon as any} size={22} color={accent} />
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={{ color: textPrimary, fontSize: 15, fontWeight: '700' }}>{f.label}</Text>
                  <Text style={{ color: textMuted, fontSize: 12, marginTop: 2 }}>{f.desc}</Text>
                </View>
                <Ionicons name="lock-open" size={18} color={colors.successText} />
              </View>
            ))}
          </View>

          <View
            style={{
              borderRadius: 14,
              borderWidth: pipelineFocusActive ? 2 : 0,
              borderColor: pipelineFocusActive ? colors.primary : 'transparent',
              padding: pipelineFocusActive ? 10 : 0,
              marginBottom: 14,
            }}
            onLayout={(event) => setPipelineSectionY(event.nativeEvent.layout.y)}
            data-testid="employer-pipeline-focus-anchor"
            testID="employer-pipeline-focus-anchor"
          >
            <EmployerKpiHeader onDrilldown={(filterKey) => setKpiDrilldownFilter(filterKey)} />

            <EmployerPipelineBoard
              drilldownFilter={kpiDrilldownFilter}
              onClearDrilldown={() => setKpiDrilldownFilter('all')}
            />
          </View>

          <TouchableOpacity onPress={() => router.push('/job-platform')} data-testid="go-to-hiring-btn" testID="go-to-hiring-btn"
            style={{
              backgroundColor: accent, borderRadius: 12, paddingVertical: 16, alignItems: 'center',
              flexDirection: 'row', justifyContent: 'center', gap: 8,
            }}>
            <Ionicons name="arrow-forward" size={18} color={colors.primaryText} />
            <Text style={{ color: colors.primaryText, fontSize: 16, fontWeight: '700' }}>{t("autofix.watchSweep1.go.to.hiring.dashboard")}</Text>
          </TouchableOpacity>
        </View>
      </ScrollView>
    );
  }

  /* ═══════════════════════════════════════
     REJECTED VIEW
     ═══════════════════════════════════════ */
  if (application?.status === 'rejected') {
    const statusCfg = STATUS_CONFIG.rejected;
    return (
      <ScrollView contentContainerStyle={{ padding: 24, paddingBottom: 60 }}>
        <View style={{ maxWidth: 960, width: '100%', alignSelf: 'center' }}>
          <View style={{
            backgroundColor: cardBg, borderRadius: 16, padding: 24, marginBottom: 20,
            borderWidth: 1, borderColor: (globalThis as any).__alphaColor(colors.error, '30'),
          }} data-testid="employer-rejected-card" testID="employer-rejected-card">
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 12, marginBottom: 14 }}>
              <View style={{ width: 44, height: 44, borderRadius: 22, backgroundColor: (globalThis as any).__alphaColor(colors.error, '10'), alignItems: 'center', justifyContent: 'center' }}>
                <Ionicons name={statusCfg.icon as any} size={24} color={statusCfg.color} />
              </View>
              <View>
                <Text style={{ color: statusCfg.color, fontSize: 18, fontWeight: '800' }}>{statusCfg.label}</Text>
                <Text style={{ color: textSec, fontSize: 14 }}>{application.business_name}</Text>
              </View>
            </View>
            {application.rejection_reason && (
              <View style={{ backgroundColor: (globalThis as any).__alphaColor(colors.error, '08'), borderRadius: 10, padding: 14, marginTop: 4 }}>
                <Text style={{ color: colors.error, fontSize: 12, fontWeight: '700', marginBottom: 4 }}>{t("jobPlatform.employer.reason")}</Text>
                <Text style={{ color: textPrimary, fontSize: 13, lineHeight: 20 }}>{application.rejection_reason}</Text>
              </View>
            )}
          </View>
          <ReverifySection onSuccess={loadData} darkMode={darkMode} colors={colors} />
          <MessageThread messages={messages} newMsg={newMsg} setNewMsg={setNewMsg} sendMessage={sendMessage} sendingMsg={sendingMsg} darkMode={darkMode} colors={colors} />
        </View>
      </ScrollView>
    );
  }

  /* ═══════════════════════════════════════
     EXISTING APPLICATION STATUS VIEW
     ═══════════════════════════════════════ */
  if (application) {
    const statusCfg = STATUS_CONFIG[application.status] || STATUS_CONFIG.pending;
    const TABS = [
      { key: 'status', label: 'Status', icon: 'information-circle' },
      { key: 'documents', label: 'Documents', icon: 'document-attach' },
      { key: 'messages', label: 'Messages', icon: 'chatbubbles', badge: messages.length },
    ];

    return (
      <ScrollView style={{ flex: 1, backgroundColor: 'transparent' }} contentContainerStyle={{ padding: 24, paddingBottom: 60, flexGrow: 1 }}>
        <View style={{ maxWidth: 960, width: '100%', alignSelf: 'center' }}>
          {!!funnelFocusBanner && (
            <View style={{ marginBottom: 16, borderRadius: 12, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(colors.primary, '33'), backgroundColor: colors.primarySoft, padding: 10 }} data-testid="employer-funnel-focus-banner" testID="employer-funnel-focus-banner">
              <Text style={{ color: colors.primary, fontSize: 12, fontWeight: '700' }}>{funnelFocusBanner}</Text>
            </View>
          )}

          {/* Status Header */}
          <View style={{
            backgroundColor: cardBg, borderRadius: 16, padding: 24, marginBottom: 20,
            borderWidth: 1, borderColor: border,
          }} data-testid="employer-status-card" testID="employer-status-card">
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 14, marginBottom: 14 }}>
              <View style={{
                width: 48, height: 48, borderRadius: 24,
                backgroundColor: (globalThis as any).__alphaColor(statusCfg.color, '15'), alignItems: 'center', justifyContent: 'center',
              }}>
                <Ionicons name={statusCfg.icon as any} size={24} color={statusCfg.color} />
              </View>
              <View style={{ flex: 1 }}>
                <Text style={{ color: statusCfg.color, fontSize: 11, fontWeight: '700', textTransform: 'uppercase', letterSpacing: 0.5 }}>{statusCfg.label}</Text>
                <Text style={{ color: textPrimary, fontSize: 18, fontWeight: '800', letterSpacing: -0.5, marginTop: 2 }}>{application.business_name}</Text>
              </View>
            </View>
            <View style={{ flexDirection: 'row', gap: 16 }}>
              <Text style={{ color: textMuted, fontSize: 12 }}>{application.industry} · {application.country}</Text>
              <Text style={{ color: textMuted, fontSize: 12 }}>{t("autofix.watchSweep1.submitted")}{new Date(application.submitted_at).toLocaleDateString()}</Text>
            </View>
            {application.info_requested && (
              <View style={{ backgroundColor: (globalThis as any).__alphaColor(colors.warning, '0A'), borderRadius: 10, padding: 14, marginTop: 16, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(colors.warning, '20') }}>
                <Text style={{ color: colors.warningText, fontSize: 12, fontWeight: '700' }}>{t("autofix.watchSweep1.admin.requested.additional.info")}</Text>
                <Text style={{ color: textPrimary, fontSize: 13, marginTop: 4, lineHeight: 20 }}>{application.info_requested}</Text>
              </View>
            )}
          </View>

          {/* Timeline */}
          <View style={{
            backgroundColor: cardBg, borderRadius: 16, padding: 24,
            borderWidth: 1, borderColor: border, marginBottom: 20,
          }}>
            <Text style={{ color: textPrimary, fontSize: 16, fontWeight: '700', marginBottom: 16 }}>{t("autofix.watchSweep1.application.timeline")}</Text>
            {['Submitted', 'Under Review', 'Decision'].map((stepLabel, i) => {
              const isDone = i === 0 || (i === 1 && ['in_review', 'approved', 'rejected', 'on_hold', 'escalated'].includes(application.status)) || (i === 2 && ['approved', 'rejected'].includes(application.status));
              const isActive = (i === 0 && application.status === 'pending') || (i === 1 && ['in_review', 'needs_info', 'on_hold', 'escalated'].includes(application.status)) || (i === 2 && ['approved', 'rejected'].includes(application.status));
              return (
                <View key={stepLabel} style={{ flexDirection: 'row', alignItems: 'center', gap: 14, marginBottom: i < 2 ? 16 : 0 }}>
                  <View style={{
                    width: 32, height: 32, borderRadius: 16,
                    backgroundColor: isDone ? colors.success : isActive ? accent : colors.bgSoft,
                    alignItems: 'center', justifyContent: 'center',
                    borderWidth: !isDone && !isActive ? 2 : 0, borderColor: colors.borderMd,
                  }}>
                    {isDone ? <Ionicons name="checkmark" size={16} color={colors.primaryText} /> : isActive ? <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: colors.primaryText }} /> : null}
                  </View>
                  <Text style={{
                    color: isDone ? colors.success : isActive ? accent : textMuted,
                    fontSize: 14, fontWeight: isActive ? '700' : '500',
                  }}>{stepLabel}</Text>
                  {i < 2 && <View style={{ position: 'absolute', left: 15, top: 36, width: 2, height: 12, backgroundColor: isDone ? (globalThis as any).__alphaColor(colors.success, '40') : darkMode ? colors.card : colors.textDim }} />}
                </View>
              );
            })}
          </View>

          {/* Tab bar */}
          <View style={{ flexDirection: 'row', gap: 8, marginBottom: 20 }}>
            {TABS.map(tab => (
              <TouchableOpacity key={tab.key} onPress={() => setActiveTab(tab.key)} data-testid={`emp-tab-${tab.key}`} testID={`emp-tab-${tab.key}`}
                style={{
                  flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6,
                  paddingVertical: 12, borderRadius: 10,
                  backgroundColor: activeTab === tab.key ? (globalThis as any).__alphaColor(accent, '0A') : cardBg,
                  borderWidth: 1, borderColor: activeTab === tab.key ? (globalThis as any).__alphaColor(accent, '30') : border,
                }}>
                <Ionicons name={tab.icon as any} size={16} color={activeTab === tab.key ? accent : textMuted} />
                <Text style={{ color: activeTab === tab.key ? accent : textMuted, fontSize: 13, fontWeight: '600' }}>{tab.label}</Text>
                {tab.badge ? (
                  <View style={{ backgroundColor: accent, borderRadius: 8, paddingHorizontal: 6, paddingVertical: 2 }}>
                    <Text style={{ color: colors.primaryText, fontSize: 10, fontWeight: '700' }}>{tab.badge}</Text>
                  </View>
                ) : null}
              </TouchableOpacity>
            ))}
          </View>

          {/* Tab content */}
          {activeTab === 'status' && application.status === 'needs_info' && (
            <View style={{
              backgroundColor: cardBg, borderRadius: 16, padding: 24,
              borderWidth: 1, borderColor: (globalThis as any).__alphaColor(colors.warning, '30'),
            }}>
              <Text style={{ color: colors.warningText, fontSize: 16, fontWeight: '700', marginBottom: 16 }}>{t("autofix.watchSweep1.update.your.information")}</Text>
              <Field label="Business Name" value={businessName || application?.business_name || ''} setter={setBusinessName} placeholder="Company name" testId="emp-business-name" colors={colors} darkMode={darkMode} required />
              <Field label="Registration Number" value={regNumber || application?.registration_number || ''} setter={setRegNumber} placeholder="Business reg. number" testId="emp-reg-number" colors={colors} darkMode={darkMode} required />
              <Field label="Country" value={country || application?.country || ''} setter={setCountry} placeholder="Country" testId="emp-country" colors={colors} darkMode={darkMode} required />
              <Field label="Business Email" value={businessEmail || application?.business_email || ''} setter={setBusinessEmail} placeholder="company@example.com" testId="emp-business-email" colors={colors} darkMode={darkMode} required />
              <Field label="Contact Person" value={contactName || application?.contact_person_name || ''} setter={setContactName} placeholder="Full name" testId="emp-contact-name" colors={colors} darkMode={darkMode} required />
              <Field label="Contact Phone" value={contactPhone || application?.contact_person_phone || ''} setter={setContactPhone} placeholder="+123..." testId="emp-contact-phone" colors={colors} darkMode={darkMode} required />
              <IndustryPicker value={industry || application?.industry || ''} onChange={setIndustry} colors={colors} darkMode={darkMode} />
              <TouchableOpacity onPress={resubmitInfo} disabled={submitting} data-testid="employer-resubmit-btn" testID="employer-resubmit-btn"
                style={{ backgroundColor: colors.warning, borderRadius: 12, paddingVertical: 16, alignItems: 'center', marginTop: 8 }}>
                {submitting ? <ActivityIndicator color={colors.primaryText} /> : (
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                    <Ionicons name="send" size={18} color={colors.primaryText} />
                    <Text style={{ color: colors.primaryText, fontSize: 16, fontWeight: '700' }}>{t("autofix.watchSweep1.resubmit.information")}</Text>
                  </View>
                )}
              </TouchableOpacity>
            </View>
          )}

          {activeTab === 'documents' && (
            <DocumentUpload employerId={application.employer_id} documents={application.documents || []} onRefresh={loadData} colors={colors} darkMode={darkMode} />
          )}

          {activeTab === 'messages' && (
            <MessageThread messages={messages} newMsg={newMsg} setNewMsg={setNewMsg} sendMessage={sendMessage} sendingMsg={sendingMsg} darkMode={darkMode} colors={colors} />
          )}
        </View>
      </ScrollView>
    );
  }

  /* ═══════════════════════════════════════
     NEW APPLICATION — MULTI-STEP WIZARD
     ═══════════════════════════════════════ */
  return (
    <ScrollView contentContainerStyle={{ padding: 24, paddingBottom: 80 }}>
      <View style={{ maxWidth: 960, width: '100%', alignSelf: 'center' }}>
        {!!funnelFocusBanner && (
          <View style={{ marginBottom: 16, borderRadius: 12, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(colors.primary, '33'), backgroundColor: colors.primarySoft, padding: 10 }} data-testid="employer-funnel-focus-banner" testID="employer-funnel-focus-banner">
            <Text style={{ color: colors.primary, fontSize: 12, fontWeight: '700' }}>{funnelFocusBanner}</Text>
          </View>
        )}

        {Platform.OS === 'web' && (
          <>
            <input
              ref={businessDocInputRef}
              type="file"
              accept=".pdf,.jpg,.jpeg,.png,.webp"
              style={{ display: 'none' }}
              onChange={(e) => {
                const file = e.target.files?.[0];
                void handleKycFileSelected(file, 'business_registration');
                e.currentTarget.value = '';
              }}
            />
            <input
              ref={idFrontUploadInputRef}
              type="file"
              accept=".pdf,.jpg,.jpeg,.png,.webp,image/*"
              style={{ display: 'none' }}
              onChange={(e) => {
                const file = e.target.files?.[0];
                void handleKycFileSelected(file, 'id_front');
                e.currentTarget.value = '';
              }}
            />
            <input
              ref={idFrontCaptureInputRef}
              type="file"
              accept="image/*"
              capture="environment"
              style={{ display: 'none' }}
              onChange={(e) => {
                const file = e.target.files?.[0];
                void handleKycFileSelected(file, 'id_front');
                e.currentTarget.value = '';
              }}
            />
            <input
              ref={idBackUploadInputRef}
              type="file"
              accept=".pdf,.jpg,.jpeg,.png,.webp,image/*"
              style={{ display: 'none' }}
              onChange={(e) => {
                const file = e.target.files?.[0];
                void handleKycFileSelected(file, 'id_back');
                e.currentTarget.value = '';
              }}
            />
            <input
              ref={idBackCaptureInputRef}
              type="file"
              accept="image/*"
              capture="environment"
              style={{ display: 'none' }}
              onChange={(e) => {
                const file = e.target.files?.[0];
                void handleKycFileSelected(file, 'id_back');
                e.currentTarget.value = '';
              }}
            />
          </>
        )}

        {/* Page Header */}
        <View style={{ marginBottom: 8 }} data-testid="employer-apply-header" testID="employer-apply-header">
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 12, marginBottom: 12 }}>
            <View style={{ width: 48, height: 48, borderRadius: 12, backgroundColor: (globalThis as any).__alphaColor(accent, '10'), alignItems: 'center', justifyContent: 'center' }}>
              <Ionicons name="briefcase" size={24} color={accent} />
            </View>
            <View>
              <Text style={{ color: textPrimary, fontSize: 24, fontWeight: '800', letterSpacing: -0.8 }}>{pageTitle === 'employerApply.header.title' ? 'Become an Employer' : pageTitle}</Text>
              <Text style={{ color: textSec, fontSize: 14, marginTop: 2 }}>{tx('employerApply.header.subtitle', 'Submit your business details to start hiring talent')}</Text>
            </View>
          </View>
        </View>

        {/* Stepper */}
        <Stepper step={step} colors={colors} darkMode={darkMode} />

        {/* Form Card */}
        <View style={{
          backgroundColor: cardBg, borderRadius: 16, padding: 28,
          borderWidth: 1, borderColor: border, marginBottom: 20,
        }}>
          {/* Step 0: Business Identity */}
          {step === 0 && (
            <View data-testid="wizard-step-identity" testID="wizard-step-identity">
              <Text style={{ color: textPrimary, fontSize: 18, fontWeight: '800', marginBottom: 4, letterSpacing: -0.5 }}>{t("autofix.watchSweep1.business.identity")}</Text>
              <Text style={{ color: textMuted, fontSize: 13, marginBottom: 24 }}>{t("autofix.watchSweep1.provide.your.company.s.legal.information")}</Text>
              <Field label="Business Name" value={businessName} setter={setBusinessName} placeholder="e.g. Acme Corporation" testId="emp-business-name" colors={colors} darkMode={darkMode} required />
              {errors.businessName && <Text style={{ color: colors.error, fontSize: 12, marginTop: -12, marginBottom: 12 }}>{errors.businessName}</Text>}
              <Field label="Registration Number" value={regNumber} setter={setRegNumber} placeholder="e.g. RC-12345678" testId="emp-reg-number" colors={colors} darkMode={darkMode} required />
              {errors.regNumber && <Text style={{ color: colors.error, fontSize: 12, marginTop: -12, marginBottom: 12 }}>{errors.regNumber}</Text>}
              <Field label="Country" value={country} setter={setCountry} placeholder="e.g. United States" testId="emp-country" colors={colors} darkMode={darkMode} required />
              {errors.country && <Text style={{ color: colors.error, fontSize: 12, marginTop: -12, marginBottom: 12 }}>{errors.country}</Text>}
              <Field label="Business Email" value={businessEmail} setter={setBusinessEmail} placeholder="contact@company.com" testId="emp-business-email" colors={colors} darkMode={darkMode} required />
              {errors.businessEmail && <Text style={{ color: colors.error, fontSize: 12, marginTop: -12, marginBottom: 12 }}>{errors.businessEmail}</Text>}

              <RequiredAttachmentField
                title="Official Business Document"
                subtitle="Upload your country official business registration document (PDF/JPG/PNG/WebP, max 10MB)."
                testId="emp-business-document"
                value={businessDocument}
                onPick={() => businessDocInputRef.current?.click()}
                onClear={() => setBusinessDocument(null)}
                error={errors.businessDocument}
                colors={colors}
              />
            </View>
          )}

          {/* Step 1: Contact Info */}
          {step === 1 && (
            <View data-testid="wizard-step-contact" testID="wizard-step-contact">
              <Text style={{ color: textPrimary, fontSize: 18, fontWeight: '800', marginBottom: 4, letterSpacing: -0.5 }}>{t("autofix.watchSweep1.contact.information")}</Text>
              <Text style={{ color: textMuted, fontSize: 13, marginBottom: 24 }}>{t("autofix.watchSweep1.who.should.we.reach.out.to")}</Text>
              <Field label="Contact Person" value={contactName} setter={setContactName} placeholder="Full name" testId="emp-contact-name" colors={colors} darkMode={darkMode} required />
              {errors.contactName && <Text style={{ color: colors.error, fontSize: 12, marginTop: -12, marginBottom: 12 }}>{errors.contactName}</Text>}
              <Field label="Phone Number" value={contactPhone} setter={setContactPhone} placeholder="+1 (555) 000-0000" testId="emp-contact-phone" colors={colors} darkMode={darkMode} required />
              {errors.contactPhone && <Text style={{ color: colors.error, fontSize: 12, marginTop: -12, marginBottom: 12 }}>{errors.contactPhone}</Text>}
              <Field label="Role / Title" value={contactRole} setter={setContactRole} placeholder="e.g. CEO, HR Manager" testId="emp-contact-role" colors={colors} darkMode={darkMode} />

              <RequiredAttachmentField
                title="ID Document — Front"
                subtitle="Upload ID front image/PDF, or take a live photo for verification."
                testId="emp-id-front"
                value={idFrontDocument}
                onPick={() => idFrontUploadInputRef.current?.click()}
                onCapture={() => idFrontCaptureInputRef.current?.click()}
                onClear={() => setIdFrontDocument(null)}
                error={errors.idFrontDocument}
                colors={colors}
                allowCapture
              />

              <RequiredAttachmentField
                title="ID Document — Back"
                subtitle="Upload ID back image/PDF, or take a live photo for verification."
                testId="emp-id-back"
                value={idBackDocument}
                onPick={() => idBackUploadInputRef.current?.click()}
                onCapture={() => idBackCaptureInputRef.current?.click()}
                onClear={() => setIdBackDocument(null)}
                error={errors.idBackDocument}
                colors={colors}
                allowCapture
              />
            </View>
          )}

          {/* Step 2: Profile */}
          {step === 2 && (
            <View data-testid="wizard-step-profile" testID="wizard-step-profile">
              <Text style={{ color: textPrimary, fontSize: 18, fontWeight: '800', marginBottom: 4, letterSpacing: -0.5 }}>{t("autofix.watchSweep1.company.profile")}</Text>
              <Text style={{ color: textMuted, fontSize: 13, marginBottom: 24 }}>{t("autofix.watchSweep1.tell.us.more.about.your.organization")}</Text>
              <IndustryPicker value={industry} onChange={setIndustry} colors={colors} darkMode={darkMode} />
              {errors.industry && <Text style={{ color: colors.error, fontSize: 12, marginTop: -8, marginBottom: 12 }}>{errors.industry}</Text>}
              <Field label="Website" value={website} setter={setWebsite} placeholder="https://www.company.com" testId="emp-website" colors={colors} darkMode={darkMode} />
              <Field label="Description" value={description} setter={setDescription} placeholder="Tell us about your business, culture, and hiring needs..." testId="emp-description" colors={colors} darkMode={darkMode} multiline />
            </View>
          )}

          {/* Step 3: Review */}
          {step === 3 && (
            <View data-testid="wizard-step-review" testID="wizard-step-review">
              <Text style={{ color: textPrimary, fontSize: 18, fontWeight: '800', marginBottom: 4, letterSpacing: -0.5 }}>{t("autofix.watchSweep1.review.your.application")}</Text>
              <Text style={{ color: textMuted, fontSize: 13, marginBottom: 24 }}>{t("autofix.watchSweep1.please.verify.all.information.before.submitting")}</Text>

              <View style={{ backgroundColor: bgAlt, borderRadius: 12, padding: 20, marginBottom: 16 }}>
                <Text style={{ color: accent, fontSize: 12, fontWeight: '700', textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 8 }}>{t("autofix.watchSweep1.business.identity")}</Text>
                <ReviewCard label="Business Name" value={businessName} icon="business" darkMode={darkMode} colors={colors} />
                <ReviewCard label="Registration Number" value={regNumber} icon="document" darkMode={darkMode} colors={colors} />
                <ReviewCard label="Country" value={country} icon="earth" darkMode={darkMode} colors={colors} />
                <ReviewCard label="Business Email" value={businessEmail} icon="mail" darkMode={darkMode} colors={colors} />
                <ReviewCard label="Business Doc" value={businessDocument?.filename || ''} icon="document-attach" darkMode={darkMode} colors={colors} />
              </View>

              <View style={{ backgroundColor: bgAlt, borderRadius: 12, padding: 20, marginBottom: 16 }}>
                <Text style={{ color: accent, fontSize: 12, fontWeight: '700', textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 8 }}>{t("autofix.watchSweep1.contact.information")}</Text>
                <ReviewCard label="Contact Person" value={contactName} icon="person" darkMode={darkMode} colors={colors} />
                <ReviewCard label="Phone" value={contactPhone} icon="call" darkMode={darkMode} colors={colors} />
                <ReviewCard label="Role" value={contactRole} icon="briefcase" darkMode={darkMode} colors={colors} />
                <ReviewCard label="ID Front" value={idFrontDocument?.filename || ''} icon="card" darkMode={darkMode} colors={colors} />
                <ReviewCard label="ID Back" value={idBackDocument?.filename || ''} icon="card" darkMode={darkMode} colors={colors} />
              </View>

              <View style={{ backgroundColor: bgAlt, borderRadius: 12, padding: 20 }}>
                <Text style={{ color: accent, fontSize: 12, fontWeight: '700', textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 8 }}>{t("autofix.watchSweep1.company.profile")}</Text>
                <ReviewCard label="Industry" value={industry} icon="grid" darkMode={darkMode} colors={colors} />
                <ReviewCard label="Website" value={website} icon="globe" darkMode={darkMode} colors={colors} />
                <ReviewCard label="Description" value={description} icon="document-text" darkMode={darkMode} colors={colors} />
              </View>
            </View>
          )}
        </View>

        {!!submitError && (
          <View style={{ backgroundColor: (globalThis as any).__alphaColor(colors.error, '12'), borderColor: (globalThis as any).__alphaColor(colors.error, '35'), borderWidth: 1, borderRadius: 10, padding: 12, marginBottom: 12 }} data-testid="employer-submit-error" testID="employer-submit-error">
            <Text style={{ color: colors.error, fontSize: 12, fontWeight: '700' }}>{submitError}</Text>
          </View>
        )}
        {!!submitSuccess && (
          <View style={{ backgroundColor: (globalThis as any).__alphaColor(colors.success, '12'), borderColor: (globalThis as any).__alphaColor(colors.success, '35'), borderWidth: 1, borderRadius: 10, padding: 12, marginBottom: 12 }} data-testid="employer-submit-success" testID="employer-submit-success">
            <Text style={{ color: colors.successText, fontSize: 12, fontWeight: '700' }}>{submitSuccess}</Text>
          </View>
        )}

        {/* Navigation Buttons */}
        <View style={{ flexDirection: 'row', gap: 12 }}>
          {step > 0 && (
            <TouchableOpacity onPress={prevStep} data-testid="employer-prev-step-btn" testID="employer-prev-step-btn"
              style={{
                flex: 1, borderRadius: 12, paddingVertical: 16, alignItems: 'center',
                backgroundColor: 'transparent', borderWidth: 1, borderColor: border,
                flexDirection: 'row', justifyContent: 'center', gap: 8,
              }}>
              <Ionicons name="arrow-back" size={18} color={textSec} />
              <Text style={{ color: textSec, fontSize: 15, fontWeight: '600' }}>{t("careers.offerConfirm.actions.back")}</Text>
            </TouchableOpacity>
          )}

          {step < 3 ? (
            <TouchableOpacity onPress={nextStep} data-testid="employer-next-step-btn" testID="employer-next-step-btn"
              style={{
                flex: step === 0 ? 1 : 2, backgroundColor: accent, borderRadius: 12,
                paddingVertical: 16, alignItems: 'center',
                flexDirection: 'row', justifyContent: 'center', gap: 8,
              }}>
              <Text style={{ color: colors.primaryText, fontSize: 15, fontWeight: '700' }}>{t("welcomeBack.continue")}</Text>
              <Ionicons name="arrow-forward" size={18} color={colors.primaryText} />
            </TouchableOpacity>
          ) : (
            <TouchableOpacity onPress={submitApplication} disabled={submitting} data-testid="employer-submit-btn" testID="employer-submit-btn"
              style={{
                flex: 2, backgroundColor: colors.success, borderRadius: 12,
                paddingVertical: 18, alignItems: 'center',
                flexDirection: 'row', justifyContent: 'center', gap: 10,
                opacity: submitting ? 0.7 : 1,
              }}>
              {submitting ? <ActivityIndicator color={colors.primaryText} /> : (
                <>
                  <Ionicons name="checkmark-circle" size={22} color={colors.primaryText} />
                  <Text style={{ color: colors.primaryText, fontSize: 17, fontWeight: '800', letterSpacing: -0.3 }}>{tx('employerApply.actions.submitApplication', 'Submit Application')}</Text>
                </>
              )}
            </TouchableOpacity>
          )}
        </View>

        {/* Info note */}
        <View style={{ flexDirection: 'row', alignItems: 'flex-start', gap: 10, marginTop: 20, paddingHorizontal: 4 }}>
          <Ionicons name="shield-checkmark" size={16} color={textMuted} style={{ marginTop: 1 }} />
          <Text style={{ color: textMuted, fontSize: 12, lineHeight: 18, flex: 1 }}>{t("autofix.watchSweep1.your.information.is.encrypted.and.securely.stored.applications")}</Text>
        </View>
      </View>
    </ScrollView>
  );
}

/* ─── Page Wrapper ─── */
export default function EmployerApplyPage() {
  return (
    <AppShell>
      <View style={{ flex: 1, backgroundColor: 'transparent' }}>
        <EmployerPortalContent />
      </View>
    </AppShell>
  );
}
