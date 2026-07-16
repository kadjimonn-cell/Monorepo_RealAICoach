import React, { useEffect, useState, useCallback } from 'react';
import { View, Text, TouchableOpacity, TextInput, ActivityIndicator, Switch } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { useLiveQuery } from '../../hooks/useLiveQuery';
import AutoFixBanner from './AutoFixBanner';

import { getAdminColors } from '../../hooks/useAdminTheme';
import { useTranslation } from '../../hooks/useTranslation';
import { useTheme } from '../../context/ThemeContext';
import { handleAppRecoverableError } from '../../utils/appRecoverableError';
function getC(dark) {
  const A = getAdminColors(dark);
  return { bg: A.bg, card: A.card, card2: A.cardSoft, border: A.border, text: A.text, muted: A.textDim, sec: A.textMuted, green: 'var(--app-success)', red: 'var(--app-error)', blue: 'var(--app-primary)', yellow: 'var(--app-warning)', purple: 'var(--app-primary)', cyan: 'var(--app-primary)', orange: 'var(--app-warning)', indigo: 'var(--app-primary)', pink: 'var(--app-primary)', lime: 'var(--app-primary)', teal: 'var(--app-primary)' };
}
const _C = getC(true);

const tx = (_key: string, fallback: string) => fallback;

const FEATURE_LABELS: Record<string, string> = {
  hiring_hub: 'AI Hiring Hub',
  mini_apps: 'AI Feature Gallery',
  leaderboard: 'Leaderboard',
  book_meeting: 'My Agenda',
  employer_portal: 'Jobs Portal',
  ai_coaching: 'AI Coaching',
  video_interviews: 'Video Interviews',
  analytics: 'Analytics',
  notifications: 'Notifications',
};

type SubTab = 'branding' | 'toggles' | 'orgs' | 'audit';

