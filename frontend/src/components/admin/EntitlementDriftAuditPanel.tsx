import React, { useEffect, useMemo, useState } from 'react';
import { ActivityIndicator, ScrollView, Text, TouchableOpacity, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useTranslation } from '../../hooks/useTranslation';
import { useLiveQuery } from '../../hooks/useLiveQuery';

type DriftFinding = {
  path?: string;
  line?: number;
  pattern?: string;
  severity?: string;
  snippet?: string;
};

type DriftRow = {
  generated_at?: string;
  trigger?: string;
  status?: string;
  severity?: string;
  title?: string;
  summary?: string;
  baseline_established?: boolean;
  raw_scan_status?: string;
  files_scanned?: number;
  finding_count?: number;
  high_risk_count?: number;
  medium_risk_count?: number;
  new_finding_count?: number;
  new_high_risk_count?: number;
  new_medium_risk_count?: number;
  baseline_previous_finding_count?: number;
  alert_dispatched?: boolean;
  preview_source?: string;
  preview_findings?: DriftFinding[];
};

type DriftPayload = {
  latest?: DriftRow | null;
  history?: DriftRow[];
  total?: number;
  status_breakdown?: { pass?: number; warning?: number; fail?: number };
  attention_count?: number;
};

const getStatusTone = (status: string | undefined, colors: any) => {
  if (status === 'fail') {
    return {
      color: colors.error,
      bg: `${colors.error}16`,
      icon: 'alert-circle',
    };
  }
  if (status === 'warning') {
    return {
      color: colors.warning,
      bg: `${colors.warning}16`,
      icon: 'warning',
    };
  }
  return {
    color: colors.successText || colors.success,
    bg: `${colors.successText || colors.success}16`,
    icon: 'checkmark-circle',
  };
};

const countLabel = (count: number, singular: string, plural?: string) => `${count} ${count === 1 ? singular : (plural || `${singular}s`)}`;
const getRowKey = (row: DriftRow, index: number) => `${row.generated_at || 'row'}-${row.trigger || 'unknown'}-${index}`;

