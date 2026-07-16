import React, { useEffect, useState, useCallback } from 'react';
import { View, Text, TouchableOpacity, ActivityIndicator, ScrollView, useWindowDimensions, Platform, TextInput } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import AutoFixBanner from './AutoFixBanner';
import UpcomingInterviewsWidget from './UpcomingInterviewsWidget';
import { StalledBadge, StalledModal, DuplicatesBadge, DuplicatesModal, PortalLinkButton, ScorecardsSection } from './CareerEnhancements';
import ApplicantThreadPanel from './ApplicantThreadPanel';
import ApplicantEngagementStrip from './ApplicantEngagementStrip';
import { ResumeScoreBadge, ViewToggle, KanbanBoard, BulkActionsToolbar, GDPRRetentionPanel, GDPRButton } from './CareerTier1';
import CareerSchedulingAvailability from './CareerSchedulingAvailability';
import CareerTZHeatmap from './CareerTZHeatmap';
import api from '../../services/api';
import { useLanguage } from '../../i18n/LanguageContext';

import { useAdminTheme } from '../../hooks/useAdminTheme';
import { useHybridPolling } from '../../hooks/useHybridPolling';
// Fallback colors for helper components defined outside the main component
const AC = {
  bg: 'var(--app-bg)' as any, bgAlt: 'var(--app-surface)' as any, card: 'var(--app-card-bg)' as any, surface: 'var(--app-surface)' as any, surfaceHover: 'var(--app-surface-hover)' as any, border: 'var(--app-border)' as any, borderStrong: 'var(--app-border-strong)' as any,
  text: 'var(--app-text)' as any, textSec: 'var(--app-text-sec)' as any, textMuted: 'var(--app-text-muted)' as any, textDim: 'var(--app-text-muted)' as any, primaryText: 'var(--app-primary-text)' as any,
  primary: 'var(--app-primary)' as any, primarySoft: 'var(--app-primary-soft)' as any,
  accent: 'var(--app-primary)' as any, accentSoft: 'var(--app-primary-soft)' as any,
  success: 'var(--app-success)' as any, successText: 'var(--app-success)', successSoft: 'var(--app-success-soft)' as any,
  warning: 'var(--app-warning)' as any, warningText: 'var(--app-warning)', warningSoft: 'var(--app-warning-soft)' as any,
  error: 'var(--app-error)' as any, errorSoft: 'var(--app-error-soft)' as any,
  overlay: 'rgba(8,14,36,0.72)' as any,
};
const API = typeof window !== 'undefined' && (`https://${window.location.host}`) ? '' : (process.env.EXPO_PUBLIC_API_URL || process.env.REACT_APP_BACKEND_URL || '');

interface ApplicationDocument {
  file_id: string;
  filename: string;
  type: string;
  url: string;
}

interface Application {
  application_id: string;
  full_name: string;
  email: string;
  phone?: string;
  position: string;
  department?: string;
  cover_letter?: string;
  linkedin_url?: string;
  portfolio_url?: string;
  experience_years?: string;
  how_heard?: string;
  status: string;
  submitted_at: string;
  admin_notes?: string;
  status_updated_at?: string;
  documents?: ApplicationDocument[];
  attachments?: {
    attachment_id: string;
    filename: string;
    size: number;
    content_type: string;
    kind: string;
    url: string;
  }[];
  attachment_count?: number;
  unread_applicant_replies?: number;
  last_applicant_reply_at?: string;
  interview?: {
    date: string;
    time: string;
    type: string;
    notes: string;
    room_id: string;
    video_url: string;
    candidate_response?: 'pending' | 'accepted' | 'reschedule_requested';
    responded_at?: string;
    reschedule_reason?: string;
    proposed_slots?: { date: string; time: string }[];
  };
  recordings?: {
    recording_id: string;
    url: string;
    recorded_by: string;
    created_at: string;
    duration_sec: number;
  }[];
  ai_analysis?: {
    transcript: string;
    analysis: {
      summary: string;
      key_points: string[];
      strengths: string[];
      weaknesses: string[];
      communication_score: number;
      technical_score: number;
      cultural_fit_score: number;
      overall_score: number;
      recommendation: string;
      recommendation_reason: string;
    };
    recording_id: string;
    analyzed_at: string;
  };
}

interface Stats {
  total: number;
  by_status: Record<string, number>;
  recent_7d: number;
  by_position: Record<string, number>;
}

const tx = (_key: string, fallback: string) => fallback;

const ALL_STATUSES = ['received', 'under_review', 'interview', 'offer', 'rejected'];

const STATUS_CONFIG: Record<string, { labelKey: string; color: string; bg: string; icon: string }> = {
  received: { labelKey: 'careerApplications.status.received', color: 'var(--app-primary)', bg: 'var(--app-primary-soft)', icon: 'mail' },
  under_review: { labelKey: 'careerApplications.status.underReview', color: 'var(--app-warning)', bg: 'var(--app-warning-soft)', icon: 'search' },
  interview: { labelKey: 'careerApplications.status.interview', color: 'var(--app-info)', bg: 'var(--app-info-soft)', icon: 'videocam' },
  offer: { labelKey: 'careerApplications.status.offer', color: 'var(--app-success)', bg: 'var(--app-success-soft)', icon: 'trophy' },
  rejected: { labelKey: 'careerApplications.status.rejected', color: 'var(--app-error)', bg: 'var(--app-error-soft)', icon: 'close-circle' },
};

function StatusBadge({ status }: { status: string }) {
  const { t } = useLanguage();
  const cfg = STATUS_CONFIG[status] || STATUS_CONFIG.received;
  return (
    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 5, backgroundColor: cfg.bg, paddingHorizontal: 10, paddingVertical: 4, borderRadius: 14, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(cfg.color, '30') }}>
      <Ionicons name={cfg.icon as any} size={11} color={cfg.color} />
      <Text style={{ color: cfg.color, fontSize: 11, fontWeight: '700' }}>{t(cfg.labelKey)}</Text>
    </View>
  );
}

const RESPONSE_CONFIG: Record<string, { labelKey: string; color: string; bg: string; icon: string }> = {
  accepted: { labelKey: 'careerApplications.response.accepted', color: 'var(--app-success)', bg: 'var(--app-success-soft)', icon: 'checkmark-circle' },
  reschedule_requested: { labelKey: 'careerApplications.response.rescheduleRequested', color: 'var(--app-warning)', bg: 'var(--app-warning-soft)', icon: 'sync' },
};

