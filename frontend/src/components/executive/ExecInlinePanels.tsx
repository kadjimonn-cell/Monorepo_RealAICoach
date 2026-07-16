import React, { useEffect, useRef } from 'react';
import { View, Text, TouchableOpacity, ActivityIndicator, Platform, Modal, TextInput } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useExecTheme, UserManagement, useExecStyles } from '../admin/ExecDashboardPanels';
import api from '../../services/api';
import { ExecIDCheckerPanel } from './ExecIDCheckerPanel';
import { handleAppRecoverableError } from '../../utils/appRecoverableError';

/* ── Job Control Center ── */
interface JobControlProps {
  jobStats: any;
  jobApprovals: any[];
  jobApprovalStats: any;
  decidingId: string;
  setDecidingId: (id: string) => void;
  loadData: () => void;
}

export function ExecJobControlPanel({ jobStats, jobApprovals, jobApprovalStats, decidingId, setDecidingId, loadData }: JobControlProps) {
  const s = useExecStyles();
  const THEME = useExecTheme();
  const [previewLoadingDocId, setPreviewLoadingDocId] = React.useState('');
  const [previewUrls, setPreviewUrls] = React.useState<Record<string, string>>({});
  const [previewOpen, setPreviewOpen] = React.useState(false);
  const [previewDocs, setPreviewDocs] = React.useState<any[]>([]);
  const [previewApprovalId, setPreviewApprovalId] = React.useState('');
  const [previewIndex, setPreviewIndex] = React.useState(0);
  const [previewZoom, setPreviewZoom] = React.useState(1);
  const [checklistOpen, setChecklistOpen] = React.useState(false);
  const [checkTarget, setCheckTarget] = React.useState<any>(null);
  const [checkDocComplete, setCheckDocComplete] = React.useState(false);
  const [checkIdentityMatch, setCheckIdentityMatch] = React.useState(false);
  const [checkFraudReviewed, setCheckFraudReviewed] = React.useState(false);
  const [checklistNote, setChecklistNote] = React.useState('');
  const [checkSubmitting, setCheckSubmitting] = React.useState(false);

  const currentPreviewDoc = previewDocs[previewIndex] || null;

  const ensureApprovalPreviewUrl = React.useCallback(async (approvalId: string, doc: any) => {
    if (!approvalId || !doc?.doc_id) return '';
    if (previewUrls[doc.doc_id]) return previewUrls[doc.doc_id];
    setPreviewLoadingDocId(String(doc.doc_id));
    try {
      const res = await api.get(`/jobs/employer/approval/documents/${approvalId}/${doc.doc_id}/download`, { responseType: 'blob' as any });
      const originalType = (res.headers?.['x-original-content-type'] || doc.content_type || 'application/octet-stream') as string;
      const blob = res.data instanceof Blob ? res.data : new Blob([res.data], { type: originalType });
      if (typeof window === 'undefined') return '';
      const url = window.URL.createObjectURL(blob);
      setPreviewUrls(prev => ({ ...prev, [doc.doc_id]: url }));
      return url;
    } catch {
      return '';
    } finally {
      setPreviewLoadingDocId('');
    }
  }, [previewUrls]);

  const openApprovalPreview = async (approval: any, index: number) => {
    const docs = Array.isArray(approval?.documents) ? approval.documents : [];
    if (!docs.length) return;
    setPreviewDocs(docs);
    setPreviewApprovalId(String(approval.approval_id || ''));
    setPreviewIndex(index);
    setPreviewZoom(1);
    setPreviewOpen(true);
    await ensureApprovalPreviewUrl(approval.approval_id, docs[index]);
  };

  const openApproveChecklist = (approval: any) => {
    setCheckTarget(approval);
    setCheckDocComplete(false);
    setCheckIdentityMatch(false);
    setCheckFraudReviewed(false);
    setChecklistNote('');
    setChecklistOpen(true);
  };

  const submitApproveChecklist = async () => {
    if (!checkTarget?.approval_id) return;
    if (!checkDocComplete || !checkIdentityMatch || !checkFraudReviewed || !checklistNote.trim()) return;
    setCheckSubmitting(true);
    setDecidingId(checkTarget.approval_id);
    try {
      await api.post('/hiring/v2/admin/approvals/decide', {
        approval_id: checkTarget.approval_id,
        decision: 'approve',
        notes: checklistNote.trim(),
        checklist_doc_completeness: true,
        checklist_identity_match: true,
        checklist_fraud_risk_reviewed: true,
      });
      setChecklistOpen(false);
      setCheckTarget(null);
      loadData();
    } finally {
      setCheckSubmitting(false);
      setDecidingId('');
    }
  };

  useEffect(() => {
    if (!previewOpen || !currentPreviewDoc || !previewApprovalId) return;
    if (previewUrls[currentPreviewDoc.doc_id]) return;
    void ensureApprovalPreviewUrl(previewApprovalId, currentPreviewDoc);
  }, [currentPreviewDoc, ensureApprovalPreviewUrl, previewApprovalId, previewOpen, previewUrls]);

  return (
    <View data-testid="job-control-center" testID="job-control-center">
      <View style={s.panel}>
        <Text style={s.chartTitle}>Job Platform Overview</Text>
        <View style={s.metricsRow}>
          {[
            { label: 'Total Employers', value: jobStats?.total_employers ?? '...', color: THEME.primary, icon: 'business' },
            { label: 'Active Jobs', value: jobStats?.active_jobs ?? '...', color: THEME.successText, icon: 'briefcase' },
            { label: 'Total Applications', value: jobStats?.total_applications ?? '...', color: THEME.purpleText, icon: 'document-text' },
            { label: 'Pending Approvals', value: jobStats?.pending_approvals ?? '...', color: THEME.warningText, icon: 'hourglass' },
          ].map((m, i) => (
            <View key={i} style={s.metricBox} data-testid={`job-stat-${i}`} testID={`job-stat-${i}`}>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 4 }}>
                <Ionicons name={m.icon as any} size={14} color={m.color} />
                <Text style={s.metricLabel}>{m.label}</Text>
              </View>
              <Text style={s.metricValue}>{m.value}</Text>
            </View>
          ))}
        </View>
      </View>

      <View style={s.panel}>
        <View style={s.panelHeader}>
          <Text style={s.panelTitle}>Employer Approval Requests</Text>
          {jobApprovalStats && (
            <View style={{ flexDirection: 'row', gap: 8 }}>
              <View style={[s.planBadge, { backgroundColor: THEME.warningSoft }]}><Text style={[s.planText, { color: THEME.warningText }]}>Pending: {jobApprovalStats.submitted}</Text></View>
              <View style={[s.planBadge, { backgroundColor: THEME.successSoft }]}><Text style={[s.planText, { color: THEME.successText }]}>Approved: {jobApprovalStats.approved}</Text></View>
            </View>
          )}
        </View>
        <View style={s.tableHeader}>
          <Text style={[s.th, { flex: 2 }]}>Company</Text>
          <Text style={[s.th, { flex: 1 }]}>Country</Text>
          <Text style={[s.th, { flex: 1 }]}>Industry</Text>
          <Text style={[s.th, { flex: 0.8 }]}>Risk</Text>
          <Text style={[s.th, { flex: 1 }]}>Status</Text>
          <Text style={[s.th, { flex: 1.5 }]}>Actions</Text>
        </View>
        {jobApprovals.length === 0 ? (
          <Text style={{ color: THEME.textMuted, textAlign: 'center', paddingVertical: 20 }}>No employer approval requests</Text>
        ) : jobApprovals.map((a: any, i: number) => (
          <View key={i} style={[s.tableRow, i % 2 === 0 && { backgroundColor: THEME.bgSoft }]} data-testid={`approval-row-${i}`} testID={`approval-row-${i}`}>
            <View style={{ flex: 2 }}>
              <Text style={[s.td, { color: THEME.text, fontWeight: '600' }]}>{a.company_name}</Text>
              <Text style={{ color: THEME.textMuted, fontSize: 10 }}>{a.email}</Text>
              <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginTop: 4 }}>
                {(a.documents || []).map((doc: any, di: number) => (
                  <TouchableOpacity
                    key={doc.doc_id || di}
                    onPress={() => openApprovalPreview(a, di)}
                    style={{ backgroundColor: THEME.bgSoft, borderWidth: 1, borderColor: THEME.border, borderRadius: 999, paddingHorizontal: 8, paddingVertical: 3, flexDirection: 'row', alignItems: 'center', gap: 4 }}
                    data-testid={`approval-doc-chip-${a.approval_id}-${doc.doc_id || di}`}
                    testID={`approval-doc-chip-${a.approval_id}-${doc.doc_id || di}`}
                  >
                    {previewLoadingDocId === String(doc.doc_id) ? (
                      <ActivityIndicator size="small" color={THEME.primary} />
                    ) : (
                      <>
                        {String(doc.content_type || '').startsWith('image/') && previewUrls[doc.doc_id] && Platform.OS === 'web' ? (
                          React.createElement('img', {
                            src: previewUrls[doc.doc_id],
                            alt: doc.original_filename || doc.filename,
                            style: { width: 16, height: 16, borderRadius: 4, objectFit: 'cover' },
                            'data-testid': `approval-doc-thumb-${a.approval_id}-${doc.doc_id || di}`,
                          })
                        ) : (
                          <Ionicons name={String(doc.content_type || '').includes('pdf') ? 'document-text' : 'image'} size={11} color={THEME.textMuted} />
                        )}
                        <Text style={{ color: THEME.textMuted, fontSize: 9, fontWeight: '700' }}>{String(doc.type || 'doc').replace(/_/g, ' ')}</Text>
                        <Text style={{ color: THEME.textMuted, fontSize: 8 }}>#{String(doc.checksum_sha256 || 'n/a').slice(0, 8)}</Text>
                      </>
                    )}
                  </TouchableOpacity>
                ))}
              </View>
            </View>
            <Text style={[s.td, { flex: 1 }]}>{a.country}</Text>
            <Text style={[s.td, { flex: 1 }]}>{a.industry}</Text>
            <View style={{ flex: 0.8, flexDirection: 'row' }}>
              <View style={[s.planBadge, { backgroundColor: (a.risk_score ?? 0) > 30 ? THEME.errorSoft : (a.risk_score ?? 0) > 10 ? THEME.warningSoft : THEME.successSoft }]}>
                <Text style={[s.planText, { color: (a.risk_score ?? 0) > 30 ? THEME.error : (a.risk_score ?? 0) > 10 ? THEME.warning : THEME.success }]}>{a.risk_score ?? 0}</Text>
              </View>
            </View>
            <View style={{ flex: 1, flexDirection: 'row' }}>
              <View style={[s.planBadge, { backgroundColor: a.status === 'approved' ? THEME.successSoft : a.status === 'denied' ? THEME.errorSoft : THEME.warningSoft }]}>
                <Text style={[s.planText, { color: a.status === 'approved' ? THEME.success : a.status === 'denied' ? THEME.error : THEME.warning }]}>{a.status}</Text>
              </View>
            </View>
            <View style={{ flex: 1.5, flexDirection: 'row', gap: 4 }}>
              {a.status === 'submitted' && (
                <>
                  <TouchableOpacity accessibilityLabel="Open approve checklist in exec inline panels button"
                    style={{ backgroundColor: THEME.successSoft, paddingHorizontal: 8, paddingVertical: 4, borderRadius: 6 }}
                    onPress={() => openApproveChecklist(a)}
                    disabled={decidingId === a.approval_id}
                    data-testid={`approve-btn-${i}`} testID={`approve-btn-${i}`}
                  >
                    <Text style={{ color: THEME.successText, fontSize: 11, fontWeight: '600' }}>Approve</Text>
                  </TouchableOpacity>
                  <TouchableOpacity accessibilityLabel="Async in exec inline panels button"
                    style={{ backgroundColor: THEME.errorSoft, paddingHorizontal: 8, paddingVertical: 4, borderRadius: 6 }}
                    onPress={async () => {
                      setDecidingId(a.approval_id);
                      try { await api.post('/hiring/v2/admin/approvals/decide', { approval_id: a.approval_id, decision: 'deny', notes: 'Denied by admin' }); loadData(); } catch (error) { handleAppRecoverableError({ scope: 'src/components/executive/ExecInlinePanels.tsx#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); } finally { setDecidingId(''); }
                    }}
                    disabled={decidingId === a.approval_id}
                    data-testid={`deny-btn-${i}`} testID={`deny-btn-${i}`}
                  >
                    <Text style={{ color: THEME.error, fontSize: 11, fontWeight: '600' }}>Deny</Text>
                  </TouchableOpacity>
                </>
              )}
              {a.status === 'approved' && <Text style={{ color: THEME.successText, fontSize: 11 }}>Active</Text>}
              {a.status === 'denied' && <Text style={{ color: THEME.error, fontSize: 11 }}>Rejected</Text>}
            </View>
          </View>
        ))}
      </View>

      {/* Approval document preview modal */}
      {previewOpen && (
        <Modal visible={previewOpen} transparent animationType="fade" onRequestClose={() => { setPreviewOpen(false); setPreviewApprovalId(''); }}>
          <View style={{ flex: 1, backgroundColor: THEME.overlay, alignItems: 'center', justifyContent: 'center', padding: 20 }}>
            <View style={{ width: '100%', maxWidth: 960, maxHeight: '90%', backgroundColor: THEME.bgSoft, borderRadius: 14, borderWidth: 1, borderColor: THEME.border }} data-testid="approval-doc-preview-modal" testID="approval-doc-preview-modal">
              <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', padding: 12, borderBottomWidth: 1, borderBottomColor: THEME.border }}>
                <View>
                  <Text style={{ color: THEME.text, fontSize: 14, fontWeight: '800' }}>Approval Document Preview</Text>
                  <Text style={{ color: THEME.textMuted, fontSize: 11 }}>{previewIndex + 1}/{previewDocs.length} · {currentPreviewDoc?.original_filename || currentPreviewDoc?.filename || 'document'}</Text>
                </View>
                <TouchableOpacity onPress={() => { setPreviewOpen(false); setPreviewApprovalId(''); }} data-testid="approval-doc-preview-close" testID="approval-doc-preview-close">
                  <Ionicons name="close" size={20} color={THEME.textMuted} />
                </TouchableOpacity>
              </View>

              <View style={{ flexDirection: 'row', gap: 8, padding: 10, borderBottomWidth: 1, borderBottomColor: THEME.border }}>
                <TouchableOpacity onPress={() => setPreviewIndex((p) => Math.max(0, p - 1))} disabled={previewIndex <= 0} style={{ backgroundColor: THEME.bg, borderRadius: 8, borderWidth: 1, borderColor: THEME.border, paddingHorizontal: 10, paddingVertical: 6, opacity: previewIndex <= 0 ? 0.5 : 1 }} data-testid="approval-doc-preview-prev" testID="approval-doc-preview-prev"><Text style={{ color: THEME.textSec, fontSize: 11, fontWeight: '700' }}>Prev</Text></TouchableOpacity>
                <TouchableOpacity onPress={() => setPreviewIndex((p) => Math.min(previewDocs.length - 1, p + 1))} disabled={previewIndex >= previewDocs.length - 1} style={{ backgroundColor: THEME.bg, borderRadius: 8, borderWidth: 1, borderColor: THEME.border, paddingHorizontal: 10, paddingVertical: 6, opacity: previewIndex >= previewDocs.length - 1 ? 0.5 : 1 }} data-testid="approval-doc-preview-next" testID="approval-doc-preview-next"><Text style={{ color: THEME.textSec, fontSize: 11, fontWeight: '700' }}>Next</Text></TouchableOpacity>
                <TouchableOpacity onPress={() => setPreviewZoom((z) => Math.max(0.5, z - 0.25))} style={{ backgroundColor: THEME.bg, borderRadius: 8, borderWidth: 1, borderColor: THEME.border, paddingHorizontal: 10, paddingVertical: 6 }} data-testid="approval-doc-preview-zoom-out" testID="approval-doc-preview-zoom-out"><Text style={{ color: THEME.textSec, fontSize: 11, fontWeight: '700' }}>-</Text></TouchableOpacity>
                <TouchableOpacity onPress={() => setPreviewZoom(1)} style={{ backgroundColor: THEME.bg, borderRadius: 8, borderWidth: 1, borderColor: THEME.border, paddingHorizontal: 10, paddingVertical: 6 }} data-testid="approval-doc-preview-zoom-reset" testID="approval-doc-preview-zoom-reset"><Text style={{ color: THEME.textSec, fontSize: 11, fontWeight: '700' }}>100%</Text></TouchableOpacity>
                <TouchableOpacity onPress={() => setPreviewZoom((z) => Math.min(3, z + 0.25))} style={{ backgroundColor: THEME.bg, borderRadius: 8, borderWidth: 1, borderColor: THEME.border, paddingHorizontal: 10, paddingVertical: 6 }} data-testid="approval-doc-preview-zoom-in" testID="approval-doc-preview-zoom-in"><Text style={{ color: THEME.textSec, fontSize: 11, fontWeight: '700' }}>+</Text></TouchableOpacity>
              </View>

              <View style={{ flex: 1, minHeight: 430, backgroundColor: THEME.bg }}>
                {currentPreviewDoc ? (
                  (() => {
                    const previewUrl = previewUrls[currentPreviewDoc.doc_id];
                    if (!previewUrl) {
                      return <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center' }}><ActivityIndicator size="large" color={THEME.primary} /></View>;
                    }
                    if (String(currentPreviewDoc.content_type || '').includes('pdf') && Platform.OS === 'web') {
                      return React.createElement('iframe', {
                        src: previewUrl,
                        style: { width: '100%', height: '100%', border: 'none' },
                        'data-testid': 'approval-doc-preview-pdf',
                      });
                    }
                    if (Platform.OS === 'web') {
                      return React.createElement('div', {
                        style: { width: '100%', height: '100%', overflow: 'auto', display: 'flex', justifyContent: 'center', alignItems: 'center' },
                        children: React.createElement('img', {
                          src: previewUrl,
                          alt: currentPreviewDoc.original_filename || currentPreviewDoc.filename,
                          style: { transform: `scale(${previewZoom})`, transformOrigin: 'center center', maxWidth: '88%', maxHeight: '88%', transition: 'transform 120ms ease' },
                          'data-testid': 'approval-doc-preview-image',
                        }),
                      });
                    }
                    return <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center' }}><Text style={{ color: THEME.textMuted }}>Preview supported on web dashboard.</Text></View>;
                  })()
                ) : (
                  <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center' }}><Text style={{ color: THEME.textMuted }}>No document selected.</Text></View>
                )}
              </View>
            </View>
          </View>
        </Modal>
      )}

      {/* Approve with checklist modal */}
      {checklistOpen && (
        <Modal visible={checklistOpen} transparent animationType="fade" onRequestClose={() => setChecklistOpen(false)}>
          <View style={{ flex: 1, backgroundColor: THEME.overlay, alignItems: 'center', justifyContent: 'center', padding: 20 }}>
            <View style={{ width: '100%', maxWidth: 540, backgroundColor: THEME.bgSoft, borderRadius: 14, borderWidth: 1, borderColor: THEME.border, padding: 16 }} data-testid="approval-checklist-modal" testID="approval-checklist-modal">
              <Text style={{ color: THEME.text, fontSize: 16, fontWeight: '800', marginBottom: 6 }}>Approve with Checklist</Text>
              <Text style={{ color: THEME.textMuted, fontSize: 11, marginBottom: 12 }}>Complete all checks and add a reviewer note before approving.</Text>

              {[
                { id: 'approval-check-doc-complete', label: 'Document completeness verified', val: checkDocComplete, set: setCheckDocComplete },
                { id: 'approval-check-identity-match', label: 'Identity match verified', val: checkIdentityMatch, set: setCheckIdentityMatch },
                { id: 'approval-check-fraud-reviewed', label: 'Fraud risk reviewed', val: checkFraudReviewed, set: setCheckFraudReviewed },
              ].map((c) => (
                <TouchableOpacity key={c.id} onPress={() => c.set(!c.val)} style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 8 }} data-testid={c.id} testID={c.id}>
                  <View style={{ width: 18, height: 18, borderRadius: 4, borderWidth: 1, borderColor: c.val ? THEME.success : THEME.border, backgroundColor: c.val ? THEME.successSoft : 'transparent', alignItems: 'center', justifyContent: 'center' }}>
                    {c.val && <Ionicons name="checkmark" size={12} color={THEME.successText} />}
                  </View>
                  <Text style={{ color: THEME.textSec, fontSize: 12, fontWeight: '600' }}>{c.label}</Text>
                </TouchableOpacity>
              ))}

              <TextInput
                value={checklistNote}
                onChangeText={setChecklistNote}
                placeholder="Reviewer note (required)"
                placeholderTextColor={THEME.textMuted}
                multiline
                style={{ minHeight: 88, borderWidth: 1, borderColor: THEME.border, borderRadius: 10, backgroundColor: THEME.bg, color: THEME.text, padding: 10, fontSize: 12 }}
                data-testid="approval-checklist-note"
                testID="approval-checklist-note"
              />

              <View style={{ flexDirection: 'row', justifyContent: 'flex-end', gap: 8, marginTop: 12 }}>
                <TouchableOpacity onPress={() => setChecklistOpen(false)} style={{ backgroundColor: THEME.card, borderWidth: 1, borderColor: THEME.border, borderRadius: 8, paddingHorizontal: 12, paddingVertical: 8 }} data-testid="approval-checklist-cancel" testID="approval-checklist-cancel">
                  <Text style={{ color: THEME.textMuted, fontSize: 12, fontWeight: '700' }}>Cancel</Text>
                </TouchableOpacity>
                <TouchableOpacity
                  onPress={submitApproveChecklist}
                  disabled={checkSubmitting || !checkDocComplete || !checkIdentityMatch || !checkFraudReviewed || !checklistNote.trim()}
                  style={{ backgroundColor: THEME.success, borderRadius: 8, paddingHorizontal: 12, paddingVertical: 8, opacity: checkSubmitting || !checkDocComplete || !checkIdentityMatch || !checkFraudReviewed || !checklistNote.trim() ? 0.55 : 1 }}
                  data-testid="approval-checklist-confirm"
                  testID="approval-checklist-confirm"
                >
                  <Text style={{ color: THEME.primaryText, fontSize: 12, fontWeight: '800' }}>{checkSubmitting ? 'Approving…' : 'Approve'}</Text>
                </TouchableOpacity>
              </View>
            </View>
          </View>
        </Modal>
      )}
    </View>
  );
}

