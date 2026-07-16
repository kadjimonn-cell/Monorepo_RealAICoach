import fs from 'fs';
import path from 'path';

const read = (relativePath: string) => fs.readFileSync(path.join(process.cwd(), relativePath), 'utf8');
const readBackend = (relativePath: string) => fs.readFileSync(path.join(process.cwd(), '..', 'backend', relativePath), 'utf8');

describe('home dashboard auth lock contract', () => {
  it('keeps dashboard entry routes on neutral secure-session loading instead of dashboard skeletons', () => {
    const dashboardRoute = read('app/dashboard.tsx');
    const homeRoute = read('app/home.tsx');
    const tabsIndexRoute = read('app/(tabs)/index.tsx');
    const tabsLayoutRoute = read('app/(tabs)/_layout.tsx');
    const protectedRouteGate = read('src/components/auth/ProtectedRouteGate.tsx');

    expect(protectedRouteGate).toContain('SecureSessionLoadingScreen');
    expect(dashboardRoute).toContain('ProtectedRouteGate');
    expect(homeRoute).toContain('ProtectedRouteGate');
    expect(tabsIndexRoute).toContain('ProtectedRouteGate');
    expect(tabsLayoutRoute).toContain('ProtectedRouteGate');
    expect(homeRoute).toContain('requireFreshServerSession');
    expect(dashboardRoute).toContain('requireFreshServerSession');
    expect(tabsLayoutRoute).toContain('requireFreshServerSession');

    expect(dashboardRoute).not.toContain('return <HomeSkeleton />');
    expect(homeRoute).not.toContain('return <HomeSkeleton />');
  });

  it('requires a live server-authenticated session before unlocking dashboard entry routes', () => {
    const protectedRouteGate = read('src/components/auth/ProtectedRouteGate.tsx');

    expect(protectedRouteGate).toContain('type ServerSessionGateState = \'idle\' | \'verifying\' | \'verified\' | \'blocked\';');
    expect(protectedRouteGate).toContain('requireFreshServerSession?: boolean;');
    expect(protectedRouteGate).toContain('const { probeServerSession, refreshUser } = useAuth();');
    expect(protectedRouteGate).toContain('const shouldVerifyServerSession = useMemo(');
    expect(protectedRouteGate).toContain('const firstProbe = await probeServerSession();');
    expect(protectedRouteGate).toContain('await refreshUser();');
    expect(protectedRouteGate).toContain('const secondProbe = await probeServerSession();');
    expect(protectedRouteGate).toContain("setServerSessionGateState('blocked');");
    expect(protectedRouteGate).toContain('Please wait while we confirm your current dashboard access.');
  });

  it('does not promote persisted auth snapshots into authenticated web sessions during bootstrap or refresh', () => {
    const authContext = read('src/context/AuthContext.tsx');

    expect(authContext).toContain('Never promote persisted snapshots into authenticated session state');
    expect(authContext).not.toContain('} else if (snapshot && !hasAdminConsoleVisibility(snapshot as any)) {');
    expect(authContext).not.toContain('if (snapshot) {\n        setUser(snapshot);');
  });

  it('uses the shared secure-session boundary across protected layouts and shells', () => {
    const appShell = read('src/components/AppShell.tsx');
    const featuresLayout = read('app/features/_layout.tsx');
    const notFoundRoute = read('app/+not-found.tsx');
    const profileRoute = read('app/(tabs)/profile.tsx');
    const bookMeetingRoute = read('app/book-meeting.tsx');
    const i18nDriftRoute = read('app/i18n-drift-dashboard.tsx');
    const protectedRouteGate = read('src/components/auth/ProtectedRouteGate.tsx');

    expect(protectedRouteGate).toContain('SecureSessionLoadingScreen');
    expect(protectedRouteGate).toContain("buildWelcomeAuthRedirect(returnTo, 'unauthenticated')");

    expect(appShell).toContain('ProtectedRouteGate');
    expect(appShell).toContain('returnTo={safeReturnTo}');

    expect(featuresLayout).toContain('ProtectedRouteGate');
    expect(featuresLayout).toContain('returnTo="/features"');

    expect(notFoundRoute).toContain('ProtectedRouteGate');
    expect(notFoundRoute).toContain("returnTo={pathname || '/dashboard'}");

    expect(profileRoute).toContain('ProtectedRouteGate');
    expect(profileRoute).toContain('returnTo="/profile"');
    expect(profileRoute).not.toContain('profile.guest.title');

    expect(bookMeetingRoute).toContain('ProtectedRouteGate');
    expect(bookMeetingRoute).toContain('returnTo="/book-meeting"');
    expect(bookMeetingRoute).not.toContain('agenda-guest-notice');
    const bookMeetingPreHookBlock = bookMeetingRoute.split('const refreshBestSlotRewardBadge = useCallback')[0];
    expect(bookMeetingPreHookBlock).not.toContain("if (authLoading) return <SecureSessionLoadingScreen />;");
    expect(bookMeetingPreHookBlock).not.toContain("if (!user?.user_id) return <Redirect href={buildWelcomeAuthRedirect('/book-meeting', 'unauthenticated')} />;");

    expect(i18nDriftRoute).toContain('ProtectedRouteGate');
    expect(i18nDriftRoute).toContain('returnTo="/i18n-drift-dashboard"');
    expect(i18nDriftRoute).not.toContain('Please sign in to view i18n drift trends.');
  });

  it('delays the checking-access overlay briefly for authenticated access-session bootstraps', () => {
    const routeAccessGuard = read('src/components/RouteAccessGuard.tsx');

    expect(routeAccessGuard).toContain('const AUTHENTICATED_ACCESS_OVERLAY_DELAY_MS = 350;');
    expect(routeAccessGuard).toContain('const accessOverlayDelayStartedAtRef = useRef<number>(0);');
    expect(routeAccessGuard).toContain('if (user && !authLoading && accessLoading && !accessOverlayDelayStartedAtRef.current) {');
    expect(routeAccessGuard).toContain('if (authenticatedAccessOverlayElapsed < AUTHENTICATED_ACCESS_OVERLAY_DELAY_MS) {');
    expect(routeAccessGuard).toContain('setOverlayState(null);');
  });

  it('uses calmer authenticated transition copy for post-login access bootstrap', () => {
    const routeAccessGuard = read('src/components/RouteAccessGuard.tsx');

    expect(routeAccessGuard).toContain('function getAuthenticatedTransitionCopy(pathname: string)');
    expect(routeAccessGuard).toContain("title: 'Almost to your dashboard'");
    expect(routeAccessGuard).toContain("body: 'Syncing your dashboard access for a smooth handoff.'");
    expect(routeAccessGuard).toContain("title: 'Almost to your profile'");
    expect(routeAccessGuard).toContain("title: 'Almost to your features'");
    expect(routeAccessGuard).toContain("title: 'Almost to your booking space'");
    expect(routeAccessGuard).toContain("title: 'Almost to your plan details'");
    expect(routeAccessGuard).toContain("title: user && !authLoading ? authenticatedTransitionCopy.title : 'Checking access'");
    expect(routeAccessGuard).toContain('? authenticatedTransitionCopy.body');
    expect(routeAccessGuard).toContain("tone: user && !authLoading ? 'polished' : 'neutral'");
    expect(routeAccessGuard).toContain('route-access-guard-status-pill');
    expect(routeAccessGuard).toContain('CONTINUING YOUR SESSION');
  });

  it('passes contextual destination details into subscription upgrade redirects', () => {
    const routeAccessGuard = read('src/components/RouteAccessGuard.tsx');
    const subscriptionPlans = read('app/subscription/plans.tsx');

    expect(routeAccessGuard).toContain('function getUpgradeContextLabel(pathname: string)');
    expect(routeAccessGuard).toContain("return 'dashboard';");
    expect(routeAccessGuard).toContain("return 'profile';");
    expect(routeAccessGuard).toContain("return 'features';");
    expect(routeAccessGuard).toContain("return 'booking space';");
    expect(routeAccessGuard).toContain("return 'plan options';");
    expect(routeAccessGuard).toContain('&upgrade_context=${contextParam}&upgrade_title=${titleParam}');

    expect(subscriptionPlans).toContain('const upgradeContext = useMemo(() => {');
    expect(subscriptionPlans).toContain('const upgradeTitleOverride = useMemo(() => {');
    expect(subscriptionPlans).toContain('const contextualUpgradeTitle = useMemo(() => {');
    expect(subscriptionPlans).toContain('const contextualUpgradeMeta = useMemo(() => {');
    expect(subscriptionPlans).toContain('const contextualUpgradeEyebrow = useMemo(() => {');
    expect(subscriptionPlans).toContain('subscription-contextual-upgrade-pill');
    expect(subscriptionPlans).toContain('PLAN MATCH');
    expect(subscriptionPlans).toContain('Trying to open: ${upgradeContext}');
  });

  it('preserves smart post-upgrade return targets across subscription success flows', () => {
    const subscriptionPlans = read('app/subscription/plans.tsx');
    const subscriptionPayment = read('app/subscription/payment.tsx');
    const subscriptionSuccess = read('app/subscription/success.tsx');
    const paymentResult = read('app/subscription/payment-result.tsx');
    const mobileMoney = read('app/subscription/mobile-money.tsx');
    const returnTargetUtil = read('src/utils/subscriptionReturnTarget.ts');

    expect(returnTargetUtil).toContain('export function normalizeReturnTarget(value: string): string');
    expect(subscriptionPlans).toContain('const resolvedUpgradeReturnTarget = useMemo(() => normalizeReturnTarget(upgradeFromPath || \'/dashboard\'), [upgradeFromPath]);');
    expect(subscriptionPlans).toContain('return_to: resolvedUpgradeReturnTarget');
    expect(subscriptionPayment).toContain("const returnTo = useMemo(() => normalizeReturnTarget(String(params.return_to || '/dashboard')), [params.return_to]);");
    expect(subscriptionPayment).toContain('await refreshAccessControl();');
    expect(subscriptionPayment).toContain('router.replace(returnTo as any)');
    expect(subscriptionSuccess).toContain("const smartReturnTarget = normalizeReturnTarget(String(params.return_to || '/dashboard')); ".trim());
    expect(subscriptionSuccess).toContain('await refreshAccessControl();');
    expect(subscriptionSuccess).toContain('router.replace(smartReturnTarget as any)');
    expect(paymentResult).toContain("const smartReturnTarget = normalizeReturnTarget(String(return_to || '/dashboard')); ".trim());
    expect(paymentResult).toContain('await refreshAccessControl();');
    expect(paymentResult).toContain('router.replace(smartReturnTarget as any)');
    expect(mobileMoney).toContain("const returnTo = useMemo(() => normalizeReturnTarget(String(params.return_to || '/dashboard')), [params.return_to]);");
    expect(mobileMoney).toContain('await refreshAccessControl();');
    expect(mobileMoney).toContain('router.replace(returnTo as any)');
  });

  it('shows a one-time success toast after smart return from an upgrade flow', () => {
    const subscriptionPayment = read('app/subscription/payment.tsx');
    const subscriptionSuccess = read('app/subscription/success.tsx');
    const paymentResult = read('app/subscription/payment-result.tsx');
    const mobileMoney = read('app/subscription/mobile-money.tsx');
    const appShell = read('src/components/AppShell.tsx');
    const realtimeToast = read('src/components/RealtimeToast.tsx');
    const returnToastUtil = read('src/utils/subscriptionReturnToast.ts');

    expect(returnToastUtil).toContain('export const SUBSCRIPTION_RETURN_TOAST_KEY');
    expect(returnToastUtil).toContain('export function stashSubscriptionReturnToast(returnTarget: string, planName?: string | null)');
    expect(returnToastUtil).toContain('export function consumeSubscriptionReturnToast()');
    expect(subscriptionPayment).toContain('stashSubscriptionReturnToast(returnTo, planName)');
    expect(subscriptionSuccess).toContain('stashSubscriptionReturnToast(smartReturnTarget, details?.plan || null)');
    expect(paymentResult).toContain('stashSubscriptionReturnToast(smartReturnTarget, null)');
    expect(mobileMoney).toContain('stashSubscriptionReturnToast(returnTo, planName);');
    expect(appShell).toContain('const payload = consumeSubscriptionReturnToast();');
    expect(appShell).toContain('message: payload.toastMessage || `You’re back in ${payload.destinationLabel}. Your access is ready.`');
    expect(realtimeToast).toContain("success: { icon: 'checkmark-circle'");
  });

  it('adds action-oriented CTA data to restore toasts', () => {
    const returnToastUtil = read('src/utils/subscriptionReturnToast.ts');
    const appShell = read('src/components/AppShell.tsx');
    const realtimeToast = read('src/components/RealtimeToast.tsx');
    const enLocale = read('src/i18n/locales/en.ts');

    expect(returnToastUtil).toContain('function getActionConfig(returnTarget: string, planName?: string | null)');
    expect(returnToastUtil).toContain("actionLabelKey: 'subscriptionReturnToast.action.profileSettings'");
    expect(returnToastUtil).toContain("actionLabelFallback: 'Profile settings'");
    expect(returnToastUtil).toContain("actionRoute: '/edit-profile'");
    expect(returnToastUtil).toContain("actionLabelKey: 'subscriptionReturnToast.action.explorePremiumTools'");
    expect(returnToastUtil).toContain("actionRoute: '/features'");
    expect(returnToastUtil).toContain("actionLabelKey: 'subscriptionReturnToast.action.reviewAgenda'");
    expect(returnToastUtil).toContain("actionRoute: '/book-meeting'");
    expect(returnToastUtil).toContain("actionLabelKey: 'subscriptionReturnToast.action.viewPlanDetails'");
    expect(returnToastUtil).toContain("actionRoute: '/subscription/plans'");
    expect(returnToastUtil).toContain("actionLabelKey: 'subscriptionReturnToast.action.paymentHistory'");
    expect(returnToastUtil).toContain("actionRoute: '/payment-history'");
    expect(returnToastUtil).toContain('const action = getActionConfig(returnTarget, planName);');
    expect(appShell).toContain('const localizedActionLabel = payload.actionLabelKey');
    expect(appShell).toContain("tx(payload.actionLabelKey, payload.actionLabelFallback || payload.actionLabel || 'View details')");
    expect(appShell).toContain('actionLabel: localizedActionLabel');
    expect(appShell).toContain('actionRoute: payload.actionRoute || undefined');
    expect(realtimeToast).toContain('actionLabel?: string;');
    expect(realtimeToast).toContain('actionRoute?: string;');
    expect(realtimeToast).toContain('router.push(t.actionRoute as any);');
    expect(realtimeToast).toContain('toast-action-');
    expect(enLocale).toContain('"subscriptionReturnToast.action.profileSettings": "Profile settings"');
    expect(enLocale).toContain('"subscriptionReturnToast.action.paymentHistory": "Payment history"');
  });

  it('stores deeper destination-aware restore toast copy for restored routes', () => {
    const returnToastUtil = read('src/utils/subscriptionReturnToast.ts');
    const appShell = read('src/components/AppShell.tsx');
    const enLocale = read('src/i18n/locales/en.ts');

    expect(returnToastUtil).toContain('function getMessageConfig(returnTarget: string, destinationLabel: string, planName?: string | null)');
    expect(returnToastUtil).toContain("toastTitleKey: title.key");
    expect(returnToastUtil).toContain("toastTitleFallback: title.fallback");
    expect(returnToastUtil).toContain("toastMessageKey: 'subscriptionReturnToast.message.dashboard'");
    expect(returnToastUtil).toContain("toastMessageKey: 'subscriptionReturnToast.message.profile'");
    expect(returnToastUtil).toContain("toastMessageKey: 'subscriptionReturnToast.message.featuresRoot'");
    expect(returnToastUtil).toContain("toastMessageKey: 'subscriptionReturnToast.message.featuresSubpath'");
    expect(returnToastUtil).toContain("toastMessageKey: 'subscriptionReturnToast.message.booking'");
    expect(returnToastUtil).toContain("toastMessageKey: 'subscriptionReturnToast.message.fallback'");
    expect(returnToastUtil).toContain('toastTitleKey: parsed?.toastTitleKey ? String(parsed.toastTitleKey) : null');
    expect(returnToastUtil).toContain('toastMessageKey: parsed?.toastMessageKey ? String(parsed.toastMessageKey) : null');
    expect(returnToastUtil).toContain('const FEATURE_LABEL_KEYS: Record<string, { key: string; fallback: string }> = {');
    expect(returnToastUtil).toContain("'audio-studio': { key: 'Audio Studio', fallback: 'Audio Studio' }");
    expect(returnToastUtil).toContain("'smart-cars': { key: 'i18n.features.smart-cars.title', fallback: 'Mobility Assistant' }");
    expect(returnToastUtil).toContain('function getDestinationLabelConfig(path: string)');
    expect(returnToastUtil).toContain('destinationLabelKey: destination.key || null');
    expect(returnToastUtil).toContain('destinationLabelFallback: destination.fallback || null');
    expect(appShell).toContain('const localizedTitle = payload.toastTitleKey');
    expect(appShell).toContain('const localizedDestination = payload.destinationLabelKey');
    expect(appShell).toContain('const localizedMessage = payload.toastMessageKey');
    expect(appShell).toContain(".replace('{destination}', localizedDestination)");
    expect(enLocale).toContain('"subscriptionReturnToast.title.complete": "Upgrade complete"');
    expect(enLocale).toContain('"subscriptionReturnToast.title.unlocked": "{plan} unlocked"');
    expect(enLocale).toContain('"subscriptionReturnToast.message.featuresSubpath": "Your upgraded access is ready in {destination}."');
  });

  it('uses a shared subscription success panel across payment success surfaces', () => {
    const subscriptionPayment = read('app/subscription/payment.tsx');
    const subscriptionSuccess = read('app/subscription/success.tsx');
    const paymentResult = read('app/subscription/payment-result.tsx');
    const mobileMoney = read('app/subscription/mobile-money.tsx');
    const mobileSubscriptionsView = read('src/components/MobileSubscriptionsViewV2.tsx');
    const successPanel = read('src/components/payment/SubscriptionSuccessPanel.tsx');
    const unlockedSummary = read('src/components/payment/SubscriptionUnlockedDestinationSummary.tsx');

    expect(successPanel).toContain('export function SubscriptionSuccessPanel');
    expect(successPanel).toContain('payment-success-primary-cta');
    expect(successPanel).toContain('payment-success-view-history');
    expect(successPanel).toContain('preCtaContent?: React.ReactNode');
    expect(successPanel).toContain('payment-success-pre-cta-content');
    expect(unlockedSummary).toContain('export function SubscriptionUnlockedDestinationSummary');
    expect(unlockedSummary).toContain('buildSubscriptionReturnToastPayload(returnTarget, planName)');
    expect(unlockedSummary).toContain('function getProviderNextStepConfig(providerKey?: string | null, providerLabel?: string | null)');
    expect(subscriptionPayment).toContain('SubscriptionSuccessPanel');
    expect(subscriptionSuccess).toContain('SubscriptionSuccessPanel');
    expect(paymentResult).toContain('SubscriptionSuccessPanel');
    expect(mobileMoney).toContain('SubscriptionSuccessPanel');
    expect(mobileSubscriptionsView).toContain('SubscriptionSuccessPanel');
    expect(mobileSubscriptionsView).toContain('SubscriptionUnlockedDestinationSummary');
    expect(mobileSubscriptionsView).toContain("const smartReturnTarget = useMemo(() => normalizeReturnTarget(String(params.return_to || '/dashboard')), [params.return_to]);");
    expect(mobileSubscriptionsView).toContain('stashSubscriptionReturnToast(smartReturnTarget, routePlanLabel);');
    expect(mobileSubscriptionsView).toContain("tx('iap.handoff.title', 'Store checkout ready')");
    expect(unlockedSummary).toContain("tx('iap.success.destinationSummaryEyebrow', 'Plan unlocked')");
    expect(unlockedSummary).toContain("tx('iap.success.destinationSummaryReturnLabel', 'Returning to')");
    expect(unlockedSummary).toContain("tx('payment.success.providerNextStep.label', 'What unlocks next')");
    expect(unlockedSummary).toContain('next-step');
    expect(unlockedSummary).toContain('testIdPrefix');
    expect(subscriptionPayment).toContain('providerKey={selectedGatewaySlug}');
    expect(subscriptionSuccess).toContain('providerKey={provider}');
    expect(paymentResult).toContain("providerKey={String(gateway || 'fedapay').toLowerCase() === 'fedapay' ? 'fedapay' : 'unknown'}");
    expect(mobileMoney).toContain('providerKey="fedapay"');
    expect(mobileSubscriptionsView).toContain('providerKey={routeProvider || \'unknown\'}');
    expect(subscriptionPayment).toContain('payment-web-unlocked');
    expect(subscriptionSuccess).toContain('payment-redirect-unlocked');
    expect(paymentResult).toContain('payment-result-unlocked');
    expect(mobileMoney).toContain('mobile-money-unlocked');
    expect(mobileSubscriptionsView).toContain('iap-native-unlocked');
    expect(subscriptionPayment).toContain('planName,');
    expect(subscriptionPayment).toContain('return_to: returnTo,');
    expect(subscriptionPayment).not.toContain("Alert.alert(\n              'Payment Successful!'");
    expect(mobileMoney).not.toContain("Alert.alert('Payment completed', 'Your mobile money payment has been completed.')");

    const enLocale = read('src/i18n/locales/en.ts');
    expect(enLocale).toContain('"payment.success.providerNextStep.label": "What unlocks next"');
    expect(enLocale).toContain('"payment.success.providerNextStep.stripe": "Stripe has confirmed your payment — your upgraded tools are ready in {destination}."');
    expect(enLocale).toContain('"payment.success.providerNextStep.google_iap": "Google Play access is synced — open {destination} to start using {plan}."');
  });

  it('keeps non-success payment notifications visible across providers', () => {
    const plans = read('app/subscription/plans.tsx');
    const iapView = read('src/components/MobileSubscriptionsViewV2.tsx');
    const paypalWebhook = readBackend('routes/payments_paypal_routes.py');
    const stripeWebhook = readBackend('routes/payments_stripe_routes.py');
    const fedapayWebhook = readBackend('routes/payments_fedapay_routes.py');
    const iapRoutes = readBackend('routes/iap.py');
    const toast = read('src/components/RealtimeToast.tsx');
    const failureCopy = read('src/utils/paymentFailureCopy.ts');

    expect(failureCopy).toContain('normalizePaymentFailureState');
    expect(failureCopy).toContain('getPaymentFailureCopy');
    expect(failureCopy).toContain("'refunded'");
    expect(plans).toContain("notificationEvents.emit('toast', {");
    expect(plans).toContain('getPaymentFailureCopy');
    expect(plans).toContain("type: returnStatusBanner.tone === 'error' ? 'payment_failed' : 'warning'");
    expect(plans).toContain("actionRoute: '/payment-history'");
    expect(iapView).toContain('hasObservedInactiveStoreStatus');
    expect(iapView).toContain('getPaymentFailureCopy');
    expect(iapView).toContain("type: copy.tone === 'error' ? 'payment_failed' : 'warning'");
    expect(iapView).toContain("actionRoute: '/subscription/mobile'");
    expect(paypalWebhook).toContain('BILLING.SUBSCRIPTION.PAYMENT.FAILED');
    expect(paypalWebhook).toContain('BILLING.SUBSCRIPTION.CANCELLED');
    expect(paypalWebhook).toContain('PAYMENT.SALE.REVERSED');
    expect(paypalWebhook).toContain('PAYMENT.SALE.REFUNDED');
    expect(paypalWebhook).toContain('_build_provider_failure_copy');
    expect(stripeWebhook).toContain('_build_provider_failure_copy');
    expect(fedapayWebhook).toContain('_build_provider_failure_copy');
    expect(iapRoutes).toContain('Checkout cancelled');
    expect(toast).toContain("payment_failed: { icon: 'close-circle'");
    expect(toast).toContain("subscription_cancelled: { icon: 'remove-circle'");
  });
});