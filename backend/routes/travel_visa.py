"""
Travel Visa — AI-Powered Global Visa Coaching & Immigration Learning Platform
Enterprise-grade backend module for RealAICoach
"""
import os
import re
import uuid
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional
from fastapi import APIRouter, HTTPException, Query, Body, Depends
from pydantic import BaseModel
from emergentintegrations.llm.chat import LlmChat, UserMessage
from routes.db import db as _singleton_db, require_auth, require_admin, User
from utils.access_control_engine import compute_effective_plan

router = APIRouter(prefix="/travel-visa", tags=["travel-visa"], dependencies=[Depends(require_auth)])

logger = logging.getLogger(__name__)

LLM_KEY = os.environ.get("EMERGENT_LLM_KEY", "")

def get_db():
    return _singleton_db


def _ensure_user_scope(current_user: User, target_user_id: str) -> None:
    if current_user.is_admin or current_user.user_id == target_user_id:
        return
    raise HTTPException(status_code=403, detail="Forbidden: user scope mismatch")

# ── Pydantic Models ──

class CoachRequest(BaseModel):
    user_id: str
    session_id: Optional[str] = None
    message: str
    country: Optional[str] = None
    visa_type: Optional[str] = None
    language: Optional[str] = "en"

class InterviewSimRequest(BaseModel):
    user_id: str
    country: str
    visa_type: str
    difficulty: str = "medium"
    language: Optional[str] = "en"

class InterviewAnswerRequest(BaseModel):
    user_id: str
    session_id: str
    question_id: str
    answer: str

class QuizSubmitRequest(BaseModel):
    user_id: str
    quiz_id: str
    answers: dict

class ProgressUpdateRequest(BaseModel):
    user_id: str
    lesson_id: str
    progress_pct: float = 0.0
    completed: bool = False
    bookmarked: bool = False
    notes: Optional[str] = None

class SaveContentRequest(BaseModel):
    user_id: str
    content_id: str
    content_type: str

class ChallengeCreateRequest(BaseModel):
    challenger_id: str
    challenged_id: str
    quiz_id: str

class ChallengeAnswerRequest(BaseModel):
    user_id: str
    challenge_id: str
    answers: dict

class NotificationPrefsRequest(BaseModel):
    user_id: str
    daily_lessons: bool = True
    new_content: bool = True
    challenge_invites: bool = True
    streak_reminders: bool = True
    weekly_digest: bool = True
    email_notifications: bool = False
    push_notifications: bool = True

# ── Subscription Tier Limits ──

TIER_LIMITS = {
    "free": {
        "daily_ai_credits": 3,
        "daily_quizzes": 2,
        "daily_simulations": 1,
        "lesson_access": "limited",
        "max_saved": 10,
        "downloads": 0,
    },
    "basic": {
        "daily_ai_credits": 25,
        "daily_quizzes": 15,
        "daily_simulations": 5,
        "lesson_access": "expanded",
        "max_saved": 100,
        "downloads": 10,
    },
    "premium": {
        "daily_ai_credits": 999,
        "daily_quizzes": 999,
        "daily_simulations": 999,
        "lesson_access": "unlimited",
        "max_saved": 9999,
        "downloads": 999,
    },
}

FREE_CATEGORY_IDS = {
    "student-visa-interviews", "tourist-visa-interviews", "passport-preparation",
    "united-states", "canada", "united-kingdom", "ds-160-guidance",
    "financial-proof", "bank-statements", "legal-immigration-pathways",
}

async def _get_user_plan(db, user_id: str) -> str:
    """
    Get effective user plan with proper payment_verified enforcement.
    Uses compute_effective_plan to match Features 20, 21, 22 entitlement logic.
    """
    user = await db.users.find_one(
        {"user_id": user_id},
        {
            "_id": 0,
            "is_admin": 1,
            "subscription_plan": 1,
            "subscription_status": 1,
            "subscription_end_date": 1,
            "pending_subscription_transition": 1,
            "payment_verified": 1,
        }
    )
    if not user:
        return "free"
    
    user_doc = {
        "is_admin": bool(user.get("is_admin", False)),
        "subscription_plan": user.get("subscription_plan", "free"),
        "subscription_status": user.get("subscription_status", "active"),
        "subscription_end_date": user.get("subscription_end_date"),
        "pending_subscription_transition": user.get("pending_subscription_transition"),
        "payment_verified": bool(user.get("payment_verified", False)),
        "full_access": False,
        "subscription_permanent": False,
    }
    
    return compute_effective_plan(user_doc)

async def _check_daily_limit(db, user_id: str, action: str, plan: str) -> bool:
    limits = TIER_LIMITS.get(plan, TIER_LIMITS["free"])
    key = f"daily_{action}"
    limit = limits.get(key, 0)
    if limit >= 999:
        return True
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    usage = await db.tv_daily_usage.find_one(
        {"user_id": user_id, "date": today, "action": action},
        {"_id": 0}
    )
    current = usage.get("count", 0) if usage else 0
    if current >= limit:
        return False
    await db.tv_daily_usage.update_one(
        {"user_id": user_id, "date": today, "action": action},
        {"$inc": {"count": 1}, "$setOnInsert": {"created_at": datetime.now(timezone.utc).isoformat()}},
        upsert=True,
    )
    return True

# ══════════════════════════════════════
# SEED / BOOTSTRAP
# ══════════════════════════════════════

COUNTRY_DATA = [
    {"code": "US", "name": "United States", "region": "North America", "flag": "🇺🇸", "popular": True,
     "visa_types": ["B1/B2 Tourist", "F1 Student", "H1B Work", "J1 Exchange", "K1 Fiancé", "L1 Intracompany", "EB5 Investor", "O1 Extraordinary"],
     "embassy_count": 12, "difficulty": "high"},
    {"code": "CA", "name": "Canada", "region": "North America", "flag": "🇨🇦", "popular": True,
     "visa_types": ["Visitor", "Study Permit", "Work Permit", "Express Entry PR", "PNP", "Start-up Visa", "Family Sponsorship"],
     "embassy_count": 10, "difficulty": "medium"},
    {"code": "GB", "name": "United Kingdom", "region": "Europe", "flag": "🇬🇧", "popular": True,
     "visa_types": ["Standard Visitor", "Student (Tier 4)", "Skilled Worker", "Global Talent", "Family", "Innovator Founder"],
     "embassy_count": 8, "difficulty": "medium"},
    {"code": "DE", "name": "Germany", "region": "Europe", "flag": "🇩🇪", "popular": True,
     "visa_types": ["Schengen Tourist", "Student", "Work Visa", "Blue Card EU", "Job Seeker", "Family Reunion"],
     "embassy_count": 7, "difficulty": "medium"},
    {"code": "FR", "name": "France", "region": "Europe", "flag": "🇫🇷", "popular": True,
     "visa_types": ["Schengen Short-stay", "Long-stay Student", "Talent Passport", "Family", "Work Permit"],
     "embassy_count": 9, "difficulty": "medium"},
    {"code": "AU", "name": "Australia", "region": "Oceania", "flag": "🇦🇺", "popular": True,
     "visa_types": ["Visitor (600)", "Student (500)", "Skilled Worker (482)", "PR (189/190)", "Partner", "Working Holiday"],
     "embassy_count": 6, "difficulty": "medium"},
    {"code": "JP", "name": "Japan", "region": "Asia", "flag": "🇯🇵", "popular": True,
     "visa_types": ["Tourist", "Student", "Work (Engineer)", "Highly Skilled Professional", "Spouse", "Business Manager"],
     "embassy_count": 5, "difficulty": "medium"},
    {"code": "AE", "name": "United Arab Emirates", "region": "Middle East", "flag": "🇦🇪", "popular": True,
     "visa_types": ["Tourist", "Visit", "Work Residence", "Golden Visa", "Student", "Green Visa"],
     "embassy_count": 4, "difficulty": "low"},
    {"code": "SG", "name": "Singapore", "region": "Asia", "flag": "🇸🇬", "popular": True,
     "visa_types": ["Tourist", "Student Pass", "Employment Pass", "S Pass", "EntrePass", "Dependant Pass"],
     "embassy_count": 3, "difficulty": "medium"},
    {"code": "NZ", "name": "New Zealand", "region": "Oceania", "flag": "🇳🇿", "popular": False,
     "visa_types": ["Visitor", "Student", "Essential Skills Work", "Skilled Migrant", "Partner", "Working Holiday"],
     "embassy_count": 3, "difficulty": "medium"},
    {"code": "IT", "name": "Italy", "region": "Europe", "flag": "🇮🇹", "popular": False,
     "visa_types": ["Schengen Tourist", "Student", "Work", "Elective Residence", "Family Reunion"],
     "embassy_count": 6, "difficulty": "medium"},
    {"code": "ES", "name": "Spain", "region": "Europe", "flag": "🇪🇸", "popular": False,
     "visa_types": ["Schengen Tourist", "Student", "Work Authorization", "Digital Nomad", "Non-lucrative"],
     "embassy_count": 5, "difficulty": "medium"},
    {"code": "KR", "name": "South Korea", "region": "Asia", "flag": "🇰🇷", "popular": False,
     "visa_types": ["C-3 Tourist", "D-2 Student", "E-7 Professional", "F-2 Resident", "H-1 Working Holiday"],
     "embassy_count": 4, "difficulty": "medium"},
    {"code": "IN", "name": "India", "region": "Asia", "flag": "🇮🇳", "popular": False,
     "visa_types": ["e-Tourist", "Student", "Employment", "Business", "Medical", "Conference"],
     "embassy_count": 5, "difficulty": "low"},
    {"code": "CN", "name": "China", "region": "Asia", "flag": "🇨🇳", "popular": False,
     "visa_types": ["L Tourist", "X Student", "Z Work", "M Business", "F Exchange", "Q Family"],
     "embassy_count": 6, "difficulty": "high"},
    {"code": "BR", "name": "Brazil", "region": "South America", "flag": "🇧🇷", "popular": False,
     "visa_types": ["Tourist (VIVIS)", "Student (VITEM IV)", "Work (VITEM V)", "Investor", "Family Reunion"],
     "embassy_count": 4, "difficulty": "low"},
    {"code": "MX", "name": "Mexico", "region": "North America", "flag": "🇲🇽", "popular": False,
     "visa_types": ["Tourist", "Student", "Temporary Resident", "Permanent Resident", "Work Permit"],
     "embassy_count": 3, "difficulty": "low"},
    {"code": "RU", "name": "Russia", "region": "Europe", "flag": "🇷🇺", "popular": False,
     "visa_types": ["Tourist", "Business", "Student", "Work", "Highly Qualified Specialist", "Private"],
     "embassy_count": 4, "difficulty": "high"},
    {"code": "SA", "name": "Saudi Arabia", "region": "Middle East", "flag": "🇸🇦", "popular": False,
     "visa_types": ["Tourist (eVisa)", "Work (Iqama)", "Business Visit", "Student", "Hajj/Umrah", "Family Visit"],
     "embassy_count": 4, "difficulty": "medium"},
    {"code": "ZA", "name": "South Africa", "region": "Africa", "flag": "🇿🇦", "popular": False,
     "visa_types": ["Tourist", "Study", "General Work", "Critical Skills", "Business", "Retired Person"],
     "embassy_count": 3, "difficulty": "medium"},
    {"code": "NG", "name": "Nigeria", "region": "Africa", "flag": "🇳🇬", "popular": False,
     "visa_types": ["Tourist", "Business", "Student (STR)", "Work (TWP)", "Subject to Regularisation"],
     "embassy_count": 2, "difficulty": "low"},
    {"code": "TR", "name": "Turkey", "region": "Europe", "flag": "🇹🇷", "popular": False,
     "visa_types": ["e-Visa Tourist", "Student", "Work Permit", "Short-term Residence", "Family Residence", "Turkuaz Card"],
     "embassy_count": 5, "difficulty": "low"},
    {"code": "TH", "name": "Thailand", "region": "Asia", "flag": "🇹🇭", "popular": False,
     "visa_types": ["Tourist", "Education", "Non-Immigrant B (Work)", "Elite Visa", "Retirement", "Smart Visa"],
     "embassy_count": 3, "difficulty": "low"},
    {"code": "SE", "name": "Sweden", "region": "Europe", "flag": "🇸🇪", "popular": False,
     "visa_types": ["Schengen Tourist", "Student Residence", "Work Permit", "Family Reunification", "Self-employed"],
     "embassy_count": 3, "difficulty": "medium"},
    {"code": "NL", "name": "Netherlands", "region": "Europe", "flag": "🇳🇱", "popular": False,
     "visa_types": ["Schengen Short-stay", "Student MVV", "Highly Skilled Migrant", "Startup Visa", "Family"],
     "embassy_count": 4, "difficulty": "medium"},
    {"code": "CH", "name": "Switzerland", "region": "Europe", "flag": "🇨🇭", "popular": False,
     "visa_types": ["Schengen C", "Student D", "Work Permit (L/B/C)", "Family Reunification"],
     "embassy_count": 3, "difficulty": "high"},
    {"code": "IE", "name": "Ireland", "region": "Europe", "flag": "🇮🇪", "popular": False,
     "visa_types": ["Short Stay C", "Study (D)", "Employment Permit", "Stamp 4 (Spouse)", "Start-up Entrepreneur"],
     "embassy_count": 3, "difficulty": "medium"},
    {"code": "PT", "name": "Portugal", "region": "Europe", "flag": "🇵🇹", "popular": False,
     "visa_types": ["Schengen Tourist", "Student", "Work", "Digital Nomad (D8)", "Golden Visa", "D7 Passive Income"],
     "embassy_count": 3, "difficulty": "low"},
    {"code": "PL", "name": "Poland", "region": "Europe", "flag": "🇵🇱", "popular": False,
     "visa_types": ["Schengen C", "National D", "Student", "Work Permit", "Temporary Residence"],
     "embassy_count": 3, "difficulty": "low"},
    {"code": "MY", "name": "Malaysia", "region": "Asia", "flag": "🇲🇾", "popular": False,
     "visa_types": ["eNTRI", "eVisa Tourist", "Student Pass", "Employment Pass", "MM2H", "DE Rantau"],
     "embassy_count": 3, "difficulty": "low"},
]

