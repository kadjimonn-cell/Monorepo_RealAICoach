import React, { useEffect, useState, useCallback, useRef } from 'react';
import { View, Text, TouchableOpacity, TextInput, ActivityIndicator, Alert, Platform, ScrollView, useWindowDimensions, Modal } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { useLiveQuery } from '../../hooks/useLiveQuery';
import AutoFixBanner from './AutoFixBanner';
import { useManagedWebSocket } from '../../hooks/useManagedWebSocket';
import { useHybridPolling } from '../../hooks/useHybridPolling';
import { handleRecoverableError } from '../../utils/handleRecoverableError';
import { getHybridPollingInterval, getWorkflowPollingPreset } from '../../utils/hybridPolling';

import { getAdminColors } from '../../hooks/useAdminTheme';
import { useTheme } from '../../context/ThemeContext';
import { useTranslation } from '../../hooks/useTranslation';
function getC(dark) {
  const A = getAdminColors(dark);
  return {
    ...A,
    bg: A.bg,
    card: A.card,
    card2: A.cardSoft,
    border: A.border,
    text: A.text,
    muted: A.textDim,
    sec: A.textMuted,
    green: A.success,
    red: A.error,
    blue: A.primary,
    yellow: A.warning,
    purple: A.purple,
    cyan: A.info,
    orange: A.orange,
    indigo: A.indigo,
    pink: A.errorText,
    lime: A.successText,
    teal: A.teal,
    orangeText: A.orangeText,
    indigoText: A.indigoText,
  };
}
const C = getC(true);
const STATUS_COLORS: any = { open: C.yellow, pending: C.blue, in_progress: C.cyan, escalated: C.red, resolved: C.green, closed: C.muted, reopened: C.orange };
const PRIORITY_COLORS: any = { low: C.muted, medium: C.blue, high: C.yellow, urgent: C.red, critical: C.red };
const STATUS_ICONS: any = { open: 'alert-circle', pending: 'time', in_progress: 'sync', escalated: 'arrow-up', resolved: 'checkmark-circle', closed: 'lock-closed', reopened: 'refresh' };
const TOPIC_COLORS: any = { billing: C.green, technical: C.blue, account: C.indigo, feature_request: C.purple, bug_report: C.red, general: C.muted };
const TOPIC_ICONS: any = { billing: 'card', technical: 'code-slash', account: 'person', feature_request: 'bulb', bug_report: 'bug', general: 'help-circle' };
const MOOD_ICONS: any = { happy: 'happy', neutral: 'remove-circle', confused: 'help-circle', frustrated: 'sad', angry: 'flame', desperate: 'warning', disappointed: 'thumbs-down' };
const MOOD_COLORS: any = { happy: C.green, neutral: C.muted, confused: C.yellow, frustrated: C.orange, angry: C.red, desperate: C.red, disappointed: C.orange };
const WORKFLOW_POLLING_PRESET = getWorkflowPollingPreset('support-ticket-fallback');
const TICKET_POLL_MAX_INTERVAL_MS = WORKFLOW_POLLING_PRESET.slowIntervalMs;
const TICKET_POLL_MIN_INTERVAL_MS = WORKFLOW_POLLING_PRESET.fastIntervalMs;

// ── AI Routing Badge ──
function AIRoutingBadge({ ticket }: { ticket: any }) {
  const cls = ticket?.ai_classification;
  if (!cls || cls.classified_by === 'none') return null;
  const isAI = cls.classified_by === 'ai';
  return (
    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 3 }}>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 3, backgroundColor: isAI ? (globalThis as any).__alphaColor(C.purple, '18') : C.muted + '18', borderRadius: 4, paddingHorizontal: 5, paddingVertical: 2 }}>
        <Ionicons name={isAI ? 'sparkles' : 'build'} size={8} color={isAI ? C.purple : C.muted} />
        <Text style={{ fontSize: 8, fontWeight: '800', color: isAI ? C.purple : C.muted }}>{isAI ? 'AI' : 'AUTO'}</Text>
      </View>
      {cls.topic && (
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 2, backgroundColor: (globalThis as any).__alphaColor((TOPIC_COLORS[cls.topic] || C.muted), '15'), borderRadius: 4, paddingHorizontal: 5, paddingVertical: 2 }}>
          <Ionicons name={(TOPIC_ICONS[cls.topic] || 'help-circle') as any} size={8} color={TOPIC_COLORS[cls.topic] || C.muted} />
          <Text style={{ fontSize: 8, fontWeight: '700', color: TOPIC_COLORS[cls.topic] || C.muted }}>{cls.topic.replace(/_/g, ' ')}</Text>
        </View>
      )}
    </View>
  );
}

// ── Sentiment Indicator ──
function SentimentBadge({ sentiment }: { sentiment: any }) {
  if (!sentiment) return null;
  const color = MOOD_COLORS[sentiment.mood] || C.muted;
  return (
    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4, backgroundColor: (globalThis as any).__alphaColor(color, '10'), borderRadius: 6, paddingHorizontal: 6, paddingVertical: 3, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(color, '20') }}>
      <Ionicons name={(MOOD_ICONS[sentiment.mood] || 'remove-circle') as any} size={12} color={color} />
      <Text style={{ fontSize: 10, fontWeight: '700', color }}>{sentiment.mood}</Text>
      <View style={{ width: 1, height: 10, backgroundColor: (globalThis as any).__alphaColor(color, '30') }} />
      <Text style={{ fontSize: 9, color }}>{sentiment.frustration_level}/10</Text>
    </View>
  );
}

// ── Ticket Risk Heat Badge ──
function RiskHeatBadge({
  riskHeat,
  compact = false,
  testId,
}: {
  riskHeat: any;
  compact?: boolean;
  testId: string;
}) {
  const level = String(riskHeat?.level || 'low').toLowerCase();
  const score = Number(riskHeat?.score || 0);
  const color = level === 'critical'
    ? C.red
    : level === 'high'
      ? C.orange
      : level === 'medium'
        ? C.yellow
        : C.green;

  return (
    <View
      style={{
        flexDirection: 'row',
        alignItems: 'center',
        gap: 4,
        backgroundColor: (globalThis as any).__alphaColor(color, '14'),
        borderRadius: compact ? 5 : 8,
        paddingHorizontal: compact ? 6 : 8,
        paddingVertical: compact ? 2 : 4,
        borderWidth: 1,
        borderColor: (globalThis as any).__alphaColor(color, '30'),
      }}
      data-testid={testId}
      testID={testId}
    >
      <Ionicons name="flame" size={compact ? 10 : 12} color={color} />
      <Text style={{ fontSize: compact ? 9 : 10, fontWeight: '800', color }}>{level.toUpperCase()}</Text>
      <Text style={{ fontSize: compact ? 8 : 10, color }}>{score}</Text>
    </View>
  );
}

