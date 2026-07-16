import { useTranslation } from '../../hooks/useTranslation';
import React, { useEffect, useState, useCallback, useMemo } from 'react';
import { View, Text, TouchableOpacity, ActivityIndicator, ScrollView, useWindowDimensions } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { handleAppRecoverableError } from '../../utils/appRecoverableError';

const tx = (_key: string, fallback: string) => fallback;

const C = {
  bg: 'var(--app-bg)' as any,
  bgSoft: 'var(--app-surface)' as any,
  card: 'var(--app-card-bg)' as any,
  border: 'var(--app-border)' as any,
  text: 'var(--app-text)' as any,
  textSec: 'var(--app-text-sec)' as any,
  textMuted: 'var(--app-text-muted)' as any,
  primary: 'var(--app-primary)' as any,
  primaryText: 'var(--app-primary-text)' as any,
  primarySoft: 'var(--app-primary-soft)',
  success: 'var(--app-success)', successSoft: 'var(--app-success-soft)',
  warning: 'var(--app-warning)', warningSoft: 'var(--app-warning-soft)',
  error: 'var(--app-error)', errorSoft: 'var(--app-error-soft)',
  cyan: 'var(--app-primary)' as any, cyanSoft: 'var(--app-primary-soft)',
};

type Interview = {
  application_id: string;
  full_name: string;
  email: string;
  position: string;
  date: string;
  time: string;
  type: string;
  notes?: string;
  video_url?: string;
  room_id?: string;
  candidate_response?: string;
  status?: string;
};

const RESPONSE_COLOR: Record<string, string> = {
  accepted: C.success,
  reschedule_requested: C.warning,
  pending: C.textSec,
  declined: C.error,
};

const TYPE_ICON: Record<string, any> = {
  video: 'videocam',
  'video-call': 'videocam',
  phone: 'call',
  onsite: 'business',
};

function parseDateLocal(iso: string): Date | null {
  if (!iso) return null;
  const parts = iso.split('-').map((x) => parseInt(x, 10));
  if (parts.length !== 3 || parts.some(isNaN)) return null;
  return new Date(parts[0], parts[1] - 1, parts[2]);
}

function fmtShortDate(iso: string): string {
  const d = parseDateLocal(iso);
  if (!d) return iso;
  return d.toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' });
}

