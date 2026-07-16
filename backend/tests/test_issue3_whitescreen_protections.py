"""
Regression test for Issue 3 ("White Screen" / "Something Went Wrong" prevention)
and Issue 2 (UI Components Breaking After Rebuilds).

Pins the current state of six protections so they cannot silently regress:

  Issue 3 — white screens / Something Went Wrong:
    1. ErrorBoundary.tsx — no auto-reload for general runtime errors;
       hooks-violation auto-reload is bounded; RECOVERY_WINDOW_MS >= 30000;
       MAX_AUTO_RELOAD_ATTEMPTS bounded.
    2. LanguageContext.tsx — overlay is pointerEvents="none" (cannot freeze
       the app); children render unconditionally; t() falls back to a stale
       locale during loading.
    3. backend/middleware.py — response_sanitization_middleware is scoped
       to /api/auth/* paths only and respects content-length caps.

  Issue 2 — UI components breaking after rebuilds:
    4. metro.config.js — NO 5xx-to-200 rewrite on the root path;
       cacheVersion derived from package.json + metro.config.js hash so the
       FileStore disk cache invalidates automatically on git pulls.
    5. app/+html.tsx — synchronous pre-hydration inline <script> sets
       --app-bg, --app-surface, --app-primary and 30+ CSS custom properties
       BEFORE React mounts (prevents FOUC).
    6. store/appStore.ts — Zustand persist middleware with AsyncStorage,
       schema versioning + migrate(), and _hasHydrated boolean exposed.

Run:  pytest /app/backend/tests/test_issue3_whitescreen_protections.py -v
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _read(rel: str) -> str:
    return (REPO_ROOT / rel).read_text(encoding="utf-8")


# ─────────────────────────────────────────────────────────────────────────
# 1. ErrorBoundary.tsx
# ─────────────────────────────────────────────────────────────────────────


class TestErrorBoundary:
    SRC = "frontend/src/components/ErrorBoundary.tsx"

    def test_recovery_window_is_at_least_30s(self):
        src = _read(self.SRC)
        assert "RECOVERY_WINDOW_MS = 30000" in src, (
            "RECOVERY_WINDOW_MS must be >= 30000ms so consecutive auto-reload "
            "loops on slow-loading pages are blocked."
        )

    def test_max_auto_reload_attempts_is_bounded(self):
        src = _read(self.SRC)
        assert "MAX_AUTO_RELOAD_ATTEMPTS" in src
        assert "tryConsumeAutoReloadAttempt" in src, (
            "Reload-attempt counter must exist to prevent infinite reload loops."
        )

    def test_no_general_error_auto_reload(self):
        """General runtime errors must NOT trigger window.location.reload().

        The only allowed reload call sites are:
          * inside the isHooksViolation(error) branch in componentDidCatch
          * inside handleReload (user clicks the manual button)
        """
        src = _read(self.SRC)
        # Auto-reload must be gated by the hooks-violation predicate.
        # The block containing "window.location.reload()" inside
        # componentDidCatch must follow an `isHooksViolation(error)` check.
        idx = 0
        reload_sites = []
        while True:
            pos = src.find("window.location.reload()", idx)
            if pos == -1:
                break
            reload_sites.append(pos)
            idx = pos + 1

        assert reload_sites, "Expected at least one reload site (handleReload)."

        # Every reload site must be reachable only from a hooks-violation
        # branch OR from handleReload. Heuristic: scan the 600 chars before
        # each call and ensure either `isHooksViolation` OR `handleReload` is in scope.
        for pos in reload_sites:
            preceding = src[max(0, pos - 800): pos]
            assert (
                "isHooksViolation" in preceding or "handleReload" in preceding
            ), (
                f"Found window.location.reload() at offset {pos} not gated "
                "by isHooksViolation or handleReload. This would cause "
                "white-screen reload loops on general errors."
            )

    def test_no_setTimeout_auto_reload(self):
        """The 120ms setTimeout-then-reload pattern must not exist."""
        src = _read(self.SRC)
        assert "setTimeout(() => window.location.reload()" not in src
        assert "setTimeout(()=>window.location.reload()" not in src

    def test_manual_recovery_buttons_present(self):
        src = _read(self.SRC)
        assert 'data-testid="error-boundary-reload"' in src
        assert 'data-testid="error-boundary-retry"' in src


# ─────────────────────────────────────────────────────────────────────────
# 2. LanguageContext.tsx
# ─────────────────────────────────────────────────────────────────────────


class TestLanguageContext:
    SRC = "frontend/src/i18n/LanguageContext.tsx"

    def test_overlay_is_pointer_events_none(self):
        src = _read(self.SRC)
        # The language-switch indicator must NOT block input.
        assert 'pointerEvents="none"' in src, (
            "Language-switch overlay must use pointerEvents='none' so it can "
            "never freeze the entire app shell."
        )
        assert 'pointerEvents="auto"' not in src, (
            "Language-switch overlay must NEVER use pointerEvents='auto'."
        )

    def test_children_render_unconditionally(self):
        """The provider must render {children} before the optional indicator,
        so the app shell is never gated on isLanguageReady."""
        src = _read(self.SRC)
        # Find the JSX root of LanguageContext.Provider
        # children must appear before the conditional sync indicator
        children_pos = src.find("{children}")
        indicator_pos = src.find("showLanguageSyncIndicator")
        assert children_pos != -1, "{children} must be rendered."
        assert indicator_pos != -1, "showLanguageSyncIndicator must exist."
        # children must render BEFORE the indicator conditional in JSX flow
        # find the JSX usage (not the variable definition) of showLanguageSyncIndicator
        indicator_jsx = src.find("{showLanguageSyncIndicator ?")
        assert indicator_jsx != -1, "showLanguageSyncIndicator must be used as a JSX conditional."
        assert children_pos < indicator_jsx, (
            "{children} must appear in JSX BEFORE the showLanguageSyncIndicator "
            "conditional so children are always rendered."
        )

    def test_t_falls_back_to_resolved_locale_while_loading(self):
        """`t()` must use resolvedLanguageCode (a cached/stale locale or English)
        while a new locale is loading — so the app never shows blank text."""
        src = _read(self.SRC)
        assert "resolvedLanguageCode" in src
        assert "fallbackLanguageCode" in src
        # The fallback selector must depend on localeLoading/languageSwitching
        assert "localeLoading" in src and "languageSwitching" in src


# ─────────────────────────────────────────────────────────────────────────
# 3. backend/middleware.py
# ─────────────────────────────────────────────────────────────────────────


class TestResponseSanitizationMiddleware:
    SRC = "backend/middleware.py"

    def test_scoped_to_auth_paths(self):
        src = _read(self.SRC)
        # The middleware must early-return for any non-auth path.
        assert "_is_auth_sanitization_path" in src
        assert 'path == "/api/auth"' in src
        assert 'path.startswith("/api/auth/")' in src

    def test_skips_options_and_non_auth(self):
        src = _read(self.SRC)
        # The non-auth early-return MUST exist:
        snippet = (
            'if request.method == "OPTIONS" or not _is_auth_sanitization_path(path):\n'
            '            return response'
        )
        assert snippet in src, (
            "response_sanitization_middleware must short-circuit for OPTIONS "
            "and any non-/api/auth path BEFORE attempting to buffer the body."
        )

    def test_content_length_cap_present(self):
        src = _read(self.SRC)
        assert "MAX_AUTH_SANITIZE_BYTES" in src
        assert "256 * 1024" in src
        # Cap must be enforced before buffering
        assert "if int(content_length_raw) > MAX_AUTH_SANITIZE_BYTES" in src

    def test_streaming_and_binary_bypassed(self):
        src = _read(self.SRC)
        assert "text/event-stream" in src
        assert "_is_trusted_binary_content_type" in src


# ─────────────────────────────────────────────────────────────────────────
# 4. frontend/metro.config.js — Issue 2 (rebuild breakage)
# ─────────────────────────────────────────────────────────────────────────


class TestMetroConfig:
    SRC = "frontend/metro.config.js"

    def test_no_5xx_to_200_rewrite(self):
        """Metro must NOT silently rewrite any HTTP 5xx response to 200.
        Such a rewrite would make CDNs cache broken shells as success and
        let health checks pass silently."""
        src = _read(self.SRC)
        assert "writeHead" not in src, (
            "metro.config.js must not override writeHead — that would risk "
            "rewriting 5xx responses to 200 and poisoning CDN caches."
        )
        # The only res.statusCode assignment must be the explicit asset-200 below.
        assert src.count("res.statusCode") <= 1
        if "res.statusCode" in src:
            # The single allowed assignment is for the static-asset fallback,
            # which has already validated that the file exists on disk.
            idx = src.index("res.statusCode")
            window = src[max(0, idx - 500): idx + 100]
            assert "fs.existsSync" in window or "fullPath.startsWith(__dirname)" in window

    def test_cache_version_derived_from_hashes(self):
        """FileStore cache must invalidate automatically on git pulls by
        deriving cacheVersion from package.json + metro.config.js hashes."""
        src = _read(self.SRC)
        assert "config.cacheVersion" in src, "cacheVersion must be set."
        assert "crypto" in src and "createHash" in src
        assert "package.json" in src
        assert "metro.config.js" in src


# ─────────────────────────────────────────────────────────────────────────
# 5. app/+html.tsx — Issue 2 (FOUC prevention)
# ─────────────────────────────────────────────────────────────────────────


class TestHtmlPrehydration:
    SRC = "frontend/app/+html.tsx"

    def test_inline_script_in_head_sets_theme_vars_before_mount(self):
        """A synchronous inline <script> in <head> MUST read the saved theme
        from localStorage and pre-set --app-bg, --app-surface, and --app-primary
        before React mounts. This prevents the flash of unstyled content
        described in Issue 2."""
        src = _read(self.SRC)

        # The prehydrate script must read localStorage for the theme.
        assert "localStorage.getItem" in src
        assert "app_theme" in src

        # It must pre-set the three required CSS custom properties.
        for prop in ("--app-bg", "--app-surface", "--app-primary"):
            assert f"'{prop}'" in src or f'"{prop}"' in src, (
                f"Pre-hydration script must set CSS variable {prop}."
            )

        # The script must run inside <head>, before <body>.
        head_close = src.index("</head>")
        body_open = src.index("<body")
        # All occurrences of setProperty('--app-bg' or '--app-bg' must come before </head>
        bg_pos = src.find("--app-bg")
        assert 0 < bg_pos < head_close < body_open, (
            "Theme CSS variable injection must happen inside <head>, before "
            "<body> renders — otherwise FOUC will occur."
        )


# ─────────────────────────────────────────────────────────────────────────
# 6. frontend/src/store/appStore.ts — Issue 2 (Zustand hydration)
# ─────────────────────────────────────────────────────────────────────────


class TestAppStorePersistence:
    SRC = "frontend/src/store/appStore.ts"

    def test_persist_middleware_with_asyncstorage(self):
        src = _read(self.SRC)
        # Accept either `zustand/middleware` or `zustand/middleware.js`
        assert (
            "from 'zustand/middleware'" in src
            or "from 'zustand/middleware.js'" in src
            or 'from "zustand/middleware"' in src
            or 'from "zustand/middleware.js"' in src
        )
        assert "persist(" in src
        # AsyncStorage adapter must be plugged into createJSONStorage
        assert "createJSONStorage" in src
        assert "AsyncStorage" in src

    def test_hasHydrated_flag_exposed(self):
        src = _read(self.SRC)
        # Some flag exposing hydration state must exist (hasHydrated or _hasHydrated)
        assert (
            "hasHydrated" in src or "_hasHydrated" in src
        ), "appStore must expose a hasHydrated boolean for downstream gating."
        assert "onRehydrateStorage" in src, (
            "appStore must use onRehydrateStorage to flip the hydration flag."
        )

    def test_schema_versioning_with_migrate(self):
        src = _read(self.SRC)
        assert "version:" in src or "version :" in src, (
            "Persist config must declare a version number for schema migrations."
        )
        assert "migrate:" in src or "migrate :" in src, (
            "Persist config must declare a migrate() function so stored data "
            "from older schemas is upgraded, not corrupted."
        )


# ─────────────────────────────────────────────────────────────────────────
# 7. Issue 4 — Frontend/Backend synchronization (WebSocket consolidation)
# ─────────────────────────────────────────────────────────────────────────


class TestRealtimeConsolidation:
    """Pins the WebSocket consolidation work done in earlier sessions:
    only RealtimeContext (and its low-level utility useManagedWebSocket)
    may open `new WebSocket(...)`. The ticket-based auth pattern must be
    the only handshake style."""

    FRONTEND_SRC = REPO_ROOT / "frontend" / "src"

    def test_only_two_websocket_constructor_call_sites(self):
        """Whitelist: useManagedWebSocket.ts (utility) and RealtimeContext.tsx
        (the singleton). Any new `new WebSocket(...)` in app code is a
        regression that re-introduces the competing-implementations problem
        described in Issue 4."""
        allowed = {
            "hooks/useManagedWebSocket.ts",
            "context/RealtimeContext.tsx",
        }
        found = []
        for path in self.FRONTEND_SRC.rglob("*.ts"):
            if path.suffix not in (".ts", ".tsx"):
                continue
            text = path.read_text(encoding="utf-8")
            if "new WebSocket(" in text:
                rel = str(path.relative_to(self.FRONTEND_SRC))
                if rel not in allowed:
                    found.append(rel)
        for path in self.FRONTEND_SRC.rglob("*.tsx"):
            text = path.read_text(encoding="utf-8")
            if "new WebSocket(" in text:
                rel = str(path.relative_to(self.FRONTEND_SRC))
                if rel not in allowed:
                    found.append(rel)
        assert not found, (
            f"Unauthorized new WebSocket() call site(s): {found}. "
            "All realtime traffic must flow through RealtimeContext."
        )

    def test_no_raw_token_query_string_in_websocket_urls(self):
        """The legacy `?token=<sessionToken>` URL pattern leaked the raw
        session token into server access logs. Only the ticket-based
        handshake (`?ticket=...`) is allowed."""
        for path in list(self.FRONTEND_SRC.rglob("*.ts")) + list(self.FRONTEND_SRC.rglob("*.tsx")):
            text = path.read_text(encoding="utf-8")
            # We only care about strings that build a WebSocket URL.
            if "ws://" not in text and "wss://" not in text and "api/ws" not in text:
                continue
            # Search for the raw `?token=${...}` pattern in WS URL construction.
            assert "?token=${" not in text, (
                f"{path.relative_to(self.FRONTEND_SRC)}: WebSocket URL must "
                "use ?ticket=... not raw ?token=..."
            )

    def test_useliveData_uses_realtime_context(self):
        src = (self.FRONTEND_SRC / "hooks" / "useLiveData.ts").read_text(encoding="utf-8")
        assert "useRealtime" in src
        assert "from '../context/RealtimeContext'" in src
        assert "new WebSocket(" not in src, (
            "useLiveData must subscribe to RealtimeContext, never open its own socket."
        )

    def test_no_useRealtimeNotifications_hook(self):
        """The duplicate hook described in Issue 4 must not be reintroduced."""
        for path in self.FRONTEND_SRC.rglob("useRealtimeNotifications*"):
            raise AssertionError(
                f"useRealtimeNotifications hook re-introduced at {path}. "
                "All consumers must use RealtimeContext directly."
            )


class TestAuthRefresh2FA:
    SRC = "frontend/src/context/AuthContext.tsx"

    def test_verify2fa_calls_fetchAuthMeResilient_with_force(self):
        src = _read(self.SRC)
        # Find the verify2FA function body
        start = src.index("const verify2FA = useCallback")
        # Search next ~1000 chars for the resilient fetch
        body = src[start: start + 1500]
        assert "fetchAuthMeResilient" in body, (
            "verify2FA() must call fetchAuthMeResilient after applyAuthSession "
            "so the post-2FA user payload is hydrated immediately."
        )
        assert "force: true" in body, (
            "The post-2FA fetchAuthMeResilient call must pass force: true."
        )
        assert "'post-2fa'" in body or '"post-2fa"' in body, (
            "The fetchAuthMeResilient call must tag its phase as 'post-2fa'."
        )


class TestApiShouldResetTokenOn401:
    SRC = "frontend/src/services/api.ts"

    def test_uses_structured_error_code_not_substring(self):
        src = _read(self.SRC)
        # The helper that extracts the structured error code must exist.
        assert "extractStructuredErrorCode" in src

        # Confirm shouldResetTokenOn401 reads from extractStructuredErrorCode
        idx = src.index("function shouldResetTokenOn401")
        body = src[idx: idx + 2000]
        assert "extractStructuredErrorCode" in body, (
            "shouldResetTokenOn401() must use the structured error_code "
            "extractor (not substring-match the human-readable detail string)."
        )

        # The candidate code list must look up `error_code` AND `code`
        # at top level, `detail`, `error`, and `detail.error` — all four
        # standard FastAPI/structured-error nesting shapes.
        for candidate in (
            "payload?.error_code",
            "payload?.code",
            "payload?.detail?.error_code",
            "payload?.detail?.code",
            "payload?.error?.error_code",
            "payload?.error?.code",
            "payload?.detail?.error?.error_code",
            "payload?.detail?.error?.code",
        ):
            assert candidate in src, f"Missing structured error_code probe: {candidate}"

    def test_token_reset_scoped_to_auth_family_paths(self):
        """Generic non-auth 401s must NEVER wipe the token (Issue 4 root cause:
        substring match on 'Unauthorized' was bouncing valid users out of
        every endpoint)."""
        src = _read(self.SRC)
        assert "isAuthFamilyEndpoint" in src
        # The early-return guard MUST exist.
        snippet = "if (!isAuthFamilyEndpoint) {\n    return false;\n  }"
        assert snippet in src, (
            "shouldResetTokenOn401() must early-return false for any URL "
            "outside the /api/auth/, /api/session/, /users/me families."
        )


# ─────────────────────────────────────────────────────────────────────────
# 8. Issue 5 — Inconsistent Responsiveness
# ─────────────────────────────────────────────────────────────────────────


class TestHomeListVirtualization:
    """The (tabs)/index.tsx dashboard must render its many sections through
    a virtualized list (FlatList) rather than a single ScrollView, so heavy
    cards don't all mount eagerly on slow devices."""

    SRC = "frontend/app/(tabs)/index.tsx"

    def test_uses_flatlist_not_scrollview(self):
        src = _read(self.SRC)
        assert "<FlatList" in src, "Home tab must render sections via FlatList."
        # Critical performance props
        for prop in (
            "keyExtractor",
            "getItemLayout",
            "initialNumToRender",
            "maxToRenderPerBatch",
            "windowSize",
        ):
            assert prop in src, f"Home FlatList must set {prop} for virtualization."

    def test_initial_render_window_is_bounded(self):
        src = _read(self.SRC)
        # initialNumToRender must be a small fixed number (not Infinity).
        assert "initialNumToRender={Infinity}" not in src
        assert "initialNumToRender={2}" in src or "initialNumToRender={3}" in src


