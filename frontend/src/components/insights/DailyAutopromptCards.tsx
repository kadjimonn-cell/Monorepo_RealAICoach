import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Platform, Text, TouchableOpacity, View } from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { Ionicons } from '@expo/vector-icons';

type AutopromptCard = {
  id: string;
  title: string;
  description: string;
  ctaLabel: string;
  onPress?: () => void;
  icon?: string;
};

type DailyAutopromptCardsProps = {
  title: string;
  subtitle: string;
  prompts: AutopromptCard[];
  colors: any;
  testIdPrefix: string;
};

export const DailyAutopromptCards = ({
  title,
  subtitle,
  prompts,
  colors,
  testIdPrefix,
}: DailyAutopromptCardsProps) => {
  const [completedMap, setCompletedMap] = useState<Record<string, boolean>>({});
  const [streakDays, setStreakDays] = useState(0);

  const todayKey = useMemo(() => {
    const now = new Date();
    return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`;
  }, []);

  const storageKey = useMemo(() => `daily_autoprompt_completed:${testIdPrefix}:${todayKey}`, [testIdPrefix, todayKey]);
  const keyPrefix = useMemo(() => `daily_autoprompt_completed:${testIdPrefix}:`, [testIdPrefix]);

  const formatDate = useCallback((date: Date) => {
    const yyyy = date.getFullYear();
    const mm = String(date.getMonth() + 1).padStart(2, '0');
    const dd = String(date.getDate()).padStart(2, '0');
    return `${yyyy}-${mm}-${dd}`;
  }, []);

  const persistCompletionState = useCallback(async (value: Record<string, boolean>) => {
    const serialized = JSON.stringify(value);
    if (Platform.OS === 'web' && typeof window !== 'undefined') {
      window.localStorage.setItem(storageKey, serialized);
      return;
    }
    await AsyncStorage.setItem(storageKey, serialized);
  }, [storageKey]);

  const recomputeStreak = useCallback(async (todaySnapshot?: Record<string, boolean>) => {
    try {
      const activeDates = new Set<string>();

      if (Platform.OS === 'web' && typeof window !== 'undefined') {
        for (let i = 0; i < window.localStorage.length; i += 1) {
          const key = window.localStorage.key(i);
          if (!key || !key.startsWith(keyPrefix)) continue;
          const raw = window.localStorage.getItem(key);
          if (!raw) continue;
          const parsed = JSON.parse(raw) as Record<string, boolean>;
          const hasCompletion = Object.values(parsed || {}).some(Boolean);
          if (!hasCompletion) continue;
          const datePart = key.replace(keyPrefix, '');
          activeDates.add(datePart);
        }
      } else {
        const allKeys = await AsyncStorage.getAllKeys();
        const matchedKeys = allKeys.filter((key) => key.startsWith(keyPrefix));
        if (matchedKeys.length > 0) {
          const pairs = await AsyncStorage.multiGet(matchedKeys);
          pairs.forEach(([key, raw]) => {
            if (!raw) return;
            const parsed = JSON.parse(raw) as Record<string, boolean>;
            const hasCompletion = Object.values(parsed || {}).some(Boolean);
            if (!hasCompletion) return;
            const datePart = key.replace(keyPrefix, '');
            activeDates.add(datePart);
          });
        }
      }

      if (todaySnapshot && Object.values(todaySnapshot).some(Boolean)) {
        activeDates.add(todayKey);
      }

      let streak = 0;
      const cursor = new Date(todayKey);
      while (activeDates.has(formatDate(cursor))) {
        streak += 1;
        cursor.setDate(cursor.getDate() - 1);
      }

      setStreakDays(streak);
    } catch {
      setStreakDays(0);
    }
  }, [formatDate, keyPrefix, todayKey]);

  useEffect(() => {
    let mounted = true;

    const loadCompletionState = async () => {
      try {
        const serialized = Platform.OS === 'web' && typeof window !== 'undefined'
          ? window.localStorage.getItem(storageKey)
          : await AsyncStorage.getItem(storageKey);

        if (!serialized) return;
        const parsed = JSON.parse(serialized);
        if (mounted && parsed && typeof parsed === 'object') {
          setCompletedMap(parsed as Record<string, boolean>);
          await recomputeStreak(parsed as Record<string, boolean>);
          return;
        }

        await recomputeStreak({});
      } catch {
        return;
      }
    };

    void loadCompletionState();

    return () => {
      mounted = false;
    };
  }, [storageKey, recomputeStreak]);

  const handlePromptPress = useCallback((prompt: AutopromptCard) => {
    if (typeof prompt.onPress === 'function') {
      prompt.onPress();
    }

    setCompletedMap((prev) => {
      const next = { ...prev, [prompt.id]: true };
      void persistCompletionState(next);
      void recomputeStreak(next);
      return next;
    });
  }, [persistCompletionState, recomputeStreak]);

  // Early return AFTER all hooks are called (React hooks rules compliance)
  if (!Array.isArray(prompts) || prompts.length === 0) return null;

  const textMuted = colors.textMuted || colors.muted || colors.textSec || colors.text;
  const bgSoft = colors.bgSoft || colors.surface || colors.card;
  const success = colors.successText || colors.success || colors.primary;
  const completedTodayCount = prompts.filter((prompt) => Boolean(completedMap[prompt.id])).length;

  return (
    <View
      style={{
        borderRadius: 14,
        borderWidth: 1,
        borderColor: colors.border,
        backgroundColor: colors.card,
        padding: 12,
        gap: 10,
      }}
      data-testid={`${testIdPrefix}-container`}
      testID={`${testIdPrefix}-container`}
    >
      <View style={{ gap: 6 }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
          <Text
            style={{ fontSize: 13, fontWeight: '800', color: colors.text, flex: 1 }}
            data-testid={`${testIdPrefix}-title`}
            testID={`${testIdPrefix}-title`}
          >
            {title}
          </Text>
          <View
            style={{
              borderRadius: 999,
              borderWidth: 1,
              borderColor: `${success}66`,
              backgroundColor: `${success}18`,
              paddingHorizontal: 10,
              paddingVertical: 5,
            }}
            data-testid={`${testIdPrefix}-streak-badge`}
            testID={`${testIdPrefix}-streak-badge`}
          >
            <Text style={{ fontSize: 10, fontWeight: '800', color: success }}>{`Streak ${streakDays}d`}</Text>
          </View>
        </View>

        <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
          <Text
            style={{ fontSize: 11, color: textMuted, flex: 1 }}
            data-testid={`${testIdPrefix}-subtitle`}
            testID={`${testIdPrefix}-subtitle`}
          >
            {subtitle}
          </Text>
          <Text
            style={{ fontSize: 10, fontWeight: '700', color: colors.text }}
            data-testid={`${testIdPrefix}-daily-progress`}
            testID={`${testIdPrefix}-daily-progress`}
          >
            {`${completedTodayCount}/${prompts.length} completed today`}
          </Text>
        </View>
      </View>

      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }} data-testid={`${testIdPrefix}-cards`} testID={`${testIdPrefix}-cards`}>
        {prompts.map((prompt) => {
          const iconName = (prompt.icon || 'sparkles-outline') as any;
          const completedToday = Boolean(completedMap[prompt.id]);
          const disabled = typeof prompt.onPress !== 'function';

          return (
            <View
              key={prompt.id}
              style={{
                minWidth: 220,
                flexGrow: 1,
                borderRadius: 12,
                borderWidth: 1,
                borderColor: colors.border,
                backgroundColor: bgSoft,
                padding: 11,
                gap: 8,
              }}
              data-testid={`${testIdPrefix}-card-${prompt.id}`}
              testID={`${testIdPrefix}-card-${prompt.id}`}
            >
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                <Ionicons name={iconName} size={14} color={success} />
                <Text
                  style={{ fontSize: 11, fontWeight: '800', color: colors.text }}
                  data-testid={`${testIdPrefix}-card-${prompt.id}-title`}
                  testID={`${testIdPrefix}-card-${prompt.id}-title`}
                >
                  {prompt.title}
                </Text>
                {completedToday && (
                  <View
                    style={{
                      marginLeft: 'auto',
                      borderRadius: 999,
                      paddingHorizontal: 8,
                      paddingVertical: 3,
                      backgroundColor: `${success}20`,
                      borderWidth: 1,
                      borderColor: `${success}66`,
                    }}
                    data-testid={`${testIdPrefix}-card-${prompt.id}-completed-badge`}
                    testID={`${testIdPrefix}-card-${prompt.id}-completed-badge`}
                  >
                    <Text style={{ fontSize: 9, color: success, fontWeight: '800' }}>Done today</Text>
                  </View>
                )}
              </View>

              <Text
                style={{ fontSize: 11, color: textMuted, lineHeight: 18 }}
                data-testid={`${testIdPrefix}-card-${prompt.id}-description`}
                testID={`${testIdPrefix}-card-${prompt.id}-description`}
              >
                {prompt.description}
              </Text>

              <TouchableOpacity accessibilityLabel="Prompt press in daily autoprompt cards button"
                onPress={() => handlePromptPress(prompt)}
                disabled={disabled}
                style={{
                  alignSelf: 'flex-start',
                  borderRadius: 999,
                  borderWidth: 1,
                  borderColor: disabled ? colors.border : completedToday ? `${success}88` : `${colors.primary}88`,
                  backgroundColor: disabled ? colors.card : completedToday ? `${success}16` : `${colors.primary}16`,
                  paddingHorizontal: 10,
                  paddingVertical: 6,
                  opacity: disabled ? 0.75 : 1,
                }}
                data-testid={`${testIdPrefix}-card-${prompt.id}-button`}
                testID={`${testIdPrefix}-card-${prompt.id}-button`}
              >
                <Text style={{ fontSize: 10, fontWeight: '800', color: disabled ? textMuted : completedToday ? success : colors.primary }}>
                  {completedToday ? 'Completed today' : prompt.ctaLabel}
                </Text>
              </TouchableOpacity>
            </View>
          );
        })}
      </View>
    </View>
  );
};

/* i18n-probe t('i18n.auto.probe') */