// ── Helpers for attachments ──
function _attName(a: any) { return a?.original_name || a?.filename || 'Untitled'; }
function _attType(a: any) { return a?.mime_type || a?.content_type || ''; }
function _apiAbsUrl(path: string) {
  const base = String(api.defaults.baseURL || '/api');
  const origin = base.endsWith('/api') ? base.slice(0, -4) : base;
  if (/^https?:\/\//i.test(path)) return path;
  if (path.startsWith('/api/')) return `${origin}${path}`;
  if (path.startsWith('/')) return `${base}${path}`;
  return `${base}/${path}`;
}
function _attUrl(a: any) {
  if (a?.file_id) return `${api.defaults.baseURL}/tickets/attachment/${a.file_id}`;
  if (a?.attachment_id) return _apiAbsUrl(`/api/support/attachment/${a.attachment_id}`);
  if (a?.url) return _apiAbsUrl(String(a.url));
  return '';
}
function _attDownloadUrl(a: any) {
  if (a?.file_id) return `${api.defaults.baseURL}/tickets/attachment/${a.file_id}`;
  if (a?.attachment_id) return _apiAbsUrl(`/api/support/attachment/${a.attachment_id}?download=1`);
  if (a?.download_url) return _apiAbsUrl(String(a.download_url));
  return _attUrl(a);
}
function _isImage(a: any) { return _attType(a).startsWith('image/') || /\.(jpg|jpeg|png|gif|webp|svg|bmp)$/i.test(_attName(a)); }
function _isPdf(a: any) { return _attType(a) === 'application/pdf' || /\.pdf$/i.test(_attName(a)); }
function _isVideo(a: any) { return _attType(a).startsWith('video/') || /\.(mp4|mov|avi|webm|mkv)$/i.test(_attName(a)); }
function _formatSize(b: number) { if (!b) return ''; if (b < 1024) return `${b} B`; if (b < 1048576) return `${(b/1024).toFixed(1)} KB`; return `${(b/1048576).toFixed(1)} MB`; }
function _fileIcon(a: any): string { if (_isImage(a)) return 'image'; if (_isPdf(a)) return 'document-text'; if (_isVideo(a)) return 'videocam'; if (_attType(a).startsWith('audio/')) return 'musical-note'; if (/\.zip|\.rar|\.7z|\.tar|\.gz/i.test(_attName(a))) return 'archive'; return 'document-attach'; }
function _fileColor(a: any): string { if (_isImage(a)) return C.purple; if (_isPdf(a)) return C.red; if (_isVideo(a)) return C.blue; if (_attType(a).startsWith('audio/')) return C.orange; return C.muted; }

// ── Attachment Viewer Modal (Enterprise) ──
function AttachmentViewer({ attachments, visible, onClose, colors, initialIndex = 0 }: any) {
  const { t } = useTranslation();
  const tx = useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);
  const { width: sw, height: sh } = useWindowDimensions();
  const [activeIdx, setActiveIdx] = useState(0);
  const [zoomed, setZoomed] = useState(false);

  // Keyboard navigation (web only)
  useEffect(() => {
    if (!visible || Platform.OS !== 'web') return;
    const handler = (e: any) => {
      if (e.key === 'ArrowRight' || e.key === 'ArrowDown') { setActiveIdx(i => Math.min(i + 1, (attachments?.length || 1) - 1)); setZoomed(false); }
      else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') { setActiveIdx(i => Math.max(i - 1, 0)); setZoomed(false); }
      else if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [visible, attachments?.length, onClose]);

  // Reset idx on open
  useEffect(() => {
    if (visible) {
      setActiveIdx(Math.max(0, Math.min(initialIndex, (attachments?.length || 1) - 1)));
      setZoomed(false);
    }
  }, [visible, initialIndex, attachments?.length]);

  if (!attachments?.length) return null;
  const att = attachments[activeIdx];
  const imgUrl = _attUrl(att);
  const isImg = _isImage(att);
  const isPdf = _isPdf(att);
  const isVid = _isVideo(att);

  return (
    <Modal visible={visible} transparent animationType="fade" onRequestClose={onClose}>
      <View style={{ flex: 1, backgroundColor: `${colors.overlay}F2` }} data-testid="attachment-viewer-modal" testID="attachment-viewer-modal">
        {/* Top Bar */}
        <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', padding: 14, borderBottomWidth: 1, borderBottomColor: `${colors.primaryText}14`, zIndex: 10 }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, flex: 1 }}>
            <View style={{ width: 32, height: 32, borderRadius: 8, backgroundColor: (globalThis as any).__alphaColor(_fileColor(att), '20'), alignItems: 'center', justifyContent: 'center' }}>
              <Ionicons name={_fileIcon(att) as any} size={16} color={_fileColor(att)} />
            </View>
            <View style={{ flex: 1 }}>
              <Text style={{ color: colors.primaryText, fontSize: 13, fontWeight: '700' }} numberOfLines={1}>{_attName(att)}</Text>
              <View style={{ flexDirection: 'row', gap: 8, marginTop: 2 }}>
                <Text style={{ color: `${colors.primaryText}80`, fontSize: 10 }}>{_attType(att) || 'Unknown'}</Text>
                {att?.size ? <Text style={{ color: `${colors.primaryText}66`, fontSize: 10 }}>{_formatSize(att.size)}</Text> : null}
                {attachments.length > 1 && <Text style={{ color: C.cyan, fontSize: 10, fontWeight: '700' }}>{activeIdx + 1} of {attachments.length}</Text>}
              </View>
            </View>
          </View>
          <View style={{ flexDirection: 'row', gap: 8 }}>
            {isImg && (
              <TouchableOpacity onPress={() => setZoomed(!zoomed)} style={{ width: 34, height: 34, borderRadius: 8, backgroundColor: zoomed ? (globalThis as any).__alphaColor(C.cyan, '25') : `${colors.primaryText}14`, alignItems: 'center', justifyContent: 'center' }} data-testid="attachment-zoom-btn" testID="attachment-zoom-btn">
                <Ionicons name={zoomed ? 'contract' : 'expand'} size={16} color={zoomed ? C.cyan : colors.primaryText} />
              </TouchableOpacity>
            )}
            {imgUrl && Platform.OS === 'web' && (
              <TouchableOpacity onPress={() => window.open(_attDownloadUrl(att), '_blank')} style={{ width: 34, height: 34, borderRadius: 8, backgroundColor: `${colors.primaryText}14`, alignItems: 'center', justifyContent: 'center' }} data-testid="attachment-download-btn" testID="attachment-download-btn">
                <Ionicons name="download-outline" size={16} color={colors.primaryText} />
              </TouchableOpacity>
            )}
            <TouchableOpacity onPress={onClose} style={{ width: 34, height: 34, borderRadius: 8, backgroundColor: `${colors.primaryText}1F`, alignItems: 'center', justifyContent: 'center' }} data-testid="attachment-close-btn" testID="attachment-close-btn">
              <Ionicons name="close" size={18} color={colors.primaryText} />
            </TouchableOpacity>
          </View>
        </View>

        {/* Main Content */}
        <View style={{ flex: 1, flexDirection: 'row' }}>
          {/* Left nav arrow */}
          {attachments.length > 1 && activeIdx > 0 && (
            <TouchableOpacity onPress={() => { setActiveIdx(i => i - 1); setZoomed(false); }} style={{ position: 'absolute', left: 8, top: '45%', zIndex: 10, width: 40, height: 40, borderRadius: 20, backgroundColor: `${colors.overlay}99`, alignItems: 'center', justifyContent: 'center' }} data-testid="attachment-prev-btn" testID="attachment-prev-btn">
              <Ionicons name="chevron-back" size={22} color={colors.primaryText} />
            </TouchableOpacity>
          )}
          {/* Right nav arrow */}
          {attachments.length > 1 && activeIdx < attachments.length - 1 && (
            <TouchableOpacity onPress={() => { setActiveIdx(i => i + 1); setZoomed(false); }} style={{ position: 'absolute', right: 8, top: '45%', zIndex: 10, width: 40, height: 40, borderRadius: 20, backgroundColor: `${colors.overlay}99`, alignItems: 'center', justifyContent: 'center' }} data-testid="attachment-next-btn" testID="attachment-next-btn">
              <Ionicons name="chevron-forward" size={22} color={colors.primaryText} />
            </TouchableOpacity>
          )}

          {/* Preview area */}
          <ScrollView style={{ flex: 1 }} contentContainerStyle={{ alignItems: 'center', justifyContent: 'center', minHeight: '100%', padding: 20 }}>
            {isImg && imgUrl ? (
              Platform.OS === 'web' ? (
                <img src={imgUrl} alt={_attName(att)} style={{ maxWidth: zoomed ? '100%' : Math.min(sw - 80, 900), maxHeight: zoomed ? 'none' : sh - 200, objectFit: 'contain', borderRadius: 6, cursor: 'pointer' }} onClick={() => setZoomed(!zoomed)} />
              ) : (
                <Text style={{ color: C.muted }}>{tx('supportTickets.attachments.viewer.imagePreviewUnavailable', 'Image preview not available')}</Text>
              )
            ) : isVid && imgUrl && Platform.OS === 'web' ? (
              <video src={imgUrl} controls style={{ maxWidth: Math.min(sw - 80, 900), maxHeight: sh - 200, borderRadius: 6 }} />
            ) : isPdf && Platform.OS === 'web' ? (
              <iframe src={imgUrl} style={{ width: Math.min(sw - 80, 900), height: sh - 200, border: 'none', borderRadius: 6 }} title={_attName(att)} />
            ) : (
              <View style={{ alignItems: 'center', padding: 40 }}>
                <View style={{ width: 80, height: 80, borderRadius: 20, backgroundColor: (globalThis as any).__alphaColor(_fileColor(att), '15'), alignItems: 'center', justifyContent: 'center', marginBottom: 16 }}>
                  <Ionicons name={_fileIcon(att) as any} size={40} color={_fileColor(att)} />
                </View>
                <Text style={{ color: colors.primaryText, fontSize: 16, fontWeight: '700', textAlign: 'center' }}>{_attName(att)}</Text>
                <Text style={{ color: `${colors.primaryText}80`, fontSize: 12, marginTop: 4 }}>{_attType(att)}</Text>
                {att?.size ? <Text style={{ color: `${colors.primaryText}66`, fontSize: 11, marginTop: 2 }}>{_formatSize(att.size)}</Text> : null}
                {imgUrl && Platform.OS === 'web' && (
                  <TouchableOpacity aria-label="Download File" onPress={() => window.open(_attDownloadUrl(att), '_blank')} style={{ marginTop: 20, backgroundColor: C.blue, paddingHorizontal: 24, paddingVertical: 10, borderRadius: 10 }}>
                    <Text style={{ color: colors.primaryText, fontWeight: '700', fontSize: 13 }}>{tx('supportTickets.attachments.viewer.downloadFile', 'Download File')}</Text>
                  </TouchableOpacity>
                )}
              </View>
            )}
          </ScrollView>

          {/* Side thumbnail strip (when > 1 attachment) */}
          {attachments.length > 1 && sw > 600 && (
            <ScrollView style={{ width: 80, backgroundColor: `${colors.overlay}66`, borderLeftWidth: 1, borderLeftColor: `${colors.primaryText}0F` }} contentContainerStyle={{ padding: 8, gap: 6 }}>
              {attachments.map((a: any, i: number) => {
                const thumbUrl = _isImage(a) ? _attUrl(a) : null;
                const active = i === activeIdx;
                return (
                  <TouchableOpacity key={i} onPress={() => { setActiveIdx(i); setZoomed(false); }} style={{ width: 64, height: 64, borderRadius: 10, overflow: 'hidden', borderWidth: 2, borderColor: active ? C.cyan : `${colors.primaryText}14`, backgroundColor: active ? (globalThis as any).__alphaColor(C.cyan, '10') : `${colors.primaryText}0A` }} data-testid={`attachment-thumb-${i}`} testID={`attachment-thumb-${i}`}>
                    {thumbUrl && Platform.OS === 'web' ? (
                      <img src={thumbUrl} style={{ width: '100%', height: '100%', objectFit: 'cover' }} alt={_attName(a).slice(0, 8)} aria-label={_attName(a).slice(0, 8)} />
                    ) : (
                      <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center' }}>
                        <Ionicons name={_fileIcon(a) as any} size={22} color={active ? C.cyan : C.muted} />
                        <Text style={{ fontSize: 7, color: active ? C.cyan : C.muted, marginTop: 2, textAlign: 'center' }} numberOfLines={1}>{_attName(a).slice(0, 8)}</Text>
                      </View>
                    )}
                  </TouchableOpacity>
                );
              })}
            </ScrollView>
          )}
        </View>

        {/* Bottom thumbnail strip (mobile or narrow screens) */}
        {attachments.length > 1 && sw <= 600 && (
          <View style={{ flexDirection: 'row', justifyContent: 'center', gap: 6, padding: 10, borderTopWidth: 1, borderTopColor: `${colors.primaryText}0F` }}>
            {attachments.map((a: any, i: number) => (
              <TouchableOpacity key={i} onPress={() => { setActiveIdx(i); setZoomed(false); }} style={{ width: 44, height: 44, borderRadius: 8, borderWidth: 2, borderColor: i === activeIdx ? C.cyan : `${colors.primaryText}1A`, backgroundColor: i === activeIdx ? (globalThis as any).__alphaColor(C.cyan, '15') : `${colors.primaryText}0D`, alignItems: 'center', justifyContent: 'center', overflow: 'hidden' }} data-testid={`attachment-thumb-${i}`} testID={`attachment-thumb-${i}`}>
                {_isImage(a) && Platform.OS === 'web' ? (
                  <img src={_attUrl(a)} style={{ width: '100%', height: '100%', objectFit: 'cover' }} alt="Decorative image" aria-label="Decorative image" />
                ) : (
                  <Ionicons name={_fileIcon(a) as any} size={18} color={i === activeIdx ? C.cyan : C.muted} />
                )}
              </TouchableOpacity>
            ))}
          </View>
        )}
      </View>
    </Modal>
  );
}

// ── Inline Attachment Grid (shown in ticket detail) ──
function AttachmentGrid({
  attachments,
  onViewAll,
  onPreview,
  onDownload,
}: {
  attachments: any[];
  onViewAll: () => void;
  onPreview: (index: number) => void;
  onDownload: (attachment: any) => void;
}) {
  const { t } = useTranslation();
  const tx = useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);
  if (!attachments?.length) return null;
  return (
    <View data-testid="attachment-grid" testID="attachment-grid" style={{ backgroundColor: C.card2, borderRadius: 12, padding: 12, marginBottom: 14, borderWidth: 1, borderColor: C.border }}>
      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
          <Ionicons name="attach" size={14} color={C.purpleText} />
          <Text style={{ fontSize: 12, fontWeight: '700', color: C.text }}>{tx('supportTickets.attachments.grid.title', 'Attachments')}</Text>
          <View style={{ backgroundColor: (globalThis as any).__alphaColor(C.purple, '18'), borderRadius: 6, paddingHorizontal: 6, paddingVertical: 1 }}>
            <Text style={{ fontSize: 10, fontWeight: '700', color: C.purpleText }}>{attachments.length}</Text>
          </View>
        </View>
        <TouchableOpacity onPress={onViewAll} data-testid="view-all-attachments-btn" testID="view-all-attachments-btn" style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}>
          <Text style={{ fontSize: 10, fontWeight: '600', color: C.cyan }}>{tx('supportTickets.attachments.grid.viewAll', 'View All')}</Text>
          <Ionicons name="expand" size={10} color={C.cyan} />
        </TouchableOpacity>
      </View>
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
        {attachments.map((a: any, i: number) => {
          const isImg = _isImage(a);
          const thumbUrl = isImg ? _attUrl(a) : null;
          return (
            <View key={i} data-testid={`attachment-inline-${i}`} testID={`attachment-inline-${i}`} style={{ width: 152, borderRadius: 10, overflow: 'hidden', backgroundColor: C.card, borderWidth: 1, borderColor: C.border }}>
              <TouchableOpacity onPress={() => onPreview(i)} data-testid={`attachment-inline-preview-${i}`} testID={`attachment-inline-preview-${i}`}>
                {isImg && thumbUrl && Platform.OS === 'web' ? (
                  <View style={{ width: '100%', height: 72, overflow: 'hidden' }}>
                    <img src={thumbUrl} style={{ width: '100%', height: '100%', objectFit: 'cover' }} alt="Decorative image" aria-label="Decorative image" />
                  </View>
                ) : (
                  <View style={{ width: '100%', height: 72, alignItems: 'center', justifyContent: 'center', backgroundColor: (globalThis as any).__alphaColor(_fileColor(a), '08') }}>
                    <Ionicons name={_fileIcon(a) as any} size={24} color={_fileColor(a)} />
                  </View>
                )}
              </TouchableOpacity>
              <View style={{ padding: 6 }}>
                <Text style={{ fontSize: 9, fontWeight: '700', color: C.text }} numberOfLines={1}>{_attName(a)}</Text>
                {a?.size ? <Text style={{ fontSize: 8, color: C.muted }}>{_formatSize(a.size)}</Text> : null}
                <View style={{ flexDirection: 'row', gap: 6, marginTop: 6 }}>
                  <TouchableOpacity onPress={() => onPreview(i)} style={{ flex: 1, borderRadius: 6, borderWidth: 1, borderColor: C.border, paddingVertical: 5, alignItems: 'center' }} data-testid={`attachment-preview-btn-${i}`} testID={`attachment-preview-btn-${i}`}>
                    <Text style={{ fontSize: 9, fontWeight: '700', color: C.cyan }}>Preview</Text>
                  </TouchableOpacity>
                  <TouchableOpacity onPress={() => onDownload(a)} style={{ flex: 1, borderRadius: 6, borderWidth: 1, borderColor: C.border, paddingVertical: 5, alignItems: 'center' }} data-testid={`attachment-download-inline-btn-${i}`} testID={`attachment-download-inline-btn-${i}`}>
                    <Text style={{ fontSize: 9, fontWeight: '700', color: C.blue }}>Download</Text>
                  </TouchableOpacity>
                </View>
              </View>
            </View>
          );
        })}
      </View>
    </View>
  );
}

