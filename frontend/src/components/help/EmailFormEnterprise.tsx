import React from 'react';
import {
  View,
  Text,
  ScrollView,
  TouchableOpacity,
  TextInput,
  Platform,
  KeyboardAvoidingView,
  ActivityIndicator,
  Linking,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useTheme } from '../../context/ThemeContext';
import type {
  ContactMode,
  SupportAISuggestion,
  SupportAttachmentDraft,
  SupportCategory,
  SupportDuplicateHint,
  SupportFAQHint,
  SupportInsights,
  SupportPriority,
  ThemeColors,
} from './helpTypes';

interface EmailFormEnterpriseProps {
  C: ThemeColors;
  isWide: boolean;
  L: (key: string, fallback?: string) => string;
  emailName: string;
  setEmailName: (v: string) => void;
  emailAddress: string;
  setEmailAddress: (v: string) => void;
  emailSubject: string;
  setEmailSubject: (v: string) => void;
  emailMessage: string;
  setEmailMessage: (v: string) => void;
  emailCategory: SupportCategory;
  setEmailCategory: (v: SupportCategory) => void;
  emailPriority: SupportPriority;
  setEmailPriority: (v: SupportPriority) => void;
  emailAttachments: SupportAttachmentDraft[];
  addEmailAttachments: (files: FileList | File[]) => void;
  removeEmailAttachment: (id: string) => void;
  emailSending: boolean;
  emailSuccess: string | null;
  setEmailSuccess: (v: string | null) => void;
  emailSuggesting: boolean;
  emailInsights: SupportInsights | null;
  aiSuggestion: SupportAISuggestion | null;
  duplicateHints: SupportDuplicateHint[];
  faqHints: SupportFAQHint[];
  requestAiSupportSuggestion: (intent: 'draft' | 'improve_tone' | 'shorten' | 'expand') => void;
  setContactMode: (v: ContactMode) => void;
  handleSubmitEmail: () => void;
  onReuseLastContext?: () => void;
  reuseLastContextLoading?: boolean;
  reuseLastContextAvailable?: boolean;
  reuseLastContextMessage?: string | null;
  reuseLastContextHint?: string;
  successPrimaryCtaLabel?: string;
  onSuccessPrimaryAction?: () => void;
}

const CATEGORIES: { key: SupportCategory; icon: string; label: string }[] = [
  { key: 'technical', icon: 'construct-outline', label: 'Technical' },
  { key: 'billing', icon: 'card-outline', label: 'Billing' },
  { key: 'account', icon: 'person-outline', label: 'Account' },
  { key: 'feature_request', icon: 'bulb-outline', label: 'Feature Request' },
  { key: 'bug', icon: 'bug-outline', label: 'Bug' },
  { key: 'general', icon: 'chatbox-ellipses-outline', label: 'General' },
];

const PRIORITIES: { key: SupportPriority; icon: string; label: string }[] = [
  { key: 'low', icon: 'arrow-down-circle-outline', label: 'Low' },
  { key: 'medium', icon: 'remove-circle-outline', label: 'Medium' },
  { key: 'high', icon: 'arrow-up-circle-outline', label: 'High' },
  { key: 'critical', icon: 'alert-circle-outline', label: 'Critical' },
];