class TestGlobalLayoutSystemBreakpoint:
    """useGLSBreakpoint must be the single source of truth for breakpoints —
    so layout shifts don't occur from multiple useWindowDimensions calls
    racing each other."""

    SRC = "frontend/src/components/layout/GlobalLayoutSystem.tsx"

    def test_useGLSBreakpoint_exported(self):
        src = _read(self.SRC)
        assert "export function useGLSBreakpoint(" in src

    def test_at_most_one_useWindowDimensions_call(self):
        """Multiple useWindowDimensions() calls fire after initial render
        and cause layout shift. They must all be funneled through the
        single useGLSBreakpoint() hook."""
        src = _read(self.SRC)
        # Count actual invocations (not the import).
        invocations = src.count("useWindowDimensions()")
        assert invocations <= 1, (
            f"Found {invocations} useWindowDimensions() invocations — must be "
            "at most 1, inside useGLSBreakpoint()."
        )

    def test_no_css_var_strings_in_style_values(self):
        """`var(--app-*)` strings resolve on web but are invalid on native.
        GLS must use direct color tokens from useTheme()."""
        src = _read(self.SRC)
        assert "var(--app-" not in src, (
            "GlobalLayoutSystem.tsx must not pass CSS var() strings into "
            "React Native style values — they break native targets."
        )


