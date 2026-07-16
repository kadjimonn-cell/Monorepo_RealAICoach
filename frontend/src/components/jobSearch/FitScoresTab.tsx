import React, { useCallback, useEffect, useState } from 'react';
import { View, Text, ActivityIndicator, TouchableOpacity } from 'react-native';
import api from '../../services/api';
import { BillingSectionCard, BillingActionButton } from '../paymentHistory/BillingRoutePrimitives';

type Match = {
  job_id: string;
  job_title: string;
  overall_score: number;
  recommendation: string;
  dimensions: { key: string; label: string; score: number; note: string }[];
  strengths: string[];
  gaps: string[];
  summary: string;
  created_at: string;
};

type Props = {
  colors: any;
  tx: (key: string, fallback: string) => string;
  refreshSignal: number;
  onGenerateKit: (jobId: string, jobTitle: string) => void;
};

export const FitScoresTab = ({ colors, tx, refreshSignal, onGenerateKit }: Props) => {
  const [matches, setMatches] = useState<Match[]>([]);
  const [loading, setLoading] = useState(true);
  const [expandedJobId, setExpandedJobId] = useState('');

  useEffect(() => {
    let mounted = true;
    (async () => {
      try {
        const resp = await api.get('/job-search/matches', { silentLoading: true });
        if (mounted) {
          const list: Match[] = resp?.data?.matches || [];
          list.sort((a, b) => (b.overall_score || 0) - (a.overall_score || 0));
          setMatches(list);
          if (list.length > 0) setExpandedJobId(list[0].job_id);
        }
      } catch {
        // shown as empty state; user can rerun scores from Find Jobs
      } finally {
        if (mounted) setLoading(false);
      }
    })();
    return () => { mounted = false; };
  }, [refreshSignal]);

  const scoreColor = (score: number) => (score >= 75 ? colors.successText : score >= 50 ? colors.warningText : colors.error);

  const recommendationLabel = (rec: string) => {
    if (rec === 'strong_apply') return tx('jobSearch.jobs.rec.strongApply', 'Strong apply');
    if (rec === 'apply') return tx('jobSearch.jobs.rec.apply', 'Apply');
    if (rec === 'stretch') return tx('jobSearch.jobs.rec.stretch', 'Stretch');
    return tx('jobSearch.jobs.rec.skip', 'Skip');
  };

  return (
    <View style={{ gap: 14 }}>
      <BillingSectionCard colors={colors} testId="job-search-fit-scores-header">
        <Text style={{ color: colors.text, fontSize: 17, fontWeight: '800' }}>{tx('jobSearch.fitScores.title', 'Fit scores & ranking')}</Text>
        <Text style={{ color: colors.textSecondary, fontSize: 12, lineHeight: 18, marginTop: 4 }}>
          {tx('jobSearch.fitScores.subtitle', 'Every job you evaluated, ranked by honest 5-dimension fit. Run new scores from the Find Jobs tab.')}
        </Text>
      </BillingSectionCard>

      {loading ? (
        <BillingSectionCard colors={colors} testId="job-search-fit-scores-loading"><ActivityIndicator color={colors.primary} /></BillingSectionCard>
      ) : matches.length === 0 ? (
        <BillingSectionCard colors={colors} testId="job-search-fit-scores-empty">
          <Text style={{ color: colors.textSecondary, fontSize: 13 }}>{tx('jobSearch.fitScores.empty', 'No fit scores yet. Evaluate a job from the Find Jobs tab.')}</Text>
        </BillingSectionCard>
      ) : (
        matches.map((match, idx) => {
          const expanded = expandedJobId === match.job_id;
          return (
            <BillingSectionCard key={match.job_id} colors={colors} testId={`job-search-fit-card-${idx}`}>
              <TouchableOpacity
                onPress={() => setExpandedJobId(expanded ? '' : match.job_id)}
                style={{ flexDirection: 'row', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}
                data-testid={`job-search-fit-toggle-${idx}`}
                testID={`job-search-fit-toggle-${idx}`}
                accessibilityRole="button"
                accessibilityLabel={match.job_title}
              >
                <Text style={{ color: scoreColor(match.overall_score), fontSize: 26, fontWeight: '900', minWidth: 48 }}>{Math.round(match.overall_score)}</Text>
                <View style={{ flex: 1, minWidth: 180 }}>
                  <Text style={{ color: colors.text, fontSize: 14.5, fontWeight: '800' }}>{match.job_title}</Text>
                  <Text style={{ color: colors.textSecondary, fontSize: 11, fontWeight: '800', textTransform: 'uppercase', marginTop: 2 }}>{recommendationLabel(match.recommendation)}</Text>
                </View>
                <BillingActionButton label={tx('jobSearch.jobs.generateKit', 'Generate kit')} onPress={() => onGenerateKit(match.job_id, match.job_title)} icon="document-text-outline" colors={colors} variant="secondary" testId={`job-search-fit-generate-${idx}`} />
              </TouchableOpacity>

              {expanded ? (
                <View style={{ marginTop: 14, borderTopWidth: 1, borderTopColor: colors.border, paddingTop: 12, gap: 10 }} data-testid={`job-search-fit-detail-${idx}`} testID={`job-search-fit-detail-${idx}`}>
                  <Text style={{ color: colors.textSecondary, fontSize: 12, lineHeight: 18 }}>{match.summary}</Text>
                  <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
                    {(match.dimensions || []).map((dim, dIdx) => (
                      <View key={dIdx} style={{ backgroundColor: colors.background, borderWidth: 1, borderColor: colors.border, borderRadius: 12, padding: 10, minWidth: 140, flex: 1 }}>
                        <Text style={{ color: colors.textSecondary, fontSize: 10, fontWeight: '800', textTransform: 'uppercase' }}>{dim.label}</Text>
                        <Text style={{ color: scoreColor(dim.score), fontSize: 18, fontWeight: '900', marginTop: 2 }}>{Math.round(dim.score)}</Text>
                        <Text style={{ color: colors.textSecondary, fontSize: 11, lineHeight: 15, marginTop: 4 }}>{dim.note}</Text>
                      </View>
                    ))}
                  </View>
                  {(match.strengths || []).length > 0 ? (
                    <View>
                      <Text style={{ color: colors.successText, fontSize: 11, fontWeight: '800', textTransform: 'uppercase', marginBottom: 4 }}>{tx('jobSearch.jobs.strengths', 'Strengths')}</Text>
                      {match.strengths.map((item, sIdx) => (
                        <Text key={sIdx} style={{ color: colors.textSecondary, fontSize: 12, lineHeight: 18 }}>• {item}</Text>
                      ))}
                    </View>
                  ) : null}
                  {(match.gaps || []).length > 0 ? (
                    <View>
                      <Text style={{ color: colors.warningText, fontSize: 11, fontWeight: '800', textTransform: 'uppercase', marginBottom: 4 }}>{tx('jobSearch.jobs.gaps', 'Honest gaps')}</Text>
                      {match.gaps.map((item, gIdx) => (
                        <Text key={gIdx} style={{ color: colors.textSecondary, fontSize: 12, lineHeight: 18 }}>• {item}</Text>
                      ))}
                    </View>
                  ) : null}
                </View>
              ) : null}
            </BillingSectionCard>
          );
        })
      )}
    </View>
  );
};