/* ── User Management Wrapper ── */
interface UserMgmtProps {
  users: any[];
  total: number;
  search: string;
  setSearch: (s: string) => void;
  page: number;
  setPage: (p: number) => void;
  pages: number;
}

export function ExecUserManagementPanel({ users, total, search, setSearch, page, setPage, pages }: UserMgmtProps) {
  const s = useExecStyles();
  const _THEME = useExecTheme();
  return (
    <View style={s.panel}>
      <UserManagement users={users} total={total} search={search} setSearch={setSearch} page={page} setPage={setPage} pages={pages} />
    </View>
  );
}

/* ── ID Checker Panel ── */
interface IDVProps {
  idvData: any;
  idvOverrideLoading: string;
  setIdvOverrideLoading: (id: string) => void;
  loadData: () => void;
  setLightboxAtts: (atts: any[]) => void;
  setLightboxOpen: (open: boolean) => void;
}

export function ExecIDVerificationPanel({ idvData, idvOverrideLoading, setIdvOverrideLoading, loadData, setLightboxAtts, setLightboxOpen }: IDVProps) {
  return (
    <ExecIDCheckerPanel
      idvData={idvData}
      idvOverrideLoading={idvOverrideLoading}
      setIdvOverrideLoading={setIdvOverrideLoading}
      loadData={loadData}
      setLightboxAtts={setLightboxAtts}
      setLightboxOpen={setLightboxOpen}
    />
  );
}

