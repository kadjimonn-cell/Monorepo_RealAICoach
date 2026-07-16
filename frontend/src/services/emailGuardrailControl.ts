import api from './api';

export const fetchEmailGuardrailOverview = async (windowHours = 24) => {
  const res = await api.get(`/admin/email-health/guardrail/overview?window_hours=${encodeURIComponent(windowHours)}`, { silentLoading: true });
  return res.data;
};

export const fetchEmailGuardrailEvents = async (params: {
  hours?: number;
  template_key?: string;
  recipient?: string;
  limit?: number;
}) => {
  const q = new URLSearchParams();
  q.set('hours', String(params.hours ?? 72));
  q.set('limit', String(params.limit ?? 200));
  if (params.template_key) q.set('template_key', params.template_key);
  if (params.recipient) q.set('recipient', params.recipient);
  const res = await api.get(`/admin/email-health/guardrail/events?${q.toString()}`, { silentLoading: true });
  return res.data;
};

export const fetchEmailGuardrailBlocklist = async (params?: { active_only?: boolean; search?: string; limit?: number }) => {
  const q = new URLSearchParams();
  q.set('active_only', String(params?.active_only ?? true));
  q.set('limit', String(params?.limit ?? 200));
  if (params?.search) q.set('search', params.search);
  const res = await api.get(`/admin/email-health/guardrail/blocklist?${q.toString()}`, { silentLoading: true });
  return res.data;
};

export const upsertEmailGuardrailBlocklist = async (payload: {
  recipient_email: string;
  active: boolean;
  apply_to_canonical?: boolean;
  reason?: string;
}) => {
  const res = await api.put('/admin/email-health/guardrail/blocklist', payload);
  return res.data;
};

export const unblockEmailGuardrailRecipient = async (recipientEmail: string) => {
  const res = await api.post(`/admin/email-health/guardrail/blocklist/${encodeURIComponent(recipientEmail)}/unblock`, {});
  return res.data;
};

export const fetchEmailGuardrailTemplatePolicies = async (activeOnly = false) => {
  const res = await api.get(`/admin/email-health/guardrail/template-policies?active_only=${String(activeOnly)}`, { silentLoading: true });
  return res.data;
};

export const upsertEmailGuardrailTemplatePolicy = async (templateKey: string, payload: { max_per_fingerprint: number; active: boolean; note?: string }) => {
  const res = await api.put(`/admin/email-health/guardrail/template-policies/${encodeURIComponent(templateKey)}`, payload);
  return res.data;
};

export const deleteEmailGuardrailTemplatePolicy = async (templateKey: string) => {
  const res = await api.delete(`/admin/email-health/guardrail/template-policies/${encodeURIComponent(templateKey)}`);
  return res.data;
};
