import React, { Component, ErrorInfo } from 'react';
import { View, Text, TouchableOpacity, StyleSheet, Platform } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { recordShellHealthMetric } from '../services/shellHealthMonitor';
import { reportClientCrash } from '../services/clientErrorReporter';
import LanguageContext from '../i18n/LanguageContext';
import { handleAppRecoverableError } from '../utils/appRecoverableError';

interface Props {
  children: React.ReactNode;
  /** Stable id of the panel/route — used to rank top broken panels in Ops Console. */
  panelId?: string;
  /** Human-readable name for the panel. Shown in the admin widget. */
  panelName?: string;
}
interface State { hasError: boolean; error: Error | null; autoRecoveryLocked: boolean; }

const HOOKS_ERROR_PATTERNS = [
  'Rendered fewer hooks than expected',
  'Rendered more hooks than expected',
  'React has detected a change in the order of Hooks',
];

function isHooksViolation(error: Error | null): boolean {
  if (!error?.message) return false;
  return HOOKS_ERROR_PATTERNS.some(p => error.message.includes(p));
}

/**
 * Auto-recovery key in sessionStorage tracks reload attempts.
 * On first hooks violation → auto-reload (user sees brief flash, not error page).
 * On repeated failure → show manual recovery UI to prevent infinite loops.
 */
const RECOVERY_KEY = 'rac_auto_recovery';
const RECOVERY_WINDOW_MS = 30000; // Block repeat auto-reloads on slow-crash loops
const AUTO_RECOVERY_ATTEMPTS_KEY = 'rac_auto_recovery_attempts';
const MAX_AUTO_RELOAD_ATTEMPTS = 3;

function tryConsumeAutoReloadAttempt(): { allowed: boolean; attempts: number } {
  try {
    const current = parseInt(sessionStorage.getItem(AUTO_RECOVERY_ATTEMPTS_KEY) || '0', 10);
    const attempts = Number.isFinite(current) && current > 0 ? current + 1 : 1;
    sessionStorage.setItem(AUTO_RECOVERY_ATTEMPTS_KEY, String(attempts));
    return { allowed: attempts <= MAX_AUTO_RELOAD_ATTEMPTS, attempts };
  } catch {
    // sessionStorage unavailable: keep behavior functional without hard-locking
    return { allowed: true, attempts: 1 };
  }
}

