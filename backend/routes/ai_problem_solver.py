"""RETIRED — Problem Solver (Feature 31) was replaced by the AI Coaching Team.

All legacy endpoints return HTTP 410 with a machine-readable retirement payload.
Replacement: /ai-coaching-team (frontend) and /api/ai-coaching-team (API).
"""

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/ai-solver")
compat_router = APIRouter(prefix="/ai-problem-solver")

RETIREMENT_PAYLOAD = {
    "retired": True,
    "feature": "ai-problem-solver",
    "feature_number": 31,
    "replacement_feature": "ai-coaching-team",
    "replacement_route": "/ai-coaching-team",
    "replacement_api": "/api/ai-coaching-team",
    "message": "Problem Solver has been retired and replaced by the AI Coaching Team.",
}

_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE"]


def _gone():
    raise HTTPException(status_code=410, detail=RETIREMENT_PAYLOAD)


@router.api_route("", methods=_METHODS, include_in_schema=False)
@router.api_route("/{path:path}", methods=_METHODS, include_in_schema=False)
async def ai_solver_retired(path: str = ""):
    _gone()


@compat_router.api_route("", methods=_METHODS, include_in_schema=False)
@compat_router.api_route("/{path:path}", methods=_METHODS, include_in_schema=False)
async def ai_problem_solver_retired(path: str = ""):
    _gone()
