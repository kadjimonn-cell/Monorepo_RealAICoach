/* eslint-disable custom-theme/no-hardcoded-theme-colors -- fullscreen modal backdrop uses pure `var(--app-text)` overlay across both themes; intentional */
import { useTranslation } from '../../../hooks/useTranslation';
import React, { useState, useCallback, useEffect, useMemo } from 'react';
import { View, Text, TouchableOpacity, ActivityIndicator, TextInput, Platform, ScrollView, useWindowDimensions } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../../services/api';
import { C, CATEGORY_ICONS, CatalogItem, RateBar } from './shared';

interface Props {
  catalog: CatalogItem[];
  catalogLoading: boolean;
  analytics: any;
  stats: any;
  userEmail: string;
  onQuickCreateAbTest: (templateType: string) => void;
  creatingTest: string | null;
  sendResult: { ok: boolean; msg: string } | null;
  onSendResult: (result: { ok: boolean; msg: string } | null) => void;
}

const VIEWPORT_OPTS = [
  { label: 'Mobile', w: 375, icon: 'phone-portrait' },
  { label: 'Tablet', w: 600, icon: 'tablet-portrait' },
  { label: 'Desktop', w: 800, icon: 'desktop' },
] as const;

const ISSUE_FIX_LIBRARY: Record<string, { title: string; guidance: string }> = {
  missing_viewport_meta: {
    title: 'Add mobile viewport metadata',
    guidance: 'Ensure template head contains responsive viewport tags and keep max-width wrappers under 600px.',
  },
  missing_mobile_media_query: {
    title: 'Add mobile media query',
    guidance: 'Include compact typography + stacked CTA layout at <=479px so content does not overflow.',
  },
  missing_color_scheme_meta: {
    title: 'Declare light/dark color schemes',
    guidance: 'Add color-scheme and supported-color-schemes meta tags for better theme handling in email clients.',
  },
  missing_dark_mode_css: {
    title: 'Add dark mode CSS block',
    guidance: 'Create a prefers-color-scheme: dark section and define safe contrast colors for text/background surfaces.',
  },
  missing_official_store_badges: {
    title: 'Restore official store badges',
    guidance: 'Include both Google Play and App Store footer badge links with valid HTTPS image URLs.',
  },
  global_footer_component_missing_or_duplicated: {
    title: 'Enforce the shared footer component',
    guidance: 'Do not define footer HTML in templates. Route every template through the global footer component exactly once.',
  },
  global_footer_version_marker_missing: {
    title: 'Restore footer version marker',
    guidance: 'Ensure the reusable footer component emits its version + last-updated markers for admin QA and build enforcement.',
  },
  missing_secondary_cta_variant: {
    title: 'Add secondary CTA fallback',
    guidance: 'Provide secondary support/help CTA below primary CTA for safer user path completion.',
  },
  render_error: {
    title: 'Resolve template render error',
    guidance: 'Open this template first and fix invalid variables/HTML blocks before link or style checks.',
  },
};

