# Tracked Issues

## P2-04 · TODO/FIXME Comments in Production Code Paths (4 files)

**Status:** Closed (Implemented)

### Scope
- `frontend/app/+html.tsx`
- `frontend/src/i18n/locales/it.ts`
- `frontend/src/i18n/locales/es.ts`
- `frontend/src/i18n/locales/pt.ts`

### Triage Decision Per File
1. `frontend/app/+html.tsx`
   - Decision: **Implement** (instead of tracking-only)
   - Resolution: TODO removed by implementing environment-aware CSP behavior.
   - Evidence:
     - `+html.tsx:27-34` host detection logic (`isLocalHost`, `shouldEnableUpgradeInsecureRequests`)
     - `+html.tsx:80-82` conditional CSP meta render

2. `frontend/src/i18n/locales/es.ts`
   - Decision: **Implement**
   - Resolution: Placeholder TODO-like user-facing values replaced with finalized copy (`SIN ALERTAS`) at previously flagged keys.
   - Evidence keys include:
     - `admin.anomalyDetectionPanel.auto.text.003`
     - `admin.escalationPanel.auto.text.003`
     - `admin.pagePerformancePanel.auto.text.014`
     - `admin.platformHealthPanel.auto.text.026`
     - `admin.suspiciousPanel.auto.text.005`
     - `aiFeatureDashboard.alerts.allClear`

3. `frontend/src/i18n/locales/it.ts`
   - Decision: **Implement**
   - Resolution: Payment label normalized to finalized copy.
   - Evidence:
     - `it.ts:2208` = `"TIPO PAGAMENTO"`

4. `frontend/src/i18n/locales/pt.ts`
   - Decision: **Implement**
   - Resolution: Payment label normalized to finalized copy.
   - Evidence:
     - `pt.ts:2208` = `"FORMA DE PAGAMENTO"`

### Validation Snapshot
- `rg -n "TODO|FIXME"` across these 4 files returns no matches.
- Frontend smoke verification confirms app loads and CSP behavior is active in preview.
