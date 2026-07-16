import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  ActivityIndicator,
  Linking,
  Platform,
  ScrollView,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';
import * as Clipboard from 'expo-clipboard';

import api from '../../src/services/api';
import { useTheme } from '../../src/context/ThemeContext';
import { useTranslation } from '../../src/hooks/useTranslation';
import { CertificatePreviewImage } from '../../src/components/certificates/CertificatePreviewImage';
import { CertificatePrintLayoutModal } from '../../src/components/certificates/CertificatePrintLayoutModal';
import { CertificateStatusBadge } from '../../src/components/certificates/CertificateStatusBadge';
import {
  absoluteCertificateUrl,
  formatCertificateDate,
  trackCertificateEngagement,
  withCertificatePrintLayout,
} from '../../src/utils/certificates';
import {
  GLSContainer,
  GLSSection,
  useGLSBreakpoint,
} from '../../src/components/layout/GlobalLayoutSystem';
import { buildAnalyticsSource } from '../../src/utils/buildAnalyticsSource';

const DEFAULT_TITLE = 'RealAICoach Certificate Verifier';
const DEFAULT_DESCRIPTION = 'Public verification page for RealAICoach certificates.';
// LinkedIn brand color (official and exempt from theme tokenization).
const LINKEDIN_BRAND_BLUE = '#0A66C2';

const maskId = (value: string) => {
  const text = String(value || '').trim();
  if (text.length <= 10) return text;
  return `${text.slice(0, 6)}...${text.slice(-4)}`;
};

const upsertMeta = (selector: string, createTag: () => HTMLElement, content: string) => {
  if (typeof document === 'undefined') return;
  let element = document.head.querySelector(selector) as HTMLElement | null;
  if (!element) {
    element = createTag();
    document.head.appendChild(element);
  }
  element.setAttribute('content', content);
};

const upsertCanonical = (href: string) => {
  if (typeof document === 'undefined') return;
  let link = document.head.querySelector('link[rel="canonical"]') as HTMLElement | null;
  if (!link) {
    link = document.createElement('link');
    link.setAttribute('rel', 'canonical');
    document.head.appendChild(link);
  }
  link.setAttribute('href', href);
};

const upsertJsonLd = (id: string, data: Record<string, any>) => {
  if (typeof document === 'undefined') return;
  let script = document.getElementById(id) as HTMLScriptElement | null;
  if (!script) {
    script = document.createElement('script');
    script.id = id;
    script.type = 'application/ld+json';
    document.head.appendChild(script);
  }
  script.textContent = JSON.stringify(data);
};

const openExternal = async (value: string, onError: (v: string) => void, tx: (k: string, f: string) => string) => {
  const target = absoluteCertificateUrl(value);
  if (!target) {
    onError(tx('certificateVerify.errors.invalidLink', 'Invalid certificate link.'));
    return;
  }
  if (Platform.OS === 'web' && typeof window !== 'undefined') {
    window.open(target, '_blank', 'noopener,noreferrer');
    return;
  }
  try {
    await Linking.openURL(target);
  } catch {
    onError(tx('certificateVerify.errors.openLinkFailed', 'Unable to open external link.'));
  }
};

