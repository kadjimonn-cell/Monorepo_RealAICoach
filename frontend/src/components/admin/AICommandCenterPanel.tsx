import React, { useState, useEffect, useCallback } from 'react';
import { View, Text, ScrollView, TouchableOpacity, ActivityIndicator, TextInput, Switch, useWindowDimensions } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { useTheme } from '../../context/ThemeContext';
import { useLanguage } from '../../i18n/LanguageContext';
import { AdminSurfaceHealthMatrix } from './AdminSurfaceHealthMatrix';

import { useAdminTheme } from '../../hooks/useAdminTheme';
import { handleAppRecoverableError } from '../../utils/appRecoverableError';
// Module-level AC removed - now using useAdminTheme() inside component
function makeT(AC: any) { return {
  bg: AC.bg,
  bgSoft: AC.bgSoft || AC.surfaceHover,
  card: AC.surface,
  border: AC.border,
  text: AC.text,
  textSec: AC.textSec,
  textMuted: AC.textMuted,
  primary: AC.primary,
  primaryText: AC.primaryText,
  success: AC.success,
  successSoft: AC.successSoft || `${AC.success}15`,
  warning: AC.warning,
  warningSoft: AC.warningSoft || `${AC.warning}15`,
  error: AC.error,
  errorSoft: AC.errorSoft || `${AC.error}15`,
  purple: AC.info || 'var(--app-primary)',
  ai: AC.info || AC.primary,
  cyan: AC.info || AC.primary,
}; }

const tx = (_key: string, fallback: string) => fallback;

const INSIGHTS = [
  { key: 'sla_predictor', labelKey: 'aiCommandCenter.insights.sla', icon: 'timer', scoreKey: 'risk_score', summaryKey: 'risk_summary', endpoint: 'sla-predictor', navId: 'sla', invertScore: true },
  { key: 'conversion_optimizer', labelKey: 'aiCommandCenter.insights.conversion', icon: 'funnel', scoreKey: 'conversion_health', summaryKey: 'executive_summary', endpoint: 'conversion-optimizer', navId: 'conversion' },
  { key: 'onboarding_coach', labelKey: 'aiCommandCenter.insights.onboarding', icon: 'rocket', scoreKey: 'onboarding_health', summaryKey: 'executive_summary', endpoint: 'onboarding-coach', navId: 'onboarding-analytics' },
  { key: 'newsletter_suggestions', labelKey: 'aiCommandCenter.insights.newsletter', icon: 'newspaper', scoreKey: 'newsletter_health', summaryKey: 'executive_summary', endpoint: 'newsletter-suggestions', navId: 'newsletter' },
  { key: 'security_narrative', labelKey: 'aiCommandCenter.insights.security', icon: 'shield-checkmark', scoreKey: 'security_score', summaryKey: 'narrative', endpoint: 'security-narrative', navId: 'enterprise-security' },
  { key: 'churn_predictor', labelKey: 'aiCommandCenter.insights.churn', icon: 'people', scoreKey: 'churn_risk_score', summaryKey: 'executive_summary', endpoint: 'churn-predictor', navId: 'sub-analytics', invertScore: true },
  { key: 'performance_forecast', labelKey: 'aiCommandCenter.insights.performance', icon: 'speedometer', scoreKey: 'performance_score', summaryKey: 'forecast_summary', endpoint: 'performance-forecast', navId: 'performance' },
  { key: 'fraud_narrative', labelKey: 'aiCommandCenter.insights.fraud', icon: 'warning', scoreKey: 'fraud_risk_score', summaryKey: 'narrative', endpoint: 'fraud-narrative', navId: 'fraud', invertScore: true },
];

interface Props {
  colors?: any;
  onNavigate?: (navId: string) => void;
}

