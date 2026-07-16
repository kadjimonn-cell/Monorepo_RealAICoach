import React, { useCallback, useEffect, useRef, useState } from 'react';
import { View, Text, ScrollView, TouchableOpacity, TextInput, ActivityIndicator, Modal, Alert } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../src/services/api';
import FeatureLayout from '../../src/components/FeatureLayout';
import { useTheme } from '../../src/context/ThemeContext';
import { useAuth } from '../../src/context/AuthContext';
import { useTranslation } from '../../src/hooks/useTranslation';

export default function AIAutomationsScreen() {
  const { colors } = useTheme();
  const { user } = useAuth();
  const { t } = useTranslation();
  t('i18n.route.features.ai-automations.probe');

  const [activeTab, setActiveTab] = useState('workflows');
  const [workflows, setWorkflows] = useState([]);
  const [usage, setUsage] = useState(null);
  const [loading, setLoading] = useState(true);
  const [executing, setExecuting] = useState(null);
  const [executionStates, setExecutionStates] = useState({});
  const executionTimersRef = useRef({});

  const [showCreateModal, setShowCreateModal] = useState(false);
  const [showEditorModal, setShowEditorModal] = useState(false);
  const [editingWorkflow, setEditingWorkflow] = useState(null);
  
  const [newWorkflowName, setNewWorkflowName] = useState('');
  const [newWorkflowDescription, setNewWorkflowDescription] = useState('');

  const [showScheduleModal, setShowScheduleModal] = useState(false);
  const [schedulingWorkflow, setSchedulingWorkflow] = useState(null);
  const [showHistoryModal, setShowHistoryModal] = useState(false);
  const [historyWorkflow, setHistoryWorkflow] = useState(null);
  const [showImportModal, setShowImportModal] = useState(false);

  const clearExecutionTimer = useCallback((workflowId) => {
    const timer = executionTimersRef.current[workflowId];
    if (timer) {
      clearTimeout(timer);
      delete executionTimersRef.current[workflowId];
    }
  }, []);

  const updateExecutionState = useCallback((workflowId, updates) => {
    setExecutionStates((prev) => ({
      ...prev,
      [workflowId]: {
        isRunning: false,
        longRunning: false,
        errorMessage: null,
        lastExecutionId: null,
        lastStatus: null,
        ...prev[workflowId],
        ...updates,
      },
    }));
  }, []);

  const getExecutionErrorMessage = (error) => {
    const detail = error?.response?.data?.detail;
    if (typeof detail === 'string' && detail.trim()) return detail;
    if (typeof detail?.message === 'string' && detail.message.trim()) return detail.message;
    if (typeof error?.message === 'string' && error.message.trim()) return error.message;
    return 'Workflow execution failed. Please retry.';
  };

  useEffect(() => {
    return () => {
      Object.keys(executionTimersRef.current).forEach((workflowId) => {
        clearExecutionTimer(workflowId);
      });
    };
  }, [clearExecutionTimer]);

  const loadWorkflows = useCallback(async () => {
    try {
      setLoading(true);
      const response = await api.get('/workflows');
      setWorkflows(response.data || []);
    } catch (error) {
      console.error('Failed to load workflows:', error);
      Alert.alert('Error', 'Failed to load workflows');
    } finally {
      setLoading(false);
    }
  }, []);

  const loadUsage = useCallback(async () => {
    try {
      const response = await api.get('/workflows/usage/stats');
      setUsage(response.data);
    } catch (error) {
      console.error('Failed to load usage stats:', error);
    }
  }, []);

  useEffect(() => {
    loadWorkflows();
    loadUsage();
  }, [loadWorkflows, loadUsage]);

  const createWorkflow = async () => {
    if (!newWorkflowName.trim()) {
      Alert.alert('Error', 'Please enter a workflow name');
      return;
    }

    try {
      const response = await api.post('/workflows', {
        name: newWorkflowName.trim(),
        description: newWorkflowDescription.trim(),
        nodes: [],
        edges: [],
        enabled: false
      });
      
      setWorkflows([...workflows, response.data]);
      setShowCreateModal(false);
      setNewWorkflowName('');
      setNewWorkflowDescription('');
      
      Alert.alert('Success', 'Workflow created! Open the editor to add nodes.');
    } catch (error) {
      console.error('Failed to create workflow:', error);
      Alert.alert('Error', 'Failed to create workflow');
    }
  };

  const deleteWorkflow = async (workflowId) => {
    Alert.alert(
      'Delete Workflow',
      'Are you sure? This cannot be undone.',
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Delete',
          style: 'destructive',
          onPress: async () => {
            try {
              await api.delete(`/workflows/${workflowId}`);
              setWorkflows(workflows.filter(w => w.workflow_id !== workflowId));
              Alert.alert('Success', 'Workflow deleted');
            } catch (error) {
              console.error('Failed to delete workflow:', error);
              Alert.alert('Error', 'Failed to delete workflow');
            }
          }
        }
      ]
    );
  };

  const toggleWorkflow = async (workflowId, currentEnabled) => {
    try {
      const response = await api.put(`/workflows/${workflowId}`, {
        enabled: !currentEnabled
      });
      
      setWorkflows(workflows.map(w => 
        w.workflow_id === workflowId ? response.data : w
      ));
    } catch (error) {
      console.error('Failed to toggle workflow:', error);
      Alert.alert('Error', 'Failed to toggle workflow');
    }
  };

  const executeWorkflow = async (workflowId, isRetry = false) => {
    clearExecutionTimer(workflowId);

    try {
      setExecuting(workflowId);
      updateExecutionState(workflowId, {
        isRunning: true,
        longRunning: false,
        errorMessage: null,
        lastStatus: 'running',
      });

      executionTimersRef.current[workflowId] = setTimeout(() => {
        setExecutionStates((prev) => {
          const current = prev[workflowId];
          if (!current?.isRunning) return prev;
          return {
            ...prev,
            [workflowId]: {
              ...current,
              longRunning: true,
            },
          };
        });
      }, 30000);

      const response = await api.post(`/workflows/${workflowId}/execute`, {
        input_data: {}
      });

      clearExecutionTimer(workflowId);
      updateExecutionState(workflowId, {
        isRunning: false,
        longRunning: false,
        errorMessage: null,
        lastExecutionId: response.data.execution_id || null,
        lastStatus: response.data.status || 'completed',
      });
      
      Alert.alert(
        isRetry ? 'Retry Started' : 'Execution Started',
        `Execution ID: ${response.data.execution_id}\nStatus: ${response.data.status}`
      );
      
      loadWorkflows();
    } catch (error) {
      console.error('Failed to execute workflow:', error);
      clearExecutionTimer(workflowId);
      const errorMessage = getExecutionErrorMessage(error);
      updateExecutionState(workflowId, {
        isRunning: false,
        longRunning: false,
        errorMessage,
        lastStatus: 'failed',
      });
      Alert.alert(isRetry ? 'Retry Failed' : 'Execution Failed', errorMessage);
    } finally {
      clearExecutionTimer(workflowId);
      setExecuting(null);
    }
  };

  const openEditor = (workflow) => {
    setEditingWorkflow(workflow);
    setShowEditorModal(true);
  };

  const exportWorkflow = async (workflowId) => {
    try {
      const response = await api.get(`/workflows/${workflowId}/export`);
      const jsonStr = JSON.stringify(response.data, null, 2);
      const blob = new Blob([jsonStr], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `workflow_${workflowId}_export.json`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
      Alert.alert('Success', 'Workflow exported successfully');
    } catch (error) {
      console.error('Failed to export workflow:', error);
      Alert.alert('Error', 'Failed to export workflow');
    }
  };

  return (
    <FeatureLayout>
      <View style={{ flex: 1, backgroundColor: colors.bg }} data-testid="workflow-builder-root" testID="workflow-builder-root">
        <View style={{ backgroundColor: colors.card, padding: 16, borderBottomWidth: 1, borderBottomColor: colors.border }} data-testid="workflow-builder-header" testID="workflow-builder-header">
          <Text style={{ fontSize: 24, fontWeight: '700', color: colors.text, marginBottom: 8 }}>
            AI Workflow Builder
          </Text>
          <Text style={{ fontSize: 14, color: colors.textMuted }}>
            Create automated workflows with AI-powered nodes
          </Text>
          
          {usage && (
            <View style={{ flexDirection: 'row', marginTop: 12, gap: 16 }} data-testid="workflow-builder-usage-stats" testID="workflow-builder-usage-stats">
              <View style={{ backgroundColor: colors.bgSecondary, paddingHorizontal: 12, paddingVertical: 8, borderRadius: 8 }}>
                <Text style={{ fontSize: 12, color: colors.textMuted }}>Workflows</Text>
                <Text style={{ fontSize: 16, fontWeight: '600', color: colors.text }}>
                  {usage.workflow_count} / {usage.workflow_limit === -1 ? '∞' : usage.workflow_limit}
                </Text>
              </View>
              <View style={{ backgroundColor: colors.bgSecondary, paddingHorizontal: 12, paddingVertical: 8, borderRadius: 8 }}>
                <Text style={{ fontSize: 12, color: colors.textMuted }}>Executions This Month</Text>
                <Text style={{ fontSize: 16, fontWeight: '600', color: colors.text }}>
                  {usage.executions_this_month} / {usage.execution_limit === -1 ? '∞' : usage.execution_limit}
                </Text>
              </View>
              <View style={{ backgroundColor: colors.bgSecondary, paddingHorizontal: 12, paddingVertical: 8, borderRadius: 8 }}>
                <Text style={{ fontSize: 12, color: colors.textMuted }}>Tier</Text>
                <Text style={{ fontSize: 16, fontWeight: '600', color: colors.primary }}>
                  {usage.tier.toUpperCase()}
                </Text>
              </View>
            </View>
          )}
        </View>

        <View style={{ flexDirection: 'row', backgroundColor: colors.card, borderBottomWidth: 1, borderBottomColor: colors.border }} data-testid="workflow-builder-tabs" testID="workflow-builder-tabs">
          <TouchableOpacity
            onPress={() => setActiveTab('workflows')}
            style={{
              flex: 1,
              paddingVertical: 14,
              borderBottomWidth: 2,
              borderBottomColor: activeTab === 'workflows' ? colors.primary : 'transparent'
            }}
            data-testid="workflow-builder-tab-workflows" testID="workflow-builder-tab-workflows"
          >
            <Text style={{ textAlign: 'center', fontWeight: '600', color: activeTab === 'workflows' ? colors.primary : colors.textMuted }}>
              My Workflows
            </Text>
          </TouchableOpacity>
          <TouchableOpacity
            onPress={() => setActiveTab('templates')}
            style={{
              flex: 1,
              paddingVertical: 14,
              borderBottomWidth: 2,
              borderBottomColor: activeTab === 'templates' ? colors.primary : 'transparent'
            }}
            data-testid="workflow-builder-tab-templates" testID="workflow-builder-tab-templates"
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
              borderBottomColor: activeTab === 'analytics' ? colors.primary : 'transparent'
            }}
            data-testid="workflow-builder-tab-analytics" testID="workflow-builder-tab-analytics"
          >
            <Text style={{ textAlign: 'center', fontWeight: '600', color: activeTab === 'analytics' ? colors.primary : colors.textMuted }}>
              Analytics
            </Text>
          </TouchableOpacity>
        </View>

        <ScrollView style={{ flex: 1 }} contentContainerStyle={{ padding: 16 }}>
          {loading ? (
            <ActivityIndicator size="large" color={colors.primary} style={{ marginTop: 32 }} />
          ) : activeTab === 'workflows' ? (
            <View>
              <View style={{ flexDirection: 'row', gap: 8, marginBottom: 16 }}>
                <TouchableOpacity
                  onPress={() => setShowCreateModal(true)}
                  disabled={usage && !usage.can_create_workflow}
                  style={{
                    flex: 1,
                    backgroundColor: usage && !usage.can_create_workflow ? colors.border : colors.primary,
                    padding: 16,
                    borderRadius: 12,
                    flexDirection: 'row',
                    alignItems: 'center',
                    justifyContent: 'center'
                  }}
                  data-testid="workflow-builder-create-button" testID="workflow-builder-create-button"
                >
                  <Ionicons name="add-circle-outline" size={20} color={colors.primaryText} style={{ marginRight: 8 }} />
                  <Text style={{ color: colors.primaryText, fontSize: 16, fontWeight: '600' }}>
                    Create New Workflow
                  </Text>
                </TouchableOpacity>

                <TouchableOpacity
                  onPress={() => setShowImportModal(true)}
                  style={{
                    backgroundColor: colors.bgSecondary,
                    padding: 16,
                    borderRadius: 12,
                    alignItems: 'center',
                    justifyContent: 'center',
                    minWidth: 60
                  }}
                  data-testid="workflow-builder-import-button" testID="workflow-builder-import-button"
                >
                  <Ionicons name="cloud-upload-outline" size={20} color={colors.text} />
                </TouchableOpacity>
              </View>

              {usage && usage.limit_reached && (
                <View
                  style={{ backgroundColor: colors.warning + '20', padding: 12, borderRadius: 8, marginBottom: 16 }}
                  data-testid="workflow-limit-reached-banner" testID="workflow-limit-reached-banner"
                >
                  <Text style={{ color: colors.warning, fontSize: 14 }} data-testid="workflow-limit-reached-message" testID="workflow-limit-reached-message">
                    Workflow limit reached. Upgrade to create more workflows.
                  </Text>
                </View>
              )}

              {workflows.length === 0 ? (
                <View style={{ alignItems: 'center', marginTop: 32 }} data-testid="workflow-empty-state" testID="workflow-empty-state">
                  <Ionicons name="construct-outline" size={64} color={colors.textMuted} />
                  <Text style={{ fontSize: 18, fontWeight: '600', color: colors.text, marginTop: 16 }} data-testid="workflow-empty-state-title" testID="workflow-empty-state-title">
                    No Workflows Yet
                  </Text>
                  <Text style={{ fontSize: 14, color: colors.textMuted, marginTop: 8, textAlign: 'center' }} data-testid="workflow-empty-state-description" testID="workflow-empty-state-description">
                    Create your first automated workflow to get started
                  </Text>
                </View>
              ) : (
                workflows.map((workflow) => (
                  <View
                    key={workflow.workflow_id}
                    style={{
                      backgroundColor: colors.card,
                      borderRadius: 12,
                      padding: 16,
                      marginBottom: 12,
                      borderWidth: 1,
                      borderColor: colors.border
                    }}
                    data-testid={`workflow-card-${workflow.workflow_id}`} testID={`workflow-card-${workflow.workflow_id}`}
                  >
                    <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 8 }}>
                      <View style={{ flex: 1 }}>
                        <Text style={{ fontSize: 18, fontWeight: '600', color: colors.text }}>
                          {workflow.name}
                        </Text>
                        {workflow.description && (
                          <Text style={{ fontSize: 14, color: colors.textMuted, marginTop: 4 }}>
                            {workflow.description}
                          </Text>
                        )}
                      </View>
                      <View style={{
                        backgroundColor: workflow.enabled ? colors.success + '20' : colors.border,
                        paddingHorizontal: 10,
                        paddingVertical: 4,
                        borderRadius: 12
                      }}>
                        <Text style={{
                          fontSize: 12,
                          fontWeight: '600',
                          color: workflow.enabled ? colors.success : colors.textMuted
                        }}>
                          {workflow.enabled ? 'Active' : 'Disabled'}
                        </Text>
                      </View>
                    </View>

                    <View style={{ flexDirection: 'row', marginTop: 12, gap: 8 }}>
                      <View style={{ backgroundColor: colors.bgSecondary, paddingHorizontal: 10, paddingVertical: 6, borderRadius: 8 }}>
                        <Text style={{ fontSize: 12, color: colors.textMuted }}>
                          {workflow.nodes?.length || 0} nodes
                        </Text>
                      </View>
                      <View style={{ backgroundColor: colors.bgSecondary, paddingHorizontal: 10, paddingVertical: 6, borderRadius: 8 }}>
                        <Text style={{ fontSize: 12, color: colors.textMuted }}>
                          {workflow.execution_count || 0} runs
                        </Text>
                      </View>
                    </View>

                    {executionStates[workflow.workflow_id]?.isRunning && (
                      <View
                        style={{
                          marginTop: 12,
                          backgroundColor: executionStates[workflow.workflow_id]?.longRunning ? colors.warning + '20' : colors.primary + '12',
                          borderWidth: 1,
                          borderColor: executionStates[workflow.workflow_id]?.longRunning ? colors.warning + '50' : colors.primary + '40',
                          borderRadius: 8,
                          padding: 10,
                          flexDirection: 'row',
                          alignItems: 'center',
                          gap: 8,
                        }}
                        data-testid={`workflow-execution-running-banner-${workflow.workflow_id}`} testID={`workflow-execution-running-banner-${workflow.workflow_id}`}
                      >
                        <ActivityIndicator size="small" color={executionStates[workflow.workflow_id]?.longRunning ? colors.warning : colors.primary} />
                        <Text
                          style={{
                            fontSize: 12,
                            color: executionStates[workflow.workflow_id]?.longRunning ? colors.warning : colors.primary,
                            fontWeight: '600',
                            flex: 1,
                          }}
                          data-testid={`workflow-execution-running-message-${workflow.workflow_id}`} testID={`workflow-execution-running-message-${workflow.workflow_id}`}
                        >
                          {executionStates[workflow.workflow_id]?.longRunning
                            ? 'This AI run is taking longer than usual (30s+). We are still processing.'
                            : 'Workflow is running...'}
                        </Text>
                      </View>
                    )}

                    {!executionStates[workflow.workflow_id]?.isRunning && executionStates[workflow.workflow_id]?.errorMessage && (
                      <View
                        style={{
                          marginTop: 12,
                          backgroundColor: colors.error + '14',
                          borderWidth: 1,
                          borderColor: colors.error + '40',
                          borderRadius: 8,
                          padding: 10,
                        }}
                        data-testid={`workflow-execution-error-banner-${workflow.workflow_id}`} testID={`workflow-execution-error-banner-${workflow.workflow_id}`}
                      >
                        <Text
                          style={{ fontSize: 12, fontWeight: '700', color: colors.error, marginBottom: 4 }}
                          data-testid={`workflow-execution-error-title-${workflow.workflow_id}`} testID={`workflow-execution-error-title-${workflow.workflow_id}`}
                        >
                          Execution failed
                        </Text>
                        <Text
                          style={{ fontSize: 12, color: colors.error, marginBottom: 8 }}
                          data-testid={`workflow-execution-error-message-${workflow.workflow_id}`} testID={`workflow-execution-error-message-${workflow.workflow_id}`}
                        >
                          {executionStates[workflow.workflow_id]?.errorMessage}
                        </Text>
                        <TouchableOpacity
                          onPress={() => executeWorkflow(workflow.workflow_id, true)}
                          disabled={executing === workflow.workflow_id || !workflow.enabled}
                          style={{
                            alignSelf: 'flex-start',
                            backgroundColor: workflow.enabled ? colors.error : colors.border,
                            paddingHorizontal: 12,
                            paddingVertical: 8,
                            borderRadius: 8,
                            flexDirection: 'row',
                            alignItems: 'center',
                            gap: 6,
                          }}
                          data-testid={`workflow-execution-retry-button-${workflow.workflow_id}`} testID={`workflow-execution-retry-button-${workflow.workflow_id}`}
                        >
                          <Ionicons name="refresh" size={14} color={colors.primaryText} />
                          <Text style={{ color: colors.primaryText, fontWeight: '600', fontSize: 12 }}>
                            Retry Run
                          </Text>
                        </TouchableOpacity>
                      </View>
                    )}

                    <View style={{ marginTop: 12, gap: 8 }}>
                      <View style={{ flexDirection: 'row', gap: 8 }}>
                        <TouchableOpacity
                          onPress={() => openEditor(workflow)}
                          style={{
                            flex: 1,
                            backgroundColor: colors.primary,
                            padding: 12,
                            borderRadius: 8,
                            alignItems: 'center'
                          }}
                          data-testid={`workflow-edit-button-${workflow.workflow_id}`} testID={`workflow-edit-button-${workflow.workflow_id}`}
                        >
                          <Text style={{ color: colors.primaryText, fontWeight: '600' }}>Edit</Text>
                        </TouchableOpacity>
                        
                        <TouchableOpacity
                          onPress={() => executeWorkflow(workflow.workflow_id)}
                          disabled={executing === workflow.workflow_id || executionStates[workflow.workflow_id]?.isRunning || !workflow.enabled}
                          style={{
                            flex: 1,
                            backgroundColor: workflow.enabled ? colors.success : colors.border,
                            padding: 12,
                            borderRadius: 8,
                            alignItems: 'center'
                          }}
                          data-testid={`workflow-run-button-${workflow.workflow_id}`} testID={`workflow-run-button-${workflow.workflow_id}`}
                        >
                          {executing === workflow.workflow_id || executionStates[workflow.workflow_id]?.isRunning ? (
                            <ActivityIndicator size="small" color={colors.primaryText} />
                          ) : (
                            <Text style={{ color: colors.primaryText, fontWeight: '600' }}>Run</Text>
                          )}
                        </TouchableOpacity>

                        <TouchableOpacity
                          onPress={() => toggleWorkflow(workflow.workflow_id, workflow.enabled)}
                          style={{
                            backgroundColor: colors.bgSecondary,
                            padding: 12,
                            borderRadius: 8,
                            alignItems: 'center',
                            minWidth: 60
                          }}
                          data-testid={`workflow-toggle-button-${workflow.workflow_id}`} testID={`workflow-toggle-button-${workflow.workflow_id}`}
                        >
                          <Ionicons 
                            name={workflow.enabled ? 'pause' : 'play'} 
                            size={18} 
                            color={colors.text} 
                          />
                        </TouchableOpacity>

                        <TouchableOpacity
                          onPress={() => deleteWorkflow(workflow.workflow_id)}
                          style={{
                            backgroundColor: colors.error + '20',
                            padding: 12,
                            borderRadius: 8,
                            alignItems: 'center',
                            minWidth: 60
                          }}
                          data-testid={`workflow-delete-button-${workflow.workflow_id}`} testID={`workflow-delete-button-${workflow.workflow_id}`}
                        >
                          <Ionicons name="trash-outline" size={18} color={colors.error} />
                        </TouchableOpacity>
                      </View>

                      <View style={{ flexDirection: 'row', gap: 8 }}>
                        <TouchableOpacity
                          onPress={() => {
                            setSchedulingWorkflow(workflow);
                            setShowScheduleModal(true);
                          }}
                          style={{
                            flex: 1,
                            backgroundColor: colors.bgSecondary,
                            padding: 10,
                            borderRadius: 8,
                            flexDirection: 'row',
                            alignItems: 'center',
                            justifyContent: 'center',
                            gap: 6
                          }}
                          data-testid={`workflow-schedule-button-${workflow.workflow_id}`} testID={`workflow-schedule-button-${workflow.workflow_id}`}
                        >
                          <Ionicons name="time-outline" size={16} color={colors.text} />
                          <Text style={{ color: colors.text, fontSize: 13, fontWeight: '600' }}>
                            {workflow.schedule ? 'Edit Schedule' : 'Schedule'}
                          </Text>
                        </TouchableOpacity>

                        <TouchableOpacity
                          onPress={() => {
                            setHistoryWorkflow(workflow);
                            setShowHistoryModal(true);
                          }}
                          style={{
                            flex: 1,
                            backgroundColor: colors.bgSecondary,
                            padding: 10,
                            borderRadius: 8,
                            flexDirection: 'row',
                            alignItems: 'center',
                            justifyContent: 'center',
                            gap: 6
                          }}
                          data-testid={`workflow-history-button-${workflow.workflow_id}`} testID={`workflow-history-button-${workflow.workflow_id}`}
                        >
                          <Ionicons name="list-outline" size={16} color={colors.text} />
                          <Text style={{ color: colors.text, fontSize: 13, fontWeight: '600' }}>History</Text>
                        </TouchableOpacity>

                        <TouchableOpacity
                          onPress={() => exportWorkflow(workflow.workflow_id)}
                          style={{
                            backgroundColor: colors.bgSecondary,
                            padding: 10,
                            borderRadius: 8,
                            alignItems: 'center',
                            justifyContent: 'center',
                            minWidth: 50
                          }}
                          data-testid={`workflow-export-button-${workflow.workflow_id}`} testID={`workflow-export-button-${workflow.workflow_id}`}
                        >
                          <Ionicons name="download-outline" size={16} color={colors.text} />
                        </TouchableOpacity>
                      </View>
                    </View>
                  </View>
                ))
              )}
            </View>
          ) : activeTab === 'templates' ? (
            <TemplatesTab colors={colors} onSelectTemplate={(template) => {
              setNewWorkflowName(template.name);
              setNewWorkflowDescription(template.description);
              setShowCreateModal(true);
            }} />
          ) : (
            <AnalyticsTab colors={colors} user={user} />
          )}
        </ScrollView>

        <Modal visible={showCreateModal} animationType="slide" transparent>
          <View style={{ flex: 1, backgroundColor: 'rgba(0,0,0,0.5)', justifyContent: 'center', padding: 16 }} data-testid="workflow-builder-create-modal" testID="workflow-builder-create-modal">
            <View style={{ backgroundColor: colors.card, borderRadius: 16, padding: 24, maxWidth: 500, width: '100%', alignSelf: 'center' }}>
              <Text style={{ fontSize: 20, fontWeight: '700', color: colors.text, marginBottom: 16 }}>
                Create New Workflow
              </Text>

              <Text style={{ fontSize: 14, color: colors.textMuted, marginBottom: 8 }}>Workflow Name</Text>
              <TextInput
                value={newWorkflowName}
                onChangeText={setNewWorkflowName}
                placeholder="My Workflow"
                placeholderTextColor={colors.textMuted}
                style={{
                  backgroundColor: colors.bgSecondary,
                  color: colors.text,
                  padding: 12,
                  borderRadius: 8,
                  fontSize: 16,
                  marginBottom: 16,
                  borderWidth: 1,
                  borderColor: colors.border
                }}
                data-testid="workflow-builder-name-input" testID="workflow-builder-name-input"
              />

              <Text style={{ fontSize: 14, color: colors.textMuted, marginBottom: 8 }}>Description (Optional)</Text>
              <TextInput
                value={newWorkflowDescription}
                onChangeText={setNewWorkflowDescription}
                placeholder="Describe what this workflow does..."
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
                  minHeight: 80
                }}
                data-testid="workflow-builder-description-input" testID="workflow-builder-description-input"
              />

              <View style={{ flexDirection: 'row', gap: 12 }}>
                <TouchableOpacity
                  onPress={() => {
                    setShowCreateModal(false);
                    setNewWorkflowName('');
                    setNewWorkflowDescription('');
                  }}
                  style={{
                    flex: 1,
                    backgroundColor: colors.bgSecondary,
                    padding: 14,
                    borderRadius: 8,
                    alignItems: 'center'
                  }}
                  data-testid="workflow-builder-cancel-button" testID="workflow-builder-cancel-button"
                >
                  <Text style={{ color: colors.text, fontWeight: '600' }}>Cancel</Text>
                </TouchableOpacity>

                <TouchableOpacity
                  onPress={createWorkflow}
                  style={{
                    flex: 1,
                    backgroundColor: colors.primary,
                    padding: 14,
                    borderRadius: 8,
                    alignItems: 'center'
                  }}
                  data-testid="workflow-builder-submit-button" testID="workflow-builder-submit-button"
                >
                  <Text style={{ color: colors.primaryText, fontWeight: '600' }}>Create</Text>
                </TouchableOpacity>
              </View>
            </View>
          </View>
        </Modal>

        {showEditorModal && editingWorkflow && (
          <WorkflowEditorModal
            workflow={editingWorkflow}
            colors={colors}
            visible={showEditorModal}
            onClose={() => {
              setShowEditorModal(false);
              setEditingWorkflow(null);
              loadWorkflows();
            }}
          />
        )}

        {showScheduleModal && schedulingWorkflow && (
          <ScheduleModal
            workflow={schedulingWorkflow}
            colors={colors}
            visible={showScheduleModal}
            onClose={() => {
              setShowScheduleModal(false);
              setSchedulingWorkflow(null);
              loadWorkflows();
            }}
          />
        )}

        {showHistoryModal && historyWorkflow && (
          <ExecutionHistoryModal
            workflow={historyWorkflow}
            colors={colors}
            visible={showHistoryModal}
            onClose={() => {
              setShowHistoryModal(false);
              setHistoryWorkflow(null);
            }}
          />
        )}

        {showImportModal && (
          <ImportModal
            colors={colors}
            visible={showImportModal}
            onClose={() => {
              setShowImportModal(false);
              loadWorkflows();
            }}
          />
        )}
      </View>
    </FeatureLayout>
  );
}

