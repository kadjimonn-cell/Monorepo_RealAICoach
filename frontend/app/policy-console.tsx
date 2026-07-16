import React, { useCallback, useEffect, useMemo, useState } from 'react';
// @gls-exempt — intentional fixed-width UI element (sidebar/chat/label/toast)
import { View, Text, ScrollView, TouchableOpacity, TextInput, ActivityIndicator } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import AppShell from '../src/components/AppShell';
import api from '../src/services/api';
import { useTheme } from '../src/context/ThemeContext';
import { useAccessControl } from '../src/context/AccessControlContext';
import { useTranslation } from '../src/hooks/useTranslation';
import { handleAppRecoverableError } from '../src/utils/appRecoverableError';
import { AdminRouteGate } from '../src/components/auth/AdminRouteGate';

type RoleTemplate = {
  role: string;
  permissions: string[];
  feature_access: string[];
  notes?: string;
};

type PendingTransition = {
  user_id: string;
  email: string;
  subscription_plan: string;
  subscription_status: string;
  pending_subscription_transition?: {
    action?: string;
    target_plan?: string;
    effective_at?: string;
  };
};

export default function PolicyConsolePage() {
  const { colors } = useTheme();
  const { t } = useTranslation();
  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };
  const { hasPermission } = useAccessControl();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [templates, setTemplates] = useState<RoleTemplate[]>([]);
  const [permissionCatalog, setPermissionCatalog] = useState<string[]>([]);
  const [selectedRole, setSelectedRole] = useState<RoleTemplate | null>(null);
  const [pendingTransitions, setPendingTransitions] = useState<PendingTransition[]>([]);
  const [observability, setObservability] = useState<any>(null);
  const [query, setQuery] = useState('');
  const [searchResults, setSearchResults] = useState<any[]>([]);
  const [selectedUserId, setSelectedUserId] = useState('');
  const [assignmentPerms, setAssignmentPerms] = useState<string[]>([]);
  const [success, setSuccess] = useState('');
  const canManageAccess = hasPermission('employee.manage_access');
  const canManageSubscriptions = hasPermission('employee.manage_subscriptions');
  const canViewAnalytics = hasPermission('employee.view_analytics');

  const loadConsole = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const tasks = [api.get('/admin/access-control/policy-console/bootstrap')];
      if (canManageSubscriptions) tasks.push(api.get('/admin/access-control/policy-console/pending-transitions'));
      if (canViewAnalytics) tasks.push(api.get('/admin/access-control/observability'));

      const [bootstrap, transitions, metrics] = await Promise.all(tasks);
      setTemplates(bootstrap.data?.role_templates || []);
      setPermissionCatalog(bootstrap.data?.permission_catalog || []);
      if (!selectedRole && bootstrap.data?.role_templates?.length) {
        setSelectedRole(bootstrap.data.role_templates[0]);
      }

      if (canManageSubscriptions) {
        setPendingTransitions((transitions as any)?.data?.records || []);
      }
      if (canViewAnalytics) {
        setObservability((tasks.length === 2 && !canManageSubscriptions ? transitions : metrics as any)?.data || null);
      }
    } catch (e: any) {
      const message = e?.response?.data?.detail || 'Failed to load policy console';
      handleAppRecoverableError({
        scope: 'policy-console.load',
        error: e,
        message,
        setError,
        onRetry: () => { void loadConsole(); },
      
        notifyMode: 'dialog',
        userInitiated: true,
      });
      setError(message);
    } finally {
      setLoading(false);
    }
  }, [canManageSubscriptions, canViewAnalytics, selectedRole]);

  useEffect(() => {
    loadConsole();
  }, [loadConsole]);

  const roleList = useMemo(() => templates.map((t) => t.role), [templates]);

  const toggleRolePermission = (permission: string) => {
    if (!selectedRole) return;
    const exists = selectedRole.permissions.includes(permission);
    const next = exists ? selectedRole.permissions.filter((p) => p !== permission) : [...selectedRole.permissions, permission];
    setSelectedRole({ ...selectedRole, permissions: next });
  };

  const saveRoleTemplate = async () => {
    if (!selectedRole) return;
    setSuccess('');
    setError('');
    try {
      await api.put(`/admin/access-control/policy-console/role-template/${encodeURIComponent(selectedRole.role)}`, {
        permissions: selectedRole.permissions,
        feature_access: selectedRole.feature_access,
        notes: selectedRole.notes || '',
      });
      setSuccess(`Saved template for ${selectedRole.role}`);
      await loadConsole();
    } catch (e: any) {
      const message = e?.response?.data?.detail || 'Failed to save role template';
      handleAppRecoverableError({
        scope: 'policy-console.save-role-template',
        error: e,
        message,
        setError,
        onRetry: () => { void saveRoleTemplate(); },
      
        notifyMode: 'dialog',
        userInitiated: true,
      });
      setError(message);
    }
  };

  const searchUsers = async () => {
    if (!query.trim()) return;
    try {
      const res = await api.get(`/admin/employees/search?q=${encodeURIComponent(query.trim())}`);
      setSearchResults(res.data?.users || res.data?.results || []);
    } catch (error) {
      handleAppRecoverableError({
        scope: 'policy-console.search-users',
        error,
        message: 'User search failed. Please retry.',
        setError,
        onRetry: () => { void searchUsers(); },
      
        notifyMode: 'dialog',
        userInitiated: true,
      });
      setSearchResults([]);
    }
  };

  const assignPermissions = async () => {
    if (!selectedUserId) return;
    setSuccess('');
    setError('');
    try {
      await api.post('/admin/access-control/employee-access', {
        user_id: selectedUserId,
        employee_permissions: assignmentPerms,
        reason: 'policy_console_assignment',
      });
      setSuccess('Employee permissions updated successfully');
      setSelectedUserId('');
      setAssignmentPerms([]);
    } catch (e: any) {
      const message = e?.response?.data?.detail || 'Failed to update employee permissions';
      handleAppRecoverableError({
        scope: 'policy-console.assign-permissions',
        error: e,
        message,
        setError,
        onRetry: () => { void assignPermissions(); },
      
        notifyMode: 'dialog',
        userInitiated: true,
      });
      setError(message);
    }
  };

  const actPendingTransition = async (userId: string, mode: 'approve' | 'reject') => {
    try {
      await api.post(`/admin/access-control/policy-console/pending-transitions/${userId}/${mode}`);
      await loadConsole();
    } catch (e: any) {
      const message = e?.response?.data?.detail || `Failed to ${mode} transition`;
      handleAppRecoverableError({
        scope: 'policy-console.pending-transition-action',
        error: e,
        message,
        setError,
        onRetry: () => { void actPendingTransition(userId, mode); },
      
        notifyMode: 'dialog',
        userInitiated: true,
      });
      setError(message);
    }
  };

  return (
    <AdminRouteGate returnTo="/policy-console">
    <AppShell>
      <ScrollView contentContainerStyle={{ padding: 16, gap: 14 }} data-testid="policy-console-page" testID="policy-console-page">
        <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 10 }}>
          <View>
            <Text style={{ color: colors.text, fontSize: 28, fontWeight: '800' }} data-testid="policy-console-title" testID="policy-console-title">Policy Console</Text>
            <Text style={{ color: colors.textMuted }}>{tx('policyConsole.subtitle', 'Role templates, permission assignment, and transition approvals')}</Text>
          </View>
          <TouchableOpacity onPress={loadConsole} style={{ backgroundColor: colors.card, borderWidth: 1, borderColor: colors.border, borderRadius: 12, paddingHorizontal: 14, paddingVertical: 10 }} data-testid="policy-console-refresh-button" testID="policy-console-refresh-button">
            <Text style={{ color: colors.text, fontWeight: '700' }}>Refresh</Text>
          </TouchableOpacity>
        </View>

        {loading && <ActivityIndicator size="large" color={colors.primary} data-testid="policy-console-loading" testID="policy-console-loading" />}
        {!!error && <Text style={{ color: colors.error }} data-testid="policy-console-error-text" testID="policy-console-error-text">{error}</Text>}
        {!!success && <Text style={{ color: colors.successText }} data-testid="policy-console-success-text" testID="policy-console-success-text">{success}</Text>}

        <View style={{ backgroundColor: colors.card, borderColor: colors.border, borderWidth: 1, borderRadius: 14, padding: 14 }} data-testid="policy-role-template-section" testID="policy-role-template-section">
          <Text style={{ color: colors.text, fontWeight: '800', fontSize: 18 }}>Role Templates</Text>
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 10 }}>
            {roleList.map((role) => (
              <TouchableOpacity
                key={role}
                onPress={() => setSelectedRole(templates.find((t) => t.role === role) || null)}
                style={{ borderRadius: 10, paddingHorizontal: 10, paddingVertical: 8, borderWidth: 1, borderColor: selectedRole?.role === role ? colors.primary : colors.border, backgroundColor: selectedRole?.role === role ? (globalThis as any).__alphaColor(colors.primary, '16') : colors.background }}
                data-testid={`policy-role-tab-${role.toLowerCase()}`} testID={`policy-role-tab-${role.toLowerCase()}`}
              >
                <Text style={{ color: colors.text, fontWeight: '700' }}>{role}</Text>
              </TouchableOpacity>
            ))}
          </View>

          <View style={{ marginTop: 12, gap: 8 }}>
            {permissionCatalog.map((permission) => (
              <TouchableOpacity key={permission} onPress={() => toggleRolePermission(permission)} style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }} data-testid={`policy-template-permission-${permission.replace(/\./g, '-')}`} testID={`policy-template-permission-${permission.replace(/\./g, '-')}`}>
                <Ionicons name={selectedRole?.permissions?.includes(permission) ? 'checkbox' : 'square-outline'} size={18} color={selectedRole?.permissions?.includes(permission) ? colors.primary : colors.textMuted} />
                <Text style={{ color: colors.text, fontSize: 13 }}>{permission}</Text>
              </TouchableOpacity>
            ))}
          </View>

          <TouchableOpacity onPress={saveRoleTemplate} style={{ marginTop: 12, backgroundColor: colors.primary, borderRadius: 10, paddingVertical: 10, alignItems: 'center' }} data-testid="policy-save-template-button" testID="policy-save-template-button">
            <Text style={{ color: colors.primaryText, fontWeight: '800' }}>Save Template</Text>
          </TouchableOpacity>
        </View>

        <View style={{ backgroundColor: colors.card, borderColor: colors.border, borderWidth: 1, borderRadius: 14, padding: 14 }} data-testid="policy-permission-assignment-section" testID="policy-permission-assignment-section">
          <Text style={{ color: colors.text, fontWeight: '800', fontSize: 18 }}>Permission Assignment</Text>
          <View style={{ flexDirection: 'row', gap: 8, marginTop: 8 }}>
            <TextInput value={query} onChangeText={setQuery} placeholder="Search user by email" placeholderTextColor={colors.textMuted} style={{ flex: 1, borderWidth: 1, borderColor: colors.border, borderRadius: 10, paddingHorizontal: 10, color: colors.text, height: 42 }} data-testid="policy-user-search-input" testID="policy-user-search-input" />
            <TouchableOpacity onPress={searchUsers} style={{ backgroundColor: colors.primary, borderRadius: 10, paddingHorizontal: 12, justifyContent: 'center' }} data-testid="policy-user-search-button" testID="policy-user-search-button">
              <Text style={{ color: colors.primaryText, fontWeight: '700' }}>Search</Text>
            </TouchableOpacity>
          </View>

          <View style={{ marginTop: 10, gap: 6 }}>
            {searchResults.slice(0, 5).map((u) => (
              <TouchableOpacity key={u.user_id} onPress={() => setSelectedUserId(u.user_id)} style={{ borderWidth: 1, borderColor: selectedUserId === u.user_id ? colors.primary : colors.border, borderRadius: 10, padding: 8 }} data-testid={`policy-user-option-${u.user_id}`} testID={`policy-user-option-${u.user_id}`}>
                <Text style={{ color: colors.text, fontWeight: '700' }}>{u.email}</Text>
                <Text style={{ color: colors.textMuted, fontSize: 12 }}>{u.platform_role || 'No employee role'}</Text>
              </TouchableOpacity>
            ))}
          </View>

          <View style={{ marginTop: 10, gap: 6 }}>
            {permissionCatalog.map((permission) => (
              <TouchableOpacity key={permission} onPress={() => setAssignmentPerms((prev) => prev.includes(permission) ? prev.filter((p) => p !== permission) : [...prev, permission])} style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }} data-testid={`policy-assignment-permission-${permission.replace(/\./g, '-')}`} testID={`policy-assignment-permission-${permission.replace(/\./g, '-')}`}>
                <Ionicons name={assignmentPerms.includes(permission) ? 'checkbox' : 'square-outline'} size={18} color={assignmentPerms.includes(permission) ? colors.primary : colors.textMuted} />
                <Text style={{ color: colors.text }}>{permission}</Text>
              </TouchableOpacity>
            ))}
          </View>

          <TouchableOpacity onPress={assignPermissions} style={{ marginTop: 10, backgroundColor: colors.primary, borderRadius: 10, paddingVertical: 10, alignItems: 'center' }} data-testid="policy-assign-permissions-button" testID="policy-assign-permissions-button">
            <Text style={{ color: colors.primaryText, fontWeight: '800' }}>Apply Permissions</Text>
          </TouchableOpacity>
        </View>

        {canManageSubscriptions && (
          <View style={{ backgroundColor: colors.card, borderColor: colors.border, borderWidth: 1, borderRadius: 14, padding: 14 }} data-testid="policy-transition-approvals-section" testID="policy-transition-approvals-section">
            <Text style={{ color: colors.text, fontWeight: '800', fontSize: 18 }}>Lifecycle Transition Approvals</Text>
            <View style={{ marginTop: 8, gap: 8 }}>
              {pendingTransitions.length === 0 && <Text style={{ color: colors.textMuted }}>No pending transitions.</Text>}
              {pendingTransitions.map((row) => (
                <View key={row.user_id} style={{ borderWidth: 1, borderColor: colors.border, borderRadius: 10, padding: 10 }} data-testid={`policy-pending-transition-${row.user_id}`} testID={`policy-pending-transition-${row.user_id}`}>
                  <Text style={{ color: colors.text, fontWeight: '700' }}>{row.email}</Text>
                  <Text style={{ color: colors.textMuted, fontSize: 12 }}>
                    {row.pending_subscription_transition?.action || 'unknown'} → {row.pending_subscription_transition?.target_plan || 'unknown'} at {row.pending_subscription_transition?.effective_at || 'n/a'}
                  </Text>
                  <View style={{ flexDirection: 'row', gap: 8, marginTop: 8 }}>
                    <TouchableOpacity onPress={() => actPendingTransition(row.user_id, 'approve')} style={{ backgroundColor: colors.success, borderRadius: 8, paddingHorizontal: 10, paddingVertical: 8 }} data-testid={`policy-transition-approve-${row.user_id}`} testID={`policy-transition-approve-${row.user_id}`}>
                      <Text style={{ color: colors.primaryText, fontWeight: '700' }}>Approve Now</Text>
                    </TouchableOpacity>
                    <TouchableOpacity onPress={() => actPendingTransition(row.user_id, 'reject')} style={{ backgroundColor: colors.error, borderRadius: 8, paddingHorizontal: 10, paddingVertical: 8 }} data-testid={`policy-transition-reject-${row.user_id}`} testID={`policy-transition-reject-${row.user_id}`}>
                      <Text style={{ color: colors.primaryText, fontWeight: '700' }}>Reject</Text>
                    </TouchableOpacity>
                  </View>
                </View>
              ))}
            </View>
          </View>
        )}

        {canViewAnalytics && observability && (
          <View style={{ backgroundColor: colors.card, borderColor: colors.border, borderWidth: 1, borderRadius: 14, padding: 14 }} data-testid="policy-observability-section" testID="policy-observability-section">
            <Text style={{ color: colors.text, fontWeight: '800', fontSize: 18 }}>Authorization Observability</Text>

            <Text style={{ color: colors.text, marginTop: 10, fontWeight: '700' }}>Denied Route Heatmap (7d)</Text>
            <View style={{ marginTop: 8, gap: 6 }}>
              {(observability.denied_route_heatmap || []).slice(0, 8).map((item: any, idx: number) => (
                <View key={`${item.path}-${idx}`} style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }} data-testid={`policy-heatmap-row-${idx}`} testID={`policy-heatmap-row-${idx}`}>
                  <Text style={{ color: colors.textMuted, width: 220, fontSize: 12 }} numberOfLines={1}>{item.path}</Text>
                  <View style={{ height: 8, borderRadius: 4, backgroundColor: colors.primary, width: Math.max(16, Math.min(220, item.count * 8)) }} />
                  <Text style={{ color: colors.text, fontWeight: '700', fontSize: 12 }}>{item.count}</Text>
                </View>
              ))}
            </View>

            <Text style={{ color: colors.text, marginTop: 12, fontWeight: '700' }}>Policy Drift Alerts</Text>
            <Text style={{ color: colors.textMuted }} data-testid="policy-drift-count-text" testID="policy-drift-count-text">{(observability.policy_drift_alerts || []).length} drift alerts</Text>

            <Text style={{ color: colors.text, marginTop: 12, fontWeight: '700' }}>Transition Failure Monitor</Text>
            <Text style={{ color: colors.textMuted }} data-testid="policy-transition-monitor-text" testID="policy-transition-monitor-text">
              stale_pending={(observability.transition_failure_monitor?.stale_pending_count ?? 0)} · recent_failed={(observability.transition_failure_monitor?.recent_rejected_or_failed ?? 0)}
            </Text>
          </View>
        )}
      </ScrollView>
    </AppShell>
    </AdminRouteGate>
  );
}
