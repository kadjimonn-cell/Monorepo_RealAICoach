/**
 * GlobalLayoutSystem (GLS) — Enterprise Layout Engine
 *
 * Provides a consistent, centered layout container that enforces:
 * - Max-width constraints (configurable, default 1240px)
 * - Automatic horizontal centering
 * - Responsive padding (scales with viewport)
 * - 12-column conceptual grid alignment
 * - Mobile-first design patterns
 *
 * Usage:
 *   <GLSContainer>
 *     <GLSSection>
 *       <Text>Centered content</Text>
 *     </GLSSection>
 *   </GLSContainer>
 */
import React from 'react';
import { View, useWindowDimensions, Pressable, Text } from 'react-native';
import { DEFAULT_GLS_TOKENS, useGLSConfig, type GLSTokens } from '../../context/GLSContext';
import { useTheme } from '../../context/ThemeContext';

// ── GLS Configuration Tokens (runtime values come from GLSContext) ──
export const GLS_TOKENS = DEFAULT_GLS_TOKENS;

export type GLSVariant = 'default' | 'narrow' | 'wide' | 'full';

function getMaxWidth(variant: GLSVariant, tokens: GLSTokens): number | undefined {
  const layoutMode = tokens.layoutMode;
  if (layoutMode === 'full-width') return undefined;
  switch (variant) {
    case 'narrow': return tokens.maxWidthNarrow;
    case 'wide': return tokens.maxWidthWide;
    case 'full': return undefined;
    default:
      if (layoutMode === 'compact') return tokens.maxWidthNarrow;
      return tokens.maxWidth;
  }
}

export function getResponsivePadding(width: number, tokens: GLSTokens = DEFAULT_GLS_TOKENS): number {
  if (!tokens.responsiveEnabled) return tokens.paddingDesktop;
  if (width >= tokens.breakpoints.large) return tokens.paddingLarge;
  if (width >= tokens.breakpoints.desktop) return tokens.paddingDesktop;
  if (width >= tokens.breakpoints.tablet) return tokens.paddingTablet;
  return tokens.paddingMobile;
}

export function getResponsiveSectionPadding(width: number, tokens: GLSTokens = DEFAULT_GLS_TOKENS): number {
  if (!tokens.responsiveEnabled) return tokens.sectionPaddingDesktop;
  if (width >= tokens.breakpoints.desktop) return tokens.sectionPaddingDesktop;
  if (width >= tokens.breakpoints.tablet) return tokens.sectionPaddingTablet;
  return tokens.sectionPaddingMobile;
}

interface GLSContainerProps {
  children: React.ReactNode;
  variant?: GLSVariant;
  noPadding?: boolean;
  style?: any;
  testID?: string;
}

/**
 * GLSContainer — Primary centered container.
 * Centers content horizontally with max-width and responsive padding.
 */
export function GLSContainer({ children, variant = 'default', noPadding, style, testID }: GLSContainerProps) {
  const { tokens, padding } = useGLSBreakpoint();
  const maxW = getMaxWidth(variant, tokens);
  const px = noPadding ? 0 : padding;

  return (
    <View
      data-testid={testID || 'gls-container'}
      testID={testID || 'gls-container'}
      style={[
        {
          width: '100%' as any,
          alignSelf: 'center' as any,
          paddingHorizontal: px,
        },
        maxW ? { maxWidth: maxW } : undefined,
        style,
      ]}
    >
      {children}
    </View>
  );
}

interface GLSSectionProps {
  children: React.ReactNode;
  variant?: GLSVariant;
  noPadding?: boolean;
  noVerticalPadding?: boolean;
  style?: any;
  testID?: string;
  backgroundColor?: string;
  fullBleed?: boolean;
}

/**
 * GLSSection — Section wrapper with vertical spacing.
 * If fullBleed, the background extends edge-to-edge but content stays centered.
 */
export function GLSSection({ children, variant = 'default', noPadding, noVerticalPadding, style, testID, backgroundColor, fullBleed }: GLSSectionProps) {
  const { tokens, sectionPadding, padding } = useGLSBreakpoint();
  const py = noVerticalPadding ? 0 : sectionPadding;
  const px = noPadding ? 0 : padding;
  const maxW = getMaxWidth(variant, tokens);

  if (fullBleed && backgroundColor) {
    return (
      <View
        style={{ width: '100%' as any, backgroundColor }}
        data-testid={testID}
        testID={testID}
      >
        <View
          style={[
            {
              width: '100%' as any,
              maxWidth: maxW,
              alignSelf: 'center' as any,
              paddingHorizontal: px,
              paddingVertical: py,
            },
            style,
          ]}
        >
          {children}
        </View>
      </View>
    );
  }

  return (
    <View
      data-testid={testID}
      testID={testID}
      style={[
        {
          width: '100%' as any,
          alignSelf: 'center' as any,
          paddingHorizontal: px,
          paddingVertical: py,
        },
        maxW ? { maxWidth: maxW } : undefined,
        backgroundColor ? { backgroundColor } : undefined,
        style,
      ]}
    >
      {children}
    </View>
  );
}