function TemplatesTab({ colors, onSelectTemplate }) {
  const [templates, setTemplates] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedCategory, setSelectedCategory] = useState('all');

  const loadTemplates = useCallback(async () => {
    try {
      setLoading(true);
      const categoryParam = selectedCategory !== 'all' ? `?category=${selectedCategory}` : '';
      const response = await api.get(`/workflows/templates${categoryParam}`);
      setTemplates(response.data.templates || []);
    } catch (error) {
      console.error('Failed to load templates:', error);
    } finally {
      setLoading(false);
    }
  }, [selectedCategory]);

  useEffect(() => {
    loadTemplates();
  }, [loadTemplates]);

  const categories = [
    { id: 'all', label: 'All Templates' },
    { id: 'email', label: 'Email' },
    { id: 'content', label: 'Content' },
    { id: 'data', label: 'Data' },
    { id: 'ai', label: 'AI' },
    { id: 'sales', label: 'Sales' },
    { id: 'monitoring', label: 'Monitoring' },
    { id: 'ecommerce', label: 'E-Commerce' }
  ];

  const handleUseTemplate = async (template) => {
    try {
      const response = await api.post('/workflows/from-template', null, {
        params: { template_id: template.template_id }
      });
      
      Alert.alert('Success', `Workflow created: ${response.data.name}`);
      onSelectTemplate({ 
        name: response.data.name, 
        description: response.data.description 
      });
    } catch (error) {
      console.error('Failed to create from template:', error);
      Alert.alert('Error', error.response?.data?.detail || 'Failed to create workflow from template');
    }
  };

  return (
    <View data-testid="workflow-templates-tab-root" testID="workflow-templates-tab-root">
      <Text style={{ fontSize: 18, fontWeight: '600', color: colors.text, marginBottom: 12 }}>
        Workflow Templates
      </Text>
      
      <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ marginBottom: 16 }}>
        {categories.map((cat) => (
          <TouchableOpacity
            key={cat.id}
            onPress={() => setSelectedCategory(cat.id)}
            style={{
              backgroundColor: selectedCategory === cat.id ? colors.primary : colors.bgSecondary,
              paddingHorizontal: 16,
              paddingVertical: 8,
              borderRadius: 20,
              marginRight: 8
            }}
            data-testid={`workflow-template-category-${cat.id}`} testID={`workflow-template-category-${cat.id}`}
          >
            <Text style={{
              color: selectedCategory === cat.id ? colors.primaryText : colors.text,
              fontSize: 14,
              fontWeight: '600'
            }}>
              {cat.label}
            </Text>
          </TouchableOpacity>
        ))}
      </ScrollView>

      {loading ? (
        <ActivityIndicator size="large" color={colors.primary} style={{ marginTop: 32 }} data-testid="workflow-templates-loading" testID="workflow-templates-loading" />
      ) : templates.length === 0 ? (
        <View style={{ alignItems: 'center', marginTop: 32 }} data-testid="workflow-templates-empty-state" testID="workflow-templates-empty-state">
          <Text style={{ color: colors.textMuted, fontSize: 16 }} data-testid="workflow-templates-empty-message" testID="workflow-templates-empty-message">
            No templates available
          </Text>
        </View>
      ) : (
        templates.map((template, index) => (
          <View
            key={index}
            style={{
              backgroundColor: colors.card,
              borderRadius: 12,
              padding: 16,
              marginBottom: 12,
              borderWidth: 1,
              borderColor: colors.border
            }}
            data-testid={`workflow-template-card-${template.template_id}`} testID={`workflow-template-card-${template.template_id}`}
          >
            <View style={{ flexDirection: 'row', alignItems: 'flex-start' }}>
              <View style={{
                width: 48,
                height: 48,
                borderRadius: 24,
                backgroundColor: colors.primary + '20',
                alignItems: 'center',
                justifyContent: 'center',
                marginRight: 16
              }}>
                <Ionicons name={template.icon} size={24} color={colors.primary} />
              </View>
              <View style={{ flex: 1 }}>
                <Text style={{ fontSize: 16, fontWeight: '600', color: colors.text }}>
                  {template.name}
                </Text>
                <Text style={{ fontSize: 14, color: colors.textMuted, marginTop: 4 }}>
                  {template.description}
                </Text>
                <View style={{ flexDirection: 'row', marginTop: 8, gap: 8 }}>
                  <View style={{ backgroundColor: colors.bgSecondary, paddingHorizontal: 8, paddingVertical: 4, borderRadius: 6 }}>
                    <Text style={{ fontSize: 12, color: colors.textMuted }}>
                      {template.nodes?.length || 0} nodes
                    </Text>
                  </View>
                  {template.tier_requirement && template.tier_requirement !== 'free' && (
                    <View style={{ backgroundColor: colors.primary + '20', paddingHorizontal: 8, paddingVertical: 4, borderRadius: 6 }}>
                      <Text style={{ fontSize: 12, color: colors.primary, fontWeight: '600' }}>
                        {template.tier_requirement.toUpperCase()}
                      </Text>
                    </View>
                  )}
                </View>
              </View>
            </View>
            
            <TouchableOpacity
              onPress={() => handleUseTemplate(template)}
              style={{
                backgroundColor: colors.primary,
                padding: 12,
                borderRadius: 8,
                alignItems: 'center',
                marginTop: 12
              }}
              data-testid={`workflow-template-use-button-${template.template_id}`} testID={`workflow-template-use-button-${template.template_id}`}
            >
              <Text style={{ color: colors.primaryText, fontWeight: '600', fontSize: 14 }}>
                Use This Template
              </Text>
            </TouchableOpacity>
          </View>
        ))
      )}
    </View>
  );
}