export default function EmailFormEnterprise({
  C,
  isWide,
  L,
  emailName,
  setEmailName,
  emailAddress,
  setEmailAddress,
  emailSubject,
  setEmailSubject,
  emailMessage,
  setEmailMessage,
  emailCategory,
  setEmailCategory,
  emailPriority,
  setEmailPriority,
  emailAttachments,
  addEmailAttachments,
  removeEmailAttachment,
  emailSending,
  emailSuccess,
  setEmailSuccess,
  emailSuggesting,
  emailInsights,
  aiSuggestion,
  duplicateHints,
  faqHints,
  requestAiSupportSuggestion,
  setContactMode,
  handleSubmitEmail,
  onReuseLastContext,
  reuseLastContextLoading = false,
  reuseLastContextAvailable = false,
  reuseLastContextMessage,
  reuseLastContextHint,
  successPrimaryCtaLabel,
  onSuccessPrimaryAction,
}: EmailFormEnterpriseProps) {
  const { colors } = useTheme();
  const fileInputRef = React.useRef<HTMLInputElement | null>(null);

  const openAttachmentPicker = () => {
    if (Platform.OS !== 'web') return;
    fileInputRef.current?.click();
  };

  const onAttachmentChange = (event: any) => {
    const files = event?.target?.files;
    if (!files) return;
    addEmailAttachments(files);
    if (event?.target) event.target.value = '';
  };

  const formatHours = (value: number | null) => {
    if (value === null || Number.isNaN(value)) return 'N/A';
    return `${value.toFixed(1)}h`;
  };

  const formatDate = (value?: string) => {
    if (!value) return 'N/A';
    try {
      return new Date(value).toLocaleString();
    } catch {
      return value;
    }
  };

  const hasReuseContextSection = Boolean(onReuseLastContext || reuseLastContextHint || reuseLastContextMessage);
  const reuseDisabled = !onReuseLastContext || !reuseLastContextAvailable || reuseLastContextLoading;

  return (
    <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : 'height'}>
      <ScrollView showsVerticalScrollIndicator={false} contentContainerStyle={{ padding: 20, paddingBottom: 64 }}>
        {emailSuccess ? (
          <View
            style={{ backgroundColor: C.bgSoft, borderRadius: 16, padding: 28, alignItems: 'center', borderWidth: 1, borderColor: (globalThis as any).__alphaColor(C.success, '30') }}
            data-testid="email-success-banner"
            testID="email-success-banner"
          >
            <View style={{ width: 64, height: 64, borderRadius: 32, backgroundColor: (globalThis as any).__alphaColor(C.success, '18'), alignItems: 'center', justifyContent: 'center', marginBottom: 16 }}>
              <Ionicons name="checkmark-circle" size={36} color={C.successText} />
            </View>
            <Text style={{ fontSize: 22, fontWeight: '800', color: C.text, marginBottom: 6 }}>{L('message_sent', 'Request Submitted')}</Text>
            <Text style={{ fontSize: 14, color: C.textSec, textAlign: 'center', lineHeight: 22 }}>
              Your ticket <Text style={{ fontWeight: '800', color: C.primary }}>{emailSuccess}</Text> has been created.{"\n"}
              You can track updates in My Tickets.
            </Text>
            <View style={{ flexDirection: 'row', gap: 10, marginTop: 20 }}>
              <TouchableOpacity accessibilityLabel="Email success ok button"
                style={{ flex: 1, backgroundColor: C.primary, paddingVertical: 13, borderRadius: 10, alignItems: 'center' }}
                onPress={() => {
                  setEmailSuccess(null);
                  if (onSuccessPrimaryAction) {
                    onSuccessPrimaryAction();
                    return;
                  }
                  setContactMode('chat');
                }}
                data-testid="email-success-ok-btn"
                testID="email-success-ok-btn"
              >
                <Text style={{ color: colors.primaryText, fontWeight: '700', fontSize: 14 }}>
                  {successPrimaryCtaLabel || 'Back to Chat'}
                </Text>
              </TouchableOpacity>
              <TouchableOpacity
                style={{ flex: 1, backgroundColor: C.card, paddingVertical: 13, borderRadius: 10, alignItems: 'center', borderWidth: 1, borderColor: C.border }}
                onPress={() => setEmailSuccess(null)}
                data-testid="email-new-request-btn"
                testID="email-new-request-btn"
              >
                <Text style={{ color: C.text, fontWeight: '700', fontSize: 14 }}>New Request</Text>
              </TouchableOpacity>
            </View>
          </View>
        ) : (
          <View style={{ gap: 16 }}>
            <View style={{ backgroundColor: C.card, borderRadius: 16, padding: 20, borderWidth: 1, borderColor: C.border }} data-testid="email-header" testID="email-header">
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 14 }}>
                <View style={{ width: 48, height: 48, borderRadius: 12, backgroundColor: C.bgSoft, borderWidth: 1, borderColor: C.border, alignItems: 'center', justifyContent: 'center' }}>
                  <Ionicons name="mail-unread" size={24} color={C.primary} />
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={{ fontSize: 20, fontWeight: '800', color: C.text, letterSpacing: -0.3 }}>{L('contact_support', 'Contact Support')}</Text>
                  <Text style={{ fontSize: 13, color: C.textSec, marginTop: 2 }}>{L('fill_form', 'Submit a structured request or use AI to refine your draft')}</Text>
                </View>
              </View>

              <View style={{ flexDirection: isWide ? 'row' : 'column', gap: 10, marginTop: 16 }} data-testid="email-insights-row" testID="email-insights-row">
                <View style={{ flex: 1, flexDirection: 'row', alignItems: 'center', gap: 8, backgroundColor: C.bgSoft, borderRadius: 10, padding: 10, borderWidth: 1, borderColor: C.border }} data-testid="email-insight-open-tickets" testID="email-insight-open-tickets">
                  <Ionicons name="albums-outline" size={16} color={C.primary} />
                  <View>
                    <Text style={{ fontSize: 10, color: C.textMuted, fontWeight: '700' }}>Open Tickets</Text>
                    <Text style={{ fontSize: 14, color: C.text, fontWeight: '800' }}>{emailInsights?.open_tickets ?? 0}</Text>
                  </View>
                </View>
                <View style={{ flex: 1, flexDirection: 'row', alignItems: 'center', gap: 8, backgroundColor: C.bgSoft, borderRadius: 10, padding: 10, borderWidth: 1, borderColor: C.border }} data-testid="email-insight-avg-response" testID="email-insight-avg-response">
                  <Ionicons name="time-outline" size={16} color={C.successText} />
                  <View>
                    <Text style={{ fontSize: 10, color: C.textMuted, fontWeight: '700' }}>Avg Response</Text>
                    <Text style={{ fontSize: 14, color: C.text, fontWeight: '800' }}>{formatHours(emailInsights?.avg_response_hours ?? null)}</Text>
                  </View>
                </View>
                <View style={{ flex: 1, flexDirection: 'row', alignItems: 'center', gap: 8, backgroundColor: C.bgSoft, borderRadius: 10, padding: 10, borderWidth: 1, borderColor: C.border }} data-testid="email-insight-last-ticket" testID="email-insight-last-ticket">
                  <Ionicons name="receipt-outline" size={16} color={C.violet} />
                  <View style={{ flex: 1 }}>
                    <Text style={{ fontSize: 10, color: C.textMuted, fontWeight: '700' }}>Last Ticket</Text>
                    <Text numberOfLines={1} style={{ fontSize: 12, color: C.text, fontWeight: '800' }}>{emailInsights?.last_ticket?.ticket_id || '—'}</Text>
                  </View>
                </View>
              </View>

              {hasReuseContextSection ? (
                <View style={{ marginTop: 12, borderTopWidth: 1, borderTopColor: C.border, paddingTop: 12 }} data-testid="email-reuse-context-section" testID="email-reuse-context-section">
                  <TouchableOpacity accessibilityLabel="Email reuse last context button"
                    onPress={() => onReuseLastContext?.()}
                    disabled={reuseDisabled}
                    style={{
                      borderRadius: 10,
                      borderWidth: 1,
                      borderColor: (globalThis as any).__alphaColor(reuseDisabled ? C.border : C.primary, '45'),
                      backgroundColor: (globalThis as any).__alphaColor(reuseDisabled ? C.bgSoft : C.primary, '10'),
                      paddingVertical: 10,
                      paddingHorizontal: 12,
                      flexDirection: 'row',
                      alignItems: 'center',
                      justifyContent: 'center',
                      gap: 8,
                    }}
                    data-testid="email-reuse-last-context-btn"
                    testID="email-reuse-last-context-btn"
                  >
                    {reuseLastContextLoading ? (
                      <ActivityIndicator size="small" color={C.primary} />
                    ) : (
                      <Ionicons name="refresh-circle-outline" size={16} color={reuseDisabled ? C.textMuted : C.primary} />
                    )}
                    <Text style={{ fontSize: 12, fontWeight: '800', color: reuseDisabled ? C.textMuted : C.primary }}>
                      Reuse Last Ticket Context
                    </Text>
                  </TouchableOpacity>

                  <Text style={{ marginTop: 8, fontSize: 11, color: C.textMuted }} data-testid="email-reuse-last-context-message" testID="email-reuse-last-context-message">
                    {reuseLastContextMessage || reuseLastContextHint || 'Prefill from your latest resolved support ticket.'}
                  </Text>
                </View>
              ) : null}
            </View>

            <View style={{ backgroundColor: C.card, borderRadius: 16, padding: 20, borderWidth: 1, borderColor: C.border }}>
              <Text style={{ fontSize: 12, fontWeight: '700', color: C.textMuted, marginBottom: 8, textTransform: 'uppercase', letterSpacing: 0.5 }}>Request Category</Text>
              <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ marginBottom: 18 }} contentContainerStyle={{ gap: 8 }}>
                {CATEGORIES.map((cat) => {
                  const isActive = emailCategory === cat.key;
                  return (
                    <TouchableOpacity
                      key={cat.key}
                      accessibilityLabel={`Select category: ${cat.label}`}
                      accessibilityRole="button"
                      onPress={() => setEmailCategory(cat.key)}
                      style={{
                        flexDirection: 'row',
                        alignItems: 'center',
                        gap: 6,
                        paddingHorizontal: 14,
                        paddingVertical: 9,
                        borderRadius: 10,
                        backgroundColor: isActive ? (globalThis as any).__alphaColor(C.primary, '15') : C.card,
                        borderWidth: 1.5,
                        borderColor: isActive ? C.primary : C.border,
                      }}
                      data-testid={`support-cat-${cat.key}`}
                      testID={`support-cat-${cat.key}`}
                    >
                      <Ionicons name={cat.icon as any} size={14} color={isActive ? C.primary : C.textMuted} />
                      <Text style={{ fontSize: 12, fontWeight: '700', color: isActive ? C.primary : C.textMuted }}>{cat.label}</Text>
                    </TouchableOpacity>
                  );
                })}
              </ScrollView>

              <View style={[{ gap: 12, marginBottom: 16 }, isWide && { flexDirection: 'row' }]}>
                <View style={{ flex: 1 }}>
                  <Text style={{ fontSize: 12, fontWeight: '700', color: C.text, marginBottom: 6 }}>Full Name <Text style={{ color: C.error }}>*</Text></Text>
                  <View style={{ flexDirection: 'row', alignItems: 'center', backgroundColor: C.bgSoft, borderRadius: 12, paddingHorizontal: 12, borderWidth: 1, borderColor: C.border }}>
                    <Ionicons name="person-outline" size={16} color={C.textMuted} />
                    <TextInput data-testid="email-field-name" testID="email-field-name" style={{ flex: 1, color: C.text, paddingVertical: 12, marginLeft: 8, fontSize: 14 }} placeholder="Your full name" placeholderTextColor={C.textMuted} value={emailName} onChangeText={setEmailName} />
                  </View>
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={{ fontSize: 12, fontWeight: '700', color: C.text, marginBottom: 6 }}>Email Address <Text style={{ color: C.error }}>*</Text></Text>
                  <View style={{ flexDirection: 'row', alignItems: 'center', backgroundColor: C.bgSoft, borderRadius: 12, paddingHorizontal: 12, borderWidth: 1, borderColor: C.border }}>
                    <Ionicons name="mail-outline" size={16} color={C.textMuted} />
                    <TextInput data-testid="email-field-email" testID="email-field-email" style={{ flex: 1, color: C.text, paddingVertical: 12, marginLeft: 8, fontSize: 14 }} placeholder="you@example.com" placeholderTextColor={C.textMuted} value={emailAddress} onChangeText={setEmailAddress} keyboardType="email-address" autoCapitalize="none" />
                  </View>
                </View>
              </View>

              <Text style={{ fontSize: 12, fontWeight: '700', color: C.text, marginBottom: 6 }}>Subject</Text>
              <View style={{ flexDirection: 'row', alignItems: 'center', backgroundColor: C.bgSoft, borderRadius: 12, paddingHorizontal: 12, borderWidth: 1, borderColor: C.border, marginBottom: 16 }}>
                <Ionicons name="document-text-outline" size={16} color={C.textMuted} />
                <TextInput data-testid="email-field-subject" testID="email-field-subject" style={{ flex: 1, color: C.text, paddingVertical: 12, marginLeft: 8, fontSize: 14 }} placeholder="Brief description of your issue" placeholderTextColor={C.textMuted} value={emailSubject} onChangeText={setEmailSubject} />
              </View>

              <Text style={{ fontSize: 12, fontWeight: '700', color: C.text, marginBottom: 8 }}>Priority Level</Text>
              <View style={{ flexDirection: isWide ? 'row' : 'column', gap: 8, marginBottom: 16 }}>
                {PRIORITIES.map((priority) => {
                  const isActive = emailPriority === priority.key;
                  return (
                    <TouchableOpacity
                      key={priority.key}
                      accessibilityLabel={`Set priority: ${priority.label}`}
                      accessibilityRole="button"
                      onPress={() => setEmailPriority(priority.key)}
                      style={{
                        flex: 1,
                        flexDirection: 'row',
                        alignItems: 'center',
                        justifyContent: 'center',
                        gap: 5,
                        paddingVertical: 9,
                        borderRadius: 10,
                        backgroundColor: isActive ? (globalThis as any).__alphaColor(C.primary, '12') : C.bgSoft,
                        borderWidth: 1.5,
                        borderColor: isActive ? (globalThis as any).__alphaColor(C.primary, '40') : C.border,
                      }}
                      data-testid={`priority-${priority.key}`}
                      testID={`priority-${priority.key}`}
                    >
                      <Ionicons name={priority.icon as any} size={14} color={isActive ? C.primary : C.textMuted} />
                      <Text style={{ fontSize: 12, fontWeight: '700', color: isActive ? C.primary : C.textMuted }}>{priority.label}</Text>
                    </TouchableOpacity>
                  );
                })}
              </View>

              <Text style={{ fontSize: 12, fontWeight: '700', color: C.text, marginBottom: 6 }}>Message <Text style={{ color: C.error }}>*</Text></Text>
              <View style={{ backgroundColor: C.bgSoft, borderRadius: 12, borderWidth: 1, borderColor: C.border, padding: 12, marginBottom: 20 }}>
                <TextInput
                  data-testid="email-field-message"
                  testID="email-field-message"
                  style={{ color: C.text, minHeight: 120, textAlignVertical: 'top', fontSize: 14, lineHeight: 20 }}
                  placeholder="Please describe your issue in detail. Include context and what outcome you need."
                  placeholderTextColor={C.textMuted}
                  value={emailMessage}
                  onChangeText={setEmailMessage}
                  multiline
                />
                <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginTop: 8 }}>
                  <Text style={{ fontSize: 11, color: C.textMuted }}>Last ticket: {formatDate(emailInsights?.last_ticket?.created_at)}</Text>
                  <Text style={{ fontSize: 11, color: C.textMuted }}>{emailMessage.length}/4000</Text>
                </View>
              </View>

              <View style={{ backgroundColor: C.bgSoft, borderRadius: 12, borderWidth: 1, borderColor: C.border, padding: 12, marginBottom: 16 }} data-testid="email-ai-suggest-panel" testID="email-ai-suggest-panel">
                <Text style={{ fontSize: 13, fontWeight: '800', color: C.text, marginBottom: 6 }}>AI Suggest Reply</Text>
                <Text style={{ fontSize: 12, color: C.textSec, marginBottom: 10 }}>Uses platform data only: your form context, recent tickets, and FAQ hints.</Text>

                <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
                  <TouchableOpacity onPress={() => requestAiSupportSuggestion('draft')} data-testid="email-ai-suggest-draft" testID="email-ai-suggest-draft" style={{ backgroundColor: C.primary, borderRadius: 10, paddingVertical: 9, paddingHorizontal: 12, flexDirection: 'row', alignItems: 'center', gap: 6, opacity: emailSuggesting ? 0.7 : 1 }}>
                    {emailSuggesting ? <ActivityIndicator color={colors.primaryText} size="small" /> : <Ionicons name="sparkles-outline" size={14} color={colors.primaryText} />}
                    <Text style={{ color: colors.primaryText, fontSize: 12, fontWeight: '800' }}>Suggest Draft</Text>
                  </TouchableOpacity>
                  <TouchableOpacity onPress={() => requestAiSupportSuggestion('improve_tone')} data-testid="email-ai-suggest-tone" testID="email-ai-suggest-tone" style={{ borderRadius: 10, paddingVertical: 9, paddingHorizontal: 12, borderWidth: 1, borderColor: C.border }}>
                    <Text style={{ color: C.text, fontSize: 12, fontWeight: '700' }}>Improve Tone</Text>
                  </TouchableOpacity>
                  <TouchableOpacity onPress={() => requestAiSupportSuggestion('shorten')} data-testid="email-ai-suggest-shorten" testID="email-ai-suggest-shorten" style={{ borderRadius: 10, paddingVertical: 9, paddingHorizontal: 12, borderWidth: 1, borderColor: C.border }}>
                    <Text style={{ color: C.text, fontSize: 12, fontWeight: '700' }}>Shorten</Text>
                  </TouchableOpacity>
                  <TouchableOpacity onPress={() => requestAiSupportSuggestion('expand')} data-testid="email-ai-suggest-expand" testID="email-ai-suggest-expand" style={{ borderRadius: 10, paddingVertical: 9, paddingHorizontal: 12, borderWidth: 1, borderColor: C.border }}>
                    <Text style={{ color: C.text, fontSize: 12, fontWeight: '700' }}>Expand</Text>
                  </TouchableOpacity>
                </View>

                {aiSuggestion ? (
                  <View style={{ marginTop: 10, borderTopWidth: 1, borderTopColor: C.border, paddingTop: 10 }} data-testid="email-ai-suggestion-meta" testID="email-ai-suggestion-meta">
                    <Text style={{ fontSize: 11, color: C.textMuted, fontWeight: '600' }}>
                      Source: {aiSuggestion.source || 'deterministic'} • Confidence: {Math.round((aiSuggestion.confidence || 0) * 100)}%
                    </Text>
                  </View>
                ) : null}
              </View>

              <View style={{ marginBottom: 16 }}>
                <Text style={{ fontSize: 12, fontWeight: '700', color: C.text, marginBottom: 6 }}>Attachments (optional)</Text>
                <TouchableOpacity onPress={openAttachmentPicker} data-testid="email-attach-button" testID="email-attach-button" style={{ borderWidth: 1, borderColor: C.border, backgroundColor: C.bgSoft, borderRadius: 12, paddingVertical: 11, paddingHorizontal: 12, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8 }}>
                  <Ionicons name="attach-outline" size={16} color={C.textSec} />
                  <Text style={{ color: C.text, fontSize: 13, fontWeight: '700' }}>Add up to 3 files (max 5MB each)</Text>
                </TouchableOpacity>
                {Platform.OS === 'web' ? (
                  // @ts-ignore react-native-web supports input
                  <input accessibilityLabel="Text input"
                    ref={fileInputRef}
                    type="file"
                    multiple
                    accept=".png,.jpg,.jpeg,.webp,.gif,.pdf,.txt,.csv,.json"
                    style={{ display: 'none' }}
                    onChange={onAttachmentChange}
                    data-testid="email-attachment-input"
                  />
                ) : null}

                {emailAttachments.length > 0 ? (
                  <View style={{ marginTop: 10, gap: 8 }} data-testid="email-attachment-list" testID="email-attachment-list">
                    {emailAttachments.map((att) => (
                      <View key={att.id} style={{ borderWidth: 1, borderColor: C.border, borderRadius: 10, padding: 10, backgroundColor: C.card, flexDirection: 'row', alignItems: 'center', gap: 8 }} data-testid={`email-attachment-item-${att.id}`} testID={`email-attachment-item-${att.id}`}>
                        <Ionicons name="document-attach-outline" size={15} color={C.primary} />
                        <View style={{ flex: 1 }}>
                          <Text numberOfLines={1} style={{ color: C.text, fontSize: 12, fontWeight: '700' }}>{att.name}</Text>
                          <Text style={{ color: C.textMuted, fontSize: 11 }}>{(att.size / 1024).toFixed(1)} KB</Text>
                        </View>
                        <TouchableOpacity onPress={() => removeEmailAttachment(att.id)} data-testid={`email-attachment-remove-${att.id}`} testID={`email-attachment-remove-${att.id}`}>
                          <Ionicons name="close-circle" size={18} color={C.textMuted} />
                        </TouchableOpacity>
                      </View>
                    ))}
                  </View>
                ) : null}
              </View>

              {duplicateHints.length > 0 ? (
                <View style={{ borderWidth: 1, borderColor: (globalThis as any).__alphaColor(C.warning, '55'), backgroundColor: (globalThis as any).__alphaColor(C.warning, '10'), borderRadius: 12, padding: 12, marginBottom: 14 }} data-testid="email-duplicate-hints" testID="email-duplicate-hints">
                  <Text style={{ color: C.text, fontSize: 12, fontWeight: '800', marginBottom: 6 }}>Possible existing tickets</Text>
                  {duplicateHints.map((item) => (
                    <View key={item.ticket_id} style={{ marginBottom: 6 }} data-testid={`email-duplicate-hint-${item.ticket_id}`} testID={`email-duplicate-hint-${item.ticket_id}`}>
                      <Text style={{ color: C.text, fontSize: 12, fontWeight: '700' }}>{item.ticket_id} • {item.status}</Text>
                      <Text style={{ color: C.textSec, fontSize: 11 }} numberOfLines={2}>{item.subject}</Text>
                      <Text style={{ color: C.textMuted, fontSize: 10 }}>Similarity {Math.round((item.similarity || 0) * 100)}% • {formatDate(item.created_at)}</Text>
                    </View>
                  ))}
                </View>
              ) : null}

              {faqHints.length > 0 ? (
                <View style={{ borderWidth: 1, borderColor: C.border, backgroundColor: C.bgSoft, borderRadius: 12, padding: 12, marginBottom: 18 }} data-testid="email-faq-hints" testID="email-faq-hints">
                  <Text style={{ color: C.text, fontSize: 12, fontWeight: '800', marginBottom: 6 }}>Relevant FAQ hints</Text>
                  {faqHints.map((hint, idx) => (
                    <View key={`${hint.question}-${idx}`} style={{ marginBottom: 7 }} data-testid={`email-faq-hint-${idx}`} testID={`email-faq-hint-${idx}`}>
                      <Text style={{ color: C.text, fontSize: 12, fontWeight: '700' }}>{hint.question}</Text>
                      <Text style={{ color: C.textSec, fontSize: 11 }} numberOfLines={3}>{hint.answer}</Text>
                    </View>
                  ))}
                </View>
              ) : null}

              <TouchableOpacity data-testid="email-submit-btn" testID="email-submit-btn" style={{ backgroundColor: C.primary, paddingVertical: 15, borderRadius: 10, alignItems: 'center', flexDirection: 'row', justifyContent: 'center', gap: 8, opacity: emailSending ? 0.6 : 1 }} onPress={handleSubmitEmail} disabled={emailSending}>
                {emailSending ? (
                  <ActivityIndicator color={colors.primaryText} />
                ) : (
                  <>
                    <Ionicons name="send" size={18} color={colors.primaryText} />
                    <Text style={{ fontSize: 15, fontWeight: '800', color: colors.primaryText }}>{L('send_message', 'Submit Request')}</Text>
                  </>
                )}
              </TouchableOpacity>
            </View>

            <View style={{ backgroundColor: C.bgSoft, borderRadius: 14, padding: 16, borderWidth: 1, borderColor: C.border, flexDirection: 'row', alignItems: 'center', gap: 12 }}>
              <View style={{ width: 36, height: 36, borderRadius: 10, backgroundColor: (globalThis as any).__alphaColor(C.primary, '12'), alignItems: 'center', justifyContent: 'center' }}>
                <Ionicons name="mail" size={18} color={C.primary} />
              </View>
              <View style={{ flex: 1 }}>
                <Text style={{ fontSize: 12, color: C.textMuted, fontWeight: '500' }}>Or email us directly</Text>
                <TouchableOpacity onPress={() => Linking.openURL('mailto:support@realaicoach.app')} data-testid="direct-email-link" testID="direct-email-link">
                  <Text style={{ fontSize: 14, fontWeight: '700', color: C.primary }}>support@realaicoach.app</Text>
                </TouchableOpacity>
              </View>
              <Ionicons name="open-outline" size={16} color={C.textMuted} />
            </View>
          </View>
        )}
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

/* i18n-probe t('i18n.auto.probe') */
