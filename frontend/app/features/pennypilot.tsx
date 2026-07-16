import React, { useEffect, useMemo, useState } from 'react';
import { View, Text, ScrollView, TouchableOpacity, TextInput, ActivityIndicator, Alert } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../src/services/api';
import FeatureLayout from '../../src/components/FeatureLayout';
import MarkdownDisplay from '../../src/components/MarkdownDisplay';
import { useTheme } from '../../src/context/ThemeContext';
import FeatureToolbar from '../../src/components/FeatureToolbar';
import AIFeedbackBar from '../../src/components/AIFeedbackBar';
import { useFeatureDraft } from '../../src/hooks/useFeatureDraft';
import { useTranslation } from '../../src/hooks/useTranslation';
import { useAuth } from '../../src/context/AuthContext';
import { handleAppRecoverableError } from '../../src/utils/appRecoverableError';

const GUEST_FALLBACK_ID = `user_${Math.random().toString(36).slice(2)}${Date.now().toString(36)}`.slice(0, 78);

export default function PennyPilotScreen() {
  const { colors } = useTheme();
  const { user } = useAuth();
  const { t } = useTranslation();
  const [advisorQuery, setAdvisorQuery] = useFeatureDraft('pennypilot');

  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [errorText, setErrorText] = useState('');

  const [bootstrap, setBootstrap] = useState(null);
  const [profile, setProfile] = useState(null);
  const [budgets, setBudgets] = useState([]);
  const [expenses, setExpenses] = useState([]);
  const [goals, setGoals] = useState([]);
  const [billReminders, setBillReminders] = useState([]);
  const [positions, setPositions] = useState([]);
  const [expenseAnalytics, setExpenseAnalytics] = useState(null);
  const [portfolioAnalytics, setPortfolioAnalytics] = useState(null);

  const [advisorResult, setAdvisorResult] = useState('');
  const [receiptBase64, setReceiptBase64] = useState('');
  const [receiptResult, setReceiptResult] = useState(null);

  const [stockSymbol, setStockSymbol] = useState('AAPL');
  const [stockData, setStockData] = useState(null);
  const [stockLoading, setStockLoading] = useState(false);
  const [cryptoData, setCryptoData] = useState(null);

  const [profileForm, setProfileForm] = useState({
    currency: 'USD',
    monthly_income: '',
    fixed_monthly_expenses: '',
    savings_target_monthly: '',
    risk_tolerance: 'moderate',
  });

  const [budgetForm, setBudgetForm] = useState({ name: '', category: 'general', monthly_limit: '' });
  const [expenseForm, setExpenseForm] = useState({ amount: '', category: 'general', merchant: '', budget_id: '' });
  const [goalForm, setGoalForm] = useState({ title: '', target_amount: '' });
  const [billForm, setBillForm] = useState({ title: '', amount_due: '', due_date: '' });
  const [positionForm, setPositionForm] = useState({
    asset_type: 'stock', symbol: '', quantity: '', average_cost: '', current_price: '',
  });

  const tx = (key, fallback) => {
    const value = t(key);
    return value === key ? fallback : value;
  };

  const C = useMemo(() => ({
    card: colors.card,
    bgSoft: colors.bgSoft,
    text: colors.text,
    textSec: colors.textSec,
    textMuted: colors.textMuted,
    border: colors.border,
    primary: colors.primary,
    primaryText: colors.primaryText,
    success: colors.success,
    error: colors.error,
    warning: colors.warning,
  }), [colors]);

  const queryParams = user ? undefined : { fallback_user_id: GUEST_FALLBACK_ID };
  const withFallback = (payload) => (
    user ? payload : { ...payload, fallback_user_id: GUEST_FALLBACK_ID }
  );

  const loadAll = async () => {
    setLoading(true);
    setErrorText('');
    try {
      const [b, p, bd, ex, gl, bl, po, exa, pta, crypto] = await Promise.all([
        api.get('/money-strategy-hub/bootstrap', { params: queryParams }),
        api.get('/money-strategy-hub/profile', { params: queryParams }),
        api.get('/money-strategy-hub/budgets', { params: queryParams }),
        api.get('/money-strategy-hub/expenses', { params: queryParams }),
        api.get('/money-strategy-hub/savings-goals', { params: queryParams }),
        api.get('/money-strategy-hub/bill-reminders', { params: queryParams }),
        api.get('/money-strategy-hub/portfolio/positions', { params: queryParams }),
        api.get('/money-strategy-hub/expenses/analytics', { params: queryParams }),
        api.get('/money-strategy-hub/portfolio/analytics', { params: queryParams }),
        api.get('/data/crypto'),
      ]);
      setBootstrap(b.data);
      setProfile(p.data.profile || null);
      setBudgets(bd.data.budgets || []);
      setExpenses(ex.data.expenses || []);
      setGoals(gl.data.goals || []);
      setBillReminders(bl.data.bill_reminders || []);
      setPositions(po.data.positions || []);
      setExpenseAnalytics(exa.data || null);
      setPortfolioAnalytics(pta.data || null);
      setCryptoData(crypto.data.data || null);
      if (p.data.profile) {
        setProfileForm({
          currency: p.data.profile.currency || 'USD',
          monthly_income: String(p.data.profile.monthly_income || ''),
          fixed_monthly_expenses: String(p.data.profile.fixed_monthly_expenses || ''),
          savings_target_monthly: String(p.data.profile.savings_target_monthly || ''),
          risk_tolerance: p.data.profile.risk_tolerance || 'moderate',
        });
      }
    } catch (error) {
      setErrorText('Failed to load money strategy workspace.');
      handleAppRecoverableError({
        scope: 'features/pennypilot.tsx#loadAll',
        error,
        message: 'Money Strategy Hub failed to load. Retry now.',
      
        notifyMode: 'silent',
      });
    } finally {
      setLoading(false);
    }
  };

  const fetchStock = async (symbol) => {
    setStockLoading(true);
    try {
      const response = await api.get(`/data/finance?symbol=${symbol}`);
      setStockData(response.data);
    } catch (error) {
      handleAppRecoverableError({ scope: 'features/pennypilot.tsx#fetchStock', error, message: 'Stock feed unavailable.',
        notifyMode: 'silent',
      });
    } finally {
      setStockLoading(false);
    }
  };

  useEffect(() => {
    const timer = setTimeout(() => {
      loadAll();
      fetchStock('AAPL');
    }, 0);
    return () => clearTimeout(timer);
  }, []);

  const saveProfile = async () => {
    setSaving(true);
    try {
      await api.post('/money-strategy-hub/profile', withFallback({
        currency: profileForm.currency,
        monthly_income: Number(profileForm.monthly_income || 0),
        fixed_monthly_expenses: Number(profileForm.fixed_monthly_expenses || 0),
        savings_target_monthly: Number(profileForm.savings_target_monthly || 0),
        risk_tolerance: profileForm.risk_tolerance,
        investment_horizon_years: 3,
        financial_goals: goals.map((g) => g.title).slice(0, 8),
      }));
      await loadAll();
    } catch (error) {
      handleAppRecoverableError({
        scope: 'features/pennypilot.tsx#saveProfile',
        error,
        message: 'Failed to save profile.',
        notifyMode: 'dialog',
        userInitiated: true,
        onRetry: () => { void saveProfile(); },
      });
    } finally {
      setSaving(false);
    }
  };

  const createBudget = async () => {
    if (!budgetForm.name.trim() || !budgetForm.monthly_limit) {
      Alert.alert('', 'Budget name and limit are required');
      return;
    }
    setSaving(true);
    try {
      await api.post('/money-strategy-hub/budgets', withFallback({
        name: budgetForm.name,
        category: budgetForm.category,
        monthly_limit: Number(budgetForm.monthly_limit),
      }));
      setBudgetForm({ name: '', category: 'general', monthly_limit: '' });
      await loadAll();
    } catch (error) {
      handleAppRecoverableError({
        scope: 'features/pennypilot.tsx#createBudget',
        error,
        message: 'Could not create budget.',
        notifyMode: 'dialog',
        userInitiated: true,
        onRetry: () => { void createBudget(); },
      });
    } finally {
      setSaving(false);
    }
  };

  const archiveBudget = async (budgetId) => {
    setSaving(true);
    try {
      await api.delete(`/money-strategy-hub/budgets/${budgetId}`, { params: queryParams });
      await loadAll();
    } catch (error) {
      handleAppRecoverableError({
        scope: 'features/pennypilot.tsx#archiveBudget',
        error,
        message: 'Could not archive budget.',
        notifyMode: 'dialog',
        userInitiated: true,
        onRetry: () => { void archiveBudget(budgetId); },
      });
    } finally {
      setSaving(false);
    }
  };

  const createExpense = async () => {
    if (!expenseForm.amount) {
      Alert.alert('', 'Expense amount is required');
      return;
    }
    setSaving(true);
    try {
      await api.post('/money-strategy-hub/expenses', withFallback({
        amount: Number(expenseForm.amount),
        category: expenseForm.category,
        merchant: expenseForm.merchant,
        budget_id: expenseForm.budget_id || undefined,
      }));
      setExpenseForm({ amount: '', category: 'general', merchant: '', budget_id: '' });
      await loadAll();
    } catch (error) {
      handleAppRecoverableError({
        scope: 'features/pennypilot.tsx#createExpense',
        error,
        message: 'Could not save expense.',
        notifyMode: 'dialog',
        userInitiated: true,
        onRetry: () => { void createExpense(); },
      });
    } finally {
      setSaving(false);
    }
  };

  const deleteExpense = async (expenseId) => {
    setSaving(true);
    try {
      await api.delete(`/money-strategy-hub/expenses/${expenseId}`, { params: queryParams });
      await loadAll();
    } catch (error) {
      handleAppRecoverableError({
        scope: 'features/pennypilot.tsx#deleteExpense',
        error,
        message: 'Could not delete expense.',
        notifyMode: 'dialog',
        userInitiated: true,
        onRetry: () => { void deleteExpense(expenseId); },
      });
    } finally {
      setSaving(false);
    }
  };

  const createGoal = async () => {
    if (!goalForm.title.trim() || !goalForm.target_amount) {
      Alert.alert('', 'Goal title and target amount are required');
      return;
    }
    setSaving(true);
    try {
      await api.post('/money-strategy-hub/savings-goals', withFallback({
        title: goalForm.title,
        target_amount: Number(goalForm.target_amount),
      }));
      setGoalForm({ title: '', target_amount: '' });
      await loadAll();
    } catch (error) {
      handleAppRecoverableError({
        scope: 'features/pennypilot.tsx#createGoal',
        error,
        message: 'Could not create savings goal.',
        notifyMode: 'dialog',
        userInitiated: true,
        onRetry: () => { void createGoal(); },
      });
    } finally {
      setSaving(false);
    }
  };

  const createBillReminder = async () => {
    if (!billForm.title.trim() || !billForm.amount_due || !billForm.due_date.trim()) {
      Alert.alert('', 'Title, amount and due date are required');
      return;
    }
    setSaving(true);
    try {
      await api.post('/money-strategy-hub/bill-reminders', withFallback({
        title: billForm.title,
        amount_due: Number(billForm.amount_due),
        due_date: billForm.due_date,
      }));
      setBillForm({ title: '', amount_due: '', due_date: '' });
      await loadAll();
    } catch (error) {
      handleAppRecoverableError({
        scope: 'features/pennypilot.tsx#createBill',
        error,
        message: 'Could not create bill reminder.',
        notifyMode: 'dialog',
        userInitiated: true,
        onRetry: () => { void createBillReminder(); },
      });
    } finally {
      setSaving(false);
    }
  };

  const markBillPaid = async (reminderId) => {
    setSaving(true);
    try {
      await api.put(`/money-strategy-hub/bill-reminders/${reminderId}`, withFallback({ status: 'paid' }));
      await loadAll();
    } catch (error) {
      handleAppRecoverableError({
        scope: 'features/pennypilot.tsx#markBillPaid',
        error,
        message: 'Could not update bill status.',
        notifyMode: 'dialog',
        userInitiated: true,
        onRetry: () => { void markBillPaid(reminderId); },
      });
    } finally {
      setSaving(false);
    }
  };

  const createPosition = async () => {
    if (!positionForm.symbol.trim() || !positionForm.quantity || !positionForm.current_price) {
      Alert.alert('', 'Symbol, quantity and current price are required');
      return;
    }
    setSaving(true);
    try {
      await api.post('/money-strategy-hub/portfolio/positions', withFallback({
        asset_type: positionForm.asset_type,
        symbol: positionForm.symbol,
        quantity: Number(positionForm.quantity),
        average_cost: Number(positionForm.average_cost || positionForm.current_price),
        current_price: Number(positionForm.current_price),
      }));
      setPositionForm({ asset_type: 'stock', symbol: '', quantity: '', average_cost: '', current_price: '' });
      await loadAll();
    } catch (error) {
      handleAppRecoverableError({
        scope: 'features/pennypilot.tsx#createPosition',
        error,
        message: 'Could not add portfolio position.',
        notifyMode: 'dialog',
        userInitiated: true,
        onRetry: () => { void createPosition(); },
      });
    } finally {
      setSaving(false);
    }
  };

  const runReceiptScan = async () => {
    if (!receiptBase64.trim()) {
      Alert.alert('', 'Paste receipt image base64 first');
      return;
    }
    setSaving(true);
    try {
      const response = await api.post('/money-strategy-hub/receipt-scan', withFallback({ image_base64: receiptBase64.trim() }));
      setReceiptResult(response.data);
      if (response.data?.expense_draft?.amount) {
        setExpenseForm((prev) => ({
          ...prev,
          amount: String(response.data.expense_draft.amount || ''),
          category: response.data.expense_draft.category || prev.category,
          merchant: response.data.expense_draft.merchant || prev.merchant,
        }));
      }
    } catch (error) {
      handleAppRecoverableError({
        scope: 'features/pennypilot.tsx#receiptScan',
        error,
        message: 'Receipt scan failed.',
        notifyMode: 'dialog',
        userInitiated: true,
        onRetry: () => { void runReceiptScan(); },
      });
    } finally {
      setSaving(false);
    }
  };

  const runAdvisor = async () => {
    if (!advisorQuery.trim()) {
      Alert.alert('', tx('pennyPilot.alerts.describeQuestion', 'Please describe your finance question'));
      return;
    }
    setSaving(true);
    try {
      const response = await api.post('/money-strategy-hub/ai-advisor', withFallback({
        question: advisorQuery,
        planning_horizon_months: 6,
        include_investment: true,
      }));
      const run = response.data?.run || {};
      const advice = run.advice || {};
      setAdvisorResult([
        `## ${advice.summary || 'Money strategy summary'}`,
        `\n**Risk Score:** ${advice.risk_score || '--'}`,
        `\n### Monthly Action Plan`,
        ...(advice.monthly_action_plan || []).map((item) => `- ${item}`),
        `\n### Savings Moves`,
        ...(advice.savings_moves || []).map((item) => `- ${item}`),
        `\n### Debt Moves`,
        ...(advice.debt_moves || []).map((item) => `- ${item}`),
      ].join('\n'));
    } catch (error) {
      setAdvisorResult('Unable to generate AI advice right now.');
      handleAppRecoverableError({
        scope: 'features/pennypilot.tsx#advisor',
        error,
        message: 'AI advisor is temporarily unavailable.',
        notifyMode: 'dialog',
        userInitiated: true,
        onRetry: () => { void runAdvisor(); },
      });
    } finally {
      setSaving(false);
    }
  };

  const POPULAR_STOCKS = ['AAPL', 'GOOGL', 'MSFT', 'TSLA', 'AMZN'];

  return (
    <FeatureLayout
      title={tx('pennyPilot.page.title', 'Money Strategy Hub')}
      feature="pennypilot"
      subtitle={tx('pennyPilot.page.subtitle', 'Budget coaching, expense tracking, forecasting, and money strategy guidance')}
      icon="wallet"
      color={colors.primary}
    >
      <ScrollView style={{ flex: 1 }} contentContainerStyle={{ paddingVertical: 16, paddingBottom: 48 }}>
        {loading ? (
          <View style={[s.card, { backgroundColor: C.card, borderColor: C.border }]} data-testid="money-strategy-loading-card" testID="money-strategy-loading-card">
            <ActivityIndicator color={C.primary} />
            <Text style={{ color: C.textSec, marginTop: 10 }} data-testid="money-strategy-loading-text" testID="money-strategy-loading-text">Loading workspace…</Text>
          </View>
        ) : null}

        {errorText ? (
          <View style={[s.card, { backgroundColor: C.card, borderColor: C.error }]} data-testid="money-strategy-error-banner" testID="money-strategy-error-banner">
            <Text style={{ color: C.error, fontWeight: '700' }} data-testid="money-strategy-error-text" testID="money-strategy-error-text">{errorText}</Text>
            <TouchableOpacity
              style={[s.btn, { marginTop: 10, backgroundColor: C.primary }]}
              onPress={loadAll}
              data-testid="money-strategy-error-retry-button"
              testID="money-strategy-error-retry-button"
            >
              <Text style={{ color: C.primaryText, fontWeight: '700' }}>Retry</Text>
            </TouchableOpacity>
          </View>
        ) : null}

        <View style={[s.card, { backgroundColor: C.card, borderColor: C.border }]} data-testid="money-strategy-kpi-card" testID="money-strategy-kpi-card">
          <Text style={[s.cardTitle, { color: C.text }]} data-testid="money-strategy-kpi-title" testID="money-strategy-kpi-title">Command KPIs</Text>
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
            {[
              { key: 'tier', label: 'Tier', value: bootstrap?.tier || '--' },
              { key: 'budgets', label: 'Budgets This Month', value: bootstrap?.usage?.budgets_this_month ?? 0 },
              { key: 'expenses', label: 'Expenses Today', value: bootstrap?.usage?.expenses_today ?? 0 },
              { key: 'advisor', label: 'Advisor Runs', value: bootstrap?.usage?.advisor_runs_this_month ?? 0 },
            ].map((item) => (
              <View key={item.key} style={[s.metricTile, { borderColor: C.border, backgroundColor: C.bgSoft }]} data-testid={`money-strategy-kpi-${item.key}`} testID={`money-strategy-kpi-${item.key}`}>
                <Text style={{ color: C.textMuted, fontSize: 11 }}>{item.label}</Text>
                <Text style={{ color: C.text, fontSize: 16, fontWeight: '800' }} data-testid={`money-strategy-kpi-value-${item.key}`} testID={`money-strategy-kpi-value-${item.key}`}>{String(item.value)}</Text>
              </View>
            ))}
          </View>
        </View>

        <View style={[s.card, { backgroundColor: C.card, borderColor: C.border }]} data-testid="money-strategy-profile-card" testID="money-strategy-profile-card">
          <Text style={[s.cardTitle, { color: C.text }]} data-testid="money-strategy-profile-title" testID="money-strategy-profile-title">Financial Profile</Text>
          <View style={s.grid2}>
            <TextInput data-testid="money-strategy-profile-currency-input" testID="money-strategy-profile-currency-input" value={profileForm.currency} onChangeText={(v) => setProfileForm((p) => ({ ...p, currency: v.toUpperCase() }))} placeholder="Currency" placeholderTextColor={C.textMuted} style={[s.inputCompact, { color: C.text, backgroundColor: C.bgSoft, borderColor: C.border }]} />
            <TextInput data-testid="money-strategy-profile-risk-input" testID="money-strategy-profile-risk-input" value={profileForm.risk_tolerance} onChangeText={(v) => setProfileForm((p) => ({ ...p, risk_tolerance: v }))} placeholder="Risk tolerance" placeholderTextColor={C.textMuted} style={[s.inputCompact, { color: C.text, backgroundColor: C.bgSoft, borderColor: C.border }]} />
            <TextInput data-testid="money-strategy-profile-income-input" testID="money-strategy-profile-income-input" value={profileForm.monthly_income} onChangeText={(v) => setProfileForm((p) => ({ ...p, monthly_income: v }))} keyboardType="numeric" placeholder="Monthly income" placeholderTextColor={C.textMuted} style={[s.inputCompact, { color: C.text, backgroundColor: C.bgSoft, borderColor: C.border }]} />
            <TextInput data-testid="money-strategy-profile-fixed-input" testID="money-strategy-profile-fixed-input" value={profileForm.fixed_monthly_expenses} onChangeText={(v) => setProfileForm((p) => ({ ...p, fixed_monthly_expenses: v }))} keyboardType="numeric" placeholder="Fixed expenses" placeholderTextColor={C.textMuted} style={[s.inputCompact, { color: C.text, backgroundColor: C.bgSoft, borderColor: C.border }]} />
          </View>
          <TextInput data-testid="money-strategy-profile-savings-target-input" testID="money-strategy-profile-savings-target-input" value={profileForm.savings_target_monthly} onChangeText={(v) => setProfileForm((p) => ({ ...p, savings_target_monthly: v }))} keyboardType="numeric" placeholder="Savings target per month" placeholderTextColor={C.textMuted} style={[s.inputCompact, { marginTop: 8, color: C.text, backgroundColor: C.bgSoft, borderColor: C.border }]} />
          <TouchableOpacity style={[s.btn, { marginTop: 10, backgroundColor: C.primary }]} onPress={saveProfile} disabled={saving} data-testid="money-strategy-profile-save-button" testID="money-strategy-profile-save-button">
            {saving ? <ActivityIndicator color={C.primaryText} /> : <Text style={{ color: C.primaryText, fontWeight: '700' }}>Save Profile</Text>}
          </TouchableOpacity>
          {profile ? <Text style={{ color: C.textSec, marginTop: 8 }} data-testid="money-strategy-profile-status" testID="money-strategy-profile-status">Profile synced</Text> : null}
        </View>

        <View style={[s.card, { backgroundColor: C.card, borderColor: C.border }]} data-testid="money-strategy-budget-card" testID="money-strategy-budget-card">
          <Text style={[s.cardTitle, { color: C.text }]} data-testid="money-strategy-budget-title" testID="money-strategy-budget-title">Budgets</Text>
          <View style={s.grid3}>
            <TextInput data-testid="money-strategy-budget-name-input" testID="money-strategy-budget-name-input" value={budgetForm.name} onChangeText={(v) => setBudgetForm((p) => ({ ...p, name: v }))} placeholder="Budget name" placeholderTextColor={C.textMuted} style={[s.inputCompact, { color: C.text, backgroundColor: C.bgSoft, borderColor: C.border }]} />
            <TextInput data-testid="money-strategy-budget-category-input" testID="money-strategy-budget-category-input" value={budgetForm.category} onChangeText={(v) => setBudgetForm((p) => ({ ...p, category: v }))} placeholder="Category" placeholderTextColor={C.textMuted} style={[s.inputCompact, { color: C.text, backgroundColor: C.bgSoft, borderColor: C.border }]} />
            <TextInput data-testid="money-strategy-budget-limit-input" testID="money-strategy-budget-limit-input" value={budgetForm.monthly_limit} onChangeText={(v) => setBudgetForm((p) => ({ ...p, monthly_limit: v }))} keyboardType="numeric" placeholder="Monthly limit" placeholderTextColor={C.textMuted} style={[s.inputCompact, { color: C.text, backgroundColor: C.bgSoft, borderColor: C.border }]} />
          </View>
          <TouchableOpacity style={[s.btn, { marginTop: 8, backgroundColor: C.primary }]} onPress={createBudget} disabled={saving} data-testid="money-strategy-budget-create-button" testID="money-strategy-budget-create-button">
            <Text style={{ color: C.primaryText, fontWeight: '700' }}>Create Budget</Text>
          </TouchableOpacity>
          <View style={{ marginTop: 10, gap: 8 }}>
            {budgets.map((item) => (
              <View key={item.budget_id} style={[s.itemRow, { borderColor: C.border, backgroundColor: C.bgSoft }]} data-testid={`money-strategy-budget-item-${item.budget_id}`} testID={`money-strategy-budget-item-${item.budget_id}`}>
                <View style={{ flex: 1 }}>
                  <Text style={{ color: C.text, fontWeight: '700' }} data-testid={`money-strategy-budget-name-${item.budget_id}`} testID={`money-strategy-budget-name-${item.budget_id}`}>{item.name}</Text>
                  <Text style={{ color: C.textSec, fontSize: 12 }} data-testid={`money-strategy-budget-spent-${item.budget_id}`} testID={`money-strategy-budget-spent-${item.budget_id}`}>${item.spent_amount || 0} / ${item.monthly_limit || 0}</Text>
                </View>
                <TouchableOpacity style={[s.smallBtn, { backgroundColor: C.error }]} onPress={() => archiveBudget(item.budget_id)} data-testid={`money-strategy-budget-archive-${item.budget_id}`} testID={`money-strategy-budget-archive-${item.budget_id}`}>
                  <Text style={{ color: C.primaryText, fontSize: 12, fontWeight: '700' }}>Archive</Text>
                </TouchableOpacity>
              </View>
            ))}
          </View>
        </View>

        <View style={[s.card, { backgroundColor: C.card, borderColor: C.border }]} data-testid="money-strategy-expense-card" testID="money-strategy-expense-card">
          <Text style={[s.cardTitle, { color: C.text }]} data-testid="money-strategy-expense-title" testID="money-strategy-expense-title">Expenses + Analytics</Text>
          <View style={s.grid2}>
            <TextInput data-testid="money-strategy-expense-amount-input" testID="money-strategy-expense-amount-input" value={expenseForm.amount} onChangeText={(v) => setExpenseForm((p) => ({ ...p, amount: v }))} keyboardType="numeric" placeholder="Amount" placeholderTextColor={C.textMuted} style={[s.inputCompact, { color: C.text, backgroundColor: C.bgSoft, borderColor: C.border }]} />
            <TextInput data-testid="money-strategy-expense-category-input" testID="money-strategy-expense-category-input" value={expenseForm.category} onChangeText={(v) => setExpenseForm((p) => ({ ...p, category: v }))} placeholder="Category" placeholderTextColor={C.textMuted} style={[s.inputCompact, { color: C.text, backgroundColor: C.bgSoft, borderColor: C.border }]} />
          </View>
          <View style={s.grid2}>
            <TextInput data-testid="money-strategy-expense-merchant-input" testID="money-strategy-expense-merchant-input" value={expenseForm.merchant} onChangeText={(v) => setExpenseForm((p) => ({ ...p, merchant: v }))} placeholder="Merchant" placeholderTextColor={C.textMuted} style={[s.inputCompact, { color: C.text, backgroundColor: C.bgSoft, borderColor: C.border }]} />
            <TextInput data-testid="money-strategy-expense-budget-id-input" testID="money-strategy-expense-budget-id-input" value={expenseForm.budget_id} onChangeText={(v) => setExpenseForm((p) => ({ ...p, budget_id: v }))} placeholder="Budget ID (optional)" placeholderTextColor={C.textMuted} style={[s.inputCompact, { color: C.text, backgroundColor: C.bgSoft, borderColor: C.border }]} />
          </View>
          <TouchableOpacity style={[s.btn, { marginTop: 8, backgroundColor: C.primary }]} onPress={createExpense} disabled={saving} data-testid="money-strategy-expense-create-button" testID="money-strategy-expense-create-button">
            <Text style={{ color: C.primaryText, fontWeight: '700' }}>Add Expense</Text>
          </TouchableOpacity>
          <View style={[s.analyticsRibbon, { borderColor: C.border, backgroundColor: C.bgSoft }]} data-testid="money-strategy-expense-analytics-ribbon" testID="money-strategy-expense-analytics-ribbon">
            <Text style={{ color: C.textSec }} data-testid="money-strategy-expense-total" testID="money-strategy-expense-total">Total: ${expenseAnalytics?.summary?.total_spent || 0}</Text>
            <Text style={{ color: C.textSec }} data-testid="money-strategy-expense-count" testID="money-strategy-expense-count">Txns: {expenseAnalytics?.summary?.transaction_count || 0}</Text>
            <Text style={{ color: C.textSec }} data-testid="money-strategy-expense-avg" testID="money-strategy-expense-avg">Avg: ${expenseAnalytics?.summary?.avg_ticket || 0}</Text>
          </View>
          <View style={{ marginTop: 8, gap: 8 }}>
            {expenses.slice(0, 8).map((item) => (
              <View key={item.expense_id} style={[s.itemRow, { borderColor: C.border, backgroundColor: C.bgSoft }]} data-testid={`money-strategy-expense-item-${item.expense_id}`} testID={`money-strategy-expense-item-${item.expense_id}`}>
                <View style={{ flex: 1 }}>
                  <Text style={{ color: C.text, fontWeight: '700' }} data-testid={`money-strategy-expense-merchant-${item.expense_id}`} testID={`money-strategy-expense-merchant-${item.expense_id}`}>{item.merchant}</Text>
                  <Text style={{ color: C.textSec, fontSize: 12 }} data-testid={`money-strategy-expense-meta-${item.expense_id}`} testID={`money-strategy-expense-meta-${item.expense_id}`}>{item.category} · ${item.amount}</Text>
                </View>
                <TouchableOpacity style={[s.smallBtn, { backgroundColor: C.error }]} onPress={() => deleteExpense(item.expense_id)} data-testid={`money-strategy-expense-delete-${item.expense_id}`} testID={`money-strategy-expense-delete-${item.expense_id}`}>
                  <Text style={{ color: C.primaryText, fontSize: 12, fontWeight: '700' }}>Delete</Text>
                </TouchableOpacity>
              </View>
            ))}
          </View>
        </View>

        <View style={[s.card, { backgroundColor: C.card, borderColor: C.border }]} data-testid="money-strategy-savings-card" testID="money-strategy-savings-card">
          <Text style={[s.cardTitle, { color: C.text }]} data-testid="money-strategy-savings-title" testID="money-strategy-savings-title">Savings Goals</Text>
          <View style={s.grid2}>
            <TextInput data-testid="money-strategy-goal-title-input" testID="money-strategy-goal-title-input" value={goalForm.title} onChangeText={(v) => setGoalForm((p) => ({ ...p, title: v }))} placeholder="Goal title" placeholderTextColor={C.textMuted} style={[s.inputCompact, { color: C.text, backgroundColor: C.bgSoft, borderColor: C.border }]} />
            <TextInput data-testid="money-strategy-goal-target-input" testID="money-strategy-goal-target-input" value={goalForm.target_amount} onChangeText={(v) => setGoalForm((p) => ({ ...p, target_amount: v }))} keyboardType="numeric" placeholder="Target amount" placeholderTextColor={C.textMuted} style={[s.inputCompact, { color: C.text, backgroundColor: C.bgSoft, borderColor: C.border }]} />
          </View>
          <TouchableOpacity style={[s.btn, { marginTop: 8, backgroundColor: C.primary }]} onPress={createGoal} disabled={saving} data-testid="money-strategy-goal-create-button" testID="money-strategy-goal-create-button">
            <Text style={{ color: C.primaryText, fontWeight: '700' }}>Create Goal</Text>
          </TouchableOpacity>
          <View style={{ marginTop: 8, gap: 8 }}>
            {goals.slice(0, 6).map((item) => (
              <View key={item.goal_id} style={[s.itemRow, { borderColor: C.border, backgroundColor: C.bgSoft }]} data-testid={`money-strategy-goal-item-${item.goal_id}`} testID={`money-strategy-goal-item-${item.goal_id}`}>
                <View style={{ flex: 1 }}>
                  <Text style={{ color: C.text, fontWeight: '700' }} data-testid={`money-strategy-goal-name-${item.goal_id}`} testID={`money-strategy-goal-name-${item.goal_id}`}>{item.title}</Text>
                  <Text style={{ color: C.textSec, fontSize: 12 }} data-testid={`money-strategy-goal-progress-${item.goal_id}`} testID={`money-strategy-goal-progress-${item.goal_id}`}>${item.current_amount || 0} / ${item.target_amount || 0}</Text>
                </View>
              </View>
            ))}
          </View>
        </View>

        <View style={[s.card, { backgroundColor: C.card, borderColor: C.border }]} data-testid="money-strategy-bill-card" testID="money-strategy-bill-card">
          <Text style={[s.cardTitle, { color: C.text }]} data-testid="money-strategy-bill-title" testID="money-strategy-bill-title">Bill Reminders</Text>
          <View style={s.grid3}>
            <TextInput data-testid="money-strategy-bill-title-input" testID="money-strategy-bill-title-input" value={billForm.title} onChangeText={(v) => setBillForm((p) => ({ ...p, title: v }))} placeholder="Bill" placeholderTextColor={C.textMuted} style={[s.inputCompact, { color: C.text, backgroundColor: C.bgSoft, borderColor: C.border }]} />
            <TextInput data-testid="money-strategy-bill-amount-input" testID="money-strategy-bill-amount-input" value={billForm.amount_due} onChangeText={(v) => setBillForm((p) => ({ ...p, amount_due: v }))} keyboardType="numeric" placeholder="Amount" placeholderTextColor={C.textMuted} style={[s.inputCompact, { color: C.text, backgroundColor: C.bgSoft, borderColor: C.border }]} />
            <TextInput data-testid="money-strategy-bill-date-input" testID="money-strategy-bill-date-input" value={billForm.due_date} onChangeText={(v) => setBillForm((p) => ({ ...p, due_date: v }))} placeholder="Due date ISO" placeholderTextColor={C.textMuted} style={[s.inputCompact, { color: C.text, backgroundColor: C.bgSoft, borderColor: C.border }]} />
          </View>
          <TouchableOpacity style={[s.btn, { marginTop: 8, backgroundColor: C.primary }]} onPress={createBillReminder} disabled={saving} data-testid="money-strategy-bill-create-button" testID="money-strategy-bill-create-button">
            <Text style={{ color: C.primaryText, fontWeight: '700' }}>Add Reminder</Text>
          </TouchableOpacity>
          <View style={{ marginTop: 8, gap: 8 }}>
            {billReminders.slice(0, 6).map((item) => (
              <View key={item.reminder_id} style={[s.itemRow, { borderColor: C.border, backgroundColor: C.bgSoft }]} data-testid={`money-strategy-bill-item-${item.reminder_id}`} testID={`money-strategy-bill-item-${item.reminder_id}`}>
                <View style={{ flex: 1 }}>
                  <Text style={{ color: C.text, fontWeight: '700' }} data-testid={`money-strategy-bill-name-${item.reminder_id}`} testID={`money-strategy-bill-name-${item.reminder_id}`}>{item.title}</Text>
                  <Text style={{ color: C.textSec, fontSize: 12 }} data-testid={`money-strategy-bill-meta-${item.reminder_id}`} testID={`money-strategy-bill-meta-${item.reminder_id}`}>${item.amount_due} · {item.due_date}</Text>
                </View>
                {item.status === 'upcoming' ? (
                  <TouchableOpacity style={[s.smallBtn, { backgroundColor: C.success }]} onPress={() => markBillPaid(item.reminder_id)} data-testid={`money-strategy-bill-paid-${item.reminder_id}`} testID={`money-strategy-bill-paid-${item.reminder_id}`}>
                    <Text style={{ color: C.primaryText, fontSize: 12, fontWeight: '700' }}>Mark Paid</Text>
                  </TouchableOpacity>
                ) : (
                  <Text style={{ color: C.success, fontSize: 12, fontWeight: '700' }} data-testid={`money-strategy-bill-status-${item.reminder_id}`} testID={`money-strategy-bill-status-${item.reminder_id}`}>PAID</Text>
                )}
              </View>
            ))}
          </View>
        </View>

        <View style={[s.card, { backgroundColor: C.card, borderColor: C.border }]} data-testid="money-strategy-portfolio-card" testID="money-strategy-portfolio-card">
          <Text style={[s.cardTitle, { color: C.text }]} data-testid="money-strategy-portfolio-title" testID="money-strategy-portfolio-title">Portfolio Tracker</Text>
          <View style={s.grid3}>
            <TextInput data-testid="money-strategy-position-type-input" testID="money-strategy-position-type-input" value={positionForm.asset_type} onChangeText={(v) => setPositionForm((p) => ({ ...p, asset_type: v }))} placeholder="Type" placeholderTextColor={C.textMuted} style={[s.inputCompact, { color: C.text, backgroundColor: C.bgSoft, borderColor: C.border }]} />
            <TextInput data-testid="money-strategy-position-symbol-input" testID="money-strategy-position-symbol-input" value={positionForm.symbol} onChangeText={(v) => setPositionForm((p) => ({ ...p, symbol: v.toUpperCase() }))} placeholder="Symbol" placeholderTextColor={C.textMuted} style={[s.inputCompact, { color: C.text, backgroundColor: C.bgSoft, borderColor: C.border }]} />
            <TextInput data-testid="money-strategy-position-quantity-input" testID="money-strategy-position-quantity-input" value={positionForm.quantity} onChangeText={(v) => setPositionForm((p) => ({ ...p, quantity: v }))} keyboardType="numeric" placeholder="Qty" placeholderTextColor={C.textMuted} style={[s.inputCompact, { color: C.text, backgroundColor: C.bgSoft, borderColor: C.border }]} />
            <TextInput data-testid="money-strategy-position-cost-input" testID="money-strategy-position-cost-input" value={positionForm.average_cost} onChangeText={(v) => setPositionForm((p) => ({ ...p, average_cost: v }))} keyboardType="numeric" placeholder="Avg cost" placeholderTextColor={C.textMuted} style={[s.inputCompact, { color: C.text, backgroundColor: C.bgSoft, borderColor: C.border }]} />
            <TextInput data-testid="money-strategy-position-price-input" testID="money-strategy-position-price-input" value={positionForm.current_price} onChangeText={(v) => setPositionForm((p) => ({ ...p, current_price: v }))} keyboardType="numeric" placeholder="Current price" placeholderTextColor={C.textMuted} style={[s.inputCompact, { color: C.text, backgroundColor: C.bgSoft, borderColor: C.border }]} />
          </View>
          <TouchableOpacity style={[s.btn, { marginTop: 8, backgroundColor: C.primary }]} onPress={createPosition} disabled={saving} data-testid="money-strategy-position-create-button" testID="money-strategy-position-create-button">
            <Text style={{ color: C.primaryText, fontWeight: '700' }}>Add Position</Text>
          </TouchableOpacity>
          <View style={[s.analyticsRibbon, { borderColor: C.border, backgroundColor: C.bgSoft }]} data-testid="money-strategy-portfolio-analytics-ribbon" testID="money-strategy-portfolio-analytics-ribbon">
            <Text style={{ color: C.textSec }} data-testid="money-strategy-portfolio-market-value" testID="money-strategy-portfolio-market-value">Value: ${portfolioAnalytics?.summary?.total_market_value || 0}</Text>
            <Text style={{ color: C.textSec }} data-testid="money-strategy-portfolio-pnl" testID="money-strategy-portfolio-pnl">PnL: ${portfolioAnalytics?.summary?.unrealized_pnl || 0}</Text>
            <Text style={{ color: C.textSec }} data-testid="money-strategy-portfolio-roi" testID="money-strategy-portfolio-roi">ROI: {portfolioAnalytics?.summary?.roi_pct || 0}%</Text>
          </View>
          <View style={{ marginTop: 8, gap: 8 }}>
            {positions.slice(0, 8).map((item) => (
              <View key={item.position_id} style={[s.itemRow, { borderColor: C.border, backgroundColor: C.bgSoft }]} data-testid={`money-strategy-position-item-${item.position_id}`} testID={`money-strategy-position-item-${item.position_id}`}>
                <View style={{ flex: 1 }}>
                  <Text style={{ color: C.text, fontWeight: '700' }} data-testid={`money-strategy-position-symbol-${item.position_id}`} testID={`money-strategy-position-symbol-${item.position_id}`}>{item.symbol}</Text>
                  <Text style={{ color: C.textSec, fontSize: 12 }} data-testid={`money-strategy-position-meta-${item.position_id}`} testID={`money-strategy-position-meta-${item.position_id}`}>{item.asset_type} · {item.quantity} · ${item.current_price}</Text>
                </View>
              </View>
            ))}
          </View>
        </View>

        <View style={[s.card, { backgroundColor: C.card, borderColor: C.border }]} data-testid="money-strategy-receipt-card" testID="money-strategy-receipt-card">
          <Text style={[s.cardTitle, { color: C.text }]} data-testid="money-strategy-receipt-title" testID="money-strategy-receipt-title">Receipt Scan</Text>
          <TextInput
            multiline
            value={receiptBase64}
            onChangeText={setReceiptBase64}
            placeholder="Paste base64 receipt image"
            placeholderTextColor={C.textMuted}
            style={[s.inputLarge, { color: C.text, backgroundColor: C.bgSoft, borderColor: C.border }]}
            data-testid="money-strategy-receipt-base64-input"
            testID="money-strategy-receipt-base64-input"
          />
          <TouchableOpacity style={[s.btn, { marginTop: 8, backgroundColor: C.primary }]} onPress={runReceiptScan} disabled={saving} data-testid="money-strategy-receipt-scan-button" testID="money-strategy-receipt-scan-button">
            <Text style={{ color: C.primaryText, fontWeight: '700' }}>Run Receipt Scan</Text>
          </TouchableOpacity>
          {receiptResult?.scan ? (
            <View style={[s.itemRow, { marginTop: 10, borderColor: C.border, backgroundColor: C.bgSoft }]} data-testid="money-strategy-receipt-result" testID="money-strategy-receipt-result">
              <View style={{ flex: 1 }}>
                <Text style={{ color: C.text, fontWeight: '700' }} data-testid="money-strategy-receipt-merchant" testID="money-strategy-receipt-merchant">{receiptResult.scan.extracted_data?.merchant || 'Unknown merchant'}</Text>
                <Text style={{ color: C.textSec, fontSize: 12 }} data-testid="money-strategy-receipt-total" testID="money-strategy-receipt-total">${receiptResult.scan.extracted_data?.total_amount || 0} · {receiptResult.scan.extracted_data?.category_suggestion || 'general'}</Text>
              </View>
            </View>
          ) : null}
        </View>

        <View style={[s.card, { backgroundColor: C.card, borderColor: C.border }]} data-testid="money-strategy-market-card" testID="money-strategy-market-card">
          <Text style={[s.cardTitle, { color: C.text }]} data-testid="money-strategy-market-title" testID="money-strategy-market-title">Live Market Context</Text>
          <View style={s.stockRow}>
            <View style={[s.stockInput, { backgroundColor: C.bgSoft, borderColor: C.border }]}>
              <Ionicons name="search" size={16} color={C.textMuted} />
              <TextInput data-testid="money-strategy-stock-symbol-input" testID="money-strategy-stock-symbol-input" style={[s.stockInputText, { color: C.text }]} value={stockSymbol} onChangeText={(v) => setStockSymbol(v.toUpperCase())} placeholder="Symbol" placeholderTextColor={C.textMuted} autoCapitalize="characters" maxLength={8} />
            </View>
            <TouchableOpacity style={[s.stockBtn, { backgroundColor: C.primary }]} onPress={() => fetchStock(stockSymbol)} disabled={stockLoading} data-testid="money-strategy-stock-lookup-button" testID="money-strategy-stock-lookup-button">
              {stockLoading ? <ActivityIndicator color={C.primaryText} /> : <Ionicons name="pulse" size={16} color={C.primaryText} />}
            </TouchableOpacity>
          </View>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ marginBottom: 10 }} contentContainerStyle={{ gap: 8 }}>
            {POPULAR_STOCKS.map((sym) => (
              <TouchableOpacity key={sym} style={[s.symChip, { borderColor: C.border }, stockSymbol === sym ? { backgroundColor: C.primary } : null]} onPress={() => { setStockSymbol(sym); fetchStock(sym); }} data-testid={`money-strategy-stock-chip-${sym}`} testID={`money-strategy-stock-chip-${sym}`}>
                <Text style={[s.symChipText, { color: stockSymbol === sym ? C.primaryText : C.textSec }]}>{sym}</Text>
              </TouchableOpacity>
            ))}
          </ScrollView>
          {stockData?.symbol ? (
            <View style={[s.stockCard, { borderColor: C.border, backgroundColor: C.bgSoft }]} data-testid="money-strategy-stock-result" testID="money-strategy-stock-result">
              <Text style={{ color: C.text, fontWeight: '800' }} data-testid="money-strategy-stock-result-symbol" testID="money-strategy-stock-result-symbol">{stockData.symbol}</Text>
              <Text style={{ color: C.text, fontSize: 22, fontWeight: '800' }} data-testid="money-strategy-stock-result-price" testID="money-strategy-stock-result-price">${stockData.price !== 'N/A' ? Number(stockData.price).toFixed(2) : '--'}</Text>
            </View>
          ) : null}
          {cryptoData ? (
            <View style={{ gap: 8, marginTop: 10 }}>
              {Object.entries(cryptoData).slice(0, 3).map(([coin, data]) => (
                <View key={coin} style={[s.itemRow, { borderColor: C.border, backgroundColor: C.bgSoft }]} data-testid={`money-strategy-crypto-item-${coin}`} testID={`money-strategy-crypto-item-${coin}`}>
                  <Text style={{ color: C.text, fontWeight: '700' }} data-testid={`money-strategy-crypto-name-${coin}`} testID={`money-strategy-crypto-name-${coin}`}>{coin.toUpperCase()}</Text>
                  <Text style={{ color: C.textSec }} data-testid={`money-strategy-crypto-value-${coin}`} testID={`money-strategy-crypto-value-${coin}`}>${data.usd?.toLocaleString?.() || data.usd || '--'}</Text>
                </View>
              ))}
            </View>
          ) : null}
        </View>

        <View style={[s.card, { backgroundColor: C.card, borderColor: C.border }]} data-testid="money-strategy-advisor-card" testID="money-strategy-advisor-card">
          <Text style={[s.cardTitle, { color: C.text }]} data-testid="money-strategy-advisor-title" testID="money-strategy-advisor-title">AI Money Advisor</Text>
          <TextInput
            style={[s.inputLarge, { color: C.text, backgroundColor: C.bgSoft, borderColor: C.border }]}
            value={advisorQuery}
            onChangeText={setAdvisorQuery}
            multiline
            placeholder="E.g. How should I optimize savings and debt over next 6 months?"
            placeholderTextColor={C.textMuted}
            data-testid="money-strategy-advisor-query-input"
            testID="money-strategy-advisor-query-input"
          />
          <TouchableOpacity style={[s.btn, { backgroundColor: C.primary, marginTop: 8 }]} onPress={runAdvisor} disabled={saving} data-testid="money-strategy-advisor-run-button" testID="money-strategy-advisor-run-button">
            {saving ? <ActivityIndicator color={C.primaryText} /> : <Text style={{ color: C.primaryText, fontWeight: '700' }}>Generate Strategy</Text>}
          </TouchableOpacity>
          {advisorResult ? (
            <View style={{ marginTop: 10 }} data-testid="money-strategy-advisor-result" testID="money-strategy-advisor-result">
              <MarkdownDisplay content={advisorResult} />
              <FeatureToolbar content={advisorResult} featureKey="pennypilot" title="Money Strategy" onClear={() => setAdvisorResult('')} />
              <AIFeedbackBar feature="pennypilot" response={advisorResult} showDisclaimer={true} />
            </View>
          ) : null}
        </View>
      </ScrollView>
    </FeatureLayout>
  );
}

