import React from 'react';
import { View, Text, TextInput, TouchableOpacity, ActivityIndicator, Platform, StyleSheet } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import type { ChatMessage, ThemeColors } from './helpTypes';
import { useTheme } from '../../context/ThemeContext';
import { NovaStatusStrip } from './NovaStatusStrip';

interface NovaComposerProps {
  C: ThemeColors;
  t: (key: string) => string;
  tx: (key: string, fallback: string) => string;
  inputText: string;
  setInputText: (v: string) => void;
  isLoading: boolean;
  isRecording: boolean;
  recordingTime: number;
  attachmentPreview: { name: string; type: string; uri: string } | null;
  setAttachmentPreview: (v: any) => void;
  sendMessage: (msg: string) => void;
  retryPrompt?: string | null;
  onRetryTimeout?: () => void;
  handleAttachment: () => void;
  onFileSelected: (e: any) => void;
  startRecording: () => void;
  stopRecording: () => void;
  fileInputRef: React.RefObject<any>;
  inputRef?: React.RefObject<any>;
  favoriteSnippets: { message_id: string; content: string }[];
  onUseFavoriteSnippet?: (content: string) => void;
  health: 'checking' | 'healthy' | 'degraded';
  hasLiveAssistantReply: boolean;
  latestAssistantMessage: ChatMessage | null;
  pinnedCount?: number;
  conversationPinned?: boolean;
  isPhone: boolean;
  isEmbedded: boolean;
  isFloating: boolean;
}

