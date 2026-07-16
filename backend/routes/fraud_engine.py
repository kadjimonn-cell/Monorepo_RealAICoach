"""Advanced Fraud Detection Engine — ML-powered behavioral anomaly scoring.

Uses Isolation Forest ML model + statistical z-score anomaly detection
across multiple behavioral signals to flag suspicious activity patterns.

API:
- GET  /api/admin/fraud/dashboard  — Executive fraud dashboard with ML metrics
- POST /api/admin/fraud/run-scan   — Trigger a manual ML-enhanced scan
- GET  /api/admin/fraud/user/{uid} — Per-user risk profile with history
- POST /api/admin/fraud/dismiss/{uid} — Dismiss/acknowledge a flagged user
"""

from fastapi import APIRouter, HTTPException, Request
from datetime import datetime, timezone, timedelta
import logging
import math
import numpy as np

from routes.db import db, get_current_user

logger = logging.getLogger(__name__)
router = APIRouter()

RISK_WEIGHTS = {
    "rapid_login_failures": 30,
    "multiple_ips": 15,
    "rapid_account_creation": 25,
    "payment_anomaly": 35,
    "unusual_hours": 10,
    "high_api_volume": 20,
    "session_hijack_risk": 40,
}

Z_SCORE_WARNING = 2.0
Z_SCORE_CRITICAL = 3.0


def _zscore(value: float, mean: float, std: float) -> float:
    if std == 0:
        return 0.0
    return abs((value - mean) / std)


def _sigmoid(x: float) -> float:
    return 100 / (1 + math.exp(-0.05 * (x - 50)))


class IsolationForestLite:
    """Lightweight Isolation Forest for anomaly detection on user behavior vectors."""

    def __init__(self, n_trees=50, sample_size=64):
        self.n_trees = n_trees
        self.sample_size = sample_size
        self.trees = []
        self.trained = False

    def _build_tree(self, data, depth=0, max_depth=10):
        if len(data) <= 1 or depth >= max_depth:
            return {"type": "leaf", "size": len(data)}
        n_features = data.shape[1]
        feat = np.random.randint(n_features)
        mn, mx = data[:, feat].min(), data[:, feat].max()
        if mn == mx:
            return {"type": "leaf", "size": len(data)}
        split = np.random.uniform(mn, mx)
        left = data[data[:, feat] < split]
        right = data[data[:, feat] >= split]
        return {
            "type": "node",
            "feat": feat,
            "split": split,
            "left": self._build_tree(left, depth + 1, max_depth),
            "right": self._build_tree(right, depth + 1, max_depth),
        }

    def fit(self, data):
        if len(data) < 4:
            self.trained = False
            return
        data = np.array(data, dtype=float)
        self.trees = []
        for _ in range(self.n_trees):
            idx = np.random.choice(len(data), min(self.sample_size, len(data)), replace=False)
            self.trees.append(self._build_tree(data[idx]))
        self.trained = True

    def _path_length(self, point, tree, depth=0):
        if tree["type"] == "leaf":
            c = 0.0
            n = tree["size"]
            if n > 1:
                c = 2.0 * (np.log(n - 1) + 0.5772) - 2.0 * (n - 1) / n
            return depth + c
        if point[tree["feat"]] < tree["split"]:
            return self._path_length(point, tree["left"], depth + 1)
        return self._path_length(point, tree["right"], depth + 1)

    def score(self, point):
        if not self.trained or not self.trees:
            return 0.5
        point = np.array(point, dtype=float)
        avg_path = np.mean([self._path_length(point, t) for t in self.trees])
        n = self.sample_size
        c = 2.0 * (np.log(max(n - 1, 1)) + 0.5772) - 2.0 * (n - 1) / max(n, 1)
        return 2 ** (-avg_path / max(c, 0.001))


_iforest = IsolationForestLite()


async def _compute_population_stats() -> dict:
    now = datetime.now(timezone.utc)
    seven_days = (now - timedelta(days=7)).isoformat()
    twenty_four_h = (now - timedelta(hours=24)).isoformat()

    users = await db.users.find({}, {"_id": 0, "user_id": 1}).to_list(1000)
    user_ids = [u["user_id"] for u in users]

    if not user_ids:
        return {"login_fail_mean": 0, "login_fail_std": 1, "event_mean": 0, "event_std": 1}

    fail_counts = []
    event_counts = []
    for uid in user_ids[:200]:
        fails = await db.security_events.count_documents(
            {"user_id": uid, "event_type": "login_failure", "timestamp": {"$gte": twenty_four_h}}
        )
        events = await db.security_events.count_documents({"user_id": uid, "timestamp": {"$gte": seven_days}})
        fail_counts.append(fails)
        event_counts.append(events)

    def _stats(arr):
        n = len(arr)
        if n == 0:
            return 0.0, 1.0
        mean = sum(arr) / n
        variance = sum((x - mean) ** 2 for x in arr) / max(n, 1)
        return mean, max(math.sqrt(variance), 0.1)

    fm, fs = _stats(fail_counts)
    em, es = _stats(event_counts)
    return {"login_fail_mean": fm, "login_fail_std": fs, "event_mean": em, "event_std": es}


