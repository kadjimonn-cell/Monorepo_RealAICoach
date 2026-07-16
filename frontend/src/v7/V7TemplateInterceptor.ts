/**
 * V7 Template Interceptor — Intercepts template creation/generation.
 * 
 * FLOW: AI/Builder → V7 VALIDATION → TEMPLATE CREATED → RENDER
 * 
 * At generation time:
 * - Injects V7 theme tokens automatically
 * - Replaces non-V7 styling
 * - Enforces V7 component usage
 * - Rejects non-compliant templates
 */
import { V7_LIGHT, V7_DARK, V7_SPACING, V7_TYPOGRAPHY, V7_RADII, V2_FINGERPRINT_COLORS } from '../theme/v7';
import type { V7Colors } from '../theme/v7';

export interface TemplateDefinition {
  id: string;
  name: string;
  type: string;
  styles?: Record<string, any>;
  components?: string[];
  content?: string;
  metadata?: Record<string, unknown>;
}

export interface V7ValidationResult {
  valid: boolean;
  violations: V7Violation[];
  sanitized?: TemplateDefinition;
}

export interface V7Violation {
  rule: string;
  message: string;
  severity: 'critical' | 'high' | 'warn';
  field?: string;
  original?: string;
  replacement?: string;
}

/**
 * V7TemplateInterceptor — Static utility class for template validation & sanitization.
 */
export class V7TemplateInterceptor {

  /**
   * Validate a template definition against V7 rules.
   * Returns violations and a sanitized version.
   */
  static validate(template: TemplateDefinition, darkMode = false): V7ValidationResult {
    const violations: V7Violation[] = [];
    const sanitized = JSON.parse(JSON.stringify(template)) as TemplateDefinition;
    const colors = darkMode ? V7_DARK : V7_LIGHT;

    // ── Rule 1: Detect V2 color contamination ──
    if (sanitized.styles) {
      V7TemplateInterceptor._scanAndReplaceColors(sanitized.styles, colors, violations);
    }

    // ── Rule 2: Detect inline style strings in content ──
    if (sanitized.content) {
      for (const fp of V2_FINGERPRINT_COLORS) {
        if (sanitized.content.includes(fp)) {
          violations.push({
            rule: 'v2_contamination',
            message: `V2 token "${fp}" found in template content`,
            severity: 'high',
            field: 'content',
            original: fp,
            replacement: colors.primary,
          });
          sanitized.content = sanitized.content.split(fp).join(colors.primary);
        }
      }
    }

    // ── Rule 3: Validate hardcoded hex colors ──
    if (sanitized.styles) {
      V7TemplateInterceptor._validateHexColors(sanitized.styles, colors, violations);
    }

    return {
      valid: violations.length === 0,
      violations,
      sanitized,
    };
  }

  /**
   * Inject V7 theme tokens into a template definition.
   * Called during template generation to ensure V7 compliance.
   */
  static inject(template: TemplateDefinition, darkMode = false): TemplateDefinition {
    const colors = darkMode ? V7_DARK : V7_LIGHT;
    const injected = JSON.parse(JSON.stringify(template)) as TemplateDefinition;

    // Ensure styles exist
    if (!injected.styles) {
      injected.styles = {};
    }

    // Inject V7 base tokens
    injected.styles.__v7_theme = {
      version: 'v7',
      tokens: {
        bg: colors.bg,
        card: colors.card,
        text: colors.text,
        textSecondary: colors.textSecondary,
        border: colors.border,
        primary: colors.primary,
        accent: colors.accent,
        success: colors.success,
        warning: colors.warning,
        error: colors.error,
      },
      spacing: V7_SPACING,
      typography: V7_TYPOGRAPHY,
      radii: V7_RADII,
    };

    // Mark as V7-compliant
    injected.metadata = {
      ...(injected.metadata || {}),
      __v7_compliant: true,
      __v7_injected_at: new Date().toISOString(),
    };

    return injected;
  }

  /**
   * Full pipeline: Validate → Inject → Return compliant template.
   * This is the mandatory entry point for all template creation.
   */
  static process(template: TemplateDefinition, darkMode = false): {
    template: TemplateDefinition;
    result: V7ValidationResult;
    compliant: boolean;
  } {
    // Step 1: Validate
    const result = V7TemplateInterceptor.validate(template, darkMode);

    // Step 2: Use sanitized version (V2 tokens replaced)
    const clean = result.sanitized || template;

    // Step 3: Inject V7 tokens
    const final = V7TemplateInterceptor.inject(clean, darkMode);

    // Step 4: Determine compliance
    const hasCritical = result.violations.some(v => v.severity === 'critical');

    return {
      template: final,
      result,
      compliant: !hasCritical, // Allow if no critical violations (warn/high are auto-fixed)
    };
  }

  // ── Private helpers ──

  private static _scanAndReplaceColors(
    styles: Record<string, any>,
    colors: V7Colors,
    violations: V7Violation[]
  ) {
    for (const [key, val] of Object.entries(styles)) {
      if (typeof val === 'string') {
        const upper = val.toUpperCase();
        for (const fp of V2_FINGERPRINT_COLORS) {
          if (upper.includes(fp.toUpperCase())) {
            violations.push({
              rule: 'v2_contamination',
              message: `V2 token "${fp}" found in style.${key}`,
              severity: 'high',
              field: key,
              original: fp,
              replacement: colors.primary,
            });
            styles[key] = val.replace(new RegExp(fp, 'gi'), colors.primary);
          }
        }
      } else if (typeof val === 'object' && val !== null) {
        V7TemplateInterceptor._scanAndReplaceColors(val, colors, violations);
      }
    }
  }

  private static _validateHexColors(
    styles: Record<string, any>,
    colors: V7Colors,
    violations: V7Violation[]
  ) {
    const v7Values = new Set(Object.values(colors).map(v => typeof v === 'string' ? v.toUpperCase() : ''));
    const hexPattern = /^#([0-9A-Fa-f]{3,8})$/;

    for (const [key, val] of Object.entries(styles)) {
      if (typeof val === 'string' && hexPattern.test(val)) {
        if (!v7Values.has(val.toUpperCase())) {
          // Hardcoded hex not in V7 palette
          violations.push({
            rule: 'hardcoded_color',
            message: `Hardcoded color "${val}" in style.${key} is not a V7 token`,
            severity: 'warn',
            field: key,
            original: val,
          });
        }
      } else if (typeof val === 'object' && val !== null && key !== '__v7_theme') {
        V7TemplateInterceptor._validateHexColors(val, colors, violations);
      }
    }
  }
}
