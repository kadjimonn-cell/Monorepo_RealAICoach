# ROADMAP

## P0 — Complete
- Welcome + Footer V2 theme compliance verification
- Welcome + Footer i18n-safe Checkpoint D verification (`/app/test_reports/iteration_743.json`)

## P1 — Complete
- Shared `buildAnalyticsSource()` helper with adoption across touched public analytics surfaces
- Admin Preview Freshness card in Operations Console (bundle freshness + rebuild reason)

## P2 — Backlog
- Reusable protected-route wrapper/helper to standardize auth contracts and access policies
- Blog editorial workflow: Draft → Review → Publish → Schedule
- Remembered-interest memory card freshness decay / softer aging state
- Dedicated layout regression suites (capability header band, wide desktop closeout, phone-Chrome footer)

## P3 — Nice to Have
- Shared analytics-source presets/constants layer on top of `buildAnalyticsSource()` for future pages
- Preview freshness backend parity follow-up if `/_preview/health` later exposes a non-empty runtime bundle hash directly