# ─────────────────────────────────────────────────────────────────────────
# 9. Issue 13 — Heavy-dashboard performance hardening
# ─────────────────────────────────────────────────────────────────────────


class TestPollVsWebSocketRaces:
    """Issue 13: any page that uses RealtimeContext for live updates must
    NOT also run a setInterval/useAutoRefresh poll — that creates the
    stale-overwrite race between WS data_change events and the poll's
    HTTP response."""

    FRONTEND = REPO_ROOT / "frontend"

    def _read(self, rel: str) -> str:
        return (self.FRONTEND / rel).read_text(encoding="utf-8")

    def test_interview_room_no_polling(self):
        src = self._read("app/interview-room.tsx")
        assert "setInterval(" not in src, (
            "interview-room.tsx must not setInterval-poll while a WebSocket "
            "is alive — rely on data_change events."
        )
        assert "useAutoRefresh(" not in src

    def test_ai_feature_dashboard_no_polling_uses_realtime(self):
        src = self._read("app/ai-feature-dashboard.tsx")
        assert "useRealtime" in src, (
            "ai-feature-dashboard must subscribe to RealtimeContext."
        )
        assert "useAutoRefresh(" not in src, (
            "ai-feature-dashboard must not poll while a WS is alive."
        )
        assert "setInterval(" not in src

    def test_admin_activity_log_no_polling_uses_realtime(self):
        src = self._read("app/admin-activity-log.tsx")
        assert "useRealtime" in src
        assert "useAutoRefresh(" not in src
        assert "setInterval(" not in src