// ── SLA Timer ──
function SLATimer({ ticket, colors }: any) {
  const created = ticket?.created_at ? new Date(ticket.created_at) : null;
  if (!created || ['resolved', 'closed'].includes(ticket?.status)) return null;
  const elapsed = Date.now() - created.getTime();
  const hours = Math.floor(elapsed / 3600000);
  const slaTarget = ticket?.priority === 'urgent' ? 4 : ticket?.priority === 'high' ? 12 : 24;
  const remaining = slaTarget - hours;
  const pct = Math.min(100, (hours / slaTarget) * 100);
  const urgentColor = remaining <= 0 ? C.red : remaining <= 2 ? C.yellow : C.green;

  return (
    <View style={{ backgroundColor: (globalThis as any).__alphaColor(urgentColor, '10'), borderRadius: 10, padding: 12, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(urgentColor, '25') }} data-testid="sla-timer" testID="sla-timer">
      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 6 }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
          <Ionicons name="timer" size={14} color={urgentColor} />
          <Text style={{ fontSize: 11, fontWeight: '700', color: urgentColor }}>SLA {remaining <= 0 ? 'BREACHED' : `${remaining}h remaining`}</Text>
        </View>
        <Text style={{ fontSize: 10, color: C.muted }}>{slaTarget}h target</Text>
      </View>
      <View style={{ height: 4, backgroundColor: C.border, borderRadius: 2, overflow: 'hidden' }}>
        <View style={{ width: `${pct}%`, height: '100%', backgroundColor: urgentColor, borderRadius: 2 }} />
      </View>
    </View>
  );
}

