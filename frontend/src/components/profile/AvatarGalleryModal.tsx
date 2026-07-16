import React, { useState, useCallback, useEffect } from 'react';
import { View, Text, TouchableOpacity, ScrollView, Image, ActivityIndicator, useWindowDimensions, Modal, TextInput, Platform } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { useTheme } from '../../context/ThemeContext';
import { handleAppRecoverableError } from '../../utils/appRecoverableError';

const AVATAR_CATEGORIES = [
  { key: 'all', label: 'All', icon: 'grid-outline' },
  { key: 'female', label: 'Female', icon: 'woman-outline' },
  { key: 'male', label: 'Male', icon: 'man-outline' },
  { key: 'kids', label: 'Kids', icon: 'happy-outline' },
  { key: 'animation', label: 'Animation', icon: 'color-wand-outline' },
  { key: 'character', label: 'Character', icon: 'planet-outline' },
  { key: 'ai', label: 'AI Generate', icon: 'sparkles-outline' },
  { key: 'history', label: 'History', icon: 'time-outline' },
];

const AVATARS = [
  { id: 'f1', category: 'female', label: 'Professional Woman', url: 'https://static.prod-images.emergentagent.com/jobs/20abb711-28bb-4d84-a96f-178a755fd768/images/235a1f2bd3df83b9d99bafb960d1b7d6e5a83d659b9c2caaeec68dee4de51e53.png' },
  { id: 'f2', category: 'female', label: 'Curly Hair Woman', url: 'https://static.prod-images.emergentagent.com/jobs/20abb711-28bb-4d84-a96f-178a755fd768/images/88d3d4f39a0ea5a9b97650090b9a73086f404350dad434dea345ecf1ffc9423d.png' },
  { id: 'f3', category: 'female', label: 'Hijab Professional', url: 'https://static.prod-images.emergentagent.com/jobs/20abb711-28bb-4d84-a96f-178a755fd768/images/c00eec7f1c89a7d5000f2c3248df6481103d0e7c56e6c2bf64a14277ff04d93d.png' },
  { id: 'm1', category: 'male', label: 'Bearded Professional', url: 'https://static.prod-images.emergentagent.com/jobs/20abb711-28bb-4d84-a96f-178a755fd768/images/7fbfe7ead88f5a508478f5e18ec0c9875ebdc698f38ed5c34423e2702f1b3ee7.png' },
  { id: 'm2', category: 'male', label: 'Senior Professional', url: 'https://static.prod-images.emergentagent.com/jobs/20abb711-28bb-4d84-a96f-178a755fd768/images/2e1ab051ffffacca7c3c74f0095b0bc8b06cf91a5f9aa95ba2c03a4a1d78b5f7.png' },
  { id: 'm3', category: 'male', label: 'Young Professional', url: 'https://static.prod-images.emergentagent.com/jobs/20abb711-28bb-4d84-a96f-178a755fd768/images/1c41d15f4a1838053ca2da7612b8cd622616fae22cbae4fd39edc01e7b9b0249.png' },
  { id: 'k1', category: 'kids', label: 'Girl', url: 'https://static.prod-images.emergentagent.com/jobs/20abb711-28bb-4d84-a96f-178a755fd768/images/bb289a4dfc08437bdffcafd67546f216417be11f1f06b39e93967b7ba8ef560d.png' },
  { id: 'k2', category: 'kids', label: 'Boy', url: 'https://static.prod-images.emergentagent.com/jobs/20abb711-28bb-4d84-a96f-178a755fd768/images/029b59b2e51790447660685a45c8a394cc77794140a7216d89438f271955343c.png' },
  { id: 'a1', category: 'animation', label: 'Anime Hero', url: 'https://static.prod-images.emergentagent.com/jobs/20abb711-28bb-4d84-a96f-178a755fd768/images/99afd4544d84b8316d40388950d31be1ba8d0c9759fd177d2546ce2493460d3d.png' },
  { id: 'a2', category: 'animation', label: 'Kawaii Cat', url: 'https://static.prod-images.emergentagent.com/jobs/20abb711-28bb-4d84-a96f-178a755fd768/images/eb5a38891cdde74dd13df1ee5e8644d8ad4c40c01aa45f010cd81e6764d305ea.png' },
  { id: 'c1', category: 'character', label: 'AI Robot', url: 'https://static.prod-images.emergentagent.com/jobs/20abb711-28bb-4d84-a96f-178a755fd768/images/76b493bea86d4e55e4f1e976e58fde2f745d7173acbb72e6989633f83a413775.png' },
  { id: 'c2', category: 'character', label: 'Superhero', url: 'https://static.prod-images.emergentagent.com/jobs/20abb711-28bb-4d84-a96f-178a755fd768/images/ef0c188b38bed832205014ea0b8ca68af546c40e4278797923c43ee7f09b60db.png' },
];

