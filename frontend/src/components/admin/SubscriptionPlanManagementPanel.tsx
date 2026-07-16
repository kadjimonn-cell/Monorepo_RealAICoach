import React, { useState } from 'react';
// @gls-exempt — intentional fixed-width UI element (sidebar/chat/label/toast)
import { View, Text, TouchableOpacity, ActivityIndicator, TextInput, Modal, ScrollView } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { useExecTheme, useExecStyles } from './ExecDashboardPanels';
import { useLiveQuery } from '../../hooks/useLiveQuery';
import AutoFixBanner from './AutoFixBanner';
import { useAdminTheme } from '../../hooks/useAdminTheme';
import { useTranslation } from '../../hooks/useTranslation';

export default function SubscriptionPlanManagementPanel() {
  const s = useExecStyles();
  const _colors = useAdminTheme();
  const T = useExecTheme();
  const { t } = useTranslation();
  const tx = React.useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);
  const [editPlan, setEditPlan] = useState<any>(null);
  const [saving, setSaving] = useState(false);

  const { data: plansRaw, loading: plansLoading, refetch: loadPlans } = useLiveQuery('/subscriptions/plans', { entity: 'subscriptions', pollInterval: 60000 });
  const { data: statsRaw } = useLiveQuery('/admin/executive/overview', { entity: 'admin_overview', pollInterval: 60000 });
  const { data: subRaw } = useLiveQuery('/admin/subscription-analytics/overview', { entity: 'subscriptions', pollInterval: 60000 });

  const planData = plansRaw?.plans || plansRaw || [];
  const plans = Array.isArray(planData) ? planData : [];
  const stats = statsRaw || null;
  const subStats = subRaw?.plan_distribution || [];
  const loading = plansLoading;

  const totalSubs = stats?.kpis?.find((k: any) => k.id === 'active_subscriptions')?.value || 0;
  const revenue = stats?.kpis?.find((k: any) => k.id === 'total_revenue')?.value || 0;
  const totalUsers = stats?.kpis?.find((k: any) => k.id === 'total_users')?.value || 0;

  const kpis = [
    { label: 'Total Plans', value: plans.length, icon: 'pricetags', color: T.primary },
    { label: 'Active Subscriptions', value: totalSubs, icon: 'people', color: T.successText },
    { label: 'Monthly Revenue', value: `$${typeof revenue === 'number' ? revenue.toLocaleString() : revenue}`, icon: 'cash', color: T.warningText },
    { label: 'Total Users', value: totalUsers, icon: 'person', color: T.cyan },
  ];

  const tierColors: Record<string, string> = { free: T.textMuted, basic: T.primary, premium: T.warning, enterprise: T.purple, pro: T.success };

  const getSubCount = (planId: string) => {
    const found = subStats.find((s: any) => s.plan?.toLowerCase() === planId?.toLowerCase() || s.plan_id === planId);
    return found?.count || found?.users || 0;
  };

  const handleEditSave = async () => {
    if (!editPlan) return;
    setSaving(true);
    try {
      await api.post('/subscriptions/plans/update', editPlan).catch(() => null);
      setEditPlan(null);
      loadPlans();
    } catch (e) { console.error(e); }
    finally { setSaving(false); }
  };

  if (loading) return <View style={{ padding: 40, alignItems: 'center' }}><ActivityIndicator size="large" color={T.primary} /></View>;

  return (
    <View style={s.panel} data-testid="subscription-plan-mgmt-panel" testID="subscription-plan-mgmt-panel">
      <AutoFixBanner domain="subscription" />      {/* KPI Row */}
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 12, marginBottom: 20 }}>
        {kpis.map((k, i) => (
          <View key={i} style={[s.kpiCard, { flex: 1, minWidth: 180, borderLeftColor: k.color, borderLeftWidth: 3 }]}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
              <Ionicons name={k.icon as any} size={18} color={k.color} />
              <Text style={{ color: T.textSec, fontSize: 12, fontWeight: '600', textTransform: 'uppercase' }}>{k.label}</Text>
            </View>
            <Text style={{ color: T.text, fontSize: 28, fontWeight: '700', marginTop: 6 }}>{k.value}</Text>
          </View>
        ))}
      </View>

      {/* Plan Cards Grid */}
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 16 }}>
        {plans.map((plan, i) => {
          const color = tierColors[plan.id?.toLowerCase()] || tierColors[plan.name?.toLowerCase()] || T.primary;
          const subscribers = getSubCount(plan.id || plan.name);
          return (
            <View key={plan.id || i} style={{ backgroundColor: T.card, borderRadius: 14, borderWidth: 1, borderColor: T.border, padding: 20, width: 280, borderTopColor: color, borderTopWidth: 3 }}
              data-testid={`plan-card-${plan.id || i}`} testID={`plan-card-${plan.id || i}`}>
              <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
                <Text style={{ color: T.text, fontSize: 18, fontWeight: '800' }}>{plan.name || plan.title}</Text>
                {plan.badge === 'popular' && (
                  <View style={{ backgroundColor: T.warningSoft, paddingHorizontal: 8, paddingVertical: 2, borderRadius: 8 }}>
                    <Text style={{ color: T.warningText, fontSize: 10, fontWeight: '700' }}>{tx('admin.subscriptionPlanManagement.badges.popular', 'POPULAR')}</Text>
                  </View>
                )}
              </View>

              {/* Price */}
              <View style={{ flexDirection: 'row', alignItems: 'baseline', marginTop: 8 }}>
                <Text style={{ color: T.text, fontSize: 32, fontWeight: '800' }}>${plan.monthly_price ?? plan.price_monthly ?? plan.price ?? 0}</Text>
                <Text style={{ color: T.textMuted, fontSize: 13, marginLeft: 4 }}>{tx('admin.subscriptionPlanManagement.labels.perMonth', '/mo')}</Text>
              </View>
              {(plan.yearly_price ?? plan.price_yearly) != null && (plan.yearly_price ?? plan.price_yearly) > 0 && (
                <Text style={{ color: T.textSec, fontSize: 12, marginTop: 2 }}>${plan.yearly_price ?? plan.price_yearly}/yr</Text>
              )}

              {/* Subscriber Count */}
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginTop: 10, backgroundColor: (globalThis as any).__alphaColor(color, '10'), borderRadius: 8, paddingHorizontal: 10, paddingVertical: 6 }}>
                <Ionicons name="people" size={14} color={color} />
                <Text style={{ color, fontSize: 12, fontWeight: '700' }}>{subscribers} subscribers</Text>
              </View>

              {/* Features */}
              <View style={{ marginTop: 12, gap: 6 }}>
                {(plan.features || []).slice(0, 5).map((f: string, fi: number) => (
                  <View key={fi} style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                    <Ionicons name="checkmark-circle" size={14} color={color} />
                    <Text style={{ color: T.textSec, fontSize: 12 }}>{f}</Text>
                  </View>
                ))}
              </View>

              {/* Limits */}
              <View style={{ marginTop: 12, paddingTop: 12, borderTopWidth: 1, borderTopColor: T.border, gap: 4 }}>
                <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
                  <Text style={{ color: T.textMuted, fontSize: 11 }}>{tx('admin.subscriptionPlanManagement.labels.dailyAiLimit', 'Daily AI Limit')}</Text>
                  <Text style={{ color: T.textSec, fontSize: 11, fontWeight: '600' }}>{plan.daily_conversation_limit || 'Unlimited'}</Text>
                </View>
                {plan.monthly_limit && (
                  <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
                    <Text style={{ color: T.textMuted, fontSize: 11 }}>{tx('admin.subscriptionPlanManagement.labels.monthlyLimit', 'Monthly Limit')}</Text>
                    <Text style={{ color: T.textSec, fontSize: 11, fontWeight: '600' }}>{plan.monthly_limit}</Text>
                  </View>
                )}
              </View>

              {/* Edit Button */}
              <TouchableOpacity onPress={() => setEditPlan({ ...plan })}
                style={{ marginTop: 14, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, paddingVertical: 8, backgroundColor: T.primarySoft, borderRadius: 8, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(T.primary, '30') }}
                data-testid={`edit-plan-${plan.id || i}`} testID={`edit-plan-${plan.id || i}`}>
                <Ionicons name="create-outline" size={14} color={T.primary} />
                <Text style={{ color: T.primary, fontSize: 12, fontWeight: '700' }}>{tx('admin.subscriptionPlanManagement.actions.editPlan', 'Edit Plan')}</Text>
              </TouchableOpacity>
            </View>
          );
        })}
        {plans.length === 0 && (
          <View style={{ padding: 30, alignItems: 'center', width: '100%' }}>
            <Ionicons name="pricetags-outline" size={36} color={T.textMuted} />
            <Text style={{ color: T.textMuted, marginTop: 8, fontSize: 13 }}>{tx('admin.subscriptionPlanManagement.states.noPlans', 'No subscription plans configured')}</Text>
          </View>
        )}
      </View>

      {/* Edit Plan Modal */}
      {editPlan && (
        <Modal visible={!!editPlan} transparent animationType="fade" onRequestClose={() => setEditPlan(null)}>
          <View style={{ flex: 1, backgroundColor: 'rgba(0,0,0,0.8)', justifyContent: 'center', alignItems: 'center', padding: 20 }}>
            <View style={{ backgroundColor: T.bgSoft, borderRadius: 16, width: '100%', maxWidth: 500, borderWidth: 1, borderColor: T.border, padding: 24 }}>
              <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
                <Text style={{ color: T.text, fontSize: 18, fontWeight: '800' }}>Edit Plan: {editPlan.name}</Text>
                <TouchableOpacity onPress={() => setEditPlan(null)} data-testid="close-edit-plan" testID="close-edit-plan">
                  <Ionicons name="close" size={20} color={T.textMuted} />
                </TouchableOpacity>
              </View>

              <ScrollView style={{ maxHeight: 400 }}>
                {[
                  { key: 'name', label: 'Plan Name' },
                  { key: 'monthly_price', label: 'Monthly Price ($)', keyboard: 'numeric' },
                  { key: 'yearly_price', label: 'Yearly Price ($)', keyboard: 'numeric' },
                  { key: 'daily_conversation_limit', label: 'Daily AI Limit', keyboard: 'numeric' },
                ].map(field => (
                  <View key={field.key} style={{ marginBottom: 14 }}>
                    <Text style={{ color: T.textSec, fontSize: 12, fontWeight: '600', marginBottom: 6 }}>{field.label}</Text>
                    <TextInput
                      value={String(editPlan[field.key] ?? editPlan[`price_${field.key.replace('monthly_price','monthly').replace('yearly_price','yearly')}`] ?? '')}
                      onChangeText={v => setEditPlan((prev: any) => ({ ...prev, [field.key]: field.keyboard === 'numeric' ? Number(v) || 0 : v }))}
                      style={{ backgroundColor: T.card, borderWidth: 1, borderColor: T.border, borderRadius: 8, paddingHorizontal: 12, paddingVertical: 10, color: T.text, fontSize: 14 } as any}
                      placeholderTextColor={T.textMuted}
                      data-testid={`edit-field-${field.key}`} testID={`edit-field-${field.key}`}
                    />
                  </View>
                ))}

                {/* Features */}
                <View style={{ marginBottom: 14 }}>
                  <Text style={{ color: T.textSec, fontSize: 12, fontWeight: '600', marginBottom: 6 }}>{tx('admin.subscriptionPlanManagement.edit.featuresLabel', 'Features (one per line)')}</Text>
                  <TextInput accessibilityLabel="Text input"
                    value={(editPlan.features || []).join('\n')}
                    onChangeText={v => setEditPlan((prev: any) => ({ ...prev, features: v.split('\n') }))}
                    multiline
                    numberOfLines={5}
                    style={{ backgroundColor: T.card, borderWidth: 1, borderColor: T.border, borderRadius: 8, paddingHorizontal: 12, paddingVertical: 10, color: T.text, fontSize: 13, minHeight: 100, textAlignVertical: 'top' } as any}
                    placeholderTextColor={T.textMuted}
                    data-testid="edit-field-features" testID="edit-field-features"
                  />
                </View>
              </ScrollView>

              <View style={{ flexDirection: 'row', gap: 10, marginTop: 16 }}>
                <TouchableOpacity accessibilityLabel="Cancel" onPress={() => setEditPlan(null)} style={{ flex: 1, paddingVertical: 10, borderRadius: 8, backgroundColor: T.card, alignItems: 'center', borderWidth: 1, borderColor: T.border }}>
                  <Text style={{ color: T.textSec, fontSize: 13, fontWeight: '600' }}>{tx('admin.subscriptionPlanManagement.actions.cancel', 'Cancel')}</Text>
                </TouchableOpacity>
                <TouchableOpacity onPress={handleEditSave} disabled={saving}
                  style={{ flex: 1, paddingVertical: 10, borderRadius: 8, backgroundColor: T.primary, alignItems: 'center', opacity: saving ? 0.6 : 1 }}
                  data-testid="save-plan-btn" testID="save-plan-btn">
                  <Text style={{ color: T.primaryText, fontSize: 13, fontWeight: '700' }}>{saving ? 'Saving...' : 'Save Changes'}</Text>
                </TouchableOpacity>
              </View>
            </View>
          </View>
        </Modal>
      )}
    </View>
  );
}