// ── Main Panel ──
export default function SupportTicketsPanel({ colors }: { colors: any }) {
  const { darkMode } = useTheme();
  const { t } = useTranslation();
  const tx = useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);
  const errorTitle = tx('supportTickets.common.error', 'Error');
  const C = getC(darkMode);
  const supportTitle = t('supportTickets.header.title');
  const { width } = useWindowDimensions();
  const isWide = width >= 900;
  const isMed = width >= 600;
  const useCompactSidebar = isWide && width < 1200;

  // Ticket list state
  const [page, setPage] = useState(1);
  const [statusFilter, setStatusFilter] = useState('all');
  const { data: ticketsData, loading, refetch: loadTickets } = useLiveQuery(`/admin/manage/tickets?page=${page}&limit=15&status=${statusFilter}`, { entity: 'tickets', pollInterval: 15000 });
  const { data: stats } = useLiveQuery('/admin/manage/tickets/stats/overview', { entity: 'tickets', pollInterval: 30000 });
  const { data: nudgesData, refetch: loadNudges } = useLiveQuery('/admin/manage/proactive-nudges?status=open&limit=25', { entity: 'tickets', pollInterval: 45000 });
  const tickets = ticketsData?.tickets || [];
  const total = ticketsData?.total || 0;
  const openNudges = nudgesData?.items || [];
  const nudgeOpenCount = nudgesData?.open || 0;
  const [selected, setSelected] = useState<any>(null);
  const [nudgeActionId, setNudgeActionId] = useState('');
  const [nudgesRunning, setNudgesRunning] = useState(false);

  // Reply state
  const [replyText, setReplyText] = useState('');
  const [replying, setReplying] = useState(false);

  // AI suggestion state
  const [aiSuggestion, setAiSuggestion] = useState('');
  const [aiLoading, setAiLoading] = useState(false);
  const [aiTone, setAiTone] = useState('professional');

  // Internal notes state
  const [noteText, setNoteText] = useState('');
  const [addingNote, setAddingNote] = useState(false);

  // Canned responses state
  const [cannedResponses, setCannedResponses] = useState<any[]>([]);
  const [showCanned, setShowCanned] = useState(false);
  const [newCannedTitle, setNewCannedTitle] = useState('');
  const [newCannedContent, setNewCannedContent] = useState('');

  // User context state
  const [userContext, setUserContext] = useState<any>(null);
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const [showUserCtx, setShowUserCtx] = useState(false);

  // Attachment viewer state
  const [showAttachments, setShowAttachments] = useState(false);
  const [attachmentStartIndex, setAttachmentStartIndex] = useState(0);

  // Action loading
  const [actionLoading, setActionLoading] = useState('');

  // Active tab in detail view
  const [detailTab, setDetailTab] = useState<'conversation' | 'notes' | 'history' | 'context'>('conversation');

  // ── WebSocket real-time chat ──
  const wsRef = useRef<WebSocket | null>(null);
  const [wsConnected, setWsConnected] = useState(false);
  const [wsError, setWsError] = useState('');
  const [typingUsers, setTypingUsers] = useState<any[]>([]);
  const [onlineMembers, setOnlineMembers] = useState<any[]>([]);
  const typingTimerRef = useRef<any>(null);
  const lastTypingSentRef = useRef(0);
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const _messagesEndRef = useRef<any>(null);

  const fallbackIntervalMs = getHybridPollingInterval({
    reconnectAttempt,
    thresholdAttempt: 3,
    slowIntervalMs: TICKET_POLL_MAX_INTERVAL_MS,
    fastIntervalMs: TICKET_POLL_MIN_INTERVAL_MS,
  });

  useHybridPolling({
    enabled: Boolean(selected?.submission_id) && !wsConnected,
    errorScope: 'admin/support-tickets/poll-fallback-hybrid',
    onTick: async () => {
      if (!selected?.submission_id) return;
      try {
        const res = await api.get(`/admin/manage/tickets/${selected.submission_id}`);
        setSelected((prev: any) => {
          if (!prev) return prev;
          const newReplies = res.data.reply_logs?.length || 0;
          const oldReplies = prev.reply_logs?.length || 0;
          if (newReplies !== oldReplies || res.data.status !== prev.status) return res.data;
          return prev;
        });
      } catch (error) {
        handleRecoverableError(error, {
          scope: 'admin/support-tickets/poll-fallback',
          fallbackMessage: 'Ticket refresh failed while reconnecting.',
          setMessage: setWsError,
        });
      }
    },
    runOnMount: WORKFLOW_POLLING_PRESET.runOnMount,
    slowIntervalMs: fallbackIntervalMs,
    fastIntervalMs: fallbackIntervalMs,
    wsEnabled: WORKFLOW_POLLING_PRESET.wsEnabled,
  });

  // ── WebSocket connection management (managed hook) ──
  const selectedTicketId = String(selected?.submission_id || '');

  const buildTicketWsUrl = useCallback(async () => {
    if (!selectedTicketId) return '';
    const ticketResp = await api.post('/auth/ws-ticket', { channel: 'ticket_chat' });
    const ticket = String(ticketResp?.data?.ticket || '').trim();
    if (!ticket) {
      throw new Error('Missing ticket chat websocket token');
    }

    const baseUrl = (api.defaults.baseURL || '').replace(/^http/, 'ws');
    return `${baseUrl}/ws/ticket-chat/${selectedTicketId}?ticket=${encodeURIComponent(ticket)}`;
  }, [selectedTicketId]);

  const { socketRef: managedSocketRef, lastError, reconnectAttempt } = useManagedWebSocket({
    enabled: Boolean(selectedTicketId),
    buildUrl: buildTicketWsUrl,
    errorScope: 'admin/support-tickets/ws',
    maxReconnectAttempts: 6,
    baseReconnectDelayMs: 1200,
    onOpen: (socket) => {
      setWsConnected(true);
      setWsError('');
      socket.send(JSON.stringify({ type: 'read' }));
    },
    onClose: () => {
      setWsConnected(false);
      setTypingUsers([]);
      setOnlineMembers([]);
    },
    onError: () => {
      setWsConnected(false);
      setWsError('Ticket chat disconnected. Reconnecting...');
    },
    onReconnectAttempt: (attempt) => {
      setWsConnected(false);
      setWsError(`Reconnecting ticket chat (${attempt})...`);
    },
    onMessage: (evt) => {
      try {
        const data = JSON.parse(evt.data);

        if (data.type === 'message') {
          setSelected((prev: any) => {
            if (!prev) return prev;
            const existing = prev.reply_logs || [];
            const isDupe = existing.some((r: any) => r.at === data.at && r.from === data.from);
            if (isDupe) return prev;
            return { ...prev, reply_logs: [...existing, data] };
          });
          setTypingUsers((prev) => prev.filter((u) => u.user_id !== data.from));
        } else if (data.type === 'typing') {
          if (data.is_typing) {
            setTypingUsers((prev) => {
              if (prev.some((u) => u.user_id === data.user_id)) return prev;
              return [...prev, { user_id: data.user_id, name: data.name, role: data.role }];
            });
          } else {
            setTypingUsers((prev) => prev.filter((u) => u.user_id !== data.user_id));
          }
        } else if (data.type === 'presence') {
          setOnlineMembers(data.members || []);
        }

        setWsError('');
      } catch (error) {
        handleRecoverableError(error, {
          scope: 'admin/support-tickets/ws-parse',
          fallbackMessage: 'A realtime ticket event could not be processed.',
          setMessage: setWsError,
        });
      }
    },
  });

  useEffect(() => {
    wsRef.current = managedSocketRef.current;
  }, [managedSocketRef, wsConnected]);

  useEffect(() => {
    if (!selectedTicketId) {
      setWsConnected(false);
      setTypingUsers([]);
      setOnlineMembers([]);
      setWsError('');
    }
  }, [selectedTicketId]);

  useEffect(() => {
    if (!lastError) return;
    setWsConnected(false);
    setWsError(lastError);
  }, [lastError]);

  // Send typing indicator (throttled)
  const sendTypingIndicator = useCallback((isTyping: boolean) => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;
    const now = Date.now();
    if (isTyping && now - lastTypingSentRef.current < 2000) return;
    lastTypingSentRef.current = now;
    wsRef.current.send(JSON.stringify({ type: 'typing', is_typing: isTyping }));
    if (isTyping) {
      if (typingTimerRef.current) clearTimeout(typingTimerRef.current);
      typingTimerRef.current = setTimeout(() => {
        if (wsRef.current?.readyState === WebSocket.OPEN) {
          wsRef.current.send(JSON.stringify({ type: 'typing', is_typing: false }));
        }
      }, 3000);
    }
  }, []);

  const loadTicket = async (id: string) => {
    try {
      const res = await api.get(`/admin/manage/tickets/${id}`);
      setSelected(res.data);
      setAiSuggestion('');
      setDetailTab('conversation');
    } catch (e) { console.error(e); }
  };

  const updateTicket = async (updates: any) => {
    if (!selected) return;
    const tid = selected.submission_id;
    setActionLoading(updates.status || updates.priority || 'update');
    try {
      await api.post(`/admin/manage/tickets/${tid}/update`, updates);
      await loadTicket(tid);
      await loadTickets();
    } catch (e: any) { Alert.alert(errorTitle, e?.response?.data?.detail || 'Update failed'); }
    setActionLoading('');
  };

  const sendReply = async () => {
    if (!selected || !replyText.trim()) return;
    setReplying(true);
    try {
      // Use WebSocket if connected, otherwise fall back to HTTP
      if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify({ type: 'message', message: replyText }));
        // Stop typing indicator
        wsRef.current.send(JSON.stringify({ type: 'typing', is_typing: false }));
        setReplyText('');
        setAiSuggestion('');
      } else {
        await api.post(`/admin/manage/tickets/${selected.submission_id}/reply`, { message: replyText });
        setReplyText('');
        setAiSuggestion('');
        await loadTicket(selected.submission_id);
      }
    } catch (e: any) { Alert.alert(errorTitle, e?.response?.data?.detail || 'Reply failed'); }
    setReplying(false);
  };

  const getAiSuggestion = async () => {
    if (!selected) return;
    setAiLoading(true);
    try {
      const res = await api.post(`/admin/manage/tickets/${selected.submission_id}/ai-suggest`, { tone: aiTone });
      setAiSuggestion(res.data.suggestion);
    } catch (e: any) { Alert.alert(errorTitle, e?.response?.data?.detail || 'AI suggestion failed'); }
    setAiLoading(false);
  };

  const addInternalNote = async () => {
    if (!selected || !noteText.trim()) return;
    setAddingNote(true);
    try {
      await api.post(`/admin/manage/tickets/${selected.submission_id}/internal-note`, { note: noteText });
      setNoteText('');
      await loadTicket(selected.submission_id);
    } catch (e: any) { Alert.alert(errorTitle, e?.response?.data?.detail || 'Failed to add note'); }
    setAddingNote(false);
  };

  const deleteNote = async (noteId: string) => {
    if (!selected) return;
    try {
      await api.delete(`/admin/manage/tickets/${selected.submission_id}/internal-note/${noteId}`);
      await loadTicket(selected.submission_id);
    // eslint-disable-next-line @typescript-eslint/no-unused-vars
    } catch (e: any) { Alert.alert(errorTitle, 'Failed to delete note'); }
  };

  const loadCannedResponses = async () => {
    try {
      const res = await api.get('/admin/manage/canned-responses');
      setCannedResponses(res.data.responses);
    } catch (error) {
      handleRecoverableError(error, {
        scope: 'admin/support-tickets/canned-responses/load',
        fallbackMessage: 'Unable to load canned responses.',
        setMessage: setWsError,
      });
    }
  };

  const applyCannedResponse = async (cr: any) => {
    setReplyText(cr.content);
    setShowCanned(false);
    try {
      await api.post(`/admin/manage/canned-responses/${cr.response_id}/use`);
    } catch (error) {
      handleRecoverableError(error, {
        scope: 'admin/support-tickets/canned-responses/use',
        fallbackMessage: 'Unable to track canned response usage.',
        setMessage: setWsError,
      });
    }
  };

  const createCannedResponse = async () => {
    if (!newCannedTitle.trim() || !newCannedContent.trim()) return;
    try {
      await api.post('/admin/manage/canned-responses', { title: newCannedTitle, content: newCannedContent });
      setNewCannedTitle('');
      setNewCannedContent('');
      await loadCannedResponses();
    } catch (error) {
      handleRecoverableError(error, {
        scope: 'admin/support-tickets/canned-responses/create',
        fallbackMessage: 'Failed to create canned response.',
        setMessage: setWsError,
      });
    }
  };

  const deleteCannedResponse = async (id: string) => {
    try {
      await api.delete(`/admin/manage/canned-responses/${id}`);
      await loadCannedResponses();
    } catch (error) {
      handleRecoverableError(error, {
        scope: 'admin/support-tickets/canned-responses/delete',
        fallbackMessage: 'Failed to delete canned response.',
        setMessage: setWsError,
      });
    }
  };

  const loadUserContext = async () => {
    if (!selected) return;
    try {
      const res = await api.get(`/admin/manage/tickets/${selected.submission_id}/user-context`);
      setUserContext(res.data);
      setShowUserCtx(true);
      setDetailTab('context');
    } catch (error) {
      handleRecoverableError(error, {
        scope: 'admin/support-tickets/user-context',
        fallbackMessage: 'Unable to load user context.',
        setMessage: setWsError,
      });
    }
  };

  const runProactiveNudgesNow = async () => {
    setNudgesRunning(true);
    try {
      await api.post('/admin/manage/proactive-nudges/run-now');
      await loadNudges();
      await loadTickets();
    } catch (e: any) {
      Alert.alert(errorTitle, e?.response?.data?.detail || 'Failed to run proactive nudges');
    }
    setNudgesRunning(false);
  };

  const acknowledgeNudge = async (nudgeId: string) => {
    setNudgeActionId(nudgeId);
    try {
      await api.post(`/admin/manage/proactive-nudges/${nudgeId}/ack`, {
        note: 'Acknowledged from support dashboard',
      });
      await loadNudges();
    } catch (e: any) {
      Alert.alert(errorTitle, e?.response?.data?.detail || 'Failed to acknowledge nudge');
    }
    setNudgeActionId('');
  };

  useEffect(() => { loadCannedResponses(); }, []);

  const attachments = selected?.attachments || [];

  const openAttachmentViewerAt = useCallback((index: number) => {
    setAttachmentStartIndex(Math.max(0, index));
    setShowAttachments(true);
  }, []);

  const downloadAttachment = useCallback((attachment: any) => {
    const url = _attDownloadUrl(attachment);
    if (!url) {
      Alert.alert(errorTitle, 'Attachment URL unavailable');
      return;
    }
    if (Platform.OS === 'web') {
      window.open(url, '_blank');
      return;
    }
    Alert.alert('Download available on web', 'Open this ticket in web admin to download attachments.');
  }, [errorTitle]);

  return (
    <View data-testid="support-tickets-panel" testID="support-tickets-panel">
      <AutoFixBanner domain="helpdesk" />
      <View style={{ marginBottom: 12 }}>
        <Text style={{ fontSize: 18, fontWeight: '800', color: C.text }}>{supportTitle === 'supportTickets.header.title' ? tx('supportTickets.header.titleFallback', 'Support Tickets') : supportTitle}</Text>
        <Text style={{ fontSize: 11, color: C.muted, marginTop: 3 }}>{tx('supportTickets.header.subtitle', 'Monitor ticket health, reply faster, and resolve escalations.')}</Text>
      </View>
      {/* Stats Bar */}
      {stats && (
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginBottom: 16 }}>
          {[
            { l: tx('supportTickets.stats.open', 'Open'), v: stats.open, c: C.yellow, icon: 'alert-circle' },
            { l: tx('supportTickets.stats.inProgress', 'In Progress'), v: stats.pending, c: C.cyan, icon: 'sync' },
            { l: tx('supportTickets.stats.escalated', 'Escalated'), v: stats.escalated, c: C.red, icon: 'arrow-up' },
            { l: tx('supportTickets.stats.riskHigh', 'High Risk'), v: stats.risk_high_or_critical || 0, c: C.orange, icon: 'flame' },
            { l: tx('supportTickets.stats.proactiveNudges', 'Open Nudges'), v: nudgeOpenCount || 0, c: C.blue, icon: 'notifications' },
            { l: tx('supportTickets.stats.resolved', 'Resolved'), v: stats.resolved, c: C.green, icon: 'checkmark-circle' },
            { l: tx('supportTickets.stats.total', 'Total'), v: stats.total, c: C.sec, icon: 'albums' },
          ].map(s => (
            <View key={s.l} style={{ flex: 1, minWidth: 90, backgroundColor: (globalThis as any).__alphaColor(s.c, '08'), borderRadius: 12, padding: 14, alignItems: 'center', borderWidth: 1, borderColor: (globalThis as any).__alphaColor(s.c, '18') }} data-testid={`ticket-stats-card-${String(s.l).toLowerCase().replace(/\s+/g, '-')}`} testID={`ticket-stats-card-${String(s.l).toLowerCase().replace(/\s+/g, '-')}`}>
              <Ionicons name={s.icon as any} size={16} color={s.c} style={{ marginBottom: 4 }} />
              <Text style={{ fontSize: 22, fontWeight: '800', color: s.c, letterSpacing: -0.5 }}>{s.v}</Text>
              <Text style={{ fontSize: 10, color: C.muted, fontWeight: '600', marginTop: 2 }}>{s.l}</Text>
            </View>
          ))}
        </View>
      )}

      {/* Status Filters + Refresh */}
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 16 }}>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ flex: 1 }}>
          <View style={{ flexDirection: 'row', gap: 6 }}>
            {['all', 'open', 'pending', 'in_progress', 'escalated', 'resolved', 'closed'].map(s => (
              <TouchableOpacity key={s} onPress={() => { setStatusFilter(s); setPage(1); }} style={{ paddingHorizontal: 12, paddingVertical: 7, borderRadius: 8, backgroundColor: statusFilter === s ? (globalThis as any).__alphaColor((STATUS_COLORS[s] || C.blue), '18') : C.card, borderWidth: 1, borderColor: statusFilter === s ? (globalThis as any).__alphaColor((STATUS_COLORS[s] || C.blue), '35') : C.border }} data-testid={`ticket-filter-${s}`} testID={`ticket-filter-${s}`}>
                <Text style={{ fontSize: 11, fontWeight: '700', color: statusFilter === s ? (STATUS_COLORS[s] || C.blue) : C.sec }}>{tx(`supportTickets.status.${s}`, s.replace(/_/g, ' '))}</Text>
              </TouchableOpacity>
            ))}
          </View>
        </ScrollView>
        <TouchableOpacity onPress={() => { loadTickets(); loadNudges(); if (selected) loadTicket(selected.submission_id); }} style={{ width: 36, height: 36, borderRadius: 8, backgroundColor: C.card, borderWidth: 1, borderColor: C.border, alignItems: 'center', justifyContent: 'center' }} data-testid="ticket-refresh-btn" testID="ticket-refresh-btn">
          <Ionicons name="refresh" size={16} color={C.blue} />
        </TouchableOpacity>
      </View>

      {/* Proactive Nudges */}
      <View
        style={{
          marginBottom: 14,
          backgroundColor: C.card,
          borderRadius: 12,
          borderWidth: 1,
          borderColor: C.border,
          padding: 10,
          gap: 8,
        }}
        data-testid="support-proactive-nudges-card"
        testID="support-proactive-nudges-card"
      >
        <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
            <Ionicons name="notifications" size={14} color={C.blue} />
            <Text style={{ fontSize: 12, fontWeight: '800', color: C.text }} data-testid="support-proactive-nudges-title" testID="support-proactive-nudges-title">
              {tx('supportTickets.nudges.title', 'Proactive Nudges')}
            </Text>
            <View style={{ backgroundColor: (globalThis as any).__alphaColor(C.blue, '18'), borderRadius: 999, paddingHorizontal: 8, paddingVertical: 2 }}>
              <Text style={{ fontSize: 10, fontWeight: '800', color: C.blue }} data-testid="support-proactive-nudges-open-count" testID="support-proactive-nudges-open-count">{nudgeOpenCount}</Text>
            </View>
          </View>
          <TouchableOpacity accessibilityLabel="Support proactive nudges run now button"
            onPress={runProactiveNudgesNow}
            style={{
              backgroundColor: C.bgSoft || C.card,
              borderRadius: 8,
              borderWidth: 1,
              borderColor: C.border,
              paddingHorizontal: 10,
              paddingVertical: 6,
            }}
            data-testid="support-proactive-nudges-run-now"
            testID="support-proactive-nudges-run-now"
          >
            <Text style={{ fontSize: 10, fontWeight: '700', color: C.blue }}>{nudgesRunning ? tx('supportTickets.nudges.running', 'Running…') : tx('supportTickets.nudges.runNow', 'Run now')}</Text>
          </TouchableOpacity>
        </View>

        {openNudges.length === 0 ? (
          <Text style={{ fontSize: 11, color: C.muted }} data-testid="support-proactive-nudges-empty" testID="support-proactive-nudges-empty">
            {tx('supportTickets.nudges.empty', 'No open nudges right now.')}
          </Text>
        ) : (
          <View style={{ gap: 6 }}>
            {openNudges.slice(0, 3).map((nudge: any) => (
              <View
                key={nudge.nudge_id}
                style={{
                  backgroundColor: C.bgSoft || C.card,
                  borderWidth: 1,
                  borderColor: C.border,
                  borderRadius: 9,
                  padding: 8,
                  gap: 5,
                }}
                data-testid={`support-proactive-nudge-row-${nudge.nudge_id}`}
                testID={`support-proactive-nudge-row-${nudge.nudge_id}`}
              >
                <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 6 }}>
                  <Text style={{ flex: 1, fontSize: 11, fontWeight: '800', color: C.text }} numberOfLines={1} data-testid={`support-proactive-nudge-title-${nudge.nudge_id}`} testID={`support-proactive-nudge-title-${nudge.nudge_id}`}>
                    {nudge.title || tx('supportTickets.nudges.defaultTitle', 'Nudge')}
                  </Text>
                  <RiskHeatBadge
                    riskHeat={{ level: nudge.risk_level || 'low', score: nudge.risk_score || 0 }}
                    compact
                    testId={`support-proactive-nudge-risk-${nudge.nudge_id}`}
                  />
                </View>
                <Text style={{ fontSize: 10, color: C.muted }} numberOfLines={2} data-testid={`support-proactive-nudge-message-${nudge.nudge_id}`} testID={`support-proactive-nudge-message-${nudge.nudge_id}`}>
                  {nudge.message || tx('supportTickets.nudges.defaultMessage', 'No nudge message')}
                </Text>
                <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
                  <Text style={{ fontSize: 10, color: C.sec }} data-testid={`support-proactive-nudge-ticket-${nudge.nudge_id}`} testID={`support-proactive-nudge-ticket-${nudge.nudge_id}`}>
                    {nudge.ticket_number || nudge.ticket_id}
                  </Text>
                  <TouchableOpacity accessibilityLabel="Acknowledge nudge in support tickets panel"
                    onPress={() => acknowledgeNudge(nudge.nudge_id)}
                    style={{
                      backgroundColor: (globalThis as any).__alphaColor(C.green, '18'),
                      borderRadius: 6,
                      borderWidth: 1,
                      borderColor: (globalThis as any).__alphaColor(C.green, '35'),
                      paddingHorizontal: 8,
                      paddingVertical: 4,
                    }}
                    data-testid={`support-proactive-nudge-ack-${nudge.nudge_id}`}
                    testID={`support-proactive-nudge-ack-${nudge.nudge_id}`}
                  >
                    <Text style={{ fontSize: 9, fontWeight: '700', color: C.green }}>
                      {nudgeActionId === nudge.nudge_id ? tx('supportTickets.nudges.saving', 'Saving…') : tx('supportTickets.nudges.acknowledge', 'Acknowledge')}
                    </Text>
                  </TouchableOpacity>
                </View>
              </View>
            ))}
          </View>
        )}
      </View>

      <View style={{ flexDirection: isWide ? 'row' : 'column', gap: 16 }}>
        {/* ═══ Ticket List ═══ */}
        <View style={{ width: isWide ? (useCompactSidebar ? 300 : 340) : '100%' }}>
          {loading ? <ActivityIndicator color={C.blue} style={{ padding: 30 }} /> : tickets.length === 0 ? (
            <View style={{ backgroundColor: C.card, borderRadius: 14, padding: 40, alignItems: 'center', borderWidth: 1, borderColor: C.border }}>
              <Ionicons name="chatbubbles-outline" size={40} color={C.border} />
              <Text style={{ color: C.muted, marginTop: 10, fontSize: 13 }}>{tx('supportTickets.states.noMatch', 'No tickets match this filter')}</Text>
            </View>
          ) : tickets.map(t => {
            const isActive = selected?.submission_id === t.submission_id;
            return (
              <TouchableOpacity key={t.submission_id} onPress={() => loadTicket(t.submission_id)} style={{ padding: 14, borderRadius: 12, marginBottom: 4, backgroundColor: isActive ? (globalThis as any).__alphaColor(C.blue, '10') : t.auto_escalated ? C.red + '06' : 'transparent', borderWidth: 1, borderColor: isActive ? (globalThis as any).__alphaColor(C.blue, '28') : t.auto_escalated ? C.red + '18' : 'transparent' }} data-testid={`ticket-row-${t.submission_id}`} testID={`ticket-row-${t.submission_id}`}>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 5 }}>
                  <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: STATUS_COLORS[t.status] || C.muted }} />
                  <Text style={{ flex: 1, fontSize: 13, fontWeight: '700', color: C.text }} numberOfLines={1}>{t.subject || t.type || tx('supportTickets.list.ticketFallback', 'Ticket')}</Text>
                  {t.auto_escalated && <Ionicons name="warning" size={12} color={C.red} />}
                  {t.attachments?.length > 0 && <Ionicons name="attach" size={12} color={C.muted} />}
                </View>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
                  {t.priority && (
                    <View style={{ backgroundColor: (globalThis as any).__alphaColor((PRIORITY_COLORS[t.priority] || C.muted), '18'), borderRadius: 4, paddingHorizontal: 6, paddingVertical: 2 }}>
                      <Text style={{ fontSize: 9, fontWeight: '800', color: PRIORITY_COLORS[t.priority] || C.muted, textTransform: 'uppercase' }}>{t.priority}</Text>
                    </View>
                  )}
                  <RiskHeatBadge riskHeat={t.risk_heat || { level: 'low', score: 0 }} compact testId={`ticket-risk-heat-${t.submission_id}`} />
                  <AIRoutingBadge ticket={t} />
                  <Text style={{ flex: 1, fontSize: 11, color: C.muted }} numberOfLines={1}>{t.user_name || t.user_email || t.user_id || tx('supportTickets.list.unknownUser', 'Unknown')}</Text>
                </View>
                {/* AI Tags */}
                {(t.ai_tags || t.ai_classification?.tags)?.length > 0 && (
                  <View style={{ flexDirection: 'row', gap: 3, marginTop: 4, flexWrap: 'wrap' }}>
                    {(t.ai_tags || t.ai_classification?.tags || []).slice(0, 3).map((tag: string, idx: number) => (
                      <View key={idx} style={{ backgroundColor: (globalThis as any).__alphaColor(C.accent, '12'), borderRadius: 3, paddingHorizontal: 4, paddingVertical: 1 }}>
                        <Text style={{ fontSize: 8, fontWeight: '600', color: C.accent }}>{tag}</Text>
                      </View>
                    ))}
                  </View>
                )}
                <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginTop: 4 }}>
                  {t.ticket_number && <Text style={{ fontSize: 10, fontWeight: '700', color: C.blue }}>{t.ticket_number}</Text>}
                  {t.assigned_agent_name && (
                    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 3 }}>
                      <Ionicons name="person-circle" size={10} color={C.cyan} />
                      <Text style={{ fontSize: 10, fontWeight: '600', color: C.cyan }}>{t.assigned_agent_name}</Text>
                    </View>
                  )}
                  {(t.escalation_level || 0) >= 1 && (
                    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 3, backgroundColor: (globalThis as any).__alphaColor((t.escalation_level >= 3 ? C.red : t.escalation_level >= 2 ? C.orange : C.yellow), '18'), borderRadius: 4, paddingHorizontal: 5, paddingVertical: 1 }}>
                      <Ionicons name="alert-circle" size={9} color={t.escalation_level >= 3 ? C.red : t.escalation_level >= 2 ? C.orange : C.yellow} />
                      <Text style={{ fontSize: 8, fontWeight: '800', color: t.escalation_level >= 3 ? C.red : t.escalation_level >= 2 ? C.orange : C.yellow }}>L{t.escalation_level}</Text>
                    </View>
                  )}
                  <Text style={{ fontSize: 10, color: C.muted }}>{t.created_at ? new Date(t.created_at).toLocaleDateString() : ''}</Text>
                </View>
              </TouchableOpacity>
            );
          })}
          {/* Pagination */}
          <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', marginTop: 10, paddingHorizontal: 8, paddingVertical: 6, backgroundColor: C.card, borderRadius: 10, gap: 8 }}>
            <TouchableOpacity disabled={page <= 1} onPress={() => setPage(p => p - 1)} style={{ flexDirection: 'row', alignItems: 'center', gap: 4, opacity: page <= 1 ? 0.3 : 1, paddingVertical: 4, paddingHorizontal: 8 }} data-testid="ticket-prev-btn" testID="ticket-prev-btn">
              <Ionicons name="chevron-back" size={14} color={C.blue} />
              <Text style={{ color: C.blue, fontSize: 12, fontWeight: '600' }}>{tx('supportTickets.pagination.prev', 'Prev')}</Text>
            </TouchableOpacity>
            <Text style={{ fontSize: 11, color: C.muted }}>{total} {total !== 1 ? tx('supportTickets.pagination.ticketsPlural', 'tickets') : tx('supportTickets.pagination.ticketSingular', 'ticket')}</Text>
            <TouchableOpacity disabled={page * 15 >= total} onPress={() => setPage(p => p + 1)} style={{ flexDirection: 'row', alignItems: 'center', gap: 4, opacity: page * 15 >= total ? 0.3 : 1, paddingVertical: 4, paddingHorizontal: 8 }} data-testid="ticket-next-btn" testID="ticket-next-btn">
              <Text style={{ color: C.blue, fontSize: 12, fontWeight: '600' }}>{tx('supportTickets.pagination.next', 'Next')}</Text>
              <Ionicons name="chevron-forward" size={14} color={C.blue} />
            </TouchableOpacity>
          </View>
        </View>

        {/* ═══ Ticket Detail ═══ */}
        <View style={{ flex: 1 }}>
          {!selected ? (
            <View style={{ backgroundColor: C.card, borderRadius: 16, padding: 50, alignItems: 'center', borderWidth: 1, borderColor: C.border, minHeight: 300 }}>
              <Ionicons name="chatbubble-ellipses-outline" size={48} color={C.border} />
              <Text style={{ color: C.muted, marginTop: 14, fontSize: 14, fontWeight: '600' }}>{tx('supportTickets.detail.selectTicketTitle', 'Select a ticket to manage')}</Text>
              <Text style={{ color: C.muted, marginTop: 4, fontSize: 12 }}>{tx('supportTickets.detail.selectTicketSubtitle', 'Click on any ticket from the list')}</Text>
            </View>
          ) : (
            <View>
              {/* ── Ticket Header Card ── */}
              <View style={{ backgroundColor: C.card, borderRadius: 14, padding: 18, marginBottom: 12, borderWidth: 1, borderColor: C.border }} data-testid="ticket-detail-card" testID="ticket-detail-card">
                <View style={{ flexDirection: 'row', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 10 }}>
                  <View style={{ flex: 1 }}>
                    <Text style={{ fontSize: 16, fontWeight: '800', color: C.text, marginBottom: 3 }}>{selected.subject || selected.type || tx('supportTickets.detail.ticketFallback', 'Ticket')}</Text>
                    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                      {selected.ticket_number && <Text style={{ fontSize: 11, fontWeight: '700', color: C.blue }}>{selected.ticket_number}</Text>}
                      <RiskHeatBadge riskHeat={selected.risk_heat || { level: 'low', score: 0 }} testId="ticket-detail-risk-heat" />
                      <Text style={{ fontSize: 11, color: C.muted }}>{selected.user_name || selected.user_email || ''}</Text>
                      <Text style={{ fontSize: 10, color: C.muted }}>{selected.created_at ? new Date(selected.created_at).toLocaleString() : ''}</Text>
                    </View>
                  </View>
                  {/* Quick Actions */}
                  <View style={{ flexDirection: 'row', gap: 6, flexWrap: 'wrap', justifyContent: 'flex-end' }}>
                    {attachments.length > 0 && (
                      <TouchableOpacity onPress={() => openAttachmentViewerAt(0)} style={{ flexDirection: 'row', alignItems: 'center', gap: 4, paddingHorizontal: 10, paddingVertical: 6, borderRadius: 8, backgroundColor: (globalThis as any).__alphaColor(C.purple, '15'), borderWidth: 1, borderColor: (globalThis as any).__alphaColor(C.purple, '30') }} data-testid="open-attachments-btn" testID="open-attachments-btn">
                        <Ionicons name="images" size={14} color={C.purpleText} />
                        <Text style={{ fontSize: 11, fontWeight: '700', color: C.purpleText }}>{attachments.length}</Text>
                      </TouchableOpacity>
                    )}
                    {attachments.length > 0 && (
                      <TouchableOpacity onPress={() => downloadAttachment(attachments[0])} style={{ width: 34, height: 34, borderRadius: 8, backgroundColor: (globalThis as any).__alphaColor(C.blue, '15'), borderWidth: 1, borderColor: (globalThis as any).__alphaColor(C.blue, '30'), alignItems: 'center', justifyContent: 'center' }} data-testid="download-first-attachment-btn" testID="download-first-attachment-btn">
                        <Ionicons name="download-outline" size={14} color={C.blue} />
                      </TouchableOpacity>
                    )}
                    <TouchableOpacity onPress={loadUserContext} style={{ width: 34, height: 34, borderRadius: 8, backgroundColor: (globalThis as any).__alphaColor(C.indigo, '15'), borderWidth: 1, borderColor: (globalThis as any).__alphaColor(C.indigo, '30'), alignItems: 'center', justifyContent: 'center' }} data-testid="user-context-btn" testID="user-context-btn">
                      <Ionicons name="person" size={14} color={C.indigoText} />
                    </TouchableOpacity>
                  </View>
                </View>

                {/* User's original message */}
                <View style={{ backgroundColor: C.bg, borderRadius: 10, padding: 14, marginBottom: 14, borderLeftWidth: 3, borderLeftColor: C.blue }}>
                  <Text style={{ fontSize: 13, color: C.sec, lineHeight: 20 }}>{selected.message || selected.content || selected.feedback || tx('supportTickets.detail.noMessageContent', 'No message content')}</Text>
                </View>

                {/* Inline Attachment Grid */}
                <AttachmentGrid
                  attachments={attachments}
                  onViewAll={() => openAttachmentViewerAt(0)}
                  onPreview={openAttachmentViewerAt}
                  onDownload={downloadAttachment}
                />

                {/* AI Classification & Routing */}
                {selected.ai_classification && (
                  <View style={{ backgroundColor: (globalThis as any).__alphaColor(C.purple, '06'), borderRadius: 12, padding: 14, marginBottom: 14, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(C.purple, '15') }} data-testid="ai-routing-section" testID="ai-routing-section">
                    <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
                      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                        <Ionicons name="sparkles" size={14} color={C.purpleText} />
                        <Text style={{ fontSize: 12, fontWeight: '800', color: C.purpleText }}>{tx('supportTickets.detail.aiRouting.title', 'AI Routing')}</Text>
                        <View style={{ backgroundColor: (globalThis as any).__alphaColor(C.purple, '18'), borderRadius: 4, paddingHorizontal: 5, paddingVertical: 1 }}>
                          <Text style={{ fontSize: 9, fontWeight: '700', color: C.purpleText }}>{Math.round((selected.ai_classification.confidence || 0) * 100)}% {tx('supportTickets.detail.aiRouting.conf', 'conf')}</Text>
                        </View>
                      </View>
                      {selected.ai_classification.classified_by === 'ai' && (
                        <Text style={{ fontSize: 9, color: C.muted }}>{tx('supportTickets.detail.aiRouting.modelName', 'GPT-4o')}</Text>
                      )}
                    </View>
                    {/* Topic + Sentiment row */}
                    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 8, flexWrap: 'wrap' }}>
                      {selected.ai_classification.topic && (
                        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4, backgroundColor: (globalThis as any).__alphaColor((TOPIC_COLORS[selected.ai_classification.topic] || C.muted), '15'), borderRadius: 8, paddingHorizontal: 8, paddingVertical: 4, borderWidth: 1, borderColor: (globalThis as any).__alphaColor((TOPIC_COLORS[selected.ai_classification.topic] || C.muted), '25') }}>
                          <Ionicons name={(TOPIC_ICONS[selected.ai_classification.topic] || 'help-circle') as any} size={12} color={TOPIC_COLORS[selected.ai_classification.topic] || C.muted} />
                          <Text style={{ fontSize: 11, fontWeight: '700', color: TOPIC_COLORS[selected.ai_classification.topic] || C.muted }}>{selected.ai_classification.topic.replace(/_/g, ' ')}</Text>
                        </View>
                      )}
                      <SentimentBadge sentiment={selected.ai_classification.sentiment} />
                      {selected.auto_escalated && (
                        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 3, backgroundColor: (globalThis as any).__alphaColor(C.red, '15'), borderRadius: 6, paddingHorizontal: 6, paddingVertical: 3, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(C.red, '25') }}>
                          <Ionicons name="warning" size={10} color={C.red} />
                          <Text style={{ fontSize: 9, fontWeight: '800', color: C.red }}>{tx('supportTickets.detail.aiRouting.autoEscalated', 'AUTO-ESCALATED')}</Text>
                        </View>
                      )}
                    </View>
                    {/* Tags */}
                    {(selected.ai_tags || selected.ai_classification.tags)?.length > 0 && (
                      <View style={{ flexDirection: 'row', gap: 4, marginBottom: 8, flexWrap: 'wrap' }}>
                        {(selected.ai_tags || selected.ai_classification.tags || []).map((tag: string, i: number) => (
                          <View key={i} style={{ backgroundColor: (globalThis as any).__alphaColor(C.accent, '12'), borderRadius: 6, paddingHorizontal: 7, paddingVertical: 3, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(C.accent, '20') }}>
                            <Text style={{ fontSize: 10, fontWeight: '600', color: C.accent }}>{tag}</Text>
                          </View>
                        ))}
                      </View>
                    )}
                    {/* Reasoning */}
                    {selected.ai_classification.reasoning && (
                      <Text style={{ fontSize: 11, color: C.sec, fontStyle: 'italic', lineHeight: 16 }}>{selected.ai_classification.reasoning}</Text>
                    )}
                    {/* Routing info */}
                    {selected.ai_routing && (
                      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginTop: 8, paddingTop: 8, borderTopWidth: 1, borderTopColor: (globalThis as any).__alphaColor(C.purple, '10') }}>
                        <Ionicons name="navigate" size={11} color={C.muted} />
                        <Text style={{ fontSize: 10, color: C.muted }}>{tx('supportTickets.detail.aiRouting.routedTo', 'Routed to:')} <Text style={{ fontWeight: '700', color: C.text }}>{selected.ai_routing.team || tx('supportTickets.detail.aiRouting.supportTeam', 'Support Team')}</Text></Text>
                        {selected.ai_routing.assigned_to && (
                          <Text style={{ fontSize: 10, color: C.muted }}>({selected.ai_routing.assigned_to})</Text>
                        )}
                      </View>
                    )}
                    {/* Escalation reason */}
                    {selected.escalation_reason && (
                      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 5, marginTop: 6, backgroundColor: (globalThis as any).__alphaColor(C.red, '08'), borderRadius: 6, padding: 8 }}>
                        <Ionicons name="alert-circle" size={12} color={C.red} />
                        <Text style={{ fontSize: 10, color: C.red, flex: 1 }}>{selected.escalation_reason}</Text>
                      </View>
                    )}
                  </View>
                )}

                {/* SLA Timer */}
                <SLATimer ticket={selected} colors={colors} />

                {/* Assignment Info */}
                {selected.assigned_agent_name && (
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginTop: 10, backgroundColor: (globalThis as any).__alphaColor(C.cyan, '08'), borderRadius: 10, padding: 12, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(C.cyan, '18') }} data-testid="ticket-assignment-info" testID="ticket-assignment-info">
                    <Ionicons name="person-circle" size={20} color={C.cyan} />
                    <View style={{ flex: 1 }}>
                      <Text style={{ fontSize: 12, fontWeight: '700', color: C.text }}>{tx('supportTickets.detail.assignment.assignedTo', 'Assigned to:')} {selected.assigned_agent_name}</Text>
                      <Text style={{ fontSize: 10, color: C.muted }}>{selected.assigned_to} {selected.assignment_type === 'auto' ? `(${tx('supportTickets.detail.assignment.auto', 'Auto-assigned')})` : `(${tx('supportTickets.detail.assignment.manual', 'Manual')})`}</Text>
                    </View>
                    {selected.assignment_type === 'auto' && (
                      <View style={{ backgroundColor: (globalThis as any).__alphaColor(C.cyan, '18'), borderRadius: 4, paddingHorizontal: 6, paddingVertical: 2 }}>
                        <Text style={{ fontSize: 9, fontWeight: '800', color: C.cyan }}>AI</Text>
                      </View>
                    )}
                  </View>
                )}

                {/* Status Controls */}
                <View style={{ marginTop: 12 }}>
                  <Text style={{ fontSize: 10, fontWeight: '700', color: C.muted, marginBottom: 6, textTransform: 'uppercase', letterSpacing: 0.5 }}>{tx('supportTickets.detail.statusLabel', 'Status')}</Text>
                  <ScrollView horizontal showsHorizontalScrollIndicator={false}>
                    <View style={{ flexDirection: 'row', gap: 5 }}>
                      {['open', 'pending', 'in_progress', 'escalated', 'resolved', 'closed', 'reopened'].map(s => (
                        <TouchableOpacity key={s} onPress={() => updateTicket({ status: s, note: `Status changed to ${s}`, action: 'status_change' })} disabled={actionLoading === s} style={{ flexDirection: 'row', alignItems: 'center', gap: 4, paddingHorizontal: 10, paddingVertical: 6, borderRadius: 8, backgroundColor: selected.status === s ? (globalThis as any).__alphaColor((STATUS_COLORS[s] || C.muted), '20') : C.bg, borderWidth: 1, borderColor: selected.status === s ? (globalThis as any).__alphaColor((STATUS_COLORS[s] || C.muted), '40') : C.border }} data-testid={`ticket-status-${s}`} testID={`ticket-status-${s}`}>
                          <Ionicons name={(STATUS_ICONS[s] || 'ellipse') as any} size={12} color={selected.status === s ? STATUS_COLORS[s] : C.sec} />
                          <Text style={{ fontSize: 10, fontWeight: '700', color: selected.status === s ? STATUS_COLORS[s] || C.muted : C.sec }}>{tx(`supportTickets.status.${s}`, s.replace(/_/g, ' '))}</Text>
                        </TouchableOpacity>
                      ))}
                    </View>
                  </ScrollView>
                </View>

                {/* Priority Controls */}
                <View style={{ marginTop: 10 }}>
                  <Text style={{ fontSize: 10, fontWeight: '700', color: C.muted, marginBottom: 6, textTransform: 'uppercase', letterSpacing: 0.5 }}>{tx('supportTickets.detail.priorityLabel', 'Priority')}</Text>
                  <View style={{ flexDirection: 'row', gap: 5 }}>
                    {['low', 'medium', 'high', 'urgent'].map(p => (
                      <TouchableOpacity key={p} onPress={() => updateTicket({ priority: p, note: `Priority set to ${p}`, action: 'priority_change' })} style={{ flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 4, paddingVertical: 7, borderRadius: 8, backgroundColor: selected.priority === p ? (globalThis as any).__alphaColor((PRIORITY_COLORS[p] || C.muted), '20') : C.bg, borderWidth: 1, borderColor: selected.priority === p ? (globalThis as any).__alphaColor((PRIORITY_COLORS[p] || C.muted), '40') : C.border }} data-testid={`ticket-priority-${p}`} testID={`ticket-priority-${p}`}>
                        <View style={{ width: 6, height: 6, borderRadius: 3, backgroundColor: PRIORITY_COLORS[p] || C.muted }} />
                        <Text style={{ fontSize: 10, fontWeight: '700', color: selected.priority === p ? PRIORITY_COLORS[p] : C.sec }}>{tx(`supportTickets.priority.${p}`, p)}</Text>
                      </TouchableOpacity>
                    ))}
                  </View>
                </View>
              </View>

              {/* ── Detail Tabs ── */}
              <View style={{ flexDirection: 'row', gap: 4, marginBottom: 12 }}>
                {([
                  { key: 'conversation', label: tx('supportTickets.tabs.conversation', 'Conversation'), icon: 'chatbubbles', count: selected.reply_logs?.length },
                  { key: 'notes', label: tx('supportTickets.tabs.notes', 'Internal Notes'), icon: 'lock-closed', count: selected.internal_notes?.length },
                  { key: 'history', label: tx('supportTickets.tabs.history', 'History'), icon: 'time', count: selected.history?.length },
                  { key: 'context', label: tx('supportTickets.tabs.context', 'User Info'), icon: 'person-circle' },
                ] as const).map(tab => (
                  <TouchableOpacity key={tab.key} onPress={() => { setDetailTab(tab.key); if (tab.key === 'context') loadUserContext(); }} style={{ flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 5, paddingVertical: 10, borderRadius: 10, backgroundColor: detailTab === tab.key ? (globalThis as any).__alphaColor(C.blue, '15') : C.card, borderWidth: 1, borderColor: detailTab === tab.key ? (globalThis as any).__alphaColor(C.blue, '30') : C.border }} data-testid={`detail-tab-${tab.key}`} testID={`detail-tab-${tab.key}`}>
                    <Ionicons name={tab.icon as any} size={14} color={detailTab === tab.key ? C.blue : C.muted} />
                    {isMed && <Text style={{ fontSize: 11, fontWeight: '700', color: detailTab === tab.key ? C.blue : C.muted }}>{tab.label}</Text>}
                    {tab.count ? <View style={{ backgroundColor: (globalThis as any).__alphaColor(C.blue, '25'), borderRadius: 8, paddingHorizontal: 5, paddingVertical: 1 }}><Text style={{ fontSize: 9, fontWeight: '800', color: C.blue }}>{tab.count}</Text></View> : null}
                  </TouchableOpacity>
                ))}
              </View>

              {/* ── Conversation Tab ── */}
              {detailTab === 'conversation' && (
                <View style={{ backgroundColor: C.card, borderRadius: 14, padding: 18, marginBottom: 12, borderWidth: 1, borderColor: C.border }} data-testid="ticket-conversation" testID="ticket-conversation">
                  <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14 }}>
                    <Text style={{ fontSize: 14, fontWeight: '800', color: C.text }}>{tx('supportTickets.conversation.title', 'Conversation')}</Text>
                    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                      {/* Online members */}
                      {onlineMembers.filter(m => m.role !== 'admin').length > 0 && (
                        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4, backgroundColor: (globalThis as any).__alphaColor(C.green, '10'), borderRadius: 6, paddingHorizontal: 8, paddingVertical: 3, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(C.green, '20') }} data-testid="user-online-badge" testID="user-online-badge">
                          <Ionicons name="person" size={10} color={C.green} />
                          <Text style={{ fontSize: 9, fontWeight: '700', color: C.green }}>{tx('supportTickets.conversation.userOnline', 'User Online')}</Text>
                        </View>
                      )}
                      {/* Connection indicator */}
                      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }} data-testid="ws-connection-status" testID="ws-connection-status">
                        <View style={{ width: 6, height: 6, borderRadius: 3, backgroundColor: wsConnected ? C.green : C.yellow }} />
                        <Text style={{ fontSize: 10, color: wsConnected ? C.green : C.yellow, fontWeight: '600' }}>{wsConnected ? tx('supportTickets.conversation.live', 'Live') : tx('supportTickets.conversation.polling', 'Polling')}</Text>
                      </View>
                    </View>
                  </View>

                  {!!wsError && (
                    <View data-testid="support-tickets-ws-error" testID="support-tickets-ws-error" style={{ backgroundColor: (globalThis as any).__alphaColor(C.red, '10'), borderWidth: 1, borderColor: (globalThis as any).__alphaColor(C.red, '28'), borderRadius: 10, padding: 10, marginBottom: 12 }}>
                      <Text style={{ color: C.red, fontSize: 11, fontWeight: '600' }}>{wsError}</Text>
                    </View>
                  )}

                  {/* Messages */}
                  {(selected.reply_logs || []).length === 0 && (
                    <View style={{ padding: 20, alignItems: 'center' }}>
                      <Text style={{ color: C.muted, fontSize: 12 }}>{tx('supportTickets.conversation.empty', 'No replies yet. Be the first to respond!')}</Text>
                    </View>
                  )}
                  {(selected.reply_logs || []).map((r: any, i: number) => {
                    const isAdmin = r.role === 'admin';
                    return (
                      <View key={i} style={{ marginBottom: 10, backgroundColor: isAdmin ? (globalThis as any).__alphaColor(C.blue, '08') : C.bg, borderRadius: 12, padding: 14, borderLeftWidth: 3, borderLeftColor: isAdmin ? C.blue : C.green }}>
                        <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
                          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                            <View style={{ width: 24, height: 24, borderRadius: 12, backgroundColor: isAdmin ? (globalThis as any).__alphaColor(C.blue, '20') : C.green + '20', alignItems: 'center', justifyContent: 'center' }}>
                              <Ionicons name={isAdmin ? 'shield' : 'person'} size={12} color={isAdmin ? C.blue : C.green} />
                            </View>
                            <Text style={{ fontSize: 12, fontWeight: '700', color: isAdmin ? C.blue : C.green }}>{r.from_name || r.from}</Text>
                            <View style={{ backgroundColor: isAdmin ? (globalThis as any).__alphaColor(C.blue, '15') : C.green + '15', borderRadius: 4, paddingHorizontal: 5, paddingVertical: 1 }}>
                              <Text style={{ fontSize: 9, fontWeight: '700', color: isAdmin ? C.blue : C.green }}>{isAdmin ? tx('supportTickets.conversation.roleAdmin', 'ADMIN') : tx('supportTickets.conversation.roleUser', 'USER')}</Text>
                            </View>
                          </View>
                          <Text style={{ fontSize: 10, color: C.muted }}>{r.at ? new Date(r.at).toLocaleString() : ''}</Text>
                          {r.via === 'realtime' && <Ionicons name="flash" size={10} color={C.cyan} />}
                        </View>
                        <Text style={{ fontSize: 13, color: C.text, lineHeight: 20 }}>{r.message}</Text>
                      </View>
                    );
                  })}

                  {/* ── AI Reply Suggestion ── */}
                  <View style={{ backgroundColor: (globalThis as any).__alphaColor(C.purple, '08'), borderRadius: 12, padding: 14, marginTop: 10, marginBottom: 10, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(C.purple, '20') }} data-testid="ai-suggestion-section" testID="ai-suggestion-section">
                    <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
                      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                        <Ionicons name="sparkles" size={14} color={C.purpleText} />
                        <Text style={{ fontSize: 12, fontWeight: '800', color: C.purpleText }}>{tx('supportTickets.conversation.aiSuggestionTitle', 'AI Reply Suggestion')}</Text>
                      </View>
                      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                        {/* Tone selector */}
                        {['professional', 'friendly', 'empathetic'].map(tone => (
                          <TouchableOpacity key={tone} onPress={() => setAiTone(tone)} style={{ paddingHorizontal: 8, paddingVertical: 3, borderRadius: 6, backgroundColor: aiTone === tone ? (globalThis as any).__alphaColor(C.purple, '20') : 'transparent', borderWidth: 1, borderColor: aiTone === tone ? (globalThis as any).__alphaColor(C.purple, '40') : C.border }} data-testid={`ai-tone-${tone}`} testID={`ai-tone-${tone}`}>
                            <Text style={{ fontSize: 9, fontWeight: '700', color: aiTone === tone ? C.purple : C.muted }}>{tx(`supportTickets.conversation.tone.${tone}`, tone)}</Text>
                          </TouchableOpacity>
                        ))}
                      </View>
                    </View>
                    {aiSuggestion ? (
                      <View>
                        <View style={{ backgroundColor: C.bg, borderRadius: 10, padding: 12, marginBottom: 10 }}>
                          <Text style={{ fontSize: 12, color: C.text, lineHeight: 19 }}>{aiSuggestion}</Text>
                        </View>
                        <View style={{ flexDirection: 'row', gap: 8 }}>
                          <TouchableOpacity onPress={() => { setReplyText(aiSuggestion); }} style={{ flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 4, paddingVertical: 8, borderRadius: 8, backgroundColor: (globalThis as any).__alphaColor(C.green, '15'), borderWidth: 1, borderColor: (globalThis as any).__alphaColor(C.green, '30') }} data-testid="use-ai-suggestion-btn" testID="use-ai-suggestion-btn">
                            <Ionicons name="checkmark" size={14} color={C.green} />
                            <Text style={{ fontSize: 11, fontWeight: '700', color: C.green }}>{tx('supportTickets.conversation.useThis', 'Use This')}</Text>
                          </TouchableOpacity>
                          <TouchableOpacity onPress={getAiSuggestion} style={{ flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 4, paddingVertical: 8, borderRadius: 8, backgroundColor: (globalThis as any).__alphaColor(C.purple, '15'), borderWidth: 1, borderColor: (globalThis as any).__alphaColor(C.purple, '30') }} data-testid="refresh-ai-suggestion-btn" testID="refresh-ai-suggestion-btn">
                            <Ionicons name="refresh" size={14} color={C.purpleText} />
                            <Text style={{ fontSize: 11, fontWeight: '700', color: C.purpleText }}>{tx('supportTickets.conversation.newSuggestion', 'New Suggestion')}</Text>
                          </TouchableOpacity>
                        </View>
                      </View>
                    ) : (
                      <TouchableOpacity onPress={getAiSuggestion} disabled={aiLoading} style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, paddingVertical: 10, borderRadius: 10, backgroundColor: (globalThis as any).__alphaColor(C.purple, '15') }} data-testid="generate-ai-suggestion-btn" testID="generate-ai-suggestion-btn">
                        {aiLoading ? <ActivityIndicator size="small" color={C.purpleText} /> : <Ionicons name="sparkles" size={16} color={C.purpleText} />}
                        <Text style={{ fontSize: 12, fontWeight: '700', color: C.purpleText }}>{aiLoading ? tx('supportTickets.conversation.generating', 'Generating...') : tx('supportTickets.conversation.generateSuggestion', 'Generate AI Suggestion')}</Text>
                      </TouchableOpacity>
                    )}
                  </View>

                  {/* ── Canned Responses ── */}
                  {showCanned && (
                    <View style={{ backgroundColor: C.bg, borderRadius: 12, padding: 14, marginBottom: 10, borderWidth: 1, borderColor: C.border }} data-testid="canned-responses-panel" testID="canned-responses-panel">
                      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
                        <Text style={{ fontSize: 12, fontWeight: '700', color: C.text }}>{tx('supportTickets.conversation.cannedResponses', 'Canned Responses')}</Text>
                        <TouchableOpacity onPress={() => setShowCanned(false)} data-testid="close-canned-btn" testID="close-canned-btn">
                          <Ionicons name="close" size={16} color={C.muted} />
                        </TouchableOpacity>
                      </View>
                      {cannedResponses.length === 0 ? (
                        <Text style={{ color: C.muted, fontSize: 11, textAlign: 'center', paddingVertical: 10 }}>{tx('supportTickets.conversation.cannedResponsesEmpty', 'No canned responses yet')}</Text>
                      ) : cannedResponses.map(cr => (
                        <View key={cr.response_id} style={{ flexDirection: 'row', alignItems: 'center', gap: 8, padding: 10, borderRadius: 8, marginBottom: 4, backgroundColor: C.card, borderWidth: 1, borderColor: C.border }}>
                          <TouchableOpacity onPress={() => applyCannedResponse(cr)} style={{ flex: 1 }} data-testid={`use-canned-${cr.response_id}`} testID={`use-canned-${cr.response_id}`}>
                            <Text style={{ fontSize: 12, fontWeight: '700', color: C.text }}>{cr.title}</Text>
                            <Text style={{ fontSize: 11, color: C.muted, marginTop: 2 }} numberOfLines={2}>{cr.content}</Text>
                          </TouchableOpacity>
                          <TouchableOpacity onPress={() => deleteCannedResponse(cr.response_id)} data-testid={`delete-canned-${cr.response_id}`} testID={`delete-canned-${cr.response_id}`}>
                            <Ionicons name="trash" size={14} color={C.red} />
                          </TouchableOpacity>
                        </View>
                      ))}
                      {/* Add new canned response */}
                      <View style={{ marginTop: 8, gap: 6 }}>
                        <TextInput value={newCannedTitle} onChangeText={setNewCannedTitle} placeholder={tx('supportTickets.conversation.cannedTitlePlaceholder', 'Title...')} placeholderTextColor={C.muted} style={{ backgroundColor: C.card, borderRadius: 8, padding: 10, color: C.text, fontSize: 12, borderWidth: 1, borderColor: C.border }} data-testid="new-canned-title" testID="new-canned-title" />
                        <TextInput value={newCannedContent} onChangeText={setNewCannedContent} placeholder={tx('supportTickets.conversation.cannedContentPlaceholder', 'Response content...')} placeholderTextColor={C.muted} multiline style={{ backgroundColor: C.card, borderRadius: 8, padding: 10, color: C.text, fontSize: 12, minHeight: 50, borderWidth: 1, borderColor: C.border }} data-testid="new-canned-content" testID="new-canned-content" />
                        <TouchableOpacity onPress={createCannedResponse} style={{ backgroundColor: C.blue, borderRadius: 8, padding: 8, alignItems: 'center' }} data-testid="save-canned-btn" testID="save-canned-btn">
                          <Text style={{ color: colors.primaryText, fontSize: 11, fontWeight: '700' }}>{tx('supportTickets.conversation.saveResponse', 'Save Response')}</Text>
                        </TouchableOpacity>
                      </View>
                    </View>
                  )}

                  {/* ── Reply Input ── */}
                  {/* Typing indicator */}
                  {typingUsers.length > 0 && (
                    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, paddingVertical: 6, paddingHorizontal: 10 }} data-testid="typing-indicator" testID="typing-indicator">
                      <View style={{ flexDirection: 'row', gap: 3 }}>
                        {[0, 1, 2].map(i => (
                          <View key={i} style={{ width: 5, height: 5, borderRadius: 3, backgroundColor: C.cyan, opacity: 0.6 }} />
                        ))}
                      </View>
                      <Text style={{ fontSize: 11, color: C.cyan, fontStyle: 'italic' }}>
                        {typingUsers.map(u => u.name).join(', ')} {typingUsers.length === 1 ? tx('supportTickets.conversation.typingIs', 'is') : tx('supportTickets.conversation.typingAre', 'are')} {tx('supportTickets.conversation.typingNow', 'typing...')}
                      </Text>
                    </View>
                  )}
                  <View style={{ marginTop: 6, gap: 8 }}>
                    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 4 }}>
                      <TouchableOpacity onPress={() => setShowCanned(!showCanned)} style={{ flexDirection: 'row', alignItems: 'center', gap: 4, paddingHorizontal: 10, paddingVertical: 5, borderRadius: 8, backgroundColor: (globalThis as any).__alphaColor(C.orange, '12'), borderWidth: 1, borderColor: (globalThis as any).__alphaColor(C.orange, '25') }} data-testid="toggle-canned-btn" testID="toggle-canned-btn">
                        <Ionicons name="flash" size={12} color={C.orangeText} />
                        <Text style={{ fontSize: 10, fontWeight: '700', color: C.orangeText }}>{tx('supportTickets.conversation.quickReplies', 'Quick Replies')}</Text>
                      </TouchableOpacity>
                      {wsConnected && (
                        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4, paddingHorizontal: 8, paddingVertical: 4, borderRadius: 6, backgroundColor: (globalThis as any).__alphaColor(C.green, '08'), borderWidth: 1, borderColor: (globalThis as any).__alphaColor(C.green, '15') }} data-testid="realtime-badge" testID="realtime-badge">
                          <Ionicons name="flash" size={10} color={C.green} />
                          <Text style={{ fontSize: 9, fontWeight: '700', color: C.green }}>{tx('supportTickets.conversation.realTime', 'Real-time')}</Text>
                        </View>
                      )}
                    </View>
                    <TextInput value={replyText} onChangeText={(t) => { setReplyText(t); if (t.trim()) sendTypingIndicator(true); else sendTypingIndicator(false); }} placeholder={tx('supportTickets.conversation.replyPlaceholder', 'Write a reply to the user...')} placeholderTextColor={C.muted} multiline style={{ backgroundColor: C.bg, borderRadius: 12, padding: 14, color: C.text, fontSize: 13, minHeight: 80, borderWidth: 1, borderColor: wsConnected ? (globalThis as any).__alphaColor(C.green, '25') : C.border, lineHeight: 20 }} data-testid="ticket-reply-input" testID="ticket-reply-input" />
                    <TouchableOpacity onPress={sendReply} disabled={replying || !replyText.trim()} style={{ backgroundColor: replying || !replyText.trim() ? C.border : C.blue, borderRadius: 10, padding: 13, alignItems: 'center', flexDirection: 'row', justifyContent: 'center', gap: 6 }} data-testid="ticket-reply-send-btn" testID="ticket-reply-send-btn">
                      {replying ? <ActivityIndicator size="small" color={colors.primaryText} /> : <><Ionicons name="send" size={15} color={colors.primaryText} /><Text style={{ color: colors.primaryText, fontWeight: '800', fontSize: 13 }}>{tx('supportTickets.conversation.sendReply', 'Send Reply')}</Text></>}
                    </TouchableOpacity>
                  </View>
                </View>
              )}

              {/* ── Internal Notes Tab ── */}
              {detailTab === 'notes' && (
                <View style={{ backgroundColor: C.card, borderRadius: 14, padding: 18, marginBottom: 12, borderWidth: 1, borderColor: C.border }} data-testid="ticket-internal-notes" testID="ticket-internal-notes">
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 14 }}>
                    <Ionicons name="lock-closed" size={14} color={C.yellow} />
                    <Text style={{ fontSize: 14, fontWeight: '800', color: C.text }}>{tx('supportTickets.notes.title', 'Internal Notes')}</Text>
                    <View style={{ backgroundColor: (globalThis as any).__alphaColor(C.yellow, '15'), borderRadius: 4, paddingHorizontal: 6, paddingVertical: 1 }}>
                      <Text style={{ fontSize: 9, fontWeight: '700', color: C.yellow }}>{tx('supportTickets.notes.adminOnly', 'ADMIN ONLY')}</Text>
                    </View>
                  </View>
                  {(selected.internal_notes || []).length === 0 && (
                    <View style={{ padding: 20, alignItems: 'center' }}>
                      <Ionicons name="document-text-outline" size={30} color={C.border} />
                      <Text style={{ color: C.muted, fontSize: 12, marginTop: 8 }}>{tx('supportTickets.notes.empty', 'No internal notes yet')}</Text>
                    </View>
                  )}
                  {(selected.internal_notes || []).map((n: any, i: number) => (
                    <View key={n.note_id || i} style={{ backgroundColor: C.bg, borderRadius: 10, padding: 12, marginBottom: 8, borderLeftWidth: 3, borderLeftColor: C.yellow }}>
                      <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
                        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                          <Ionicons name="person" size={12} color={C.yellow} />
                          <Text style={{ fontSize: 11, fontWeight: '700', color: C.yellow }}>{n.by_name || tx('supportTickets.notes.adminFallback', 'Admin')}</Text>
                        </View>
                        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                          <Text style={{ fontSize: 10, color: C.muted }}>{n.created_at ? new Date(n.created_at).toLocaleString() : ''}</Text>
                          <TouchableOpacity onPress={() => deleteNote(n.note_id)} data-testid={`delete-note-${n.note_id}`} testID={`delete-note-${n.note_id}`}>
                            <Ionicons name="trash-outline" size={14} color={C.red} />
                          </TouchableOpacity>
                        </View>
                      </View>
                      <Text style={{ fontSize: 12, color: C.text, lineHeight: 18 }}>{n.note}</Text>
                    </View>
                  ))}
                  <View style={{ marginTop: 10, gap: 8 }}>
                    <TextInput value={noteText} onChangeText={setNoteText} placeholder={tx('supportTickets.notes.placeholder', 'Add an internal note...')} placeholderTextColor={C.muted} multiline style={{ backgroundColor: C.bg, borderRadius: 10, padding: 12, color: C.text, fontSize: 13, minHeight: 60, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(C.yellow, '25') }} data-testid="internal-note-input" testID="internal-note-input" />
                    <TouchableOpacity onPress={addInternalNote} disabled={addingNote || !noteText.trim()} style={{ backgroundColor: addingNote || !noteText.trim() ? C.border : C.yellow, borderRadius: 10, padding: 12, alignItems: 'center', flexDirection: 'row', justifyContent: 'center', gap: 6 }} data-testid="add-internal-note-btn" testID="add-internal-note-btn">
                      {addingNote ? <ActivityIndicator size="small" color={C.text} /> : <><Ionicons name="lock-closed" size={14} color={C.text} /><Text style={{ color: C.text, fontWeight: '800', fontSize: 13 }}>{tx('supportTickets.notes.addNote', 'Add Note')}</Text></>}
                    </TouchableOpacity>
                  </View>
                </View>
              )}

              {/* ── History Tab ── */}
              {detailTab === 'history' && (
                <View style={{ backgroundColor: C.card, borderRadius: 14, padding: 18, marginBottom: 12, borderWidth: 1, borderColor: C.border }} data-testid="ticket-history" testID="ticket-history">
                  <Text style={{ fontSize: 14, fontWeight: '800', color: C.text, marginBottom: 14 }}>{tx('supportTickets.history.title', 'Activity Timeline')}</Text>
                  {(selected.history || []).length === 0 ? (
                    <View style={{ padding: 20, alignItems: 'center' }}>
                      <Ionicons name="time-outline" size={30} color={C.border} />
                      <Text style={{ color: C.muted, fontSize: 12, marginTop: 8 }}>{tx('supportTickets.history.empty', 'No history yet')}</Text>
                    </View>
                  ) : (selected.history || []).map((h: any, i: number) => (
                    <View key={i} style={{ flexDirection: 'row', gap: 12, marginBottom: 12 }}>
                      <View style={{ alignItems: 'center', width: 24 }}>
                        <View style={{ width: 10, height: 10, borderRadius: 5, backgroundColor: h.action?.includes('reply') ? C.blue : h.action?.includes('status') ? C.cyan : h.action?.includes('priority') ? C.yellow : C.muted, borderWidth: 2, borderColor: C.card }} />
                        {i < (selected.history?.length || 0) - 1 && <View style={{ width: 1, flex: 1, backgroundColor: C.border, marginTop: 2 }} />}
                      </View>
                      <View style={{ flex: 1, paddingBottom: 8 }}>
                        <Text style={{ fontSize: 12, fontWeight: '600', color: C.text }}>{h.action?.replace(/_/g, ' ')}</Text>
                        <Text style={{ fontSize: 11, color: C.muted, marginTop: 2 }}>{h.note}</Text>
                        <Text style={{ fontSize: 10, color: C.muted, marginTop: 3 }}>{h.by_name || tx('supportTickets.history.systemFallback', 'System')} - {h.at ? new Date(h.at).toLocaleString() : ''}</Text>
                      </View>
                    </View>
                  ))}
                </View>
              )}

              {/* ── User Context Tab ── */}
              {detailTab === 'context' && (
                <View style={{ backgroundColor: C.card, borderRadius: 14, padding: 18, marginBottom: 12, borderWidth: 1, borderColor: C.border }} data-testid="ticket-user-context" testID="ticket-user-context">
                  <Text style={{ fontSize: 14, fontWeight: '800', color: C.text, marginBottom: 14 }}>{tx('supportTickets.context.title', 'User Context')}</Text>
                  {!userContext?.user ? (
                    <View style={{ padding: 20, alignItems: 'center' }}>
                      <ActivityIndicator color={C.blue} />
                    </View>
                  ) : (
                    <View>
                      {/* User Info */}
                      <View style={{ backgroundColor: C.bg, borderRadius: 10, padding: 14, marginBottom: 12 }}>
                        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 10 }}>
                          <View style={{ width: 40, height: 40, borderRadius: 20, backgroundColor: (globalThis as any).__alphaColor(C.indigo, '20'), alignItems: 'center', justifyContent: 'center' }}>
                            <Ionicons name="person" size={20} color={C.indigoText} />
                          </View>
                          <View>
                            <Text style={{ fontSize: 14, fontWeight: '700', color: C.text }}>{userContext.user.name || tx('supportTickets.context.unknownUser', 'Unknown')}</Text>
                            <Text style={{ fontSize: 11, color: C.muted }}>{userContext.user.email}</Text>
                          </View>
                        </View>
                        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6 }}>
                          <View style={{ backgroundColor: (globalThis as any).__alphaColor(C.blue, '15'), borderRadius: 6, paddingHorizontal: 8, paddingVertical: 4 }}>
                            <Text style={{ fontSize: 10, fontWeight: '700', color: C.blue }}>{userContext.user.subscription_plan || tx('supportTickets.context.freePlan', 'free')}</Text>
                          </View>
                          {userContext.user.full_access && (
                            <View style={{ backgroundColor: (globalThis as any).__alphaColor(C.green, '15'), borderRadius: 6, paddingHorizontal: 8, paddingVertical: 4 }}>
                              <Text style={{ fontSize: 10, fontWeight: '700', color: C.green }}>{tx('supportTickets.context.fullAccess', 'Full Access')}</Text>
                            </View>
                          )}
                          {userContext.user.email_verified && (
                            <View style={{ backgroundColor: (globalThis as any).__alphaColor(C.cyan, '15'), borderRadius: 6, paddingHorizontal: 8, paddingVertical: 4 }}>
                              <Text style={{ fontSize: 10, fontWeight: '700', color: C.cyan }}>{tx('supportTickets.context.verified', 'Verified')}</Text>
                            </View>
                          )}
                        </View>
                      </View>
                      {/* Ticket Stats */}
                      <View style={{ flexDirection: 'row', gap: 8, marginBottom: 12 }}>
                        <View style={{ flex: 1, backgroundColor: C.bg, borderRadius: 10, padding: 12, alignItems: 'center' }}>
                          <Text style={{ fontSize: 18, fontWeight: '800', color: C.blue }}>{userContext.stats?.total_tickets || 0}</Text>
                          <Text style={{ fontSize: 10, color: C.muted }}>{tx('supportTickets.context.totalTickets', 'Total Tickets')}</Text>
                        </View>
                        <View style={{ flex: 1, backgroundColor: C.bg, borderRadius: 10, padding: 12, alignItems: 'center' }}>
                          <Text style={{ fontSize: 18, fontWeight: '800', color: C.green }}>{userContext.stats?.resolved || 0}</Text>
                          <Text style={{ fontSize: 10, color: C.muted }}>{tx('supportTickets.context.resolved', 'Resolved')}</Text>
                        </View>
                        <View style={{ flex: 1, backgroundColor: C.bg, borderRadius: 10, padding: 12, alignItems: 'center' }}>
                          <Text style={{ fontSize: 18, fontWeight: '800', color: C.yellow }}>{userContext.stats?.open || 0}</Text>
                          <Text style={{ fontSize: 10, color: C.muted }}>{tx('supportTickets.context.open', 'Open')}</Text>
                        </View>
                      </View>
                      {/* Previous Tickets */}
                      <Text style={{ fontSize: 12, fontWeight: '700', color: C.muted, marginBottom: 8 }}>{tx('supportTickets.context.previousTickets', 'Previous Tickets')}</Text>
                      {(userContext.previous_tickets || []).map((pt: any) => (
                        <TouchableOpacity key={pt.submission_id} aria-label="pt.ticket_number" onPress={() => loadTicket(pt.submission_id)} style={{ flexDirection: 'row', alignItems: 'center', gap: 8, padding: 10, borderRadius: 8, marginBottom: 4, backgroundColor: C.bg }}>
                          <View style={{ width: 6, height: 6, borderRadius: 3, backgroundColor: STATUS_COLORS[pt.status] || C.muted }} />
                          <Text style={{ flex: 1, fontSize: 11, fontWeight: '600', color: C.text }} numberOfLines={1}>{pt.subject || pt.type || tx('supportTickets.context.ticketFallback', 'Ticket')}</Text>
                          {pt.ticket_number && <Text style={{ fontSize: 9, fontWeight: '700', color: C.blue }}>{pt.ticket_number}</Text>}
                          <Text style={{ fontSize: 10, color: C.muted }}>{pt.created_at ? new Date(pt.created_at).toLocaleDateString() : ''}</Text>
                        </TouchableOpacity>
                      ))}
                    </View>
                  )}
                </View>
              )}

              {/* Attachment Viewer Modal */}
              <AttachmentViewer
                attachments={attachments}
                visible={showAttachments}
                onClose={() => setShowAttachments(false)}
                colors={colors}
                initialIndex={attachmentStartIndex}
              />
            </View>
          )}
        </View>
      </View>
    </View>
  );
}
