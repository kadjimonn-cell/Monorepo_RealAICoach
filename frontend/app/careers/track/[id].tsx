// Public applicant-facing Application Tracker.
// Route: /careers/track/[id]
// No auth required — the `application_id` itself is the capability.
// Backend: GET /api/careers/applications/track/{application_id}
//
// Design goals:
//   • Zero-friction — arriving from the confirmation email takes them
//     straight to their status without account creation.
//   • PII-safe — the endpoint only returns first name, never email/phone.
//   • Trust-building — a clear 5-step timeline, friendly copy, visible
//     hiring-contact email for questions / withdrawals.
import React, { useCallback, useEffect, useState } from 'react';
import { View, Text, TouchableOpacity, ActivityIndicator, ScrollView, Linking, TextInput, Modal } from 'react-native';
import { useLocalSearchParams, Stack } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { useTheme } from '../../../src/context/ThemeContext';
import { useTranslation } from '../../../src/hooks/useTranslation';
import { resolveRuntimeBaseUrl } from '../../../src/utils/runtimeBaseUrl';
import { handleAppRecoverableError } from '../../../src/utils/appRecoverableError';

const API = resolveRuntimeBaseUrl();

type TimelineStep = {
  key: string;
  title: string;
  subtitle: string;
  state: 'done' | 'active' | 'pending';
};

type TrackerData = {
  application_id: string;
  role_title: string;
  role_slug?: string | null;
  status: string;
  status_updated_at?: string | null;
  submitted_at?: string | null;
  applicant_first_name: string;
  attachment_count: number;
  timeline: TimelineStep[];
  interview: { start_utc: string; interview_type: string } | null;
  role_queue: { total_in_role: number; review_sla_hours: number } | null;
  hiring_contact_email: string;
};

const STATUS_TINT: Record<string, { tone: string; labelKey: string; fallback: string }> = {
  received: { tone: 'info', labelKey: 'careerTracker.statusLabels.underReview', fallback: 'Under Review' },
  screening: { tone: 'purple', labelKey: 'careerTracker.statusLabels.screening', fallback: 'Screening' },
  interview: { tone: 'primary', labelKey: 'careerTracker.statusLabels.interview', fallback: 'Interview' },
  offer: { tone: 'warning', labelKey: 'careerTracker.statusLabels.offerExtended', fallback: 'Offer Extended' },
  hired: { tone: 'success', labelKey: 'careerTracker.statusLabels.hired', fallback: 'Hired' },
  rejected: { tone: 'textMuted', labelKey: 'careerTracker.statusLabels.notMovingForward', fallback: 'Not Moving Forward' },
};

function fmtDate(iso?: string | null): string {
  if (!iso) return '';
  try {
    const d = new Date(iso);
    return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
  } catch {
    return '';
  }
}

function fmtDateTime(iso?: string | null): string {
  if (!iso) return '';
  try {
    const d = new Date(iso);
    return d.toLocaleString(undefined, {
      month: 'short', day: 'numeric', year: 'numeric',
      hour: 'numeric', minute: '2-digit',
    });
  } catch {
    return '';
  }
}

