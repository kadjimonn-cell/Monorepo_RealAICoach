import React, { useEffect, useState } from 'react';
import { View, Text, ActivityIndicator, TouchableOpacity } from 'react-native';
import api from '../../services/api';
import { BillingSectionCard, BillingActionButton } from '../paymentHistory/BillingRoutePrimitives';

type JobDoc = {
  job_id: string;
  job_title: string;
  cv_markdown: string;
  ats_report: null | {
    ats_score: number;
    covered_keywords: string[];
    missing_keywords: string[];
    parseability: { score: number; issues: string[] };
    recommendations: string[];
  };
};

type Props = {
  colors: any;
  tx: (key: string, fallback: string) => string;
  refreshSignal: number;
};

export const AtsCheckTab = ({ colors, tx, refreshSignal }: Props) => {
  const [docs, setDocs] = useState<JobDoc[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeJobId, setActiveJobId] = useState('');
  const [running, setRunning] = useState(false);
  const [errorMsg, setErrorMsg] = useState('');

  useEffect(() => {
    let mounted = true;
    (async () => {
      try {
        const resp = await api.get('/job-search/documents', { silentLoading: true });
        if (mounted) {
          const list: JobDoc[] = resp?.data?.documents || [];
          setDocs(list);
          if (list.length > 0) setActiveJobId(list[0].job_id);
        }
      } catch {
        // empty state shown
      } finally {
        if (mounted) setLoading(false);
      }
    })();
    return () => { mounted = false; };
  }, [refreshSignal]);

  const runAts = async () => {
    if (!activeJobId) return;
    setRunning(true);
    setErrorMsg('');
    try {
      const resp = await api.post('/job-search/ats-check', { job_id: activeJobId }, { timeout: 120000 });
      const report = resp?.data?.ats_report;
      if (report) setDocs((prev) => prev.map((d) => (d.job_id === activeJobId ? { ...d, ats_report: report } : d)));
    } catch {
      setErrorMsg(tx('jobSearch.docs.atsFailed', 'ATS validation is unavailable right now. Please retry.'));
    } finally {
      setRunning(false);
    }
  };

  const activeDoc = docs.find((d) => d.job_id === activeJobId) || null;
  const report = activeDoc?.ats_report || null;
  const scoreColor = (score: number) => (score >= 75 ? colors.successText : score >= 50 ? colors.warningText : colors.error);

  return (
    <View style={{ gap: 14 }}>
      <BillingSectionCard colors={colors} testId="job-search-ats-header">
        <Text style={{ color: colors.text, fontSize: 17, fontWeight: '800' }}>{tx('jobSearch.ats.title', 'ATS validation')}</Text>
        <Text style={{ color: colors.textSecondary, fontSize: 12, lineHeight: 18, marginTop: 4 }}>
          {tx('jobSearch.ats.subtitle', 'Check keyword coverage and parseability of your tailored CV against the job posting — the way an applicant tracking system reads it.')}
        </Text>
      </BillingSectionCard>

      {loading ? (
        <BillingSectionCard colors={colors} testId="job-search-ats-loading"><ActivityIndicator color={colors.primary} /></BillingSectionCard>
      ) : docs.length === 0 ? (
        <BillingSectionCard colors={colors} testId="job-search-ats-empty">
          <Text style={{ color: colors.textSecondary, fontSize: 13 }}>{tx('jobSearch.ats.empty', 'No application kits yet. Generate a CV in the Documents tab first.')}</Text>
        </BillingSectionCard>
      ) : (
        <BillingSectionCard colors={colors} testId="job-search-ats-panel">
          <View style={{ flexDirection: 'row', gap: 8, flexWrap: 'wrap' }}>
            {docs.map((doc, idx) => (
              <TouchableOpacity
                key={doc.job_id}
                onPress={() => setActiveJobId(doc.job_id)}
                style={{ backgroundColor: doc.job_id === activeJobId ? colors.primary : colors.background, borderWidth: 1, borderColor: doc.job_id === activeJobId ? colors.primary : colors.border, borderRadius: 999, paddingHorizontal: 14, paddingVertical: 8 }}
                data-testid={`job-search-ats-chip-${idx}`}
                testID={`job-search-ats-chip-${idx}`}
                accessibilityRole="button"
                accessibilityLabel={doc.job_title}
              >
                <Text style={{ color: doc.job_id === activeJobId ? colors.primaryText : colors.text, fontSize: 12, fontWeight: '700' }}>{doc.job_title}</Text>
              </TouchableOpacity>
            ))}
          </View>
          <View style={{ marginTop: 12, flexDirection: 'row', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
            <BillingActionButton
              label={running ? tx('jobSearch.docs.atsRunning', 'Validating…') : tx('jobSearch.docs.runAts', 'Run ATS check')}
              onPress={runAts}
              icon="shield-checkmark-outline"
              colors={colors}
              testId="job-search-ats-btn"
              disabled={running}
            />
            {errorMsg ? <Text style={{ color: colors.error, fontSize: 12, flex: 1 }} data-testid="job-search-ats-error" testID="job-search-ats-error">{errorMsg}</Text> : null}
          </View>

          {report ? (
            <View style={{ marginTop: 14, borderTopWidth: 1, borderTopColor: colors.border, paddingTop: 12, gap: 10 }} data-testid="job-search-ats-report" testID="job-search-ats-report">
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
                <Text style={{ color: colors.text, fontSize: 14, fontWeight: '800' }}>{tx('jobSearch.docs.atsReport', 'ATS validation report')}</Text>
                <Text style={{ color: scoreColor(report.ats_score), fontSize: 22, fontWeight: '900' }} data-testid="job-search-ats-score" testID="job-search-ats-score">
                  {Math.round(report.ats_score)}/100
                </Text>
              </View>
              <View style={{ flexDirection: 'row', gap: 12, flexWrap: 'wrap' }}>
                <View style={{ flex: 1, minWidth: 200 }}>
                  <Text style={{ color: colors.successText, fontSize: 11, fontWeight: '800', textTransform: 'uppercase', marginBottom: 4 }}>{tx('jobSearch.docs.coveredKeywords', 'Covered keywords')}</Text>
                  <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6 }}>
                    {(report.covered_keywords || []).map((kw, kIdx) => (
                      <View key={kIdx} style={{ backgroundColor: colors.successSoft, borderRadius: 999, paddingHorizontal: 10, paddingVertical: 4 }}>
                        <Text style={{ color: colors.successText, fontSize: 11, fontWeight: '700' }}>{kw}</Text>
                      </View>
                    ))}
                  </View>
                </View>
                <View style={{ flex: 1, minWidth: 200 }}>
                  <Text style={{ color: colors.warningText, fontSize: 11, fontWeight: '800', textTransform: 'uppercase', marginBottom: 4 }}>{tx('jobSearch.docs.missingKeywords', 'Missing keywords')}</Text>
                  <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6 }}>
                    {(report.missing_keywords || []).map((kw, kIdx) => (
                      <View key={kIdx} style={{ backgroundColor: colors.warningSoft, borderRadius: 999, paddingHorizontal: 10, paddingVertical: 4 }}>
                        <Text style={{ color: colors.warningText, fontSize: 11, fontWeight: '700' }}>{kw}</Text>
                      </View>
                    ))}
                  </View>
                </View>
              </View>
              {(report.recommendations || []).length > 0 ? (
                <View>
                  <Text style={{ color: colors.textSecondary, fontSize: 11, fontWeight: '800', textTransform: 'uppercase', marginBottom: 4 }}>{tx('jobSearch.docs.atsRecommendations', 'Recommendations')}</Text>
                  {report.recommendations.map((rec, rIdx) => (
                    <Text key={rIdx} style={{ color: colors.textSecondary, fontSize: 12, lineHeight: 18 }}>• {rec}</Text>
                  ))}
                </View>
              ) : null}
            </View>
          ) : (
            <Text style={{ color: colors.textSecondary, fontSize: 12, marginTop: 12 }} data-testid="job-search-ats-no-report" testID="job-search-ats-no-report">
              {tx('jobSearch.ats.noReport', 'No report yet for this kit — run the check above.')}
            </Text>
          )}
        </BillingSectionCard>
      )}
    </View>
  );
};
