import React, { useState, useCallback, useEffect, useMemo } from 'react';
import { View, Text, TouchableOpacity, ActivityIndicator, ScrollView, Platform, useWindowDimensions } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../../services/api';
import { C, CatalogItem, RateBar } from './shared';
import { useTranslation } from '../../../hooks/useTranslation';

interface ClientPreview {
  client: string;
  name: string;
  platform: string;
  dark_mode_support: string;
  method: string;
  notes: string;
  market_share: number;
  html: string;
}

interface CompatResult {
  key: string;
  label: string;
  category: string;
  compatibility: Record<string, { score: number; status: string; issues: string[] }>;
}

interface CompatReport {
  summary: { overall_score: number; overall_grade: string; clients_tested: number; templates_tested: number };
  clients: Record<string, { name: string; platform: string; avg_score: number; grade: string; templates_tested: number; market_share: number }>;
  results: CompatResult[];
}

const CLIENT_ICONS: Record<string, string> = {
  apple_mail: 'logo-apple',
  gmail_web: 'mail',
  gmail_mobile: 'phone-portrait',
  outlook_desktop: 'desktop',
  outlook_web: 'globe',
  yahoo_mail: 'at',
  thunderbird: 'thunderstorm',
};

const SUPPORT_COLORS: Record<string, string> = {
  full: 'var(--app-success)', // @theme-ok brand/role/state identifier
  partial: 'var(--app-warning)', // @theme-ok brand/role/state identifier
  limited: 'var(--app-error)', // @theme-ok brand/role/state identifier
};

const GRADE_COLORS: Record<string, string> = {
  A: 'var(--app-success)', // @theme-ok brand/role/state identifier
  B: 'var(--app-primary)', // @theme-ok brand/role/state identifier
  C: 'var(--app-warning)', // @theme-ok brand/role/state identifier
  D: 'var(--app-error)', // @theme-ok brand/role/state identifier
  F: 'var(--app-error)', // @theme-ok brand/role/state identifier
};

interface Props {
  catalog: CatalogItem[];
}

