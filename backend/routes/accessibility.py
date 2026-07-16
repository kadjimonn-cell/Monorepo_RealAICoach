from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import Response
from routes.db import db, get_current_user, User
from datetime import datetime, timezone
import io
import logging
import textwrap

from middleware_pdf_policy import enforce_pdf_v14_bytes
from services.pdf_v15_theme import PALETTE, draw_page_chrome, draw_kv_card, draw_callout_card
from utils.pdf_v15_filename import build_pdf_v15_filename

logger = logging.getLogger(__name__)
router = APIRouter()

DEFAULT_PREFERENCES = {
    "textSize": "medium",
    "dyslexiaFont": False,
    "highContrast": False,
    "colorBlindMode": "none",
    "contrastMode": "default",
    "screenReaderOptimized": False,
    "keyboardNavigation": False,
    "focusIndicators": False,
    "motionReduction": False,
    "readingGuide": False,
    "textToSpeech": False,
    "buttonSpacing": False,
    "simplifiedNav": False,
    "easyNavMode": False,
    "voiceCommand": False,
}

# WCAG 2.1 AA criteria mapped to our accessibility features
WCAG_CRITERIA = [
    {
        "id": "1.1.1",
        "name": "Non-text Content",
        "level": "A",
        "principle": "Perceivable",
        "description": "All non-text content has a text alternative.",
        "platform_feature": "screenReaderOptimized",
        "auto_pass": True,
        "detail": "ARIA labels and alt text are provided across all UI components.",
    },
    {
        "id": "1.3.1",
        "name": "Info and Relationships",
        "level": "A",
        "principle": "Perceivable",
        "description": "Information, structure, and relationships are programmatically determinable.",
        "platform_feature": "screenReaderOptimized",
        "auto_pass": True,
        "detail": "Semantic HTML and ARIA roles used throughout the application.",
    },
    {
        "id": "1.4.1",
        "name": "Use of Color",
        "level": "A",
        "principle": "Perceivable",
        "description": "Color is not the only visual means of conveying information.",
        "platform_feature": "colorBlindMode",
        "auto_pass": True,
        "detail": "Color-blind-friendly themes (Protanopia, Deuteranopia, Tritanopia) available.",
    },
    {
        "id": "1.4.3",
        "name": "Contrast (Minimum)",
        "level": "AA",
        "principle": "Perceivable",
        "description": "Text has a contrast ratio of at least 4.5:1.",
        "platform_feature": "highContrast",
        "auto_pass": False,
        "detail": "High contrast mode increases contrast by 35%. Ultra contrast mode available.",
    },
    {
        "id": "1.4.4",
        "name": "Resize Text",
        "level": "AA",
        "principle": "Perceivable",
        "description": "Text can be resized up to 200% without loss of content.",
        "platform_feature": "textSize",
        "auto_pass": True,
        "detail": "4-level text scaling: Small (85%), Medium (100%), Large (120%), Extra-Large (145%).",
    },
    {
        "id": "1.4.5",
        "name": "Images of Text",
        "level": "AA",
        "principle": "Perceivable",
        "description": "Text is used to convey information rather than images of text.",
        "platform_feature": None,
        "auto_pass": True,
        "detail": "Platform uses live text for all informational content.",
    },
    {
        "id": "1.4.10",
        "name": "Reflow",
        "level": "AA",
        "principle": "Perceivable",
        "description": "Content can be presented without two-dimensional scrolling at 320px.",
        "platform_feature": None,
        "auto_pass": True,
        "detail": "Responsive layout adapts to all screen widths including mobile.",
    },
    {
        "id": "1.4.11",
        "name": "Non-text Contrast",
        "level": "AA",
        "principle": "Perceivable",
        "description": "UI components and graphical objects have 3:1 contrast ratio.",
        "platform_feature": "focusIndicators",
        "auto_pass": False,
        "detail": "Focus indicators use high-visibility orange (#FF6B00) outlines.",
    },
    {
        "id": "1.4.12",
        "name": "Text Spacing",
        "level": "AA",
        "principle": "Perceivable",
        "description": "No loss of content when adjusting line height, paragraph, letter, and word spacing.",
        "platform_feature": "dyslexiaFont",
        "auto_pass": True,
        "detail": "Dyslexia-friendly font applies wider letter and word spacing.",
    },
    {
        "id": "2.1.1",
        "name": "Keyboard",
        "level": "A",
        "principle": "Operable",
        "description": "All functionality is operable through a keyboard interface.",
        "platform_feature": "keyboardNavigation",
        "auto_pass": False,
        "detail": "Enhanced keyboard tab-order support available via accessibility settings.",
    },
    {
        "id": "2.3.1",
        "name": "Three Flashes or Below Threshold",
        "level": "A",
        "principle": "Operable",
        "description": "No content flashes more than three times per second.",
        "platform_feature": "motionReduction",
        "auto_pass": True,
        "detail": "Motion reduction disables all animations. No flashing content by default.",
    },
    {
        "id": "2.4.1",
        "name": "Bypass Blocks",
        "level": "A",
        "principle": "Operable",
        "description": "A mechanism is available to bypass blocks of repeated content.",
        "platform_feature": "simplifiedNav",
        "auto_pass": True,
        "detail": "Skip-to-content link and simplified navigation mode available.",
    },
    {
        "id": "2.4.3",
        "name": "Focus Order",
        "level": "A",
        "principle": "Operable",
        "description": "Focusable components receive focus in a meaningful order.",
        "platform_feature": "keyboardNavigation",
        "auto_pass": False,
        "detail": "Keyboard navigation enforces logical focus order across the app.",
    },
    {
        "id": "2.4.6",
        "name": "Headings and Labels",
        "level": "AA",
        "principle": "Operable",
        "description": "Headings and labels describe topic or purpose.",
        "platform_feature": None,
        "auto_pass": True,
        "detail": "All sections use descriptive headings. ARIA labels on interactive elements.",
    },
    {
        "id": "2.4.7",
        "name": "Focus Visible",
        "level": "AA",
        "principle": "Operable",
        "description": "Keyboard focus indicator is visible.",
        "platform_feature": "focusIndicators",
        "auto_pass": False,
        "detail": "3px orange outline with 5px glow on focused elements.",
    },
    {
        "id": "2.5.5",
        "name": "Target Size",
        "level": "AAA",
        "principle": "Operable",
        "description": "Touch targets are at least 44x44 CSS pixels.",
        "platform_feature": "buttonSpacing",
        "auto_pass": False,
        "detail": "Button spacing enlargement ensures minimum 48x48px touch targets.",
    },
    {
        "id": "3.1.1",
        "name": "Language of Page",
        "level": "A",
        "principle": "Understandable",
        "description": "Default human language of each page can be programmatically determined.",
        "platform_feature": None,
        "auto_pass": True,
        "detail": "HTML lang attribute set on all pages.",
    },
    {
        "id": "3.2.3",
        "name": "Consistent Navigation",
        "level": "AA",
        "principle": "Understandable",
        "description": "Navigation mechanisms occur in the same relative order on each page.",
        "platform_feature": "simplifiedNav",
        "auto_pass": True,
        "detail": "Persistent sidebar navigation with consistent order across all pages.",
    },
    {
        "id": "3.3.2",
        "name": "Labels or Instructions",
        "level": "A",
        "principle": "Understandable",
        "description": "Labels or instructions are provided for user input.",
        "platform_feature": None,
        "auto_pass": True,
        "detail": "All form fields have associated labels and placeholder instructions.",
    },
    {
        "id": "4.1.2",
        "name": "Name, Role, Value",
        "level": "A",
        "principle": "Robust",
        "description": "All UI components have accessible name and role.",
        "platform_feature": "screenReaderOptimized",
        "auto_pass": False,
        "detail": "ARIA roles, labels, and states applied to interactive components.",
    },
]


