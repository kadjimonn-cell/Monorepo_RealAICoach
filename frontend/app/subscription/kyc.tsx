import React, { useEffect, useMemo, useState, useCallback } from 'react';
import { View, Text, ScrollView, TouchableOpacity, TextInput, ActivityIndicator, Platform, Dimensions } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { useAuth } from '../../src/context/AuthContext';
import { useTheme } from '../../src/context/ThemeContext';
import AppShell from '../../src/components/AppShell';
import api from '../../src/services/api';
import { ProfileFormSkeleton } from '../../src/components/SkeletonLoaders';
import { useTranslation } from '../../src/hooks/useTranslation';
import { handleAppRecoverableError } from '../../src/utils/appRecoverableError';

const { width: SW } = Dimensions.get('window');
const isMobileDevice = Platform.OS === 'web' && SW < 768;
const isDesktop = Platform.OS === 'web' && SW >= 768;

type Step = 'info' | 'documents' | 'review';
const STEPS: { key: Step; label: string; icon: string }[] = [
  { key: 'info', label: 'Personal Info', icon: 'person' },
  { key: 'documents', label: 'ID Documents', icon: 'camera' },
  { key: 'review', label: 'Review', icon: 'checkmark-circle' },
];

// QR Code SVG generator (pure implementation, no external dependency needed at runtime)
function QRCodeSVG({ value, size = 200 }: { value: string; size?: number }) {
  const [svgContent, setSvgContent] = useState<string | null>(null);

  useEffect(() => {
    if (Platform.OS === 'web' && typeof window !== 'undefined') {
      import('qrcode').then((QRCode) => {
        QRCode.toString(value, { type: 'svg', width: size, margin: 1 }, (err: any, svg: string) => {
          if (!err) setSvgContent(svg);
        });
      });
    }
  }, [value, size]);

  if (!svgContent) return <ActivityIndicator />;

  if (Platform.OS === 'web') {
    const svgDataUri = `data:image/svg+xml;utf8,${encodeURIComponent(svgContent)}`;
    return (
      <img
        src={svgDataUri}
        alt="KYC QR code"
        data-testid="kyc-qr-svg-image"
        style={{ width: size, height: size, display: 'block' }}
      />
    );
  }
  return null;
}

