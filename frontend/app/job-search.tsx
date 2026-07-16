import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { View, Text, TouchableOpacity, ScrollView, useWindowDimensions, StyleSheet } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import AppShell from '../src/components/AppShell';
import { useTheme } from '../src/context/ThemeContext';
import { useTranslation } from '../src/hooks/useTranslation';
import api from '../src/services/api';
import { JobSearchHero } from '../src/components/jobSearch/JobSearchHero';
import { ProfileTab } from '../src/components/jobSearch/ProfileTab';
import { FindJobsTab } from '../src/components/jobSearch/FindJobsTab';
import { FitScoresTab } from '../src/components/jobSearch/FitScoresTab';
import { DocumentsTab } from '../src/components/jobSearch/DocumentsTab';
import { AtsCheckTab } from '../src/components/jobSearch/AtsCheckTab';
import { TrackerTab } from '../src/components/jobSearch/TrackerTab';
import { SalaryInterviewTab } from '../src/components/jobSearch/SalaryInterviewTab';
import { BillingMetricCard } from '../src/components/paymentHistory/BillingRoutePrimitives';

type JobSearchStep = 'profile' | 'find-jobs' | 'fit-scores' | 'documents' | 'ats-check' | 'tracker' | 'salary-interview';

type Summary = {
  profile_complete: boolean;
  open_jobs: number | null;
  matches: number | null;
  documents: number | null;
  tracked: number | null;
  interviews: number | null;
  offers: number | null;
};

const DEFAULT_SUMMARY: Summary = {
  profile_complete: false,
  open_jobs: null,
  matches: null,
  documents: null,
  tracked: null,
  interviews: null,
  offers: null,
};

