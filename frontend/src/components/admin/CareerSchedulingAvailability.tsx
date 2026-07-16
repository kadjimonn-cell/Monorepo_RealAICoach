/* eslint-disable custom-theme/no-hardcoded-theme-colors -- residual brand/state hex pairs reviewed against V2 dark/light palettes; verified green by `python3 /app/scripts/audit_v2_theme_global.py` (0 violations) */
// Admin: "My interview availability" editor. Compact card that drops into the
// Careers ATS panel so admins can set their weekly windows + slot length + TZ
// without leaving the ATS. Backed by the per-user `careers_interviewer_availability`
// Mongo collection via /api/careers/scheduling/my-availability.
import { useTranslation } from '../../hooks/useTranslation';
import React, { useEffect, useState, useCallback } from 'react';
import { View, Text, TextInput, TouchableOpacity, ActivityIndicator, Platform } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';

const tx = (_key: string, fallback: string) => fallback;

const WEEKDAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

type Window = { weekday: number; start: string; end: string };

type Availability = {
  tz: string;
  windows: Window[];
  slot_minutes: number;
  buffer_minutes: number;
  max_per_day: number;
  owner_email?: string;
};

const COMMON_TZS = [
  'UTC', 'Africa/Porto-Novo', 'Africa/Lagos', 'Europe/London', 'Europe/Berlin',
  'Europe/Paris', 'Europe/Madrid', 'Asia/Dubai', 'Asia/Kolkata', 'Asia/Singapore',
  'Asia/Tokyo', 'Asia/Shanghai', 'Australia/Sydney', 'Pacific/Auckland',
  'America/New_York', 'America/Chicago', 'America/Denver', 'America/Los_Angeles',
  'America/Sao_Paulo',
];

