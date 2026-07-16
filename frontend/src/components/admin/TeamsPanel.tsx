import React, { useState } from 'react';
import { View, Text, TouchableOpacity, TextInput, ActivityIndicator } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { useLiveQuery } from '../../hooks/useLiveQuery';
import AutoFixBanner from './AutoFixBanner';
import { useAdminTheme } from '../../hooks/useAdminTheme';
import { useTranslation } from '../../hooks/useTranslation';
import { handleAppRecoverableError } from '../../utils/appRecoverableError';

const tx = (_key: string, fallback: string) => fallback;

const ROLE_COLORS = ['var(--app-primary)', 'var(--app-success)', 'var(--app-warning)', 'var(--app-error)', 'var(--app-primary)', 'var(--app-primary)', 'var(--app-primary)', 'var(--app-warning)'];

export default function TeamsPanel({ colors: _colors }: { colors: any }) {
  const { t } = useTranslation();
  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };

  const colors = useAdminTheme();
  const ROLE_META: Record<string, { color: string; icon: string }> = {
    owner: { color: colors.warningText, icon: 'star' },
    admin: { color: colors.error, icon: 'shield-checkmark' },
    manager: { color: colors.accent, icon: 'briefcase' },
    member: { color: colors.primary, icon: 'person' },
    viewer: { color: colors.textMuted, icon: 'eye' },
  };
  const { data: teamsData, loading, refetch: load } = useLiveQuery('/teams/', { entity: 'teams', pollInterval: 30000 });
  const teams = teamsData?.teams || [];
  const [showCreate, setShowCreate] = useState(false);
  const [name, setName] = useState('');
  const [desc, setDesc] = useState('');
  const [selectedTeam, setSelectedTeam] = useState<any>(null);
  const [auditLogs, setAuditLogs] = useState<any[]>([]);
  const [inviteEmail, setInviteEmail] = useState('');
  const [inviteRole, setInviteRole] = useState('member');
  const [detailTab, setDetailTab] = useState<'members' | 'audit' | 'roles'>('members');
  const [customRoles, setCustomRoles] = useState<any[]>([]);
  const [allPermissions, setAllPermissions] = useState<any[]>([]);
  const [showRoleForm, setShowRoleForm] = useState(false);
  const [editingRole, setEditingRole] = useState<any>(null);
  const [roleName, setRoleName] = useState('');
  const [roleLevel, setRoleLevel] = useState('50');
  const [roleColor, setRoleColor] = useState('var(--app-primary)');
  const [rolePerms, setRolePerms] = useState<string[]>([]);

  const create = async () => {
    if (!name.trim()) return;
    try { await api.post('/teams/', { name: name.trim(), description: desc }); setShowCreate(false); setName(''); setDesc(''); load(); } catch (error) { handleAppRecoverableError({ scope: 'src/components/admin/TeamsPanel.tsx#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
  };

  const viewTeam = async (tid: string) => {
    try {
      const [tRes, aRes] = await Promise.all([api.get(`/teams/${tid}`), api.get(`/teams/${tid}/audit`)]);
      setSelectedTeam(tRes.data);
      setAuditLogs(aRes.data.audit_logs || []);
      setDetailTab('members');
    } catch (error) { handleAppRecoverableError({ scope: 'src/components/admin/TeamsPanel.tsx#catch2', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
  };

  const loadCustomRoles = async (tid: string) => {
    try {
      const r = await api.get(`/teams/${tid}/custom-roles`);
      setCustomRoles(r.data.custom_roles || []);
      setAllPermissions(r.data.all_permissions || []);
    } catch (error) { handleAppRecoverableError({ scope: 'src/components/admin/TeamsPanel.tsx#catch3', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
  };

  const resetRoleForm = () => {
    setRoleName(''); setRoleLevel('50'); setRoleColor('var(--app-primary)'); setRolePerms([]);
    setEditingRole(null); setShowRoleForm(false);
  };

  const openEditRole = (role: any) => {
    setEditingRole(role);
    setRoleName(role.name);
    setRoleLevel(String(role.level));
    setRoleColor(role.color || 'var(--app-primary)');
    setRolePerms(role.permissions || []);
    setShowRoleForm(true);
  };

  const saveRole = async () => {
    if (!roleName.trim() || !selectedTeam) return;
    const payload = { name: roleName.trim(), level: parseInt(roleLevel) || 50, color: roleColor, permissions: rolePerms };
    try {
      if (editingRole) {
        await api.put(`/teams/${selectedTeam.team_id}/custom-roles/${editingRole.role_id}`, payload);
      } else {
        await api.post(`/teams/${selectedTeam.team_id}/custom-roles`, payload);
      }
      resetRoleForm();
      loadCustomRoles(selectedTeam.team_id);
    } catch (error) { handleAppRecoverableError({ scope: 'src/components/admin/TeamsPanel.tsx#catch4', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
  };

  const deleteRole = async (roleId: string) => {
    if (!selectedTeam) return;
    try { await api.delete(`/teams/${selectedTeam.team_id}/custom-roles/${roleId}`); loadCustomRoles(selectedTeam.team_id); } catch (error) { handleAppRecoverableError({ scope: 'src/components/admin/TeamsPanel.tsx#catch5', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
  };

  const togglePerm = (pid: string) => {
    setRolePerms(prev => prev.includes(pid) ? prev.filter(p => p !== pid) : [...prev, pid]);
  };

  const invite = async () => {
    if (!inviteEmail.trim() || !selectedTeam) return;
    try { await api.post(`/teams/${selectedTeam.team_id}/invite`, { email: inviteEmail.trim(), role: inviteRole }); setInviteEmail(''); viewTeam(selectedTeam.team_id); } catch (error) { handleAppRecoverableError({ scope: 'src/components/admin/TeamsPanel.tsx#catch6', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
  };

  const removeMember = async (mid: string) => {
    if (!selectedTeam) return;
    try { await api.delete(`/teams/${selectedTeam.team_id}/members/${mid}`); viewTeam(selectedTeam.team_id); } catch (error) { handleAppRecoverableError({ scope: 'src/components/admin/TeamsPanel.tsx#catch7', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
  };

  const changeRole = async (mid: string, role: string) => {
    if (!selectedTeam) return;
    try { await api.put(`/teams/${selectedTeam.team_id}/members/${mid}/role`, { role }); viewTeam(selectedTeam.team_id); } catch (error) { handleAppRecoverableError({ scope: 'src/components/admin/TeamsPanel.tsx#catch8', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
  };

  const deleteTeam = async (tid: string) => {
    try { await api.delete(`/teams/${tid}`); setSelectedTeam(null); load(); } catch (error) { handleAppRecoverableError({ scope: 'src/components/admin/TeamsPanel.tsx#catch9', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
  };

  if (selectedTeam) {
    return (
      <View data-testid="admin-team-detail-panel" testID="admin-team-detail-panel">
      <AutoFixBanner domain="teams" />
        <TouchableOpacity accessibilityLabel={tx('admin.teamsPanel.auto.accessibility.001', 'Back to Teams')} onPress={() => setSelectedTeam(null)} style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 16 }}>
          <Ionicons name="arrow-back" size={16} color={colors.primary} /><Text style={{ color: colors.primary, fontSize: 12, fontWeight: '600' }}>{tx('admin.teamsPanel.auto.text.001', 'Back to Teams')}</Text>
        </TouchableOpacity>

        <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
          <View>
            <Text style={{ color: colors.text, fontSize: 20, fontWeight: '800' }} data-testid="admin-team-name" testID="admin-team-name">{selectedTeam.name}</Text>
            <Text style={{ color: colors.textMuted, fontSize: 11, marginTop: 2 }}>{selectedTeam.description || 'No description'} | {selectedTeam.members?.length || 0} members</Text>
          </View>
          <TouchableOpacity onPress={() => deleteTeam(selectedTeam.team_id)} data-testid="admin-delete-team" testID="admin-delete-team"
            style={{ backgroundColor: colors.errorSoft, paddingHorizontal: 12, paddingVertical: 6, borderRadius: 8, borderWidth: 1, borderColor: colors.errorSoft }}>
            <Text style={{ color: colors.error, fontSize: 11, fontWeight: '700' }}>{tx('admin.teamsPanel.auto.text.002', 'Delete')}</Text>
          </TouchableOpacity>
        </View>

        {/* Tabs */}
        <View style={{ flexDirection: 'row', gap: 6, marginBottom: 16 }}>
          {(['members', 'roles', 'audit'] as const).map(tab => (
            <TouchableOpacity key={tab} onPress={() => { setDetailTab(tab); if (tab === 'roles') loadCustomRoles(selectedTeam.team_id); }} data-testid={`admin-team-tab-${tab}`} testID={`admin-team-tab-${tab}`}
              style={{ paddingHorizontal: 14, paddingVertical: 7, borderRadius: 8, backgroundColor: detailTab === tab ? colors.primary : colors.card, borderWidth: 1, borderColor: detailTab === tab ? colors.primary : colors.border }}>
              <Text style={{ color: detailTab === tab ? colors.primaryText : colors.textMuted, fontSize: 11, fontWeight: '700', textTransform: 'capitalize' }}>{tab === 'roles' ? 'Custom Roles' : tab}</Text>
            </TouchableOpacity>
          ))}
        </View>

        {detailTab === 'members' && (
          <>
            {/* Invite */}
            <View style={{ flexDirection: 'row', gap: 6, marginBottom: 16, flexWrap: 'wrap' }}>
              <TextInput value={inviteEmail} onChangeText={setInviteEmail} placeholder={tx('admin.teamsPanel.auto.placeholder.001', 'Email to invite')} placeholderTextColor={colors.textMuted} data-testid="admin-invite-email" testID="admin-invite-email"
                style={{ flex: 1, minWidth: 160, backgroundColor: colors.card, color: colors.text, borderRadius: 8, padding: 10, borderWidth: 1, borderColor: colors.border, fontSize: 12 }} />
              <View style={{ flexDirection: 'row', gap: 4 }}>
                {['admin', 'manager', 'member', 'viewer'].map(r => (
                  <TouchableOpacity key={r} accessibilityLabel={tx('admin.teamsPanel.auto.accessibility.002', 'Invite')} onPress={() => setInviteRole(r)}
                    style={{ paddingHorizontal: 8, paddingVertical: 6, borderRadius: 6, backgroundColor: inviteRole === r ? (globalThis as any).__alphaColor((ROLE_META[r]?.color), '20') : colors.card, borderWidth: 1, borderColor: inviteRole === r ? ROLE_META[r]?.color : colors.border }}>
                    <Text style={{ color: inviteRole === r ? ROLE_META[r]?.color : colors.textMuted, fontSize: 9, fontWeight: '700', textTransform: 'uppercase' }}>{r}</Text>
                  </TouchableOpacity>
                ))}
              </View>
              <TouchableOpacity onPress={invite} data-testid="admin-invite-btn" testID="admin-invite-btn" style={{ backgroundColor: colors.primary, paddingHorizontal: 14, paddingVertical: 8, borderRadius: 8 }}>
                <Text style={{ color: colors.primaryText, fontSize: 11, fontWeight: '700' }}>{tx('admin.teamsPanel.auto.text.003', 'Invite')}</Text>
              </TouchableOpacity>
            </View>

            {/* Members */}
            {(selectedTeam.members || []).map((m: any) => (
              <View key={m.user_id} data-testid={`admin-member-${m.user_id}`} testID={`admin-member-${m.user_id}`}
                style={{ flexDirection: 'row', alignItems: 'center', padding: 12, marginBottom: 6, backgroundColor: colors.card, borderRadius: 10, borderWidth: 1, borderColor: colors.border }}>
                <View style={{ width: 34, height: 34, borderRadius: 9, backgroundColor: (globalThis as any).__alphaColor((ROLE_META[m.role]?.color || colors.border), '15'), alignItems: 'center', justifyContent: 'center', marginRight: 10 }}>
                  <Ionicons name={ROLE_META[m.role]?.icon as any || 'person'} size={16} color={ROLE_META[m.role]?.color || colors.textSec} />
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={{ color: colors.text, fontSize: 13, fontWeight: '600' }}>{m.name || m.email}</Text>
                  <Text style={{ color: colors.textMuted, fontSize: 10 }}>{m.email}</Text>
                </View>
                <View style={{ backgroundColor: (globalThis as any).__alphaColor((ROLE_META[m.role]?.color || colors.border), '15'), paddingHorizontal: 8, paddingVertical: 3, borderRadius: 6, marginRight: 6 }}>
                  <Text style={{ color: ROLE_META[m.role]?.color || colors.textSec, fontSize: 9, fontWeight: '800', textTransform: 'uppercase' }}>{m.role}</Text>
                </View>
                {m.role !== 'owner' && (
                  <View style={{ flexDirection: 'row', gap: 4 }}>
                    <TouchableOpacity onPress={() => changeRole(m.user_id, m.role === 'member' ? 'admin' : 'member')} data-testid={`admin-toggle-role-${m.user_id}`} testID={`admin-toggle-role-${m.user_id}`}>
                      <Ionicons name="swap-horizontal" size={16} color={colors.textMuted} />
                    </TouchableOpacity>
                    <TouchableOpacity onPress={() => removeMember(m.user_id)} data-testid={`admin-remove-${m.user_id}`} testID={`admin-remove-${m.user_id}`}>
                      <Ionicons name="close-circle" size={16} color={'var(--app-error)'} />
                    </TouchableOpacity>
                  </View>
                )}
              </View>
            ))}
          </>
        )}

        {detailTab === 'roles' && (
          <View data-testid="admin-custom-roles-tab" testID="admin-custom-roles-tab">
            <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
              <Text style={{ color: colors.text, fontSize: 14, fontWeight: '700' }}>{tx('admin.teamsPanel.auto.text.004', 'Custom Roles')}</Text>
              <TouchableOpacity onPress={() => { resetRoleForm(); setShowRoleForm(true); }} data-testid="admin-create-role-btn" testID="admin-create-role-btn"
                style={{ flexDirection: 'row', alignItems: 'center', gap: 4, backgroundColor: colors.primary, paddingHorizontal: 12, paddingVertical: 6, borderRadius: 8 }}>
                <Ionicons name="add" size={14} color={colors.primaryText} /><Text style={{ color: colors.primaryText, fontSize: 10, fontWeight: '700' }}>{tx('admin.teamsPanel.auto.text.005', 'New Role')}</Text>
              </TouchableOpacity>
            </View>

            {showRoleForm && (
              <View style={{ backgroundColor: colors.card, borderRadius: 12, padding: 14, marginBottom: 16, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(colors.primary, '30') }} data-testid="admin-role-form" testID="admin-role-form">
                <Text style={{ color: colors.text, fontSize: 13, fontWeight: '700', marginBottom: 10 }}>{editingRole ? 'Edit Role' : 'Create Custom Role'}</Text>
                <TextInput value={roleName} onChangeText={setRoleName} placeholder={tx('admin.teamsPanel.auto.placeholder.002', 'Role name')} placeholderTextColor={colors.textMuted} data-testid="admin-role-name-input" testID="admin-role-name-input"
                  style={{ backgroundColor: colors.surface, color: colors.text, borderRadius: 8, padding: 10, marginBottom: 8, borderWidth: 1, borderColor: colors.border, fontSize: 12 }} />
                <View style={{ flexDirection: 'row', gap: 8, marginBottom: 8 }}>
                  <View style={{ flex: 1 }}>
                    <Text style={{ color: colors.textMuted, fontSize: 10, fontWeight: '600', marginBottom: 4 }}>{tx('admin.teamsPanel.auto.text.006', 'Priority Level (10-90)')}</Text>
                    <TextInput value={roleLevel} onChangeText={setRoleLevel} placeholder="50" placeholderTextColor={colors.textMuted} data-testid="admin-role-level-input" testID="admin-role-level-input"
                      style={{ backgroundColor: colors.surface, color: colors.text, borderRadius: 8, padding: 10, borderWidth: 1, borderColor: colors.border, fontSize: 12 }} />
                  </View>
                  <View style={{ flex: 1 }}>
                    <Text style={{ color: colors.textMuted, fontSize: 10, fontWeight: '600', marginBottom: 4 }}>{tx('admin.teamsPanel.auto.text.007', 'Color')}</Text>
                    <View style={{ flexDirection: 'row', gap: 4, flexWrap: 'wrap' }}>
                      {ROLE_COLORS.map(c => (
                        <TouchableOpacity key={c} onPress={() => setRoleColor(c)} data-testid={`admin-role-color-${c}`} testID={`admin-role-color-${c}`}
                          style={{ width: 24, height: 24, borderRadius: 6, backgroundColor: c, borderWidth: 2, borderColor: roleColor === c ? colors.text : 'transparent' /* @theme-ok deliberate-high-contrast outline on selected color chip */ }} />
                      ))}
                    </View>
                  </View>
                </View>
                <Text style={{ color: colors.textMuted, fontSize: 10, fontWeight: '600', marginBottom: 6, marginTop: 4 }}>{tx('admin.teamsPanel.auto.text.008', 'Permissions')}</Text>
                <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginBottom: 12 }}>
                  {allPermissions.map((p: any) => (
                    <TouchableOpacity key={p.id} onPress={() => togglePerm(p.id)} data-testid={`admin-perm-toggle-${p.id}`} testID={`admin-perm-toggle-${p.id}`}
                      style={{ flexDirection: 'row', alignItems: 'center', gap: 4, paddingHorizontal: 10, paddingVertical: 6, borderRadius: 8, backgroundColor: rolePerms.includes(p.id) ? (globalThis as any).__alphaColor(colors.primary, '15') : colors.surface, borderWidth: 1, borderColor: rolePerms.includes(p.id) ? colors.primary : colors.border }}>
                      <Ionicons name={rolePerms.includes(p.id) ? 'checkbox' : 'square-outline'} size={14} color={rolePerms.includes(p.id) ? colors.primary : colors.textMuted} />
                      <Text style={{ color: rolePerms.includes(p.id) ? colors.primary : colors.textMuted, fontSize: 10, fontWeight: '600' }}>{p.label}</Text>
                    </TouchableOpacity>
                  ))}
                </View>
                <View style={{ flexDirection: 'row', gap: 8 }}>
                  <TouchableOpacity onPress={saveRole} data-testid="admin-save-role-btn" testID="admin-save-role-btn" style={{ backgroundColor: colors.primary, borderRadius: 8, paddingVertical: 10, paddingHorizontal: 20 }}>
                    <Text style={{ color: colors.primaryText, fontSize: 11, fontWeight: '700' }}>{editingRole ? 'Update' : 'Create'}</Text>
                  </TouchableOpacity>
                  <TouchableOpacity onPress={resetRoleForm} style={{ paddingVertical: 10, paddingHorizontal: 16 }} accessibilityLabel={tx('admin.teamsPanel.auto.accessibility.003', 'Cancel')}>
                    <Text style={{ color: colors.textMuted, fontSize: 11, fontWeight: '600' }}>{tx('admin.teamsPanel.auto.text.009', 'Cancel')}</Text>
                  </TouchableOpacity>
                </View>
              </View>
            )}

            {customRoles.length === 0 && !showRoleForm ? (
              <View style={{ padding: 24, alignItems: 'center' }}>
                <Ionicons name="ribbon-outline" size={28} color={colors.textMuted} />
                <Text style={{ color: colors.textMuted, fontSize: 11, marginTop: 6 }}>{tx('admin.teamsPanel.auto.text.010', 'No custom roles yet. Create one to extend the built-in roles.')}</Text>
              </View>
            ) : customRoles.map(role => (
              <View key={role.role_id} data-testid={`admin-custom-role-${role.role_id}`} testID={`admin-custom-role-${role.role_id}`}
                style={{ flexDirection: 'row', alignItems: 'center', padding: 12, marginBottom: 6, backgroundColor: colors.surfaceHover, borderRadius: 10, borderWidth: 1, borderColor: colors.border, borderLeftWidth: 3, borderLeftColor: role.color || colors.borderStrong }}>
                <View style={{ width: 34, height: 34, borderRadius: 9, backgroundColor: (globalThis as any).__alphaColor((role.color || colors.border), '15'), alignItems: 'center', justifyContent: 'center', marginRight: 10 }}>
                  <Ionicons name="ribbon" size={16} color={role.color || colors.textSec} />
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={{ color: colors.text, fontSize: 13, fontWeight: '600' }}>{role.name}</Text>
                  <Text style={{ color: colors.textMuted, fontSize: 10 }}>Level {role.level} | {(role.permissions || []).length} permissions</Text>
                </View>
                <View style={{ flexDirection: 'row', gap: 6 }}>
                  <TouchableOpacity onPress={() => openEditRole(role)} data-testid={`admin-edit-role-${role.role_id}`} testID={`admin-edit-role-${role.role_id}`}>
                    <Ionicons name="create-outline" size={16} color={'var(--app-primary)'} />
                  </TouchableOpacity>
                  <TouchableOpacity onPress={() => deleteRole(role.role_id)} data-testid={`admin-delete-role-${role.role_id}`} testID={`admin-delete-role-${role.role_id}`}>
                    <Ionicons name="trash-outline" size={16} color={'var(--app-error)'} />
                  </TouchableOpacity>
                </View>
              </View>
            ))}
          </View>
        )}

        {detailTab === 'audit' && (
          <View>
            {auditLogs.length === 0 ? (
              <View style={{ padding: 24, alignItems: 'center' }}><Ionicons name="document-text-outline" size={28} color={colors.textMuted} /><Text style={{ color: colors.textMuted, fontSize: 11, marginTop: 6 }}>{tx('admin.teamsPanel.auto.text.011', 'No activity yet')}</Text></View>
            ) : auditLogs.map((log, idx) => (
              <View key={log.audit_id || idx} style={{ flexDirection: 'row', alignItems: 'flex-start', gap: 10, padding: 10, marginBottom: 4, backgroundColor: colors.surfaceHover, borderRadius: 8, borderWidth: 1, borderColor: colors.border }}>
                <View style={{ width: 28, height: 28, borderRadius: 7, backgroundColor: (globalThis as any).__alphaColor(colors.primary, '15'), alignItems: 'center', justifyContent: 'center' }}>
                  <Ionicons name="document-text" size={12} color={'var(--app-primary)'} />
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={{ color: colors.text, fontSize: 12, fontWeight: '600' }}>{log.action?.replace(/_/g, ' ')}</Text>
                  <Text style={{ color: colors.textMuted, fontSize: 10 }}>by {log.user_name} | {new Date(log.created_at).toLocaleString()}</Text>
                </View>
              </View>
            ))}
          </View>
        )}
      </View>
    );
  }

  return (
    <View data-testid="admin-teams-panel" testID="admin-teams-panel">
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
        <View>
          <Text style={{ color: colors.text, fontSize: 18, fontWeight: '800' }}>{tx('admin.teamsPanel.auto.text.012', 'Team Management')}</Text>
          <Text style={{ color: colors.textMuted, fontSize: 11, marginTop: 2 }}>{tx('admin.teamsPanel.auto.text.013', 'Enterprise team control and permissions')}</Text>
        </View>
        <TouchableOpacity onPress={() => setShowCreate(!showCreate)} data-testid="admin-create-team-btn" testID="admin-create-team-btn" style={{ flexDirection: 'row', alignItems: 'center', gap: 4, backgroundColor: colors.primary, paddingHorizontal: 14, paddingVertical: 8, borderRadius: 8 }}>
          <Ionicons name="add" size={16} color={colors.primaryText} /><Text style={{ color: colors.primaryText, fontSize: 11, fontWeight: '700' }}>{tx('admin.teamsPanel.auto.text.014', 'New Team')}</Text>
        </TouchableOpacity>
      </View>

      {/* Stats */}
      <View style={{ flexDirection: 'row', gap: 8, marginTop: 16, marginBottom: 16 }}>
        <View style={{ flex: 1, backgroundColor: colors.primarySoft, borderRadius: 10, padding: 14, borderWidth: 1, borderColor: colors.primarySoft }}>
          <Text style={{ color: colors.primary, fontSize: 20, fontWeight: '800' }}>{teams.length}</Text>
          <Text style={{ color: colors.textMuted, fontSize: 10, fontWeight: '600' }}>{tx('admin.teamsPanel.auto.text.015', 'Teams')}</Text>
        </View>
        <View style={{ flex: 1, backgroundColor: colors.successSoft, borderRadius: 10, padding: 14, borderWidth: 1, borderColor: colors.successSoft }}>
          <Text style={{ color: colors.successText, fontSize: 20, fontWeight: '800' }}>{teams.reduce((s, t) => s + (t.member_count || 0), 0)}</Text>
          <Text style={{ color: colors.textMuted, fontSize: 10, fontWeight: '600' }}>{tx('admin.teamsPanel.auto.text.016', 'Total Members')}</Text>
        </View>
        <View style={{ flex: 1, backgroundColor: colors.accentSoft, borderRadius: 10, padding: 14, borderWidth: 1, borderColor: colors.accentSoft }}>
          <Text style={{ color: colors.accent, fontSize: 20, fontWeight: '800' }}>{5 + teams.reduce((s, t) => s + (t.custom_role_count || 0), 0)}</Text>
          <Text style={{ color: colors.textMuted, fontSize: 10, fontWeight: '600' }}>{tx('admin.teamsPanel.auto.text.017', 'Roles')}</Text>
        </View>
      </View>

      {showCreate && (
        <View style={{ backgroundColor: colors.surfaceHover, borderRadius: 12, padding: 14, marginBottom: 16, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(colors.primary, '30') }}>
          <Text style={{ color: colors.text, fontSize: 13, fontWeight: '700', marginBottom: 10 }}>{tx('admin.teamsPanel.auto.text.018', 'Create New Team')}</Text>
          <TextInput value={name} onChangeText={setName} placeholder={tx('admin.teamsPanel.auto.placeholder.003', 'Team name')} placeholderTextColor={colors.textMuted} data-testid="admin-team-name-input" testID="admin-team-name-input"
            style={{ backgroundColor: colors.surface, color: colors.text, borderRadius: 8, padding: 10, marginBottom: 8, borderWidth: 1, borderColor: colors.border, fontSize: 12 }} />
          <TextInput value={desc} onChangeText={setDesc} placeholder={tx('admin.teamsPanel.auto.placeholder.004', 'Description (optional)')} placeholderTextColor={colors.textMuted}
            style={{ backgroundColor: colors.surface, color: colors.text, borderRadius: 8, padding: 10, marginBottom: 10, borderWidth: 1, borderColor: colors.border, fontSize: 12 }} />
          <View style={{ flexDirection: 'row', gap: 8 }}>
            <TouchableOpacity onPress={create} data-testid="admin-submit-team-btn" testID="admin-submit-team-btn" style={{ backgroundColor: colors.primary, borderRadius: 8, paddingVertical: 10, paddingHorizontal: 20 }}>
              <Text style={{ color: colors.primaryText, fontSize: 11, fontWeight: '700' }}>{tx('admin.teamsPanel.auto.text.019', 'Create')}</Text>
            </TouchableOpacity>
            <TouchableOpacity accessibilityLabel={tx('admin.teamsPanel.auto.accessibility.004', 'Cancel')} onPress={() => setShowCreate(false)} style={{ paddingVertical: 10, paddingHorizontal: 16 }}>
              <Text style={{ color: colors.textMuted, fontSize: 11, fontWeight: '600' }}>{tx('admin.teamsPanel.auto.text.020', 'Cancel')}</Text>
            </TouchableOpacity>
          </View>
        </View>
      )}

      {loading ? <ActivityIndicator color={'var(--app-primary)'} /> : teams.length === 0 ? (
        <View style={{ padding: 30, alignItems: 'center' }}><Ionicons name="people-outline" size={36} color={colors.textMuted} /><Text style={{ color: colors.textMuted, marginTop: 8, fontSize: 12 }}>{tx('admin.teamsPanel.auto.text.021', 'No teams yet')}</Text></View>
      ) : teams.map(t => (
        <TouchableOpacity key={t.team_id} onPress={() => viewTeam(t.team_id)} data-testid={`admin-team-${t.team_id}`} testID={`admin-team-${t.team_id}`}
          style={{ backgroundColor: colors.surfaceHover, borderRadius: 12, padding: 14, marginBottom: 8, borderWidth: 1, borderColor: colors.border, flexDirection: 'row', alignItems: 'center' }}>
          <View style={{ width: 38, height: 38, borderRadius: 10, backgroundColor: colors.primarySoft, alignItems: 'center', justifyContent: 'center', marginRight: 12 }}>
            <Ionicons name="people" size={18} color={'var(--app-primary)'} />
          </View>
          <View style={{ flex: 1 }}>
            <Text style={{ color: colors.text, fontSize: 14, fontWeight: '700' }}>{t.name}</Text>
            <Text style={{ color: colors.textMuted, fontSize: 10 }}>{t.member_count} member(s) | Created {new Date(t.created_at).toLocaleDateString()}</Text>
          </View>
          <Ionicons name="chevron-forward" size={16} color={colors.textMuted} />
        </TouchableOpacity>
      ))}
    </View>
  );
}
