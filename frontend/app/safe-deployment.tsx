import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { View, Text, ScrollView, TouchableOpacity, Alert, TextInput, ActivityIndicator } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { useTheme } from '../src/context/ThemeContext';
import { useTranslation } from '../src/hooks/useTranslation';
import { InfoPageSkeleton, usePageReady } from '../src/components/SkeletonLoaders';
import api from '../src/services/api';
import { AdminRouteGate } from '../src/components/auth/AdminRouteGate';

const SECTIONS = [
  {
    id: 'pipeline',
    title: 'Zero-Downtime Pipeline',
    description: 'Ship safely without interrupting live users by running every change through an automated, staged release flow.',
    bullets: [
      'Build → Test → Stage → Canary → Full Release',
      'Use immutable artifacts and env-driven configuration',
      'Keep rollback artifacts ready for 1-click reverts',
    ],
  },
  {
    id: 'flags',
    title: 'Feature Flags & Kill Switch',
    description: 'Gate new functionality behind flags to roll out gradually and deactivate instantly when needed.',
    bullets: [
      'Ship dark, release after enabling flags',
      'Gradually expand from internal → beta → public',
      'Document ownership for each flag and flag owner',
    ],
  },
  {
    id: 'tests',
    title: 'Automated Test Gates',
    description: 'Block deployments unless critical tests pass across backend, frontend, and database migrations.',
    bullets: [
      'Contract tests for /api endpoints',
      'Playwright UI smoke tests on staging',
      'Load test hot paths before >50% rollout',
    ],
  },
  {
    id: 'rollout',
    title: 'Progressive Rollout Strategy',
    description: 'Ramp exposure carefully to detect regressions early and protect uptime.',
    bullets: [
      '1% → 5% → 25% → 50% → 100% traffic',
      'Observe error rates and latency at each step',
      'Pause and rollback if SLOs degrade',
    ],
  },
  {
    id: 'monitoring',
    title: 'Monitoring & Alerts',
    description: 'Detect errors before users report them with strong observability and alert routing.',
    bullets: [
      'Track 4xx/5xx by endpoint and flag',
      'Alert on latency & saturation thresholds',
      'Log high-impact user sessions for traceability',
    ],
  },
  {
    id: 'rollback',
    title: 'Rollback & Postmortems',
    description: 'When incidents happen, reverse fast and capture learnings to prevent recurrence.',
    bullets: [
      'Revert within 5 minutes if error budget blows',
      'Keep database migrations reversible',
      'Run a 24-hour postmortem with action items',
    ],
  },
];

const CHECKLIST = [
  'All tests passing (unit, integration, UI)',
  'Feature flag set to off by default',
  'Canary metrics dashboards ready',
  'Rollback artifact verified',
  'On-call schedule + incident playbook prepared',
];

