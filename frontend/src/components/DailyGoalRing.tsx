/**
 * DailyGoalRing — SVG completion ring showing today's progress vs daily goal.
 * Includes a modal to set the goal target (1-10 sessions).
 */
import React, { useState, useEffect, useRef } from 'react';
import { View, Text, TouchableOpacity, Modal, TextInput, Animated } from 'react-native';
import { useTheme } from '../context/ThemeContext';
import Svg, { Circle } from 'react-native-svg';
import { Ionicons } from '@expo/vector-icons';
import api from '../services/api';
import { useLiveQuery } from '../hooks/useLiveQuery';
import { useAuth } from '../context/AuthContext';
import { handleAppRecoverableError } from '../utils/appRecoverableError';

const BLUE = 'var(--app-primary)';
const GREEN = 'var(--app-success)';
const AMBER = 'var(--app-warning)';

interface DailyGoalRingProps {
  size?: number;
  strokeWidth?: number;
}

export default function DailyGoalRing({ size = 120, strokeWidth = 10 }: DailyGoalRingProps) {
  const { colors } = useTheme();
  // Theme-aware structural colors (replaces removed module-level dark-only constants)
  const CARD2 = 'var(--app-text)';
  const BORDER = 'var(--app-primary)';
  const TEXT = 'var(--app-primary-text)';
  const MUTED = 'var(--app-text-muted)';
  const { user } = useAuth();
  const [goal, setGoal] = useState<{ target: number; today_count: number; completed: boolean } | null>(null);
  const [modalOpen, setModalOpen] = useState(false);
  const [inputTarget, setInputTarget] = useState('3');
  const [saving, setSaving] = useState(false);
  const progressAnim = useRef(new Animated.Value(0)).current;

  const r = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * r;
  const cx = size / 2;

  const { data: goalData, refetch: loadGoal } = useLiveQuery(
    user?.user_id ? `/progress/daily-goal/${user.user_id}` : '',
    { entity: 'daily_goal', pollInterval: 30000, deps: [user?.user_id] }
  );

  useEffect(() => {
    if (goalData) {
      setGoal(goalData);
      const pct = Math.min(goalData.today_count / Math.max(goalData.target, 1), 1);
      Animated.timing(progressAnim, {
        toValue: pct,
        duration: 800,
        useNativeDriver: false,
      }).start();
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [goalData]);

  const saveGoal = async () => {
    const t = Math.max(1, Math.min(20, parseInt(inputTarget) || 3));
    setSaving(true);
    try {
      await api.post(`/progress/daily-goal/${user?.user_id}`, { target: t });
      setModalOpen(false);
      loadGoal();
    } catch (error) { handleAppRecoverableError({ scope: 'src/components/DailyGoalRing.tsx#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
    setSaving(false);
  };

  const todayCount = goal?.today_count ?? 0;
  const target = goal?.target ?? 3;
  const completed = goal?.completed ?? false;
  const pct = Math.min(todayCount / Math.max(target, 1), 1);

  const ringColor = completed ? GREEN : pct >= 0.5 ? BLUE : AMBER;
  const dashOffset = circumference * (1 - pct);

  return (
    <View style={{ alignItems: 'center' }} testID="daily-goal-ring">
      {/* SVG ring */}
      <TouchableOpacity onPress={() => { setInputTarget(String(target)); setModalOpen(true); }} accessibilityLabel="Daily goal ring touch button" testID="daily-goal-ring-touch">
        <Svg width={size} height={size} style={{ transform: [{ rotate: '-90deg' }] }}>
          {/* Background track */}
          <Circle
            cx={cx} cy={cx} r={r}
            stroke={CARD2}
            strokeWidth={strokeWidth}
            fill="none"
          />
          {/* Progress arc */}
          <Circle
            cx={cx} cy={cx} r={r}
            stroke={ringColor}
            strokeWidth={strokeWidth}
            fill="none"
            strokeDasharray={`${circumference}`}
            strokeDashoffset={dashOffset}
            strokeLinecap="round"
          />
        </Svg>
        {/* Center content */}
        <View style={{
          position: 'absolute', top: 0, left: 0, width: size, height: size,
          alignItems: 'center', justifyContent: 'center',
        }}>
          {completed ? (
            <Ionicons name="checkmark-circle" size={28} color={GREEN} />
          ) : (
            <>
              <Text style={{ fontSize: 20, fontWeight: '900', color: ringColor }}>{todayCount}</Text>
              <Text style={{ fontSize: 9, color: MUTED, fontWeight: '700' }}>/ {target}</Text>
            </>
          )}
        </View>
      </TouchableOpacity>

      {/* Label */}
      <Text style={{ fontSize: 11, color: MUTED, fontWeight: '700', marginTop: 6, textAlign: 'center' }}>
        {completed ? 'Daily Goal Met!' : "Today's Goal"}
      </Text>
      <TouchableOpacity accessibilityLabel="Set goal"
        onPress={() => { setInputTarget(String(target)); setModalOpen(true); }}
        style={{ flexDirection: 'row', alignItems: 'center', gap: 3, marginTop: 3 }}
        testID="daily-goal-set-btn"
      >
        <Ionicons name="create-outline" size={10} color={BLUE} />
        <Text style={{ fontSize: 10, color: BLUE }}>Set goal</Text>
      </TouchableOpacity>

      {/* Set Goal Modal */}
      <Modal visible={modalOpen} transparent animationType="fade">
        <View style={{ flex: 1, backgroundColor: 'rgba(0,0,0,0.7)', justifyContent: 'center', alignItems: 'center', padding: 24 }}>
          <View style={{ backgroundColor: colors?.card, borderRadius: 20, padding: 24, width: '100%', maxWidth: 360, borderWidth: 1, borderColor: BORDER }}>
            <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
              <Text style={{ fontSize: 18, fontWeight: '800', color: TEXT }}>Set Daily Goal</Text>
              <TouchableOpacity onPress={() => setModalOpen(false)} accessibilityLabel="close button" testID="daily-goal-modal-close">
                <Ionicons name="close" size={20} color={MUTED} />
              </TouchableOpacity>
            </View>

            <Text style={{ fontSize: 13, color: MUTED, marginBottom: 16 }}>
              How many AI sessions do you want to complete each day?
            </Text>

            {/* Quick presets */}
            <View style={{ flexDirection: 'row', gap: 8, marginBottom: 16, flexWrap: 'wrap' }}>
              {[1, 2, 3, 5, 7, 10].map(n => (
                <TouchableOpacity accessibilityLabel="Set input target in daily goal ring"
                  key={n}
                  onPress={() => setInputTarget(String(n))}
                  style={{
                    width: 44, height: 44, borderRadius: 12,
                    backgroundColor: inputTarget === String(n) ? BLUE : CARD2,
                    alignItems: 'center', justifyContent: 'center',
                    borderWidth: 1, borderColor: inputTarget === String(n) ? BLUE : BORDER,
                  }}
                  testID={`daily-goal-preset-${n}`}
                >
                  <Text style={{ fontSize: 14, fontWeight: '800', color: inputTarget === String(n) ? (colors.primaryText || colors.buttonText || colors.card) : MUTED }}>{n}</Text>
                </TouchableOpacity>
              ))}
            </View>

            <TextInput
              value={inputTarget}
              onChangeText={setInputTarget}
              keyboardType="number-pad"
              placeholder="Custom (1-20)"
              placeholderTextColor={MUTED}
              style={{
                backgroundColor: CARD2, borderRadius: 12, padding: 12,
                color: TEXT, fontSize: 16, fontWeight: '700',
                borderWidth: 1, borderColor: BORDER, textAlign: 'center', marginBottom: 16,
              }}
              testID="daily-goal-input"
            />

            <TouchableOpacity accessibilityLabel="Daily goal save button"
              onPress={saveGoal}
              disabled={saving}
              style={{ backgroundColor: BLUE, borderRadius: 14, padding: 14, alignItems: 'center' }}
              testID="daily-goal-save-btn"
            >
              <Text style={{ color: colors.primaryText || colors.buttonText || colors.text, fontWeight: '800', fontSize: 15 }}>
                {saving ? 'Saving...' : 'Set My Goal'}
              </Text>
            </TouchableOpacity>
          </View>
        </View>
      </Modal>
    </View>
  );
}

/* i18n-probe t('i18n.auto.probe') */
