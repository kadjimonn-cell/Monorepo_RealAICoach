import React, { useCallback, useEffect, useState } from 'react';
import { View, Text, TouchableOpacity, ActivityIndicator, Platform, Linking } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useTheme } from '../../context/ThemeContext';
import { useLanguage } from '../../i18n/LanguageContext';
import api from '../../services/api';

interface Props {
  userId: string;
}

type Cert = {
  cert_id: string;
  course_title: string;
  score?: number | null;
  created_at?: string;
};

export default function TravelVisaCertificates({ userId }: Props) {
  const { colors, darkMode } = useTheme();
  const { t } = useLanguage();
  const tx = useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);

  const [loading, setLoading] = useState(true);
  const [certs, setCerts] = useState<Cert[]>([]);
  const [error, setError] = useState('');
  const [busyId, setBusyId] = useState('');
  const [feedback, setFeedback] = useState<{ id: string; msg: string } | null>(null);

  const apiBase = (api as any)?.defaults?.baseURL || '';

  const load = useCallback(async () => {
    if (!userId) { setLoading(false); return; }
    setLoading(true);
    setError('');
    try {
      const res = await api.get(`/travel-visa/certificate/list/${userId}`, { silentLoading: true } as any);
      setCerts(Array.isArray(res.data?.certificates) ? res.data.certificates : (Array.isArray(res.data) ? res.data : []));
    } catch (e: any) {
      setError(e?.response?.data?.detail || tx('travelVisa.certificates.loadError', 'Could not load your certificates. Please retry.'));
    } finally {
      setLoading(false);
    }
  }, [userId, tx]);

  useEffect(() => { load(); }, [load]);

  const downloadUrl = (id: string) => `${apiBase}/travel-visa/certificate/download/${id}`;
  const verifyUrl = (id: string) => `${apiBase}/travel-visa/certificate/verify/${id}`;

  const onDownload = (id: string) => {
    const url = downloadUrl(id);
    if (Platform.OS === 'web' && typeof window !== 'undefined') window.open(url, '_blank');
    else Linking.openURL(url).catch(() => {});
  };

  const onEmail = async (id: string) => {
    setBusyId(id);
    try {
      const res = await api.post(`/travel-visa/certificate/email/${id}`, { user_id: userId });
      const ok = res.data?.email_status === 'sent';
      setFeedback({ id, msg: ok ? tx('travelVisa.certificates.emailSent', 'Certificate emailed to your inbox') : tx('travelVisa.certificates.emailQueued', 'Email queued — delivery pending') });
    } catch {
      setFeedback({ id, msg: tx('travelVisa.certificates.emailFailed', 'Could not send the email. Please retry.') });
    } finally {
      setBusyId('');
      setTimeout(() => setFeedback(null), 4000);
    }
  };

  const onCopyVerify = async (id: string) => {
    const url = verifyUrl(id);
    try {
      if (Platform.OS === 'web' && typeof navigator !== 'undefined' && navigator.clipboard) {
        await navigator.clipboard.writeText(url);
        setFeedback({ id, msg: tx('travelVisa.certificates.linkCopied', 'Verification link copied') });
      } else {
        Linking.openURL(url).catch(() => {});
      }
    } catch {
      setFeedback({ id, msg: tx('travelVisa.certificates.linkReady', 'Verification link ready:') + ' ' + url });
    }
    setTimeout(() => setFeedback(null), 3500);
  };

  const onShareLinkedIn = (cert: Cert) => {
    const url = verifyUrl(cert.cert_id);
    const template = tx('travelVisa.certificates.sharePost', 'I just earned a verified certificate from RealAICoach Travel Visa Academy — {course}. Verify it instantly: {link}');
    const text = template.replace('{course}', cert.course_title || '').replace('{link}', url);
    const shareUrl = `https://www.linkedin.com/feed/?shareActive=true&text=${encodeURIComponent(text)}`;
    if (Platform.OS === 'web' && typeof window !== 'undefined') window.open(shareUrl, '_blank');
    else Linking.openURL(shareUrl).catch(() => {});
  };

  const btnStyle = (accent = false) => ({
    flexDirection: 'row' as const,
    alignItems: 'center' as const,
    gap: 6,
    borderRadius: 999,
    borderWidth: 1,
    borderColor: accent ? colors.primary : colors.border,
    backgroundColor: accent ? colors.primarySoft : colors.surfaceHover,
    paddingHorizontal: 12,
    paddingVertical: 7,
  });

  return (
    <View data-testid="tv-certificates-root" testID="tv-certificates-root">
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 6 }}>
        <View style={{ width: 34, height: 34, borderRadius: 10, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.primarySoft, borderWidth: 1, borderColor: colors.border }}>
          <Ionicons name="ribbon-outline" size={18} color={colors.primary} />
        </View>
        <View style={{ flex: 1 }}>
          <Text style={{ fontSize: 15, fontWeight: '800', color: colors.text }} data-testid="tv-certificates-title" testID="tv-certificates-title">
            {tx('travelVisa.certificates.title', 'My Certificates')}
          </Text>
          <Text style={{ fontSize: 11, color: colors.textSec }}>
            {tx('travelVisa.certificates.subtitle', 'Earned credentials with instant QR verification — share them with employers and embassies.')}
          </Text>
        </View>
      </View>

      {loading && (
        <View style={{ paddingVertical: 24, alignItems: 'center' }}>
          <ActivityIndicator color={colors.primary} />
        </View>
      )}

      {!loading && !!error && (
        <View style={{ padding: 14, borderRadius: 12, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface, marginTop: 10 }} data-testid="tv-certificates-error" testID="tv-certificates-error">
          <Text style={{ color: colors.error, fontSize: 12, fontWeight: '600' }}>{error}</Text>
          <TouchableOpacity onPress={load} style={{ marginTop: 8 }} data-testid="tv-certificates-retry" testID="tv-certificates-retry">
            <Text style={{ color: colors.primary, fontSize: 12, fontWeight: '800' }}>{tx('travelVisa.certificates.retry', 'Retry')}</Text>
          </TouchableOpacity>
        </View>
      )}

      {!loading && !error && certs.length === 0 && (
        <View style={{ padding: 18, borderRadius: 12, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface, marginTop: 10, alignItems: 'center', gap: 6 }} data-testid="tv-certificates-empty" testID="tv-certificates-empty">
          <Ionicons name="school-outline" size={22} color={colors.textSec} />
          <Text style={{ color: colors.text, fontSize: 13, fontWeight: '700' }}>{tx('travelVisa.certificates.emptyTitle', 'No certificates yet')}</Text>
          <Text style={{ color: colors.textSec, fontSize: 11, textAlign: 'center' }}>
            {tx('travelVisa.certificates.emptyCopy', 'Pass a course quiz to earn your first verifiable certificate.')}
          </Text>
        </View>
      )}

      {!loading && certs.map((cert) => (
        <View
          key={cert.cert_id}
          style={{ marginTop: 10, padding: 14, borderRadius: 14, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface }}
          data-testid={`tv-certificate-card-${cert.cert_id}`}
          testID={`tv-certificate-card-${cert.cert_id}`}
        >
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 12 }}>
            <View style={{ width: 46, height: 46, borderRadius: 23, borderWidth: 3, borderColor: (cert.score ?? 100) >= 70 ? colors.success : colors.warning, alignItems: 'center', justifyContent: 'center', backgroundColor: darkMode ? colors.surfaceHover : colors.bg }}>
              <Text style={{ fontSize: 11, fontWeight: '800', color: colors.text }}>{cert.score != null ? `${cert.score}%` : '—'}</Text>
            </View>
            <View style={{ flex: 1, minWidth: 0 }}>
              <Text style={{ fontSize: 13, fontWeight: '800', color: colors.text }} numberOfLines={2}>{cert.course_title}</Text>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginTop: 3, flexWrap: 'wrap' }}>
                <Text style={{ fontSize: 10, color: colors.textSec, fontWeight: '700' }}>{cert.cert_id}</Text>
                {!!cert.created_at && <Text style={{ fontSize: 10, color: colors.textSec }}>{String(cert.created_at).slice(0, 10)}</Text>}
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 3, borderRadius: 999, backgroundColor: colors.successSoft, paddingHorizontal: 7, paddingVertical: 2 }}>
                  <Ionicons name="shield-checkmark" size={10} color={colors.success} />
                  <Text style={{ fontSize: 9, fontWeight: '800', color: colors.success }}>{tx('travelVisa.certificates.verified', 'Verifiable')}</Text>
                </View>
              </View>
            </View>
          </View>
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 12 }}>
            <TouchableOpacity style={btnStyle(true)} onPress={() => onDownload(cert.cert_id)} data-testid={`tv-certificate-download-${cert.cert_id}`} testID={`tv-certificate-download-${cert.cert_id}`}>
              <Ionicons name="download-outline" size={13} color={colors.primary} />
              <Text style={{ fontSize: 11, fontWeight: '800', color: colors.primary }}>{tx('travelVisa.certificates.download', 'Download PDF')}</Text>
            </TouchableOpacity>
            <TouchableOpacity style={btnStyle()} onPress={() => onEmail(cert.cert_id)} disabled={busyId === cert.cert_id} data-testid={`tv-certificate-email-${cert.cert_id}`} testID={`tv-certificate-email-${cert.cert_id}`}>
              {busyId === cert.cert_id
                ? <ActivityIndicator size={12} color={colors.textSec} />
                : <Ionicons name="mail-outline" size={13} color={colors.textSec} />}
              <Text style={{ fontSize: 11, fontWeight: '800', color: colors.textSec }}>{tx('travelVisa.certificates.emailMe', 'Email me a copy')}</Text>
            </TouchableOpacity>
            <TouchableOpacity style={btnStyle()} onPress={() => onCopyVerify(cert.cert_id)} data-testid={`tv-certificate-verify-${cert.cert_id}`} testID={`tv-certificate-verify-${cert.cert_id}`}>
              <Ionicons name="qr-code-outline" size={13} color={colors.textSec} />
              <Text style={{ fontSize: 11, fontWeight: '800', color: colors.textSec }}>{tx('travelVisa.certificates.copyVerify', 'Copy verify link')}</Text>
            </TouchableOpacity>
            <TouchableOpacity style={btnStyle(true)} onPress={() => onShareLinkedIn(cert)} data-testid={`tv-certificate-share-linkedin-${cert.cert_id}`} testID={`tv-certificate-share-linkedin-${cert.cert_id}`}>
              <Ionicons name="logo-linkedin" size={13} color={colors.primary} />
              <Text style={{ fontSize: 11, fontWeight: '800', color: colors.primary }}>{tx('travelVisa.certificates.shareLinkedIn', 'Share on LinkedIn')}</Text>
            </TouchableOpacity>
          </View>
          {feedback?.id === cert.cert_id && (
            <Text style={{ marginTop: 8, fontSize: 11, fontWeight: '700', color: colors.primary }} data-testid={`tv-certificate-feedback-${cert.cert_id}`} testID={`tv-certificate-feedback-${cert.cert_id}`}>
              {feedback.msg}
            </Text>
          )}
        </View>
      ))}
    </View>
  );
}
