import React, { useState, Suspense, lazy, useCallback } from 'react';
import { View, Text, TouchableOpacity, ActivityIndicator } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useExecTheme} from './ExecDashboardPanels';
import api from '../../services/api';
import { useAdminTheme } from '../../hooks/useAdminTheme';
import { useTranslation } from '../../hooks/useTranslation';
import { useHybridPolling } from '../../hooks/useHybridPolling';

const SupportTicketPanel = lazy(() => import('./SupportTicketsPanel'));
const TicketEmailPanel = lazy(() => import('./TicketEmailPanel'));
const ContactSubmissionsPanel = lazy(() => import('./ContactSubmissionsPanel'));

type Tab = 'tickets' | 'email' | 'contact-submissions';

const TABS: { id: Tab; label: string; icon: string; desc: string }[] = [
  { id: 'tickets', label: 'Ticket Management', icon: 'chatbox-ellipses', desc: 'View, reply, escalate & manage all support tickets' },
  { id: 'email', label: 'Email & AI Routing', icon: 'mail', desc: 'Email config, templates, AI classification & routing rules' },
  { id: 'contact-submissions', label: 'Contact Submissions', icon: 'mail-open', desc: 'Guest/public contact form submissions sent to support' },
];

function Fallback() {
  const T = useExecTheme();
  const { t } = useTranslation();
  const tx = React.useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);
  return (
    <View style={{ padding: 40, alignItems: 'center' }}>
      <ActivityIndicator size="large" color={T.primary} />
      <Text style={{ color: T.textMuted, marginTop: 10, fontSize: 12 }}>{tx('admin.unifiedSupportPanel.states.loading', 'Loading...')}</Text>
    </View>
  );
}

export default function UnifiedSupportPanel() {
  const colors = useAdminTheme();
  const T = useExecTheme();
  const { t } = useTranslation();
  const tx = React.useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);
  const [activeTab, setActiveTab] = useState<Tab>('tickets');
  const [contactStats, setContactStats] = useState<{ new?: number } | null>(null);

  const loadStats = useCallback(async () => {
    try {
      const response = await api.get('/contact/submissions?status=all&limit=1');
      setContactStats(response.data?.stats || null);
    } catch {
      setContactStats(null);
    }
  }, []);

  useHybridPolling({
    enabled: true,
    errorScope: 'admin/unified-support/contact-stats-hybrid',
    onTick: loadStats,
    runOnMount: true,
    slowIntervalMs: 90000,
    fastIntervalMs: 30000,
  });

  return (
    <View data-testid="unified-support-panel" testID="unified-support-panel">
      {/* Header */}
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 14, marginBottom: 20 }}>
        <View style={{ width: 48, height: 48, borderRadius: 14, backgroundColor: (globalThis as any).__alphaColor(T.primary, '12'), alignItems: 'center', justifyContent: 'center', borderWidth: 1, borderColor: (globalThis as any).__alphaColor(T.primary, '25') }}>
          <Ionicons name="headset" size={24} color={T.primary} />
        </View>
        <View style={{ flex: 1 }}>
          <Text style={{ color: T.text, fontSize: 22, fontWeight: '800', letterSpacing: -0.5 }} data-testid="unified-support-title" testID="unified-support-title">{tx('admin.unifiedSupportPanel.header.title', 'Support & Tickets')}</Text>
          <Text style={{ color: T.textMuted, fontSize: 12, marginTop: 2 }}>{tx('admin.unifiedSupportPanel.header.subtitle', 'Unified ticket management, contact inbox, email configuration & AI routing')}</Text>
        </View>
      </View>

      {/* Tab Bar */}
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginBottom: 20 }}>
        {TABS.map(tab => {
          const isActive = activeTab === tab.id;
          return (
            <TouchableOpacity accessibilityLabel="Set active tab in unified support panel"
              key={tab.id}
              onPress={() => setActiveTab(tab.id)}
              style={{
                flexGrow: 1,
                flexBasis: 220,
                flexDirection: 'row',
                alignItems: 'center',
                gap: 10,
                paddingVertical: 14,
                paddingHorizontal: 16,
                borderRadius: 12,
                backgroundColor: isActive ? (globalThis as any).__alphaColor(T.primary, '12') : T.card,
                borderWidth: 1,
                borderColor: isActive ? (globalThis as any).__alphaColor(T.primary, '35') : T.border,
              }}
              data-testid={`support-tab-${tab.id}`} testID={`support-tab-${tab.id}`}
            >
              <View style={{
                width: 36, height: 36, borderRadius: 10,
                backgroundColor: isActive ? (globalThis as any).__alphaColor(T.primary, '20') : T.border + '40',
                alignItems: 'center', justifyContent: 'center',
              }}>
                <Ionicons name={tab.icon as any} size={18} color={isActive ? T.primary : T.textMuted} />
              </View>
              <View style={{ flex: 1 }}>
                <Text style={{ color: isActive ? T.primary : T.text, fontSize: 13, fontWeight: '700' }}>{tab.label}</Text>
                <Text style={{ color: T.textMuted, fontSize: 10, marginTop: 2 }} numberOfLines={1}>{tab.desc}</Text>
              </View>
              {tab.id === 'contact-submissions' && (contactStats?.new || 0) > 0 && (
                <View style={{ minWidth: 24, height: 24, borderRadius: 999, backgroundColor: colors.error, alignItems: 'center', justifyContent: 'center', paddingHorizontal: 7 }} data-testid="support-tab-contact-submissions-badge" testID="support-tab-contact-submissions-badge">
                  <Text style={{ color: colors.text, fontSize: 11, fontWeight: '800' }}>{contactStats?.new}</Text>
                </View>
              )}
              {isActive && (
                <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: T.primary }} />
              )}
            </TouchableOpacity>
          );
        })}
      </View>

      {/* Panel Content */}
      <Suspense fallback={<Fallback />}>
        {activeTab === 'tickets' && <SupportTicketPanel colors={T} />}
        {activeTab === 'email' && <TicketEmailPanel colors={T} />}
        {activeTab === 'contact-submissions' && <ContactSubmissionsPanel colors={T} />}
      </Suspense>
    </View>
  );
}