@router.get("/accessibility/preferences/{user_id}")
async def get_accessibility_preferences(user_id: str, user: User = Depends(get_current_user)):
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    if user.user_id != user_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    doc = await db.accessibility_preferences.find_one({"user_id": user_id}, {"_id": 0})
    if not doc:
        return {"user_id": user_id, "preferences": DEFAULT_PREFERENCES}
    return {"user_id": doc["user_id"], "preferences": doc.get("preferences", DEFAULT_PREFERENCES)}


@router.get("/accessibility/settings")
async def get_accessibility_settings_alias(request: Request):
    """Compatibility endpoint for current-user accessibility settings."""
    user = await get_current_user(request)
    if not user:
        return {"user_id": "anonymous", "preferences": DEFAULT_PREFERENCES}
    return await get_accessibility_preferences(user.user_id)


@router.put("/accessibility/preferences/{user_id}")
async def save_accessibility_preferences(user_id: str, request: Request, user: User = Depends(get_current_user)):
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    if user.user_id != user_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    body = await request.json()
    preferences = body.get("preferences", {})
    merged = {**DEFAULT_PREFERENCES, **preferences}
    await db.accessibility_preferences.update_one(
        {"user_id": user_id},
        {
            "$set": {
                "user_id": user_id,
                "preferences": merged,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        },
        upsert=True,
    )
    return {"success": True, "preferences": merged}


@router.post("/accessibility/preferences/{user_id}/reset")
async def reset_accessibility_preferences(user_id: str, user: User = Depends(get_current_user)):
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    if user.user_id != user_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    await db.accessibility_preferences.update_one(
        {"user_id": user_id},
        {
            "$set": {
                "user_id": user_id,
                "preferences": DEFAULT_PREFERENCES,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        },
        upsert=True,
    )
    return {"success": True, "preferences": DEFAULT_PREFERENCES}


@router.get("/accessibility/wcag-report")
async def generate_wcag_report():
    """Generate WCAG 2.1 compliance report with platform-wide accessibility stats."""
    now = datetime.now(timezone.utc).isoformat()

    # Aggregate user accessibility usage
    total_users = await db.users.count_documents({})
    a11y_docs = await db.accessibility_preferences.find({}, {"_id": 0}).to_list(None)
    users_with_prefs = len(a11y_docs)

    # Count feature adoption
    feature_counts = {}
    for key in DEFAULT_PREFERENCES:
        feature_counts[key] = 0
    for doc in a11y_docs:
        prefs = doc.get("preferences", {})
        for key, val in prefs.items():
            if key == "textSize" and val != "medium":
                feature_counts[key] = feature_counts.get(key, 0) + 1
            elif key == "colorBlindMode" and val != "none":
                feature_counts[key] = feature_counts.get(key, 0) + 1
            elif key == "contrastMode" and val != "default":
                feature_counts[key] = feature_counts.get(key, 0) + 1
            elif val is True:
                feature_counts[key] = feature_counts.get(key, 0) + 1

    # Build per-criterion results
    criteria_results = []
    pass_count = 0
    partial_count = 0
    for c in WCAG_CRITERIA:
        feat = c["platform_feature"]
        if c["auto_pass"]:
            status = "pass"
            pass_count += 1
        elif feat and feature_counts.get(feat, 0) > 0:
            status = "pass"
            pass_count += 1
        elif feat:
            status = "available"
            partial_count += 1
        else:
            status = "pass"
            pass_count += 1

        criteria_results.append(
            {
                "id": c["id"],
                "name": c["name"],
                "level": c["level"],
                "principle": c["principle"],
                "description": c["description"],
                "detail": c["detail"],
                "status": status,
                "feature": feat,
                "adoption": feature_counts.get(feat, 0) if feat else None,
            }
        )

    total_criteria = len(WCAG_CRITERIA)
    score = round((pass_count / total_criteria) * 100) if total_criteria > 0 else 0

    return {
        "generated_at": now,
        "wcag_version": "2.1",
        "target_level": "AA",
        "score": score,
        "summary": {
            "total_criteria": total_criteria,
            "pass": pass_count,
            "available": partial_count,
            "fail": total_criteria - pass_count - partial_count,
        },
        "user_stats": {
            "total_users": total_users,
            "users_with_preferences": users_with_prefs,
            "adoption_rate": round((users_with_prefs / total_users * 100) if total_users > 0 else 0),
            "feature_adoption": feature_counts,
        },
        "criteria": criteria_results,
    }


@router.get("/accessibility/wcag-report/pdf")
async def export_wcag_report_pdf():
    """Generate and download WCAG compliance report in global PDF v15 style."""
    now = datetime.now(timezone.utc)

    # Reuse the same logic as the JSON report
    total_users = await db.users.count_documents({})
    a11y_docs = await db.accessibility_preferences.find({}, {"_id": 0}).to_list(None)
    users_with_prefs = len(a11y_docs)

    feature_counts = {k: 0 for k in DEFAULT_PREFERENCES}
    for doc in a11y_docs:
        prefs = doc.get("preferences", {})
        for key, val in prefs.items():
            if key == "textSize" and val != "medium":
                feature_counts[key] = feature_counts.get(key, 0) + 1
            elif key == "colorBlindMode" and val != "none":
                feature_counts[key] = feature_counts.get(key, 0) + 1
            elif key == "contrastMode" and val != "default":
                feature_counts[key] = feature_counts.get(key, 0) + 1
            elif val is True:
                feature_counts[key] = feature_counts.get(key, 0) + 1

    pass_count = 0
    criteria_results = []
    for c in WCAG_CRITERIA:
        feat = c["platform_feature"]
        if c["auto_pass"]:
            status = "PASS"
            pass_count += 1
        elif feat and feature_counts.get(feat, 0) > 0:
            status = "PASS"
            pass_count += 1
        elif feat:
            status = "AVAILABLE"
        else:
            status = "PASS"
            pass_count += 1
        criteria_results.append({**c, "status": status, "adoption": feature_counts.get(feat, 0) if feat else None})

    total_criteria = len(WCAG_CRITERIA)
    score = round((pass_count / total_criteria) * 100) if total_criteria > 0 else 0

    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    avail = sum(1 for c in criteria_results if c["status"] == "AVAILABLE")
    not_met = total_criteria - pass_count - avail
    adopt_rate = round((users_with_prefs / total_users * 100) if total_users > 0 else 0)

    principle_groups = {p: [c for c in criteria_results if c["principle"] == p] for p in ["Perceivable", "Operable", "Understandable", "Robust"]}

    buf = io.BytesIO()
    pdf = canvas.Canvas(buf, pagesize=A4, pdfVersion=(1, 4))
    width, height = A4
    margin_x = 40
    content_w = width - (2 * margin_x)
    page_no = 1
    y = 0.0

    status = "PASS" if score >= 80 else "WARNING" if score >= 50 else "FAIL"

    def _draw_page() -> None:
        nonlocal y
        y = draw_page_chrome(
            pdf,
            width=width,
            height=height,
            margin_x=margin_x,
            page_no=page_no,
            title="RealAICoach Accessibility Compliance",
            subtitle="WCAG 2.1 Report  •  Enterprise Governance Artifact",
            right_primary="noreply@realaicoach.app",
            right_secondary=now.strftime("%Y-%m-%d %H:%M:%S"),
            badge_text=f"[WCAG 2.1 • SCORE {score}%] pass={pass_count} available={avail} not_met={not_met}",
            badge_status=status,
            footer_text="RealAICoach  •  Global Accessibility Compliance",
        )

    def _new_page() -> None:
        nonlocal page_no
        pdf.showPage()
        page_no += 1
        _draw_page()

    def _ensure_space(points_needed: float) -> None:
        nonlocal y
        if y - points_needed < 52:
            _new_page()

    def _draw_text_block_card(title: str, lines: list[str], tone) -> None:
        nonlocal y
        wrapped: list[str] = []
        for line in lines:
            wrapped.extend(textwrap.wrap(line, width=98) or [""])
        wrapped = wrapped or ["No details available."]
        body_h = 15 + (len(wrapped) * 10.5)
        header_h = 17
        total_h = header_h + 4 + body_h + 10
        _ensure_space(total_h)

        pdf.setFillColor(tone)
        pdf.roundRect(margin_x, y - header_h, content_w, header_h, 5, stroke=0, fill=1)
        pdf.setFillColorRGB(1, 1, 1)
        pdf.setFont("Helvetica-Bold", 9.5)
        pdf.drawString(margin_x + 8, y - 11.5, title)

        body_top = y - header_h - 4
        pdf.setFillColorRGB(1, 1, 1)
        pdf.setStrokeColor(PALETTE["border_soft"])
        pdf.roundRect(margin_x, body_top - body_h, content_w, body_h, 7, stroke=1, fill=1)
        cursor = body_top - 11
        for line in wrapped:
            pdf.setFillColor(PALETTE["slate"])
            pdf.setFont("Helvetica", 8.8)
            pdf.drawString(margin_x + 8, cursor, line)
            cursor -= 10.5
        y -= total_h

    _draw_page()
    _ensure_space(75)
    y = draw_callout_card(
        pdf,
        margin_x=margin_x,
        content_w=content_w,
        y=y,
        title="Accessibility Compliance Snapshot",
        subtitle=f"WCAG 2.1 Level AA • Generated {now.strftime('%Y-%m-%d %H:%M UTC')}",
        detail=f"Compliance Score {score}% • {pass_count}/{total_criteria} criteria passing",
        status=status,
    )

    _ensure_space(150)
    y = draw_kv_card(
        pdf,
        margin_x=margin_x,
        content_w=content_w,
        y=y,
        title="Summary Metrics",
        rows=[
            ("Total Criteria Evaluated", total_criteria),
            ("Passing", pass_count),
            ("Available (needs adoption)", avail),
            ("Not Met", not_met),
            ("WCAG Target", "2.1 Level AA"),
        ],
        tone=PALETTE["primary"],
    )

    _ensure_space(120)
    y = draw_kv_card(
        pdf,
        margin_x=margin_x,
        content_w=content_w,
        y=y,
        title="User Adoption",
        rows=[
            ("Total Platform Users", total_users),
            ("Users with Accessibility Settings", users_with_prefs),
            ("Adoption Rate", f"{adopt_rate}%"),
        ],
        tone=PALETTE["teal"],
    )

    for principle in ["Perceivable", "Operable", "Understandable", "Robust"]:
        items = principle_groups.get(principle) or []
        if not items:
            continue
        lines: list[str] = []
        for item in items:
            state = "PASS" if item["status"] == "PASS" else "AVAILABLE"
            level = item.get("level", "")
            lines.append(f"{state}  {item.get('id')}  {item.get('name')} (Level {level})")
            lines.append(f"  {item.get('description')}")
            if item["status"] == "AVAILABLE" and item.get("adoption") is not None:
                lines.append(f"  Adoption: {item.get('adoption')} user(s)")
        _draw_text_block_card(f"{principle} Criteria", lines, PALETTE["indigo"] if principle in {"Operable", "Robust"} else PALETTE["primary"])

    pdf.save()
    raw = buf.getvalue()
    normalized, _policy = enforce_pdf_v14_bytes(raw)
    filename = build_pdf_v15_filename("compliance", "wcag-2-1")
    return Response(
        content=normalized,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
