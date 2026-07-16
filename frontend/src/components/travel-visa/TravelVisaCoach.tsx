import React, { useState, useCallback, useRef, useEffect } from 'react';
import { View, Text, TouchableOpacity, TextInput, ScrollView, ActivityIndicator, Platform } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useTheme } from '../../context/ThemeContext';
import { useLanguage } from '../../i18n/LanguageContext';
import api from '../../services/api';

export default function TravelVisaCoach({ userId, plan }: { userId: string; plan: string }) {
  const { colors } = useTheme();
  const { t } = useLanguage();
  const tx = React.useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);
  const [messages, setMessages] = useState<{ role: string; content: string }[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [country, setCountry] = useState('');
  const [visaType, setVisaType] = useState('');
  const [started, setStarted] = useState(false);
  const scrollRef = useRef<ScrollView>(null);

  const sendMessage = useCallback(async () => {
    if (!input.trim() || loading) return;
    const userMsg = input.trim();
    setInput('');
    setMessages(prev => [...prev, { role: 'user', content: userMsg }]);
    setLoading(true);
    try {
      const res = await api.post('/travel-visa/coach', {
        user_id: userId, session_id: sessionId, message: userMsg,
        country: country || undefined, visa_type: visaType || undefined,
      });
      if (res.data?.session_id) setSessionId(res.data.session_id);
      setMessages(prev => [...prev, { role: 'assistant', content: res.data?.response || tx('travelVisa.coach.states.noResponse', 'No response') }]);
    } catch (e: any) {
      const detail = e?.response?.data?.detail || tx('travelVisa.coach.errors.connectFailed', 'Error connecting to AI coach');
      setMessages(prev => [...prev, { role: 'assistant', content: detail }]);
    }
    setLoading(false);
    setTimeout(() => scrollRef.current?.scrollToEnd({ animated: true }), 100);
  }, [input, loading, sessionId, userId, country, visaType]);

  if (!started) {
    return (
      <View data-testid="tv-coach-setup" style={{
        padding: 24, borderRadius: 16, backgroundColor: colors.card,
        borderWidth: 1, borderColor: colors.border,
      }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 16 }}>
          <View style={{ width: 36, height: 36, borderRadius: 10, backgroundColor: colors.primarySoft, alignItems: 'center', justifyContent: 'center' }}>
            <Ionicons name="chatbubble-ellipses" size={18} color={colors.primary} />
          </View>
          <View>
            <Text style={{ fontSize: 16, fontWeight: '700', color: colors.text }}>{tx('travelVisa.coach.header.title', 'AI Visa Coach')}</Text>
            <Text style={{ fontSize: 12, color: colors.textMuted }}>{tx('travelVisa.coach.header.poweredBy', 'Powered by GPT-5.2')}</Text>
          </View>
        </View>
        <Text style={{ fontSize: 13, color: colors.textMuted, marginBottom: 16, lineHeight: 20 }}>
          {tx('travelVisa.coach.header.description', 'Get personalized visa preparation advice, interview coaching, document checklists, and expert guidance for any country.')}
        </Text>
        <Text style={{ fontSize: 12, fontWeight: '600', color: colors.text, marginBottom: 6 }}>{tx('travelVisa.coach.fields.targetCountry', 'Target Country (optional)')}</Text>
        <TextInput data-testid="tv-coach-country-input" value={country} onChangeText={setCountry}
          placeholder={tx('travelVisa.coach.fields.countryPlaceholder', 'e.g. United States, Canada, UK...')}
          placeholderTextColor={colors.placeholder}
          style={{
            height: 42, borderRadius: 10, paddingHorizontal: 14, fontSize: 14,
            backgroundColor: colors.input, borderWidth: 1, borderColor: colors.inputBorder,
            color: colors.inputText, marginBottom: 12,
            ...(Platform.OS === 'web' ? { outlineStyle: 'none' } as any : {}),
          }} />
        <Text style={{ fontSize: 12, fontWeight: '600', color: colors.text, marginBottom: 6 }}>{tx('travelVisa.coach.fields.visaType', 'Visa Type (optional)')}</Text>
        <TextInput data-testid="tv-coach-visa-input" value={visaType} onChangeText={setVisaType}
          placeholder={tx('travelVisa.coach.fields.visaPlaceholder', 'e.g. Student, Tourist, Work...')}
          placeholderTextColor={colors.placeholder}
          style={{
            height: 42, borderRadius: 10, paddingHorizontal: 14, fontSize: 14,
            backgroundColor: colors.input, borderWidth: 1, borderColor: colors.inputBorder,
            color: colors.inputText, marginBottom: 16,
            ...(Platform.OS === 'web' ? { outlineStyle: 'none' } as any : {}),
          }} />
        <TouchableOpacity data-testid="tv-coach-start-btn" onPress={() => setStarted(true)}
          style={{ paddingVertical: 12, borderRadius: 10, backgroundColor: colors.primary, alignItems: 'center' }}>
          <Text style={{ fontSize: 14, fontWeight: '700', color: colors.primaryText }}>{tx('travelVisa.coach.actions.startSession', 'Start Coaching Session')}</Text>
        </TouchableOpacity>
      </View>
    );
  }

  return (
    <View data-testid="tv-coach-chat" style={{
      borderRadius: 16, backgroundColor: colors.card, borderWidth: 1, borderColor: colors.border,
      overflow: 'hidden', minHeight: 400,
    }}>
      <View style={{
        flexDirection: 'row', alignItems: 'center', gap: 8, padding: 14,
        borderBottomWidth: 1, borderBottomColor: colors.border,
      }}>
        <View style={{ width: 28, height: 28, borderRadius: 8, backgroundColor: colors.primarySoft, alignItems: 'center', justifyContent: 'center' }}>
          <Ionicons name="chatbubble-ellipses" size={14} color={colors.primary} />
        </View>
        <Text style={{ fontSize: 14, fontWeight: '600', color: colors.text, flex: 1 }}>{tx('travelVisa.coach.header.title', 'AI Visa Coach')}</Text>
        {country && <Text style={{ fontSize: 11, color: colors.textMuted }}>{country}</Text>}
        <TouchableOpacity accessibilityLabel="refresh button" onPress={() => { setStarted(false); setMessages([]); setSessionId(null); }}>
          <Ionicons name="refresh" size={18} color={colors.textMuted} />
        </TouchableOpacity>
      </View>
      <ScrollView ref={scrollRef} style={{ flex: 1, maxHeight: 400, padding: 14 }} contentContainerStyle={{ gap: 10 }}>
        {messages.length === 0 && (
          <Text style={{ fontSize: 13, color: colors.textMuted, textAlign: 'center', padding: 20 }}>
            {tx('travelVisa.coach.states.emptyPrompt', 'Ask me anything about visa applications, interviews, documents, or immigration!')}
          </Text>
        )}
        {messages.map((msg, i) => (
          <View key={i} style={{
            alignSelf: msg.role === 'user' ? 'flex-end' : 'flex-start',
            maxWidth: '80%', padding: 12, borderRadius: 12,
            backgroundColor: msg.role === 'user' ? colors.primary : colors.surfaceHover,
          }}>
            <Text style={{
              fontSize: 13, lineHeight: 20,
              color: msg.role === 'user' ? colors.primaryText : colors.text,
            }}>{msg.content}</Text>
          </View>
        ))}
        {loading && (
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, padding: 8 }}>
            <ActivityIndicator size="small" color={colors.primary} />
            <Text style={{ fontSize: 12, color: colors.textMuted }}>{tx('travelVisa.coach.states.thinking', 'Thinking...')}</Text>
          </View>
        )}
      </ScrollView>
      <View style={{
        flexDirection: 'row', alignItems: 'center', gap: 8, padding: 12,
        borderTopWidth: 1, borderTopColor: colors.border,
      }}>
        <TextInput data-testid="tv-coach-message-input" value={input} onChangeText={setInput}
          placeholder={tx('travelVisa.coach.fields.messagePlaceholder', 'Type your question...')} placeholderTextColor={colors.placeholder}
          onSubmitEditing={sendMessage}
          style={{
            flex: 1, height: 40, borderRadius: 10, paddingHorizontal: 14, fontSize: 13,
            backgroundColor: colors.input, borderWidth: 1, borderColor: colors.inputBorder,
            color: colors.inputText,
            ...(Platform.OS === 'web' ? { outlineStyle: 'none' } as any : {}),
          }} />
        <TouchableOpacity data-testid="tv-coach-send-btn" onPress={sendMessage} disabled={loading || !input.trim()}
          style={{
            width: 40, height: 40, borderRadius: 10, backgroundColor: colors.primary,
            alignItems: 'center', justifyContent: 'center', opacity: loading || !input.trim() ? 0.5 : 1,
          }}>
          <Ionicons name="send" size={16} color={colors.primaryText} />
        </TouchableOpacity>
      </View>
    </View>
  );
}
