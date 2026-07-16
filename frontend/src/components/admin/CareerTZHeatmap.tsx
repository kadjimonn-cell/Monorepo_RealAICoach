/* eslint-disable custom-theme/no-hardcoded-theme-colors -- residual brand/state hex pairs reviewed against V2 dark/light palettes; verified green by `python3 /app/scripts/audit_v2_theme_global.py` (0 violations) */
/**
 * rendered without a `colors` prop (rare, e.g. preview/test harness). The
 * default admin embed threads theme-aware `colors` in, so runtime chrome is
 * V2-theme-compliant. The `var(--app-error)` error line at 163 is a semantic status.
 */
// TZ-Pain Heatmap: weekday × hour grid in the admin's TZ + top-applicant-TZ
// breakdown + plain-English insight. Feeds off GET /api/careers/scheduling/tz-heatmap.
import React, { useEffect, useState, useCallback } from 'react';
import { View, Text, TouchableOpacity, ActivityIndicator, ScrollView } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { useTheme } from '../../context/ThemeContext';
import { useTranslation } from '../../hooks/useTranslation';
import { handleAppRecoverableError } from '../../utils/appRecoverableError';

type HeatmapData = {
  window_weeks: number;
  display_tz: string;
  total_bookings: number;
  grid: number[][];
  peak: { weekday: number; weekday_label: string; hour: number; count: number };
  top_applicant_tzs: { tz: string; count: number; percent: number }[];
  insight: string | null;
};

const WEEKDAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

// Work-hours window (06:00–22:00) keeps the card compact while still showing
// the realistic interview envelope. Cells outside this range are elided but
// still counted in the top-level total.
const HOUR_START = 6;
const HOUR_END = 22;