async def _build_feature_vectors():
    """Build feature vectors for ML model from all users."""
    now = datetime.now(timezone.utc)
    twenty_four_h = (now - timedelta(hours=24)).isoformat()
    seven_days = (now - timedelta(days=7)).isoformat()

    users = await db.users.find({}, {"_id": 0, "user_id": 1, "created_at": 1}).to_list(500)
    vectors = []
    user_ids = []

    for user in users:
        uid = user["user_id"]
        fails = await db.security_events.count_documents(
            {"user_id": uid, "event_type": "login_failure", "timestamp": {"$gte": twenty_four_h}}
        )
        events = await db.security_events.count_documents({"user_id": uid, "timestamp": {"$gte": seven_days}})
        ips = len(
            await db.security_events.distinct("ip_address", {"user_id": uid, "timestamp": {"$gte": twenty_four_h}})
        )
        failed_payments = await db.payments.count_documents(
            {"user_id": uid, "status": "failed", "created_at": {"$gte": twenty_four_h}}
        )

        age_hours = 999
        if user.get("created_at"):
            created = user["created_at"]
            if isinstance(created, str):
                try:
                    created = datetime.fromisoformat(created.replace("Z", "+00:00"))
                except Exception:
                    created = None
            if created:
                if created.tzinfo is None:
                    created = created.replace(tzinfo=timezone.utc)
                age_hours = max(0, (now - created).total_seconds() / 3600)

        vectors.append([fails, events, ips, failed_payments, min(age_hours, 1000)])
        user_ids.append(uid)

    return vectors, user_ids, users


