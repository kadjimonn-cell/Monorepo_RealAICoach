import React, { useCallback, useEffect, useState } from 'react';
import { View, Text, TouchableOpacity, ActivityIndicator, Platform } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { BillingSectionCard, BillingActionButton } from '../paymentHistory/BillingRoutePrimitives';

type JobDoc = {
  job_id: string;
  job_title: string;
  cv_markdown: string;
  cover_letter_markdown: string;
  reviewer_notes: string[];
  ats_report: null | {
    ats_score: number;
    covered_keywords: string[];
    missing_keywords: string[];
    parseability: { score: number; issues: string[] };
    recommendations: string[];
  };
  generated_at: string;
};

type Props = {
  colors: any;
  tx: (key: string, fallback: string) => string;
  selectedJobId: string;
  selectedJobTitle: string;
  onKitGenerated: () => void;
  onApplied: () => void;
};

const triggerBlobDownload = (blob: Blob, filename: string) => {
  if (typeof document === 'undefined') return;
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  document.body.removeChild(anchor);
  URL.revokeObjectURL(url);
};

export const DocumentsTab = ({ colors, tx, selectedJobId, selectedJobTitle, onKitGenerated, onApplied }: Props) => {
  const [docs, setDocs] = useState<JobDoc[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [activeDocJobId, setActiveDocJobId] = useState('');
  const [docView, setDocView] = useState<'cv' | 'cover'>('cv');
  const [statusMsg, setStatusMsg] = useState('');
  const [copiedMsg, setCopiedMsg] = useState('');
  const [pdfDownloading, setPdfDownloading] = useState(false);
  const [wordDownloading, setWordDownloading] = useState(false);

  const downloadWord = async () => {
    if (!activeDocJobId || Platform.OS !== 'web') return;
    setWordDownloading(true);
    setStatusMsg('');
    try {
      const resp = await api.get(`/job-search/documents/${activeDocJobId}/docx`, {
        params: { view: docView === 'cv' ? 'cv' : 'cover' },
        responseType: 'blob',
        timeout: 60000,
      });
      const blob = new Blob([resp.data], { type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' });
      triggerBlobDownload(blob, `${docView === 'cv' ? 'cv' : 'cover-letter'}-${activeDocJobId}.docx`);
      promptMarkApplied(activeDocJobId);
    } catch {
      setStatusMsg(tx('jobSearch.docs.wordFailed', 'Word export is unavailable right now. Please retry.'));
    } finally {
      setWordDownloading(false);
    }
  };
  const [emailingKit, setEmailingKit] = useState(false);
  const [markPromptJobId, setMarkPromptJobId] = useState('');
  const [markedJobIds, setMarkedJobIds] = useState<string[]>([]);
  const [markBusy, setMarkBusy] = useState(false);
  const [markMsg, setMarkMsg] = useState('');

  const statusLabel = (status: string) => {
    if (status === 'saved') return tx('jobSearch.tracker.status.saved', 'Saved');
    if (status === 'applied') return tx('jobSearch.tracker.status.applied', 'Applied');
    if (status === 'interview') return tx('jobSearch.tracker.status.interview', 'Interview');
    if (status === 'offer') return tx('jobSearch.tracker.status.offer', 'Offer');
    return tx('jobSearch.tracker.status.rejected', 'Rejected');
  };

  const promptMarkApplied = (jobId: string) => {
    if (!jobId || markedJobIds.includes(jobId)) return;
    setMarkMsg('');
    setMarkPromptJobId(jobId);
  };

  const markApplied = async () => {
    const jobId = markPromptJobId;
    if (!jobId) return;
    setMarkBusy(true);
    try {
      const resp = await api.post('/job-search/applications/mark-applied', { job_id: jobId });
      const data = resp?.data || {};
      setMarkMsg(
        data.changed
          ? tx('jobSearch.docs.markAppliedDone', 'Moved to Applied in your tracker.')
          : `${tx('jobSearch.docs.markAppliedAlready', 'Already tracked as')} ${statusLabel(String(data.status || 'applied'))}`
      );
      setMarkedJobIds((prev) => [...prev, jobId]);
      setMarkPromptJobId('');
      onApplied();
    } catch {
      setMarkMsg(tx('jobSearch.docs.markAppliedFailed', 'Could not update your tracker right now.'));
    } finally {
      setMarkBusy(false);
    }
  };

  const emailKit = async () => {
    if (!activeDocJobId) return;
    setEmailingKit(true);
    setStatusMsg('');
    try {
      const resp = await api.post(`/job-search/documents/${activeDocJobId}/email`, {}, { timeout: 60000 });
      const sentTo = resp?.data?.sent_to || '';
      setStatusMsg(`${tx('jobSearch.docs.kitEmailed', 'Application kit sent to')} ${sentTo}`);
      promptMarkApplied(activeDocJobId);
    } catch {
      setStatusMsg(tx('jobSearch.docs.kitEmailFailed', 'Could not email your kit right now. Please retry.'));
    } finally {
      setEmailingKit(false);
    }
  };

  const downloadPdf = async () => {
    if (!activeDocJobId || Platform.OS !== 'web') return;
    setPdfDownloading(true);
    setStatusMsg('');
    try {
      const resp = await api.get(`/job-search/documents/${activeDocJobId}/pdf`, {
        params: { view: docView === 'cv' ? 'cv' : 'cover' },
        responseType: 'blob',
        timeout: 60000,
      });
      const blob = new Blob([resp.data], { type: 'application/pdf' });
      triggerBlobDownload(blob, `${docView === 'cv' ? 'cv' : 'cover-letter'}-${activeDocJobId}.pdf`);
      promptMarkApplied(activeDocJobId);
    } catch {
      setStatusMsg(tx('jobSearch.docs.pdfFailed', 'PDF export is unavailable right now. Please retry.'));
    } finally {
      setPdfDownloading(false);
    }
  };

  const loadDocs = useCallback(async () => {
    try {
      const resp = await api.get('/job-search/documents', { silentLoading: true });
      const list: JobDoc[] = resp?.data?.documents || [];
      setDocs(list);
      setLoadError(false);
      if (!activeDocJobId && list.length > 0) setActiveDocJobId(list[0].job_id);
    } catch {
      setLoadError(true);
    } finally {
      setLoading(false);
    }
  }, [activeDocJobId]);

  useEffect(() => { loadDocs(); }, [loadDocs]);
  useEffect(() => { if (selectedJobId) setActiveDocJobId(selectedJobId); }, [selectedJobId]);

  const generateKit = async () => {
    const jobId = selectedJobId || activeDocJobId;
    if (!jobId) {
      setStatusMsg(tx('jobSearch.docs.pickJobFirst', 'Pick a job in the Find Jobs tab first (Generate kit).'));
      return;
    }
    setGenerating(true);
    setStatusMsg(tx('jobSearch.docs.generating', 'Drafting, reviewing, and finalizing your documents… this can take up to a minute.'));
    try {
      const resp = await api.post('/job-search/documents/generate', { job_id: jobId }, { timeout: 180000 });
      const doc = resp?.data?.document;
      if (doc) {
        setDocs((prev) => [doc, ...prev.filter((d) => d.job_id !== doc.job_id)]);
        setActiveDocJobId(doc.job_id);
        setStatusMsg(tx('jobSearch.docs.generated', 'Your application kit is ready. A copy notification was emailed to you.'));
        onKitGenerated();
      }
    } catch (e: any) {
      const detail = e?.response?.data?.detail;
      setStatusMsg(detail === 'Complete your career profile first'
        ? tx('jobSearch.docs.profileFirst', 'Complete your career profile first, then generate documents.')
        : tx('jobSearch.docs.generateFailed', 'Document generation is unavailable right now. Please retry.'));
    } finally {
      setGenerating(false);
    }
  };

  const copyContent = async (content: string) => {
    try {
      if (Platform.OS === 'web' && typeof navigator !== 'undefined' && navigator.clipboard) {
        await navigator.clipboard.writeText(content);
        setCopiedMsg(tx('jobSearch.docs.copied', 'Copied to clipboard'));
        setTimeout(() => setCopiedMsg(''), 2500);
      }
    } catch {
      setCopiedMsg(tx('jobSearch.docs.copyFailed', 'Copy failed'));
    }
  };

  const activeDoc = docs.find((d) => d.job_id === activeDocJobId) || null;
  const activeContent = activeDoc ? (docView === 'cv' ? activeDoc.cv_markdown : activeDoc.cover_letter_markdown) : '';

  return (
    <View style={{ gap: 14 }}>
      <BillingSectionCard colors={colors} testId="job-search-docs-header-card">
        <Text style={{ color: colors.text, fontSize: 17, fontWeight: '800' }}>{tx('jobSearch.docs.title', 'Document studio')}</Text>
        <Text style={{ color: colors.textSecondary, fontSize: 12, lineHeight: 18, marginTop: 4, marginBottom: 12 }}>
          {tx('jobSearch.docs.subtitle', 'AI drafts your tailored CV and cover letter, a second reviewer agent critiques them, and the final versions are ATS-validated.')}
        </Text>
        {selectedJobTitle ? (
          <Text style={{ color: colors.textSecondary, fontSize: 12, marginBottom: 10 }} data-testid="job-search-docs-selected-job" testID="job-search-docs-selected-job">
            {tx('jobSearch.docs.selectedJob', 'Selected job')}: <Text style={{ color: colors.text, fontWeight: '800' }}>{selectedJobTitle}</Text>
          </Text>
        ) : null}
        <View style={{ flexDirection: 'row', gap: 8, flexWrap: 'wrap' }}>
          <BillingActionButton
            label={generating ? tx('jobSearch.docs.generatingShort', 'Generating…') : tx('jobSearch.docs.generate', 'Generate CV + cover letter')}
            onPress={generateKit}
            icon="sparkles-outline"
            colors={colors}
            testId="job-search-generate-docs-btn"
            disabled={generating}
          />
          {activeDoc ? (
            <BillingActionButton
              label={emailingKit ? tx('jobSearch.docs.kitEmailing', 'Sending…') : tx('jobSearch.docs.emailKit', 'Send kit to my email')}
              onPress={emailKit}
              icon="mail-outline"
              colors={colors}
              variant="secondary"
              testId="job-search-email-kit-btn"
              disabled={emailingKit}
            />
          ) : null}
        </View>
        {statusMsg ? <Text style={{ color: colors.textSecondary, fontSize: 12, marginTop: 10 }} data-testid="job-search-docs-status" testID="job-search-docs-status">{statusMsg}</Text> : null}
        {markPromptJobId ? (
          <View style={{ marginTop: 12, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.background, borderRadius: 14, padding: 12, flexDirection: 'row', alignItems: 'center', gap: 10, flexWrap: 'wrap' }} data-testid="job-search-mark-applied-prompt" testID="job-search-mark-applied-prompt">
            <Text style={{ color: colors.text, fontSize: 12.5, flex: 1, minWidth: 200, lineHeight: 18 }}>
              {tx('jobSearch.docs.markAppliedPrompt', 'Sent this kit to an employer? Mark the job as Applied in your tracker.')}
            </Text>
            <BillingActionButton
              label={markBusy ? tx('jobSearch.docs.markAppliedBusy', 'Updating…') : tx('jobSearch.docs.markApplied', 'Mark as Applied')}
              onPress={markApplied}
              icon="checkmark-circle-outline"
              colors={colors}
              testId="job-search-mark-applied-btn"
              disabled={markBusy}
            />
            <TouchableOpacity
              onPress={() => setMarkPromptJobId('')}
              data-testid="job-search-mark-applied-dismiss"
              testID="job-search-mark-applied-dismiss"
              accessibilityRole="button"
              accessibilityLabel={tx('jobSearch.docs.markAppliedDismiss', 'Dismiss')}
            >
              <Ionicons name="close" size={18} color={colors.textSecondary} />
            </TouchableOpacity>
          </View>
        ) : null}
        {markMsg ? <Text style={{ color: colors.successText, fontSize: 12, marginTop: 8 }} data-testid="job-search-mark-applied-msg" testID="job-search-mark-applied-msg">{markMsg}</Text> : null}
      </BillingSectionCard>

      {loading ? (
        <BillingSectionCard colors={colors} testId="job-search-docs-loading"><ActivityIndicator color={colors.primary} /></BillingSectionCard>
      ) : docs.length === 0 && loadError ? (
        <BillingSectionCard colors={colors} testId="job-search-docs-load-error">
          <Text style={{ color: colors.textSecondary, fontSize: 13 }}>{tx('jobSearch.docs.loadFailed', 'Could not load your documents right now.')}</Text>
          <View style={{ marginTop: 10, flexDirection: 'row' }}>
            <BillingActionButton label={tx('jobSearch.docs.retry', 'Retry')} onPress={() => { setLoading(true); loadDocs(); }} icon="refresh-outline" colors={colors} variant="subtle" testId="job-search-docs-retry-btn" />
          </View>
        </BillingSectionCard>
      ) : docs.length === 0 ? (
        <BillingSectionCard colors={colors} testId="job-search-docs-empty">
          <Text style={{ color: colors.textSecondary, fontSize: 13 }}>{tx('jobSearch.docs.empty', 'No documents yet. Pick a job and generate your first AI application kit.')}</Text>
        </BillingSectionCard>
      ) : (
        <>
          <View style={{ flexDirection: 'row', gap: 8, flexWrap: 'wrap' }}>
            {docs.map((doc, idx) => (
              <TouchableOpacity
                key={doc.job_id}
                onPress={() => setActiveDocJobId(doc.job_id)}
                style={{ backgroundColor: doc.job_id === activeDocJobId ? colors.primary : colors.card, borderWidth: 1, borderColor: doc.job_id === activeDocJobId ? colors.primary : colors.border, borderRadius: 999, paddingHorizontal: 14, paddingVertical: 8 }}
                data-testid={`job-search-doc-chip-${idx}`}
                testID={`job-search-doc-chip-${idx}`}
                accessibilityRole="button"
                accessibilityLabel={doc.job_title}
              >
                <Text style={{ color: doc.job_id === activeDocJobId ? colors.primaryText : colors.text, fontSize: 12, fontWeight: '700' }}>{doc.job_title}</Text>
              </TouchableOpacity>
            ))}
          </View>

          {activeDoc ? (
            <BillingSectionCard colors={colors} testId="job-search-doc-viewer">
              <View style={{ flexDirection: 'row', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
                {(['cv', 'cover'] as const).map((view) => (
                  <TouchableOpacity
                    key={view}
                    onPress={() => setDocView(view)}
                    style={{ backgroundColor: docView === view ? colors.primary : colors.background, borderWidth: 1, borderColor: docView === view ? colors.primary : colors.border, borderRadius: 10, paddingHorizontal: 12, paddingVertical: 7 }}
                    data-testid={`job-search-doc-view-${view}`}
                    testID={`job-search-doc-view-${view}`}
                    accessibilityRole="button"
                    accessibilityLabel={view === 'cv' ? tx('jobSearch.docs.cv', 'Tailored CV') : tx('jobSearch.docs.coverLetter', 'Cover letter')}
                  >
                    <Text style={{ color: docView === view ? colors.primaryText : colors.text, fontSize: 12, fontWeight: '800' }}>
                      {view === 'cv' ? tx('jobSearch.docs.cv', 'Tailored CV') : tx('jobSearch.docs.coverLetter', 'Cover letter')}
                    </Text>
                  </TouchableOpacity>
                ))}
                <View style={{ flex: 1 }} />
                <BillingActionButton label={tx('jobSearch.docs.copy', 'Copy')} onPress={() => copyContent(activeContent)} icon="copy-outline" colors={colors} variant="subtle" testId="job-search-doc-copy-btn" />
                <BillingActionButton
                  label={wordDownloading ? tx('jobSearch.docs.wordDownloading', 'Exporting…') : tx('jobSearch.docs.downloadWord', 'Download .Word')}
                  onPress={downloadWord}
                  icon="document-outline"
                  colors={colors}
                  variant="subtle"
                  testId="job-search-doc-download-word-btn"
                  disabled={wordDownloading}
                />
                <BillingActionButton
                  label={pdfDownloading ? tx('jobSearch.docs.pdfDownloading', 'Exporting…') : tx('jobSearch.docs.downloadPdf', 'Download .pdf')}
                  onPress={downloadPdf}
                  icon="document-attach-outline"
                  colors={colors}
                  variant="subtle"
                  testId="job-search-doc-download-pdf-btn"
                  disabled={pdfDownloading}
                />
              </View>
              {copiedMsg ? <Text style={{ color: colors.successText, fontSize: 11, marginTop: 6 }} data-testid="job-search-doc-copied" testID="job-search-doc-copied">{copiedMsg}</Text> : null}
              <View style={{ marginTop: 12, backgroundColor: colors.background, borderWidth: 1, borderColor: colors.border, borderRadius: 14, padding: 14 }}>
                <Text style={{ color: colors.text, fontSize: 12.5, lineHeight: 20, fontFamily: Platform.OS === 'web' ? 'monospace' : undefined }} data-testid="job-search-doc-content" testID="job-search-doc-content">
                  {activeContent}
                </Text>
              </View>

              {(activeDoc.reviewer_notes || []).length > 0 ? (
                <View style={{ marginTop: 12 }}>
                  <Text style={{ color: colors.textSecondary, fontSize: 11, fontWeight: '800', textTransform: 'uppercase', marginBottom: 4 }}>{tx('jobSearch.docs.reviewerNotes', 'Reviewer agent notes')}</Text>
                  {activeDoc.reviewer_notes.map((note, nIdx) => (
                    <Text key={nIdx} style={{ color: colors.textSecondary, fontSize: 12, lineHeight: 18 }}>• {note}</Text>
                  ))}
                </View>
              ) : null}

            </BillingSectionCard>
          ) : null}
        </>
      )}
    </View>
  );
};