export const NovaComposer = (props: NovaComposerProps) => {
  const { colors } = useTheme();
  const {
    C, t, tx, inputText, setInputText, isLoading, isRecording, recordingTime,
    attachmentPreview, setAttachmentPreview, sendMessage, retryPrompt, onRetryTimeout,
    handleAttachment, onFileSelected, startRecording, stopRecording, fileInputRef, inputRef,
    favoriteSnippets, onUseFavoriteSnippet, health, hasLiveAssistantReply, latestAssistantMessage,
    pinnedCount, conversationPinned, isPhone, isEmbedded, isFloating,
  } = props;

  const s = StyleSheet.create({
    inputBar: { padding: 12, borderTopWidth: 1 },
    inputRow: { flexDirection: 'row', alignItems: 'flex-end', borderRadius: 14, paddingLeft: 14, paddingRight: 4, paddingVertical: 4, borderWidth: 1 },
    chatInput: { flex: 1, minWidth: 0, fontSize: 14, maxHeight: 90, paddingVertical: 8 },
    sendBtn: { width: 38, height: 38, borderRadius: 19, alignItems: 'center', justifyContent: 'center', borderWidth: 1 },
  });

  return (
    <View style={[s.inputBar, { borderTopColor: C.border, backgroundColor: C.card, padding: isFloating ? 10 : 12 }]}>
      {favoriteSnippets.length > 0 && onUseFavoriteSnippet && !isPhone && !isEmbedded && !isFloating ? (
        <View style={{ marginBottom: 8, gap: 6 }} data-testid="chat-favorite-snippets" testID="chat-favorite-snippets">
          <Text style={{ color: C.textSec, fontSize: 10, fontWeight: '700' }} data-testid="chat-favorite-snippets-title" testID="chat-favorite-snippets-title">
            Favorite answers
          </Text>
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6 }}>
            {favoriteSnippets.slice(0, 4).map((fav) => (
              <TouchableOpacity
                key={fav.message_id}
                onPress={() => onUseFavoriteSnippet(fav.content)}
                style={{ borderRadius: 999, borderWidth: 1, borderColor: C.border, backgroundColor: C.bgSoft, paddingHorizontal: 8, paddingVertical: 5 }}
                data-testid={`chat-favorite-snippet-${fav.message_id}`}
                testID={`chat-favorite-snippet-${fav.message_id}`}
              >
                <Text style={{ color: C.text, fontSize: 10, fontWeight: '700' }} numberOfLines={1}>
                  {fav.content.slice(0, 44)}
                </Text>
              </TouchableOpacity>
            ))}
          </View>
        </View>
      ) : null}

      <NovaStatusStrip
        C={C}
        tx={tx}
        health={health}
        hasLiveAssistantReply={hasLiveAssistantReply}
        latestAssistantMessage={latestAssistantMessage}
        pinnedCount={pinnedCount}
        conversationPinned={conversationPinned}
        isPhone={isPhone}
        isEmbedded={isEmbedded}
        isFloating={isFloating}
        retryPrompt={retryPrompt}
        isLoading={isLoading}
        onRetryTimeout={onRetryTimeout}
      />

      {/* Attachment preview */}
      {attachmentPreview && (
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, paddingHorizontal: 14, paddingTop: 8 }}>
          <Ionicons name={attachmentPreview.type.startsWith('image/') ? 'image' : 'document'} size={16} color={C.primary} />
          <Text style={{ fontSize: 12, color: C.text, flex: 1 }} numberOfLines={1}>{attachmentPreview.name}</Text>
          <TouchableOpacity aria-label="close circle button" onPress={() => setAttachmentPreview(null)}><Ionicons name="close-circle" size={18} color={C.textMuted} /></TouchableOpacity>
        </View>
      )}
      {/* Recording indicator */}
      {isRecording && (
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, paddingHorizontal: 14, paddingTop: 8 }}>
          <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: C.error }} />
          <Text style={{ fontSize: 12, fontWeight: '700', color: C.error }}>{t('help.nova.recording')} {recordingTime}s</Text>
          <TouchableOpacity onPress={stopRecording} style={{ marginLeft: 'auto', backgroundColor: C.error, paddingHorizontal: 12, paddingVertical: 6, borderRadius: 8 }} data-testid="stop-recording-btn" testID="stop-recording-btn">
            <Text style={{ color: colors.primaryText, fontSize: 12, fontWeight: '700' }}>{t('help.nova.stopSend')}</Text>
          </TouchableOpacity>
        </View>
      )}
      <View style={[s.inputRow, { backgroundColor: C.bgSoft, borderColor: C.border }]}>
        {/* Hidden file input */}
        {Platform.OS === 'web' && (
          <input ref={fileInputRef} type="file" accept="image/*,.pdf,.txt,.docx,application/vnd.openxmlformats-officedocument.wordprocessingml.document,text/plain" style={{ display: 'none' } as any} onChange={onFileSelected} data-testid="file-input-hidden" aria-label="attach button" />
        )}
        {/* Attachment button */}
        <TouchableOpacity data-testid="chat-attach-btn" testID="chat-attach-btn" style={{ paddingHorizontal: 8, paddingVertical: 8, opacity: isLoading ? 0.4 : 1 }} onPress={handleAttachment} disabled={isLoading || isRecording}>
          <Ionicons name="attach" size={20} color={C.primary} />
        </TouchableOpacity>
        <TextInput ref={inputRef as any} data-testid="chat-input" testID="chat-input" style={[s.chatInput, { color: C.text }]}
          placeholder={isRecording ? t('help.nova.recording') : t('help.nova.placeholder')} placeholderTextColor={C.textMuted}
          value={inputText} onChangeText={setInputText} multiline maxLength={500} editable={!isRecording} />
        {/* Audio button */}
        {!inputText.trim() && !isRecording && (
          <TouchableOpacity data-testid="chat-audio-btn" testID="chat-audio-btn" style={{ paddingHorizontal: 8, paddingVertical: 8, opacity: isLoading ? 0.4 : 1 }} onPress={startRecording} disabled={isLoading}>
            <Ionicons name="mic" size={20} color={C.primary} />
          </TouchableOpacity>
        )}
        <TouchableOpacity data-testid="chat-send-btn" testID="chat-send-btn" style={[s.sendBtn, { backgroundColor: C.primary, borderColor: (globalThis as any).__alphaColor(C.primary, '55') }, (!inputText.trim() || isLoading || isRecording) && { opacity: 0.4 }]}
          onPress={() => sendMessage(inputText)} disabled={!inputText.trim() || isLoading || isRecording}>
          {isLoading ? <ActivityIndicator size="small" color={colors.primaryText} /> : <Ionicons name="send" size={18} color={colors.primaryText} />}
        </TouchableOpacity>
      </View>
    </View>
  );
};
