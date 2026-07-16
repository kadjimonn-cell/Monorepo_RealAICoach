import React, { useMemo } from 'react';
import { ActivityIndicator, Modal, ScrollView, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useTheme } from '../../context/ThemeContext';
import { useTranslation } from '../../hooks/useTranslation';

interface FeatureLifecycleDrawerProps {
  visible: boolean;
  onClose: () => void;
  audit: any;
  loading: boolean;
  error: string;
  width: number;
  fallbackActiveCount: number;
}

export const FeatureLifecycleDrawer = ({
  visible,
  onClose,
  audit,
  loading,
  error,
  width,
  fallbackActiveCount,
}: FeatureLifecycleDrawerProps) => {
  const { colors } = useTheme();
  const { t } = useTranslation();
  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };
  const C = useMemo(
    () => ({
      card: colors.card,
      bgSoft: colors.bgSoft,
      text: colors.text,
      textMuted: colors.textMuted,
      textSec: colors.textSec,
      border: colors.border,
      primary: colors.primary,
      error: colors.error,
    }),
    [colors],
  );
  const styles = useMemo(() => createStyles(C), [C]);
  const retiredFeatures = Array.isArray(audit?.retired_features) ? audit.retired_features : [];
  const auditEvents = Array.isArray(audit?.audit_events) ? audit.audit_events : [];

  return (
    <Modal visible={visible} transparent animationType="none" onRequestClose={onClose}>
      <View style={styles.overlay} data-testid="features-lifecycle-overlay" testID="features-lifecycle-overlay">
        <TouchableOpacity style={styles.scrim} onPress={onClose} data-testid="features-lifecycle-scrim" testID="features-lifecycle-scrim" />
        <View
          style={[styles.drawer, { width: width >= 860 ? 520 : '94%', maxHeight: width >= 620 ? '88%' : '92%' }]}
          data-testid="features-lifecycle-drawer"
          testID="features-lifecycle-drawer"
        >
          <View style={styles.header}>
            <View style={{ flex: 1 }}>
              <Text style={styles.title} data-testid="features-lifecycle-title" testID="features-lifecycle-title">
                {tx('features.lifecycle.title', 'Feature Lifecycle')}
              </Text>
              <Text style={styles.subtitle} data-testid="features-lifecycle-subtitle" testID="features-lifecycle-subtitle">
                {tx('features.lifecycle.subtitle', 'Admin audit trail for retired and replaced catalog features.')}
              </Text>
            </View>
            <TouchableOpacity style={styles.closeButton} onPress={onClose} data-testid="features-lifecycle-close-button" testID="features-lifecycle-close-button">
              <Ionicons name="close" size={18} color={C.text} />
            </TouchableOpacity>
          </View>

          {loading ? (
            <View style={styles.state} data-testid="features-lifecycle-loading" testID="features-lifecycle-loading">
              <ActivityIndicator color={C.primary} />
              <Text style={styles.stateText}>{tx('features.lifecycle.loading', 'Loading lifecycle audit…')}</Text>
            </View>
          ) : error ? (
            <View style={styles.state} data-testid="features-lifecycle-error" testID="features-lifecycle-error">
              <Ionicons name="warning-outline" size={22} color={C.error} />
              <Text style={styles.errorText}>{error}</Text>
            </View>
          ) : (
            <ScrollView showsVerticalScrollIndicator={false} contentContainerStyle={{ paddingBottom: 18 }} data-testid="features-lifecycle-scroll" testID="features-lifecycle-scroll">
              <View style={styles.summaryRow} data-testid="features-lifecycle-summary" testID="features-lifecycle-summary">
                <View style={styles.summaryPill} data-testid="features-lifecycle-active-count" testID="features-lifecycle-active-count">
                  <Text style={styles.summaryValue}>{Number(audit?.summary?.active_features || fallbackActiveCount || 0)}</Text>
                  <Text style={styles.summaryLabel}>{tx('features.lifecycle.active', 'Active')}</Text>
                </View>
                <View style={styles.summaryPill} data-testid="features-lifecycle-retired-count" testID="features-lifecycle-retired-count">
                  <Text style={styles.summaryValue}>{Number(audit?.summary?.retired_features || retiredFeatures.length || 0)}</Text>
                  <Text style={styles.summaryLabel}>{tx('features.lifecycle.retired', 'Retired')}</Text>
                </View>
                <View style={styles.summaryPill} data-testid="features-lifecycle-phase" testID="features-lifecycle-phase">
                  <Text style={styles.summaryValue}>{String(audit?.summary?.latest_phase || 'PHASE_F')}</Text>
                  <Text style={styles.summaryLabel}>{tx('features.lifecycle.latestPhase', 'Latest phase')}</Text>
                </View>
              </View>

              <Text style={styles.sectionTitle}>{tx('features.lifecycle.retiredList', 'Retired catalog features')}</Text>
              {retiredFeatures.map((item: any) => (
                <View key={item.feature_id} style={styles.item} data-testid={`features-lifecycle-item-${item.feature_id}`} testID={`features-lifecycle-item-${item.feature_id}`}>
                  <View style={styles.itemHeader}>
                    <View style={{ flex: 1 }}>
                      <Text style={styles.itemTitle}>{String(item.title || item.feature_id)}</Text>
                      <Text style={styles.itemMeta}>{String(item.feature_id)} · {String(item.retired_phase || 'retired')}</Text>
                    </View>
                    <View style={styles.retiredBadge} data-testid={`features-lifecycle-status-${item.feature_id}`} testID={`features-lifecycle-status-${item.feature_id}`}>
                      <Text style={styles.retiredBadgeText}>{tx('features.lifecycle.retiredBadge', 'RETIRED')}</Text>
                    </View>
                  </View>
                  <Text style={styles.reason}>{String(item.retired_reason || '')}</Text>
                  <Text style={styles.routeText}>{tx('features.lifecycle.oldRoute', 'Old route')}: {String(item.route || '—')}</Text>
                  {item.replacement_route ? <Text style={styles.routeText}>{tx('features.lifecycle.replacement', 'Replacement')}: {String(item.replacement_route)}</Text> : null}
                </View>
              ))}

              <Text style={styles.sectionTitle}>{tx('features.lifecycle.auditEvents', 'Audit events')}</Text>
              {auditEvents.map((event: any, idx: number) => (
                <View key={`${event.phase || 'event'}-${idx}`} style={styles.event} data-testid={`features-lifecycle-event-${idx}`} testID={`features-lifecycle-event-${idx}`}>
                  <Text style={styles.itemTitle}>{String(event.name || event.phase || 'Lifecycle event')}</Text>
                  <Text style={styles.itemMeta}>{String(event.created_at || audit?.generated_at || '')}</Text>
                  <Text style={styles.reason}>{String(event.policy || '')}</Text>
                </View>
              ))}
            </ScrollView>
          )}
        </View>
      </View>
    </Modal>
  );
};

