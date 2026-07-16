import React, { createContext, useContext, useState, useEffect, useCallback, useMemo, ReactNode } from 'react';
import { useAuth } from './AuthContext';
import api from '../services/api';
import { useAccessControl } from './AccessControlContext';

interface SubscriptionStatus {
  subscription_plan: string;
  subscription_status: string;
  subscription_end_date: string | null;
  plan_name: string;
  is_privileged: boolean;
  features: Record<string, any>;
  plan_features: string[];
  plan_limitations: string[];
  daily_conversation_limit: number;
  daily_conversations_used: number;
  export_formats: string[];
  automation_enabled: boolean;
  print_enabled: boolean;
  history_days: number;
  payment_verified: boolean;
  pending_subscription_transition?: Record<string, any> | null;
  feature_entitlements?: Record<string, any>;
}

interface SubscriptionContextType {
  plan: string;
  planName: string;
  isPremium: boolean;
  isBasic: boolean;
  isFree: boolean;
  isPrivileged: boolean;
  canAccess: (requiredPlan: 'basic' | 'premium') => boolean;
  canUseFeature: (featureName: string) => boolean;
  status: SubscriptionStatus | null;
  loading: boolean;
  refresh: () => Promise<void>;
  dailyUsagePercent: number;
  subscriptionEndDate: string | null;
  subscriptionStatus: string;
  pendingTransition: Record<string, any> | null;
}

const PLAN_HIERARCHY: Record<string, number> = { free: 0, basic: 1, premium: 2 };

const SubscriptionContext = createContext<SubscriptionContextType | undefined>(undefined);

export function SubscriptionProvider({ children }: { children: ReactNode }) {
  const { user, isAuthenticated } = useAuth();
  const { effectivePlan, canAccessPlan } = useAccessControl();
  const [status, setStatus] = useState<SubscriptionStatus | null>(null);
  const [loading, setLoading] = useState(false);

  const fetchStatus = useCallback(async () => {
    if (!isAuthenticated) return;
    setLoading(true);
    try {
      const res = await api.get('/subscriptions/status');
      setStatus(res.data);
    } catch {
      // Silently fail - don't crash the provider
      // The component will use fallback values from the user object
    } finally {
      setLoading(false);
    }
  }, [isAuthenticated]);

  useEffect(() => {
    fetchStatus();
  }, [fetchStatus]);

  const plan = effectivePlan || status?.subscription_plan || user?.subscription_plan || 'free';
  const planLevel = PLAN_HIERARCHY[plan] ?? 0;
  const isPremium = canAccessPlan('premium');
  const isBasic = planLevel >= 1 || isPremium;
  const isFree = planLevel === 0 && !isPremium;

  const canAccess = useCallback((requiredPlan: 'basic' | 'premium') => {
    return canAccessPlan(requiredPlan);
  }, [canAccessPlan]);

  const canUseFeature = useCallback((featureName: string) => {
    if (isPremium) return true;
    const source = status?.feature_entitlements || status?.features || null;
    if (!source) return isBasic;
    const val = source[featureName];
    if (val === undefined || val === null) return true;
    if (typeof val === 'boolean') return val;
    if (typeof val === 'number') return val !== 0;
    if (Array.isArray(val)) return val.length > 0;
    if (typeof val === 'string') {
      const lowered = val.toLowerCase();
      return lowered !== 'false' && lowered !== 'none' && lowered !== 'blocked';
    }
    return true;
  }, [isBasic, isPremium, status]);

  const dailyUsagePercent = useMemo(() => {
    if (!status) return 0;
    const limit = status.daily_conversation_limit;
    if (limit <= 0) return 0;
    return Math.round((status.daily_conversations_used / limit) * 100);
  }, [status]);

  const value: SubscriptionContextType = {
    plan,
    planName: status?.plan_name || plan.charAt(0).toUpperCase() + plan.slice(1),
    isPremium,
    isBasic,
    isFree,
    isPrivileged: isPremium,
    canAccess,
    canUseFeature,
    status,
    loading,
    refresh: fetchStatus,
    dailyUsagePercent,
    subscriptionEndDate: status?.subscription_end_date || null,
    subscriptionStatus: status?.subscription_status || 'active',
    pendingTransition: status?.pending_subscription_transition || null,
  };

  return (
    <SubscriptionContext.Provider value={value}>
      {children}
    </SubscriptionContext.Provider>
  );
}

export function useSubscription() {
  const context = useContext(SubscriptionContext);
  if (!context) {
    // Fallback when used outside provider
    return {
      plan: 'free',
      planName: 'Free',
      isPremium: false,
      isBasic: false,
      isFree: true,
      isPrivileged: false,
      canAccess: () => false,
      canUseFeature: () => false,
      status: null,
      loading: false,
      refresh: async () => {},
      dailyUsagePercent: 0,
      subscriptionEndDate: null,
      subscriptionStatus: 'active',
      pendingTransition: null,
    };
  }
  return context;
}
