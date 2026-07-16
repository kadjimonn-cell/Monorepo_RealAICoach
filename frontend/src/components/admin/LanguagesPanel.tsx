import React, { useState, useCallback } from 'react';
import { View, Text, TouchableOpacity, ActivityIndicator, Switch } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { useLiveQuery } from '../../hooks/useLiveQuery';
import AutoFixBanner from './AutoFixBanner';
import { useAdminTheme } from '../../hooks/useAdminTheme';
import { useTranslation } from '../../hooks/useTranslation';
import { handleAppRecoverableError } from '../../utils/appRecoverableError';

const tx = (_key: string, fallback: string) => fallback;

export default function LanguagesPanel({ colors: _colors }: { colors: any }) {
  const { t } = useTranslation();
  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };

  const colors = useAdminTheme();
  const { data: langData, loading } = useLiveQuery('/i18n/languages', { pollInterval: 30000, entity: 'i18n' });
  const { data: prefData } = useLiveQuery('/i18n/user-preference', { pollInterval: 30000, entity: 'i18n' });
  const languages = langData?.languages || [];
  const [currentLang, setCurrentLang] = useState('en');

  // Quality Score state
  const [qualityScores, setQualityScores] = useState<any[]>([]);
  const [scoringInProgress, setScoringInProgress] = useState(false);
  const [fixingLang, setFixingLang] = useState<string | null>(null);
  const [scoreError, setScoreError] = useState<string | null>(null);
  const [expandedScore, setExpandedScore] = useState<string | null>(null);

  // Health Dashboard state
  const [healthConfig, setHealthConfig] = useState<any>(null);
  const [qualityHistory, setQualityHistory] = useState<any[]>([]);
  const [showConfig, setShowConfig] = useState(false);
  const [savingConfig, setSavingConfig] = useState(false);
  const [configThreshold, setConfigThreshold] = useState(70);
  const [configEnabled, setConfigEnabled] = useState(true);
  const [configAlerts, setConfigAlerts] = useState(true);

  React.useEffect(() => { if (prefData?.language) setCurrentLang(prefData.language); }, [prefData]);

  // Load cached data on mount
  React.useEffect(() => {
    api.get('/i18n/quality-scores').then(r => {
      if (r.data?.scores?.length) setQualityScores(r.data.scores);
    }).catch(() => {});
    api.get('/i18n/quality-history').then(r => {
      if (r.data?.history?.length) setQualityHistory(r.data.history);
    }).catch(() => {});
    api.get('/i18n/quality-config').then(r => {
      if (r.data) {
        setHealthConfig(r.data);
        setConfigThreshold(r.data.threshold || 70);
        setConfigEnabled(r.data.enabled ?? true);
        setConfigAlerts(r.data.email_alerts ?? true);
      }
    }).catch(() => {});
  }, []);

  const setLang = async (code: string) => {
    try { await api.post('/i18n/user-preference', { language: code }); setCurrentLang(code); } catch (error) { handleAppRecoverableError({ scope: 'src/components/admin/LanguagesPanel.tsx#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
  };

  const runQualityScore = useCallback(async () => {
    setScoringInProgress(true);
    setScoreError(null);
    try {
      const r = await api.post('/i18n/quality-score', { sample_size: 20 }, { timeout: 120000 });
      setQualityScores(r.data.scores || []);
      // Refresh history
      const h = await api.get('/i18n/quality-history');
      if (h.data?.history) setQualityHistory(h.data.history);
    } catch (e: any) {
      setScoreError(e?.response?.data?.detail || 'Quality scoring failed');
    } finally {
      setScoringInProgress(false);
    }
  }, []);

  const fixTranslations = useCallback(async (langCode: string) => {
    setFixingLang(langCode);
    try {
      const score = qualityScores.find(s => s.code === langCode);
      const keys = score?.issues?.map((i: any) => i.key) || [];
      await api.post('/i18n/fix-translations', { language: langCode, keys }, { timeout: 60000 });
      const r = await api.post('/i18n/quality-score', { languages: [langCode], sample_size: 20 }, { timeout: 60000 });
      if (r.data.scores?.length) {
        setQualityScores(prev => prev.map(s => s.code === langCode ? r.data.scores[0] : s));
      }
    } catch (error) { handleAppRecoverableError({ scope: 'src/components/admin/LanguagesPanel.tsx#catch2', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); } finally { setFixingLang(null); }
  }, [qualityScores]);

  const saveConfig = useCallback(async () => {
    setSavingConfig(true);
    try {
      await api.post('/i18n/quality-config', {
        enabled: configEnabled,
        threshold: configThreshold,
        email_alerts: configAlerts,
      });
      setHealthConfig((prev: any) => ({ ...prev, enabled: configEnabled, threshold: configThreshold, email_alerts: configAlerts }));
      setShowConfig(false);
    } catch (error) { handleAppRecoverableError({ scope: 'src/components/admin/LanguagesPanel.tsx#catch3', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); } finally { setSavingConfig(false); }
  }, [configEnabled, configThreshold, configAlerts]);

  const getScoreColor = (score: number) => {
    if (score >= 90) return 'var(--app-success)';
    if (score >= 75) return 'var(--app-primary)';
    if (score >= 60) return 'var(--app-warning)';
    return 'var(--app-error)';
  };

  const getScoreLabel = (score: number) => {
    if (score >= 90) return 'Excellent';
    if (score >= 75) return 'Good';
    if (score >= 60) return 'Fair';
    return 'Needs Work';
  };

  if (loading) return <ActivityIndicator color={'var(--app-primary)'} />;

  const avgScore = qualityScores.length
    ? Math.round(qualityScores.filter(s => s.score > 0).reduce((a, b) => a + b.score, 0) / Math.max(qualityScores.filter(s => s.score > 0).length, 1))
    : null;

  const maxHistoryScore = qualityHistory.length ? Math.max(...qualityHistory.map(h => h.avg_score || 0)) : 100;

  return (
    <View data-testid="admin-languages-panel" testID="admin-languages-panel">
      <AutoFixBanner domain="languages" />
      <View style={{ marginBottom: 6 }}>
        <Text style={{ color: colors.text, fontSize: 18, fontWeight: '800' }}>{tx('admin.languagesPanel.auto.text.001', 'Translation Health Dashboard')}</Text>
        <Text style={{ color: colors.textMuted, fontSize: 11, marginTop: 2 }}>{tx('admin.languagesPanel.auto.text.002', 'Monitor translation quality, trends, and automated alerts')}</Text>
      </View>

      {/* Stats Row */}
      <View style={{ flexDirection: 'row', gap: 8, marginTop: 16, marginBottom: 16 }}>
        <View style={{ flex: 1, backgroundColor: colors.primarySoft, borderRadius: 10, padding: 14, borderWidth: 1, borderColor: colors.primarySoft }}>
          <Text style={{ color: colors.primary, fontSize: 20, fontWeight: '800' }}>{languages.length}</Text>
          <Text style={{ color: colors.textMuted, fontSize: 10, fontWeight: '600' }}>{tx('admin.languagesPanel.auto.text.003', 'Languages')}</Text>
        </View>
        <View style={{ flex: 1, backgroundColor: colors.successSoft, borderRadius: 10, padding: 14, borderWidth: 1, borderColor: colors.successSoft }}>
          <Text style={{ color: colors.successText, fontSize: 20, fontWeight: '800' }}>{avgScore !== null ? `${avgScore}%` : '--'}</Text>
          <Text style={{ color: colors.textMuted, fontSize: 10, fontWeight: '600' }}>{tx('admin.languagesPanel.auto.text.004', 'Avg Quality')}</Text>
        </View>
        <View style={{ flex: 1, backgroundColor: colors.accentSoft, borderRadius: 10, padding: 14, borderWidth: 1, borderColor: colors.accentSoft }}>
          <Text style={{ color: colors.accent, fontSize: 20, fontWeight: '800' }}>{qualityHistory.length}</Text>
          <Text style={{ color: colors.textMuted, fontSize: 10, fontWeight: '600' }}>{tx('admin.languagesPanel.auto.text.005', 'Scans Run')}</Text>
        </View>
        <View style={{ flex: 1, backgroundColor: configEnabled ? 'var(--app-success-soft)' : 'var(--app-error-soft)', borderRadius: 10, padding: 14, borderWidth: 1, borderColor: configEnabled ? 'var(--app-success-soft)' : 'var(--app-error-soft)' }}>
          <Ionicons name={configEnabled ? 'shield-checkmark' : 'shield-outline'} size={20} color={configEnabled ? 'var(--app-success)' : 'var(--app-error)'} />
          <Text style={{ color: colors.textMuted, fontSize: 10, fontWeight: '600' }}>{configEnabled ? 'Active' : 'Paused'}</Text>
        </View>
      </View>

      {/* Quality Trend Chart */}
      {qualityHistory.length > 0 && (
        <View style={{ backgroundColor: colors.surfaceHover, borderRadius: 14, padding: 16, marginBottom: 16, borderWidth: 1, borderColor: colors.border }} data-testid="quality-trend-section" testID="quality-trend-section">
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 14 }}>
            <Ionicons name="trending-up" size={16} color={'var(--app-primary)'} />
            <Text style={{ color: colors.text, fontSize: 14, fontWeight: '700' }}>{tx('admin.languagesPanel.auto.text.006', 'Quality Trend')}</Text>
            <Text style={{ color: colors.textMuted, fontSize: 10, marginLeft: 'auto' }}>Last {qualityHistory.length} scan(s)</Text>
          </View>
          <View style={{ height: 100, flexDirection: 'row', alignItems: 'flex-end', gap: 3, paddingBottom: 20 }}>
            {qualityHistory.slice(-20).map((h, i) => {
              const barHeight = Math.max(((h.avg_score || 0) / Math.max(maxHistoryScore, 1)) * 80, 4);
              const barColor = getScoreColor(h.avg_score || 0);
              return (
                <View key={i} style={{ flex: 1, alignItems: 'center' }}>
                  <Text style={{ color: barColor, fontSize: 8, fontWeight: '700', marginBottom: 2 }}>{h.avg_score}%</Text>
                  <View style={{ height: barHeight, width: '80%', backgroundColor: barColor, borderRadius: 3, minWidth: 6 }} />
                  <Text style={{ color: colors.textMuted, fontSize: 7, marginTop: 2 }}>
                    {h.evaluated_at?.slice(5, 10) || ''}
                  </Text>
                </View>
              );
            })}
          </View>
          {/* Threshold line indicator */}
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginTop: 4 }}>
            <View style={{ height: 1, flex: 1, backgroundColor: colors.errorSoft, borderStyle: 'dashed' }} />
            <Text style={{ color: colors.error, fontSize: 9, fontWeight: '600' }}>Threshold: {configThreshold}%</Text>
          </View>
        </View>
      )}

      {/* Monitoring Config */}
      <View style={{ backgroundColor: colors.surfaceHover, borderRadius: 14, padding: 16, marginBottom: 16, borderWidth: 1, borderColor: colors.border }} data-testid="health-config-section" testID="health-config-section">
        <TouchableOpacity accessibilityLabel={tx('admin.languagesPanel.auto.accessibility.001', 'Weekly Monitoring')}
          onPress={() => setShowConfig(!showConfig)}
          style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
            <Ionicons name="settings-outline" size={16} color={colors.textMuted} />
            <View>
              <Text style={{ color: colors.text, fontSize: 13, fontWeight: '700' }}>{tx('admin.languagesPanel.auto.text.007', 'Weekly Monitoring')}</Text>
              <Text style={{ color: colors.textMuted, fontSize: 10 }}>
                {healthConfig?.last_run ? `Last run: ${new Date(healthConfig.last_run).toLocaleDateString()}` : 'Not yet run'} | Threshold: {configThreshold}%
              </Text>
            </View>
          </View>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
            <View style={{ backgroundColor: configEnabled ? 'var(--app-success-soft)' : 'var(--app-error-soft)', paddingHorizontal: 8, paddingVertical: 3, borderRadius: 6 }}>
              <Text style={{ color: configEnabled ? 'var(--app-success)' : 'var(--app-error)', fontSize: 10, fontWeight: '700' }}>{configEnabled ? 'ON' : 'OFF'}</Text>
            </View>
            <Ionicons name={showConfig ? 'chevron-up' : 'chevron-down'} size={16} color={colors.textMuted} />
          </View>
        </TouchableOpacity>

        {showConfig && (
          <View style={{ marginTop: 14, gap: 12 }}>
            <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
              <Text style={{ color: colors.text, fontSize: 12, fontWeight: '600' }}>{tx('admin.languagesPanel.auto.text.008', 'Enable Weekly Scan')}</Text>
              <Switch value={configEnabled} onValueChange={setConfigEnabled} trackColor={{ false: 'var(--app-primary)', true: 'var(--app-success)' }} data-testid="config-enabled-switch" testID="config-enabled-switch" />
            </View>
            <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
              <Text style={{ color: colors.text, fontSize: 12, fontWeight: '600' }}>{tx('admin.languagesPanel.auto.text.009', 'Email Alerts')}</Text>
              <Switch value={configAlerts} onValueChange={setConfigAlerts} trackColor={{ false: 'var(--app-primary)', true: 'var(--app-primary)' }} data-testid="config-alerts-switch" testID="config-alerts-switch" />
            </View>
            <View>
              <Text style={{ color: colors.text, fontSize: 12, fontWeight: '600', marginBottom: 8 }}>Alert Threshold: {configThreshold}%</Text>
              <View style={{ flexDirection: 'row', gap: 6 }}>
                {[50, 60, 70, 80, 90].map(v => (
                  <TouchableOpacity
                    key={v}
                    onPress={() => setConfigThreshold(v)}
                    data-testid={`threshold-${v}`} testID={`threshold-${v}`}
                    style={{
                      flex: 1, paddingVertical: 8, borderRadius: 8, alignItems: 'center',
                      backgroundColor: (globalThis as any).__alphaColor(configThreshold === v ? 'var(--app-primary)' : colors.border, '60'),
                      borderWidth: 1, borderColor: configThreshold === v ? 'var(--app-primary)' : 'transparent',
                    }}>
                    <Text style={{ color: configThreshold === v ? colors.primaryText : colors.text, fontSize: 12, fontWeight: '700' }}>{v}%</Text>
                  </TouchableOpacity>
                ))}
              </View>
            </View>
            <TouchableOpacity
              onPress={saveConfig}
              disabled={savingConfig}
              data-testid="save-config-btn" testID="save-config-btn"
              style={{ backgroundColor: colors.success, paddingVertical: 10, borderRadius: 8, alignItems: 'center', marginTop: 4 }}>
              {savingConfig ? <ActivityIndicator size="small" color={colors.primaryText} /> : (
                <Text style={{ color: colors.primaryText, fontSize: 12, fontWeight: '700' }}>{tx('admin.languagesPanel.auto.text.010', 'Save Configuration')}</Text>
              )}
            </TouchableOpacity>
          </View>
        )}
      </View>

      {/* AI Translation Quality Score */}
      <View style={{ marginBottom: 20, backgroundColor: colors.surfaceHover, borderRadius: 14, padding: 16, borderWidth: 1, borderColor: colors.border }} data-testid="quality-score-section" testID="quality-score-section">
        <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14 }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
            <View style={{ width: 28, height: 28, borderRadius: 8, backgroundColor: colors.accentSoft, alignItems: 'center', justifyContent: 'center' }}>
              <Ionicons name="sparkles" size={16} color={'var(--app-primary)'} />
            </View>
            <View>
              <Text style={{ color: colors.text, fontSize: 14, fontWeight: '700' }}>{tx('admin.languagesPanel.auto.text.011', 'AI Translation Quality Score')}</Text>
              <Text style={{ color: colors.textMuted, fontSize: 10 }}>{tx('admin.languagesPanel.auto.text.012', 'AI evaluates accuracy, naturalness & consistency')}</Text>
            </View>
          </View>
          <TouchableOpacity
            onPress={runQualityScore}
            disabled={scoringInProgress}
            data-testid="run-quality-score-btn" testID="run-quality-score-btn"
            style={{
              flexDirection: 'row', alignItems: 'center', gap: 5,
              backgroundColor: scoringInProgress ? colors.border : 'var(--app-border)',
              paddingHorizontal: 14, paddingVertical: 8, borderRadius: 8,
            }}>
            {scoringInProgress ? <ActivityIndicator size="small" color={colors.primaryText} /> : <Ionicons name="analytics" size={14} color={colors.primaryText} />}
            <Text style={{ color: colors.primaryText, fontSize: 11, fontWeight: '700' }}>
              {scoringInProgress ? 'Scoring...' : qualityScores.length ? 'Re-Score' : 'Run Score'}
            </Text>
          </TouchableOpacity>
        </View>

        {scoreError && (
          <View style={{ backgroundColor: colors.errorSoft, borderRadius: 8, padding: 10, marginBottom: 12, borderWidth: 1, borderColor: colors.errorSoft }}>
            <Text style={{ color: colors.error, fontSize: 11 }}>{scoreError}</Text>
          </View>
        )}

        {qualityScores.length > 0 && (
          <View style={{ gap: 6 }}>
            {qualityScores.filter(s => s.score >= 0).sort((a, b) => a.score - b.score).map(score => (
              <View key={score.code} data-testid={`quality-score-${score.code}`} testID={`quality-score-${score.code}`}>
                <TouchableOpacity accessibilityLabel={tx('admin.languagesPanel.auto.accessibility.002', 'Expand language quality details')}
                  onPress={() => setExpandedScore(expandedScore === score.code ? null : score.code)}
                  style={{
                    flexDirection: 'row', alignItems: 'center', gap: 10,
                    backgroundColor: expandedScore === score.code ? colors.primarySoft : 'transparent',
                    padding: 10, borderRadius: 10,
                    borderWidth: 1, borderColor: expandedScore === score.code ? colors.primarySoft : 'transparent',
                  }}>
                  <Text style={{ color: colors.textMuted, fontSize: 11, fontWeight: '800', width: 24 }}>{score.code.toUpperCase()}</Text>
                  <View style={{ flex: 1 }}>
                    <View style={{ height: 6, backgroundColor: colors.border, borderRadius: 3, overflow: 'hidden' }}>
                      <View style={{ height: 6, width: `${Math.max(score.score, 5)}%`, backgroundColor: getScoreColor(score.score), borderRadius: 3 }} />
                    </View>
                  </View>
                  <Text style={{ color: getScoreColor(score.score), fontSize: 13, fontWeight: '800', width: 38, textAlign: 'right' }}>{score.score}%</Text>
                  <View style={{ backgroundColor: (globalThis as any).__alphaColor(getScoreColor(score.score), '15'), paddingHorizontal: 6, paddingVertical: 2, borderRadius: 4 }}>
                    <Text style={{ color: getScoreColor(score.score), fontSize: 9, fontWeight: '700' }}>{getScoreLabel(score.score)}</Text>
                  </View>
                  {score.issues?.length > 0 && (
                    <TouchableOpacity
                      onPress={() => fixTranslations(score.code)}
                      disabled={fixingLang === score.code}
                      data-testid={`fix-btn-${score.code}`} testID={`fix-btn-${score.code}`}
                      style={{
                        flexDirection: 'row', alignItems: 'center', gap: 3,
                        backgroundColor: fixingLang === score.code ? colors.border : 'var(--app-error)',
                        paddingHorizontal: 8, paddingVertical: 4, borderRadius: 6,
                      }}>
                      {fixingLang === score.code ? <ActivityIndicator size={10} color={colors.primaryText} /> : <Ionicons name="hammer" size={10} color={colors.primaryText} />}
                      <Text style={{ color: colors.primaryText, fontSize: 9, fontWeight: '700' }}>
                        {fixingLang === score.code ? 'Fixing...' : `Fix ${score.issues.length}`}
                      </Text>
                    </TouchableOpacity>
                  )}
                  <Ionicons name={expandedScore === score.code ? 'chevron-up' : 'chevron-down'} size={14} color={colors.textMuted} />
                </TouchableOpacity>

                {expandedScore === score.code && score.issues?.length > 0 && (
                  <View style={{ marginLeft: 34, marginTop: 6, marginBottom: 8, gap: 4 }}>
                    {score.summary && <Text style={{ color: colors.textMuted, fontSize: 10, fontStyle: 'italic', marginBottom: 4 }}>{score.summary}</Text>}
                    {score.issues.map((issue: any, idx: number) => (
                      <View key={idx} style={{ backgroundColor: issue.severity === 'high' ? 'var(--app-error-soft)' : 'var(--app-warning-soft)', borderRadius: 8, padding: 8, borderLeftWidth: 3, borderLeftColor: issue.severity === 'high' ? 'var(--app-error)' : 'var(--app-warning)' }}>
                        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4, marginBottom: 2 }}>
                          <Text style={{ color: issue.severity === 'high' ? 'var(--app-error)' : 'var(--app-warning)', fontSize: 8, fontWeight: '800', textTransform: 'uppercase' }}>{issue.severity}</Text>
                          <Text style={{ color: colors.textMuted, fontSize: 9 }}>{issue.key}</Text>
                        </View>
                        <Text style={{ color: colors.text, fontSize: 10 }}>{issue.issue}</Text>
                        {issue.suggestion && <Text style={{ color: colors.successText, fontSize: 10, marginTop: 2 }}>Suggestion: {issue.suggestion}</Text>}
                      </View>
                    ))}
                  </View>
                )}
              </View>
            ))}
          </View>
        )}

        {!qualityScores.length && !scoringInProgress && (
          <View style={{ alignItems: 'center', paddingVertical: 20 }}>
            <Ionicons name="shield-checkmark-outline" size={32} color={colors.textMuted + '60'} />
            <Text style={{ color: colors.textMuted, fontSize: 12, marginTop: 8, textAlign: 'center' }}>{tx('admin.languagesPanel.auto.text.013', 'Run AI quality scoring to evaluate translation accuracy across all languages')}</Text>
          </View>
        )}
      </View>

      {/* Language Grid */}
      <Text style={{ color: colors.text, fontSize: 14, fontWeight: '700', marginBottom: 10 }}>Available Languages ({languages.length})</Text>
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginBottom: 20 }}>
        {languages.map((l: any) => (
          <TouchableOpacity key={l.code} onPress={() => setLang(l.code)} data-testid={`admin-lang-${l.code}`} testID={`admin-lang-${l.code}`}
            style={{
              flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 12, paddingVertical: 8, borderRadius: 10,
              backgroundColor: currentLang === l.code ? colors.primarySoft : colors.surfaceHover,
              borderWidth: 1, borderColor: currentLang === l.code ? 'var(--app-primary)' : colors.border,
            }}>
            <Text style={{ fontSize: 11, fontWeight: '800', color: currentLang === l.code ? 'var(--app-primary)' : colors.textMuted }}>{l.code.toUpperCase()}</Text>
            <Text style={{ color: currentLang === l.code ? 'var(--app-primary)' : colors.text, fontSize: 12, fontWeight: '600' }}>{l.name}</Text>
            {currentLang === l.code && <Ionicons name="checkmark-circle" size={14} color={'var(--app-success)'} />}
          </TouchableOpacity>
        ))}
      </View>
    </View>
  );
}
