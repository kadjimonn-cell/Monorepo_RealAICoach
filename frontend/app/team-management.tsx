import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  View,
  Text,
  ScrollView,
  TouchableOpacity,
  TextInput,
  ActivityIndicator,
  useWindowDimensions,
  Platform,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import AppShell from '../src/components/AppShell';
import TeamNotificationToasts from '../src/components/TeamNotificationToasts';
import InvitationQRModal from '../src/components/admin/InvitationQRModal';
import api from '../src/services/api';
import { useTheme } from '../src/context/ThemeContext';
import { useLanguage } from '../src/i18n/LanguageContext';
import { useAuth } from '../src/context/AuthContext';
import { useAccessControl } from '../src/context/AccessControlContext';
import { useAutoRefresh } from '../src/hooks/useAutoRefresh';
import { hasAdminConsoleVisibility } from '../src/utils/adminAccess';
import { AdminRouteGate } from '../src/components/auth/AdminRouteGate';

type EmployeeRecord = {
  user_id: string;
  email: string;
  name?: string;
  platform_role?: string | null;
  premium_access?: boolean;
  feature_access?: string[];
  employee_permissions?: string[];
  is_admin?: boolean;
  last_active?: string;
  created_at?: string;
};

type SearchUser = {
  user_id: string;
  email: string;
  name?: string;
  platform_role?: string | null;
  is_admin?: boolean;
};

type RolesConfig = {
  roles: string[];
  all_features: string[];
  all_permissions: string[];
  default_role_features: Record<string, string[]>;
  default_role_permissions: Record<string, string[]>;
};

type AuditLogItem = {
  log_id?: string;
  action: string;
  admin_email: string;
  target_email: string;
  timestamp: string;
  details?: Record<string, any>;
};

const ROLE_COLOR_KEYS: Record<string, keyof ReturnType<typeof useTheme>['colors']> = {
  Support: 'primary',
  BillingOps: 'warning',
  UserManager: 'accent',
  ComplianceAuditor: 'accent',
  SuperEmployee: 'success',
  Manager: 'accent',
  'Support Team': 'primary',
  Developer: 'success',
  'Finance Advisor': 'warning',
  Operations: 'primary',
  Custom: 'text',
};

const ROLE_ICONS: Record<string, string> = {
  Support: 'headset',
  BillingOps: 'card',
  UserManager: 'people',
  ComplianceAuditor: 'shield-checkmark',
  SuperEmployee: 'flash',
  Manager: 'briefcase',
  'Support Team': 'headset',
  Developer: 'code-slash',
  'Finance Advisor': 'cash',
  Operations: 'cog',
  Custom: 'build',
};

const FALLBACK_CONFIG: RolesConfig = {
  roles: ['Support', 'BillingOps', 'UserManager', 'ComplianceAuditor', 'SuperEmployee', 'Custom'],
  all_features: [],
  all_permissions: [
    'employee.manage_users',
    'employee.manage_subscriptions',
    'employee.manage_access',
    'employee.view_audit_logs',
    'employee.manage_operations',
    'employee.view_analytics',
    'employee.manage_billing',
    'employee.handle_support',
  ],
  default_role_features: {},
  default_role_permissions: {},
};

type Snapshot = {
  employeesAnalyzed: number;
  highRisk: number;
  mediumRisk: number;
  pendingApprovals: number;
  summary: string;
};

type ApprovalModeStatus = {
  scope: string;
  approval_mode: string;
  approval_label: string;
  evidence_count: number;
};

