export type DisplayUser = {
  role?: string;
  subscription_plan?: string;
  effective_plan?: string;
  is_admin?: boolean;
  full_access?: boolean;
  subscription?: { plan?: string };
};

export const normalizeRole = (role?: string) => {
  if (!role) return '';
  return role.toLowerCase().replace(' ', '_');
};

export const getDisplayPlan = (user?: DisplayUser | null) => {
  if (!user) return 'free';
  const role = normalizeRole(user.role);
  if (role === 'admin' || role === 'full_users') return 'premium';
  if (user.is_admin || user.full_access) return 'premium';
  return user.effective_plan || user.subscription_plan || user.subscription?.plan || 'free';
};

export const hasPremiumAccess = (user?: DisplayUser | null) => {
  const plan = getDisplayPlan(user);
  return plan === 'premium';
};

export const hasBasicAccess = (user?: DisplayUser | null) => {
  const plan = getDisplayPlan(user);
  return plan === 'basic' || plan === 'premium';
};
