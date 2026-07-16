import React from 'react';
import { View } from 'react-native';
import { BillingMetricCard } from '../paymentHistory/BillingRoutePrimitives';

type Summary = {
  openRoles: number | null;
  candidateApplications: number | null;
  savedJobs: number | null;
  employerJobs: number | null;
};

type Props = {
  colors: any;
  tx: (key: string, fallback: string) => string;
  summary: Summary;
};

export const JobsPortalSummaryMetrics = ({ colors, tx, summary }: Props) => {
  const renderSummaryValue = (value: number | null) => (value == null ? tx('jobsPortal.summary.unavailable', 'Unavailable') : String(value));

  return (
    <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 12 }}>
      <BillingMetricCard label={tx('jobsPortal.summary.openRoles', 'Open roles')} value={renderSummaryValue(summary.openRoles)} helper={tx('jobsPortal.summary.openRolesHelper', 'Pulled from the live public jobs feed currently visible to this workspace.')} colors={colors} icon="briefcase-outline" testId="jobs-portal-summary-open-roles" />
      <BillingMetricCard label={tx('jobsPortal.summary.candidateApplications', 'Candidate applications')} value={renderSummaryValue(summary.candidateApplications)} helper={tx('jobsPortal.summary.candidateApplicationsHelper', 'Candidate-side application count if accessible for this account context.')} colors={colors} icon="document-text-outline" testId="jobs-portal-summary-candidate-applications" />
      <BillingMetricCard label={tx('jobsPortal.summary.savedJobs', 'Saved jobs')} value={renderSummaryValue(summary.savedJobs)} helper={tx('jobsPortal.summary.savedJobsHelper', 'Saved jobs count when the route can access candidate job state.')} colors={colors} icon="bookmark-outline" testId="jobs-portal-summary-saved-jobs" />
      <BillingMetricCard label={tx('jobsPortal.summary.employerJobs', 'Employer jobs')} value={renderSummaryValue(summary.employerJobs)} helper={tx('jobsPortal.summary.employerJobsHelper', 'Employer-side posted jobs count if available for this account context.')} colors={colors} icon="business-outline" testId="jobs-portal-summary-employer-jobs" />
    </View>
  );
};
