/**
 * /careers/offer/confirm?token=<candidate_token>
 * Public candidate landing page — accept/decline with typed e-signature.
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { ActivityIndicator, Platform, ScrollView, Text, TouchableOpacity, View, useWindowDimensions } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useLocalSearchParams } from 'expo-router';
import { useTheme } from '../../../src/context/ThemeContext';
import { useTranslation } from '../../../src/hooks/useTranslation';
import { resolveRuntimeBaseUrl } from '../../../src/utils/runtimeBaseUrl';
import { handleAppRecoverableError } from '../../../src/utils/appRecoverableError';

const API = resolveRuntimeBaseUrl();

export default function OfferConfirmPublic() {
  const { t } = useTranslation();
  t('i18n.route.careers.offer.confirm.probe');
  const { token: tokenParam } = useLocalSearchParams<{ token?: string }>();
  const token = (typeof tokenParam === 'string' ? tokenParam : '') as string;
  const { colors } = useTheme();
  const tx = useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);
  const { width } = useWindowDimensions();
  const isMobile = width < 768;

  const [loading, setLoading] = useState(true);
  const [offer, setOffer] = useState<any | null>(null);
  const [err, setErr] = useState('');

  const [mode, setMode] = useState<'idle' | 'accepting' | 'declining'>('idle');
  const [signedName, setSignedName] = useState('');
  const [ack, setAck] = useState(false);
  const [declineReason, setDeclineReason] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const fetchOffer = useCallback(async () => {
    if (!token) { setErr(tx('careers.offerConfirm.errors.missingToken', 'Missing token. Please use the full link from your offer email.')); setLoading(false); return; }
    try {
      const res = await fetch(`${API}/api/careers/offers/public/${encodeURIComponent(token)}`, {
        headers: { 'X-Requested-With': 'XMLHttpRequest', Accept: 'application/json' },
      });
      const body = await res.json();
      if (!res.ok || !body.success) setErr(body.detail || tx('careers.offerConfirm.errors.invalidLink', 'This link is invalid or has expired.'));
      else setOffer(body);
    } catch (error) {
      const message = tx('careers.offerConfirm.errors.loadFailed', 'Unable to load your offer. Please try again later.');
      handleAppRecoverableError({
        scope: 'careers.offer.confirm.load',
        error,
        message,
        setError: setErr,
        onRetry: () => { void fetchOffer(); },
      
        notifyMode: 'dialog',
        userInitiated: true,
      });
      setErr(message);
    }
    setLoading(false);
  }, [token, tx]);

  useEffect(() => { fetchOffer(); }, [fetchOffer]);

  const handleAccept = async () => {
    if (!signedName.trim() || signedName.trim().length < 3) { setErr(tx('careers.offerConfirm.errors.signatureRequired', 'Please type your full legal name to sign.')); return; }
    if (!ack) { setErr(tx('careers.offerConfirm.errors.ackRequired', 'Please acknowledge the terms to accept.')); return; }
    setSubmitting(true); setErr('');
    try {
      const res = await fetch(`${API}/api/careers/offers/public/${encodeURIComponent(token)}/accept`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
        body: JSON.stringify({ signed_name: signedName.trim(), acknowledge_terms: ack }),
      });
      const body = await res.json();
      if (res.ok && body.success) { setOffer(body); setMode('idle'); }
      else setErr(body.detail || tx('careers.offerConfirm.errors.submitFailed', 'Unable to submit. Please try again.'));
    } catch (error) {
      const message = tx('careers.offerConfirm.errors.network', 'Network error. Please try again.');
      handleAppRecoverableError({
        scope: 'careers.offer.confirm.accept',
        error,
        message,
        setError: setErr,
        onRetry: () => { void handleAccept(); },
      
        notifyMode: 'dialog',
        userInitiated: true,
      });
      setErr(message);
    }
    setSubmitting(false);
  };

  const handleDecline = async () => {
    setSubmitting(true); setErr('');
    try {
      const res = await fetch(`${API}/api/careers/offers/public/${encodeURIComponent(token)}/decline`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
        body: JSON.stringify({ reason: declineReason || null }),
      });
      const body = await res.json();
      if (res.ok && body.success) { setOffer(body); setMode('idle'); }
      else setErr(body.detail || tx('careers.offerConfirm.errors.submitFailed', 'Unable to submit. Please try again.'));
    } catch (error) {
      const message = tx('careers.offerConfirm.errors.network', 'Network error. Please try again.');
      handleAppRecoverableError({
        scope: 'careers.offer.confirm.decline',
        error,
        message,
        setError: setErr,
        onRetry: () => { void handleDecline(); },
      
        notifyMode: 'dialog',
        userInitiated: true,
      });
      setErr(message);
    }
    setSubmitting(false);
  };

  const pdfUrl = useMemo(() => `${API}/api/careers/offers/public/${encodeURIComponent(token)}/pdf`, [token]);

  if (loading) {
    return <View style={{ flex: 1, backgroundColor: colors.bg, justifyContent: 'center', alignItems: 'center' }} data-testid="offer-public-loading" testID="offer-public-loading"><ActivityIndicator color={colors.primary} size="large" /></View>;
  }
  if (err && !offer) {
    return (
      <View style={{ flex: 1, backgroundColor: colors.bg, justifyContent: 'center', alignItems: 'center', padding: 24 }} data-testid="offer-public-error" testID="offer-public-error">
        <Ionicons name="alert-circle" size={48} color={colors.error} />
        <Text style={{ color: colors.text, fontSize: 20, fontWeight: '700', marginTop: 16, textAlign: 'center' }}>{tx('careers.offerConfirm.states.linkUnavailable', 'Link unavailable')}</Text>
        <Text style={{ color: colors.textSec, fontSize: 14, marginTop: 8, textAlign: 'center', maxWidth: 440 }}>{err}</Text>
        <TouchableOpacity
          onPress={() => { void fetchOffer(); }}
          style={{ marginTop: 14, backgroundColor: colors.error, paddingHorizontal: 14, paddingVertical: 10, borderRadius: 8 }}
          data-testid="offer-public-error-retry-button"
          testID="offer-public-error-retry-button"
        >
          <Text style={{ color: colors.primaryText, fontSize: 12, fontWeight: '800' }}>{tx('common.retry', 'Retry')}</Text>
        </TouchableOpacity>
      </View>
    );
  }
  if (!offer) return null;

  const state = offer.state;
  return (
    <ScrollView style={{ flex: 1, backgroundColor: colors.bg }} contentContainerStyle={{ padding: isMobile ? 16 : 32, alignItems: 'center' }}>
      <View style={{ width: '100%', maxWidth: 960 }} data-testid="offer-public-page" testID="offer-public-page">
        {/* Hero */}
        <View style={{ alignItems: 'center', marginBottom: 20, marginTop: isMobile ? 8 : 24 }}>
          <View style={{ width: 64, height: 64, borderRadius: 32, backgroundColor: colors.primarySoft, justifyContent: 'center', alignItems: 'center', marginBottom: 16 }}>
            <Ionicons name="briefcase" size={30} color={colors.primary} />
          </View>
          <Text style={{ color: colors.text, fontSize: isMobile ? 24 : 32, fontWeight: '800', textAlign: 'center', letterSpacing: -0.5 }}>
            {tx('careers.offerConfirm.hero.titleWithName', 'Hi {name}, you have an offer! 🎉').replace('{name}', (offer.candidate_name || '').split(' ')[0])}
          </Text>
          <Text style={{ color: colors.textSec, fontSize: 15, marginTop: 8, textAlign: 'center' }}>
            {tx('careers.offerConfirm.hero.subtitlePrefix', 'for the')} <Text style={{ fontWeight: '700', color: colors.text }}>{offer.role_title}</Text> {tx('careers.offerConfirm.hero.subtitleSuffix', 'role at RealAICoach')}
          </Text>
        </View>

        {/* Offer Summary Card */}
        <View style={{ backgroundColor: colors.card, borderRadius: 18, padding: 20, borderWidth: 1, borderColor: colors.border, marginBottom: 16 }} data-testid="offer-summary-card" testID="offer-summary-card">
          <Text style={{ color: colors.textMuted, fontSize: 11, fontWeight: '700', letterSpacing: 1 }}>{tx('careers.offerConfirm.summary.title', 'OFFER SUMMARY')}</Text>
          <Text style={{ color: colors.primary, fontSize: 28, fontWeight: '800', marginTop: 8 }}>
            ${(offer.base_salary_usd || 0).toLocaleString()} <Text style={{ fontSize: 14, color: colors.textSec, fontWeight: '600' }}>{tx('careers.offerConfirm.summary.baseUsd', 'base · USD')}</Text>
          </Text>
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 12 }}>
            {offer.bonus_target_pct > 0 && <Chip text={tx('careers.offerConfirm.summary.bonusTarget', '+{pct}% target bonus').replace('{pct}', String(offer.bonus_target_pct))} colors={colors} />}
            {offer.equity_shares && <Chip text={tx('careers.offerConfirm.summary.shares', '{count} shares').replace('{count}', offer.equity_shares.toLocaleString())} colors={colors} />}
            {offer.signing_bonus_usd > 0 && <Chip text={tx('careers.offerConfirm.summary.signingBonus', '${amount} signing').replace('{amount}', offer.signing_bonus_usd.toLocaleString())} colors={colors} />}
            {offer.pto_days && <Chip text={tx('careers.offerConfirm.summary.ptoDays', '{days} PTO days').replace('{days}', String(offer.pto_days))} colors={colors} />}
            <Chip text={(offer.work_location || 'remote').toUpperCase()} colors={colors} accent />
          </View>
          <View style={{ marginTop: 16, gap: 4 }}>
            <Text style={{ color: colors.textSec, fontSize: 13 }}><Text style={{ fontWeight: '700' }}>{tx('careers.offerConfirm.summary.start', 'Start:')}</Text> {offer.start_date || tx('careers.offerConfirm.common.tbd', 'TBD')}</Text>
            {offer.reporting_manager && <Text style={{ color: colors.textSec, fontSize: 13 }}><Text style={{ fontWeight: '700' }}>{tx('careers.offerConfirm.summary.manager', 'Manager:')}</Text> {offer.reporting_manager}</Text>}
            <Text style={{ color: colors.textSec, fontSize: 13 }}><Text style={{ fontWeight: '700' }}>{tx('careers.offerConfirm.summary.expires', 'Expires:')}</Text> {(offer.expires_at || '').slice(0, 10) || tx('careers.offerConfirm.common.tbd', 'TBD')}</Text>
          </View>
          {offer.personal_message && (
            <View style={{ marginTop: 14, padding: 12, backgroundColor: colors.bgAlt, borderRadius: 10, borderLeftWidth: 3, borderLeftColor: colors.primary }}>
              <Text style={{ color: colors.text, fontSize: 13, lineHeight: 18, fontStyle: 'italic' as any }}>“{offer.personal_message}”</Text>
            </View>
          )}
          {Platform.OS === 'web' && (
            <TouchableOpacity onPress={() => (window as any).open(pdfUrl, '_blank')} style={{ marginTop: 16, flexDirection: 'row', alignItems: 'center', gap: 6, alignSelf: 'flex-start' }} data-testid="offer-download-pdf-btn" testID="offer-download-pdf-btn">
              <Ionicons name="document" size={14} color={colors.primary} />
              <Text style={{ color: colors.primary, fontSize: 13, fontWeight: '700' }}>{tx('careers.offerConfirm.summary.viewPdf', 'View full PDF offer letter')}</Text>
            </TouchableOpacity>
          )}
        </View>

        {/* Actions — state-dependent */}
        {state === 'sent' && mode === 'idle' && (
          <View style={{ flexDirection: isMobile ? 'column' : 'row', gap: 12 }}>
            <TouchableOpacity onPress={() => setMode('accepting')}
              style={{ flex: 2, backgroundColor: colors.primary, paddingVertical: 16, borderRadius: 14, flexDirection: 'row', justifyContent: 'center', alignItems: 'center', gap: 8 }}
              data-testid="public-accept-btn" testID="public-accept-btn">
              <Ionicons name="checkmark-circle" size={20} color={colors.primaryText} />
              <Text style={{ color: colors.primaryText, fontSize: 16, fontWeight: '800' }}>{tx('careers.offerConfirm.actions.acceptOffer', 'Accept this offer')}</Text>
            </TouchableOpacity>
            <TouchableOpacity onPress={() => setMode('declining')}
              style={{ flex: 1, backgroundColor: 'transparent', paddingVertical: 16, borderRadius: 14, borderWidth: 1, borderColor: colors.border, flexDirection: 'row', justifyContent: 'center', alignItems: 'center', gap: 8 }}
              data-testid="public-decline-btn" testID="public-decline-btn">
              <Ionicons name="close-circle" size={18} color={colors.text} />
              <Text style={{ color: colors.text, fontSize: 15, fontWeight: '700' }}>{tx('careers.offerConfirm.actions.declinePolitely', 'Politely decline')}</Text>
            </TouchableOpacity>
          </View>
        )}

        {/* Accept form */}
        {mode === 'accepting' && state === 'sent' && (
          <View style={{ backgroundColor: colors.card, borderRadius: 14, padding: 20, borderWidth: 1, borderColor: colors.primary }} data-testid="accept-form" testID="accept-form">
            <Text style={{ color: colors.text, fontSize: 18, fontWeight: '800', marginBottom: 6 }}>{tx('careers.offerConfirm.accept.title', 'Confirm your acceptance')}</Text>
            <Text style={{ color: colors.textSec, fontSize: 13, marginBottom: 14 }}>{tx('careers.offerConfirm.accept.subtitle', 'Type your full legal name as your e-signature. We record name + timestamp + IP + device fingerprint into a SHA-256 signed PDF, which will be emailed to you immediately.')}</Text>
            {Platform.OS === 'web' && (
              <input type="text" value={signedName} onChange={(e: any) => setSignedName(e.target.value)}
                placeholder={tx('careers.offerConfirm.accept.signaturePlaceholder', 'Your full legal name (required)')}
                data-testid="accept-signed-name"
                style={{ width: '100%', padding: '12px 14px', borderRadius: 10, border: `1px solid ${colors.border}`, backgroundColor: colors.bgAlt, color: colors.text, fontSize: 16, fontFamily: 'Georgia, serif', fontStyle: 'italic', outline: 'none', marginBottom: 14, boxSizing: 'border-box' as any }}
              />
            )}
            <TouchableOpacity onPress={() => setAck(!ack)} style={{ flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 16 }} data-testid="accept-ack-toggle" testID="accept-ack-toggle">
              <View style={{ width: 22, height: 22, borderRadius: 5, borderWidth: 2, borderColor: ack ? colors.primary : colors.border, backgroundColor: ack ? colors.primary : 'transparent', justifyContent: 'center', alignItems: 'center' }}>
                {ack && <Ionicons name="checkmark" size={14} color={colors.primaryText} />}
              </View>
              <Text style={{ color: colors.textSec, fontSize: 13, flex: 1 }}>{tx('careers.offerConfirm.accept.acknowledgement', 'I have read the attached offer letter and I agree to its terms. My typed name above serves as my legally-binding electronic signature.')}</Text>
            </TouchableOpacity>
            {err ? <Text style={{ color: colors.error, fontSize: 12, marginBottom: 12 }} data-testid="accept-err">{err}</Text> : null}
            <View style={{ flexDirection: 'row', gap: 10 }}>
              <TouchableOpacity onPress={() => { setMode('idle'); setErr(''); }} disabled={submitting}
                style={{ flex: 1, paddingVertical: 13, borderRadius: 10, borderWidth: 1, borderColor: colors.border, alignItems: 'center' }}
                data-testid="accept-cancel-btn" testID="accept-cancel-btn">
                <Text style={{ color: colors.text, fontWeight: '700' }}>{tx('careers.offerConfirm.actions.back', 'Back')}</Text>
              </TouchableOpacity>
              <TouchableOpacity onPress={handleAccept} disabled={submitting || !signedName || !ack}
                style={{ flex: 2, paddingVertical: 13, borderRadius: 10, backgroundColor: (submitting || !signedName || !ack) ? colors.textMuted : colors.primary, alignItems: 'center', flexDirection: 'row', justifyContent: 'center', gap: 6 }}
                data-testid="accept-submit-btn" testID="accept-submit-btn">
                {submitting ? <ActivityIndicator color={colors.primaryText} /> : <Ionicons name="create" size={14} color={colors.primaryText} />}
                <Text style={{ color: colors.primaryText, fontWeight: '800' }}>{submitting ? tx('careers.offerConfirm.accept.signing', 'Signing…') : tx('careers.offerConfirm.accept.signAndAccept', 'Sign & Accept')}</Text>
              </TouchableOpacity>
            </View>
          </View>
        )}

        {/* Decline form */}
        {mode === 'declining' && state === 'sent' && (
          <View style={{ backgroundColor: colors.card, borderRadius: 14, padding: 20, borderWidth: 1, borderColor: colors.border }} data-testid="decline-form" testID="decline-form">
            <Text style={{ color: colors.text, fontSize: 18, fontWeight: '800', marginBottom: 6 }}>{tx('careers.offerConfirm.decline.title', 'Decline this offer')}</Text>
            <Text style={{ color: colors.textSec, fontSize: 13, marginBottom: 14 }}>{tx('careers.offerConfirm.decline.subtitle', "We're sorry it didn't work out. A short reason is optional — it helps us improve.")}</Text>
            {Platform.OS === 'web' && (
              <textarea value={declineReason} onChange={(e: any) => setDeclineReason(e.target.value)} rows={4}
                placeholder={tx('careers.offerConfirm.decline.reasonPlaceholder', 'Optional — e.g. accepted another offer, compensation, location…')}
                data-testid="decline-reason-input"
                style={{ width: '100%', padding: 12, borderRadius: 10, border: `1px solid ${colors.border}`, backgroundColor: colors.bgAlt, color: colors.text, fontSize: 14, fontFamily: 'inherit', resize: 'vertical' as any, outline: 'none', marginBottom: 14, boxSizing: 'border-box' as any }}
              />
            )}
            {err ? <Text style={{ color: colors.error, fontSize: 12, marginBottom: 12 }} data-testid="decline-err">{err}</Text> : null}
            <View style={{ flexDirection: 'row', gap: 10 }}>
              <TouchableOpacity onPress={() => { setMode('idle'); setErr(''); }} disabled={submitting}
                style={{ flex: 1, paddingVertical: 13, borderRadius: 10, borderWidth: 1, borderColor: colors.border, alignItems: 'center' }}
                data-testid="decline-cancel-btn" testID="decline-cancel-btn">
                <Text style={{ color: colors.text, fontWeight: '700' }}>{tx('careers.offerConfirm.actions.back', 'Back')}</Text>
              </TouchableOpacity>
              <TouchableOpacity onPress={handleDecline} disabled={submitting}
                style={{ flex: 2, paddingVertical: 13, borderRadius: 10, backgroundColor: colors.textSec, alignItems: 'center' }}
                data-testid="decline-submit-btn" testID="decline-submit-btn">
                <Text style={{ color: colors.primaryText, fontWeight: '800' }}>{submitting ? tx('careers.offerConfirm.decline.sending', 'Sending…') : tx('careers.offerConfirm.decline.sendDecline', 'Send decline')}</Text>
              </TouchableOpacity>
            </View>
          </View>
        )}

        {/* Post-action states */}
        {state === 'accepted' && (
          <View style={{ backgroundColor: colors.successSoft, borderRadius: 16, padding: 24, borderWidth: 1, borderColor: colors.success, alignItems: 'center' }} data-testid="accepted-state" testID="accepted-state">
            <Ionicons name="checkmark-circle" size={48} color={colors.success} />
            <Text style={{ color: colors.successText, fontSize: 22, fontWeight: '800', marginTop: 12, textAlign: 'center' }}>{tx('careers.offerConfirm.accepted.title', 'Welcome to RealAICoach! 🎉')}</Text>
            <Text style={{ color: colors.textSec, fontSize: 14, marginTop: 8, textAlign: 'center', maxWidth: 440 }}>{tx('careers.offerConfirm.accepted.subtitleWithDate', "Your signed offer has been recorded on {date}. A countersigned PDF copy is in your email — check spam if you don't see it.").replace('{date}', (offer.responded_at || '').slice(0,10))}</Text>
            {Platform.OS === 'web' && (
              <TouchableOpacity onPress={() => (window as any).open(pdfUrl, '_blank')} style={{ marginTop: 18, backgroundColor: colors.primary, paddingHorizontal: 22, paddingVertical: 12, borderRadius: 10 }} data-testid="accepted-download-btn">
                <Text style={{ color: colors.primaryText, fontSize: 13, fontWeight: '800' }}>{tx('careers.offerConfirm.accepted.downloadSignedPdf', 'Download signed PDF')}</Text>
              </TouchableOpacity>
            )}
          </View>
        )}
        {state === 'declined' && (
          <View style={{ backgroundColor: colors.bgAlt, borderRadius: 16, padding: 24, borderWidth: 1, borderColor: colors.border, alignItems: 'center' }} data-testid="declined-state" testID="declined-state">
            <Ionicons name="close-circle" size={44} color={colors.textSec} />
            <Text style={{ color: colors.text, fontSize: 20, fontWeight: '700', marginTop: 10, textAlign: 'center' }}>{tx('careers.offerConfirm.declined.title', 'Decision recorded')}</Text>
            <Text style={{ color: colors.textSec, fontSize: 13, marginTop: 6, textAlign: 'center', maxWidth: 440 }}>{tx('careers.offerConfirm.declined.subtitle', "Thank you for the time you invested. We've emailed you a copy for your records. We'd love to stay in touch for the future.")}</Text>
          </View>
        )}
        {state === 'expired' && (
          <View style={{ backgroundColor: colors.warningSoft, borderRadius: 16, padding: 24, borderWidth: 1, borderColor: colors.warning, alignItems: 'center' }} data-testid="expired-state" testID="expired-state">
            <Ionicons name="time" size={44} color={colors.warning} />
            <Text style={{ color: colors.warningText, fontSize: 20, fontWeight: '700', marginTop: 10, textAlign: 'center' }}>{tx('careers.offerConfirm.expired.title', 'This offer has expired')}</Text>
            <Text style={{ color: colors.textSec, fontSize: 13, marginTop: 6, textAlign: 'center', maxWidth: 440 }}>{tx('careers.offerConfirm.expired.subtitleWithDate', "The response window closed on {date}. If you're still interested, please reply to the offer email and we'll re-engage.").replace('{date}', (offer.expires_at || '').slice(0, 10))}</Text>
          </View>
        )}
        {state === 'rescinded' && (
          <View style={{ backgroundColor: colors.errorSoft, borderRadius: 16, padding: 24, borderWidth: 1, borderColor: colors.error, alignItems: 'center' }} data-testid="rescinded-state" testID="rescinded-state">
            <Ionicons name="ban" size={44} color={colors.error} />
            <Text style={{ color: colors.error, fontSize: 20, fontWeight: '700', marginTop: 10, textAlign: 'center' }}>{tx('careers.offerConfirm.rescinded.title', 'This offer has been rescinded')}</Text>
            <Text style={{ color: colors.textSec, fontSize: 13, marginTop: 6, textAlign: 'center', maxWidth: 440 }}>{tx('careers.offerConfirm.rescinded.subtitle', 'This offer is no longer in effect. A rescission letter has been emailed to you for your records.')}</Text>
          </View>
        )}

        <Text style={{ color: colors.textMuted, fontSize: 11, marginTop: 28, textAlign: 'center' }}>{tx('careers.offerConfirm.footer.note', 'RealAICoach Talent · offers secured by typed e-signature + SHA-256 hash')}</Text>
      </View>
    </ScrollView>
  );
}

function Chip({ text, colors, accent }: any) {
  return (
    <View style={{ backgroundColor: accent ? colors.accentSoft : colors.bgAlt, paddingHorizontal: 10, paddingVertical: 5, borderRadius: 10 }}>
      <Text style={{ color: accent ? colors.accent : colors.textSec, fontSize: 11, fontWeight: '700' }}>{text}</Text>
    </View>
  );
}
