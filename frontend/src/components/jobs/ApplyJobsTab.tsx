import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { View, Text, ScrollView, TouchableOpacity, TextInput, ActivityIndicator } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { useTheme } from '../../context/ThemeContext';

type ApplyJobsTabProps = {
  funnelFocusStage?: 'open-roles' | null;
  focusSignal?: number;
};

export const ApplyJobsTab = ({ funnelFocusStage = null, focusSignal = 0 }: ApplyJobsTabProps) => {
  const { colors } = useTheme();
  const scrollRef = useRef<ScrollView>(null);
  const [loading, setLoading] = useState(true);
  const [q, setQ] = useState('');
  const [location, setLocation] = useState('');
  const [skills, setSkills] = useState('');
  const [remoteOnly, setRemoteOnly] = useState(false);
  const [jobs, setJobs] = useState<any[]>([]);
  const [recs, setRecs] = useState<any[]>([]);
  const [savedIds, setSavedIds] = useState<Record<string, boolean>>({});
  const [applicationStatus, setApplicationStatus] = useState<Record<string, string>>({});
  const [expandedJobId, setExpandedJobId] = useState<string | null>(null);
  const [applyingJobId, setApplyingJobId] = useState<string | null>(null);
  const [savingJobId, setSavingJobId] = useState<string | null>(null);
  const [lastSyncAt, setLastSyncAt] = useState<string>('');
  const [searchPanelY, setSearchPanelY] = useState(0);
  const [focusTarget, setFocusTarget] = useState('');

  const recMap = useMemo(() => {
    const map: Record<string, any> = {};
    recs.forEach((item) => {
      if (item.job_id) map[item.job_id] = item;
    });
    return map;
  }, [recs]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const searchQuery = [q.trim(), skills.trim()].filter(Boolean).join(' ');
      const [jobsRes, recRes, appsRes, savedRes] = await Promise.all([
        api.get('/jobs/search', { params: { q: searchQuery, location: location.trim(), remote: remoteOnly ? 'true' : '' } }).catch(() => ({ data: { jobs: [] } })),
        api.get('/jobs/recommendations').catch(() => ({ data: { jobs: [] } })),
        api.get('/jobs/my-applications?status=all').catch(() => ({ data: { applications: [] } })),
        api.get('/jobs/saved').catch(() => ({ data: { saved_jobs: [] } })),
      ]);

      const apps = appsRes.data?.applications || [];
      const appMap: Record<string, string> = {};
      apps.forEach((app: any) => {
        if (app.job_id) appMap[app.job_id] = app.status || 'applied';
      });

      const saved: Record<string, boolean> = {};
      (savedRes.data?.saved_jobs || []).forEach((job: any) => {
        if (job.job_id) saved[job.job_id] = true;
      });

      setJobs(jobsRes.data?.jobs || []);
      setRecs(recRes.data?.jobs || []);
      setApplicationStatus(appMap);
      setSavedIds(saved);
      setLastSyncAt(new Date().toLocaleTimeString());
    } finally {
      setLoading(false);
    }
  }, [location, q, remoteOnly, skills]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    const timer = setInterval(() => {
      load();
    }, 30000);
    return () => clearInterval(timer);
  }, [load]);

  useEffect(() => {
    if (funnelFocusStage !== 'open-roles') return;
    setFocusTarget('search-panel');
    const timeout = setTimeout(() => setFocusTarget(''), 1800);
    scrollRef.current?.scrollTo({ y: Math.max(0, searchPanelY - 8), animated: true });
    return () => clearTimeout(timeout);
  }, [funnelFocusStage, focusSignal, searchPanelY]);

  const applyOneClick = async (jobId: string) => {
    setApplyingJobId(jobId);
    try {
      await api.post('/hiring/v2/candidate/apply', { job_id: jobId, cover_letter: '' });
      await load();
    } finally {
      setApplyingJobId(null);
    }
  };

  const toggleSave = async (jobId: string) => {
    setSavingJobId(jobId);
    try {
      await api.post(`/hiring/v2/candidate/save/${jobId}`);
      await load();
    } finally {
      setSavingJobId(null);
    }
  };

  const renderJobCard = (job: any, idx: number) => {
    const status = applicationStatus[job.job_id] || '';
    const isExpanded = expandedJobId === job.job_id;
    const rec = recMap[job.job_id] || {};
    const saved = Boolean(savedIds[job.job_id]);
    const applying = applyingJobId === job.job_id;
    const saving = savingJobId === job.job_id;

    return (
      <View key={job.job_id || idx} style={{ backgroundColor: colors.card, borderWidth: 1, borderColor: colors.border, borderRadius: 14, padding: 14 }} data-testid={`apply-job-card-${idx}`}>
        <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 10 }}>
          <View style={{ flex: 1 }}>
            <Text style={{ color: colors.text, fontSize: 15, fontWeight: '800' }}>{job.title || 'Untitled Role'}</Text>
            <Text style={{ color: colors.textMuted, fontSize: 12, marginTop: 2 }}>
              {job.company_name || 'Company'} • {job.location || 'Location N/A'} {job.remote ? '• Remote' : ''}
            </Text>
          </View>
          {rec.match_score != null && (
            <View style={{ backgroundColor: colors.successSoft, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(colors.success, '33'), borderRadius: 999, paddingHorizontal: 10, paddingVertical: 6 }} data-testid={`apply-job-match-${idx}`}>
              <Text style={{ color: colors.successText, fontSize: 11, fontWeight: '800' }}>{rec.match_score}% MATCH</Text>
            </View>
          )}
        </View>

        {!!status && (
          <View style={{ marginTop: 8, alignSelf: 'flex-start', backgroundColor: colors.primarySoft, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(colors.primary, '33'), borderRadius: 999, paddingHorizontal: 10, paddingVertical: 5 }} data-testid={`apply-job-status-${idx}`}>
            <Text style={{ color: colors.primary, fontSize: 11, fontWeight: '800' }}>STATUS: {status.toUpperCase()}</Text>
          </View>
        )}

        <View style={{ flexDirection: 'row', gap: 8, marginTop: 12 }}>
          <TouchableOpacity
            data-testid={`apply-job-details-btn-${idx}`}
            testID={`apply-job-details-btn-${idx}`}
            onPress={() => setExpandedJobId(isExpanded ? null : job.job_id)}
            style={{ flex: 1, backgroundColor: colors.bgSoft, borderWidth: 1, borderColor: colors.border, borderRadius: 10, paddingVertical: 10, alignItems: 'center' }}
          >
            <Text style={{ color: colors.textSec, fontSize: 12, fontWeight: '700' }}>{isExpanded ? 'Hide Details' : 'Job Details'}</Text>
          </TouchableOpacity>

          <TouchableOpacity
            data-testid={`apply-job-save-btn-${idx}`}
            testID={`apply-job-save-btn-${idx}`}
            onPress={() => toggleSave(job.job_id)}
            disabled={saving}
            style={{ flex: 1, backgroundColor: colors.bgSoft, borderWidth: 1, borderColor: colors.border, borderRadius: 10, paddingVertical: 10, alignItems: 'center' }}
          >
            <Text style={{ color: colors.textSec, fontSize: 12, fontWeight: '700' }}>{saving ? 'Saving...' : saved ? 'Saved' : 'Save Job'}</Text>
          </TouchableOpacity>

          <TouchableOpacity
            data-testid={`apply-job-one-click-btn-${idx}`}
            testID={`apply-job-one-click-btn-${idx}`}
            onPress={() => applyOneClick(job.job_id)}
            disabled={Boolean(status) || applying}
            style={{ flex: 1, backgroundColor: Boolean(status) ? colors.dim : colors.primary, borderRadius: 10, paddingVertical: 10, alignItems: 'center' }}
          >
            {applying ? <ActivityIndicator color={colors.primaryText} size="small" /> : (
              <Text style={{ color: colors.primaryText, fontSize: 12, fontWeight: '800' }}>{status ? 'Applied' : 'One-Click Apply'}</Text>
            )}
          </TouchableOpacity>
        </View>

        {isExpanded && (
          <View style={{ marginTop: 12, backgroundColor: colors.bgSoft, borderWidth: 1, borderColor: colors.border, borderRadius: 10, padding: 10 }} data-testid={`apply-job-details-panel-${idx}`}>
            <Text style={{ color: colors.textSec, fontSize: 12, lineHeight: 19 }}>{job.description || 'No description provided.'}</Text>
            {(job.salary_min || job.salary_max) && (
              <Text style={{ color: colors.text, fontSize: 12, fontWeight: '700', marginTop: 8 }}>
                Salary Insight: {job.salary_currency || 'USD'} {job.salary_min || 0} - {job.salary_max || 0}
              </Text>
            )}
            {!!rec.match_reason && <Text style={{ color: colors.info, fontSize: 12, marginTop: 8 }}>Compatibility Feedback: {rec.match_reason}</Text>}
          </View>
        )}
      </View>
    );
  };

  return (
    <ScrollView ref={scrollRef} contentContainerStyle={{ padding: 16, paddingBottom: 56, gap: 14 }} data-testid="apply-jobs-tab" testID="apply-jobs-tab">
      {focusTarget === 'search-panel' ? (
        <View style={{ backgroundColor: colors.primarySoft, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(colors.primary, '33'), borderRadius: 10, padding: 10 }} data-testid="apply-jobs-funnel-focus-banner" testID="apply-jobs-funnel-focus-banner">
          <Text style={{ color: colors.primary, fontSize: 12, fontWeight: '700' }}>Funnel focus: Open roles landed on live search filters.</Text>
        </View>
      ) : null}

      <View
        style={{
          backgroundColor: colors.card,
          borderWidth: focusTarget === 'search-panel' ? 2 : 1,
          borderColor: focusTarget === 'search-panel' ? colors.primary : colors.border,
          borderRadius: 14,
          padding: 14,
        }}
        onLayout={(event) => setSearchPanelY(event.nativeEvent.layout.y)}
        data-testid="apply-jobs-search-panel"
      >
        <Text style={{ color: colors.text, fontSize: 16, fontWeight: '800' }}>Apply Jobs</Text>
        <Text style={{ color: colors.textMuted, fontSize: 12, marginTop: 3 }}>Real-time listings + AI matching + one-click apply</Text>

        <View style={{ marginTop: 10, gap: 8 }}>
          <TextInput value={q} onChangeText={setQ} placeholder="Search role or company" placeholderTextColor={colors.textMuted} style={{ borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bgSoft, borderRadius: 10, paddingHorizontal: 12, paddingVertical: 11, color: colors.text }} data-testid="apply-jobs-search-input" />
          <TextInput value={location} onChangeText={setLocation} placeholder="Location" placeholderTextColor={colors.textMuted} style={{ borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bgSoft, borderRadius: 10, paddingHorizontal: 12, paddingVertical: 11, color: colors.text }} data-testid="apply-jobs-location-input" />
          <TextInput value={skills} onChangeText={setSkills} placeholder="Skills (comma-separated)" placeholderTextColor={colors.textMuted} style={{ borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bgSoft, borderRadius: 10, paddingHorizontal: 12, paddingVertical: 11, color: colors.text }} data-testid="apply-jobs-skills-input" />
          <TouchableOpacity onPress={() => setRemoteOnly((v) => !v)} data-testid="apply-jobs-remote-toggle" style={{ alignSelf: 'flex-start', borderWidth: 1, borderColor: remoteOnly ? colors.primary : colors.border, backgroundColor: remoteOnly ? colors.primarySoft : colors.bgSoft, borderRadius: 999, paddingHorizontal: 10, paddingVertical: 7 }}>
            <Text style={{ color: remoteOnly ? colors.primary : colors.textSec, fontSize: 12, fontWeight: '700' }}>{remoteOnly ? 'Remote Only: ON' : 'Remote Only: OFF'}</Text>
          </TouchableOpacity>
          <View style={{ flexDirection: 'row', gap: 8 }}>
            <TouchableOpacity onPress={load} data-testid="apply-jobs-search-button" style={{ flex: 1, backgroundColor: colors.primary, borderRadius: 10, paddingVertical: 11, alignItems: 'center' }}>
              <Text style={{ color: colors.primaryText, fontWeight: '800', fontSize: 12 }}>Search Jobs</Text>
            </TouchableOpacity>
            <TouchableOpacity onPress={load} data-testid="apply-jobs-refresh-button" style={{ flex: 1, backgroundColor: colors.bgSoft, borderWidth: 1, borderColor: colors.border, borderRadius: 10, paddingVertical: 11, alignItems: 'center' }}>
              <Text style={{ color: colors.textSec, fontWeight: '700', fontSize: 12 }}>Refresh Feed</Text>
            </TouchableOpacity>
          </View>
          <Text style={{ color: colors.textMuted, fontSize: 11 }}>Last sync: {lastSyncAt || '—'}</Text>
        </View>
      </View>

      {loading ? (
        <View style={{ paddingVertical: 30, alignItems: 'center' }} data-testid="apply-jobs-loading">
          <ActivityIndicator color={colors.primary} />
        </View>
      ) : (
        <View style={{ gap: 10 }}>
          {jobs.length === 0 ? (
            <View style={{ backgroundColor: colors.card, borderWidth: 1, borderColor: colors.border, borderRadius: 12, padding: 16 }} data-testid="apply-jobs-empty-state">
              <Text style={{ color: colors.text, fontSize: 14, fontWeight: '700' }}>No jobs matched these filters.</Text>
              <Text style={{ color: colors.textMuted, fontSize: 12, marginTop: 4 }}>Try broader search terms or disable remote-only filter.</Text>
            </View>
          ) : jobs.slice(0, 25).map(renderJobCard)}
        </View>
      )}
    </ScrollView>
  );
};

/* i18n-probe t('i18n.auto.probe') */
