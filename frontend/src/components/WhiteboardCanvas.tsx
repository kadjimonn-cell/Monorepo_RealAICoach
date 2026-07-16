import React, { useRef, useState, useEffect, useCallback } from 'react';
import { View, TouchableOpacity, Text } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useManagedWebSocket } from '../hooks/useManagedWebSocket';
import { handleRecoverableError } from '../utils/handleRecoverableError';

interface Stroke {
  id: string;
  tool: string;
  color: string;
  width: number;
  points: { x: number; y: number }[];
  text?: string;
}

interface Props {
  roomId: string;
  userId: string;
  wsRef: React.MutableRefObject<WebSocket | null>;
  onClose: () => void;
  isWide: boolean;
}

const COLORS = ['var(--app-primary-text)', 'var(--app-error)', 'var(--app-primary)', 'var(--app-success)', 'var(--app-warning)', 'var(--app-primary)', 'var(--app-primary)', 'var(--app-primary)'];
const TOOLS = [
  { id: 'pen', icon: 'pencil', label: 'Pen' },
  { id: 'eraser', icon: 'close-circle', label: 'Eraser' },
  { id: 'line', icon: 'remove', label: 'Line' },
  { id: 'rect', icon: 'square-outline', label: 'Rectangle' },
  { id: 'circle', icon: 'ellipse-outline', label: 'Circle' },
];

const C = {
  bg: 'var(--app-bg)', card: 'var(--app-card-bg)', border: 'var(--app-border)', text: 'var(--app-text)',
  muted: 'var(--app-text-muted)', primary: 'var(--app-primary)', accent: 'var(--app-primary)', success: 'var(--app-success)', error: 'var(--app-error)',
};