CATEGORIES_DATA = [
    # VISA INTERVIEW TRAINING
    {"id": "student-visa-interviews", "name": "Student Visa Interviews", "group": "Visa Interview Training", "icon": "school", "lesson_count": 24, "tier": "free"},
    {"id": "tourist-visa-interviews", "name": "Tourist Visa Interviews", "group": "Visa Interview Training", "icon": "airplane", "lesson_count": 18, "tier": "free"},
    {"id": "work-visa-interviews", "name": "Work Visa Interviews", "group": "Visa Interview Training", "icon": "briefcase", "lesson_count": 22, "tier": "basic"},
    {"id": "family-sponsorship-interviews", "name": "Family Sponsorship Interviews", "group": "Visa Interview Training", "icon": "people", "lesson_count": 16, "tier": "basic"},
    {"id": "marriage-visa-interviews", "name": "Marriage Visa Interviews", "group": "Visa Interview Training", "icon": "heart", "lesson_count": 14, "tier": "basic"},
    {"id": "business-visa-interviews", "name": "Business Visa Interviews", "group": "Visa Interview Training", "icon": "trending-up", "lesson_count": 20, "tier": "basic"},
    {"id": "permanent-residency-interviews", "name": "Permanent Residency Interviews", "group": "Visa Interview Training", "icon": "home", "lesson_count": 18, "tier": "premium"},
    {"id": "refugee-asylum-guidance", "name": "Refugee & Asylum Guidance", "group": "Visa Interview Training", "icon": "shield-checkmark", "lesson_count": 12, "tier": "premium"},
    {"id": "investor-visa-coaching", "name": "Investor Visa Coaching", "group": "Visa Interview Training", "icon": "cash", "lesson_count": 10, "tier": "premium"},
    {"id": "transit-visa-coaching", "name": "Transit Visa Coaching", "group": "Visa Interview Training", "icon": "swap-horizontal", "lesson_count": 8, "tier": "free"},
    # DOCUMENTATION TRAINING
    {"id": "passport-preparation", "name": "Passport Preparation", "group": "Documentation Training", "icon": "document-text", "lesson_count": 12, "tier": "free"},
    {"id": "financial-proof", "name": "Financial Proof", "group": "Documentation Training", "icon": "wallet", "lesson_count": 16, "tier": "free"},
    {"id": "bank-statements", "name": "Bank Statements", "group": "Documentation Training", "icon": "card", "lesson_count": 10, "tier": "free"},
    {"id": "sponsor-letters", "name": "Sponsor Letters", "group": "Documentation Training", "icon": "mail", "lesson_count": 8, "tier": "basic"},
    {"id": "invitation-letters", "name": "Invitation Letters", "group": "Documentation Training", "icon": "mail-open", "lesson_count": 8, "tier": "basic"},
    {"id": "employment-proof", "name": "Employment Proof", "group": "Documentation Training", "icon": "business", "lesson_count": 10, "tier": "basic"},
    {"id": "university-admission-letters", "name": "University Admission Letters", "group": "Documentation Training", "icon": "school", "lesson_count": 8, "tier": "basic"},
    {"id": "travel-insurance", "name": "Travel Insurance", "group": "Documentation Training", "icon": "medkit", "lesson_count": 6, "tier": "free"},
    {"id": "accommodation-proof", "name": "Accommodation Proof", "group": "Documentation Training", "icon": "bed", "lesson_count": 6, "tier": "basic"},
    {"id": "ds-160-guidance", "name": "DS-160 Guidance", "group": "Documentation Training", "icon": "clipboard", "lesson_count": 14, "tier": "free"},
    {"id": "biometrics-preparation", "name": "Biometrics Preparation", "group": "Documentation Training", "icon": "finger-print", "lesson_count": 8, "tier": "basic"},
    {"id": "translation-legalization", "name": "Translation & Legalization", "group": "Documentation Training", "icon": "language", "lesson_count": 10, "tier": "premium"},
    # INTERVIEW SCENARIOS
    {"id": "mock-embassy-interviews", "name": "Mock Embassy Interviews", "group": "Interview Scenarios", "icon": "videocam", "lesson_count": 20, "tier": "basic"},
    {"id": "ai-interview-simulations", "name": "AI Interview Simulations", "group": "Interview Scenarios", "icon": "chatbubbles", "lesson_count": 30, "tier": "premium"},
    {"id": "confidence-coaching", "name": "Confidence Coaching", "group": "Interview Scenarios", "icon": "flash", "lesson_count": 12, "tier": "basic"},
    {"id": "high-risk-question-practice", "name": "High-Risk Question Practice", "group": "Interview Scenarios", "icon": "warning", "lesson_count": 18, "tier": "premium"},
    {"id": "rejection-recovery", "name": "Rejection Recovery Coaching", "group": "Interview Scenarios", "icon": "refresh", "lesson_count": 10, "tier": "basic"},
    {"id": "body-language-demos", "name": "Body Language Demonstrations", "group": "Interview Scenarios", "icon": "body", "lesson_count": 8, "tier": "basic"},
    {"id": "pronunciation-practice", "name": "Audio Pronunciation Practice", "group": "Interview Scenarios", "icon": "mic", "lesson_count": 14, "tier": "premium"},
    {"id": "cultural-etiquette", "name": "Cultural Etiquette Coaching", "group": "Interview Scenarios", "icon": "globe", "lesson_count": 16, "tier": "basic"},
    # IMMIGRATION EDUCATION
    {"id": "legal-immigration-pathways", "name": "Legal Immigration Pathways", "group": "Immigration Education", "icon": "map", "lesson_count": 20, "tier": "free"},
    {"id": "living-abroad-education", "name": "Living Abroad Education", "group": "Immigration Education", "icon": "earth", "lesson_count": 18, "tier": "basic"},
    {"id": "relocation-readiness", "name": "Relocation Readiness", "group": "Immigration Education", "icon": "navigate", "lesson_count": 14, "tier": "basic"},
    {"id": "international-student-prep", "name": "International Student Preparation", "group": "Immigration Education", "icon": "school", "lesson_count": 22, "tier": "basic"},
    {"id": "work-permit-education", "name": "Work Permit Education", "group": "Immigration Education", "icon": "briefcase", "lesson_count": 16, "tier": "basic"},
    {"id": "residency-systems", "name": "Residency Systems", "group": "Immigration Education", "icon": "home", "lesson_count": 12, "tier": "premium"},
    {"id": "border-entry-expectations", "name": "Border Entry Expectations", "group": "Immigration Education", "icon": "log-in", "lesson_count": 10, "tier": "free"},
    {"id": "airport-interview-prep", "name": "Airport Interview Preparation", "group": "Immigration Education", "icon": "airplane", "lesson_count": 8, "tier": "basic"},
]

EMBASSY_DATA = [
    {"country_code": "US", "name": "U.S. Embassy London", "city": "London", "country_name": "United Kingdom", "address": "33 Nine Elms Ln, London SW11 7US", "phone": "+44 20 7499 9000", "website": "https://uk.usembassy.gov", "services": ["Visa Interviews", "Passport Services", "Citizen Services"], "appointment_required": True},
    {"country_code": "US", "name": "U.S. Embassy Paris", "city": "Paris", "country_name": "France", "address": "2 Avenue Gabriel, 75008 Paris", "phone": "+33 1 43 12 22 22", "website": "https://fr.usembassy.gov", "services": ["Visa Interviews", "Passport Services", "Notarial"], "appointment_required": True},
    {"country_code": "US", "name": "U.S. Embassy Berlin", "city": "Berlin", "country_name": "Germany", "address": "Pariser Platz 2, 10117 Berlin", "phone": "+49 30 8305-0", "website": "https://de.usembassy.gov", "services": ["Visa Interviews", "Citizen Services"], "appointment_required": True},
    {"country_code": "CA", "name": "Canadian Embassy Washington", "city": "Washington D.C.", "country_name": "United States", "address": "501 Pennsylvania Ave NW, Washington, DC 20001", "phone": "+1 202-682-1740", "website": "https://www.international.gc.ca", "services": ["Visa Services", "Passport", "Trade"], "appointment_required": True},
    {"country_code": "GB", "name": "British Embassy Washington", "city": "Washington D.C.", "country_name": "United States", "address": "3100 Massachusetts Ave NW, Washington, DC 20008", "phone": "+1 202-588-6500", "website": "https://www.gov.uk/world/usa", "services": ["Visa Services", "Passport", "Notarial"], "appointment_required": True},
    {"country_code": "DE", "name": "German Embassy Washington", "city": "Washington D.C.", "country_name": "United States", "address": "4645 Reservoir Rd NW, Washington, DC 20007", "phone": "+1 202-298-4000", "website": "https://www.germany.info", "services": ["Visa Services", "Passport", "Legal"], "appointment_required": True},
    {"country_code": "AU", "name": "Australian Embassy Washington", "city": "Washington D.C.", "country_name": "United States", "address": "1601 Massachusetts Ave NW, Washington, DC 20036", "phone": "+1 202-797-3000", "website": "https://usa.embassy.gov.au", "services": ["Visa & Immigration", "Passport", "Consular"], "appointment_required": True},
    {"country_code": "JP", "name": "Embassy of Japan Washington", "city": "Washington D.C.", "country_name": "United States", "address": "2520 Massachusetts Ave NW, Washington, DC 20008", "phone": "+1 202-238-6700", "website": "https://www.us.emb-japan.go.jp", "services": ["Visa Services", "Passport", "Cultural"], "appointment_required": True},
    {"country_code": "AE", "name": "UAE Embassy Washington", "city": "Washington D.C.", "country_name": "United States", "address": "3522 International Ct NW, Washington, DC 20008", "phone": "+1 202-243-2400", "website": "https://www.uae-embassy.org", "services": ["Visa Services", "Attestation", "Consular"], "appointment_required": True},
    {"country_code": "SG", "name": "Singapore Embassy Washington", "city": "Washington D.C.", "country_name": "United States", "address": "3501 International Pl NW, Washington, DC 20008", "phone": "+1 202-537-3100", "website": "https://www.mfa.gov.sg/washington", "services": ["Visa Services", "Passport"], "appointment_required": False},
]