export default function SafeDeploymentScreen() {
  const pageReady = usePageReady();
  const router = useRouter();
  const { colors } = useTheme();
  const { t } = useTranslation();
  const [killSwitchLoading, setKillSwitchLoading] = useState(true);
  const [killSwitchSaving, setKillSwitchSaving] = useState(false);
  const [killSwitchEnabled, setKillSwitchEnabled] = useState(false);
  const [killSwitchReason, setKillSwitchReason] = useState('');
  const [killSwitchError, setKillSwitchError] = useState('');
  const [dryRunLoading, setDryRunLoading] = useState(true);
  const [dryRunReport, setDryRunReport] = useState<any>(null);
  const [dryRunError, setDryRunError] = useState('');
  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };

  const C = useMemo(() => ({
    bg: colors.bg,
    card: colors.card,
    text: colors.text,
    textMuted: colors.textMuted,
    textSec: colors.textSec,
    border: colors.border,
    primary: colors.primary,
    primaryText: 'rgb(255,255,255)',
  }), [colors]);

  const handleCopyChecklist = async () => {
    const checklistText = CHECKLIST.map((item, idx) => `${idx + 1}. ${item}`).join('\n');
    if (typeof navigator !== 'undefined' && navigator.clipboard) {
      try {
        await navigator.clipboard.writeText(checklistText);
        Alert.alert('Copied', 'Deployment checklist copied.');
        return;
      } catch (error) {
        console.warn('Clipboard blocked', error);
      }
    }
    Alert.alert('Deployment Checklist', checklistText);
  };

  const loadKillSwitchState = useCallback(async () => {
    setKillSwitchLoading(true);
    setKillSwitchError('');
    try {
      const { data } = await api.get('/admin/payments/checkout-kill-switch', { silentLoading: true });
      setKillSwitchEnabled(Boolean(data?.enabled));
      setKillSwitchReason(String(data?.reason || ''));
    } catch (error: any) {
      const message = String(error?.response?.data?.detail || error?.message || 'Unable to load kill-switch state.');
      setKillSwitchError(message);
    } finally {
      setKillSwitchLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadKillSwitchState();
  }, [loadKillSwitchState]);

  const loadLatestDryRunReport = useCallback(async () => {
    setDryRunLoading(true);
    setDryRunError('');
    try {
      const { data } = await api.get('/admin/i18n/literal-autofix-dry-run/latest', { silentLoading: true });
      setDryRunReport(data?.latest || null);
    } catch (error: any) {
      const message = String(error?.response?.data?.detail || error?.message || 'Unable to load dry-run report.');
      setDryRunError(message);
      setDryRunReport(null);
    } finally {
      setDryRunLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadLatestDryRunReport();
  }, [loadLatestDryRunReport]);

  const saveKillSwitchState = useCallback(async (enabled: boolean) => {
    setKillSwitchSaving(true);
    setKillSwitchError('');
    try {
      const { data } = await api.put('/admin/payments/checkout-kill-switch', {
        enabled,
        reason: killSwitchReason.trim() || 'Checkout is temporarily paused by admin while payment integrity checks are in progress.',
      }, { silentLoading: true });
      const state = data?.state || {};
      setKillSwitchEnabled(Boolean(state?.enabled));
      setKillSwitchReason(String(state?.reason || killSwitchReason));
      Alert.alert('Saved', enabled ? 'Checkout kill-switch enabled.' : 'Checkout kill-switch disabled.');
    } catch (error: any) {
      const message = String(error?.response?.data?.detail || error?.message || 'Unable to save kill-switch state.');
      setKillSwitchError(message);
      Alert.alert('Save failed', message);
    } finally {
      setKillSwitchSaving(false);
    }
  }, [killSwitchReason]);

  if (!pageReady) return <InfoPageSkeleton />;
  return (
    <AdminRouteGate returnTo="/safe-deployment">
<SafeAreaView style={{ flex: 1, backgroundColor: C.bg }} edges={['top']} data-testid="safe-deployment-screen" testID="safe-deployment-screen">
      
<View style={{ position: 'absolute', top: -140, left: -60, width: 260, height: 260, borderRadius: 130, backgroundColor: (globalThis as any).__alphaColor(C.primary, '1F') }} />
      
<View style={{ position: 'absolute', bottom: -180, right: -80, width: 280, height: 280, borderRadius: 140, backgroundColor: colors.warningSoft }} />

<ScrollView contentContainerStyle={{ padding: 20, paddingBottom: 40 }}>
        
<View style={{ marginBottom: 20 }}>
          
<Text style={{ fontSize: 26, fontWeight: '800', color: C.text }} data-testid="safe-deployment-title" testID="safe-deployment-title">{tx('safeDeployment.page.title', 'Safe Deployment Playbook')}</Text>
          
<Text style={{ marginTop: 6, color: C.textSec, fontSize: 13 }} data-testid="safe-deployment-subtitle" testID="safe-deployment-subtitle">
            {tx('safeDeployment.page.subtitle', 'A commercial-grade approach to shipping with confidence, designed for RealAICoach reliability.')}
          
</Text>
          
<View style={{ flexDirection: 'row', gap: 10, marginTop: 14, flexWrap: 'wrap' }}>
            
<TouchableOpacity
              style={{ backgroundColor: C.primary, paddingHorizontal: 14, paddingVertical: 10, borderRadius: 12, flexDirection: 'row', alignItems: 'center', gap: 6 }}
              onPress={handleCopyChecklist}
              data-testid="safe-deployment-copy-checklist" testID="safe-deployment-copy-checklist"
              accessibilityRole="button"
            >
              
<Ionicons name="copy" size={14} color={C.primaryText} />
              
<Text style={{ color: C.primaryText, fontWeight: '700', fontSize: 12 }}>{tx('safeDeployment.actions.copyChecklist', 'Copy Checklist')}</Text>
            
</TouchableOpacity>
            
<TouchableOpacity
              style={{ backgroundColor: C.card, paddingHorizontal: 14, paddingVertical: 10, borderRadius: 12, borderWidth: 1, borderColor: C.border, flexDirection: 'row', alignItems: 'center', gap: 6 }}
              onPress={() => router.push('/features/health-dashboard')}
              data-testid="safe-deployment-health-dashboard" testID="safe-deployment-health-dashboard"
              accessibilityRole="button"
            >
              
<Ionicons name="pulse" size={14} color={C.primary} />
              
<Text style={{ color: C.text, fontWeight: '700', fontSize: 12 }}>Open Feature Health</Text>
            
</TouchableOpacity>
          
</View>
        
</View>

<View style={{ marginBottom: 14, backgroundColor: C.card, borderRadius: 16, padding: 16, borderWidth: 1, borderColor: C.border }} data-testid="safe-deployment-kill-switch-card" testID="safe-deployment-kill-switch-card">
  <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 10 }}>
    <View style={{ flex: 1 }}>
      <Text style={{ fontSize: 15, fontWeight: '800', color: C.text }} data-testid="safe-deployment-kill-switch-title" testID="safe-deployment-kill-switch-title">Checkout Global Kill-Switch</Text>
      <Text style={{ marginTop: 4, color: C.textSec, fontSize: 12, lineHeight: 18 }} data-testid="safe-deployment-kill-switch-subtitle" testID="safe-deployment-kill-switch-subtitle">
        Temporarily pause all checkout creation across Stripe, PayPal, and FedaPay.
      </Text>
    </View>
    <View style={{ borderRadius: 999, borderWidth: 1, borderColor: killSwitchEnabled ? colors.error : C.border, backgroundColor: killSwitchEnabled ? colors.errorSoft : C.bg, paddingHorizontal: 10, paddingVertical: 5 }} data-testid="safe-deployment-kill-switch-status-chip" testID="safe-deployment-kill-switch-status-chip">
      <Text style={{ color: killSwitchEnabled ? colors.error : C.textMuted, fontSize: 10, fontWeight: '800' }}>
        {killSwitchEnabled ? 'ENABLED' : 'DISABLED'}
      </Text>
    </View>
  </View>

  {killSwitchLoading ? (
    <View style={{ marginTop: 12, flexDirection: 'row', alignItems: 'center', gap: 8 }}>
      <ActivityIndicator size="small" color={C.primary} />
      <Text style={{ color: C.textMuted, fontSize: 12 }}>Loading kill-switch state…</Text>
    </View>
  ) : (
    <>
      <TextInput
        value={killSwitchReason}
        onChangeText={setKillSwitchReason}
        placeholder="Reason shown to users when checkout is paused"
        placeholderTextColor={C.textMuted}
        multiline
        style={{ marginTop: 12, borderRadius: 10, borderWidth: 1, borderColor: C.border, backgroundColor: C.bg, color: C.text, paddingHorizontal: 10, paddingVertical: 10, minHeight: 64, textAlignVertical: 'top', fontSize: 12 }}
        data-testid="safe-deployment-kill-switch-reason-input"
        testID="safe-deployment-kill-switch-reason-input"
      />

      {killSwitchError ? (
        <Text style={{ marginTop: 8, color: colors.error, fontSize: 11 }} data-testid="safe-deployment-kill-switch-error" testID="safe-deployment-kill-switch-error">
          {killSwitchError}
        </Text>
      ) : null}

      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 12 }}>
        <TouchableOpacity
          disabled={killSwitchSaving || killSwitchEnabled}
          onPress={() => { void saveKillSwitchState(true); }}
          style={{ borderRadius: 10, borderWidth: 1, borderColor: colors.error, backgroundColor: killSwitchSaving || killSwitchEnabled ? colors.errorSoft : colors.error, paddingHorizontal: 12, paddingVertical: 10, opacity: killSwitchSaving || killSwitchEnabled ? 0.65 : 1 }}
          data-testid="safe-deployment-kill-switch-enable"
          testID="safe-deployment-kill-switch-enable"
        >
          <Text style={{ color: C.primaryText, fontSize: 12, fontWeight: '800' }}>{killSwitchSaving ? 'Saving…' : 'Enable Kill-Switch'}</Text>
        </TouchableOpacity>

        <TouchableOpacity
          disabled={killSwitchSaving || !killSwitchEnabled}
          onPress={() => { void saveKillSwitchState(false); }}
          style={{ borderRadius: 10, borderWidth: 1, borderColor: C.border, backgroundColor: C.card, paddingHorizontal: 12, paddingVertical: 10, opacity: killSwitchSaving || !killSwitchEnabled ? 0.65 : 1 }}
          data-testid="safe-deployment-kill-switch-disable"
          testID="safe-deployment-kill-switch-disable"
        >
          <Text style={{ color: C.text, fontSize: 12, fontWeight: '800' }}>{killSwitchSaving ? 'Saving…' : 'Disable Kill-Switch'}</Text>
        </TouchableOpacity>

        <TouchableOpacity
          disabled={killSwitchSaving}
          onPress={() => { void loadKillSwitchState(); }}
          style={{ borderRadius: 10, borderWidth: 1, borderColor: C.border, backgroundColor: C.bg, paddingHorizontal: 12, paddingVertical: 10, opacity: killSwitchSaving ? 0.65 : 1 }}
          data-testid="safe-deployment-kill-switch-refresh"
          testID="safe-deployment-kill-switch-refresh"
        >
          <Text style={{ color: C.textMuted, fontSize: 12, fontWeight: '700' }}>Refresh</Text>
        </TouchableOpacity>
      </View>
    </>
  )}
