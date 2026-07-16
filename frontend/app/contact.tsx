import React, { useEffect, useMemo, useState } from 'react';
import { View, Text, TouchableOpacity, useWindowDimensions, Platform, ScrollView, Image, TextInput, Alert } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useLocalSearchParams, useRouter } from 'expo-router';
import Footer from '../src/components/Footer';
import api from '../src/services/api';
import { useTheme } from '../src/context/ThemeContext';
import { useAuth } from '../src/context/AuthContext';
import { useTranslation } from '../src/hooks/useTranslation';
import { buildAnalyticsSource } from '../src/utils/buildAnalyticsSource';
import { useLanguage } from '../src/i18n/LanguageContext';

const blur = Platform.OS === 'web' ? ({ backdropFilter: 'blur(18px)', WebkitBackdropFilter: 'blur(18px)' } as any) : {};

const INTENTS = [
  { key: 'sales', label: 'Sales', icon: 'briefcase-outline', sla: '24h response', note: 'Pricing, enterprise plans, and deployment fit.' },
  { key: 'support', label: 'Support', icon: 'help-circle-outline', sla: '4h priority routing', note: 'Product help, account issues, and troubleshooting.' },
  { key: 'partnerships', label: 'Partnerships', icon: 'people-outline', sla: '48h response', note: 'Co-marketing, integrations, and strategic alliances.' },
  { key: 'press', label: 'Press', icon: 'newspaper-outline', sla: '24h media desk', note: 'Media requests, interviews, and spokesperson access.' },
] as const;

const TEAM_SIZE_OPTIONS = ['1-10', '11-50', '51-200', '201-1000', '1000+'];
const PRIORITY_OPTIONS = ['low', 'medium', 'high', 'urgent'] as const;
const REGION_OPTIONS = ['North America', 'Europe', 'Africa', 'Middle East', 'Asia-Pacific', 'LATAM'];
const TIMELINE_OPTIONS = ['Immediate', 'This month', 'Next quarter', 'Researching'];
const BUDGET_OPTIONS = ['<$5k', '$5k-$20k', '$20k-$75k', '$75k+'];

function ContactNav() {
  const { t } = useLanguage();
  const router = useRouter();
  const { width } = useWindowDimensions();
  const { colors: palette, darkMode } = useTheme();
  const m = width < 640;
  const navBg = darkMode ? 'rgba(5,10,20,0.85)' : 'rgba(248,250,252,0.92)';

  return (
    <View
      style={[
        {
          backgroundColor: navBg,
          borderBottomWidth: 1,
          borderBottomColor: palette.border,
          paddingHorizontal: m ? 16 : 28,
          paddingVertical: 14,
          flexDirection: 'row',
          alignItems: 'center',
          justifyContent: 'space-between',
        },
        Platform.OS === 'web' ? ({ position: 'sticky' as any, top: 0, zIndex: 100, ...blur }) : {},
      ]}
      data-testid="contact-nav"
      testID="contact-nav"
    >
      <TouchableOpacity
        onPress={() => router.push('/welcome')}
        style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}
        data-testid="contact-nav-logo"
        testID="contact-nav-logo"
      >
        <Image
          source={Platform.OS === 'web' ? { uri: '/api/static/images/logo.png' } : require('../assets/images/logo.png')}
          style={{ width: m ? 26 : 30, height: m ? 26 : 30, borderRadius: 7 }}
          resizeMode="contain"
        />
        <Text style={{ color: palette.text, fontSize: m ? 15 : 17, fontWeight: '800', letterSpacing: -0.3 }}>Real<Text style={{ color: palette.accent }}>AI</Text>Coach</Text>
      </TouchableOpacity>

      <View style={{ flexDirection: 'row', alignItems: 'center', gap: m ? 8 : 12 }}>
        <TouchableOpacity
          onPress={() => router.push('/welcome')}
          style={{
            flexDirection: 'row',
            alignItems: 'center',
            gap: 4,
            paddingHorizontal: 12,
            paddingVertical: 7,
            borderRadius: 8,
            borderWidth: 1,
            borderColor: palette.border,
          }}
          data-testid="contact-nav-back"
          testID="contact-nav-back"
        >
          <Ionicons name="arrow-back" size={14} color={palette.textSec} />
          {!m ? <Text style={{ color: palette.textSec, fontSize: 13, fontWeight: '600' }}>{t("admin.tosManagementPanel.auto.text.007")}</Text> : null}
        </TouchableOpacity>
        <TouchableOpacity
          onPress={() => router.push('/auth/register')}
          style={{ paddingHorizontal: m ? 14 : 18, paddingVertical: 8, borderRadius: 8, backgroundColor: palette.accent }}
          data-testid="contact-nav-signup"
          testID="contact-nav-signup"
        >
          <Text style={{ color: palette.primaryText, fontSize: 13, fontWeight: '700' }}>{t("adopt.sign.up.free")}</Text>
        </TouchableOpacity>
      </View>
    </View>
  );
}

