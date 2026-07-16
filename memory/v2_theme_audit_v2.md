# Platform-wide V2 Theme Audit v2 — Deep Global Scan
_Last updated: 2026-04-23 by E1. Scope: `/app/frontend/src/**/*.tsx` + `/app/frontend/app/**/*.tsx` (558 files)._
_Automated scanner: `/app/scripts/audit_v2_theme.py`. Machine-readable report: `/tmp/v2_theme_audit_v2.json`._

## Scoreboard

| Bucket | Count | % |
|---|---:|---:|
| Total UI files scanned | 558 | 100 % |
| ✅ Theme-compliant (calls `useTheme` / `useAdminTheme` / `useExecTheme` / `useThemeMode`) | 409 | 73 % |
| 🟡 Explicitly exempt (`@theme-audit-file-ok` / `@theme-v2-exempt`) | 257 | 46 % |
| 🔴 **Files with active violations** | **73** | **13 %** |
|     &nbsp;&nbsp;• P0 — hot admin paths | 18 | |
|     &nbsp;&nbsp;• P1 — user-facing pages | 51 | |
|     &nbsp;&nbsp;• P2 — theme/UIEM helpers | 4 | |

Compliance is high on the SURFACE (97 % as reported Apr 23), but that number hides the #1 problem: **208 legacy `darkMode ? dark : light` ternaries** across 53 files. These look fine when the OS color scheme matches the hardcoded branches but break the V2 theme TOGGLE — the app's own light/dark switch.

---

## Root cause (1 dominant pattern, 3 smaller ones)

### #1 — Legacy `darkMode` ternary branching (208 occurrences, 53 files, ~90 % of all violations)
```tsx
backgroundColor: darkMode ? '#111827' : '#FFFFFF',
color: darkMode ? '#F8FAFC' : '#0F172A',
```
This pattern predates the V2 `ThemeContext` CSS-variable system. It reads a single `darkMode` boolean (usually from `useColorScheme()` or a custom hook) and picks hex literals by hand. When V2's theme TOGGLE flips to light:
- `useColorScheme()` still returns `'dark'` if the OS is dark → the ternary stays dark.
- Even if `darkMode` wire is correct, the hardcoded hex bypasses the `--app-*` CSS variables set by `ThemeContext`, so nothing else on the page can re-tune those values via tokens.

**Worst offender:** `app/employer-apply.tsx` with **56 ternaries** (the entire page is `darkMode ? : :`). Next: `ExecShortcutSheet.tsx` (13), `GalleryCard.tsx` (12), `AIChatPanel.tsx` (9), `HomeDashboardCharts.tsx` (9).

### #2 — Hardcoded light-text hex (`#FFF…` / `#F0F4FC` / `#E5E7EB`) on non-themed surfaces (16 occurrences)
```tsx
<Text style={{ color: '#F8FAFC' }}>…</Text>
```
Locks the text to light — unreadable the instant the toggle goes to light theme over a white bg. Typically found where a dark background was hardcoded nearby.

### #3 — UI-rendering files that don't consume the theme AT ALL (31 files)
```tsx
import { View, Text } from 'react-native';   // no useTheme / useAdminTheme
// hardcoded styles throughout
```
Most are in: session-replay viewers, certificate galleries, dashboard chart helpers, footer, +html, etc. A few are legitimately static (e.g. `+html.tsx` SSR shell, the `ThemeContext` itself, `UIEMFallback`) — but the rest should consume tokens OR accept a `colors` prop from a themed parent.

### #4 — Remaining module-scope dark palettes (1 occurrence)
`CampaignDashboardPanel.tsx` still carries a module-scope dark `const C` (added as a CRASH-FIX fallback in the Apr-23 sweep). Safe because helpers use it for icon tints only — does not break theme flip on the main surface, but should be CSS-var-bound for consistency.

### Why compliance "97 %" missed this

The earlier audit counted any file that imported `useTheme` as compliant. But these files can *import* the hook, *read* one value, and *then* still branch on `darkMode` for 50 other lines. The ternary IS the bug — importing the hook isn't enough.

---

## Proposed fixing actions (three phases)

### Phase 1 — Codemod `darkMode ? dark : light` → token-based (auto-fixable)

A narrow codemod can rewrite the safe subset automatically. Rules:

| Source pattern | Replacement |
|---|---|
| `backgroundColor: darkMode ? '#0..' : '#FFF..'` | `backgroundColor: colors.card` |
| `backgroundColor: darkMode ? '#1..' : '#F..'` | `backgroundColor: colors.surface` |
| `color: darkMode ? '#F..' : '#0..'` | `color: colors.text` |
| `color: darkMode ? '#94A3B8' : '#64748B'` | `color: colors.textSec` |
| `borderColor: darkMode ? '#1..' : '#E..'` | `borderColor: colors.border` |

Plus a guard: only rewrite files that *already* have a `colors` constant in scope (either via `useTheme()` or a `colors` prop). Anything else → mark manual.

Expected yield at P1: ~140 / 208 ternaries auto-clean, zero behavioural change because the token values match the literals we're replacing. Output a report of which files need eyes.

**Highest-ROI target:** `app/employer-apply.tsx` (56 ternaries on a user-facing page). One file, one theme hook, ~30 minutes to land.

### Phase 2 — Manual sweep of P0 admin offenders (18 files, ~2 h)

The list is short and mostly single-violation:

- `ApplicantThreadPanel.tsx` (5 hits) — the only P0 with an `inline_dark_bg` too; worth a focused fix.
- `V7TemplateComplianceWidget.tsx` (6 hits) — highest P0 violation count.
- `TopBrokenPanelsWidget.tsx`, `CareerTZHeatmap.tsx`, `ApplicantThread`, `admin/offers/[offerId].tsx` — need `colors.text`/`colors.textSec` swaps.
- `DependencyScanPanel.tsx`, `GtecCrawlerPanel.tsx`, `email-templates/CoverageView.tsx` — add `const colors = useAdminTheme()` (or accept `colors` prop).
- `CampaignDashboardPanel.tsx` — convert the one remaining module palette to the CSS-var-bound pattern from the Apr-23 playbook.

### Phase 3 — Add a guardrail so the bug can't creep back

1. **ESLint rule** (repo-local) that flags `darkMode ? '#…' : '#…'` patterns and hardcoded `backgroundColor`/`color` hex strings in `.tsx` files outside the exempt list.
2. **Pre-commit hook** that runs `python3 /app/scripts/audit_v2_theme.py --strict` and fails if the P0 violation count is > 0.
3. **CI job** (or the existing code_health daily) that uploads the same report to `db.theme_audit_log`; existing `AdminHealthDigestWidget` can show the trend so ops can spot regressions in the morning email.

---

## Concrete 2-hour plan (if proceeding immediately)

1. Write `/app/scripts/migrate_darkmode_ternaries.py` — the Phase-1 codemod with the 5 safe rewrite rules above + dry-run support.
2. Run it on `app/employer-apply.tsx` alone first, build+smoke test.
3. Run on the remaining 52 P1 files in a single pass.
4. Manually fix the 18 P0 files (follow the Apr-23 CSS-variable-binding playbook already documented in `v2_theme_audit.md`).
5. Re-run `audit_v2_theme.py`; verify violation count < 5.
6. Add ESLint rule + pre-commit hook + CI upload.
7. Update `AdminHealthDigestWidget` + digest email to include a "theme compliance" field (delta from previous scan).

Expected end-state: **0 P0 violations, 0 P1 `darkmode_ternary` in user-facing pages, ~20 P2 exceptions with documented reasons**.