export default function EntitlementDriftAuditPanel({ colors }: { colors: any }) {
  const { t } = useTranslation();
  const tx = React.useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);
  const { data, loading } = useLiveQuery<DriftPayload>('/admin/code-health/entitlement-drift/history?limit=7', {
    entity: 'code_health',
    pollInterval: 120000,
  });
  const [expandedRowKey, setExpandedRowKey] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<'all' | 'pass' | 'warning' | 'fail'>('all');
  const [triggerFilter, setTriggerFilter] = useState<string>('all');
  const [onlyNewFindings, setOnlyNewFindings] = useState(false);

  const rows = useMemo(() => data?.history || [], [data?.history]);
  const latest = data?.latest || null;
  const breakdown = data?.status_breakdown || {};
  const empty = !loading && rows.length === 0;
  const triggerOptions = useMemo(
    () => Array.from(new Set(rows.map((row) => row.trigger).filter(Boolean) as string[])),
    [rows],
  );
  const filteredRows = useMemo(() => (
    rows.filter((row) => {
      if (statusFilter !== 'all' && row.status !== statusFilter) return false;
      if (triggerFilter !== 'all' && row.trigger !== triggerFilter) return false;
      if (onlyNewFindings && (row.new_finding_count || 0) === 0) return false;
      return true;
    })
  ), [rows, statusFilter, triggerFilter, onlyNewFindings]);
  const noResults = !empty && filteredRows.length === 0;

  const latestTone = useMemo(() => getStatusTone(latest?.status, colors), [latest?.status, colors]);

  useEffect(() => {
    if (filteredRows.length === 0) {
      setExpandedRowKey(null);
      return;
    }
    const hasExpandedRow = filteredRows.some((row, index) => getRowKey(row, index) === expandedRowKey);
    if (!hasExpandedRow) {
      setExpandedRowKey(getRowKey(filteredRows[0], 0));
    }
  }, [filteredRows, expandedRowKey]);

  const clearFilters = () => {
    setStatusFilter('all');
    setTriggerFilter('all');
    setOnlyNewFindings(false);
  };

  if (loading) {
    return (
      <View style={{ padding: 28, alignItems: 'center', justifyContent: 'center' }} data-testid="entitlement-drift-panel-loading" testID="entitlement-drift-panel-loading">
        <ActivityIndicator size="small" color={colors.primary} />
        <Text style={{ color: colors.textMuted, fontSize: 12, marginTop: 10 }}>
          {tx('operationsConsole.entitlementDrift.loading', 'Loading entitlement drift history...')}
        </Text>
      </View>
    );
  }

  return (
    <ScrollView
      style={{ flex: 1 }}
      contentContainerStyle={{ padding: 16, gap: 14 }}
      data-testid="entitlement-drift-panel"
      testID="entitlement-drift-panel"
    >
      <View style={{ backgroundColor: colors.card, borderWidth: 1, borderColor: colors.border, borderRadius: 16, padding: 16, gap: 12 }}>
        <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12, flexWrap: 'wrap' }}>
          <View style={{ flex: 1, minWidth: 220 }}>
            <Text style={{ color: colors.text, fontSize: 20, fontWeight: '800' }} data-testid="entitlement-drift-panel-title" testID="entitlement-drift-panel-title">
              {tx('operationsConsole.entitlementDrift.title', 'Entitlement Drift Audit')}
            </Text>
            <Text style={{ color: colors.textMuted, fontSize: 12, marginTop: 4, lineHeight: 18 }} data-testid="entitlement-drift-panel-subtitle" testID="entitlement-drift-panel-subtitle">
              {tx('operationsConsole.entitlementDrift.subtitle', 'Daily history for risky raw plan reads, so the team can review findings without direct database access.')}
            </Text>
          </View>
          <View style={{ borderRadius: 999, paddingHorizontal: 10, paddingVertical: 6, backgroundColor: latestTone.bg }} data-testid="entitlement-drift-panel-status-pill" testID="entitlement-drift-panel-status-pill">
            <Text style={{ color: latestTone.color, fontSize: 10, fontWeight: '800', textTransform: 'uppercase' }} data-testid="entitlement-drift-panel-status-pill-text" testID="entitlement-drift-panel-status-pill-text">
              {latest?.status || 'unknown'}
            </Text>
          </View>
        </View>

        {latest ? (
          <View style={{ borderRadius: 14, borderWidth: 1, borderColor: latestTone.color, backgroundColor: latestTone.bg, padding: 14, gap: 8 }} data-testid="entitlement-drift-panel-latest-banner" testID="entitlement-drift-panel-latest-banner">
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
              <View style={{ width: 38, height: 38, borderRadius: 19, backgroundColor: `${latestTone.color}20`, alignItems: 'center', justifyContent: 'center' }}>
                <Ionicons name={latestTone.icon as any} size={20} color={latestTone.color} />
              </View>
              <View style={{ flex: 1 }}>
                <Text style={{ color: colors.text, fontSize: 14, fontWeight: '800' }} data-testid="entitlement-drift-panel-latest-title" testID="entitlement-drift-panel-latest-title">
                  {latest.title || 'Entitlement drift audit'}
                </Text>
                <Text style={{ color: colors.textMuted, fontSize: 11, marginTop: 2 }} data-testid="entitlement-drift-panel-latest-time" testID="entitlement-drift-panel-latest-time">
                  {latest.generated_at ? new Date(latest.generated_at).toLocaleString() : tx('operationsConsole.entitlementDrift.never', 'No completed runs yet')}
                </Text>
              </View>
            </View>
            <Text style={{ color: colors.text, fontSize: 12, lineHeight: 18 }} data-testid="entitlement-drift-panel-latest-summary" testID="entitlement-drift-panel-latest-summary">
              {latest.summary || tx('operationsConsole.entitlementDrift.noSummary', 'No summary available for this audit run.')}
            </Text>
            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
              {[
                { label: 'files scanned', value: latest.files_scanned || 0, color: colors.primary },
                { label: 'new findings', value: latest.new_finding_count || 0, color: latestTone.color },
                { label: 'high risk', value: latest.new_high_risk_count || 0, color: colors.error },
                { label: 'baseline previous', value: latest.baseline_previous_finding_count || 0, color: colors.textMuted },
              ].map((metric) => (
                <View key={metric.label} style={{ minWidth: 112, flexGrow: 1, borderRadius: 12, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, paddingHorizontal: 10, paddingVertical: 9 }} data-testid={`entitlement-drift-panel-metric-${metric.label.replace(/\s+/g, '-')}`} testID={`entitlement-drift-panel-metric-${metric.label.replace(/\s+/g, '-')}`}>
                  <Text style={{ color: colors.textMuted, fontSize: 10, fontWeight: '700', textTransform: 'uppercase' }}>{metric.label}</Text>
                  <Text style={{ color: metric.color, fontSize: 18, fontWeight: '800', marginTop: 5 }}>{metric.value}</Text>
                </View>
              ))}
            </View>
          </View>
        ) : null}

        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }} data-testid="entitlement-drift-panel-breakdown" testID="entitlement-drift-panel-breakdown">
          {[
            { key: 'pass', label: tx('operationsConsole.entitlementDrift.passRuns', 'Pass runs'), value: breakdown.pass || 0, color: colors.successText || colors.success },
            { key: 'warning', label: tx('operationsConsole.entitlementDrift.warningRuns', 'Warning runs'), value: breakdown.warning || 0, color: colors.warning },
            { key: 'fail', label: tx('operationsConsole.entitlementDrift.failRuns', 'Fail runs'), value: breakdown.fail || 0, color: colors.error },
            { key: 'attention', label: tx('operationsConsole.entitlementDrift.attention', 'Needs attention'), value: data?.attention_count || 0, color: colors.primary },
          ].map((item) => (
            <View key={item.key} style={{ flex: 1, minWidth: 140, borderRadius: 12, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bg, padding: 12 }} data-testid={`entitlement-drift-panel-breakdown-${item.key}`} testID={`entitlement-drift-panel-breakdown-${item.key}`}>
              <Text style={{ color: colors.textMuted, fontSize: 10, fontWeight: '700', textTransform: 'uppercase' }}>{item.label}</Text>
              <Text style={{ color: item.color, fontSize: 19, fontWeight: '900', marginTop: 6 }}>{item.value}</Text>
            </View>
          ))}
        </View>

        <View style={{ borderRadius: 14, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bg, padding: 12, gap: 10 }} data-testid="entitlement-drift-panel-filters" testID="entitlement-drift-panel-filters">
          <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 10, flexWrap: 'wrap' }}>
            <View>
              <Text style={{ color: colors.text, fontSize: 12, fontWeight: '800' }} data-testid="entitlement-drift-panel-filters-title" testID="entitlement-drift-panel-filters-title">
                {tx('operationsConsole.entitlementDrift.filtersTitle', 'Quick filters')}
              </Text>
              <Text style={{ color: colors.textMuted, fontSize: 10, marginTop: 3 }} data-testid="entitlement-drift-panel-filters-count" testID="entitlement-drift-panel-filters-count">
                {filteredRows.length} of {rows.length} runs visible
              </Text>
            </View>

            <TouchableOpacity
              onPress={clearFilters}
              style={{ borderRadius: 999, borderWidth: 1, borderColor: colors.border, paddingHorizontal: 10, paddingVertical: 6, backgroundColor: colors.card }}
              data-testid="entitlement-drift-panel-filters-reset-button"
              testID="entitlement-drift-panel-filters-reset-button"
            >
              <Text style={{ color: colors.text, fontSize: 10, fontWeight: '700' }}>
                {tx('operationsConsole.entitlementDrift.resetFilters', 'Reset filters')}
              </Text>
            </TouchableOpacity>
          </View>

          <View style={{ gap: 8 }}>
            <Text style={{ color: colors.textMuted, fontSize: 10, fontWeight: '700', textTransform: 'uppercase' }} data-testid="entitlement-drift-panel-status-filter-label" testID="entitlement-drift-panel-status-filter-label">
              {tx('operationsConsole.entitlementDrift.statusFilter', 'Status')}
            </Text>
            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
              {(['all', 'pass', 'warning', 'fail'] as const).map((statusOption) => {
                const selected = statusFilter === statusOption;
                return (
                  <TouchableOpacity
                    key={statusOption}
                    onPress={() => setStatusFilter(statusOption)}
                    style={{
                      borderRadius: 999,
                      paddingHorizontal: 10,
                      paddingVertical: 7,
                      borderWidth: 1,
                      borderColor: selected ? colors.primary : colors.border,
                      backgroundColor: selected ? `${colors.primary}16` : colors.card,
                    }}
                    data-testid={`entitlement-drift-panel-status-filter-${statusOption}`}
                    testID={`entitlement-drift-panel-status-filter-${statusOption}`}
                  >
                    <Text style={{ color: selected ? colors.primary : colors.text, fontSize: 10, fontWeight: '700', textTransform: 'capitalize' }}>
                      {statusOption}
                    </Text>
                  </TouchableOpacity>
                );
              })}
            </View>
          </View>

          <View style={{ gap: 8 }}>
            <Text style={{ color: colors.textMuted, fontSize: 10, fontWeight: '700', textTransform: 'uppercase' }} data-testid="entitlement-drift-panel-trigger-filter-label" testID="entitlement-drift-panel-trigger-filter-label">
              {tx('operationsConsole.entitlementDrift.triggerFilter', 'Trigger')}
            </Text>
            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
              {['all', ...triggerOptions].map((triggerOption) => {
                const selected = triggerFilter === triggerOption;
                return (
                  <TouchableOpacity
                    key={triggerOption}
                    onPress={() => setTriggerFilter(triggerOption)}
                    style={{
                      borderRadius: 999,
                      paddingHorizontal: 10,
                      paddingVertical: 7,
                      borderWidth: 1,
                      borderColor: selected ? colors.primary : colors.border,
                      backgroundColor: selected ? `${colors.primary}16` : colors.card,
                    }}
                    data-testid={`entitlement-drift-panel-trigger-filter-${triggerOption}`}
                    testID={`entitlement-drift-panel-trigger-filter-${triggerOption}`}
                  >
                    <Text style={{ color: selected ? colors.primary : colors.text, fontSize: 10, fontWeight: '700', textTransform: 'capitalize' }}>
                      {triggerOption.replace(/_/g, ' ')}
                    </Text>
                  </TouchableOpacity>
                );
              })}
            </View>
          </View>

          <TouchableOpacity
            onPress={() => setOnlyNewFindings((current) => !current)}
            style={{
              borderRadius: 12,
              borderWidth: 1,
              borderColor: onlyNewFindings ? colors.primary : colors.border,
              backgroundColor: onlyNewFindings ? `${colors.primary}16` : colors.card,
              padding: 12,
              flexDirection: 'row',
              alignItems: 'center',
              justifyContent: 'space-between',
              gap: 10,
            }}
            data-testid="entitlement-drift-panel-new-findings-toggle"
            testID="entitlement-drift-panel-new-findings-toggle"
          >
            <View style={{ flex: 1 }}>
              <Text style={{ color: onlyNewFindings ? colors.primary : colors.text, fontSize: 11, fontWeight: '800' }} data-testid="entitlement-drift-panel-new-findings-toggle-title" testID="entitlement-drift-panel-new-findings-toggle-title">
                {tx('operationsConsole.entitlementDrift.onlyNewFindings', 'Only runs with new findings')}
              </Text>
              <Text style={{ color: colors.textMuted, fontSize: 10, marginTop: 4 }} data-testid="entitlement-drift-panel-new-findings-toggle-caption" testID="entitlement-drift-panel-new-findings-toggle-caption">
                {tx('operationsConsole.entitlementDrift.onlyNewFindingsCaption', 'Hide clean runs and baseline-only snapshots when triaging active drift.')}
              </Text>
            </View>
            <Ionicons name={onlyNewFindings ? 'checkbox' : 'square-outline'} size={18} color={onlyNewFindings ? colors.primary : colors.textMuted} />
          </TouchableOpacity>
        </View>
      </View>

      {empty ? (
        <View style={{ borderRadius: 14, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, padding: 24, alignItems: 'center' }} data-testid="entitlement-drift-panel-empty" testID="entitlement-drift-panel-empty">
          <Ionicons name="timer-outline" size={26} color={colors.textMuted} />
          <Text style={{ color: colors.text, fontSize: 14, fontWeight: '700', marginTop: 10 }}>
            {tx('operationsConsole.entitlementDrift.emptyTitle', 'No audit history yet')}
          </Text>
          <Text style={{ color: colors.textMuted, fontSize: 12, textAlign: 'center', marginTop: 6, lineHeight: 18 }}>
            {tx('operationsConsole.entitlementDrift.emptyBody', 'The scheduled job will populate this list after the next daily run.')}
          </Text>
        </View>
      ) : null}

      {noResults ? (
        <View style={{ borderRadius: 14, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, padding: 24, alignItems: 'center' }} data-testid="entitlement-drift-panel-no-results" testID="entitlement-drift-panel-no-results">
          <Ionicons name="funnel-outline" size={24} color={colors.textMuted} />
          <Text style={{ color: colors.text, fontSize: 14, fontWeight: '700', marginTop: 10 }} data-testid="entitlement-drift-panel-no-results-title" testID="entitlement-drift-panel-no-results-title">
            {tx('operationsConsole.entitlementDrift.noResultsTitle', 'No runs match these filters')}
          </Text>
          <Text style={{ color: colors.textMuted, fontSize: 12, textAlign: 'center', marginTop: 6, lineHeight: 18 }} data-testid="entitlement-drift-panel-no-results-body" testID="entitlement-drift-panel-no-results-body">
            {tx('operationsConsole.entitlementDrift.noResultsBody', 'Try another status or trigger, or turn off the new-findings filter.')}
          </Text>
        </View>
      ) : null}

      {filteredRows.map((row, index) => {
        const tone = getStatusTone(row.status, colors);
        const rowKey = getRowKey(row, index);
        const expanded = expandedRowKey === rowKey;
        const findings = row.preview_findings || [];
        return (
          <View key={rowKey} style={{ borderRadius: 14, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, overflow: 'hidden' }} data-testid={`entitlement-drift-history-row-${index}`} testID={`entitlement-drift-history-row-${index}`}>
            <TouchableOpacity
              onPress={() => setExpandedRowKey(expanded ? null : rowKey)}
              style={{ padding: 14, gap: 10 }}
              data-testid={`entitlement-drift-history-row-toggle-${index}`}
              testID={`entitlement-drift-history-row-toggle-${index}`}
            >
              <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 10, flexWrap: 'wrap' }}>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, flex: 1, minWidth: 220 }}>
                  <View style={{ width: 34, height: 34, borderRadius: 17, backgroundColor: tone.bg, alignItems: 'center', justifyContent: 'center' }}>
                    <Ionicons name={tone.icon as any} size={18} color={tone.color} />
                  </View>
                  <View style={{ flex: 1 }}>
                    <Text style={{ color: colors.text, fontSize: 13, fontWeight: '800' }} data-testid={`entitlement-drift-history-row-title-${index}`} testID={`entitlement-drift-history-row-title-${index}`}>
                      {row.title || 'Entitlement drift audit'}
                    </Text>
                    <Text style={{ color: colors.textMuted, fontSize: 10, marginTop: 3 }} data-testid={`entitlement-drift-history-row-time-${index}`} testID={`entitlement-drift-history-row-time-${index}`}>
                      {(row.trigger || 'manual').replace(/_/g, ' ')} · {row.generated_at ? new Date(row.generated_at).toLocaleString() : tx('operationsConsole.entitlementDrift.unknownTime', 'Unknown time')}
                    </Text>
                  </View>
                </View>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                  <View style={{ borderRadius: 999, backgroundColor: tone.bg, paddingHorizontal: 8, paddingVertical: 4 }} data-testid={`entitlement-drift-history-row-status-${index}`} testID={`entitlement-drift-history-row-status-${index}`}>
                    <Text style={{ color: tone.color, fontSize: 10, fontWeight: '800', textTransform: 'uppercase' }}>{row.status || 'unknown'}</Text>
                  </View>
                  <Ionicons name={expanded ? 'chevron-up' : 'chevron-down'} size={16} color={colors.textMuted} />
                </View>
              </View>

              <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
                {[
                  { id: 'new-findings', label: 'new findings', value: row.new_finding_count || 0, color: tone.color },
                  { id: 'high-risk', label: 'high risk', value: row.high_risk_count || 0, color: colors.error },
                  { id: 'medium-risk', label: 'medium risk', value: row.medium_risk_count || 0, color: colors.warning },
                  { id: 'files-scanned', label: 'files scanned', value: row.files_scanned || 0, color: colors.primary },
                ].map((chip) => (
                  <View key={chip.id} style={{ borderRadius: 999, paddingHorizontal: 9, paddingVertical: 5, backgroundColor: colors.bg, borderWidth: 1, borderColor: colors.border }} data-testid={`entitlement-drift-history-row-chip-${chip.id}-${index}`} testID={`entitlement-drift-history-row-chip-${chip.id}-${index}`}>
                    <Text style={{ color: colors.textMuted, fontSize: 10 }}>
                      <Text style={{ color: chip.color, fontWeight: '800' }}>{chip.value}</Text> {chip.label}
                    </Text>
                  </View>
                ))}
              </View>
            </TouchableOpacity>

            {expanded ? (
              <View style={{ borderTopWidth: 1, borderTopColor: colors.border, padding: 14, gap: 12, backgroundColor: colors.bg }} data-testid={`entitlement-drift-history-row-details-${index}`} testID={`entitlement-drift-history-row-details-${index}`}>
                <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10 }}>
                  <View style={{ flex: 1, minWidth: 220, borderRadius: 12, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, padding: 12 }} data-testid={`entitlement-drift-history-row-summary-${index}`} testID={`entitlement-drift-history-row-summary-${index}`}>
                    <Text style={{ color: colors.text, fontSize: 12, fontWeight: '800' }}>{tx('operationsConsole.entitlementDrift.summaryLabel', 'Run summary')}</Text>
                    <Text style={{ color: colors.textMuted, fontSize: 11, lineHeight: 18, marginTop: 6 }}>
                      {row.summary || tx('operationsConsole.entitlementDrift.noSummary', 'No summary available for this audit run.')}
                    </Text>
                    <Text style={{ color: colors.textMuted, fontSize: 10, marginTop: 8 }}>
                      {row.baseline_established
                        ? tx('operationsConsole.entitlementDrift.baselineNote', 'This run established or preserved the current baseline for future comparisons.')
                        : `${countLabel(row.baseline_previous_finding_count || 0, 'baseline finding')} compared against prior history.`}
                    </Text>
                  </View>
                  <View style={{ flex: 1, minWidth: 220, borderRadius: 12, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, padding: 12 }} data-testid={`entitlement-drift-history-row-meta-${index}`} testID={`entitlement-drift-history-row-meta-${index}`}>
                    <Text style={{ color: colors.text, fontSize: 12, fontWeight: '800' }}>{tx('operationsConsole.entitlementDrift.runMetaLabel', 'Run metadata')}</Text>
                    {[
                      `Raw scan status: ${(row.raw_scan_status || 'unknown').toUpperCase()}`,
                      `Alert dispatched: ${row.alert_dispatched ? 'Yes' : 'No'}`,
                      `Preview source: ${(row.preview_source || 'findings').replace(/_/g, ' ')}`,
                      `New high / medium: ${row.new_high_risk_count || 0} / ${row.new_medium_risk_count || 0}`,
                    ].map((line, metaIndex) => (
                      <Text key={`${line}-${metaIndex}`} style={{ color: colors.textMuted, fontSize: 11, marginTop: metaIndex === 0 ? 8 : 6 }} data-testid={`entitlement-drift-history-row-meta-line-${index}-${metaIndex}`} testID={`entitlement-drift-history-row-meta-line-${index}-${metaIndex}`}>
                        {line}
                      </Text>
                    ))}
                  </View>
                </View>

                <View style={{ borderRadius: 12, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, padding: 12, gap: 10 }} data-testid={`entitlement-drift-history-row-findings-${index}`} testID={`entitlement-drift-history-row-findings-${index}`}>
                  <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 10, flexWrap: 'wrap' }}>
                    <Text style={{ color: colors.text, fontSize: 12, fontWeight: '800' }}>
                      {tx('operationsConsole.entitlementDrift.findingsPreview', 'Finding preview')}
                    </Text>
                    <Text style={{ color: colors.textMuted, fontSize: 10 }} data-testid={`entitlement-drift-history-row-findings-count-${index}`} testID={`entitlement-drift-history-row-findings-count-${index}`}>
                      {countLabel(findings.length, 'preview item')}
                    </Text>
                  </View>

                  {findings.length === 0 ? (
                    <Text style={{ color: colors.textMuted, fontSize: 11 }} data-testid={`entitlement-drift-history-row-findings-empty-${index}`} testID={`entitlement-drift-history-row-findings-empty-${index}`}>
                      {tx('operationsConsole.entitlementDrift.findingsEmpty', 'No preview findings were stored for this run.')}
                    </Text>
                  ) : (
                    findings.map((finding, findingIndex) => {
                      const findingColor = finding.severity === 'high' ? colors.error : colors.warning;
                      return (
                        <View key={`${finding.path || 'path'}-${finding.line || 0}-${findingIndex}`} style={{ borderRadius: 10, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bg, padding: 10 }} data-testid={`entitlement-drift-history-row-finding-${index}-${findingIndex}`} testID={`entitlement-drift-history-row-finding-${index}-${findingIndex}`}>
                          <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 10, flexWrap: 'wrap' }}>
                            <Text style={{ color: colors.text, fontSize: 11, fontWeight: '800', flex: 1 }} data-testid={`entitlement-drift-history-row-finding-path-${index}-${findingIndex}`} testID={`entitlement-drift-history-row-finding-path-${index}-${findingIndex}`}>
                              {finding.path || 'Unknown file'}
                            </Text>
                            <View style={{ borderRadius: 999, paddingHorizontal: 8, paddingVertical: 3, backgroundColor: `${findingColor}18` }} data-testid={`entitlement-drift-history-row-finding-severity-${index}-${findingIndex}`} testID={`entitlement-drift-history-row-finding-severity-${index}-${findingIndex}`}>
                              <Text style={{ color: findingColor, fontSize: 9, fontWeight: '800', textTransform: 'uppercase' }}>{finding.severity || 'medium'}</Text>
                            </View>
                          </View>
                          <Text style={{ color: colors.textMuted, fontSize: 10, marginTop: 5 }} data-testid={`entitlement-drift-history-row-finding-meta-${index}-${findingIndex}`} testID={`entitlement-drift-history-row-finding-meta-${index}-${findingIndex}`}>
                            line {finding.line || 0} · {finding.pattern || 'unknown pattern'}
                          </Text>
                          {finding.snippet ? (
                            <Text style={{ color: colors.text, fontSize: 11, marginTop: 6, lineHeight: 17 }} data-testid={`entitlement-drift-history-row-finding-snippet-${index}-${findingIndex}`} testID={`entitlement-drift-history-row-finding-snippet-${index}-${findingIndex}`}>
                              {finding.snippet}
                            </Text>
                          ) : null}
                        </View>
                      );
                    })
                  )}
                </View>
              </View>
            ) : null}
          </View>
        );
      })}
    </ScrollView>
  );
}