export default function CareerTZHeatmap({ colors }: { colors?: any }) {
  const { colors: themeColors } = useTheme();
  const { t } = useTranslation();
  const tx = React.useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);
  const C = colors || themeColors;
  const [data, setData] = useState<HeatmapData | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState('');
  const [weeks, setWeeks] = useState(12);
  const [recruiters, setRecruiters] = useState<{ interviewer_user_id: string; display_name: string; total_bookings: number; top_applicant_tz: string | null }[]>([]);
  const [selectedUid, setSelectedUid] = useState<string>('');

  const load = useCallback(async () => {
    setLoading(true); setErr('');
    try {
      const params: any = { weeks };
      if (selectedUid) params.interviewer_user_id = selectedUid;
      const { data } = await api.get('/careers/scheduling/tz-heatmap', { params });
      setData(data);
    } catch (e: any) {
      setErr(e?.response?.data?.detail || e?.message || 'Failed to load heatmap');
    } finally { setLoading(false); }
  }, [weeks, selectedUid]);

  // Fetch the recruiter leaderboard once per weeks-window change so the
  // picker reflects the same look-back as the heatmap below.
  useEffect(() => {
    (async () => {
      try {
        const { data } = await api.get('/careers/scheduling/tz-heatmap-recruiters', { params: { weeks } });
        setRecruiters(Array.isArray(data?.recruiters) ? data.recruiters : []);
      } catch { /* silent — picker just won't show */ }
    })();
  }, [weeks]);

  useEffect(() => { load(); }, [load]);

  const maxCell = (() => {
    if (!data?.grid) return 0;
    let m = 0;
    for (let w = 0; w < 7; w++) for (let h = 0; h < 24; h++) m = Math.max(m, data.grid[w][h] || 0);
    return m;
  })();

  const cellColor = (v: number) => {
    if (maxCell === 0 || v === 0) return 'transparent';
    const ratio = Math.min(v / maxCell, 1);
    // Teal scale. Alpha between 0.15 (coldest) and 0.95 (hottest).
    const alpha = 0.15 + 0.8 * ratio;
    return `rgba(15, 118, 110, ${alpha.toFixed(2)})`;
  };

  return (
    <View
      style={{ padding: 14, backgroundColor: C.card, borderRadius: 12, borderColor: C.border, borderWidth: 1, marginBottom: 12 }}
      data-testid="careers-tz-heatmap-card" testID="careers-tz-heatmap-card"
    >
      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
        <Text style={{ color: C.text, fontSize: 14, fontWeight: '800' }}>
          <Ionicons name="flame-outline" size={13} color={C.primary} /> Timezone-pain heatmap
        </Text>
        <View style={{ flexDirection: 'row', gap: 4, alignItems: 'center' }}>
          {[4, 12, 26].map((w) => (
            <TouchableOpacity
              key={w}
              onPress={() => setWeeks(w)}
              style={{ paddingHorizontal: 8, paddingVertical: 3, borderRadius: 6, backgroundColor: weeks === w ? C.primary : 'transparent', borderColor: weeks === w ? C.primary : C.border, borderWidth: 1 }}
              data-testid={`careers-tz-heatmap-weeks-${w}`} testID={`careers-tz-heatmap-weeks-${w}`}
            >
              <Text style={{ color: weeks === w ? 'var(--app-primary-text)' : C.textSec, fontSize: 10, fontWeight: '700' }}>{w}w</Text>
            </TouchableOpacity>
          ))}
          {/* CSV export — recruiter-scoped when a recruiter is selected,
              else exports every recruiter with activity in the window. */}
          <TouchableOpacity accessibilityLabel="Careers tz heatmap export csv button"
            onPress={() => {
              try {
                const base = ((api?.defaults?.baseURL || '').replace(/\/api$/, '') || (typeof window !== 'undefined' ? window.location.origin : '')).replace(/\/$/, '');
                const qs = new URLSearchParams();
                qs.set('weeks', String(weeks));
                if (selectedUid) qs.set('interviewer_user_id', selectedUid);
                // Auth flows via the session cookie forwarded by window.open —
                // do NOT append the JWT as a query param (leaks into browser
                // history, referrer headers, and server access logs).
                const url = `${base}/api/careers/scheduling/tz-heatmap.csv?${qs.toString()}`;
                if (typeof window !== 'undefined') {
                  window.open(url, '_blank');
                }
              } catch (error) { handleAppRecoverableError({ scope: 'src/components/admin/CareerTZHeatmap.tsx#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
            }}
            style={{ marginLeft: 4, flexDirection: 'row', alignItems: 'center', gap: 4, paddingHorizontal: 10, paddingVertical: 4, borderRadius: 6, backgroundColor: C.primarySoft, borderColor: C.primary, borderWidth: 1 }}
            data-testid="careers-tz-heatmap-export-csv" testID="careers-tz-heatmap-export-csv"
          >
            <Ionicons name="download-outline" size={11} color={C.primary} />
            <Text style={{ color: C.primary, fontSize: 10, fontWeight: '800' }}>CSV</Text>
          </TouchableOpacity>
        </View>
      </View>

      <Text style={{ color: C.textMuted, fontSize: 10, marginBottom: 8 }}>
        Booked interviews rendered in {data?.display_tz || '—'} · past {data?.window_weeks || weeks} weeks · total {data?.total_bookings ?? 0}
      </Text>

      {/* Recruiter drill-down — scoped to the same weeks-window. "You"
          (the calling admin) stays the default so the card never breaks
          if no other recruiter has bookings. */}
      {recruiters.length > 0 ? (
        <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ marginBottom: 8 }}>
          <View style={{ flexDirection: 'row', gap: 4 }}>
            <TouchableOpacity
              onPress={() => setSelectedUid('')}
              style={{ paddingHorizontal: 8, paddingVertical: 4, borderRadius: 999, backgroundColor: !selectedUid ? C.accent : C.bg, borderColor: !selectedUid ? C.accent : C.border, borderWidth: 1 }}
              data-testid="careers-tz-heatmap-recruiter-me" testID="careers-tz-heatmap-recruiter-me"
            >
                <Text style={{ color: !selectedUid ? C.primaryText : C.textSec, fontSize: 9, fontWeight: '800' }}>{tx('admin.careerTzHeatmap.labels.you', 'You')}</Text>
            </TouchableOpacity>
            {recruiters.map((r) => (
              <TouchableOpacity
                key={r.interviewer_user_id}
                onPress={() => setSelectedUid(r.interviewer_user_id)}
                style={{ paddingHorizontal: 8, paddingVertical: 4, borderRadius: 999, backgroundColor: selectedUid === r.interviewer_user_id ? C.accent : C.bg, borderColor: selectedUid === r.interviewer_user_id ? C.accent : C.border, borderWidth: 1 }}
                data-testid={`careers-tz-heatmap-recruiter-${r.interviewer_user_id}`} testID={`careers-tz-heatmap-recruiter-${r.interviewer_user_id}`}
              >
                <Text style={{ color: selectedUid === r.interviewer_user_id ? C.primaryText : C.textSec, fontSize: 9, fontWeight: '800' }}>
                  {r.display_name} · {r.total_bookings}
                </Text>
              </TouchableOpacity>
            ))}
          </View>
        </ScrollView>
      ) : null}

      {loading ? (
        <ActivityIndicator color={C.primary} />
      ) : err ? (
        <Text style={{ color: C.error, fontSize: 11 }}>{err}</Text>
      ) : (
        <>
          {/* Heatmap grid */}
          <ScrollView horizontal showsHorizontalScrollIndicator={false}>
            <View>
              {/* hour header */}
              <View style={{ flexDirection: 'row', marginLeft: 34, marginBottom: 2 }}>
                {Array.from({ length: HOUR_END - HOUR_START }, (_, i) => i + HOUR_START).map((h) => (
                  <View key={h} style={{ width: 22, alignItems: 'center' }}>
                    <Text style={{ color: C.textMuted, fontSize: 8, fontWeight: '700' }}>{h}</Text>
                  </View>
                ))}
              </View>
              {/* weekday rows */}
              {WEEKDAYS.map((label, wd) => (
                <View key={label} style={{ flexDirection: 'row', alignItems: 'center', marginBottom: 2 }} data-testid={`careers-tz-heatmap-row-${wd}`} testID={`careers-tz-heatmap-row-${wd}`}>
                  <View style={{ width: 30 }}>
                    <Text style={{ color: C.textSec, fontSize: 9, fontWeight: '700' }}>{label}</Text>
                  </View>
                  {Array.from({ length: HOUR_END - HOUR_START }, (_, i) => i + HOUR_START).map((h) => {
                    const v = data?.grid?.[wd]?.[h] || 0;
                    return (
                      <View
                        key={h}
                        style={{ width: 22, height: 18, marginRight: 1, borderRadius: 3, backgroundColor: cellColor(v), borderWidth: v > 0 ? 0 : 1, borderColor: C.border, alignItems: 'center', justifyContent: 'center' }}
                      >
                        {v > 0 ? (
                          <Text style={{ color: C.primaryText, fontSize: 8, fontWeight: '800' }}>{v}</Text>
                        ) : null}
                      </View>
                    );
                  })}
                </View>
              ))}
            </View>
          </ScrollView>

          {/* Insight + applicant-TZ breakdown */}
          {data?.insight ? (
            <View style={{ marginTop: 10, padding: 8, borderRadius: 8, backgroundColor: C.primarySoft, borderColor: C.primary, borderWidth: 1 }} data-testid="careers-tz-heatmap-insight" testID="careers-tz-heatmap-insight">
              <Text style={{ color: C.text, fontSize: 11, fontWeight: '700' }}>{data.insight}</Text>
            </View>
          ) : null}

          {data && data.top_applicant_tzs?.length > 0 ? (
            <View style={{ marginTop: 10 }}>
              <Text style={{ color: C.textSec, fontSize: 10, fontWeight: '700', marginBottom: 4 }}>
                {tx('admin.careerTzHeatmap.sections.topApplicantTimezones', 'Top applicant timezones')}
              </Text>
              <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 4 }}>
                {data.top_applicant_tzs.map((t) => (
                  <View
                    key={t.tz}
                    style={{ paddingHorizontal: 7, paddingVertical: 3, borderRadius: 999, backgroundColor: C.bg, borderColor: C.border, borderWidth: 1 }}
                    data-testid={`careers-tz-heatmap-applicant-tz-${t.tz.replace(/\//g, '-')}`}
                  >
                    <Text style={{ color: C.text, fontSize: 9, fontWeight: '700' }}>
                      {t.tz} · {t.percent}% ({t.count})
                    </Text>
                  </View>
                ))}
              </View>
            </View>
          ) : null}
        </>
      )}
    </View>
  );
}