interface GLSGridProps {
  children: React.ReactNode;
  columns?: number;
  gap?: number;
  style?: any;
  testID?: string;
}

interface GLSGridItemProps {
  children: React.ReactNode;
  span?: number;
  spanMobile?: number;
  spanTablet?: number;
  spanDesktop?: number;
  spanLarge?: number;
}

/**
 * GLSGrid — Responsive grid layout.
 * On mobile: single column (stacked).
 * On tablet: 2 columns.
 * On desktop: specified columns (default 3).
 *
 * Children should be wrapped in GLSGridItem for proper sizing.
 */
export function GLSGrid({ children, columns = 12, gap = 16, style, testID }: GLSGridProps) {
  const { isDesktop, isTablet, isLarge } = useGLSBreakpoint();
  const totalColumns = Math.max(1, columns || 12);

  return (
    <View
      data-testid={testID || 'gls-grid'}
      testID={testID || 'gls-grid'}
      style={[
        {
          flexDirection: 'row' as const,
          flexWrap: 'wrap' as const,
          marginHorizontal: -(gap / 2),
          width: '100%' as any,
          alignItems: 'stretch' as const,
        },
        style,
      ]}
    >
      {React.Children.map(children, (child, index) => {
        if (!React.isValidElement(child)) return child;
        const props = (child.props || {}) as GLSGridItemProps;
        const fallbackSpan = Math.max(1, Math.min(totalColumns, props.span || totalColumns));

        const spanForViewport = isLarge
          ? (props.spanLarge || props.spanDesktop || props.spanTablet || props.spanMobile || fallbackSpan)
          : isDesktop
            ? (props.spanDesktop || props.spanTablet || props.spanMobile || fallbackSpan)
            : isTablet
              ? (props.spanTablet || props.spanMobile || Math.min(6, fallbackSpan))
              : (props.spanMobile || Math.min(12, fallbackSpan));

        const safeSpan = Math.max(1, Math.min(totalColumns, Number(spanForViewport) || totalColumns));
        const itemWidth = `${(safeSpan / totalColumns) * 100}%`;

        return (
          <View
            key={(child as any).key || `gls-grid-item-${index}`}
            style={{
              width: itemWidth as any,
              paddingHorizontal: gap / 2,
              marginBottom: gap,
            }}
          >
            {child}
          </View>
        );
      })}
    </View>
  );
}

export function GLSGridItem({ children }: GLSGridItemProps) {
  return <>{children}</>;
}

interface GLSCardProps {
  children: React.ReactNode;
  style?: any;
  testID?: string;
}

export function GLSCard({ children, style, testID }: GLSCardProps) {
  const { colors } = useTheme();
  return (
    <View
      testID={testID}
      data-testid={testID}
      style={[
        {
          borderRadius: 18,
          borderWidth: 1,
          borderColor: colors.border,
          backgroundColor: colors.surface,
          padding: 20,
        },
        style,
      ]}
    >
      {children}
    </View>
  );
}

interface GLSButtonProps {
  label: string;
  onPress?: () => void;
  testID?: string;
  style?: any;
}

export function GLSButton({ label, onPress, testID, style }: GLSButtonProps) {
  const { colors } = useTheme();
  return (
    <Pressable
      onPress={onPress}
      testID={testID}
      data-testid={testID}
      style={[
        {
          minHeight: 44,
          paddingHorizontal: 18,
          borderRadius: 999,
          alignItems: 'center',
          justifyContent: 'center',
          backgroundColor: colors.primary,
        },
        style,
      ]}
    >
      <Text style={{ color: colors.primaryText, fontWeight: '700', fontSize: 14 }}>{label}</Text>
    </Pressable>
  );
}

/**
 * useGLSBreakpoint — Hook to get current breakpoint info.
 */
export function useGLSBreakpoint() {
  const { width, height } = useWindowDimensions();
  const { tokens } = useGLSConfig();
  return {
    width,
    height,
    isMobile: width < tokens.breakpoints.tablet,
    isTablet: width >= tokens.breakpoints.tablet && width < tokens.breakpoints.desktop,
    isDesktop: width >= tokens.breakpoints.desktop,
    isLarge: width >= tokens.breakpoints.large,
    breakpoint: width >= tokens.breakpoints.large ? 'large'
      : width >= tokens.breakpoints.desktop ? 'desktop'
      : width >= tokens.breakpoints.tablet ? 'tablet'
      : 'mobile' as 'mobile' | 'tablet' | 'desktop' | 'large',
    padding: getResponsivePadding(width, tokens),
    sectionPadding: getResponsiveSectionPadding(width, tokens),
    tokens,
  };
}

export default {
  GLSContainer,
  GLSSection,
  GLSGrid,
  GLSGridItem,
  GLSCard,
  GLSButton,
  useGLSBreakpoint,
  GLS_TOKENS,
};

/* i18n-probe t('i18n.auto.probe') */
