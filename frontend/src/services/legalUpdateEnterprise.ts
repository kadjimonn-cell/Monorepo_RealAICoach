import api from './api';

export const fetchLegalUpdateBundle = async () => {
  const [contentPages, accessLogs, legalBroadcasts] = await Promise.allSettled([
    api.get('/admin/content/pages', { silentLoading: true }),
    api.get('/admin/access-logs', { silentLoading: true }),
    api.get('/admin/legal-notice/broadcasts', { silentLoading: true }),
  ]);

  const [tosVersions, tosStats, currentTos] = await Promise.allSettled([
    api.get('/admin/tos/versions', { silentLoading: true }),
    api.get('/admin/tos/stats', { silentLoading: true }),
    api.get('/tos/current', { silentLoading: true }),
  ]);

  return {
    contentPages,
    accessLogs,
    legalBroadcasts,
    tosVersions,
    tosStats,
    currentTos,
  };
};

export const upsertLegalContentPage = async (payload: {
  title: string;
  slug: string;
  status: string;
  body: string;
}) => {
  const res = await api.post('/admin/content/pages', payload);
  return res.data;
};

export const runLegalNoticeDryRun = async (payload: {
  policy_type: string;
  effective_date: string;
  summary_of_changes: string;
  review_url?: string;
  audience: 'all_users' | 'affected_only';
  user_ids?: string[];
}) => {
  const res = await api.post('/admin/legal-notice/broadcast', {
    ...payload,
    dry_run: true,
  });
  return res.data;
};

export const sendLegalNoticeBroadcast = async (payload: {
  policy_type: string;
  effective_date: string;
  summary_of_changes: string;
  review_url?: string;
  audience: 'all_users' | 'affected_only';
  user_ids?: string[];
  confirm_phrase: 'SEND';
}) => {
  const res = await api.post('/admin/legal-notice/broadcast', {
    ...payload,
    dry_run: false,
  });
  return res.data;
};

export const getAiLegalSuggestion = async (payload: {
  email?: string;
  subject: string;
  message: string;
  intent: 'draft' | 'improve_tone' | 'shorten' | 'expand';
  lang?: string;
}) => {
  const res = await api.post('/support/email/assist', {
    name: 'Legal Admin',
    email: payload.email || 'admin@realaicoach.app',
    subject: payload.subject,
    message: payload.message,
    category: 'policy',
    priority: 'high',
    intent: payload.intent,
    lang: payload.lang || 'en',
  }, { silentLoading: true });
  return res.data;
};

export const logLegalSuggestionFeedback = async (payload: {
  schedule_id?: string;
  policy_type: 'Terms of Service' | 'Privacy Policy' | 'Cookie Policy';
  intent: 'draft' | 'improve_tone' | 'shorten' | 'expand';
  style_preset?: 'formal' | 'regulatory' | 'plain-language';
  decision: 'accepted' | 'rejected';
  source?: string;
  confidence?: number;
  summary_length?: number;
  note?: string;
}) => {
  const res = await api.post('/admin/legal-notice/suggestion-feedback', payload, { silentLoading: true });
  return res.data;
};

export const getLegalSuggestionAnalytics = async (days = 30) => {
  const res = await api.get(`/admin/legal-notice/suggestion-analytics?days=${encodeURIComponent(days)}`, { silentLoading: true });
  return res.data;
};
