import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { View, Text, TouchableOpacity, ScrollView, TextInput, ActivityIndicator } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useTheme } from '../context/ThemeContext';
import { useAuth } from '../context/AuthContext';
import FeatureLayout from '../components/FeatureLayout';
import api from '../services/api';

type LearningTab = 'curricula' | 'profile' | 'progress' | 'streaks';

const TABS: Array<{ id: LearningTab; label: string; icon: keyof typeof Ionicons.glyphMap }> = [
  { id: 'curricula', label: 'Curricula', icon: 'library-outline' },
  { id: 'profile', label: 'Profile', icon: 'person-outline' },
  { id: 'progress', label: 'Progress', icon: 'analytics-outline' },
  { id: 'streaks', label: 'Streaks', icon: 'flame-outline' },
];

const CARD = (colors: any) => ({
  backgroundColor: colors.card,
  borderRadius: 14,
  borderWidth: 1,
  borderColor: colors.border,
  padding: 14,
  marginBottom: 12,
});

export default function SchoolTutorView() {
  const { colors, accentColor } = useTheme();
  const { user } = useAuth();
  const [activeTab, setActiveTab] = useState<LearningTab>('curricula');
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [bootstrap, setBootstrap] = useState<any>(null);
  const [curricula, setCurricula] = useState<any[]>([]);
  const [selectedCurriculumId, setSelectedCurriculumId] = useState('');
  const [progressSummary, setProgressSummary] = useState<any>(null);
  const [profile, setProfile] = useState<any>(null);

  const [subject, setSubject] = useState('Mathematics');
  const [goal, setGoal] = useState('Master algebra fundamentals');
  const [pace, setPace] = useState('moderate');

  const [learningStyle, setLearningStyle] = useState('visual');
  const [currentLevel, setCurrentLevel] = useState('beginner');
  const [weeklyHours, setWeeklyHours] = useState('5');

  const fallbackUserId = useMemo(
    () => user?.user_id || `user_${Math.random().toString(36).slice(2)}${Date.now().toString(36)}`.slice(0, 78),
    [user?.user_id],
  );

  const fetchBootstrap = useCallback(async () => {
    const res = await api.get('/learning-coach/bootstrap', { params: { fallback_user_id: fallbackUserId } });
    const data = res.data || {};
    setBootstrap(data);
    const list = Array.isArray(data.curricula) ? data.curricula : [];
    setCurricula(list);
    if (!selectedCurriculumId && list.length > 0) {
      setSelectedCurriculumId(list[0].curriculum_id);
    }
  }, [fallbackUserId, selectedCurriculumId]);

  const fetchProfile = useCallback(async () => {
    const res = await api.get('/learning-coach/profile', { params: { fallback_user_id: fallbackUserId } });
    const payload = res.data || {};
    if (payload.has_profile && payload.profile) {
      setProfile(payload.profile);
      setLearningStyle(payload.profile.learning_style || 'visual');
      setCurrentLevel(payload.profile.current_level || 'beginner');
      setWeeklyHours(String(payload.profile.available_time_weekly || 5));
    }
  }, [fallbackUserId]);

  const fetchProgress = useCallback(async () => {
    if (!selectedCurriculumId) {
      setProgressSummary(null);
      return;
    }
    const res = await api.get(`/learning-coach/progress/${selectedCurriculumId}`, {
      params: { fallback_user_id: fallbackUserId },
    });
    setProgressSummary(res.data || null);
  }, [fallbackUserId, selectedCurriculumId]);

  const loadAll = useCallback(async () => {
    setLoading(true);
    try {
      await Promise.all([fetchBootstrap(), fetchProfile()]);
    } finally {
      setLoading(false);
    }
  }, [fetchBootstrap, fetchProfile]);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  useEffect(() => {
    if (activeTab === 'progress') {
      fetchProgress();
    }
  }, [activeTab, fetchProgress]);

  const createCurriculum = async () => {
    setBusy(true);
    try {
      await api.post('/learning-coach/curricula', {
        fallback_user_id: fallbackUserId,
        subject,
        goal,
        pace,
      });
      await fetchBootstrap();
      setActiveTab('curricula');
    } finally {
      setBusy(false);
    }
  };

  const saveProfile = async () => {
    setBusy(true);
    try {
      await api.post('/learning-coach/profile', {
        fallback_user_id: fallbackUserId,
        learning_style: learningStyle,
        current_level: currentLevel,
        available_time_weekly: Number(weeklyHours) || 5,
        goals: [goal],
      });
      await fetchProfile();
    } finally {
      setBusy(false);
    }
  };

  const streak = Number(bootstrap?.streak || 0);

  return (
    <FeatureLayout
      feature="school-tutor"
      title="Learning Coach"
      subtitle="Adaptive curricula, learner profile, progress insights, and streak momentum"
      icon="school"
      color={accentColor}
    >
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8, padding: 12 }} data-testid="learning-coach-tabs" testID="learning-coach-tabs">
        {TABS.map((tab) => (
          <TouchableOpacity
            key={tab.id}
            onPress={() => setActiveTab(tab.id)}
            style={{
              flexDirection: 'row',
              alignItems: 'center',
              gap: 6,
              backgroundColor: activeTab === tab.id ? accentColor : colors.card,
              borderColor: activeTab === tab.id ? accentColor : colors.border,
              borderWidth: 1,
              borderRadius: 20,
              paddingHorizontal: 12,
              paddingVertical: 8,
            }}
            data-testid={`learning-coach-tab-${tab.id}`}
            testID={`learning-coach-tab-${tab.id}`}
          >
            <Ionicons name={tab.icon} size={14} color={activeTab === tab.id ? colors.primaryText : colors.textSec} />
            <Text style={{ color: activeTab === tab.id ? colors.primaryText : colors.textSec, fontWeight: '700', fontSize: 12 }}>
              {tab.label}
            </Text>
          </TouchableOpacity>
        ))}
      </View>

      {loading ? (
        <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center', gap: 10 }}>
          <ActivityIndicator size="large" color={accentColor} data-testid="learning-coach-loading" testID="learning-coach-loading" />
          <Text style={{ color: colors.textSec }} data-testid="learning-coach-loading-text" testID="learning-coach-loading-text">
            Loading Learning Coach...
          </Text>
        </View>
      ) : (
        <ScrollView style={{ flex: 1 }} contentContainerStyle={{ padding: 12, paddingBottom: 36 }}>
          <View style={CARD(colors)} data-testid="learning-coach-summary-card" testID="learning-coach-summary-card">
            <Text style={{ color: colors.text, fontWeight: '800', fontSize: 18 }} data-testid="learning-coach-tier-title" testID="learning-coach-tier-title">
              {String(bootstrap?.tier || 'free').toUpperCase()} Plan
            </Text>
            <Text style={{ color: colors.textSec, marginTop: 4 }} data-testid="learning-coach-usage-text" testID="learning-coach-usage-text">
              Curricula this month: {bootstrap?.usage?.curricula_this_month ?? 0} / {String(bootstrap?.usage?.monthly_limit ?? '-')} • Lessons today: {bootstrap?.usage?.lessons_today ?? 0}
            </Text>
          </View>

          {activeTab === 'curricula' && (
            <View data-testid="learning-coach-curricula-panel" testID="learning-coach-curricula-panel">
              <View style={CARD(colors)}>
                <Text style={{ color: colors.text, fontSize: 16, fontWeight: '800', marginBottom: 10 }} data-testid="learning-coach-create-curriculum-title" testID="learning-coach-create-curriculum-title">
                  Create Curriculum
                </Text>
                <TextInput
                  value={subject}
                  onChangeText={setSubject}
                  placeholder="Subject (e.g. Mathematics)"
                  placeholderTextColor={colors.textMuted}
                  style={{ backgroundColor: colors.bgSecondary, borderRadius: 10, borderWidth: 1, borderColor: colors.border, color: colors.text, padding: 10, marginBottom: 8 }}
                  data-testid="learning-coach-subject-input"
                  testID="learning-coach-subject-input"
                />
                <TextInput
                  value={goal}
                  onChangeText={setGoal}
                  placeholder="Learning goal"
                  placeholderTextColor={colors.textMuted}
                  style={{ backgroundColor: colors.bgSecondary, borderRadius: 10, borderWidth: 1, borderColor: colors.border, color: colors.text, padding: 10, marginBottom: 8 }}
                  data-testid="learning-coach-goal-input"
                  testID="learning-coach-goal-input"
                />
                <TextInput
                  value={pace}
                  onChangeText={setPace}
                  placeholder="Pace (slow/moderate/fast)"
                  placeholderTextColor={colors.textMuted}
                  style={{ backgroundColor: colors.bgSecondary, borderRadius: 10, borderWidth: 1, borderColor: colors.border, color: colors.text, padding: 10, marginBottom: 12 }}
                  data-testid="learning-coach-pace-input"
                  testID="learning-coach-pace-input"
                />
                <TouchableOpacity
                  onPress={createCurriculum}
                  disabled={busy}
                  style={{ backgroundColor: accentColor, borderRadius: 10, paddingVertical: 11, alignItems: 'center', opacity: busy ? 0.6 : 1 }}
                  data-testid="learning-coach-create-curriculum-button"
                  testID="learning-coach-create-curriculum-button"
                >
                  <Text style={{ color: colors.primaryText, fontWeight: '800' }}>{busy ? 'Creating...' : 'Create Curriculum'}</Text>
                </TouchableOpacity>
              </View>

              <Text style={{ color: colors.text, fontWeight: '800', marginBottom: 8 }} data-testid="learning-coach-curricula-list-title" testID="learning-coach-curricula-list-title">
                Your Curricula
              </Text>
              {curricula.length === 0 ? (
                <View style={CARD(colors)} data-testid="learning-coach-curricula-empty" testID="learning-coach-curricula-empty">
                  <Text style={{ color: colors.textSec }}>No curricula yet. Create your first path above.</Text>
                </View>
              ) : (
                curricula.map((item) => (
                  <TouchableOpacity
                    key={item.curriculum_id}
                    onPress={() => {
                      setSelectedCurriculumId(item.curriculum_id);
                      setActiveTab('progress');
                    }}
                    style={CARD(colors)}
                    data-testid={`learning-coach-curriculum-card-${item.curriculum_id}`}
                    testID={`learning-coach-curriculum-card-${item.curriculum_id}`}
                  >
                    <Text style={{ color: colors.text, fontWeight: '700' }}>{item.title || item.subject || 'Curriculum'}</Text>
                    <Text style={{ color: colors.textSec, marginTop: 4 }}>Progress: {item?.progress?.completed_lessons?.length || 0} lessons completed</Text>
                  </TouchableOpacity>
                ))
              )}
            </View>
          )}

          {activeTab === 'profile' && (
            <View style={CARD(colors)} data-testid="learning-coach-profile-panel" testID="learning-coach-profile-panel">
              <Text style={{ color: colors.text, fontSize: 16, fontWeight: '800', marginBottom: 10 }} data-testid="learning-coach-profile-title" testID="learning-coach-profile-title">
                Learner Profile
              </Text>
              <TextInput
                value={learningStyle}
                onChangeText={setLearningStyle}
                placeholder="Learning style"
                placeholderTextColor={colors.textMuted}
                style={{ backgroundColor: colors.bgSecondary, borderRadius: 10, borderWidth: 1, borderColor: colors.border, color: colors.text, padding: 10, marginBottom: 8 }}
                data-testid="learning-coach-profile-style-input"
                testID="learning-coach-profile-style-input"
              />
              <TextInput
                value={currentLevel}
                onChangeText={setCurrentLevel}
                placeholder="Current level"
                placeholderTextColor={colors.textMuted}
                style={{ backgroundColor: colors.bgSecondary, borderRadius: 10, borderWidth: 1, borderColor: colors.border, color: colors.text, padding: 10, marginBottom: 8 }}
                data-testid="learning-coach-profile-level-input"
                testID="learning-coach-profile-level-input"
              />
              <TextInput
                value={weeklyHours}
                onChangeText={setWeeklyHours}
                placeholder="Available hours per week"
                placeholderTextColor={colors.textMuted}
                keyboardType="number-pad"
                style={{ backgroundColor: colors.bgSecondary, borderRadius: 10, borderWidth: 1, borderColor: colors.border, color: colors.text, padding: 10, marginBottom: 12 }}
                data-testid="learning-coach-profile-hours-input"
                testID="learning-coach-profile-hours-input"
              />
              <TouchableOpacity
                onPress={saveProfile}
                disabled={busy}
                style={{ backgroundColor: accentColor, borderRadius: 10, paddingVertical: 11, alignItems: 'center', opacity: busy ? 0.6 : 1 }}
                data-testid="learning-coach-profile-save-button"
                testID="learning-coach-profile-save-button"
              >
                <Text style={{ color: colors.primaryText, fontWeight: '800' }}>{busy ? 'Saving...' : 'Save Profile'}</Text>
              </TouchableOpacity>
              {profile && (
                <Text style={{ marginTop: 10, color: colors.textSec }} data-testid="learning-coach-profile-status" testID="learning-coach-profile-status">
                  Profile loaded for {profile.owner_id}
                </Text>
              )}
            </View>
          )}

          {activeTab === 'progress' && (
            <View style={CARD(colors)} data-testid="learning-coach-progress-panel" testID="learning-coach-progress-panel">
              <Text style={{ color: colors.text, fontSize: 16, fontWeight: '800', marginBottom: 10 }} data-testid="learning-coach-progress-title" testID="learning-coach-progress-title">
                Progress
              </Text>
              {!selectedCurriculumId ? (
                <Text style={{ color: colors.textSec }} data-testid="learning-coach-progress-empty" testID="learning-coach-progress-empty">
                  Select or create a curriculum first.
                </Text>
              ) : !progressSummary ? (
                <ActivityIndicator color={accentColor} data-testid="learning-coach-progress-loading" testID="learning-coach-progress-loading" />
              ) : (
                <View>
                  <Text style={{ color: colors.textSec }} data-testid="learning-coach-progress-lessons" testID="learning-coach-progress-lessons">
                    Completed lessons: {progressSummary.completed_lessons || 0}
                  </Text>
                  <Text style={{ color: colors.textSec }} data-testid="learning-coach-progress-time" testID="learning-coach-progress-time">
                    Total time: {progressSummary.total_time_minutes || 0} minutes
                  </Text>
                  <Text style={{ color: colors.textSec }} data-testid="learning-coach-progress-score" testID="learning-coach-progress-score">
                    Average score: {progressSummary.average_score || 0}
                  </Text>
                </View>
              )}
            </View>
          )}

          {activeTab === 'streaks' && (
            <View style={CARD(colors)} data-testid="learning-coach-streaks-panel" testID="learning-coach-streaks-panel">
              <Text style={{ color: colors.text, fontSize: 16, fontWeight: '800', marginBottom: 8 }} data-testid="learning-coach-streaks-title" testID="learning-coach-streaks-title">
                Streaks
              </Text>
              <Text style={{ color: colors.textSec }} data-testid="learning-coach-current-streak" testID="learning-coach-current-streak">
                Current streak: {streak} day{streak === 1 ? '' : 's'}
              </Text>
            </View>
          )}
        </ScrollView>
      )}
    </FeatureLayout>
  );
}