class TestLiveQueryCache:
    """useLiveQuery must cache only in sessionStorage (not localStorage),
    and TTL-evict stale entries on read."""

    SRC = "frontend/src/hooks/useLiveQuery.ts"

    def test_no_localStorage_writes(self):
        src = _read(self.SRC)
        assert "localStorage.setItem" not in src, (
            "useLiveQuery must not persist snapshots to localStorage — "
            "use sessionStorage with TTL eviction."
        )

    def test_ttl_constant_and_eviction(self):
        src = _read(self.SRC)
        assert "LIVE_QUERY_CACHE_TTL_MS" in src, (
            "useLiveQuery must declare a TTL constant for snapshot eviction."
        )
        # The reader must remove the entry when stale.
        assert (
            "sessionStorage.removeItem" in src
        ), "useLiveQuery reader must remove stale entries on TTL expiry."


class TestSubscriptionAnalyticsFacet:
    """The admin subscription analytics endpoint must use a single $facet
    aggregation instead of 24 sequential count_documents() calls."""

    SRC = "backend/routes/admin_subscription_analytics.py"

    def test_uses_facet_aggregation(self):
        src = _read(self.SRC)
        assert "$facet" in src, (
            "admin_subscription_analytics must consolidate count queries via $facet."
        )
        # The shared helper must exist.
        assert "_count_many_facet" in src

    def test_no_24_sequential_count_documents_loop(self):
        """Look for the legacy pattern of a for-loop that issues
        count_documents() once per iteration."""
        src = _read(self.SRC)
        # The total count_documents calls in this file should now be small
        # (a handful of true one-offs are acceptable). The 24-query loop
        # would push it well above 15.
        count = src.count("count_documents(")
        assert count <= 12, (
            f"admin_subscription_analytics still has {count} count_documents() "
            "calls — consolidate them into a $facet aggregation."
        )


# ─────────────────────────────────────────────────────────────────────────
# 10. Redis operational sanity (regression: false-429 storms)
# ─────────────────────────────────────────────────────────────────────────


class TestRedisRateLimiterBackendAvailable:
    """If supervisor manages a Redis program, the redis-server binary must
    be installed. Otherwise the rate limiter falls back to an aggressive
    in-memory implementation that fires false 429 storms on bootstrap
    endpoints."""

    def test_supervisor_expects_redis(self):
        from pathlib import Path
        conf = Path("/etc/supervisor/conf.d/redis.conf")
        assert conf.exists(), "Supervisor must manage Redis."
        text = conf.read_text(encoding="utf-8")
        assert "redis-server" in text

    def test_redis_server_binary_installed(self):
        import shutil
        assert shutil.which("redis-server") is not None, (
            "Supervisor expects redis-server but the binary is missing. "
            "Install with: apt-get install -y redis-server"
        )


# ─────────────────────────────────────────────────────────────────────────
# 11. OpenAPI contract for enforcement-audit (carry-forward fix)
# ─────────────────────────────────────────────────────────────────────────


class TestEnforcementAuditOpenAPIContract:
    """`health_score` must be documented at the TOP LEVEL of the
    enforcement-audit response with the correct int/0-100 constraints."""

    SRC = "backend/routes/admin_subscription_analytics.py"

    def test_response_model_wired(self):
        src = _read(self.SRC)
        assert "response_model=SubscriptionEnforcementAuditResponse" in src
        # The Pydantic model must declare health_score with bounds
        assert "health_score: int = Field(..., ge=0, le=100" in src

    def test_model_imports_pydantic(self):
        src = _read(self.SRC)
        assert "from pydantic import BaseModel, Field" in src


# ─────────────────────────────────────────────────────────────────────────
# 12. scheduler_jobs Phase 2 domain split — first batch
# ─────────────────────────────────────────────────────────────────────────


class TestSchedulerJobsPhase2Utils:
    """`scheduler_jobs/utils.py` must hold the canonical implementations
    of the first batch of extracted helpers, and the facade + _legacy
    module must re-export them identically."""

    @staticmethod
    def _ensure_backend_on_path():
        import sys
        backend_dir = str((REPO_ROOT / "backend").resolve())
        if backend_dir not in sys.path:
            sys.path.insert(0, backend_dir)

    def test_utils_module_exists(self):
        from pathlib import Path
        assert (REPO_ROOT / "backend" / "scheduler_jobs" / "utils.py").exists()

    def test_canonical_functions_in_utils(self):
        self._ensure_backend_on_path()
        import importlib
        utils = importlib.import_module("scheduler_jobs.utils")
        for name in (
            "_slugify_weekly_careers",
            "_resolve_frontend_base_url",
            "_is_active_user_record",
        ):
            assert hasattr(utils, name), f"scheduler_jobs.utils missing {name}"

    def test_facade_reexports_are_identical(self):
        """`from scheduler_jobs import X` must resolve to the SAME function
        object as `from scheduler_jobs.utils import X` — otherwise we have
        a shadow definition somewhere."""
        self._ensure_backend_on_path()
        import importlib
        facade = importlib.import_module("scheduler_jobs")
        utils = importlib.import_module("scheduler_jobs.utils")
        for name in (
            "_slugify_weekly_careers",
            "_resolve_frontend_base_url",
            "_is_active_user_record",
        ):
            assert getattr(facade, name) is getattr(utils, name), (
                f"{name} differs between scheduler_jobs and scheduler_jobs.utils"
            )