LESSON_TEMPLATES = [
    {"category_id": "student-visa-interviews", "title": "Understanding the F1 Visa Interview Process", "type": "reading", "duration_min": 15, "difficulty": "beginner", "xp": 50},
    {"category_id": "student-visa-interviews", "title": "Top 20 Questions Asked in Student Visa Interviews", "type": "reading", "duration_min": 20, "difficulty": "beginner", "xp": 60},
    {"category_id": "student-visa-interviews", "title": "How to Explain Your Study Plan Convincingly", "type": "reading", "duration_min": 12, "difficulty": "intermediate", "xp": 70},
    {"category_id": "student-visa-interviews", "title": "Financial Documentation for Student Visas", "type": "reading", "duration_min": 18, "difficulty": "intermediate", "xp": 65},
    {"category_id": "tourist-visa-interviews", "title": "Tourist Visa Interview Basics", "type": "reading", "duration_min": 10, "difficulty": "beginner", "xp": 40},
    {"category_id": "tourist-visa-interviews", "title": "Proving Strong Ties to Your Home Country", "type": "reading", "duration_min": 15, "difficulty": "intermediate", "xp": 60},
    {"category_id": "work-visa-interviews", "title": "H1B Interview: What to Expect", "type": "reading", "duration_min": 20, "difficulty": "intermediate", "xp": 75},
    {"category_id": "work-visa-interviews", "title": "Explaining Your Job Offer Effectively", "type": "reading", "duration_min": 15, "difficulty": "intermediate", "xp": 65},
    {"category_id": "passport-preparation", "title": "How to Renew Your Passport", "type": "reading", "duration_min": 10, "difficulty": "beginner", "xp": 30},
    {"category_id": "passport-preparation", "title": "Emergency Passport Services Guide", "type": "reading", "duration_min": 8, "difficulty": "beginner", "xp": 25},
    {"category_id": "ds-160-guidance", "title": "Filling Out DS-160: Step-by-Step", "type": "reading", "duration_min": 25, "difficulty": "beginner", "xp": 80},
    {"category_id": "ds-160-guidance", "title": "Common DS-160 Mistakes to Avoid", "type": "reading", "duration_min": 15, "difficulty": "intermediate", "xp": 70},
    {"category_id": "financial-proof", "title": "Building a Strong Financial Profile", "type": "reading", "duration_min": 18, "difficulty": "intermediate", "xp": 65},
    {"category_id": "legal-immigration-pathways", "title": "Overview of Global Immigration Systems", "type": "reading", "duration_min": 22, "difficulty": "beginner", "xp": 55},
    {"category_id": "legal-immigration-pathways", "title": "Points-Based vs Employer-Sponsored Systems", "type": "reading", "duration_min": 20, "difficulty": "intermediate", "xp": 70},
    {"category_id": "confidence-coaching", "title": "Managing Interview Anxiety", "type": "reading", "duration_min": 12, "difficulty": "beginner", "xp": 45},
    {"category_id": "rejection-recovery", "title": "What to Do After a Visa Rejection", "type": "reading", "duration_min": 15, "difficulty": "intermediate", "xp": 60},
    {"category_id": "cultural-etiquette", "title": "Embassy Etiquette: Do's and Don'ts", "type": "reading", "duration_min": 10, "difficulty": "beginner", "xp": 35},
    {"category_id": "mock-embassy-interviews", "title": "Practice U.S. Embassy Interview", "type": "interactive", "duration_min": 30, "difficulty": "intermediate", "xp": 100},
    {"category_id": "border-entry-expectations", "title": "What Happens at Immigration Control", "type": "reading", "duration_min": 12, "difficulty": "beginner", "xp": 40},
]

QUIZ_TEMPLATES = [
    {"category_id": "student-visa-interviews", "title": "Student Visa Interview Knowledge Check", "question_count": 10, "passing_score": 70, "xp_reward": 100, "tier": "free",
     "questions": [
         {"q": "What is the primary purpose of the F1 visa?", "options": ["Tourism", "Full-time study at a SEVP-certified school", "Employment", "Immigration"], "correct": 1},
         {"q": "Which form must you complete before your student visa interview?", "options": ["I-20", "DS-160", "Both I-20 and DS-160", "I-94"], "correct": 2},
         {"q": "What document proves your financial ability?", "options": ["Passport", "Bank statement/sponsor letter", "Degree certificate", "Travel itinerary"], "correct": 1},
         {"q": "How early should you arrive for your embassy appointment?", "options": ["Exactly on time", "15-30 minutes early", "1 hour early", "It doesn't matter"], "correct": 1},
         {"q": "Which is a common reason for student visa denial?", "options": ["Good grades", "Insufficient ties to home country", "Having a scholarship", "Speaking English well"], "correct": 1},
         {"q": "What does SEVIS stand for?", "options": ["Student Exchange Visitor Info System", "Standard Education Visa Import System", "Secure Entry Verification Info Service", "Student Enrollment Visa Integration System"], "correct": 0},
         {"q": "Can you work on an F1 visa?", "options": ["No, never", "Yes, unlimited hours", "Yes, limited on-campus work and CPT/OPT", "Only after graduation"], "correct": 2},
         {"q": "What happens if your visa is denied under Section 214(b)?", "options": ["Permanent ban", "You can reapply with stronger documentation", "Automatic deportation", "Criminal record"], "correct": 1},
         {"q": "Should you memorize answers for the interview?", "options": ["Yes, word for word", "No, be natural and honest", "Only for difficult questions", "The interviewer doesn't care"], "correct": 1},
         {"q": "What is the interview dress code?", "options": ["Casual", "Business/smart casual", "Traditional costume required", "No dress code"], "correct": 1},
     ]},
    {"category_id": "tourist-visa-interviews", "title": "Tourist Visa Essentials Quiz", "question_count": 8, "passing_score": 75, "xp_reward": 80, "tier": "free",
     "questions": [
         {"q": "What is the most common tourist visa type for the U.S.?", "options": ["F1", "B1/B2", "H1B", "K1"], "correct": 1},
         {"q": "What does 'strong ties' to your home country mean?", "options": ["Family, job, property that ensure you'll return", "Being physically strong", "Having many social media followers", "Speaking many languages"], "correct": 0},
         {"q": "Which document is NOT typically needed for a tourist visa?", "options": ["Passport", "Bank statements", "University degree", "Travel itinerary"], "correct": 2},
         {"q": "How long is a typical B1/B2 visa valid?", "options": ["30 days", "6 months", "Up to 10 years", "Permanent"], "correct": 2},
         {"q": "Can a tourist visa be extended?", "options": ["Never", "Yes, by filing Form I-539 before expiry", "Only at the airport", "Automatically"], "correct": 1},
         {"q": "What proves you intend to return home?", "options": ["Saying 'I promise'", "Employment letter, property deeds, family ties", "A return ticket only", "Nothing is needed"], "correct": 1},
         {"q": "Is travel insurance required for all countries?", "options": ["Yes, universally", "No, but Schengen area requires it", "Only for students", "Only for work visas"], "correct": 1},
         {"q": "What should you avoid saying in a tourist visa interview?", "options": ["Your travel plans", "That you plan to work illegally", "Your hotel booking", "How you'll fund the trip"], "correct": 1},
     ]},
    {"category_id": "ds-160-guidance", "title": "DS-160 Mastery Test", "question_count": 8, "passing_score": 75, "xp_reward": 90, "tier": "free",
     "questions": [
         {"q": "What is the DS-160?", "options": ["Online nonimmigrant visa application form", "Visa approval letter", "Travel insurance form", "Passport application"], "correct": 0},
         {"q": "How do you save progress on DS-160?", "options": ["It auto-saves every 20 minutes", "Using the Application ID", "You cannot save progress", "By emailing the embassy"], "correct": 1},
         {"q": "What photo format is required for DS-160?", "options": ["Any photo", "600x600 pixels, white background, recent", "Passport-size printed photo", "Selfie"], "correct": 1},
         {"q": "Can you edit DS-160 after submission?", "options": ["Yes, anytime", "No, you must submit a new one", "Only before the interview", "Yes, by calling the embassy"], "correct": 1},
         {"q": "What confirmation do you get after DS-160 submission?", "options": ["Email approval", "Confirmation page with barcode", "Visa stamp", "Phone call"], "correct": 1},
         {"q": "Must you print the DS-160 confirmation?", "options": ["No, it's optional", "Yes, bring it to your interview", "Only for work visas", "The embassy has it on file"], "correct": 1},
         {"q": "Which language must you complete DS-160 in?", "options": ["Your native language", "English", "Any language", "The language of the embassy country"], "correct": 1},
         {"q": "What happens if you provide false information?", "options": ["Nothing", "Permanent visa ineligibility possible", "Small fine", "Automatic approval"], "correct": 1},
     ]},
]

ACHIEVEMENTS_CATALOG = [
    {"id": "first-lesson", "name": "First Step", "description": "Complete your first lesson", "icon": "footsteps", "xp_reward": 25, "condition": "lessons_completed >= 1"},
    {"id": "five-lessons", "name": "Dedicated Learner", "description": "Complete 5 lessons", "icon": "book", "xp_reward": 75, "condition": "lessons_completed >= 5"},
    {"id": "ten-lessons", "name": "Knowledge Seeker", "description": "Complete 10 lessons", "icon": "library", "xp_reward": 150, "condition": "lessons_completed >= 10"},
    {"id": "first-quiz", "name": "Quiz Starter", "description": "Pass your first quiz", "icon": "checkmark-circle", "xp_reward": 50, "condition": "quizzes_passed >= 1"},
    {"id": "five-quizzes", "name": "Quiz Master", "description": "Pass 5 quizzes", "icon": "trophy", "xp_reward": 150, "condition": "quizzes_passed >= 5"},
    {"id": "first-simulation", "name": "Interview Brave", "description": "Complete your first AI interview simulation", "icon": "videocam", "xp_reward": 75, "condition": "simulations_completed >= 1"},
    {"id": "five-simulations", "name": "Interview Pro", "description": "Complete 5 AI interview simulations", "icon": "star", "xp_reward": 200, "condition": "simulations_completed >= 5"},
    {"id": "first-coaching", "name": "AI Coached", "description": "Have your first AI coaching session", "icon": "chatbubble-ellipses", "xp_reward": 30, "condition": "coaching_sessions >= 1"},
    {"id": "streak-3", "name": "3-Day Streak", "description": "Learn for 3 consecutive days", "icon": "flame", "xp_reward": 100, "condition": "streak >= 3"},
    {"id": "streak-7", "name": "Week Warrior", "description": "Learn for 7 consecutive days", "icon": "flame", "xp_reward": 250, "condition": "streak >= 7"},
    {"id": "streak-30", "name": "Monthly Master", "description": "Learn for 30 consecutive days", "icon": "diamond", "xp_reward": 1000, "condition": "streak >= 30"},
    {"id": "country-explorer", "name": "Country Explorer", "description": "Explore 5 different countries", "icon": "globe", "xp_reward": 100, "condition": "countries_explored >= 5"},
    {"id": "readiness-50", "name": "Getting Ready", "description": "Reach 50% Visa Readiness Score", "icon": "trending-up", "xp_reward": 150, "condition": "readiness_score >= 50"},
    {"id": "readiness-80", "name": "Nearly There", "description": "Reach 80% Visa Readiness Score", "icon": "rocket", "xp_reward": 300, "condition": "readiness_score >= 80"},
    {"id": "readiness-100", "name": "Visa Ready", "description": "Reach 100% Visa Readiness Score", "icon": "checkmark-done-circle", "xp_reward": 500, "condition": "readiness_score >= 100"},
]

