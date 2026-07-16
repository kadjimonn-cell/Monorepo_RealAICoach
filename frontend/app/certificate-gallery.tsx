import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  ActivityIndicator,
  Linking,
  Modal,
  Platform,
  ScrollView,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import * as Clipboard from 'expo-clipboard';

import AppShell from '../src/components/AppShell';
import api from '../src/services/api';
import { useTheme } from '../src/context/ThemeContext';
import { useAuth } from '../src/context/AuthContext';
import { useTranslation } from '../src/hooks/useTranslation';
import { AdminRouteGate } from '../src/components/auth/AdminRouteGate';
import { CertificatePreviewImage } from '../src/components/certificates/CertificatePreviewImage';
import { CertificateStatusBadge } from '../src/components/certificates/CertificateStatusBadge';
import { CertificatePrintLayoutModal } from '../src/components/certificates/CertificatePrintLayoutModal';
import {
  absoluteCertificateUrl,
  formatCertificateDate,
  trackCertificateEngagement,
  withCertificatePrintLayout,
} from '../src/utils/certificates';
import {
  GLSContainer,
  GLSSection,
  GLSGrid,
  GLSGridItem,
  useGLSBreakpoint,
} from '../src/components/layout/GlobalLayoutSystem';
import { hasAdminConsoleVisibility } from '../src/utils/adminAccess';
import { buildAnalyticsSource } from '../src/utils/buildAnalyticsSource';

// LinkedIn brand color (official and exempt from theme tokenization).
const LINKEDIN_BRAND_BLUE = '#0A66C2';
const REVOKE_CONFIRM_WORD = 'REVOKE';

const openExternal = async (value, onError, tx) => {
  const target = absoluteCertificateUrl(value);
  if (!target) {
    onError(tx('certificateGallery.errors.invalidLink', 'Invalid certificate link.'));
    return;
  }
  if (Platform.OS === 'web' && typeof window !== 'undefined') {
    window.open(target, '_blank', 'noopener,noreferrer');
    return;
  }
  try {
    await Linking.openURL(target);
  } catch {
    onError(tx('certificateGallery.errors.openLinkFailed', 'Unable to open certificate link.'));
  }
};

