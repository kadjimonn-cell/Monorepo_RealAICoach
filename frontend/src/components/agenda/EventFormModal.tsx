import React from 'react';
import { View, Text, ScrollView, TouchableOpacity, TextInput, ActivityIndicator, Modal } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { EVENT_CATEGORIES, RECURRENCE_OPTIONS, REMINDER_OPTIONS, MINUTES_OPTIONS, pad, fmtTime } from './constants';
// eslint-disable-next-line @typescript-eslint/no-unused-vars
import { useFocusTrap } from '../../hooks/useFocusTrap';

interface EventFormModalProps {
  visible: boolean;
  onClose: () => void;
  editingEvent: any;
  formTitle: string; setFormTitle: (s: string) => void;
  formCategory: string; setFormCategory: (s: string) => void;
  formDate: string; setFormDate: (s: string) => void;
  formStartHour: number; setFormStartHour: (fn: number | ((h: number) => number)) => void;
  formStartMin: string; setFormStartMin: (s: string) => void;
  formEndHour: number; setFormEndHour: (fn: number | ((h: number) => number)) => void;
  formEndMin: string; setFormEndMin: (s: string) => void;
  formDescription: string; setFormDescription: (s: string) => void;
  formLocation: string; setFormLocation: (s: string) => void;
  formRecurrence: string; setFormRecurrence: (s: string) => void;
  formReminder: number; setFormReminder: (n: number) => void;
  formSaving: boolean;
  handleSave: () => void;
  handleAiSuggest: () => void;
  aiLoading: boolean;
  showAiPanel: boolean; setShowAiPanel: (b: boolean) => void;
  aiSuggestions: any[];
  applySuggestion: (sug: any) => void;
  C: any;
}

