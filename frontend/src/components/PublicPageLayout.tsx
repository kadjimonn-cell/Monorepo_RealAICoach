import React, { useState } from 'react';
import { View, Text, ScrollView, TouchableOpacity, Platform, Image, useWindowDimensions } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import Footer from './Footer';
import { useTheme } from '../context/ThemeContext';
import { useTranslation } from '../hooks/useTranslation';
import { useGLSBreakpoint } from './layout/GlobalLayoutSystem';

const blur = Platform.OS === 'web' ? { backdropFilter: 'blur(16px)', WebkitBackdropFilter: 'blur(16px)' } as any : {};

function PublicNav() {
  const router = useRouter();
  const { darkMode, colors, setThemeMode } = useTheme();
  const { t } = useTranslation();
  const { width, tokens, padding } = useGLSBreakpoint();
  const TC = {
    bg: colors.bg, card: colors.card, cardSoft: colors.cardSoft,
    border: colors.glassBorder, borderLight: colors.borderLight || colors.glassBorder,
    text: colors.text, textSec: colors.textSec, textMuted: colors.textMuted,
    accent: colors.primary, accentSoft: colors.primarySoft,
    navBg: darkMode ? 'rgba(11,18,32,0.9)' : 'rgba(247,249,252,0.96)',
  };
  const isMobile = width < tokens.breakpoints.tablet;
  const isTablet = width >= tokens.breakpoints.tablet && width < tokens.breakpoints.desktop;
  const [menuOpen, setMenuOpen] = useState(false);

  const NAV_LINKS = [
    { key: 'public.nav.about', fallback: 'About', href: '/about-us' },
    { key: 'public.nav.blog', fallback: 'Blog', href: '/blog' },
    { key: 'public.nav.careers', fallback: 'Careers', href: '/careers' },
    { key: 'public.nav.pricing', fallback: 'Pricing', href: '/pricing' },
  ];

  return (
    <>
      <View
        style={[
          {
            backgroundColor: TC.navBg,
            borderBottomWidth: 1,
            borderBottomColor: TC.border,
            paddingVertical: 12,
          },
          Platform.OS === 'web' ? { position: 'sticky' as any, top: 0, zIndex: 100, ...blur } : {},
        ]}
        data-testid="public-nav"
        testID="public-nav"
      >
        <View
          style={{
            maxWidth: tokens.maxWidth,
            alignSelf: 'center' as any,
            width: '100%' as any,
            paddingHorizontal: padding,
            flexDirection: 'row',
            alignItems: 'center',
            justifyContent: 'space-between',
          }}
        >
        {/* Logo */}
        <TouchableOpacity onPress={() => router.push('/welcome')} style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }} data-testid="public-nav-logo" testID="public-nav-logo">
          <Image source={Platform.OS === 'web' ? { uri: '/api/static/images/logo.png' } : require('../../assets/images/logo.png')} style={{ width: isMobile ? 26 : 30, height: isMobile ? 26 : 30, borderRadius: 7 }} resizeMode="contain" accessibilityLabel="AI" />
          <Text style={{ color: TC.text, fontSize: isMobile ? 15 : 17, fontWeight: '800', letterSpacing: -0.3 }}>Real<Text style={{ color: TC.accent }}>AI</Text>Coach</Text>
        </TouchableOpacity>

        {/* Desktop Nav Links */}
        {!isMobile && !isTablet && (
          <View style={{ flexDirection: 'row', gap: 28 }}>
            {NAV_LINKS.map(l => (
              <TouchableOpacity key={l.href} onPress={() => router.push(l.href as any)} data-testid={`public-nav-link-${l.fallback.toLowerCase()}`} testID={`public-nav-link-${l.fallback.toLowerCase()}`}>
                <Text style={{ color: TC.textSec, fontSize: 13, fontWeight: '500' }}>
                  {(() => {
                    const value = t(l.key);
                    return value && value !== l.key ? value : l.fallback;
                  })()}
                </Text>
              </TouchableOpacity>
            ))}
          </View>
        )}

        {/* Right buttons */}
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: isMobile ? 8 : 10 }}>
          {/* Theme toggle */}
          <TouchableOpacity
            onPress={() => setThemeMode(darkMode ? 'light' : 'dark')}
            style={{ width: 32, height: 32, borderRadius: 16, alignItems: 'center', justifyContent: 'center', borderWidth: 1, borderColor: TC.border, backgroundColor: colors.surfaceHover }}
            data-testid="public-nav-theme-toggle" testID="public-nav-theme-toggle"
            accessibilityLabel={darkMode ? 'Switch to light mode' : 'Switch to dark mode'}
          >
            <Ionicons name={darkMode ? 'sunny-outline' : 'moon-outline'} size={15} color={TC.textSec} />
          </TouchableOpacity>
          {!isMobile && (
            <TouchableOpacity onPress={() => router.push('/auth/login')} style={{ paddingHorizontal: 14, paddingVertical: 7, borderRadius: 8, borderWidth: 1, borderColor: TC.border }} data-testid="public-nav-login" testID="public-nav-login">
              <Text style={{ color: TC.textSec, fontSize: 13, fontWeight: '600' }}>{t('public.nav.logIn') !== 'public.nav.logIn' ? t('public.nav.logIn') : 'Log In'}</Text>
            </TouchableOpacity>
          )}
          <TouchableOpacity onPress={() => router.push('/auth/register')} style={{ paddingHorizontal: isMobile ? 14 : 16, paddingVertical: 7, borderRadius: 8, backgroundColor: TC.accent }} data-testid="public-nav-signup" testID="public-nav-signup">
            <Text style={{ color: colors.primaryText, fontSize: 13, fontWeight: '700' }}>
              {isMobile
                ? (t('public.nav.signUp') !== 'public.nav.signUp' ? t('public.nav.signUp') : 'Sign Up')
                : (t('public.nav.signUpFree') !== 'public.nav.signUpFree' ? t('public.nav.signUpFree') : 'Sign Up Free')}
            </Text>
          </TouchableOpacity>
          {(isMobile || isTablet) && (
            <TouchableOpacity onPress={() => setMenuOpen(!menuOpen)} style={{ padding: 6 }} data-testid="public-nav-menu-toggle" testID="public-nav-menu-toggle">
              <Ionicons name={menuOpen ? 'close' : 'menu'} size={22} color={TC.textSec} />
            </TouchableOpacity>
          )}
        </View>
        </View>
      </View>

      {/* Mobile/Tablet Menu */}
      {menuOpen && (isMobile || isTablet) && (
        <View style={{ backgroundColor: TC.card, borderBottomWidth: 1, borderBottomColor: TC.border, paddingVertical: 8, zIndex: 99 }} data-testid="public-nav-mobile-menu" testID="public-nav-mobile-menu">
          <View style={{ maxWidth: tokens.maxWidth, alignSelf: 'center' as any, width: '100%' as any, paddingHorizontal: padding }}>
          {NAV_LINKS.map(l => (
            <TouchableOpacity key={l.href} onPress={() => { router.push(l.href as any); setMenuOpen(false); }} accessibilityLabel={l.fallback} style={{ paddingVertical: 12, borderBottomWidth: 1, borderBottomColor: TC.borderLight }} data-testid={`public-nav-mobile-link-${l.fallback.toLowerCase()}`} testID={`public-nav-mobile-link-${l.fallback.toLowerCase()}`}>
              <Text style={{ color: TC.text, fontSize: 14, fontWeight: '500' }}>
                {(() => {
                  const value = t(l.key);
                  return value && value !== l.key ? value : l.fallback;
                })()}
              </Text>
            </TouchableOpacity>
          ))}
          {isMobile && (
            <TouchableOpacity onPress={() => { router.push('/auth/login'); setMenuOpen(false); }} accessibilityLabel={t('public.nav.logIn') !== 'public.nav.logIn' ? t('public.nav.logIn') : 'Log In'} style={{ paddingVertical: 12 }} data-testid="public-nav-mobile-login" testID="public-nav-mobile-login">
              <Text style={{ color: TC.accent, fontSize: 14, fontWeight: '600' }}>{t('public.nav.logIn') !== 'public.nav.logIn' ? t('public.nav.logIn') : 'Log In'}</Text>
            </TouchableOpacity>
          )}
          </View>
        </View>
      )}
    </>
  );
}