const s = {
  card: { borderRadius: 16, padding: 16, marginHorizontal: 16, marginBottom: 14, borderWidth: 1 },
  cardTitle: { fontSize: 15, fontWeight: '700', marginBottom: 10 },
  btn: { borderRadius: 12, paddingVertical: 12, alignItems: 'center', justifyContent: 'center' },
  inputCompact: { borderRadius: 10, borderWidth: 1, paddingHorizontal: 12, paddingVertical: 10, fontSize: 13, marginTop: 8 },
  inputLarge: { borderRadius: 12, borderWidth: 1, paddingHorizontal: 12, paddingVertical: 10, fontSize: 13, minHeight: 88, textAlignVertical: 'top' },
  grid2: { flexDirection: 'row', gap: 8, flexWrap: 'wrap' },
  grid3: { flexDirection: 'row', gap: 8, flexWrap: 'wrap' },
  metricTile: { minWidth: 130, borderWidth: 1, borderRadius: 10, padding: 10 },
  itemRow: { borderWidth: 1, borderRadius: 10, padding: 10, flexDirection: 'row', alignItems: 'center', gap: 8 },
  smallBtn: { borderRadius: 8, paddingHorizontal: 10, paddingVertical: 6 },
  analyticsRibbon: { marginTop: 10, borderWidth: 1, borderRadius: 10, padding: 10, flexDirection: 'row', justifyContent: 'space-between' },
  stockRow: { flexDirection: 'row', gap: 8 },
  stockInput: { flex: 1, flexDirection: 'row', alignItems: 'center', borderRadius: 10, borderWidth: 1, paddingHorizontal: 10 },
  stockInputText: { flex: 1, paddingVertical: 10, fontSize: 13, fontWeight: '700' },
  stockBtn: { width: 42, height: 42, borderRadius: 10, alignItems: 'center', justifyContent: 'center' },
  symChip: { borderWidth: 1, borderRadius: 8, paddingHorizontal: 12, paddingVertical: 6 },
  symChipText: { fontSize: 11, fontWeight: '700' },
  stockCard: { borderWidth: 1, borderRadius: 10, padding: 10, marginTop: 8 },
};
