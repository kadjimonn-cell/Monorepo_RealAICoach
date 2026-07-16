"""Scanning and auto-fix helpers for platform health routes."""

from datetime import datetime, timezone
import glob
import os
import re
import subprocess
from typing import Any, Dict, List, Sequence

from routes.db import db


def scan_files_for_patterns(
    base_dirs: List[str],
    patterns: List[str],
    extensions: List[str],
    *,
    safe_pattern: str,
    skip_dirs: Sequence[str],
) -> List[Dict[str, Any]]:
    """Scan source files for stale URL patterns."""
    issues: List[Dict[str, Any]] = []
    skip_dir_set = set(skip_dirs)
    for base_dir in base_dirs:
        if not os.path.exists(base_dir):
            continue
        for root, dirs, files in os.walk(base_dir):
            dirs[:] = [d for d in dirs if d not in skip_dir_set]
            for fname in files:
                if not any(fname.endswith(ext) for ext in extensions):
                    continue
                fpath = os.path.join(root, fname)
                try:
                    with open(fpath, "r", errors="ignore") as file_handle:
                        content = file_handle.read()
                        lines = content.split("\n")
                    has_safe_base = safe_pattern in content and "/api" in content
                    for index, line in enumerate(lines):
                        for pattern in patterns:
                            if not re.search(pattern, line):
                                continue
                            if safe_pattern in line:
                                continue
                            if has_safe_base and re.match(r"^\s*const\s+\w+\s*=\s*process\.env\.\w+;\s*$", line):
                                continue
                            issues.append(
                                {
                                    "file": fpath.replace("/app/frontend/", ""),
                                    "line": index + 1,
                                    "code": line.strip()[:120],
                                    "pattern": pattern.split(r"\.")[2] if r"\." in pattern else pattern[:40],
                                    "severity": "high" if "wss://" in line or "ws://" in line else "medium",
                                    "fixable": True,
                                }
                            )
                except Exception:
                    pass
    return issues


