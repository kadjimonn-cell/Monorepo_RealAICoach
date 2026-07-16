export interface User {
  user_id: string;
  email: string;
  name: string;
  picture?: string;
  phone?: string;
  profile_image?: string;
  created_at?: string;
  role?: string;
  subscription_plan: string;
  subscription_status?: string;
  roles?: string[];
  platform_role?: string | null;
  employee_permissions?: string[];
  feature_access?: string[];
  is_admin?: boolean;
  full_access?: boolean;
  theme_preference?: string | null;
  language_preference?: string | null;
  currency_preference?: string | null;
  tenant_id?: string | null;
  organization_id?: string | null;
  company_id?: string | null;
  workspace_id?: string | null;
  tenant_disclaimer_profile?: 'default' | 'strict_regulated' | null;
}

export interface LogoutOptions {
  reason?: string;
  source?: string;
  redirectTarget?: string;
  expectedLogoutBanner?: boolean;
}

export type ServerSessionProbeResult = {
  state: 'authenticated' | 'unauthenticated' | 'transient';
  status?: number;
  kind?: string;
};

export interface AuthContextType {
  user: User | null;
  loading: boolean;
  isAuthenticated: boolean;
  login: (email: string, password: string, rememberMe?: boolean, resendOtp?: boolean) => Promise<any>;
  requestOtp: (email: string, forceResend?: boolean) => Promise<{ otp_hint?: string; code_reused?: boolean; otp_delivery_status?: string; expires_in?: number }>;
  loginWithOtp: (email: string, code: string) => Promise<any>;
  verify2FA: (userId: string, code: string, rememberMe?: boolean) => Promise<any>;
  verifyPin: (userId: string, pin: string) => Promise<void>;
  register: (email: string, password: string, name: string) => Promise<void>;
  loginWithGoogle: () => Promise<void>;
  loginWithMicrosoft: () => Promise<void>;
  logout: (options?: LogoutOptions) => Promise<void>;
  refreshUser: () => Promise<void>;
  hasServerSession: () => Promise<boolean>;
  probeServerSession: () => Promise<ServerSessionProbeResult>;
  guest: boolean;
  loginAsGuest: () => Promise<void>;
  welcomeBack: { name: string; lastRoute: string; lastActiveAt?: string } | null;
  clearWelcomeBack: () => void;
}