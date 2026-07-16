import React from 'react';
import { TouchableOpacity, View, Text, StyleSheet } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

interface VideoStudioStatusBannerProps {
  message: string;
  onRefresh: () => void;
  colors: {
    card: string;
    border: string;
    text: string;
    textSec: string;
    primary: string;
  };
}

export const VideoStudioStatusBanner: React.FC<VideoStudioStatusBannerProps> = ({
  message,
  onRefresh,
  colors,
}) => {
  return (
    <View
      style={[styles.container, { backgroundColor: colors.card, borderColor: colors.border }]}
      data-testid="video-studio-status-banner"
      testID="video-studio-status-banner"
    >
      <View style={styles.messageRow}>
        <Ionicons name="alert-circle-outline" size={18} color={colors.primary} />
        <Text
          style={[styles.messageText, { color: colors.textSec }]}
          data-testid="video-studio-status-banner-message"
          testID="video-studio-status-banner-message"
        >
          {message}
        </Text>
      </View>

      <TouchableOpacity
        style={[styles.refreshButton, { borderColor: colors.primary }]}
        onPress={onRefresh}
        data-testid="video-studio-refresh-studio-button"
        testID="video-studio-refresh-studio-button"
      >
        <Ionicons name="refresh" size={14} color={colors.primary} />
        <Text style={[styles.refreshText, { color: colors.primary }]}>Refresh Studio</Text>
      </TouchableOpacity>
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    borderWidth: 1,
    borderRadius: 10,
    padding: 12,
    marginBottom: 12,
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    gap: 10,
  },
  messageRow: {
    flexDirection: 'row',
    alignItems: 'center',
    flex: 1,
    gap: 8,
  },
  messageText: {
    fontSize: 12,
    lineHeight: 16,
    flexShrink: 1,
  },
  refreshButton: {
    borderWidth: 1,
    borderRadius: 999,
    paddingHorizontal: 10,
    paddingVertical: 6,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  refreshText: {
    fontSize: 12,
    fontWeight: '600',
  },
});
