 
/**
 * FAQ section uses semantic V2 tokens for all light/dark chip states.
 */
import React, { useState, useEffect, useRef, useCallback } from 'react';
import { View, Text, StyleSheet, ScrollView, TouchableOpacity, TextInput, ActivityIndicator, Platform } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { getShadow } from '../../utils/themeShadows';
import api from '../../services/api';
import { useLiveQuery } from '../../hooks/useLiveQuery';
import { useTheme } from '../../context/ThemeContext';
import { clientLogger } from '../../utils/clientLogger';
import { type FAQItem, type ThemeColors, type TabKey } from './helpTypes';

interface FAQSectionProps {
  C: ThemeColors;
  darkMode: boolean;
  L: (key: string, fallback?: string) => string;
  searchQuery: string;
  setSearchQuery: (v: string) => void;
  activeCategory: string | null;
  setActiveCategory: (cat: string | null) => void;
  faqs: FAQItem[];
  faqLoading: boolean;
  expandedFAQ: string | null;
  setExpandedFAQ: (v: string | null) => void;
  faqVotes: Record<string, 'up' | 'down'>;
  voteFaq: (question: string, helpful: boolean) => void;
  filteredFAQs: FAQItem[];
  setActiveTab: (tab: TabKey) => void;
  languageCode: string;
}

function formatCategoryLabel(category: string) {
  return String(category || 'general').replace(/[-_]/g, ' ').replace(/\b\w/g, (ch) => ch.toUpperCase());
}

function categoryMeta(category: string, fallbackColor: string) {
  return { label: formatCategoryLabel(category), icon: 'ellipse', color: fallbackColor };
}

function FAQItemRow({ faq, idx, C, L, expandedFAQ, setExpandedFAQ, faqVotes, voteFaq }: {
  faq: FAQItem; idx: number; C: ThemeColors; L: (k: string, f?: string) => string;
  expandedFAQ: string | null; setExpandedFAQ: (v: string | null) => void;
  faqVotes: Record<string, 'up' | 'down'>; voteFaq: (q: string, h: boolean) => void;
}) {
  const key = `${faq.category}-${idx}`;
  const isOpen = expandedFAQ === key;
  const meta = categoryMeta(faq.category, C.primary);
  return (
    <TouchableOpacity key={key} data-testid={`faq-item-${key}`} testID={`faq-item-${key}`} style={[s.faqItem, { borderBottomColor: C.border }, isOpen && { backgroundColor: (globalThis as any).__alphaColor(C.primary, '06') }]}
      onPress={() => setExpandedFAQ(isOpen ? null : key)} activeOpacity={0.7}>
      <View style={s.faqRow}>
        <View style={[s.faqDot, { backgroundColor: (globalThis as any).__alphaColor(meta.color, '20') }]}>
          <Ionicons name={meta.icon as any} size={14} color={meta.color} />
        </View>
        <Text style={[s.faqQ, { color: C.text }]}>{faq.q}</Text>
        <Ionicons name={isOpen ? 'chevron-up' : 'chevron-down'} size={16} color={isOpen ? C.primary : C.textMuted} />
      </View>
      {isOpen && (
        <View style={s.faqAnswerWrap}>
          <View style={[s.faqAnswerBar, { backgroundColor: meta.color }]} />
          <View style={{ flex: 1 }}>
            <Text style={[s.faqA, { color: C.textSec }]}>{faq.a}</Text>
            <View style={s.voteRow}>
              <Text style={[s.voteLabel, { color: C.textMuted }]}>{L('was_helpful', 'Was this helpful?')}</Text>
              {faqVotes[faq.q] ? (
                <View style={s.voteDone}>
                  <Ionicons name={faqVotes[faq.q] === 'up' ? 'thumbs-up' : 'thumbs-down'} size={14} color={faqVotes[faq.q] === 'up' ? C.success : C.error} />
                  <Text style={{ fontSize: 12, fontWeight: '600', color: faqVotes[faq.q] === 'up' ? C.success : C.error }}>{faqVotes[faq.q] === 'up' ? L('thanks', 'Thanks!') : L('noted', 'Noted')}</Text>
                </View>
              ) : (
                <View style={s.voteBtns}>
                  <TouchableOpacity data-testid={`faq-vote-up-${idx}`} testID={`faq-vote-up-${idx}`} style={[s.voteBtn, { backgroundColor: C.bgSoft, borderColor: C.border }]} onPress={() => voteFaq(faq.q, true)}>
                    <Ionicons name="thumbs-up-outline" size={14} color={C.successText} />
                  </TouchableOpacity>
                  <TouchableOpacity data-testid={`faq-vote-down-${idx}`} testID={`faq-vote-down-${idx}`} style={[s.voteBtn, { backgroundColor: C.bgSoft, borderColor: C.border }]} onPress={() => voteFaq(faq.q, false)}>
                    <Ionicons name="thumbs-down-outline" size={14} color={C.error} />
                  </TouchableOpacity>
                </View>
              )}
            </View>
          </View>
        </View>
      )}
    </TouchableOpacity>
  );
}

