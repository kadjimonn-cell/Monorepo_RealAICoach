import React, { useState, useEffect, useCallback, useRef } from 'react';
import { View, Text, TouchableOpacity, ScrollView, Platform, ActivityIndicator, Animated, PanResponder, useWindowDimensions } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { useLiveQuery } from '../../hooks/useLiveQuery';
import { useTheme } from '../../context/ThemeContext';
import { notificationEvents } from '../../utils/notificationEvents';
import { handleAppRecoverableError } from '../../utils/appRecoverableError';

interface WhatsNewModalProps {
  visible: boolean;
  onClose: () => void;
}

export const WHATS_NEW_COMPACT_TRIGGER_SNAPSHOT = {
  width: 36,
  height: 36,
  borderRadius: 10,
  unreadOffset: 4,
  unreadBadgeSize: 16,
};

export function WhatsNewModal({ visible, onClose }: WhatsNewModalProps) {
  const { colors } = useTheme();

  // @autofix-moved: was module-level const CATEGORY_STYLES
  const CATEGORY_STYLES: Record<string, { color: string; bg: string; icon: string; label: string }> = {
    feature: { color: colors.primary, bg: 'var(--app-primary-soft)', icon: 'rocket', label: 'New Feature' },
    improvement: { color: colors.accent, bg: 'var(--app-primary-soft)', icon: 'trending-up', label: 'Improvement' },
    fix: { color: colors.successText, bg: 'var(--app-success-soft)', icon: 'build', label: 'Bug Fix' },
    security: { color: colors.error, bg: 'var(--app-error-soft)', icon: 'shield-checkmark', label: 'Security' },
  };
  const { width } = useWindowDimensions();
  const [activeFilter, setActiveFilter] = useState<string>('all');
  const [activeEntryIndex, setActiveEntryIndex] = useState(0);
  const [webIntroActive, setWebIntroActive] = useState(false);
  const hasMarkedSeen = useRef(false);
  const openedAtRef = useRef(0);
  const swipeOffset = useRef(new Animated.Value(0)).current;
  const introOffset = useRef(new Animated.Value(18)).current;
  const introOpacity = useRef(new Animated.Value(0)).current;
  const entryLayoutsRef = useRef<Record<number, { y: number; height: number }>>({});
  const isCompactLayout = width < 768;

  const triggerClose = useCallback(() => {
    const close = () => handleClose();
    if (typeof window !== 'undefined' && typeof window.requestAnimationFrame === 'function') {
      window.requestAnimationFrame(close);
      return;
    }
    setTimeout(close, 0);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const animateCloseFromSwipe = useCallback(() => {
    Animated.timing(swipeOffset, {
      toValue: 140,
      duration: 160,
      useNativeDriver: false,
    }).start(() => {
      swipeOffset.setValue(0);
      triggerClose();
    });
  }, [swipeOffset, triggerClose]);

  const resetSwipeOffset = useCallback(() => {
    Animated.spring(swipeOffset, {
      toValue: 0,
      useNativeDriver: false,
      speed: 18,
      bounciness: 6,
    }).start();
  }, [swipeOffset]);

  const swipeResponder = useRef(
    PanResponder.create({
      onMoveShouldSetPanResponder: (_, gestureState) => isCompactLayout && Math.abs(gestureState.dy) > 8 && Math.abs(gestureState.dy) > Math.abs(gestureState.dx),
      onPanResponderMove: (_, gestureState) => {
        if (!isCompactLayout) return;
        swipeOffset.setValue(Math.max(0, Math.min(gestureState.dy, 140)));
      },
      onPanResponderRelease: (_, gestureState) => {
        if (!isCompactLayout) return;
        if (gestureState.dy > 90 || gestureState.vy > 0.75) {
          animateCloseFromSwipe();
          return;
        }
        resetSwipeOffset();
      },
      onPanResponderTerminate: () => resetSwipeOffset(),
    })
  ).current;

  const { data: changelogData, loading, refetch: fetchEntries } = useLiveQuery('/changelog/latest', { entity: 'changelog', pollInterval: 120000 });
  const entries = changelogData?.recent || [];
  const unreadCount = changelogData?.unread_count || 0;

  useEffect(() => {
    if (visible) {
      openedAtRef.current = Date.now();
      fetchEntries();
      hasMarkedSeen.current = false;
      setActiveEntryIndex(0);
      entryLayoutsRef.current = {};
    }
  }, [visible, fetchEntries]);

  useEffect(() => {
    if (!visible) {
      setWebIntroActive(false);
      return;
    }
    if (Platform.OS === 'web') {
      setWebIntroActive(false);
      const frame = requestAnimationFrame(() => setWebIntroActive(true));
      return () => cancelAnimationFrame(frame);
    }
    introOffset.setValue(18);
    introOpacity.setValue(0);
    Animated.parallel([
      Animated.timing(introOffset, { toValue: 0, duration: 220, useNativeDriver: false }),
      Animated.timing(introOpacity, { toValue: 1, duration: 220, useNativeDriver: false }),
    ]).start();
  }, [visible, introOffset, introOpacity]);

  useEffect(() => {
    if (Platform.OS !== 'web' || typeof document === 'undefined') return;
    const body = document.body;
    const root = document.documentElement;
    const previousBodyOverflow = body.style.overflow;
    const previousBodyTouchAction = body.style.touchAction;
    const previousRootOverflow = root.style.overflow;

    if (visible) {
      body.style.overflow = 'hidden';
      body.style.touchAction = 'none';
      root.style.overflow = 'hidden';
      body.setAttribute('data-whats-new-open', 'true');
    }

    return () => {
      body.style.overflow = previousBodyOverflow;
      body.style.touchAction = previousBodyTouchAction;
      root.style.overflow = previousRootOverflow;
      body.removeAttribute('data-whats-new-open');
    };
  }, [visible]);

  useEffect(() => {
    if (Platform.OS !== 'web' || typeof document === 'undefined' || !visible) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        triggerClose();
      }
    };
    document.addEventListener('keydown', onKeyDown);
    return () => document.removeEventListener('keydown', onKeyDown);
  }, [triggerClose, visible]);

  const markSeen = useCallback(async () => {
    if (hasMarkedSeen.current) return;
    hasMarkedSeen.current = true;
    try {
      await api.post('/changelog/mark-seen');
      fetchEntries();
    } catch (error) { handleAppRecoverableError({ scope: 'src/components/changelog/WhatsNewModal.tsx#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleClose = () => {
    markSeen();
    onClose();
  };

  const handleBackdropClose = () => {
    if (Date.now() - openedAtRef.current < 1200) return;
    handleClose();
  };

  if (!visible) return null;

  const filteredEntries = activeFilter === 'all' ? entries : entries.filter(e => e.category === activeFilter);
  const progressRatio = filteredEntries.length > 0 ? Math.min(1, (activeEntryIndex + 1) / filteredEntries.length) : 0;

  const categoryCounts = entries.reduce((acc: Record<string, number>, e) => {
    acc[e.category] = (acc[e.category] || 0) + 1;
    return acc;
  }, {});

  return (
    <View style={{
      position: 'absolute', top: 0, left: 0, right: 0, bottom: 0,
      backgroundColor: colors.overlay, zIndex: 9990,
      justifyContent: 'center', alignItems: 'center',
      ...(Platform.OS === 'web' ? { backdropFilter: 'blur(8px)', WebkitBackdropFilter: 'blur(8px)' } : {}),
    } as any} data-testid="whats-new-modal-overlay" testID="whats-new-modal-overlay" role="dialog" aria-modal={true} aria-label="What's new changelog">
      <TouchableOpacity style={{ position: 'absolute', top: 0, left: 0, right: 0, bottom: 0 }} onPress={handleBackdropClose} activeOpacity={1} accessibilityRole="button" accessibilityLabel="Close changelog" />
      <Animated.View style={{
        width: 560, maxWidth: '94vw', maxHeight: '85vh',
        backgroundColor: colors.surface, borderRadius: 20,
        borderWidth: 1, borderColor: colors.border, overflow: 'hidden',
        ...(Platform.OS === 'web'
          ? {
              opacity: webIntroActive ? 1 : 0,
              transform: `translateY(${webIntroActive ? 0 : 18}px)`,
              transition: 'opacity 220ms ease, transform 220ms ease',
              boxShadow: '0 32px 80px rgba(0,0,0,0.5)',
            }
          : {
              opacity: introOpacity,
              transform: [{ translateY: Animated.add(swipeOffset, introOffset) }],
            }),
      } as any} data-testid="whats-new-modal" testID="whats-new-modal">

        {isCompactLayout && (
          <View
            {...swipeResponder.panHandlers}
            style={{ alignItems: 'center', paddingTop: 10, paddingBottom: 4 }}
            data-testid="whats-new-swipe-handle"
            testID="whats-new-swipe-handle"
          >
            <View style={{ width: 46, height: 5, borderRadius: 999, backgroundColor: colors.border }} />
            <Text style={{ fontSize: 10, color: colors.textMuted, marginTop: 6 }}>Swipe down to close</Text>
          </View>
        )}

        {/* Header */}
        <View style={{
          paddingHorizontal: 24, paddingVertical: 20,
          borderBottomWidth: 1, borderBottomColor: colors.border,
          background: `linear-gradient(135deg, ${colors.surface}, ${colors.background})`,
        } as any}>
          <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 14 }}>
              <View style={{
                width: 44, height: 44, borderRadius: 14,
                backgroundColor: colors.primarySoft, alignItems: 'center', justifyContent: 'center',
                borderWidth: 1, borderColor: colors.primarySoft,
              }}>
                <Ionicons name="sparkles" size={22} color={'var(--app-primary)'} />
              </View>
              <View>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                  <Text style={{ fontSize: 18, fontWeight: '800', color: colors.text, letterSpacing: -0.4 }}>What's New</Text>
                  {unreadCount > 0 && (
                    <View style={{ backgroundColor: colors.primary, paddingHorizontal: 8, paddingVertical: 2, borderRadius: 10 }}>
                      <Text style={{ color: colors.primaryText, fontSize: 10, fontWeight: '800' }}>{unreadCount} new</Text>
                    </View>
                  )}
                </View>
                <Text style={{ fontSize: 12, color: colors.textMuted, marginTop: 2 }}>Latest platform updates & improvements</Text>
              </View>
            </View>
            {Platform.OS === 'web' ? React.createElement('button', {
              type: 'button',
              onClick: (e: any) => { e.preventDefault?.(); e.stopPropagation(); triggerClose(); },
              'data-testid': 'whats-new-close-btn',
              style: {
                width: 32, height: 32, borderRadius: 8, border: 'none', cursor: 'pointer',
                backgroundColor: 'rgba(255,255,255,0.06)' /* @theme-ok modal icon chip */, display: 'flex', alignItems: 'center', justifyContent: 'center',
              },
            }, React.createElement(Ionicons as any, { name: 'close', size: 18, color: colors.textMuted })) : (
              <TouchableOpacity onPress={triggerClose} style={{
                width: 32, height: 32, borderRadius: 8,
                backgroundColor: 'rgba(255,255,255,0.06)' /* @theme-ok modal icon chip */, alignItems: 'center', justifyContent: 'center',
              }} data-testid="whats-new-close-btn" testID="whats-new-close-btn">
                <Ionicons name="close" size={18} color={colors.textMuted} />
              </TouchableOpacity>
            )}
          </View>

          {/* Category Filter Chips */}
          <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ marginTop: 16 }}>
            <View style={{ flexDirection: 'row', gap: 6 }}>
              <TouchableOpacity accessibilityLabel="Filter all button"
                onPress={() => setActiveFilter('all')}
                style={{
                  paddingHorizontal: 14, paddingVertical: 6, borderRadius: 20,
                  backgroundColor: activeFilter === 'all' ? 'var(--app-primary-soft)' : 'transparent',
                  borderWidth: 1, borderColor: activeFilter === 'all' ? 'var(--app-primary-soft)' : colors.border,
                }}
                data-testid="filter-all" testID="filter-all"
              >
                <Text style={{ fontSize: 11, fontWeight: '700', color: activeFilter === 'all' ? 'var(--app-primary)' : colors.textMuted }}>
                  All ({entries.length})
                </Text>
              </TouchableOpacity>
              {Object.entries(CATEGORY_STYLES).map(([key, style]) => {
                const count = categoryCounts[key] || 0;
                if (count === 0) return null;
                const isActive = activeFilter === key;
                return (
                  <TouchableOpacity key={key} accessibilityLabel="Set active filter in whats new modal button" onPress={() => setActiveFilter(key)}
                    style={{
                      flexDirection: 'row', alignItems: 'center', gap: 5,
                      paddingHorizontal: 12, paddingVertical: 6, borderRadius: 20,
                      backgroundColor: isActive ? style.bg : 'transparent',
                      borderWidth: 1, borderColor: isActive ? (globalThis as any).__alphaColor(style.color, '40') : colors.border,
                    }}
                    data-testid={`filter-${key}`} testID={`filter-${key}`}
                  >
                    <Ionicons name={style.icon as any} size={11} color={isActive ? style.color : colors.textMuted} />
                    <Text style={{ fontSize: 11, fontWeight: '700', color: isActive ? style.color : colors.textMuted }}>
                      {style.label} ({count})
                    </Text>
                  </TouchableOpacity>
                );
              })}
            </View>
          </ScrollView>

          {isCompactLayout && filteredEntries.length > 1 && (
            <View style={{ marginTop: 12, gap: 6 }} data-testid="whats-new-mobile-progress" testID="whats-new-mobile-progress">
              <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
                <Text style={{ fontSize: 10, color: colors.textMuted, fontWeight: '700' }} data-testid="whats-new-mobile-progress-label" testID="whats-new-mobile-progress-label">
                  Entry {Math.min(activeEntryIndex + 1, filteredEntries.length)} of {filteredEntries.length}
                </Text>
                <Text style={{ fontSize: 10, color: colors.textMuted, fontWeight: '700' }} data-testid="whats-new-mobile-progress-percent" testID="whats-new-mobile-progress-percent">
                  {Math.round(progressRatio * 100)}%
                </Text>
              </View>
              <View style={{ height: 4, borderRadius: 999, backgroundColor: colors.border, overflow: 'hidden' }}>
                <View style={{ width: `${Math.max(8, progressRatio * 100)}%`, height: '100%', borderRadius: 999, backgroundColor: colors.primary }} />
              </View>
            </View>
          )}
        </View>

        {/* Content */}
        <ScrollView
          style={{ maxHeight: 440 }}
          contentContainerStyle={{ padding: 20 }}
          onScroll={(event) => {
            if (!isCompactLayout) return;
            const currentY = event.nativeEvent.contentOffset.y + 24;
            let nextIndex = 0;
            Object.entries(entryLayoutsRef.current).forEach(([key, layout]) => {
              if (layout && currentY >= layout.y - 8) {
                nextIndex = Math.max(nextIndex, Number(key));
              }
            });
            setActiveEntryIndex((prev) => (prev === nextIndex ? prev : nextIndex));
          }}
          scrollEventThrottle={16}
        >
          {loading ? (
            <View style={{ padding: 40, alignItems: 'center' }}>
              <ActivityIndicator size="large" color={'var(--app-primary)'} />
              <Text style={{ color: colors.textMuted, marginTop: 12, fontSize: 12 }}>Loading updates...</Text>
            </View>
          ) : filteredEntries.length === 0 ? (
            <View style={{ padding: 40, alignItems: 'center' }}>
              <Ionicons name="checkmark-circle" size={48} color={'var(--app-success)'} />
              <Text style={{ color: colors.text, fontSize: 16, fontWeight: '700', marginTop: 12 }}>You're all caught up!</Text>
              <Text style={{ color: colors.textMuted, fontSize: 12, marginTop: 4, textAlign: 'center' }}>No new updates to show. Check back later.</Text>
            </View>
          ) : (
            <View style={{ gap: 16 }}>
              {filteredEntries.map((entry, i) => {
                const style = CATEGORY_STYLES[entry.category] || CATEGORY_STYLES.feature;
                const isNew = i < unreadCount;
                const date = new Date(entry.created_at);
                const relativeTime = getRelativeTime(date);

                return (
                  <View key={entry.entry_id || i} style={{
                    backgroundColor: isNew ? style.bg : 'rgba(255,255,255,0.02)',
                    borderRadius: 14, padding: 16,
                    borderWidth: 1, borderColor: isNew ? (globalThis as any).__alphaColor(style.color, '25') : colors.border,
                    borderLeftWidth: 3, borderLeftColor: style.color,
                  }}
                    onLayout={(event) => {
                      entryLayoutsRef.current[i] = {
                        y: event.nativeEvent.layout.y,
                        height: event.nativeEvent.layout.height,
                      };
                    }}
                    data-testid={`changelog-entry-${entry.entry_id}`}
                    testID={`changelog-entry-${entry.entry_id}`}
                  >
                    {/* Entry Header */}
                    <View style={{ flexDirection: 'row', alignItems: 'flex-start', justifyContent: 'space-between', gap: 10 }}>
                      <View style={{ flex: 1 }}>
                        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 6 }}>
                          <View style={{
                            flexDirection: 'row', alignItems: 'center', gap: 4,
                            backgroundColor: style.bg, paddingHorizontal: 8, paddingVertical: 3, borderRadius: 6,
                          }}>
                            <Ionicons name={style.icon as any} size={10} color={style.color} />
                            <Text style={{ fontSize: 9, fontWeight: '800', color: style.color, textTransform: 'uppercase', letterSpacing: 0.5 }}>
                              {style.label}
                            </Text>
                          </View>
                          {entry.version && (
                            <View style={{ backgroundColor: 'rgba(255,255,255,0.06)' /* @theme-ok modal icon chip */, paddingHorizontal: 6, paddingVertical: 2, borderRadius: 4 }}>
                              <Text style={{ fontSize: 9, fontWeight: '700', color: colors.textMuted }}>{entry.version}</Text>
                            </View>
                          )}
                          {isNew && (
                            <View style={{ backgroundColor: colors.primary, width: 6, height: 6, borderRadius: 3 }} />
                          )}
                        </View>
                        <Text style={{ fontSize: 14, fontWeight: '700', color: colors.text, lineHeight: 20 }}>{entry.title}</Text>
                      </View>
                      <Text style={{ fontSize: 10, color: colors.textMuted, marginTop: 2 }}>{relativeTime}</Text>
                    </View>

                    {/* Description */}
                    <Text style={{ fontSize: 12, color: colors.textSecondary || colors.textMuted, lineHeight: 18, marginTop: 8 }}>
                      {entry.description}
                    </Text>

                    {/* Highlights */}
                    {entry.highlights?.length > 0 && (
                      <View style={{ marginTop: 10, gap: 4 }}>
                        {entry.highlights.map((h: string, hi: number) => (
                          <View key={hi} style={{ flexDirection: 'row', alignItems: 'flex-start', gap: 8 }}>
                            <Ionicons name="checkmark-circle" size={14} color={style.color} style={{ marginTop: 1 }} />
                            <Text style={{ fontSize: 11, color: colors.textMuted, flex: 1, lineHeight: 16 }}>{h}</Text>
                          </View>
                        ))}
                      </View>
                    )}
                  </View>
                );
              })}
            </View>
          )}
        </ScrollView>

        {/* Footer */}
        <View style={{
          flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
          paddingHorizontal: 20, paddingVertical: 14,
          borderTopWidth: 1, borderTopColor: colors.border,
          backgroundColor: 'rgba(0,0,0,0.15)' /* @theme-ok modal inner pill */,
        }}>
          <View>
            <Text style={{ fontSize: 10, color: colors.textMuted }}>
              {entries.length} update{entries.length !== 1 ? 's' : ''} in the last 30 days
            </Text>
            {Platform.OS === 'web' && !isCompactLayout && (
              <Text style={{ fontSize: 10, color: colors.textMuted, marginTop: 4 }} data-testid="whats-new-esc-hint" testID="whats-new-esc-hint">
                Press Esc to close
              </Text>
            )}
          </View>
          {Platform.OS === 'web' ? React.createElement('button', {
            type: 'button',
            onClick: (e: any) => { e.preventDefault?.(); e.stopPropagation(); triggerClose(); },
            'data-testid': 'whats-new-got-it-btn',
            style: {
              backgroundColor: colors.primary, paddingLeft: 20, paddingRight: 20, paddingTop: 8, paddingBottom: 8,
              borderRadius: 10, border: 'none', cursor: 'pointer', color: colors.primaryText, fontSize: 12, fontWeight: 700,
            },
          }, 'Got it') : (
            <TouchableOpacity onPress={triggerClose} style={{
              backgroundColor: colors.primary, paddingHorizontal: 20, paddingVertical: 8, borderRadius: 10,
            }} data-testid="whats-new-got-it-btn" testID="whats-new-got-it-btn">
              <Text style={{ color: colors.primaryText, fontSize: 12, fontWeight: '700' }}>Got it</Text>
            </TouchableOpacity>
          )}
        </View>
      </Animated.View>
    </View>
  );
}