class TestSchedulerJobsPhase2Observability:
    """Second Phase-2 batch — `scheduler_jobs/observability.py` holds the
    canonical `_record_scheduler_heartbeat` implementation, and the facade
    + legacy module re-export it identically."""

    @staticmethod
    def _ensure_backend_on_path():
        import sys
        backend_dir = str((REPO_ROOT / "backend").resolve())
        if backend_dir not in sys.path:
            sys.path.insert(0, backend_dir)

    def test_observability_module_exists(self):
        assert (REPO_ROOT / "backend" / "scheduler_jobs" / "observability.py").exists()

    def test_record_heartbeat_canonical_in_observability(self):
        self._ensure_backend_on_path()
        import importlib
        obs = importlib.import_module("scheduler_jobs.observability")
        assert hasattr(obs, "_record_scheduler_heartbeat")
        # The detail cap constant must be present (defends against future
        # accidental cap bumps that would blow up the heartbeat docs).
        assert hasattr(obs, "_HEARTBEAT_DETAIL_MAX_CHARS")
        assert obs._HEARTBEAT_DETAIL_MAX_CHARS == 400

    def test_facade_reexports_heartbeat_identical(self):
        self._ensure_backend_on_path()
        import importlib
        facade = importlib.import_module("scheduler_jobs")
        obs = importlib.import_module("scheduler_jobs.observability")
        assert facade._record_scheduler_heartbeat is obs._record_scheduler_heartbeat, (
            "scheduler_jobs._record_scheduler_heartbeat must resolve to the "
            "same function object as scheduler_jobs.observability._record_scheduler_heartbeat"
        )

    def test_record_heartbeat_swallows_db_errors(self):
        """The heartbeat MUST NOT raise — it's instrumentation, not critical path."""
        self._ensure_backend_on_path()
        import asyncio
        import importlib
        obs = importlib.import_module("scheduler_jobs.observability")
        # Even with `routes.db` perfectly fine, simply ensure calling with
        # broken parameters does not raise.
        result = asyncio.run(obs._record_scheduler_heartbeat("regression_test_job", "healthy", "x" * 1000))
        assert result is None


class TestSchedulerJobsPhase2WeeklyCareers:
    """Third Phase-2 batch — `scheduler_jobs/weekly_careers.py` owns the
    end-to-end weekly-careers automation pipeline (5 constants +
    fallback template list + 6 helpers + 1 entry point). All 13 public
    names must re-export identically through the facade."""

    PUBLIC_NAMES = (
        "WEEKLY_CAREERS_TEMPLATE_FLAG_KEY",
        "WEEKLY_CAREERS_AUTOMATION_STATE_KEY",
        "WEEKLY_CAREERS_AUTOMATION_RUNS_COLLECTION",
        "WEEKLY_CAREERS_JOB_HEARTBEAT_ID",
        "WEEKLY_CAREERS_FALLBACK_TEMPLATES",
        "_merge_weekly_careers_template",
        "_get_weekly_careers_template_config",
        "_build_weekly_careers_job_doc",
        "_select_weekly_careers_email_recipients",
        "_emit_weekly_careers_in_app_notifications",
        "_send_weekly_careers_emails",
        "scheduled_weekly_careers_job_creation_and_announcement",
    )

    @staticmethod
    def _ensure_backend_on_path():
        import sys
        backend_dir = str((REPO_ROOT / "backend").resolve())
        if backend_dir not in sys.path:
            sys.path.insert(0, backend_dir)

    def test_module_exists(self):
        assert (REPO_ROOT / "backend" / "scheduler_jobs" / "weekly_careers.py").exists()

    def test_canonical_names_in_module(self):
        self._ensure_backend_on_path()
        import importlib
        wc = importlib.import_module("scheduler_jobs.weekly_careers")
        for name in self.PUBLIC_NAMES:
            assert hasattr(wc, name), f"scheduler_jobs.weekly_careers missing {name}"

    def test_fallback_templates_has_three_entries(self):
        """The rotation logic depends on 3 fallback templates."""
        self._ensure_backend_on_path()
        import importlib
        wc = importlib.import_module("scheduler_jobs.weekly_careers")
        assert isinstance(wc.WEEKLY_CAREERS_FALLBACK_TEMPLATES, list)
        assert len(wc.WEEKLY_CAREERS_FALLBACK_TEMPLATES) == 3
        for tpl in wc.WEEKLY_CAREERS_FALLBACK_TEMPLATES:
            for required in ("slug_base", "title", "department", "location", "type"):
                assert required in tpl, f"Fallback template missing {required}"

    def test_facade_reexports_identical(self):
        """`from scheduler_jobs import X` must resolve to the SAME object
        as `from scheduler_jobs.weekly_careers import X` for all 12 names."""
        self._ensure_backend_on_path()
        import importlib
        facade = importlib.import_module("scheduler_jobs")
        wc = importlib.import_module("scheduler_jobs.weekly_careers")
        for name in self.PUBLIC_NAMES:
            assert getattr(facade, name) is getattr(wc, name), (
                f"{name} differs between scheduler_jobs facade and "
                "scheduler_jobs.weekly_careers — silent shadow definition somewhere."
            )

    def test_legacy_no_longer_has_inline_definitions(self):
        """`_legacy.py` must NOT redeclare these names — they should only
        appear as `from scheduler_jobs.weekly_careers import …`."""
        legacy_path = REPO_ROOT / "backend" / "scheduler_jobs" / "misc.py"
        src = legacy_path.read_text(encoding="utf-8")
        for name in (
            "_merge_weekly_careers_template",
            "_build_weekly_careers_job_doc",
            "_emit_weekly_careers_in_app_notifications",
            "_send_weekly_careers_emails",
            "scheduled_weekly_careers_job_creation_and_announcement",
        ):
            # `def name(` or `async def name(` must NOT appear in _legacy.py
            assert f"def {name}(" not in src, (
                f"_legacy.py still has an inline `def {name}(` — should be "
                "imported from scheduler_jobs.weekly_careers instead."
            )

    def test_template_merge_and_doc_build(self):
        """Sanity: the public helpers actually work end-to-end with no DB."""
        self._ensure_backend_on_path()
        from datetime import datetime, timezone
        import importlib
        wc = importlib.import_module("scheduler_jobs.weekly_careers")

        # Merge with no override yields a fully populated template.
        merged = wc._merge_weekly_careers_template(wc.WEEKLY_CAREERS_FALLBACK_TEMPLATES[0], {})
        for key in ("slug_base", "title", "department", "location", "type", "status"):
            assert merged.get(key), f"Merged template missing {key}"
        assert merged["status"] == "open"

        # Build doc produces a slug + automation block.
        now = datetime(2026, 1, 5, tzinfo=timezone.utc)
        doc = wc._build_weekly_careers_job_doc(merged, now, "admin@x.com", "2026W02")
        assert doc["slug"].endswith("-2026w02")
        assert doc["automation"]["week_key"] == "2026W02"
        assert doc["job_id"].startswith("job_")


