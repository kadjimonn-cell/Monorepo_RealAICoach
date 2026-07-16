/**
 * primary-color CTA badge (brand fill), where white text is intentional and
 * theme-invariant. All structural footer chrome uses `colors.*` from
 * useTheme().
 */
import React, { useCallback, useMemo, useState, useRef, useEffect } from 'react';
import { View, Text, TouchableOpacity, StyleSheet, Platform, Image, TextInput, ActivityIndicator, Modal, Animated as RNAnimated } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { useTheme } from '../context/ThemeContext';
// eslint-disable-next-line @typescript-eslint/no-unused-vars
import { getShadow } from '../utils/themeShadows';
import { getTestProps } from '../utils/testProps';
import { FOOTER_LINKS, SOCIAL_LINKS } from '../config/siteConfig';
import { useTranslation } from '../hooks/useTranslation';
import { useGlobalPlatformState } from '../hooks/useGlobalPlatformState';
import { useGLSBreakpoint } from './layout/GlobalLayoutSystem';
import { EnterpriseDisclaimerToken } from './tokens/EnterpriseDisclaimerToken';
import { resolveRuntimeBaseUrl } from '../utils/runtimeBaseUrl';
import { resolveVisitorCtaPath } from '../utils/visitorCtaPolicy';
import { useAuth } from '../context/AuthContext';
import { withAlpha } from '../utils/colorAlpha';
import { buildAnalyticsSource } from '../utils/buildAnalyticsSource';

// Dark divider inside the modal highlight region — an intentional
// near-black rule. Theme-exempt by design.
const MODAL_DIVIDER_BG = 'var(--app-primary)';

interface FooterProps {
  variant?: 'default' | 'welcome';
}

