import React, { useState, useEffect, useCallback } from 'react';
import {
  View,
  Text,
  ScrollView,
  TouchableOpacity,
  TextInput,
  Modal,
  ActivityIndicator,
  Alert,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useTheme } from '../../src/context/ThemeContext';
import FeatureLayout from '../../src/components/FeatureLayout';
import { useAuth } from '../../src/context/AuthContext';
import api from '../../src/services/api';
import { useTranslation } from '../../src/hooks/useTranslation';

export default function DecisionCoachScreen() {
  const { colors } = useTheme();
  const { user } = useAuth();
  const { t } = useTranslation();
  t('i18n.route.features.decision-coach.probe');
  const [localGuestId] = useState(() => `user_${Math.random().toString(36).slice(2)}${Date.now().toString(36)}`.slice(0, 78));
  const fallbackUserId = user?.user_id || localGuestId;
  const [activeTab, setActiveTab] = useState('decisions');
  const [loading, setLoading] = useState(true);
  const [decisions, setDecisions] = useState([]);
  const [templates, setTemplates] = useState([]);
  const [usage, setUsage] = useState(null);
  const [stats, setStats] = useState(null);

  // Modals
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [showTemplateModal, setShowTemplateModal] = useState(false);
  const [showEditorModal, setShowEditorModal] = useState(false);
  const [editingDecision, setEditingDecision] = useState(null);

  // Form state
  const [newTitle, setNewTitle] = useState('');
  const [newDescription, setNewDescription] = useState('');
  const [selectedFramework, setSelectedFramework] = useState('pros_cons');

  const loadData = useCallback(async () => {
    try {
      setLoading(true);
      const response = await api.get('/decision-coach/bootstrap', {
        params: { fallback_user_id: fallbackUserId },
      });
      setDecisions(response.data.recent_decisions || []);
      setTemplates(response.data.templates || []);
      setUsage(response.data.usage || {});
      setStats(response.data.stats || {});
    } catch (error) {
      console.error('Failed to load decision coach data:', error);
      Alert.alert('Error', 'Failed to load data');
    } finally {
      setLoading(false);
    }
  }, [fallbackUserId]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const loadAllDecisions = async () => {
    try {
      const response = await api.get('/decision-coach/decisions', {
        params: { fallback_user_id: fallbackUserId },
      });
      setDecisions(response.data.decisions || []);
    } catch (error) {
      console.error('Failed to load decisions:', error);
    }
  };

  const createDecision = async () => {
    if (!newTitle.trim()) {
      Alert.alert('Error', 'Please enter a title');
      return;
    }

    try {
      await api.post('/decision-coach/decisions', {
        title: newTitle,
        description: newDescription,
        framework_type: selectedFramework,
        fallback_user_id: fallbackUserId,
      });

      Alert.alert('Success', 'Decision created');
      setShowCreateModal(false);
      setNewTitle('');
      setNewDescription('');
      setSelectedFramework('pros_cons');
      loadData();
      loadAllDecisions();
    } catch (error) {
      console.error('Failed to create decision:', error);
      if (error.response?.data?.detail?.upgrade_prompt) {
        Alert.alert(
          'Upgrade Required',
          error.response.data.detail.message,
          [{ text: 'OK' }]
        );
      } else {
        Alert.alert('Error', error.response?.data?.detail?.message || 'Failed to create decision');
      }
    }
  };

  const createFromTemplate = async (template) => {
    try {
      const response = await api.post('/decision-coach/decisions/from-template', {
        template_id: template.template_id,
        fallback_user_id: fallbackUserId,
      });

      Alert.alert('Success', `Decision created from template: ${template.name}`);
      setShowTemplateModal(false);
      loadData();
      loadAllDecisions();
      
      // Open editor with new decision
      setEditingDecision(response.data.decision);
      setShowEditorModal(true);
    } catch (error) {
      console.error('Failed to create from template:', error);
      if (error.response?.data?.detail?.upgrade_prompt) {
        Alert.alert(
          'Upgrade Required',
          error.response.data.detail.message,
          [{ text: 'OK' }]
        );
      } else {
        Alert.alert('Error', 'Failed to create from template');
      }
    }
  };

  const deleteDecision = async (decisionId) => {
    Alert.alert(
      'Delete Decision',
      'Are you sure you want to delete this decision?',
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Delete',
          style: 'destructive',
          onPress: async () => {
            try {
              await api.delete(`/decision-coach/decisions/${decisionId}`, {
                params: { fallback_user_id: fallbackUserId },
              });
              Alert.alert('Success', 'Decision deleted');
              loadData();
              loadAllDecisions();
            } catch (error) {
              console.error('Failed to delete decision:', error);
              Alert.alert('Error', 'Failed to delete decision');
            }
          },
        },
      ]
    );
  };

  const openEditor = (decision) => {
    setEditingDecision(decision);
    setShowEditorModal(true);
  };

  const getStatusColor = (status) => {
    switch (status) {
      case 'decided':
        return colors.success;
      case 'analyzing':
        return colors.primary;
      case 'tracked':
        return colors.info;
      default:
        return colors.textMuted;
    }
  };

  const getFrameworkLabel = (type) => {
    const labels = {
      pros_cons: 'Pros & Cons',
      swot: 'SWOT Analysis',
      decision_matrix: 'Decision Matrix',
      weighted_scoring: 'Weighted Scoring',
    };
    return labels[type] || type;
  };

  const frameworks = [
    {
      id: 'pros_cons',
      name: 'Pros & Cons',
      description: 'Compare options with weighted pros and cons',
      icon: 'list',
      color: colors.primary,
      tier: 'free',
    },
    {
      id: 'swot',
      name: 'SWOT Analysis',
      description: 'Strengths, Weaknesses, Opportunities, Threats',
      icon: 'grid',
      color: colors.success,
      tier: 'basic',
    },
    {
      id: 'decision_matrix',
      name: 'Decision Matrix',
      description: 'Score options against weighted criteria',
      icon: 'analytics',
      color: colors.warning,
      tier: 'basic',
    },
    {
      id: 'weighted_scoring',
      name: 'Weighted Scoring',
      description: 'Advanced multi-factor evaluation',
      icon: 'calculator',
      color: colors.primary,
      tier: 'premium',
    },
  ];

  return (
    <FeatureLayout
      feature="ai-cognitive"
      title="Decision Coach"
      subtitle="Make better decisions with AI-powered frameworks"
      icon="bulb"
      color={colors.primary}
      showSecondaryTabs={false}
    >
      {/* Tabs */}
      <View style={{ flexDirection: 'row', backgroundColor: colors.card, borderBottomWidth: 1, borderBottomColor: colors.border }} data-testid="decision-coach-tabs" testID="decision-coach-tabs">
        <TouchableOpacity
          onPress={() => setActiveTab('decisions')}
          style={{
            flex: 1,
            paddingVertical: 14,
            borderBottomWidth: 2,
            borderBottomColor: activeTab === 'decisions' ? colors.primary : 'transparent',
          }}
          data-testid="decision-coach-tab-decisions" testID="decision-coach-tab-decisions"
        >
          <Text style={{ textAlign: 'center', fontWeight: '600', color: activeTab === 'decisions' ? colors.primary : colors.textMuted }}>
            My Decisions
          </Text>
        </TouchableOpacity>
        <TouchableOpacity
          onPress={() => setActiveTab('templates')}
          style={{
            flex: 1,
            paddingVertical: 14,
            borderBottomWidth: 2,
            borderBottomColor: activeTab === 'templates' ? colors.primary : 'transparent',
          }}
          data-testid="decision-coach-tab-templates" testID="decision-coach-tab-templates"
        >
          <Text style={{ textAlign: 'center', fontWeight: '600', color: activeTab === 'templates' ? colors.primary : colors.textMuted }}>
            Templates
          </Text>
        </TouchableOpacity>
        <TouchableOpacity
          onPress={() => setActiveTab('analytics')}
          style={{
            flex: 1,
            paddingVertical: 14,
            borderBottomWidth: 2,
            borderBottomColor: activeTab === 'analytics' ? colors.primary : 'transparent',
          }}
          data-testid="decision-coach-tab-analytics" testID="decision-coach-tab-analytics"
        >
          <Text style={{ textAlign: 'center', fontWeight: '600', color: activeTab === 'analytics' ? colors.primary : colors.textMuted }}>
            Analytics
          </Text>
        </TouchableOpacity>
      </View>

      <ScrollView style={{ flex: 1 }} contentContainerStyle={{ padding: 16 }} data-testid="decision-coach-content" testID="decision-coach-content">
        {loading ? (
          <ActivityIndicator size="large" color={colors.primary} style={{ marginTop: 32 }} data-testid="decision-coach-loading-indicator" testID="decision-coach-loading-indicator" />
        ) : activeTab === 'decisions' ? (
          <View>
            {/* Usage Stats */}
            {usage && (
              <View style={{ backgroundColor: colors.card, borderRadius: 12, padding: 16, marginBottom: 16, borderWidth: 1, borderColor: colors.border }} data-testid="decision-coach-usage-stats" testID="decision-coach-usage-stats">
                <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                  <Text style={{ fontSize: 16, fontWeight: '600', color: colors.text }}>
                    {usage.tier.charAt(0).toUpperCase() + usage.tier.slice(1)} Plan
                  </Text>
                  <View style={{ backgroundColor: usage.can_create ? colors.success + '20' : colors.error + '20', paddingHorizontal: 12, paddingVertical: 4, borderRadius: 12 }}>
                    <Text style={{ fontSize: 12, fontWeight: '600', color: usage.can_create ? colors.success : colors.error }}>
                      {usage.monthly_limit === -1 ? 'Unlimited' : `${usage.decisions_used_this_month}/${usage.monthly_limit}`}
                    </Text>
                  </View>
                </View>
                <Text style={{ fontSize: 13, color: colors.textMuted }}>
                  Decisions this month • {usage.frameworks_available.length} frameworks available
                </Text>
              </View>
            )}

            {/* Create Button */}
            <TouchableOpacity
              onPress={() => setShowCreateModal(true)}
              disabled={usage && !usage.can_create}
              style={{
                backgroundColor: usage && !usage.can_create ? colors.border : colors.primary,
                padding: 16,
                borderRadius: 12,
                flexDirection: 'row',
                alignItems: 'center',
                justifyContent: 'center',
                marginBottom: 16,
              }}
              data-testid="decision-coach-create-button" testID="decision-coach-create-button"
            >
              <Ionicons name="add-circle-outline" size={20} color={colors.primaryText} style={{ marginRight: 8 }} />
              <Text style={{ color: colors.primaryText, fontSize: 16, fontWeight: '600' }}>
                {usage && !usage.can_create ? 'Monthly Limit Reached' : 'Create New Decision'}
              </Text>
            </TouchableOpacity>

            {/* Decisions List */}
            {decisions.length === 0 ? (
              <View style={{ alignItems: 'center', marginTop: 32 }} data-testid="decision-coach-empty-state" testID="decision-coach-empty-state">
                <Ionicons name="bulb-outline" size={64} color={colors.textMuted} />
                <Text style={{ fontSize: 16, color: colors.textMuted, marginTop: 16, textAlign: 'center' }} data-testid="decision-coach-empty-state-message" testID="decision-coach-empty-state-message">
                  No decisions yet{'\n'}Start by creating your first decision
                </Text>
              </View>
            ) : (
              decisions.map((decision) => (
                <View
                  key={decision.decision_id}
                  style={{
                    backgroundColor: colors.card,
                    borderRadius: 12,
                    padding: 16,
                    marginBottom: 12,
                    borderWidth: 1,
                    borderColor: colors.border,
                  }}
                  data-testid={`decision-coach-card-${decision.decision_id}`}
                  testID={`decision-coach-card-${decision.decision_id}`}
                >
                  <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 8 }}>
                    <View style={{ flex: 1, marginRight: 12 }}>
                      <Text style={{ fontSize: 18, fontWeight: '600', color: colors.text, marginBottom: 4 }}>
                        {decision.title}
                      </Text>
                      <Text style={{ fontSize: 13, color: colors.textMuted }}>
                        {getFrameworkLabel(decision.framework_type)}
                      </Text>
                    </View>
                    <View style={{
                      backgroundColor: getStatusColor(decision.status) + '20',
                      paddingHorizontal: 10,
                      paddingVertical: 4,
                      borderRadius: 12,
                    }}>
                      <Text style={{
                        fontSize: 12,
                        fontWeight: '600',
                        color: getStatusColor(decision.status),
                      }}>
                        {decision.status.toUpperCase()}
                      </Text>
                    </View>
                  </View>

                  {decision.final_choice && (
                    <View style={{ backgroundColor: colors.bgSecondary, padding: 12, borderRadius: 8, marginBottom: 12 }}>
                      <Text style={{ fontSize: 13, color: colors.textMuted, marginBottom: 4 }}>Decision:</Text>
                      <Text style={{ fontSize: 15, fontWeight: '600', color: colors.text }}>
                        {decision.final_choice}
                      </Text>
                      {decision.confidence_score && (
                        <Text style={{ fontSize: 12, color: colors.textMuted, marginTop: 4 }}>
                          Confidence: {decision.confidence_score}%
                        </Text>
                      )}
                    </View>
                  )}

                  <View style={{ flexDirection: 'row', gap: 8, marginTop: 8 }}>
                    <TouchableOpacity
                      onPress={() => openEditor(decision)}
                      style={{
                        flex: 1,
                        backgroundColor: colors.primary,
                        padding: 12,
                        borderRadius: 8,
                        alignItems: 'center',
                      }}
                      data-testid={`decision-coach-open-button-${decision.decision_id}`}
                      testID={`decision-coach-open-button-${decision.decision_id}`}
                    >
                      <Text style={{ color: colors.primaryText, fontWeight: '600' }}>Open</Text>
                    </TouchableOpacity>

                    <TouchableOpacity
                      onPress={() => deleteDecision(decision.decision_id)}
                      style={{
                        backgroundColor: colors.error + '20',
                        padding: 12,
                        borderRadius: 8,
                        alignItems: 'center',
                        minWidth: 60,
                      }}
                      data-testid={`decision-coach-delete-button-${decision.decision_id}`}
                      testID={`decision-coach-delete-button-${decision.decision_id}`}
                    >
                      <Ionicons name="trash-outline" size={18} color={colors.error} />
                    </TouchableOpacity>
                  </View>
                </View>
              ))
            )}
          </View>
        ) : activeTab === 'templates' ? (
          <View>
            <Text style={{ fontSize: 16, fontWeight: '600', color: colors.text, marginBottom: 12 }}>
              Decision Templates
            </Text>
            {templates.map((template) => (
              <TouchableOpacity
                key={template.template_id}
                onPress={() => createFromTemplate(template)}
                style={{
                  backgroundColor: colors.card,
                  borderRadius: 12,
                  padding: 16,
                  marginBottom: 12,
                  borderWidth: 1,
                  borderColor: colors.border,
                }}
                data-testid={`decision-coach-template-card-${template.template_id}`}
                testID={`decision-coach-template-card-${template.template_id}`}
              >
                <View style={{ flexDirection: 'row', alignItems: 'center', marginBottom: 8 }}>
                  <View
                    style={{
                      width: 40,
                      height: 40,
                      borderRadius: 20,
                      backgroundColor: template.color + '20',
                      alignItems: 'center',
                      justifyContent: 'center',
                      marginRight: 12,
                    }}
                  >
                    <Ionicons name={template.icon} size={20} color={template.color} />
                  </View>
                  <View style={{ flex: 1 }}>
                    <Text style={{ fontSize: 16, fontWeight: '600', color: colors.text }}>
                      {template.name}
                    </Text>
                    <Text style={{ fontSize: 12, color: colors.textMuted }}>
                      {getFrameworkLabel(template.framework_type)}
                    </Text>
                  </View>
                  <View
                    style={{
                      backgroundColor: colors.bgSecondary,
                      paddingHorizontal: 10,
                      paddingVertical: 4,
                      borderRadius: 12,
                    }}
                  >
                    <Text style={{ fontSize: 11, fontWeight: '600', color: colors.textMuted }}>
                      {template.tier_requirement.toUpperCase()}
                    </Text>
                  </View>
                </View>
                <Text style={{ fontSize: 13, color: colors.textMuted }}>
                  {template.description}
                </Text>
              </TouchableOpacity>
            ))}
          </View>
        ) : (
          <AnalyticsTab colors={colors} fallbackUserId={fallbackUserId} />
        )}
      </ScrollView>

      {/* Create Decision Modal */}
      <Modal visible={showCreateModal} animationType="slide" transparent testID="decision-coach-create-modal" data-testid="decision-coach-create-modal">
        <View style={{ flex: 1, backgroundColor: 'rgba(0,0,0,0.5)', justifyContent: 'center', padding: 16 }} data-testid="decision-coach-create-modal-overlay" testID="decision-coach-create-modal-overlay">
          <ScrollView style={{ maxHeight: '80%' }}>
            <View style={{ backgroundColor: colors.card, borderRadius: 16, padding: 24, maxWidth: 600, width: '100%', alignSelf: 'center' }} data-testid="decision-coach-create-modal-content" testID="decision-coach-create-modal-content">
              <Text style={{ fontSize: 20, fontWeight: '700', color: colors.text, marginBottom: 16 }}>
                Create New Decision
              </Text>

              <Text style={{ fontSize: 14, color: colors.textMuted, marginBottom: 8 }}>Title</Text>
              <TextInput
                value={newTitle}
                onChangeText={setNewTitle}
                placeholder="e.g., Should I switch careers?"
                placeholderTextColor={colors.textMuted}
                style={{
                  backgroundColor: colors.bgSecondary,
                  color: colors.text,
                  padding: 12,
                  borderRadius: 8,
                  fontSize: 14,
                  marginBottom: 16,
                  borderWidth: 1,
                  borderColor: colors.border,
                }}
                data-testid="decision-coach-create-title-input"
                testID="decision-coach-create-title-input"
              />

              <Text style={{ fontSize: 14, color: colors.textMuted, marginBottom: 8 }}>Description (Optional)</Text>
              <TextInput
                value={newDescription}
                onChangeText={setNewDescription}
                placeholder="Add context about your decision..."
                placeholderTextColor={colors.textMuted}
                multiline
                numberOfLines={3}
                style={{
                  backgroundColor: colors.bgSecondary,
                  color: colors.text,
                  padding: 12,
                  borderRadius: 8,
                  fontSize: 14,
                  marginBottom: 16,
                  borderWidth: 1,
                  borderColor: colors.border,
                  minHeight: 80,
                }}
                data-testid="decision-coach-create-description-input"
                testID="decision-coach-create-description-input"
              />

              <Text style={{ fontSize: 14, color: colors.textMuted, marginBottom: 12 }}>Framework</Text>
              <View style={{ gap: 12, marginBottom: 24 }}>
                {frameworks.map((framework) => {
                  const isAvailable = usage?.frameworks_available.includes(framework.id);
                  return (
                    <TouchableOpacity
                      key={framework.id}
                      onPress={() => isAvailable && setSelectedFramework(framework.id)}
                      disabled={!isAvailable}
                      style={{
                        backgroundColor: selectedFramework === framework.id ? framework.color + '20' : colors.bgSecondary,
                        borderRadius: 12,
                        padding: 16,
                        borderWidth: 2,
                        borderColor: selectedFramework === framework.id ? framework.color : 'transparent',
                        opacity: isAvailable ? 1 : 0.5,
                      }}
                      data-testid={`decision-coach-framework-option-${framework.id}`}
                      testID={`decision-coach-framework-option-${framework.id}`}
                    >
                      <View style={{ flexDirection: 'row', alignItems: 'center' }}>
                        <View
                          style={{
                            width: 40,
                            height: 40,
                            borderRadius: 20,
                            backgroundColor: framework.color + '20',
                            alignItems: 'center',
                            justifyContent: 'center',
                            marginRight: 12,
                          }}
                        >
                          <Ionicons name={framework.icon} size={20} color={framework.color} />
                        </View>
                        <View style={{ flex: 1 }}>
                          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                            <Text style={{ fontSize: 16, fontWeight: '600', color: colors.text }}>
                              {framework.name}
                            </Text>
                            {!isAvailable && (
                              <View style={{ backgroundColor: colors.error + '20', paddingHorizontal: 8, paddingVertical: 2, borderRadius: 8 }}>
                                <Text style={{ fontSize: 10, fontWeight: '600', color: colors.error }}>
                                  {framework.tier.toUpperCase()}
                                </Text>
                              </View>
                            )}
                          </View>
                          <Text style={{ fontSize: 13, color: colors.textMuted, marginTop: 2 }}>
                            {framework.description}
                          </Text>
                        </View>
                      </View>
                    </TouchableOpacity>
                  );
                })}
              </View>

              <View style={{ flexDirection: 'row', gap: 12 }}>
                <TouchableOpacity
                  onPress={() => {
                    setShowCreateModal(false);
                    setNewTitle('');
                    setNewDescription('');
                    setSelectedFramework('pros_cons');
                  }}
                  style={{
                    flex: 1,
                    backgroundColor: colors.bgSecondary,
                    padding: 14,
                    borderRadius: 8,
                    alignItems: 'center',
                  }}
                  data-testid="decision-coach-create-cancel-button"
                  testID="decision-coach-create-cancel-button"
                >
                  <Text style={{ color: colors.text, fontWeight: '600' }}>Cancel</Text>
                </TouchableOpacity>

                <TouchableOpacity
                  onPress={createDecision}
                  style={{
                    flex: 1,
                    backgroundColor: colors.primary,
                    padding: 14,
                    borderRadius: 8,
                    alignItems: 'center',
                  }}
                  data-testid="decision-coach-create-submit-button"
                  testID="decision-coach-create-submit-button"
                >
                  <Text style={{ color: colors.primaryText, fontWeight: '600' }}>Create</Text>
                </TouchableOpacity>
              </View>
            </View>
          </ScrollView>
        </View>
      </Modal>

      {/* Decision Editor Modal */}
      {showEditorModal && editingDecision && (
        <DecisionEditorModal
          decision={editingDecision}
          colors={colors}
          visible={showEditorModal}
          fallbackUserId={fallbackUserId}
          onClose={() => {
            setShowEditorModal(false);
            setEditingDecision(null);
            loadData();
            loadAllDecisions();
          }}
        />
      )}
    </FeatureLayout>
  );
}