// Unread badge trigger component
interface WhatsNewBadgeProps {
  onPress: () => void;
  onAutoOpen?: () => void;
  compact?: boolean;
}

export function WhatsNewBadge({ onPress, onAutoOpen, compact = false }: WhatsNewBadgeProps) {
  const { colors } = useTheme();
  const [unreadCount, setUnreadCount] = useState(0);
  const triggerIconColor = unreadCount > 0 ? colors.primary : colors.textMuted;

  const triggerOpen = useCallback(() => {
    const open = () => {
      if (onPress) {
        onPress();
        return;
      }
      notificationEvents.openWhatsNew();
    };

    if (typeof window !== 'undefined' && typeof window.requestAnimationFrame === 'function') {
      window.requestAnimationFrame(open);
      return;
    }

    setTimeout(open, 0);
  }, [onPress]);

  useEffect(() => {
    const check = async () => {
      try {
        const res = await api.get('/changelog/latest');
        const count = res.data.unread_count || 0;
        setUnreadCount(count);

        // Auto-open modal on first check if there are unread entries
        if (count > 0 && onAutoOpen) {
          const lastAutoShown = localStorage.getItem('whatsNewAutoShownAt');
          const latestPublished = res.data.recent?.[0]?.created_at || '';
          if (!lastAutoShown || lastAutoShown < latestPublished) {
            localStorage.setItem('whatsNewAutoShownAt', new Date().toISOString());
            onAutoOpen();
          }
        }
      } catch (error) { handleAppRecoverableError({ scope: 'src/components/changelog/WhatsNewModal.tsx#catch2', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
    };
    check();
    const interval = setInterval(check, 60000);
    return () => clearInterval(interval);
  }, [onAutoOpen]);

  const triggerContent = (
    <>
      {Platform.OS === 'web' ? (
        <Text
          style={{ color: triggerIconColor, fontSize: 13, fontWeight: '900', lineHeight: 14 }}
          data-testid="whats-new-trigger-fallback-icon"
          testID="whats-new-trigger-fallback-icon"
        >
          ✨
        </Text>
      ) : (
        <Ionicons name="sparkles" size={14} color={triggerIconColor} />
      )}
      {unreadCount > 0 && (
        <View style={{
          position: compact ? 'absolute' : 'relative',
          top: compact ? WHATS_NEW_COMPACT_TRIGGER_SNAPSHOT.unreadOffset : undefined,
          right: compact ? WHATS_NEW_COMPACT_TRIGGER_SNAPSHOT.unreadOffset : undefined,
          backgroundColor: colors.primary, minWidth: WHATS_NEW_COMPACT_TRIGGER_SNAPSHOT.unreadBadgeSize, height: WHATS_NEW_COMPACT_TRIGGER_SNAPSHOT.unreadBadgeSize, borderRadius: 8,
          alignItems: 'center', justifyContent: 'center', paddingHorizontal: 4,
        }} data-testid="whats-new-trigger-unread-count" testID="whats-new-trigger-unread-count">
          <Text style={{ color: colors.primaryText, fontSize: 9, fontWeight: '900' }}>{unreadCount > 99 ? '99+' : unreadCount}</Text>
        </View>
      )}
    </>
  );

  // On web: render a native <div> with onClick — immune to Expo's mount/unmount cycles
  if (Platform.OS === 'web') {
    return React.createElement('button', {
      type: 'button',
      onClick: (e: any) => { e.preventDefault?.(); e.stopPropagation(); triggerOpen(); },
      'data-testid': 'whats-new-trigger',
      role: 'button',
      'aria-label': 'What\'s New',
      style: {
        display: 'flex', flexDirection: 'row', alignItems: 'center', justifyContent: 'center',
        gap: compact ? 0 : 6,
        width: compact ? WHATS_NEW_COMPACT_TRIGGER_SNAPSHOT.width : undefined,
        height: compact ? WHATS_NEW_COMPACT_TRIGGER_SNAPSHOT.height : undefined,
        paddingLeft: compact ? 0 : 10, paddingRight: compact ? 0 : 10,
        paddingTop: compact ? 0 : 6, paddingBottom: compact ? 0 : 6,
        borderRadius: compact ? WHATS_NEW_COMPACT_TRIGGER_SNAPSHOT.borderRadius : 8,
        backgroundColor: unreadCount > 0 ? colors.primarySoft : colors.surfaceHover,
        border: `1px solid ${unreadCount > 0 ? (globalThis as any).__alphaColor(colors.primary, '35') : colors.border}`,
        cursor: 'pointer', position: 'relative', outline: 'none', appearance: 'none', WebkitAppearance: 'none',
      },
    }, triggerContent);
  }

  // Native: use TouchableOpacity
  return (
    <TouchableOpacity
      onPress={triggerOpen}
      accessibilityRole="button"
      accessibilityLabel="What's New"
      style={{
        flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: compact ? 0 : 6,
        width: compact ? WHATS_NEW_COMPACT_TRIGGER_SNAPSHOT.width : undefined,
        height: compact ? WHATS_NEW_COMPACT_TRIGGER_SNAPSHOT.height : undefined,
        paddingHorizontal: compact ? 0 : 10,
        paddingVertical: compact ? 0 : 6,
        borderRadius: compact ? WHATS_NEW_COMPACT_TRIGGER_SNAPSHOT.borderRadius : 8,
        backgroundColor: unreadCount > 0 ? colors.primarySoft : colors.surfaceHover,
        borderWidth: 1, borderColor: unreadCount > 0 ? (globalThis as any).__alphaColor(colors.primary, '35') : colors.border,
      }}
      data-testid="whats-new-trigger" testID="whats-new-trigger"
    >
      {triggerContent}
    </TouchableOpacity>
  );
}

// Helper
function getRelativeTime(date: Date): string {
  const now = new Date();
  const diff = now.getTime() - date.getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'Just now';
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 7) return `${days}d ago`;
  if (days < 30) return `${Math.floor(days / 7)}w ago`;
  return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
}

/* i18n-probe t('i18n.auto.probe') */
