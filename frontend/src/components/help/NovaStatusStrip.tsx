import React from 'react';
import { View, Text, TouchableOpacity } from 'react-native';
import type { ChatMessage, ThemeColors } from './helpTypes';
import { useTheme } from '../../context/ThemeContext';
import { useLanguage } from '../../i18n/LanguageContext';

interface NovaStatusStripProps {
  C: ThemeColors;
  tx: (key: string, fallback: string) => string;
  health: 'checking' | 'healthy' | 'degraded';
  hasLiveAssistantReply: boolean;
  latestAssistantMessage: ChatMessage | null;
  pinnedCount?: number;
  conversationPinned?: boolean;
  isPhone: boolean;
  isEmbedded: boolean;
  isFloating: boolean;
  retryPrompt?: string | null;
  isLoading: boolean;
  onRetryTimeout?: () => void;
}

export const NovaStatusStrip = ({
  C, tx, health, hasLiveAssistantReply, latestAssistantMessage, pinnedCount, conversationPinned,
  isPhone, isEmbedded, isFloating, retryPrompt, isLoading, onRetryTimeout,
}: NovaStatusStripProps) => {
  const { t } = useLanguage();
  const { colors } = useTheme();
  const showInlineStatusDetail = isEmbedded || isFloating;
  const statusText = health === 'degraded'
    ? tx('help.chat.novaNeedsAttentionShort', 'Nova Needs Attention')
    : hasLiveAssistantReply
      ? tx('help.chat.novaHealthy', 'Nova Healthy')
      : tx('help.chat.novaReady', 'Nova Ready');
  const statusDetail = hasLiveAssistantReply
    ? 'Live replies are responding in this conversation.'
    : 'Live GPS sync is ready. Send a message to start chatting.';
  const condensedStatusDetail = health === 'degraded'
    ? tx('help.chat.novaNeedsAttention', 'Nova needs attention right now.')
    : hasLiveAssistantReply
      ? tx('help.chat.novaLiveReplies', 'Live replies are responding in this conversation.')
      : tx('help.chat.novaConversationPrompt', 'Send a message to start chatting.');

  return (
    <>
      {latestAssistantMessage?.gps_context && !isPhone && !isEmbedded && !isFloating ? (
        <View
          style={{
            marginBottom: 8,
            borderRadius: 10,
            borderWidth: 1,
            borderColor: latestAssistantMessage.gps_context.gps_live ? `${colors.successText}55` : `${colors.warningText}55`,
            backgroundColor: latestAssistantMessage.gps_context.gps_live ? `${colors.successText}14` : `${colors.warningText}14`,
            paddingHorizontal: 10,
            paddingVertical: 7,
          }}
          data-testid="chat-gps-live-indicator"
          testID="chat-gps-live-indicator"
        >
          <Text style={{ color: C.textSec, fontSize: 10, fontWeight: '800' }} data-testid="chat-gps-live-indicator-text" testID="chat-gps-live-indicator-text">
            {latestAssistantMessage.gps_context.gps_live ? tx('help.chat.gpsLive', 'GPS LIVE') : tx('help.chat.gpsDegraded', 'GPS DEGRADED')}{t("adopt.v")}{latestAssistantMessage.gps_context.gps_version || 1} · {tx('help.chat.gpsSource', 'source')} {latestAssistantMessage.gps_context.gps_source || 'live'} · {tx('help.chat.gpsFreshness', 'freshness')} {latestAssistantMessage.gps_context.gps_freshness_sec ?? '—'}s
          </Text>
        </View>
      ) : null}

      <View
        style={{ marginBottom: isEmbedded || isFloating ? 6 : 8, flexDirection: 'row', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}
        data-testid="chat-nova-status-indicator"
        testID="chat-nova-status-indicator"
      >
        <View
          style={{
            width: 8,
            height: 8,
            borderRadius: 4,
            backgroundColor: health === 'degraded'
              ? colors.error
              : hasLiveAssistantReply
                ? colors.successText
                : colors.warningText,
          }}
        />
        <Text style={{ color: C.textSec, fontSize: 11, fontWeight: '700' }} data-testid="chat-nova-status-text" testID="chat-nova-status-text">
          {statusText}
        </Text>
        {showInlineStatusDetail ? (
          <Text style={{ color: C.textMuted, fontSize: 10, lineHeight: 14, flexShrink: 1 }} data-testid="chat-nova-status-inline-detail" testID="chat-nova-status-inline-detail">
            · {condensedStatusDetail}
          </Text>
        ) : null}
      </View>
      {!isEmbedded && !isFloating && typeof pinnedCount === 'number' ? (
        <Text style={{ color: C.textMuted, fontSize: 10, marginBottom: 8, lineHeight: 14 }} data-testid="chat-nova-curation-detail" testID="chat-nova-curation-detail">
          {(conversationPinned ? 'Conversation pinned' : 'Conversation not pinned')}{t("adopt.total.pins")}{pinnedCount}
        </Text>
      ) : null}
      {!showInlineStatusDetail ? (
        <Text style={{ color: C.textMuted, fontSize: 10, marginBottom: 8, lineHeight: 14 }} data-testid="chat-nova-status-detail" testID="chat-nova-status-detail">
          {statusDetail}
        </Text>
      ) : null}

      {retryPrompt && !isLoading ? (
        <View
          style={{
            marginBottom: 8,
            paddingHorizontal: 10,
            paddingVertical: 8,
            borderRadius: 10,
            borderWidth: 1,
            borderColor: colors.warningText,
            backgroundColor: `${colors.warningText}14`,
            flexDirection: 'row',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: 8,
          }}
          data-testid="chat-timeout-retry-banner"
          testID="chat-timeout-retry-banner"
        >
          <Text style={{ flex: 1, fontSize: 11, color: C.textSec, fontWeight: '700' }} numberOfLines={2}>
            {tx('help.chat.retryHint', 'Nova timed out on your last request. You can retry safely.')}
          </Text>
          <TouchableOpacity
            onPress={() => onRetryTimeout?.()}
            style={{ paddingHorizontal: 10, paddingVertical: 6, borderRadius: 8, backgroundColor: C.primary }}
            data-testid="chat-timeout-retry-btn"
            testID="chat-timeout-retry-btn"
          >
            <Text style={{ fontSize: 11, fontWeight: '800', color: colors.primaryText }}>
              {tx('help.chat.retryAction', 'Retry')}
            </Text>
          </TouchableOpacity>
        </View>
      ) : null}
    </>
  );
};