function WorkflowEditorModal({ workflow, colors, visible, onClose }) {
  const [workflowName, setWorkflowName] = useState(workflow.name);
  const [workflowDescription, setWorkflowDescription] = useState(workflow.description || '');
  const [nodes, setNodes] = useState(workflow.nodes || []);
  const [saving, setSaving] = useState(false);
  const [showNodePicker, setShowNodePicker] = useState(false);

  const saveWorkflow = async () => {
    try {
      setSaving(true);
      await api.put(`/workflows/${workflow.workflow_id}`, {
        name: workflowName,
        description: workflowDescription,
        nodes: nodes
      });
      Alert.alert('Success', 'Workflow saved');
      onClose();
    } catch (error) {
      console.error('Failed to save workflow:', error);
      Alert.alert('Error', 'Failed to save workflow');
    } finally {
      setSaving(false);
    }
  };

  const addNode = useCallback((nodeType) => {
    const newNode = {
      node_id: `node_${Math.random().toString(36).substr(2, 9)}_${new Date().getTime()}`,
      type: 'action',
      action: nodeType,
      label: nodeType.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase()),
      config: {}
    };
    setNodes(prevNodes => [...prevNodes, newNode]);
    setShowNodePicker(false);
  }, []);

  const deleteNode = (nodeId) => {
    setNodes(nodes.filter(n => n.node_id !== nodeId));
  };

  const nodeTypes = [
    { id: 'ai_completion', label: 'AI Completion', icon: 'bulb-outline' },
    { id: 'ai_chat', label: 'AI Chat', icon: 'chatbubbles-outline' },
    { id: 'http_request', label: 'HTTP Request', icon: 'cloud-outline' },
    { id: 'transform_json', label: 'Transform JSON', icon: 'code-slash-outline' },
    { id: 'send_email', label: 'Send Email', icon: 'mail-outline' },
    { id: 'delay', label: 'Delay', icon: 'time-outline' }
  ];

  return (
    <Modal visible={visible} animationType="slide">
      <View style={{ flex: 1, backgroundColor: colors.bg }} data-testid={`workflow-editor-modal-${workflow.workflow_id}`} testID={`workflow-editor-modal-${workflow.workflow_id}`}>
        <View style={{ backgroundColor: colors.card, padding: 16, borderBottomWidth: 1, borderBottomColor: colors.border }} data-testid="workflow-editor-header" testID="workflow-editor-header">
          <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
            <TouchableOpacity onPress={onClose} style={{ padding: 8 }} data-testid="workflow-editor-close-button" testID="workflow-editor-close-button">
              <Ionicons name="arrow-back" size={24} color={colors.text} />
            </TouchableOpacity>
            <Text style={{ fontSize: 18, fontWeight: '700', color: colors.text }}>Workflow Editor</Text>
            <TouchableOpacity
              onPress={saveWorkflow}
              disabled={saving}
              style={{
                backgroundColor: colors.primary,
                paddingHorizontal: 16,
                paddingVertical: 8,
                borderRadius: 8
              }}
              data-testid="workflow-editor-save-button" testID="workflow-editor-save-button"
            >
              {saving ? (
                <ActivityIndicator size="small" color={colors.primaryText} />
              ) : (
                <Text style={{ color: colors.primaryText, fontWeight: '600' }}>Save</Text>
              )}
            </TouchableOpacity>
          </View>
        </View>

        <ScrollView style={{ flex: 1 }} contentContainerStyle={{ padding: 16 }}>
          <View style={{ backgroundColor: colors.card, borderRadius: 12, padding: 16, marginBottom: 16 }}>
            <Text style={{ fontSize: 14, color: colors.textMuted, marginBottom: 8 }}>Workflow Name</Text>
            <TextInput
              value={workflowName}
              onChangeText={setWorkflowName}
              style={{
                backgroundColor: colors.bgSecondary,
                color: colors.text,
                padding: 12,
                borderRadius: 8,
                fontSize: 16,
                marginBottom: 16,
                borderWidth: 1,
                borderColor: colors.border
              }}
              data-testid="workflow-editor-name-input" testID="workflow-editor-name-input"
            />

            <Text style={{ fontSize: 14, color: colors.textMuted, marginBottom: 8 }}>Description</Text>
            <TextInput
              value={workflowDescription}
              onChangeText={setWorkflowDescription}
              multiline
              numberOfLines={2}
              style={{
                backgroundColor: colors.bgSecondary,
                color: colors.text,
                padding: 12,
                borderRadius: 8,
                fontSize: 14,
                borderWidth: 1,
                borderColor: colors.border,
                minHeight: 60
              }}
              data-testid="workflow-editor-description-input" testID="workflow-editor-description-input"
            />
          </View>

          <View style={{ marginBottom: 16 }}>
            <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
              <Text style={{ fontSize: 18, fontWeight: '600', color: colors.text }}>Workflow Nodes</Text>
              <TouchableOpacity
                onPress={() => setShowNodePicker(true)}
                style={{
                  backgroundColor: colors.primary,
                  paddingHorizontal: 12,
                  paddingVertical: 8,
                  borderRadius: 8,
                  flexDirection: 'row',
                  alignItems: 'center'
                }}
                data-testid="workflow-editor-add-node-button" testID="workflow-editor-add-node-button"
              >
                <Ionicons name="add" size={18} color={colors.primaryText} />
                <Text style={{ color: colors.primaryText, marginLeft: 4, fontWeight: '600' }}>Add Node</Text>
              </TouchableOpacity>
            </View>

            {nodes.length === 0 ? (
              <View style={{ backgroundColor: colors.card, borderRadius: 12, padding: 24, alignItems: 'center' }}>
                <Ionicons name="git-network-outline" size={48} color={colors.textMuted} />
                <Text style={{ fontSize: 16, color: colors.textMuted, marginTop: 12 }}>
                  No nodes yet. Add your first node to start building.
                </Text>
              </View>
            ) : (
              nodes.map((node, index) => (
                <View
                  key={node.node_id}
                  style={{
                    backgroundColor: colors.card,
                    borderRadius: 12,
                    padding: 16,
                    marginBottom: 8,
                    borderWidth: 1,
                    borderColor: colors.border
                  }}
                  data-testid={`workflow-editor-node-card-${node.node_id}`} testID={`workflow-editor-node-card-${node.node_id}`}
                >
                  <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
                    <View style={{ flexDirection: 'row', alignItems: 'center', flex: 1 }}>
                      <View style={{
                        width: 32,
                        height: 32,
                        borderRadius: 16,
                        backgroundColor: colors.primary + '20',
                        alignItems: 'center',
                        justifyContent: 'center',
                        marginRight: 12
                      }}>
                        <Text style={{ fontSize: 14, fontWeight: '600', color: colors.primary }}>
                          {index + 1}
                        </Text>
                      </View>
                      <View style={{ flex: 1 }}>
                        <Text style={{ fontSize: 16, fontWeight: '600', color: colors.text }}>
                          {node.label || node.action}
                        </Text>
                        <Text style={{ fontSize: 12, color: colors.textMuted, marginTop: 2 }}>
                          {node.action}
                        </Text>
                      </View>
                    </View>
                    <TouchableOpacity
                      onPress={() => deleteNode(node.node_id)}
                      style={{ padding: 8 }}
                      data-testid={`workflow-editor-delete-node-button-${node.node_id}`} testID={`workflow-editor-delete-node-button-${node.node_id}`}
                    >
                      <Ionicons name="trash-outline" size={20} color={colors.error} />
                    </TouchableOpacity>
                  </View>
                </View>
              ))
            )}
          </View>
        </ScrollView>

        <Modal visible={showNodePicker} animationType="slide" transparent>
          <View style={{ flex: 1, backgroundColor: 'rgba(0,0,0,0.5)', justifyContent: 'flex-end' }} data-testid="workflow-node-picker-overlay" testID="workflow-node-picker-overlay">
            <View style={{ backgroundColor: colors.card, borderTopLeftRadius: 16, borderTopRightRadius: 16, padding: 16 }} data-testid="workflow-node-picker-sheet" testID="workflow-node-picker-sheet">
              <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
                <Text style={{ fontSize: 18, fontWeight: '700', color: colors.text }}>Add Node</Text>
                <TouchableOpacity onPress={() => setShowNodePicker(false)} data-testid="workflow-node-picker-close-button" testID="workflow-node-picker-close-button">
                  <Ionicons name="close" size={24} color={colors.text} />
                </TouchableOpacity>
              </View>

              <ScrollView style={{ maxHeight: 400 }}>
                {nodeTypes.map((nodeType) => (
                  <TouchableOpacity
                    key={nodeType.id}
                    onPress={() => addNode(nodeType.id)}
                    style={{
                      flexDirection: 'row',
                      alignItems: 'center',
                      padding: 16,
                      backgroundColor: colors.bgSecondary,
                      borderRadius: 8,
                      marginBottom: 8
                    }}
                    data-testid={`workflow-node-picker-option-${nodeType.id}`} testID={`workflow-node-picker-option-${nodeType.id}`}
                  >
                    <View style={{
                      width: 40,
                      height: 40,
                      borderRadius: 20,
                      backgroundColor: colors.primary + '20',
                      alignItems: 'center',
                      justifyContent: 'center',
                      marginRight: 12
                    }}>
                      <Ionicons name={nodeType.icon} size={20} color={colors.primary} />
                    </View>
                    <Text style={{ fontSize: 16, fontWeight: '600', color: colors.text }}>
                      {nodeType.label}
                    </Text>
                  </TouchableOpacity>
                ))}
              </ScrollView>
            </View>
          </View>
        </Modal>
      </View>
    </Modal>
  );
}


