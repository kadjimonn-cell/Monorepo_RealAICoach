# Global Entitlement Divergence Report (Locked Protocol)

Date: 2026-06-23  
Scope: Global system-level scan for Features with 3-tier entitlement divergence patterns similar to Feature 1, including adjacent risk analysis.

## 1) Method (Deterministic)

- Auth baseline established using current production-like preview sessions:
  - free account baseline plan: `free`
  - basic account baseline plan: `basic`
  - admin account baseline plan: `premium`
- Enumerated backend route candidates exposing `/bootstrap` or `/usage/stats` contracts from `/app/backend/routes/*.py`.
- Queried each candidate endpoint for all three accounts.
- Flag rule for **confirmed divergence**:
  - endpoint returns a tier/plan field,
  - endpoint is `200` for all three roles,
  - returned plans collapse to `free/free/free` despite baseline `free/basic/premium`.

## 2) Confirmed Features with Same 3-Tier Entitlement Issue (Runtime-Confirmed)

These features are confirmed by live matrix evidence to collapse tier reporting to free across free/basic/admin in the current codebase.

1. **Feature 1 — ai-writer (Smart Writing Studio)**
   - Endpoint: `/api/writing-studio/bootstrap`
   - Returned: free=free, basic=free, admin=free
   - Route file: `backend/routes/writing_studio.py`

2. **Feature 2 — ai-chatbot (Personal Assistant)**
   - Endpoint: `/api/personal-assistant/bootstrap`
   - Returned: free=free, basic=free, admin=free
   - Route file: `backend/routes/personal_assistant.py`

3. **Feature 3 — ai-search (Research Navigator)**
   - Endpoint: `/api/research-navigator/bootstrap`
   - Returned: free=free, basic=free, admin=free
   - Route file: `backend/routes/research_navigator.py`

4. **Feature 5 — ai-cognitive (Decision Coach)**
   - Endpoint: `/api/decision-coach/bootstrap`
   - Returned: free=free, basic=free, admin=free
   - Route file: `backend/routes/decision_coach.py`

5. **Feature 10 — smartbuy (Smart Shopping Advisor)**
   - Endpoint: `/api/smart-shopping-advisor/bootstrap`
   - Returned: free=free, basic=free, admin=free
   - Route file: `backend/routes/smart_shopping_advisor.py`

## 3) Root-Cause Family (Observed)

Across confirmed features, divergence is caused by one or more of the following:

- `owner_id` prefixed as `auth:{user_id}` and then used directly for user-tier lookup against `users.user_id` (without normalization).
- Lookup performed on non-canonical field (`owner_id`) for users collection where canonical auth identity is `user_id`.
- Feature-local `TIER_LIMITS` + `_get_user_tier` pipelines bypassing global entitlement engine (`compute_effective_plan` + unified feature entitlements).

## 4) Adjacent Risk Candidates (Code-Level Risk, not all runtime-confirmed yet)

Features/routes with similar structural patterns and high risk of entitlement drift:

- `workflow_builder.py` (Feature 4 / ai-automations)
- `fitness_planner.py` (Feature 8 / fitness)
- `money_strategy_hub.py` (Feature 9 / pennypilot)
- `learning_coach.py` (Feature 24 / ai-learning-hub lineage route)
- `health_guide.py`
- `relationship_coach.py` (Feature 12 lineage route)
- `travel_planner_pro.py` (Feature 11 lineage route)
- `mobility_assistant.py` (Feature 13 lineage route)
- `video_creator_studio.py` (Feature 15 lineage route)
- `ai_photo_studio.py` (Feature 16 lineage route)
- `ai_speech_studio.py` (Feature 17 lineage route)
- `ai_enterprise_copilot.py` (Feature 18 lineage route)

> Note: Adjacent risk list is intentionally conservative; each route requires runtime matrix confirmation before final classification as broken.

## 5) Locked Protocol Verdict

- **Confirmed divergence count (runtime): 5 features**
- **Confirmed affected feature numbers:** `1, 2, 3, 5, 10`
- Feature 31 remains aligned after prior fixes and is not in the divergence set.

## 6) Recommended Next Action (Execution Sequence)

1. Patch the confirmed 5 features first (normalize identity + global entitlement engine alignment).
2. Run the same deterministic matrix for all adjacent-risk routes.
3. Produce post-fix parity report proving `free/basic/premium` mapping for all 1–36 canonical features.

---

## 7) Post-Fix Validation Update (2026-06-23)

### Fixes implemented for confirmed divergence set
- Feature 1 (`writing_studio.py`): normalized `owner_id` before user lookup (`auth:`/`guest:` removed; lookup on `user_id`).
- Feature 2 (`personal_assistant.py`): switched tier source from `subscription_tier` to canonical `subscription_plan`.
- Feature 3 (`research_navigator.py`): switched tier source from `subscription_tier` to canonical `subscription_plan`.
- Feature 5 (`decision_coach.py`): switched tier source from `subscription_tier` to canonical `subscription_plan`.
- Feature 10 (`smart_shopping_advisor.py`): corrected users lookup key from `owner_id` to canonical `user_id`.

### Regression guards added
- `/app/backend/tests/test_feature_entitlement_divergence_fix_contract.py`

### Runtime parity evidence after fix
- Deep backend matrix verification: **15/15 pass**
  - Features 1, 2, 3, 5, 10 now return:
    - free account => `free`
    - basic account => `basic`
    - admin account => `premium`

### Frontend verification note
- Free/admin smoke passed for affected feature routes.
- Basic-user browser-session verification encountered preview session persistence instability in one automation run (environmental blocker).
- Backend parity is fully validated and is the source-of-truth for entitlement correctness.