export default function ContactPage() {
  const { t } = useLanguage();
  const { width } = useWindowDimensions();
  const { context, intent: intentParam } = useLocalSearchParams();
  const supportContext = Array.isArray(context) ? context[0] : context;
  const { colors } = useTheme();
  const { user } = useAuth();
  const { tx } = useTranslation();

  const C = useMemo(() => ({
    primary: colors.primary,
    bg: colors.bg,
    bgSoft: colors.bgSoft,
    card: colors.card,
    text: colors.text,
    textSec: colors.textSec,
    textMuted: colors.textMuted,
    border: colors.border,
    success: colors.success,
    warning: colors.warning,
    error: colors.error,
    violet: colors.purple,
  }), [colors]);

  const isWide = width >= 1024;
  const isTablet = width >= 640 && width < 1024;
  const isMobile = width < 640;

  const rawIntent = Array.isArray(intentParam) ? intentParam[0] : intentParam;
  const normalizedIntent = String(rawIntent || '').trim().toLowerCase();
  const initialIntent = (INTENTS.find((item) => item.key === normalizedIntent)?.key || 'support') as (typeof INTENTS)[number]['key'];

  const [intent, setIntent] = useState<(typeof INTENTS)[number]['key']>(initialIntent);
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [subject, setSubject] = useState('');
  const [company, setCompany] = useState('');
  const [website, setWebsite] = useState('');
  const [teamSize, setTeamSize] = useState('11-50');
  const [priority, setPriority] = useState<(typeof PRIORITY_OPTIONS)[number]>('medium');
  const [region, setRegion] = useState('North America');
  const [timeline, setTimeline] = useState('This month');
  const [budgetRange, setBudgetRange] = useState('$5k-$20k');
  const [useCase, setUseCase] = useState('');
  const [message, setMessage] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [successRef, setSuccessRef] = useState('');
  const [successMessage, setSuccessMessage] = useState('');
  const contactCommandCenterSource = useMemo(() => buildAnalyticsSource('contact', 'command', 'center'), []);

  useEffect(() => {
    if (!name && user?.name) setName(user.name);
    if (!email && user?.email) setEmail(user.email);
  }, [email, name, user?.email, user?.name]);

  useEffect(() => {
    if (supportContext === 'login-lockout') {
      setIntent('support');
      setPriority('high');
      setSubject((prev) => prev || tx('contact.lockout.subject', 'Account access issue after login lockout'));
      setMessage((prev) => prev || tx('contact.lockout.message', "I'm locked out after failed sign-in attempts and need help regaining access."));
    }
  }, [supportContext, tx]);

  const activeIntent = INTENTS.find((item) => item.key === intent) || INTENTS[1];

  const recommendationByIntent: Record<(typeof INTENTS)[number]['key'], string> = {
    sales: tx('contact.recommendation.sales', 'Attach expected rollout timeline and team size for the fastest proposal turn-around.'),
    support: tx('contact.recommendation.support', 'Include the exact error text or screenshot details to speed up triage.'),
    partnerships: tx('contact.recommendation.partnerships', 'Share your audience profile and success metrics for strategic fit checks.'),
    press: tx('contact.recommendation.press', 'Include publication deadline and interview format for priority handling.'),
  };

  const validate = () => {
    if (!name.trim() || !email.trim() || !message.trim()) {
      return tx('contact.validation.required', 'Name, work email, and message are required.');
    }
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim())) {
      return tx('contact.validation.email', 'Please enter a valid work email.');
    }
    if (message.trim().length < 20) {
      return tx('contact.validation.messageLength', 'Please add a bit more detail (at least 20 characters).');
    }
    return '';
  };

  const submitContact = async () => {
    const err = validate();
    if (err) {
      if (Platform.OS === 'web') window.alert(err);
      else Alert.alert('Validation', err);
      return;
    }

    setSubmitting(true);
    setSuccessRef('');
    setSuccessMessage('');
    try {
      const response = await api.post('/contact/submit', {
        intent,
        name: name.trim(),
        email: email.trim(),
        subject: subject.trim(),
        company: company.trim(),
        team_size: teamSize,
        use_case: useCase.trim(),
        message: message.trim(),
        priority,
        timeline,
        budget_range: intent === 'sales' ? budgetRange : '',
        website: website.trim(),
        region,
        context: String(supportContext || '').trim(),
        source: contactCommandCenterSource,
      }, { silentLoading: true });

      if (response?.data?.success) {
        setSuccessRef(String(response.data.reference_id || ''));
        setSuccessMessage(String(response.data.message || tx('contact.success.default', 'Request received successfully.')));
        setSubject('');
        setUseCase('');
        setMessage('');
      }
    } catch (error: any) {
      const msg = String(error?.response?.data?.detail || tx('contact.error.submit', 'Could not submit right now. Please try again.'));
      if (Platform.OS === 'web') window.alert(msg);
      else Alert.alert(tx('contact.error.submitTitle', 'Submission failed'), msg);
    } finally {
      setSubmitting(false);
    }
  };

  const infoCards = [
    { icon: 'time', label: 'Response SLA', value: activeIntent.sla, note: 'Priority-routed through our operations desk', color: C.success },
    { icon: 'shield-checkmark', label: 'Data Handling', value: 'Encrypted intake', note: 'Submission details are protected and tracked with reference IDs', color: C.violet },
    { icon: 'people', label: 'Routing', value: activeIntent.label, note: 'Automatically directed to the correct specialized team', color: C.primary },
  ];

  return (
    <ScrollView style={{ flex: 1, backgroundColor: C.bg }} showsVerticalScrollIndicator={false}>
      <ContactNav />

      <View
        style={{
          width: '100%',
          maxWidth: 1240,
          alignSelf: 'center',
          paddingHorizontal: isMobile ? 16 : isTablet ? 24 : 32,
          paddingTop: isMobile ? 24 : 42,
          paddingBottom: isMobile ? 32 : 52,
        }}
        data-testid="contact-page"
        testID="contact-page"
      >
        <View style={{ marginBottom: 24 }} data-testid="contact-hero" testID="contact-hero">
          {supportContext === 'login-lockout' ? (
            <View
              style={{
                alignSelf: 'flex-start',
                flexDirection: 'row',
                alignItems: 'center',
                gap: 8,
                backgroundColor: (globalThis as any).__alphaColor(C.primary, '15'),
                borderColor: (globalThis as any).__alphaColor(C.primary, '35'),
                borderWidth: 1,
                borderRadius: 999,
                paddingHorizontal: 12,
                paddingVertical: 6,
                marginBottom: 12,
              }}
              data-testid="contact-lockout-context-banner"
              testID="contact-lockout-context-banner"
            >
              <Ionicons name="shield-checkmark" size={14} color={C.primary} />
              <Text style={{ color: C.primary, fontSize: 11, fontWeight: '700' }}>{tx('contact.lockout.banner', 'Support request from sign-in recovery flow')}</Text>
            </View>
          ) : null}

          <Text style={{ color: C.text, fontSize: isMobile ? 30 : 42, fontWeight: '800', letterSpacing: -0.7 }} data-testid="contact-heading" testID="contact-heading">
            {tx('contact.hero.title', 'Contact Command Center')}
          </Text>
          <Text style={{ color: C.textSec, fontSize: isMobile ? 14 : 16, marginTop: 8, maxWidth: 960, lineHeight: 24 }} data-testid="contact-subtitle" testID="contact-subtitle">
            {tx('contact.hero.subtitle', 'Enterprise-grade contact routing for Sales, Support, Partnerships, and Press — with validated intake, response SLAs, and reference tracking.')}
          </Text>

          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 12 }} data-testid="contact-hero-cta-row" testID="contact-hero-cta-row">
            <TouchableOpacity
              onPress={() => setIntent('sales')}
              style={{ borderRadius: 10, backgroundColor: C.primary, paddingHorizontal: 14, paddingVertical: 9 }}
              data-testid="contact-hero-contact-sales"
              testID="contact-hero-contact-sales"
            >
              <Text style={{ color: C.primaryText, fontSize: 12, fontWeight: '800' }}>{tx('contact.hero.cta.sales', 'Contact sales')}</Text>
            </TouchableOpacity>
            <TouchableOpacity
              onPress={() => setIntent('support')}
              style={{ borderRadius: 10, borderWidth: 1, borderColor: C.border, backgroundColor: C.card, paddingHorizontal: 14, paddingVertical: 9 }}
              data-testid="contact-hero-submit-ticket"
              testID="contact-hero-submit-ticket"
            >
              <Text style={{ color: C.textSec, fontSize: 12, fontWeight: '800' }}>{tx('contact.hero.cta.ticket', 'Submit ticket')}</Text>
            </TouchableOpacity>
          </View>
        </View>

        <View style={{ flexDirection: isWide ? 'row' : 'column', gap: 20 }} data-testid="contact-main-grid" testID="contact-main-grid">
          <View style={{ width: isWide ? 340 : '100%', gap: 10 }} data-testid="contact-info-column" testID="contact-info-column">
            <View style={{ backgroundColor: C.card, borderRadius: 14, borderWidth: 1, borderColor: C.border, padding: 12, gap: 8 }} data-testid="contact-intent-selector" testID="contact-intent-selector">
              <Text style={{ color: C.text, fontSize: 13, fontWeight: '800' }}>{t("adopt.choose.your.intent")}</Text>
              <View style={{ gap: 7 }}>
                {INTENTS.map((item, idx) => {
                  const active = item.key === intent;
                  return (
                    <TouchableOpacity
                      key={item.key}
                      onPress={() => setIntent(item.key)}
                      style={{ borderRadius: 10, borderWidth: 1, borderColor: active ? C.primary : C.border, backgroundColor: active ? (globalThis as any).__alphaColor(C.primary, '16') : C.bgSoft, paddingHorizontal: 10, paddingVertical: 8 }}
                      data-testid={`contact-intent-option-${idx}`}
                      testID={`contact-intent-option-${idx}`}
                    >
                      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                        <Ionicons name={item.icon as any} size={15} color={active ? C.primary : C.textMuted} />
                        <Text style={{ color: active ? C.primary : C.text, fontSize: 12, fontWeight: '700' }}>{item.label}</Text>
                      </View>
                      <Text style={{ color: C.textMuted, fontSize: 10, marginTop: 4 }}>{item.sla} • {item.note}</Text>
                    </TouchableOpacity>
                  );
                })}
              </View>
            </View>

            {infoCards.map((card, idx) => (
              <View
                key={card.label}
                style={{
                  backgroundColor: C.card,
                  borderRadius: 14,
                  borderWidth: 1,
                  borderColor: C.border,
                  padding: 14,
                }}
                data-testid={`contact-info-card-${idx}`}
                testID={`contact-info-card-${idx}`}
              >
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 8 }}>
                  <View style={{ width: 34, height: 34, borderRadius: 10, backgroundColor: (globalThis as any).__alphaColor(card.color, '15'), alignItems: 'center', justifyContent: 'center' }}>
                    <Ionicons name={card.icon as any} size={17} color={card.color} />
                  </View>
                  <Text style={{ color: C.text, fontSize: 13, fontWeight: '800' }}>{card.label}</Text>
                </View>
                <Text style={{ color: card.color, fontSize: 13, fontWeight: '700' }}>{card.value}</Text>
                <Text style={{ color: C.textSec, fontSize: 12, marginTop: 4 }}>{card.note}</Text>
              </View>
            ))}

            <View style={{ backgroundColor: C.card, borderRadius: 14, borderWidth: 1, borderColor: C.border, padding: 14 }} data-testid="contact-recommendation-panel" testID="contact-recommendation-panel">
              <Text style={{ color: C.text, fontSize: 13, fontWeight: '800', marginBottom: 6 }}>{t("adopt.recommended.next.action")}</Text>
              <Text style={{ color: C.textSec, fontSize: 12, lineHeight: 19 }}>{recommendationByIntent[intent]}</Text>
            </View>
          </View>

          <View style={{ flex: 1 }} data-testid="contact-form-column" testID="contact-form-column">
            <View style={{ backgroundColor: C.card, borderRadius: 16, borderWidth: 1, borderColor: C.border, padding: isMobile ? 14 : 18, gap: 10 }} data-testid="contact-enterprise-form" testID="contact-enterprise-form">
              <Text style={{ color: C.text, fontSize: 18, fontWeight: '800' }} data-testid="contact-form-title" testID="contact-form-title">{activeIntent.label}{t("adopt.intake.form")}</Text>
              <Text style={{ color: C.textSec, fontSize: 12, lineHeight: 19 }} data-testid="contact-form-sla" testID="contact-form-sla">{t("adopt.expected.response")}{activeIntent.sla}</Text>

              <View style={{ flexDirection: isMobile ? 'column' : 'row', gap: 8 }}>
                <TextInput value={name} onChangeText={setName} placeholder="Full name*" placeholderTextColor={C.textMuted} style={{ flex: 1, borderWidth: 1, borderColor: C.border, borderRadius: 9, paddingHorizontal: 10, paddingVertical: 9, color: C.text, backgroundColor: C.bg }} data-testid="contact-input-name" testID="contact-input-name" />
                <TextInput value={email} onChangeText={setEmail} placeholder="Work email*" autoCapitalize="none" placeholderTextColor={C.textMuted} style={{ flex: 1, borderWidth: 1, borderColor: C.border, borderRadius: 9, paddingHorizontal: 10, paddingVertical: 9, color: C.text, backgroundColor: C.bg }} data-testid="contact-input-email" testID="contact-input-email" />
              </View>

              <View style={{ flexDirection: isMobile ? 'column' : 'row', gap: 8 }}>
                <TextInput value={company} onChangeText={setCompany} placeholder="Company" placeholderTextColor={C.textMuted} style={{ flex: 1, borderWidth: 1, borderColor: C.border, borderRadius: 9, paddingHorizontal: 10, paddingVertical: 9, color: C.text, backgroundColor: C.bg }} data-testid="contact-input-company" testID="contact-input-company" />
                <TextInput value={website} onChangeText={setWebsite} placeholder="Website" autoCapitalize="none" placeholderTextColor={C.textMuted} style={{ flex: 1, borderWidth: 1, borderColor: C.border, borderRadius: 9, paddingHorizontal: 10, paddingVertical: 9, color: C.text, backgroundColor: C.bg }} data-testid="contact-input-website" testID="contact-input-website" />
              </View>

              <TextInput value={subject} onChangeText={setSubject} placeholder="Subject" placeholderTextColor={C.textMuted} style={{ borderWidth: 1, borderColor: C.border, borderRadius: 9, paddingHorizontal: 10, paddingVertical: 9, color: C.text, backgroundColor: C.bg }} data-testid="contact-input-subject" testID="contact-input-subject" />

              <View style={{ gap: 6 }}>
                <Text style={{ color: C.text, fontSize: 12, fontWeight: '700' }}>{t("pricing.roi.teamSizePlaceholder")}</Text>
                <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 7 }}>
                  {TEAM_SIZE_OPTIONS.map((option, idx) => (
                    <TouchableOpacity key={option} onPress={() => setTeamSize(option)} style={{ borderWidth: 1, borderColor: teamSize === option ? C.primary : C.border, backgroundColor: teamSize === option ? (globalThis as any).__alphaColor(C.primary, '14') : C.bgSoft, borderRadius: 999, paddingHorizontal: 10, paddingVertical: 6 }} data-testid={`contact-team-size-${idx}`} testID={`contact-team-size-${idx}`}>
                      <Text style={{ color: teamSize === option ? C.primary : C.textSec, fontSize: 11, fontWeight: '700' }}>{option}</Text>
                    </TouchableOpacity>
                  ))}
                </View>
              </View>

              <View style={{ gap: 6 }}>
                <Text style={{ color: C.text, fontSize: 12, fontWeight: '700' }}>{t("myTickets.newTicket.priority")}</Text>
                <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 7 }}>
                  {PRIORITY_OPTIONS.map((option, idx) => (
                    <TouchableOpacity key={option} onPress={() => setPriority(option)} style={{ borderWidth: 1, borderColor: priority === option ? C.primary : C.border, backgroundColor: priority === option ? (globalThis as any).__alphaColor(C.primary, '14') : C.bgSoft, borderRadius: 999, paddingHorizontal: 10, paddingVertical: 6 }} data-testid={`contact-priority-${idx}`} testID={`contact-priority-${idx}`}>
                      <Text style={{ color: priority === option ? C.primary : C.textSec, fontSize: 11, fontWeight: '700', textTransform: 'capitalize' }}>{option}</Text>
                    </TouchableOpacity>
                  ))}
                </View>
              </View>

              <View style={{ flexDirection: isMobile ? 'column' : 'row', gap: 8 }}>
                <View style={{ flex: 1, gap: 6 }}>
                  <Text style={{ color: C.text, fontSize: 12, fontWeight: '700' }}>{t("admin.execDashboardPanels.auto.text.006")}</Text>
                  <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6 }}>
                    {REGION_OPTIONS.slice(0, isMobile ? 3 : 6).map((option, idx) => (
                      <TouchableOpacity key={option} onPress={() => setRegion(option)} style={{ borderWidth: 1, borderColor: region === option ? C.primary : C.border, backgroundColor: region === option ? (globalThis as any).__alphaColor(C.primary, '14') : C.bgSoft, borderRadius: 999, paddingHorizontal: 9, paddingVertical: 5 }} data-testid={`contact-region-${idx}`} testID={`contact-region-${idx}`}>
                        <Text style={{ color: region === option ? C.primary : C.textSec, fontSize: 10, fontWeight: '700' }}>{option}</Text>
                      </TouchableOpacity>
                    ))}
                  </View>
                </View>
              </View>

              {(intent === 'sales' || intent === 'partnerships' || intent === 'press') ? (
                <View style={{ gap: 6 }}>
                  <Text style={{ color: C.text, fontSize: 12, fontWeight: '700' }}>{t("admin.pagePerformance.tabs.timeline")}</Text>
                  <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 7 }}>
                    {TIMELINE_OPTIONS.map((option, idx) => (
                      <TouchableOpacity key={option} onPress={() => setTimeline(option)} style={{ borderWidth: 1, borderColor: timeline === option ? C.primary : C.border, backgroundColor: timeline === option ? (globalThis as any).__alphaColor(C.primary, '14') : C.bgSoft, borderRadius: 999, paddingHorizontal: 10, paddingVertical: 6 }} data-testid={`contact-timeline-${idx}`} testID={`contact-timeline-${idx}`}>
                        <Text style={{ color: timeline === option ? C.primary : C.textSec, fontSize: 11, fontWeight: '700' }}>{option}</Text>
                      </TouchableOpacity>
                    ))}
                  </View>
                </View>
              ) : null}

              {intent === 'sales' ? (
                <View style={{ gap: 6 }}>
                  <Text style={{ color: C.text, fontSize: 12, fontWeight: '700' }}>{t("adopt.budget.range")}</Text>
                  <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 7 }}>
                    {BUDGET_OPTIONS.map((option, idx) => (
                      <TouchableOpacity key={option} onPress={() => setBudgetRange(option)} style={{ borderWidth: 1, borderColor: budgetRange === option ? C.primary : C.border, backgroundColor: budgetRange === option ? (globalThis as any).__alphaColor(C.primary, '14') : C.bgSoft, borderRadius: 999, paddingHorizontal: 10, paddingVertical: 6 }} data-testid={`contact-budget-${idx}`} testID={`contact-budget-${idx}`}>
                        <Text style={{ color: budgetRange === option ? C.primary : C.textSec, fontSize: 11, fontWeight: '700' }}>{option}</Text>
                      </TouchableOpacity>
                    ))}
                  </View>
                </View>
              ) : null}

              <TextInput value={useCase} onChangeText={setUseCase} placeholder="Use case / goals" placeholderTextColor={C.textMuted} multiline style={{ borderWidth: 1, borderColor: C.border, borderRadius: 9, paddingHorizontal: 10, paddingVertical: 10, color: C.text, backgroundColor: C.bg, minHeight: 72, textAlignVertical: 'top' as any }} data-testid="contact-input-use-case" testID="contact-input-use-case" />
              <TextInput value={message} onChangeText={setMessage} placeholder="Message*" placeholderTextColor={C.textMuted} multiline style={{ borderWidth: 1, borderColor: C.border, borderRadius: 9, paddingHorizontal: 10, paddingVertical: 10, color: C.text, backgroundColor: C.bg, minHeight: 108, textAlignVertical: 'top' as any }} data-testid="contact-input-message" testID="contact-input-message" />

              <Text style={{ color: C.textMuted, fontSize: 11 }} data-testid="contact-form-trust-note" testID="contact-form-trust-note">{t("adopt.no.spam.your.request.is.routed.securely.and")}</Text>

              <TouchableOpacity onPress={() => void submitContact()} disabled={submitting} style={{ borderRadius: 10, backgroundColor: C.primary, paddingHorizontal: 14, paddingVertical: 11, opacity: submitting ? 0.7 : 1, alignItems: 'center' }} data-testid="contact-submit-button" testID="contact-submit-button">
                <Text style={{ color: C.primaryText, fontSize: 12, fontWeight: '800' }}>{submitting ? 'Submitting…' : `Submit ${activeIntent.label} request`}</Text>
              </TouchableOpacity>

              {successRef ? (
                <View style={{ borderWidth: 1, borderColor: (globalThis as any).__alphaColor(C.success, '45'), backgroundColor: (globalThis as any).__alphaColor(C.success, '12'), borderRadius: 10, padding: 10 }} data-testid="contact-success-card" testID="contact-success-card">
                  <Text style={{ color: C.success, fontSize: 12, fontWeight: '800' }}>{t("adopt.submitted.successfully")}</Text>
                  <Text style={{ color: C.textSec, fontSize: 11, marginTop: 4 }}>{successMessage}</Text>
                  <Text style={{ color: C.text, fontSize: 11, marginTop: 4, fontWeight: '700' }}>{t("adopt.reference.id")}{successRef}</Text>
                </View>
              ) : null}
            </View>
          </View>
        </View>
      </View>

      <Footer variant="welcome" />
    </ScrollView>
  );
}