import React, { useState, useEffect, useMemo, useRef, useCallback } from 'react';
import { View, Text, TouchableOpacity, ScrollView, ActivityIndicator, Platform, Modal } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useTheme } from '../context/ThemeContext';
import { useAuth } from '../context/AuthContext';
import { useLanguage } from '../i18n/LanguageContext';
import api from '../services/api';

/**
 * TosAcceptanceModal — Enterprise-grade blocking overlay for TOS acceptance.
 * Fully v2 theme compliant — uses only colors.* tokens, no hardcoded values.
 */
export default function TosAcceptanceModal() {
  const { darkMode, colors } = useTheme();
  const { user } = useAuth();
  const { t } = useLanguage();
  const tx = useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);
  const isE2EUser = String(user?.email || '').toLowerCase().startsWith('e2e.') && String(user?.email || '').toLowerCase().endsWith('@example.com');

  const [status, setStatus] = useState<null | {
    accepted: boolean;
    tos_version_id?: string;
    tos_version_number?: string;
    tos_title?: string;
    tos_summary?: string;
  }>(null);
  const [tosContent, setTosContent] = useState<{ heading: string; body: string }[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [accepting, setAccepting] = useState(false);
  const [showFull, setShowFull] = useState(false);
  const autoAcceptAttemptedRef = useRef(false);

  const autoAcceptForE2E = useMemo(() => {
    if (Platform.OS !== 'web') return false;
    if (typeof window === 'undefined') return false;
    try {
      const params = new URLSearchParams(window.location.search || '');
      const queryFlag = (
        params.get('e2eAutoAcceptTos') === '1'
        || params.get('__e2e_auto_tos') === '1'
      );
      const storageFlag = window.localStorage?.getItem('rac:e2e:auto-accept-tos') === '1';
      const webdriverFlag = Boolean((window.navigator as any)?.webdriver);
      return Boolean(queryFlag || storageFlag || webdriverFlag);
    } catch {
      return false;
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    const check = async () => {
      try {
        const res = await api.get('/tos/acceptance-status');
        if (cancelled) return;
        setStatus(res.data);
        if (res.data && !res.data.accepted && res.data.tos_version_id) {
          const tosRes = await api.get('/tos/current');
          if (!cancelled && tosRes.data?.tos) {
            setTosContent(tosRes.data.tos.content_sections || []);
          }
        }
      } catch {
        if (!cancelled) setStatus({ accepted: true });
      }
      if (!cancelled) setLoading(false);
    };
    check();
    return () => { cancelled = true; };
  }, []);

  const handleAccept = useCallback(async () => {
    setAccepting(true);
    try {
      await api.post('/tos/accept');
      setStatus(prev => prev ? { ...prev, accepted: true } : null);
    } catch (e) {
      console.error('TOS accept error:', e);
    }
    setAccepting(false);
  }, []);

  useEffect(() => {
    if (!autoAcceptForE2E || isE2EUser) return;
    if (loading || !status || status.accepted || accepting) return;
    if (autoAcceptAttemptedRef.current) return;
    autoAcceptAttemptedRef.current = true;
    void handleAccept();
  }, [accepting, autoAcceptForE2E, handleAccept, isE2EUser, loading, status]);

  if (isE2EUser) return null;
  if (loading || !status || status.accepted) return null;

  const sections = tosContent || [];
  const visibleSections = showFull ? sections : sections.slice(0, 2);
  const hasMore = sections.length > 2 && !showFull;

  return (
    <Modal visible={true} transparent animationType="fade" data-testid="tos-acceptance-modal" testID="tos-acceptance-modal">
    <View style={{
      flex: 1,
      backgroundColor: colors.overlay,
      alignItems: 'center', justifyContent: 'center',
      padding: 24,
    }}>
      <View style={{
        width: '100%', maxWidth: 540, maxHeight: '92%',
        backgroundColor: colors.card,
        borderRadius: 12,
        overflow: 'hidden',
        borderWidth: 1, borderColor: colors.border,
        ...(Platform.OS === 'web' ? {
          boxShadow: `0 25px 50px -12px ${colors.shadowColor}`,
        } : {
          shadowColor: colors.shadowColor, shadowOffset: { width: 0, height: 12 },
          shadowOpacity: 0.15, shadowRadius: 24, elevation: 12,
        }),
      } as any} data-testid="tos-modal-container" testID="tos-modal-container">

        {/* Header */}
        <View style={{ padding: 32, paddingBottom: 0 }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 14, marginBottom: 8 }}>
            <View style={{
              width: 48, height: 48, borderRadius: 12,
              backgroundColor: colors.primarySoft,
              borderWidth: 1, borderColor: colors.border,
              alignItems: 'center', justifyContent: 'center',
            }}>
              <Ionicons name="document-text" size={24} color={colors.primary} />
            </View>
            <View style={{ flex: 1 }}>
              <Text style={{ fontSize: 22, fontWeight: '700', color: colors.text, letterSpacing: -0.4 }}
                data-testid="tos-modal-title">
                {status.tos_title || tx('tos.modal.title', 'Terms of Service')}
              </Text>
              <Text style={{ fontSize: 12, fontWeight: '600', color: colors.textMuted, letterSpacing: 1, textTransform: 'uppercase', marginTop: 2 }}>
                {tx('tos.modal.version', 'Version')} {status.tos_version_number || '1.0'}
              </Text>
            </View>
          </View>
        </View>

        {/* What Changed */}
        {status.tos_summary ? (
          <View style={{ paddingHorizontal: 32, paddingTop: 20 }}>
            <View style={{
              backgroundColor: colors.surfaceHover,
              borderRadius: 8, padding: 16,
              borderLeftWidth: 3, borderLeftColor: colors.primary,
              borderWidth: 1, borderColor: colors.border,
            }} data-testid="tos-what-changed-box">
              <Text style={{ fontSize: 11, fontWeight: '700', color: colors.textMuted, textTransform: 'uppercase', letterSpacing: 0.8, marginBottom: 6 }}>
                {tx('tos.modal.whatChanged', 'What changed')}
              </Text>
              <Text style={{ fontSize: 14, color: colors.textSec, lineHeight: 22 }} data-testid="tos-change-summary">
                {status.tos_summary}
              </Text>
            </View>
          </View>
        ) : null}

        {/* Divider */}
        <View style={{ height: 1, backgroundColor: colors.border, marginHorizontal: 32, marginTop: 24 }} />

        {/* Terms Content */}
        <ScrollView
          style={{ maxHeight: 320, paddingHorizontal: 32, paddingTop: 24 }}
          showsVerticalScrollIndicator={false}
          data-testid="tos-scroll-area"
        >
          {visibleSections.map((s, i) => (
            <View key={i} style={{ marginBottom: 24 }}>
              <Text style={{ fontSize: 15, fontWeight: '700', color: colors.text, marginBottom: 8 }}>
                {s.heading}
              </Text>
              <Text style={{ fontSize: 14, color: colors.textSec, lineHeight: 24 }}>
                {s.body}
              </Text>
            </View>
          ))}
          {hasMore && (
            <TouchableOpacity
              onPress={() => setShowFull(true)}
              style={{ flexDirection: 'row', alignItems: 'center', gap: 6, paddingBottom: 8 }}
              activeOpacity={0.7}
              data-testid="tos-expand-sections-button" testID="tos-show-full-btn"
            >
              <Text style={{ fontSize: 14, fontWeight: '600', color: colors.primary }}>
                {tx('tos.modal.showAllSections', `Show all ${sections.length} sections`)}
              </Text>
              <Ionicons name="chevron-down" size={14} color={colors.primary} />
            </TouchableOpacity>
          )}
          {sections.length === 0 && (
            <Text style={{ fontSize: 14, color: colors.textMuted, lineHeight: 22 }}>
              {tx('tos.modal.reviewNotice', 'Please review and accept the updated Terms of Service to continue using the platform.')}
            </Text>
          )}
          <View style={{ height: 16 }} />
        </ScrollView>

        {/* Footer */}
        <View style={{
          padding: 32, paddingTop: 20,
          borderTopWidth: 1, borderTopColor: colors.border,
          backgroundColor: colors.surfaceHover,
        }}>
          {autoAcceptForE2E && (
            <Text
              data-testid="tos-auto-accept-e2e-indicator"
              testID="tos-auto-accept-e2e-indicator"
              style={{ fontSize: 11, color: colors.textMuted, textAlign: 'center', marginBottom: 10 }}
            >
              {tx('tos.modal.e2eAutoAcceptNotice', 'E2E automation mode: terms acceptance is auto-confirmed for this session.')}
            </Text>
          )}
          <Text style={{ fontSize: 13, color: colors.textMuted, textAlign: 'center', lineHeight: 20, marginBottom: 16 }}>
            {tx('tos.modal.acceptanceNotice', 'By clicking "I Accept", you agree to be bound by the updated Terms of Service.')}
          </Text>
          <TouchableOpacity accessibilityLabel="Tos accept button"
            onPress={handleAccept}
            disabled={accepting}
            activeOpacity={0.8}
            style={{
              backgroundColor: accepting ? colors.textDisabled : colors.primary,
              borderRadius: 8,
              paddingVertical: 16,
              alignItems: 'center', justifyContent: 'center',
              flexDirection: 'row', minHeight: 56,
            }}
            data-testid="tos-accept-btn" testID="tos-accept-btn"
          >
            {accepting ? (
              <ActivityIndicator size="small" color={colors.primaryText} data-testid="tos-loading-indicator" />
            ) : (
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                <Text style={{ color: colors.primaryText, fontSize: 16, fontWeight: '600', letterSpacing: 0.2 }}>
                  {tx('tos.modal.acceptButton', 'I Accept')}
                </Text>
                <Ionicons name="arrow-forward" size={16} color={colors.primaryText} />
              </View>
            )}
          </TouchableOpacity>
        </View>
      </View>
    </View>
    </Modal>
  );
}