export default function PublicCertificateVerifierPage() {
  const { t } = useTranslation();
  t('i18n.route.certificate-verify.[verificationId].probe');
  const { colors, darkMode } = useTheme();
  const { isMobile, isTablet } = useGLSBreakpoint();
  const router = useRouter();

  const tx = useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);

  const params = useLocalSearchParams();
  const verificationId = String(params.verificationId || params.id || params.vid || '').trim();
  const isNarrow = isMobile || isTablet;
  const certificateVerifierSource = useMemo(() => buildAnalyticsSource('certificate', 'verifier'), []);

  const C = useMemo(() => ({
    bg: colors.bg,
    paper: colors.card,
    card: colors.card,
    cardMuted: colors.cardMuted || colors.bgAlt || colors.bg,
    border: colors.border,
    borderSoft: colors.borderLight || colors.border,
    text: colors.text,
    muted: colors.textMuted,
    ink: darkMode ? colors.cardMuted : colors.text,
    blue: colors.primary,
    cyan: colors.notificationInfo || colors.primary,
    rose: colors.error,
    soft: darkMode ? (colors.cardMuted || colors.surfaceHover || colors.cardMuted) : (colors.bgAlt || colors.bg),
    successBg: darkMode ? 'rgba(16,185,129,0.16)' : '#DCFCE7',
    successBorder: darkMode ? 'rgba(134,239,172,0.25)' : '#86EFAC',
    successText: darkMode ? colors.success : '#166534',
    dangerBg: darkMode ? 'rgba(220,38,38,0.18)' : '#FEF2F2',
    dangerBorder: darkMode ? 'rgba(248,113,113,0.3)' : '#FECACA',
  }), [colors, darkMode]);

  const [loading, setLoading] = useState(true);
  const [data, setData] = useState<any>(null);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [assetBusy, setAssetBusy] = useState('');
  const [proofExpanded, setProofExpanded] = useState(false);
  const [printModalOpen, setPrintModalOpen] = useState(false);

  const load = useCallback(async () => {
    if (!verificationId) {
      setError(tx('certificateVerify.errors.missingVerificationId', 'Missing certificate verification ID.'));
      setLoading(false);
      return;
    }
    setLoading(true);
    setError('');
    try {
      const res = await api.get(`/ai-learn/certificates/verify/${encodeURIComponent(verificationId)}`);
      setData(res.data || null);
    } catch (e: any) {
      const message = e?.response?.data?.detail || e?.response?.data?.message || tx('certificateVerify.errors.verificationFailed', 'Certificate verification failed.');
      setData(e?.response?.data || null);
      setError(message);
    } finally {
      setLoading(false);
    }
  }, [tx, verificationId]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (!data?.verification_id) return;
    void trackCertificateEngagement({
      verificationId: data.verification_id,
      eventType: 'verifier_view',
      source: certificateVerifierSource,
    });
  }, [certificateVerifierSource, data?.verification_id]);

  const publicVerifyUrl = absoluteCertificateUrl(data?.public_verify_url || `/certificate-verify/${verificationId}`);
  const previewImageUrl = absoluteCertificateUrl(data?.preview_image_url || data?.thumbnail_image_url || '');
  const printPdfUrl = absoluteCertificateUrl(data?.public_pdf_url || '');
  const printPngUrl = absoluteCertificateUrl(data?.public_png_url || '');
  const proofPath = Array.isArray(data?.proof_path)
    ? data.proof_path
    : Array.isArray(data?.anchoring?.merkle_proof)
      ? data.anchoring.merkle_proof
      : [];

  const copyText = useCallback(async (value: string, label: string) => {
    try {
      if (Platform.OS === 'web' && typeof navigator !== 'undefined' && navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(value);
      } else {
        await Clipboard.setStringAsync(value);
      }
      setNotice(tx('certificateVerify.messages.copiedWithLabel', '{label} copied.').replace('{label}', label));
    } catch {
      setError(tx('certificateVerify.errors.copyFailedWithLabel', 'Unable to copy {label}.').replace('{label}', label.toLowerCase()));
    }
  }, [tx]);

  const openPrintVersion = useCallback(async (layout = 'portrait') => {
    setAssetBusy(`pdf-${layout}`);
    try {
      await trackCertificateEngagement({
        verificationId,
        eventType: 'pdf_open',
        source: certificateVerifierSource,
        metadata: { layout },
      });
      await openExternal(withCertificatePrintLayout(printPdfUrl, layout), setError, tx);
    } finally {
      setAssetBusy('');
      setPrintModalOpen(false);
    }
  }, [certificateVerifierSource, printPdfUrl, tx, verificationId]);

  const downloadPng = useCallback(async () => {
    setAssetBusy('png');
    try {
      await trackCertificateEngagement({ verificationId, eventType: 'png_export', source: certificateVerifierSource });
      if (Platform.OS === 'web' && typeof window !== 'undefined') {
        const response = await fetch(printPngUrl);
        if (!response.ok) throw new Error('png_export_failed');
        const blob = await response.blob();
        const blobUrl = URL.createObjectURL(blob);
        const anchor = document.createElement('a');
        anchor.href = blobUrl;
        anchor.download = `realaicoach-certificate-${verificationId}.png`;
        document.body.appendChild(anchor);
        anchor.click();
        anchor.remove();
        URL.revokeObjectURL(blobUrl);
      } else {
        await Linking.openURL(printPngUrl);
      }
      setNotice(tx('certificateVerify.messages.pngExported', 'High-resolution PNG exported.'));
    } catch {
      setError(tx('certificateVerify.errors.pngExportFailed', 'Unable to export the certificate PNG.'));
    } finally {
      setAssetBusy('');
    }
  }, [certificateVerifierSource, printPngUrl, tx, verificationId]);

  const exportPayload = useMemo(() => ({
    verification_id: data?.verification_id || verificationId,
    certificate_number: data?.certificate_number,
    status: data?.status,
    valid: data?.valid,
    learner_name: data?.learner_name,
    course_title: data?.course_title,
    issued_at: data?.issued_at,
    expiration_date: data?.expiration_date,
    signer_name: data?.signer_name,
    signer_role: data?.signer_role,
    public_verify_url: publicVerifyUrl,
    anchoring: data?.anchoring,
    revocation_reason: data?.revocation_reason,
  }), [data, publicVerifyUrl, verificationId]);

  const exportJson = useCallback(async () => {
    const text = JSON.stringify(exportPayload, null, 2);
    if (Platform.OS === 'web' && typeof window !== 'undefined') {
      const blob = new Blob([text], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = `certificate-proof-${verificationId}.json`;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(url);
      setNotice(tx('certificateVerify.messages.jsonExported', 'JSON proof exported.'));
      return;
    }
    await copyText(text, tx('certificateVerify.common.jsonProof', 'JSON proof'));
  }, [copyText, exportPayload, tx, verificationId]);

  useEffect(() => {
    if (typeof document === 'undefined') return;

    const masked = maskId(verificationId);
    const statusLabel = String(data?.status_label || tx('certificateVerify.common.statusValid', 'Valid'));
    const title = data?.verification_id
      ? tx('certificateVerify.meta.titleWithStatus', '{status} Certificate • {id} | RealAICoach')
        .replace('{status}', statusLabel)
        .replace('{id}', masked)
      : tx('certificateVerify.meta.titleFallback', 'Certificate Verification • {id} | RealAICoach').replace('{id}', masked);
    const description = data?.course_title
      ? tx('certificateVerify.meta.descriptionWithCourse', '{status} RealAICoach certificate for {course}. View secure preview, dates, signer, and trust details.')
        .replace('{status}', statusLabel)
        .replace('{course}', String(data.course_title))
      : DEFAULT_DESCRIPTION;

    document.title = title;
    upsertMeta('meta[name="description"]', () => {
      const meta = document.createElement('meta');
      meta.setAttribute('name', 'description');
      return meta;
    }, description);

    upsertCanonical(publicVerifyUrl || 'https://realaicoach.app');
    upsertJsonLd('certificate-verifier-jsonld', {
      '@context': 'https://schema.org',
      '@type': 'EducationalOccupationalCredential',
      name: data?.course_title || tx('certificateVerify.meta.defaultCredentialName', 'RealAICoach Certificate'),
      description,
      identifier: data?.certificate_number || masked,
      url: publicVerifyUrl,
      recognizedBy: { '@type': 'Organization', name: 'RealAICoach' },
      validFor: statusLabel,
    });

    return () => {
      document.title = DEFAULT_TITLE;
      upsertMeta('meta[name="description"]', () => {
        const meta = document.createElement('meta');
        meta.setAttribute('name', 'description');
        return meta;
      }, DEFAULT_DESCRIPTION);
    };
  }, [data, publicVerifyUrl, tx, verificationId]);

  if (loading) {
    return (
      <View style={{ flex: 1, backgroundColor: C.bg, alignItems: 'center', justifyContent: 'center', padding: 24 }} data-testid="certificate-verifier-loading-state" testID="certificate-verifier-loading-state">
        <ActivityIndicator size="large" color={C.blue} />
        <Text style={{ color: C.muted, fontSize: 12, marginTop: 10 }} data-testid="certificate-verifier-loading-text" testID="certificate-verifier-loading-text">
          {tx('certificateVerify.states.loading', 'Validating certificate proof...')}
        </Text>
      </View>
    );
  }

  const summaryRows = [
    { key: 'name', label: tx('certificateVerify.summary.learner', 'Learner'), value: data?.learner_name || tx('certificateVerify.common.naDash', '—') },
    { key: 'course', label: tx('certificateVerify.summary.certificateTitle', 'Certificate title'), value: data?.course_title || tx('certificateVerify.common.naDash', '—') },
    { key: 'number', label: tx('certificateVerify.summary.certificateId', 'Certificate ID'), value: data?.certificate_number || tx('certificateVerify.common.naDash', '—') },
    { key: 'issued', label: tx('certificateVerify.summary.issued', 'Issued'), value: formatCertificateDate(data?.issued_at) },
    { key: 'expires', label: tx('certificateVerify.summary.expires', 'Expires'), value: formatCertificateDate(data?.expiration_date, tx('certificateVerify.common.lifetimeValidity', 'Lifetime Validity')) },
    { key: 'signer', label: tx('certificateVerify.summary.signedBy', 'Signed by'), value: [data?.signer_name, data?.signer_role].filter(Boolean).join(' · ') || tx('certificateVerify.common.naDash', '—') },
  ];

  const trustRows = [
    { key: 'status', label: tx('certificateVerify.trust.status', 'Status'), value: data?.status_label || tx('certificateVerify.common.unknown', 'Unknown') },
    { key: 'verification', label: tx('certificateVerify.trust.verificationId', 'Verification ID'), value: data?.verification_id || verificationId || tx('certificateVerify.common.naDash', '—') },
    { key: 'anchor', label: tx('certificateVerify.trust.anchorStatus', 'Anchor status'), value: String(data?.anchoring?.status || 'not_queued').replace(/_/g, ' ') },
    { key: 'chain', label: tx('certificateVerify.trust.chain', 'Chain'), value: data?.chain || data?.anchoring?.chain_target || tx('certificateVerify.common.naDash', '—') },
  ];

  return (
    <>
      <ScrollView style={{ flex: 1, backgroundColor: C.bg }} contentContainerStyle={{ paddingBottom: 72 }} data-testid="certificate-verifier-page-root" testID="certificate-verifier-page-root">
        <GLSSection noVerticalPadding style={{ paddingTop: isNarrow ? 14 : 20, paddingBottom: 20 }} testID="certificate-verifier-main-section">
          <GLSContainer noPadding testID="certificate-verifier-main-container">
            <View style={{ borderWidth: 1, borderColor: C.borderSoft, borderRadius: 16, backgroundColor: C.paper, padding: isNarrow ? 14 : 18 }} data-testid="certificate-verifier-hero-section" testID="certificate-verifier-hero-section">
              <View style={{ flexDirection: isNarrow ? 'column' : 'row', justifyContent: 'space-between', gap: 12 }}>
                <View style={{ flex: 1, minWidth: 260 }}>
                  <Text style={{ color: C.blue, fontSize: 11, fontWeight: '900', letterSpacing: 1.4 }} data-testid="certificate-verifier-heading-overline" testID="certificate-verifier-heading-overline">
                    {tx('certificateVerify.hero.overline', 'PUBLIC CERTIFICATE VERIFIER')}
                  </Text>
                  <Text style={{ color: C.text, fontSize: isNarrow ? 30 : 42, lineHeight: isNarrow ? 36 : 46, marginTop: 8, fontWeight: '900' }} data-testid="certificate-verifier-heading" testID="certificate-verifier-heading">
                    {tx('certificateVerify.hero.title', 'RealAICoach certificate record')}
                  </Text>
                  <Text style={{ color: C.muted, fontSize: 13, marginTop: 10, lineHeight: 22 }} data-testid="certificate-verifier-subheading" testID="certificate-verifier-subheading">
                    {tx('certificateVerify.hero.subtitle', 'Review the regenerated certificate preview, live credential status, certificate dates, and trust proof from one secure public link.')}
                  </Text>
                </View>
                <CertificateStatusBadge status={data?.status} testID="certificate-verifier-status-pill" />
              </View>

              {notice ? (
                <View style={{ marginTop: 12, backgroundColor: C.successBg, borderWidth: 1, borderColor: C.successBorder, borderRadius: 10, padding: 10 }} data-testid="certificate-verifier-notice-banner" testID="certificate-verifier-notice-banner">
                  <Text style={{ color: C.successText, fontSize: 11, fontWeight: '700' }} data-testid="certificate-verifier-notice-text" testID="certificate-verifier-notice-text">{notice}</Text>
                </View>
              ) : null}

              {error ? (
                <View style={{ marginTop: 12, backgroundColor: C.dangerBg, borderWidth: 1, borderColor: C.dangerBorder, borderRadius: 10, padding: 10 }} data-testid="certificate-verifier-error-banner" testID="certificate-verifier-error-banner">
                  <Text style={{ color: C.rose, fontSize: 11, fontWeight: '700' }} data-testid="certificate-verifier-error-text" testID="certificate-verifier-error-text">{error}</Text>
                </View>
              ) : null}

              <View style={{ marginTop: 14, flexDirection: isNarrow ? 'column' : 'row', gap: 12 }}>
                <View style={{ flex: isNarrow ? undefined : 1.1, borderWidth: 1, borderColor: C.border, borderRadius: 12, backgroundColor: C.soft, padding: 10 }} data-testid="certificate-verifier-preview-panel" testID="certificate-verifier-preview-panel">
                  <CertificatePreviewImage
                    backgroundColor={C.soft}
                    borderRadius={10}
                    fallbackCopy={tx('certificateVerify.preview.fallbackCopy', 'The public preview is temporarily unavailable, but verification record, proof, PDF, and PNG actions remain live.')}
                    fallbackTitle={tx('certificateVerify.preview.fallbackTitle', 'Secure preview restoring')}
                    iconColor={C.blue}
                    imageStyle={{ width: '100%', aspectRatio: 0.707, borderRadius: 10, backgroundColor: C.soft }}
                    imageTestId="certificate-verifier-preview-image"
                    placeholderTestId="certificate-verifier-preview-fallback"
                    resizeMode="cover"
                    textColor={C.text}
                    urls={[previewImageUrl, data?.thumbnail_image_url, printPngUrl]}
                  />
                </View>

                <View style={{ flex: isNarrow ? undefined : 0.9, gap: 10 }}>
                  <View style={{ borderWidth: 1, borderColor: C.border, borderRadius: 12, backgroundColor: C.cardMuted, padding: 12 }} data-testid="certificate-verifier-summary-card" testID="certificate-verifier-summary-card">
                    <Text style={{ color: C.text, fontSize: 15, fontWeight: '800' }} data-testid="certificate-verifier-summary-title" testID="certificate-verifier-summary-title">
                      {tx('certificateVerify.summary.title', 'Certificate summary')}
                    </Text>
                    <View style={{ marginTop: 10, gap: 8 }}>
                      {summaryRows.map((item) => (
                        <View key={item.key} style={{ borderWidth: 1, borderColor: C.borderSoft, borderRadius: 10, padding: 10, backgroundColor: C.paper }} data-testid={`certificate-verifier-summary-row-${item.key}`} testID={`certificate-verifier-summary-row-${item.key}`}>
                          <Text style={{ color: C.muted, fontSize: 10, fontWeight: '700' }}>{item.label}</Text>
                          <Text style={{ color: C.text, fontSize: 13, fontWeight: '800', marginTop: 4 }}>{item.value}</Text>
                        </View>
                      ))}
                    </View>
                    {data?.revocation_reason ? (
                      <View style={{ marginTop: 10, backgroundColor: C.dangerBg, borderWidth: 1, borderColor: C.dangerBorder, borderRadius: 10, padding: 10 }} data-testid="certificate-verifier-revocation-banner" testID="certificate-verifier-revocation-banner">
                        <Text style={{ color: C.rose, fontSize: 10, fontWeight: '900' }} data-testid="certificate-verifier-revocation-title" testID="certificate-verifier-revocation-title">
                          {tx('certificateVerify.revocation.title', 'REVOCATION NOTE')}
                        </Text>
                        <Text style={{ color: C.rose, fontSize: 12, marginTop: 4 }} data-testid="certificate-verifier-revocation-copy" testID="certificate-verifier-revocation-copy">
                          {data.revocation_reason}
                        </Text>
                      </View>
                    ) : null}
                  </View>

                  <View style={{ borderWidth: 1, borderColor: C.border, borderRadius: 12, backgroundColor: C.cardMuted, padding: 12 }} data-testid="certificate-verifier-export-actions" testID="certificate-verifier-export-actions">
                    <Text style={{ color: C.text, fontSize: 15, fontWeight: '800' }} data-testid="certificate-verifier-export-title" testID="certificate-verifier-export-title">
                      {tx('certificateVerify.export.title', 'Share & export')}
                    </Text>
                    <Text style={{ color: C.muted, fontSize: 12, marginTop: 6, lineHeight: 19 }} data-testid="certificate-verifier-export-copy" testID="certificate-verifier-export-copy">
                      {tx('certificateVerify.export.subtitle', 'Open print-ready PDF, export high-resolution PNG, or copy the secure verification link.')}
                    </Text>

                    <View style={{ marginTop: 10, flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
                      <TouchableOpacity onPress={() => setPrintModalOpen(true)} style={{ backgroundColor: C.ink, borderRadius: 10, paddingHorizontal: 10, paddingVertical: 8 }} data-testid="certificate-verifier-print-button" testID="certificate-verifier-print-button">
                        <Text style={{ color: colors.primaryText, fontSize: 11, fontWeight: '800' }}>{assetBusy.startsWith('pdf-') ? tx('certificateVerify.actions.opening', 'Opening...') : tx('certificateVerify.actions.printOptions', 'Print Options')}</Text>
                      </TouchableOpacity>
                      <TouchableOpacity onPress={downloadPng} style={{ backgroundColor: C.blue, borderRadius: 10, paddingHorizontal: 10, paddingVertical: 8 }} data-testid="certificate-verifier-png-button" testID="certificate-verifier-png-button">
                        <Text style={{ color: colors.primaryText, fontSize: 11, fontWeight: '800' }}>{assetBusy === 'png' ? tx('certificateVerify.actions.preparing', 'Preparing...') : tx('certificateVerify.actions.exportPng', 'Export PNG')}</Text>
                      </TouchableOpacity>
                      <TouchableOpacity
                        onPress={async () => {
                          await trackCertificateEngagement({ verificationId, eventType: 'secure_link_copy', source: certificateVerifierSource });
                          await copyText(publicVerifyUrl, tx('certificateVerify.common.secureLink', 'Secure link'));
                        }}
                        style={{ backgroundColor: C.cyan, borderRadius: 10, paddingHorizontal: 10, paddingVertical: 8 }}
                        data-testid="certificate-verifier-copy-link-button"
                        testID="certificate-verifier-copy-link-button"
                      >
                        <Text style={{ color: colors.primaryText, fontSize: 11, fontWeight: '800' }}>{tx('certificateVerify.actions.copyLink', 'Copy Link')}</Text>
                      </TouchableOpacity>
                      <TouchableOpacity
                        onPress={async () => {
                          await trackCertificateEngagement({ verificationId, eventType: 'linkedin_share_click', source: certificateVerifierSource });
                          await openExternal(data?.linkedin_share_url || publicVerifyUrl, setError, tx);
                        }}
                        style={{ backgroundColor: LINKEDIN_BRAND_BLUE, borderRadius: 10, paddingHorizontal: 10, paddingVertical: 8 }}
                        data-testid="certificate-verifier-linkedin-button"
                        testID="certificate-verifier-linkedin-button"
                      >
                        <Text style={{ color: darkMode ? C.text : colors.primaryText, fontSize: 11, fontWeight: '800' }}>LinkedIn</Text>
                      </TouchableOpacity>
                    </View>

                    <View style={{ marginTop: 8, flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
                      <TouchableOpacity onPress={() => copyText(JSON.stringify(exportPayload, null, 2), tx('certificateVerify.common.verificationJson', 'Verification JSON'))} style={{ borderWidth: 1, borderColor: C.border, borderRadius: 10, paddingHorizontal: 10, paddingVertical: 8 }} data-testid="certificate-verifier-copy-json-button" testID="certificate-verifier-copy-json-button">
                        <Text style={{ color: C.text, fontSize: 11, fontWeight: '800' }}>{tx('certificateVerify.actions.copyJson', 'Copy JSON')}</Text>
                      </TouchableOpacity>
                      <TouchableOpacity onPress={exportJson} style={{ borderWidth: 1, borderColor: C.border, borderRadius: 10, paddingHorizontal: 10, paddingVertical: 8 }} data-testid="certificate-verifier-export-json-button" testID="certificate-verifier-export-json-button">
                        <Text style={{ color: C.text, fontSize: 11, fontWeight: '800' }}>{tx('certificateVerify.actions.exportJson', 'Export JSON')}</Text>
                      </TouchableOpacity>
                      <TouchableOpacity
                        onPress={() => router.push(`/certificate-compare?verificationId=${encodeURIComponent(verificationId)}` as any)}
                        style={{ borderWidth: 1, borderColor: C.border, borderRadius: 10, paddingHorizontal: 10, paddingVertical: 8 }}
                        data-testid="certificate-verifier-open-compare-button"
                        testID="certificate-verifier-open-compare-button"
                      >
                        <Text style={{ color: C.text, fontSize: 11, fontWeight: '800' }}>{tx('certificateVerify.actions.openCompare', 'Open Compare')}</Text>
                      </TouchableOpacity>
                    </View>
                  </View>
                </View>
              </View>
            </View>

            <View style={{ marginTop: 12, flexDirection: isNarrow ? 'column' : 'row', gap: 12 }}>
              <View style={{ flex: isNarrow ? undefined : 1, borderWidth: 1, borderColor: C.borderSoft, borderRadius: 12, backgroundColor: C.paper, padding: 12 }} data-testid="certificate-verifier-trust-summary" testID="certificate-verifier-trust-summary">
                <Text style={{ color: C.text, fontSize: 15, fontWeight: '800' }} data-testid="certificate-verifier-trust-title" testID="certificate-verifier-trust-title">
                  {tx('certificateVerify.trust.title', 'Trust summary')}
                </Text>
                <View style={{ marginTop: 10, gap: 8 }}>
                  {trustRows.map((item) => (
                    <View key={item.key} style={{ borderWidth: 1, borderColor: C.border, borderRadius: 10, padding: 10, backgroundColor: C.soft }} data-testid={`certificate-verifier-trust-row-${item.key}`} testID={`certificate-verifier-trust-row-${item.key}`}>
                      <Text style={{ color: C.muted, fontSize: 10, fontWeight: '700' }}>{item.label}</Text>
                      <Text style={{ color: C.text, fontSize: 13, fontWeight: '800', marginTop: 4 }}>{item.value}</Text>
                    </View>
                  ))}
                </View>
              </View>

              <View style={{ flex: isNarrow ? undefined : 1, borderWidth: 1, borderColor: C.borderSoft, borderRadius: 12, backgroundColor: C.paper, padding: 12 }} data-testid="certificate-verifier-proof-section" testID="certificate-verifier-proof-section">
                <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 10 }}>
                  <View style={{ flex: 1 }}>
                    <Text style={{ color: C.text, fontSize: 15, fontWeight: '800' }} data-testid="certificate-verifier-proof-title" testID="certificate-verifier-proof-title">
                      {tx('certificateVerify.proof.title', 'Proof path')}
                    </Text>
                    <Text style={{ color: C.muted, fontSize: 11, marginTop: 4, lineHeight: 18 }} data-testid="certificate-verifier-proof-subtitle" testID="certificate-verifier-proof-subtitle">
                      {tx('certificateVerify.proof.subtitle', 'Review trust nodes used to validate this credential batch.')}
                    </Text>
                  </View>
                  <TouchableOpacity onPress={() => setProofExpanded((prev) => !prev)} style={{ borderWidth: 1, borderColor: C.border, borderRadius: 999, paddingHorizontal: 10, paddingVertical: 7 }} data-testid="certificate-verifier-proof-toggle-button" testID="certificate-verifier-proof-toggle-button">
                    <Text style={{ color: C.text, fontSize: 10, fontWeight: '800' }}>{proofExpanded ? tx('certificateVerify.proof.hideNodes', 'Hide nodes') : tx('certificateVerify.proof.showNodes', 'Show nodes')}</Text>
                  </TouchableOpacity>
                </View>

                <View style={{ marginTop: 10, borderWidth: 1, borderColor: C.border, borderRadius: 10, padding: 10, backgroundColor: C.soft }} data-testid="certificate-verifier-proof-summary-box" testID="certificate-verifier-proof-summary-box">
                  <Text style={{ color: C.text, fontSize: 11, fontWeight: '700' }} data-testid="certificate-verifier-proof-summary-text" testID="certificate-verifier-proof-summary-text">
                    {proofPath.length > 0
                      ? tx('certificateVerify.proof.summaryWithCount', '{count} proof node(s) available for this certificate.').replace('{count}', String(proofPath.length))
                      : tx('certificateVerify.proof.summaryEmpty', 'No proof nodes are available yet for this certificate.')}
                  </Text>
                </View>

                {proofExpanded ? (
                  <View style={{ marginTop: 10, gap: 8 }} data-testid="certificate-verifier-proof-list" testID="certificate-verifier-proof-list">
                    {proofPath.map((node: any, index: number) => (
                      <View key={`${node?.hash || index}`} style={{ borderWidth: 1, borderColor: C.borderSoft, borderRadius: 10, padding: 10, backgroundColor: C.paper }} data-testid={`certificate-verifier-proof-row-${index}`} testID={`certificate-verifier-proof-row-${index}`}>
                        <Text style={{ color: C.muted, fontSize: 10, fontWeight: '700' }} data-testid={`certificate-verifier-proof-position-${index}`} testID={`certificate-verifier-proof-position-${index}`}>
                          {String(node?.position || '--').toUpperCase()}
                        </Text>
                        <Text style={{ color: C.text, fontSize: 11, marginTop: 4, lineHeight: 18 }} data-testid={`certificate-verifier-proof-hash-${index}`} testID={`certificate-verifier-proof-hash-${index}`}>
                          {String(node?.hash || '--')}
                        </Text>
                      </View>
                    ))}
                  </View>
                ) : null}
              </View>
            </View>

            <View style={{ marginTop: 12, borderWidth: 1, borderColor: C.borderSoft, borderRadius: 16, backgroundColor: C.paper, padding: isNarrow ? 14 : 18, overflow: 'hidden' }} data-testid="certificate-verifier-earn-yours-section" testID="certificate-verifier-earn-yours-section">
              <View style={{ position: 'absolute', top: 0, left: 0, right: 0, height: 3, backgroundColor: C.blue }} />
              <View style={{ flexDirection: isNarrow ? 'column' : 'row', alignItems: isNarrow ? 'flex-start' : 'center', gap: 14 }}>
                <View style={{ flex: 1, minWidth: 240 }}>
                  <Text style={{ color: C.blue, fontSize: 11, fontWeight: '900', letterSpacing: 1.4 }} data-testid="certificate-verifier-earn-yours-overline" testID="certificate-verifier-earn-yours-overline">
                    {tx('certificateVerify.earnYours.overline', 'START YOUR JOURNEY')}
                  </Text>
                  <Text style={{ color: C.text, fontSize: isNarrow ? 22 : 26, fontWeight: '900', marginTop: 6 }} data-testid="certificate-verifier-earn-yours-title" testID="certificate-verifier-earn-yours-title">
                    {tx('certificateVerify.earnYours.title', 'Earn yours')}
                  </Text>
                  <Text style={{ color: C.muted, fontSize: 13, marginTop: 6, lineHeight: 21 }} data-testid="certificate-verifier-earn-yours-copy" testID="certificate-verifier-earn-yours-copy">
                    {tx('certificateVerify.earnYours.copy', "This credential was earned through RealAICoach's AI-powered courses. Start learning today and earn your own verifiable certificate.")}
                  </Text>
                </View>
                <View style={{ flexDirection: isNarrow ? 'row' : 'column', flexWrap: 'wrap', gap: 8 }}>
                  <TouchableOpacity
                    onPress={async () => {
                      await trackCertificateEngagement({ verificationId, eventType: 'earn_yours_click', source: certificateVerifierSource, metadata: { target: 'ai-learning-hub' } });
                      router.push('/ai-learning-hub' as any);
                    }}
                    style={{ backgroundColor: C.blue, borderRadius: 10, paddingHorizontal: 16, paddingVertical: 11 }}
                    data-testid="certificate-verifier-earn-yours-primary-button"
                    testID="certificate-verifier-earn-yours-primary-button"
                  >
                    <Text style={{ color: colors.primaryText, fontSize: 12, fontWeight: '900', textAlign: 'center' }}>{tx('certificateVerify.earnYours.primaryCta', 'Start Learning Free')}</Text>
                  </TouchableOpacity>
                  <TouchableOpacity
                    onPress={async () => {
                      await trackCertificateEngagement({ verificationId, eventType: 'earn_yours_click', source: certificateVerifierSource, metadata: { target: 'home' } });
                      router.push('/' as any);
                    }}
                    style={{ borderWidth: 1, borderColor: C.border, borderRadius: 10, paddingHorizontal: 16, paddingVertical: 11 }}
                    data-testid="certificate-verifier-earn-yours-secondary-button"
                    testID="certificate-verifier-earn-yours-secondary-button"
                  >
                    <Text style={{ color: C.text, fontSize: 12, fontWeight: '800', textAlign: 'center' }}>{tx('certificateVerify.earnYours.secondaryCta', 'Explore RealAICoach')}</Text>
                  </TouchableOpacity>
                </View>
              </View>
            </View>
          </GLSContainer>
        </GLSSection>
      </ScrollView>

      <CertificatePrintLayoutModal
        visible={printModalOpen}
        onClose={() => setPrintModalOpen(false)}
        onSelect={(layout) => { void openPrintVersion(layout); }}
        colors={{ ...C, paper: C.paper, muted: C.muted, borderSoft: C.borderSoft, soft: C.soft, blue: C.blue }}
        busy={assetBusy.startsWith('pdf-')}
        prefix="certificate-verifier"
        previewUrl={printPngUrl}
      />
    </>
  );
}