import React, { useEffect, useMemo, useState } from 'react';
import { ActivityIndicator, Text, TouchableOpacity, View } from 'react-native';
import { usePathname, useRouter } from 'expo-router';
import { useTheme } from '../context/ThemeContext';

const API = process.env.REACT_APP_BACKEND_URL || '';

type RuntimeReport = {
  status?: string;
  score?: number;
  run_id?: string;
  scanned_at?: string;
  enforcement_mode?: string;
  global_block?: boolean;
  blocking_routes?: string[];
  global_blockers?: string[];
  theme_policy?: {
    pages_theme_version?: string;
    email_theme_version?: string;
    pdf_theme_version?: string;
    strict_no_bypass?: boolean;
    strict_route_prefixes?: string[];
  };
  summary?: {
    files_with_blockers?: number;
    legacy_brand_issue_count?: number;
  };
};

export function ThemeComplianceRuntimeGate({ children }: { children: React.ReactNode }) {
  const { colors } = useTheme();
  const pathname = usePathname();
  const router = useRouter();
  const [report, setReport] = useState<RuntimeReport | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const res = await fetch(`${API}/api/config/v2-compliance/runtime`, { credentials: 'include' });
        const data = await res.json();
        if (!cancelled) setReport(data || null);
      } catch {
        if (!cancelled) setReport(null);
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    void load();
    return () => { cancelled = true; };
  }, []);

  const routeMatchesBlockRule = (route: string, rule: string): boolean => {
    const cleanedRoute = route || '/';
    const cleanedRule = String(rule || '').trim();
    if (!cleanedRule) return false;
    if (cleanedRule.endsWith('*')) {
      const prefix = cleanedRule.slice(0, -1);
      return cleanedRoute === prefix.replace(/\/$/, '') || cleanedRoute.startsWith(prefix);
    }
    return cleanedRoute === cleanedRule;
  };

  const isBlocked = useMemo(() => {
    if (!report) return false;
    const strictBlocking = report.enforcement_mode === 'blocking' || report.theme_policy?.strict_no_bypass === true;
    if (!strictBlocking) return false;
    if (report.status === 'healthy') return false;

    const blockerCount = Number(report?.summary?.files_with_blockers || 0);
    const legacyIssueCount = Number(report?.summary?.legacy_brand_issue_count || 0);
    const explicitGlobalBlockers = Array.isArray(report?.global_blockers) ? report.global_blockers.length : 0;
    if (blockerCount <= 0 && legacyIssueCount <= 0 && explicitGlobalBlockers <= 0) {
      return false;
    }

    const route = pathname || '/';
    const blockingRoutes = report.blocking_routes || [];
    if (report.global_block) return true;
    if (blockingRoutes.length === 0) return false;
    return blockingRoutes.some((rule) => routeMatchesBlockRule(route, String(rule || '')));
  }, [pathname, report]);

  if (!isBlocked) return <>{children}</>;

  return (
    <View
      style={{ flex: 1, backgroundColor: colors.bg, alignItems: 'center', justifyContent: 'center', padding: 24 }}
      data-testid="theme-compliance-runtime-gate"
      testID="theme-compliance-runtime-gate"
    >
      <View
        style={{ width: '100%', maxWidth: 560, backgroundColor: colors.surfaceElevated, borderRadius: 24, borderWidth: 1, borderColor: colors.border, padding: 24, gap: 14 }}
        data-testid="theme-compliance-runtime-gate-card"
        testID="theme-compliance-runtime-gate-card"
      >
        <View style={{ width: 58, height: 58, borderRadius: 18, backgroundColor: colors.errorSoft, alignItems: 'center', justifyContent: 'center' }}>
          <ActivityIndicator color={colors.error} />
        </View>
        <View>
          <Text style={{ color: colors.text, fontSize: 22, fontWeight: '800' }} data-testid="theme-compliance-runtime-gate-title" testID="theme-compliance-runtime-gate-title">
            V2 compliance hold
          </Text>
          <Text style={{ color: colors.textSec, fontSize: 13, lineHeight: 20, marginTop: 6 }} data-testid="theme-compliance-runtime-gate-copy" testID="theme-compliance-runtime-gate-copy">
            This route is temporarily blocked because the latest V2 compliance scan detected off-brand styling in a page or shared shell file.
          </Text>
        </View>

        <View style={{ gap: 6, padding: 14, borderRadius: 16, backgroundColor: colors.bgSoft, borderWidth: 1, borderColor: colors.border }}>
          <Text style={{ color: colors.text, fontSize: 12, fontWeight: '700' }} data-testid="theme-compliance-runtime-gate-meta-run" testID="theme-compliance-runtime-gate-meta-run">Run: {report?.run_id || 'latest'}</Text>
          <Text style={{ color: colors.textMuted, fontSize: 11 }} data-testid="theme-compliance-runtime-gate-meta-score" testID="theme-compliance-runtime-gate-meta-score">Score: {report?.score ?? '--'} · Blockers: {report?.summary?.files_with_blockers ?? 0}</Text>
          <Text style={{ color: colors.textMuted, fontSize: 11 }} data-testid="theme-compliance-runtime-gate-meta-theme-policy" testID="theme-compliance-runtime-gate-meta-theme-policy">Theme policy: pages {report?.theme_policy?.pages_theme_version || 'v2'} · email {report?.theme_policy?.email_theme_version || 'v7'} · pdf {report?.theme_policy?.pdf_theme_version || 'v15'}</Text>
          <Text style={{ color: colors.textMuted, fontSize: 11 }} data-testid="theme-compliance-runtime-gate-meta-route" testID="theme-compliance-runtime-gate-meta-route">Current route: {pathname || '/'}</Text>
        </View>

        <View style={{ flexDirection: 'row', gap: 10, flexWrap: 'wrap' }}>
          <TouchableOpacity
            onPress={() => router.replace('/welcome')}
            style={{ paddingHorizontal: 14, paddingVertical: 11, borderRadius: 12, backgroundColor: colors.primary }}
            data-testid="theme-compliance-runtime-gate-welcome-button"
            testID="theme-compliance-runtime-gate-welcome-button"
          >
            <Text style={{ color: colors.primaryText, fontSize: 12, fontWeight: '800' }}>Go to welcome</Text>
          </TouchableOpacity>
          <TouchableOpacity accessibilityLabel="Theme compliance runtime gate retry button"
            onPress={() => {
              if (typeof window !== 'undefined') window.location.reload();
            }}
            style={{ paddingHorizontal: 14, paddingVertical: 11, borderRadius: 12, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceHover }}
            data-testid="theme-compliance-runtime-gate-retry-button"
            testID="theme-compliance-runtime-gate-retry-button"
          >
            <Text style={{ color: colors.text, fontSize: 12, fontWeight: '700' }}>Retry scan</Text>
          </TouchableOpacity>
        </View>

        {loading ? null : (
          <Text style={{ color: colors.textMuted, fontSize: 11 }} data-testid="theme-compliance-runtime-gate-footnote" testID="theme-compliance-runtime-gate-footnote">
            Admins can review blockers in Theme Health Center → V2 Compliance Guardrail.
          </Text>
        )}
      </View>
    </View>
  );
}

/* i18n-probe t('i18n.auto.probe') */
