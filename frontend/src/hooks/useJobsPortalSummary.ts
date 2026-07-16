import { useCallback, useEffect, useState } from 'react';
import api from '../services/api';

export type JobsPortalSummaryState = {
  openRoles: number | null;
  candidateApplications: number | null;
  interviewApplications: number | null;
  offerApplications: number | null;
  savedJobs: number | null;
  employerJobs: number | null;
  lastSyncLabel: string;
};

const DEFAULT_SUMMARY: JobsPortalSummaryState = {
  openRoles: null,
  candidateApplications: null,
  interviewApplications: null,
  offerApplications: null,
  savedJobs: null,
  employerJobs: null,
  lastSyncLabel: '',
};

export const JOBS_PORTAL_REFRESH_MS = 60000;

export const useJobsPortalSummary = (
  options: {
    onSummaryLoadError?: (error: unknown, retry: () => void) => void;
  } = {}
) => {
  const { onSummaryLoadError } = options;
  const [summary, setSummary] = useState<JobsPortalSummaryState>(DEFAULT_SUMMARY);

  const loadPortalSummary = useCallback(async () => {
    try {
      let payload: any = {};
      try {
        const summaryRes = await api.get('/hiring/v2/dashboard/summary', { skipDedupe: true });
        payload = summaryRes?.data || {};
      } catch {
        const legacyRes = await api.get('/jobs/portal-summary', { skipDedupe: true });
        payload = legacyRes?.data || {};
      }

      setSummary({
        openRoles: typeof payload.open_roles === 'number'
          ? payload.open_roles
          : typeof payload.total_active_jobs === 'number'
            ? payload.total_active_jobs
            : null,
        candidateApplications: typeof payload.candidate_applications === 'number'
          ? payload.candidate_applications
          : typeof payload.my_applications === 'number'
            ? payload.my_applications
            : typeof payload.candidate?.applications === 'number'
              ? payload.candidate.applications
              : null,
        interviewApplications: typeof payload.interview_applications === 'number' ? payload.interview_applications : null,
        offerApplications: typeof payload.offer_applications === 'number' ? payload.offer_applications : null,
        savedJobs: typeof payload.saved_jobs === 'number'
          ? payload.saved_jobs
          : typeof payload.candidate?.saved_jobs === 'number'
            ? payload.candidate.saved_jobs
            : null,
        employerJobs: typeof payload.employer_jobs === 'number'
          ? payload.employer_jobs
          : typeof payload.employer?.open_roles === 'number'
            ? payload.employer.open_roles
            : null,
        lastSyncLabel: new Date().toLocaleTimeString(),
      });
    } catch (error) {
      setSummary((current) => ({ ...current, lastSyncLabel: new Date().toLocaleTimeString() }));
      onSummaryLoadError?.(error, () => {
        void loadPortalSummary();
      });
    }
  }, [onSummaryLoadError]);

  useEffect(() => {
    void loadPortalSummary();
  }, [loadPortalSummary]);

  useEffect(() => {
    const timer = setInterval(() => {
      if (typeof document !== 'undefined' && document.hidden) return;
      void loadPortalSummary();
    }, JOBS_PORTAL_REFRESH_MS);
    return () => clearInterval(timer);
  }, [loadPortalSummary]);

  return {
    summary,
    setSummary,
    loadPortalSummary,
  };
};
