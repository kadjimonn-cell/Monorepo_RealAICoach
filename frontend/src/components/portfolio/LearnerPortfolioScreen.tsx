import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { ActivityIndicator, Platform, ScrollView, Text, TouchableOpacity, View, useWindowDimensions } from 'react-native';
import { useRouter } from 'expo-router';
import * as Clipboard from 'expo-clipboard';

import api from '../../services/api';
import { useTheme } from '../../context/ThemeContext';
import { CertificatePreviewImage } from '../certificates/CertificatePreviewImage';
import { absoluteCertificateUrl, formatCertificateDate } from '../../utils/certificates';

type PortfolioMode = 'private' | 'public';

interface LearnerPortfolioScreenProps {
  mode: PortfolioMode;
  userId?: string;
}

export const LearnerPortfolioScreen = ({ mode, userId = '' }: LearnerPortfolioScreenProps) => {
  const router = useRouter();
  const { colors } = useTheme();
  const { width } = useWindowDimensions();
  const isNarrow = width < 980;

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [portfolio, setPortfolio] = useState<any>(null);

  const C = useMemo(() => ({
    bg: colors.bg,
    panel: colors.card,
    card: colors.card,
    cardSoft: colors.bgSoft || colors.cardMuted || colors.bg,
    border: colors.border,
    borderSoft: colors.borderSoft || colors.border,
    text: colors.text,
    muted: colors.textMuted,
    primary: colors.primary,
    ink: colors.info,
    successBg: colors.successSoft,
    successBorder: colors.success,
    successText: colors.successText,
    dangerBg: colors.errorSoft,
    dangerBorder: colors.error,
    dangerText: colors.errorText,
  }), [colors]);

  const loadPortfolio = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const endpoint = mode === 'private'
        ? '/ai-learn/portfolio/me'
        : `/ai-learn/portfolio/${encodeURIComponent(userId)}`;
      const res = await api.get(endpoint);
      setPortfolio(res.data || null);
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Unable to load this learner portfolio right now.');
    } finally {
      setLoading(false);
    }
  }, [mode, userId]);

  useEffect(() => {
    if (mode === 'public' && !userId) {
      setError('Portfolio link is invalid.');
      setLoading(false);
      return;
    }
    void loadPortfolio();
  }, [mode, userId, loadPortfolio]);

  const profile = portfolio?.profile || {};
  const metrics = portfolio?.metrics || {};
  const skills = Array.isArray(portfolio?.skills) ? portfolio.skills : [];
  const milestones = Array.isArray(portfolio?.milestones) ? portfolio.milestones : [];
  const certificates = Array.isArray(portfolio?.certificates) ? portfolio.certificates : [];
  const sharePath = String(profile?.share_path || '').trim();
  const shareUrl = useMemo(() => {
    if (!sharePath) return '';
    if (typeof window !== 'undefined' && window.location?.origin) {
      return `${window.location.origin}${sharePath}`;
    }
    return sharePath;
  }, [sharePath]);

  const copyShareLink = useCallback(async () => {
    if (!shareUrl) return;
    try {
      if (Platform.OS === 'web' && typeof navigator !== 'undefined' && navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(shareUrl);
      } else {
        await Clipboard.setStringAsync(shareUrl);
      }
      setNotice('Share link copied.');
    } catch {
      setError('Unable to copy share link.');
    }
  }, [shareUrl]);

  const openCertificate = (verificationId: string) => {
    if (!verificationId) return;
    router.push(`/certificate-verify/${encodeURIComponent(verificationId)}` as any);
  };

  return (
    <ScrollView style={{ flex: 1, backgroundColor: C.bg }} contentContainerStyle={{ paddingBottom: 56 }} data-testid="learner-portfolio-screen" testID="learner-portfolio-screen">
      <View style={{ width: '100%', maxWidth: 1240, alignSelf: 'center', paddingHorizontal: 16, paddingTop: 16 }}>
        <View style={{ borderWidth: 1, borderColor: C.borderSoft, borderRadius: 28, backgroundColor: C.panel, overflow: 'hidden' }} data-testid="learner-portfolio-hero-card" testID="learner-portfolio-hero-card">
          <View style={{ padding: isNarrow ? 18 : 24 }}>
            <Text style={{ color: C.primary, fontSize: 11, fontWeight: '800', letterSpacing: 1.3 }} data-testid="learner-portfolio-overline" testID="learner-portfolio-overline">
              LEARNER PORTFOLIO
            </Text>
            <View style={{ flexDirection: isNarrow ? 'column' : 'row', gap: 14, justifyContent: 'space-between', marginTop: 8 }}>
              <View style={{ flex: 1 }}>
                <Text style={{ color: C.text, fontSize: isNarrow ? 34 : 44, fontWeight: '900', lineHeight: isNarrow ? 40 : 50 }} data-testid="learner-portfolio-name" testID="learner-portfolio-name">
                  {profile?.name || 'Learner'}
                </Text>
                <Text style={{ color: C.muted, fontSize: 13, lineHeight: 22, marginTop: 8 }} data-testid="learner-portfolio-headline" testID="learner-portfolio-headline">
                  {profile?.headline || 'AI Learning Hub Learner'}
                </Text>
                <Text style={{ color: C.muted, fontSize: 11, marginTop: 8 }} data-testid="learner-portfolio-updated-at" testID="learner-portfolio-updated-at">
                  Last updated · {formatCertificateDate(portfolio?.latest_updated_at, 'Not available yet')}
                </Text>
                <View style={{ marginTop: 16, flexDirection: 'row', flexWrap: 'wrap', gap: 10 }}>
                  <TouchableOpacity onPress={copyShareLink} style={{ backgroundColor: C.primary, borderRadius: 12, paddingHorizontal: 14, paddingVertical: 10 }} data-testid="learner-portfolio-copy-share-button" testID="learner-portfolio-copy-share-button">
                    <Text style={{ color: colors.primaryText, fontSize: 11, fontWeight: '800' }}>Copy Share Link</Text>
                  </TouchableOpacity>
                  <TouchableOpacity onPress={() => router.push('/certificate-gallery' as any)} style={{ backgroundColor: C.ink, borderRadius: 12, paddingHorizontal: 14, paddingVertical: 10 }} data-testid="learner-portfolio-open-certificate-gallery-button" testID="learner-portfolio-open-certificate-gallery-button">
                    <Text style={{ color: colors.primaryText, fontSize: 11, fontWeight: '800' }}>Open Certificate Gallery</Text>
                  </TouchableOpacity>
                  <TouchableOpacity onPress={() => router.push('/ai-learning-hub' as any)} style={{ backgroundColor: C.cardSoft, borderRadius: 12, borderWidth: 1, borderColor: C.borderSoft, paddingHorizontal: 14, paddingVertical: 10 }} data-testid="learner-portfolio-open-learning-hub-button" testID="learner-portfolio-open-learning-hub-button">
                    <Text style={{ color: C.text, fontSize: 11, fontWeight: '800' }}>Open Learning Hub</Text>
                  </TouchableOpacity>
                </View>
              </View>

              <View style={{ width: isNarrow ? '100%' : 290, flexDirection: 'row', flexWrap: 'wrap', gap: 10 }} data-testid="learner-portfolio-metrics-grid" testID="learner-portfolio-metrics-grid">
                {[
                  { key: 'certificates', label: 'Certificates', value: metrics?.total_certificates || 0 },
                  { key: 'skills', label: 'Skills', value: metrics?.total_skills || 0 },
                  { key: 'milestones', label: 'Milestones', value: metrics?.total_milestones || 0 },
                  { key: 'completion', label: 'Completion', value: `${Number(metrics?.completion_rate_pct || 0).toFixed(0)}%` },
                ].map((metric) => (
                  <View key={metric.key} style={{ flex: 1, minWidth: 130, borderWidth: 1, borderColor: C.borderSoft, borderRadius: 16, backgroundColor: C.card, padding: 12 }} data-testid={`learner-portfolio-metric-${metric.key}`} testID={`learner-portfolio-metric-${metric.key}`}>
                    <Text style={{ color: C.muted, fontSize: 10, fontWeight: '700' }}>{metric.label}</Text>
                    <Text style={{ color: C.text, fontSize: 24, fontWeight: '900', marginTop: 8 }}>{metric.value}</Text>
                  </View>
                ))}
              </View>
            </View>

            {!!notice ? (
              <View style={{ marginTop: 14, borderWidth: 1, borderColor: C.successBorder, borderRadius: 14, backgroundColor: C.successBg, padding: 10 }} data-testid="learner-portfolio-notice-banner" testID="learner-portfolio-notice-banner">
                <Text style={{ color: C.successText, fontSize: 11, fontWeight: '700' }}>{notice}</Text>
              </View>
            ) : null}
            {!!error ? (
              <View style={{ marginTop: 14, borderWidth: 1, borderColor: C.dangerBorder, borderRadius: 14, backgroundColor: C.dangerBg, padding: 10 }} data-testid="learner-portfolio-error-banner" testID="learner-portfolio-error-banner">
                <Text style={{ color: C.dangerText, fontSize: 11, fontWeight: '700' }}>{error}</Text>
              </View>
            ) : null}
          </View>
        </View>

        {loading ? (
          <View style={{ marginTop: 14, borderRadius: 22, borderWidth: 1, borderColor: C.border, backgroundColor: C.card, alignItems: 'center', padding: 32 }} data-testid="learner-portfolio-loading-state" testID="learner-portfolio-loading-state">
            <ActivityIndicator size="large" color={C.primary} />
            <Text style={{ color: C.muted, fontSize: 12, marginTop: 10 }}>Loading portfolio data...</Text>
          </View>
        ) : null}

        {!loading ? (
          <View style={{ marginTop: 14, flexDirection: isNarrow ? 'column' : 'row', gap: 12 }}>
            <View style={{ flex: 1, borderWidth: 1, borderColor: C.borderSoft, borderRadius: 22, backgroundColor: C.card, padding: 16 }} data-testid="learner-portfolio-skills-card" testID="learner-portfolio-skills-card">
              <Text style={{ color: C.text, fontSize: 19, fontWeight: '800' }} data-testid="learner-portfolio-skills-title" testID="learner-portfolio-skills-title">Skill Signature</Text>
              <Text style={{ color: C.muted, fontSize: 12, marginTop: 6, lineHeight: 19 }} data-testid="learner-portfolio-skills-subtitle" testID="learner-portfolio-skills-subtitle">
                Skills distilled from completed learning paths and roadmap progress.
              </Text>
              <View style={{ marginTop: 12, flexDirection: 'row', flexWrap: 'wrap', gap: 8 }} data-testid="learner-portfolio-skills-list" testID="learner-portfolio-skills-list">
                {skills.length ? skills.map((skill: string, idx: number) => (
                  <View key={`${skill}-${idx}`} style={{ borderWidth: 1, borderColor: C.borderSoft, borderRadius: 999, paddingHorizontal: 10, paddingVertical: 6, backgroundColor: C.cardSoft }} data-testid={`learner-portfolio-skill-chip-${idx}`} testID={`learner-portfolio-skill-chip-${idx}`}>
                    <Text style={{ color: C.text, fontSize: 11, fontWeight: '700' }}>{skill}</Text>
                  </View>
                )) : (
                  <Text style={{ color: C.muted, fontSize: 12 }} data-testid="learner-portfolio-skills-empty" testID="learner-portfolio-skills-empty">No skills recorded yet.</Text>
                )}
              </View>
            </View>

            <View style={{ flex: 1, borderWidth: 1, borderColor: C.borderSoft, borderRadius: 22, backgroundColor: C.card, padding: 16 }} data-testid="learner-portfolio-milestones-card" testID="learner-portfolio-milestones-card">
              <Text style={{ color: C.text, fontSize: 19, fontWeight: '800' }} data-testid="learner-portfolio-milestones-title" testID="learner-portfolio-milestones-title">Completion Milestones</Text>
              <Text style={{ color: C.muted, fontSize: 12, marginTop: 6, lineHeight: 19 }} data-testid="learner-portfolio-milestones-subtitle" testID="learner-portfolio-milestones-subtitle">
                Timeline of course completions, certificates, and roadmap landmarks.
              </Text>
              <View style={{ marginTop: 12, gap: 8 }} data-testid="learner-portfolio-milestones-list" testID="learner-portfolio-milestones-list">
                {milestones.length ? milestones.slice(0, 8).map((milestone: any, idx: number) => (
                  <View key={`${milestone?.title}-${idx}`} style={{ borderWidth: 1, borderColor: C.borderSoft, borderRadius: 14, padding: 10, backgroundColor: C.cardSoft }} data-testid={`learner-portfolio-milestone-row-${idx}`} testID={`learner-portfolio-milestone-row-${idx}`}>
                    <Text style={{ color: C.text, fontSize: 12, fontWeight: '800' }} data-testid={`learner-portfolio-milestone-title-${idx}`} testID={`learner-portfolio-milestone-title-${idx}`}>{milestone?.title || 'Milestone'}</Text>
                    <Text style={{ color: C.muted, fontSize: 11, marginTop: 3 }} data-testid={`learner-portfolio-milestone-detail-${idx}`} testID={`learner-portfolio-milestone-detail-${idx}`}>{milestone?.detail || 'Progress update'}</Text>
                    <Text style={{ color: C.muted, fontSize: 10, marginTop: 4 }} data-testid={`learner-portfolio-milestone-date-${idx}`} testID={`learner-portfolio-milestone-date-${idx}`}>
                      {formatCertificateDate(milestone?.achieved_at, 'In progress')}
                    </Text>
                  </View>
                )) : (
                  <Text style={{ color: C.muted, fontSize: 12 }} data-testid="learner-portfolio-milestones-empty" testID="learner-portfolio-milestones-empty">No milestones yet.</Text>
                )}
              </View>
            </View>
          </View>
        ) : null}

        {!loading ? (
          <View style={{ marginTop: 14, borderWidth: 1, borderColor: C.borderSoft, borderRadius: 24, backgroundColor: C.card, padding: 16 }} data-testid="learner-portfolio-certificates-card" testID="learner-portfolio-certificates-card">
            <Text style={{ color: C.text, fontSize: 20, fontWeight: '900' }} data-testid="learner-portfolio-certificates-title" testID="learner-portfolio-certificates-title">Certificate Showcase</Text>
            <Text style={{ color: C.muted, fontSize: 12, marginTop: 6, lineHeight: 19 }} data-testid="learner-portfolio-certificates-subtitle" testID="learner-portfolio-certificates-subtitle">
              Verified certificates from completed AI Learning Hub journeys.
            </Text>

            {certificates.length ? (
              <View style={{ marginTop: 12, flexDirection: 'row', flexWrap: 'wrap', gap: 10 }} data-testid="learner-portfolio-certificates-grid" testID="learner-portfolio-certificates-grid">
                {certificates.slice(0, 6).map((certificate: any, idx: number) => (
                  <View key={certificate?.certificate_id || certificate?.verification_id || idx} style={{ width: isNarrow ? '100%' : '49%', borderWidth: 1, borderColor: C.borderSoft, borderRadius: 18, overflow: 'hidden', backgroundColor: C.cardSoft }} data-testid={`learner-portfolio-certificate-card-${idx}`} testID={`learner-portfolio-certificate-card-${idx}`}>
                    <TouchableOpacity onPress={() => openCertificate(String(certificate?.verification_id || ''))} data-testid={`learner-portfolio-certificate-preview-button-${idx}`} testID={`learner-portfolio-certificate-preview-button-${idx}`}>
                      <CertificatePreviewImage
                        backgroundColor={C.cardSoft}
                        borderRadius={0}
                        fallbackCopy="Open the certificate to view the full verified record while the image restores."
                        fallbackTitle="Certificate preview restoring"
                        iconColor={C.primary}
                        imageStyle={{ width: '100%', aspectRatio: 0.707, backgroundColor: C.cardSoft }}
                        imageTestId={`learner-portfolio-certificate-preview-image-${idx}`}
                        placeholderTestId={`learner-portfolio-certificate-preview-fallback-${idx}`}
                        resizeMode="cover"
                        textColor={C.text}
                        urls={[certificate?.preview_image_url, certificate?.thumbnail_image_url, certificate?.public_png_url, absoluteCertificateUrl(certificate?.preview_image_url || certificate?.thumbnail_image_url || '')]}
                      />
                    </TouchableOpacity>
                    <View style={{ padding: 12 }}>
                      <Text style={{ color: C.text, fontSize: 14, fontWeight: '800' }} numberOfLines={2} data-testid={`learner-portfolio-certificate-course-${idx}`} testID={`learner-portfolio-certificate-course-${idx}`}>
                        {certificate?.course_title || 'Certificate'}
                      </Text>
                      <Text style={{ color: C.muted, fontSize: 11, marginTop: 6 }} data-testid={`learner-portfolio-certificate-issued-${idx}`} testID={`learner-portfolio-certificate-issued-${idx}`}>
                        Issued · {formatCertificateDate(certificate?.issued_at)}
                      </Text>
                      <TouchableOpacity onPress={() => openCertificate(String(certificate?.verification_id || ''))} style={{ marginTop: 10, alignSelf: 'flex-start', borderRadius: 10, backgroundColor: C.primary, paddingHorizontal: 12, paddingVertical: 8 }} data-testid={`learner-portfolio-certificate-open-button-${idx}`} testID={`learner-portfolio-certificate-open-button-${idx}`}>
                        <Text style={{ color: colors.primaryText, fontSize: 10, fontWeight: '800' }}>View Certificate</Text>
                      </TouchableOpacity>
                    </View>
                  </View>
                ))}
              </View>
            ) : (
              <View style={{ marginTop: 12, borderWidth: 1, borderColor: C.borderSoft, borderRadius: 14, backgroundColor: C.cardSoft, padding: 14 }} data-testid="learner-portfolio-certificates-empty" testID="learner-portfolio-certificates-empty">
                <Text style={{ color: C.muted, fontSize: 12 }}>No certificates have been issued yet.</Text>
              </View>
            )}
          </View>
        ) : null}

        {!loading && mode === 'public' ? (
          <View style={{ marginTop: 14, borderWidth: 1, borderColor: C.borderSoft, borderRadius: 18, backgroundColor: C.panel, padding: 16 }} data-testid="learner-portfolio-public-cta-card" testID="learner-portfolio-public-cta-card">
            <Text style={{ color: C.text, fontSize: 16, fontWeight: '800' }} data-testid="learner-portfolio-public-cta-title" testID="learner-portfolio-public-cta-title">Build your own learner portfolio</Text>
            <Text style={{ color: C.muted, fontSize: 12, marginTop: 6, lineHeight: 19 }} data-testid="learner-portfolio-public-cta-subtitle" testID="learner-portfolio-public-cta-subtitle">
              Join RealAICoach to track progress, earn verified certificates, and publish your growth profile.
            </Text>
            <TouchableOpacity onPress={() => router.push('/auth/register' as any)} style={{ marginTop: 10, alignSelf: 'flex-start', borderRadius: 10, backgroundColor: C.primary, paddingHorizontal: 13, paddingVertical: 9 }} data-testid="learner-portfolio-public-join-button" testID="learner-portfolio-public-join-button">
              <Text style={{ color: colors.primaryText, fontSize: 11, fontWeight: '800' }}>Join RealAICoach</Text>
            </TouchableOpacity>
          </View>
        ) : null}
      </View>
    </ScrollView>
  );
};

/* i18n-probe t('i18n.auto.probe') */