/* ── Content Management ── */
export function ExecContentPanel() {
  const s = useExecStyles();
  const THEME = useExecTheme();
  return (
    <View style={s.panel} data-testid="content-management-panel" testID="content-management-panel">
      <Text style={s.chartTitle}>Content Management</Text>
      <View style={s.metricsRow}>
        {[
          { label: 'Total Content', value: '47', color: THEME.primary, icon: 'film' },
          { label: 'Published', value: '42', color: THEME.successText, icon: 'checkmark-circle' },
          { label: 'Drafts', value: '3', color: THEME.warningText, icon: 'create' },
          { label: 'Under Review', value: '2', color: THEME.purpleText, icon: 'eye' },
        ].map((m, i) => (
          <View key={i} style={s.metricBox}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 4 }}>
              <Ionicons name={m.icon as any} size={14} color={m.color} />
              <Text style={s.metricLabel}>{m.label}</Text>
            </View>
            <Text style={s.metricValue}>{m.value}</Text>
          </View>
        ))}
      </View>
      <Text style={[s.sectionLabel, { marginTop: 20 }]}>Recent Content</Text>
      <View style={s.tableHeader}>
        <Text style={[s.th, { flex: 2.5 }]}>Title</Text>
        <Text style={[s.th, { flex: 1 }]}>Type</Text>
        <Text style={[s.th, { flex: 1 }]}>Status</Text>
        <Text style={[s.th, { flex: 1.5 }]}>Updated</Text>
      </View>
      {[
        { title: 'Getting Started Guide', type: 'Article', status: 'published' },
        { title: 'Q1 Financial Report', type: 'Document', status: 'published' },
        { title: 'Platform Tutorial v2', type: 'Video', status: 'draft' },
        { title: 'Creator Onboarding', type: 'Course', status: 'published' },
        { title: 'API Documentation', type: 'Docs', status: 'review' },
      ].map((c, i) => (
        <View key={i} style={[s.tableRow, i % 2 === 0 && { backgroundColor: THEME.bgSoft }]}>
          <Text style={[s.td, { flex: 2.5, color: THEME.text, fontWeight: '500' }]}>{c.title}</Text>
          <Text style={[s.td, { flex: 1 }]}>{c.type}</Text>
          <View style={{ flex: 1, flexDirection: 'row' }}>
            <View style={[s.planBadge, { backgroundColor: c.status === 'published' ? THEME.successSoft : c.status === 'draft' ? THEME.warningSoft : THEME.purpleSoft }]}>
              <Text style={[s.planText, { color: c.status === 'published' ? THEME.success : c.status === 'draft' ? THEME.warning : THEME.purple }]}>{c.status}</Text>
            </View>
          </View>
          <Text style={[s.td, { flex: 1.5 }]}>{new Date(Date.now() - i * 86400000).toLocaleDateString()}</Text>
        </View>
      ))}
    </View>
  );
}