export default function UpcomingInterviewsWidget({ onOpenApplication }: { onOpenApplication?: (appId: string) => void }) {
  const { width } = useWindowDimensions();
  const isWide = width >= 900;

  const [loading, setLoading] = useState(true);
  const [rows, setRows] = useState<Interview[]>([]);
  const [err, setErr] = useState('');
  const [selectedDate, setSelectedDate] = useState<string>('');
  const [cursor, setCursor] = useState<Date>(() => {
    const d = new Date();
    return new Date(d.getFullYear(), d.getMonth(), 1);
  });
  const [collapsed, setCollapsed] = useState(false);
  const [sending, setSending] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [sendResult, setSendResult] = useState<{ sent: number; skipped: number; total: number } | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setErr('');
    try {
      const r = await api.get('/careers/interviews/upcoming?days=60');
      setRows((r.data?.items as Interview[]) || []);
    } catch (e: any) {
      setErr(e?.response?.data?.detail || e?.message || 'Failed to load interviews');
    }
    setLoading(false);
  }, []);

  const acceptedCount = useMemo(
    () => rows.filter((r) => (r.candidate_response || '').toLowerCase() === 'accepted').length,
    [rows],
  );

  const bulkSendIcs = useCallback(async () => {
    setSending(true);
    setErr('');
    setSendResult(null);
    try {
      const r = await api.post('/careers/interviews/bulk-send-ics', { days: 60, only_accepted: true });
      const d = r.data || {};
      setSendResult({ sent: d.sent || 0, skipped: d.skipped || 0, total: d.total_attempted || 0 });
      setConfirmOpen(false);
      load();
    } catch (e: any) {
      setErr(e?.response?.data?.detail || e?.message || 'Failed to send calendar invites');
    }
    setSending(false);
  }, [load]);

  useEffect(() => { load(); }, [load]);

  const byDate = useMemo(() => {
    const m: Record<string, Interview[]> = {};
    rows.forEach((r) => {
      if (!r.date) return;
      (m[r.date] ||= []).push(r);
    });
    return m;
  }, [rows]);

  const cells = useMemo(() => {
    // 6-week grid starting from Sunday of cursor month
    const start = new Date(cursor.getFullYear(), cursor.getMonth(), 1);
    const dow = start.getDay();
    const gridStart = new Date(start); gridStart.setDate(1 - dow);
    const out: { iso: string; date: Date; inMonth: boolean }[] = [];
    for (let i = 0; i < 42; i++) {
      const d = new Date(gridStart); d.setDate(gridStart.getDate() + i);
      const iso = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
      out.push({ iso, date: d, inMonth: d.getMonth() === cursor.getMonth() });
    }
    return out;
  }, [cursor]);

  const todayIso = useMemo(() => {
    const d = new Date();
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
  }, []);

  const next14 = useMemo(() => rows.slice(0, 14), [rows]);
  const selectedRows = selectedDate ? (byDate[selectedDate] || []) : [];

  const shiftMonth = (dir: number) => {
    setCursor((c) => new Date(c.getFullYear(), c.getMonth() + dir, 1));
  };

  return (
    <View
      style={{ backgroundColor: C.card, borderRadius: 14, padding: 14, borderWidth: 1, borderColor: C.border, marginBottom: 16, position: 'relative' }}
      data-testid="upcoming-interviews-widget" testID="upcoming-interviews-widget"
    >
      <TouchableOpacity
        onPress={() => setCollapsed((v) => !v)}
        activeOpacity={0.8}
        style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 8 }}
        data-testid="upcoming-interviews-toggle" testID="upcoming-interviews-toggle"
      >
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
          <View style={{ width: 36, height: 36, borderRadius: 10, backgroundColor: C.cyanSoft, alignItems: 'center', justifyContent: 'center' }}>
            <Ionicons name="calendar" size={18} color={C.cyan} />
          </View>
          <View>
            <Text style={{ color: C.text, fontSize: 15, fontWeight: '700' }} data-testid="upcoming-interviews-title" testID="upcoming-interviews-title">{tx('admin.upcomingInterviewsWidget.auto.text.001', 'Upcoming Interviews')}</Text>
            <Text style={{ color: C.textMuted, fontSize: 11 }} data-testid="upcoming-interviews-summary" testID="upcoming-interviews-summary">
              {rows.length} scheduled · next 60 days
            </Text>
          </View>
        </View>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
          {acceptedCount > 0 && (
            <TouchableOpacity accessibilityLabel="mail unread button"
              onPress={(e: any) => { try { e.stopPropagation && e.stopPropagation(); } catch (error) { handleAppRecoverableError({ scope: 'src/components/admin/UpcomingInterviewsWidget.tsx#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); } setConfirmOpen(true); }}
              style={{ flexDirection: 'row', alignItems: 'center', gap: 4, paddingHorizontal: 10, paddingVertical: 6, borderRadius: 8, backgroundColor: (globalThis as any).__alphaColor(C.success, '22'), borderWidth: 1, borderColor: (globalThis as any).__alphaColor(C.success, '44') }}
              data-testid="bulk-send-ics-btn" testID="bulk-send-ics-btn"
            >
              <Ionicons name="mail-unread" size={12} color={C.success} />
              <Text style={{ color: C.success, fontSize: 10, fontWeight: '800' }}>
                Send ICS · {acceptedCount}
              </Text>
            </TouchableOpacity>
          )}
          <TouchableOpacity accessibilityLabel="refresh button"
            onPress={(e: any) => { try { e.stopPropagation && e.stopPropagation(); } catch (error) { handleAppRecoverableError({ scope: 'src/components/admin/UpcomingInterviewsWidget.tsx#catch2', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); } load(); }}
            style={{ flexDirection: 'row', alignItems: 'center', gap: 4, paddingHorizontal: 10, paddingVertical: 6, borderRadius: 8, backgroundColor: C.bgSoft, borderWidth: 1, borderColor: C.border }}
            data-testid="upcoming-interviews-refresh" testID="upcoming-interviews-refresh"
          >
            <Ionicons name="refresh" size={12} color={C.textSec} />
            <Text style={{ color: C.textSec, fontSize: 10, fontWeight: '700' }}>{tx('admin.upcomingInterviewsWidget.auto.text.002', 'Refresh')}</Text>
          </TouchableOpacity>
          <Ionicons name={collapsed ? 'chevron-down' : 'chevron-up'} size={18} color={C.textSec} />
        </View>
      </TouchableOpacity>

      {sendResult ? (
        <View
          style={{ marginTop: 10, padding: 10, borderRadius: 10, backgroundColor: C.successSoft, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(C.success, '44'), flexDirection: 'row', alignItems: 'center', gap: 8 }}
          data-testid="bulk-send-ics-result" testID="bulk-send-ics-result"
        >
          <Ionicons name="checkmark-circle" size={14} color={C.success} />
          <Text style={{ color: C.success, fontSize: 11, fontWeight: '700', flex: 1 }}>
            Calendar invites sent: {sendResult.sent} delivered · {sendResult.skipped} skipped · {sendResult.total} total
          </Text>
          <TouchableOpacity onPress={() => setSendResult(null)} data-testid="bulk-send-ics-result-dismiss" testID="bulk-send-ics-result-dismiss">
            <Ionicons name="close" size={14} color={C.success} />
          </TouchableOpacity>
        </View>
      ) : null}

      {confirmOpen ? (
        <View
          style={{ position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, backgroundColor: 'rgba(8,14,36,0.72)', zIndex: 20, alignItems: 'center', justifyContent: 'center', padding: 20 }}
          data-testid="bulk-send-ics-confirm-modal" testID="bulk-send-ics-confirm-modal"
        >
          <View style={{ backgroundColor: C.card, borderRadius: 14, padding: 18, borderWidth: 1, borderColor: C.border, maxWidth: 480, width: '100%' }}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 10 }}>
              <Ionicons name="mail-unread" size={20} color={C.success} />
              <Text style={{ color: C.text, fontSize: 15, fontWeight: '800' }}>{tx('admin.upcomingInterviewsWidget.auto.text.003', 'Send ICS calendar invites')}</Text>
            </View>
            <Text style={{ color: C.textSec, fontSize: 12, marginBottom: 14, lineHeight: 17 }}>
              This will email a branded interview invitation + `.ics` calendar attachment to{' '}
              <Text style={{ color: C.text, fontWeight: '700' }}>{acceptedCount}</Text> candidate
              {acceptedCount === 1 ? '' : 's'} whose interviews are marked
              <Text style={{ color: C.success, fontWeight: '700' }}>{tx('admin.upcomingInterviewsWidget.auto.text.004', 'Accepted')}</Text> and scheduled in the next 60 days.
              Candidates can add the event to Google Calendar, Outlook, or Apple Calendar with one click.
            </Text>
            <View style={{ flexDirection: 'row', gap: 8, justifyContent: 'flex-end' }}>
              <TouchableOpacity
                onPress={() => setConfirmOpen(false)}
                disabled={sending}
                style={{ paddingHorizontal: 14, paddingVertical: 8, borderRadius: 8, backgroundColor: C.bgSoft, borderWidth: 1, borderColor: C.border, opacity: sending ? 0.5 : 1 }}
                data-testid="bulk-send-ics-cancel" testID="bulk-send-ics-cancel"
              >
                <Text style={{ color: C.textSec, fontSize: 12, fontWeight: '700' }}>{tx('admin.upcomingInterviewsWidget.auto.text.005', 'Cancel')}</Text>
              </TouchableOpacity>
              <TouchableOpacity
                onPress={bulkSendIcs}
                disabled={sending}
                style={{ flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 16, paddingVertical: 8, borderRadius: 8, backgroundColor: C.success, opacity: sending ? 0.7 : 1 }}
                data-testid="bulk-send-ics-confirm" testID="bulk-send-ics-confirm"
              >
                {sending ? <ActivityIndicator size="small" color={C.primaryText} /> : <Ionicons name="send" size={13} color={C.primaryText} />}
                <Text style={{ color: C.primaryText, fontSize: 12, fontWeight: '800' }}>
                  {sending ? 'Sending…' : `Send to ${acceptedCount}`}
                </Text>
              </TouchableOpacity>
            </View>
          </View>
        </View>
      ) : null}

      {collapsed ? null : (
        <View style={{ marginTop: 12 }}>
          {loading ? (
            <View style={{ paddingVertical: 26, alignItems: 'center' }} data-testid="upcoming-interviews-loading" testID="upcoming-interviews-loading">
              <ActivityIndicator size="small" color={C.primary} />
            </View>
          ) : err ? (
            <View style={{ padding: 10, borderRadius: 10, backgroundColor: C.errorSoft, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(C.error, '44') }} data-testid="upcoming-interviews-error" testID="upcoming-interviews-error">
              <Text style={{ color: C.error, fontSize: 12, fontWeight: '700' }}>{err}</Text>
            </View>
          ) : (
            <View style={{ flexDirection: isWide ? 'row' : 'column', gap: 12 }}>
              {/* Calendar column */}
              <View style={{ flex: 1, minWidth: 0, backgroundColor: C.bgSoft, borderRadius: 10, padding: 10, borderWidth: 1, borderColor: C.border }}>
                <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
                  <TouchableOpacity
                    onPress={() => shiftMonth(-1)}
                    style={{ paddingHorizontal: 10, paddingVertical: 6, borderRadius: 8, backgroundColor: C.card, borderWidth: 1, borderColor: C.border }}
                    data-testid="interviews-cal-prev" testID="interviews-cal-prev"
                  >
                    <Ionicons name="chevron-back" size={14} color={C.textSec} />
                  </TouchableOpacity>
                  <Text style={{ color: C.text, fontSize: 13, fontWeight: '800' }} data-testid="interviews-cal-month" testID="interviews-cal-month">
                    {cursor.toLocaleDateString(undefined, { month: 'long', year: 'numeric' })}
                  </Text>
                  <TouchableOpacity
                    onPress={() => shiftMonth(1)}
                    style={{ paddingHorizontal: 10, paddingVertical: 6, borderRadius: 8, backgroundColor: C.card, borderWidth: 1, borderColor: C.border }}
                    data-testid="interviews-cal-next" testID="interviews-cal-next"
                  >
                    <Ionicons name="chevron-forward" size={14} color={C.textSec} />
                  </TouchableOpacity>
                </View>
                <View style={{ flexDirection: 'row', gap: 2, marginBottom: 4 }}>
                  {['S', 'M', 'T', 'W', 'T', 'F', 'S'].map((d, i) => (
                    <View key={i} style={{ flex: 1, alignItems: 'center' }}>
                      <Text style={{ color: C.textMuted, fontSize: 10, fontWeight: '700' }}>{d}</Text>
                    </View>
                  ))}
                </View>
                <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 2 }}>
                  {cells.map((c, i) => {
                    const count = (byDate[c.iso] || []).length;
                    const isToday = c.iso === todayIso;
                    const isSelected = c.iso === selectedDate;
                    const hasIv = count > 0;
                    return (
                      <TouchableOpacity accessibilityLabel={tx('admin.upcomingInterviewsWidget.auto.accessibility.001', 'Set interview date filter')}
                        key={i}
                        onPress={() => setSelectedDate((p) => (p === c.iso ? '' : c.iso))}
                        style={{
                          width: `${100 / 7 - 0.3}%`,
                          aspectRatio: 1,
                          minHeight: 32,
                          backgroundColor: isSelected ? (globalThis as any).__alphaColor(C.primary, '33') : hasIv ? C.cyan + '12' : 'transparent',
                          borderRadius: 6,
                          borderWidth: isToday ? 1 : 0,
                          borderColor: isToday ? C.primary : 'transparent',
                          alignItems: 'center',
                          justifyContent: 'center',
                          opacity: c.inMonth ? 1 : 0.35,
                        }}
                        data-testid={`interviews-cal-cell-${c.iso}`} testID={`interviews-cal-cell-${c.iso}`}
                      >
                        <Text style={{ color: hasIv ? C.text : c.inMonth ? C.textSec : C.textMuted, fontSize: 11, fontWeight: hasIv ? '800' : '600' }}>
                          {c.date.getDate()}
                        </Text>
                        {hasIv && (
                          <View style={{ flexDirection: 'row', gap: 2, marginTop: 2 }}>
                            {Array.from({ length: Math.min(count, 3) }).map((_, j) => (
                              <View key={j} style={{ width: 4, height: 4, borderRadius: 2, backgroundColor: C.cyan }} />
                            ))}
                          </View>
                        )}
                      </TouchableOpacity>
                    );
                  })}
                </View>
                <View style={{ flexDirection: 'row', gap: 10, marginTop: 10, alignItems: 'center', flexWrap: 'wrap' }}>
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}>
                    <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: C.cyan }} />
                    <Text style={{ color: C.textMuted, fontSize: 10 }}>{tx('admin.upcomingInterviewsWidget.auto.text.006', 'Scheduled')}</Text>
                  </View>
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}>
                    <View style={{ width: 8, height: 8, borderRadius: 4, borderWidth: 1, borderColor: C.primary }} />
                    <Text style={{ color: C.textMuted, fontSize: 10 }}>{tx('admin.upcomingInterviewsWidget.auto.text.007', 'Today')}</Text>
                  </View>
                </View>
              </View>

              {/* List column */}
              <View style={{ flex: 1, minWidth: 0 }}>
                <Text style={{ color: C.text, fontSize: 13, fontWeight: '800', marginBottom: 8 }} data-testid="interviews-list-title" testID="interviews-list-title">
                  {selectedDate ? `Interviews on ${fmtShortDate(selectedDate)}` : 'Next 14 scheduled'}
                </Text>
                <ScrollView style={{ maxHeight: 280 }}>
                  {(selectedDate ? selectedRows : next14).length === 0 ? (
                    <View style={{ padding: 16, backgroundColor: C.bgSoft, borderRadius: 10, borderWidth: 1, borderColor: C.border }} data-testid="interviews-list-empty" testID="interviews-list-empty">
                      <Text style={{ color: C.textMuted, fontSize: 12 }}>
                        {selectedDate ? 'No interviews scheduled this day.' : 'No upcoming interviews.'}
                      </Text>
                    </View>
                  ) : (
                    (selectedDate ? selectedRows : next14).map((iv, idx) => {
                      const respColor = RESPONSE_COLOR[iv.candidate_response || 'pending'] || C.textSec;
                      const icon = TYPE_ICON[iv.type] || 'calendar';
                      return (
                        <TouchableOpacity accessibilityLabel={tx('admin.upcomingInterviewsWidget.auto.accessibility.002', 'Open interview application')}
                          key={iv.application_id || idx}
                          onPress={() => onOpenApplication && onOpenApplication(iv.application_id)}
                          activeOpacity={0.7}
                          style={{ flexDirection: 'row', alignItems: 'center', gap: 10, padding: 10, borderRadius: 10, backgroundColor: C.bgSoft, borderWidth: 1, borderColor: C.border, marginBottom: 6 }}
                          data-testid={`interview-row-${idx}`} testID={`interview-row-${idx}`}
                        >
                          <View style={{ width: 32, height: 32, borderRadius: 8, backgroundColor: C.cyanSoft, alignItems: 'center', justifyContent: 'center' }}>
                            <Ionicons name={icon} size={15} color={C.cyan} />
                          </View>
                          <View style={{ flex: 1, minWidth: 0 }}>
                            <Text style={{ color: C.text, fontSize: 12, fontWeight: '700' }} numberOfLines={1} data-testid={`interview-row-name-${idx}`} testID={`interview-row-name-${idx}`}>
                              {iv.full_name || '—'}
                            </Text>
                            <Text style={{ color: C.textMuted, fontSize: 10 }} numberOfLines={1}>
                              {iv.position} · {fmtShortDate(iv.date)} · {iv.time || '—'}
                            </Text>
                          </View>
                          <View style={{ paddingHorizontal: 7, paddingVertical: 3, borderRadius: 999, backgroundColor: (globalThis as any).__alphaColor(respColor, '22'), borderWidth: 1, borderColor: (globalThis as any).__alphaColor(respColor, '44') }} data-testid={`interview-row-response-${idx}`} testID={`interview-row-response-${idx}`}>
                            <Text style={{ color: respColor, fontSize: 9, fontWeight: '800' }}>
                              {(iv.candidate_response || 'pending').toUpperCase().replace('_', ' ')}
                            </Text>
                          </View>
                        </TouchableOpacity>
                      );
                    })
                  )}
                </ScrollView>
              </View>
            </View>
          )}
        </View>
      )}
    </View>
  );
}

/* i18n-probe t('i18n.auto.probe') */