function resetAutoReloadAttempts() {
  try {
    sessionStorage.removeItem(AUTO_RECOVERY_ATTEMPTS_KEY);
  } catch (error) { handleAppRecoverableError({ scope: 'src/components/ErrorBoundary.tsx#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
}

function clearStaleBrowserCaches() {
  try {
    const protectedKeys = new Set(['session_token', 'cache_schema_version']);
    Object.keys(localStorage).forEach((key) => {
      if (protectedKeys.has(key)) return;
      if (key.startsWith('legacy_') || key.startsWith('cache_') || key.startsWith('stale_')) {
        localStorage.removeItem(key);
      }
    });

    if ('caches' in window) {
      window.caches.keys().then((keys) => Promise.all(keys.map((k) => window.caches.delete(k)))).catch(() => {});
    }
  } catch (error) { handleAppRecoverableError({ scope: 'src/components/ErrorBoundary.tsx#catch2', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false, error: null, autoRecoveryLocked: false };

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error, autoRecoveryLocked: false };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    if (__DEV__) console.error('ErrorBoundary caught:', error, info);

    // Fire-and-forget crash report so Ops Console can rank top broken panels
    try {
      reportClientCrash({
        panelId: this.props.panelId,
        panelName: this.props.panelName,
        message: error?.message || 'Unknown error',
        stack: error?.stack,
        componentStack: info?.componentStack || undefined,
      });
    } catch (error) { handleAppRecoverableError({ scope: 'src/components/ErrorBoundary.tsx#catch3', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }

    // Auto-recovery: If this is a React hooks violation on web, try a one-time reload
    if (Platform.OS === 'web' && isHooksViolation(error)) {
      try {
        const now = Date.now();
        const lastAttempt = parseInt(sessionStorage.getItem(RECOVERY_KEY) || '0', 10);
        const elapsed = now - lastAttempt;

        if (elapsed > RECOVERY_WINDOW_MS) {
          const attemptInfo = tryConsumeAutoReloadAttempt();
          if (attemptInfo.allowed) {
            // Attempt bounded auto-reload for this browser session.
            sessionStorage.setItem(RECOVERY_KEY, String(now));
            recordShellHealthMetric('route_recoveries', {
              mode: 'auto_reload',
              reason: 'hooks_violation',
              attempts: attemptInfo.attempts,
            });
            console.warn('[ErrorBoundary] Auto-recovering from hooks violation — reloading...');
            window.location.reload();
            return; // reload is async; prevent further processing
          }
          recordShellHealthMetric('route_recoveries', {
            mode: 'auto_reload_blocked',
            reason: 'hooks_violation_attempt_limit',
            attempts: attemptInfo.attempts,
          });
          this.setState({ autoRecoveryLocked: true });
          console.warn('[ErrorBoundary] Auto-recovery attempt limit reached — showing static recovery screen');
        }
        // If we already reloaded recently, fall through to show manual UI
        console.warn('[ErrorBoundary] Hooks violation persists after auto-recovery — showing manual UI');
      } catch (error) { handleAppRecoverableError({ scope: 'src/components/ErrorBoundary.tsx#catch4', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
    }

    if (Platform.OS === 'web' && !isHooksViolation(error)) {
      try {
        clearStaleBrowserCaches();
        recordShellHealthMetric('route_recoveries', {
          mode: 'manual_required',
          reason: 'general_runtime_error',
        });
      } catch (error) { handleAppRecoverableError({ scope: 'src/components/ErrorBoundary.tsx#catch5', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
    }
  }

  handleReset = () => {
    this.setState({ hasError: false, error: null, autoRecoveryLocked: false });
  };

  handleReload = () => {
    if (Platform.OS === 'web') {
      try { sessionStorage.removeItem(RECOVERY_KEY); } catch (error) { handleAppRecoverableError({ scope: 'src/components/ErrorBoundary.tsx#catch6', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
      resetAutoReloadAttempts();
      recordShellHealthMetric('route_recoveries', { mode: 'manual_reload', reason: 'error_boundary_reload' });
      window.location.reload();
    } else {
      this.handleReset();
    }
  };

  render() {
    if (!this.state.hasError) return this.props.children;

    return (
      <LocalizedErrorBoundaryCard
        error={this.state.error}
        autoRecoveryLocked={this.state.autoRecoveryLocked}
        onReload={this.handleReload}
        onRetry={this.handleReset}
      />
    );
  }
}

function LocalizedErrorBoundaryCard({
  error,
  autoRecoveryLocked,
  onReload,
  onRetry,
}: {
  error: Error | null;
  autoRecoveryLocked: boolean;
  onReload: () => void;
  onRetry: () => void;
}) {
  const languageContext = React.useContext(LanguageContext as any);

  const tx = React.useCallback((key: string, fallback: string) => {
    try {
      const translated = languageContext?.t?.(key);
      if (!translated || translated === key) return fallback;
      return translated;
    } catch {
      return fallback;
    }
  }, [languageContext]);

  const titleText = tx('common.error', 'Something went wrong');
  const descText = autoRecoveryLocked
    ? tx(
      'errorBoundary.staticRecoveryDescription',
      'Automatic reload is paused after multiple failures. Please use manual recovery options below.'
    )
    : tx('errorBoundary.description', 'An unexpected error occurred. Please try again or reload the page.');
  const errorDetails = (error?.message && String(error.message).trim())
    ? String(error.message).trim().slice(0, 320)
    : tx('errorBoundary.noDetails', 'No additional error details were provided.');
  const reloadText = tx('errorBoundary.reload', 'Reload Page');
  const retryText = tx('common.tryAgain', 'Try Again');

    return (
      <View style={s.root} data-testid="error-boundary" testID="error-boundary">
        <View style={s.card}>
          <View style={s.iconWrap}>
            <Ionicons name="warning-outline" size={36} color={'var(--app-primary)' as any} />
          </View>
          <Text style={s.title} data-testid="error-boundary-title" testID="error-boundary-title">{titleText}</Text>
          <Text style={s.desc}>{descText}</Text>
          {autoRecoveryLocked && (
            <Text
              style={s.lockedNote}
              data-testid="error-boundary-static-recovery-note"
              testID="error-boundary-static-recovery-note"
            >
              {tx('errorBoundary.staticRecoveryNote', 'Auto-reload limit reached for this session.')}
            </Text>
          )}
          <View style={s.errorBox} data-testid="error-boundary-message-box" testID="error-boundary-message-box">
            <Text
              style={s.errorLabel}
              data-testid="error-boundary-message-label"
              testID="error-boundary-message-label"
            >
              {tx('errorBoundary.errorLabel', 'Error details')}
            </Text>
            <Text
              style={s.errorText}
              numberOfLines={5}
              data-testid="error-boundary-message"
              testID="error-boundary-message"
            >
              {errorDetails}
            </Text>
          </View>
          <View style={s.btns}>
            <TouchableOpacity style={s.btnPrimary} onPress={onReload} data-testid="error-boundary-reload" testID="error-boundary-reload" accessibilityRole="button">
              <Ionicons name="refresh" size={16} color={'var(--app-primary-text)' as any} />
              <Text style={s.btnPrimaryText}>{reloadText}</Text>
            </TouchableOpacity>
            <TouchableOpacity style={s.btnGhost} onPress={onRetry} data-testid="error-boundary-retry" testID="error-boundary-retry" accessibilityRole="button">
              <Text style={s.btnGhostText}>{retryText}</Text>
            </TouchableOpacity>
          </View>
        </View>
      </View>
    );
}

const s = StyleSheet.create({
  root: { flex: 1, backgroundColor: 'var(--app-bg)' as any, justifyContent: 'center', alignItems: 'center', padding: 24 }, // @theme-ok css-var-fallback (runtime override sets --app-bg from theme)
  card: { maxWidth: 420, width: '100%', backgroundColor: 'var(--app-card-bg)' as any, borderRadius: 22, padding: 40, alignItems: 'center', borderWidth: 1, borderColor: 'var(--app-border)' as any },
  iconWrap: { width: 72, height: 72, borderRadius: 36, backgroundColor: 'rgba(20,184,166,0.12)', alignItems: 'center', justifyContent: 'center', marginBottom: 20 },
  title: { color: 'var(--app-text)' as any, fontSize: 22, fontWeight: '800', textAlign: 'center', marginBottom: 10, letterSpacing: -0.3 },
  desc: { color: 'var(--app-text-sec)' as any, fontSize: 14, lineHeight: 22, textAlign: 'center', marginBottom: 20 },
  errorBox: { width: '100%', backgroundColor: 'rgba(220,38,38,0.08)', borderRadius: 12, padding: 12, marginBottom: 20, borderWidth: 1, borderColor: 'rgba(220,38,38,0.18)' },
  errorLabel: { color: 'var(--app-text)' as any, fontSize: 11, fontWeight: '700', letterSpacing: 0.3, marginBottom: 6, textTransform: 'uppercase' },
  errorText: { color: 'var(--app-text-sec)' as any, fontSize: 12, fontFamily: Platform.OS === 'web' ? 'monospace' : undefined },
  lockedNote: { color: 'var(--app-warning)' as any, fontSize: 12, fontWeight: '700', marginBottom: 14 },
  btns: { width: '100%', gap: 10 },
  btnPrimary: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, backgroundColor: 'var(--app-primary)' as any, paddingVertical: 14, borderRadius: 12 },
  btnPrimaryText: { color: 'var(--app-primary-text)' as any, fontSize: 14, fontWeight: '700' },
  btnGhost: { alignItems: 'center', paddingVertical: 12, borderRadius: 12, borderWidth: 1, borderColor: 'var(--app-border)' as any },
  btnGhostText: { color: 'var(--app-text-sec)' as any, fontSize: 14, fontWeight: '600' },
});

/* i18n-probe t('i18n.auto.probe') */
