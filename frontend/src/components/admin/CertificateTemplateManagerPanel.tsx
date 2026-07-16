import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { ActivityIndicator, Image, PanResponder, ScrollView, Text, TextInput, TouchableOpacity, View, useWindowDimensions } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import api from '../../services/api';
import { useAdminTheme } from '../../hooks/useAdminTheme';
import { useTranslation } from '../../hooks/useTranslation';

const tx = (_key: string, fallback: string) => fallback;

const FIELD_GROUPS = [
  {
    id: 'stamp',
    title: 'Official stamp',
    fields: [
      { key: 'stamp_offset_x_mm', label: 'Horizontal offset', step: '0.5' },
      { key: 'stamp_y_mm', label: 'Vertical position', step: '0.5' },
      { key: 'stamp_size_mm', label: 'Stamp size', step: '0.5' },
    ],
  },
  {
    id: 'signature',
    title: 'Signature block',
    fields: [
      { key: 'signature_line_width_mm', label: 'Line width', step: '0.5' },
      { key: 'signature_right_margin_mm', label: 'Right margin', step: '0.5' },
      { key: 'signature_y_mm', label: 'Line vertical position', step: '0.5' },
      { key: 'signature_image_offset_x_mm', label: 'Image X offset', step: '0.5' },
      { key: 'signature_image_offset_y_mm', label: 'Image Y offset', step: '0.5' },
      { key: 'signature_image_width_mm', label: 'Image width', step: '0.5' },
      { key: 'signature_image_height_mm', label: 'Image height', step: '0.5' },
    ],
  },
  {
    id: 'logo',
    title: 'Footer logo',
    fields: [
      { key: 'footer_logo_x_mm', label: 'Logo X position', step: '0.5' },
      { key: 'footer_logo_y_mm', label: 'Logo Y position', step: '0.5' },
      { key: 'footer_logo_w_mm', label: 'Logo width', step: '0.5' },
      { key: 'footer_logo_h_mm', label: 'Logo height', step: '0.5' },
    ],
  },
];

const MM_STAGE_WIDTH = 210;
const MM_STAGE_HEIGHT = 297;
const LOGO_VISIBLE_RATIO = 0.5009765625;
const SIGNATURE_VISIBLE_RATIO = 0.44360902255639095;
const LOGO_ASPECT_RATIO = 1;
const SIGNATURE_ASPECT_RATIO = 1064 / 450;
const SNAP_THRESHOLD_MM = 2;
const RULER_STEP_MM = 10;
const DEFAULT_TYPOGRAPHY_PRESETS = [
  { id: 'classic', label: 'Classic', subtitle: 'Traditional signer lines' },
  { id: 'executive', label: 'Executive', subtitle: 'Balanced bold hierarchy' },
  { id: 'premium', label: 'Premium', subtitle: 'High-emphasis signature block' },
];

const LAYER_META = {
  stamp: { title: 'Official Stamp', subtitle: 'Balance against footer midpoint', icon: 'ellipse-outline', tone: 'var(--app-primary)' },
  signature: { title: 'CEO Signature', subtitle: 'Underline, image box, and margin', icon: 'create-outline', tone: 'var(--app-primary)' },
  logo: { title: 'Footer Logo', subtitle: 'Platform brand mark alignment', icon: 'diamond-outline', tone: 'var(--app-primary)' },
} as const;

type EditableElement = 'stamp' | 'signature' | 'logo';

type TemplateSettings = Record<string, number>;

const clamp = (value: number, minimum: number, maximum: number) => Math.max(minimum, Math.min(maximum, value));

const fitWithinBox = (aspectRatio: number, maxWidth: number, maxHeight: number) => {
  const boxRatio = maxWidth / Math.max(maxHeight, 0.001);
  if (aspectRatio > boxRatio) {
    return { width: maxWidth, height: maxWidth / aspectRatio };
  }
  return { width: maxHeight * aspectRatio, height: maxHeight };
};

const toNumberSettings = (source: Record<string, string>) => {
  const values = Object.fromEntries(Object.entries(source).map(([key, value]) => [key, Number(value)])) as TemplateSettings;
  return {
    stamp_offset_x_mm: clamp(values.stamp_offset_x_mm || -9.43, -40, 40),
    stamp_y_mm: clamp(values.stamp_y_mm || 17, 8, 40),
    stamp_size_mm: clamp(values.stamp_size_mm || 40, 18, 70),
    footer_logo_x_mm: clamp(values.footer_logo_x_mm || 24.5, 8, 60),
    footer_logo_y_mm: clamp(values.footer_logo_y_mm || 24, 12, 40),
    footer_logo_w_mm: clamp(values.footer_logo_w_mm || 44, 20, 70),
    footer_logo_h_mm: clamp(values.footer_logo_h_mm || 24, 12, 42),
    signature_line_width_mm: clamp(values.signature_line_width_mm || 72, 40, 100),
    signature_right_margin_mm: clamp(values.signature_right_margin_mm || 28, 8, 50),
    signature_y_mm: clamp(values.signature_y_mm || 31, 16, 44),
    signature_image_offset_x_mm: clamp(values.signature_image_offset_x_mm || 0, -8, 16),
    signature_image_offset_y_mm: clamp(values.signature_image_offset_y_mm || -0.5, -4, 18),
    signature_image_width_mm: clamp(values.signature_image_width_mm || 80, 30, 90),
    signature_image_height_mm: clamp(values.signature_image_height_mm || 34, 12, 42),
  };
};

const toStringSettings = (source: TemplateSettings) => (
  Object.fromEntries(Object.entries(source).map(([key, value]) => [key, String(Number(value.toFixed(2)))])) as Record<string, string>
);

const getPageCenterX = () => MM_STAGE_WIDTH / 2;

const getFooterLogoVisibleCenterX = (settings: TemplateSettings) => {
  const renderSize = fitWithinBox(LOGO_ASPECT_RATIO, settings.footer_logo_w_mm, settings.footer_logo_h_mm);
  return settings.footer_logo_x_mm + ((settings.footer_logo_w_mm - renderSize.width) / 2) + (renderSize.width * LOGO_VISIBLE_RATIO);
};

const getSignatureLineX = (settings: TemplateSettings) => MM_STAGE_WIDTH - settings.signature_line_width_mm - settings.signature_right_margin_mm;

const getSignatureVisibleCenterX = (settings: TemplateSettings) => {
  const imageBoxX = getSignatureLineX(settings) + settings.signature_image_offset_x_mm;
  const renderSize = fitWithinBox(SIGNATURE_ASPECT_RATIO, settings.signature_image_width_mm, settings.signature_image_height_mm);
  return imageBoxX + ((settings.signature_image_width_mm - renderSize.width) / 2) + (renderSize.width * SIGNATURE_VISIBLE_RATIO);
};

const getStampMidpointX = (settings: TemplateSettings) => (getFooterLogoVisibleCenterX(settings) + getSignatureVisibleCenterX(settings)) / 2;