export default function WhiteLabelPanel({ colors }: { colors: any }) {
  const { t } = useTranslation();
  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };

  const { darkMode } = useTheme();
  const C = getC(darkMode);
  const { data: configData, loading: configLoading, refetch: refetchConfig } = useLiveQuery('/whitelabel/config/admin', { entity: 'whitelabel', pollInterval: 60000 });
  const { data: togglesData, refetch: refetchToggles } = useLiveQuery('/whitelabel/feature-toggles', { entity: 'whitelabel', pollInterval: 60000 });
  const { data: orgsData, refetch: refetchOrgs } = useLiveQuery('/whitelabel/organizations', { entity: 'whitelabel', pollInterval: 60000 });
  const { data: auditData } = useLiveQuery('/whitelabel/audit-log', { entity: 'whitelabel', pollInterval: 60000 });

  const [config, setConfig] = useState<any>(null);
  const [toggles, setToggles] = useState<Record<string, boolean>>({});
  const loading = configLoading;
  const [saving, setSaving] = useState(false);
  const orgs = orgsData?.organizations || [];
  const auditLogs = auditData?.logs || [];
  const [saved, setSaved] = useState(false);
  const [subTab, setSubTab] = useState<SubTab>('branding');
  const [showNewOrg, setShowNewOrg] = useState(false);
  const [newOrg, setNewOrg] = useState({ name: '', domain: '', plan: 'enterprise', max_users: '50', primary_color: colors.primary });

  useEffect(() => { if (configData) setConfig(configData); }, [configData]);
  useEffect(() => { if (togglesData) setToggles(togglesData); }, [togglesData]);

  const load = useCallback(async () => {
    await Promise.all([refetchConfig(), refetchToggles(), refetchOrgs()]);
  }, [refetchConfig, refetchToggles, refetchOrgs]);

  const updateConfig = (key: string, value: string) => {
    setConfig((c: any) => ({ ...c, [key]: value }));
  };

  const showSaved = () => { setSaved(true); setTimeout(() => setSaved(false), 3000); };

  const saveConfig = async () => {
    setSaving(true);
    try { await api.post('/whitelabel/config', config); showSaved(); } catch (error) { handleAppRecoverableError({ scope: 'src/components/admin/WhiteLabelPanel.tsx#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
    setSaving(false);
  };

  const saveToggles = async () => {
    setSaving(true);
    try { await api.post('/whitelabel/feature-toggles', toggles); showSaved(); } catch (error) { handleAppRecoverableError({ scope: 'src/components/admin/WhiteLabelPanel.tsx#catch2', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
    setSaving(false);
  };

  const createOrg = async () => {
    setSaving(true);
    try {
      await api.post('/whitelabel/organizations', { ...newOrg, max_users: parseInt(newOrg.max_users) || 50 });
      setNewOrg({ name: '', domain: '', plan: 'enterprise', max_users: '50', primary_color: colors.primary });
      setShowNewOrg(false);
      showSaved();
      load();
    } catch (error) { handleAppRecoverableError({ scope: 'src/components/admin/WhiteLabelPanel.tsx#catch3', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
    setSaving(false);
  };

  if (loading) return <ActivityIndicator style={{ padding: 30 }} color={C.blue} />;

  const tabs: { id: SubTab; label: string; icon: string }[] = [
    { id: 'branding', label: 'Branding', icon: 'color-palette' },
    { id: 'toggles', label: 'Features', icon: 'toggle' },
    { id: 'orgs', label: 'Organizations', icon: 'business' },
    { id: 'audit', label: 'Audit Log', icon: 'document-text' },
  ];

  return (
    <View data-testid="whitelabel-panel" testID="whitelabel-panel">
      <AutoFixBanner domain="whitelabel" />
      {/* Header */}
      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
        <View>
          <Text style={{ color: C.text, fontSize: 20, fontWeight: '800' }} data-testid="whitelabel-title" testID="whitelabel-title">{tx('admin.whiteLabelPanel.auto.text.001', 'White-Label Configuration')}</Text>
          <Text style={{ color: C.muted, fontSize: 12, marginTop: 4 }}>{tx('admin.whiteLabelPanel.auto.text.002', 'Branding, feature toggles, and multi-tenant management')}</Text>
        </View>
        {saved && (
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4, backgroundColor: (globalThis as any).__alphaColor(C.green, '15'), paddingHorizontal: 10, paddingVertical: 4, borderRadius: 6 }} data-testid="saved-indicator" testID="saved-indicator">
            <Ionicons name="checkmark-circle" size={14} color={C.green} />
            <Text style={{ color: C.green, fontSize: 11, fontWeight: '600' }}>{tx('admin.whiteLabelPanel.auto.text.003', 'Saved')}</Text>
          </View>
        )}
      </View>

      {/* Sub Tabs */}
      <View style={{ flexDirection: 'row', gap: 6, marginBottom: 20 }}>
        {tabs.map(t => (
          <TouchableOpacity accessibilityLabel={tx('admin.whiteLabelPanel.auto.accessibility.001', 'Switch white-label preview tab')}
            key={t.id}
            onPress={() => setSubTab(t.id)}
            style={{
              flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 14, paddingVertical: 8,
              borderRadius: 10, backgroundColor: subTab === t.id ? C.purple : C.card,
              borderWidth: 1, borderColor: subTab === t.id ? C.purple : C.border,
            }}
            data-testid={`wl-tab-${t.id}`} testID={`wl-tab-${t.id}`}
          >
            <Ionicons name={t.icon as any} size={13} color={subTab === t.id ? 'var(--app-primary-text)' : C.muted} />
            <Text style={{ color: subTab === t.id ? 'var(--app-primary-text)' : C.muted, fontSize: 12, fontWeight: '700' }}>{t.label}</Text>
          </TouchableOpacity>
        ))}
      </View>

      {/* Branding Tab */}
      {subTab === 'branding' && (
        <View>
          {/* Live Preview */}
          <View style={{ backgroundColor: C.card, borderRadius: 14, padding: 16, borderWidth: 1, borderColor: C.border, marginBottom: 16 }} data-testid="live-preview-card" testID="live-preview-card">
            <Text style={{ color: C.muted, fontSize: 10, fontWeight: '600', textTransform: 'uppercase', marginBottom: 10 }}>{tx('admin.whiteLabelPanel.auto.text.004', 'Live Preview')}</Text>
            <View style={{ backgroundColor: config?.dark_bg || 'var(--app-text)', borderRadius: 10, padding: 16, borderWidth: 1, borderColor: C.border }}>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 12 }}>
                {config?.logo_url ? (
                  <View style={{ width: 32, height: 32, borderRadius: 8, backgroundColor: (globalThis as any).__alphaColor((config?.primary_color || C.blue), '20'), alignItems: 'center', justifyContent: 'center' }}>
                    <Ionicons name="image" size={16} color={config?.primary_color || C.blue} />
                  </View>
                ) : (
                  <View style={{ width: 32, height: 32, borderRadius: 8, backgroundColor: (globalThis as any).__alphaColor((config?.primary_color || C.blue), '20'), alignItems: 'center', justifyContent: 'center' }}>
                    <Text style={{ color: config?.primary_color || C.blue, fontSize: 14, fontWeight: '800' }}>{(config?.company_name || 'R').charAt(0)}</Text>
                  </View>
                )}
                <Text style={{ color: C.text, fontSize: 16, fontWeight: '800' }}>{config?.company_name || 'RealAICoach'}</Text>
              </View>
              <View style={{ flexDirection: 'row', gap: 8, marginBottom: 8 }}>
                <View style={{ flex: 1, height: 4, borderRadius: 2, backgroundColor: config?.primary_color || C.blue }} />
                <View style={{ flex: 1, height: 4, borderRadius: 2, backgroundColor: config?.secondary_color || C.purple }} />
                <View style={{ flex: 1, height: 4, borderRadius: 2, backgroundColor: config?.accent_color || C.green }} />
              </View>
              {config?.welcome_message ? (
                <Text style={{ color: C.muted, fontSize: 11, fontStyle: 'italic' }}>{config.welcome_message}</Text>
              ) : null}
              {config?.footer_text ? (
                <Text style={{ color: C.muted + '80', fontSize: 9, marginTop: 8, textAlign: 'center' }}>{config.footer_text}</Text>
              ) : null}
            </View>
          </View>

          {/* Core Branding Fields */}
          <View style={{ backgroundColor: C.card, borderRadius: 14, padding: 16, borderWidth: 1, borderColor: C.border, marginBottom: 16 }}>
            <Text style={{ color: C.text, fontSize: 13, fontWeight: '700', marginBottom: 12 }}>{tx('admin.whiteLabelPanel.auto.text.005', 'Core Branding')}</Text>
            {[
              { key: 'company_name', label: 'Company Name', icon: 'business' },
              { key: 'logo_url', label: 'Logo URL', icon: 'image' },
              { key: 'favicon_url', label: 'Favicon URL', icon: 'link' },
              { key: 'support_email', label: 'Support Email', icon: 'mail' },
              { key: 'custom_domain', label: 'Custom Domain', icon: 'globe' },
              { key: 'welcome_message', label: 'Welcome Message', icon: 'chatbubble' },
              { key: 'footer_text', label: 'Footer Text', icon: 'document-text' },
            ].map(f => (
              <View key={f.key} style={{ marginBottom: 12 }}>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 4 }}>
                  <Ionicons name={f.icon as any} size={12} color={C.muted} />
                  <Text style={{ color: C.muted, fontSize: 10, fontWeight: '600', textTransform: 'uppercase' }}>{f.label}</Text>
                </View>
                <TextInput
                  value={config?.[f.key] || ''}
                  onChangeText={(v) => updateConfig(f.key, v)}
                  style={{ backgroundColor: C.bg, color: C.text, borderRadius: 8, padding: 10, fontSize: 12, borderWidth: 1, borderColor: C.border }}
                  placeholderTextColor={C.muted}
                  placeholder={`Enter ${f.label.toLowerCase()}...`}
                  data-testid={`wl-${f.key}`} testID={`wl-${f.key}`}
                />
              </View>
            ))}
          </View>

          {/* Theme Colors */}
          <View style={{ backgroundColor: C.card, borderRadius: 14, padding: 16, borderWidth: 1, borderColor: C.border, marginBottom: 16 }}>
            <Text style={{ color: C.text, fontSize: 13, fontWeight: '700', marginBottom: 12 }}>{tx('admin.whiteLabelPanel.auto.text.006', 'Theme Colors')}</Text>
            <View style={{ flexDirection: 'row', gap: 8, flexWrap: 'wrap', marginBottom: 12 }}>
              {[
                { key: 'primary_color', label: 'Primary' },
                { key: 'secondary_color', label: 'Secondary' },
                { key: 'accent_color', label: 'Accent' },
                { key: 'dark_bg', label: 'Dark Background' },
                { key: 'dark_card', label: 'Dark Card' },
              ].map(c => (
                <View key={c.key} style={{ flex: 1, minWidth: 120 }}>
                  <Text style={{ color: C.muted, fontSize: 9, marginBottom: 4 }}>{c.label}</Text>
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                    <View style={{ width: 24, height: 24, borderRadius: 6, backgroundColor: config?.[c.key] || C.blue, borderWidth: 1, borderColor: C.border }} />
                    <TextInput accessibilityLabel={tx('admin.whiteLabelPanel.auto.accessibility.002', 'Text input')}
                      value={config?.[c.key] || ''}
                      onChangeText={(v) => updateConfig(c.key, v)}
                      style={{ flex: 1, backgroundColor: C.bg, color: C.text, borderRadius: 6, padding: 6, fontSize: 11, borderWidth: 1, borderColor: C.border, fontFamily: 'monospace' }}
                      data-testid={`wl-color-${c.key}`} testID={`wl-color-${c.key}`}
                    />
                  </View>
                </View>
              ))}
            </View>
          </View>

          {/* Advanced Settings */}
          <View style={{ backgroundColor: C.card, borderRadius: 14, padding: 16, borderWidth: 1, borderColor: C.border, marginBottom: 16 }}>
            <Text style={{ color: C.text, fontSize: 13, fontWeight: '700', marginBottom: 12 }}>{tx('admin.whiteLabelPanel.auto.text.007', 'Advanced Settings')}</Text>
            {[
              { key: 'font_family', label: 'Font Family', icon: 'text', placeholder: 'system-ui, sans-serif' },
              { key: 'privacy_url', label: 'Privacy Policy URL', icon: 'shield-checkmark', placeholder: 'https://...' },
              { key: 'terms_url', label: 'Terms of Service URL', icon: 'document', placeholder: 'https://...' },
            ].map(f => (
              <View key={f.key} style={{ marginBottom: 12 }}>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 4 }}>
                  <Ionicons name={f.icon as any} size={12} color={C.muted} />
                  <Text style={{ color: C.muted, fontSize: 10, fontWeight: '600', textTransform: 'uppercase' }}>{f.label}</Text>
                </View>
                <TextInput
                  value={config?.[f.key] || ''}
                  onChangeText={(v) => updateConfig(f.key, v)}
                  style={{ backgroundColor: C.bg, color: C.text, borderRadius: 8, padding: 10, fontSize: 12, borderWidth: 1, borderColor: C.border }}
                  placeholderTextColor={C.muted}
                  placeholder={f.placeholder}
                  data-testid={`wl-${f.key}`} testID={`wl-${f.key}`}
                />
              </View>
            ))}
            <View style={{ marginBottom: 12 }}>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 4 }}>
                <Ionicons name="code-slash" size={12} color={C.muted} />
                <Text style={{ color: C.muted, fontSize: 10, fontWeight: '600', textTransform: 'uppercase' }}>{tx('admin.whiteLabelPanel.auto.text.008', 'Custom CSS')}</Text>
              </View>
              <TextInput accessibilityLabel={tx('admin.whiteLabelPanel.auto.accessibility.003', '.custom-class { color: var(--app-primary-text); }')}
                value={config?.custom_css || ''}
                onChangeText={(v) => updateConfig('custom_css', v)}
                multiline
                numberOfLines={4}
                style={{ backgroundColor: C.bg, color: C.cyan, borderRadius: 8, padding: 10, fontSize: 11, borderWidth: 1, borderColor: C.border, fontFamily: 'monospace', minHeight: 80, textAlignVertical: 'top' }}
                placeholderTextColor={C.muted}
                placeholder={tx('admin.whiteLabelPanel.auto.placeholder.001', '.custom-class { color: var(--app-primary-text); }')}
                data-testid="wl-custom_css" testID="wl-custom_css"
              />
            </View>
          </View>

          <TouchableOpacity onPress={saveConfig} disabled={saving} style={{ backgroundColor: C.blue, borderRadius: 10, paddingVertical: 12, alignItems: 'center', opacity: saving ? 0.6 : 1 }} data-testid="save-branding-btn" testID="save-branding-btn">
            <Text style={{ color: colors.primaryText, fontSize: 13, fontWeight: '700' }}>{saving ? 'Saving...' : 'Save All Branding'}</Text>
          </TouchableOpacity>
        </View>
      )}

      {/* Feature Toggles Tab */}
      {subTab === 'toggles' && (
        <View style={{ backgroundColor: C.card, borderRadius: 14, padding: 16, borderWidth: 1, borderColor: C.border }}>
          <Text style={{ color: C.text, fontSize: 13, fontWeight: '700', marginBottom: 4 }}>{tx('admin.whiteLabelPanel.auto.text.009', 'Feature Toggles')}</Text>
          <Text style={{ color: C.muted, fontSize: 11, marginBottom: 16 }}>{tx('admin.whiteLabelPanel.auto.text.010', 'Enable or disable features for all users across the platform.')}</Text>
          {Object.entries(FEATURE_LABELS).map(([key, label]) => (
            <View key={key} style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: C.border }} data-testid={`toggle-row-${key}`} testID={`toggle-row-${key}`}>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: toggles[key] !== false ? C.green : C.red }} />
                <Text style={{ color: C.text, fontSize: 12, fontWeight: '600' }}>{label}</Text>
              </View>
              <Switch
                value={toggles[key] !== false}
                onValueChange={(v) => setToggles(t => ({ ...t, [key]: v }))}
                trackColor={{ false: C.border, true: C.green + '40' }}
                thumbColor={toggles[key] !== false ? C.green : C.muted}
                data-testid={`toggle-${key}`} testID={`toggle-${key}`}
              />
            </View>
          ))}
          <TouchableOpacity onPress={saveToggles} disabled={saving} style={{ backgroundColor: C.purple, borderRadius: 10, paddingVertical: 12, alignItems: 'center', marginTop: 16, opacity: saving ? 0.6 : 1 }} data-testid="save-toggles-btn" testID="save-toggles-btn">
            <Text style={{ color: colors.primaryText, fontSize: 13, fontWeight: '700' }}>{saving ? 'Saving...' : 'Save Feature Toggles'}</Text>
          </TouchableOpacity>
        </View>
      )}

      {/* Organizations Tab */}
      {subTab === 'orgs' && (
        <View>
          <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
            <Text style={{ color: C.text, fontSize: 13, fontWeight: '700' }}>Organizations ({orgs.length})</Text>
            <TouchableOpacity onPress={() => setShowNewOrg(!showNewOrg)} style={{ flexDirection: 'row', alignItems: 'center', gap: 4, paddingHorizontal: 12, paddingVertical: 6, borderRadius: 8, backgroundColor: showNewOrg ? (globalThis as any).__alphaColor(C.red, '20') : C.blue }} data-testid="toggle-new-org-btn" testID="toggle-new-org-btn">
              <Ionicons name={showNewOrg ? 'close' : 'add'} size={14} color={showNewOrg ? C.red : 'var(--app-primary-text)'} />
              <Text style={{ color: showNewOrg ? C.red : 'var(--app-primary-text)', fontSize: 11, fontWeight: '700' }}>{showNewOrg ? 'Cancel' : 'New Org'}</Text>
            </TouchableOpacity>
          </View>

          {/* New Org Form */}
          {showNewOrg && (
            <View style={{ backgroundColor: C.card, borderRadius: 14, padding: 16, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(C.blue, '40'), marginBottom: 16 }} data-testid="new-org-form" testID="new-org-form">
              <Text style={{ color: C.blue, fontSize: 12, fontWeight: '700', marginBottom: 12 }}>{tx('admin.whiteLabelPanel.auto.text.011', 'Create Organization')}</Text>
              {[
                { key: 'name', label: 'Organization Name', placeholder: 'Acme Corp' },
                { key: 'domain', label: 'Domain', placeholder: 'acme.realaicoach.app' },
                { key: 'primary_color', label: 'Brand Color', placeholder: 'var(--app-primary)' },
                { key: 'max_users', label: 'Max Users', placeholder: '50' },
              ].map(f => (
                <View key={f.key} style={{ marginBottom: 10 }}>
                  <Text style={{ color: C.muted, fontSize: 10, fontWeight: '600', marginBottom: 4 }}>{f.label}</Text>
                  <TextInput
                    value={(newOrg as any)[f.key]}
                    onChangeText={(v) => setNewOrg(o => ({ ...o, [f.key]: v }))}
                    style={{ backgroundColor: C.bg, color: C.text, borderRadius: 8, padding: 10, fontSize: 12, borderWidth: 1, borderColor: C.border }}
                    placeholderTextColor={C.muted}
                    placeholder={f.placeholder}
                    data-testid={`new-org-${f.key}`} testID={`new-org-${f.key}`}
                  />
                </View>
              ))}
              <View style={{ marginBottom: 10 }}>
                <Text style={{ color: C.muted, fontSize: 10, fontWeight: '600', marginBottom: 4 }}>{tx('admin.whiteLabelPanel.auto.text.012', 'Plan')}</Text>
                <View style={{ flexDirection: 'row', gap: 6 }}>
                  {['starter', 'professional', 'enterprise'].map(p => (
                    <TouchableOpacity key={p} onPress={() => setNewOrg(o => ({ ...o, plan: p }))} style={{ flex: 1, paddingVertical: 8, borderRadius: 8, backgroundColor: newOrg.plan === p ? C.blue : C.bg, borderWidth: 1, borderColor: newOrg.plan === p ? C.blue : C.border, alignItems: 'center' }} data-testid={`plan-${p}`} testID={`plan-${p}`}>
                      <Text style={{ color: newOrg.plan === p ? 'var(--app-primary-text)' : C.muted, fontSize: 11, fontWeight: '600', textTransform: 'capitalize' }}>{p}</Text>
                    </TouchableOpacity>
                  ))}
                </View>
              </View>
              <TouchableOpacity onPress={createOrg} disabled={saving || !newOrg.name} style={{ backgroundColor: C.green, borderRadius: 10, paddingVertical: 12, alignItems: 'center', opacity: (saving || !newOrg.name) ? 0.5 : 1 }} data-testid="create-org-btn" testID="create-org-btn">
                <Text style={{ color: colors.primaryText, fontSize: 13, fontWeight: '700' }}>{saving ? 'Creating...' : 'Create Organization'}</Text>
              </TouchableOpacity>
            </View>
          )}

          {/* Org List */}
          {orgs.length === 0 ? (
            <View style={{ backgroundColor: C.card, borderRadius: 14, padding: 24, borderWidth: 1, borderColor: C.border, alignItems: 'center' }}>
              <Ionicons name="business-outline" size={32} color={C.muted} />
              <Text style={{ color: C.muted, fontSize: 12, marginTop: 8, textAlign: 'center' }}>{tx('admin.whiteLabelPanel.auto.text.013', 'No organizations yet. Create one to enable multi-tenant white-labeling.')}</Text>
            </View>
          ) : (
            <View style={{ gap: 8 }}>
              {orgs.map(o => (
                <View key={o.org_id} style={{ flexDirection: 'row', alignItems: 'center', gap: 12, padding: 14, backgroundColor: C.card, borderRadius: 12, borderWidth: 1, borderColor: C.border }} data-testid={`org-${o.org_id}`} testID={`org-${o.org_id}`}>
                  <View style={{ width: 40, height: 40, borderRadius: 10, backgroundColor: (globalThis as any).__alphaColor((o.primary_color || C.blue), '20'), alignItems: 'center', justifyContent: 'center' }}>
                    <Ionicons name="business" size={18} color={o.primary_color || C.blue} />
                  </View>
                  <View style={{ flex: 1 }}>
                    <Text style={{ color: C.text, fontSize: 13, fontWeight: '700' }}>{o.name}</Text>
                    <Text style={{ color: C.muted, fontSize: 10, marginTop: 2 }}>
                      {o.domain || 'No domain'} | {o.plan} | Max {o.max_users} users
                    </Text>
                  </View>
                  <View style={{ backgroundColor: o.status === 'active' ? (globalThis as any).__alphaColor(C.green, '15') : C.red + '15', paddingHorizontal: 10, paddingVertical: 4, borderRadius: 6 }}>
                    <Text style={{ color: o.status === 'active' ? C.green : C.red, fontSize: 10, fontWeight: '700', textTransform: 'uppercase' }}>{o.status}</Text>
                  </View>
                </View>
              ))}
            </View>
          )}
        </View>
      )}

      {/* Audit Log Tab */}
      {subTab === 'audit' && (
        <View>
          <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
            <Text style={{ color: C.text, fontSize: 13, fontWeight: '700' }}>{tx('admin.whiteLabelPanel.auto.text.014', 'Configuration Change Log')}</Text>
            <TouchableOpacity onPress={load} style={{ flexDirection: 'row', alignItems: 'center', gap: 4, paddingHorizontal: 10, paddingVertical: 6, borderRadius: 8, backgroundColor: C.card, borderWidth: 1, borderColor: C.border }} data-testid="refresh-audit-btn" testID="refresh-audit-btn">
              <Ionicons name="refresh" size={12} color={C.muted} />
              <Text style={{ color: C.muted, fontSize: 10, fontWeight: '600' }}>{tx('admin.whiteLabelPanel.auto.text.015', 'Refresh')}</Text>
            </TouchableOpacity>
          </View>
          {auditLogs.length === 0 ? (
            <View style={{ backgroundColor: C.card, borderRadius: 14, padding: 24, borderWidth: 1, borderColor: C.border, alignItems: 'center' }}>
              <Ionicons name="document-text-outline" size={32} color={C.muted} />
              <Text style={{ color: C.muted, fontSize: 12, marginTop: 8 }}>{tx('admin.whiteLabelPanel.auto.text.016', 'No configuration changes recorded yet.')}</Text>
            </View>
          ) : (
            <View style={{ gap: 8 }}>
              {auditLogs.map((log, i) => {
                const changes = log.changes ? Object.keys(log.changes) : [];
                const time = log.created_at ? new Date(log.created_at).toLocaleString() : '';
                return (
                  <View key={log.audit_id || i} style={{ backgroundColor: C.card, borderRadius: 12, padding: 14, borderWidth: 1, borderColor: C.border }} data-testid={`audit-log-${i}`} testID={`audit-log-${i}`}>
                    <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 6 }}>
                      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                        <Ionicons name="person-circle" size={16} color={C.blue} />
                        <Text style={{ color: C.text, fontSize: 12, fontWeight: '600' }}>{log.changed_by_name || 'Admin'}</Text>
                      </View>
                      <Text style={{ color: C.muted, fontSize: 10 }}>{time}</Text>
                    </View>
                    {changes.length > 0 && (
                      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 4 }}>
                        {changes.map(c => (
                          <View key={c} style={{ backgroundColor: (globalThis as any).__alphaColor(C.purple, '15'), paddingHorizontal: 8, paddingVertical: 2, borderRadius: 4 }}>
                            <Text style={{ color: C.purpleText, fontSize: 9, fontWeight: '600' }}>{c}</Text>
                          </View>
                        ))}
                      </View>
                    )}
                  </View>
                );
              })}
            </View>
          )}
        </View>
      )}
    </View>
  );
}