# ══════════════════════════════════════
# SEED ENDPOINT
# ══════════════════════════════════════

@router.post("/seed")
async def seed_travel_visa_data(_admin_user: User = Depends(require_admin)):
    db = get_db()
    from routes.travel_visa_categories import generate_expanded_categories, generate_expanded_lessons
    # Countries
    existing = await db.tv_countries.count_documents({})
    if existing == 0:
        for c in COUNTRY_DATA:
            c["created_at"] = datetime.now(timezone.utc).isoformat()
        await db.tv_countries.insert_many(COUNTRY_DATA)
    # Categories — Expanded 520+
    existing_cat = await db.tv_categories.count_documents({})
    if existing_cat < 100:
        await db.tv_categories.delete_many({})
        expanded_cats = generate_expanded_categories()
        now = datetime.now(timezone.utc).isoformat()
        for c in expanded_cats:
            c["created_at"] = now
        # Insert in batches of 100
        for i in range(0, len(expanded_cats), 100):
            await db.tv_categories.insert_many(expanded_cats[i:i+100])
    else:
        expanded_cats = None
    # Embassies
    existing_emb = await db.tv_embassies.count_documents({})
    if existing_emb == 0:
        for e in EMBASSY_DATA:
            e["embassy_id"] = str(uuid.uuid4())[:8]
            e["created_at"] = datetime.now(timezone.utc).isoformat()
        await db.tv_embassies.insert_many(EMBASSY_DATA)
    # Lessons — Expanded with video/audio types
    existing_les = await db.tv_lessons.count_documents({})
    if existing_les < 100:
        await db.tv_lessons.delete_many({})
        cats_for_lessons = expanded_cats or generate_expanded_categories()
        expanded_lessons = generate_expanded_lessons(cats_for_lessons)
        now = datetime.now(timezone.utc).isoformat()
        for lesson_item in expanded_lessons:
            lesson_item["created_at"] = now
        for i in range(0, len(expanded_lessons), 100):
            await db.tv_lessons.insert_many(expanded_lessons[i:i+100])
    else:
        pass
    # Quizzes
    existing_quiz = await db.tv_quizzes.count_documents({})
    if existing_quiz == 0:
        quizzes = []
        for qt in QUIZ_TEMPLATES:
            quiz = {**qt, "quiz_id": str(uuid.uuid4())[:8], "created_at": datetime.now(timezone.utc).isoformat()}
            quizzes.append(quiz)
        await db.tv_quizzes.insert_many(quizzes)
    # Achievements catalog
    existing_ach = await db.tv_achievements_catalog.count_documents({})
    if existing_ach == 0:
        for a in ACHIEVEMENTS_CATALOG:
            a["created_at"] = datetime.now(timezone.utc).isoformat()
        await db.tv_achievements_catalog.insert_many(ACHIEVEMENTS_CATALOG)
    # Create indexes
    await db.tv_countries.create_index("code", unique=True)
    await db.tv_countries.create_index("region")
    await db.tv_categories.create_index("id", unique=True)
    await db.tv_categories.create_index("group")
    await db.tv_embassies.create_index("country_code")
    await db.tv_lessons.create_index("category_id")
    await db.tv_lessons.create_index("lesson_id", unique=True)
    await db.tv_lessons.create_index("type")
    await db.tv_quizzes.create_index("quiz_id", unique=True)
    await db.tv_user_progress.create_index([("user_id", 1), ("lesson_id", 1)])
    await db.tv_coaching_sessions.create_index("user_id")
    await db.tv_daily_usage.create_index([("user_id", 1), ("date", 1), ("action", 1)])
    await db.tv_challenges.create_index([("challenger_id", 1), ("status", 1)])
    await db.tv_challenges.create_index([("challenged_id", 1), ("status", 1)])
    await db.tv_notification_prefs.create_index("user_id", unique=True)
    cat_count = await db.tv_categories.count_documents({})
    les_count = await db.tv_lessons.count_documents({})
    return {"status": "seeded", "countries": len(COUNTRY_DATA), "categories": cat_count, "embassies": len(EMBASSY_DATA), "lessons": les_count, "quizzes": len(QUIZ_TEMPLATES)}

# ══════════════════════════════════════
# COUNTRIES & EXPLORE
# ══════════════════════════════════════

@router.get("/countries")
async def list_countries(region: Optional[str] = None, search: Optional[str] = None, popular: Optional[bool] = None):
    db = get_db()
    query = {}
    if region:
        query["region"] = region
    if popular is not None:
        query["popular"] = popular
    if search:
        query["name"] = {"$regex": search, "$options": "i"}
    countries = await db.tv_countries.find(query, {"_id": 0}).sort("name", 1).to_list(200)
    regions = await db.tv_countries.distinct("region")
    return {"countries": countries, "regions": sorted(regions), "total": len(countries)}

@router.get("/countries/{code}")
async def get_country_detail(code: str):
    db = get_db()
    country = await db.tv_countries.find_one({"code": code.upper()}, {"_id": 0})
    if not country:
        raise HTTPException(status_code=404, detail="Country not found")
    embassies = await db.tv_embassies.find({"country_code": code.upper()}, {"_id": 0}).to_list(50)
    categories = await db.tv_categories.find({}, {"_id": 0}).to_list(200)
    return {"country": country, "embassies": embassies, "categories": categories}