class TestSchedulerJobsPhase2Security:
    """Fourth Phase-2 batch — `scheduler_jobs/security.py` owns the
    security audit / enforcement / GTEC C5 scheduled jobs."""

    PUBLIC_NAMES = (
        "scheduled_release_intelligence_monitor",
        "scheduled_production_security_policy_gate",
        "scheduled_zero_trust_auto_mitigation",
        "scheduled_zero_trust_daily_email_digest",
        "scheduled_security_incident_runbook_monitor",
    )

    @staticmethod
    def _ensure_backend_on_path():
        import sys
        backend_dir = str((REPO_ROOT / "backend").resolve())
        if backend_dir not in sys.path:
            sys.path.insert(0, backend_dir)

    def test_module_exists(self):
        assert (REPO_ROOT / "backend" / "scheduler_jobs" / "security.py").exists()

    def test_canonical_names_in_module(self):
        self._ensure_backend_on_path()
        import importlib
        sec = importlib.import_module("scheduler_jobs.security")
        for name in self.PUBLIC_NAMES:
            assert hasattr(sec, name), f"scheduler_jobs.security missing {name}"

    def test_facade_reexports_identical(self):
        self._ensure_backend_on_path()
        import importlib
        facade = importlib.import_module("scheduler_jobs")
        sec = importlib.import_module("scheduler_jobs.security")
        for name in self.PUBLIC_NAMES:
            assert getattr(facade, name) is getattr(sec, name), (
                f"{name} differs between scheduler_jobs facade and "
                "scheduler_jobs.security — silent shadow definition somewhere."
            )

    def test_legacy_no_longer_has_inline_definitions(self):
        legacy_path = REPO_ROOT / "backend" / "scheduler_jobs" / "misc.py"
        src = legacy_path.read_text(encoding="utf-8")
        for name in self.PUBLIC_NAMES:
            assert f"async def {name}(" not in src, (
                f"_legacy.py still has an inline `async def {name}(` — should "
                "be imported from scheduler_jobs.security instead."
            )


class TestSchedulerJobsPhase2Digests:
    """Fifth Phase-2 batch — `scheduler_jobs/digests.py` owns the weekly
    quality digest pipeline (1 entry point + 1 helper)."""

    PUBLIC_NAMES = (
        "_send_weekly_quality_digest",
        "scheduled_weekly_quality_digest",
    )

    @staticmethod
    def _ensure_backend_on_path():
        import sys
        backend_dir = str((REPO_ROOT / "backend").resolve())
        if backend_dir not in sys.path:
            sys.path.insert(0, backend_dir)

    def test_module_exists(self):
        assert (REPO_ROOT / "backend" / "scheduler_jobs" / "digests.py").exists()

    def test_canonical_names_in_module(self):
        self._ensure_backend_on_path()
        import importlib
        m = importlib.import_module("scheduler_jobs.digests")
        for name in self.PUBLIC_NAMES:
            assert hasattr(m, name), f"scheduler_jobs.digests missing {name}"

    def test_facade_reexports_identical(self):
        self._ensure_backend_on_path()
        import importlib
        facade = importlib.import_module("scheduler_jobs")
        m = importlib.import_module("scheduler_jobs.digests")
        for name in self.PUBLIC_NAMES:
            assert getattr(facade, name) is getattr(m, name), (
                f"{name} differs between facade and scheduler_jobs.digests"
            )

    def test_legacy_no_longer_has_inline_definitions(self):
        legacy_path = REPO_ROOT / "backend" / "scheduler_jobs" / "misc.py"
        src = legacy_path.read_text(encoding="utf-8")
        for name in self.PUBLIC_NAMES:
            assert f"async def {name}(" not in src, (
                f"_legacy.py still has `async def {name}(` — should be "
                "imported from scheduler_jobs.digests instead."
            )


class TestSchedulerJobsPhase2Payments:
    """Sixth Phase-2 batch — `scheduler_jobs/payments.py` owns billing
    automation jobs (bill generator, FedaPay webhook self-heal, dunning)."""

    PUBLIC_NAMES = (
        "scheduled_bill_generator_hourly_daemon",
        "scheduled_fedapay_webhook_self_heal",
        "scheduled_invoice_dunning",
    )

    @staticmethod
    def _ensure_backend_on_path():
        import sys
        backend_dir = str((REPO_ROOT / "backend").resolve())
        if backend_dir not in sys.path:
            sys.path.insert(0, backend_dir)

    def test_module_exists(self):
        assert (REPO_ROOT / "backend" / "scheduler_jobs" / "payments.py").exists()

    def test_canonical_names_in_module(self):
        self._ensure_backend_on_path()
        import importlib
        m = importlib.import_module("scheduler_jobs.payments")
        for name in self.PUBLIC_NAMES:
            assert hasattr(m, name), f"scheduler_jobs.payments missing {name}"

    def test_facade_reexports_identical(self):
        self._ensure_backend_on_path()
        import importlib
        facade = importlib.import_module("scheduler_jobs")
        m = importlib.import_module("scheduler_jobs.payments")
        for name in self.PUBLIC_NAMES:
            assert getattr(facade, name) is getattr(m, name), (
                f"{name} differs between facade and scheduler_jobs.payments"
            )

    def test_legacy_no_longer_has_inline_definitions(self):
        legacy_path = REPO_ROOT / "backend" / "scheduler_jobs" / "misc.py"
        src = legacy_path.read_text(encoding="utf-8")
        for name in self.PUBLIC_NAMES:
            assert f"async def {name}(" not in src, (
                f"_legacy.py still has `async def {name}(` — should be "
                "imported from scheduler_jobs.payments instead."
            )


class TestSchedulerJobsPhase2Content:
    """Seventh Phase-2 batch — `scheduler_jobs/content.py` owns content
    automation jobs. Currently scoped to the daily watch-videos drop."""

    PUBLIC_NAMES = ("scheduled_watch_videos_daily_drop",)

    @staticmethod
    def _ensure_backend_on_path():
        import sys
        backend_dir = str((REPO_ROOT / "backend").resolve())
        if backend_dir not in sys.path:
            sys.path.insert(0, backend_dir)

    def test_module_exists(self):
        assert (REPO_ROOT / "backend" / "scheduler_jobs" / "content.py").exists()

    def test_canonical_names_in_module(self):
        self._ensure_backend_on_path()
        import importlib
        m = importlib.import_module("scheduler_jobs.content")
        for name in self.PUBLIC_NAMES:
            assert hasattr(m, name), f"scheduler_jobs.content missing {name}"

    def test_facade_reexports_identical(self):
        self._ensure_backend_on_path()
        import importlib
        facade = importlib.import_module("scheduler_jobs")
        m = importlib.import_module("scheduler_jobs.content")
        for name in self.PUBLIC_NAMES:
            assert getattr(facade, name) is getattr(m, name)

    def test_legacy_no_longer_has_inline_definitions(self):
        legacy_path = REPO_ROOT / "backend" / "scheduler_jobs" / "misc.py"
        src = legacy_path.read_text(encoding="utf-8")
        for name in self.PUBLIC_NAMES:
            assert f"async def {name}(" not in src, (
                f"_legacy.py still has `async def {name}(` — should be "
                "imported from scheduler_jobs.content instead."
            )


