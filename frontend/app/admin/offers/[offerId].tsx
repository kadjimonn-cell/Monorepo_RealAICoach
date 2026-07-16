/**
 * Offer Studio — /admin/offers/[offerId]
 * Enterprise-grade page to build, preview, send, rescind, and monitor an offer.
 * Opens in a new tab when the recruiter clicks Offer on an application.
 *
 * declined / rescinded pills) and `var(--app-primary-text)` on the red rescind button are
 * intentional brand tokens. Structural chrome uses `colors.*` from useTheme().
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { ActivityIndicator, Platform, ScrollView, Text, TextInput, TouchableOpacity, View, useWindowDimensions } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useLocalSearchParams, useRouter } from 'expo-router';
import api from '../../../src/services/api';
import { useTheme } from '../../../src/context/ThemeContext';
import { useTranslation } from '../../../src/hooks/useTranslation';
import { resolveRuntimeBaseUrl } from '../../../src/utils/runtimeBaseUrl';
import { handleAppRecoverableError } from '../../../src/utils/appRecoverableError';

// Brand accent for the AI Draft action + the PDF error banner palette.
// Theme-exempt — these are explicit semantic/brand stops, not surface chrome.
const AI_BRAND_TEAL = 'var(--app-primary)';
const AI_BRAND_TEAL_SOFT = 'var(--app-primary-soft)';
const PDF_ERROR_BG = 'var(--app-error)';
const PDF_ERROR_BORDER = 'var(--app-error)';
const PDF_ERROR_ACCENT = 'var(--app-error)';

const STATE_COLORS: Record<string, { bg: string; fg: string; label: string }> = {
  draft:     { bg: 'var(--app-bg)', fg: 'var(--app-primary)', label: 'Draft' },
  sent:      { bg: 'var(--app-bg)', fg: 'var(--app-primary)', label: 'Sent' },
  viewed:    { bg: 'var(--app-bg)', fg: 'var(--app-primary)', label: 'Viewed' },
  accepted:  { bg: 'var(--app-bg)', fg: 'var(--app-primary)', label: 'Accepted' },
  declined:  { bg: 'var(--app-bg)', fg: 'var(--app-primary)', label: 'Declined' },
  expired:   { bg: 'var(--app-bg)', fg: 'var(--app-primary)', label: 'Expired' },
  rescinded: { bg: 'var(--app-bg)', fg: 'var(--app-error)', label: 'Rescinded' },
};

type OfferStudioScreenProps = {
  forcedOfferId?: string;
};

export function OfferStudioScreen({ forcedOfferId }: OfferStudioScreenProps = {}) {
  const params = useLocalSearchParams<{ offerId?: string; id?: string; offer?: string }>();
  const routeOfferId = (() => {
    const oid = params?.offerId;
    if (Array.isArray(oid)) return oid[0] || '';
    if (typeof oid === 'string' && oid) return oid;
    const id = params?.id;
    if (Array.isArray(id)) return id[0] || '';
    if (typeof id === 'string' && id) return id;
    const offer = params?.offer;
    if (Array.isArray(offer)) return offer[0] || '';
    if (typeof offer === 'string' && offer) return offer;
    return '';
  })();
  const offerId = String(forcedOfferId || routeOfferId || '').trim();
  const { colors } = useTheme();
  const { t } = useTranslation();
  const tx = useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);
  const { width } = useWindowDimensions();
  const router = useRouter();
  const isMobile = width < 900;

  const [loading, setLoading] = useState(true);
  const [offer, setOffer] = useState<any | null>(null);
  const [saving, setSaving] = useState(false);
  const [aiBusy, setAiBusy] = useState(false);
  const [msg, setMsg] = useState('');
  const [benchmark, setBenchmark] = useState<any | null>(null);
  const [rescindModal, setRescindModal] = useState(false);
  const [rescindReason, setRescindReason] = useState('');
  const [brandingModal, setBrandingModal] = useState(false);
  const [brandingDoc, setBrandingDoc] = useState<any>({});
  const [brandingSaving, setBrandingSaving] = useState(false);
  const [pdfError, setPdfError] = useState<{ code: string; missing: string[]; message: string } | null>(null);
  const [pdfCacheBust, setPdfCacheBust] = useState(0);
  const studioLabel = t('offerStudio.header.label');

  const fetchOffer = useCallback(async () => {
    try {
      const res = await api.get(`/careers/offers/${offerId}`);
      setOffer(res.data);
    } catch (e: any) {
      setMsg(e?.response?.data?.detail || 'Failed to load offer.');
    }
    setLoading(false);
  }, [offerId]);

  const fetchBenchmark = useCallback(async (roleTitle?: string) => {
    if (!roleTitle) return;
    try {
      const res = await api.get(`/careers/offers/benchmark?role_title=${encodeURIComponent(roleTitle)}`);
      setBenchmark(res.data);
    } catch (error) {
      handleAppRecoverableError({
        scope: 'admin.offer.fetch-benchmark',
        error,
        message: 'Benchmark data is temporarily unavailable.',
        setError: setMsg,
        onRetry: () => { void fetchBenchmark(roleTitle); },
      
        notifyMode: 'dialog',
        userInitiated: true,
      });
    }
  }, []);

  useEffect(() => { if (offerId) fetchOffer(); }, [offerId, fetchOffer]);
  useEffect(() => { if (offer?.role_title) fetchBenchmark(offer.role_title); }, [offer?.role_title, fetchBenchmark]);
  useEffect(() => {
    // Real-time poll every 10s while sent/viewed → picks up candidate events
    if (!offer || !['sent', 'viewed'].includes(offer.state)) return;
    const t = setInterval(() => fetchOffer(), 10000);
    return () => clearInterval(t);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [offer?.state, fetchOffer]);

  const updateField = (key: string, value: any) => setOffer((prev: any) => ({ ...prev, [key]: value }));

  const handleSave = async () => {
    setSaving(true); setMsg('');
    try {
      const patchable = ['base_salary_usd', 'bonus_target_pct', 'equity_shares', 'equity_pct',
        'signing_bonus_usd', 'relocation_usd', 'pto_days', 'start_date', 'reporting_manager',
        'work_location', 'work_city', 'expiry_days', 'personal_message', 'offer_body_md'];
      const body: any = {};
      patchable.forEach(k => { if (offer[k] !== undefined && offer[k] !== null) body[k] = offer[k]; });
      const res = await api.patch(`/careers/offers/${offerId}`, body);
      setOffer(res.data);
      setMsg('✓ Saved.');
    } catch (e: any) { setMsg(e?.response?.data?.detail || 'Save failed.'); }
    setSaving(false);
  };

  const handleAiDraft = async () => {
    setAiBusy(true); setMsg('');
    try {
      const res = await api.post(`/careers/offers/${offerId}/ai-draft-body`, { tone: 'warm' });
      if (res.data?.body) { updateField('offer_body_md', res.data.body); setMsg('✓ AI draft applied.'); }
    } catch (e: any) { setMsg(e?.response?.data?.detail || 'AI draft failed.'); }
    setAiBusy(false);
  };

  const handleSend = async () => {
    setSaving(true); setMsg('');
    try {
      // save first
      await handleSave();
      const res = await api.post(`/careers/offers/${offerId}/send`);
      setOffer(res.data);
      setMsg(res.data.email_sent ? '🚀 Offer sent! Candidate email delivered.' : '⚠ Sent, but email delivery failed.');
    } catch (e: any) { setMsg(e?.response?.data?.detail || 'Send failed.'); }
    setSaving(false);
  };

  const handleRescind = async () => {
    if (!rescindReason.trim()) { setMsg('Please provide a reason.'); return; }
    setSaving(true); setMsg('');
    try {
      const res = await api.post(`/careers/offers/${offerId}/rescind`, { reason: rescindReason });
      setOffer(res.data); setRescindModal(false); setRescindReason('');
      setMsg('🛑 Offer rescinded. Candidate notified.');
    } catch (e: any) { setMsg(e?.response?.data?.detail || 'Rescind failed.'); }
    setSaving(false);
  };

  const pdfUrl = useMemo(() => {
    const base = resolveRuntimeBaseUrl();
    const bust = pdfCacheBust ? `?t=${pdfCacheBust}` : '';
    return `${base}/api/careers/offers/${offerId}/pdf${bust}`;
  }, [offerId, pdfCacheBust]);

  // Detect PDF errors via HEAD probe so the admin knows before scrolling to the iframe
  const probePdf = useCallback(async () => {
    try {
      const res = await api.get(`/careers/offers/${offerId}/pdf`, { responseType: 'blob', validateStatus: () => true });
      if (res.status === 200) { setPdfError(null); return; }
      // read the error body
      if (res.data && res.data.text) {
        const txt = await res.data.text();
        try {
          const j = JSON.parse(txt);
          setPdfError(j?.detail || null);
        } catch (error) {
          handleAppRecoverableError({
            scope: 'admin.offer.probe-pdf-parse',
            error,
            message: 'Offer PDF diagnostic response could not be parsed.',
            setError: setMsg,
            onRetry: () => { void probePdf(); },
          
        notifyMode: 'dialog',
        userInitiated: true,
      });
          setPdfError(null);
        }
      }
    } catch (error) {
      handleAppRecoverableError({
        scope: 'admin.offer.probe-pdf',
        error,
        message: 'Unable to probe PDF status right now.',
        setError: setMsg,
        onRetry: () => { void probePdf(); },
      
        notifyMode: 'dialog',
        userInitiated: true,
      });
    }
  }, [offerId]);
  useEffect(() => { if (offer) probePdf(); }, [offer?.updated_at, offer?.base_salary_usd, offer?.candidate_address, offer?.department, offer?.start_date, offer?.employment_type, pdfCacheBust, probePdf, offer]);

  const openBranding = useCallback(async () => {
    try {
      const res = await api.get('/careers/offer-branding');
      setBrandingDoc(res.data?.branding || {});
    } catch (error) {
      handleAppRecoverableError({
        scope: 'admin.offer.open-branding',
        error,
        message: 'Could not load branding settings right now.',
        setError: setMsg,
        onRetry: () => { void openBranding(); },
      
        notifyMode: 'dialog',
        userInitiated: true,
      });
      setBrandingDoc({});
    }
    setBrandingModal(true);
  }, []);

  const handleSaveBranding = async () => {
    setBrandingSaving(true); setMsg('');
    try {
      const payload: any = {};
      ['legal_name', 'hq_address', 'signer_name', 'signer_title', 'signer_signature_image'].forEach((k) => {
        if (brandingDoc[k] !== undefined && brandingDoc[k] !== null && String(brandingDoc[k]).trim() !== '') {
          payload[k] = String(brandingDoc[k]).trim();
        }
      });
      if (Object.keys(payload).length === 0) { setMsg('Fill at least one field.'); setBrandingSaving(false); return; }
      const res = await api.put('/careers/offer-branding', payload);
      setBrandingDoc(res.data?.branding || {});
      setBrandingModal(false);
      setPdfCacheBust(Date.now()); // refresh PDF preview
      setMsg('✓ Offer branding saved. PDF preview refreshed.');
    } catch (e: any) { setMsg(e?.response?.data?.detail || 'Failed to save branding.'); }
    setBrandingSaving(false);
  };

  if (loading) {
    return (
      <View style={{ flex: 1, backgroundColor: colors.bg, justifyContent: 'center', alignItems: 'center' }} data-testid="offer-studio-loading" testID="offer-studio-loading">
        <ActivityIndicator color={colors.primary} size="large" />
      </View>
    );
  }
  if (!offer) {
    return (
      <View style={{ flex: 1, backgroundColor: colors.bg, justifyContent: 'center', alignItems: 'center', padding: 24 }}>
        <Ionicons name="alert-circle" size={44} color={colors.error} />
        <Text style={{ color: colors.text, fontSize: 18, fontWeight: '700', marginTop: 10 }}>{tx('offerStudio.states.notFound', 'Offer not found')}</Text>
        <Text style={{ color: colors.textSec, fontSize: 13, marginTop: 4 }}>{msg || tx('offerStudio.states.notFoundDesc', 'We could not load that offer.')}</Text>
      </View>
    );
  }

  const st = STATE_COLORS[offer.state] || STATE_COLORS.draft;
  const editable = offer.state === 'draft';

  return (
    <ScrollView style={{ flex: 1, backgroundColor: colors.bg }} contentContainerStyle={{ paddingBottom: 80 }}>
      {/* Header */}
      <View style={{ padding: isMobile ? 16 : 32, paddingBottom: 20, borderBottomWidth: 1, borderBottomColor: colors.border }}>
        <View style={{ flexDirection: isMobile ? 'column' : 'row', gap: 16, justifyContent: 'space-between', alignItems: isMobile ? 'flex-start' : 'center' }}>
          <View style={{ flex: 1 }}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
              <TouchableOpacity onPress={() => router.back()} data-testid="offer-back-btn" testID="offer-back-btn">
                <Ionicons name="arrow-back" size={20} color={colors.textSec} />
              </TouchableOpacity>
              <Text style={{ color: colors.textMuted, fontSize: 11, fontWeight: '700', letterSpacing: 1 }}>{studioLabel === 'offerStudio.header.label' ? 'OFFER STUDIO' : studioLabel}</Text>
            </View>
            <Text style={{ color: colors.text, fontSize: isMobile ? 22 : 28, fontWeight: '800', marginTop: 6, letterSpacing: -0.5 }}>
              {offer.candidate_name} · {offer.role_title}
            </Text>
            <View style={{ flexDirection: 'row', gap: 8, marginTop: 8, alignItems: 'center' }}>
              <View style={{ backgroundColor: st.bg, paddingHorizontal: 10, paddingVertical: 4, borderRadius: 10 }} data-testid="offer-state-badge" testID="offer-state-badge">
                <Text style={{ color: st.fg, fontSize: 11, fontWeight: '800' }}>{st.label.toUpperCase()}</Text>
              </View>
              <Text style={{ color: colors.textDim, fontSize: 12 }}>{offer.offer_id}</Text>
              {offer.view_count > 0 && <Text style={{ color: colors.textSec, fontSize: 12 }}>· 👁 {offer.view_count}{t("autofix.watchSweep1.view")}{offer.view_count !== 1 ? 's' : ''}</Text>}
              {offer.open_count > 0 && <Text style={{ color: colors.textSec, fontSize: 12 }}>· ✉ {offer.open_count}{t("autofix.watchSweep1.open")}{offer.open_count !== 1 ? 's' : ''}</Text>}
            </View>
          </View>
          {/* Action buttons */}
          <View style={{ flexDirection: 'row', gap: 8, flexWrap: 'wrap' }}>
            {editable && (
              <TouchableOpacity onPress={handleSave} disabled={saving}
                style={{ paddingHorizontal: 16, paddingVertical: 10, borderRadius: 10, borderWidth: 1, borderColor: colors.border }}
                data-testid="offer-save-btn" testID="offer-save-btn">
                <Text style={{ color: colors.text, fontWeight: '700', fontSize: 13 }}>{tx('offerStudio.actions.saveDraft', 'Save draft')}</Text>
              </TouchableOpacity>
            )}
            {editable && (
              <TouchableOpacity onPress={handleSend} disabled={saving || !offer.base_salary_usd || !offer.candidate_email}
                style={{ paddingHorizontal: 18, paddingVertical: 10, borderRadius: 10, backgroundColor: colors.primary, flexDirection: 'row', alignItems: 'center', gap: 6 }}
                data-testid="offer-send-btn" testID="offer-send-btn">
                {saving ? <ActivityIndicator size="small" color={colors.primaryText} /> : <Ionicons name="send" size={14} color={colors.primaryText} />}
                <Text style={{ color: colors.primaryText, fontWeight: '800', fontSize: 13 }}>{tx('offerStudio.actions.sendOffer', 'Send offer')}</Text>
              </TouchableOpacity>
            )}
            {(['sent', 'viewed', 'accepted'] as string[]).includes(offer.state) && (
              <TouchableOpacity onPress={() => setRescindModal(true)}
                style={{ paddingHorizontal: 16, paddingVertical: 10, borderRadius: 10, borderWidth: 1, borderColor: colors.error }}
                data-testid="offer-rescind-btn" testID="offer-rescind-btn">
                <Text style={{ color: colors.error, fontWeight: '700', fontSize: 13 }}>{tx('offerStudio.actions.rescind', 'Rescind')}</Text>
              </TouchableOpacity>
            )}
            <TouchableOpacity onPress={openBranding}
              style={{ paddingHorizontal: 16, paddingVertical: 10, borderRadius: 10, borderWidth: 1, borderColor: colors.border, flexDirection: 'row', alignItems: 'center', gap: 4 }}
              data-testid="offer-branding-btn" testID="offer-branding-btn">
              <Ionicons name="business" size={14} color={colors.textSec} />
              <Text style={{ color: colors.text, fontWeight: '700', fontSize: 13 }}>{tx('offerStudio.actions.branding', 'Branding')}</Text>
            </TouchableOpacity>
            <TouchableOpacity onPress={() => Platform.OS === 'web' && (window as any).open(pdfUrl, '_blank')}
              style={{ paddingHorizontal: 16, paddingVertical: 10, borderRadius: 10, borderWidth: 1, borderColor: colors.border, flexDirection: 'row', alignItems: 'center', gap: 4 }}
              data-testid="offer-pdf-btn" testID="offer-pdf-btn">
              <Ionicons name="document" size={14} color={colors.textSec} />
              <Text style={{ color: colors.text, fontWeight: '700', fontSize: 13 }}>{tx('offerStudio.actions.pdf', 'PDF')}</Text>
            </TouchableOpacity>
          </View>
        </View>
        {msg ? <Text style={{ color: msg.startsWith('✓') || msg.startsWith('🚀') ? colors.success : (msg.startsWith('🛑') || msg.startsWith('⚠') ? colors.warning : colors.error), fontSize: 13, marginTop: 12, fontWeight: '600' }} data-testid="offer-msg" testID="offer-msg">{msg}</Text> : null}
      </View>

      {/* 2-column: builder + side panel */}
      <View style={{ flexDirection: isMobile ? 'column' : 'row', gap: 16, padding: isMobile ? 16 : 32 }}>
        {/* LEFT: Builder */}
        <View style={{ flex: 2, gap: 12 }}>
          <SectionCard title="Compensation" colors={colors}>
            <Field label="Base salary (USD)" value={offer.base_salary_usd} onChange={(v) => updateField('base_salary_usd', parseInt(v) || 0)} editable={editable} colors={colors} testId="field-base-salary" />
            <Field label="Target bonus (% of base)" value={offer.bonus_target_pct} onChange={(v) => updateField('bonus_target_pct', parseInt(v) || 0)} editable={editable} colors={colors} testId="field-bonus-pct" />
            <Field label="Signing bonus (USD)" value={offer.signing_bonus_usd} onChange={(v) => updateField('signing_bonus_usd', parseInt(v) || 0)} editable={editable} colors={colors} testId="field-signing" />
            <Field label="Equity — shares" value={offer.equity_shares} onChange={(v) => updateField('equity_shares', parseInt(v) || null)} editable={editable} colors={colors} testId="field-equity-shares" />
            <Field label="Relocation allowance (USD)" value={offer.relocation_usd} onChange={(v) => updateField('relocation_usd', parseInt(v) || 0)} editable={editable} colors={colors} testId="field-relocation" />
            <Field label="PTO (days per year)" value={offer.pto_days} onChange={(v) => updateField('pto_days', parseInt(v) || 20)} editable={editable} colors={colors} testId="field-pto" />
          </SectionCard>

          <SectionCard title="Logistics" colors={colors}>
            <Field label="Start date (YYYY-MM-DD)" value={offer.start_date} onChange={(v) => updateField('start_date', v)} editable={editable} colors={colors} testId="field-start" />
            <Field label="Reporting manager" value={offer.reporting_manager} onChange={(v) => updateField('reporting_manager', v)} editable={editable} colors={colors} testId="field-manager" />
            <Field label="Work location" value={offer.work_location} onChange={(v) => updateField('work_location', v)} editable={editable} colors={colors} testId="field-worklocation" hint="remote / hybrid / onsite" />
            <Field label="Work city (optional)" value={offer.work_city} onChange={(v) => updateField('work_city', v)} editable={editable} colors={colors} testId="field-workcity" />
            <Field label="Expiry window (days)" value={offer.expiry_days} onChange={(v) => updateField('expiry_days', Math.max(2, Math.min(14, parseInt(v) || 5)))} editable={editable} colors={colors} testId="field-expiry" hint="2–14 days" />
          </SectionCard>

          <SectionCard title="Personal note & body" colors={colors}
            headerRight={editable ? (
              <TouchableOpacity onPress={handleAiDraft} disabled={aiBusy}
                style={{ flexDirection: 'row', alignItems: 'center', gap: 4, backgroundColor: AI_BRAND_TEAL_SOFT, borderWidth: 1, borderColor: AI_BRAND_TEAL, paddingHorizontal: 10, paddingVertical: 5, borderRadius: 8 }}
                data-testid="offer-ai-draft-btn" testID="offer-ai-draft-btn">
                {aiBusy ? <ActivityIndicator size="small" color={AI_BRAND_TEAL} /> : <Ionicons name="sparkles" size={12} color={AI_BRAND_TEAL} />}
                <Text style={{ color: AI_BRAND_TEAL, fontSize: 11, fontWeight: '700' }}>{aiBusy ? 'Drafting…' : 'AI Draft Body'}</Text>
              </TouchableOpacity>
            ) : null}>
            <Text style={{ color: colors.textMuted, fontSize: 10, fontWeight: '700', letterSpacing: 0.5, marginBottom: 4 }}>{t("autofix.watchSweep1.personal.message.shown.at.top.of.letter")}</Text>
            {Platform.OS === 'web' && (
              <textarea
                value={offer.personal_message || ''}
                onChange={(e: any) => updateField('personal_message', e.target.value)}
                disabled={!editable}
                rows={2}
                data-testid="field-personal-msg"
                style={{ width: '100%', padding: 10, borderRadius: 8, border: `1px solid ${colors.border}`, backgroundColor: colors.bgAlt, color: colors.text, fontSize: 13, fontFamily: 'inherit', resize: 'vertical' as any, outline: 'none', marginBottom: 12, boxSizing: 'border-box' as any }}
              />
            )}
            <Text style={{ color: colors.textMuted, fontSize: 10, fontWeight: '700', letterSpacing: 0.5, marginBottom: 4 }}>OFFER LETTER BODY</Text>
            {Platform.OS === 'web' && (
              <textarea
                value={offer.offer_body_md || ''}
                onChange={(e: any) => updateField('offer_body_md', e.target.value)}
                disabled={!editable}
                rows={7}
                placeholder="Write the body of the offer letter (or click AI Draft Body for a Claude-powered start)."
                data-testid="field-body"
                style={{ width: '100%', padding: 10, borderRadius: 8, border: `1px solid ${colors.border}`, backgroundColor: colors.bgAlt, color: colors.text, fontSize: 13, fontFamily: 'inherit', resize: 'vertical' as any, outline: 'none', boxSizing: 'border-box' as any }}
              />
            )}
          </SectionCard>

          {/* Event timeline */}
          {(offer.events && offer.events.length > 0) && (
            <SectionCard title="Event timeline" colors={colors}>
              {offer.events.slice().reverse().map((ev: any, i: number) => (
                <View key={i} style={{ flexDirection: 'row', gap: 10, paddingVertical: 6, borderBottomWidth: i === offer.events.length - 1 ? 0 : 1, borderBottomColor: colors.border }} data-testid={`offer-event-${i}`} testID={`offer-event-${i}`}>
                  <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: colors.primary, marginTop: 6 }} />
                  <View style={{ flex: 1 }}>
                    <Text style={{ color: colors.text, fontSize: 13, fontWeight: '600' }}>{ev.type.replace(/_/g, ' ').replace(/\b\w/g, (c: string) => c.toUpperCase())}</Text>
                    <Text style={{ color: colors.textDim, fontSize: 11 }}>{new Date(ev.ts).toLocaleString()}</Text>
                    {ev.meta && Object.keys(ev.meta).length > 0 && (
                      <Text style={{ color: colors.textSec, fontSize: 11 }}>{JSON.stringify(ev.meta)}</Text>
                    )}
                  </View>
                </View>
              ))}
            </SectionCard>
          )}
        </View>

        {/* RIGHT: Sidebar — Benchmarking + PDF preview */}
        <View style={{ flex: 1, gap: 12 }}>
          {/* Benchmark */}
          <View style={{ backgroundColor: colors.card, borderRadius: 14, padding: 18, borderWidth: 1, borderColor: colors.border }} data-testid="benchmark-panel" testID="benchmark-panel">
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
              <Ionicons name="analytics" size={16} color={colors.primary} />
              <Text style={{ color: colors.text, fontSize: 15, fontWeight: '800' }}>{t("autofix.watchSweep1.benchmarking")}</Text>
            </View>
            <Text style={{ color: colors.textDim, fontSize: 11, marginTop: 2 }}>{t("autofix.watchSweep1.vs.your.historical")}{offer.role_title}{t("autofix.watchSweep1.offers")}</Text>
            {benchmark?.has_data ? (
              <View style={{ marginTop: 14, gap: 8 }}>
                <BenchmarkRow label="Median base" value={`$${benchmark.salary_median.toLocaleString()}`} colors={colors} />
                <BenchmarkRow label="25th — 75th %ile" value={`$${benchmark.salary_p25.toLocaleString()} – $${benchmark.salary_p75.toLocaleString()}`} colors={colors} />
                <BenchmarkRow label="Acceptance rate" value={`${benchmark.acceptance_rate}%`} colors={colors} emphasize />
                <BenchmarkRow label="Median start window" value={`${benchmark.median_start_days} days`} colors={colors} />
                <BenchmarkRow label="Sample size" value={`${benchmark.total} offer${benchmark.total !== 1 ? 's' : ''}`} colors={colors} />
                {offer.base_salary_usd && benchmark.salary_median > 0 && (
                  <Text style={{ color: colors.textSec, fontSize: 12, marginTop: 10, lineHeight: 17 }}>{t("autofix.watchSweep1.this.offer.is")}<Text style={{ fontWeight: '800', color: offer.base_salary_usd >= benchmark.salary_median ? colors.success : colors.warning }}>{offer.base_salary_usd >= benchmark.salary_p75 ? 'above p75' : offer.base_salary_usd >= benchmark.salary_median ? 'at/above median' : offer.base_salary_usd >= benchmark.salary_p25 ? 'between p25–median' : 'below p25'}</Text>{' '}{t("autofix.watchSweep1.of.past")}{offer.role_title}{t("autofix.watchSweep1.offers.2")}</Text>
                )}
              </View>
            ) : (
              <Text style={{ color: colors.textSec, fontSize: 12, marginTop: 12 }}>{t("autofix.watchSweep1.not.enough.historical.data.yet.after.you.send")}</Text>
            )}
          </View>

          {/* PDF preview */}
          <View style={{ backgroundColor: colors.card, borderRadius: 14, padding: 18, borderWidth: 1, borderColor: colors.border }} data-testid="pdf-preview-panel" testID="pdf-preview-panel">
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 12 }}>
              <Ionicons name="document-text" size={16} color={colors.primary} />
              <Text style={{ color: colors.text, fontSize: 15, fontWeight: '800' }}>{t("autofix.watchSweep1.live.pdf.preview")}</Text>
            </View>
            {pdfError ? (
              <View style={{ backgroundColor: PDF_ERROR_BG, borderWidth: 1, borderColor: PDF_ERROR_BORDER, borderRadius: 10, padding: 14, marginBottom: 12 }} data-testid="pdf-error-banner" testID="pdf-error-banner">
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 6 }}>
                  <Ionicons name="warning" size={16} color={PDF_ERROR_ACCENT} />
                  <Text style={{ color: PDF_ERROR_ACCENT, fontSize: 13, fontWeight: '800' }}>{t("autofix.watchSweep1.pdf.cannot.render")}</Text>
                </View>
                <Text style={{ color: colors.errorText, fontSize: 12, lineHeight: 17, marginBottom: 6 }}>{pdfError.message}</Text>
                <Text style={{ color: colors.errorText, fontSize: 11, fontWeight: '600', marginBottom: 10 }}>{t("autofix.watchSweep1.missing.fields")}{pdfError.missing.join(', ')}
                </Text>
                {pdfError.code === 'BRANDING_INCOMPLETE' && (
                  <TouchableOpacity onPress={openBranding}
                    style={{ alignSelf: 'flex-start', backgroundColor: PDF_ERROR_ACCENT, paddingHorizontal: 14, paddingVertical: 8, borderRadius: 8 }}
                    data-testid="pdf-error-fix-btn" testID="pdf-error-fix-btn">
                    <Text style={{ color: colors.primaryText, fontSize: 12, fontWeight: '800' }}>{t("autofix.watchSweep1.fix.branding")}</Text>
                  </TouchableOpacity>
                )}
              </View>
            ) : null}
            {Platform.OS === 'web' && !pdfError && (
              <iframe src={pdfUrl} title="Offer PDF" width="100%" height={480} style={{ border: `1px solid ${colors.border}`, borderRadius: 8, background: 'var(--app-primary-text)' }} data-testid="pdf-preview-iframe" />
            )}
          </View>
        </View>
      </View>

      {/* Branding modal */}
      {brandingModal && (
        <View style={{ position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, backgroundColor: 'rgba(0,0,0,0.75)', zIndex: 310, justifyContent: 'center', alignItems: 'center', padding: 20 }} data-testid="branding-modal" testID="branding-modal">
          <View style={{ backgroundColor: colors.card, borderRadius: 14, padding: 20, width: '100%', maxWidth: 560, borderWidth: 1, borderColor: colors.border }}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 6 }}>
              <Ionicons name="business" size={18} color={colors.primary} />
              <Text style={{ color: colors.text, fontSize: 18, fontWeight: '800' }}>{t("autofix.watchSweep1.offer.branding.signer")}</Text>
            </View>
            <Text style={{ color: colors.textSec, fontSize: 12, marginBottom: 14, lineHeight: 17 }}>{t("autofix.watchSweep1.required.by.the.strict.enterprise.pdf.generator.fields")}{' '}<Text style={{ fontWeight: '700', color: colors.text }}>{t("autofix.watchSweep1.settings.receipt.branding")}</Text>.
            </Text>
            <BrandingField label="Legal business name" value={brandingDoc.legal_name}
              onChange={(v) => setBrandingDoc((p: any) => ({ ...p, legal_name: v }))}
              placeholder="e.g. RealAICoach, Inc." colors={colors} testId="branding-legal-name" />
            <BrandingField label="Registered HQ address" value={brandingDoc.hq_address}
              onChange={(v) => setBrandingDoc((p: any) => ({ ...p, hq_address: v }))}
              placeholder="Street, City, State ZIP, Country" colors={colors} testId="branding-hq-address" />
            <BrandingField label="CEO full legal name" value={brandingDoc.signer_name}
              onChange={(v) => setBrandingDoc((p: any) => ({ ...p, signer_name: v }))}
              placeholder="First Middle Last" colors={colors} testId="branding-signer-name" />
            <BrandingField label="CEO signature image URL (optional)" value={brandingDoc.signer_signature_image}
              onChange={(v) => setBrandingDoc((p: any) => ({ ...p, signer_signature_image: v }))}
              placeholder="/api/static/signatures/ceo.png" colors={colors} testId="branding-signature-url" />
            {/* Read-only preview of inherited fields */}
            <View style={{ backgroundColor: colors.bgAlt, borderRadius: 8, padding: 12, marginTop: 4, marginBottom: 14, borderWidth: 1, borderColor: colors.border }}>
              <Text style={{ color: colors.textMuted, fontSize: 10, fontWeight: '700', letterSpacing: 0.5, marginBottom: 6 }}>INHERITED FROM RECEIPT BRANDING</Text>
              <Text style={{ color: colors.textSec, fontSize: 12, lineHeight: 18 }}>{t("autofix.watchSweep1.brand")}<Text style={{ color: colors.text, fontWeight: '700' }}>{brandingDoc.brand_name || '—'}</Text>{'\n'}{t("autofix.watchSweep1.logo")}<Text style={{ color: colors.text }}>{brandingDoc.custom_logo || '—'}</Text>{'\n'}{t("autofix.watchSweep1.contact.email")}<Text style={{ color: colors.text }}>{brandingDoc.company_info || '—'}</Text>
              </Text>
            </View>
            <View style={{ flexDirection: 'row', gap: 10 }}>
              <TouchableOpacity onPress={() => setBrandingModal(false)}
                style={{ flex: 1, paddingVertical: 12, borderRadius: 10, borderWidth: 1, borderColor: colors.border, alignItems: 'center' }}
                data-testid="branding-cancel-btn" testID="branding-cancel-btn">
                <Text style={{ color: colors.text, fontWeight: '700' }}>{t("admin.onboardingAB.actions.cancel")}</Text>
              </TouchableOpacity>
              <TouchableOpacity onPress={handleSaveBranding} disabled={brandingSaving}
                style={{ flex: 2, paddingVertical: 12, borderRadius: 10, backgroundColor: colors.primary, alignItems: 'center' }}
                data-testid="branding-save-btn" testID="branding-save-btn">
                <Text style={{ color: colors.primaryText, fontWeight: '800' }}>{brandingSaving ? 'Saving…' : 'Save & refresh PDF'}</Text>
              </TouchableOpacity>
            </View>
          </View>
        </View>
      )}

      {/* Rescind modal */}
      {rescindModal && (
        <View style={{ position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, backgroundColor: 'rgba(0,0,0,0.75)', zIndex: 300, justifyContent: 'center', alignItems: 'center', padding: 20 }} data-testid="rescind-modal" testID="rescind-modal">
          <View style={{ backgroundColor: colors.card, borderRadius: 14, padding: 20, width: '100%', maxWidth: 480, borderWidth: 1, borderColor: colors.error }}>
            <Text style={{ color: colors.text, fontSize: 18, fontWeight: '800', marginBottom: 6 }}>{t("autofix.watchSweep1.rescind.this.offer")}</Text>
            <Text style={{ color: colors.textSec, fontSize: 13, marginBottom: 14 }}>{t("autofix.watchSweep1.the.candidate.will.receive.a.rescission.email.pdf")}</Text>
            {Platform.OS === 'web' && (
              <textarea value={rescindReason} onChange={(e: any) => setRescindReason(e.target.value)} rows={4}
                placeholder="Reason for rescinding (included in the email and PDF)…"
                data-testid="rescind-reason-input"
                style={{ width: '100%', padding: 10, borderRadius: 8, border: `1px solid ${colors.border}`, backgroundColor: colors.bgAlt, color: colors.text, fontSize: 13, fontFamily: 'inherit', resize: 'vertical' as any, outline: 'none', marginBottom: 14, boxSizing: 'border-box' as any }}
              />
            )}
            <View style={{ flexDirection: 'row', gap: 10 }}>
              <TouchableOpacity onPress={() => { setRescindModal(false); setRescindReason(''); }}
                style={{ flex: 1, paddingVertical: 12, borderRadius: 10, borderWidth: 1, borderColor: colors.border, alignItems: 'center' }}
                data-testid="rescind-cancel-btn" testID="rescind-cancel-btn">
                <Text style={{ color: colors.text, fontWeight: '700' }}>{t("admin.onboardingAB.actions.cancel")}</Text>
              </TouchableOpacity>
              <TouchableOpacity onPress={handleRescind} disabled={saving}
                style={{ flex: 2, paddingVertical: 12, borderRadius: 10, backgroundColor: colors.error, alignItems: 'center' }}
                data-testid="rescind-confirm-btn" testID="rescind-confirm-btn">
                <Text style={{ color: colors.primaryText, fontWeight: '800' }}>{saving ? 'Rescinding…' : 'Yes, rescind'}</Text>
              </TouchableOpacity>
            </View>
          </View>
        </View>
      )}
    </ScrollView>
  );
}