export default function ClientSandboxView({ catalog }: Props) {
  const { t } = useTranslation();
  const tx = useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);
  const { width } = useWindowDimensions();
  const [tab, setTab] = useState<'sandbox' | 'compat'>('sandbox');
  const [selectedTemplate, setSelectedTemplate] = useState<string | null>(null);
  const [selectedClient, setSelectedClient] = useState<string>('apple_mail');
  const [allClientsMode, setAllClientsMode] = useState(false);
  const [previewHtml, setPreviewHtml] = useState('');
  const [allPreviews, setAllPreviews] = useState<ClientPreview[]>([]);
  const [loading, setLoading] = useState(false);
  const [clientInfo, setClientInfo] = useState<any>(null);

  const [compatReport, setCompatReport] = useState<CompatReport | null>(null);
  const [compatLoading, setCompatLoading] = useState(false);
  const [compatFilter, setCompatFilter] = useState<string | null>(null);

  const loadSinglePreview = useCallback(async (templateKey: string, client: string) => {
    setLoading(true);
    setPreviewHtml('');
    setAllPreviews([]);
    setAllClientsMode(false);
    try {
      const res = await api.get(`/email-notifications/preview/${templateKey}/client-sandbox?client=${client}`);
      setPreviewHtml(res.data.html);
      setClientInfo(res.data);
    } catch {
      setPreviewHtml('<p style="color:red;padding:20px;">Failed to load preview</p>');
    } finally {
      setLoading(false);
    }
  }, []);

  const loadAllPreviews = useCallback(async (templateKey: string) => {
    setLoading(true);
    setPreviewHtml('');
    setAllPreviews([]);
    setAllClientsMode(true);
    try {
      const res = await api.get(`/email-notifications/preview/${templateKey}/client-sandbox/all`);
      setAllPreviews(res.data.clients || []);
    } catch {
      setAllPreviews([]);
    } finally {
      setLoading(false);
    }
  }, []);

  const loadCompatReport = useCallback(async () => {
    setCompatLoading(true);
    try {
      const res = await api.get('/email-notifications/templates/client-compatibility');
      setCompatReport(res.data);
    } catch {
      setCompatReport(null);
    } finally {
      setCompatLoading(false);
    }
  }, []);

  useEffect(() => {
    if (selectedTemplate && !allClientsMode) {
      loadSinglePreview(selectedTemplate, selectedClient);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedClient]);

  const filteredCompat = useMemo(() => {
    if (!compatReport?.results) return [];
    if (!compatFilter) return compatReport.results;
    return compatReport.results.filter(r => {
      const compat = r.compatibility[compatFilter];
      return compat && compat.issues.length > 0;
    });
  }, [compatReport, compatFilter]);

  const clients = [
    { id: 'apple_mail', name: 'Apple Mail' },
    { id: 'gmail_web', name: 'Gmail' },
    { id: 'gmail_mobile', name: 'Gmail Mobile' },
    { id: 'outlook_desktop', name: 'Outlook' },
    { id: 'outlook_web', name: 'Outlook.com' },
    { id: 'yahoo_mail', name: 'Yahoo' },
    { id: 'thunderbird', name: 'Thunderbird' },
  ];

  const galleryCols = width > 1200 ? 3 : width > 800 ? 2 : 1;

  return (
    <View style={{ gap: 16 }} data-testid="client-sandbox-view">
      {/* Sub-tabs */}
      <View style={{ flexDirection: 'row', gap: 8 }}>
        <TouchableOpacity
          onPress={() => setTab('sandbox')}
          style={{ flexDirection: 'row', alignItems: 'center', gap: 6, paddingVertical: 8, paddingHorizontal: 16, borderRadius: 10, backgroundColor: tab === 'sandbox' ? (globalThis as any).__alphaColor(C.blue, '15') : 'transparent', borderWidth: 1, borderColor: tab === 'sandbox' ? (globalThis as any).__alphaColor(C.blue, '35') : C.border }}
          data-testid="sandbox-tab-btn"
        >
          <Ionicons name="eye" size={14} color={tab === 'sandbox' ? C.blue : C.muted} />
          <Text style={{ fontSize: 12, fontWeight: '700', color: tab === 'sandbox' ? C.blue : C.muted }}>{tx('admin.emailTemplates.clientSandbox.tabs.clientPreview', 'Client Preview')}</Text>
        </TouchableOpacity>
        <TouchableOpacity
          onPress={() => { setTab('compat'); if (!compatReport) loadCompatReport(); }}
          style={{ flexDirection: 'row', alignItems: 'center', gap: 6, paddingVertical: 8, paddingHorizontal: 16, borderRadius: 10, backgroundColor: tab === 'compat' ? (globalThis as any).__alphaColor(C.purple, '15') : 'transparent', borderWidth: 1, borderColor: tab === 'compat' ? (globalThis as any).__alphaColor(C.purple, '35') : C.border }}
          data-testid="compat-tab-btn"
        >
          <Ionicons name="analytics" size={14} color={tab === 'compat' ? C.purple : C.muted} />
          <Text style={{ fontSize: 12, fontWeight: '700', color: tab === 'compat' ? C.purple : C.muted }}>{tx('admin.emailTemplates.clientSandbox.tabs.compatibilityReport', 'Compatibility Report')}</Text>
        </TouchableOpacity>
      </View>

      {/* ═══ SANDBOX TAB ═══ */}
      {tab === 'sandbox' && (
        <View style={{ gap: 14 }}>
          {/* Template selector */}
          <View style={{ backgroundColor: C.card, borderRadius: 12, borderWidth: 1, borderColor: C.border, padding: 14 }} data-testid="sandbox-template-selector">
            <Text style={{ fontSize: 12, fontWeight: '700', color: C.text, marginBottom: 10 }}>{tx('admin.emailTemplates.clientSandbox.selector.title', 'Select Template')}</Text>
            <ScrollView horizontal showsHorizontalScrollIndicator={false}>
              <View style={{ flexDirection: 'row', gap: 6 }}>
                {catalog.slice(0, 20).map(t => (
                  <TouchableOpacity accessibilityLabel="Set selected template in client sandbox view button"
                    key={t.key}
                    onPress={() => {
                      setSelectedTemplate(t.key);
                      if (allClientsMode) {
                        loadAllPreviews(t.key);
                      } else {
                        loadSinglePreview(t.key, selectedClient);
                      }
                    }}
                    style={{ paddingVertical: 6, paddingHorizontal: 12, borderRadius: 8, backgroundColor: selectedTemplate === t.key ? (globalThis as any).__alphaColor(C.blue, '18') : 'transparent', borderWidth: 1, borderColor: selectedTemplate === t.key ? (globalThis as any).__alphaColor(C.blue, '40') : C.border }}
                    data-testid={`sandbox-tpl-${t.key}`}
                  >
                    <Text style={{ fontSize: 10, fontWeight: '700', color: selectedTemplate === t.key ? C.blue : C.muted }} numberOfLines={1}>{t.label}</Text>
                  </TouchableOpacity>
                ))}
                {catalog.length > 20 && (
                  <Text style={{ fontSize: 10, color: C.muted, alignSelf: 'center', paddingHorizontal: 8 }}>+{catalog.length - 20} more</Text>
                )}
              </View>
            </ScrollView>
          </View>

          {selectedTemplate && (
            <>
              {/* Client selector + all-clients toggle */}
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                {/* Single client chips */}
                {!allClientsMode && clients.map(c => (
                  <TouchableOpacity
                    key={c.id}
                    onPress={() => setSelectedClient(c.id)}
                    style={{ flexDirection: 'row', alignItems: 'center', gap: 5, paddingVertical: 6, paddingHorizontal: 12, borderRadius: 8, backgroundColor: selectedClient === c.id ? (globalThis as any).__alphaColor(C.blue, '18') : 'transparent', borderWidth: 1, borderColor: selectedClient === c.id ? (globalThis as any).__alphaColor(C.blue, '40') : C.border }}
                    data-testid={`sandbox-client-${c.id}`}
                  >
                    <Ionicons name={CLIENT_ICONS[c.id] as any} size={12} color={selectedClient === c.id ? C.blue : C.muted} />
                    <Text style={{ fontSize: 10, fontWeight: '700', color: selectedClient === c.id ? C.blue : C.muted }}>{c.name}</Text>
                  </TouchableOpacity>
                ))}
                {/* All clients toggle */}
                <TouchableOpacity accessibilityLabel="Sandbox all clients button"
                  onPress={() => {
                    if (allClientsMode) {
                      setAllClientsMode(false);
                      loadSinglePreview(selectedTemplate, selectedClient);
                    } else {
                      loadAllPreviews(selectedTemplate);
                    }
                  }}
                  style={{ flexDirection: 'row', alignItems: 'center', gap: 5, paddingVertical: 6, paddingHorizontal: 12, borderRadius: 8, backgroundColor: allClientsMode ? (globalThis as any).__alphaColor(C.purple, '18') : 'transparent', borderWidth: 1, borderColor: allClientsMode ? (globalThis as any).__alphaColor(C.purple, '40') : C.border }}
                  data-testid="sandbox-all-clients-btn"
                >
                  <Ionicons name="grid" size={12} color={allClientsMode ? C.purple : C.muted} />
                  <Text style={{ fontSize: 10, fontWeight: '700', color: allClientsMode ? C.purple : C.muted }}>{tx('admin.emailTemplates.clientSandbox.selector.allClients', 'All Clients')}</Text>
                </TouchableOpacity>
              </View>

              {/* Loading */}
              {loading && (
                <View style={{ padding: 40, alignItems: 'center' }}>
                  <ActivityIndicator size="large" color={C.blue} />
                  <Text style={{ color: C.muted, marginTop: 8, fontSize: 11 }}>{tx('admin.emailTemplates.clientSandbox.states.renderingPreview', 'Rendering preview...')}</Text>
                </View>
              )}

              {/* Single client preview */}
              {!loading && !allClientsMode && previewHtml && (
                <View style={{ backgroundColor: C.card, borderRadius: 14, borderWidth: 1, borderColor: C.border, overflow: 'hidden' }} data-testid="sandbox-single-preview">
                  {/* Client info bar */}
                  {clientInfo && (
                    <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', padding: 12, borderBottomWidth: 1, borderBottomColor: C.border, flexWrap: 'wrap', gap: 8 }}>
                      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
                        <Ionicons name={CLIENT_ICONS[selectedClient] as any} size={18} color={C.blue} />
                        <View>
                          <Text style={{ fontSize: 13, fontWeight: '800', color: C.text }}>{clientInfo.client_name}</Text>
                          <Text style={{ fontSize: 10, color: C.muted }}>{clientInfo.client_platform}</Text>
                        </View>
                      </View>
                      <View style={{ flexDirection: 'row', gap: 6 }}>
                        <View style={{ paddingHorizontal: 8, paddingVertical: 3, borderRadius: 99, backgroundColor: (globalThis as any).__alphaColor((SUPPORT_COLORS[clientInfo.dark_mode_support] || C.muted), '18') }}>
                          <Text style={{ fontSize: 9, fontWeight: '800', color: SUPPORT_COLORS[clientInfo.dark_mode_support] || C.muted }}>{clientInfo.dark_mode_support} support</Text>
                        </View>
                        <View style={{ paddingHorizontal: 8, paddingVertical: 3, borderRadius: 99, backgroundColor: C.border }}>
                          <Text style={{ fontSize: 9, fontWeight: '700', color: C.muted }}>{clientInfo.dark_mode_method}</Text>
                        </View>
                      </View>
                    </View>
                  )}
                  {/* Notes */}
                  {clientInfo?.notes && (
                    <View style={{ padding: 10, backgroundColor: (globalThis as any).__alphaColor(C.blue, '06'), borderBottomWidth: 1, borderBottomColor: C.border }}>
                      <Text style={{ fontSize: 10, color: C.muted, lineHeight: 16 }}>
                        <Ionicons name="information-circle" size={11} color={C.blue} /> {clientInfo.notes}
                      </Text>
                    </View>
                  )}
                  {/* Preview iframe */}
                  {Platform.OS === 'web' ? (
                    <iframe srcDoc={previewHtml} style={{ width: '100%', height: 600, border: 'none' } as any} title="Client sandbox preview" sandbox="allow-same-origin" />
                  ) : (
                    <Text style={{ color: C.muted, padding: 20, fontSize: 11 }}>{tx('admin.emailTemplates.clientSandbox.states.webPreviewOnly', 'Web preview only')}</Text>
                  )}
                </View>
              )}

              {/* All clients gallery */}
              {!loading && allClientsMode && allPreviews.length > 0 && (
                <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 14 }} data-testid="sandbox-all-clients-grid">
                  {allPreviews.map(p => (
                    <View key={p.client} style={{ width: galleryCols === 1 ? '100%' as any : galleryCols === 2 ? '48.5%' as any : '31.5%' as any, backgroundColor: C.card, borderRadius: 14, borderWidth: 1, borderColor: C.border, overflow: 'hidden' }} data-testid={`sandbox-client-card-${p.client}`}>
                      {/* Client header */}
                      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', padding: 10, borderBottomWidth: 1, borderBottomColor: C.border }}>
                        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                          <Ionicons name={CLIENT_ICONS[p.client] as any} size={14} color={C.blue} />
                          <View>
                            <Text style={{ fontSize: 11, fontWeight: '800', color: C.text }}>{p.name}</Text>
                            <Text style={{ fontSize: 9, color: C.muted }}>{p.platform}</Text>
                          </View>
                        </View>
                        <View style={{ flexDirection: 'row', gap: 4 }}>
                          <View style={{ paddingHorizontal: 6, paddingVertical: 2, borderRadius: 99, backgroundColor: (globalThis as any).__alphaColor((SUPPORT_COLORS[p.dark_mode_support] || C.muted), '18') }}>
                            <Text style={{ fontSize: 8, fontWeight: '800', color: SUPPORT_COLORS[p.dark_mode_support] || C.muted }}>{p.dark_mode_support}</Text>
                          </View>
                          <View style={{ paddingHorizontal: 6, paddingVertical: 2, borderRadius: 99, backgroundColor: C.border }}>
                            <Text style={{ fontSize: 8, fontWeight: '700', color: C.muted }}>{p.market_share}%</Text>
                          </View>
                        </View>
                      </View>
                      {/* Preview */}
                      <View style={{ height: 280, backgroundColor: 'var(--app-primary)' }}>{/* @theme-ok email dark-mode preview frame (always dark) */}
                        {Platform.OS === 'web' ? (
                          <iframe srcDoc={p.html} style={{ width: '100%', height: '100%', border: 'none', pointerEvents: 'none' } as any} title={p.name} sandbox="allow-same-origin" tabIndex={-1} />
                        ) : (
                          <Text style={{ color: C.muted, padding: 16, fontSize: 11 }}>{tx('admin.emailTemplates.clientSandbox.states.webOnly', 'Web only')}</Text>
                        )}
                      </View>
                      {/* Method note */}
                      <View style={{ padding: 8, borderTopWidth: 1, borderTopColor: C.border }}>
                        <Text style={{ fontSize: 9, color: C.muted }} numberOfLines={2}>{p.method}: {p.notes.slice(0, 80)}{p.notes.length > 80 ? '...' : ''}</Text>
                      </View>
                    </View>
                  ))}
                </View>
              )}
            </>
          )}

          {!selectedTemplate && (
            <View style={{ backgroundColor: C.card, borderRadius: 14, padding: 40, alignItems: 'center', justifyContent: 'center', borderWidth: 1, borderColor: C.border }}>
              <Ionicons name="eye-outline" size={36} color={C.border} />
              <Text style={{ fontSize: 14, color: C.muted, fontWeight: '700', marginTop: 12 }}>{tx('admin.emailTemplates.clientSandbox.empty.title', 'Select a template to preview')}</Text>
              <Text style={{ fontSize: 11, color: C.muted, marginTop: 4 }}>{tx('admin.emailTemplates.clientSandbox.empty.subtitle', 'See how your emails render across different email clients')}</Text>
            </View>
          )}
        </View>
      )}

      {/* ═══ COMPATIBILITY REPORT TAB ═══ */}
      {tab === 'compat' && (
        <View style={{ gap: 14 }}>
          {compatLoading && (
            <View style={{ padding: 40, alignItems: 'center' }}>
              <ActivityIndicator size="large" color={C.purpleText} />
              <Text style={{ color: C.muted, marginTop: 8, fontSize: 11 }}>Scanning {catalog.length} templates across 7 clients...</Text>
            </View>
          )}

          {!compatLoading && compatReport && (
            <>
              {/* Overall score card */}
              <View style={{ backgroundColor: C.card, borderRadius: 14, borderWidth: 1, borderColor: C.border, padding: 16 }} data-testid="compat-overall-card">
                <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14 }}>
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
                    <Ionicons name="shield-checkmark" size={18} color={GRADE_COLORS[compatReport.summary.overall_grade] || C.muted} />
                    <Text style={{ fontSize: 15, fontWeight: '800', color: C.text }}>{tx('admin.emailTemplates.clientSandbox.compatibility.title', 'Client Compatibility')}</Text>
                  </View>
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                    <View style={{ paddingHorizontal: 10, paddingVertical: 4, borderRadius: 99, backgroundColor: (globalThis as any).__alphaColor((GRADE_COLORS[compatReport.summary.overall_grade] || C.muted), '18') }}>
                      <Text style={{ fontSize: 12, fontWeight: '800', color: GRADE_COLORS[compatReport.summary.overall_grade] || C.muted }}>
                        Grade {compatReport.summary.overall_grade} ({compatReport.summary.overall_score}%)
                      </Text>
                    </View>
                    <TouchableOpacity onPress={loadCompatReport} style={{ padding: 6 }} data-testid="compat-refresh-btn">
                      <Ionicons name="refresh" size={14} color={C.muted} />
                    </TouchableOpacity>
                  </View>
                </View>
                <Text style={{ fontSize: 10, color: C.muted, marginBottom: 12 }}>
                  {compatReport.summary.templates_tested} templates tested across {compatReport.summary.clients_tested} email clients
                </Text>

                {/* Client score bars */}
                <View style={{ gap: 10 }}>
                  {Object.entries(compatReport.clients)
                    .sort(([, a], [, b]) => b.market_share - a.market_share)
                    .map(([clientId, info]) => (
                      <TouchableOpacity
                        key={clientId}
                        onPress={() => setCompatFilter(compatFilter === clientId ? null : clientId)}
                        style={{ flexDirection: 'row', alignItems: 'center', gap: 10, opacity: compatFilter && compatFilter !== clientId ? 0.4 : 1 }}
                        data-testid={`compat-client-row-${clientId}`}
                      >
                        <View style={{ width: 24, alignItems: 'center' }}>
                          <Ionicons name={CLIENT_ICONS[clientId] as any} size={14} color={C.blue} />
                        </View>
                        <View style={{ width: 100 }}>
                          <Text style={{ fontSize: 11, fontWeight: '700', color: C.text }} numberOfLines={1}>{info.name}</Text>
                          <Text style={{ fontSize: 9, color: C.muted }}>{info.market_share}% share</Text>
                        </View>
                        <View style={{ flex: 1 }}>
                          <RateBar rate={Math.round(info.avg_score)} color={GRADE_COLORS[info.grade] || C.muted} />
                        </View>
                        <View style={{ paddingHorizontal: 8, paddingVertical: 3, borderRadius: 99, backgroundColor: (globalThis as any).__alphaColor((GRADE_COLORS[info.grade] || C.muted), '15'), minWidth: 28, alignItems: 'center' }}>
                          <Text style={{ fontSize: 10, fontWeight: '800', color: GRADE_COLORS[info.grade] || C.muted }}>{info.grade}</Text>
                        </View>
                      </TouchableOpacity>
                    ))}
                </View>
              </View>

              {/* Filter indicator */}
              {compatFilter && (
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, padding: 10, backgroundColor: (globalThis as any).__alphaColor(C.blue, '08'), borderRadius: 10, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(C.blue, '20') }}>
                  <Ionicons name="funnel" size={12} color={C.blue} />
                  <Text style={{ fontSize: 11, color: C.blue, fontWeight: '600', flex: 1 }}>
                    Showing templates with issues for {compatReport.clients[compatFilter]?.name || compatFilter}
                  </Text>
                  <TouchableOpacity onPress={() => setCompatFilter(null)} data-testid="compat-clear-filter-btn">
                    <Ionicons name="close-circle" size={16} color={C.blue} />
                  </TouchableOpacity>
                </View>
              )}

              {/* Template results */}
              <View style={{ backgroundColor: C.card, borderRadius: 14, borderWidth: 1, borderColor: C.border, overflow: 'hidden' }} data-testid="compat-results-table">
                <View style={{ flexDirection: 'row', padding: 12, borderBottomWidth: 1, borderBottomColor: C.border, backgroundColor: C.bg }}>
                  <Text style={{ flex: 2, fontSize: 10, fontWeight: '800', color: C.muted, textTransform: 'uppercase', letterSpacing: 0.5 }}>{tx('admin.emailTemplates.clientSandbox.compatibility.table.template', 'Template')}</Text>
                  {Object.entries(compatReport.clients)
                    .sort(([, a], [, b]) => b.market_share - a.market_share)
                    .map(([cid]) => (
                      <Text key={cid} style={{ flex: 1, fontSize: 9, fontWeight: '700', color: C.muted, textAlign: 'center' }} numberOfLines={1}>{compatReport.clients[cid].name.split(' ')[0]}</Text>
                    ))}
                </View>
                <ScrollView style={{ maxHeight: 400 }} data-testid="compat-results-scroll">
                  {filteredCompat.slice(0, 30).map(r => (
                    <View key={r.key} style={{ flexDirection: 'row', alignItems: 'center', padding: 10, borderBottomWidth: 1, borderBottomColor: C.border }}>
                      <View style={{ flex: 2 }}>
                        <Text style={{ fontSize: 11, fontWeight: '700', color: C.text }} numberOfLines={1}>{r.label}</Text>
                        <Text style={{ fontSize: 9, color: C.muted }}>{r.category}</Text>
                      </View>
                      {Object.entries(compatReport.clients)
                        .sort(([, a], [, b]) => b.market_share - a.market_share)
                        .map(([cid]) => {
                          const compat = r.compatibility[cid];
                          if (!compat) return <View key={cid} style={{ flex: 1, alignItems: 'center' }}><Text style={{ fontSize: 9, color: C.muted }}>-</Text></View>;
                          const color = compat.score >= 90 ? 'var(--app-success)' : compat.score >= 70 ? 'var(--app-primary)' : compat.score >= 50 ? 'var(--app-warning)' : 'var(--app-error)';
                          return (
                            <View key={cid} style={{ flex: 1, alignItems: 'center' }}>
                              <View style={{ width: 28, height: 28, borderRadius: 14, backgroundColor: (globalThis as any).__alphaColor(color, '15'), alignItems: 'center', justifyContent: 'center' }}>
                                <Text style={{ fontSize: 9, fontWeight: '800', color }}>{compat.score}</Text>
                              </View>
                            </View>
                          );
                        })}
                    </View>
                  ))}
                  {filteredCompat.length > 30 && (
                    <View style={{ padding: 12, alignItems: 'center' }}>
                      <Text style={{ fontSize: 10, color: C.muted }}>+{filteredCompat.length - 30} more templates</Text>
                    </View>
                  )}
                </ScrollView>
              </View>
            </>
          )}

          {!compatLoading && !compatReport && (
            <View style={{ backgroundColor: C.card, borderRadius: 14, padding: 40, alignItems: 'center', borderWidth: 1, borderColor: C.border }}>
              <Ionicons name="analytics-outline" size={36} color={C.border} />
              <Text style={{ fontSize: 14, color: C.muted, fontWeight: '700', marginTop: 12 }}>{tx('admin.emailTemplates.clientSandbox.states.loadingCompatibility', 'Loading compatibility report...')}</Text>
            </View>
          )}
        </View>
      )}
    </View>
  );
}
