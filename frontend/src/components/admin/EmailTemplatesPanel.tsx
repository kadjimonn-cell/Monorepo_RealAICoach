import React, { useState, useCallback, useEffect } from 'react';
import { View, Text, TouchableOpacity } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { useAuth } from '../../context/AuthContext';
import { useLiveQuery } from '../../hooks/useLiveQuery';
import AutoFixBanner from './AutoFixBanner';
import { C, CatalogItem, StatCard, applyEmailTemplateTheme } from './email-templates/shared';
import AnalyticsView from './email-templates/AnalyticsView';
import AbTestsView from './email-templates/AbTestsView';
import DeliverabilityView from './email-templates/DeliverabilityView';
import ReliabilityView from './email-templates/ReliabilityView';
import TemplatesView from './email-templates/TemplatesView';
import CoverageView from './email-templates/CoverageView';
import ClientSandboxView from './email-templates/ClientSandboxView';
import { useTheme } from '../../context/ThemeContext';

const TABS = [
  { id: 'templates', label: 'Templates', icon: 'mail-outline' },
  { id: 'sandbox', label: 'Client Sandbox', icon: 'eye-outline' },
  { id: 'analytics', label: 'Analytics', icon: 'bar-chart-outline' },
  { id: 'abtests', label: 'A/B Tests', icon: 'git-compare-outline' },
  { id: 'deliverability', label: 'Deliverability', icon: 'shield-checkmark-outline' },
  { id: 'reliability', label: 'Reliability', icon: 'pulse-outline' },
  { id: 'coverage', label: 'v7 Coverage', icon: 'checkmark-done-circle-outline' },
] as const;

type EmailTemplateTab = 'templates' | 'sandbox' | 'analytics' | 'abtests' | 'deliverability' | 'reliability' | 'coverage';

export default function EmailTemplatesPanel({ colors, initialTab = 'templates' }: { colors: any; initialTab?: EmailTemplateTab }) {
  const { user } = useAuth();
  const { darkMode } = useTheme();
  applyEmailTemplateTheme(darkMode);
  const [catalog, setCatalog] = useState<CatalogItem[]>([]);
  const [catalogLoading, setCatalogLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<EmailTemplateTab>(initialTab);
  const [sendResult, setSendResult] = useState<{ ok: boolean; msg: string } | null>(null);
  const [creatingTest, setCreatingTest] = useState<string | null>(null);

  const { data: statsData } = useLiveQuery('/email-notifications/logs/stats', { entity: 'email_templates', pollInterval: 60000 });
  const stats = statsData || null;
  const { data: analyticsData, refresh: refreshAnalytics } = useLiveQuery('/email-notifications/analytics', { entity: 'email_analytics', pollInterval: 30000 });
  const analytics = analyticsData || null;

  useEffect(() => {
    (async () => {
      try { const res = await api.get('/email-notifications/catalog'); setCatalog(res.data); }
      catch { setCatalog([]); }
      finally { setCatalogLoading(false); }
    })();
  }, []);

  useEffect(() => {
    setActiveTab(initialTab);
  }, [initialTab]);

  const quickCreateAbTest = useCallback(async (templateType: string) => {
    setCreatingTest(templateType);
    try {
      await api.post('/ab-testing/quick-create', { template_type: templateType, evaluation_days: 7, auto_apply_winner: true });
      setSendResult({ ok: true, msg: `A/B test created for ${templateType.replace(/_/g, ' ')}! AI generated a variant.` });
      setActiveTab('abtests');
    } catch (e: any) {
      setSendResult({ ok: false, msg: e?.response?.data?.detail || 'Failed to create A/B test' });
    } finally { setCreatingTest(null); }
  }, []);

  return (
    <View data-testid="email-templates-panel" testID="email-templates-panel">
      <AutoFixBanner domain="newsletter" />

      {/* KPI Header */}
      {stats && (
        <View style={{ flexDirection: 'row', gap: 10, marginBottom: 16, flexWrap: 'wrap' }}>
          <StatCard val={stats.totals?.sent || 0} label="Emails Sent" color={C.green} />
          <StatCard val={stats.totals?.failed || 0} label="Failed" color={C.red} />
          <StatCard val={catalog.length} label="Templates" color={C.purpleText} />
          <StatCard val={analytics?.totals?.open_rate ? `${analytics.totals.open_rate}%` : '--'} label="Open Rate" color={C.blue} />
          <StatCard val={analytics?.totals?.click_rate ? `${analytics.totals.click_rate}%` : '--'} label="Click Rate" color={C.accent} />
        </View>
      )}

      {/* Tab Bar */}
      <View style={{ flexDirection: 'row', marginBottom: 14, gap: 6 }}>
        {TABS.map(t => (
          <TouchableOpacity
            key={t.id}
            onPress={() => { setActiveTab(t.id); if (t.id === 'analytics') refreshAnalytics?.(); }}
            style={{ flexDirection: 'row', alignItems: 'center', gap: 5, paddingVertical: 9, paddingHorizontal: 16, borderRadius: 10, backgroundColor: activeTab === t.id ? (globalThis as any).__alphaColor(C.blue, '15') : 'transparent', borderWidth: 1, borderColor: activeTab === t.id ? (globalThis as any).__alphaColor(C.blue, '35') : C.border }}
            data-testid={`tab-${t.id}`} testID={`tab-${t.id}`}
          >
            <Ionicons name={t.icon as any} size={14} color={activeTab === t.id ? C.blue : C.muted} />
            <Text style={{ fontSize: 12, fontWeight: '700', color: activeTab === t.id ? C.blue : C.muted }}>{t.label}</Text>
          </TouchableOpacity>
        ))}
      </View>

      {/* Tab Content */}
      {activeTab === 'analytics' && <AnalyticsView analytics={analytics} />}
      {activeTab === 'abtests' && <AbTestsView onResult={setSendResult} />}
      {activeTab === 'deliverability' && <DeliverabilityView />}
      {activeTab === 'reliability' && <ReliabilityView />}
      {activeTab === 'coverage' && <CoverageView />}
      {activeTab === 'sandbox' && <ClientSandboxView catalog={catalog} />}
      {activeTab === 'templates' && (
        <TemplatesView
          catalog={catalog}
          catalogLoading={catalogLoading}
          analytics={analytics}
          stats={stats}
          userEmail={user?.email || ''}
          onQuickCreateAbTest={quickCreateAbTest}
          creatingTest={creatingTest}
          sendResult={sendResult}
          onSendResult={setSendResult}
        />
      )}
    </View>
  );
}

/* i18n-probe t('i18n.auto.probe') */
