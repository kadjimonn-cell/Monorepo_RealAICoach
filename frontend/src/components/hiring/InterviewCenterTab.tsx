// eslint-disable-next-line @typescript-eslint/no-unused-vars
import React, { useState } from 'react';
import { View, Text, TouchableOpacity } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { useLiveQuery } from '../../hooks/useLiveQuery';
import { HColors, Badge } from './shared';

interface Props { C: HColors; isEmployer: boolean; onShowSummary: (id: string) => void; onShowRate: (id: string) => void; onJoinRoom: (id: string) => void; }

export function InterviewCenterTab({ C, isEmployer, onShowSummary, onShowRate, onJoinRoom }: Props) {
  const { data: interviewData, refetch: load } = useLiveQuery(
    `/interviews/my?role=${isEmployer ? 'employer' : 'candidate'}`,
    { entity: 'interviews', pollInterval: 30000, deps: [isEmployer] }
  );
  const myInterviews = interviewData?.interviews || [];

  const statusColor = (s: string) => {
    const map: Record<string, string> = { scheduled: C.primary, confirmed: C.success, completed: C.accent, cancelled: C.error, rescheduled: C.warning, in_progress: C.success };
    return map[s] || C.muted;
  };

  return (
    <View data-testid="interview-center" testID="interview-center">
      {myInterviews.length === 0 ? (
        <View style={{ backgroundColor: C.card, borderRadius: 12, padding: 24, alignItems: 'center', borderWidth: 1, borderColor: C.border }}>
          <Ionicons name="videocam-outline" size={40} color={C.muted} />
          <Text style={{ color: C.muted, fontSize: 14, marginTop: 12, textAlign: 'center' }}>No interviews scheduled yet</Text>
        </View>
      ) : (
        myInterviews.map((intv, i) => (
          <View key={intv.interview_id} data-testid={`interview-card-${i}`} testID={`interview-card-${i}`} style={{
            backgroundColor: C.card, borderRadius: 12, padding: 14, marginBottom: 10,
            borderWidth: 1, borderColor: C.border, borderLeftWidth: 3, borderLeftColor: statusColor(intv.status),
          }}>
            <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start' }}>
              <View style={{ flex: 1 }}>
                <Text style={{ color: C.text, fontSize: 15, fontWeight: '600' }}>{intv.job_title}</Text>
                <Text style={{ color: C.muted, fontSize: 12 }}>{intv.company_name}</Text>
                <Text style={{ color: C.muted, fontSize: 12, marginTop: 4 }}>
                  {isEmployer ? `Candidate: ${intv.candidate_name}` : `Interviewer: ${intv.interviewer_name}`}
                </Text>
              </View>
              <Badge label={intv.status} color={statusColor(intv.status)} bg={statusColor(intv.status) + '22'} />
            </View>
            <View style={{ flexDirection: 'row', gap: 12, marginTop: 8, flexWrap: 'wrap' }}>
              <View style={{ flexDirection: 'row', alignItems: 'center' }}>
                <Ionicons name="calendar-outline" size={14} color={C.muted} />
                <Text style={{ color: C.text, fontSize: 12, marginLeft: 4 }}>{intv.scheduled_start?.slice(0, 10)}</Text>
              </View>
              <View style={{ flexDirection: 'row', alignItems: 'center' }}>
                <Ionicons name="time-outline" size={14} color={C.muted} />
                <Text style={{ color: C.text, fontSize: 12, marginLeft: 4 }}>{intv.scheduled_start?.slice(11, 16)}</Text>
              </View>
              <Badge label={intv.interview_type} color={C.primary} bg={C.primary + '22'} />
              <Text style={{ color: C.muted, fontSize: 12 }}>{intv.duration_minutes}min</Text>
            </View>
            {intv.meeting_link && intv.status !== 'cancelled' && (
              <TouchableOpacity data-testid={`join-interview-${intv.interview_id}`} testID={`join-interview-${intv.interview_id}`}
                onPress={() => onJoinRoom(intv.interview_id)}
                style={{ marginTop: 8, padding: 10, backgroundColor: C.accent, borderRadius: 8, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6 }}>
                <Ionicons name="videocam" size={16} color={C.primaryText || C.text} />
                <Text style={{ color: C.primaryText || C.text, fontSize: 13, fontWeight: '600' }}>Join Interview Room</Text>
              </TouchableOpacity>
            )}
            {intv.notes && <Text style={{ color: C.muted, fontSize: 12, marginTop: 6, fontStyle: 'italic' }}>Notes: {intv.notes}</Text>}
            {intv.feedback && (
              <View style={{ marginTop: 8, padding: 8, backgroundColor: (globalThis as any).__alphaColor(C.success, '15'), borderRadius: 8 }}>
                <Text style={{ color: C.successText, fontSize: 12, fontWeight: '600' }}>Rating: {intv.feedback.overall_rating}/5 | Recommendation: {intv.feedback.recommendation}</Text>
              </View>
            )}
            {intv.status === 'completed' && (
              <View style={{ flexDirection: 'row', gap: 6, marginTop: 8 }}>
                <TouchableOpacity data-testid={`summary-btn-${intv.interview_id}`} testID={`summary-btn-${intv.interview_id}`} onPress={() => onShowSummary(intv.interview_id)}
                  style={{ flex: 1, padding: 8, borderRadius: 8, backgroundColor: (globalThis as any).__alphaColor(C.primary, '22'), borderWidth: 1, borderColor: (globalThis as any).__alphaColor(C.primary, '44'), flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 4 }}>
                  <Ionicons name="sparkles" size={14} color={C.primary} />
                  <Text style={{ color: C.primary, fontSize: 11, fontWeight: '600' }}>AI Summary</Text>
                </TouchableOpacity>
                {!isEmployer && (
                  <TouchableOpacity data-testid={`rate-exp-btn-${intv.interview_id}`} testID={`rate-exp-btn-${intv.interview_id}`} onPress={() => onShowRate(intv.interview_id)}
                    style={{ flex: 1, padding: 8, borderRadius: 8, backgroundColor: (globalThis as any).__alphaColor(C.warning, '22'), borderWidth: 1, borderColor: (globalThis as any).__alphaColor(C.warning, '44'), flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 4 }}>
                    <Ionicons name="star" size={14} color={C.warning} />
                    <Text style={{ color: C.warning, fontSize: 11, fontWeight: '600' }}>Rate Experience</Text>
                  </TouchableOpacity>
                )}
              </View>
            )}
            {!isEmployer && intv.status === 'scheduled' && (
              <View style={{ flexDirection: 'row', gap: 8, marginTop: 10 }}>
                <TouchableOpacity data-testid={`accept-intv-${intv.interview_id}`} testID={`accept-intv-${intv.interview_id}`}
                  onPress={async () => { await api.post(`/interviews/${intv.interview_id}/accept`); load(); }}
                  style={{ flex: 1, padding: 10, borderRadius: 8, backgroundColor: C.success, alignItems: 'center' }}>
                  <Text style={{ color: C.primaryText || C.text, fontSize: 13, fontWeight: '600' }}>Accept</Text>
                </TouchableOpacity>
                <TouchableOpacity data-testid={`decline-intv-${intv.interview_id}`} testID={`decline-intv-${intv.interview_id}`}
                  onPress={async () => { await api.post(`/interviews/${intv.interview_id}/decline`, {}); load(); }}
                  style={{ flex: 1, padding: 10, borderRadius: 8, backgroundColor: C.error, alignItems: 'center' }}>
                  <Text style={{ color: C.primaryText || C.text, fontSize: 13, fontWeight: '600' }}>Decline</Text>
                </TouchableOpacity>
              </View>
            )}
            {isEmployer && intv.status !== 'cancelled' && intv.status !== 'completed' && (
              <View style={{ flexDirection: 'row', gap: 8, marginTop: 10 }}>
                <TouchableOpacity data-testid={`complete-intv-${intv.interview_id}`} testID={`complete-intv-${intv.interview_id}`}
                  onPress={async () => { await api.post(`/interviews/${intv.interview_id}/complete`); load(); }}
                  style={{ flex: 1, padding: 10, borderRadius: 8, backgroundColor: C.success, alignItems: 'center' }}>
                  <Text style={{ color: C.primaryText || C.text, fontSize: 12, fontWeight: '600' }}>Complete</Text>
                </TouchableOpacity>
                <TouchableOpacity data-testid={`cancel-intv-${intv.interview_id}`} testID={`cancel-intv-${intv.interview_id}`}
                  onPress={async () => { await api.post(`/interviews/${intv.interview_id}/cancel`, {}); load(); }}
                  style={{ flex: 1, padding: 10, borderRadius: 8, backgroundColor: C.error, alignItems: 'center' }}>
                  <Text style={{ color: C.primaryText || C.text, fontSize: 12, fontWeight: '600' }}>Cancel</Text>
                </TouchableOpacity>
              </View>
            )}
          </View>
        ))
      )}
    </View>
  );
}

/* i18n-probe t('i18n.auto.probe') */