const applyElementMove = (base: TemplateSettings, element: EditableElement, dxMm: number, dyMm: number) => {
  const next = { ...base };
  let snapNote = '';
  if (element === 'stamp') {
    const midpointX = getStampMidpointX(base);
    const currentCenterX = midpointX + base.stamp_offset_x_mm;
    let desiredCenterX = currentCenterX + dxMm;
    const pageCenter = getPageCenterX();
    if (Math.abs(desiredCenterX - midpointX) <= SNAP_THRESHOLD_MM) {
      desiredCenterX = midpointX;
      snapNote = 'Snapped to footer midpoint';
    } else if (Math.abs(desiredCenterX - pageCenter) <= SNAP_THRESHOLD_MM) {
      desiredCenterX = pageCenter;
      snapNote = 'Snapped to page center';
    }
    next.stamp_offset_x_mm = clamp(desiredCenterX - midpointX, -40, 40);
    next.stamp_y_mm = clamp(base.stamp_y_mm + dyMm, 8, 40);
  }
  if (element === 'logo') {
    const currentX = base.footer_logo_x_mm;
    let nextX = currentX + dxMm;
    const desiredCenterX = nextX + (base.footer_logo_w_mm / 2);
    if (Math.abs(desiredCenterX - getPageCenterX()) <= SNAP_THRESHOLD_MM) {
      nextX = getPageCenterX() - (base.footer_logo_w_mm / 2);
      snapNote = 'Snapped to page center';
    }
    next.footer_logo_x_mm = clamp(nextX, 8, 60);
    next.footer_logo_y_mm = clamp(base.footer_logo_y_mm + dyMm, 12, 40);
  }
  if (element === 'signature') {
    const currentLineX = getSignatureLineX(base);
    let nextLineX = currentLineX + dxMm;
    const desiredCenterX = nextLineX + (base.signature_line_width_mm / 2);
    if (Math.abs(desiredCenterX - getPageCenterX()) <= SNAP_THRESHOLD_MM) {
      nextLineX = getPageCenterX() - (base.signature_line_width_mm / 2);
      snapNote = 'Snapped to page center';
    }
    next.signature_right_margin_mm = clamp(MM_STAGE_WIDTH - base.signature_line_width_mm - nextLineX, 8, 50);
    next.signature_y_mm = clamp(base.signature_y_mm + dyMm, 16, 44);
  }
  return { next, snapNote };
};

const applyElementResize = (base: TemplateSettings, element: EditableElement, deltaWidthMm: number, deltaHeightMm: number) => {
  const next = { ...base };
  let note = '';

  if (element === 'stamp') {
    const delta = (deltaWidthMm + deltaHeightMm) / 2;
    next.stamp_size_mm = clamp(base.stamp_size_mm + delta, 18, 70);
    note = `Resized stamp to ${next.stamp_size_mm.toFixed(1)}mm`;
  }

  if (element === 'logo') {
    next.footer_logo_w_mm = clamp(base.footer_logo_w_mm + deltaWidthMm, 20, 70);
    next.footer_logo_h_mm = clamp(base.footer_logo_h_mm + deltaHeightMm, 12, 42);
    note = `Resized logo to ${next.footer_logo_w_mm.toFixed(1)} × ${next.footer_logo_h_mm.toFixed(1)}mm`;
  }

  if (element === 'signature') {
    next.signature_line_width_mm = clamp(base.signature_line_width_mm + deltaWidthMm, 40, 100);
    next.signature_image_width_mm = clamp(base.signature_image_width_mm + deltaWidthMm, 30, 90);
    next.signature_image_height_mm = clamp(base.signature_image_height_mm + deltaHeightMm, 12, 42);
    note = `Resized signature image to ${next.signature_image_width_mm.toFixed(1)} × ${next.signature_image_height_mm.toFixed(1)}mm`;
  }

  return { next, note };
};

const toAbsoluteUrl = (path: string) => {
  const raw = String(path || '').trim();
  if (!raw) return '';
  if (raw.startsWith('http://') || raw.startsWith('https://')) return raw;
  if (typeof window !== 'undefined') return `${window.location.origin}${raw.startsWith('/') ? raw : `/${raw}`}`;
  return raw;
};

