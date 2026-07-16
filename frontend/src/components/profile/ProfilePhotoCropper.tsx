import React from 'react';
import { Platform } from 'react-native';

interface ProfilePhotoCropperProps {
  visible: boolean;
  rawImageSrc: string | null;
  canvasRef: React.RefObject<HTMLCanvasElement | null>;
  zoom: number;
  setZoom: (z: number) => void;
  rotation: number;
  setRotation: (r: number) => void;
  onApply: () => void;
  onCancel: () => void;
  primaryColor: string;
}

export function ProfilePhotoCropper({
  visible, rawImageSrc, canvasRef,
  zoom, setZoom, rotation, setRotation,
  onApply, onCancel, primaryColor,
}: ProfilePhotoCropperProps) {
  if (Platform.OS !== 'web' || !visible || !rawImageSrc) return null;

  return (
    <div style={{
      position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
      backgroundColor: 'rgba(0,0,0,0.9)', zIndex: 9999,
      display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
    } as any} data-testid="crop-modal">
      <div style={{ color: 'var(--app-primary-text)', fontSize: 18, fontWeight: '700', marginBottom: 16, textAlign: 'center', fontFamily: '-apple-system, BlinkMacSystemFont, sans-serif' } as any}>
        Crop Your Photo
      </div>
      <div style={{
        position: 'relative',
        width: 'min(90vw, 400px)',
        aspectRatio: '1 / 1',
        maxHeight: '52vh',
        borderRadius: 16,
        overflow: 'hidden',
        backgroundColor: 'var(--app-bg)',
      } as any}>
        <canvas
          ref={(el: any) => { (canvasRef as any).current = el; }}
          width={380} height={380}
          style={{ width: '100%', height: '100%', display: 'block' } as any}
        />
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 14, marginTop: 20, width: 'min(90vw, 380px)' } as any}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, width: '100%' } as any}>
          <span style={{ color: 'var(--app-text-muted)', fontSize: 12, fontWeight: '600', width: 50, fontFamily: '-apple-system, sans-serif' } as any}>Zoom</span>
          <input type="range" min={1} max={3} step={0.05} value={zoom} aria-label="Text input" onChange={(e: any) => setZoom(Number(e.target.value))}
            style={{ flex: 1, accentColor: primaryColor, cursor: 'pointer', height: 6 } as any} data-testid="crop-zoom-slider" />
          <span style={{ color: 'var(--app-text-sec)', fontSize: 11, fontFamily: 'monospace', width: 36, textAlign: 'right' } as any}>{zoom.toFixed(1)}x</span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, width: '100%' } as any}>
          <span style={{ color: 'var(--app-text-muted)', fontSize: 12, fontWeight: '600', width: 50, fontFamily: '-apple-system, sans-serif' } as any}>Rotate</span>
          <input type="range" min={0} max={360} step={1} value={rotation} aria-label="Text input" onChange={(e: any) => setRotation(Number(e.target.value))}
            style={{ flex: 1, accentColor: primaryColor, cursor: 'pointer', height: 6 } as any} data-testid="crop-rotate-slider" />
          <span style={{ color: 'var(--app-text-sec)', fontSize: 11, fontFamily: 'monospace', width: 36, textAlign: 'right' } as any}>{rotation}°</span>
        </div>
        <div style={{ display: 'flex', gap: 8, justifyContent: 'center' } as any}>
          {[0, 90, 180, 270].map(deg => (
            <button key={deg} onClick={() => setRotation(deg)}
              style={{ background: rotation === deg ? primaryColor : 'rgba(255,255,255,0.1)', color: rotation === deg ? 'var(--app-primary-text)' : 'var(--app-text-muted)', border: 'none', borderRadius: 8, padding: '6px 14px', fontSize: 12, fontWeight: '600', cursor: 'pointer', transition: 'all 0.2s', fontFamily: '-apple-system, sans-serif' } as any}
              data-testid={`crop-rotate-${deg}`}>{deg}°</button>
          ))}
        </div>
        <div style={{ display: 'flex', gap: 12, marginTop: 8, width: '100%' } as any}>
          <button onClick={onCancel}
            style={{ flex: 1, padding: '12px 0', borderRadius: 12, background: 'rgba(255,255,255,0.08)', color: 'var(--app-text-sec)', border: '1px solid rgba(255,255,255,0.15)', fontSize: 14, fontWeight: '600', cursor: 'pointer', fontFamily: '-apple-system, sans-serif' } as any}
            data-testid="crop-cancel-btn">Cancel</button>
          <button onClick={onApply}
            style={{ flex: 1, padding: '12px 0', borderRadius: 12, background: primaryColor, color: 'var(--app-primary-text)', border: 'none', fontSize: 14, fontWeight: '700', cursor: 'pointer', fontFamily: '-apple-system, sans-serif', boxShadow: `0 4px 20px ${primaryColor}40` } as any}
            data-testid="crop-apply-btn">Apply & Upload</button>
        </div>
      </div>
    </div>
  );
}

/* i18n-probe t('i18n.auto.probe') */
