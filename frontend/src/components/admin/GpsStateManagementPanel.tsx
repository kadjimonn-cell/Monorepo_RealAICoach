import { useTranslation } from '../../hooks/useTranslation';
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { ActivityIndicator, ScrollView, StyleSheet, Text, TextInput, TouchableOpacity, View } from 'react-native';
import api from '../../services/api';

type SectionKey =
  | 'features'
  | 'plans'
  | 'faq'
  | 'labels'
  | 'knowledge'
  | 'outbox'
  | 'governance'
  | 'monitoring'
  | 'import-export';

const tx = (_key: string, fallback: string) => fallback;

const unwrap = (response: any) => response?.data ?? response;

interface Props {
  colors: any;
}

export default function GpsStateManagementPanel({ colors }: Props) {
  const { t } = useTranslation();
  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };

  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [section, setSection] = useState<SectionKey>('features');
  const [workflowMode, setWorkflowMode] = useState<'draft' | 'review' | 'publish'>('publish');
  const [state, setState] = useState<any>(null);
  const [selectedId, setSelectedId] = useState<string>('');
  const [reason, setReason] = useState('');
  const [editor, setEditor] = useState('{}');
  const [status, setStatus] = useState('');
  const [labelKey, setLabelKey] = useState('');
  const [labelValue, setLabelValue] = useState('');
  const [outboxStats, setOutboxStats] = useState<any>(null);
  const [selfHealingAudits, setSelfHealingAudits] = useState<any[]>([]);
  const [staleScan, setStaleScan] = useState<any>(null);
  const [paymentMonitor, setPaymentMonitor] = useState<any>(null);

  const [versions, setVersions] = useState<any[]>([]);
  const [selectedVersionId, setSelectedVersionId] = useState('');
  const [versionDiff, setVersionDiff] = useState<any>(null);
  const [changes, setChanges] = useState<any[]>([]);

  const [importSection, setImportSection] = useState('features');
  const [importFormat, setImportFormat] = useState<'json' | 'csv'>('json');
  const [importContent, setImportContent] = useState('');
  const [exportContent, setExportContent] = useState('');

  const styles = useMemo(() => createStyles(colors), [colors]);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const [gps, outbox, versionRows, changeRows, auditRows] = await Promise.all([
        api.get('/gps/state'),
        api.get('/gps/admin/outbox/stats').catch(() => ({ queued: 0, retrying: 0, failed: 0, sent: 0 })),
        api.get('/gps/admin/versions?limit=40').catch(() => ({ versions: [] })),
        api.get('/gps/admin/changes').catch(() => ({ changes: [] })),
        api.get('/gps/admin/audit/self-healing?limit=30').catch(() => ({ audits: [] })),
      ]);
      const gpsData = unwrap(gps);
      const outboxData = unwrap(outbox);
      const versionData = unwrap(versionRows);
      const changeData = unwrap(changeRows);
      const auditData = unwrap(auditRows);
      setState(gpsData || null);
      setOutboxStats(outboxData || null);
      setVersions(versionData?.versions || []);
      setChanges(changeData?.changes || []);
      setSelfHealingAudits(auditData?.audits || []);
      setStatus('GPS control center refreshed');
    } catch (e: any) {
      setStatus(e?.message || 'Failed to refresh GPS control center');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  useEffect(() => {
    if (section !== 'monitoring') return;
    let cancelled = false;
    const loadMonitoring = async () => {
      try {
        const [scanRows, paymentRows, auditRows] = await Promise.all([
          api.get('/gps/admin/compliance/stale-count-scan').catch(() => ({ passed: false, finding_count: 0, findings: [], error: 'scan unavailable' })),
          api.get('/gps/admin/payment-plan-monitor').catch(() => ({ status: 'unknown', error: 'payment monitor unavailable' })),
          api.get('/gps/admin/audit/self-healing?limit=30').catch(() => ({ audits: [] })),
        ]);
        if (cancelled) return;
        setStaleScan(unwrap(scanRows) || null);
        setPaymentMonitor(unwrap(paymentRows) || null);
        setSelfHealingAudits(unwrap(auditRows)?.audits || []);
      } catch {
        if (!cancelled) setStatus('Monitoring refresh failed');
      }
    };
    loadMonitoring();
    return () => { cancelled = true; };
  }, [section]);

  const items = useMemo(() => {
    if (!state) return [];
    if (section === 'features') return state.features || [];
    if (section === 'plans') return state.plans || [];
    if (section === 'faq') return state.faq || [];
    if (section === 'knowledge') return state.assistant_knowledge?.documents || [];
    if (section === 'labels') return Object.entries(state.ui_labels || {}).map(([k, v]) => ({ key: k, value: v }));
    return [];
  }, [section, state]);

  const getItemId = (item: any) => {
    if (section === 'features') return item.feature_id;
    if (section === 'plans') return item.plan_id;
    if (section === 'faq') return item.faq_id;
    if (section === 'knowledge') return item.doc_id || item.id;
    if (section === 'labels') return item.key;
    return '';
  };

  const onSelectItem = (item: any) => {
    const id = getItemId(item);
    setSelectedId(id || '');
    if (section === 'labels') {
      setLabelKey(item.key || '');
      setLabelValue(String(item.value || ''));
      setEditor('{}');
    } else {
      setEditor(JSON.stringify(item, null, 2));
    }
  };

  const parseEditor = () => {
    try {
      return JSON.parse(editor || '{}');
    } catch {
      throw new Error('Invalid JSON payload');
    }
  };

  const upsert = async () => {
    setSaving(true);
    try {
      let response: any = null;
      if (section === 'features') {
        response = await api.post('/gps/admin/features/upsert', { item: parseEditor(), reason, workflow_mode: workflowMode });
      } else if (section === 'plans') {
        response = await api.post('/gps/admin/plans/upsert', { item: parseEditor(), reason, workflow_mode: workflowMode });
      } else if (section === 'faq') {
        response = await api.post('/gps/admin/faq/upsert', { item: parseEditor(), reason, workflow_mode: workflowMode });
      } else if (section === 'knowledge') {
        response = await api.post('/gps/admin/knowledge/upsert', { item: parseEditor(), reason, workflow_mode: workflowMode });
      } else if (section === 'labels') {
        if (!labelKey.trim()) throw new Error('Label key is required');
        response = await api.put('/gps/admin/ui-label', { key: labelKey.trim(), value: labelValue, reason, workflow_mode: workflowMode });
      }
      const saved = unwrap(response);
      await refresh();
      setStatus(saved?.status === 'queued_for_approval' ? 'Peer review required before publish' : workflowMode === 'publish' ? 'Published successfully' : `Queued for ${workflowMode}`);
    } catch (e: any) {
      setStatus(e?.message || 'Save failed');
    } finally {
      setSaving(false);
    }
  };

  const remove = async () => {
    if (!selectedId) {
      setStatus('Select an item first');
      return;
    }
    setSaving(true);
    try {
      const qs = `reason=${encodeURIComponent(reason || 'Admin deletion')}&workflow_mode=${workflowMode}`;
      let response: any = null;
      if (section === 'features') {
        response = await api.delete(`/gps/admin/features/${encodeURIComponent(selectedId)}?${qs}`);
      } else if (section === 'plans') {
        response = await api.delete(`/gps/admin/plans/${encodeURIComponent(selectedId)}?${qs}`);
      } else if (section === 'faq') {
        response = await api.delete(`/gps/admin/faq/${encodeURIComponent(selectedId)}?${qs}`);
      } else if (section === 'knowledge') {
        response = await api.delete(`/gps/admin/knowledge/${encodeURIComponent(selectedId)}?${qs}`);
      } else if (section === 'labels') {
        response = await api.delete(`/gps/admin/ui-label/${encodeURIComponent(selectedId)}?${qs}`);
      }
      const removed = unwrap(response);
      setSelectedId('');
      setEditor('{}');
      setLabelKey('');
      setLabelValue('');
      await refresh();
      setStatus(removed?.status === 'queued_for_approval' ? 'Delete queued for peer review' : workflowMode === 'publish' ? 'Deleted successfully' : `Delete request queued for ${workflowMode}`);
    } catch (e: any) {
      setStatus(e?.message || 'Delete failed');
    } finally {
      setSaving(false);
    }
  };

  const runOutboxAction = async (mode: 'replay' | 'reconcile') => {
    setSaving(true);
    try {
      const url = mode === 'replay' ? '/gps/admin/outbox/replay' : '/gps/admin/outbox/reconcile';
      const response = await api.post(url, { batch_size: 500 });
      await refresh();
      setStatus(`${mode} complete: ${JSON.stringify(response?.result || {})}`);
    } catch (e: any) {
      setStatus(e?.message || `${mode} failed`);
    } finally {
      setSaving(false);
    }
  };

  const loadDiff = async (versionId: string) => {
    setSaving(true);
    try {
      const diff = await api.get(`/gps/admin/versions/${encodeURIComponent(versionId)}/diff?against=previous`);
      setSelectedVersionId(versionId);
      setVersionDiff(unwrap(diff));
      setStatus('Loaded version diff');
    } catch (e: any) {
      setStatus(e?.message || 'Failed to load diff');
    } finally {
      setSaving(false);
    }
  };

  const rollbackVersion = async () => {
    if (!selectedVersionId) {
      setStatus('Select a version first');
      return;
    }
    setSaving(true);
    try {
      const response = unwrap(await api.post(`/gps/admin/versions/${encodeURIComponent(selectedVersionId)}/rollback?reason=${encodeURIComponent(reason || 'Governance rollback')}`));
      await refresh();
      setStatus(response?.status === 'queued_for_approval' ? 'Rollback queued for peer review' : `Rolled back to version snapshot ${selectedVersionId}`);
    } catch (e: any) {
      setStatus(e?.message || 'Rollback failed');
    } finally {
      setSaving(false);
    }
  };

  const changeAction = async (requestId: string, action: 'submit-review' | 'approve-publish' | 'reject') => {
    setSaving(true);
    try {
      const suffix = action === 'reject' ? `?reason=${encodeURIComponent(reason || 'Rejected by reviewer')}` : '';
      await api.post(`/gps/admin/changes/${encodeURIComponent(requestId)}/${action}${suffix}`);
      await refresh();
      setStatus(`Change ${requestId} -> ${action}`);
    } catch (e: any) {
      setStatus(e?.message || 'Change workflow action failed');
    } finally {
      setSaving(false);
    }
  };

  const exportData = async (format: 'json' | 'csv') => {
    setSaving(true);
    try {
      const response = unwrap(await api.get(`/gps/admin/export?section=${encodeURIComponent(importSection)}&format=${format}`));
      const content = format === 'json' ? JSON.stringify(response?.data || response, null, 2) : String(response?.content || '');
      setExportContent(content);
      setStatus(`Exported ${importSection} as ${format.toUpperCase()}`);
    } catch (e: any) {
      setStatus(e?.message || 'Export failed');
    } finally {
      setSaving(false);
    }
  };

  const importData = async () => {
    setSaving(true);
    try {
      const response = unwrap(await api.post('/gps/admin/import', {
        section: importSection,
        format: importFormat,
        content: importContent,
        workflow_mode: workflowMode,
        reason,
      }));
      await refresh();
      setStatus(response?.status === 'queued_for_approval' ? 'Import queued for peer review' : workflowMode === 'publish' ? 'Import published successfully' : `Import queued for ${workflowMode}`);
    } catch (e: any) {
      setStatus(e?.message || 'Import failed');
    } finally {
      setSaving(false);
    }
  };

  const runMonitoringCheck = async (kind: 'scan' | 'payment') => {
    setSaving(true);
    try {
      if (kind === 'scan') {
        const response = unwrap(await api.get('/gps/admin/compliance/stale-count-scan'));
        setStaleScan(response);
        setStatus(`Stale-count scan ${response?.passed ? 'passed' : 'needs attention'}`);
      } else {
        const response = unwrap(await api.get('/gps/admin/payment-plan-monitor'));
        setPaymentMonitor(response);
        setStatus(`Payment plan monitor: ${response?.status || 'unknown'}`);
      }
      const auditRows = unwrap(await api.get('/gps/admin/audit/self-healing?limit=30').catch(() => ({ audits: [] })));
      setSelfHealingAudits(auditRows?.audits || []);
    } catch (e: any) {
      setStatus(e?.message || 'Monitoring check failed');
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <View style={styles.loadingWrap} data-testid="gps-admin-loading" testID="gps-admin-loading">
        <ActivityIndicator size="small" color={colors.primary} />
        <Text style={styles.loadingText}>{tx('admin.gpsStateManagementPanel.auto.text.001', 'Loading GPS control plane…')}</Text>
      </View>
    );
  }

  const sectionTabs: SectionKey[] = ['features', 'plans', 'faq', 'labels', 'knowledge', 'governance', 'monitoring', 'import-export', 'outbox'];

  return (
    <View style={styles.root} data-testid="gps-admin-panel" testID="gps-admin-panel">
      <Text style={styles.title} data-testid="gps-admin-title" testID="gps-admin-title">{tx('admin.gpsStateManagementPanel.auto.text.002', 'GlobalPlatformState Control Center')}</Text>
      <Text style={styles.subtitle} data-testid="gps-admin-subtitle" testID="gps-admin-subtitle">{tx('admin.gpsStateManagementPanel.auto.text.003', 'CRUD + approvals + audit timeline/diff/rollback + CSV/JSON import/export + delivery reconciliation.')}</Text>

      <View style={styles.policyBanner} data-testid="gps-maker-checker-policy-banner" testID="gps-maker-checker-policy-banner">
        <Text style={styles.policyBannerText} data-testid="gps-maker-checker-policy-text" testID="gps-maker-checker-policy-text">{tx('admin.gpsStateManagementPanel.auto.text.004', 'Two-person publish control is active for high-impact GPS changes.')}</Text>
      </View>

      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.sectionRow}>
        {sectionTabs.map((key) => {
          const active = section === key;
          return (
            <TouchableOpacity accessibilityLabel="Set section in gps state management panel"
              key={key}
              onPress={() => setSection(key)}
              {...({ onClick: () => setSection(key) } as any)}
              style={[styles.sectionChip, active ? styles.sectionChipActive : null]}
              data-testid={`gps-section-${key}`}
              testID={`gps-section-${key}`}
            >
              <Text style={[styles.sectionChipText, active ? styles.sectionChipTextActive : null]}>{key.toUpperCase()}</Text>
            </TouchableOpacity>
          );
        })}
      </ScrollView>

      <View style={styles.modeRow}>
        {(['draft', 'review', 'publish'] as const).map((mode) => {
          const active = workflowMode === mode;
          return (
            <TouchableOpacity
              key={mode}
              onPress={() => setWorkflowMode(mode)}
              style={[styles.modeChip, active ? styles.modeChipActive : null]}
              data-testid={`gps-workflow-${mode}`}
              testID={`gps-workflow-${mode}`}
            >
              <Text style={[styles.modeChipText, active ? styles.modeChipTextActive : null]}>{mode.toUpperCase()}</Text>
            </TouchableOpacity>
          );
        })}
      </View>

      <View style={styles.monitorStrip} data-testid="gps-monitoring-section" testID="gps-monitoring-section">
        <View style={[styles.badge, staleScan?.passed !== false ? styles.goodBadge : styles.warnBadge]} data-testid="gps-stale-count-badge" testID="gps-stale-count-badge">
          <Text style={styles.badgeText}>{staleScan?.passed === false ? `STALE COUNT FINDINGS: ${staleScan?.finding_count || 0}` : 'STALE COUNT CLEAN'}</Text>
        </View>
        <View style={[styles.badge, paymentMonitor?.status !== 'attention' ? styles.goodBadge : styles.warnBadge]} data-testid="gps-payment-drift-badge" testID="gps-payment-drift-badge">
          <Text style={styles.badgeText}>PAYMENT PLAN MONITOR: {(paymentMonitor?.status || 'HEALTHY').toUpperCase()}</Text>
        </View>
        <TouchableOpacity style={styles.secondaryBtn} onPress={() => runMonitoringCheck('scan')} data-testid="gps-run-stale-scan-btn" testID="gps-run-stale-scan-btn" disabled={saving}>
          <Text style={styles.secondaryBtnText}>{tx('admin.gpsStateManagementPanel.auto.text.005', 'Run Stale Scan')}</Text>
        </TouchableOpacity>
        <TouchableOpacity style={styles.secondaryBtn} onPress={() => runMonitoringCheck('payment')} data-testid="gps-run-payment-monitor-btn" testID="gps-run-payment-monitor-btn" disabled={saving}>
          <Text style={styles.secondaryBtnText}>{tx('admin.gpsStateManagementPanel.auto.text.006', 'Run Payment Monitor')}</Text>
        </TouchableOpacity>
        <Text style={styles.monitorTitle} data-testid="gps-self-healing-title" testID="gps-self-healing-title">Self-Healing Audit: {selfHealingAudits.length}</Text>
      </View>

      {section === 'outbox' && (
        <View style={styles.outboxCard} data-testid="gps-outbox-card" testID="gps-outbox-card">
          <Text style={styles.paneTitle}>{tx('admin.gpsStateManagementPanel.auto.text.007', 'Notification Outbox')}</Text>
          <Text style={styles.outboxLine}>Queued: {outboxStats?.queued || 0}</Text>
          <Text style={styles.outboxLine}>Retrying: {outboxStats?.retrying || 0}</Text>
          <Text style={styles.outboxLine}>Failed: {outboxStats?.failed || 0}</Text>
          <Text style={styles.outboxLine}>Sent: {outboxStats?.sent || 0}</Text>
          <View style={styles.actionRow}>
            <TouchableOpacity style={styles.primaryBtn} onPress={() => runOutboxAction('replay')} data-testid="gps-outbox-replay-btn" testID="gps-outbox-replay-btn" disabled={saving}>
              <Text style={styles.primaryBtnText}>{tx('admin.gpsStateManagementPanel.auto.text.008', 'Run Replay Worker')}</Text>
            </TouchableOpacity>
            <TouchableOpacity style={styles.secondaryBtn} onPress={() => runOutboxAction('reconcile')} data-testid="gps-outbox-reconcile-btn" testID="gps-outbox-reconcile-btn" disabled={saving}>
              <Text style={styles.secondaryBtnText}>{tx('admin.gpsStateManagementPanel.auto.text.009', 'Run Reconcile')}</Text>
            </TouchableOpacity>
            <TouchableOpacity style={styles.secondaryBtn} onPress={refresh} data-testid="gps-outbox-refresh-btn" testID="gps-outbox-refresh-btn" disabled={saving}>
              <Text style={styles.secondaryBtnText}>{tx('admin.gpsStateManagementPanel.auto.text.010', 'Refresh Stats')}</Text>
            </TouchableOpacity>
          </View>
        </View>
      )}

      {section === 'governance' && (
        <View style={styles.grid}>
          <View style={styles.leftPane}>
            <Text style={styles.paneTitle} data-testid="gps-versions-title" testID="gps-versions-title">Audit Timeline ({versions.length})</Text>
            <ScrollView style={{ maxHeight: 300 }}>
              {versions.map((version) => (
                <TouchableOpacity
                  key={version.version_id}
                  style={[styles.itemRow, selectedVersionId === version.version_id ? styles.itemRowActive : null]}
                  onPress={() => loadDiff(version.version_id)}
                  data-testid={`gps-version-${version.version_id}`}
                  testID={`gps-version-${version.version_id}`}
                >
                  <Text style={styles.itemId}>v{version.version}</Text>
                  <Text style={styles.itemMeta}>{version.event_type} • {version.created_at}</Text>
                </TouchableOpacity>
              ))}
            </ScrollView>
            <TouchableOpacity style={styles.warnBtn} onPress={rollbackVersion} data-testid="gps-rollback-btn" testID="gps-rollback-btn" disabled={saving}>
              <Text style={styles.warnBtnText}>{tx('admin.gpsStateManagementPanel.auto.text.011', 'Rollback Selected Version')}</Text>
            </TouchableOpacity>
          </View>

          <View style={styles.rightPane}>
            <Text style={styles.paneTitle} data-testid="gps-diff-title" testID="gps-diff-title">{tx('admin.gpsStateManagementPanel.auto.text.012', 'Diff Viewer')}</Text>
            <TextInput style={styles.editor} multiline editable={false} value={JSON.stringify(versionDiff || {}, null, 2)} data-testid="gps-diff-viewer" testID="gps-diff-viewer" accessibilityLabel="GPS diff viewer" />

            <Text style={[styles.paneTitle, { marginTop: 10 }]} data-testid="gps-approvals-title" testID="gps-approvals-title">Role-Scoped Approvals ({changes.length})</Text>
            <ScrollView style={{ maxHeight: 220 }}>
              {changes.slice(0, 40).map((change) => (
                <View key={change.request_id} style={styles.changeCard} data-testid={`gps-change-${change.request_id}`} testID={`gps-change-${change.request_id}`}>
                  <Text style={styles.itemId}>{change.request_id}</Text>
                  <Text style={styles.itemMeta}>{change.entity_type}/{change.operation} • {change.status}</Text>
                  {change.requires_peer_review ? (
                    <Text style={styles.peerReviewBadge} data-testid={`gps-change-peer-review-${change.request_id}`} testID={`gps-change-peer-review-${change.request_id}`}>{tx('admin.gpsStateManagementPanel.auto.text.013', 'PEER REVIEW REQUIRED')}</Text>
                  ) : null}
                  <View style={styles.actionRow}>
                    <TouchableOpacity style={styles.secondaryBtn} onPress={() => changeAction(change.request_id, 'submit-review')} data-testid={`gps-change-submit-${change.request_id}`} testID={`gps-change-submit-${change.request_id}`}>
                      <Text style={styles.secondaryBtnText}>{tx('admin.gpsStateManagementPanel.auto.text.014', 'Submit Review')}</Text>
                    </TouchableOpacity>
                    <TouchableOpacity style={styles.primaryBtn} onPress={() => changeAction(change.request_id, 'approve-publish')} data-testid={`gps-change-approve-${change.request_id}`} testID={`gps-change-approve-${change.request_id}`}>
                      <Text style={styles.primaryBtnText}>{tx('admin.gpsStateManagementPanel.auto.text.015', 'Approve & Publish')}</Text>
                    </TouchableOpacity>
                    <TouchableOpacity style={styles.warnBtn} onPress={() => changeAction(change.request_id, 'reject')} data-testid={`gps-change-reject-${change.request_id}`} testID={`gps-change-reject-${change.request_id}`}>
                      <Text style={styles.warnBtnText}>{tx('admin.gpsStateManagementPanel.auto.text.016', 'Reject')}</Text>
                    </TouchableOpacity>
                  </View>
                </View>
              ))}
            </ScrollView>
          </View>
        </View>
      )}

      {section === 'monitoring' && (
        <View style={styles.grid} data-testid="gps-monitoring-detail-section" testID="gps-monitoring-detail-section">
          <View style={styles.leftPane}>
            <Text style={styles.paneTitle} data-testid="gps-compliance-detail-title" testID="gps-compliance-detail-title">{tx('admin.gpsStateManagementPanel.auto.text.017', 'Compliance Score')}</Text>
            <View style={[styles.badge, staleScan?.passed ? styles.goodBadge : styles.warnBadge]} data-testid="gps-stale-count-detail-badge" testID="gps-stale-count-detail-badge">
              <Text style={styles.badgeText}>{staleScan?.passed ? 'STALE COUNT CLEAN' : `STALE COUNT FINDINGS: ${staleScan?.finding_count || 0}`}</Text>
            </View>
            <View style={[styles.badge, paymentMonitor?.status === 'healthy' ? styles.goodBadge : styles.warnBadge]} data-testid="gps-payment-drift-detail-badge" testID="gps-payment-drift-detail-badge">
              <Text style={styles.badgeText}>PAYMENT PLAN MONITOR: {(paymentMonitor?.status || 'UNKNOWN').toUpperCase()}</Text>
            </View>
            <Text style={styles.outboxLine} data-testid="gps-payment-drift-summary" testID="gps-payment-drift-summary">
              Plans: {paymentMonitor?.plan_count ?? 0} • Recent tx: {paymentMonitor?.recent_transaction_count ?? 0} • Mismatches: {paymentMonitor?.transaction_mismatches?.length || 0}
            </Text>
            <View style={styles.actionRow}>
              <TouchableOpacity style={styles.primaryBtn} onPress={() => runMonitoringCheck('scan')} data-testid="gps-run-stale-scan-detail-btn" testID="gps-run-stale-scan-detail-btn" disabled={saving}>
                <Text style={styles.primaryBtnText}>{tx('admin.gpsStateManagementPanel.auto.text.018', 'Run Stale Scan')}</Text>
              </TouchableOpacity>
              <TouchableOpacity style={styles.secondaryBtn} onPress={() => runMonitoringCheck('payment')} data-testid="gps-run-payment-monitor-detail-btn" testID="gps-run-payment-monitor-detail-btn" disabled={saving}>
                <Text style={styles.secondaryBtnText}>{tx('admin.gpsStateManagementPanel.auto.text.019', 'Run Payment Monitor')}</Text>
              </TouchableOpacity>
            </View>
            <TextInput style={[styles.editor, { marginTop: 10 }]} multiline editable={false} value={JSON.stringify({ staleScan, paymentMonitor }, null, 2)} data-testid="gps-monitoring-json" testID="gps-monitoring-json" accessibilityLabel="GPS monitoring JSON" />
          </View>

          <View style={styles.rightPane}>
            <Text style={styles.paneTitle} data-testid="gps-self-healing-detail-title" testID="gps-self-healing-detail-title">Self-Healing Audit ({selfHealingAudits.length})</Text>
            <ScrollView style={{ maxHeight: 520 }}>
              {selfHealingAudits.map((audit) => (
                <View key={audit.audit_id} style={styles.changeCard} data-testid={`gps-self-healing-${audit.audit_id}`} testID={`gps-self-healing-${audit.audit_id}`}>
                  <Text style={styles.itemId}>{audit.audit_id}</Text>
                  <Text style={styles.itemMeta}>{audit.source} • {audit.created_at}</Text>
                  <Text style={styles.itemMeta}>Repairs: {audit.repair_count}</Text>
                  <Text style={styles.auditJson} numberOfLines={6}>{JSON.stringify(audit.repairs || [], null, 2)}</Text>
                </View>
              ))}
              {selfHealingAudits.length === 0 && (
                <Text style={styles.itemMeta} data-testid="gps-self-healing-empty" testID="gps-self-healing-empty">{tx('admin.gpsStateManagementPanel.auto.text.020', 'No self-healing repairs logged yet.')}</Text>
              )}
            </ScrollView>
          </View>
        </View>
      )}

      {section === 'import-export' && (
        <View style={styles.grid}>
          <View style={styles.leftPane}>
            <Text style={styles.paneTitle}>{tx('admin.gpsStateManagementPanel.auto.text.021', 'Bulk Import / Export')}</Text>
            <TextInput style={styles.input} value={importSection} onChangeText={setImportSection} placeholder={tx('admin.gpsStateManagementPanel.auto.placeholder.001', 'section (features/plans/faq/labels/knowledge/full)')} placeholderTextColor={colors.textMuted} data-testid="gps-import-section-input" testID="gps-import-section-input" />
            <TextInput style={[styles.input, { marginTop: 8 }]} value={importFormat} onChangeText={(v) => setImportFormat((v?.toLowerCase() === 'csv' ? 'csv' : 'json'))} placeholder={tx('admin.gpsStateManagementPanel.auto.placeholder.002', 'format json|csv')} placeholderTextColor={colors.textMuted} data-testid="gps-import-format-input" testID="gps-import-format-input" />
            <TextInput style={[styles.editor, { marginTop: 8 }]} multiline value={importContent} onChangeText={setImportContent} placeholder={tx('admin.gpsStateManagementPanel.auto.placeholder.003', 'Paste JSON or CSV payload')} placeholderTextColor={colors.textMuted} data-testid="gps-import-content-input" testID="gps-import-content-input" />
            <View style={styles.actionRow}>
              <TouchableOpacity style={styles.primaryBtn} onPress={importData} data-testid="gps-import-run-btn" testID="gps-import-run-btn" disabled={saving}>
                <Text style={styles.primaryBtnText}>{tx('admin.gpsStateManagementPanel.auto.text.022', 'Run Import')}</Text>
              </TouchableOpacity>
              <TouchableOpacity style={styles.secondaryBtn} onPress={() => exportData('json')} data-testid="gps-export-json-btn" testID="gps-export-json-btn" disabled={saving}>
                <Text style={styles.secondaryBtnText}>{tx('admin.gpsStateManagementPanel.auto.text.023', 'Export JSON')}</Text>
              </TouchableOpacity>
              <TouchableOpacity style={styles.secondaryBtn} onPress={() => exportData('csv')} data-testid="gps-export-csv-btn" testID="gps-export-csv-btn" disabled={saving}>
                <Text style={styles.secondaryBtnText}>{tx('admin.gpsStateManagementPanel.auto.text.024', 'Export CSV')}</Text>
              </TouchableOpacity>
            </View>
          </View>
          <View style={styles.rightPane}>
            <Text style={styles.paneTitle}>{tx('admin.gpsStateManagementPanel.auto.text.025', 'Export Preview')}</Text>
            <TextInput style={styles.editor} multiline editable={false} value={exportContent} data-testid="gps-export-preview" testID="gps-export-preview" accessibilityLabel="GPS export preview" />
          </View>
        </View>
      )}

      {!['outbox', 'governance', 'monitoring', 'import-export'].includes(section) && (
        <View style={styles.grid}>
          <View style={styles.leftPane}>
            <Text style={styles.paneTitle} data-testid="gps-items-title" testID="gps-items-title">Items ({items.length})</Text>
            <ScrollView style={{ maxHeight: 360 }}>
              {items.map((item: any, index: number) => {
                const id = getItemId(item) || `item-${index}`;
                const active = selectedId === id;
                return (
                  <TouchableOpacity key={id} onPress={() => onSelectItem(item)} style={[styles.itemRow, active ? styles.itemRowActive : null]} data-testid={`gps-item-${id}`} testID={`gps-item-${id}`}>
                    <Text style={styles.itemId}>{id}</Text>
                    <Text style={styles.itemMeta} numberOfLines={1}>{item.title || item.name || item.question || item.key || 'Untitled'}</Text>
                  </TouchableOpacity>
                );
              })}
            </ScrollView>
          </View>

          <View style={styles.rightPane}>
            <Text style={styles.paneTitle}>{tx('admin.gpsStateManagementPanel.auto.text.026', 'Editor')}</Text>
            {section === 'labels' ? (
              <>
                <TextInput style={styles.input} placeholder={tx('admin.gpsStateManagementPanel.auto.placeholder.004', 'Label key')} placeholderTextColor={colors.textMuted} value={labelKey} onChangeText={setLabelKey} data-testid="gps-label-key-input" testID="gps-label-key-input" />
                <TextInput style={[styles.input, { marginTop: 8 }]} placeholder={tx('admin.gpsStateManagementPanel.auto.placeholder.005', 'Label value')} placeholderTextColor={colors.textMuted} value={labelValue} onChangeText={setLabelValue} data-testid="gps-label-value-input" testID="gps-label-value-input" />
              </>
            ) : (
              <TextInput style={styles.editor} multiline value={editor} onChangeText={setEditor} data-testid="gps-json-editor" testID="gps-json-editor" />
            )}
            <TextInput style={[styles.input, { marginTop: 10 }]} value={reason} onChangeText={setReason} placeholder={tx('admin.gpsStateManagementPanel.auto.placeholder.006', 'Reason for change (audit trail)')} placeholderTextColor={colors.textMuted} data-testid="gps-change-reason-input" testID="gps-change-reason-input" />
            <View style={styles.actionRow}>
              <TouchableOpacity style={styles.primaryBtn} onPress={upsert} data-testid="gps-upsert-btn" testID="gps-upsert-btn" disabled={saving}>
                <Text style={styles.primaryBtnText}>{saving ? 'Saving…' : workflowMode === 'publish' ? 'Publish' : 'Create Request'}</Text>
              </TouchableOpacity>
              <TouchableOpacity style={styles.warnBtn} onPress={remove} data-testid="gps-delete-btn" testID="gps-delete-btn" disabled={saving}>
                <Text style={styles.warnBtnText}>{workflowMode === 'publish' ? 'Delete' : 'Request Delete'}</Text>
              </TouchableOpacity>
              <TouchableOpacity style={styles.secondaryBtn} onPress={refresh} data-testid="gps-refresh-btn" testID="gps-refresh-btn" disabled={saving}>
                <Text style={styles.secondaryBtnText}>{tx('admin.gpsStateManagementPanel.auto.text.027', 'Refresh')}</Text>
              </TouchableOpacity>
            </View>
          </View>
        </View>
      )}

      <Text style={styles.status} data-testid="gps-admin-status" testID="gps-admin-status">{status}</Text>
    </View>
  );
}