const INITIALS_COLORS = ['var(--app-primary)', 'var(--app-success)', 'var(--app-warning)', 'var(--app-error)', 'var(--app-primary)', 'var(--app-primary)', 'var(--app-primary)', 'var(--app-warning)'];

const PROMPT_SUGGESTIONS = [
  'Professional headshot, clean background, friendly smile',
  'Cartoon style, colorful, big eyes, cheerful',
  'Cyberpunk style, neon lights, futuristic visor',
  'Watercolor painting, soft colors, artistic portrait',
  'Pixel art style, retro gaming character',
  'Anime style, sparkle eyes, vibrant hair',
];

interface Props {
  visible: boolean;
  onClose: () => void;
  onSelectAvatar: (url: string) => void;
  currentImage: string | null;
  userName?: string;
}

export function AvatarGalleryModal({ visible, onClose, onSelectAvatar, currentImage, userName }: Props) {
  const { width } = useWindowDimensions();
  const { colors } = useTheme();

  // @autofix-moved: was module-level const STYLE_PRESETS
  const STYLE_PRESETS = [
    { id: 'corporate', label: 'Corporate', icon: 'briefcase', color: colors.primary, prompt: 'Professional corporate headshot, clean white background, business attire, confident friendly smile, studio lighting, high-end portrait photography' },
    { id: 'gaming', label: 'Gaming', icon: 'game-controller', color: colors.error, prompt: 'Epic gaming avatar, dramatic lighting, futuristic helmet with glowing HUD visor, neon accents, dark background with particle effects, high-tech sci-fi style' },
    { id: 'fantasy', label: 'Fantasy', icon: 'flame', color: colors.warningText, prompt: 'Mystical fantasy character portrait, enchanted forest background, ethereal glow, magical sparks, elven features, ornate golden crown, fantasy art style' },
    { id: 'minimalist', label: 'Minimal', icon: 'ellipse', color: colors.successText, prompt: 'Minimalist flat design avatar, geometric shapes, pastel color palette, clean vector art style, simple elegant portrait with solid color background' },
    { id: 'anime', label: 'Anime', icon: 'star', color: 'var(--app-primary)', prompt: 'Anime style character portrait, large expressive sparkle eyes, vibrant colorful hair, dynamic pose, soft cel-shading, clean linework, manga aesthetic' }, // @theme-ok residual semantic hex (reviewed)
    { id: 'cyberpunk', label: 'Cyberpunk', icon: 'flash', color: colors.accent, prompt: 'Cyberpunk portrait, neon-lit cityscape reflection in cybernetic eye implants, chrome jaw augmentation, rain-soaked, pink and blue neon glow, blade runner aesthetic' },
    { id: 'watercolor', label: 'Watercolor', icon: 'water', color: colors.accent, prompt: 'Beautiful watercolor painting portrait, soft flowing brushstrokes, gentle color bleeding, artistic splashes, warm earth tones, fine art gallery quality' },
    { id: 'pixel', label: 'Pixel Art', icon: 'apps', color: colors.warningText, prompt: 'Retro pixel art character portrait, 16-bit style, vibrant limited color palette, crisp pixel edges, nostalgic video game aesthetic, iconic character design' },
  ];
  const T = { bg: colors.bg, card: colors.card, border: colors.border, white: colors.text, sec: colors.textSec, muted: colors.textMuted, cyan: colors.primary, purple: colors.purple || colors.primary, red: colors.error, green: colors.success, amber: colors.warning };
  const isMobile = width < 600;
  const [selectedCategory, setSelectedCategory] = useState('all');
  const [selectedAvatar, setSelectedAvatar] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  // AI Generation state
  const [aiPrompt, setAiPrompt] = useState('');
  const [aiProvider, setAiProvider] = useState<'openai' | 'gemini'>('openai');
  const [aiGenerating, setAiGenerating] = useState(false);
  const [aiGeneratedImage, setAiGeneratedImage] = useState<string | null>(null);
  const [aiError, setAiError] = useState('');
  const [aiMode, setAiMode] = useState<'presets' | 'custom'>('presets');
  const [activePreset, setActivePreset] = useState<string | null>(null);

  // History state
  const [historyItems, setHistoryItems] = useState<any[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [selectedHistoryItem, setSelectedHistoryItem] = useState<string | null>(null);

  const isHistoryTab = selectedCategory === 'history';

  // Fetch history when History tab is selected
  useEffect(() => {
    if (isHistoryTab && visible) {
      setHistoryLoading(true);
      api.get('/auth/avatar-history')
        .then(res => setHistoryItems(res.data.items || []))
        .catch(() => setHistoryItems([]))
        .finally(() => setHistoryLoading(false));
    }
  }, [isHistoryTab, visible]);

  const handleDeleteHistoryItem = useCallback(async (historyId: string) => {
    try {
      await api.delete(`/auth/avatar-history/${historyId}`);
      setHistoryItems(prev => prev.filter(i => i.history_id !== historyId));
      if (selectedHistoryItem === historyId) setSelectedHistoryItem(null);
    } catch (error) { handleAppRecoverableError({ scope: 'src/components/profile/AvatarGalleryModal.tsx#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
  }, [selectedHistoryItem]);

  const handleUseHistoryItem = useCallback(async (item: any) => {
    setSaving(true);
    try {
      await api.post('/auth/set-avatar', { avatar_url: item.data_uri });
      onSelectAvatar(item.data_uri);
      onClose();
    } catch {
      onSelectAvatar(item.data_uri);
      onClose();
    }
    setSaving(false);
  }, [onSelectAvatar, onClose]);

  const filteredAvatars = selectedCategory === 'all' ? AVATARS : AVATARS.filter(a => a.category === selectedCategory);
  const cols = isMobile ? 3 : 4;
  const avatarSize = isMobile ? (width - 80) / cols : 90;

  const initials = (userName || 'U').split(' ').map(n => n[0]).join('').toUpperCase().slice(0, 2);

  const handleGenerateAI = useCallback(async (promptOverride?: string) => {
    const prompt = promptOverride || aiPrompt;
    if (!prompt.trim() || prompt.trim().length < 3) {
      setAiError('Please enter a description (at least 3 characters)');
      return;
    }
    setAiGenerating(true);
    setAiError('');
    setAiGeneratedImage(null);
    try {
      const res = await api.post('/auth/generate-avatar', {
        prompt: prompt.trim(),
        provider: aiProvider,
        save_as_profile: false,
      });
      setAiGeneratedImage(res.data.data_uri);
    } catch (e: any) {
      setAiError(e?.response?.data?.detail || 'Failed to generate avatar. Please try again.');
    }
    setAiGenerating(false);
  }, [aiPrompt, aiProvider]);

  const handlePresetClick = useCallback((preset: typeof STYLE_PRESETS[0]) => {
    setAiPrompt(preset.prompt);
    setActivePreset(preset.id);
    setAiError('');
    setAiGeneratedImage(null);
    // Auto-trigger generation
    setAiGenerating(true);
    api.post('/auth/generate-avatar', {
      prompt: preset.prompt,
      provider: aiProvider,
      save_as_profile: false,
    }).then(res => {
      setAiGeneratedImage(res.data.data_uri);
    }).catch((e: any) => {
      setAiError(e?.response?.data?.detail || 'Failed to generate avatar. Please try again.');
    }).finally(() => {
      setAiGenerating(false);
    });
  }, [aiProvider]);

  const handleSaveAIAvatar = useCallback(async () => {
    if (!aiGeneratedImage) return;
    setSaving(true);
    try {
      await api.post('/auth/set-avatar', { avatar_url: aiGeneratedImage });
      onSelectAvatar(aiGeneratedImage);
      onClose();
    } catch {
      onSelectAvatar(aiGeneratedImage);
      onClose();
    }
    setSaving(false);
  }, [aiGeneratedImage, onSelectAvatar, onClose]);

  const handleSave = useCallback(async () => {
    if (!selectedAvatar) return;
    setSaving(true);
    try {
      await api.post('/auth/set-avatar', { avatar_url: selectedAvatar });
      onSelectAvatar(selectedAvatar);
      onClose();
    } catch {
      onSelectAvatar(selectedAvatar);
      onClose();
    }
    setSaving(false);
  }, [selectedAvatar, onSelectAvatar, onClose]);

  const isAITab = selectedCategory === 'ai';

  // Preview image logic
  const previewImage = isAITab ? aiGeneratedImage : isHistoryTab && selectedHistoryItem ? historyItems.find(i => i.history_id === selectedHistoryItem)?.data_uri : selectedAvatar;

  return (
    <Modal visible={visible} transparent animationType="fade" onRequestClose={onClose}>
      <View style={{ flex: 1, backgroundColor: 'rgba(0,0,0,0.7)', justifyContent: 'center', alignItems: 'center', padding: isMobile ? 8 : 20 }} testID="avatar-gallery-modal">
        <View style={{ backgroundColor: T.card, borderRadius: 20, width: '100%', maxWidth: 560, maxHeight: '92%', borderWidth: 1, borderColor: T.border, overflow: 'hidden' }}>
          {/* Header */}
          <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', padding: 16, borderBottomWidth: 1, borderBottomColor: T.border }}>
            <Text style={{ color: T.white, fontSize: 16, fontWeight: '800' }}>
              {isAITab ? 'AI Avatar Generator' : 'Choose Avatar'}
            </Text>
            <TouchableOpacity onPress={onClose} style={{ width: 32, height: 32, borderRadius: 16, backgroundColor: T.border, alignItems: 'center', justifyContent: 'center' }} testID="avatar-gallery-close"  accessibilityLabel="close button">
              <Ionicons name="close" size={16} color={T.sec} />
            </TouchableOpacity>
          </View>

          {/* Current preview */}
          <View style={{ alignItems: 'center', padding: 16 }}>
            <View style={{ width: 80, height: 80, borderRadius: 40, borderWidth: 3, borderColor: isAITab ? T.purple : T.cyan, overflow: 'hidden', backgroundColor: T.bg }}>
              {previewImage ? (
                <Image source={{ uri: previewImage }} style={{ width: '100%', height: '100%' }} accessibilityLabel="initials" />
              ) : currentImage ? (
                <Image source={{ uri: currentImage }} style={{ width: '100%', height: '100%' }} accessibilityLabel="initials" />
              ) : (
                <View style={{ flex: 1, backgroundColor: INITIALS_COLORS[0], alignItems: 'center', justifyContent: 'center' }}>
                  <Text style={{ color: T.white, fontSize: 28, fontWeight: '800' }}>{initials}</Text>
                </View>
              )}
            </View>
            {previewImage && (
              <Text style={{ color: isAITab ? T.purple : T.cyan, fontSize: 11, fontWeight: '600', marginTop: 6 }}>Preview</Text>
            )}
          </View>

          {/* Category tabs */}
          <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ maxHeight: 42, borderBottomWidth: 1, borderBottomColor: T.border }} contentContainerStyle={{ paddingHorizontal: 8, gap: 4 }}>
            {AVATAR_CATEGORIES.map(cat => {
              const isActive = selectedCategory === cat.key;
              const isAI = cat.key === 'ai';
              const activeColor = isAI ? T.purple : T.cyan;
              return (
                <TouchableOpacity accessibilityLabel="Set selected category in avatar gallery modal button"
                  key={cat.key}
                  onPress={() => setSelectedCategory(cat.key)}
                  testID={`avatar-cat-${cat.key}`}
                  style={{
                    flexDirection: 'row', alignItems: 'center', gap: 4,
                    paddingHorizontal: 8, paddingVertical: 8, borderRadius: 20,
                    backgroundColor: isActive ? (globalThis as any).__alphaColor(activeColor, '18') : 'transparent',
                    borderWidth: 1,
                    borderColor: isActive ? (globalThis as any).__alphaColor(activeColor, '40') : 'transparent',
                  }}
                >
                  <Ionicons name={cat.icon as any} size={12} color={isActive ? activeColor : T.muted} />
                  <Text style={{ fontSize: 10, fontWeight: '700', color: isActive ? activeColor : T.muted }}>{cat.label}</Text>
                </TouchableOpacity>
              );
            })}
          </ScrollView>

          {/* AI Generate Panel */}
          {isAITab ? (
            <ScrollView style={{ maxHeight: 340, padding: 16 }} contentContainerStyle={{ gap: 12 }}>
              {/* Provider selector */}
              <View style={{ flexDirection: 'row', gap: 8 }}>
                <TouchableOpacity accessibilityLabel="Ai provider openai button"
                  onPress={() => setAiProvider('openai')}
                  style={{
                    flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6,
                    paddingVertical: 8, borderRadius: 10,
                    borderWidth: 1.5,
                    borderColor: aiProvider === 'openai' ? T.cyan : T.border,
                    backgroundColor: aiProvider === 'openai' ? (globalThis as any).__alphaColor(T.cyan, '10') : 'transparent',
                  }}
                  testID="ai-provider-openai"
                >
                  <Ionicons name="cube-outline" size={13} color={aiProvider === 'openai' ? T.cyan : T.muted} />
                  <Text style={{ fontSize: 11, fontWeight: '700', color: aiProvider === 'openai' ? T.cyan : T.muted }}>GPT Image</Text>
                </TouchableOpacity>
                <TouchableOpacity accessibilityLabel="Ai provider gemini button"
                  onPress={() => setAiProvider('gemini')}
                  style={{
                    flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6,
                    paddingVertical: 8, borderRadius: 10,
                    borderWidth: 1.5,
                    borderColor: aiProvider === 'gemini' ? T.purple : T.border,
                    backgroundColor: aiProvider === 'gemini' ? (globalThis as any).__alphaColor(T.purple, '10') : 'transparent',
                  }}
                  testID="ai-provider-gemini"
                >
                  <Ionicons name="diamond-outline" size={13} color={aiProvider === 'gemini' ? T.purple : T.muted} />
                  <Text style={{ fontSize: 11, fontWeight: '700', color: aiProvider === 'gemini' ? T.purple : T.muted }}>Gemini</Text>
                </TouchableOpacity>
              </View>

              {/* Mode toggle: Presets / Custom */}
              <View style={{ flexDirection: 'row', backgroundColor: T.bg, borderRadius: 10, padding: 3 }}>
                <TouchableOpacity accessibilityLabel="Ai mode presets button"
                  onPress={() => setAiMode('presets')}
                  style={{
                    flex: 1, paddingVertical: 7, borderRadius: 8, alignItems: 'center',
                    backgroundColor: aiMode === 'presets' ? T.card : 'transparent',
                    borderWidth: aiMode === 'presets' ? 1 : 0,
                    borderColor: T.border,
                  }}
                  testID="ai-mode-presets"
                >
                  <Text style={{ fontSize: 11, fontWeight: '700', color: aiMode === 'presets' ? T.white : T.muted }}>Style Presets</Text>
                </TouchableOpacity>
                <TouchableOpacity accessibilityLabel="Ai mode custom button"
                  onPress={() => setAiMode('custom')}
                  style={{
                    flex: 1, paddingVertical: 7, borderRadius: 8, alignItems: 'center',
                    backgroundColor: aiMode === 'custom' ? T.card : 'transparent',
                    borderWidth: aiMode === 'custom' ? 1 : 0,
                    borderColor: T.border,
                  }}
                  testID="ai-mode-custom"
                >
                  <Text style={{ fontSize: 11, fontWeight: '700', color: aiMode === 'custom' ? T.white : T.muted }}>Custom Prompt</Text>
                </TouchableOpacity>
              </View>

              {/* Generating state overlay */}
              {aiGenerating && (
                <View style={{ alignItems: 'center', padding: 20, gap: 10, borderRadius: 14, borderWidth: 1, borderColor: (globalThis as any).__alphaColor((aiProvider === 'openai' ? T.cyan : T.purple), '30'), backgroundColor: T.bg }}>
                  <ActivityIndicator color={aiProvider === 'openai' ? T.cyan : T.purple} size="large" />
                  <Text style={{ color: T.white, fontSize: 13, fontWeight: '700' }}>Creating your avatar...</Text>
                  <Text style={{ color: T.muted, fontSize: 11 }}>This may take up to 60 seconds</Text>
                </View>
              )}

              {/* Error */}
              {aiError && !aiGenerating ? (
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, padding: 10, borderRadius: 10, backgroundColor: (globalThis as any).__alphaColor(T.red, '12'), borderWidth: 1, borderColor: (globalThis as any).__alphaColor(T.red, '25') }} testID="ai-error">
                  <Ionicons name="alert-circle" size={14} color={T.red} />
                  <Text style={{ color: T.red, fontSize: 11, flex: 1 }}>{aiError}</Text>
                </View>
              ) : null}

              {/* Generated image preview */}
              {aiGeneratedImage && !aiGenerating && (
                <View style={{ alignItems: 'center', gap: 10, padding: 14, borderRadius: 14, borderWidth: 1, borderColor: (globalThis as any).__alphaColor((aiProvider === 'openai' ? T.cyan : T.purple), '30'), backgroundColor: (globalThis as any).__alphaColor((aiProvider === 'openai' ? T.cyan : T.purple), '06') }} testID="ai-generated-preview">
                  <View style={{ width: 120, height: 120, borderRadius: 60, overflow: 'hidden', borderWidth: 3, borderColor: aiProvider === 'openai' ? T.cyan : T.purple }}>
                    <Image source={{ uri: aiGeneratedImage }} style={{ width: '100%', height: '100%' }} resizeMode="cover" />
                  </View>
                  <TouchableOpacity accessibilityLabel="Regenerate"
                    onPress={() => handleGenerateAI()}
                    style={{ flexDirection: 'row', alignItems: 'center', gap: 4, paddingHorizontal: 12, paddingVertical: 7, borderRadius: 10, borderWidth: 1, borderColor: T.border }}
                    testID="ai-regenerate-btn"
                  >
                    <Ionicons name="refresh" size={13} color={T.sec} />
                    <Text style={{ color: T.sec, fontSize: 11, fontWeight: '600' }}>Regenerate</Text>
                  </TouchableOpacity>
                </View>
              )}

              {/* PRESETS MODE */}
              {aiMode === 'presets' && !aiGenerating && !aiGeneratedImage && (
                <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
                  {STYLE_PRESETS.map(preset => (
                    <TouchableOpacity accessibilityLabel="Preset click in avatar gallery modal button"
                      key={preset.id}
                      onPress={() => handlePresetClick(preset)}
                      style={{
                        width: isMobile ? '47%' : '23%',
                        padding: 12, borderRadius: 12, alignItems: 'center', gap: 6,
                        borderWidth: 1.5,
                        borderColor: activePreset === preset.id ? (globalThis as any).__alphaColor(preset.color, '60') : T.border,
                        backgroundColor: activePreset === preset.id ? (globalThis as any).__alphaColor(preset.color, '12') : T.bg,
                      }}
                      testID={`ai-preset-${preset.id}`}
                    >
                      <View style={{ width: 36, height: 36, borderRadius: 18, backgroundColor: (globalThis as any).__alphaColor(preset.color, '20'), alignItems: 'center', justifyContent: 'center' }}>
                        <Ionicons name={preset.icon as any} size={18} color={preset.color} />
                      </View>
                      <Text style={{ color: T.white, fontSize: 10, fontWeight: '700', textAlign: 'center' }}>{preset.label}</Text>
                    </TouchableOpacity>
                  ))}
                </View>
              )}

              {/* CUSTOM MODE */}
              {aiMode === 'custom' && !aiGenerating && !aiGeneratedImage && (
                <>
                  <View>
                    <Text style={{ color: T.sec, fontSize: 10, fontWeight: '600', marginBottom: 5, letterSpacing: 0.5 }}>DESCRIBE YOUR AVATAR</Text>
                    <View style={{
                      borderWidth: 1, borderColor: T.border, borderRadius: 12,
                      backgroundColor: T.bg, paddingHorizontal: 14, paddingVertical: Platform.OS === 'web' ? 0 : 10,
                    }}>
                      <TextInput
                        value={aiPrompt}
                        onChangeText={setAiPrompt}
                        placeholder="e.g. professional woman with glasses, cartoon style"
                        placeholderTextColor={T.muted}
                        style={{
                          color: T.white, fontSize: 13, minHeight: 50,
                          ...(Platform.OS === 'web' ? { outlineStyle: 'none', padding: 10 } as any : {}),
                        }}
                        multiline
                        maxLength={500}
                        testID="ai-prompt-input"
                      />
                    </View>
                    <Text style={{ color: T.muted, fontSize: 9, marginTop: 3, textAlign: 'right' }}>{aiPrompt.length}/500</Text>
                  </View>

                  {/* Suggestion chips */}
                  <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 5 }}>
                    {PROMPT_SUGGESTIONS.map((s, i) => (
                      <TouchableOpacity accessibilityLabel="Set ai prompt in avatar gallery modal button"
                        key={i}
                        onPress={() => setAiPrompt(s)}
                        style={{
                          paddingHorizontal: 9, paddingVertical: 5, borderRadius: 14,
                          borderWidth: 1, borderColor: T.border,
                          backgroundColor: aiPrompt === s ? (globalThis as any).__alphaColor((aiProvider === 'openai' ? T.cyan : T.purple), '15') : 'transparent',
                        }}
                        testID={`ai-suggestion-${i}`}
                      >
                        <Text style={{ color: T.sec, fontSize: 9, fontWeight: '600' }} numberOfLines={1}>{s}</Text>
                      </TouchableOpacity>
                    ))}
                  </ScrollView>

                  {/* Generate button */}
                  <TouchableOpacity accessibilityLabel="Ai generate button"
                    onPress={() => handleGenerateAI()}
                    disabled={!aiPrompt.trim()}
                    style={{
                      flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8,
                      paddingVertical: 12, borderRadius: 12,
                      backgroundColor: !aiPrompt.trim() ? T.border : aiProvider === 'openai' ? T.cyan : T.purple,
                      opacity: !aiPrompt.trim() ? 0.5 : 1,
                    }}
                    testID="ai-generate-btn"
                  >
                    <Ionicons name="sparkles" size={15} color="var(--app-primary-text)" />
                    <Text style={{ color: T.white, fontSize: 12, fontWeight: '700' }}>Generate Avatar</Text>
                  </TouchableOpacity>
                </>
              )}
            </ScrollView>
          ) : isHistoryTab ? (
            /* History grid */
            <ScrollView style={{ maxHeight: 340, padding: 16 }} contentContainerStyle={{ gap: 12 }}>
              {historyLoading ? (
                <View style={{ alignItems: 'center', padding: 30 }}>
                  <ActivityIndicator color={T.cyan} size="large" />
                  <Text style={{ color: T.muted, fontSize: 12, marginTop: 10 }}>Loading history...</Text>
                </View>
              ) : historyItems.length === 0 ? (
                <View style={{ alignItems: 'center', padding: 30, gap: 10 }}>
                  <Ionicons name="time-outline" size={40} color={T.border} />
                  <Text style={{ color: T.muted, fontSize: 13, fontWeight: '600' }}>No generated avatars yet</Text>
                  <Text style={{ color: T.muted, fontSize: 11, textAlign: 'center' }}>Generate an AI avatar and it will appear here</Text>
                </View>
              ) : (
                <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10, justifyContent: 'center' }}>
                  {historyItems.map(item => {
                    const isSelected = selectedHistoryItem === item.history_id;
                    const date = new Date(item.created_at);
                    const timeStr = `${date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}`;
                    return (
                      <TouchableOpacity accessibilityLabel="Set selected history item in avatar gallery modal button"
                        key={item.history_id}
                        onPress={() => setSelectedHistoryItem(isSelected ? null : item.history_id)}
                        style={{
                          width: isMobile ? (width - 80) / 3 : 110,
                          alignItems: 'center', gap: 4, padding: 6, borderRadius: 12,
                          borderWidth: 2,
                          borderColor: isSelected ? T.amber : 'transparent',
                          backgroundColor: isSelected ? (globalThis as any).__alphaColor(T.amber, '08') : 'transparent',
                        }}
                        testID={`history-item-${item.history_id}`}
                      >
                        <View style={{ width: isMobile ? 65 : 75, height: isMobile ? 65 : 75, borderRadius: isMobile ? 32 : 37, overflow: 'hidden', borderWidth: 2, borderColor: isSelected ? T.amber : T.border }}>
                          <Image source={{ uri: item.data_uri }} style={{ width: '100%', height: '100%' }} resizeMode="cover" accessibilityLabel="timeStr" />
                        </View>
                        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 3 }}>
                          <Ionicons name={item.provider === 'gemini' ? 'diamond' : 'cube'} size={8} color={item.provider === 'gemini' ? T.purple : T.cyan} />
                          <Text style={{ color: T.muted, fontSize: 8, fontWeight: '600' }}>{timeStr}</Text>
                        </View>
                        <Text style={{ color: T.sec, fontSize: 8, textAlign: 'center' }} numberOfLines={1}>{item.prompt?.slice(0, 25)}...</Text>
                        {isSelected && (
                          <TouchableOpacity accessibilityLabel="trash button"
                            onPress={() => handleDeleteHistoryItem(item.history_id)}
                            style={{ position: 'absolute', top: 2, right: 2, width: 20, height: 20, borderRadius: 10, backgroundColor: (globalThis as any).__alphaColor(T.red, '20'), alignItems: 'center', justifyContent: 'center' }}
                            testID={`history-delete-${item.history_id}`}
                          >
                            <Ionicons name="trash" size={10} color={T.red} />
                          </TouchableOpacity>
                        )}
                      </TouchableOpacity>
                    );
                  })}
                </View>
              )}
            </ScrollView>
          ) : (
            /* Regular avatar grid */
            <ScrollView style={{ maxHeight: 280, padding: 12 }} contentContainerStyle={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10, justifyContent: 'center' }}>
              {/* Initials avatars */}
              {selectedCategory === 'all' && INITIALS_COLORS.map((color, i) => (
                <TouchableOpacity accessibilityLabel="initials"
                  key={`ini_${i}`}
                  onPress={() => setSelectedAvatar(`initials:${color}`)}
                  style={{ width: avatarSize, height: avatarSize, borderRadius: avatarSize / 2, backgroundColor: color, alignItems: 'center', justifyContent: 'center', borderWidth: 3, borderColor: selectedAvatar === `initials:${color}` ? T.white : 'transparent', opacity: selectedAvatar === `initials:${color}` ? 1 : 0.8 }}
                  testID={`avatar-initials-${i}`}
                >
                  <Text style={{ color: T.white, fontSize: avatarSize * 0.35, fontWeight: '800' }}>{initials}</Text>
                </TouchableOpacity>
              ))}

              {/* Image avatars */}
              {filteredAvatars.map(avatar => (
                <TouchableOpacity accessibilityLabel="Set selected avatar in avatar gallery modal button"
                  key={avatar.id}
                  onPress={() => setSelectedAvatar(avatar.url)}
                  style={{ width: avatarSize, height: avatarSize, borderRadius: avatarSize / 2, overflow: 'hidden', borderWidth: 3, borderColor: selectedAvatar === avatar.url ? T.cyan : 'transparent', opacity: selectedAvatar === avatar.url ? 1 : 0.75 }}
                  testID={`avatar-${avatar.id}`}
                >
                  <Image source={{ uri: avatar.url }} style={{ width: '100%', height: '100%' }} resizeMode="cover" accessibilityLabel="checkmark button" />
                  {selectedAvatar === avatar.url && (
                    <View style={{ position: 'absolute', bottom: 2, right: 2, width: 20, height: 20, borderRadius: 10, backgroundColor: T.cyan, alignItems: 'center', justifyContent: 'center' }}>
                      <Ionicons name="checkmark" size={12} color="var(--app-primary-text)" />
                    </View>
                  )}
                </TouchableOpacity>
              ))}
            </ScrollView>
          )}

          {/* Action buttons */}
          <View style={{ flexDirection: 'row', padding: 16, gap: 10, borderTopWidth: 1, borderTopColor: T.border }}>
            <TouchableOpacity onPress={onClose} style={{ flex: 1, paddingVertical: 12, borderRadius: 12, borderWidth: 1, borderColor: T.border, alignItems: 'center' }} testID="avatar-gallery-cancel" >
              <Text style={{ color: T.sec, fontSize: 13, fontWeight: '700' }}>Cancel</Text>
            </TouchableOpacity>
            {isAITab ? (
              <TouchableOpacity accessibilityLabel="Ai save avatar button"
                onPress={handleSaveAIAvatar}
                disabled={!aiGeneratedImage || saving}
                style={{ flex: 2, paddingVertical: 12, borderRadius: 12, backgroundColor: aiGeneratedImage ? T.purple : T.border, alignItems: 'center', opacity: aiGeneratedImage ? 1 : 0.4 }}
                testID="ai-save-avatar-btn"
              >
                {saving ? (
                  <ActivityIndicator color="var(--app-primary-text)" size="small" />
                ) : (
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                    <Ionicons name="sparkles" size={16} color="var(--app-primary-text)" />
                    <Text style={{ color: T.white, fontSize: 13, fontWeight: '800' }}>Use AI Avatar</Text>
                  </View>
                )}
              </TouchableOpacity>
            ) : isHistoryTab ? (
              <TouchableOpacity accessibilityLabel="History use avatar button"
                onPress={() => {
                  const item = historyItems.find(i => i.history_id === selectedHistoryItem);
                  if (item) handleUseHistoryItem(item);
                }}
                disabled={!selectedHistoryItem || saving}
                style={{ flex: 2, paddingVertical: 12, borderRadius: 12, backgroundColor: selectedHistoryItem ? T.amber : T.border, alignItems: 'center', opacity: selectedHistoryItem ? 1 : 0.4 }}
                testID="history-use-avatar-btn"
              >
                {saving ? (
                  <ActivityIndicator color="var(--app-primary-text)" size="small" />
                ) : (
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                    <Ionicons name="time" size={16} color="var(--app-primary-text)" />
                    <Text style={{ color: T.white, fontSize: 13, fontWeight: '800' }}>Use This Avatar</Text>
                  </View>
                )}
              </TouchableOpacity>
            ) : (
              <TouchableOpacity accessibilityLabel="Avatar gallery save button"
                onPress={handleSave}
                disabled={!selectedAvatar || saving}
                style={{ flex: 2, paddingVertical: 12, borderRadius: 12, backgroundColor: selectedAvatar ? T.cyan : T.border, alignItems: 'center', opacity: selectedAvatar ? 1 : 0.4 }}
                testID="avatar-gallery-save"
              >
                {saving ? (
                  <ActivityIndicator color="var(--app-primary-text)" size="small" />
                ) : (
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                    <Ionicons name="checkmark-circle" size={16} color="var(--app-primary-text)" />
                    <Text style={{ color: T.white, fontSize: 13, fontWeight: '800' }}>Set as Avatar</Text>
                  </View>
                )}
              </TouchableOpacity>
            )}
          </View>
        </View>
      </View>
    </Modal>
  );
}

export { AVATARS, INITIALS_COLORS };

/* i18n-probe t('i18n.auto.probe') */