function InterviewResponseChip({ interview, onPress, testId }: {
  interview?: Application['interview'];
  onPress?: () => void;
  testId: string;
}) {
  const { t } = useLanguage();
  if (!interview || !interview.candidate_response || interview.candidate_response === 'pending') return null;
  const cfg = RESPONSE_CONFIG[interview.candidate_response];
  if (!cfg) return null;
  const when = interview.responded_at
    ? new Date(interview.responded_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
    : '';
  const Wrapper: any = onPress ? TouchableOpacity : View;
  const wrapperProps = onPress ? { onPress: (e: any) => { e?.stopPropagation?.(); onPress(); }, activeOpacity: 0.75 } : {};
  return (
    <Wrapper
      {...wrapperProps}
      data-testid={testId}
      testID={testId}
      style={{ flexDirection: 'row', alignItems: 'center', gap: 5, backgroundColor: cfg.bg, paddingHorizontal: 10, paddingVertical: 4, borderRadius: 14, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(cfg.color, '50') }}
    >
      <Ionicons name={cfg.icon as any} size={11} color={cfg.color} />
      <Text allowFontScaling={false} style={{ color: cfg.color, fontSize: 11, fontWeight: '700' } as any}>{t(cfg.labelKey)}</Text>
      {when ? <Text allowFontScaling={false} style={{ color: cfg.color, fontSize: 10, fontWeight: '500', opacity: 0.75 } as any}>· {when}</Text> : null}
      {interview.candidate_response === 'reschedule_requested' && (
        (interview.proposed_slots?.length || 0) > 0 ? (
          <View style={{ marginLeft: 2, paddingHorizontal: 5, paddingVertical: 1, borderRadius: 8, backgroundColor: cfg.color }}>
            <Text style={{ color: 'var(--app-primary-text)', fontSize: 9, fontWeight: '800' }}>{interview.proposed_slots?.length}</Text>
          </View>
        ) : null
      )}
    </Wrapper>
  );
}

function RescheduleDetailsModal({ app, onClose, onOpenStudio }: { app: Application; onClose: () => void; onOpenStudio: () => void }) {
  const iv = app.interview!;
  const slots = iv.proposed_slots || [];
  return (
    <View style={{ position: 'absolute' as any, top: 0, left: 0, right: 0, bottom: 0, backgroundColor: AC.overlay, zIndex: 520, justifyContent: 'center', alignItems: 'center', padding: 20 }} data-testid="reschedule-details-modal" testID="reschedule-details-modal">
      <View style={{ backgroundColor: AC.bgAlt, borderRadius: 14, padding: 22, width: '100%', maxWidth: 520, borderWidth: 1, borderColor: AC.borderStrong }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14 }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
            <Ionicons name="sync" size={18} color={'var(--app-warning)'} />
            <Text style={{ color: AC.text, fontSize: 16, fontWeight: '800' }}>{tx('admin.careerApplicationsPanel.auto.text.001', 'Reschedule requested')}</Text>
          </View>
          <TouchableOpacity onPress={onClose} data-testid="reschedule-details-close" testID="reschedule-details-close">
            <Ionicons name="close" size={20} color={AC.textDim} />
          </TouchableOpacity>
        </View>
        <Text style={{ color: AC.textDim, fontSize: 12, marginBottom: 14 }}>
          {app.full_name} asked to move the interview for <Text style={{ color: AC.text, fontWeight: '600' }}>{app.position}</Text>.
        </Text>
        <View style={{ backgroundColor: 'var(--app-warning-soft)', borderRadius: 10, padding: 12, borderLeftWidth: 3, borderLeftColor: 'var(--app-warning)', marginBottom: 14 }}>
          <Text style={{ color: 'var(--app-warning)', fontSize: 11, fontWeight: '700', marginBottom: 4, textTransform: 'uppercase', letterSpacing: 0.4 }}>{tx('admin.careerApplicationsPanel.auto.text.002', 'Original slot')}</Text>
          <Text style={{ color: AC.text, fontSize: 13 }}>{iv.date} · {iv.time} UTC ({iv.type})</Text>
        </View>
        {iv.reschedule_reason ? (
          <View style={{ marginBottom: 14 }}>
            <Text style={{ color: AC.textDim, fontSize: 11, fontWeight: '700', marginBottom: 4, textTransform: 'uppercase', letterSpacing: 0.4 }}>{tx('admin.careerApplicationsPanel.auto.text.003', 'Reason')}</Text>
            <Text style={{ color: AC.text, fontSize: 13, lineHeight: 19, fontStyle: 'italic' }}>"{iv.reschedule_reason}"</Text>
          </View>
        ) : null}
        {slots.length > 0 ? (
          <View style={{ marginBottom: 14 }}>
            <Text style={{ color: AC.textDim, fontSize: 11, fontWeight: '700', marginBottom: 6, textTransform: 'uppercase', letterSpacing: 0.4 }}>Proposed slots ({slots.length})</Text>
            {slots.map((s, i) => (
              <View key={i} style={{ flexDirection: 'row', alignItems: 'center', gap: 8, paddingVertical: 6, paddingHorizontal: 10, backgroundColor: AC.border, borderRadius: 8, marginBottom: 4 }}>
                <Ionicons name="time-outline" size={12} color={AC.textDim} />
                <Text style={{ color: AC.text, fontSize: 12, fontWeight: '600' }}>{s.date}</Text>
                <Text style={{ color: AC.textDim, fontSize: 12 }}>at {s.time} UTC</Text>
              </View>
            ))}
          </View>
        ) : null}
        <View style={{ flexDirection: 'row', gap: 10, marginTop: 4 }}>
          <TouchableOpacity onPress={onClose} style={{ flex: 1, paddingVertical: 11, borderRadius: 10, borderWidth: 1, borderColor: AC.borderStrong, alignItems: 'center' }} data-testid="reschedule-dismiss-btn" testID="reschedule-dismiss-btn">
            <Text style={{ color: AC.text, fontWeight: '700', fontSize: 13 }}>{tx('admin.careerApplicationsPanel.auto.text.004', 'Dismiss')}</Text>
          </TouchableOpacity>
          <TouchableOpacity onPress={onOpenStudio} style={{ flex: 2, paddingVertical: 11, borderRadius: 10, backgroundColor: AC.primary, alignItems: 'center', flexDirection: 'row', justifyContent: 'center', gap: 6 }} data-testid="reschedule-open-studio-btn" testID="reschedule-open-studio-btn">
            <Ionicons name="arrow-forward-circle" size={13} color="var(--app-primary-text)" />
            <Text style={{ color: 'var(--app-primary-text)', fontWeight: '800', fontSize: 13 }}>{tx('admin.careerApplicationsPanel.auto.text.005', 'Open application')}</Text>
          </TouchableOpacity>
        </View>
      </View>
    </View>
  );
}

const COMPARE_COLORS = ['var(--app-primary)', 'var(--app-success)', 'var(--app-warning)', 'var(--app-info)'];
const RADAR_AXES = [
  { key: 'communication_score', label: 'Communication' },
  { key: 'technical_score', label: 'Technical' },
  { key: 'cultural_fit_score', label: 'Cultural Fit' },
  { key: 'overall_score', label: 'Overall' },
];

function RadarChart({ candidates }: { candidates: Application[] }) {
  const size = 260;
  const cx = size / 2;
  const cy = size / 2;
  const maxR = 100;
  const levels = [2, 4, 6, 8, 10];

  const angleStep = (2 * Math.PI) / RADAR_AXES.length;
  const startAngle = -Math.PI / 2;

  const getPoint = (axisIdx: number, value: number) => {
    const angle = startAngle + axisIdx * angleStep;
    const r = (value / 10) * maxR;
    return { x: cx + r * Math.cos(angle), y: cy + r * Math.sin(angle) };
  };

  const gridLines = levels.map(level => {
    const pts = RADAR_AXES.map((_, i) => getPoint(i, level));
    return pts.map(p => `${p.x},${p.y}`).join(' ');
  });

  const axisLines = RADAR_AXES.map((_, i) => {
    const p = getPoint(i, 10);
    return { x1: cx, y1: cy, x2: p.x, y2: p.y };
  });

  const labelPositions = RADAR_AXES.map((ax, i) => {
    const p = getPoint(i, 11.8);
    return { ...p, label: ax.label };
  });

  const candidatePolygons = candidates.map((c, ci) => {
    const analysis = c.ai_analysis?.analysis;
    if (!analysis) return null;
    const pts = RADAR_AXES.map((ax, i) => {
      const val = (analysis as any)[ax.key] || 0;
      return getPoint(i, val);
    });
    return {
      points: pts.map(p => `${p.x},${p.y}`).join(' '),
      color: COMPARE_COLORS[ci % COMPARE_COLORS.length],
    };
  });

  if (Platform.OS !== 'web') return null;

  return (
    <View style={{ alignItems: 'center', marginVertical: 8 }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        {gridLines.map((pts, i) => (
          <polygon key={i} points={pts} fill="none" stroke={AC.border} strokeWidth={0.8} opacity={0.6} />
        ))}
        {axisLines.map((l, i) => (
          <line key={i} x1={l.x1} y1={l.y1} x2={l.x2} y2={l.y2} stroke={AC.border} strokeWidth={0.6} opacity={0.5} />
        ))}
        {candidatePolygons.map((cp, i) => cp && (
          <React.Fragment key={i}>
            <polygon points={cp.points} fill={cp.color} fillOpacity={0.12} stroke={cp.color} strokeWidth={2} />
            {RADAR_AXES.map((ax, j) => {
              const val = (candidates[i].ai_analysis?.analysis as any)?.[ax.key] || 0;
              const p = getPoint(j, val);
              return <circle key={j} cx={p.x} cy={p.y} r={3.5} fill={cp.color} />;
            })}
          </React.Fragment>
        ))}
        {labelPositions.map((lp, i) => (
          <text key={i} x={lp.x} y={lp.y} fill={AC.textSec} fontSize={10} fontWeight="600" textAnchor="middle" dominantBaseline="middle">{lp.label}</text>
        ))}
      </svg>
    </View>
  );
}

function CompareModal({ candidates, onClose }: { candidates: Application[]; onClose: () => void }) {
  const { width } = useWindowDimensions();
  const m = width < 768;
  const [exporting, setExporting] = useState(false);
  const [showEmailForm, setShowEmailForm] = useState(false);
  const [emailTo, setEmailTo] = useState('');
  const [emailMsg, setEmailMsg] = useState('');
  const [sending, setSending] = useState(false);
  const [emailStatus, setEmailStatus] = useState('');

  const recLabel = (r: string) => ({ strong_hire: 'Strong Hire', hire: 'Hire', maybe: 'Maybe', no_hire: 'No Hire' }[r] || r);
  const recColor = (r: string) => ({ strong_hire: 'var(--app-success)', hire: 'var(--app-primary)', maybe: 'var(--app-warning)', no_hire: 'var(--app-error)' }[r] || AC.textDim);

  const handleExportPdf = async () => {
    setExporting(true);
    try {
      const res = await api.post(
        '/careers/comparison/export-pdf',
        { application_ids: candidates.map(c => c.application_id) },
        { responseType: 'blob' },
      );
      const blob = res.data as Blob;
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `candidate-comparison-${new Date().toISOString().slice(0, 10)}.pdf`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch { /* silent */ }
    setExporting(false);
  };

  const handleShareEmail = async () => {
    const recipients = emailTo.split(',').map(e => e.trim()).filter(e => e.includes('@'));
    if (recipients.length === 0) { setEmailStatus('Enter at least one valid email.'); return; }
    setSending(true);
    setEmailStatus('');
    try {
      const res = await api.post('/careers/comparison/share-email', {
        application_ids: candidates.map(c => c.application_id),
        recipients,
        message: emailMsg,
      });
      const data = res.data;
      if (data.success) {
        setEmailStatus(`Sent to ${data.sent.length} recipient(s)!`);
        setTimeout(() => { setShowEmailForm(false); setEmailStatus(''); setEmailTo(''); setEmailMsg(''); }, 2000);
      } else {
        setEmailStatus(data.message || 'Failed to send.');
      }
    } catch {
      setEmailStatus('Failed to connect.');
    }
    setSending(false);
  };

  return (
    <View style={{ position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, backgroundColor: AC.overlay, zIndex: 200, justifyContent: 'center', alignItems: 'center', padding: 16 }} data-testid="compare-modal" testID="compare-modal">
      <View style={{ backgroundColor: AC.bgAlt, borderRadius: 16, width: '100%', maxWidth: 960, maxHeight: '95%', borderWidth: 1, borderColor: AC.borderStrong }}>
        <ScrollView style={{ padding: m ? 16 : 24 }}>
          {/* Header */}
          <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
            <View>
              <Text style={{ color: AC.text, fontSize: 18, fontWeight: '800' }}>{tx('admin.careerApplicationsPanel.auto.text.006', 'Candidate Comparison')}</Text>
              <Text style={{ color: AC.textDim, fontSize: 12, marginTop: 2 }}>{candidates.length} candidates selected</Text>
            </View>
            <TouchableOpacity onPress={onClose} style={{ width: 32, height: 32, borderRadius: 16, backgroundColor: AC.border, justifyContent: 'center', alignItems: 'center' }} data-testid="close-compare-modal" testID="close-compare-modal">
              <Ionicons name="close" size={16} color={AC.textSec} />
            </TouchableOpacity>
          </View>

          {/* Legend */}
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 12, marginBottom: 12 }}>
            {candidates.map((c, i) => (
              <View key={c.application_id} style={{ flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: (globalThis as any).__alphaColor(COMPARE_COLORS[i], '15'), paddingHorizontal: 10, paddingVertical: 5, borderRadius: 8, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(COMPARE_COLORS[i], '30') }}>
                <View style={{ width: 10, height: 10, borderRadius: 5, backgroundColor: COMPARE_COLORS[i] }} />
                <Text style={{ color: COMPARE_COLORS[i], fontSize: 12, fontWeight: '700' }}>{c.full_name}</Text>
                <Text style={{ color: AC.textDim, fontSize: 10 }}>({c.position})</Text>
              </View>
            ))}
          </View>

          {/* Export PDF */}
          <View style={{ marginBottom: 16, gap: 10 }}>
            <View style={{ flexDirection: 'row', gap: 10 }}>
              <TouchableOpacity
                onPress={handleExportPdf}
                disabled={exporting}
                data-testid="export-pdf-btn" testID="export-pdf-btn"
                style={{ flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, paddingVertical: 10, borderRadius: 10, backgroundColor: exporting ? AC.border : 'var(--app-border)', opacity: exporting ? 0.7 : 1 }}
              >
                {exporting ? (
                  <ActivityIndicator size="small" color={'var(--app-primary-soft)'} />
                ) : (
                  <Ionicons name="document-text" size={15} color={AC.primaryText} />
                )}
                <Text style={{ color: AC.primaryText, fontSize: 13, fontWeight: '700' }}>{exporting ? 'Generating PDF...' : 'Export PDF'}</Text>
              </TouchableOpacity>
              <TouchableOpacity
                onPress={() => setShowEmailForm(!showEmailForm)}
                data-testid="share-email-btn" testID="share-email-btn"
                style={{ flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, paddingVertical: 10, borderRadius: 10, backgroundColor: showEmailForm ? 'var(--app-success-soft)' : AC.border, borderWidth: 1, borderColor: showEmailForm ? 'var(--app-success)' : AC.borderStrong }}
              >
                <Ionicons name="mail" size={15} color={showEmailForm ? 'var(--app-success)' : AC.textMuted} />
                <Text style={{ color: showEmailForm ? 'var(--app-success)' : AC.textMuted, fontSize: 13, fontWeight: '700' }}>{tx('admin.careerApplicationsPanel.auto.text.007', 'Share via Email')}</Text>
              </TouchableOpacity>
            </View>

            {/* Email Form */}
            {showEmailForm && (
              <View style={{ backgroundColor: AC.border, borderRadius: 10, padding: 14, borderWidth: 1, borderColor: AC.borderStrong }} data-testid="email-share-form" testID="email-share-form">
                <Text style={{ color: AC.textDim, fontSize: 10, fontWeight: '700', letterSpacing: 0.5, marginBottom: 8 }}>{tx('admin.careerApplicationsPanel.auto.text.008', 'SEND REPORT VIA EMAIL')}</Text>
                <TextInput
                  value={emailTo}
                  onChangeText={setEmailTo}
                  placeholder={tx('admin.careerApplicationsPanel.auto.placeholder.001', 'Recipient emails (comma-separated)')}
                  placeholderTextColor="var(--app-text-sec)"
                  data-testid="email-recipients-input" testID="email-recipients-input"
                  style={{ backgroundColor: AC.bgAlt, borderRadius: 8, padding: 10, color: AC.text, fontSize: 13, marginBottom: 8, borderWidth: 1, borderColor: AC.borderStrong } as any}
                />
                <TextInput
                  value={emailMsg}
                  onChangeText={setEmailMsg}
                  placeholder={tx('admin.careerApplicationsPanel.auto.placeholder.002', 'Optional message for recipients...')}
                  placeholderTextColor="var(--app-text-sec)"
                  multiline
                  numberOfLines={2}
                  data-testid="email-message-input" testID="email-message-input"
                  style={{ backgroundColor: AC.bgAlt, borderRadius: 8, padding: 10, color: AC.text, fontSize: 13, marginBottom: 10, borderWidth: 1, borderColor: AC.borderStrong, minHeight: 50 } as any}
                />
                {emailStatus ? <Text style={{ color: emailStatus.includes('Sent') ? 'var(--app-success)' : 'var(--app-error)', fontSize: 12, fontWeight: '600', marginBottom: 8 }}>{emailStatus}</Text> : null}
                <TouchableOpacity
                  onPress={handleShareEmail}
                  disabled={sending || !emailTo.trim()}
                  data-testid="send-email-btn" testID="send-email-btn"
                  style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, paddingVertical: 10, borderRadius: 8, backgroundColor: sending || !emailTo.trim() ? AC.border : 'var(--app-success)', opacity: sending || !emailTo.trim() ? 0.6 : 1 }}
                >
                  {sending ? <ActivityIndicator size="small" color={'var(--app-success)'} /> : <Ionicons name="send" size={14} color={AC.primaryText} />}
                  <Text style={{ color: AC.primaryText, fontSize: 13, fontWeight: '700' }}>{sending ? 'Sending...' : 'Send Report'}</Text>
                </TouchableOpacity>
              </View>
            )}
          </View>

          {/* Radar Chart */}
          <View style={{ backgroundColor: AC.border, borderRadius: 12, padding: 16, marginBottom: 16, borderWidth: 1, borderColor: AC.borderStrong, alignItems: 'center' }}>
            <Text style={{ color: AC.textDim, fontSize: 10, fontWeight: '700', letterSpacing: 0.5, marginBottom: 8 }}>{tx('admin.careerApplicationsPanel.auto.text.009', 'SCORE COMPARISON')}</Text>
            <RadarChart candidates={candidates} />
          </View>

          {/* Score Table */}
          <View style={{ backgroundColor: AC.border, borderRadius: 12, overflow: 'hidden', marginBottom: 16, borderWidth: 1, borderColor: AC.borderStrong }}>
            {/* Table Header */}
            <View style={{ flexDirection: 'row', backgroundColor: AC.bgAlt, padding: 12 }}>
              <Text style={{ flex: 1.5, color: AC.textDim, fontSize: 10, fontWeight: '700', letterSpacing: 0.5 }}>{tx('admin.careerApplicationsPanel.auto.text.010', 'METRIC')}</Text>
              {candidates.map((c, i) => (
                <Text key={c.application_id} style={{ flex: 1, color: COMPARE_COLORS[i], fontSize: 10, fontWeight: '700', textAlign: 'center' }}>{c.full_name.split(' ')[0]}</Text>
              ))}
            </View>
            {/* Score Rows */}
            {[...RADAR_AXES, { key: 'recommendation', label: 'Recommendation' }].map((ax, ri) => (
              <View key={ax.key} style={{ flexDirection: 'row', padding: 12, borderTopWidth: 1, borderTopColor: AC.bgAlt, alignItems: 'center' }}>
                <Text style={{ flex: 1.5, color: AC.textSec, fontSize: 12, fontWeight: '600' }}>{ax.label}</Text>
                {candidates.map((c, ci) => {
                  const analysis = c.ai_analysis?.analysis;
                  if (ax.key === 'recommendation') {
                    const rec = analysis?.recommendation || 'N/A';
                    return (
                      <View key={c.application_id} style={{ flex: 1, alignItems: 'center' }}>
                        <Text style={{ color: recColor(rec), fontSize: 11, fontWeight: '800', textTransform: 'uppercase' }}>{recLabel(rec)}</Text>
                      </View>
                    );
                  }
                  const score = (analysis as any)?.[ax.key] || 0;
                  const isMax = candidates.every((other, oi) => oi === ci || ((other.ai_analysis?.analysis as any)?.[ax.key] || 0) <= score);
                  return (
                    <View key={c.application_id} style={{ flex: 1, alignItems: 'center' }}>
                      <Text style={{ color: isMax && candidates.length > 1 ? COMPARE_COLORS[ci] : AC.text, fontSize: 14, fontWeight: isMax ? '900' : '600' }}>
                        {score}<Text style={{ fontSize: 10, color: AC.textDim }}>/10</Text>
                      </Text>
                    </View>
                  );
                })}
              </View>
            ))}
          </View>

          {/* Summary Comparison */}
          <View style={{ gap: 12, marginBottom: 16 }}>
            <Text style={{ color: AC.textDim, fontSize: 10, fontWeight: '700', letterSpacing: 0.5 }}>{tx('admin.careerApplicationsPanel.auto.text.011', 'SUMMARIES')}</Text>
            {candidates.map((c, i) => (
              <View key={c.application_id} style={{ backgroundColor: AC.border, borderRadius: 10, padding: 14, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(COMPARE_COLORS[i], '30'), borderLeftWidth: 3, borderLeftColor: COMPARE_COLORS[i] }}>
                <Text style={{ color: COMPARE_COLORS[i], fontSize: 12, fontWeight: '700', marginBottom: 6 }}>{c.full_name}</Text>
                <Text style={{ color: AC.textSec, fontSize: 12, lineHeight: 18 }}>{c.ai_analysis?.analysis.summary || 'No summary available.'}</Text>
              </View>
            ))}
          </View>

          {/* Strengths & Weaknesses Grid */}
          <View style={{ flexDirection: m ? 'column' : 'row', gap: 12, marginBottom: 16 }}>
            {/* Strengths Column */}
            <View style={{ flex: 1 }}>
              <Text style={{ color: AC.successText, fontSize: 10, fontWeight: '700', letterSpacing: 0.5, marginBottom: 8 }}>{tx('admin.careerApplicationsPanel.auto.text.012', 'STRENGTHS')}</Text>
              {candidates.map((c, i) => (
                <View key={c.application_id} style={{ marginBottom: 10 }}>
                  <Text style={{ color: COMPARE_COLORS[i], fontSize: 11, fontWeight: '700', marginBottom: 4 }}>{c.full_name.split(' ')[0]}</Text>
                  {(c.ai_analysis?.analysis.strengths || []).map((s: string, si: number) => (
                    <View key={si} style={{ flexDirection: 'row', gap: 5, marginBottom: 3 }}>
                      <Ionicons name="checkmark-circle" size={11} color={'var(--app-success)'} style={{ marginTop: 2 }} />
                      <Text style={{ color: AC.textSec, fontSize: 11, lineHeight: 16, flex: 1 }}>{s}</Text>
                    </View>
                  ))}
                </View>
              ))}
            </View>
            {/* Weaknesses Column */}
            <View style={{ flex: 1 }}>
              <Text style={{ color: AC.warningText, fontSize: 10, fontWeight: '700', letterSpacing: 0.5, marginBottom: 8 }}>{tx('admin.careerApplicationsPanel.auto.text.013', 'AREAS FOR IMPROVEMENT')}</Text>
              {candidates.map((c, i) => (
                <View key={c.application_id} style={{ marginBottom: 10 }}>
                  <Text style={{ color: COMPARE_COLORS[i], fontSize: 11, fontWeight: '700', marginBottom: 4 }}>{c.full_name.split(' ')[0]}</Text>
                  {(c.ai_analysis?.analysis.weaknesses || []).map((w: string, wi: number) => (
                    <View key={wi} style={{ flexDirection: 'row', gap: 5, marginBottom: 3 }}>
                      <Ionicons name="alert-circle" size={11} color={'var(--app-warning)'} style={{ marginTop: 2 }} />
                      <Text style={{ color: AC.textSec, fontSize: 11, lineHeight: 16, flex: 1 }}>{w}</Text>
                    </View>
                  ))}
                </View>
              ))}
            </View>
          </View>

          {/* Recommendation Reason */}
          <View style={{ gap: 12, marginBottom: 20 }}>
            <Text style={{ color: AC.textDim, fontSize: 10, fontWeight: '700', letterSpacing: 0.5 }}>{tx('admin.careerApplicationsPanel.auto.text.014', 'RECOMMENDATION REASONING')}</Text>
            {candidates.map((c, i) => {
              const rec = c.ai_analysis?.analysis.recommendation || 'N/A';
              return (
                <View key={c.application_id} style={{ backgroundColor: (globalThis as any).__alphaColor(recColor(rec), '10'), borderRadius: 10, padding: 14, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(recColor(rec), '25') }}>
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 6 }}>
                    <View style={{ width: 10, height: 10, borderRadius: 5, backgroundColor: COMPARE_COLORS[i] }} />
                    <Text style={{ color: COMPARE_COLORS[i], fontSize: 12, fontWeight: '700' }}>{c.full_name}</Text>
                    <View style={{ backgroundColor: (globalThis as any).__alphaColor(recColor(rec), '20'), paddingHorizontal: 8, paddingVertical: 2, borderRadius: 10 }}>
                      <Text style={{ color: recColor(rec), fontSize: 10, fontWeight: '800', textTransform: 'uppercase' }}>{recLabel(rec)}</Text>
                    </View>
                  </View>
                  <Text style={{ color: AC.textSec, fontSize: 12, lineHeight: 18 }}>{c.ai_analysis?.analysis.recommendation_reason || 'No reason provided.'}</Text>
                </View>
              );
            })}
          </View>
        </ScrollView>
      </View>
    </View>
  );
}