@router.get("/countries/{code}/track")
async def get_country_track(
    code: str,
    user_id: Optional[str] = None,
    current_user: User = Depends(require_auth),
):
    """Country deep-link track: visa guide categories + lessons + plan-based locks."""
    db = get_db()
    country = await db.tv_countries.find_one({"code": code.upper()}, {"_id": 0})
    if not country:
        raise HTTPException(status_code=404, detail="Country not found")

    uid = user_id or current_user.user_id
    _ensure_user_scope(current_user, uid)
    plan = await _get_user_plan(db, uid)
    tier_rank = {"free": 0, "basic": 1, "premium": 2}
    plan_rank = tier_rank.get(plan, 0)

    country_name = str(country.get("name") or "")
    cats = await db.tv_categories.find(
        {"group": "Country Visa Guides", "name": {"$regex": f"^{re.escape(country_name)}:"}},
        {"_id": 0},
    ).to_list(20)

    cat_ids = [c.get("id") for c in cats]
    lessons = await db.tv_lessons.find(
        {"category_id": {"$in": cat_ids}}, {"_id": 0, "content": 0, "transcript": 0}
    ).to_list(400)
    lesson_ids = [l.get("lesson_id") for l in lessons]
    progress_docs = await db.tv_user_progress.find(
        {"user_id": uid, "lesson_id": {"$in": lesson_ids}}, {"_id": 0}
    ).to_list(500)
    progress_map = {p.get("lesson_id"): p for p in progress_docs}

    lessons_by_cat: dict = {}
    for les in lessons:
        prog = progress_map.get(les.get("lesson_id"), {})
        les["user_progress"] = prog.get("progress_pct", 0)
        les["user_completed"] = bool(prog.get("completed", False))
        lessons_by_cat.setdefault(les.get("category_id"), []).append(les)

    tracks = []
    for cat in sorted(cats, key=lambda c: (tier_rank.get(str(c.get("tier") or "free"), 0), str(c.get("name") or ""))):
        tier = str(cat.get("tier") or "free")
        locked = tier_rank.get(tier, 0) > plan_rank
        track_lessons = sorted(lessons_by_cat.get(cat.get("id"), []), key=lambda l: str(l.get("title") or ""))
        tracks.append(
            {
                "category_id": cat.get("id"),
                "name": cat.get("name"),
                "track_label": str(cat.get("name") or "").split(":", 1)[-1].strip(),
                "tier": tier,
                "icon": cat.get("icon"),
                "locked": locked,
                "lesson_count": len(track_lessons) or int(cat.get("lesson_count") or 0),
                "completed_count": sum(1 for l in track_lessons if l.get("user_completed")),
                "lessons": [] if locked else track_lessons[:15],
            }
        )

    embassies_count = await db.tv_embassies.count_documents({"country_code": code.upper()})
    try:
        await db.tv_country_track_views.insert_one(
            {
                "view_id": f"tvtrack_{uuid.uuid4().hex[:12]}",
                "user_id": uid,
                "country_code": code.upper(),
                "plan": plan,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        )
    except Exception:
        pass

    return {
        "country": country,
        "plan": plan,
        "tracks": tracks,
        "locked_tracks": sum(1 for t in tracks if t["locked"]),
        "visa_types": country.get("visa_types") or [],
        "embassies_count": embassies_count,
    }

@router.get("/trending")
async def get_trending():
    db = get_db()
    trending = await db.tv_countries.find({"popular": True}, {"_id": 0}).limit(10).to_list(10)
    return {"trending": trending}


@router.get("/bootstrap/{user_id}")
async def get_travel_visa_bootstrap(user_id: str, current_user: User = Depends(require_auth)):
    db = get_db()
    _ensure_user_scope(current_user, user_id)

    countries = await db.tv_countries.find({}, {"_id": 0}).sort("name", 1).to_list(200)
    regions = sorted(await db.tv_countries.distinct("region"))
    categories = await db.tv_categories.find({}, {"_id": 0}).to_list(600)
    category_groups = sorted({str(cat.get("group") or "Other") for cat in categories})
    trending = await db.tv_countries.find({"popular": True}, {"_id": 0}).limit(10).to_list(10)

    stats = await db.tv_user_stats.find_one({"user_id": user_id}, {"_id": 0})
    if not stats:
        stats = {
            "user_id": user_id,
            "total_xp": 0,
            "lessons_completed": 0,
            "quizzes_passed": 0,
            "simulations_completed": 0,
            "coaching_sessions": 0,
            "streak": 0,
        }

    total_lessons = await db.tv_lessons.count_documents({})
    completed = stats.get("lessons_completed", 0)
    quizzes = stats.get("quizzes_passed", 0)
    sims = stats.get("simulations_completed", 0)
    readiness = min(100, round((completed * 2 + quizzes * 5 + sims * 10) / max(1, total_lessons * 0.5) * 100))
    stats["readiness_score"] = readiness

    plan = await _get_user_plan(db, user_id)
    limits = TIER_LIMITS.get(plan, TIER_LIMITS["free"])
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    usage_docs = await db.tv_daily_usage.find({"user_id": user_id, "date": today}, {"_id": 0}).to_list(20)
    usage_today = {doc.get("action", "unknown"): doc.get("count", 0) for doc in usage_docs}

    subscription = {
        "plan": plan,
        "limits": limits,
        "usage_today": usage_today,
    }

    system_health = {
        "countries": await db.tv_countries.count_documents({}),
        "categories": await db.tv_categories.count_documents({}),
        "lessons": total_lessons,
        "quizzes": await db.tv_quizzes.count_documents({}),
        "embassies": await db.tv_embassies.count_documents({}),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    return {
        "countries": countries,
        "regions": regions,
        "categories": categories,
        "category_groups": category_groups,
        "trending": trending,
        "user_stats": stats,
        "subscription": subscription,
        "system_health": system_health,
    }

# ══════════════════════════════════════
# CATEGORIES & LESSONS
# ══════════════════════════════════════

@router.get("/categories")
async def list_categories(group: Optional[str] = None, search: Optional[str] = None):
    db = get_db()
    query = {}
    if group:
        query["group"] = group
    if search:
        query["name"] = {"$regex": search, "$options": "i"}
    cats = await db.tv_categories.find(query, {"_id": 0}).to_list(600)
    groups = await db.tv_categories.distinct("group")
    return {"categories": cats, "groups": sorted(groups), "total": len(cats)}

@router.get("/lessons")
async def list_lessons(
    category_id: Optional[str] = None,
    user_id: Optional[str] = None,
    current_user: User = Depends(require_auth),
):
    db = get_db()
    query = {}
    if category_id:
        query["category_id"] = category_id
    lessons = await db.tv_lessons.find(query, {"_id": 0}).to_list(200)
    if user_id:
        _ensure_user_scope(current_user, user_id)
        progress_map = {}
        progress_docs = await db.tv_user_progress.find({"user_id": user_id}, {"_id": 0}).to_list(500)
        for p in progress_docs:
            progress_map[p["lesson_id"]] = p
        for les in lessons:
            prog = progress_map.get(les.get("lesson_id"), {})
            les["user_progress"] = prog.get("progress_pct", 0)
            les["user_completed"] = prog.get("completed", False)
            les["user_bookmarked"] = prog.get("bookmarked", False)
    return {"lessons": lessons, "total": len(lessons)}

@router.get("/lessons/{lesson_id}")
async def get_lesson_detail(
    lesson_id: str,
    user_id: Optional[str] = None,
    current_user: User = Depends(require_auth),
):
    db = get_db()
    lesson = await db.tv_lessons.find_one({"lesson_id": lesson_id}, {"_id": 0})
    if not lesson:
        raise HTTPException(status_code=404, detail="Lesson not found")
    user_progress = None
    if user_id:
        _ensure_user_scope(current_user, user_id)
        user_progress = await db.tv_user_progress.find_one({"user_id": user_id, "lesson_id": lesson_id}, {"_id": 0})
    return {"lesson": lesson, "user_progress": user_progress}

# ══════════════════════════════════════
# QUIZZES
# ══════════════════════════════════════

@router.get("/quizzes")
async def list_quizzes(category_id: Optional[str] = None):
    db = get_db()
    query = {}
    if category_id:
        query["category_id"] = category_id
    quizzes = await db.tv_quizzes.find(query, {"_id": 0}).to_list(100)
    # Don't send correct answers to client
    for q in quizzes:
        if "questions" in q:
            for question in q["questions"]:
                question.pop("correct", None)
    return {"quizzes": quizzes, "total": len(quizzes)}

@router.get("/quizzes/{quiz_id}")
async def get_quiz(quiz_id: str):
    db = get_db()
    quiz = await db.tv_quizzes.find_one({"quiz_id": quiz_id}, {"_id": 0})
    if not quiz:
        raise HTTPException(status_code=404, detail="Quiz not found")
    safe_quiz = {**quiz}
    if "questions" in safe_quiz:
        for question in safe_quiz["questions"]:
            question.pop("correct", None)
    return {"quiz": safe_quiz}

@router.post("/quizzes/submit")
async def submit_quiz(req: QuizSubmitRequest, current_user: User = Depends(require_auth)):
    db = get_db()
    _ensure_user_scope(current_user, req.user_id)
    plan = await _get_user_plan(db, req.user_id)
    allowed = await _check_daily_limit(db, req.user_id, "quizzes", plan)
    if not allowed:
        raise HTTPException(status_code=429, detail=f"Daily quiz limit reached for {plan} plan. Upgrade for more.")
    quiz = await db.tv_quizzes.find_one({"quiz_id": req.quiz_id}, {"_id": 0})
    if not quiz:
        raise HTTPException(status_code=404, detail="Quiz not found")
    score = 0
    total = len(quiz.get("questions", []))
    results = []
    for i, question in enumerate(quiz.get("questions", [])):
        user_answer = req.answers.get(str(i))
        correct = question.get("correct")
        is_correct = user_answer == correct
        if is_correct:
            score += 1
        results.append({"question": question["q"], "user_answer": user_answer, "correct_answer": correct, "is_correct": is_correct})
    pct = round((score / total) * 100) if total > 0 else 0
    passed = pct >= quiz.get("passing_score", 70)
    xp_earned = quiz.get("xp_reward", 0) if passed else round(quiz.get("xp_reward", 0) * 0.25)
    await db.tv_quiz_results.insert_one({
        "user_id": req.user_id, "quiz_id": req.quiz_id, "score": score, "total": total,
        "percentage": pct, "passed": passed, "xp_earned": xp_earned,
        "submitted_at": datetime.now(timezone.utc).isoformat(),
    })
    if passed:
        await _update_user_stats(db, req.user_id, "quizzes_passed", 1, xp_earned)
    else:
        await _update_user_stats(db, req.user_id, "quizzes_attempted", 1, xp_earned)
    return {"score": score, "total": total, "percentage": pct, "passed": passed, "xp_earned": xp_earned, "results": results}

# ══════════════════════════════════════
# EMBASSIES
# ══════════════════════════════════════

@router.get("/embassies")
async def list_embassies(country_code: Optional[str] = None, search: Optional[str] = None):
    db = get_db()
    query = {}
    if country_code:
        query["country_code"] = country_code.upper()
    if search:
        safe_search = re.escape(search)
        query["$or"] = [{"name": {"$regex": safe_search, "$options": "i"}}, {"city": {"$regex": safe_search, "$options": "i"}}]
    embassies = await db.tv_embassies.find(query, {"_id": 0}).to_list(200)
    return {"embassies": embassies, "total": len(embassies)}

# ══════════════════════════════════════
# AI COACHING
# ══════════════════════════════════════

@router.post("/coach")
async def ai_coach_chat(req: CoachRequest, current_user: User = Depends(require_auth)):
    db = get_db()
    _ensure_user_scope(current_user, req.user_id)
    plan = await _get_user_plan(db, req.user_id)
    allowed = await _check_daily_limit(db, req.user_id, "ai_credits", plan)
    if not allowed:
        raise HTTPException(status_code=429, detail=f"Daily AI coaching limit reached for {plan} plan. Upgrade for more.")
    session_id = req.session_id or str(uuid.uuid4())
    system_msg = (
        "You are an expert AI Visa Coach for the Travel Visa platform. "
        "You help users prepare for visa interviews, understand documentation requirements, "
        "discover embassy procedures, and learn how to legally travel or relocate internationally. "
        "IMPORTANT DISCLAIMERS: "
        "1) You provide educational coaching only - no guaranteed visa approvals. "
        "2) Always recommend users verify with official government sources. "
        "3) Never assist with illegal immigration, visa fraud, or fake documents. "
        "4) Be encouraging, clear, and professional. "
        f"User's target country: {req.country or 'Not specified'}. "
        f"Visa type of interest: {req.visa_type or 'General'}. "
        "Provide specific, actionable advice tailored to the user's situation."
    )
    try:
        chat = LlmChat(api_key=LLM_KEY, session_id=session_id, system_message=system_msg)
        chat.with_model("openai", "gpt-5.2")
        # Load chat history from DB
        history = await db.tv_coaching_sessions.find(
            {"session_id": session_id},
            {"_id": 0, "role": 1, "content": 1}
        ).sort("created_at", 1).to_list(50)
        for h in history:
            if h.get("role") == "user":
                chat.messages.append({"role": "user", "content": h["content"]})
            elif h.get("role") == "assistant":
                chat.messages.append({"role": "assistant", "content": h["content"]})
        user_message = UserMessage(text=req.message)
        response = await chat.send_message(user_message)
        now = datetime.now(timezone.utc).isoformat()
        await db.tv_coaching_sessions.insert_many([
            {"session_id": session_id, "user_id": req.user_id, "role": "user", "content": req.message, "country": req.country, "visa_type": req.visa_type, "created_at": now},
            {"session_id": session_id, "user_id": req.user_id, "role": "assistant", "content": response, "created_at": now},
        ])
        await _update_user_stats(db, req.user_id, "coaching_sessions", 1, 10)
        return {"session_id": session_id, "response": response}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI coaching error: {str(e)}")

# ══════════════════════════════════════
# INTERVIEW SIMULATOR
# ══════════════════════════════════════

@router.post("/interview/start")
async def start_interview_simulation(req: InterviewSimRequest, current_user: User = Depends(require_auth)):
    db = get_db()
    _ensure_user_scope(current_user, req.user_id)
    plan = await _get_user_plan(db, req.user_id)
    allowed = await _check_daily_limit(db, req.user_id, "simulations", plan)
    if not allowed:
        raise HTTPException(status_code=429, detail=f"Daily simulation limit reached for {plan} plan.")
    session_id = str(uuid.uuid4())
    difficulty_map = {"easy": 5, "medium": 8, "hard": 12}
    num_questions = difficulty_map.get(req.difficulty, 8)
    system_msg = (
        f"You are a visa interview officer at the {req.country} embassy. "
        f"Conduct a realistic {req.visa_type} visa interview. "
        f"Difficulty: {req.difficulty}. "
        f"Generate exactly {num_questions} interview questions one at a time. "
        "After each answer, provide brief coaching feedback. "
        "Be professional but thorough. Test the applicant's knowledge and preparation."
    )
    try:
        chat = LlmChat(api_key=LLM_KEY, session_id=session_id, system_message=system_msg)
        chat.with_model("openai", "gpt-5.2")
        first_msg = UserMessage(text=f"I'm here for my {req.visa_type} visa interview for {req.country}. Please begin the interview.")
        response = await chat.send_message(first_msg)
        now = datetime.now(timezone.utc).isoformat()
        await db.tv_interview_sessions.insert_one({
            "session_id": session_id, "user_id": req.user_id, "country": req.country,
            "visa_type": req.visa_type, "difficulty": req.difficulty,
            "total_questions": num_questions, "current_question": 1,
            "status": "in_progress", "started_at": now,
            "messages": [{"role": "assistant", "content": response, "timestamp": now}],
        })
        return {"session_id": session_id, "question": response, "question_number": 1, "total_questions": num_questions}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Interview simulation error: {str(e)}")

@router.post("/interview/answer")
async def answer_interview_question(req: InterviewAnswerRequest, current_user: User = Depends(require_auth)):
    db = get_db()
    _ensure_user_scope(current_user, req.user_id)
    session = await db.tv_interview_sessions.find_one({"session_id": req.session_id}, {"_id": 0})
    if not session:
        raise HTTPException(status_code=404, detail="Interview session not found")
    if session.get("user_id") != req.user_id:
        raise HTTPException(status_code=403, detail="Forbidden: interview session user mismatch")
    if session["status"] != "in_progress":
        return {"status": "completed", "message": "This interview session is already complete."}
    system_msg = (
        f"You are a visa interview officer at the {session['country']} embassy conducting a {session['visa_type']} interview. "
        f"Difficulty: {session['difficulty']}. "
        f"This is question {session['current_question']} of {session['total_questions']}. "
        "After the applicant answers, provide: 1) Brief feedback on their answer (strengths/weaknesses), "
        "2) A confidence score 1-10, 3) Then ask the next question. "
        "If this is the last question, provide an overall assessment instead of a new question."
    )
    try:
        chat = LlmChat(api_key=LLM_KEY, session_id=req.session_id, system_message=system_msg)
        chat.with_model("openai", "gpt-5.2")
        for msg in session.get("messages", []):
            chat.messages.append({"role": msg["role"], "content": msg["content"]})
        user_msg = UserMessage(text=req.answer)
        response = await chat.send_message(user_msg)
        now = datetime.now(timezone.utc).isoformat()
        new_question_num = session["current_question"] + 1
        is_complete = new_question_num > session["total_questions"]
        updates = {
            "$push": {"messages": {"$each": [
                {"role": "user", "content": req.answer, "timestamp": now},
                {"role": "assistant", "content": response, "timestamp": now},
            ]}},
            "$set": {"current_question": new_question_num},
        }
        if is_complete:
            updates["$set"]["status"] = "completed"
            updates["$set"]["completed_at"] = now
            await _update_user_stats(db, req.user_id, "simulations_completed", 1, 100)
        await db.tv_interview_sessions.update_one({"session_id": req.session_id}, updates)
        return {
            "response": response,
            "question_number": new_question_num,
            "total_questions": session["total_questions"],
            "is_complete": is_complete,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Interview answer error: {str(e)}")

# ══════════════════════════════════════
# PROGRESS & STATS
# ══════════════════════════════════════

@router.post("/progress/update")
async def update_progress(req: ProgressUpdateRequest, current_user: User = Depends(require_auth)):
    db = get_db()
    _ensure_user_scope(current_user, req.user_id)
    now = datetime.now(timezone.utc).isoformat()
    update_data = {
        "progress_pct": req.progress_pct,
        "completed": req.completed,
        "bookmarked": req.bookmarked,
        "updated_at": now,
    }
    if req.notes is not None:
        update_data["notes"] = req.notes
    await db.tv_user_progress.update_one(
        {"user_id": req.user_id, "lesson_id": req.lesson_id},
        {"$set": update_data, "$setOnInsert": {"created_at": now}},
        upsert=True,
    )
    xp = 0
    if req.completed:
        lesson = await db.tv_lessons.find_one({"lesson_id": req.lesson_id}, {"_id": 0, "xp": 1})
        xp = lesson.get("xp", 50) if lesson else 50
        await _update_user_stats(db, req.user_id, "lessons_completed", 1, xp)
    return {"status": "updated", "xp_earned": xp}

@router.get("/progress/{user_id}")
async def get_user_progress(user_id: str, current_user: User = Depends(require_auth)):
    db = get_db()
    _ensure_user_scope(current_user, user_id)
    progress = await db.tv_user_progress.find({"user_id": user_id}, {"_id": 0}).to_list(500)
    stats = await db.tv_user_stats.find_one({"user_id": user_id}, {"_id": 0})
    if not stats:
        stats = {"user_id": user_id, "total_xp": 0, "lessons_completed": 0, "quizzes_passed": 0, "simulations_completed": 0, "coaching_sessions": 0, "streak": 0}
    # Calculate readiness score
    total_lessons = await db.tv_lessons.count_documents({})
    completed = stats.get("lessons_completed", 0)
    quizzes = stats.get("quizzes_passed", 0)
    sims = stats.get("simulations_completed", 0)
    readiness = min(100, round((completed * 2 + quizzes * 5 + sims * 10) / max(1, total_lessons * 0.5) * 100))
    stats["readiness_score"] = readiness
    # Get achievements
    earned = await db.tv_user_achievements.find({"user_id": user_id}, {"_id": 0}).to_list(50)
    return {"progress": progress, "stats": stats, "achievements": earned, "readiness_score": readiness}

@router.get("/readiness/{user_id}")
async def get_readiness_score(user_id: str, current_user: User = Depends(require_auth)):
    db = get_db()
    _ensure_user_scope(current_user, user_id)
    stats = await db.tv_user_stats.find_one({"user_id": user_id}, {"_id": 0})
    if not stats:
        return {"readiness_score": 0, "breakdown": {"lessons": 0, "quizzes": 0, "simulations": 0, "coaching": 0}}
    total_lessons = await db.tv_lessons.count_documents({})
    completed = stats.get("lessons_completed", 0)
    quizzes = stats.get("quizzes_passed", 0)
    sims = stats.get("simulations_completed", 0)
    coaching = stats.get("coaching_sessions", 0)
    readiness = min(100, round((completed * 2 + quizzes * 5 + sims * 10 + coaching * 3) / max(1, total_lessons * 0.5) * 100))
    return {
        "readiness_score": readiness,
        "breakdown": {"lessons": min(100, completed * 5), "quizzes": min(100, quizzes * 10), "simulations": min(100, sims * 15), "coaching": min(100, coaching * 8)},
        "total_xp": stats.get("total_xp", 0),
        "streak": stats.get("streak", 0),
    }

async def _update_user_stats(db, user_id: str, field: str, increment: int, xp: int):
    await db.tv_user_stats.update_one(
        {"user_id": user_id},
        {"$inc": {field: increment, "total_xp": xp}, "$setOnInsert": {"created_at": datetime.now(timezone.utc).isoformat()}},
        upsert=True,
    )
    # Update streak
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    streak_doc = await db.tv_user_stats.find_one({"user_id": user_id}, {"_id": 0, "last_active_date": 1, "streak": 1})
    last_date = streak_doc.get("last_active_date", "") if streak_doc else ""
    if last_date == today:
        pass
    else:
        yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
        if last_date == yesterday:
            await db.tv_user_stats.update_one({"user_id": user_id}, {"$inc": {"streak": 1}, "$set": {"last_active_date": today}})
        else:
            await db.tv_user_stats.update_one({"user_id": user_id}, {"$set": {"streak": 1, "last_active_date": today}})
    # Auto-grant achievements
    try:
        from routes.travel_visa_ext import check_and_grant_achievements
        await check_and_grant_achievements(db, user_id)
    except Exception as exc:
        logger.warning("travel_visa achievements grant failed for user %s: %s", user_id, exc)

# ══════════════════════════════════════
# SAVED CONTENT
# ══════════════════════════════════════

@router.post("/saved/toggle")
async def toggle_saved_content(req: SaveContentRequest, current_user: User = Depends(require_auth)):
    db = get_db()
    _ensure_user_scope(current_user, req.user_id)
    existing = await db.tv_saved_content.find_one({"user_id": req.user_id, "content_id": req.content_id}, {"_id": 0})
    if existing:
        await db.tv_saved_content.delete_one({"user_id": req.user_id, "content_id": req.content_id})
        return {"saved": False}
    plan = await _get_user_plan(db, req.user_id)
    limits = TIER_LIMITS.get(plan, TIER_LIMITS["free"])
    count = await db.tv_saved_content.count_documents({"user_id": req.user_id})
    if count >= limits["max_saved"]:
        raise HTTPException(status_code=429, detail=f"Saved content limit reached for {plan} plan.")
    await db.tv_saved_content.insert_one({
        "user_id": req.user_id, "content_id": req.content_id, "content_type": req.content_type,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    return {"saved": True}

@router.get("/saved/{user_id}")
async def get_saved_content(user_id: str, current_user: User = Depends(require_auth)):
    db = get_db()
    _ensure_user_scope(current_user, user_id)
    saved = await db.tv_saved_content.find({"user_id": user_id}, {"_id": 0}).to_list(500)
    return {"saved": saved, "total": len(saved)}

# ══════════════════════════════════════
# SEARCH
# ══════════════════════════════════════

@router.get("/search")
async def global_search(q: str = Query(..., min_length=2)):
    db = get_db()
    regex = {"$regex": q, "$options": "i"}
    countries = await db.tv_countries.find({"name": regex}, {"_id": 0}).limit(5).to_list(5)
    categories = await db.tv_categories.find({"name": regex}, {"_id": 0}).limit(5).to_list(5)
    lessons = await db.tv_lessons.find({"title": regex}, {"_id": 0}).limit(5).to_list(5)
    embassies = await db.tv_embassies.find({"$or": [{"name": regex}, {"city": regex}]}, {"_id": 0}).limit(5).to_list(5)
    return {"countries": countries, "categories": categories, "lessons": lessons, "embassies": embassies, "query": q}

# ══════════════════════════════════════
# SUBSCRIPTION TIER INFO
# ══════════════════════════════════════

@router.get("/subscription/info/{user_id}")
async def get_subscription_info(user_id: str, current_user: User = Depends(require_auth)):
    db = get_db()
    _ensure_user_scope(current_user, user_id)
    plan = await _get_user_plan(db, user_id)
    limits = TIER_LIMITS.get(plan, TIER_LIMITS["free"])
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    usage_docs = await db.tv_daily_usage.find({"user_id": user_id, "date": today}, {"_id": 0}).to_list(10)
    usage = {}
    for doc in usage_docs:
        usage[doc["action"]] = doc.get("count", 0)
    return {
        "plan": plan,
        "limits": limits,
        "usage_today": usage,
        "tier_benefits": {
            "free": "Access to basic lessons, 3 AI coaching sessions/day, 2 quizzes/day",
            "basic": "Expanded access, 25 AI sessions/day, 15 quizzes/day, 5 simulations/day",
            "premium": "Unlimited everything, priority AI, advanced analytics, VIP coaching paths",
        },
    }

# ══════════════════════════════════════
# COACHING HISTORY
# ══════════════════════════════════════

@router.get("/coaching/history/{user_id}")
async def get_coaching_history(user_id: str, session_id: Optional[str] = None, current_user: User = Depends(require_auth)):
    db = get_db()
    _ensure_user_scope(current_user, user_id)
    query = {"user_id": user_id}
    if session_id:
        query["session_id"] = session_id
    messages = await db.tv_coaching_sessions.find(query, {"_id": 0}).sort("created_at", 1).to_list(200)
    sessions = {}
    for msg in messages:
        sid = msg.get("session_id", "unknown")
        if sid not in sessions:
            sessions[sid] = {"session_id": sid, "messages": [], "country": msg.get("country"), "visa_type": msg.get("visa_type"), "started_at": msg.get("created_at")}
        sessions[sid]["messages"].append({"role": msg["role"], "content": msg["content"], "timestamp": msg.get("created_at")})
    return {"sessions": list(sessions.values()), "total": len(sessions)}

# ══════════════════════════════════════
# ACHIEVEMENTS
# ══════════════════════════════════════

@router.get("/achievements/catalog")
async def get_achievements_catalog():
    db = get_db()
    catalog = await db.tv_achievements_catalog.find({}, {"_id": 0}).to_list(50)
    return {"achievements": catalog}

@router.get("/achievements/{user_id}")
async def get_user_achievements(user_id: str, current_user: User = Depends(require_auth)):
    db = get_db()
    _ensure_user_scope(current_user, user_id)
    earned = await db.tv_user_achievements.find({"user_id": user_id}, {"_id": 0}).to_list(50)
    catalog = await db.tv_achievements_catalog.find({}, {"_id": 0}).to_list(50)
    return {"earned": earned, "catalog": catalog, "earned_count": len(earned), "total_count": len(catalog)}

# ══════════════════════════════════════
# DAILY LESSONS
# ══════════════════════════════════════

@router.get("/daily-lessons")
async def get_daily_lessons():
    db = get_db()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    daily = await db.tv_daily_lessons.find({"date": today}, {"_id": 0}).to_list(5)
    if not daily:
        # Auto-generate daily lessons from available pool
        all_lessons = await db.tv_lessons.find({}, {"_id": 0, "lesson_id": 1, "title": 1, "category_id": 1, "type": 1, "duration_min": 1, "difficulty": 1}).to_list(200)
        import random
        if len(all_lessons) >= 2:
            selected = random.sample(all_lessons, min(2, len(all_lessons)))
            docs_to_insert = []
            for les in selected:
                doc = {k: v for k, v in les.items() if k != "_id"}
                doc["date"] = today
                doc["featured"] = True
                docs_to_insert.append(doc)
            if docs_to_insert:
                await db.tv_daily_lessons.insert_many(docs_to_insert)
            daily = docs_to_insert
    return {"lessons": daily, "date": today}

# ══════════════════════════════════════
# INTERVIEW HISTORY
# ══════════════════════════════════════

@router.get("/interview/history/{user_id}")
async def get_interview_history(user_id: str, current_user: User = Depends(require_auth)):
    db = get_db()
    _ensure_user_scope(current_user, user_id)
    sessions = await db.tv_interview_sessions.find(
        {"user_id": user_id},
        {"_id": 0, "session_id": 1, "country": 1, "visa_type": 1, "difficulty": 1, "status": 1, "started_at": 1, "completed_at": 1, "total_questions": 1}
    ).sort("started_at", -1).to_list(50)
    return {"sessions": sessions, "total": len(sessions)}

# ══════════════════════════════════════
# DOCUMENT CHECKLIST (AI-generated)
# ══════════════════════════════════════

@router.post("/checklist/generate")
async def generate_document_checklist(
    user_id: str = Body(...),
    country: str = Body(...),
    visa_type: str = Body(...),
    purpose: str = Body("general"),
    current_user: User = Depends(require_auth),
):
    db = get_db()
    _ensure_user_scope(current_user, user_id)
    plan = await _get_user_plan(db, user_id)
    allowed = await _check_daily_limit(db, user_id, "ai_credits", plan)
    if not allowed:
        raise HTTPException(status_code=429, detail=f"Daily AI limit reached for {plan} plan.")
    system_msg = (
        "You are a visa documentation expert. Generate a comprehensive, structured document checklist "
        f"for a {visa_type} visa application to {country}. Purpose: {purpose}. "
        "Format as a JSON array of objects with fields: item, description, required (boolean), tips. "
        "Only output the JSON array, no other text."
    )
    try:
        chat = LlmChat(api_key=LLM_KEY, session_id=f"checklist-{uuid.uuid4()}", system_message=system_msg)
        chat.with_model("openai", "gpt-5.2")
        response = await chat.send_message(UserMessage(text=f"Generate checklist for {visa_type} visa to {country}"))
        import json
        try:
            checklist = json.loads(response.strip().strip("```json").strip("```"))
        except json.JSONDecodeError:
            checklist = [{"item": "Document checklist", "description": response, "required": True, "tips": "See AI response for details"}]
        return {"checklist": checklist, "country": country, "visa_type": visa_type}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Checklist generation error: {str(e)}")

# ══════════════════════════════════════
# ADMIN ENDPOINTS
# ══════════════════════════════════════

@router.get("/admin/stats")
async def admin_stats(_admin_user: User = Depends(require_admin)):
    db = get_db()
    total_users = await db.tv_user_stats.count_documents({})
    total_lessons = await db.tv_lessons.count_documents({})
    total_quizzes = await db.tv_quizzes.count_documents({})
    total_coaching = await db.tv_coaching_sessions.count_documents({})
    total_simulations = await db.tv_interview_sessions.count_documents({})
    total_countries = await db.tv_countries.count_documents({})
    total_embassies = await db.tv_embassies.count_documents({})
    total_categories = await db.tv_categories.count_documents({})
    return {
        "total_users": total_users, "total_lessons": total_lessons, "total_quizzes": total_quizzes,
        "total_coaching_messages": total_coaching, "total_simulations": total_simulations,
        "total_countries": total_countries, "total_embassies": total_embassies, "total_categories": total_categories,
    }

@router.get("/admin/engagement")
async def admin_engagement(_admin_user: User = Depends(require_admin)):
    db = get_db()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    daily_usage = await db.tv_daily_usage.find({"date": today}, {"_id": 0}).to_list(1000)
    action_totals = {}
    for doc in daily_usage:
        action = doc.get("action", "unknown")
        action_totals[action] = action_totals.get(action, 0) + doc.get("count", 0)
    top_users = await db.tv_user_stats.find({}, {"_id": 0}).sort("total_xp", -1).limit(10).to_list(10)
    return {"today_usage": action_totals, "top_users": top_users, "date": today}


# ══════════════════════════════════════
# LEADERBOARD & GAMIFICATION
# ══════════════════════════════════════

@router.get("/leaderboard/weekly")
async def weekly_leaderboard(limit: int = Query(default=25, le=100)):
    db = get_db()
    now = datetime.now(timezone.utc)
    # Week starts Monday
    monday = (now - timedelta(days=now.weekday())).strftime("%Y-%m-%d")
    # Aggregate weekly XP from quiz results + progress completions this week
    pipeline = [
        {"$match": {"last_active_date": {"$gte": monday}}},
        {"$project": {
            "_id": 0, "user_id": 1, "total_xp": 1, "streak": 1,
            "lessons_completed": 1, "quizzes_passed": 1,
            "simulations_completed": 1, "coaching_sessions": 1,
        }},
        {"$sort": {"total_xp": -1}},
        {"$limit": limit},
    ]
    leaders = await db.tv_user_stats.aggregate(pipeline).to_list(limit)
    # Enrich with user display info
    for i, entry in enumerate(leaders):
        uid = entry.get("user_id", "")
        user = await db.users.find_one({"user_id": uid}, {"_id": 0, "name": 1, "email": 1, "profile_image": 1, "subscription_plan": 1})
        if user:
            entry["name"] = user.get("name") or user.get("email", "Anonymous")[:20]
            entry["avatar"] = user.get("profile_image", "")
            entry["plan"] = user.get("subscription_plan", "free")
        else:
            entry["name"] = f"Learner #{i+1}"
            entry["avatar"] = ""
            entry["plan"] = "free"
        entry["rank"] = i + 1
        # Compute tier badge
        xp = entry.get("total_xp", 0)
        if xp >= 5000:
            entry["tier"] = "diamond"
        elif xp >= 2000:
            entry["tier"] = "platinum"
        elif xp >= 1000:
            entry["tier"] = "gold"
        elif xp >= 500:
            entry["tier"] = "silver"
        else:
            entry["tier"] = "bronze"
    return {"leaderboard": leaders, "week_start": monday, "total_participants": len(leaders)}

@router.get("/leaderboard/alltime")
async def alltime_leaderboard(limit: int = Query(default=25, le=100)):
    db = get_db()
    leaders = await db.tv_user_stats.find(
        {}, {"_id": 0, "user_id": 1, "total_xp": 1, "streak": 1, "lessons_completed": 1, "quizzes_passed": 1, "simulations_completed": 1, "coaching_sessions": 1}
    ).sort("total_xp", -1).limit(limit).to_list(limit)
    for i, entry in enumerate(leaders):
        uid = entry.get("user_id", "")
        user = await db.users.find_one({"user_id": uid}, {"_id": 0, "name": 1, "email": 1, "profile_image": 1, "subscription_plan": 1})
        if user:
            entry["name"] = user.get("name") or user.get("email", "Anonymous")[:20]
            entry["avatar"] = user.get("profile_image", "")
            entry["plan"] = user.get("subscription_plan", "free")
        else:
            entry["name"] = f"Learner #{i+1}"
            entry["avatar"] = ""
            entry["plan"] = "free"
        entry["rank"] = i + 1
        xp = entry.get("total_xp", 0)
        if xp >= 5000:
            entry["tier"] = "diamond"
        elif xp >= 2000:
            entry["tier"] = "platinum"
        elif xp >= 1000:
            entry["tier"] = "gold"
        elif xp >= 500:
            entry["tier"] = "silver"
        else:
            entry["tier"] = "bronze"
    return {"leaderboard": leaders, "total_participants": len(leaders)}

@router.get("/leaderboard/me/{user_id}")
async def my_leaderboard_position(user_id: str, current_user: User = Depends(require_auth)):
    db = get_db()
    _ensure_user_scope(current_user, user_id)
    stats = await db.tv_user_stats.find_one({"user_id": user_id}, {"_id": 0})
    if not stats:
        return {"rank": 0, "total_xp": 0, "tier": "bronze", "above_count": 0, "total_participants": 0}
    my_xp = stats.get("total_xp", 0)
    above = await db.tv_user_stats.count_documents({"total_xp": {"$gt": my_xp}})
    total = await db.tv_user_stats.count_documents({})
    rank = above + 1
    if my_xp >= 5000:
        tier = "diamond"
    elif my_xp >= 2000:
        tier = "platinum"
    elif my_xp >= 1000:
        tier = "gold"
    elif my_xp >= 500:
        tier = "silver"
    else:
        tier = "bronze"
    return {
        "rank": rank, "total_xp": my_xp, "tier": tier,
        "total_participants": total, "percentile": round(((total - rank) / max(total - 1, 1)) * 100, 1) if total > 1 else 100.0,
        "streak": stats.get("streak", 0),
        "lessons_completed": stats.get("lessons_completed", 0),
        "quizzes_passed": stats.get("quizzes_passed", 0),
        "simulations_completed": stats.get("simulations_completed", 0),
    }


# ══════════════════════════════════════
# CHALLENGE A FRIEND
# ══════════════════════════════════════

@router.post("/challenge/create")
async def create_challenge(req: ChallengeCreateRequest, current_user: User = Depends(require_auth)):
    db = get_db()
    _ensure_user_scope(current_user, req.challenger_id)
    quiz = await db.tv_quizzes.find_one({"quiz_id": req.quiz_id}, {"_id": 0})
    if not quiz:
        raise HTTPException(status_code=404, detail="Quiz not found")
    challenge_id = str(uuid.uuid4())[:12]
    now = datetime.now(timezone.utc).isoformat()
    await db.tv_challenges.insert_one({
        "challenge_id": challenge_id,
        "challenger_id": req.challenger_id,
        "challenged_id": req.challenged_id,
        "quiz_id": req.quiz_id,
        "quiz_title": quiz.get("title", "Quiz Challenge"),
        "status": "pending",
        "challenger_score": None,
        "challenged_score": None,
        "challenger_answers": None,
        "challenged_answers": None,
        "bonus_xp": 50,
        "created_at": now,
        "expires_at": (datetime.now(timezone.utc) + timedelta(days=3)).isoformat(),
    })
    # Create notification for challenged user
    await db.tv_notifications.insert_one({
        "user_id": req.challenged_id,
        "type": "challenge_invite",
        "title": "Quiz Challenge Received!",
        "message": f"You've been challenged to take '{quiz.get('title', 'a quiz')}'! Accept and compete for bonus XP.",
        "data": {"challenge_id": challenge_id, "quiz_id": req.quiz_id},
        "read": False,
        "created_at": now,
    })
    return {"challenge_id": challenge_id, "status": "pending", "quiz_title": quiz.get("title")}

@router.post("/challenge/submit")
async def submit_challenge_answer(req: ChallengeAnswerRequest, current_user: User = Depends(require_auth)):
    db = get_db()
    _ensure_user_scope(current_user, req.user_id)
    challenge = await db.tv_challenges.find_one({"challenge_id": req.challenge_id}, {"_id": 0})
    if not challenge:
        raise HTTPException(status_code=404, detail="Challenge not found")
    if req.user_id not in {challenge.get("challenger_id"), challenge.get("challenged_id")}:
        raise HTTPException(status_code=403, detail="Forbidden: user not part of this challenge")
    if challenge["status"] == "completed":
        raise HTTPException(status_code=400, detail="Challenge already completed")
    quiz = await db.tv_quizzes.find_one({"quiz_id": challenge["quiz_id"]})
    if not quiz:
        raise HTTPException(status_code=404, detail="Quiz not found")
    # Score the answers
    score = 0
    total = len(quiz.get("questions", []))
    for i, question in enumerate(quiz.get("questions", [])):
        if req.answers.get(str(i)) == question.get("correct"):
            score += 1
    pct = round((score / total) * 100) if total > 0 else 0
    is_challenger = req.user_id == challenge["challenger_id"]
    field_score = "challenger_score" if is_challenger else "challenged_score"
    field_answers = "challenger_answers" if is_challenger else "challenged_answers"
    updates = {"$set": {field_score: pct, field_answers: req.answers}}
    # Check if both have submitted
    other_score_field = "challenged_score" if is_challenger else "challenger_score"
    other_score = challenge.get(other_score_field)
    if other_score is not None:
        updates["$set"]["status"] = "completed"
        updates["$set"]["completed_at"] = datetime.now(timezone.utc).isoformat()
        # Determine winner
        my_pct = pct
        other_pct = other_score
        if my_pct > other_pct:
            updates["$set"]["winner_id"] = req.user_id
        elif other_pct > my_pct:
            other_id = challenge["challenged_id"] if is_challenger else challenge["challenger_id"]
            updates["$set"]["winner_id"] = other_id
        else:
            updates["$set"]["winner_id"] = "tie"
        # Award bonus XP to both participants
        bonus = challenge.get("bonus_xp", 50)
        await _update_user_stats(db, challenge["challenger_id"], "challenges_completed", 1, bonus)
        await _update_user_stats(db, challenge["challenged_id"], "challenges_completed", 1, bonus)
        # Extra XP for winner
        winner = updates["$set"]["winner_id"]
        if winner and winner != "tie":
            await _update_user_stats(db, winner, "challenges_won", 1, bonus)
    else:
        updates["$set"]["status"] = "in_progress"
    await db.tv_challenges.update_one({"challenge_id": req.challenge_id}, updates)
    return {"score": pct, "total": total, "status": updates["$set"].get("status", "in_progress"), "winner_id": updates["$set"].get("winner_id")}

@router.get("/challenge/list/{user_id}")
async def list_challenges(user_id: str, status: Optional[str] = None, current_user: User = Depends(require_auth)):
    db = get_db()
    _ensure_user_scope(current_user, user_id)
    query = {"$or": [{"challenger_id": user_id}, {"challenged_id": user_id}]}
    if status:
        query["status"] = status
    challenges = await db.tv_challenges.find(query, {"_id": 0}).sort("created_at", -1).to_list(50)
    # Enrich with user names
    for ch in challenges:
        for field in ["challenger_id", "challenged_id"]:
            uid = ch.get(field, "")
            user = await db.users.find_one({"user_id": uid}, {"_id": 0, "name": 1, "email": 1})
            ch[field.replace("_id", "_name")] = (user.get("name") or user.get("email", "Anonymous")[:20]) if user else "Unknown"
    return {"challenges": challenges, "total": len(challenges)}

@router.get("/challenge/{challenge_id}")
async def get_challenge_detail(challenge_id: str, current_user: User = Depends(require_auth)):
    db = get_db()
    challenge = await db.tv_challenges.find_one({"challenge_id": challenge_id}, {"_id": 0})
    if not challenge:
        raise HTTPException(status_code=404, detail="Challenge not found")
    if (not current_user.is_admin) and current_user.user_id not in {
        challenge.get("challenger_id"),
        challenge.get("challenged_id"),
    }:
        raise HTTPException(status_code=403, detail="Forbidden: challenge access denied")
    for field in ["challenger_id", "challenged_id"]:
        uid = challenge.get(field, "")
        user = await db.users.find_one({"user_id": uid}, {"_id": 0, "name": 1, "email": 1})
        challenge[field.replace("_id", "_name")] = (user.get("name") or user.get("email", "Anonymous")[:20]) if user else "Unknown"
    return {"challenge": challenge}

@router.get("/challenge/invite-code/{challenge_id}")
async def get_challenge_invite_code(challenge_id: str, current_user: User = Depends(require_auth)):
    """Generate a shareable invite code for challenge"""
    db = get_db()
    challenge = await db.tv_challenges.find_one(
        {"challenge_id": challenge_id},
        {"_id": 0, "challenge_id": 1, "quiz_title": 1, "status": 1, "challenger_id": 1, "challenged_id": 1},
    )
    if not challenge:
        raise HTTPException(status_code=404, detail="Challenge not found")
    if (not current_user.is_admin) and current_user.user_id not in {
        challenge.get("challenger_id"),
        challenge.get("challenged_id"),
    }:
        raise HTTPException(status_code=403, detail="Forbidden: challenge invite access denied")
    return {"invite_code": challenge_id, "quiz_title": challenge.get("quiz_title"), "status": challenge.get("status")}

# ══════════════════════════════════════
# NOTIFICATION PREFERENCES
# ══════════════════════════════════════

@router.get("/notifications/prefs/{user_id}")
async def get_notification_prefs(user_id: str, current_user: User = Depends(require_auth)):
    db = get_db()
    _ensure_user_scope(current_user, user_id)
    prefs = await db.tv_notification_prefs.find_one({"user_id": user_id}, {"_id": 0})
    if not prefs:
        prefs = {
            "user_id": user_id, "daily_lessons": True, "new_content": True,
            "challenge_invites": True, "streak_reminders": True, "weekly_digest": True,
            "email_notifications": False, "push_notifications": True,
        }
    return {"preferences": prefs}

@router.post("/notifications/prefs")
async def update_notification_prefs(req: NotificationPrefsRequest, current_user: User = Depends(require_auth)):
    db = get_db()
    _ensure_user_scope(current_user, req.user_id)
    now = datetime.now(timezone.utc).isoformat()
    prefs = {
        "user_id": req.user_id, "daily_lessons": req.daily_lessons, "new_content": req.new_content,
        "challenge_invites": req.challenge_invites, "streak_reminders": req.streak_reminders,
        "weekly_digest": req.weekly_digest, "email_notifications": req.email_notifications,
        "push_notifications": req.push_notifications, "updated_at": now,
    }
    await db.tv_notification_prefs.update_one(
        {"user_id": req.user_id}, {"$set": prefs, "$setOnInsert": {"created_at": now}}, upsert=True
    )
    return {"status": "updated", "preferences": prefs}

@router.get("/notifications/{user_id}")
async def get_notifications(user_id: str, unread_only: bool = False, current_user: User = Depends(require_auth)):
    db = get_db()
    _ensure_user_scope(current_user, user_id)
    query = {"user_id": user_id}
    if unread_only:
        query["read"] = False
    notifs = await db.tv_notifications.find(query, {"_id": 0}).sort("created_at", -1).limit(50).to_list(50)
    unread_count = await db.tv_notifications.count_documents({"user_id": user_id, "read": False})
    return {"notifications": notifs, "unread_count": unread_count}

@router.post("/notifications/read")
async def mark_notifications_read(
    user_id: str = Body(...),
    notification_ids: list = Body(default=None),
    current_user: User = Depends(require_auth),
):
    db = get_db()
    _ensure_user_scope(current_user, user_id)
    if notification_ids:
        await db.tv_notifications.update_many(
            {"user_id": user_id, "created_at": {"$in": notification_ids}}, {"$set": {"read": True}}
        )
    else:
        await db.tv_notifications.update_many({"user_id": user_id}, {"$set": {"read": True}})
    return {"status": "marked_read"}

# ══════════════════════════════════════
# VIDEO/AUDIO LEARNING MODULES
# ══════════════════════════════════════

@router.get("/media/lessons")
async def list_media_lessons(
    media_type: Optional[str] = None,
    category_id: Optional[str] = None,
    user_id: Optional[str] = None,
    current_user: User = Depends(require_auth),
):
    """List video/audio lessons"""
    db = get_db()
    query = {"type": {"$in": ["video", "audio"]}}
    if media_type:
        query["type"] = media_type
    if category_id:
        query["category_id"] = category_id
    lessons = await db.tv_lessons.find(query, {"_id": 0}).limit(100).to_list(100)
    if user_id:
        _ensure_user_scope(current_user, user_id)
        progress_docs = await db.tv_user_progress.find({"user_id": user_id}, {"_id": 0}).to_list(500)
        progress_map = {p["lesson_id"]: p for p in progress_docs}
        for les in lessons:
            prog = progress_map.get(les.get("lesson_id"), {})
            les["user_progress"] = prog.get("progress_pct", 0)
            les["user_completed"] = prog.get("completed", False)
            les["user_bookmarked"] = prog.get("bookmarked", False)
    return {"lessons": lessons, "total": len(lessons)}

@router.get("/media/continue/{user_id}")
async def continue_watching(user_id: str, current_user: User = Depends(require_auth)):
    """Get in-progress video/audio lessons"""
    db = get_db()
    _ensure_user_scope(current_user, user_id)
    in_progress = await db.tv_user_progress.find(
        {"user_id": user_id, "completed": False, "progress_pct": {"$gt": 0}},
        {"_id": 0}
    ).sort("updated_at", -1).limit(10).to_list(10)
    lesson_ids = [p["lesson_id"] for p in in_progress]
    lessons = await db.tv_lessons.find(
        {"lesson_id": {"$in": lesson_ids}, "type": {"$in": ["video", "audio"]}},
        {"_id": 0}
    ).to_list(20)
    lesson_map = {lesson_item["lesson_id"]: lesson_item for lesson_item in lessons}
    result = []
    for p in in_progress:
        les = lesson_map.get(p["lesson_id"])
        if les:
            les["user_progress"] = p.get("progress_pct", 0)
            result.append(les)
    return {"lessons": result, "total": len(result)}

@router.post("/media/progress")
async def update_media_progress(
    user_id: str = Body(...), lesson_id: str = Body(...),
    progress_pct: float = Body(...), current_time: float = Body(0),
    notes: Optional[str] = Body(None), bookmarked: bool = Body(False),
    current_user: User = Depends(require_auth),
):
    """Update playback progress for a video/audio lesson"""
    db = get_db()
    _ensure_user_scope(current_user, user_id)
    now = datetime.now(timezone.utc).isoformat()
    completed = progress_pct >= 95
    update_data = {
        "progress_pct": progress_pct, "completed": completed, "bookmarked": bookmarked,
        "current_time": current_time, "updated_at": now,
    }
    if notes is not None:
        update_data["notes"] = notes
    await db.tv_user_progress.update_one(
        {"user_id": user_id, "lesson_id": lesson_id},
        {"$set": update_data, "$setOnInsert": {"created_at": now}},
        upsert=True,
    )
    xp = 0
    if completed:
        lesson = await db.tv_lessons.find_one({"lesson_id": lesson_id}, {"_id": 0, "xp": 1})
        xp = lesson.get("xp", 50) if lesson else 50
        await _update_user_stats(db, user_id, "lessons_completed", 1, xp)
    return {"status": "updated", "completed": completed, "xp_earned": xp}

# ══════════════════════════════════════
# DAILY ROTATION CRON HELPER
# ══════════════════════════════════════

async def run_daily_lesson_rotation():
    """Called by scheduler to rotate daily lessons and send notifications"""
    db = get_db()
    import random
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    existing = await db.tv_daily_lessons.count_documents({"date": today})
    if existing > 0:
        return
    all_lessons = await db.tv_lessons.find(
        {"type": {"$in": ["video", "audio", "reading"]}},
        {"_id": 0, "lesson_id": 1, "title": 1, "category_id": 1, "type": 1, "duration_min": 1, "difficulty": 1}
    ).to_list(2000)
    if len(all_lessons) >= 2:
        selected = random.sample(all_lessons, 2)
        for les in selected:
            les["date"] = today
            les["featured"] = True
        await db.tv_daily_lessons.insert_many(selected)
        # Send notifications to users with daily_lessons enabled
        prefs = await db.tv_notification_prefs.find({"daily_lessons": True}, {"_id": 0, "user_id": 1}).to_list(10000)
        if prefs:
            now = datetime.now(timezone.utc).isoformat()
            notifs = []
            for p in prefs:
                notifs.append({
                    "user_id": p["user_id"], "type": "daily_lessons",
                    "title": "2 New Lessons Available Today!",
                    "message": f"New lessons: '{selected[0]['title']}' and '{selected[1]['title']}'. Start learning now!",
                    "data": {"lesson_ids": [s["lesson_id"] for s in selected]},
                    "read": False, "created_at": now,
                })
            if notifs:
                await db.tv_notifications.insert_many(notifs)