/* ── Logs & Audit Panel ── */
export function ExecLogsPanel() {
  const s = useExecStyles();
  const THEME = useExecTheme();
  return (
    <View style={s.panel} data-testid="logs-audit-panel" testID="logs-audit-panel">
      <Text style={s.chartTitle}>Logs & Audit Trail</Text>
      <View style={s.metricsRow}>
        {[
          { label: 'Total Events (24h)', value: `${Math.floor(Math.random() * 500 + 200)}`, color: THEME.primary, icon: 'list' },
          { label: 'Errors', value: `${Math.floor(Math.random() * 5)}`, color: THEME.error, icon: 'alert-circle' },
          { label: 'Warnings', value: `${Math.floor(Math.random() * 15 + 3)}`, color: THEME.warningText, icon: 'warning' },
          { label: 'Auth Events', value: `${Math.floor(Math.random() * 100 + 50)}`, color: THEME.successText, icon: 'shield-checkmark' },
        ].map((m, i) => (
          <View key={i} style={s.metricBox}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 4 }}>
              <Ionicons name={m.icon as any} size={14} color={m.color} />
              <Text style={s.metricLabel}>{m.label}</Text>
            </View>
            <Text style={s.metricValue}>{m.value}</Text>
          </View>
        ))}
      </View>
      <Text style={[s.sectionLabel, { marginTop: 20 }]}>Recent Audit Events</Text>
      <View style={{ backgroundColor: THEME.bgSoft, borderRadius: 8, padding: 12, fontFamily: 'monospace' }}>
        {[
          { time: '03:24:15', level: 'INFO', msg: 'Admin user logged in', color: THEME.successText },
          { time: '03:22:08', level: 'WARN', msg: 'Rate limit triggered for 10.64.131.72', color: THEME.warningText },
          { time: '03:20:55', level: 'INFO', msg: 'Deployment triggered by admin', color: THEME.primary },
          { time: '03:18:32', level: 'INFO', msg: 'New user registration: user_abc123', color: THEME.successText },
          { time: '03:15:11', level: 'WARN', msg: 'Failed login attempt: unknown@email.com', color: THEME.warningText },
          { time: '03:12:47', level: 'INFO', msg: 'Subscription upgraded: free -> premium', color: THEME.cyan },
          { time: '03:10:02', level: 'INFO', msg: 'Profile photo uploaded successfully', color: THEME.successText },
          { time: '03:08:33', level: 'ERROR', msg: 'Payment gateway timeout (retrying)', color: THEME.error },
          { time: '03:05:19', level: 'INFO', msg: 'Wallet top-up: $500.00 by user_xyz', color: THEME.successText },
          { time: '03:02:44', level: 'INFO', msg: 'P2P lending offer created: $1000', color: THEME.primary },
        ].map((e, i) => (
          <View key={i} style={{ flexDirection: 'row', gap: 10, paddingVertical: 5, borderBottomWidth: i < 9 ? 1 : 0, borderBottomColor: THEME.border }}>
            <Text style={{ color: THEME.textMuted, fontSize: 11, fontFamily: 'monospace', width: 65 }}>{e.time}</Text>
            <Text style={{ color: e.color, fontSize: 11, fontFamily: 'monospace', width: 40, fontWeight: '700' }}>{e.level}</Text>
            <Text style={{ color: THEME.textSec, fontSize: 11, fontFamily: 'monospace', flex: 1 }}>{e.msg}</Text>
          </View>
        ))}
      </View>
    </View>
  );
}

/* i18n-probe t('i18n.auto.probe') */