// Phase 5.4: Analytics Dashboard Tab
function AnalyticsTab({ colors, user }) {
  const [analytics, setAnalytics] = useState(null);
  const [loading, setLoading] = useState(true);
  const [days, setDays] = useState(30);

  const loadAnalytics = useCallback(async () => {
    try {
      setLoading(true);
      const response = await api.get(`/workflows/analytics/overview?days=${days}`);
      setAnalytics(response.data);
    } catch (error) {
      console.error('Failed to load analytics:', error);
      Alert.alert('Error', 'Failed to load analytics');
    } finally {
      setLoading(false);
    }
  }, [days]);

  useEffect(() => {
    loadAnalytics();
  }, [loadAnalytics]);

  if (loading) {
    return <ActivityIndicator size="large" color={colors.primary} style={{ marginTop: 32 }} data-testid="workflow-analytics-loading" testID="workflow-analytics-loading" />;
  }

  if (!analytics) {
    return (
      <View style={{ alignItems: 'center', marginTop: 32 }}>
        <Text style={{ color: colors.textMuted, fontSize: 16 }} data-testid="workflow-analytics-empty-message" testID="workflow-analytics-empty-message">No analytics data available</Text>
      </View>
    );
  }

  const { summary, most_used_workflows, node_type_usage, recent_failures } = analytics;

  return (
    <View>
      <View style={{ flexDirection: 'row', marginBottom: 16, gap: 8 }}>
        {[7, 30, 90].map((d) => (
          <TouchableOpacity
            key={d}
            onPress={() => setDays(d)}
            style={{
              flex: 1,
              backgroundColor: days === d ? colors.primary : colors.bgSecondary,
              padding: 12,
              borderRadius: 8,
              alignItems: 'center'
            }}
            data-testid={`workflow-analytics-range-${d}-days`} testID={`workflow-analytics-range-${d}-days`}
          >
            <Text style={{ color: days === d ? colors.primaryText : colors.text, fontWeight: '600' }}>
              {d} days
            </Text>
          </TouchableOpacity>
        ))}
      </View>

      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 12, marginBottom: 16 }}>
        <View style={{ flex: 1, minWidth: 150, backgroundColor: colors.card, padding: 16, borderRadius: 12 }}>
          <Text style={{ fontSize: 12, color: colors.textMuted, marginBottom: 4 }}>Total Workflows</Text>
          <Text style={{ fontSize: 24, fontWeight: '700', color: colors.text }}>{summary.total_workflows}</Text>
        </View>
        <View style={{ flex: 1, minWidth: 150, backgroundColor: colors.card, padding: 16, borderRadius: 12 }}>
          <Text style={{ fontSize: 12, color: colors.textMuted, marginBottom: 4 }}>Total Executions</Text>
          <Text style={{ fontSize: 24, fontWeight: '700', color: colors.text }}>{summary.total_executions}</Text>
        </View>
        <View style={{ flex: 1, minWidth: 150, backgroundColor: colors.card, padding: 16, borderRadius: 12 }}>
          <Text style={{ fontSize: 12, color: colors.textMuted, marginBottom: 4 }}>Success Rate</Text>
          <Text style={{ fontSize: 24, fontWeight: '700', color: colors.success }}>{summary.success_rate}%</Text>
        </View>
        <View style={{ flex: 1, minWidth: 150, backgroundColor: colors.card, padding: 16, borderRadius: 12 }}>
          <Text style={{ fontSize: 12, color: colors.textMuted, marginBottom: 4 }}>Avg Duration</Text>
          <Text style={{ fontSize: 24, fontWeight: '700', color: colors.text }}>{summary.average_duration_seconds}s</Text>
        </View>
      </View>

      <View style={{ backgroundColor: colors.card, borderRadius: 12, padding: 16, marginBottom: 16 }}>
        <Text style={{ fontSize: 18, fontWeight: '600', color: colors.text, marginBottom: 12 }}>Most Used Workflows</Text>
        {most_used_workflows.length === 0 ? (
          <Text style={{ color: colors.textMuted }}>No workflows executed yet</Text>
        ) : (
          most_used_workflows.map((wf, index) => (
            <View key={wf.workflow_id} style={{ flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 8, borderBottomWidth: index < most_used_workflows.length - 1 ? 1 : 0, borderBottomColor: colors.border }}>
              <Text style={{ color: colors.text, flex: 1 }}>{wf.name}</Text>
              <Text style={{ color: colors.textMuted, fontWeight: '600' }}>{wf.execution_count} runs</Text>
            </View>
          ))
        )}
      </View>

      <View style={{ backgroundColor: colors.card, borderRadius: 12, padding: 16, marginBottom: 16 }}>
        <Text style={{ fontSize: 18, fontWeight: '600', color: colors.text, marginBottom: 12 }}>Node Usage</Text>
        {Object.keys(node_type_usage).length === 0 ? (
          <Text style={{ color: colors.textMuted }}>No node usage data</Text>
        ) : (
          Object.entries(node_type_usage).sort((a, b) => b[1] - a[1]).map(([action, count], index) => (
            <View key={action} style={{ flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 8, borderBottomWidth: index < Object.keys(node_type_usage).length - 1 ? 1 : 0, borderBottomColor: colors.border }}>
              <Text style={{ color: colors.text }}>{action.replace(/_/g, ' ')}</Text>
              <Text style={{ color: colors.textMuted, fontWeight: '600' }}>{count}</Text>
            </View>
          ))
        )}
      </View>

      {recent_failures.length > 0 && (
        <View style={{ backgroundColor: colors.card, borderRadius: 12, padding: 16 }}>
          <Text style={{ fontSize: 18, fontWeight: '600', color: colors.text, marginBottom: 12 }}>Recent Failures</Text>
          {recent_failures.map((failure, index) => (
            <View key={failure.execution_id} style={{ paddingVertical: 12, borderBottomWidth: index < recent_failures.length - 1 ? 1 : 0, borderBottomColor: colors.border }}>
              <Text style={{ color: colors.text, fontWeight: '600', marginBottom: 4 }}>{failure.workflow_name}</Text>
              <Text style={{ color: colors.error, fontSize: 13, marginBottom: 4 }}>{failure.error}</Text>
              <Text style={{ color: colors.textMuted, fontSize: 12 }}>{new Date(failure.started_at).toLocaleString()}</Text>
            </View>
          ))}
        </View>
      )}
    </View>
  );
}