export default function JobSearchPage() {
  const { t } = useTranslation();
  t('i18n.route.job-search.probe');
  const { colors } = useTheme();
  const { width } = useWindowDimensions();
  const isWide = width >= 1024;
  const isMedium = width >= 768;
  const tx = useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);

  const [activeStep, setActiveStep] = useState<JobSearchStep>('profile');
  const [summary, setSummary] = useState<Summary>(DEFAULT_SUMMARY);
  const [selectedJobId, setSelectedJobId] = useState('');
  const [selectedJobTitle, setSelectedJobTitle] = useState('');
  const [trackerRefreshSignal, setTrackerRefreshSignal] = useState(0);
  const [workflowSignal, setWorkflowSignal] = useState(0);

  const STEP_ITEMS: { key: JobSearchStep; label: string; icon: string; desc: string }[] = useMemo(() => [
    { key: 'profile', label: tx('jobSearch.steps.profile', 'Career Profile'), icon: 'person-circle-outline', desc: tx('jobSearch.steps.profileDesc', 'Your skills, experience, and goals power every AI evaluation.') },
    { key: 'find-jobs', label: tx('jobSearch.steps.findJobs', 'Find Jobs'), icon: 'search-outline', desc: tx('jobSearch.steps.findJobsDesc', 'Search open roles or paste a link from any public job site.') },
    { key: 'fit-scores', label: tx('jobSearch.steps.fitScores', 'Fit Scores'), icon: 'analytics-outline', desc: tx('jobSearch.steps.fitScoresDesc', 'Your evaluated jobs ranked by honest 5-dimension AI fit.') },
    { key: 'documents', label: tx('jobSearch.steps.documents', 'Documents'), icon: 'document-text-outline', desc: tx('jobSearch.steps.documentsDesc', 'Tailored CV + cover letter with reviewer critique, PDF export, and email delivery.') },
    { key: 'ats-check', label: tx('jobSearch.steps.atsCheck', 'ATS Check'), icon: 'shield-checkmark-outline', desc: tx('jobSearch.steps.atsCheckDesc', 'Validate keyword coverage and parseability against the posting.') },
    { key: 'tracker', label: tx('jobSearch.steps.tracker', 'Tracker'), icon: 'trending-up-outline', desc: tx('jobSearch.steps.trackerDesc', 'Track every application from saved to offer.') },
    { key: 'salary-interview', label: tx('jobSearch.steps.salaryInterview', 'Salary & Interview'), icon: 'cash-outline', desc: tx('jobSearch.steps.salaryInterviewDesc', 'Benchmark your market value and rehearse AI interview questions.') },
  ], [tx]);

  const loadSummary = useCallback(async () => {
    try {
      const resp = await api.get('/job-search/summary', { silentLoading: true });
      if (resp?.data) setSummary(resp.data);
    } catch {
      // summary refreshes on next action
    }
  }, []);

  useEffect(() => { loadSummary(); }, [loadSummary]);

  const bumpWorkflow = useCallback(() => {
    setWorkflowSignal((v) => v + 1);
    loadSummary();
  }, [loadSummary]);

  useEffect(() => {
    if (summary.profile_complete && activeStep === 'profile') {
      // Keep user context; do not auto-switch. Intentional no-op.
    }
  }, [summary.profile_complete, activeStep]);

  const handleGenerateKit = (jobId: string, jobTitle: string) => {
    setSelectedJobId(jobId);
    setSelectedJobTitle(jobTitle);
    setActiveStep('documents');
  };

  const activeStepMeta = STEP_ITEMS.find((step) => step.key === activeStep);
  const renderSummaryValue = (value: number | null) => (value == null ? '—' : String(value));

  return (
    <AppShell>
      <View style={[s.root, { backgroundColor: colors.bg }]} data-testid="job-search-page" testID="job-search-page">
        <ScrollView contentContainerStyle={{ padding: isWide ? 24 : isMedium ? 18 : 14, paddingBottom: 44 }}>
          <View style={{ maxWidth: 1440, width: '100%', alignSelf: 'center', gap: 12 }}>
            <JobSearchHero
              colors={colors}
              isWide={isWide}
              tx={tx}
              t={t}
              activeStepLabel={activeStepMeta?.label || tx('jobSearch.steps.default', 'Job Search')}
              activeStepDesc={activeStepMeta?.desc || tx('jobSearch.hero.workspaceFallback', 'AI-guided job search from profile to offer.')}
              openJobs={summary.open_jobs}
            />

            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 12 }}>
              <BillingMetricCard label={tx('jobSearch.summary.matches', 'AI fit scores')} value={renderSummaryValue(summary.matches)} helper={tx('jobSearch.summary.matchesHelper', 'Jobs you evaluated with the 5-dimension fit framework.')} colors={colors} icon="analytics-outline" testId="job-search-summary-matches" />
              <BillingMetricCard label={tx('jobSearch.summary.documents', 'Application kits')} value={renderSummaryValue(summary.documents)} helper={tx('jobSearch.summary.documentsHelper', 'Tailored CV + cover letter kits generated and reviewed by AI.')} colors={colors} icon="document-text-outline" testId="job-search-summary-documents" />
              <BillingMetricCard label={tx('jobSearch.summary.tracked', 'Tracked applications')} value={renderSummaryValue(summary.tracked)} helper={tx('jobSearch.summary.trackedHelper', 'Applications in your tracker across every stage.')} colors={colors} icon="bookmark-outline" testId="job-search-summary-tracked" />
              <BillingMetricCard label={tx('jobSearch.summary.interviews', 'Interviews & offers')} value={`${renderSummaryValue(summary.interviews)} / ${renderSummaryValue(summary.offers)}`} helper={tx('jobSearch.summary.interviewsHelper', 'Interview-stage and offer-stage applications you recorded.')} colors={colors} icon="ribbon-outline" testId="job-search-summary-interviews" />
            </View>

            <View style={{ flexDirection: 'row', gap: 8, flexWrap: 'wrap' }} data-testid="job-search-step-bar" testID="job-search-step-bar">
              {STEP_ITEMS.map((step, idx) => {
                const isActive = activeStep === step.key;
                return (
                  <TouchableOpacity
                    key={step.key}
                    onPress={() => setActiveStep(step.key)}
                    style={{
                      flexBasis: '13%',
                      flexGrow: 1,
                      minWidth: 128,
                      borderRadius: 14,
                      borderWidth: 1,
                      borderColor: isActive ? colors.primary : colors.border,
                      backgroundColor: isActive ? colors.primary : colors.card,
                      paddingHorizontal: 12,
                      paddingVertical: 12,
                      flexDirection: 'row',
                      alignItems: 'center',
                      gap: 8,
                    }}
                    data-testid={`job-search-step-${step.key}`}
                    testID={`job-search-step-${step.key}`}
                    accessibilityRole="button"
                    accessibilityLabel={step.label}
                  >
                    <Ionicons name={step.icon as any} size={16} color={isActive ? colors.primaryText : colors.textSecondary} />
                    <View style={{ flex: 1 }}>
                      <Text style={{ color: isActive ? colors.primaryText : colors.text, fontSize: 12.5, fontWeight: '800' }} numberOfLines={1}>
                        {idx + 1}. {step.label}
                      </Text>
                    </View>
                  </TouchableOpacity>
                );
              })}
            </View>

            {activeStep === 'profile' ? (
              <ProfileTab colors={colors} tx={tx} onProfileSaved={loadSummary} />
            ) : null}
            {activeStep === 'find-jobs' ? (
              <FindJobsTab
                colors={colors}
                tx={tx}
                onGenerateKit={handleGenerateKit}
                onTracked={() => { setTrackerRefreshSignal((v) => v + 1); loadSummary(); }}
                onMatched={() => { bumpWorkflow(); setActiveStep('fit-scores'); }}
              />
            ) : null}
            {activeStep === 'fit-scores' ? (
              <FitScoresTab colors={colors} tx={tx} refreshSignal={workflowSignal} onGenerateKit={handleGenerateKit} />
            ) : null}
            {activeStep === 'documents' ? (
              <DocumentsTab colors={colors} tx={tx} selectedJobId={selectedJobId} selectedJobTitle={selectedJobTitle} onKitGenerated={bumpWorkflow} onApplied={() => { setTrackerRefreshSignal((v) => v + 1); loadSummary(); }} />
            ) : null}
            {activeStep === 'ats-check' ? (
              <AtsCheckTab colors={colors} tx={tx} refreshSignal={workflowSignal} />
            ) : null}
            {activeStep === 'tracker' ? (
              <TrackerTab colors={colors} tx={tx} refreshSignal={trackerRefreshSignal} onChanged={loadSummary} />
            ) : null}
            {activeStep === 'salary-interview' ? (
              <SalaryInterviewTab colors={colors} tx={tx} />
            ) : null}
          </View>
        </ScrollView>
      </View>
    </AppShell>
  );
}

const s = StyleSheet.create({
  root: { flex: 1 },
});