export default function CertificateTemplateManagerPanel({ colors: _colors }: { colors: any }) {
  const { t } = useTranslation();
  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };

  const colors = useAdminTheme();
  const getElementFrame = (settings: TemplateSettings, element: EditableElement) => {
    if (element === 'stamp') {
      const centerX = getStampMidpointX(settings) + settings.stamp_offset_x_mm;
      return {
        x: centerX - (settings.stamp_size_mm / 2),
        y: MM_STAGE_HEIGHT - settings.stamp_y_mm - settings.stamp_size_mm,
        width: settings.stamp_size_mm,
        height: settings.stamp_size_mm,
        label: 'Official Stamp',
        color: colors.warningText,
      };
    }
    if (element === 'logo') {
      return {
        x: settings.footer_logo_x_mm,
        y: MM_STAGE_HEIGHT - settings.footer_logo_y_mm - settings.footer_logo_h_mm,
        width: settings.footer_logo_w_mm,
        height: settings.footer_logo_h_mm,
        label: 'Footer Logo',
        color: colors.accent,
      };
    }
    const lineX = getSignatureLineX(settings);
    const imageX = lineX + settings.signature_image_offset_x_mm;
    const x = Math.min(lineX, imageX);
    const width = Math.max(lineX + settings.signature_line_width_mm, imageX + settings.signature_image_width_mm) - x;
    const top = MM_STAGE_HEIGHT - (settings.signature_y_mm + settings.signature_image_offset_y_mm + settings.signature_image_height_mm);
    return {
      x,
      y: top,
      width,
      height: settings.signature_image_offset_y_mm + settings.signature_image_height_mm + 6,
      label: 'Signature Block',
      color: colors.primary,
    };
  };
  const { width } = useWindowDimensions();
  const C = {
    bg: colors.bg,
    card: colors.card,
    cardMuted: colors.surfaceHover,
    border: colors.border,
    borderSoft: colors.borderSoft || colors.border,
    text: colors.text,
    muted: colors.textMuted,
    textSoft: colors.textSec,
    blue: colors.primary,
    cyan: colors.accent,
    rose: colors.error,
  };

  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [settings, setSettings] = useState<Record<string, string>>({});
  const [certificates, setCertificates] = useState<any[]>([]);
  const [previewId, setPreviewId] = useState('');
  const [previewBust, setPreviewBust] = useState(() => Date.now());
  const [selectedElement, setSelectedElement] = useState<EditableElement>('stamp');
  const [dragHint, setDragHint] = useState('Drag an overlay box, then save the template.');
  const [stageSize, setStageSize] = useState({ width: 0, height: 0 });
  const [zoom, setZoom] = useState(1);
  const [guidesVisible, setGuidesVisible] = useState(true);
  const [typographyPreset, setTypographyPreset] = useState('executive');
  const [typographyPresets, setTypographyPresets] = useState(DEFAULT_TYPOGRAPHY_PRESETS);
  const dragStartRef = useRef<TemplateSettings | null>(null);
  const resizeStartRef = useRef<TemplateSettings | null>(null);

  const load = useCallback(async () => {
    try {
      setError('');
      const [templateRes, certificatesRes] = await Promise.all([
        api.get('/ai-learn/admin/certificate-template'),
        api.get('/ai-learn/admin/certificates', { params: { limit: 12 } }),
      ]);
      const nextSettings = templateRes.data?.settings || {};
      const nextTypographyPreset = String(templateRes.data?.typography_preset || 'executive');
      const nextPresets = Array.isArray(templateRes.data?.typography_presets)
        ? templateRes.data.typography_presets
          .map((row: any) => ({
            id: String(row?.id || '').trim(),
            label: String(row?.label || row?.id || '').trim(),
            subtitle: String(row?.subtitle || '').trim(),
          }))
          .filter((row: any) => row.id)
        : [];
      const nextCertificates = certificatesRes.data?.certificates || [];
      setSettings(Object.fromEntries(Object.entries(nextSettings).map(([key, value]) => [key, String(value)])));
      setTypographyPreset(nextTypographyPreset);
      if (nextPresets.length) setTypographyPresets(nextPresets);
      setCertificates(nextCertificates);
      setPreviewId((current) => current || nextCertificates[0]?.verification_id || '');
      setPreviewBust(Date.now());
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Unable to load certificate template controls.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  const previewUrl = useMemo(() => {
    if (!previewId) return '';
    return toAbsoluteUrl(`/api/ai-learn/certificates/verify/${encodeURIComponent(previewId)}/png/file?variant=web&template_preview=${previewBust}`);
  }, [previewBust, previewId]);

  const updateField = (key: string, value: string) => {
    setSettings((prev) => ({ ...prev, [key]: value }));
  };

  const numericSettings = useMemo(() => toNumberSettings(settings), [settings]);

  const nudgeSelected = (dxMm: number, dyMm: number) => {
    const result = applyElementMove(numericSettings, selectedElement, dxMm, dyMm);
    setSettings(toStringSettings(result.next));
    setDragHint(result.snapNote || `Adjusted ${selectedElement} by ${Math.abs(dxMm) + Math.abs(dyMm) > 0 ? '0.5' : '0'}mm`);
  };

  const handleDragMove = useCallback((element: EditableElement, dxPx: number, dyPx: number) => {
    if (!stageSize.width || !stageSize.height || !dragStartRef.current) return;
    const dxMm = (dxPx / stageSize.width) * MM_STAGE_WIDTH;
    const dyMm = -(dyPx / stageSize.height) * MM_STAGE_HEIGHT;
    const result = applyElementMove(dragStartRef.current, element, dxMm, dyMm);
    setSettings(toStringSettings(result.next));
    setDragHint(result.snapNote || `Dragging ${element}`);
  }, [stageSize.height, stageSize.width]);

  const handleResizeMove = useCallback((element: EditableElement, dxPx: number, dyPx: number) => {
    if (!stageSize.width || !stageSize.height || !resizeStartRef.current) return;
    const deltaWidthMm = (dxPx / stageSize.width) * MM_STAGE_WIDTH;
    const deltaHeightMm = (dyPx / stageSize.height) * MM_STAGE_HEIGHT;
    const result = applyElementResize(resizeStartRef.current, element, deltaWidthMm, deltaHeightMm);
    setSettings(toStringSettings(result.next));
    setDragHint(result.note || `Resizing ${element}`);
  }, [stageSize.height, stageSize.width]);

  const stampPanResponder = useMemo(() => PanResponder.create({
    onStartShouldSetPanResponder: () => true,
    onMoveShouldSetPanResponder: () => true,
    onPanResponderGrant: () => {
      setSelectedElement('stamp');
      dragStartRef.current = numericSettings;
    },
    onPanResponderMove: (_, gesture) => handleDragMove('stamp', gesture.dx, gesture.dy),
  }), [handleDragMove, numericSettings]);

  const signaturePanResponder = useMemo(() => PanResponder.create({
    onStartShouldSetPanResponder: () => true,
    onMoveShouldSetPanResponder: () => true,
    onPanResponderGrant: () => {
      setSelectedElement('signature');
      dragStartRef.current = numericSettings;
    },
    onPanResponderMove: (_, gesture) => handleDragMove('signature', gesture.dx, gesture.dy),
  }), [handleDragMove, numericSettings]);

  const logoPanResponder = useMemo(() => PanResponder.create({
    onStartShouldSetPanResponder: () => true,
    onMoveShouldSetPanResponder: () => true,
    onPanResponderGrant: () => {
      setSelectedElement('logo');
      dragStartRef.current = numericSettings;
    },
    onPanResponderMove: (_, gesture) => handleDragMove('logo', gesture.dx, gesture.dy),
  }), [handleDragMove, numericSettings]);

  const stampResizePanResponder = useMemo(() => PanResponder.create({
    onStartShouldSetPanResponder: () => true,
    onMoveShouldSetPanResponder: () => true,
    onPanResponderGrant: () => {
      setSelectedElement('stamp');
      resizeStartRef.current = numericSettings;
    },
    onPanResponderMove: (_, gesture) => handleResizeMove('stamp', gesture.dx, gesture.dy),
  }), [handleResizeMove, numericSettings]);

  const signatureResizePanResponder = useMemo(() => PanResponder.create({
    onStartShouldSetPanResponder: () => true,
    onMoveShouldSetPanResponder: () => true,
    onPanResponderGrant: () => {
      setSelectedElement('signature');
      resizeStartRef.current = numericSettings;
    },
    onPanResponderMove: (_, gesture) => handleResizeMove('signature', gesture.dx, gesture.dy),
  }), [handleResizeMove, numericSettings]);

  const logoResizePanResponder = useMemo(() => PanResponder.create({
    onStartShouldSetPanResponder: () => true,
    onMoveShouldSetPanResponder: () => true,
    onPanResponderGrant: () => {
      setSelectedElement('logo');
      resizeStartRef.current = numericSettings;
    },
    onPanResponderMove: (_, gesture) => handleResizeMove('logo', gesture.dx, gesture.dy),
  }), [handleResizeMove, numericSettings]);

  const elementFrames = useMemo(() => ({
    stamp: getElementFrame(numericSettings, 'stamp'),
    signature: getElementFrame(numericSettings, 'signature'),
    logo: getElementFrame(numericSettings, 'logo'),
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }), [numericSettings]);

  const midpointGuideX = useMemo(() => (getStampMidpointX(numericSettings) / MM_STAGE_WIDTH) * stageSize.width, [numericSettings, stageSize.width]);
  const pageCenterGuideX = useMemo(() => (getPageCenterX() / MM_STAGE_WIDTH) * stageSize.width, [stageSize.width]);
  const rulerTicks = useMemo(() => {
    const ticks: number[] = [];
    for (let value = 0; value <= MM_STAGE_WIDTH; value += RULER_STEP_MM) ticks.push(value);
    return ticks;
  }, []);
  const rulerTicksVertical = useMemo(() => {
    const ticks: number[] = [];
    for (let value = 0; value <= MM_STAGE_HEIGHT; value += RULER_STEP_MM) ticks.push(value);
    return ticks;
  }, []);
  const selectedFrame = elementFrames[selectedElement];
  const selectedRulerReadout = useMemo(() => {
    const scaleX = stageSize.width / MM_STAGE_WIDTH;
    const scaleY = stageSize.height / MM_STAGE_HEIGHT;
    return {
      xMm: selectedFrame.x,
      yMm: selectedFrame.y,
      wMm: selectedFrame.width,
      hMm: selectedFrame.height,
      xPx: selectedFrame.x * scaleX,
      yPx: selectedFrame.y * scaleY,
      wPx: selectedFrame.width * scaleX,
      hPx: selectedFrame.height * scaleY,
    };
  }, [selectedFrame, stageSize.height, stageSize.width]);
  const selectedGroup = FIELD_GROUPS.find((group) => group.id === selectedElement) || FIELD_GROUPS[0];
  const selectedMeta = LAYER_META[selectedElement];
  const workspaceStacked = width < 1340;
  const canvasBaseWidth = Math.min(workspaceStacked ? width - 72 : 760, 760);
  const canvasWidth = Math.max(280, Math.round(canvasBaseWidth * zoom));
  const zoomLabel = `${Math.round(zoom * 100)}%`;
  const otherGroups = FIELD_GROUPS.filter((group) => group.id !== selectedElement);

  const setZoomLevel = (value: number) => setZoom(clamp(Number(value.toFixed(2)), 0.7, 1.8));

  const saveTemplate = async () => {
    try {
      setSaving(true);
      setError('');
      const payload = Object.fromEntries(Object.entries(settings).map(([key, value]) => [key, Number(value)]));
      await api.put('/ai-learn/admin/certificate-template', {
        settings: payload,
        typography_preset: typographyPreset,
      });
      setPreviewBust(Date.now());
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Unable to save certificate template.');
    } finally {
      setSaving(false);
    }
  };

  const resetTemplate = async () => {
    try {
      setSaving(true);
      setError('');
      const res = await api.post('/ai-learn/admin/certificate-template/reset');
      const nextSettings = res.data?.settings || {};
      const nextTypographyPreset = String(res.data?.typography_preset || 'executive');
      setSettings(Object.fromEntries(Object.entries(nextSettings).map(([key, value]) => [key, String(value)])));
      setTypographyPreset(nextTypographyPreset);
      setPreviewBust(Date.now());
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Unable to reset certificate template.');
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <View style={{ paddingVertical: 64, alignItems: 'center' }} data-testid="admin-certificate-template-loading" testID="admin-certificate-template-loading">
        <ActivityIndicator size="large" color={C.blue} />
        <Text style={{ color: C.muted, fontSize: 12, marginTop: 10 }}>{tx('admin.certificateTemplateManagerPanel.auto.text.001', 'Loading certificate template manager...')}</Text>
      </View>
    );
  }

  return (
    <ScrollView contentContainerStyle={{ padding: 18, gap: 16, backgroundColor: C.bg }} data-testid="admin-certificate-template-panel" testID="admin-certificate-template-panel">
      <View style={{ backgroundColor: C.card, borderWidth: 1, borderColor: C.borderSoft, borderRadius: 20, padding: 18 }} data-testid="admin-certificate-template-topbar" testID="admin-certificate-template-topbar">
        <View style={{ flexDirection: workspaceStacked ? 'column' : 'row', justifyContent: 'space-between', gap: 16 }}>
          <View style={{ flex: 1 }}>
            <Text style={{ color: C.cyan, fontSize: 11, fontWeight: '800', letterSpacing: 1.4 }} data-testid="admin-certificate-template-overline" testID="admin-certificate-template-overline">{tx('admin.certificateTemplateManagerPanel.auto.text.002', 'CONTROL ROOM · CERTIFICATE TEMPLATE PREVIEW')}</Text>
            <Text style={{ color: C.text, fontSize: 28, fontWeight: '900', marginTop: 8 }} data-testid="admin-certificate-template-title" testID="admin-certificate-template-title">{tx('admin.certificateTemplateManagerPanel.auto.text.003', 'Redesigned live preview workspace')}</Text>
            <Text style={{ color: C.muted, fontSize: 12, marginTop: 8, lineHeight: 19 }} data-testid="admin-certificate-template-subtitle" testID="admin-certificate-template-subtitle">{tx('admin.certificateTemplateManagerPanel.auto.text.004', 'Drag layers on the certificate canvas, use guides and zoom for precision, then save the platform-wide template without touching certificate logic.')}</Text>
          </View>
          <View style={{ minWidth: workspaceStacked ? undefined : 360, gap: 10 }}>
            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }} data-testid="admin-certificate-template-actions-row" testID="admin-certificate-template-actions-row">
              <TouchableOpacity onPress={saveTemplate} style={{ backgroundColor: C.blue, borderRadius: 999, paddingHorizontal: 14, paddingVertical: 10, flexDirection: 'row', alignItems: 'center', gap: 6 }} data-testid="admin-certificate-template-save-button" testID="admin-certificate-template-save-button">
                <Ionicons name="save-outline" size={14} color="var(--app-primary-text)" />
                <Text style={{ color: colors.primaryText, fontSize: 11, fontWeight: '900' }}>{saving ? 'Saving…' : 'Save Template'}</Text>
              </TouchableOpacity>
              <TouchableOpacity onPress={resetTemplate} style={{ backgroundColor: C.cardMuted, borderRadius: 999, borderWidth: 1, borderColor: C.borderSoft, paddingHorizontal: 14, paddingVertical: 10, flexDirection: 'row', alignItems: 'center', gap: 6 }} data-testid="admin-certificate-template-reset-button" testID="admin-certificate-template-reset-button">
                <Ionicons name="refresh-outline" size={14} color={C.text} />
                <Text style={{ color: C.text, fontSize: 11, fontWeight: '800' }}>{tx('admin.certificateTemplateManagerPanel.auto.text.005', 'Reset')}</Text>
              </TouchableOpacity>
              <TouchableOpacity onPress={() => setPreviewBust(Date.now())} style={{ backgroundColor: C.cardMuted, borderRadius: 999, borderWidth: 1, borderColor: C.borderSoft, paddingHorizontal: 14, paddingVertical: 10, flexDirection: 'row', alignItems: 'center', gap: 6 }} data-testid="admin-certificate-template-refresh-preview-button" testID="admin-certificate-template-refresh-preview-button">
                <Ionicons name="sparkles-outline" size={14} color={C.text} />
                <Text style={{ color: C.text, fontSize: 11, fontWeight: '800' }}>{tx('admin.certificateTemplateManagerPanel.auto.text.006', 'Refresh Preview')}</Text>
              </TouchableOpacity>
            </View>

            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }} data-testid="admin-certificate-template-kpis-row" testID="admin-certificate-template-kpis-row">
              {[
                { label: 'Selected layer', value: selectedMeta.title },
                { label: 'Zoom', value: zoomLabel },
                { label: 'Preview cert', value: previewId ? previewId.slice(-8) : 'None' },
              ].map((item) => (
                <View key={item.label} style={{ minWidth: 104, flex: 1, backgroundColor: C.cardMuted, borderRadius: 14, borderWidth: 1, borderColor: C.borderSoft, padding: 10 }} data-testid={`admin-certificate-template-kpi-${item.label.replace(/[^a-z0-9]+/gi, '-').toLowerCase()}`} testID={`admin-certificate-template-kpi-${item.label.replace(/[^a-z0-9]+/gi, '-').toLowerCase()}`}>
                  <Text style={{ color: C.muted, fontSize: 10, fontWeight: '700', textTransform: 'uppercase', letterSpacing: 0.8 }}>{item.label}</Text>
                  <Text style={{ color: C.text, fontSize: 13, fontWeight: '900', marginTop: 4 }}>{item.value}</Text>
                </View>
              ))}
            </View>
          </View>
        </View>

        <Text style={{ color: C.muted, fontSize: 10, marginTop: 12 }} data-testid="admin-certificate-template-drag-hint" testID="admin-certificate-template-drag-hint">{dragHint}</Text>
        {error ? (
          <View style={{ marginTop: 12, backgroundColor: (globalThis as any).__alphaColor(C.error, '15'), borderWidth: 1, borderColor: (globalThis as any).__alphaColor(C.error, '35'), borderRadius: 12, padding: 12 }} data-testid="admin-certificate-template-error" testID="admin-certificate-template-error">
            <Text style={{ color: C.error, fontSize: 11, fontWeight: '700' }}>{error}</Text>
          </View>
        ) : null}
      </View>

      <View style={{ flexDirection: workspaceStacked ? 'column' : 'row', gap: 14, alignItems: 'flex-start' }} data-testid="admin-certificate-template-workspace" testID="admin-certificate-template-workspace">
        <View style={{ width: workspaceStacked ? '100%' : 272, backgroundColor: C.card, borderWidth: 1, borderColor: C.borderSoft, borderRadius: 18, padding: 14, gap: 12 }} data-testid="admin-certificate-template-left-sidebar" testID="admin-certificate-template-left-sidebar">
          <View>
            <Text style={{ color: C.text, fontSize: 15, fontWeight: '900' }} data-testid="admin-certificate-template-layer-title" testID="admin-certificate-template-layer-title">{tx('admin.certificateTemplateManagerPanel.auto.text.007', 'Layers')}</Text>
            <Text style={{ color: C.muted, fontSize: 10, marginTop: 4 }}>{tx('admin.certificateTemplateManagerPanel.auto.text.008', 'Pick a layer to edit. Hover and drag behavior stays mapped to the current template math.')}</Text>
          </View>

          {(['stamp', 'signature', 'logo'] as EditableElement[]).map((element) => {
            const active = selectedElement === element;
            const meta = LAYER_META[element];
            const frame = elementFrames[element];
            return (
              <TouchableOpacity accessibilityLabel={tx('admin.certificateTemplateManagerPanel.auto.accessibility.001', 'Select certificate layer')}
                key={element}
                onPress={() => setSelectedElement(element)}
                style={{
                  borderRadius: 16,
                  borderWidth: 1,
                  borderColor: active ? meta.tone : C.borderSoft,
                  backgroundColor: active ? `${meta.tone}16` : C.cardMuted,
                  padding: 12,
                  gap: 8,
                }}
                data-testid={`admin-certificate-template-select-${element}`} testID={`admin-certificate-template-select-${element}`}
              >
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
                  <View style={{ width: 32, height: 32, borderRadius: 10, backgroundColor: `${meta.tone}24`, alignItems: 'center', justifyContent: 'center' }}>
                    <Ionicons name={meta.icon as any} size={16} color={meta.tone} />
                  </View>
                  <View style={{ flex: 1 }}>
                    <Text style={{ color: C.text, fontSize: 12, fontWeight: '800' }}>{meta.title}</Text>
                    <Text style={{ color: C.muted, fontSize: 10, marginTop: 2 }}>{meta.subtitle}</Text>
                  </View>
                  <Ionicons name={active ? 'radio-button-on' : 'radio-button-off'} size={16} color={active ? meta.tone : C.muted} />
                </View>
                <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6 }}>
                  {[`X ${frame.x.toFixed(1)}mm`, `Y ${frame.y.toFixed(1)}mm`, `W ${frame.width.toFixed(1)}mm`].map((metric) => (
                    <View key={metric} style={{ borderRadius: 999, backgroundColor: C.card, borderWidth: 1, borderColor: C.borderSoft, paddingHorizontal: 8, paddingVertical: 4 }}>
                      <Text style={{ color: C.textSoft, fontSize: 10, fontWeight: '700' }}>{metric}</Text>
                    </View>
                  ))}
                </View>
              </TouchableOpacity>
            );
          })}

          <View style={{ borderTopWidth: 1, borderTopColor: C.borderSoft, paddingTop: 12, gap: 10 }} data-testid="admin-certificate-template-preview-picker-section" testID="admin-certificate-template-preview-picker-section">
            <Text style={{ color: C.text, fontSize: 13, fontWeight: '900' }}>{tx('admin.certificateTemplateManagerPanel.auto.text.009', 'Preview certificate')}</Text>
            <Text style={{ color: C.muted, fontSize: 10 }}>{tx('admin.certificateTemplateManagerPanel.auto.text.010', 'Switch the live sample that drives the PNG preview.')}</Text>
            <ScrollView style={{ maxHeight: 220 }} contentContainerStyle={{ gap: 8 }} data-testid="admin-certificate-template-preview-certificate-options" testID="admin-certificate-template-preview-certificate-options">
              {certificates.map((certificate, index) => {
                const selected = previewId === certificate.verification_id;
                return (
                  <TouchableOpacity
                    key={certificate.verification_id || index}
                    onPress={() => setPreviewId(certificate.verification_id)}
                    style={{ borderRadius: 14, borderWidth: 1, borderColor: selected ? C.blue : C.borderSoft, backgroundColor: selected ? `${C.blue}16` : C.cardMuted, padding: 10, gap: 4 }}
                    data-testid={`admin-certificate-template-preview-option-${index}`} testID={`admin-certificate-template-preview-option-${index}`}
                  >
                    <Text style={{ color: C.text, fontSize: 11, fontWeight: '800' }}>{certificate.certificate_number || certificate.verification_id}</Text>
                    <Text style={{ color: C.muted, fontSize: 10 }}>{certificate.course_title || 'Certificate preview sample'}</Text>
                  </TouchableOpacity>
                );
              })}
            </ScrollView>
          </View>
        </View>

        <View style={{ flex: 1, minWidth: workspaceStacked ? undefined : 520, backgroundColor: C.card, borderWidth: 1, borderColor: C.borderSoft, borderRadius: 18, padding: 14, gap: 12 }} data-testid="admin-certificate-template-center-canvas-card" testID="admin-certificate-template-center-canvas-card">
          <View style={{ flexDirection: workspaceStacked ? 'column' : 'row', justifyContent: 'space-between', gap: 10 }}>
            <View>
              <Text style={{ color: C.text, fontSize: 15, fontWeight: '900' }} data-testid="admin-certificate-template-preview-title" testID="admin-certificate-template-preview-title">{tx('admin.certificateTemplateManagerPanel.auto.text.011', 'Live certificate canvas')}</Text>
              <Text style={{ color: C.muted, fontSize: 10, marginTop: 4 }}>{tx('admin.certificateTemplateManagerPanel.auto.text.012', 'Canvas overlays mirror the current template values. Save to regenerate the real asset.')}</Text>
            </View>
            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }} data-testid="admin-certificate-template-canvas-toolbar" testID="admin-certificate-template-canvas-toolbar">
              <TouchableOpacity onPress={() => setZoomLevel(zoom - 0.1)} style={{ borderRadius: 999, borderWidth: 1, borderColor: C.borderSoft, backgroundColor: C.cardMuted, paddingHorizontal: 12, paddingVertical: 9, flexDirection: 'row', alignItems: 'center', gap: 6 }} data-testid="admin-certificate-template-zoom-out-button" testID="admin-certificate-template-zoom-out-button">
                <Ionicons name="remove-outline" size={14} color={C.text} />
                <Text style={{ color: C.text, fontSize: 11, fontWeight: '800' }}>{tx('admin.certificateTemplateManagerPanel.auto.text.013', 'Zoom out')}</Text>
              </TouchableOpacity>
              <TouchableOpacity onPress={() => setZoomLevel(1)} style={{ borderRadius: 999, borderWidth: 1, borderColor: C.borderSoft, backgroundColor: C.cardMuted, paddingHorizontal: 12, paddingVertical: 9 }} data-testid="admin-certificate-template-fit-button" testID="admin-certificate-template-fit-button">
                <Text style={{ color: C.text, fontSize: 11, fontWeight: '800' }}>{zoomLabel}</Text>
              </TouchableOpacity>
              <TouchableOpacity onPress={() => setZoomLevel(zoom + 0.1)} style={{ borderRadius: 999, borderWidth: 1, borderColor: C.borderSoft, backgroundColor: C.cardMuted, paddingHorizontal: 12, paddingVertical: 9, flexDirection: 'row', alignItems: 'center', gap: 6 }} data-testid="admin-certificate-template-zoom-in-button" testID="admin-certificate-template-zoom-in-button">
                <Ionicons name="add-outline" size={14} color={C.text} />
                <Text style={{ color: C.text, fontSize: 11, fontWeight: '800' }}>{tx('admin.certificateTemplateManagerPanel.auto.text.014', 'Zoom in')}</Text>
              </TouchableOpacity>
              <TouchableOpacity onPress={() => setGuidesVisible((value) => !value)} style={{ borderRadius: 999, borderWidth: 1, borderColor: guidesVisible ? C.blue : C.borderSoft, backgroundColor: guidesVisible ? `${C.blue}16` : C.cardMuted, paddingHorizontal: 12, paddingVertical: 9, flexDirection: 'row', alignItems: 'center', gap: 6 }} data-testid="admin-certificate-template-guides-toggle-button" testID="admin-certificate-template-guides-toggle-button">
                <Ionicons name={guidesVisible ? 'eye-outline' : 'eye-off-outline'} size={14} color={guidesVisible ? C.blue : C.text} />
                <Text style={{ color: guidesVisible ? C.blue : C.text, fontSize: 11, fontWeight: '800' }}>{guidesVisible ? 'Guides on' : 'Guides off'}</Text>
              </TouchableOpacity>
            </View>
          </View>

          <View style={{ borderRadius: 14, borderWidth: 1, borderColor: C.borderSoft, backgroundColor: C.cardMuted, padding: 10, gap: 8 }} data-testid="admin-certificate-template-live-ruler-panel" testID="admin-certificate-template-live-ruler-panel">
            <Text style={{ color: C.text, fontSize: 12, fontWeight: '900' }} data-testid="admin-certificate-template-live-ruler-title" testID="admin-certificate-template-live-ruler-title">Live ruler measurements · {selectedMeta.title}</Text>
            <Text style={{ color: C.muted, fontSize: 10, lineHeight: 16 }} data-testid="admin-certificate-template-live-ruler-subtitle" testID="admin-certificate-template-live-ruler-subtitle">{tx('admin.certificateTemplateManagerPanel.auto.text.015', 'Drag the layer to move. Pull the corner handle to resize. Measurements update live in millimeters and stage pixels.')}</Text>
            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6 }} data-testid="admin-certificate-template-live-ruler-metrics" testID="admin-certificate-template-live-ruler-metrics">
              {[
                { key: 'x', label: `X ${selectedRulerReadout.xMm.toFixed(1)}mm`, detail: `${selectedRulerReadout.xPx.toFixed(0)}px` },
                { key: 'y', label: `Y ${selectedRulerReadout.yMm.toFixed(1)}mm`, detail: `${selectedRulerReadout.yPx.toFixed(0)}px` },
                { key: 'w', label: `W ${selectedRulerReadout.wMm.toFixed(1)}mm`, detail: `${selectedRulerReadout.wPx.toFixed(0)}px` },
                { key: 'h', label: `H ${selectedRulerReadout.hMm.toFixed(1)}mm`, detail: `${selectedRulerReadout.hPx.toFixed(0)}px` },
              ].map((item) => (
                <View key={item.key} style={{ borderRadius: 999, borderWidth: 1, borderColor: C.borderSoft, backgroundColor: C.card, paddingHorizontal: 10, paddingVertical: 5 }} data-testid={`admin-certificate-template-live-ruler-${item.key}`} testID={`admin-certificate-template-live-ruler-${item.key}`}>
                  <Text style={{ color: C.text, fontSize: 10, fontWeight: '800' }}>{item.label}</Text>
                  <Text style={{ color: C.muted, fontSize: 9, marginTop: 2 }}>{item.detail}</Text>
                </View>
              ))}
            </View>
          </View>

          <View style={{ borderRadius: 16, borderWidth: 1, borderColor: C.borderSoft, backgroundColor: C.cardMuted, padding: 12, alignItems: 'center', overflow: 'hidden' }} data-testid="admin-certificate-template-preview-frame" testID="admin-certificate-template-preview-frame">
            {previewUrl ? (
              <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ paddingHorizontal: 6 }} data-testid="admin-certificate-template-preview-scroll-x" testID="admin-certificate-template-preview-scroll-x">
                <View
                  style={{ width: canvasWidth, aspectRatio: MM_STAGE_WIDTH / MM_STAGE_HEIGHT, position: 'relative', backgroundColor: C.card, borderRadius: 14, overflow: 'hidden', borderWidth: 1, borderColor: C.borderSoft }}
                  onLayout={(event) => {
                    const { width: measuredWidth, height } = event.nativeEvent.layout;
                    setStageSize({ width: measuredWidth, height });
                  }}
                  data-testid="admin-certificate-template-preview-stage" testID="admin-certificate-template-preview-stage"
                >
                  <Image source={{ uri: previewUrl }} style={{ width: '100%', height: '100%' }} resizeMode="contain" data-testid="admin-certificate-template-preview-image" testID="admin-certificate-template-preview-image" accessibilityLabel={tx('admin.certificateTemplateManagerPanel.auto.accessibility.002', 'Decorative image')} />

                  <View style={{ position: 'absolute', left: 0, right: 0, top: 0, height: 20, borderBottomWidth: 1, borderBottomColor: 'rgba(148,163,184,0.35)', backgroundColor: 'rgba(2,6,23,0.14)' }} pointerEvents="none" data-testid="admin-certificate-template-ruler-top" testID="admin-certificate-template-ruler-top">
                    {rulerTicks.map((value) => {
                      const left = (value / MM_STAGE_WIDTH) * stageSize.width;
                      const major = value % 50 === 0;
                      return (
                        <View key={`top-${value}`} style={{ position: 'absolute', left, top: 0, alignItems: 'center' }}>
                          <View style={{ width: 1, height: major ? 12 : 7, backgroundColor: 'rgba(226,232,240,0.75)' }} />
                          {major ? <Text style={{ color: colors.textMuted, fontSize: 8, fontWeight: '700' }}>{value}</Text> : null}
                        </View>
                      );
                    })}
                  </View>

                  <View style={{ position: 'absolute', left: 0, top: 0, bottom: 0, width: 26, borderRightWidth: 1, borderRightColor: 'rgba(148,163,184,0.35)', backgroundColor: 'rgba(2,6,23,0.14)' }} pointerEvents="none" data-testid="admin-certificate-template-ruler-left" testID="admin-certificate-template-ruler-left">
                    {rulerTicksVertical.map((value) => {
                      const top = (value / MM_STAGE_HEIGHT) * stageSize.height;
                      const major = value % 50 === 0;
                      return (
                        <View key={`left-${value}`} style={{ position: 'absolute', top, left: 0, flexDirection: 'row', alignItems: 'center' }}>
                          <View style={{ width: major ? 12 : 7, height: 1, backgroundColor: 'rgba(226,232,240,0.75)' }} />
                          {major ? <Text style={{ color: colors.textMuted, fontSize: 8, fontWeight: '700' }}>{value}</Text> : null}
                        </View>
                      );
                    })}
                  </View>

                  {guidesVisible ? (
                    <>
                      <View style={{ position: 'absolute', top: 0, bottom: 0, left: pageCenterGuideX, width: 1, backgroundColor: 'rgba(34,199,200,0.72)' }} pointerEvents="none" />
                      <View style={{ position: 'absolute', top: 0, bottom: 0, left: midpointGuideX, width: 1, backgroundColor: 'rgba(99,102,241,0.72)' }} pointerEvents="none" />
                      <View style={{ position: 'absolute', left: pageCenterGuideX + 4, top: 8, backgroundColor: 'rgba(34,199,200,0.14)', borderRadius: 999, paddingHorizontal: 8, paddingVertical: 4 }} pointerEvents="none">
                        <Text style={{ color: colors.accent, fontSize: 9, fontWeight: '800' }}>{tx('admin.certificateTemplateManagerPanel.auto.text.016', 'Page center')}</Text>
                      </View>
                      <View style={{ position: 'absolute', left: midpointGuideX + 4, top: 34, backgroundColor: 'rgba(99,102,241,0.14)', borderRadius: 999, paddingHorizontal: 8, paddingVertical: 4 }} pointerEvents="none">
                        <Text style={{ color: colors.primary, fontSize: 9, fontWeight: '800' }}>{tx('admin.certificateTemplateManagerPanel.auto.text.017', 'Stamp midpoint')}</Text>
                      </View>
                    </>
                  ) : null}

                  {(['stamp', 'signature', 'logo'] as EditableElement[]).map((element) => {
                    const frame = elementFrames[element];
                    const scaleX = stageSize.width / MM_STAGE_WIDTH;
                    const scaleY = stageSize.height / MM_STAGE_HEIGHT;
                    const panHandlers = element === 'stamp'
                      ? stampPanResponder.panHandlers
                      : element === 'signature'
                        ? signaturePanResponder.panHandlers
                        : logoPanResponder.panHandlers;
                    const resizeHandlers = element === 'stamp'
                      ? stampResizePanResponder.panHandlers
                      : element === 'signature'
                        ? signatureResizePanResponder.panHandlers
                        : logoResizePanResponder.panHandlers;
                    const selected = selectedElement === element;
                    const meta = LAYER_META[element];
                    return (
                      <TouchableOpacity accessibilityLabel={tx('admin.certificateTemplateManagerPanel.auto.accessibility.003', 'Drag certificate layer overlay')}
                        key={element}
                        activeOpacity={0.95}
                        onPress={() => setSelectedElement(element)}
                        {...panHandlers}
                        style={{
                          position: 'absolute',
                          left: frame.x * scaleX,
                          top: frame.y * scaleY,
                          width: Math.max(frame.width * scaleX, 24),
                          height: Math.max(frame.height * scaleY, 18),
                          borderWidth: selected ? 2 : 1,
                          borderStyle: 'dashed',
                          borderColor: meta.tone,
                          backgroundColor: `${meta.tone}${selected ? '1A' : '10'}`,
                          borderRadius: 12,
                          justifyContent: 'space-between',
                          padding: 6,
                        }}
                        data-testid={`admin-certificate-template-overlay-${element}`} testID={`admin-certificate-template-overlay-${element}`}
                      >
                        <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 6 }}>
                          <Text style={{ color: C.text, fontSize: 9, fontWeight: '900' }}>{meta.title}</Text>
                          <Ionicons name="move-outline" size={12} color={meta.tone} />
                        </View>
                        <Text style={{ color: C.textSoft, fontSize: 8, fontWeight: '700' }}>X {frame.x.toFixed(1)} · Y {frame.y.toFixed(1)}</Text>
                        <View
                          {...resizeHandlers}
                          style={{
                            position: 'absolute',
                            right: -8,
                            bottom: -8,
                            width: 18,
                            height: 18,
                            borderRadius: 9,
                            backgroundColor: meta.tone,
                            borderWidth: 2,
                            borderColor: colors.primaryText,
                            alignItems: 'center',
                            justifyContent: 'center',
                          }}
                          data-testid={`admin-certificate-template-resize-handle-${element}`} testID={`admin-certificate-template-resize-handle-${element}`}
                        >
                          <Ionicons name="resize-outline" size={10} color={colors.primaryText} />
                        </View>
                      </TouchableOpacity>
                    );
                  })}
                </View>
              </ScrollView>
            ) : (
              <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center', padding: 18 }} data-testid="admin-certificate-template-preview-empty" testID="admin-certificate-template-preview-empty">
                <Text style={{ color: C.text, fontSize: 12, fontWeight: '700' }}>{tx('admin.certificateTemplateManagerPanel.auto.text.018', 'No certificate available for preview')}</Text>
                <Text style={{ color: C.muted, fontSize: 10, marginTop: 4, textAlign: 'center' }}>{tx('admin.certificateTemplateManagerPanel.auto.text.019', 'Issue a certificate first, then it will appear here for template editing.')}</Text>
              </View>
            )}
          </View>
        </View>

        <View style={{ width: workspaceStacked ? '100%' : 332, backgroundColor: C.card, borderWidth: 1, borderColor: C.borderSoft, borderRadius: 18, padding: 14, gap: 12 }} data-testid="admin-certificate-template-right-sidebar" testID="admin-certificate-template-right-sidebar">
          <View style={{ borderRadius: 16, borderWidth: 1, borderColor: C.borderSoft, backgroundColor: C.cardMuted, padding: 12, gap: 8 }} data-testid="admin-certificate-template-typography-presets-card" testID="admin-certificate-template-typography-presets-card">
            <Text style={{ color: C.text, fontSize: 13, fontWeight: '900' }} data-testid="admin-certificate-template-typography-presets-title" testID="admin-certificate-template-typography-presets-title">{tx('admin.certificateTemplateManagerPanel.auto.text.020', 'Signer typography presets')}</Text>
            <Text style={{ color: C.muted, fontSize: 10, lineHeight: 16 }} data-testid="admin-certificate-template-typography-presets-subtitle" testID="admin-certificate-template-typography-presets-subtitle">{tx('admin.certificateTemplateManagerPanel.auto.text.021', 'Choose how CEO name and title render in the certificate signature block.')}</Text>
            <View style={{ gap: 8 }} data-testid="admin-certificate-template-typography-presets-options" testID="admin-certificate-template-typography-presets-options">
              {typographyPresets.map((preset) => {
                const active = typographyPreset === preset.id;
                return (
                  <TouchableOpacity accessibilityLabel={tx('admin.certificateTemplateManagerPanel.auto.accessibility.004', 'Choose signer typography preset')}
                    key={preset.id}
                    onPress={() => {
                      setTypographyPreset(preset.id);
                      setDragHint(`Typography preset selected: ${preset.label}`);
                    }}
                    style={{
                      borderRadius: 12,
                      borderWidth: 1,
                      borderColor: active ? C.blue : C.borderSoft,
                      backgroundColor: active ? `${C.blue}14` : C.card,
                      paddingHorizontal: 10,
                      paddingVertical: 9,
                    }}
                    data-testid={`admin-certificate-template-typography-preset-${preset.id}`} testID={`admin-certificate-template-typography-preset-${preset.id}`}
                  >
                    <Text style={{ color: active ? C.blue : C.text, fontSize: 11, fontWeight: '800' }}>{preset.label}</Text>
                    {preset.subtitle ? <Text style={{ color: C.muted, fontSize: 9, marginTop: 2 }}>{preset.subtitle}</Text> : null}
                  </TouchableOpacity>
                );
              })}
            </View>
          </View>

          <View style={{ borderRadius: 16, borderWidth: 1, borderColor: `${selectedMeta.tone}33`, backgroundColor: `${selectedMeta.tone}12`, padding: 12, gap: 8 }} data-testid="admin-certificate-template-selected-layer-card" testID="admin-certificate-template-selected-layer-card">
            <Text style={{ color: selectedMeta.tone, fontSize: 10, fontWeight: '900', letterSpacing: 1.2 }}>{tx('admin.certificateTemplateManagerPanel.auto.text.022', 'SELECTED LAYER')}</Text>
            <Text style={{ color: C.text, fontSize: 16, fontWeight: '900' }}>{selectedMeta.title}</Text>
            <Text style={{ color: C.muted, fontSize: 10, lineHeight: 16 }}>{selectedMeta.subtitle}</Text>
            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
              {[`X ${selectedFrame.x.toFixed(1)}mm`, `Y ${selectedFrame.y.toFixed(1)}mm`, `W ${selectedFrame.width.toFixed(1)}mm`, `H ${selectedFrame.height.toFixed(1)}mm`].map((metric) => (
                <View key={metric} style={{ borderRadius: 999, backgroundColor: C.card, borderWidth: 1, borderColor: C.borderSoft, paddingHorizontal: 8, paddingVertical: 4 }}>
                  <Text style={{ color: C.textSoft, fontSize: 10, fontWeight: '800' }}>{metric}</Text>
                </View>
              ))}
            </View>
          </View>

          <View data-testid="admin-certificate-template-nudge-controls" testID="admin-certificate-template-nudge-controls">
            <Text style={{ color: C.text, fontSize: 13, fontWeight: '900' }}>{tx('admin.certificateTemplateManagerPanel.auto.text.023', 'Precision nudges')}</Text>
            <View style={{ marginTop: 8, flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
              {[
                { id: 'left', label: '← 0.5mm', dx: -0.5, dy: 0 },
                { id: 'right', label: '0.5mm →', dx: 0.5, dy: 0 },
                { id: 'up', label: '↑ 0.5mm', dx: 0, dy: 0.5 },
                { id: 'down', label: '0.5mm ↓', dx: 0, dy: -0.5 },
              ].map((nudge) => (
                <TouchableOpacity
                  key={nudge.id}
                  onPress={() => nudgeSelected(nudge.dx, nudge.dy)}
                  style={{ flex: 1, minWidth: 130, backgroundColor: C.cardMuted, borderRadius: 12, borderWidth: 1, borderColor: C.borderSoft, paddingHorizontal: 10, paddingVertical: 9, alignItems: 'center' }}
                  data-testid={`admin-certificate-template-nudge-${nudge.id}`} testID={`admin-certificate-template-nudge-${nudge.id}`}
                >
                  <Text style={{ color: C.text, fontSize: 10, fontWeight: '800' }}>{nudge.label}</Text>
                </TouchableOpacity>
              ))}
            </View>
          </View>

          <View data-testid={`admin-certificate-template-group-${selectedGroup.id}`} testID={`admin-certificate-template-group-${selectedGroup.id}`}>
            <Text style={{ color: C.text, fontSize: 13, fontWeight: '900' }}>Inspector · {selectedGroup.title}</Text>
            <Text style={{ color: C.muted, fontSize: 10, marginTop: 4 }}>{tx('admin.certificateTemplateManagerPanel.auto.text.024', 'Every value stays in millimeters. Typing here immediately updates the live overlay.')}</Text>
            <View style={{ marginTop: 10, gap: 10 }}>
              {selectedGroup.fields.map((field) => (
                <View key={field.key} data-testid={`admin-certificate-template-field-${field.key}`} testID={`admin-certificate-template-field-${field.key}`}>
                  <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 5 }}>
                    <Text style={{ color: C.textSoft, fontSize: 10, fontWeight: '800', textTransform: 'uppercase', letterSpacing: 0.6 }}>{field.label}</Text>
                    <Text style={{ color: C.muted, fontSize: 10, fontWeight: '800' }}>{field.step}mm</Text>
                  </View>
                  <TextInput
                    value={settings[field.key] || ''}
                    onChangeText={(value) => updateField(field.key, value)}
                    keyboardType="decimal-pad"
                    placeholder="0"
                    placeholderTextColor={C.muted}
                    style={{ borderWidth: 1, borderColor: C.borderSoft, borderRadius: 12, paddingHorizontal: 12, paddingVertical: 10, color: C.text, backgroundColor: C.cardMuted, fontSize: 12, fontWeight: '700' }}
                    data-testid={`admin-certificate-template-input-${field.key}`} testID={`admin-certificate-template-input-${field.key}`}
                  />
                </View>
              ))}
            </View>
          </View>

          <View style={{ borderTopWidth: 1, borderTopColor: C.borderSoft, paddingTop: 12, gap: 10 }} data-testid="admin-certificate-template-other-groups-summary" testID="admin-certificate-template-other-groups-summary">
            <Text style={{ color: C.text, fontSize: 13, fontWeight: '900' }}>{tx('admin.certificateTemplateManagerPanel.auto.text.025', 'Other layers')}</Text>
            {otherGroups.map((group) => (
              <TouchableOpacity key={group.id} onPress={() => setSelectedElement(group.id as EditableElement)} style={{ borderRadius: 14, borderWidth: 1, borderColor: C.borderSoft, backgroundColor: C.cardMuted, padding: 10 }} data-testid={`admin-certificate-template-jump-${group.id}`} testID={`admin-certificate-template-jump-${group.id}`}>
                <Text style={{ color: C.text, fontSize: 11, fontWeight: '800' }}>{group.title}</Text>
                <Text style={{ color: C.muted, fontSize: 10, marginTop: 3 }}>{tx('admin.certificateTemplateManagerPanel.auto.text.026', 'Open this inspector and update its live overlay.')}</Text>
              </TouchableOpacity>
            ))}
          </View>
        </View>
      </View>
    </ScrollView>
  );
}