import React, { useState } from 'react';
import { View, Text, TouchableOpacity, ActivityIndicator } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { useLiveQuery } from '../../hooks/useLiveQuery';
import AutoFixBanner from './AutoFixBanner';
import { useAdminTheme } from '../../hooks/useAdminTheme';
import { useTranslation } from '../../hooks/useTranslation';

interface Widget {
  id: string;
  title: string;
  visible: boolean;
  order: number;
  size: string;
}

interface Props {
  dashboardType: string;
  colors: any;
  onLayoutChange?: (widgets: Widget[]) => void;
}

const tx = (_key: string, fallback: string) => fallback;

export default function DashboardLayoutManager({ dashboardType, onLayoutChange }: Omit<Props, 'colors'>) {
  const { t } = useTranslation();
  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };

  const colors = useAdminTheme();
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const { data: layoutData, loading, refetch: _loadLayout } = useLiveQuery(`/dashboard/layout/${dashboardType}`, { entity: 'dashboard_layout', pollInterval: 60000, deps: [dashboardType] });
  const [widgets, setWidgets] = useState<Widget[]>([]);
  const [isDefault, setIsDefault] = useState(true);
  const [saving, setSaving] = useState(false);
  const [editMode, setEditMode] = useState(false);

  React.useEffect(() => {
    if (layoutData) {
      setWidgets(layoutData.layout || []);
      setIsDefault(layoutData.is_default);
    }
  }, [layoutData]);

  const toggleVisibility = (id: string) => {
    setWidgets(prev => prev.map(w => w.id === id ? { ...w, visible: !w.visible } : w));
  };

  const moveWidget = (index: number, direction: 'up' | 'down') => {
    const newWidgets = [...widgets];
    const targetIdx = direction === 'up' ? index - 1 : index + 1;
    if (targetIdx < 0 || targetIdx >= newWidgets.length) return;
    [newWidgets[index], newWidgets[targetIdx]] = [newWidgets[targetIdx], newWidgets[index]];
    setWidgets(newWidgets.map((w, i) => ({ ...w, order: i })));
  };

  const saveLayout = async () => {
    setSaving(true);
    try {
      await api.post(`/dashboard/layout/${dashboardType}`, { widgets });
      setIsDefault(false);
      onLayoutChange?.(widgets);
    } catch { /* skip */ }
    setSaving(false);
    setEditMode(false);
  };

  const resetLayout = async () => {
    try {
      const res = await api.post(`/dashboard/layout/${dashboardType}/reset`);
      setWidgets(res.data.layout || []);
      setIsDefault(true);
      onLayoutChange?.(res.data.layout || []);
    } catch { /* skip */ }
    setEditMode(false);
  };

  if (loading) return <ActivityIndicator color={'var(--app-primary)'} />;

  if (!editMode) {
    return (
      <TouchableOpacity onPress={() => setEditMode(true)}
        style={{ flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 12, paddingVertical: 6, borderRadius: 8, backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border }}
        data-testid="customize-dashboard-btn" testID="customize-dashboard-btn">
        <Ionicons name="options" size={14} color={colors.textMuted} />
        <Text style={{ fontSize: 11, fontWeight: '600', color: colors.textMuted }}>{tx('admin.dashboardLayoutManager.auto.text.001', 'Customize')}</Text>
      </TouchableOpacity>
    );
  }

  return (
    <View style={{ backgroundColor: colors.surface, borderRadius: 14, padding: 16, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(colors.primary, '40'), marginBottom: 16 }} data-testid="dashboard-layout-editor" testID="dashboard-layout-editor">
      <AutoFixBanner domain="executive" />
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
          <Ionicons name="grid" size={16} color={'var(--app-primary)'} />
          <Text style={{ fontSize: 14, fontWeight: '700', color: colors.text }}>{tx('admin.dashboardLayoutManager.auto.text.002', 'Customize Dashboard')}</Text>
        </View>
        <View style={{ flexDirection: 'row', gap: 6 }}>
          {!isDefault && (
            <TouchableOpacity onPress={resetLayout} style={{ paddingHorizontal: 10, paddingVertical: 5, borderRadius: 6, backgroundColor: colors.warningSoft }} data-testid="reset-layout-btn" testID="reset-layout-btn">
              <Text style={{ fontSize: 10, fontWeight: '700', color: colors.warningText }}>{tx('admin.dashboardLayoutManager.auto.text.003', 'Reset')}</Text>
            </TouchableOpacity>
          )}
          <TouchableOpacity onPress={() => setEditMode(false)} style={{ paddingHorizontal: 10, paddingVertical: 5, borderRadius: 6, backgroundColor: colors.border }}>
            <Text style={{ fontSize: 10, fontWeight: '700', color: colors.textSec }}>{tx('admin.dashboardLayoutManager.auto.text.004', 'Cancel')}</Text>
          </TouchableOpacity>
          <TouchableOpacity onPress={saveLayout} disabled={saving} style={{ paddingHorizontal: 12, paddingVertical: 5, borderRadius: 6, backgroundColor: colors.primary }} data-testid="save-layout-btn" testID="save-layout-btn">
            <Text style={{ fontSize: 10, fontWeight: '700', color: colors.primaryText }}>{saving ? 'Saving...' : 'Save'}</Text>
          </TouchableOpacity>
        </View>
      </View>

      {widgets.map((w, i) => (
        <View key={w.id} style={{ flexDirection: 'row', alignItems: 'center', gap: 10, paddingVertical: 8, paddingHorizontal: 10, borderRadius: 8, marginBottom: 4, backgroundColor: w.visible ? 'transparent' : colors.surfaceHover, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(w.visible ? colors.border : colors.border, '60') }}
          data-testid={`widget-item-${w.id}`} testID={`widget-item-${w.id}`}>
          <View style={{ flexDirection: 'column', gap: 2 }}>
            <TouchableOpacity accessibilityLabel={tx('admin.dashboardLayoutManager.auto.accessibility.001', 'chevron up button')} onPress={() => moveWidget(i, 'up')} disabled={i === 0}
              style={{ padding: 2, opacity: i === 0 ? 0.3 : 1 }}>
              <Ionicons name="chevron-up" size={12} color={colors.textMuted} />
            </TouchableOpacity>
            <TouchableOpacity accessibilityLabel={tx('admin.dashboardLayoutManager.auto.accessibility.002', 'chevron down button')} onPress={() => moveWidget(i, 'down')} disabled={i === widgets.length - 1}
              style={{ padding: 2, opacity: i === widgets.length - 1 ? 0.3 : 1 }}>
              <Ionicons name="chevron-down" size={12} color={colors.textMuted} />
            </TouchableOpacity>
          </View>
          <TouchableOpacity accessibilityLabel={tx('admin.dashboardLayoutManager.auto.accessibility.003', 'w.title')} onPress={() => toggleVisibility(w.id)}
            style={{ width: 24, height: 24, borderRadius: 6, borderWidth: 2, borderColor: w.visible ? 'var(--app-primary)' : colors.border, backgroundColor: w.visible ? 'var(--app-primary)' : 'transparent', alignItems: 'center', justifyContent: 'center' }}>
            {w.visible && <Ionicons name="checkmark" size={14} color={colors.primaryText} />}
          </TouchableOpacity>
          <Text style={{ flex: 1, fontSize: 13, fontWeight: '600', color: w.visible ? colors.text : colors.textMuted }}>{w.title}</Text>
          <View style={{ paddingHorizontal: 6, paddingVertical: 2, borderRadius: 4, backgroundColor: colors.border }}>
            <Text style={{ fontSize: 9, fontWeight: '600', color: colors.textMuted }}>{w.size}</Text>
          </View>
        </View>
      ))}
    </View>
  );
}