interface PublicPageShellProps {
  children: React.ReactNode;
  maxWidth?: number;
  title?: string;
  subtitle?: string;
  testID?: string;
  'data-testid'?: string;
}

export default function PublicPageShell({
  children,
  maxWidth = 900,
  testID,
  'data-testid': dataTestId,
}: PublicPageShellProps) {
  const { width } = useWindowDimensions();
  const { colors } = useTheme();
  const { tokens, padding } = useGLSBreakpoint();
  const TC = {
    bg: colors.bg,
    border: colors.glassBorder,
  };
  const isMobile = width < tokens.breakpoints.tablet;
  const isUltraWide = width >= 1920;
  const px = padding;

  return (
    <ScrollView
      style={{ flex: 1, backgroundColor: TC.bg }}
      showsVerticalScrollIndicator={false}
      data-testid={dataTestId || testID}
      testID={testID}
    >
      <PublicNav />
      <View style={{ maxWidth: isUltraWide ? Math.max(Math.min(maxWidth, tokens.maxWidthWide), 1000) : Math.min(maxWidth, tokens.maxWidth), alignSelf: 'center', width: '100%', paddingHorizontal: px, paddingTop: isMobile ? 20 : isUltraWide ? 48 : 32, paddingBottom: 60 }}>
        {children}
      </View>
      <Footer variant="welcome" />
    </ScrollView>
  );
}

export { PublicNav };
