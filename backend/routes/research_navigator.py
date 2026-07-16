"""Deep Research Navigator v2 — enterprise-grade research workspace APIs."""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Any, Optional
from urllib.parse import quote

import httpx
from fastapi import APIRouter, HTTPException, Request
from utils.access_control_engine import compute_effective_plan

from models.research import AddInsightRequest, CreateProjectRequest, RunResearchRequest
from routes.db import db, get_current_user, logger
from utils.llm_helper import generate_verified_text


router = APIRouter(prefix="/research-navigator", tags=["Deep Research Navigator"])

GUEST_ID_RE = re.compile(r"^user_[a-zA-Z0-9_-]{12,80}$")

# TIER LIMITS: Research quotas per day
TIER_LIMITS = {
    "free": {
        "runs_per_day": 5,
        "max_sources": 15,
        "export_formats": ["txt"],
    },
    "basic": {
        "runs_per_day": 20,
        "max_sources": 30,
        "export_formats": ["txt", "md"],
    },
    "premium": {
        "runs_per_day": -1,  # Unlimited
        "max_sources": 50,
        "export_formats": ["txt", "md", "bibtex", "pdf"],
    },
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _resolve_owner_id(user: Any, fallback_user_id: Optional[str]) -> str:
    if user and getattr(user, "user_id", None):
        return f"auth:{str(user.user_id)}"

    fallback = str(fallback_user_id or "").strip()
    if not fallback:
        raise HTTPException(
            status_code=401,
            detail={
                "error_code": "research_nav_auth_required",
                "message": "Login required or provide fallback_user_id",
            },
        )
    if not GUEST_ID_RE.match(fallback):
        raise HTTPException(
            status_code=400,
            detail={
                "error_code": "research_nav_invalid_guest_id",
                "message": "fallback_user_id format is invalid",
            },
        )
    return f"guest:{fallback}"


async def _get_user_tier(owner_id: str) -> str:
    """Determine user's subscription tier (free, basic, premium)."""
    if not owner_id.startswith("auth:"):
        return "free"  # Guest users are always free tier
    
    try:
        user_id = owner_id.replace("auth:", "")
        user_doc = await db.users.find_one(
            {"user_id": user_id},
            {
                "_id": 0,
                "subscription_plan": 1,
                "subscription_status": 1,
                "subscription_end_date": 1,
                "pending_subscription_transition": 1,
                "payment_verified": 1,
                "is_admin": 1,
            },
        )
        if not user_doc:
            return "free"

        effective = compute_effective_plan(user_doc or {})
        return effective if effective in TIER_LIMITS else "free"
    except Exception as e:
        logger.warning(f"Failed to fetch tier for {owner_id}: {e}")
        return "free"


async def _get_daily_research_count(owner_id: str) -> int:
    """Get number of research runs today by user."""
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    count = await db.research_navigator_runs.count_documents({
        "owner_id": owner_id,
        "created_at": {"$gte": today_start.isoformat()},
    })
    return count


async def _check_research_limit(owner_id: str, tier: str) -> dict[str, Any]:
    """Check if user can run more research today. Returns usage info."""
    limits = TIER_LIMITS.get(tier, TIER_LIMITS["free"])
    daily_limit = limits["runs_per_day"]
    
    # Premium has unlimited (-1)
    if daily_limit == -1:
        return {
            "can_run": True,
            "runs_used_today": 0,
            "daily_limit": -1,
            "tier": tier,
            "limit_reached": False,
        }
    
    runs_used = await _get_daily_research_count(owner_id)
    can_run = runs_used < daily_limit
    
    return {
        "can_run": can_run,
        "runs_used_today": runs_used,
        "daily_limit": daily_limit,
        "tier": tier,
        "limit_reached": not can_run,
    }


def _domain_confidence(url: str) -> int:
    u = (url or "").lower()
    if not u:
        return 25
    if "wikipedia.org" in u or ".gov" in u or ".edu" in u:
        return 92
    if "duckduckgo.com" in u or "nature.com" in u or "arxiv.org" in u:
        return 84
    if "medium.com" in u or "substack" in u:
        return 66
    return 72


async def _fetch_wikipedia_sources(query: str, limit: int = 5) -> list[dict[str, Any]]:
    search_url = "https://en.wikipedia.org/w/api.php"
    params = {
        "action": "opensearch",
        "search": query,
        "limit": max(1, min(limit, 8)),
        "namespace": 0,
        "format": "json",
    }

    sources: list[dict[str, Any]] = []
    async with httpx.AsyncClient(
        timeout=15,
        headers={
            "User-Agent": "RealAICoach-ResearchNavigator/1.0 (support@realaicoach.app)",
            "Accept": "application/json",
        },
    ) as client:
        response = await client.get(search_url, params=params)
        response.raise_for_status()
        data = response.json()
        titles = data[1] if isinstance(data, list) and len(data) > 1 else []
        descriptions = data[2] if isinstance(data, list) and len(data) > 2 else []
        urls = data[3] if isinstance(data, list) and len(data) > 3 else []

        for idx, title in enumerate(titles):
            sources.append(
                {
                    "source_id": f"src_wiki_{idx}",
                    "title": str(title),
                    "url": str(urls[idx]) if idx < len(urls) else f"https://en.wikipedia.org/wiki/{quote(str(title).replace(' ', '_'))}",
                    "snippet": str(descriptions[idx]) if idx < len(descriptions) else "Wikipedia source",
                    "domain": "wikipedia.org",
                    "confidence": 92,
                    "retrieved_at": _now_iso(),
                    "source_type": "reference",
                    "published_at": None,
                }
            )
    return sources


async def _fetch_duckduckgo_source(query: str) -> list[dict[str, Any]]:
    url = "https://api.duckduckgo.com/"
    params = {
        "q": query,
        "format": "json",
        "no_redirect": 1,
        "no_html": 1,
        "skip_disambig": 1,
    }
    async with httpx.AsyncClient(
        timeout=15,
        headers={
            "User-Agent": "RealAICoach-ResearchNavigator/1.0 (support@realaicoach.app)",
            "Accept": "application/json",
        },
    ) as client:
        response = await client.get(url, params=params)
        response.raise_for_status()
        data = response.json()

    abstract = str(data.get("AbstractText") or "").strip()
    abstract_url = str(data.get("AbstractURL") or "").strip()
    heading = str(data.get("Heading") or "DuckDuckGo Answer").strip()
    if not abstract:
        return []
    return [
        {
            "source_id": "src_ddg_0",
            "title": heading,
            "url": abstract_url or "https://duckduckgo.com",
            "snippet": abstract,
            "domain": "duckduckgo.com",
            "confidence": 84,
            "retrieved_at": _now_iso(),
            "source_type": "search",
            "published_at": None,
        }
    ]


async def _fetch_arxiv_sources(query: str, limit: int = 4) -> list[dict[str, Any]]:
    """Fetch academic papers from arXiv API with publication dates."""
    search_url = "https://export.arxiv.org/api/query"
    params = {
        "search_query": f"all:{query}",
        "start": 0,
        "max_results": max(1, min(limit, 8)),
        "sortBy": "relevance",
        "sortOrder": "descending",
    }

    sources: list[dict[str, Any]] = []
    async with httpx.AsyncClient(
        timeout=20,
        headers={
            "User-Agent": "RealAICoach-ResearchNavigator/1.0 (support@realaicoach.app)",
        },
    ) as client:
        response = await client.get(search_url, params=params)
        response.raise_for_status()
        xml_data = response.text

        # Parse XML response (arXiv returns Atom XML format)
        import xml.etree.ElementTree as ET
        root = ET.fromstring(xml_data)
        ns = {"atom": "http://www.w3.org/2005/Atom"}

        for idx, entry in enumerate(root.findall("atom:entry", ns)):
            title_elem = entry.find("atom:title", ns)
            summary_elem = entry.find("atom:summary", ns)
            published_elem = entry.find("atom:published", ns)
            link_elem = entry.find("atom:id", ns)

            if title_elem is None or link_elem is None:
                continue

            title = str(title_elem.text or "").strip().replace("\n", " ")
            summary = str(summary_elem.text or "No abstract available").strip().replace("\n", " ")[:300]
            url = str(link_elem.text or "").strip()
            published_at = str(published_elem.text or "").strip() if published_elem is not None else None

            sources.append(
                {
                    "source_id": f"src_arxiv_{idx}",
                    "title": title,
                    "url": url,
                    "snippet": summary,
                    "domain": "arxiv.org",
                    "confidence": 88,
                    "retrieved_at": _now_iso(),
                    "source_type": "academic",
                    "published_at": published_at,
                }
            )
    return sources


async def _fetch_pubmed_sources(query: str, limit: int = 4) -> list[dict[str, Any]]:
    """Fetch medical research from PubMed E-utilities API with publication metadata."""
    # Step 1: Search for article IDs
    search_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    search_params = {
        "db": "pubmed",
        "term": query,
        "retmax": max(1, min(limit, 8)),
        "retmode": "json",
        "sort": "relevance",
    }

    sources: list[dict[str, Any]] = []
    async with httpx.AsyncClient(
        timeout=20,
        headers={
            "User-Agent": "RealAICoach-ResearchNavigator/1.0 (support@realaicoach.app)",
        },
    ) as client:
        search_response = await client.get(search_url, params=search_params)
        search_response.raise_for_status()
        search_data = search_response.json()

        id_list = search_data.get("esearchresult", {}).get("idlist", [])
        if not id_list:
            return sources

        # Step 2: Fetch article summaries
        summary_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
        summary_params = {
            "db": "pubmed",
            "id": ",".join(id_list),
            "retmode": "json",
        }

        summary_response = await client.get(summary_url, params=summary_params)
        summary_response.raise_for_status()
        summary_data = summary_response.json()

        results = summary_data.get("result", {})
        for idx, pmid in enumerate(id_list):
            article = results.get(pmid, {})
            if not article:
                continue

            title = str(article.get("title", "")).strip()
            authors = article.get("authors", [])
            author_names = ", ".join([a.get("name", "") for a in authors[:3]])
            pub_date = str(article.get("pubdate", "")).strip()
            source_journal = str(article.get("source", "")).strip()

            snippet = f"{author_names}. {source_journal}." if author_names else source_journal

            sources.append(
                {
                    "source_id": f"src_pubmed_{idx}",
                    "title": title,
                    "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                    "snippet": snippet[:300],
                    "domain": "pubmed.ncbi.nlm.nih.gov",
                    "confidence": 90,
                    "retrieved_at": _now_iso(),
                    "source_type": "medical",
                    "published_at": pub_date or None,
                }
            )
    return sources


async def _fetch_sec_sources(query: str, limit: int = 3) -> list[dict[str, Any]]:
    """Fetch SEC EDGAR filings with filing dates (official SEC.gov search)."""
    search_url = "https://www.sec.gov/cgi-bin/browse-edgar"
    params = {
        "action": "getcompany",
        "CIK": "",
        "type": "",
        "dateb": "",
        "owner": "exclude",
        "start": 0,
        "count": max(1, min(limit, 10)),
        "search_text": query,
    }

    sources: list[dict[str, Any]] = []
    async with httpx.AsyncClient(
        timeout=20,
        headers={
            "User-Agent": "RealAICoach-ResearchNavigator/1.0 (support@realaicoach.app)",
            "Accept": "text/html,application/xhtml+xml",
        },
    ) as client:
        try:
            response = await client.get(search_url, params=params)
            response.raise_for_status()
            html_content = response.text

            # Parse HTML to extract filings (simple regex-based extraction)
            import re
            # Extract filing entries from the results table
            # Pattern: <tr>...<td>Form Type</td><td>Filing Date</td><td>Description</td>...
            filing_pattern = re.compile(
                r'<tr[^>]*>.*?<td[^>]*>.*?(\d{4}-\d{2}-\d{2}).*?</td>.*?<td[^>]*>(.*?)</td>.*?</tr>',
                re.DOTALL
            )
            
            matches = filing_pattern.findall(html_content)
            for idx, (filing_date, form_type) in enumerate(matches[:limit]):
                filing_date = filing_date.strip()
                form_type = form_type.strip()
                
                # Build a basic filing entry
                sources.append(
                    {
                        "source_id": f"src_sec_{idx}",
                        "title": f"SEC Filing: {form_type}",
                        "url": f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&search_text={query}",
                        "snippet": f"Form {form_type} filing related to {query}",
                        "domain": "sec.gov",
                        "confidence": 85,
                        "retrieved_at": _now_iso(),
                        "source_type": "financial",
                        "published_at": filing_date,
                    }
                )
        except Exception:
            # If HTML parsing fails, return empty (graceful degradation)
            pass
    
    return sources


def _build_followups(query: str) -> list[str]:
    q = query.strip().rstrip("?")
    return [
        f"What are the top 3 counter-arguments to this view on '{q}'?",
        f"What changed in the last 12 months regarding '{q}'?",
        f"What should an executive team do next based on research about '{q}'?",
    ]


@router.get("/bootstrap")
async def bootstrap_research_workspace(request: Request, fallback_user_id: Optional[str] = None):
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, fallback_user_id)

    # Get tier and usage info
    tier = await _get_user_tier(owner_id)
    usage_info = await _check_research_limit(owner_id, tier)

    projects = await db.research_navigator_projects.find(
        {"owner_id": owner_id},
        {"_id": 0, "project_id": 1, "title": 1, "topic": 1, "updated_at": 1, "run_count": 1, "last_run_id": 1},
    ).sort("updated_at", -1).to_list(20)

    notes = await db.research_navigator_notes.find(
        {"owner_id": owner_id},
        {"_id": 0, "note_id": 1, "project_id": 1, "title": 1, "content": 1, "created_at": 1},
    ).sort("created_at", -1).to_list(20)

    return {
        "owner_id": owner_id,
        "tier": tier,
        "projects": projects,
        "insight_notes": notes,
        "usage": usage_info,
        "stats": {
            "project_count": len(projects),
            "insight_count": len(notes),
            "avg_runs_per_project": round((sum(int(p.get("run_count") or 0) for p in projects) / len(projects)), 1) if projects else 0,
        },
    }


