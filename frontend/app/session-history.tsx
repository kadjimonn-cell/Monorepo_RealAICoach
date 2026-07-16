import React, { useEffect, useMemo, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  FlatList,
  TouchableOpacity,
  RefreshControl,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { Redirect, useRouter } from 'expo-router';
import { useAuth } from '../src/context/AuthContext';
import { useAppStore } from '../src/store/appStore';
import api from '../src/services/api';
import { useTheme } from '../src/context/ThemeContext';
import AppShell from '../src/components/AppShell';
import { TableListSkeleton } from '../src/components/SkeletonLoaders';
import { useTranslation } from '../src/hooks/useTranslation';
import { handleAppRecoverableError } from '../src/utils/appRecoverableError';

const staticColors = {
  success: '#10B981', // @theme-ok brand/role/state identifier
  warning: '#F59E0B', // @theme-ok brand/role/state identifier
  error: '#EF4444', // @theme-ok brand/role/state identifier
};

const categoryColors: { [key: string]: string } = {
  dating: '#EC4899', // @theme-ok brand/role/state identifier
  workplace: '#0F766E', // @theme-ok brand/role/state identifier
  friendship: '#10B981', // @theme-ok brand/role/state identifier
  family: '#F59E0B', // @theme-ok brand/role/state identifier
  networking: '#14B8A6', // @theme-ok brand/role/state identifier
  conflict: '#EF4444', // @theme-ok brand/role/state identifier
};

const CATEGORY_ICONS: { [key: string]: keyof typeof Ionicons.glyphMap } = {
  dating: 'heart',
  workplace: 'briefcase',
  friendship: 'people',
  family: 'home',
  networking: 'globe',
  conflict: 'shield-checkmark',
};

// Moved outside component to avoid TDZ issues with useCallback dependency
const SESSION_CARD_ESTIMATED_HEIGHT = 112;

interface Conversation {
  id: string;
  scenario_id: string;
  scenario_title: string;
  category: string;
  status: string;
  created_at: string;
  updated_at: string;
  overall_feedback?: {
    overall_score: number;
    summary: string;
  };
}

export default function SessionHistoryScreen() {
  const router = useRouter();
  const { user, isAuthenticated } = useAuth();
  const { userId, hasHydrated } = useAppStore();
  const { colors } = useTheme();
  const { t } = useTranslation();

  // @autofix-moved: was module-level const createStyles
  const createStyles = (COLORS: any) => StyleSheet.create({
    container: {
      flex: 1,
      backgroundColor: COLORS.background,
    },
    header: {
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'space-between',
      paddingHorizontal: 16,
      paddingVertical: 12,
      backgroundColor: COLORS.surface,
      borderBottomWidth: 1,
      borderBottomColor: COLORS.border,
    },
    backButton: {
      width: 40,
      height: 40,
      borderRadius: 20,
      backgroundColor: COLORS.backgroundSecondary,
      alignItems: 'center',
      justifyContent: 'center',
    },
    headerTitle: {
      fontSize: 18,
      fontWeight: '700',
      color: COLORS.text,
    },
    headerSpacer: {
      width: 40,
    },
    filterContainer: {
      flexDirection: 'row',
      paddingHorizontal: 16,
      paddingVertical: 12,
      backgroundColor: COLORS.surface,
      gap: 8,
    },
    filterTab: {
      flex: 1,
      paddingVertical: 10,
      borderRadius: 10,
      backgroundColor: COLORS.backgroundSecondary,
      alignItems: 'center',
    },
    filterTabActive: {
      backgroundColor: (globalThis as any).__alphaColor(COLORS.primary, '15'),
    },
    filterTabText: {
      fontSize: 13,
      fontWeight: '500',
      color: COLORS.textMuted,
    },
    filterTabTextActive: {
      color: COLORS.primary,
    },
    statsContainer: {
      flexDirection: 'row',
      marginHorizontal: 16,
      marginTop: 16,
      backgroundColor: COLORS.surface,
      borderRadius: 14,
      padding: 16,
      borderWidth: 1,
      borderColor: COLORS.border,
    },
    statItem: {
      flex: 1,
      alignItems: 'center',
    },
    statDivider: {
      width: 1,
      backgroundColor: COLORS.border,
    },
    statValue: {
      fontSize: 24,
      fontWeight: '700',
      color: COLORS.text,
    },
    statLabel: {
      fontSize: 12,
      color: COLORS.textMuted,
      marginTop: 4,
    },
    loadingContainer: {
      flex: 1,
      justifyContent: 'center',
      alignItems: 'center',
    },
    scrollContent: {
      padding: 16,
      paddingBottom: 32,
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
      backgroundColor: (globalThis as any).__alphaColor(COLORS.primary, '15'),
      alignItems: 'center',
      justifyContent: 'center',
      marginBottom: 24,
    },
    emptyTitle: {
      fontSize: 20,
      fontWeight: '700',
      color: COLORS.text,
      marginBottom: 8,
    },
    emptyText: {
      fontSize: 14,
      color: COLORS.textSecondary,
      textAlign: 'center',
      marginBottom: 24,
    },
    signInButton: {
      backgroundColor: COLORS.primary,
      paddingHorizontal: 32,
      paddingVertical: 14,
      borderRadius: 12,
    },
    signInButtonText: {
      fontSize: 16,
      fontWeight: '600',
      color: colors.primaryText,
    },
    emptyState: {
      alignItems: 'center',
      paddingVertical: 48,
    },
    emptyStateTitle: {
      fontSize: 18,
      fontWeight: '600',
      color: COLORS.text,
      marginTop: 16,
      marginBottom: 8,
    },
    emptyStateText: {
      fontSize: 14,
      color: COLORS.textMuted,
      textAlign: 'center',
      marginBottom: 24,
    },
    startButton: {
      backgroundColor: COLORS.primary,
      paddingHorizontal: 24,
      paddingVertical: 12,
      borderRadius: 10,
    },
    startButtonText: {
      fontSize: 14,
      fontWeight: '600',
      color: colors.primaryText,
    },
    sessionCard: {
      flexDirection: 'row',
      alignItems: 'center',
      backgroundColor: COLORS.surface,
      borderRadius: 14,
      padding: 14,
      marginBottom: 10,
      borderWidth: 1,
      borderColor: COLORS.border,
    },
    sessionIcon: {
      width: 48,
      height: 48,
      borderRadius: 12,
      alignItems: 'center',
      justifyContent: 'center',
    },
    sessionContent: {
      flex: 1,
      marginLeft: 12,
    },
    sessionTitle: {
      fontSize: 15,
      fontWeight: '600',
      color: COLORS.text,
      marginBottom: 4,
    },
    sessionDate: {
      fontSize: 12,
      color: COLORS.textMuted,
      marginBottom: 8,
    },
    sessionMeta: {
      flexDirection: 'row',
      gap: 8,
    },
    categoryBadge: {
      paddingHorizontal: 8,
      paddingVertical: 3,
      borderRadius: 6,
    },
    categoryBadgeText: {
      fontSize: 10,
      fontWeight: '600',
      textTransform: 'capitalize',
    },
    statusBadge: {
      paddingHorizontal: 8,
      paddingVertical: 3,
      borderRadius: 6,
    },
    statusBadgeText: {
      fontSize: 10,
      fontWeight: '600',
    },
    scoreContainer: {
      width: 44,
      height: 44,
      borderRadius: 10,
      alignItems: 'center',
      justifyContent: 'center',
      marginRight: 8,
    },
    scoreText: {
      fontSize: 16,
      fontWeight: '700',
    },
    footer: {
      alignItems: 'center',
      paddingVertical: 24,
    },
    footerText: {
      fontSize: 12,
      color: COLORS.textMuted,
    },
  });
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [filter, setFilter] = useState<'all' | 'completed' | 'in_progress'>('all');

  const tx = React.useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);

  const COLORS = useMemo(() => ({
    ...staticColors,
    primary: colors.primary,
    background: colors.bg,
    backgroundSecondary: colors.bgSoft,
    surface: colors.card,
    text: colors.text,
    textSecondary: colors.textSec,
    textMuted: colors.textMuted,
    border: colors.border,
  }), [colors]);

  // eslint-disable-next-line react-hooks/exhaustive-deps
  const styles = useMemo(() => createStyles(COLORS), [COLORS]);

  const currentUserId = user?.user_id || userId;

  const loadConversations = React.useCallback(async () => {
    if (!currentUserId) {
      setLoading(false);
      return;
    }
    try {
      // Load both practice conversations and AI sessions
      const [convRes, sessRes] = await Promise.all([
        api.get(`/conversations/${currentUserId}`),
        api.get(`/session-history/${currentUserId}`).catch(() => ({ data: { sessions: [] } })),
      ]);
      const practiceConvos = convRes.data.conversations || [];
      const aiSessions = (sessRes.data.sessions || []).filter((s: any) => s.type !== 'practice');
      
      // Merge and tag
      const merged = [
        ...practiceConvos,
        ...aiSessions.map((s: any) => ({
          ...s,
          conversation_id: s.id,
          scenario_title: s.title,
          category: s.category,
          status: s.status || 'completed',
          score: s.score,
          session_type: s.type,
        })),
      ];
      setConversations(merged);
    } catch (error) {
      console.error('Error loading conversations:', error);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [currentUserId]);

  useEffect(() => {
    loadConversations();
  }, [loadConversations]);

  // Auto-refresh: poll every 30s for real-time data
  useEffect(() => {
    const _autoRefresh = setInterval(() => { try { loadConversations(); } catch (error) { handleAppRecoverableError({ scope: 'session-history.tsx#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); } }, 30000);
    return () => clearInterval(_autoRefresh);
  }, [loadConversations]);
  const onRefresh = () => {
    setRefreshing(true);
    loadConversations();
  };

  const filteredConversations = conversations.filter((conv) => {
    if (filter === 'all') return true;
    if (filter === 'completed') return conv.status === 'completed';
    if (filter === 'in_progress') return conv.status === 'active' || conv.status === 'in_progress';
    return true;
  });

  const getScoreColor = (score: number) => {
    if (score >= 80) return COLORS.success;
    if (score >= 60) return COLORS.warning;
    return COLORS.error;
  };

  const formatDate = (dateString?: string) => {
    if (!dateString) return tx('sessionHistory.dateFallback', '—');
    const normalized = dateString.replace(/\.(\d{3})\d+/, '.$1');
    const date = new Date(normalized);
    if (Number.isNaN(date.getTime())) return tx('sessionHistory.dateFallback', '—');
    return date.toLocaleDateString(undefined, {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  const resolveDate = (primary?: string, fallback?: string) => {
    if (primary) {
      const primaryDate = new Date(primary);
      if (!Number.isNaN(primaryDate.getTime())) {
        return primary;
      }
    }
    return fallback;
  };

  const renderConversationItem = React.useCallback(({ item: conversation }: { item: Conversation }) => {
    const categoryColor = categoryColors[conversation.category] || COLORS.primary;
    const categoryIcon = CATEGORY_ICONS[conversation.category] || 'chatbubbles';
    const categoryLabel = tx(`practice.categories.${conversation.category || ''}`, conversation.category);
    const isCompleted = conversation.status === 'completed';

    return (
      <TouchableOpacity
        key={conversation.id}
        style={styles.sessionCard}
        onPress={() => router.push(`/conversation/${conversation.id}`)}
        data-testid={`session-history-card-${conversation.id}`} testID={`session-history-card-${conversation.id}`}
        accessibilityRole="button"
      >
        <View style={[styles.sessionIcon, { backgroundColor: (globalThis as any).__alphaColor(categoryColor, '15') }]}>
          <Ionicons name={categoryIcon} size={22} color={categoryColor} />
        </View>

        <View style={styles.sessionContent}>
          <Text style={styles.sessionTitle}>{conversation.scenario_title}</Text>
          <Text style={styles.sessionDate}>{formatDate(resolveDate(conversation.updated_at, conversation.created_at))}</Text>

          <View style={styles.sessionMeta}>
            <View style={[styles.categoryBadge, { backgroundColor: (globalThis as any).__alphaColor(categoryColor, '15') }]}>
              <Text style={[styles.categoryBadgeText, { color: categoryColor }]}>
                {categoryLabel}
              </Text>
            </View>

            <View style={[
              styles.statusBadge,
              { backgroundColor: conversation.status === 'completed' ? (globalThis as any).__alphaColor(COLORS.success, '15') : COLORS.warning + '15' }
            ]}>
              <Text style={[
                styles.statusBadgeText,
                { color: isCompleted ? COLORS.success : COLORS.warning }
              ]}>
                {isCompleted
                  ? tx('sessionHistory.status.completed', 'Completed')
                  : tx('sessionHistory.status.inProgress', 'In Progress')}
              </Text>
            </View>
          </View>
        </View>

        {conversation.overall_feedback && (
          <View style={[
            styles.scoreContainer,
            { backgroundColor: (globalThis as any).__alphaColor(getScoreColor(conversation.overall_feedback.overall_score), '15') }
          ]}>
            <Text style={[
              styles.scoreText,
              { color: getScoreColor(conversation.overall_feedback.overall_score) }
            ]}>
              {conversation.overall_feedback.overall_score}
            </Text>
          </View>
        )}

        <Ionicons name="chevron-forward" size={18} color={COLORS.textMuted} />
      </TouchableOpacity>
    );
  }, [COLORS.primary, COLORS.success, COLORS.textMuted, COLORS.warning, formatDate, getScoreColor, resolveDate, router, styles.categoryBadge, styles.categoryBadgeText, styles.scoreContainer, styles.scoreText, styles.sessionCard, styles.sessionContent, styles.sessionDate, styles.sessionIcon, styles.sessionMeta, styles.sessionTitle, styles.statusBadge, styles.statusBadgeText, tx]);

  const renderEmptyState = React.useCallback(() => (
    <View style={styles.emptyState}>
      <Ionicons name="chatbubbles-outline" size={48} color={COLORS.textMuted} />
      <Text style={styles.emptyStateTitle}>{tx('sessionHistory.empty.title', 'No sessions yet')}</Text>
      <Text style={styles.emptyStateText}>
        {tx('sessionHistory.empty.subtitle', 'Start practicing to see your session history here.')}
      </Text>
      <TouchableOpacity
        style={styles.startButton}
        onPress={() => router.push('/practice')}
        data-testid="session-history-start-practice"
        testID="session-history-start-practice"
        accessibilityRole="button"
      >
        <Text style={styles.startButtonText}>{tx('sessionHistory.empty.start', 'Start Practicing')}</Text>
      </TouchableOpacity>
    </View>
  ), [COLORS.textMuted, router, styles.emptyState, styles.emptyStateText, styles.emptyStateTitle, styles.startButton, styles.startButtonText, tx]);

  const getSessionItemLayout = React.useCallback((_: ArrayLike<Conversation> | null | undefined, index: number) => ({
    length: SESSION_CARD_ESTIMATED_HEIGHT,
    offset: SESSION_CARD_ESTIMATED_HEIGHT * index,
    index,
  }), []);

  if (!hasHydrated || loading) {
    return (
      <AppShell>
        <SafeAreaView style={styles.container} edges={['top']}>
          <TableListSkeleton />
        </SafeAreaView>
      </AppShell>
    );
  }

  if (!isAuthenticated && !userId) {
    return <Redirect href="/welcome?return_to=%2Fsession-history&auth_reason=unauthenticated" />;
  }

  return (
    <AppShell>
      <SafeAreaView style={styles.container} edges={['top']}>
      {/* Header */}
      <View style={styles.header}>
        <TouchableOpacity
          style={styles.backButton}
          onPress={() => router.back()}
          data-testid="session-history-back-auth"
          testID="session-history-back-auth"
          accessibilityRole="button"
        >
          <Ionicons name="arrow-back" size={24} color={COLORS.text} />
        </TouchableOpacity>
        <Text style={styles.headerTitle} data-testid="session-history-title-auth" testID="session-history-title-auth">{tx('sessionHistory.title', 'Session History')}</Text>
        <View style={styles.headerSpacer} />
      </View>

      {/* Filter Tabs */}
      <View style={styles.filterContainer}>
        {[
          { id: 'all', label: tx('sessionHistory.filters.all', 'All Sessions') },
          { id: 'completed', label: tx('sessionHistory.filters.completed', 'Completed') },
          { id: 'in_progress', label: tx('sessionHistory.filters.inProgress', 'In Progress') },
        ].map((tab) => (
          <TouchableOpacity
            key={tab.id}
            style={[styles.filterTab, filter === tab.id && styles.filterTabActive]}
            onPress={() => setFilter(tab.id as any)}
            data-testid={`session-history-filter-${tab.id}`}
            testID={`session-history-filter-${tab.id}`}
            accessibilityRole="button"
          >
            <Text style={[styles.filterTabText, filter === tab.id && styles.filterTabTextActive]}>
              {tab.label}
            </Text>
          </TouchableOpacity>
        ))}
      </View>

      {/* Stats Summary */}
      <View style={styles.statsContainer}>
        <View style={styles.statItem}>
          <Text style={styles.statValue}>{conversations.length}</Text>
          <Text style={styles.statLabel}>{tx('sessionHistory.stats.total', 'Total')}</Text>
        </View>
        <View style={styles.statDivider} />
        <View style={styles.statItem}>
          <Text style={styles.statValue}>
            {conversations.filter((c) => c.status === 'completed').length}
          </Text>
          <Text style={styles.statLabel}>{tx('sessionHistory.stats.completed', 'Completed')}</Text>
        </View>
        <View style={styles.statDivider} />
        <View style={styles.statItem}>
          <Text style={styles.statValue}>
            {conversations.filter((c) => c.status !== 'completed').length}
          </Text>
          <Text style={styles.statLabel}>{tx('sessionHistory.stats.inProgress', 'In Progress')}</Text>
        </View>
      </View>

      {loading ? (
        <TableListSkeleton />
      ) : (
        <FlatList
          data={filteredConversations}
          keyExtractor={(conversation) => conversation.id}
          renderItem={renderConversationItem}
          getItemLayout={getSessionItemLayout}
          initialNumToRender={8}
          maxToRenderPerBatch={8}
          windowSize={6}
          removeClippedSubviews
          showsVerticalScrollIndicator={false}
          contentContainerStyle={[styles.scrollContent, filteredConversations.length === 0 ? { flexGrow: 1, justifyContent: 'center' as const } : null]}
          refreshControl={
            <RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={COLORS.primary} />
          }
          ListEmptyComponent={renderEmptyState}
          ListFooterComponent={
            <View style={styles.footer}>
              <Text style={styles.footerText}>{tx('sessionHistory.footer', '© 2026-2030 RealAICoach LLC. All rights reserved. (USA)')}</Text>
            </View>
          }
        />
      )}
    </SafeAreaView>
  </AppShell>
  );
}
