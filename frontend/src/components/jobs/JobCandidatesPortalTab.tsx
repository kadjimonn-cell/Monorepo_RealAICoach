import React, { useCallback, useEffect, useRef, useState } from 'react';
import { View, Text, ScrollView, TouchableOpacity, ActivityIndicator } from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { useTheme } from '../../context/ThemeContext';

type CandidateSnapshot = {
  totalApplications: number;
  responseRate: number;
  interviewRate: number;
  resumeScore: number;
  unreadAlerts: number;
  savedJobs: number;
  statusBreakdown: Record<string, number>;
  recentApplications: any[];
  recommendations: any[];
};

const STATUS_ORDER = ['applied', 'viewed', 'interview', 'offer', 'rejected'];

type JobCandidatesPortalTabProps = {
  funnelFocusStage?: 'applications' | 'interviews' | 'offers' | null;
  focusSignal?: number;
};

export const JobCandidatesPortalTab = ({ funnelFocusStage = null, focusSignal = 0 }: JobCandidatesPortalTabProps) => {
  const router = useRouter();
  const { colors } = useTheme();
  const scrollRef = useRef<ScrollView>(null);
  const [loading, setLoading] = useState(true);
  const [snapshot, setSnapshot] = useState<CandidateSnapshot>({
    totalApplications: 0,
    responseRate: 0,
    interviewRate: 0,
    resumeScore: 0,
    unreadAlerts: 0,
    savedJobs: 0,
    statusBreakdown: {},
    recentApplications: [],
    recommendations: [],
  });
  const [statusTrackerY, setStatusTrackerY] = useState(0);
  const [recentApplicationsY, setRecentApplicationsY] = useState(0);
  const [focusTarget, setFocusTarget] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [analyticsRes, appsRes, resumeRes, dashboardRes, savedRes, recRes] = await Promise.all([
        api.get('/jobs/analytics').catch(() => ({ data: {} })),
        api.get('/jobs/my-applications?status=all').catch(() => ({ data: { applications: [], stats: {} } })),
        api.get('/jobs/resume/score').catch(() => ({ data: {} })),
        api.get('/aris/dashboard/candidate').catch(() => ({ data: {} })),
        api.get('/jobs/saved').catch(() => ({ data: { total: 0 } })),
        api.get('/jobs/recommendations').catch(() => ({ data: { jobs: [] } })),
      ]);

      const analytics = analyticsRes.data || {};
      const appsPayload = appsRes.data || {};
      const resumePayload = resumeRes.data || {};
      const aris = dashboardRes.data || {};

      setSnapshot({
        totalApplications: analytics.total_applications || aris.total_applications || appsPayload.total || 0,
        responseRate: analytics.response_rate || 0,
        interviewRate: analytics.interview_rate || aris.interview_rate || 0,
        resumeScore: resumePayload.score || analytics.resume_score || aris.resume_score || 0,
        unreadAlerts: aris.unread_alerts || 0,
        savedJobs: savedRes.data?.total || aris.saved_jobs || 0,
        statusBreakdown: appsPayload.stats || analytics.status_breakdown || aris.application_statuses || {},
        recentApplications: (appsPayload.applications || []).slice(0, 6),
        recommendations: (recRes.data?.jobs || []).slice(0, 3),
      });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    if (!funnelFocusStage) return;
    const target = funnelFocusStage === 'applications' ? 'recent-applications' : 'status-tracker';
    const targetY = target === 'recent-applications' ? recentApplicationsY : statusTrackerY;
    setFocusTarget(target);
    const timeout = setTimeout(() => setFocusTarget(''), 1800);
    scrollRef.current?.scrollTo({ y: Math.max(0, targetY - 10), animated: true });
    return () => clearTimeout(timeout);
  }, [funnelFocusStage, focusSignal, recentApplicationsY, statusTrackerY]);

  const kpiCards = [
    { key: 'applications', label: 'Applications', value: snapshot.totalApplications, icon: 'briefcase-outline', tone: colors.primary },
    { key: 'response', label: 'Response Rate', value: `${snapshot.responseRate}%`, icon: 'pulse-outline', tone: colors.info },
    { key: 'interview', label: 'Interview Rate', value: `${snapshot.interviewRate}%`, icon: 'mic-outline', tone: colors.success },
    { key: 'resume', label: 'AI Resume Score', value: `${snapshot.resumeScore}/100`, icon: 'sparkles-outline', tone: colors.purple },
  ];

  if (loading) {
    return (
      <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center' }} data-testid="jobs-candidates-loading" testID="jobs-candidates-loading">
        <ActivityIndicator color={colors.primary} />
      </View>
    );
  }

  return (
    <ScrollView ref={scrollRef} contentContainerStyle={{ padding: 16, paddingBottom: 56, gap: 14 }} data-testid="jobs-candidates-tab" testID="jobs-candidates-tab">
      {focusTarget ? (
        <View style={{ backgroundColor: colors.primarySoft, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(colors.primary, '33'), borderRadius: 10, padding: 10 }} data-testid="jobs-candidates-funnel-focus-banner" testID="jobs-candidates-funnel-focus-banner">
          <Text style={{ color: colors.primary, fontSize: 12, fontWeight: '700' }}>
            Funnel focus: {focusTarget === 'recent-applications' ? 'Applications list' : 'Application status tracker'}
          </Text>
        </View>
      ) : null}

      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10 }}>
        {kpiCards.map((card) => (
          <View key={card.key} style={{ width: '48%', backgroundColor: colors.card, borderWidth: 1, borderColor: colors.border, borderRadius: 14, padding: 12 }} data-testid={`candidate-kpi-${card.key}`}>
            <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
              <Text style={{ color: colors.textMuted, fontSize: 11, fontWeight: '700' }}>{card.label}</Text>
              <Ionicons name={card.icon as any} size={16} color={card.tone} />
            </View>
            <Text style={{ color: colors.text, fontSize: 21, fontWeight: '800', marginTop: 8 }} data-testid={`candidate-kpi-${card.key}-value`}>
              {card.value}
            </Text>
          </View>
        ))}
      </View>

      <View
        style={{
          backgroundColor: colors.card,
          borderWidth: focusTarget === 'status-tracker' ? 2 : 1,
          borderColor: focusTarget === 'status-tracker' ? colors.primary : colors.border,
          borderRadius: 14,
          padding: 14,
        }}
        onLayout={(event) => setStatusTrackerY(event.nativeEvent.layout.y)}
        data-testid="candidate-status-tracker-card"
      >
        <Text style={{ color: colors.text, fontSize: 16, fontWeight: '800' }}>Application Tracker</Text>
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 12 }}>
          {STATUS_ORDER.map((status) => (
            <View key={status} style={{ backgroundColor: colors.bgSoft, borderWidth: 1, borderColor: colors.border, borderRadius: 999, paddingHorizontal: 10, paddingVertical: 7 }} data-testid={`candidate-status-${status}`}>
              <Text style={{ color: colors.textSec, fontSize: 12, fontWeight: '700' }}>
                {status.toUpperCase()}: {snapshot.statusBreakdown[status] || 0}
              </Text>
            </View>
          ))}
        </View>
      </View>

      <View style={{ backgroundColor: colors.card, borderWidth: 1, borderColor: colors.border, borderRadius: 14, padding: 14 }} data-testid="candidate-quick-actions-card">
        <Text style={{ color: colors.text, fontSize: 16, fontWeight: '800', marginBottom: 10 }}>Candidate Operations</Text>
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
          {[
            { key: 'profile', label: 'Profile Management', href: '/profile' },
            { key: 'tracker', label: 'Track Applications', href: '/track-application' },
            { key: 'messages', label: 'Messaging', href: '/messages' },
            { key: 'notifications', label: `Alerts (${snapshot.unreadAlerts})`, href: '/notifications' },
            { key: 'saved', label: `Saved Jobs (${snapshot.savedJobs})`, href: '/job-platform' },
          ].map((btn) => (
            <TouchableOpacity
              key={btn.key}
              data-testid={`candidate-action-${btn.key}`}
              testID={`candidate-action-${btn.key}`}
              onPress={() => router.push(btn.href as any)}
              style={{ backgroundColor: colors.bgSoft, borderWidth: 1, borderColor: colors.border, borderRadius: 10, paddingHorizontal: 12, paddingVertical: 9 }}
            >
              <Text style={{ color: colors.textSec, fontSize: 12, fontWeight: '700' }}>{btn.label}</Text>
            </TouchableOpacity>
          ))}
        </View>
      </View>

      <View
        style={{
          backgroundColor: colors.card,
          borderWidth: focusTarget === 'recent-applications' ? 2 : 1,
          borderColor: focusTarget === 'recent-applications' ? colors.primary : colors.border,
          borderRadius: 14,
          padding: 14,
        }}
        onLayout={(event) => setRecentApplicationsY(event.nativeEvent.layout.y)}
        data-testid="candidate-recent-applications-card"
      >
        <Text style={{ color: colors.text, fontSize: 16, fontWeight: '800' }}>Recent Applications</Text>
        {snapshot.recentApplications.length === 0 ? (
          <Text style={{ color: colors.textMuted, fontSize: 13, marginTop: 10 }}>No applications yet.</Text>
        ) : snapshot.recentApplications.map((item, idx) => (
          <View key={item.application_id || idx} style={{ marginTop: 10, paddingTop: 10, borderTopWidth: idx === 0 ? 0 : 1, borderTopColor: colors.border }} data-testid={`candidate-application-row-${idx}`}>
            <Text style={{ color: colors.text, fontSize: 13, fontWeight: '700' }}>{item.job_title || 'Untitled Role'}</Text>
            <Text style={{ color: colors.textMuted, fontSize: 12, marginTop: 2 }}>{item.company_name || 'Company'} • {String(item.status || 'applied').toUpperCase()}</Text>
          </View>
        ))}
      </View>

      <View style={{ backgroundColor: colors.card, borderWidth: 1, borderColor: colors.border, borderRadius: 14, padding: 14 }} data-testid="candidate-ai-recommendations-card">
        <Text style={{ color: colors.text, fontSize: 16, fontWeight: '800' }}>AI Career Recommendations</Text>
        {snapshot.recommendations.length === 0 ? (
          <Text style={{ color: colors.textMuted, fontSize: 13, marginTop: 10 }}>Complete your profile and resume to unlock tailored recommendations.</Text>
        ) : snapshot.recommendations.map((job, idx) => (
          <View key={job.job_id || idx} style={{ marginTop: 10, padding: 10, borderRadius: 10, backgroundColor: colors.bgSoft, borderWidth: 1, borderColor: colors.border }} data-testid={`candidate-recommendation-${idx}`}>
            <Text style={{ color: colors.text, fontSize: 13, fontWeight: '700' }}>{job.title}</Text>
            <Text style={{ color: colors.textMuted, fontSize: 12, marginTop: 2 }}>{job.company_name} • Match {job.match_score || 0}%</Text>
            {!!job.match_reason && <Text style={{ color: colors.textSec, fontSize: 12, marginTop: 6 }}>{job.match_reason}</Text>}
          </View>
        ))}
      </View>

      <TouchableOpacity data-testid="candidate-refresh-button" testID="candidate-refresh-button" onPress={load} style={{ backgroundColor: colors.primary, borderRadius: 10, paddingVertical: 12, alignItems: 'center' }}>
        <Text style={{ color: colors.primaryText, fontSize: 13, fontWeight: '800' }}>Refresh Candidate Portal</Text>
      </TouchableOpacity>
    </ScrollView>
  );
};

/* i18n-probe t('i18n.auto.probe') */
