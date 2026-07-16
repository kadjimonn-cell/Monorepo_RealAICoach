import React, { useEffect, useMemo, useState, useCallback } from 'react';
import { View, Text, ScrollView, TouchableOpacity, ActivityIndicator, Platform} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useTheme } from '../src/context/ThemeContext';
import { SafeAreaView } from 'react-native-safe-area-context';
import { ProfileFormSkeleton } from '../src/components/SkeletonLoaders';
import { useTranslation } from '../src/hooks/useTranslation';

const API_BASE = Platform.OS === 'web' && typeof window !== 'undefined'
  ? (`https://${window.location.host}`) + '/api'
  : '';

export default function MobileQRVerifyPage() {
  const { t } = useTranslation();
  t('i18n.route.id-verify-mobile.probe');
  const { colors } = useTheme();
  const C = useMemo(() => ({
    ...colors,
    bg: colors.bg, card: colors.card, cardAlt: colors.bgSoft, text: colors.text,
    muted: colors.textSec, dim: colors.textMuted, border: colors.border,
    primary: colors.primary, success: colors.success, error: colors.error,
  }), [colors]);

  const [sessionId, setSessionId] = useState('');
  const [token, setToken] = useState('');
  const [valid, setValid] = useState<boolean | null>(null);
  const [reason, setReason] = useState('');
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [completed, setCompleted] = useState(false);

  const [idFront, setIdFront] = useState<string | null>(null);
  const [idBack, setIdBack] = useState<string | null>(null);
  const [selfie, setSelfie] = useState<string | null>(null);
  const onPrimary = C.primaryText || C.buttonText || C.card;

  // Parse URL params
  useEffect(() => {
    if (Platform.OS !== 'web') return;
    const params = new URLSearchParams(window.location.search);
    const sid = params.get('sid') || '';
    const tok = params.get('token') || '';
    setSessionId(sid);
    setToken(tok);
    if (sid && tok) validateSession(sid, tok);
    else { setValid(false); setReason('Missing session parameters'); setLoading(false); }
  }, []);

  const validateSession = async (sid: string, tok: string) => {
    try {
      const res = await fetch(`${API_BASE}/id-checker/qr/mobile/${sid}?token=${tok}`);
      const data = await res.json();
      setValid(data.valid);
      if (!data.valid) setReason(data.reason || 'Invalid session');
    } catch { setValid(false); setReason('Connection error'); }
    finally { setLoading(false); }
  };

  const capturePhoto = useCallback((type: 'front' | 'back' | 'selfie') => {
    if (Platform.OS !== 'web') return;
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = 'image/*';
    input.setAttribute('capture', type === 'selfie' ? 'user' : 'environment');
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

  const uploadAndComplete = async () => {
    if (!idFront && !idBack && !selfie) {
      alert('Please capture at least one document photo');
      return;
    }
    setUploading(true);
    try {
      const docs = [
        { type: 'id_front', data: idFront },
        { type: 'id_back', data: idBack },
        { type: 'selfie', data: selfie },
      ].filter(d => d.data);

      for (const doc of docs) {
        await fetch(`${API_BASE}/id-checker/qr/upload/${sessionId}?token=${token}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ document_type: doc.type, document_data: doc.data?.substring(0, 200) }),
        });
      }

      await fetch(`${API_BASE}/id-checker/qr/complete/${sessionId}?token=${token}`, {
        method: 'POST',
      });

      setCompleted(true);
    } catch (_e) {
      alert('Upload failed. Please try again.');
    } finally { setUploading(false); }
  };

  if (loading) return (
    <SafeAreaView style={{ flex: 1, backgroundColor: C.bg }}>
      <ProfileFormSkeleton />
    </SafeAreaView>
  );

  if (!valid) return (
    <SafeAreaView style={{ flex: 1, backgroundColor: C.bg, alignItems: 'center', justifyContent: 'center', padding: 24 }}>
      <View style={{ width: 64, height: 64, borderRadius: 32, backgroundColor: (globalThis as any).__alphaColor(C.error, '20'), alignItems: 'center', justifyContent: 'center', marginBottom: 16 }}>
        <Ionicons name="alert-circle" size={32} color={C.error} />
      </View>
      <Text style={{ color: C.text, fontSize: 18, fontWeight: '800', marginBottom: 8 }} data-testid="qr-mobile-invalid-title" testID="qr-mobile-invalid-title">Session Invalid</Text>
      <Text style={{ color: C.muted, fontSize: 13, textAlign: 'center' }} data-testid="qr-mobile-invalid-reason" testID="qr-mobile-invalid-reason">{reason}</Text>
      <Text style={{ color: C.dim, fontSize: 11, marginTop: 16, textAlign: 'center' }}>
        Go back to your desktop and generate a new QR code.
      </Text>
    </SafeAreaView>
  );

  if (completed) return (
    <SafeAreaView style={{ flex: 1, backgroundColor: C.bg, alignItems: 'center', justifyContent: 'center', padding: 24 }} data-testid="qr-mobile-complete" testID="qr-mobile-complete">
      <View style={{ width: 80, height: 80, borderRadius: 40, backgroundColor: (globalThis as any).__alphaColor(C.success, '20'), alignItems: 'center', justifyContent: 'center', marginBottom: 20 }}>
        <Ionicons name="checkmark-circle" size={44} color={C.successText} />
      </View>
      <Text style={{ color: C.successText, fontSize: 22, fontWeight: '800', marginBottom: 8 }}>Documents Uploaded!</Text>
      <Text style={{ color: C.muted, fontSize: 13, textAlign: 'center', maxWidth: 300 }}>
        Your ID documents have been synced to your desktop session. You can close this page and continue on your computer.
      </Text>
    </SafeAreaView>
  );

  const capturedCount = [idFront, idBack, selfie].filter(Boolean).length;

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: C.bg }} edges={['top', 'bottom']}>
      <ScrollView contentContainerStyle={{ padding: 20, gap: 16 }}>
        {/* Header */}
        <View style={{ alignItems: 'center', marginBottom: 8 }}>
          <View style={{ width: 56, height: 56, borderRadius: 28, backgroundColor: (globalThis as any).__alphaColor(C.primary, '15'), alignItems: 'center', justifyContent: 'center', marginBottom: 12 }}>
            <Ionicons name="finger-print" size={28} color={C.primary} />
          </View>
          <Text style={{ color: C.text, fontSize: 20, fontWeight: '800' }} data-testid="qr-mobile-title" testID="qr-mobile-title">ID Verification</Text>
          <Text style={{ color: C.muted, fontSize: 12, textAlign: 'center', marginTop: 4 }}>
            Capture photos of your ID and a selfie below
          </Text>
        </View>

        {/* Capture Buttons */}
        {[
          { type: 'front' as const, label: 'ID Front', icon: 'card', data: idFront, desc: 'Front side of your ID card' },
          { type: 'back' as const, label: 'ID Back', icon: 'card-outline', data: idBack, desc: 'Back side of your ID card' },
          { type: 'selfie' as const, label: 'Selfie', icon: 'person-circle', data: selfie, desc: 'Clear photo of your face' },
        ].map((doc, idx) => (
          <TouchableOpacity key={doc.type} onPress={() => capturePhoto(doc.type)} data-testid={`qr-mobile-capture-${doc.type}`} testID={`qr-mobile-capture-${doc.type}`}
            style={{
              flexDirection: 'row', alignItems: 'center', gap: 14,
              backgroundColor: doc.data ? (globalThis as any).__alphaColor(C.success, '10') : C.card,
              borderRadius: 14, padding: 16, borderWidth: 1.5,
              borderColor: doc.data ? (globalThis as any).__alphaColor(C.success, '50') : C.border,
            }}>
            {doc.data ? (
              <View style={{ width: 56, height: 56, borderRadius: 12, overflow: 'hidden' }}>
                {Platform.OS === 'web' && <img src={doc.data} style={{ width: 56, height: 56, objectFit: 'cover', borderRadius: 12 }} />}
              </View>
            ) : (
              <View style={{
                width: 56, height: 56, borderRadius: 12,
                backgroundColor: (globalThis as any).__alphaColor(C.primary, '10'), alignItems: 'center', justifyContent: 'center',
                borderWidth: 2, borderColor: (globalThis as any).__alphaColor(C.primary, '30'), borderStyle: 'dashed',
              }}>
                <Ionicons name={doc.icon as any} size={24} color={C.primary} />
              </View>
            )}
            <View style={{ flex: 1 }}>
              <Text style={{ color: C.text, fontSize: 15, fontWeight: '700' }}>
                {idx + 1}. {doc.label}
              </Text>
              <Text style={{ color: doc.data ? C.success : C.dim, fontSize: 11, marginTop: 2 }}>
                {doc.data ? 'Captured! Tap to retake' : doc.desc}
              </Text>
            </View>
            <View style={{
              width: 36, height: 36, borderRadius: 18,
              backgroundColor: doc.data ? C.success : C.primary,
              alignItems: 'center', justifyContent: 'center',
            }}>
              <Ionicons name={doc.data ? 'checkmark' : 'camera'} size={18} color={onPrimary} />
            </View>
          </TouchableOpacity>
        ))}

        {/* Submit */}
        <TouchableOpacity
          onPress={uploadAndComplete}
          disabled={uploading || capturedCount === 0}
          data-testid="qr-mobile-submit-btn" testID="qr-mobile-submit-btn"
          style={{
            backgroundColor: capturedCount > 0 ? C.success : C.dim,
            borderRadius: 14, paddingVertical: 16, alignItems: 'center', marginTop: 8,
            opacity: uploading ? 0.6 : 1,
          }}>
          {uploading ? (
            <ActivityIndicator color={onPrimary} />
          ) : (
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
              <Ionicons name="cloud-upload" size={20} color={onPrimary} />
              <Text style={{ color: onPrimary, fontSize: 16, fontWeight: '800' }}>
                Upload {capturedCount} Document{capturedCount !== 1 ? 's' : ''}
              </Text>
            </View>
          )}
        </TouchableOpacity>

        <Text style={{ color: C.dim, fontSize: 10, textAlign: 'center', marginTop: 4 }}>
          Your documents will sync automatically to your desktop session
        </Text>
      </ScrollView>
    </SafeAreaView>
  );
}