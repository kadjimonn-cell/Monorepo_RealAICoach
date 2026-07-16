# Theme Guide — RealAICoach Platform

> **All current and future pages MUST auto-adapt to light/dark mode.**
> This is enforced by ESLint at build time and CSS variables at runtime.

---

## Quick Start

### Inside AppShell (authenticated pages)

```tsx
import { useTheme } from '../context/ThemeContext';

export default function MyPage() {
  const { colors, darkMode } = useTheme();

  return (
    <AppShell>
      <View style={{ backgroundColor: colors.bg }}>
        <Text style={{ color: colors.text }}>Hello</Text>
      </View>
    </AppShell>
  );
}
```

### Inside PublicPageShell (public pages)

```tsx
import PublicPageShell, { getColors } from '../src/components/PublicPageLayout';
import { useTheme } from '../src/context/ThemeContext';

export default function MyPublicPage() {
  const { darkMode } = useTheme();
  const C = getColors(darkMode);

  return (
    <PublicPageShell>
      <Text style={{ color: C.text }}>Hello</Text>
    </PublicPageShell>
  );
}
```

### Admin panels / utility components

```tsx
import { useAdminTheme } from '../hooks/useAdminTheme';

function MyAdminPanel() {
  const AC = useAdminTheme();

  return (
    <View style={{ backgroundColor: AC.card, borderColor: AC.border }}>
      <Text style={{ color: AC.text }}>Panel content</Text>
    </View>
  );
}
```

---

## Rules

### DO

- Use `useTheme()`, `useAdminTheme()`, or `getColors(darkMode)` for ALL colors
- Use CSS variables (`var(--app-bg)`) as a web fallback when hooks aren't available
- Keep accent colors (teal, blue, purple) consistent — use the theme token, not raw hex
- Test every new page in BOTH light and dark mode before committing

### DON'T

- Hardcode dark hex colors: `#0F172A`, `#1E293B`, `#F1F5F9`, `#050A18`, etc.
- Hardcode light hex colors without a dark counterpart
- Use `StyleSheet.create` with theme colors at module level without a fallback
- Skip the theme import — ESLint will flag it

---

## Available Theme Hooks

| Hook / Function | Import From | Use Case |
|---|---|---|
| `useTheme()` | `../context/ThemeContext` | Pages inside AppShell |
| `getColors(dark)` | `../components/PublicPageLayout` | Public pages |
| `useAdminTheme()` | `../hooks/useAdminTheme` | Admin panels |
| `getAdminColors(dark)` | `../hooks/useAdminTheme` | Module-level fallback |
| `getT(dark)` | `../components/pages/login/designTokens` | Login/auth pages |

---

## CSS Variables (Web Fallback)

The `ThemeEnforcer` component injects CSS custom properties on `:root` that
update whenever the theme changes. Any web-rendered component can use them:

```tsx
// Web-only fallback style
style={{
  backgroundColor: Platform.OS === 'web' ? 'var(--app-bg)' : colors.bg,
}}
```

Available variables:
`--app-bg`, `--app-bg-alt`, `--app-card`, `--app-surface`,
`--app-border`, `--app-border-light`, `--app-border-strong`,
`--app-text`, `--app-text-sec`, `--app-text-muted`, `--app-text-dim`,
`--app-accent`, `--app-primary`, `--app-success`, `--app-warning`,
`--app-error`, `--app-info`, `--app-input-bg`, `--app-input-border`,
`--app-skeleton`

---

## Module-Level Patterns

If you need colors in `StyleSheet.create()` or module-level constants, provide a static fallback:

```tsx
import { getAdminColors } from '../hooks/useAdminTheme';

// Module-level fallback (dark defaults for StyleSheet)
const AC = getAdminColors(true);

const styles = StyleSheet.create({
  card: { backgroundColor: AC.card, borderColor: AC.border },
});

// Component-level override (runtime theme-aware)
function MyPanel() {
  const AC = useAdminTheme(); // shadows the module AC
  return <View style={[styles.card, { backgroundColor: AC.card }]} />;
}
```

---

## ESLint Enforcement

The custom rule `no-hardcoded-theme-colors` will flag any `.tsx` file that:
1. Contains known dark hex colors (`#0F172A`, `#1E293B`, `#F1F5F9`, etc.)
2. Does NOT import a theme hook (`useTheme`, `useAdminTheme`, `getColors`, etc.)

This runs on every build. Fix violations by adding the appropriate theme import.

---

## Color Token Reference

| Token | Light | Dark |
|---|---|---|
| bg | `#F8FAFC` | `#0B1121` |
| bgAlt | `#FFFFFF` | `#0F172A` |
| card | `#FFFFFF` | `#111B2E` |
| surface | `#FFFFFF` | `#132036` |
| border | `#E2E8F0` | `#1E293B` |
| text | `#0F172A` | `#F1F5F9` |
| textSec | `#334155` | `#CBD5E1` |
| textMuted | `#64748B` | `#94A3B8` |
| accent | `#0D9488` | `#00D4AA` |
| primary | `#3B82F6` | `#3B82F6` |
| success | `#059669` | `#10B981` |
| warning | `#D97706` | `#F59E0B` |
| error | `#DC2626` | `#EF4444` |
