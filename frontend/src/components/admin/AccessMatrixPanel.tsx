import React, { useState } from 'react';
import { View, Text, TouchableOpacity, ActivityIndicator, ScrollView, useWindowDimensions } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useLiveQuery } from '../../hooks/useLiveQuery';
import AutoFixBanner from './AutoFixBanner';
import { useAdminTheme } from '../../hooks/useAdminTheme';
import { useTranslation } from '../../hooks/useTranslation';

const PERM_CATEGORY_COLORS: Record<string, string> = {
  team: 'var(--app-primary)', analytics: 'var(--app-primary)', content: 'var(--app-success)', hiring: 'var(--app-warning)', // @theme-ok brand/role/state identifier
};

export default function AccessMatrixPanel({ colors: _colors }: { colors: any }) {
  const colors = useAdminTheme();
  const { t } = useTranslation();
  const tx = React.useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);
  const { data, loading, refetch: load } = useLiveQuery('/access-matrix/overview', { entity: 'access-matrix', pollInterval: 60000 });
  const [view, setView] = useState<'matrix' | 'usage'>('matrix');
  const { width } = useWindowDimensions();
  const isMobile = width < 900;

  if (loading) return <ActivityIndicator color={'var(--app-primary)'} />;
  if (!data) return <Text style={{ color: colors.textMuted, textAlign: 'center', padding: 20 }}>{tx('admin.accessMatrixPanel.states.loadFailed', 'Failed to load')}</Text>;

  const allRoles = [...(data.builtin_roles || []), ...(data.custom_roles || [])];
  const perms = data.permissions || [];
  const categories = [...new Set(perms.map((p: any) => p.category))];

  return (
    <View data-testid="access-matrix-panel" testID="access-matrix-panel">
      <AutoFixBanner domain="access_matrix" />
      {/* Header */}
      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 6 }}>
        <View>
          <Text style={{ color: colors.text, fontSize: 18, fontWeight: '800' }}>{tx('admin.accessMatrixPanel.header.title', 'Access Matrix')}</Text>
          <Text style={{ color: colors.textMuted, fontSize: 11, marginTop: 2 }}>{tx('admin.accessMatrixPanel.header.subtitle', 'Executive role-permission audit across all teams')}</Text>
        </View>
        <TouchableOpacity onPress={load} data-testid="access-matrix-refresh" testID="access-matrix-refresh" style={{ flexDirection: 'row', alignItems: 'center', gap: 4, backgroundColor: colors.surface, paddingHorizontal: 12, paddingVertical: 8, borderRadius: 8, borderWidth: 1, borderColor: colors.border }}>
          <Ionicons name="refresh" size={14} color={colors.textMuted} />
          <Text style={{ color: colors.textMuted, fontSize: 10, fontWeight: '600' }}>{tx('admin.accessMatrixPanel.actions.refresh', 'Refresh')}</Text>
        </TouchableOpacity>
      </View>

      {/* KPIs */}
      <View style={{ flexDirection: 'row', gap: 8, marginTop: 16, marginBottom: 20, flexWrap: 'wrap' }}>
        <KPI label="Total Roles" value={data.total_roles} color={'var(--app-primary)'} icon="ribbon" colors={colors} compact={isMobile} />
        <KPI label="Permissions" value={data.total_permissions} color={'var(--app-primary)'} icon="key" colors={colors} compact={isMobile} />
        <KPI label="Built-in" value={(data.builtin_roles || []).length} color={'var(--app-success)'} icon="shield-checkmark" colors={colors} compact={isMobile} />
        <KPI label="Custom" value={(data.custom_roles || []).length} color={'var(--app-warning)'} icon="create" colors={colors} compact={isMobile} />
      </View>

      {/* View Switcher */}
      <View style={{ flexDirection: 'row', gap: 6, marginBottom: 16 }}>
        {(['matrix', 'usage'] as const).map(v => (
          <TouchableOpacity key={v} onPress={() => setView(v)} data-testid={`access-view-${v}`} testID={`access-view-${v}`}
            style={{ paddingHorizontal: 14, paddingVertical: 7, borderRadius: 8, backgroundColor: view === v ? 'var(--app-primary)' : colors.surfaceHover, borderWidth: 1, borderColor: view === v ? 'var(--app-primary)' : colors.border }}>
            <Text style={{ color: view === v ? colors.primaryText : colors.textMuted, fontSize: 11, fontWeight: '700', textTransform: 'capitalize' }}>{v === 'matrix' ? 'Permission Matrix' : 'Usage Analytics'}</Text>
          </TouchableOpacity>
        ))}
      </View>

      {view === 'matrix' && (
        <View>
          {/* Matrix Grid */}
          <ScrollView horizontal showsHorizontalScrollIndicator={false}>
            <View style={{ minWidth: isMobile ? 620 : 700 }}>
              {/* Header Row */}
              <View style={{ flexDirection: 'row', borderBottomWidth: 2, borderBottomColor: colors.border, paddingBottom: 8, marginBottom: 4 }}>
                <View style={{ width: 130 }}>
                  <Text style={{ color: colors.textMuted, fontSize: 9, fontWeight: '800', letterSpacing: 1.2 }}>{tx('admin.accessMatrixPanel.table.role', 'ROLE')}</Text>
                </View>
                {perms.map((p: any) => (
                  <View key={p.id} style={{ width: 70, alignItems: 'center' }}>
                    <View style={{ width: 4, height: 4, borderRadius: 2, backgroundColor: PERM_CATEGORY_COLORS[p.category] || colors.textSec, marginBottom: 3 }} />
                    <Text style={{ color: colors.textMuted, fontSize: 8, fontWeight: '700', textAlign: 'center' }} numberOfLines={2}>{p.label}</Text>
                  </View>
                ))}
              </View>

              {/* Role Rows */}
              {allRoles.map((role: any, idx: number) => {
                const isCustom = role.type === 'custom';
                return (
                  <View key={role.role_id} data-testid={`matrix-role-${role.role_id}`} testID={`matrix-role-${role.role_id}`}
                    style={{ flexDirection: 'row', alignItems: 'center', paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: (globalThis as any).__alphaColor(colors.border, '30'), backgroundColor: (globalThis as any).__alphaColor(idx % 2 === 0 ? 'transparent' : colors.surfaceHover, '40') }}>
                    <View style={{ width: 130, flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                      <View style={{ width: 6, height: 24, borderRadius: 3, backgroundColor: role.color || colors.border }} />
                      <View>
                        <Text style={{ color: colors.text, fontSize: 11, fontWeight: '700' }}>{role.name}</Text>
                        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 3, marginTop: 1 }}>
                          <Text style={{ color: colors.textMuted, fontSize: 8 }}>Lv.{role.level}</Text>
                          {isCustom && (
                            <View style={{ backgroundColor: colors.warningSoft, paddingHorizontal: 4, paddingVertical: 1, borderRadius: 3 }}>
                              <Text style={{ color: colors.warningText, fontSize: 7, fontWeight: '800' }}>{tx('admin.accessMatrixPanel.badges.custom', 'CUSTOM')}</Text>
                            </View>
                          )}
                        </View>
                      </View>
                    </View>
                    {perms.map((p: any) => {
                      const granted = role.permissions?.[p.id];
                      return (
                        <View key={p.id} style={{ width: 70, alignItems: 'center' }}>
                          <View style={{
                            width: 28, height: 28, borderRadius: 8,
                            backgroundColor: granted ? (globalThis as any).__alphaColor((role.color || 'var(--app-success)'), '15') : colors.surface,
                            borderWidth: 1, borderColor: granted ? (globalThis as any).__alphaColor((role.color || 'var(--app-success)'), '40') : colors.border + '40',
                            alignItems: 'center', justifyContent: 'center',
                          }}>
                            {granted ? (
                              <Ionicons name="checkmark" size={14} color={role.color || 'var(--app-success)'} />
                            ) : (
                              <Ionicons name="close" size={10} color={colors.border} />
                            )}
                          </View>
                        </View>
                      );
                    })}
                  </View>
                );
              })}
            </View>
          </ScrollView>

          {/* Category Legend */}
          <View style={{ flexDirection: 'row', gap: 12, marginTop: 16, paddingTop: 12, borderTopWidth: 1, borderTopColor: colors.border }}>
            {categories.map((cat: string) => (
              <View key={cat} style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}>
                <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: PERM_CATEGORY_COLORS[cat] || colors.border }} />
                <Text style={{ color: colors.textMuted, fontSize: 9, fontWeight: '700', textTransform: 'capitalize' }}>{cat}</Text>
              </View>
            ))}
          </View>
        </View>
      )}

      {view === 'usage' && (
        <View>
          {/* Permission Usage Chart */}
          <View style={{ backgroundColor: colors.surfaceHover, borderRadius: 12, padding: 14, borderWidth: 1, borderColor: colors.border, marginBottom: 16 }}>
            <Text style={{ color: colors.text, fontSize: 14, fontWeight: '700', marginBottom: 12 }}>{tx('admin.accessMatrixPanel.usage.permissionCoverage', 'Permission Coverage')}</Text>
            {(data.permission_usage || []).map((pu: any) => {
              const pct = Math.round((pu.granted_to / Math.max(pu.total_roles, 1)) * 100);
              const catColor = PERM_CATEGORY_COLORS[pu.category] || colors.textSec;
              return (
                <View key={pu.permission_id} style={{ marginBottom: 10 }} data-testid={`perm-usage-${pu.permission_id}`} testID={`perm-usage-${pu.permission_id}`}>
                  <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginBottom: 4 }}>
                    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                      <View style={{ width: 6, height: 6, borderRadius: 3, backgroundColor: catColor }} />
                      <Text style={{ color: colors.text, fontSize: 11, fontWeight: '600' }}>{pu.label}</Text>
                    </View>
                    <Text style={{ color: colors.textMuted, fontSize: 10, fontWeight: '700' }}>{pu.granted_to}/{pu.total_roles} roles ({pct}%)</Text>
                  </View>
                  <View style={{ height: 8, backgroundColor: (globalThis as any).__alphaColor(colors.border, '30'), borderRadius: 4, overflow: 'hidden' }}>
                    <View style={{ height: 8, width: `${Math.max(pct, 4)}%`, backgroundColor: catColor, borderRadius: 4 }} />
                  </View>
                </View>
              );
            })}
          </View>

          {/* Member Counts per Role */}
          <View style={{ backgroundColor: colors.surfaceHover, borderRadius: 12, padding: 14, borderWidth: 1, borderColor: colors.border }}>
            <Text style={{ color: colors.text, fontSize: 14, fontWeight: '700', marginBottom: 12 }}>{tx('admin.accessMatrixPanel.usage.membersPerRole', 'Members per Role')}</Text>
            {Object.entries(data.role_member_counts || {}).map(([role, count]: [string, any]) => {
              const roleData = allRoles.find((r: any) => r.role_id === role);
              const maxCount = Math.max(...Object.values(data.role_member_counts || {}).map(Number), 1);
              const pct = Math.round((count / maxCount) * 100);
              return (
                <View key={role} style={{ flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 8 }}>
                  <View style={{ width: 70 }}>
                    <Text style={{ color: roleData?.color || colors.textSec, fontSize: 10, fontWeight: '800', textTransform: 'uppercase' }}>{role}</Text>
                  </View>
                  <View style={{ flex: 1, height: 24, backgroundColor: (globalThis as any).__alphaColor(colors.border, '20'), borderRadius: 6, overflow: 'hidden' }}>
                    <View style={{ height: 24, width: `${Math.max(pct, 8)}%`, backgroundColor: (globalThis as any).__alphaColor((roleData?.color || colors.border), '25'), borderRadius: 6, justifyContent: 'center', paddingLeft: 8 }}>
                      <Text style={{ color: roleData?.color || colors.text, fontSize: 11, fontWeight: '800' }}>{count}</Text>
                    </View>
                  </View>
                </View>
              );
            })}
            {Object.keys(data.role_member_counts || {}).length === 0 && (
              <Text style={{ color: colors.textMuted, fontSize: 11, textAlign: 'center', padding: 12 }}>{tx('admin.accessMatrixPanel.usage.noMemberData', 'No member data available yet')}</Text>
            )}
          </View>
        </View>
      )}
    </View>
  );
}

function KPI({ label, value, color, icon, colors, compact = false }: any) {
  return (
    <View style={{ flex: 1, minWidth: compact ? '47%' : 100, backgroundColor: (globalThis as any).__alphaColor(color, '08'), borderRadius: 12, padding: 14, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(color, '20') }}>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 5, marginBottom: 6 }}>
        <Ionicons name={icon} size={13} color={color} />
        <Text style={{ color: colors.textMuted, fontSize: 10, fontWeight: '600' }}>{label}</Text>
      </View>
      <Text style={{ color, fontSize: 22, fontWeight: '800' }}>{value}</Text>
    </View>
  );
}
