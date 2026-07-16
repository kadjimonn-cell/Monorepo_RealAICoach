import React, { useState } from 'react';
import { View, Text, ScrollView, TouchableOpacity, TextInput, ActivityIndicator } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useAuth } from '../../context/AuthContext';
import api from '../../services/api';
import { HColors } from './shared';
import { handleAppRecoverableError } from '../../utils/appRecoverableError';

interface Props { C: HColors; myJobs: any[]; selectedJobId: string; onSelectJob: (id: string) => void; onSwitchToInterviews: () => void; }

export function SchedulerTab({ C, myJobs, selectedJobId, onSelectJob, onSwitchToInterviews }: Props) {
  const { user } = useAuth();
  const [suggestedSlots, setSuggestedSlots] = useState<any[]>([]);
  const [slotLoading, setSlotLoading] = useState(false);
  const [schedCandidateId, setSchedCandidateId] = useState('');

  const loadSmartSlots = async () => {
    if (!schedCandidateId || !selectedJobId) return;
    setSlotLoading(true);
    try {
      const res = await api.post('/smart-scheduler/suggest-slots', {
        candidate_id: schedCandidateId,
        employer_id: (user as any)?.user_id,
        duration_minutes: 45,
        days_ahead: 7,
      });
      setSuggestedSlots(res.data?.slots || []);
    } catch (error) { handleAppRecoverableError({ scope: 'src/components/hiring/SchedulerTab.tsx#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
    setSlotLoading(false);
  };

  const quickSchedule = async (slot: any) => {
    try {
      await api.post('/smart-scheduler/quick-schedule', {
        candidate_id: schedCandidateId,
        job_id: selectedJobId,
        start: slot.start,
        end: slot.end,
        interview_type: 'video',
        notes: 'Scheduled via AI Smart Scheduler',
      });
      setSuggestedSlots([]);
      onSwitchToInterviews();
    } catch (error) { handleAppRecoverableError({ scope: 'src/components/hiring/SchedulerTab.tsx#catch2', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
  };

  const JobSelector = () => (
    <ScrollView data-testid="job-selector" testID="job-selector" horizontal showsHorizontalScrollIndicator={false} style={{ marginBottom: 12 }}>
      {myJobs.map(j => (
        <TouchableOpacity key={j.job_id} data-testid={`job-select-${j.job_id}`} testID={`job-select-${j.job_id}`}
          onPress={() => onSelectJob(j.job_id)}
          style={{
            paddingHorizontal: 12, paddingVertical: 6, borderRadius: 16, marginRight: 8,
            backgroundColor: selectedJobId === j.job_id ? C.primary : C.card,
            borderWidth: 1, borderColor: selectedJobId === j.job_id ? C.primary : C.border,
          }}>
          <Text style={{ color: selectedJobId === j.job_id ? C.primaryText : C.text, fontSize: 12, fontWeight: '500' }}>
            {j.title} ({j.applications_count || 0})
          </Text>
        </TouchableOpacity>
      ))}
    </ScrollView>
  );

  return (
    <View data-testid="scheduler-tab" testID="scheduler-tab">
      <View style={{ backgroundColor: C.card, borderRadius: 12, padding: 16, marginBottom: 16, borderWidth: 1, borderColor: C.border }}>
        <Text style={{ color: C.text, fontSize: 16, fontWeight: '700', marginBottom: 12 }}>AI Smart Scheduler</Text>
        <Text style={{ color: C.muted, fontSize: 13, marginBottom: 12 }}>Auto-detect availability and find optimal interview slots</Text>
        <JobSelector />
        <TextInput data-testid="sched-candidate-id" testID="sched-candidate-id" placeholder="Candidate user ID" placeholderTextColor={C.muted}
          value={schedCandidateId} onChangeText={setSchedCandidateId}
          style={{ backgroundColor: C.bgSoft, borderRadius: 8, padding: 12, marginBottom: 8, color: C.text, borderWidth: 1, borderColor: C.border }} />
        <TouchableOpacity data-testid="find-slots-btn" testID="find-slots-btn" onPress={loadSmartSlots}
          disabled={!schedCandidateId || !selectedJobId || slotLoading}
          style={{
            padding: 14, borderRadius: 12, backgroundColor: !schedCandidateId || !selectedJobId ? C.border : C.accent,
            alignItems: 'center', flexDirection: 'row', justifyContent: 'center', gap: 8,
          }}>
          <Ionicons name="flash" size={18} color={C.primaryText} />
          <Text style={{ color: C.primaryText, fontSize: 14, fontWeight: '600' }}>{slotLoading ? 'Finding Slots...' : 'Find Optimal Slots'}</Text>
        </TouchableOpacity>
      </View>
      {slotLoading && (
        <View style={{ alignItems: 'center', paddingVertical: 30 }}>
          <ActivityIndicator size="large" color={C.accent} />
          <Text style={{ color: C.muted, marginTop: 12 }}>AI is analyzing calendars...</Text>
        </View>
      )}
      {suggestedSlots.length > 0 && (
        <View>
          <Text style={{ color: C.text, fontSize: 15, fontWeight: '700', marginBottom: 10 }}>Suggested Slots ({suggestedSlots.length})</Text>
          {suggestedSlots.map((slot, i) => (
            <View key={i} data-testid={`slot-card-${i}`} testID={`slot-card-${i}`} style={{
              backgroundColor: C.card, borderRadius: 12, padding: 14, marginBottom: 8,
              borderWidth: 1, borderColor: slot.ai_recommended ? C.accent : C.border,
              borderLeftWidth: 3, borderLeftColor: slot.ai_recommended ? C.success : C.border,
            }}>
              <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
                <View>
                  <Text style={{ color: C.text, fontSize: 14, fontWeight: '600' }}>{slot.day_name}, {slot.date}</Text>
                  <Text style={{ color: C.muted, fontSize: 13 }}>{slot.time} UTC ({slot.duration_minutes}min)</Text>
                </View>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                  {slot.ai_recommended && (
                    <View style={{ backgroundColor: (globalThis as any).__alphaColor(C.success, '22'), paddingHorizontal: 6, paddingVertical: 2, borderRadius: 6 }}>
                      <Text style={{ color: C.successText, fontSize: 10, fontWeight: '700' }}>AI PICK</Text>
                    </View>
                  )}
                  <Text style={{ color: C.muted, fontSize: 11 }}>#{slot.rank}</Text>
                </View>
              </View>
              <TouchableOpacity data-testid={`quick-schedule-${i}`} testID={`quick-schedule-${i}`} onPress={() => quickSchedule(slot)}
                style={{ marginTop: 10, padding: 10, borderRadius: 8, backgroundColor: C.accent, alignItems: 'center', flexDirection: 'row', justifyContent: 'center', gap: 6 }}>
                <Ionicons name="checkmark-circle" size={16} color={C.primaryText} />
                <Text style={{ color: C.primaryText, fontSize: 13, fontWeight: '600' }}>Schedule This Slot</Text>
              </TouchableOpacity>
            </View>
          ))}
        </View>
      )}
    </View>
  );
}

/* i18n-probe t('i18n.auto.probe') */
