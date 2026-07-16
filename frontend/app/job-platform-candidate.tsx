import React, { useEffect, useState } from 'react';
import { ScrollView, Text, View, TouchableOpacity } from 'react-native';
import AppShell from '../src/components/AppShell';
import { useTheme } from '../src/context/ThemeContext';
import { JobCandidatesPortalTab } from '../src/components/jobs/JobCandidatesPortalTab';
import { useTranslation } from '../src/hooks/useTranslation';
import api from '../src/services/api';

type ActionCenter = {
  streak_days: number;
  momentum_score: number;
  summary: {
    applications: number;
    interviews: number;
    saved_jobs: number;
    recommendations: number;
  };
  next_actions: {
    action_key: string;
    label: string;
    description: string;
    completed: boolean;
  }[];
};

export default function JobPlatformCandidateRoute() {
  const { colors } = useTheme();
  const { tx } = useTranslation();
  const copy = (key: string, fallback: string) => {
    const value = tx(key, fallback);
    return value === key ? fallback : value;
  };
  const [commercialMsg, setCommercialMsg] = useState('');
  const [loadingKey, setLoadingKey] = useState('');
  const [actionCenter, setActionCenter] = useState<ActionCenter | null>(null);

  const loadActionCenter = async () => {
    try {
      const response = await api.get('/hiring/v2/candidate/action-center', { skipDedupe: true });
      setActionCenter(response?.data || null);
    } catch {
      setActionCenter(null);
    }
  };

  useEffect(() => {
    void loadActionCenter();
  }, []);

  const momentumLabel = !actionCenter
    ? copy('jobsPortal.candidate.momentumUnknown', 'Momentum unavailable')
    : actionCenter.momentum_score >= 80
      ? copy('jobsPortal.candidate.momentumHot', 'High hiring momentum')
      : actionCenter.momentum_score >= 45
        ? copy('jobsPortal.candidate.momentumWarm', 'Growing hiring momentum')
        : copy('jobsPortal.candidate.momentumCold', 'Kickstart your momentum');

  const completeAction = async (actionKey: string) => {
    setLoadingKey(`mission-${actionKey}`);
    try {
      await api.post('/hiring/v2/candidate/action-center/complete', { action_key: actionKey });
      await loadActionCenter();
      setCommercialMsg(copy('jobsPortal.candidate.missionSaved', 'Action logged. Momentum updated.'));
    } catch {
      setCommercialMsg(copy('jobsPortal.candidate.missionSaveFailed', 'Could not update mission state right now.'));
    } finally {
      setLoadingKey('');
    }
  };

  const activateBoost = async () => {
    setLoadingKey('boost');
    try {
      await api.post('/hiring/v2/candidate/boost-profile', { boost_hours: 72 });
      setCommercialMsg(copy('jobsPortal.commercial.boostSuccess', 'Boosted profile activated for 72 hours.'));
    } catch (error: any) {
      setCommercialMsg(error?.response?.data?.detail || copy('jobsPortal.commercial.boostRequiresPlan', 'Boosted profile requires Basic/Premium plan.'));
    } finally {
      setLoadingKey('');
    }
  };

  const priorityApplyDemo = async () => {
    setLoadingKey('priority');
    try {
      await api.post('/hiring/v2/candidate/priority-apply/demo-priority-application');
      setCommercialMsg(copy('jobsPortal.commercial.prioritySuccess', 'Priority apply activated. Recruiters will see your profile first.'));
    } catch (error: any) {
      setCommercialMsg(error?.response?.data?.detail || copy('jobsPortal.commercial.priorityRequiresPlan', 'Priority apply requires Basic/Premium plan.'));
    } finally {
      setLoadingKey('');
    }
  };

  return (
    <AppShell>
      <View style={{ flex: 1, backgroundColor: colors.bg }} data-testid="job-platform-candidate-route" testID="job-platform-candidate-route">
        <ScrollView contentContainerStyle={{ padding: 16, paddingBottom: 36 }}>
          <View style={{ maxWidth: 1240, width: '100%', alignSelf: 'center', gap: 12 }}>
            <View style={{ borderRadius: 16, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bgSoft, padding: 14 }}>
              <Text style={{ color: colors.text, fontSize: 22, fontWeight: '900' }} data-testid="job-platform-candidate-title" testID="job-platform-candidate-title">{copy('jobsPortal.candidate.workspaceTitle', 'Candidate Workspace')}</Text>
              <Text style={{ color: colors.textMuted, marginTop: 6, fontSize: 12 }}>{copy('jobsPortal.candidate.workspaceSubtitle', 'Dedicated Feature 26 module for candidate-side applications, tracking, and alerts.')}</Text>
            </View>

            <View style={{ borderRadius: 14, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, padding: 12 }} data-testid="job-platform-candidate-action-center" testID="job-platform-candidate-action-center">
              <Text style={{ color: colors.text, fontSize: 15, fontWeight: '800' }} data-testid="job-platform-candidate-action-center-title" testID="job-platform-candidate-action-center-title">
                {copy('jobsPortal.candidate.actionCenterTitle', 'Daily Action Center')}
              </Text>
              <Text style={{ color: colors.textMuted, marginTop: 4, fontSize: 12 }}>
                {copy('jobsPortal.candidate.actionCenterSubtitle', 'Build daily consistency to climb recruiter queues faster.')}
              </Text>

              <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10, marginTop: 10 }}>
                <View style={{ borderRadius: 10, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bgSoft, paddingHorizontal: 10, paddingVertical: 8 }} data-testid="job-platform-candidate-streak-chip" testID="job-platform-candidate-streak-chip">
                  <Text style={{ color: colors.textMuted, fontSize: 10, fontWeight: '700' }}>{copy('jobsPortal.candidate.streakLabel', 'Streak')}</Text>
                  <Text style={{ color: colors.text, fontSize: 16, fontWeight: '900' }}>{actionCenter?.streak_days ?? 0} {copy('jobsPortal.candidate.days', 'days')}</Text>
                </View>
                <View style={{ borderRadius: 10, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bgSoft, paddingHorizontal: 10, paddingVertical: 8 }} data-testid="job-platform-candidate-momentum-chip" testID="job-platform-candidate-momentum-chip">
                  <Text style={{ color: colors.textMuted, fontSize: 10, fontWeight: '700' }}>{copy('jobsPortal.candidate.momentumLabel', 'Momentum')}</Text>
                  <Text style={{ color: colors.text, fontSize: 16, fontWeight: '900' }}>{actionCenter?.momentum_score ?? 0}/100</Text>
                </View>
              </View>

              <Text style={{ color: colors.primary, fontSize: 12, fontWeight: '700', marginTop: 10 }} data-testid="job-platform-candidate-momentum-label" testID="job-platform-candidate-momentum-label">
                {momentumLabel}
              </Text>

              <View style={{ marginTop: 10, gap: 8 }}>
                {(actionCenter?.next_actions || []).map((action, index) => (
                  <View key={action.action_key} style={{ borderRadius: 10, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bgSoft, padding: 10 }} data-testid={`job-platform-candidate-action-item-${index}`} testID={`job-platform-candidate-action-item-${index}`}>
                    <Text style={{ color: colors.text, fontSize: 13, fontWeight: '800' }}>{action.label}</Text>
                    <Text style={{ color: colors.textMuted, marginTop: 2, fontSize: 11 }}>{action.description}</Text>
                    <TouchableOpacity
                      onPress={() => completeAction(action.action_key)}
                      disabled={Boolean(action.completed)}
                      data-testid={`job-platform-candidate-action-complete-${action.action_key}`}
                      testID={`job-platform-candidate-action-complete-${action.action_key}`}
                      style={{
                        marginTop: 8,
                        borderRadius: 8,
                        borderWidth: 1,
                        borderColor: action.completed ? colors.success : colors.primary,
                        backgroundColor: action.completed ? `${colors.success}20` : `${colors.primary}16`,
                        paddingVertical: 7,
                        paddingHorizontal: 10,
                        alignSelf: 'flex-start',
                      }}
                    >
                      <Text style={{ color: action.completed ? colors.success : colors.primary, fontSize: 11, fontWeight: '800' }}>
                        {action.completed
                          ? copy('jobsPortal.candidate.actionDone', 'Completed')
                          : loadingKey === `mission-${action.action_key}`
                            ? copy('jobsPortal.candidate.actionSaving', 'Saving...')
                            : copy('jobsPortal.candidate.actionMarkDone', 'Mark done')}
                      </Text>
                    </TouchableOpacity>
                  </View>
                ))}
              </View>
            </View>

            <View style={{ borderRadius: 14, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bgSoft, padding: 12 }} data-testid="job-platform-candidate-commercial-panel" testID="job-platform-candidate-commercial-panel">
              <Text style={{ color: colors.text, fontSize: 15, fontWeight: '800' }}>{copy('jobsPortal.candidate.commercialTitle', 'Commercial acceleration tools')}</Text>
              <Text style={{ color: colors.textMuted, marginTop: 4, fontSize: 12 }}>
                {copy('jobsPortal.candidate.commercialSubtitle', 'Premium candidates win faster with Priority Apply and Boosted Profile visibility.')}
              </Text>
              <View style={{ flexDirection: 'row', gap: 10, marginTop: 10, flexWrap: 'wrap' }}>
                <TouchableOpacity
                  onPress={priorityApplyDemo}
                  data-testid="job-platform-candidate-priority-apply-btn"
                  testID="job-platform-candidate-priority-apply-btn"
                  style={{ backgroundColor: colors.primary, borderRadius: 10, paddingHorizontal: 14, paddingVertical: 10 }}
                >
                  <Text style={{ color: colors.primaryText, fontSize: 12, fontWeight: '800' }}>{loadingKey === 'priority' ? copy('jobsPortal.candidate.activating', 'Activating...') : copy('jobsPortal.candidate.priorityApplyLabel', 'Priority Apply')}</Text>
                </TouchableOpacity>
                <TouchableOpacity
                  onPress={activateBoost}
                  data-testid="job-platform-candidate-boost-btn"
                  testID="job-platform-candidate-boost-btn"
                  style={{ backgroundColor: colors.info, borderRadius: 10, paddingHorizontal: 14, paddingVertical: 10 }}
                >
                  <Text style={{ color: colors.primaryText, fontSize: 12, fontWeight: '800' }}>{loadingKey === 'boost' ? copy('jobsPortal.candidate.activating', 'Activating...') : copy('jobsPortal.candidate.boostLabel', 'Boost Profile (72h)')}</Text>
                </TouchableOpacity>
              </View>
              {!!commercialMsg && (
                <Text style={{ color: colors.primary, marginTop: 10, fontSize: 12 }} data-testid="job-platform-candidate-commercial-msg" testID="job-platform-candidate-commercial-msg">{commercialMsg}</Text>
              )}
            </View>

            <JobCandidatesPortalTab />
          </View>
        </ScrollView>
      </View>
    </AppShell>
  );
}
