export const SUBSCRIPTION_RETURN_TOAST_KEY = 'rac:subscription-return-toast';

const FEATURE_LABEL_KEYS: Record<string, { key: string; fallback: string }> = {
  'audio-studio': { key: 'Audio Studio', fallback: 'Audio Studio' },
  'games-station': { key: 'FPS Game', fallback: 'FPS Game' },
  'travel-visa': { key: 'Travel Visa', fallback: 'Travel Visa' },
  'my-podcasts': { key: 'My Podcasts', fallback: 'My Podcasts' },
  'daily-meditation': { key: 'Daily Meditation', fallback: 'Daily Meditation' },
  'sports': { key: 'Sports', fallback: 'Sports' },
  'smart-cars': { key: 'i18n.features.smart-cars.title', fallback: 'Mobility Assistant' },
  'pennypilot': { key: 'pennyPilot.page.title', fallback: 'Money Strategy Hub' },
  'bill-generator': { key: 'billGenerator.title', fallback: 'Bill Generator' },
  'ai-photo': { key: 'aiPhoto.page.title', fallback: 'Image & Design Studio' },
};

export type SubscriptionReturnToastPayload = {
  returnTarget: string;
  destinationLabel: string;
  destinationLabelKey?: string | null;
  destinationLabelFallback?: string | null;
  planName?: string | null;
  actionLabel?: string | null;
  actionLabelKey?: string | null;
  actionLabelFallback?: string | null;
  actionRoute?: string | null;
  toastTitleKey?: string | null;
  toastTitleFallback?: string | null;
  toastMessageKey?: string | null;
  toastMessageFallback?: string | null;
  createdAt?: number;
};

export function buildSubscriptionReturnToastPayload(returnTarget: string, planName?: string | null): SubscriptionReturnToastPayload {
  const action = getActionConfig(returnTarget, planName);
  const destination = getDestinationLabelConfig(returnTarget);
  const destinationLabel = destination.label;
  const message = getMessageConfig(returnTarget, destinationLabel, planName);

  return {
    returnTarget,
    destinationLabel,
    destinationLabelKey: destination.key || null,
    destinationLabelFallback: destination.fallback || null,
    planName: String(planName || '').trim() || null,
    actionLabel: action.actionLabelFallback,
    actionLabelKey: action.actionLabelKey,
    actionLabelFallback: action.actionLabelFallback,
    actionRoute: action.actionRoute,
    toastTitleKey: message.toastTitleKey,
    toastTitleFallback: message.toastTitleFallback,
    toastMessageKey: message.toastMessageKey,
    toastMessageFallback: message.toastMessageFallback,
    createdAt: Date.now(),
  };
}

function titleForPlan(planName?: string | null): { key: string; fallback: string } {
  if (String(planName || '').trim()) {
    const normalizedPlan = String(planName).trim().toUpperCase();
    return {
      key: 'subscriptionReturnToast.title.unlocked',
      fallback: `${normalizedPlan} unlocked`,
    };
  }
  return {
    key: 'subscriptionReturnToast.title.complete',
    fallback: 'Upgrade complete',
  };
}