// Analytics Tab Component
function AnalyticsTab({ colors, fallbackUserId }) {
  const [analytics, setAnalytics] = useState(null);
  const [loading, setLoading] = useState(true);

  const loadAnalytics = useCallback(async () => {
    try {
      setLoading(true);
      const response = await api.get('/decision-coach/analytics', {
        params: { fallback_user_id: fallbackUserId },
      });
      setAnalytics(response.data);
    } catch (error) {
      console.error('Failed to load analytics:', error);
    } finally {
      setLoading(false);
    }
  }, [fallbackUserId]);

  useEffect(() => {
    loadAnalytics();
  }, [loadAnalytics]);

  if (loading) {
    return <ActivityIndicator size="large" color={colors.primary} style={{ marginTop: 32 }} data-testid="decision-coach-analytics-loading" testID="decision-coach-analytics-loading" />;
  }

  if (!analytics || analytics.total_decisions === 0) {
    return (
      <View style={{ alignItems: 'center', marginTop: 32 }} data-testid="decision-coach-analytics-empty-state" testID="decision-coach-analytics-empty-state">
        <Ionicons name="stats-chart-outline" size={64} color={colors.textMuted} />
        <Text style={{ fontSize: 16, color: colors.textMuted, marginTop: 16 }} data-testid="decision-coach-analytics-empty-message" testID="decision-coach-analytics-empty-message">
          No analytics data yet
        </Text>
      </View>
    );
  }

  return (
    <View data-testid="decision-coach-analytics-root" testID="decision-coach-analytics-root">
      {/* Key Metrics */}
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 12, marginBottom: 16 }} data-testid="decision-coach-analytics-metrics-grid" testID="decision-coach-analytics-metrics-grid">
        <View style={{ flex: 1, minWidth: 150, backgroundColor: colors.card, padding: 16, borderRadius: 12, borderWidth: 1, borderColor: colors.border }}>
          <Text style={{ fontSize: 12, color: colors.textMuted, marginBottom: 4 }}>Total Decisions</Text>
          <Text style={{ fontSize: 24, fontWeight: '700', color: colors.text }}>{analytics.total_decisions}</Text>
        </View>
        <View style={{ flex: 1, minWidth: 150, backgroundColor: colors.card, padding: 16, borderRadius: 12, borderWidth: 1, borderColor: colors.border }}>
          <Text style={{ fontSize: 12, color: colors.textMuted, marginBottom: 4 }}>This Month</Text>
          <Text style={{ fontSize: 24, fontWeight: '700', color: colors.text }}>{analytics.decisions_this_month}</Text>
        </View>
        <View style={{ flex: 1, minWidth: 150, backgroundColor: colors.card, padding: 16, borderRadius: 12, borderWidth: 1, borderColor: colors.border }}>
          <Text style={{ fontSize: 12, color: colors.textMuted, marginBottom: 4 }}>Success Rate</Text>
          <Text style={{ fontSize: 24, fontWeight: '700', color: colors.success }}>{analytics.success_rate}%</Text>
        </View>
        <View style={{ flex: 1, minWidth: 150, backgroundColor: colors.card, padding: 16, borderRadius: 12, borderWidth: 1, borderColor: colors.border }}>
          <Text style={{ fontSize: 12, color: colors.textMuted, marginBottom: 4 }}>Avg Confidence</Text>
          <Text style={{ fontSize: 24, fontWeight: '700', color: colors.text }}>{analytics.avg_confidence_score}%</Text>
        </View>
      </View>

      {/* Framework Usage */}
      <View style={{ backgroundColor: colors.card, borderRadius: 12, padding: 16, marginBottom: 16, borderWidth: 1, borderColor: colors.border }}>
        <Text style={{ fontSize: 16, fontWeight: '600', color: colors.text, marginBottom: 12 }}>
          Framework Usage
        </Text>
        {Object.entries(analytics.framework_usage).map(([framework, count], index) => (
          <View
            key={framework}
            style={{
              flexDirection: 'row',
              justifyContent: 'space-between',
              paddingVertical: 8,
              borderBottomWidth: index < Object.keys(analytics.framework_usage).length - 1 ? 1 : 0,
              borderBottomColor: colors.border,
            }}
          >
            <Text style={{ color: colors.text }}>{framework.replace(/_/g, ' ')}</Text>
            <Text style={{ color: colors.textMuted, fontWeight: '600' }}>{count}</Text>
          </View>
        ))}
      </View>

      {/* Most Used Framework */}
      <View style={{ backgroundColor: colors.card, borderRadius: 12, padding: 16, borderWidth: 1, borderColor: colors.border }}>
        <Text style={{ fontSize: 16, fontWeight: '600', color: colors.text, marginBottom: 8 }}>
          Most Used Framework
        </Text>
        <Text style={{ fontSize: 18, color: colors.primary, fontWeight: '600' }}>
          {analytics.most_used_framework.replace(/_/g, ' ')}
        </Text>
        <Text style={{ fontSize: 13, color: colors.textMuted, marginTop: 4 }}>
          Avg decision speed: {analytics.decision_speed_avg_hours.toFixed(1)} hours
        </Text>
      </View>
    </View>
  );
}