</View>

<View style={{ marginBottom: 14, backgroundColor: C.card, borderRadius: 16, padding: 16, borderWidth: 1, borderColor: C.border }} data-testid="safe-deployment-i18n-dry-run-card" testID="safe-deployment-i18n-dry-run-card">
  <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 10 }}>
    <View style={{ flex: 1 }}>
      <Text style={{ fontSize: 15, fontWeight: '800', color: C.text }} data-testid="safe-deployment-i18n-dry-run-title" testID="safe-deployment-i18n-dry-run-title">Nightly Literal-Autofix Dry-Run</Text>
      <Text style={{ marginTop: 4, color: C.textSec, fontSize: 12, lineHeight: 18 }} data-testid="safe-deployment-i18n-dry-run-subtitle" testID="safe-deployment-i18n-dry-run-subtitle">
        Tracks newly missing i18n keys nightly without applying automatic code changes.
      </Text>
    </View>
    <TouchableOpacity
      onPress={() => { void loadLatestDryRunReport(); }}
      style={{ borderRadius: 8, borderWidth: 1, borderColor: C.border, backgroundColor: C.bg, paddingHorizontal: 10, paddingVertical: 7 }}
      data-testid="safe-deployment-i18n-dry-run-refresh"
      testID="safe-deployment-i18n-dry-run-refresh"
    >
      <Text style={{ color: C.textMuted, fontSize: 11, fontWeight: '700' }}>Refresh</Text>
    </TouchableOpacity>
  </View>

  {dryRunLoading ? (
    <View style={{ marginTop: 12, flexDirection: 'row', alignItems: 'center', gap: 8 }}>
      <ActivityIndicator size="small" color={C.primary} />
      <Text style={{ color: C.textMuted, fontSize: 12 }}>Loading nightly report…</Text>
    </View>
  ) : dryRunError ? (
    <Text style={{ marginTop: 10, color: colors.error, fontSize: 11 }} data-testid="safe-deployment-i18n-dry-run-error" testID="safe-deployment-i18n-dry-run-error">{dryRunError}</Text>
  ) : (
    <View style={{ marginTop: 12, flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
      {[{
        key: 'new',
        label: 'Newly Missing',
        value: Number(dryRunReport?.newly_missing_count || 0),
      }, {
        key: 'baseline',
        label: 'Baseline',
        value: Number(dryRunReport?.baseline_count || 0),
      }, {
        key: 'unresolved',
        label: 'Unresolved Top',
        value: Number(dryRunReport?.unresolved_top_count || 0),
      }].map((item) => (
        <View key={item.key} style={{ borderRadius: 10, borderWidth: 1, borderColor: C.border, backgroundColor: C.bg, paddingHorizontal: 10, paddingVertical: 8, minWidth: 116 }} data-testid={`safe-deployment-i18n-dry-run-${item.key}`} testID={`safe-deployment-i18n-dry-run-${item.key}`}>
          <Text style={{ color: C.textMuted, fontSize: 10, fontWeight: '700' }}>{item.label}</Text>
          <Text style={{ color: item.key === 'new' && item.value > 0 ? colors.warningText : C.text, fontSize: 15, fontWeight: '800', marginTop: 3 }}>{item.value}</Text>
        </View>
      ))}
      <View style={{ borderRadius: 10, borderWidth: 1, borderColor: C.border, backgroundColor: C.bg, paddingHorizontal: 10, paddingVertical: 8, minWidth: 180 }} data-testid="safe-deployment-i18n-dry-run-generated-at" testID="safe-deployment-i18n-dry-run-generated-at">
        <Text style={{ color: C.textMuted, fontSize: 10, fontWeight: '700' }}>Generated At</Text>
        <Text style={{ color: C.text, fontSize: 11, fontWeight: '700', marginTop: 3 }}>
          {dryRunReport?.generated_at ? new Date(dryRunReport.generated_at).toLocaleString() : 'Not available yet'}
        </Text>
      </View>
    </View>
  )}
</View>

<View style={{ gap: 14 }}>
          {SECTIONS.map(section => (
            
<View key={section.id} style={{ backgroundColor: C.card, borderRadius: 16, padding: 16, borderWidth: 1, borderColor: C.border }} data-testid={`safe-deployment-section-${section.id}`} testID={`safe-deployment-section-${section.id}`}>
              
<Text style={{ fontSize: 15, fontWeight: '800', color: C.text }}>{section.title}</Text>
              
<Text style={{ marginTop: 6, color: C.textSec, fontSize: 12, lineHeight: 18 }}>{section.description}</Text>
              
<View style={{ marginTop: 10, gap: 6 }}>
                {section.bullets.map((bullet, idx) => (
                  
<View key={`${section.id}-${idx}`} style={{ flexDirection: 'row', gap: 8 }}>
                    
<View style={{ width: 6, height: 6, borderRadius: 3, backgroundColor: C.primary, marginTop: 6 }} />
                    
<Text style={{ flex: 1, color: C.textMuted, fontSize: 12, lineHeight: 18 }}>{bullet}</Text>
                  
</View>
                ))}
              
</View>
            
</View>
          ))}
        
</View>

<View style={{ marginTop: 18, backgroundColor: C.card, borderRadius: 16, padding: 16, borderWidth: 1, borderColor: C.border }} data-testid="safe-deployment-checklist" testID="safe-deployment-checklist">
          
<View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 10 }}>
            
<Ionicons name="checkmark-circle" size={18} color={C.primary} />
            
<Text style={{ fontSize: 15, fontWeight: '800', color: C.text }}>Release Checklist</Text>
          
</View>
          {CHECKLIST.map((item, idx) => (
            
<Text key={item} style={{ color: C.textMuted, fontSize: 12, lineHeight: 19 }} data-testid={`safe-deployment-checklist-${idx}`} testID={`safe-deployment-checklist-${idx}`}>
              {idx + 1}. {item}
            
</Text>
          ))}
        
</View>
      
</ScrollView>
    
</SafeAreaView>
    </AdminRouteGate>
  );
}
