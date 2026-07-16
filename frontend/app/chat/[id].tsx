import React, { useEffect, useState, useRef, useCallback } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  TextInput,
  FlatList,
  KeyboardAvoidingView,
  Platform,
  ActivityIndicator,
  Alert,
  Animated,
  Keyboard,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { useAppStore } from '../../src/store/appStore';
import { useAuth } from '../../src/context/AuthContext';
import { useTheme } from '../../src/context/ThemeContext';
import { useTranslation } from '../../src/hooks/useTranslation';
import { getConversation, sendMessage, completeConversation, getScenario } from '../../src/services/api';
import { ChatSkeleton } from '../../src/components/SkeletonLoaders';

interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: string;
  feedback?: {
    scores?: { [key: string]: number };
    overall_score?: number;
    tone?: string;
    strengths?: string[];
    suggestions?: string[];
  };
}

interface Scenario {
  id: string;
  title: string;
  category: string;
  persona_name: string;
  persona_description: string;
}

export default function ChatScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const { colors } = useTheme();
  const { t } = useTranslation();
  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };
  const { user } = useAuth();
  const { userId, hasHydrated, currentScenario, setCurrentScenario, initializeUser } = useAppStore();

  const COLORS = React.useMemo(() => ({
    primary: colors.primary,
    primaryLight: colors.primary,
    background: colors.bg,
    cardBg: colors.card,
    messageBg: colors.bgCard || colors.cardAlt || colors.surface || colors.card,
    userMessage: colors.primary,
    text: colors.text,
    textMuted: colors.textMuted,
    success: colors.success,
    successText: colors.successText || colors.success,
    warning: colors.warning,
    warningText: colors.warningText || colors.warning,
    error: colors.error,
    onPrimary: colors.primaryText,
    dating: colors.warningText || colors.warning,
    workplace: colors.primary,
    friendship: colors.success,
  }), [colors]);

  const styles = React.useMemo(() => createStyles(COLORS), [COLORS]);
  
  // Initialize user and get effective user ID
  useEffect(() => {
    if (!hasHydrated) return;
    void initializeUser();
  }, [hasHydrated, initializeUser]);
  
  const effectiveUserId = user?.user_id || userId;
  
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputText, setInputText] = useState('');
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [scenario, setScenarioData] = useState<Scenario | null>(currentScenario);
  const [showFeedback, setShowFeedback] = useState(false);
  const [lastFeedback, setLastFeedback] = useState<any>(null);
  const [completing, setCompleting] = useState(false);
  
  const flatListRef = useRef<FlatList>(null);
  const feedbackAnimation = useRef(new Animated.Value(0)).current;

  const loadConversation = useCallback(async () => {
    if (!id) return;
    try {
      const data = await getConversation(id);
      setMessages(data.messages || []);
      
      // Load scenario if not set
      if (!currentScenario && data.scenario_id) {
        const scenarioData = await getScenario(data.scenario_id);
        setScenarioData(scenarioData);
        setCurrentScenario(scenarioData);
      }
    } catch (error) {
      console.error('Error loading conversation:', error);
      Alert.alert(tx('chat.alerts.errorTitle', 'Error'), tx('chat.alerts.loadConversationFailed', 'Failed to load conversation'));
    } finally {
      setLoading(false);
    }
  }, [currentScenario, id, setCurrentScenario]);

  useEffect(() => {
    loadConversation();
  }, [loadConversation]);

  useEffect(() => {
    if (showFeedback) {
      Animated.spring(feedbackAnimation, {
        toValue: 1,
        useNativeDriver: true,
        tension: 50,
        friction: 7,
      }).start();
    } else {
      Animated.timing(feedbackAnimation, {
        toValue: 0,
        duration: 200,
        useNativeDriver: true,
      }).start();
    }
  }, [feedbackAnimation, showFeedback]);

  const handleSendMessage = async () => {
    if (!inputText.trim() || sending || !id || !effectiveUserId) return;
    
    Keyboard.dismiss();
    const messageText = inputText.trim();
    setInputText('');
    setSending(true);
    setShowFeedback(false);

    // Optimistically add user message
    const tempUserMessage: Message = {
      id: `temp-${Date.now()}`,
      role: 'user',
      content: messageText,
      timestamp: new Date().toISOString(),
    };
    setMessages(prev => [...prev, tempUserMessage]);

    try {
      const response = await sendMessage(id, effectiveUserId, messageText);
      
      // Update with real messages
      setMessages(prev => {
        const withoutTemp = prev.filter(m => !m.id.startsWith('temp-'));
        return [
          ...withoutTemp,
          { ...tempUserMessage, id: `user-${Date.now()}`, feedback: response.feedback },
          {
            id: `assistant-${Date.now()}`,
            role: 'assistant',
            content: response.assistant_message,
            timestamp: new Date().toISOString(),
          },
        ];
      });

      // Show feedback
      setLastFeedback(response.feedback);
      setShowFeedback(true);
      
      // Auto-hide feedback after 5 seconds
      setTimeout(() => {
        setShowFeedback(false);
      }, 5000);
      
    } catch (error) {
      console.error('Error sending message:', error);
      // Remove temp message on error
      setMessages(prev => prev.filter(m => !m.id.startsWith('temp-')));
      Alert.alert(tx('chat.alerts.errorTitle', 'Error'), tx('chat.alerts.sendMessageFailed', 'Failed to send message. Please try again.'));
    } finally {
      setSending(false);
    }
  };

  const handleCompleteSession = async () => {
    if (!id || !effectiveUserId) return;
    
    Alert.alert(
      'Complete Session',
      'Are you sure you want to end this practice session? You\'ll receive a summary of your performance.',
      [
        { text: 'Continue Practicing', style: 'cancel' },
        {
          text: 'Complete',
          onPress: async () => {
            setCompleting(true);
            try {
              const result = await completeConversation(id, effectiveUserId);
              Alert.alert(
                'Session Complete!',
                `Your overall score: ${result.summary.overall_score}/100\n\nStrengths: ${result.summary.strengths?.join(', ') || 'Keep practicing!'}\n\nAreas to improve: ${result.summary.areas_to_improve?.join(', ') || 'Great job!'}`,
                [
                  {
                    text: 'View Progress',
                    onPress: () => {
                      setCurrentScenario(null);
                      router.replace('/progress');
                    },
                  },
                  {
                    text: 'Done',
                    onPress: () => {
                      setCurrentScenario(null);
                      router.replace('/dashboard');
                    },
                  },
                ]
              );
            } catch (error) {
              console.error('Error completing conversation:', error);
              Alert.alert('Error', 'Failed to complete session');
            } finally {
              setCompleting(false);
            }
          },
        },
      ]
    );
  };

  const getScoreColor = (score: number) => {
    if (score >= 80) return COLORS.success;
    if (score >= 60) return COLORS.warning;
    return COLORS.error;
  };

  const renderMessage = useCallback(({ item }: { item: Message }) => {
    const isUser = item.role === 'user';
    
    return (
      <View style={[styles.messageContainer, isUser && styles.userMessageContainer]}>
        {!isUser && (
          <View style={styles.avatarContainer}>
            <Ionicons name="person-circle" size={36} color={COLORS.primary} />
          </View>
        )}
        <View
          style={[
            styles.messageBubble,
            isUser ? styles.userBubble : styles.assistantBubble,
          ]}
        >
          <Text style={[styles.messageText, isUser && styles.userMessageText]}>
            {item.content}
          </Text>
        </View>
      </View>
    );
  }, [COLORS, styles]);

  const categoryColor = scenario?.category 
    ? COLORS[scenario.category as keyof typeof COLORS] || COLORS.primary 
    : COLORS.primary;

  if (!hasHydrated || loading) {
    return (
      <SafeAreaView style={styles.container}>
        <ChatSkeleton />
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      {/* Header */}
      <View style={[styles.header, { borderBottomColor: (globalThis as any).__alphaColor(categoryColor, '30') }]}>
        <TouchableOpacity 
          style={styles.headerButton} 
          onPress={() => {
            setCurrentScenario(null);
            router.back();
          }}
        >
          <Ionicons name="arrow-back" size={24} color={COLORS.text} />
        </TouchableOpacity>
        
        <View style={styles.headerCenter}>
          <Text style={styles.headerTitle} numberOfLines={1}>
            {scenario?.persona_name || tx('chat.header.practiceSession', 'Practice Session')}
          </Text>
          <Text style={styles.headerSubtitle} numberOfLines={1}>
            {scenario?.title || tx('chat.header.conversation', 'Conversation')}
          </Text>
        </View>
        
        <TouchableOpacity 
          style={[styles.completeButton, { backgroundColor: categoryColor }]} 
          onPress={handleCompleteSession}
          disabled={completing}
        >
          {completing ? (
            <ActivityIndicator size="small" color={COLORS.onPrimary} />
          ) : (
            <Text style={styles.completeButtonText}>{tx('chat.actions.done', 'Done')}</Text>
          )}
        </TouchableOpacity>
      </View>

      {/* Feedback Popup */}
      {showFeedback && lastFeedback && (
        <Animated.View
          style={[
            styles.feedbackPopup,
            {
              opacity: feedbackAnimation,
              transform: [
                {
                  translateY: feedbackAnimation.interpolate({
                    inputRange: [0, 1],
                    outputRange: [-20, 0],
                  }),
                },
              ],
            },
          ]}
        >
          <TouchableOpacity 
            style={styles.feedbackClose}
            onPress={() => setShowFeedback(false)}
          >
            <Ionicons name="close" size={18} color={COLORS.textMuted} />
          </TouchableOpacity>
          
          <View style={styles.feedbackHeader}>
            <View style={[styles.scoreCircle, { borderColor: getScoreColor(lastFeedback.overall_score || 0) }]}>
              <Text style={[styles.scoreText, { color: getScoreColor(lastFeedback.overall_score || 0) }]}>
                {lastFeedback.overall_score || 0}
              </Text>
            </View>
            <View style={styles.feedbackInfo}>
              <Text style={styles.feedbackTone}>
                Tone: {lastFeedback.tone || 'Neutral'}
              </Text>
              {lastFeedback.strengths?.length > 0 && (
                <View style={styles.strengthItem}>
                  <Ionicons name="checkmark-circle" size={14} color={COLORS.successText} />
                  <Text style={styles.strengthText} numberOfLines={1}>
                    {lastFeedback.strengths[0]}
                  </Text>
                </View>
              )}
              {lastFeedback.suggestions?.length > 0 && (
                <View style={styles.suggestionItem}>
                  <Ionicons name="bulb" size={14} color={COLORS.warningText} />
                  <Text style={styles.suggestionText} numberOfLines={1}>
                    {lastFeedback.suggestions[0]}
                  </Text>
                </View>
              )}
            </View>
          </View>
        </Animated.View>
      )}

      {/* Messages */}
      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
        style={styles.chatContainer}
        keyboardVerticalOffset={0}
      >
        <FlatList
          ref={flatListRef}
          data={messages}
          renderItem={renderMessage}
          keyExtractor={(item) => item.id}
          contentContainerStyle={styles.messagesList}
          showsVerticalScrollIndicator={false}
          onContentSizeChange={() => flatListRef.current?.scrollToEnd({ animated: true })}
          ListHeaderComponent={
            <View style={styles.scenarioReminder}>
              <Ionicons name="information-circle" size={16} color={COLORS.textMuted} />
              <Text style={styles.scenarioReminderText}>
                {tx('chat.labels.practice', 'Practice:')} {scenario?.title || tx('chat.labels.communicationSkills', 'Communication Skills')}
              </Text>
            </View>
          }
        />

        {/* Typing Indicator */}
        {sending && (
          <View style={styles.typingIndicator}>
            <View style={styles.avatarContainer}>
              <Ionicons name="person-circle" size={36} color={COLORS.primary} />
            </View>
            <View style={styles.typingBubble}>
              <View style={styles.typingDots}>
                <View style={styles.typingDot} />
                <View style={[styles.typingDot, styles.typingDotMiddle]} />
                <View style={styles.typingDot} />
              </View>
            </View>
          </View>
        )}

        {/* Input */}
        <View style={styles.inputContainer}>
          <View style={styles.inputWrapper}>
            <TextInput
              style={styles.textInput}
              value={inputText}
              onChangeText={setInputText}
              placeholder={tx('chat.input.placeholder', 'Type your response...')}
              placeholderTextColor={COLORS.textMuted}
              multiline
              maxLength={500}
              editable={!sending}
            />
            <TouchableOpacity
              style={[
                styles.sendButton,
                (!inputText.trim() || sending) && styles.sendButtonDisabled,
              ]}
              onPress={handleSendMessage}
              disabled={!inputText.trim() || sending}
            >
              {sending ? (
                <ActivityIndicator size="small" color={COLORS.onPrimary} />
              ) : (
                <Ionicons name="send" size={20} color={COLORS.onPrimary} />
              )}
            </TouchableOpacity>
          </View>
        </View>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const createStyles = (COLORS: any) => StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: COLORS.background,
  },
  loadingContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
  },
  loadingText: {
    color: COLORS.textMuted,
    marginTop: 16,
    fontSize: 16,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 12,
    paddingVertical: 12,
    borderBottomWidth: 1,
    borderBottomColor: COLORS.cardBg,
  },
  headerButton: {
    width: 40,
    height: 40,
    justifyContent: 'center',
    alignItems: 'center',
  },
  headerCenter: {
    flex: 1,
    marginHorizontal: 8,
  },
  headerTitle: {
    fontSize: 17,
    fontWeight: 'bold',
    color: COLORS.text,
  },
  headerSubtitle: {
    fontSize: 12,
    color: COLORS.textMuted,
    marginTop: 2,
  },
  completeButton: {
    paddingHorizontal: 16,
    paddingVertical: 8,
    borderRadius: 16,
  },
  completeButtonText: {
    fontSize: 14,
    fontWeight: '600',
    color: COLORS.onPrimary,
  },
  feedbackPopup: {
    position: 'absolute',
    top: 70,
    left: 16,
    right: 16,
    backgroundColor: COLORS.cardBg,
    borderRadius: 16,
    padding: 16,
    zIndex: 100,
    ...(Platform.OS === 'web'
      ? { boxShadow: '0 4px 8px rgba(0,0,0,0.3)' }
      : { shadowColor: COLORS.text, shadowOffset: { width: 0, height: 4 }, shadowOpacity: 0.3, shadowRadius: 8 }),
    elevation: 8,
  },
  feedbackClose: {
    position: 'absolute',
    top: 8,
    right: 8,
    padding: 4,
  },
  feedbackHeader: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  scoreCircle: {
    width: 50,
    height: 50,
    borderRadius: 25,
    borderWidth: 3,
    justifyContent: 'center',
    alignItems: 'center',
    marginRight: 14,
  },
  scoreText: {
    fontSize: 18,
    fontWeight: 'bold',
  },
  feedbackInfo: {
    flex: 1,
  },
  feedbackTone: {
    fontSize: 14,
    fontWeight: '600',
    color: COLORS.text,
    marginBottom: 6,
  },
  strengthItem: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    marginBottom: 4,
  },
  strengthText: {
    fontSize: 12,
    color: COLORS.successText,
    flex: 1,
  },
  suggestionItem: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  suggestionText: {
    fontSize: 12,
    color: COLORS.warningText,
    flex: 1,
  },
  chatContainer: {
    flex: 1,
  },
  messagesList: {
    paddingHorizontal: 16,
    paddingBottom: 16,
  },
  scenarioReminder: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 12,
    gap: 6,
  },
  scenarioReminderText: {
    fontSize: 12,
    color: COLORS.textMuted,
  },
  messageContainer: {
    flexDirection: 'row',
    marginBottom: 16,
    alignItems: 'flex-end',
  },
  userMessageContainer: {
    justifyContent: 'flex-end',
  },
  avatarContainer: {
    marginRight: 8,
  },
  messageBubble: {
    maxWidth: '75%',
    paddingHorizontal: 16,
    paddingVertical: 12,
    borderRadius: 20,
  },
  userBubble: {
    backgroundColor: COLORS.userMessage,
    borderBottomRightRadius: 6,
    marginLeft: 'auto',
  },
  assistantBubble: {
    backgroundColor: COLORS.messageBg,
    borderBottomLeftRadius: 6,
  },
  messageText: {
    fontSize: 15,
    color: COLORS.text,
    lineHeight: 22,
  },
  userMessageText: {
    color: COLORS.onPrimary,
  },
  typingIndicator: {
    flexDirection: 'row',
    alignItems: 'flex-end',
    paddingHorizontal: 16,
    marginBottom: 8,
  },
  typingBubble: {
    backgroundColor: COLORS.messageBg,
    paddingHorizontal: 16,
    paddingVertical: 14,
    borderRadius: 20,
    borderBottomLeftRadius: 6,
  },
  typingDots: {
    flexDirection: 'row',
    gap: 4,
  },
  typingDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    backgroundColor: COLORS.textMuted,
    opacity: 0.5,
  },
  typingDotMiddle: {
    opacity: 0.7,
  },
  inputContainer: {
    paddingHorizontal: 16,
    paddingVertical: 12,
    borderTopWidth: 1,
    borderTopColor: COLORS.cardBg,
    backgroundColor: COLORS.background,
  },
  inputWrapper: {
    flexDirection: 'row',
    alignItems: 'flex-end',
    backgroundColor: COLORS.cardBg,
    borderRadius: 24,
    paddingLeft: 16,
    paddingRight: 6,
    paddingVertical: 6,
  },
  textInput: {
    flex: 1,
    fontSize: 15,
    color: COLORS.text,
    maxHeight: 100,
    paddingVertical: 8,
  },
  sendButton: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: COLORS.primary,
    justifyContent: 'center',
    alignItems: 'center',
  },
  sendButtonDisabled: {
    backgroundColor: (globalThis as any).__alphaColor(COLORS.primary, '50'),
  },
});
