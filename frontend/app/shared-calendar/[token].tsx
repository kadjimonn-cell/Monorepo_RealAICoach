import React, { useEffect, useMemo, useState } from 'react';
import { View, Text, ScrollView, StyleSheet } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useLocalSearchParams } from 'expo-router';
import api from '../../src/services/api';
import { AgendaSkeleton } from '../../src/components/SkeletonLoaders';
import { useTheme } from '../../src/context/ThemeContext';
import { useTranslation } from '../../src/hooks/useTranslation';

const fmtTime = (s: string) => {
  try { return new Date(s).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }); } catch { return s; }
};

const fmtDateFull = (s: string) => {
  try { return new Date(s + 'T00:00:00').toLocaleDateString([], { weekday: 'long', month: 'long', day: 'numeric', year: 'numeric' }); } catch { return s; }
};

export default function SharedCalendarPage() {
  const { colors } = useTheme();
  const { t } = useTranslation();
  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };

  // @autofix-moved: was module-level const makeStyles
  function makeStyles(colors: any) { return StyleSheet.create({
    container: { flex: 1, backgroundColor: colors.surface, alignItems: 'center', justifyContent: 'center', padding: 20 },
    loadingText: { color: colors.textMuted, marginTop: 12, fontSize: 14 },
    errorTitle: { color: colors.textSec, fontSize: 18, fontWeight: '800', marginTop: 16 },
    errorText: { color: colors.textMuted, fontSize: 13, marginTop: 6, textAlign: 'center' },
    header: { alignItems: 'center', marginBottom: 28, paddingVertical: 24 },
    iconWrap: { width: 52, height: 52, borderRadius: 16, backgroundColor: colors.primarySoft, alignItems: 'center', justifyContent: 'center', marginBottom: 12 },
    title: { fontSize: 22, fontWeight: '800', color: colors.text, marginBottom: 4 },
    subtitle: { fontSize: 14, color: colors.textMuted, marginBottom: 12 },
    metaRow: { flexDirection: 'row', gap: 10, flexWrap: 'wrap', justifyContent: 'center' },
    metaChip: { flexDirection: 'row', alignItems: 'center', gap: 4, paddingHorizontal: 10, paddingVertical: 4, borderRadius: 8, backgroundColor: colors.surface },
    metaText: { fontSize: 11, color: colors.textMuted, fontWeight: '600' },
    emptyCard: { alignItems: 'center', padding: 30, borderRadius: 16, backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.surface },
    emptyTitle: { fontSize: 16, fontWeight: '700', color: colors.successText, marginTop: 12 },
    emptyText: { fontSize: 13, color: colors.textMuted, marginTop: 4 },
    dateSection: { marginBottom: 16 },
    dateHeader: { fontSize: 13, fontWeight: '700', color: colors.primary, marginBottom: 8, textTransform: 'uppercase', letterSpacing: 0.5 },
    eventsCard: { borderRadius: 14, backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.surface, overflow: 'hidden' },
    eventRow: { flexDirection: 'row', alignItems: 'center', padding: 14, gap: 12 },
    timeBadge: { alignItems: 'center', width: 54 },
    timeText: { fontSize: 11, fontWeight: '700', color: colors.textSec },
    timeDash: { fontSize: 9, color: colors.textMuted },
    eventTitle: { fontSize: 13, fontWeight: '600', color: colors.text },
    statusDot: { width: 8, height: 8, borderRadius: 4 },
    footer: { alignItems: 'center', paddingVertical: 24 },
    footerText: { fontSize: 11, color: colors.textSec },
  }); }
  const s = useMemo(() => makeStyles(colors), [colors]);
  const { token } = useLocalSearchParams();
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!token) { setError(tx('sharedCalendar.errors.invalidLink', 'Invalid share link')); setLoading(false); return; }
    (async () => {
      try {
        const res = await api.get(`/calendar/shared/${token}`);
        setData(res.data);
      } catch (e: any) {
        setError(e?.response?.data?.detail || tx('sharedCalendar.errors.notFound', 'Share link not found or expired'));
      } finally { setLoading(false); }
    })();
  }, [token]);

  if (loading) {
    return (
      <SafeAreaView style={s.container} data-testid="shared-calendar-loading" testID="shared-calendar-loading">
        <AgendaSkeleton />
      </SafeAreaView>
    );
  }

  if (error || !data) {
    return (
      <SafeAreaView style={s.container} data-testid="shared-calendar-error" testID="shared-calendar-error">
        <Ionicons name="calendar-outline" size={48} color={colors.textMuted} />
        <Text style={s.errorTitle}>{tx('sharedCalendar.errors.title', 'Calendar Not Found')}</Text>
        <Text style={s.errorText}>{error || tx('sharedCalendar.errors.expired', 'This share link is invalid or has expired.')}</Text>
      </SafeAreaView>
    );
  }

  const share = data.share;
  const dates = Object.keys(data.events_by_date || {}).sort();
  const totalEvents = data.events?.length || 0;

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: colors.card }} data-testid="shared-calendar-page" testID="shared-calendar-page">
      <ScrollView contentContainerStyle={{ padding: 20, maxWidth: 960, alignSelf: 'center', width: '100%' }}>
        {/* Header */}
        <View style={s.header} data-testid="shared-calendar-header" testID="shared-calendar-header">
          <View style={s.iconWrap}>
            <Ionicons name="calendar" size={24} color={colors.indigoText} />
          </View>
          <Text style={s.title}>{share.name || tx('sharedCalendar.labels.availability', 'Availability')}</Text>
          <Text style={s.subtitle}>{tx('sharedCalendar.labels.sharedBy', 'Shared by')} {share.owner_name}</Text>
          <View style={s.metaRow}>
            <View style={s.metaChip}>
              <Ionicons name="globe-outline" size={12} color={colors.textMuted} />
              <Text style={s.metaText}>{share.owner_timezone}</Text>
            </View>
            <View style={s.metaChip}>
              <Ionicons name="time-outline" size={12} color={colors.textMuted} />
              <Text style={s.metaText}>Next {share.days} days</Text>
            </View>
            <View style={s.metaChip}>
              <Ionicons name="list-outline" size={12} color={colors.textMuted} />
              <Text style={s.metaText}>{totalEvents} event{totalEvents !== 1 ? 's' : ''}</Text>
            </View>
          </View>
        </View>

        {/* Events by Date */}
        {dates.length === 0 ? (
          <View style={s.emptyCard} data-testid="shared-calendar-empty" testID="shared-calendar-empty">
            <Ionicons name="sunny-outline" size={32} color={colors.successText} />
            <Text style={s.emptyTitle}>All Clear!</Text>
            <Text style={s.emptyText}>{share.owner_name} has no events in the next {share.days} days.</Text>
          </View>
        ) : (
          dates.map(dateStr => (
            <View key={dateStr} style={s.dateSection} data-testid={`shared-date-${dateStr}`} testID={`shared-date-${dateStr}`}>
              <Text style={s.dateHeader}>{fmtDateFull(dateStr)}</Text>
              <View style={s.eventsCard}>
                {(data.events_by_date[dateStr] || []).map((evt: any, i: number) => (
                  <View key={evt.id || i} style={[s.eventRow, i > 0 && { borderTopWidth: 1, borderTopColor: colors.card }]}
                    data-testid={`shared-event-${evt.id}`} testID={`shared-event-${evt.id}`}>
                    <View style={s.timeBadge}>
                      <Text style={s.timeText}>{fmtTime(evt.start)}</Text>
                      <Text style={s.timeDash}>-</Text>
                      <Text style={s.timeText}>{fmtTime(evt.end)}</Text>
                    </View>
                    <View style={{ flex: 1 }}>
                      <Text style={s.eventTitle}>{evt.title}</Text>
                    </View>
                    <View style={[s.statusDot, { backgroundColor: share.show_titles ? colors.indigo : colors.warning }]} />
                  </View>
                ))}
              </View>
            </View>
          ))
        )}

        {/* Footer */}
        <View style={s.footer}>
          <Text style={s.footerText}>Powered by RealAICoach Calendar</Text>
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}
