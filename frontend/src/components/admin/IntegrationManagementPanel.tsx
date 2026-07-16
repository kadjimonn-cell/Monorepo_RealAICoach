import React, { useEffect, useState } from 'react';
// @gls-exempt — intentional fixed-width UI element (sidebar/chat/label/toast)
import { View, Text, TouchableOpacity, ActivityIndicator, Switch, TextInput, useWindowDimensions } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { useExecTheme, useExecStyles } from './ExecDashboardPanels';
import { useLiveQuery } from '../../hooks/useLiveQuery';
import AutoFixBanner from './AutoFixBanner';
import { useAdminTheme } from '../../hooks/useAdminTheme';
import { useTranslation } from '../../hooks/useTranslation';

export default function IntegrationManagementPanel() {
  const s = useExecStyles();
  const colors = useAdminTheme();
  const { t } = useTranslation();
  const tx = React.useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);
  const INTEGRATIONS = [
    { id: 'google_calendar', name: 'Google Calendar', icon: 'calendar', color: 'var(--app-primary)', category: 'Productivity', description: 'Sync meetings and events' }, // @theme-ok brand identifier
    { id: 'google_drive', name: 'Google Drive', icon: 'cloud', color: 'var(--app-primary)', category: 'Storage', description: 'File storage and sharing' }, // @theme-ok brand identifier
    { id: 'slack', name: 'Slack', icon: 'chatbubbles', color: 'var(--app-primary)', category: 'Communication', description: 'Team messaging and notifications' }, // @theme-ok brand identifier
    { id: 'zoom', name: 'Zoom', icon: 'videocam', color: 'var(--app-primary)', category: 'Communication', description: 'Video conferencing' }, // @theme-ok brand identifier
    { id: 'stripe', name: 'Stripe', icon: 'card', color: colors.primary, category: 'Payments', description: 'Credit card payments' },
    { id: 'paypal', name: 'PayPal', icon: 'wallet', color: 'var(--app-primary)', category: 'Payments', description: 'Online payments' }, // @theme-ok brand identifier
    { id: 'fedapay', name: 'FedaPay', icon: 'phone-portrait', color: 'var(--app-primary)', category: 'Payments', description: 'Mobile money payments' }, // @theme-ok brand identifier
    { id: 'sendgrid', name: 'SendGrid', icon: 'mail', color: 'var(--app-primary)', category: 'Email', description: 'Transactional emails' }, // @theme-ok brand identifier
    { id: 'resend', name: 'Resend', icon: 'mail', color: 'var(--app-text)', category: 'Email', description: 'Email delivery service' }, // @theme-ok brand identifier
    { id: 'twilio', name: 'Twilio', icon: 'call', color: 'var(--app-primary)', category: 'SMS', description: 'SMS and voice' }, // @theme-ok brand identifier
    { id: 'openai', name: 'OpenAI', icon: 'sparkles', color: 'var(--app-primary)', category: 'AI', description: 'AI language models' }, // @theme-ok brand identifier
    { id: 'webhook', name: 'Webhooks', icon: 'git-branch', color: colors.warningText || colors.warning, category: 'Developer', description: 'Event notifications' },
  ];
  const T = useExecTheme();
  const { data: config, loading, refetch } = useLiveQuery('/config/global', { entity: 'config' });
  const { width } = useWindowDimensions();
  const isMobile = width < 900;
  const [filter, setFilter] = useState('all');
  const [search, setSearch] = useState('');
  const [toggling, setToggling] = useState<string | null>(null);
  const [localConfig, setLocalConfig] = useState<any>(null);

  useEffect(() => {
    if (config) setLocalConfig(config);
  }, [config]);

  const isEnabled = (id: string) => localConfig?.integrations?.[id]?.enabled ?? localConfig?.features?.[id] ?? true;

  const handleToggle = async (id: string, value: boolean) => {
    setToggling(id);
    try {
      await api.post('/config/admin/update', { [`integrations.${id}.enabled`]: value });
      setLocalConfig((prev: any) => ({
        ...prev,
        integrations: { ...(prev?.integrations || {}), [id]: { ...(prev?.integrations?.[id] || {}), enabled: value } },
      }));
      await refetch();
    } catch (e) { console.error(e); }
    finally { setToggling(null); }
  };

  const categories = ['all', ...new Set(INTEGRATIONS.map(i => i.category))];
  const filtered = INTEGRATIONS
    .filter(i => filter === 'all' || i.category === filter)
    .filter(i => !search || i.name.toLowerCase().includes(search.toLowerCase()) || i.category.toLowerCase().includes(search.toLowerCase()));

  const activeCount = INTEGRATIONS.filter(i => isEnabled(i.id)).length;

  const kpis = [
    { label: 'Total Integrations', value: INTEGRATIONS.length, icon: 'git-network', color: T.primary },
    { label: 'Active', value: activeCount, icon: 'checkmark-circle', color: T.successText },
    { label: 'Inactive', value: INTEGRATIONS.length - activeCount, icon: 'pause-circle', color: T.textMuted },
    { label: 'Categories', value: new Set(INTEGRATIONS.map(i => i.category)).size, icon: 'apps', color: T.cyan },
  ];

  if (loading) return <View style={{ padding: 40, alignItems: 'center' }}><ActivityIndicator size="large" color={T.primary} /></View>;

  return (
    <View style={s.panel} data-testid="integration-mgmt-panel" testID="integration-mgmt-panel">
      <AutoFixBanner domain="integration" />
      {/* KPI Row */}
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 12, marginBottom: 20 }}>
        {kpis.map((k, i) => (
          <View key={i} style={[s.kpiCard, { flex: 1, minWidth: isMobile ? 140 : 180, borderLeftColor: k.color, borderLeftWidth: 3 }]}> 
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
              <Ionicons name={k.icon as any} size={18} color={k.color} />
              <Text style={{ color: T.textSec, fontSize: 12, fontWeight: '600', textTransform: 'uppercase' }}>{k.label}</Text>
            </View>
            <Text style={{ color: T.text, fontSize: 28, fontWeight: '700', marginTop: 6 }}>{k.value}</Text>
          </View>
        ))}
      </View>

      {/* Category Filters + Search */}
      <View style={{ flexDirection: 'row', gap: 8, marginBottom: 16, flexWrap: 'wrap', alignItems: 'center' }}>
        {categories.map(c => (
          <TouchableOpacity key={c} onPress={() => setFilter(c)}
            style={{ paddingHorizontal: 14, paddingVertical: 7, borderRadius: 20, backgroundColor: filter === c ? T.primary : T.card, borderWidth: 1, borderColor: filter === c ? T.primary : T.border }}
            data-testid={`intg-filter-${c}`} testID={`intg-filter-${c}`}>
            <Text style={{ color: filter === c ? T.primaryText : T.textSec, fontSize: 13, fontWeight: '600', textTransform: 'capitalize' }}>{c}</Text>
          </TouchableOpacity>
        ))}
        <TextInput placeholder={tx('admin.integrationManagement.searchPlaceholder', 'Search integrations...')} placeholderTextColor={T.textMuted} value={search} onChangeText={setSearch}
          style={{ marginLeft: isMobile ? 0 : 'auto', width: isMobile ? '100%' : undefined, backgroundColor: T.card, borderWidth: 1, borderColor: T.border, borderRadius: 8, paddingHorizontal: 12, paddingVertical: 6, color: T.text, fontSize: 12, minWidth: isMobile ? undefined : 180 } as any}
          data-testid="intg-search-input" testID="intg-search-input" />
      </View>

      {/* Integration Cards */}
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 12 }}>
        {filtered.map((intg) => {
          const enabled = isEnabled(intg.id);
          return (
            <View key={intg.id} style={{ backgroundColor: T.card, borderRadius: 12, borderWidth: 1, borderColor: enabled ? (globalThis as any).__alphaColor(intg.color, '30') : T.border, padding: 16, width: isMobile ? '100%' : 280, opacity: enabled ? 1 : 0.7 }}
              data-testid={`intg-card-${intg.id}`} testID={`intg-card-${intg.id}`}>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 12 }}>
                <View style={{ width: 42, height: 42, borderRadius: 10, backgroundColor: (globalThis as any).__alphaColor(intg.color, '20'), alignItems: 'center', justifyContent: 'center' }}>
                  <Ionicons name={intg.icon as any} size={20} color={intg.color} />
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={{ color: T.text, fontSize: 14, fontWeight: '700' }}>{intg.name}</Text>
                  <Text style={{ color: T.textMuted, fontSize: 11 }}>{intg.category}</Text>
                </View>
                <Switch
                  value={enabled}
                  onValueChange={(v) => handleToggle(intg.id, v)}
                  disabled={toggling === intg.id}
                  trackColor={{ false: T.border, true: intg.color + '60' }}
                  thumbColor={enabled ? intg.color : T.textMuted}
                  data-testid={`intg-toggle-${intg.id}`} testID={`intg-toggle-${intg.id}`}
                />
              </View>
              <Text style={{ color: T.textMuted, fontSize: 12, marginTop: 8, lineHeight: 16 }}>{intg.description}</Text>
              <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginTop: 10, paddingTop: 10, borderTopWidth: 1, borderTopColor: T.border }}>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}>
                  <View style={{ width: 6, height: 6, borderRadius: 3, backgroundColor: enabled ? T.success : T.textMuted }} />
                  <Text style={{ color: enabled ? T.success : T.textMuted, fontSize: 11, fontWeight: '600' }}>{enabled ? 'Active' : 'Disabled'}</Text>
                </View>
              </View>
            </View>
          );
        })}
      </View>
    </View>
  );
}
