import React, { useState } from 'react';
import { View, Text, ActivityIndicator, TouchableOpacity } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { KPICard, RevenueChart, RegionTable, RiskPanel, UserManagement, useExecTheme, useExecStyles } from './ExecDashboardPanels';
import api from '../../services/api';
import { useLiveQuery } from '../../hooks/useLiveQuery';
import { useAdminTheme } from '../../hooks/useAdminTheme';
import { useTranslation } from '../../hooks/useTranslation';
import { handleAppRecoverableError } from '../../utils/appRecoverableError';

interface Props { colors: any; }

export default function ExecDashboardTab({ colors: _propColors }: Props) {
  const _s = useExecStyles();
  const colors = useAdminTheme();
  const T = useExecTheme();
  const { t } = useTranslation();
  const tx = React.useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);
  const [activeSection, setActiveSection] = useState('overview');
  const [userSearch, setUserSearch] = useState('');
  const [userPage, setUserPage] = useState(1);

  const { data: overview, loading: ovLoading } = useLiveQuery('/admin/executive/overview', { entity: 'executive', pollInterval: 60000 });
  const { data: financial } = useLiveQuery('/admin/executive/financial-intelligence', { entity: 'executive', pollInterval: 60000 });
  const { data: risk } = useLiveQuery('/admin/executive/risk-control', { entity: 'executive', pollInterval: 60000 });
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const { data: users, loading: _usrLoading } = useLiveQuery('/admin/executive/user-management?page=1&limit=10', { entity: 'users', pollInterval: 60000 });
  const loading = ovLoading;

  const loadUsers = async (page: number, search: string) => {
    try {
      const res = await api.get(`/admin/executive/user-management?page=${page}&limit=10&search=${search}`);
      setUsers(res.data);
      setUserPage(page);
    } catch (error) { handleAppRecoverableError({ scope: 'src/components/admin/ExecDashboardTab.tsx#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
  };

  if (loading) {
    return <View style={{ paddingVertical: 40, alignItems: 'center' }}><ActivityIndicator size="large" color={T.primary} /></View>;
  }

  const sections = [
    { id: 'overview', label: 'Overview', icon: 'grid' },
    { id: 'financial', label: 'Financial', icon: 'cash' },
    { id: 'risk', label: 'Risk', icon: 'shield-checkmark' },
    { id: 'users', label: 'Users', icon: 'people' },
  ];

  return (
    <View data-testid="exec-dashboard-tab" testID="exec-dashboard-tab">
      {/* Title */}
      <View style={{ marginBottom: 16 }}>
        <Text style={{ fontSize: 20, fontWeight: '800', color: T.text }} data-testid="exec-dashboard-title" testID="exec-dashboard-title">{tx('admin.execDashboard.title', 'Executive Dashboard')}</Text>
        <Text style={{ fontSize: 12, color: T.textSec, marginTop: 4 }}>{tx('admin.execDashboard.subtitle', 'Real-time business intelligence and KPIs')}</Text>
      </View>

      {/* Section Tabs */}
      <View style={{ flexDirection: 'row', gap: 6, marginBottom: 20, flexWrap: 'wrap' }} data-testid="exec-section-tabs" testID="exec-section-tabs">
        {sections.map(s => (
          <TouchableOpacity key={s.id} style={{
            flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 14, paddingVertical: 8,
            borderRadius: 10, backgroundColor: activeSection === s.id ? T.primary : T.bgSoft,
          }} onPress={() => setActiveSection(s.id)} data-testid={`exec-tab-${s.id}`} testID={`exec-tab-${s.id}`}>
            <Ionicons name={s.icon as any} size={14} color={activeSection === s.id ? 'var(--app-primary-text)' : T.textSec} />
            <Text style={{ fontSize: 12, fontWeight: '700', color: activeSection === s.id ? 'var(--app-primary-text)' : T.textSec }}>{s.label}</Text>
          </TouchableOpacity>
        ))}
      </View>

      {/* Overview Section */}
      {activeSection === 'overview' && overview && (
        <View data-testid="exec-overview-section" testID="exec-overview-section">
          {/* KPI Cards */}
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10, marginBottom: 20 }}>
            {(overview.kpis || []).map((kpi: any) => (
              <View key={kpi.id} style={{ flex: 1, minWidth: 200 }}>
                <KPICard kpi={kpi} />
              </View>
            ))}
          </View>
          {/* Revenue Chart */}
          {overview.revenue_chart && <RevenueChart data={overview.revenue_chart} />}
          {/* Region Breakdown */}
          {overview.regions && (
            <View style={{ marginTop: 16 }}>
              <RegionTable data={overview.regions} />
            </View>
          )}
        </View>
      )}

      {/* Financial Section */}
      {activeSection === 'financial' && financial && (
        <View data-testid="exec-financial-section" testID="exec-financial-section">
          {financial.kpis && (
            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10, marginBottom: 20 }}>
              {financial.kpis.map((kpi: any) => (
                <View key={kpi.id} style={{ flex: 1, minWidth: 200 }}>
                  <KPICard kpi={kpi} />
                </View>
              ))}
            </View>
          )}
        </View>
      )}

      {/* Risk Section */}
      {activeSection === 'risk' && risk && (
        <View data-testid="exec-risk-section" testID="exec-risk-section">
          <RiskPanel data={risk} />
        </View>
      )}

      {/* Users Section */}
      {activeSection === 'users' && users && (
        <View data-testid="exec-users-section" testID="exec-users-section">
          <UserManagement
            users={users.users || []}
            total={users.total || 0}
            search={userSearch}
            setSearch={(s: string) => { setUserSearch(s); loadUsers(1, s); }}
            page={userPage}
            setPage={(p: number) => loadUsers(p, userSearch)}
            pages={users.pages || 1}
          />
        </View>
      )}
    </View>
  );
}