class TestSchedulerJobsPhase2Learning:
    """Eighth Phase-2 batch — `scheduler_jobs/learning.py` owns the
    AI Learning Hub recurring jobs (anchoring, integrity, autopublish,
    video maintenance, assurance, email queue, synthetic canary)."""

    PUBLIC_NAMES = (
        "scheduled_learning_certificate_anchor_batch",
        "scheduled_learning_hub_integrity_guard",
        "scheduled_learning_hub_weekly_autopublish",
        "scheduled_learning_hub_video_maintenance",
        "scheduled_learning_hub_assurance_guard",
        "scheduled_learning_hub_email_dispatcher",
        "scheduled_learning_hub_synthetic_canary",
    )

    @staticmethod
    def _ensure_backend_on_path():
        import sys
        backend_dir = str((REPO_ROOT / "backend").resolve())
        if backend_dir not in sys.path:
            sys.path.insert(0, backend_dir)

    def test_module_exists(self):
        assert (REPO_ROOT / "backend" / "scheduler_jobs" / "learning.py").exists()

    def test_canonical_names_in_module(self):
        self._ensure_backend_on_path()
        import importlib
        m = importlib.import_module("scheduler_jobs.learning")
        for name in self.PUBLIC_NAMES:
            assert hasattr(m, name), f"scheduler_jobs.learning missing {name}"

    def test_facade_reexports_identical(self):
        self._ensure_backend_on_path()
        import importlib
        facade = importlib.import_module("scheduler_jobs")
        m = importlib.import_module("scheduler_jobs.learning")
        for name in self.PUBLIC_NAMES:
            assert getattr(facade, name) is getattr(m, name), (
                f"{name} differs between facade and scheduler_jobs.learning"
            )

    def test_legacy_no_longer_has_inline_definitions(self):
        legacy_path = REPO_ROOT / "backend" / "scheduler_jobs" / "misc.py"
        src = legacy_path.read_text(encoding="utf-8")
        for name in self.PUBLIC_NAMES:
            assert f"async def {name}(" not in src, (
                f"_legacy.py still has `async def {name}(` — should be "
                "imported from scheduler_jobs.learning instead."
            )


class TestSchedulerJobsPhase2BatchedExtractions:
    """Batches #9-#12 — SSO/auth health, visual audits, preview cache,
    global parity. Generic facade-identity + no-inline-leftover check
    across the 13 newly-extracted job names."""

    CLUSTERS = {
        "sso_auth_health": (
            "scheduled_sso_redirect_auto_sync",
            "scheduled_sso_provider_registration_alignment_auto",
            "scheduled_sso_e2e_validation_alerts",
            "scheduled_sso_redirect_drift_sentinel",
            "scheduled_multi_region_auth_probe",
            "scheduled_auth_fallback_link_guardian",
            "scheduled_admin_e2e_health_gate",
        ),
        "visual_audits": (
            "scheduled_fee_visibility_visual_audit_hourly",
            "scheduled_fee_visibility_visual_audit_nightly",
        ),
        "preview_cache": (
            "scheduled_preview_cache_hygiene_hourly",
            "scheduled_preview_cache_hygiene_nightly",
        ),
        "global_parity": (
            "scheduled_global_parity_audit_hourly",
            "scheduled_global_parity_audit_nightly",
        ),
    }

    @staticmethod
    def _ensure_backend_on_path():
        import sys
        backend_dir = str((REPO_ROOT / "backend").resolve())
        if backend_dir not in sys.path:
            sys.path.insert(0, backend_dir)

    def test_all_modules_exist(self):
        for cluster in self.CLUSTERS:
            assert (REPO_ROOT / "backend" / "scheduler_jobs" / f"{cluster}.py").exists(), (
                f"scheduler_jobs/{cluster}.py is missing"
            )

    def test_canonical_names_in_modules(self):
        self._ensure_backend_on_path()
        import importlib
        for cluster, names in self.CLUSTERS.items():
            m = importlib.import_module(f"scheduler_jobs.{cluster}")
            for name in names:
                assert hasattr(m, name), f"scheduler_jobs.{cluster} missing {name}"

    def test_facade_reexports_identical(self):
        self._ensure_backend_on_path()
        import importlib
        facade = importlib.import_module("scheduler_jobs")
        for cluster, names in self.CLUSTERS.items():
            m = importlib.import_module(f"scheduler_jobs.{cluster}")
            for name in names:
                assert getattr(facade, name) is getattr(m, name), (
                    f"{name} differs between facade and scheduler_jobs.{cluster}"
                )

    def test_legacy_no_longer_has_inline_definitions(self):
        legacy_path = REPO_ROOT / "backend" / "scheduler_jobs" / "misc.py"
        src = legacy_path.read_text(encoding="utf-8")
        for cluster, names in self.CLUSTERS.items():
            for name in names:
                assert f"async def {name}(" not in src, (
                    f"_legacy.py still has `async def {name}(` — should be "
                    f"imported from scheduler_jobs.{cluster} instead."
                )


class TestSchedulerJobsPhase2ThemeGuardrails:
    """Batch #13 — `scheduler_jobs/theme_guardrails.py` owns the 4
    recurring theme-system hygiene jobs."""

    PUBLIC_NAMES = (
        "scheduled_theme_guardrail_scan",
        "scheduled_theme_drift_nightly_detector",
        "scheduled_admin_tabs_theme_drift_report",
        "scheduled_admin_tabs_theme_drift_weekly_digest",
    )

    @staticmethod
    def _ensure_backend_on_path():
        import sys
        backend_dir = str((REPO_ROOT / "backend").resolve())
        if backend_dir not in sys.path:
            sys.path.insert(0, backend_dir)

    def test_module_exists(self):
        assert (REPO_ROOT / "backend" / "scheduler_jobs" / "theme_guardrails.py").exists()

    def test_canonical_names_in_module(self):
        self._ensure_backend_on_path()
        import importlib
        m = importlib.import_module("scheduler_jobs.theme_guardrails")
        for name in self.PUBLIC_NAMES:
            assert hasattr(m, name), f"scheduler_jobs.theme_guardrails missing {name}"

    def test_facade_reexports_identical(self):
        self._ensure_backend_on_path()
        import importlib
        facade = importlib.import_module("scheduler_jobs")
        m = importlib.import_module("scheduler_jobs.theme_guardrails")
        for name in self.PUBLIC_NAMES:
            assert getattr(facade, name) is getattr(m, name)

    def test_legacy_no_longer_has_inline_definitions(self):
        legacy_path = REPO_ROOT / "backend" / "scheduler_jobs" / "misc.py"
        src = legacy_path.read_text(encoding="utf-8")
        for name in self.PUBLIC_NAMES:
            assert f"async def {name}(" not in src, (
                f"_legacy.py still has `async def {name}(` — should be "
                "imported from scheduler_jobs.theme_guardrails instead."
            )


