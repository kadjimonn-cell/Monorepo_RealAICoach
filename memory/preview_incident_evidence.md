# Emergent Preview Stale Routing Evidence
- Timestamp (UTC): 2026-05-07T09:24:04.923164Z
- Job/Run ID: `21a85e87-b105-4fa4-b385-10bd5c641b79`
- External preview checked: `https://coach-web-preview.preview.emergentagent.com/job-platform`
- Local service checked: `http://127.0.0.1:3000/job-platform`

## 1) External vs Local response mismatch
- External response: status `200`, server `cloudflare`, length `2277`
- Local response: status `200`, server `Express`, length `107036`
- External cache-control: `no-store, no-cache, must-revalidate`
- Local cache-control: `no-store, no-cache, must-revalidate, max-age=0`

## 2) External preview is a wrapper, not app bundle HTML
- External HTML contains iframe redirect host: `trust-layer-checkout.preview.emergentagent.com`
- External index script found: `NONE`
- Local index script found: `/_expo/static/js/web/index-a7cfd30a2925e955caf4aac21298dd22.js?v=1778144031971`

## 3) Wrapper target host behavior
- Wrapper target checked: `https://coach-web-preview.preview.emergentagent.com/job-platform`
- Wrapper target also returns iframe host: `trust-layer-checkout.preview.emergentagent.com`
- Wrapper target index script found: `NONE`

## 4) Latest local bundle hash
- Local serves latest hash: `index-a7cfd30a2925e955caf4aac21298dd22.js`
- Local dist path: `/app/frontend/dist/client/_expo/static/js/web/index-a7cfd30a2925e955caf4aac21298dd22.js`

## 5) Divergence point
- Divergence occurs before frontend app HTML delivery, at external preview routing/wrapper resolution layer (Cloudflare + loading-preview host mapping), not local pod build output.