async def run_fraud_scan():
    """Background job: ML-enhanced fraud scan. Called by APScheduler."""
    now = datetime.now(timezone.utc)
    (now - timedelta(hours=24)).isoformat()
    (now - timedelta(days=7)).isoformat()

    pop_stats = await _compute_population_stats()

    # Build and train Isolation Forest
    vectors, user_ids, users_data = await _build_feature_vectors()
    ml_trained = False
    if len(vectors) >= 4:
        _iforest.fit(vectors)
        ml_trained = _iforest.trained

    flagged = 0
    cleared = 0
    user_map = {u["user_id"]: u for u in users_data}

    for i, uid in enumerate(user_ids):
        user = user_map.get(uid, {})
        risk_score = 0
        risk_signals = []
        anomaly_scores = {}

        vec = vectors[i]
        login_failures, total_events, ip_count, failed_payments, age_hours = vec

        # ML anomaly score
        ml_score = 0.5
        if ml_trained:
            ml_score = _iforest.score(vec)
            anomaly_scores["ml_isolation_forest"] = round(ml_score, 3)
            if ml_score > 0.65:
                risk_score += 25
                risk_signals.append(f"ml_anomaly:{ml_score:.2f}")
            elif ml_score > 0.55:
                risk_score += 10
                risk_signals.append(f"ml_elevated:{ml_score:.2f}")

        # Rule-based scoring
        z_fail = _zscore(login_failures, pop_stats["login_fail_mean"], pop_stats["login_fail_std"])
        anomaly_scores["login_failures_z"] = round(z_fail, 2)
        if login_failures > 5 or z_fail > Z_SCORE_CRITICAL:
            risk_score += RISK_WEIGHTS["rapid_login_failures"]
            risk_signals.append(f"login_failures:{login_failures} (z={z_fail:.1f})")
        elif z_fail > Z_SCORE_WARNING:
            risk_score += RISK_WEIGHTS["rapid_login_failures"] // 2
            risk_signals.append(f"elevated_login_failures:{login_failures} (z={z_fail:.1f})")

        if ip_count > 5:
            risk_score += RISK_WEIGHTS["multiple_ips"]
            risk_signals.append(f"distinct_ips:{ip_count}")
        elif ip_count > 3:
            risk_score += RISK_WEIGHTS["multiple_ips"] // 2
            risk_signals.append(f"multiple_ips:{ip_count}")

        z_events = _zscore(total_events, pop_stats["event_mean"], pop_stats["event_std"])
        anomaly_scores["event_volume_z"] = round(z_events, 2)
        if z_events > Z_SCORE_CRITICAL:
            risk_score += RISK_WEIGHTS["high_api_volume"]
            risk_signals.append(f"high_event_volume:{total_events} (z={z_events:.1f})")

        if age_hours < 1 and login_failures > 2:
            risk_score += RISK_WEIGHTS["rapid_account_creation"]
            risk_signals.append("new_account_suspicious_activity")

        if failed_payments > 3:
            risk_score += RISK_WEIGHTS["payment_anomaly"]
            risk_signals.append(f"failed_payments:{failed_payments}")

        normalized_score = round(_sigmoid(risk_score), 1) if risk_score > 0 else 0

        # Boost with ML score
        if ml_trained and ml_score > 0.6:
            normalized_score = min(100, normalized_score + round(ml_score * 15))

        risk_level = "low"
        if normalized_score >= 70:
            risk_level = "critical"
        elif normalized_score >= 50:
            risk_level = "high"
        elif normalized_score >= 25:
            risk_level = "medium"

        update_doc = {
            "user_id": uid,
            "email": user.get("email", ""),
            "name": user.get("name", ""),
            "risk_score": normalized_score,
            "risk_level": risk_level,
            "risk_signals": risk_signals,
            "anomaly_scores": anomaly_scores,
            "feature_vector": vec,
            "scoring_method": "isolation_forest_hybrid" if ml_trained else "hybrid_rule",
            "last_scan": now.isoformat(),
            "status": "flagged" if normalized_score >= 25 else "cleared",
        }

        if normalized_score >= 25:
            flagged += 1
            # Preserve existing history
            existing = await db.fraud_reports.find_one(
                {"user_id": uid, "status": "flagged"}, {"_id": 0, "risk_history": 1}
            )
            history = (existing or {}).get("risk_history", [])
            history.append({"score": normalized_score, "level": risk_level, "at": now.isoformat()})
            update_doc["risk_history"] = history[-30:]  # Keep last 30

            await db.fraud_reports.update_one({"user_id": uid}, {"$set": update_doc}, upsert=True)

            # Real-time WebSocket + email alerts for all flagged risk levels
            try:
                from routes.notification_engine import emit_notification
                from utils.email_notifications import send_fraud_alert_email

                admins = await db.users.find({"is_admin": True}, {"_id": 0, "user_id": 1, "email": 1}).to_list(10)
                alert_body = (
                    f"Risk score: {normalized_score}/100 ({risk_level}). Signals: {', '.join(risk_signals[:3])}"
                )
                for admin in admins:
                    # WebSocket alert for ALL risk levels (medium, high, critical)
                    await emit_notification(
                        user_id=admin["user_id"],
                        notif_type="fraud_alert",
                        title=f"Fraud Alert [{risk_level.upper()}]: {user.get('email', uid)}",
                        body=alert_body,
                        action_url="/admin-console",
                        metadata={
                            "user_id": uid,
                            "risk_score": normalized_score,
                            "risk_level": risk_level,
                            "signals": risk_signals[:5],
                        },
                    )
                    # Email alert for HIGH and CRITICAL
                    if risk_level in ("high", "critical"):
                        try:
                            await send_fraud_alert_email(
                                admin.get("email", ""),
                                user.get("email", uid),
                                normalized_score,
                                risk_level,
                                ", ".join(risk_signals[:3]),
                                now.strftime("%b %d, %Y at %H:%M UTC"),
                            )
                        except Exception:
                            pass
            except Exception:
                pass
        else:
            cleared += 1
            update_doc["risk_history"] = []
            await db.fraud_reports.update_one({"user_id": uid}, {"$set": update_doc}, upsert=True)

    result = {
        "flagged": flagged,
        "cleared": cleared,
        "total_scanned": len(user_ids),
        "scan_time": now.isoformat(),
        "method": "isolation_forest_hybrid" if ml_trained else "hybrid_rule",
        "ml_model_trained": ml_trained,
        "feature_dimensions": 5,
    }
    await db.fraud_scan_history.insert_one({**result, "timestamp": now.isoformat()})
    logger.info(f"Fraud scan: {flagged} flagged, {cleared} cleared (ML={ml_trained})")
    return result


