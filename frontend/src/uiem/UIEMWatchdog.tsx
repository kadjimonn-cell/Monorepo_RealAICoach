/**
 * Root-level error boundary.
 * UIEM Watchdog — Render loop & crash protection.
 * Detects infinite render loops, rapid re-renders, and recursive calls.
 * Wraps the entire app tree to catch and stop runaway components.
 *
 * This file runs BEFORE ThemeContext mounts (it catches render errors at
 * the React tree root), so it cannot consume theme colors. The hardcoded
 * dark palette + red icon ring are an intentional always-dark "crash"
 * surface so users instantly recognise this as a system recovery overlay
 * and not normal UI.
 */
import React, { Component, useRef, useCallback } from 'react';
import { View, Text } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { resolveRuntimeBaseUrl } from '../utils/runtimeBaseUrl';
import { handleAppRecoverableError } from '../utils/appRecoverableError';

// ── Class-based Error Boundary for render crashes ──
interface WatchdogState { hasCrash: boolean; error: string; component: string; }

export class UIEMWatchdog extends Component<{ children: React.ReactNode }, WatchdogState> {
  state: WatchdogState = { hasCrash: false, error: '', component: '' };

  static getDerivedStateFromError(error: Error): Partial<WatchdogState> {
    const isRenderLoop = error.message?.includes('Maximum update depth') ||
      error.message?.includes('Too many re-renders') ||
      error.message?.includes('Rendered fewer hooks') ||
      error.message?.includes('Rendered more hooks');

    return {
      hasCrash: true,
      error: error.message?.substring(0, 200) || 'Unknown render error',
      component: isRenderLoop ? 'render-loop-detected' : 'crash-detected',
    };
  }

  componentDidCatch(error: Error) {
    // Log to UIEM backend
    const API = resolveRuntimeBaseUrl();
    try {
      fetch(`${API}/api/admin/uiem/log`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          component: 'UIEMWatchdog',
          layer: 'state',
          error_type: 'render_crash',
          message: error.message?.substring(0, 300) || 'Unknown',
          severity: 'critical',
          pathname: typeof window !== 'undefined' ? window.location?.pathname : '',
        }),
        keepalive: true,
      }).catch(() => {});
    } catch (error) { handleAppRecoverableError({ scope: 'src/uiem/UIEMWatchdog.tsx#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
  }

  render() {
    if (this.state.hasCrash) {
      return (
        <View style={{
          flex: 1, alignItems: 'center', justifyContent: 'center',
          backgroundColor: 'rgb(15,22,35)', padding: 32,
        }}>
          <View style={{
            backgroundColor: 'rgb(26,35,50)', borderRadius: 16, padding: 24,
            maxWidth: 420, width: '100%', alignItems: 'center', gap: 12,
            borderWidth: 1, borderColor: 'rgb(42,58,78)',
          }}>
            <View style={{
              width: 48, height: 48, borderRadius: 24,
              backgroundColor: 'rgb(127,29,29)', alignItems: 'center', justifyContent: 'center',
            }}>
              <Ionicons name="shield-half" size={24} color="rgb(254,202,202)" />
            </View>
            <Text style={{ color: 'rgb(241,245,249)', fontSize: 16, fontWeight: '800', textAlign: 'center' }}>
              Render Loop Blocked
            </Text>
            <Text style={{ color: 'rgb(148,163,184)', fontSize: 12, textAlign: 'center' }}>
              UIEM Watchdog stopped a component that was causing instability.
            </Text>
            <View style={{
              backgroundColor: 'rgb(15,23,42)', borderRadius: 8, padding: 10, width: '100%', // @theme-ok crash-overlay (UIEM watchdog runs on pre-theme error boundary)
            }}>
              <Text style={{ color: 'rgb(100,116,139)', fontSize: 9, fontFamily: 'monospace' }}>
                {this.state.error}
              </Text>
            </View>
            <Text
              style={{ color: 'rgb(13,148,136)', fontSize: 12, fontWeight: '700', marginTop: 8 }}
              onPress={() => {
                this.setState({ hasCrash: false, error: '', component: '' });
              }}
            >
              Retry Render
            </Text>
          </View>
        </View>
      );
    }
    return this.props.children;
  }
}

// ── Hook for detecting rapid re-renders in individual components ──
const RENDER_THRESHOLD = 30; // max renders per second
const RENDER_WINDOW = 1000; // 1 second window

export function useRenderGuard(componentName: string) {
  const renderCountRef = useRef(0);
  const windowStartRef = useRef(Date.now());
  const blockedRef = useRef(false);

  const checkRenderRate = useCallback(() => {
    const now = Date.now();
    if (now - windowStartRef.current > RENDER_WINDOW) {
      renderCountRef.current = 0;
      windowStartRef.current = now;
      blockedRef.current = false;
    }
    renderCountRef.current++;

    if (renderCountRef.current > RENDER_THRESHOLD) {
      if (!blockedRef.current) {
        blockedRef.current = true;
        console.error(`[UIEM Watchdog] Render loop risk at ${componentName}: ${renderCountRef.current} renders/sec`);
      }
      return true; // blocked
    }
    return false; // ok
  }, [componentName]);

  return { checkRenderRate, isBlocked: blockedRef.current };
}
