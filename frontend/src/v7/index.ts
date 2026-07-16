/**
 * V7 Template System — Barrel Export
 * 
 * V7 = Template-Only Design System (isolated from V2 platform UI)
 */

// Theme tokens
export { V7_LIGHT, V7_DARK, V7_SPACING, V7_TYPOGRAPHY, V7_RADII, V7_GRID, V7_APPROVED_COMPONENTS, V2_FINGERPRINT_COLORS, THEME_V7_VERSION } from '../theme/v7';
export type { V7Colors } from '../theme/v7';

// Context & hooks
export { V7TemplateProvider, useV7Theme, useIsV7Domain } from './V7TemplateContext';

// Gate (render pipeline)
export { V7TemplateGate } from './V7TemplateGate';

// Boundary enforcer (cross-contamination detection)
export { V7BoundaryEnforcer } from './V7BoundaryEnforcer';

// Template interceptor (generation-time validation)
export { V7TemplateInterceptor } from './V7TemplateInterceptor';
export type { TemplateDefinition, V7ValidationResult, V7Violation } from './V7TemplateInterceptor';
