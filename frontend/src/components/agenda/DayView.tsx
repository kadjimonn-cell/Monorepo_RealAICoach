import React from 'react';
import { View, Text, ScrollView, TouchableOpacity } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { DAYS_SHORT, MONTHS, HOURS, fmtTime, getCatMeta } from './constants';

interface DayViewProps {
  selectedDate: Date;
  selectedDayEvents: any[];
  openCreateModal: (date?: Date) => void;
  setDetailEvent: (ev: any) => void;
  C: any;
}

export default function DayView({
  selectedDate, selectedDayEvents, openCreateModal, setDetailEvent, C,
}: DayViewProps) {
  return (
    <View style={{ backgroundColor: C.card, borderRadius: 16, borderWidth: 1, borderColor: C.border, overflow: 'hidden' }} data-testid="day-view" testID="day-view">
      <View style={{ padding: 14, borderBottomWidth: 1, borderBottomColor: C.border, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
        <View>
          <Text style={{ fontSize: 18, fontWeight: '800', color: C.text }}>
            {DAYS_SHORT[selectedDate.getDay()]}, {MONTHS[selectedDate.getMonth()]} {selectedDate.getDate()}
          </Text>
          <Text style={{ fontSize: 12, color: C.muted }}>{selectedDayEvents.length} event{selectedDayEvents.length !== 1 ? 's' : ''}</Text>
        </View>
        <TouchableOpacity onPress={() => openCreateModal(selectedDate)}
          style={{ flexDirection: 'row', alignItems: 'center', gap: 4, backgroundColor: (globalThis as any).__alphaColor(C.primary, '12'), paddingHorizontal: 12, paddingVertical: 7, borderRadius: 8 }}
          data-testid="day-add-event-btn" testID="day-add-event-btn">
          <Ionicons name="add" size={16} color={C.primary} />
          <Text style={{ fontSize: 12, fontWeight: '700', color: C.primary }}>Add</Text>
        </TouchableOpacity>
      </View>
      <ScrollView style={{ maxHeight: 500 }} contentContainerStyle={{ padding: 12 }}>
        {HOURS.filter(h => h >= 6 && h <= 22).map(hour => {
          const hourEvents = selectedDayEvents.filter(e => {
            try { return new Date(e.start).getHours() === hour; } catch { return false; }
          });
          return (
            <View key={hour} style={{ flexDirection: 'row', minHeight: 52, borderBottomWidth: 1, borderBottomColor: (globalThis as any).__alphaColor(C.border, '40') }}>
              <View style={{ width: 50, paddingTop: 4 }}>
                <Text style={{ fontSize: 11, fontWeight: '600', color: C.muted, textAlign: 'right', paddingRight: 8 }}>
                  {hour === 0 ? '12 AM' : hour < 12 ? `${hour} AM` : hour === 12 ? '12 PM' : `${hour - 12} PM`}
                </Text>
              </View>
              <View style={{ flex: 1, paddingVertical: 2, paddingLeft: 8, borderLeftWidth: 1, borderLeftColor: (globalThis as any).__alphaColor(C.border, '60') }}>
                {hourEvents.map(ev => {
                  const cat = getCatMeta(ev.category);
                  return (
                    <TouchableOpacity key={ev.id} onPress={() => setDetailEvent(ev)}
                      style={{ backgroundColor: (globalThis as any).__alphaColor(cat.color, '14'), borderLeftWidth: 3, borderLeftColor: cat.color, borderRadius: 6, padding: 8, marginBottom: 4 }}
                      data-testid={`day-event-${ev.id}`} testID={`day-event-${ev.id}`}>
                      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}>
                        <Text style={{ fontSize: 13, fontWeight: '700', color: C.text }}>{ev.title}</Text>
                        {ev.recurrence && ev.recurrence !== 'none' && <Ionicons name="repeat" size={11} color={cat.color} />}
                      </View>
                      <Text style={{ fontSize: 11, color: C.muted }}>{fmtTime(ev.start)} - {fmtTime(ev.end)}</Text>
                    </TouchableOpacity>
                  );
                })}
              </View>
            </View>
          );
        })}
      </ScrollView>
    </View>
  );
}

/* i18n-probe t('i18n.auto.probe') */
