import api from './api';

export const trackTabAliasHit = async (payload: {
  console: 'executive' | 'operations';
  source_tab_id: string;
  canonical_tab_id: string;
  context?: string;
}) => {
  const res = await api.post('/admin/tab-alias-telemetry/hit', payload, { silentLoading: true });
  return res.data;
};

export const fetchTabAliasTelemetrySummary = async (days = 30) => {
  const res = await api.get(`/admin/tab-alias-telemetry/summary?days=${encodeURIComponent(days)}`, { silentLoading: true });
  return res.data;
};
