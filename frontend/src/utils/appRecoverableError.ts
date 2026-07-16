import { Alert, Platform } from 'react-native';
import { reportClientCrash } from '../services/clientErrorReporter';

type RecoverableErrorOptions = {
  scope?: string;
  error?: any;
  message?: string;
  onRetry?: () => void;
  setError?: (message: string) => void;
  notifyMode?: 'auto' | 'silent' | 'dialog';
  userInitiated?: boolean;
};

const DEDUPE_WINDOW_MS = 20_000;
const lastShownByScope = new Map<string, number>();
const GLOBAL_NOTIFY_WINDOW_MS = 8_000;
const MESSAGE_NOTIFY_WINDOW_MS = 45_000;
const lastShownByMessage = new Map<string, number>();
let lastGlobalNotifyAt = 0;

const shouldNotify = (scope: string, message: string) => {
  const now = Date.now();

  if (now - lastGlobalNotifyAt < GLOBAL_NOTIFY_WINDOW_MS) return false;

  const last = lastShownByScope.get(scope) || 0;
  if (now - last < DEDUPE_WINDOW_MS) return false;

  const messageKey = String(message || '').trim().toLowerCase();
  if (messageKey) {
    const messageLast = lastShownByMessage.get(messageKey) || 0;
    if (now - messageLast < MESSAGE_NOTIFY_WINDOW_MS) return false;
    lastShownByMessage.set(messageKey, now);
  }

  lastShownByScope.set(scope, now);
  lastGlobalNotifyAt = now;
  return true;
};

const normalizeRecoverableErrorArgs = (
  optionsOrError: RecoverableErrorOptions | any,
  legacyMessage?: string,
): RecoverableErrorOptions => {
  if (
    optionsOrError
    && typeof optionsOrError === 'object'
    && (
      'scope' in optionsOrError
      || 'error' in optionsOrError
      || 'message' in optionsOrError
      || 'onRetry' in optionsOrError
      || 'setError' in optionsOrError
      || 'notifyMode' in optionsOrError
      || 'userInitiated' in optionsOrError
    )
  ) {
    return optionsOrError as RecoverableErrorOptions;
  }

  return {
    scope: 'legacy-unknown-scope',
    error: optionsOrError,
    message: legacyMessage,
  };
};

const resolveWebNotifyMode = (options: RecoverableErrorOptions): 'silent' | 'dialog' => {
  const mode = options.notifyMode || 'auto';
  if (mode === 'silent' || mode === 'dialog') return mode;

  // Auto mode: avoid blocking dialogs for background/system flows.
  if (options.userInitiated && options.onRetry) return 'dialog';
  return 'silent';
};

export const handleAppRecoverableError = (
  optionsOrError: RecoverableErrorOptions | any,
  legacyMessage?: string,
) => {
  const {
    scope,
    error,
    message,
    onRetry,
    setError,
    notifyMode,
    userInitiated,
  } = normalizeRecoverableErrorArgs(optionsOrError, legacyMessage);

  const safeScope = String(scope || 'unknown-scope');
  const fallbackMessage = message || 'Something went wrong. Please retry.';

  reportClientCrash({
    panelId: `recoverable:${safeScope}`,
    panelName: 'AppRecoverableError',
    message: fallbackMessage,
    stack: String(error?.stack || error?.message || ''),
  });

  setError?.(fallbackMessage);
  if (!shouldNotify(safeScope, fallbackMessage)) return fallbackMessage;

  if (Platform.OS === 'web' && typeof window !== 'undefined') {
    const mode = resolveWebNotifyMode({
      scope: safeScope,
      error,
      message: fallbackMessage,
      onRetry,
      setError,
      notifyMode,
      userInitiated,
    });

    if (mode === 'dialog') {
      const retry = window.confirm(`${fallbackMessage}\n\nRetry now?`);
      if (retry) {
        try {
          onRetry?.();
        } catch {
          // best-effort retry only
        }
      }
    } else {
      try {
        // Non-blocking signal for web UI/telemetry listeners.
        window.dispatchEvent(new CustomEvent('app-recoverable-error', {
          detail: {
            scope: safeScope,
            message: fallbackMessage,
            has_retry: Boolean(onRetry),
          },
        }));
      } catch {
        // best-effort only
      }
    }

    return fallbackMessage;
  }

  Alert.alert(
    'Action failed',
    fallbackMessage,
    [
      { text: 'Dismiss', style: 'cancel' },
      {
        text: 'Retry',
        onPress: () => {
          try {
            onRetry?.();
          } catch {
            // best-effort retry only
          }
        },
      },
    ],
    { cancelable: true }
  );

  return fallbackMessage;
};