function getActionConfig(returnTarget: string, planName?: string | null): { actionLabelKey: string; actionLabelFallback: string; actionRoute: string } {
  const normalized = String(returnTarget || '/dashboard').split(/[?#]/)[0] || '/dashboard';

  if (normalized === '/profile' || normalized.startsWith('/edit-profile')) {
    return {
      actionLabelKey: 'subscriptionReturnToast.action.profileSettings',
      actionLabelFallback: 'Profile settings',
      actionRoute: '/edit-profile',
    };
  }

  if (normalized === '/features' || normalized.startsWith('/features/')) {
    return {
      actionLabelKey: 'subscriptionReturnToast.action.explorePremiumTools',
      actionLabelFallback: 'Explore premium tools',
      actionRoute: '/features',
    };
  }

  if (normalized === '/book-meeting' || normalized.startsWith('/book/')) {
    return {
      actionLabelKey: 'subscriptionReturnToast.action.reviewAgenda',
      actionLabelFallback: 'Review agenda',
      actionRoute: '/book-meeting',
    };
  }

  if (String(planName || '').trim()) {
    return {
      actionLabelKey: 'subscriptionReturnToast.action.viewPlanDetails',
      actionLabelFallback: 'View plan details',
      actionRoute: '/subscription/plans',
    };
  }
  return {
    actionLabelKey: 'subscriptionReturnToast.action.paymentHistory',
    actionLabelFallback: 'Payment history',
    actionRoute: '/payment-history',
  };
}

function labelForReturnTarget(path: string): string {
  const normalized = String(path || '/dashboard').split(/[?#]/)[0] || '/dashboard';

  if (normalized === '/dashboard' || normalized === '/home' || normalized === '/(tabs)' || normalized === '/') return 'dashboard';
  if (normalized === '/profile' || normalized.startsWith('/edit-profile')) return 'profile';
  if (normalized === '/book-meeting' || normalized.startsWith('/book/')) return 'booking space';
  if (normalized === '/features') return 'features';
  if (normalized.startsWith('/features/')) {
    const featureSlug = normalized.split('/').filter(Boolean)[1] || 'feature';
    return featureSlug.replace(/[-_]/g, ' ');
  }

  const segment = normalized.split('/').filter(Boolean)[0] || 'workspace';
  return segment.replace(/[-_]/g, ' ');
}

function getDestinationLabelConfig(path: string): { label: string; key?: string; fallback?: string } {
  const normalized = String(path || '/dashboard').split(/[?#]/)[0] || '/dashboard';

  if (normalized.startsWith('/features/')) {
    const featureSlug = normalized.split('/').filter(Boolean)[1] || 'feature';
    const mapped = FEATURE_LABEL_KEYS[featureSlug];
    if (mapped) {
      return {
        label: mapped.fallback,
        key: mapped.key,
        fallback: mapped.fallback,
      };
    }
  }

  return { label: labelForReturnTarget(path) };
}

function getMessageConfig(returnTarget: string, destinationLabel: string, planName?: string | null): {
  toastTitleKey: string;
  toastTitleFallback: string;
  toastMessageKey: string;
  toastMessageFallback: string;
} {
  const normalized = String(returnTarget || '/dashboard').split(/[?#]/)[0] || '/dashboard';
  const title = titleForPlan(planName);

  if (normalized === '/dashboard' || normalized === '/home' || normalized === '/(tabs)' || normalized === '/') {
    return {
      toastTitleKey: title.key,
      toastTitleFallback: title.fallback,
      toastMessageKey: 'subscriptionReturnToast.message.dashboard',
      toastMessageFallback: 'Your dashboard access is restored and ready to use.',
    };
  }

  if (normalized === '/profile' || normalized.startsWith('/edit-profile')) {
    return {
      toastTitleKey: title.key,
      toastTitleFallback: title.fallback,
      toastMessageKey: 'subscriptionReturnToast.message.profile',
      toastMessageFallback: 'Your profile access is restored, and your settings are ready to review.',
    };
  }

  if (normalized === '/features') {
    return {
      toastTitleKey: title.key,
      toastTitleFallback: title.fallback,
      toastMessageKey: 'subscriptionReturnToast.message.featuresRoot',
      toastMessageFallback: 'Your premium tools are unlocked in Features and ready to explore.',
    };
  }

  if (normalized.startsWith('/features/')) {
    return {
      toastTitleKey: title.key,
      toastTitleFallback: title.fallback,
      toastMessageKey: 'subscriptionReturnToast.message.featuresSubpath',
      toastMessageFallback: `Your upgraded access is ready in ${destinationLabel}.`,
    };
  }

  if (normalized === '/book-meeting' || normalized.startsWith('/book/')) {
    return {
      toastTitleKey: title.key,
      toastTitleFallback: title.fallback,
      toastMessageKey: 'subscriptionReturnToast.message.booking',
      toastMessageFallback: 'Your booking space is restored so you can continue planning right away.',
    };
  }

  return {
    toastTitleKey: title.key,
    toastTitleFallback: title.fallback,
    toastMessageKey: 'subscriptionReturnToast.message.fallback',
    toastMessageFallback: `Your access is restored in ${destinationLabel} and ready to use.`,
  };
}

export function stashSubscriptionReturnToast(returnTarget: string, planName?: string | null) {
  if (typeof window === 'undefined') return;
  try {
    window.sessionStorage.setItem(SUBSCRIPTION_RETURN_TOAST_KEY, JSON.stringify(buildSubscriptionReturnToastPayload(returnTarget, planName)));
  } catch {
    // noop
  }
}

export function consumeSubscriptionReturnToast(): null | SubscriptionReturnToastPayload {
  if (typeof window === 'undefined') return null;
  try {
    const raw = window.sessionStorage.getItem(SUBSCRIPTION_RETURN_TOAST_KEY);
    if (!raw) return null;
    window.sessionStorage.removeItem(SUBSCRIPTION_RETURN_TOAST_KEY);
    const parsed = JSON.parse(raw);
    return {
      returnTarget: String(parsed?.returnTarget || '/dashboard'),
      destinationLabel: String(parsed?.destinationLabel || 'workspace'),
      destinationLabelKey: parsed?.destinationLabelKey ? String(parsed.destinationLabelKey) : null,
      destinationLabelFallback: parsed?.destinationLabelFallback ? String(parsed.destinationLabelFallback) : null,
      planName: parsed?.planName ? String(parsed.planName) : null,
      actionLabel: parsed?.actionLabel ? String(parsed.actionLabel) : null,
      actionLabelKey: parsed?.actionLabelKey ? String(parsed.actionLabelKey) : null,
      actionLabelFallback: parsed?.actionLabelFallback ? String(parsed.actionLabelFallback) : null,
      actionRoute: parsed?.actionRoute ? String(parsed.actionRoute) : null,
      toastTitleKey: parsed?.toastTitleKey ? String(parsed.toastTitleKey) : null,
      toastTitleFallback: parsed?.toastTitleFallback ? String(parsed.toastTitleFallback) : null,
      toastMessageKey: parsed?.toastMessageKey ? String(parsed.toastMessageKey) : null,
      toastMessageFallback: parsed?.toastMessageFallback ? String(parsed.toastMessageFallback) : null,
      createdAt: Number(parsed?.createdAt || Date.now()),
    };
  } catch {
    return null;
  }
}