@router.post("/projects")
async def create_project(payload: CreateProjectRequest, request: Request):
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, payload.fallback_user_id)

    now = _now_iso()
    project = {
        "project_id": f"rnav_{uuid.uuid4().hex[:14]}",
        "owner_id": owner_id,
        "title": payload.title.strip()[:160],
        "topic": payload.topic.strip()[:260],
        "created_at": now,
        "updated_at": now,
        "run_count": 0,
        "last_run_id": None,
    }
    await db.research_navigator_projects.insert_one(dict(project))
    return {"project": project}


@router.get("/projects")
async def list_projects(request: Request, fallback_user_id: Optional[str] = None):
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, fallback_user_id)
    projects = await db.research_navigator_projects.find(
        {"owner_id": owner_id},
        {"_id": 0},
    ).sort("updated_at", -1).to_list(40)
    return {"projects": projects}


@router.get("/projects/{project_id}")
async def get_project(project_id: str, request: Request, fallback_user_id: Optional[str] = None):
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, fallback_user_id)

    project = await db.research_navigator_projects.find_one({"owner_id": owner_id, "project_id": project_id}, {"_id": 0})
    if not project:
        raise HTTPException(status_code=404, detail={"error_code": "research_nav_project_not_found", "message": "Project not found"})

    runs = await db.research_navigator_runs.find(
        {"owner_id": owner_id, "project_id": project_id},
        {"_id": 0},
    ).sort("created_at", -1).to_list(20)

    notes = await db.research_navigator_notes.find(
        {"owner_id": owner_id, "project_id": project_id},
        {"_id": 0},
    ).sort("created_at", -1).to_list(20)
    return {"project": project, "runs": runs, "insight_notes": notes}


