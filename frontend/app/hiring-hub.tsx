import React, { useEffect, useState, useMemo } from 'react';
import {
  View, Text, ScrollView, TouchableOpacity,
  _ActivityIndicator, RefreshControl, useWindowDimensions,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useAuth } from '../src/context/AuthContext';
import { useTheme } from '../src/context/ThemeContext';
import AppShell from '../src/components/AppShell';
import { CareerSkeleton } from '../src/components/SkeletonLoaders';

// Sub-components (each manages its own state & API calls)
import { EmpOverviewTab } from '../src/components/hiring/EmpOverviewTab';
import { PipelineTab } from '../src/components/hiring/PipelineTab';
import { RankingsTab } from '../src/components/hiring/RankingsTab';
import { InterviewCenterTab } from '../src/components/hiring/InterviewCenterTab';
import { SchedulerTab } from '../src/components/hiring/SchedulerTab';
import { AdminAIOversightTab } from '../src/components/hiring/AdminAIOversightTab';
import { CandOverviewTab } from '../src/components/hiring/CandOverviewTab';
import { AIMatchTab } from '../src/components/hiring/AIMatchTab';
import { CareerCoachTab } from '../src/components/hiring/CareerCoachTab';
import { InterviewPrepTab } from '../src/components/hiring/InterviewPrepTab';
import { ResumeBuilderTab } from '../src/components/hiring/ResumeBuilderTab';
import { MockInterviewTab } from '../src/components/hiring/MockInterviewTab';
import { RealTimeDashboard } from '../src/components/hiring/RealTimeDashboard';
import { FairnessDashboard } from '../src/components/hiring/FairnessDashboard';
import { AILearningDashboard } from '../src/components/hiring/AILearningDashboard';
import { SystemHealthDashboard } from '../src/components/hiring/SystemHealthDashboard';
import { InterviewSummaryModal, CandidateExperienceForm } from '../src/components/hiring/InterviewSummary';
import { InterviewRoomPanel } from '../src/components/hiring/InterviewRoomPanel';
import EmpTier3Tab from '../src/components/hiring/EmpTier3Tab';
import { useTranslation } from '../src/hooks/useTranslation';
import { handleAppRecoverableError } from '../src/utils/appRecoverableError';

type EmpTab = 'overview' | 'pipeline' | 'rankings' | 'copilot' | 'interviews' | 'scheduler' | 'tier3' | 'admin-ai' | 'realtime' | 'fairness' | 'ai-learning' | 'health';
type CandTab = 'overview' | 'ai-match' | 'career-coach' | 'interview-prep' | 'my-interviews' | 'resume-builder' | 'mock-interview';

