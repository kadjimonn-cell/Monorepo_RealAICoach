/* eslint-disable react-hooks/exhaustive-deps */
import React, { useEffect, useRef, useState } from 'react';
import { View, Text, ScrollView, TouchableOpacity, TextInput, StyleSheet, Alert, ActivityIndicator } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import AppShell from '../../src/components/AppShell';
import { useTheme } from '../../src/context/ThemeContext';
import { useAuth } from '../../src/context/AuthContext';
import api from '../../src/services/api';
import { useAutoRefresh } from '../../src/hooks/useAutoRefresh';
import { useTranslation } from '../../src/hooks/useTranslation';
import JobsPortalPage from '../job-platform';
import { handleAppRecoverableError } from '../../src/utils/appRecoverableError';

const JOB_CATEGORIES = ['Engineering', 'Design', 'Marketing', 'Operations', 'Sales', 'Finance', 'HR'];
const JOB_TYPES = ['Full-time', 'Part-time', 'Contract', 'Remote'];

type ApprovalKycUpload = {
  document_key: 'business_registration' | 'id_front' | 'id_back';
  doc_id: string;
  filename: string;
  original_filename: string;
  content_type: string;
  file_size: number;
  storage_path: string;
};

async function uploadApprovalDocument(
  file: File,
  documentKey: ApprovalKycUpload['document_key'],
): Promise<ApprovalKycUpload> {
  const allowed = ['application/pdf', 'image/jpeg', 'image/png', 'image/webp'];
  const normalizedType = file.type === 'image/jpg' ? 'image/jpeg' : file.type;
  if (!allowed.includes(normalizedType)) throw new Error('Invalid file type. Allowed: PDF, JPG, PNG, WebP');
  if (file.size > 10 * 1024 * 1024) throw new Error('File too large. Maximum: 10MB');
  if (file.size < 1024) throw new Error('File too small or empty');

  const formData = new FormData();
  formData.append('document_key', documentKey);
  formData.append('file', file);

  const response = await fetch(`${process.env.REACT_APP_BACKEND_URL}/api/jobs/employer/approval/upload-document`, {
    method: 'POST',
    body: formData,
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Upload failed' }));
    throw new Error(error.detail || 'Upload failed');
  }

  const result = await response.json();
  return result.document;
}

const SectionTitle = ({ title, right, colors }) => (
  <View style={styles.sectionHeader}>
    <Text style={[styles.sectionTitle, { color: colors.primaryText }]} data-testid={`job-section-${title.replace(/\s+/g, '-')}`} testID={`job-section-${title.replace(/\s+/g, '-')}`}>
      {title}
    </Text>
    {right}
  </View>
);

export default function JobPlatformScreen() {
  return <JobsPortalPage />;
}

function LegacyJobPlatformScreen() {
  const { t } = useTranslation();
  t('i18n.route.mini-apps.job-platform.probe');
  const { colors } = useTheme();
  const tx = React.useCallback((key: string, fallback: string) => {
    const v = t(key);
    return v === key ? fallback : v;
  }, [t]);

  // @autofix-moved: was module-level const styles
  const styles = StyleSheet.create({
    hero: { marginBottom: 20 },
    heroKicker: { fontSize: 12, fontWeight: '700', letterSpacing: 1.1, textTransform: 'uppercase' },
    heroTitle: { fontSize: 26, fontWeight: '800', marginTop: 6 },
    heroSubtitle: { fontSize: 14, marginTop: 6, lineHeight: 20 },
    modeRow: { flexDirection: 'row', gap: 12, marginTop: 16 },
    modeButton: { paddingVertical: 10, paddingHorizontal: 18, borderRadius: 14 },
    modeText: { fontWeight: '700', fontSize: 13 },
    card: { borderRadius: 18, borderWidth: 1, padding: 16, marginBottom: 18 },
    cardTitle: { fontSize: 16, fontWeight: '700' },
    label: { fontSize: 12, fontWeight: '600', marginBottom: 6 },
    input: { borderWidth: 1, borderRadius: 12, paddingHorizontal: 12, paddingVertical: 10, marginBottom: 12, fontSize: 13 },
    multiline: { minHeight: 90, textAlignVertical: 'top' },
    sectionHeader: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 },
    sectionTitle: { fontSize: 18, fontWeight: '800' },
    filterRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginBottom: 10 },
    filterChip: { paddingHorizontal: 12, paddingVertical: 6, borderRadius: 999, borderWidth: 1 },
    primaryButton: { flexDirection: 'row', gap: 8, alignItems: 'center', justifyContent: 'center', paddingVertical: 12, borderRadius: 12 },
    primaryButtonText: { color: colors.primaryText, fontWeight: '700' },
    secondaryButton: { paddingVertical: 10, paddingHorizontal: 12, borderRadius: 12, borderWidth: 1, alignItems: 'center', flexDirection: 'row', gap: 6 },
    actionRow: { flexDirection: 'row', gap: 10, marginTop: 12 },
    divider: { height: 1, marginVertical: 12, backgroundColor: colors.border },
    resultBox: { marginTop: 12, padding: 12, borderRadius: 12, backgroundColor: (globalThis as any).__alphaColor(colors.card, '10') },
    resultText: { fontSize: 12 },
    rankRow: { flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 6 },
  });

  const { _user } = useAuth();
  const [mode, setMode] = useState('employee');
  const [_loading, setLoading] = useState(false);

  const [jobs, setJobs] = useState([]);
  const [savedJobs, setSavedJobs] = useState([]);
  const [search, setSearch] = useState('');
  const [location, setLocation] = useState('');
  const [remoteOnly, setRemoteOnly] = useState(false);
  const [category, setCategory] = useState('');
  const [jobType, setJobType] = useState('');
  const [selectedJob, setSelectedJob] = useState(null);
  const [resumeText, setResumeText] = useState('');
  const [coverLetter, setCoverLetter] = useState('');

  const [resumeTitle, setResumeTitle] = useState('Professional Resume');
  const [resumeSummary, setResumeSummary] = useState('');
  const [aiResume, setAiResume] = useState(null);
  const [aiAnalysis, setAiAnalysis] = useState(null);
  const [aiJobDesc, setAiJobDesc] = useState(null);
  const [aiSalary, setAiSalary] = useState(null);

  const [employerProfile, setEmployerProfile] = useState(null);
  const [employerForm, setEmployerForm] = useState({ company_name: '', location: '', website: '', description: '' });
  const [employerJobs, setEmployerJobs] = useState([]);
  const [jobForm, setJobForm] = useState({
    title: '',
    company_name: '',
    location: '',
    remote: false,
    salary_min: '',
    salary_max: '',
    description: '',
    skills_required: '',
    category: '',
    job_type: '',
  });
  const [editingJobId, setEditingJobId] = useState(null);
  const [_applicants, setApplicants] = useState([]);
  const [rankings, setRankings] = useState([]);

  const [planId, setPlanId] = useState('employer_basic');
  const [provider, _setProvider] = useState('mtn');
  const [phoneNumber, setPhoneNumber] = useState('');

  // Employer Approval
  const [approvalStatus, setApprovalStatus] = useState<any>(null);
  const [approvalForm, setApprovalForm] = useState({
    company_name: '', business_registration: '', country: '', industry: 'technology',
    website: '', contact_email: '', company_size: '1-10', hiring_volume: '', description: '',
  });
  const [approvalBusinessDoc, setApprovalBusinessDoc] = useState<ApprovalKycUpload | null>(null);
  const [approvalIdFrontDoc, setApprovalIdFrontDoc] = useState<ApprovalKycUpload | null>(null);
  const [approvalIdBackDoc, setApprovalIdBackDoc] = useState<ApprovalKycUpload | null>(null);
  const [approvalSubmitError, setApprovalSubmitError] = useState('');
  const [approvalUpgradeUrl, setApprovalUpgradeUrl] = useState('');
  const [submittingApproval, setSubmittingApproval] = useState(false);
  const [_userApplications, setUserApplications] = useState<any[]>([]);
  const [translating, setTranslating] = useState<Record<string, boolean>>({});
  const [translations, setTranslations] = useState<Record<string, { title: string; description: string }>>({});
  const [targetLang, setTargetLang] = useState('fr');

  const approvalBusinessInputRef = useRef<HTMLInputElement>(null);
  const approvalIdFrontUploadRef = useRef<HTMLInputElement>(null);
  const approvalIdFrontCaptureRef = useRef<HTMLInputElement>(null);
  const approvalIdBackUploadRef = useRef<HTMLInputElement>(null);
  const approvalIdBackCaptureRef = useRef<HTMLInputElement>(null);

  const loadJobs = async () => {
    try {
      setLoading(true);
      const res = await api.get('/jobs/search', {
        params: {
          q: search || undefined,
          location: location || undefined,
          category: category || undefined,
          job_type: jobType || undefined,
          remote: remoteOnly ? true : undefined,
        },
      });
      setJobs(res.data.jobs || []);
    } catch (e) {
      console.log('Job search failed', e);
    } finally {
      setLoading(false);
    }
  };

  const loadSavedJobs = async () => {
    try {
      const res = await api.get('/jobs/saved');
      const ids = (res.data.jobs || []).map((job) => job.job_id);
      setSavedJobs(ids);
    } catch (e) {
      console.log('Saved jobs failed', e);
    }
  };

  const loadEmployer = async () => {
    try {
      const res = await api.get('/jobs/employer/profile');
      setEmployerProfile(res.data.employer);
      setJobForm((prev) => ({ ...prev, company_name: res.data.employer.company_name || '' }));
    } catch (_e) {
      setEmployerProfile(null);
    }
  };

  const loadEmployerJobs = async () => {
    try {
      const res = await api.get('/jobs/employer/list');
      setEmployerJobs(res.data.jobs || []);
    } catch (e) {
      console.log('Employer jobs failed', e);
    }
  };

  const loadApplicants = async () => {
    try {
      const res = await api.get('/jobs/applications/employer');
      setApplicants(res.data.applications || []);
    } catch (e) {
      console.log('Applicants failed', e);
    }
  };

  useEffect(() => {
    loadJobs();
    loadSavedJobs();
  }, []);
  useAutoRefresh(loadJobs, { intervalMs: 30000 });

  useEffect(() => {
    if (mode === 'employer') {
      loadEmployer();
      loadEmployerJobs();
      loadApplicants();
      api.get('/jobs/employer/approval/status').then(r => setApprovalStatus(r.data)).catch(() => {});
    }
    if (mode === 'employee') {
      api.get('/jobs/applications/user').then(r => setUserApplications(r.data.applications || [])).catch(() => {});
    }
  }, [mode]);

  const handleApply = async () => {
    if (!selectedJob) return;
    if (!resumeText.trim()) {
      Alert.alert('Resume required', 'Paste your resume text to apply.');
      return;
    }
    try {
      await api.post('/hiring/v2/candidate/apply', {
        job_id: selectedJob.job_id,
        resume_text: resumeText,
        cover_letter: coverLetter,
        skills: [],
      });
      Alert.alert('Application sent', 'Your application was submitted successfully.');
      setSelectedJob(null);
      setResumeText('');
      setCoverLetter('');
    } catch (_e) {
      Alert.alert('Error', 'Unable to submit application.');
    }
  };

  const handleSaveJob = async (jobId) => {
    try {
      const res = await api.post(`/hiring/v2/candidate/save/${jobId}`);
      if (res.data.saved) {
        setSavedJobs((prev) => [...prev, jobId]);
      } else {
        setSavedJobs((prev) => prev.filter((id) => id !== jobId));
      }
    } catch (e) {
      console.log('Save job failed', e);
    }
  };

  const handleEmployerRegister = async () => {
    try {
      const res = await api.post('/hiring/v2/employer/register', employerForm);
      setEmployerProfile(res.data.employer);
    } catch (_e) {
      Alert.alert('Error', 'Unable to register employer profile.');
    }
  };

  const handleActivateSubscription = async () => {
    if (!phoneNumber.trim()) {
      Alert.alert('Phone required', 'Add a mobile money phone number.');
      return;
    }
    try {
      await api.post('/mobile-money/process', {
        plan_id: planId,
        provider,
        phone_number: phoneNumber,
        billing_period: 'monthly',
        purpose: 'employer_subscription',
      });
      await loadEmployer();
      Alert.alert('Subscription active', 'Employer subscription activated.');
    } catch (_e) {
      Alert.alert('Error', 'Unable to process payment.');
    }
  };

  const handleCreateJob = async () => {
    if (!jobForm.title || !jobForm.description) {
      Alert.alert('Missing info', 'Add job title and description.');
      return;
    }
    const payload = {
      ...jobForm,
      salary_min: jobForm.salary_min ? Number(jobForm.salary_min) : undefined,
      salary_max: jobForm.salary_max ? Number(jobForm.salary_max) : undefined,
      skills_required: jobForm.skills_required.split(',').map((s) => s.trim()).filter(Boolean),
      category: jobForm.category || 'General',
      job_type: jobForm.job_type || 'Full-time',
    };

    try {
      if (editingJobId) {
        await api.put(`/hiring/v2/employer/jobs/${editingJobId}`, payload);
      } else {
        await api.post('/hiring/v2/employer/jobs/create', payload);
      }
      setJobForm({
        title: '',
        company_name: employerProfile?.company_name || '',
        location: '',
        remote: false,
        salary_min: '',
        salary_max: '',
        description: '',
        skills_required: '',
        category: '',
        job_type: '',
      });
      setEditingJobId(null);
      await loadEmployerJobs();
    } catch (_e) {
      Alert.alert('Error', 'Unable to save job.');
    }
  };

  const handleRankCandidates = async (jobId) => {
    try {
      const form = new FormData();
      form.append('job_id', jobId);
      const res = await api.post('/hiring/v2/ai/rank-candidates', form, { headers: { 'Content-Type': 'multipart/form-data' } });
      setRankings(res.data.rankings || []);
    } catch (_e) {
      Alert.alert('Error', 'Unable to rank candidates.');
    }
  };

  const handleResumeBuild = async () => {
    if (!resumeSummary.trim()) {
      Alert.alert('Summary required', 'Add a resume summary to generate.');
      return;
    }
    try {
      const res = await api.post('/resumes/ai/build', {
        title: resumeTitle,
        summary: resumeSummary,
        experience: [],
        education: [],
        skills: [],
        certifications: [],
        projects: [],
      });
      setAiResume(res.data.resume);
    } catch (_e) {
      Alert.alert('Error', 'Resume build failed.');
    }
  };

  const handleResumeAnalyze = async () => {
    if (!resumeText.trim()) {
      Alert.alert('Resume required', 'Paste your resume text for analysis.');
      return;
    }
    const form = new FormData();
    form.append('resume_text', resumeText);
    try {
      const res = await api.post('/resumes/ai/analyze', form, { headers: { 'Content-Type': 'multipart/form-data' } });
      setAiAnalysis(res.data.analysis);
    } catch (_e) {
      Alert.alert('Error', 'Resume analysis failed.');
    }
  };

  const handleJobDescription = async () => {
    if (!jobForm.title.trim()) {
      Alert.alert('Title required', 'Provide a job title for AI generation.');
      return;
    }
    try {
      const res = await api.post('/hiring/v2/ai/description', {
        job_title: jobForm.title,
        company_name: employerProfile?.company_name || jobForm.company_name,
        location: jobForm.location,
      });
      setAiJobDesc(res.data.job_description);
    } catch (_e) {
      Alert.alert('Error', 'AI description failed.');
    }
  };

  const handleSalaryAI = async () => {
    if (!jobForm.title.trim() || !jobForm.location.trim()) {
      Alert.alert('Missing info', 'Add job title and location.');
      return;
    }
    try {
      const res = await api.post('/hiring/v2/ai/salary', {
        job_title: jobForm.title,
        location: jobForm.location,
      });
      setAiSalary(res.data.salary);
    } catch (_e) {
      Alert.alert('Error', 'Salary AI failed.');
    }
  };

  const handleApprovalDocSelected = async (
    file: File | undefined,
    key: ApprovalKycUpload['document_key'],
  ) => {
    if (!file) return;
    try {
      const uploadedDoc = await uploadApprovalDocument(file, key);
      if (key === 'business_registration') setApprovalBusinessDoc(uploadedDoc);
      if (key === 'id_front') setApprovalIdFrontDoc(uploadedDoc);
      if (key === 'id_back') setApprovalIdBackDoc(uploadedDoc);
      setApprovalSubmitError('');
      setApprovalUpgradeUrl('');
    } catch (e: any) {
      setApprovalSubmitError(e?.message || 'Failed to upload file');
    }
  };

  const downloadApprovalDoc = async (approvalId: string, doc: any) => {
    try {
      const res = await api.get(`/jobs/employer/approval/documents/${approvalId}/${doc.doc_id}/download`, { responseType: 'blob' as any });
      if (typeof window !== 'undefined') {
        const blob = res.data instanceof Blob ? res.data : new Blob([res.data], { type: doc.content_type || 'application/octet-stream' });
        const url = window.URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = doc.original_filename || doc.filename || `${doc.doc_id}`;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        window.URL.revokeObjectURL(url);
      }
    } catch (e: any) {
      Alert.alert('Error', e?.response?.data?.detail || 'Failed to download document');
    }
  };

  return (
    <AppShell>
      <ScrollView style={{ flex: 1, backgroundColor: colors.bg }} contentContainerStyle={{ padding: 24 }}>
        {typeof document !== 'undefined' && (
          <>
            <input ref={approvalBusinessInputRef} type="file" accept=".pdf,.jpg,.jpeg,.png,.webp"
              style={{ display: 'none' }}
              onChange={(e) => { const file = e.target.files?.[0]; void handleApprovalDocSelected(file, 'business_registration'); e.currentTarget.value = ''; }} />
            <input ref={approvalIdFrontUploadRef} type="file" accept=".pdf,.jpg,.jpeg,.png,.webp,image/*"
              style={{ display: 'none' }}
              onChange={(e) => { const file = e.target.files?.[0]; void handleApprovalDocSelected(file, 'id_front'); e.currentTarget.value = ''; }} />
            <input ref={approvalIdFrontCaptureRef} type="file" accept="image/*" capture="environment"
              style={{ display: 'none' }}
              onChange={(e) => { const file = e.target.files?.[0]; void handleApprovalDocSelected(file, 'id_front'); e.currentTarget.value = ''; }} />
            <input ref={approvalIdBackUploadRef} type="file" accept=".pdf,.jpg,.jpeg,.png,.webp,image/*"
              style={{ display: 'none' }}
              onChange={(e) => { const file = e.target.files?.[0]; void handleApprovalDocSelected(file, 'id_back'); e.currentTarget.value = ''; }} />
            <input ref={approvalIdBackCaptureRef} type="file" accept="image/*" capture="environment"
              style={{ display: 'none' }}
              onChange={(e) => { const file = e.target.files?.[0]; void handleApprovalDocSelected(file, 'id_back'); e.currentTarget.value = ''; }} />
          </>
        )}

        <View style={styles.hero}>
          <Text style={[styles.heroKicker, { color: colors.textMuted }]} data-testid="job-platform-kicker" testID="job-platform-kicker">{tx('jobPlatform.hero.kicker', 'Global AI Jobs')}</Text>
          <Text style={[styles.heroTitle, { color: colors.text }]} data-testid="job-platform-title" testID="job-platform-title">{tx('jobPlatform.hero.title', 'AI Job Platform')}</Text>
          <Text style={[styles.heroSubtitle, { color: colors.textSec }]} data-testid="job-platform-subtitle" testID="job-platform-subtitle">
            {tx('jobPlatform.hero.subtitle', 'Switch between employee and employer workflows. Every action is AI-assisted.')}
          </Text>
          <View style={styles.modeRow}>
            <TouchableOpacity
              style={[styles.modeButton, { backgroundColor: mode === 'employee' ? colors.primary : colors.card }]}
              onPress={() => setMode('employee')}
              data-testid="job-mode-employee" testID="job-mode-employee"
            >
              <Text style={[styles.modeText, { color: mode === 'employee' ? colors.primaryText : colors.text }]}>{tx('jobPlatform.mode.employee', 'Employee')}</Text>
            </TouchableOpacity>
            <TouchableOpacity
              style={[styles.modeButton, { backgroundColor: mode === 'employer' ? colors.primary : colors.card }]}
              onPress={() => setMode('employer')}
              data-testid="job-mode-employer" testID="job-mode-employer"
            >
              <Text style={[styles.modeText, { color: mode === 'employer' ? colors.primaryText : colors.text }]}>{tx('jobPlatform.mode.employer', 'Employer')}</Text>
            </TouchableOpacity>
          </View>
        </View>

        {mode === 'employee' ? (
          <View>
            <SectionTitle colors={colors} title={tx('jobPlatform.sections.resumeStudio', 'AI Resume Studio')} />
            <View style={[styles.card, { backgroundColor: colors.card, borderColor: colors.border }]}>
              <Text style={[styles.label, { color: colors.textMuted }]}>{tx('jobPlatform.resume.titleLabel', 'Resume Title')}</Text>
              <TextInput
                style={[styles.input, { borderColor: colors.border, color: colors.text }]}
                value={resumeTitle}
                onChangeText={setResumeTitle}
                placeholder={tx('jobPlatform.resume.titlePlaceholder', 'Senior Product Manager')}
                placeholderTextColor={colors.textMuted}
                data-testid="resume-title-input" testID="resume-title-input"
              />
              <Text style={[styles.label, { color: colors.textMuted }]}>{tx('jobPlatform.resume.summaryLabel', 'Resume Summary')}</Text>
              <TextInput
                style={[styles.input, styles.multiline, { borderColor: colors.border, color: colors.text }]}
                value={resumeSummary}
                onChangeText={setResumeSummary}
                placeholder={tx('jobPlatform.resume.summaryPlaceholder', 'Write a concise professional summary...')}
                placeholderTextColor={colors.textMuted}
                multiline
                data-testid="resume-summary-input" testID="resume-summary-input"
              />
              <TouchableOpacity
                style={[styles.primaryButton, { backgroundColor: colors.primary }]}
                onPress={handleResumeBuild}
                data-testid="resume-build-button" testID="resume-build-button"
              >
                <Ionicons name="sparkles" size={16} color={colors.primaryText} />
                <Text style={styles.primaryButtonText}>{tx('jobPlatform.actions.generateResume', 'Generate Resume')}</Text>
              </TouchableOpacity>
              {aiResume ? (
                <View style={styles.resultBox} data-testid="ai-resume-output" testID="ai-resume-output">
                  <Text style={[styles.resultText, { color: colors.text }]}>{JSON.stringify(aiResume, null, 2)}</Text>
                </View>
              ) : null}
            </View>

            <SectionTitle colors={colors} title={tx('jobPlatform.sections.jobSearch', 'Job Search')} right={
              <TouchableOpacity
                style={[styles.secondaryButton, { borderColor: colors.border }]}
                onPress={loadJobs}
                data-testid="job-search-refresh" testID="job-search-refresh"
                accessibilityRole="button"
                accessibilityLabel="Refresh job search"
              >
                <Ionicons name="refresh" size={14} color={colors.text} />
              </TouchableOpacity>
            } />
            <View style={[styles.card, { backgroundColor: colors.card, borderColor: colors.border }]} accessibilityRole="search" >
              <TextInput
                style={[styles.input, { borderColor: colors.border, color: colors.text }]}
                value={search}
                onChangeText={setSearch}
                placeholder={tx('jobPlatform.search.placeholder', 'Search by title, skill, or company')}
                placeholderTextColor={colors.textMuted}
                data-testid="job-search-input" testID="job-search-input"
                accessibilityLabel="Search keywords"
              />
              <View style={{ flexDirection: 'row', gap: 8 }}>
                <TextInput
                  style={[styles.input, { borderColor: colors.border, color: colors.text, flex: 1 }]}
                  value={location}
                  onChangeText={setLocation}
                  placeholder={tx('jobPlatform.search.locationPlaceholder', 'City or Country')}
                  placeholderTextColor={colors.textMuted}
                  data-testid="job-location-input" testID="job-location-input"
                  accessibilityLabel="Location filter"
                />
              </View>
              <View style={{ flexDirection: 'row', gap: 8, marginBottom: 10 }}>
                <TextInput
                  style={[styles.input, { borderColor: colors.border, color: colors.text, flex: 1, marginBottom: 0 }]}
                  placeholder={tx('jobPlatform.search.minSalary', 'Min salary $')}
                  placeholderTextColor={colors.textMuted}
                  keyboardType="numeric"
                  data-testid="job-salary-min" testID="job-salary-min"
                  accessibilityLabel="Minimum salary"
                />
                <TextInput
                  style={[styles.input, { borderColor: colors.border, color: colors.text, flex: 1, marginBottom: 0 }]}
                  placeholder={tx('jobPlatform.search.maxSalary', 'Max salary $')}
                  placeholderTextColor={colors.textMuted}
                  keyboardType="numeric"
                  data-testid="job-salary-max" testID="job-salary-max"
                  accessibilityLabel="Maximum salary"
                />
              </View>
              <View style={styles.filterRow} accessibilityRole="radiogroup" >
                <TouchableOpacity
                  style={[styles.filterChip, { backgroundColor: remoteOnly ? colors.primary : colors.cardMuted, borderColor: colors.border }]}
                  onPress={() => setRemoteOnly(!remoteOnly)}
                  data-testid="job-remote-toggle" testID="job-remote-toggle"
                  accessibilityRole="checkbox"
                  accessibilityState={{ checked: remoteOnly }}
                  accessibilityLabel="Remote only filter"
                >
                  <Ionicons name={remoteOnly ? 'checkmark-circle' : 'globe-outline'} size={14} color={remoteOnly ? colors.primaryText : colors.text} />
                  <Text style={{ color: remoteOnly ? colors.primaryText : colors.text, marginLeft: 4 }}>{tx('jobPlatform.search.remote', 'Remote')}</Text>
                </TouchableOpacity>
                {JOB_TYPES.map((item) => (
                  <TouchableOpacity
                    key={item}
                    style={[styles.filterChip, { backgroundColor: jobType === item ? colors.primary : colors.cardMuted, borderColor: colors.border }]}
                    onPress={() => setJobType(jobType === item ? '' : item)}
                    data-testid={`job-type-${item}`} testID={`job-type-${item}`}
                    accessibilityRole="radio"
                    accessibilityState={{ selected: jobType === item }}
                  >
                    <Text style={{ color: jobType === item ? colors.primaryText : colors.text, fontSize: 12 }}>{item}</Text>
                  </TouchableOpacity>
                ))}
              </View>
              <View style={[styles.filterRow, { marginTop: 0 }]} >
                {JOB_CATEGORIES.map((item) => (
                  <TouchableOpacity
                    key={item}
                    style={[styles.filterChip, { backgroundColor: category === item ? colors.primary : colors.cardMuted, borderColor: colors.border }]}
                    onPress={() => setCategory(category === item ? '' : item)}
                    data-testid={`job-category-${item}`} testID={`job-category-${item}`}
                    accessibilityRole="radio"
                    accessibilityState={{ selected: category === item }}
                  >
                    <Text style={{ color: category === item ? colors.primaryText : colors.text, fontSize: 12 }}>{item}</Text>
                  </TouchableOpacity>
                ))}
              </View>
              <TouchableOpacity
                style={[styles.primaryButton, { backgroundColor: colors.primary }]}
                onPress={loadJobs}
                data-testid="job-search-button" testID="job-search-button"
                accessibilityRole="button"
                accessibilityLabel="Search jobs"
              >
                <Ionicons name="search" size={16} color={colors.primaryText} />
                <Text style={styles.primaryButtonText}>{tx('jobPlatform.actions.searchJobs', 'Search Jobs')}</Text>
              </TouchableOpacity>
            </View>

            <SectionTitle colors={colors} title={tx('jobPlatform.sections.liveFeed', 'Live Job Feed')} />
            {/* Language selector for translation */}
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 10 }}>
              <Ionicons name="language" size={16} color={colors.textMuted} />
              <Text style={{ color: colors.textMuted, fontSize: 12 }}>{tx('jobPlatform.translate.to', 'Translate to:')}</Text>
              {[{c:'fr',n:'FR'},{c:'es',n:'ES'},{c:'ar',n:'AR'},{c:'pt',n:'PT'},{c:'sw',n:'SW'},{c:'en',n:'EN'}].map(l => (
                <TouchableOpacity key={l.c} onPress={() => setTargetLang(l.c)} style={{ paddingHorizontal: 8, paddingVertical: 4, borderRadius: 6, backgroundColor: targetLang === l.c ? colors.primary : colors.card, borderWidth: 1, borderColor: colors.border }} data-testid={`lang-${l.c}`} testID={`lang-${l.c}`}>
                  <Text style={{ color: targetLang === l.c ? colors.primaryText : colors.textMuted, fontSize: 11, fontWeight: '600' }}>{l.n}</Text>
                </TouchableOpacity>
              ))}
            </View>
            {jobs.map((job) => {
              const t = translations[job.job_id];
              const isTranslating = translating[job.job_id];
              return (
              <View key={job.job_id} style={[styles.card, { backgroundColor: colors.card, borderColor: colors.border }]}>
                <Text style={[styles.cardTitle, { color: colors.text }]} data-testid={`job-title-${job.job_id}`} testID={`job-title-${job.job_id}`}>{t?.title || job.title}</Text>
                <Text style={{ color: colors.textMuted }} data-testid={`job-company-${job.job_id}`} testID={`job-company-${job.job_id}`}>{job.company_name} • {job.location}</Text>
                <Text style={{ color: colors.textSec, marginVertical: 6 }}>{(t?.description || job.description)?.slice(0, 120)}...</Text>
                <View style={styles.actionRow}>
                  <TouchableOpacity
                    style={[styles.primaryButton, { backgroundColor: colors.primary, flex: 1 }]}
                    onPress={() => setSelectedJob(job)}
                    data-testid={`job-apply-${job.job_id}`} testID={`job-apply-${job.job_id}`}
                  >
                    <Text style={styles.primaryButtonText}>{tx('jobPlatform.actions.apply', 'Apply')}</Text>
                  </TouchableOpacity>
                  <TouchableOpacity
                    style={[styles.secondaryButton, { borderColor: colors.border }]}
                    onPress={async () => {
                      if (t) { setTranslations(prev => { const n = {...prev}; delete n[job.job_id]; return n; }); return; }
                      setTranslating(prev => ({...prev, [job.job_id]: true}));
                      try {
                        const [tRes, dRes] = await Promise.all([
                          api.post('/hiring/v2/ai/translate', { text: job.title, target_lang: targetLang }),
                          api.post('/hiring/v2/ai/translate', { text: job.description || '', target_lang: targetLang }),
                        ]);
                        setTranslations(prev => ({...prev, [job.job_id]: { title: tRes.data.translated_text, description: dRes.data.translated_text }}));
                      } catch { Alert.alert('Error', tx('jobPlatform.errors.translationFailed', 'Translation failed')); }
                      finally { setTranslating(prev => ({...prev, [job.job_id]: false})); }
                    }}
                    data-testid={`job-translate-${job.job_id}`} testID={`job-translate-${job.job_id}`}
                    accessibilityRole="button"
                    accessibilityLabel={t ? tx('jobPlatform.actions.showOriginal', 'Show original') : tx('jobPlatform.actions.translatePosting', 'Translate job posting')}
                  >
                    {isTranslating ? <ActivityIndicator size="small" color={colors.text} /> : <Ionicons name={t ? 'close-circle' : 'language'} size={16} color={t ? colors.warning : colors.text} />}
                  </TouchableOpacity>
                  <TouchableOpacity
                    style={[styles.secondaryButton, { borderColor: colors.border }]}
                    onPress={() => handleSaveJob(job.job_id)}
                    data-testid={`job-save-${job.job_id}`} testID={`job-save-${job.job_id}`}
                  >
                    <Ionicons name={savedJobs.includes(job.job_id) ? 'bookmark' : 'bookmark-outline'} size={16} color={colors.text} />
                  </TouchableOpacity>
                </View>
              </View>
              );
            })}

            {selectedJob ? (
              <View style={[styles.card, { backgroundColor: colors.card, borderColor: colors.border }]} data-testid="job-apply-card" testID="job-apply-card">
                <Text style={[styles.cardTitle, { color: colors.text }]}>{tx('jobPlatform.applyModal.titlePrefix', 'Apply to')} {selectedJob.title}</Text>
                <TextInput
                  style={[styles.input, styles.multiline, { borderColor: colors.border, color: colors.text }]}
                  value={resumeText}
                  onChangeText={setResumeText}
                  placeholder={tx('jobPlatform.applyModal.resumePlaceholder', 'Paste resume text')}
                  placeholderTextColor={colors.textMuted}
                  multiline
                  data-testid="apply-resume-text" testID="apply-resume-text"
                />
                <TextInput
                  style={[styles.input, styles.multiline, { borderColor: colors.border, color: colors.text }]}
                  value={coverLetter}
                  onChangeText={setCoverLetter}
                  placeholder={tx('jobPlatform.applyModal.coverLetterPlaceholder', 'Cover letter (optional)')}
                  placeholderTextColor={colors.textMuted}
                  multiline
                  data-testid="apply-cover-letter" testID="apply-cover-letter"
                />
                <View style={styles.actionRow}>
                  <TouchableOpacity
                    style={[styles.primaryButton, { backgroundColor: colors.primary, flex: 1 }]}
                    onPress={handleApply}
                    data-testid="submit-application" testID="submit-application"
                  >
                    <Text style={styles.primaryButtonText}>{tx('jobPlatform.actions.submitApplication', 'Submit Application')}</Text>
                  </TouchableOpacity>
                  <TouchableOpacity
                    style={[styles.secondaryButton, { borderColor: colors.border }]}
                    onPress={() => setSelectedJob(null)}
                    data-testid="cancel-application" testID="cancel-application"
                  >
                    <Text style={{ color: colors.text }}>{tx('common.cancel', 'Cancel')}</Text>
                  </TouchableOpacity>
                </View>
              </View>
            ) : null}

            <SectionTitle colors={colors} title={tx('jobPlatform.sections.resumeAnalysis', 'AI Resume Analysis')} />
            <View style={[styles.card, { backgroundColor: colors.card, borderColor: colors.border }]}>
              <TouchableOpacity
                style={[styles.primaryButton, { backgroundColor: colors.primary }]}
                onPress={handleResumeAnalyze}
                data-testid="resume-analyze-button" testID="resume-analyze-button"
              >
                <Ionicons name="analytics" size={16} color={colors.primaryText} />
                <Text style={styles.primaryButtonText}>{tx('jobPlatform.actions.analyzeResumeText', 'Analyze Resume Text')}</Text>
              </TouchableOpacity>
              {aiAnalysis ? (
                <View style={styles.resultBox} data-testid="resume-analysis-output" testID="resume-analysis-output">
                  <Text style={[styles.resultText, { color: colors.text }]}>{JSON.stringify(aiAnalysis, null, 2)}</Text>
                </View>
              ) : null}
            </View>
          </View>
        ) : (
          <View>
            {/* Employer Approval Status */}
            <SectionTitle colors={colors} title={tx('jobPlatform.sections.employerStatus', 'Employer Status')} />
            <View style={[styles.card, { backgroundColor: colors.card, borderColor: colors.border }]} data-testid="employer-approval-section" testID="employer-approval-section">
              {approvalStatus?.status === 'approved' ? (
                <View>
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 12 }}>
                    <Ionicons name="checkmark-circle" size={24} color={colors.successText} />
                    <Text style={[styles.cardTitle, { color: colors.text }]}>{tx('jobPlatform.employer.approved', 'Employer Approved')}</Text>
                  </View>
                  <Text style={{ color: colors.textSec, marginBottom: 4 }}>{tx('jobPlatform.employer.company', 'Company')}: {approvalStatus.company_name}</Text>
                  <Text style={{ color: colors.textSec, marginBottom: 4 }}>{tx('jobPlatform.employer.country', 'Country')}: {approvalStatus.country} | {tx('jobPlatform.employer.industry', 'Industry')}: {approvalStatus.industry}</Text>
                  <Text style={{ color: colors.successText, fontSize: 12 }}>{tx('jobPlatform.employer.unlimitedJobs', 'You can post unlimited jobs for FREE.')}</Text>
                </View>
              ) : approvalStatus?.status === 'submitted' || approvalStatus?.status === 'in_review' ? (
                <View>
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 12 }}>
                    <Ionicons name="hourglass" size={24} color={colors.warningText} />
                    <Text style={[styles.cardTitle, { color: colors.text }]}>{tx('jobPlatform.employer.pending', 'Approval Pending')}</Text>
                  </View>
                  <Text style={{ color: colors.textSec, marginBottom: 4 }}>{tx('jobPlatform.employer.company', 'Company')}: {approvalStatus.company_name}</Text>
                  <Text style={{ color: colors.warningText, fontSize: 12 }}>{tx('jobPlatform.employer.status', 'Status')}: {approvalStatus.status.replace('_', ' ').toUpperCase()}</Text>
                  {approvalStatus.reviewer_notes ? <Text style={{ color: colors.textMuted, fontSize: 12, marginTop: 8 }}>{tx('jobPlatform.employer.notes', 'Notes')}: {approvalStatus.reviewer_notes}</Text> : null}
                  {(approvalStatus.documents || []).length > 0 && (
                    <View style={{ marginTop: 10, gap: 6 }} data-testid="approval-submitted-documents" testID="approval-submitted-documents">
                      <Text style={{ color: colors.textMuted, fontSize: 11, fontWeight: '700' }}>{t("autofix.precision12.uploaded.verification.docs")}</Text>
                      {(approvalStatus.documents || []).map((doc: any, i: number) => (
                        <View key={doc.doc_id || i} style={{ flexDirection: 'row', alignItems: 'center', gap: 8, backgroundColor: colors.bgSoft || colors.card, borderWidth: 1, borderColor: colors.border, borderRadius: 8, padding: 8 }}>
                          <Ionicons name={String(doc.content_type || '').includes('pdf') ? 'document-text' : 'image'} size={14} color={colors.textMuted} />
                          <Text style={{ color: colors.textSec, fontSize: 11, flex: 1 }} numberOfLines={1}>{doc.original_filename || doc.filename}</Text>
                          <TouchableOpacity
                            onPress={() => downloadApprovalDoc(approvalStatus.approval_id, doc)}
                            style={{ backgroundColor: (globalThis as any).__alphaColor(colors.primary, '15'), borderWidth: 1, borderColor: (globalThis as any).__alphaColor(colors.primary, '30'), borderRadius: 6, paddingHorizontal: 8, paddingVertical: 4 }}
                            data-testid={`approval-doc-download-${doc.doc_id}`}
                            testID={`approval-doc-download-${doc.doc_id}`}
                          >
                            <Text style={{ color: colors.primary, fontSize: 10, fontWeight: '700' }}>{t("autofix.precision12.download")}</Text>
                          </TouchableOpacity>
                        </View>
                      ))}
                    </View>
                  )}
                </View>
              ) : approvalStatus?.status === 'denied' ? (
                <View>
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 12 }}>
                    <Ionicons name="close-circle" size={24} color={colors.error} />
                    <Text style={[styles.cardTitle, { color: colors.text }]}>{tx('jobPlatform.employer.denied', 'Application Denied')}</Text>
                  </View>
                  <Text style={{ color: colors.error, fontSize: 12 }}>{tx('jobPlatform.employer.reason', 'Reason')}: {approvalStatus.reviewer_notes || tx('jobPlatform.employer.contactSupport', 'Contact support for details')}</Text>
                </View>
              ) : approvalStatus?.status === 'need_more_info' ? (
                <View>
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 12 }}>
                    <Ionicons name="information-circle" size={24} color={colors.warningText} />
                    <Text style={[styles.cardTitle, { color: colors.text }]}>{tx('jobPlatform.employer.moreInfo', 'More Information Needed')}</Text>
                  </View>
                  <Text style={{ color: colors.textSec, marginBottom: 8 }}>{approvalStatus.reviewer_notes}</Text>
                  <TouchableOpacity style={[styles.primaryButton, { backgroundColor: colors.warning }]} onPress={async () => {
                    try { await api.post('/hiring/v2/employer/approval/resubmit', { additional_info: 'Updated details provided' }); setApprovalStatus({ ...approvalStatus, status: 'submitted' }); } catch (error) { handleAppRecoverableError({ scope: 'mini-apps/job-platform.tsx#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
                  }} data-testid="employer-resubmit-btn" testID="employer-resubmit-btn">
                    <Text style={styles.primaryButtonText}>{tx('jobPlatform.actions.resubmitApplication', 'Resubmit Application')}</Text>
                  </TouchableOpacity>
                </View>
              ) : (
                /* Approval Form */
                <View data-testid="employer-approval-form" testID="employer-approval-form">
                  <Text style={[styles.cardTitle, { color: colors.text, marginBottom: 12 }]}>{tx('jobPlatform.sections.applyEmployer', 'Apply as Employer')}</Text>
                  <Text style={{ color: colors.textSec, fontSize: 12, marginBottom: 16 }}>{tx('jobPlatform.employer.applyHelp', 'Post jobs for FREE after admin approval. Fill out your company details below.')}</Text>
                  {[
                    { key: 'company_name', label: 'Company Name', placeholder: 'TechCorp Africa' },
                    { key: 'business_registration', label: 'Business Registration #', placeholder: 'REG-12345' },
                    { key: 'country', label: 'Country', placeholder: 'Nigeria' },
                    { key: 'website', label: 'Company Website', placeholder: 'https://example.com' },
                    { key: 'contact_email', label: 'Contact Email', placeholder: 'hr@company.com' },
                    { key: 'hiring_volume', label: 'Estimated Hiring Volume', placeholder: '10-20 per year' },
                  ].map(f => (
                    <View key={f.key} style={{ marginBottom: 10 }}>
                      <Text style={[styles.label, { color: colors.textMuted }]}>{f.label}</Text>
                      <TextInput style={[styles.input, { borderColor: colors.border, color: colors.text }]}
                        value={(approvalForm as any)[f.key]} placeholder={f.placeholder} placeholderTextColor={colors.textMuted}
                        onChangeText={v => setApprovalForm({ ...approvalForm, [f.key]: v })} data-testid={`approval-${f.key}`} testID={`approval-${f.key}`} />
                    </View>
                  ))}
                  <Text style={[styles.label, { color: colors.textMuted }]}>{tx('jobPlatform.employer.industry', 'Industry')}</Text>
                  <View style={[styles.filterRow, { marginBottom: 10, flexWrap: 'wrap' }]}>
                    {['technology', 'finance', 'healthcare', 'education', 'retail', 'media', 'other'].map(ind => (
                      <TouchableOpacity key={ind} onPress={() => setApprovalForm({ ...approvalForm, industry: ind })}
                        style={[styles.filterChip, { backgroundColor: approvalForm.industry === ind ? colors.primary : colors.bgSoft || colors.card, borderColor: approvalForm.industry === ind ? colors.primary : colors.border }]}>
                        <Text style={{ color: approvalForm.industry === ind ? colors.primaryText : colors.text, fontSize: 12 }}>{ind}</Text>
                      </TouchableOpacity>
                    ))}
                  </View>
                  <Text style={[styles.label, { color: colors.textMuted }]}>{tx('jobPlatform.employer.companyDescription', 'Company Description')}</Text>
                  <TextInput style={[styles.input, styles.multiline, { borderColor: colors.border, color: colors.text }]}
                    value={approvalForm.description} placeholder={tx('jobPlatform.employer.descriptionPlaceholder', 'Describe your company...')} placeholderTextColor={colors.textMuted}
                    multiline onChangeText={v => setApprovalForm({ ...approvalForm, description: v })} data-testid="approval-description" testID="approval-description" />

                  <Text style={[styles.label, { color: colors.textMuted }]}>{t("autofix.precision12.official.business.document")}</Text>
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 10 }}>
                    <TouchableOpacity
                      style={[styles.secondaryButton, { borderColor: colors.border }]}
                      onPress={() => approvalBusinessInputRef.current?.click()}
                      data-testid="approval-business-doc-upload-btn"
                      testID="approval-business-doc-upload-btn"
                    >
                      <Ionicons name="cloud-upload" size={14} color={colors.text} />
                      <Text style={{ color: colors.text, fontSize: 12, fontWeight: '600' }}>{approvalBusinessDoc ? 'Replace' : 'Upload'}</Text>
                    </TouchableOpacity>
                    <Text style={{ color: colors.textSec, fontSize: 11, flex: 1 }} data-testid="approval-business-doc-name" testID="approval-business-doc-name">
                      {approvalBusinessDoc?.filename || 'No file selected'}
                    </Text>
                  </View>

                  <Text style={[styles.label, { color: colors.textMuted }]}>{t("autofix.precision12.id.document.front")}</Text>
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 10, flexWrap: 'wrap' }}>
                    <TouchableOpacity
                      style={[styles.secondaryButton, { borderColor: colors.border }]}
                      onPress={() => approvalIdFrontUploadRef.current?.click()}
                      data-testid="approval-id-front-upload-btn"
                      testID="approval-id-front-upload-btn"
                    >
                      <Ionicons name="cloud-upload" size={14} color={colors.text} />
                      <Text style={{ color: colors.text, fontSize: 12, fontWeight: '600' }}>{approvalIdFrontDoc ? 'Replace upload' : 'Upload file'}</Text>
                    </TouchableOpacity>
                    <TouchableOpacity
                      style={[styles.secondaryButton, { borderColor: colors.border }]}
                      onPress={() => approvalIdFrontCaptureRef.current?.click()}
                      data-testid="approval-id-front-capture-btn"
                      testID="approval-id-front-capture-btn"
                    >
                      <Ionicons name="camera" size={14} color={colors.text} />
                      <Text style={{ color: colors.text, fontSize: 12, fontWeight: '600' }}>{t("autofix.precision12.take.photo")}</Text>
                    </TouchableOpacity>
                    <Text style={{ color: colors.textSec, fontSize: 11, flex: 1 }} data-testid="approval-id-front-name" testID="approval-id-front-name">
                      {approvalIdFrontDoc?.filename || 'No file selected'}
                    </Text>
                  </View>

                  <Text style={[styles.label, { color: colors.textMuted }]}>{t("autofix.precision12.id.document.back")}</Text>
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 10, flexWrap: 'wrap' }}>
                    <TouchableOpacity
                      style={[styles.secondaryButton, { borderColor: colors.border }]}
                      onPress={() => approvalIdBackUploadRef.current?.click()}
                      data-testid="approval-id-back-upload-btn"
                      testID="approval-id-back-upload-btn"
                    >
                      <Ionicons name="cloud-upload" size={14} color={colors.text} />
                      <Text style={{ color: colors.text, fontSize: 12, fontWeight: '600' }}>{approvalIdBackDoc ? 'Replace upload' : 'Upload file'}</Text>
                    </TouchableOpacity>
                    <TouchableOpacity
                      style={[styles.secondaryButton, { borderColor: colors.border }]}
                      onPress={() => approvalIdBackCaptureRef.current?.click()}
                      data-testid="approval-id-back-capture-btn"
                      testID="approval-id-back-capture-btn"
                    >
                      <Ionicons name="camera" size={14} color={colors.text} />
                      <Text style={{ color: colors.text, fontSize: 12, fontWeight: '600' }}>{t("autofix.precision12.take.photo")}</Text>
                    </TouchableOpacity>
                    <Text style={{ color: colors.textSec, fontSize: 11, flex: 1 }} data-testid="approval-id-back-name" testID="approval-id-back-name">
                      {approvalIdBackDoc?.filename || 'No file selected'}
                    </Text>
                  </View>

                  {!!approvalSubmitError && (
                    <View style={{ backgroundColor: (globalThis as any).__alphaColor(colors.error, '15'), borderWidth: 1, borderColor: (globalThis as any).__alphaColor(colors.error, '33'), borderRadius: 10, padding: 10, marginBottom: 10 }} data-testid="approval-submit-error" testID="approval-submit-error">
                      <Text style={{ color: colors.error, fontSize: 12, fontWeight: '700' }}>{approvalSubmitError}</Text>
                      {!!approvalUpgradeUrl && (
                        <TouchableOpacity
                          onPress={() => {
                            if (typeof window !== 'undefined') {
                              window.location.href = approvalUpgradeUrl;
                            }
                          }}
                          style={{ marginTop: 8, backgroundColor: (globalThis as any).__alphaColor(colors.error, '20'), borderWidth: 1, borderColor: (globalThis as any).__alphaColor(colors.error, '40'), borderRadius: 8, paddingHorizontal: 10, paddingVertical: 7, alignSelf: 'flex-start' }}
                          data-testid="approval-upgrade-plan-btn"
                          testID="approval-upgrade-plan-btn"
                        >
                          <Text style={{ color: colors.error, fontSize: 11, fontWeight: '800' }}>{t("autofix.precision12.view.subscription.plans")}</Text>
                        </TouchableOpacity>
                      )}
                    </View>
                  )}

                  <TouchableOpacity style={[styles.primaryButton, { backgroundColor: colors.primary, opacity: submittingApproval ? 0.5 : 1 }]}
                    disabled={submittingApproval || !approvalForm.company_name || !approvalForm.country || !approvalForm.contact_email}
                    onPress={async () => {
                      if (!approvalBusinessDoc || !approvalIdFrontDoc || !approvalIdBackDoc) {
                        setApprovalSubmitError('Please upload required business and ID documents before submission.');
                        setApprovalUpgradeUrl('');
                        return;
                      }
                      setSubmittingApproval(true);
                      setApprovalSubmitError('');
                      setApprovalUpgradeUrl('');
                      try {
                        const r = await api.post('/hiring/v2/employer/approval/submit', {
                          ...approvalForm,
                          documents: [approvalBusinessDoc, approvalIdFrontDoc, approvalIdBackDoc],
                        });
                        Alert.alert(tx('jobPlatform.alerts.submittedTitle', 'Submitted!'), tx('jobPlatform.alerts.submittedBody', 'Your employer application is under review.'));
                        setApprovalStatus({ ...approvalForm, status: 'submitted', approval_id: r.data.approval_id, documents: [approvalBusinessDoc, approvalIdFrontDoc, approvalIdBackDoc] });
                      } catch (e: any) {
                        const payload = e?.response?.data || {};
                        const d = payload?.detail;
                        if (payload?.error === 'Subscription Required') {
                          setApprovalSubmitError(payload?.message || tx('jobPlatform.errors.subscriptionRequired', 'Employer submission requires an active subscription.'));
                          setApprovalUpgradeUrl(String(payload?.upgrade_url || '/subscription/plans'));
                        } else if (typeof d === 'object' && d?.message) {
                          const missing = Array.isArray(d?.missing_document_keys) ? d.missing_document_keys.join(', ') : '';
                          setApprovalSubmitError(`${d.message}${missing ? ` (${missing})` : ''}`);
                        } else {
                          setApprovalSubmitError(typeof d === 'string' ? d : (payload?.message || tx('jobPlatform.errors.submissionFailed', 'Submission failed')));
                        }
                        const alertMsg = payload?.message || (typeof d === 'string' ? d : tx('jobPlatform.errors.submissionFailed', 'Submission failed'));
                        Alert.alert(tx('common.error', 'Error'), alertMsg);
                      }
                      finally { setSubmittingApproval(false); }
                    }} data-testid="employer-submit-approval-btn" testID="employer-submit-approval-btn">
                    <Text style={styles.primaryButtonText}>{submittingApproval ? tx('jobPlatform.actions.submitting', 'Submitting...') : tx('jobPlatform.actions.submitForApproval', 'Submit for Approval')}</Text>
                  </TouchableOpacity>
                </View>
              )}
            </View>

            {/* Only show job posting if approved */}
            {approvalStatus?.status === 'approved' && (
              <>
                <SectionTitle colors={colors} title={tx('jobPlatform.sections.employerProfile', 'Employer Profile')} />
                <View style={[styles.card, { backgroundColor: colors.card, borderColor: colors.border }]}>
                  {!employerProfile ? (
                    <>
                      <TextInput
                        style={[styles.input, { borderColor: colors.border, color: colors.text }]}
                        value={employerForm.company_name}
                        onChangeText={(text) => setEmployerForm({ ...employerForm, company_name: text })}
                        placeholder={tx('jobPlatform.employer.companyPlaceholder', 'Company name')}
                        placeholderTextColor={colors.textMuted}
                        data-testid="employer-company-input" testID="employer-company-input"
                      />
                      <TextInput
                        style={[styles.input, { borderColor: colors.border, color: colors.text }]}
                        value={employerForm.location}
                        onChangeText={(text) => setEmployerForm({ ...employerForm, location: text })}
                        placeholder={tx('jobPlatform.employer.hqPlaceholder', 'HQ location')}
                        placeholderTextColor={colors.textMuted}
                        data-testid="employer-location-input" testID="employer-location-input"
                      />
                      <TouchableOpacity
                        style={[styles.primaryButton, { backgroundColor: colors.primary }]}
                        onPress={handleEmployerRegister}
                        data-testid="employer-register-button" testID="employer-register-button"
                      >
                        <Text style={styles.primaryButtonText}>{tx('jobPlatform.actions.createEmployerProfile', 'Create Employer Profile')}</Text>
                      </TouchableOpacity>
                    </>
                  ) : (
                <>
                  <Text style={[styles.cardTitle, { color: colors.text }]} data-testid="employer-company-name" testID="employer-company-name">{employerProfile.company_name}</Text>
                  <Text style={{ color: colors.textSec }} data-testid="employer-subscription-status" testID="employer-subscription-status">{tx('jobPlatform.employer.subscription', 'Subscription')}: {employerProfile.subscription_status}</Text>
                  <View style={styles.divider} />
                  <Text style={[styles.label, { color: colors.textMuted }]}>{tx('jobPlatform.actions.activateSubscriptionLabel', 'Activate Employer Subscription')}</Text>
                  <View style={styles.filterRow}>
                    {['employer_basic', 'employer_growth'].map((plan) => (
                      <TouchableOpacity
                        key={plan}
                        style={[styles.filterChip, { backgroundColor: planId === plan ? colors.primary : colors.cardMuted, borderColor: colors.border }]}
                        onPress={() => setPlanId(plan)}
                        data-testid={`employer-plan-${plan}`} testID={`employer-plan-${plan}`}
                      >
                        <Text style={{ color: planId === plan ? colors.primaryText : colors.text }}>{plan.replace('employer_', '').toUpperCase()}</Text>
                      </TouchableOpacity>
                    ))}
                  </View>
                  <TextInput
                    style={[styles.input, { borderColor: colors.border, color: colors.text }]}
                    value={phoneNumber}
                    onChangeText={setPhoneNumber}
                    placeholder={tx('jobPlatform.employer.mobileMoneyPhone', 'Mobile money phone')}
                    placeholderTextColor={colors.textMuted}
                    data-testid="employer-phone-input" testID="employer-phone-input"
                  />
                  <TouchableOpacity
                    style={[styles.primaryButton, { backgroundColor: colors.primary }]}
                    onPress={handleActivateSubscription}
                    data-testid="employer-activate-button" testID="employer-activate-button"
                  >
                    <Text style={styles.primaryButtonText}>{tx('jobPlatform.actions.activateSubscription', 'Activate Subscription')}</Text>
                  </TouchableOpacity>
                </>
              )}
            </View>

            <SectionTitle colors={colors} title={tx('jobPlatform.sections.jobDrafting', 'AI Job Drafting')} />
            <View style={[styles.card, { backgroundColor: colors.card, borderColor: colors.border }]}>
              <TextInput
                style={[styles.input, { borderColor: colors.border, color: colors.text }]}
                value={jobForm.title}
                onChangeText={(text) => setJobForm({ ...jobForm, title: text })}
                placeholder="Job title"
                placeholderTextColor={colors.textMuted}
                data-testid="job-title-input" testID="job-title-input"
              />
              <TextInput
                style={[styles.input, { borderColor: colors.border, color: colors.text }]}
                value={jobForm.location}
                onChangeText={(text) => setJobForm({ ...jobForm, location: text })}
                placeholder="Location"
                placeholderTextColor={colors.textMuted}
                data-testid="job-location-input" testID="job-location-input"
              />
              <TouchableOpacity
                style={[styles.secondaryButton, { borderColor: colors.border }]}
                onPress={handleJobDescription}
                data-testid="job-ai-description" testID="job-ai-description"
              >
                <Ionicons name="sparkles" size={16} color={colors.text} />
                <Text style={{ color: colors.text, fontWeight: '600' }}>{tx('jobPlatform.actions.generateDescription', 'Generate Description')}</Text>
              </TouchableOpacity>
              <TouchableOpacity
                style={[styles.secondaryButton, { borderColor: colors.border }]}
                onPress={handleSalaryAI}
                data-testid="job-ai-salary" testID="job-ai-salary"
              >
                <Ionicons name="cash" size={16} color={colors.text} />
                <Text style={{ color: colors.text, fontWeight: '600' }}>{tx('jobPlatform.actions.recommendSalary', 'Recommend Salary')}</Text>
              </TouchableOpacity>
              {aiJobDesc ? (
                <View style={styles.resultBox} data-testid="ai-job-description-output" testID="ai-job-description-output">
                  <Text style={[styles.resultText, { color: colors.text }]}>{JSON.stringify(aiJobDesc, null, 2)}</Text>
                </View>
              ) : null}
              {aiSalary ? (
                <View style={styles.resultBox} data-testid="ai-salary-output" testID="ai-salary-output">
                  <Text style={[styles.resultText, { color: colors.text }]}>{JSON.stringify(aiSalary, null, 2)}</Text>
                </View>
              ) : null}
            </View>

            <SectionTitle colors={colors} title={tx('jobPlatform.sections.publishJob', 'Publish a Job')} />
            <View style={[styles.card, { backgroundColor: colors.card, borderColor: colors.border }]}>
              <TextInput
                style={[styles.input, { borderColor: colors.border, color: colors.text }]}
                value={jobForm.description}
                onChangeText={(text) => setJobForm({ ...jobForm, description: text })}
                placeholder="Job description"
                placeholderTextColor={colors.textMuted}
                multiline
                data-testid="job-description-input" testID="job-description-input"
              />
              <TextInput
                style={[styles.input, { borderColor: colors.border, color: colors.text }]}
                value={jobForm.skills_required}
                onChangeText={(text) => setJobForm({ ...jobForm, skills_required: text })}
                placeholder="Skills (comma separated)"
                placeholderTextColor={colors.textMuted}
                data-testid="job-skills-input" testID="job-skills-input"
              />
              <View style={styles.filterRow}>
                {JOB_CATEGORIES.slice(0, 3).map((item) => (
                  <TouchableOpacity
                    key={item}
                    style={[styles.filterChip, { backgroundColor: jobForm.category === item ? colors.primary : colors.cardMuted, borderColor: colors.border }]}
                    onPress={() => setJobForm({ ...jobForm, category: jobForm.category === item ? '' : item })}
                    data-testid={`job-form-category-${item}`} testID={`job-form-category-${item}`}
                  >
                    <Text style={{ color: jobForm.category === item ? colors.primaryText : colors.text }}>{item}</Text>
                  </TouchableOpacity>
                ))}
              </View>
              <TouchableOpacity
                style={[styles.primaryButton, { backgroundColor: colors.primary }]}
                onPress={handleCreateJob}
                data-testid="job-save-button" testID="job-save-button"
              >
                <Text style={styles.primaryButtonText}>{editingJobId ? tx('jobPlatform.actions.updateJob', 'Update Job') : tx('jobPlatform.actions.publishJob', 'Publish Job')}</Text>
              </TouchableOpacity>
            </View>

            <SectionTitle colors={colors} title={tx('jobPlatform.sections.activeJobs', 'Your Active Jobs')} />
            {employerJobs.map((job) => (
              <View key={job.job_id} style={[styles.card, { backgroundColor: colors.card, borderColor: colors.border }]}>
                <Text style={[styles.cardTitle, { color: colors.text }]} data-testid={`employer-job-${job.job_id}`} testID={`employer-job-${job.job_id}`}>{job.title}</Text>
                <Text style={{ color: colors.textMuted }}>{job.location} • {job.job_type}</Text>
                <View style={styles.actionRow}>
                  <TouchableOpacity
                    style={[styles.secondaryButton, { borderColor: colors.border }]}
                    onPress={() => {
                      setEditingJobId(job.job_id);
                      setJobForm({
                        title: job.title,
                        company_name: job.company_name,
                        location: job.location,
                        remote: job.remote,
                        salary_min: job.salary_min ? String(job.salary_min) : '',
                        salary_max: job.salary_max ? String(job.salary_max) : '',
                        description: job.description,
                        skills_required: (job.skills_required || []).join(', '),
                        category: job.category,
                        job_type: job.job_type,
                      });
                    }}
                    data-testid={`job-edit-${job.job_id}`} testID={`job-edit-${job.job_id}`}
                  >
                    <Text style={{ color: colors.text }}>{tx('common.edit', 'Edit')}</Text>
                  </TouchableOpacity>
                  <TouchableOpacity
                    style={[styles.secondaryButton, { borderColor: colors.border }]}
                    onPress={() => handleRankCandidates(job.job_id)}
                    data-testid={`job-rank-${job.job_id}`} testID={`job-rank-${job.job_id}`}
                  >
                    <Text style={{ color: colors.text }}>{tx('jobPlatform.actions.aiRank', 'AI Rank')}</Text>
                  </TouchableOpacity>
                </View>
              </View>
            ))}

            <SectionTitle colors={colors} title={tx('jobPlatform.sections.applicantRankings', 'Applicant Rankings')} />
            <View style={[styles.card, { backgroundColor: colors.card, borderColor: colors.border }]}>
              {rankings.length === 0 ? (
                <Text style={{ color: colors.textMuted }} data-testid="no-rankings" testID="no-rankings">{tx('jobPlatform.rankings.empty', 'Run AI rank on a job to see candidates.')}</Text>
              ) : (
                rankings.map((rank) => (
                  <View key={rank.application_id} style={styles.rankRow}>
                    <Text style={{ color: colors.text }} data-testid={`ranking-${rank.application_id}`} testID={`ranking-${rank.application_id}`}>{rank.application_id}</Text>
                    <Text style={{ color: colors.textSec }}>{rank.score}</Text>
                  </View>
                ))
              )}
            </View>
              </>
            )}
          </View>
        )}
      </ScrollView>
    </AppShell>
  );
}
