import React, { useState, useEffect } from 'react';
import { View, Text, ScrollView, TouchableOpacity, ActivityIndicator, Alert, TextInput } from 'react-native';
import { Ionicons, FontAwesome5 } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import api from '../../src/services/api';
import FeatureLayout from '../../src/components/FeatureLayout';
import { useTheme } from '../../src/context/ThemeContext';
import { useAuth } from '../../src/context/AuthContext';
import { handleAppRecoverableError } from '../../src/utils/appRecoverableError';
import { useTranslation } from '../../src/hooks/useTranslation';

type Tab = 'plans' | 'progress' | 'exercises' | 'records';

export default function FitnessScreen() {
  const { colors } = useTheme();
  const { user } = useAuth();
  const { t } = useTranslation();
  t('i18n.route.features.fitness.probe');
  const [activeTab, setActiveTab] = useState<Tab>('plans');
  const [loading, setLoading] = useState(true);
  const [usage, setUsage] = useState<any>(null);
  
  // Plans state
  const [workoutPlans, setWorkoutPlans] = useState<any[]>([]);
  const [selectedPlan, setSelectedPlan] = useState<any>(null);
  const [generating, setGenerating] = useState(false);
  
  // Progress state
  const [workoutHistory, setWorkoutHistory] = useState<any[]>([]);
  const [progressMetrics, setProgressMetrics] = useState<any>(null);
  
  // Exercises state
  const [exercises, setExercises] = useState<any[]>([]);
  const [exerciseFilter, setExerciseFilter] = useState('all');
  
  // Personal records
  const [personalRecords, setPersonalRecords] = useState<any[]>([]);
  
  // Create plan form
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [planName, setPlanName] = useState('');
  const [planType, setPlanType] = useState('weekly');
  const [focusAreas, setFocusAreas] = useState<string[]>(['strength']);
  const [difficulty, setDifficulty] = useState('intermediate');
  const [durationWeeks, setDurationWeeks] = useState(4);
  const [sessionMinutes, setSessionMinutes] = useState(45);
  const [equipment, setEquipment] = useState<string[]>(['bodyweight']);
  const [fallbackUserId] = useState(() =>
    user?.user_id || `user_${Math.random().toString(36).slice(2)}${Date.now().toString(36)}`.slice(0, 78)
  );

  useEffect(() => {
    bootstrap();
  }, []);

  useEffect(() => {
    if (activeTab === 'plans') loadWorkoutPlans();
    else if (activeTab === 'progress') loadProgress();
    else if (activeTab === 'exercises') loadExercises();
    else if (activeTab === 'records') loadPersonalRecords();
  }, [activeTab]);

  const bootstrap = async () => {
    try {
      const response = await api.get('/fitness-planner/bootstrap', {
        params: { fallback_user_id: fallbackUserId },
      });
      setUsage(response.data);
      setLoading(false);
    } catch (error) {
      console.error('Bootstrap error:', error);
      setLoading(false);
    }
  };

  const loadWorkoutPlans = async () => {
    try {
      const response = await api.get('/fitness-planner/workout-plans', {
        params: { fallback_user_id: fallbackUserId },
      });
      setWorkoutPlans(response.data.plans || []);
    } catch (error) {
      console.error('Load plans error:', error);
    }
  };

  const createWorkoutPlan = async () => {
    if (!planName.trim()) {
      Alert.alert('Error', 'Please enter a plan name');
      return;
    }

    setGenerating(true);
    try {
      const response = await api.post('/fitness-planner/workout-plans', {
        fallback_user_id: fallbackUserId,
        plan_name: planName,
        plan_type: planType,
        focus_areas: focusAreas,
        difficulty,
        duration_weeks: durationWeeks,
        session_duration_minutes: sessionMinutes,
        equipment_available: equipment,
      });
      
      setWorkoutPlans(prev => [response.data?.plan, ...prev].filter(Boolean));
      setShowCreateModal(false);
      setPlanName('');
      Alert.alert('Success', 'Workout plan created!');
    } catch (error: any) {
      handleAppRecoverableError({
        scope: 'fitness.create-plan',
        error,
        message: error.response?.data?.detail || 'Failed to create plan',
      
        notifyMode: 'silent',
      });
    } finally {
      setGenerating(false);
    }
  };

  const deletePlan = async (planId: string) => {
    try {
      await api.delete(`/fitness-planner/workout-plans/${planId}`, {
        params: { fallback_user_id: fallbackUserId },
      });
      setWorkoutPlans(prev => prev.filter(p => p.plan_id !== planId));
      if (selectedPlan?.plan_id === planId) setSelectedPlan(null);
      Alert.alert('Success', 'Plan deleted');
    } catch (error) {
      Alert.alert('Error', 'Failed to delete plan');
    }
  };

  const loadProgress = async () => {
    try {
      const [historyRes, analyticsRes] = await Promise.all([
        api.get('/fitness-planner/workouts/history', {
          params: { fallback_user_id: fallbackUserId },
        }),
        api.get('/fitness-planner/progress/analytics', {
          params: { fallback_user_id: fallbackUserId },
        })
      ]);
      setWorkoutHistory(historyRes.data.history || []);
      setProgressMetrics(analyticsRes.data);
    } catch (error) {
      console.error('Load progress error:', error);
    }
  };

  const loadExercises = async () => {
    try {
      const response = await api.get('/fitness-planner/exercises');
      setExercises(response.data.exercises || []);
    } catch (error) {
      console.error('Load exercises error:', error);
    }
  };

  const loadPersonalRecords = async () => {
    try {
      const response = await api.get('/fitness-planner/personal-records', {
        params: { fallback_user_id: fallbackUserId },
      });
      setPersonalRecords(response.data.personal_records || []);
    } catch (error) {
      console.error('Load records error:', error);
    }
  };

  const toggleFocusArea = (area: string) => {
    if (focusAreas.includes(area)) {
      setFocusAreas(focusAreas.filter(a => a !== area));
    } else {
      setFocusAreas([...focusAreas, area]);
    }
  };

  const toggleEquipment = (item: string) => {
    if (equipment.includes(item)) {
      setEquipment(equipment.filter(e => e !== item));
    } else {
      setEquipment([...equipment, item]);
    }
  };

  const filteredExercises = exerciseFilter === 'all' 
    ? exercises 
    : exercises.filter(e => e.category === exerciseFilter);

  if (loading) {
    return (
      <FeatureLayout title="Fitness Planner Pro" subtitle="AI-powered fitness companion">
        <View style={{ flex: 1, justifyContent: 'center', alignItems: 'center' }} data-testid="fitness-loading-view" testID="fitness-loading-view">
          <ActivityIndicator size="large" color={colors.primary} data-testid="fitness-loading-indicator" testID="fitness-loading-indicator" />
        </View>
      </FeatureLayout>
    );
  }

  return (
    <FeatureLayout title="Fitness Planner Pro" subtitle="AI-powered fitness companion">
      {/* Usage Stats */}
      {usage && (
        <View style={{ backgroundColor: colors.card, padding: 16, marginBottom: 16, borderBottomWidth: 1, borderBottomColor: colors.border }} data-testid="fitness-usage-stats" testID="fitness-usage-stats">
          <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
            <View>
              <Text style={{ fontSize: 12, color: colors.textSecondary, marginBottom: 4 }}>Plans This Month</Text>
              <Text style={{ fontSize: 20, fontWeight: '700', color: colors.text }}>
                {usage.usage?.plans_created_this_month || 0} / {usage.tier_limits?.workout_plans_per_month === -1 ? '∞' : usage.tier_limits?.workout_plans_per_month}
              </Text>
            </View>
            <View>
              <Text style={{ fontSize: 12, color: colors.textSecondary, marginBottom: 4 }}>Body Scans</Text>
              <Text style={{ fontSize: 20, fontWeight: '700', color: colors.text }}>
                {usage.usage?.scans_this_month || 0} / {usage.tier_limits?.body_scans_per_month === -1 ? '∞' : usage.tier_limits?.body_scans_per_month}
              </Text>
            </View>
            <View>
              <Text style={{ fontSize: 12, color: colors.textSecondary, marginBottom: 4 }}>Tier</Text>
              <Text style={{ fontSize: 20, fontWeight: '700', color: colors.primary }}>
                {usage.tier?.toUpperCase()}
              </Text>
            </View>
          </View>
        </View>
      )}

      {/* Tabs */}
      <View style={{ flexDirection: 'row', backgroundColor: colors.card, borderBottomWidth: 1, borderBottomColor: colors.border }} data-testid="fitness-tabs" testID="fitness-tabs">
        {(['plans', 'progress', 'exercises', 'records'] as Tab[]).map((tab) => (
          <TouchableOpacity
            key={tab}
            onPress={() => setActiveTab(tab)}
            style={{
              flex: 1,
              paddingVertical: 14,
              borderBottomWidth: 2,
              borderBottomColor: activeTab === tab ? colors.primary : 'transparent',
            }}
            data-testid={`fitness-tab-${tab}`}
            testID={`fitness-tab-${tab}`}
          >
            <Text style={{ textAlign: 'center', fontWeight: '600', color: activeTab === tab ? colors.primary : colors.textSecondary, textTransform: 'capitalize' }}>
              {tab === 'plans' ? 'Workout Plans' : tab === 'records' ? 'PRs' : tab}
            </Text>
          </TouchableOpacity>
        ))}
      </View>

      <ScrollView style={{ flex: 1 }} contentContainerStyle={{ padding: 16 }}>
        {/* WORKOUT PLANS TAB */}
        {activeTab === 'plans' && (
          <View>
            {/* Create Plan Button */}
            {!showCreateModal && (
              <TouchableOpacity
                onPress={() => setShowCreateModal(true)}
                style={{
                  backgroundColor: colors.primary,
                  padding: 16,
                  borderRadius: 12,
                  flexDirection: 'row',
                  alignItems: 'center',
                  justifyContent: 'center',
                  marginBottom: 16,
                }}
                data-testid="fitness-generate-workout-button"
                testID="fitness-generate-workout-button"
              >
                <Ionicons name="add-circle-outline" size={20} color={colors.primaryText} style={{ marginRight: 8 }} />
                <Text style={{ color: colors.primaryText, fontSize: 16, fontWeight: '600' }}>Generate Workout Plan</Text>
              </TouchableOpacity>
            )}

            {/* Create Plan Form */}
            {showCreateModal && (
              <View style={{ backgroundColor: colors.card, borderRadius: 12, padding: 16, marginBottom: 16, borderWidth: 1, borderColor: colors.border }}>
                <Text style={{ fontSize: 18, fontWeight: '700', color: colors.text, marginBottom: 16 }}>
                  Create Workout Plan
                </Text>

                <Text style={{ fontSize: 14, color: colors.textSecondary, marginBottom: 8 }}>Plan Name</Text>
                <TextInput
                  value={planName}
                  onChangeText={setPlanName}
                  placeholder="My Workout Plan"
                  placeholderTextColor={colors.textSecondary}
                  style={{
                    backgroundColor: colors.background,
                    color: colors.text,
                    padding: 12,
                    borderRadius: 8,
                    fontSize: 16,
                    marginBottom: 16,
                    borderWidth: 1,
                    borderColor: colors.border,
                  }}
                  data-testid="fitness-plan-name-input"
                  testID="fitness-plan-name-input"
                />

                <Text style={{ fontSize: 14, color: colors.textSecondary, marginBottom: 8 }}>Focus Areas</Text>
                <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginBottom: 16 }}>
                  {['strength', 'cardio', 'flexibility', 'muscle_gain', 'weight_loss'].map((area) => (
                    <TouchableOpacity
                      key={area}
                      onPress={() => toggleFocusArea(area)}
                      style={{
                        paddingHorizontal: 14,
                        paddingVertical: 8,
                        borderRadius: 8,
                        backgroundColor: focusAreas.includes(area) ? colors.primary : colors.background,
                        borderWidth: 1,
                        borderColor: focusAreas.includes(area) ? colors.primary : colors.border,
                      }}
                      data-testid={`fitness-focus-area-button-${area}`}
                      testID={`fitness-focus-area-button-${area}`}
                    >
                      <Text style={{ fontSize: 12, fontWeight: '600', color: focusAreas.includes(area) ? colors.primaryText : colors.text }}>
                        {area.replace('_', ' ').toUpperCase()}
                      </Text>
                    </TouchableOpacity>
                  ))}
                </View>

                <Text style={{ fontSize: 14, color: colors.textSecondary, marginBottom: 8 }}>Difficulty</Text>
                <View style={{ flexDirection: 'row', gap: 8, marginBottom: 16 }}>
                  {['beginner', 'intermediate', 'advanced'].map((diff) => (
                    <TouchableOpacity
                      key={diff}
                      onPress={() => setDifficulty(diff)}
                      style={{
                        flex: 1,
                        paddingVertical: 10,
                        borderRadius: 8,
                        backgroundColor: difficulty === diff ? colors.primary : colors.background,
                        borderWidth: 1,
                        borderColor: difficulty === diff ? colors.primary : colors.border,
                      }}
                      data-testid={`fitness-difficulty-button-${diff}`}
                      testID={`fitness-difficulty-button-${diff}`}
                    >
                      <Text style={{ textAlign: 'center', fontSize: 12, fontWeight: '600', color: difficulty === diff ? colors.primaryText : colors.text }}>
                        {diff.toUpperCase()}
                      </Text>
                    </TouchableOpacity>
                  ))}
                </View>

                <Text style={{ fontSize: 14, color: colors.textSecondary, marginBottom: 8 }}>Equipment Available</Text>
                <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginBottom: 16 }}>
                  {['bodyweight', 'dumbbells', 'barbell', 'resistance_bands'].map((item) => (
                    <TouchableOpacity
                      key={item}
                      onPress={() => toggleEquipment(item)}
                      style={{
                        paddingHorizontal: 14,
                        paddingVertical: 8,
                        borderRadius: 8,
                        backgroundColor: equipment.includes(item) ? colors.primary : colors.background,
                        borderWidth: 1,
                        borderColor: equipment.includes(item) ? colors.primary : colors.border,
                      }}
                      data-testid={`fitness-equipment-button-${item}`}
                      testID={`fitness-equipment-button-${item}`}
                    >
                      <Text style={{ fontSize: 12, fontWeight: '600', color: equipment.includes(item) ? colors.primaryText : colors.text }}>
                        {item.replace('_', ' ').toUpperCase()}
                      </Text>
                    </TouchableOpacity>
                  ))}
                </View>

                <View style={{ flexDirection: 'row', gap: 12 }}>
                  <TouchableOpacity
                    onPress={() => {
                      setShowCreateModal(false);
                      setPlanName('');
                    }}
                    style={{
                      flex: 1,
                      backgroundColor: colors.background,
                      padding: 14,
                      borderRadius: 8,
                      borderWidth: 1,
                      borderColor: colors.border,
                    }}
                    data-testid="fitness-create-plan-cancel-button"
                    testID="fitness-create-plan-cancel-button"
                  >
                    <Text style={{ textAlign: 'center', color: colors.text, fontWeight: '600' }}>Cancel</Text>
                  </TouchableOpacity>

                  <TouchableOpacity
                    onPress={createWorkoutPlan}
                    disabled={generating}
                    style={{
                      flex: 1,
                      backgroundColor: colors.primary,
                      padding: 14,
                      borderRadius: 8,
                    }}
                    data-testid="fitness-create-plan-submit-button"
                    testID="fitness-create-plan-submit-button"
                  >
                    {generating ? (
                      <ActivityIndicator size="small" color={colors.primaryText} />
                    ) : (
                      <Text style={{ textAlign: 'center', color: colors.primaryText, fontWeight: '600' }}>Create Plan</Text>
                    )}
                  </TouchableOpacity>
                </View>
              </View>
            )}

            {/* Plans List */}
            {workoutPlans.length === 0 ? (
              <View style={{ alignItems: 'center', marginTop: 40 }}>
                <FontAwesome5 name="dumbbell" size={48} color={colors.textSecondary} />
                <Text style={{ fontSize: 16, color: colors.textSecondary, marginTop: 16 }}>
                  No workout plans yet
                </Text>
                <Text style={{ fontSize: 14, color: colors.textSecondary, marginTop: 8 }}>
                  Create your first AI-powered plan above
                </Text>
              </View>
            ) : (
              workoutPlans.map((plan) => (
                <View
                  key={plan.plan_id}
                  style={{
                    backgroundColor: colors.card,
                    borderRadius: 12,
                    padding: 16,
                    marginBottom: 12,
                    borderWidth: 1,
                    borderColor: colors.border,
                  }}
                >
                  <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginBottom: 12 }}>
                    <View style={{ flex: 1 }}>
                      <Text style={{ fontSize: 16, fontWeight: '700', color: colors.text }}>
                        {plan.plan_name || 'Workout Plan'}
                      </Text>
                      <Text style={{ fontSize: 12, color: colors.textSecondary, marginTop: 4 }}>
                        {plan.difficulty} • {plan.duration_weeks} weeks • {plan.session_duration_minutes} min/session
                      </Text>
                    </View>
                    <TouchableOpacity
                      onPress={() => deletePlan(plan.plan_id)}
                      style={{ padding: 8 }}
                      data-testid={`fitness-plan-delete-button-${plan.plan_id}`}
                      testID={`fitness-plan-delete-button-${plan.plan_id}`}
                    >
                      <Ionicons name="trash-outline" size={20} color={colors.error} />
                    </TouchableOpacity>
                  </View>

                  <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginBottom: 12 }}>
                    {plan.focus_areas?.map((area: string, idx: number) => (
                      <View
                        key={idx}
                        style={{
                          paddingHorizontal: 10,
                          paddingVertical: 4,
                          borderRadius: 6,
                          backgroundColor: colors.primary + '20',
                        }}
                      >
                        <Text style={{ fontSize: 10, fontWeight: '600', color: colors.primary }}>
                          {area.toUpperCase()}
                        </Text>
                      </View>
                    ))}
                  </View>

                  <TouchableOpacity
                    onPress={() => setSelectedPlan(selectedPlan?.plan_id === plan.plan_id ? null : plan)}
                    style={{
                      backgroundColor: colors.primary,
                      padding: 12,
                      borderRadius: 8,
                    }}
                    data-testid={`fitness-plan-details-button-${plan.plan_id}`}
                    testID={`fitness-plan-details-button-${plan.plan_id}`}
                  >
                    <Text style={{ textAlign: 'center', color: colors.primaryText, fontWeight: '600' }}>
                      {selectedPlan?.plan_id === plan.plan_id ? 'Hide Details' : 'View Details'}
                    </Text>
                  </TouchableOpacity>

                  {selectedPlan?.plan_id === plan.plan_id && selectedPlan.exercises && (
                    <View style={{ marginTop: 16, paddingTop: 16, borderTopWidth: 1, borderTopColor: colors.border }}>
                      <Text style={{ fontSize: 14, fontWeight: '700', color: colors.text, marginBottom: 12 }}>
                        Exercises
                      </Text>
                      {selectedPlan.exercises.map((exercise: any, idx: number) => (
                        <View key={idx} style={{ marginBottom: 10 }}>
                          <Text style={{ fontSize: 14, fontWeight: '600', color: colors.text }}>
                            {idx + 1}. {exercise.name}
                          </Text>
                          <Text style={{ fontSize: 12, color: colors.textSecondary, marginTop: 2 }}>
                            {exercise.sets} sets × {exercise.reps} reps
                          </Text>
                        </View>
                      ))}
                    </View>
                  )}
                </View>
              ))
            )}
          </View>
        )}

        {/* PROGRESS TAB */}
        {activeTab === 'progress' && (
          <View>
            {/* Analytics Summary */}
            {progressMetrics && (
              <View style={{ backgroundColor: colors.card, borderRadius: 12, padding: 16, marginBottom: 16, borderWidth: 1, borderColor: colors.border }}>
                <Text style={{ fontSize: 18, fontWeight: '700', color: colors.text, marginBottom: 16 }}>
                  Progress Analytics
                </Text>
                <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 12 }}>
                  <View style={{ flex: 1, minWidth: 140 }}>
                    <Text style={{ fontSize: 12, color: colors.textSecondary, marginBottom: 4 }}>Total Workouts</Text>
                    <Text style={{ fontSize: 24, fontWeight: '700', color: colors.text }}>
                      {progressMetrics.total_workouts || 0}
                    </Text>
                  </View>
                  <View style={{ flex: 1, minWidth: 140 }}>
                    <Text style={{ fontSize: 12, color: colors.textSecondary, marginBottom: 4 }}>Total Time</Text>
                    <Text style={{ fontSize: 24, fontWeight: '700', color: colors.text }}>
                      {Math.round((progressMetrics.total_duration_minutes || 0) / 60)}h
                    </Text>
                  </View>
                  <View style={{ flex: 1, minWidth: 140 }}>
                    <Text style={{ fontSize: 12, color: colors.textSecondary, marginBottom: 4 }}>This Week</Text>
                    <Text style={{ fontSize: 24, fontWeight: '700', color: colors.text }}>
                      {progressMetrics.workouts_this_week || 0}
                    </Text>
                  </View>
                  <View style={{ flex: 1, minWidth: 140 }}>
                    <Text style={{ fontSize: 12, color: colors.textSecondary, marginBottom: 4 }}>Avg / Week</Text>
                    <Text style={{ fontSize: 24, fontWeight: '700', color: colors.text }}>
                      {progressMetrics.avg_workouts_per_week?.toFixed(1) || 0}
                    </Text>
                  </View>
                </View>
              </View>
            )}

            {/* Workout History */}
            <Text style={{ fontSize: 18, fontWeight: '700', color: colors.text, marginBottom: 12 }}>
              Workout History
            </Text>
            {workoutHistory.length === 0 ? (
              <View style={{ alignItems: 'center', marginTop: 40 }}>
                <FontAwesome5 name="history" size={48} color={colors.textSecondary} />
                <Text style={{ fontSize: 16, color: colors.textSecondary, marginTop: 16 }}>
                  No workout logs yet
                </Text>
              </View>
            ) : (
              workoutHistory.map((workout) => (
                <View
                  key={workout.log_id}
                  style={{
                    backgroundColor: colors.card,
                    borderRadius: 12,
                    padding: 16,
                    marginBottom: 12,
                    borderWidth: 1,
                    borderColor: colors.border,
                  }}
                >
                  <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginBottom: 8 }}>
                    <Text style={{ fontSize: 14, fontWeight: '600', color: colors.text }}>
                      {new Date(workout.workout_date).toLocaleDateString()}
                    </Text>
                    <Text style={{ fontSize: 12, color: colors.textSecondary }}>
                      {workout.duration_minutes} min
                    </Text>
                  </View>
                  <Text style={{ fontSize: 12, color: colors.textSecondary }}>
                    Effort: {workout.effort_level?.toUpperCase()} • {workout.exercises_completed?.length || 0} exercises
                  </Text>
                </View>
              ))
            )}
          </View>
        )}

        {/* EXERCISES TAB */}
        {activeTab === 'exercises' && (
          <View>
            {/* Filter Chips */}
            <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ marginBottom: 16 }}>
              <View style={{ flexDirection: 'row', gap: 8 }}>
                {['all', 'strength', 'cardio', 'flexibility', 'core'].map((filter) => (
                  <TouchableOpacity
                    key={filter}
                    onPress={() => setExerciseFilter(filter)}
                    style={{
                      paddingHorizontal: 16,
                      paddingVertical: 8,
                      borderRadius: 8,
                      backgroundColor: exerciseFilter === filter ? colors.primary : colors.background,
                      borderWidth: 1,
                      borderColor: exerciseFilter === filter ? colors.primary : colors.border,
                    }}
                    data-testid={`fitness-exercise-filter-${filter}`}
                    testID={`fitness-exercise-filter-${filter}`}
                  >
                    <Text style={{ fontSize: 12, fontWeight: '600', color: exerciseFilter === filter ? colors.primaryText : colors.text }}>
                      {filter.toUpperCase()}
                    </Text>
                  </TouchableOpacity>
                ))}
              </View>
            </ScrollView>

            {/* Exercise Library */}
            {filteredExercises.length === 0 ? (
              <View style={{ alignItems: 'center', marginTop: 40 }}>
                <FontAwesome5 name="book-open" size={48} color={colors.textSecondary} />
                <Text style={{ fontSize: 16, color: colors.textSecondary, marginTop: 16 }}>
                  Loading exercise library...
                </Text>
              </View>
            ) : (
              filteredExercises.map((exercise, idx) => (
                <View
                  key={idx}
                  style={{
                    backgroundColor: colors.card,
                    borderRadius: 12,
                    padding: 16,
                    marginBottom: 12,
                    borderWidth: 1,
                    borderColor: colors.border,
                  }}
                >
                  <Text style={{ fontSize: 16, fontWeight: '700', color: colors.text, marginBottom: 4 }}>
                    {exercise.name}
                  </Text>
                  <Text style={{ fontSize: 12, color: colors.textSecondary, marginBottom: 8 }}>
                    {exercise.category} • {exercise.difficulty}
                  </Text>
                  <Text style={{ fontSize: 13, color: colors.text, lineHeight: 20 }}>
                    {exercise.description}
                  </Text>
                  {exercise.equipment && exercise.equipment.length > 0 && (
                    <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginTop: 8 }}>
                      {exercise.equipment.map((eq: string, i: number) => (
                        <View
                          key={i}
                          style={{
                            paddingHorizontal: 8,
                            paddingVertical: 4,
                            borderRadius: 6,
                            backgroundColor: colors.primary + '20',
                          }}
                        >
                          <Text style={{ fontSize: 10, fontWeight: '600', color: colors.primary }}>
                            {eq}
                          </Text>
                        </View>
                      ))}
                    </View>
                  )}
                </View>
              ))
            )}
          </View>
        )}

        {/* PERSONAL RECORDS TAB */}
        {activeTab === 'records' && (
          <View>
            <Text style={{ fontSize: 18, fontWeight: '700', color: colors.text, marginBottom: 12 }}>
              Personal Records
            </Text>
            {personalRecords.length === 0 ? (
              <View style={{ alignItems: 'center', marginTop: 40 }}>
                <FontAwesome5 name="trophy" size={48} color={colors.textSecondary} />
                <Text style={{ fontSize: 16, color: colors.textSecondary, marginTop: 16 }}>
                  No personal records yet
                </Text>
                <Text style={{ fontSize: 14, color: colors.textSecondary, marginTop: 8 }}>
                  Complete workouts to track your PRs
                </Text>
              </View>
            ) : (
              personalRecords.map((record, idx) => (
                <View
                  key={idx}
                  style={{
                    backgroundColor: colors.card,
                    borderRadius: 12,
                    padding: 16,
                    marginBottom: 12,
                    borderWidth: 1,
                    borderColor: colors.border,
                  }}
                >
                  <View style={{ flexDirection: 'row', alignItems: 'center', marginBottom: 8 }}>
                    <FontAwesome5 name="medal" size={20} color={colors.warning} style={{ marginRight: 12 }} />
                    <View style={{ flex: 1 }}>
                      <Text style={{ fontSize: 16, fontWeight: '700', color: colors.text }}>
                        {record.exercise_name}
                      </Text>
                      <Text style={{ fontSize: 12, color: colors.textSecondary, marginTop: 2 }}>
                        {new Date(record.date_achieved).toLocaleDateString()}
                      </Text>
                    </View>
                    <Text style={{ fontSize: 20, fontWeight: '700', color: colors.primary }}>
                      {record.value} {record.unit}
                    </Text>
                  </View>
                </View>
              ))
            )}
          </View>
        )}
      </ScrollView>
    </FeatureLayout>
  );
}
