/**
 * V7 Boundary Enforcer — Detects cross-contamination between V2 and V7 domains.
 * 
 * RULES:
 * - V2 styles are FORBIDDEN inside templates (V7 domain)
 * - V7 styles are FORBIDDEN outside templates (V2 domain)
 * 
 * If cross-contamination detected: STOP render, log boundary violation.
 *
 * Theme note — Developer-only error panel rendered when the V2/V7
 * boundary is crossed. Uses fixed red/warning palette because it only shows
 * during boundary violations (a diagnostics surface, not user-facing chrome).
 */
import React, { useMemo } from 'react';
import { View, Text } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useIsV7Domain } from './V7TemplateContext';
import { useUIEM } from '../uiem/UIEMContext';
import { useTheme } from '../context/ThemeContext';
import { V2_FINGERPRINT_COLORS } from '../theme/v7';

interface V7BoundaryEnforcerProps {
  children: React.ReactNode;
  componentName: string;
  /** 'template' = must be in V7 domain, 'platform' = must NOT be in V7 domain */
  domain: 'template' | 'platform';
  /** Optional style object to scan for cross-contamination */
  styleToCheck?: Record<string, unknown>;
}

/**
 * Check if a style object contains V2 fingerprint colors (cross-contamination).
 */
function detectV2Contamination(style: Record<string, unknown>): string[] {
  const violations: string[] = [];
  if (!style) return violations;

  for (const [key, val] of Object.entries(style)) {
    if (typeof val === 'string') {
      const upper = val.toUpperCase();
      for (const fp of V2_FINGERPRINT_COLORS) {
        if (upper.includes(fp.toUpperCase())) {
          violations.push(`V2 token "${fp}" found in style.${key}`);
        }
      }
    }
  }
  return violations;
}

export function V7BoundaryEnforcer({ children, componentName, domain, styleToCheck }: V7BoundaryEnforcerProps) {
  const isV7 = useIsV7Domain();
  const { logViolation } = useUIEM();
  const { colors } = useTheme();

  const boundaryResult = useMemo(() => {
    // Domain check
    if (domain === 'template' && !isV7) {
      logViolation({
        component: componentName,
        layer: 'design',
        error_type: 'v7_boundary_violation',
        message: `Template component "${componentName}" rendered outside V7 domain — must be inside V7TemplateProvider`,
        severity: 'critical',
      });
      return { valid: false, reason: 'Template component outside V7 domain' };
    }

    if (domain === 'platform' && isV7) {
      logViolation({
        component: componentName,
        layer: 'design',
        error_type: 'v2_boundary_violation',
        message: `Platform component "${componentName}" rendered inside V7 domain — V2 components forbidden in templates`,
        severity: 'critical',
      });
      return { valid: false, reason: 'Platform component inside V7 template domain' };
    }

    // Cross-contamination check (V2 colors inside V7 template)
    if (domain === 'template' && styleToCheck) {
      const contaminations = detectV2Contamination(styleToCheck);
      if (contaminations.length > 0) {
        logViolation({
          component: componentName,
          layer: 'design',
          error_type: 'v2_contamination_in_template',
          message: `V2 tokens found in template "${componentName}": ${contaminations.join(', ')}`,
          severity: 'high',
        });
        return { valid: false, reason: `V2 cross-contamination: ${contaminations[0]}` };
      }
    }

    return { valid: true, reason: '' };
  }, [isV7, domain, componentName, styleToCheck, logViolation]);

  if (!boundaryResult.valid) {
    return (
      <View
        style={{
          backgroundColor: colors.errorSoft,
          borderWidth: 1,
          borderColor: colors.error,
          borderRadius: 10,
          padding: 14,
          margin: 4,
          alignItems: 'center',
          gap: 6,
        }}
        data-testid="v7-boundary-violation"
        testID="v7-boundary-violation"
      >
        <Ionicons name="ban" size={18} color={colors.error} />
        <Text style={{ color: colors.errorText, fontSize: 12, fontWeight: '700', textAlign: 'center' }}>
          Theme Boundary Violation
        </Text>
        <Text style={{ color: colors.text, fontSize: 10, textAlign: 'center' }}>
          {boundaryResult.reason}
        </Text>
      </View>
    );
  }

  return <>{children}</>;
}