export default function TeamManagementPage() {
  const router = useRouter();
  const { colors, darkMode } = useTheme();
  const { t } = useLanguage();

  // @autofix-moved: was module-level const AUDIT_ACTION_CONFIG
  const AUDIT_ACTION_CONFIG: Record<string, { label: string; color: string; icon: string }> = {
    employee_added: { label: 'Employee Added', color: colors.successText, icon: 'person-add' },
    employee_removed: { label: 'Employee Removed', color: colors.error, icon: 'person-remove' },
    premium_granted: { label: 'Premium Granted', color: colors.warningText, icon: 'diamond' },
    premium_revoked: { label: 'Premium Revoked', color: colors.textMuted, icon: 'diamond-outline' },
    role_changed: { label: 'Role Changed', color: colors.primary, icon: 'swap-horizontal' },
    access_updated: { label: 'Access Updated', color: colors.accent, icon: 'key' },
    access_request_approved: { label: 'Request Approved', color: colors.successText, icon: 'checkmark-done' },
    access_request_denied: { label: 'Request Denied', color: colors.error, icon: 'close-circle' },
  };
  const dm = darkMode;
  const T = useMemo(() => ({
    ...colors,
    bg: colors.bg,
    surface: colors.surface,
    surfaceAlt: colors.surfaceHover,
    border: colors.border,
    text: colors.text,
    textSec: colors.textSec,
    textMuted: colors.textMuted,
    inputBg: colors.surface,
    inputBorder: colors.border,
    cardShadow: dm ? '0 2px 12px rgba(0,0,0,0.3)' : '0 1px 3px rgba(0,0,0,0.06), 0 4px 16px rgba(0,0,0,0.04)',
  }), [dm, colors]);
  const { user, loading: authLoading } = useAuth();
  const { loading: accessLoading } = useAccessControl();
  const { width } = useWindowDimensions();

  const isDesktop = width >= 1024;
  const isMedium = width >= 768;

  const isAdmin = hasAdminConsoleVisibility(user as any);
  const canManageAccess = isAdmin;
  const canManageUsers = isAdmin;
  const canViewAuditLogs = isAdmin;
  const canViewAnalytics = isAdmin;
  const canUsePage = canManageUsers || canViewAuditLogs || canViewAnalytics;
  const waitingForAuth = authLoading || accessLoading;

  const [loadingEmployees, setLoadingEmployees] = useState(true);
  const [loadingAudit, setLoadingAudit] = useState(false);
  const [loadingSnapshot, setLoadingSnapshot] = useState(false);
  const [refreshingSnapshot, setRefreshingSnapshot] = useState(false);
  const [loadingApprovalMode, setLoadingApprovalMode] = useState(false);
  const [exportingApprovalEvidence, setExportingApprovalEvidence] = useState(false);

  const [employees, setEmployees] = useState<EmployeeRecord[]>([]);
  const [rolesConfig, setRolesConfig] = useState<RolesConfig>(FALLBACK_CONFIG);
  const [approvalMode, setApprovalMode] = useState<ApprovalModeStatus | null>(null);
  const [snapshot, setSnapshot] = useState<Snapshot>({
    employeesAnalyzed: 0,
    highRisk: 0,
    mediumRisk: 0,
    pendingApprovals: 0,
    summary: t('teamManagement.snapshot.emptySummary'),
  });

  const [auditLogs, setAuditLogs] = useState<AuditLogItem[]>([]);
  const [auditTotal, setAuditTotal] = useState(0);
  const [auditPage, setAuditPage] = useState(1);
  const [auditPages, setAuditPages] = useState(1);
  const [auditFilter, setAuditFilter] = useState('');

  const [globalError, setGlobalError] = useState('');
  const [globalSuccess, setGlobalSuccess] = useState('');

  const [filterSearch, setFilterSearch] = useState('');
  const [filterRole, setFilterRole] = useState('');
  const [filterPremium, setFilterPremium] = useState<'all' | 'premium' | 'standard'>('all');

  const [editorOpen, setEditorOpen] = useState(false);
  const [editorMode, setEditorMode] = useState<'create' | 'edit'>('create');
  const [editingUserId, setEditingUserId] = useState<string | null>(null);
  const [savingEditor, setSavingEditor] = useState(false);

  const [candidateQuery, setCandidateQuery] = useState('');
  const [candidateResults, setCandidateResults] = useState<SearchUser[]>([]);
  const [candidateSearching, setCandidateSearching] = useState(false);
  const [selectedCandidate, setSelectedCandidate] = useState<SearchUser | null>(null);

  const [formRole, setFormRole] = useState('');
  const [formPremium, setFormPremium] = useState(false);
  const [formFeatures, setFormFeatures] = useState<string[]>([]);
  const [formPermissions, setFormPermissions] = useState<string[]>([]);

  const [confirmModal, setConfirmModal] = useState<{ visible: boolean; employee: EmployeeRecord | null }>({ visible: false, employee: null });

  const [bulkOpen, setBulkOpen] = useState(false);
  const [bulkText, setBulkText] = useState('');
  const [bulkDragOver, setBulkDragOver] = useState(false);
  const [bulkSubmitting, setBulkSubmitting] = useState(false);
  const [bulkResult, setBulkResult] = useState<{ total: number; added: number; invited_count?: number; failed_count: number; success: { email: string; platform_role: string }[]; invited?: { email: string; platform_role: string; expires_at?: string }[]; failed: { email: string; reason: string }[] } | null>(null);

  // Multi-select + bulk actions on existing employees
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [bulkActionBusy, setBulkActionBusy] = useState(false);
  const [bulkRolePickerOpen, setBulkRolePickerOpen] = useState(false);
  const [bulkRemoveConfirm, setBulkRemoveConfirm] = useState(false);

  const [pendingInvites, setPendingInvites] = useState<{ invitation_id: string; email: string; platform_role: string; invited_by_email: string; created_at: string; expires_at: string; delivery_status?: string | null; delivery_event_at?: string | null }[]>([]);
  // Ghost-audit: employees with platform_role but no invitation record (legacy silent-grant remediation)
  const [ghosts, setGhosts] = useState<{ user_id: string; email: string; name?: string; platform_role: string; premium_access: boolean; employee_since?: string }[]>([]);
  const [ghostLoading, setGhostLoading] = useState(false);
  const [ghostConverting, setGhostConverting] = useState(false);
  const [ghostError, setGhostError] = useState<string | null>(null);
  const [invitesLoading, setInvitesLoading] = useState(false);
  const [invitesError, setInvitesError] = useState<string | null>(null);
  const [busyInvitationId, setBusyInvitationId] = useState<string | null>(null);
  const [inviteSearch, setInviteSearch] = useState('');
  const [inviteRoleFilter, setInviteRoleFilter] = useState<string>('');
  const [inviteWindow, setInviteWindow] = useState<'' | '24h' | '72h' | '7d' | '30d'>('');
  const [qrModal, setQrModal] = useState<{ visible: boolean; url: string; email: string; role: string }>({ visible: false, url: '', email: '', role: '' });

  const clearNotifications = () => {
    setGlobalError('');
    setGlobalSuccess('');
  };

  const getRoleColor = useCallback((role: string) => {
    const key = ROLE_COLOR_KEYS[role] || 'textMuted';
    return (colors as any)[key] || colors.textMuted;
  }, [colors]);

  // Sort state for employee table
  const [sortBy, setSortBy] = useState<'name' | 'email' | 'role' | 'last_active'>('name');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('asc');
  const toggleSort = useCallback((key: 'name' | 'email' | 'role' | 'last_active') => {
    setSortBy((prev) => {
      if (prev === key) {
        setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
      } else {
        setSortDir('asc');
      }
      return key;
    });
  }, []);

  const applyRoleDefaults = useCallback((role: string) => {
    setFormFeatures([...(rolesConfig.default_role_features?.[role] || [])]);
    setFormPermissions([...(rolesConfig.default_role_permissions?.[role] || [])]);
  }, [rolesConfig.default_role_features, rolesConfig.default_role_permissions]);

  const loadEmployeesAndConfig = useCallback(async (silent = false) => {
    if (!canManageUsers) {
      if (waitingForAuth) return;
      setEmployees([]);
      setLoadingEmployees(false);
      return;
    }

    if (!silent) setLoadingEmployees(true);
    try {
      const [employeesRes, configRes] = await Promise.all([
        api.get('/admin/employees'),
        api.get('/admin/employees/roles-config'),
      ]);
      const rows = (employeesRes.data?.employees || []) as EmployeeRecord[];
      rows.sort((a, b) => (a.email || '').localeCompare(b.email || ''));
      setEmployees(rows);
      setRolesConfig({
        ...FALLBACK_CONFIG,
        ...(configRes.data || {}),
        roles: configRes.data?.roles?.length ? configRes.data.roles : FALLBACK_CONFIG.roles,
      });
    } catch (error: any) {
      setGlobalError(error?.response?.data?.detail || 'Unable to load employee management data.');
      setRolesConfig(FALLBACK_CONFIG);
    } finally {
      if (!silent) setLoadingEmployees(false);
    }
  }, [canManageUsers, waitingForAuth]);

  const loadAuditLog = useCallback(async (nextPage = 1, action = '') => {
    if (!canViewAuditLogs) {
      if (waitingForAuth) return;
      setAuditLogs([]);
      setAuditTotal(0);
      setAuditPage(1);
      setAuditPages(1);
      return;
    }
    setLoadingAudit(true);
    try {
      const params = new URLSearchParams({ page: String(nextPage), limit: '12' });
      if (action) params.set('action', action);
      const response = await api.get(`/admin/employees/audit-log?${params.toString()}`);
      setAuditLogs(response.data?.logs || []);
      setAuditTotal(response.data?.total || 0);
      setAuditPage(response.data?.page || 1);
      setAuditPages(response.data?.pages || 1);
    } catch {
      setGlobalError('Unable to load activity log right now.');
    } finally {
      setLoadingAudit(false);
    }
  }, [canViewAuditLogs, waitingForAuth]);

  const loadSnapshot = useCallback(async (isManual = false) => {
    if (!canViewAnalytics) {
      if (waitingForAuth) return;
      setSnapshot({
        employeesAnalyzed: employees.length,
        highRisk: 0,
        mediumRisk: 0,
        pendingApprovals: 0,
        summary: 'Analytics permission is required to view AI security insights.',
      });
      return;
    }
    if (isManual) setRefreshingSnapshot(true);
    else setLoadingSnapshot(true);

    try {
      const response = await api.get('/admin/employees/ai-insights', { params: { hours: 24 } });
      const payload = response.data || {};
      const riskRows = payload.risk_scores || [];
      const high = riskRows.filter((r: any) => r.risk_level === 'high').length;
      const medium = riskRows.filter((r: any) => r.risk_level === 'medium').length;
      setSnapshot({
        employeesAnalyzed: payload.employees_analyzed || employees.length,
        highRisk: high,
        mediumRisk: medium,
        pendingApprovals: (payload.approval_suggestions || []).length,
        summary: payload.auto_audit_summary?.summary || t('teamManagement.snapshot.emptySummaryFallback'),
      });
    } catch {
      setSnapshot({
        employeesAnalyzed: employees.length,
        highRisk: 0,
        mediumRisk: 0,
        pendingApprovals: 0,
        summary: t('teamManagement.snapshot.unavailable'),
      });
    } finally {
      if (isManual) setRefreshingSnapshot(false);
      else setLoadingSnapshot(false);
    }
  }, [canViewAnalytics, employees.length, waitingForAuth]);

  const loadApprovalMode = useCallback(async () => {
    if (!canManageAccess) {
      if (waitingForAuth) return;
      setApprovalMode(null);
      return;
    }
    setLoadingApprovalMode(true);
    try {
      const response = await api.get('/admin/employees/approval-mode');
      setApprovalMode(response.data || null);
    } catch {
      setApprovalMode(null);
    } finally {
      setLoadingApprovalMode(false);
    }
  }, [canManageAccess, waitingForAuth]);

  useEffect(() => {
    void loadEmployeesAndConfig();
  }, [loadEmployeesAndConfig]);

  useEffect(() => {
    void loadAuditLog(1, '');
  }, [loadAuditLog]);

  useEffect(() => {
    void loadSnapshot();
  }, [loadSnapshot]);

  useEffect(() => {
    void loadApprovalMode();
  }, [loadApprovalMode]);

  useAutoRefresh(() => {
    void loadEmployeesAndConfig(true);
    void loadAuditLog(auditPage, auditFilter);
    void loadApprovalMode();
  }, { intervalMs: 30000 });

  const openCreateEditor = () => {
    clearNotifications();
    setEditorMode('create');
    setEditingUserId(null);
    setSelectedCandidate(null);
    setCandidateQuery('');
    setCandidateResults([]);
    const defaultRole = rolesConfig.roles[0] || '';
    setFormRole(defaultRole);
    setFormPremium(false);
    setFormFeatures([...(rolesConfig.default_role_features?.[defaultRole] || [])]);
    setFormPermissions([...(rolesConfig.default_role_permissions?.[defaultRole] || [])]);
    setEditorOpen(true);
  };

  const openEditEditor = (employee: EmployeeRecord) => {
    clearNotifications();
    setEditorMode('edit');
    setEditingUserId(employee.user_id);
    setSelectedCandidate({
      user_id: employee.user_id,
      email: employee.email,
      name: employee.name,
      platform_role: employee.platform_role,
      is_admin: employee.is_admin,
    });
    setCandidateQuery(employee.email);
    setCandidateResults([]);
    setFormRole(employee.platform_role || rolesConfig.roles[0] || '');
    setFormPremium(Boolean(employee.premium_access));
    setFormFeatures([...(employee.feature_access || [])]);
    setFormPermissions([...(employee.employee_permissions || [])]);
    setEditorOpen(true);
  };

  const closeEditor = () => {
    setEditorOpen(false);
    setEditingUserId(null);
    setSavingEditor(false);
    setSelectedCandidate(null);
    setCandidateResults([]);
    setCandidateQuery('');
  };

  const openBulkInvite = () => {
    clearNotifications();
    setBulkResult(null);
    setBulkText('');
    setBulkOpen(true);
  };

  const closeBulkInvite = () => {
    setBulkOpen(false);
    setBulkResult(null);
    setBulkText('');
    setBulkSubmitting(false);
  };

  const parseBulkLines = useCallback((raw: string): { email: string; platform_role: string; premium_access: boolean }[] => {
    const lines = raw.split(/\r?\n/).map(l => l.trim()).filter(Boolean);
    const defaultRole = rolesConfig.roles[0] || '';
    return lines
      .filter(line => !line.toLowerCase().startsWith('email,'))
      .map(line => {
        const parts = line.split(/[,;\t]/).map(p => p.trim());
        const email = (parts[0] || '').toLowerCase();
        const role = parts[1] || defaultRole;
        const premium = (parts[2] || '').toLowerCase();
        return {
          email,
          platform_role: role,
          premium_access: premium === 'true' || premium === 'yes' || premium === '1' || premium === 'premium',
        };
      });
  }, [rolesConfig.roles]);

  const bulkParsed = bulkText ? parseBulkLines(bulkText) : [];
  const bulkValidCount = bulkParsed.filter(r => /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(r.email) && rolesConfig.roles.includes(r.platform_role)).length;

  const handleBulkFile = useCallback(async (file: File) => {
    try {
      const text = await file.text();
      setBulkText(text);
    } catch {
      setGlobalError('Unable to read file');
    }
  }, []);

  const loadPendingInvites = useCallback(async () => {
    if (!canManageAccess) return;
    setInvitesLoading(true);
    setInvitesError(null);
    try {
      const params = new URLSearchParams();
      params.set('limit', '100');
      if (inviteSearch.trim()) params.set('q', inviteSearch.trim());
      if (inviteRoleFilter) params.set('platform_role', inviteRoleFilter);
      if (inviteWindow) params.set('window', inviteWindow);
      const res = await api.get(`/admin/employees/invitations?${params.toString()}`);
      setPendingInvites(res.data?.invitations || []);
    } catch (err) {
      setInvitesError((err as any)?.response?.data?.detail || (err as any)?.message || 'Failed to load invitations');
    } finally {
      setInvitesLoading(false);
    }
  }, [canManageAccess, inviteSearch, inviteRoleFilter, inviteWindow]);

  useEffect(() => {
    if (!canManageAccess) return;
    const t = setTimeout(() => { void loadPendingInvites(); }, 250);
    return () => clearTimeout(t);
  }, [canManageAccess, loadPendingInvites]);

  const loadGhosts = useCallback(async () => {
    if (!canManageAccess) return;
    setGhostLoading(true);
    setGhostError(null);
    try {
      const res = await api.get('/admin/employees/ghost-audit');
      setGhosts(res.data?.ghosts || []);
    } catch (err) {
      setGhostError((err as any)?.response?.data?.detail || (err as any)?.message || 'Ghost audit failed');
    } finally {
      setGhostLoading(false);
    }
  }, [canManageAccess]);

  useEffect(() => { void loadGhosts(); }, [loadGhosts]);

  const convertGhosts = useCallback(async (userIds?: string[]) => {
    if (!canManageAccess || ghostConverting) return;
    if (typeof window !== 'undefined') {
      const n = userIds?.length ?? ghosts.length;
      if (!window.confirm(
        `This will REVOKE platform_role from ${n} ghost employee(s), create fresh pending invitations, and email each one. They cannot access admin features again until they click the email link and accept. Continue?`
      )) return;
    }
    setGhostConverting(true);
    setGhostError(null);
    try {
      const body = userIds?.length ? { user_ids: userIds } : {};
      const res = await api.post('/admin/employees/ghost-audit/convert-to-pending', body);
      await Promise.all([loadGhosts(), loadPendingInvites(), loadEmployeesAndConfig(true)]);
      if (typeof window !== 'undefined') {
        window.alert(`Remediated ${res.data?.converted_count ?? 0} ghost employee(s). ${res.data?.failed_count ?? 0} failed.`);
      }
    } catch (err) {
      setGhostError((err as any)?.response?.data?.detail || (err as any)?.message || 'Remediation failed');
    } finally {
      setGhostConverting(false);
    }
  }, [canManageAccess, ghostConverting, ghosts.length, loadGhosts, loadPendingInvites, loadEmployeesAndConfig]);

  const resendInvitation = async (invitationId: string) => {
    setBusyInvitationId(invitationId);
    try {
      await api.post(`/admin/employees/invitations/${invitationId}/resend`);
      setGlobalSuccess('Invitation email resent');
      void loadPendingInvites();
    } catch (err) {
      setGlobalError((err as any)?.response?.data?.detail || 'Resend failed');
    } finally {
      setBusyInvitationId(null);
    }
  };

  const revokeInvitation = async (invitationId: string) => {
    setBusyInvitationId(invitationId);
    try {
      await api.delete(`/admin/employees/invitations/${invitationId}`);
      setGlobalSuccess('Invitation revoked');
      setPendingInvites(prev => prev.filter(i => i.invitation_id !== invitationId));
    } catch (err) {
      setGlobalError((err as any)?.response?.data?.detail || 'Revoke failed');
    } finally {
      setBusyInvitationId(null);
    }
  };

  const copyInvitationLink = async (invitationId: string) => {
    setBusyInvitationId(invitationId);
    try {
      const res = await api.get(`/admin/employees/invitations/${invitationId}/link`);
      let url = res.data?.invite_url || '';
      if (url.startsWith('/') && Platform.OS === 'web' && typeof window !== 'undefined') {
        url = `${window.location.origin}${url}`;
      }
      if (Platform.OS === 'web' && typeof navigator !== 'undefined' && (navigator as any).clipboard?.writeText) {
        await (navigator as any).clipboard.writeText(url);
        setGlobalSuccess('Invitation link copied to clipboard');
      } else {
        setGlobalSuccess(`Invitation link: ${url}`);
      }
    } catch (err) {
      setGlobalError((err as any)?.response?.data?.detail || 'Failed to get link');
    } finally {
      setBusyInvitationId(null);
    }
  };

  const openInvitationQR = async (invitationId: string, email: string, role: string) => {
    setBusyInvitationId(invitationId);
    try {
      const res = await api.get(`/admin/employees/invitations/${invitationId}/link`);
      let url = res.data?.invite_url || '';
      if (url.startsWith('/') && Platform.OS === 'web' && typeof window !== 'undefined') {
        url = `${window.location.origin}${url}`;
      }
      if (!url) {
        setGlobalError('Unable to load invitation QR link');
        return;
      }
      setQrModal({ visible: true, url, email, role });
    } catch (err) {
      setGlobalError((err as any)?.response?.data?.detail || 'Failed to open invitation QR');
    } finally {
      setBusyInvitationId(null);
    }
  };

  const copyFromQRModal = async () => {
    const url = qrModal.url || '';
    if (!url) {
      setGlobalError('No invitation link available to copy');
      return;
    }
    try {
      if (Platform.OS === 'web' && typeof navigator !== 'undefined' && (navigator as any).clipboard?.writeText) {
        await (navigator as any).clipboard.writeText(url);
        setGlobalSuccess('Invitation link copied to clipboard');
      } else {
        setGlobalSuccess(`Invitation link: ${url}`);
      }
    } catch {
      setGlobalError('Failed to copy invitation link');
    }
  };

  const submitBulkInvite = async () => {
    const entries = parseBulkLines(bulkText);
    if (!entries.length) {
      setGlobalError('No rows to invite');
      return;
    }
    setBulkSubmitting(true);
    setBulkResult(null);
    try {
      const res = await api.post('/admin/employees/bulk-invite', { invites: entries.slice(0, 100) });
      const data = res.data || {};
      setBulkResult({
        total: data.total || entries.length,
        added: data.added || 0,
        invited_count: data.invited_count || 0,
        failed_count: data.failed_count || 0,
        success: data.success || [],
        invited: data.invited || [],
        failed: data.failed || [],
      });
      if ((data.added || 0) > 0 || (data.invited_count || 0) > 0) {
        const parts: string[] = [];
        if (data.added) parts.push(`${data.added} added`);
        if (data.invited_count) parts.push(`${data.invited_count} invited by email`);
        if ((data.failed_count || 0) > 0) parts.push(`${data.failed_count} skipped`);
        setGlobalSuccess(parts.join(' · '));
        void loadEmployeesAndConfig(true);
        void loadAuditLog(1, auditFilter);
        void loadPendingInvites();
      } else if ((data.failed_count || 0) > 0) {
        // All rows failed — surface a clear global error so it isn't missed below the fold
        const reasons = (data.failed || []).slice(0, 3).map((f: any) => `${f.email} — ${f.reason}`);
        const more = (data.failed_count || 0) > 3 ? ` (+${(data.failed_count || 0) - 3} more)` : '';
        setGlobalError(`No invitations sent · ${data.failed_count} failed: ${reasons.join('; ')}${more}`);
      }
    } catch (err) {
      const msg = (err as any)?.response?.data?.detail || (err as any)?.message || 'Bulk invite failed';
      setGlobalError(String(msg));
    } finally {
      setBulkSubmitting(false);
    }
  };

  const searchCandidates = async (query: string) => {
    setCandidateQuery(query);
    if (query.trim().length < 2) {
      setCandidateResults([]);
      return;
    }
    setCandidateSearching(true);
    try {
      const response = await api.get(`/admin/employees/search?q=${encodeURIComponent(query.trim())}`);
      setCandidateResults(response.data?.users || []);
    } catch {
      setCandidateResults([]);
    } finally {
      setCandidateSearching(false);
    }
  };

  const onSelectCandidate = (candidate: SearchUser) => {
    if (candidate.is_admin) {
      setGlobalError('Admin owner account cannot be added as an employee record.');
      return;
    }
    if (candidate.platform_role) {
      setGlobalError('This user is already a platform employee. Use Edit instead.');
      return;
    }
    setSelectedCandidate(candidate);
    setCandidateQuery(candidate.email);
    setCandidateResults([]);
  };

  const toggleFormPermission = (permission: string) => {
    setFormPermissions((prev) => prev.includes(permission) ? prev.filter((p) => p !== permission) : [...prev, permission]);
  };

  const toggleFormFeature = (feature: string) => {
    setFormFeatures((prev) => prev.includes(feature) ? prev.filter((f) => f !== feature) : [...prev, feature]);
  };

  const canSubmitEditor = useMemo(() => {
    if (savingEditor || !formRole) return false;
    if (editorMode === 'create') {
      return Boolean(selectedCandidate?.email && !selectedCandidate?.is_admin && !selectedCandidate?.platform_role);
    }
    return Boolean(editingUserId);
  }, [savingEditor, formRole, editorMode, selectedCandidate, editingUserId]);

  const handleSubmitEditor = async () => {
    if (!canManageAccess) {
      setGlobalError('You do not have permission to change employee access.');
      return;
    }
    if (!canSubmitEditor) return;

    setSavingEditor(true);
    clearNotifications();
    try {
      if (editorMode === 'create') {
        await api.post('/admin/employees', {
          email: selectedCandidate?.email,
          platform_role: formRole,
          premium_access: formPremium,
          feature_access: formPremium ? [] : formFeatures,
          employee_permissions: formPermissions,
        });
        setGlobalSuccess(`${selectedCandidate?.email} was added successfully.`);
      } else {
        await api.patch(`/admin/employees/${editingUserId}`, {
          platform_role: formRole,
          premium_access: formPremium,
          feature_access: formPremium ? [] : formFeatures,
          employee_permissions: formPermissions,
        });
        setGlobalSuccess('Employee access settings updated successfully.');
      }

      closeEditor();
      await Promise.all([
        loadEmployeesAndConfig(true),
        loadAuditLog(1, auditFilter),
        loadSnapshot(),
      ]);
    } catch (error: any) {
      setGlobalError(error?.response?.data?.detail || 'Unable to save employee access changes.');
    } finally {
      setSavingEditor(false);
    }
  };

  const handleRemoveEmployee = async (employee: EmployeeRecord) => {
    if (!canManageAccess) {
      setGlobalError('You do not have permission to remove employees.');
      return;
    }
    if (employee.is_admin) {
      setGlobalError('Admin owner account cannot be removed.');
      return;
    }
    setConfirmModal({ visible: true, employee });
  };

  const executeRemoveEmployee = async () => {
    const employee = confirmModal.employee;
    setConfirmModal({ visible: false, employee: null });
    if (!employee) return;

    clearNotifications();
    try {
      await api.delete(`/admin/employees/${employee.user_id}`);
      setGlobalSuccess(`${employee.email} removed from platform employees.`);
      await Promise.all([
        loadEmployeesAndConfig(true),
        loadAuditLog(1, auditFilter),
        loadSnapshot(),
      ]);
    } catch (error: any) {
      setGlobalError(error?.response?.data?.detail || 'Unable to remove employee.');
    }
  };

  const dispatchRiskAlerts = async () => {
    if (!canManageAccess) {
      setGlobalError('You do not have permission to dispatch alerts.');
      return;
    }
    clearNotifications();
    try {
      const response = await api.post('/admin/employees/anomaly-alerts/dispatch', null, { params: { min_risk_score: 70 } });
      const inApp = response.data?.in_app_notifications_sent || 0;
      const email = response.data?.email_notifications_sent || 0;
      setGlobalSuccess(`Security alerts dispatched (${inApp} in-app, ${email} email).`);
      await loadSnapshot(true);
    } catch {
      setGlobalError('Unable to dispatch security alerts right now.');
    }
  };

  // ─── Bulk operations on existing employees ───
  const toggleSelect = useCallback((userId: string) => {
    setSelectedIds(prev => {
      const next = new Set(prev);
      if (next.has(userId)) next.delete(userId); else next.add(userId);
      return next;
    });
  }, []);

  const toggleSelectAllFiltered = useCallback((selectable: EmployeeRecord[]) => {
    setSelectedIds(prev => {
      const allSelected = selectable.every(e => prev.has(e.user_id));
      if (allSelected) {
        const next = new Set(prev);
        selectable.forEach(e => next.delete(e.user_id));
        return next;
      }
      const next = new Set(prev);
      selectable.forEach(e => next.add(e.user_id));
      return next;
    });
  }, []);

  const clearSelection = useCallback(() => setSelectedIds(new Set()), []);

  const bulkUpdateRole = useCallback(async (role: string) => {
    if (!canManageAccess || selectedIds.size === 0) return;
    setBulkActionBusy(true);
    clearNotifications();
    try {
      const res = await api.post('/admin/employees/bulk-update-role', {
        user_ids: Array.from(selectedIds), platform_role: role,
      });
      setGlobalSuccess(`Role updated for ${res.data?.updated_count || 0} employee(s) (${res.data?.skipped_count || 0} skipped).`);
      setBulkRolePickerOpen(false);
      clearSelection();
      await Promise.all([loadEmployeesAndConfig(true), loadAuditLog(1, auditFilter), loadSnapshot()]);
    } catch (e: any) {
      setGlobalError(e?.response?.data?.detail || 'Bulk role change failed.');
    } finally {
      setBulkActionBusy(false);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [canManageAccess, selectedIds, auditFilter, clearSelection]);

  const bulkUpdatePremium = useCallback(async (premium: boolean) => {
    if (!canManageAccess || selectedIds.size === 0) return;
    setBulkActionBusy(true);
    clearNotifications();
    try {
      const res = await api.post('/admin/employees/bulk-update-premium', {
        user_ids: Array.from(selectedIds), premium_access: premium,
      });
      setGlobalSuccess(`Premium ${premium ? 'granted' : 'revoked'} for ${res.data?.updated_count || 0} (${res.data?.skipped_count || 0} skipped).`);
      clearSelection();
      await Promise.all([loadEmployeesAndConfig(true), loadAuditLog(1, auditFilter), loadSnapshot()]);
    } catch (e: any) {
      setGlobalError(e?.response?.data?.detail || 'Bulk premium change failed.');
    } finally {
      setBulkActionBusy(false);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [canManageAccess, selectedIds, auditFilter, clearSelection]);

  const bulkRemove = useCallback(async () => {
    if (!canManageAccess || selectedIds.size === 0) return;
    setBulkActionBusy(true);
    clearNotifications();
    try {
      const res = await api.post('/admin/employees/bulk-remove', {
        user_ids: Array.from(selectedIds),
      });
      setGlobalSuccess(`Removed ${res.data?.removed_count || 0} employee(s) (${res.data?.skipped_count || 0} skipped — admin owners are protected).`);
      setBulkRemoveConfirm(false);
      clearSelection();
      await Promise.all([loadEmployeesAndConfig(true), loadAuditLog(1, auditFilter), loadSnapshot()]);
    } catch (e: any) {
      setGlobalError(e?.response?.data?.detail || 'Bulk remove failed.');
    } finally {
      setBulkActionBusy(false);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [canManageAccess, selectedIds, auditFilter, clearSelection]);

  const exportFilteredCsv = useCallback((list: EmployeeRecord[]) => {
    if (Platform.OS !== 'web' || typeof document === 'undefined') {
      setGlobalError('CSV export is currently available on web.');
      return;
    }
    if (!list.length) return;
    const rows = [
      ['user_id', 'email', 'name', 'platform_role', 'premium_access', 'employee_since'],
      ...list.map(e => [
        e.user_id, e.email || '', (e.name || '').replace(/"/g, '""'),
        e.platform_role || '', String(Boolean(e.premium_access)), e.employee_since || '',
      ]),
    ];
    const csv = rows.map(r => r.map(v => `"${String(v).replace(/"/g, '""')}"`).join(',')).join('\n');
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `employees_${new Date().toISOString().slice(0, 10)}.csv`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }, []);

  const exportAuditCsv = async () => {
    if (Platform.OS !== 'web' || typeof document === 'undefined') {
      setGlobalError('CSV export is currently available on web.');
      return;
    }
    try {
      const params = new URLSearchParams();
      if (auditFilter) params.set('action', auditFilter);
      const response = await api.get(`/admin/employees/audit-log/export?${params.toString()}`, { responseType: 'blob' });
      const blob = new Blob([response.data], { type: 'text/csv' });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = `employee_audit_log_${new Date().toISOString().slice(0, 10)}.csv`;
      document.body.appendChild(anchor);
      anchor.click();
      document.body.removeChild(anchor);
      URL.revokeObjectURL(url);
      setGlobalSuccess('Audit CSV export downloaded successfully.');
    } catch {
      setGlobalError('Unable to export audit CSV.');
    }
  };

  const exportApprovalEvidenceCsv = async () => {
    if (!canManageAccess) {
      setGlobalError('You do not have permission to export approval evidence.');
      return;
    }
    if (Platform.OS !== 'web' || typeof document === 'undefined') {
      setGlobalError('CSV export is currently available on web.');
      return;
    }
    setExportingApprovalEvidence(true);
    try {
      const response = await api.get('/admin/employees/approval-mode/evidence/export?limit=500', { responseType: 'blob' });
      const blob = new Blob([response.data], { type: 'text/csv' });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = `team_approval_evidence_${new Date().toISOString().slice(0, 10)}.csv`;
      document.body.appendChild(anchor);
      anchor.click();
      document.body.removeChild(anchor);
      URL.revokeObjectURL(url);
      setGlobalSuccess('Approval evidence CSV exported successfully.');
    } catch {
      setGlobalError('Unable to export approval evidence CSV.');
    } finally {
      setExportingApprovalEvidence(false);
    }
  };

  const allRoles = rolesConfig.roles || [];
  const allPermissions = rolesConfig.all_permissions || [];
  const allFeatures = rolesConfig.all_features || [];

  const filteredEmployees = useMemo(() => {
    const filtered = employees.filter((employee) => {
      if (filterRole && employee.platform_role !== filterRole) return false;
      if (filterPremium === 'premium' && !employee.premium_access) return false;
      if (filterPremium === 'standard' && employee.premium_access) return false;
      if (filterSearch.trim()) {
        const q = filterSearch.toLowerCase();
        const haystack = `${employee.email || ''} ${employee.name || ''}`.toLowerCase();
        if (!haystack.includes(q)) return false;
      }
      return true;
    });
    const dir = sortDir === 'asc' ? 1 : -1;
    const key = sortBy;
    return [...filtered].sort((a, b) => {
      let va: string | number = '';
      let vb: string | number = '';
      if (key === 'name') { va = (a.name || a.email || '').toLowerCase(); vb = (b.name || b.email || '').toLowerCase(); }
      else if (key === 'email') { va = (a.email || '').toLowerCase(); vb = (b.email || '').toLowerCase(); }
      else if (key === 'role') { va = (a.platform_role || '').toLowerCase(); vb = (b.platform_role || '').toLowerCase(); }
      else if (key === 'last_active') { va = a.last_active || ''; vb = b.last_active || ''; }
      if (va < vb) return -1 * dir;
      if (va > vb) return 1 * dir;
      return 0;
    });
  }, [employees, filterRole, filterPremium, filterSearch, sortBy, sortDir]);

  const computedStats = useMemo(() => {
    const premiumCount = employees.filter((e) => e.premium_access).length;
    const roles = new Set(employees.map((e) => e.platform_role).filter(Boolean));
    const permissionsCount = employees.reduce((sum, e) => sum + (e.employee_permissions?.length || 0), 0);
    const avgPermissions = employees.length ? Math.round((permissionsCount / employees.length) * 10) / 10 : 0;
    return {
      total: employees.length,
      premiumCount,
      rolesActive: roles.size,
      avgPermissions,
    };
  }, [employees]);

  return (
    <AdminRouteGate returnTo="/team-management">
    <AppShell>
      <TeamNotificationToasts />
      <InvitationQRModal
        visible={qrModal.visible}
        url={qrModal.url}
        email={qrModal.email}
        role={qrModal.role}
        onClose={() => setQrModal({ visible: false, url: '', email: '', role: '' })}
        onCopy={copyFromQRModal}
      />
      <View style={{ flex: 1, backgroundColor: 'transparent' }}>
        <ScrollView contentContainerStyle={{ padding: isMedium ? 28 : 16, paddingBottom: 120 }} data-testid="team-management-page" testID="team-management-page">

          <View
            style={{
              paddingBottom: 18,
              marginBottom: 18,
              borderBottomWidth: 1,
              borderBottomColor: colors.border,
            }}
            data-testid="team-management-header-card" testID="team-management-header-card"
          >
            <View style={{ flexDirection: isMedium ? 'row' : 'column', justifyContent: 'space-between', gap: 14, alignItems: isMedium ? 'flex-end' : 'stretch' }}>
              <View style={{ flex: 1 }}>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                  <View style={{ width: 6, height: 6, borderRadius: 3, backgroundColor: colors.success }} />
                  <Text style={{ color: colors.textMuted, fontSize: 10, fontWeight: '700', textTransform: 'uppercase', letterSpacing: 1.4 }}>
                    {t('teamManagement.header.badge')}
                  </Text>
                  <View
                    data-testid="team-live-indicator"
                    testID="team-live-indicator"
                    style={{
                      flexDirection: 'row', alignItems: 'center', gap: 4,
                      paddingHorizontal: 8, paddingVertical: 2, borderRadius: 999,
                      backgroundColor: colors.successSoft, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(colors.success, '55'),
                      marginLeft: 4,
                    }}>
                    <View style={{ width: 5, height: 5, borderRadius: 3, backgroundColor: colors.success }} />
                    <Text style={{ color: colors.successText, fontSize: 9, fontWeight: '800', letterSpacing: 0.6 }}>LIVE</Text>
                  </View>
                </View>
                <Text style={{ color: colors.text, fontSize: isMedium ? 28 : 22, fontWeight: '800', marginTop: 8, letterSpacing: -0.8 }} data-testid="team-management-title" testID="team-management-title">
                  {t('teamManagement.header.title')}
                </Text>
                <Text style={{ color: colors.textSec, marginTop: 4, fontSize: 13, lineHeight: 20 }} data-testid="team-management-subtitle" testID="team-management-subtitle">
                  {t('teamManagement.header.subtitle')}
                </Text>
                <View
                  data-testid="team-approval-mode-badge"
                  testID="team-approval-mode-badge"
                  style={{
                    marginTop: 10,
                    alignSelf: 'flex-start',
                    flexDirection: 'row',
                    alignItems: 'center',
                    gap: 8,
                    borderRadius: 999,
                    borderWidth: 1,
                    borderColor: colors.border,
                    backgroundColor: Platform.OS === 'web' ? (globalThis as any).__alphaColor(colors.surface, 'B0') : colors.surface,
                    paddingHorizontal: 10,
                    paddingVertical: 6,
                    ...(Platform.OS === 'web' ? { backdropFilter: 'blur(10px)', WebkitBackdropFilter: 'blur(10px)' } as any : {}),
                  }}
                >
                  <Ionicons name="shield-checkmark" size={12} color={colors.primary} />
                  <Text style={{ color: colors.textMuted, fontSize: 10, fontWeight: '700', textTransform: 'uppercase', letterSpacing: 0.6 }}>
                    Approval Mode
                  </Text>
                  <Text
                    data-testid="team-approval-mode-value"
                    testID="team-approval-mode-value"
                    style={{ color: colors.text, fontSize: 11, fontWeight: '800' }}
                  >
                    {loadingApprovalMode ? 'Checking…' : (approvalMode?.approval_label || 'Unavailable')}
                  </Text>
                  <Text
                    data-testid="team-approval-evidence-count"
                    testID="team-approval-evidence-count"
                    style={{ color: colors.textSec, fontSize: 10, fontWeight: '700' }}
                  >
                    {`Evidence: ${approvalMode?.evidence_count || 0}`}
                  </Text>
                </View>
              </View>

              <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
                <TouchableOpacity
                  onPress={() => { void loadEmployeesAndConfig(); void loadAuditLog(1, auditFilter); void loadSnapshot(true); void loadApprovalMode(); }}
                  data-testid="team-refresh-button" testID="team-refresh-button"
                  style={{
                    flexDirection: 'row', alignItems: 'center', gap: 6,
                    backgroundColor: Platform.OS === 'web' ? (globalThis as any).__alphaColor(colors.surface, 'B0') : colors.surface, borderWidth: 1, borderColor: colors.border, borderRadius: 8,
                    paddingHorizontal: 12, paddingVertical: 9,
                    ...(Platform.OS === 'web' ? { backdropFilter: 'blur(10px)', WebkitBackdropFilter: 'blur(10px)' } as any : {}),
                  }}
                >
                  <Ionicons name="refresh" size={13} color={colors.textSec} />
                  <Text style={{ color: colors.textSec, fontWeight: '700', fontSize: 12 }}>{t('teamManagement.actions.refresh')}</Text>
                </TouchableOpacity>

                {canManageAccess && (
                  <TouchableOpacity
                    onPress={exportApprovalEvidenceCsv}
                    disabled={exportingApprovalEvidence}
                    data-testid="team-export-approval-evidence-button"
                    testID="team-export-approval-evidence-button"
                    style={{
                      flexDirection: 'row', alignItems: 'center', gap: 6,
                      backgroundColor: Platform.OS === 'web' ? (globalThis as any).__alphaColor(colors.surface, 'B0') : colors.surface, borderWidth: 1, borderColor: colors.border, borderRadius: 8,
                      paddingHorizontal: 12, paddingVertical: 9,
                      ...(Platform.OS === 'web' ? { backdropFilter: 'blur(10px)', WebkitBackdropFilter: 'blur(10px)' } as any : {}),
                      opacity: exportingApprovalEvidence ? 0.6 : 1,
                    }}
                  >
                    {exportingApprovalEvidence ? (
                      <ActivityIndicator size="small" color={colors.textSec} />
                    ) : (
                      <Ionicons name="download-outline" size={13} color={colors.textSec} />
                    )}
                    <Text style={{ color: colors.textSec, fontWeight: '700', fontSize: 12 }}>
                      {exportingApprovalEvidence ? 'Exporting…' : 'Export Approval Evidence'}
                    </Text>
                  </TouchableOpacity>
                )}

                {canManageAccess && (
                  <TouchableOpacity
                    onPress={() => router.push('/policy-console')}
                    data-testid="team-open-policy-console-button" testID="team-open-policy-console-button"
                    style={{
                      flexDirection: 'row', alignItems: 'center', gap: 6,
                      backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, borderRadius: 8,
                      paddingHorizontal: 12, paddingVertical: 9,
                    }}
                  >
                    <Ionicons name="shield-half" size={13} color={colors.textSec} />
                    <Text style={{ color: colors.textSec, fontWeight: '700', fontSize: 12 }}>{t("autofix.watchSweep1.policy.console")}</Text>
                  </TouchableOpacity>
                )}

                {canManageAccess && (
                  <TouchableOpacity
                    onPress={openBulkInvite}
                    data-testid="team-open-bulk-invite-button" testID="team-open-bulk-invite-button"
                    style={{
                      flexDirection: 'row', alignItems: 'center', gap: 6,
                      backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, borderRadius: 8,
                      paddingHorizontal: 12, paddingVertical: 9,
                    }}
                  >
                    <Ionicons name="people-circle-outline" size={13} color={colors.textSec} />
                  <Text style={{ color: colors.textSec, fontWeight: '700', fontSize: 12 }}>{t('teamManagement.actions.bulkInvite')}</Text>
                  </TouchableOpacity>
                )}

                {canManageAccess && (
                  <TouchableOpacity
                    onPress={openCreateEditor}
                    data-testid="team-open-add-employee-button" testID="team-open-add-employee-button"
                    style={{
                      flexDirection: 'row', alignItems: 'center', gap: 6,
                      backgroundColor: colors.primary, borderRadius: 8,
                      paddingHorizontal: 14, paddingVertical: 9,
                    }}
                  >
                    <Ionicons name="person-add" size={14} color={colors.primaryText} />
                    <Text style={{ color: colors.primaryText, fontWeight: '800', fontSize: 12 }}>{t("autofix.watchSweep1.add.employee")}</Text>
                  </TouchableOpacity>
                )}
              </View>
            </View>
          </View>

          {globalError ? (
            <NotificationBanner
              type="error"
              message={globalError}
              onDismiss={() => setGlobalError('')}
              testId="team-error-banner"
            />
          ) : null}

          {globalSuccess ? (
            <NotificationBanner
              type="success"
              message={globalSuccess}
              onDismiss={() => setGlobalSuccess('')}
              testId="team-success-banner"
            />
          ) : null}

          {bulkOpen && canManageAccess ? (
            <View
              data-testid="team-bulk-invite-card" testID="team-bulk-invite-card"
              style={{
                borderRadius: 14,
                borderWidth: 1,
                borderColor: bulkDragOver ? colors.primary : colors.border,
                backgroundColor: colors.surface,
                padding: 18,
                marginBottom: 16,
              }}
              {...(Platform.OS === 'web' ? {
                onDragOver: (e: any) => { e.preventDefault(); setBulkDragOver(true); },
                onDragLeave: () => setBulkDragOver(false),
                onDrop: (e: any) => {
                  e.preventDefault();
                  setBulkDragOver(false);
                  const file = e.dataTransfer?.files?.[0];
                  if (file) void handleBulkFile(file);
                },
              } : {})}
            >
              <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12 }}>
                <View style={{ flex: 1 }}>
                  <Text style={{ color: colors.text, fontSize: 15, fontWeight: '800', letterSpacing: -0.2 }}>{t("autofix.watchSweep1.bulk.invite.employees")}</Text>
                  <Text style={{ color: colors.textMuted, fontSize: 12, marginTop: 3, lineHeight: 18 }}>{t("autofix.watchSweep1.paste.csv.one.row.per.employee.or.drop")}<Text style={{ color: colors.text, fontFamily: Platform.OS === 'web' ? 'monospace' as any : undefined, fontWeight: '700' }}>{t("autofix.watchSweep1.email.role.premium")}</Text>{t("autofix.watchSweep1.role.defaults.to")}{rolesConfig.roles[0] || 'first role'}{t("autofix.watchSweep1.premium.is.optional")}</Text>
                </View>
                <TouchableOpacity
                  onPress={closeBulkInvite}
                  data-testid="team-bulk-close-button" testID="team-bulk-close-button"
                  style={{ padding: 4 }}
                >
                  <Ionicons name="close" size={18} color={colors.textMuted} />
                </TouchableOpacity>
              </View>

              <TextInput
                value={bulkText}
                onChangeText={setBulkText}
                multiline
                numberOfLines={6}
                placeholder={`alice@example.com,Support\nbob@example.com,Manager,true\ncara@example.com,Finance Advisor`}
                placeholderTextColor={colors.textMuted}
                data-testid="team-bulk-textarea" testID="team-bulk-textarea"
                style={{
                  marginTop: 12,
                  minHeight: 120,
                  borderRadius: 10,
                  borderWidth: 1,
                  borderColor: colors.border,
                  backgroundColor: colors.bg,
                  color: colors.text,
                  padding: 12,
                  fontSize: 13,
                  fontFamily: Platform.OS === 'web' ? ('ui-monospace, Menlo, monospace' as any) : undefined,
                  ...(Platform.OS === 'web' ? { outlineStyle: 'none' } as any : {}),
                }}
              />

              <View style={{ flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', gap: 10, marginTop: 12 }}>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: colors.bg, borderWidth: 1, borderColor: colors.border, borderRadius: 999, paddingHorizontal: 10, paddingVertical: 5 }}>
                  <View style={{ width: 6, height: 6, borderRadius: 3, backgroundColor: bulkValidCount > 0 ? colors.success : colors.textMuted }} />
                  <Text style={{ color: colors.textSec, fontSize: 11, fontWeight: '700' }} data-testid="team-bulk-valid-count" testID="team-bulk-valid-count">
                    {bulkValidCount}{t("autofix.watchSweep1.valid")}{bulkParsed.length}{t("autofix.watchSweep1.parsed")}</Text>
                </View>
                {Platform.OS === 'web' && (
                  // @ts-ignore — web-only input file
                  <input
                    type="file"
                    accept=".csv,text/csv,text/plain"
                    data-testid="team-bulk-file-input"
                    style={{ color: colors.textSec, fontSize: 11 } as any}
                    onChange={(e: any) => {
                      const f = e.target?.files?.[0];
                      if (f) void handleBulkFile(f);
                    }}
                  />
                )}
                <View style={{ flex: 1 }} />
                <TouchableOpacity
                  onPress={closeBulkInvite}
                  disabled={bulkSubmitting}
                  data-testid="team-bulk-cancel-button" testID="team-bulk-cancel-button"
                  style={{
                    borderRadius: 8, borderWidth: 1, borderColor: colors.border,
                    backgroundColor: colors.surface, paddingHorizontal: 14, paddingVertical: 9,
                  }}
                >
                  <Text style={{ color: colors.textSec, fontWeight: '700', fontSize: 12 }}>{t('common.cancel')}</Text>
                </TouchableOpacity>
                <TouchableOpacity
                  onPress={submitBulkInvite}
                  disabled={bulkSubmitting || bulkValidCount === 0}
                  data-testid="team-bulk-submit-button" testID="team-bulk-submit-button"
                  style={{
                    borderRadius: 8, backgroundColor: colors.primary,
                    paddingHorizontal: 14, paddingVertical: 9,
                    opacity: bulkSubmitting || bulkValidCount === 0 ? 0.55 : 1,
                    flexDirection: 'row', alignItems: 'center', gap: 6,
                  }}
                >
                  {bulkSubmitting && <ActivityIndicator size="small" color={colors.primaryText} />}
                  <Text style={{ color: colors.primaryText, fontWeight: '800', fontSize: 12 }}>
                    {bulkSubmitting ? t('teamManagement.bulk.inviting') : t('teamManagement.bulk.inviteCount').replace('{count}', String(bulkValidCount || ''))}
                  </Text>
                </TouchableOpacity>
              </View>

              {bulkResult ? (
                <View style={{ marginTop: 14, borderTopWidth: 1, borderTopColor: colors.border, paddingTop: 12 }} data-testid="team-bulk-result" testID="team-bulk-result">
                  <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10, marginBottom: 10 }}>
                    {bulkResult.added > 0 ? (
                      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: colors.successSoft, borderRadius: 999, paddingHorizontal: 10, paddingVertical: 5 }}>
                        <Ionicons name="checkmark-circle" size={12} color={colors.successText} />
                        <Text style={{ color: colors.successText, fontSize: 11, fontWeight: '700' }} data-testid="team-bulk-added-count" testID="team-bulk-added-count">
                          {bulkResult.added}{t("autofix.watchSweep1.added")}</Text>
                      </View>
                    ) : null}
                    {(bulkResult.invited_count || 0) > 0 ? (
                      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: colors.warningSoft, borderRadius: 999, paddingHorizontal: 10, paddingVertical: 5 }}>
                        <Ionicons name="mail-outline" size={12} color={colors.warningText} />
                        <Text style={{ color: colors.warningText, fontSize: 11, fontWeight: '700' }} data-testid="team-bulk-invited-count" testID="team-bulk-invited-count">
                          {bulkResult.invited_count}{t("autofix.watchSweep1.invited.by.email")}</Text>
                      </View>
                    ) : null}
                    {bulkResult.failed_count > 0 ? (
                      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: colors.errorSoft, borderRadius: 999, paddingHorizontal: 10, paddingVertical: 5 }}>
                        <Ionicons name="alert-circle" size={12} color={colors.error} />
                        <Text style={{ color: colors.error, fontSize: 11, fontWeight: '700' }} data-testid="team-bulk-failed-count" testID="team-bulk-failed-count">
                          {bulkResult.failed_count}{t("admin.gdpr.errors.failed")}</Text>
                      </View>
                    ) : null}
                  </View>
                  {bulkResult.failed.length > 0 ? (
                    <View style={{ gap: 6, marginTop: 4 }}>
                      <Text style={{ color: colors.error, fontSize: 11, fontWeight: '800', textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 2 }}>{t("autofix.watchSweep1.not.sent.reasons")}</Text>
                      {bulkResult.failed.slice(0, 10).map((f, i) => (
                        <View
                          key={`bulk-fail-${i}`}
                          data-testid={`team-bulk-failed-row-${i}`} testID={`team-bulk-failed-row-${i}`}
                          style={{
                            flexDirection: 'row', alignItems: 'center', gap: 8, paddingVertical: 6, paddingHorizontal: 10,
                            borderRadius: 8, backgroundColor: colors.errorSoft, borderLeftWidth: 3, borderLeftColor: colors.error,
                          }}>
                          <Ionicons name="close-circle" size={14} color={colors.error} />
                          <Text style={{ flex: 1, color: colors.text, fontSize: 12, fontWeight: '600', fontFamily: Platform.OS === 'web' ? 'monospace' as any : undefined }} numberOfLines={1}>{f.email}</Text>
                          <Text style={{ color: colors.error, fontSize: 11, fontWeight: '700' }} numberOfLines={1}>{f.reason}</Text>
                        </View>
                      ))}
                      {bulkResult.failed.length > 10 ? (
                        <Text style={{ color: colors.textMuted, fontSize: 11, fontStyle: 'italic', marginTop: 2 }}>
                          + {bulkResult.failed.length - 10}{t("autofix.watchSweep1.more.not.shown")}</Text>
                      ) : null}
                    </View>
                  ) : null}
                </View>
              ) : null}
            </View>
          ) : null}

          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 12, marginBottom: 14 }}>
            <MetricCard
              label={t('teamManagement.stats.totalEmployees')}
              value={computedStats.total}
              icon="people"
              color={colors.purpleText}
              testId="team-metric-total-employees"
            />
            <MetricCard
              label={t('teamManagement.stats.premiumAccess')}
              value={computedStats.premiumCount}
              icon="diamond"
              color={colors.warningText}
              testId="team-metric-premium-access"
            />
            <MetricCard
              label={t('teamManagement.stats.rolesActive')}
              value={computedStats.rolesActive}
              icon="shield-checkmark"
              color={colors.primary}
              testId="team-metric-roles-active"
            />
            <MetricCard
              label={t('teamManagement.stats.avgPermissions')}
              value={computedStats.avgPermissions}
              icon="key"
              color={colors.successText}
              testId="team-metric-avg-permissions"
            />
          </View>

          <View style={{ flexDirection: isDesktop ? 'row' : 'column', gap: 14 }}>
            <View style={{ flex: 2, minWidth: 0 }}>
                <PanelCard title={t('teamManagement.panels.directoryTitle')} subtitle={t('teamManagement.panels.directorySubtitle')} testId="employee-directory-panel">
                {/* Row 1: search input (flex:1) + access filter (right-aligned) */}
                <View style={{ flexDirection: isMedium ? 'row' : 'column', gap: 10, marginBottom: 10, alignItems: isMedium ? 'center' : 'stretch' }}>
                  <View style={{ flex: 1, flexDirection: 'row', alignItems: 'center', backgroundColor: T.inputBg, borderWidth: 1, borderColor: T.inputBorder, borderRadius: 10, paddingHorizontal: 12, minHeight: 42 }}>
                    <Ionicons name="search" size={15} color={T.textMuted} />
                    <TextInput
                      value={filterSearch}
                      onChangeText={setFilterSearch}
                      placeholder={t('teamManagement.placeholders.searchEmployee')}
                      placeholderTextColor={T.textMuted}
                      style={{ flex: 1, color: T.text, paddingVertical: 10, paddingHorizontal: 8, fontSize: 13, minWidth: 0 }}
                      data-testid="employee-directory-search-input" testID="employee-directory-search-input"
                    />
                    {filterSearch ? (
                      <TouchableOpacity onPress={() => setFilterSearch('')} accessibilityLabel="Clear search" style={{ padding: 4 }} data-testid="employee-directory-search-clear" testID="employee-directory-search-clear">
                        <Ionicons name="close-circle" size={16} color={T.textMuted} />
                      </TouchableOpacity>
                    ) : null}
                  </View>

                  <View style={{ flexDirection: 'row', gap: 6, flexWrap: 'wrap' }}>
                    <PillButton
                      label={t('teamManagement.filters.allAccess')}
                      active={filterPremium === 'all'}
                      onPress={() => setFilterPremium('all')}
                      testId="employee-premium-filter-all"
                    />
                    <PillButton
                      label="Premium"
                      active={filterPremium === 'premium'}
                      onPress={() => setFilterPremium('premium')}
                      testId="employee-premium-filter-premium"
                    />
                    <PillButton
                      label="Standard"
                      active={filterPremium === 'standard'}
                      onPress={() => setFilterPremium('standard')}
                      testId="employee-premium-filter-standard"
                    />
                  </View>
                </View>

                {/* Row 2: full-width role-pill horizontal scroll */}
                <View style={{ marginBottom: 14 }}>
                  <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 6, paddingRight: 8 }}>
                    <PillButton
                      label="All Roles"
                      active={!filterRole}
                      onPress={() => setFilterRole('')}
                      testId="employee-role-filter-all"
                    />
                    {allRoles.map((role) => (
                      <PillButton
                        key={role}
                        label={role}
                        active={filterRole === role}
                        onPress={() => setFilterRole(filterRole === role ? '' : role)}
                        testId={`employee-role-filter-${toTestId(role)}`}
                      />
                    ))}
                  </ScrollView>
                </View>

                {/* Sort controls */}
                <View
                  data-testid="employee-sort-bar"
                  testID="employee-sort-bar"
                  style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 10, flexWrap: 'wrap' }}>
                  <Text style={{ color: T.textMuted, fontSize: 11, fontWeight: '700', textTransform: 'uppercase', letterSpacing: 0.6 }}>{t("autofix.watchSweep1.sort.by")}</Text>
                  {(['name', 'email', 'role', 'last_active'] as const).map((key) => {
                    const active = sortBy === key;
                    const label = key === 'last_active' ? 'Last Active' : key.charAt(0).toUpperCase() + key.slice(1);
                    return (
                      <TouchableOpacity
                        key={key}
                        onPress={() => toggleSort(key)}
                        data-testid={`employee-sort-${key}`}
                        testID={`employee-sort-${key}`}
                        style={{
                          flexDirection: 'row', alignItems: 'center', gap: 4,
                          paddingHorizontal: 10, paddingVertical: 6, borderRadius: 999,
                          backgroundColor: active ? colors.primary : T.surface,
                          borderWidth: 1, borderColor: active ? colors.primary : T.border,
                        }}>
                        <Text style={{ color: active ? colors.primaryText : T.textSec, fontSize: 12, fontWeight: '700' }}>{label}</Text>
                        {active ? (
                          <Ionicons name={sortDir === 'asc' ? 'arrow-up' : 'arrow-down'} size={12} color={colors.primaryText} />
                        ) : null}
                      </TouchableOpacity>
                    );
                  })}
                </View>

                {/* Bulk action bar + select-all + CSV export */}
                {(() => {
                  const selectable = filteredEmployees.filter(e => !e.is_admin);
                  const allSelected = selectable.length > 0 && selectable.every(e => selectedIds.has(e.user_id));
                  const selectedFiltered = selectable.filter(e => selectedIds.has(e.user_id));
                  return (
                    <View
                      data-testid="team-bulk-action-bar"
                      testID="team-bulk-action-bar"
                      style={{
                        flexDirection: 'row', flexWrap: 'wrap', gap: 10, alignItems: 'center',
                        marginBottom: 12, padding: 10, borderRadius: 10,
                        backgroundColor: selectedIds.size > 0 ? colors.primarySoft : T.bg,
                        borderWidth: 1, borderColor: selectedIds.size > 0 ? (globalThis as any).__alphaColor(colors.primary, '55') : T.border,
                      }}>
                      {canManageAccess && selectable.length > 0 ? (
                        <TouchableOpacity
                          onPress={() => toggleSelectAllFiltered(selectable)}
                          data-testid="team-select-all-toggle"
                          testID="team-select-all-toggle"
                          accessibilityLabel={allSelected ? 'Deselect all employees' : 'Select all employees'}
                          style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                          <View style={{
                            width: 18, height: 18, borderRadius: 4, borderWidth: 2,
                            borderColor: allSelected ? colors.primary : T.border,
                            backgroundColor: allSelected ? colors.primary : 'transparent',
                            alignItems: 'center', justifyContent: 'center',
                          }}>
                            {allSelected ? <Ionicons name="checkmark" size={12} color={colors.primaryText} /> : null}
                          </View>
                          <Text style={{ color: T.text, fontSize: 12, fontWeight: '700' }}>
                            {selectedIds.size > 0 ? `${selectedIds.size} selected` : 'Select all'}
                          </Text>
                        </TouchableOpacity>
                      ) : null}

                      {selectedIds.size > 0 && canManageAccess ? (
                        <>
                          <TouchableOpacity
                            onPress={() => setBulkRolePickerOpen(v => !v)}
                            disabled={bulkActionBusy}
                            data-testid="team-bulk-change-role-button"
                            testID="team-bulk-change-role-button"
                            style={{ flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 12, paddingVertical: 7, borderRadius: 8, backgroundColor: colors.primary, opacity: bulkActionBusy ? 0.55 : 1 }}>
                            <Ionicons name="shield-checkmark-outline" size={14} color={colors.primaryText} />
                            <Text style={{ color: colors.primaryText, fontSize: 12, fontWeight: '700' }}>{t("autofix.watchSweep1.change.role")}</Text>
                          </TouchableOpacity>
                          <TouchableOpacity
                            onPress={() => bulkUpdatePremium(true)}
                            disabled={bulkActionBusy}
                            data-testid="team-bulk-grant-premium-button"
                            testID="team-bulk-grant-premium-button"
                            style={{ flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 12, paddingVertical: 7, borderRadius: 8, backgroundColor: (globalThis as any).__alphaColor(colors.warning, '22'), borderWidth: 1, borderColor: (globalThis as any).__alphaColor(colors.warning, '55'), opacity: bulkActionBusy ? 0.55 : 1 }}>
                            <Ionicons name="diamond-outline" size={14} color={colors.warningText} />
                            <Text style={{ color: colors.warningText, fontSize: 12, fontWeight: '700' }}>{t("autofix.watchSweep1.grant.premium")}</Text>
                          </TouchableOpacity>
                          <TouchableOpacity
                            onPress={() => bulkUpdatePremium(false)}
                            disabled={bulkActionBusy}
                            data-testid="team-bulk-revoke-premium-button"
                            testID="team-bulk-revoke-premium-button"
                            style={{ flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 12, paddingVertical: 7, borderRadius: 8, backgroundColor: T.surface, borderWidth: 1, borderColor: T.border, opacity: bulkActionBusy ? 0.55 : 1 }}>
                            <Ionicons name="close-outline" size={14} color={T.textSec} />
                            <Text style={{ color: T.textSec, fontSize: 12, fontWeight: '700' }}>{t("autofix.watchSweep1.revoke.premium")}</Text>
                          </TouchableOpacity>
                          <TouchableOpacity
                            onPress={() => setBulkRemoveConfirm(true)}
                            disabled={bulkActionBusy}
                            data-testid="team-bulk-remove-button"
                            testID="team-bulk-remove-button"
                            style={{ flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 12, paddingVertical: 7, borderRadius: 8, backgroundColor: (globalThis as any).__alphaColor(colors.error, '18'), borderWidth: 1, borderColor: (globalThis as any).__alphaColor(colors.error, '55'), opacity: bulkActionBusy ? 0.55 : 1 }}>
                            <Ionicons name="trash-outline" size={14} color={colors.error} />
                            <Text style={{ color: colors.error, fontSize: 12, fontWeight: '700' }}>{t("securityDashboard.knownDevices.actions.remove")}</Text>
                          </TouchableOpacity>
                          <TouchableOpacity
                            onPress={clearSelection}
                            data-testid="team-bulk-clear-button"
                            testID="team-bulk-clear-button"
                            style={{ paddingHorizontal: 10, paddingVertical: 7 }}>
                            <Text style={{ color: T.textMuted, fontSize: 12, fontWeight: '700' }}>{t("admin.themeDrift.bulk.clear")}</Text>
                          </TouchableOpacity>
                        </>
                      ) : null}

                      <View style={{ flex: 1 }} />

                      <TouchableOpacity
                        onPress={() => exportFilteredCsv(filteredEmployees)}
                        disabled={!filteredEmployees.length}
                        data-testid="team-export-csv-button"
                        testID="team-export-csv-button"
                        style={{ flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 12, paddingVertical: 7, borderRadius: 8, backgroundColor: T.surface, borderWidth: 1, borderColor: T.border, opacity: filteredEmployees.length ? 1 : 0.5 }}>
                        <Ionicons name="download-outline" size={14} color={T.textSec} />
                        <Text style={{ color: T.textSec, fontSize: 12, fontWeight: '700' }}>{t('teamManagement.actions.exportCsv').replace('{count}', String(filteredEmployees.length))}</Text>
                      </TouchableOpacity>
                    </View>
                  );
                })()}

                {/* Bulk role picker popover */}
                {bulkRolePickerOpen && canManageAccess ? (
                  <View
                    data-testid="team-bulk-role-picker"
                    testID="team-bulk-role-picker"
                    style={{ marginBottom: 12, padding: 10, borderRadius: 10, backgroundColor: T.surface, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(colors.primary, '55') }}>
                    <Text style={{ color: T.textSec, fontSize: 11, fontWeight: '700', textTransform: 'uppercase', marginBottom: 6 }}>{t("autofix.watchSweep1.pick.a.new.role.for")}{selectedIds.size}{t("autofix.watchSweep1.employee.s")}</Text>
                    <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6 }}>
                      {(rolesConfig?.roles || []).map((r: string) => (
                        <TouchableOpacity
                          key={`bulk-role-${r}`}
                          onPress={() => bulkUpdateRole(r)}
                          disabled={bulkActionBusy}
                          data-testid={`team-bulk-role-option-${r}`}
                          testID={`team-bulk-role-option-${r}`}
                          style={{ paddingHorizontal: 10, paddingVertical: 6, borderRadius: 999, borderWidth: 1, borderColor: T.border, backgroundColor: T.bg }}>
                          <Text style={{ color: T.text, fontSize: 12, fontWeight: '700' }}>{r}</Text>
                        </TouchableOpacity>
                      ))}
                    </View>
                  </View>
                ) : null}

                {/* Bulk remove confirmation */}
                {bulkRemoveConfirm ? (
                  <View
                    data-testid="team-bulk-remove-confirm"
                    testID="team-bulk-remove-confirm"
                    style={{ marginBottom: 12, padding: 12, borderRadius: 10, backgroundColor: (globalThis as any).__alphaColor(colors.error, '10'), borderWidth: 1, borderColor: (globalThis as any).__alphaColor(colors.error, '55') }}>
                    <Text style={{ color: colors.error, fontSize: 13, fontWeight: '800', marginBottom: 6 }}>{t("securityDashboard.knownDevices.actions.remove")}{selectedIds.size}{t("autofix.watchSweep1.employee.s.2")}</Text>
                    <Text style={{ color: T.textSec, fontSize: 12, marginBottom: 8 }}>{t("autofix.watchSweep1.they.will.lose.platform.employee.status.and.all")}</Text>
                    <View style={{ flexDirection: 'row', gap: 8 }}>
                      <TouchableOpacity
                        onPress={bulkRemove}
                        disabled={bulkActionBusy}
                        data-testid="team-bulk-remove-confirm-button"
                        testID="team-bulk-remove-confirm-button"
                        style={{ paddingHorizontal: 14, paddingVertical: 8, borderRadius: 8, backgroundColor: colors.error, opacity: bulkActionBusy ? 0.55 : 1, flexDirection: 'row', gap: 6, alignItems: 'center' }}>
                        {bulkActionBusy ? <ActivityIndicator size="small" color={colors.primaryText} /> : null}
                        <Text style={{ color: colors.primaryText, fontSize: 12, fontWeight: '700' }}>{t("autofix.watchSweep1.confirm.removal")}</Text>
                      </TouchableOpacity>
                      <TouchableOpacity
                        onPress={() => setBulkRemoveConfirm(false)}
                        data-testid="team-bulk-remove-cancel-button"
                        testID="team-bulk-remove-cancel-button"
                        style={{ paddingHorizontal: 14, paddingVertical: 8, borderRadius: 8, backgroundColor: T.bg, borderWidth: 1, borderColor: T.border }}>
                        <Text style={{ color: T.textSec, fontSize: 12, fontWeight: '700' }}>{t("admin.onboardingAB.actions.cancel")}</Text>
                      </TouchableOpacity>
                    </View>
                  </View>
                ) : null}

                {loadingEmployees ? (
                  <View style={{ gap: 10 }} data-testid="employee-directory-loading" testID="employee-directory-loading">
                    {[0, 1, 2, 3].map((i) => (
                      <View
                        key={i}
                        style={{
                          borderRadius: 12,
                          borderWidth: 1,
                          borderColor: T.border,
                          backgroundColor: T.surface,
                          padding: 14,
                          flexDirection: 'row',
                          alignItems: 'center',
                          gap: 12,
                          opacity: 0.75 - i * 0.12,
                        }}>
                        <View style={{ width: 36, height: 36, borderRadius: 18, backgroundColor: T.bg }} />
                        <View style={{ flex: 1, gap: 6 }}>
                          <View style={{ width: '55%', height: 12, borderRadius: 6, backgroundColor: T.bg }} />
                          <View style={{ width: '35%', height: 10, borderRadius: 5, backgroundColor: T.bg }} />
                        </View>
                        <View style={{ width: 70, height: 22, borderRadius: 11, backgroundColor: T.bg }} />
                      </View>
                    ))}
                    <Text style={{ color: T.textMuted, fontSize: 11, textAlign: 'center', marginTop: 6 }}>{t("autofix.watchSweep1.loading.employees")}</Text>
                  </View>
                ) : filteredEmployees.length === 0 ? (
                  <View style={{ paddingVertical: 40, alignItems: 'center' }} data-testid="employee-directory-empty-state" testID="employee-directory-empty-state">
                    <Ionicons name="people-outline" size={44} color={colors.textMuted} />
                    <Text style={{ color: T.text, fontSize: 18, fontWeight: '700', marginTop: 12 }}>
                      {employees.length ? 'No matching employees' : 'No employees yet'}
                    </Text>
                    <Text style={{ color: T.textSec, marginTop: 6, textAlign: 'center', maxWidth: 400 }}>
                      {employees.length
                        ? 'Adjust role, premium, or search filters to find the employee record.'
                        : 'Use Add Employee to assign roles and permissions for your first team member.'}
                    </Text>
                  </View>
                ) : (
                  <View style={{ gap: 10 }}>
                    {filteredEmployees.map((employee) => {
                      const role = employee.platform_role || 'Custom';
                      const roleColor = getRoleColor(role);
                      const roleIcon = ROLE_ICONS[role] || 'person';
                      const canEditRow = canManageAccess && !employee.is_admin;
                      return (
                        <View
                          key={employee.user_id}
                          style={{
                            borderRadius: 12,
                            borderWidth: 1,
                            borderColor: T.border,
                            backgroundColor: T.surface,
                            padding: 14,
                          }}
                          data-testid={`employee-row-${employee.user_id}`} testID={`employee-row-${employee.user_id}`}
                        >
                          <View style={{ flexDirection: isMedium ? 'row' : 'column', gap: 12 }}>
                            {canManageAccess && !employee.is_admin ? (
                              <TouchableOpacity
                                onPress={() => toggleSelect(employee.user_id)}
                                data-testid={`employee-row-select-${employee.user_id}`}
                                testID={`employee-row-select-${employee.user_id}`}
                                accessibilityLabel={selectedIds.has(employee.user_id) ? 'Deselect employee' : 'Select employee'}
                                style={{ alignSelf: 'center', padding: 6 }}>
                                <View style={{
                                  width: 20, height: 20, borderRadius: 4, borderWidth: 2,
                                  borderColor: selectedIds.has(employee.user_id) ? colors.primary : T.border,
                                  backgroundColor: selectedIds.has(employee.user_id) ? colors.primary : 'transparent',
                                  alignItems: 'center', justifyContent: 'center',
                                }}>
                                  {selectedIds.has(employee.user_id) ? <Ionicons name="checkmark" size={13} color={colors.primaryText} /> : null}
                                </View>
                              </TouchableOpacity>
                            ) : null}
                            <View style={{ flex: 1, minWidth: 0 }}>
                              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
                                <View style={{ width: 38, height: 38, borderRadius: 10, backgroundColor: (globalThis as any).__alphaColor(roleColor, '28'), alignItems: 'center', justifyContent: 'center' }}>
                                  <Text style={{ color: roleColor, fontWeight: '800' }}>{(employee.name || employee.email || '?')[0].toUpperCase()}</Text>
                                </View>
                                <View style={{ flex: 1, minWidth: 0 }}>
                                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                                    <Text style={{ color: T.text, fontSize: 14, fontWeight: '700' }} numberOfLines={1}>
                                      {employee.name || 'Unnamed Employee'}
                                    </Text>
                                    {employee.is_admin ? (
                                      <Badge label="OWNER ADMIN" color={colors.error} testId={`employee-admin-badge-${employee.user_id}`} />
                                    ) : null}
                                  </View>
                                  <Text style={{ color: T.textSec, marginTop: 2, fontSize: 12 }} numberOfLines={1}>
                                    {employee.email}
                                  </Text>
                                </View>
                              </View>

                              <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 10 }}>
                                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 10, paddingVertical: 6, borderRadius: 8, backgroundColor: (globalThis as any).__alphaColor(roleColor, '20') }}>
                                  <Ionicons name={roleIcon as any} size={12} color={roleColor} />
                                  <Text style={{ color: roleColor, fontWeight: '700', fontSize: 11 }} data-testid={`employee-role-${employee.user_id}`} testID={`employee-role-${employee.user_id}`}>
                                    {role}
                                  </Text>
                                </View>

                                <Badge
                                  label={employee.premium_access ? 'PREMIUM ACCESS' : 'STANDARD ACCESS'}
                                  color={employee.premium_access ? colors.warning : colors.textMuted}
                                  testId={`employee-premium-status-${employee.user_id}`}
                                />

                                <Badge
                                  label={`${employee.employee_permissions?.length || 0} permission(s)`}
                                  color={colors.successText}
                                  testId={`employee-permission-count-${employee.user_id}`}
                                />

                                <Badge
                                  label={`${employee.feature_access?.length || 0} feature(s)`}
                                  color={colors.info}
                                  testId={`employee-feature-count-${employee.user_id}`}
                                />
                              </View>
                            </View>

                            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                              <TouchableOpacity
                                disabled={!canEditRow}
                                onPress={() => openEditEditor(employee)}
                                data-testid={`employee-edit-button-${employee.user_id}`} testID={`employee-edit-button-${employee.user_id}`}
                                style={{
                                  opacity: canEditRow ? 1 : 0.45,
                                  width: 38,
                                  height: 38,
                                  borderRadius: 10,
                                  alignItems: 'center',
                                  justifyContent: 'center',
                                  backgroundColor: colors.primarySoft,
                                }}
                              >
                                <Ionicons name="create-outline" size={16} color={colors.primary} />
                              </TouchableOpacity>

                              <TouchableOpacity
                                disabled={!canEditRow}
                                onPress={() => { void handleRemoveEmployee(employee); }}
                                data-testid={`employee-remove-button-${employee.user_id}`} testID={`employee-remove-button-${employee.user_id}`}
                                style={{
                                  opacity: canEditRow ? 1 : 0.45,
                                  width: 38,
                                  height: 38,
                                  borderRadius: 10,
                                  alignItems: 'center',
                                  justifyContent: 'center',
                                  backgroundColor: colors.errorSoft,
                                }}
                              >
                                <Ionicons name="trash-outline" size={16} color={colors.error} />
                              </TouchableOpacity>
                            </View>
                          </View>

                          {!!employee.employee_permissions?.length && (
                            <View style={{ marginTop: 10, flexDirection: 'row', flexWrap: 'wrap', gap: 6 }} data-testid={`employee-permissions-preview-${employee.user_id}`} testID={`employee-permissions-preview-${employee.user_id}`}>
                              {employee.employee_permissions.slice(0, 5).map((permission) => (
                                <Text
                                  key={permission}
                                  style={{ color: colors.successText, fontSize: 10, backgroundColor: colors.successSoft, paddingHorizontal: 8, paddingVertical: 4, borderRadius: 6 }}
                                >
                                  {permission}
                                </Text>
                              ))}
                            </View>
                          )}
                        </View>
                      );
                    })}
                  </View>
                )}
              </PanelCard>
            </View>

            <View style={{ flex: 1, minWidth: 0 }}>
              <PanelCard
                title={editorMode === 'create' ? 'Add Employee' : 'Edit Employee Access'}
                subtitle={editorMode === 'create' ? 'Assign role, permissions, and feature access' : 'Update role and access permissions quickly'}
                testId="employee-access-editor-panel"
              >
                {editorOpen ? (
                  <View style={{ gap: 12 }}>
                    {editorMode === 'create' ? (
                      <>
                        <Text style={{ color: T.textSec, fontSize: 11, fontWeight: '700', textTransform: 'uppercase' }}>{t("autofix.watchSweep1.search.user")}</Text>
                        <View style={{ flexDirection: 'row', alignItems: 'center', backgroundColor: T.inputBg, borderWidth: 1, borderColor: T.inputBorder, borderRadius: 10, paddingHorizontal: 10 }}>
                          <Ionicons name="search" size={14} color={colors.textMuted} />
                          <TextInput
                            value={candidateQuery}
                            onChangeText={(value) => { void searchCandidates(value); }}
                            placeholder="Type email..."
                            placeholderTextColor={colors.textMuted}
                            style={{ color: T.text, flex: 1, paddingVertical: 10, paddingHorizontal: 8, fontSize: 13 }}
                            data-testid="employee-editor-user-search-input" testID="employee-editor-user-search-input"
                          />
                          {candidateSearching && <ActivityIndicator size="small" color={colors.purpleText} />}
                        </View>

                        {candidateResults.length > 0 && (
                          <View style={{ borderWidth: 1, borderColor: T.inputBorder, borderRadius: 10, overflow: 'hidden' }} data-testid="employee-editor-search-results" testID="employee-editor-search-results">
                            {candidateResults.map((candidate) => (
                              <TouchableOpacity
                                key={candidate.user_id}
                                onPress={() => onSelectCandidate(candidate)}
                                data-testid={`employee-editor-candidate-${candidate.user_id}`} testID={`employee-editor-candidate-${candidate.user_id}`}
                                style={{
                                  borderBottomWidth: 1,
                                  borderBottomColor: T.border,
                                  paddingHorizontal: 12,
                                  paddingVertical: 10,
                                  backgroundColor: T.surfaceAlt,
                                }}
                              >
                                <Text style={{ color: T.text, fontWeight: '700', fontSize: 13 }}>{candidate.name || 'Unnamed User'}</Text>
                                <Text style={{ color: T.textSec, fontSize: 11, marginTop: 2 }}>{candidate.email}</Text>
                                {candidate.platform_role ? (
                                  <Text style={{ color: colors.warningText, fontSize: 10, marginTop: 3 }}>{t("autofix.watchSweep1.already.employee")}{candidate.platform_role})</Text>
                                ) : null}
                                {candidate.is_admin ? <Text style={{ color: colors.error, fontSize: 10, marginTop: 3 }}>{t("autofix.watchSweep1.admin.owner.account")}</Text> : null}
                              </TouchableOpacity>
                            ))}
                          </View>
                        )}
                      </>
                    ) : null}

                    {selectedCandidate ? (
                      <View style={{ borderWidth: 1, borderColor: T.border, backgroundColor: T.surface, borderRadius: 10, padding: 10 }} data-testid="employee-editor-selected-user" testID="employee-editor-selected-user">
                        <Text style={{ color: T.text, fontWeight: '700', fontSize: 13 }}>{selectedCandidate.name || 'Selected User'}</Text>
                        <Text style={{ color: T.textSec, marginTop: 2, fontSize: 11 }}>{selectedCandidate.email}</Text>
                      </View>
                    ) : null}

                    <Text style={{ color: T.textSec, fontSize: 11, fontWeight: '700', textTransform: 'uppercase' }}>{t("autofix.watchSweep1.platform.role")}</Text>
                    <View style={{ flexDirection: 'row', gap: 6, flexWrap: 'wrap' }}>
                      {allRoles.map((role) => {
                        const active = formRole === role;
                        const roleColor = getRoleColor(role);
                        return (
                          <TouchableOpacity
                            key={role}
                            onPress={() => {
                              setFormRole(role);
                              if (editorMode === 'create') applyRoleDefaults(role);
                            }}
                            data-testid={`employee-editor-role-${toTestId(role)}`} testID={`employee-editor-role-${toTestId(role)}`}
                            style={{
                              borderRadius: 8,
                              borderWidth: 1,
                              borderColor: active ? roleColor : T.border,
                              backgroundColor: active ? `${roleColor}22` : T.surfaceAlt,
                              paddingHorizontal: 10,
                              paddingVertical: 7,
                            }}
                          >
                            <Text style={{ color: active ? roleColor : T.textSec, fontSize: 11, fontWeight: '700' }}>{role}</Text>
                          </TouchableOpacity>
                        );
                      })}
                    </View>

                    <TouchableOpacity
                      onPress={() => applyRoleDefaults(formRole)}
                      data-testid="employee-editor-apply-role-defaults-button" testID="employee-editor-apply-role-defaults-button"
                      style={{ alignSelf: 'flex-start', paddingHorizontal: 10, paddingVertical: 7, backgroundColor: colors.primarySoft, borderRadius: 8, borderWidth: 1, borderColor: colors.primary }}
                    >
                      <Text style={{ color: colors.info, fontSize: 11, fontWeight: '700' }}>{t("autofix.watchSweep1.apply.role.defaults")}</Text>
                    </TouchableOpacity>

                    <View style={{ borderWidth: 1, borderColor: T.inputBorder, borderRadius: 10, padding: 10, backgroundColor: T.surfaceAlt }}>
                      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
                        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                          <Ionicons name="diamond" size={16} color={formPremium ? colors.warning : T.textMuted} />
                          <Text style={{ color: T.text, fontWeight: '700' }} data-testid="employee-editor-premium-label" testID="employee-editor-premium-label">{t("teamManagement.stats.premiumAccess")}</Text>
                        </View>
                        <TouchableOpacity
                          onPress={() => setFormPremium((v) => !v)}
                          data-testid="employee-editor-premium-toggle" testID="employee-editor-premium-toggle"
                          style={{ width: 48, height: 26, borderRadius: 13, backgroundColor: formPremium ? colors.warning : T.inputBorder, paddingHorizontal: 3, justifyContent: 'center' }}
                        >
                          <View style={{ width: 20, height: 20, borderRadius: 10, backgroundColor: colors.surface, alignSelf: formPremium ? 'flex-end' : 'flex-start' }} />
                        </TouchableOpacity>
                      </View>
                      <Text style={{ color: T.textSec, marginTop: 6, fontSize: 11 }}>{t("autofix.watchSweep1.premium.grants.full.product.access.while.keeping.audit")}</Text>
                    </View>

                    <Text style={{ color: T.textSec, fontSize: 11, fontWeight: '700', textTransform: 'uppercase' }}>{t("autofix.watchSweep1.permissions")}{formPermissions.length})
                    </Text>
                    <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6 }} data-testid="employee-editor-permissions-grid" testID="employee-editor-permissions-grid">
                      {allPermissions.map((permission) => {
                        const active = formPermissions.includes(permission);
                        return (
                          <TouchableOpacity
                            key={permission}
                            onPress={() => toggleFormPermission(permission)}
                            data-testid={`employee-editor-permission-${toTestId(permission)}`} testID={`employee-editor-permission-${toTestId(permission)}`}
                            style={{
                              borderRadius: 8,
                              borderWidth: 1,
                              borderColor: active ? colors.success : T.inputBorder,
                              backgroundColor: active ? colors.successSoft : T.surfaceAlt,
                              paddingHorizontal: 9,
                              paddingVertical: 6,
                            }}
                          >
                            <Text style={{ color: active ? colors.success : T.textSec, fontSize: 10, fontWeight: '700' }}>
                              {permission}
                            </Text>
                          </TouchableOpacity>
                        );
                      })}
                    </View>

                    {!formPremium && allFeatures.length > 0 ? (
                      <>
                        <Text style={{ color: T.textSec, fontSize: 11, fontWeight: '700', textTransform: 'uppercase' }}>{t("autofix.watchSweep1.feature.access")}{formFeatures.length})
                        </Text>
                        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6 }} data-testid="employee-editor-features-grid" testID="employee-editor-features-grid">
                          {allFeatures.map((feature) => {
                            const active = formFeatures.includes(feature);
                            return (
                              <TouchableOpacity
                                key={feature}
                                onPress={() => toggleFormFeature(feature)}
                                data-testid={`employee-editor-feature-${toTestId(feature)}`} testID={`employee-editor-feature-${toTestId(feature)}`}
                                style={{
                                  borderRadius: 8,
                                  borderWidth: 1,
                                  borderColor: active ? colors.info : T.inputBorder,
                                  backgroundColor: active ? colors.infoSoft : T.surfaceAlt,
                                  paddingHorizontal: 9,
                                  paddingVertical: 6,
                                }}
                              >
                                <Text style={{ color: active ? colors.info : T.textSec, fontSize: 10, fontWeight: '700' }}>
                                  {feature}
                                </Text>
                              </TouchableOpacity>
                            );
                          })}
                        </View>
                      </>
                    ) : null}

                    <View style={{ flexDirection: 'row', gap: 8, marginTop: 4 }}>
                      <TouchableOpacity
                        onPress={() => { void handleSubmitEditor(); }}
                        disabled={!canSubmitEditor}
                        data-testid="employee-editor-submit-button" testID="employee-editor-submit-button"
                        style={{
                          flex: 1,
                          borderRadius: 10,
                          backgroundColor: colors.primary,
                          alignItems: 'center',
                          justifyContent: 'center',
                          paddingVertical: 11,
                          opacity: canSubmitEditor ? 1 : 0.45,
                        }}
                      >
                        <Text style={{ color: colors.primaryText, fontWeight: '800', fontSize: 12 }}>
                          {savingEditor ? 'Saving...' : editorMode === 'create' ? 'Add Employee' : 'Save Changes'}
                        </Text>
                      </TouchableOpacity>

                      <TouchableOpacity
                        onPress={closeEditor}
                        data-testid="employee-editor-cancel-button" testID="employee-editor-cancel-button"
                        style={{
                          borderRadius: 10,
                          paddingVertical: 11,
                          paddingHorizontal: 14,
                          backgroundColor: T.surfaceAlt,
                          borderWidth: 1,
                          borderColor: T.inputBorder,
                        }}
                      >
                        <Text style={{ color: T.textSec, fontWeight: '700', fontSize: 12 }}>{t("admin.onboardingAB.actions.cancel")}</Text>
                      </TouchableOpacity>
                    </View>
                  </View>
                ) : (
                  <View style={{ paddingVertical: 24, alignItems: 'center' }} data-testid="employee-editor-closed-state" testID="employee-editor-closed-state">
                    <Ionicons name="settings-outline" size={34} color={colors.textMuted} />
                    <Text style={{ color: T.text, fontWeight: '700', fontSize: 16, marginTop: 10 }}>{t('teamManagement.editor.readyTitle')}</Text>
                    <Text style={{ color: T.textSec, marginTop: 5, textAlign: 'center', maxWidth: 320 }}>
                      {t('teamManagement.editor.readySubtitle')}
                    </Text>
                  </View>
                )}
              </PanelCard>

              <PanelCard title={t('teamManagement.panels.aiCenterTitle')} subtitle={t('teamManagement.panels.aiCenterSubtitle')} testId="employee-ai-security-panel">
                {loadingSnapshot ? (
                  <View style={{ alignItems: 'center', paddingVertical: 20 }} data-testid="employee-ai-security-loading" testID="employee-ai-security-loading">
                    <ActivityIndicator color={colors.primary} />
                  </View>
                ) : (
                  <>
                    <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginBottom: 10 }}>
                      <Badge label={`${snapshot.employeesAnalyzed} ${t('teamManagement.snapshot.employees')}`} color={colors.primary} testId="employee-ai-employees-count" />
                      <Badge label={`${snapshot.highRisk} ${t('teamManagement.snapshot.highRisk')}`} color={colors.error} testId="employee-ai-high-risk-count" />
                      <Badge label={`${snapshot.mediumRisk} ${t('teamManagement.snapshot.mediumRisk')}`} color={colors.warningText} testId="employee-ai-medium-risk-count" />
                      <Badge label={`${snapshot.pendingApprovals} ${t('teamManagement.snapshot.pendingApprovals')}`} color={colors.successText} testId="employee-ai-pending-approvals-count" />
                    </View>
                    <Text style={{ color: T.textSec, fontSize: 11, lineHeight: 18 }} data-testid="employee-ai-summary-text" testID="employee-ai-summary-text">
                      {snapshot.summary}
                    </Text>
                    <View style={{ flexDirection: 'row', gap: 8, marginTop: 12 }}>
                      <TouchableOpacity
                        onPress={() => { void loadSnapshot(true); }}
                        data-testid="employee-ai-refresh-button" testID="employee-ai-refresh-button"
                        style={{ flex: 1, borderRadius: 9, borderWidth: 1, borderColor: T.inputBorder, backgroundColor: T.surfaceAlt, alignItems: 'center', paddingVertical: 10 }}
                      >
                        <Text style={{ color: T.text, fontSize: 12, fontWeight: '700' }}>
                          {refreshingSnapshot ? t('teamManagement.snapshot.refreshing') : t('teamManagement.snapshot.refreshAi')}
                        </Text>
                      </TouchableOpacity>

                      <TouchableOpacity
                        onPress={() => { void dispatchRiskAlerts(); }}
                        data-testid="employee-ai-dispatch-alerts-button" testID="employee-ai-dispatch-alerts-button"
                        style={{ flex: 1, borderRadius: 9, borderWidth: 1, borderColor: colors.error, backgroundColor: colors.errorSoft, alignItems: 'center', paddingVertical: 10 }}
                      >
                        <Text style={{ color: colors.error, fontSize: 12, fontWeight: '700' }}>{t('teamManagement.snapshot.dispatchAlerts')}</Text>
                      </TouchableOpacity>
                    </View>
                  </>
                )}
              </PanelCard>

              <PanelCard title="Single Admin Guardrails" subtitle="Safety checks for owner-managed operations" testId="team-guardrails-panel">
                <View style={{ gap: 8 }}>
                  <GuardrailRow text="Owner admin account cannot be removed from employee controls." testId="guardrail-admin-protection" />
                  <GuardrailRow text="Role, permissions, and premium changes are audit logged." testId="guardrail-audit-logging" />
                  <GuardrailRow text="Policy Console remains linked for deeper RBAC governance." testId="guardrail-policy-console-link" />
                </View>
              </PanelCard>
            </View>
          </View>

          {canManageAccess ? (
            <PanelCard
              title={ghosts.length > 0 ? `⚠️ Ghost Employees Detected (${ghosts.length})` : 'Ghost Employee Audit'}
              subtitle={
                ghosts.length > 0
                  ? 'These users have `platform_role` access but no invitation record — legacy silent-grant from a prior bug. Remediate to revoke + send a fresh invitation.'
                  : 'Periodic scan for users with platform_role access but no invitation record. No ghosts detected right now.'
              }
              testId="ghost-audit-panel"
              headerAction={
                <TouchableOpacity
                  onPress={() => { void loadGhosts(); }}
                  disabled={ghostLoading}
                  style={{ flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 10, paddingVertical: 6, borderRadius: 8, borderWidth: 1, borderColor: T.border, backgroundColor: T.surface, opacity: ghostLoading ? 0.6 : 1 }}
                  data-testid="ghost-audit-refresh" testID="ghost-audit-refresh"
                >
                  {ghostLoading ? <ActivityIndicator size="small" color={T.textSec} /> : <Ionicons name="refresh" size={12} color={T.textSec} />}
                  <Text style={{ color: T.textSec, fontSize: 11, fontWeight: '700' }}>{t("abTesting.actions.refresh")}</Text>
                </TouchableOpacity>
              }
            >
              {ghostError ? (
                <Text style={{ color: T.error, fontSize: 12, marginBottom: 8 }} data-testid="ghost-audit-error" testID="ghost-audit-error">{ghostError}</Text>
              ) : null}
              {ghosts.length === 0 ? (
                <View
                  style={{ padding: 16, borderRadius: 8, backgroundColor: T.successSoft, borderWidth: 1, borderColor: T.successSoft, flexDirection: 'row', alignItems: 'center', gap: 10 }}
                  data-testid="ghost-audit-empty" testID="ghost-audit-empty"
                >
                  <Ionicons name="shield-checkmark" size={18} color={T.successText} />
                  <View style={{ flex: 1 }}>
                    <Text style={{ color: T.text, fontSize: 13, fontWeight: '700' }}>{t("autofix.watchSweep1.no.ghost.employees.detected")}</Text>
                    <Text style={{ color: T.textSec, fontSize: 11, marginTop: 2 }}>{t("autofix.watchSweep1.every.user.with.elevated.access.has.a.valid")}</Text>
                  </View>
                </View>
              ) : (
                <>
                  <View style={{ gap: 8, marginBottom: 12 }}>
                    {ghosts.slice(0, 25).map((g) => (
                      <View
                        key={g.user_id}
                        style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8, padding: 10, borderRadius: 8, backgroundColor: T.errorSoft, borderWidth: 1, borderColor: T.errorSoft }}
                        data-testid={`ghost-row-${g.user_id}`} testID={`ghost-row-${g.user_id}`}
                      >
                        <View style={{ flex: 1, minWidth: 0 }}>
                          <Text style={{ color: T.text, fontSize: 13, fontWeight: '700' }} numberOfLines={1}>{g.name || g.email}</Text>
                          <Text style={{ color: T.textSec, fontSize: 11 }} numberOfLines={1}>{g.email} · {g.platform_role}{g.premium_access ? ' · Premium' : ''}</Text>
                        </View>
                        <TouchableOpacity
                          onPress={() => convertGhosts([g.user_id])}
                          disabled={ghostConverting}
                          style={{ paddingHorizontal: 12, paddingVertical: 7, borderRadius: 6, backgroundColor: T.errorText, opacity: ghostConverting ? 0.55 : 1 }}
                          data-testid={`ghost-remediate-${g.user_id}`} testID={`ghost-remediate-${g.user_id}`}
                        >
                          <Text style={{ color: T.primaryText, fontSize: 11, fontWeight: '800' }}>{t("autofix.watchSweep1.remediate")}</Text>
                        </TouchableOpacity>
                      </View>
                    ))}
                    {ghosts.length > 25 ? (
                      <Text style={{ color: T.textMuted, fontSize: 11, textAlign: 'center' }}>+ {ghosts.length - 25}{t("autofix.watchSweep1.more.remediate.all.below")}</Text>
                    ) : null}
                  </View>
                  <TouchableOpacity
                    onPress={() => convertGhosts()}
                    disabled={ghostConverting || ghostLoading}
                    style={{ alignSelf: 'flex-start', paddingHorizontal: 16, paddingVertical: 9, borderRadius: 8, backgroundColor: T.error, opacity: (ghostConverting || ghostLoading) ? 0.6 : 1, flexDirection: 'row', alignItems: 'center', gap: 6 }}
                    data-testid="ghost-remediate-all-button" testID="ghost-remediate-all-button"
                    aria-label="Remediate all ghost employees"
                  >
                    {ghostConverting ? <ActivityIndicator size="small" color={T.primaryText} /> : <Ionicons name="shield-checkmark" size={14} color={T.primaryText} />}
                    <Text style={{ color: T.primaryText, fontSize: 12, fontWeight: '800' }} data-testid="ghost-audit-convert" testID="ghost-audit-convert">{ghostConverting ? 'Remediating…' : `Remediate all ${ghosts.length} ghost(s)`}</Text>
                  </TouchableOpacity>
                </>
              )}
            </PanelCard>
          ) : null}

          {canManageAccess ? (
            <PanelCard
              title={`Pending Invitations (${pendingInvites.length})`}
              subtitle="Outstanding email invitations waiting for the recipient to accept."
              testId="employee-pending-invites-panel"
            >
              <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8, alignItems: 'center', marginBottom: 12 }} data-testid="pending-invites-filter-bar" testID="pending-invites-filter-bar">
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 10, paddingVertical: 6, borderRadius: 8, borderWidth: 1, borderColor: T.border, backgroundColor: T.bg, minWidth: 200, flex: 1 }}>
                  <Ionicons name="search" size={12} color={T.textMuted} />
                  <TextInput
                    value={inviteSearch}
                    onChangeText={setInviteSearch}
                    placeholder="Search email or inviter…"
                    placeholderTextColor={T.textMuted}
                    data-testid="pending-invites-search-input" testID="pending-invites-search-input"
                    style={{ flex: 1, fontSize: 12, color: T.text, ...(Platform.OS === 'web' ? { outlineStyle: 'none' } as any : {}) }}
                  />
                  {inviteSearch ? (
                    <TouchableOpacity onPress={() => setInviteSearch('')} data-testid="pending-invites-search-clear" testID="pending-invites-search-clear">
                      <Ionicons name="close-circle" size={13} color={T.textMuted} />
                    </TouchableOpacity>
                  ) : null}
                </View>

                <View style={{ flexDirection: 'row', gap: 4 }}>
                  {(['', ...rolesConfig.roles].slice(0, 6)).map((role) => {
                    const active = inviteRoleFilter === role;
                    const label = role || 'All roles';
                    return (
                      <TouchableOpacity
                        key={`invite-role-${role || 'all'}`}
                        onPress={() => setInviteRoleFilter(active ? '' : role)}
                        data-testid={`pending-invites-role-${toTestId(role || 'all')}`} testID={`pending-invites-role-${toTestId(role || 'all')}`}
                        style={{
                          borderRadius: 999, paddingHorizontal: 10, paddingVertical: 5,
                          borderWidth: 1, borderColor: active ? T.primary : T.border,
                          backgroundColor: active ? T.primary : T.surface,
                        }}
                      >
                        <Text style={{ color: active ? T.primaryText : T.textSec, fontSize: 10, fontWeight: '700', letterSpacing: 0.2 }}>{label}</Text>
                      </TouchableOpacity>
                    );
                  })}
                </View>

                <View style={{ flexDirection: 'row', gap: 4 }}>
                  {([
                    { key: '', label: 'Any' },
                    { key: '24h', label: '24h' },
                    { key: '72h', label: '72h' },
                    { key: '7d', label: '7d' },
                    { key: '30d', label: '30d' },
                  ] as const).map((opt) => {
                    const active = inviteWindow === opt.key;
                    return (
                      <TouchableOpacity
                        key={`invite-window-${opt.key || 'any'}`}
                        onPress={() => setInviteWindow(active ? '' : opt.key)}
                        data-testid={`pending-invites-window-${opt.key || 'any'}`} testID={`pending-invites-window-${opt.key || 'any'}`}
                        style={{
                          borderRadius: 999, paddingHorizontal: 10, paddingVertical: 5,
                          borderWidth: 1, borderColor: active ? T.primary : T.border,
                          backgroundColor: active ? T.primary : T.surface,
                        }}
                      >
                        <Text style={{ color: active ? T.primaryText : T.textSec, fontSize: 10, fontWeight: '700' }}>{opt.label}</Text>
                      </TouchableOpacity>
                    );
                  })}
                </View>
              </View>
              {invitesLoading ? (
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, paddingVertical: 8 }} data-testid="pending-invites-loading" testID="pending-invites-loading">
                  <ActivityIndicator size="small" color={T.primary} />
                  <Text style={{ color: T.textMuted, fontSize: 12 }}>{t("autofix.watchSweep1.loading.invitations")}</Text>
                </View>
              ) : invitesError ? (
                <Text style={{ color: T.error, fontSize: 12 }} data-testid="pending-invites-error" testID="pending-invites-error">{invitesError}</Text>
              ) : pendingInvites.length === 0 ? (
                <View style={{ alignItems: 'center', paddingVertical: 22 }} data-testid="pending-invites-empty" testID="pending-invites-empty">
                  <Ionicons name="mail-outline" size={28} color={T.textMuted} />
                  <Text style={{ color: T.textSec, fontSize: 12, marginTop: 8 }}>
                    {inviteSearch || inviteRoleFilter || inviteWindow ? 'No invitations match your filters.' : 'No pending invitations.'}
                  </Text>
                </View>
              ) : (
                <View style={{ gap: 8 }}>
                  {pendingInvites.map((inv) => {
                    const expiresIn = (() => {
                      try {
                        const diff = new Date(inv.expires_at).getTime() - Date.now();
                        if (diff <= 0) return 'expired';
                        const h = Math.floor(diff / 3600000);
                        if (h >= 24) return `in ${Math.floor(h / 24)}d ${h % 24}h`;
                        return `in ${Math.max(1, h)}h`;
                      } catch { return ''; }
                    })();
                    const busy = busyInvitationId === inv.invitation_id;
                    return (
                      <View
                        key={inv.invitation_id}
                        data-testid={`pending-invite-row-${inv.invitation_id}`} testID={`pending-invite-row-${inv.invitation_id}`}
                        style={{
                          borderRadius: 10, borderWidth: 1, borderColor: T.border, backgroundColor: T.bg,
                          padding: 11, flexDirection: 'row', alignItems: 'center', gap: 10, flexWrap: 'wrap',
                        }}
                      >
                        <View style={{ width: 34, height: 34, borderRadius: 9, backgroundColor: T.warningSoft, alignItems: 'center', justifyContent: 'center' }}>
                          <Ionicons name="mail-outline" size={15} color={T.warningText} />
                        </View>
                        <View style={{ flex: 1, minWidth: 180 }}>
                          <Text style={{ color: T.text, fontSize: 13, fontWeight: '700' }} numberOfLines={1} data-testid={`pending-invite-email-${inv.invitation_id}`} testID={`pending-invite-email-${inv.invitation_id}`}>
                            {inv.email}
                          </Text>
                          <Text style={{ color: T.textMuted, fontSize: 11, marginTop: 2 }} numberOfLines={1}>
                            <Text style={{ color: T.textSec, fontWeight: '700' }}>{inv.platform_role}</Text>
                            {t("autofix.watchSweep1.invited.by")}{inv.invited_by_email}
                          </Text>
                        </View>
                        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: T.warningSoft, borderRadius: 999, paddingHorizontal: 10, paddingVertical: 4 }}>
                          <Ionicons name="time-outline" size={11} color={T.warningText} />
                          <Text style={{ color: T.warningText, fontSize: 11, fontWeight: '700' }} data-testid={`pending-invite-expires-${inv.invitation_id}`} testID={`pending-invite-expires-${inv.invitation_id}`}>{t("autofix.watchSweep1.expires")}{expiresIn}
                          </Text>
                        </View>
                        {inv.delivery_status ? (() => {
                          const s = inv.delivery_status;
                          const meta: Record<string, { color: string; bg: string; icon: string; label: string }> = {
                            sent:       { color: T.textSec, bg: T.surface,      icon: 'paper-plane-outline',   label: 'Sent' },
                            delivered:  { color: T.successText, bg: T.successSoft,  icon: 'checkmark-done',        label: 'Delivered' },
                            opened:     { color: T.primary, bg: T.primarySoft,  icon: 'mail-open-outline',     label: 'Opened' },
                            clicked:    { color: T.primary, bg: T.primarySoft,  icon: 'link',                  label: 'Clicked' },
                            bounced:    { color: T.error,   bg: T.errorSoft,    icon: 'close-circle',          label: 'Bounced' },
                            complained: { color: T.error,   bg: T.errorSoft,    icon: 'warning',               label: 'Complaint' },
                            delayed:    { color: T.warningText, bg: T.warningSoft,  icon: 'hourglass-outline',     label: 'Delayed' },
                          };
                          const m = meta[s] || { color: T.textMuted, bg: T.surface, icon: 'ellipse-outline', label: s };
                          return (
                            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: m.bg, borderRadius: 999, paddingHorizontal: 10, paddingVertical: 4 }}
                              data-testid={`pending-invite-delivery-${inv.invitation_id}`} testID={`pending-invite-delivery-${inv.invitation_id}`}
                            >
                              <Ionicons name={m.icon as any} size={11} color={m.color} />
                              <Text style={{ color: m.color, fontSize: 11, fontWeight: '700' }}>{m.label}</Text>
                            </View>
                          );
                        })() : null}
                        <TouchableOpacity
                          onPress={() => { void copyInvitationLink(inv.invitation_id); }}
                          disabled={busy}
                          data-testid={`pending-invite-copy-${inv.invitation_id}`} testID={`pending-invite-copy-${inv.invitation_id}`}
                          style={{
                            flexDirection: 'row', alignItems: 'center', gap: 6,
                            borderRadius: 8, borderWidth: 1, borderColor: T.border, backgroundColor: T.surface,
                            paddingHorizontal: 10, paddingVertical: 7, opacity: busy ? 0.55 : 1,
                          }}
                        >
                          <Ionicons name="link-outline" size={12} color={T.textSec} />
                          <Text style={{ color: T.textSec, fontWeight: '700', fontSize: 11 }}>{t("autofix.watchSweep1.copy.link")}</Text>
                        </TouchableOpacity>
                        <TouchableOpacity
                          onPress={() => { void openInvitationQR(inv.invitation_id, inv.email, inv.platform_role); }}
                          disabled={busy}
                          data-testid={`pending-invite-qr-${inv.invitation_id}`} testID={`pending-invite-qr-${inv.invitation_id}`}
                          style={{
                            flexDirection: 'row', alignItems: 'center', gap: 6,
                            borderRadius: 8, borderWidth: 1, borderColor: T.border, backgroundColor: T.surface,
                            paddingHorizontal: 10, paddingVertical: 7, opacity: busy ? 0.55 : 1,
                          }}
                        >
                          <Ionicons name="qr-code-outline" size={12} color={T.textSec} />
                          <Text style={{ color: T.textSec, fontWeight: '700', fontSize: 11 }}>QR</Text>
                        </TouchableOpacity>
                        <TouchableOpacity
                          onPress={() => { void resendInvitation(inv.invitation_id); }}
                          disabled={busy}
                          data-testid={`pending-invite-resend-${inv.invitation_id}`} testID={`pending-invite-resend-${inv.invitation_id}`}
                          style={{
                            flexDirection: 'row', alignItems: 'center', gap: 6,
                            borderRadius: 8, borderWidth: 1, borderColor: T.border, backgroundColor: T.surface,
                            paddingHorizontal: 10, paddingVertical: 7, opacity: busy ? 0.55 : 1,
                          }}
                        >
                          <Ionicons name="refresh" size={12} color={T.textSec} />
                          <Text style={{ color: T.textSec, fontWeight: '700', fontSize: 11 }}>{t("autofix.watchSweep1.resend")}</Text>
                        </TouchableOpacity>
                        <TouchableOpacity
                          onPress={() => { void revokeInvitation(inv.invitation_id); }}
                          disabled={busy}
                          data-testid={`pending-invite-revoke-${inv.invitation_id}`} testID={`pending-invite-revoke-${inv.invitation_id}`}
                          style={{
                            flexDirection: 'row', alignItems: 'center', gap: 6,
                            borderRadius: 8, borderWidth: 1, borderColor: T.error, backgroundColor: T.errorSoft,
                            paddingHorizontal: 10, paddingVertical: 7, opacity: busy ? 0.55 : 1,
                          }}
                        >
                          <Ionicons name="close" size={12} color={T.error} />
                          <Text style={{ color: T.error, fontWeight: '700', fontSize: 11 }}>{t("certificateGallery.actions.revoke")}</Text>
                        </TouchableOpacity>
                      </View>
                    );
                  })}
                </View>
              )}
            </PanelCard>
          ) : null}

          <PanelCard title="Activity Log" subtitle="Track add, edit, remove, and access actions" testId="employee-audit-log-panel">
            {canViewAuditLogs ? (
              <>
                <View style={{ flexDirection: isMedium ? 'row' : 'column', gap: 10, marginBottom: 12 }}>
                  <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ flexGrow: 0 }}>
                    <View style={{ flexDirection: 'row', gap: 6 }}>
                      <PillButton
                        label="All"
                        active={!auditFilter}
                        onPress={() => {
                          setAuditFilter('');
                          void loadAuditLog(1, '');
                        }}
                        testId="employee-audit-filter-all"
                      />
                      {Object.keys(AUDIT_ACTION_CONFIG).map((action) => (
                        <PillButton
                          key={action}
                          label={AUDIT_ACTION_CONFIG[action].label}
                          active={auditFilter === action}
                          onPress={() => {
                            setAuditFilter(action);
                            void loadAuditLog(1, action);
                          }}
                          testId={`employee-audit-filter-${toTestId(action)}`}
                        />
                      ))}
                    </View>
                  </ScrollView>

                  <TouchableOpacity
                    onPress={() => { void exportAuditCsv(); }}
                    data-testid="employee-audit-export-csv-button" testID="employee-audit-export-csv-button"
                    style={{ alignSelf: 'flex-start', borderRadius: 8, borderWidth: 1, borderColor: colors.success, backgroundColor: colors.successSoft, paddingHorizontal: 12, paddingVertical: 9 }}
                  >
                    <Text style={{ color: colors.successText, fontWeight: '700', fontSize: 12 }}>{t("admin.subscriptionDashboard.paymentE2E.actions.exportCsv")}</Text>
                  </TouchableOpacity>
                </View>

                {loadingAudit ? (
                  <View style={{ alignItems: 'center', paddingVertical: 24 }} data-testid="employee-audit-loading" testID="employee-audit-loading">
                    <ActivityIndicator color={colors.purpleText} />
                  </View>
                ) : auditLogs.length ? (
                  <View style={{ gap: 8 }}>
                    {auditLogs.map((log, index) => {
                      const config = AUDIT_ACTION_CONFIG[log.action] || { label: log.action, color: colors.textMuted, icon: 'ellipse' };
                      return (
                        <View key={log.log_id || `${log.action}-${index}`} style={{ borderWidth: 1, borderColor: T.border, borderRadius: 10, backgroundColor: T.surface, padding: 11 }} data-testid={`employee-audit-entry-${index}`} testID={`employee-audit-entry-${index}`}>
                          <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
                            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                              <View style={{ width: 28, height: 28, borderRadius: 8, backgroundColor: `${config.color}22`, alignItems: 'center', justifyContent: 'center' }}>
                                <Ionicons name={config.icon as any} size={13} color={config.color} />
                              </View>
                              <Text style={{ color: config.color, fontWeight: '700', fontSize: 12 }}>{config.label}</Text>
                            </View>
                            <Text style={{ color: T.textMuted, fontSize: 10 }}>{timeAgo(log.timestamp)}</Text>
                          </View>
                          <Text style={{ color: T.text, marginTop: 6, fontSize: 12 }}>
                            <Text style={{ fontWeight: '700' }}>{log.admin_email}</Text>
                            <Text style={{ color: T.textMuted }}> → </Text>
                            <Text style={{ fontWeight: '600' }}>{log.target_email}</Text>
                          </Text>
                          <Text style={{ color: T.textSec, marginTop: 3, fontSize: 11 }}>{formatAuditDetail(log.action, log.details || {}) || 'No additional details'}</Text>
                        </View>
                      );
                    })}

                    {auditPages > 1 && (
                      <View style={{ flexDirection: 'row', justifyContent: 'center', alignItems: 'center', gap: 10, marginTop: 6 }}>
                        <TouchableOpacity
                          disabled={auditPage <= 1}
                          onPress={() => void loadAuditLog(auditPage - 1, auditFilter)}
                          data-testid="employee-audit-pagination-prev" testID="employee-audit-pagination-prev"
                          style={{ opacity: auditPage <= 1 ? 0.35 : 1, width: 32, height: 32, borderRadius: 8, borderWidth: 1, borderColor: T.inputBorder, alignItems: 'center', justifyContent: 'center' }}
                        >
                          <Ionicons name="chevron-back" size={14} color={colors.textSec} />
                        </TouchableOpacity>
                        <Text style={{ color: T.textSec, fontSize: 11 }} data-testid="employee-audit-pagination-text" testID="employee-audit-pagination-text">{t("autofix.watchSweep1.page")}{auditPage} of {auditPages}
                        </Text>
                        <TouchableOpacity
                          disabled={auditPage >= auditPages}
                          onPress={() => void loadAuditLog(auditPage + 1, auditFilter)}
                          data-testid="employee-audit-pagination-next" testID="employee-audit-pagination-next"
                          style={{ opacity: auditPage >= auditPages ? 0.35 : 1, width: 32, height: 32, borderRadius: 8, borderWidth: 1, borderColor: T.inputBorder, alignItems: 'center', justifyContent: 'center' }}
                        >
                          <Ionicons name="chevron-forward" size={14} color={colors.textSec} />
                        </TouchableOpacity>
                      </View>
                    )}
                  </View>
                ) : (
                  <View style={{ alignItems: 'center', paddingVertical: 24 }} data-testid="employee-audit-empty-state" testID="employee-audit-empty-state">
                    <Text style={{ color: T.textSec }}>{t("autofix.watchSweep1.no.activity.log.entries.found")}</Text>
                  </View>
                )}

                <Text style={{ color: T.textSec, marginTop: 10, fontSize: 11 }} data-testid="employee-audit-total-count" testID="employee-audit-total-count">
                  {auditTotal}{t("autofix.watchSweep1.total.log.entries")}</Text>
              </>
            ) : (
              <Text style={{ color: T.textSec }} data-testid="employee-audit-permission-note" testID="employee-audit-permission-note">{t("autofix.watchSweep1.audit.log.visibility.requires.employee.view.audit.logs")}</Text>
            )}
          </PanelCard>
        </ScrollView>
      </View>

      {confirmModal.visible && confirmModal.employee && (
        <View
          style={{
            ...(Platform.OS === 'web' ? { position: 'fixed' as any } : { position: 'absolute' }),
            top: 0, left: 0, right: 0, bottom: 0,
            backgroundColor: colors.overlay,
            justifyContent: 'center', alignItems: 'center',
            zIndex: 9999, padding: 20,
          }}
          data-testid="employee-remove-confirm-modal" testID="employee-remove-confirm-modal"
        >
          <View style={{
            backgroundColor: T.inputBg, borderRadius: 16, padding: 24,
            maxWidth: 420, width: '100%', borderWidth: 1, borderColor: colors.errorSoft,
          }}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 16 }}>
              <View style={{ width: 40, height: 40, borderRadius: 20, backgroundColor: colors.errorSoft, justifyContent: 'center', alignItems: 'center' }}>
                <Ionicons name="person-remove" size={20} color={colors.error} />
              </View>
              <Text style={{ color: colors.text, fontSize: 17, fontWeight: '800', flex: 1 }}>{t("autofix.watchSweep1.remove.employee")}</Text>
            </View>
            <Text style={{ color: colors.textMuted, fontSize: 14, lineHeight: 22, marginBottom: 20 }}>{t("securityDashboard.knownDevices.actions.remove")}<Text style={{ color: colors.text, fontWeight: '700' }}>{confirmModal.employee.email}</Text>{t("autofix.watchSweep1.from.platform.employees.this.will.revoke.all.access")}</Text>
            <View style={{ flexDirection: 'row', gap: 10 }}>
              <TouchableOpacity
                onPress={() => setConfirmModal({ visible: false, employee: null })}
                style={{ flex: 1, paddingVertical: 12, borderRadius: 10, backgroundColor: T.surfaceAlt, borderWidth: 1, borderColor: T.inputBorder, alignItems: 'center' }}
                data-testid="employee-remove-cancel-btn" testID="employee-remove-cancel-btn"
              >
                <Text style={{ color: T.textSec, fontWeight: '700', fontSize: 13 }}>{t("admin.onboardingAB.actions.cancel")}</Text>
              </TouchableOpacity>
              <TouchableOpacity
                onPress={() => { void executeRemoveEmployee(); }}
                style={{ flex: 1, paddingVertical: 12, borderRadius: 10, backgroundColor: colors.error, alignItems: 'center' }}
                data-testid="employee-remove-confirm-btn" testID="employee-remove-confirm-btn"
              >
                <Text style={{ color: colors.primaryText, fontWeight: '700', fontSize: 13 }}>{t("securityDashboard.knownDevices.actions.remove")}</Text>
              </TouchableOpacity>
            </View>
          </View>
        </View>
      )}
    </AppShell>
    </AdminRouteGate>
  );
}

