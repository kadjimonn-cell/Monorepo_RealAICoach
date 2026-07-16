# Web Runtime Package

This package isolates server-only frontend runtime dependencies from the main Expo app dependency graph.

## Why this exists
- `express`, `http-proxy-middleware`, and `serve-static` are only needed for server/runtime scripts (`serve-production.js`, CI static server).
- Keeping them here avoids mixing SSR/proxy runtime packages into the core app dependency surface.

## Resolution/override note
- Root security/transitive pinning remains centralized in `frontend/package.json` under the top-level `resolutions` block.
- Any future overrides for this package should be added there to keep one authoritative lock policy.