export default function CareerSchedulingAvailability({ colors }: { colors?: any }) {
  const { t } = useTranslation();
  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };

  const C = colors || { primary: 'var(--app-primary)', text: 'var(--app-text)', textSec: 'var(--app-text-sec)', textMuted: 'var(--app-text-muted)', border: 'var(--app-border)', card: 'var(--app-card-bg)', bg: 'var(--app-bg)', success: 'var(--app-success)', error: 'var(--app-error)' };
  const [data, setData] = useState<Availability | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState('');
  const [msg, setMsg] = useState('');

  const load = useCallback(async () => {
    setLoading(true); setErr('');
    try {
      const { data } = await api.get('/careers/scheduling/my-availability');
      setData(data?.availability || null);
    } catch (e: any) {
      setErr(e?.response?.data?.detail || e?.message || 'Failed to load availability');
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const toggleDay = (wd: number) => {
    if (!data) return;
    const existing = data.windows.find((w) => w.weekday === wd);
    if (existing) {
      setData({ ...data, windows: data.windows.filter((w) => w.weekday !== wd) });
    } else {
      const any = data.windows[0];
      setData({ ...data, windows: [...data.windows, { weekday: wd, start: any?.start || '09:00', end: any?.end || '17:00' }] });
    }
  };

  const updateWindow = (wd: number, field: 'start' | 'end', value: string) => {
    if (!data) return;
    setData({
      ...data,
      windows: data.windows.map((w) => w.weekday === wd ? { ...w, [field]: value } : w),
    });
  };

  const save = async () => {
    if (!data) return;
    setSaving(true); setErr(''); setMsg('');
    try {
      await api.put('/careers/scheduling/my-availability', {
        tz: data.tz,
        windows: data.windows,
        slot_minutes: data.slot_minutes,
        buffer_minutes: data.buffer_minutes,
        max_per_day: data.max_per_day,
      });
      setMsg('Availability saved — applies to the next scheduling invite.');
    } catch (e: any) {
      setErr(e?.response?.data?.detail || e?.message || 'Save failed');
    } finally { setSaving(false); }
  };

  if (loading || !data) {
    return (
      <View style={{ padding: 14, backgroundColor: C.card, borderRadius: 10, borderColor: C.border, borderWidth: 1 }}>
        <ActivityIndicator color={C.primary} />
      </View>
    );
  }

  const daysWithWindow = new Set(data.windows.map((w) => w.weekday));

  return (
    <View
      style={{ padding: 14, backgroundColor: C.card, borderRadius: 12, borderColor: C.border, borderWidth: 1, marginBottom: 12 }}
      data-testid="careers-scheduling-availability-card" testID="careers-scheduling-availability-card"
    >
      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
        <Text style={{ color: C.text, fontSize: 14, fontWeight: '800' }}>
          <Ionicons name="calendar-outline" size={14} color={C.primary} /> My interview availability
        </Text>
        <TouchableOpacity
          onPress={load}
          style={{ paddingHorizontal: 8, paddingVertical: 4 }}
          data-testid="careers-scheduling-availability-refresh" testID="careers-scheduling-availability-refresh"
        >
          <Ionicons name="refresh" size={13} color={C.textSec} />
        </TouchableOpacity>
      </View>

      <Text style={{ color: C.textMuted, fontSize: 10, marginBottom: 10 }}>{tx('admin.careerSchedulingAvailability.auto.text.001', 'Applicants see these slots translated to their local time. Change takes effect on the next invite.')}</Text>

      {/* TZ picker */}
      <Text style={{ color: C.textSec, fontSize: 11, fontWeight: '700', marginBottom: 4 }}>{tx('admin.careerSchedulingAvailability.auto.text.002', 'Your time zone')}</Text>
      {Platform.OS === 'web' ? (
        <select
          value={data.tz}
          onChange={(e: any) => setData({ ...data, tz: e.target.value })}
          data-testid="careers-scheduling-availability-tz"
          style={{
            width: '100%', padding: 8, borderRadius: 8, border: `1px solid ${C.border}`,
            background: C.bg, color: C.text, fontSize: 13, marginBottom: 10,
          } as any}
        >
          {COMMON_TZS.map((t) => (<option key={t} value={t}>{t}</option>))}
          {!COMMON_TZS.includes(data.tz) ? <option value={data.tz}>{data.tz}</option> : null}
        </select>
      ) : (
        <TextInput
          value={data.tz}
          onChangeText={(v) => setData({ ...data, tz: v })}
          placeholder={tx('admin.careerSchedulingAvailability.auto.placeholder.001', 'IANA tz e.g. Africa/Porto-Novo')}
          style={{ borderWidth: 1, borderColor: C.border, borderRadius: 8, padding: 8, fontSize: 13, color: C.text, marginBottom: 10 }}
          data-testid="careers-scheduling-availability-tz" testID="careers-scheduling-availability-tz"
        />
      )}

      {/* Per-day windows */}
      <Text style={{ color: C.textSec, fontSize: 11, fontWeight: '700', marginBottom: 6 }}>{tx('admin.careerSchedulingAvailability.auto.text.003', 'Weekly windows')}</Text>
      {WEEKDAYS.map((dayLabel, i) => {
        const hasWindow = daysWithWindow.has(i);
        const win = data.windows.find((w) => w.weekday === i);
        return (
          <View key={i} style={{ flexDirection: 'row', alignItems: 'center', marginBottom: 6 }}>
            <TouchableOpacity
              onPress={() => toggleDay(i)}
              style={{ width: 58, paddingVertical: 6, paddingHorizontal: 8, borderRadius: 8, backgroundColor: hasWindow ? C.primary : C.bg, borderColor: hasWindow ? C.primary : C.border, borderWidth: 1 }}
              data-testid={`careers-scheduling-day-toggle-${i}`} testID={`careers-scheduling-day-toggle-${i}`}
            >
              <Text style={{ color: hasWindow ? 'var(--app-primary-text)' : C.textSec, fontSize: 11, fontWeight: '700', textAlign: 'center' }}>{dayLabel}</Text>
            </TouchableOpacity>
            {hasWindow && win ? (
              <View style={{ flexDirection: 'row', alignItems: 'center', marginLeft: 8, gap: 6 }}>
                <TextInput
                  value={win.start}
                  onChangeText={(v) => updateWindow(i, 'start', v)}
                  placeholder="09:00"
                  style={{ borderWidth: 1, borderColor: C.border, borderRadius: 6, paddingHorizontal: 6, paddingVertical: 4, fontSize: 12, color: C.text, width: 60 }}
                  data-testid={`careers-scheduling-day-start-${i}`} testID={`careers-scheduling-day-start-${i}`}
                />
                <Text style={{ color: C.textMuted, fontSize: 11 }}>–</Text>
                <TextInput
                  value={win.end}
                  onChangeText={(v) => updateWindow(i, 'end', v)}
                  placeholder="17:00"
                  style={{ borderWidth: 1, borderColor: C.border, borderRadius: 6, paddingHorizontal: 6, paddingVertical: 4, fontSize: 12, color: C.text, width: 60 }}
                  data-testid={`careers-scheduling-day-end-${i}`} testID={`careers-scheduling-day-end-${i}`}
                />
              </View>
            ) : (
              <Text style={{ color: C.textMuted, fontSize: 10, marginLeft: 10 }}>{tx('admin.careerSchedulingAvailability.auto.text.004', 'off')}</Text>
            )}
          </View>
        );
      })}

      {/* Slot length + buffer + max */}
      <View style={{ flexDirection: 'row', gap: 8, marginTop: 10 }}>
        <View style={{ flex: 1 }}>
          <Text style={{ color: C.textSec, fontSize: 10, marginBottom: 2 }}>{tx('admin.careerSchedulingAvailability.auto.text.005', 'Slot (min)')}</Text>
          <TextInput accessibilityLabel={tx('admin.careerSchedulingAvailability.auto.accessibility.001', 'Text input')}
            value={String(data.slot_minutes)}
            onChangeText={(v) => setData({ ...data, slot_minutes: parseInt(v || '0', 10) || 0 })}
            keyboardType="numeric"
            style={{ borderWidth: 1, borderColor: C.border, borderRadius: 6, padding: 6, fontSize: 12, color: C.text }}
            data-testid="careers-scheduling-availability-slot-minutes" testID="careers-scheduling-availability-slot-minutes"
          />
        </View>
        <View style={{ flex: 1 }}>
          <Text style={{ color: C.textSec, fontSize: 10, marginBottom: 2 }}>{tx('admin.careerSchedulingAvailability.auto.text.006', 'Buffer (min)')}</Text>
          <TextInput accessibilityLabel={tx('admin.careerSchedulingAvailability.auto.accessibility.002', 'Text input')}
            value={String(data.buffer_minutes)}
            onChangeText={(v) => setData({ ...data, buffer_minutes: parseInt(v || '0', 10) || 0 })}
            keyboardType="numeric"
            style={{ borderWidth: 1, borderColor: C.border, borderRadius: 6, padding: 6, fontSize: 12, color: C.text }}
            data-testid="careers-scheduling-availability-buffer-minutes" testID="careers-scheduling-availability-buffer-minutes"
          />
        </View>
        <View style={{ flex: 1 }}>
          <Text style={{ color: C.textSec, fontSize: 10, marginBottom: 2 }}>{tx('admin.careerSchedulingAvailability.auto.text.007', 'Max/day')}</Text>
          <TextInput accessibilityLabel={tx('admin.careerSchedulingAvailability.auto.accessibility.003', 'Text input')}
            value={String(data.max_per_day)}
            onChangeText={(v) => setData({ ...data, max_per_day: parseInt(v || '0', 10) || 0 })}
            keyboardType="numeric"
            style={{ borderWidth: 1, borderColor: C.border, borderRadius: 6, padding: 6, fontSize: 12, color: C.text }}
            data-testid="careers-scheduling-availability-max-per-day" testID="careers-scheduling-availability-max-per-day"
          />
        </View>
      </View>

      {msg ? <Text style={{ color: C.success, fontSize: 11, marginTop: 8 }}>{msg}</Text> : null}
      {err ? <Text style={{ color: C.error, fontSize: 11, marginTop: 8 }}>{err}</Text> : null}

      <TouchableOpacity
        disabled={saving}
        onPress={save}
        style={{ marginTop: 12, backgroundColor: C.primary, paddingVertical: 10, borderRadius: 8, alignItems: 'center', opacity: saving ? 0.6 : 1 }}
        data-testid="careers-scheduling-availability-save" testID="careers-scheduling-availability-save"
      >
        <Text style={{ color: 'var(--app-primary-text)', fontSize: 12, fontWeight: '800' }}>{saving ? 'Saving…' : 'Save availability'}</Text>{/* @theme-ok: white on primary button */}
      </TouchableOpacity>
    </View>
  );
}