export default function WhiteboardCanvas({ roomId, userId, wsRef, onClose, isWide }: Props) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const [tool, setTool] = useState('pen');
  const [color, setColor] = useState('var(--app-primary-text)');
  const [strokeWidth, setStrokeWidth] = useState(2);
  const [strokes, setStrokes] = useState<Stroke[]>([]);
  const [currentStroke, setCurrentStroke] = useState<Stroke | null>(null);
  const [undoStack, setUndoStack] = useState<Stroke[]>([]);
  const [connectionError, setConnectionError] = useState('');
  const isDrawingRef = useRef(false);
  const wsUrlBuilder = useCallback(() => {
    const runtimeBase = typeof window !== 'undefined' && window.location?.host
      ? `https://${window.location.host}`
      : (process.env.REACT_APP_BACKEND_URL || '');
    return runtimeBase.replace(/^https?/, 'wss') + `/api/ws/whiteboard/${roomId}/${userId}`;
  }, [roomId, userId]);

  const {
    socketRef: wbWsRef,
    connected: wbConnected,
    reconnectAttempt,
    lastError,
  } = useManagedWebSocket({
    enabled: Boolean(roomId && userId),
    buildUrl: wsUrlBuilder,
    errorScope: 'whiteboard/ws',
    maxReconnectAttempts: 4,
    onReconnectAttempt: () => {
      setConnectionError('Live whiteboard reconnecting...');
    },
    onMessage: (event) => {
      if (event.data === 'pong') return;
      try {
        const data = JSON.parse(event.data);
        if (data.type === 'wb_stroke') {
          setStrokes(prev => [...prev, data.stroke]);
        } else if (data.type === 'wb_clear') {
          setStrokes([]);
        } else if (data.type === 'wb_undo') {
          setStrokes(prev => prev.filter(s => s.id !== data.stroke_id));
        }
        setConnectionError('');
      } catch (error) {
        handleRecoverableError(error, {
          scope: 'whiteboard/parse',
          fallbackMessage: 'Live whiteboard update could not be read.',
          setMessage: setConnectionError,
        });
      }
    },
  });

  useEffect(() => {
    wsRef.current = wbWsRef.current;
  }, [wbConnected, wbWsRef, wsRef]);

  useEffect(() => {
    if (!lastError) return;
    setConnectionError(lastError);
  }, [lastError]);

  // Redraw canvas whenever strokes change
  useEffect(() => {
    redraw();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [strokes, currentStroke]);

  const redraw = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    ctx.fillStyle = C.bg;
    ctx.fillRect(0, 0, canvas.width, canvas.height);

    // Draw grid
    ctx.strokeStyle = 'var(--app-primary)';
    ctx.lineWidth = 0.5;
    for (let x = 0; x < canvas.width; x += 40) {
      ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, canvas.height); ctx.stroke();
    }
    for (let y = 0; y < canvas.height; y += 40) {
      ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(canvas.width, y); ctx.stroke();
    }

    // Draw all completed strokes
    [...strokes, ...(currentStroke ? [currentStroke] : [])].forEach(s => drawStroke(ctx, s));
  }, [strokes, currentStroke]);

  const drawStroke = (ctx: CanvasRenderingContext2D, s: Stroke) => {
    if (!s.points || s.points.length === 0) return;
    ctx.strokeStyle = s.tool === 'eraser' ? C.bg : s.color;
    ctx.lineWidth = s.tool === 'eraser' ? s.width * 5 : s.width;
    ctx.lineCap = 'round';
    ctx.lineJoin = 'round';

    if (s.tool === 'pen' || s.tool === 'eraser') {
      ctx.beginPath();
      ctx.moveTo(s.points[0].x, s.points[0].y);
      for (let i = 1; i < s.points.length; i++) {
        ctx.lineTo(s.points[i].x, s.points[i].y);
      }
      ctx.stroke();
    } else if (s.tool === 'line' && s.points.length >= 2) {
      const start = s.points[0];
      const end = s.points[s.points.length - 1];
      ctx.beginPath(); ctx.moveTo(start.x, start.y); ctx.lineTo(end.x, end.y); ctx.stroke();
    } else if (s.tool === 'rect' && s.points.length >= 2) {
      const start = s.points[0];
      const end = s.points[s.points.length - 1];
      ctx.beginPath();
      ctx.rect(start.x, start.y, end.x - start.x, end.y - start.y);
      ctx.stroke();
    } else if (s.tool === 'circle' && s.points.length >= 2) {
      const start = s.points[0];
      const end = s.points[s.points.length - 1];
      const rx = Math.abs(end.x - start.x) / 2;
      const ry = Math.abs(end.y - start.y) / 2;
      const cx = (start.x + end.x) / 2;
      const cy = (start.y + end.y) / 2;
      ctx.beginPath(); ctx.ellipse(cx, cy, rx, ry, 0, 0, Math.PI * 2); ctx.stroke();
    }
  };

  const getPos = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const canvas = canvasRef.current;
    if (!canvas) return { x: 0, y: 0 };
    const rect = canvas.getBoundingClientRect();
    return { x: e.clientX - rect.left, y: e.clientY - rect.top };
  };

  const onMouseDown = (e: React.MouseEvent<HTMLCanvasElement>) => {
    isDrawingRef.current = true;
    const pos = getPos(e);
    const stroke: Stroke = {
      id: `s_${Date.now()}_${Math.random().toString(36).slice(2, 6)}`,
      tool, color, width: strokeWidth, points: [pos],
    };
    setCurrentStroke(stroke);
  };

  const onMouseMove = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (!isDrawingRef.current || !currentStroke) return;
    const pos = getPos(e);
    setCurrentStroke(prev => prev ? { ...prev, points: [...prev.points, pos] } : null);
  };

  const onMouseUp = () => {
    if (!isDrawingRef.current || !currentStroke) return;
    isDrawingRef.current = false;
    setStrokes(prev => [...prev, currentStroke]);
    setUndoStack([]);

    // Broadcast stroke to peers
    if (wbWsRef.current?.readyState === WebSocket.OPEN) {
      wbWsRef.current.send(JSON.stringify({ type: 'wb_stroke', stroke: currentStroke }));
    }
    setCurrentStroke(null);
  };

  const undo = () => {
    if (strokes.length === 0) return;
    const last = strokes[strokes.length - 1];
    setStrokes(prev => prev.slice(0, -1));
    setUndoStack(prev => [...prev, last]);
    if (wbWsRef.current?.readyState === WebSocket.OPEN) {
      wbWsRef.current.send(JSON.stringify({ type: 'wb_undo', stroke_id: last.id }));
    }
  };

  const redo = () => {
    if (undoStack.length === 0) return;
    const last = undoStack[undoStack.length - 1];
    setUndoStack(prev => prev.slice(0, -1));
    setStrokes(prev => [...prev, last]);
    if (wbWsRef.current?.readyState === WebSocket.OPEN) {
      wbWsRef.current.send(JSON.stringify({ type: 'wb_stroke', stroke: last }));
    }
  };

  const clearAll = () => {
    setStrokes([]);
    setUndoStack([]);
    if (wbWsRef.current?.readyState === WebSocket.OPEN) {
      wbWsRef.current.send(JSON.stringify({ type: 'wb_clear' }));
    }
  };

  return (
    <View data-testid="whiteboard-panel" testID="whiteboard-panel" style={{
      width: isWide ? '100%' : '100%', height: '100%',
      backgroundColor: C.bg, display: 'flex', flexDirection: 'column',
    }}>
      {/* Toolbar */}
      <View style={{
        flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
        paddingHorizontal: 10, paddingVertical: 6, backgroundColor: C.card,
        borderBottomWidth: 1, borderBottomColor: C.border, flexWrap: 'wrap', gap: 4,
      }}>
        {/* Tools */}
        <View style={{ flexDirection: 'row', gap: 3 }}>
          {TOOLS.map(t => (
            <TouchableOpacity key={t.id} onPress={() => setTool(t.id)} data-testid={`wb-tool-${t.id}`} testID={`wb-tool-${t.id}`}
              style={{
                padding: 6, borderRadius: 6,
                backgroundColor: tool === t.id ? (globalThis as any).__alphaColor(C.primary, '30') : 'transparent',
                borderWidth: 1, borderColor: tool === t.id ? C.primary : 'transparent',
              }}>
              <Ionicons name={t.icon as any} size={16} color={tool === t.id ? C.primary : C.muted} />
            </TouchableOpacity>
          ))}
        </View>

        {/* Colors */}
        <View style={{ flexDirection: 'row', gap: 3, alignItems: 'center' }}>
          {COLORS.map(c => (
            <TouchableOpacity key={c} onPress={() => setColor(c)} data-testid={`wb-color-${c.replace('#', '')}`} testID={`wb-color-${c.replace('#', '')}`}
              style={{
                width: 18, height: 18, borderRadius: 9, backgroundColor: c,
                borderWidth: 2, borderColor: color === c ? C.primary : C.border,
              }} />
          ))}
        </View>

        {/* Width */}
        <View style={{ flexDirection: 'row', gap: 3, alignItems: 'center' }}>
          {[1, 2, 4, 8].map(w => (
            <TouchableOpacity key={w} onPress={() => setStrokeWidth(w)} data-testid={`wb-width-${w}`} testID={`wb-width-${w}`}
              style={{
                width: 22, height: 22, borderRadius: 4, alignItems: 'center', justifyContent: 'center',
                backgroundColor: strokeWidth === w ? (globalThis as any).__alphaColor(C.primary, '30') : 'transparent',
                borderWidth: 1, borderColor: strokeWidth === w ? C.primary : C.border,
              }}>
              <View style={{ width: Math.min(w * 2, 12), height: Math.min(w * 2, 12), borderRadius: w, backgroundColor: C.text }} />
            </TouchableOpacity>
          ))}
        </View>

        {/* Actions */}
        <View style={{ flexDirection: 'row', gap: 3 }}>
          <TouchableOpacity onPress={undo} data-testid="wb-undo" testID="wb-undo" style={{ padding: 6, borderRadius: 6, backgroundColor: C.card, borderWidth: 1, borderColor: C.border }}>
            <Ionicons name="arrow-undo" size={14} color={strokes.length > 0 ? C.text : C.muted} />
          </TouchableOpacity>
          <TouchableOpacity onPress={redo} data-testid="wb-redo" testID="wb-redo" style={{ padding: 6, borderRadius: 6, backgroundColor: C.card, borderWidth: 1, borderColor: C.border }}>
            <Ionicons name="arrow-redo" size={14} color={undoStack.length > 0 ? C.text : C.muted} />
          </TouchableOpacity>
          <TouchableOpacity onPress={clearAll} data-testid="wb-clear" testID="wb-clear" style={{ padding: 6, borderRadius: 6, backgroundColor: (globalThis as any).__alphaColor(C.error, '15'), borderWidth: 1, borderColor: C.error }}>
            <Ionicons name="trash" size={14} color={C.error} />
          </TouchableOpacity>
          <TouchableOpacity onPress={onClose} data-testid="wb-close" testID="wb-close" style={{ padding: 6, borderRadius: 6, backgroundColor: C.card, borderWidth: 1, borderColor: C.border }}>
            <Ionicons name="close" size={14} color={C.muted} />
          </TouchableOpacity>
        </View>
        <View data-testid="wb-connection-status" testID="wb-connection-status" style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginLeft: 6 }}>
          <View style={{ width: 7, height: 7, borderRadius: 4, backgroundColor: wbConnected ? C.success : C.error }} />
          <Text style={{ color: wbConnected ? C.success : C.error, fontSize: 10, fontWeight: '700' }}>
            {wbConnected ? 'Live' : reconnectAttempt > 0 ? `Reconnecting (${reconnectAttempt})` : 'Disconnected'}
          </Text>
        </View>
      </View>

      {!!connectionError && (
        <View data-testid="wb-error-banner" testID="wb-error-banner" style={{ backgroundColor: (globalThis as any).__alphaColor(C.error, '14'), borderBottomWidth: 1, borderBottomColor: (globalThis as any).__alphaColor(C.error, '45'), paddingHorizontal: 10, paddingVertical: 6 }}>
          <Text data-testid="wb-error-text" testID="wb-error-text" style={{ color: C.error, fontSize: 11, fontWeight: '600' }}>{connectionError}</Text>
        </View>
      )}

      {/* Canvas */}
      <View style={{ flex: 1 }}>
        {/* @ts-ignore - web-only canvas */}
        <canvas
          ref={canvasRef}
          width={isWide ? 800 : 600}
          height={isWide ? 500 : 350}
          style={{ width: '100%', height: '100%', cursor: tool === 'eraser' ? 'crosshair' : 'default' }}
          onMouseDown={onMouseDown as any}
          onMouseMove={onMouseMove as any}
          onMouseUp={onMouseUp as any}
          onMouseLeave={onMouseUp as any}
        />
      </View>
    </View>
  );
}

/* i18n-probe t('i18n.auto.probe') */