export default function OfferStudio() {
  return <OfferStudioScreen />;
}

function SectionCard({ title, children, colors, headerRight }: { title: string; children: React.ReactNode; colors: any; headerRight?: React.ReactNode }) {
  return (
    <View style={{ backgroundColor: colors.card, borderRadius: 14, padding: 18, borderWidth: 1, borderColor: colors.border }}>
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
        <Text style={{ color: colors.text, fontSize: 15, fontWeight: '800' }}>{title}</Text>
        {headerRight}
      </View>
      {children}
    </View>
  );
}

function Field({ label, value, onChange, editable, colors, testId, hint }: any) {
  return (
    <View style={{ marginBottom: 12 }}>
      <Text style={{ color: colors.textMuted, fontSize: 10, fontWeight: '700', letterSpacing: 0.5, marginBottom: 4 }}>{label.toUpperCase()}</Text>
      <TextInput
        value={value === null || value === undefined ? '' : String(value)}
        onChangeText={onChange}
        editable={editable}
        placeholder={hint || ''}
        placeholderTextColor={colors.textMuted as any}
        data-testid={testId} testID={testId}
        style={{ backgroundColor: editable ? colors.bgAlt : colors.border, color: colors.text, borderWidth: 1, borderColor: colors.border, borderRadius: 8, padding: 10, fontSize: 13 }}
      />
      {hint && !value && <Text style={{ color: colors.textDim, fontSize: 10, marginTop: 4 }}>{hint}</Text>}
    </View>
  );
}

function BenchmarkRow({ label, value, colors, emphasize }: any) {
  return (
    <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
      <Text style={{ color: colors.textSec, fontSize: 12 }}>{label}</Text>
      <Text style={{ color: emphasize ? colors.primary : colors.text, fontSize: emphasize ? 14 : 13, fontWeight: emphasize ? '800' : '600' }}>{value}</Text>
    </View>
  );
}

function BrandingField({ label, value, onChange, placeholder, colors, testId }: any) {
  return (
    <View style={{ marginBottom: 12 }}>
      <Text style={{ color: colors.textMuted, fontSize: 10, fontWeight: '700', letterSpacing: 0.5, marginBottom: 4 }}>{label.toUpperCase()}</Text>
      <TextInput
        value={value || ''}
        onChangeText={onChange}
        placeholder={placeholder}
        placeholderTextColor={colors.textMuted as any}
        data-testid={testId} testID={testId}
        style={{ backgroundColor: colors.bgAlt, color: colors.text, borderWidth: 1, borderColor: colors.border, borderRadius: 8, padding: 10, fontSize: 13 }}
      />
    </View>
  );
}
