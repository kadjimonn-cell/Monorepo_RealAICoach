import React, { useEffect, useMemo, useState } from 'react';
import { View, Text, ScrollView, TouchableOpacity, StyleSheet } from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import api from '../../src/services/api';
import { AnalyticsSkeleton } from '../../src/components/SkeletonLoaders';
import { useTheme } from '../../src/context/ThemeContext';
import { useTranslation } from '../../src/hooks/useTranslation';

export default function SharedContentPage() {
  const { colors } = useTheme();
  const { t } = useTranslation();
  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };

  // @autofix-moved: was module-level const makeStyles
  function makeStyles(colors: any) { return StyleSheet.create({
    center: { flex: 1, backgroundColor: colors.surfaceHover, justifyContent: 'center', alignItems: 'center', padding: 24 },
    loadingText: { color: colors.textMuted, fontSize: 14, marginTop: 16 },
    errorIcon: { marginBottom: 16 },
    errorTitle: { color: colors.text, fontSize: 20, fontWeight: '800', marginBottom: 8 },
    errorText: { color: colors.textMuted, fontSize: 14, textAlign: 'center', maxWidth: 300, lineHeight: 22 },
    homeBtn: { marginTop: 24, paddingHorizontal: 24, paddingVertical: 12, borderRadius: 10, backgroundColor: colors.accent },
    homeBtnText: { color: colors.primaryText, fontSize: 14, fontWeight: '700' },
    container: { flex: 1, backgroundColor: colors.surfaceHover },
    header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: 20, paddingVertical: 16, paddingTop: 20, borderBottomWidth: 1, borderBottomColor: colors.border },
    brandRow: { flexDirection: 'row', alignItems: 'center', gap: 8 },
    logoBox: { width: 32, height: 32, borderRadius: 9, backgroundColor: colors.accentSoft, alignItems: 'center', justifyContent: 'center' },
    brandText: { color: colors.text, fontSize: 16, fontWeight: '800' },
    badge: { flexDirection: 'row', alignItems: 'center', gap: 5, paddingHorizontal: 10, paddingVertical: 5, borderRadius: 8, backgroundColor: colors.primarySoft, borderWidth: 1, borderColor: colors.primarySoft },
    badgeText: { color: colors.primary, fontSize: 11, fontWeight: '700' },
    body: { flex: 1 },
    bodyContent: { padding: 20, maxWidth: 960, alignSelf: 'center', width: '100%' },
    title: { color: colors.text, fontSize: 24, fontWeight: '800', marginBottom: 16, lineHeight: 32 },
    meta: { flexDirection: 'row', flexWrap: 'wrap', gap: 16, marginBottom: 20, paddingBottom: 16, borderBottomWidth: 1, borderBottomColor: colors.border },
    metaItem: { flexDirection: 'row', alignItems: 'center', gap: 5 },
    metaText: { color: colors.textMuted, fontSize: 12 },
    contentCard: { backgroundColor: colors.surface, borderRadius: 14, padding: 20, borderWidth: 1, borderColor: colors.border, marginBottom: 24 },
    contentText: { color: colors.textSec, fontSize: 14, lineHeight: 24 },
    ctaBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, paddingVertical: 14, borderRadius: 12, backgroundColor: colors.accent, marginBottom: 40 },
    ctaBtnText: { color: colors.primaryText, fontSize: 15, fontWeight: '700' },
  }); }
  const s = useMemo(() => makeStyles(colors), [colors]);
  const { token } = useLocalSearchParams<{ token: string }>();
  const router = useRouter();
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!token) return;
    (async () => {
      try {
        const res = await api.get(`/share/${token}`);
        setData(res.data);
      } catch (e: any) {
        const status = e?.response?.status;
        if (status === 410) setError(tx('sharedContent.errors.expired', 'This share link has expired.'));
        else if (status === 404) setError(tx('sharedContent.errors.notFound', 'Share link not found or has been revoked.'));
        else setError(tx('sharedContent.errors.loadFailed', 'Failed to load shared content.'));
      } finally {
        setLoading(false);
      }
    })();
  }, [token]);

  if (loading) {
    return (
      <AnalyticsSkeleton />
    );
  }

  if (error) {
    return (
      <View style={s.center} data-testid="shared-error" testID="shared-error">
        <View style={s.errorIcon}>
          <Ionicons name="alert-circle" size={48} color={colors.error} />
        </View>
        <Text style={s.errorTitle}>{tx('sharedContent.errors.title', 'Unable to Load')}</Text>
        <Text style={s.errorText}>{error}</Text>
        <TouchableOpacity style={s.homeBtn} onPress={() => router.replace('/welcome')} data-testid="shared-go-home" testID="shared-go-home" accessibilityRole="button">
          <Text style={s.homeBtnText}>{tx('sharedContent.actions.goHome', 'Go to RealAICoach')}</Text>
        </TouchableOpacity>
      </View>
    );
  }

  return (
    <View style={s.container} data-testid="shared-content-page" testID="shared-content-page">
      <View style={s.header}>
        <View style={s.brandRow}>
          <View style={s.logoBox}>
            <Ionicons name="flash" size={18} color={colors.info} />
          </View>
          <Text style={s.brandText}>
            Real<Text style={{ color: colors.accent }}>AI</Text>Coach
          </Text>
        </View>
        <View style={s.badge}>
          <Ionicons name="share-social" size={12} color={colors.primary} />
          <Text style={s.badgeText}>{tx('sharedContent.badge.label', 'Shared Content')}</Text>
        </View>
      </View>

      <ScrollView style={s.body} contentContainerStyle={s.bodyContent} showsVerticalScrollIndicator={false}>
        <Text style={s.title} data-testid="shared-title" testID="shared-title">{data?.title || tx('sharedContent.defaultTitle', 'Shared Content')}</Text>

        <View style={s.meta}>
          <View style={s.metaItem}>
            <Ionicons name="layers-outline" size={13} color={colors.textMuted} />
            <Text style={s.metaText}>{data?.feature_key || tx('sharedContent.meta.unknownFeature', 'Unknown')}</Text>
          </View>
          <View style={s.metaItem}>
            <Ionicons name="eye-outline" size={13} color={colors.textMuted} />
            <Text style={s.metaText}>{data?.view_count || 0} views</Text>
          </View>
          <View style={s.metaItem}>
            <Ionicons name="time-outline" size={13} color={colors.textMuted} />
            <Text style={s.metaText}>
              Expires {data?.expires_at ? new Date(data.expires_at).toLocaleDateString() : 'N/A'}
            </Text>
          </View>
        </View>

        <View style={s.contentCard}>
          <Text style={s.contentText} selectable data-testid="shared-content-text" testID="shared-content-text">{data?.content || ''}</Text>
        </View>

        <TouchableOpacity style={s.ctaBtn} onPress={() => router.replace('/auth/register')} data-testid="shared-signup-btn" testID="shared-signup-btn" accessibilityRole="button">
          <Text style={s.ctaBtnText}>Join RealAICoach</Text>
          <Ionicons name="arrow-forward" size={16} color={colors.primaryText} />
        </TouchableOpacity>
      </ScrollView>
    </View>
  );
}