export function HiringHubContent() {
  const { user } = useAuth();
  const { colors } = useTheme();
  const { width } = useWindowDimensions();
  const isWide = width >= 768;

  const C = useMemo(() => ({
    bg: colors.bg, card: colors.card, text: colors.text, muted: colors.textMuted,
    border: colors.border, primary: colors.primary, success: colors.success,
    warning: colors.warning, error: colors.error, accent: colors.indigo,
    bgSoft: colors.bgSoft,
  }), [colors]);

  const [isEmployer, setIsEmployer] = useState(false);
  const [empTab, setEmpTab] = useState<EmpTab>('overview');
  const [candTab, setCandTab] = useState<CandTab>('overview');
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  // Shared state for job selection (employer tabs)
  const [myJobs, setMyJobs] = useState<any[]>([]);
  const [selectedJobId, setSelectedJobId] = useState<string>('');

  // Modal overlays
  const [summaryInterview, setSummaryInterview] = useState<string | null>(null);
  const [rateInterview, setRateInterview] = useState<string | null>(null);
  const [roomInterview, setRoomInterview] = useState<string | null>(null);

  useEffect(() => {
    try {
      const roles = (user as any)?.roles || [];
      const admin = (user as any)?.is_admin;
      setIsEmployer(admin || roles.includes('employer'));
    } catch (error) { handleAppRecoverableError({ scope: 'hiring-hub.tsx#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
    setLoading(false);
  }, [user]);

  const handleJobsLoaded = (jobs: any[]) => {
    setMyJobs(jobs);
    if (!selectedJobId && jobs[0]) setSelectedJobId(jobs[0].job_id);
  };

  const onRefresh = () => {
    setRefreshing(true);
    // Force re-mount active tab by toggling a key
    const current = isEmployer ? empTab : candTab;
    if (isEmployer) { setEmpTab('overview'); setTimeout(() => setEmpTab(current), 50); }
    else { setCandTab('overview'); setTimeout(() => setCandTab(current as CandTab), 50); }
    setRefreshing(false);
  };

  // ── Tab Bars ──
  const EMP_TABS: { key: EmpTab; label: string; icon: string }[] = [
    { key: 'overview', label: 'Dashboard', icon: 'grid-outline' },
    { key: 'pipeline', label: 'Pipeline', icon: 'git-branch-outline' },
    { key: 'rankings', label: 'Rankings', icon: 'trophy-outline' },
    { key: 'interviews', label: 'Interviews', icon: 'videocam-outline' },
    { key: 'scheduler', label: 'Scheduler', icon: 'calendar-outline' },
    { key: 'tier3', label: 'Tier 3', icon: 'rocket-outline' },
    { key: 'copilot', label: 'AI Copilot', icon: 'sparkles-outline' },
    { key: 'admin-ai', label: 'AI Oversight', icon: 'shield-checkmark-outline' },
    { key: 'realtime', label: 'Live Intel', icon: 'pulse-outline' },
    { key: 'fairness', label: 'Fairness', icon: 'scale-outline' },
    { key: 'ai-learning', label: 'AI Learning', icon: 'school-outline' },
    { key: 'health', label: 'Health', icon: 'medkit-outline' },
  ];

  const CAND_TABS: { key: CandTab; label: string; icon: string }[] = [
    { key: 'overview', label: 'Dashboard', icon: 'grid-outline' },
    { key: 'my-interviews', label: 'Interviews', icon: 'videocam-outline' },
    { key: 'ai-match', label: 'AI Match', icon: 'flash-outline' },
    { key: 'resume-builder', label: 'Resume AI', icon: 'document-text-outline' },
    { key: 'mock-interview', label: 'Mock Interview', icon: 'mic-outline' },
    { key: 'career-coach', label: 'Career AI', icon: 'school-outline' },
    { key: 'interview-prep', label: 'Prep', icon: 'clipboard-outline' },
  ];

  const renderTabBar = (tabs: { key: string; label: string; icon: string }[], active: string, onSelect: (k: any) => void) => (
    <ScrollView data-testid={isEmployer ? 'employer-tabs' : 'candidate-tabs'} testID={isEmployer ? 'employer-tabs' : 'candidate-tabs'} horizontal showsHorizontalScrollIndicator={false}
      style={{ marginBottom: 16 }} contentContainerStyle={{ gap: 6, paddingRight: 16 }}>
      {tabs.map(t => (
        <TouchableOpacity key={t.key} data-testid={`${isEmployer ? 'emp' : 'cand'}-tab-${t.key}`} testID={`${isEmployer ? 'emp' : 'cand'}-tab-${t.key}`}
          onPress={() => onSelect(t.key)}
          style={{
            flexDirection: 'row', alignItems: 'center', gap: 6,
            paddingHorizontal: 14, paddingVertical: 8, borderRadius: 20,
            backgroundColor: active === t.key ? C.primary : C.card,
            borderWidth: 1, borderColor: active === t.key ? C.primary : C.border,
          }}>
          <Ionicons name={t.icon as any} size={16} color={active === t.key ? colors.primaryText : C.muted} />
          <Text style={{ color: active === t.key ? colors.primaryText : C.text, fontSize: 13, fontWeight: '600' }}>{t.label}</Text>
        </TouchableOpacity>
      ))}
    </ScrollView>
  );

  // ── Content Rendering ──
  const renderContent = () => {
    if (loading) {
      return (
        <CareerSkeleton />
      );
    }

    if (isEmployer) {
      return (
        <View>
          {renderTabBar(EMP_TABS, empTab, setEmpTab)}
          {empTab === 'overview' && <EmpOverviewTab C={C} onJobsLoaded={handleJobsLoaded} />}
          {empTab === 'pipeline' && <PipelineTab C={C} isWide={isWide} myJobs={myJobs} selectedJobId={selectedJobId} onSelectJob={setSelectedJobId} />}
          {(empTab === 'rankings' || empTab === 'copilot') && <RankingsTab C={C} myJobs={myJobs} selectedJobId={selectedJobId} onSelectJob={setSelectedJobId} />}
          {empTab === 'interviews' && <InterviewCenterTab C={C} isEmployer={true} onShowSummary={setSummaryInterview} onShowRate={setRateInterview} onJoinRoom={setRoomInterview} />}
          {empTab === 'scheduler' && <SchedulerTab C={C} myJobs={myJobs} selectedJobId={selectedJobId} onSelectJob={setSelectedJobId} onSwitchToInterviews={() => setEmpTab('interviews')} />}
          {empTab === 'tier3' && <EmpTier3Tab C={C} />}
          {empTab === 'admin-ai' && <AdminAIOversightTab C={C} />}
          {empTab === 'realtime' && <RealTimeDashboard C={C} isWide={isWide} />}
          {empTab === 'fairness' && <FairnessDashboard C={C} isWide={isWide} />}
          {empTab === 'ai-learning' && <AILearningDashboard C={C} isWide={isWide} />}
          {empTab === 'health' && <SystemHealthDashboard C={C} isWide={isWide} />}
        </View>
      );
    }

    return (
      <View>
        {renderTabBar(CAND_TABS, candTab, setCandTab)}
        {candTab === 'overview' && <CandOverviewTab C={C} onSwitchTab={setCandTab} />}
        {candTab === 'my-interviews' && <InterviewCenterTab C={C} isEmployer={false} onShowSummary={setSummaryInterview} onShowRate={setRateInterview} onJoinRoom={setRoomInterview} />}
        {candTab === 'ai-match' && <AIMatchTab C={C} />}
        {candTab === 'resume-builder' && <ResumeBuilderTab C={C} />}
        {candTab === 'mock-interview' && <MockInterviewTab C={C} />}
        {candTab === 'career-coach' && <CareerCoachTab C={C} />}
        {candTab === 'interview-prep' && <InterviewPrepTab C={C} />}
      </View>
    );
  };

  const hiringContent = (
    <SafeAreaView style={{ flex: 1, backgroundColor: C.bg }}>
      <ScrollView
        contentContainerStyle={{ padding: isWide ? 24 : 16, paddingBottom: 100 }}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={C.accent} />}
      >
        <View data-testid="hiring-hub-header" testID="hiring-hub-header" style={{ marginBottom: 20 }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
            <View>
              <Text style={{ color: C.text, fontSize: 18, fontWeight: '700' }}>
                {isEmployer ? 'Hiring Intelligence' : 'Global Job Platform'}
              </Text>
              <Text style={{ color: C.muted, fontSize: 12 }}>
                {isEmployer ? 'AI-Powered Recruitment Copilot' : 'AI Career Navigation & Matching'}
              </Text>
            </View>
            <View style={{ backgroundColor: (globalThis as any).__alphaColor(C.accent, '22'), paddingHorizontal: 10, paddingVertical: 4, borderRadius: 12 }}>
              <Text style={{ color: colors.indigoText, fontSize: 11, fontWeight: '700' }}>ARIS AI</Text>
            </View>
          </View>
        </View>

        {renderContent()}
      </ScrollView>

      {summaryInterview && (
        <View style={{
          position: 'absolute', top: 0, left: 0, right: 0, bottom: 0,
          backgroundColor: colors.overlay, justifyContent: 'center', alignItems: 'center',
          padding: 20, zIndex: 100,
        }}>
          <InterviewSummaryModal C={C} interviewId={summaryInterview} interviewStatus="completed" onClose={() => setSummaryInterview(null)} />
        </View>
      )}

      {rateInterview && (
        <View style={{
          position: 'absolute', top: 0, left: 0, right: 0, bottom: 0,
          backgroundColor: colors.overlay, justifyContent: 'center', alignItems: 'center',
          padding: 20, zIndex: 100,
        }}>
          <CandidateExperienceForm C={C} interviewId={rateInterview} onClose={() => setRateInterview(null)} />
        </View>
      )}

      {roomInterview && (
        <View style={{
          position: 'absolute', top: 0, left: 0, right: 0, bottom: 0,
          backgroundColor: colors.overlay, justifyContent: 'center', alignItems: 'center',
          padding: 16, zIndex: 120,
        }}>
          <InterviewRoomPanel C={C} interviewId={roomInterview} onClose={() => setRoomInterview(null)} />
        </View>
      )}
    </SafeAreaView>
  );

  return hiringContent;
}

export default function HiringHub() {
  const { t } = useTranslation();
  t('i18n.route.hiring-hub.probe');
  return (
    <AppShell>
      <HiringHubContent />
    </AppShell>
  );
}