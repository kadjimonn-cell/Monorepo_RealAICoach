/**
 * Video Creator Studio - Enterprise-grade video production planning
 * Feature 15: Full-stack video creation platform with AI-powered workflows
 */

import React, { useState } from 'react';
import {
  View,
  Text,
  ScrollView,
  TouchableOpacity,
  TextInput,
  ActivityIndicator,
  Alert,
  Modal,
  StyleSheet,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import FeatureLayout from '../../src/components/FeatureLayout';
import { useTheme } from '../../src/context/ThemeContext';
import { useTranslation } from '../../src/hooks/useTranslation';
import { useVideoStudioData } from '../../src/hooks/useVideoStudioData';
import { VideoStudioStatusBanner } from '../../src/components/video-studio/VideoStudioStatusBanner';

function VideoCreatorStudioScreen() {
  const { colors } = useTheme();
  useTranslation();

  // UI State
  const [activeTab, setActiveTab] = useState('projects');
  
  // Create Project Modal
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [newProject, setNewProject] = useState({
    title: '',
    description: '',
    platform: 'youtube',
    video_type: 'tutorial',
    target_duration_seconds: 600,
  });

  const [scriptPrompt, setScriptPrompt] = useState('');

  const [thumbnailTitle, setThumbnailTitle] = useState('');

  const {
    loading,
    bootstrapErrorMessage,
    bootstrapData,
    projects,
    selectedProject,
    setSelectedProject,
    generatingScript,
    currentScript,
    generatingThumbnails,
    thumbnailConcepts,
    createProject,
    generateScript,
    generateThumbnails,
    deleteProject,
    loadBootstrapData,
  } = useVideoStudioData();

  const accent = colors.success;

  const handleCreateProject = async () => {
    if (!newProject.title.trim()) {
      Alert.alert('Required', 'Please enter a project title');
      return;
    }

    try {
      const response = await createProject(newProject);
      
      if (response?.success) {
        setShowCreateModal(false);
        setNewProject({
          title: '',
          description: '',
          platform: 'youtube',
          video_type: 'tutorial',
          target_duration_seconds: 600,
        });
        Alert.alert('Success', 'Project created successfully!');
      }
    } catch (error) {
      const message = error?.response?.data?.detail || 'Failed to create project';
      Alert.alert('Error', message);
    }
  };

  const handleGenerateScript = async () => {
    if (!selectedProject || !scriptPrompt.trim()) {
      Alert.alert('Required', 'Please enter a script prompt');
      return;
    }

    try {
      const response = await generateScript({
        projectId: selectedProject.project_id,
        prompt: scriptPrompt,
      });

      if (response?.success) {
        setActiveTab('script');
        Alert.alert('Success', 'Script generated successfully!');
      }
    } catch (error) {
      const message = error?.response?.data?.detail || 'Failed to generate script';
      Alert.alert('Error', message);
    }
  };

  const handleGenerateThumbnails = async () => {
    if (!selectedProject || !thumbnailTitle.trim()) {
      Alert.alert('Required', 'Please enter a video title');
      return;
    }

    try {
      const response = await generateThumbnails({
        projectId: selectedProject.project_id,
        videoTitle: thumbnailTitle,
      });

      if (response?.success) {
        setActiveTab('thumbnails');
        Alert.alert('Success', 'Thumbnail concepts generated!');
      }
    } catch (error) {
      const message = error?.response?.data?.detail || 'Failed to generate thumbnails';
      Alert.alert('Error', message);
    }
  };

  const handleDeleteProject = async (projectId) => {
    Alert.alert(
      'Delete Project',
      'Are you sure? This action cannot be undone.',
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Delete',
          style: 'destructive',
          onPress: async () => {
            try {
              await deleteProject(projectId);
              Alert.alert('Success', 'Project deleted');
            } catch {
              Alert.alert('Error', 'Failed to delete project');
            }
          },
        },
      ]
    );
  };

  // Render functions
  const renderPlatformIcon = (platform) => {
    const icons = {
      youtube: 'logo-youtube',
      tiktok: 'musical-notes',
      instagram: 'logo-instagram',
      linkedin: 'logo-linkedin',
      multi: 'apps',
    };
    return icons[platform] || 'videocam';
  };

  const renderStatusBadge = (status) => {
    const statusColors = {
      draft: colors.textMuted,
      script_ready: colors.primary,
      production: colors.warning,
      editing: colors.primary,
      published: colors.success,
    };

    return (
      <View style={[styles.statusBadge, { backgroundColor: statusColors[status] || colors.textMuted }]}>
        <Text style={styles.statusText}>{status.replace('_', ' ')}</Text>
      </View>
    );
  };

  const renderProjectCard = (project) => {
    if (!project || !project.project_id) {
      console.warn('[VideoStudio] Invalid project data:', project);
      return null;
    }
    
    const isSelected = selectedProject?.project_id === project.project_id;
    
    return (
      <TouchableOpacity
        key={project.project_id}
        style={[
          styles.projectCard,
          { 
            backgroundColor: isSelected ? accent + '20' : colors.card,
            borderColor: isSelected ? accent : colors.border,
          }
        ]}
        onPress={() => setSelectedProject(project)}
        data-testid={`video-studio-project-card-${project.project_id}`}
        testID={`video-studio-project-card-${project.project_id}`}
      >
        <View style={styles.projectHeader}>
          <View style={styles.projectTitleRow}>
            <Ionicons 
              name={renderPlatformIcon(project.platform)} 
              size={20} 
              color={isSelected ? accent : colors.text} 
            />
            <Text style={[styles.projectTitle, { color: colors.text }]} numberOfLines={1}>
              {project.title}
            </Text>
          </View>
          {renderStatusBadge(project.status)}
        </View>

        {project.description && (
          <Text style={[styles.projectDesc, { color: colors.textSec }]} numberOfLines={2}>
            {project.description}
          </Text>
        )}

        <View style={styles.projectMeta}>
          <View style={styles.metaItem}>
            <Ionicons name="time-outline" size={14} color={colors.textMuted} />
            <Text style={[styles.metaText, { color: colors.textMuted }]}>
              {Math.floor(project.target_duration_seconds / 60)} min
            </Text>
          </View>
          <View style={styles.metaItem}>
            <Ionicons name="film-outline" size={14} color={colors.textMuted} />
            <Text style={[styles.metaText, { color: colors.textMuted }]}>
              {project.video_type}
            </Text>
          </View>
        </View>

        {isSelected && (
          <View style={styles.projectActions}>
            <TouchableOpacity 
              style={[styles.actionBtn, { backgroundColor: accent }]}
              onPress={() => setActiveTab('script')}
              data-testid={`video-studio-project-script-action-${project.project_id}`}
              testID={`video-studio-project-script-action-${project.project_id}`}
            >
              <Ionicons name="document-text" size={16} color={colors.primaryText} />
              <Text style={styles.actionBtnText}>Script</Text>
            </TouchableOpacity>
            
            <TouchableOpacity 
              style={[styles.actionBtn, { backgroundColor: colors.bgSoft, borderWidth: 1, borderColor: colors.border }]}
              onPress={() => setActiveTab('thumbnails')}
              data-testid={`video-studio-project-thumbnails-action-${project.project_id}`}
              testID={`video-studio-project-thumbnails-action-${project.project_id}`}
            >
              <Ionicons name="image-outline" size={16} color={colors.text} />
              <Text style={[styles.actionBtnText, { color: colors.text }]}>Thumbnails</Text>
            </TouchableOpacity>
            
            <TouchableOpacity 
              style={[styles.actionBtn, { backgroundColor: colors.error + '20' }]}
              onPress={() => handleDeleteProject(project.project_id)}
              data-testid={`video-studio-project-delete-action-${project.project_id}`}
              testID={`video-studio-project-delete-action-${project.project_id}`}
            >
              <Ionicons name="trash-outline" size={16} color={colors.error} />
            </TouchableOpacity>
          </View>
        )}
      </TouchableOpacity>
    );
  };

  const renderProjectsTab = () => (
    <ScrollView style={styles.tabContent} data-testid="video-studio-projects-tab-content" testID="video-studio-projects-tab-content">
      {!!bootstrapErrorMessage && (
        <VideoStudioStatusBanner
          message={bootstrapErrorMessage}
          onRefresh={loadBootstrapData}
          colors={{
            card: colors.card,
            border: colors.border,
            text: colors.text,
            textSec: colors.textSec,
            primary: accent,
          }}
        />
      )}

      <View style={[styles.statsCard, { backgroundColor: colors.card, borderColor: colors.border }]} data-testid="video-studio-stats-card" testID="video-studio-stats-card">
        <View style={styles.statItem}>
          <Text style={[styles.statValue, { color: colors.text }]} data-testid="video-studio-stats-project-count" testID="video-studio-stats-project-count">{projects.length}</Text>
          <Text style={[styles.statLabel, { color: colors.textSec }]}>Projects</Text>
        </View>
        <View style={[styles.statDivider, { backgroundColor: colors.border }]} />
        <View style={styles.statItem}>
          <Text style={[styles.statValue, { color: colors.text }]} data-testid="video-studio-stats-plan" testID="video-studio-stats-plan"> 
            {bootstrapData?.plan || 'free'}
          </Text>
          <Text style={[styles.statLabel, { color: colors.textSec }]}>Plan</Text>
        </View>
        <View style={[styles.statDivider, { backgroundColor: colors.border }]} />
        <View style={styles.statItem}>
          <Text style={[styles.statValue, { color: colors.text }]} data-testid="video-studio-stats-scripts-per-day" testID="video-studio-stats-scripts-per-day"> 
            {bootstrapData?.limits?.scripts_per_day === -1 ? '∞' : bootstrapData?.limits?.scripts_per_day || 3}
          </Text>
          <Text style={[styles.statLabel, { color: colors.textSec }]}>Scripts/day</Text>
        </View>
      </View>

      <View style={styles.projectsHeader} data-testid="video-studio-projects-header" testID="video-studio-projects-header">
        <Text style={[styles.sectionTitle, { color: colors.text }]}>My Projects</Text>
        <TouchableOpacity
          style={[styles.createBtn, { backgroundColor: accent }]}
          onPress={() => setShowCreateModal(true)}
          data-testid="video-studio-new-project-button"
          testID="video-studio-new-project-button"
        >
          <Ionicons name="add" size={20} color={colors.primaryText} />
          <Text style={styles.createBtnText}>New Project</Text>
        </TouchableOpacity>
      </View>

      {projects.length === 0 ? (
        <View style={[styles.emptyState, { backgroundColor: colors.card, borderColor: colors.border }]} data-testid="video-studio-empty-state" testID="video-studio-empty-state">
          <Ionicons name="videocam-outline" size={48} color={colors.textMuted} />
          <Text style={[styles.emptyTitle, { color: colors.text }]}>No Projects Yet</Text>
          <Text style={[styles.emptyDesc, { color: colors.textSec }]}>
            Create your first video project to get started
          </Text>
          <TouchableOpacity
            style={[styles.emptyBtn, { backgroundColor: accent }]}
            onPress={() => setShowCreateModal(true)}
            data-testid="video-studio-empty-create-project-button"
            testID="video-studio-empty-create-project-button"
          >
            <Text style={styles.emptyBtnText}>Create Project</Text>
          </TouchableOpacity>

          <TouchableOpacity
            style={[styles.emptyRetryBtn, { borderColor: accent }]}
            onPress={loadBootstrapData}
            data-testid="video-studio-empty-refresh-studio-button"
            testID="video-studio-empty-refresh-studio-button"
          >
            <Ionicons name="refresh" size={16} color={accent} />
            <Text style={[styles.emptyRetryBtnText, { color: accent }]}>Refresh Studio</Text>
          </TouchableOpacity>
        </View>
      ) : (
        <View style={styles.projectsList} data-testid="video-studio-projects-list" testID="video-studio-projects-list">
          {projects.map(renderProjectCard)}
        </View>
      )}
    </ScrollView>
  );

  const renderScriptTab = () => {
    if (!selectedProject) {
      return (
        <View style={[styles.placeholderContainer, { backgroundColor: colors.card }]} data-testid="video-studio-script-placeholder" testID="video-studio-script-placeholder"> 
          <Ionicons name="document-text-outline" size={48} color={colors.textMuted} />
          <Text style={[styles.placeholderText, { color: colors.textSec }]}>
            Select a project to generate scripts
          </Text>
        </View>
      );
    }

    return (
      <ScrollView style={styles.tabContent} data-testid="video-studio-script-tab-content" testID="video-studio-script-tab-content">
        <View style={[styles.card, { backgroundColor: colors.card, borderColor: colors.border }]} data-testid="video-studio-script-generator-card" testID="video-studio-script-generator-card">
          <Text style={[styles.cardTitle, { color: colors.text }]}>AI Script Generator</Text>
          <Text style={[styles.cardDesc, { color: colors.textSec }]}>
            Generate professional video scripts using GPT-4o
          </Text>

          <Text style={[styles.label, { color: colors.text }]}>Script Prompt</Text>
          <TextInput
            style={[styles.textArea, { 
              backgroundColor: colors.bg, 
              color: colors.text,
              borderColor: colors.border
            }]}
            multiline
            numberOfLines={4}
            placeholder="Describe your video content, target audience, and key points..."
            placeholderTextColor={colors.textMuted}
            value={scriptPrompt}
            onChangeText={setScriptPrompt}
            data-testid="video-studio-script-prompt-input"
            testID="video-studio-script-prompt-input"
          />

          <TouchableOpacity
            style={[styles.generateBtn, { backgroundColor: accent }]}
            onPress={handleGenerateScript}
            disabled={generatingScript}
            data-testid="video-studio-generate-script-button"
            testID="video-studio-generate-script-button"
          >
            {generatingScript ? (
              <ActivityIndicator color={colors.primaryText} />
            ) : (
              <>
                <Ionicons name="sparkles" size={18} color={colors.primaryText} />
                <Text style={styles.generateBtnText}>Generate Script</Text>
              </>
            )}
          </TouchableOpacity>
        </View>

        {currentScript && (
          <View style={[styles.card, { backgroundColor: colors.card, borderColor: colors.border }]} data-testid="video-studio-generated-script-card" testID="video-studio-generated-script-card">
            <View style={styles.scriptHeader}>
              <Ionicons name="checkmark-circle" size={20} color={colors.success} />
              <Text style={[styles.cardTitle, { color: colors.text, marginLeft: 8 }]}>
                Generated Script
              </Text>
            </View>
            
            <View style={styles.scriptMeta}>
              <View style={styles.metaChip} data-testid="video-studio-generated-script-word-chip" testID="video-studio-generated-script-word-chip">
                <Text style={[styles.metaChipText, { color: colors.text }]} data-testid="video-studio-generated-script-word-count" testID="video-studio-generated-script-word-count"> 
                  {currentScript.word_count} words
                </Text>
              </View>
              <View style={styles.metaChip} data-testid="video-studio-generated-script-duration-chip" testID="video-studio-generated-script-duration-chip">
                <Text style={[styles.metaChipText, { color: colors.text }]} data-testid="video-studio-generated-script-duration" testID="video-studio-generated-script-duration"> 
                  ~{Math.floor(currentScript.estimated_duration_seconds / 60)} min
                </Text>
              </View>
            </View>

            <ScrollView 
              style={[styles.scriptContent, { backgroundColor: colors.bg }]}
              nestedScrollEnabled
              data-testid="video-studio-generated-script-content"
              testID="video-studio-generated-script-content"
            >
              <Text style={[styles.scriptText, { color: colors.text }]}>
                {currentScript.content}
              </Text>
            </ScrollView>
          </View>
        )}
      </ScrollView>
    );
  };

  const renderThumbnailsTab = () => {
    if (!selectedProject) {
      return (
        <View style={[styles.placeholderContainer, { backgroundColor: colors.card }]} data-testid="video-studio-thumbnails-placeholder" testID="video-studio-thumbnails-placeholder"> 
          <Ionicons name="image-outline" size={48} color={colors.textMuted} />
          <Text style={[styles.placeholderText, { color: colors.textSec }]}>
            Select a project to generate thumbnails
          </Text>
        </View>
      );
    }

    return (
      <ScrollView style={styles.tabContent} data-testid="video-studio-thumbnails-tab-content" testID="video-studio-thumbnails-tab-content">
        <View style={[styles.card, { backgroundColor: colors.card, borderColor: colors.border }]} data-testid="video-studio-thumbnail-generator-card" testID="video-studio-thumbnail-generator-card">
          <Text style={[styles.cardTitle, { color: colors.text }]}>Thumbnail Designer</Text>
          <Text style={[styles.cardDesc, { color: colors.textSec }]}>
            Generate eye-catching thumbnail concepts for your video
          </Text>

          <Text style={[styles.label, { color: colors.text }]}>Video Title</Text>
          <TextInput
            style={[styles.input, { 
              backgroundColor: colors.bg, 
              color: colors.text,
              borderColor: colors.border
            }]}
            placeholder="Enter your video title..."
            placeholderTextColor={colors.textMuted}
            value={thumbnailTitle}
            onChangeText={setThumbnailTitle}
            data-testid="video-studio-thumbnail-title-input"
            testID="video-studio-thumbnail-title-input"
          />

          <TouchableOpacity
            style={[styles.generateBtn, { backgroundColor: accent }]}
            onPress={handleGenerateThumbnails}
            disabled={generatingThumbnails}
            data-testid="video-studio-generate-thumbnails-button"
            testID="video-studio-generate-thumbnails-button"
          >
            {generatingThumbnails ? (
              <ActivityIndicator color={colors.primaryText} />
            ) : (
              <>
                <Ionicons name="color-palette" size={18} color={colors.primaryText} />
                <Text style={styles.generateBtnText}>Generate Concepts</Text>
              </>
            )}
          </TouchableOpacity>
        </View>

        {thumbnailConcepts.length > 0 && (
          <View style={[styles.card, { backgroundColor: colors.card, borderColor: colors.border }]} data-testid="video-studio-thumbnail-concepts-card" testID="video-studio-thumbnail-concepts-card">
            <Text style={[styles.cardTitle, { color: colors.text }]} data-testid="video-studio-thumbnail-concepts-title" testID="video-studio-thumbnail-concepts-title">Thumbnail Concepts</Text>
            {thumbnailConcepts.map((concept, index) => (
              <View 
                key={concept.concept_id} 
                style={[styles.conceptCard, { backgroundColor: colors.bg, borderColor: colors.border }]}
                data-testid={`video-studio-thumbnail-concept-${concept.concept_id}`}
                testID={`video-studio-thumbnail-concept-${concept.concept_id}`}
              >
                <View style={styles.conceptHeader}>
                  <Text style={[styles.conceptTitle, { color: colors.text }]}>
                    Concept {index + 1}
                  </Text>
                  {concept.selected && (
                    <View style={[styles.selectedBadge, { backgroundColor: accent }]}>
                      <Ionicons name="checkmark" size={12} color={colors.primaryText} />
                      <Text style={styles.selectedText}>Selected</Text>
                    </View>
                  )}
                </View>
                <Text style={[styles.conceptDesc, { color: colors.textSec }]} data-testid={`video-studio-thumbnail-concept-description-${concept.concept_id}`} testID={`video-studio-thumbnail-concept-description-${concept.concept_id}`}> 
                  {concept.description}
                </Text>
                <View style={styles.colorScheme}>
                  {concept.color_scheme.map((color, i) => (
                    <View 
                      key={i} 
                      style={[styles.colorDot, { backgroundColor: color }]} 
                      data-testid={`video-studio-thumbnail-concept-color-${concept.concept_id}-${i}`}
                      testID={`video-studio-thumbnail-concept-color-${concept.concept_id}-${i}`}
                    />
                  ))}
                </View>
              </View>
            ))}
          </View>
        )}
      </ScrollView>
    );
  };

  const renderCreateModal = () => (
    <Modal
      visible={showCreateModal}
      animationType="slide"
      transparent
      onRequestClose={() => setShowCreateModal(false)}
      testID="video-studio-create-project-modal"
    >
      <View style={styles.modalOverlay} data-testid="video-studio-create-project-modal-overlay" testID="video-studio-create-project-modal-overlay">
        <View style={[styles.modalContent, { backgroundColor: colors.card }]} data-testid="video-studio-create-project-modal-content" testID="video-studio-create-project-modal-content"> 
          <View style={styles.modalHeader} data-testid="video-studio-create-project-modal-header" testID="video-studio-create-project-modal-header">
            <Text style={[styles.modalTitle, { color: colors.text }]}>New Video Project</Text>
            <TouchableOpacity onPress={() => setShowCreateModal(false)} data-testid="video-studio-create-project-modal-close" testID="video-studio-create-project-modal-close">
              <Ionicons name="close" size={24} color={colors.text} />
            </TouchableOpacity>
          </View>

          <ScrollView style={styles.modalBody} data-testid="video-studio-create-project-modal-body" testID="video-studio-create-project-modal-body">
            <Text style={[styles.label, { color: colors.text }]}>Project Title *</Text>
            <TextInput
              style={[styles.input, { 
                backgroundColor: colors.bg, 
                color: colors.text,
                borderColor: colors.border
              }]}
              placeholder="e.g. Python Tutorial Series"
              placeholderTextColor={colors.textMuted}
              value={newProject.title}
              onChangeText={(text) => setNewProject({ ...newProject, title: text })}
              data-testid="video-studio-create-project-title-input"
              testID="video-studio-create-project-title-input"
            />

            <Text style={[styles.label, { color: colors.text }]}>Description</Text>
            <TextInput
              style={[styles.textArea, { 
                backgroundColor: colors.bg, 
                color: colors.text,
                borderColor: colors.border
              }]}
              multiline
              numberOfLines={3}
              placeholder="Brief description of your video project..."
              placeholderTextColor={colors.textMuted}
              value={newProject.description}
              onChangeText={(text) => setNewProject({ ...newProject, description: text })}
              data-testid="video-studio-create-project-description-input"
              testID="video-studio-create-project-description-input"
            />

            <Text style={[styles.label, { color: colors.text }]}>Platform</Text>
            <View style={styles.platformGrid}>
              {['youtube', 'tiktok', 'instagram', 'linkedin'].map((platform) => {
                const isSelected = newProject.platform === platform;
                return (
                  <TouchableOpacity
                    key={platform}
                    style={[
                      styles.platformChip,
                      { 
                        backgroundColor: isSelected ? accent : colors.bg,
                        borderColor: isSelected ? accent : colors.border
                      }
                    ]}
                    onPress={() => setNewProject({ ...newProject, platform: platform })}
                    data-testid={`video-studio-create-project-platform-${platform}`}
                    testID={`video-studio-create-project-platform-${platform}`}
                  >
                    <Ionicons 
                      name={renderPlatformIcon(platform)} 
                      size={20} 
                      color={isSelected ? colors.primaryText : colors.text} 
                    />
                    <Text style={[
                      styles.platformText,
                      { color: isSelected ? colors.primaryText : colors.text }
                    ]}>
                      {platform}
                    </Text>
                  </TouchableOpacity>
                );
              })}
            </View>

            <Text style={[styles.label, { color: colors.text }]}>Video Type</Text>
            <View style={styles.typeGrid}>
              {['tutorial', 'vlog', 'review', 'educational', 'promotional'].map((type) => {
                const isSelected = newProject.video_type === type;
                return (
                  <TouchableOpacity
                    key={type}
                    style={[
                      styles.typeChip,
                      { 
                        backgroundColor: isSelected ? accent + '20' : colors.bg,
                        borderColor: isSelected ? accent : colors.border
                      }
                    ]}
                    onPress={() => setNewProject({ ...newProject, video_type: type })}
                    data-testid={`video-studio-create-project-type-${type}`}
                    testID={`video-studio-create-project-type-${type}`}
                  >
                    <Text style={[
                      styles.typeText,
                      { color: isSelected ? accent : colors.text }
                    ]}>
                      {type}
                    </Text>
                  </TouchableOpacity>
                );
              })}
            </View>
          </ScrollView>

          <View style={styles.modalFooter} data-testid="video-studio-create-project-modal-footer" testID="video-studio-create-project-modal-footer">
            <TouchableOpacity
              style={[styles.modalBtn, { backgroundColor: colors.bgSoft }]}
              onPress={() => setShowCreateModal(false)}
              data-testid="video-studio-create-project-cancel-button"
              testID="video-studio-create-project-cancel-button"
            >
              <Text style={[styles.modalBtnText, { color: colors.text }]}>Cancel</Text>
            </TouchableOpacity>
            <TouchableOpacity
              style={[styles.modalBtn, { backgroundColor: accent }]}
              onPress={handleCreateProject}
              disabled={loading}
              data-testid="video-studio-create-project-submit-button"
              testID="video-studio-create-project-submit-button"
            >
              {loading ? (
                <ActivityIndicator color={colors.primaryText} />
              ) : (
                <Text style={[styles.modalBtnText, { color: colors.primaryText }]}>Create</Text>
              )}
            </TouchableOpacity>
          </View>
        </View>
      </View>
    </Modal>
  );

  if (loading && !bootstrapData) {
    return (
      <FeatureLayout
        feature="ai-video"
        title="Video Creator Studio"
        subtitle="Professional video production planning"
        icon="videocam"
        color={accent}
      >
        <View style={styles.loadingContainer}>
          <ActivityIndicator size="large" color={accent} />
          <Text style={[styles.loadingText, { color: colors.textSec }]}>
            Loading studio...
          </Text>
        </View>
      </FeatureLayout>
    );
  }

  return (
    <FeatureLayout
      feature="ai-video"
      title="Video Creator Studio"
      subtitle="AI-powered video production workflows"
      icon="videocam"
      color={accent}
      showActions={false}
    >
      <View style={styles.container} data-testid="video-studio-root" testID="video-studio-root">
        {/* Tabs */}
        <View style={[styles.tabBar, { backgroundColor: colors.card, borderBottomColor: colors.border }]} data-testid="video-studio-tab-bar" testID="video-studio-tab-bar"> 
          <TouchableOpacity
            style={[
              styles.tab,
              activeTab === 'projects' && [styles.activeTab, { borderBottomColor: accent }]
            ]}
            onPress={() => setActiveTab('projects')}
            data-testid="video-studio-tab-projects"
            testID="video-studio-tab-projects"
          >
            <Ionicons 
              name="folder-outline" 
              size={20} 
              color={activeTab === 'projects' ? accent : colors.textMuted} 
            />
            <Text style={[
              styles.tabText,
              { color: activeTab === 'projects' ? accent : colors.textMuted }
            ]}>
              Projects
            </Text>
          </TouchableOpacity>

          <TouchableOpacity
            style={[
              styles.tab,
              activeTab === 'script' && [styles.activeTab, { borderBottomColor: accent }]
            ]}
            onPress={() => setActiveTab('script')}
            data-testid="video-studio-tab-script"
            testID="video-studio-tab-script"
          >
            <Ionicons 
              name="document-text-outline" 
              size={20} 
              color={activeTab === 'script' ? accent : colors.textMuted} 
            />
            <Text style={[
              styles.tabText,
              { color: activeTab === 'script' ? accent : colors.textMuted }
            ]}>
              Script
            </Text>
          </TouchableOpacity>

          <TouchableOpacity
            style={[
              styles.tab,
              activeTab === 'thumbnails' && [styles.activeTab, { borderBottomColor: accent }]
            ]}
            onPress={() => setActiveTab('thumbnails')}
            data-testid="video-studio-tab-thumbnails"
            testID="video-studio-tab-thumbnails"
          >
            <Ionicons 
              name="image-outline" 
              size={20} 
              color={activeTab === 'thumbnails' ? accent : colors.textMuted} 
            />
            <Text style={[
              styles.tabText,
              { color: activeTab === 'thumbnails' ? accent : colors.textMuted }
            ]}>
              Thumbnails
            </Text>
          </TouchableOpacity>
        </View>

        {/* Tab Content */}
        {activeTab === 'projects' && renderProjectsTab()}
        {activeTab === 'script' && renderScriptTab()}
        {activeTab === 'thumbnails' && renderThumbnailsTab()}

        {/* Create Project Modal */}
        {renderCreateModal()}
      </View>
    </FeatureLayout>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
  loadingContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    padding: 20,
  },
  loadingText: {
    marginTop: 12,
    fontSize: 14,
  },
  tabBar: {
    flexDirection: 'row',
    borderBottomWidth: 1,
  },
  tab: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 14,
    gap: 6,
    borderBottomWidth: 2,
    borderBottomColor: 'transparent',
  },
  activeTab: {
    borderBottomWidth: 2,
  },
  tabText: {
    fontSize: 14,
    fontWeight: '600',
  },
  tabContent: {
    flex: 1,
    padding: 16,
  },
  statsCard: {
    flexDirection: 'row',
    borderRadius: 12,
    padding: 16,
    marginBottom: 16,
    borderWidth: 1,
  },
  statItem: {
    flex: 1,
    alignItems: 'center',
  },
  statValue: {
    fontSize: 24,
    fontWeight: '700',
  },
  statLabel: {
    fontSize: 12,
    marginTop: 4,
  },
  statDivider: {
    width: 1,
    marginHorizontal: 12,
  },
  projectsHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 16,
  },
  sectionTitle: {
    fontSize: 18,
    fontWeight: '700',
  },
  createBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 16,
    paddingVertical: 10,
    borderRadius: 8,
    gap: 6,
  },
  createBtnText: {
    color: 'var(--app-primary-text)',
    fontSize: 14,
    fontWeight: '600',
  },
  projectsList: {
    gap: 12,
  },
  projectCard: {
    borderRadius: 12,
    padding: 16,
    borderWidth: 1,
  },
  projectHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 8,
  },
  projectTitleRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    flex: 1,
  },
  projectTitle: {
    fontSize: 16,
    fontWeight: '600',
    flex: 1,
  },
  statusBadge: {
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: 6,
  },
  statusText: {
    color: 'var(--app-primary-text)',
    fontSize: 11,
    fontWeight: '600',
    textTransform: 'capitalize',
  },
  projectDesc: {
    fontSize: 13,
    lineHeight: 18,
    marginBottom: 12,
  },
  projectMeta: {
    flexDirection: 'row',
    gap: 16,
    marginBottom: 12,
  },
  metaItem: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
  },
  metaText: {
    fontSize: 12,
  },
  projectActions: {
    flexDirection: 'row',
    gap: 8,
    marginTop: 12,
    paddingTop: 12,
    borderTopWidth: 1,
    borderTopColor: 'rgba(0,0,0,0.1)',
  },
  actionBtn: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 10,
    borderRadius: 8,
    gap: 6,
  },
  actionBtnText: {
    color: 'var(--app-primary-text)',
    fontSize: 13,
    fontWeight: '600',
  },
  emptyState: {
    borderRadius: 12,
    padding: 40,
    alignItems: 'center',
    borderWidth: 1,
    borderStyle: 'dashed',
  },
  emptyTitle: {
    fontSize: 18,
    fontWeight: '600',
    marginTop: 16,
  },
  emptyDesc: {
    fontSize: 14,
    textAlign: 'center',
    marginTop: 8,
  },
  emptyBtn: {
    marginTop: 20,
    paddingHorizontal: 24,
    paddingVertical: 12,
    borderRadius: 8,
  },
  emptyBtnText: {
    color: 'var(--app-primary-text)',
    fontSize: 14,
    fontWeight: '600',
  },
  emptyRetryBtn: {
    marginTop: 10,
    borderWidth: 1,
    borderRadius: 8,
    paddingHorizontal: 20,
    paddingVertical: 10,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  emptyRetryBtnText: {
    fontSize: 13,
    fontWeight: '600',
  },
  card: {
    borderRadius: 12,
    padding: 16,
    marginBottom: 16,
    borderWidth: 1,
  },
  cardTitle: {
    fontSize: 16,
    fontWeight: '700',
    marginBottom: 4,
  },
  cardDesc: {
    fontSize: 13,
    marginBottom: 16,
    lineHeight: 18,
  },
  label: {
    fontSize: 13,
    fontWeight: '600',
    marginBottom: 8,
  },
  input: {
    borderRadius: 8,
    padding: 12,
    fontSize: 14,
    marginBottom: 16,
    borderWidth: 1,
  },
  textArea: {
    borderRadius: 8,
    padding: 12,
    fontSize: 14,
    marginBottom: 16,
    minHeight: 100,
    textAlignVertical: 'top',
    borderWidth: 1,
  },
  generateBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 14,
    borderRadius: 8,
    gap: 8,
  },
  generateBtnText: {
    color: 'var(--app-primary-text)',
    fontSize: 14,
    fontWeight: '600',
  },
  scriptHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 12,
  },
  scriptMeta: {
    flexDirection: 'row',
    gap: 8,
    marginBottom: 12,
  },
  metaChip: {
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 6,
    backgroundColor: 'rgba(20, 184, 166, 0.1)',
  },
  metaChipText: {
    fontSize: 12,
    fontWeight: '600',
  },
  scriptContent: {
    borderRadius: 8,
    padding: 12,
    maxHeight: 400,
  },
  scriptText: {
    fontSize: 14,
    lineHeight: 22,
  },
  conceptCard: {
    borderRadius: 8,
    padding: 12,
    marginBottom: 12,
    borderWidth: 1,
  },
  conceptHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 8,
  },
  conceptTitle: {
    fontSize: 14,
    fontWeight: '600',
  },
  selectedBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 4,
    gap: 4,
  },
  selectedText: {
    color: 'var(--app-primary-text)',
    fontSize: 11,
    fontWeight: '600',
  },
  conceptDesc: {
    fontSize: 13,
    lineHeight: 18,
    marginBottom: 12,
  },
  colorScheme: {
    flexDirection: 'row',
    gap: 8,
  },
  colorDot: {
    width: 32,
    height: 32,
    borderRadius: 16,
  },
  placeholderContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    padding: 40,
    margin: 16,
    borderRadius: 12,
  },
  placeholderText: {
    fontSize: 14,
    marginTop: 12,
    textAlign: 'center',
  },
  modalOverlay: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.5)',
    justifyContent: 'flex-end',
  },
  modalContent: {
    borderTopLeftRadius: 20,
    borderTopRightRadius: 20,
    maxHeight: '90%',
  },
  modalHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: 20,
    borderBottomWidth: 1,
    borderBottomColor: 'rgba(0,0,0,0.1)',
  },
  modalTitle: {
    fontSize: 18,
    fontWeight: '700',
  },
  modalBody: {
    padding: 20,
  },
  platformGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
    marginBottom: 16,
  },
  platformChip: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 16,
    paddingVertical: 10,
    borderRadius: 8,
    gap: 8,
    borderWidth: 1,
  },
  platformText: {
    fontSize: 13,
    fontWeight: '600',
    textTransform: 'capitalize',
  },
  typeGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
    marginBottom: 16,
  },
  typeChip: {
    paddingHorizontal: 16,
    paddingVertical: 10,
    borderRadius: 8,
    borderWidth: 1,
  },
  typeText: {
    fontSize: 13,
    fontWeight: '600',
    textTransform: 'capitalize',
  },
  modalFooter: {
    flexDirection: 'row',
    padding: 20,
    gap: 12,
    borderTopWidth: 1,
    borderTopColor: 'rgba(0,0,0,0.1)',
  },
  modalBtn: {
    flex: 1,
    paddingVertical: 14,
    borderRadius: 8,
    alignItems: 'center',
  },
  modalBtnText: {
    fontSize: 14,
    fontWeight: '600',
  },
});

// Export directly without Error Boundary wrapper to prevent unmount issues
// The FeatureLayout already has error handling, and the extra wrapper was causing
// component lifecycle issues during auth session renewal
export default VideoCreatorStudioScreen;