@router.post("/projects/{project_id}/runs")
async def run_research(project_id: str, payload: RunResearchRequest, request: Request):
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, payload.fallback_user_id)

    # TIER ENFORCEMENT: Check if user can run research today
    tier = await _get_user_tier(owner_id)
    usage_check = await _check_research_limit(owner_id, tier)
    if not usage_check["can_run"]:
        raise HTTPException(
            status_code=403,
            detail={
                "error_code": "research_nav_limit_reached",
                "message": f"Daily research limit reached ({usage_check['daily_limit']}/day for {tier} tier). Upgrade to run more research.",
                "upgrade_prompt": True,
                "current_tier": tier,
                "runs_used_today": usage_check["runs_used_today"],
                "daily_limit": usage_check["daily_limit"],
            }
        )

    project = await db.research_navigator_projects.find_one(
        {"owner_id": owner_id, "project_id": project_id},
        {"_id": 0, "project_id": 1, "title": 1, "topic": 1},
    )
    if not project:
        raise HTTPException(status_code=404, detail={"error_code": "research_nav_project_not_found", "message": "Project not found"})

    idempotency_key = (payload.idempotency_key or "").strip()
    if idempotency_key:
        existing = await db.research_navigator_runs.find_one(
            {
                "owner_id": owner_id,
                "project_id": project_id,
                "idempotency_key": idempotency_key,
                "status": "completed",
            },
            {"_id": 0},
        )
        if existing:
            return {"run": existing, "idempotent_replay": True}

    run_id = f"run_{uuid.uuid4().hex[:14]}"
    now = _now_iso()
    steps = [
        {"step": "planner", "status": "running", "updated_at": now},
        {"step": "retriever", "status": "pending", "updated_at": now},
        {"step": "verifier", "status": "pending", "updated_at": now},
        {"step": "synthesizer", "status": "pending", "updated_at": now},
    ]

    pending_run = {
        "run_id": run_id,
        "owner_id": owner_id,
        "project_id": project_id,
        "query": payload.query.strip(),
        "status": "running",
        "steps": steps,
        "created_at": now,
        "completed_at": None,
        "idempotency_key": idempotency_key or None,
    }
    await db.research_navigator_runs.insert_one(dict(pending_run))

    try:
        steps[0] = {"step": "planner", "status": "completed", "updated_at": _now_iso()}
        steps[1] = {"step": "retriever", "status": "running", "updated_at": _now_iso()}

        # Parallel retrieval from 5 sources: Wikipedia, DuckDuckGo, arXiv, PubMed, SEC EDGAR
        wiki_sources: list[dict[str, Any]] = []
        ddg_sources: list[dict[str, Any]] = []
        arxiv_sources: list[dict[str, Any]] = []
        pubmed_sources: list[dict[str, Any]] = []
        sec_sources: list[dict[str, Any]] = []
        
        try:
            wiki_sources = await _fetch_wikipedia_sources(payload.query, 3)
        except Exception as wiki_err:
            logger.warning("Wikipedia retrieval failed for research run %s: %s", run_id, wiki_err)
        try:
            ddg_sources = await _fetch_duckduckgo_source(payload.query)
        except Exception as ddg_err:
            logger.warning("DuckDuckGo retrieval failed for research run %s: %s", run_id, ddg_err)
        try:
            arxiv_sources = await _fetch_arxiv_sources(payload.query, 4)
        except Exception as arxiv_err:
            logger.warning("arXiv retrieval failed for research run %s: %s", run_id, arxiv_err)
        try:
            pubmed_sources = await _fetch_pubmed_sources(payload.query, 4)
        except Exception as pubmed_err:
            logger.warning("PubMed retrieval failed for research run %s: %s", run_id, pubmed_err)
        try:
            sec_sources = await _fetch_sec_sources(payload.query, 3)
        except Exception as sec_err:
            logger.warning("SEC EDGAR retrieval failed for research run %s: %s", run_id, sec_err)
        
        # Combine sources (max 15 total: 3 wiki + 1 ddg + 4 arxiv + 4 pubmed + 3 sec)
        sources = (wiki_sources + ddg_sources + arxiv_sources + pubmed_sources + sec_sources)[:15]
        if not sources:
            sources = [
                {
                    "source_id": "src_unavailable_0",
                    "title": "External evidence retrieval unavailable",
                    "url": "",
                    "snippet": "No external source could be retrieved in this run. The synthesis is based on model priors and should be independently verified.",
                    "domain": "unavailable",
                    "confidence": 25,
                    "retrieved_at": _now_iso(),
                    "source_type": "fallback",
                    "published_at": None,
                }
            ]

        steps[1] = {"step": "retriever", "status": "completed", "updated_at": _now_iso()}
        steps[2] = {"step": "verifier", "status": "running", "updated_at": _now_iso()}

        for source in sources:
            source["confidence"] = _domain_confidence(source.get("url") or "")

        steps[2] = {"step": "verifier", "status": "completed", "updated_at": _now_iso()}
        steps[3] = {"step": "synthesizer", "status": "running", "updated_at": _now_iso()}

        evidence = "\n".join([f"- {item['title']} ({item['url']}): {item['snippet']}" for item in sources[:6]])
        synthesis_prompt = f"""
Research query: {payload.query.strip()}
Project context: {project.get('title')} | {project.get('topic')}

Evidence snippets:
{evidence or '- No external evidence retrieved'}

Generate a research-grade output with:
1) Executive Summary
2) Key Findings (bulleted)
3) Contradictions / Caveats
4) Actionable Recommendations
5) Confidence assessment
""".strip()

        synthesis = await generate_verified_text(
            synthesis_prompt,
            "You are a senior research strategist. Ground claims in provided evidence and avoid speculation.",
            f"research-nav-{owner_id}-{run_id}",
            feature="research_navigator",
            user_id=owner_id,
        )

        follow_ups = _build_followups(payload.query)

        completed_at = _now_iso()
        steps[3] = {"step": "synthesizer", "status": "completed", "updated_at": completed_at}
        run_doc = {
            "run_id": run_id,
            "owner_id": owner_id,
            "project_id": project_id,
            "query": payload.query.strip(),
            "status": "completed",
            "steps": steps,
            "sources": sources,
            "answer": synthesis,
            "follow_up_questions": follow_ups,
            "created_at": now,
            "completed_at": completed_at,
            "idempotency_key": idempotency_key or None,
        }

        await db.research_navigator_runs.update_one(
            {"owner_id": owner_id, "run_id": run_id},
            {"$set": run_doc},
        )
        await db.research_navigator_projects.update_one(
            {"owner_id": owner_id, "project_id": project_id},
            {"$set": {"updated_at": completed_at, "last_run_id": run_id}, "$inc": {"run_count": 1}},
        )

        return {"run": run_doc}
    except Exception as exc:
        logger.exception("Research navigator run failed: %s", exc)
        failed_at = _now_iso()
        await db.research_navigator_runs.update_one(
            {"owner_id": owner_id, "run_id": run_id},
            {
                "$set": {
                    "status": "failed",
                    "steps": steps,
                    "error": str(exc)[:280],
                    "completed_at": failed_at,
                }
            },
        )
        raise HTTPException(status_code=500, detail={"error_code": "research_nav_run_failed", "message": "Research run failed. Please retry."})