export default function ApplicationTrackerPage() {
  const { t } = useTranslation();
  const tx = useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);
  t('i18n.route.careers.track.[id].probe');
  const params = useLocalSearchParams<{ id: string }>();
  const applicationId = String(params?.id || '').trim();
  const { colors } = useTheme();

  const [loading, setLoading] = useState(true);
  const [data, setData] = useState<TrackerData | null>(null);
  const [err, setErr] = useState<string>('');
  const [withdrawOpen, setWithdrawOpen] = useState(false);
  const [withdrawReason, setWithdrawReason] = useState('');
  const [withdrawing, setWithdrawing] = useState(false);
  const [withdrawErr, setWithdrawErr] = useState('');

  const load = useCallback(async () => {
    if (!applicationId) return;
    setLoading(true);
    setErr('');
    try {
      const r = await fetch(
        `${API}/api/careers/applications/track/${encodeURIComponent(applicationId)}`,
        { credentials: 'omit' },
      );
      if (r.status === 404) {
        setErr(tx('careerTracker.errors.notFoundById', "We couldn't find an application with that ID."));
      } else if (r.status === 429) {
        setErr(tx('careerTracker.errors.tooManyLookups', 'Too many lookups — please wait a minute and try again.'));
      } else if (!r.ok) {
        setErr(tx('careerTracker.errors.unableToLoadHttp', 'Unable to load (HTTP {status}).').replace('{status}', String(r.status)));
      } else {
        setData((await r.json()) as TrackerData);
      }
    } catch (e: any) {
      const message = e?.message || tx('careerTracker.errors.network', 'Network error — please try again.');
      handleAppRecoverableError({
        scope: 'careers.track.load',
        error: e,
        message,
        setError: setErr,
        onRetry: () => { void load(); },
      
        notifyMode: 'dialog',
        userInitiated: true,
      });
      setErr(message);
    }
    setLoading(false);
  }, [applicationId, tx]);

  useEffect(() => { load(); }, [load]);

  const doWithdraw = useCallback(async () => {
    setWithdrawing(true);
    setWithdrawErr('');
    try {
      const r = await fetch(
        `${API}/api/careers/applications/track/${encodeURIComponent(applicationId)}/withdraw`,
        {
          method: 'POST',
          credentials: 'omit',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ reason: withdrawReason.slice(0, 500) }),
        },
      );
      if (!r.ok) {
        setWithdrawErr(tx('careerTracker.withdraw.errors.httpStatus', 'HTTP {status} — try again in a moment.').replace('{status}', String(r.status)));
      } else {
        setWithdrawOpen(false);
        setWithdrawReason('');
        await load();
      }
    } catch (e: any) {
      const message = e?.message || tx('careerTracker.withdraw.errors.network', 'Network error.');
      handleAppRecoverableError({
        scope: 'careers.track.withdraw',
        error: e,
        message,
        setError: setWithdrawErr,
        onRetry: () => { void doWithdraw(); },
      
        notifyMode: 'dialog',
        userInitiated: true,
      });
      setWithdrawErr(message);
    }
    setWithdrawing(false);
  }, [applicationId, withdrawReason, load, tx]);

  const pageTitle = tx('careerTracker.page.title', 'Application Status');

  if (loading) {
    return (
      <View
        style={{ flex: 1, backgroundColor: colors.bg, alignItems: 'center', justifyContent: 'center' }}
        data-testid="tracker-loading"
        testID="tracker-loading"
      >
        <Stack.Screen options={{ title: pageTitle, headerShown: false }} />
        <ActivityIndicator size="large" color={colors.primary} />
      </View>
    );
  }

  if (err || !data) {
    return (
      <View
        style={{ flex: 1, backgroundColor: colors.bg, alignItems: 'center', justifyContent: 'center', padding: 30 }}
        data-testid="tracker-error"
        testID="tracker-error"
      >
        <Stack.Screen options={{ title: pageTitle, headerShown: false }} />
        <Ionicons name="search-outline" size={48} color={colors.textMuted} />
        <Text style={{ color: colors.text, fontSize: 20, fontWeight: '800', marginTop: 18, textAlign: 'center' }}>
          {tx('careerTracker.errors.applicationNotFoundTitle', 'Application not found')}
        </Text>
        <Text style={{ color: colors.textSec, fontSize: 14, marginTop: 8, textAlign: 'center', maxWidth: 480, lineHeight: 22 }}>
          {err || tx('careerTracker.errors.doubleCheckLink', 'Please double-check the link from your confirmation email.')}
        </Text>
        <TouchableOpacity
          onPress={() => { void load(); }}
          style={{
            marginTop: 12,
            paddingHorizontal: 18,
            paddingVertical: 10,
            borderRadius: 999,
            backgroundColor: colors.error,
          }}
          data-testid="tracker-error-retry"
          testID="tracker-error-retry"
        >
          <Text style={{ color: colors.primaryText, fontWeight: '800', fontSize: 13 }}>
            {tx('common.retry', 'Retry')}
          </Text>
        </TouchableOpacity>
        <TouchableOpacity
          onPress={() => Linking.openURL('mailto:hiring@realaicoach.app')}
          style={{
            marginTop: 20, paddingHorizontal: 18, paddingVertical: 10, borderRadius: 999,
            backgroundColor: colors.primary,
          }}
          data-testid="tracker-error-contact"
          testID="tracker-error-contact"
        >
          <Text style={{ color: colors.primaryText, fontWeight: '800', fontSize: 13 }}>
            {tx('careerTracker.actions.emailHiring', 'Email hiring@realaicoach.app')}
          </Text>
        </TouchableOpacity>
      </View>
    );
  }

  const tint = STATUS_TINT[data.status] || STATUS_TINT.received;
  const tintColor = (colors as any)[tint.tone] || colors.primary;
  const tintLabel = tx(tint.labelKey, tint.fallback);

  return (
    <ScrollView
      style={{ flex: 1, backgroundColor: colors.bg }}
      contentContainerStyle={{ alignItems: 'center', paddingVertical: 40, paddingHorizontal: 20 }}
      data-testid="tracker-page"
      testID="tracker-page"
    >
      <Stack.Screen options={{ title: pageTitle, headerShown: false }} />
      <View style={{ width: '100%', maxWidth: 960 }}>
        {/* Hero */}
        <View
          style={{
            backgroundColor: colors.card,
            borderRadius: 20,
            padding: 28,
            borderWidth: 1,
            borderColor: colors.border,
            marginBottom: 18,
          }}
        >
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 12, marginBottom: 18 }}>
            <View
              style={{
                width: 44, height: 44, borderRadius: 22,
                backgroundColor: `${tintColor}1A`,
                alignItems: 'center', justifyContent: 'center',
              }}
            >
              <Ionicons name="briefcase" size={22} color={tintColor} />
            </View>
            <View style={{ flex: 1 }}>
              <Text style={{ color: colors.textSec, fontSize: 11, fontWeight: '800', letterSpacing: 0.6, textTransform: 'uppercase' }}>
                {tx('careerTracker.labels.applicationStatus', 'Application Status')}
              </Text>
              <Text
                style={{ color: colors.text, fontSize: 22, fontWeight: '800', marginTop: 2 }}
                data-testid="tracker-role-title"
                testID="tracker-role-title"
              >
                {data.role_title}
              </Text>
            </View>
          </View>

          <Text style={{ color: colors.text, fontSize: 15, fontWeight: '600', marginBottom: 4 }}>
            {tx('careerTracker.greeting', 'Hi {name},').replace('{name}', String(data.applicant_first_name || ''))}
          </Text>
          <Text style={{ color: colors.textSec, fontSize: 14, lineHeight: 22 }}>
            {tx('careerTracker.greetingSubtitle', "Here's the live status of your application. We'll update this page whenever something changes — feel free to bookmark it.")}
          </Text>

          {/* Status chip + submission date */}
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, flexWrap: 'wrap', marginTop: 18 }}>
            <View
              style={{
                paddingHorizontal: 12, paddingVertical: 6, borderRadius: 999,
                backgroundColor: `${tintColor}1A`,
                borderWidth: 1, borderColor: tintColor,
                flexDirection: 'row', alignItems: 'center', gap: 6,
              }}
              data-testid="tracker-status-pill"
              testID="tracker-status-pill"
            >
              <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: tintColor }} />
              <Text style={{ color: tintColor, fontSize: 12, fontWeight: '800' }}>{tintLabel}</Text>
            </View>
            {data.submitted_at ? (
              <Text style={{ color: colors.textMuted, fontSize: 12 }}>
                {tx('careerTracker.labels.submittedOn', 'Submitted {date}').replace('{date}', fmtDate(data.submitted_at))}
              </Text>
            ) : null}
            {data.attachment_count > 0 ? (
              <Text style={{ color: colors.textMuted, fontSize: 12 }}>
                {tx('careerTracker.labels.attachmentsCount', '· {count} attachment{suffix}')
                  .replace('{count}', String(data.attachment_count))
                  .replace('{suffix}', data.attachment_count === 1 ? '' : 's')}
              </Text>
            ) : null}
          </View>

          {/* Scheduled interview */}
          {data.interview?.start_utc ? (
            <View
              style={{
                marginTop: 18, padding: 14, borderRadius: 12,
                backgroundColor: `${colors.primary}0F`,
                borderWidth: 1, borderColor: `${colors.primary}30`,
                flexDirection: 'row', alignItems: 'center', gap: 10,
              }}
              data-testid="tracker-interview-card"
              testID="tracker-interview-card"
            >
              <Ionicons name="calendar" size={18} color={colors.primary} />
              <View style={{ flex: 1 }}>
                <Text style={{ color: colors.text, fontSize: 13, fontWeight: '700' }}>
                  {tx('careerTracker.labels.interviewScheduled', 'Interview scheduled')}
                </Text>
                <Text style={{ color: colors.textSec, fontSize: 12, marginTop: 2 }}>
                  {fmtDateTime(data.interview.start_utc)} · {data.interview.interview_type}
                </Text>
              </View>
            </View>
          ) : null}

          {/* Queue context — visible while the app is in the review queue */}
          {data.role_queue ? (
            <View
              style={{
                marginTop: 12, padding: 14, borderRadius: 12,
                backgroundColor: colors.bgSoft,
                borderWidth: 1, borderColor: colors.border,
                flexDirection: 'row', alignItems: 'center', gap: 10,
              }}
              data-testid="tracker-queue-card"
              testID="tracker-queue-card"
            >
              <Ionicons name="people" size={18} color={colors.textSec} />
              <View style={{ flex: 1 }}>
                <Text style={{ color: colors.text, fontSize: 13, fontWeight: '700' }}>
                  {tx('careerTracker.queue.oneOfApplicants', "You're one of {count} applicants for this role").replace('{count}', String(data.role_queue.total_in_role))}
                </Text>
                <Text style={{ color: colors.textSec, fontSize: 12, marginTop: 2 }}>
                  {tx('careerTracker.queue.reviewSla', 'Recruiters typically complete first-pass review within {hours} hours of submission.').replace('{hours}', String(data.role_queue.review_sla_hours))}
                </Text>
              </View>
            </View>
          ) : null}
        </View>

        {/* Timeline */}
        <View
          style={{
            backgroundColor: colors.card,
            borderRadius: 20,
            padding: 22,
            borderWidth: 1,
            borderColor: colors.border,
            marginBottom: 18,
          }}
          data-testid="tracker-timeline"
          testID="tracker-timeline"
        >
          <Text style={{ color: colors.textSec, fontSize: 11, fontWeight: '800', letterSpacing: 0.6, textTransform: 'uppercase', marginBottom: 14 }}>
            {tx('careerTracker.labels.progress', 'Progress')}
          </Text>
          {data.timeline.map((step, idx) => {
            const isActive = step.state === 'active';
            const isDone = step.state === 'done';
            const dotBg = isDone ? colors.primary : isActive ? tintColor : colors.border;
            const dotFg = isDone || isActive ? colors.primaryText : colors.textMuted;
            const titleColor = isActive ? colors.text : isDone ? colors.textSec : colors.textMuted;
            return (
              <View
                key={step.key}
                style={{ flexDirection: 'row', gap: 14, marginBottom: idx === data.timeline.length - 1 ? 0 : 14 }}
                data-testid={`tracker-step-${step.key}`}
                testID={`tracker-step-${step.key}`}
              >
                <View style={{ alignItems: 'center' }}>
                  <View
                    style={{
                      width: 30, height: 30, borderRadius: 15, backgroundColor: dotBg,
                      alignItems: 'center', justifyContent: 'center',
                    }}
                  >
                    {isDone ? (
                      <Ionicons name="checkmark" size={16} color={dotFg} />
                    ) : (
                      <Text style={{ color: dotFg, fontSize: 12, fontWeight: '800' }}>{idx + 1}</Text>
                    )}
                  </View>
                  {idx !== data.timeline.length - 1 ? (
                    <View
                      style={{
                        width: 2, flex: 1, backgroundColor: isDone ? colors.primary : colors.border,
                        marginTop: 4, minHeight: 20,
                      }}
                    />
                  ) : null}
                </View>
                <View style={{ flex: 1, paddingBottom: 8 }}>
                  <Text style={{ color: titleColor, fontSize: 15, fontWeight: '700' }}>
                    {step.title}
                  </Text>
                  <Text style={{ color: colors.textSec, fontSize: 13, marginTop: 4, lineHeight: 20 }}>
                    {step.subtitle}
                  </Text>
                </View>
              </View>
            );
          })}
        </View>

        {/* Application ID + contact */}
        <View
          style={{
            backgroundColor: colors.bgSoft,
            borderRadius: 14,
            padding: 18,
            borderWidth: 1,
            borderColor: colors.border,
          }}
        >
          <Text style={{ color: colors.textSec, fontSize: 11, fontWeight: '800', letterSpacing: 0.4, textTransform: 'uppercase', marginBottom: 8 }}>
            {tx('careerTracker.labels.reference', 'Reference')}
          </Text>
          <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14, flexWrap: 'wrap', gap: 6 }}>
            <Text style={{ color: colors.textSec, fontSize: 13 }}>{tx('careerTracker.labels.applicationId', 'Application ID')}</Text>
            <Text
              style={{ color: colors.text, fontSize: 13, fontWeight: '700', fontFamily: 'monospace' }}
              data-testid="tracker-app-id"
              testID="tracker-app-id"
              selectable
            >
              {data.application_id}
            </Text>
          </View>
          <Text style={{ color: colors.textSec, fontSize: 13, lineHeight: 20, marginBottom: 12 }}>
            {tx('careerTracker.labels.contactHint', "Questions, updates, or need to withdraw? Email us and include your Application ID — we'll reply within one business day.")}
          </Text>
          <View style={{ flexDirection: 'row', gap: 8, flexWrap: 'wrap' }}>
            <TouchableOpacity
              onPress={() => Linking.openURL(`mailto:${data.hiring_contact_email}?subject=${encodeURIComponent(`Re: ${data.role_title} [${data.application_id}]`)}`)}
              style={{
                paddingHorizontal: 16, paddingVertical: 12, borderRadius: 10,
                backgroundColor: colors.primary,
                flexDirection: 'row', alignItems: 'center', gap: 8,
              }}
              data-testid="tracker-contact-btn"
              testID="tracker-contact-btn"
            >
              <Ionicons name="mail" size={16} color={colors.primaryText} />
              <Text style={{ color: colors.primaryText, fontSize: 13, fontWeight: '800' }}>
                {tx('careerTracker.actions.emailAddress', 'Email {email}').replace('{email}', String(data.hiring_contact_email || ''))}
              </Text>
            </TouchableOpacity>
            {data.status !== 'withdrawn' && data.status !== 'hired' && data.status !== 'rejected' ? (
              <TouchableOpacity
                onPress={() => setWithdrawOpen(true)}
                style={{
                  paddingHorizontal: 14, paddingVertical: 12, borderRadius: 10,
                  backgroundColor: 'transparent',
                  borderWidth: 1, borderColor: colors.border,
                  flexDirection: 'row', alignItems: 'center', gap: 6,
                }}
                data-testid="tracker-withdraw-btn"
                testID="tracker-withdraw-btn"
              >
                <Ionicons name="close-circle-outline" size={14} color={colors.textSec} />
                <Text style={{ color: colors.textSec, fontSize: 12, fontWeight: '700' }}>
                  {tx('careerTracker.actions.withdrawApplication', 'Withdraw application')}
                </Text>
              </TouchableOpacity>
            ) : null}
          </View>
        </View>

        <Text
          style={{ color: colors.textMuted, fontSize: 11, textAlign: 'center', marginTop: 24, lineHeight: 18 }}
        >
          {tx('careerTracker.footer.linkPrivacy', "This link is a bookmarkable status page. Your Application ID is the only credential — don't share it publicly.")}
        </Text>
      </View>

      {/* Withdraw confirmation modal */}
      <Modal visible={withdrawOpen} transparent animationType="fade" onRequestClose={() => setWithdrawOpen(false)}>
        <View style={{ flex: 1, backgroundColor: 'rgba(15,23,42,0.55)', alignItems: 'center', justifyContent: 'center', padding: 20 }}>
          <View
            style={{ backgroundColor: colors.card, borderRadius: 16, padding: 22, width: '100%', maxWidth: 460, borderWidth: 1, borderColor: colors.border }}
            data-testid="tracker-withdraw-modal"
            testID="tracker-withdraw-modal"
          >
            <Text style={{ color: colors.text, fontSize: 17, fontWeight: '800', marginBottom: 6 }}>
              {tx('careerTracker.withdraw.title', 'Withdraw this application?')}
            </Text>
            <Text style={{ color: colors.textSec, fontSize: 13, lineHeight: 20, marginBottom: 14 }}>
              {tx('careerTracker.withdraw.subtitle', "We'll let the hiring team know and remove your application from active review. You can always re-apply later for the same or a different role.")}
            </Text>
            <TextInput
              value={withdrawReason}
              onChangeText={setWithdrawReason}
              placeholder={tx('careerTracker.withdraw.placeholders.reason', 'Optional — reason for withdrawing')}
              placeholderTextColor={colors.placeholder}
              multiline
              numberOfLines={3}
              maxLength={500}
              style={{
                backgroundColor: colors.input, color: colors.inputText,
                borderRadius: 8, borderWidth: 1, borderColor: colors.inputBorder,
                padding: 12, fontSize: 13, minHeight: 80, textAlignVertical: 'top',
              }}
              data-testid="tracker-withdraw-reason"
              testID="tracker-withdraw-reason"
            />
            {withdrawErr ? (
              <Text style={{ color: colors.error, fontSize: 12, marginTop: 8 }}>{withdrawErr}</Text>
            ) : null}
            <View style={{ flexDirection: 'row', justifyContent: 'flex-end', gap: 10, marginTop: 14 }}>
              <TouchableOpacity
                onPress={() => { setWithdrawOpen(false); setWithdrawReason(''); setWithdrawErr(''); }}
                disabled={withdrawing}
                style={{ paddingHorizontal: 14, paddingVertical: 10, borderRadius: 8 }}
                data-testid="tracker-withdraw-cancel"
                testID="tracker-withdraw-cancel"
              >
                <Text style={{ color: colors.textSec, fontSize: 13, fontWeight: '700' }}>{tx('common.cancel', 'Cancel')}</Text>
              </TouchableOpacity>
              <TouchableOpacity
                onPress={doWithdraw}
                disabled={withdrawing}
                style={{
                  paddingHorizontal: 16, paddingVertical: 10, borderRadius: 8,
                  backgroundColor: colors.error,
                  flexDirection: 'row', alignItems: 'center', gap: 6,
                }}
                data-testid="tracker-withdraw-confirm"
                testID="tracker-withdraw-confirm"
              >
                {withdrawing ? (
                  <ActivityIndicator size="small" color={colors.primaryText} />
                ) : (
                  <Ionicons name="close-circle" size={14} color={colors.primaryText} />
                )}
                <Text style={{ color: colors.primaryText, fontSize: 13, fontWeight: '800' }}>
                  {withdrawing ? tx('careerTracker.withdraw.states.withdrawing', 'Withdrawing…') : tx('careerTracker.withdraw.actions.confirmWithdraw', 'Confirm withdraw')}
                </Text>
              </TouchableOpacity>
            </View>
          </View>
        </View>
      </Modal>
    </ScrollView>
  );
}