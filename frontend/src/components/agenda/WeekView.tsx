import React from 'react';
import { View, Text, ScrollView, TouchableOpacity } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { DAYS_SHORT, MONTHS, isSameDay, fmtTime, getCatMeta } from './constants';

interface WeekViewProps {
  weekDays: Date[];
  today: Date;
  selectedDate: Date;
  setSelectedDate: (d: Date) => void;
  getEventsForDay: (d: Date) => any[];
  setDetailEvent: (ev: any) => void;
  C: any;
}

export default function WeekView({
  weekDays, today, selectedDate, setSelectedDate, getEventsForDay, setDetailEvent, C,
}: WeekViewProps) {
  return (
    <View style={{ backgroundColor: C.card, borderRadius: 16, borderWidth: 1, borderColor: C.border, overflow: 'hidden' }} data-testid="week-view" testID="week-view">
      <View style={{ flexDirection: 'row', borderBottomWidth: 1, borderBottomColor: C.border }}>
        {weekDays.map((d, i) => {
          const isToday_ = isSameDay(d, today);
          const isSelected_ = isSameDay(d, selectedDate);
          return (
            <TouchableOpacity key={i} onPress={() => setSelectedDate(d)} accessibilityLabel={DAYS_SHORT[d.getDay()]}
              style={{ flex: 1, paddingVertical: 10, alignItems: 'center', backgroundColor: isSelected_ ? (globalThis as any).__alphaColor(C.primary, '08') : 'transparent' }}>
              <Text style={{ fontSize: 10, fontWeight: '700', color: C.muted }}>{DAYS_SHORT[d.getDay()]}</Text>
              <View style={{
                width: 28, height: 28, borderRadius: 14, alignItems: 'center', justifyContent: 'center', marginTop: 4,
                backgroundColor: isToday_ ? C.primary : 'transparent',
              }}>
                <Text style={{ fontSize: 14, fontWeight: '800', color: isToday_ ? 'var(--app-primary-text)' : C.text }}>{d.getDate()}</Text>
              </View>
            </TouchableOpacity>
          );
        })}
      </View>
      <ScrollView style={{ maxHeight: 400 }} contentContainerStyle={{ padding: 12 }}>
        {weekDays.map((d, i) => {
          const dayEvs = getEventsForDay(d);
          if (dayEvs.length === 0) return null;
          return (
            <View key={i} style={{ marginBottom: 12 }}>
              <Text style={{ fontSize: 12, fontWeight: '700', color: C.muted, marginBottom: 6 }}>
                {DAYS_SHORT[d.getDay()]} {d.getDate()} {MONTHS[d.getMonth()].slice(0, 3)}
              </Text>
              {dayEvs.map(ev => {
                const cat = getCatMeta(ev.category);
                return (
                  <TouchableOpacity key={ev.id} onPress={() => setDetailEvent(ev)}
                    style={{ flexDirection: 'row', alignItems: 'center', gap: 10, paddingVertical: 8, paddingHorizontal: 10, borderRadius: 10, backgroundColor: (globalThis as any).__alphaColor(cat.color, '08'), marginBottom: 4 }}
                    data-testid={`week-event-${ev.id}`} testID={`week-event-${ev.id}`}>
                    <View style={{ width: 4, height: 28, borderRadius: 2, backgroundColor: cat.color }} />
                    <View style={{ flex: 1 }}>
                      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}>
                        <Text style={{ fontSize: 13, fontWeight: '700', color: C.text }}>{ev.title}</Text>
                        {ev.recurrence && ev.recurrence !== 'none' && <Ionicons name="repeat" size={11} color={cat.color} />}
                      </View>
                      <Text style={{ fontSize: 11, color: C.muted }}>{fmtTime(ev.start)} - {fmtTime(ev.end)}</Text>
                    </View>
                    <View style={{ backgroundColor: (globalThis as any).__alphaColor(cat.color, '18'), paddingHorizontal: 8, paddingVertical: 3, borderRadius: 6 }}>
                      <Text style={{ fontSize: 9, fontWeight: '700', color: cat.color }}>{cat.label}</Text>
                    </View>
                  </TouchableOpacity>
                );
              })}
            </View>
          );
        })}
        {weekDays.every(d => getEventsForDay(d).length === 0) && (
          <View style={{ alignItems: 'center', paddingVertical: 40 }}>
            <Ionicons name="calendar-outline" size={40} color={C.muted} />
            <Text style={{ fontSize: 14, fontWeight: '600', color: C.muted, marginTop: 8 }}>No events this week</Text>
          </View>
        )}
      </ScrollView>
    </View>
  );
}

/* i18n-probe t('i18n.auto.probe') */