// Decision Editor Modal - Full Implementation
function DecisionEditorModal({ decision, colors, visible, onClose, fallbackUserId }) {
  const [editing, setEditing] = useState(decision);
  const [analyzing, setAnalyzing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [showDecideModal, setShowDecideModal] = useState(false);

  const saveFrameworkData = async (frameworkData) => {
    try {
      setSaving(true);
      await api.put(`/decision-coach/decisions/${decision.decision_id}`, {
        framework_data: frameworkData,
        fallback_user_id: fallbackUserId,
      });
      setEditing({ ...editing, framework_data: frameworkData });
    } catch (error) {
      console.error('Failed to save framework data:', error);
      Alert.alert('Error', 'Failed to save changes');
    } finally {
      setSaving(false);
    }
  };

  const runAIAnalysis = async () => {
    try {
      setAnalyzing(true);
      const response = await api.post(`/decision-coach/decisions/${decision.decision_id}/analyze`, {
        fallback_user_id: fallbackUserId,
      });
      
      Alert.alert('Success', 'AI analysis complete');
      setEditing({ ...editing, ai_analysis: response.data.ai_analysis, status: 'draft' });
    } catch (error) {
      console.error('AI analysis failed:', error);
      Alert.alert('Error', 'AI analysis failed. Please try again.');
    } finally {
      setAnalyzing(false);
    }
  };

  const markAsDecided = async (finalChoice, confidence, notes) => {
    try {
      await api.post(`/decision-coach/decisions/${decision.decision_id}/decide`, {
        final_choice: finalChoice,
        confidence_score: confidence,
        notes: notes,
        fallback_user_id: fallbackUserId,
      });
      Alert.alert('Success', 'Decision marked as decided');
      setShowDecideModal(false);
      onClose();
    } catch (error) {
      console.error('Failed to mark as decided:', error);
      Alert.alert('Error', 'Failed to save decision');
    }
  };

  return (
    <Modal visible={visible} animationType="slide" testID="decision-coach-editor-modal" data-testid="decision-coach-editor-modal">
      <View style={{ flex: 1, backgroundColor: colors.bg }} data-testid={`decision-coach-editor-modal-${decision.decision_id}`} testID={`decision-coach-editor-modal-${decision.decision_id}`}>
        {/* Header */}
        <View style={{ backgroundColor: colors.card, padding: 16, borderBottomWidth: 1, borderBottomColor: colors.border }} data-testid="decision-coach-editor-header" testID="decision-coach-editor-header">
          <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
            <TouchableOpacity onPress={onClose} style={{ padding: 8 }} data-testid="decision-coach-editor-close-button" testID="decision-coach-editor-close-button">
              <Ionicons name="arrow-back" size={24} color={colors.text} />
            </TouchableOpacity>
            <Text style={{ fontSize: 18, fontWeight: '700', color: colors.text, flex: 1, textAlign: 'center', marginHorizontal: 8 }}>
              {editing.title}
            </Text>
            {editing.status !== 'decided' && (
              <TouchableOpacity
                onPress={() => setShowDecideModal(true)}
                style={{ padding: 8 }}
                data-testid="decision-coach-editor-open-decide-button"
                testID="decision-coach-editor-open-decide-button"
              >
                <Ionicons name="checkmark-circle" size={24} color={colors.success} />
              </TouchableOpacity>
            )}
          </View>
        </View>

        <ScrollView style={{ flex: 1 }} contentContainerStyle={{ padding: 16 }}>
          {/* Info Card */}
          <View style={{ backgroundColor: colors.card, borderRadius: 12, padding: 16, marginBottom: 16, borderWidth: 1, borderColor: colors.border }}>
            <Text style={{ fontSize: 16, fontWeight: '600', color: colors.text, marginBottom: 8 }}>
              {editing.framework_type.replace(/_/g, ' ')}
            </Text>
            <Text style={{ fontSize: 14, color: colors.textMuted }}>
              {editing.description || 'No description'}
            </Text>
          </View>

          {/* Framework Editor */}
          {editing.framework_type === 'pros_cons' && (
            <ProsConsEditor
              decision={editing}
              colors={colors}
              onSave={saveFrameworkData}
              saving={saving}
            />
          )}
          {editing.framework_type === 'swot' && (
            <SwotEditor
              decision={editing}
              colors={colors}
              onSave={saveFrameworkData}
              saving={saving}
            />
          )}
          {editing.framework_type === 'decision_matrix' && (
            <DecisionMatrixEditor
              decision={editing}
              colors={colors}
              onSave={saveFrameworkData}
              saving={saving}
            />
          )}
          {editing.framework_type === 'weighted_scoring' && (
            <WeightedScoringEditor
              decision={editing}
              colors={colors}
              onSave={saveFrameworkData}
              saving={saving}
            />
          )}

          {/* AI Analysis Button */}
          <TouchableOpacity
            onPress={runAIAnalysis}
            disabled={analyzing}
            style={{
              backgroundColor: colors.primary,
              padding: 16,
              borderRadius: 12,
              flexDirection: 'row',
              alignItems: 'center',
              justifyContent: 'center',
              marginTop: 16,
              marginBottom: 16,
            }}
            data-testid="decision-coach-editor-run-analysis-button"
            testID="decision-coach-editor-run-analysis-button"
          >
            {analyzing ? (
              <ActivityIndicator size="small" color={colors.primaryText} />
            ) : (
              <>
                <Ionicons name="sparkles" size={20} color={colors.primaryText} style={{ marginRight: 8 }} />
                <Text style={{ color: colors.primaryText, fontSize: 16, fontWeight: '600' }}>
                  {editing.ai_analysis ? 'Regenerate AI Analysis' : 'Generate AI Analysis'}
                </Text>
              </>
            )}
          </TouchableOpacity>

          {/* AI Analysis Results */}
          {editing.ai_analysis && (
            <View style={{ backgroundColor: colors.card, borderRadius: 12, padding: 16, borderWidth: 1, borderColor: colors.border, marginBottom: 16 }}>
              <Text style={{ fontSize: 16, fontWeight: '600', color: colors.text, marginBottom: 12 }}>
                AI Analysis
              </Text>
              <Text style={{ fontSize: 14, color: colors.text, marginBottom: 12 }}>
                {editing.ai_analysis.summary}
              </Text>
              <View style={{ backgroundColor: colors.primary + '20', padding: 12, borderRadius: 8, marginBottom: 12 }}>
                <Text style={{ fontSize: 13, fontWeight: '600', color: colors.primary, marginBottom: 4 }}>
                  Recommendation
                </Text>
                <Text style={{ fontSize: 14, color: colors.text }}>
                  {editing.ai_analysis.recommendation}
                </Text>
              </View>
              <View style={{ flexDirection: 'row', gap: 12, marginBottom: 12 }}>
                <View style={{ flex: 1, backgroundColor: colors.bgSecondary, padding: 12, borderRadius: 8 }}>
                  <Text style={{ fontSize: 12, color: colors.textMuted }}>Confidence</Text>
                  <Text style={{ fontSize: 18, fontWeight: '600', color: colors.text }}>
                    {editing.ai_analysis.confidence}%
                  </Text>
                </View>
                <View style={{ flex: 1, backgroundColor: colors.bgSecondary, padding: 12, borderRadius: 8 }}>
                  <Text style={{ fontSize: 12, color: colors.textMuted }}>Risk Level</Text>
                  <Text style={{ fontSize: 18, fontWeight: '600', color: colors.text }}>
                    {editing.ai_analysis.risk_level}
                  </Text>
                </View>
              </View>
              {editing.ai_analysis.key_insights && editing.ai_analysis.key_insights.length > 0 && (
                <View>
                  <Text style={{ fontSize: 14, fontWeight: '600', color: colors.text, marginBottom: 8 }}>
                    Key Insights
                  </Text>
                  {editing.ai_analysis.key_insights.map((insight, index) => (
                    <View key={index} style={{ flexDirection: 'row', marginBottom: 6 }}>
                      <Text style={{ color: colors.primary, marginRight: 8 }}>•</Text>
                      <Text style={{ flex: 1, fontSize: 13, color: colors.text }}>{insight}</Text>
                    </View>
                  ))}
                </View>
              )}
            </View>
          )}
        </ScrollView>

        {/* Decide Modal */}
        {showDecideModal && (
          <DecideModal
            colors={colors}
            visible={showDecideModal}
            onClose={() => setShowDecideModal(false)}
            onDecide={markAsDecided}
          />
        )}
      </View>
    </Modal>
  );
}

// Pros & Cons Editor
function ProsConsEditor({ decision, colors, onSave, saving }) {
  const [options, setOptions] = useState(
    decision.framework_data?.options || [
      { option_id: 'opt0', name: 'Option 1', pros: [], cons: [], score: 50 },
      { option_id: 'opt1', name: 'Option 2', pros: [], cons: [], score: 50 },
    ]
  );

  const addOption = () => {
    const newOption = {
      option_id: `opt${options.length}`,
      name: `Option ${options.length + 1}`,
      pros: [],
      cons: [],
      score: 50,
    };
    const updated = [...options, newOption];
    setOptions(updated);
    onSave({ options: updated });
  };

  const updateOptionName = (index, name) => {
    const updated = [...options];
    updated[index].name = name;
    setOptions(updated);
  };

  const addProCon = (optionIndex, type) => {
    const updated = [...options];
    const newItem = {
      item_id: `${type}_${Date.now()}`,
      text: '',
      weight: 5,
    };
    updated[optionIndex][type].push(newItem);
    setOptions(updated);
  };

  const updateProCon = (optionIndex, type, itemIndex, field, value) => {
    const updated = [...options];
    updated[optionIndex][type][itemIndex][field] = value;
    setOptions(updated);
  };

  const removeProCon = (optionIndex, type, itemIndex) => {
    const updated = [...options];
    updated[optionIndex][type].splice(itemIndex, 1);
    setOptions(updated);
  };

  const saveChanges = () => {
    onSave({ options });
  };

  return (
    <View style={{ marginBottom: 16 }}>
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
        <Text style={{ fontSize: 16, fontWeight: '600', color: colors.text }}>
          Compare Options
        </Text>
        <TouchableOpacity
          onPress={addOption}
          style={{
            flexDirection: 'row',
            alignItems: 'center',
            backgroundColor: colors.primary + '20',
            paddingHorizontal: 12,
            paddingVertical: 6,
            borderRadius: 8,
          }}
        data-testid="decision-coach-pros-cons-add-option-button"
        testID="decision-coach-pros-cons-add-option-button"
        >
          <Ionicons name="add" size={16} color={colors.primary} />
          <Text style={{ color: colors.primary, fontSize: 13, fontWeight: '600', marginLeft: 4 }}>
            Add Option
          </Text>
        </TouchableOpacity>
      </View>

      {options.map((option, optIndex) => (
        <View
          key={option.option_id}
          style={{
            backgroundColor: colors.card,
            borderRadius: 12,
            padding: 16,
            marginBottom: 12,
            borderWidth: 1,
            borderColor: colors.border,
          }}
        >
          <TextInput
            value={option.name}
            onChangeText={(text) => updateOptionName(optIndex, text)}
            onBlur={saveChanges}
            placeholder="Option name"
            placeholderTextColor={colors.textMuted}
            style={{
              backgroundColor: colors.bgSecondary,
              color: colors.text,
              padding: 12,
              borderRadius: 8,
              fontSize: 16,
              fontWeight: '600',
              marginBottom: 12,
            }}
            data-testid={`decision-coach-pros-cons-option-name-input-${optIndex}`}
            testID={`decision-coach-pros-cons-option-name-input-${optIndex}`}
          />

          {/* Pros */}
          <View style={{ marginBottom: 12 }}>
            <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
              <Text style={{ fontSize: 14, fontWeight: '600', color: colors.success }}>
                ✓ Pros
              </Text>
              <TouchableOpacity
                onPress={() => addProCon(optIndex, 'pros')}
                style={{ padding: 4 }}
                data-testid={`decision-coach-pros-cons-add-pro-button-${optIndex}`}
                testID={`decision-coach-pros-cons-add-pro-button-${optIndex}`}
              >
                <Ionicons name="add-circle" size={20} color={colors.success} />
              </TouchableOpacity>
            </View>
            {option.pros.map((pro, proIndex) => (
              <View key={pro.item_id} style={{ flexDirection: 'row', gap: 8, marginBottom: 8 }}>
                <TextInput
                  value={pro.text}
                  onChangeText={(text) => updateProCon(optIndex, 'pros', proIndex, 'text', text)}
                  onBlur={saveChanges}
                  placeholder="Add a pro..."
                  placeholderTextColor={colors.textMuted}
                  style={{
                    flex: 1,
                    backgroundColor: colors.bgSecondary,
                    color: colors.text,
                    padding: 10,
                    borderRadius: 8,
                    fontSize: 14,
                  }}
                  data-testid={`decision-coach-pros-cons-pro-input-${optIndex}-${proIndex}`}
                  testID={`decision-coach-pros-cons-pro-input-${optIndex}-${proIndex}`}
                />
                <TouchableOpacity
                  onPress={() => removeProCon(optIndex, 'pros', proIndex)}
                  style={{
                    backgroundColor: colors.error + '20',
                    padding: 10,
                    borderRadius: 8,
                    justifyContent: 'center',
                  }}
                  data-testid={`decision-coach-pros-cons-remove-pro-button-${optIndex}-${proIndex}`}
                  testID={`decision-coach-pros-cons-remove-pro-button-${optIndex}-${proIndex}`}
                >
                  <Ionicons name="trash-outline" size={16} color={colors.error} />
                </TouchableOpacity>
              </View>
            ))}
          </View>

          {/* Cons */}
          <View>
            <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
              <Text style={{ fontSize: 14, fontWeight: '600', color: colors.error }}>
                ✗ Cons
              </Text>
              <TouchableOpacity
                onPress={() => addProCon(optIndex, 'cons')}
                style={{ padding: 4 }}
                data-testid={`decision-coach-pros-cons-add-con-button-${optIndex}`}
                testID={`decision-coach-pros-cons-add-con-button-${optIndex}`}
              >
                <Ionicons name="add-circle" size={20} color={colors.error} />
              </TouchableOpacity>
            </View>
            {option.cons.map((con, conIndex) => (
              <View key={con.item_id} style={{ flexDirection: 'row', gap: 8, marginBottom: 8 }}>
                <TextInput
                  value={con.text}
                  onChangeText={(text) => updateProCon(optIndex, 'cons', conIndex, 'text', text)}
                  onBlur={saveChanges}
                  placeholder="Add a con..."
                  placeholderTextColor={colors.textMuted}
                  style={{
                    flex: 1,
                    backgroundColor: colors.bgSecondary,
                    color: colors.text,
                    padding: 10,
                    borderRadius: 8,
                    fontSize: 14,
                  }}
                  data-testid={`decision-coach-pros-cons-con-input-${optIndex}-${conIndex}`}
                  testID={`decision-coach-pros-cons-con-input-${optIndex}-${conIndex}`}
                />
                <TouchableOpacity
                  onPress={() => removeProCon(optIndex, 'cons', conIndex)}
                  style={{
                    backgroundColor: colors.error + '20',
                    padding: 10,
                    borderRadius: 8,
                    justifyContent: 'center',
                  }}
                  data-testid={`decision-coach-pros-cons-remove-con-button-${optIndex}-${conIndex}`}
                  testID={`decision-coach-pros-cons-remove-con-button-${optIndex}-${conIndex}`}
                >
                  <Ionicons name="trash-outline" size={16} color={colors.error} />
                </TouchableOpacity>
              </View>
            ))}
          </View>

          {/* Score display */}
          <View style={{ backgroundColor: colors.bgSecondary, padding: 12, borderRadius: 8, marginTop: 12 }}>
            <Text style={{ fontSize: 12, color: colors.textMuted }}>
              Score: {option.pros.length} pros, {option.cons.length} cons
            </Text>
          </View>
        </View>
      ))}

      <TouchableOpacity
        onPress={saveChanges}
        disabled={saving}
        style={{
          backgroundColor: colors.primary,
          padding: 14,
          borderRadius: 8,
          alignItems: 'center',
          marginTop: 8,
        }}
        data-testid="decision-coach-pros-cons-save-button"
        testID="decision-coach-pros-cons-save-button"
      >
        {saving ? (
          <ActivityIndicator size="small" color={colors.primaryText} />
        ) : (
          <Text style={{ color: colors.primaryText, fontWeight: '600' }}>Save Changes</Text>
        )}
      </TouchableOpacity>
    </View>
  );
}

// SWOT Editor
function SwotEditor({ decision, colors, onSave, saving }) {
  const [swot, setSwot] = useState(
    decision.framework_data || {
      strengths: [],
      weaknesses: [],
      opportunities: [],
      threats: [],
    }
  );

  const addItem = (quadrant) => {
    const updated = { ...swot };
    updated[quadrant] = [...updated[quadrant], ''];
    setSwot(updated);
  };

  const updateItem = (quadrant, index, value) => {
    const updated = { ...swot };
    updated[quadrant][index] = value;
    setSwot(updated);
  };

  const removeItem = (quadrant, index) => {
    const updated = { ...swot };
    updated[quadrant].splice(index, 1);
    setSwot(updated);
  };

  const saveChanges = () => {
    onSave(swot);
  };

  const quadrants = [
    { key: 'strengths', label: 'Strengths', icon: 'shield-checkmark', color: colors.success },
    { key: 'weaknesses', label: 'Weaknesses', icon: 'warning', color: colors.error },
    { key: 'opportunities', label: 'Opportunities', icon: 'trending-up', color: colors.primary },
    { key: 'threats', label: 'Threats', icon: 'alert-circle', color: colors.warning },
  ];

  return (
    <View style={{ marginBottom: 16 }}>
      <Text style={{ fontSize: 16, fontWeight: '600', color: colors.text, marginBottom: 12 }}>
        SWOT Analysis
      </Text>

      {quadrants.map((quadrant) => (
        <View
          key={quadrant.key}
          style={{
            backgroundColor: colors.card,
            borderRadius: 12,
            padding: 16,
            marginBottom: 12,
            borderWidth: 1,
            borderColor: colors.border,
          }}
        >
          <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
            <View style={{ flexDirection: 'row', alignItems: 'center' }}>
              <Ionicons name={quadrant.icon} size={20} color={quadrant.color} style={{ marginRight: 8 }} />
              <Text style={{ fontSize: 16, fontWeight: '600', color: colors.text }}>
                {quadrant.label}
              </Text>
            </View>
            <TouchableOpacity
              onPress={() => addItem(quadrant.key)}
              style={{ padding: 4 }}
              data-testid={`decision-coach-swot-add-item-button-${quadrant.key}`}
              testID={`decision-coach-swot-add-item-button-${quadrant.key}`}
            >
              <Ionicons name="add-circle" size={20} color={quadrant.color} />
            </TouchableOpacity>
          </View>

          {swot[quadrant.key].map((item, index) => (
            <View key={index} style={{ flexDirection: 'row', gap: 8, marginBottom: 8 }}>
              <TextInput
                value={item}
                onChangeText={(text) => updateItem(quadrant.key, index, text)}
                onBlur={saveChanges}
                placeholder={`Add ${quadrant.label.toLowerCase()}...`}
                placeholderTextColor={colors.textMuted}
                style={{
                  flex: 1,
                  backgroundColor: colors.bgSecondary,
                  color: colors.text,
                  padding: 10,
                  borderRadius: 8,
                  fontSize: 14,
                }}
                data-testid={`decision-coach-swot-item-input-${quadrant.key}-${index}`}
                testID={`decision-coach-swot-item-input-${quadrant.key}-${index}`}
              />
              <TouchableOpacity
                onPress={() => removeItem(quadrant.key, index)}
                style={{
                  backgroundColor: colors.error + '20',
                  padding: 10,
                  borderRadius: 8,
                  justifyContent: 'center',
                }}
                data-testid={`decision-coach-swot-remove-item-button-${quadrant.key}-${index}`}
                testID={`decision-coach-swot-remove-item-button-${quadrant.key}-${index}`}
              >
                <Ionicons name="trash-outline" size={16} color={colors.error} />
              </TouchableOpacity>
            </View>
          ))}

          {swot[quadrant.key].length === 0 && (
            <Text style={{ fontSize: 13, color: colors.textMuted, fontStyle: 'italic' }}>
              No {quadrant.label.toLowerCase()} added yet
            </Text>
          )}
        </View>
      ))}

      <TouchableOpacity
        onPress={saveChanges}
        disabled={saving}
        style={{
          backgroundColor: colors.primary,
          padding: 14,
          borderRadius: 8,
          alignItems: 'center',
        }}
        data-testid="decision-coach-swot-save-button"
        testID="decision-coach-swot-save-button"
      >
        {saving ? (
          <ActivityIndicator size="small" color={colors.primaryText} />
        ) : (
          <Text style={{ color: colors.primaryText, fontWeight: '600' }}>Save Changes</Text>
        )}
      </TouchableOpacity>
    </View>
  );
}

// Decision Matrix Editor (Full Implementation)
function DecisionMatrixEditor({ decision, colors, onSave, saving }) {
  const [matrix, setMatrix] = useState(
    decision.framework_data || {
      criteria: [
        { criteria_id: 'crit0', name: 'Cost', weight: 5, description: '' },
        { criteria_id: 'crit1', name: 'Quality', weight: 5, description: '' },
      ],
      options: [
        { option_id: 'opt0', name: 'Option 1', scores: {} },
        { option_id: 'opt1', name: 'Option 2', scores: {} },
      ],
    }
  );

  const addCriteria = () => {
    const newCriteria = {
      criteria_id: `crit${matrix.criteria.length}`,
      name: `Criteria ${matrix.criteria.length + 1}`,
      weight: 5,
      description: '',
    };
    const updated = { ...matrix, criteria: [...matrix.criteria, newCriteria] };
    setMatrix(updated);
  };

  const updateCriteria = (index, field, value) => {
    const updated = { ...matrix };
    updated.criteria[index][field] = value;
    setMatrix(updated);
  };

  const removeCriteria = (index) => {
    const updated = { ...matrix };
    const criteriaId = updated.criteria[index].criteria_id;
    updated.criteria.splice(index, 1);
    // Remove scores for this criteria from all options
    updated.options.forEach(opt => delete opt.scores[criteriaId]);
    setMatrix(updated);
  };

  const addOption = () => {
    const newOption = {
      option_id: `opt${matrix.options.length}`,
      name: `Option ${matrix.options.length + 1}`,
      scores: {},
    };
    const updated = { ...matrix, options: [...matrix.options, newOption] };
    setMatrix(updated);
  };

  const updateOptionName = (index, name) => {
    const updated = { ...matrix };
    updated.options[index].name = name;
    setMatrix(updated);
  };

  const updateScore = (optionIndex, criteriaId, score) => {
    const updated = { ...matrix };
    updated.options[optionIndex].scores[criteriaId] = parseInt(score) || 0;
    setMatrix(updated);
  };

  const removeOption = (index) => {
    const updated = { ...matrix };
    updated.options.splice(index, 1);
    setMatrix(updated);
  };

  const calculateTotalScore = (option) => {
    let total = 0;
    matrix.criteria.forEach(criteria => {
      const score = option.scores[criteria.criteria_id] || 0;
      total += score * criteria.weight;
    });
    return total;
  };

  const saveChanges = () => {
    onSave(matrix);
  };

  return (
    <View style={{ marginBottom: 16 }}>
      {/* Criteria Section */}
      <View style={{ marginBottom: 16 }}>
        <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
          <Text style={{ fontSize: 16, fontWeight: '600', color: colors.text }}>
            Criteria (Factors)
          </Text>
          <TouchableOpacity
            onPress={addCriteria}
            style={{
              flexDirection: 'row',
              alignItems: 'center',
              backgroundColor: colors.primary + '20',
              paddingHorizontal: 12,
              paddingVertical: 6,
              borderRadius: 8,
            }}
            data-testid="decision-coach-matrix-add-criteria-button"
            testID="decision-coach-matrix-add-criteria-button"
          >
            <Ionicons name="add" size={16} color={colors.primary} />
            <Text style={{ color: colors.primary, fontSize: 13, fontWeight: '600', marginLeft: 4 }}>
              Add Criteria
            </Text>
          </TouchableOpacity>
        </View>

        {matrix.criteria.map((criteria, index) => (
          <View
            key={criteria.criteria_id}
            style={{
              backgroundColor: colors.card,
              borderRadius: 12,
              padding: 12,
              marginBottom: 8,
              borderWidth: 1,
              borderColor: colors.border,
            }}
          >
            <View style={{ flexDirection: 'row', gap: 8, alignItems: 'center' }}>
              <TextInput
                value={criteria.name}
                onChangeText={(text) => updateCriteria(index, 'name', text)}
                onBlur={saveChanges}
                placeholder="Criteria name"
                placeholderTextColor={colors.textMuted}
                style={{
                  flex: 1,
                  backgroundColor: colors.bgSecondary,
                  color: colors.text,
                  padding: 10,
                  borderRadius: 8,
                  fontSize: 14,
                  fontWeight: '600',
                }}
                data-testid={`decision-coach-matrix-criteria-name-input-${index}`}
                testID={`decision-coach-matrix-criteria-name-input-${index}`}
              />
              <View style={{ flexDirection: 'row', alignItems: 'center', backgroundColor: colors.bgSecondary, borderRadius: 8, paddingHorizontal: 12, paddingVertical: 10 }}>
                <Text style={{ fontSize: 12, color: colors.textMuted, marginRight: 4 }}>Weight:</Text>
                <TextInput
                  value={String(criteria.weight)}
                  onChangeText={(text) => updateCriteria(index, 'weight', parseInt(text) || 1)}
                  onBlur={saveChanges}
                  keyboardType="number-pad"
                  style={{
                    color: colors.text,
                    fontSize: 14,
                    fontWeight: '600',
                    width: 30,
                    textAlign: 'center',
                  }}
                  data-testid={`decision-coach-matrix-criteria-weight-input-${index}`}
                  testID={`decision-coach-matrix-criteria-weight-input-${index}`}
                />
              </View>
              <TouchableOpacity
                onPress={() => removeCriteria(index)}
                style={{
                  backgroundColor: colors.error + '20',
                  padding: 10,
                  borderRadius: 8,
                }}
                data-testid={`decision-coach-matrix-remove-criteria-button-${index}`}
                testID={`decision-coach-matrix-remove-criteria-button-${index}`}
              >
                <Ionicons name="trash-outline" size={16} color={colors.error} />
              </TouchableOpacity>
            </View>
          </View>
        ))}
      </View>

      {/* Options & Scoring Grid */}
      <View style={{ marginBottom: 16 }}>
        <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
          <Text style={{ fontSize: 16, fontWeight: '600', color: colors.text }}>
            Options & Scores
          </Text>
          <TouchableOpacity
            onPress={addOption}
            style={{
              flexDirection: 'row',
              alignItems: 'center',
              backgroundColor: colors.success + '20',
              paddingHorizontal: 12,
              paddingVertical: 6,
              borderRadius: 8,
            }}
            data-testid="decision-coach-matrix-add-option-button"
            testID="decision-coach-matrix-add-option-button"
          >
            <Ionicons name="add" size={16} color={colors.success} />
            <Text style={{ color: colors.success, fontSize: 13, fontWeight: '600', marginLeft: 4 }}>
              Add Option
            </Text>
          </TouchableOpacity>
        </View>

        {matrix.options.map((option, optIndex) => (
          <View
            key={option.option_id}
            style={{
              backgroundColor: colors.card,
              borderRadius: 12,
              padding: 16,
              marginBottom: 12,
              borderWidth: 1,
              borderColor: colors.border,
            }}
          >
            <View style={{ flexDirection: 'row', gap: 8, marginBottom: 12 }}>
              <TextInput
                value={option.name}
                onChangeText={(text) => updateOptionName(optIndex, text)}
                onBlur={saveChanges}
                placeholder="Option name"
                placeholderTextColor={colors.textMuted}
                style={{
                  flex: 1,
                  backgroundColor: colors.bgSecondary,
                  color: colors.text,
                  padding: 12,
                  borderRadius: 8,
                  fontSize: 16,
                  fontWeight: '600',
                }}
                data-testid={`decision-coach-matrix-option-name-input-${optIndex}`}
                testID={`decision-coach-matrix-option-name-input-${optIndex}`}
              />
              <TouchableOpacity
                onPress={() => removeOption(optIndex)}
                style={{
                  backgroundColor: colors.error + '20',
                  padding: 12,
                  borderRadius: 8,
                  justifyContent: 'center',
                }}
                data-testid={`decision-coach-matrix-remove-option-button-${optIndex}`}
                testID={`decision-coach-matrix-remove-option-button-${optIndex}`}
              >
                <Ionicons name="trash-outline" size={18} color={colors.error} />
              </TouchableOpacity>
            </View>

            {/* Score inputs for each criteria */}
            {matrix.criteria.map((criteria) => (
              <View
                key={criteria.criteria_id}
                style={{
                  flexDirection: 'row',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  paddingVertical: 8,
                  borderBottomWidth: 1,
                  borderBottomColor: colors.border,
                }}
              >
                <Text style={{ flex: 1, color: colors.text, fontSize: 14 }}>
                  {criteria.name}
                </Text>
                <View style={{ flexDirection: 'row', alignItems: 'center' }}>
                  <Text style={{ fontSize: 12, color: colors.textMuted, marginRight: 8 }}>
                    Score (1-10):
                  </Text>
                  <TextInput
                    value={String(option.scores[criteria.criteria_id] || '')}
                    onChangeText={(text) => updateScore(optIndex, criteria.criteria_id, text)}
                    onBlur={saveChanges}
                    keyboardType="number-pad"
                    placeholder="0"
                    placeholderTextColor={colors.textMuted}
                    style={{
                      backgroundColor: colors.bgSecondary,
                      color: colors.text,
                      padding: 8,
                      borderRadius: 6,
                      fontSize: 14,
                      fontWeight: '600',
                      width: 50,
                      textAlign: 'center',
                    }}
                    data-testid={`decision-coach-matrix-score-input-${optIndex}-${criteria.criteria_id}`}
                    testID={`decision-coach-matrix-score-input-${optIndex}-${criteria.criteria_id}`}
                  />
                </View>
              </View>
            ))}

            {/* Total weighted score */}
            <View style={{ backgroundColor: colors.primary + '20', padding: 12, borderRadius: 8, marginTop: 12 }}>
              <Text style={{ fontSize: 14, fontWeight: '600', color: colors.primary, textAlign: 'center' }}>
                Total Weighted Score: {calculateTotalScore(option)}
              </Text>
            </View>
          </View>
        ))}
      </View>

      <TouchableOpacity
        onPress={saveChanges}
        disabled={saving}
        style={{
          backgroundColor: colors.primary,
          padding: 14,
          borderRadius: 8,
          alignItems: 'center',
        }}
        data-testid="decision-coach-matrix-save-button"
        testID="decision-coach-matrix-save-button"
      >
        {saving ? (
          <ActivityIndicator size="small" color={colors.primaryText} />
        ) : (
          <Text style={{ color: colors.primaryText, fontWeight: '600' }}>Save Changes</Text>
        )}
      </TouchableOpacity>
    </View>
  );
}

// Weighted Scoring Editor (Full Implementation)
function WeightedScoringEditor({ decision, colors, onSave, saving }) {
  const [scoring, setScoring] = useState(
    decision.framework_data || {
      factors: [
        { factor_id: 'fac0', name: 'Factor 1', weight: 5, description: '' },
      ],
      options: [
        { option_id: 'opt0', name: 'Option 1', factor_scores: {} },
      ],
    }
  );

  const addFactor = () => {
    const newFactor = {
      factor_id: `fac${scoring.factors.length}`,
      name: `Factor ${scoring.factors.length + 1}`,
      weight: 5,
      description: '',
    };
    const updated = { ...scoring, factors: [...scoring.factors, newFactor] };
    setScoring(updated);
  };

  const updateFactor = (index, field, value) => {
    const updated = { ...scoring };
    updated.factors[index][field] = value;
    setScoring(updated);
  };

  const removeFactor = (index) => {
    const updated = { ...scoring };
    const factorId = updated.factors[index].factor_id;
    updated.factors.splice(index, 1);
    updated.options.forEach(opt => delete opt.factor_scores[factorId]);
    setScoring(updated);
  };

  const addOption = () => {
    const newOption = {
      option_id: `opt${scoring.options.length}`,
      name: `Option ${scoring.options.length + 1}`,
      factor_scores: {},
    };
    const updated = { ...scoring, options: [...scoring.options, newOption] };
    setScoring(updated);
  };

  const updateOptionName = (index, name) => {
    const updated = { ...scoring };
    updated.options[index].name = name;
    setScoring(updated);
  };

  const updateFactorScore = (optionIndex, factorId, score) => {
    const updated = { ...scoring };
    updated.options[optionIndex].factor_scores[factorId] = parseInt(score) || 0;
    setScoring(updated);
  };

  const removeOption = (index) => {
    const updated = { ...scoring };
    updated.options.splice(index, 1);
    setScoring(updated);
  };

  const calculateWeightedScore = (option) => {
    let total = 0;
    let maxPossible = 0;
    scoring.factors.forEach(factor => {
      const score = option.factor_scores[factor.factor_id] || 0;
      total += score * factor.weight;
      maxPossible += 10 * factor.weight; // Max score is 10
    });
    return maxPossible > 0 ? Math.round((total / maxPossible) * 100) : 0;
  };

  const saveChanges = () => {
    onSave(scoring);
  };

  return (
    <View style={{ marginBottom: 16 }}>
      <View style={{ backgroundColor: colors.info + '20', padding: 12, borderRadius: 8, marginBottom: 16 }}>
        <Text style={{ fontSize: 13, color: colors.text }}>
          💡 Weighted scoring uses factors with different importance levels. Score each option (1-10) per factor.
        </Text>
      </View>

      {/* Factors Section */}
      <View style={{ marginBottom: 16 }}>
        <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
          <Text style={{ fontSize: 16, fontWeight: '600', color: colors.text }}>
            Evaluation Factors
          </Text>
          <TouchableOpacity
            onPress={addFactor}
            style={{
              flexDirection: 'row',
              alignItems: 'center',
              backgroundColor: colors.primary + '20',
              paddingHorizontal: 12,
              paddingVertical: 6,
              borderRadius: 8,
            }}
            data-testid="decision-coach-weighted-add-factor-button"
            testID="decision-coach-weighted-add-factor-button"
          >
            <Ionicons name="add" size={16} color={colors.primary} />
            <Text style={{ color: colors.primary, fontSize: 13, fontWeight: '600', marginLeft: 4 }}>
              Add Factor
            </Text>
          </TouchableOpacity>
        </View>

        {scoring.factors.map((factor, index) => (
          <View
            key={factor.factor_id}
            style={{
              backgroundColor: colors.card,
              borderRadius: 12,
              padding: 12,
              marginBottom: 8,
              borderWidth: 1,
              borderColor: colors.border,
            }}
          >
            <View style={{ flexDirection: 'row', gap: 8, marginBottom: 8 }}>
              <TextInput
                value={factor.name}
                onChangeText={(text) => updateFactor(index, 'name', text)}
                onBlur={saveChanges}
                placeholder="Factor name"
                placeholderTextColor={colors.textMuted}
                style={{
                  flex: 1,
                  backgroundColor: colors.bgSecondary,
                  color: colors.text,
                  padding: 10,
                  borderRadius: 8,
                  fontSize: 14,
                  fontWeight: '600',
                }}
                data-testid={`decision-coach-weighted-factor-name-input-${index}`}
                testID={`decision-coach-weighted-factor-name-input-${index}`}
              />
              <View style={{ flexDirection: 'row', alignItems: 'center', backgroundColor: colors.bgSecondary, borderRadius: 8, paddingHorizontal: 12, paddingVertical: 10 }}>
                <Text style={{ fontSize: 12, color: colors.textMuted, marginRight: 4 }}>Weight:</Text>
                <TextInput
                  value={String(factor.weight)}
                  onChangeText={(text) => updateFactor(index, 'weight', parseInt(text) || 1)}
                  onBlur={saveChanges}
                  keyboardType="number-pad"
                  style={{
                    color: colors.text,
                    fontSize: 14,
                    fontWeight: '600',
                    width: 30,
                    textAlign: 'center',
                  }}
                  data-testid={`decision-coach-weighted-factor-weight-input-${index}`}
                  testID={`decision-coach-weighted-factor-weight-input-${index}`}
                />
              </View>
              <TouchableOpacity
                onPress={() => removeFactor(index)}
                style={{
                  backgroundColor: colors.error + '20',
                  padding: 10,
                  borderRadius: 8,
                }}
                data-testid={`decision-coach-weighted-remove-factor-button-${index}`}
                testID={`decision-coach-weighted-remove-factor-button-${index}`}
              >
                <Ionicons name="trash-outline" size={16} color={colors.error} />
              </TouchableOpacity>
            </View>
            <TextInput
              value={factor.description}
              onChangeText={(text) => updateFactor(index, 'description', text)}
              onBlur={saveChanges}
              placeholder="Optional description..."
              placeholderTextColor={colors.textMuted}
              style={{
                backgroundColor: colors.bgSecondary,
                color: colors.text,
                padding: 8,
                borderRadius: 6,
                fontSize: 12,
              }}
              data-testid={`decision-coach-weighted-factor-description-input-${index}`}
              testID={`decision-coach-weighted-factor-description-input-${index}`}
            />
          </View>
        ))}
      </View>

      {/* Options & Scoring */}
      <View style={{ marginBottom: 16 }}>
        <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
          <Text style={{ fontSize: 16, fontWeight: '600', color: colors.text }}>
            Score Options
          </Text>
          <TouchableOpacity
            onPress={addOption}
            style={{
              flexDirection: 'row',
              alignItems: 'center',
              backgroundColor: colors.success + '20',
              paddingHorizontal: 12,
              paddingVertical: 6,
              borderRadius: 8,
            }}
            data-testid="decision-coach-weighted-add-option-button"
            testID="decision-coach-weighted-add-option-button"
          >
            <Ionicons name="add" size={16} color={colors.success} />
            <Text style={{ color: colors.success, fontSize: 13, fontWeight: '600', marginLeft: 4 }}>
              Add Option
            </Text>
          </TouchableOpacity>
        </View>

        {scoring.options.map((option, optIndex) => (
          <View
            key={option.option_id}
            style={{
              backgroundColor: colors.card,
              borderRadius: 12,
              padding: 16,
              marginBottom: 12,
              borderWidth: 1,
              borderColor: colors.border,
            }}
          >
            <View style={{ flexDirection: 'row', gap: 8, marginBottom: 12 }}>
              <TextInput
                value={option.name}
                onChangeText={(text) => updateOptionName(optIndex, text)}
                onBlur={saveChanges}
                placeholder="Option name"
                placeholderTextColor={colors.textMuted}
                style={{
                  flex: 1,
                  backgroundColor: colors.bgSecondary,
                  color: colors.text,
                  padding: 12,
                  borderRadius: 8,
                  fontSize: 16,
                  fontWeight: '600',
                }}
                data-testid={`decision-coach-weighted-option-name-input-${optIndex}`}
                testID={`decision-coach-weighted-option-name-input-${optIndex}`}
              />
              <TouchableOpacity
                onPress={() => removeOption(optIndex)}
                style={{
                  backgroundColor: colors.error + '20',
                  padding: 12,
                  borderRadius: 8,
                  justifyContent: 'center',
                }}
                data-testid={`decision-coach-weighted-remove-option-button-${optIndex}`}
                testID={`decision-coach-weighted-remove-option-button-${optIndex}`}
              >
                <Ionicons name="trash-outline" size={18} color={colors.error} />
              </TouchableOpacity>
            </View>

            {/* Factor scores */}
            {scoring.factors.map((factor) => (
              <View
                key={factor.factor_id}
                style={{
                  flexDirection: 'row',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  paddingVertical: 8,
                  borderBottomWidth: 1,
                  borderBottomColor: colors.border,
                }}
              >
                <View style={{ flex: 1 }}>
                  <Text style={{ color: colors.text, fontSize: 14, fontWeight: '500' }}>
                    {factor.name}
                  </Text>
                  {factor.description && (
                    <Text style={{ color: colors.textMuted, fontSize: 11, marginTop: 2 }}>
                      {factor.description}
                    </Text>
                  )}
                </View>
                <View style={{ flexDirection: 'row', alignItems: 'center' }}>
                  <Text style={{ fontSize: 12, color: colors.textMuted, marginRight: 8 }}>
                    1-10:
                  </Text>
                  <TextInput
                    value={String(option.factor_scores[factor.factor_id] || '')}
                    onChangeText={(text) => updateFactorScore(optIndex, factor.factor_id, text)}
                    onBlur={saveChanges}
                    keyboardType="number-pad"
                    placeholder="0"
                    placeholderTextColor={colors.textMuted}
                    style={{
                      backgroundColor: colors.bgSecondary,
                      color: colors.text,
                      padding: 8,
                      borderRadius: 6,
                      fontSize: 14,
                      fontWeight: '600',
                      width: 50,
                      textAlign: 'center',
                    }}
                    data-testid={`decision-coach-weighted-score-input-${optIndex}-${factor.factor_id}`}
                    testID={`decision-coach-weighted-score-input-${optIndex}-${factor.factor_id}`}
                  />
                </View>
              </View>
            ))}

            {/* Weighted Score */}
            <View style={{ backgroundColor: colors.success + '20', padding: 12, borderRadius: 8, marginTop: 12 }}>
              <Text style={{ fontSize: 14, fontWeight: '600', color: colors.success, textAlign: 'center' }}>
                Weighted Score: {calculateWeightedScore(option)}%
              </Text>
            </View>
          </View>
        ))}
      </View>

      <TouchableOpacity
        onPress={saveChanges}
        disabled={saving}
        style={{
          backgroundColor: colors.primary,
          padding: 14,
          borderRadius: 8,
          alignItems: 'center',
        }}
        data-testid="decision-coach-weighted-save-button"
        testID="decision-coach-weighted-save-button"
      >
        {saving ? (
          <ActivityIndicator size="small" color={colors.primaryText} />
        ) : (
          <Text style={{ color: colors.primaryText, fontWeight: '600' }}>Save Changes</Text>
        )}
      </TouchableOpacity>
    </View>
  );
}

// Decide Modal
function DecideModal({ colors, visible, onClose, onDecide }) {
  const [finalChoice, setFinalChoice] = useState('');
  const [confidence, setConfidence] = useState(70);
  const [notes, setNotes] = useState('');

  const handleDecide = () => {
    if (!finalChoice.trim()) {
      Alert.alert('Error', 'Please enter your final decision');
      return;
    }
    onDecide(finalChoice, confidence, notes);
  };

  return (
    <Modal visible={visible} animationType="fade" transparent testID="decision-coach-decide-modal" data-testid="decision-coach-decide-modal">
      <View style={{ flex: 1, backgroundColor: 'rgba(0,0,0,0.5)', justifyContent: 'center', padding: 16 }} data-testid="decision-coach-decide-modal-overlay" testID="decision-coach-decide-modal-overlay">
        <View style={{ backgroundColor: colors.card, borderRadius: 16, padding: 24, maxWidth: 500, width: '100%', alignSelf: 'center' }} data-testid="decision-coach-decide-modal-content" testID="decision-coach-decide-modal-content">
          <Text style={{ fontSize: 20, fontWeight: '700', color: colors.text, marginBottom: 16 }}>
            Mark as Decided
          </Text>

          <Text style={{ fontSize: 14, color: colors.textMuted, marginBottom: 8 }}>Final Decision</Text>
          <TextInput
            value={finalChoice}
            onChangeText={setFinalChoice}
            placeholder="e.g., I decided to switch careers"
            placeholderTextColor={colors.textMuted}
            style={{
              backgroundColor: colors.bgSecondary,
              color: colors.text,
              padding: 12,
              borderRadius: 8,
              fontSize: 14,
              marginBottom: 16,
              borderWidth: 1,
              borderColor: colors.border,
            }}
            data-testid="decision-coach-decide-final-choice-input"
            testID="decision-coach-decide-final-choice-input"
          />

          <Text style={{ fontSize: 14, color: colors.textMuted, marginBottom: 8 }}>
            Confidence: {confidence}%
          </Text>
          <View style={{ flexDirection: 'row', alignItems: 'center', marginBottom: 16 }}>
            <Text style={{ color: colors.textMuted, marginRight: 8 }}>0%</Text>
            <View style={{ flex: 1, height: 40, justifyContent: 'center' }}>
              <View style={{ height: 6, backgroundColor: colors.bgSecondary, borderRadius: 3 }} />
              <TouchableOpacity
                onPress={(e) => {
                  // Simple slider simulation - in production use a proper slider component
                  const newConfidence = Math.round((e.nativeEvent.pageX / 300) * 100);
                  setConfidence(Math.min(100, Math.max(0, newConfidence)));
                }}
                style={{
                  position: 'absolute',
                  left: `${confidence}%`,
                  width: 20,
                  height: 20,
                  borderRadius: 10,
                  backgroundColor: colors.primary,
                  marginLeft: -10,
                }}
                data-testid="decision-coach-decide-confidence-slider"
                testID="decision-coach-decide-confidence-slider"
              />
            </View>
            <Text style={{ color: colors.textMuted, marginLeft: 8 }}>100%</Text>
          </View>

          <Text style={{ fontSize: 14, color: colors.textMuted, marginBottom: 8 }}>Notes (Optional)</Text>
          <TextInput
            value={notes}
            onChangeText={setNotes}
            placeholder="Any additional thoughts..."
            placeholderTextColor={colors.textMuted}
            multiline
            numberOfLines={3}
            style={{
              backgroundColor: colors.bgSecondary,
              color: colors.text,
              padding: 12,
              borderRadius: 8,
              fontSize: 14,
              marginBottom: 24,
              borderWidth: 1,
              borderColor: colors.border,
              minHeight: 80,
            }}
            data-testid="decision-coach-decide-notes-input"
            testID="decision-coach-decide-notes-input"
          />

          <View style={{ flexDirection: 'row', gap: 12 }}>
            <TouchableOpacity
              onPress={onClose}
              style={{
                flex: 1,
                backgroundColor: colors.bgSecondary,
                padding: 14,
                borderRadius: 8,
                alignItems: 'center',
              }}
              data-testid="decision-coach-decide-cancel-button"
              testID="decision-coach-decide-cancel-button"
            >
              <Text style={{ color: colors.text, fontWeight: '600' }}>Cancel</Text>
            </TouchableOpacity>

            <TouchableOpacity
              onPress={handleDecide}
              style={{
                flex: 1,
                backgroundColor: colors.success,
                padding: 14,
                borderRadius: 8,
                alignItems: 'center',
              }}
              data-testid="decision-coach-decide-submit-button"
              testID="decision-coach-decide-submit-button"
            >
              <Text style={{ color: colors.primaryText, fontWeight: '600' }}>Decide</Text>
            </TouchableOpacity>
          </View>
        </View>
      </View>
    </Modal>
  );
}