// Phase 5.2: Cron Scheduling Modal
function ScheduleModal({ workflow, colors, visible, onClose }) {
  const [cronExpression, setCronExpression] = useState(workflow.schedule?.cron_expression || '');
  const [timezone, setTimezone] = useState(workflow.schedule?.timezone || 'UTC');
  const [saving, setSaving] = useState(false);

  const presets = [
    { label: 'Every Hour', value: '0 * * * *' },
    { label: 'Every Day at 9 AM', value: '0 9 * * *' },
    { label: 'Every Monday', value: '0 9 * * 1' },
    { label: 'Every Month', value: '0 9 1 * *' },
  ];

  const saveSchedule = async () => {
    if (!cronExpression.trim()) {
      Alert.alert('Error', 'Please enter a cron expression');
      return;
    }

    try {
      setSaving(true);
      await api.put(`/workflows/${workflow.workflow_id}/schedule`, null, {
        params: {
          cron_expression: cronExpression,
          timezone: timezone,
          enabled: true
        }
      });
      Alert.alert('Success', 'Schedule saved successfully');
      onClose();
    } catch (error) {
      console.error('Failed to save schedule:', error);
      Alert.alert('Error', error.response?.data?.detail || 'Failed to save schedule');
    } finally {
      setSaving(false);
    }
  };

  const removeSchedule = async () => {
    Alert.alert(
      'Remove Schedule',
      'Are you sure you want to remove this schedule?',
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Remove',
          style: 'destructive',
          onPress: async () => {
            try {
              await api.delete(`/workflows/${workflow.workflow_id}/schedule`);
              Alert.alert('Success', 'Schedule removed');
              onClose();
            } catch (error) {
              console.error('Failed to remove schedule:', error);
              Alert.alert('Error', 'Failed to remove schedule');
            }
          }
        }
      ]
    );
  };

  return (
    <Modal visible={visible} animationType="slide" transparent>
      <View style={{ flex: 1, backgroundColor: 'rgba(0,0,0,0.5)', justifyContent: 'center', padding: 16 }} data-testid={`workflow-schedule-modal-${workflow.workflow_id}`} testID={`workflow-schedule-modal-${workflow.workflow_id}`}>
        <ScrollView style={{ maxHeight: '80%' }}>
          <View style={{ backgroundColor: colors.card, borderRadius: 16, padding: 24, maxWidth: 600, width: '100%', alignSelf: 'center' }} data-testid="workflow-schedule-modal-content" testID="workflow-schedule-modal-content">
            <Text style={{ fontSize: 20, fontWeight: '700', color: colors.text, marginBottom: 16 }}>
              Schedule: {workflow.name}
            </Text>

            <Text style={{ fontSize: 14, color: colors.textMuted, marginBottom: 8 }}>Quick Presets</Text>
            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginBottom: 16 }}>
              {presets.map((preset) => (
                <TouchableOpacity
                  key={preset.value}
                  onPress={() => setCronExpression(preset.value)}
                  style={{
                    backgroundColor: colors.bgSecondary,
                    paddingHorizontal: 12,
                    paddingVertical: 8,
                    borderRadius: 8
                  }}
                  data-testid={`workflow-schedule-preset-${preset.value.replace(/[^a-zA-Z0-9]+/g, '-').replace(/^-|-$/g, '').toLowerCase()}`} testID={`workflow-schedule-preset-${preset.value.replace(/[^a-zA-Z0-9]+/g, '-').replace(/^-|-$/g, '').toLowerCase()}`}
                >
                  <Text style={{ color: colors.text, fontSize: 13 }}>{preset.label}</Text>
                </TouchableOpacity>
              ))}
            </View>

            <Text style={{ fontSize: 14, color: colors.textMuted, marginBottom: 8 }}>Cron Expression</Text>
            <TextInput
              value={cronExpression}
              onChangeText={setCronExpression}
              placeholder="0 * * * * (minute hour day month weekday)"
              placeholderTextColor={colors.textMuted}
              style={{
                backgroundColor: colors.bgSecondary,
                color: colors.text,
                padding: 12,
                borderRadius: 8,
                fontSize: 14,
                marginBottom: 8,
                borderWidth: 1,
                borderColor: colors.border,
                fontFamily: 'monospace'
              }}
              data-testid="workflow-schedule-cron-input" testID="workflow-schedule-cron-input"
            />
            <Text style={{ fontSize: 12, color: colors.textMuted, marginBottom: 16 }}>
              Format: minute hour day month weekday
            </Text>

            <Text style={{ fontSize: 14, color: colors.textMuted, marginBottom: 8 }}>Timezone</Text>
            <TextInput
              value={timezone}
              onChangeText={setTimezone}
              placeholder="UTC"
              placeholderTextColor={colors.textMuted}
              style={{
                backgroundColor: colors.bgSecondary,
                color: colors.text,
                padding: 12,
                borderRadius: 8,
                fontSize: 14,
                marginBottom: 24,
                borderWidth: 1,
                borderColor: colors.border
              }}
              data-testid="workflow-schedule-timezone-input" testID="workflow-schedule-timezone-input"
            />

            <View style={{ flexDirection: 'row', gap: 12 }}>
              <TouchableOpacity
                onPress={onClose}
                style={{
                  flex: 1,
                  backgroundColor: colors.bgSecondary,
                  padding: 14,
                  borderRadius: 8,
                  alignItems: 'center'
                }}
                data-testid="workflow-schedule-cancel-button" testID="workflow-schedule-cancel-button"
              >
                <Text style={{ color: colors.text, fontWeight: '600' }}>Cancel</Text>
              </TouchableOpacity>

              {workflow.schedule && (
                <TouchableOpacity
                  onPress={removeSchedule}
                  style={{
                    flex: 1,
                    backgroundColor: colors.error + '20',
                    padding: 14,
                    borderRadius: 8,
                    alignItems: 'center'
                  }}
                  data-testid="workflow-schedule-remove-button" testID="workflow-schedule-remove-button"
                >
                  <Text style={{ color: colors.error, fontWeight: '600' }}>Remove</Text>
                </TouchableOpacity>
              )}

              <TouchableOpacity
                onPress={saveSchedule}
                disabled={saving}
                style={{
                  flex: 1,
                  backgroundColor: colors.primary,
                  padding: 14,
                  borderRadius: 8,
                  alignItems: 'center'
                }}
                data-testid="workflow-schedule-save-button" testID="workflow-schedule-save-button"
              >
                {saving ? (
                  <ActivityIndicator size="small" color={colors.primaryText} />
                ) : (
                  <Text style={{ color: colors.primaryText, fontWeight: '600' }}>Save</Text>
                )}
              </TouchableOpacity>
            </View>
          </View>
        </ScrollView>
      </View>
    </Modal>
  );
}

