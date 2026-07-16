import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  ActivityIndicator,
  RefreshControl,
  ScrollView,
  Text,
  TextInput,
  TouchableOpacity,
  useWindowDimensions,
  View,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import { useTheme } from '../../context/ThemeContext';
import { useTranslation } from '../../hooks/useTranslation';
import TosManagementPanel from '../admin/TosManagementPanel';
import { handleAppRecoverableError } from '../../utils/appRecoverableError';
import {
  fetchLegalUpdateBundle,
  getAiLegalSuggestion,
  getLegalSuggestionAnalytics,
  logLegalSuggestionFeedback,
  runLegalNoticeDryRun,
  sendLegalNoticeBroadcast,
  upsertLegalContentPage,
} from '../../services/legalUpdateEnterprise';

type TabKey = 'cookies' | 'privacy' | 'tos';

type NotificationDraft = {
  effective_date: string;
  summary_of_changes: string;
  review_url: string;
  audience: 'all_users' | 'affected_only';
  user_ids_text: string;
  confirm_phrase: string;
};

const txFallback = (t: (key: string) => string, key: string, fallback: string) => {
  const value = t(key);
  return value === key ? fallback : value;
};

const formatDateTime = (value?: string | null) => {
  if (!value) return '—';
  try {
    return new Date(value).toLocaleString();
  } catch {
    return String(value);
  }
};

const TabButton = ({ active, label, onPress, colors, testId }: { active: boolean; label: string; onPress: () => void; colors: any; testId: string }) => (
  <TouchableOpacity accessibilityLabel="On press in legal update enterprise workspace button"
    onPress={onPress}
    style={{
      paddingHorizontal: 14,
      paddingVertical: 9,
      borderRadius: 999,
      borderWidth: 1,
      borderColor: active ? colors.primary : colors.border,
      backgroundColor: active ? `${colors.primary}20` : colors.cardBg,
    }}
    data-testid={testId}
    testID={testId}
  >
    <Text style={{ color: active ? colors.primary : colors.text, fontSize: 12, fontWeight: '800' }}>{label}</Text>
  </TouchableOpacity>
);

const SectionCard = ({ children, colors, testId }: { children: React.ReactNode; colors: any; testId: string }) => (
  <View
    style={{
      borderRadius: 16,
      borderWidth: 1,
      borderColor: colors.border,
      backgroundColor: colors.cardBg,
      padding: 14,
      gap: 10,
    }}
    data-testid={testId}
    testID={testId}
  >
    {children}
  </View>
);

const ActionButton = ({
  label,
  onPress,
  colors,
  testId,
  disabled,
  danger,
}: {
  label: string;
  onPress: () => void;
  colors: any;
  testId: string;
  disabled?: boolean;
  danger?: boolean;
}) => (
  <TouchableOpacity accessibilityLabel="On press in legal update enterprise workspace button"
    onPress={onPress}
    disabled={disabled}
    style={{
      borderRadius: 999,
      paddingHorizontal: 12,
      paddingVertical: 9,
      borderWidth: 1,
      borderColor: danger ? `${colors.error}70` : colors.border,
      backgroundColor: danger ? `${colors.error}1A` : colors.bgSoft,
      opacity: disabled ? 0.55 : 1,
    }}
    data-testid={testId}
    testID={testId}
  >
    <Text style={{ color: danger ? colors.error : colors.text, fontSize: 11, fontWeight: '800' }}>{label}</Text>
  </TouchableOpacity>
);

const UnsupportedNote = ({ title, details, colors, testId }: { title: string; details: string; colors: any; testId: string }) => (
  <View
    style={{
      borderRadius: 10,
      borderWidth: 1,
      borderStyle: 'dashed',
      borderColor: `${colors.warning}88`,
      backgroundColor: `${colors.warning}14`,
      padding: 10,
      gap: 4,
    }}
    data-testid={testId}
    testID={testId}
  >
    <Text style={{ color: colors.warningText, fontSize: 12, fontWeight: '800' }}>{title}</Text>
    <Text style={{ color: colors.warningText, fontSize: 11, lineHeight: 16 }}>{details}</Text>
  </View>
);

const defaultNotificationDraft = (): NotificationDraft => ({
  effective_date: '',
  summary_of_changes: '',
  review_url: '',
  audience: 'all_users',
  user_ids_text: '',
  confirm_phrase: '',
});