function PanelCard({
  title,
  subtitle,
  children,
  testId,
  headerAction,
}: {
  title: string;
  subtitle: string;
  children: React.ReactNode;
  testId: string;
  headerAction?: React.ReactNode;
}) {
  const { colors, darkMode } = useTheme();
  return (
    <View
      style={{
        borderRadius: 14,
        borderWidth: 1,
        borderColor: colors.border,
        backgroundColor: colors.surface,
        padding: 18,
        marginBottom: 16,
        ...(Platform.OS === 'web' ? { boxShadow: darkMode ? '0 2px 12px rgba(0,0,0,0.32)' : '0 1px 2px rgba(15,23,42,0.04), 0 6px 20px rgba(15,23,42,0.05)' } as any : {}),
      }}
      data-testid={testId} testID={testId}
    >
      <View style={{ flexDirection: 'row', alignItems: 'flex-start', justifyContent: 'space-between', gap: 12 }}>
        <View style={{ flex: 1, minWidth: 0 }}>
          <Text style={{ color: colors.text, fontSize: 16, fontWeight: '700', letterSpacing: -0.3 }}>{title}</Text>
          <Text style={{ color: colors.textMuted, marginTop: 3, fontSize: 12 }}>{subtitle}</Text>
        </View>
        {headerAction ? <View>{headerAction}</View> : null}
      </View>
      <View style={{ marginTop: 14 }}>{children}</View>
    </View>
  );
}

