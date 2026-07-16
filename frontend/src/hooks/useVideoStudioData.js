import { useCallback, useEffect, useRef, useState } from 'react';
import { Alert } from 'react-native';
import api from '../services/api';
import { useAuth } from '../context/AuthContext';

const createFallbackUserId = () => (
  `user_${Math.random().toString(36).slice(2)}${Date.now().toString(36)}`.slice(0, 78)
);

const EMPTY_BOOTSTRAP = {
  success: false,
  plan: 'free',
  projects: [],
  limits: {},
  usage: {},
  platform_presets: [],
  templates: [],
  features: {},
  project_count: 0,
};

const normalizeBootstrap = (payload) => ({
  success: payload?.success !== false,
  plan: payload?.plan || 'free',
  projects: Array.isArray(payload?.projects) ? payload.projects : [],
  limits: payload?.limits || {},
  usage: payload?.usage || {},
  platform_presets: payload?.platform_presets || [],
  templates: payload?.templates || [],
  features: payload?.features || {},
  project_count: payload?.project_count || 0,
});

export const useVideoStudioData = () => {
  const { user, loading: authLoading } = useAuth();
  const [fallbackUserId] = useState(() => user?.user_id || createFallbackUserId());

  const [loading, setLoading] = useState(false);
  const [bootstrapErrorMessage, setBootstrapErrorMessage] = useState('');
  const [bootstrapData, setBootstrapData] = useState(null);
  const [projects, setProjects] = useState([]);
  const [selectedProject, setSelectedProject] = useState(null);

  const [generatingScript, setGeneratingScript] = useState(false);
  const [currentScript, setCurrentScript] = useState(null);

  const [generatingThumbnails, setGeneratingThumbnails] = useState(false);
  const [thumbnailConcepts, setThumbnailConcepts] = useState([]);

  const mountedRef = useRef(true);
  const hasAttemptedLoad = useRef(false);

  const loadBootstrapData = useCallback(async () => {
    if (!mountedRef.current) return;

    try {
      setLoading(true);
      setBootstrapErrorMessage('');
      const response = await api.get('/video-studio/bootstrap', {
        params: { fallback_user_id: fallbackUserId },
      });

      const normalized = normalizeBootstrap(response.data);
      if (!mountedRef.current) return;

      setBootstrapData(normalized);
      setProjects(normalized.projects);
    } catch (error) {
      const isAuthError = error?.response?.status === 401 || error?.response?.status === 403;

      if (!mountedRef.current) return;

      if (isAuthError) {
        setBootstrapData(EMPTY_BOOTSTRAP);
        setBootstrapErrorMessage('Session refresh in progress. Studio data may be limited temporarily.');
      } else {
        setBootstrapErrorMessage('Unable to refresh studio data right now.');
        Alert.alert('Error', 'Failed to load studio. Please try again.');
      }
    } finally {
      if (mountedRef.current) {
        setLoading(false);
      }
    }
  }, [fallbackUserId]);

  useEffect(() => {
    mountedRef.current = true;

    if (authLoading) return;
    if (hasAttemptedLoad.current) return;

    hasAttemptedLoad.current = true;
    loadBootstrapData();

    return () => {
      mountedRef.current = false;
    };
  }, [authLoading, user, loadBootstrapData]);

  const createProject = async (projectPayload) => {
    setLoading(true);
    try {
      const response = await api.post('/video-studio/projects/create', {
        ...projectPayload,
        fallback_user_id: fallbackUserId,
      });

      if (response.data?.success && response.data?.project) {
        setProjects((prev) => [response.data.project, ...prev]);
      }

      return response.data;
    } finally {
      setLoading(false);
    }
  };

  const generateScript = async ({ projectId, prompt, tone = 'professional', includeHook = true, includeCta = true }) => {
    setGeneratingScript(true);
    try {
      const response = await api.post('/video-studio/scripts/generate', {
        project_id: projectId,
        prompt,
        tone,
        include_hook: includeHook,
        include_cta: includeCta,
        fallback_user_id: fallbackUserId,
      });

      if (response.data?.success && response.data?.script) {
        setCurrentScript(response.data.script);
      }

      return response.data;
    } finally {
      setGeneratingScript(false);
    }
  };

  const generateThumbnails = async ({ projectId, videoTitle, conceptCount = 3, style = 'bold' }) => {
    setGeneratingThumbnails(true);
    try {
      const response = await api.post('/video-studio/thumbnails/generate', {
        project_id: projectId,
        video_title: videoTitle,
        concept_count: conceptCount,
        style,
        fallback_user_id: fallbackUserId,
      });

      if (response.data?.success) {
        setThumbnailConcepts(response.data?.thumbnails?.concepts || []);
      }

      return response.data;
    } finally {
      setGeneratingThumbnails(false);
    }
  };

  const deleteProject = async (projectId) => {
    await api.delete(`/video-studio/projects/${projectId}`, {
      params: { fallback_user_id: fallbackUserId },
    });

    setProjects((prev) => prev.filter((project) => project.project_id !== projectId));
    setSelectedProject((prev) => (prev?.project_id === projectId ? null : prev));
  };

  return {
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
  };
};
