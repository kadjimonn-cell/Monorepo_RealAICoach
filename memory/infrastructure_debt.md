# Infrastructure Technical Debt Log

## Critical Issues

### 1. Metro Bundler "Premature Close" Crash Loop ⚠️ CRITICAL

**Status**: UNRESOLVED (5th occurrence)  
**First Reported**: Previous forks (exact date unknown)  
**Last Occurrence**: 2026-05-26  
**Impact**: HIGH - Blocks frontend preview validation for all feature changes

#### Description
Metro bundler enters infinite crash loop with error:
```
Error: Premature close
    at onclose (node:internal/streams/end-of-stream:159:30)
    at processTicksAndRejections (node:internal/process/task_queues:77:11)
```

The bundling process takes 75-85 seconds per attempt, never completes successfully, and leaves `dist/` directory empty. This prevents `serve-production.js` from serving the built application.

#### Root Cause (Suspected)
- Metro's internal HTTP server or WebSocket connection being terminated unexpectedly
- File watcher or dependency resolution process crashing
- Memory pressure causing Node process to abort mid-bundle
- Possible corruption in Metro's internal cache state (persists even after clearing documented caches)

#### Attempted Fixes
1. ✅ Cleared `/tmp/frontend-metro-cache/*`
2. ✅ Cleared `/app/frontend/.expo/*`
3. ✅ Cleared `/app/frontend/dist/*`
4. ✅ Cleared `/tmp/metro-*`, `/tmp/haste-*`, `/tmp/react-*`
5. ✅ Cleared `/app/frontend/node_modules/.cache`
6. ✅ Restarted Expo service multiple times
7. ✅ Removed CI mode from `zz_expo_override.conf` (previous fork)
8. ✅ Tested with minimal component (simplified Decision Coach)
9. ❌ **All attempts failed - issue persists**

#### Current Workaround
- Proceed with backend-first development
- Validate backend APIs independently via curl/Postman
- Defer frontend E2E validation until Metro is stabilized
- Log frontend code changes as "Pending Visual Verification"

#### Recommended Solution (Requires Infrastructure Team)
1. Investigate Node.js version compatibility with Metro bundler
2. Profile Metro memory usage during bundle process
3. Review Expo configuration for conflicts
4. Consider upgrading/downgrading Metro to stable version
5. Evaluate alternative bundler (Vite, Webpack) for production builds
6. Implement Metro restart watchdog with automatic recovery

#### Features Affected
- ✅ Feature 4 (Workflow Builder): Backend verified, Frontend pending
- ✅ Feature 5 (Decision Coach): Backend verified, Frontend pending
- ⚠️ All future features: Frontend validation blocked until resolved

#### Priority
**P0** - This issue blocks frontend validation for the entire 36-feature enterprise rebuild. However, backend development can continue independently.

#### Assigned To
Infrastructure/DevOps Team (requires specialized Expo/Metro expertise)

---

## Medium Priority Issues

### 2. External Proxy Aggressive Caching

**Status**: RECURRING  
**Impact**: MEDIUM - Delays visibility of frontend changes on preview URL

#### Description
External proxy (`https://coach-web-preview.preview.emergentagent.com`) aggressively caches old React Native web bundles, preventing updated code from being visible even when Metro successfully builds.

#### Workaround
- Test against `localhost:3000` directly when possible
- Wait for cache TTL to expire naturally (timing unknown)
- Document in testing notes when external URL may show stale content

#### Recommended Solution
- Configure proxy cache headers properly
- Implement cache busting via query parameters
- Reduce TTL for preview environments

---

## Log Format
Date | Issue | Status | Reporter | Notes
-----|-------|--------|----------|-------
2026-05-26 | Metro Premature Close | Unresolved | E1 Agent | 5th occurrence, backend-first workaround adopted