function MetricCard({
  label,
  value,
  icon,
  color,
  testId,
}: {
  label: string;
  value: number;
  icon: string;
  color: string;
  testId: string;
}) {
  const { colors, darkMode } = useTheme();
  return (
    <View style={{
      minWidth: 160, flex: 1, borderRadius: 12, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface, padding: 14,
      ...(Platform.OS === 'web' ? { boxShadow: darkMode ? '0 2px 10px rgba(0,0,0,0.28)' : '0 1px 2px rgba(15,23,42,0.04), 0 4px 14px rgba(15,23,42,0.04)' } as any : {}),
    }} data-testid={testId} testID={testId}>
      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
        <Text style={{ color: colors.textMuted, fontSize: 10, fontWeight: '700', textTransform: 'uppercase', letterSpacing: 1 }}>
          {label}
        </Text>
        <View style={{ width: 32, height: 32, borderRadius: 8, backgroundColor: `${color}15`, alignItems: 'center', justifyContent: 'center' }}>
          <Ionicons name={icon as any} size={16} color={color} />
        </View>
      </View>
      <Text style={{ color: colors.text, fontSize: 28, fontWeight: '800', marginTop: 10, letterSpacing: -1 }} data-testid={`${testId}-value`} testID={`${testId}-value`}>
        {value}
      </Text>
    </View>
  );
}

