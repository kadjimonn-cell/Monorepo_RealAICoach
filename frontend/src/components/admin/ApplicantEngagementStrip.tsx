// Admin-side "Engagement" strip + in-panel iframe preview of the public
// Application Tracker. Shown inside the applicant detail modal.
//
// Backend: GET /api/admin/careers/applications/{id}/engagement
//
// (blue = sent, green = delivered, purple = clicked, amber = delayed,
// red = bounced/complained). These are constant across themes by design;
// structural chrome uses `AC.*` from useAdminTheme().
import React, { useCallback, useEffect, useState } from 'react';
import { View, Text, TouchableOpacity, ActivityIndicator, Platform } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { useAdminTheme } from '../../hooks/useAdminTheme';
import { useTheme } from '../../context/ThemeContext';
import { useTranslation } from '../../hooks/useTranslation';

type EventDoc = {
  event_type: string;
  template?: string | null;
  email_id?: string | null;
  received_at?: string;
  subject?: string | null;
};

type Engagement = {
  application_id: string;
  events: EventDoc[];
  counts: Record<string, number>;
  last_event_at: string | null;
  total_events: number;
};

function fmtRelative(iso?: string | null): string {
  if (!iso) return '';
  try {
    const diffMs = Date.now() - new Date(iso).getTime();
    const s = Math.max(0, Math.floor(diffMs / 1000));
    if (s < 60) return `${s}s ago`;
    if (s < 3600) return `${Math.floor(s / 60)}m ago`;
    if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
    return `${Math.floor(s / 86400)}d ago`;
  } catch {
    return '';
  }
}

export default function ApplicantEngagementStrip({ applicationId }: { applicationId: string }) {
  const { colors } = useTheme();
  const { t } = useTranslation();
  const tx = useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);

  // @autofix-moved: was module-level const EVENT_ICON
  const EVENT_ICON: Record<string, { icon: any; color: string; label: string }> = {
    sent: { icon: 'send', color: colors.info, label: 'Sent' },
    delivered: { icon: 'checkmark-done', color: colors.success, label: 'Delivered' },
    opened: { icon: 'mail-open', color: colors.primary, label: 'Opened' },
    clicked: { icon: 'link', color: colors.purple, label: 'Clicked' },
    delayed: { icon: 'time', color: colors.warning, label: 'Delayed' },
    bounced: { icon: 'alert-circle', color: colors.error, label: 'Bounced' },
    complained: { icon: 'warning', color: colors.error, label: 'Complained' },
    withdrawn: { icon: 'close-circle', color: colors.textMuted, label: 'Withdrew' },
  };
  const AC = useAdminTheme();
  const [data, setData] = useState<Engagement | null>(null);
  const [loading, setLoading] = useState(true);
  const [showPreview, setShowPreview] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await api.get(`/admin/careers/applications/${applicationId}/engagement`);
      setData(r.data as Engagement);
    } catch (_e: any) {
      setData(null);
    }
    setLoading(false);
  }, [applicationId]);

  useEffect(() => { load(); }, [load]);

  const trackerUrl = `${typeof window !== 'undefined' && window.location?.origin ? window.location.origin : ''}/careers/track/${applicationId}`;

  return (
    <View
      style={{ backgroundColor: AC.bgAlt, borderRadius: 10, padding: 14, borderWidth: 1, borderColor: AC.border, marginBottom: 20 }}
      data-testid="applicant-engagement-strip"
      testID="applicant-engagement-strip"
    >
      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
        <Text style={{ color: AC.textDim, fontSize: 10, fontWeight: '700', letterSpacing: 0.5 }}>{tx('admin.applicantEngagementStrip.header.label', 'ENGAGEMENT')}</Text>
        <TouchableOpacity
          onPress={() => setShowPreview((v) => !v)}
          style={{ flexDirection: 'row', alignItems: 'center', gap: 4, paddingHorizontal: 8, paddingVertical: 4, borderRadius: 12, borderWidth: 1, borderColor: AC.border }}
          data-testid="toggle-tracker-preview"
          testID="toggle-tracker-preview"
        >
          <Ionicons name={showPreview ? 'eye-off' : 'eye'} size={11} color={AC.textSec} />
          <Text style={{ color: AC.textSec, fontSize: 10, fontWeight: '700' }}>
            {showPreview ? 'Hide candidate view' : 'Preview candidate view'}
          </Text>
        </TouchableOpacity>
      </View>

      {loading ? (
        <ActivityIndicator size="small" color={AC.primary} />
      ) : !data || data.total_events === 0 ? (
        <Text style={{ color: AC.textDim, fontSize: 12 }}>{tx('admin.applicantEngagementStrip.states.empty', 'No tracker events yet — the candidate hasn\'t opened their email or viewed the tracker page.')}</Text>
      ) : (
        <>
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }} data-testid="engagement-counts" testID="engagement-counts">
            {Object.entries(data.counts).map(([type, n]) => {
              const meta = EVENT_ICON[type] || { icon: 'ellipse', color: AC.textSec, label: type };
              return (
                <View
                  key={type}
                  style={{ flexDirection: 'row', alignItems: 'center', gap: 5, backgroundColor: `${meta.color}15`, borderWidth: 1, borderColor: meta.color, paddingHorizontal: 9, paddingVertical: 4, borderRadius: 14 }}
                >
                  <Ionicons name={meta.icon} size={11} color={meta.color} />
                  <Text style={{ color: meta.color, fontSize: 11, fontWeight: '700' }}>
                    {meta.label}{n > 1 ? ` ×${n}` : ''}
                  </Text>
                </View>
              );
            })}
          </View>
          {data.last_event_at ? (
            <Text style={{ color: AC.textDim, fontSize: 11, marginTop: 10 }}>
              Last seen {fmtRelative(data.last_event_at)}
            </Text>
          ) : null}
        </>
      )}

      {showPreview && Platform.OS === 'web' ? (
        <View
          style={{ marginTop: 12, borderWidth: 1, borderColor: AC.border, borderRadius: 10, overflow: 'hidden', backgroundColor: AC.bg }}
          data-testid="tracker-preview-iframe-wrap"
          testID="tracker-preview-iframe-wrap"
        >
          <iframe
            src={trackerUrl}
            style={{ width: '100%', height: 520, border: 0, display: 'block' }}
            title="Candidate tracker preview"
            data-testid="tracker-preview-iframe"
          />
        </View>
      ) : null}
    </View>
  );
}