export default function LegalUpdateEnterpriseWorkspace() {
  const { colors } = useTheme();
  const { t } = useTranslation();
  const tx = useCallback((key: string, fallback: string) => txFallback(t, key, fallback), [t]);
  const { width } = useWindowDimensions();
  const isMobile = width < 760;

  const [activeTab, setActiveTab] = useState<TabKey>('cookies');
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [statusMessage, setStatusMessage] = useState<{ type: 'success' | 'error' | 'info'; message: string } | null>(null);
  const [lastUpdated, setLastUpdated] = useState('');

  const [contentPages, setContentPages] = useState<any[]>([]);
  const [accessLogs, setAccessLogs] = useState<any[]>([]);
  const [legalBroadcasts, setLegalBroadcasts] = useState<any[]>([]);
  const [tosVersions, setTosVersions] = useState<any[]>([]);
  const [tosStats, setTosStats] = useState<any>(null);
  const [currentTos, setCurrentTos] = useState<any>(null);

  const [supported, setSupported] = useState<Record<string, boolean>>({});

  const [docDrafts, setDocDrafts] = useState<Record<'cookies' | 'privacy', { title: string; slug: string; status: string; body: string }>>({
    cookies: { title: 'Cookies Policy', slug: 'cookies', status: 'draft', body: '' },
    privacy: { title: 'Privacy Policy', slug: 'privacy-policy', status: 'draft', body: '' },
  });

  const [notificationDrafts, setNotificationDrafts] = useState<Record<TabKey, NotificationDraft>>({
    cookies: defaultNotificationDraft(),
    privacy: defaultNotificationDraft(),
    tos: defaultNotificationDraft(),
  });
  const [notificationPreview, setNotificationPreview] = useState<Record<TabKey, any | null>>({
    cookies: null,
    privacy: null,
    tos: null,
  });
  const [aiSuggestingTab, setAiSuggestingTab] = useState<Record<TabKey, boolean>>({
    cookies: false,
    privacy: false,
    tos: false,
  });
  const [aiSuggestionMeta, setAiSuggestionMeta] = useState<Record<TabKey, any | null>>({
    cookies: null,
    privacy: null,
    tos: null,
  });
  const [aiStylePreset, setAiStylePreset] = useState<Record<TabKey, 'formal' | 'regulatory' | 'plain-language'>>({
    cookies: 'formal',
    privacy: 'formal',
    tos: 'regulatory',
  });
  const [aiPendingSuggestion, setAiPendingSuggestion] = useState<Record<TabKey, any | null>>({
    cookies: null,
    privacy: null,
    tos: null,
  });
  const [aiIntentCounters, setAiIntentCounters] = useState<Record<string, any>>({});
  const [compliantPresetPack, setCompliantPresetPack] = useState<Record<TabKey, { subject: string; effectiveSummary: string; cta: string } | null>>({
    cookies: null,
    privacy: null,
    tos: null,
  });

  const [savingKey, setSavingKey] = useState('');
  const pendingRef = useRef(false);
  const aliveRef = useRef(true);

  const policyMap: Record<TabKey, string> = {
    cookies: 'Cookie Policy',
    privacy: 'Privacy Policy',
    tos: 'Terms of Service',
  };

  const findPolicyPage = useCallback((kind: 'cookies' | 'privacy') => {
    const slugCandidates = kind === 'cookies'
      ? ['cookies', 'cookie-policy', 'cookie-policy-page']
      : ['privacy-policy', 'privacy', 'privacy-policy-page'];
    const lowerSet = new Set(slugCandidates.map((x) => x.toLowerCase()));
    return contentPages.find((p) => lowerSet.has(String(p?.slug || '').toLowerCase())) || null;
  }, [contentPages]);

  const hydrateDraftsFromPages = useCallback((pages: any[]) => {
    const findByCandidates = (candidates: string[]) =>
      pages.find((p: any) => candidates.includes(String(p?.slug || '').toLowerCase())) || null;

    const cookiePage = findByCandidates(['cookies', 'cookie-policy', 'cookie-policy-page']);
    const privacyPage = findByCandidates(['privacy-policy', 'privacy', 'privacy-policy-page']);

    setDocDrafts({
      cookies: {
        title: cookiePage?.title || 'Cookies Policy',
        slug: cookiePage?.slug || 'cookies',
        status: cookiePage?.status || 'draft',
        body: cookiePage?.body || '',
      },
      privacy: {
        title: privacyPage?.title || 'Privacy Policy',
        slug: privacyPage?.slug || 'privacy-policy',
        status: privacyPage?.status || 'draft',
        body: privacyPage?.body || '',
      },
    });
  }, []);

  const loadBundle = useCallback(async (mode: 'initial' | 'refresh' | 'silent' = 'initial') => {
    if (pendingRef.current) return;
    pendingRef.current = true;
    if (mode === 'initial') setLoading(true);
    if (mode === 'refresh') setRefreshing(true);
    setError(null);

    try {
      const bundle = await fetchLegalUpdateBundle();
      if (!aliveRef.current) return;

      const supportFlags: Record<string, boolean> = {};
      const pick = (key: string, result: PromiseSettledResult<any>, setter: (value: any) => void, fallback: any) => {
        if (result.status === 'fulfilled') {
          supportFlags[key] = true;
          setter(result.value?.data ?? fallback);
          return;
        }
        supportFlags[key] = false;
        setter(fallback);
      };

      pick('contentPages', bundle.contentPages, (data) => setContentPages(data?.pages || []), []);
      pick('accessLogs', bundle.accessLogs, (data) => setAccessLogs(data?.logs || []), []);
      pick('legalBroadcasts', bundle.legalBroadcasts, (data) => setLegalBroadcasts(data?.items || []), []);
      pick('tosVersions', bundle.tosVersions, (data) => setTosVersions(data?.versions || []), []);
      pick('tosStats', bundle.tosStats, setTosStats, null);
      pick('currentTos', bundle.currentTos, (data) => setCurrentTos(data?.tos || null), null);

      if (bundle.contentPages.status === 'fulfilled') {
        hydrateDraftsFromPages(bundle.contentPages.value?.data?.pages || []);
      }

      setSupported(supportFlags);
      if (!supportFlags.contentPages && !supportFlags.tosVersions) {
        setError('Legal data endpoints are unavailable for this session.');
      }

      try {
        const aiStats = await getLegalSuggestionAnalytics(30);
        if (aliveRef.current) {
          setAiIntentCounters(aiStats?.by_intent || {});
        }
      } catch (error) { handleAppRecoverableError({ scope: 'src/components/executive/LegalUpdateEnterpriseWorkspace.tsx#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }

      setLastUpdated(new Date().toISOString());
    } catch (err: any) {
      setError(err?.message || 'Failed to load legal governance data');
    } finally {
      pendingRef.current = false;
      if (aliveRef.current) {
        setLoading(false);
        setRefreshing(false);
      }
    }
  }, [hydrateDraftsFromPages]);

  useEffect(() => {
    loadBundle('initial');
    const timer = setInterval(() => loadBundle('silent'), 60000);
    return () => {
      aliveRef.current = false;
      clearInterval(timer);
    };
  }, [loadBundle]);

  const withAction = async (key: string, fn: () => Promise<void>) => {
    setSavingKey(key);
    try {
      await fn();
    } catch (err: any) {
      setStatusMessage({
        type: 'error',
        message: err?.response?.data?.detail || err?.message || 'Action failed',
      });
    } finally {
      setSavingKey('');
    }
  };

  const saveContentDocument = async (kind: 'cookies' | 'privacy') => {
    const draft = docDrafts[kind];
    if (!draft.title.trim() || !draft.slug.trim()) {
      setStatusMessage({ type: 'error', message: 'Title and slug are required.' });
      return;
    }

    await withAction(`save-${kind}`, async () => {
      await upsertLegalContentPage({
        title: draft.title.trim(),
        slug: draft.slug.trim(),
        status: draft.status || 'draft',
        body: draft.body || '',
      });
      setStatusMessage({ type: 'success', message: `${kind === 'cookies' ? 'Cookies' : 'Privacy'} policy saved.` });
      await loadBundle('silent');
    });
  };

  const runDryRun = async (tab: TabKey) => {
    const draft = notificationDrafts[tab];
    if (!draft.effective_date.trim() || draft.summary_of_changes.trim().length < 10) {
      setStatusMessage({ type: 'error', message: 'Effective date and summary (min 10 chars) are required for dry-run.' });
      return;
    }

    await withAction(`dryrun-${tab}`, async () => {
      const userIds = draft.audience === 'affected_only'
        ? draft.user_ids_text.split(',').map((id) => id.trim()).filter(Boolean)
        : [];

      const preview = await runLegalNoticeDryRun({
        policy_type: policyMap[tab],
        effective_date: draft.effective_date.trim(),
        summary_of_changes: draft.summary_of_changes.trim(),
        review_url: draft.review_url.trim(),
        audience: draft.audience,
        user_ids: userIds,
      });

      setNotificationPreview((prev) => ({ ...prev, [tab]: preview }));
      setNotificationDrafts((prev) => ({ ...prev, [tab]: { ...prev[tab], confirm_phrase: '' } }));
      setStatusMessage({ type: 'info', message: `${policyMap[tab]} dry-run complete.` });
    });
  };

  const sendBroadcast = async (tab: TabKey) => {
    const draft = notificationDrafts[tab];
    const preview = notificationPreview[tab];
    if (!preview) {
      setStatusMessage({ type: 'error', message: 'Run dry-run first.' });
      return;
    }
    if (draft.confirm_phrase.trim() !== 'SEND') {
      setStatusMessage({ type: 'error', message: 'Type SEND exactly to confirm.' });
      return;
    }

    await withAction(`send-${tab}`, async () => {
      const userIds = draft.audience === 'affected_only'
        ? draft.user_ids_text.split(',').map((id) => id.trim()).filter(Boolean)
        : [];

      const result = await sendLegalNoticeBroadcast({
        policy_type: policyMap[tab],
        effective_date: draft.effective_date.trim(),
        summary_of_changes: draft.summary_of_changes.trim(),
        review_url: draft.review_url.trim(),
        audience: draft.audience,
        user_ids: userIds,
        confirm_phrase: 'SEND',
      });

      setStatusMessage({
        type: 'success',
        message: `${policyMap[tab]} broadcast sent. Delivered ${result?.sent_ok ?? 0}, failed ${result?.sent_failed ?? 0}.`,
      });
      setNotificationPreview((prev) => ({ ...prev, [tab]: null }));
      setNotificationDrafts((prev) => ({ ...prev, [tab]: defaultNotificationDraft() }));
      await loadBundle('silent');
    });
  };

  const requestAiSuggestion = async (tab: TabKey, intent: 'draft' | 'improve_tone' | 'shorten' | 'expand') => {
    const draft = notificationDrafts[tab];
    const baseMessage = (draft.summary_of_changes || '').trim();
    if (baseMessage.length < 8) {
      setStatusMessage({ type: 'error', message: 'Add a short change summary first, then use AI Suggest.' });
      return;
    }

    setAiSuggestingTab((prev) => ({ ...prev, [tab]: true }));
    try {
      const style = aiStylePreset[tab];
      const res = await getAiLegalSuggestion({
        subject: `${policyMap[tab]} update notice`,
        message: `${baseMessage}\n\nStyle requirement: ${style}. Keep legal wording precise and compliant.`,
        intent,
      });
      const suggestion = res?.suggestion;
      if (suggestion?.message) {
        setAiPendingSuggestion((prev) => ({
          ...prev,
          [tab]: {
            text: suggestion.message,
            intent,
            style_preset: style,
            source: suggestion.source || '',
            confidence: suggestion.confidence || 0,
          },
        }));
        setAiSuggestionMeta((prev) => ({ ...prev, [tab]: suggestion }));
        setStatusMessage({ type: 'success', message: `${policyMap[tab]} AI suggestion ready. Accept or reject it.` });
      }
    } catch (err: any) {
      setStatusMessage({ type: 'error', message: err?.response?.data?.detail || 'AI Suggest is temporarily unavailable.' });
    } finally {
      setAiSuggestingTab((prev) => ({ ...prev, [tab]: false }));
    }
  };

  const acceptAiSuggestion = async (tab: TabKey) => {
    const pending = aiPendingSuggestion[tab];
    if (!pending?.text) return;

    setNotificationDrafts((prev) => ({
      ...prev,
      [tab]: {
        ...prev[tab],
        summary_of_changes: pending.text,
      },
    }));

    try {
      await logLegalSuggestionFeedback({
        policy_type: policyMap[tab] as any,
        intent: pending.intent,
        style_preset: pending.style_preset,
        decision: 'accepted',
        source: pending.source,
        confidence: pending.confidence,
        summary_length: String(pending.text || '').length,
      });
      const stats = await getLegalSuggestionAnalytics(30);
      setAiIntentCounters(stats?.by_intent || {});
    } catch (error) { handleAppRecoverableError({ scope: 'src/components/executive/LegalUpdateEnterpriseWorkspace.tsx#catch2', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }

    setAiPendingSuggestion((prev) => ({ ...prev, [tab]: null }));
    setStatusMessage({ type: 'success', message: 'AI suggestion accepted and logged in legal audit trail.' });
  };

  const rejectAiSuggestion = async (tab: TabKey) => {
    const pending = aiPendingSuggestion[tab];
    if (!pending?.text) return;
    try {
      await logLegalSuggestionFeedback({
        policy_type: policyMap[tab] as any,
        intent: pending.intent,
        style_preset: pending.style_preset,
        decision: 'rejected',
        source: pending.source,
        confidence: pending.confidence,
        summary_length: String(pending.text || '').length,
      });
      const stats = await getLegalSuggestionAnalytics(30);
      setAiIntentCounters(stats?.by_intent || {});
    } catch (error) { handleAppRecoverableError({ scope: 'src/components/executive/LegalUpdateEnterpriseWorkspace.tsx#catch3', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
    setAiPendingSuggestion((prev) => ({ ...prev, [tab]: null }));
    setStatusMessage({ type: 'info', message: 'AI suggestion rejected and logged in legal audit trail.' });
  };

  const parseCompliantPack = (rawText: string, tab: TabKey, effectiveDate: string, reviewUrl: string) => {
    const lines = String(rawText || '').split('\n').map((line) => line.trim()).filter(Boolean);
    let subject = '';
    let effectiveSummary = '';
    let cta = '';

    lines.forEach((line) => {
      const lower = line.toLowerCase();
      if (!subject && lower.startsWith('subject:')) {
        subject = line.replace(/^subject\s*:\s*/i, '').trim();
      } else if (!effectiveSummary && (lower.startsWith('effective-date summary:') || lower.startsWith('effective date summary:') || lower.startsWith('summary:'))) {
        effectiveSummary = line.replace(/^(effective-date summary|effective date summary|summary)\s*:\s*/i, '').trim();
      } else if (!cta && lower.startsWith('cta:')) {
        cta = line.replace(/^cta\s*:\s*/i, '').trim();
      }
    });

    if (!subject) {
      subject = `Important: ${policyMap[tab]} Updated — Effective ${effectiveDate}`;
    }
    if (!effectiveSummary) {
      effectiveSummary = rawText.trim();
    }
    if (!cta) {
      cta = reviewUrl?.trim()
        ? `Review full policy: ${reviewUrl.trim()}`
        : 'Review the full policy inside the LEGAL UPDATE center.';
    }

    return { subject, effectiveSummary, cta };
  };

  const generateCompliantPack = async (tab: TabKey) => {
    const draft = notificationDrafts[tab];
    const baseSummary = (draft.summary_of_changes || '').trim();
    const effectiveDate = (draft.effective_date || '').trim();
    if (!effectiveDate) {
      setStatusMessage({ type: 'error', message: 'Effective date is required for compliant one-click generation.' });
      return;
    }
    if (baseSummary.length < 8) {
      setStatusMessage({ type: 'error', message: 'Please add a short summary first, then generate compliant pack.' });
      return;
    }

    setAiSuggestingTab((prev) => ({ ...prev, [tab]: true }));
    try {
      const response = await getAiLegalSuggestion({
        subject: `${policyMap[tab]} legal campaign`,
        message: `${baseSummary}\n\nGenerate compliant legal campaign copy in this exact format:\nSubject: ...\nEffective-Date Summary: ...\nCTA: ...\nEffective date: ${effectiveDate}\nReview URL: ${draft.review_url || ''}\nStyle requirement: regulatory.`,
        intent: 'draft',
      });

      const suggestion = response?.suggestion;
      const text = String(suggestion?.message || '').trim();
      if (!text) {
        throw new Error('No AI content returned for compliant pack.');
      }

      const pack = parseCompliantPack(text, tab, effectiveDate, draft.review_url || '');
      setCompliantPresetPack((prev) => ({ ...prev, [tab]: pack }));
      setAiSuggestionMeta((prev) => ({ ...prev, [tab]: suggestion }));
      setNotificationDrafts((prev) => ({
        ...prev,
        [tab]: {
          ...prev[tab],
          summary_of_changes: `${pack.effectiveSummary}\n\n${pack.cta}`,
        },
      }));

      try {
        await logLegalSuggestionFeedback({
          policy_type: policyMap[tab] as any,
          intent: 'draft',
          style_preset: 'regulatory',
          decision: 'accepted',
          source: suggestion?.source || '',
          confidence: suggestion?.confidence,
          summary_length: `${pack.effectiveSummary} ${pack.cta}`.trim().length,
          note: 'one_click_compliant_pack',
        });
        const stats = await getLegalSuggestionAnalytics(30);
        setAiIntentCounters(stats?.by_intent || {});
      } catch (error) { handleAppRecoverableError({ scope: 'src/components/executive/LegalUpdateEnterpriseWorkspace.tsx#catch4', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }

      setStatusMessage({ type: 'success', message: 'Compliant subject + effective-date summary + CTA generated and applied.' });
    } catch (err: any) {
      setStatusMessage({ type: 'error', message: err?.response?.data?.detail || err?.message || 'Compliant one-click generation failed.' });
    } finally {
      setAiSuggestingTab((prev) => ({ ...prev, [tab]: false }));
    }
  };

  const legalDocAuditRows = useCallback((slug: string | null) => {
    if (!slug) return [];
    return accessLogs.filter((row: any) => {
      const action = String(row?.action || '');
      const metaSlug = String(row?.metadata?.slug || '').toLowerCase();
      return ['update_content_page', 'delete_content_page'].includes(action) && metaSlug === slug.toLowerCase();
    });
  }, [accessLogs]);

  const legalBroadcastRows = useCallback((policyType: string) => {
    return legalBroadcasts.filter((row: any) => String(row?.policy_type || '').toLowerCase() === policyType.toLowerCase());
  }, [legalBroadcasts]);

  const cookiesPage = findPolicyPage('cookies');
  const privacyPage = findPolicyPage('privacy');

  const legalCoverageStatus = useMemo(() => {
    const tosAvailable = supported.tosVersions || supported.currentTos;
    const cookieAvailable = Boolean(cookiesPage);
    const privacyAvailable = Boolean(privacyPage);
    return {
      tosAvailable,
      cookieAvailable,
      privacyAvailable,
    };
  }, [supported, cookiesPage, privacyPage]);

  const renderNotificationComposer = (tab: TabKey) => {
    const draft = notificationDrafts[tab];
    const preview = notificationPreview[tab];
    const aiMeta = aiSuggestionMeta[tab];
    const pending = aiPendingSuggestion[tab];
    const stylePreset = aiStylePreset[tab];
    const prefix = `legal-update-${tab}`;

    return (
      <SectionCard colors={colors} testId={`${prefix}-notification-card`}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 7 }}>
          <Ionicons name="mail" size={16} color={colors.primary} />
          <Text style={{ color: colors.text, fontSize: 14, fontWeight: '800' }}>Notification Workflow</Text>
        </View>
        <Text style={{ color: colors.textMuted, fontSize: 11, lineHeight: 17 }} data-testid={`${prefix}-notification-subtitle`} testID={`${prefix}-notification-subtitle`}>
          DRY-RUN first, then confirm with SEND for real dispatch. Uses real legal broadcast API.
        </Text>

        <TextInput
          value={draft.effective_date}
          onChangeText={(text) => setNotificationDrafts((prev) => ({ ...prev, [tab]: { ...prev[tab], effective_date: text } }))}
          placeholder="Effective date"
          placeholderTextColor={colors.textMuted}
          style={{ borderWidth: 1, borderColor: colors.border, borderRadius: 10, paddingHorizontal: 10, paddingVertical: 9, fontSize: 12, backgroundColor: colors.bgSoft, color: colors.text }}
          data-testid={`${prefix}-effective-date-input`}
          testID={`${prefix}-effective-date-input`}
        />

        <TextInput
          value={draft.summary_of_changes}
          onChangeText={(text) => setNotificationDrafts((prev) => ({ ...prev, [tab]: { ...prev[tab], summary_of_changes: text } }))}
          placeholder="Summary of changes"
          placeholderTextColor={colors.textMuted}
          multiline
          style={{ borderWidth: 1, borderColor: colors.border, borderRadius: 10, minHeight: 74, textAlignVertical: 'top', paddingHorizontal: 10, paddingVertical: 9, fontSize: 12, backgroundColor: colors.bgSoft, color: colors.text }}
          data-testid={`${prefix}-summary-input`}
          testID={`${prefix}-summary-input`}
        />

        <View style={{ borderWidth: 1, borderColor: colors.border, borderRadius: 10, backgroundColor: colors.bgSoft, padding: 10, gap: 8 }} data-testid={`${prefix}-ai-suggest-panel`} testID={`${prefix}-ai-suggest-panel`}>
          <Text style={{ color: colors.text, fontSize: 12, fontWeight: '800' }}>AI Suggest Reply</Text>
          <Text style={{ color: colors.textMuted, fontSize: 11 }}>Uses platform AI assist endpoint with your current legal summary as source input.</Text>

          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
            {(['formal', 'regulatory', 'plain-language'] as const).map((style) => (
              <ActionButton
                key={style}
                label={stylePreset === style ? `Style: ${style}` : style}
                onPress={() => setAiStylePreset((prev) => ({ ...prev, [tab]: style }))}
                colors={colors}
                testId={`${prefix}-ai-style-${style}-button`}
                disabled={aiSuggestingTab[tab]}
              />
            ))}
          </View>

          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
            <ActionButton
              label={aiSuggestingTab[tab] ? 'Generating...' : 'Suggest Draft'}
              onPress={() => requestAiSuggestion(tab, 'draft')}
              colors={colors}
              testId={`${prefix}-ai-suggest-draft-button`}
              disabled={aiSuggestingTab[tab]}
            />
            <ActionButton
              label="Improve Tone"
              onPress={() => requestAiSuggestion(tab, 'improve_tone')}
              colors={colors}
              testId={`${prefix}-ai-suggest-tone-button`}
              disabled={aiSuggestingTab[tab]}
            />
            <ActionButton
              label="Shorten"
              onPress={() => requestAiSuggestion(tab, 'shorten')}
              colors={colors}
              testId={`${prefix}-ai-suggest-shorten-button`}
              disabled={aiSuggestingTab[tab]}
            />
            <ActionButton
              label="Expand"
              onPress={() => requestAiSuggestion(tab, 'expand')}
              colors={colors}
              testId={`${prefix}-ai-suggest-expand-button`}
              disabled={aiSuggestingTab[tab]}
            />
            <ActionButton
              label="One-click compliant pack"
              onPress={() => generateCompliantPack(tab)}
              colors={colors}
              testId={`${prefix}-ai-compliant-pack-button`}
              disabled={aiSuggestingTab[tab]}
            />
          </View>

          <View style={{ borderWidth: 1, borderColor: colors.border, borderRadius: 8, padding: 8, backgroundColor: `${colors.textMuted}08`, gap: 4 }} data-testid={`${prefix}-ai-intent-counters`} testID={`${prefix}-ai-intent-counters`}>
            <Text style={{ color: colors.text, fontSize: 11, fontWeight: '700' }}>Intent usage counters (30d)</Text>
            {(['draft', 'improve_tone', 'shorten', 'expand'] as const).map((intentKey) => {
              const metric = aiIntentCounters?.[intentKey] || { used: 0, accepted: 0, rejected: 0, accept_rate: 0 };
              return (
                <Text key={intentKey} style={{ color: colors.textMuted, fontSize: 10 }} data-testid={`${prefix}-ai-counter-${intentKey}`} testID={`${prefix}-ai-counter-${intentKey}`}>
                  {intentKey}: used {metric.used || 0} • accepted {metric.accepted || 0} • rejected {metric.rejected || 0}
                </Text>
              );
            })}
          </View>

          {pending ? (
            <View style={{ borderWidth: 1, borderColor: `${colors.primary}66`, borderRadius: 8, padding: 8, gap: 6, backgroundColor: `${colors.primary}10` }} data-testid={`${prefix}-ai-pending-card`} testID={`${prefix}-ai-pending-card`}>
              <Text style={{ color: colors.text, fontSize: 11, fontWeight: '700' }}>Pending suggestion ({pending.intent}, {pending.style_preset})</Text>
              <Text style={{ color: colors.text, fontSize: 11, lineHeight: 16 }} numberOfLines={5}>{pending.text}</Text>
              <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
                <ActionButton
                  label="Accept"
                  onPress={() => acceptAiSuggestion(tab)}
                  colors={colors}
                  testId={`${prefix}-ai-accept-button`}
                  disabled={aiSuggestingTab[tab]}
                />
                <ActionButton
                  label="Reject"
                  onPress={() => rejectAiSuggestion(tab)}
                  colors={colors}
                  testId={`${prefix}-ai-reject-button`}
                  disabled={aiSuggestingTab[tab]}
                  danger
                />
              </View>
            </View>
          ) : null}

          {compliantPresetPack[tab] ? (
            <View style={{ borderWidth: 1, borderColor: `${colors.successText}66`, borderRadius: 8, padding: 8, gap: 4, backgroundColor: `${colors.successText}10` }} data-testid={`${prefix}-ai-compliant-pack-card`} testID={`${prefix}-ai-compliant-pack-card`}>
              <Text style={{ color: colors.successText, fontSize: 11, fontWeight: '800' }}>Compliant Pack Preview</Text>
              <Text style={{ color: colors.text, fontSize: 11 }} data-testid={`${prefix}-ai-compliant-pack-subject`} testID={`${prefix}-ai-compliant-pack-subject`}>
                Subject: {compliantPresetPack[tab]?.subject}
              </Text>
              <Text style={{ color: colors.textMuted, fontSize: 10 }} numberOfLines={3} data-testid={`${prefix}-ai-compliant-pack-summary`} testID={`${prefix}-ai-compliant-pack-summary`}>
                Effective-Date Summary: {compliantPresetPack[tab]?.effectiveSummary}
              </Text>
              <Text style={{ color: colors.textMuted, fontSize: 10 }} numberOfLines={2} data-testid={`${prefix}-ai-compliant-pack-cta`} testID={`${prefix}-ai-compliant-pack-cta`}>
                CTA: {compliantPresetPack[tab]?.cta}
              </Text>
            </View>
          ) : null}

          {aiMeta ? (
            <Text style={{ color: colors.textMuted, fontSize: 10 }} data-testid={`${prefix}-ai-suggest-meta`} testID={`${prefix}-ai-suggest-meta`}>
              Source: {aiMeta?.source || 'deterministic'} • Confidence: {Math.round((aiMeta?.confidence || 0) * 100)}%
            </Text>
          ) : null}
        </View>

        <TextInput
          value={draft.review_url}
          onChangeText={(text) => setNotificationDrafts((prev) => ({ ...prev, [tab]: { ...prev[tab], review_url: text } }))}
          placeholder="Review URL (optional)"
          placeholderTextColor={colors.textMuted}
          style={{ borderWidth: 1, borderColor: colors.border, borderRadius: 10, paddingHorizontal: 10, paddingVertical: 9, fontSize: 12, backgroundColor: colors.bgSoft, color: colors.text }}
          data-testid={`${prefix}-review-url-input`}
          testID={`${prefix}-review-url-input`}
        />

        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
          <ActionButton
            label={`Audience: ${draft.audience}`}
            onPress={() => setNotificationDrafts((prev) => ({
              ...prev,
              [tab]: {
                ...prev[tab],
                audience: prev[tab].audience === 'all_users' ? 'affected_only' : 'all_users',
              },
            }))}
            colors={colors}
            testId={`${prefix}-audience-toggle-button`}
          />
          <ActionButton
            label={savingKey === `dryrun-${tab}` ? 'Previewing...' : 'Dry-run'}
            onPress={() => runDryRun(tab)}
            colors={colors}
            testId={`${prefix}-dryrun-button`}
            disabled={savingKey === `dryrun-${tab}`}
          />
        </View>

        {draft.audience === 'affected_only' && (
          <TextInput
            value={draft.user_ids_text}
            onChangeText={(text) => setNotificationDrafts((prev) => ({ ...prev, [tab]: { ...prev[tab], user_ids_text: text } }))}
            placeholder="Comma-separated user_ids"
            placeholderTextColor={colors.textMuted}
            style={{ borderWidth: 1, borderColor: colors.border, borderRadius: 10, paddingHorizontal: 10, paddingVertical: 9, fontSize: 12, backgroundColor: colors.bgSoft, color: colors.text }}
            data-testid={`${prefix}-audience-userids-input`}
            testID={`${prefix}-audience-userids-input`}
          />
        )}

        {preview && (
          <View style={{ borderWidth: 1, borderColor: `${colors.warning}66`, backgroundColor: `${colors.warning}18`, borderRadius: 10, padding: 10, gap: 6 }} data-testid={`${prefix}-dryrun-preview-card`} testID={`${prefix}-dryrun-preview-card`}>
            <Text style={{ color: colors.warningText, fontSize: 11, fontWeight: '800' }}>DRY-RUN RESULT</Text>
            <Text style={{ color: colors.text, fontSize: 12 }} data-testid={`${prefix}-dryrun-recipient-count`} testID={`${prefix}-dryrun-recipient-count`}>
              Recipients: {Number(preview?.recipient_count || 0).toLocaleString()}
            </Text>
            <Text style={{ color: colors.textMuted, fontSize: 11 }} numberOfLines={2}>{preview?.preview_subject || ''}</Text>
            <TextInput
              value={draft.confirm_phrase}
              onChangeText={(text) => setNotificationDrafts((prev) => ({ ...prev, [tab]: { ...prev[tab], confirm_phrase: text } }))}
              placeholder="Type SEND"
              placeholderTextColor={colors.textMuted}
              style={{ borderWidth: 1, borderColor: colors.border, borderRadius: 10, paddingHorizontal: 10, paddingVertical: 9, fontSize: 12, backgroundColor: colors.bgSoft, color: colors.text }}
              autoCapitalize="characters"
              data-testid={`${prefix}-confirm-input`}
              testID={`${prefix}-confirm-input`}
            />
            <ActionButton
              label={savingKey === `send-${tab}` ? 'Sending...' : 'Send Broadcast'}
              onPress={() => sendBroadcast(tab)}
              colors={colors}
              testId={`${prefix}-send-button`}
              disabled={savingKey === `send-${tab}`}
              danger
            />
          </View>
        )}

        <UnsupportedNote
          title="Notification analytics limitations"
          details="Open rates and click-through rates are not returned by the current legal broadcast APIs. Delivery and failure counts are available."
          colors={colors}
          testId={`${prefix}-notification-unsupported-note`}
        />
      </SectionCard>
    );
  };

  const renderDocumentTimeline = (kind: 'cookies' | 'privacy', page: any | null) => {
    const slug = page?.slug || docDrafts[kind].slug;
    const rows = legalDocAuditRows(slug);
    const prefix = `legal-update-${kind}`;

    return (
      <SectionCard colors={colors} testId={`${prefix}-timeline-card`}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 7 }}>
          <Ionicons name="time" size={16} color={colors.primary} />
          <Text style={{ color: colors.text, fontSize: 14, fontWeight: '800' }}>Version/Audit Timeline</Text>
        </View>
        {rows.length === 0 ? (
          <Text style={{ color: colors.textMuted, fontSize: 11 }} data-testid={`${prefix}-timeline-empty`} testID={`${prefix}-timeline-empty`}>
            No history events found for this document slug in admin audit logs.
          </Text>
        ) : (
          rows.slice(0, 20).map((row: any, idx: number) => (
            <View key={`${row?.event_id || idx}`} style={{ borderTopWidth: idx === 0 ? 0 : 1, borderTopColor: colors.border, paddingTop: idx === 0 ? 0 : 8, gap: 3 }} data-testid={`${prefix}-timeline-row-${idx}`} testID={`${prefix}-timeline-row-${idx}`}>
              <Text style={{ color: colors.text, fontSize: 11, fontWeight: '700' }}>{row?.action || 'event'}</Text>
              <Text style={{ color: colors.textMuted, fontSize: 10 }}>Admin: {row?.user_id || '—'}</Text>
              <Text style={{ color: colors.textMuted, fontSize: 10 }}>At: {formatDateTime(row?.created_at)}</Text>
            </View>
          ))
        )}
        <UnsupportedNote
          title="Diff / rollback constraints"
          details="Current content-page API stores latest document snapshot only; document-level diff and rollback versions are not exposed by backend contract."
          colors={colors}
          testId={`${prefix}-timeline-unsupported-note`}
        />
      </SectionCard>
    );
  };

  const renderLegalPolicyTab = (kind: 'cookies' | 'privacy') => {
    const page = kind === 'cookies' ? cookiesPage : privacyPage;
    const prefix = `legal-update-${kind}`;
    const policyType = kind === 'cookies' ? 'Cookie Policy' : 'Privacy Policy';
    const draft = docDrafts[kind];
    const broadcasts = legalBroadcastRows(policyType);

    return (
      <View style={{ gap: 12 }} data-testid={`${prefix}-tab-root`} testID={`${prefix}-tab-root`}>
        <SectionCard colors={colors} testId={`${prefix}-document-state-card`}>
          <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 10, flexWrap: 'wrap' }}>
            <Text style={{ color: colors.text, fontSize: 16, fontWeight: '900' }} data-testid={`${prefix}-title`} testID={`${prefix}-title`}>{policyType}</Text>
            <Text style={{ color: colors.textMuted, fontSize: 11 }} data-testid={`${prefix}-last-updated`} testID={`${prefix}-last-updated`}>Last updated: {formatDateTime(page?.updated_at)}</Text>
          </View>

          {!page ? (
            <Text style={{ color: colors.textMuted, fontSize: 12 }} data-testid={`${prefix}-empty-state`} testID={`${prefix}-empty-state`}>
              No {policyType} document found in content-page store.
            </Text>
          ) : (
            <>
              <Text style={{ color: colors.textMuted, fontSize: 11 }} data-testid={`${prefix}-active-version`} testID={`${prefix}-active-version`}>
                Active slug: {page?.slug || '—'} • Status: {page?.status || 'unknown'}
              </Text>
              <Text style={{ color: colors.text, fontSize: 12, lineHeight: 18 }} numberOfLines={5} data-testid={`${prefix}-body-preview`} testID={`${prefix}-body-preview`}>
                {page?.body || ''}
              </Text>
            </>
          )}
        </SectionCard>

        <SectionCard colors={colors} testId={`${prefix}-editor-card`}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 7 }}>
            <Ionicons name="create" size={16} color={colors.primary} />
            <Text style={{ color: colors.text, fontSize: 14, fontWeight: '800' }}>Document Management</Text>
          </View>

          <TextInput
            value={draft.title}
            onChangeText={(text) => setDocDrafts((prev) => ({ ...prev, [kind]: { ...prev[kind], title: text } }))}
            placeholder="Document title"
            placeholderTextColor={colors.textMuted}
            style={{ borderWidth: 1, borderColor: colors.border, borderRadius: 10, paddingHorizontal: 10, paddingVertical: 9, fontSize: 12, color: colors.text, backgroundColor: colors.bgSoft }}
            data-testid={`${prefix}-title-input`}
            testID={`${prefix}-title-input`}
          />

          <TextInput
            value={draft.slug}
            onChangeText={(text) => setDocDrafts((prev) => ({ ...prev, [kind]: { ...prev[kind], slug: text } }))}
            placeholder="Document slug"
            placeholderTextColor={colors.textMuted}
            style={{ borderWidth: 1, borderColor: colors.border, borderRadius: 10, paddingHorizontal: 10, paddingVertical: 9, fontSize: 12, color: colors.text, backgroundColor: colors.bgSoft }}
            data-testid={`${prefix}-slug-input`}
            testID={`${prefix}-slug-input`}
          />

          <TextInput
            value={draft.body}
            onChangeText={(text) => setDocDrafts((prev) => ({ ...prev, [kind]: { ...prev[kind], body: text } }))}
            placeholder="Policy body from legal source"
            placeholderTextColor={colors.textMuted}
            multiline
            style={{ borderWidth: 1, borderColor: colors.border, borderRadius: 10, minHeight: 180, textAlignVertical: 'top', paddingHorizontal: 10, paddingVertical: 9, fontSize: 12, color: colors.text, backgroundColor: colors.bgSoft }}
            data-testid={`${prefix}-body-input`}
            testID={`${prefix}-body-input`}
          />

          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
            <ActionButton
              label={`Status: ${draft.status}`}
              onPress={() => setDocDrafts((prev) => ({
                ...prev,
                [kind]: {
                  ...prev[kind],
                  status: prev[kind].status === 'published' ? 'draft' : 'published',
                },
              }))}
              colors={colors}
              testId={`${prefix}-status-toggle`}
            />
            <ActionButton
              label={savingKey === `save-${kind}` ? 'Saving...' : 'Save document'}
              onPress={() => saveContentDocument(kind)}
              colors={colors}
              testId={`${prefix}-save-button`}
              disabled={savingKey === `save-${kind}`}
            />
          </View>

          <UnsupportedNote
            title="Scheduling + rollback status"
            details="Dedicated legal document scheduling, rollback, and approval workflow endpoints are not currently exposed for cookies/privacy content pages."
            colors={colors}
            testId={`${prefix}-editor-unsupported-note`}
          />
        </SectionCard>

        {renderDocumentTimeline(kind, page)}

        {renderNotificationComposer(kind)}

        <SectionCard colors={colors} testId={`${prefix}-broadcast-history-card`}>
          <Text style={{ color: colors.text, fontSize: 14, fontWeight: '800' }} data-testid={`${prefix}-broadcast-history-title`} testID={`${prefix}-broadcast-history-title`}>
            Notification Delivery History
          </Text>
          {broadcasts.length === 0 ? (
            <Text style={{ color: colors.textMuted, fontSize: 11 }} data-testid={`${prefix}-broadcast-history-empty`} testID={`${prefix}-broadcast-history-empty`}>
              No prior {policyType} broadcasts found.
            </Text>
          ) : (
            broadcasts.slice(0, 20).map((row: any, idx: number) => (
              <View key={`${row?.broadcast_id || idx}`} style={{ borderTopWidth: idx === 0 ? 0 : 1, borderTopColor: colors.border, paddingTop: idx === 0 ? 0 : 8 }} data-testid={`${prefix}-broadcast-row-${idx}`} testID={`${prefix}-broadcast-row-${idx}`}>
                <Text style={{ color: colors.text, fontSize: 11, fontWeight: '700' }}>{row?.effective_date || '—'} • {row?.policy_type || '—'}</Text>
                <Text style={{ color: colors.textMuted, fontSize: 10 }}>Delivered: {row?.sent_ok ?? 0} • Failed: {row?.sent_failed ?? 0} • Recipients: {row?.recipient_count ?? 0}</Text>
                <Text style={{ color: colors.textMuted, fontSize: 10 }}>By: {row?.broadcast_by || '—'} at {formatDateTime(row?.sent_at)}</Text>
              </View>
            ))
          )}
        </SectionCard>
      </View>
    );
  };

  const renderTermsTab = () => {
    const broadcasts = legalBroadcastRows('Terms of Service');

    return (
      <View style={{ gap: 12 }} data-testid="legal-update-tos-tab-root" testID="legal-update-tos-tab-root">
        <SectionCard colors={colors} testId="legal-update-tos-overview-card">
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10 }}>
            <View style={{ flex: 1, minWidth: 160 }}>
              <Text style={{ color: colors.textMuted, fontSize: 11, fontWeight: '700' }}>Active Version</Text>
              <Text style={{ color: colors.text, fontSize: 20, fontWeight: '900' }} data-testid="legal-update-tos-active-version" testID="legal-update-tos-active-version">
                {currentTos?.version_number ? `v${currentTos.version_number}` : 'None'}
              </Text>
              <Text style={{ color: colors.textMuted, fontSize: 10 }}>{formatDateTime(currentTos?.published_at)}</Text>
            </View>
            <View style={{ flex: 1, minWidth: 160 }}>
              <Text style={{ color: colors.textMuted, fontSize: 11, fontWeight: '700' }}>Acceptance Rate</Text>
              <Text style={{ color: colors.text, fontSize: 20, fontWeight: '900' }} data-testid="legal-update-tos-acceptance-rate" testID="legal-update-tos-acceptance-rate">
                {tosStats?.acceptance_rate != null ? `${tosStats.acceptance_rate}%` : '--'}
              </Text>
              <Text style={{ color: colors.textMuted, fontSize: 10 }}>Accepted {tosStats?.accepted_count ?? 0} / {tosStats?.total_users ?? 0}</Text>
            </View>
            <View style={{ flex: 1, minWidth: 160 }}>
              <Text style={{ color: colors.textMuted, fontSize: 11, fontWeight: '700' }}>Versions in Store</Text>
              <Text style={{ color: colors.text, fontSize: 20, fontWeight: '900' }} data-testid="legal-update-tos-version-count" testID="legal-update-tos-version-count">
                {tosVersions.length}
              </Text>
              <Text style={{ color: colors.textMuted, fontSize: 10 }}>Draft + Published + Archived</Text>
            </View>
          </View>
        </SectionCard>

        <SectionCard colors={colors} testId="legal-update-tos-management-card">
          <Text style={{ color: colors.text, fontSize: 14, fontWeight: '800' }} data-testid="legal-update-tos-management-title" testID="legal-update-tos-management-title">
            Terms Version Control Management
          </Text>
          <Text style={{ color: colors.textMuted, fontSize: 11 }} data-testid="legal-update-tos-management-subtitle" testID="legal-update-tos-management-subtitle">
            This panel uses real `/api/admin/tos/*` endpoints for draft, publish, version timeline, and acceptance tracking.
          </Text>
          <View style={{ minHeight: 520 }} data-testid="legal-update-tos-management-panel-wrapper" testID="legal-update-tos-management-panel-wrapper">
            <TosManagementPanel />
          </View>
        </SectionCard>

        {renderNotificationComposer('tos')}

        <SectionCard colors={colors} testId="legal-update-tos-broadcast-history-card">
          <Text style={{ color: colors.text, fontSize: 14, fontWeight: '800' }} data-testid="legal-update-tos-broadcast-history-title" testID="legal-update-tos-broadcast-history-title">
            Terms Notification History
          </Text>
          {broadcasts.length === 0 ? (
            <Text style={{ color: colors.textMuted, fontSize: 11 }} data-testid="legal-update-tos-broadcast-empty" testID="legal-update-tos-broadcast-empty">
              No Terms of Service broadcasts found.
            </Text>
          ) : (
            broadcasts.slice(0, 20).map((row: any, idx: number) => (
              <View key={`${row?.broadcast_id || idx}`} style={{ borderTopWidth: idx === 0 ? 0 : 1, borderTopColor: colors.border, paddingTop: idx === 0 ? 0 : 8 }} data-testid={`legal-update-tos-broadcast-row-${idx}`} testID={`legal-update-tos-broadcast-row-${idx}`}>
                <Text style={{ color: colors.text, fontSize: 11, fontWeight: '700' }}>{row?.effective_date || '—'} • {row?.policy_type || '—'}</Text>
                <Text style={{ color: colors.textMuted, fontSize: 10 }}>Delivered: {row?.sent_ok ?? 0} • Failed: {row?.sent_failed ?? 0}</Text>
              </View>
            ))
          )}
        </SectionCard>

        <UnsupportedNote
          title="Scheduling/approval gaps"
          details="Dedicated ToS scheduling endpoint (future publish date), approval-chain workflow, and open/click analytics are not exposed by current ToS contracts."
          colors={colors}
          testId="legal-update-tos-unsupported-note"
        />
      </View>
    );
  };

  if (loading && !lastUpdated) {
    return (
      <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center', gap: 10 }} data-testid="legal-update-loading" testID="legal-update-loading">
        <ActivityIndicator size="large" color={colors.primary} />
        <Text style={{ color: colors.textMuted, fontSize: 12 }}>{tx('legalUpdate.loading', 'Loading legal governance center...')}</Text>
      </View>
    );
  }

  return (
    <View style={{ flex: 1 }} data-testid="legal-update-workspace" testID="legal-update-workspace">
      <View style={{ paddingHorizontal: isMobile ? 12 : 20, paddingTop: 16, paddingBottom: 8, gap: 10 }} data-testid="legal-update-header" testID="legal-update-header">
        <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 10 }}>
          <View style={{ gap: 4 }}>
            <Text style={{ color: colors.text, fontSize: isMobile ? 24 : 30, fontWeight: '900', letterSpacing: -0.6 }} data-testid="legal-update-title" testID="legal-update-title">
              LEGAL UPDATE
            </Text>
            <Text style={{ color: colors.textMuted, fontSize: 12 }} data-testid="legal-update-subtitle" testID="legal-update-subtitle">
              Global legal governance center driven by live platform legal data endpoints.
            </Text>
          </View>
          <ActionButton
            label={refreshing ? 'Refreshing...' : 'Refresh'}
            onPress={() => loadBundle('refresh')}
            colors={colors}
            testId="legal-update-refresh-btn"
            disabled={refreshing}
          />
        </View>
        <Text style={{ color: colors.textMuted, fontSize: 11 }} data-testid="legal-update-last-sync" testID="legal-update-last-sync">
          Last sync: {formatDateTime(lastUpdated)} • Auto-refresh: 60s polling
        </Text>
      </View>

      <ScrollView
        style={{ flex: 1 }}
        contentContainerStyle={{ paddingHorizontal: isMobile ? 12 : 20, paddingBottom: 30, gap: 12 }}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => loadBundle('refresh')} tintColor={colors.primary} />}
        data-testid="legal-update-scroll-root"
        testID="legal-update-scroll-root"
      >
        {statusMessage && (
          <View
            style={{
              borderWidth: 1,
              borderColor: statusMessage.type === 'error' ? `${colors.error}66` : statusMessage.type === 'success' ? `${colors.successText}66` : `${colors.primary}66`,
              backgroundColor: statusMessage.type === 'error' ? `${colors.error}14` : statusMessage.type === 'success' ? `${colors.successText}10` : `${colors.primary}10`,
              borderRadius: 10,
              padding: 10,
            }}
            data-testid="legal-update-status-message"
            testID="legal-update-status-message"
          >
            <Text style={{ color: statusMessage.type === 'error' ? colors.error : statusMessage.type === 'success' ? colors.successText : colors.text, fontSize: 11, fontWeight: '700' }}>
              {statusMessage.message}
            </Text>
          </View>
        )}

        {!!error && (
          <View style={{ borderRadius: 10, borderWidth: 1, borderColor: `${colors.error}55`, backgroundColor: `${colors.error}12`, padding: 10 }} data-testid="legal-update-error-banner" testID="legal-update-error-banner">
            <Text style={{ color: colors.error, fontSize: 12 }}>{error}</Text>
          </View>
        )}

        <SectionCard colors={colors} testId="legal-update-coverage-card">
          <Text style={{ color: colors.text, fontSize: 14, fontWeight: '800' }} data-testid="legal-update-coverage-title" testID="legal-update-coverage-title">Data Coverage Snapshot</Text>
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10 }}>
            <Text style={{ color: legalCoverageStatus.cookieAvailable ? colors.successText : colors.warningText, fontSize: 11 }} data-testid="legal-update-coverage-cookies" testID="legal-update-coverage-cookies">Cookies source: {legalCoverageStatus.cookieAvailable ? 'available' : 'not found'}</Text>
            <Text style={{ color: legalCoverageStatus.privacyAvailable ? colors.successText : colors.warningText, fontSize: 11 }} data-testid="legal-update-coverage-privacy" testID="legal-update-coverage-privacy">Privacy source: {legalCoverageStatus.privacyAvailable ? 'available' : 'not found'}</Text>
            <Text style={{ color: legalCoverageStatus.tosAvailable ? colors.successText : colors.warningText, fontSize: 11 }} data-testid="legal-update-coverage-tos" testID="legal-update-coverage-tos">ToS source: {legalCoverageStatus.tosAvailable ? 'available' : 'not found'}</Text>
          </View>
        </SectionCard>

        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }} data-testid="legal-update-tab-switcher" testID="legal-update-tab-switcher">
          <TabButton active={activeTab === 'cookies'} label="COOKIES" onPress={() => setActiveTab('cookies')} colors={colors} testId="legal-update-tab-cookies" />
          <TabButton active={activeTab === 'privacy'} label="PRIVACY POLICY" onPress={() => setActiveTab('privacy')} colors={colors} testId="legal-update-tab-privacy" />
          <TabButton active={activeTab === 'tos'} label="TERMS OF SERVICE" onPress={() => setActiveTab('tos')} colors={colors} testId="legal-update-tab-tos" />
        </View>

        {activeTab === 'cookies' && renderLegalPolicyTab('cookies')}
        {activeTab === 'privacy' && renderLegalPolicyTab('privacy')}
        {activeTab === 'tos' && renderTermsTab()}
      </ScrollView>
    </View>
  );
}
