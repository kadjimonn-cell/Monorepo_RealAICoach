import React, { useCallback, useEffect, useState } from 'react';
import { View, Text, TextInput, TouchableOpacity, ActivityIndicator, Platform, Linking } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { BillingSectionCard, BillingActionButton } from '../paymentHistory/BillingRoutePrimitives';

type Job = {
  job_id: string;
  title: string;
  department: string;
  location: string;
  type: string;
  level: string;
  description: string;
  salary_usd_min?: number | null;
  salary_usd_max?: number | null;
  salary_text?: string;
  source_url?: string;
  portal?: string;
  is_external?: boolean;
};

type Props = {
  colors: any;
  tx: (key: string, fallback: string) => string;
  onGenerateKit: (jobId: string, jobTitle: string) => void;
  onTracked: () => void;
  onMatched: () => void;
};

const openExternal = (url: string) => {
  if (Platform.OS === 'web' && typeof window !== 'undefined') {
    window.open(url, '_blank', 'noopener');
  } else {
    Linking.openURL(url);
  }
};

export const FindJobsTab = ({ colors, tx, onGenerateKit, onTracked, onMatched }: Props) => {
  const [query, setQuery] = useState('');
  const [jobs, setJobs] = useState<Job[]>([]);
  const [externalJobs, setExternalJobs] = useState<Job[]>([]);
  const [loading, setLoading] = useState(true);
  const [matchingJobId, setMatchingJobId] = useState('');
  const [trackingJobId, setTrackingJobId] = useState('');
  const [errorMsg, setErrorMsg] = useState('');
  const [importUrl, setImportUrl] = useState('');
  const [importing, setImporting] = useState(false);
  const [importMsg, setImportMsg] = useState('');
  const [pasteMode, setPasteMode] = useState(false);
  const [pastedText, setPastedText] = useState('');
  const [portals, setPortals] = useState<string[]>([]);
  const [appliedPromptJobId, setAppliedPromptJobId] = useState('');
  const [alerts, setAlerts] = useState<any[]>([]);
  const [savingAlert, setSavingAlert] = useState(false);

  const loadAlerts = useCallback(async () => {
    try {
      const resp = await api.get('/job-search/alerts', { silentLoading: true });
      setAlerts(Array.isArray(resp.data?.alerts) ? resp.data.alerts : []);
    } catch {
      // silent
    }
  }, []);

  useEffect(() => {
    void loadAlerts();
  }, [loadAlerts]);

  const saveAlert = async () => {
    if (!query.trim() || savingAlert) return;
    setSavingAlert(true);
    try {
      await api.post('/job-search/alerts', { q: query.trim() });
      await loadAlerts();
    } catch (e: any) {
      setErrorMsg(e?.response?.data?.detail || tx('jobSearch.alerts.saveError', 'Could not save this search alert.'));
    } finally {
      setSavingAlert(false);
    }
  };

  const deleteAlert = async (alertId: string) => {
    try {
      await api.delete(`/job-search/alerts/${alertId}`);
      setAlerts((prev) => prev.filter((a) => a.alert_id !== alertId));
    } catch {
      // silent
    }
  };

  const toggleAlertEmail = async (alert: any) => {
    const next = alert.notify_email === false;
    try {
      await api.patch(`/job-search/alerts/${alert.alert_id}`, { notify_email: next });
      setAlerts((prev) => prev.map((a) => (a.alert_id === alert.alert_id ? { ...a, notify_email: next } : a)));
    } catch {
      // silent
    }
  };

  const loadJobs = useCallback(async (q: string) => {
    setLoading(true);
    setErrorMsg('');
    try {
      const resp = await api.get('/job-search/jobs', { params: { q }, silentLoading: true });
      setJobs(resp?.data?.jobs || []);
    } catch {
      setErrorMsg(tx('jobSearch.jobs.loadFailed', 'Could not load open jobs right now.'));
    } finally {
      setLoading(false);
    }
  }, [tx]);

  const loadExternal = useCallback(async () => {
    try {
      const resp = await api.get('/job-search/external/jobs', { silentLoading: true });
      setExternalJobs(resp?.data?.jobs || []);
    } catch {
      // section simply stays empty
    }
  }, []);

  useEffect(() => {
    loadJobs('');
    loadExternal();
    (async () => {
      try {
        const resp = await api.get('/job-search/external/portals', { silentLoading: true });
        setPortals(resp?.data?.portals || []);
      } catch {
        // chips optional
      }
    })();
  }, [loadJobs, loadExternal]);

  const importJob = async () => {
    if (!importUrl.trim()) {
      setImportMsg(tx('jobSearch.import.needUrl', 'Paste a job posting link first.'));
      return;
    }
    setImporting(true);
    setImportMsg('');
    try {
      const resp = await api.post('/job-search/external/import', { url: importUrl.trim() }, { timeout: 120000 });
      if (resp?.data?.fetch_blocked) {
        setPasteMode(true);
        setImportMsg(tx('jobSearch.import.blocked', 'This site blocks automated fetching — paste the job description below instead.'));
      } else if (resp?.data?.job) {
        setExternalJobs((prev) => [resp.data.job, ...prev]);
        setImportUrl('');
        setPasteMode(false);
        setPastedText('');
        setImportMsg(`${tx('jobSearch.import.imported', 'Imported')}: ${resp.data.job.title}`);
      }
    } catch (e: any) {
      setImportMsg(e?.response?.data?.detail || tx('jobSearch.import.failed', 'Could not import this link. Check the URL and retry.'));
    } finally {
      setImporting(false);
    }
  };

  const importManual = async () => {
    setImporting(true);
    setImportMsg('');
    try {
      const resp = await api.post('/job-search/external/import-manual', { url: importUrl.trim(), pasted_text: pastedText }, { timeout: 120000 });
      if (resp?.data?.job) {
        setExternalJobs((prev) => [resp.data.job, ...prev]);
        setImportUrl('');
        setPasteMode(false);
        setPastedText('');
        setImportMsg(`${tx('jobSearch.import.imported', 'Imported')}: ${resp.data.job.title}`);
      }
    } catch (e: any) {
      setImportMsg(e?.response?.data?.detail || tx('jobSearch.import.failed', 'Could not import this link. Check the URL and retry.'));
    } finally {
      setImporting(false);
    }
  };

  const removeExternal = async (jobId: string) => {
    try {
      await api.delete(`/job-search/external/jobs/${jobId}`);
      setExternalJobs((prev) => prev.filter((j) => j.job_id !== jobId));
    } catch {
      setImportMsg(tx('jobSearch.import.removeFailed', 'Could not remove the imported job.'));
    }
  };

  const runMatch = async (job: Job) => {
    setMatchingJobId(job.job_id);
    setErrorMsg('');
    try {
      const resp = await api.post('/job-search/match', { job_id: job.job_id }, { timeout: 90000 });
      if (resp?.data?.match) onMatched();
    } catch (e: any) {
      const detail = e?.response?.data?.detail;
      setErrorMsg(detail === 'Complete your career profile first'
        ? tx('jobSearch.jobs.profileFirst', 'Complete your career profile first, then run the AI fit score.')
        : tx('jobSearch.jobs.matchFailed', 'Fit evaluation is unavailable right now. Please retry.'));
    } finally {
      setMatchingJobId('');
    }
  };

  const trackJob = async (job: Job) => {
    setTrackingJobId(job.job_id);
    setErrorMsg('');
    try {
      await api.post('/job-search/applications', { job_id: job.job_id, status: 'saved' });
      onTracked();
    } catch (e: any) {
      if (e?.response?.status === 409) {
        setErrorMsg(tx('jobSearch.jobs.alreadyTracked', 'This job is already in your tracker.'));
      } else {
        setErrorMsg(tx('jobSearch.jobs.trackFailed', 'Could not add this job to your tracker.'));
      }
    } finally {
      setTrackingJobId('');
    }
  };

  const applyOnSite = (job: Job) => {
    if (job.source_url) openExternal(job.source_url);
    setAppliedPromptJobId(job.job_id);
  };

  const confirmApplied = async (job: Job) => {
    try {
      await api.post('/job-search/applications/mark-applied', { job_id: job.job_id });
      setAppliedPromptJobId('');
      onTracked();
      setImportMsg(tx('jobSearch.docs.markAppliedDone', 'Moved to Applied in your tracker.'));
    } catch {
      setImportMsg(tx('jobSearch.docs.markAppliedFailed', 'Could not update your tracker right now.'));
    }
  };

  const renderJobCard = (job: Job, idx: number, external: boolean) => {
    const prefix = external ? 'ext' : 'int';
    return (
      <BillingSectionCard key={job.job_id} colors={colors} testId={`job-search-${prefix}-job-card-${idx}`}>
        <View style={{ flexDirection: 'row', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
          <View style={{ flex: 1, minWidth: 200 }}>
            {external ? (
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 4, flexWrap: 'wrap' }}>
                <View style={{ backgroundColor: colors.primary, borderRadius: 999, paddingHorizontal: 10, paddingVertical: 3 }}>
                  <Text style={{ color: colors.primaryText, fontSize: 10, fontWeight: '800', textTransform: 'uppercase' }} data-testid={`job-search-portal-badge-${idx}`} testID={`job-search-portal-badge-${idx}`}>{job.portal}</Text>
                </View>
                {job.source_url ? (
                  <TouchableOpacity onPress={() => openExternal(job.source_url!)} data-testid={`job-search-open-posting-${idx}`} testID={`job-search-open-posting-${idx}`} accessibilityRole="link" accessibilityLabel={tx('jobSearch.import.openPosting', 'Open original posting')}>
                    <Text style={{ color: colors.info, fontSize: 11, fontWeight: '700' }}>{tx('jobSearch.import.openPosting', 'Open original posting')} ↗</Text>
                  </TouchableOpacity>
                ) : null}
              </View>
            ) : null}
            <Text style={{ color: colors.text, fontSize: 15, fontWeight: '800' }} data-testid={`job-search-${prefix}-job-title-${idx}`} testID={`job-search-${prefix}-job-title-${idx}`}>{job.title}</Text>
            <Text style={{ color: colors.textSecondary, fontSize: 12, marginTop: 4 }}>
              {[job.department, job.location, job.type, job.level].filter(Boolean).join(' · ')}
            </Text>
            {job.salary_text ? (
              <Text style={{ color: colors.textSecondary, fontSize: 12, marginTop: 2 }}>{tx('jobSearch.jobs.salary', 'Salary')}: {job.salary_text}</Text>
            ) : job.salary_usd_min != null && job.salary_usd_max != null ? (
              <Text style={{ color: colors.textSecondary, fontSize: 12, marginTop: 2 }}>
                {tx('jobSearch.jobs.salary', 'Salary')}: ${Number(job.salary_usd_min).toLocaleString()} – ${Number(job.salary_usd_max).toLocaleString()}
              </Text>
            ) : null}
            <Text style={{ color: colors.textSecondary, fontSize: 12, lineHeight: 18, marginTop: 8 }} numberOfLines={3}>{job.description}</Text>
          </View>
          {external ? (
            <TouchableOpacity onPress={() => removeExternal(job.job_id)} data-testid={`job-search-ext-remove-${idx}`} testID={`job-search-ext-remove-${idx}`} accessibilityRole="button" accessibilityLabel={tx('jobSearch.import.remove', 'Remove imported job')}>
              <Ionicons name="trash-outline" size={16} color={colors.textSecondary} />
            </TouchableOpacity>
          ) : null}
        </View>

        <View style={{ flexDirection: 'row', gap: 8, marginTop: 12, flexWrap: 'wrap' }}>
          <BillingActionButton
            label={matchingJobId === job.job_id ? tx('jobSearch.jobs.scoring', 'Scoring…') : tx('jobSearch.jobs.fitScore', 'AI fit score')}
            onPress={() => runMatch(job)}
            icon="analytics-outline"
            colors={colors}
            testId={`job-search-${prefix}-match-btn-${idx}`}
            disabled={Boolean(matchingJobId)}
          />
          <BillingActionButton
            label={tx('jobSearch.jobs.generateKit', 'Generate kit')}
            onPress={() => onGenerateKit(job.job_id, job.title)}
            icon="document-text-outline"
            colors={colors}
            variant="secondary"
            testId={`job-search-${prefix}-generate-btn-${idx}`}
          />
          <BillingActionButton
            label={trackingJobId === job.job_id ? tx('jobSearch.jobs.tracking', 'Adding…') : tx('jobSearch.jobs.track', 'Track')}
            onPress={() => trackJob(job)}
            icon="bookmark-outline"
            colors={colors}
            variant="subtle"
            testId={`job-search-${prefix}-track-btn-${idx}`}
            disabled={Boolean(trackingJobId)}
          />
          {external && job.source_url ? (
            <BillingActionButton
              label={tx('jobSearch.import.applyOnSite', 'Apply on site')}
              onPress={() => applyOnSite(job)}
              icon="open-outline"
              colors={colors}
              variant="secondary"
              testId={`job-search-apply-on-site-btn-${idx}`}
            />
          ) : null}
        </View>

        {appliedPromptJobId === job.job_id ? (
          <View style={{ marginTop: 12, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.background, borderRadius: 14, padding: 12, flexDirection: 'row', alignItems: 'center', gap: 10, flexWrap: 'wrap' }} data-testid={`job-search-applied-prompt-${idx}`} testID={`job-search-applied-prompt-${idx}`}>
            <Text style={{ color: colors.text, fontSize: 12.5, flex: 1, minWidth: 180, lineHeight: 18 }}>
              {tx('jobSearch.import.appliedPrompt', 'Did you submit your application on the site? Mark it as Applied.')}
            </Text>
            <BillingActionButton label={tx('jobSearch.docs.markApplied', 'Mark as Applied')} onPress={() => confirmApplied(job)} icon="checkmark-circle-outline" colors={colors} testId={`job-search-applied-confirm-${idx}`} />
            <TouchableOpacity onPress={() => setAppliedPromptJobId('')} data-testid={`job-search-applied-dismiss-${idx}`} testID={`job-search-applied-dismiss-${idx}`} accessibilityRole="button" accessibilityLabel={tx('jobSearch.docs.markAppliedDismiss', 'Dismiss')}>
              <Ionicons name="close" size={18} color={colors.textSecondary} />
            </TouchableOpacity>
          </View>
        ) : null}
      </BillingSectionCard>
    );
  };

  return (
    <View style={{ gap: 14 }}>
      <BillingSectionCard colors={colors} testId="job-search-import-card">
        <Text style={{ color: colors.text, fontSize: 17, fontWeight: '800' }}>{tx('jobSearch.import.title', 'Import a job from any job site')}</Text>
        <Text style={{ color: colors.textSecondary, fontSize: 12, lineHeight: 18, marginTop: 4, marginBottom: 10 }}>
          {tx('jobSearch.import.subtitle', 'Paste a job posting link — AI extracts the role so you can fit-score it, tailor your kit, and track the application.')}
        </Text>
        {portals.length > 0 ? (
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginBottom: 10 }} data-testid="job-search-portal-chips" testID="job-search-portal-chips">
            {portals.map((portal, pIdx) => (
              <View key={pIdx} style={{ backgroundColor: colors.background, borderWidth: 1, borderColor: colors.border, borderRadius: 999, paddingHorizontal: 10, paddingVertical: 4 }}>
                <Text style={{ color: colors.textSecondary, fontSize: 10.5, fontWeight: '700' }}>{portal}</Text>
              </View>
            ))}
          </View>
        ) : null}
        <View style={{ flexDirection: 'row', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
          <TextInput
            value={importUrl}
            onChangeText={setImportUrl}
            placeholder={tx('jobSearch.import.urlPlaceholder', 'https://www.linkedin.com/jobs/view/…')}
            placeholderTextColor={colors.muted}
            autoCapitalize="none"
            style={{ flex: 1, minWidth: 220, backgroundColor: colors.background, borderWidth: 1, borderColor: colors.border, borderRadius: 12, paddingHorizontal: 12, paddingVertical: 10, color: colors.text, fontSize: 13 }}
            data-testid="job-search-import-url-input"
            testID="job-search-import-url-input"
            accessibilityLabel={tx('jobSearch.import.urlPlaceholder', 'Job posting URL')}
          />
          <BillingActionButton
            label={importing && !pasteMode ? tx('jobSearch.import.importing', 'Importing…') : tx('jobSearch.import.import', 'Import job')}
            onPress={importJob}
            icon="link-outline"
            colors={colors}
            testId="job-search-import-btn"
            disabled={importing}
          />
        </View>
        {pasteMode ? (
          <View style={{ marginTop: 10, gap: 8 }}>
            <TextInput accessibilityLabel="Text input"
              value={pastedText}
              onChangeText={setPastedText}
              multiline
              numberOfLines={6}
              placeholder={tx('jobSearch.import.pastePlaceholder', 'Paste the full job description here…')}
              placeholderTextColor={colors.muted}
              style={{ backgroundColor: colors.background, borderWidth: 1, borderColor: colors.border, borderRadius: 12, paddingHorizontal: 12, paddingVertical: 10, color: colors.text, fontSize: 13, minHeight: 120, textAlignVertical: 'top' }}
              data-testid="job-search-import-paste-input"
              testID="job-search-import-paste-input"
              accessibilityLabel={tx('jobSearch.import.pastePlaceholder', 'Paste the full job description here…')}
            />
            <View style={{ flexDirection: 'row' }}>
              <BillingActionButton
                label={importing ? tx('jobSearch.import.importing', 'Importing…') : tx('jobSearch.import.extractPasted', 'Extract from pasted text')}
                onPress={importManual}
                icon="sparkles-outline"
                colors={colors}
                variant="secondary"
                testId="job-search-import-manual-btn"
                disabled={importing}
              />
            </View>
          </View>
        ) : null}
        {importMsg ? <Text style={{ color: colors.textSecondary, fontSize: 12, marginTop: 10 }} data-testid="job-search-import-status" testID="job-search-import-status">{importMsg}</Text> : null}
      </BillingSectionCard>

      {externalJobs.length > 0 ? (
        <View style={{ gap: 14 }} data-testid="job-search-external-list" testID="job-search-external-list">
          <Text style={{ color: colors.textSecondary, fontSize: 11, fontWeight: '800', textTransform: 'uppercase', letterSpacing: 0.6 }}>
            {tx('jobSearch.import.importedSection', 'Imported jobs')}
          </Text>
          {externalJobs.map((job, idx) => renderJobCard(job, idx, true))}
        </View>
      ) : null}

      <BillingSectionCard colors={colors} testId="job-search-search-card">
        <Text style={{ color: colors.text, fontSize: 17, fontWeight: '800' }}>{tx('jobSearch.jobs.title', 'Find jobs & evaluate fit')}</Text>
        <Text style={{ color: colors.textSecondary, fontSize: 12, lineHeight: 18, marginTop: 4, marginBottom: 12 }}>
          {tx('jobSearch.jobs.subtitle', 'Search live open roles, then run an honest 5-dimension AI fit score before you invest time applying.')}
        </Text>
        <View style={{ flexDirection: 'row', gap: 10, alignItems: 'center' }}>
          <TextInput
            value={query}
            onChangeText={setQuery}
            onSubmitEditing={() => loadJobs(query)}
            placeholder={tx('jobSearch.jobs.searchPlaceholder', 'Search title, team, or keyword…')}
            placeholderTextColor={colors.muted}
            style={{ flex: 1, backgroundColor: colors.background, borderWidth: 1, borderColor: colors.border, borderRadius: 12, paddingHorizontal: 12, paddingVertical: 10, color: colors.text, fontSize: 13 }}
            data-testid="job-search-query-input"
            testID="job-search-query-input"
            accessibilityLabel={tx('jobSearch.jobs.searchPlaceholder', 'Search title, team, or keyword…')}
          />
          <BillingActionButton label={tx('jobSearch.jobs.search', 'Search')} onPress={() => loadJobs(query)} icon="search-outline" colors={colors} testId="job-search-search-btn" />
          <BillingActionButton
            label={savingAlert ? tx('jobSearch.alerts.saving', 'Saving…') : tx('jobSearch.alerts.save', 'Save alert')}
            onPress={() => void saveAlert()}
            icon="notifications-outline"
            colors={colors}
            variant="subtle"
            testId="job-search-save-alert-btn"
            disabled={!query.trim() || savingAlert}
          />
        </View>
        {alerts.length > 0 ? (
          <View style={{ marginTop: 12 }} data-testid="job-search-alerts-section" testID="job-search-alerts-section">
            <Text style={{ color: colors.textSecondary, fontSize: 11, fontWeight: '800', textTransform: 'uppercase', marginBottom: 6 }}>
              {tx('jobSearch.alerts.title', 'Search alerts — new matches land in your weekly digest')}
            </Text>
            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6 }}>
              {alerts.map((alert, aIdx) => (
                <View key={alert.alert_id || aIdx} style={{ flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: colors.background, borderWidth: 1, borderColor: colors.border, borderRadius: 999, paddingHorizontal: 10, paddingVertical: 5 }} data-testid={`job-search-alert-chip-${aIdx}`} testID={`job-search-alert-chip-${aIdx}`}>
                  <Ionicons name="notifications-outline" size={12} color={colors.primary} />
                  <Text style={{ color: colors.text, fontSize: 11.5, fontWeight: '700' }} numberOfLines={1}>{alert.label}</Text>
                  {Number(alert.new_match_count) > 0 ? (
                    <View style={{ backgroundColor: colors.primary, borderRadius: 999, paddingHorizontal: 6, paddingVertical: 1 }} data-testid={`job-search-alert-new-count-${aIdx}`} testID={`job-search-alert-new-count-${aIdx}`}>
                      <Text style={{ color: colors.primaryText, fontSize: 10, fontWeight: '800' }}>{alert.new_match_count}</Text>
                    </View>
                  ) : null}
                  <TouchableOpacity onPress={() => void toggleAlertEmail(alert)} data-testid={`job-search-alert-email-toggle-${aIdx}`} testID={`job-search-alert-email-toggle-${aIdx}`} accessibilityRole="button" accessibilityLabel={tx('jobSearch.alerts.emailToggle', 'Toggle instant email for this alert')}>
                    <Ionicons name={alert.notify_email === false ? 'mail-unread-outline' : 'mail'} size={13} color={alert.notify_email === false ? colors.textSecondary : colors.primary} />
                  </TouchableOpacity>
                  <TouchableOpacity onPress={() => void deleteAlert(alert.alert_id)} data-testid={`job-search-alert-delete-${aIdx}`} testID={`job-search-alert-delete-${aIdx}`} accessibilityRole="button" accessibilityLabel={tx('jobSearch.alerts.delete', 'Delete alert')}>
                    <Ionicons name="close" size={13} color={colors.textSecondary} />
                  </TouchableOpacity>
                </View>
              ))}
            </View>
          </View>
        ) : null}
        {errorMsg ? <Text style={{ color: colors.error, fontSize: 12, marginTop: 10 }} data-testid="job-search-jobs-error" testID="job-search-jobs-error">{errorMsg}</Text> : null}
      </BillingSectionCard>

      {loading ? (
        <BillingSectionCard colors={colors} testId="job-search-jobs-loading"><ActivityIndicator color={colors.primary} /></BillingSectionCard>
      ) : jobs.length === 0 ? (
        <BillingSectionCard colors={colors} testId="job-search-jobs-empty">
          <Text style={{ color: colors.textSecondary, fontSize: 13 }}>{tx('jobSearch.jobs.empty', 'No open jobs match your search right now.')}</Text>
        </BillingSectionCard>
      ) : (
        jobs.map((job, idx) => renderJobCard(job, idx, false))
      )}
    </View>
  );
};
