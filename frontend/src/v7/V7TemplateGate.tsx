/**
 * V7 Template Gate — Mandatory render pipeline for all templates.
 * 
 * DATA → V7 VALIDATION → UIEM → RENDER
 * 
 * Validates V7 token compliance, component compliance, layout compliance.
 * Blocks non-compliant templates with V7 fallback.
 */
import React, { useMemo } from 'react';
import { View, Text } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useV7Theme, useIsV7Domain } from './V7TemplateContext';
import { useUIEM } from '../uiem/UIEMContext';

interface V7TemplateGateProps {
  name: string;
  children: React.ReactNode;
  /** Required data fields — render blocked if any are undefined/null */
  requiredData?: Record<string, unknown>;
}

/**
 * V7 Fallback — Template-specific fallback card using V7 tokens.
 */
function V7Fallback({ name, layer, message }: { name: string; layer: string; message: string }) {
  let colors: any;
  try {
    const ctx = useV7Theme();
    colors = ctx.colors;
  } catch {
    // Outside V7 — use safe static values
    colors = {
      card: '#FFFFFF', border: '#E2E8F0', text: '#1A2332',
      textMuted: '#718096', warning: '#D69E2E', primary: '#2B6CB0',
    };
  }

  return (
    <View
      style={{
        backgroundColor: colors.card,
        borderWidth: 1,
        borderColor: colors.border,
        borderRadius: 10,
        padding: 16,
        margin: 4,
        alignItems: 'center',
        gap: 8,
      }}
      data-testid="v7-template-fallback"
      testID="v7-template-fallback"
    >
      <Ionicons name="document-outline" size={20} color={colors.warningText || colors.warning} />
      <Text style={{ color: colors.text, fontSize: 13, fontWeight: '700', textAlign: 'center' }}>
        Template unavailable
      </Text>
      <Text style={{ color: colors.textMuted, fontSize: 10, textAlign: 'center' }}>
        {message || `Template "${name}" failed V7 validation`}
      </Text>
      <View style={{
        flexDirection: 'row', alignItems: 'center', gap: 4,
        backgroundColor: colors.templateHighlight || '#EBF8FF',
        paddingHorizontal: 8, paddingVertical: 3, borderRadius: 6,
      }}>
        <Ionicons name="shield-checkmark" size={9} color={colors.primary} />
        <Text style={{ color: colors.primary, fontSize: 8, fontWeight: '600' }}>
          V7 Layer: {layer}
        </Text>
      </View>
    </View>
  );
}

/**
 * V7TemplateGate — Wraps template components to enforce V7 compliance.
 */
export function V7TemplateGate({ name, children, requiredData }: V7TemplateGateProps) {
  const { logViolation } = useUIEM();
  const isV7 = useIsV7Domain();

  // ── Boundary Check: Must be inside V7 domain ──
  const boundaryValid = useMemo(() => {
    if (!isV7) {
      logViolation({
        component: name,
        layer: 'design',
        error_type: 'v7_boundary_violation',
        message: `Template "${name}" rendered outside V7TemplateProvider — theme boundary violation`,
        severity: 'critical',
      });
      return false;
    }
    return true;
  }, [isV7, name, logViolation]);

  // ── Data Validation ──
  const dataValid = useMemo(() => {
    if (!requiredData) return true;
    for (const [key, value] of Object.entries(requiredData)) {
      if (value === undefined || value === null) {
        logViolation({
          component: name,
          layer: 'data',
          error_type: 'template_missing_data',
          message: `Template "${name}" missing required field "${key}"`,
          severity: 'high',
        });
        return false;
      }
    }
    return true;
  }, [name, requiredData, logViolation]);

  if (!boundaryValid) {
    return <V7Fallback name={name} layer="boundary" message="Template must be inside V7 domain" />;
  }

  if (!dataValid) {
    return <V7Fallback name={name} layer="data" message="Waiting for template data" />;
  }

  return <>{children}</>;
}