function StatCard({ label, value, icon, color }: { label: string; value: number | string; icon: string; color: string }) {
  return (
    <View style={{ flex: 1, minWidth: 140, backgroundColor: AC.bgAlt, borderRadius: 12, padding: 16, borderWidth: 1, borderColor: AC.border }} data-testid={`stat-${label.toLowerCase().replace(/\s/g, '-')}`} testID={`stat-${label.toLowerCase().replace(/\s/g, '-')}`}>
      <View style={{ width: 32, height: 32, borderRadius: 8, backgroundColor: (globalThis as any).__alphaColor(color, '18'), justifyContent: 'center', alignItems: 'center', marginBottom: 10 }}>
        <Ionicons name={icon as any} size={16} color={color} />
      </View>
      <Text style={{ fontSize: 24, fontWeight: '800', color: AC.text, letterSpacing: -0.5 }}>{value}</Text>
      <Text style={{ fontSize: 11, color: AC.textDim, marginTop: 2, fontWeight: '600' }}>{label}</Text>
    </View>
  );
}

function DetailModal({ app, onClose, onStatusUpdate, onRefresh }: { app: Application; onClose: () => void; onStatusUpdate: (id: string, status: string, sendEmail: boolean, notes: string, interview?: { date: string; time: string; type: string; notes: string }) => Promise<void>; onRefresh: () => Promise<void> }) {
  const { width } = useWindowDimensions();
  const m = width < 640;
  const [newStatus, setNewStatus] = useState(app.status);
  const [sendEmail, setSendEmail] = useState(true);
  const [notes, setNotes] = useState(app.admin_notes || '');
  const [updating, setUpdating] = useState(false);
  const [message, setMessage] = useState('');
  const [aiSuggesting, setAiSuggesting] = useState(false);
  const [aiTone, setAiTone] = useState<'professional' | 'warm' | 'direct'>('professional');

  const handleAiSuggestNote = async () => {
    setAiSuggesting(true);
    setMessage('');
    try {
      const res = await api.post(`/careers/applications/${app.application_id}/ai-suggest-note`, {
        status: newStatus, tone: aiTone, seed: notes || undefined,
      });
      const data = res.data || {};
      if (data.success && data.note) {
        setNotes(data.note);
      } else {
        setMessage('AI could not draft a note — please try again.');
      }
    } catch (e: any) {
      setMessage(e?.response?.data?.detail || 'AI suggestion failed — please try again.');
    }
    setAiSuggesting(false);
  };
  const [intDate, setIntDate] = useState(app.interview?.date || '');
  const [intTime, setIntTime] = useState(app.interview?.time || '');
  const [intType, setIntType] = useState(app.interview?.type || 'in-app-video');
  const [intNotes, setIntNotes] = useState(app.interview?.notes || '');
  const [analyzing, setAnalyzing] = useState(false);
  const [analysisMsg, setAnalysisMsg] = useState('');

  const handleAnalyze = async () => {
    setAnalyzing(true);
    setAnalysisMsg('');
    try {
      const res = await api.post(`/careers/interview/analyze/${app.application_id}`);
      const data = res.data;
      if (data.success) {
        setAnalysisMsg('Analysis complete!');
        await onRefresh();
      } else {
        setAnalysisMsg(data.message || 'Analysis failed.');
      }
    } catch {
      setAnalysisMsg('Failed to connect to analysis service.');
    }
    setAnalyzing(false);
  };

  const handleUpdate = async () => {
    if (newStatus === app.status && !notes && newStatus !== 'interview') return;
    setUpdating(true);
    setMessage('');
    try {
      const interview = newStatus === 'interview' && intDate ? { date: intDate, time: intTime, type: intType, notes: intNotes } : undefined;
      await onStatusUpdate(app.application_id, newStatus, sendEmail, notes, interview);
      setMessage('Status updated successfully!');
    } catch {
      setMessage('Failed to update status.');
    }
    setUpdating(false);
  };

  return (
    <View style={{ position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, backgroundColor: AC.overlay, zIndex: 100, justifyContent: 'center', alignItems: 'center', padding: 16 }} data-testid="application-detail-modal" testID="application-detail-modal">
      <View style={{ backgroundColor: AC.border, borderRadius: 16, width: '100%', maxWidth: 600, maxHeight: '90%', borderWidth: 1, borderColor: AC.borderStrong }}>
        <ScrollView style={{ padding: m ? 16 : 24 }}>
          {/* Header */}
          <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 20 }}>
            <View style={{ flex: 1 }}>
              <Text style={{ color: AC.text, fontSize: 18, fontWeight: '800' }}>{app.full_name}</Text>
              <Text style={{ color: AC.textMuted, fontSize: 13, marginTop: 2 }}>{app.position}</Text>
            </View>
            <TouchableOpacity onPress={onClose} style={{ width: 32, height: 32, borderRadius: 16, backgroundColor: AC.borderStrong, justifyContent: 'center', alignItems: 'center' }} data-testid="close-detail-modal" testID="close-detail-modal">
              <Ionicons name="close" size={16} color={AC.textSec} />
            </TouchableOpacity>
          </View>

          {/* Status */}
          <View style={{ marginBottom: 20 }}>
            <StatusBadge status={app.status} />
            {app.status_updated_at && (
              <Text style={{ color: AC.textDim, fontSize: 11, marginTop: 6 }}>Last updated: {new Date(app.status_updated_at).toLocaleDateString()}</Text>
            )}
          </View>

          {/* Engagement strip (Resend events + candidate-view iframe preview) */}
          <ApplicantEngagementStrip applicationId={app.application_id} />

          {/* Info Grid */}
          <View style={{ gap: 12, marginBottom: 20 }}>
            {[
              { label: 'Application ID', value: app.application_id, mono: true },
              { label: 'Email', value: app.email },
              { label: 'Phone', value: app.phone || 'Not provided' },
              { label: 'Experience', value: app.experience_years || 'Not provided' },
              { label: 'LinkedIn', value: app.linkedin_url || 'Not provided', link: app.linkedin_url },
              { label: 'Portfolio', value: app.portfolio_url || 'Not provided', link: app.portfolio_url },
              { label: 'How Heard', value: app.how_heard || 'Not provided' },
              { label: 'Submitted', value: new Date(app.submitted_at).toLocaleDateString(undefined, { year: 'numeric', month: 'long', day: 'numeric' }) },
            ].map((item, i) => (
              <View key={i} style={{ backgroundColor: AC.bgAlt, borderRadius: 10, padding: 12, borderWidth: 1, borderColor: AC.border }}>
                <Text style={{ color: AC.textDim, fontSize: 10, fontWeight: '700', letterSpacing: 0.5, marginBottom: 3 }}>{item.label.toUpperCase()}</Text>
                {item.link ? (
                  Platform.OS === 'web' ? (
                    <a href={item.link} target="_blank" rel="noopener noreferrer" style={{ color: AC.primary, fontSize: 13, fontWeight: '600', textDecoration: 'none' }}>{item.value}</a>
                  ) : (
                    <Text style={{ color: AC.primary, fontSize: 13, fontWeight: '600' }}>{item.value}</Text>
                  )
                ) : (
                  <Text style={{ color: AC.text, fontSize: 13, fontWeight: '600', fontFamily: item.mono ? 'monospace' : undefined }}>{item.value}</Text>
                )}
              </View>
            ))}
          </View>

          {/* Cover Letter */}
          {app.cover_letter && (
            <View style={{ backgroundColor: AC.bgAlt, borderRadius: 10, padding: 14, marginBottom: 20, borderWidth: 1, borderColor: AC.border }}>
              <Text style={{ color: AC.textDim, fontSize: 10, fontWeight: '700', letterSpacing: 0.5, marginBottom: 6 }}>{tx('admin.careerApplicationsPanel.auto.text.015', 'COVER LETTER')}</Text>
              <Text style={{ color: AC.textSec, fontSize: 13, lineHeight: 20 }}>{app.cover_letter}</Text>
            </View>
          )}

          {/* Documents */}
          {app.documents && app.documents.length > 0 && (
            <View style={{ backgroundColor: AC.bgAlt, borderRadius: 12, padding: 14, marginBottom: 20, borderWidth: 1, borderColor: AC.border }} data-testid="applicant-documents" testID="applicant-documents">
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 12 }}>
                <Ionicons name="folder-open" size={15} color={'var(--app-primary)'} />
                <Text style={{ color: AC.text, fontSize: 13, fontWeight: '700' }}>Attached Documents ({app.documents.length})</Text>
              </View>
              <View style={{ gap: 8 }}>
                {app.documents.map((doc: any, i: number) => {
                  const typeLabels: Record<string, string> = { resume: 'Resume / CV', cover_letter_file: 'Cover Letter', additional: 'Additional' };
                  const ext = doc.filename?.split('.').pop()?.toUpperCase() || 'FILE';
                  return (
                    <View key={i} style={{ flexDirection: 'row', alignItems: 'center', gap: 10, backgroundColor: AC.border, borderRadius: 8, padding: 10, borderWidth: 1, borderColor: AC.borderStrong }}>
                      <View style={{ width: 36, height: 36, borderRadius: 8, backgroundColor: AC.primarySoft, justifyContent: 'center', alignItems: 'center' }}>
                        <Text style={{ color: AC.primary, fontSize: 10, fontWeight: '800' }}>{ext}</Text>
                      </View>
                      <View style={{ flex: 1 }}>
                        <Text style={{ color: AC.text, fontSize: 12, fontWeight: '600' }}>{doc.filename}</Text>
                        <Text style={{ color: AC.textDim, fontSize: 10 }}>{typeLabels[doc.type] || doc.type}</Text>
                      </View>
                      {Platform.OS === 'web' && (
                        <a href={`${API}${doc.url}`} target="_blank" rel="noopener noreferrer" download style={{ padding: '6px 12px', borderRadius: 6, backgroundColor: AC.primarySoft, textDecoration: 'none', display: 'flex', alignItems: 'center', gap: 4 }} data-testid={`download-doc-${i}`}>
                          <Ionicons name="download" size={13} color={'var(--app-primary)'} />
                          <span style={{ color: AC.primary, fontSize: 11, fontWeight: '600' }}>Download</span>
                        </a>
                      )}
                    </View>
                  );
                })}
              </View>
            </View>
          )}

          {/* Candidate Attachments (resume/portfolio/etc. uploaded at apply time) */}
          {app.attachments && app.attachments.length > 0 && (
            <View style={{ backgroundColor: AC.bgAlt, borderRadius: 12, padding: 14, marginBottom: 20, borderWidth: 1, borderColor: AC.border }} data-testid="applicant-attachments" testID="applicant-attachments">
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 12 }}>
                <Ionicons name="attach" size={15} color={'var(--app-primary)'} />
                <Text style={{ color: AC.text, fontSize: 13, fontWeight: '700' }}>Candidate Attachments ({app.attachments.length})</Text>
                <Text style={{ color: AC.textDim, fontSize: 10, marginLeft: 'auto' as any }}>
                  {(() => {
                    const tot = (app.attachments || []).reduce((n, a) => n + (a.size || 0), 0);
                    return tot < 1024 ? `${tot} B` : tot < 1024 * 1024 ? `${(tot / 1024).toFixed(1)} KB` : `${(tot / (1024 * 1024)).toFixed(1)} MB`;
                  })()}
                </Text>
              </View>
              <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
                {app.attachments.map((a) => {
                  const ext = (a.filename?.split('.').pop() || '').toUpperCase() || 'FILE';
                  const kindLabels: Record<string, string> = {
                    resume: 'Resume',
                    portfolio: 'Portfolio',
                    cover_letter: 'Cover Letter',
                    certification: 'Cert',
                    transcript: 'Transcript',
                    other: 'Other',
                  };
                  const kindColors: Record<string, string> = {
                    resume: 'var(--app-primary)',
                    portfolio: 'var(--app-primary)',
                    cover_letter: 'var(--app-primary)',
                    certification: 'var(--app-warning)',
                    transcript: 'var(--app-success)',
                    other: AC.textDim,
                  };
                  const kindCol = kindColors[a.kind] || AC.primary;
                  const isImage = (a.content_type || '').startsWith('image/');
                  const icon = isImage ? 'image' : ext === 'ZIP' ? 'archive' : 'document-text';
                  const sizeLabel = a.size < 1024 ? `${a.size} B` : a.size < 1024 * 1024 ? `${(a.size / 1024).toFixed(0)} KB` : `${(a.size / (1024 * 1024)).toFixed(1)} MB`;
                  const href = a.url?.startsWith('http') ? a.url : `${API}${a.url}`;
                  return (
                    <View
                      key={a.attachment_id}
                      style={{ flexDirection: 'row', alignItems: 'center', gap: 8, backgroundColor: AC.border, borderRadius: 999, paddingLeft: 10, paddingRight: 6, paddingVertical: 6, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(kindCol, '44'), minWidth: 200, maxWidth: 360 }}
                      data-testid={`applicant-attachment-${a.attachment_id}`}
                      testID={`applicant-attachment-${a.attachment_id}`}
                    >
                      <Ionicons name={icon as any} size={14} color={kindCol} />
                      <View style={{ flex: 1, minWidth: 0 }}>
                        <Text style={{ color: AC.text, fontSize: 11, fontWeight: '700' }} numberOfLines={1}>{a.filename}</Text>
                        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                          <Text style={{ color: kindCol, fontSize: 9, fontWeight: '800', letterSpacing: 0.4 }}>
                            {(kindLabels[a.kind] || a.kind || 'FILE').toUpperCase()}
                          </Text>
                          <Text style={{ color: AC.textDim, fontSize: 9 }}>·</Text>
                          <Text style={{ color: AC.textDim, fontSize: 9 }}>{ext}</Text>
                          <Text style={{ color: AC.textDim, fontSize: 9 }}>·</Text>
                          <Text style={{ color: AC.textDim, fontSize: 9 }}>{sizeLabel}</Text>
                        </View>
                      </View>
                      {Platform.OS === 'web' && (
                        <a
                          href={href}
                          target="_blank"
                          rel="noopener noreferrer"
                          download={a.filename}
                          style={{ width: 28, height: 28, borderRadius: 14, backgroundColor: (globalThis as any).__alphaColor(kindCol, '22'), display: 'flex', alignItems: 'center', justifyContent: 'center', textDecoration: 'none' }}
                          data-testid={`applicant-attachment-download-${a.attachment_id}`}
                          aria-label={`Download ${a.filename}`}
                        >
                          <Ionicons name="download" size={13} color={kindCol} />
                        </a>
                      )}
                    </View>
                  );
                })}
              </View>
            </View>
          )}

          {/* Interview Room Link (for admin to join) */}
          {app.interview && app.interview.type === 'in-app-video' && app.interview.video_url && (
            <View style={{ backgroundColor: AC.accentSoft, borderRadius: 12, padding: 14, marginBottom: 20, borderWidth: 1, borderColor: AC.accentSoft }} data-testid="admin-join-interview" testID="admin-join-interview">
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 10 }}>
                <Ionicons name="videocam" size={16} color={'var(--app-info)'} />
                <Text style={{ color: AC.text, fontSize: 13, fontWeight: '700' }}>{tx('admin.careerApplicationsPanel.auto.text.016', 'In-App Video Interview')}</Text>
              </View>
              <View style={{ flexDirection: m ? 'column' : 'row', gap: 8, marginBottom: 12 }}>
                <View style={{ flex: 1, backgroundColor: AC.bgAlt, borderRadius: 8, padding: 10 }}>
                  <Text style={{ color: AC.textDim, fontSize: 10, fontWeight: '700' }}>{tx('admin.careerApplicationsPanel.auto.text.017', 'DATE')}</Text>
                  <Text style={{ color: AC.text, fontSize: 13, fontWeight: '600' }}>{app.interview.date}</Text>
                </View>
                <View style={{ flex: 1, backgroundColor: AC.bgAlt, borderRadius: 8, padding: 10 }}>
                  <Text style={{ color: AC.textDim, fontSize: 10, fontWeight: '700' }}>{tx('admin.careerApplicationsPanel.auto.text.018', 'TIME')}</Text>
                  <Text style={{ color: AC.text, fontSize: 13, fontWeight: '600' }}>{app.interview.time || 'TBD'}</Text>
                </View>
              </View>
              {Platform.OS === 'web' && (
                <a href={`${app.interview.video_url.replace(/name=[^&]*/, 'name=Interviewer')}&appId=${app.application_id}`} target="_blank" rel="noopener noreferrer" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8, padding: '12px 20px', borderRadius: 10, backgroundColor: AC.accent, textDecoration: 'none' }} data-testid="admin-join-video-btn">
                  <Ionicons name="videocam" size={16} color={AC.primaryText} />
                  <span style={{ color: AC.primaryText, fontSize: 14, fontWeight: '700' }}>Join as Interviewer</span>
                </a>
              )}
            </View>
          )}

          {/* Interview Recordings */}
          {app.recordings && app.recordings.length > 0 && (
            <View style={{ backgroundColor: AC.bgAlt, borderRadius: 12, padding: 14, marginBottom: 20, borderWidth: 1, borderColor: AC.border }} data-testid="interview-recordings" testID="interview-recordings">
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 12 }}>
                <Ionicons name="recording" size={15} color={'var(--app-error)'} />
                <Text style={{ color: AC.text, fontSize: 13, fontWeight: '700' }}>Interview Recordings ({app.recordings.length})</Text>
              </View>
              <View style={{ gap: 10 }}>
                {app.recordings.map((rec: any, i: number) => {
                  const mins = Math.floor((rec.duration_sec || 0) / 60);
                  const secs = (rec.duration_sec || 0) % 60;
                  return (
                    <View key={i} style={{ backgroundColor: AC.border, borderRadius: 10, overflow: 'hidden', borderWidth: 1, borderColor: AC.borderStrong }}>
                      {Platform.OS === 'web' && (
                        <video
                          src={`${API}${rec.url}`}
                          controls
                          preload="metadata"
                          style={{ width: '100%', maxHeight: 280, borderRadius: 8, backgroundColor: AC.bgAlt }}
                          data-testid={`recording-player-${i}`}
                        />
                      )}
                      <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', padding: 10 }}>
                        <View>
                          <Text style={{ color: AC.textSec, fontSize: 12, fontWeight: '600' }}>
                            Recorded by {rec.recorded_by || 'Unknown'}
                          </Text>
                          <Text style={{ color: AC.textDim, fontSize: 11 }}>
                            {new Date(rec.created_at).toLocaleDateString()} — ~{mins}m {secs}s
                          </Text>
                        </View>
                        {Platform.OS === 'web' && (
                          <a href={`${API}${rec.url}`} download style={{ padding: '6px 10px', borderRadius: 6, backgroundColor: AC.primarySoft, textDecoration: 'none', display: 'flex', alignItems: 'center', gap: 4 }} data-testid={`download-recording-${i}`}>
                            <Ionicons name="download" size={12} color={'var(--app-primary)'} />
                            <span style={{ color: AC.primary, fontSize: 11, fontWeight: '600' }}>Download</span>
                          </a>
                        )}
                      </View>
                    </View>
                  );
                })}
              </View>
            </View>
          )}

          {/* AI Analysis Section */}
          {(app.recordings && app.recordings.length > 0) && (
            <View style={{ backgroundColor: AC.bgAlt, borderRadius: 12, padding: 14, marginBottom: 20, borderWidth: 1, borderColor: app.ai_analysis ? 'var(--app-success-soft)' : AC.border }} data-testid="ai-analysis-section" testID="ai-analysis-section">
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 12 }}>
                <Ionicons name="analytics" size={15} color={'var(--app-success)'} />
                <Text style={{ color: AC.text, fontSize: 13, fontWeight: '700' }}>{tx('admin.careerApplicationsPanel.auto.text.019', 'AI Interview Analysis')}</Text>
              </View>

              {!app.ai_analysis ? (
                <View style={{ alignItems: 'center', paddingVertical: 12 }}>
                  <Text style={{ color: AC.textMuted, fontSize: 12, textAlign: 'center', marginBottom: 14, lineHeight: 18 }}>{tx('admin.careerApplicationsPanel.auto.text.020', 'Use AI to transcribe and analyze the interview recording. Get a summary, scores, and hiring recommendation.')}</Text>
                  {analysisMsg ? <Text style={{ color: analysisMsg.includes('complete') ? 'var(--app-success)' : 'var(--app-error)', fontSize: 12, fontWeight: '600', marginBottom: 10 }}>{analysisMsg}</Text> : null}
                  <TouchableOpacity onPress={handleAnalyze} disabled={analyzing} style={{ flexDirection: 'row', alignItems: 'center', gap: 8, paddingHorizontal: 20, paddingVertical: 12, borderRadius: 10, backgroundColor: analyzing ? AC.border : 'var(--app-success)', opacity: analyzing ? 0.7 : 1 }} data-testid="analyze-interview-btn" testID="analyze-interview-btn">
                    {analyzing ? (
                      <>
                        <ActivityIndicator size="small" color={'var(--app-success)'} />
                        <Text style={{ color: AC.successText, fontSize: 13, fontWeight: '700' }}>{tx('admin.careerApplicationsPanel.auto.text.021', 'Analyzing... This may take a moment')}</Text>
                      </>
                    ) : (
                      <>
                        <Ionicons name="sparkles" size={15} color={AC.primaryText} />
                        <Text style={{ color: AC.primaryText, fontSize: 13, fontWeight: '700' }}>{tx('admin.careerApplicationsPanel.auto.text.022', 'Analyze Interview with AI')}</Text>
                      </>
                    )}
                  </TouchableOpacity>
                </View>
              ) : (
                <View style={{ gap: 12 }}>
                  {/* Overall Score & Recommendation */}
                  <View style={{ flexDirection: m ? 'column' : 'row', gap: 10 }}>
                    <View style={{ flex: 1, backgroundColor: AC.border, borderRadius: 10, padding: 14, alignItems: 'center', borderWidth: 1, borderColor: AC.borderStrong }}>
                      <Text style={{ color: AC.textDim, fontSize: 10, fontWeight: '700', letterSpacing: 0.5, marginBottom: 6 }}>{tx('admin.careerApplicationsPanel.auto.text.023', 'OVERALL SCORE')}</Text>
                      <Text style={{ fontSize: 32, fontWeight: '900', color: (app.ai_analysis.analysis.overall_score || 0) >= 7 ? 'var(--app-success)' : (app.ai_analysis.analysis.overall_score || 0) >= 5 ? 'var(--app-warning)' : 'var(--app-error)' }}>
                        {app.ai_analysis.analysis.overall_score || 0}<Text style={{ fontSize: 16, color: AC.textDim }}>/10</Text>
                      </Text>
                    </View>
                    <View style={{ flex: 1, backgroundColor: AC.border, borderRadius: 10, padding: 14, alignItems: 'center', borderWidth: 1, borderColor: AC.borderStrong }}>
                      <Text style={{ color: AC.textDim, fontSize: 10, fontWeight: '700', letterSpacing: 0.5, marginBottom: 6 }}>{tx('admin.careerApplicationsPanel.auto.text.024', 'RECOMMENDATION')}</Text>
                      <View style={{ backgroundColor: app.ai_analysis.analysis.recommendation === 'strong_hire' ? 'var(--app-success-soft)' : app.ai_analysis.analysis.recommendation === 'hire' ? 'var(--app-primary-soft)' : app.ai_analysis.analysis.recommendation === 'maybe' ? 'var(--app-warning-soft)' : 'var(--app-error-soft)', paddingHorizontal: 14, paddingVertical: 6, borderRadius: 20 }}>
                        <Text style={{ color: app.ai_analysis.analysis.recommendation === 'strong_hire' ? 'var(--app-success)' : app.ai_analysis.analysis.recommendation === 'hire' ? 'var(--app-primary)' : app.ai_analysis.analysis.recommendation === 'maybe' ? 'var(--app-warning)' : 'var(--app-error)', fontSize: 13, fontWeight: '800', textTransform: 'uppercase' }}>
                          {(app.ai_analysis.analysis.recommendation || 'N/A').replace('_', ' ')}
                        </Text>
                      </View>
                    </View>
                  </View>

                  {/* Score Bars */}
                  <View style={{ backgroundColor: AC.border, borderRadius: 10, padding: 14, borderWidth: 1, borderColor: AC.borderStrong }}>
                    {[
                      { label: 'Communication', score: app.ai_analysis.analysis.communication_score, color: AC.primary },
                      { label: 'Technical', score: app.ai_analysis.analysis.technical_score, color: AC.accent },
                      { label: 'Cultural Fit', score: app.ai_analysis.analysis.cultural_fit_score, color: AC.warningText },
                    ].map((item, i) => (
                      <View key={i} style={{ marginBottom: i < 2 ? 12 : 0 }}>
                        <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginBottom: 4 }}>
                          <Text style={{ color: AC.textSec, fontSize: 12, fontWeight: '600' }}>{item.label}</Text>
                          <Text style={{ color: item.color, fontSize: 12, fontWeight: '800' }}>{item.score || 0}/10</Text>
                        </View>
                        <View style={{ height: 6, borderRadius: 3, backgroundColor: AC.bgAlt }}>
                          <View style={{ height: 6, borderRadius: 3, backgroundColor: item.color, width: `${((item.score || 0) / 10) * 100}%` as any }} />
                        </View>
                      </View>
                    ))}
                  </View>

                  {/* Summary */}
                  {app.ai_analysis.analysis.summary && (
                    <View style={{ backgroundColor: AC.border, borderRadius: 10, padding: 14, borderWidth: 1, borderColor: AC.borderStrong }}>
                      <Text style={{ color: AC.textDim, fontSize: 10, fontWeight: '700', letterSpacing: 0.5, marginBottom: 6 }}>{tx('admin.careerApplicationsPanel.auto.text.025', 'SUMMARY')}</Text>
                      <Text style={{ color: AC.textSec, fontSize: 13, lineHeight: 20 }}>{app.ai_analysis.analysis.summary}</Text>
                    </View>
                  )}

                  {/* Recommendation Reason */}
                  {app.ai_analysis.analysis.recommendation_reason && (
                    <View style={{ backgroundColor: AC.border, borderRadius: 10, padding: 14, borderWidth: 1, borderColor: AC.borderStrong }}>
                      <Text style={{ color: AC.textDim, fontSize: 10, fontWeight: '700', letterSpacing: 0.5, marginBottom: 6 }}>{tx('admin.careerApplicationsPanel.auto.text.026', 'RECOMMENDATION REASON')}</Text>
                      <Text style={{ color: AC.textSec, fontSize: 13, lineHeight: 20 }}>{app.ai_analysis.analysis.recommendation_reason}</Text>
                    </View>
                  )}

                  {/* Key Points */}
                  {app.ai_analysis.analysis.key_points && app.ai_analysis.analysis.key_points.length > 0 && (
                    <View style={{ backgroundColor: AC.border, borderRadius: 10, padding: 14, borderWidth: 1, borderColor: AC.borderStrong }}>
                      <Text style={{ color: AC.textDim, fontSize: 10, fontWeight: '700', letterSpacing: 0.5, marginBottom: 8 }}>{tx('admin.careerApplicationsPanel.auto.text.027', 'KEY DISCUSSION POINTS')}</Text>
                      {app.ai_analysis.analysis.key_points.map((pt: string, i: number) => (
                        <View key={i} style={{ flexDirection: 'row', gap: 8, marginBottom: i < app.ai_analysis!.analysis.key_points.length - 1 ? 6 : 0 }}>
                          <Text style={{ color: AC.primary, fontSize: 11 }}>•</Text>
                          <Text style={{ color: AC.textSec, fontSize: 12, lineHeight: 18, flex: 1 }}>{pt}</Text>
                        </View>
                      ))}
                    </View>
                  )}

                  {/* Strengths & Weaknesses side by side */}
                  <View style={{ flexDirection: m ? 'column' : 'row', gap: 10 }}>
                    {app.ai_analysis.analysis.strengths && app.ai_analysis.analysis.strengths.length > 0 && (
                      <View style={{ flex: 1, backgroundColor: AC.successSoft, borderRadius: 10, padding: 14, borderWidth: 1, borderColor: AC.successSoft }}>
                        <Text style={{ color: AC.successText, fontSize: 10, fontWeight: '700', letterSpacing: 0.5, marginBottom: 8 }}>{tx('admin.careerApplicationsPanel.auto.text.028', 'STRENGTHS')}</Text>
                        {app.ai_analysis.analysis.strengths.map((s: string, i: number) => (
                          <View key={i} style={{ flexDirection: 'row', gap: 6, marginBottom: i < app.ai_analysis!.analysis.strengths.length - 1 ? 5 : 0 }}>
                            <Ionicons name="checkmark-circle" size={13} color={'var(--app-success)'} style={{ marginTop: 1 }} />
                            <Text style={{ color: AC.textSec, fontSize: 12, lineHeight: 17, flex: 1 }}>{s}</Text>
                          </View>
                        ))}
                      </View>
                    )}
                    {app.ai_analysis.analysis.weaknesses && app.ai_analysis.analysis.weaknesses.length > 0 && (
                      <View style={{ flex: 1, backgroundColor: AC.warningSoft, borderRadius: 10, padding: 14, borderWidth: 1, borderColor: AC.warningSoft }}>
                        <Text style={{ color: AC.warningText, fontSize: 10, fontWeight: '700', letterSpacing: 0.5, marginBottom: 8 }}>{tx('admin.careerApplicationsPanel.auto.text.029', 'AREAS FOR IMPROVEMENT')}</Text>
                        {app.ai_analysis.analysis.weaknesses.map((w: string, i: number) => (
                          <View key={i} style={{ flexDirection: 'row', gap: 6, marginBottom: i < app.ai_analysis!.analysis.weaknesses.length - 1 ? 5 : 0 }}>
                            <Ionicons name="alert-circle" size={13} color={'var(--app-warning)'} style={{ marginTop: 1 }} />
                            <Text style={{ color: AC.textSec, fontSize: 12, lineHeight: 17, flex: 1 }}>{w}</Text>
                          </View>
                        ))}
                      </View>
                    )}
                  </View>

                  {/* Analyzed timestamp */}
                  <Text style={{ color: AC.textDim, fontSize: 10, textAlign: 'right' }}>
                    Analyzed {new Date(app.ai_analysis.analyzed_at).toLocaleString()}
                  </Text>

                  {/* Re-analyze button */}
                  <TouchableOpacity onPress={handleAnalyze} disabled={analyzing} style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, paddingVertical: 8, borderRadius: 8, backgroundColor: AC.border, borderWidth: 1, borderColor: AC.borderStrong, opacity: analyzing ? 0.6 : 1 }} data-testid="re-analyze-btn" testID="re-analyze-btn">
                    {analyzing ? <ActivityIndicator size="small" color={AC.textSec} /> : <Ionicons name="refresh" size={12} color={AC.textSec} />}
                    <Text style={{ color: AC.textMuted, fontSize: 11, fontWeight: '600' }}>{analyzing ? 'Re-analyzing...' : 'Re-analyze'}</Text>
                  </TouchableOpacity>
                </View>
              )}
            </View>
          )}

          {/* Status Update Section */}
          <View style={{ backgroundColor: AC.bgAlt, borderRadius: 12, padding: 16, marginBottom: 20, borderWidth: 1, borderColor: AC.borderStrong }}>
            <Text style={{ color: AC.text, fontSize: 14, fontWeight: '700', marginBottom: 12 }}>{tx('admin.careerApplicationsPanel.auto.text.030', 'Update Status')}</Text>
            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginBottom: 14 }}>
              {ALL_STATUSES.map(s => {
                const cfg = STATUS_CONFIG[s];
                const active = newStatus === s;
                const onPress = async () => {
                  setNewStatus(s);
                  if (s === 'offer' && Platform.OS === 'web') {
                    // Open (or create then open) the Offer Studio in a new tab
                    try {
                      const list = await api.get(`/careers/offers?application_id=${app.application_id}`);
                      const existing = (list.data?.items || []).find((o: any) => ['draft', 'sent', 'viewed'].includes(o.state));
                      let offerId = existing?.offer_id;
                      if (!offerId) {
                        const created = await api.post('/careers/offers/draft', {
                          application_id: app.application_id, base_salary_usd: 0, bonus_target_pct: 0,
                          pto_days: 20, expiry_days: 5, work_location: 'remote',
                        });
                        offerId = created.data?.offer_id;
                      }
                      if (offerId) (window as any).open(`/admin/offer-studio?offerId=${encodeURIComponent(offerId)}`, '_blank');
                    } catch { /* fallback: don't block the status UI */ }
                  }
                };
                return (
                  <TouchableOpacity key={s} onPress={onPress} style={{ flexDirection: 'row', alignItems: 'center', gap: 5, paddingHorizontal: 12, paddingVertical: 8, borderRadius: 8, backgroundColor: active ? (globalThis as any).__alphaColor(cfg.color, '25') : AC.border, borderWidth: 1, borderColor: active ? cfg.color : AC.borderStrong }} data-testid={`status-option-${s}`} testID={`status-option-${s}`}>
                    <Ionicons name={cfg.icon as any} size={13} color={active ? cfg.color : AC.textDim} />
                    <Text style={{ color: active ? cfg.color : AC.textDim, fontSize: 12, fontWeight: '600' }}>{cfg.label}</Text>
                  </TouchableOpacity>
                );
              })}
            </View>

            {/* Offer Studio CTA — only when Offer is selected */}
            {newStatus === 'offer' && Platform.OS === 'web' && (
              <View style={{ backgroundColor: (globalThis as any).__alphaColor((AC.primary || 'var(--app-primary)'), '15'), borderRadius: 10, padding: 14, marginBottom: 14, borderWidth: 1, borderColor: AC.primary, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 12 }} data-testid="offer-studio-cta" testID="offer-studio-cta">
                <View style={{ flex: 1 }}>
                  <Text style={{ color: AC.primary, fontSize: 13, fontWeight: '800' }}>{tx('admin.careerApplicationsPanel.auto.text.031', 'Continue in Offer Studio')}</Text>
                  <Text style={{ color: AC.textSec, fontSize: 11, marginTop: 2 }}>{tx('admin.careerApplicationsPanel.auto.text.032', 'Build comp terms, auto-generate PDF, send with e-signature flow + 5-day auto-expiry.')}</Text>
                </View>
                <TouchableOpacity accessibilityLabel={tx('admin.careerApplicationsPanel.auto.accessibility.001', 'Open or create offer')} onPress={async () => {
                  try {
                    const list = await api.get(`/careers/offers?application_id=${app.application_id}`);
                    const existing = (list.data?.items || []).find((o: any) => ['draft','sent','viewed'].includes(o.state));
                    let offerId = existing?.offer_id;
                    if (!offerId) {
                      const created = await api.post('/careers/offers/draft', {
                        application_id: app.application_id, base_salary_usd: 0, bonus_target_pct: 0,
                        pto_days: 20, expiry_days: 5, work_location: 'remote',
                      });
                      offerId = created.data?.offer_id;
                    }
                    if (offerId) (window as any).open(`/admin/offer-studio?offerId=${encodeURIComponent(offerId)}`, '_blank');
                  } catch {/* silent */}
                }} style={{ backgroundColor: AC.primary, paddingHorizontal: 14, paddingVertical: 8, borderRadius: 8, flexDirection: 'row', alignItems: 'center', gap: 4 }} data-testid="open-offer-studio-btn" testID="open-offer-studio-btn">
                  <Text style={{ color: AC.primaryText, fontSize: 12, fontWeight: '700' }}>{tx('admin.careerApplicationsPanel.auto.text.033', 'Open Studio')}</Text>
                  <Ionicons name="open" size={12} color={AC.primaryText} />
                </TouchableOpacity>
              </View>
            )}

            {/* Interview Scheduling Fields */}
            {newStatus === 'interview' && Platform.OS === 'web' && (
              <View style={{ backgroundColor: AC.accentSoft, borderRadius: 10, padding: 14, marginBottom: 14, borderWidth: 1, borderColor: AC.accentSoft }} data-testid="interview-scheduling" testID="interview-scheduling">
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 12 }}>
                  <Ionicons name="calendar" size={14} color={'var(--app-info)'} />
                  <Text style={{ color: AC.accent, fontSize: 12, fontWeight: '700' }}>{tx('admin.careerApplicationsPanel.auto.text.034', 'Schedule Interview')}</Text>
                </View>
                <View style={{ flexDirection: m ? 'column' : 'row', gap: 10, marginBottom: 10 }}>
                  <View style={{ flex: 1 }}>
                    <Text style={{ color: AC.textDim, fontSize: 10, fontWeight: '600', marginBottom: 4 }}>{tx('admin.careerApplicationsPanel.auto.text.035', 'Date *')}</Text>
                    <input type="date" value={intDate} onChange={(e: any) => setIntDate(e.target.value)} data-testid="interview-date" style={{ width: '100%', padding: '9px 12px', borderRadius: 8, border: `1px solid ${AC.border}`, backgroundColor: AC.border, color: AC.text, fontSize: 13, outline: 'none', boxSizing: 'border-box' as any }} />
                  </View>
                  <View style={{ flex: 1 }}>
                    <Text style={{ color: AC.textDim, fontSize: 10, fontWeight: '600', marginBottom: 4 }}>{tx('admin.careerApplicationsPanel.auto.text.036', 'Time')}</Text>
                    <input type="text" value={intTime} onChange={(e: any) => setIntTime(e.target.value)} placeholder={tx('admin.careerApplicationsPanel.auto.placeholder.003', 'e.g. 10:00 AM EST')} data-testid="interview-time" style={{ width: '100%', padding: '9px 12px', borderRadius: 8, border: `1px solid ${AC.border}`, backgroundColor: AC.border, color: AC.text, fontSize: 13, outline: 'none', boxSizing: 'border-box' as any }} />
                  </View>
                </View>
                <View style={{ marginBottom: 10 }}>
                  <Text style={{ color: AC.textDim, fontSize: 10, fontWeight: '600', marginBottom: 6 }}>{tx('admin.careerApplicationsPanel.auto.text.037', 'Interview Type')}</Text>
                  <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6 }}>
                    {[
                      { id: 'in-app-video', label: 'In-App Video', icon: 'videocam' },
                      { id: 'video', label: 'External Video', icon: 'laptop' },
                      { id: 'phone', label: 'Phone', icon: 'call' },
                      { id: 'in-person', label: 'In-Person', icon: 'people' },
                    ].map(t => (
                      <TouchableOpacity key={t.id} onPress={() => setIntType(t.id)} style={{ flexDirection: 'row', alignItems: 'center', gap: 5, paddingHorizontal: 10, paddingVertical: 7, borderRadius: 6, backgroundColor: intType === t.id ? 'var(--app-info-soft)' : AC.bgAlt, borderWidth: 1, borderColor: intType === t.id ? 'var(--app-info)' : AC.border }} data-testid={`interview-type-${t.id}`} testID={`interview-type-${t.id}`}>
                        <Ionicons name={t.icon as any} size={12} color={intType === t.id ? 'var(--app-info)' : AC.textDim} />
                        <Text style={{ color: intType === t.id ? 'var(--app-info)' : AC.textDim, fontSize: 11, fontWeight: '600' }}>{t.label}</Text>
                      </TouchableOpacity>
                    ))}
                  </View>
                </View>
                <View>
                  <Text style={{ color: AC.textDim, fontSize: 10, fontWeight: '600', marginBottom: 4 }}>{tx('admin.careerApplicationsPanel.auto.text.038', 'Interview Notes (sent to applicant)')}</Text>
                  <textarea value={intNotes} onChange={(e: any) => setIntNotes(e.target.value)} placeholder={tx('admin.careerApplicationsPanel.auto.placeholder.004', 'Preparation instructions, what to expect...')} rows={2} data-testid="interview-notes" style={{ width: '100%', padding: '9px 12px', borderRadius: 8, border: `1px solid ${AC.border}`, backgroundColor: AC.border, color: AC.text, fontSize: 13, fontFamily: 'inherit', resize: 'vertical' as any, outline: 'none', boxSizing: 'border-box' as any }} />
                </View>
              </View>
            )}

            {/* Send Email Toggle */}
            <TouchableOpacity onPress={() => setSendEmail(!sendEmail)} style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 12 }} data-testid="send-email-toggle" testID="send-email-toggle">
              <View style={{ width: 20, height: 20, borderRadius: 4, borderWidth: 1.5, borderColor: sendEmail ? 'var(--app-primary)' : AC.textDim, backgroundColor: sendEmail ? 'var(--app-primary)' : 'transparent', justifyContent: 'center', alignItems: 'center' }}>
                {sendEmail && <Ionicons name="checkmark" size={13} color={AC.primaryText} />}
              </View>
              <Text style={{ color: AC.textSec, fontSize: 13 }}>{tx('admin.careerApplicationsPanel.auto.text.039', 'Send notification email to applicant')}</Text>
            </TouchableOpacity>

            {/* Admin Notes */}
            {Platform.OS === 'web' && (
              <View style={{ marginBottom: 14 }}>
                <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 6 }}>
                  <Text style={{ color: AC.textDim, fontSize: 11, fontWeight: '600' }}>{tx('admin.careerApplicationsPanel.auto.text.040', 'Admin Notes')}</Text>
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                    {/* Tone toggle */}
                    <View style={{ flexDirection: 'row', backgroundColor: AC.border, borderRadius: 6, padding: 2 }}>
                      {(['professional', 'warm', 'direct'] as const).map(t => (
                        <TouchableOpacity key={t} onPress={() => setAiTone(t)}
                          style={{ paddingHorizontal: 8, paddingVertical: 3, borderRadius: 5, backgroundColor: aiTone === t ? AC.primary : 'transparent' }}
                          data-testid={`ai-tone-${t}`} testID={`ai-tone-${t}`}>
                          <Text style={{ color: aiTone === t ? AC.primaryText : AC.textSec, fontSize: 10, fontWeight: '700' }}>{t.charAt(0).toUpperCase() + t.slice(1)}</Text>
                        </TouchableOpacity>
                      ))}
                    </View>
                    <TouchableOpacity onPress={handleAiSuggestNote} disabled={aiSuggesting}
                      style={{ flexDirection: 'row', alignItems: 'center', gap: 4, backgroundColor: 'var(--app-info-soft)', borderWidth: 1, borderColor: 'var(--app-info)', paddingHorizontal: 8, paddingVertical: 4, borderRadius: 6 }}
                      data-testid="ai-suggest-note-btn" testID="ai-suggest-note-btn">
                      {aiSuggesting ? <ActivityIndicator size="small" color={'var(--app-info)'} /> : <Ionicons name="sparkles" size={11} color={'var(--app-info)'} />}
                      <Text style={{ color: 'var(--app-info)', fontSize: 10, fontWeight: '700' }}>{aiSuggesting ? 'Drafting…' : 'AI Suggest'}</Text>
                    </TouchableOpacity>
                  </View>
                </View>
                <textarea
                  value={notes}
                  onChange={(e: any) => setNotes(e.target.value)}
                  placeholder={tx('admin.careerApplicationsPanel.auto.placeholder.005', 'Internal notes about this applicant… (Tip: type a seed phrase, then click AI Suggest for a polished draft.)')}
                  rows={4}
                  data-testid="admin-notes-input"
                  style={{ width: '100%', padding: '10px 12px', borderRadius: 8, border: `1px solid ${AC.border}`, backgroundColor: AC.border, color: AC.text, fontSize: 13, fontFamily: 'inherit', resize: 'vertical' as any, outline: 'none', boxSizing: 'border-box' as any }}
                />
                <Text style={{ color: AC.textDim, fontSize: 10, marginTop: 4 }}>{tx('admin.careerApplicationsPanel.auto.text.041', 'AI Suggest drafts a status-aware internal note using Claude Sonnet 4.5 (candidate profile + your seed). Internal-only.')}</Text>
              </View>
            )}

            {message && (
              <Text style={{ color: message.includes('success') ? 'var(--app-success)' : 'var(--app-error)', fontSize: 12, fontWeight: '600', marginBottom: 10 }}>{message}</Text>
            )}

            {/* Portal link + Scorecards (Tier 2 enhancements) */}
            <PortalLinkButton appId={app.application_id} />
            <View style={{ marginTop: 4, marginBottom: 14 }}>
              <ScorecardsSection appId={app.application_id} interviewerDefault="" />
            </View>

            {/* Applicant conversation thread (inbound replies auto-correlated) */}
            <ApplicantThreadPanel applicationId={app.application_id} />

            <TouchableOpacity onPress={handleUpdate} disabled={updating || (newStatus === app.status && !notes)} style={{ paddingVertical: 12, borderRadius: 10, backgroundColor: (newStatus !== app.status || notes) ? 'var(--app-primary)' : AC.border, alignItems: 'center', opacity: updating ? 0.6 : 1 }} data-testid="update-status-btn" testID="update-status-btn">
              {updating ? (
                <ActivityIndicator size="small" color={AC.primaryText} />
              ) : (
                <Text style={{ color: (newStatus !== app.status || notes) ? AC.primaryText : AC.textDim, fontSize: 14, fontWeight: '700' }}>
                  {newStatus !== app.status ? `Update to ${STATUS_CONFIG[newStatus]?.label}` : 'Save Notes'}
                </Text>
              )}
            </TouchableOpacity>
          </View>
        </ScrollView>
      </View>
    </View>
  );
}