@router.get("/admin/fraud/dashboard")
async def fraud_dashboard(request: Request):
    user = await get_current_user(request)
    if not user:
        raise HTTPException(401, "Unauthorized")

    now = datetime.now(timezone.utc)
    thirty_days = (now - timedelta(days=30)).isoformat()

    # Risk distribution
    pipeline = [
        {"$match": {"status": "flagged", "last_scan": {"$gte": thirty_days}}},
        {"$group": {"_id": "$risk_level", "count": {"$sum": 1}}},
    ]
    risk_dist_raw = await db.fraud_reports.aggregate(pipeline).to_list(10)
    risk_distribution = {r["_id"]: r["count"] for r in risk_dist_raw}

    # Top risk users
    top_risk = (
        await db.fraud_reports.find(
            {"status": "flagged"},
            {
                "_id": 0,
                "user_id": 1,
                "email": 1,
                "name": 1,
                "risk_score": 1,
                "risk_level": 1,
                "risk_signals": 1,
                "anomaly_scores": 1,
                "scoring_method": 1,
                "risk_history": 1,
            },
        )
        .sort("risk_score", -1)
        .limit(10)
        .to_list(10)
    )

    # Security events (7d)
    seven_days = (now - timedelta(days=7)).isoformat()
    sec_pipeline = [
        {"$match": {"timestamp": {"$gte": seven_days}}},
        {"$group": {"_id": "$event_type", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
    ]
    sec_events = await db.security_events.aggregate(sec_pipeline).to_list(20)
    security_events = [{"event": e["_id"], "count": e["count"]} for e in sec_events]

    # Signal breakdown
    signal_counts: dict = {}
    flagged_users = await db.fraud_reports.find({"status": "flagged"}, {"_id": 0, "risk_signals": 1}).to_list(200)
    for fu in flagged_users:
        for sig in fu.get("risk_signals", []):
            key = sig.split(":")[0]
            signal_counts[key] = signal_counts.get(key, 0) + 1

    # Scan history
    scan_history = await db.fraud_scan_history.find({}, {"_id": 0}).sort("timestamp", -1).limit(10).to_list(10)

    # ML model status
    ml_status = {
        "trained": _iforest.trained,
        "n_trees": _iforest.n_trees,
        "feature_dimensions": 5,
        "features": ["login_failures", "event_volume", "distinct_ips", "failed_payments", "account_age"],
    }

    last_scan = scan_history[0] if scan_history else None

    return {
        "risk_distribution": risk_distribution,
        "top_risk_users": top_risk,
        "security_events": security_events,
        "signal_breakdown": signal_counts,
        "scan_history": scan_history[:5],
        "last_scan": last_scan,
        "ml_status": ml_status,
        "scoring_method": "isolation_forest_hybrid",
        "z_score_thresholds": {"warning": Z_SCORE_WARNING, "critical": Z_SCORE_CRITICAL},
    }


@router.get("/admin/fraud/user/{user_id}")
async def user_risk_profile(request: Request, user_id: str):
    """Get detailed risk profile for a specific user."""
    user = await get_current_user(request)
    if not user or not user.is_admin:
        raise HTTPException(403, "Admin access required")

    report = await db.fraud_reports.find_one({"user_id": user_id}, {"_id": 0})
    if not report:
        return {"user_id": user_id, "risk_score": 0, "risk_level": "low", "status": "no_data"}

    # Recent security events
    seven_days = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    events = (
        await db.security_events.find({"user_id": user_id, "timestamp": {"$gte": seven_days}}, {"_id": 0})
        .sort("timestamp", -1)
        .limit(20)
        .to_list(20)
    )

    return {**report, "recent_events": events}


@router.post("/admin/fraud/dismiss/{user_id}")
async def dismiss_fraud_flag(request: Request, user_id: str):
    """Admin dismisses a fraud flag."""
    user = await get_current_user(request)
    if not user or not user.is_admin:
        raise HTTPException(403, "Admin access required")

    await db.fraud_reports.update_one(
        {"user_id": user_id},
        {
            "$set": {
                "status": "dismissed",
                "dismissed_by": user.user_id,
                "dismissed_at": datetime.now(timezone.utc).isoformat(),
            }
        },
    )
    return {"success": True, "user_id": user_id, "status": "dismissed"}


@router.post("/admin/fraud/run-scan")
async def trigger_fraud_scan(request: Request):
    user = await get_current_user(request)
    if not user:
        raise HTTPException(401, "Unauthorized")
    result = await run_fraud_scan()
    return {"success": True, **result}