// Phase 5.3: Execution History Modal
function ExecutionHistoryModal({ workflow, colors, visible, onClose }) {
  const [executions, setExecutions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [expandedId, setExpandedId] = useState(null);

  const loadExecutions = useCallback(async () => {
    try {
      setLoading(true);
      const response = await api.get(`/workflows/${workflow.workflow_id}/executions?limit=50`);
      setExecutions(response.data || []);
    } catch (error) {
      console.error('Failed to load executions:', error);
      Alert.alert('Error', 'Failed to load execution history');
    } finally {
      setLoading(false);
    }
  }, [workflow.workflow_id]);

  useEffect(() => {
    if (visible) {
      loadExecutions();
    }
  }, [visible, loadExecutions]);

  const clearHistory = async () => {
    Alert.alert(
      'Clear History',
      'Delete all execution history? (keeps 5 most recent)',
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Clear',
          style: 'destructive',
          onPress: async () => {
            try {
              await api.post(`/workflows/${workflow.workflow_id}/executions/clear`, null, {
                params: { keep_recent: 5 }
              });
              Alert.alert('Success', 'History cleared');
              loadExecutions();
            } catch (error) {
              console.error('Failed to clear history:', error);
              Alert.alert('Error', 'Failed to clear history');
            }
          }
        }
      ]
    );
  };

  return (
    <Modal visible={visible} animationType="slide">
      <View style={{ flex: 1, backgroundColor: colors.bg }} data-testid={`workflow-history-modal-${workflow.workflow_id}`} testID={`workflow-history-modal-${workflow.workflow_id}`}>
        <View style={{ backgroundColor: colors.card, padding: 16, borderBottomWidth: 1, borderBottomColor: colors.border }} data-testid="workflow-history-header" testID="workflow-history-header">
          <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
            <TouchableOpacity onPress={onClose} style={{ padding: 8 }} data-testid="workflow-history-close-button" testID="workflow-history-close-button">
              <Ionicons name="arrow-back" size={24} color={colors.text} />
            </TouchableOpacity>
            <Text style={{ fontSize: 18, fontWeight: '700', color: colors.text }}>Execution History</Text>
            <TouchableOpacity onPress={clearHistory} style={{ padding: 8 }} data-testid="workflow-history-clear-button" testID="workflow-history-clear-button">
              <Ionicons name="trash-outline" size={20} color={colors.error} />
            </TouchableOpacity>
          </View>
          <Text style={{ fontSize: 14, color: colors.textMuted, marginTop: 4 }}>{workflow.name}</Text>
        </View>

        <ScrollView style={{ flex: 1 }} contentContainerStyle={{ padding: 16 }}>
          {loading ? (
            <ActivityIndicator size="large" color={colors.primary} style={{ marginTop: 32 }} />
          ) : executions.length === 0 ? (
            <View style={{ alignItems: 'center', marginTop: 32 }}>
              <Ionicons name="time-outline" size={64} color={colors.textMuted} />
              <Text style={{ fontSize: 16, color: colors.textMuted, marginTop: 16 }}>No executions yet</Text>
            </View>
          ) : (
            executions.map((execution) => (
              <TouchableOpacity
                key={execution.execution_id}
                onPress={() => setExpandedId(expandedId === execution.execution_id ? null : execution.execution_id)}
                style={{
                  backgroundColor: colors.card,
                  borderRadius: 12,
                  padding: 16,
                  marginBottom: 12,
                  borderWidth: 1,
                  borderColor: colors.border
                }}
                data-testid={`workflow-history-item-${execution.execution_id}`} testID={`workflow-history-item-${execution.execution_id}`}
              >
                <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                  <View style={{
                    backgroundColor: execution.status === 'completed' ? colors.success + '20' : execution.status === 'failed' ? colors.error + '20' : colors.border,
                    paddingHorizontal: 10,
                    paddingVertical: 4,
                    borderRadius: 12
                  }}>
                    <Text style={{
                      fontSize: 12,
                      fontWeight: '600',
                      color: execution.status === 'completed' ? colors.success : execution.status === 'failed' ? colors.error : colors.textMuted
                    }}>
                      {execution.status.toUpperCase()}
                    </Text>
                  </View>
                  <Text style={{ fontSize: 13, color: colors.textMuted }}>
                    {execution.duration_ms ? `${(execution.duration_ms / 1000).toFixed(2)}s` : 'N/A'}
                  </Text>
                </View>

                <Text style={{ fontSize: 12, color: colors.textMuted, marginBottom: 4 }}>
                  {new Date(execution.started_at).toLocaleString()}
                </Text>

                {expandedId === execution.execution_id && (
                  <View style={{ marginTop: 12, paddingTop: 12, borderTopWidth: 1, borderTopColor: colors.border }}>
                    <Text style={{ fontSize: 14, fontWeight: '600', color: colors.text, marginBottom: 8 }}>
                      Execution Steps ({execution.step_results?.length || 0})
                    </Text>
                    {execution.step_results?.map((step, index) => (
                      <View key={index} style={{ backgroundColor: colors.bgSecondary, padding: 12, borderRadius: 8, marginBottom: 8 }}>
                        <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginBottom: 4 }}>
                          <Text style={{ fontSize: 13, fontWeight: '600', color: colors.text }}>
                            {index + 1}. {step.action || 'Unknown'}
                          </Text>
                          <Text style={{
                            fontSize: 12,
                            color: step.status === 'success' ? colors.success : colors.error
                          }}>
                            {step.status}
                          </Text>
                        </View>
                        <Text style={{ fontSize: 12, color: colors.textMuted }}>
                          {step.duration_ms}ms
                        </Text>
                        {step.error && (
                          <Text style={{ fontSize: 12, color: colors.error, marginTop: 4 }}>
                            Error: {step.error}
                          </Text>
                        )}
                      </View>
                    ))}
                    {execution.error && (
                      <View style={{ backgroundColor: colors.error + '20', padding: 12, borderRadius: 8, marginTop: 8 }}>
                        <Text style={{ fontSize: 13, fontWeight: '600', color: colors.error, marginBottom: 4 }}>
                          Execution Error
                        </Text>
                        <Text style={{ fontSize: 12, color: colors.error }}>{execution.error}</Text>
                      </View>
                    )}
                  </View>
                )}
              </TouchableOpacity>
            ))
          )}
        </ScrollView>
      </View>
    </Modal>
  );
}

