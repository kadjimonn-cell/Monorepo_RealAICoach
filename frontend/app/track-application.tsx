import React, { useState, useEffect } from 'react';
import { View, Text, TouchableOpacity, useWindowDimensions, ActivityIndicator, Platform } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import PublicPageShell from '../src/components/PublicPageLayout';
import { useTheme } from '../src/context/ThemeContext';
import { useTranslation } from '../src/hooks/useTranslation';
import { resolveRuntimeBaseUrl } from '../src/utils/runtimeBaseUrl';

const API = resolveRuntimeBaseUrl();

interface TimelineStep {
  step: string;
  label: string;
  description: string;
}

interface TrackResult {
  found: boolean;
  message?: string;
  application?: {
    application_id: string;
    full_name: string;
    position: string;
    department: string;
    status: string;
    submitted_at: string;
    interview?: {
      date: string;
      time: string;
      type: string;
      notes: string;
      room_id: string;
      video_url: string;
    };
  };
  timeline?: TimelineStep[];
  current_step_index?: number;
  is_rejected?: boolean;
}

type NewTrackerPayload = {
  application_id: string;
  role_title?: string;
  status?: string;
  submitted_at?: string;
  status_updated_at?: string;
  applicant_first_name?: string;
  timeline?: { key: string; title: string; subtitle: string; state: 'done' | 'active' | 'pending' }[];
  interview?: {
    start_utc?: string;
    interview_type?: string;
  } | null;
};

const mapNewTrackerPayload = (payload: NewTrackerPayload): TrackResult => {
  const timelineSrc = Array.isArray(payload?.timeline) ? payload.timeline : [];
  const currentStepIndex = timelineSrc.findIndex((s) => s?.state === 'active');
  const status = String(payload?.status || 'received');
  const isRejected = status === 'rejected';
  const interviewStart = String(payload?.interview?.start_utc || '');
  const interviewDate = interviewStart ? new Date(interviewStart) : null;
  const formattedDate = interviewDate ? interviewDate.toLocaleDateString() : '';
  const formattedTime = interviewDate ? interviewDate.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '';

  return {
    found: true,
    application: {
      application_id: String(payload?.application_id || ''),
      full_name: String(payload?.applicant_first_name || 'Applicant'),
      position: String(payload?.role_title || 'Open Application'),
      department: '',
      status,
      submitted_at: String(payload?.submitted_at || ''),
      interview: interviewDate
        ? {
          date: formattedDate,
          time: formattedTime,
          type: String(payload?.interview?.interview_type || 'video'),
          notes: '',
          room_id: '',
          video_url: '',
        }
        : undefined,
    },
    timeline: timelineSrc.map((item) => ({
      step: item?.key || 'received',
      label: item?.title || 'Application Update',
      description: item?.subtitle || '',
    })),
    current_step_index: currentStepIndex >= 0 ? currentStepIndex : 0,
    is_rejected: isRejected,
  };
};

const STEP_COLORS = ['#0F766E', '#10B981', '#F59E0B', '#14B8A6'];
const STEP_BG = ['#EFF6FF', '#F0FDF4', '#FFFBEB', '#F5F3FF'];  // @theme-ok brand/role/state identifier
const STEP_ICONS: (keyof typeof Ionicons.glyphMap)[] = ['document-text', 'search', 'videocam', 'trophy'];