function PillButton({
  label,
  active,
  onPress,
  testId,
}: {
  label: string;
  active: boolean;
  onPress: () => void;
  testId: string;
}) {
  const { colors } = useTheme();
  return (
    <TouchableOpacity
      onPress={onPress}
      data-testid={testId} testID={testId}
      style={{
        borderRadius: 999,
        borderWidth: 1,
        borderColor: active ? colors.primary : colors.border,
        backgroundColor: active ? colors.primary : colors.surface,
        paddingHorizontal: 12,
        paddingVertical: 6,
      }}
    >
      <Text style={{ color: active ? colors.primaryText : colors.textSec, fontSize: 11, fontWeight: '700', letterSpacing: 0.2 }}>{label}</Text>
    </TouchableOpacity>
  );
}

function Badge({ label, color, testId }: { label: string; color: string; testId: string }) {
  return (
    <View style={{ borderRadius: 6, paddingHorizontal: 8, paddingVertical: 4, backgroundColor: `${color}15`, borderWidth: 1, borderColor: `${color}30` }} data-testid={testId} testID={testId}>
      <Text style={{ color, fontWeight: '700', fontSize: 11 }}>{label}</Text>
    </View>
  );
}

function GuardrailRow({ text, testId }: { text: string; testId: string }) {
  const { colors } = useTheme();
  return (
    <View style={{ flexDirection: 'row', alignItems: 'flex-start', gap: 10, paddingVertical: 6 }} data-testid={testId} testID={testId}>
      <Ionicons name="checkmark-circle" size={16} color={colors.successText} style={{ marginTop: 1 }} />
      <Text style={{ color: colors.textSec, lineHeight: 20, fontSize: 13, flex: 1 }}>{text}</Text>
    </View>
  );
}

