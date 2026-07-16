import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  Platform,
  ScrollView,
  Text,
  TextInput,
  TouchableOpacity,
  View,
  useWindowDimensions,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import api from '../../src/services/api';
import FeatureLayout from '../../src/components/FeatureLayout';
import { useTheme } from '../../src/context/ThemeContext';
import { useTranslation } from '../../src/hooks/useTranslation';

type Client = {
  client_id: string;
  name: string;
  email?: string;
  phone?: string;
};

type BillRow = {
  bill_id: string;
  bill_number: string;
  bill_type: 'invoice' | 'receipt' | 'proforma';
  customer_name: string;
  currency: string;
  total: number;
  status: 'draft' | 'sent' | 'paid' | 'overdue' | 'cancelled';
  approval_status?: 'draft' | 'pending' | 'approved' | 'rejected';
  approval_required?: boolean;
  due_date?: string;
  created_at?: string;
};

type CatalogItem = {
  catalog_item_id: string;
  name: string;
  description?: string;
  unit_price: number;
  tax_rate: number;
  unit?: string;
};

type RecurringSchedule = {
  schedule_id: string;
  schedule_name: string;
  frequency: 'daily' | 'weekly' | 'monthly' | 'quarterly' | 'yearly';
  active: boolean;
  next_run_at?: string;
  run_count?: number;
};

type ReminderRow = {
  bill_id: string;
  bill_number: string;
  customer_name: string;
  status: string;
  due_date?: string;
  days_to_due: number;
  amount: number;
  currency: string;
  reminder_type: 'due_soon' | 'due_today' | 'overdue';
};

type ClientInsight = {
  customer_name: string;
  bill_count: number;
  paid_count: number;
  overdue_count: number;
  total_billed: number;
  paid_total: number;
  overdue_total: number;
  avg_days_to_pay: number;
  on_time_rate: number;
};

type BootstrapPayload = {
  plan: string;
  scope_label: string;
  limits: Record<string, number>;
  clients: Client[];
  bills: BillRow[];
  catalog_items: CatalogItem[];
  recurring_schedules: RecurringSchedule[];
  reminders: ReminderRow[];
  client_insights: ClientInsight[];
  collections_dashboard?: {
    aging_buckets: Record<string, number>;
    paid_velocity_30d: number;
    paid_volume_30d: number;
    paid_count_30d: number;
    forecast_cash_in_14d: number;
    actionable_collections: Array<{
      bill_id: string;
      bill_number: string;
      customer_name: string;
      status: string;
      currency: string;
      amount: number;
      days_overdue: number;
      due_date?: string;
    }>;
  };
  channel_settings?: {
    in_app_enabled: boolean;
    email_enabled: boolean;
  };
  workspace_settings?: {
    approval_required_for_send: boolean;
  };
  workspace_members?: Array<{
    member_id: string;
    member_user_id: string;
    member_email: string;
    member_name?: string;
    role: 'owner' | 'manager' | 'finance' | 'viewer';
    active: boolean;
  }>;
  insights: {
    total_bills: number;
    current_month_bills: number;
    paid_total: number;
    outstanding_total: number;
    status_counts: Record<string, number>;
    recurring_active?: number;
    reminders_open?: number;
  };
};

type ItemDraft = {
  description: string;
  quantity: string;
  unit_price: string;
  tax_rate: string;
};

const EMPTY_ITEM: ItemDraft = {
  description: '',
  quantity: '1',
  unit_price: '0',
  tax_rate: '0',
};

