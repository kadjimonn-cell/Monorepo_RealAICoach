import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  ActivityIndicator,
  Image,
  Platform,
  ScrollView,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';
import * as Clipboard from 'expo-clipboard';

import api from '../src/services/api';
import { useTheme } from '../src/context/ThemeContext';
import { useTranslation } from '../src/hooks/useTranslation';
import { handleAppRecoverableError } from '../src/utils/appRecoverableError';
import {
  CERTIFICATE_ASSET_VERSION,
  absoluteCertificateUrl,
  buildCertificateCompareProofUrl,
  buildCertificateRenderUrl,
  formatCertificateDate,
} from '../src/utils/certificates';
import {
  GLSContainer,
  GLSSection,
  useGLSBreakpoint,
} from '../src/components/layout/GlobalLayoutSystem';

export default function CertificateComparePage() {
  const { t } = useTranslation();
  t('i18n.route.certificate-compare.probe');
  const { colors, darkMode } = useTheme();
  const router = useRouter();
  const params = useLocalSearchParams<{ verificationId?: string; v?: string }>();
  const { isMobile, isTablet } = useGLSBreakpoint();
  const isNarrow = isMobile || isTablet;

  const tx = useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);

  const C = useMemo(() => ({
    bg: colors.bg,
    paper: colors.card,
    card: colors.cardMuted || colors.card,
    border: colors.border,
    borderSoft: colors.borderLight || colors.border,
    text: colors.text,
    muted: colors.textMuted,
    primary: colors.primary,
    info: colors.notificationInfo || colors.primary,
    success: colors.success,
    onPrimary: colors.primaryText || colors.buttonText || colors.card,
    ink: darkMode ? colors.cardMuted : colors.text,
  }), [colors, darkMode]);

  const activeVersion = String(params.v || CERTIFICATE_ASSET_VERSION);
  const [verificationId, setVerificationId] = useState(String(params.verificationId || '').trim());
  const [inputValue, setInputValue] = useState(String(params.verificationId || '').trim());
  const [verificationData, setVerificationData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [resolvingDefault, setResolvingDefault] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  const portraitRenderUrl = useMemo(
    () => buildCertificateRenderUrl(verificationId, 'portrait', 'print', activeVersion),
    [activeVersion, verificationId],
  );
  const landscapeRenderUrl = useMemo(
    () => buildCertificateRenderUrl(verificationId, 'landscape', 'print', activeVersion),
    [activeVersion, verificationId],
  );
  const compareImageUrl = useMemo(
    () => buildCertificateCompareProofUrl(verificationId, activeVersion, false),
    [activeVersion, verificationId],
  );
  const zoomImageUrl = useMemo(
    () => buildCertificateCompareProofUrl(verificationId, activeVersion, true),
    [activeVersion, verificationId],
  );

  useEffect(() => {
    const fromParams = String(params.verificationId || '').trim();
    setVerificationId(fromParams);
    setInputValue(fromParams);
  }, [params.verificationId]);

  useEffect(() => {
    if (verificationId) return;
    let active = true;
    const resolveFromPlatformData = async () => {
      setResolvingDefault(true);
      try {
        const res = await api.get('/ai-learn/certificates');
        const firstId = String(res?.data?.certificates?.[0]?.verification_id || '').trim();
        if (active && firstId) {
          setVerificationId(firstId);
          setInputValue(firstId);
          setNotice(tx('certificateCompare.messages.autoResolvedLatest', 'Loaded your latest certificate from platform data.'));
        }
      } catch (error) { handleAppRecoverableError({ scope: 'certificate-compare.tsx#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); } finally {
        if (active) setResolvingDefault(false);
      }
    };
    void resolveFromPlatformData();
    return () => {
      active = false;
    };
  }, [tx, verificationId]);

  useEffect(() => {
    let active = true;
    const loadVerification = async () => {
      if (!verificationId) {
        setLoading(false);
        setVerificationData(null);
        return;
      }
      setLoading(true);
      setError('');
      try {
        const res = await api.get(`/ai-learn/certificates/verify/${encodeURIComponent(verificationId)}`);
        if (!active) return;
        setVerificationData(res.data || null);
      } catch (e: any) {
        if (!active) return;
        setVerificationData(null);
        setError(e?.response?.data?.detail || tx('certificateCompare.errors.loadFailed', 'Unable to load certificate data for compare.'));
      } finally {
        if (active) setLoading(false);
      }
    };
    void loadVerification();
    return () => {
      active = false;
    };
  }, [tx, verificationId]);

  const copyText = useCallback(async (value: string, label: string) => {
    try {
      if (Platform.OS === 'web' && typeof navigator !== 'undefined' && navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(value);
      } else {
        await Clipboard.setStringAsync(value);
      }
      setNotice(tx('certificateCompare.messages.copiedWithLabel', '{label} copied.').replace('{label}', label));
    } catch {
      setError(tx('certificateCompare.errors.copyFailed', 'Unable to copy value.'));
    }
  }, [tx]);

  const applyVerificationId = useCallback(() => {
    const clean = inputValue.trim();
    if (!clean) {
      setError(tx('certificateCompare.errors.missingVerificationId', 'Enter a certificate verification ID to continue.'));
      return;
    }
    setError('');
    setVerificationId(clean);
    router.replace(`/certificate-compare?verificationId=${encodeURIComponent(clean)}` as any);
  }, [inputValue, router, tx]);

  const openWebExternal = useCallback((url: string) => {
    if (Platform.OS === 'web' && typeof window !== 'undefined' && url) {
      window.open(url, '_blank', 'noopener,noreferrer');
    }
  }, []);

  return (
    <ScrollView
      style={{ flex: 1, backgroundColor: C.bg }}
      contentContainerStyle={{ paddingBottom: 70 }}
      data-testid="certificate-compare-page"
      testID="certificate-compare-page"
    >
      <GLSSection noVerticalPadding style={{ paddingTop: isNarrow ? 14 : 20, paddingBottom: 20 }} testID="certificate-compare-main-section">
        <GLSContainer noPadding testID="certificate-compare-main-container">
          <View
            style={{ borderWidth: 1, borderColor: C.borderSoft, borderRadius: 14, backgroundColor: C.paper, padding: isNarrow ? 14 : 18 }}
            data-testid="certificate-compare-shell"
            testID="certificate-compare-shell"
          >
            <Text style={{ color: C.info, fontSize: 11, letterSpacing: 1.4, fontWeight: '900' }} data-testid="certificate-compare-overline" testID="certificate-compare-overline">
              {tx('certificateCompare.hero.overline', 'CERTIFICATE COMPARE VIEW')}
            </Text>
            <Text style={{ color: C.text, fontSize: isNarrow ? 30 : 40, lineHeight: isNarrow ? 36 : 46, fontWeight: '900', marginTop: 8 }} data-testid="certificate-compare-title" testID="certificate-compare-title">
              {tx('certificateCompare.hero.title', 'Portrait source vs rebuilt landscape')}
            </Text>
            <Text style={{ color: C.muted, fontSize: 13, lineHeight: 22, marginTop: 10 }} data-testid="certificate-compare-subtitle" testID="certificate-compare-subtitle">
              {tx('certificateCompare.hero.subtitle', 'This page compares live certificate renders using platform-backed verification data.')}
            </Text>

            <View style={{ marginTop: 14, borderWidth: 1, borderColor: C.border, borderRadius: 12, padding: 12, backgroundColor: C.card }} data-testid="certificate-compare-lookup-panel" testID="certificate-compare-lookup-panel">
              <Text style={{ color: C.text, fontSize: 12, fontWeight: '800' }} data-testid="certificate-compare-lookup-title" testID="certificate-compare-lookup-title">
                {tx('certificateCompare.lookup.title', 'Certificate lookup')}
              </Text>
              <Text style={{ color: C.muted, fontSize: 11, marginTop: 4 }} data-testid="certificate-compare-lookup-copy" testID="certificate-compare-lookup-copy">
                {tx('certificateCompare.lookup.copy', 'Enter a verification ID or load your latest certificate from platform data.')}
              </Text>
              <View style={{ marginTop: 10, flexDirection: isNarrow ? 'column' : 'row', gap: 8 }}>
                <TextInput
                  value={inputValue}
                  onChangeText={setInputValue}
                  placeholder={tx('certificateCompare.lookup.inputPlaceholder', 'Enter verification ID')}
                  placeholderTextColor={C.muted}
                  style={{ flex: 1, borderWidth: 1, borderColor: C.borderSoft, borderRadius: 10, paddingHorizontal: 12, paddingVertical: 10, color: C.text, backgroundColor: C.paper }}
                  data-testid="certificate-compare-verification-input"
                  testID="certificate-compare-verification-input"
                />
                <TouchableOpacity
                  onPress={applyVerificationId}
                  style={{ backgroundColor: C.primary, borderRadius: 10, paddingHorizontal: 14, paddingVertical: 10, alignItems: 'center', justifyContent: 'center' }}
                  data-testid="certificate-compare-load-button"
                  testID="certificate-compare-load-button"
                >
                  <Text style={{ color: C.onPrimary, fontSize: 11, fontWeight: '800' }}>{tx('certificateCompare.lookup.load', 'Load compare')}</Text>
                </TouchableOpacity>
              </View>
            </View>

            {notice ? (
              <View style={{ marginTop: 12, borderWidth: 1, borderColor: C.success, borderRadius: 10, padding: 10 }} data-testid="certificate-compare-notice-banner" testID="certificate-compare-notice-banner">
                <Text style={{ color: C.success, fontSize: 11, fontWeight: '700' }} data-testid="certificate-compare-notice-text" testID="certificate-compare-notice-text">
                  {notice}
                </Text>
              </View>
            ) : null}
            {error ? (
              <View style={{ marginTop: 12, borderWidth: 1, borderColor: colors.error, borderRadius: 10, padding: 10 }} data-testid="certificate-compare-error-banner" testID="certificate-compare-error-banner">
                <Text style={{ color: colors.error, fontSize: 11, fontWeight: '700' }} data-testid="certificate-compare-error-text" testID="certificate-compare-error-text">
                  {error}
                </Text>
              </View>
            ) : null}
          </View>

          {(loading || resolvingDefault) ? (
            <View style={{ marginTop: 12, borderWidth: 1, borderColor: C.border, borderRadius: 14, backgroundColor: C.paper, padding: 26, alignItems: 'center' }} data-testid="certificate-compare-loading-state" testID="certificate-compare-loading-state">
              <ActivityIndicator size="large" color={C.primary} />
              <Text style={{ color: C.muted, fontSize: 12, marginTop: 10 }} data-testid="certificate-compare-loading-text" testID="certificate-compare-loading-text">
                {tx('certificateCompare.states.loading', 'Loading certificate compare data...')}
              </Text>
            </View>
          ) : null}

          {!loading && !resolvingDefault && !verificationId ? (
            <View style={{ marginTop: 12, borderWidth: 1, borderColor: C.border, borderRadius: 14, backgroundColor: C.paper, padding: 20 }} data-testid="certificate-compare-empty-state" testID="certificate-compare-empty-state">
              <Text style={{ color: C.text, fontSize: 18, fontWeight: '800' }} data-testid="certificate-compare-empty-title" testID="certificate-compare-empty-title">
                {tx('certificateCompare.states.noVerificationIdTitle', 'No certificate selected')}
              </Text>
              <Text style={{ color: C.muted, fontSize: 12, marginTop: 8, lineHeight: 20 }} data-testid="certificate-compare-empty-copy" testID="certificate-compare-empty-copy">
                {tx('certificateCompare.states.noVerificationIdCopy', 'Provide a verification ID to compare portrait and landscape renders.')}
              </Text>
            </View>
          ) : null}

          {!loading && verificationId ? (
            <View style={{ marginTop: 12, borderWidth: 1, borderColor: C.border, borderRadius: 14, backgroundColor: C.paper, padding: 14 }} data-testid="certificate-compare-image-frame" testID="certificate-compare-image-frame">
              <View style={{ flexDirection: isNarrow ? 'column' : 'row', gap: 10 }} data-testid="certificate-compare-legend" testID="certificate-compare-legend">
                <View style={{ borderWidth: 1, borderColor: C.borderSoft, borderRadius: 999, paddingHorizontal: 10, paddingVertical: 7 }}>
                  <Text style={{ color: C.muted, fontSize: 10, fontWeight: '800' }}>{tx('certificateCompare.legend.portrait', 'Left · Portrait source of truth')}</Text>
                </View>
                <View style={{ borderWidth: 1, borderColor: C.borderSoft, borderRadius: 999, paddingHorizontal: 10, paddingVertical: 7 }}>
                  <Text style={{ color: C.muted, fontSize: 10, fontWeight: '800' }}>{tx('certificateCompare.legend.landscape', 'Right · Landscape rebuild')}</Text>
                </View>
              </View>

              <View style={{ marginTop: 10, flexDirection: isNarrow ? 'column' : 'row', gap: 12 }} data-testid="certificate-compare-live-grid" testID="certificate-compare-live-grid">
                <View style={{ flex: 1, minWidth: 0 }} data-testid="certificate-compare-portrait-card" testID="certificate-compare-portrait-card">
                  <Text style={{ color: C.text, fontSize: 13, fontWeight: '800', marginBottom: 8 }}>{tx('certificateCompare.cards.portrait', 'Portrait render')}</Text>
                  <View style={{ borderWidth: 1, borderColor: C.borderSoft, borderRadius: 12, backgroundColor: C.card, padding: 10 }}>
                    <Image
                      source={{ uri: portraitRenderUrl }}
                      resizeMode="contain"
                      style={{ width: '100%', aspectRatio: 0.707, borderRadius: 10 }}
                      accessibilityLabel={tx('certificateCompare.accessibility.portrait', 'Portrait certificate render')}
                      data-testid="certificate-compare-portrait-image"
                      testID="certificate-compare-portrait-image"
                    />
                  </View>
                </View>

                <View style={{ flex: 1, minWidth: 0 }} data-testid="certificate-compare-landscape-card" testID="certificate-compare-landscape-card">
                  <Text style={{ color: C.text, fontSize: 13, fontWeight: '800', marginBottom: 8 }}>{tx('certificateCompare.cards.landscape', 'Landscape render')}</Text>
                  <View style={{ borderWidth: 1, borderColor: C.borderSoft, borderRadius: 12, backgroundColor: C.card, padding: 10 }}>
                    <Image
                      source={{ uri: landscapeRenderUrl }}
                      resizeMode="contain"
                      style={{ width: '100%', aspectRatio: 1.414, borderRadius: 10 }}
                      accessibilityLabel={tx('certificateCompare.accessibility.landscape', 'Landscape certificate render')}
                      data-testid="certificate-compare-landscape-image"
                      testID="certificate-compare-landscape-image"
                    />
                  </View>
                </View>
              </View>

              <View style={{ marginTop: 12, borderWidth: 1, borderColor: C.borderSoft, borderRadius: 12, backgroundColor: C.card, padding: 12 }} data-testid="certificate-compare-meta-panel" testID="certificate-compare-meta-panel">
                <Text style={{ color: C.text, fontSize: 13, fontWeight: '800' }} data-testid="certificate-compare-meta-title" testID="certificate-compare-meta-title">
                  {tx('certificateCompare.meta.title', 'Certificate metadata')}
                </Text>
                <View style={{ marginTop: 8, gap: 6 }}>
                  <Text style={{ color: C.muted, fontSize: 11 }} data-testid="certificate-compare-meta-verification" testID="certificate-compare-meta-verification">
                    {tx('certificateCompare.meta.verificationWithValue', 'Verification ID · {value}').replace('{value}', verificationId)}
                  </Text>
                  <Text style={{ color: C.muted, fontSize: 11 }} data-testid="certificate-compare-meta-status" testID="certificate-compare-meta-status">
                    {tx('certificateCompare.meta.statusWithValue', 'Status · {value}').replace('{value}', String(verificationData?.status_label || verificationData?.status || '—'))}
                  </Text>
                  <Text style={{ color: C.muted, fontSize: 11 }} data-testid="certificate-compare-meta-course" testID="certificate-compare-meta-course">
                    {tx('certificateCompare.meta.courseWithValue', 'Course · {value}').replace('{value}', String(verificationData?.course_title || '—'))}
                  </Text>
                  <Text style={{ color: C.muted, fontSize: 11 }} data-testid="certificate-compare-meta-issued" testID="certificate-compare-meta-issued">
                    {tx('certificateCompare.meta.issuedWithValue', 'Issued · {value}').replace('{value}', formatCertificateDate(verificationData?.issued_at))}
                  </Text>
                </View>
              </View>

              <View style={{ marginTop: 12, flexDirection: isNarrow ? 'column' : 'row', gap: 8 }}>
                <TouchableOpacity
                  onPress={() => router.push(`/certificate-verify/${encodeURIComponent(verificationId)}` as any)}
                  style={{ backgroundColor: C.primary, borderRadius: 10, paddingHorizontal: 14, paddingVertical: 10 }}
                  data-testid="certificate-compare-open-verifier-button"
                  testID="certificate-compare-open-verifier-button"
                >
                <Text style={{ color: C.onPrimary, fontSize: 11, fontWeight: '800' }}>{tx('certificateCompare.actions.openVerifier', 'Open Public Verifier')}</Text>
                </TouchableOpacity>

                <TouchableOpacity
                  onPress={() => copyText(
                    absoluteCertificateUrl(`/certificate-compare?verificationId=${encodeURIComponent(verificationId)}`),
                    tx('certificateCompare.common.compareLink', 'Compare link'),
                  )}
                  style={{ borderWidth: 1, borderColor: C.borderSoft, borderRadius: 10, paddingHorizontal: 14, paddingVertical: 10 }}
                  data-testid="certificate-compare-copy-link-button"
                  testID="certificate-compare-copy-link-button"
                >
                  <Text style={{ color: C.text, fontSize: 11, fontWeight: '800' }}>{tx('certificateCompare.actions.copyLink', 'Copy compare link')}</Text>
                </TouchableOpacity>

                {Platform.OS === 'web' ? (
                  <TouchableOpacity
                    onPress={() => openWebExternal(compareImageUrl)}
                    style={{ borderWidth: 1, borderColor: C.borderSoft, borderRadius: 10, paddingHorizontal: 14, paddingVertical: 10 }}
                    data-testid="certificate-compare-open-raw-image-button"
                    testID="certificate-compare-open-raw-image-button"
                  >
                    <Text style={{ color: C.text, fontSize: 11, fontWeight: '800' }}>{tx('certificateCompare.actions.openRawImage', 'Open raw image')}</Text>
                  </TouchableOpacity>
                ) : null}

                {Platform.OS === 'web' ? (
                  <TouchableOpacity
                    onPress={() => openWebExternal(zoomImageUrl)}
                    style={{ borderWidth: 1, borderColor: C.borderSoft, borderRadius: 10, paddingHorizontal: 14, paddingVertical: 10 }}
                    data-testid="certificate-compare-open-zoom-image-button"
                    testID="certificate-compare-open-zoom-image-button"
                  >
                    <Text style={{ color: C.text, fontSize: 11, fontWeight: '800' }}>{tx('certificateCompare.actions.openZoomImage', 'Open zoomed proof')}</Text>
                  </TouchableOpacity>
                ) : null}
              </View>
            </View>
          ) : null}
        </GLSContainer>
      </GLSSection>
    </ScrollView>
  );
}