class TestSchedulerJobsPhase2BatchedExtractions2:
    """Batches #14-#18 — key rotation, engagement, enterprise enforcement,
    pricing, i18n/accessibility. Generic facade-identity + no-inline-leftover
    check across all 18 newly-extracted job names."""

    CLUSTERS = {
        "key_rotation": (
            "scheduled_key_rotation_policy_attestation",
            "scheduled_key_rotation_game_day_staleness_guard",
            "scheduled_key_rotation_compliance_bundle_autogen",
            "scheduled_key_rotation_status_drift_monitor",
        ),
        "engagement": (
            "scheduled_weekly_engagement_emails",
            "scheduled_referral_weekly_email",
            "scheduled_card_expiry_check",
            "scheduled_welcome_back_check",
        ),
        "enterprise_enforcement": (
            "scheduled_enterprise_lock_cycle",
            "scheduled_slo_breach_auto_mitigation",
            "scheduled_weekly_enterprise_standard_enforcement",
            "scheduled_global_rbac_subscription_enforcement",
            "scheduled_quarterly_access_recertification",
        ),
        "pricing": (
            "scheduled_subscription_plan_guardrail",
            "scheduled_pricing_guard_nightly_monitor",
        ),
        "i18n_accessibility": (
            "scheduled_i18n_literal_autofix_dry_run_report",
            "scheduled_weekly_email_contrast_compliance",
            "scheduled_nightly_darkmode_regression_scan",
        ),
    }

    @staticmethod
    def _ensure_backend_on_path():
        import sys
        backend_dir = str((REPO_ROOT / "backend").resolve())
        if backend_dir not in sys.path:
            sys.path.insert(0, backend_dir)

    def test_all_modules_exist(self):
        for cluster in self.CLUSTERS:
            assert (REPO_ROOT / "backend" / "scheduler_jobs" / f"{cluster}.py").exists(), (
                f"scheduler_jobs/{cluster}.py is missing"
            )

    def test_canonical_names_in_modules(self):
        self._ensure_backend_on_path()
        import importlib
        for cluster, names in self.CLUSTERS.items():
            m = importlib.import_module(f"scheduler_jobs.{cluster}")
            for name in names:
                assert hasattr(m, name), f"scheduler_jobs.{cluster} missing {name}"

    def test_facade_reexports_identical(self):
        self._ensure_backend_on_path()
        import importlib
        facade = importlib.import_module("scheduler_jobs")
        for cluster, names in self.CLUSTERS.items():
            m = importlib.import_module(f"scheduler_jobs.{cluster}")
            for name in names:
                assert getattr(facade, name) is getattr(m, name), (
                    f"{name} differs between facade and scheduler_jobs.{cluster}"
                )

    def test_legacy_no_longer_has_inline_definitions(self):
        legacy_path = REPO_ROOT / "backend" / "scheduler_jobs" / "misc.py"
        src = legacy_path.read_text(encoding="utf-8")
        for cluster, names in self.CLUSTERS.items():
            for name in names:
                assert f"async def {name}(" not in src, (
                    f"_legacy.py still has `async def {name}(` — should be "
                    f"imported from scheduler_jobs.{cluster} instead."
                )



# ─────────────────────────────────────────────────────────────────────────
# 13. Phase 2 finalization — CI guard for misc.py
# ─────────────────────────────────────────────────────────────────────────


class TestSchedulerJobsMiscPyGuard:
    """Phase 2 finalization — `misc.py` regression guard.
    
    After the complete Phase 2 domain split (batches #1-#24), the old
    `_legacy.py` was renamed to `misc.py` and should only hold the 2
    non-scheduled job functions (check_meeting_reminders and 
    run_auto_response_scan). This test ensures no new `scheduled_*` 
    jobs drift back into `misc.py` without proper domain extraction.
    """

    @staticmethod
    def _ensure_backend_on_path():
        import sys
        backend_dir = str((REPO_ROOT / "backend").resolve())
        if backend_dir not in sys.path:
            sys.path.insert(0, backend_dir)

    def test_legacy_py_file_no_longer_exists(self):
        """The old `_legacy.py` monolith must not be resurrected."""
        legacy_file = REPO_ROOT / "backend" / "scheduler_jobs" / "_legacy.py"
        assert not legacy_file.exists(), (
            "scheduler_jobs/_legacy.py exists — this file was renamed to "
            "misc.py in Phase 2 batch #24 and must never be recreated."
        )

    def test_no_scheduled_functions_defined_in_misc_py(self):
        """misc.py must not contain any inline `def scheduled_*` or 
        `async def scheduled_*` definitions. All scheduled jobs must live
        in their respective domain modules."""
        misc_path = REPO_ROOT / "backend" / "scheduler_jobs" / "misc.py"
        src = misc_path.read_text(encoding="utf-8")
        
        # Scan for any inline scheduled_* function definitions
        import re
        pattern = r"^(?:async\s+)?def\s+(scheduled_\w+)\s*\("
        matches = re.findall(pattern, src, re.MULTILINE)
        
        assert not matches, (
            f"misc.py contains inline scheduled_* function(s): {matches}. "
            "All scheduled jobs must be defined in domain-specific modules "
            "(platform_health.py, security.py, etc.) and only re-imported "
            "in misc.py if necessary."
        )

    def test_no_scheduled_symbols_resolve_to_misc(self):
        """When importing `scheduled_*` names from the scheduler_jobs facade,
        NONE should resolve to `scheduler_jobs.misc` as their canonical module.
        All scheduled jobs must originate from domain modules."""
        self._ensure_backend_on_path()
        import importlib
        facade = importlib.import_module("scheduler_jobs")
        
        # Collect all scheduled_* exports from the facade
        scheduled_names = [
            name for name in dir(facade)
            if name.startswith("scheduled_")
        ]
        
        assert len(scheduled_names) > 50, (
            f"Expected 70+ scheduled_* jobs, found only {len(scheduled_names)}. "
            "This might indicate a facade regression."
        )
        
        # Verify NONE resolve to misc.py as their canonical home
        misc_jobs = []
        for name in scheduled_names:
            obj = getattr(facade, name)
            if not callable(obj):
                continue
            module = getattr(obj, "__module__", "")
            if module == "scheduler_jobs.misc":
                misc_jobs.append(name)
        
        assert not misc_jobs, (
            f"Found {len(misc_jobs)} scheduled_* job(s) resolving to "
            f"scheduler_jobs.misc: {misc_jobs[:10]}. All scheduled jobs must "
            "be canonically defined in domain modules (platform_health.py, "
            "security_defense.py, compliance.py, etc.), NOT in misc.py."
        )