@router.get("/runs/{run_id}")
async def get_run(run_id: str, request: Request, fallback_user_id: Optional[str] = None):
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, fallback_user_id)
    run = await db.research_navigator_runs.find_one({"owner_id": owner_id, "run_id": run_id}, {"_id": 0})
    if not run:
        raise HTTPException(status_code=404, detail={"error_code": "research_nav_run_not_found", "message": "Run not found"})
    return {"run": run}


@router.post("/projects/{project_id}/insights")
async def add_insight_note(project_id: str, payload: AddInsightRequest, request: Request):
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, payload.fallback_user_id)

    project_exists = await db.research_navigator_projects.find_one(
        {"owner_id": owner_id, "project_id": project_id},
        {"_id": 0, "project_id": 1},
    )
    if not project_exists:
        raise HTTPException(status_code=404, detail={"error_code": "research_nav_project_not_found", "message": "Project not found"})

    note = {
        "note_id": f"ins_{uuid.uuid4().hex[:12]}",
        "owner_id": owner_id,
        "project_id": project_id,
        "title": payload.title.strip()[:180],
        "content": payload.content.strip()[:5000],
        "created_at": _now_iso(),
    }
    await db.research_navigator_notes.insert_one(dict(note))
    return {"insight": note}


@router.get("/usage")
async def get_research_usage(request: Request, fallback_user_id: Optional[str] = None):
    """Get research usage summary for current user."""
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, fallback_user_id)
    tier = await _get_user_tier(owner_id)
    usage_info = await _check_research_limit(owner_id, tier)
    return {
        "usage": usage_info,
        "tier_limits": TIER_LIMITS.get(tier, TIER_LIMITS["free"]),
    }


@router.delete("/projects/{project_id}")
async def delete_project(project_id: str, request: Request, fallback_user_id: Optional[str] = None):
    """Delete a research project and all its data."""
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, fallback_user_id)
    
    result = await db.research_navigator_projects.delete_one({"project_id": project_id, "owner_id": owner_id})
    if result.deleted_count == 0:
        raise HTTPException(
            status_code=404,
            detail={"error_code": "research_project_not_found", "message": "Project not found"}
        )
    
    # Also delete associated runs and insights
    await db.research_navigator_runs.delete_many({"project_id": project_id, "owner_id": owner_id})
    await db.research_navigator_notes.delete_many({"project_id": project_id, "owner_id": owner_id})
    
    return {"message": "Project deleted successfully", "project_id": project_id}
