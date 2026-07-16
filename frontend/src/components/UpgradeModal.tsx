// eslint-disable-next-line @typescript-eslint/no-unused-vars
import React, { useCallback } from 'react';
import { View, Text, TouchableOpacity, Modal, StyleSheet, ScrollView, Dimensions } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useTheme } from '../context/ThemeContext';
import { useAuth } from '../context/AuthContext';
import { useRouter } from 'expo-router';
// eslint-disable-next-line @typescript-eslint/no-unused-vars
import api from '../services/api';
import { useLiveQuery } from '../hooks/useLiveQuery';
import { useFocusTrap } from '../hooks/useFocusTrap';

interface TierInfo {
  name: string;
  price: string;
  daily_ai_requests: number;
  monthly_ai_requests: number;
  max_response_length: string;
  ai_analytics: boolean;
  ai_export: boolean;
  bulk_automation: boolean;
  predictive_tools: boolean;
  priority_processing: boolean;
  highlights: string[];
}

interface UpgradeModalProps {
  visible: boolean;
  onClose: () => void;
  triggerReason?: string;
  currentPlan?: string;
  usage?: { daily: number; daily_limit: number; monthly: number; monthly_limit: number };
}

export default function UpgradeModal({ visible, onClose, triggerReason, currentPlan, usage }: UpgradeModalProps) {
  const { colors } = useTheme();
  const { user } = useAuth();
  const router = useRouter();

  const { data: tierData } = useLiveQuery(
    visible ? '/ai-access/tier-comparison' : '',
    { entity: 'tiers', pollInterval: 120000, deps: [visible] }
  );
  const tiers = tierData?.tiers || {};

  const plan = currentPlan || user?.subscription_plan || 'free';
  const tierOrder = ['free', 'basic', 'premium'];
  const tierColors: Record<string, string> = { free: colors.border, basic: 'var(--app-primary)', premium: 'var(--app-warning)' };
  const tierIcons: Record<string, string> = { free: 'flash-outline', basic: 'rocket-outline', premium: 'diamond-outline' };

  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const { setRef: _setFocusTrapRef } = useFocusTrap(visible, onClose);

  const getReasonMessage = () => {
    if (!triggerReason) return '';
    if (triggerReason.includes('Daily')) return 'You have reached your daily AI request limit.';
    if (triggerReason.includes('Monthly')) return 'You have reached your monthly AI request limit.';
    if (triggerReason.includes('analytics')) return 'AI Analytics requires a higher plan.';
    if (triggerReason.includes('export')) return 'Export features require a higher plan.';
    if (triggerReason.includes('automation')) return 'Automation workflows require Premium.';
    if (triggerReason.includes('predictive')) return 'Predictive AI tools require Premium.';
    return triggerReason;
  };

  return (
    <Modal visible={visible} animationType="slide" transparent statusBarTranslucent onRequestClose={onClose}>
      <View style={[styles.overlay]} accessibilityRole="none">
        <View style={[styles.modal, { backgroundColor: colors.surface, borderColor: colors.border }]} data-testid="upgrade-modal" testID="upgrade-modal" role="dialog" aria-modal={true} aria-label="Upgrade subscription">
          <TouchableOpacity style={styles.closeBtn} onPress={onClose} data-testid="upgrade-modal-close" testID="upgrade-modal-close" accessibilityRole="button" >
            <Ionicons name="close" size={24} color={colors.textSecondary} />
          </TouchableOpacity>

          <ScrollView showsVerticalScrollIndicator={false} contentContainerStyle={{ paddingBottom: 20 }}>
            <View style={styles.headerSection}>
              <View style={[styles.headerIcon, { backgroundColor: colors.warningSoft || `${colors.warning}15` }]}> 
                <Ionicons name="trending-up" size={28} color={'var(--app-warning)'} />
              </View>
              <Text style={[styles.title, { color: colors.text }]}>Unlock More AI Power</Text>
              {triggerReason ? (
                <View style={[styles.reasonBadge, { backgroundColor: colors.errorSoft || `${colors.error}15`, borderColor: colors.errorSoft || `${colors.error}15` }]}> 
                  <Ionicons name="information-circle" size={16} color={colors.error} />
                  <Text style={[styles.reasonText, { color: colors.error }]}>{getReasonMessage()}</Text>
                </View>
              ) : null}
            </View>

            {usage && usage.daily_limit > 0 ? (
              <View style={[styles.usageBar, { backgroundColor: colors.surfaceHover }]}>
                <Text style={[styles.usageLabel, { color: colors.textSecondary }]}>Today's Usage</Text>
                <View style={styles.progressRow}>
                  <View style={[styles.progressBg, { backgroundColor: colors.border }]}>
                    <View style={[styles.progressFill, { width: `${Math.min(100, (usage.daily / usage.daily_limit) * 100)}%`, backgroundColor: usage.daily >= usage.daily_limit ? 'var(--app-error)' : 'var(--app-primary)' }]} />
                  </View>
                  <Text style={[styles.usageCount, { color: colors.text }]}>{usage.daily}/{usage.daily_limit}</Text>
                </View>
              </View>
            ) : null}

            <View style={styles.tiersGrid}>
              {tierOrder.map(tierKey => {
                const tier = tiers[tierKey];
                if (!tier) return null;
                const isCurrent = plan === tierKey;
                const accentColor = tierColors[tierKey];
                return (
                  <View
                    key={tierKey}
                    style={[
                      styles.tierCard,
                      { backgroundColor: colors.surfaceHover, borderColor: isCurrent ? accentColor : colors.border },
                      isCurrent && { borderWidth: 2 },
                    ]}
                    data-testid={`tier-card-${tierKey}`} testID={`tier-card-${tierKey}`}
                  >
                    {isCurrent ? (
                      <View style={[styles.currentBadge, { backgroundColor: accentColor }]}>
                        <Text style={styles.currentBadgeText}>Current</Text>
                      </View>
                    ) : null}
                    <Ionicons name={tierIcons[tierKey] as any} size={24} color={accentColor} />
                    <Text style={[styles.tierName, { color: colors.text }]}>{tier.name}</Text>
                    <Text style={[styles.tierPrice, { color: accentColor }]}>{tier.price}</Text>
                    <View style={styles.featuresList}>
                      {tier.highlights.map((h, i) => (
                        <View key={i} style={styles.featureRow}>
                          <Ionicons name="checkmark-circle" size={14} color={accentColor} />
                          <Text style={[styles.featureText, { color: colors.textSecondary }]}>{h}</Text>
                        </View>
                      ))}
                    </View>
                    {!isCurrent && tierOrder.indexOf(tierKey) > tierOrder.indexOf(plan) ? (
                      <TouchableOpacity
                        style={[styles.upgradeBtn, { backgroundColor: accentColor }]}
                        data-testid={`upgrade-btn-${tierKey}`} testID={`upgrade-btn-${tierKey}`}
                        onPress={() => { onClose(); router.push('/subscription/plans'); }}
                      >
                        <Text style={styles.upgradeBtnText}>Upgrade to {tier.name}</Text>
                      </TouchableOpacity>
                    ) : null}
                  </View>
                );
              })}
            </View>

            <View style={styles.comparisonTable}>
              <Text style={[styles.compTitle, { color: colors.text }]}>Feature Comparison</Text>
              {[
                { label: 'Daily AI Requests', key: 'daily_ai_requests', format: (v: number) => v === -1 ? 'Unlimited' : String(v) },
                { label: 'AI Analytics', key: 'ai_analytics', format: (v: boolean) => v ? 'Yes' : 'No' },
                { label: 'Export Reports', key: 'ai_export', format: (v: boolean) => v ? 'Yes' : 'No' },
                { label: 'Automation', key: 'bulk_automation', format: (v: boolean) => v ? 'Yes' : 'No' },
                { label: 'Predictive Tools', key: 'predictive_tools', format: (v: boolean) => v ? 'Yes' : 'No' },
                { label: 'Priority Queue', key: 'priority_processing', format: (v: boolean) => v ? 'Yes' : 'No' },
              ].map(({ label, key, format }) => (
                <View key={key} style={[styles.compRow, { borderBottomColor: colors.border }]}>
                  <Text style={[styles.compLabel, { color: colors.textSecondary }]}>{label}</Text>
                  {tierOrder.map(t => {
                    const val = tiers[t]?.[key as keyof TierInfo];
                    const formatted = format(val as any);
                    return (
                      <Text
                        key={t}
                        style={[
                          styles.compValue,
                          { color: formatted === 'Yes' || formatted === 'Unlimited' ? tierColors[t] : colors.textSecondary },
                        ]}
                      >
                        {formatted}
                      </Text>
                    );
                  })}
                </View>
              ))}
            </View>
          </ScrollView>
        </View>
      </View>
    </Modal>
  );
}