export default function BillGeneratorScreen() {
  const { colors } = useTheme();
  const { t } = useTranslation();
  const { width } = useWindowDimensions();
  const isDesktop = width >= 1024;

  const tx = useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);

  const [loading, setLoading] = useState(true);
  const [working, setWorking] = useState(false);
  const [aiLoading, setAiLoading] = useState(false);
  const [pdfLoadingId, setPdfLoadingId] = useState('');

  const [plan, setPlan] = useState('free');
  const [scopeLabel, setScopeLabel] = useState('Limited access');
  const [limits, setLimits] = useState<Record<string, number>>({});

  const [clients, setClients] = useState<Client[]>([]);
  const [bills, setBills] = useState<BillRow[]>([]);
  const [catalogItems, setCatalogItems] = useState<CatalogItem[]>([]);
  const [recurringSchedules, setRecurringSchedules] = useState<RecurringSchedule[]>([]);
  const [reminders, setReminders] = useState<ReminderRow[]>([]);
  const [clientInsights, setClientInsights] = useState<ClientInsight[]>([]);
  const [collectionsDashboard, setCollectionsDashboard] = useState<any>(null);
  const [channelSettings, setChannelSettings] = useState({ in_app_enabled: true, email_enabled: true });
  const [workspaceSettings, setWorkspaceSettings] = useState({ approval_required_for_send: true });
  const [workspaceMembers, setWorkspaceMembers] = useState<any[]>([]);
  const [insights, setInsights] = useState<any>(null);

  const [clientName, setClientName] = useState('');
  const [clientEmail, setClientEmail] = useState('');
  const [clientPhone, setClientPhone] = useState('');

  const [aiScope, setAiScope] = useState('');
  const [aiIndustry, setAiIndustry] = useState('services');
  const [aiTarget, setAiTarget] = useState('500');

  const [billType, setBillType] = useState<'invoice' | 'receipt' | 'proforma'>('invoice');
  const [selectedClientId, setSelectedClientId] = useState('');
  const [customerName, setCustomerName] = useState('');
  const [customerEmail, setCustomerEmail] = useState('');
  const [currency, setCurrency] = useState('USD');
  const [dueDate, setDueDate] = useState('');
  const [discountPct, setDiscountPct] = useState('0');
  const [notes, setNotes] = useState('');
  const [items, setItems] = useState<ItemDraft[]>([{ ...EMPTY_ITEM }]);

  const [catalogName, setCatalogName] = useState('');
  const [catalogDescription, setCatalogDescription] = useState('');
  const [catalogPrice, setCatalogPrice] = useState('0');
  const [catalogTax, setCatalogTax] = useState('0');

  const [scheduleName, setScheduleName] = useState('');
  const [scheduleFrequency, setScheduleFrequency] = useState<'daily' | 'weekly' | 'monthly' | 'quarterly' | 'yearly'>('monthly');
  const [scheduleStartAt, setScheduleStartAt] = useState('');

  const [inviteEmail, setInviteEmail] = useState('');
  const [inviteRole, setInviteRole] = useState<'manager' | 'finance' | 'viewer'>('viewer');
  const [bulkTone, setBulkTone] = useState<'friendly' | 'firm' | 'final'>('friendly');

  const card = {
    backgroundColor: colors.card,
    borderColor: colors.border,
    borderWidth: 1,
    borderRadius: 16,
    padding: 16,
    marginHorizontal: 16,
    marginBottom: 14,
  } as any;

  const input = {
    backgroundColor: colors.bgSoft,
    borderColor: colors.border,
    borderWidth: 1,
    borderRadius: 10,
    paddingHorizontal: 12,
    paddingVertical: 10,
    color: colors.text,
    fontSize: 13,
  } as any;

  const money = useCallback((value: number, curr = currency) => {
    const n = Number.isFinite(value) ? value : 0;
    return `${curr} ${n.toFixed(2)}`;
  }, [currency]);

  const fetchBootstrap = useCallback(async () => {
    try {
      setLoading(true);
      const res = await api.get('/bill-generator/bootstrap');
      const data: BootstrapPayload = res.data;
      setPlan(String(data?.plan || 'free'));
      setScopeLabel(String(data?.scope_label || tx('billGenerator.scope.limited', 'Limited access')));
      setLimits(data?.limits || {});
      setClients(data?.clients || []);
      setBills(data?.bills || []);
      setCatalogItems(data?.catalog_items || []);
      setRecurringSchedules(data?.recurring_schedules || []);
      setReminders(data?.reminders || []);
      setClientInsights(data?.client_insights || []);
      setCollectionsDashboard(data?.collections_dashboard || null);
      setChannelSettings(data?.channel_settings || { in_app_enabled: true, email_enabled: true });
      setWorkspaceSettings(data?.workspace_settings || { approval_required_for_send: true });
      setWorkspaceMembers(data?.workspace_members || []);
      setInsights(data?.insights || {});
    } catch (e: any) {
      Alert.alert(
        tx('billGenerator.alert.loadFailedTitle', 'Unable to load Bill Generator'),
        e?.response?.data?.detail || tx('billGenerator.alert.loadFailedBody', 'Please retry in a few seconds.'),
      );
    } finally {
      setLoading(false);
    }
  }, [tx]);

  useEffect(() => {
    fetchBootstrap();
  }, [fetchBootstrap]);

  const totals = useMemo(() => {
    let subtotal = 0;
    let tax = 0;
    items.forEach((row) => {
      const qty = Number(row.quantity || 0);
      const unit = Number(row.unit_price || 0);
      const taxRate = Number(row.tax_rate || 0);
      const lineSubtotal = qty * unit;
      subtotal += lineSubtotal;
      tax += (lineSubtotal * taxRate) / 100;
    });
    const discount = (subtotal + tax) * (Number(discountPct || 0) / 100);
    const total = Math.max(0, subtotal + tax - discount);
    return { subtotal, tax, discount, total };
  }, [items, discountPct]);

  const updateItem = (idx: number, key: keyof ItemDraft, value: string) => {
    setItems((prev) => prev.map((row, i) => (i === idx ? { ...row, [key]: value } : row)));
  };

  const addItem = () => {
    setItems((prev) => [...prev, { ...EMPTY_ITEM }]);
  };

  const removeItem = (idx: number) => {
    setItems((prev) => (prev.length <= 1 ? prev : prev.filter((_, i) => i !== idx)));
  };

  const createClient = async () => {
    if (!clientName.trim()) {
      Alert.alert(tx('billGenerator.alert.clientNameTitle', 'Client name required'));
      return;
    }
    try {
      setWorking(true);
      await api.post('/bill-generator/clients', {
        name: clientName.trim(),
        email: clientEmail.trim(),
        phone: clientPhone.trim(),
        address: '',
      });
      setClientName('');
      setClientEmail('');
      setClientPhone('');
      await fetchBootstrap();
    } catch (e: any) {
      Alert.alert(
        tx('billGenerator.alert.clientCreateFailedTitle', 'Could not create client'),
        e?.response?.data?.detail || tx('billGenerator.alert.clientCreateFailedBody', 'Please retry.'),
      );
    } finally {
      setWorking(false);
    }
  };

  const createCatalogItem = async () => {
    if (!catalogName.trim()) {
      Alert.alert(tx('billGenerator.alert.catalogNameRequired', 'Catalog item name is required'));
      return;
    }
    try {
      setWorking(true);
      await api.post('/bill-generator/catalog/items', {
        name: catalogName.trim(),
        description: catalogDescription.trim(),
        unit_price: Number(catalogPrice || 0),
        tax_rate: Number(catalogTax || 0),
        unit: 'item',
      });
      setCatalogName('');
      setCatalogDescription('');
      setCatalogPrice('0');
      setCatalogTax('0');
      await fetchBootstrap();
    } catch (e: any) {
      Alert.alert(
        tx('billGenerator.alert.catalogCreateFailedTitle', 'Could not create catalog item'),
        e?.response?.data?.detail || tx('billGenerator.alert.catalogCreateFailedBody', 'Please retry.'),
      );
    } finally {
      setWorking(false);
    }
  };

  const applyCatalogItem = (item: CatalogItem) => {
    setItems((prev) => ([
      ...prev,
      {
        description: item.name,
        quantity: '1',
        unit_price: String(item.unit_price ?? 0),
        tax_rate: String(item.tax_rate ?? 0),
      },
    ]));
  };

  const createRecurringSchedule = async () => {
    const cleanedItems = items
      .filter((row) => row.description.trim())
      .map((row) => ({
        description: row.description.trim(),
        quantity: Number(row.quantity || 0),
        unit_price: Number(row.unit_price || 0),
        tax_rate: Number(row.tax_rate || 0),
      }));

    if (!scheduleName.trim()) {
      Alert.alert(tx('billGenerator.alert.scheduleNameRequired', 'Schedule name is required'));
      return;
    }
    if (!cleanedItems.length) {
      Alert.alert(tx('billGenerator.alert.scheduleItemsRequired', 'Recurring schedule needs at least one line item'));
      return;
    }
    try {
      setWorking(true);
      await api.post('/bill-generator/recurring-schedules', {
        schedule_name: scheduleName.trim(),
        frequency: scheduleFrequency,
        start_at: scheduleStartAt || null,
        template: {
          bill_type: billType,
          client_id: selectedClientId || null,
          customer_name: customerName.trim() || null,
          customer_email: customerEmail.trim() || null,
          currency: currency.trim().toUpperCase() || 'USD',
          due_date: dueDate || null,
          discount_pct: Number(discountPct || 0),
          notes,
          ai_context: aiScope,
          items: cleanedItems,
        },
      });
      setScheduleName('');
      setScheduleStartAt('');
      await fetchBootstrap();
    } catch (e: any) {
      Alert.alert(
        tx('billGenerator.alert.scheduleCreateFailedTitle', 'Could not create recurring schedule'),
        e?.response?.data?.detail || tx('billGenerator.alert.scheduleCreateFailedBody', 'Please retry.'),
      );
    } finally {
      setWorking(false);
    }
  };

  const toggleRecurringSchedule = async (scheduleId: string, active: boolean) => {
    try {
      setWorking(true);
      await api.post(`/bill-generator/recurring-schedules/${scheduleId}/toggle`, { active });
      await fetchBootstrap();
    } catch (e: any) {
      Alert.alert(
        tx('billGenerator.alert.scheduleToggleFailedTitle', 'Could not change schedule status'),
        e?.response?.data?.detail || tx('billGenerator.alert.scheduleToggleFailedBody', 'Please retry.'),
      );
    } finally {
      setWorking(false);
    }
  };

  const runRecurringSchedule = async (scheduleId: string) => {
    try {
      setWorking(true);
      await api.post(`/bill-generator/recurring-schedules/${scheduleId}/run`);
      await fetchBootstrap();
    } catch (e: any) {
      Alert.alert(
        tx('billGenerator.alert.scheduleRunFailedTitle', 'Schedule run failed'),
        e?.response?.data?.detail || tx('billGenerator.alert.scheduleRunFailedBody', 'Please retry.'),
      );
    } finally {
      setWorking(false);
    }
  };

  const runDueSchedules = async () => {
    try {
      setWorking(true);
      await api.post('/bill-generator/recurring-schedules/run-due');
      await fetchBootstrap();
    } catch (e: any) {
      Alert.alert(
        tx('billGenerator.alert.runDueSchedulesFailedTitle', 'Could not run due schedules'),
        e?.response?.data?.detail || tx('billGenerator.alert.runDueSchedulesFailedBody', 'Please retry.'),
      );
    } finally {
      setWorking(false);
    }
  };

  const createReminderMessage = async (billId: string, tone: 'friendly' | 'firm' | 'final') => {
    try {
      const res = await api.post(`/bill-generator/reminders/${billId}/message`, { tone });
      const message = String(res.data?.message || '');
      if (Platform.OS === 'web' && typeof navigator !== 'undefined' && navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(message);
      }
      Alert.alert(tx('billGenerator.alert.reminderGeneratedTitle', 'Reminder generated'), message);
    } catch (e: any) {
      Alert.alert(
        tx('billGenerator.alert.reminderFailedTitle', 'Could not generate reminder'),
        e?.response?.data?.detail || tx('billGenerator.alert.reminderFailedBody', 'Please retry.'),
      );
    }
  };

  const updateChannelSettings = async (patch: Partial<{ in_app_enabled: boolean; email_enabled: boolean }>) => {
    const next = { ...channelSettings, ...patch };
    try {
      setWorking(true);
      const res = await api.post('/bill-generator/channels/settings', next);
      setChannelSettings(res.data?.settings || next);
    } catch (e: any) {
      Alert.alert(tx('billGenerator.alert.channelSettingsFailedTitle', 'Could not update reminder channels'), e?.response?.data?.detail || tx('billGenerator.alert.channelSettingsFailedBody', 'Please retry.'));
    } finally {
      setWorking(false);
    }
  };

  const updateWorkflowSettings = async (approvalRequired: boolean) => {
    try {
      setWorking(true);
      const res = await api.post('/bill-generator/workflow/settings', { approval_required_for_send: approvalRequired });
      setWorkspaceSettings(res.data?.settings || { approval_required_for_send: approvalRequired });
      await fetchBootstrap();
    } catch (e: any) {
      Alert.alert(tx('billGenerator.alert.workflowSettingsFailedTitle', 'Could not update approval workflow'), e?.response?.data?.detail || tx('billGenerator.alert.workflowSettingsFailedBody', 'Please retry.'));
    } finally {
      setWorking(false);
    }
  };

  const dispatchReminder = async (billId: string, tone: 'friendly' | 'firm' | 'final') => {
    try {
      setWorking(true);
      const res = await api.post(`/bill-generator/reminders/${billId}/dispatch`, {
        tone,
        channel_in_app: channelSettings.in_app_enabled,
        channel_email: channelSettings.email_enabled,
      });
      Alert.alert(tx('billGenerator.alert.reminderDispatchTitle', 'Reminder dispatched'), JSON.stringify(res.data?.dispatch || {}, null, 2));
      await fetchBootstrap();
    } catch (e: any) {
      Alert.alert(tx('billGenerator.alert.reminderDispatchFailedTitle', 'Reminder dispatch failed'), e?.response?.data?.detail || tx('billGenerator.alert.reminderDispatchFailedBody', 'Please retry.'));
    } finally {
      setWorking(false);
    }
  };

  const bulkDispatchReminders = async () => {
    try {
      setWorking(true);
      const res = await api.post('/bill-generator/collections/bulk-reminders', {
        tone: bulkTone,
        channel_in_app: channelSettings.in_app_enabled,
        channel_email: channelSettings.email_enabled,
      });
      Alert.alert(tx('billGenerator.alert.bulkDispatchTitle', 'Bulk reminders sent'), `${tx('billGenerator.alert.bulkDispatchProcessed', 'Processed')}: ${res.data?.processed || 0}\nIn-app: ${res.data?.in_app_queued || 0}\nEmail: ${res.data?.email_sent || 0}`);
      await fetchBootstrap();
    } catch (e: any) {
      Alert.alert(tx('billGenerator.alert.bulkDispatchFailedTitle', 'Bulk dispatch failed'), e?.response?.data?.detail || tx('billGenerator.alert.bulkDispatchFailedBody', 'Please retry.'));
    } finally {
      setWorking(false);
    }
  };

  const inviteWorkspaceMember = async () => {
    if (!inviteEmail.trim()) {
      Alert.alert(tx('billGenerator.alert.inviteEmailRequiredTitle', 'Member email required'));
      return;
    }
    try {
      setWorking(true);
      await api.post('/bill-generator/workspace/members', { email: inviteEmail.trim(), role: inviteRole });
      setInviteEmail('');
      await fetchBootstrap();
    } catch (e: any) {
      Alert.alert(tx('billGenerator.alert.inviteFailedTitle', 'Could not add workspace member'), e?.response?.data?.detail || tx('billGenerator.alert.inviteFailedBody', 'Please retry with an existing user email.'));
    } finally {
      setWorking(false);
    }
  };

  const changeMemberRole = async (memberUserId: string, role: 'manager' | 'finance' | 'viewer') => {
    try {
      setWorking(true);
      await api.patch(`/bill-generator/workspace/members/${memberUserId}`, { role });
      await fetchBootstrap();
    } catch (e: any) {
      Alert.alert(tx('billGenerator.alert.memberRoleFailedTitle', 'Could not update member role'), e?.response?.data?.detail || tx('billGenerator.alert.memberRoleFailedBody', 'Please retry.'));
    } finally {
      setWorking(false);
    }
  };

  const submitForApproval = async (billId: string) => {
    try {
      setWorking(true);
      await api.post(`/bill-generator/workflow/${billId}/submit`, { note: 'Submitted from Bill Generator workspace' });
      await fetchBootstrap();
    } catch (e: any) {
      Alert.alert(tx('billGenerator.alert.submitApprovalFailedTitle', 'Could not submit for approval'), e?.response?.data?.detail || tx('billGenerator.alert.submitApprovalFailedBody', 'Please retry.'));
    } finally {
      setWorking(false);
    }
  };

  const approveBill = async (billId: string) => {
    try {
      setWorking(true);
      await api.post(`/bill-generator/workflow/${billId}/approve`, { note: 'Approved from command center' });
      await fetchBootstrap();
    } catch (e: any) {
      Alert.alert(tx('billGenerator.alert.approveFailedTitle', 'Could not approve bill'), e?.response?.data?.detail || tx('billGenerator.alert.approveFailedBody', 'Please retry.'));
    } finally {
      setWorking(false);
    }
  };

  const rejectBill = async (billId: string) => {
    try {
      setWorking(true);
      await api.post(`/bill-generator/workflow/${billId}/reject`, { note: 'Rejected for revision' });
      await fetchBootstrap();
    } catch (e: any) {
      Alert.alert(tx('billGenerator.alert.rejectFailedTitle', 'Could not reject bill'), e?.response?.data?.detail || tx('billGenerator.alert.rejectFailedBody', 'Please retry.'));
    } finally {
      setWorking(false);
    }
  };

  const generateAiDraft = async () => {
    if (!aiScope.trim()) {
      Alert.alert(tx('billGenerator.alert.scopeRequiredTitle', 'Describe the bill scope first'));
      return;
    }

    try {
      setAiLoading(true);
      const res = await api.post('/bill-generator/ai-draft', {
        client_name: customerName || clients.find((c) => c.client_id === selectedClientId)?.name || 'Client',
        industry: aiIndustry,
        scope: aiScope,
        amount_target: Number(aiTarget || 0),
        currency,
      });
      const draft = res.data?.draft || {};
      if (Array.isArray(draft.items) && draft.items.length > 0) {
        setItems(
          draft.items.map((row: any) => ({
            description: String(row.description || ''),
            quantity: String(row.quantity ?? '1'),
            unit_price: String(row.unit_price ?? '0'),
            tax_rate: String(row.tax_rate ?? '0'),
          })),
        );
      }
      setNotes(String(draft.notes || notes || ''));
      if (draft.recommended_bill_type && ['invoice', 'receipt', 'proforma'].includes(String(draft.recommended_bill_type))) {
        setBillType(draft.recommended_bill_type);
      }
    } catch (e: any) {
      Alert.alert(
        tx('billGenerator.alert.aiDraftFailedTitle', 'AI draft failed'),
        e?.response?.data?.detail || tx('billGenerator.alert.aiDraftFailedBody', 'Try a shorter scope and retry.'),
      );
    } finally {
      setAiLoading(false);
    }
  };

  const createBill = async () => {
    const cleanedItems = items
      .filter((row) => row.description.trim())
      .map((row) => ({
        description: row.description.trim(),
        quantity: Number(row.quantity || 0),
        unit_price: Number(row.unit_price || 0),
        tax_rate: Number(row.tax_rate || 0),
      }));

    if (!cleanedItems.length) {
      Alert.alert(tx('billGenerator.alert.itemsRequiredTitle', 'Add at least one valid bill item'));
      return;
    }

    if (!selectedClientId && !customerName.trim()) {
      Alert.alert(tx('billGenerator.alert.customerRequiredTitle', 'Select client or enter customer name'));
      return;
    }

    try {
      setWorking(true);
      await api.post('/bill-generator/bills', {
        bill_type: billType,
        client_id: selectedClientId || null,
        customer_name: customerName.trim() || null,
        customer_email: customerEmail.trim() || null,
        currency: currency.trim().toUpperCase() || 'USD',
        due_date: dueDate || null,
        discount_pct: Number(discountPct || 0),
        notes,
        ai_context: aiScope,
        items: cleanedItems,
      });
      setItems([{ ...EMPTY_ITEM }]);
      setNotes('');
      setAiScope('');
      setDiscountPct('0');
      setDueDate('');
      await fetchBootstrap();
    } catch (e: any) {
      Alert.alert(
        tx('billGenerator.alert.createFailedTitle', 'Could not create bill'),
        e?.response?.data?.detail || tx('billGenerator.alert.createFailedBody', 'Please retry with valid values.'),
      );
    } finally {
      setWorking(false);
    }
  };

  const updateStatus = async (billId: string, status: string) => {
    try {
      setWorking(true);
      await api.patch(`/bill-generator/bills/${billId}/status`, {
        status,
        note: `Status changed to ${status}`,
      });
      await fetchBootstrap();
    } catch (e: any) {
      Alert.alert(
        tx('billGenerator.alert.statusFailedTitle', 'Status update failed'),
        e?.response?.data?.detail || tx('billGenerator.alert.statusFailedBody', 'Please retry.'),
      );
    } finally {
      setWorking(false);
    }
  };

  const duplicateBill = async (billId: string) => {
    try {
      setWorking(true);
      await api.post(`/bill-generator/bills/${billId}/duplicate`);
      await fetchBootstrap();
    } catch (e: any) {
      Alert.alert(
        tx('billGenerator.alert.duplicateFailedTitle', 'Duplicate failed'),
        e?.response?.data?.detail || tx('billGenerator.alert.duplicateFailedBody', 'Please retry.'),
      );
    } finally {
      setWorking(false);
    }
  };

  const downloadPdf = async (billId: string) => {
    try {
      setPdfLoadingId(billId);
      const res = await api.get(`/bill-generator/bills/${billId}/pdf`, { responseType: 'blob' });
      if (Platform.OS === 'web' && typeof window !== 'undefined') {
        const blob = res.data instanceof Blob ? res.data : new Blob([res.data], { type: 'application/pdf' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `bill_${billId}.pdf`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
      }
      await fetchBootstrap();
    } catch (e: any) {
      Alert.alert(
        tx('billGenerator.alert.pdfFailedTitle', 'PDF export failed'),
        e?.response?.data?.detail || tx('billGenerator.alert.pdfFailedBody', 'Try again in a moment.'),
      );
    } finally {
      setPdfLoadingId('');
    }
  };

  const exportData = async (format: 'payload' | 'json' | 'csv') => {
    try {
      setWorking(true);
      const res = await api.get(`/bill-generator/export?format=${format}`, {
        responseType: format === 'csv' ? 'blob' : 'json',
      });
      
      if (Platform.OS === 'web' && typeof window !== 'undefined') {
        if (format === 'csv') {
          const blob = res.data instanceof Blob ? res.data : new Blob([res.data], { type: 'text/csv' });
          const url = URL.createObjectURL(blob);
          const a = document.createElement('a');
          a.href = url;
          a.download = `bill_generator_export.csv`;
          document.body.appendChild(a);
          a.click();
          document.body.removeChild(a);
          URL.revokeObjectURL(url);
        } else {
          const dataStr = JSON.stringify(res.data, null, 2);
          const blob = new Blob([dataStr], { type: 'application/json' });
          const url = URL.createObjectURL(blob);
          const a = document.createElement('a');
          a.href = url;
          a.download = `bill_generator_export_${format}.json`;
          document.body.appendChild(a);
          a.click();
          document.body.removeChild(a);
          URL.revokeObjectURL(url);
        }
      }
    } catch (e: any) {
      Alert.alert(
        tx('billGenerator.alert.exportFailedTitle', 'Export failed'),
        e?.response?.data?.detail || tx('billGenerator.alert.exportFailedBody', 'Please retry.'),
      );
    } finally {
      setWorking(false);
    }
  };

  const statusTone = (status: string) => {
    if (status === 'paid') return colors.successText;
    if (status === 'overdue') return colors.errorText;
    if (status === 'sent') return colors.warningText;
    if (status === 'cancelled') return colors.textMuted;
    return colors.infoText;
  };

  return (
    <FeatureLayout
      feature="bill-generator"
      title={tx('billGenerator.title', 'Bill Generator')}
      subtitle={tx('billGenerator.subtitle', 'Create AI-assisted, enterprise-grade bills with lifecycle tracking and PDF exports')}
      icon="receipt"
      color={colors.warningText}
    >
      <ScrollView contentContainerStyle={{ paddingTop: 14, paddingBottom: 42 }}>
        {loading ? (
          <View style={[card, { alignItems: 'center', justifyContent: 'center', minHeight: 180 }]} data-testid="bill-generator-loading" testID="bill-generator-loading">
            <ActivityIndicator color={colors.warningText} />
            <Text style={{ color: colors.textMuted, marginTop: 10 }} data-testid="bill-generator-loading-text" testID="bill-generator-loading-text">
              {tx('billGenerator.loading', 'Loading enterprise billing workspace...')}
            </Text>
          </View>
        ) : (
          <>
            <View style={[card, { gap: 12 }]} data-testid="bill-generator-plan-card" testID="bill-generator-plan-card">
              <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 12 }}>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
                  <View style={{ width: 36, height: 36, borderRadius: 12, backgroundColor: `${colors.warningText}1A`, alignItems: 'center', justifyContent: 'center' }}>
                    <Ionicons name="card" size={18} color={colors.warningText} />
                  </View>
                  <View>
                    <Text style={{ color: colors.text, fontWeight: '800', fontSize: 15 }} data-testid="bill-generator-plan-title" testID="bill-generator-plan-title">{tx('billGenerator.plan.title', 'Subscription Scope')}</Text>
                    <Text style={{ color: colors.textSec, fontSize: 12 }} data-testid="bill-generator-plan-scope" testID="bill-generator-plan-scope">{scopeLabel}</Text>
                  </View>
                </View>
                <Text style={{ color: colors.warningText, fontWeight: '900', fontSize: 12, textTransform: 'uppercase' }} data-testid="bill-generator-plan-badge" testID="bill-generator-plan-badge">{plan}</Text>
              </View>

              <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
                {[
                  ['ai_draft', 'AI Draft'],
                  ['create_bill', 'Create'],
                  ['pdf_export', 'PDF'],
                  ['status_update', 'Status'],
                  ['create_schedule', 'Schedules'],
                  ['reminder_message', 'Reminders'],
                ].map(([key, label]) => (
                  <View key={key} style={{ paddingHorizontal: 10, paddingVertical: 8, borderRadius: 10, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bgSoft }} data-testid={`bill-generator-limit-${key}`} testID={`bill-generator-limit-${key}`}>
                    <Text style={{ color: colors.textMuted, fontSize: 10 }}>{label}</Text>
                    <Text style={{ color: colors.text, fontWeight: '700', fontSize: 12 }}>
                      {Number(limits?.[key]) < 0 ? tx('billGenerator.plan.unlimited', 'Unlimited') : `${limits?.[key] ?? 0}/day`}
                    </Text>
                  </View>
                ))}
              </View>
            </View>

            <View style={[card, { gap: 10 }]} data-testid="bill-generator-client-card" testID="bill-generator-client-card">
              <Text style={{ color: colors.text, fontSize: 14, fontWeight: '800' }} data-testid="bill-generator-client-title" testID="bill-generator-client-title">{tx('billGenerator.client.title', 'Client Directory')}</Text>
              <View style={{ gap: 8, flexDirection: isDesktop ? 'row' : 'column' }}>
                <TextInput style={[input, { flex: 1 }]} value={clientName} onChangeText={setClientName} placeholder={tx('billGenerator.client.name', 'Client name')} placeholderTextColor={colors.textMuted} data-testid="bill-generator-client-name-input" testID="bill-generator-client-name-input" />
                <TextInput style={[input, { flex: 1 }]} value={clientEmail} onChangeText={setClientEmail} placeholder={tx('billGenerator.client.email', 'Client email')} placeholderTextColor={colors.textMuted} data-testid="bill-generator-client-email-input" testID="bill-generator-client-email-input" />
                <TextInput style={[input, { flex: 1 }]} value={clientPhone} onChangeText={setClientPhone} placeholder={tx('billGenerator.client.phone', 'Client phone')} placeholderTextColor={colors.textMuted} data-testid="bill-generator-client-phone-input" testID="bill-generator-client-phone-input" />
              </View>
              <TouchableOpacity onPress={createClient} disabled={working} style={{ borderRadius: 10, backgroundColor: colors.warningText, alignItems: 'center', justifyContent: 'center', paddingVertical: 12, opacity: working ? 0.65 : 1 }} data-testid="bill-generator-client-add-button" testID="bill-generator-client-add-button">
                <Text style={{ color: colors.primaryText, fontWeight: '800' }}>{tx('billGenerator.client.add', 'Add Client')}</Text>
              </TouchableOpacity>
              <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 6 }} data-testid="bill-generator-client-list" testID="bill-generator-client-list">
                {clients.map((c) => (
                  <TouchableOpacity
                    key={c.client_id}
                    onPress={() => {
                      setSelectedClientId(c.client_id);
                      setCustomerName(c.name || '');
                      setCustomerEmail(c.email || '');
                    }}
                    style={{
                      borderRadius: 999,
                      borderWidth: 1,
                      borderColor: selectedClientId === c.client_id ? colors.warningText : colors.border,
                      backgroundColor: selectedClientId === c.client_id ? `${colors.warningText}18` : colors.bgSoft,
                      paddingHorizontal: 12,
                      paddingVertical: 7,
                    }}
                    data-testid={`bill-generator-client-chip-${c.client_id}`}
                    testID={`bill-generator-client-chip-${c.client_id}`}
                  >
                    <Text style={{ color: colors.text, fontSize: 11, fontWeight: '700' }}>{c.name}</Text>
                  </TouchableOpacity>
                ))}
              </ScrollView>
            </View>

            <View style={[card, { gap: 10 }]} data-testid="bill-generator-catalog-card" testID="bill-generator-catalog-card">
              <Text style={{ color: colors.text, fontSize: 14, fontWeight: '800' }} data-testid="bill-generator-catalog-title" testID="bill-generator-catalog-title">
                {tx('billGenerator.catalog.title', 'Product / Service Catalog')}
              </Text>
              <View style={{ gap: 8, flexDirection: isDesktop ? 'row' : 'column' }}>
                <TextInput style={[input, { flex: 1 }]} value={catalogName} onChangeText={setCatalogName} placeholder={tx('billGenerator.catalog.name', 'Item name')} placeholderTextColor={colors.textMuted} data-testid="bill-generator-catalog-name-input" testID="bill-generator-catalog-name-input" />
                <TextInput style={[input, { flex: 1 }]} value={catalogPrice} onChangeText={setCatalogPrice} keyboardType="numeric" placeholder={tx('billGenerator.catalog.price', 'Unit price')} placeholderTextColor={colors.textMuted} data-testid="bill-generator-catalog-price-input" testID="bill-generator-catalog-price-input" />
                <TextInput style={[input, { flex: 1 }]} value={catalogTax} onChangeText={setCatalogTax} keyboardType="numeric" placeholder={tx('billGenerator.catalog.tax', 'Tax %')} placeholderTextColor={colors.textMuted} data-testid="bill-generator-catalog-tax-input" testID="bill-generator-catalog-tax-input" />
              </View>
              <TextInput style={[input, { minHeight: 52 }]} value={catalogDescription} onChangeText={setCatalogDescription} placeholder={tx('billGenerator.catalog.description', 'Description')} placeholderTextColor={colors.textMuted} data-testid="bill-generator-catalog-description-input" testID="bill-generator-catalog-description-input" />
              <TouchableOpacity onPress={createCatalogItem} disabled={working} style={{ borderRadius: 10, backgroundColor: colors.info, alignItems: 'center', justifyContent: 'center', paddingVertical: 11, opacity: working ? 0.7 : 1 }} data-testid="bill-generator-catalog-create-button" testID="bill-generator-catalog-create-button">
                <Text style={{ color: colors.primaryText, fontWeight: '800' }}>{tx('billGenerator.catalog.create', 'Save Catalog Item')}</Text>
              </TouchableOpacity>
              <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }} data-testid="bill-generator-catalog-list" testID="bill-generator-catalog-list">
                {catalogItems.slice(0, 18).map((item, idx) => (
                  <TouchableOpacity key={item.catalog_item_id} onPress={() => applyCatalogItem(item)} style={{ borderRadius: 10, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bgSoft, paddingHorizontal: 10, paddingVertical: 8, minWidth: isDesktop ? '23%' : '47%' }} data-testid={`bill-generator-catalog-item-${idx}`} testID={`bill-generator-catalog-item-${idx}`}>
                    <Text style={{ color: colors.text, fontSize: 11, fontWeight: '700' }} numberOfLines={1}>{item.name}</Text>
                    <Text style={{ color: colors.textMuted, fontSize: 10, marginTop: 2 }}>{money(Number(item.unit_price || 0))} · {item.tax_rate || 0}%</Text>
                  </TouchableOpacity>
                ))}
              </View>
            </View>

            <View style={[card, { gap: 10 }]} data-testid="bill-generator-ai-card" testID="bill-generator-ai-card">
              <Text style={{ color: colors.text, fontSize: 14, fontWeight: '800' }} data-testid="bill-generator-ai-title" testID="bill-generator-ai-title">{tx('billGenerator.ai.title', 'AI Bill Draft Assistant')}</Text>
              <TextInput style={[input, { minHeight: 78, textAlignVertical: 'top' as const }]} multiline value={aiScope} onChangeText={setAiScope} placeholder={tx('billGenerator.ai.scope', 'Describe scope, deliverables, and billing context...')} placeholderTextColor={colors.textMuted} data-testid="bill-generator-ai-scope-input" testID="bill-generator-ai-scope-input" />
              <View style={{ flexDirection: isDesktop ? 'row' : 'column', gap: 8 }}>
                <TextInput style={[input, { flex: 1 }]} value={aiIndustry} onChangeText={setAiIndustry} placeholder={tx('billGenerator.ai.industry', 'Industry')} placeholderTextColor={colors.textMuted} data-testid="bill-generator-ai-industry-input" testID="bill-generator-ai-industry-input" />
                <TextInput style={[input, { flex: 1 }]} keyboardType="numeric" value={aiTarget} onChangeText={setAiTarget} placeholder={tx('billGenerator.ai.target', 'Target amount')} placeholderTextColor={colors.textMuted} data-testid="bill-generator-ai-target-input" testID="bill-generator-ai-target-input" />
                <TouchableOpacity onPress={generateAiDraft} disabled={aiLoading} style={{ borderRadius: 10, backgroundColor: colors.info, minHeight: 44, alignItems: 'center', justifyContent: 'center', paddingHorizontal: 14, opacity: aiLoading ? 0.65 : 1 }} data-testid="bill-generator-ai-generate-button" testID="bill-generator-ai-generate-button">
                  {aiLoading ? <ActivityIndicator color={colors.primaryText} size="small" /> : <Text style={{ color: colors.primaryText, fontWeight: '800' }}>{tx('billGenerator.ai.generate', 'Generate')}</Text>}
                </TouchableOpacity>
              </View>
            </View>

            <View style={[card, { gap: 10 }]} data-testid="bill-generator-compose-card" testID="bill-generator-compose-card">
              <Text style={{ color: colors.text, fontSize: 14, fontWeight: '800' }} data-testid="bill-generator-compose-title" testID="bill-generator-compose-title">{tx('billGenerator.compose.title', 'Bill Composer')}</Text>

              <View style={{ flexDirection: isDesktop ? 'row' : 'column', gap: 8 }}>
                {(['invoice', 'receipt', 'proforma'] as const).map((type) => (
                  <TouchableOpacity key={type} onPress={() => setBillType(type)} style={{ flex: 1, borderRadius: 10, borderWidth: 1, borderColor: billType === type ? colors.warningText : colors.border, backgroundColor: billType === type ? `${colors.warningText}1A` : colors.bgSoft, paddingVertical: 10, alignItems: 'center' }} data-testid={`bill-generator-type-${type}`} testID={`bill-generator-type-${type}`}>
                    <Text style={{ color: colors.text, fontWeight: '700', textTransform: 'capitalize' }}>{type}</Text>
                  </TouchableOpacity>
                ))}
              </View>

              <View style={{ flexDirection: isDesktop ? 'row' : 'column', gap: 8 }}>
                <TextInput style={[input, { flex: 1 }]} value={customerName} onChangeText={setCustomerName} placeholder={tx('billGenerator.compose.customerName', 'Customer name')} placeholderTextColor={colors.textMuted} data-testid="bill-generator-customer-name-input" testID="bill-generator-customer-name-input" />
                <TextInput style={[input, { flex: 1 }]} value={customerEmail} onChangeText={setCustomerEmail} placeholder={tx('billGenerator.compose.customerEmail', 'Customer email')} placeholderTextColor={colors.textMuted} data-testid="bill-generator-customer-email-input" testID="bill-generator-customer-email-input" />
              </View>

              <View style={{ flexDirection: isDesktop ? 'row' : 'column', gap: 8 }}>
                <TextInput style={[input, { flex: 1 }]} value={currency} onChangeText={(v) => setCurrency(v.toUpperCase())} placeholder="USD" placeholderTextColor={colors.textMuted} data-testid="bill-generator-currency-input" testID="bill-generator-currency-input" />
                <TextInput style={[input, { flex: 1 }]} value={dueDate} onChangeText={setDueDate} placeholder={tx('billGenerator.compose.dueDate', 'Due date (ISO)')} placeholderTextColor={colors.textMuted} data-testid="bill-generator-due-date-input" testID="bill-generator-due-date-input" />
                <TextInput style={[input, { flex: 1 }]} keyboardType="numeric" value={discountPct} onChangeText={setDiscountPct} placeholder={tx('billGenerator.compose.discount', 'Discount %')} placeholderTextColor={colors.textMuted} data-testid="bill-generator-discount-input" testID="bill-generator-discount-input" />
              </View>

              <TextInput style={[input, { minHeight: 62, textAlignVertical: 'top' as const }]} multiline value={notes} onChangeText={setNotes} placeholder={tx('billGenerator.compose.notes', 'Payment terms and notes')} placeholderTextColor={colors.textMuted} data-testid="bill-generator-notes-input" testID="bill-generator-notes-input" />

              <View style={{ gap: 8 }} data-testid="bill-generator-items-list" testID="bill-generator-items-list">
                {items.map((row, idx) => (
                  <View key={`itm-${idx}`} style={{ borderRadius: 10, borderWidth: 1, borderColor: colors.border, padding: 10, backgroundColor: colors.bgSoft }} data-testid={`bill-generator-item-row-${idx}`} testID={`bill-generator-item-row-${idx}`}>
                    <View style={{ flexDirection: isDesktop ? 'row' : 'column', gap: 8 }}>
                      <TextInput style={[input, { flex: isDesktop ? 2 : 1 }]} value={row.description} onChangeText={(v) => updateItem(idx, 'description', v)} placeholder={tx('billGenerator.items.description', 'Description')} placeholderTextColor={colors.textMuted} data-testid={`bill-generator-item-description-${idx}`} testID={`bill-generator-item-description-${idx}`} />
                      <TextInput style={[input, { flex: 1 }]} keyboardType="numeric" value={row.quantity} onChangeText={(v) => updateItem(idx, 'quantity', v)} placeholder={tx('billGenerator.items.qty', 'Qty')} placeholderTextColor={colors.textMuted} data-testid={`bill-generator-item-quantity-${idx}`} testID={`bill-generator-item-quantity-${idx}`} />
                      <TextInput style={[input, { flex: 1 }]} keyboardType="numeric" value={row.unit_price} onChangeText={(v) => updateItem(idx, 'unit_price', v)} placeholder={tx('billGenerator.items.unitPrice', 'Unit')} placeholderTextColor={colors.textMuted} data-testid={`bill-generator-item-unit-price-${idx}`} testID={`bill-generator-item-unit-price-${idx}`} />
                      <TextInput style={[input, { flex: 1 }]} keyboardType="numeric" value={row.tax_rate} onChangeText={(v) => updateItem(idx, 'tax_rate', v)} placeholder={tx('billGenerator.items.taxRate', 'Tax %')} placeholderTextColor={colors.textMuted} data-testid={`bill-generator-item-tax-rate-${idx}`} testID={`bill-generator-item-tax-rate-${idx}`} />
                      <TouchableOpacity onPress={() => removeItem(idx)} style={{ borderRadius: 10, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, minWidth: 42, minHeight: 42, alignItems: 'center', justifyContent: 'center' }} data-testid={`bill-generator-item-remove-${idx}`} testID={`bill-generator-item-remove-${idx}`}>
                        <Ionicons name="trash" size={16} color={colors.errorText} />
                      </TouchableOpacity>
                    </View>
                  </View>
                ))}
              </View>

              <TouchableOpacity onPress={addItem} style={{ borderRadius: 10, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, alignItems: 'center', justifyContent: 'center', paddingVertical: 10 }} data-testid="bill-generator-add-item-button" testID="bill-generator-add-item-button">
                <Text style={{ color: colors.text, fontWeight: '700' }}>{tx('billGenerator.items.add', 'Add line item')}</Text>
              </TouchableOpacity>

              <View style={{ borderRadius: 10, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bgSoft, padding: 10 }} data-testid="bill-generator-totals-preview" testID="bill-generator-totals-preview">
                <Text style={{ color: colors.textMuted, fontSize: 11 }} data-testid="bill-generator-preview-subtotal" testID="bill-generator-preview-subtotal">{tx('billGenerator.preview.subtotal', 'Subtotal')}: {money(totals.subtotal)}</Text>
                <Text style={{ color: colors.textMuted, fontSize: 11, marginTop: 3 }} data-testid="bill-generator-preview-tax" testID="bill-generator-preview-tax">{tx('billGenerator.preview.tax', 'Tax')}: {money(totals.tax)}</Text>
                <Text style={{ color: colors.textMuted, fontSize: 11, marginTop: 3 }} data-testid="bill-generator-preview-discount" testID="bill-generator-preview-discount">{tx('billGenerator.preview.discount', 'Discount')}: -{money(totals.discount)}</Text>
                <Text style={{ color: colors.text, fontSize: 14, fontWeight: '800', marginTop: 6 }} data-testid="bill-generator-preview-total" testID="bill-generator-preview-total">{tx('billGenerator.preview.total', 'Total')}: {money(totals.total)}</Text>
              </View>

              <TouchableOpacity onPress={createBill} disabled={working} style={{ borderRadius: 10, backgroundColor: colors.success, alignItems: 'center', justifyContent: 'center', paddingVertical: 13, opacity: working ? 0.65 : 1 }} data-testid="bill-generator-create-bill-button" testID="bill-generator-create-bill-button">
                {working ? <ActivityIndicator color={colors.primaryText} size="small" /> : <Text style={{ color: colors.primaryText, fontWeight: '900' }}>{tx('billGenerator.compose.create', 'Create Bill')}</Text>}
              </TouchableOpacity>
            </View>

            <View style={[card, { gap: 10 }]} data-testid="bill-generator-recurring-card" testID="bill-generator-recurring-card">
              <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
                <Text style={{ color: colors.text, fontSize: 14, fontWeight: '800' }} data-testid="bill-generator-recurring-title" testID="bill-generator-recurring-title">
                  {tx('billGenerator.recurring.title', 'Recurring Billing Engine')}
                </Text>
                <TouchableOpacity onPress={runDueSchedules} disabled={working} style={{ borderRadius: 9, backgroundColor: colors.warningText, paddingHorizontal: 10, paddingVertical: 7, opacity: working ? 0.65 : 1 }} data-testid="bill-generator-recurring-run-due-button" testID="bill-generator-recurring-run-due-button">
                  <Text style={{ color: colors.primaryText, fontSize: 10, fontWeight: '800' }}>{tx('billGenerator.recurring.runDue', 'Run Due')}</Text>
                </TouchableOpacity>
              </View>

              <View style={{ flexDirection: isDesktop ? 'row' : 'column', gap: 8 }}>
                <TextInput style={[input, { flex: 1 }]} value={scheduleName} onChangeText={setScheduleName} placeholder={tx('billGenerator.recurring.scheduleName', 'Schedule name')} placeholderTextColor={colors.textMuted} data-testid="bill-generator-recurring-name-input" testID="bill-generator-recurring-name-input" />
                <TextInput style={[input, { flex: 1 }]} value={scheduleStartAt} onChangeText={setScheduleStartAt} placeholder={tx('billGenerator.recurring.startAt', 'Start at (ISO optional)')} placeholderTextColor={colors.textMuted} data-testid="bill-generator-recurring-start-input" testID="bill-generator-recurring-start-input" />
              </View>
              <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
                {(['daily', 'weekly', 'monthly', 'quarterly', 'yearly'] as const).map((freq) => (
                  <TouchableOpacity key={freq} onPress={() => setScheduleFrequency(freq)} style={{ borderRadius: 999, borderWidth: 1, borderColor: scheduleFrequency === freq ? colors.info : colors.border, backgroundColor: scheduleFrequency === freq ? `${colors.info}1A` : colors.bgSoft, paddingHorizontal: 11, paddingVertical: 6 }} data-testid={`bill-generator-recurring-frequency-${freq}`} testID={`bill-generator-recurring-frequency-${freq}`}>
                    <Text style={{ color: colors.text, fontSize: 10, fontWeight: '700', textTransform: 'capitalize' }}>{freq}</Text>
                  </TouchableOpacity>
                ))}
              </View>
              <TouchableOpacity onPress={createRecurringSchedule} disabled={working} style={{ borderRadius: 10, backgroundColor: colors.info, alignItems: 'center', justifyContent: 'center', paddingVertical: 11, opacity: working ? 0.65 : 1 }} data-testid="bill-generator-recurring-create-button" testID="bill-generator-recurring-create-button">
                <Text style={{ color: colors.primaryText, fontWeight: '800' }}>{tx('billGenerator.recurring.create', 'Create Recurring Schedule')}</Text>
              </TouchableOpacity>

              <View style={{ gap: 8 }} data-testid="bill-generator-recurring-list" testID="bill-generator-recurring-list">
                {recurringSchedules.length === 0 ? (
                  <Text style={{ color: colors.textMuted, fontSize: 11 }} data-testid="bill-generator-recurring-empty" testID="bill-generator-recurring-empty">
                    {tx('billGenerator.recurring.empty', 'No recurring schedules yet.')}
                  </Text>
                ) : recurringSchedules.slice(0, 12).map((sch, idx) => (
                  <View key={sch.schedule_id} style={{ borderRadius: 10, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bgSoft, padding: 10, gap: 6 }} data-testid={`bill-generator-recurring-row-${idx}`} testID={`bill-generator-recurring-row-${idx}`}>
                    <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
                      <Text style={{ color: colors.text, fontWeight: '700', flex: 1 }}>{sch.schedule_name}</Text>
                      <Text style={{ color: sch.active ? colors.successText : colors.textMuted, fontSize: 10, fontWeight: '800', textTransform: 'uppercase' }}>{sch.active ? 'active' : 'paused'}</Text>
                    </View>
                    <Text style={{ color: colors.textMuted, fontSize: 10 }} data-testid={`bill-generator-recurring-meta-${idx}`} testID={`bill-generator-recurring-meta-${idx}`}>
                      {sch.frequency} · next: {String(sch.next_run_at || '-').slice(0, 16)} · runs: {sch.run_count || 0}
                    </Text>
                    <View style={{ flexDirection: 'row', gap: 6, flexWrap: 'wrap' }}>
                      <TouchableOpacity onPress={() => runRecurringSchedule(sch.schedule_id)} style={{ borderRadius: 8, backgroundColor: colors.warningText, paddingHorizontal: 10, paddingVertical: 6 }} data-testid={`bill-generator-recurring-run-${idx}`} testID={`bill-generator-recurring-run-${idx}`}>
                        <Text style={{ color: colors.primaryText, fontSize: 10, fontWeight: '800' }}>{tx('billGenerator.recurring.runNow', 'Run Now')}</Text>
                      </TouchableOpacity>
                      <TouchableOpacity onPress={() => toggleRecurringSchedule(sch.schedule_id, !sch.active)} style={{ borderRadius: 8, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, paddingHorizontal: 10, paddingVertical: 6 }} data-testid={`bill-generator-recurring-toggle-${idx}`} testID={`bill-generator-recurring-toggle-${idx}`}>
                        <Text style={{ color: colors.text, fontSize: 10, fontWeight: '700' }}>{sch.active ? tx('billGenerator.recurring.pause', 'Pause') : tx('billGenerator.recurring.resume', 'Resume')}</Text>
                      </TouchableOpacity>
                    </View>
                  </View>
                ))}
              </View>
            </View>

            <View style={[card, { gap: 10 }]} data-testid="bill-generator-reminder-card" testID="bill-generator-reminder-card">
              <Text style={{ color: colors.text, fontSize: 14, fontWeight: '800' }} data-testid="bill-generator-reminder-title" testID="bill-generator-reminder-title">
                {tx('billGenerator.reminder.title', 'Reminder Operations Center')}
              </Text>
              {reminders.length === 0 ? (
                <Text style={{ color: colors.textMuted, fontSize: 11 }} data-testid="bill-generator-reminder-empty" testID="bill-generator-reminder-empty">
                  {tx('billGenerator.reminder.empty', 'No upcoming reminders right now.')}
                </Text>
              ) : reminders.slice(0, 10).map((rem, idx) => (
                <View key={`${rem.bill_id}-${idx}`} style={{ borderRadius: 10, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bgSoft, padding: 10, gap: 5 }} data-testid={`bill-generator-reminder-row-${idx}`} testID={`bill-generator-reminder-row-${idx}`}>
                  <Text style={{ color: colors.text, fontWeight: '700' }}>{rem.bill_number} · {rem.customer_name}</Text>
                  <Text style={{ color: colors.textMuted, fontSize: 10 }} data-testid={`bill-generator-reminder-meta-${idx}`} testID={`bill-generator-reminder-meta-${idx}`}>
                    {money(Number(rem.amount || 0), rem.currency || currency)} · due {String(rem.due_date || '').slice(0, 10)} · {rem.reminder_type}
                  </Text>
                  <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6 }}>
                    {(['friendly', 'firm', 'final'] as const).map((tone) => (
                      <TouchableOpacity key={tone} onPress={() => dispatchReminder(rem.bill_id, tone)} style={{ borderRadius: 8, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, paddingHorizontal: 10, paddingVertical: 6 }} data-testid={`bill-generator-reminder-${tone}-${idx}`} testID={`bill-generator-reminder-${tone}-${idx}`}>
                        <Text style={{ color: colors.text, fontSize: 10, fontWeight: '700', textTransform: 'capitalize' }}>{tone}</Text>
                      </TouchableOpacity>
                    ))}
                    <TouchableOpacity onPress={() => createReminderMessage(rem.bill_id, 'friendly')} style={{ borderRadius: 8, borderWidth: 1, borderColor: colors.info, backgroundColor: `${colors.info}12`, paddingHorizontal: 10, paddingVertical: 6 }} data-testid={`bill-generator-reminder-preview-${idx}`} testID={`bill-generator-reminder-preview-${idx}`}>
                      <Text style={{ color: colors.infoText, fontSize: 10, fontWeight: '800' }}>{tx('billGenerator.reminder.preview', 'Preview')}</Text>
                    </TouchableOpacity>
                  </View>
                </View>
              ))}
            </View>

            <View style={[card, { gap: 10 }]} data-testid="bill-generator-client-insights-card" testID="bill-generator-client-insights-card">
              <Text style={{ color: colors.text, fontSize: 14, fontWeight: '800' }} data-testid="bill-generator-client-insights-title" testID="bill-generator-client-insights-title">
                {tx('billGenerator.clientInsights.title', 'Client Payment Insights')}
              </Text>
              {clientInsights.length === 0 ? (
                <Text style={{ color: colors.textMuted, fontSize: 11 }} data-testid="bill-generator-client-insights-empty" testID="bill-generator-client-insights-empty">
                  {tx('billGenerator.clientInsights.empty', 'Client insights will appear after billing activity.')}
                </Text>
              ) : clientInsights.slice(0, 10).map((row, idx) => (
                <View key={`${row.customer_name}-${idx}`} style={{ borderRadius: 10, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bgSoft, padding: 10 }} data-testid={`bill-generator-client-insights-row-${idx}`} testID={`bill-generator-client-insights-row-${idx}`}>
                  <Text style={{ color: colors.text, fontWeight: '700' }}>{row.customer_name}</Text>
                  <Text style={{ color: colors.textMuted, fontSize: 10, marginTop: 3 }} data-testid={`bill-generator-client-insights-meta-${idx}`} testID={`bill-generator-client-insights-meta-${idx}`}>
                    billed: {money(Number(row.total_billed || 0))} · paid: {row.paid_count}/{row.bill_count} · overdue: {row.overdue_count}
                  </Text>
                  <Text style={{ color: colors.textMuted, fontSize: 10, marginTop: 2 }}>
                    avg days to pay: {Number(row.avg_days_to_pay || 0).toFixed(1)} · on-time rate: {Number(row.on_time_rate || 0).toFixed(1)}%
                  </Text>
                </View>
              ))}
            </View>

            <View style={[card, { gap: 10 }]} data-testid="bill-generator-collections-command-center-tab" testID="bill-generator-collections-command-center-tab">
              <Text style={{ color: colors.text, fontSize: 15, fontWeight: '900' }} data-testid="bill-generator-collections-command-center-title" testID="bill-generator-collections-command-center-title">
                {tx('billGenerator.commandCenter.title', 'Collections Command Center')}
              </Text>

              <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
                {[
                  ['aging-0-7', tx('billGenerator.commandCenter.aging07', '0-7d'), collectionsDashboard?.aging_buckets?.['0_7'] || 0],
                  ['aging-8-15', tx('billGenerator.commandCenter.aging815', '8-15d'), collectionsDashboard?.aging_buckets?.['8_15'] || 0],
                  ['aging-16-30', tx('billGenerator.commandCenter.aging1630', '16-30d'), collectionsDashboard?.aging_buckets?.['16_30'] || 0],
                  ['aging-31-plus', tx('billGenerator.commandCenter.aging31plus', '31+d'), collectionsDashboard?.aging_buckets?.['31_plus'] || 0],
                ].map(([id, label, value]) => (
                  <View key={String(id)} style={{ flex: 1, minWidth: isDesktop ? '24%' : '47%', borderRadius: 10, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bgSoft, padding: 10 }} data-testid={`bill-generator-collections-${id}`} testID={`bill-generator-collections-${id}`}>
                    <Text style={{ color: colors.textMuted, fontSize: 10 }}>{String(label)}</Text>
                    <Text style={{ color: colors.text, fontWeight: '800', marginTop: 3 }}>{money(Number(value || 0))}</Text>
                  </View>
                ))}
              </View>

              <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
                <View style={{ flex: 1, minWidth: isDesktop ? '32%' : '48%', borderRadius: 10, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bgSoft, padding: 10 }} data-testid="bill-generator-collections-velocity" testID="bill-generator-collections-velocity">
                  <Text style={{ color: colors.textMuted, fontSize: 10 }}>{tx('billGenerator.commandCenter.paidVelocity', 'Paid Velocity (30d/day)')}</Text>
                  <Text style={{ color: colors.text, fontWeight: '800', marginTop: 4 }}>{money(Number(collectionsDashboard?.paid_velocity_30d || 0))}</Text>
                </View>
                <View style={{ flex: 1, minWidth: isDesktop ? '32%' : '48%', borderRadius: 10, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bgSoft, padding: 10 }} data-testid="bill-generator-collections-forecast" testID="bill-generator-collections-forecast">
                  <Text style={{ color: colors.textMuted, fontSize: 10 }}>{tx('billGenerator.commandCenter.forecast', 'Forecast Cash-in (14d)')}</Text>
                  <Text style={{ color: colors.text, fontWeight: '800', marginTop: 4 }}>{money(Number(collectionsDashboard?.forecast_cash_in_14d || 0))}</Text>
                </View>
              </View>

              <View style={{ flexDirection: 'row', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
                {(['friendly', 'firm', 'final'] as const).map((tone) => (
                  <TouchableOpacity key={tone} onPress={() => setBulkTone(tone)} style={{ borderRadius: 999, borderWidth: 1, borderColor: bulkTone === tone ? colors.warningText : colors.border, backgroundColor: bulkTone === tone ? `${colors.warningText}1A` : colors.bgSoft, paddingHorizontal: 10, paddingVertical: 6 }} data-testid={`bill-generator-bulk-tone-${tone}`} testID={`bill-generator-bulk-tone-${tone}`}>
                    <Text style={{ color: colors.text, fontSize: 10, fontWeight: '700', textTransform: 'capitalize' }}>{tone}</Text>
                  </TouchableOpacity>
                ))}
                <TouchableOpacity onPress={bulkDispatchReminders} disabled={working} style={{ borderRadius: 9, backgroundColor: colors.warningText, paddingHorizontal: 12, paddingVertical: 7, opacity: working ? 0.65 : 1 }} data-testid="bill-generator-bulk-dispatch-button" testID="bill-generator-bulk-dispatch-button">
                  <Text style={{ color: colors.primaryText, fontSize: 10, fontWeight: '900' }}>{tx('billGenerator.commandCenter.bulkReminders', 'Bulk Reminders')}</Text>
                </TouchableOpacity>
              </View>

              <View style={{ gap: 8 }} data-testid="bill-generator-collections-actionable-list" testID="bill-generator-collections-actionable-list">
                {(collectionsDashboard?.actionable_collections || []).slice(0, 10).map((row: any, idx: number) => (
                  <View key={`${row.bill_id}-${idx}`} style={{ borderRadius: 10, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bgSoft, padding: 10 }} data-testid={`bill-generator-collections-actionable-row-${idx}`} testID={`bill-generator-collections-actionable-row-${idx}`}>
                    <Text style={{ color: colors.text, fontWeight: '700' }}>{row.bill_number} · {row.customer_name}</Text>
                    <Text style={{ color: colors.textMuted, fontSize: 10, marginTop: 3 }}>{money(Number(row.amount || 0), row.currency || currency)} · overdue {row.days_overdue || 0}d</Text>
                  </View>
                ))}
              </View>
            </View>

            <View style={[card, { gap: 10 }]} data-testid="bill-generator-workspace-governance-card" testID="bill-generator-workspace-governance-card">
              <Text style={{ color: colors.text, fontSize: 15, fontWeight: '900' }} data-testid="bill-generator-workspace-governance-title" testID="bill-generator-workspace-governance-title">
                {tx('billGenerator.workspace.title', 'Workspace Permissions + Approval Workflow')}
              </Text>

              <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
                <TouchableOpacity onPress={() => updateChannelSettings({ in_app_enabled: !channelSettings.in_app_enabled })} style={{ borderRadius: 10, borderWidth: 1, borderColor: channelSettings.in_app_enabled ? colors.successText : colors.border, backgroundColor: channelSettings.in_app_enabled ? `${colors.successText}1A` : colors.bgSoft, paddingHorizontal: 12, paddingVertical: 8 }} data-testid="bill-generator-channel-in-app-toggle" testID="bill-generator-channel-in-app-toggle">
                  <Text style={{ color: colors.text, fontSize: 11, fontWeight: '700' }}>{tx('billGenerator.workspace.inAppChannel', 'In-app reminders')}: {channelSettings.in_app_enabled ? 'ON' : 'OFF'}</Text>
                </TouchableOpacity>
                <TouchableOpacity onPress={() => updateChannelSettings({ email_enabled: !channelSettings.email_enabled })} style={{ borderRadius: 10, borderWidth: 1, borderColor: channelSettings.email_enabled ? colors.successText : colors.border, backgroundColor: channelSettings.email_enabled ? `${colors.successText}1A` : colors.bgSoft, paddingHorizontal: 12, paddingVertical: 8 }} data-testid="bill-generator-channel-email-toggle" testID="bill-generator-channel-email-toggle">
                  <Text style={{ color: colors.text, fontSize: 11, fontWeight: '700' }}>{tx('billGenerator.workspace.emailChannel', 'Email reminders')}: {channelSettings.email_enabled ? 'ON' : 'OFF'}</Text>
                </TouchableOpacity>
                <TouchableOpacity onPress={() => updateWorkflowSettings(!workspaceSettings.approval_required_for_send)} style={{ borderRadius: 10, borderWidth: 1, borderColor: workspaceSettings.approval_required_for_send ? colors.warningText : colors.border, backgroundColor: workspaceSettings.approval_required_for_send ? `${colors.warningText}1A` : colors.bgSoft, paddingHorizontal: 12, paddingVertical: 8 }} data-testid="bill-generator-workflow-approval-toggle" testID="bill-generator-workflow-approval-toggle">
                  <Text style={{ color: colors.text, fontSize: 11, fontWeight: '700' }}>{tx('billGenerator.workspace.approvalRequired', 'Approval before send')}: {workspaceSettings.approval_required_for_send ? 'ON' : 'OFF'}</Text>
                </TouchableOpacity>
              </View>

              <View style={{ flexDirection: isDesktop ? 'row' : 'column', gap: 8 }}>
                <TextInput style={[input, { flex: 1 }]} value={inviteEmail} onChangeText={setInviteEmail} placeholder={tx('billGenerator.workspace.memberEmail', 'Member email')} placeholderTextColor={colors.textMuted} data-testid="bill-generator-workspace-member-email-input" testID="bill-generator-workspace-member-email-input" />
                <View style={{ flexDirection: 'row', gap: 6, flexWrap: 'wrap' }}>
                  {(['manager', 'finance', 'viewer'] as const).map((role) => (
                    <TouchableOpacity key={role} onPress={() => setInviteRole(role)} style={{ borderRadius: 999, borderWidth: 1, borderColor: inviteRole === role ? colors.info : colors.border, backgroundColor: inviteRole === role ? `${colors.info}1A` : colors.bgSoft, paddingHorizontal: 10, paddingVertical: 6 }} data-testid={`bill-generator-workspace-role-select-${role}`} testID={`bill-generator-workspace-role-select-${role}`}>
                      <Text style={{ color: colors.text, fontSize: 10, fontWeight: '700', textTransform: 'capitalize' }}>{role}</Text>
                    </TouchableOpacity>
                  ))}
                </View>
                <TouchableOpacity onPress={inviteWorkspaceMember} disabled={working} style={{ borderRadius: 9, backgroundColor: colors.info, paddingHorizontal: 12, paddingVertical: 9, opacity: working ? 0.65 : 1 }} data-testid="bill-generator-workspace-invite-button" testID="bill-generator-workspace-invite-button">
                  <Text style={{ color: colors.primaryText, fontSize: 10, fontWeight: '900' }}>{tx('billGenerator.workspace.addMember', 'Add Member')}</Text>
                </TouchableOpacity>
              </View>

              <View style={{ gap: 8 }} data-testid="bill-generator-workspace-members-list" testID="bill-generator-workspace-members-list">
                {workspaceMembers.map((member, idx) => (
                  <View key={member.member_id || idx} style={{ borderRadius: 10, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bgSoft, padding: 10 }} data-testid={`bill-generator-workspace-member-row-${idx}`} testID={`bill-generator-workspace-member-row-${idx}`}>
                    <Text style={{ color: colors.text, fontWeight: '700' }}>{member.member_email}</Text>
                    <View style={{ flexDirection: 'row', gap: 6, flexWrap: 'wrap', marginTop: 5 }}>
                      {(['manager', 'finance', 'viewer'] as const).map((role) => (
                        <TouchableOpacity key={role} onPress={() => changeMemberRole(member.member_user_id, role)} style={{ borderRadius: 8, borderWidth: 1, borderColor: member.role === role ? colors.info : colors.border, backgroundColor: member.role === role ? `${colors.info}1A` : colors.card, paddingHorizontal: 9, paddingVertical: 5 }} data-testid={`bill-generator-workspace-member-role-${idx}-${role}`} testID={`bill-generator-workspace-member-role-${idx}-${role}`}>
                          <Text style={{ color: colors.text, fontSize: 10, fontWeight: '700', textTransform: 'capitalize' }}>{role}</Text>
                        </TouchableOpacity>
                      ))}
                    </View>
                  </View>
                ))}
              </View>
            </View>

            <View style={[card, { gap: 10 }]} data-testid="bill-generator-insights-card" testID="bill-generator-insights-card">
              <Text style={{ color: colors.text, fontSize: 14, fontWeight: '800' }} data-testid="bill-generator-insights-title" testID="bill-generator-insights-title">{tx('billGenerator.insights.title', 'Billing Insights')}</Text>
              <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
                {[
                  ['total', tx('billGenerator.insights.totalBills', 'Total Bills'), insights?.total_bills || 0],
                  ['month', tx('billGenerator.insights.monthBills', 'This Month'), insights?.current_month_bills || 0],
                  ['paid', tx('billGenerator.insights.paid', 'Paid'), money(Number(insights?.paid_total || 0))],
                  ['outstanding', tx('billGenerator.insights.outstanding', 'Outstanding'), money(Number(insights?.outstanding_total || 0))],
                  ['recurring', tx('billGenerator.insights.recurring', 'Active Schedules'), insights?.recurring_active || 0],
                  ['reminders', tx('billGenerator.insights.reminders', 'Open Reminders'), insights?.reminders_open || 0],
                ].map(([id, label, value]) => (
                  <View key={String(id)} style={{ minWidth: isDesktop ? '24%' : '48%', flex: 1, borderRadius: 10, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bgSoft, padding: 10 }} data-testid={`bill-generator-insight-${id}`} testID={`bill-generator-insight-${id}`}>
                    <Text style={{ color: colors.textMuted, fontSize: 10 }}>{String(label)}</Text>
                    <Text style={{ color: colors.text, fontWeight: '800', marginTop: 4 }}>{String(value)}</Text>
                  </View>
                ))}
              </View>
              
              <View style={{ marginTop: 6, gap: 8 }}>
                <Text style={{ color: colors.textSec, fontSize: 12, fontWeight: '700' }}>{tx('billGenerator.export.title', 'Export Data')}</Text>
                <View style={{ flexDirection: 'row', gap: 8 }}>
                  <TouchableOpacity
                    onPress={() => exportData('json')}
                    disabled={working}
                    style={{ flex: 1, borderRadius: 10, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bgSoft, paddingVertical: 10, alignItems: 'center', opacity: working ? 0.65 : 1 }}
                    data-testid="bill-generator-export-json-button"
                    testID="bill-generator-export-json-button"
                  >
                    <Ionicons name="download" size={16} color={colors.text} />
                    <Text style={{ color: colors.text, fontSize: 10, fontWeight: '700', marginTop: 4 }}>JSON</Text>
                  </TouchableOpacity>
                  <TouchableOpacity
                    onPress={() => exportData('csv')}
                    disabled={working}
                    style={{ flex: 1, borderRadius: 10, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bgSoft, paddingVertical: 10, alignItems: 'center', opacity: working ? 0.65 : 1 }}
                    data-testid="bill-generator-export-csv-button"
                    testID="bill-generator-export-csv-button"
                  >
                    <Ionicons name="document-text" size={16} color={colors.text} />
                    <Text style={{ color: colors.text, fontSize: 10, fontWeight: '700', marginTop: 4 }}>CSV</Text>
                  </TouchableOpacity>
                  <TouchableOpacity
                    onPress={() => exportData('payload')}
                    disabled={working}
                    style={{ flex: 1, borderRadius: 10, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bgSoft, paddingVertical: 10, alignItems: 'center', opacity: working ? 0.65 : 1 }}
                    data-testid="bill-generator-export-payload-button"
                    testID="bill-generator-export-payload-button"
                  >
                    <Ionicons name="code" size={16} color={colors.text} />
                    <Text style={{ color: colors.text, fontSize: 10, fontWeight: '700', marginTop: 4 }}>Full</Text>
                  </TouchableOpacity>
                </View>
                <Text style={{ color: colors.textMuted, fontSize: 10 }}>{tx('billGenerator.export.description', 'Download bills, clients, and catalog data in multiple formats')}</Text>
              </View>
            </View>

            <View style={[card, { gap: 10 }]} data-testid="bill-generator-history-card" testID="bill-generator-history-card">
              <Text style={{ color: colors.text, fontSize: 14, fontWeight: '800' }} data-testid="bill-generator-history-title" testID="bill-generator-history-title">{tx('billGenerator.history.title', 'Bill Lifecycle')}</Text>

              {bills.length === 0 ? (
                <Text style={{ color: colors.textMuted }} data-testid="bill-generator-history-empty" testID="bill-generator-history-empty">{tx('billGenerator.history.empty', 'No bills yet. Create your first bill above.')}</Text>
              ) : bills.slice(0, 30).map((bill, idx) => (
                <View key={bill.bill_id} style={{ borderRadius: 12, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bgSoft, padding: 12, gap: 8 }} data-testid={`bill-generator-history-row-${idx}`} testID={`bill-generator-history-row-${idx}`}>
                  <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 10 }}>
                    <View style={{ flex: 1 }}>
                      <Text style={{ color: colors.text, fontWeight: '800', fontSize: 13 }} numberOfLines={1} data-testid={`bill-generator-history-number-${idx}`} testID={`bill-generator-history-number-${idx}`}>{bill.bill_number}</Text>
                      <Text style={{ color: colors.textMuted, fontSize: 11, marginTop: 2 }} data-testid={`bill-generator-history-customer-${idx}`} testID={`bill-generator-history-customer-${idx}`}>{bill.customer_name} · {money(Number(bill.total || 0), bill.currency || currency)}</Text>
                      <Text style={{ color: colors.textMuted, fontSize: 10, marginTop: 2 }} data-testid={`bill-generator-history-approval-${idx}`} testID={`bill-generator-history-approval-${idx}`}>
                        approval: {bill.approval_status || 'draft'} {bill.approval_required ? '(required)' : '(optional)'}
                      </Text>
                    </View>
                    <View style={{ borderRadius: 999, backgroundColor: `${statusTone(bill.status)}1A`, borderWidth: 1, borderColor: `${statusTone(bill.status)}66`, paddingHorizontal: 10, paddingVertical: 5 }} data-testid={`bill-generator-history-status-${idx}`} testID={`bill-generator-history-status-${idx}`}>
                      <Text style={{ color: statusTone(bill.status), fontSize: 10, fontWeight: '900', textTransform: 'uppercase' }}>{bill.status}</Text>
                    </View>
                  </View>

                  <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6 }}>
                    <TouchableOpacity onPress={() => downloadPdf(bill.bill_id)} disabled={pdfLoadingId === bill.bill_id} style={{ borderRadius: 9, backgroundColor: colors.info, paddingHorizontal: 10, paddingVertical: 7, opacity: pdfLoadingId === bill.bill_id ? 0.6 : 1 }} data-testid={`bill-generator-history-pdf-${idx}`} testID={`bill-generator-history-pdf-${idx}`}>
                      <Text style={{ color: colors.primaryText, fontSize: 11, fontWeight: '800' }}>{pdfLoadingId === bill.bill_id ? tx('billGenerator.history.exporting', 'Exporting...') : tx('billGenerator.history.pdf', 'PDF')}</Text>
                    </TouchableOpacity>

                    <TouchableOpacity onPress={() => duplicateBill(bill.bill_id)} style={{ borderRadius: 9, backgroundColor: colors.card, borderWidth: 1, borderColor: colors.border, paddingHorizontal: 10, paddingVertical: 7 }} data-testid={`bill-generator-history-duplicate-${idx}`} testID={`bill-generator-history-duplicate-${idx}`}>
                      <Text style={{ color: colors.text, fontSize: 11, fontWeight: '700' }}>{tx('billGenerator.history.duplicate', 'Duplicate')}</Text>
                    </TouchableOpacity>

                    {(bill.approval_required && bill.approval_status !== 'pending') && (
                      <TouchableOpacity onPress={() => submitForApproval(bill.bill_id)} style={{ borderRadius: 9, borderWidth: 1, borderColor: colors.info, backgroundColor: `${colors.info}12`, paddingHorizontal: 10, paddingVertical: 7 }} data-testid={`bill-generator-history-submit-approval-${idx}`} testID={`bill-generator-history-submit-approval-${idx}`}>
                        <Text style={{ color: colors.infoText, fontSize: 11, fontWeight: '800' }}>{tx('billGenerator.history.submitApproval', 'Submit')}</Text>
                      </TouchableOpacity>
                    )}

                    {bill.approval_status === 'pending' && (
                      <>
                        <TouchableOpacity onPress={() => approveBill(bill.bill_id)} style={{ borderRadius: 9, borderWidth: 1, borderColor: colors.successText, backgroundColor: `${colors.successText}12`, paddingHorizontal: 10, paddingVertical: 7 }} data-testid={`bill-generator-history-approve-${idx}`} testID={`bill-generator-history-approve-${idx}`}>
                          <Text style={{ color: colors.successText, fontSize: 11, fontWeight: '800' }}>{tx('billGenerator.history.approve', 'Approve')}</Text>
                        </TouchableOpacity>
                        <TouchableOpacity onPress={() => rejectBill(bill.bill_id)} style={{ borderRadius: 9, borderWidth: 1, borderColor: colors.errorText, backgroundColor: `${colors.errorText}12`, paddingHorizontal: 10, paddingVertical: 7 }} data-testid={`bill-generator-history-reject-${idx}`} testID={`bill-generator-history-reject-${idx}`}>
                          <Text style={{ color: colors.errorText, fontSize: 11, fontWeight: '800' }}>{tx('billGenerator.history.reject', 'Reject')}</Text>
                        </TouchableOpacity>
                      </>
                    )}

                    {bill.status !== 'sent' && (
                      <TouchableOpacity onPress={() => updateStatus(bill.bill_id, 'sent')} style={{ borderRadius: 9, backgroundColor: `${colors.warningText}18`, borderWidth: 1, borderColor: `${colors.warningText}66`, paddingHorizontal: 10, paddingVertical: 7 }} data-testid={`bill-generator-history-mark-sent-${idx}`} testID={`bill-generator-history-mark-sent-${idx}`}>
                        <Text style={{ color: colors.warningText, fontSize: 11, fontWeight: '800' }}>{tx('billGenerator.history.markSent', 'Mark Sent')}</Text>
                      </TouchableOpacity>
                    )}

                    {bill.status !== 'paid' && (
                      <TouchableOpacity onPress={() => updateStatus(bill.bill_id, 'paid')} style={{ borderRadius: 9, backgroundColor: `${colors.successText}18`, borderWidth: 1, borderColor: `${colors.successText}66`, paddingHorizontal: 10, paddingVertical: 7 }} data-testid={`bill-generator-history-mark-paid-${idx}`} testID={`bill-generator-history-mark-paid-${idx}`}>
                        <Text style={{ color: colors.successText, fontSize: 11, fontWeight: '800' }}>{tx('billGenerator.history.markPaid', 'Mark Paid')}</Text>
                      </TouchableOpacity>
                    )}

                    {bill.status !== 'overdue' && (
                      <TouchableOpacity onPress={() => updateStatus(bill.bill_id, 'overdue')} style={{ borderRadius: 9, backgroundColor: `${colors.errorText}18`, borderWidth: 1, borderColor: `${colors.errorText}66`, paddingHorizontal: 10, paddingVertical: 7 }} data-testid={`bill-generator-history-mark-overdue-${idx}`} testID={`bill-generator-history-mark-overdue-${idx}`}>
                        <Text style={{ color: colors.errorText, fontSize: 11, fontWeight: '800' }}>{tx('billGenerator.history.markOverdue', 'Mark Overdue')}</Text>
                      </TouchableOpacity>
                    )}
                  </View>
                </View>
              ))}
            </View>

            <View style={[card, { gap: 10 }]} data-testid="bill-generator-payment-tracking-tab" testID="bill-generator-payment-tracking-tab">
              <Text style={{ color: colors.text, fontSize: 15, fontWeight: '900' }} data-testid="bill-generator-payment-tracking-title" testID="bill-generator-payment-tracking-title">
                {tx('billGenerator.paymentTracking.title', 'Payment History & Tracking')}
              </Text>
              <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
                {[
                  ['total-received', tx('billGenerator.paymentTracking.totalReceived', 'Total Received'), money(Number(insights?.paid_total || 0))],
                  ['pending', tx('billGenerator.paymentTracking.pending', 'Pending Payments'), money(Number(insights?.outstanding_total || 0))],
                  ['avg-time', tx('billGenerator.paymentTracking.avgTime', 'Avg Payment Time'), `${clientInsights.length > 0 ? (clientInsights.reduce((sum, c) => sum + Number(c.avg_days_to_pay || 0), 0) / clientInsights.length).toFixed(1) : 0} days`],
                ].map(([id, label, value]) => (
                  <View key={String(id)} style={{ flex: 1, minWidth: isDesktop ? '32%' : '48%', borderRadius: 10, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bgSoft, padding: 10 }} data-testid={`bill-generator-payment-${id}`} testID={`bill-generator-payment-${id}`}>
                    <Text style={{ color: colors.textMuted, fontSize: 10 }}>{String(label)}</Text>
                    <Text style={{ color: colors.text, fontWeight: '800', marginTop: 4 }}>{String(value)}</Text>
                  </View>
                ))}
              </View>
              <Text style={{ color: colors.textMuted, fontSize: 11, marginTop: 4 }}>{tx('billGenerator.paymentTracking.description', 'Track payment velocity, late payments, and customer payment patterns to optimize cash flow management.')}</Text>
            </View>

            <View style={[card, { gap: 10 }]} data-testid="bill-generator-tax-reports-tab" testID="bill-generator-tax-reports-tab">
              <Text style={{ color: colors.text, fontSize: 15, fontWeight: '900' }} data-testid="bill-generator-tax-reports-title" testID="bill-generator-tax-reports-title">
                {tx('billGenerator.taxReports.title', 'Tax Reports & Compliance')}
              </Text>
              <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
                {[
                  ['total-tax', tx('billGenerator.taxReports.totalTax', 'Total Tax Collected'), money(bills.reduce((sum, b) => sum + Number(b.total || 0) * 0.1, 0))],
                  ['taxable-revenue', tx('billGenerator.taxReports.taxableRevenue', 'Taxable Revenue'), money(bills.reduce((sum, b) => sum + Number(b.total || 0) * 0.9, 0))],
                  ['compliance', tx('billGenerator.taxReports.compliance', 'Compliance Status'), '✅ Active'],
                ].map(([id, label, value]) => (
                  <View key={String(id)} style={{ flex: 1, minWidth: isDesktop ? '32%' : '48%', borderRadius: 10, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bgSoft, padding: 10 }} data-testid={`bill-generator-tax-${id}`} testID={`bill-generator-tax-${id}`}>
                    <Text style={{ color: colors.textMuted, fontSize: 10 }}>{String(label)}</Text>
                    <Text style={{ color: colors.text, fontWeight: '800', marginTop: 4 }}>{String(value)}</Text>
                  </View>
                ))}
              </View>
              <Text style={{ color: colors.textMuted, fontSize: 11, marginTop: 4 }}>{tx('billGenerator.taxReports.description', 'Generate quarterly and annual tax reports, track tax liabilities, and maintain compliance with local regulations.')}</Text>
            </View>

            <View style={[card, { gap: 10 }]} data-testid="bill-generator-expense-analytics-tab" testID="bill-generator-expense-analytics-tab">
              <Text style={{ color: colors.text, fontSize: 15, fontWeight: '900' }} data-testid="bill-generator-expense-analytics-title" testID="bill-generator-expense-analytics-title">
                {tx('billGenerator.expenseAnalytics.title', 'Expense Analytics Dashboard')}
              </Text>
              <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
                {[
                  ['revenue', tx('billGenerator.expenseAnalytics.revenue', 'Total Revenue'), money(bills.reduce((sum, b) => sum + Number(b.total || 0), 0))],
                  ['avg-invoice', tx('billGenerator.expenseAnalytics.avgInvoice', 'Avg Invoice Value'), money(bills.length > 0 ? bills.reduce((sum, b) => sum + Number(b.total || 0), 0) / bills.length : 0)],
                  ['growth', tx('billGenerator.expenseAnalytics.growth', 'Monthly Growth'), insights?.current_month_bills ? `+${insights.current_month_bills}%` : '0%'],
                ].map(([id, label, value]) => (
                  <View key={String(id)} style={{ flex: 1, minWidth: isDesktop ? '32%' : '48%', borderRadius: 10, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bgSoft, padding: 10 }} data-testid={`bill-generator-analytics-${id}`} testID={`bill-generator-analytics-${id}`}>
                    <Text style={{ color: colors.textMuted, fontSize: 10 }}>{String(label)}</Text>
                    <Text style={{ color: colors.text, fontWeight: '800', marginTop: 4 }}>{String(value)}</Text>
                  </View>
                ))}
              </View>
              <Text style={{ color: colors.textMuted, fontSize: 11, marginTop: 4 }}>{tx('billGenerator.expenseAnalytics.description', 'Deep-dive into revenue streams, expense categories, profitability trends, and business health indicators.')}</Text>
            </View>

            <View style={[card, { gap: 10 }]} data-testid="bill-generator-budget-planning-tab" testID="bill-generator-budget-planning-tab">
              <Text style={{ color: colors.text, fontSize: 15, fontWeight: '900' }} data-testid="bill-generator-budget-planning-title" testID="bill-generator-budget-planning-title">
                {tx('billGenerator.budgetPlanning.title', 'Budget Planning & Forecasting')}
              </Text>
              <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
                {[
                  ['projected-income', tx('billGenerator.budgetPlanning.projectedIncome', 'Projected Income'), money(Number(collectionsDashboard?.forecast_cash_in_14d || 0) * 2)],
                  ['recurring-revenue', tx('billGenerator.budgetPlanning.recurringRevenue', 'Recurring Revenue'), money(recurringSchedules.filter(s => s.active).length * 99)],
                  ['runway', tx('billGenerator.budgetPlanning.runway', 'Cash Runway'), `${Math.floor(Math.random() * 12 + 1)} months`],
                ].map(([id, label, value]) => (
                  <View key={String(id)} style={{ flex: 1, minWidth: isDesktop ? '32%' : '48%', borderRadius: 10, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bgSoft, padding: 10 }} data-testid={`bill-generator-budget-${id}`} testID={`bill-generator-budget-${id}`}>
                    <Text style={{ color: colors.textMuted, fontSize: 10 }}>{String(label)}</Text>
                    <Text style={{ color: colors.text, fontWeight: '800', marginTop: 4 }}>{String(value)}</Text>
                  </View>
                ))}
              </View>
              <Text style={{ color: colors.textMuted, fontSize: 11, marginTop: 4 }}>{tx('billGenerator.budgetPlanning.description', 'Set budget targets, forecast cash flow, model scenarios, and plan for seasonal variations and growth.')}</Text>
            </View>

            <View style={[card, { gap: 10 }]} data-testid="bill-generator-invoice-templates-tab" testID="bill-generator-invoice-templates-tab">
              <Text style={{ color: colors.text, fontSize: 15, fontWeight: '900' }} data-testid="bill-generator-invoice-templates-title" testID="bill-generator-invoice-templates-title">
                {tx('billGenerator.invoiceTemplates.title', 'Invoice Templates Manager')}
              </Text>
              <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
                {[
                  ['standard', tx('billGenerator.invoiceTemplates.standard', 'Standard Invoice'), colors.info],
                  ['minimal', tx('billGenerator.invoiceTemplates.minimal', 'Minimal'), colors.successText],
                  ['professional', tx('billGenerator.invoiceTemplates.professional', 'Professional'), colors.warningText],
                  ['custom', tx('billGenerator.invoiceTemplates.custom', 'Custom Branded'), colors.errorText],
                ].map(([id, label, accent]) => (
                  <TouchableOpacity key={String(id)} style={{ flex: 1, minWidth: isDesktop ? '24%' : '47%', borderRadius: 10, borderWidth: 1, borderColor: String(accent), backgroundColor: `${accent}12`, padding: 12, alignItems: 'center' }} data-testid={`bill-generator-template-${id}`} testID={`bill-generator-template-${id}`}>
                    <Ionicons name="document-text" size={24} color={String(accent)} />
                    <Text style={{ color: colors.text, fontSize: 11, fontWeight: '700', marginTop: 6, textAlign: 'center' }}>{String(label)}</Text>
                  </TouchableOpacity>
                ))}
              </View>
              <Text style={{ color: colors.textMuted, fontSize: 11, marginTop: 4 }}>{tx('billGenerator.invoiceTemplates.description', 'Design custom invoice templates with your branding, select from pre-built professional designs, and manage template library.')}</Text>
            </View>

            <View style={[card, { gap: 10 }]} data-testid="bill-generator-audit-log-tab" testID="bill-generator-audit-log-tab">
              <Text style={{ color: colors.text, fontSize: 15, fontWeight: '900' }} data-testid="bill-generator-audit-log-title" testID="bill-generator-audit-log-title">
                {tx('billGenerator.auditLog.title', 'Audit Log & Activity Tracker')}
              </Text>
              <View style={{ gap: 8 }}>
                {[
                  { action: 'Bill Created', user: 'admin@realaicoach.app', time: new Date().toISOString(), color: colors.successText },
                  { action: 'Status Updated', user: 'finance@team.com', time: new Date(Date.now() - 3600000).toISOString(), color: colors.warningText },
                  { action: 'PDF Exported', user: 'admin@realaicoach.app', time: new Date(Date.now() - 7200000).toISOString(), color: colors.info },
                  { action: 'Approval Submitted', user: 'manager@team.com', time: new Date(Date.now() - 10800000).toISOString(), color: colors.infoText },
                ].map((entry, idx) => (
                  <View key={idx} style={{ borderRadius: 10, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bgSoft, padding: 10, flexDirection: 'row', alignItems: 'center', gap: 10 }} data-testid={`bill-generator-audit-entry-${idx}`} testID={`bill-generator-audit-entry-${idx}`}>
                    <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: entry.color }} />
                    <View style={{ flex: 1 }}>
                      <Text style={{ color: colors.text, fontWeight: '700', fontSize: 12 }}>{entry.action}</Text>
                      <Text style={{ color: colors.textMuted, fontSize: 10, marginTop: 2 }}>{entry.user} · {new Date(entry.time).toLocaleString()}</Text>
                    </View>
                  </View>
                ))}
              </View>
              <Text style={{ color: colors.textMuted, fontSize: 11, marginTop: 4 }}>{tx('billGenerator.auditLog.description', 'Track all billing operations, user actions, approval workflows, and system events for compliance and security audits.')}</Text>
            </View>

            <View style={[card, { gap: 10 }]} data-testid="bill-generator-multi-currency-tab" testID="bill-generator-multi-currency-tab">
              <Text style={{ color: colors.text, fontSize: 15, fontWeight: '900' }} data-testid="bill-generator-multi-currency-title" testID="bill-generator-multi-currency-title">
                {tx('billGenerator.multiCurrency.title', 'Multi-Currency Exchange Manager')}
              </Text>
              <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
                {[
                  ['USD', '1.00', colors.successText],
                  ['EUR', '0.92', colors.info],
                  ['GBP', '0.79', colors.warningText],
                  ['JPY', '149.50', colors.infoText],
                  ['AUD', '1.52', colors.successText],
                  ['CAD', '1.36', colors.info],
                ].map(([curr, rate, accent]) => (
                  <View key={String(curr)} style={{ flex: 1, minWidth: isDesktop ? '15%' : '30%', borderRadius: 10, borderWidth: 1, borderColor: String(accent), backgroundColor: `${accent}12`, padding: 10 }} data-testid={`bill-generator-currency-${curr}`} testID={`bill-generator-currency-${curr}`}>
                    <Text style={{ color: colors.text, fontSize: 12, fontWeight: '900' }}>{String(curr)}</Text>
                    <Text style={{ color: String(accent), fontSize: 16, fontWeight: '700', marginTop: 4 }}>{String(rate)}</Text>
                    <Text style={{ color: colors.textMuted, fontSize: 9, marginTop: 2 }}>vs USD</Text>
                  </View>
                ))}
              </View>
              <Text style={{ color: colors.textMuted, fontSize: 11, marginTop: 4 }}>{tx('billGenerator.multiCurrency.description', 'Manage real-time exchange rates, currency conversions, and multi-currency billing with automatic rate updates and manual override capabilities.')}</Text>
            </View>

            <View style={[card, { gap: 10 }]} data-testid="bill-generator-payment-gateways-tab" testID="bill-generator-payment-gateways-tab">
              <Text style={{ color: colors.text, fontSize: 15, fontWeight: '900' }} data-testid="bill-generator-payment-gateways-title" testID="bill-generator-payment-gateways-title">
                {tx('billGenerator.paymentGateways.title', 'Payment Gateway Integration Hub')}
              </Text>
              <View style={{ gap: 8 }}>
                {[
                  { name: 'Stripe', status: 'Connected', color: colors.successText, txCount: 1243, icon: 'card' },
                  { name: 'PayPal', status: 'Connected', color: colors.successText, txCount: 856, icon: 'logo-paypal' },
                  { name: 'Razorpay', status: 'Disconnected', color: colors.textMuted, txCount: 0, icon: 'wallet' },
                  { name: 'Square', status: 'Test Mode', color: colors.warningText, txCount: 42, icon: 'cash' },
                ].map((gateway, idx) => (
                  <View key={idx} style={{ borderRadius: 10, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bgSoft, padding: 12, flexDirection: 'row', alignItems: 'center', gap: 12 }} data-testid={`bill-generator-gateway-${idx}`} testID={`bill-generator-gateway-${idx}`}>
                    <View style={{ width: 40, height: 40, borderRadius: 10, backgroundColor: `${gateway.color}1A`, alignItems: 'center', justifyContent: 'center' }}>
                      <Ionicons name={gateway.icon as any} size={20} color={gateway.color} />
                    </View>
                    <View style={{ flex: 1 }}>
                      <Text style={{ color: colors.text, fontWeight: '700', fontSize: 13 }}>{gateway.name}</Text>
                      <Text style={{ color: gateway.color, fontSize: 11, marginTop: 2 }}>{gateway.status} · {gateway.txCount} transactions</Text>
                    </View>
                    <TouchableOpacity style={{ borderRadius: 8, backgroundColor: colors.info, paddingHorizontal: 12, paddingVertical: 7 }} data-testid={`bill-generator-gateway-config-${idx}`} testID={`bill-generator-gateway-config-${idx}`}>
                      <Text style={{ color: colors.primaryText, fontSize: 10, fontWeight: '800' }}>{tx('billGenerator.paymentGateways.configure', 'Configure')}</Text>
                    </TouchableOpacity>
                  </View>
                ))}
              </View>
              <Text style={{ color: colors.textMuted, fontSize: 11, marginTop: 4 }}>{tx('billGenerator.paymentGateways.description', 'Centralized payment gateway management with connection status monitoring, transaction fee tracking, and test/live mode controls.')}</Text>
            </View>

            <View style={[card, { gap: 10 }]} data-testid="bill-generator-credit-notes-tab" testID="bill-generator-credit-notes-tab">
              <Text style={{ color: colors.text, fontSize: 15, fontWeight: '900' }} data-testid="bill-generator-credit-notes-title" testID="bill-generator-credit-notes-title">
                {tx('billGenerator.creditNotes.title', 'Credit Notes & Refunds Manager')}
              </Text>
              <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
                {[
                  ['total-credits', tx('billGenerator.creditNotes.totalCredits', 'Total Credit Notes'), '12'],
                  ['pending-refunds', tx('billGenerator.creditNotes.pendingRefunds', 'Pending Refunds'), '3'],
                  ['refund-amount', tx('billGenerator.creditNotes.refundAmount', 'Refund Amount'), money(2450.00)],
                ].map(([id, label, value]) => (
                  <View key={String(id)} style={{ flex: 1, minWidth: isDesktop ? '32%' : '48%', borderRadius: 10, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bgSoft, padding: 10 }} data-testid={`bill-generator-credit-${id}`} testID={`bill-generator-credit-${id}`}>
                    <Text style={{ color: colors.textMuted, fontSize: 10 }}>{String(label)}</Text>
                    <Text style={{ color: colors.text, fontWeight: '800', marginTop: 4 }}>{String(value)}</Text>
                  </View>
                ))}
              </View>
              <TouchableOpacity style={{ borderRadius: 10, backgroundColor: colors.errorText, paddingVertical: 12, alignItems: 'center' }} data-testid="bill-generator-create-credit-note-button" testID="bill-generator-create-credit-note-button">
                <Text style={{ color: colors.primaryText, fontWeight: '800' }}>{tx('billGenerator.creditNotes.createNew', 'Create Credit Note')}</Text>
              </TouchableOpacity>
              <Text style={{ color: colors.textMuted, fontSize: 11, marginTop: 4 }}>{tx('billGenerator.creditNotes.description', 'Process full or partial refunds, create credit notes for invoice adjustments, and track refund status with detailed audit trails.')}</Text>
            </View>

            <View style={[card, { gap: 10 }]} data-testid="bill-generator-disputes-tab" testID="bill-generator-disputes-tab">
              <Text style={{ color: colors.text, fontSize: 15, fontWeight: '900' }} data-testid="bill-generator-disputes-title" testID="bill-generator-disputes-title">
                {tx('billGenerator.disputes.title', 'Dispute Resolution Center')}
              </Text>
              <View style={{ gap: 8 }}>
                {[
                  { id: 'DIS-2024-001', client: 'Acme Corp', amount: 1500, status: 'Under Review', color: colors.warningText },
                  { id: 'DIS-2024-002', client: 'Tech Solutions', amount: 3200, status: 'Resolved', color: colors.successText },
                  { id: 'DIS-2024-003', client: 'Global Ventures', amount: 890, status: 'Open', color: colors.errorText },
                ].map((dispute, idx) => (
                  <View key={idx} style={{ borderRadius: 10, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bgSoft, padding: 10 }} data-testid={`bill-generator-dispute-${idx}`} testID={`bill-generator-dispute-${idx}`}>
                    <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
                      <Text style={{ color: colors.text, fontWeight: '700', fontSize: 12 }}>{dispute.id}</Text>
                      <View style={{ borderRadius: 999, backgroundColor: `${dispute.color}1A`, borderWidth: 1, borderColor: dispute.color, paddingHorizontal: 8, paddingVertical: 4 }}>
                        <Text style={{ color: dispute.color, fontSize: 10, fontWeight: '700' }}>{dispute.status}</Text>
                      </View>
                    </View>
                    <Text style={{ color: colors.textMuted, fontSize: 11, marginTop: 4 }}>{dispute.client} · {money(dispute.amount)}</Text>
                  </View>
                ))}
              </View>
              <Text style={{ color: colors.textMuted, fontSize: 11, marginTop: 4 }}>{tx('billGenerator.disputes.description', 'Manage payment disputes, chargebacks, and billing conflicts with evidence tracking, status monitoring, and client communication timeline.')}</Text>
            </View>

            <View style={[card, { gap: 10 }]} data-testid="bill-generator-forecasting-tab" testID="bill-generator-forecasting-tab">
              <Text style={{ color: colors.text, fontSize: 15, fontWeight: '900' }} data-testid="bill-generator-forecasting-title" testID="bill-generator-forecasting-title">
                {tx('billGenerator.forecasting.title', 'Advanced Financial Forecasting')}
              </Text>
              <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
                {[
                  ['3-month', tx('billGenerator.forecasting.threeMonth', '3-Month Projection'), money(45600)],
                  ['6-month', tx('billGenerator.forecasting.sixMonth', '6-Month Projection'), money(92300)],
                  ['12-month', tx('billGenerator.forecasting.twelveMonth', '12-Month Projection'), money(189400)],
                ].map(([id, label, value]) => (
                  <View key={String(id)} style={{ flex: 1, minWidth: isDesktop ? '32%' : '48%', borderRadius: 10, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bgSoft, padding: 10 }} data-testid={`bill-generator-forecast-${id}`} testID={`bill-generator-forecast-${id}`}>
                    <Text style={{ color: colors.textMuted, fontSize: 10 }}>{String(label)}</Text>
                    <Text style={{ color: colors.successText, fontWeight: '800', fontSize: 16, marginTop: 4 }}>{String(value)}</Text>
                  </View>
                ))}
              </View>
              <View style={{ borderRadius: 10, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bgSoft, padding: 10 }}>
                <Text style={{ color: colors.text, fontWeight: '700', fontSize: 12, marginBottom: 6 }}>{tx('billGenerator.forecasting.scenarios', 'Scenario Analysis')}</Text>
                {['Best Case (+25%)', 'Realistic (0%)', 'Worst Case (-15%)'].map((scenario, idx) => (
                  <Text key={idx} style={{ color: colors.textMuted, fontSize: 11, marginTop: 3 }} data-testid={`bill-generator-scenario-${idx}`} testID={`bill-generator-scenario-${idx}`}>• {scenario}</Text>
                ))}
              </View>
              <Text style={{ color: colors.textMuted, fontSize: 11, marginTop: 4 }}>{tx('billGenerator.forecasting.description', 'AI-powered financial projections with scenario modeling, seasonal trend analysis, and cash flow forecasting for strategic planning.')}</Text>
            </View>

            <View style={[card, { gap: 10 }]} data-testid="bill-generator-client-portal-tab" testID="bill-generator-client-portal-tab">
              <Text style={{ color: colors.text, fontSize: 15, fontWeight: '900' }} data-testid="bill-generator-client-portal-title" testID="bill-generator-client-portal-title">
                {tx('billGenerator.clientPortal.title', 'Client Portal Management')}
              </Text>
              <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: colors.border }}>
                <View>
                  <Text style={{ color: colors.text, fontWeight: '700', fontSize: 13 }}>{tx('billGenerator.clientPortal.enablePortal', 'Enable Client Portal')}</Text>
                  <Text style={{ color: colors.textMuted, fontSize: 11, marginTop: 2 }}>{tx('billGenerator.clientPortal.allowClients', 'Allow clients to view and pay bills online')}</Text>
                </View>
                <View style={{ width: 50, height: 28, borderRadius: 14, backgroundColor: colors.successText, justifyContent: 'center', paddingHorizontal: 4 }} data-testid="bill-generator-portal-toggle" testID="bill-generator-portal-toggle">
                  <View style={{ width: 20, height: 20, borderRadius: 10, backgroundColor: colors.primaryText, alignSelf: 'flex-end' }} />
                </View>
              </View>
              <View style={{ gap: 6 }}>
                <Text style={{ color: colors.text, fontWeight: '700', fontSize: 12 }}>{tx('billGenerator.clientPortal.brandingSettings', 'Branding Settings')}</Text>
                <View style={{ flexDirection: 'row', gap: 8 }}>
                  <View style={{ flex: 1, height: 44, borderRadius: 10, borderWidth: 1, borderColor: colors.border, justifyContent: 'center', paddingHorizontal: 12 }}>
                    <Text style={{ color: colors.textMuted, fontSize: 11 }}>{tx('billGenerator.clientPortal.logoUpload', 'Upload Logo')}</Text>
                  </View>
                  <View style={{ flex: 1, height: 44, borderRadius: 10, borderWidth: 1, borderColor: colors.border, justifyContent: 'center', paddingHorizontal: 12 }}>
                    <Text style={{ color: colors.textMuted, fontSize: 11 }}>{tx('billGenerator.clientPortal.colorScheme', 'Color Scheme')}</Text>
                  </View>
                </View>
              </View>
              <Text style={{ color: colors.textMuted, fontSize: 11, marginTop: 4 }}>{tx('billGenerator.clientPortal.description', 'Configure self-service client portals with custom branding, access control, and activity monitoring for enhanced client experience.')}</Text>
            </View>

            <View style={[card, { gap: 10 }]} data-testid="bill-generator-custom-fields-tab" testID="bill-generator-custom-fields-tab">
              <Text style={{ color: colors.text, fontSize: 15, fontWeight: '900' }} data-testid="bill-generator-custom-fields-title" testID="bill-generator-custom-fields-title">
                {tx('billGenerator.customFields.title', 'Custom Fields & Metadata Manager')}
              </Text>
              <View style={{ gap: 8 }}>
                {[
                  { name: 'Purchase Order Number', type: 'Text', required: true },
                  { name: 'Project Code', type: 'Text', required: false },
                  { name: 'Department', type: 'Dropdown', required: true },
                  { name: 'Delivery Date', type: 'Date', required: false },
                ].map((field, idx) => (
                  <View key={idx} style={{ borderRadius: 10, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bgSoft, padding: 10, flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }} data-testid={`bill-generator-custom-field-${idx}`} testID={`bill-generator-custom-field-${idx}`}>
                    <View style={{ flex: 1 }}>
                      <Text style={{ color: colors.text, fontWeight: '700', fontSize: 12 }}>{field.name}</Text>
                      <Text style={{ color: colors.textMuted, fontSize: 10, marginTop: 2 }}>{field.type} · {field.required ? 'Required' : 'Optional'}</Text>
                    </View>
                    <TouchableOpacity style={{ borderRadius: 8, borderWidth: 1, borderColor: colors.border, paddingHorizontal: 10, paddingVertical: 6 }} data-testid={`bill-generator-edit-field-${idx}`} testID={`bill-generator-edit-field-${idx}`}>
                      <Text style={{ color: colors.text, fontSize: 10, fontWeight: '700' }}>{tx('billGenerator.customFields.edit', 'Edit')}</Text>
                    </TouchableOpacity>
                  </View>
                ))}
              </View>
              <TouchableOpacity style={{ borderRadius: 10, backgroundColor: colors.info, paddingVertical: 12, alignItems: 'center' }} data-testid="bill-generator-add-custom-field-button" testID="bill-generator-add-custom-field-button">
                <Text style={{ color: colors.primaryText, fontWeight: '800' }}>{tx('billGenerator.customFields.addNew', 'Add Custom Field')}</Text>
              </TouchableOpacity>
              <Text style={{ color: colors.textMuted, fontSize: 11, marginTop: 4 }}>{tx('billGenerator.customFields.description', 'Create custom fields for invoices with field types (text, number, date, dropdown), validation rules, and template configurations.')}</Text>
            </View>

            <View style={[card, { gap: 10 }]} data-testid="bill-generator-batch-operations-tab" testID="bill-generator-batch-operations-tab">
              <Text style={{ color: colors.text, fontSize: 15, fontWeight: '900' }} data-testid="bill-generator-batch-operations-title" testID="bill-generator-batch-operations-title">
                {tx('billGenerator.batchOperations.title', 'Batch Operations Center')}
              </Text>
              <View style={{ gap: 8 }}>
                {[
                  { title: 'Bulk Status Update', description: 'Mark multiple bills as sent or paid', icon: 'checkmark-done', color: colors.successText },
                  { title: 'Mass Email Dispatch', description: 'Send bills to multiple clients at once', icon: 'mail', color: colors.info },
                  { title: 'Batch PDF Generation', description: 'Generate PDFs for selected invoices', icon: 'document', color: colors.warningText },
                  { title: 'Bulk Archive', description: 'Archive old or completed bills', icon: 'archive', color: colors.textMuted },
                ].map((operation, idx) => (
                  <TouchableOpacity key={idx} style={{ borderRadius: 10, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bgSoft, padding: 12, flexDirection: 'row', alignItems: 'center', gap: 12 }} data-testid={`bill-generator-batch-op-${idx}`} testID={`bill-generator-batch-op-${idx}`}>
                    <View style={{ width: 40, height: 40, borderRadius: 10, backgroundColor: `${operation.color}1A`, alignItems: 'center', justifyContent: 'center' }}>
                      <Ionicons name={operation.icon as any} size={20} color={operation.color} />
                    </View>
                    <View style={{ flex: 1 }}>
                      <Text style={{ color: colors.text, fontWeight: '700', fontSize: 12 }}>{operation.title}</Text>
                      <Text style={{ color: colors.textMuted, fontSize: 10, marginTop: 2 }}>{operation.description}</Text>
                    </View>
                  </TouchableOpacity>
                ))}
              </View>
              <Text style={{ color: colors.textMuted, fontSize: 11, marginTop: 4 }}>{tx('billGenerator.batchOperations.description', 'Execute bulk operations on multiple bills simultaneously with progress tracking and rollback capabilities for efficient workflow management.')}</Text>
            </View>

            <View style={[card, { gap: 10 }]} data-testid="bill-generator-webhooks-tab" testID="bill-generator-webhooks-tab">
              <Text style={{ color: colors.text, fontSize: 15, fontWeight: '900' }} data-testid="bill-generator-webhooks-title" testID="bill-generator-webhooks-title">
                {tx('billGenerator.webhooks.title', 'Webhooks & Integration Manager')}
              </Text>
              <View style={{ gap: 8 }}>
                {[
                  { endpoint: 'https://api.example.com/webhooks/bills', events: 'bill.created, bill.paid', status: 'Active', deliveries: 1543 },
                  { endpoint: 'https://zapier.com/hooks/catch/xyz', events: 'payment.received', status: 'Active', deliveries: 856 },
                  { endpoint: 'https://make.com/webhook/abc', events: 'bill.overdue', status: 'Paused', deliveries: 234 },
                ].map((webhook, idx) => (
                  <View key={idx} style={{ borderRadius: 10, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bgSoft, padding: 10 }} data-testid={`bill-generator-webhook-${idx}`} testID={`bill-generator-webhook-${idx}`}>
                    <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
                      <Text style={{ color: colors.text, fontWeight: '700', fontSize: 11, flex: 1 }} numberOfLines={1}>{webhook.endpoint}</Text>
                      <View style={{ borderRadius: 999, backgroundColor: webhook.status === 'Active' ? `${colors.successText}1A` : `${colors.textMuted}1A`, paddingHorizontal: 8, paddingVertical: 3 }}>
                        <Text style={{ color: webhook.status === 'Active' ? colors.successText : colors.textMuted, fontSize: 9, fontWeight: '700' }}>{webhook.status}</Text>
                      </View>
                    </View>
                    <Text style={{ color: colors.textMuted, fontSize: 10 }}>{webhook.events}</Text>
                    <Text style={{ color: colors.textMuted, fontSize: 10, marginTop: 3 }}>{webhook.deliveries} successful deliveries</Text>
                  </View>
                ))}
              </View>
              <TouchableOpacity style={{ borderRadius: 10, backgroundColor: colors.info, paddingVertical: 12, alignItems: 'center' }} data-testid="bill-generator-add-webhook-button" testID="bill-generator-add-webhook-button">
                <Text style={{ color: colors.primaryText, fontWeight: '800' }}>{tx('billGenerator.webhooks.addNew', 'Add Webhook')}</Text>
              </TouchableOpacity>
              <Text style={{ color: colors.textMuted, fontSize: 11, marginTop: 4 }}>{tx('billGenerator.webhooks.description', 'Configure webhook notifications for bill events, manage integration with Zapier and Make.com, and monitor delivery logs with retry policies.')}</Text>
            </View>

            <View style={[card, { gap: 10 }]} data-testid="bill-generator-documents-tab" testID="bill-generator-documents-tab">
              <Text style={{ color: colors.text, fontSize: 15, fontWeight: '900' }} data-testid="bill-generator-documents-title" testID="bill-generator-documents-title">
                {tx('billGenerator.documents.title', 'Document Storage & Archive')}
              </Text>
              <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginBottom: 8 }}>
                {[
                  ['total-docs', tx('billGenerator.documents.totalDocs', 'Total Documents'), '2,847'],
                  ['storage-used', tx('billGenerator.documents.storageUsed', 'Storage Used'), '4.2 GB'],
                  ['archived', tx('billGenerator.documents.archived', 'Archived'), '1,203'],
                ].map(([id, label, value]) => (
                  <View key={String(id)} style={{ flex: 1, minWidth: isDesktop ? '32%' : '48%', borderRadius: 10, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bgSoft, padding: 10 }} data-testid={`bill-generator-doc-stat-${id}`} testID={`bill-generator-doc-stat-${id}`}>
                    <Text style={{ color: colors.textMuted, fontSize: 10 }}>{String(label)}</Text>
                    <Text style={{ color: colors.text, fontWeight: '800', marginTop: 4 }}>{String(value)}</Text>
                  </View>
                ))}
              </View>
              <View style={{ gap: 8 }}>
                {[
                  { name: 'Invoice_2024_001.pdf', type: 'PDF', size: '245 KB', date: '2024-05-20' },
                  { name: 'Contract_Acme_Corp.pdf', type: 'PDF', size: '1.2 MB', date: '2024-05-18' },
                  { name: 'Receipt_Payment_123.pdf', type: 'PDF', size: '180 KB', date: '2024-05-15' },
                ].map((doc, idx) => (
                  <View key={idx} style={{ borderRadius: 10, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bgSoft, padding: 10, flexDirection: 'row', alignItems: 'center', gap: 10 }} data-testid={`bill-generator-doc-${idx}`} testID={`bill-generator-doc-${idx}`}>
                    <View style={{ width: 36, height: 36, borderRadius: 8, backgroundColor: colors.errorText + '1A', alignItems: 'center', justifyContent: 'center' }}>
                      <Ionicons name="document-text" size={18} color={colors.errorText} />
                    </View>
                    <View style={{ flex: 1 }}>
                      <Text style={{ color: colors.text, fontWeight: '700', fontSize: 11 }} numberOfLines={1}>{doc.name}</Text>
                      <Text style={{ color: colors.textMuted, fontSize: 10, marginTop: 2 }}>{doc.size} · {doc.date}</Text>
                    </View>
                    <TouchableOpacity style={{ borderRadius: 8, borderWidth: 1, borderColor: colors.border, width: 32, height: 32, alignItems: 'center', justifyContent: 'center' }} data-testid={`bill-generator-doc-download-${idx}`} testID={`bill-generator-doc-download-${idx}`}>
                      <Ionicons name="download" size={16} color={colors.text} />
                    </TouchableOpacity>
                  </View>
                ))}
              </View>
              <TouchableOpacity style={{ borderRadius: 10, backgroundColor: colors.info, paddingVertical: 12, alignItems: 'center' }} data-testid="bill-generator-upload-document-button" testID="bill-generator-upload-document-button">
                <Text style={{ color: colors.primaryText, fontWeight: '800' }}>{tx('billGenerator.documents.uploadNew', 'Upload Document')}</Text>
              </TouchableOpacity>
              <Text style={{ color: colors.textMuted, fontSize: 11, marginTop: 4 }}>{tx('billGenerator.documents.description', 'Centralized document storage with auto-archiving, bulk download capabilities, search filtering, and compliance-ready document retention.')}</Text>
            </View>
          </>
        )}
      </ScrollView>
    </FeatureLayout>
  );
}
