import React from 'react';
import { View, Text, ScrollView, TouchableOpacity, TextInput, Platform, KeyboardAvoidingView, ActivityIndicator, Linking } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useTheme } from '../../context/ThemeContext';
import type { ThemeColors, ContactMode } from './helpTypes';

interface EmailFormProps {
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
  emailSending: boolean;
  emailSuccess: string | null;
  setEmailSuccess: (v: string | null) => void;
  setContactMode: (v: ContactMode) => void;
  handleSubmitEmail: () => void;
}

export default function EmailForm({ C, isWide, L, emailName, setEmailName, emailAddress, setEmailAddress, emailSubject, setEmailSubject, emailMessage, setEmailMessage, emailSending, emailSuccess, setEmailSuccess, setContactMode, handleSubmitEmail }: EmailFormProps) {
  const { colors } = useTheme();
  return (
    <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : 'height'}>
      <ScrollView showsVerticalScrollIndicator={false} contentContainerStyle={{ padding: 20, paddingBottom: 60 }}>
        {emailSuccess ? (
          <View style={{ backgroundColor: C.bgSoft, borderRadius: 16, padding: 28, alignItems: 'center', borderWidth: 1, borderColor: (globalThis as any).__alphaColor(C.success, '30') }} data-testid="email-success-banner" testID="email-success-banner">
            <View style={{ width: 64, height: 64, borderRadius: 32, backgroundColor: (globalThis as any).__alphaColor(C.success, '18'), alignItems: 'center', justifyContent: 'center', marginBottom: 16 }}>
              <Ionicons name="checkmark-circle" size={36} color={C.successText} />
            </View>
            <Text style={{ fontSize: 22, fontWeight: '800', color: C.text, marginBottom: 6 }}>{L('message_sent', 'Request Submitted')}</Text>
            <Text style={{ fontSize: 14, color: C.textSec, textAlign: 'center', lineHeight: 22 }}>
              Your ticket <Text style={{ fontWeight: '800', color: C.primary }}>{emailSuccess}</Text> has been created.{'\n'}Our team will respond within 24 hours.
            </Text>
            <View style={{ flexDirection: 'row', gap: 10, marginTop: 20 }}>
              <TouchableOpacity style={{ flex: 1, backgroundColor: C.primary, paddingVertical: 13, borderRadius: 10, alignItems: 'center' }}
                onPress={() => { setEmailSuccess(null); setContactMode('chat'); }} data-testid="email-success-ok-btn" testID="email-success-ok-btn">
                <Text style={{ color: colors.primaryText, fontWeight: '700', fontSize: 14 }}>Back to Chat</Text>
              </TouchableOpacity>
              <TouchableOpacity style={{ flex: 1, backgroundColor: C.card, paddingVertical: 13, borderRadius: 10, alignItems: 'center', borderWidth: 1, borderColor: C.border }}
                onPress={() => setEmailSuccess(null)} data-testid="email-new-request-btn" testID="email-new-request-btn">
                <Text style={{ color: C.text, fontWeight: '700', fontSize: 14 }}>New Request</Text>
              </TouchableOpacity>
            </View>
          </View>
        ) : (
          <View style={{ gap: 16 }}>
            {/* Form Header */}
            <View style={{ backgroundColor: C.card, borderRadius: 16, padding: 20, borderWidth: 1, borderColor: C.border, marginBottom: 2 }} data-testid="email-header" testID="email-header">
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 14 }}>
                <View style={{ width: 48, height: 48, borderRadius: 12, backgroundColor: C.bgSoft, borderWidth: 1, borderColor: C.border, alignItems: 'center', justifyContent: 'center' }}>
                  <Ionicons name="mail-unread" size={24} color={C.primary} />
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={{ fontSize: 20, fontWeight: '800', color: C.text, letterSpacing: -0.3 }}>{L('contact_support', 'Contact Support')}</Text>
                  <Text style={{ fontSize: 13, color: C.textSec, marginTop: 2 }}>{L('fill_form', 'Fill out the form below and our team will get back to you')}</Text>
                </View>
              </View>
              {/* Response time indicator */}
              <View style={{ flexDirection: 'row', gap: 12, marginTop: 16 }}>
                {[
                  { icon: 'flash', label: 'Avg. Response', value: '< 12 hours', color: C.successText },
                  { icon: 'shield-checkmark', label: 'Resolution Rate', value: '98%', color: C.violet },
                ].map(m => (
                  <View key={m.label} style={{ flex: 1, flexDirection: 'row', alignItems: 'center', gap: 8, backgroundColor: C.bgSoft, borderRadius: 10, padding: 10, borderWidth: 1, borderColor: C.border }}>
                    <Ionicons name={m.icon as any} size={16} color={m.color} />
                    <View>
                      <Text style={{ fontSize: 9, color: C.textMuted, fontWeight: '600', textTransform: 'uppercase', letterSpacing: 0.3 }}>{m.label}</Text>
                      <Text style={{ fontSize: 13, color: m.color, fontWeight: '800' }}>{m.value}</Text>
                    </View>
                  </View>
                ))}
              </View>
            </View>

            {/* The Form */}
            <View style={{ backgroundColor: C.card, borderRadius: 16, padding: 20, borderWidth: 1, borderColor: C.border }}>
              {/* Category selector */}
              <Text style={{ fontSize: 12, fontWeight: '700', color: C.textMuted, marginBottom: 8, textTransform: 'uppercase', letterSpacing: 0.5 }}>Request Category</Text>
              <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ marginBottom: 18 }} contentContainerStyle={{ gap: 8 }}>
                {[
                  { key: 'bug', icon: 'bug', label: 'Bug Report', color: colors.error },
                  { key: 'billing', icon: 'card', label: 'Billing', color: colors.warningText },
                  { key: 'feature', icon: 'bulb', label: 'Feature Request', color: colors.accent },
                  { key: 'account', icon: 'person', label: 'Account', color: colors.accent },
                  { key: 'other', icon: 'chatbox-ellipses', label: 'Other', color: colors.textMuted },
                ].map(cat => {
                  const isActive = emailSubject.toLowerCase().includes(cat.key);
                  return (
                    <TouchableOpacity accessibilityLabel={`Select category: ${cat.label}`} accessibilityRole="button"
                      key={cat.key}
                      onPress={() => setEmailSubject(cat.label)}
                      style={{
                        flexDirection: 'row', alignItems: 'center', gap: 6,
                        paddingHorizontal: 14, paddingVertical: 9, borderRadius: 10,
                        backgroundColor: isActive ? (globalThis as any).__alphaColor(cat.color, '15') : C.card,
                        borderWidth: 1.5, borderColor: isActive ? cat.color : C.border,
                      }}
                      data-testid={`support-cat-${cat.key}`} testID={`support-cat-${cat.key}`}
                    >
                      <Ionicons name={cat.icon as any} size={14} color={isActive ? cat.color : C.textMuted} />
                      <Text style={{ fontSize: 12, fontWeight: '700', color: isActive ? cat.color : C.textMuted }}>{cat.label}</Text>
                    </TouchableOpacity>
                  );
                })}
              </ScrollView>

              {/* Name & Email in a row on desktop */}
              <View style={[{ gap: 12, marginBottom: 16 }, isWide && { flexDirection: 'row' }]}>
                <View style={{ flex: 1 }}>
                  <Text style={{ fontSize: 12, fontWeight: '700', color: C.text, marginBottom: 6 }}>Full Name <Text style={{ color: C.error }}>*</Text></Text>
                  <View style={{ flexDirection: 'row', alignItems: 'center', backgroundColor: C.bgSoft, borderRadius: 12, paddingHorizontal: 12, borderWidth: 1, borderColor: C.border }}>
                    <Ionicons name="person-outline" size={16} color={C.textMuted} />
                    <TextInput data-testid="email-field-name" testID="email-field-name" style={{ flex: 1, color: C.text, paddingVertical: 12, marginLeft: 8, fontSize: 14 }}
                      placeholder="Your full name" placeholderTextColor={C.textMuted} value={emailName} onChangeText={setEmailName} />
                  </View>
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={{ fontSize: 12, fontWeight: '700', color: C.text, marginBottom: 6 }}>Email Address <Text style={{ color: C.error }}>*</Text></Text>
                  <View style={{ flexDirection: 'row', alignItems: 'center', backgroundColor: C.bgSoft, borderRadius: 12, paddingHorizontal: 12, borderWidth: 1, borderColor: C.border }}>
                    <Ionicons name="mail-outline" size={16} color={C.textMuted} />
                    <TextInput data-testid="email-field-email" testID="email-field-email" style={{ flex: 1, color: C.text, paddingVertical: 12, marginLeft: 8, fontSize: 14 }}
                      placeholder="you@example.com" placeholderTextColor={C.textMuted} value={emailAddress} onChangeText={setEmailAddress}
                      keyboardType="email-address" autoCapitalize="none" />
                  </View>
                </View>
              </View>

              {/* Subject */}
              <Text style={{ fontSize: 12, fontWeight: '700', color: C.text, marginBottom: 6 }}>Subject</Text>
              <View style={{ flexDirection: 'row', alignItems: 'center', backgroundColor: C.bgSoft, borderRadius: 12, paddingHorizontal: 12, borderWidth: 1, borderColor: C.border, marginBottom: 16 }}>
                <Ionicons name="document-text-outline" size={16} color={C.textMuted} />
                <TextInput data-testid="email-field-subject" testID="email-field-subject" style={{ flex: 1, color: C.text, paddingVertical: 12, marginLeft: 8, fontSize: 14 }}
                  placeholder="Brief description of your issue" placeholderTextColor={C.textMuted} value={emailSubject} onChangeText={setEmailSubject} />
              </View>

              {/* Priority indicator */}
              <Text style={{ fontSize: 12, fontWeight: '700', color: C.text, marginBottom: 8 }}>Priority Level</Text>
              <View style={{ flexDirection: 'row', gap: 8, marginBottom: 16 }}>
                {[
                  { key: 'low', label: 'Low', color: colors.successText, icon: 'arrow-down-circle' },
                  { key: 'medium', label: 'Medium', color: colors.warningText, icon: 'remove-circle' },
                  { key: 'high', label: 'High', color: colors.error, icon: 'arrow-up-circle' },
                ].map(p => {
                  const isActive = emailSubject.toLowerCase().includes(p.key) || (!emailSubject.toLowerCase().includes('low') && !emailSubject.toLowerCase().includes('high') && p.key === 'medium');
                  return (
                    <TouchableOpacity accessibilityLabel={`Set priority: ${p.label}`} accessibilityRole="button"
                      key={p.key}
                      style={{
                        flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 5,
                        paddingVertical: 9, borderRadius: 10,
                        backgroundColor: isActive ? (globalThis as any).__alphaColor(p.color, '12') : C.bgSoft,
                        borderWidth: 1.5, borderColor: isActive ? (globalThis as any).__alphaColor(p.color, '40') : C.border,
                      }}
                      data-testid={`priority-${p.key}`} testID={`priority-${p.key}`}
                    >
                      <Ionicons name={p.icon as any} size={14} color={isActive ? p.color : C.textMuted} />
                      <Text style={{ fontSize: 12, fontWeight: '700', color: isActive ? p.color : C.textMuted }}>{p.label}</Text>
                    </TouchableOpacity>
                  );
                })}
              </View>

              {/* Message */}
              <Text style={{ fontSize: 12, fontWeight: '700', color: C.text, marginBottom: 6 }}>Message <Text style={{ color: C.error }}>*</Text></Text>
              <View style={{ backgroundColor: C.bgSoft, borderRadius: 12, borderWidth: 1, borderColor: C.border, padding: 12, marginBottom: 20 }}>
                <TextInput data-testid="email-field-message" testID="email-field-message" style={{ color: C.text, minHeight: 120, textAlignVertical: 'top', fontSize: 14, lineHeight: 20 }}
                  placeholder="Please describe your issue in detail. Include any error messages, steps to reproduce, or relevant context that will help us resolve your request faster."
                  placeholderTextColor={C.textMuted} value={emailMessage} onChangeText={setEmailMessage} multiline />
                <View style={{ flexDirection: 'row', justifyContent: 'flex-end', marginTop: 8 }}>
                  <Text style={{ fontSize: 11, color: C.textMuted }}>{emailMessage.length}/2000</Text>
                </View>
              </View>

              {/* Submit */}
              <TouchableOpacity data-testid="email-submit-btn" testID="email-submit-btn" style={{ backgroundColor: C.primary, paddingVertical: 15, borderRadius: 10, alignItems: 'center', flexDirection: 'row', justifyContent: 'center', gap: 8, opacity: emailSending ? 0.6 : 1 }}
                onPress={handleSubmitEmail} disabled={emailSending}>
                {emailSending ? <ActivityIndicator color={colors.primaryText} /> : (
                  <>
                    <Ionicons name="send" size={18} color={colors.primaryText} />
                    <Text style={{ fontSize: 15, fontWeight: '800', color: colors.primaryText }}>{L('send_message', 'Submit Request')}</Text>
                  </>
                )}
              </TouchableOpacity>
            </View>

            {/* Direct contact */}
            <View style={{ backgroundColor: C.bgSoft, borderRadius: 14, padding: 16, borderWidth: 1, borderColor: C.border, flexDirection: 'row', alignItems: 'center', gap: 12, marginTop: 2 }}>
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