def check_build_staleness(frontend_dist: str, frontend_src: str, frontend_app: str, skip_dirs: Sequence[str]) -> Dict[str, Any]:
    """Check if the production build is stale compared to source."""
    dist_dir = os.path.join(frontend_dist, "client")
    if not os.path.exists(dist_dir):
        return {"status": "missing", "age_hours": -1, "stale": True, "message": "No production build found"}

    build_time = os.path.getmtime(dist_dir)
    build_dt = datetime.fromtimestamp(build_time, tz=timezone.utc)
    age = datetime.now(timezone.utc) - build_dt
    age_hours = age.total_seconds() / 3600

    newest_source = 0.0
    skip_dir_set = set(skip_dirs)
    for base in [frontend_src, frontend_app]:
        if not os.path.exists(base):
            continue
        for root, dirs, files in os.walk(base):
            dirs[:] = [d for d in dirs if d not in skip_dir_set]
            for fname in files:
                if any(fname.endswith(ext) for ext in [".tsx", ".ts", ".js", ".jsx"]):
                    newest_source = max(newest_source, os.path.getmtime(os.path.join(root, fname)))

    source_newer = newest_source > build_time if newest_source > 0 else False

    stale_in_build = False
    index_files = glob.glob(os.path.join(dist_dir, "_expo/static/js/web/index-*.js"))
    for idx_file in index_files:
        try:
            result = subprocess.run(
                ["grep", "-c", "form-submission-fix\\|js-scanner-suite", idx_file],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.stdout.strip() != "0":
                stale_in_build = True
        except Exception:
            pass

    stale = source_newer or stale_in_build or age_hours > 168
    return {
        "status": "stale" if stale else "fresh",
        "build_time": build_dt.isoformat(),
        "age_hours": round(age_hours, 1),
        "source_newer_than_build": source_newer,
        "stale_domains_in_build": stale_in_build,
        "stale": stale,
        "message": (
            "Stale domains found in build" if stale_in_build
            else "Source files newer than build" if source_newer
            else "Build older than 7 days" if age_hours > 168
            else "Build is fresh"
        ),
    }


def check_cache_health(cache_dirs: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Check age and size of various caches."""
    results: List[Dict[str, Any]] = []
    for cache in cache_dirs:
        path = cache["path"]
        if not os.path.exists(path):
            results.append(
                {
                    "label": cache["label"],
                    "path": path.replace("/app/frontend/", ""),
                    "exists": False,
                    "size_mb": 0,
                    "age_hours": 0,
                    "status": "clean",
                    "stale": False,
                }
            )
            continue

        total_size = 0
        try:
            for root, dirs, files in os.walk(path):
                _ = dirs
                for file_name in files:
                    file_path = os.path.join(root, file_name)
                    try:
                        total_size += os.path.getsize(file_path)
                    except OSError:
                        pass
        except Exception:
            pass
        size_mb = round(total_size / (1024 * 1024), 1)

        mtime = os.path.getmtime(path)
        age = datetime.now(timezone.utc) - datetime.fromtimestamp(mtime, tz=timezone.utc)
        age_hours = round(age.total_seconds() / 3600, 1)

        is_dist = "dist" in path
        stale = (not is_dist and age_hours > 168) or (not is_dist and size_mb > 500)

        results.append(
            {
                "label": cache["label"],
                "path": path.replace("/app/frontend/", ""),
                "exists": True,
                "size_mb": size_mb,
                "age_hours": age_hours,
                "status": "stale" if stale else "healthy",
                "stale": stale,
            }
        )
    return results


def check_env_consistency(frontend_root: str, backend_env: str = "/app/backend/.env") -> Dict[str, Any]:
    """Check that .env files have consistent and valid URLs."""
    issues = []
    frontend_env = os.path.join(frontend_root, ".env")

    frontend_url = ""
    react_backend_url = ""
    expo_backend_url = ""
    if os.path.exists(frontend_env):
        with open(frontend_env) as file_handle:
            for line in file_handle:
                if line.startswith("REACT_APP_BACKEND_URL=") or line.startswith("EXPO_PUBLIC_BACKEND_URL="):
                    value = line.split("=", 1)[1].strip()
                    key = line.split("=", 1)[0].strip()
                    if key == "REACT_APP_BACKEND_URL":
                        react_backend_url = value
                    if key == "EXPO_PUBLIC_BACKEND_URL":
                        expo_backend_url = value
                    frontend_url = react_backend_url or expo_backend_url
                    if not value.startswith("https://"):
                        issues.append({"field": key, "issue": "URL does not use HTTPS", "severity": "high"})

    if react_backend_url and expo_backend_url:
        react_host = react_backend_url.split("://", 1)[-1].split("/", 1)[0].lower()
        expo_host = expo_backend_url.split("://", 1)[-1].split("/", 1)[0].lower()
        if react_host != expo_host:
            issues.append(
                {
                    "field": "REACT_APP_BACKEND_URL/EXPO_PUBLIC_BACKEND_URL",
                    "issue": f"Backend host mismatch ({react_host} != {expo_host})",
                    "severity": "critical",
                }
            )

    if os.path.exists(backend_env):
        with open(backend_env) as file_handle:
            content = file_handle.read()
            if "MONGO_URL" not in content:
                issues.append({"field": "MONGO_URL", "issue": "Missing from backend .env", "severity": "critical"})

    return {
        "frontend_url": frontend_url,
        "react_backend_url": react_backend_url,
        "expo_backend_url": expo_backend_url,
        "issues": issues,
        "status": "error" if any(issue["severity"] == "critical" for issue in issues) else "warning" if issues else "healthy",
    }


def compute_health_score(stale_urls: List[Dict[str, Any]], build_info: Dict[str, Any], cache_health: List[Dict[str, Any]], env_info: Dict[str, Any]) -> int:
    """Compute overall platform health score 0-100."""
    score = 100

    for issue in stale_urls:
        score -= 5 if issue["severity"] == "high" else 3

    if build_info["stale"]:
        if build_info.get("stale_domains_in_build"):
            score -= 25
        elif build_info.get("source_newer_than_build"):
            score -= 15
        else:
            score -= 5

    for cache in cache_health:
        if cache["stale"]:
            score -= 5

    for issue in env_info.get("issues", []):
        score -= 10 if issue["severity"] == "critical" else 5

    return max(0, min(100, score))


def auto_fix_stale_urls(issues: List[Dict[str, Any]], frontend_root: str = "/app/frontend") -> Dict[str, Any]:
    """Auto-fix stale URL patterns by replacing with window.location.origin."""
    fixed_files = []
    failed_files = []

    for issue in issues:
        if not issue.get("fixable"):
            continue
        file_path = os.path.join(frontend_root, issue["file"])
        if not os.path.exists(file_path):
            failed_files.append({"file": issue["file"], "reason": "File not found"})
            continue

        try:
            with open(file_path, "r") as file_handle:
                content = file_handle.read()

            original = content
            content = re.sub(
                r"(const\s+\w+\s*=\s*)process\.env\.EXPO_PUBLIC_BACKEND_URL\s*\|\|\s*''",
                r"\1typeof window !== 'undefined' && window.location?.origin ? window.location.origin : (process.env.EXPO_PUBLIC_BACKEND_URL || '')",
                content,
            )
            content = re.sub(
                r"(const\s+\w+\s*=\s*)process\.env\.REACT_APP_BACKEND_URL\s*\|\|\s*''",
                r"\1typeof window !== 'undefined' && window.location?.origin ? window.location.origin : (process.env.REACT_APP_BACKEND_URL || '')",
                content,
            )
            content = re.sub(
                r"(const\s+\w+\s*=\s*)process\.env\.EXPO_PUBLIC_BACKEND_URL\s*\|\|\s*process\.env\.REACT_APP_BACKEND_URL\s*\|\|\s*''",
                r"\1typeof window !== 'undefined' && window.location?.origin ? window.location.origin : (process.env.EXPO_PUBLIC_BACKEND_URL || process.env.REACT_APP_BACKEND_URL || '')",
                content,
            )
            content = re.sub(
                r"(const\s+\w+\s*=\s*)process\.env\.REACT_APP_BACKEND_URL\s*\|\|\s*process\.env\.EXPO_PUBLIC_BACKEND_URL\s*\|\|\s*''",
                r"\1typeof window !== 'undefined' && window.location?.origin ? window.location.origin : (process.env.REACT_APP_BACKEND_URL || process.env.EXPO_PUBLIC_BACKEND_URL || '')",
                content,
            )
            content = re.sub(
                r"\(process\.env\.EXPO_PUBLIC_BACKEND_URL\s*\|\|\s*''\)\.replace\('https://',\s*'wss://'\)\.replace\('http://',\s*'ws://'\)",
                "(typeof window !== 'undefined' && window.location?.origin ? window.location.origin : (process.env.EXPO_PUBLIC_BACKEND_URL || '')).replace('https://', 'wss://').replace('http://', 'ws://')",
                content,
            )

            if content != original:
                with open(file_path, "w") as file_handle:
                    file_handle.write(content)
                fixed_files.append(issue["file"])
            else:
                failed_files.append({"file": issue["file"], "reason": "No matching pattern to fix"})
        except Exception as exc:
            failed_files.append({"file": issue["file"], "reason": str(exc)[:80]})

    return {"fixed": fixed_files, "failed": failed_files, "fixed_count": len(fixed_files)}


def auto_fix_caches(stale_caches: List[Dict[str, Any]], frontend_root: str = "/app/frontend") -> List[str]:
    """Clear stale caches (excluding dist)."""
    cleared = []
    for cache in stale_caches:
        if not cache["stale"] or "dist" in cache["path"]:
            continue
        full_path = os.path.join(frontend_root, cache["path"])
        if os.path.exists(full_path):
            try:
                subprocess.run(["rm", "-rf", full_path], timeout=30)
                cleared.append(cache["label"])
            except Exception:
                pass
    return cleared


async def store_scan_result(result: Dict[str, Any]):
    """Store scan result in database."""
    to_store = {**result, "_stored_at": datetime.now(timezone.utc).isoformat()}
    await db.platform_health_scans.insert_one(to_store)