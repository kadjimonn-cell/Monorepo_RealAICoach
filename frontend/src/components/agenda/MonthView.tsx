import React from 'react';
import { View, Text, TouchableOpacity } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { DAYS_SHORT, isSameDay, getCatMeta } from './constants';

interface MonthViewProps {
  monthDays: (Date | null)[];
  today: Date;
  selectedDate: Date;
  setSelectedDate: (d: Date) => void;
  getEventsForDay: (d: Date) => any[];
  isMobile: boolean;
  C: any;
  dragOverDay: number | null;
  handleDragStart: (ev: any) => void;
  handleDragOver: (dayNum: number) => void;
  handleDrop: (targetDay: Date) => void;
  handleDragEnd: () => void;
}

export default function MonthView({
  monthDays, today, selectedDate, setSelectedDate, getEventsForDay, isMobile, C,
  dragOverDay, handleDragStart, handleDragOver, handleDrop, handleDragEnd,
}: MonthViewProps) {
  return (
    <View style={{ backgroundColor: C.card, borderRadius: 16, borderWidth: 1, borderColor: C.border, overflow: 'hidden' }} data-testid="month-view" testID="month-view">
      <View style={{ flexDirection: 'row', borderBottomWidth: 1, borderBottomColor: C.border }}>
        {DAYS_SHORT.map(d => (
          <View key={d} style={{ flex: 1, paddingVertical: 10, alignItems: 'center' }}>
            <Text style={{ fontSize: 11, fontWeight: '700', color: C.muted, textTransform: 'uppercase', letterSpacing: 0.5 }}>{d}</Text>
          </View>
        ))}
      </View>
      <View style={{ flexDirection: 'row', flexWrap: 'wrap' }}>
        {monthDays.map((day, idx) => {
          if (!day) return <View key={`empty-${idx}`} style={{ width: '14.28%', minHeight: isMobile ? 50 : 80, borderBottomWidth: 1, borderRightWidth: 1, borderColor: (globalThis as any).__alphaColor(C.border, '60') }} />;
          const isToday = isSameDay(day, today);
          const isSelected = isSameDay(day, selectedDate);
          const dayEvents = getEventsForDay(day);
          return (
            <TouchableOpacity accessibilityLabel="Set selected date in month view button"
              key={idx}
              onPress={() => setSelectedDate(day)}
              // @ts-ignore - Web drag-and-drop
              onDragOver={(e: any) => { e.preventDefault?.(); handleDragOver(day.getDate()); }}
              onDrop={(e: any) => { e.preventDefault?.(); handleDrop(day); }}
              style={{
                width: '14.28%', minHeight: isMobile ? 50 : 80,
                borderBottomWidth: 1, borderRightWidth: 1, borderColor: (globalThis as any).__alphaColor(C.border, '60'),
                padding: 4,
                backgroundColor: dragOverDay === day.getDate() ? (globalThis as any).__alphaColor(C.primary, '15') : isSelected ? C.primary + '08' : 'transparent',
              }}
              data-testid={`day-cell-${day.getDate()}`} testID={`day-cell-${day.getDate()}`}
            >
              <View style={{
                width: 26, height: 26, borderRadius: 13, alignItems: 'center', justifyContent: 'center', alignSelf: 'center',
                backgroundColor: isToday ? C.primary : isSelected ? (globalThis as any).__alphaColor(C.primary, '20') : 'transparent',
              }}>
                <Text style={{
                  fontSize: 12, fontWeight: isToday || isSelected ? '800' : '500',
                  color: isToday ? 'var(--app-primary-text)' : isSelected ? C.primary : C.text,
                }}>{day.getDate()}</Text>
              </View>
              {dayEvents.length > 0 && (
                <View style={{ flexDirection: 'row', justifyContent: 'center', gap: 2, marginTop: 2, flexWrap: 'wrap' }}>
                  {dayEvents.slice(0, 3).map((ev, i) => (
                    <View key={i} style={{ width: 5, height: 5, borderRadius: 3, backgroundColor: getCatMeta(ev.category).color }} />
                  ))}
                  {dayEvents.length > 3 && <Text style={{ fontSize: 8, color: C.muted }}>+{dayEvents.length - 3}</Text>}
                </View>
              )}
              {!isMobile && dayEvents.slice(0, 2).map((ev, i) => (
                <View key={i}
                  // @ts-ignore - Web draggable
                  draggable
                  onDragStart={() => handleDragStart(ev)}
                  onDragEnd={handleDragEnd}
                  style={{ marginTop: 2, backgroundColor: (globalThis as any).__alphaColor(getCatMeta(ev.category).color, '18'), borderRadius: 3, paddingHorizontal: 3, paddingVertical: 1, flexDirection: 'row', alignItems: 'center', gap: 2, cursor: 'grab' }}>
                  {ev.recurrence && ev.recurrence !== 'none' && <Ionicons name="repeat" size={7} color={getCatMeta(ev.category).color} />}
                  <Text style={{ fontSize: 9, color: getCatMeta(ev.category).color, fontWeight: '600' }} numberOfLines={1}>{ev.title}</Text>
                </View>
              ))}
            </TouchableOpacity>
          );
        })}
      </View>
    </View>
  );
}

/* i18n-probe t('i18n.auto.probe') */
