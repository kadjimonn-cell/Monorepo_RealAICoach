/**
 * useAdminTheme — DEPRECATED WRAPPER
 *
 * Delegates to useTheme().colors from ThemeContext (v1).
 * Kept for backward compatibility.
 */
import { useTheme } from '../context/ThemeContext';
import { V1_LIGHT, V1_DARK, type ThemeColors } from '../theme/v1';

export function getAdminColors(isDark: boolean): ThemeColors {
  return isDark ? V1_DARK : V1_LIGHT;
}

export function useAdminTheme(): ThemeColors {
  const { colors } = useTheme();
  return colors as ThemeColors;
}

export default useAdminTheme;
