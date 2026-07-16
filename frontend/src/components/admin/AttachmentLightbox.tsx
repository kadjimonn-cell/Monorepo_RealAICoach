// dark backdrop (rgba(0,0,0,0.95)) on every theme, so rgba(255,255,255,*)
// overlays and fixed file-type accents (FILE_ACCENT) are the correct contrast
// primitives here. Any theme-reactive text colors are sourced through the
// colocated `useAdminTheme()` consumer.
import React, { useState, useEffect } from 'react';
import { View, Text, TouchableOpacity, Modal, ScrollView, useWindowDimensions, Platform } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useAdminTheme } from '../../hooks/useAdminTheme';
import { useTranslation } from '../../hooks/useTranslation';

interface Attachment {
  file_id?: string;
  url?: string;
  original_name?: string;
  filename?: string;
  mime_type?: string;
  content_type?: string;
  size?: number;
}

interface Props {
  attachments: Attachment[];
  visible: boolean;
  onClose: () => void;
  baseUrl?: string;
}

// Static file-type accent palette. These are NOT theme colors — the
// lightbox always renders on a fixed dark backdrop (rgba(0,0,0,0.95))
// and the accents communicate file-type (image/pdf/video/audio/other)
// consistently across light and dark admin themes. The component itself
// consumes `useAdminTheme()` for any text colors that do need to react.
const FILE_ACCENT = {
  cyan: 'var(--app-success)',
  blue: 'var(--app-primary)',
  purple: 'var(--app-primary)',
  red: 'var(--app-error)',
  orange: 'var(--app-warning)',
  muted: 'var(--app-text-muted)',
};

function attName(a: Attachment) { return a?.original_name || a?.filename || 'Untitled'; }
function attType(a: Attachment) { return a?.mime_type || a?.content_type || ''; }
function attUrl(a: Attachment, base?: string) {
  if (a?.file_id && base) return `${base}/tickets/attachment/${a.file_id}`;
  if (a?.url) return a.url;
  if (a?.file_id) return `/api/tickets/attachment/${a.file_id}`;
  return '';
}
function isImage(a: Attachment) { return attType(a).startsWith('image/') || /\.(jpg|jpeg|png|gif|webp|svg|bmp)$/i.test(attName(a)); }
function isPdf(a: Attachment) { return attType(a) === 'application/pdf' || /\.pdf$/i.test(attName(a)); }
function isVideo(a: Attachment) { return attType(a).startsWith('video/') || /\.(mp4|mov|avi|webm|mkv)$/i.test(attName(a)); }
function formatSize(b: number) { if (!b) return ''; if (b < 1024) return `${b} B`; if (b < 1048576) return `${(b / 1024).toFixed(1)} KB`; return `${(b / 1048576).toFixed(1)} MB`; }
function fileIcon(a: Attachment): string { if (isImage(a)) return 'image'; if (isPdf(a)) return 'document-text'; if (isVideo(a)) return 'videocam'; if (attType(a).startsWith('audio/')) return 'musical-note'; return 'document-attach'; }
function fileColor(a: Attachment): string { if (isImage(a)) return FILE_ACCENT.purple; if (isPdf(a)) return FILE_ACCENT.red; if (isVideo(a)) return FILE_ACCENT.blue; if (attType(a).startsWith('audio/')) return FILE_ACCENT.orange; return FILE_ACCENT.muted; }