export default function TemplatesView({
  catalog, catalogLoading, analytics, stats, userEmail,
  onQuickCreateAbTest, creatingTest, sendResult, onSendResult,
}: Props) {
  const { width } = useWindowDimensions();
  const isWide = width >= 768;
  const { t } = useTranslation();
  const tx = useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);
  const galleryLabel = t('templatesView.toolbar.gallery');

  const [viewMode, setViewMode] = useState<'list' | 'gallery'>('gallery');
  const [selected, setSelected] = useState<string | null>(null);
  const [previewHtml, setPreviewHtml] = useState('');
  const [previewSubject, setPreviewSubject] = useState('');
  const [previewFooterVersion, setPreviewFooterVersion] = useState('');
  const [previewFooterUpdatedAt, setPreviewFooterUpdatedAt] = useState('');
  const [loading, setLoading] = useState(false);
  const [sending, setSending] = useState(false);
  const [testEmail, setTestEmail] = useState(userEmail);
  const [previewWidth, setPreviewWidth] = useState<number>(600);
  const [previewTheme, setPreviewTheme] = useState<'dark' | 'light'>('light');
  const [compareMode, setCompareMode] = useState(false);
  const [compareHtml, setCompareHtml] = useState<{ dark: string; light: string }>({ dark: '', light: '' });
  const [fullscreenItem, setFullscreenItem] = useState<CatalogItem | null>(null);
  const [fullscreenHtml, setFullscreenHtml] = useState<{ dark: string; light: string }>({ dark: '', light: '' });
  const [fullscreenLoading, setFullscreenLoading] = useState(false);
  const [galleryTheme, setGalleryTheme] = useState<'dark' | 'light'>('light');
  const [gallerySendingKey, setGallerySendingKey] = useState<string | null>(null);
  const [galleryHtmlCache, setGalleryHtmlCache] = useState<Record<string, Record<string, string>>>({});
  const [planTier, setPlanTier] = useState<'' | 'free' | 'basic' | 'premium'>('');
  const [bulkSending, setBulkSending] = useState(false);
  const [bulkProgress, setBulkProgress] = useState({ sent: 0, failed: 0, total: 0 });
  const [filterCat, setFilterCat] = useState<string | null>(null);
  const [auditRunning, setAuditRunning] = useState(false);
  const [auditSummary, setAuditSummary] = useState<any>(null);
  const [auditFailures, setAuditFailures] = useState<any[]>([]);
  const [failedOnlyMode, setFailedOnlyMode] = useState(false);
  const [issueFilter, setIssueFilter] = useState<string | null>(null);
  const [contrastAuditRunning, setContrastAuditRunning] = useState(false);
  const [contrastResult, setContrastResult] = useState<{ total: number; passed: number; failed: number; rate: number; failedList: any[] } | null>(null);
  const [batchAuditRunning, setBatchAuditRunning] = useState(false);
  const [batchAuditResult, setBatchAuditResult] = useState<any>(null);
  const [sendAllRunning, setSendAllRunning] = useState(false);
  const [sendAllResult, setSendAllResult] = useState<{ sent: number; failed: number; total: number } | null>(null);

  const categories = Array.from(new Set(catalog.map(t => t.category))).sort();
  const footerGallerySummary = useMemo(() => {
    const first = catalog[0];
    return {
      templates: catalog.length,
      version: first?.footer_version || '—',
      updatedAt: first?.footer_last_updated || '—',
      badgeBlock: first?.footer_badge_block || null,
    };
  }, [catalog]);
  const filtered = useMemo(() => {
    let items = filterCat ? catalog.filter(t => t.category === filterCat) : catalog;
    if (failedOnlyMode) {
      const failedKeys = new Set((auditFailures || []).map((f: any) => f.key));
      items = items.filter(t => failedKeys.has(t.key));
    }
    if (issueFilter) {
      items = items.filter(t => {
        const failMeta = (auditFailures || []).find((f: any) => f.key === t.key);
        return Array.isArray(failMeta?.issues) && failMeta.issues.includes(issueFilter);
      });
    }
    return items;
  }, [catalog, filterCat, failedOnlyMode, issueFilter, auditFailures]);

  const failedIssueOptions = useMemo(() => {
    const issueSet = new Set<string>();
    (auditFailures || []).forEach((f: any) => (f.issues || []).forEach((issue: string) => issueSet.add(issue)));
    return Array.from(issueSet).sort();
  }, [auditFailures]);

  const activeFailure = useMemo(() => {
    if (!auditFailures.length) return null;
    const selectedFailure = selected ? auditFailures.find((f: any) => f.key === selected) : null;
    return selectedFailure || auditFailures[0];
  }, [auditFailures, selected]);

  const autoFixSuggestions = useMemo(() => {
    if (!auditFailures.length) {
      return [
        {
          issue: 'healthy',
          title: 'All templates are healthy',
          guidance: 'Run audit after every batch of edits. If a failure appears, use Fix Failing Templates to jump directly into triage mode.',
        },
      ];
    }

    const targetIssues = issueFilter
      ? [issueFilter]
      : Array.isArray(activeFailure?.issues)
        ? activeFailure.issues
        : [];

    if (!targetIssues.length) {
      return [
        {
          issue: 'generic',
          title: 'Review failing templates first',
          guidance: 'Open each failed template and validate links, badges, CTA variants, and dark-mode CSS markers.',
        },
      ];
    }

    return targetIssues.map((issue: string) => {
      const entry = ISSUE_FIX_LIBRARY[issue] || {
        title: `Investigate ${issue}`,
        guidance: 'Review this issue in preview and apply a targeted template fix, then rerun audit.',
      };
      return { issue, title: entry.title, guidance: entry.guidance };
    });
  }, [auditFailures, activeFailure, issueFilter]);

  const loadPreview = useCallback(async (key: string) => {
    setSelected(key); setPreviewHtml(''); onSendResult(null); setLoading(true);
    try {
      const planParam = planTier ? `&plan_id=${planTier}` : '';
      const res = await api.get(`/email-notifications/preview/${key}?theme=${previewTheme}${planParam}`);
      setPreviewHtml(res.data.html); setPreviewSubject(res.data.subject);
      setPreviewFooterVersion(res.data.footer_version || '');
      setPreviewFooterUpdatedAt(res.data.footer_last_updated || '');
      if (compareMode) {
        const [darkRes, lightRes] = await Promise.all([
          api.get(`/email-notifications/preview/${key}?theme=dark${planParam}`),
          api.get(`/email-notifications/preview/${key}?theme=light${planParam}`),
        ]);
        setCompareHtml({ dark: darkRes.data.html, light: lightRes.data.html });
      }
    } catch (e: any) {
      setPreviewHtml(`<p style="color:red;">Failed: ${e?.response?.data?.detail || e.message}</p>`);
    } finally { setLoading(false); }
  }, [previewTheme, onSendResult, compareMode, planTier]);

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { if (selected) loadPreview(selected); }, [previewTheme, planTier]);

  // Load both themes when entering compare mode
  useEffect(() => {
    if (compareMode && selected) {
      (async () => {
        try {
          const [darkRes, lightRes] = await Promise.all([
            api.get(`/email-notifications/preview/${selected}?theme=dark`),
            api.get(`/email-notifications/preview/${selected}?theme=light`),
          ]);
          setCompareHtml({ dark: darkRes.data.html, light: lightRes.data.html });
        } catch { /* keep existing preview */ }
      })();
    }
   
  }, [compareMode, selected]);

  const sendTest = useCallback(async () => {
    if (!selected || !testEmail) return;
    setSending(true); onSendResult(null);
    try {
      const res = await api.post(`/email-notifications/send-test/${selected}?theme=${previewTheme}`, { recipient_email: testEmail });
      onSendResult({ ok: true, msg: res.data.message || `Sent (${previewTheme}) to ${testEmail}` });
    } catch (e: any) { onSendResult({ ok: false, msg: e?.response?.data?.detail || 'Send failed' }); }
    finally { setSending(false); }
  }, [selected, testEmail, previewTheme, onSendResult]);

  const openPreviewWindow = useCallback(() => {
    if (Platform.OS !== 'web' || !previewHtml || typeof window === 'undefined') return;
    const previewWindow = window.open('', '_blank', 'noopener,noreferrer');
    if (!previewWindow) {
      onSendResult({ ok: false, msg: 'Popup blocked. Please allow popups for preview testing.' });
      return;
    }
    previewWindow.document.open();
    previewWindow.document.write(previewHtml);
    previewWindow.document.close();
  }, [onSendResult, previewHtml]);

  const sendAllTests = useCallback(async () => {
    if (!testEmail || bulkSending) return;
    setBulkSending(true); setBulkProgress({ sent: 0, failed: 0, total: catalog.length });
    let sent = 0, failed = 0;
    for (const tpl of catalog) {
      try { await api.post(`/email-notifications/send-test/${tpl.key}?theme=${previewTheme}`, { recipient_email: testEmail }); sent++; }
      catch { failed++; }
      setBulkProgress({ sent, failed, total: catalog.length });
    }
    setBulkSending(false);
    onSendResult({ ok: failed === 0, msg: `Bulk send (${previewTheme}): ${sent} sent, ${failed} failed of ${catalog.length}` });
  }, [testEmail, catalog, bulkSending, previewTheme, onSendResult]);

  const sendAllQA = useCallback(async () => {
    if (sendAllRunning) return;
    setSendAllRunning(true);
    setSendAllResult(null);
    try {
      const res = await api.post(`/email-notifications/send-all-templates?theme=${galleryTheme}`, { recipient_email: userEmail });
      const data = res.data;
      setSendAllResult({ sent: data.sent, failed: data.failed, total: data.total });
      onSendResult({ ok: data.failed === 0, msg: data.message });
    } catch (e: any) {
      setSendAllResult({ sent: 0, failed: 0, total: 0 });
      onSendResult({ ok: false, msg: `Send All failed: ${e?.response?.data?.detail || e.message}` });
    }
    setSendAllRunning(false);
  }, [sendAllRunning, galleryTheme, userEmail, onSendResult]);

  const runTemplateAudit = useCallback(async () => {
    setAuditRunning(true);
    try {
      const res = await api.get('/email-notifications/templates/audit');
      setAuditSummary(res.data?.summary || null);
      setAuditFailures(res.data?.failed_templates || []);
      setFailedOnlyMode(false);
      setIssueFilter(null);
      const failed = res.data?.summary?.templates_failed || 0;
      const total = res.data?.summary?.templates_total || 0;
      onSendResult({ ok: failed === 0, msg: `Template audit complete: ${total - failed}/${total} passing` });
    } catch (e: any) {
      onSendResult({ ok: false, msg: e?.response?.data?.detail || 'Template audit failed' });
    } finally {
      setAuditRunning(false);
    }
  }, [onSendResult]);

  const runContrastAudit = useCallback(async () => {
    setContrastAuditRunning(true);
    try {
      const res = await api.get('/email-notifications/templates/audit');
      const results = res.data?.results || [];
      const total = results.length;
      const failedList = results.filter((r: any) => r.status === 'fail');
      const passed = total - failedList.length;
      const rate = total > 0 ? Math.round((passed / total) * 1000) / 10 : 0;
      setContrastResult({ total, passed, failed: failedList.length, rate, failedList });
      onSendResult({ ok: failedList.length === 0, msg: `Contrast audit: ${rate}% compliant (${passed}/${total})` });
    } catch (e: any) {
      onSendResult({ ok: false, msg: e?.response?.data?.detail || 'Contrast audit failed' });
    } finally {
      setContrastAuditRunning(false);
    }
  }, [onSendResult]);

  const activateFixFailingTemplates = useCallback(async () => {
    if (!auditFailures.length) {
      onSendResult({ ok: true, msg: 'No failing templates detected.' });
      return;
    }
    setFailedOnlyMode(true);
    const firstFailure = auditFailures[0];
    const defaultIssue = Array.isArray(firstFailure?.issues) ? firstFailure.issues[0] : null;
    setIssueFilter(defaultIssue || null);

    if (firstFailure?.key) {
      await loadPreview(firstFailure.key);
    }

    onSendResult({
      ok: true,
      msg: `Fix mode enabled. Showing ${auditFailures.length} failing templates${defaultIssue ? ` (filtered by ${defaultIssue})` : ''}.`,
    });
  }, [auditFailures, loadPreview, onSendResult]);

  // Gallery: load both themes for fullscreen comparison
  const openFullscreen = useCallback(async (item: CatalogItem) => {
    setFullscreenItem(item);
    setFullscreenLoading(true);
    try {
      const [darkRes, lightRes] = await Promise.all([
        api.get(`/email-notifications/preview/${item.key}?theme=dark`),
        api.get(`/email-notifications/preview/${item.key}?theme=light`),
      ]);
      setFullscreenHtml({ dark: darkRes.data.html, light: lightRes.data.html });
    } catch { setFullscreenHtml({ dark: '', light: '' }); }
    finally { setFullscreenLoading(false); }
  }, []);

  // Gallery: quick send test email
  const galleryQuickSend = useCallback(async (key: string) => {
    setGallerySendingKey(key);
    try {
      await api.post(`/email-notifications/send-test/${key}?theme=${galleryTheme}`, { recipient_email: userEmail });
      onSendResult({ ok: true, msg: `Test sent to ${userEmail} (${galleryTheme})` });
    } catch { onSendResult({ ok: false, msg: 'Send failed' }); }
    finally { setTimeout(() => setGallerySendingKey(null), 2000); }
  }, [galleryTheme, userEmail, onSendResult]);

  // Gallery: load thumbnails for gallery cards in current theme
  useEffect(() => {
    if (viewMode !== 'gallery' || catalogLoading || !filtered.length) return;
    const keysToLoad = filtered.filter(t => !galleryHtmlCache[t.key]?.[galleryTheme]).map(t => t.key);
    if (!keysToLoad.length) return;
    let cancelled = false;
    (async () => {
      const batch: Record<string, Record<string, string>> = { ...galleryHtmlCache };
      for (const key of keysToLoad.slice(0, 12)) {
        if (cancelled) break;
        try {
          const res = await api.get(`/email-notifications/preview/${key}?theme=${galleryTheme}`);
          if (!batch[key]) batch[key] = {};
          batch[key][galleryTheme] = res.data.html;
        } catch { /* skip */ }
      }
      if (!cancelled) setGalleryHtmlCache(batch);
    })();
    return () => { cancelled = true; };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [viewMode, galleryTheme, catalogLoading, filterCat]);

  const galleryCols = width > 1200 ? 3 : width > 800 ? 2 : 1;

  // Batch Theme Audit
  const runBatchThemeAudit = useCallback(async () => {
    setBatchAuditRunning(true);
    setBatchAuditResult(null);
    try {
      const res = await api.get('/email-notifications/templates/batch-theme-audit');
      setBatchAuditResult(res.data);
      const s = res.data?.summary;
      onSendResult({ ok: s?.failed === 0, msg: `Theme audit: ${s?.passed}/${s?.total} pass (${s?.pass_rate}%), ${s?.total_issues} issues` });
    } catch (e: any) {
      onSendResult({ ok: false, msg: e?.response?.data?.detail || 'Batch theme audit failed' });
    } finally {
      setBatchAuditRunning(false);
    }
  }, [onSendResult]);

  const previewChecks = useMemo(() => {
    const h = (previewHtml || '').toLowerCase();
    const googleHeights = Array.from(h.matchAll(/data-footer-badge="google-play"[^>]*data-footer-badge-lock-height="(\d+)"/g)).map((match) => match[1]);
    const appHeights = Array.from(h.matchAll(/data-footer-badge="app-store"[^>]*data-footer-badge-lock-height="(\d+)"/g)).map((match) => match[1]);
    const googleWidths = Array.from(h.matchAll(/data-footer-badge="google-play"[^>]*data-footer-badge-lock-width="(\d+)"/g)).map((match) => match[1]);
    const appWidths = Array.from(h.matchAll(/data-footer-badge="app-store"[^>]*data-footer-badge-lock-width="(\d+)"/g)).map((match) => match[1]);
    const badgeLock = googleHeights.length > 0 && appHeights.length > 0 && googleHeights.join(',') === appHeights.join(',') && googleWidths.join(',') === appWidths.join(',');
    const globalFooterCount = (h.match(/data-global-footer-component="realaicoach-global-email-footer"/g) || []).length;
    const sharedHeaderDark = h.includes('email-header-shell') && h.includes('email-header-pill') && h.includes('email-header-kicker');
    return {
      responsive: h.includes('@media only screen and (max-width:479px)'),
      darkMode: h.includes('prefers-color-scheme:dark'),
      officialBadges: h.includes('data-footer-badge="google-play"') && h.includes('data-footer-badge="app-store"') && badgeLock,
      badgeLock,
      sharedFooter: globalFooterCount === 1 && h.includes('data-global-footer-version='),
      sharedHeaderDark,
      secondaryCta: h.includes('email-secondary-cta'),
    };
  }, [previewHtml]);

  const selectedCatalogItem = useMemo(() => catalog.find((item) => item.key === selected) || null, [catalog, selected]);

  const selAnalytics = selected && analytics?.by_type?.[selected] ? analytics.by_type[selected] : null;
  const isBillingTemplate = selectedCatalogItem?.category === 'Billing';

  return (
    <View style={{ flexDirection: 'column', gap: 16 }}>
      {/* ═══ TOOLBAR: View Toggle + Gallery Theme + Category Filter ═══ */}
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
        {/* View Mode Toggle */}
        <View style={{ flexDirection: 'row', backgroundColor: C.card, borderRadius: 10, padding: 3, borderWidth: 1, borderColor: C.border }} data-testid="view-mode-toggle" testID="view-mode-toggle">
          <TouchableOpacity onPress={() => setViewMode('gallery')} style={{ flexDirection: 'row', alignItems: 'center', gap: 5, paddingVertical: 6, paddingHorizontal: 12, borderRadius: 8, backgroundColor: viewMode === 'gallery' ? (globalThis as any).__alphaColor(C.blue, '18') : 'transparent' }} data-testid="view-mode-gallery-btn" testID="view-mode-gallery-btn">
            <Ionicons name="grid" size={13} color={viewMode === 'gallery' ? C.blue : C.muted} />
            <Text style={{ fontSize: 11, fontWeight: '700', color: viewMode === 'gallery' ? C.blue : C.muted }}>{galleryLabel === 'templatesView.toolbar.gallery' ? 'Gallery' : galleryLabel}</Text>
          </TouchableOpacity>
          <TouchableOpacity onPress={() => setViewMode('list')} style={{ flexDirection: 'row', alignItems: 'center', gap: 5, paddingVertical: 6, paddingHorizontal: 12, borderRadius: 8, backgroundColor: viewMode === 'list' ? (globalThis as any).__alphaColor(C.blue, '18') : 'transparent' }} data-testid="view-mode-list-btn" testID="view-mode-list-btn">
            <Ionicons name="list" size={13} color={viewMode === 'list' ? C.blue : C.muted} />
            <Text style={{ fontSize: 11, fontWeight: '700', color: viewMode === 'list' ? C.blue : C.muted }}>{tx('templatesView.toolbar.detail', 'Detail')}</Text>
          </TouchableOpacity>
        </View>

        {/* Gallery Theme Toggle (visible in gallery mode) */}
        {viewMode === 'gallery' && (
          <View style={{ flexDirection: 'row', backgroundColor: C.card, borderRadius: 10, padding: 3, borderWidth: 1, borderColor: C.border }} data-testid="gallery-theme-toggle" testID="gallery-theme-toggle">
            <TouchableOpacity onPress={() => setGalleryTheme('light')} style={{ flexDirection: 'row', alignItems: 'center', gap: 4, paddingVertical: 6, paddingHorizontal: 10, borderRadius: 8, backgroundColor: galleryTheme === 'light' ? C.warningSoft : 'transparent' }} data-testid="gallery-theme-light-btn" testID="gallery-theme-light-btn">
              <Ionicons name="sunny" size={12} color={galleryTheme === 'light' ? 'var(--app-warning)' : C.muted} />
              <Text style={{ fontSize: 11, fontWeight: '600', color: galleryTheme === 'light' ? C.warning : C.muted }}>{tx('templatesView.toolbar.light', 'Light')}</Text>
            </TouchableOpacity>
            <TouchableOpacity onPress={() => setGalleryTheme('dark')} style={{ flexDirection: 'row', alignItems: 'center', gap: 4, paddingVertical: 6, paddingHorizontal: 10, borderRadius: 8, backgroundColor: galleryTheme === 'dark' ? C.primarySoft : 'transparent' }} data-testid="gallery-theme-dark-btn" testID="gallery-theme-dark-btn">
              <Ionicons name="moon" size={12} color={galleryTheme === 'dark' ? 'var(--app-primary)' : C.muted} />
              <Text style={{ fontSize: 11, fontWeight: '600', color: galleryTheme === 'dark' ? C.primary : C.muted }}>{tx('templatesView.toolbar.dark', 'Dark')}</Text>
            </TouchableOpacity>
          </View>
        )}

        {/* Batch Theme Audit button (visible in gallery mode) */}
        {viewMode === 'gallery' && (
          <TouchableOpacity onPress={runBatchThemeAudit} disabled={batchAuditRunning} style={{ flexDirection: 'row', alignItems: 'center', gap: 5, paddingVertical: 6, paddingHorizontal: 12, borderRadius: 10, backgroundColor: batchAuditRunning ? (globalThis as any).__alphaColor(C.purple, '08') : C.purple + '12', borderWidth: 1, borderColor: (globalThis as any).__alphaColor(C.purple, '25'), opacity: batchAuditRunning ? 0.7 : 1 }} data-testid="batch-theme-audit-btn" testID="batch-theme-audit-btn">
            {batchAuditRunning ? <ActivityIndicator size={10} color={C.purpleText} /> : <Ionicons name="shield-checkmark" size={12} color={C.purpleText} />}
            <Text style={{ fontSize: 11, fontWeight: '700', color: C.purpleText }}>{batchAuditRunning ? tx('templatesView.toolbar.auditing', 'Auditing...') : tx('templatesView.toolbar.themeAudit', 'Theme Audit')}</Text>
            {batchAuditResult && !batchAuditRunning && (
              <View style={{ paddingHorizontal: 6, paddingVertical: 1, borderRadius: 99, backgroundColor: batchAuditResult.summary?.failed === 0 ? (globalThis as any).__alphaColor(C.green, '18') : C.red + '18' }}>
                <Text style={{ fontSize: 9, fontWeight: '800', color: batchAuditResult.summary?.failed === 0 ? C.green : C.red }}>{batchAuditResult.summary?.pass_rate}%</Text>
              </View>
            )}
          </TouchableOpacity>
        )}

        {/* Send All 51 QA button (visible in gallery mode) */}
        {viewMode === 'gallery' && (
          <TouchableOpacity onPress={sendAllQA} disabled={sendAllRunning} style={{ flexDirection: 'row', alignItems: 'center', gap: 5, paddingVertical: 6, paddingHorizontal: 12, borderRadius: 10, backgroundColor: sendAllRunning ? (globalThis as any).__alphaColor(C.cyan, '08') : C.cyan + '12', borderWidth: 1, borderColor: (globalThis as any).__alphaColor(C.cyan, '25'), opacity: sendAllRunning ? 0.7 : 1 }} data-testid="send-all-51-btn" testID="send-all-51-btn">
            {sendAllRunning ? <ActivityIndicator size={10} color={C.cyan} /> : <Ionicons name="paper-plane" size={12} color={C.cyan} />}
            <Text style={{ fontSize: 11, fontWeight: '700', color: C.cyan }}>{sendAllRunning ? tx('templatesView.toolbar.sending', 'Sending...') : tx('templatesView.toolbar.sendAll', 'Send All {count}').replace('{count}', String(catalog.length))}</Text>
            {sendAllResult && !sendAllRunning && (
              <View style={{ paddingHorizontal: 6, paddingVertical: 1, borderRadius: 99, backgroundColor: sendAllResult.failed === 0 ? (globalThis as any).__alphaColor(C.green, '18') : C.red + '18' }}>
                <Text style={{ fontSize: 9, fontWeight: '800', color: sendAllResult.failed === 0 ? C.green : C.red }}>{sendAllResult.sent}/{sendAllResult.total}</Text>
              </View>
            )}
          </TouchableOpacity>
        )}

        {/* Category chips (compact) */}
        <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ flex: 1 }}>
          <View style={{ flexDirection: 'row', gap: 4 }}>
            <TouchableOpacity onPress={() => setFilterCat(null)} style={{ paddingVertical: 5, paddingHorizontal: 10, borderRadius: 8, backgroundColor: !filterCat ? (globalThis as any).__alphaColor(C.blue, '15') : 'transparent', borderWidth: 1, borderColor: !filterCat ? (globalThis as any).__alphaColor(C.blue, '35') : C.border }} data-testid="template-cat-all" testID="template-cat-all">
              <Text style={{ fontSize: 10, fontWeight: '700', color: !filterCat ? C.blue : C.muted }}>{tx('templatesView.toolbar.allCount', 'All ({count})').replace('{count}', String(catalog.length))}</Text>
            </TouchableOpacity>
            {categories.map(cat => (
              <TouchableOpacity key={cat} onPress={() => setFilterCat(cat)} style={{ flexDirection: 'row', alignItems: 'center', gap: 4, paddingVertical: 5, paddingHorizontal: 10, borderRadius: 8, backgroundColor: filterCat === cat ? (globalThis as any).__alphaColor(C.blue, '15') : 'transparent', borderWidth: 1, borderColor: filterCat === cat ? (globalThis as any).__alphaColor(C.blue, '35') : C.border }} data-testid={`template-cat-${cat.toLowerCase().replace(/[^a-z0-9]+/g, '-')}`} testID={`template-cat-${cat.toLowerCase().replace(/[^a-z0-9]+/g, '-')}`}>
                <Ionicons name={(CATEGORY_ICONS[cat] || 'mail') as any} size={10} color={filterCat === cat ? C.blue : C.muted} />
                <Text style={{ fontSize: 10, fontWeight: '700', color: filterCat === cat ? C.blue : C.muted }}>{cat}</Text>
              </TouchableOpacity>
            ))}
          </View>
        </ScrollView>

        {/* Template Count */}
        <Text style={{ fontSize: 11, color: C.muted, fontWeight: '600' }}>{tx('templatesView.toolbar.templatesCount', '{count} templates').replace('{count}', String(filtered.length))}</Text>
      </View>

      {/* ═══ GALLERY VIEW ═══ */}
      {viewMode === 'gallery' && (
        <View>
          {/* Send result toast */}
          {sendResult && (
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, padding: 10, marginBottom: 12, borderRadius: 10, backgroundColor: sendResult.ok ? (globalThis as any).__alphaColor(C.green, '12') : C.red + '12', borderWidth: 1, borderColor: sendResult.ok ? (globalThis as any).__alphaColor(C.green, '25') : C.red + '25' }} data-testid="gallery-toast" testID="gallery-toast">
              <Ionicons name={sendResult.ok ? 'checkmark-circle' : 'alert-circle'} size={16} color={sendResult.ok ? C.green : C.red} />
              <Text style={{ color: sendResult.ok ? C.green : C.red, fontSize: 11, fontWeight: '600', flex: 1 }}>{sendResult.msg}</Text>
              <TouchableOpacity onPress={() => onSendResult(null)} accessibilityLabel={tx('admin.templatesView.auto.accessibility.001', 'Close gallery toast')}><Ionicons name="close" size={14} color={C.muted} /></TouchableOpacity>
            </View>
          )}

          {catalogLoading ? (
            <View style={{ padding: 60, alignItems: 'center' }}><ActivityIndicator size="large" color={C.blue} /><Text style={{ color: C.muted, marginTop: 10, fontSize: 12 }}>{tx('templatesView.states.loadingGallery', 'Loading gallery...')}</Text></View>
          ) : (
            <>
            {/* Batch Theme Audit Results */}
            {batchAuditResult && !batchAuditRunning && (
              <View style={{ backgroundColor: C.card, borderRadius: 14, borderWidth: 1, borderColor: C.border, marginBottom: 14, overflow: 'hidden' }} data-testid="batch-audit-results" testID="batch-audit-results">
                {/* Audit header */}
                <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', padding: 14, borderBottomWidth: 1, borderBottomColor: C.border }}>
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
                    <Ionicons name="shield-checkmark" size={16} color={batchAuditResult.summary?.failed === 0 ? C.green : C.purple} />
                    <Text style={{ color: C.text, fontSize: 13, fontWeight: '800' }}>{tx('templatesView.audit.batchThemeAudit', 'Batch Theme Audit')}</Text>
                    <View style={{ paddingHorizontal: 8, paddingVertical: 2, borderRadius: 99, backgroundColor: batchAuditResult.summary?.failed === 0 ? (globalThis as any).__alphaColor(C.green, '15') : C.red + '15' }}>
                      <Text style={{ fontSize: 10, fontWeight: '800', color: batchAuditResult.summary?.failed === 0 ? C.green : C.red }}>{tx('templatesView.audit.passRate', '{rate}% pass').replace('{rate}', String(batchAuditResult.summary?.pass_rate ?? 0))}</Text>
                    </View>
                  </View>
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                    <Text style={{ fontSize: 10, color: C.muted }}>{tx('templatesView.audit.templatesClean', '{passed}/{total} templates clean').replace('{passed}', String(batchAuditResult.summary?.passed ?? 0)).replace('{total}', String(batchAuditResult.summary?.total ?? 0))}</Text>
                    <TouchableOpacity onPress={() => setBatchAuditResult(null)} data-testid="batch-audit-close" testID="batch-audit-close">
                      <Ionicons name="close" size={14} color={C.muted} />
                    </TouchableOpacity>
                  </View>
                </View>
                {/* Failed templates list */}
                {(batchAuditResult.results || []).filter((r: any) => r.status !== 'pass').length > 0 && (
                  <View style={{ padding: 12, gap: 6 }}>
                    {(batchAuditResult.results || []).filter((r: any) => r.status !== 'pass').map((r: any) => (
                      <View key={r.key} style={{ flexDirection: 'row', alignItems: 'flex-start', gap: 10, padding: 10, borderRadius: 10, backgroundColor: r.status === 'critical' ? (globalThis as any).__alphaColor(C.red, '08') : C.purple + '06', borderWidth: 1, borderColor: r.status === 'critical' ? (globalThis as any).__alphaColor(C.red, '20') : C.border }}>
                        <Ionicons name={r.status === 'critical' ? 'alert-circle' : 'warning'} size={14} color={r.status === 'critical' ? C.red : 'var(--app-warning)'} style={{ marginTop: 2 }} />
                        <View style={{ flex: 1 }}>
                          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                            <Text style={{ color: C.text, fontSize: 11, fontWeight: '700' }}>{r.label}</Text>
                            <View style={{ paddingHorizontal: 6, paddingVertical: 1, borderRadius: 99, backgroundColor: (globalThis as any).__alphaColor(C.purple, '10') }}>
                              <Text style={{ color: C.purpleText, fontSize: 8, fontWeight: '700' }}>{r.category}</Text>
                            </View>
                          </View>
                          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 4, marginTop: 4 }}>
                            {(r.issues || []).map((issue: any, idx: number) => (
                              <View key={idx} style={{ flexDirection: 'row', alignItems: 'center', gap: 3, paddingHorizontal: 6, paddingVertical: 2, borderRadius: 6, backgroundColor: issue.severity === 'critical' ? (globalThis as any).__alphaColor(C.red, '12') : issue.severity === 'high' ? C.warningSoft : C.border + '60' }}>
                                <View style={{ width: 5, height: 5, borderRadius: 3, backgroundColor: issue.severity === 'critical' ? C.red : issue.severity === 'high' ? C.warning : C.muted }} />
                                <Text style={{ fontSize: 9, color: C.muted, fontWeight: '600' }}>{issue.theme}: {issue.type.replace(/_/g, ' ')}</Text>
                              </View>
                            ))}
                          </View>
                        </View>
                        <TouchableOpacity onPress={() => openFullscreen({ key: r.key, label: r.label, category: r.category, description: '' } as CatalogItem)} accessibilityLabel={tx('admin.templatesView.auto.accessibility.002', 'Expand template audit')} style={{ padding: 4 }}>
                          <Ionicons name="expand" size={12} color={C.blue} />
                        </TouchableOpacity>
                      </View>
                    ))}
                  </View>
                )}
                {/* All pass message */}
                {(batchAuditResult.results || []).filter((r: any) => r.status !== 'pass').length === 0 && (
                  <View style={{ padding: 20, alignItems: 'center' }}>
                    <Ionicons name="checkmark-circle" size={28} color={C.green} />
                    <Text style={{ color: C.green, fontSize: 13, fontWeight: '700', marginTop: 6 }}>{tx('templatesView.audit.allPass', 'All {count} templates pass theme audit').replace('{count}', String(batchAuditResult.summary?.total ?? 0))}</Text>
                  </View>
                )}
              </View>
            )}
            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 14 }}>
              {filtered.map(t => {
                const icon = CATEGORY_ICONS[t.category] || 'mail';
                const cachedHtml = galleryHtmlCache[t.key]?.[galleryTheme] || '';
                const isSending = gallerySendingKey === t.key;
                return (
                  <View key={t.key} style={{ width: galleryCols === 1 ? '100%' as any : `${Math.floor(100 / galleryCols) - 1}%` as any, backgroundColor: C.card, borderRadius: 14, borderWidth: 1, borderColor: C.border, overflow: 'hidden' }} data-testid={`gallery-card-${t.key}`} testID={`gallery-card-${t.key}`}>
                    {/* Card header */}
                    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, padding: 12, borderBottomWidth: 1, borderBottomColor: C.border }}>
                      <View style={{ width: 28, height: 28, borderRadius: 8, backgroundColor: (globalThis as any).__alphaColor(C.blue, '14'), alignItems: 'center', justifyContent: 'center' }}>
                        <Ionicons name={icon as any} size={12} color={C.blue} />
                      </View>
                      <View style={{ flex: 1 }}>
                        <Text style={{ color: C.text, fontSize: 12, fontWeight: '700' }} numberOfLines={1}>{t.label}</Text>
                        <Text style={{ color: C.muted, fontSize: 9, marginTop: 1 }} numberOfLines={1}>{t.description}</Text>
                      </View>
                      <View style={{ paddingHorizontal: 7, paddingVertical: 2, borderRadius: 99, backgroundColor: (globalThis as any).__alphaColor(C.purple, '12') }}>
                        <Text style={{ color: C.purpleText, fontSize: 8, fontWeight: '800' }}>{t.category}</Text>
                      </View>
                    </View>
                    {/* Thumbnail */}
                    <View style={{ height: 260, backgroundColor: galleryTheme === 'dark' ? 'var(--app-text)' : C.surface }}>
                      {cachedHtml ? (
                        Platform.OS === 'web' ? (
                          <iframe srcDoc={cachedHtml} style={{ width: '100%', height: '100%', border: 'none', pointerEvents: 'none' } as any} title={t.label} sandbox="allow-same-origin" tabIndex={-1} />
                        ) : <Text style={{ color: C.muted, padding: 16, fontSize: 11 }}>{tx('templatesView.preview.webOnly', 'Web only')}</Text>
                      ) : (
                        <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center' }}>
                          <ActivityIndicator size="small" color={C.blue} />
                          <Text style={{ color: C.muted, fontSize: 9, marginTop: 6 }}>{tx('templatesView.preview.loading', 'Loading preview...')}</Text>
                        </View>
                      )}
                    </View>
                    {/* Actions */}
                    <View style={{ flexDirection: 'row', padding: 10, gap: 6, borderTopWidth: 1, borderTopColor: C.border }}>
                      <TouchableOpacity onPress={() => openFullscreen(t)} style={{ flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 5, paddingVertical: 8, borderRadius: 8, backgroundColor: (globalThis as any).__alphaColor(C.blue, '10'), borderWidth: 1, borderColor: (globalThis as any).__alphaColor(C.blue, '25') }} data-testid={`gallery-preview-${t.key}`} testID={`gallery-preview-${t.key}`}>
                        <Ionicons name="expand" size={12} color={C.blue} />
                        <Text style={{ color: C.blue, fontSize: 10, fontWeight: '700' }}>{tx('templatesView.actions.preview', 'Preview')}</Text>
                      </TouchableOpacity>
                      <TouchableOpacity onPress={() => galleryQuickSend(t.key)} disabled={isSending} style={{ flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 5, paddingVertical: 8, borderRadius: 8, backgroundColor: isSending ? (globalThis as any).__alphaColor(C.green, '25') : C.green + '10', borderWidth: 1, borderColor: (globalThis as any).__alphaColor(C.green, '25'), opacity: isSending ? 0.7 : 1 }} data-testid={`gallery-send-${t.key}`} testID={`gallery-send-${t.key}`}>
                        {isSending ? <ActivityIndicator size={10} color={C.green} /> : <Ionicons name="mail-outline" size={12} color={C.green} />}
                        <Text style={{ color: C.green, fontSize: 10, fontWeight: '700' }}>{isSending ? tx('templatesView.toolbar.sending', 'Sending...') : tx('templatesView.actions.send', 'Send')}</Text>
                      </TouchableOpacity>
                      <TouchableOpacity onPress={() => { setViewMode('list'); loadPreview(t.key); }} style={{ flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 5, paddingVertical: 8, borderRadius: 8, backgroundColor: (globalThis as any).__alphaColor(C.purple, '10'), borderWidth: 1, borderColor: (globalThis as any).__alphaColor(C.purple, '25') }} data-testid={`gallery-edit-${t.key}`} testID={`gallery-edit-${t.key}`}>
                        <Ionicons name="create-outline" size={12} color={C.purpleText} />
                        <Text style={{ color: C.purpleText, fontSize: 10, fontWeight: '700' }}>{tx('templatesView.actions.edit', 'Edit')}</Text>
                      </TouchableOpacity>
                    </View>
                  </View>
                );
              })}
            </View>
            </>
          )}
        </View>
      )}

      {/* ═══ FULLSCREEN MODAL ═══ */}
      {fullscreenItem && Platform.OS === 'web' && (
        <View style={{ position: 'absolute' as any, top: 0, left: 0, right: 0, bottom: 0, zIndex: 999 } as any}>
          <div style={{ position: 'fixed', inset: 0, zIndex: 9999, backgroundColor: 'rgba(0,0,0,0.7)', backdropFilter: 'blur(8px)', display: 'flex', flexDirection: 'column', overflow: 'auto' } as any} data-testid="fullscreen-modal" role="button" tabIndex={0} onClick={(e: any) => { if (e.target === e.currentTarget) setFullscreenItem(null); }}>
            {/* Modal header */}
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '16px 24px', background: 'rgba(15,23,42,0.95)', borderBottom: '1px solid var(--app-text)', flexShrink: 0 } as any}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 12 } as any}>
                <span style={{ fontSize: 15, fontWeight: 800, color: C.text } as any}>{fullscreenItem.label}</span>
                <span style={{ fontSize: 11, color: C.textMuted, background: C.surface, padding: '3px 10px', borderRadius: 99 } as any}>{fullscreenItem.category}</span>
                <span style={{ fontSize: 11, color: C.textMuted } as any}>{tx('templatesView.preview.sideBySideComparison', 'Side-by-side dark/light comparison')}</span>
              </div>
              <button onClick={() => setFullscreenItem(null)} style={{ background: C.surface, border: '1px solid var(--app-primary)', borderRadius: 8, padding: '6px 14px', color: C.textMuted, fontSize: 12, fontWeight: 700, cursor: 'pointer' } as any} data-testid="fullscreen-close-btn">{tx('templatesView.common.close', 'Close')}</button>
            </div>
            {/* Side-by-side */}
            {fullscreenLoading ? (
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', flex: 1, padding: 60 } as any}>
                <ActivityIndicator size="large" color={'var(--app-primary)'} />
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'row', gap: 16, padding: 20, flex: 1, minHeight: 0 } as any}>
                {(['light', 'dark'] as const).map(theme => (
                  <div key={theme} style={{ flex: 1, display: 'flex', flexDirection: 'column', borderRadius: 12, overflow: 'hidden', border: theme === 'dark' ? '1px solid var(--app-text)' : '1px solid var(--app-primary)', background: theme === 'dark' ? 'var(--app-text)' : C.surfaceHover } as any}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '10px 16px', background: theme === 'dark' ? C.surface : C.surface, borderBottom: theme === 'dark' ? '1px solid var(--app-text)' : '1px solid var(--app-text-muted)' } as any}>
                      <span style={{ width: 8, height: 8, borderRadius: 4, background: theme === 'dark' ? 'var(--app-primary)' : 'var(--app-warning)' } as any} />
                      <span style={{ fontSize: 12, fontWeight: 700, color: theme === 'dark' ? C.textMuted : C.textSec, textTransform: 'capitalize' } as any}>{tx('templatesView.preview.mode', '{theme} Mode').replace('{theme}', theme)}</span>
                    </div>
                    <iframe srcDoc={fullscreenHtml[theme]} style={{ width: '100%', flex: 1, border: 'none', minHeight: 600 }} title={`${fullscreenItem.label} ${theme}`} sandbox="allow-same-origin" />
                  </div>
                ))}
              </div>
            )}
          </div>
        </View>
      )}

      {/* ═══ LIST/DETAIL VIEW ═══ */}
      {viewMode === 'list' && (
    <View style={{ flexDirection: isWide ? 'row' : 'column', gap: 16 }}>
      {/* Template List */}
      <View style={{ width: isWide ? 280 : '100%' as any }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
          <Text style={{ fontSize: 14, fontWeight: '700', color: C.text }}>{tx('templatesView.list.templatesCount', 'Templates ({count})').replace('{count}', String(catalog.length))}</Text>
        </View>

        <View style={{ backgroundColor: C.card, borderRadius: 12, borderWidth: 1, borderColor: C.border, padding: 12, marginBottom: 10 }} data-testid="template-gallery-footer-standard-card" testID="template-gallery-footer-standard-card">
          <Text style={{ fontSize: 10, fontWeight: '800', color: C.accent, letterSpacing: 0.8, textTransform: 'uppercase' }}>{tx('admin.templatesView.auto.text.001', 'Permanent Footer Standard')}</Text>
          <Text style={{ fontSize: 15, fontWeight: '800', color: C.text, marginTop: 6 }}>Locked across all {footerGallerySummary.templates} templates</Text>
          <Text style={{ fontSize: 10, lineHeight: 16, color: C.muted, marginTop: 4 }}>{tx('admin.templatesView.auto.text.002', 'Exact-match badge block, shared CTA/footer system, theme-ready preview, and responsive coverage for mobile/tablet/desktop/web.')}</Text>
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginTop: 10 }}>
            <View style={{ paddingHorizontal: 8, paddingVertical: 4, borderRadius: 999, backgroundColor: (globalThis as any).__alphaColor(C.green, '18'), borderWidth: 1, borderColor: (globalThis as any).__alphaColor(C.green, '35') }} data-testid="template-gallery-standard-shared-footer-chip" testID="template-gallery-standard-shared-footer-chip">
              <Text style={{ fontSize: 9, fontWeight: '700', color: C.green }}>{tx('admin.templatesView.auto.text.003', 'Shared Footer')}</Text>
            </View>
            <View style={{ paddingHorizontal: 8, paddingVertical: 4, borderRadius: 999, backgroundColor: (globalThis as any).__alphaColor(C.blue, '18'), borderWidth: 1, borderColor: (globalThis as any).__alphaColor(C.blue, '35') }} data-testid="template-gallery-standard-badge-lock-chip" testID="template-gallery-standard-badge-lock-chip">
              <Text style={{ fontSize: 9, fontWeight: '700', color: C.blue }}>Badge Lock {footerGallerySummary.badgeBlock ? `${footerGallerySummary.badgeBlock.width}×${footerGallerySummary.badgeBlock.height}` : '—'}</Text>
            </View>
            <View style={{ paddingHorizontal: 8, paddingVertical: 4, borderRadius: 999, backgroundColor: (globalThis as any).__alphaColor(C.purple, '18'), borderWidth: 1, borderColor: (globalThis as any).__alphaColor(C.purple, '35') }} data-testid="template-gallery-standard-theme-chip" testID="template-gallery-standard-theme-chip">
              <Text style={{ fontSize: 9, fontWeight: '700', color: C.purpleText }}>{tx('admin.templatesView.auto.text.004', 'Light + Dark')}</Text>
            </View>
            <View style={{ paddingHorizontal: 8, paddingVertical: 4, borderRadius: 999, backgroundColor: (globalThis as any).__alphaColor(C.indigo, '18'), borderWidth: 1, borderColor: (globalThis as any).__alphaColor(C.indigo, '35') }} data-testid="template-gallery-standard-header-footer-dark-chip" testID="template-gallery-standard-header-footer-dark-chip">
              <Text style={{ fontSize: 9, fontWeight: '700', color: C.indigoText }}>{tx('admin.templatesView.auto.text.005', 'Header + Footer Dark')}</Text>
            </View>
          </View>
          <Text style={{ fontSize: 9, color: C.muted, marginTop: 10 }} data-testid="template-gallery-standard-version-text" testID="template-gallery-standard-version-text">Footer Version: <Text style={{ color: C.text, fontWeight: '700' }}>{footerGallerySummary.version}</Text></Text>
          <Text style={{ fontSize: 9, color: C.muted, marginTop: 2 }} data-testid="template-gallery-standard-updated-text" testID="template-gallery-standard-updated-text">Last Updated: <Text style={{ color: C.text, fontWeight: '700' }}>{footerGallerySummary.updatedAt}</Text></Text>
        </View>

        {/* Automated Quality Audit */}
        <View style={{ backgroundColor: C.card, borderRadius: 10, borderWidth: 1, borderColor: C.border, padding: 10, marginBottom: 10 }} data-testid="template-audit-card" testID="template-audit-card">
          <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8, marginBottom: 8 }}>
            <View style={{ flex: 1 }}>
              <Text style={{ fontSize: 12, fontWeight: '700', color: C.text }}>{tx('admin.templatesView.auto.text.006', 'Enterprise Template QA')}</Text>
              <Text style={{ fontSize: 10, color: C.muted }}>{tx('admin.templatesView.auto.text.007', 'Checks links, badges, dark mode and responsive markers')}</Text>
            </View>
            <View style={{ flexDirection: 'row', gap: 6, flexWrap: 'wrap', justifyContent: 'flex-end' }}>
              <TouchableOpacity
                onPress={() => { void activateFixFailingTemplates(); }}
                disabled={!auditFailures.length}
                style={{ paddingHorizontal: 10, paddingVertical: 8, borderRadius: 8, backgroundColor: auditFailures.length ? C.red : C.border }}
                data-testid="fix-failing-templates-btn" testID="fix-failing-templates-btn"
              >
                <Text style={{ color: C.primaryText, fontSize: 10, fontWeight: '700' }}>{tx('admin.templatesView.auto.text.008', 'Fix Failing Templates')}</Text>
              </TouchableOpacity>
              <TouchableOpacity
                onPress={runTemplateAudit}
                disabled={auditRunning}
                style={{ paddingHorizontal: 10, paddingVertical: 8, borderRadius: 8, backgroundColor: auditRunning ? C.border : C.indigo }}
                data-testid="run-template-audit-btn" testID="run-template-audit-btn"
              >
                {auditRunning ? <ActivityIndicator size="small" color={C.primaryText} /> : <Text style={{ color: C.primaryText, fontSize: 10, fontWeight: '700' }}>{tx('admin.templatesView.auto.text.009', 'Run Audit')}</Text>}
              </TouchableOpacity>
            </View>
          </View>

          {auditSummary ? (
            <View data-testid="template-audit-summary" testID="template-audit-summary">
              <View style={{ flexDirection: 'row', gap: 8, flexWrap: 'wrap', marginBottom: auditFailures.length ? 8 : 0 }}>
                <Text style={{ fontSize: 10, color: C.muted }}>Templates: <Text style={{ color: C.text, fontWeight: '700' }}>{auditSummary.templates_total}</Text></Text>
                <Text style={{ fontSize: 10, color: C.green }}>Pass: <Text style={{ color: C.green, fontWeight: '700' }}>{auditSummary.templates_passed}</Text></Text>
                <Text style={{ fontSize: 10, color: auditSummary.templates_failed ? C.red : C.green }}>Fail: <Text style={{ color: auditSummary.templates_failed ? C.red : C.green, fontWeight: '700' }}>{auditSummary.templates_failed}</Text></Text>
                <Text style={{ fontSize: 10, color: C.muted }}>Links: <Text style={{ color: C.text, fontWeight: '700' }}>{auditSummary.total_links_checked}</Text></Text>
                <Text style={{ fontSize: 10, color: C.muted }}>Footer: <Text style={{ color: C.text, fontWeight: '700' }}>{auditSummary.footer_version || '—'}</Text></Text>
              </View>
              {auditFailures.length > 0 && (
                <View data-testid="template-audit-failures" testID="template-audit-failures">
                  {auditFailures.slice(0, 3).map((f: any) => (
                    <Text key={f.key} style={{ fontSize: 10, color: C.red }} numberOfLines={1}>• {f.label}: {(f.issues || []).join(', ') || 'link issues'}</Text>
                  ))}
                </View>
              )}

              {failedOnlyMode && (
                <View style={{ marginTop: 8, borderTopWidth: 1, borderTopColor: C.border, paddingTop: 8 }} data-testid="failed-template-fix-mode-panel" testID="failed-template-fix-mode-panel">
                  <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
                    <Text style={{ fontSize: 10, color: C.muted }}>{tx('admin.templatesView.auto.text.010', 'Fix mode active: only failing templates shown')}</Text>
                    <TouchableOpacity accessibilityLabel={tx('admin.templatesView.auto.accessibility.003', 'Exit Fix Mode')}
                      onPress={() => {
                        setFailedOnlyMode(false);
                        setIssueFilter(null);
                      }}
                      data-testid="exit-failed-template-fix-mode-btn" testID="exit-failed-template-fix-mode-btn"
                    >
                      <Text style={{ fontSize: 10, color: C.blue, fontWeight: '700' }}>{tx('admin.templatesView.auto.text.011', 'Exit Fix Mode')}</Text>
                    </TouchableOpacity>
                  </View>

                  {failedIssueOptions.length > 0 && (
                    <ScrollView horizontal showsHorizontalScrollIndicator={false} data-testid="failed-template-issue-chip-list" testID="failed-template-issue-chip-list">
                      <View style={{ flexDirection: 'row', gap: 6 }}>
                        <TouchableOpacity
                          onPress={() => setIssueFilter(null)}
                          style={{ paddingHorizontal: 8, paddingVertical: 5, borderRadius: 999, borderWidth: 1, borderColor: !issueFilter ? (globalThis as any).__alphaColor(C.blue, '40') : C.border, backgroundColor: !issueFilter ? (globalThis as any).__alphaColor(C.blue, '15') : 'transparent' }}
                          data-testid="failed-template-issue-chip-all" testID="failed-template-issue-chip-all"
                        >
                          <Text style={{ fontSize: 9, fontWeight: '700', color: !issueFilter ? C.blue : C.muted }}>{tx('admin.templatesView.auto.text.012', 'All Issues')}</Text>
                        </TouchableOpacity>
                        {failedIssueOptions.map(issue => (
                          <TouchableOpacity
                            key={issue}
                            onPress={() => setIssueFilter(issue)}
                            style={{ paddingHorizontal: 8, paddingVertical: 5, borderRadius: 999, borderWidth: 1, borderColor: issueFilter === issue ? (globalThis as any).__alphaColor(C.red, '45') : C.border, backgroundColor: issueFilter === issue ? (globalThis as any).__alphaColor(C.red, '15') : 'transparent' }}
                            data-testid={`failed-template-issue-chip-${issue.toLowerCase().replace(/[^a-z0-9]+/g, '-')}`} testID={`failed-template-issue-chip-${issue.toLowerCase().replace(/[^a-z0-9]+/g, '-')}`}
                          >
                            <Text style={{ fontSize: 9, fontWeight: '700', color: issueFilter === issue ? C.red : C.muted }}>{issue}</Text>
                          </TouchableOpacity>
                        ))}
                      </View>
                    </ScrollView>
                  )}
                </View>
              )}

              <View style={{ marginTop: 8, borderTopWidth: 1, borderTopColor: C.border, paddingTop: 8 }} data-testid="auto-fix-suggestions-panel" testID="auto-fix-suggestions-panel">
                <Text style={{ fontSize: 11, fontWeight: '700', color: C.text, marginBottom: 6 }}>{tx('admin.templatesView.auto.text.013', 'Auto-fix suggestions')}</Text>
                <View style={{ gap: 6 }}>
                  {autoFixSuggestions.slice(0, 3).map((s, idx) => (
                    <View key={`${s.issue}-${idx}`} style={{ borderWidth: 1, borderColor: C.border, borderRadius: 8, padding: 8, backgroundColor: C.bg }} data-testid={`auto-fix-suggestion-${idx}`} testID={`auto-fix-suggestion-${idx}`}>
                      <Text style={{ fontSize: 10, fontWeight: '700', color: C.text }}>{s.title}</Text>
                      <Text style={{ fontSize: 9, color: C.muted, marginTop: 4 }}>{s.guidance}</Text>
                      {s.issue && s.issue !== 'healthy' && s.issue !== 'generic' && (
                        <TouchableOpacity accessibilityLabel={tx('admin.templatesView.auto.accessibility.004', 'Focus issue in template editor')}
                          onPress={() => {
                            setFailedOnlyMode(true);
                            setIssueFilter(s.issue);
                          }}
                          style={{ marginTop: 6, alignSelf: 'flex-start', borderWidth: 1, borderColor: (globalThis as any).__alphaColor(C.blue, '45'), borderRadius: 999, paddingHorizontal: 8, paddingVertical: 4, backgroundColor: (globalThis as any).__alphaColor(C.blue, '12') }}
                          data-testid={`auto-fix-focus-issue-${s.issue.toLowerCase().replace(/[^a-z0-9]+/g, '-')}`} testID={`auto-fix-focus-issue-${s.issue.toLowerCase().replace(/[^a-z0-9]+/g, '-')}`}
                        >
                          <Text style={{ fontSize: 9, color: C.blue, fontWeight: '700' }}>{tx('admin.templatesView.auto.text.014', 'Focus this issue')}</Text>
                        </TouchableOpacity>
                      )}
                    </View>
                  ))}
                </View>
              </View>
            </View>
          ) : (
            <Text style={{ fontSize: 10, color: C.muted }} data-testid="template-audit-empty" testID="template-audit-empty">{tx('admin.templatesView.auto.text.015', 'Run audit to validate all templates end-to-end.')}</Text>
          )}
        </View>

        {/* Global Contrast Audit Control */}
        <View style={{ backgroundColor: C.card, borderRadius: 10, borderWidth: 1, borderColor: C.border, padding: 10, marginBottom: 10 }} data-testid="contrast-audit-card" testID="contrast-audit-card">
          <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8, marginBottom: 8 }}>
            <View style={{ flex: 1 }}>
              <Text style={{ fontSize: 12, fontWeight: '700', color: C.text }}>{tx('admin.templatesView.auto.text.016', 'Contrast Compliance')}</Text>
              <Text style={{ fontSize: 10, color: C.muted }}>{tx('admin.templatesView.auto.text.017', 'WCAG 4.5 ratio check across all templates')}</Text>
            </View>
            <TouchableOpacity
              onPress={runContrastAudit}
              disabled={contrastAuditRunning}
              style={{ paddingHorizontal: 10, paddingVertical: 8, borderRadius: 8, backgroundColor: contrastAuditRunning ? C.border : C.success }}
              data-testid="rerun-contrast-audit-btn" testID="rerun-contrast-audit-btn"
            >
              {contrastAuditRunning ? <ActivityIndicator size="small" color={C.primaryText} /> : <Text style={{ color: C.primaryText, fontSize: 10, fontWeight: '700' }}>{tx('admin.templatesView.auto.text.018', 'Re-run Contrast Audit')}</Text>}
            </TouchableOpacity>
          </View>
          {contrastResult ? (
            <View data-testid="contrast-audit-result" testID="contrast-audit-result">
              <View style={{ flexDirection: 'row', gap: 8, flexWrap: 'wrap', marginBottom: contrastResult.failed > 0 ? 8 : 0 }}>
                <Text style={{ fontSize: 10, color: C.muted }}>Rate: <Text style={{ color: contrastResult.rate >= 100 ? C.green : C.red, fontWeight: '700' }}>{contrastResult.rate}%</Text></Text>
                <Text style={{ fontSize: 10, color: C.green }}>Pass: <Text style={{ fontWeight: '700' }}>{contrastResult.passed}</Text></Text>
                <Text style={{ fontSize: 10, color: contrastResult.failed > 0 ? C.red : C.green }}>Fail: <Text style={{ fontWeight: '700' }}>{contrastResult.failed}</Text></Text>
                <Text style={{ fontSize: 10, color: C.muted }}>Total: <Text style={{ fontWeight: '700' }}>{contrastResult.total}</Text></Text>
              </View>
              {contrastResult.failed > 0 && contrastResult.failedList.slice(0, 3).map((f: any) => (
                <Text key={f.key} style={{ fontSize: 10, color: C.red }} numberOfLines={1}>• {f.label || f.key}: {(f.issues || []).join(', ')}</Text>
              ))}
              {contrastResult.rate >= 100 && (
                <Text style={{ fontSize: 10, color: C.green, fontWeight: '700' }}>{tx('admin.templatesView.auto.text.019', 'All templates pass WCAG 4.5 contrast ratio.')}</Text>
              )}
            </View>
          ) : (
            <Text style={{ fontSize: 10, color: C.muted }} data-testid="contrast-audit-empty" testID="contrast-audit-empty">{tx('admin.templatesView.auto.text.020', 'Click to verify contrast compliance across all email templates.')}</Text>
          )}
        </View>

        {/* Template Items */}
        <ScrollView style={{ maxHeight: isWide ? 500 : 320 }} data-testid="template-gallery-scroll-view" testID="template-gallery-scroll-view">
          {catalogLoading ? <ActivityIndicator size="small" color={C.blue} style={{ marginTop: 20 }} /> : filtered.map(t => {
            const icon = CATEGORY_ICONS[t.category] || 'mail';
            const tData = analytics?.by_type?.[t.key];
            const failMeta = (auditFailures || []).find((f: any) => f.key === t.key);
            const hasFailure = !!failMeta;
            return (
              <TouchableOpacity
                key={t.key} onPress={() => loadPreview(t.key)}
                style={{ padding: 12, borderRadius: 12, marginBottom: 8, backgroundColor: selected === t.key ? (globalThis as any).__alphaColor(C.blue, '12') : C.card, borderWidth: 1, borderColor: hasFailure ? (globalThis as any).__alphaColor(C.red, '45') : (selected === t.key ? C.blue + '40' : C.border) }}
                data-testid={`template-select-${t.key}`} testID={`template-select-${t.key}`}
              >
                <View style={{ flexDirection: 'row', alignItems: 'flex-start', gap: 10 }}>
                  <View style={{ width: 34, height: 34, borderRadius: 9, backgroundColor: selected === t.key ? (globalThis as any).__alphaColor(C.blue, '25') : C.border, alignItems: 'center', justifyContent: 'center' }}>
                    <Ionicons name={icon as any} size={14} color={selected === t.key ? C.blue : C.muted} />
                  </View>
                  <View style={{ flex: 1, minWidth: 0 }}>
                    <View style={{ flexDirection: 'row', justifyContent: 'space-between', gap: 8 }}>
                      <View style={{ flex: 1 }}>
                        <Text style={{ fontSize: 12, fontWeight: '700', color: selected === t.key ? C.blue : C.text }} numberOfLines={1}>{t.label}</Text>
                        <Text style={{ fontSize: 9, color: C.muted, marginTop: 2 }} numberOfLines={2}>{t.description}</Text>
                      </View>
                      {tData && tData.sent > 0 && (
                        <View style={{ paddingHorizontal: 7, paddingVertical: 4, borderRadius: 999, backgroundColor: (globalThis as any).__alphaColor(C.green, '16') }}>
                          <Text style={{ fontSize: 8, color: C.green, fontWeight: '800' }}>{tData.open_rate}% open</Text>
                        </View>
                      )}
                    </View>

                    <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginTop: 8 }}>
                      <View style={{ paddingHorizontal: 7, paddingVertical: 4, borderRadius: 999, backgroundColor: (globalThis as any).__alphaColor(C.green, '18'), borderWidth: 1, borderColor: (globalThis as any).__alphaColor(C.green, '35') }} data-testid={`template-shared-footer-chip-${t.key}`} testID={`template-shared-footer-chip-${t.key}`}>
                        <Text style={{ fontSize: 8, fontWeight: '800', color: C.green }}>{tx('admin.templatesView.auto.text.021', 'Shared Footer')}</Text>
                      </View>
                      <View style={{ paddingHorizontal: 7, paddingVertical: 4, borderRadius: 999, backgroundColor: (globalThis as any).__alphaColor(C.blue, '18'), borderWidth: 1, borderColor: (globalThis as any).__alphaColor(C.blue, '35') }} data-testid={`template-badge-lock-chip-${t.key}`} testID={`template-badge-lock-chip-${t.key}`}>
                        <Text style={{ fontSize: 8, fontWeight: '800', color: C.blue }}>Badge {t.footer_badge_block ? `${t.footer_badge_block.width}×${t.footer_badge_block.height}` : 'Lock'}</Text>
                      </View>
                      <View style={{ paddingHorizontal: 7, paddingVertical: 4, borderRadius: 999, backgroundColor: (globalThis as any).__alphaColor(C.purple, '18'), borderWidth: 1, borderColor: (globalThis as any).__alphaColor(C.purple, '35') }} data-testid={`template-theme-chip-${t.key}`} testID={`template-theme-chip-${t.key}`}>
                        <Text style={{ fontSize: 8, fontWeight: '800', color: C.purpleText }}>{(t.footer_theme_support || []).join(' + ') || 'Themes'}</Text>
                      </View>
                      <View style={{ paddingHorizontal: 7, paddingVertical: 4, borderRadius: 999, backgroundColor: (globalThis as any).__alphaColor(C.indigo, '18'), borderWidth: 1, borderColor: (globalThis as any).__alphaColor(C.indigo, '35') }} data-testid={`template-header-footer-dark-chip-${t.key}`} testID={`template-header-footer-dark-chip-${t.key}`}>
                        <Text style={{ fontSize: 8, fontWeight: '800', color: C.indigoText }}>{t.header_footer_theme_status === 'validated_dark_mode' ? 'Header + Footer Dark' : 'Header/Footer Theme'}</Text>
                      </View>
                    </View>

                    <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginTop: 8, gap: 8 }}>
                      <View style={{ flex: 1 }}>
                        <Text style={{ fontSize: 8, color: C.muted }} numberOfLines={1}>Version: <Text style={{ color: C.text, fontWeight: '700' }}>{t.footer_version || '—'}</Text></Text>
                        <Text style={{ fontSize: 8, color: C.muted, marginTop: 2 }} numberOfLines={1}>Updated: <Text style={{ color: C.text, fontWeight: '700' }}>{t.footer_last_updated || '—'}</Text></Text>
                      </View>
                      <View style={{ flexDirection: 'row', gap: 8, alignItems: 'center' }}>
                        {hasFailure && (
                          <View style={{ backgroundColor: (globalThis as any).__alphaColor(C.red, '18'), borderRadius: 999, paddingHorizontal: 6, paddingVertical: 3 }} data-testid={`template-failure-badge-${t.key}`} testID={`template-failure-badge-${t.key}`}>
                            <Text style={{ fontSize: 8, color: C.red, fontWeight: '700' }}>{tx('admin.templatesView.auto.text.022', 'FAIL')}</Text>
                          </View>
                        )}
                        <TouchableOpacity
                          onPress={(e) => { e.stopPropagation(); onQuickCreateAbTest(t.key); }}
                          disabled={!!creatingTest}
                          style={{ width: 28, height: 28, borderRadius: 8, backgroundColor: creatingTest === t.key ? (globalThis as any).__alphaColor(C.indigo, '40') : C.indigo + '15', alignItems: 'center', justifyContent: 'center' }}
                          data-testid={`create-ab-${t.key}`} testID={`create-ab-${t.key}`}
                        >
                          {creatingTest === t.key ? <ActivityIndicator size={10} color={C.indigoText} /> : <Ionicons name="git-compare" size={12} color={C.indigoText} />}
                        </TouchableOpacity>
                        {selected === t.key && <Ionicons name="chevron-forward" size={12} color={C.blue} />}
                      </View>
                    </View>
                  </View>
                </View>
              </TouchableOpacity>
            );
          })}
        </ScrollView>
      </View>

      {/* Preview + Send Test */}
      <View style={{ flex: 1 }}>
        {!selected ? (
          <View style={{ backgroundColor: C.card, borderRadius: 14, padding: 40, alignItems: 'center', justifyContent: 'center', borderWidth: 1, borderColor: C.border, minHeight: 300 }}>
            <Ionicons name="mail-open-outline" size={48} color={C.border} />
            <Text style={{ fontSize: 15, color: C.muted, marginTop: 12 }}>{tx('admin.templatesView.auto.text.023', 'Select a template to preview')}</Text>
            <Text style={{ fontSize: 11, color: C.muted, marginTop: 4 }}>{catalog.length} templates across {categories.length} categories</Text>
          </View>
        ) : (
          <View>
            {/* Viewport Toggle + Subject */}
            <View style={{ backgroundColor: C.card, borderRadius: 12, padding: 14, marginBottom: 12, borderWidth: 1, borderColor: C.border }}>
              <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8, flexWrap: 'wrap', gap: 8 }}>
                <View style={{ flex: 1, minWidth: 150 }}>
                  <Text style={{ fontSize: 11, color: C.muted, marginBottom: 4 }}>{tx('admin.templatesView.auto.text.024', 'Subject Line')}</Text>
                  <Text style={{ fontSize: 14, fontWeight: '600', color: C.text }} numberOfLines={2} data-testid="template-preview-subject" testID="template-preview-subject">{previewSubject || '...'}</Text>
                  <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10, marginTop: 6 }} data-testid="template-preview-footer-meta" testID="template-preview-footer-meta">
                    <Text style={{ fontSize: 10, color: C.muted }} data-testid="template-preview-footer-version" testID="template-preview-footer-version">Footer Version: <Text style={{ color: C.text, fontWeight: '700' }}>{previewFooterVersion || selectedCatalogItem?.footer_version || '—'}</Text></Text>
                    <Text style={{ fontSize: 10, color: C.muted }} data-testid="template-preview-footer-updated" testID="template-preview-footer-updated">Last Updated: <Text style={{ color: C.text, fontWeight: '700' }}>{previewFooterUpdatedAt || selectedCatalogItem?.footer_last_updated || '—'}</Text></Text>
                  </View>
                  <View style={{ flexDirection: 'row', alignItems: 'center', flexWrap: 'wrap', gap: 6, marginTop: 6 }} data-testid="preview-quality-chips" testID="preview-quality-chips">
                    {[
                      { id: 'responsive', label: 'Responsive', pass: previewChecks.responsive },
                      { id: 'dark', label: 'Dark CSS', pass: previewChecks.darkMode },
                      { id: 'header-dark', label: 'Header Dark', pass: previewChecks.sharedHeaderDark },
                      { id: 'badges', label: 'Store Badges', pass: previewChecks.officialBadges },
                      { id: 'badge-lock', label: 'Badge Lock', pass: previewChecks.badgeLock },
                      { id: 'shared-footer', label: 'Shared Footer', pass: previewChecks.sharedFooter },
                      { id: 'secondary', label: 'Secondary CTA', pass: previewChecks.secondaryCta },
                    ].map(chip => (
                      <View key={chip.id} style={{ paddingHorizontal: 8, paddingVertical: 3, borderRadius: 8, backgroundColor: chip.pass ? (globalThis as any).__alphaColor(C.green, '18') : C.red + '18', borderWidth: 1, borderColor: chip.pass ? (globalThis as any).__alphaColor(C.green, '35') : C.red + '35' }} data-testid={`preview-check-${chip.id}`} testID={`preview-check-${chip.id}`}>
                        <Text style={{ fontSize: 9, fontWeight: '700', color: chip.pass ? C.green : C.red }}>{chip.label}</Text>
                      </View>
                    ))}
                  </View>
                </View>
                {Platform.OS === 'web' && (
                  <View style={{ flexDirection: 'row', gap: 8, alignItems: 'center' }}>
                    <View style={{ flexDirection: 'row', gap: 4, backgroundColor: C.bg, borderRadius: 8, padding: 3 }} data-testid="viewport-toggle" testID="viewport-toggle">
                      {VIEWPORT_OPTS.map(v => (
                        <TouchableOpacity key={v.w} onPress={() => setPreviewWidth(v.w)} style={{ flexDirection: 'row', alignItems: 'center', gap: 4, paddingVertical: 5, paddingHorizontal: 10, borderRadius: 6, backgroundColor: previewWidth === v.w ? (globalThis as any).__alphaColor(C.blue, '20') : 'transparent', borderWidth: 1, borderColor: previewWidth === v.w ? (globalThis as any).__alphaColor(C.blue, '40') : 'transparent' }} data-testid={`viewport-${v.label.toLowerCase()}`} testID={`viewport-${v.label.toLowerCase()}`}>
                          <Ionicons name={v.icon as any} size={12} color={previewWidth === v.w ? C.blue : C.muted} />
                          <Text style={{ fontSize: 10, fontWeight: '600', color: previewWidth === v.w ? C.blue : C.muted }}>{v.label}</Text>
                        </TouchableOpacity>
                      ))}
                    </View>
                    <View style={{ flexDirection: 'row', backgroundColor: C.bg, borderRadius: 8, padding: 3 }} data-testid="theme-toggle" testID="theme-toggle">
                      <TouchableOpacity onPress={() => setPreviewTheme('dark')} style={{ flexDirection: 'row', alignItems: 'center', gap: 4, paddingVertical: 5, paddingHorizontal: 10, borderRadius: 6, backgroundColor: previewTheme === 'dark' ? (globalThis as any).__alphaColor(C.blue, '25') : 'transparent', borderWidth: 1, borderColor: previewTheme === 'dark' ? (globalThis as any).__alphaColor(C.blue, '50') : 'transparent' }} data-testid="theme-dark-btn" testID="theme-dark-btn">
                        <Ionicons name="moon" size={12} color={previewTheme === 'dark' ? 'var(--app-primary)' : C.muted} />
                        <Text style={{ fontSize: 10, fontWeight: '600', color: previewTheme === 'dark' ? C.primary : C.muted }}>{tx('admin.templatesView.auto.text.025', 'Dark')}</Text>
                      </TouchableOpacity>
                      <TouchableOpacity onPress={() => setPreviewTheme('light')} style={{ flexDirection: 'row', alignItems: 'center', gap: 4, paddingVertical: 5, paddingHorizontal: 10, borderRadius: 6, backgroundColor: previewTheme === 'light' ? (globalThis as any).__alphaColor(C.amber, '25') : 'transparent', borderWidth: 1, borderColor: previewTheme === 'light' ? (globalThis as any).__alphaColor(C.amber, '50') : 'transparent' }} data-testid="theme-light-btn" testID="theme-light-btn">
                        <Ionicons name="sunny" size={12} color={previewTheme === 'light' ? 'var(--app-warning)' : C.muted} />
                        <Text style={{ fontSize: 10, fontWeight: '600', color: previewTheme === 'light' ? C.warning : C.muted }}>{tx('admin.templatesView.auto.text.026', 'Light')}</Text>
                      </TouchableOpacity>
                    </View>
                    <TouchableOpacity
                      onPress={openPreviewWindow}
                      style={{ flexDirection: 'row', alignItems: 'center', gap: 4, paddingVertical: 8, paddingHorizontal: 12, borderRadius: 8, backgroundColor: C.card, borderWidth: 1, borderColor: C.border }}
                      data-testid="open-preview-window-btn" testID="open-preview-window-btn"
                    >
                      <Ionicons name="open-outline" size={12} color={C.blue} />
                      <Text style={{ fontSize: 10, fontWeight: '700', color: C.blue }}>{tx('admin.templatesView.auto.text.027', 'Open Live Preview')}</Text>
                    </TouchableOpacity>
                    <TouchableOpacity
                      onPress={() => setCompareMode(!compareMode)}
                      style={{ flexDirection: 'row', alignItems: 'center', gap: 4, paddingVertical: 8, paddingHorizontal: 12, borderRadius: 8, backgroundColor: compareMode ? (globalThis as any).__alphaColor(C.green, '20') : C.card, borderWidth: 1, borderColor: compareMode ? (globalThis as any).__alphaColor(C.green, '50') : C.border }}
                      data-testid="compare-mode-btn" testID="compare-mode-btn"
                    >
                      <Ionicons name="git-compare-outline" size={12} color={compareMode ? 'var(--app-success)' : C.muted} />
                      <Text style={{ fontSize: 10, fontWeight: '700', color: compareMode ? C.success : C.muted }}>{tx('admin.templatesView.auto.text.028', 'Compare')}</Text>
                    </TouchableOpacity>
                    {isBillingTemplate && (
                      <View style={{ flexDirection: 'row', backgroundColor: C.bg, borderRadius: 8, padding: 3, alignItems: 'center', gap: 2 }} data-testid="plan-tier-switcher" testID="plan-tier-switcher">
                        <Ionicons name="pricetag-outline" size={11} color={C.muted} style={{ marginRight: 4, marginLeft: 4 }} />
                        {([
                          { id: '' as const, label: 'Default', price: '' },
                          { id: 'free' as const, label: 'Free', price: '$0' },
                          { id: 'basic' as const, label: 'Basic', price: '$5.99' },
                          { id: 'premium' as const, label: 'Premium', price: '$15.99' },
                        ]).map((p) => (
                          <TouchableOpacity
                            key={p.id}
                            onPress={() => setPlanTier(p.id)}
                            style={{ paddingVertical: 5, paddingHorizontal: 10, borderRadius: 6, backgroundColor: planTier === p.id ? (globalThis as any).__alphaColor(C.teal, '25') : 'transparent', borderWidth: 1, borderColor: planTier === p.id ? (globalThis as any).__alphaColor(C.teal, '50') : 'transparent' }}
                            data-testid={`plan-tier-${p.id || 'default'}`} testID={`plan-tier-${p.id || 'default'}`}
                          >
                            <Text style={{ fontSize: 10, fontWeight: '700', color: planTier === p.id ? C.accent : C.muted }}>{p.label}{p.price ? ` ${p.price}` : ''}</Text>
                          </TouchableOpacity>
                        ))}
                      </View>
                    )}
                  </View>
                )}
              </View>
            </View>

            {/* Per-Template Analytics Mini-Card */}
            {selAnalytics && (
              <View style={{ backgroundColor: C.card, borderRadius: 12, padding: 14, marginBottom: 12, borderWidth: 1, borderColor: C.border }} data-testid="template-mini-analytics" testID="template-mini-analytics">
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 10 }}>
                  <Ionicons name="pulse-outline" size={14} color={C.indigoText} />
                  <Text style={{ fontSize: 12, fontWeight: '700', color: C.text }}>{tx('admin.templatesView.auto.text.029', 'Template Analytics')}</Text>
                </View>
                <View style={{ flexDirection: 'row', gap: 10, flexWrap: 'wrap' }}>
                  <View style={{ flex: 1, minWidth: 80 }}>
                    <Text style={{ fontSize: 20, fontWeight: '800', color: C.text }}>{selAnalytics.sent}</Text>
                    <Text style={{ fontSize: 9, color: C.muted }}>{tx('admin.templatesView.auto.text.030', 'Sent')}</Text>
                  </View>
                  <View style={{ flex: 1, minWidth: 80 }}>
                    <Text style={{ fontSize: 20, fontWeight: '800', color: C.green }}>{selAnalytics.opened}</Text>
                    <Text style={{ fontSize: 9, color: C.muted }}>{tx('admin.templatesView.auto.text.031', 'Opened')}</Text>
                  </View>
                  <View style={{ flex: 1, minWidth: 80 }}>
                    <Text style={{ fontSize: 20, fontWeight: '800', color: C.blue }}>{selAnalytics.clicked}</Text>
                    <Text style={{ fontSize: 9, color: C.muted }}>{tx('admin.templatesView.auto.text.032', 'Clicked')}</Text>
                  </View>
                  <View style={{ flex: 1.5, minWidth: 100 }}>
                    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4, marginBottom: 4 }}>
                      <Text style={{ fontSize: 10, color: C.muted }}>{tx('admin.templatesView.auto.text.033', 'Open')}</Text>
                      <Text style={{ fontSize: 12, fontWeight: '800', color: C.green }}>{selAnalytics.open_rate}%</Text>
                    </View>
                    <RateBar rate={selAnalytics.open_rate} color={C.green} />
                  </View>
                  <View style={{ flex: 1.5, minWidth: 100 }}>
                    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4, marginBottom: 4 }}>
                      <Text style={{ fontSize: 10, color: C.muted }}>{tx('admin.templatesView.auto.text.034', 'Click')}</Text>
                      <Text style={{ fontSize: 12, fontWeight: '800', color: C.blue }}>{selAnalytics.click_rate}%</Text>
                    </View>
                    <RateBar rate={selAnalytics.click_rate} color={C.blue} />
                  </View>
                </View>
              </View>
            )}

            {/* HTML Preview */}
            {compareMode ? (
              <View style={{ flexDirection: 'row', gap: 12, marginBottom: 12 }} data-testid="template-compare-frame" testID="template-compare-frame">
                {(['dark', 'light'] as const).map((theme) => (
                  <View key={theme} style={{ flex: 1, backgroundColor: theme === 'dark' ? 'var(--app-primary)' : C.textSec, borderRadius: 12, overflow: 'hidden', borderWidth: 1, borderColor: C.border, minHeight: 400, padding: 12 }}>
                    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 8 }}>
                      <Ionicons name={theme === 'dark' ? 'moon' : 'sunny'} size={12} color={theme === 'dark' ? 'var(--app-primary)' : 'var(--app-warning)'} />
                      <Text style={{ fontSize: 11, fontWeight: '700', color: theme === 'dark' ? C.textMuted : C.textSec, textTransform: 'capitalize' }}>{theme} Mode</Text>
                    </View>
                    {loading ? (
                      <View style={{ padding: 40, alignItems: 'center' }}><ActivityIndicator size="large" color={C.blue} /></View>
                    ) : Platform.OS === 'web' ? (
                      <div style={{ width: '100%', maxWidth: '100%', background: theme === 'dark' ? 'var(--app-text)' : C.surface, borderRadius: 8, overflow: 'hidden', boxShadow: theme === 'dark' ? '0 4px 24px rgba(0,0,0,0.3)' : '0 4px 16px rgba(15,23,42,0.1)', border: theme === 'dark' ? '1px solid var(--app-text)' : '1px solid var(--app-primary)' } as any}>
                        <iframe
                          srcDoc={compareHtml[theme] || previewHtml}
                          style={{ width: '100%', minHeight: 500, border: 'none', display: 'block' }}
                          title={`Email Preview ${theme}`}
                          sandbox="allow-same-origin allow-popups allow-popups-to-escape-sandbox allow-top-navigation-by-user-activation"
                          data-testid={`template-compare-iframe-${theme}`}
                        />
                      </div>
                    ) : (
                      <Text style={{ padding: 16, color: C.textSec }}>{tx('admin.templatesView.auto.text.035', 'Preview available on web only')}</Text>
                    )}
                  </View>
                ))}
              </View>
            ) : (
            <View style={{ backgroundColor: previewTheme === 'dark' ? 'var(--app-primary)' : C.textSec, borderRadius: 12, overflow: 'hidden', marginBottom: 12, borderWidth: 1, borderColor: C.border, minHeight: 400, alignItems: 'center', padding: 16 }} data-testid="template-preview-frame" testID="template-preview-frame">
              <View style={{ width: '100%', flexDirection: 'row', justifyContent: 'space-between', marginBottom: 10 }} data-testid="template-preview-mode-indicator" testID="template-preview-mode-indicator">
                <Text style={{ fontSize: 10, color: C.muted }}>Theme: <Text style={{ color: C.text, fontWeight: '700' }}>{previewTheme}</Text></Text>
                <Text style={{ fontSize: 10, color: C.muted }}>Viewport: <Text style={{ color: C.text, fontWeight: '700' }}>{previewWidth}px</Text></Text>
              </View>
              {loading ? (
                <View style={{ padding: 40, alignItems: 'center' }}><ActivityIndicator size="large" color={C.blue} /></View>
              ) : Platform.OS === 'web' ? (
                <div style={{ width: previewWidth, maxWidth: '100%', transition: 'width 0.3s ease', background: previewTheme === 'dark' ? 'var(--app-text)' : C.surface, borderRadius: 8, overflow: 'hidden', boxShadow: previewTheme === 'dark' ? '0 4px 24px rgba(0,0,0,0.3)' : '0 4px 16px rgba(15,23,42,0.1)', border: previewTheme === 'dark' ? '1px solid var(--app-text)' : '1px solid var(--app-primary)' } as any}>
                  <iframe srcDoc={previewHtml} style={{ width: '100%', minHeight: 600, border: 'none', display: 'block' }} title="Email Preview" sandbox="allow-same-origin allow-popups allow-popups-to-escape-sandbox allow-top-navigation-by-user-activation" data-testid="template-preview-iframe" />
                </div>
              ) : (
                <Text style={{ padding: 16, color: C.textSec }}>{tx('admin.templatesView.auto.text.036', 'Preview available on web only')}</Text>
              )}
            </View>
            )}

            {/* Send Test */}
            <View style={{ backgroundColor: C.card, borderRadius: 12, padding: 16, borderWidth: 1, borderColor: C.border }} data-testid="template-send-test-section" testID="template-send-test-section">
              <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
                <Text style={{ fontSize: 14, fontWeight: '700', color: C.text }}>{tx('admin.templatesView.auto.text.037', 'Send Test Email')}</Text>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: previewTheme === 'dark' ? C.surface : 'var(--app-card-bg)', paddingHorizontal: 10, paddingVertical: 4, borderRadius: 6 }}>
                  <Ionicons name={previewTheme === 'dark' ? 'moon' : 'sunny'} size={12} color={previewTheme === 'dark' ? C.textMuted : 'var(--app-text-muted)'} />
                  <Text style={{ fontSize: 11, fontWeight: '600', color: previewTheme === 'dark' ? C.textMuted : C.primary }}>{previewTheme === 'dark' ? 'Dark mode' : 'Light mode'}</Text>
                </View>
              </View>
              <View style={{ flexDirection: 'row', gap: 8, flexWrap: 'wrap' }}>
                <TextInput value={testEmail} onChangeText={setTestEmail} placeholder={tx('admin.templatesView.auto.placeholder.001', 'Recipient email')} placeholderTextColor={C.muted} style={{ flex: 1, minWidth: 180, backgroundColor: C.bg, borderRadius: 10, padding: 12, color: C.text, fontSize: 14, borderWidth: 1, borderColor: C.border }} data-testid="template-test-email-input" testID="template-test-email-input" />
                <TouchableOpacity onPress={sendTest} disabled={sending || !testEmail} style={{ backgroundColor: sending ? C.border : C.blue, borderRadius: 10, paddingHorizontal: 18, paddingVertical: 12, flexDirection: 'row', gap: 6, alignItems: 'center' }} data-testid="template-send-test-btn" testID="template-send-test-btn">
                  {sending ? <ActivityIndicator size="small" color={C.primaryText} /> : <><Ionicons name="send" size={14} color={C.primaryText} /><Text style={{ color: C.primaryText, fontWeight: '700', fontSize: 13 }}>{tx('admin.templatesView.auto.text.038', 'Send')}</Text></>}
                </TouchableOpacity>
                <TouchableOpacity onPress={sendAllTests} disabled={bulkSending || !testEmail} style={{ backgroundColor: bulkSending ? C.border : C.purple, borderRadius: 10, paddingHorizontal: 18, paddingVertical: 12, flexDirection: 'row', gap: 6, alignItems: 'center' }} data-testid="template-send-all-btn" testID="template-send-all-btn">
                  {bulkSending ? (
                    <><ActivityIndicator size="small" color={C.primaryText} /><Text style={{ color: C.primaryText, fontWeight: '600', fontSize: 12 }}>{bulkProgress.sent + bulkProgress.failed}/{bulkProgress.total}</Text></>
                  ) : (
                    <><Ionicons name="paper-plane" size={14} color={C.primaryText} /><Text style={{ color: C.primaryText, fontWeight: '700', fontSize: 12 }}>Send All ({catalog.length})</Text></>
                  )}
                </TouchableOpacity>
              </View>
              {sendResult && (
                <View style={{ marginTop: 10, flexDirection: 'row', alignItems: 'center', gap: 6, padding: 10, borderRadius: 8, backgroundColor: sendResult.ok ? (globalThis as any).__alphaColor(C.green, '15') : C.red + '15' }}>
                  <Ionicons name={sendResult.ok ? 'checkmark-circle' : 'close-circle'} size={16} color={sendResult.ok ? C.green : C.red} />
                  <Text style={{ fontSize: 12, color: sendResult.ok ? C.green : C.red, fontWeight: '500', flex: 1 }} data-testid="template-send-result" testID="template-send-result">{sendResult.msg}</Text>
                </View>
              )}
            </View>

            {/* Per-Type Delivery Stats */}
            {selected && stats?.by_type?.[selected] && (
              <View style={{ backgroundColor: C.card, borderRadius: 12, padding: 16, marginTop: 12, borderWidth: 1, borderColor: C.border }}>
                <Text style={{ fontSize: 13, fontWeight: '600', color: C.text, marginBottom: 8 }}>{tx('admin.templatesView.auto.text.039', 'Delivery Stats')}</Text>
                <View style={{ flexDirection: 'row', gap: 16 }}>
                  <Text style={{ fontSize: 13, color: C.green }}>{stats.by_type[selected].sent || 0} sent</Text>
                  <Text style={{ fontSize: 13, color: C.red }}>{stats.by_type[selected].failed || 0} failed</Text>
                  <Text style={{ fontSize: 13, color: C.muted }}>{stats.by_type[selected].total || 0} total</Text>
                </View>
              </View>
            )}
          </View>
        )}
      </View>
    </View>
      )}
    </View>
  );
}