export default function TrackApplicationPage() {
  const { width } = useWindowDimensions();
  const { colors: C, darkMode } = useTheme();
  const { t } = useTranslation();
  const tx = React.useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);
  const deepSurface = C.card;
  const deepSurfaceAlt = C.border;
  const deepText = C.text;
  const deepMuted = C.textSec;
  const deepMeta = C.textMuted;
  const accentButtonText = darkMode ? C.bg : C.card;
  const m = width < 640;
  const router = useRouter();
  const [appId, setAppId] = useState('');
  const [status, setStatus] = useState<'idle' | 'loading' | 'found' | 'not_found'>('idle');
  const [result, setResult] = useState<TrackResult | null>(null);

  // Check for ?id= query param on mount
  useEffect(() => {
    if (Platform.OS === 'web') {
      const params = new URLSearchParams(window.location.search);
      const idParam = params.get('id');
      if (idParam) {
        setAppId(idParam);
        lookupApplication(idParam);
      }
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const lookupApplication = async (id?: string) => {
    const lookupId = (id || appId).trim();
    if (!lookupId) return;
    setStatus('loading');
    try {
      const modernRes = await fetch(`${API}/api/careers/applications/track/${encodeURIComponent(lookupId)}`);
      if (modernRes.ok) {
        const modernPayload: NewTrackerPayload = await modernRes.json();
        const mapped = mapNewTrackerPayload(modernPayload);
        setResult(mapped);
        setStatus(mapped.found ? 'found' : 'not_found');
        return;
      }

      const legacyRes = await fetch(`${API}/api/careers/track/${encodeURIComponent(lookupId.toUpperCase())}`);
      const legacyData: TrackResult = await legacyRes.json();
      setResult(legacyData);
      setStatus(legacyData.found ? 'found' : 'not_found');
    } catch {
      setResult({ found: false, message: tx('trackApplication.errors.network', 'Network error. Please try again.') });
      setStatus('not_found');
    }
  };

  const formatDate = (iso: string) => {
    try {
      return new Date(iso).toLocaleDateString(undefined, { year: 'numeric', month: 'long', day: 'numeric' });
    } catch { return iso; }
  };

  return (
    <PublicPageShell>
      {/* Hero */}
      <View style={{ alignItems: m ? 'flex-start' : 'center', marginBottom: m ? 24 : 40 }} data-testid="track-application-page" testID="track-application-page">
        <View style={{ paddingHorizontal: 14, paddingVertical: 6, borderRadius: 20, backgroundColor: C.primarySoft, borderWidth: 1, borderColor: C.primarySoft, marginBottom: 14 }}>
          <Text style={{ color: C.primary, fontSize: 11, fontWeight: '700', letterSpacing: 1 }}>{tx('trackApplication.badge', 'APPLICATION TRACKER')}</Text>
        </View>
        <Text style={{ color: C.text, fontSize: m ? 24 : 32, fontWeight: '800', textAlign: m ? 'left' : 'center', letterSpacing: -0.5, marginBottom: 10, lineHeight: m ? 30 : 40 }}>
          {tx('trackApplication.title', 'Track Your Application')}
        </Text>
        <Text style={{ color: C.textSec, fontSize: m ? 13 : 15, lineHeight: m ? 20 : 24, textAlign: m ? 'left' : 'center', maxWidth: 520 }}>
          {tx('trackApplication.subtitle', 'Enter your Application ID to check the current status of your submission.')}
        </Text>
      </View>

      {/* Search Box */}
      <View style={{ backgroundColor: C.card, borderRadius: 16, padding: m ? 20 : 28, marginBottom: 24, borderWidth: 1, borderColor: C.border, maxWidth: 560, alignSelf: 'center', width: '100%' }} data-testid="track-search-box" testID="track-search-box">
        <Text style={{ color: C.textSec, fontSize: 12, fontWeight: '600', marginBottom: 8 }}>
          {tx('trackApplication.search.applicationId', 'Application ID')} <Text style={{ color: C.error }}>*</Text>
        </Text>
        {Platform.OS === 'web' ? (
          <View style={{ flexDirection: m ? 'column' : 'row', gap: 10 }}>
            <input
              type="text"
              value={appId}
              onChange={(e: any) => setAppId(e.target.value)}
              onKeyDown={(e: any) => e.key === 'Enter' && lookupApplication()}
              placeholder={tx('trackApplication.search.placeholder', 'e.g. app_a1b2c3d4e5f6')}
              data-testid="track-input"
              style={{
                flex: 1, padding: '14px 16px', borderRadius: 10, border: `1px solid ${C.border}`,
                backgroundColor: deepSurface, color: deepText, fontSize: 15, fontFamily: 'monospace',
                outline: 'none', boxSizing: 'border-box' as any, letterSpacing: 0.5,
              }}
            />
            <TouchableOpacity
              onPress={() => lookupApplication()}
              disabled={status === 'loading' || !appId.trim()}
              style={{
                paddingHorizontal: 24, paddingVertical: 14, borderRadius: 10,
                backgroundColor: C.accent, opacity: status === 'loading' || !appId.trim() ? 0.6 : 1,
                flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8,
              }}
              data-testid="track-search-btn" testID="track-search-btn"
            >
              {status === 'loading' ? (
                <ActivityIndicator size="small" color={accentButtonText} />
              ) : (
                <>
                  <Ionicons name="search" size={16} color={accentButtonText} />
                  <Text style={{ color: accentButtonText, fontSize: 14, fontWeight: '700' }}>{tx('trackApplication.search.track', 'Track')}</Text>
                </>
              )}
            </TouchableOpacity>
          </View>
        ) : (
          <Text style={{ color: C.textSec, fontSize: 13 }}>{tx('trackApplication.search.webOnly', 'Please use the web version to track applications.')}</Text>
        )}
      </View>

      {/* Not Found */}
      {status === 'not_found' && result && (
        <View style={{ backgroundColor: C.errorSoft, borderRadius: 14, padding: m ? 20 : 24, marginBottom: 24, borderWidth: 1, borderColor: C.errorSoft, maxWidth: 560, alignSelf: 'center', width: '100%', alignItems: 'center' }} data-testid="track-not-found" testID="track-not-found">
          <View style={{ width: 48, height: 48, borderRadius: 24, backgroundColor: C.errorSoft, justifyContent: 'center', alignItems: 'center', marginBottom: 12 }}>
            <Ionicons name="search-outline" size={24} color={C.error} />
          </View>
          <Text style={{ color: C.text, fontSize: 16, fontWeight: '700', marginBottom: 6, textAlign: 'center' }}>
            {tx('trackApplication.notFound.title', 'Application Not Found')}
          </Text>
          <Text style={{ color: C.textSec, fontSize: 13, textAlign: 'center', lineHeight: 20 }}>
            {result.message || tx('trackApplication.notFound.subtitle', 'No application found with that ID. Please double-check and try again.')}
          </Text>
          <TouchableOpacity
            onPress={() => router.push('/careers' as any)}
            style={{ marginTop: 16, paddingHorizontal: 20, paddingVertical: 10, borderRadius: 8, borderWidth: 1, borderColor: C.accent }}
            data-testid="track-apply-link" testID="track-apply-link"
          >
            <Text style={{ color: C.accent, fontSize: 13, fontWeight: '600' }}>{tx('trackApplication.notFound.applyNow', 'Apply Now')}</Text>
          </TouchableOpacity>
        </View>
      )}

      {/* Found — Results */}
      {status === 'found' && result?.application && (
        <View style={{ maxWidth: 560, alignSelf: 'center', width: '100%' }} data-testid="track-result" testID="track-result">
          {/* Application Summary Card */}
          <View style={{ backgroundColor: C.card, borderRadius: 16, padding: m ? 20 : 24, marginBottom: 20, borderWidth: 1, borderColor: C.border }}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 12, marginBottom: 16 }}>
              <View style={{ width: 44, height: 44, borderRadius: 12, backgroundColor: C.successSoft, justifyContent: 'center', alignItems: 'center' }}>
                <Ionicons name="person" size={22} color={C.successText} />
              </View>
              <View style={{ flex: 1 }}>
                <Text style={{ color: C.text, fontSize: m ? 16 : 18, fontWeight: '800' }}>{result.application.full_name}</Text>
                <Text style={{ color: C.textSec, fontSize: 13 }}>{result.application.position}</Text>
              </View>
            </View>

            <View style={{ flexDirection: m ? 'column' : 'row', gap: m ? 10 : 16 }}>
              <View style={{ flex: 1, backgroundColor: deepSurface, borderRadius: 10, padding: 14 }}>
                <Text style={{ color: deepMeta, fontSize: 10, fontWeight: '700', letterSpacing: 0.5, marginBottom: 4 }}>{tx('trackApplication.result.applicationId', 'APPLICATION ID')}</Text>
                <Text style={{ color: deepText, fontSize: 13, fontWeight: '700', fontFamily: 'monospace' }}>{result.application.application_id}</Text>
              </View>
              <View style={{ flex: 1, backgroundColor: deepSurface, borderRadius: 10, padding: 14 }}>
                <Text style={{ color: deepMeta, fontSize: 10, fontWeight: '700', letterSpacing: 0.5, marginBottom: 4 }}>{tx('trackApplication.result.submitted', 'SUBMITTED')}</Text>
                <Text style={{ color: deepText, fontSize: 13, fontWeight: '600' }}>{formatDate(result.application.submitted_at)}</Text>
              </View>
            </View>
          </View>

          {/* Rejected State */}
          {result.is_rejected && (
            <View style={{ backgroundColor: C.errorSoft, borderRadius: 14, padding: 20, marginBottom: 20, borderWidth: 1, borderColor: C.errorSoft, alignItems: 'center' }}>
              <Ionicons name="close-circle" size={32} color={C.error} style={{ marginBottom: 8 }} />
              <Text style={{ color: C.text, fontSize: 16, fontWeight: '700', marginBottom: 4 }}>{tx('trackApplication.rejected.title', 'Application Not Selected')}</Text>
              <Text style={{ color: C.textSec, fontSize: 13, textAlign: 'center', lineHeight: 20 }}>
                {tx('trackApplication.rejected.subtitle', 'We appreciate your interest but have decided to move forward with other candidates. We encourage you to apply again in the future.')}
              </Text>
            </View>
          )}

          {/* Timeline */}
          {!result.is_rejected && result.timeline && (
            <View style={{ backgroundColor: C.card, borderRadius: 16, padding: m ? 20 : 24, marginBottom: 20, borderWidth: 1, borderColor: C.border }}>
              <Text style={{ color: C.text, fontSize: 16, fontWeight: '700', marginBottom: 20 }}>{tx('trackApplication.timeline.title', 'Application Progress')}</Text>
              {result.timeline.map((step, idx) => {
                const isActive = idx <= (result.current_step_index ?? 0);
                const isCurrent = idx === (result.current_step_index ?? 0);
                const color = isActive ? STEP_COLORS[idx] : C.borderMd;
                const bg = isActive ? STEP_BG[idx] : deepSurfaceAlt;
                const isLast = idx === result.timeline!.length - 1;

                return (
                  <View key={step.step} style={{ flexDirection: 'row', gap: m ? 12 : 16, marginBottom: isLast ? 0 : 4 }}>
                    {/* Line + Circle */}
                    <View style={{ alignItems: 'center', width: 40 }}>
                      <View style={{
                        width: 36, height: 36, borderRadius: 18, backgroundColor: bg,
                        justifyContent: 'center', alignItems: 'center',
                        borderWidth: isCurrent ? 2 : 0, borderColor: isCurrent ? color : 'transparent',
                      }}>
                        {isActive ? (
                          <Ionicons name={isCurrent ? STEP_ICONS[idx] : 'checkmark'} size={16} color={color} />
                        ) : (
                          <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: C.textDisabled }} />
                        )}
                      </View>
                      {!isLast && (
                        <View style={{ width: 2, height: 32, backgroundColor: isActive ? (globalThis as any).__alphaColor(color, '40') : deepSurfaceAlt, marginVertical: 2 }} />
                      )}
                    </View>
                    {/* Content */}
                    <View style={{ flex: 1, paddingBottom: isLast ? 0 : 16 }}>
                      <Text style={{ color: isActive ? C.text : C.textDisabled, fontSize: 14, fontWeight: '700', marginBottom: 2 }}>
                        {step.label}
                        {isCurrent && (
                          <Text style={{ color, fontSize: 11, fontWeight: '600' }}> ({tx('trackApplication.timeline.current', 'Current')})</Text>
                        )}
                      </Text>
                      <Text style={{ color: isActive ? deepMuted : C.borderMd, fontSize: 12, lineHeight: 18 }}>{step.description}</Text>
                    </View>
                  </View>
                );
              })}
            </View>
          )}

          {/* Interview Details Card */}
          {result.application.interview && result.application.status === 'interview' && (
            <View style={{ backgroundColor: C.purpleSoft, borderRadius: 16, padding: m ? 20 : 24, marginBottom: 20, borderWidth: 1, borderColor: C.purpleSoft }} data-testid="interview-details-card" testID="interview-details-card">
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 16 }}>
                <View style={{ width: 36, height: 36, borderRadius: 10, backgroundColor: C.purpleSoft, justifyContent: 'center', alignItems: 'center' }}>
                  <Ionicons name="videocam" size={18} color={C.purpleText} />
                </View>
                <Text style={{ color: C.text, fontSize: 16, fontWeight: '700' }}>{tx('trackApplication.interview.title', 'Interview Scheduled')}</Text>
              </View>

              <View style={{ flexDirection: m ? 'column' : 'row', gap: m ? 10 : 14, marginBottom: 14 }}>
                <View style={{ flex: 1, backgroundColor: deepSurface, borderRadius: 10, padding: 14 }}>
                  <Text style={{ color: deepMeta, fontSize: 10, fontWeight: '700', letterSpacing: 0.5, marginBottom: 4 }}>{tx('trackApplication.interview.date', 'DATE')}</Text>
                  <Text style={{ color: deepText, fontSize: 15, fontWeight: '700' }}>{result.application.interview.date}</Text>
                </View>
                <View style={{ flex: 1, backgroundColor: deepSurface, borderRadius: 10, padding: 14 }}>
                  <Text style={{ color: deepMeta, fontSize: 10, fontWeight: '700', letterSpacing: 0.5, marginBottom: 4 }}>{tx('trackApplication.interview.time', 'TIME')}</Text>
                  <Text style={{ color: deepText, fontSize: 15, fontWeight: '700' }}>{result.application.interview.time || tx('trackApplication.interview.tbd', 'TBD')}</Text>
                </View>
                <View style={{ flex: 1, backgroundColor: deepSurface, borderRadius: 10, padding: 14 }}>
                  <Text style={{ color: deepMeta, fontSize: 10, fontWeight: '700', letterSpacing: 0.5, marginBottom: 4 }}>{tx('trackApplication.interview.format', 'FORMAT')}</Text>
                  <Text style={{ color: deepText, fontSize: 14, fontWeight: '600' }}>
                    {({
                      video: tx('trackApplication.interview.type.video', 'Video Call'),
                      phone: tx('trackApplication.interview.type.phone', 'Phone Call'),
                      'in-person': tx('trackApplication.interview.type.inPerson', 'In Person'),
                      'in-app-video': tx('trackApplication.interview.type.inAppVideo', 'In-App Video'),
                    } as any)[result.application.interview.type] || tx('trackApplication.interview.type.video', 'Video Call')}
                  </Text>
                </View>
              </View>

              {result.application.interview.notes ? (
                <View style={{ backgroundColor: deepSurface, borderRadius: 10, padding: 14, marginBottom: 14 }}>
                  <Text style={{ color: deepMeta, fontSize: 10, fontWeight: '700', letterSpacing: 0.5, marginBottom: 4 }}>{tx('trackApplication.interview.notes', 'PREPARATION NOTES')}</Text>
                  <Text style={{ color: deepMuted, fontSize: 13, lineHeight: 20 }}>{result.application.interview.notes}</Text>
                </View>
              ) : null}

              {result.application.interview.type === 'in-app-video' && result.application.interview.video_url ? (
                <TouchableOpacity
                  onPress={() => { if (Platform.OS === 'web') window.open(result!.application!.interview!.video_url, '_blank'); }}
                  style={{ backgroundColor: C.purple, paddingVertical: 14, paddingHorizontal: 28, borderRadius: 10, alignItems: 'center', flexDirection: 'row', justifyContent: 'center', gap: 8 }}
                  data-testid="join-video-interview-btn" testID="join-video-interview-btn"
                >
                  <Ionicons name="videocam" size={16} color={accentButtonText} />
                  <Text style={{ color: accentButtonText, fontSize: 14, fontWeight: '700' }}>{tx('trackApplication.interview.join', 'Join Video Interview')}</Text>
                </TouchableOpacity>
              ) : null}
            </View>
          )}

          {/* CTA: Sign Up */}
          <View style={{ backgroundColor: C.card, borderRadius: 16, padding: m ? 20 : 24, alignItems: 'center', borderWidth: 1, borderColor: C.border }}>
            <Ionicons name="rocket" size={28} color={C.accent} style={{ marginBottom: 10 }} />
            <Text style={{ color: C.text, fontSize: 16, fontWeight: '700', marginBottom: 6, textAlign: 'center' }}>
              {tx('trackApplication.cta.title', 'Explore RealAICoach While You Wait')}
            </Text>
            <Text style={{ color: C.textSec, fontSize: 13, textAlign: 'center', lineHeight: 20, marginBottom: 16, maxWidth: 400 }}>
              {tx('trackApplication.cta.subtitle', 'Create a free account to experience our AI coaching platform firsthand and see what you could help build.')}
            </Text>
            <TouchableOpacity
              onPress={() => router.push('/auth/register' as any)}
              style={{ paddingHorizontal: 28, paddingVertical: 13, borderRadius: 10, backgroundColor: C.accent }}
              data-testid="track-signup-btn" testID="track-signup-btn"
            >
              <Text style={{ color: accentButtonText, fontSize: 14, fontWeight: '700' }}>{tx('trackApplication.cta.button', 'Create Your Free Account')}</Text>
            </TouchableOpacity>
          </View>
        </View>
      )}

      {/* Idle — Info Card */}
      {status === 'idle' && (
        <View style={{ maxWidth: 560, alignSelf: 'center', width: '100%' }}>
          <View style={{ backgroundColor: C.card, borderRadius: 14, padding: m ? 18 : 24, borderWidth: 1, borderColor: C.border }}>
            <Text style={{ color: C.text, fontSize: 15, fontWeight: '700', marginBottom: 12 }}>{tx('trackApplication.idHelp.title', 'Where to find your Application ID?')}</Text>
            <View style={{ gap: 10 }}>
              {[
                { icon: 'mail' as const, text: tx('trackApplication.idHelp.item1', 'Check the confirmation email sent after you applied') },
                { icon: 'document-text' as const, text: tx('trackApplication.idHelp.item2', 'It starts with "APP-" followed by a timestamp and your initials') },
                { icon: 'help-circle' as const, text: tx('trackApplication.idHelp.item3', 'Can\'t find it? Contact us at careers@realaicoach.app') },
              ].map((item, i) => (
                <View key={i} style={{ flexDirection: 'row', alignItems: 'flex-start', gap: 10 }}>
                  <Ionicons name={item.icon} size={16} color={C.accent} style={{ marginTop: 2 }} />
                  <Text style={{ color: C.textSec, fontSize: 13, flex: 1, lineHeight: 20 }}>{item.text}</Text>
                </View>
              ))}
            </View>
          </View>
        </View>
      )}
    </PublicPageShell>
  );
}
