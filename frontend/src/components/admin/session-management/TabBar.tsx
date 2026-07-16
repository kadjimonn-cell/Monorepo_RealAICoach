import React from 'react';
import { View, Text, TouchableOpacity } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useExecTheme} from '../ExecDashboardPanels';
import { Tab } from './types';

interface TabBarProps {
  tab: Tab;
  setTab: (t: Tab) => void;
  suspiciousTotal?: number;
  activePolicies?: number;
  totalBlocked?: number;
}

export default function TabBar({ tab, setTab, suspiciousTotal, activePolicies, totalBlocked }: TabBarProps) {
  const T = useExecTheme();
  const tabs = [
    { id: 'security' as Tab, label: 'Security', icon: 'shield-checkmark' },
    { id: 'sessions' as Tab, label: 'Sessions', icon: 'key' },
    { id: 'suspicious' as Tab, label: 'Threats', icon: 'shield', badge: suspiciousTotal },
    { id: 'map' as Tab, label: 'Map', icon: 'globe' },
    { id: 'policies' as Tab, label: 'Cleanup', icon: 'trash', badge: activePolicies || undefined },
    { id: 'alerts' as Tab, label: 'Alerts', icon: 'notifications' },
    { id: 'blocklist' as Tab, label: 'Blocklist', icon: 'ban', badge: totalBlocked || undefined },
  ] as const;

  return (
    <View style={{ flexDirection: 'row', marginBottom: 16, gap: 6, flexWrap: 'wrap' }}>
      {tabs.map(t_ => (
        <TouchableOpacity key={t_.id} onPress={() => setTab(t_.id)}
          style={{ flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 14, paddingVertical: 8, borderRadius: 8,
            backgroundColor: tab === t_.id ? T.primary : T.bgSoft, borderWidth: 1,
            borderColor: tab === t_.id ? T.primary : T.border }}
          data-testid={`session-tab-${t_.id}`} testID={`session-tab-${t_.id}`}
        >
          <Ionicons name={t_.icon as any} size={14} color={tab === t_.id ? 'var(--app-primary-text)' : T.textMuted} />
          <Text style={{ color: tab === t_.id ? 'var(--app-primary-text)' : T.textSec, fontSize: 12, fontWeight: '700' }}>{t_.label}</Text>
          {t_.badge != null && t_.badge > 0 && (
            <View style={{ backgroundColor: tab === t_.id ? 'rgba(255,255,255,0.3)' : T.errorSoft, borderRadius: 10, paddingHorizontal: 6, paddingVertical: 1 }}>
              <Text style={{ color: tab === t_.id ? 'var(--app-primary-text)' : T.error, fontSize: 9, fontWeight: '800' }}>{t_.badge}</Text>
            </View>
          )}
        </TouchableOpacity>
      ))}
    </View>
  );
}

/* i18n-probe t('i18n.auto.probe') */
