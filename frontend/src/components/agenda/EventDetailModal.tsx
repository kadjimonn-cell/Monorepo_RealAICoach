import React from 'react';
import { View, Text, TouchableOpacity, Modal } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { fmtTime, fmtDateShort, getCatMeta } from './constants';

interface EventDetailModalProps {
  detailEvent: any;
  setDetailEvent: (ev: any) => void;
  openEditModal: (ev: any) => void;
  handleDelete: (eventId: string) => void;
  handleDeleteSeries: (seriesId: string) => void;
  C: any;
}

export default function EventDetailModal({
  detailEvent, setDetailEvent, openEditModal, handleDelete, handleDeleteSeries, C,
}: EventDetailModalProps) {
  return (
    <Modal visible={!!detailEvent} transparent animationType="fade" onRequestClose={() => setDetailEvent(null)}>
      <View style={{ flex: 1, backgroundColor: 'rgba(0,0,0,0.55)', justifyContent: 'center', alignItems: 'center', padding: 20 }}>
        <View style={{ backgroundColor: C.card, borderRadius: 20, padding: 24, width: '100%', maxWidth: 460, borderWidth: 1, borderColor: C.border }} data-testid="event-detail-modal" testID="event-detail-modal" role="dialog" aria-modal={true} aria-label="Event details">
          {detailEvent && (() => {
            const cat = getCatMeta(detailEvent.category);
            const isRecurring = detailEvent.recurrence && detailEvent.recurrence !== 'none';
            return (
              <>
                <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 16 }}>
                  <View style={{ flex: 1, flexDirection: 'row', alignItems: 'center', gap: 12 }}>
                    <View style={{ width: 44, height: 44, borderRadius: 14, backgroundColor: (globalThis as any).__alphaColor(cat.color, '18'), alignItems: 'center', justifyContent: 'center' }}>
                      <Ionicons name={cat.icon as any} size={22} color={cat.color} />
                    </View>
                    <View style={{ flex: 1 }}>
                      <Text style={{ fontSize: 18, fontWeight: '800', color: C.text }}>{detailEvent.title}</Text>
                      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginTop: 2 }}>
                        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}>
                          <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: cat.color }} />
                          <Text style={{ fontSize: 12, fontWeight: '600', color: cat.color }}>{cat.label}</Text>
                        </View>
                        {isRecurring && (
                          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 3, backgroundColor: (globalThis as any).__alphaColor(C.error, '12'), paddingHorizontal: 6, paddingVertical: 2, borderRadius: 6 }}>
                            <Ionicons name="repeat" size={10} color={C.error} />
                            <Text style={{ fontSize: 10, fontWeight: '700', color: C.error, textTransform: 'capitalize' }}>{detailEvent.recurrence}</Text>
                          </View>
                        )}
                      </View>
                    </View>
                  </View>
                  <TouchableOpacity onPress={() => setDetailEvent(null)} data-testid="close-detail-modal" testID="close-detail-modal">
                    <Ionicons name="close" size={22} color={C.muted} />
                  </TouchableOpacity>
                </View>

                <View style={{ height: 1, backgroundColor: C.border, marginBottom: 16 }} />

                <View style={{ gap: 14 }}>
                  {[
                    { icon: 'calendar', label: 'Date', value: fmtDateShort(new Date(detailEvent.start)) },
                    { icon: 'time', label: 'Time', value: `${fmtTime(detailEvent.start)} - ${fmtTime(detailEvent.end)}` },
                    ...(detailEvent.location ? [{ icon: 'location', label: 'Location', value: detailEvent.location }] : []),
                    ...(detailEvent.description ? [{ icon: 'document-text', label: 'Notes', value: detailEvent.description }] : []),
                    ...(detailEvent.reminder_minutes && detailEvent.reminder_minutes > 0 ? [{ icon: 'notifications', label: 'Reminder', value: detailEvent.reminder_minutes >= 1440 ? `${Math.floor(detailEvent.reminder_minutes / 1440)} day before` : detailEvent.reminder_minutes >= 60 ? `${Math.floor(detailEvent.reminder_minutes / 60)} hour before` : `${detailEvent.reminder_minutes} min before` }] : []),
                  ].map(r => (
                    <View key={r.label} style={{ flexDirection: 'row', alignItems: 'flex-start', gap: 12 }}>
                      <View style={{ width: 32, height: 32, borderRadius: 8, backgroundColor: C.bgSoft, alignItems: 'center', justifyContent: 'center' }}>
                        <Ionicons name={r.icon as any} size={16} color={C.accent} />
                      </View>
                      <View style={{ flex: 1 }}>
                        <Text style={{ fontSize: 11, fontWeight: '600', color: C.muted }}>{r.label}</Text>
                        <Text style={{ fontSize: 14, fontWeight: '600', color: C.text, marginTop: 1 }}>{r.value}</Text>
                      </View>
                    </View>
                  ))}
                </View>

                <View style={{ flexDirection: 'row', gap: 8, marginTop: 20 }}>
                  <TouchableOpacity onPress={() => { setDetailEvent(null); openEditModal(detailEvent); }}
                    style={{ flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, backgroundColor: C.primary, paddingVertical: 12, borderRadius: 10 }}
                    data-testid="edit-event-btn" testID="edit-event-btn">
                    <Ionicons name="create-outline" size={16} color={C.primaryText} />
                    <Text style={{ color: C.primaryText, fontSize: 13, fontWeight: '700' }}>Edit</Text>
                  </TouchableOpacity>
                  <TouchableOpacity onPress={() => handleDelete(detailEvent.id)}
                    style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, backgroundColor: (globalThis as any).__alphaColor(C.error, '12'), paddingHorizontal: 16, paddingVertical: 12, borderRadius: 10 }}
                    data-testid="delete-event-btn" testID="delete-event-btn">
                    <Ionicons name="trash-outline" size={16} color={C.error} />
                    <Text style={{ color: C.error, fontSize: 13, fontWeight: '700' }}>Delete</Text>
                  </TouchableOpacity>
                </View>

                {isRecurring && detailEvent.series_id && (
                  <TouchableOpacity onPress={() => handleDeleteSeries(detailEvent.series_id)}
                    style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, backgroundColor: (globalThis as any).__alphaColor(C.error, '06'), paddingVertical: 10, borderRadius: 10, marginTop: 8, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(C.error, '20') }}
                    data-testid="delete-series-btn" testID="delete-series-btn">
                    <Ionicons name="repeat" size={14} color={C.error} />
                    <Text style={{ color: C.error, fontSize: 12, fontWeight: '600' }}>Delete entire series</Text>
                  </TouchableOpacity>
                )}
              </>
            );
          })()}
        </View>
      </View>
    </Modal>
  );
}

/* i18n-probe t('i18n.auto.probe') */