export default function FAQSection({ C, darkMode, L, searchQuery, setSearchQuery, activeCategory, setActiveCategory, faqs, faqLoading, expandedFAQ, setExpandedFAQ, faqVotes, voteFaq, filteredFAQs, setActiveTab, languageCode }: FAQSectionProps) {
  // NOTE: several inline styles below reference `colors.primaryText` /
  // `.warning` / `.success` / `.successText` — those aren't on the cherry-
  // picked `C: ThemeColors` prop, so we pull the full theme here.
  const { colors } = useTheme();
  const [smartSuggestions, setSmartSuggestions] = useState<FAQItem[]>([]);
  const [aiAnswer, setAiAnswer] = useState<string | null>(null);
  const [didYouMean, setDidYouMean] = useState<string | null>(null);
  const [smartLoading, setSmartLoading] = useState(false);
  const [aiLoading, setAiLoading] = useState(false);
  const [showDropdown, setShowDropdown] = useState(false);
  const [trending, setTrending] = useState<{ term: string; count: number }[]>([]);
  const [isRecording, setIsRecording] = useState(false);
  const [recordingTime, setRecordingTime] = useState(0);
  const [transcribing, setTranscribing] = useState(false);
  const inactiveChipBg = C.bgSoft;
  const inactiveChipBorder = C.border;
  const inactiveChipText = darkMode ? C.textMuted : C.textSec;
  const selectedChipText = colors.primaryText;
  const faqCategories = Array.from(new Set(faqs.map((faq) => faq.category).filter(Boolean)));
  const mediaRecorderRef = useRef<any>(null);
  const audioChunksRef = useRef<any[]>([]);
  const recordingTimerRef = useRef<any>(null);
  const debounceRef = useRef<any>(null);
  const searchInputFocused = useRef(false);

  // Fetch trending searches via useLiveQuery
  const { data: trendData } = useLiveQuery('/support/faq/trending', { entity: 'faq_trending', pollInterval: 120000 });
  useEffect(() => { if (trendData?.trending) setTrending(trendData.trending); }, [trendData]);

  // Debounced smart search
  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    if (!searchQuery.trim() || searchQuery.trim().length < 2) {
      setSmartSuggestions([]);
      setAiAnswer(null);
      setDidYouMean(null);
      setShowDropdown(false);
      return;
    }
    debounceRef.current = setTimeout(async () => {
      setSmartLoading(true);
      try {
        const res = await api.post('/support/faq/smart-search', { query: searchQuery.trim(), lang: languageCode });
        clientLogger.log('[FAQSection] Smart search response:', res.data);
        clientLogger.log('[FAQSection] did_you_mean value:', res.data.did_you_mean);
        setSmartSuggestions(res.data.suggestions || []);
        setDidYouMean(res.data.did_you_mean || null);
        setAiAnswer(null);
        setShowDropdown(true);
      } catch (err) { console.error('[FAQSection] Smart search error:', err); } finally { setSmartLoading(false); }
    }, 300);
    return () => { if (debounceRef.current) clearTimeout(debounceRef.current); };
  }, [searchQuery, languageCode]);

  const askNova = useCallback(async () => {
    setAiLoading(true);
    try {
      const res = await api.post('/support/faq/smart-search', { query: searchQuery.trim(), lang: languageCode, generate_ai: true });
      setAiAnswer(res.data.ai_answer || 'Sorry, I could not generate an answer right now.');
    } catch {
      setAiAnswer('Sorry, I could not generate an answer right now. Please try the Chat tab.');
    } finally { setAiLoading(false); }
  }, [searchQuery, languageCode]);

  const selectSuggestion = useCallback((faq: FAQItem) => {
    setShowDropdown(false);
    // Find the FAQ in the main list and expand it
    const idx = filteredFAQs.findIndex(f => f.q === faq.q);
    if (idx >= 0) {
      setExpandedFAQ(`${faq.category}-${idx}`);
    } else {
      // FAQ might be in a different category, search all faqs
      const allIdx = faqs.findIndex(f => f.q === faq.q);
      if (allIdx >= 0) {
        setActiveCategory(null); // Show all categories
        setTimeout(() => setExpandedFAQ(`${faq.category}-${allIdx}`), 100);
      }
    }
  }, [filteredFAQs, faqs, setExpandedFAQ, setActiveCategory]);

  const startRecording = useCallback(async () => {
    if (Platform.OS !== 'web') return;
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(stream, { mimeType: 'audio/webm' });
      audioChunksRef.current = [];
      recorder.ondataavailable = (e: any) => { if (e.data.size > 0) audioChunksRef.current.push(e.data); };
      recorder.start();
      mediaRecorderRef.current = recorder;
      setIsRecording(true);
      setRecordingTime(0);
      recordingTimerRef.current = setInterval(() => setRecordingTime(t => t + 1), 1000);
    } catch { window.alert('Microphone access denied. Please allow microphone access.'); }
  }, []);

  const stopRecording = useCallback(async () => {
    if (!mediaRecorderRef.current) return;
    clearInterval(recordingTimerRef.current);
    return new Promise<void>((resolve) => {
      mediaRecorderRef.current.onstop = async () => {
        const blob = new Blob(audioChunksRef.current, { type: 'audio/webm' });
        mediaRecorderRef.current.stream.getTracks().forEach((t: any) => t.stop());
        setIsRecording(false);
        setRecordingTime(0);
        if (blob.size < 100) { resolve(); return; }
        setTranscribing(true);
        try {
          const fd = new FormData();
          fd.append('audio', blob, 'recording.webm');
          const res = await api.post('/support/faq/voice-search', fd, { headers: { 'Content-Type': 'multipart/form-data' } });
          if (res.data.transcription) {
            setSearchQuery(res.data.transcription);
          } else {
            window.alert(res.data.error || 'Could not transcribe. Try again or type your question.');
          }
        } catch { window.alert('Voice search failed. Please type your question instead.'); }
        finally { setTranscribing(false); }
        resolve();
      };
      mediaRecorderRef.current.stop();
    });
  }, [setSearchQuery]);

  return (
    <ScrollView showsVerticalScrollIndicator={false} contentContainerStyle={{ padding: 20, paddingBottom: 60 }}>
      {/* FAQ Header */}
      <View style={[s.faqHeader, { backgroundColor: C.card, borderColor: C.border }]} data-testid="faq-header" testID="faq-header">
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 8 }}>
          <View style={[s.faqHeaderIcon, { backgroundColor: colors.infoSoft }]}> 
            <Ionicons name="help-buoy" size={20} color={colors.info} />
          </View>
          <View>
            <Text style={[s.faqHeaderTitle, { color: C.text }]}>{L('title', 'Frequently Asked Questions')}</Text>
            <Text style={{ fontSize: 12, color: C.textMuted }}>{faqs.length} {L('answers_ready', 'answers ready for you')}</Text>
          </View>
        </View>
      </View>

      {/* Trending Searches */}
      {trending.length > 0 && !searchQuery.trim() && (
        <View style={[s.trendingWrap, { backgroundColor: C.card, borderColor: C.border }]} data-testid="trending-searches" testID="trending-searches">
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 8 }}>
            <Ionicons name="trending-up" size={14} color={C.primary} />
            <Text style={{ fontSize: 11, fontWeight: '700', color: C.textMuted, textTransform: 'uppercase', letterSpacing: 0.5 }}>{L('popular_searches', 'Popular searches')}</Text>
          </View>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 6 }}>
            {trending.map((t, i) => (
              <TouchableOpacity key={i} data-testid={`trending-chip-${i}`} testID={`trending-chip-${i}`}
                style={[s.trendingChip, { backgroundColor: C.bgSoft, borderColor: C.border }]}
                onPress={() => { setSearchQuery(t.term); }} activeOpacity={0.7}>
                <Ionicons name="search" size={11} color={C.textSec} />
                <Text style={{ fontSize: 12, fontWeight: '600', color: C.textSec }}>{t.term}</Text>
                <Text style={{ fontSize: 10, color: C.textMuted, fontWeight: '500' }}>{t.count}</Text>
              </TouchableOpacity>
            ))}
          </ScrollView>
        </View>
      )}

      {/* Search with Smart Suggestions */}
      <View style={{ position: 'relative', zIndex: 10 }}>
        <View style={[s.searchWrap, { backgroundColor: C.card, borderColor: showDropdown && smartSuggestions.length > 0 ? C.primary : C.border }]}>
          <Ionicons name="search" size={18} color={C.textMuted} />
          <TextInput data-testid="faq-search-input" testID="faq-search-input" style={[s.searchInput, { color: C.text }]}
            placeholder={L('search_placeholder', 'Search questions...')} placeholderTextColor={C.textMuted}
            value={searchQuery} onChangeText={setSearchQuery}
            onFocus={() => { searchInputFocused.current = true; if (smartSuggestions.length > 0 || searchQuery.trim().length >= 2) setShowDropdown(true); }}
            onBlur={() => { searchInputFocused.current = false; setTimeout(() => { if (!searchInputFocused.current) setShowDropdown(false); }, 300); }}
          />
          {smartLoading && <ActivityIndicator size="small" color={C.primary} style={{ marginRight: 4 }} />}
          {transcribing && <ActivityIndicator size="small" color={C.primary} style={{ marginRight: 4 }} />}
          {searchQuery.length > 0 && !smartLoading && !transcribing && (
            <TouchableOpacity data-testid="faq-search-clear" testID="faq-search-clear" onPress={() => { setSearchQuery(''); setShowDropdown(false); setAiAnswer(null); setDidYouMean(null); }}>
              <Ionicons name="close-circle" size={18} color={C.textMuted} />
            </TouchableOpacity>
          )}
          {/* Voice search mic button */}
          {!isRecording && !transcribing && Platform.OS === 'web' && (
            <TouchableOpacity data-testid="faq-voice-search-btn" testID="faq-voice-search-btn"
              style={[s.micBtn, { backgroundColor: (globalThis as any).__alphaColor(C.primary, '12') }]}
              onPress={startRecording} activeOpacity={0.7}>
              <Ionicons name="mic" size={16} color={C.primary} />
            </TouchableOpacity>
          )}
          {isRecording && (
            <TouchableOpacity data-testid="faq-voice-stop-btn" testID="faq-voice-stop-btn"
              style={[s.micBtn, { backgroundColor: (globalThis as any).__alphaColor(C.error, '15') }]}
              onPress={stopRecording} activeOpacity={0.7}>
              <Ionicons name="stop-circle" size={16} color={C.error} />
            </TouchableOpacity>
          )}
        </View>

        {/* Recording indicator */}
        {isRecording && (
          <View style={[s.recordingBar, { backgroundColor: (globalThis as any).__alphaColor(C.error, '10'), borderColor: (globalThis as any).__alphaColor(C.error, '25') }]} data-testid="faq-recording-indicator" testID="faq-recording-indicator">
            <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: C.error }} />
            <Text style={{ fontSize: 12, fontWeight: '700', color: C.error }}>Recording... {recordingTime}s</Text>
            <TouchableOpacity onPress={stopRecording} style={{ marginLeft: 'auto', backgroundColor: C.error, paddingHorizontal: 12, paddingVertical: 5, borderRadius: 8 }} accessibilityLabel="Stop & Search">
              <Text style={{ color: colors.primaryText, fontSize: 11, fontWeight: '700' }}>Stop & Search</Text>
            </TouchableOpacity>
          </View>
        )}
        {transcribing && (
          <View style={[s.recordingBar, { backgroundColor: (globalThis as any).__alphaColor(C.primary, '10'), borderColor: (globalThis as any).__alphaColor(C.primary, '25') }]} data-testid="faq-transcribing-indicator" testID="faq-transcribing-indicator">
            <ActivityIndicator size="small" color={C.primary} />
            <Text style={{ fontSize: 12, fontWeight: '600', color: C.primary }}>Transcribing your question...</Text>
          </View>
        )}

        {/* Smart Suggestions Dropdown */}
        {showDropdown && searchQuery.trim().length >= 2 && (
          <View 
            style={[s.dropdown, { backgroundColor: C.card, borderColor: C.border }, getShadow('lg', darkMode)]} 
            data-testid="smart-search-dropdown" testID="smart-search-dropdown"
            onStartShouldSetResponder={() => true}
            onResponderRelease={() => {}}
          >
            {/* Did you mean? banner */}
            {didYouMean && (
              <TouchableOpacity data-testid="did-you-mean-btn" testID="did-you-mean-btn"
                style={[s.didYouMean, { backgroundColor: (globalThis as any).__alphaColor(colors.warning, '10'), borderBottomColor: (globalThis as any).__alphaColor(C.warning, '25') }]}
                onPress={() => { setSearchQuery(didYouMean); setDidYouMean(null); }} activeOpacity={0.7}>
                <Ionicons name="bulb-outline" size={15} color={colors.warning} />
                <Text style={{ fontSize: 13, color: C.textSec }}>
                  Did you mean: <Text style={{ fontWeight: '800', color: C.primary }}>{didYouMean}</Text>?
                </Text>
                <Ionicons name="arrow-forward" size={14} color={C.primary} style={{ marginLeft: 'auto' }} />
              </TouchableOpacity>
            )}

            {smartSuggestions.length > 0 ? (
              <>
                <View style={{ paddingHorizontal: 14, paddingVertical: 8, borderBottomWidth: 1, borderBottomColor: C.border }}>
                  <Text style={{ fontSize: 10, fontWeight: '700', color: C.textMuted, textTransform: 'uppercase', letterSpacing: 0.5 }}>Matching FAQs</Text>
                </View>
                {smartSuggestions.map((faq, i) => {
                  const meta = categoryMeta(faq.category, C.primary);
                  return (
                    <TouchableOpacity key={i} data-testid={`smart-suggestion-${i}`} testID={`smart-suggestion-${i}`}
                      style={[s.suggestionItem, { borderBottomColor: C.border }]}
                      onPress={() => selectSuggestion(faq)} activeOpacity={0.7}>
                      <View style={[s.suggestionDot, { backgroundColor: (globalThis as any).__alphaColor(meta.color, '20') }]}>
                        <Ionicons name={meta.icon as any} size={12} color={meta.color} />
                      </View>
                      <Text style={{ flex: 1, fontSize: 13, color: C.text, fontWeight: '500' }} numberOfLines={2}>{faq.q}</Text>
                      <Ionicons name="arrow-forward" size={14} color={C.textMuted} />
                    </TouchableOpacity>
                  );
                })}
              </>
            ) : !smartLoading ? (
              <View style={{ paddingHorizontal: 14, paddingVertical: 12, alignItems: 'center' }}>
                <Ionicons name="search-outline" size={24} color={C.textMuted} />
                <Text style={{ fontSize: 13, color: C.textMuted, marginTop: 4 }}>No matching FAQs found</Text>
              </View>
            ) : null}

            {/* Ask Nova AI button */}
            <TouchableOpacity data-testid="smart-search-ask-nova" testID="smart-search-ask-nova"
              style={[s.askNovaBtn, { backgroundColor: C.bgSoft, borderTopColor: C.border }]}
              onPress={askNova} disabled={aiLoading}>
              <View style={[s.askNovaIcon, { backgroundColor: (globalThis as any).__alphaColor(C.primary, '20') }]}>
                <Ionicons name="sparkles" size={14} color={C.primary} />
              </View>
              <View style={{ flex: 1 }}>
                <Text style={{ fontSize: 13, fontWeight: '700', color: C.primary }}>
                  {aiLoading ? 'Nova is thinking...' : 'Ask Nova AI'}
                </Text>
                <Text style={{ fontSize: 11, color: C.textMuted }}>Get an instant AI answer</Text>
              </View>
              {aiLoading ? (
                <ActivityIndicator size="small" color={C.primary} />
              ) : (
                <Ionicons name="arrow-forward-circle" size={20} color={C.primary} />
              )}
            </TouchableOpacity>

            {/* AI Answer inline */}
            {aiAnswer && (
              <View style={[s.aiAnswerBox, { backgroundColor: C.bg, borderTopColor: C.border }]} data-testid="smart-search-ai-answer" testID="smart-search-ai-answer">
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 8 }}>
                  <View style={{ width: 22, height: 22, borderRadius: 7, backgroundColor: colors.success, alignItems: 'center', justifyContent: 'center' }}>
                    <Ionicons name="sparkles" size={11} color={colors.primaryText} />
                  </View>
                  <Text style={{ fontSize: 12, fontWeight: '800', color: colors.successText }}>Nova AI</Text>
                </View>
                <Text style={{ fontSize: 13, lineHeight: 20, color: C.text }}>{aiAnswer}</Text>
                <TouchableOpacity data-testid="ai-answer-chat-btn" testID="ai-answer-chat-btn"
                  style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginTop: 10, alignSelf: 'flex-start', backgroundColor: C.primary, paddingHorizontal: 12, paddingVertical: 6, borderRadius: 8 }}
                  onPress={() => { setShowDropdown(false); setActiveTab('contact'); }}>
                  <Ionicons name="chatbubbles" size={12} color={colors.primaryText} />
                  <Text style={{ fontSize: 11, fontWeight: '700', color: colors.primaryText }}>Continue in Chat</Text>
                </TouchableOpacity>
              </View>
            )}
          </View>
        )}
      </View>

      {/* Category chips */}
      <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ marginBottom: 16 }} contentContainerStyle={{ gap: 8, paddingRight: 8 }}>
        <TouchableOpacity data-testid="faq-chip-all" testID="faq-chip-all" style={[s.chip, { backgroundColor: !activeCategory ? C.primary : inactiveChipBg, borderWidth: 1, borderColor: !activeCategory ? C.primary : inactiveChipBorder }]} onPress={() => setActiveCategory(null)}>
          <Ionicons name="apps" size={14} color={!activeCategory ? selectedChipText : inactiveChipText} />
          <Text style={[s.chipText, { color: !activeCategory ? selectedChipText : inactiveChipText }]}>All</Text>
        </TouchableOpacity>
        {faqCategories.map((key) => {
          const meta = categoryMeta(key, C.primary);
          return (
          <TouchableOpacity key={key} data-testid={`faq-chip-${key}`} testID={`faq-chip-${key}`}
            style={[s.chip, { backgroundColor: activeCategory === key ? meta.color : inactiveChipBg, borderWidth: 1, borderColor: activeCategory === key ? meta.color : inactiveChipBorder }]}
            onPress={() => setActiveCategory(activeCategory === key ? null : key)}>
            <Ionicons name={meta.icon as any} size={14} color={activeCategory === key ? selectedChipText : inactiveChipText} />
            <Text style={[s.chipText, { color: activeCategory === key ? selectedChipText : inactiveChipText }]}>{meta.label}</Text>
          </TouchableOpacity>
          );
        })}
      </ScrollView>

      {/* FAQ List */}
      {faqLoading ? (
        <View style={{ alignItems: 'center', paddingVertical: 40 }}>
          <ActivityIndicator size="large" color={C.primary} />
          <Text style={{ fontSize: 13, color: C.textMuted, marginTop: 12 }}>Loading FAQs...</Text>
        </View>
      ) : filteredFAQs.length > 0 ? (
        <View style={[s.faqCard, { backgroundColor: C.bgSoft, borderColor: C.border }]}> 
          {filteredFAQs.map((faq, i) => (
            <FAQItemRow key={`${faq.category}-${i}`} faq={faq} idx={i} C={C} L={L}
              expandedFAQ={expandedFAQ} setExpandedFAQ={setExpandedFAQ}
              faqVotes={faqVotes} voteFaq={voteFaq} />
          ))}
        </View>
      ) : (
        <View style={{ alignItems: 'center', paddingVertical: 40 }} data-testid="faq-empty" testID="faq-empty">
          <Ionicons name="search-outline" size={40} color={C.textMuted} />
          <Text style={{ fontSize: 16, fontWeight: '700', color: C.text, marginTop: 12 }}>{L('no_results', 'No results found')}</Text>
          <Text style={{ fontSize: 13, color: C.textMuted, marginTop: 4, marginBottom: 16 }}>Try different keywords or ask Nova</Text>
          <TouchableOpacity style={[s.askBtnBottom, { backgroundColor: C.primary }]} onPress={() => setActiveTab('contact')} data-testid="faq-ask-nova-btn" testID="faq-ask-nova-btn">
            <Ionicons name="chatbubbles" size={16} color={colors.primaryText} />
            <Text style={{ fontSize: 13, fontWeight: '600', color: colors.primaryText }}>Ask Nova</Text>
          </TouchableOpacity>
        </View>
      )}

      {/* Didn't find answer? */}
      <View style={[s.ctaCard, { backgroundColor: C.bgSoft, borderColor: C.border }]} data-testid="faq-cta" testID="faq-cta">
        <Ionicons name="chatbubbles" size={28} color={C.primary} />
        <Text style={{ fontSize: 16, fontWeight: '700', color: C.text, marginTop: 8 }}>{L('still_questions', 'Still have questions?')}</Text>
        <Text style={{ fontSize: 13, color: C.textMuted, textAlign: 'center', marginTop: 4 }}>{L('nova_help', 'Our AI assistant Nova is available 24/7 to help you.')}</Text>
        <TouchableOpacity style={[s.ctaBtn, { backgroundColor: C.primary }]} onPress={() => setActiveTab('contact')} data-testid="faq-cta-btn" testID="faq-cta-btn">
          <Ionicons name="chatbubbles" size={16} color={colors.primaryText} />
          <Text style={{ fontSize: 14, fontWeight: '700', color: colors.primaryText }}>{L('chat_nova', 'Chat with Nova')}</Text>
        </TouchableOpacity>
      </View>
    </ScrollView>
  );
}