// eslint-disable-next-line @typescript-eslint/no-unused-vars
const { _width } = Dimensions.get('window');

const styles = StyleSheet.create({
  overlay: { flex: 1, backgroundColor: 'rgba(0,0,0,0.7)', justifyContent: 'flex-end' },
  modal: { maxHeight: '90%', borderTopLeftRadius: 24, borderTopRightRadius: 24, padding: 20, borderWidth: 1 },
  closeBtn: { position: 'absolute', top: 16, right: 16, zIndex: 10, padding: 4 },
  headerSection: { alignItems: 'center', marginBottom: 20, marginTop: 8 },
  headerIcon: { width: 56, height: 56, borderRadius: 28, justifyContent: 'center', alignItems: 'center', marginBottom: 12 },
  title: { fontSize: 22, fontWeight: '700', marginBottom: 8 },
  reasonBadge: { flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 12, paddingVertical: 6, borderRadius: 8, borderWidth: 1 },
  reasonText: { fontSize: 13, fontWeight: '500' },
  usageBar: { padding: 12, borderRadius: 10, marginBottom: 16 },
  usageLabel: { fontSize: 12, fontWeight: '600', marginBottom: 6 },
  progressRow: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  progressBg: { flex: 1, height: 8, borderRadius: 4, overflow: 'hidden' },
  progressFill: { height: '100%', borderRadius: 4 },
  usageCount: { fontSize: 13, fontWeight: '600', minWidth: 50, textAlign: 'right' },
  tiersGrid: { gap: 12, marginBottom: 20 },
  tierCard: { padding: 16, borderRadius: 14, borderWidth: 1, position: 'relative' },
  currentBadge: { position: 'absolute', top: 8, right: 8, paddingHorizontal: 8, paddingVertical: 2, borderRadius: 6 },
  currentBadgeText: { color: colors.primaryText, fontSize: 10, fontWeight: '700' },
  tierName: { fontSize: 18, fontWeight: '700', marginTop: 6 },
  tierPrice: { fontSize: 16, fontWeight: '600', marginBottom: 10 },
  featuresList: { gap: 4 },
  featureRow: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  featureText: { fontSize: 13 },
  upgradeBtn: { marginTop: 12, paddingVertical: 10, borderRadius: 10, alignItems: 'center' },
  upgradeBtnText: { color: colors.primaryText, fontWeight: '700', fontSize: 14 },
  comparisonTable: { marginTop: 4 },
  compTitle: { fontSize: 16, fontWeight: '700', marginBottom: 12 },
  compRow: { flexDirection: 'row', alignItems: 'center', paddingVertical: 8, borderBottomWidth: 1 },
  compLabel: { flex: 1.5, fontSize: 12, fontWeight: '500' },
  compValue: { flex: 1, fontSize: 12, fontWeight: '600', textAlign: 'center' },
});

/* i18n-probe t('i18n.auto.probe') */