export default function CareerApplicationsPanel({ colors }: { colors: any }) {
  const AC = useAdminTheme();
  const { t } = useLanguage();
  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };
  const { width } = useWindowDimensions();
  const m = width < 768;
  const [apps, setApps] = useState<Application[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState('all');
  const [search, setSearch] = useState('');
  const [selectedApp, setSelectedApp] = useState<Application | null>(null);
  const [sortBy, setSortBy] = useState<'date' | 'name'>('date');
  const [compareMode, setCompareMode] = useState(false);
  const [compareList, setCompareList] = useState<Application[]>([]);
  const [showCompare, setShowCompare] = useState(false);
  const [inviteApp, setInviteApp] = useState<Application | null>(null);
  const [rescheduleApp, setRescheduleApp] = useState<Application | null>(null);
  const [showStalled, setShowStalled] = useState(false);
  const [showDuplicates, setShowDuplicates] = useState(false);
  const [showGDPR, setShowGDPR] = useState(false);
  const [viewMode, setViewMode] = useState<'table' | 'kanban'>('table');
  const [bulkSelected, setBulkSelected] = useState<string[]>([]);

  const fetchData = useCallback(async () => {
    try {
      const [appsRes, statsRes] = await Promise.all([
        api.get('/careers/applications'),
        api.get('/careers/applications/stats'),
      ]);
      setApps(appsRes.data?.applications || []);
      setStats(statsRes.data || null);
    } catch (e) {
      console.error('Failed to fetch career data', e);
    }
    setLoading(false);
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);

  useHybridPolling({
    enabled: true,
    errorScope: 'admin/career-applications/hybrid-refresh',
    onTick: fetchData,
    runOnMount: false,
    slowIntervalMs: 45000,
    fastIntervalMs: 15000,
  });
  const handleStatusUpdate = async (appId: string, status: string, sendEmail: boolean, notes: string, interview?: { date: string; time: string; type: string; notes: string }) => {
    const body: any = { status, send_email: sendEmail, admin_notes: notes };
    if (interview) {
      body.interview_date = interview.date;
      body.interview_time = interview.time;
      body.interview_type = interview.type;
      body.interview_notes = interview.notes;
    }
    const res = await api.patch(`/careers/applications/${appId}/status`, body);
    const data = res.data || {};
    if (data.success) {
      await fetchData();
      setSelectedApp(prev => prev ? { ...prev, status, admin_notes: notes } : null);
    }
    if (!data.success) throw new Error(data.message || 'status update failed');
  };

  const analyzedApps = apps.filter(a => a.ai_analysis);

  const toggleCompareItem = (app: Application) => {
    setCompareList(prev => {
      const exists = prev.find(a => a.application_id === app.application_id);
      if (exists) return prev.filter(a => a.application_id !== app.application_id);
      if (prev.length >= 4) return prev;
      return [...prev, app];
    });
  };

  const filtered = apps
    .filter(a => {
      if (filter === 'all') return true;
      if (filter === 'needs_response') return (a.unread_applicant_replies || 0) > 0;
      return a.status === filter;
    })
    .filter(a => {
      if (!search) return true;
      const q = search.toLowerCase();
      return a.full_name.toLowerCase().includes(q) || a.email.toLowerCase().includes(q) || a.position.toLowerCase().includes(q) || a.application_id.toLowerCase().includes(q);
    })
    .sort((a, b) => sortBy === 'date' ? b.submitted_at.localeCompare(a.submitted_at) : a.full_name.localeCompare(b.full_name));

  if (loading) return (
    <View style={{ flex: 1, justifyContent: 'center', alignItems: 'center', padding: 40 }}>
      <AutoFixBanner domain="careers" />
      <ActivityIndicator size="large" color={'var(--app-primary)'} />
      <Text style={{ color: AC.textDim, marginTop: 12, fontSize: 13 }}>{t('careerApplications.loading')}</Text>
    </View>
  );

  return (
    <View style={{ flex: 1, padding: m ? 12 : 16 }} data-testid="career-applications-panel" testID="career-applications-panel">
      {/* Header */}
      <View style={{ flexDirection: m ? 'column' : 'row', justifyContent: 'space-between', alignItems: m ? 'flex-start' : 'center', marginBottom: 20, gap: 12 }}>
        <View>
          <Text style={{ fontSize: 20, fontWeight: '800', color: AC.text }}>{t('careerApplications.header.title')}</Text>
          <Text style={{ fontSize: 13, color: AC.textMuted, marginTop: 2 }}>{t('careerApplications.header.subtitle')}</Text>
        </View>
        <View style={{ flexDirection: 'row', gap: 8 }}>
          <ViewToggle value={viewMode} onChange={setViewMode} />
          <GDPRButton onOpen={() => setShowGDPR(true)} />
          {analyzedApps.length >= 2 && (
            <TouchableOpacity
              onPress={() => { setCompareMode(!compareMode); if (compareMode) setCompareList([]); }}
              style={{ flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 14, paddingVertical: 8, borderRadius: 8, backgroundColor: compareMode ? 'var(--app-success-soft)' : AC.border, borderWidth: 1, borderColor: compareMode ? 'var(--app-success)' : AC.borderStrong }}
              data-testid="compare-candidates-btn" testID="compare-candidates-btn"
            >
              <Ionicons name="git-compare" size={14} color={compareMode ? 'var(--app-success)' : AC.textMuted} />
              <Text style={{ color: compareMode ? 'var(--app-success)' : AC.textMuted, fontSize: 12, fontWeight: '600' }}>{compareMode ? t('careerApplications.actions.cancelCompare') : t('careerApplications.actions.compare')}</Text>
            </TouchableOpacity>
          )}
          <TouchableOpacity onPress={fetchData} style={{ flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 14, paddingVertical: 8, borderRadius: 8, backgroundColor: AC.border, borderWidth: 1, borderColor: AC.borderStrong }} data-testid="refresh-apps-btn" testID="refresh-apps-btn">
            <Ionicons name="refresh" size={14} color={AC.textSec} />
            <Text style={{ color: AC.textMuted, fontSize: 12, fontWeight: '600' }}>{t('careerApplications.actions.refresh')}</Text>
          </TouchableOpacity>
        </View>
      </View>

      {/* Tier 2 enhancement badges — Stalled + Duplicates */}
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 10, flexWrap: 'wrap' }} data-testid="career-enhancement-badges" testID="career-enhancement-badges">
        <StalledBadge onOpen={() => setShowStalled(true)} />
        <DuplicatesBadge onOpen={() => setShowDuplicates(true)} />
      </View>

      {/* Upcoming Interviews Calendar Widget */}
      <UpcomingInterviewsWidget
        onOpenApplication={(appId) => {
          const match = apps.find((a) => a.application_id === appId);
          if (match) setSelectedApp(match);
        }}
      />

      {/* My Interview Availability (for the applicant self-serve scheduler) */}
      <CareerSchedulingAvailability colors={AC} />

      {/* Timezone-pain heatmap — compounding scheduling intelligence */}
      <CareerTZHeatmap colors={AC} />
      {/* Stats */}
      {stats && (
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 12, marginBottom: 20 }}>
          <StatCard label={t('careerApplications.stats.totalApplications')} value={stats.total} icon="people" color={'var(--app-primary)'} />
          <StatCard label={t('careerApplications.stats.thisWeek')} value={stats.recent_7d} icon="calendar" color={'var(--app-success)'} />
          <StatCard label={t('careerApplications.stats.underReview')} value={stats.by_status.under_review || 0} icon="search" color={'var(--app-warning)'} />
          <StatCard label={t('careerApplications.stats.interviews')} value={stats.by_status.interview || 0} icon="videocam" color={'var(--app-info)'} />
        </View>
      )}

      {/* Pipeline Overview */}
      {stats && (
        <View style={{ backgroundColor: AC.bgAlt, borderRadius: 12, padding: m ? 12 : 16, marginBottom: 20, borderWidth: 1, borderColor: AC.border }}>
          <Text style={{ color: AC.text, fontSize: 14, fontWeight: '700', marginBottom: 12 }}>{t('careerApplications.pipeline.title')}</Text>
          <View style={{ flexDirection: 'row', gap: 2, height: 8, borderRadius: 4, overflow: 'hidden', marginBottom: 10 }}>
            {ALL_STATUSES.map(s => {
              const count = stats.by_status[s] || 0;
              const pct = stats.total > 0 ? (count / stats.total) * 100 : 0;
              return pct > 0 ? <View key={s} style={{ width: `${pct}%` as any, backgroundColor: STATUS_CONFIG[s].color, minWidth: 4 }} /> : null;
            })}
          </View>
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: m ? 8 : 16 }}>
            {ALL_STATUSES.map(s => {
              const count = stats.by_status[s] || 0;
              const cfg = STATUS_CONFIG[s];
              return (
                <View key={s} style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                  <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: cfg.color }} />
                  <Text style={{ color: AC.textMuted, fontSize: 11 }}>{cfg.label}: <Text style={{ color: AC.text, fontWeight: '700' }}>{count}</Text></Text>
                </View>
              );
            })}
          </View>
        </View>
      )}

      {/* Filters */}
      <View style={{ flexDirection: m ? 'column' : 'row', gap: 10, marginBottom: 16 }}>
        {/* Search */}
        {Platform.OS === 'web' && (
          <View style={{ flex: 1 }}>
            <input
              type="text"
              value={search}
              onChange={(e: any) => setSearch(e.target.value)}
              placeholder={t('careerApplications.search.placeholder')}
              data-testid="search-applications"
              style={{ width: '100%', padding: '10px 14px', borderRadius: 8, border: `1px solid ${AC.border}`, backgroundColor: AC.bgAlt, color: AC.text, fontSize: 13, outline: 'none', boxSizing: 'border-box' as any }}
            />
          </View>
        )}
        {/* Status Filter */}
        <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ flexGrow: 0 }} contentContainerStyle={{ gap: 6 }}>
          <TouchableOpacity onPress={() => setFilter('all')} style={{ paddingHorizontal: 12, paddingVertical: 7, borderRadius: 8, backgroundColor: filter === 'all' ? 'var(--app-primary-soft)' : AC.border, borderWidth: 1, borderColor: filter === 'all' ? 'var(--app-primary)' : AC.borderStrong }} data-testid="filter-all" testID="filter-all">
            <Text style={{ color: filter === 'all' ? 'var(--app-primary)' : AC.textDim, fontSize: 12, fontWeight: '600' }}>{t('careerApplications.filters.all').replace('{count}', String(apps.length))}</Text>
          </TouchableOpacity>
          {(() => {
            const needsCount = apps.filter(a => (a.unread_applicant_replies || 0) > 0).length;
            if (needsCount === 0) return null;
            const active = filter === 'needs_response';
            return (
              <TouchableOpacity accessibilityLabel={tx('admin.careerApplicationsPanel.auto.accessibility.002', 'Filter applications needing response')}
                onPress={() => setFilter('needs_response')}
                style={{
                  flexDirection: 'row', alignItems: 'center', gap: 6,
                  paddingHorizontal: 12, paddingVertical: 7, borderRadius: 8,
                  backgroundColor: active ? 'var(--app-success-soft)' : AC.border,
                  borderWidth: 1, borderColor: active ? 'var(--app-success)' : AC.borderStrong,
                }}
                data-testid="filter-needs-response"
                testID="filter-needs-response"
              >
                <Ionicons name="mail-unread" size={12} color={active ? 'var(--app-success)' : AC.textDim} />
                <Text style={{ color: active ? 'var(--app-success)' : AC.textDim, fontSize: 12, fontWeight: '700' }}>
                  Needs response ({needsCount})
                </Text>
              </TouchableOpacity>
            );
          })()}
          {ALL_STATUSES.map(s => {
            const count = apps.filter(a => a.status === s).length;
            const cfg = STATUS_CONFIG[s];
            const active = filter === s;
            return (
              <TouchableOpacity key={s} onPress={() => setFilter(s)} style={{ paddingHorizontal: 12, paddingVertical: 7, borderRadius: 8, backgroundColor: active ? (globalThis as any).__alphaColor(cfg.color, '25') : AC.border, borderWidth: 1, borderColor: active ? cfg.color : AC.borderStrong }} data-testid={`filter-${s}`} testID={`filter-${s}`}>
                <Text style={{ color: active ? cfg.color : AC.textDim, fontSize: 12, fontWeight: '600' }}>{cfg.label} ({count})</Text>
              </TouchableOpacity>
            );
          })}
        </ScrollView>
        {/* Sort */}
        <TouchableOpacity onPress={() => setSortBy(sortBy === 'date' ? 'name' : 'date')} style={{ flexDirection: 'row', alignItems: 'center', gap: 5, paddingHorizontal: 12, paddingVertical: 7, borderRadius: 8, backgroundColor: AC.border, borderWidth: 1, borderColor: AC.borderStrong }} data-testid="sort-toggle" testID="sort-toggle">
          <Ionicons name={sortBy === 'date' ? 'time' : 'text'} size={13} color={AC.textSec} />
          <Text style={{ color: AC.textMuted, fontSize: 12, fontWeight: '600' }}>{sortBy === 'date' ? 'Newest' : 'A-Z'}</Text>
        </TouchableOpacity>
      </View>

      {/* Compare Mode Banner */}
      {compareMode && (
        <View style={{ backgroundColor: colors.successSoft, borderRadius: 10, padding: 12, marginBottom: 16, borderWidth: 1, borderColor: colors.successSoft, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }} data-testid="compare-mode-banner" testID="compare-mode-banner">
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
            <Ionicons name="git-compare" size={16} color={'var(--app-success)'} />
            <Text style={{ color: colors.successText, fontSize: 13, fontWeight: '700' }}>
              Select 2-4 analyzed candidates to compare ({compareList.length}/4 selected)
            </Text>
          </View>
          {compareList.length >= 2 && (
            <TouchableOpacity
              onPress={() => setShowCompare(true)}
              style={{ flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: colors.success, paddingHorizontal: 16, paddingVertical: 8, borderRadius: 8 }}
              data-testid="open-compare-btn" testID="open-compare-btn"
            >
              <Ionicons name="analytics" size={14} color={AC.primaryText} />
              <Text style={{ color: AC.primaryText, fontSize: 12, fontWeight: '700' }}>Compare ({compareList.length})</Text>
            </TouchableOpacity>
          )}
        </View>
      )}

      {/* Applications List */}
      {viewMode === 'kanban' ? (
        <KanbanBoard
          apps={filtered}
          onOpen={(a) => setSelectedApp(a)}
          onStatusChanged={() => fetchData()}
        />
      ) : filtered.length === 0 ? (
        <View style={{ backgroundColor: AC.bgAlt, borderRadius: 12, padding: 32, alignItems: 'center', borderWidth: 1, borderColor: AC.border }}>
          <Ionicons name="document-text-outline" size={32} color={AC.border} />
          <Text style={{ color: AC.textDim, fontSize: 14, fontWeight: '600', marginTop: 10 }}>{tx('admin.careerApplicationsPanel.auto.text.042', 'No applications found')}</Text>
          <Text style={{ color: AC.textDim, fontSize: 12, marginTop: 4 }}>
            {search ? 'Try adjusting your search terms' : 'No applications match this filter'}
          </Text>
        </View>
      ) : (
        <View style={{ gap: 8 }}>
          {filtered.map(app => {
            const isSelected = compareList.some(a => a.application_id === app.application_id);
            const hasAnalysis = !!app.ai_analysis;
            return (
            <TouchableOpacity key={app.application_id} onPress={() => compareMode ? (hasAnalysis ? toggleCompareItem(app) : null) : setSelectedApp(app)} style={{ backgroundColor: AC.bgAlt, borderRadius: 12, padding: m ? 12 : 16, borderWidth: 1, borderColor: isSelected ? 'var(--app-success)' : bulkSelected.includes(app.application_id) ? 'var(--app-primary)' : AC.border, opacity: compareMode && !hasAnalysis ? 0.4 : 1 }} data-testid={`app-row-${app.application_id}`} testID={`app-row-${app.application_id}`}>
              <View style={{ flexDirection: m ? 'column' : 'row', justifyContent: 'space-between', alignItems: m ? 'flex-start' : 'center', gap: m ? 10 : 0 }}>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 12, flex: 1 }}>
                  {!compareMode && (
                    <TouchableOpacity accessibilityLabel={tx('admin.careerApplicationsPanel.auto.accessibility.003', 'Select application for bulk actions')}
                      onPress={(e: any) => {
                        e?.stopPropagation?.();
                        setBulkSelected((p) => p.includes(app.application_id) ? p.filter((x) => x !== app.application_id) : [...p, app.application_id]);
                      }}
                      style={{ width: 20, height: 20, borderRadius: 4, borderWidth: 1.5, borderColor: bulkSelected.includes(app.application_id) ? 'var(--app-primary)' : AC.borderStrong, backgroundColor: bulkSelected.includes(app.application_id) ? 'var(--app-primary)' : 'transparent', justifyContent: 'center', alignItems: 'center' }}
                      data-testid={`bulk-checkbox-${app.application_id}`} testID={`bulk-checkbox-${app.application_id}`}
                    >
                      {bulkSelected.includes(app.application_id) && <Ionicons name="checkmark" size={12} color="var(--app-primary-text)" />}
                    </TouchableOpacity>
                  )}
                  {compareMode && (
                    <View style={{ width: 22, height: 22, borderRadius: 4, borderWidth: 1.5, borderColor: isSelected ? 'var(--app-success)' : hasAnalysis ? AC.textDim : AC.borderStrong, backgroundColor: isSelected ? 'var(--app-success)' : 'transparent', justifyContent: 'center', alignItems: 'center' }} data-testid={`compare-checkbox-${app.application_id}`} testID={`compare-checkbox-${app.application_id}`}>
                      {isSelected && <Ionicons name="checkmark" size={14} color={AC.primaryText} />}
                    </View>
                  )}
                  <View style={{ width: 40, height: 40, borderRadius: 20, backgroundColor: (globalThis as any).__alphaColor(STATUS_CONFIG[app.status]?.color, '18'), justifyContent: 'center', alignItems: 'center' }}>
                    <Text style={{ color: STATUS_CONFIG[app.status]?.color || AC.textDim, fontSize: 15, fontWeight: '800' }}>{app.full_name.charAt(0).toUpperCase()}</Text>
                  </View>
                  <View style={{ flex: 1 }}>
                    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                      <Text style={{ color: AC.text, fontSize: 14, fontWeight: '700' }}>{app.full_name}</Text>
                      {hasAnalysis && <Ionicons name="analytics" size={12} color={'var(--app-success)'} />}
                      {(app.unread_applicant_replies || 0) > 0 && (
                        <View
                          style={{
                            flexDirection: 'row', alignItems: 'center', gap: 3,
                            backgroundColor: 'var(--app-success)',
                            paddingHorizontal: 6, paddingVertical: 2,
                            borderRadius: 999,
                          }}
                          data-testid={`app-row-unread-${app.application_id}`}
                          testID={`app-row-unread-${app.application_id}`}
                        >
                          <Ionicons name="mail-unread" size={9} color="var(--app-primary-text)" />
                          <Text style={{ color: 'var(--app-primary-text)', fontSize: 9, fontWeight: '800' }}>
                            {app.unread_applicant_replies} new
                          </Text>
                        </View>
                      )}
                    </View>
                    <Text style={{ color: AC.textDim, fontSize: 12, marginTop: 1 }}>{app.position}</Text>
                  </View>
                </View>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, flexShrink: 0 }}>
                  <ResumeScoreBadge app={app} onScored={() => fetchData()} />
                  <StatusBadge status={app.status} />
                  <InterviewResponseChip
                    interview={app.interview}
                    onPress={app.interview?.candidate_response === 'reschedule_requested' ? () => setRescheduleApp(app) : undefined}
                    testId={`interview-response-chip-${app.application_id}`}
                  />
                  {app.status !== 'interview' && app.status !== 'rejected' && (
                    <TouchableOpacity
                      onPress={(e: any) => { e?.stopPropagation?.(); setInviteApp(app); }}
                      style={{ flexDirection: 'row', alignItems: 'center', gap: 4, backgroundColor: 'var(--app-info-soft)', borderWidth: 1, borderColor: 'var(--app-info)', paddingHorizontal: 10, paddingVertical: 5, borderRadius: 14 }}
                      data-testid={`invite-interview-btn-${app.application_id}`}
                      testID={`invite-interview-btn-${app.application_id}`}
                    >
                      <Ionicons name="calendar" size={11} color={'var(--app-info)'} />
                      <Text style={{ color: 'var(--app-info)', fontSize: 11, fontWeight: '700' }}>{tx('admin.careerApplicationsPanel.auto.text.043', 'Invite')}</Text>
                    </TouchableOpacity>
                  )}
                  <TouchableOpacity accessibilityLabel={tx('admin.careerApplicationsPanel.auto.accessibility.004', 'Open candidate tracker link')}
                    onPress={(e: any) => {
                      e?.stopPropagation?.();
                      const url = `${typeof window !== 'undefined' && window.location?.origin ? window.location.origin : ''}/careers/track/${app.application_id}`;
                      try {
                        if (typeof window !== 'undefined') window.open(url, '_blank', 'noopener');
                      } catch { /* noop */ }
                    }}
                    style={{ flexDirection: 'row', alignItems: 'center', gap: 4, backgroundColor: 'var(--app-info-soft)', borderWidth: 1, borderColor: 'var(--app-info)', paddingHorizontal: 10, paddingVertical: 5, borderRadius: 14 }}
                    accessibilityLabel={`Open public tracker for ${app.full_name}`}
                    data-testid={`open-tracker-btn-${app.application_id}`}
                    testID={`open-tracker-btn-${app.application_id}`}
                  >
                    <Ionicons name="open-outline" size={11} color={'var(--app-info)'} />
                    <Text style={{ color: 'var(--app-info)', fontSize: 11, fontWeight: '700' }}>{tx('admin.careerApplicationsPanel.auto.text.044', 'Tracker')}</Text>
                  </TouchableOpacity>
                  <Text style={{ color: AC.textDim, fontSize: 11 }}>{new Date(app.submitted_at).toLocaleDateString()}</Text>
                  <Ionicons name="chevron-forward" size={14} color="var(--app-text-sec)" />
                </View>
              </View>
            </TouchableOpacity>
            );
          })}
        </View>
      )}

      {/* Position Breakdown */}
      {stats && stats.by_position && Object.keys(stats.by_position).length > 0 && (
        <View style={{ backgroundColor: AC.bgAlt, borderRadius: 12, padding: m ? 12 : 16, marginTop: 20, borderWidth: 1, borderColor: AC.border }}>
          <Text style={{ color: AC.text, fontSize: 14, fontWeight: '700', marginBottom: 12 }}>{tx('admin.careerApplicationsPanel.auto.text.045', 'Applications by Position')}</Text>
          <View style={{ gap: 8 }}>
            {Object.entries(stats.by_position).map(([pos, count]) => {
              const maxVal = Math.max(...Object.values(stats.by_position));
              const pct = maxVal > 0 ? (count / maxVal) * 100 : 0;
              return (
                <View key={pos}>
                  <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginBottom: 4 }}>
                    <Text style={{ color: AC.textSec, fontSize: 12, fontWeight: '500' }}>{pos}</Text>
                    <Text style={{ color: AC.textMuted, fontSize: 12, fontWeight: '700' }}>{count}</Text>
                  </View>
                  <View style={{ height: 6, borderRadius: 3, backgroundColor: AC.border }}>
                    <View style={{ height: 6, borderRadius: 3, backgroundColor: colors.primary, width: `${pct}%` as any }} />
                  </View>
                </View>
              );
            })}
          </View>
        </View>
      )}

      {/* Detail Modal */}
      {selectedApp && !compareMode && (
        <DetailModal
          app={selectedApp}
          onClose={() => setSelectedApp(null)}
          onStatusUpdate={handleStatusUpdate}
          onRefresh={async () => {
            await fetchData();
            const res = await api.get('/careers/applications');
            const data = res.data;
            const updated = (data.applications || []).find((a: Application) => a.application_id === selectedApp.application_id);
            if (updated) setSelectedApp(updated);
          }}
        />
      )}

      {/* Compare Modal */}
      {showCompare && compareList.length >= 2 && (
        <CompareModal candidates={compareList} onClose={() => setShowCompare(false)} />
      )}

      {/* Quick Invite Modal */}
      {inviteApp && (
        <QuickInviteModal
          app={inviteApp}
          onClose={() => setInviteApp(null)}
          onInvited={async () => { await fetchData(); setInviteApp(null); }}
        />
      )}

      {/* Reschedule details modal */}
      {rescheduleApp && (
        <RescheduleDetailsModal
          app={rescheduleApp}
          onClose={() => setRescheduleApp(null)}
          onOpenStudio={() => {
            const toOpen = rescheduleApp;
            setRescheduleApp(null);
            setSelectedApp(toOpen);
          }}
        />
      )}

      {showStalled && (
        <StalledModal
          onClose={() => setShowStalled(false)}
          onOpenApp={(appId) => {
            const match = apps.find((a) => a.application_id === appId);
            if (match) { setSelectedApp(match); setShowStalled(false); }
          }}
        />
      )}
      {showDuplicates && (
        <DuplicatesModal onClose={() => setShowDuplicates(false)} onMerged={fetchData} />
      )}
      {showGDPR && <GDPRRetentionPanel onClose={() => setShowGDPR(false)} />}
      <BulkActionsToolbar
        selectedIds={bulkSelected}
        onClear={() => setBulkSelected([])}
        onApplied={() => { setBulkSelected([]); fetchData(); }}
      />
    </View>
  );
}