// ── Verification Journey Timeline Component ──
function VerificationTimeline({ kyc, C }: { kyc: any; C: any }) {
  const { t } = useTranslation();
  const docs = kyc.documents || [];
  const docTypes = new Set(docs.map((d: any) => d.type));
  const hasAllDocs = ['id_front', 'id_back', 'selfie'].every(t => docTypes.has(t));
  const hasAI = kyc.ai_verification && kyc.ai_verification.analyzer !== 'fallback';
  const aiPassed = hasAI && kyc.ai_verification.confidence_score >= 0.6;
  const isVerified = kyc.status === 'verified';
  const isRejected = kyc.status === 'rejected';

  const steps = [
    {
      key: 'submitted',
      label: 'Application Submitted',
      icon: 'document-text' as const,
      done: !!kyc.submitted_at,
      active: !!kyc.submitted_at && !hasAllDocs,
      time: kyc.submitted_at ? new Date(kyc.submitted_at).toLocaleDateString('en', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : null,
      detail: kyc.submitted_at ? `Level ${kyc.level || 1} - ${kyc.id_type?.replace(/_/g, ' ')}` : 'Submit your personal information',
      est: null,
    },
    {
      key: 'documents',
      label: 'Documents Uploaded',
      icon: 'camera' as const,
      done: hasAllDocs,
      active: !!kyc.submitted_at && !hasAllDocs,
      time: hasAllDocs ? (() => {
        const lastDoc = [...docs].sort((a: any, b: any) => new Date(b.uploaded_at).getTime() - new Date(a.uploaded_at).getTime())[0];
        return lastDoc ? new Date(lastDoc.uploaded_at).toLocaleDateString('en', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : null;
      })() : null,
      detail: hasAllDocs ? `${docTypes.size} document types verified` : `${docTypes.size}/3 uploaded (ID front, back, selfie)`,
      est: !hasAllDocs && kyc.submitted_at ? 'Upload remaining documents' : null,
    },
    {
      key: 'ai_analysis',
      label: 'AI Analysis',
      icon: 'sparkles' as const,
      done: hasAI,
      active: hasAllDocs && !hasAI,
      time: hasAI ? new Date(kyc.ai_verification.analyzed_at).toLocaleDateString('en', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : null,
      detail: hasAI
        ? `${kyc.ai_verification.checks?.filter((c: any) => c.passed).length}/${kyc.ai_verification.checks?.length} checks passed - ${kyc.ai_verification.risk_level} risk`
        : hasAllDocs ? 'AI analysis in progress...' : 'Triggers after all documents uploaded',
      est: hasAllDocs && !hasAI ? '~5 seconds' : null,
    },
    {
      key: 'decision',
      label: isRejected ? 'Verification Declined' : isVerified ? 'Verification Approved' : 'Final Decision',
      icon: isRejected ? 'close-circle' as const : 'shield-checkmark' as const,
      done: isVerified || isRejected,
      active: hasAI && !isVerified && !isRejected,
      time: kyc.verified_at ? new Date(kyc.verified_at).toLocaleDateString('en', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : kyc.last_rejection_date ? new Date(kyc.last_rejection_date).toLocaleDateString('en', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : null,
      detail: isVerified ? `Tier: ${kyc.tier?.replace(/_/g, ' ')} - Full access granted`
        : isRejected ? (kyc.rejection_reason || 'Review flagged concerns')
        : aiPassed ? 'Pending final approval' : 'Awaiting AI analysis completion',
      est: hasAI && !isVerified && !isRejected ? 'Under review' : null,
    },
  ];

  return (
    <View style={{ backgroundColor: C.card, borderRadius: 14, padding: 16, marginBottom: 16, borderWidth: 1, borderColor: C.border }} data-testid="idv-timeline" testID="idv-timeline">
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 14 }}>
        <View style={{ width: 28, height: 28, borderRadius: 14, backgroundColor: (globalThis as any).__alphaColor(C.primary, '15'), alignItems: 'center', justifyContent: 'center' }}>
          <Ionicons name="git-branch" size={15} color={C.primary} />
        </View>
        <Text style={{ color: C.text, fontSize: 14, fontWeight: '700' }}>{t("autofix.watchSweep1.verification.journey")}</Text>
        {isVerified && (
          <View style={{ backgroundColor: (globalThis as any).__alphaColor(C.success, '20'), paddingHorizontal: 8, paddingVertical: 2, borderRadius: 4, marginLeft: 'auto' }}>
            <Text style={{ color: C.successText, fontSize: 8, fontWeight: '800' }}>COMPLETE</Text>
          </View>
        )}
      </View>

      {steps.map((s, i) => {
        const nodeColor = s.done ? (s.key === 'decision' && isRejected ? C.error : C.success) : s.active ? C.primary : C.border;
        const lineColor = s.done ? C.success : C.border;
        const isLast = i === steps.length - 1;

        return (
          <View key={s.key} style={{ flexDirection: 'row', minHeight: isLast ? 44 : 64 }} data-testid={`idv-timeline-step-${s.key}`} testID={`idv-timeline-step-${s.key}`}>
            {/* Timeline connector */}
            <View style={{ width: 32, alignItems: 'center' }}>
              {/* Node */}
              <View style={{
                width: s.done || s.active ? 22 : 18,
                height: s.done || s.active ? 22 : 18,
                borderRadius: 11,
                backgroundColor: s.done ? (globalThis as any).__alphaColor(nodeColor, '20') : 'transparent',
                borderWidth: 2,
                borderColor: nodeColor,
                alignItems: 'center',
                justifyContent: 'center',
              }}>
                {s.done ? (
                  <Ionicons name={s.key === 'decision' && isRejected ? 'close' : 'checkmark'} size={12} color={nodeColor} />
                ) : s.active ? (
                  <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: C.primary }} />
                ) : null}
              </View>
              {/* Line */}
              {!isLast && (
                <View style={{ width: 2, flex: 1, backgroundColor: lineColor, marginVertical: 2 }} />
              )}
            </View>

            {/* Content */}
            <View style={{ flex: 1, paddingLeft: 10, paddingBottom: isLast ? 0 : 16 }}>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                <Text style={{ color: s.done || s.active ? C.text : C.dim, fontSize: 12, fontWeight: s.done || s.active ? '700' : '500' }}>{s.label}</Text>
                {s.est && (
                  <View style={{ backgroundColor: (globalThis as any).__alphaColor(C.primary, '15'), paddingHorizontal: 6, paddingVertical: 1, borderRadius: 3 }}>
                    <Text style={{ color: C.primary, fontSize: 8, fontWeight: '600' }}>{s.est}</Text>
                  </View>
                )}
              </View>
              <Text style={{ color: C.muted, fontSize: 10, marginTop: 2 }}>{s.detail}</Text>
              {s.time && <Text style={{ color: C.dim, fontSize: 9, marginTop: 2 }}>{s.time}</Text>}
            </View>
          </View>
        );
      })}
    </View>
  );
}

// ── Drag & Drop File Upload Zone Component ──
function DropZone({ docType, label, icon, data, desc, onFilePicked, C }: {
  docType: string; label: string; icon: string; data: string | null; desc: string;
  onFilePicked: (dataUrl: string) => void; C: any;
}) {
  const [isDragging, setIsDragging] = useState(false);
  const [uploadProgress, setUploadProgress] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const ALLOWED_TYPES = ['image/jpeg', 'image/png', 'image/webp', 'application/pdf'];
  const MAX_SIZE = 5 * 1024 * 1024; // 5MB

  const validateFile = (file: File): string | null => {
    if (!ALLOWED_TYPES.includes(file.type)) return `Invalid format: ${file.type}. Use JPG, PNG, WebP, or PDF.`;
    if (file.size > MAX_SIZE) return `File too large (${(file.size / 1024 / 1024).toFixed(1)}MB). Max: 5MB.`;
    if (file.size < 1024) return 'File too small or corrupted.';
    return null;
  };

  const processFile = (file: File) => {
    setError(null);
    const err = validateFile(file);
    if (err) { setError(err); return; }
    setUploadProgress('Reading...');
    const reader = new FileReader();
    reader.onload = (ev) => {
      const dataUrl = ev.target?.result as string;
      onFilePicked(dataUrl);
      setUploadProgress(null);
    };
    reader.onerror = () => { setError('Failed to read file'); setUploadProgress(null); };
    reader.readAsDataURL(file);
  };

  const handleDrop = useCallback((e: any) => {
    e.preventDefault(); e.stopPropagation(); setIsDragging(false);
    const file = e.dataTransfer?.files?.[0];
    if (file) processFile(file);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleDragOver = useCallback((e: any) => { e.preventDefault(); e.stopPropagation(); setIsDragging(true); }, []);
  const handleDragLeave = useCallback((e: any) => { e.preventDefault(); e.stopPropagation(); setIsDragging(false); }, []);

  const openFilePicker = () => {
    if (Platform.OS !== 'web') return;
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = 'image/jpeg,image/png,image/webp,application/pdf';
    input.onchange = (e: any) => {
      const file = e.target?.files?.[0];
      if (file) processFile(file);
    };
    input.click();
  };

  if (Platform.OS !== 'web') return null;

  return (
    <div
      onDrop={handleDrop}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onClick={openFilePicker}
      data-testid={`idv-dropzone-${docType}`}
      style={{
        cursor: 'pointer',
        marginBottom: 10,
        borderRadius: 12,
        border: `2px dashed ${isDragging ? C.primary : data ? C.success + '80' : C.border}`,
        backgroundColor: isDragging ? (globalThis as any).__alphaColor(C.primary, '08') : data ? C.success + '06' : 'transparent',
        padding: 14,
        display: 'flex',
        flexDirection: 'row',
        alignItems: 'center',
        gap: 12,
        transition: 'all 0.15s ease',
      } as any}
    >
      {data ? (
        <div style={{ width: 52, height: 52, borderRadius: 10, overflow: 'hidden', flexShrink: 0 }}>
          <img src={data} style={{ width: 52, height: 52, objectFit: 'cover', borderRadius: 10 }} />
        </div>
      ) : (
        <View style={{
          width: 52, height: 52, borderRadius: 10,
          backgroundColor: isDragging ? (globalThis as any).__alphaColor(C.primary, '20') : C.primary + '10',
          alignItems: 'center', justifyContent: 'center',
        }}>
          <Ionicons name={icon as any} size={24} color={C.primary} />
        </View>
      )}
      <View style={{ flex: 1 }}>
        <Text style={{ color: C.text, fontSize: 13, fontWeight: '700' }}>{label}</Text>
        {uploadProgress ? (
          <ProfileFormSkeleton />
        ) : error ? (
          <Text style={{ color: C.error, fontSize: 10, marginTop: 2 }}>{error}</Text>
        ) : (
          <Text style={{ color: data ? C.success : C.dim, fontSize: 10, marginTop: 2 }}>
            {data ? 'Uploaded! Click or drop to replace' : isDragging ? 'Drop file here...' : desc + ' — drag & drop or click'}
          </Text>
        )}
      </View>
      <View style={{
        width: 32, height: 32, borderRadius: 16,
        backgroundColor: (globalThis as any).__alphaColor(data ? C.success : isDragging ? C.primary : C.primary, '20'),
        alignItems: 'center', justifyContent: 'center',
      }}>
        <Ionicons name={data ? 'checkmark' : isDragging ? 'download' : 'cloud-upload'} size={16} color={data || isDragging ? C.primaryText : C.primary} />
      </View>
    </div>
  );
}

export default function IDVerificationPage() {
  const router = useRouter();
  const { user, isAuthenticated } = useAuth();
  const { colors } = useTheme();
  const { t } = useTranslation();
  const tx = useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);
  const C = useMemo(() => ({
    ...colors,
    bg: colors.bg, card: colors.card, cardAlt: colors.bgSoft, text: colors.text,
    muted: colors.textSec, dim: colors.textMuted, border: colors.border,
    primary: colors.primary, success: colors.success, warning: colors.warning, error: colors.error,
  }), [colors]);

  const [step, setStep] = useState<Step>('info');
  const [kycStatus, setKycStatus] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [emailLogs, setEmailLogs] = useState<any[]>([]);
  const [notifPrefs, setNotifPrefs] = useState({ email: true, sms: true });

  // Form fields
  const [fullName, setFullName] = useState('');
  const [dob, setDob] = useState('');
  const [nationality, setNationality] = useState('');
  const [idType, setIdType] = useState('national_id');
  const [idNumber, setIdNumber] = useState('');
  const [address, setAddress] = useState('');
  const [phone, setPhone] = useState('');

  // Document captures (mobile)
  const [idFront, setIdFront] = useState<string | null>(null);
  const [idBack, setIdBack] = useState<string | null>(null);
  const [selfie, setSelfie] = useState<string | null>(null);

  // QR session (desktop)
  const [qrSession, setQrSession] = useState<{ session_id: string; token: string; expires_in: number } | null>(null);
  const [qrStatus, setQrStatus] = useState<string>('idle'); // idle, pending, uploading, complete, expired
  const [qrDocs, setQrDocs] = useState<Record<string, any>>({});
  const [qrCountdown, setQrCountdown] = useState(0);
  const pageTitle = t('kyc.header.title');

  useEffect(() => { if (isAuthenticated) loadStatus(); }, [isAuthenticated]);

  async function loadStatus() {
    try {
      const r = await api.get('/id-checker/kyc/status');
      setKycStatus(r.data.kyc);
    } catch (error) { handleAppRecoverableError({ scope: 'subscription/kyc.tsx#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); } finally { setLoading(false); }
  }

  // Fetch email/SMS logs and notification prefs when KYC status is loaded
  useEffect(() => {
    if (kycStatus) {
      api.get('/id-checker/kyc/email-log')
        .then((r: any) => setEmailLogs(r.data.notifications || []))
        .catch((error) => {
          handleAppRecoverableError({
            scope: 'subscription.kyc.load-email-log',
            error,
            message: 'Unable to load KYC notification history.',
            setError,
          
        notifyMode: 'silent',
      });
        });
      api.get('/id-checker/kyc/notification-prefs')
        .then((r: any) => setNotifPrefs(r.data.preferences || { email: true, sms: true }))
        .catch((error) => {
          handleAppRecoverableError({
            scope: 'subscription.kyc.load-notification-prefs',
            error,
            message: 'Unable to load KYC notification preferences.',
            setError,
          
        notifyMode: 'silent',
      });
        });
    }
  }, [kycStatus]);

  // --- QR Session Management ---
  const createQrSession = async () => {
    try {
      const r = await api.post('/id-checker/qr/create');
      setQrSession(r.data);
      setQrStatus('pending');
      setQrCountdown(r.data.expires_in);
      setQrDocs({});
    } catch (e: any) {
      handleAppRecoverableError({
        scope: 'subscription.kyc.create-qr-session',
        error: e,
        message: 'Failed to create QR session',
        setError,
        onRetry: () => { void createQrSession(); },
      
        notifyMode: 'dialog',
        userInitiated: true,
      });
      alert('Failed to create QR session');
    }
  };

  // Countdown timer
  useEffect(() => {
    if (qrCountdown <= 0 || qrStatus === 'complete') return;
    const timer = setInterval(() => {
      setQrCountdown(prev => {
        if (prev <= 1) { setQrStatus('expired'); clearInterval(timer); return 0; }
        return prev - 1;
      });
    }, 1000);
    return () => clearInterval(timer);
  }, [qrCountdown, qrStatus]);

  // Poll for QR session status
  useEffect(() => {
    if (!qrSession || qrStatus === 'complete' || qrStatus === 'expired') return;
    const poll = setInterval(async () => {
      try {
        const r = await api.get(`/id-checker/qr/status/${qrSession.session_id}`);
        const s = r.data.status;
        setQrStatus(s);
        setQrDocs(r.data.documents || {});
        if (s === 'complete') { clearInterval(poll); loadStatus(); }
        if (s === 'expired') clearInterval(poll);
      } catch (error) { handleAppRecoverableError({ scope: 'subscription/kyc.tsx#catch2', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
    }, 3000);
    return () => clearInterval(poll);
  }, [qrSession, qrStatus]);

  const getQrUrl = () => {
    if (!qrSession) return '';
    const base = Platform.OS === 'web' ? `https://${window.location.host}` : '';
    return `${base}/id-verify-mobile?sid=${qrSession.session_id}&token=${qrSession.token}`;
  };

  // --- Mobile Camera Capture ---
  const handleCapture = useCallback((type: 'front' | 'back' | 'selfie') => {
    if (Platform.OS !== 'web') return;
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = 'image/*';
    if (isMobileDevice) input.setAttribute('capture', type === 'selfie' ? 'user' : 'environment');
    input.onchange = (e: any) => {
      const file = e.target?.files?.[0];
      if (!file) return;
      const reader = new FileReader();
      reader.onload = (ev) => {
        const dataUrl = ev.target?.result as string;
        if (type === 'front') setIdFront(dataUrl);
        else if (type === 'back') setIdBack(dataUrl);
        else setSelfie(dataUrl);
      };
      reader.readAsDataURL(file);
    };
    input.click();
  }, []);

  const submitVerification = async () => {
    if (!fullName || !dob || !nationality || !idNumber || !address || !phone) {
      alert('Please fill all required fields'); return;
    }
    setSubmitting(true);
    try {
      const hasDocuments = idFront || idBack || selfie || qrStatus === 'complete';
      const r = await api.post('/id-checker/kyc/submit', {
        full_name: fullName, date_of_birth: dob, nationality, id_type: idType,
        id_number: idNumber, address, phone, level: hasDocuments ? 2 : 1,
      });
      setKycStatus(r.data.kyc);

      // Upload docs using the proper file upload endpoint
      const docs = [
        { type: 'id_front', data: idFront },
        { type: 'id_back', data: idBack },
        { type: 'selfie', data: selfie },
      ].filter(d => d.data);

      for (const doc of docs) {
        try {
          // Convert data URL to File/Blob and upload via multipart form
          const dataUrl = doc.data!;
          const resp = await fetch(dataUrl);
          const blob = await resp.blob();
          const ext = blob.type.includes('png') ? 'png' : blob.type.includes('webp') ? 'webp' : 'jpg';
          const formData = new FormData();
          formData.append('document_type', doc.type);
          formData.append('file', blob, `${doc.type}.${ext}`);
          await api.post('/id-checker/kyc/upload-file', formData, {
            headers: { 'Content-Type': 'multipart/form-data' },
          });
        } catch (uploadErr: any) {
          handleAppRecoverableError({
            scope: 'subscription.kyc.upload-document',
            error: uploadErr,
            message: `Failed to upload ${doc.type}.`,
            setError,
          
        notifyMode: 'silent',
      });
        }
      }

      const status = r.data.kyc?.status;
      if (status === 'verified') alert('ID Verified! You now have full access.');
      else if (status === 'rejected') alert('Verification rejected: ' + (r.data.auto_verification?.issues?.join(', ') || 'Please check your information'));
      else if (r.data.days_remaining) alert(`Retry available in ${r.data.days_remaining} days.`);
      else alert('ID Checker submitted for review.');
      loadStatus();
    } catch (e: any) {
      const message = e?.response?.data?.detail || 'Submission failed';
      handleAppRecoverableError({
        scope: 'subscription.kyc.submit',
        error: e,
        message,
        setError,
        onRetry: () => { void submitVerification(); },
      
        notifyMode: 'dialog',
        userInitiated: true,
      });
      alert(message);
    }
    finally { setSubmitting(false); }
  };

  if (!isAuthenticated) {
    return (
      <AppShell><View style={{ flex: 1, alignItems: 'center', justifyContent: 'center', backgroundColor: C.bg }}>
        <Ionicons name="lock-closed" size={40} color={C.dim} />
        <Text style={{ color: C.text, fontSize: 18, fontWeight: '700', marginTop: 12 }}>{t("autofix.watchSweep1.login.required")}</Text>
      </View></AppShell>
    );
  }

  if (loading) return (
    <AppShell><ProfileFormSkeleton /></AppShell>
  );

  const isVerified = kycStatus?.status === 'verified';
  const isPending = kycStatus?.status === 'pending_review';
  const isRejected = kycStatus?.status === 'rejected';
  const isBanned = kycStatus?.status === 'banned';
  const statusColor = isVerified ? C.success : isPending ? C.warning : isRejected ? C.error : isBanned ? C.error : C.dim;
  const statusLabel = isVerified ? 'VERIFIED' : isPending ? 'PENDING REVIEW' : isRejected ? 'REJECTED' : isBanned ? 'BANNED' : 'NOT SUBMITTED';
  const canRetry = isRejected && kycStatus?.retry_available_date ? new Date(kycStatus.retry_available_date) <= new Date() : !isRejected;
  const stepIndex = STEPS.findIndex(s => s.key === step);

  const formatCountdown = (s: number) => `${Math.floor(s / 60)}:${(s % 60).toString().padStart(2, '0')}`;

  return (
    <AppShell>
      <ScrollView style={{ flex: 1, backgroundColor: C.bg }} contentContainerStyle={{ padding: 20, maxWidth: 960, alignSelf: 'center', width: '100%' }}>
        {/* Header */}
        <TouchableOpacity onPress={() => router.back()} style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 16 }} data-testid="idv-back-btn" testID="idv-back-btn">
          <Ionicons name="arrow-back" size={20} color={C.muted} />
          <Text style={{ color: C.muted, fontSize: 13 }}>{tx('kyc.common.back', 'Back')}</Text>
        </TouchableOpacity>

        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 20 }}>
          <View style={{ width: 44, height: 44, borderRadius: 22, backgroundColor: (globalThis as any).__alphaColor(statusColor, '20'), alignItems: 'center', justifyContent: 'center' }}>
            <Ionicons name={isVerified ? 'shield-checkmark' : 'finger-print'} size={22} color={statusColor} />
          </View>
          <View style={{ flex: 1 }}>
            <Text style={{ color: C.text, fontSize: 20, fontWeight: '800' }} data-testid="idv-title" testID="idv-title">{pageTitle === 'kyc.header.title' ? 'ID Checker' : pageTitle}</Text>
            <Text style={{ color: C.muted, fontSize: 12 }}>{t("autofix.watchSweep1.verify.your.identity.for.full.platform.access")}</Text>
          </View>
          <View style={{ backgroundColor: (globalThis as any).__alphaColor(statusColor, '20'), paddingHorizontal: 10, paddingVertical: 4, borderRadius: 8 }}>
            <Text style={{ color: statusColor, fontSize: 9, fontWeight: '800' }} data-testid="idv-status-badge" testID="idv-status-badge">{statusLabel}</Text>
          </View>
        </View>

        {/* Status Card */}
        {kycStatus && (
          <View style={{ backgroundColor: C.card, borderRadius: 14, padding: 16, marginBottom: 16, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(statusColor, '40') }} data-testid="idv-status-card" testID="idv-status-card">
            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
              {[
                { label: 'Level', value: `Level ${kycStatus.level || 1}` },
                { label: 'Rule Score', value: kycStatus.auto_verification?.score != null ? `${kycStatus.auto_verification.score}/100` : 'N/A' },
                { label: 'Status', value: statusLabel },
                { label: 'AI Score', value: kycStatus.ai_verification?.confidence_score != null ? `${Math.round(kycStatus.ai_verification.confidence_score * 100)}%` : 'Pending' },
                ...(kycStatus.combined_score != null ? [{ label: 'Combined', value: `${Math.round(kycStatus.combined_score * 100)}%` }] : []),
                ...(isRejected && kycStatus.retry_available_date ? [{ label: 'Retry Available', value: new Date(kycStatus.retry_available_date).toLocaleDateString() }] : []),
              ].map(s => (
                <View key={s.label} style={{ width: '48%', backgroundColor: C.cardAlt, borderRadius: 10, padding: 10 }}>
                  <Text style={{ color: C.dim, fontSize: 9 }}>{s.label}</Text>
                  <Text style={{ color: C.text, fontSize: 13, fontWeight: '700' }}>{s.value}</Text>
                </View>
              ))}
            </View>

            {/* AI Verification Analysis */}
            {kycStatus.ai_verification && kycStatus.ai_verification.analyzer !== 'fallback' && (
              <View style={{ marginTop: 12 }}>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 8 }}>
                  <View style={{ width: 20, height: 20, borderRadius: 10, backgroundColor: (globalThis as any).__alphaColor(C.primary, '20'), alignItems: 'center', justifyContent: 'center' }}>
                    <Ionicons name="sparkles" size={12} color={C.primary} />
                  </View>
                  <Text style={{ color: C.text, fontSize: 12, fontWeight: '700' }}>{t("autofix.watchSweep1.ai.verification.analysis")}</Text>
                  <View style={{ backgroundColor: kycStatus.ai_verification.risk_level === 'low' ? (globalThis as any).__alphaColor(C.success, '20') : kycStatus.ai_verification.risk_level === 'medium' ? C.warning + '20' : C.error + '20', paddingHorizontal: 6, paddingVertical: 2, borderRadius: 4 }}>
                    <Text style={{ color: kycStatus.ai_verification.risk_level === 'low' ? C.success : kycStatus.ai_verification.risk_level === 'medium' ? C.warning : C.error, fontSize: 8, fontWeight: '800', textTransform: 'uppercase' }}>{kycStatus.ai_verification.risk_level}{t("autofix.watchSweep1.risk.2")}</Text>
                  </View>
                </View>

                {/* AI Checks */}
                {kycStatus.ai_verification.checks?.map((check: any, i: number) => (
                  <View key={i} style={{ flexDirection: 'row', alignItems: 'flex-start', gap: 8, paddingVertical: 6, borderBottomWidth: i < kycStatus.ai_verification.checks.length - 1 ? 1 : 0, borderBottomColor: C.border }} data-testid={`idv-ai-check-${check.check}`} testID={`idv-ai-check-${check.check}`}>
                    <Ionicons name={check.passed ? 'checkmark-circle' : 'alert-circle'} size={16} color={check.passed ? C.success : C.warning} style={{ marginTop: 1 }} />
                    <View style={{ flex: 1 }}>
                      <Text style={{ color: C.text, fontSize: 11, fontWeight: '600' }}>{check.check.replace(/_/g, ' ').replace(/\b\w/g, (c: string) => c.toUpperCase())}</Text>
                      <Text style={{ color: C.muted, fontSize: 10, marginTop: 2 }}>{check.detail}</Text>
                    </View>
                  </View>
                ))}

                {/* AI Summary */}
                {kycStatus.ai_verification.summary && (
                  <View style={{ backgroundColor: (globalThis as any).__alphaColor(C.primary, '08'), borderRadius: 8, padding: 10, marginTop: 8, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(C.primary, '20') }}>
                    <Text style={{ color: C.primary, fontSize: 10, fontWeight: '700', marginBottom: 2 }}>{t("autofix.watchSweep1.ai.summary")}</Text>
                    <Text style={{ color: C.muted, fontSize: 10, lineHeight: 15 }}>{kycStatus.ai_verification.summary}</Text>
                  </View>
                )}

                {/* AI Flags */}
                {kycStatus.ai_verification.flags?.length > 0 && (
                  <View style={{ backgroundColor: (globalThis as any).__alphaColor(C.warning, '10'), borderRadius: 8, padding: 10, marginTop: 6, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(C.warning, '20') }}>
                    <Text style={{ color: C.warningText, fontSize: 10, fontWeight: '700', marginBottom: 2 }}>{t("autofix.watchSweep1.flags")}</Text>
                    {kycStatus.ai_verification.flags.map((flag: string, i: number) => (
                      <Text key={i} style={{ color: C.warningText, fontSize: 10 }}>- {flag}</Text>
                    ))}
                  </View>
                )}

                <Text style={{ color: C.dim, fontSize: 8, marginTop: 6, textAlign: 'right' }}>{t("autofix.watchSweep1.analyzed.by")}{kycStatus.ai_verification.analyzer} at {new Date(kycStatus.ai_verification.analyzed_at).toLocaleString()}
                </Text>
              </View>
            )}

            {/* Request AI Analysis button for pending submissions without AI analysis */}
            {isPending && (!kycStatus.ai_verification || kycStatus.ai_verification.analyzer === 'fallback') && (
              <TouchableOpacity
                onPress={async () => {
                  try {
                    setSubmitting(true);
                    const r = await api.post('/id-checker/kyc/ai-verify');
                    setKycStatus(r.data.kyc);
                    alert(r.data.ai_result?.ai_analysis?.summary || 'AI analysis complete');
                  } catch (e: any) {
                    const message = e?.response?.data?.detail || 'AI analysis failed';
                    handleAppRecoverableError({
                      scope: 'subscription.kyc.ai-analysis',
                      error: e,
                      message,
                      setError,
                      onRetry: async () => {
                        const r = await api.post('/id-checker/kyc/ai-verify');
                        setKycStatus(r.data.kyc);
                      },
                    
        notifyMode: 'dialog',
        userInitiated: true,
      });
                    alert(message);
                  }
                  finally { setSubmitting(false); }
                }}
                disabled={submitting}
                style={{ backgroundColor: C.primary, borderRadius: 10, paddingVertical: 12, alignItems: 'center', marginTop: 12, opacity: submitting ? 0.6 : 1 }}
                data-testid="idv-request-ai-analysis-btn" testID="idv-request-ai-analysis-btn"
              >
                {submitting ? <ActivityIndicator color={C.primaryText} size="small" /> : (
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                    <Ionicons name="sparkles" size={16} color={C.primaryText} />
                    <Text style={{ color: C.primaryText, fontSize: 13, fontWeight: '700' }}>{t("autofix.watchSweep1.request.ai.analysis")}</Text>
                  </View>
                )}
              </TouchableOpacity>
            )}

            {kycStatus.auto_verification?.issues?.length > 0 && (
              <View style={{ backgroundColor: (globalThis as any).__alphaColor(C.error, '15'), borderRadius: 10, padding: 10, marginTop: 10 }}>
                <Text style={{ color: C.error, fontSize: 10, fontWeight: '700', marginBottom: 4 }}>{t("autofix.watchSweep1.issues.found")}</Text>
                {kycStatus.auto_verification.issues.map((issue: string, i: number) => (
                  <Text key={i} style={{ color: C.error, fontSize: 11, marginLeft: 8 }}>- {issue}</Text>
                ))}
              </View>
            )}
            {isRejected && !canRetry && (
              <View style={{ backgroundColor: (globalThis as any).__alphaColor(C.warning, '15'), borderRadius: 10, padding: 10, marginTop: 10 }}>
                <Text style={{ color: C.warningText, fontSize: 11, fontWeight: '600' }}>{t("autofix.watchSweep1.retry.available.on")}{new Date(kycStatus.retry_available_date).toLocaleDateString()}{t("autofix.watchSweep1.you.may.also.wait.for.support.review")}</Text>
              </View>
            )}
          </View>
        )}

        {/* Verification Journey Timeline */}
        {kycStatus && !isBanned && (
          <VerificationTimeline kyc={kycStatus} C={C} />
        )}

        {isBanned && (
          <View style={{ backgroundColor: (globalThis as any).__alphaColor(C.error, '20'), borderRadius: 14, padding: 20, alignItems: 'center', borderWidth: 1, borderColor: (globalThis as any).__alphaColor(C.error, '40') }}>
            <Ionicons name="ban" size={36} color={C.error} />
            <Text style={{ color: C.error, fontSize: 16, fontWeight: '800', marginTop: 8 }}>{t("autofix.watchSweep1.account.banned")}</Text>
            <Text style={{ color: C.muted, fontSize: 12, marginTop: 4, textAlign: 'center' }}>{t("autofix.watchSweep1.your.account.has.been.banned.contact.support.for")}</Text>
          </View>
        )}

        {isVerified && (
          <View style={{ backgroundColor: (globalThis as any).__alphaColor(C.success, '15'), borderRadius: 14, padding: 20, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(C.success, '40'), alignItems: 'center' }} data-testid="idv-verified-banner" testID="idv-verified-banner">
            <Ionicons name="shield-checkmark" size={36} color={C.successText} />
            <Text style={{ color: C.successText, fontSize: 16, fontWeight: '800', marginTop: 8 }}>{t("idVerification.verified.title")}</Text>
            <Text style={{ color: C.muted, fontSize: 11, marginTop: 4, textAlign: 'center' }}>{t("autofix.watchSweep1.your.id.checker.level")}{kycStatus?.level}{t("autofix.watchSweep1.is.complete.you.have.full.platform.access")}</Text>
          </View>
        )}

        {/* Notification History & Preferences */}
        {kycStatus && (
          <View style={{ backgroundColor: C.card, borderRadius: 14, padding: 16, marginTop: 16, borderWidth: 1, borderColor: C.border }} data-testid="idv-notification-section" testID="idv-notification-section">
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 12 }}>
              <View style={{ width: 28, height: 28, borderRadius: 14, backgroundColor: (globalThis as any).__alphaColor(C.primary, '15'), alignItems: 'center', justifyContent: 'center' }}>
                <Ionicons name="notifications" size={15} color={C.primary} />
              </View>
              <Text style={{ color: C.text, fontSize: 14, fontWeight: '700' }}>{t("nav.notifications")}</Text>
              {emailLogs.length > 0 && (
                <View style={{ backgroundColor: (globalThis as any).__alphaColor(C.primary, '15'), paddingHorizontal: 6, paddingVertical: 2, borderRadius: 4, marginLeft: 'auto' }}>
                  <Text style={{ color: C.primary, fontSize: 8, fontWeight: '800' }}>{emailLogs.length} SENT</Text>
                </View>
              )}
            </View>

            {/* Notification Preferences */}
            <View style={{ flexDirection: 'row', gap: 10, marginBottom: 14 }} data-testid="idv-notif-prefs" testID="idv-notif-prefs">
              {[
                { key: 'email', icon: 'mail' as const, label: 'Email' },
                { key: 'sms', icon: 'chatbubble' as const, label: 'SMS' },
              ].map(ch => {
                const enabled = (notifPrefs as any)[ch.key];
                return (
                  <TouchableOpacity
                    key={ch.key}
                    onPress={async () => {
                      const newPrefs = { ...notifPrefs, [ch.key]: !enabled };
                      setNotifPrefs(newPrefs);
                      try {
                        await api.put('/id-checker/kyc/notification-prefs', newPrefs);
                      } catch (error) { handleAppRecoverableError({ scope: 'subscription/kyc.tsx#catch3', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
                    }}
                    style={{
                      flex: 1,
                      flexDirection: 'row',
                      alignItems: 'center',
                      gap: 8,
                      paddingVertical: 10,
                      paddingHorizontal: 12,
                      borderRadius: 10,
                      backgroundColor: enabled ? (globalThis as any).__alphaColor(C.primary, '12') : C.cardAlt,
                      borderWidth: 1,
                      borderColor: enabled ? (globalThis as any).__alphaColor(C.primary, '40') : C.border,
                    }}
                    data-testid={`idv-notif-toggle-${ch.key}`} testID={`idv-notif-toggle-${ch.key}`}
                  >
                    <Ionicons name={ch.icon} size={16} color={enabled ? C.primary : C.dim} />
                    <Text style={{ color: enabled ? C.text : C.dim, fontSize: 12, fontWeight: '600', flex: 1 }}>{ch.label}</Text>
                    <View style={{
                      width: 36, height: 20, borderRadius: 10,
                      backgroundColor: enabled ? C.primary : C.border,
                      justifyContent: 'center',
                      paddingHorizontal: 2,
                    }}>
                      <View style={{
                        width: 16, height: 16, borderRadius: 8,
                        backgroundColor: C.primaryText,
                        alignSelf: enabled ? 'flex-end' : 'flex-start',
                      }} />
                    </View>
                  </TouchableOpacity>
                );
              })}
            </View>

            {/* Notification Log */}
            {emailLogs.length > 0 ? emailLogs.map((log: any, i: number) => {
              const isEmail = log.channel === 'email' || !log.channel;
              const statusIcon = log.status === 'verified' ? 'checkmark-circle' : log.status === 'rejected' ? 'close-circle' : 'time';
              const statusColor = log.status === 'verified' ? C.success : log.status === 'rejected' ? C.error : C.warning;
              return (
                <View key={i} style={{ flexDirection: 'row', alignItems: 'flex-start', gap: 10, paddingVertical: 8, borderTopWidth: i > 0 ? 1 : 0, borderTopColor: C.border }} data-testid={`idv-notif-log-item-${i}`} testID={`idv-notif-log-item-${i}`}>
                  <View style={{ width: 28, height: 28, borderRadius: 14, backgroundColor: (globalThis as any).__alphaColor(statusColor, '15'), alignItems: 'center', justifyContent: 'center' }}>
                    <Ionicons name={isEmail ? 'mail' : 'chatbubble'} size={13} color={statusColor} />
                  </View>
                  <View style={{ flex: 1 }}>
                    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                      <View style={{ backgroundColor: isEmail ? (globalThis as any).__alphaColor(C.primary, '15') : C.success + '15', paddingHorizontal: 5, paddingVertical: 1, borderRadius: 3 }}>
                        <Text style={{ color: isEmail ? C.primary : C.success, fontSize: 7, fontWeight: '800' }}>{isEmail ? 'EMAIL' : 'SMS'}</Text>
                      </View>
                      <Text style={{ color: C.text, fontSize: 11, fontWeight: '600', flex: 1 }} numberOfLines={1}>{log.subject}</Text>
                    </View>
                    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginTop: 3 }}>
                      <Text style={{ color: C.dim, fontSize: 9 }}>{new Date(log.created_at).toLocaleDateString('en', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}</Text>
                      <View style={{ width: 3, height: 3, borderRadius: 1.5, backgroundColor: C.dim }} />
                      <Text style={{ color: log.sent ? C.success : C.error, fontSize: 9, fontWeight: '600' }}>{log.sent ? 'Delivered' : 'Not configured'}</Text>
                      {!isEmail && log.phone && (
                        <>
                          <View style={{ width: 3, height: 3, borderRadius: 1.5, backgroundColor: C.dim }} />
                          <Text style={{ color: C.dim, fontSize: 9 }}>{log.phone}</Text>
                        </>
                      )}
                    </View>
                  </View>
                </View>
              );
            }) : (
              <View style={{ paddingVertical: 16, alignItems: 'center' }}>
                <Ionicons name="notifications-off" size={24} color={C.dim} />
                <Text style={{ color: C.dim, fontSize: 11, marginTop: 6 }}>{t("autofix.watchSweep1.no.notifications.sent.yet")}</Text>
              </View>
            )}
          </View>
        )}

        {/* Form - only show when can submit */}
        {!isVerified && !isBanned && canRetry && (
          <>
            {/* Progress Steps */}
            <View style={{ flexDirection: 'row', marginBottom: 20, gap: 4 }} data-testid="idv-progress-bar" testID="idv-progress-bar">
              {STEPS.map((s, i) => {
                const isActive = i === stepIndex;
                const isDone = i < stepIndex;
                const barColor = isDone ? C.success : isActive ? C.primary : C.border;
                return (
                  <TouchableOpacity key={s.key} onPress={() => setStep(s.key)} style={{ flex: 1, alignItems: 'center' }} data-testid={`idv-step-${s.key}`} testID={`idv-step-${s.key}`}>
                    <View style={{ flexDirection: 'row', alignItems: 'center', width: '100%', marginBottom: 6 }}>
                      <View style={{ flex: 1, height: 3, backgroundColor: barColor, borderRadius: 2 }} />
                    </View>
                    <View style={{
                      width: 28, height: 28, borderRadius: 14,
                      backgroundColor: isDone ? C.success : isActive ? C.primary : C.card,
                      borderWidth: 2, borderColor: barColor,
                      alignItems: 'center', justifyContent: 'center', marginBottom: 4,
                    }}>
                      <Ionicons name={isDone ? 'checkmark' : s.icon as any} size={14} color={isDone || isActive ? C.primaryText : C.dim} />
                    </View>
                    <Text style={{ color: isActive ? C.primary : C.dim, fontSize: 9, fontWeight: '700' }}>{s.label}</Text>
                  </TouchableOpacity>
                );
              })}
            </View>

            {/* Step 1: Personal Info */}
            {step === 'info' && (
              <View style={{ backgroundColor: C.card, borderRadius: 14, padding: 16, marginBottom: 16, borderWidth: 1, borderColor: C.border }} data-testid="idv-step-info-form" testID="idv-step-info-form">
                <Text style={{ color: C.text, fontSize: 15, fontWeight: '700', marginBottom: 12 }}>{t("idVerification.form.personalInfo")}</Text>
                {[
                  { label: 'Full Legal Name', value: fullName, set: setFullName, placeholder: 'Jean-Pierre Kouassi', testId: 'idv-name' },
                  { label: 'Date of Birth', value: dob, set: setDob, placeholder: 'YYYY-MM-DD', testId: 'idv-dob' },
                  { label: 'Nationality (Country Code)', value: nationality, set: setNationality, placeholder: 'BJ', testId: 'idv-nationality' },
                  { label: 'ID Number', value: idNumber, set: setIdNumber, placeholder: 'BJ123456789', testId: 'idv-id-number' },
                  { label: 'Address', value: address, set: setAddress, placeholder: '123 Rue de Commerce, Cotonou', testId: 'idv-address' },
                  { label: 'Phone Number', value: phone, set: setPhone, placeholder: '+22960123456', testId: 'idv-phone' },
                ].map(f => (
                  <View key={f.label} style={{ marginBottom: 12 }}>
                    <Text style={{ color: C.muted, fontSize: 11, marginBottom: 4 }}>{f.label}</Text>
                    <TextInput value={f.value} onChangeText={f.set} placeholder={f.placeholder} placeholderTextColor={C.dim}
                      style={{ backgroundColor: C.cardAlt, borderRadius: 10, padding: 12, color: C.text, fontSize: 14, borderWidth: 1, borderColor: C.border }}
                      data-testid={f.testId} testID={f.testId} />
                  </View>
                ))}
                <Text style={{ color: C.muted, fontSize: 11, marginBottom: 6 }}>{t("autofix.id.type")}</Text>
                <View style={{ flexDirection: 'row', gap: 6, marginBottom: 16 }}>
                  {[{ id: 'national_id', label: 'National ID' }, { id: 'passport', label: 'Passport' }, { id: 'drivers_license', label: "Driver's License" }].map(t => (
                    <TouchableOpacity key={t.id} onPress={() => setIdType(t.id)} data-testid={`idv-idtype-${t.id}`} testID={`idv-idtype-${t.id}`}
                      style={{ flex: 1, paddingVertical: 10, borderRadius: 10, backgroundColor: idType === t.id ? C.primary : C.cardAlt, alignItems: 'center', borderWidth: 1, borderColor: idType === t.id ? C.primary : C.border }}>
                      <Text style={{ color: idType === t.id ? C.primaryText : C.muted, fontSize: 10, fontWeight: '700' }}>{t.label}</Text>
                    </TouchableOpacity>
                  ))}
                </View>
                <TouchableOpacity onPress={() => setStep('documents')} data-testid="idv-next-to-docs" testID="idv-next-to-docs"
                  style={{ backgroundColor: C.primary, borderRadius: 12, paddingVertical: 14, alignItems: 'center' }}>
                  <Text style={{ color: C.primaryText, fontSize: 14, fontWeight: '700' }}>{t("autofix.watchSweep1.next.upload.documents")}</Text>
                </TouchableOpacity>
              </View>
            )}

            {/* Step 2: Documents - Device-Aware */}
            {step === 'documents' && (
              <View style={{ backgroundColor: C.card, borderRadius: 14, padding: 16, marginBottom: 16, borderWidth: 1, borderColor: C.border }} data-testid="idv-step-docs-form" testID="idv-step-docs-form">
                <Text style={{ color: C.text, fontSize: 15, fontWeight: '700', marginBottom: 4 }}>{t("autofix.watchSweep1.id.documents")}</Text>

                {/* Desktop: Show QR Code or File Upload */}
                {isDesktop && (
                  <>
                    <Text style={{ color: C.muted, fontSize: 11, marginBottom: 16 }}>{t("autofix.watchSweep1.upload.your.id.documents.using.drag.drop.or")}</Text>

                    {/* Drag & Drop File Upload Area */}
                    {Platform.OS === 'web' && (
                      <View style={{ marginBottom: 16 }}>
                        {[
                          { type: 'id_front' as const, label: 'ID Front', icon: 'card', data: idFront, desc: 'Front side of your ID card' },
                          { type: 'id_back' as const, label: 'ID Back', icon: 'card-outline', data: idBack, desc: 'Back side of your ID card' },
                          { type: 'selfie' as const, label: 'Selfie Photo', icon: 'camera', data: selfie, desc: 'A clear photo of your face' },
                        ].map(doc => (
                          <DropZone
                            key={doc.type}
                            docType={doc.type}
                            label={doc.label}
                            icon={doc.icon}
                            data={doc.type === 'id_front' ? idFront : doc.type === 'id_back' ? idBack : selfie}
                            desc={doc.desc}
                            onFilePicked={(dataUrl) => {
                              if (doc.type === 'id_front') setIdFront(dataUrl);
                              else if (doc.type === 'id_back') setIdBack(dataUrl);
                              else setSelfie(dataUrl);
                            }}
                            C={C}
                          />
                        ))}
                      </View>
                    )}

                    {/* QR Code Alternative */}
                    <View style={{ backgroundColor: C.cardAlt, borderRadius: 12, padding: 14, marginBottom: 12 }}>
                      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 8 }}>
                        <Ionicons name="qr-code" size={16} color={C.dim} />
                        <Text style={{ color: C.dim, fontSize: 11, fontWeight: '600' }}>{t("autofix.watchSweep1.or.use.your.phone.via.qr.code")}</Text>
                      </View>

                    {qrStatus === 'idle' || qrStatus === 'expired' ? (
                      <TouchableOpacity onPress={createQrSession} data-testid="idv-generate-qr-btn" testID="idv-generate-qr-btn"
                        style={{ backgroundColor: (globalThis as any).__alphaColor(C.primary, '15'), borderRadius: 10, paddingVertical: 10, alignItems: 'center', borderWidth: 1, borderColor: (globalThis as any).__alphaColor(C.primary, '30') }}>
                        <Text style={{ color: C.primary, fontSize: 12, fontWeight: '700' }}>
                          {qrStatus === 'expired' ? 'Generate New QR Code' : 'Generate QR Code'}
                        </Text>
                      </TouchableOpacity>
                    ) : (
                      <View style={{ alignItems: 'center' }}>
                        <View style={{
                          backgroundColor: C.primaryText, borderRadius: 16, padding: 16, marginBottom: 12,
                          ...(Platform.OS === 'web' ? { boxShadow: '0 2px 8px rgba(0,0,0,0.1)' } : { shadowColor: '#000', shadowOffset: { width: 0, height: 2 }, shadowOpacity: 0.1, shadowRadius: 8 }),
                        }} data-testid="idv-qr-code-display" testID="idv-qr-code-display">
                          <QRCodeSVG value={getQrUrl()} size={200} />
                        </View>
                        <View style={{
                          flexDirection: 'row', alignItems: 'center', gap: 6,
                          backgroundColor: qrCountdown < 30 ? (globalThis as any).__alphaColor(C.error, '15') : C.primary + '15',
                          borderRadius: 20, paddingHorizontal: 14, paddingVertical: 6, marginBottom: 8,
                        }}>
                          <Ionicons name="time" size={14} color={qrCountdown < 30 ? C.error : C.primary} />
                          <Text style={{ color: qrCountdown < 30 ? C.error : C.primary, fontSize: 13, fontWeight: '700' }} data-testid="idv-qr-countdown" testID="idv-qr-countdown">
                            {formatCountdown(qrCountdown)}
                          </Text>
                        </View>
                        <View style={{
                          backgroundColor: qrStatus === 'complete' ? (globalThis as any).__alphaColor(C.success, '15') : qrStatus === 'uploading' ? C.warning + '15' : C.cardAlt,
                          borderRadius: 10, padding: 12, width: '100%', alignItems: 'center',
                        }}>
                          <Ionicons
                            name={qrStatus === 'complete' ? 'checkmark-circle' : qrStatus === 'uploading' ? 'cloud-upload' : 'phone-portrait'}
                            size={20}
                            color={qrStatus === 'complete' ? C.success : qrStatus === 'uploading' ? C.warning : C.dim}
                          />
                          <Text style={{
                            color: qrStatus === 'complete' ? C.success : qrStatus === 'uploading' ? C.warning : C.dim,
                            fontSize: 12, fontWeight: '700', marginTop: 4,
                          }} data-testid="idv-qr-status-text" testID="idv-qr-status-text">
                            {qrStatus === 'complete' ? 'Documents received!' :
                             qrStatus === 'uploading' ? 'Receiving documents...' :
                             'Waiting for phone scan...'}
                          </Text>
                        </View>
                        {Object.keys(qrDocs).length > 0 && (
                          <View style={{ flexDirection: 'row', gap: 8, marginTop: 10, width: '100%' }}>
                            {['id_front', 'id_back', 'selfie'].map(docType => {
                              const received = !!qrDocs[docType];
                              return (
                                <View key={docType} style={{
                                  flex: 1, flexDirection: 'row', alignItems: 'center', gap: 4,
                                  backgroundColor: received ? (globalThis as any).__alphaColor(C.success, '10') : C.cardAlt, borderRadius: 8, padding: 8,
                                }}>
                                  <Ionicons name={received ? 'checkmark-circle' : 'ellipse-outline'} size={14} color={received ? C.success : C.dim} />
                                  <Text style={{ color: received ? C.success : C.dim, fontSize: 9, fontWeight: '600', textTransform: 'capitalize' }}>
                                    {docType.replace('_', ' ')}
                                  </Text>
                                </View>
                              );
                            })}
                          </View>
                        )}
                      </View>
                    )}
                    </View>

                    {qrStatus === 'expired' && (
                      <View style={{ backgroundColor: (globalThis as any).__alphaColor(C.error, '15'), borderRadius: 10, padding: 12, marginBottom: 12, alignItems: 'center' }}>
                        <Ionicons name="alert-circle" size={18} color={C.error} />
                        <Text style={{ color: C.error, fontSize: 11, fontWeight: '600', marginTop: 4 }}>{t("autofix.watchSweep1.qr.code.expired.generate.a.new.one")}</Text>
                      </View>
                    )}
                  </>
                )}

                {/* Mobile: Direct Camera Capture */}
                {!isDesktop && (
                  <>
                    <Text style={{ color: C.muted, fontSize: 11, marginBottom: 16 }}>{t("autofix.watchSweep1.use.your.camera.to.capture.clear.photos.of")}</Text>
                    {[
                      { type: 'front' as const, label: 'ID Front', icon: 'card', data: idFront, desc: 'Clear photo of your ID front side' },
                      { type: 'back' as const, label: 'ID Back', icon: 'card-outline', data: idBack, desc: 'Clear photo of your ID back side' },
                      { type: 'selfie' as const, label: 'Selfie Photo', icon: 'camera', data: selfie, desc: 'A clear selfie of your face' },
                    ].map(doc => (
                      <TouchableOpacity key={doc.type} onPress={() => handleCapture(doc.type)} data-testid={`idv-capture-${doc.type}`} testID={`idv-capture-${doc.type}`}
                        style={{
                          flexDirection: 'row', alignItems: 'center', gap: 12, backgroundColor: doc.data ? (globalThis as any).__alphaColor(C.success, '10') : C.cardAlt,
                          borderRadius: 12, padding: 14, marginBottom: 10, borderWidth: 1,
                          borderColor: doc.data ? (globalThis as any).__alphaColor(C.success, '40') : C.border,
                        }}>
                        {doc.data ? (
                          <View style={{ width: 48, height: 48, borderRadius: 10, overflow: 'hidden' }}>
                            {Platform.OS === 'web' && <img src={doc.data} style={{ width: 48, height: 48, objectFit: 'cover' }} />}
                          </View>
                        ) : (
                          <View style={{ width: 48, height: 48, borderRadius: 10, backgroundColor: (globalThis as any).__alphaColor(C.primary, '15'), alignItems: 'center', justifyContent: 'center' }}>
                            <Ionicons name={doc.icon as any} size={22} color={C.primary} />
                          </View>
                        )}
                        <View style={{ flex: 1 }}>
                          <Text style={{ color: C.text, fontSize: 13, fontWeight: '700' }}>{doc.label}</Text>
                          <Text style={{ color: doc.data ? C.success : C.dim, fontSize: 10 }}>
                            {doc.data ? 'Captured - Tap to retake' : doc.desc}
                          </Text>
                        </View>
                        <Ionicons name={doc.data ? 'checkmark-circle' : 'camera'} size={20} color={doc.data ? C.success : C.primary} />
                      </TouchableOpacity>
                    ))}
                  </>
                )}

                <View style={{ flexDirection: 'row', gap: 8, marginTop: 8 }}>
                  <TouchableOpacity onPress={() => setStep('info')} data-testid="idv-back-to-info" testID="idv-back-to-info"
                    style={{ flex: 1, borderRadius: 12, paddingVertical: 14, alignItems: 'center', borderWidth: 1, borderColor: C.border }}>
                    <Text style={{ color: C.muted, fontSize: 14, fontWeight: '700' }}>{t("careers.offerConfirm.actions.back")}</Text>
                  </TouchableOpacity>
                  <TouchableOpacity onPress={() => setStep('review')} data-testid="idv-next-to-review" testID="idv-next-to-review"
                    style={{ flex: 2, backgroundColor: C.primary, borderRadius: 12, paddingVertical: 14, alignItems: 'center' }}>
                    <Text style={{ color: C.primaryText, fontSize: 14, fontWeight: '700' }}>{t("autofix.watchSweep1.next.review")}</Text>
                  </TouchableOpacity>
                </View>
              </View>
            )}

            {/* Step 3: Review & Submit */}
            {step === 'review' && (
              <View style={{ backgroundColor: C.card, borderRadius: 14, padding: 16, marginBottom: 16, borderWidth: 1, borderColor: C.border }} data-testid="idv-step-review" testID="idv-step-review">
                <Text style={{ color: C.text, fontSize: 15, fontWeight: '700', marginBottom: 12 }}>{t("autofix.watchSweep1.review.your.submission")}</Text>
                {[
                  { label: 'Name', value: fullName },
                  { label: 'Date of Birth', value: dob },
                  { label: 'Nationality', value: nationality },
                  { label: 'ID Type', value: idType.replace('_', ' ') },
                  { label: 'ID Number', value: idNumber ? '***' + idNumber.slice(-4) : '' },
                  { label: 'Address', value: address },
                  { label: 'Phone', value: phone },
                ].map(r => (
                  <View key={r.label} style={{ flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 8, borderBottomWidth: 1, borderBottomColor: C.border }}>
                    <Text style={{ color: C.dim, fontSize: 12 }}>{r.label}</Text>
                    <Text style={{ color: C.text, fontSize: 12, fontWeight: '600' }}>{r.value || '-'}</Text>
                  </View>
                ))}
                <View style={{ flexDirection: 'row', gap: 8, marginTop: 12 }}>
                  {isDesktop ? (
                    // Desktop: Show QR sync status
                    <View style={{ flex: 1, flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: qrStatus === 'complete' ? (globalThis as any).__alphaColor(C.success, '10') : C.cardAlt, borderRadius: 8, padding: 10 }}>
                      <Ionicons name={qrStatus === 'complete' ? 'checkmark-circle' : 'qr-code'} size={16} color={qrStatus === 'complete' ? C.success : C.dim} />
                      <Text style={{ color: qrStatus === 'complete' ? C.success : C.dim, fontSize: 10, fontWeight: '600' }}>
                        {qrStatus === 'complete' ? `${Object.keys(qrDocs).length} docs via QR` : 'No QR docs synced'}
                      </Text>
                    </View>
                  ) : (
                    // Mobile: Show capture status
                    <>
                      {[
                        { type: 'ID Front', ok: !!idFront },
                        { type: 'ID Back', ok: !!idBack },
                        { type: 'Selfie', ok: !!selfie },
                      ].map(d => (
                        <View key={d.type} style={{ flex: 1, flexDirection: 'row', alignItems: 'center', gap: 4, backgroundColor: d.ok ? (globalThis as any).__alphaColor(C.success, '10') : C.cardAlt, borderRadius: 8, padding: 8 }}>
                          <Ionicons name={d.ok ? 'checkmark-circle' : 'close-circle'} size={14} color={d.ok ? C.success : C.dim} />
                          <Text style={{ color: d.ok ? C.success : C.dim, fontSize: 9, fontWeight: '600' }}>{d.type}</Text>
                        </View>
                      ))}
                    </>
                  )}
                </View>
                <View style={{ flexDirection: 'row', gap: 8, marginTop: 16 }}>
                  <TouchableOpacity onPress={() => setStep('documents')} data-testid="idv-back-to-docs" testID="idv-back-to-docs"
                    style={{ flex: 1, borderRadius: 12, paddingVertical: 14, alignItems: 'center', borderWidth: 1, borderColor: C.border }}>
                    <Text style={{ color: C.muted, fontSize: 14, fontWeight: '700' }}>{t("careers.offerConfirm.actions.back")}</Text>
                  </TouchableOpacity>
                  <TouchableOpacity onPress={submitVerification} disabled={submitting} data-testid="idv-submit-btn" testID="idv-submit-btn"
                    style={{ flex: 2, backgroundColor: C.success, borderRadius: 12, paddingVertical: 14, alignItems: 'center', opacity: submitting ? 0.6 : 1 }}>
                    {submitting ? <ActivityIndicator color={C.primaryText} /> : (
                      <Text style={{ color: C.primaryText, fontSize: 14, fontWeight: '800' }}>{t("autofix.watchSweep1.submit.id")}</Text>
                    )}
                  </TouchableOpacity>
                </View>
              </View>
            )}
          </>
        )}
      </ScrollView>
    </AppShell>
  );
}