export default function AttachmentLightbox({ attachments, visible, onClose, baseUrl }: Props) {
  const colors = useAdminTheme();
  const { t } = useTranslation();
  const tx = React.useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);
  const { width: sw, height: sh } = useWindowDimensions();
  const [activeIdx, setActiveIdx] = useState(0);
  const [zoomed, setZoomed] = useState(false);

  useEffect(() => {
    if (!visible || Platform.OS !== 'web') return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'ArrowRight' || e.key === 'ArrowDown') { setActiveIdx(i => Math.min(i + 1, (attachments?.length || 1) - 1)); setZoomed(false); }
      else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') { setActiveIdx(i => Math.max(i - 1, 0)); setZoomed(false); }
      else if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [visible, attachments?.length, onClose]);

  useEffect(() => { if (visible) { setActiveIdx(0); setZoomed(false); } }, [visible]);

  if (!attachments?.length) return null;
  const att = attachments[activeIdx];
  const imgUrl = attUrl(att, baseUrl);
  const isImg = isImage(att);
  const _isPdf = isPdf(att);
  const isVid = isVideo(att);

  return (
    <Modal visible={visible} transparent animationType="fade" onRequestClose={onClose}>
      <View style={{ flex: 1, backgroundColor: 'rgba(0,0,0,0.95)' }} data-testid="attachment-lightbox-modal" testID="attachment-lightbox-modal">
        {/* Top Bar */}
        <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', padding: 14, borderBottomWidth: 1, borderBottomColor: 'rgba(255,255,255,0.08)', zIndex: 10 }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, flex: 1 }}>
            <View style={{ width: 32, height: 32, borderRadius: 8, backgroundColor: (globalThis as any).__alphaColor(fileColor(att), '20'), alignItems: 'center', justifyContent: 'center' }}>
              <Ionicons name={fileIcon(att) as any} size={16} color={fileColor(att)} />
            </View>
            <View style={{ flex: 1 }}>
              <Text style={{ color: colors.primaryText, fontSize: 13, fontWeight: '700' }} numberOfLines={1}>{attName(att)}</Text>
              <View style={{ flexDirection: 'row', gap: 8, marginTop: 2 }}>
                <Text style={{ color: 'rgba(255,255,255,0.5)', fontSize: 10 }}>{attType(att) || 'Unknown'}</Text>
                {att?.size ? <Text style={{ color: 'rgba(255,255,255,0.4)', fontSize: 10 }}>{formatSize(att.size)}</Text> : null}
                {attachments.length > 1 && <Text style={{ color: FILE_ACCENT.cyan, fontSize: 10, fontWeight: '700' }}>{activeIdx + 1} of {attachments.length}</Text>}
              </View>
            </View>
          </View>
          <View style={{ flexDirection: 'row', gap: 8 }}>
            {isImg && (
              <TouchableOpacity onPress={() => setZoomed(!zoomed)} style={{ width: 34, height: 34, borderRadius: 8, backgroundColor: zoomed ? (globalThis as any).__alphaColor(FILE_ACCENT.cyan, '25') : 'rgba(255,255,255,0.08)', alignItems: 'center', justifyContent: 'center' }} data-testid="lightbox-zoom-btn" testID="lightbox-zoom-btn">
                <Ionicons name={zoomed ? 'contract' : 'expand'} size={16} color={zoomed ? FILE_ACCENT.cyan : 'var(--app-primary-text)'} />
              </TouchableOpacity>
            )}
            {imgUrl && Platform.OS === 'web' && (
              <TouchableOpacity onPress={() => window.open(imgUrl, '_blank')} style={{ width: 34, height: 34, borderRadius: 8, backgroundColor: 'rgba(255,255,255,0.08)', alignItems: 'center', justifyContent: 'center' }} data-testid="lightbox-download-btn" testID="lightbox-download-btn">
                <Ionicons name="download-outline" size={16} color="var(--app-primary-text)" />
              </TouchableOpacity>
            )}
            <TouchableOpacity onPress={onClose} style={{ width: 34, height: 34, borderRadius: 8, backgroundColor: 'rgba(255,255,255,0.12)', alignItems: 'center', justifyContent: 'center' }} data-testid="lightbox-close-btn" testID="lightbox-close-btn">
              <Ionicons name="close" size={18} color="var(--app-primary-text)" />
            </TouchableOpacity>
          </View>
        </View>

        {/* Main Content */}
        <View style={{ flex: 1, flexDirection: 'row' }}>
          {attachments.length > 1 && activeIdx > 0 && (
            <TouchableOpacity onPress={() => { setActiveIdx(i => i - 1); setZoomed(false); }} style={{ position: 'absolute', left: 8, top: '45%', zIndex: 10, width: 40, height: 40, borderRadius: 20, backgroundColor: 'rgba(0,0,0,0.6)', alignItems: 'center', justifyContent: 'center' }} data-testid="lightbox-prev-btn" testID="lightbox-prev-btn">
              <Ionicons name="chevron-back" size={22} color="var(--app-primary-text)" />
            </TouchableOpacity>
          )}
          {attachments.length > 1 && activeIdx < attachments.length - 1 && (
            <TouchableOpacity onPress={() => { setActiveIdx(i => i + 1); setZoomed(false); }} style={{ position: 'absolute', right: 8, top: '45%', zIndex: 10, width: 40, height: 40, borderRadius: 20, backgroundColor: 'rgba(0,0,0,0.6)', alignItems: 'center', justifyContent: 'center' }} data-testid="lightbox-next-btn" testID="lightbox-next-btn">
              <Ionicons name="chevron-forward" size={22} color="var(--app-primary-text)" />
            </TouchableOpacity>
          )}

          <ScrollView style={{ flex: 1 }} contentContainerStyle={{ alignItems: 'center', justifyContent: 'center', minHeight: '100%', padding: 20 }}>
            {isImg && imgUrl ? (
              Platform.OS === 'web' ? (
                <img src={imgUrl} alt={attName(att)} style={{ maxWidth: zoomed ? '100%' : Math.min(sw - 80, 900), maxHeight: zoomed ? 'none' : sh - 200, objectFit: 'contain', borderRadius: 6, cursor: 'pointer' }} onClick={() => setZoomed(!zoomed)} />
              ) : (
                <Text style={{ color: FILE_ACCENT.muted }}>{tx('admin.attachmentLightbox.previewUnavailable', 'Image preview not available')}</Text>
              )
            ) : isVid && imgUrl && Platform.OS === 'web' ? (
              <video src={imgUrl} controls style={{ maxWidth: Math.min(sw - 80, 900), maxHeight: sh - 200, borderRadius: 6 }} />
            ) : _isPdf && Platform.OS === 'web' ? (
              <iframe src={imgUrl} style={{ width: Math.min(sw - 80, 900), height: sh - 200, border: 'none', borderRadius: 6 }} title={attName(att)} />
            ) : (
              <View style={{ alignItems: 'center', padding: 40 }}>
                <View style={{ width: 80, height: 80, borderRadius: 20, backgroundColor: (globalThis as any).__alphaColor(fileColor(att), '15'), alignItems: 'center', justifyContent: 'center', marginBottom: 16 }}>
                  <Ionicons name={fileIcon(att) as any} size={40} color={fileColor(att)} />
                </View>
                <Text style={{ color: colors.primaryText, fontSize: 16, fontWeight: '700', textAlign: 'center' }}>{attName(att)}</Text>
                <Text style={{ color: 'rgba(255,255,255,0.5)', fontSize: 12, marginTop: 4 }}>{attType(att)}</Text>
                {att?.size ? <Text style={{ color: 'rgba(255,255,255,0.4)', fontSize: 11, marginTop: 2 }}>{formatSize(att.size)}</Text> : null}
                {imgUrl && Platform.OS === 'web' && (
                  <TouchableOpacity aria-label="Download File" onPress={() => window.open(imgUrl, '_blank')} style={{ marginTop: 20, backgroundColor: FILE_ACCENT.blue, paddingHorizontal: 24, paddingVertical: 10, borderRadius: 10 }}>
                    <Text style={{ color: colors.primaryText, fontWeight: '700', fontSize: 13 }}>{tx('admin.attachmentLightbox.actions.downloadFile', 'Download File')}</Text>
                  </TouchableOpacity>
                )}
              </View>
            )}
          </ScrollView>

          {/* Side thumbnail strip */}
          {attachments.length > 1 && sw > 600 && (
            <ScrollView style={{ width: 80, backgroundColor: 'rgba(0,0,0,0.4)', borderLeftWidth: 1, borderLeftColor: 'rgba(255,255,255,0.06)' }} contentContainerStyle={{ padding: 8, gap: 6 }}>
              {attachments.map((a: any, i: number) => {
                const thumbUrl = isImage(a) ? attUrl(a, baseUrl) : null;
                const active = i === activeIdx;
                return (
                  <TouchableOpacity key={i} onPress={() => { setActiveIdx(i); setZoomed(false); }} style={{ width: 64, height: 64, borderRadius: 10, overflow: 'hidden', borderWidth: 2, borderColor: active ? FILE_ACCENT.cyan : 'rgba(255,255,255,0.08)', backgroundColor: active ? (globalThis as any).__alphaColor(FILE_ACCENT.cyan, '10') : 'rgba(255,255,255,0.04)' }} data-testid={`lightbox-thumb-${i}`} testID={`lightbox-thumb-${i}`}>
                    {thumbUrl && Platform.OS === 'web' ? (
                      <img src={thumbUrl} style={{ width: '100%', height: '100%', objectFit: 'cover' }} alt={attName(a).slice(0, 8)} aria-label={attName(a).slice(0, 8)} />
                    ) : (
                      <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center' }}>
                        <Ionicons name={fileIcon(a) as any} size={22} color={active ? FILE_ACCENT.cyan : FILE_ACCENT.muted} />
                        <Text style={{ fontSize: 7, color: active ? FILE_ACCENT.cyan : FILE_ACCENT.muted, marginTop: 2, textAlign: 'center' }} numberOfLines={1}>{attName(a).slice(0, 8)}</Text>
                      </View>
                    )}
                  </TouchableOpacity>
                );
              })}
            </ScrollView>
          )}
        </View>

        {/* Bottom counter */}
        {attachments.length > 1 && (
          <View style={{ flexDirection: 'row', justifyContent: 'center', padding: 10, borderTopWidth: 1, borderTopColor: 'rgba(255,255,255,0.06)' }}>
            {attachments.map((_, i) => (
              <TouchableOpacity key={i} onPress={() => { setActiveIdx(i); setZoomed(false); }} data-testid={`lightbox-dot-${i}`} testID={`lightbox-dot-${i}`}>
                <View style={{ width: i === activeIdx ? 16 : 6, height: 6, borderRadius: 3, backgroundColor: i === activeIdx ? FILE_ACCENT.cyan : 'rgba(255,255,255,0.2)', marginHorizontal: 3 }} />
              </TouchableOpacity>
            ))}
          </View>
        )}
      </View>
    </Modal>
  );
}