function NotificationBanner({
  type,
  message,
  onDismiss,
  testId,
}: {
  type: 'error' | 'success';
  message: string;
  onDismiss: () => void;
  testId: string;
}) {
  const { colors } = useTheme();
  const color = type === 'error' ? colors.error : colors.success;
  const softBg = type === 'error' ? colors.errorSoft : colors.successSoft;
  const icon = type === 'error' ? 'alert-circle' : 'checkmark-circle';

  return (
    <View style={{
      borderRadius: 10, borderWidth: 1, borderColor: `${color}40`,
      backgroundColor: softBg,
      padding: 12, marginBottom: 14, flexDirection: 'row', alignItems: 'center', gap: 10,
    }} data-testid={testId} testID={testId}>
      <Ionicons name={icon as any} size={18} color={color} />
      <Text style={{ color, flex: 1, fontSize: 13, fontWeight: '600' }}>{message}</Text>
      <TouchableOpacity onPress={onDismiss} data-testid={`${testId}-dismiss`} testID={`${testId}-dismiss`}>
        <Ionicons name="close" size={16} color={color} />
      </TouchableOpacity>
    </View>
  );
}

function formatAuditDetail(action: string, details: Record<string, any>) {
  if (!details || !Object.keys(details).length) return '';
  if (action === 'employee_added') {
    return `Role: ${details.role || 'unknown'}${details.premium_access ? ' · Premium enabled' : ''}`;
  }
  if (action === 'employee_removed') {
    return `Removed role: ${details.role || 'unknown'}`;
  }
  if (action === 'role_changed' && details.role) {
    return `${details.role.from || 'unknown'} → ${details.role.to || 'unknown'}`;
  }
  if (action === 'access_updated') {
    const added = details.features_added?.length ? `+${details.features_added.length} features` : '';
    const removed = details.features_removed?.length ? `-${details.features_removed.length} features` : '';
    return [added, removed].filter(Boolean).join(' · ');
  }
  if (typeof details === 'object') {
    return Object.keys(details).slice(0, 3).map((k) => `${k}: ${String(details[k])}`).join(' · ');
  }
  return String(details);
}

function timeAgo(isoString: string) {
  const value = new Date(isoString).getTime();
  if (Number.isNaN(value)) return 'unknown';
  const diff = Date.now() - value;
  const minutes = Math.floor(diff / 60000);
  if (minutes < 1) return 'just now';
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 7) return `${days}d ago`;
  return new Date(isoString).toLocaleDateString();
}

function toTestId(value: string) {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '');
}