const createStyles = (C: any) => StyleSheet.create({
  overlay: { flex: 1, alignItems: 'center', justifyContent: 'center', padding: 12 },
  scrim: { ...StyleSheet.absoluteFillObject, backgroundColor: 'rgba(15, 23, 42, 0.42)' },
  drawer: {
    borderRadius: 16,
    borderWidth: 1,
    borderColor: C.border,
    backgroundColor: C.card,
    padding: 14,
    shadowColor: 'var(--app-text)',
    shadowOpacity: 0.18,
    shadowRadius: 20,
    shadowOffset: { width: 0, height: 10 },
  },
  header: { flexDirection: 'row', alignItems: 'flex-start', gap: 10, marginBottom: 12 },
  title: { color: C.text, fontSize: 20, fontWeight: '900' },
  subtitle: { color: C.textSec, fontSize: 12, marginTop: 3, lineHeight: 18 },
  closeButton: { width: 36, height: 36, borderRadius: 18, backgroundColor: C.bgSoft, alignItems: 'center', justifyContent: 'center' },
  state: { minHeight: 190, alignItems: 'center', justifyContent: 'center', gap: 10 },
  stateText: { color: C.textSec, fontSize: 12, fontWeight: '700' },
  errorText: { color: C.error, fontSize: 12, fontWeight: '700', textAlign: 'center' },
  summaryRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginBottom: 12 },
  summaryPill: { flex: 1, minWidth: 110, borderRadius: 12, borderWidth: 1, borderColor: C.border, backgroundColor: C.bgSoft, padding: 10 },
  summaryValue: { color: C.text, fontSize: 16, fontWeight: '900' },
  summaryLabel: { color: C.textMuted, fontSize: 10, fontWeight: '800', marginTop: 3, textTransform: 'uppercase' },
  sectionTitle: { color: C.text, fontSize: 13, fontWeight: '900', marginTop: 8, marginBottom: 8 },
  item: { borderRadius: 12, borderWidth: 1, borderColor: C.border, backgroundColor: C.bgSoft, padding: 11, marginBottom: 8 },
  event: { borderRadius: 12, borderWidth: 1, borderColor: C.border, backgroundColor: C.card, padding: 11, marginBottom: 8 },
  itemHeader: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 10 },
  itemTitle: { color: C.text, fontSize: 13, fontWeight: '900' },
  itemMeta: { color: C.textMuted, fontSize: 10, marginTop: 2, textTransform: 'uppercase' },
  reason: { color: C.textSec, fontSize: 11, lineHeight: 17, marginTop: 8 },
  routeText: { color: C.textMuted, fontSize: 11, marginTop: 5 },
  retiredBadge: { borderRadius: 999, borderWidth: 1, borderColor: C.warning || C.primary, backgroundColor: C.warningSoft || C.bgSoft, paddingHorizontal: 8, paddingVertical: 4 },
  retiredBadgeText: { color: C.warningText || C.textSec, fontSize: 9, fontWeight: '900' },
});