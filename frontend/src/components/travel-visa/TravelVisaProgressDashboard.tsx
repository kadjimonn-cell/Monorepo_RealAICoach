import React from 'react';
import { View, Text, TouchableOpacity, ScrollView, Platform } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useTheme } from '../../context/ThemeContext';
import { router } from 'expo-router';

interface ProgressDashboardProps {
  userStats: any;
  plan: string;
  onUpgradeClick: () => void;
}

export default function TravelVisaProgressDashboard({ userStats, plan, onUpgradeClick }: ProgressDashboardProps) {
  const { colors } = useTheme();

  const totalXP = Number(userStats?.total_xp || 0);
  const lessonsCompleted = Number(userStats?.lessons_completed || 0);
  const quizzesPassed = Number(userStats?.quizzes_passed || 0);
  const simulationsCompleted = Number(userStats?.simulations_completed || 0);
  const coachingSessions = Number(userStats?.coaching_sessions || 0);
  const streak = Number(userStats?.streak || 0);
  const readinessScore = Number(userStats?.readiness_score || 0);

  // Calculate level from XP (100 XP per level)
  const level = Math.floor(totalXP / 100) + 1;
  const xpToNextLevel = 100 - (totalXP % 100);
  const levelProgress = ((totalXP % 100) / 100) * 100;

  // Achievement badges
  const achievements = [
    { id: 'first-lesson', unlocked: lessonsCompleted >= 1, label: 'First Step', icon: 'footsteps', color: colors.success },
    { id: 'quiz-master', unlocked: quizzesPassed >= 5, label: 'Quiz Master', icon: 'trophy', color: colors.warning },
    { id: 'interview-pro', unlocked: simulationsCompleted >= 5, label: 'Interview Pro', icon: 'star', color: colors.info },
    { id: 'streak-7', unlocked: streak >= 7, label: 'Week Warrior', icon: 'flame', color: colors.error },
  ];

  const unlockedCount = achievements.filter(a => a.unlocked).length;

  return (
    <ScrollView data-testid="tv-v2-progress-root" testID="tv-v2-progress-root" style={{ flex: 1 }} contentContainerStyle={{ padding: 16 }}>
      {/* XP & Level Card */}
      <View data-testid="tv-v2-progress-level-card" testID="tv-v2-progress-level-card" style={{
        padding: 20,
        borderRadius: 16,
        backgroundColor: colors.primary,
        marginBottom: 16,
        ...(Platform.OS === 'web' ? {
          backgroundImage: `linear-gradient(135deg, ${colors.primary} 0%, ${colors.primaryDark || colors.primary} 100%)`,
        } as any : {}),
      }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
          <View>
            <Text style={{ fontSize: 14, fontWeight: '600', color: 'rgba(255,255,255,0.8)', marginBottom: 4 }}>
              Your Level
            </Text>
            <Text style={{ fontSize: 32, fontWeight: '800', color: colors.primaryText }}>
              Level {level}
            </Text>
          </View>
          <View style={{
            width: 60,
            height: 60,
            borderRadius: 30,
            backgroundColor: 'rgba(255,255,255,0.2)',
            alignItems: 'center',
            justifyContent: 'center',
          }}>
            <Ionicons name="trophy" size={28} color={colors.primaryText} />
          </View>
        </View>

        <View style={{ marginBottom: 8 }}>
          <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginBottom: 6 }}>
            <Text style={{ fontSize: 13, fontWeight: '600', color: 'rgba(255,255,255,0.9)' }}>
              {totalXP} XP
            </Text>
            <Text style={{ fontSize: 13, fontWeight: '600', color: 'rgba(255,255,255,0.9)' }}>
              {xpToNextLevel} to Level {level + 1}
            </Text>
          </View>
          <View style={{
            height: 8,
            backgroundColor: 'rgba(255,255,255,0.2)',
            borderRadius: 4,
            overflow: 'hidden',
          }}>
            <View style={{
              width: `${levelProgress}%`,
              height: '100%',
              backgroundColor: colors.primaryText,
              borderRadius: 4,
            }} />
          </View>
        </View>
      </View>

      {/* Streak & Readiness */}
      <View data-testid="tv-v2-progress-streak-readiness" testID="tv-v2-progress-streak-readiness" style={{ flexDirection: 'row', gap: 12, marginBottom: 16 }}>
        <View style={{
          flex: 1,
          padding: 16,
          borderRadius: 14,
          backgroundColor: colors.card,
          borderWidth: 1,
          borderColor: colors.border,
        }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', marginBottom: 8 }}>
            <View style={{
              width: 36,
              height: 36,
              borderRadius: 10,
              backgroundColor: streak >= 7 ? colors.errorSoft : colors.border,
              alignItems: 'center',
              justifyContent: 'center',
              marginRight: 10,
            }}>
              <Ionicons name="flame" size={20} color={streak >= 7 ? colors.error : colors.textMuted} />
            </View>
            <View>
              <Text style={{ fontSize: 24, fontWeight: '800', color: colors.text }}>{streak}</Text>
              <Text style={{ fontSize: 11, color: colors.textMuted, fontWeight: '600' }}>Day Streak</Text>
            </View>
          </View>
          <Text style={{ fontSize: 12, color: colors.textMuted }}>
            {streak === 0 ? 'Start today!' : streak < 7 ? `${7 - streak} more for reward` : 'Amazing! 🔥'}
          </Text>
        </View>

        <View style={{
          flex: 1,
          padding: 16,
          borderRadius: 14,
          backgroundColor: colors.card,
          borderWidth: 1,
          borderColor: colors.border,
        }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', marginBottom: 8 }}>
            <View style={{
              width: 36,
              height: 36,
              borderRadius: 10,
              backgroundColor: readinessScore >= 80 ? colors.successSoft : colors.border,
              alignItems: 'center',
              justifyContent: 'center',
              marginRight: 10,
            }}>
              <Ionicons name="checkmark-circle" size={20} color={readinessScore >= 80 ? colors.success : colors.textMuted} />
            </View>
            <View>
              <Text style={{ fontSize: 24, fontWeight: '800', color: colors.text }}>{readinessScore}%</Text>
              <Text style={{ fontSize: 11, color: colors.textMuted, fontWeight: '600' }}>Readiness</Text>
            </View>
          </View>
          <Text style={{ fontSize: 12, color: colors.textMuted }}>
            {readinessScore < 50 ? 'Keep learning!' : readinessScore < 80 ? 'Almost ready' : 'Visa ready! 🎉'}
          </Text>
        </View>
      </View>

      {/* Stats Grid */}
      <View data-testid="tv-v2-progress-stats-grid" testID="tv-v2-progress-stats-grid" style={{
        padding: 16,
        borderRadius: 14,
        backgroundColor: colors.card,
        borderWidth: 1,
        borderColor: colors.border,
        marginBottom: 16,
      }}>
        <Text style={{ fontSize: 16, fontWeight: '700', color: colors.text, marginBottom: 14 }}>
          Your Progress
        </Text>
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 12 }}>
          {[
            { label: 'Lessons', value: lessonsCompleted, icon: 'book-outline', color: colors.primary },
            { label: 'Quizzes', value: quizzesPassed, icon: 'help-circle-outline', color: colors.info },
            { label: 'Simulations', value: simulationsCompleted, icon: 'videocam-outline', color: colors.warning },
            { label: 'Coaching', value: coachingSessions, icon: 'chatbubble-outline', color: colors.success },
          ].map((stat) => (
            <View key={stat.label} style={{
              flex: 1,
              minWidth: '45%',
              padding: 14,
              borderRadius: 12,
              backgroundColor: colors.background,
            }}>
              <View style={{ flexDirection: 'row', alignItems: 'center', marginBottom: 6 }}>
                <Ionicons name={stat.icon as any} size={18} color={stat.color} style={{ marginRight: 6 }} />
                <Text style={{ fontSize: 20, fontWeight: '800', color: colors.text }}>{stat.value}</Text>
              </View>
              <Text style={{ fontSize: 12, color: colors.textMuted, fontWeight: '500' }}>{stat.label}</Text>
            </View>
          ))}
        </View>
      </View>

      {/* Achievements */}
      <View data-testid="tv-v2-progress-achievements" testID="tv-v2-progress-achievements" style={{
        padding: 16,
        borderRadius: 14,
        backgroundColor: colors.card,
        borderWidth: 1,
        borderColor: colors.border,
        marginBottom: 16,
      }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14 }}>
          <Text style={{ fontSize: 16, fontWeight: '700', color: colors.text }}>
            Achievements
          </Text>
          <Text style={{ fontSize: 13, fontWeight: '600', color: colors.textMuted }}>
            {unlockedCount}/{achievements.length}
          </Text>
        </View>
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10 }}>
          {achievements.map((achievement) => (
            <View key={achievement.id} style={{
              padding: 12,
              borderRadius: 12,
              backgroundColor: achievement.unlocked ? achievement.color + '15' : colors.border,
              borderWidth: 2,
              borderColor: achievement.unlocked ? achievement.color : 'transparent',
              alignItems: 'center',
              minWidth: '22%',
              opacity: achievement.unlocked ? 1 : 0.4,
            }}>
              <Ionicons 
                name={achievement.icon as any} 
                size={24} 
                color={achievement.unlocked ? achievement.color : colors.textMuted} 
              />
              <Text style={{
                fontSize: 10,
                fontWeight: '600',
                color: achievement.unlocked ? achievement.color : colors.textMuted,
                marginTop: 6,
                textAlign: 'center',
              }}>
                {achievement.label}
              </Text>
            </View>
          ))}
        </View>
      </View>

      {/* Upgrade CTA (for Free/Basic users) */}
      {plan !== 'premium' && (
        <TouchableOpacity
          data-testid="tv-v2-progress-upgrade-cta"
          testID="tv-v2-progress-upgrade-cta"
          onPress={onUpgradeClick}
          style={{
            padding: 18,
            borderRadius: 14,
            backgroundColor: colors.primary,
            flexDirection: 'row',
            alignItems: 'center',
            justifyContent: 'space-between',
            marginBottom: 16,
          }}
        >
          <View style={{ flex: 1 }}>
            <Text style={{ fontSize: 16, fontWeight: '700', color: colors.primaryText, marginBottom: 4 }}>
              Unlock Premium Features
            </Text>
            <Text style={{ fontSize: 13, color: 'rgba(255,255,255,0.8)' }}>
              Unlimited lessons, quizzes, and AI coaching
            </Text>
          </View>
          <View style={{
            width: 40,
            height: 40,
            borderRadius: 12,
            backgroundColor: 'rgba(255,255,255,0.2)',
            alignItems: 'center',
            justifyContent: 'center',
          }}>
            <Ionicons name="arrow-forward" size={20} color={colors.primaryText} />
          </View>
        </TouchableOpacity>
      )}
    </ScrollView>
  );
}