const s = StyleSheet.create({
  faqHeader: { borderRadius: 18, borderWidth: 1, padding: 18, marginBottom: 18 },
  faqHeaderIcon: { width: 36, height: 36, borderRadius: 10, alignItems: 'center', justifyContent: 'center' },
  faqHeaderTitle: { fontSize: 18, fontWeight: '800' },
  searchWrap: { flexDirection: 'row', alignItems: 'center', borderRadius: 14, paddingHorizontal: 14, borderWidth: 1, marginBottom: 14 },
  searchInput: { flex: 1, paddingVertical: 12, marginLeft: 10, fontSize: 15 },
  chip: { flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 14, paddingVertical: 9, borderRadius: 12 },
  chipText: { fontSize: 12, fontWeight: '600' },
  faqCard: { borderRadius: 16, borderWidth: 1, overflow: 'hidden' },
  faqItem: { paddingHorizontal: 16, paddingVertical: 15, borderBottomWidth: 1 },
  faqRow: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  faqDot: { width: 28, height: 28, borderRadius: 8, alignItems: 'center', justifyContent: 'center' },
  faqQ: { flex: 1, fontSize: 14, fontWeight: '700', lineHeight: 20 },
  faqAnswerWrap: { flexDirection: 'row', marginTop: 12, paddingLeft: 38, gap: 10 },
  faqAnswerBar: { width: 3, borderRadius: 2 },
  faqA: { flex: 1, fontSize: 13, lineHeight: 20 },
  voteRow: { flexDirection: 'row', alignItems: 'center', marginTop: 12, gap: 10 },
  voteLabel: { fontSize: 12 },
  voteBtns: { flexDirection: 'row', gap: 6 },
  voteBtn: { width: 32, height: 32, borderRadius: 8, alignItems: 'center', justifyContent: 'center', borderWidth: 1 },
  voteDone: { flexDirection: 'row', alignItems: 'center', gap: 4 },
  askBtnBottom: { flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 20, paddingVertical: 10, borderRadius: 20 },
  ctaCard: { borderRadius: 18, borderWidth: 1, padding: 24, alignItems: 'center', marginTop: 26 },
  ctaBtn: { flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 20, paddingVertical: 12, borderRadius: 10, marginTop: 12 },

  // Smart Search Dropdown
  dropdown: { position: 'absolute', top: 52, left: 0, right: 0, borderRadius: 16, borderWidth: 1, overflow: 'hidden', zIndex: 100 },
  didYouMean: { flexDirection: 'row', alignItems: 'center', gap: 8, paddingHorizontal: 14, paddingVertical: 10, borderBottomWidth: 1 },
  suggestionItem: { flexDirection: 'row', alignItems: 'center', gap: 10, paddingHorizontal: 14, paddingVertical: 11, borderBottomWidth: 1 },
  suggestionDot: { width: 24, height: 24, borderRadius: 7, alignItems: 'center', justifyContent: 'center' },
  askNovaBtn: { flexDirection: 'row', alignItems: 'center', gap: 10, paddingHorizontal: 14, paddingVertical: 12, borderTopWidth: 1 },
  askNovaIcon: { width: 28, height: 28, borderRadius: 8, alignItems: 'center', justifyContent: 'center' },
  aiAnswerBox: { paddingHorizontal: 14, paddingVertical: 14, borderTopWidth: 1 },

  // Trending Searches
  trendingWrap: { marginBottom: 12, borderWidth: 1, borderRadius: 14, padding: 10 },
  trendingChip: { flexDirection: 'row', alignItems: 'center', gap: 5, paddingHorizontal: 12, paddingVertical: 7, borderRadius: 12, borderWidth: 1 },

  // Voice Search
  micBtn: { width: 32, height: 32, borderRadius: 10, alignItems: 'center', justifyContent: 'center', marginLeft: 4 },
  recordingBar: { flexDirection: 'row', alignItems: 'center', gap: 8, paddingHorizontal: 14, paddingVertical: 10, borderRadius: 10, borderWidth: 1, marginBottom: 8 },
});

/* i18n-probe t('i18n.auto.probe') */