function QuickInviteModal({ app, onClose, onInvited }: { app: Application; onClose: () => void; onInvited: () => void | Promise<void> }) {
  const { width } = useWindowDimensions();
  const m = width < 640;
  // Default: tomorrow at 10:00
  const tomorrow = new Date(); tomorrow.setDate(tomorrow.getDate() + 1);
  const yyyy = tomorrow.getFullYear();
  const mm = String(tomorrow.getMonth() + 1).padStart(2, '0');
  const dd = String(tomorrow.getDate()).padStart(2, '0');
  const [date, setDate] = useState(`${yyyy}-${mm}-${dd}`);
  const [time, setTime] = useState('10:00');
  const [duration, setDuration] = useState(45);
  const [interviewType, setInterviewType] = useState<'video' | 'phone' | 'onsite'>('video');
  const [message, setMessage] = useState(`Hi ${app.full_name?.split(' ')[0] || 'there'}, we'd love to chat about your application for the ${app.position} role.`);
  const [sending, setSending] = useState(false);
  const [status, setStatus] = useState('');

  const handleSend = async () => {
    if (!date || !time) { setStatus('Please pick a date and time.'); return; }
    setSending(true);
    setStatus('');
    try {
      const res = await api.post(`/careers/applications/${app.application_id}/invite-interview`, {
        date, time, duration_minutes: duration, interview_type: interviewType, message,
      });
      const data = res.data || {};
      if (data.success) {
        const emailBit = data.email_sent ? 'Email sent to candidate.' : 'Interview saved (email delivery failed; check logs).';
        setStatus(`✓ Invitation booked. ${emailBit}`);
        setTimeout(async () => { await onInvited(); }, 1200);
      } else {
        setStatus('Failed to send invitation.');
      }
    } catch (e: any) {
      setStatus(e?.response?.data?.detail || 'Failed to send invitation.');
    }
    setSending(false);
  };

  return (
    <View style={{ position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, backgroundColor: AC.overlay, zIndex: 250, justifyContent: 'center', alignItems: 'center', padding: 16 }} data-testid="invite-interview-modal" testID="invite-interview-modal">
      <View style={{ backgroundColor: AC.bgAlt, borderRadius: 16, width: '100%', maxWidth: 520, borderWidth: 1, borderColor: AC.borderStrong }}>
        <ScrollView style={{ padding: m ? 16 : 24 }}>
          <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 16 }}>
            <View style={{ flex: 1 }}>
              <Text style={{ color: AC.text, fontSize: 18, fontWeight: '800' }}>{tx('admin.careerApplicationsPanel.auto.text.046', 'Invite to Interview')}</Text>
              <Text style={{ color: AC.textDim, fontSize: 12, marginTop: 2 }}>{app.full_name} — {app.position}</Text>
            </View>
            <TouchableOpacity onPress={onClose} style={{ width: 32, height: 32, borderRadius: 16, backgroundColor: AC.border, justifyContent: 'center', alignItems: 'center' }} data-testid="invite-modal-close" testID="invite-modal-close">
              <Ionicons name="close" size={16} color={AC.textSec} />
            </TouchableOpacity>
          </View>

          <Text style={{ color: AC.textSec, fontSize: 11, fontWeight: '700', letterSpacing: 0.5, marginBottom: 6 }}>{tx('admin.careerApplicationsPanel.auto.text.047', 'DATE')}</Text>
          <TextInput value={date} onChangeText={setDate} placeholder={tx('admin.careerApplicationsPanel.auto.placeholder.006', 'YYYY-MM-DD')} placeholderTextColor={AC.textDim as any}
            style={{ backgroundColor: AC.surface, color: AC.text, borderWidth: 1, borderColor: AC.border, borderRadius: 8, padding: 10, marginBottom: 12, fontSize: 14 }}
            data-testid="invite-date-input" testID="invite-date-input" />

          <Text style={{ color: AC.textSec, fontSize: 11, fontWeight: '700', letterSpacing: 0.5, marginBottom: 6 }}>{tx('admin.careerApplicationsPanel.auto.text.048', 'TIME (UTC)')}</Text>
          <TextInput value={time} onChangeText={setTime} placeholder={tx('admin.careerApplicationsPanel.auto.placeholder.007', 'HH:MM (24h)')} placeholderTextColor={AC.textDim as any}
            style={{ backgroundColor: AC.surface, color: AC.text, borderWidth: 1, borderColor: AC.border, borderRadius: 8, padding: 10, marginBottom: 12, fontSize: 14 }}
            data-testid="invite-time-input" testID="invite-time-input" />

          <Text style={{ color: AC.textSec, fontSize: 11, fontWeight: '700', letterSpacing: 0.5, marginBottom: 6 }}>{tx('admin.careerApplicationsPanel.auto.text.049', 'DURATION')}</Text>
          <View style={{ flexDirection: 'row', gap: 8, marginBottom: 12 }}>
            {[30, 45, 60].map(d => (
              <TouchableOpacity key={d} onPress={() => setDuration(d)}
                style={{ flex: 1, paddingVertical: 10, borderRadius: 8, borderWidth: 1, alignItems: 'center', backgroundColor: duration === d ? AC.primarySoft : AC.surface, borderColor: duration === d ? AC.primary : AC.border }}
                data-testid={`invite-duration-${d}`} testID={`invite-duration-${d}`}>
                <Text style={{ color: duration === d ? AC.primary : AC.textSec, fontSize: 13, fontWeight: '700' }}>{d} min</Text>
              </TouchableOpacity>
            ))}
          </View>

          <Text style={{ color: AC.textSec, fontSize: 11, fontWeight: '700', letterSpacing: 0.5, marginBottom: 6 }}>{tx('admin.careerApplicationsPanel.auto.text.050', 'TYPE')}</Text>
          <View style={{ flexDirection: 'row', gap: 8, marginBottom: 12 }}>
            {(['video', 'phone', 'onsite'] as const).map(t => (
              <TouchableOpacity key={t} onPress={() => setInterviewType(t)}
                style={{ flex: 1, paddingVertical: 10, borderRadius: 8, borderWidth: 1, alignItems: 'center', backgroundColor: interviewType === t ? AC.accentSoft : AC.surface, borderColor: interviewType === t ? AC.accent : AC.border }}
                data-testid={`invite-type-${t}`} testID={`invite-type-${t}`}>
                <Text style={{ color: interviewType === t ? AC.accent : AC.textSec, fontSize: 13, fontWeight: '700' }}>{t.charAt(0).toUpperCase() + t.slice(1)}</Text>
              </TouchableOpacity>
            ))}
          </View>

          <Text style={{ color: AC.textSec, fontSize: 11, fontWeight: '700', letterSpacing: 0.5, marginBottom: 6 }}>{tx('admin.careerApplicationsPanel.auto.text.051', 'MESSAGE (optional)')}</Text>
          <TextInput value={message} onChangeText={setMessage} multiline numberOfLines={4}
            placeholder={tx('admin.careerApplicationsPanel.auto.placeholder.008', 'Add a personal note to the candidate…')} placeholderTextColor={AC.textDim as any}
            style={{ backgroundColor: AC.surface, color: AC.text, borderWidth: 1, borderColor: AC.border, borderRadius: 8, padding: 10, marginBottom: 12, fontSize: 13, minHeight: 80, textAlignVertical: 'top' as any }}
            data-testid="invite-message-input" testID="invite-message-input" />

          {status ? (
            <Text style={{ color: status.startsWith('✓') ? AC.success : AC.error, fontSize: 12, marginBottom: 10, fontWeight: '600' }} data-testid="invite-status-msg" testID="invite-status-msg">{status}</Text>
          ) : null}

          <View style={{ flexDirection: 'row', gap: 8, marginTop: 8 }}>
            <TouchableOpacity onPress={onClose} disabled={sending}
              style={{ flex: 1, paddingVertical: 12, borderRadius: 8, borderWidth: 1, borderColor: AC.border, alignItems: 'center' }}
              data-testid="invite-cancel-btn" testID="invite-cancel-btn">
              <Text style={{ color: AC.textSec, fontSize: 13, fontWeight: '700' }}>{tx('admin.careerApplicationsPanel.auto.text.052', 'Cancel')}</Text>
            </TouchableOpacity>
            <TouchableOpacity onPress={handleSend} disabled={sending}
              style={{ flex: 2, paddingVertical: 12, borderRadius: 8, backgroundColor: sending ? AC.textDim : AC.primary, alignItems: 'center', flexDirection: 'row', justifyContent: 'center', gap: 6 }}
              data-testid="invite-send-btn" testID="invite-send-btn">
              {sending ? <ActivityIndicator color={AC.primaryText} size="small" /> : <Ionicons name="send" size={14} color={AC.primaryText} />}
              <Text style={{ color: AC.primaryText, fontSize: 13, fontWeight: '700' }}>{sending ? 'Sending…' : 'Send Invitation'}</Text>
            </TouchableOpacity>
          </View>
        </ScrollView>
      </View>
    </View>
  );
}
