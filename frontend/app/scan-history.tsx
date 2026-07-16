import React, { useEffect, useMemo, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  _ActivityIndicator,
  RefreshControl,
  useWindowDimensions,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { Redirect, useRouter } from 'expo-router';
import api from '../src/services/api';
import { useAuth } from '../src/context/AuthContext';
import { useTheme } from '../src/context/ThemeContext';
import { useTranslation } from '../src/hooks/useTranslation';
import { TableListSkeleton } from '../src/components/SkeletonLoaders';
import { handleAppRecoverableError } from '../src/utils/appRecoverableError';

interface ScanRecord {
  id: string;
  scan_type: string;
  scanner_title: string;
  summary?: string;
  analysis: any;
  created_at: string;
}

export default function ScanHistoryScreen() {
  const theme = useTheme();

  // @autofix-moved: was module-level const SCAN_META
  const SCAN_META: Record<string, { icon: keyof typeof Ionicons.glyphMap; color: string }> = {
    medimate: { icon: 'medkit', color: theme.colors.error },
    mindease: { icon: 'sparkles', color: '#EC4899' }, // @theme-ok brand-fixed-palette residual accent hex (reviewed)
    fitness: { icon: 'body', color: theme.colors.successText },
    nutritrack: { icon: 'nutrition', color: theme.colors.warningText },
    translate: { icon: 'language', color: theme.colors.accent },
    smartbuy: { icon: 'barcode', color: theme.colors.warningText },
    travelpal: { icon: 'airplane', color: theme.colors.accent },
  };
  // @autofix-moved: was module-level const createStyles
  const createStyles = (C: any) => StyleSheet.create({
    container: {
      flex: 1,
      backgroundColor: C.bg,
    },
    header: {
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'space-between',
      paddingHorizontal: 16,
      paddingVertical: 12,
      backgroundColor: C.card,
      borderBottomWidth: 1,
      borderBottomColor: C.border,
    },
    backButton: {
      width: 38,
      height: 38,
      borderRadius: 19,
      backgroundColor: C.bgSoft,
      alignItems: 'center',
      justifyContent: 'center',
    },
    headerTitle: {
      fontSize: 18,
      fontWeight: '700',
      color: C.text,
    },
    headerSpacer: {
      width: 38,
    },
    statsRow: {
      flexDirection: 'row',
      gap: 10,
      marginTop: 16,
    },
    statCard: {
      flex: 1,
      backgroundColor: C.card,
      borderRadius: 14,
      paddingVertical: 12,
      alignItems: 'center',
      borderWidth: 1,
      borderColor: C.border,
    },
    statDivider: {
      width: 1,
      backgroundColor: C.border,
      alignSelf: 'center',
    },
    statValue: {
      fontSize: 18,
      fontWeight: '700',
      color: C.text,
    },
    statLabel: {
      fontSize: 11,
      color: C.textMuted,
      marginTop: 4,
    },
    loadingContainer: {
      flex: 1,
      justifyContent: 'center',
      alignItems: 'center',
    },
    scrollContent: {
      paddingTop: 16,
      paddingBottom: 32,
    },
    scanCard: {
      flexDirection: 'row',
      alignItems: 'flex-start',
      backgroundColor: C.card,
      borderRadius: 16,
      padding: 16,
      marginBottom: 12,
      borderWidth: 1,
      borderColor: C.border,
    },
    scanIcon: {
      width: 46,
      height: 46,
      borderRadius: 12,
      alignItems: 'center',
      justifyContent: 'center',
    },
    scanContent: {
      flex: 1,
      marginLeft: 12,
    },
    scanHeader: {
      flexDirection: 'row',
      justifyContent: 'space-between',
      alignItems: 'center',
    },
    scanTitle: {
      fontSize: 15,
      fontWeight: '700',
      color: C.text,
      flex: 1,
      marginRight: 8,
    },
    scanDate: {
      fontSize: 11,
      color: C.textMuted,
    },
    scanSummary: {
      fontSize: 12,
      color: C.textSec,
      marginTop: 6,
      lineHeight: 18,
    },
    scanTags: {
      flexDirection: 'row',
      marginTop: 10,
    },
    tag: {
      paddingHorizontal: 8,
      paddingVertical: 3,
      borderRadius: 6,
    },
    tagText: {
      fontSize: 10,
      fontWeight: '600',
      textTransform: 'capitalize',
    },
    emptyContainer: {
      flex: 1,
      alignItems: 'center',
      justifyContent: 'center',
      padding: 32,
    },
    emptyIcon: {
      width: 96,
      height: 96,
      borderRadius: 48,
      backgroundColor: (globalThis as any).__alphaColor(C.primary, '15'),
      alignItems: 'center',
      justifyContent: 'center',
      marginBottom: 24,
    },
    emptyState: {
      alignItems: 'center',
      paddingVertical: 40,
    },
    emptyTitle: {
      fontSize: 18,
      fontWeight: '700',
      color: C.text,
      marginTop: 12,
    },
    emptyText: {
      fontSize: 13,
      color: C.textMuted,
      textAlign: 'center',
      marginTop: 6,
    },
    signInButton: {
      backgroundColor: C.primary,
      paddingHorizontal: 32,
      paddingVertical: 12,
      borderRadius: 12,
      marginTop: 20,
    },
    signInButtonText: {
      color: C.primaryText,
      fontWeight: '600',
    },
    startButton: {
      backgroundColor: C.primary,
      paddingHorizontal: 24,
      paddingVertical: 12,
      borderRadius: 12,
      marginTop: 18,
    },
    startButtonText: {
      color: C.primaryText,
      fontWeight: '600',
    },
    footer: {
      alignItems: 'center',
      paddingTop: 20,
    },
    footerText: {
      fontSize: 11,
      color: C.textMuted,
    },
  });
  const router = useRouter();
  const { isAuthenticated } = useAuth();
  const { t } = useTranslation();
  const { width } = useWindowDimensions();
  const [scans, setScans] = useState<ScanRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const C = useMemo(() => ({
    primary: theme.colors.primary,
    primaryText: theme.colors.primaryText,
    bg: theme.colors.bg,
    bgSoft: theme.colors.bgSoft,
    card: theme.colors.card,
    text: theme.colors.text,
    textSec: theme.colors.textSec,
    textMuted: theme.colors.textMuted,
    border: theme.colors.border,
    success: theme.colors.success,
    warning: theme.colors.warning,
  }), [theme.colors]);

  const styles = useMemo(() => createStyles(C), [C]);
  const pad = width < 360 ? 14 : width >= 414 ? 20 : 16;

  const loadScans = async () => {
    if (!isAuthenticated) {
      setLoading(false);
      setRefreshing(false);
      return;
    }
    try {
      const response = await api.get('/scans');
      setScans(response.data.scans || []);
    } catch (error) {
      handleAppRecoverableError({
        scope: 'scan-history.load-scans',
        error,
        message: 'Error loading scans.',
        onRetry: () => { void loadScans(); },
      
        notifyMode: 'dialog',
        userInitiated: true,
      });
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => {
    loadScans();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isAuthenticated]);

  // Auto-refresh: poll every 30s for real-time data
  useEffect(() => {
    const _autoRefresh = setInterval(() => { try { loadScans(); } catch (error) { handleAppRecoverableError({ scope: 'scan-history.tsx#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); } }, 30000);
    return () => clearInterval(_autoRefresh);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  const onRefresh = () => {
    setRefreshing(true);
    loadScans();
  };

  const formatDate = (dateString: string) => {
    const date = new Date(dateString);
    return date.toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  const getSummary = (scan: ScanRecord) => {
    if (scan.summary) return scan.summary;
    if (scan.analysis && typeof scan.analysis === 'string') return scan.analysis;
    if (scan.analysis && typeof scan.analysis === 'object') {
      const entry = Object.entries(scan.analysis).find(([key, value]) => typeof value === 'string' && !['scan_type', 'scanner_title', 'error'].includes(key));
      if (entry) return entry[1] as string;
    }
    return 'Scan completed. Tap to view full details.';
  };

  const getMeta = (scanType: string) => SCAN_META[scanType] || { icon: 'scan', color: C.primary };

  if (!isAuthenticated) {
    return <Redirect href="/welcome?return_to=%2Fscan-history&auth_reason=unauthenticated" />;
  }

  return (
    <SafeAreaView style={styles.container} edges={['top']} data-testid="scan-history-screen" testID="scan-history-screen">
      <View style={styles.header} data-testid="scan-history-header" testID="scan-history-header">
        <TouchableOpacity
          style={styles.backButton}
          onPress={() => router.back()}
          data-testid="scan-history-back" testID="scan-history-back"
          dataSet={{ testid: 'scan-history-back' }}
          accessibilityLabel="scan-history-back"
          accessible={true}
          nativeID="scan-history-back"
        >
          <Ionicons name="arrow-back" size={22} color={C.text} />
        </TouchableOpacity>
        <Text style={styles.headerTitle} data-testid="scan-history-title" testID="scan-history-title">{t('scanHistory.title')}</Text>
        <View style={styles.headerSpacer} data-testid="scan-history-spacer" testID="scan-history-spacer" />
      </View>

      <View style={[styles.statsRow, { paddingHorizontal: pad }]} data-testid="scan-history-stats" testID="scan-history-stats">
        <View style={styles.statCard}>
          <Text style={styles.statValue} data-testid="scan-history-total" testID="scan-history-total">{scans.length}</Text>
          <Text style={styles.statLabel} data-testid="scan-history-total-label" testID="scan-history-total-label">Total Scans</Text>
        </View>
        <View style={styles.statDivider} />
        <View style={styles.statCard}>
          <Text style={styles.statValue} data-testid="scan-history-recent" testID="scan-history-recent">{scans.slice(0, 7).length}</Text>
          <Text style={styles.statLabel} data-testid="scan-history-recent-label" testID="scan-history-recent-label">Last 7</Text>
        </View>
      </View>

      {loading ? (
        <TableListSkeleton />
      ) : (
        <ScrollView
          showsVerticalScrollIndicator={false}
          contentContainerStyle={[styles.scrollContent, { paddingHorizontal: pad }]}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={C.primary} />}
          data-testid="scan-history-scroll" testID="scan-history-scroll"
        >
          {scans.length === 0 ? (
            <View style={styles.emptyState} data-testid="scan-history-empty" testID="scan-history-empty">
              <Ionicons name="scan" size={48} color={C.textMuted} />
              <Text style={styles.emptyTitle} data-testid="scan-history-empty-title" testID="scan-history-empty-title">{t('scanHistory.emptyTitle')}</Text>
              <Text style={styles.emptyText} data-testid="scan-history-empty-text" testID="scan-history-empty-text">{t('scanHistory.emptySubtitle')}</Text>
              <TouchableOpacity
                style={styles.startButton}
                onPress={() => router.push('/features')}
                data-testid="scan-history-start" testID="scan-history-start"
                dataSet={{ testid: 'scan-history-start' }}
                accessibilityLabel="scan-history-start"
                accessible={true}
                nativeID="scan-history-start"
              >
                <Text style={styles.startButtonText} data-testid="scan-history-start-label" testID="scan-history-start-label">{t('scanHistory.startButton')}</Text>
              </TouchableOpacity>
            </View>
          ) : (
            scans.map((scan) => {
              const meta = getMeta(scan.scan_type);
              return (
                <View key={scan.id} style={styles.scanCard} data-testid={`scan-history-card-${scan.id}`} testID={`scan-history-card-${scan.id}`}>
                  <View style={[styles.scanIcon, { backgroundColor: (globalThis as any).__alphaColor(meta.color, '15') }]}>
                    <Ionicons name={meta.icon} size={22} color={meta.color} />
                  </View>
                  <View style={styles.scanContent}>
                    <View style={styles.scanHeader}>
                      <Text style={styles.scanTitle} data-testid={`scan-history-title-${scan.id}`} testID={`scan-history-title-${scan.id}`}>{scan.scanner_title || 'AI Scan'}</Text>
                      <Text style={styles.scanDate} data-testid={`scan-history-date-${scan.id}`} testID={`scan-history-date-${scan.id}`}>{formatDate(scan.created_at)}</Text>
                    </View>
                    <Text style={styles.scanSummary} numberOfLines={3} data-testid={`scan-history-summary-${scan.id}`} testID={`scan-history-summary-${scan.id}`}>{getSummary(scan)}</Text>
                    <View style={styles.scanTags}>
                      <View style={[styles.tag, { backgroundColor: (globalThis as any).__alphaColor(meta.color, '15') }]}>
                        <Text style={[styles.tagText, { color: meta.color }]} data-testid={`scan-history-tag-${scan.id}`} testID={`scan-history-tag-${scan.id}`}>{scan.scan_type}</Text>
                      </View>
                    </View>
                  </View>
                </View>
              );
            })
          )}

          <View style={styles.footer} data-testid="scan-history-footer" testID="scan-history-footer">
            <Text style={styles.footerText} data-testid="scan-history-footer-text" testID="scan-history-footer-text">© 2026-2030 RealAICoach LLC. All rights reserved. (USA)</Text>
          </View>
        </ScrollView>
      )}
    </SafeAreaView>
  );
}
