import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { ActivityIndicator, ScrollView, Switch, Text, TouchableOpacity, View } from 'react-native';
import api from '../../services/api';
import { useAuth } from '../../context/AuthContext';
import { handleAppRecoverableError } from '../../utils/appRecoverableError';
import { useTranslation } from '../../hooks/useTranslation';

type Props = { colors: any };

export const MatchdayRemindersOpsPanel = ({ colors }: Props) => {
  const { t } = useTranslation();
  t('i18n.route.admin.matchday.reminders.probe');
  const { user } = useAuth();
  const userId = user?.user_id || '';
  const [loading, setLoading] = useState(true);
  const [prefs, setPrefs] = useState<any>(null);
  const [leagues, setLeagues] = useState<any[]>([]);

  const load = useCallback(async () => {
    if (!userId) {
      setLoading(false);
      return;
    }
    setLoading(true);
    try {
      const [prefsRes, leaguesRes] = await Promise.all([
        api.get(`/matchday-reminders/prefs/${userId}`),
        api.get(`/matchday-reminders/league/subscriptions/${userId}`),
      ]);
      setPrefs(prefsRes.data?.preferences || {});
      setLeagues(leaguesRes.data?.leagues || []);
    } finally {
      setLoading(false);
    }
  }, [userId]);

  useEffect(() => {
    void load();
  }, [load]);

  const updatePref = useCallback(async (key: string, value: any) => {
    const updated = { ...(prefs || {}), [key]: value };
    setPrefs(updated);
    try {
      await api.post('/matchday-reminders/prefs', { user_id: userId, [key]: value });
    } catch (error) { handleAppRecoverableError({ scope: 'src/components/admin/MatchdayRemindersOpsPanel.tsx#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
  }, [prefs, userId]);

  const toggleLeague = useCallback(async (leagueId: string, enabled: boolean) => {
    setLeagues((prev) => prev.map((l) => (l.id === leagueId ? { ...l, subscribed: enabled } : l)));
    try {
      await api.post('/matchday-reminders/league/toggle', { user_id: userId, league_id: leagueId, enabled });
    } catch (error) { handleAppRecoverableError({ scope: 'src/components/admin/MatchdayRemindersOpsPanel.tsx#catch2', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
  }, [userId]);

  const subscribedCount = useMemo(() => leagues.filter((l) => l.subscribed).length, [leagues]);

  if (loading) {
    return (
      <View style={{ alignItems: 'center', justifyContent: 'center', padding: 28 }} data-testid="ops-matchday-reminders-loading" testID="ops-matchday-reminders-loading">
        <ActivityIndicator color={colors.primary} />
      </View>
    );
  }

  return (
    <ScrollView style={{ flex: 1 }} contentContainerStyle={{ gap: 10, paddingBottom: 16 }} data-testid="ops-matchday-reminders-panel" testID="ops-matchday-reminders-panel">
      <View style={{ borderWidth: 1, borderColor: colors.border, borderRadius: 12, padding: 12, backgroundColor: colors.card }}>
        <Text style={{ color: colors.text, fontSize: 16, fontWeight: '800' }}>Matchday Reminders</Text>
        <Text style={{ color: colors.textSec, marginTop: 4 }}>Reminder automation controls and league subscriptions.</Text>
      </View>

      <View style={{ borderWidth: 1, borderColor: colors.border, borderRadius: 12, padding: 12, backgroundColor: colors.card }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
          <Text style={{ color: colors.text, fontWeight: '800' }}>Enable reminders</Text>
          <Switch
            value={prefs?.global_enabled ?? true}
            onValueChange={(value) => {
              void updatePref('global_enabled', value);
            }}
            trackColor={{ false: colors.border, true: '#0F766E60' }}
            thumbColor={prefs?.global_enabled ? colors.primary : colors.textMuted}
          />
        </View>
        <Text style={{ color: colors.textSec, marginTop: 6 }}>Subscribed leagues: {subscribedCount}/{leagues.length}</Text>
      </View>

      <View style={{ borderWidth: 1, borderColor: colors.border, borderRadius: 12, padding: 12, backgroundColor: colors.card }}>
        <Text style={{ color: colors.text, fontWeight: '800', marginBottom: 8 }}>League Subscriptions</Text>
        {leagues.slice(0, 20).map((league) => (
          <TouchableOpacity accessibilityLabel="Toggle league in matchday reminders ops panel"
            key={league.id}
            onPress={() => {
              void toggleLeague(league.id, !league.subscribed);
            }}
            style={{
              flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
              borderTopWidth: 1, borderTopColor: colors.border, paddingVertical: 8,
            }}
            data-testid={`ops-matchday-league-${league.id}`}
            testID={`ops-matchday-league-${league.id}`}
          >
            <View>
              <Text style={{ color: colors.text, fontWeight: '600' }}>{league.name}</Text>
              <Text style={{ color: colors.textMuted, fontSize: 11 }}>{league.country}</Text>
            </View>
            <Text style={{ color: league.subscribed ? colors.primary : colors.textMuted, fontSize: 12, fontWeight: '700' }}>
              {league.subscribed ? 'ON' : 'OFF'}
            </Text>
          </TouchableOpacity>
        ))}
      </View>
    </ScrollView>
  );
};