export default function AICommandCenterPanel({ colors, onNavigate }: Props) {
  const AC = useAdminTheme();
  const { t } = useLanguage();
  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };
  const T = React.useMemo(() => makeT(AC), [AC]);
  const { width } = useWindowDimensions();
  const { colors: themeColors, darkMode } = useTheme();
  const resolvedColors = colors || themeColors;
  const cardBg = darkMode ? T.card : resolvedColors.card;
  const softBg = darkMode ? T.bgSoft : resolvedColors.bgSoft;
  const border = resolvedColors.border;
  const text = resolvedColors.text;
  const textSec = resolvedColors.textSec;
  const textMuted = resolvedColors.textMuted;
  const isCompact = width < 640;
  const [insights, setInsights] = useState<Record<string, any>>({});
  const [loading, setLoading] = useState(true);
  const [runningAll, setRunningAll] = useState(false);
  const [runningKey, setRunningKey] = useState('');
  const [autoFixRunning, setAutoFixRunning] = useState(false);
  const [autoFixResult, setAutoFixResult] = useState<any>(null);
  const [showFixLog, setShowFixLog] = useState(false);
  const [reviewQueue, setReviewQueue] = useState<any[]>([]);
  const [reviewActionState, setReviewActionState] = useState<{ actionId: string; mode: 'approve' | 'dismiss' | '' }>({ actionId: '', mode: '' });
  const [reviewFeedback, setReviewFeedback] = useState<{ type: 'success' | 'error' | ''; message: string }>({ type: '', message: '' });
  const [resetting, setResetting] = useState(false);
  // Feature 1: Configurable Confidence Threshold
  const [afConfig, setAfConfig] = useState<any>({ confidence_threshold: 80, auto_run_enabled: true, run_interval_minutes: 30 });
  const [showConfig, setShowConfig] = useState(false);
  const [savingConfig, setSavingConfig] = useState(false);
  // Feature 2: Export
  const [exporting, setExporting] = useState('');
  // Feature 3: Performance Budgets
  const [budgets, setBudgets] = useState<any[]>([]);
  const [violations, setViolations] = useState<any[]>([]);
  const [showBudgets, setShowBudgets] = useState(false);
  const [newBudget, setNewBudget] = useState({ route: '', label: '', lcp_budget_ms: '1000', fcp_budget_ms: '1000', ttfb_budget_ms: '500' });
  const [architectureCompliance, setArchitectureCompliance] = useState<any>(null);
  const [responsiveGuardrail, setResponsiveGuardrail] = useState<any>(null);
  const [guardrailRunning, setGuardrailRunning] = useState(false);
  const [themeGuardrail, setThemeGuardrail] = useState<any>(null);
  const [themeGuardrailRunning, setThemeGuardrailRunning] = useState(false);
  const [themeSuggestions, setThemeSuggestions] = useState<any[]>([]);
  const [themeSuggestionsSummary, setThemeSuggestionsSummary] = useState<any>({ total: 0, safe_ready: 0, completed: 0, pending: 0 });
  const [themeSuggestionsRunMeta, setThemeSuggestionsRunMeta] = useState<any>({ source_run_id: null, source_checked_at: null });
  const [themeSuggestionsLoading, setThemeSuggestionsLoading] = useState(false);
  const [themeSuggestionsAction, setThemeSuggestionsAction] = useState<{ suggestionId: string; mode: 'done' | 'reopen' | '' }>({ suggestionId: '', mode: '' });
  const [safeThemeAutofixRunning, setSafeThemeAutofixRunning] = useState(false);
  const [safeThemeAutofixResult, setSafeThemeAutofixResult] = useState<any>(null);

  const loadReviewQueue = useCallback(async () => {
    try {
      const queueRes = await api.get('/admin/ai-autofix/review-queue');
      setReviewQueue(queueRes.data?.items || []);
    } catch {
      setReviewQueue([]);
    }
  }, []);

  const loadAll = useCallback(async () => {
    setLoading(true);
    const failSafe = setTimeout(() => setLoading(false), 15000);
    try {
      const results: Record<string, any> = {};

      await Promise.all(
        INSIGHTS.map(async (ins) => {
          try {
            const res = await api.get(`/admin/ai-insights/latest/${ins.key}`, { timeout: 8000 });
            if (res.data && !res.data.status) results[ins.key] = res.data;
          } catch (error) { handleAppRecoverableError({ scope: 'src/components/admin/AICommandCenterPanel.tsx#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
        })
      );

      try {
        const fixRes = await api.get('/admin/ai-autofix/latest', { timeout: 8000 });
        if (fixRes.data && !fixRes.data.status) setAutoFixResult(fixRes.data);
      } catch (error) { handleAppRecoverableError({ scope: 'src/components/admin/AICommandCenterPanel.tsx#catch2', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }

      await loadReviewQueue();

      try {
        const cfgRes = await api.get('/admin/ai-autofix/config', { timeout: 8000 });
        if (cfgRes.data) setAfConfig(cfgRes.data);
      } catch (error) { handleAppRecoverableError({ scope: 'src/components/admin/AICommandCenterPanel.tsx#catch3', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }

      try {
        const [budgetRes, violRes, architectureRes, guardrailRes, themeGuardRes, themeSuggestionsRes] = await Promise.all([
          api.get('/admin/performance-guardian/budgets', { timeout: 8000 }),
          api.get('/admin/performance-guardian/budget-violations', { timeout: 8000 }),
          api.get('/admin/autonomous-engine/architecture/compliance-dashboard?limit=12', { timeout: 8000 }),
          api.get('/admin/autonomous-engine/responsive-guardrail/status', { timeout: 8000 }),
          api.get('/admin/autonomous-engine/theme-guardrail/status', { timeout: 8000 }),
          api.get('/admin/autonomous-engine/theme-guardrail/low-severity/suggestions?limit=8', { timeout: 8000 }),
        ]);
        if (budgetRes.data?.budgets) setBudgets(budgetRes.data.budgets);
        if (violRes.data?.violations) setViolations(violRes.data.violations);
        if (architectureRes.data) setArchitectureCompliance(architectureRes.data);
        if (guardrailRes.data) setResponsiveGuardrail(guardrailRes.data);
        if (themeGuardRes.data) setThemeGuardrail(themeGuardRes.data);
        if (themeSuggestionsRes.data) {
          setThemeSuggestions(themeSuggestionsRes.data.suggestions || []);
          setThemeSuggestionsSummary({
            total: themeSuggestionsRes.data.total ?? 0,
            safe_ready: themeSuggestionsRes.data.safe_ready ?? 0,
            completed: themeSuggestionsRes.data.completed ?? 0,
            pending: themeSuggestionsRes.data.pending ?? 0,
          });
          setThemeSuggestionsRunMeta({
            source_run_id: themeSuggestionsRes.data.source_run_id || null,
            source_checked_at: themeSuggestionsRes.data.source_checked_at || null,
          });
        }
      } catch (error) { handleAppRecoverableError({ scope: 'src/components/admin/AICommandCenterPanel.tsx#catch4', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }

      setInsights(results);
    } finally {
      clearTimeout(failSafe);
      setLoading(false);
    }
  }, [loadReviewQueue]);

  const runSingle = useCallback(async (ins: typeof INSIGHTS[0]) => {
    setRunningKey(ins.key);
    try {
      const res = await api.post(`/admin/ai-insights/${ins.endpoint}`);
      setInsights(prev => ({ ...prev, [ins.key]: res.data }));
    } catch (error) { handleAppRecoverableError({ scope: 'src/components/admin/AICommandCenterPanel.tsx#catch5', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
    setRunningKey('');
  }, []);

  const runAll = useCallback(async () => {
    setRunningAll(true);
    for (const ins of INSIGHTS) {
      setRunningKey(ins.key);
      try {
        const res = await api.post(`/admin/ai-insights/${ins.endpoint}`);
        setInsights(prev => ({ ...prev, [ins.key]: res.data }));
      } catch (error) { handleAppRecoverableError({ scope: 'src/components/admin/AICommandCenterPanel.tsx#catch6', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
    }
    setRunningKey('');
    setRunningAll(false);
  }, []);

  const runAutoFix = useCallback(async () => {
    setAutoFixRunning(true);
    try {
      const res = await api.post('/admin/ai-autofix/run');
      setAutoFixResult(res.data);
      setShowFixLog(true);
      await loadReviewQueue();
      // After auto-fix, re-run all analyses to get updated scores
      setTimeout(() => runAll(), 1000);
    } catch (error) { handleAppRecoverableError({ scope: 'src/components/admin/AICommandCenterPanel.tsx#catch7', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
    setAutoFixRunning(false);
  }, [loadReviewQueue, runAll]);

  const resetAutoFix = useCallback(async () => {
    setResetting(true);
    try {
      await api.post('/admin/ai-autofix/reset');
      setAutoFixResult(null);
      setReviewQueue([]);
      setReviewFeedback({ type: 'success', message: 'Auto-fix state reset. Run a new scan to generate fresh review items.' });
    } catch (error) { handleAppRecoverableError({ scope: 'src/components/admin/AICommandCenterPanel.tsx#catch8', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
    setResetting(false);
  }, []);

  const approveReviewItem = useCallback(async (actionId: string) => {
    setReviewActionState({ actionId, mode: 'approve' });
    setReviewFeedback({ type: '', message: '' });
    try {
      const res = await api.post(`/admin/ai-autofix/review-queue/${actionId}/approve`);
      await loadReviewQueue();
      setReviewFeedback({ type: 'success', message: res.data?.status === 'approved_and_applied' ? 'Review item approved and applied successfully.' : 'Review item approved.' });
    } catch (err: any) {
      setReviewFeedback({ type: 'error', message: err?.response?.data?.detail || 'Unable to approve the review item right now.' });
    }
    setReviewActionState({ actionId: '', mode: '' });
  }, [loadReviewQueue]);

  const dismissReviewItem = useCallback(async (actionId: string) => {
    setReviewActionState({ actionId, mode: 'dismiss' });
    setReviewFeedback({ type: '', message: '' });
    try {
      await api.post(`/admin/ai-autofix/review-queue/${actionId}/dismiss`);
      await loadReviewQueue();
      setReviewFeedback({ type: 'success', message: 'Review item dismissed successfully.' });
    } catch (err: any) {
      setReviewFeedback({ type: 'error', message: err?.response?.data?.detail || 'Unable to dismiss the review item right now.' });
    }
    setReviewActionState({ actionId: '', mode: '' });
  }, [loadReviewQueue]);

  // Feature 1: Save config
  const saveConfig = useCallback(async () => {
    setSavingConfig(true);
    try {
      const res = await api.put('/admin/ai-autofix/config', afConfig);
      if (res.data) setAfConfig(res.data);
      setShowConfig(false);
    } catch (error) { handleAppRecoverableError({ scope: 'src/components/admin/AICommandCenterPanel.tsx#catch9', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
    setSavingConfig(false);
  }, [afConfig]);

  // Feature 2: Export
  const backendUrl = (api.defaults.baseURL || '').replace(/\/$/, '');
  const exportAudit = useCallback(async (format: 'csv' | 'pdf') => {
    setExporting(format);
    try {
      if (typeof window !== 'undefined') {
        window.open(`${backendUrl}/admin/ai-autofix/export/${format}`, '_blank');
      }
    } catch (error) { handleAppRecoverableError({ scope: 'src/components/admin/AICommandCenterPanel.tsx#catch10', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
    setTimeout(() => setExporting(''), 1500);
  }, [backendUrl]);

  // Feature 3: Add budget
  const addBudget = useCallback(async () => {
    if (!newBudget.route) return;
    try {
      await api.post('/admin/performance-guardian/budgets', {
        route: newBudget.route,
        label: newBudget.label || newBudget.route,
        lcp_budget_ms: parseInt(newBudget.lcp_budget_ms),
        fcp_budget_ms: parseInt(newBudget.fcp_budget_ms),
        ttfb_budget_ms: parseInt(newBudget.ttfb_budget_ms),
      });
      // Refresh budgets and violations
      const [budgetRes, violRes] = await Promise.all([
        api.get('/admin/performance-guardian/budgets'),
        api.get('/admin/performance-guardian/budget-violations'),
      ]);
      if (budgetRes.data?.budgets) setBudgets(budgetRes.data.budgets);
      if (violRes.data?.violations) setViolations(violRes.data.violations);
      setNewBudget({ route: '', label: '', lcp_budget_ms: '1000', fcp_budget_ms: '1000', ttfb_budget_ms: '500' });
    } catch (error) { handleAppRecoverableError({ scope: 'src/components/admin/AICommandCenterPanel.tsx#catch11', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
  }, [newBudget]);

  const deleteBudget = useCallback(async (route: string) => {
    try {
      await api.delete(`/admin/performance-guardian/budgets/${encodeURIComponent(route)}`);
      setBudgets(prev => prev.filter(b => b.route !== route));
      setViolations(prev => prev.filter(v => v.route !== route));
    } catch (error) { handleAppRecoverableError({ scope: 'src/components/admin/AICommandCenterPanel.tsx#catch12', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
  }, []);

  const runResponsiveGuardrail = useCallback(async () => {
    setGuardrailRunning(true);
    try {
      const res = await api.post('/admin/autonomous-engine/responsive-guardrail/run');
      if (res.data) setResponsiveGuardrail(res.data);
    } catch (error) { handleAppRecoverableError({ scope: 'src/components/admin/AICommandCenterPanel.tsx#catch13', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
    setGuardrailRunning(false);
  }, []);

  const runThemeGuardrail = useCallback(async () => {
    setThemeGuardrailRunning(true);
    try {
      const res = await api.post('/admin/autonomous-engine/theme-guardrail/run');
      if (res.data) setThemeGuardrail(res.data);
      const suggestionsRes = await api.get('/admin/autonomous-engine/theme-guardrail/low-severity/suggestions?limit=8');
      if (suggestionsRes.data) {
        setThemeSuggestions(suggestionsRes.data.suggestions || []);
        setThemeSuggestionsSummary({
          total: suggestionsRes.data.total ?? 0,
          safe_ready: suggestionsRes.data.safe_ready ?? 0,
          completed: suggestionsRes.data.completed ?? 0,
          pending: suggestionsRes.data.pending ?? 0,
        });
        setThemeSuggestionsRunMeta({
          source_run_id: suggestionsRes.data.source_run_id || null,
          source_checked_at: suggestionsRes.data.source_checked_at || null,
        });
      }
    } catch (error) { handleAppRecoverableError({ scope: 'src/components/admin/AICommandCenterPanel.tsx#catch14', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
    setThemeGuardrailRunning(false);
  }, []);

  const refreshThemeSuggestions = useCallback(async () => {
    setThemeSuggestionsLoading(true);
    try {
      const res = await api.get('/admin/autonomous-engine/theme-guardrail/low-severity/suggestions?limit=8');
      if (res.data) {
        setThemeSuggestions(res.data.suggestions || []);
        setThemeSuggestionsSummary({
          total: res.data.total ?? 0,
          safe_ready: res.data.safe_ready ?? 0,
          completed: res.data.completed ?? 0,
          pending: res.data.pending ?? 0,
        });
        setThemeSuggestionsRunMeta({
          source_run_id: res.data.source_run_id || null,
          source_checked_at: res.data.source_checked_at || null,
        });
      }
    } catch (error) { handleAppRecoverableError({ scope: 'src/components/admin/AICommandCenterPanel.tsx#catch15', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
    setThemeSuggestionsLoading(false);
  }, []);

  const runSafeThemeAutofix = useCallback(async () => {
    setSafeThemeAutofixRunning(true);
    try {
      const res = await api.post('/admin/autonomous-engine/theme-guardrail/safe-autofix/run');
      if (res.data) {
        setSafeThemeAutofixResult(res.data);
        if (res.data.theme_guardrail) {
          setThemeGuardrail((prev: any) => ({
            ...(prev || {}),
            run_id: res.data.theme_guardrail.run_id,
            status: res.data.theme_guardrail.status,
            theme_guardrail_score: res.data.theme_guardrail.score,
            issues_total: res.data.theme_guardrail.issues_total,
            issues_by_severity: res.data.theme_guardrail.issues_by_severity,
          }));
        }
      }
      await refreshThemeSuggestions();
    } catch (error) { handleAppRecoverableError({ scope: 'src/components/admin/AICommandCenterPanel.tsx#catch16', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
    setSafeThemeAutofixRunning(false);
  }, [refreshThemeSuggestions]);

  const markThemeSuggestionDone = useCallback(async (suggestionId: string) => {
    setThemeSuggestionsAction({ suggestionId, mode: 'done' });
    try {
      await api.post(`/admin/autonomous-engine/theme-guardrail/low-severity/suggestions/${suggestionId}/mark-done`);
      await refreshThemeSuggestions();
    } catch (error) { handleAppRecoverableError({ scope: 'src/components/admin/AICommandCenterPanel.tsx#catch17', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
    setThemeSuggestionsAction({ suggestionId: '', mode: '' });
  }, [refreshThemeSuggestions]);

  const reopenThemeSuggestion = useCallback(async (suggestionId: string) => {
    setThemeSuggestionsAction({ suggestionId, mode: 'reopen' });
    try {
      await api.post(`/admin/autonomous-engine/theme-guardrail/low-severity/suggestions/${suggestionId}/reopen`);
      await refreshThemeSuggestions();
    } catch (error) { handleAppRecoverableError({ scope: 'src/components/admin/AICommandCenterPanel.tsx#catch18', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
    setThemeSuggestionsAction({ suggestionId: '', mode: '' });
  }, [refreshThemeSuggestions]);

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { loadAll(); }, []);

  // Calculate combined platform health
  const scores = INSIGHTS.map(ins => {
    const data = insights[ins.key];
    if (!data) return null;
    const raw = data[ins.scoreKey] ?? 0;
    return ins.invertScore ? (100 - raw) : raw;
  }).filter(s => s !== null) as number[];

  const platformScore = scores.length > 0 ? Math.round(scores.reduce((a, b) => a + b, 0) / scores.length) : 0;
  const analyzed = scores.length;
  const platformColor = platformScore >= 70 ? T.success : platformScore >= 40 ? T.warning : T.error;
  const platformLabel = platformScore >= 70
    ? t('aiCommandCenter.platform.healthy')
    : platformScore >= 40
      ? t('aiCommandCenter.platform.attention')
      : t('aiCommandCenter.platform.critical');

  if (loading) return (
    <View style={{ paddingVertical: 60, alignItems: 'center' }}>
      <ActivityIndicator size="large" color={T.ai} />
      <Text style={{ color: textSec, marginTop: 12, fontSize: 13 }}>{t('aiCommandCenter.loading')}</Text>
    </View>
  );

  return (
    <ScrollView style={{ flex: 1, backgroundColor: 'transparent' }} contentContainerStyle={{ padding: 20, gap: 20 }} data-testid="ai-command-center" testID="ai-command-center">

      {/* Hero Card */}
      <View style={{ backgroundColor: cardBg, borderRadius: 20, padding: isCompact ? 18 : 28, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(T.ai, '30'), overflow: 'hidden' }} data-testid="ai-cc-hero" testID="ai-cc-hero">
        <View style={{ flexDirection: isCompact ? 'column' : 'row', alignItems: isCompact ? 'stretch' : 'center', gap: 10, marginBottom: 20 }}>
          <View style={{ width: 40, height: 40, borderRadius: 14, backgroundColor: (globalThis as any).__alphaColor(T.ai, '25'), alignItems: 'center', justifyContent: 'center' }}>
            <Ionicons name="sparkles" size={22} color={T.ai} />
          </View>
          <View style={{ flex: 1 }}>
            <Text style={{ color: text, fontSize: 20, fontWeight: '900', letterSpacing: -0.5 }}>{t('aiCommandCenter.title')}</Text>
            <Text style={{ color: textMuted, fontSize: 11 }}>{t('aiCommandCenter.subtitle')}</Text>
          </View>
          <View style={{ flexDirection: isCompact ? 'column' : 'row', gap: 10, width: isCompact ? '100%' : undefined }}>
            <TouchableOpacity onPress={runAll} disabled={runningAll || autoFixRunning} style={{ backgroundColor: runningAll ? (globalThis as any).__alphaColor(T.ai, '30') : T.ai, paddingHorizontal: 18, paddingVertical: 10, borderRadius: 12, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, minWidth: isCompact ? undefined : 132 }} data-testid="ai-cc-run-all-btn" testID="ai-cc-run-all-btn">
              {runningAll ? <ActivityIndicator size="small" color={T.primaryText} /> : <Ionicons name="analytics" size={14} color={T.primaryText} />}
              <Text style={{ color: T.primaryText, fontWeight: '700', fontSize: 12 }}>{runningAll ? t('aiCommandCenter.actions.analyzing') : t('aiCommandCenter.actions.analyzeAll')}</Text>
            </TouchableOpacity>
            <TouchableOpacity onPress={runAutoFix} disabled={autoFixRunning || runningAll} style={{ backgroundColor: autoFixRunning ? (globalThis as any).__alphaColor(T.success, '30') : T.success, paddingHorizontal: 18, paddingVertical: 10, borderRadius: 12, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, minWidth: isCompact ? undefined : 132 }} data-testid="ai-cc-autofix-btn" testID="ai-cc-autofix-btn">
              {autoFixRunning ? <ActivityIndicator size="small" color={T.primaryText} /> : <Ionicons name="hammer" size={14} color={T.primaryText} />}
              <Text style={{ color: T.primaryText, fontWeight: '700', fontSize: 12 }}>{autoFixRunning ? t('aiCommandCenter.actions.fixing') : t('aiCommandCenter.actions.autoFixAll')}</Text>
            </TouchableOpacity>
          </View>
        </View>

        {/* Platform Health Ring */}
        <View style={{ flexDirection: isCompact ? 'column' : 'row', alignItems: isCompact ? 'stretch' : 'center', gap: 24 }}>
          <View style={{ width: 100, height: 100, borderRadius: 50, borderWidth: 5, borderColor: (globalThis as any).__alphaColor(platformColor, '30'), alignItems: 'center', justifyContent: 'center', position: 'relative' }}>
            <View style={{ width: 86, height: 86, borderRadius: 43, borderWidth: 4, borderColor: platformColor, alignItems: 'center', justifyContent: 'center' }}>
              <Text style={{ color: platformColor, fontSize: 32, fontWeight: '900' }}>{platformScore}</Text>
            </View>
          </View>
          <View style={{ flex: 1 }}>
            <Text style={{ color: platformColor, fontSize: 16, fontWeight: '800', marginBottom: 4 }}>{platformLabel}</Text>
            <Text style={{ color: textSec, fontSize: 12, lineHeight: 18 }}>
              {t('aiCommandCenter.platform.summary').replace('{analyzed}', String(analyzed)).replace('{total}', '8')}{' '}
              {analyzed < 8
                ? t('aiCommandCenter.platform.remaining').replace('{remaining}', String(8 - analyzed))
                : t('aiCommandCenter.platform.allAnalyzed')}
            </Text>
          </View>
        </View>
      </View>

      <AdminSurfaceHealthMatrix colors={resolvedColors} compact={isCompact} />

      <View style={{ backgroundColor: cardBg, borderRadius: 16, borderWidth: 1, borderColor: border, padding: 16, gap: 12 }} data-testid="architecture-compliance-widget" testID="architecture-compliance-widget">
        <View style={{ flexDirection: isCompact ? 'column' : 'row', alignItems: isCompact ? 'stretch' : 'center', justifyContent: 'space-between', gap: 10 }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
            <View style={{ width: 32, height: 32, borderRadius: 10, backgroundColor: colors.accentSoft, alignItems: 'center', justifyContent: 'center' }}>
              <Ionicons name="git-network" size={16} color={'var(--app-primary)'} />
            </View>
            <View>
              <Text style={{ color: T.text, fontSize: 14, fontWeight: '700' }}>{t('aiCommandCenter.architecture.title')}</Text>
              <Text style={{ color: T.textMuted, fontSize: 11 }}>{t('aiCommandCenter.architecture.subtitle')}</Text>
            </View>
          </View>
          <TouchableOpacity
            onPress={loadAll}
            style={{ backgroundColor: colors.accentSoft, borderWidth: 1, borderColor: colors.accent, borderRadius: 8, paddingHorizontal: 12, paddingVertical: 7, flexDirection: 'row', alignItems: 'center', gap: 6, justifyContent: 'center' }}
            data-testid="architecture-widget-refresh-btn"
            testID="architecture-widget-refresh-btn"
          >
            <Ionicons name="refresh" size={13} color={'var(--app-primary)'} />
            <Text style={{ color: colors.accent, fontSize: 11, fontWeight: '700' }}>{tx('admin.aiCommandCenterPanel.auto.text.001', 'Refresh')}</Text>
          </TouchableOpacity>
        </View>

        <View style={{ flexDirection: isCompact ? 'column' : 'row', gap: 14 }}>
          <View style={{ backgroundColor: softBg, borderRadius: 12, borderWidth: 1, borderColor: border, padding: 14, minWidth: 180 }} data-testid="architecture-compliance-score-card" testID="architecture-compliance-score-card">
            <Text style={{ color: T.textMuted, fontSize: 10, fontWeight: '700', letterSpacing: 0.4 }}>{tx('admin.aiCommandCenterPanel.auto.text.002', 'COMPLIANCE SCORE')}</Text>
            <Text style={{ color: (architectureCompliance?.architecture_compliance_score ?? 0) >= 85 ? T.success : (architectureCompliance?.architecture_compliance_score ?? 0) >= 60 ? T.warning : T.error, fontSize: 34, fontWeight: '900', marginTop: 4 }} data-testid="architecture-compliance-score-value" testID="architecture-compliance-score-value">
              {architectureCompliance?.architecture_compliance_score ?? '--'}
            </Text>
            <Text style={{ color: T.textSec, fontSize: 11, marginTop: 2 }} data-testid="architecture-compliance-status" testID="architecture-compliance-status">
              Status: {architectureCompliance?.architecture_status || 'UNKNOWN'}
            </Text>
            <Text style={{ color: T.textMuted, fontSize: 10, marginTop: 6 }} data-testid="architecture-compliance-checked-at" testID="architecture-compliance-checked-at">
              {architectureCompliance?.checked_at ? `Updated ${getAge(architectureCompliance.checked_at)}` : 'Waiting for data'}
            </Text>
          </View>

          <View style={{ flex: 1, backgroundColor: softBg, borderRadius: 12, borderWidth: 1, borderColor: border, padding: 14 }} data-testid="architecture-compliance-meta" testID="architecture-compliance-meta">
            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10 }}>
              <View style={{ backgroundColor: colors.successSoft, borderWidth: 1, borderColor: colors.successSoft, borderRadius: 8, paddingHorizontal: 10, paddingVertical: 8 }}>
                <Text style={{ color: colors.successText, fontSize: 10, fontWeight: '700' }}>{tx('admin.aiCommandCenterPanel.auto.text.003', 'Modules Passing')}</Text>
                <Text style={{ color: T.text, fontSize: 14, fontWeight: '800' }} data-testid="architecture-modules-pass" testID="architecture-modules-pass">
                  {(architectureCompliance?.summary?.pass_modules ?? 0)} / {(architectureCompliance?.summary?.total_modules ?? 0)}
                </Text>
              </View>
              <View style={{ backgroundColor: colors.warningSoft, borderWidth: 1, borderColor: colors.warningSoft, borderRadius: 8, paddingHorizontal: 10, paddingVertical: 8 }}>
                <Text style={{ color: colors.warningText, fontSize: 10, fontWeight: '700' }}>{tx('admin.aiCommandCenterPanel.auto.text.004', 'Modules Failing')}</Text>
                <Text style={{ color: T.text, fontSize: 14, fontWeight: '800' }} data-testid="architecture-modules-fail" testID="architecture-modules-fail">
                  {architectureCompliance?.summary?.fail_modules ?? 0}
                </Text>
              </View>
              <View style={{ backgroundColor: colors.primarySoft, borderWidth: 1, borderColor: colors.primarySoft, borderRadius: 8, paddingHorizontal: 10, paddingVertical: 8 }}>
                <Text style={{ color: colors.primary, fontSize: 10, fontWeight: '700' }}>{tx('admin.aiCommandCenterPanel.auto.text.005', 'Gateway Mapping')}</Text>
                <Text style={{ color: T.text, fontSize: 14, fontWeight: '800' }} data-testid="architecture-gateway-mapping-status" testID="architecture-gateway-mapping-status">
                  {architectureCompliance?.gateway_path_mapping?.communications_pilot?.path_mapping_verified ? 'Verified' : 'Attention'}
                </Text>
              </View>
            </View>
          </View>
        </View>

        <View style={{ gap: 8 }} data-testid="architecture-gate-history" testID="architecture-gate-history">
          <Text style={{ color: T.textSec, fontSize: 12, fontWeight: '700' }}>{tx('admin.aiCommandCenterPanel.auto.text.006', 'Recent Gate History')}</Text>
          {(architectureCompliance?.gate_history || []).slice(0, 8).map((row: any, idx: number) => (
            <View key={`${row.run_id || idx}`} style={{ backgroundColor: T.bgSoft, borderWidth: 1, borderColor: T.border, borderRadius: 10, padding: 10, gap: 6 }} data-testid={`architecture-gate-history-row-${idx}`} testID={`architecture-gate-history-row-${idx}`}>
              <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
                <Text style={{ color: T.text, fontSize: 11, fontWeight: '700' }} numberOfLines={1}>Run {row.run_id || 'n/a'}</Text>
                <Text style={{ color: row.overall_status === 'PASS' ? T.success : T.error, fontSize: 10, fontWeight: '800' }}>{row.overall_status || 'UNKNOWN'}</Text>
              </View>
              <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6 }}>
                {Object.entries(row.gates || {}).map(([gateKey, gateStatus]: any) => (
                  <View key={`${row.run_id || idx}-${String(gateKey)}`} style={{ borderRadius: 999, borderWidth: 1, borderColor: gateStatus === 'PASS' ? 'var(--app-success-soft)' : gateStatus === 'FAIL' ? 'var(--app-error-soft)' : T.border, backgroundColor: gateStatus === 'PASS' ? 'var(--app-success-soft)' : gateStatus === 'FAIL' ? 'var(--app-error-soft)' : T.bgSoft, paddingHorizontal: 8, paddingVertical: 4 }} data-testid={`architecture-gate-pill-${idx}-${String(gateKey)}`} testID={`architecture-gate-pill-${idx}-${String(gateKey)}`}>
                    <Text style={{ color: gateStatus === 'PASS' ? T.success : gateStatus === 'FAIL' ? T.error : T.textMuted, fontSize: 9, fontWeight: '700' }}>{String(gateKey).toUpperCase()}: {String(gateStatus).toUpperCase()}</Text>
                  </View>
                ))}
              </View>
            </View>
          ))}
          {(architectureCompliance?.gate_history || []).length === 0 && (
            <Text style={{ color: T.textMuted, fontSize: 11 }} data-testid="architecture-gate-history-empty" testID="architecture-gate-history-empty">{tx('admin.aiCommandCenterPanel.auto.text.007', 'No gate history available yet.')}</Text>
          )}
        </View>
      </View>

      <View style={{ backgroundColor: cardBg, borderRadius: 16, borderWidth: 1, borderColor: border, padding: 16, gap: 12 }} data-testid="responsive-guardrail-widget" testID="responsive-guardrail-widget">
        <View style={{ flexDirection: isCompact ? 'column' : 'row', alignItems: isCompact ? 'stretch' : 'center', justifyContent: 'space-between', gap: 10 }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
            <View style={{ width: 32, height: 32, borderRadius: 10, backgroundColor: colors.successSoft, alignItems: 'center', justifyContent: 'center' }}>
              <Ionicons name="phone-portrait" size={16} color={'var(--app-success)'} />
            </View>
            <View>
              <Text style={{ color: T.text, fontSize: 14, fontWeight: '700' }}>{tx('admin.aiCommandCenterPanel.auto.text.008', 'Responsive Guardrail Checker')}</Text>
              <Text style={{ color: T.textMuted, fontSize: 11 }}>{tx('admin.aiCommandCenterPanel.auto.text.009', 'Automated hidden-tab/overflow guard for admin & executive surfaces')}</Text>
            </View>
          </View>
          <TouchableOpacity
            onPress={runResponsiveGuardrail}
            disabled={guardrailRunning}
            style={{ backgroundColor: colors.successSoft, borderWidth: 1, borderColor: colors.successSoft, borderRadius: 8, paddingHorizontal: 12, paddingVertical: 7, flexDirection: 'row', alignItems: 'center', gap: 6, justifyContent: 'center', opacity: guardrailRunning ? 0.7 : 1 }}
            data-testid="responsive-guardrail-run-btn"
            testID="responsive-guardrail-run-btn"
          >
            <Ionicons name={guardrailRunning ? 'hourglass-outline' : 'play'} size={13} color={'var(--app-success)'} />
            <Text style={{ color: colors.successText, fontSize: 11, fontWeight: '700' }}>{guardrailRunning ? 'Running…' : 'Run Check'}</Text>
          </TouchableOpacity>
        </View>

        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10 }}>
          <View style={{ backgroundColor: T.bgSoft, borderRadius: 10, borderWidth: 1, borderColor: T.border, paddingHorizontal: 12, paddingVertical: 10 }} data-testid="responsive-guardrail-status" testID="responsive-guardrail-status">
            <Text style={{ color: T.textMuted, fontSize: 10, fontWeight: '700' }}>{tx('admin.aiCommandCenterPanel.auto.text.010', 'STATUS')}</Text>
            <Text style={{ color: responsiveGuardrail?.status === 'PASS' ? T.success : responsiveGuardrail?.status === 'FAIL' ? T.error : T.warning, fontSize: 14, fontWeight: '800' }}>{responsiveGuardrail?.status || 'NOT_RUN'}</Text>
          </View>
          <View style={{ backgroundColor: T.bgSoft, borderRadius: 10, borderWidth: 1, borderColor: T.border, paddingHorizontal: 12, paddingVertical: 10 }} data-testid="responsive-guardrail-score" testID="responsive-guardrail-score">
            <Text style={{ color: T.textMuted, fontSize: 10, fontWeight: '700' }}>{tx('admin.aiCommandCenterPanel.auto.text.011', 'SCORE')}</Text>
            <Text style={{ color: T.text, fontSize: 14, fontWeight: '800' }}>{responsiveGuardrail?.responsive_guardrail_score ?? 0}</Text>
          </View>
          <View style={{ backgroundColor: T.bgSoft, borderRadius: 10, borderWidth: 1, borderColor: T.border, paddingHorizontal: 12, paddingVertical: 10 }} data-testid="responsive-guardrail-files-scanned" testID="responsive-guardrail-files-scanned">
            <Text style={{ color: T.textMuted, fontSize: 10, fontWeight: '700' }}>{tx('admin.aiCommandCenterPanel.auto.text.012', 'FILES SCANNED')}</Text>
            <Text style={{ color: T.text, fontSize: 14, fontWeight: '800' }}>{responsiveGuardrail?.files_scanned ?? 0}</Text>
          </View>
          <View style={{ backgroundColor: T.bgSoft, borderRadius: 10, borderWidth: 1, borderColor: T.border, paddingHorizontal: 12, paddingVertical: 10 }} data-testid="responsive-guardrail-issues-total" testID="responsive-guardrail-issues-total">
            <Text style={{ color: T.textMuted, fontSize: 10, fontWeight: '700' }}>{tx('admin.aiCommandCenterPanel.auto.text.013', 'ISSUES')}</Text>
            <Text style={{ color: (responsiveGuardrail?.issues_total ?? 0) > 0 ? T.warning : T.success, fontSize: 14, fontWeight: '800' }}>{responsiveGuardrail?.issues_total ?? 0}</Text>
          </View>
        </View>

        {(responsiveGuardrail?.findings || []).length > 0 && (
          <View style={{ gap: 6 }} data-testid="responsive-guardrail-findings" testID="responsive-guardrail-findings">
            <Text style={{ color: T.textSec, fontSize: 12, fontWeight: '700' }}>{tx('admin.aiCommandCenterPanel.auto.text.014', 'Top Findings')}</Text>
            {(responsiveGuardrail.findings || []).slice(0, 4).map((f: any, idx: number) => (
              <View key={`${f.file || 'file'}-${idx}`} style={{ backgroundColor: T.bgSoft, borderRadius: 8, borderWidth: 1, borderColor: T.border, paddingHorizontal: 10, paddingVertical: 8 }} data-testid={`responsive-guardrail-finding-${idx}`} testID={`responsive-guardrail-finding-${idx}`}>
                <Text style={{ color: T.text, fontSize: 10, fontWeight: '700' }} numberOfLines={1}>{f.file}</Text>
                <Text style={{ color: T.textMuted, fontSize: 10 }} numberOfLines={2}>[{String(f.severity || '').toUpperCase()}] {f.message}</Text>
              </View>
            ))}
          </View>
        )}
      </View>

      <View style={{ backgroundColor: cardBg, borderRadius: 16, borderWidth: 1, borderColor: border, padding: 16, gap: 12 }} data-testid="theme-guardrail-widget" testID="theme-guardrail-widget">
        <View style={{ flexDirection: isCompact ? 'column' : 'row', alignItems: isCompact ? 'stretch' : 'center', justifyContent: 'space-between', gap: 10 }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
            <View style={{ width: 32, height: 32, borderRadius: 10, backgroundColor: colors.accentSoft, alignItems: 'center', justifyContent: 'center' }}>
              <Ionicons name="contrast" size={16} color={'var(--app-primary)'} />
            </View>
            <View>
              <Text style={{ color: T.text, fontSize: 14, fontWeight: '700' }}>{tx('admin.aiCommandCenterPanel.auto.text.015', 'Theme Guardrail (Light/Dark)')}</Text>
              <Text style={{ color: T.textMuted, fontSize: 11 }}>{tx('admin.aiCommandCenterPanel.auto.text.016', 'Global adaptive-theme audit + lock against hardcoded regressions')}</Text>
            </View>
          </View>
          <TouchableOpacity
            onPress={runThemeGuardrail}
            disabled={themeGuardrailRunning}
            style={{ backgroundColor: colors.accentSoft, borderWidth: 1, borderColor: colors.accentSoft, borderRadius: 8, paddingHorizontal: 12, paddingVertical: 7, flexDirection: 'row', alignItems: 'center', gap: 6, justifyContent: 'center', opacity: themeGuardrailRunning ? 0.7 : 1 }}
            data-testid="theme-guardrail-run-btn"
            testID="theme-guardrail-run-btn"
          >
            <Ionicons name={themeGuardrailRunning ? 'hourglass-outline' : 'play'} size={13} color={'var(--app-primary)'} />
            <Text style={{ color: colors.accent, fontSize: 11, fontWeight: '700' }}>{themeGuardrailRunning ? 'Running…' : 'Run Theme Audit'}</Text>
          </TouchableOpacity>
        </View>

        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10 }}>
          <View style={{ backgroundColor: T.bgSoft, borderRadius: 10, borderWidth: 1, borderColor: T.border, paddingHorizontal: 12, paddingVertical: 10 }} data-testid="theme-guardrail-status" testID="theme-guardrail-status">
            <Text style={{ color: T.textMuted, fontSize: 10, fontWeight: '700' }}>{tx('admin.aiCommandCenterPanel.auto.text.017', 'STATUS')}</Text>
            <Text style={{ color: themeGuardrail?.status === 'PASS' ? T.success : themeGuardrail?.status === 'FAIL' ? T.error : T.warning, fontSize: 14, fontWeight: '800' }}>{themeGuardrail?.status || 'NOT_RUN'}</Text>
          </View>
          <View style={{ backgroundColor: T.bgSoft, borderRadius: 10, borderWidth: 1, borderColor: T.border, paddingHorizontal: 12, paddingVertical: 10 }} data-testid="theme-guardrail-score" testID="theme-guardrail-score">
            <Text style={{ color: T.textMuted, fontSize: 10, fontWeight: '700' }}>{tx('admin.aiCommandCenterPanel.auto.text.018', 'SCORE')}</Text>
            <Text style={{ color: T.text, fontSize: 14, fontWeight: '800' }}>{themeGuardrail?.theme_guardrail_score ?? 0}</Text>
          </View>
          <View style={{ backgroundColor: T.bgSoft, borderRadius: 10, borderWidth: 1, borderColor: T.border, paddingHorizontal: 12, paddingVertical: 10 }} data-testid="theme-guardrail-files-scanned" testID="theme-guardrail-files-scanned">
            <Text style={{ color: T.textMuted, fontSize: 10, fontWeight: '700' }}>{tx('admin.aiCommandCenterPanel.auto.text.019', 'FILES SCANNED')}</Text>
            <Text style={{ color: T.text, fontSize: 14, fontWeight: '800' }}>{themeGuardrail?.files_scanned ?? 0}</Text>
          </View>
          <View style={{ backgroundColor: T.bgSoft, borderRadius: 10, borderWidth: 1, borderColor: T.border, paddingHorizontal: 12, paddingVertical: 10 }} data-testid="theme-guardrail-issues-total" testID="theme-guardrail-issues-total">
            <Text style={{ color: T.textMuted, fontSize: 10, fontWeight: '700' }}>{tx('admin.aiCommandCenterPanel.auto.text.020', 'ISSUES')}</Text>
            <Text style={{ color: (themeGuardrail?.issues_total ?? 0) > 0 ? T.warning : T.success, fontSize: 14, fontWeight: '800' }}>{themeGuardrail?.issues_total ?? 0}</Text>
          </View>
        </View>

        {(themeGuardrail?.findings || []).length > 0 && (
          <View style={{ gap: 6 }} data-testid="theme-guardrail-findings" testID="theme-guardrail-findings">
            <Text style={{ color: T.textSec, fontSize: 12, fontWeight: '700' }}>{tx('admin.aiCommandCenterPanel.auto.text.021', 'Top Theme Findings')}</Text>
            {(themeGuardrail.findings || []).slice(0, 4).map((f: any, idx: number) => (
              <View key={`${f.file || 'file'}-${idx}`} style={{ backgroundColor: T.bgSoft, borderRadius: 8, borderWidth: 1, borderColor: T.border, paddingHorizontal: 10, paddingVertical: 8 }} data-testid={`theme-guardrail-finding-${idx}`} testID={`theme-guardrail-finding-${idx}`}>
                <Text style={{ color: T.text, fontSize: 10, fontWeight: '700' }} numberOfLines={1}>{f.file}</Text>
                <Text style={{ color: T.textMuted, fontSize: 10 }} numberOfLines={2}>[{String(f.severity || '').toUpperCase()}] {f.message}</Text>
              </View>
            ))}
          </View>
        )}
      </View>

      <View style={{ backgroundColor: cardBg, borderRadius: 16, borderWidth: 1, borderColor: border, padding: 16, gap: 12 }} data-testid="theme-safe-autofix-widget" testID="theme-safe-autofix-widget">
        <View style={{ flexDirection: isCompact ? 'column' : 'row', alignItems: isCompact ? 'stretch' : 'center', justifyContent: 'space-between', gap: 10 }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
            <View style={{ width: 32, height: 32, borderRadius: 10, backgroundColor: colors.successSoft, alignItems: 'center', justifyContent: 'center' }}>
              <Ionicons name="shield-checkmark" size={16} color={T.successText} />
            </View>
            <View>
              <Text style={{ color: T.text, fontSize: 14, fontWeight: '700' }} data-testid="theme-safe-autofix-title" testID="theme-safe-autofix-title">{tx('admin.aiCommandCenterPanel.auto.text.022', 'Low-Severity Theme Safe Auto-Fix')}</Text>
              <Text style={{ color: T.textMuted, fontSize: 11 }} data-testid="theme-safe-autofix-subtitle" testID="theme-safe-autofix-subtitle">{tx('admin.aiCommandCenterPanel.auto.text.023', 'Prioritized cleanup guidance with safe auto-fix orchestration + completion tracking')}</Text>
            </View>
          </View>
          <View style={{ flexDirection: isCompact ? 'column' : 'row', gap: 8, width: isCompact ? '100%' : undefined }}>
            <TouchableOpacity
              onPress={refreshThemeSuggestions}
              disabled={themeSuggestionsLoading || safeThemeAutofixRunning}
              style={{ backgroundColor: colors.primarySoft, borderWidth: 1, borderColor: colors.primarySoft, borderRadius: 8, paddingHorizontal: 12, paddingVertical: 7, flexDirection: 'row', alignItems: 'center', gap: 6, justifyContent: 'center', opacity: themeSuggestionsLoading ? 0.7 : 1 }}
              data-testid="theme-safe-autofix-refresh-btn"
              testID="theme-safe-autofix-refresh-btn"
            >
              <Ionicons name={themeSuggestionsLoading ? 'hourglass-outline' : 'refresh'} size={13} color={'var(--app-primary)'} />
              <Text style={{ color: colors.primary, fontSize: 11, fontWeight: '700' }}>{themeSuggestionsLoading ? 'Refreshing…' : 'Refresh List'}</Text>
            </TouchableOpacity>
            <TouchableOpacity
              onPress={runSafeThemeAutofix}
              disabled={safeThemeAutofixRunning || themeGuardrailRunning}
              style={{ backgroundColor: colors.successSoft, borderWidth: 1, borderColor: colors.successSoft, borderRadius: 8, paddingHorizontal: 12, paddingVertical: 7, flexDirection: 'row', alignItems: 'center', gap: 6, justifyContent: 'center', opacity: safeThemeAutofixRunning ? 0.7 : 1 }}
              data-testid="theme-safe-autofix-run-btn"
              testID="theme-safe-autofix-run-btn"
            >
              <Ionicons name={safeThemeAutofixRunning ? 'hourglass-outline' : 'hammer'} size={13} color={T.successText} />
              <Text style={{ color: T.successText, fontSize: 11, fontWeight: '700' }}>{safeThemeAutofixRunning ? 'Running…' : 'Run Safe Auto-Fix'}</Text>
            </TouchableOpacity>
          </View>
        </View>

        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10 }}>
          <View style={{ backgroundColor: T.bgSoft, borderRadius: 10, borderWidth: 1, borderColor: T.border, paddingHorizontal: 12, paddingVertical: 10 }} data-testid="theme-safe-autofix-total" testID="theme-safe-autofix-total">
            <Text style={{ color: T.textMuted, fontSize: 10, fontWeight: '700' }}>{tx('admin.aiCommandCenterPanel.auto.text.024', 'TOTAL SUGGESTIONS')}</Text>
            <Text style={{ color: T.text, fontSize: 14, fontWeight: '800' }}>{themeSuggestionsSummary.total ?? 0}</Text>
          </View>
          <View style={{ backgroundColor: colors.successSoft, borderRadius: 10, borderWidth: 1, borderColor: colors.successSoft, paddingHorizontal: 12, paddingVertical: 10 }} data-testid="theme-safe-autofix-safe-ready" testID="theme-safe-autofix-safe-ready">
            <Text style={{ color: T.successText, fontSize: 10, fontWeight: '700' }}>{tx('admin.aiCommandCenterPanel.auto.text.025', 'SAFE READY')}</Text>
            <Text style={{ color: T.successText, fontSize: 14, fontWeight: '800' }}>{themeSuggestionsSummary.safe_ready ?? 0}</Text>
          </View>
          <View style={{ backgroundColor: colors.primarySoft, borderRadius: 10, borderWidth: 1, borderColor: colors.primarySoft, paddingHorizontal: 12, paddingVertical: 10 }} data-testid="theme-safe-autofix-completed" testID="theme-safe-autofix-completed">
            <Text style={{ color: colors.primary, fontSize: 10, fontWeight: '700' }}>{tx('admin.aiCommandCenterPanel.auto.text.026', 'COMPLETED')}</Text>
            <Text style={{ color: colors.primary, fontSize: 14, fontWeight: '800' }}>{themeSuggestionsSummary.completed ?? 0}</Text>
          </View>
          <View style={{ backgroundColor: colors.warningSoft, borderRadius: 10, borderWidth: 1, borderColor: colors.warningSoft, paddingHorizontal: 12, paddingVertical: 10 }} data-testid="theme-safe-autofix-pending" testID="theme-safe-autofix-pending">
            <Text style={{ color: T.warningText, fontSize: 10, fontWeight: '700' }}>{tx('admin.aiCommandCenterPanel.auto.text.027', 'PENDING')}</Text>
            <Text style={{ color: T.warningText, fontSize: 14, fontWeight: '800' }}>{themeSuggestionsSummary.pending ?? 0}</Text>
          </View>
        </View>

        {!!themeSuggestionsRunMeta?.source_checked_at && (
          <Text style={{ color: T.textMuted, fontSize: 10 }} data-testid="theme-safe-autofix-source-run" testID="theme-safe-autofix-source-run">
            Source scan: {themeSuggestionsRunMeta.source_run_id || 'n/a'} · {getAge(themeSuggestionsRunMeta.source_checked_at)}
          </Text>
        )}

        {safeThemeAutofixResult && (
          <View style={{ backgroundColor: colors.successSoft, borderRadius: 10, borderWidth: 1, borderColor: colors.successSoft, padding: 10, gap: 4 }} data-testid="theme-safe-autofix-last-run" testID="theme-safe-autofix-last-run">
            <Text style={{ color: T.successText, fontSize: 11, fontWeight: '700' }}>{tx('admin.aiCommandCenterPanel.auto.text.028', 'Last Safe Auto-Fix Run')}</Text>
            <Text style={{ color: T.textSec, fontSize: 10 }}>
              Applied: {safeThemeAutofixResult?.ai_autofix?.total_applied ?? 0} · Flagged: {safeThemeAutofixResult?.ai_autofix?.total_flagged ?? 0} · Theme Score: {safeThemeAutofixResult?.theme_guardrail?.score ?? '--'}
            </Text>
          </View>
        )}

        <View style={{ gap: 8 }} data-testid="theme-safe-autofix-list" testID="theme-safe-autofix-list">
          {themeSuggestions.length === 0 ? (
            <View style={{ backgroundColor: T.bgSoft, borderRadius: 10, borderWidth: 1, borderColor: T.border, padding: 10 }} data-testid="theme-safe-autofix-empty" testID="theme-safe-autofix-empty">
              <Text style={{ color: T.textMuted, fontSize: 11 }}>{tx('admin.aiCommandCenterPanel.auto.text.029', 'No low-severity theme suggestions pending right now.')}</Text>
            </View>
          ) : (
            themeSuggestions.slice(0, 6).map((row: any, idx: number) => {
              const isCompleted = row.status === 'completed';
              const isBusy = themeSuggestionsAction.suggestionId === row.suggestion_id;
              return (
                <View key={row.suggestion_id || idx} style={{ backgroundColor: T.bgSoft, borderRadius: 10, borderWidth: 1, borderColor: isCompleted ? 'var(--app-primary-soft)' : T.border, padding: 10, gap: 8 }} data-testid={`theme-safe-autofix-item-${idx}`} testID={`theme-safe-autofix-item-${idx}`}>
                  <View style={{ flexDirection: isCompact ? 'column' : 'row', gap: 8, justifyContent: 'space-between', alignItems: isCompact ? 'stretch' : 'center' }}>
                    <View style={{ flex: 1 }}>
                      <Text style={{ color: T.text, fontSize: 11, fontWeight: '700' }} numberOfLines={1} data-testid={`theme-safe-autofix-item-file-${idx}`} testID={`theme-safe-autofix-item-file-${idx}`}>{row.file}</Text>
                      <Text style={{ color: T.textSec, fontSize: 10, marginTop: 2 }} numberOfLines={2} data-testid={`theme-safe-autofix-item-message-${idx}`} testID={`theme-safe-autofix-item-message-${idx}`}>{row.message}</Text>
                    </View>
                    <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6 }}>
                      <View style={{ borderRadius: 999, borderWidth: 1, borderColor: colors.accentSoft, backgroundColor: colors.accentSoft, paddingHorizontal: 8, paddingVertical: 4 }} data-testid={`theme-safe-autofix-item-occurrence-${idx}`} testID={`theme-safe-autofix-item-occurrence-${idx}`}>
                        <Text style={{ color: colors.accent, fontSize: 9, fontWeight: '700' }}>{row.occurrence_count || 0}×</Text>
                      </View>
                      <View style={{ borderRadius: 999, borderWidth: 1, borderColor: row.safe_auto_fix ? 'var(--app-success-soft)' : 'var(--app-warning-soft)', backgroundColor: row.safe_auto_fix ? 'var(--app-success-soft)' : 'var(--app-warning-soft)', paddingHorizontal: 8, paddingVertical: 4 }} data-testid={`theme-safe-autofix-item-safety-${idx}`} testID={`theme-safe-autofix-item-safety-${idx}`}>
                        <Text style={{ color: row.safe_auto_fix ? T.success : T.warning, fontSize: 9, fontWeight: '700' }}>{row.safe_auto_fix ? 'SAFE READY' : 'REVIEW'}</Text>
                      </View>
                      <View style={{ borderRadius: 999, borderWidth: 1, borderColor: isCompleted ? 'var(--app-primary-soft)' : T.border, backgroundColor: isCompleted ? 'var(--app-primary-soft)' : T.bgSoft, paddingHorizontal: 8, paddingVertical: 4 }} data-testid={`theme-safe-autofix-item-status-${idx}`} testID={`theme-safe-autofix-item-status-${idx}`}>
                        <Text style={{ color: isCompleted ? 'var(--app-primary)' : T.textMuted, fontSize: 9, fontWeight: '700' }}>{isCompleted ? 'DONE' : 'PENDING'}</Text>
                      </View>
                    </View>
                  </View>

                  <Text style={{ color: T.textMuted, fontSize: 10 }} numberOfLines={2} data-testid={`theme-safe-autofix-item-guidance-${idx}`} testID={`theme-safe-autofix-item-guidance-${idx}`}>{row.suggested_fix}</Text>

                  <View style={{ flexDirection: 'row', justifyContent: 'flex-end' }}>
                    {isCompleted ? (
                      <TouchableOpacity
                        onPress={() => reopenThemeSuggestion(row.suggestion_id)}
                        disabled={isBusy}
                        style={{ backgroundColor: colors.primarySoft, borderWidth: 1, borderColor: colors.primarySoft, borderRadius: 8, paddingHorizontal: 10, paddingVertical: 6, flexDirection: 'row', alignItems: 'center', gap: 5, opacity: isBusy ? 0.7 : 1 }}
                        data-testid={`theme-safe-autofix-item-reopen-btn-${idx}`}
                        testID={`theme-safe-autofix-item-reopen-btn-${idx}`}
                      >
                        <Ionicons name={isBusy ? 'hourglass-outline' : 'refresh'} size={12} color={'var(--app-primary)'} />
                        <Text style={{ color: colors.primary, fontSize: 10, fontWeight: '700' }}>{isBusy ? 'Reopening…' : 'Reopen'}</Text>
                      </TouchableOpacity>
                    ) : (
                      <TouchableOpacity
                        onPress={() => markThemeSuggestionDone(row.suggestion_id)}
                        disabled={isBusy}
                        style={{ backgroundColor: colors.successSoft, borderWidth: 1, borderColor: colors.successSoft, borderRadius: 8, paddingHorizontal: 10, paddingVertical: 6, flexDirection: 'row', alignItems: 'center', gap: 5, opacity: isBusy ? 0.7 : 1 }}
                        data-testid={`theme-safe-autofix-item-done-btn-${idx}`}
                        testID={`theme-safe-autofix-item-done-btn-${idx}`}
                      >
                        <Ionicons name={isBusy ? 'hourglass-outline' : 'checkmark'} size={12} color={T.successText} />
                        <Text style={{ color: T.successText, fontSize: 10, fontWeight: '700' }}>{isBusy ? 'Saving…' : 'Mark as done'}</Text>
                      </TouchableOpacity>
                    )}
                  </View>
                </View>
              );
            })
          )}
        </View>
      </View>

      {/* Insight Grid */}
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 14 }} data-testid="ai-cc-grid" testID="ai-cc-grid">
        {INSIGHTS.map(ins => {
          const data = insights[ins.key];
          const isRunning = runningKey === ins.key;
          const hasData = data && !data.status;
          const rawScore = hasData ? (data[ins.scoreKey] ?? 0) : null;
          const displayScore = rawScore !== null ? rawScore : '--';
          const healthScore = rawScore !== null ? (ins.invertScore ? 100 - rawScore : rawScore) : null;
          const scoreColor = healthScore !== null ? (healthScore >= 70 ? T.success : healthScore >= 40 ? T.warning : T.error) : T.textMuted;
          const summary = hasData ? (data[ins.summaryKey] || '') : '';
          const age = hasData && data.created_at ? getAge(data.created_at) : null;

          return (
            <View key={ins.key} style={{ width: isCompact ? '100%' : '48.5%', minWidth: isCompact ? 0 : 300, backgroundColor: T.card, borderRadius: 16, padding: 18, borderWidth: 1, borderColor: hasData ? (globalThis as any).__alphaColor(scoreColor, '25') : T.border }} data-testid={`ai-cc-card-${ins.key}`} testID={`ai-cc-card-${ins.key}`}>
              <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, flex: 1, paddingRight: 8 }}>
                  <View style={{ width: 30, height: 30, borderRadius: 9, backgroundColor: (globalThis as any).__alphaColor(T.ai, '18'), alignItems: 'center', justifyContent: 'center' }}>
                    <Ionicons name={ins.icon as any} size={15} color={T.ai} />
                  </View>
                  <Text style={{ color: T.text, fontSize: 13, fontWeight: '700', flexShrink: 1 }}>{t(ins.labelKey)}</Text>
                </View>
                <View style={{ alignItems: 'center' }}>
                  {isRunning ? (
                    <ActivityIndicator size="small" color={T.ai} />
                  ) : (
                    <Text style={{ color: scoreColor, fontSize: 24, fontWeight: '900' }}>{displayScore}</Text>
                  )}
                  {!isRunning && hasData && <Text style={{ color: scoreColor, fontSize: 8, fontWeight: '700' }}>/100</Text>}
                </View>
              </View>

              {hasData ? (
                <>
                  <Text style={{ color: T.textSec, fontSize: 11, lineHeight: 16, marginBottom: 10 }} numberOfLines={3}>{summary}</Text>
                  <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
                    {age && <Text style={{ color: T.textMuted, fontSize: 9 }}>{age}</Text>}
                    <View style={{ flexDirection: 'row', gap: 8 }}>
                      {onNavigate && (
                        <TouchableOpacity onPress={() => onNavigate(ins.navId)} style={{ paddingHorizontal: 8, paddingVertical: 4, borderRadius: 6, backgroundColor: (globalThis as any).__alphaColor(T.primary, '15') }} data-testid={`ai-cc-goto-${ins.key}`} testID={`ai-cc-goto-${ins.key}`}>
                          <Text style={{ color: T.primary, fontSize: 10, fontWeight: '700' }}>{t('aiCommandCenter.actions.viewPanel')}</Text>
                        </TouchableOpacity>
                      )}
                      <TouchableOpacity onPress={() => runSingle(ins)} style={{ paddingHorizontal: 8, paddingVertical: 4, borderRadius: 6, backgroundColor: (globalThis as any).__alphaColor(T.ai, '15') }} data-testid={`ai-cc-refresh-${ins.key}`} testID={`ai-cc-refresh-${ins.key}`}>
                        <Text style={{ color: T.ai, fontSize: 10, fontWeight: '700' }}>{t('aiCommandCenter.actions.refresh')}</Text>
                      </TouchableOpacity>
                    </View>
                  </View>
                </>
              ) : (
                <TouchableOpacity onPress={() => runSingle(ins)} style={{ paddingVertical: 14, alignItems: 'center', borderRadius: 10, backgroundColor: (globalThis as any).__alphaColor(T.ai, '10'), borderWidth: 1, borderColor: (globalThis as any).__alphaColor(T.ai, '30') }} data-testid={`ai-cc-run-${ins.key}`} testID={`ai-cc-run-${ins.key}`}>
                  {isRunning ? (
                    <Text style={{ color: T.ai, fontSize: 12, fontWeight: '600' }}>{t('aiCommandCenter.actions.analyzing')}</Text>
                  ) : (
                    <Text style={{ color: T.ai, fontSize: 12, fontWeight: '700' }}>{t('aiCommandCenter.actions.runAnalysis')}</Text>
                  )}
                </TouchableOpacity>
              )}
            </View>
          );
        })}
      </View>

      {/* Auto-Fix Results with Confidence Scoring */}
      {autoFixResult && (
        <View style={{ backgroundColor: T.card, borderRadius: 16, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(T.success, '30'), overflow: 'hidden' }} data-testid="ai-autofix-results" testID="ai-autofix-results">
          <TouchableOpacity accessibilityLabel={tx('admin.aiCommandCenterPanel.auto.accessibility.001', 'AI Auto-Fix Engine')} onPress={() => setShowFixLog(!showFixLog)} style={{ padding: 16, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
              <View style={{ width: 32, height: 32, borderRadius: 10, backgroundColor: (globalThis as any).__alphaColor(T.success, '20'), alignItems: 'center', justifyContent: 'center' }}>
                <Ionicons name="hammer" size={16} color={T.successText} />
              </View>
              <View>
                <Text style={{ color: T.text, fontSize: 14, fontWeight: '700' }}>{tx('admin.aiCommandCenterPanel.auto.text.030', 'AI Auto-Fix Engine')}</Text>
                <Text style={{ color: T.textMuted, fontSize: 11 }}>
                  {autoFixResult.total_proposed ?? 0} proposed, {autoFixResult.total_applied ?? 0} applied, {autoFixResult.total_flagged ?? 0} flagged
                </Text>
              </View>
            </View>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
              {(autoFixResult.total_applied ?? 0) > 0 && (
                <View style={{ backgroundColor: (globalThis as any).__alphaColor(T.success, '20'), paddingHorizontal: 8, paddingVertical: 3, borderRadius: 6 }}>
                  <Text style={{ color: T.successText, fontSize: 10, fontWeight: '700' }} data-testid="autofix-applied-count" testID="autofix-applied-count">{autoFixResult.total_applied} applied</Text>
                </View>
              )}
              {(autoFixResult.total_flagged ?? 0) > 0 && (
                <View style={{ backgroundColor: (globalThis as any).__alphaColor(T.warning, '20'), paddingHorizontal: 8, paddingVertical: 3, borderRadius: 6 }}>
                  <Text style={{ color: T.warningText, fontSize: 10, fontWeight: '700' }} data-testid="autofix-flagged-count" testID="autofix-flagged-count">{autoFixResult.total_flagged} review</Text>
                </View>
              )}
              <Ionicons name={showFixLog ? 'chevron-up' : 'chevron-down'} size={16} color={T.textMuted} />
            </View>
          </TouchableOpacity>

          {showFixLog && (
            <View style={{ paddingHorizontal: 16, paddingBottom: 16, gap: 10 }}>
              {/* Confidence Threshold Badge */}
              {autoFixResult.confidence_threshold && (
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                  <Ionicons name="shield-checkmark" size={13} color={T.ai} />
                  <Text style={{ color: T.textMuted, fontSize: 10 }}>
                    Confidence threshold: {autoFixResult.confidence_threshold}% — Actions below this are flagged for manual review
                  </Text>
                </View>
              )}

              {/* Engine Summary */}
              <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginBottom: 4 }}>
                {Object.entries(autoFixResult.engine_results || {}).map(([name, r]: [string, any]) => {
                  const total = (r.applied ?? 0) + (r.flagged ?? 0);
                  return (
                    <View key={name} style={{ backgroundColor: total > 0 ? (globalThis as any).__alphaColor(T.success, '12') : T.bgSoft, borderRadius: 8, paddingHorizontal: 10, paddingVertical: 5, borderWidth: 1, borderColor: total > 0 ? (globalThis as any).__alphaColor(T.success, '25') : T.border }}>
                      <Text style={{ color: total > 0 ? T.success : T.textMuted, fontSize: 10, fontWeight: '700' }}>
                        {name}: {r.applied ?? 0}/{r.proposed ?? 0}
                      </Text>
                    </View>
                  );
                })}
              </View>

              {/* Applied Fixes */}
              {(autoFixResult.fixes || []).filter((f: any) => f.status === 'applied').length > 0 && (
                <View>
                  <Text style={{ color: T.successText, fontSize: 11, fontWeight: '800', marginBottom: 6 }}>{tx('admin.aiCommandCenterPanel.auto.text.031', 'Applied Automatically')}</Text>
                  {(autoFixResult.fixes || []).filter((f: any) => f.status === 'applied').map((fix: any, i: number) => (
                    <FixRow key={`applied-${i}`} fix={fix} type="applied" T={T} />
                  ))}
                </View>
              )}

              {/* Flagged for Review */}
              {(autoFixResult.fixes || []).filter((f: any) => f.status === 'flagged_for_review').length > 0 && (
                <View style={{ marginTop: 4 }}>
                  <Text style={{ color: T.warningText, fontSize: 11, fontWeight: '800', marginBottom: 6 }}>{tx('admin.aiCommandCenterPanel.auto.text.032', 'Flagged for Manual Review')}</Text>
                  {(autoFixResult.fixes || []).filter((f: any) => f.status === 'flagged_for_review').map((fix: any, i: number) => (
                    <FixRow key={`flagged-${i}`} fix={fix} type="flagged" T={T} />
                  ))}
                </View>
              )}

              {/* All Healthy */}
              {(autoFixResult.fixes || []).every((f: any) => f.status === 'skipped') && (
                <View style={{ alignItems: 'center', paddingVertical: 12 }}>
                  <Ionicons name="checkmark-circle" size={28} color={T.successText} />
                  <Text style={{ color: T.successText, fontSize: 13, fontWeight: '700', marginTop: 6 }}>{tx('admin.aiCommandCenterPanel.auto.text.033', 'All Systems Healthy')}</Text>
                  <Text style={{ color: T.textMuted, fontSize: 11 }}>{tx('admin.aiCommandCenterPanel.auto.text.034', 'No issues detected — nothing to fix')}</Text>
                </View>
              )}

              {autoFixResult.run_at && (
                <Text style={{ color: T.textMuted, fontSize: 9, textAlign: 'center', marginTop: 6 }}>{t("autofix.last.run")} {new Date(autoFixResult.run_at).toLocaleString()}</Text>
              )}
            </View>
          )}
        </View>
      )}

      {/* Manual Review Queue */}
      {reviewQueue.length > 0 && (
        <View style={{ backgroundColor: T.card, borderRadius: 16, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(T.warning, '30'), padding: 16, gap: 10 }} data-testid="ai-review-queue" testID="ai-review-queue">
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 4 }}>
            <View style={{ width: 32, height: 32, borderRadius: 10, backgroundColor: (globalThis as any).__alphaColor(T.warning, '20'), alignItems: 'center', justifyContent: 'center' }}>
              <Ionicons name="eye" size={16} color={T.warningText} />
            </View>
            <View style={{ flex: 1 }}>
              <Text style={{ color: T.text, fontSize: 14, fontWeight: '700' }}>{tx('admin.aiCommandCenterPanel.auto.text.035', 'Manual Review Queue')}</Text>
              <Text style={{ color: T.textMuted, fontSize: 11 }}>{reviewQueue.length} item(s) need your approval</Text>
            </View>
          </View>
          {reviewFeedback.message ? (
            <View
              style={{
                backgroundColor: reviewFeedback.type === 'error' ? T.errorSoft : T.successSoft,
                borderRadius: 10,
                borderWidth: 1,
                borderColor: reviewFeedback.type === 'error' ? (globalThis as any).__alphaColor(T.error, '35') : T.success + '35',
                paddingHorizontal: 12,
                paddingVertical: 10,
              }}
              data-testid="ai-review-queue-feedback" testID="ai-review-queue-feedback"
            >
              <Text style={{ color: reviewFeedback.type === 'error' ? T.error : T.success, fontSize: 11, fontWeight: '700' }}>{reviewFeedback.message}</Text>
            </View>
          ) : null}
          {reviewQueue.map((item: any, index: number) => {
            const conf = item.confidence ?? 0;
            const confColor = conf >= 80 ? T.success : conf >= 50 ? T.warning : T.error;
            const rowId = `${item.action_id}-${index}`;
            const isApproving = reviewActionState.actionId === item.action_id && reviewActionState.mode === 'approve';
            const isDismissing = reviewActionState.actionId === item.action_id && reviewActionState.mode === 'dismiss';
            const isActing = isApproving || isDismissing;
            return (
              <View key={rowId} style={{ backgroundColor: T.bgSoft, borderRadius: 12, padding: 12, borderWidth: 1, borderColor: T.border }} data-testid={`review-item-${rowId}`} testID={`review-item-${rowId}`}>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 6 }}>
                  <Text style={{ color: T.ai, fontSize: 10, fontWeight: '700' }}>{item.engine}</Text>
                  <Text style={{ color: T.textMuted, fontSize: 10 }}>{item.action}</Text>
                  <View style={{ marginLeft: 'auto' as any, flexDirection: 'row', gap: 4 }}>
                    <View style={{ backgroundColor: (globalThis as any).__alphaColor(confColor, '18'), paddingHorizontal: 6, paddingVertical: 2, borderRadius: 4 }}>
                      <Text style={{ color: confColor, fontSize: 9, fontWeight: '800' }}>{conf}% confidence</Text>
                    </View>
                    {item.risk && item.risk !== 'none' && (
                      <View style={{ backgroundColor: (globalThis as any).__alphaColor(T.warning, '18'), paddingHorizontal: 5, paddingVertical: 2, borderRadius: 4 }}>
                        <Text style={{ color: T.warningText, fontSize: 8, fontWeight: '700' }}>{item.risk} risk</Text>
                      </View>
                    )}
                  </View>
                </View>
                <Text style={{ color: T.textSec, fontSize: 11, marginBottom: 4 }}>{item.details}</Text>
                {item.reasoning && <Text style={{ color: T.textMuted, fontSize: 10, fontStyle: 'italic', marginBottom: 8 }}>{item.reasoning}</Text>}
                <View style={{ flexDirection: 'row', gap: 8 }}>
                  <TouchableOpacity onPress={() => approveReviewItem(item.action_id)} disabled={isActing} style={{ backgroundColor: isActing ? (globalThis as any).__alphaColor(T.success, '80') : T.success, paddingHorizontal: 14, paddingVertical: 7, borderRadius: 8, flexDirection: 'row', alignItems: 'center', gap: 4 }} data-testid={`approve-${rowId}`} testID={`approve-${rowId}`}>
                    {isApproving ? <ActivityIndicator size="small" color={T.primaryText} /> : <Ionicons name="checkmark" size={12} color={T.primaryText} />}
                    <Text style={{ color: T.primaryText, fontSize: 11, fontWeight: '700' }}>{isApproving ? 'Approving...' : 'Approve'}</Text>
                  </TouchableOpacity>
                  <TouchableOpacity onPress={() => dismissReviewItem(item.action_id)} disabled={isActing} style={{ backgroundColor: (globalThis as any).__alphaColor(T.error, '20'), opacity: isActing ? 0.7 : 1, paddingHorizontal: 14, paddingVertical: 7, borderRadius: 8, flexDirection: 'row', alignItems: 'center', gap: 4 }} data-testid={`dismiss-${rowId}`} testID={`dismiss-${rowId}`}>
                    {isDismissing ? <ActivityIndicator size="small" color={T.error} /> : <Ionicons name="close" size={12} color={T.error} />}
                    <Text style={{ color: T.error, fontSize: 11, fontWeight: '700' }}>{isDismissing ? 'Dismissing...' : 'Dismiss'}</Text>
                  </TouchableOpacity>
                </View>
              </View>
            );
          })}
        </View>
      )}

      {/* Reset Button for Testing */}
      <View style={{ flexDirection: 'row', justifyContent: 'center', gap: 10 }}>
        <TouchableOpacity onPress={resetAutoFix} disabled={resetting || autoFixRunning} style={{ backgroundColor: (globalThis as any).__alphaColor(T.error, '15'), paddingHorizontal: 16, paddingVertical: 8, borderRadius: 10, flexDirection: 'row', alignItems: 'center', gap: 6, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(T.error, '30') }} data-testid="ai-autofix-reset-btn" testID="ai-autofix-reset-btn">
          {resetting ? <ActivityIndicator size="small" color={T.error} /> : <Ionicons name="refresh" size={13} color={T.error} />}
          <Text style={{ color: T.error, fontSize: 11, fontWeight: '700' }}>{resetting ? 'Resetting...' : 'Reset & Re-scan'}</Text>
        </TouchableOpacity>
      </View>

      {/* Feature 1: Configurable Confidence Threshold + Feature 2: Export */}
      <View style={{ backgroundColor: T.card, borderRadius: 16, borderWidth: 1, borderColor: T.border, padding: 16, gap: 12 }} data-testid="ai-autofix-config-section" testID="ai-autofix-config-section">
        <TouchableOpacity accessibilityLabel={tx('admin.aiCommandCenterPanel.auto.accessibility.002', 'Auto-Fix Settings & Export')} onPress={() => setShowConfig(!showConfig)} style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
            <View style={{ width: 32, height: 32, borderRadius: 10, backgroundColor: (globalThis as any).__alphaColor(T.ai, '20'), alignItems: 'center', justifyContent: 'center' }}>
              <Ionicons name="settings" size={16} color={T.ai} />
            </View>
            <View>
              <Text style={{ color: T.text, fontSize: 14, fontWeight: '700' }}>{tx('admin.aiCommandCenterPanel.auto.text.036', 'Auto-Fix Settings & Export')}</Text>
              <Text style={{ color: T.textMuted, fontSize: 11 }}>Threshold: {afConfig.confidence_threshold}% | Interval: {afConfig.run_interval_minutes}m</Text>
            </View>
          </View>
          <Ionicons name={showConfig ? 'chevron-up' : 'chevron-down'} size={16} color={T.textMuted} />
        </TouchableOpacity>

        {showConfig && (
          <View style={{ gap: 12 }}>
            {/* Confidence Threshold Slider */}
            <View style={{ gap: 6 }}>
              <Text style={{ color: T.textSec, fontSize: 12, fontWeight: '600' }}>Confidence Threshold: {afConfig.confidence_threshold}%</Text>
              <Text style={{ color: T.textMuted, fontSize: 10 }}>{tx('admin.aiCommandCenterPanel.auto.text.037', 'Actions below this threshold are flagged for manual review')}</Text>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                {[50, 60, 70, 75, 80, 85, 90, 95].map(val => (
                  <TouchableOpacity key={val} onPress={() => setAfConfig((p: any) => ({ ...p, confidence_threshold: val }))} style={{ backgroundColor: afConfig.confidence_threshold === val ? T.ai : T.bgSoft, paddingHorizontal: 10, paddingVertical: 5, borderRadius: 8, borderWidth: 1, borderColor: afConfig.confidence_threshold === val ? T.ai : T.border }} data-testid={`threshold-${val}`} testID={`threshold-${val}`}>
                    <Text style={{ color: afConfig.confidence_threshold === val ? T.primaryText : T.textMuted, fontSize: 11, fontWeight: '700' }}>{val}%</Text>
                  </TouchableOpacity>
                ))}
              </View>
            </View>

            {/* Auto-run toggle */}
            <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
              <Text style={{ color: T.textSec, fontSize: 12 }}>{tx('admin.aiCommandCenterPanel.auto.text.038', 'Auto-run enabled')}</Text>
              <Switch value={afConfig.auto_run_enabled} onValueChange={(v: boolean) => setAfConfig((p: any) => ({ ...p, auto_run_enabled: v }))} trackColor={{ false: 'var(--app-text-muted)', true: T.ai }} data-testid="autorun-toggle" testID="autorun-toggle" />
            </View>

            {/* Save button */}
            <TouchableOpacity onPress={saveConfig} disabled={savingConfig} style={{ backgroundColor: T.ai, paddingVertical: 10, borderRadius: 10, alignItems: 'center', flexDirection: 'row', justifyContent: 'center', gap: 6 }} data-testid="save-config-btn" testID="save-config-btn">
              {savingConfig ? <ActivityIndicator size="small" color={T.primaryText} /> : <Ionicons name="checkmark-circle" size={16} color={T.primaryText} />}
              <Text style={{ color: T.primaryText, fontSize: 13, fontWeight: '700' }}>{savingConfig ? 'Saving...' : 'Save Configuration'}</Text>
            </TouchableOpacity>

            {/* Export Buttons */}
            <View style={{ flexDirection: 'row', gap: 8 }}>
              <TouchableOpacity onPress={() => exportAudit('csv')} disabled={exporting === 'csv'} style={{ flex: 1, backgroundColor: (globalThis as any).__alphaColor(T.success, '15'), paddingVertical: 10, borderRadius: 10, alignItems: 'center', flexDirection: 'row', justifyContent: 'center', gap: 6, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(T.success, '30') }} data-testid="export-csv-btn" testID="export-csv-btn">
                {exporting === 'csv' ? <ActivityIndicator size="small" color={T.successText} /> : <Ionicons name="document-text" size={14} color={T.successText} />}
                <Text style={{ color: T.successText, fontSize: 12, fontWeight: '700' }}>{t("paymentsTax.header.exportCsv")}</Text>
              </TouchableOpacity>
              <TouchableOpacity onPress={() => exportAudit('pdf')} disabled={exporting === 'pdf'} style={{ flex: 1, backgroundColor: (globalThis as any).__alphaColor(colors.primary, '15'), paddingVertical: 10, borderRadius: 10, alignItems: 'center', flexDirection: 'row', justifyContent: 'center', gap: 6, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(colors.primary, '30') }} data-testid="export-pdf-btn" testID="export-pdf-btn">
                {exporting === 'pdf' ? <ActivityIndicator size="small" color={'var(--app-primary)'} /> : <Ionicons name="document" size={14} color={'var(--app-primary)'} />}
                <Text style={{ color: colors.primary, fontSize: 12, fontWeight: '700' }}>{tx('admin.aiCommandCenterPanel.auto.text.039', 'Export Report')}</Text>
              </TouchableOpacity>
            </View>
          </View>
        )}
      </View>

      {/* Feature 3: Performance Budget Dashboard */}
      <View style={{ backgroundColor: T.card, borderRadius: 16, borderWidth: 1, borderColor: T.border, padding: 16, gap: 12 }} data-testid="performance-budget-section" testID="performance-budget-section">
        <TouchableOpacity accessibilityLabel={tx('admin.aiCommandCenterPanel.auto.accessibility.003', 'Performance Budgets')} onPress={() => setShowBudgets(!showBudgets)} style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
            <View style={{ width: 32, height: 32, borderRadius: 10, backgroundColor: (globalThis as any).__alphaColor(colors.warning, '20'), alignItems: 'center', justifyContent: 'center' }}>
              <Ionicons name="speedometer" size={16} color={'var(--app-warning)'} />
            </View>
            <View>
              <Text style={{ color: T.text, fontSize: 14, fontWeight: '700' }}>{tx('admin.aiCommandCenterPanel.auto.text.040', 'Performance Budgets')}</Text>
              <Text style={{ color: T.textMuted, fontSize: 11 }}>
                {budgets.length} budget{budgets.length !== 1 ? 's' : ''} | {violations.filter(v => v.status === 'violation').length} violation{violations.filter(v => v.status === 'violation').length !== 1 ? 's' : ''}
              </Text>
            </View>
          </View>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
            {violations.filter(v => v.status === 'insufficient_data').length > 0 && (
              <View style={{ backgroundColor: (globalThis as any).__alphaColor(T.warning, '18'), paddingHorizontal: 8, paddingVertical: 3, borderRadius: 6 }}>
                <Text style={{ color: T.warningText, fontSize: 10, fontWeight: '700' }}>{violations.filter(v => v.status === 'insufficient_data').length} cold</Text>
              </View>
            )}
            {violations.filter(v => v.coverage_alert).length > 0 && (
              <View style={{ backgroundColor: (globalThis as any).__alphaColor(T.error, '20'), paddingHorizontal: 8, paddingVertical: 3, borderRadius: 6 }}>
                <Text style={{ color: T.error, fontSize: 10, fontWeight: '700' }}>{violations.filter(v => v.coverage_alert).length} stale</Text>
              </View>
            )}
            {violations.filter(v => v.status === 'violation').length > 0 && (
              <View style={{ backgroundColor: (globalThis as any).__alphaColor(T.error, '20'), paddingHorizontal: 8, paddingVertical: 3, borderRadius: 6 }}>
                <Text style={{ color: T.error, fontSize: 10, fontWeight: '700' }}>{violations.filter(v => v.status === 'violation').length} over</Text>
              </View>
            )}
            <Ionicons name={showBudgets ? 'chevron-up' : 'chevron-down'} size={16} color={T.textMuted} />
          </View>
        </TouchableOpacity>

        {showBudgets && (
          <View style={{ gap: 10 }}>
            {violations.filter(v => v.coverage_alert).length > 0 && (
              <View style={{ backgroundColor: (globalThis as any).__alphaColor(T.error, '10'), borderWidth: 1, borderColor: (globalThis as any).__alphaColor(T.error, '35'), borderRadius: 10, padding: 12 }} data-testid="budget-coverage-alert-banner" testID="budget-coverage-alert-banner">
                <Text style={{ color: T.error, fontSize: 12, fontWeight: '800' }}>{tx('admin.aiCommandCenterPanel.auto.text.041', 'Coverage alert')}</Text>
                <Text style={{ color: T.textSec, fontSize: 11, marginTop: 4, lineHeight: 17 }}>{tx('admin.aiCommandCenterPanel.auto.text.042', 'Some protected routes have stayed in low-sample coverage too long. Open those flows to warm telemetry before the gate starts treating them as stale coverage risk.')}</Text>
              </View>
            )}

            {/* Violations List */}
            {violations.map((v: any, i: number) => {
              const isOver = v.status === 'violation';
              const isCoverageWarm = v.status === 'warmup_covered';
              const isInsufficient = v.status === 'insufficient_data';
              const cardBg = isOver ? T.error + '08' : isCoverageWarm ? T.cyan + '08' : isInsufficient ? T.warning + '08' : T.success + '08';
              const cardBorder = isOver ? T.error + '20' : isCoverageWarm ? T.cyan + '25' : isInsufficient ? T.warning + '20' : T.success + '20';
              const iconName = isOver ? 'alert-circle' : isCoverageWarm ? 'flash' : isInsufficient ? 'hourglass' : 'checkmark-circle';
              const iconColor = isOver ? T.error : isCoverageWarm ? T.cyan : isInsufficient ? T.warning : T.success;
              return (
                <View key={i} style={{ backgroundColor: cardBg, borderRadius: 10, padding: 10, borderWidth: 1, borderColor: cardBorder }} data-testid={`budget-violation-${v.route}`} testID={`budget-violation-${v.route}`}>
                  <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 6 }}>
                    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                      <Ionicons name={iconName as any} size={14} color={iconColor} />
                      <Text style={{ color: T.text, fontSize: 12, fontWeight: '700' }}>{v.label || v.route}</Text>
                    </View>
                    {v.route !== '*' && (
                      <TouchableOpacity onPress={() => deleteBudget(v.route)} style={{ padding: 4 }} data-testid={`delete-budget-${v.route}`} testID={`delete-budget-${v.route}`}>
                        <Ionicons name="trash" size={12} color={T.error} />
                      </TouchableOpacity>
                    )}
                  </View>
                  <View style={{ flexDirection: 'row', gap: 12 }}>
                    <View style={{ flex: 1 }}>
                      <Text style={{ color: T.textMuted, fontSize: 9, fontWeight: '600' }}>{tx('admin.aiCommandCenterPanel.auto.text.043', 'LCP')}</Text>
                      <Text style={{ color: v.lcp_over > 0 ? T.error : T.success, fontSize: 11, fontWeight: '700' }}>{v.lcp_actual_ms}{t("autofix.ms")}{v.lcp_budget_ms}ms</Text>
                      {v.lcp_over > 0 && <Text style={{ color: T.error, fontSize: 9 }}>+{v.lcp_over}{t("autofix.ms.over")}</Text>}
                    </View>
                    <View style={{ flex: 1 }}>
                      <Text style={{ color: T.textMuted, fontSize: 9, fontWeight: '600' }}>{tx('admin.aiCommandCenterPanel.auto.text.044', 'FCP')}</Text>
                      <Text style={{ color: v.fcp_over > 0 ? T.error : T.success, fontSize: 11, fontWeight: '700' }}>{v.fcp_actual_ms}{t("autofix.ms")}{v.fcp_budget_ms}ms</Text>
                      {v.fcp_over > 0 && <Text style={{ color: T.error, fontSize: 9 }}>+{v.fcp_over}{t("autofix.ms.over")}</Text>}
                    </View>
                    <View style={{ flex: 1 }}>
                      <Text style={{ color: T.textMuted, fontSize: 9, fontWeight: '600' }}>{tx('admin.aiCommandCenterPanel.auto.text.045', 'TTFB')}</Text>
                      <Text style={{ color: v.ttfb_over > 0 ? T.error : T.success, fontSize: 11, fontWeight: '700' }}>{v.ttfb_actual_ms}{t("autofix.ms")}{v.ttfb_budget_ms}ms</Text>
                      {v.ttfb_over > 0 && <Text style={{ color: T.error, fontSize: 9 }}>+{v.ttfb_over}{t("autofix.ms.over")}</Text>}
                    </View>
                  </View>
                  {(isCoverageWarm || isInsufficient) && (
                    <View style={{ marginTop: 8, gap: 3 }}>
                      <Text style={{ color: iconColor, fontSize: 10, fontWeight: '700' }}>
                        {isCoverageWarm ? 'Warm-up coverage active' : 'Insufficient coverage'}
                      </Text>
                      <Text style={{ color: T.textMuted, fontSize: 10, lineHeight: 15 }}>
                        {v.warmup_page_avg_ms
                          ? `Using page-performance warm-up (${v.warmup_page_avg_ms}ms avg) while waiting for ${v.min_samples_required} full vitals samples.`
                          : `Waiting for ${v.min_samples_required} full vitals samples. Coverage status: ${v.coverage_status}.`}
                      </Text>
                    </View>
                  )}
                  {v.coverage_alert && (
                    <Text style={{ color: T.error, fontSize: 10, fontWeight: '700', marginTop: 6 }}>{tx('admin.aiCommandCenterPanel.auto.text.046', 'Coverage has been insufficient longer than the configured alert window.')}</Text>
                  )}
                </View>
              );
            })}

            {/* Add Budget Form */}
            <View style={{ backgroundColor: T.bgSoft, borderRadius: 10, padding: 10, gap: 8, borderWidth: 1, borderColor: T.border }}>
              <Text style={{ color: T.textSec, fontSize: 11, fontWeight: '700' }}>{tx('admin.aiCommandCenterPanel.auto.text.047', 'Add Performance Budget')}</Text>
              <View style={{ flexDirection: 'row', gap: 8 }}>
                <TextInput value={newBudget.route} onChangeText={(t: string) => setNewBudget(p => ({ ...p, route: t }))} placeholder={tx('admin.aiCommandCenterPanel.auto.placeholder.001', 'Route (e.g. /pricing)')} placeholderTextColor={T.textMuted} style={{ flex: 2, backgroundColor: T.card, borderRadius: 8, padding: 8, borderWidth: 1, borderColor: T.border, color: T.text, fontSize: 11 }} data-testid="new-budget-route" testID="new-budget-route" />
                <TextInput value={newBudget.label} onChangeText={(t: string) => setNewBudget(p => ({ ...p, label: t }))} placeholder={tx('admin.aiCommandCenterPanel.auto.placeholder.002', 'Label')} placeholderTextColor={T.textMuted} style={{ flex: 1, backgroundColor: T.card, borderRadius: 8, padding: 8, borderWidth: 1, borderColor: T.border, color: T.text, fontSize: 11 }} data-testid="new-budget-label" testID="new-budget-label" />
              </View>
              <View style={{ flexDirection: 'row', gap: 8 }}>
                <View style={{ flex: 1 }}>
                  <Text style={{ color: T.textMuted, fontSize: 9 }}>{tx('admin.aiCommandCenterPanel.auto.text.048', 'LCP (ms)')}</Text>
                  <TextInput value={newBudget.lcp_budget_ms} accessibilityLabel={tx('admin.aiCommandCenterPanel.auto.accessibility.004', 'FCP (ms)')} onChangeText={(t: string) => setNewBudget(p => ({ ...p, lcp_budget_ms: t }))} keyboardType="numeric" style={{ backgroundColor: T.card, borderRadius: 8, padding: 8, borderWidth: 1, borderColor: T.border, color: T.text, fontSize: 11 }} data-testid="new-budget-lcp" testID="new-budget-lcp" />
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={{ color: T.textMuted, fontSize: 9 }}>{tx('admin.aiCommandCenterPanel.auto.text.049', 'FCP (ms)')}</Text>
                  <TextInput value={newBudget.fcp_budget_ms} accessibilityLabel={tx('admin.aiCommandCenterPanel.auto.accessibility.005', 'TTFB (ms)')} onChangeText={(t: string) => setNewBudget(p => ({ ...p, fcp_budget_ms: t }))} keyboardType="numeric" style={{ backgroundColor: T.card, borderRadius: 8, padding: 8, borderWidth: 1, borderColor: T.border, color: T.text, fontSize: 11 }} data-testid="new-budget-fcp" testID="new-budget-fcp" />
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={{ color: T.textMuted, fontSize: 9 }}>{tx('admin.aiCommandCenterPanel.auto.text.050', 'TTFB (ms)')}</Text>
                  <TextInput value={newBudget.ttfb_budget_ms} accessibilityLabel={tx('admin.aiCommandCenterPanel.auto.accessibility.006', 'Add Budget')} onChangeText={(t: string) => setNewBudget(p => ({ ...p, ttfb_budget_ms: t }))} keyboardType="numeric" style={{ backgroundColor: T.card, borderRadius: 8, padding: 8, borderWidth: 1, borderColor: T.border, color: T.text, fontSize: 11 }} data-testid="new-budget-ttfb" testID="new-budget-ttfb" />
                </View>
              </View>
              <TouchableOpacity onPress={addBudget} style={{ backgroundColor: colors.warning, paddingVertical: 8, borderRadius: 8, alignItems: 'center', flexDirection: 'row', justifyContent: 'center', gap: 6 }} data-testid="add-budget-btn" testID="add-budget-btn">
                <Ionicons name="add-circle" size={14} color={T.primaryText} />
                <Text style={{ color: T.primaryText, fontSize: 12, fontWeight: '700' }}>{tx('admin.aiCommandCenterPanel.auto.text.051', 'Add Budget')}</Text>
              </TouchableOpacity>
            </View>
          </View>
        )}
      </View>

      {/* Weekly Digest Settings */}
      <WeeklyDigestSettings />

      {/* Footer */}
      <View style={{ backgroundColor: T.bgSoft, borderRadius: 14, padding: 16, borderWidth: 1, borderColor: T.border, flexDirection: 'row', alignItems: 'center', gap: 12 }} data-testid="ai-cc-footer" testID="ai-cc-footer">
        <Ionicons name="information-circle" size={18} color={T.ai} />
        <Text style={{ color: T.textSec, fontSize: 11, flex: 1, lineHeight: 16 }}>{tx('admin.aiCommandCenterPanel.auto.text.052', 'All insights are powered by GPT-4o. Analyses are cached for 1 hour. Use "Run All" to refresh all 8 engines simultaneously. Click "View Panel" to jump to the detailed panel for each insight.')}</Text>
      </View>

      <View style={{ height: 32 }} />
    </ScrollView>
  );
}

function FixRow({ fix, type, T }: { fix: any; type: 'applied' | 'flagged'; T: any }) {
  const isApplied = type === 'applied';
  const iconColor = isApplied ? T.success : T.warning;
  const iconName = isApplied ? 'checkmark-circle' : 'alert-circle';
  const conf = fix.confidence ?? 0;
  const confColor = conf >= 80 ? T.success : conf >= 50 ? T.warning : T.error;

  return (
    <View style={{ flexDirection: 'row', gap: 8, paddingVertical: 8, borderBottomWidth: 1, borderBottomColor: (globalThis as any).__alphaColor(T.border, '40') }} data-testid={`fix-row-${fix.action_id || fix.action}`} testID={`fix-row-${fix.action_id || fix.action}`}>
      <View style={{ width: 22, height: 22, borderRadius: 11, backgroundColor: (globalThis as any).__alphaColor(iconColor, '20'), alignItems: 'center', justifyContent: 'center', marginTop: 1, flexShrink: 0 }}>
        <Ionicons name={iconName as any} size={13} color={iconColor} />
      </View>
      <View style={{ flex: 1 }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 3 }}>
          <Text style={{ color: T.ai, fontSize: 9, fontWeight: '700' }}>{fix.engine}</Text>
          <Text style={{ color: T.textMuted, fontSize: 9 }}>{fix.action}</Text>
          <View style={{ marginLeft: 'auto' as any, flexDirection: 'row', alignItems: 'center', gap: 4 }}>
            <View style={{ backgroundColor: (globalThis as any).__alphaColor(confColor, '18'), paddingHorizontal: 6, paddingVertical: 2, borderRadius: 4 }}>
              <Text style={{ color: confColor, fontSize: 9, fontWeight: '800' }}>{conf}%</Text>
            </View>
            {fix.risk && fix.risk !== 'none' && (
              <View style={{ backgroundColor: (globalThis as any).__alphaColor((fix.risk === 'high' ? T.error : fix.risk === 'medium' ? T.warning : T.success), '18'), paddingHorizontal: 5, paddingVertical: 2, borderRadius: 4 }}>
                <Text style={{ color: fix.risk === 'high' ? T.error : fix.risk === 'medium' ? T.warning : T.success, fontSize: 8, fontWeight: '700' }}>{fix.risk}</Text>
              </View>
            )}
          </View>
        </View>
        <Text style={{ color: T.textSec, fontSize: 11, lineHeight: 16 }}>{fix.details}</Text>
        {fix.reasoning && (
          <Text style={{ color: T.textMuted, fontSize: 10, fontStyle: 'italic', marginTop: 3, lineHeight: 14 }}>{fix.reasoning}</Text>
        )}
      </View>
    </View>
  );
}

function getAge(isoDate: string): string {
  const ms = Date.now() - new Date(isoDate).getTime();
  const mins = Math.floor(ms / 60000);
  if (mins < 1) return 'Just now';
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

const DAYS = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday'];
// eslint-disable-next-line @typescript-eslint/no-unused-vars
const _HOURS = Array.from({ length: 24 }, (_, i) => i);

function WeeklyDigestSettings() {
  const AC = useAdminTheme();
  const T = React.useMemo(() => makeT(AC), [AC]);
  const [show, setShow] = useState(false);
  const [config, setConfig] = useState<any>(null);
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const [saving, setSaving] = useState(false);
  const [sending, setSending] = useState(false);
  const [sendResult, setSendResult] = useState('');

  const loadConfig = useCallback(async () => {
    try {
      const res = await api.get('/admin/ai-insights/health-digest/config');
      setConfig(res.data);
    } catch (error) { handleAppRecoverableError({ scope: 'src/components/admin/AICommandCenterPanel.tsx#catch19', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
  }, []);

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { loadConfig(); }, []);

  const saveConfig = async (updates: any) => {
    setSaving(true);
    try {
      const res = await api.put('/admin/ai-insights/health-digest/config', { ...config, ...updates });
      setConfig({ ...config, ...res.data });
    } catch (error) { handleAppRecoverableError({ scope: 'src/components/admin/AICommandCenterPanel.tsx#catch20', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
    setSaving(false);
  };

  const sendNow = async () => {
    setSending(true);
    setSendResult('');
    try {
      const res = await api.post('/admin/ai-insights/health-digest/send-now');
      setSendResult(res.data?.sent ? `Sent to ${res.data.recipients?.length || 0} admin(s) — Score: ${res.data.platform_score}/100` : (res.data?.reason || 'Failed'));
      loadConfig();
    } catch { setSendResult('Failed to send'); }
    setSending(false);
  };

  if (!config) return null;

  return (
    <View style={{ backgroundColor: T.card, borderRadius: 16, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(T.ai, '25'), overflow: 'hidden' }} data-testid="ai-digest-settings" testID="ai-digest-settings">
      <TouchableOpacity accessibilityLabel={tx('admin.aiCommandCenterPanel.auto.accessibility.007', 'Weekly AI Health Digest')} onPress={() => setShow(!show)} style={{ padding: 16, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
          <View style={{ width: 32, height: 32, borderRadius: 10, backgroundColor: (globalThis as any).__alphaColor(T.ai, '20'), alignItems: 'center', justifyContent: 'center' }}>
            <Ionicons name="mail" size={16} color={T.ai} />
          </View>
          <View>
            <Text style={{ color: T.text, fontSize: 14, fontWeight: '700' }}>{tx('admin.aiCommandCenterPanel.auto.text.053', 'Weekly AI Health Digest')}</Text>
            <Text style={{ color: T.textMuted, fontSize: 11 }}>
              {config.enabled ? `Sends every ${config.day} at ${config.hour}:00 UTC` : 'Disabled'}
            </Text>
          </View>
        </View>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
          <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: config.enabled ? T.success : T.error }} />
          <Ionicons name={show ? 'chevron-up' : 'chevron-down'} size={16} color={T.textMuted} />
        </View>
      </TouchableOpacity>

      {show && (
        <View style={{ padding: 16, paddingTop: 0, gap: 14 }}>
          {/* Enable/Disable */}
          <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
            <Text style={{ color: T.textSec, fontSize: 12 }}>{tx('admin.aiCommandCenterPanel.auto.text.054', 'Enabled')}</Text>
            <TouchableOpacity onPress={() => saveConfig({ enabled: !config.enabled })} style={{ width: 44, height: 24, borderRadius: 12, backgroundColor: config.enabled ? T.success : T.border, justifyContent: 'center', padding: 2 }} data-testid="ai-digest-toggle" testID="ai-digest-toggle">
              <View style={{ width: 20, height: 20, borderRadius: 10, backgroundColor: T.primaryText, alignSelf: config.enabled ? 'flex-end' as any : 'flex-start' as any }} />
            </TouchableOpacity>
          </View>

          {/* Day Selector */}
          <View>
            <Text style={{ color: T.textSec, fontSize: 11, marginBottom: 6, fontWeight: '600' }}>{tx('admin.aiCommandCenterPanel.auto.text.055', 'Send Day')}</Text>
            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6 }}>
              {DAYS.map(d => (
                <TouchableOpacity key={d} onPress={() => saveConfig({ day: d })} style={{ paddingHorizontal: 10, paddingVertical: 5, borderRadius: 8, backgroundColor: config.day === d ? T.ai : T.bgSoft, borderWidth: 1, borderColor: config.day === d ? T.ai : T.border }} data-testid={`ai-digest-day-${d}`} testID={`ai-digest-day-${d}`}>
                  <Text style={{ color: config.day === d ? T.primaryText : T.textMuted, fontSize: 10, fontWeight: '700', textTransform: 'capitalize' }}>{d.slice(0, 3)}</Text>
                </TouchableOpacity>
              ))}
            </View>
          </View>

          {/* Hour Selector */}
          <View>
            <Text style={{ color: T.textSec, fontSize: 11, marginBottom: 6, fontWeight: '600' }}>{tx('admin.aiCommandCenterPanel.auto.text.056', 'Send Hour (UTC)')}</Text>
            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 4 }}>
              {[6, 7, 8, 9, 10, 11, 12, 14, 16, 18].map(h => (
                <TouchableOpacity key={h} onPress={() => saveConfig({ hour: h })} style={{ paddingHorizontal: 8, paddingVertical: 4, borderRadius: 6, backgroundColor: config.hour === h ? T.ai : T.bgSoft, borderWidth: 1, borderColor: config.hour === h ? T.ai : T.border }} data-testid={`ai-digest-hour-${h}`} testID={`ai-digest-hour-${h}`}>
                  <Text style={{ color: config.hour === h ? T.primaryText : T.textMuted, fontSize: 10, fontWeight: '700' }}>{h}:00</Text>
                </TouchableOpacity>
              ))}
            </View>
          </View>

          {/* Send Now */}
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 12 }}>
            <TouchableOpacity onPress={sendNow} disabled={sending} style={{ backgroundColor: T.ai, paddingHorizontal: 16, paddingVertical: 10, borderRadius: 10, flexDirection: 'row', alignItems: 'center', gap: 6 }} data-testid="ai-digest-send-now-btn" testID="ai-digest-send-now-btn">
              {sending ? <ActivityIndicator size="small" color={T.primaryText} /> : <Ionicons name="send" size={14} color={T.primaryText} />}
              <Text style={{ color: T.primaryText, fontWeight: '700', fontSize: 12 }}>{sending ? 'Sending...' : 'Send Now'}</Text>
            </TouchableOpacity>
            {sendResult ? <Text style={{ color: T.successText, fontSize: 11, flex: 1 }}>{sendResult}</Text> : null}
          </View>

          {/* Last Sent */}
          {config.last_sent && (
            <Text style={{ color: T.textMuted, fontSize: 10 }}>Last sent: {new Date(config.last_sent).toLocaleString()}</Text>
          )}
        </View>
      )}
    </View>
  );
}