const createStyles = (C: any) =>
  StyleSheet.create({
    root: { flex: 1, padding: 16, gap: 12 },
    title: { fontSize: 20, fontWeight: '800', color: C.text },
    subtitle: { fontSize: 12, color: C.textMuted, lineHeight: 18 },
    policyBanner: { borderWidth: 1, borderColor: C.warning || C.primary, borderRadius: 10, paddingHorizontal: 12, paddingVertical: 10, backgroundColor: C.warningSoft || C.bgSoft },
    policyBannerText: { color: C.text, fontSize: 12, fontWeight: '800' },
    sectionRow: { gap: 8, paddingBottom: 2 },
    sectionChip: { borderWidth: 1, borderColor: C.border, borderRadius: 999, paddingHorizontal: 12, paddingVertical: 8, backgroundColor: C.card },
    sectionChipActive: { backgroundColor: C.primary, borderColor: C.primary },
    sectionChipText: { fontSize: 11, fontWeight: '700', color: C.textMuted },
    sectionChipTextActive: { color: C.primaryText },
    modeRow: { flexDirection: 'row', gap: 8, flexWrap: 'wrap' },
    modeChip: { borderWidth: 1, borderColor: C.border, borderRadius: 999, paddingHorizontal: 10, paddingVertical: 6, backgroundColor: C.card },
    modeChipActive: { backgroundColor: C.accent || C.primary, borderColor: C.accent || C.primary },
    modeChipText: { color: C.textMuted, fontSize: 10, fontWeight: '700' },
    modeChipTextActive: { color: C.primaryText },
    grid: { flexDirection: 'row', gap: 12, flexWrap: 'wrap' },
    leftPane: { flex: 1, minWidth: 300, borderWidth: 1, borderColor: C.border, borderRadius: 12, backgroundColor: C.card, padding: 12 },
    rightPane: { flex: 2, minWidth: 360, borderWidth: 1, borderColor: C.border, borderRadius: 12, backgroundColor: C.card, padding: 12 },
    paneTitle: { fontSize: 14, fontWeight: '800', color: C.text, marginBottom: 8 },
    itemRow: { borderWidth: 1, borderColor: C.border, borderRadius: 10, padding: 10, marginBottom: 8, backgroundColor: C.bgSoft },
    itemRowActive: { borderColor: C.primary, backgroundColor: `${C.primary}1A` },
    itemId: { color: C.text, fontSize: 12, fontWeight: '700' },
    itemMeta: { color: C.textMuted, marginTop: 2, fontSize: 11 },
    peerReviewBadge: { alignSelf: 'flex-start', marginTop: 8, borderRadius: 8, paddingHorizontal: 8, paddingVertical: 5, backgroundColor: C.warningSoft || 'var(--app-primary)', color: C.text, fontSize: 10, fontWeight: '900' },
    changeCard: { borderWidth: 1, borderColor: C.border, borderRadius: 10, padding: 10, marginBottom: 8, backgroundColor: C.bgSoft },
    input: { borderWidth: 1, borderColor: C.border, borderRadius: 10, paddingHorizontal: 10, paddingVertical: 10, color: C.text, backgroundColor: C.bgSoft, fontSize: 12 },
    editor: { borderWidth: 1, borderColor: C.border, borderRadius: 10, paddingHorizontal: 10, paddingVertical: 10, color: C.text, backgroundColor: C.bgSoft, fontSize: 11, minHeight: 220, textAlignVertical: 'top' as any },
    actionRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 10 },
    primaryBtn: { backgroundColor: C.primary, borderRadius: 10, paddingHorizontal: 12, paddingVertical: 10 },
    primaryBtnText: { color: C.primaryText, fontSize: 11, fontWeight: '800' },
    warnBtn: { backgroundColor: C.error || colors.error, borderRadius: 10, paddingHorizontal: 12, paddingVertical: 10 },
    warnBtnText: { color: C.primaryText, fontSize: 11, fontWeight: '800' },
    secondaryBtn: { borderWidth: 1, borderColor: C.border, backgroundColor: C.bgSoft, borderRadius: 10, paddingHorizontal: 12, paddingVertical: 10 },
    secondaryBtnText: { color: C.text, fontSize: 11, fontWeight: '700' },
    outboxCard: { borderWidth: 1, borderColor: C.border, borderRadius: 12, padding: 12, backgroundColor: C.card },
    outboxLine: { color: C.text, fontSize: 13, marginTop: 6 },
    monitorStrip: { flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', gap: 8, borderWidth: 1, borderColor: C.border, borderRadius: 12, backgroundColor: C.card, padding: 10 },
    monitorTitle: { color: C.text, fontSize: 11, fontWeight: '800' },
    badge: { borderRadius: 10, paddingHorizontal: 12, paddingVertical: 10, marginTop: 8 },
    goodBadge: { backgroundColor: C.successSoft || 'var(--app-primary)' },
    warnBadge: { backgroundColor: C.warningSoft || 'var(--app-primary)' },
    badgeText: { color: C.text, fontSize: 11, fontWeight: '900' },
    auditJson: { color: C.textMuted, fontSize: 10, marginTop: 6, lineHeight: 14 },
    status: { marginTop: 4, color: C.textMuted, fontSize: 12 },
    loadingWrap: { flexDirection: 'row', alignItems: 'center', gap: 8, padding: 18 },
    loadingText: { color: C.textMuted, fontSize: 13 },
  });
