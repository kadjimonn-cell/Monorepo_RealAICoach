import React, { useEffect, useState, useCallback } from 'react';
import { View, Text, TouchableOpacity, ActivityIndicator, StyleSheet } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';

type Props = { C: any; isCompact: boolean };

const HEALTH_ICON: Record<string, string> = { healthy: 'heart', degraded: 'warning', idle: 'moon' };

export const AgentPortfolioTab: React.FC<Props> = ({ C, isCompact }) => {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [portfolio, setPortfolio] = useState<any>(null);
  const [coverage, setCoverage] = useState<any>(null);
  const [categories, setCategories] = useState<any[]>([]);
  const [readiness, setReadiness] = useState<any>(null);
  const [showAllFeatures, setShowAllFeatures] = useState(false);

  const load = useCallback(async () => {
    try {
      setError(null);
      const [p, cov, cats, rdy] = await Promise.all([
        api.get('/agent-framework/marketplace/portfolio'),
        api.get('/agent-framework/marketplace/coverage'),
        api.get('/agent-framework/marketplace/categories'),
        api.get('/agent-framework/marketplace/readiness'),
      ]);
      setPortfolio(p.data);
      setCoverage(cov.data);
      setCategories(cats.data?.categories || []);
      setReadiness(rdy.data);
    } catch (err: any) {
      setError(err?.response?.data?.detail || err?.message || 'Failed to load portfolio');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const s = makeStyles(C, isCompact);

  if (loading) {
    return (
      <View style={s.center} testID="portfolio-loading">
        <ActivityIndicator size="large" color={C.primary} />
      </View>
    );
  }
  if (error) {
    return (
      <View style={s.errorBox}>
        <Text style={{ color: C.errorText }} testID="portfolio-error">{error}</Text>
      </View>
    );
  }

  const st = portfolio?.by_status || {};
  const health = portfolio?.by_health || {};
  const avail = portfolio?.by_availability || {};
  const featureRows = showAllFeatures ? (coverage?.matrix || []) : (coverage?.matrix || []).slice(0, 12);

  return (
    <View testID="agent-portfolio-tab">
      {/* Overview stat cards */}
      <View style={s.statsRow} testID="portfolio-stats">
        {[
          { label: 'Total Agents', value: portfolio?.agents_total, icon: 'people' },
          { label: 'Categories', value: portfolio?.categories_total, icon: 'grid' },
          { label: 'Active', value: st.active, icon: 'checkmark-circle' },
          { label: 'Beta', value: st.beta, icon: 'flask' },
          { label: 'Experimental', value: st.experimental, icon: 'bulb' },
          { label: 'Disabled', value: st.disabled, icon: 'pause-circle' },
          { label: 'Coverage', value: `${portfolio?.coverage?.coverage_percent ?? 0}%`, icon: 'shield-checkmark' },
          { label: 'Avg Quality', value: portfolio?.avg_quality_score, icon: 'star' },
        ].map((card) => (
          <View key={card.label} style={s.statCard} testID={`portfolio-stat-${card.label.toLowerCase().replace(/\s+/g, '-')}`}>
            <Ionicons name={card.icon as any} size={16} color={C.primary} />
            <Text style={s.statValue}>{card.value ?? '—'}</Text>
            <Text style={s.statLabel}>{card.label}</Text>
          </View>
        ))}
      </View>

      {/* Health + availability */}
      <View style={s.rowWrap}>
        <View style={s.panel} testID="portfolio-health-panel">
          <Text style={s.panelTitle}>Fleet Health</Text>
          {(['healthy', 'degraded', 'idle'] as const).map((h) => (
            <View key={h} style={s.lineRow}>
              <Ionicons name={HEALTH_ICON[h] as any} size={14} color={h === 'degraded' ? C.warningText : C.primary} />
              <Text style={s.lineLabel}>{h}</Text>
              <Text style={s.lineValue} testID={`portfolio-health-${h}`}>{health[h] || 0}</Text>
            </View>
          ))}
          <Text style={[s.lineLabel, { marginTop: 8 }]}>Total executions: {portfolio?.executions_total ?? 0}</Text>
        </View>
        <View style={s.panel} testID="portfolio-availability-panel">
          <Text style={s.panelTitle}>Availability</Text>
          {Object.entries(avail).map(([k, v]) => (
            <View key={k} style={s.lineRow}>
              <Ionicons name="globe-outline" size={14} color={C.primary} />
              <Text style={s.lineLabel}>{k}</Text>
              <Text style={s.lineValue}>{v as number}</Text>
            </View>
          ))}
        </View>
      </View>

      {/* Marketplace readiness */}
      <View style={s.panel} testID="portfolio-readiness-panel">
        <View style={s.panelHeader}>
          <Text style={s.panelTitle}>Marketplace Readiness</Text>
          <View style={[s.badge, { backgroundColor: readiness?.ready ? C.successSoft : C.warningSoft }]}>
            <Text style={[s.badgeText, { color: readiness?.ready ? C.successText : C.warningText }]} testID="portfolio-readiness-status">
              {readiness?.ready ? 'READY' : 'NOT READY'}
            </Text>
          </View>
        </View>
        {(readiness?.checks || []).map((chk: any) => (
          <View key={chk.check} style={s.lineRow} testID={`readiness-check-${chk.check}`}>
            <Ionicons name={chk.passed ? 'checkmark-circle' : 'close-circle'} size={15} color={chk.passed ? C.successText : C.errorText} />
            <Text style={s.lineLabel}>{chk.check.replace(/_/g, ' ')}</Text>
            <Text style={[s.lineDetail]} numberOfLines={1}>{chk.detail}</Text>
          </View>
        ))}
      </View>

      {/* Category summaries */}
      <View style={s.panel} testID="portfolio-categories-panel">
        <Text style={s.panelTitle}>Category Portfolio ({categories.length})</Text>
        {categories.map((cat) => (
          <View key={cat.category} style={s.catRow} testID={`portfolio-category-${cat.category.toLowerCase().replace(/[^a-z0-9]+/g, '-')}`}>
            <Text style={s.catName} numberOfLines={1}>{cat.category}</Text>
            <Text style={s.catMeta}>{cat.total} agents · {cat.active} active{cat.beta ? ` · ${cat.beta} beta` : ''}{cat.experimental ? ` · ${cat.experimental} exp` : ''}</Text>
          </View>
        ))}
      </View>

      {/* Feature coverage matrix */}
      <View style={s.panel} testID="portfolio-coverage-panel">
        <View style={s.panelHeader}>
          <Text style={s.panelTitle}>Feature Coverage Matrix</Text>
          <Text style={s.catMeta} testID="portfolio-coverage-summary">
            {coverage?.features_covered}/{coverage?.features_total} covered
          </Text>
        </View>
        {featureRows.map((row: any) => (
          <View key={row.feature_key} style={s.lineRow} testID={`coverage-row-${row.feature_key}`}>
            <Ionicons name={row.covered ? 'checkmark-circle' : 'alert-circle'} size={15} color={row.covered ? C.successText : C.errorText} />
            <Text style={s.lineLabel} numberOfLines={1}>{row.feature_key}</Text>
            <Text style={s.lineValue}>{row.active_agent_count} active / {row.agent_count} mapped</Text>
          </View>
        ))}
        <TouchableOpacity onPress={() => setShowAllFeatures(!showAllFeatures)} style={s.moreBtn} testID="portfolio-coverage-toggle" accessibilityLabel="Interactive element">
          <Text style={s.moreBtnText}>{showAllFeatures ? 'Show fewer features' : `Show all ${coverage?.features_total} features`}</Text>
        </TouchableOpacity>
      </View>
    </View>
  );
};

const makeStyles = (C: any, isCompact: boolean) => StyleSheet.create({
  center: { padding: 40, alignItems: 'center' },
  errorBox: { backgroundColor: C.errorSoft, borderRadius: 10, padding: 12, marginBottom: 12 },
  statsRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 10, marginBottom: 14 },
  statCard: {
    flexGrow: 1, minWidth: isCompact ? 100 : 130, backgroundColor: C.card, borderRadius: 12,
    borderWidth: 1, borderColor: C.border, padding: 12, gap: 4,
  },
  statValue: { fontSize: 18, fontWeight: '800', color: C.text },
  statLabel: { fontSize: 11, color: C.textSecondary },
  rowWrap: { flexDirection: isCompact ? 'column' : 'row', gap: 12, marginBottom: 12 },
  panel: {
    flex: 1, backgroundColor: C.card, borderRadius: 14, borderWidth: 1, borderColor: C.border,
    padding: 16, marginBottom: 12,
  },
  panelHeader: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 },
  panelTitle: { fontSize: 14, fontWeight: '700', color: C.text, marginBottom: 8 },
  lineRow: { flexDirection: 'row', alignItems: 'center', gap: 8, paddingVertical: 4 },
  lineLabel: { fontSize: 12, color: C.textSecondary, flexShrink: 1, minWidth: 90 },
  lineValue: { fontSize: 12, fontWeight: '700', color: C.text, marginLeft: 'auto' },
  lineDetail: { fontSize: 11, color: C.textDim, marginLeft: 'auto', maxWidth: isCompact ? 140 : 320 },
  badge: { paddingVertical: 4, paddingHorizontal: 10, borderRadius: 999 },
  badgeText: { fontSize: 11, fontWeight: '800' },
  catRow: { flexDirection: isCompact ? 'column' : 'row', justifyContent: 'space-between', paddingVertical: 6, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: C.border, gap: 2 },
  catName: { fontSize: 13, fontWeight: '600', color: C.text },
  catMeta: { fontSize: 11, color: C.textDim },
  moreBtn: { marginTop: 10, alignSelf: 'flex-start', paddingVertical: 6, paddingHorizontal: 14, borderRadius: 999, backgroundColor: C.primarySoft },
  moreBtnText: { fontSize: 12, fontWeight: '700', color: C.accentText },
});

export default AgentPortfolioTab;
