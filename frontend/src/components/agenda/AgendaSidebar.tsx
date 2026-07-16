import React, { useState } from 'react';
import { View, Text, TouchableOpacity, ActivityIndicator, Platform } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { EVENT_CATEGORIES, isSameDay, fmtTime, fmtDateShort, getCatMeta } from './constants';
import api from '../../services/api';

interface AgendaSidebarProps {
  selectedDate: Date;
  today: Date;
  selectedDayEvents: any[];
  upcomingEvents: any[];
  googleConnected: boolean;
  openCreateModal: (date?: Date) => void;
  setDetailEvent: (ev: any) => void;
  C: any;
}

export default function AgendaSidebar({
  selectedDate, today, selectedDayEvents, upcomingEvents,
  googleConnected, openCreateModal, setDetailEvent, C,
}: AgendaSidebarProps) {
  const [connecting, setConnecting] = useState(false);
  const [connectError, setConnectError] = useState('');
  const nextEvent = upcomingEvents[0] || null;

  const handleConnectGoogle = async () => {
    setConnecting(true);
    setConnectError('');
    try {
      const res = await api.get('/integrations/calendar/auth');
      const url = res.data?.authorization_url;
      if (url) {
        if (Platform.OS === 'web') {
          window.location.href = url;
        } else {
          // eslint-disable-next-line @typescript-eslint/no-require-imports
          const { Linking } = require('react-native');
          Linking.openURL(url);
        }
      } else {
        setConnectError('Could not get authorization URL');
      }
    } catch (e: any) {
      const msg = e?.response?.data?.detail || 'Failed to connect';
      setConnectError(msg);
    } finally {
      setConnecting(false);
    }
  };

  return (
    <View style={{ gap: 14 }}>
      <View style={{ backgroundColor: C.card, borderRadius: 16, borderWidth: 1, borderColor: C.border, padding: 16, gap: 10 }} data-testid="agenda-command-center-card" testID="agenda-command-center-card">
        <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
          <Text style={{ fontSize: 14, fontWeight: '800', color: C.text }} data-testid="agenda-command-center-title" testID="agenda-command-center-title">Agenda Command Center</Text>
          <View style={{ paddingHorizontal: 10, paddingVertical: 4, borderRadius: 999, backgroundColor: googleConnected ? (globalThis as any).__alphaColor(C.success, '20') : C.warning + '20' }} data-testid="agenda-google-status-pill" testID="agenda-google-status-pill">
            <Text style={{ fontSize: 10, fontWeight: '700', color: googleConnected ? C.successText : C.warningText }}>
              {googleConnected ? 'Google Connected' : 'Google Not Connected'}
            </Text>
          </View>
        </View>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
          <Ionicons name="time-outline" size={14} color={C.muted} />
          <Text style={{ fontSize: 11, color: C.muted }} data-testid="agenda-next-event-text" testID="agenda-next-event-text">
            {nextEvent
              ? `Next: ${fmtDateShort(new Date(nextEvent.start))} ${fmtTime(nextEvent.start)}`
              : 'No upcoming meetings yet'
            }
          </Text>
        </View>
      </View>

      {/* Selected Day's Events */}
      <View style={{ backgroundColor: C.card, borderRadius: 16, borderWidth: 1, borderColor: C.border, padding: 16 }} data-testid="selected-day-panel" testID="selected-day-panel">
        <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
          <View>
            <Text style={{ fontSize: 15, fontWeight: '800', color: C.text }}>
              {isSameDay(selectedDate, today) ? "Today's Agenda" : fmtDateShort(selectedDate)}
            </Text>
            <Text style={{ fontSize: 11, color: C.muted }}>{selectedDayEvents.length} event{selectedDayEvents.length !== 1 ? 's' : ''} scheduled</Text>
          </View>
          <TouchableOpacity onPress={() => openCreateModal(selectedDate)} style={{ width: 32, height: 32, borderRadius: 10, backgroundColor: (globalThis as any).__alphaColor(C.primary, '12'), alignItems: 'center', justifyContent: 'center' }} data-testid="sidebar-add-event-btn" testID="sidebar-add-event-btn">
            <Ionicons name="add" size={18} color={C.primary} />
          </TouchableOpacity>
        </View>

        {selectedDayEvents.length === 0 ? (
          <View style={{ alignItems: 'center', paddingVertical: 20 }}>
            <Ionicons name="sunny-outline" size={32} color={C.muted} />
            <Text style={{ fontSize: 13, fontWeight: '600', color: C.muted, marginTop: 8 }}>Nothing planned</Text>
            <Text style={{ fontSize: 11, color: C.muted, marginTop: 2 }}>Tap + to add an event</Text>
          </View>
        ) : (
          <View style={{ gap: 6 }}>
            {selectedDayEvents.map(ev => {
              const cat = getCatMeta(ev.category);
              return (
                <TouchableOpacity key={ev.id} onPress={() => setDetailEvent(ev)}
                  style={{ flexDirection: 'row', alignItems: 'center', gap: 10, padding: 10, borderRadius: 10, backgroundColor: (globalThis as any).__alphaColor(cat.color, '08') }}
                  data-testid={`sidebar-event-${ev.id}`} testID={`sidebar-event-${ev.id}`}>
                  <View style={{ width: 36, height: 36, borderRadius: 10, backgroundColor: (globalThis as any).__alphaColor(cat.color, '18'), alignItems: 'center', justifyContent: 'center' }}>
                    <Ionicons name={cat.icon as any} size={16} color={cat.color} />
                  </View>
                  <View style={{ flex: 1 }}>
                    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}>
                      <Text style={{ fontSize: 13, fontWeight: '700', color: C.text }} numberOfLines={1}>{ev.title}</Text>
                      {ev.recurrence && ev.recurrence !== 'none' && <Ionicons name="repeat" size={10} color={cat.color} />}
                    </View>
                    <Text style={{ fontSize: 11, color: C.muted }}>{fmtTime(ev.start)} - {fmtTime(ev.end)}</Text>
                  </View>
                </TouchableOpacity>
              );
            })}
          </View>
        )}
      </View>

      {/* Categories legend */}
      <View style={{ backgroundColor: C.card, borderRadius: 16, borderWidth: 1, borderColor: C.border, padding: 16 }} data-testid="categories-panel" testID="categories-panel">
        <Text style={{ fontSize: 13, fontWeight: '800', color: C.text, marginBottom: 10 }}>Categories</Text>
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6 }}>
          {Object.entries(EVENT_CATEGORIES).map(([key, meta]) => (
            <View key={key} style={{ flexDirection: 'row', alignItems: 'center', gap: 5, paddingHorizontal: 10, paddingVertical: 5, borderRadius: 8, backgroundColor: (globalThis as any).__alphaColor(meta.color, '10') }}>
              <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: meta.color }} />
              <Text style={{ fontSize: 11, fontWeight: '600', color: meta.color }}>{meta.label}</Text>
            </View>
          ))}
        </View>
      </View>

      {/* Upcoming */}
      {upcomingEvents.length > 0 && (
        <View style={{ backgroundColor: C.card, borderRadius: 16, borderWidth: 1, borderColor: C.border, padding: 16 }} data-testid="upcoming-panel" testID="upcoming-panel">
          <Text style={{ fontSize: 13, fontWeight: '800', color: C.text, marginBottom: 10 }}>Upcoming</Text>
          <View style={{ gap: 8 }}>
            {upcomingEvents.slice(0, 5).map(ev => {
              const cat = getCatMeta(ev.category);
              return (
                <TouchableOpacity key={ev.id} onPress={() => setDetailEvent(ev)} style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }} data-testid={`upcoming-${ev.id}`} testID={`upcoming-${ev.id}`}>
                  <View style={{ width: 4, height: 24, borderRadius: 2, backgroundColor: cat.color }} />
                  <View style={{ flex: 1 }}>
                    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}>
                      <Text style={{ fontSize: 12, fontWeight: '700', color: C.text }} numberOfLines={1}>{ev.title}</Text>
                      {ev.recurrence && ev.recurrence !== 'none' && <Ionicons name="repeat" size={9} color={cat.color} />}
                    </View>
                    <Text style={{ fontSize: 10, color: C.muted }}>{fmtDateShort(new Date(ev.start))} {fmtTime(ev.start)}</Text>
                  </View>
                </TouchableOpacity>
              );
            })}
          </View>
        </View>
      )}

      {/* Google Calendar Connect */}
      {!googleConnected && (
        <TouchableOpacity onPress={handleConnectGoogle} disabled={connecting}
          style={{ backgroundColor: C.card, borderRadius: 16, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(C.primary, '30'), padding: 16, alignItems: 'center', opacity: connecting ? 0.7 : 1 }}
          data-testid="google-connect-cta" testID="google-connect-cta">
          <View style={{ width: 40, height: 40, borderRadius: 12, backgroundColor: (globalThis as any).__alphaColor(C.primary, '14'), alignItems: 'center', justifyContent: 'center', marginBottom: 8 }}>
            {connecting
              ? <ActivityIndicator size="small" color={C.primary} />
              : <Ionicons name="logo-google" size={20} color={C.primary} />
            }
          </View>
          <Text style={{ fontSize: 13, fontWeight: '700', color: C.text, marginBottom: 4 }}>
            {connecting ? 'Connecting...' : 'Connect Google Calendar'}
          </Text>
          <Text style={{ fontSize: 11, color: C.muted, textAlign: 'center' }} data-testid="google-connect-cta-copy" testID="google-connect-cta-copy">Enable secure two-way sync with your Google Calendar</Text>
          {connectError ? <Text style={{ fontSize: 10, color: C.error || C.rose || C.warning, marginTop: 6, textAlign: 'center' }} data-testid="google-connect-error" testID="google-connect-error">{connectError}</Text> : null}
        </TouchableOpacity>
      )}
    </View>
  );
}

/* i18n-probe t('i18n.auto.probe') */