export default function EventFormModal({
  visible, onClose, editingEvent,
  formTitle, setFormTitle, formCategory, setFormCategory,
  formDate, setFormDate,
  formStartHour, setFormStartHour, formStartMin, setFormStartMin,
  formEndHour, setFormEndHour, formEndMin, setFormEndMin,
  formDescription, setFormDescription, formLocation, setFormLocation,
  formRecurrence, setFormRecurrence, formReminder, setFormReminder,
  formSaving, handleSave, handleAiSuggest,
  aiLoading, showAiPanel, setShowAiPanel, aiSuggestions, applySuggestion,
  C,
}: EventFormModalProps) {
  return (
    <Modal visible={visible} transparent animationType="fade" onRequestClose={onClose}>
      <View style={{ flex: 1, backgroundColor: 'rgba(0,0,0,0.55)', justifyContent: 'center', alignItems: 'center', padding: 20 }}>
        <View style={{ backgroundColor: C.card, borderRadius: 20, padding: 24, width: '100%', maxWidth: 520, borderWidth: 1, borderColor: C.border, maxHeight: '92%' }} data-testid="event-modal" testID="event-modal" role="dialog" aria-modal={true} aria-label={editingEvent ? 'Edit event' : 'New event'}>
          <ScrollView showsVerticalScrollIndicator={false}>
            <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
              <Text style={{ fontSize: 20, fontWeight: '800', color: C.text }}>{editingEvent ? 'Edit Event' : 'New Event'}</Text>
              <TouchableOpacity onPress={onClose} data-testid="close-event-modal" testID="close-event-modal" accessibilityRole="button" >
                <Ionicons name="close" size={22} color={C.muted} />
              </TouchableOpacity>
            </View>

            <Text style={{ fontSize: 12, fontWeight: '700', color: C.muted, marginBottom: 6, textTransform: 'uppercase', letterSpacing: 0.5 }}>Event Title</Text>
            <TextInput
              value={formTitle} onChangeText={setFormTitle}
              placeholder="e.g., Team standup, Gym session..."
              placeholderTextColor={C.muted}
              style={{ backgroundColor: C.bgSoft, color: C.text, borderRadius: 10, padding: 12, borderWidth: 1, borderColor: C.border, fontSize: 15, fontWeight: '600', marginBottom: 16 }}
              data-testid="event-title-input" testID="event-title-input"
            />

            <Text style={{ fontSize: 12, fontWeight: '700', color: C.muted, marginBottom: 8, textTransform: 'uppercase', letterSpacing: 0.5 }}>Category</Text>
            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginBottom: 16 }}>
              {Object.entries(EVENT_CATEGORIES).map(([key, meta]) => (
                <TouchableOpacity key={key} accessibilityLabel="Set form category in event form modal button" onPress={() => setFormCategory(key)}
                  style={{
                    flexDirection: 'row', alignItems: 'center', gap: 6,
                    paddingHorizontal: 12, paddingVertical: 8, borderRadius: 10,
                    backgroundColor: formCategory === key ? (globalThis as any).__alphaColor(meta.color, '18') : C.bgSoft,
                    borderWidth: 1.5, borderColor: formCategory === key ? meta.color : C.border,
                  }}
                  data-testid={`cat-${key}`} testID={`cat-${key}`}>
                  <Ionicons name={meta.icon as any} size={14} color={formCategory === key ? meta.color : C.muted} />
                  <Text style={{ fontSize: 12, fontWeight: '700', color: formCategory === key ? meta.color : C.muted }}>{meta.label}</Text>
                </TouchableOpacity>
              ))}
            </View>

            <Text style={{ fontSize: 12, fontWeight: '700', color: C.muted, marginBottom: 8, textTransform: 'uppercase', letterSpacing: 0.5 }}>Repeat</Text>
            <View style={{ flexDirection: 'row', gap: 6, marginBottom: 16 }} data-testid="recurrence-picker" testID="recurrence-picker">
              {RECURRENCE_OPTIONS.map(opt => (
                <TouchableOpacity key={opt.key} accessibilityLabel="Set form recurrence in event form modal button" onPress={() => setFormRecurrence(opt.key)}
                  style={{
                    flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 5,
                    paddingVertical: 9, borderRadius: 10,
                    backgroundColor: formRecurrence === opt.key ? '#0F766E14' : C.bgSoft,
                    borderWidth: 1.5, borderColor: formRecurrence === opt.key ? 'var(--app-primary)' : C.border,
                  }}
                  data-testid={`recurrence-${opt.key}`} testID={`recurrence-${opt.key}`}>
                  <Ionicons name={opt.icon as any} size={13} color={formRecurrence === opt.key ? 'var(--app-primary)' : C.muted} />
                  <Text style={{ fontSize: 11, fontWeight: '700', color: formRecurrence === opt.key ? 'var(--app-primary)' : C.muted }}>{opt.label}</Text>
                </TouchableOpacity>
              ))}
            </View>

            <Text style={{ fontSize: 12, fontWeight: '700', color: C.muted, marginBottom: 8, textTransform: 'uppercase', letterSpacing: 0.5 }}>Reminder</Text>
            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginBottom: 16 }}>
              {REMINDER_OPTIONS.map(opt => (
                <TouchableOpacity key={opt.key} accessibilityLabel="Set form reminder in event form modal button" onPress={() => setFormReminder(opt.key)}
                  style={{
                    flexDirection: 'row', alignItems: 'center', gap: 5,
                    paddingHorizontal: 12, paddingVertical: 8, borderRadius: 10,
                    backgroundColor: formReminder === opt.key ? (globalThis as any).__alphaColor(C.accent, '14') : C.bgSoft,
                    borderWidth: 1.5, borderColor: formReminder === opt.key ? C.accent : C.border,
                  }}
                  data-testid={`reminder-${opt.key}`} testID={`reminder-${opt.key}`}>
                  <Ionicons name={opt.icon as any} size={13} color={formReminder === opt.key ? C.accent : C.muted} />
                  <Text style={{ fontSize: 11, fontWeight: '700', color: formReminder === opt.key ? C.accent : C.muted }}>{opt.label}</Text>
                </TouchableOpacity>
              ))}
            </View>

            <View style={{ flexDirection: 'row', alignItems: 'flex-end', gap: 8, marginBottom: 16 }}>
              <View style={{ flex: 1 }}>
                <Text style={{ fontSize: 12, fontWeight: '700', color: C.muted, marginBottom: 6, textTransform: 'uppercase', letterSpacing: 0.5 }}>Date</Text>
                <TextInput value={formDate} onChangeText={setFormDate} placeholder="YYYY-MM-DD" placeholderTextColor={C.muted}
                  style={{ backgroundColor: C.bgSoft, color: C.text, borderRadius: 10, padding: 12, borderWidth: 1, borderColor: C.border, fontSize: 14 }}
                  data-testid="event-date-input" testID="event-date-input" />
              </View>
              <TouchableOpacity onPress={handleAiSuggest} disabled={aiLoading} accessibilityLabel="sparkles button"
                style={{
                  flexDirection: 'row', alignItems: 'center', gap: 6,
                  backgroundColor: (globalThis as any).__alphaColor(C.accent, '14'), paddingHorizontal: 14, paddingVertical: 12, borderRadius: 10,
                  borderWidth: 1.5, borderColor: (globalThis as any).__alphaColor(C.accent, '30'),
                }}
                data-testid="ai-suggest-btn" testID="ai-suggest-btn">
                {aiLoading ? <ActivityIndicator size="small" color={C.accent} /> : <Ionicons name="sparkles" size={16} color={C.accent} />}
                <Text style={{ fontSize: 12, fontWeight: '700', color: C.accent }}>AI Suggest</Text>
              </TouchableOpacity>
            </View>

            {showAiPanel && (
              <View style={{ backgroundColor: (globalThis as any).__alphaColor(C.accent, '06'), borderRadius: 12, padding: 12, marginBottom: 16, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(C.accent, '20') }} data-testid="ai-suggestions-panel" testID="ai-suggestions-panel">
                <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                    <Ionicons name="sparkles" size={14} color={C.accent} />
                    <Text style={{ fontSize: 13, fontWeight: '800', color: C.accent }}>AI-Suggested Times</Text>
                  </View>
                  <TouchableOpacity onPress={() => setShowAiPanel(false)} data-testid="close-ai-panel" testID="close-ai-panel">
                    <Ionicons name="close-circle" size={18} color={C.muted} />
                  </TouchableOpacity>
                </View>
                {aiLoading ? (
                  <View style={{ paddingVertical: 20, alignItems: 'center' }}>
                    <ActivityIndicator color={C.accent} />
                    <Text style={{ fontSize: 12, color: C.muted, marginTop: 6 }}>Analyzing your schedule...</Text>
                  </View>
                ) : aiSuggestions.length === 0 ? (
                  <Text style={{ fontSize: 12, color: C.muted, textAlign: 'center', paddingVertical: 10 }}>No suggestions available</Text>
                ) : (
                  <View style={{ gap: 6 }}>
                    {aiSuggestions.map((sug, i) => (
                      <TouchableOpacity key={i} accessibilityLabel="Apply suggestion in event form modal button" onPress={() => applySuggestion(sug)}
                        style={{
                          flexDirection: 'row', alignItems: 'center', gap: 10,
                          backgroundColor: C.card, borderRadius: 10, padding: 10,
                          borderWidth: 1, borderColor: C.border,
                        }}
                        data-testid={`ai-suggestion-${i}`} testID={`ai-suggestion-${i}`}>
                        <View style={{ width: 32, height: 32, borderRadius: 8, backgroundColor: (globalThis as any).__alphaColor(C.accent, '14'), alignItems: 'center', justifyContent: 'center' }}>
                          <Text style={{ fontSize: 12, fontWeight: '800', color: C.accent }}>{i + 1}</Text>
                        </View>
                        <View style={{ flex: 1 }}>
                          <Text style={{ fontSize: 13, fontWeight: '700', color: C.text }}>
                            {fmtTime(sug.start)} - {fmtTime(sug.end)}
                          </Text>
                          <Text style={{ fontSize: 11, color: C.muted }}>{sug.reason}</Text>
                        </View>
                        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}>
                          <View style={{ width: 28, height: 4, borderRadius: 2, backgroundColor: C.border, overflow: 'hidden' }}>
                            <View style={{ width: `${sug.score}%`, height: 4, borderRadius: 2, backgroundColor: sug.score >= 80 ? C.success : sug.score >= 60 ? C.warning : C.error }} />
                          </View>
                          <Text style={{ fontSize: 10, fontWeight: '700', color: C.muted }}>{sug.score}</Text>
                        </View>
                        <Ionicons name="checkmark-circle" size={18} color={C.successText} />
                      </TouchableOpacity>
                    ))}
                    <Text style={{ fontSize: 10, color: C.muted, textAlign: 'center', marginTop: 4 }}>Tap a suggestion to apply, then modify if needed</Text>
                  </View>
                )}
              </View>
            )}

            <View style={{ flexDirection: 'row', gap: 12, marginBottom: 16 }}>
              <View style={{ flex: 1 }}>
                <Text style={{ fontSize: 12, fontWeight: '700', color: C.muted, marginBottom: 6, textTransform: 'uppercase', letterSpacing: 0.5 }}>Start</Text>
                <View style={{ flexDirection: 'row', gap: 6 }}>
                  <View style={{ flex: 1, flexDirection: 'row', alignItems: 'center', backgroundColor: C.bgSoft, borderRadius: 10, borderWidth: 1, borderColor: C.border }}>
                    <TouchableOpacity accessibilityLabel="Decrease start hour" onPress={() => setFormStartHour((h: number) => Math.max(0, h - 1))} style={{ paddingHorizontal: 8, paddingVertical: 10 }}>
                      <Ionicons name="chevron-back" size={14} color={C.muted} />
                    </TouchableOpacity>
                    <Text style={{ flex: 1, textAlign: 'center', color: C.text, fontSize: 14, fontWeight: '700' }}>{pad(formStartHour)}</Text>
                    <TouchableOpacity accessibilityLabel="Increase start hour" onPress={() => setFormStartHour((h: number) => Math.min(23, h + 1))} style={{ paddingHorizontal: 8, paddingVertical: 10 }}>
                      <Ionicons name="chevron-forward" size={14} color={C.muted} />
                    </TouchableOpacity>
                  </View>
                  <View style={{ flexDirection: 'row', gap: 3 }}>
                    {MINUTES_OPTIONS.map(m => (
                      <TouchableOpacity key={m} accessibilityLabel="Set form start min in event form modal button" onPress={() => setFormStartMin(m)}
                        style={{ paddingHorizontal: 8, paddingVertical: 10, borderRadius: 8, backgroundColor: formStartMin === m ? (globalThis as any).__alphaColor(C.primary, '18') : C.bgSoft, borderWidth: 1, borderColor: formStartMin === m ? C.primary : C.border }}>
                        <Text style={{ fontSize: 12, fontWeight: '600', color: formStartMin === m ? C.primary : C.muted }}>{m}</Text>
                      </TouchableOpacity>
                    ))}
                  </View>
                </View>
              </View>
              <View style={{ flex: 1 }}>
                <Text style={{ fontSize: 12, fontWeight: '700', color: C.muted, marginBottom: 6, textTransform: 'uppercase', letterSpacing: 0.5 }}>End</Text>
                <View style={{ flexDirection: 'row', gap: 6 }}>
                  <View style={{ flex: 1, flexDirection: 'row', alignItems: 'center', backgroundColor: C.bgSoft, borderRadius: 10, borderWidth: 1, borderColor: C.border }}>
                    <TouchableOpacity accessibilityLabel="Decrease end hour" onPress={() => setFormEndHour((h: number) => Math.max(0, h - 1))} style={{ paddingHorizontal: 8, paddingVertical: 10 }}>
                      <Ionicons name="chevron-back" size={14} color={C.muted} />
                    </TouchableOpacity>
                    <Text style={{ flex: 1, textAlign: 'center', color: C.text, fontSize: 14, fontWeight: '700' }}>{pad(formEndHour)}</Text>
                    <TouchableOpacity accessibilityLabel="Increase end hour" onPress={() => setFormEndHour((h: number) => Math.min(23, h + 1))} style={{ paddingHorizontal: 8, paddingVertical: 10 }}>
                      <Ionicons name="chevron-forward" size={14} color={C.muted} />
                    </TouchableOpacity>
                  </View>
                  <View style={{ flexDirection: 'row', gap: 3 }}>
                    {MINUTES_OPTIONS.map(m => (
                      <TouchableOpacity key={m} accessibilityLabel="Set form end min in event form modal button" onPress={() => setFormEndMin(m)}
                        style={{ paddingHorizontal: 8, paddingVertical: 10, borderRadius: 8, backgroundColor: formEndMin === m ? (globalThis as any).__alphaColor(C.primary, '18') : C.bgSoft, borderWidth: 1, borderColor: formEndMin === m ? C.primary : C.border }}>
                        <Text style={{ fontSize: 12, fontWeight: '600', color: formEndMin === m ? C.primary : C.muted }}>{m}</Text>
                      </TouchableOpacity>
                    ))}
                  </View>
                </View>
              </View>
            </View>

            <Text style={{ fontSize: 12, fontWeight: '700', color: C.muted, marginBottom: 6, textTransform: 'uppercase', letterSpacing: 0.5 }}>Location (optional)</Text>
            <View style={{ flexDirection: 'row', alignItems: 'center', backgroundColor: C.bgSoft, borderRadius: 10, borderWidth: 1, borderColor: C.border, paddingHorizontal: 12, marginBottom: 16 }}>
              <Ionicons name="location-outline" size={16} color={C.muted} />
              <TextInput value={formLocation} onChangeText={setFormLocation} placeholder="Add location or meeting link" placeholderTextColor={C.muted}
                style={{ flex: 1, color: C.text, padding: 12, fontSize: 14 }} data-testid="event-location-input" testID="event-location-input" />
            </View>

            <Text style={{ fontSize: 12, fontWeight: '700', color: C.muted, marginBottom: 6, textTransform: 'uppercase', letterSpacing: 0.5 }}>Notes (optional)</Text>
            <TextInput value={formDescription} onChangeText={setFormDescription} placeholder="Add details or notes..." placeholderTextColor={C.muted}
              multiline
              style={{ backgroundColor: C.bgSoft, color: C.text, borderRadius: 10, padding: 12, borderWidth: 1, borderColor: C.border, fontSize: 14, minHeight: 70, textAlignVertical: 'top', marginBottom: 20 }}
              data-testid="event-notes-input" testID="event-notes-input" />

            {formRecurrence !== 'none' && (
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, backgroundColor: (globalThis as any).__alphaColor(C.accent, '08'), borderRadius: 10, padding: 10, marginBottom: 16, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(C.accent, '20') }} data-testid="recurrence-info" testID="recurrence-info">
                <Ionicons name="repeat" size={16} color={C.accent} />
                <Text style={{ fontSize: 12, color: C.accent, fontWeight: '600', flex: 1 }}>
                  This event will repeat {formRecurrence} indefinitely. Up to 60 future instances will be created.
                </Text>
              </View>
            )}

            <TouchableOpacity onPress={handleSave} disabled={formSaving || !formTitle.trim()}
              style={{ backgroundColor: C.primary, paddingVertical: 14, borderRadius: 12, alignItems: 'center', opacity: (formSaving || !formTitle.trim()) ? 0.6 : 1 }}
              data-testid="save-event-btn" testID="save-event-btn">
              {formSaving ? (
                <ActivityIndicator color={C.primaryText} />
              ) : (
                <Text style={{ color: C.primaryText, fontSize: 15, fontWeight: '800' }}>{editingEvent ? 'Update Event' : 'Create Event'}</Text>
              )}
            </TouchableOpacity>
          </ScrollView>
        </View>
      </View>
    </Modal>
  );
}

/* i18n-probe t('i18n.auto.probe') */
