import React, { useState } from 'react';
import { View, TouchableOpacity, Text, Share, Platform, Alert, ActivityIndicator } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import * as Clipboard from 'expo-clipboard';
import api from '../services/api';
import { useAuth } from '../context/AuthContext';
import { useTheme } from '../context/ThemeContext';
import AIResponseFeedback from './AIResponseFeedback';
import { handleAppRecoverableError } from '../utils/appRecoverableError';

interface FeatureToolbarProps {
  content: string;
  featureKey: string;
  title?: string;
  onClear?: () => void;
  showShare?: boolean;
}

export default function FeatureToolbar({ content, featureKey, title, onClear, showShare = true }: FeatureToolbarProps) {
  const { colors } = useTheme();
  const { user } = useAuth();
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  const handleCopy = async () => {
    if (Platform.OS === 'web' && navigator.clipboard) {
        await navigator.clipboard.writeText(content);
    } else {
        await Clipboard.setStringAsync(content);
    }
    Alert.alert('Copied', 'Content copied to clipboard');
  };

  const handleSave = async () => {
    if (!user) {
        Alert.alert('Login Required', 'Please login to save content');
        return;
    }
    if (saved) {
        return;
    }

    setSaving(true);
    try {
      // eslint-disable-next-line @typescript-eslint/no-unused-vars
      const _response = await api.post('/content/save-generated', {
        user_id: user.user_id,
        content,
        feature_key: featureKey,
        title: title || 'Generated Content'
      });
      setSaved(true);
      Alert.alert('Saved', 'Content saved to your library');
    } catch {
      Alert.alert('Error', 'Failed to save content');
    } finally {
      setSaving(false);
    }
  };

  const handleShare = async () => {
    try {
        await Share.share({
            message: content,
            title: title || 'Shared Content'
        });
    } catch (error) { handleAppRecoverableError({ scope: 'src/components/FeatureToolbar.tsx#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
  };

  if (!content) return null;

  return (
    <View>
      <View style={{ flexDirection: 'row', gap: 10, marginTop: 12 }} data-testid={`feature-toolbar-${featureKey}`} testID={`feature-toolbar-${featureKey}`}>
        <TouchableOpacity 
          style={{ flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', paddingVertical: 10, paddingHorizontal: 4, backgroundColor: colors.card, borderRadius: 12, borderWidth: 1, borderColor: colors.border, gap: 6 }}
          onPress={handleCopy}
          data-testid={`feature-toolbar-copy-${featureKey}`} testID={`feature-toolbar-copy-${featureKey}`}
          accessibilityRole="button"
        >
          <Ionicons name="copy-outline" size={16} color={colors.text} />
          <Text style={{ color: colors.text, fontWeight: '600', fontSize: 12 }}>Copy</Text>
        </TouchableOpacity>

        <TouchableOpacity 
          style={{ flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', paddingVertical: 10, paddingHorizontal: 4, backgroundColor: saved ? colors.primarySoft : colors.card, borderRadius: 12, borderWidth: 1, borderColor: saved ? colors.primary : colors.border, gap: 6 }}
          onPress={handleSave}
          disabled={saving || saved}
          data-testid={`feature-toolbar-save-${featureKey}`} testID={`feature-toolbar-save-${featureKey}`}
          accessibilityRole="button"
        >
          {saving ? <ActivityIndicator size="small" color={'var(--app-primary)'} /> : (
            <>
                <Ionicons name={saved ? "bookmark" : "bookmark-outline"} size={16} color={saved ? colors.primary : colors.text} />
                <Text style={{ color: saved ? colors.primary : colors.text, fontWeight: '600', fontSize: 12 }}>{saved ? 'Saved' : 'Save'}</Text>
            </>
          )}
        </TouchableOpacity>

        {showShare && (
          <TouchableOpacity 
              style={{ flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', paddingVertical: 10, paddingHorizontal: 4, backgroundColor: colors.card, borderRadius: 12, borderWidth: 1, borderColor: colors.border, gap: 6 }}
              onPress={handleShare}
              data-testid={`feature-toolbar-share-${featureKey}`} testID={`feature-toolbar-share-${featureKey}`}
              accessibilityRole="button"
          >
              <Ionicons name="share-social-outline" size={16} color={colors.text} />
              <Text style={{ color: colors.text, fontWeight: '600', fontSize: 12 }}>Share</Text>
          </TouchableOpacity>
        )}
        
        {onClear && (
           <TouchableOpacity 
              style={{ width: 44, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.card, borderRadius: 12, borderWidth: 1, borderColor: colors.border }}
              onPress={onClear}
              data-testid={`feature-toolbar-clear-${featureKey}`} testID={`feature-toolbar-clear-${featureKey}`}
              accessibilityRole="button"
           >
              <Ionicons name="trash-outline" size={18} color={'var(--app-text-muted)'} />
           </TouchableOpacity>
        )}
      </View>
      <AIResponseFeedback featureKey={featureKey} responseText={content} testId={`feature-toolbar-feedback-${featureKey}`} />
    </View>
  );
}

/* i18n-probe t('i18n.auto.probe') */