export default function Footer({ variant = 'default' }: FooterProps) {
  const router = useRouter();
  const { colors, darkMode } = useTheme();
  const { isAuthenticated } = useAuth();
  const { state: gpsState } = useGlobalPlatformState();

  // @autofix-moved: was module-level const styles
  const styles = StyleSheet.create({
    root: {
      borderTopWidth: 1,
      paddingTop: 48,
      ...(Platform.OS === 'web' ? { width: '100%' } as any : {}),
    },
    inner: {
      alignSelf: 'center' as any,
      width: '100%' as any,
      paddingBottom: 40,
    },
    innerDesktop: {
      flexDirection: 'row' as any,
      gap: 64,
    },
  
    /* Brand Column */
    brandCol: {
      marginBottom: 36,
    },
    brandColDesktop: {
      flex: 1,
      maxWidth: 380,
      marginBottom: 0,
    },
    brandRow: {
      flexDirection: 'row' as any,
      alignItems: 'center' as any,
      gap: 10,
      marginBottom: 14,
    },
    logo: {
      width: 30,
      height: 30,
      borderRadius: 8,
    },
    brandName: {
      fontSize: 18,
      fontWeight: '800' as any,
      letterSpacing: -0.3,
    },
    tagline: {
      fontSize: 13,
      lineHeight: 21,
      marginBottom: 20,
      maxWidth: 300,
    },
    ctaPill: {
      flexDirection: 'row' as any,
      alignItems: 'center' as any,
      gap: 8,
      paddingHorizontal: 14,
      paddingVertical: 10,
      borderRadius: 10,
      borderWidth: 1,
      marginBottom: 20,
      alignSelf: 'flex-start' as any,
    },
    ctaPillText: {
      fontSize: 12,
      fontWeight: '600' as any,
    },
    socialSection: {
      gap: 12,
      width: '100%' as any,
    },
    socialIntro: {
      gap: 4,
      alignItems: 'center' as any,
    },
    socialEyebrow: {
      fontSize: 10,
      fontWeight: '800' as any,
      letterSpacing: 1.6,
      textTransform: 'uppercase' as any,
    },
    socialTitle: {
      fontSize: 16,
      fontWeight: '800' as any,
      letterSpacing: -0.3,
      textAlign: 'center' as any,
    },
    socialSubtitle: {
      fontSize: 12,
      lineHeight: 18,
      textAlign: 'center' as any,
      maxWidth: 360,
    },
    socialRow: {
      flexDirection: 'row' as any,
      gap: 10,
      flexWrap: 'wrap' as any,
      justifyContent: 'center' as any,
      width: '100%' as any,
    },
    socialBtn: {
      minHeight: 58,
      borderRadius: 16,
      borderWidth: 1,
      alignItems: 'center' as any,
      justifyContent: 'center' as any,
      paddingHorizontal: 12,
      paddingVertical: 10,
      gap: 8,
      ...(Platform.OS === 'web' ? { transition: 'opacity 0.18s ease, transform 0.18s ease, box-shadow 0.18s ease, border-color 0.18s ease, background-color 0.18s ease', cursor: 'default' } as any : {}),
    },
    socialBtnIconRow: {
      flexDirection: 'row' as any,
      alignItems: 'center' as any,
      justifyContent: 'center' as any,
      gap: 6,
    },
    socialBtnLabel: {
      fontSize: 11,
      fontWeight: '800' as any,
      textAlign: 'center' as any,
    },
    socialBtnIntent: {
      fontSize: 10,
      lineHeight: 14,
      textAlign: 'center' as any,
      opacity: 0.92,
    },
    socialBtnExternal: {
      width: 18,
      height: 18,
      borderRadius: 9,
      alignItems: 'center' as any,
      justifyContent: 'center' as any,
    },
  
    /* Link Grid */
    linksGrid: {
      flex: 1,
    },
    linksGridDesktop: {
      flexDirection: 'row' as any,
      gap: 48,
    },
    linksGridTablet: {
      flexDirection: 'row' as any,
      flexWrap: 'wrap' as any,
      gap: 32,
    },
    linksGridMobile: {
      flexDirection: 'row' as any,
      flexWrap: 'wrap' as any,
      gap: 14,
      justifyContent: 'center' as any,
    },
    linkCol: {
      minWidth: 0,
      flexBasis: '46%' as any,
      flex: 1,
      marginBottom: 8,
    },
    colTitle: {
      fontSize: 13,
      fontWeight: '700' as any,
      letterSpacing: 0.4,
      textTransform: 'uppercase' as any,
      marginBottom: 6,
    },
    colTitleUnderline: {
      width: 20,
      height: 2,
      borderRadius: 1,
      marginBottom: 14,
    },
    linkItem: {
      flexDirection: 'row' as any,
      alignItems: 'center' as any,
      paddingVertical: 5,
      ...(Platform.OS === 'web' ? { cursor: 'pointer' } as any : {}),
    },
    linkLabel: {
      fontSize: 13,
      fontWeight: '500' as any,
      lineHeight: 20,
    },
  
    /* Divider */
    divider: {
      height: 1,
      alignSelf: 'center' as any,
      width: '100%' as any,
    },
  
    /* Bottom Bar */
    bottomBar: {
      alignSelf: 'center' as any,
      width: '100%' as any,
      paddingVertical: 20,
      gap: 12,
    },
    bottomBarDesktop: {
      flexDirection: 'row' as any,
      justifyContent: 'space-between' as any,
      alignItems: 'center' as any,
    },
    bottomLeft: {
      flexDirection: 'row' as any,
      alignItems: 'center' as any,
      gap: 8,
      flexWrap: 'wrap' as any,
    },
    bottomCenter: {
      flexDirection: 'row' as any,
      alignItems: 'center' as any,
      gap: 4,
    },
    copyright: {
      fontSize: 12,
      fontWeight: '500' as any,
    },
    statusDot: {
      width: 6,
      height: 6,
      borderRadius: 3,
      marginLeft: 4,
    },
    statusText: {
      fontSize: 11,
      fontWeight: '500' as any,
    },
    addressRow: {
      flexDirection: 'row' as any,
      alignItems: 'center' as any,
      gap: 5,
      width: '100%' as any,
      marginTop: 6,
    },
    addressText: {
      fontSize: 11,
      fontWeight: '500' as any,
    },
    bottomRight: {
      flexDirection: 'row' as any,
      alignItems: 'center' as any,
      gap: 10,
      flexWrap: 'wrap' as any,
    },
    badge: {
      flexDirection: 'row' as any,
      alignItems: 'center' as any,
      gap: 5,
      paddingHorizontal: 10,
      paddingVertical: 5,
      borderRadius: 8,
      borderWidth: 1,
    },
    badgeText: {
      fontSize: 11,
      fontWeight: '600' as any,
    },
    versionText: {
      fontSize: 11,
      fontWeight: '500' as any,
      marginLeft: 4,
    },
  
    /* Newsletter */
    nlContainer: {
      marginBottom: 20,
      gap: 8,
    },
    nlTitle: {
      fontSize: 15,
      fontWeight: '700' as any,
      letterSpacing: -0.2,
    },
    nlSubtitle: {
      fontSize: 12,
      lineHeight: 18,
      maxWidth: 300,
      marginBottom: 4,
    },
    nlInputRow: {
      gap: 10,
    },
    nlInputRowDesktop: {
      flexDirection: 'row' as any,
      alignItems: 'center' as any,
    },
    nlInputWrap: {
      flex: 1,
      flexDirection: 'row' as any,
      alignItems: 'center' as any,
      gap: 10,
      paddingHorizontal: 14,
      paddingVertical: 0,
      borderRadius: 10,
      borderWidth: 1,
      height: 46,
      minWidth: 0,
    },
    nlInput: {
      flex: 1,
      fontSize: 13,
      fontWeight: '500' as any,
      ...(Platform.OS === 'web' ? { outlineStyle: 'none', height: 46 } as any : { height: 46 }),
    },
    nlBtn: {
      flexDirection: 'row' as any,
      alignItems: 'center' as any,
      justifyContent: 'center' as any,
      gap: 6,
      paddingHorizontal: 24,
      borderRadius: 10,
      height: 46,
      minWidth: 120,
      ...(Platform.OS === 'web' ? { cursor: 'pointer', transition: 'opacity 0.15s ease', flexShrink: 0 } as any : {}),
    },
    nlBtnText: {
      fontSize: 13,
      fontWeight: '700' as any,
      color: colors.primaryText,
      letterSpacing: 0.2,
    },
    nlSuccess: {
      flexDirection: 'row' as any,
      alignItems: 'flex-start' as any,
      gap: 12,
      paddingHorizontal: 16,
      paddingVertical: 14,
      borderRadius: 12,
      borderWidth: 1,
      borderLeftWidth: 3,
      marginTop: 4,
    },
    nlSuccessText: {
      fontSize: 13,
      fontWeight: '600' as any,
      flex: 1,
    },
    nlErrorRow: {
      flexDirection: 'row' as any,
      alignItems: 'center' as any,
      gap: 6,
      marginTop: 4,
    },
    nlErrorText: {
      fontSize: 12,
      fontWeight: '500' as any,
      color: colors.error,
    },
    nlTrust: {
      flexDirection: 'row' as any,
      alignItems: 'center' as any,
      gap: 6,
      marginTop: 4,
    },
    nlTrustText: {
      fontSize: 11,
      fontWeight: '500' as any,
    },
  
    /* Sign Up Modal */
    modalBackdrop: {
      flex: 1,
      backgroundColor: withAlpha(colors.overlay, 'E6'),
      justifyContent: 'center' as any,
      alignItems: 'center' as any,
      ...(Platform.OS === 'web' ? { backdropFilter: 'blur(8px)', WebkitBackdropFilter: 'blur(8px)' } as any : {}),
    },
    modalBackdropTouch: {
      position: 'absolute' as any,
      top: 0,
      left: 0,
      right: 0,
      bottom: 0,
    },
    modalCard: {
      backgroundColor: 'transparent',
      borderRadius: 20,
      padding: 32,
      maxWidth: 400,
      width: '90%' as any,
      alignItems: 'center' as any,
      borderWidth: 1,
      borderColor: colors.border,
      ...(Platform.OS === 'web' ? { boxShadow: `0 24px 64px ${withAlpha(colors.shadowColor, 'CC')}` } as any : {}),
    },
    modalIconWrap: {
      width: 64,
      height: 64,
      borderRadius: 20,
      alignItems: 'center' as any,
      justifyContent: 'center' as any,
      marginBottom: 20,
    },
    modalTitle: {
      fontSize: 20,
      fontWeight: '800' as any,
      color: colors.primaryText,
      textAlign: 'center' as any,
      letterSpacing: -0.3,
      marginBottom: 10,
    },
    modalDesc: {
      fontSize: 14,
      color: colors.textMuted,
      textAlign: 'center' as any,
      lineHeight: 22,
      marginBottom: 16,
      maxWidth: 320,
    },
    modalHighlight: {
      flexDirection: 'row' as any,
      alignItems: 'center' as any,
      gap: 8,
      paddingHorizontal: 14,
      paddingVertical: 8,
      borderRadius: 10,
      borderWidth: 1,
      marginBottom: 20,
    },
    modalHighlightText: {
      fontSize: 12,
      fontWeight: '700' as any,
    },
    modalDivider: {
      width: '100%' as any,
      height: 1,
      backgroundColor: MODAL_DIVIDER_BG,
      marginBottom: 20,
    },
    modalCta: {
      flexDirection: 'row' as any,
      alignItems: 'center' as any,
      justifyContent: 'center' as any,
      gap: 8,
      width: '100%' as any,
      paddingVertical: 14,
      borderRadius: 12,
      marginBottom: 12,
      ...(Platform.OS === 'web' ? { cursor: 'pointer' } as any : {}),
    },
    modalCtaText: {
      fontSize: 15,
      fontWeight: '800' as any,
      color: colors.primaryText,
      letterSpacing: 0.2,
    },
    modalDismiss: {
      paddingVertical: 8,
      ...(Platform.OS === 'web' ? { cursor: 'pointer' } as any : {}),
    },
    modalDismissText: {
      fontSize: 13,
      color: colors.textMuted,
      fontWeight: '600' as any,
    },
  });
  const { width, isDesktop, isTablet, tokens, padding } = useGLSBreakpoint();
  const footerViewportWidth = Platform.OS === 'web' && typeof window !== 'undefined'
    ? window.innerWidth
    : width;
  const footerResponsiveWidth = variant === 'welcome' ? footerViewportWidth : width;
  const isMobile = footerResponsiveWidth < 560;
  const isCompactMobile = footerResponsiveWidth < 560;
  const isUltraNarrowMobile = footerResponsiveWidth < 300;
  const isNarrowMobile = footerResponsiveWidth < 480;
  const useDensePhoneFooter = variant === 'welcome' && footerResponsiveWidth < 480;
  const useThreeColumnSocial = useDensePhoneFooter && footerResponsiveWidth >= 430;
  const useComfortableDensePhoneType = useDensePhoneFooter && footerResponsiveWidth >= 360 && footerResponsiveWidth < 430;
  const useWideWelcomeFooterLayout = variant === 'welcome' && footerResponsiveWidth >= 1280;
  const useWelcomeDesktopStack = variant === 'welcome' && footerResponsiveWidth >= 1280;
  const isTabletBand = footerResponsiveWidth >= 560 && footerResponsiveWidth < 1280;
  const usePhoneTwoColumnFooter = variant === 'welcome' && footerResponsiveWidth < 560;
  const useCompactTabletFooter = variant === 'welcome' && footerResponsiveWidth >= 560 && footerResponsiveWidth < 880;
  const useTabletFourColumnFooter = variant === 'welcome' && footerResponsiveWidth >= 880 && footerResponsiveWidth < 1280;
  const useMediumDesktopLayout = variant === 'welcome' && footerResponsiveWidth >= 1280 && footerResponsiveWidth < 1480;
  const useWideDesktopLayout = variant === 'welcome' && footerResponsiveWidth >= 1480;
  const useDesktopLikeFooter = variant === 'welcome' && footerResponsiveWidth >= 1280;
  const useCompactTabletSocialGrid = variant === 'welcome' && footerResponsiveWidth >= 560 && footerResponsiveWidth < 880;
  const useBalancedTabletSocialGrid = variant === 'welcome' && footerResponsiveWidth >= 880 && footerResponsiveWidth < 1280;
  const useCenteredLinkCluster = variant === 'welcome';
  const layoutMode = usePhoneTwoColumnFooter
    ? 'phone-two-column'
    : useCompactTabletFooter
      ? 'tablet-two-by-two'
    : useTabletFourColumnFooter
      ? 'tablet-four-column-balanced'
      : useMediumDesktopLayout
        ? 'desktop-four-column-balanced'
        : 'desktop-four-column-wide';
  const [modeTransitionActive, setModeTransitionActive] = useState(false);
  const previousLayoutModeRef = useRef(layoutMode);

  useEffect(() => {
    if (previousLayoutModeRef.current === layoutMode) return;
    previousLayoutModeRef.current = layoutMode;
    setModeTransitionActive(true);
    const timer = setTimeout(() => setModeTransitionActive(false), 220);
    return () => clearTimeout(timer);
  }, [layoutMode]);
  const { t } = useTranslation();
  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };

  const [email, setEmail] = useState('');
  const [nlState, setNlState] = useState<'idle' | 'loading' | 'success' | 'error'>('idle');
  const [nlMsg, setNlMsg] = useState('');
  const [nlSuccessKind, setNlSuccessKind] = useState<'new' | 'already'>('new');
  const [nlBriefingLocal, setNlBriefingLocal] = useState<string>('');
  const [nlPrefsToken, setNlPrefsToken] = useState<string>('');
  const [nlEmailUsed, setNlEmailUsed] = useState<string>('');
  const [nlPrefWeekday, setNlPrefWeekday] = useState<number>(1);
  const [nlPrefHour, setNlPrefHour] = useState<number>(7);
  const [nlCadenceOpen, setNlCadenceOpen] = useState<boolean>(false);
  const [nlCadenceSaving, setNlCadenceSaving] = useState<boolean>(false);
  const [nlCadenceSaved, setNlCadenceSaved] = useState<boolean>(false);
  const [modalVisible, setModalVisible] = useState(false);
  const [modalFeature, setModalFeature] = useState<{ icon: string; title: string; desc: string; highlight: string } | null>(null);
  const [hoveredSocialSlug, setHoveredSocialSlug] = useState<string | null>(null);
  const modalSlide = useRef(new RNAnimated.Value(0)).current;
  const modalOpacity = useRef(new RNAnimated.Value(0)).current;

  const footerBg = variant === 'welcome'
    ? withAlpha(darkMode ? colors.bgAlt : colors.surface, darkMode ? '8A' : 'C8')
    : (darkMode ? colors.bgAlt : colors.surface);
  const borderColor = colors.border;
  const brandWhite = colors.text;
  const mutedText = colors.textMuted;
  const dimText = colors.textSec;
  const linkText = colors.textSec;
  const accentTeal = colors.primary;
  const API_BASE = resolveRuntimeBaseUrl();
  const pillBg = darkMode ? colors.surface : colors.bgSoft;
  const accentText = colors.primaryText;
  const successBg = colors.successSoft;
  const successText = colors.successText;
  const welcomeMobileSidePadding = variant === 'welcome' && isMobile
    ? (useDensePhoneFooter ? 12 : 14)
    : padding;
  const footerContentMaxWidth = usePhoneTwoColumnFooter
    ? footerResponsiveWidth
    : useCompactTabletFooter
      ? Math.min(860, Math.max(520, footerResponsiveWidth - (padding * 2)))
    : useTabletFourColumnFooter
      ? Math.min(980, Math.max(820, footerResponsiveWidth - (padding * 2) - 24))
      : useWideWelcomeFooterLayout
        ? tokens.maxWidth
        : Math.min(tokens.maxWidth, 1120);
  const tabletFourColumnUsableRowWidth = useTabletFourColumnFooter
    ? Math.max(0, footerContentMaxWidth - (welcomeMobileSidePadding * 2))
    : null;
  const welcomeFooterLinkClusterMaxWidth = useWelcomeDesktopStack
    ? Math.min(useWideDesktopLayout ? 1040 : 980, Math.max(760, footerResponsiveWidth - (padding * 2) - 32))
    : useTabletFourColumnFooter
      ? Math.min(tabletFourColumnUsableRowWidth || footerContentMaxWidth, 900)
    : footerContentMaxWidth;
  const footerDisclaimerMaxWidth = variant === 'welcome' && footerResponsiveWidth >= 1180
    ? Math.min(welcomeFooterLinkClusterMaxWidth, useWideDesktopLayout ? 760 : 680)
    : useTabletFourColumnFooter
      ? Math.min(720, footerContentMaxWidth)
    : useCompactTabletFooter
      ? Math.min(680, footerContentMaxWidth)
    : variant === 'welcome' && isMobile
      ? Math.min(388, Math.max(268, footerResponsiveWidth - (welcomeMobileSidePadding * 2) - (isCompactMobile ? 6 : 10)))
    : usePhoneTwoColumnFooter
      ? Math.min(640, Math.max(320, footerResponsiveWidth - welcomeMobileSidePadding * 2))
      : useTabletFourColumnFooter
        ? footerContentMaxWidth
        : tokens.maxWidth;
  const compactTabletSocialGridGap = 12;
  const compactTabletSocialGridMaxWidth = useCompactTabletSocialGrid
    ? Math.max(0, Math.min(720, footerContentMaxWidth - (welcomeMobileSidePadding * 2)))
    : null;
  const balancedTabletSocialGridMaxWidth = useBalancedTabletSocialGrid
    ? Math.max(0, Math.min(760, footerContentMaxWidth))
    : null;
  const compactTabletUsableRowWidth = useCompactTabletFooter
    ? Math.max(0, footerContentMaxWidth - (welcomeMobileSidePadding * 2))
    : null;
  const compactTabletSocialUsableRowWidth = useCompactTabletSocialGrid
    ? Math.max(0, footerContentMaxWidth - (padding * 2))
    : null;
  const compactTabletSocialCardWidth = useCompactTabletSocialGrid
    ? Math.max(
      148,
      Math.floor(
        ((compactTabletSocialUsableRowWidth || 0) - (compactTabletSocialGridGap * 2) - 12) / 3,
      ),
    )
    : null;
  const balancedTabletSocialCardWidth = useBalancedTabletSocialGrid
    ? Math.max(
      104,
      Math.floor((((balancedTabletSocialGridMaxWidth || 760) - (compactTabletSocialGridGap * 5)) / 6)),
    )
    : null;
  const compactTabletLinkColumnWidth = useCompactTabletFooter
    ? Math.max(172, Math.floor((((compactTabletUsableRowWidth || footerContentMaxWidth) - 16) / 2)))
    : null;
  const tabletFourColumnLinkColumnWidth = useTabletFourColumnFooter
    ? Math.max(156, Math.floor((((welcomeFooterLinkClusterMaxWidth || tabletFourColumnUsableRowWidth || 820) - 30) / 4)))
    : null;
  const featurePreviewMap = useMemo(() => {
    const entries = new Map<string, { icon: string; title: string; desc: string; highlight: string }>();
    (gpsState?.features || [])
      .filter((feature) => feature.enabled !== false && feature.soft_deactivated !== true)
      .forEach((feature) => {
      const title = feature.title || feature.feature_id;
      entries.set(title, {
        icon: feature.icon || 'sparkles',
        title,
        desc: feature.description || '',
        highlight: feature.status || feature.availability || '',
      });
      });
    return entries;
  }, [gpsState?.features]);

  const trackEvent = (event: string, feature: string) => {
    fetch(`${API_BASE}/api/newsletter/modal/events`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Requested-With': 'XMLHttpRequest',
      },
      body: JSON.stringify({ event, feature }),
    }).catch(() => {});
  };

  const openModal = (featureLabel: string) => {
    const preview = featurePreviewMap.get(featureLabel) || { icon: 'lock-closed', title: featureLabel, desc: '', highlight: '' };
    setModalFeature(preview);
    setModalVisible(true);
    trackEvent('opened', featureLabel);
    RNAnimated.parallel([
      RNAnimated.timing(modalOpacity, { toValue: 1, duration: 250, useNativeDriver: false }),
      RNAnimated.timing(modalSlide, { toValue: 1, duration: 300, useNativeDriver: false }),
    ]).start();
  };

  const closeModal = (reason: 'dismiss' | 'backdrop_close' = 'dismiss') => {
    trackEvent(reason, modalFeature?.title || '');
    RNAnimated.parallel([
      RNAnimated.timing(modalOpacity, { toValue: 0, duration: 200, useNativeDriver: false }),
      RNAnimated.timing(modalSlide, { toValue: 0, duration: 200, useNativeDriver: false }),
    ]).start(() => {
      setModalVisible(false);
      setModalFeature(null);
    });
  };

  const buildProtectedFooterRegisterTarget = useCallback((link: { href?: string; label?: string; i18nKey?: string }) => {
    const sourceSeed = String(link?.i18nKey || link?.label || 'protected-link')
      .trim()
      .toLowerCase()
      .replace(/^footer\.link\./, '')
      .replace(/[^a-z0-9]+/g, '-')
      .replace(/(^-|-$)/g, '') || 'protected-link';
    const params = new URLSearchParams();
    params.set('source', buildAnalyticsSource('footer', sourceSeed));
    params.set('return_to', String(link?.href || '/welcome').trim() || '/welcome');
    return `/auth/register?${params.toString()}`;
  }, []);

  const handleNav = (link: any) => {
    const hrefRaw = String(link?.href || '').trim();
    const i18nKey = String(link?.i18nKey || '').trim().toLowerCase();
    const label = String(link?.label || '').trim().toLowerCase();
    const isPricingLink = i18nKey === 'footer.link.pricing'
      || label === 'pricing'
      || hrefRaw === '/pricing'
      || hrefRaw === '/welcome#pricing'
      || hrefRaw === '/welcome?section=pricing';

    if (isPricingLink) {
      const safePricingTarget = resolveVisitorCtaPath('/pricing', {
        isAuthenticated: Boolean(isAuthenticated),
        surface: 'footer',
        fallbackPath: '/pricing',
      });
      router.push(safePricingTarget as any);
      return;
    }

    if (link.public && link.href) {
      const href = String(link.href || '').trim();
      if (!href) return;
      if (variant === 'welcome' && href === '/careers') {
        const params = new URLSearchParams();
        params.set('ref', 'footer-company');
        params.set('surface', 'welcome-footer');
        router.push(`/careers?${params.toString()}` as any);
        return;
      }
      const safePublicTarget = resolveVisitorCtaPath(href, {
        isAuthenticated: Boolean(isAuthenticated),
        surface: 'footer',
        fallbackPath: '/welcome',
      });
      router.push(safePublicTarget as any);
      return;
    }

    if (!link.public && link.href && !isAuthenticated) {
      const registerTarget = resolveVisitorCtaPath(buildProtectedFooterRegisterTarget(link), {
        isAuthenticated: false,
        surface: 'footer',
        fallbackPath: '/auth/register',
      });
      router.push(registerTarget as any);
      return;
    }

    if (variant === 'welcome') {
      openModal(link.label);
      return;
    }
    if (link.href) {
      const safeTarget = resolveVisitorCtaPath(String(link.href), {
        isAuthenticated: Boolean(isAuthenticated),
        surface: 'footer',
        fallbackPath: '/welcome',
      });
      router.push(safeTarget as any);
    }
  };

  const handleSubscribe = async () => {
    const trimmed = email.trim();
    if (!trimmed || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(trimmed)) {
      setNlState('error');
      setNlMsg(t('footer.invalidEmail'));
      return;
    }
    setNlState('loading');
    try {
      const browserTz = (() => {
        try {
          return Intl.DateTimeFormat().resolvedOptions().timeZone || '';
        } catch {
          return '';
        }
      })();
      const res = await fetch(`${API_BASE}/api/newsletter/subscribe`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Requested-With': 'XMLHttpRequest',
        },
        body: JSON.stringify({
          email: trimmed,
          subscription_type: 'platform',
          timezone: browserTz || undefined,
        }),
      });
      const data = await res.json();
      if (data.success) {
        setNlState('success');
        setNlSuccessKind(data.already_subscribed ? 'already' : 'new');
        setNlBriefingLocal(data.next_briefing_local || '');
        setNlPrefsToken(data.preferences_token || '');
        setNlEmailUsed(trimmed);
        if (typeof data.preferred_weekday === 'number') setNlPrefWeekday(data.preferred_weekday);
        if (typeof data.preferred_hour === 'number') setNlPrefHour(data.preferred_hour);
        setNlCadenceOpen(false);
        setNlCadenceSaved(false);
        setNlMsg(data.already_subscribed
          ? t('footer.nlAlready')
          : t('footer.nlSuccess'));
        if (!data.already_subscribed) setEmail('');
      } else {
        setNlState('error');
        setNlMsg(data.detail || t('footer.nlError'));
      }
    } catch {
      setNlState('error');
      setNlMsg(t('footer.networkError'));
    }
  };

  const saveCadence = async (weekday: number, hour: number) => {
    if (!nlPrefsToken || !nlEmailUsed) return;
    setNlCadenceSaving(true);
    setNlCadenceSaved(false);
    try {
      const browserTz = (() => {
        try { return Intl.DateTimeFormat().resolvedOptions().timeZone || ''; } catch { return ''; }
      })();
      const res = await fetch(`${API_BASE}/api/newsletter/preferences/cadence`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Requested-With': 'XMLHttpRequest',
        },
        body: JSON.stringify({
          email: nlEmailUsed,
          token: nlPrefsToken,
          weekday,
          hour,
          timezone: browserTz || undefined,
        }),
      });
      const data = await res.json();
      if (data?.success) {
        setNlBriefingLocal(data.next_briefing_local || '');
        setNlPrefWeekday(weekday);
        setNlPrefHour(hour);
        setNlCadenceSaved(true);
        setTimeout(() => setNlCadenceOpen(false), 900);
      }
    } catch {
      /* swallow — keep the success card intact */
    } finally {
      setNlCadenceSaving(false);
    }
  };

  const showNewsletter = variant === 'welcome';

  return (
    <View style={[styles.root, { backgroundColor: footerBg, borderTopColor: borderColor, paddingTop: variant === 'welcome' && isMobile ? 32 : 48 }]} {...getTestProps('platform-footer')}>
      {/* Main Footer Content */}
      <View
        style={[
          styles.inner,
          {
            maxWidth: footerContentMaxWidth,
            paddingHorizontal: welcomeMobileSidePadding,
            paddingBottom: variant === 'welcome' && isMobile ? (useDensePhoneFooter ? 6 : 28) : 40,
            rowGap: variant === 'welcome' && isMobile ? (useDensePhoneFooter ? 8 : 14) : (isTabletBand ? 10 : 0),
            ...(Platform.OS === 'web'
              ? {
                transition: 'opacity 220ms ease, transform 220ms ease',
                opacity: modeTransitionActive ? 0.97 : 1,
                transform: modeTransitionActive ? 'translateY(2px)' : 'translateY(0px)',
              }
              : {}),
          },
          variant === 'welcome' && isMobile && {
            alignSelf: 'stretch' as any,
          },
          useWelcomeDesktopStack && {
            flexDirection: 'column' as any,
            alignItems: 'center' as any,
            justifyContent: 'center' as any,
            gap: 24,
            rowGap: 24,
          },
          useTabletFourColumnFooter && {
            flexDirection: 'column' as any,
            alignItems: 'stretch' as any,
            justifyContent: 'center' as any,
            gap: 14,
            rowGap: 14,
          },
          useCompactTabletFooter && {
            flexDirection: 'column' as any,
            alignItems: 'center' as any,
            justifyContent: 'center' as any,
            gap: 16,
            rowGap: 16,
          },
          variant !== 'welcome' && isDesktop && styles.innerDesktop,
        ]}
      >

        {/* Brand Column */}
        <View
          style={[
            styles.brandCol,
            variant !== 'welcome' && isDesktop && styles.brandColDesktop,
            isTabletBand && { maxWidth: 360 },
            useCompactTabletFooter && { maxWidth: footerContentMaxWidth, width: '100%' as any, alignItems: 'center' as any, marginBottom: 0 },
            useTabletFourColumnFooter && { maxWidth: footerContentMaxWidth, width: '100%' as any, alignItems: 'center' as any, marginBottom: 0 },
            useWelcomeDesktopStack && { maxWidth: footerContentMaxWidth, width: '100%' as any, alignItems: 'center' as any, marginBottom: 0 },
            variant === 'welcome' && {
              alignItems: 'center' as any,
              width: '100%' as any,
              alignSelf: 'stretch' as any,
            },
            useDensePhoneFooter && { marginBottom: 4 },
          ]}
          {...getTestProps('footer-brand')}
          data-notranslate
        >
          <View style={[styles.brandRow, variant === 'welcome' && { justifyContent: 'center' as any }]} data-notranslate>
            <Image accessibilityLabel="AI"
              source={Platform.OS === 'web' ? { uri: '/api/static/images/logo.png' } : require('../../assets/images/logo.png')}
              style={styles.logo}
              resizeMode="contain"
            />
            <Text style={[styles.brandName, { color: brandWhite }]} data-notranslate>
              Real<Text style={{ color: accentTeal }}>AI</Text>Coach
            </Text>
          </View>
          <Text style={[styles.tagline, { color: mutedText }, variant === 'welcome' && { textAlign: 'center' as any, maxWidth: footerDisclaimerMaxWidth }]}> 
            {t('footer.tagline')}
          </Text>

          {/* Newsletter signup (welcome only) or CTA pill (authenticated) */}
          {showNewsletter ? (
            <View
              style={[
                styles.nlContainer,
                variant === 'welcome' && {
                  width: '100%' as any,
                  alignSelf: 'center' as any,
                  alignItems: 'center' as any,
                  marginBottom: useDensePhoneFooter ? 8 : undefined,
                  gap: useDensePhoneFooter ? 6 : 8,
                },
              ]}
              {...getTestProps('footer-newsletter')}
            >
              <Text
                style={[
                  styles.nlTitle,
                  { color: brandWhite },
                  variant === 'welcome' && { textAlign: 'center' as any, fontSize: useDensePhoneFooter ? 14 : undefined },
                ]}
                data-testid="footer-newsletter-title"
                testID="footer-newsletter-title"
              >
                {t('footer.nlTitle')}
              </Text>
              <Text
                style={[
                  styles.nlSubtitle,
                  { color: mutedText },
                  variant === 'welcome' && { textAlign: 'center' as any, width: '100%' as any, fontSize: useDensePhoneFooter ? 11 : undefined, lineHeight: useDensePhoneFooter ? 16 : undefined, maxWidth: useDensePhoneFooter ? 300 : undefined, marginBottom: useDensePhoneFooter ? 0 : undefined },
                ]}
                data-testid="footer-newsletter-subtitle"
                testID="footer-newsletter-subtitle"
              >
                {t('footer.nlSubtitle')}
              </Text>
              {nlState === 'success' ? (
                <View
                  style={[styles.nlSuccess, { backgroundColor: successBg, borderColor: colors.success }]}
                  accessibilityRole="status"
                  accessibilityLabel={nlSuccessKind === 'new' ? t('footer.nlSuccessTitle') : t('footer.nlAlreadyTitle')}
                  {...getTestProps('newsletter-success')}
                  data-testid={nlSuccessKind === 'new' ? 'newsletter-success-new' : 'newsletter-success-already'}
                  testID={nlSuccessKind === 'new' ? 'newsletter-success-new' : 'newsletter-success-already'}
                >
                  <Ionicons
                    name={nlSuccessKind === 'new' ? 'sparkles' : 'hand-left'}
                    size={20}
                    color={colors.successText}
                    style={{ marginTop: 1 }}
                  />
                  <View style={{ flex: 1 }}>
                    <Text
                      style={{
                        color: successText,
                        fontSize: 13,
                        fontWeight: '800',
                        letterSpacing: 0.1,
                        marginBottom: 2,
                      }}
                      data-notranslate={false as any}
                    >
                      {nlSuccessKind === 'new'
                        ? t('footer.nlSuccessTitle')
                        : t('footer.nlAlreadyTitle')}
                    </Text>
                    <Text
                      style={[styles.nlSuccessText, { color: successText, fontWeight: '500' as any, opacity: 0.9 }]}
                    >
                      {nlMsg}
                    </Text>
                    {nlBriefingLocal ? (
                      <View
                        style={{
                          flexDirection: 'row' as any,
                          alignItems: 'center' as any,
                          gap: 5,
                          marginTop: 8,
                          paddingTop: 8,
                          borderTopWidth: 1,
                          borderTopColor: withAlpha(colors.success, '40'),
                        }}
                        data-testid="newsletter-success-next-briefing"
                        testID="newsletter-success-next-briefing"
                      >
                        <Ionicons name="time-outline" size={11} color={colors.successText} />
                        <Text style={{ color: successText, fontSize: 11, fontWeight: '700' as any, letterSpacing: 0.1 }}>
                          {tx('footer.newsletter.nextBriefing', 'Next briefing: {time}').replace('{time}', nlBriefingLocal)}
                        </Text>
                      </View>
                    ) : null}

                    {nlPrefsToken ? (
                      <View style={{ marginTop: 8 }}>
                        {!nlCadenceOpen ? (
                          <TouchableOpacity
                            onPress={() => setNlCadenceOpen(true)}
                            style={{ flexDirection: 'row' as any, alignItems: 'center' as any, gap: 4 }}
                            accessibilityRole="button"
                            data-testid="newsletter-cadence-open"
                            testID="newsletter-cadence-open"
                          >
                            <Text style={{ color: successText, fontSize: 11, fontWeight: '600' as any, textDecorationLine: 'underline' as any, opacity: 0.85 }}>
                              {tx('footer.newsletter.cadencePrompt', 'Prefer a different time? Set your briefing cadence')}
                            </Text>
                            <Ionicons name="chevron-forward" size={11} color={successText} />
                          </TouchableOpacity>
                        ) : (
                          <View
                            style={{
                              marginTop: 6,
                              padding: 10,
                              borderRadius: 10,
                              backgroundColor: withAlpha(colors.surface, '14'),
                              borderWidth: 1,
                              borderColor: withAlpha(colors.success, '40'),
                            }}
                            data-testid="newsletter-cadence-editor"
                            testID="newsletter-cadence-editor"
                          >
                            <Text style={{ color: successText, fontSize: 10, fontWeight: '800' as any, marginBottom: 6, letterSpacing: 0.5 }}>
                              {tx('footer.newsletter.weekdayLabel', 'WEEKDAY')}
                            </Text>
                            <View style={{ flexDirection: 'row' as any, flexWrap: 'wrap' as any, gap: 4, marginBottom: 10 }}>
                              {[0,1,2,3,4,5,6].map((idx) => {
                                const active = nlPrefWeekday === idx;
                                const lbl = tx(`footer.newsletter.weekday.${idx}`, ['Mon','Tue','Wed','Thu','Fri','Sat','Sun'][idx]);
                                return (
                                  <TouchableOpacity accessibilityLabel={tx('footer.accessibility.setWeekday', 'Set newsletter preference weekday')}
                                    key={lbl}
                                    onPress={() => setNlPrefWeekday(idx)}
                                    disabled={nlCadenceSaving}
                                    style={{
                                      paddingHorizontal: 9, paddingVertical: 4, borderRadius: 999,
                                      backgroundColor: active ? colors.success : 'transparent',
                                      borderWidth: 1, borderColor: active ? colors.success : withAlpha(colors.success, '59'),
                                    }}
                                    data-testid={`newsletter-cadence-weekday-${idx}`}
                                    testID={`newsletter-cadence-weekday-${idx}`}
                                  >
                                    <Text style={{ color: active ? 'var(--app-primary-text)' : successText, fontSize: 10, fontWeight: '700' as any }}>
                                      {lbl}
                                    </Text>
                                  </TouchableOpacity>
                                );
                              })}
                            </View>
                            <Text style={{ color: successText, fontSize: 10, fontWeight: '800' as any, marginBottom: 6, letterSpacing: 0.5 }}>
                              {tx('footer.newsletter.localHourLabel', 'LOCAL HOUR')}
                            </Text>
                            <View style={{ flexDirection: 'row' as any, flexWrap: 'wrap' as any, gap: 4, marginBottom: 10 }}>
                              {[5,6,7,8,9,12,17,20].map((h) => {
                                const active = nlPrefHour === h;
                                const hr12 = h % 12 || 12;
                                const ampm = h < 12 ? tx('footer.newsletter.ampm.am', 'AM') : tx('footer.newsletter.ampm.pm', 'PM');
                                return (
                                  <TouchableOpacity accessibilityLabel={tx('footer.accessibility.setHour', 'Set newsletter preference hour')}
                                    key={h}
                                    onPress={() => setNlPrefHour(h)}
                                    disabled={nlCadenceSaving}
                                    style={{
                                      paddingHorizontal: 9, paddingVertical: 4, borderRadius: 999,
                                      backgroundColor: active ? colors.success : 'transparent',
                                      borderWidth: 1, borderColor: active ? colors.success : withAlpha(colors.success, '59'),
                                    }}
                                    data-testid={`newsletter-cadence-hour-${h}`}
                                    testID={`newsletter-cadence-hour-${h}`}
                                  >
                                    <Text style={{ color: active ? colors.primaryText : successText, fontSize: 10, fontWeight: '700' as any }}>
                                      {hr12} {ampm}
                                    </Text>
                                  </TouchableOpacity>
                                );
                              })}
                            </View>
                            <View style={{ flexDirection: 'row' as any, gap: 6, alignItems: 'center' as any }}>
                              <TouchableOpacity accessibilityLabel={tx('footer.accessibility.cadenceSave', 'Save newsletter cadence')}
                                onPress={() => saveCadence(nlPrefWeekday, nlPrefHour)}
                                disabled={nlCadenceSaving}
                                style={{
                                  flexDirection: 'row' as any, alignItems: 'center' as any, gap: 5,
                                  paddingVertical: 6, paddingHorizontal: 12, borderRadius: 8,
                                  backgroundColor: colors.success, opacity: nlCadenceSaving ? 0.6 : 1,
                                }}
                                data-testid="newsletter-cadence-save"
                                testID="newsletter-cadence-save"
                              >
                                <Ionicons name={nlCadenceSaved ? 'checkmark' : 'save-outline'} size={11} color={colors.primaryText} />
                                <Text style={{ color: colors.primaryText, fontSize: 10, fontWeight: '800' as any, letterSpacing: 0.3 }}>
                                  {nlCadenceSaving ? tx('footer.newsletter.saveState.saving', 'SAVING…') : nlCadenceSaved ? tx('footer.newsletter.saveState.saved', 'SAVED') : tx('footer.newsletter.saveState.idle', 'SAVE')}
                                </Text>
                              </TouchableOpacity>
                              <TouchableOpacity
                                onPress={() => setNlCadenceOpen(false)}
                                disabled={nlCadenceSaving}
                                style={{ paddingVertical: 6, paddingHorizontal: 10 }}
                                data-testid="newsletter-cadence-cancel"
                                testID="newsletter-cadence-cancel"
                              >
                                <Text style={{ color: successText, fontSize: 10, fontWeight: '700' as any, opacity: 0.7 }}>
                                  {tx('common.cancel', 'Cancel')}
                                </Text>
                              </TouchableOpacity>
                            </View>
                          </View>
                        )}
                      </View>
                    ) : null}
                  </View>
                </View>
              ) : (
                <>
                  <View
                    style={[
                      styles.nlInputRow,
                      (isDesktop || useDensePhoneFooter) && styles.nlInputRowDesktop,
                      variant === 'welcome' && {
                        width: '100%' as any,
                        alignSelf: 'center' as any,
                        gap: useDensePhoneFooter ? 8 : undefined,
                      },
                    ]}
                  >
                    <View style={[styles.nlInputWrap, { backgroundColor: pillBg, borderColor: nlState === 'error' ? 'var(--app-error)' : borderColor, height: useDensePhoneFooter ? 42 : 46, paddingHorizontal: useDensePhoneFooter ? 12 : 14 }]}>
                      <Ionicons name="mail-outline" size={16} color={dimText} />
                      <TextInput
                        style={[styles.nlInput, { color: brandWhite, height: useDensePhoneFooter ? 42 : 46, fontSize: useDensePhoneFooter ? 12.5 : 13 }]}
                        placeholder={t('footer.emailPlaceholder')}
                        placeholderTextColor={dimText}
                        value={email}
                        onChangeText={(t) => { setEmail(t); if (nlState === 'error') setNlState('idle'); }}
                        keyboardType="email-address"
                        autoCapitalize="none"
                        autoCorrect={false}
                        onSubmitEditing={handleSubscribe}
                        {...getTestProps('newsletter-email-input')}
                      />
                    </View>
                    <TouchableOpacity accessibilityLabel={tx('footer.accessibility.subscribe', 'Newsletter subscribe button')}
                      style={[styles.nlBtn, { backgroundColor: accentTeal, opacity: nlState === 'loading' ? 0.7 : 1, height: useDensePhoneFooter ? 42 : 46, minWidth: useDensePhoneFooter ? 108 : 120, paddingHorizontal: useDensePhoneFooter ? 16 : 24 }]}
                      onPress={handleSubscribe}
                      disabled={nlState === 'loading'}
                      activeOpacity={0.8}
                      {...getTestProps('newsletter-subscribe-btn')}
                    >
                      {nlState === 'loading' ? (
                        <ActivityIndicator size="small" color={accentText} />
                      ) : (
                        <>
                          <Text style={[styles.nlBtnText, useDensePhoneFooter ? { fontSize: 12 } : null]}>{t('footer.subscribe')}</Text>
                          <Ionicons name="arrow-forward" size={14} color={accentText} />
                        </>
                      )}
                    </TouchableOpacity>
                  </View>
                  {nlState === 'error' && (
                    <View
                      style={[
                        styles.nlErrorRow,
                        variant === 'welcome' && { justifyContent: 'center' as any, alignSelf: 'center' as any },
                      ]}
                      {...getTestProps('newsletter-error')}
                    >
                      <Ionicons name="alert-circle" size={13} color={colors.error} />
                      <Text style={[styles.nlErrorText, { color: colors.errorText }]}>{nlMsg}</Text>
                    </View>
                  )}
                  <View
                    style={[
                      styles.nlTrust,
                      variant === 'welcome' && { justifyContent: 'center' as any, alignSelf: 'center' as any, marginTop: useDensePhoneFooter ? 0 : undefined },
                    ]}
                  >
                    <Ionicons name="shield-checkmark-outline" size={12} color={dimText} />
                    <Text style={[styles.nlTrustText, { color: dimText }, useDensePhoneFooter ? { fontSize: 10.5 } : null]}>{t('footer.nlTrust')}</Text>
                  </View>
                </>
              )}
            </View>
          ) : (
            <View style={[styles.ctaPill, { backgroundColor: pillBg, borderColor: borderColor }]} {...getTestProps('footer-cta')}>
              <Ionicons name="sparkles" size={14} color={accentTeal} />
              <Text style={[styles.ctaPillText, { color: linkText }]}>{t('footer.cta')}</Text>
              <Ionicons name="arrow-forward" size={12} color={accentTeal} />
            </View>
          )}

          <View style={[styles.socialSection, useDensePhoneFooter ? { gap: 6 } : null]} data-testid="footer-social-section" testID="footer-social-section">
            <View style={[styles.socialIntro, useDensePhoneFooter ? { gap: 3 } : null]}>
              <Text style={[styles.socialEyebrow, { color: accentTeal }]} data-testid="footer-social-eyebrow" testID="footer-social-eyebrow">
                {tx('footer.social.eyebrow', 'Follow RealAICoach')}
              </Text>
              <Text style={[styles.socialTitle, { color: brandWhite }, useDensePhoneFooter ? { fontSize: useComfortableDensePhoneType ? 14.5 : 14, lineHeight: useComfortableDensePhoneType ? 21 : 20, maxWidth: useComfortableDensePhoneType ? 320 : 300 } : null]} data-testid="footer-social-title" testID="footer-social-title">
                {tx('footer.social.title', 'Product drops, operator notes, and weekly AI coaching signals')}
              </Text>
              <Text style={[styles.socialSubtitle, { color: mutedText }, useDensePhoneFooter ? { fontSize: useComfortableDensePhoneType ? 11.5 : 11, lineHeight: useComfortableDensePhoneType ? 17 : 16, maxWidth: useComfortableDensePhoneType ? 320 : 300 } : null]} data-testid="footer-social-subtitle" testID="footer-social-subtitle">
                {tx('footer.social.subtitle', 'Stay close to launches, clips, case studies, and platform updates across our social channels.')}
              </Text>
            </View>

          {/* Social Icons */}
          <View
            style={[
              styles.socialRow,
              variant === 'welcome' && { justifyContent: 'center' as any },
              useDensePhoneFooter ? { gap: 6 } : null,
              useCompactTabletSocialGrid
                ? {
                    gap: compactTabletSocialGridGap,
                    maxWidth: compactTabletSocialGridMaxWidth,
                  }
                : null,
              useBalancedTabletSocialGrid
                ? {
                    gap: 10,
                    maxWidth: balancedTabletSocialGridMaxWidth,
                  }
                : null,
            ]}
            {...getTestProps('footer-socials')}
          >
            {SOCIAL_LINKS.map(s => {
              const isHovered = Platform.OS === 'web' && hoveredSocialSlug === s.slug;
              const motionBorder = isHovered ? (s.accent || accentTeal) : borderColor;
              const motionBg = isHovered
                ? (globalThis as any).__alphaColor(s.accent || accentTeal, darkMode ? '16' : '10')
                : pillBg;
              const motionShadow = isHovered
                ? `0 14px 34px ${(globalThis as any).__alphaColor(s.accent || accentTeal, darkMode ? '1F' : '1A')}`
                : `0 8px 24px ${(globalThis as any).__alphaColor(s.accent || accentTeal, darkMode ? '10' : '12')}`;

              return (
                <TouchableOpacity accessibilityLabel={s.slug}
                  key={s.slug}
                  onHoverIn={Platform.OS === 'web' ? () => setHoveredSocialSlug(s.slug) : undefined}
                  onHoverOut={Platform.OS === 'web' ? () => setHoveredSocialSlug((current) => (current === s.slug ? null : current)) : undefined}
                  style={[
                    styles.socialBtn,
                    {
                      backgroundColor: motionBg,
                      borderColor: motionBorder,
                      ...(Platform.OS === 'web'
                        ? {
                            boxShadow: motionShadow,
                            transform: isHovered ? 'translateY(-3px) scale(1.01)' : 'translateY(0) scale(1)',
                          } as any
                        : {}),
                      width: isUltraNarrowMobile
                        ? '100%' as any
                        : useCompactTabletSocialGrid
                          ? compactTabletSocialCardWidth
                          : useBalancedTabletSocialGrid
                            ? balancedTabletSocialCardWidth
                          : useThreeColumnSocial
                            ? '31.5%' as any
                            : isCompactMobile
                              ? '48%' as any
                              : isNarrowMobile
                                ? '31.5%' as any
                                : 88,
                      minHeight: useDensePhoneFooter ? (useThreeColumnSocial ? 42 : 48) : useCompactTabletSocialGrid ? 64 : useBalancedTabletSocialGrid ? 62 : 58,
                      paddingHorizontal: useDensePhoneFooter ? 8 : 12,
                      paddingVertical: useDensePhoneFooter ? (useThreeColumnSocial ? 6 : 7) : useCompactTabletSocialGrid ? 11 : useBalancedTabletSocialGrid ? 10 : 10,
                      gap: useDensePhoneFooter ? 4 : useCompactTabletSocialGrid ? 7 : useBalancedTabletSocialGrid ? 6 : 8,
                    },
                  ]}
                  accessibilityLabel={s.label}
                  data-testid={`footer-social-${s.slug}`}
                  testID={`footer-social-${s.slug}`}
                  activeOpacity={1}
                >
                  <View style={[styles.socialBtnIconRow, useDensePhoneFooter ? { gap: 4 } : null]}>
                    <Ionicons name={s.icon as any} size={useDensePhoneFooter ? 15 : 18} color={s.accent || mutedText} />
                    <View style={[styles.socialBtnExternal, { backgroundColor: (globalThis as any).__alphaColor(s.accent || accentTeal, darkMode ? '18' : '12') }, useDensePhoneFooter ? { width: 15, height: 15, borderRadius: 8 } : null]} data-testid={`footer-social-external-${s.slug}`} testID={`footer-social-external-${s.slug}`}>
                      <Ionicons name="arrow-up-outline" size={useDensePhoneFooter ? 9 : 11} color={s.accent || accentTeal} />
                    </View>
                  </View>
                  <Text style={[styles.socialBtnLabel, { color: linkText }, useDensePhoneFooter ? { fontSize: useThreeColumnSocial ? 9.5 : 10.5 } : null]} numberOfLines={1}>{s.shortLabel || s.label}</Text>
                  <Text style={[styles.socialBtnIntent, { color: mutedText }, useDensePhoneFooter ? { fontSize: useThreeColumnSocial ? 8.5 : 9, lineHeight: useThreeColumnSocial ? 11 : 12 } : null]} numberOfLines={useDensePhoneFooter ? 1 : 2} data-testid={`footer-social-intent-${s.slug}`} testID={`footer-social-intent-${s.slug}`}>
                    {s.intentLabel || tx('footer.social.intent.default', 'Official updates')}
                  </Text>
                </TouchableOpacity>
              );
            })}
          </View>
          </View>
        </View>

        {/* Link Columns */}
        <View
          style={[
            styles.linksGrid,
            (variant !== 'welcome' && useDesktopLikeFooter) ? styles.linksGridDesktop : (isTablet || isDesktop) ? styles.linksGridTablet : styles.linksGridMobile,
            useWelcomeDesktopStack && {
              width: '100%' as any,
              maxWidth: welcomeFooterLinkClusterMaxWidth,
              flexDirection: 'row' as any,
              flexWrap: 'wrap' as any,
              alignContent: 'center' as any,
              justifyContent: 'center' as any,
              gap: useWideDesktopLayout ? 26 : 22,
              rowGap: useWideDesktopLayout ? 24 : 20,
            },
            isTabletBand && !useTabletFourColumnFooter && !useCompactTabletFooter
              ? { gap: 24, alignContent: 'flex-start' as any, justifyContent: 'center' as any }
              : null,
            useTabletFourColumnFooter && {
              width: '100%' as any,
              maxWidth: welcomeFooterLinkClusterMaxWidth,
              justifyContent: 'center' as any,
              alignContent: 'center' as any,
              gap: 10,
              rowGap: 18,
            },
            useCompactTabletFooter && {
              width: '100%' as any,
              maxWidth: footerContentMaxWidth,
              justifyContent: 'center' as any,
              alignContent: 'center' as any,
              gap: 16,
              rowGap: 16,
            },
            useCenteredLinkCluster && {
              width: '100%' as any,
              justifyContent: 'center' as any,
              alignContent: 'center' as any,
            },
            isMobile && { justifyContent: 'center' as any, gap: isUltraNarrowMobile ? 12 : useDensePhoneFooter ? 6 : 10 },
          ]}
          data-testid="footer-link-columns-grid"
          testID="footer-link-columns-grid"
        >
          {Object.values(FOOTER_LINKS).map(section => (
            <View
              key={section.title}
              style={[
                styles.linkCol,
                useWelcomeDesktopStack
                  ? {
                    minWidth: useWideDesktopLayout ? 180 : 164,
                    maxWidth: useWideDesktopLayout ? 240 : 220,
                    flexBasis: useWideDesktopLayout ? '22%' as any : '21.5%' as any,
                    flexGrow: 0,
                    marginBottom: 0,
                    alignItems: 'center' as any,
                  }
                  : null,
                useTabletFourColumnFooter
                  ? {
                    minWidth: tabletFourColumnLinkColumnWidth || 168,
                    maxWidth: tabletFourColumnLinkColumnWidth || 204,
                    flexBasis: tabletFourColumnLinkColumnWidth || 168,
                    flexGrow: 0,
                    marginBottom: 0,
                    alignItems: useCenteredLinkCluster ? 'center' as any : 'flex-start' as any,
                  }
                  : null,
                useCompactTabletFooter
                  ? {
                    minWidth: compactTabletLinkColumnWidth || 220,
                    maxWidth: compactTabletLinkColumnWidth || 280,
                    flexBasis: compactTabletLinkColumnWidth || 220,
                    flexGrow: 0,
                    marginBottom: 0,
                    alignItems: useCenteredLinkCluster ? 'center' as any : 'flex-start' as any,
                  }
                  : null,
                isTabletBand && !useTabletFourColumnFooter && !useCompactTabletFooter
                  ? {
                    minWidth: 180,
                    maxWidth: 240,
                    flexBasis: footerResponsiveWidth >= 960 ? '22%' as any : '42%' as any,
                    flexGrow: 0,
                    marginBottom: 6,
                    alignItems: useCenteredLinkCluster ? 'center' as any : 'flex-start' as any,
                  }
                  : null,
                isMobile
                  ? {
                    flexBasis: isUltraNarrowMobile ? '100%' as any : 'calc(50% - 8px)' as any,
                    flexGrow: 0,
                    minWidth: isUltraNarrowMobile ? 0 : useDensePhoneFooter ? 118 : 128,
                    maxWidth: isUltraNarrowMobile ? undefined : (isNarrowMobile ? 220 : 260),
                    marginBottom: variant === 'welcome' ? (isUltraNarrowMobile ? 10 : 0) : 8,
                    alignItems: useCenteredLinkCluster ? 'center' as any : undefined,
                  }
                  : null,
              ]}
              data-testid={`footer-section-${section.title.toLowerCase()}-column`}
              testID={`footer-section-${section.title.toLowerCase()}-column`}
              {...getTestProps(`footer-section-${section.title.toLowerCase()}`)}
            >
              <Text
                style={[styles.colTitle, { color: brandWhite, fontSize: useDensePhoneFooter ? (useComfortableDensePhoneType ? 12 : 11.5) : isMobile ? 12 : (isTabletBand ? 12.5 : 13), marginBottom: variant === 'welcome' && isMobile ? 4 : 6, letterSpacing: 0.45, textAlign: useCenteredLinkCluster ? 'center' as any : 'left' as any }]}
                data-testid={`footer-section-${section.title.toLowerCase()}-title`}
                testID={`footer-section-${section.title.toLowerCase()}-title`}
              >
                {section.i18nKey ? t(section.i18nKey) : section.title}
              </Text>
              <View style={[styles.colTitleUnderline, { backgroundColor: accentTeal, alignSelf: useCenteredLinkCluster ? 'center' as any : 'flex-start' as any, marginBottom: useDensePhoneFooter ? 8 : 14, width: useDensePhoneFooter ? 18 : 20 }]} />
              {section.links.map(link => (
                <TouchableOpacity
                  key={link.label}
                  onPress={() => handleNav(link)}
                  activeOpacity={0.6}
                  data-testid={link.href === '/careers' ? 'footer-careers-link' : `footer-link-${link.label.toLowerCase().replace(/\s+/g, '-')}`} testID={link.href === '/careers' ? 'footer-careers-link' : `footer-link-${link.label.toLowerCase().replace(/\s+/g, '-')}`}
                  style={[styles.linkItem, variant === 'welcome' && isMobile ? { paddingVertical: useDensePhoneFooter ? 3 : 5 } : null, useCenteredLinkCluster ? { justifyContent: 'center' as any } : null]}
                >
                  <Text style={[styles.linkLabel, { color: variant === 'welcome' ? colors.textSec : mutedText, fontSize: useDensePhoneFooter ? (useComfortableDensePhoneType ? 12 : 11.25) : isMobile ? 12 : (isTabletBand ? 12.5 : 13), lineHeight: useDensePhoneFooter ? (useComfortableDensePhoneType ? 18 : 17) : isMobile ? 19 : (isTabletBand ? 19 : 20), fontWeight: (isMobile || isTabletBand) ? '600' as any : '500' as any, textAlign: useCenteredLinkCluster ? 'center' as any : 'left' as any }]}>{link.i18nKey ? t(link.i18nKey) : link.label}</Text>
                  {link.external && <Ionicons name="open-outline" size={10} color={dimText} style={{ marginLeft: 4 }} />}
                </TouchableOpacity>
              ))}
            </View>
          ))}
        </View>
      </View>

      {/* ── Enterprise Bottom Bar ── */}
      <View
        style={{
          maxWidth: footerContentMaxWidth,
          alignSelf: 'center' as any,
          width: '100%' as any,
          paddingHorizontal: welcomeMobileSidePadding,
        }}
      >

        {/* Divider with gradient fade */}
        <View style={{ height: 1, backgroundColor: borderColor, opacity: 0.5 }} />

        {/* Enterprise AI Disclaimer */}
        <View style={{ marginTop: variant === 'welcome' ? (useDensePhoneFooter ? 8 : 18) : 14, marginBottom: variant === 'welcome' ? (useDensePhoneFooter ? 12 : isCompactMobile ? 24 : width < 1180 ? 16 : 12) : 0, width: '100%', alignItems: 'center' as any }} data-testid="footer-disclaimer-shell" testID="footer-disclaimer-shell">
          <EnterpriseDisclaimerToken context="footer" testIdPrefix="footer-ai-disclaimer" maxWidth={footerDisclaimerMaxWidth} alignContent={variant === 'welcome' ? 'center' : 'start'} />
        </View>

        {variant !== 'welcome' && (
          <>
            <View style={{
              flexDirection: 'row', alignItems: 'center', justifyContent: 'center',
              paddingVertical: isDesktop ? 20 : 16, gap: isDesktop ? 24 : isTablet ? 14 : 8, flexWrap: 'wrap' as any,
            }} {...getTestProps('footer-trust-badges')}>
              <View {...getTestProps('footer-status-badge')} style={{
                flexDirection: 'row', alignItems: 'center', gap: 6,
                paddingHorizontal: isDesktop ? 14 : 10, paddingVertical: isDesktop ? 7 : 5, borderRadius: 20,
                backgroundColor: successBg, borderWidth: 1, borderColor: colors.successSoft,
              }}>
                <View {...getTestProps('footer-status-dot')} style={{ width: 7, height: 7, borderRadius: 4, backgroundColor: colors.success }} />
                <Text style={{ fontSize: isDesktop ? 11 : 10, fontWeight: '600', color: successText, letterSpacing: 0.3 }}>{t('footer.operational')}</Text>
              </View>
              {[
                { icon: 'shield-checkmark' as const, text: tx('footer.trust.ssl256', '256-bit SSL') },
                { icon: 'earth' as const, text: tx('footer.trust.gdprReady', 'GDPR Ready') },
                { icon: 'globe-outline' as const, text: t('footer.globalReach') },
                { icon: 'speedometer-outline' as const, text: t('footer.uptimeSla') },
              ].map((b, i) => (
                <View key={i} style={{
                  flexDirection: 'row', alignItems: 'center', gap: 6,
                  paddingHorizontal: isDesktop ? 14 : 10, paddingVertical: isDesktop ? 7 : 5, borderRadius: 20,
                  backgroundColor: pillBg, borderWidth: 1, borderColor: borderColor,
                }}>
                  <Ionicons name={b.icon} size={isDesktop ? 12 : 11} color={accentTeal} />
                  <Text style={{ fontSize: isDesktop ? 11 : 10, fontWeight: '600', color: mutedText, letterSpacing: 0.2 }}>{b.text}</Text>
                </View>
              ))}
            </View>
            <View style={{ height: 1, backgroundColor: borderColor, opacity: 0.3 }} />
          </>
        )}

        {/* Copyright & Address Row */}
        <View style={{
          flexDirection: isDesktop ? 'row' : 'column' as any,
          alignItems: isDesktop ? 'center' : 'center' as any,
          justifyContent: isDesktop ? 'space-between' : 'center' as any,
          paddingTop: variant === 'welcome' ? (useDensePhoneFooter ? 0 : isCompactMobile ? 2 : 10) : 18,
          paddingBottom: variant === 'welcome' ? (useDensePhoneFooter ? 4 : isCompactMobile ? 8 : 14) : 18,
          gap: isDesktop ? 0 : useDensePhoneFooter ? 6 : 10,
        }} {...getTestProps('footer-bottom-bar')}>
          <Text style={{ fontSize: 12, fontWeight: '500', color: dimText, textAlign: 'center' as any }} {...getTestProps('footer-copyright')}>
            <Text data-notranslate>{'\u00A9'} {new Date().getFullYear()} RealAICoach LLC.</Text> {t('footer.copyright')}
          </Text>

          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, flexWrap: isCompactMobile ? 'wrap' as any : 'nowrap' as any, justifyContent: 'center' as any, maxWidth: isCompactMobile ? 320 : undefined }} {...getTestProps('footer-address')}>
            <Ionicons name="location-outline" size={11} color={dimText} />
            <Text style={{ fontSize: 11, fontWeight: '500', color: dimText, textAlign: isCompactMobile ? 'center' as any : 'left' as any }}>{tx('footer.address', '11501 Domain Dr, Suite 200, Austin, TX 78758, USA')}</Text>
          </View>

          {variant !== 'welcome' && (
            <Text style={{ fontSize: 11, fontWeight: '500', color: dimText, letterSpacing: 0.5 }}>{tx('footer.version', 'v2.0')}</Text>
          )}
        </View>
      </View>

      {/* Sign Up Free Conversion Modal */}
      {modalVisible && (
        <Modal transparent visible={modalVisible} animationType="none" onRequestClose={closeModal}>
          <RNAnimated.View style={[styles.modalBackdrop, { opacity: modalOpacity }]} {...getTestProps('signup-modal-backdrop')}>
            <TouchableOpacity style={styles.modalBackdropTouch} accessibilityLabel={tx('footer.accessibility.closeModal', 'Close footer modal')} onPress={() => closeModal('backdrop_close')} activeOpacity={1} />
            <RNAnimated.View style={[styles.modalCard, { backgroundColor: colors.surfaceElevated, borderColor: borderColor, transform: [{ translateY: modalSlide.interpolate({ inputRange: [0, 1], outputRange: [40, 0] }) }] }]} {...getTestProps('signup-modal-card')}>
              {/* Feature Icon */}
              <View style={[styles.modalIconWrap, { backgroundColor: (globalThis as any).__alphaColor(accentTeal, '15') }]}>
                <Ionicons name={(modalFeature?.icon || 'lock-closed') as any} size={28} color={accentTeal} />
              </View>

              {/* Title */}
              <Text style={[styles.modalTitle, { color: brandWhite }]} {...getTestProps('signup-modal-title')}>{modalFeature?.title}</Text>

              {/* Description */}
              <Text style={[styles.modalDesc, { color: mutedText }]}>{modalFeature?.desc}</Text>

              {/* Highlight Badge */}
              <View style={[styles.modalHighlight, { backgroundColor: (globalThis as any).__alphaColor(accentTeal, '12'), borderColor: (globalThis as any).__alphaColor(accentTeal, '25') }]}>
                <Ionicons name="checkmark-circle" size={14} color={accentTeal} />
                <Text style={[styles.modalHighlightText, { color: accentTeal }]}>{modalFeature?.highlight}</Text>
              </View>

              {/* Divider */}
              <View style={[styles.modalDivider, { backgroundColor: borderColor }]} />

              {/* CTA */}
              <TouchableOpacity accessibilityLabel={tx('footer.accessibility.signUpFree', 'Sign Up Free')}
                style={[styles.modalCta, { backgroundColor: accentTeal }]}
                onPress={() => {
                  trackEvent('signup_click', modalFeature?.title || '');
                  closeModal('dismiss');
                  const target = resolveVisitorCtaPath('/auth/login', {
                    isAuthenticated: Boolean(isAuthenticated),
                    surface: 'footer',
                    fallbackPath: '/welcome',
                  });
                  router.push(target as any);
                }}
                activeOpacity={0.8}
                {...getTestProps('signup-modal-cta')}
              >
                <Ionicons name="rocket" size={16} color={accentText} />
                <Text style={[styles.modalCtaText, { color: accentText }]}>{t('footer.signUpFree')}</Text>
                <Ionicons name="arrow-forward" size={14} color={accentText} />
              </TouchableOpacity>

              {/* Dismiss */}
              <TouchableOpacity accessibilityLabel={tx('footer.accessibility.signupModalDismiss', 'Dismiss signup modal')} onPress={() => closeModal('dismiss')} style={styles.modalDismiss} activeOpacity={0.6} {...getTestProps('signup-modal-dismiss')}>
                <Text style={styles.modalDismissText}>{t('footer.maybeLater')}</Text>
              </TouchableOpacity>
            </RNAnimated.View>
          </RNAnimated.View>
        </Modal>
      )}
    </View>
  );
}