export default function CertificateGalleryPage() {
  const { t } = useTranslation();
  t('i18n.route.certificate-gallery.probe');
  const router = useRouter();
  const { colors, darkMode } = useTheme();
  const { user } = useAuth();
  const { isMobile, isTablet } = useGLSBreakpoint();

  const tx = useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);

  const isAdmin = hasAdminConsoleVisibility(user as any);
  const isNarrow = isMobile || isTablet;
  const certificateGallerySource = useMemo(() => buildAnalyticsSource('certificate', 'gallery'), []);

  const C = useMemo(() => ({
    bg: colors.bg,
    paper: colors.card,
    card: colors.card,
    cardMuted: colors.cardMuted || colors.bgAlt || colors.bg,
    border: colors.border,
    borderSoft: colors.borderLight || colors.border,
    text: colors.text,
    muted: colors.textMuted,
    primary: colors.primary,
    info: colors.notificationInfo || colors.primary,
    ink: darkMode ? colors.cardMuted : colors.text,
    soft: darkMode ? (colors.cardMuted || colors.surfaceHover || colors.cardMuted) : (colors.bgAlt || colors.bg),
    rose: colors.error,
    successBg: darkMode ? 'rgba(16,185,129,0.16)' : '#DCFCE7',
    successBorder: darkMode ? 'rgba(134,239,172,0.25)' : '#86EFAC',
    successText: darkMode ? colors.success : '#166534',
    dangerBg: darkMode ? 'rgba(220,38,38,0.18)' : '#FEF2F2',
    dangerBorder: darkMode ? 'rgba(248,113,113,0.3)' : '#FECACA',
  }), [colors, darkMode]);

  const [loading, setLoading] = useState(true);
  const [adminLoading, setAdminLoading] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [busyId, setBusyId] = useState('');
  const [mode, setMode] = useState<'mine' | 'platform'>('mine');
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');
  const [sortMode, setSortMode] = useState('newest');
  const [certificates, setCertificates] = useState<any[]>([]);
  const [adminCertificates, setAdminCertificates] = useState<any[]>([]);
  const [revocationTarget, setRevocationTarget] = useState<any>(null);
  const [revocationReason, setRevocationReason] = useState('');
  const [revocationConfirmText, setRevocationConfirmText] = useState('');
  const [printTarget, setPrintTarget] = useState<any>(null);

  const statusOptions = useMemo(() => ([
    { id: 'all', label: tx('certificateGallery.filters.status.all', 'All') },
    { id: 'valid', label: tx('certificateGallery.filters.status.valid', 'Valid') },
    { id: 'expired', label: tx('certificateGallery.filters.status.expired', 'Expired') },
    { id: 'revoked', label: tx('certificateGallery.filters.status.revoked', 'Revoked') },
  ]), [tx]);

  const sortOptions = useMemo(() => ([
    { id: 'newest', label: tx('certificateGallery.filters.sort.newest', 'Newest') },
    { id: 'oldest', label: tx('certificateGallery.filters.sort.oldest', 'Oldest') },
    { id: 'course', label: tx('certificateGallery.filters.sort.course', 'Course') },
    { id: 'status', label: tx('certificateGallery.filters.sort.status', 'Status') },
  ]), [tx]);

  const loadCertificates = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const res = await api.get('/ai-learn/certificates');
      setCertificates(res.data?.certificates || []);
    } catch (e: any) {
      setError(e?.response?.data?.detail || tx('certificateGallery.errors.loadMineFailed', 'Unable to load your certificate gallery right now.'));
    } finally {
      setLoading(false);
    }
  }, [tx]);

  const loadAdminCertificates = useCallback(async () => {
    if (!isAdmin) return;
    setAdminLoading(true);
    try {
      const res = await api.get('/ai-learn/admin/certificates', {
        params: { search, status: statusFilter, sort: sortMode, limit: 120 },
      });
      setAdminCertificates(res.data?.certificates || []);
    } catch (e: any) {
      setError(e?.response?.data?.detail || tx('certificateGallery.errors.loadPlatformFailed', 'Unable to load platform certificates.'));
    } finally {
      setAdminLoading(false);
    }
  }, [isAdmin, search, statusFilter, sortMode, tx]);

  useEffect(() => {
    if (!user?.user_id) {
      setLoading(false);
      return;
    }
    void loadCertificates();
  }, [user?.user_id, loadCertificates]);

  useEffect(() => {
    if (isAdmin && mode === 'platform') {
      void loadAdminCertificates();
    }
  }, [isAdmin, mode, loadAdminCertificates]);

  const copyText = useCallback(async (value: string, label: string) => {
    try {
      if (Platform.OS === 'web' && typeof navigator !== 'undefined' && navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(value);
      } else {
        await Clipboard.setStringAsync(value);
      }
      setNotice(tx('certificateGallery.messages.copiedWithLabel', '{label} copied.').replace('{label}', label));
    } catch {
      setError(tx('certificateGallery.errors.copyFailedWithLabel', 'Unable to copy {label}.').replace('{label}', label.toLowerCase()));
    }
  }, [tx]);

  const visibleCertificates = useMemo(() => {
    const list = mode === 'platform' ? adminCertificates : certificates;
    const normalizedSearch = search.trim().toLowerCase();

    const filtered = list.filter((row: any) => {
      const haystack = `${row?.learner_name || ''} ${row?.course_title || ''} ${row?.certificate_number || ''} ${row?.verification_id || ''}`.toLowerCase();
      const searchMatch = !normalizedSearch || haystack.includes(normalizedSearch);
      const statusMatch = statusFilter === 'all' || String(row?.status || '').toLowerCase() === statusFilter;
      return searchMatch && statusMatch;
    });

    filtered.sort((a: any, b: any) => {
      if (sortMode === 'oldest') return String(a?.issued_at || '').localeCompare(String(b?.issued_at || ''));
      if (sortMode === 'course') return String(a?.course_title || '').localeCompare(String(b?.course_title || ''));
      if (sortMode === 'status') return String(a?.status || '').localeCompare(String(b?.status || ''));
      return String(b?.issued_at || '').localeCompare(String(a?.issued_at || ''));
    });

    return filtered;
  }, [adminCertificates, certificates, mode, search, sortMode, statusFilter]);

  const latestCertificate = visibleCertificates[0] || null;

  const stats = useMemo(() => ({
    total: visibleCertificates.length,
    valid: visibleCertificates.filter((row: any) => String(row?.status || '').toLowerCase() === 'valid').length,
    shareable: visibleCertificates.filter((row: any) => row?.public_verify_url).length,
    revoked: visibleCertificates.filter((row: any) => String(row?.status || '').toLowerCase() === 'revoked').length,
  }), [visibleCertificates]);

  const openCertificatePage = useCallback((verificationId?: string) => {
    if (!verificationId) return;
    router.push(`/certificate-verify/${encodeURIComponent(verificationId)}` as any);
  }, [router]);

  const openComparePage = useCallback((verificationId?: string) => {
    if (!verificationId) return;
    router.push(`/certificate-compare?verificationId=${encodeURIComponent(verificationId)}` as any);
  }, [router]);

  const openPdf = useCallback(async (certificate: any, layout = 'portrait') => {
    setBusyId(`pdf-${certificate?.verification_id}-${layout}`);
    setError('');
    try {
      await trackCertificateEngagement({
        verificationId: certificate?.verification_id,
        eventType: 'pdf_open',
        source: certificateGallerySource,
        metadata: { layout },
      });
      await openExternal(
        withCertificatePrintLayout(certificate?.public_pdf_url || certificate?.download_pdf_url || '', layout),
        setError,
        tx,
      );
    } finally {
      setBusyId('');
      setPrintTarget(null);
    }
  }, [certificateGallerySource, tx]);

  const openPrintOptions = useCallback((certificate: any) => {
    setPrintTarget(certificate || null);
  }, []);

  const openLinkedIn = useCallback(async (certificate: any) => {
    await trackCertificateEngagement({
      verificationId: certificate?.verification_id,
      eventType: 'linkedin_share_click',
      source: certificateGallerySource,
    });
    await openExternal(certificate?.linkedin_share_url || certificate?.public_verify_url || '', setError, tx);
  }, [certificateGallerySource, tx]);

  const confirmRevocation = useCallback(async () => {
    if (!revocationTarget?.verification_id) return;
    if (revocationConfirmText.trim().toUpperCase() !== REVOKE_CONFIRM_WORD) {
      setError(tx('certificateGallery.errors.revokeConfirmWordRequired', 'Type REVOKE to confirm this action.'));
      return;
    }

    setBusyId(`revoke-${revocationTarget.verification_id}`);
    setError('');

    try {
      await api.post(`/ai-learn/admin/certificates/${encodeURIComponent(revocationTarget.verification_id)}/revoke`, {
        reason: revocationReason || tx('certificateGallery.revoke.defaultReason', 'Revoked by administrator'),
      });
      setNotice(tx('certificateGallery.revoke.success', 'Certificate revoked successfully.'));
      setRevocationTarget(null);
      setRevocationReason('');
      setRevocationConfirmText('');
      await Promise.all([loadCertificates(), loadAdminCertificates()]);
    } catch (e: any) {
      setError(e?.response?.data?.detail || tx('certificateGallery.errors.revokeFailed', 'Unable to revoke this certificate.'));
    } finally {
      setBusyId('');
    }
  }, [loadAdminCertificates, loadCertificates, revocationConfirmText, revocationReason, revocationTarget, tx]);

  const featuredStats = useMemo(() => ([
    { key: 'total', label: tx('certificateGallery.stats.visibleCertificates', 'Visible certificates'), value: stats.total },
    { key: 'valid', label: tx('certificateGallery.stats.currentlyValid', 'Currently valid'), value: stats.valid },
    { key: 'share', label: tx('certificateGallery.stats.secureShareLinks', 'Secure share links'), value: stats.shareable },
    { key: 'revoked', label: tx('certificateGallery.stats.revoked', 'Revoked'), value: stats.revoked },
  ]), [stats, tx]);

  const isLoadingState = loading || (isAdmin && mode === 'platform' && adminLoading);

  const renderCertificateCard = (certificate: any, index: number, adminView = false) => (
    <View
      key={certificate?.certificate_id || certificate?.verification_id || index}
      style={{ borderWidth: 1, borderColor: C.borderSoft, borderRadius: 16, backgroundColor: C.paper, overflow: 'hidden' }}
      data-testid={`certificate-gallery-card-${index}`}
      testID={`certificate-gallery-card-${index}`}
    >
      <TouchableOpacity
        onPress={() => openCertificatePage(certificate?.verification_id)}
        style={{ backgroundColor: C.soft, padding: 12 }}
        data-testid={`certificate-gallery-card-preview-button-${index}`}
        testID={`certificate-gallery-card-preview-button-${index}`}
      >
        <CertificatePreviewImage
          backgroundColor={C.soft}
          borderRadius={12}
          fallbackCopy={tx('certificateGallery.card.previewFallbackCopy', 'The certificate image is regenerating. Open the record or PDF while the preview restores.')}
          fallbackTitle={tx('certificateGallery.card.previewFallbackTitle', 'Certificate preview offline')}
          iconColor={C.primary}
          imageStyle={{ width: '100%', aspectRatio: 0.707, borderRadius: 12, backgroundColor: C.soft }}
          imageTestId={`certificate-gallery-card-preview-image-${index}`}
          placeholderTestId={`certificate-gallery-card-preview-fallback-${index}`}
          resizeMode="cover"
          textColor={C.text}
          urls={[certificate?.thumbnail_image_url, certificate?.preview_image_url, certificate?.public_png_url]}
        />
      </TouchableOpacity>

      <View style={{ padding: 14, gap: 10 }}>
        <View style={{ flexDirection: 'row', gap: 10, justifyContent: 'space-between' }}>
          <View style={{ flex: 1 }}>
            <Text
              style={{ color: C.text, fontSize: 16, fontWeight: '900' }}
              data-testid={`certificate-gallery-card-title-${index}`}
              testID={`certificate-gallery-card-title-${index}`}
            >
              {certificate?.course_title || tx('certificateGallery.card.certificateFallback', 'Certificate')}
            </Text>
            {adminView ? (
              <Text
                style={{ color: C.muted, fontSize: 11, marginTop: 6 }}
                data-testid={`certificate-gallery-card-learner-${index}`}
                testID={`certificate-gallery-card-learner-${index}`}
              >
                {tx('certificateGallery.card.learnerWithName', 'Learner · {name}').replace('{name}', certificate?.learner_name || tx('certificateGallery.card.unknown', 'Unknown'))}
              </Text>
            ) : null}
          </View>
          <CertificateStatusBadge status={certificate?.status} testID={`certificate-gallery-card-status-${index}`} />
        </View>

        <View style={{ borderWidth: 1, borderColor: C.border, borderRadius: 12, backgroundColor: C.cardMuted, padding: 10, gap: 5 }}>
          <Text style={{ color: C.muted, fontSize: 10 }} data-testid={`certificate-gallery-card-number-${index}`} testID={`certificate-gallery-card-number-${index}`}>
            {tx('certificateGallery.card.certificateIdWithValue', 'Certificate ID · {value}').replace('{value}', certificate?.certificate_number || '—')}
          </Text>
          <Text style={{ color: C.muted, fontSize: 10 }} data-testid={`certificate-gallery-card-issued-${index}`} testID={`certificate-gallery-card-issued-${index}`}>
            {tx('certificateGallery.card.issuedWithValue', 'Issued · {value}').replace('{value}', formatCertificateDate(certificate?.issued_at))}
          </Text>
          <Text style={{ color: C.muted, fontSize: 10 }} data-testid={`certificate-gallery-card-expires-${index}`} testID={`certificate-gallery-card-expires-${index}`}>
            {tx('certificateGallery.card.expiresWithValue', 'Expires · {value}').replace('{value}', formatCertificateDate(certificate?.expiration_date, tx('certificateGallery.common.lifetimeValidity', 'Lifetime Validity')))}
          </Text>
          {certificate?.revocation_reason ? (
            <Text style={{ color: C.rose, fontSize: 10 }} data-testid={`certificate-gallery-card-revocation-${index}`} testID={`certificate-gallery-card-revocation-${index}`}>
              {tx('certificateGallery.card.reasonWithValue', 'Reason · {value}').replace('{value}', certificate.revocation_reason)}
            </Text>
          ) : null}
        </View>

        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
          <TouchableOpacity
            onPress={() => openCertificatePage(certificate?.verification_id)}
            style={{ backgroundColor: C.ink, borderRadius: 10, paddingHorizontal: 10, paddingVertical: 8 }}
            data-testid={`certificate-gallery-card-view-${index}`}
            testID={`certificate-gallery-card-view-${index}`}
          >
            <Text style={{ color: colors.primaryText, fontSize: 10, fontWeight: '800' }}>{tx('certificateGallery.actions.view', 'View')}</Text>
          </TouchableOpacity>
          <TouchableOpacity
            onPress={() => openPrintOptions(certificate)}
            style={{ backgroundColor: C.primary, borderRadius: 10, paddingHorizontal: 10, paddingVertical: 8 }}
            data-testid={`certificate-gallery-card-pdf-${index}`}
            testID={`certificate-gallery-card-pdf-${index}`}
          >
            <Text style={{ color: colors.primaryText, fontSize: 10, fontWeight: '800' }}>
              {busyId.startsWith(`pdf-${certificate?.verification_id}`)
                ? tx('certificateGallery.actions.opening', 'Opening...')
                : tx('certificateGallery.actions.printPdf', 'Print PDF')}
            </Text>
          </TouchableOpacity>
          <TouchableOpacity
            onPress={async () => {
              await trackCertificateEngagement({
                verificationId: certificate?.verification_id,
                eventType: 'secure_link_copy',
                source: certificateGallerySource,
              });
              await copyText(
                absoluteCertificateUrl(certificate?.public_verify_url || ''),
                tx('certificateGallery.common.secureLink', 'Secure link'),
              );
            }}
            style={{ backgroundColor: C.info, borderRadius: 10, paddingHorizontal: 10, paddingVertical: 8 }}
            data-testid={`certificate-gallery-card-copy-link-${index}`}
            testID={`certificate-gallery-card-copy-link-${index}`}
          >
            <Text style={{ color: colors.primaryText, fontSize: 10, fontWeight: '800' }}>{tx('certificateGallery.actions.copyLink', 'Copy Link')}</Text>
          </TouchableOpacity>
          <TouchableOpacity
            onPress={() => openComparePage(certificate?.verification_id)}
            style={{ borderWidth: 1, borderColor: C.borderSoft, borderRadius: 10, paddingHorizontal: 10, paddingVertical: 8 }}
            data-testid={`certificate-gallery-card-compare-${index}`}
            testID={`certificate-gallery-card-compare-${index}`}
          >
            <Text style={{ color: C.text, fontSize: 10, fontWeight: '800' }}>{tx('certificateGallery.actions.compare', 'Compare')}</Text>
          </TouchableOpacity>
          <TouchableOpacity
            onPress={() => openLinkedIn(certificate)}
            style={{ backgroundColor: LINKEDIN_BRAND_BLUE, borderRadius: 10, paddingHorizontal: 10, paddingVertical: 8 }}
            data-testid={`certificate-gallery-card-linkedin-${index}`}
            testID={`certificate-gallery-card-linkedin-${index}`}
          >
            <Text style={{ color: darkMode ? C.text : colors.primaryText, fontSize: 10, fontWeight: '800' }}>LinkedIn</Text>
          </TouchableOpacity>
          {adminView && certificate?.status !== 'revoked' ? (
            <TouchableOpacity
              onPress={() => {
                setRevocationTarget(certificate);
                setRevocationReason(certificate?.revocation_reason || '');
                setRevocationConfirmText('');
              }}
              style={{ backgroundColor: C.dangerBg, borderRadius: 10, paddingHorizontal: 10, paddingVertical: 8, borderWidth: 1, borderColor: C.dangerBorder }}
              data-testid={`certificate-gallery-card-revoke-${index}`}
              testID={`certificate-gallery-card-revoke-${index}`}
            >
              <Text style={{ color: C.rose, fontSize: 10, fontWeight: '800' }}>{tx('certificateGallery.actions.revoke', 'Revoke')}</Text>
            </TouchableOpacity>
          ) : null}
        </View>
      </View>
    </View>
  );

  return (
    <AdminRouteGate returnTo="/certificate-gallery">
    <AppShell>
      <ScrollView
        style={{ flex: 1, backgroundColor: C.bg }}
        contentContainerStyle={{ paddingBottom: 80 }}
        data-testid="certificate-gallery-page"
        testID="certificate-gallery-page"
      >
        <GLSSection
          noVerticalPadding
          style={{ paddingTop: isNarrow ? 14 : 20, paddingBottom: 22 }}
          testID="certificate-gallery-main-section"
        >
          <GLSContainer noPadding testID="certificate-gallery-main-container">
            <View
              style={{ borderWidth: 1, borderColor: C.borderSoft, borderRadius: 18, backgroundColor: C.paper, padding: isNarrow ? 14 : 18 }}
              data-testid="certificate-gallery-hero"
              testID="certificate-gallery-hero"
            >
              <Text style={{ color: C.primary, fontSize: 11, fontWeight: '900', letterSpacing: 1.4 }} data-testid="certificate-gallery-overline" testID="certificate-gallery-overline">
                {tx('certificateGallery.hero.overline', 'CERTIFICATE GALLERY')}
              </Text>

              <View style={{ marginTop: 10, flexDirection: isNarrow ? 'column' : 'row', justifyContent: 'space-between', gap: 14 }}>
                <View style={{ flex: 1 }}>
                  <Text style={{ color: C.text, fontSize: isNarrow ? 32 : 42, lineHeight: isNarrow ? 38 : 48, fontWeight: '900' }} data-testid="certificate-gallery-title" testID="certificate-gallery-title">
                    {tx('certificateGallery.hero.title', 'Premium certificate records, beautifully organized.')}
                  </Text>
                  <Text style={{ color: C.muted, fontSize: 13, marginTop: 10, lineHeight: 22 }} data-testid="certificate-gallery-subtitle" testID="certificate-gallery-subtitle">
                    {tx('certificateGallery.hero.subtitle', 'Browse regenerated RealAICoach certificates with live status, high-resolution PDF access, secure share links, and instant visibility from course completion to public verification.')}
                  </Text>

                  <View style={{ marginTop: 14, flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
                    <TouchableOpacity onPress={() => router.push('/ai-learning-hub' as any)} style={{ backgroundColor: C.ink, borderRadius: 10, paddingHorizontal: 12, paddingVertical: 9 }} data-testid="certificate-gallery-open-learning-hub-button" testID="certificate-gallery-open-learning-hub-button">
                      <Text style={{ color: colors.primaryText, fontSize: 11, fontWeight: '800' }}>{tx('certificateGallery.actions.openLearningHub', 'Open Learning Hub')}</Text>
                    </TouchableOpacity>
                    <TouchableOpacity onPress={() => router.push('/learner-portfolio' as any)} style={{ borderWidth: 1, borderColor: C.border, borderRadius: 10, paddingHorizontal: 12, paddingVertical: 9 }} data-testid="certificate-gallery-open-portfolio-button" testID="certificate-gallery-open-portfolio-button">
                      <Text style={{ color: C.text, fontSize: 11, fontWeight: '800' }}>{tx('certificateGallery.actions.openLearnerPortfolio', 'Open Learner Portfolio')}</Text>
                    </TouchableOpacity>
                    {isAdmin ? (
                      <TouchableOpacity onPress={() => router.push('/certificate-operations' as any)} style={{ borderWidth: 1, borderColor: C.border, borderRadius: 10, paddingHorizontal: 12, paddingVertical: 9 }} data-testid="certificate-gallery-open-operations-button" testID="certificate-gallery-open-operations-button">
                        <Text style={{ color: C.text, fontSize: 11, fontWeight: '800' }}>{tx('certificateGallery.actions.openOperations', 'Open Operations')}</Text>
                      </TouchableOpacity>
                    ) : null}
                    {latestCertificate ? (
                      <TouchableOpacity onPress={() => openCertificatePage(latestCertificate?.verification_id)} style={{ backgroundColor: C.primary, borderRadius: 10, paddingHorizontal: 12, paddingVertical: 9 }} data-testid="certificate-gallery-open-latest-button" testID="certificate-gallery-open-latest-button">
                        <Text style={{ color: colors.primaryText, fontSize: 11, fontWeight: '800' }}>{tx('certificateGallery.actions.openLatestCertificate', 'Open Latest Certificate')}</Text>
                      </TouchableOpacity>
                    ) : null}
                  </View>

                  {isAdmin ? (
                    <View style={{ marginTop: 14, flexDirection: 'row', flexWrap: 'wrap', gap: 8 }} data-testid="certificate-gallery-mode-toggle" testID="certificate-gallery-mode-toggle">
                      {[
                        { id: 'mine', label: tx('certificateGallery.modes.mine', 'My Certificates') },
                        { id: 'platform', label: tx('certificateGallery.modes.platform', 'Platform Control') },
                      ].map((item) => {
                        const active = mode === item.id;
                        return (
                          <TouchableOpacity
                            key={item.id}
                            onPress={() => setMode(item.id as 'mine' | 'platform')}
                            style={{
                              backgroundColor: active ? C.primary : C.soft,
                              borderRadius: 999,
                              paddingHorizontal: 12,
                              paddingVertical: 8,
                              borderWidth: 1,
                              borderColor: active ? C.primary : C.borderSoft,
                            }}
                            data-testid={`certificate-gallery-mode-${item.id}-button`}
                            testID={`certificate-gallery-mode-${item.id}-button`}
                          >
                    <Text style={{ color: active ? colors.primaryText : C.text, fontSize: 10, fontWeight: '800' }}>{item.label}</Text>
                          </TouchableOpacity>
                        );
                      })}
                    </View>
                  ) : null}
                </View>

                <View style={{ width: isNarrow ? '100%' : 350 }} data-testid="certificate-gallery-stat-cards" testID="certificate-gallery-stat-cards">
                  <GLSGrid columns={12} gap={10} testID="certificate-gallery-stat-grid">
                    {featuredStats.map((item) => (
                      <GLSGridItem key={item.key} span={6} spanMobile={6}>
                        <View style={{ borderWidth: 1, borderColor: C.borderSoft, borderRadius: 12, padding: 12, backgroundColor: C.cardMuted }} data-testid={`certificate-gallery-stat-${item.key}`} testID={`certificate-gallery-stat-${item.key}`}>
                          <Text style={{ color: C.muted, fontSize: 10, fontWeight: '700' }}>{item.label}</Text>
                          <Text style={{ color: C.text, fontSize: 24, marginTop: 8, fontWeight: '900' }}>{item.value}</Text>
                        </View>
                      </GLSGridItem>
                    ))}
                  </GLSGrid>
                </View>
              </View>

              <View style={{ marginTop: 16, borderWidth: 1, borderColor: C.borderSoft, borderRadius: 12, padding: 12, backgroundColor: C.cardMuted }} data-testid="certificate-gallery-toolbar" testID="certificate-gallery-toolbar">
                <Text style={{ color: C.text, fontSize: 12, fontWeight: '800' }} data-testid="certificate-gallery-toolbar-title" testID="certificate-gallery-toolbar-title">
                  {tx('certificateGallery.toolbar.title', 'Filter and manage records')}
                </Text>
                <TextInput
                  value={search}
                  onChangeText={setSearch}
                  placeholder={mode === 'platform' ? tx('certificateGallery.search.platformPlaceholder', 'Search learner, course, certificate ID, verification ID') : tx('certificateGallery.search.minePlaceholder', 'Search your certificates')}
                  placeholderTextColor={C.muted}
                  style={{ marginTop: 10, borderWidth: 1, borderColor: C.borderSoft, borderRadius: 10, paddingHorizontal: 12, paddingVertical: 10, backgroundColor: C.paper, color: C.text }}
                  data-testid="certificate-gallery-search-input"
                  testID="certificate-gallery-search-input"
                />

                <View style={{ marginTop: 10 }}>
                  <Text style={{ color: C.muted, fontSize: 10, fontWeight: '700' }} data-testid="certificate-gallery-status-label" testID="certificate-gallery-status-label">
                    {tx('certificateGallery.filters.status.label', 'Status')}
                  </Text>
                  <View style={{ marginTop: 6, flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
                    {statusOptions.map((item) => {
                      const active = statusFilter === item.id;
                      return (
                        <TouchableOpacity
                          key={item.id}
                          onPress={() => setStatusFilter(item.id)}
                          style={{ backgroundColor: active ? C.primary : C.paper, borderWidth: 1, borderColor: active ? C.primary : C.borderSoft, borderRadius: 999, paddingHorizontal: 12, paddingVertical: 7 }}
                          data-testid={`certificate-gallery-filter-${item.id}`}
                          testID={`certificate-gallery-filter-${item.id}`}
                        >
                    <Text style={{ color: active ? colors.primaryText : C.text, fontSize: 10, fontWeight: '800' }}>{item.label}</Text>
                        </TouchableOpacity>
                      );
                    })}
                  </View>
                </View>

                <View style={{ marginTop: 10 }}>
                  <Text style={{ color: C.muted, fontSize: 10, fontWeight: '700' }} data-testid="certificate-gallery-sort-label" testID="certificate-gallery-sort-label">
                    {tx('certificateGallery.filters.sort.label', 'Sort')}
                  </Text>
                  <View style={{ marginTop: 6, flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
                    {sortOptions.map((item) => {
                      const active = sortMode === item.id;
                      return (
                        <TouchableOpacity
                          key={item.id}
                          onPress={() => setSortMode(item.id)}
                          style={{ backgroundColor: active ? C.ink : C.paper, borderWidth: 1, borderColor: C.borderSoft, borderRadius: 999, paddingHorizontal: 12, paddingVertical: 7 }}
                          data-testid={`certificate-gallery-sort-${item.id}`}
                          testID={`certificate-gallery-sort-${item.id}`}
                        >
                    <Text style={{ color: active ? colors.primaryText : C.text, fontSize: 10, fontWeight: '800' }}>{item.label}</Text>
                        </TouchableOpacity>
                      );
                    })}
                  </View>
                </View>
              </View>

              {notice ? (
                <View style={{ marginTop: 12, backgroundColor: C.successBg, borderWidth: 1, borderColor: C.successBorder, borderRadius: 10, padding: 10 }} data-testid="certificate-gallery-notice-banner" testID="certificate-gallery-notice-banner">
                  <Text style={{ color: C.successText, fontSize: 11, fontWeight: '700' }} data-testid="certificate-gallery-notice-text" testID="certificate-gallery-notice-text">
                    {notice}
                  </Text>
                </View>
              ) : null}

              {error ? (
                <View style={{ marginTop: 12, backgroundColor: C.dangerBg, borderWidth: 1, borderColor: C.dangerBorder, borderRadius: 10, padding: 10 }} data-testid="certificate-gallery-error-banner" testID="certificate-gallery-error-banner">
                  <Text style={{ color: C.rose, fontSize: 11, fontWeight: '700' }} data-testid="certificate-gallery-error-text" testID="certificate-gallery-error-text">
                    {error}
                  </Text>
                </View>
              ) : null}
            </View>

            {isLoadingState ? (
              <View style={{ marginTop: 12, borderWidth: 1, borderColor: C.border, borderRadius: 16, padding: 28, alignItems: 'center', backgroundColor: C.paper }} data-testid="certificate-gallery-loading-state" testID="certificate-gallery-loading-state">
                <ActivityIndicator size="large" color={C.primary} />
                <Text style={{ color: C.muted, fontSize: 12, marginTop: 10 }} data-testid="certificate-gallery-loading-text" testID="certificate-gallery-loading-text">
                  {tx('certificateGallery.loadingRecords', 'Loading certificate records...')}
                </Text>
              </View>
            ) : null}

            {!isLoadingState && latestCertificate ? (
              <View style={{ marginTop: 12, borderWidth: 1, borderColor: C.border, borderRadius: 16, backgroundColor: C.paper, padding: 14 }} data-testid="certificate-gallery-featured-card" testID="certificate-gallery-featured-card">
                <View style={{ flexDirection: isNarrow ? 'column' : 'row', gap: 14 }}>
                  <View style={{ flex: isNarrow ? undefined : 0.8 }}>
                    <Text style={{ color: C.text, fontSize: 18, fontWeight: '800' }} data-testid="certificate-gallery-featured-title" testID="certificate-gallery-featured-title">
                      {tx('certificateGallery.featured.title', 'Featured latest certificate')}
                    </Text>
                    <View style={{ marginTop: 10, borderWidth: 1, borderColor: C.border, borderRadius: 12, padding: 10, backgroundColor: C.soft }}>
                      <CertificatePreviewImage
                        backgroundColor={C.soft}
                        borderRadius={12}
                        fallbackCopy={tx('certificateGallery.featured.previewFallbackCopy', 'Use the certificate actions on the right while the featured preview restores.')}
                        fallbackTitle={tx('certificateGallery.featured.previewFallbackTitle', 'Featured preview unavailable')}
                        iconColor={C.primary}
                        imageStyle={{ width: '100%', aspectRatio: 0.707, borderRadius: 12, backgroundColor: C.soft }}
                        imageTestId="certificate-gallery-featured-preview-image"
                        placeholderTestId="certificate-gallery-featured-preview-fallback"
                        resizeMode="cover"
                        textColor={C.text}
                        urls={[latestCertificate?.preview_image_url, latestCertificate?.thumbnail_image_url, latestCertificate?.public_png_url]}
                      />
                    </View>
                  </View>

                  <View style={{ flex: 1, borderWidth: 1, borderColor: C.border, borderRadius: 12, backgroundColor: C.cardMuted, padding: 12 }}>
                    <CertificateStatusBadge status={latestCertificate?.status} testID="certificate-gallery-featured-status" />
                    <Text style={{ color: C.text, fontSize: isNarrow ? 22 : 26, lineHeight: isNarrow ? 30 : 34, marginTop: 10, fontWeight: '900' }} data-testid="certificate-gallery-featured-course-title" testID="certificate-gallery-featured-course-title">
                      {latestCertificate?.course_title || tx('certificateGallery.card.certificateFallback', 'Certificate')}
                    </Text>
                    {mode === 'platform' ? (
                      <Text style={{ color: C.muted, fontSize: 12, marginTop: 7 }} data-testid="certificate-gallery-featured-learner-name" testID="certificate-gallery-featured-learner-name">
                        {tx('certificateGallery.featured.learnerWithName', 'Learner · {name}').replace('{name}', latestCertificate?.learner_name || tx('certificateGallery.card.unknown', 'Unknown'))}
                      </Text>
                    ) : null}
                    <Text style={{ color: C.muted, fontSize: 12, marginTop: 7 }} data-testid="certificate-gallery-featured-certificate-id" testID="certificate-gallery-featured-certificate-id">
                      {tx('certificateGallery.card.certificateIdWithValue', 'Certificate ID · {value}').replace('{value}', latestCertificate?.certificate_number || '—')}
                    </Text>
                    <Text style={{ color: C.muted, fontSize: 12, marginTop: 4 }} data-testid="certificate-gallery-featured-issued" testID="certificate-gallery-featured-issued">
                      {tx('certificateGallery.card.issuedWithValue', 'Issued · {value}').replace('{value}', formatCertificateDate(latestCertificate?.issued_at))}
                    </Text>
                    <Text style={{ color: C.muted, fontSize: 12, marginTop: 4 }} data-testid="certificate-gallery-featured-expires" testID="certificate-gallery-featured-expires">
                      {tx('certificateGallery.card.expiresWithValue', 'Expires · {value}').replace('{value}', formatCertificateDate(latestCertificate?.expiration_date, tx('certificateGallery.common.lifetimeValidity', 'Lifetime Validity')))}
                    </Text>

                    <View style={{ marginTop: 12, flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
                      <TouchableOpacity onPress={() => openCertificatePage(latestCertificate?.verification_id)} style={{ backgroundColor: C.ink, borderRadius: 10, paddingHorizontal: 10, paddingVertical: 8 }} data-testid="certificate-gallery-featured-view-button" testID="certificate-gallery-featured-view-button">
                        <Text style={{ color: colors.primaryText, fontSize: 11, fontWeight: '800' }}>{tx('certificateGallery.actions.openCertificate', 'Open Certificate')}</Text>
                      </TouchableOpacity>
                      <TouchableOpacity onPress={() => openPrintOptions(latestCertificate)} style={{ backgroundColor: C.primary, borderRadius: 10, paddingHorizontal: 10, paddingVertical: 8 }} data-testid="certificate-gallery-featured-pdf-button" testID="certificate-gallery-featured-pdf-button">
                        <Text style={{ color: colors.primaryText, fontSize: 11, fontWeight: '800' }}>{busyId.startsWith(`pdf-${latestCertificate?.verification_id}`) ? tx('certificateGallery.actions.openingPdf', 'Opening PDF...') : tx('certificateGallery.actions.printOptions', 'Print Options')}</Text>
                      </TouchableOpacity>
                      <TouchableOpacity onPress={() => openComparePage(latestCertificate?.verification_id)} style={{ borderWidth: 1, borderColor: C.border, borderRadius: 10, paddingHorizontal: 10, paddingVertical: 8 }} data-testid="certificate-gallery-featured-compare-button" testID="certificate-gallery-featured-compare-button">
                        <Text style={{ color: C.text, fontSize: 11, fontWeight: '800' }}>{tx('certificateGallery.actions.compare', 'Compare')}</Text>
                      </TouchableOpacity>
                    </View>
                  </View>
                </View>
              </View>
            ) : null}

            {!isLoadingState && visibleCertificates.length === 0 ? (
              <View style={{ marginTop: 12, borderWidth: 1, borderColor: C.border, borderRadius: 14, padding: 24, alignItems: 'center', backgroundColor: C.paper }} data-testid="certificate-gallery-empty-state" testID="certificate-gallery-empty-state">
                <Ionicons name="ribbon-outline" size={28} color={C.muted} />
                <Text style={{ color: C.text, fontSize: 18, fontWeight: '800', marginTop: 10 }} data-testid="certificate-gallery-empty-title" testID="certificate-gallery-empty-title">
                  {tx('certificateGallery.empty.title', 'No certificates match this view')}
                </Text>
                <Text style={{ color: C.muted, fontSize: 12, marginTop: 8, textAlign: 'center', maxWidth: 540 }} data-testid="certificate-gallery-empty-copy" testID="certificate-gallery-empty-copy">
                  {mode === 'platform'
                    ? tx('certificateGallery.empty.platform', 'Adjust the platform filters or search terms to find the certificate you want to manage.')
                    : tx('certificateGallery.empty.mine', 'Complete an AI Learning Hub course and your certificate will appear here automatically.')}
                </Text>
              </View>
            ) : null}

            {!isLoadingState && visibleCertificates.length > 0 ? (
              <View style={{ marginTop: 12 }} data-testid="certificate-gallery-grid-section" testID="certificate-gallery-grid-section">
                <View style={{ flexDirection: isNarrow ? 'column' : 'row', justifyContent: 'space-between', alignItems: isNarrow ? 'flex-start' : 'center', gap: 8 }}>
                  <Text style={{ color: C.text, fontSize: 18, fontWeight: '800' }} data-testid="certificate-gallery-grid-title" testID="certificate-gallery-grid-title">
                    {mode === 'platform'
                      ? tx('certificateGallery.grid.platformTitle', 'Platform certificate control')
                      : tx('certificateGallery.grid.mineTitle', 'All earned certificates')}
                  </Text>
                  <Text style={{ color: C.muted, fontSize: 12 }} data-testid="certificate-gallery-grid-count" testID="certificate-gallery-grid-count">
                    {tx('certificateGallery.grid.countWithValue', '{count} records').replace('{count}', String(visibleCertificates.length))}
                  </Text>
                </View>

                <View style={{ marginTop: 10 }}>
                  <GLSGrid columns={12} gap={12} testID="certificate-gallery-grid">
                    {visibleCertificates.map((certificate, index) => (
                      <GLSGridItem
                        key={certificate?.certificate_id || certificate?.verification_id || `certificate-grid-${index}`}
                        span={isMobile ? 12 : isTablet ? 6 : 4}
                        spanMobile={12}
                        spanTablet={6}
                        spanDesktop={4}
                      >
                        {renderCertificateCard(certificate, index, mode === 'platform')}
                      </GLSGridItem>
                    ))}
                  </GLSGrid>
                </View>
              </View>
            ) : null}
          </GLSContainer>
        </GLSSection>
      </ScrollView>

      <Modal visible={!!revocationTarget} transparent animationType="fade" onRequestClose={() => setRevocationTarget(null)}>
        <View style={{ flex: 1, backgroundColor: 'rgba(15,23,42,0.58)', alignItems: 'center', justifyContent: 'center', padding: 18 }}>
          <View style={{ width: '100%', maxWidth: 560, backgroundColor: C.paper, borderWidth: 1, borderColor: C.borderSoft, borderRadius: 14, padding: 18 }} data-testid="certificate-gallery-revoke-modal" testID="certificate-gallery-revoke-modal">
            <Text style={{ color: C.text, fontSize: 22, fontWeight: '900' }} data-testid="certificate-gallery-revoke-modal-title" testID="certificate-gallery-revoke-modal-title">
              {tx('certificateGallery.revoke.title', 'Revoke certificate')}
            </Text>
            <Text style={{ color: C.muted, fontSize: 12, marginTop: 8, lineHeight: 20 }} data-testid="certificate-gallery-revoke-modal-copy" testID="certificate-gallery-revoke-modal-copy">
              {tx('certificateGallery.revoke.subtitle', 'This certificate will remain auditable, but its public status will change to revoked immediately.')}
            </Text>

            <TextInput
              value={revocationReason}
              onChangeText={setRevocationReason}
              placeholder={tx('certificateGallery.revoke.reasonPlaceholder', 'Reason for revocation')}
              placeholderTextColor={C.muted}
              multiline
              style={{ marginTop: 12, minHeight: 88, borderWidth: 1, borderColor: C.border, borderRadius: 10, paddingHorizontal: 12, paddingVertical: 10, textAlignVertical: 'top', color: C.text, backgroundColor: C.cardMuted }}
              data-testid="certificate-gallery-revoke-reason-input"
              testID="certificate-gallery-revoke-reason-input"
            />

            <Text style={{ color: C.muted, marginTop: 12, fontSize: 11, fontWeight: '700' }} data-testid="certificate-gallery-revoke-confirm-label" testID="certificate-gallery-revoke-confirm-label">
              {tx('certificateGallery.revoke.confirmPhraseLabel', 'Type REVOKE to confirm')}
            </Text>
            <TextInput
              value={revocationConfirmText}
              onChangeText={setRevocationConfirmText}
              autoCapitalize="characters"
              placeholder={tx('certificateGallery.revoke.confirmPhrasePlaceholder', 'REVOKE')}
              placeholderTextColor={C.muted}
              style={{ marginTop: 6, borderWidth: 1, borderColor: C.border, borderRadius: 10, paddingHorizontal: 12, paddingVertical: 10, color: C.text, backgroundColor: C.cardMuted }}
              data-testid="certificate-gallery-revoke-confirm-input"
              testID="certificate-gallery-revoke-confirm-input"
            />

            <View style={{ marginTop: 14, flexDirection: 'row', gap: 10 }}>
              <TouchableOpacity onPress={() => setRevocationTarget(null)} style={{ flex: 1, borderWidth: 1, borderColor: C.border, borderRadius: 10, paddingVertical: 11, alignItems: 'center' }} data-testid="certificate-gallery-revoke-cancel-button" testID="certificate-gallery-revoke-cancel-button">
                <Text style={{ color: C.text, fontSize: 11, fontWeight: '800' }}>{tx('certificateGallery.actions.cancel', 'Cancel')}</Text>
              </TouchableOpacity>
              <TouchableOpacity
                disabled={revocationConfirmText.trim().toUpperCase() !== REVOKE_CONFIRM_WORD || busyId.startsWith('revoke-')}
                onPress={confirmRevocation}
                style={{
                  flex: 1,
                  backgroundColor: revocationConfirmText.trim().toUpperCase() === REVOKE_CONFIRM_WORD ? C.rose : C.dangerBorder,
                  borderRadius: 10,
                  paddingVertical: 11,
                  alignItems: 'center',
                }}
                data-testid="certificate-gallery-revoke-confirm-button"
                testID="certificate-gallery-revoke-confirm-button"
              >
                <Text style={{ color: colors.primaryText, fontSize: 11, fontWeight: '900' }}>
                  {busyId.startsWith('revoke-') ? tx('certificateGallery.revoke.revoking', 'Revoking...') : tx('certificateGallery.revoke.confirm', 'Confirm revocation')}
                </Text>
              </TouchableOpacity>
            </View>
          </View>
        </View>
      </Modal>

      <CertificatePrintLayoutModal
        visible={!!printTarget}
        onClose={() => setPrintTarget(null)}
        onSelect={(layout) => { void openPdf(printTarget, layout); }}
        colors={{ ...C, borderSoft: C.borderSoft, paper: C.paper, blue: C.primary }}
        busy={busyId.startsWith(`pdf-${printTarget?.verification_id || ''}`)}
        prefix="certificate-gallery"
        previewUrl={printTarget?.public_png_url || printTarget?.preview_image_url || printTarget?.thumbnail_image_url || ''}
      />
    </AppShell>
    </AdminRouteGate>
  );
}