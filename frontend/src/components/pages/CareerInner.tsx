import React, { useEffect, useState, useCallback, useMemo } from 'react';
import {
  View, Text, ScrollView, TextInput, TouchableOpacity,
  ActivityIndicator, RefreshControl, useWindowDimensions, Platform,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { useTheme } from '../../context/ThemeContext';
import api from '../../services/api';
import AppShell from '../AppShell';
import { CareerSkeleton } from '../SkeletonLoaders';
import { useAutoRefresh } from '../../hooks/useAutoRefresh';
import { useTranslation } from '../../hooks/useTranslation';
import { handleAppRecoverableError } from '../../utils/appRecoverableError';

type Tab = 'discover' | 'applications' | 'resume' | 'profile' | 'insights' | 'alerts';

const JOB_TYPES = ['full_time', 'part_time', 'contract', 'freelance', 'internship'];
const JOB_TYPE_LABELS: Record<string, string> = {
  full_time: 'Full Time', part_time: 'Part Time', contract: 'Contract',
  freelance: 'Freelance', internship: 'Internship', 'Full-time': 'Full Time',
  'Part-time': 'Part Time',
};

export function CareerContent() {
  const { colors } = useTheme();
  const { t } = useTranslation();
  const { width } = useWindowDimensions();
  const isWide = width >= 768;
  const isTablet = width >= 768 && width < 1024;
  const pad = isWide ? 24 : 16;
  const tx = useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);
  const careerTitle = t('career.header.title');

  const C = useMemo(() => ({
    ...colors,
    bg: colors.bg, bgSoft: colors.bgSoft, card: colors.card,
    text: colors.text, muted: colors.textMuted, border: colors.border,
    primary: colors.primary, success: colors.success,
    warning: colors.warning, error: colors.error,
    accent: colors.purple,
  }), [colors]);

  const [tab, setTab] = useState<Tab>('discover');
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  // Discover state
  const [jobs, setJobs] = useState<any[]>([]);
  const [searchQ, setSearchQ] = useState('');
  const [filterLocation, setFilterLocation] = useState('');
  const [filterType, setFilterType] = useState('');
  const [filterRemote, setFilterRemote] = useState(false);
  const [totalJobs, setTotalJobs] = useState(0);
  const [jobPage, setJobPage] = useState(1);
  const [searchLoading, setSearchLoading] = useState(false);
  const [recommendations, setRecommendations] = useState<any[]>([]);
  const [recLoading, setRecLoading] = useState(false);
  const [showRecs, setShowRecs] = useState(false);

  // Applications state
  const [applications, setApplications] = useState<any[]>([]);
  const [appStats, setAppStats] = useState<any>({});
  const [appFilter, setAppFilter] = useState('all');

  // Resume state
  const [resumeData, setResumeData] = useState<any>(null);
  const [uploading, setUploading] = useState(false);

  // Profile state
  const [, setProfile] = useState<any>(null);
  const [editSkills, setEditSkills] = useState('');
  const [editYears, setEditYears] = useState('');
  const [editLocation, setEditLocation] = useState('');
  const [editJobType, setEditJobType] = useState('');
  const [editIndustry, setEditIndustry] = useState('');
  const [editRemote, setEditRemote] = useState(false);
  const [profileSaving, setProfileSaving] = useState(false);

  // Analytics state
  const [analytics, setAnalytics] = useState<any>(null);

  // Alerts state
  const [alerts, setAlerts] = useState<any[]>([]);
  const [alertUnread, setAlertUnread] = useState(0);
  const [alertPrefs, setAlertPrefs] = useState<any>({ enabled: true, min_match_score: 20 });
  const [alertsLoading, setAlertsLoading] = useState(false);

  // Saved jobs
  const [savedIds, setSavedIds] = useState<Set<string>>(new Set());

  // Job detail modal
  const [selectedJob, setSelectedJob] = useState<any>(null);
  const [applyingJob, setApplyingJob] = useState(false);
  const [coverLetter, setCoverLetter] = useState('');

  const searchJobs = useCallback(async (page = 1) => {
    setSearchLoading(true);
    try {
      const params: any = { page, limit: 20 };
      if (searchQ) params.q = searchQ;
      if (filterLocation) params.location = filterLocation;
      if (filterType) params.job_type = filterType;
      if (filterRemote) params.remote = 'true';
      const res = await api.get('/jobs/search', { params });
      setJobs(prev => (page === 1 ? res.data.jobs : [...prev, ...res.data.jobs]));
      setTotalJobs(res.data.total);
      setJobPage(page);
    } catch (e) { console.warn('Job search error', e); }
    finally { setSearchLoading(false); setLoading(false); }
  }, [searchQ, filterLocation, filterType, filterRemote]);

  const loadRecommendations = async () => {
    setRecLoading(true);
    try {
      const res = await api.get('/jobs/recommendations');
      setRecommendations(res.data.jobs || []);
      setShowRecs(true);
    } catch (e) { console.warn('Rec error', e); }
    finally { setRecLoading(false); }
  };

  const loadApplications = useCallback(async () => {
    try {
      const res = await api.get('/jobs/my-applications', { params: { status: appFilter } });
      setApplications(res.data.applications || []);
      setAppStats(res.data.stats || {});
    } catch (e) { console.warn('Apps error', e); }
  }, [appFilter]);

  const loadProfile = async () => {
    try {
      const res = await api.get('/jobs/profile');
      const p = res.data.profile;
      setProfile(p);
      if (p) {
        setEditSkills((p.skills || []).join(', '));
        setEditYears(String(p.experience_years || ''));
        setEditLocation(p.preferred_location || '');
        setEditJobType(p.preferred_job_type || '');
        setEditIndustry(p.preferred_industry || '');
        setEditRemote(p.remote_only || false);
      }
    } catch (e) { console.warn('Profile error', e); }
  };

  const loadResume = async () => {
    try {
      const res = await api.get('/jobs/resume/score');
      setResumeData(res.data);
    } catch (e) { console.warn('Resume error', e); }
  };

  const loadAnalytics = async () => {
    try {
      const res = await api.get('/jobs/analytics');
      setAnalytics(res.data);
    } catch (e) { console.warn('Analytics error', e); }
  };

  const loadAlerts = async () => {
    setAlertsLoading(true);
    try {
      const res = await api.get('/jobs/alerts');
      setAlerts(res.data.alerts || []);
      setAlertUnread(res.data.unread_count || 0);
    } catch (e) { console.warn('Alerts error', e); }
    finally { setAlertsLoading(false); }
  };

  const loadAlertPrefs = async () => {
    try {
      const res = await api.get('/jobs/alerts/preferences');
      setAlertPrefs(res.data.preferences || { enabled: true, min_match_score: 20 });
    } catch (e) { console.warn('Alert prefs error', e); }
  };

  const markAlertRead = async (alertId: string) => {
    try {
      await api.post(`/hiring/v2/candidate/alerts/${alertId}/read`);
      setAlerts(prev => prev.map(a => a.alert_id === alertId ? { ...a, read: true } : a));
      setAlertUnread(prev => Math.max(0, prev - 1));
    } catch (error) { handleAppRecoverableError({ scope: 'src/components/pages/CareerInner.tsx#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
  };

  const markAllAlertsRead = async () => {
    try {
      await api.post('/hiring/v2/candidate/alerts/read-all');
      setAlerts(prev => prev.map(a => ({ ...a, read: true })));
      setAlertUnread(0);
    } catch (error) { handleAppRecoverableError({ scope: 'src/components/pages/CareerInner.tsx#catch2', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
  };

  const saveAlertPrefs = async () => {
    try {
      await api.post('/hiring/v2/candidate/alerts/preferences', alertPrefs);
      alert('Alert preferences saved!');
    } catch (e: any) { alert(e?.response?.data?.detail || 'Save failed'); }
  };

  const loadSaved = async () => {
    try {
      const res = await api.get('/jobs/saved');
      const ids = new Set<string>((res.data.saved_jobs || []).map((j: any) => j.job_id));
      setSavedIds(ids);
    } catch (error) { handleAppRecoverableError({ scope: 'src/components/pages/CareerInner.tsx#catch3', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
  };

  useAutoRefresh(loadRecommendations, { intervalMs: 30000 });

  useEffect(() => {
    searchJobs(1);
    loadSaved();
    loadAlerts();
  }, [searchJobs]);

  useEffect(() => {
    if (tab === 'applications') loadApplications();
    if (tab === 'resume') loadResume();
    if (tab === 'profile') loadProfile();
    if (tab === 'insights') { loadAnalytics(); loadApplications(); }
    if (tab === 'alerts') { loadAlerts(); loadAlertPrefs(); }
  }, [tab, appFilter, loadApplications]);

  const onRefresh = () => {
    setRefreshing(true);
    searchJobs(1).then(() => setRefreshing(false));
  };

  const saveJob = async (jobId: string) => {
    try {
      const res = await api.post(`/hiring/v2/candidate/save/${jobId}`);
      setSavedIds(prev => {
        const next = new Set(prev);
        if (res.data.saved) {
          next.add(jobId);
        } else {
          next.delete(jobId);
        }
        return next;
      });
    } catch (error) { handleAppRecoverableError({ scope: 'src/components/pages/CareerInner.tsx#catch4', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
  };

  const applyForJob = async () => {
    if (!selectedJob) return;
    setApplyingJob(true);
    try {
      await api.post('/hiring/v2/candidate/apply', {
        job_id: selectedJob.job_id,
        cover_letter: coverLetter || undefined,
      });
      alert('Application submitted successfully!');
      setSelectedJob(null);
      setCoverLetter('');
      loadApplications();
    } catch (e: any) {
      alert(e?.response?.data?.detail || 'Application failed');
    } finally { setApplyingJob(false); }
  };

  const saveProfile = async () => {
    setProfileSaving(true);
    try {
      await api.post('/hiring/v2/candidate/profile/update', {
        skills: editSkills.split(',').map(s => s.trim()).filter(Boolean),
        experience_years: editYears ? parseInt(editYears) : null,
        preferred_location: editLocation || null,
        preferred_job_type: editJobType || null,
        preferred_industry: editIndustry || null,
        remote_only: editRemote,
      });
      alert('Profile updated!');
      loadProfile();
    } catch (e: any) { alert(e?.response?.data?.detail || 'Save failed'); }
    finally { setProfileSaving(false); }
  };

  const uploadResume = async () => {
    if (Platform.OS !== 'web') {
      alert('Resume upload is available on desktop web.');
      return;
    }
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = '.pdf,.doc,.docx,.txt';
    input.onchange = async (e: any) => {
      const file = e.target.files?.[0];
      if (!file) return;
      setUploading(true);
      try {
        const formData = new FormData();
        formData.append('file', file);
        await api.post('/hiring/v2/candidate/resume/upload', formData, {
          headers: { 'Content-Type': 'multipart/form-data' },
        });
        alert('Resume uploaded! AI analysis in progress.');
        loadResume();
      } catch (err: any) { alert(err?.response?.data?.detail || 'Upload failed'); }
      finally { setUploading(false); }
    };
    input.click();
  };

  const tabs: { key: Tab; label: string; icon: string }[] = [
    { key: 'discover', label: tx('career.tabs.discover', 'Discover'), icon: 'search' },
    { key: 'applications', label: tx('career.tabs.applications', 'Applications'), icon: 'document-text' },
    { key: 'alerts', label: `${tx('career.tabs.alerts', 'Alerts')}${alertUnread > 0 ? ` (${alertUnread})` : ''}`, icon: 'notifications' },
    { key: 'resume', label: tx('career.tabs.resume', 'Resume'), icon: 'newspaper' },
    { key: 'profile', label: tx('career.tabs.profile', 'Profile'), icon: 'person-circle' },
    { key: 'insights', label: tx('career.tabs.insights', 'Insights'), icon: 'analytics' },
  ];

  const getSkills = (job: any) => job.skills || job.skills_required || [];
  const getIndustry = (job: any) => job.industry || job.category || '';

  const renderJobCard = (job: any, showScore = false) => {
    const isSaved = savedIds.has(job.job_id);
    return (
      <TouchableOpacity accessibilityLabel="Set selected job in career inner button"
        key={job.job_id}
        onPress={() => setSelectedJob(job)}
        style={{
          backgroundColor: C.card, borderRadius: 14, padding: 16,
          borderWidth: 1, borderColor: C.border, marginBottom: 12,
        }}
        data-testid={`job-card-${job.job_id}`} testID={`job-card-${job.job_id}`}
      >
        <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start' }}>
          <View style={{ flex: 1, marginRight: 12 }}>
            <Text style={{ color: C.text, fontSize: 15, fontWeight: '700' }}>{job.title}</Text>
            <Text style={{ color: C.primary, fontSize: 13, fontWeight: '600', marginTop: 2 }}>
              {job.company_name}
            </Text>
          </View>
          <TouchableOpacity
            onPress={() => saveJob(job.job_id)}
            data-testid={`save-job-${job.job_id}`} testID={`save-job-${job.job_id}`}
          >
            <Ionicons name={isSaved ? 'bookmark' : 'bookmark-outline'} size={22} color={isSaved ? C.warning : C.muted} />
          </TouchableOpacity>
        </View>

        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginTop: 10 }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4, backgroundColor: C.bgSoft, borderRadius: 6, paddingHorizontal: 8, paddingVertical: 3 }}>
            <Ionicons name="location-outline" size={12} color={C.muted} />
            <Text style={{ color: C.muted, fontSize: 11 }}>{job.location || 'Not specified'}</Text>
          </View>
          {job.remote && (
            <View style={{ backgroundColor: (globalThis as any).__alphaColor(C.success, '18'), borderRadius: 6, paddingHorizontal: 8, paddingVertical: 3 }}>
              <Text style={{ color: C.successText, fontSize: 11, fontWeight: '600' }}>Remote</Text>
            </View>
          )}
          <View style={{ backgroundColor: (globalThis as any).__alphaColor(C.primary, '15'), borderRadius: 6, paddingHorizontal: 8, paddingVertical: 3 }}>
            <Text style={{ color: C.primary, fontSize: 11, fontWeight: '600' }}>
              {JOB_TYPE_LABELS[job.job_type] || job.job_type || 'Full Time'}
            </Text>
          </View>
          {getIndustry(job) ? (
            <View style={{ backgroundColor: (globalThis as any).__alphaColor(C.accent, '15'), borderRadius: 6, paddingHorizontal: 8, paddingVertical: 3 }}>
              <Text style={{ color: C.accent, fontSize: 11, fontWeight: '600' }}>{getIndustry(job)}</Text>
            </View>
          ) : null}
        </View>

        {(job.salary_min || job.salary_max) && (
          <Text style={{ color: C.successText, fontSize: 13, fontWeight: '700', marginTop: 8 }}>
            {job.salary_currency || 'USD'} {job.salary_min?.toLocaleString()}{job.salary_max ? ` - ${job.salary_max.toLocaleString()}` : '+'}
          </Text>
        )}

        {getSkills(job).length > 0 && (
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 4, marginTop: 8 }}>
            {getSkills(job).slice(0, 5).map((s: string, i: number) => (
              <View key={i} style={{ backgroundColor: C.bgSoft, borderRadius: 4, paddingHorizontal: 6, paddingVertical: 2 }}>
                <Text style={{ color: C.muted, fontSize: 10 }}>{s}</Text>
              </View>
            ))}
          </View>
        )}

        {showScore && job.match_score && (
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginTop: 10, backgroundColor: (globalThis as any).__alphaColor(C.success, '12'), borderRadius: 8, padding: 8 }}>
            <Ionicons name="sparkles" size={14} color={C.successText} />
            <Text style={{ color: C.successText, fontSize: 12, fontWeight: '700' }}>{job.match_score}% Match</Text>
            {job.match_reason && <Text style={{ color: C.muted, fontSize: 11, flex: 1 }} numberOfLines={1}>{job.match_reason}</Text>}
          </View>
        )}
      </TouchableOpacity>
    );
  };

  if (loading) return (
    <AppShell>
      <CareerSkeleton />
    </AppShell>
  );

  const careerContent = (
      <SafeAreaView style={{ flex: 1, backgroundColor: C.bg }} edges={['top']}>
        {/* Job Detail Modal */}
        {selectedJob && (
          <View style={{
            position: 'absolute', top: 0, left: 0, right: 0, bottom: 0,
            backgroundColor: colors.overlay, zIndex: 100,
            justifyContent: 'center', alignItems: 'center', padding: 20,
          }}>
            <View style={{
              backgroundColor: C.card, borderRadius: 20, padding: 24,
              maxWidth: 600, width: '100%', maxHeight: '85%',
              borderWidth: 1, borderColor: C.border,
            }}>
              <ScrollView showsVerticalScrollIndicator={false}>
                <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
                  <Text style={{ color: C.text, fontSize: 20, fontWeight: '800', flex: 1, marginRight: 12 }} data-testid="job-detail-title" testID="job-detail-title">
                    {selectedJob.title}
                  </Text>
                  <TouchableOpacity onPress={() => setSelectedJob(null)} data-testid="job-detail-close" testID="job-detail-close">
                    <Ionicons name="close-circle" size={28} color={C.muted} />
                  </TouchableOpacity>
                </View>

                <Text style={{ color: C.primary, fontSize: 16, fontWeight: '700' }}>{selectedJob.company_name}</Text>

                <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 12 }}>
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}>
                    <Ionicons name="location" size={14} color={C.muted} />
                    <Text style={{ color: C.muted, fontSize: 13 }}>{selectedJob.location}</Text>
                  </View>
                  {selectedJob.remote && (
                    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}>
                      <Ionicons name="globe" size={14} color={C.successText} />
                      <Text style={{ color: C.successText, fontSize: 13 }}>Remote</Text>
                    </View>
                  )}
                </View>

                {(selectedJob.salary_min || selectedJob.salary_max) && (
                  <Text style={{ color: C.successText, fontSize: 16, fontWeight: '700', marginTop: 12 }}>
                    {selectedJob.salary_currency || 'USD'} {selectedJob.salary_min?.toLocaleString()}{selectedJob.salary_max ? ` - ${selectedJob.salary_max.toLocaleString()}` : '+'}
                  </Text>
                )}

                <View style={{ marginTop: 16, borderTopWidth: 1, borderTopColor: C.border, paddingTop: 16 }}>
                  <Text style={{ color: C.text, fontSize: 14, fontWeight: '700', marginBottom: 8 }}>Description</Text>
                  <Text style={{ color: C.muted, fontSize: 13, lineHeight: 20 }}>{selectedJob.description}</Text>
                </View>

                {selectedJob.requirements && (
                  <View style={{ marginTop: 12 }}>
                    <Text style={{ color: C.text, fontSize: 14, fontWeight: '700', marginBottom: 8 }}>Requirements</Text>
                    <Text style={{ color: C.muted, fontSize: 13, lineHeight: 20 }}>{selectedJob.requirements}</Text>
                  </View>
                )}

                {getSkills(selectedJob).length > 0 && (
                  <View style={{ marginTop: 12 }}>
                    <Text style={{ color: C.text, fontSize: 14, fontWeight: '700', marginBottom: 8 }}>Skills</Text>
                    <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6 }}>
                      {getSkills(selectedJob).map((s: string, i: number) => (
                        <View key={i} style={{ backgroundColor: (globalThis as any).__alphaColor(C.primary, '15'), borderRadius: 8, paddingHorizontal: 10, paddingVertical: 5 }}>
                          <Text style={{ color: C.primary, fontSize: 12, fontWeight: '600' }}>{s}</Text>
                        </View>
                      ))}
                    </View>
                  </View>
                )}

                {/* Apply Section */}
                <View style={{ marginTop: 20, borderTopWidth: 1, borderTopColor: C.border, paddingTop: 16 }}>
                  <Text style={{ color: C.text, fontSize: 14, fontWeight: '700', marginBottom: 8 }}>Cover Letter (Optional)</Text>
                  <TextInput
                    value={coverLetter}
                    onChangeText={setCoverLetter}
                    placeholder="Why are you a great fit for this role?"
                    placeholderTextColor={C.muted + '80'}
                    multiline
                    numberOfLines={4}
                    style={{
                      backgroundColor: C.bgSoft, color: C.text, borderRadius: 12,
                      padding: 14, fontSize: 13, borderWidth: 1, borderColor: C.border,
                      minHeight: 100, textAlignVertical: 'top',
                    }}
                    data-testid="job-cover-letter" testID="job-cover-letter"
                  />
                  <TouchableOpacity accessibilityLabel="Job apply button"
                    onPress={applyForJob}
                    disabled={applyingJob}
                    style={{
                      backgroundColor: C.primary, borderRadius: 12, paddingVertical: 14,
                      alignItems: 'center', marginTop: 12,
                    }}
                    data-testid="job-apply-btn" testID="job-apply-btn"
                  >
                    {applyingJob ? <ActivityIndicator color="var(--app-primary-text)" /> :
                      <Text style={{ color: colors.primaryText, fontSize: 15, fontWeight: '700' }}>Apply Now</Text>
                    }
                  </TouchableOpacity>
                </View>
              </ScrollView>
            </View>
          </View>
        )}

        <ScrollView
          showsVerticalScrollIndicator={false}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={C.primary} />}
          contentContainerStyle={{ paddingBottom: 40 }}
        >
          {/* Header */}
          <View style={{ paddingHorizontal: pad, paddingTop: 16, paddingBottom: 8 }}>
            <Text style={{ fontSize: 24, fontWeight: '800', color: C.text }} data-testid="career-title" testID="career-title">{careerTitle === 'career.header.title' ? 'Job Discovery' : careerTitle}</Text>
            <Text style={{ fontSize: 13, color: C.muted, marginTop: 2 }}>{tx('career.header.subtitle', 'Smart job search and career tools')}</Text>
          </View>

          {/* Tab Bar */}
          <View style={{ paddingHorizontal: pad, marginBottom: 16 }}>
            <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 8 }}>
              {tabs.map(t => (
                <TouchableOpacity accessibilityLabel="Set tab in career inner"
                  key={t.key}
                  onPress={() => setTab(t.key)}
                  style={{
                    flexDirection: 'row', alignItems: 'center', gap: 6,
                    paddingHorizontal: 16, paddingVertical: 10, borderRadius: 12,
                    backgroundColor: tab === t.key ? C.primary : C.bgSoft,
                    borderWidth: 1, borderColor: tab === t.key ? C.primary : C.border,
                  }}
                  data-testid={`career-tab-${t.key}`} testID={`career-tab-${t.key}`}
                >
                  <Ionicons name={t.icon as any} size={14} color={tab === t.key ? 'var(--app-primary-text)' : C.muted} />
                  <Text style={{ fontSize: 13, fontWeight: '700', color: tab === t.key ? 'var(--app-primary-text)' : C.muted }}>{t.label}</Text>
                </TouchableOpacity>
              ))}
            </ScrollView>
          </View>

          {/* === DISCOVER TAB === */}
          {tab === 'discover' && (
            <View style={{ paddingHorizontal: pad, gap: 12 }}>
              {/* Search Bar */}
              <View style={{ flexDirection: 'row', gap: 8 }}>
                <View style={{
                  flex: 1, flexDirection: 'row', alignItems: 'center', gap: 8,
                  backgroundColor: C.card, borderRadius: 12, paddingHorizontal: 14,
                  borderWidth: 1, borderColor: C.border,
                }}>
                  <Ionicons name="search" size={18} color={C.muted} />
                  <TextInput
                    value={searchQ}
                    onChangeText={setSearchQ}
                    placeholder="Job title, skills, company..."
                    placeholderTextColor={C.muted + '80'}
                    onSubmitEditing={() => searchJobs(1)}
                    style={{ flex: 1, color: C.text, fontSize: 14, paddingVertical: 12 }}
                    data-testid="career-search-input" testID="career-search-input"
                  />
                </View>
                <TouchableOpacity
                  onPress={() => searchJobs(1)}
                  style={{ backgroundColor: C.primary, borderRadius: 12, paddingHorizontal: 18, justifyContent: 'center' }}
                  data-testid="career-search-btn" testID="career-search-btn"
                >
                  <Ionicons name="search" size={18} color="var(--app-primary-text)" />
                </TouchableOpacity>
              </View>

              {/* Filters Row */}
              <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
                <View style={{
                  flex: 1, minWidth: 140, flexDirection: 'row', alignItems: 'center', gap: 6,
                  backgroundColor: C.card, borderRadius: 10, paddingHorizontal: 12,
                  borderWidth: 1, borderColor: C.border,
                }}>
                  <Ionicons name="location-outline" size={14} color={C.muted} />
                  <TextInput
                    value={filterLocation}
                    onChangeText={setFilterLocation}
                    placeholder="Location"
                    placeholderTextColor={C.muted + '80'}
                    onSubmitEditing={() => searchJobs(1)}
                    style={{ flex: 1, color: C.text, fontSize: 13, paddingVertical: 10 }}
                    data-testid="career-filter-location" testID="career-filter-location"
                  />
                </View>
                <TouchableOpacity accessibilityLabel="Career filter remote button"
                  onPress={() => setFilterRemote(!filterRemote)}
                  style={{
                    flexDirection: 'row', alignItems: 'center', gap: 6,
                    paddingHorizontal: 14, paddingVertical: 10, borderRadius: 10,
                    backgroundColor: filterRemote ? (globalThis as any).__alphaColor(C.success, '20') : C.card,
                    borderWidth: 1, borderColor: filterRemote ? C.success : C.border,
                  }}
                  data-testid="career-filter-remote" testID="career-filter-remote"
                >
                  <Ionicons name="globe-outline" size={14} color={filterRemote ? C.success : C.muted} />
                  <Text style={{ color: filterRemote ? C.success : C.muted, fontSize: 13, fontWeight: '600' }}>Remote</Text>
                </TouchableOpacity>
              </View>

              {/* Job Type Pills */}
              <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 6 }}>
                <TouchableOpacity accessibilityLabel="Career type all button"
                  onPress={() => { setFilterType(''); searchJobs(1); }}
                  style={{
                    paddingHorizontal: 14, paddingVertical: 8, borderRadius: 10,
                    backgroundColor: !filterType ? C.primary : C.bgSoft,
                    borderWidth: 1, borderColor: !filterType ? C.primary : C.border,
                  }}
                  data-testid="career-type-all" testID="career-type-all"
                >
                  <Text style={{ fontSize: 12, fontWeight: '600', color: !filterType ? 'var(--app-primary-text)' : C.muted }}>All Types</Text>
                </TouchableOpacity>
                {JOB_TYPES.map(t => (
                  <TouchableOpacity accessibilityLabel="Set filter type in career inner button"
                    key={t}
                    onPress={() => { setFilterType(filterType === t ? '' : t); setTimeout(() => searchJobs(1), 100); }}
                    style={{
                      paddingHorizontal: 14, paddingVertical: 8, borderRadius: 10,
                      backgroundColor: filterType === t ? C.primary : C.bgSoft,
                      borderWidth: 1, borderColor: filterType === t ? C.primary : C.border,
                    }}
                    data-testid={`career-type-${t}`} testID={`career-type-${t}`}
                  >
                    <Text style={{ fontSize: 12, fontWeight: '600', color: filterType === t ? 'var(--app-primary-text)' : C.muted }}>
                      {JOB_TYPE_LABELS[t]}
                    </Text>
                  </TouchableOpacity>
                ))}
              </ScrollView>

              {/* AI Recommendations Button */}
              <TouchableOpacity accessibilityLabel="Career ai recommend button"
                onPress={loadRecommendations}
                disabled={recLoading}
                style={{
                  flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8,
                  backgroundColor: (globalThis as any).__alphaColor(C.accent, '15'), borderRadius: 12, paddingVertical: 12,
                  borderWidth: 1, borderColor: (globalThis as any).__alphaColor(C.accent, '30'),
                }}
                data-testid="career-ai-recommend-btn" testID="career-ai-recommend-btn"
              >
                {recLoading ? <ActivityIndicator size="small" color={C.accent} /> : (
                  <>
                    <Ionicons name="sparkles" size={16} color={C.accent} />
                    <Text style={{ color: C.accent, fontSize: 14, fontWeight: '700' }}>AI Recommendations</Text>
                  </>
                )}
              </TouchableOpacity>

              {/* AI Recommendations */}
              {showRecs && recommendations.length > 0 && (
                <View style={{ backgroundColor: (globalThis as any).__alphaColor(C.accent, '08'), borderRadius: 14, padding: 14, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(C.accent, '20') }}>
                  <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
                    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                      <Ionicons name="sparkles" size={16} color={C.accent} />
                      <Text style={{ color: C.accent, fontSize: 14, fontWeight: '700' }}>{tx('career.search.aiMatchedForYou', 'AI-Matched For You')}</Text>
                    </View>
                    <TouchableOpacity onPress={() => setShowRecs(false)} data-testid="career-close-recs" testID="career-close-recs">
                      <Ionicons name="close" size={18} color={C.muted} />
                    </TouchableOpacity>
                  </View>
                  {recommendations.map(j => renderJobCard(j, true))}
                </View>
              )}

              {/* Results Count */}
              <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
                <Text style={{ color: C.muted, fontSize: 13 }} data-testid="career-results-count" testID="career-results-count">
                  {tx('career.search.jobsFound', '{count} jobs found').replace('{count}', String(totalJobs))}
                </Text>
              </View>

              {/* Job Listings */}
              {searchLoading && jobs.length === 0 ? (
                <ActivityIndicator size="large" color={C.primary} style={{ paddingVertical: 40 }} />
              ) : jobs.length === 0 ? (
                <View style={{ alignItems: 'center', paddingVertical: 40 }}>
                  <Ionicons name="briefcase-outline" size={48} color={C.muted} />
                  <Text style={{ color: C.muted, fontSize: 15, marginTop: 12 }}>{tx('career.search.noJobsFound', 'No jobs found')}</Text>
                  <Text style={{ color: C.muted, fontSize: 12, marginTop: 4 }}>{tx('career.search.adjustFilters', 'Try adjusting your search or filters')}</Text>
                </View>
              ) : (
                <>
                  {jobs.map(j => renderJobCard(j))}
                  {totalJobs > jobs.length && (
                    <TouchableOpacity accessibilityLabel="Career load more button"
                      onPress={() => searchJobs(jobPage + 1)}
                      disabled={searchLoading}
                      style={{
                        backgroundColor: C.card, borderRadius: 12, paddingVertical: 14,
                        alignItems: 'center', borderWidth: 1, borderColor: C.border,
                      }}
                      data-testid="career-load-more" testID="career-load-more"
                    >
                      {searchLoading ? <ActivityIndicator color={C.primary} /> :
                        <Text style={{ color: C.primary, fontSize: 14, fontWeight: '600' }}>Load More Jobs</Text>
                      }
                    </TouchableOpacity>
                  )}
                </>
              )}
            </View>
          )}

          {/* === APPLICATIONS TAB === */}
          {tab === 'applications' && (
            <View style={{ paddingHorizontal: pad, gap: 12 }}>
              {/* Status Pills */}
              <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 6 }}>
                {['all', 'applied', 'viewed', 'interview', 'offer', 'rejected'].map(s => {
                  const count = s === 'all' ? applications.length : (appStats[s] || 0);
                  const statusColors: Record<string, string> = {
                    all: C.primary, applied: colors.skeleton, viewed: colors.primary,
                    interview: colors.purple, offer: colors.success, rejected: colors.error,
                  };
                  return (
                    <TouchableOpacity accessibilityLabel="Set app filter in career inner button"
                      key={s}
                      onPress={() => setAppFilter(s)}
                      style={{
                        flexDirection: 'row', alignItems: 'center', gap: 6,
                        paddingHorizontal: 14, paddingVertical: 8, borderRadius: 10,
                        backgroundColor: appFilter === s ? (globalThis as any).__alphaColor(statusColors[s], '20') : C.bgSoft,
                        borderWidth: 1, borderColor: appFilter === s ? statusColors[s] : C.border,
                      }}
                      data-testid={`app-filter-${s}`} testID={`app-filter-${s}`}
                    >
                      <Text style={{ fontSize: 12, fontWeight: '700', color: appFilter === s ? statusColors[s] : C.muted, textTransform: 'capitalize' }}>
                        {s} {count > 0 ? `(${count})` : ''}
                      </Text>
                    </TouchableOpacity>
                  );
                })}
              </ScrollView>

              {/* Summary Cards */}
              <View style={{ flexDirection: 'row', gap: 10 }}>
                {[
                  { label: 'Total', value: applications.length, color: C.primary, icon: 'document-text' },
                  { label: 'Interview', value: appStats.interview || 0, color: colors.purpleText, icon: 'videocam' },
                  { label: 'Offer', value: appStats.offer || 0, color: C.successText, icon: 'checkmark-done' },
                ].map((c, i) => (
                  <View key={i} style={{ flex: 1, backgroundColor: C.card, borderRadius: 14, padding: 14, borderWidth: 1, borderColor: C.border, alignItems: 'center' }}>
                    <Ionicons name={c.icon as any} size={20} color={c.color} />
                    <Text style={{ color: C.text, fontSize: 20, fontWeight: '800', marginTop: 6 }}>{c.value}</Text>
                    <Text style={{ color: C.muted, fontSize: 11 }}>{c.label}</Text>
                  </View>
                ))}
              </View>

              {/* Application List */}
              {applications.length === 0 ? (
                <View style={{ alignItems: 'center', paddingVertical: 40 }}>
                  <Ionicons name="document-text-outline" size={48} color={C.muted} />
                  <Text style={{ color: C.muted, fontSize: 15, marginTop: 12 }}>No applications yet</Text>
                  <TouchableOpacity accessibilityLabel="Browse Jobs" onPress={() => setTab('discover')} style={{ marginTop: 12 }}>
                    <Text style={{ color: C.primary, fontSize: 14, fontWeight: '600' }}>Browse Jobs</Text>
                  </TouchableOpacity>
                </View>
              ) : applications.map((app, i) => {
                const statusColors: Record<string, string> = {
                  applied: colors.skeleton, viewed: colors.primary, interview: colors.purple,
                  offer: colors.success, rejected: colors.error,
                };
                const statusIcons: Record<string, string> = {
                  applied: 'paper-plane', viewed: 'eye', interview: 'videocam',
                  offer: 'checkmark-done-circle', rejected: 'close-circle',
                };
                return (
                  <View
                    key={app.application_id || i}
                    style={{
                      backgroundColor: C.card, borderRadius: 14, padding: 16,
                      borderWidth: 1, borderColor: C.border, marginBottom: 8,
                    }}
                    data-testid={`application-card-${i}`} testID={`application-card-${i}`}
                  >
                    <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
                      <View style={{ flex: 1 }}>
                        <Text style={{ color: C.text, fontSize: 15, fontWeight: '700' }}>{app.job_title}</Text>
                        <Text style={{ color: C.primary, fontSize: 13, marginTop: 2 }}>{app.company_name}</Text>
                      </View>
                      <View style={{
                        flexDirection: 'row', alignItems: 'center', gap: 4,
                        backgroundColor: (globalThis as any).__alphaColor((statusColors[app.status] || colors.skeleton), '18'),
                        borderRadius: 8, paddingHorizontal: 10, paddingVertical: 5,
                      }}>
                        <Ionicons name={(statusIcons[app.status] || 'ellipse') as any} size={14}
                          color={statusColors[app.status] || colors.textDim} />
                        <Text style={{
                          color: statusColors[app.status] || colors.textDim,
                          fontSize: 12, fontWeight: '700', textTransform: 'capitalize',
                        }}>{app.status}</Text>
                      </View>
                    </View>
                    <Text style={{ color: C.muted, fontSize: 11, marginTop: 8 }}>
                      Applied: {app.applied_at ? new Date(app.applied_at).toLocaleDateString() : 'N/A'}
                    </Text>
                  </View>
                );
              })}
            </View>
          )}

          {/* === RESUME TAB === */}
          {tab === 'resume' && (
            <View style={{ paddingHorizontal: pad, gap: 16 }}>
              {/* Upload Card */}
              <View style={{
                backgroundColor: C.card, borderRadius: 16, padding: 20,
                borderWidth: 1, borderColor: C.border, alignItems: 'center',
              }}>
                <Ionicons name="cloud-upload" size={40} color={C.primary} />
                <Text style={{ color: C.text, fontSize: 16, fontWeight: '700', marginTop: 12 }}>Upload Your Resume</Text>
                <Text style={{ color: C.muted, fontSize: 12, marginTop: 4, textAlign: 'center' }}>
                  PDF, DOC, DOCX, or TXT (max 5MB). AI will analyze and score your resume.
                </Text>
                <TouchableOpacity accessibilityLabel="Resume upload button"
                  onPress={uploadResume}
                  disabled={uploading}
                  style={{
                    backgroundColor: C.primary, borderRadius: 12, paddingVertical: 12,
                    paddingHorizontal: 32, marginTop: 16,
                  }}
                  data-testid="resume-upload-btn" testID="resume-upload-btn"
                >
                  {uploading ? <ActivityIndicator color="var(--app-primary-text)" /> :
                    <Text style={{ color: colors.primaryText, fontSize: 14, fontWeight: '700' }}>Choose File</Text>
                  }
                </TouchableOpacity>
              </View>

              {/* Resume Score */}
              {resumeData && (
                <>
                  <View style={{
                    backgroundColor: C.card, borderRadius: 16, padding: 20,
                    borderWidth: 1, borderColor: C.border, alignItems: 'center',
                  }} data-testid="resume-score-card" testID="resume-score-card">
                    <Text style={{ color: C.muted, fontSize: 13, fontWeight: '600' }}>Resume Score</Text>
                    <View style={{
                      width: 100, height: 100, borderRadius: 50, borderWidth: 6,
                      borderColor: resumeData.score >= 70 ? C.success : resumeData.score >= 40 ? C.warning : C.error,
                      alignItems: 'center', justifyContent: 'center', marginTop: 12,
                    }}>
                      <Text style={{
                        fontSize: 32, fontWeight: '800',
                        color: resumeData.score >= 70 ? C.success : resumeData.score >= 40 ? C.warning : C.error,
                      }}>
                        {resumeData.score || 0}
                      </Text>
                    </View>
                    <Text style={{ color: C.muted, fontSize: 12, marginTop: 8 }}>
                      {resumeData.has_resume ? 'AI-analyzed score' : 'Upload a resume to get your score'}
                    </Text>
                  </View>

                  {/* AI Analysis */}
                  {resumeData.analysis && (
                    <>
                      {resumeData.analysis.strengths?.length > 0 && (
                        <View style={{
                          backgroundColor: (globalThis as any).__alphaColor(C.success, '10'), borderRadius: 14, padding: 16,
                          borderWidth: 1, borderColor: (globalThis as any).__alphaColor(C.success, '30'),
                        }} data-testid="resume-strengths" testID="resume-strengths">
                          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 10 }}>
                            <Ionicons name="checkmark-circle" size={18} color={C.successText} />
                            <Text style={{ color: C.successText, fontSize: 14, fontWeight: '700' }}>Strengths</Text>
                          </View>
                          {resumeData.analysis.strengths.map((s: string, i: number) => (
                            <Text key={i} style={{ color: C.text, fontSize: 13, marginBottom: 4, paddingLeft: 26 }}>{s}</Text>
                          ))}
                        </View>
                      )}
                      {resumeData.analysis.improvements?.length > 0 && (
                        <View style={{
                          backgroundColor: (globalThis as any).__alphaColor(C.warning, '10'), borderRadius: 14, padding: 16,
                          borderWidth: 1, borderColor: (globalThis as any).__alphaColor(C.warning, '30'),
                        }} data-testid="resume-improvements" testID="resume-improvements">
                          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 10 }}>
                            <Ionicons name="alert-circle" size={18} color={C.warningText} />
                            <Text style={{ color: C.warningText, fontSize: 14, fontWeight: '700' }}>Improvements</Text>
                          </View>
                          {resumeData.analysis.improvements.map((s: string, i: number) => (
                            <Text key={i} style={{ color: C.text, fontSize: 13, marginBottom: 4, paddingLeft: 26 }}>{s}</Text>
                          ))}
                        </View>
                      )}
                    </>
                  )}

                  {/* Detected Skills */}
                  {resumeData.profile?.skills?.length > 0 && (
                    <View style={{
                      backgroundColor: C.card, borderRadius: 14, padding: 16,
                      borderWidth: 1, borderColor: C.border,
                    }} data-testid="resume-detected-skills" testID="resume-detected-skills">
                      <Text style={{ color: C.text, fontSize: 14, fontWeight: '700', marginBottom: 10 }}>Detected Skills</Text>
                      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6 }}>
                        {resumeData.profile.skills.map((s: string, i: number) => (
                          <View key={i} style={{ backgroundColor: (globalThis as any).__alphaColor(C.primary, '15'), borderRadius: 8, paddingHorizontal: 10, paddingVertical: 5 }}>
                            <Text style={{ color: C.primary, fontSize: 12, fontWeight: '600' }}>{s}</Text>
                          </View>
                        ))}
                      </View>
                    </View>
                  )}
                </>
              )}
            </View>
          )}

          {/* === PROFILE TAB === */}
          {tab === 'profile' && (
            <View style={{ paddingHorizontal: pad, gap: 16 }}>
              <View style={{
                backgroundColor: C.card, borderRadius: 16, padding: 20,
                borderWidth: 1, borderColor: C.border,
              }}>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 16 }}>
                  <Ionicons name="person-circle" size={28} color={C.primary} />
                  <Text style={{ color: C.text, fontSize: 16, fontWeight: '700' }}>Job Preferences</Text>
                </View>
                <Text style={{ color: C.muted, fontSize: 12, marginBottom: 16 }}>
                  Update your profile for better AI-powered job matches
                </Text>

                {[
                  { label: 'Skills (comma separated)', value: editSkills, setter: setEditSkills, placeholder: 'Python, React, Data Analysis', testId: 'profile-skills' },
                  { label: 'Years of Experience', value: editYears, setter: setEditYears, placeholder: '3', testId: 'profile-years', keyboard: 'numeric' as const },
                  { label: 'Preferred Location', value: editLocation, setter: setEditLocation, placeholder: 'Remote, New York, etc.', testId: 'profile-location' },
                  { label: 'Preferred Industry', value: editIndustry, setter: setEditIndustry, placeholder: 'Technology, Finance, etc.', testId: 'profile-industry' },
                ].map(field => (
                  <View key={field.testId} style={{ marginBottom: 12 }}>
                    <Text style={{ color: C.muted, fontSize: 11, fontWeight: '600', marginBottom: 4 }}>{field.label}</Text>
                    <TextInput
                      value={field.value}
                      onChangeText={field.setter}
                      placeholder={field.placeholder}
                      placeholderTextColor={C.muted + '80'}
                      keyboardType={field.keyboard}
                      style={{
                        backgroundColor: C.bgSoft, color: C.text, borderRadius: 10,
                        padding: 12, fontSize: 13, borderWidth: 1, borderColor: C.border,
                      }}
                      data-testid={field.testId} testID={field.testId}
                    />
                  </View>
                ))}

                {/* Job Type Selection */}
                <View style={{ marginBottom: 12 }}>
                  <Text style={{ color: C.muted, fontSize: 11, fontWeight: '600', marginBottom: 6 }}>Preferred Job Type</Text>
                  <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6 }}>
                    {JOB_TYPES.map(t => (
                      <TouchableOpacity accessibilityLabel="Set edit job type in career inner button"
                        key={t}
                        onPress={() => setEditJobType(editJobType === t ? '' : t)}
                        style={{
                          paddingHorizontal: 14, paddingVertical: 8, borderRadius: 10,
                          backgroundColor: editJobType === t ? C.primary : C.bgSoft,
                          borderWidth: 1, borderColor: editJobType === t ? C.primary : C.border,
                        }}
                        data-testid={`profile-type-${t}`} testID={`profile-type-${t}`}
                      >
                        <Text style={{ fontSize: 12, fontWeight: '600', color: editJobType === t ? 'var(--app-primary-text)' : C.muted }}>
                          {JOB_TYPE_LABELS[t]}
                        </Text>
                      </TouchableOpacity>
                    ))}
                  </View>
                </View>

                {/* Remote Toggle */}
                <TouchableOpacity accessibilityLabel="Profile remote toggle button"
                  onPress={() => setEditRemote(!editRemote)}
                  style={{
                    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
                    backgroundColor: C.bgSoft, borderRadius: 10, padding: 14,
                    borderWidth: 1, borderColor: C.border, marginBottom: 16,
                  }}
                  data-testid="profile-remote-toggle" testID="profile-remote-toggle"
                >
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                    <Ionicons name="globe" size={18} color={editRemote ? C.success : C.muted} />
                    <Text style={{ color: C.text, fontSize: 14, fontWeight: '600' }}>Remote Only</Text>
                  </View>
                  <View style={{
                    width: 44, height: 24, borderRadius: 12,
                    backgroundColor: editRemote ? C.success : C.border,
                    justifyContent: 'center', paddingHorizontal: 2,
                  }}>
                    <View style={{
                      width: 20, height: 20, borderRadius: 10, backgroundColor: colors.primaryText,
                      alignSelf: editRemote ? 'flex-end' : 'flex-start',
                    }} />
                  </View>
                </TouchableOpacity>

                <TouchableOpacity
                  onPress={saveProfile}
                  disabled={profileSaving}
                  style={{ backgroundColor: C.primary, borderRadius: 12, paddingVertical: 14, alignItems: 'center' }}
                  data-testid="profile-save-btn" testID="profile-save-btn"
                >
                  {profileSaving ? <ActivityIndicator color="var(--app-primary-text)" /> :
                    <Text style={{ color: colors.primaryText, fontSize: 15, fontWeight: '700' }}>Save Profile</Text>
                  }
                </TouchableOpacity>
              </View>
            </View>
          )}

          {/* === INSIGHTS TAB === */}
          {tab === 'insights' && (
            <View style={{ paddingHorizontal: pad, gap: 16 }}>
              {!analytics ? (
                <ActivityIndicator size="large" color={C.primary} style={{ paddingVertical: 40 }} />
              ) : (
                <>
                  {/* Stats Grid */}
                  <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10 }}>
                    {[
                      { label: 'Applications', value: analytics.total_applications, icon: 'paper-plane', color: C.primary },
                      { label: 'Response Rate', value: `${analytics.response_rate}%`, icon: 'chatbubble', color: colors.purpleText },
                      { label: 'Interview Rate', value: `${analytics.interview_rate}%`, icon: 'videocam', color: C.successText },
                      { label: 'Saved Jobs', value: analytics.saved_jobs, icon: 'bookmark', color: C.warningText },
                      { label: 'Resume Score', value: analytics.resume_score || '-', icon: 'newspaper', color: C.accent },
                      { label: 'Profile', value: analytics.profile_complete ? 'Complete' : 'Incomplete', icon: 'person', color: analytics.profile_complete ? C.success : C.error },
                    ].map((stat, i) => (
                      <View
                        key={i}
                        style={{
                          width: isWide ? (isTablet ? '47%' : '31%') : '47%', backgroundColor: C.card,
                          borderRadius: 14, padding: 16, borderWidth: 1, borderColor: C.border,
                        }}
                        data-testid={`insight-stat-${i}`} testID={`insight-stat-${i}`}
                      >
                        <View style={{
                          width: 36, height: 36, borderRadius: 10,
                          backgroundColor: (globalThis as any).__alphaColor(stat.color, '15'), alignItems: 'center', justifyContent: 'center',
                          marginBottom: 10,
                        }}>
                          <Ionicons name={stat.icon as any} size={18} color={stat.color} />
                        </View>
                        <Text style={{ color: C.text, fontSize: 20, fontWeight: '800' }}>{stat.value}</Text>
                        <Text style={{ color: C.muted, fontSize: 11, marginTop: 2 }}>{stat.label}</Text>
                      </View>
                    ))}
                  </View>

                  {/* Status Breakdown */}
                  {Object.keys(analytics.status_breakdown).length > 0 && (
                    <View style={{
                      backgroundColor: C.card, borderRadius: 16, padding: 16,
                      borderWidth: 1, borderColor: C.border,
                    }} data-testid="insight-status-breakdown" testID="insight-status-breakdown">
                      <Text style={{ color: C.text, fontSize: 15, fontWeight: '700', marginBottom: 14 }}>Application Status</Text>
                      {Object.entries(analytics.status_breakdown).map(([status, count]: any, i: number) => {
                        const total = analytics.total_applications || 1;
                        const pct = Math.round((count / total) * 100);
                        const barColor: Record<string, string> = {
                          applied: colors.skeleton, viewed: colors.primary, interview: colors.purple,
                          offer: colors.success, rejected: colors.error,
                        };
                        return (
                          <View key={status} style={{ marginBottom: 10 }}>
                            <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginBottom: 4 }}>
                              <Text style={{ color: C.text, fontSize: 13, fontWeight: '600', textTransform: 'capitalize' }}>{status}</Text>
                              <Text style={{ color: barColor[status] || C.primary, fontSize: 13, fontWeight: '700' }}>{count} ({pct}%)</Text>
                            </View>
                            <View style={{ height: 6, backgroundColor: C.bgSoft, borderRadius: 999, overflow: 'hidden' }}>
                              <View style={{
                                height: '100%', width: `${pct}%`,
                                backgroundColor: barColor[status] || C.primary, borderRadius: 999,
                              }} />
                            </View>
                          </View>
                        );
                      })}
                    </View>
                  )}

                  {/* Monthly Trend */}
                  {analytics.monthly_applications?.length > 0 && (
                    <View style={{
                      backgroundColor: C.card, borderRadius: 16, padding: 16,
                      borderWidth: 1, borderColor: C.border,
                    }} data-testid="insight-monthly-trend" testID="insight-monthly-trend">
                      <Text style={{ color: C.text, fontSize: 15, fontWeight: '700', marginBottom: 14 }}>Monthly Applications</Text>
                      <View style={{ flexDirection: 'row', alignItems: 'flex-end', gap: 6, height: 80 }}>
                        {analytics.monthly_applications.map((m: any, i: number) => {
                          const maxC = Math.max(...analytics.monthly_applications.map((x: any) => x.count), 1);
                          const h = Math.max(8, (m.count / maxC) * 70);
                          return (
                            <View key={i} style={{ flex: 1, alignItems: 'center' }}>
                              <Text style={{ color: C.muted, fontSize: 9, marginBottom: 2 }}>{m.count}</Text>
                              <View style={{ height: h, width: '80%', backgroundColor: C.primary, borderRadius: 4, minWidth: 16 }} />
                              <Text style={{ color: C.muted, fontSize: 9, marginTop: 4 }}>{m.month?.slice(5)}</Text>
                            </View>
                          );
                        })}
                      </View>
                    </View>
                  )}

                  {/* Tips */}
                  <View style={{
                    backgroundColor: (globalThis as any).__alphaColor(C.accent, '10'), borderRadius: 14, padding: 16,
                    borderWidth: 1, borderColor: (globalThis as any).__alphaColor(C.accent, '25'),
                  }} data-testid="insight-tips" testID="insight-tips">
                    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 10 }}>
                      <Ionicons name="bulb" size={18} color={C.accent} />
                      <Text style={{ color: C.accent, fontSize: 14, fontWeight: '700' }}>Career Tips</Text>
                    </View>
                    {[
                      !analytics.profile_complete && 'Complete your profile with skills for AI-powered recommendations',
                      analytics.resume_score === 0 && 'Upload your resume to get an AI score and improvement tips',
                      analytics.total_applications < 5 && 'Apply to more jobs to increase your chances',
                      analytics.response_rate < 20 && 'Customize your cover letters for better response rates',
                    ].filter(Boolean).map((tip, i) => (
                      <View key={i} style={{ flexDirection: 'row', gap: 8, marginBottom: 6, paddingLeft: 4 }}>
                        <Ionicons name="chevron-forward" size={14} color={C.accent} style={{ marginTop: 1 }} />
                        <Text style={{ color: C.text, fontSize: 13, flex: 1 }}>{tip}</Text>
                      </View>
                    ))}
                  </View>
                </>
              )}
            </View>
          )}

          {/* === ALERTS TAB === */}
          {tab === 'alerts' && (
            <View style={{ paddingHorizontal: pad, gap: 16 }}>
              {/* Alert Preferences */}
              <View style={{
                backgroundColor: C.card, borderRadius: 14, padding: 16,
                borderWidth: 1, borderColor: C.border,
              }} data-testid="alert-prefs-card" testID="alert-prefs-card">
                <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                    <Ionicons name="notifications" size={18} color={C.primary} />
                    <Text style={{ color: C.text, fontSize: 15, fontWeight: '700' }}>Smart Alerts</Text>
                  </View>
                  <TouchableOpacity
                    onPress={() => { setAlertPrefs((p: any) => ({ ...p, enabled: !p.enabled })); }}
                    data-testid="alerts-toggle" testID="alerts-toggle"
                  >
                    <View style={{
                      width: 44, height: 24, borderRadius: 12,
                      backgroundColor: alertPrefs.enabled ? C.success : C.border,
                      justifyContent: 'center', paddingHorizontal: 2,
                    }}>
                      <View style={{
                        width: 20, height: 20, borderRadius: 10, backgroundColor: colors.primaryText,
                        alignSelf: alertPrefs.enabled ? 'flex-end' : 'flex-start',
                      }} />
                    </View>
                  </TouchableOpacity>
                </View>
                <Text style={{ color: C.muted, fontSize: 12, marginTop: 6 }}>
                  Get notified when new jobs match your profile
                </Text>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, marginTop: 10 }}>
                  <Text style={{ color: C.muted, fontSize: 12 }}>Min match score:</Text>
                  <View style={{ flexDirection: 'row', gap: 4 }}>
                    {[10, 20, 40, 60, 80].map(s => (
                      <TouchableOpacity accessibilityLabel="Set alert prefs in career inner button"
                        key={s}
                        onPress={() => setAlertPrefs((p: any) => ({ ...p, min_match_score: s }))}
                        style={{
                          paddingHorizontal: 10, paddingVertical: 5, borderRadius: 8,
                          backgroundColor: alertPrefs.min_match_score === s ? C.primary : C.bgSoft,
                          borderWidth: 1, borderColor: alertPrefs.min_match_score === s ? C.primary : C.border,
                        }}
                        data-testid={`alert-score-${s}`} testID={`alert-score-${s}`}
                      >
                        <Text style={{ fontSize: 11, fontWeight: '600', color: alertPrefs.min_match_score === s ? 'var(--app-primary-text)' : C.muted }}>{s}%</Text>
                      </TouchableOpacity>
                    ))}
                  </View>
                </View>
                <TouchableOpacity
                  onPress={saveAlertPrefs}
                  style={{ backgroundColor: C.primary, borderRadius: 10, paddingVertical: 10, alignItems: 'center', marginTop: 12 }}
                  data-testid="alert-prefs-save" testID="alert-prefs-save"
                >
                  <Text style={{ color: colors.primaryText, fontSize: 13, fontWeight: '700' }}>Save Preferences</Text>
                </TouchableOpacity>
              </View>

              {/* Mark All Read */}
              {alertUnread > 0 && (
                <TouchableOpacity
                  onPress={markAllAlertsRead}
                  style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, paddingVertical: 8 }}
                  data-testid="alerts-mark-all-read" testID="alerts-mark-all-read"
                >
                  <Ionicons name="checkmark-done" size={16} color={C.primary} />
                  <Text style={{ color: C.primary, fontSize: 13, fontWeight: '600' }}>Mark all as read ({alertUnread})</Text>
                </TouchableOpacity>
              )}

              {/* Alert List */}
              {alertsLoading ? (
                <ActivityIndicator size="large" color={C.primary} style={{ paddingVertical: 40 }} />
              ) : alerts.length === 0 ? (
                <View style={{ alignItems: 'center', paddingVertical: 40 }}>
                  <Ionicons name="notifications-off-outline" size={48} color={C.muted} />
                  <Text style={{ color: C.muted, fontSize: 15, marginTop: 12 }}>No alerts yet</Text>
                  <Text style={{ color: C.muted, fontSize: 12, marginTop: 4, textAlign: 'center' }}>
                    Update your profile with skills to get matched with new job postings
                  </Text>
                </View>
              ) : alerts.map((a, i) => (
                <TouchableOpacity accessibilityLabel="A in career inner button"
                  key={a.alert_id || i}
                  onPress={() => {
                    if (!a.read) markAlertRead(a.alert_id);
                    // Find the job and show detail
                    const matchedJob = jobs.find(j => j.job_id === a.job_id);
                    if (matchedJob) setSelectedJob(matchedJob);
                  }}
                  style={{
                    backgroundColor: (globalThis as any).__alphaColor(a.read ? C.card : C.primary, '08'),
                    borderRadius: 14, padding: 16,
                    borderWidth: 1, borderColor: (globalThis as any).__alphaColor(a.read ? C.border : C.primary, '30'),
                  }}
                  data-testid={`alert-card-${i}`} testID={`alert-card-${i}`}
                >
                  <View style={{ flexDirection: 'row', alignItems: 'flex-start', gap: 12 }}>
                    <View style={{
                      width: 36, height: 36, borderRadius: 10,
                      backgroundColor: (globalThis as any).__alphaColor(a.read ? C.bgSoft : C.primary, '15'),
                      alignItems: 'center', justifyContent: 'center',
                    }}>
                      <Ionicons name="sparkles" size={18} color={a.read ? C.muted : C.primary} />
                    </View>
                    <View style={{ flex: 1 }}>
                      <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
                        <Text style={{ color: C.text, fontSize: 14, fontWeight: a.read ? '600' : '700', flex: 1 }}>
                          {a.job_title}
                        </Text>
                        <View style={{
                          backgroundColor: (globalThis as any).__alphaColor(C.success, '15'), borderRadius: 6,
                          paddingHorizontal: 8, paddingVertical: 3,
                        }}>
                          <Text style={{ color: C.successText, fontSize: 11, fontWeight: '700' }}>{a.match_score}%</Text>
                        </View>
                      </View>
                      <Text style={{ color: C.primary, fontSize: 12, fontWeight: '600', marginTop: 2 }}>
                        {a.company_name}
                      </Text>
                      {a.match_reasons?.length > 0 && (
                        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 4, marginTop: 6 }}>
                          {a.match_reasons.map((r: string, ri: number) => (
                            <View key={ri} style={{ backgroundColor: C.bgSoft, borderRadius: 4, paddingHorizontal: 6, paddingVertical: 2 }}>
                              <Text style={{ color: C.muted, fontSize: 10 }}>{r}</Text>
                            </View>
                          ))}
                        </View>
                      )}
                      <Text style={{ color: C.muted, fontSize: 10, marginTop: 6 }}>
                        {a.created_at ? new Date(a.created_at).toLocaleString() : ''}
                      </Text>
                    </View>
                    {!a.read && (
                      <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: C.primary, marginTop: 4 }} />
                    )}
                  </View>
                </TouchableOpacity>
              ))}
            </View>
          )}
        </ScrollView>
      </SafeAreaView>
  );

  return careerContent;
}

// Career Hub has been merged into Global Job Platform
// This page redirects to /job-platform for backward compatibility
export default function CareerPage() {
  const router = useRouter();
  React.useEffect(() => {
    router.replace('/job-platform' as any);
  }, [router]);
  return null;
}