// Phase 5.5: Import Workflow Modal
function ImportModal({ colors, visible, onClose }) {
  const [importing, setImporting] = useState(false);
  const [fileContent, setFileContent] = useState(null);
  const [fileName, setFileName] = useState('');

  const handleFileSelect = (event) => {
    const file = event.target.files[0];
    if (!file) return;

    setFileName(file.name);
    const reader = new FileReader();
    reader.onload = (e) => {
      try {
        const content = JSON.parse(e.target.result);
        setFileContent(content);
      } catch (error) {
        Alert.alert('Error', 'Invalid JSON file');
      }
    };
    reader.readAsText(file);
  };

  const importWorkflow = async () => {
    if (!fileContent) {
      Alert.alert('Error', 'Please select a file first');
      return;
    }

    try {
      setImporting(true);
      const response = await api.post('/workflows/import', fileContent);
      Alert.alert('Success', `Workflow imported: ${response.data.name}`);
      onClose();
    } catch (error) {
      console.error('Failed to import workflow:', error);
      Alert.alert('Error', error.response?.data?.detail || 'Failed to import workflow');
    } finally {
      setImporting(false);
    }
  };

  return (
    <Modal visible={visible} animationType="slide" transparent>
      <View style={{ flex: 1, backgroundColor: 'rgba(0,0,0,0.5)', justifyContent: 'center', padding: 16 }} data-testid="workflow-import-modal-overlay" testID="workflow-import-modal-overlay">
        <View style={{ backgroundColor: colors.card, borderRadius: 16, padding: 24, maxWidth: 500, width: '100%', alignSelf: 'center' }} data-testid="workflow-import-modal-content" testID="workflow-import-modal-content">
          <Text style={{ fontSize: 20, fontWeight: '700', color: colors.text, marginBottom: 16 }}>
            Import Workflow
          </Text>

          <Text style={{ fontSize: 14, color: colors.textMuted, marginBottom: 12 }}>
            Select a workflow JSON file to import
          </Text>

          <input
            type="file"
            accept=".json"
            onChange={handleFileSelect}
            style={{
              backgroundColor: colors.bgSecondary,
              color: colors.text,
              padding: '12px',
              borderRadius: '8px',
              border: `1px solid ${colors.border}`,
              marginBottom: '16px',
              width: '100%',
              cursor: 'pointer'
            }}
            data-testid="workflow-import-file-input"
          />

          {fileName && (
            <View style={{ backgroundColor: colors.bgSecondary, padding: 12, borderRadius: 8, marginBottom: 16 }}>
              <Text style={{ color: colors.text, fontSize: 14 }}>Selected: {fileName}</Text>
              {fileContent && (
                <Text style={{ color: colors.success, fontSize: 12, marginTop: 4 }}>
                  ✓ Valid workflow file
                </Text>
              )}
            </View>
          )}

          <View style={{ flexDirection: 'row', gap: 12 }}>
            <TouchableOpacity
              onPress={() => {
                setFileContent(null);
                setFileName('');
                onClose();
              }}
              style={{
                flex: 1,
                backgroundColor: colors.bgSecondary,
                padding: 14,
                borderRadius: 8,
                alignItems: 'center'
              }}
              data-testid="workflow-import-cancel-button" testID="workflow-import-cancel-button"
            >
              <Text style={{ color: colors.text, fontWeight: '600' }}>Cancel</Text>
            </TouchableOpacity>

            <TouchableOpacity
              onPress={importWorkflow}
              disabled={!fileContent || importing}
              style={{
                flex: 1,
                backgroundColor: fileContent && !importing ? colors.primary : colors.border,
                padding: 14,
                borderRadius: 8,
                alignItems: 'center'
              }}
              data-testid="workflow-import-submit-button" testID="workflow-import-submit-button"
            >
              {importing ? (
                <ActivityIndicator size="small" color={colors.primaryText} />
              ) : (
                <Text style={{ color: colors.primaryText, fontWeight: '600' }}>Import</Text>
              )}
            </TouchableOpacity>
          </View>
        </View>
      </View>
    </Modal>
  );
}
