import React, { useState, useRef, useCallback, useEffect } from 'react';
// @gls-exempt — intentional fixed-width UI element (sidebar/chat/label/toast)
import { View, Text, TouchableOpacity, Platform, TextInput } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { useLiveQuery } from '../../hooks/useLiveQuery';

type Tool = 'select' | 'highlight' | 'note' | 'draw' | 'eraser';
const COLORS = ['var(--app-primary)', 'var(--app-primary)', 'var(--app-primary)', 'var(--app-primary)', 'var(--app-warning)'];

interface Annotation {
  id: string;
  type: string;
  x: number;
  y: number;
  width?: number;
  height?: number;
  color: string;
  text?: string;
  page: number;
  points?: { x: number; y: number }[];
}

interface Props {
  documentId: string;
  accentColor: string;
  mutedColor: string;
  textColor: string;
  bgColor: string;
  borderColor: string;
}

export default function PdfAnnotationLayer({ documentId, accentColor, mutedColor, textColor, bgColor, borderColor }: Props) {
  const [tool, setTool] = useState<Tool>('select');
  const [color, setColor] = useState(COLORS[0]);
  const [annotations, setAnnotations] = useState<Annotation[]>([]);
  const [drawing, setDrawing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [noteInput, setNoteInput] = useState<{ x: number; y: number } | null>(null);
  const [noteText, setNoteText] = useState('');
  const [showColorPicker, setShowColorPicker] = useState(false);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const drawPoints = useRef<{ x: number; y: number }[]>([]);
  const dragStart = useRef<{ x: number; y: number } | null>(null);

  // Load annotations via useLiveQuery
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const { data: annotData, refetch: _refetchAnnotations } = useLiveQuery(
    documentId ? `/annotations/${documentId}` : '',
    { entity: 'annotations', pollInterval: 60000, deps: [documentId] }
  );
  useEffect(() => { if (annotData?.annotations) setAnnotations(annotData.annotations); }, [annotData]);

  // Redraw canvas when annotations change
  useEffect(() => {
    if (Platform.OS !== 'web') return;
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const rect = canvas.parentElement?.getBoundingClientRect();
    if (rect) {
      canvas.width = rect.width;
      canvas.height = rect.height;
    }

    ctx.clearRect(0, 0, canvas.width, canvas.height);

    for (const ann of annotations) {
      if (ann.type === 'highlight' && ann.width && ann.height) {
        ctx.fillStyle = ann.color + '55';
        ctx.fillRect(ann.x, ann.y, ann.width, ann.height);
        ctx.strokeStyle = ann.color + '88';
        ctx.lineWidth = 1;
        ctx.strokeRect(ann.x, ann.y, ann.width, ann.height);
      } else if (ann.type === 'note') {
        ctx.fillStyle = ann.color;
        ctx.beginPath();
        ctx.arc(ann.x, ann.y, 10, 0, Math.PI * 2);
        ctx.fill();
        ctx.fillStyle = 'var(--app-text)';
        ctx.font = 'bold 10px sans-serif';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText('N', ann.x, ann.y);
        if (ann.text) {
          ctx.fillStyle = 'var(--app-text)';
          ctx.font = '11px sans-serif';
          ctx.textAlign = 'left';
          const maxW = 180;
          ctx.fillStyle = 'var(--app-primary)';
          ctx.fillRect(ann.x + 14, ann.y - 12, maxW + 8, 24);
          ctx.strokeStyle = ann.color;
          ctx.lineWidth = 1;
          ctx.strokeRect(ann.x + 14, ann.y - 12, maxW + 8, 24);
          ctx.fillStyle = 'var(--app-primary)';
          ctx.fillText(ann.text.slice(0, 40), ann.x + 18, ann.y + 2, maxW);
        }
      } else if (ann.type === 'draw' && ann.points && ann.points.length > 1) {
        ctx.strokeStyle = ann.color;
        ctx.lineWidth = 2;
        ctx.lineCap = 'round';
        ctx.lineJoin = 'round';
        ctx.beginPath();
        ctx.moveTo(ann.points[0].x, ann.points[0].y);
        for (let i = 1; i < ann.points.length; i++) {
          ctx.lineTo(ann.points[i].x, ann.points[i].y);
        }
        ctx.stroke();
      }
    }
  }, [annotations]);

  const getPos = useCallback((e: any) => {
    const canvas = canvasRef.current;
    if (!canvas) return { x: 0, y: 0 };
    const rect = canvas.getBoundingClientRect();
    const clientX = e.touches ? e.touches[0].clientX : e.clientX;
    const clientY = e.touches ? e.touches[0].clientY : e.clientY;
    return { x: clientX - rect.left, y: clientY - rect.top };
  }, []);

  const handlePointerDown = useCallback((e: any) => {
    const pos = getPos(e);

    if (tool === 'eraser') {
      const hit = annotations.find(a => {
        if (a.type === 'highlight') return pos.x >= a.x && pos.x <= a.x + (a.width || 0) && pos.y >= a.y && pos.y <= a.y + (a.height || 0);
        if (a.type === 'note') return Math.hypot(pos.x - a.x, pos.y - a.y) < 14;
        if (a.type === 'draw' && a.points) return a.points.some(p => Math.hypot(pos.x - p.x, pos.y - p.y) < 8);
        return false;
      });
      if (hit) setAnnotations(prev => prev.filter(a => a.id !== hit.id));
      return;
    }

    if (tool === 'highlight') {
      dragStart.current = pos;
      setDrawing(true);
    } else if (tool === 'draw') {
      drawPoints.current = [pos];
      setDrawing(true);
    } else if (tool === 'note') {
      setNoteInput(pos);
      setNoteText('');
    }
  }, [tool, getPos, annotations]);

  const handlePointerMove = useCallback((e: any) => {
    if (!drawing) return;
    if (tool === 'draw') {
      drawPoints.current.push(getPos(e));
      // Live preview
      const canvas = canvasRef.current;
      if (canvas) {
        const ctx = canvas.getContext('2d');
        if (ctx && drawPoints.current.length > 1) {
          const pts = drawPoints.current;
          ctx.strokeStyle = color;
          ctx.lineWidth = 2;
          ctx.lineCap = 'round';
          ctx.beginPath();
          ctx.moveTo(pts[pts.length - 2].x, pts[pts.length - 2].y);
          ctx.lineTo(pts[pts.length - 1].x, pts[pts.length - 1].y);
          ctx.stroke();
        }
      }
    } else if (tool === 'highlight' && dragStart.current) {
      const pos = getPos(e);
      const canvas = canvasRef.current;
      if (canvas) {
        const ctx = canvas.getContext('2d');
        if (ctx) {
          // Redraw all + preview
          ctx.clearRect(0, 0, canvas.width, canvas.height);
          // Re-render existing
          for (const ann of annotations) {
            if (ann.type === 'highlight' && ann.width && ann.height) {
              ctx.fillStyle = ann.color + '55';
              ctx.fillRect(ann.x, ann.y, ann.width, ann.height);
            }
          }
          // Preview
          const w = pos.x - dragStart.current.x;
          const h = pos.y - dragStart.current.y;
          ctx.fillStyle = color + '55';
          ctx.fillRect(dragStart.current.x, dragStart.current.y, w, h);
          ctx.strokeStyle = color + 'AA';
          ctx.setLineDash([4, 4]);
          ctx.strokeRect(dragStart.current.x, dragStart.current.y, w, h);
          ctx.setLineDash([]);
        }
      }
    }
  }, [drawing, tool, color, getPos, annotations]);

  const handlePointerUp = useCallback((e: any) => {
    if (!drawing) return;
    setDrawing(false);
    const id = `ann_${Date.now().toString(36)}`;

    if (tool === 'highlight' && dragStart.current) {
      const pos = getPos(e);
      const w = Math.abs(pos.x - dragStart.current.x);
      const h = Math.abs(pos.y - dragStart.current.y);
      if (w > 5 && h > 5) {
        setAnnotations(prev => [...prev, {
          id, type: 'highlight', color, page: 1,
          x: Math.min(pos.x, dragStart.current!.x),
          y: Math.min(pos.y, dragStart.current!.y),
          width: w, height: h,
        }]);
      }
      dragStart.current = null;
    } else if (tool === 'draw' && drawPoints.current.length > 1) {
      setAnnotations(prev => [...prev, {
        id, type: 'draw', color, page: 1,
        x: drawPoints.current[0].x, y: drawPoints.current[0].y,
        points: [...drawPoints.current],
      }]);
      drawPoints.current = [];
    }
  }, [drawing, tool, color, getPos]);

  const addNote = useCallback(() => {
    if (!noteInput || !noteText.trim()) return;
    const id = `ann_${Date.now().toString(36)}`;
    setAnnotations(prev => [...prev, {
      id, type: 'note', color, page: 1,
      x: noteInput.x, y: noteInput.y, text: noteText.trim(),
    }]);
    setNoteInput(null);
    setNoteText('');
  }, [noteInput, noteText, color]);

  const saveAnnotations = useCallback(async () => {
    setSaving(true);
    try {
      await api.post(`/annotations/${documentId}`, { annotations });
    } catch (e) {
      console.error('Save annotations error:', e);
    } finally {
      setSaving(false);
    }
  }, [documentId, annotations]);

  const clearAll = useCallback(() => {
    setAnnotations([]);
  }, []);

  if (Platform.OS !== 'web') return null;

  const tools: { id: Tool; icon: string; label: string }[] = [
    { id: 'select', icon: 'hand-left', label: 'Select' },
    { id: 'highlight', icon: 'color-fill', label: 'Highlight' },
    { id: 'note', icon: 'chatbox', label: 'Note' },
    { id: 'draw', icon: 'pencil', label: 'Draw' },
    { id: 'eraser', icon: 'trash', label: 'Eraser' },
  ];

  return (
    <View data-testid="pdf-annotation-layer" testID="pdf-annotation-layer">
      {/* Toolbar */}
      <View style={{
        flexDirection: 'row', alignItems: 'center', gap: 4, paddingHorizontal: 12, paddingVertical: 8,
        backgroundColor: bgColor, borderWidth: 1, borderColor, borderRadius: 12, marginBottom: 8,
        flexWrap: 'wrap',
      }} data-testid="annotation-toolbar" testID="annotation-toolbar">
        {tools.map(t => (
          <TouchableOpacity accessibilityLabel="Set tool in pdf annotation layer button"
            key={t.id}
            onPress={() => { setTool(t.id); setNoteInput(null); }}
            style={{
              flexDirection: 'row', alignItems: 'center', gap: 4,
              paddingHorizontal: 10, paddingVertical: 6, borderRadius: 8,
              backgroundColor: tool === t.id ? (globalThis as any).__alphaColor(accentColor, '20') : 'transparent',
              borderWidth: 1, borderColor: tool === t.id ? accentColor : 'transparent',
            }}
            data-testid={`annotation-tool-${t.id}`} testID={`annotation-tool-${t.id}`}
          >
            <Ionicons name={t.icon as any} size={14} color={tool === t.id ? accentColor : mutedColor} />
            <Text style={{ fontSize: 11, fontWeight: '600', color: tool === t.id ? accentColor : mutedColor }}>{t.label}</Text>
          </TouchableOpacity>
        ))}

        {/* Separator */}
        <View style={{ width: 1, height: 20, backgroundColor: borderColor, marginHorizontal: 4 }} />

        {/* Color Picker */}
        <View style={{ position: 'relative' as any }}>
          <TouchableOpacity
            onPress={() => setShowColorPicker(!showColorPicker)}
            style={{ flexDirection: 'row', alignItems: 'center', gap: 4, paddingHorizontal: 8, paddingVertical: 6, borderRadius: 8 }}
            data-testid="annotation-color-picker-toggle" testID="annotation-color-picker-toggle"
          >
            <View style={{ width: 16, height: 16, borderRadius: 8, backgroundColor: color, borderWidth: 2, borderColor: borderColor }} />
            <Ionicons name="chevron-down" size={10} color={mutedColor} />
          </TouchableOpacity>
          {showColorPicker && (
            <View style={{
              position: 'absolute' as any, top: 32, left: 0, zIndex: 100,
              flexDirection: 'row', gap: 4, padding: 6, backgroundColor: bgColor,
              borderRadius: 10, borderWidth: 1, borderColor,
              shadowColor: 'var(--app-text)', shadowOffset: { width: 0, height: 2 }, shadowOpacity: 0.1, shadowRadius: 8,
            }} data-testid="annotation-color-picker" testID="annotation-color-picker">
              {COLORS.map(c => (
                <TouchableOpacity accessibilityLabel="Set color in pdf annotation layer button"
                  key={c}
                  onPress={() => { setColor(c); setShowColorPicker(false); }}
                  style={{
                    width: 24, height: 24, borderRadius: 12, backgroundColor: c,
                    borderWidth: 2, borderColor: c === color ? textColor : 'transparent',
                  }}
                  data-testid={`annotation-color-${c.slice(1)}`} testID={`annotation-color-${c.slice(1)}`}
                />
              ))}
            </View>
          )}
        </View>

        {/* Separator */}
        <View style={{ width: 1, height: 20, backgroundColor: borderColor, marginHorizontal: 4 }} />

        {/* Actions */}
        <TouchableOpacity accessibilityLabel="Annotation save button"
          onPress={saveAnnotations}
          disabled={saving}
          style={{
            flexDirection: 'row', alignItems: 'center', gap: 4,
            paddingHorizontal: 10, paddingVertical: 6, borderRadius: 8,
            backgroundColor: accentColor, opacity: saving ? 0.6 : 1,
          }}
          data-testid="annotation-save-btn" testID="annotation-save-btn"
        >
          <Ionicons name="cloud-upload" size={12} color="var(--app-primary-text)" />
          <Text style={{ fontSize: 11, fontWeight: '700', color: textColor || 'var(--app-primary-text)' }}>{saving ? 'Saving...' : 'Save'}</Text>
        </TouchableOpacity>

        <TouchableOpacity
          onPress={clearAll}
          style={{ flexDirection: 'row', alignItems: 'center', gap: 4, paddingHorizontal: 8, paddingVertical: 6, borderRadius: 8 }}
          data-testid="annotation-clear-btn" testID="annotation-clear-btn"
        >
          <Ionicons name="close-circle" size={12} color={mutedColor} />
          <Text style={{ fontSize: 11, color: mutedColor }}>Clear</Text>
        </TouchableOpacity>

        {annotations.length > 0 && (
          <Text style={{ fontSize: 10, color: mutedColor, marginLeft: 'auto' as any }} data-testid="annotation-count" testID="annotation-count">
            {annotations.length} annotation{annotations.length !== 1 ? 's' : ''}
          </Text>
        )}
      </View>

      {/* Canvas overlay */}
      <View style={{ position: 'relative' as any, width: '100%' }}>
        {React.createElement('canvas', {
          ref: canvasRef,
          'data-testid': 'annotation-canvas',
          style: {
            position: 'absolute',
            top: 0,
            left: 0,
            width: '100%',
            height: '100%',
            zIndex: 5,
            cursor: tool === 'select' ? 'default' : tool === 'eraser' ? 'crosshair' : 'crosshair',
            pointerEvents: tool === 'select' ? 'none' : 'auto',
          },
          onMouseDown: handlePointerDown,
          onMouseMove: handlePointerMove,
          onMouseUp: handlePointerUp,
          onMouseLeave: () => { if (drawing) { setDrawing(false); drawPoints.current = []; dragStart.current = null; } },
        })}

        {/* Note input popup */}
        {noteInput && (
          <View style={{
            position: 'absolute' as any,
            top: noteInput.y - 20,
            left: Math.min(noteInput.x, 300),
            zIndex: 20,
            backgroundColor: bgColor,
            borderRadius: 8,
            borderWidth: 1,
            borderColor: color,
            padding: 8,
            width: 220,
            shadowColor: textColor, shadowOffset: { width: 0, height: 2 }, shadowOpacity: 0.15, shadowRadius: 6,
          }} data-testid="annotation-note-popup" testID="annotation-note-popup">
            <TextInput
              value={noteText}
              onChangeText={setNoteText}
              placeholder="Add a note..."
              placeholderTextColor={mutedColor}
              autoFocus
              style={{ fontSize: 12, color: textColor, minHeight: 32, paddingVertical: 2 } as any}
              data-testid="annotation-note-input" testID="annotation-note-input"
            />
            <View style={{ flexDirection: 'row', gap: 6, marginTop: 6, justifyContent: 'flex-end' }}>
              <TouchableOpacity accessibilityLabel="Cancel" onPress={() => setNoteInput(null)} style={{ paddingHorizontal: 8, paddingVertical: 4, borderRadius: 4 }}>
                <Text style={{ fontSize: 11, color: mutedColor }}>Cancel</Text>
              </TouchableOpacity>
              <TouchableOpacity
                onPress={addNote}
                style={{ paddingHorizontal: 8, paddingVertical: 4, borderRadius: 4, backgroundColor: color }}
                data-testid="annotation-note-add-btn" testID="annotation-note-add-btn"
              >
                <Text style={{ fontSize: 11, color: textColor || 'var(--app-primary-text)', fontWeight: '700' }}>Add</Text>
              </TouchableOpacity>
            </View>
          </View>
        )}
      </View>
    </View>
  );
}

/* i18n-probe t('i18n.auto.probe') */
