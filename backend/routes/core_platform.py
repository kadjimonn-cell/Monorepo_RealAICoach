"""Core platform routes: conversations, scenarios, progress, achievements."""

import os
import json
import uuid
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, List
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from emergentintegrations.llm.chat import LlmChat, UserMessage
from routes.db import db, get_current_user, EMERGENT_LLM_KEY
from routes.payments_catalog import get_subscription_plan_from_gps
from services.ai_helpers import analyze_message_with_ai, get_ai_response as _get_ai_response_helper
from utils.access_control_engine import compute_effective_plan

logger = logging.getLogger(__name__)
router = APIRouter()

# ══════════ MODELS ══════════


class Scenario(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    category: str
    title: str
    description: str
    persona_name: str
    persona_description: str
    persona_personality: str
    difficulty: str
    objectives: List[str]
    tips: List[str]
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Message(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    role: str
    content: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    feedback: Optional[Dict[str, Any]] = None
    is_voice: bool = False


class Conversation(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    scenario_id: str
    scenario_title: str
    category: str
    messages: List[Message] = []
    status: str = "active"
    overall_feedback: Optional[Dict[str, Any]] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class AIResponseFeedbackRequest(BaseModel):
    user_id: str
    feature_key: str
    rating: int
    comment: Optional[str] = None
    response_excerpt: Optional[str] = None
    session_id: Optional[str] = None


class UserProgress(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    total_conversations: int = 0
    completed_conversations: int = 0
    daily_conversations: int = 0
    last_conversation_date: Optional[str] = None
    skills: Dict[str, int] = {
        "empathy": 50,
        "clarity": 50,
        "confidence": 50,
        "active_listening": 50,
        "emotional_intelligence": 50,
    }
    category_progress: Dict[str, int] = {
        "dating": 0,
        "workplace": 0,
        "friendship": 0,
        "family": 0,
        "networking": 0,
        "conflict": 0,
    }
    achievements: List[str] = []
    # Gamification fields
    xp: int = 0
    level: int = 1
    current_streak: int = 0
    longest_streak: int = 0
    streak_last_date: Optional[str] = None
    highest_score: int = 0
    total_messages_sent: int = 0
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class StartConversationRequest(BaseModel):
    user_id: str
    scenario_id: str


class SendMessageRequest(BaseModel):
    conversation_id: str
    user_id: str
    message: str


# Voice message request
class VoiceMessageRequest(BaseModel):
    conversation_id: str
    user_id: str
    audio_base64: str  # Base64 encoded audio
    audio_format: str = "webm"  # File extension hint: webm (web), m4a/caf (native recordings)


# ══════════ STATIC DATA ══════════

SCENARIOS = [
    # Dating Scenarios
    {
        "id": "dating-first-date",
        "category": "dating",
        "title": "First Date Conversation",
        "description": "Practice making a great first impression and keeping the conversation flowing on a first date.",
        "persona_name": "Alex",
        "persona_description": "A friendly, curious person you matched with on a dating app. They're interested in getting to know you better.",
        "persona_personality": "Warm, slightly nervous but enthusiastic, asks thoughtful questions, appreciates humor and authenticity.",
        "difficulty": "beginner",
        "objectives": ["Make a positive first impression", "Show genuine interest", "Keep conversation balanced"],
        "tips": ["Ask open-ended questions", "Share personal stories", "Be an active listener"],
    },
    {
        "id": "dating-expressing-feelings",
        "category": "dating",
        "title": "Expressing Your Feelings",
        "description": "Learn to communicate your feelings and intentions clearly in a romantic context.",
        "persona_name": "Jordan",
        "persona_description": "Someone you've been dating for a few weeks. The relationship is going well and it's time to discuss where things are heading.",
        "persona_personality": "Thoughtful, values honesty, a bit guarded but opens up with trust, appreciates directness.",
        "difficulty": "intermediate",
        "objectives": ["Express feelings authentically", "Handle vulnerability", "Navigate emotional conversations"],
        "tips": ["Use 'I' statements", "Be specific about feelings", "Give space for their response"],
    },
    {
        "id": "dating-conflict-resolution",
        "category": "dating",
        "title": "Resolving Disagreements",
        "description": "Practice handling conflicts constructively in romantic relationships.",
        "persona_name": "Sam",
        "persona_description": "Your partner who is upset about a recent miscommunication. They feel hurt but want to work things out.",
        "persona_personality": "Emotional but fair, needs to feel heard, responds well to empathy and accountability.",
        "difficulty": "advanced",
        "objectives": ["Acknowledge their feelings", "Take responsibility appropriately", "Find common ground"],
        "tips": ["Listen before defending", "Validate their perspective", "Focus on solutions, not blame"],
    },
    # Workplace Scenarios
    {
        "id": "workplace-networking",
        "category": "workplace",
        "title": "Professional Networking",
        "description": "Practice making meaningful professional connections at events and meetings.",
        "persona_name": "Morgan",
        "persona_description": "A senior professional in your industry at a networking event. They're well-connected and could be a valuable contact.",
        "persona_personality": "Busy but approachable, appreciates concise communication, values substance over small talk.",
        "difficulty": "beginner",
        "objectives": ["Make a memorable impression", "Find common ground", "Exchange contact information naturally"],
        "tips": ["Have a clear elevator pitch", "Ask about their work", "Offer value, don't just take"],
    },
    {
        "id": "workplace-feedback",
        "category": "workplace",
        "title": "Giving Constructive Feedback",
        "description": "Learn to deliver feedback that helps colleagues improve without damaging relationships.",
        "persona_name": "Taylor",
        "persona_description": "A colleague whose recent work has had some issues. They're generally capable but need guidance.",
        "persona_personality": "Sensitive to criticism, hardworking, responds better to encouragement than harsh feedback.",
        "difficulty": "intermediate",
        "objectives": ["Be specific and objective", "Balance positive and constructive", "Maintain relationship"],
        "tips": ["Start with positives", "Be specific about issues", "Offer solutions and support"],
    },
    {
        "id": "workplace-negotiation",
        "category": "workplace",
        "title": "Salary Negotiation",
        "description": "Practice advocating for yourself in compensation discussions.",
        "persona_name": "Casey",
        "persona_description": "Your manager during a performance review. They appreciate your work but have budget constraints.",
        "persona_personality": "Fair but firm, respects confidence and preparation, open to reasonable arguments.",
        "difficulty": "advanced",
        "objectives": ["Present your value clearly", "Handle pushback gracefully", "Negotiate win-win outcomes"],
        "tips": ["Know your worth with data", "Be confident but not aggressive", "Have alternatives ready"],
    },
    # Friendship Scenarios
    {
        "id": "friendship-new-friend",
        "category": "friendship",
        "title": "Making New Friends",
        "description": "Practice initiating and building new friendships as an adult.",
        "persona_name": "Riley",
        "persona_description": "Someone you met at a local hobby group who shares your interests. They seem friendly but you don't know them well yet.",
        "persona_personality": "Friendly, a bit reserved initially, opens up when they find common interests, values authenticity.",
        "difficulty": "beginner",
        "objectives": ["Find common interests", "Suggest future hangouts", "Build rapport naturally"],
        "tips": ["Be genuinely curious", "Share about yourself too", "Suggest low-pressure activities"],
    },
    {
        "id": "friendship-boundaries",
        "category": "friendship",
        "title": "Setting Boundaries",
        "description": "Learn to establish healthy boundaries with friends while maintaining the relationship.",
        "persona_name": "Jamie",
        "persona_description": "A close friend who has been asking too much of your time and energy lately. They mean well but don't realize the impact.",
        "persona_personality": "Well-meaning but unaware, might feel hurt initially, ultimately respects honest communication.",
        "difficulty": "intermediate",
        "objectives": ["Express needs clearly", "Maintain the friendship", "Be firm but kind"],
        "tips": ["Use 'I' statements", "Be specific about what you need", "Reaffirm the friendship"],
    },
    {
        "id": "friendship-support",
        "category": "friendship",
        "title": "Supporting a Friend in Crisis",
        "description": "Practice being there for a friend going through a difficult time.",
        "persona_name": "Avery",
        "persona_description": "A close friend who just lost their job and is feeling overwhelmed and anxious about the future.",
        "persona_personality": "Vulnerable, needs emotional support more than advice, appreciates presence and validation.",
        "difficulty": "intermediate",
        "objectives": ["Show empathy and support", "Listen actively", "Offer appropriate help"],
        "tips": ["Don't rush to fix", "Validate their feelings", "Ask what they need"],
    },
    # Family Scenarios (NEW)
    {
        "id": "family-parent-conversation",
        "category": "family",
        "title": "Talking to Parents About Life Choices",
        "description": "Practice discussing major life decisions with parents who may have different expectations.",
        "persona_name": "Mom/Dad",
        "persona_description": "Your parent who has strong opinions about your career, relationships, or life path. They care deeply but can be overbearing.",
        "persona_personality": "Loving but controlling, struggles to see you as an adult, means well but expresses it poorly, responds to patience and firmness.",
        "difficulty": "intermediate",
        "objectives": [
            "Assert your independence respectfully",
            "Acknowledge their concerns",
            "Maintain the relationship",
        ],
        "tips": [
            "Stay calm and don't get defensive",
            "Validate their feelings first",
            "Be clear about your boundaries",
        ],
    },
    {
        "id": "family-sibling-conflict",
        "category": "family",
        "title": "Resolving Sibling Rivalry",
        "description": "Navigate conflicts with siblings stemming from childhood dynamics or current disagreements.",
        "persona_name": "Chris",
        "persona_description": "Your sibling who you've had ongoing tension with. Old patterns keep repeating despite both being adults now.",
        "persona_personality": "Competitive, quick to bring up past grievances, defensive but ultimately wants a better relationship.",
        "difficulty": "advanced",
        "objectives": [
            "Break old patterns",
            "Address current issues without relitigating the past",
            "Build a healthier dynamic",
        ],
        "tips": [
            "Focus on present behavior, not childhood",
            "Acknowledge your part in conflicts",
            "Propose new ways of interacting",
        ],
    },
    {
        "id": "family-inlaw-dynamics",
        "category": "family",
        "title": "Navigating In-Law Relationships",
        "description": "Build positive relationships with in-laws while maintaining appropriate boundaries.",
        "persona_name": "Patricia",
        "persona_description": "Your mother-in-law who has strong opinions about how things should be done. She wants to be involved but sometimes oversteps.",
        "persona_personality": "Well-intentioned but intrusive, sensitive to feeling excluded, responds well to inclusion and clear boundaries.",
        "difficulty": "intermediate",
        "objectives": [
            "Set boundaries diplomatically",
            "Build genuine connection",
            "Protect your primary relationship",
        ],
        "tips": [
            "Include your partner in boundary-setting",
            "Find common ground to bond over",
            "Be consistent with limits",
        ],
    },
    {
        "id": "family-elderly-parent",
        "category": "family",
        "title": "Discussing Care for Aging Parents",
        "description": "Have sensitive conversations about care needs, independence, and future planning with elderly parents.",
        "persona_name": "Dad",
        "persona_description": "Your aging father who is struggling with some daily tasks but resistant to accepting help or discussing future care.",
        "persona_personality": "Proud, fears losing independence, can be stubborn, deeply appreciates respect and being included in decisions.",
        "difficulty": "advanced",
        "objectives": [
            "Express concerns with compassion",
            "Respect their autonomy",
            "Collaboratively plan for the future",
        ],
        "tips": [
            "Listen to their fears and concerns",
            "Offer choices rather than demands",
            "Involve them in decision-making",
        ],
    },
    # Networking Scenarios (NEW)
    {
        "id": "networking-conference",
        "category": "networking",
        "title": "Working a Conference",
        "description": "Maximize networking opportunities at industry conferences and professional events.",
        "persona_name": "Dr. Chen",
        "persona_description": "A keynote speaker and industry thought leader at a conference. They're surrounded by people wanting their attention.",
        "persona_personality": "Accomplished, time-conscious, appreciates intelligence and unique perspectives, tires of generic small talk.",
        "difficulty": "intermediate",
        "objectives": ["Make a memorable impression quickly", "Demonstrate value", "Secure a follow-up opportunity"],
        "tips": ["Research them beforehand", "Lead with insight, not flattery", "Have a clear ask ready"],
    },
    {
        "id": "networking-linkedin",
        "category": "networking",
        "title": "LinkedIn Connection Building",
        "description": "Practice reaching out to new connections and nurturing professional relationships online.",
        "persona_name": "Sarah",
        "persona_description": "A professional you'd like to connect with on LinkedIn. You have mutual connections but have never spoken.",
        "persona_personality": "Selective about connections, values authenticity, suspicious of generic messages, appreciates specific value propositions.",
        "difficulty": "beginner",
        "objectives": [
            "Craft a compelling connection request",
            "Start a meaningful conversation",
            "Build toward a real relationship",
        ],
        "tips": ["Personalize every message", "Mention specific shared interests", "Offer before asking"],
    },
    {
        "id": "networking-mentorship",
        "category": "networking",
        "title": "Asking for Mentorship",
        "description": "Approach potential mentors and establish valuable mentoring relationships.",
        "persona_name": "James",
        "persona_description": "A successful professional whose career path you admire. They're busy but have mentioned being open to mentoring.",
        "persona_personality": "Generous with knowledge, values initiative and preparation, dislikes vague requests, appreciates follow-through.",
        "difficulty": "intermediate",
        "objectives": [
            "Make a specific, compelling ask",
            "Demonstrate your commitment",
            "Establish clear expectations",
        ],
        "tips": [
            "Be specific about what you want to learn",
            "Show you've done your homework",
            "Propose a concrete structure",
        ],
    },
    {
        "id": "networking-informational",
        "category": "networking",
        "title": "Informational Interview",
        "description": "Conduct informational interviews to learn about careers and build professional relationships.",
        "persona_name": "Michelle",
        "persona_description": "A professional in a role you're interested in who agreed to a 20-minute informational call.",
        "persona_personality": "Helpful but busy, appreciates well-prepared questions, values enthusiasm and genuine curiosity.",
        "difficulty": "beginner",
        "objectives": ["Ask insightful questions", "Learn actionable information", "Leave a positive impression"],
        "tips": ["Prepare specific questions", "Respect their time strictly", "Send a thoughtful thank-you"],
    },
    # Conflict Resolution Scenarios (NEW)
    {
        "id": "conflict-difficult-coworker",
        "category": "conflict",
        "title": "Addressing a Difficult Coworker",
        "description": "Handle ongoing issues with a challenging colleague professionally and effectively.",
        "persona_name": "Derek",
        "persona_description": "A coworker who consistently takes credit for others' work and undermines teammates. HR is aware but hasn't acted.",
        "persona_personality": "Defensive when confronted, skilled at deflection, responds to direct evidence and clear consequences.",
        "difficulty": "advanced",
        "objectives": ["Address specific behaviors", "Document the conversation", "Establish consequences"],
        "tips": ["Stick to facts and specific instances", "Don't attack character", "Have a clear outcome in mind"],
    },
    {
        "id": "conflict-neighbor-dispute",
        "category": "conflict",
        "title": "Neighbor Dispute Resolution",
        "description": "Resolve conflicts with neighbors over noise, boundaries, or shared spaces.",
        "persona_name": "Mark",
        "persona_description": "Your neighbor whose late-night parties have been disrupting your sleep. Previous hints haven't worked.",
        "persona_personality": "Initially defensive, unaware of impact, reasonable when approached respectfully, values being a good neighbor.",
        "difficulty": "intermediate",
        "objectives": ["Communicate impact clearly", "Find a workable compromise", "Maintain neighborly relations"],
        "tips": ["Choose the right time to talk", "Focus on impact, not judgment", "Propose specific solutions"],
    },
    {
        "id": "conflict-service-complaint",
        "category": "conflict",
        "title": "Escalating a Service Complaint",
        "description": "Effectively advocate for yourself when service providers fail to meet expectations.",
        "persona_name": "Customer Service Rep",
        "persona_description": "A customer service representative for a company that has repeatedly failed to resolve your issue.",
        "persona_personality": "Following scripts, limited authority, responds to calm persistence, more helpful when treated with respect.",
        "difficulty": "beginner",
        "objectives": [
            "Clearly state the problem and desired resolution",
            "Escalate appropriately",
            "Get results without burning bridges",
        ],
        "tips": ["Document everything", "Stay calm but firm", "Ask for supervisors when needed"],
    },
    {
        "id": "conflict-friend-betrayal",
        "category": "conflict",
        "title": "Confronting a Friend's Betrayal",
        "description": "Address serious breaches of trust with someone you care about.",
        "persona_name": "Nicole",
        "persona_description": "A close friend who shared something you told them in confidence, causing real damage to your reputation.",
        "persona_personality": "Remorseful but defensive, makes excuses initially, capable of genuine accountability when given space.",
        "difficulty": "advanced",
        "objectives": [
            "Express hurt without attacking",
            "Understand their perspective",
            "Decide the future of the friendship",
        ],
        "tips": ["Use 'I' statements", "Allow silence for processing", "Be clear about what you need to move forward"],
    },
    # NEW AI-Enhanced Scenarios
    {
        "id": "dating-long-distance",
        "category": "dating",
        "title": "Long Distance Relationship Talk",
        "description": "Navigate the challenges of starting or maintaining a long-distance relationship.",
        "persona_name": "Mia",
        "persona_description": "Someone you've been dating who just got a job offer in another city. You both need to decide what happens next.",
        "persona_personality": "Torn between excitement and worry, values honesty, needs reassurance but respects pragmatism.",
        "difficulty": "advanced",
        "objectives": [
            "Discuss logistics openly",
            "Express commitment level honestly",
            "Create a realistic plan together",
        ],
        "tips": [
            "Be honest about your feelings and fears",
            "Discuss specific plans, not just feelings",
            "Set check-in milestones",
        ],
    },
    {
        "id": "workplace-remote-leadership",
        "category": "workplace",
        "title": "Leading a Remote Team",
        "description": "Practice motivating and managing a distributed team through communication alone.",
        "persona_name": "Priya",
        "persona_description": "A remote team member who feels disconnected and undervalued. Their productivity has dropped and they're considering leaving.",
        "persona_personality": "Talented but disengaged, needs to feel seen and heard, responds to genuine interest in their growth.",
        "difficulty": "intermediate",
        "objectives": [
            "Rebuild engagement and trust",
            "Identify root causes of disengagement",
            "Create an actionable improvement plan",
        ],
        "tips": [
            "Ask about their experience, not just output",
            "Offer flexibility and autonomy",
            "Schedule regular 1-on-1 check-ins",
        ],
    },
    {
        "id": "friendship-toxic-friendship",
        "category": "friendship",
        "title": "Ending a Toxic Friendship",
        "description": "Learn to recognize and respectfully end a friendship that's become harmful to your wellbeing.",
        "persona_name": "Zoe",
        "persona_description": "A long-time friend who has become increasingly negative, manipulative, and draining. The friendship is one-sided.",
        "persona_personality": "Guilt-trips when confronted, plays victim, occasionally shows the old caring side that makes you doubt yourself.",
        "difficulty": "advanced",
        "objectives": ["Set a firm boundary", "Resist manipulation tactics", "End things with compassion but clarity"],
        "tips": [
            "Write down specific examples beforehand",
            "Don't JADE (Justify, Argue, Defend, Explain)",
            "Have an exit strategy for the conversation",
        ],
    },
    {
        "id": "family-blended-family",
        "category": "family",
        "title": "Navigating a Blended Family",
        "description": "Build relationships with stepchildren or step-parents while respecting everyone's boundaries.",
        "persona_name": "Liam",
        "persona_description": "Your partner's 14-year-old child who resents your presence and refuses to accept you as part of the family.",
        "persona_personality": "Defensive, loyal to absent parent, tests boundaries constantly, secretly wants stability.",
        "difficulty": "advanced",
        "objectives": [
            "Build trust gradually",
            "Respect their grief process",
            "Establish your role without replacing their parent",
        ],
        "tips": ["Don't force closeness", "Be consistent and reliable", "Let the biological parent lead on discipline"],
    },
    {
        "id": "networking-cold-outreach",
        "category": "networking",
        "title": "Cold Outreach to a CEO",
        "description": "Practice reaching out to high-level executives with a compelling value proposition.",
        "persona_name": "Robert",
        "persona_description": "CEO of a company you want to work with. They get hundreds of pitches weekly and have a 2-minute attention span.",
        "persona_personality": "Impatient, results-driven, respects boldness and data, dismisses fluff instantly.",
        "difficulty": "advanced",
        "objectives": [
            "Capture attention in 30 seconds",
            "Deliver clear value proposition",
            "Secure a follow-up meeting",
        ],
        "tips": [
            "Lead with their problem, not your solution",
            "Use specific numbers and results",
            "Make the ask crystal clear",
        ],
    },
    {
        "id": "conflict-cultural-misunderstanding",
        "category": "conflict",
        "title": "Resolving Cultural Misunderstandings",
        "description": "Navigate conflicts arising from cultural differences with empathy and curiosity.",
        "persona_name": "Akira",
        "persona_description": "A colleague from a different cultural background who was offended by something you said that you didn't realize was inappropriate.",
        "persona_personality": "Hurt but willing to educate, values genuine curiosity over performative apologies, appreciates humility.",
        "difficulty": "intermediate",
        "objectives": [
            "Apologize sincerely without defensiveness",
            "Learn about the cultural context",
            "Build a stronger cross-cultural relationship",
        ],
        "tips": [
            "Don't say 'I didn't mean it that way'",
            "Ask questions to understand, not to debate",
            "Thank them for educating you",
        ],
    },
    {
        "id": "dating-meeting-parents",
        "category": "dating",
        "title": "Meeting Your Partner's Parents",
        "description": "Make a great first impression when meeting your significant other's parents for the first time.",
        "persona_name": "Mr. & Mrs. Kim",
        "persona_description": "Your partner's parents who are protective and have high standards for who their child dates. First impressions matter deeply to them.",
        "persona_personality": "Warm but evaluating, traditional values, appreciate respect and ambition, subtle in their questioning.",
        "difficulty": "intermediate",
        "objectives": [
            "Show genuine respect and interest",
            "Handle tough questions gracefully",
            "Demonstrate your character naturally",
        ],
        "tips": [
            "Bring a thoughtful gift",
            "Ask about their stories and interests",
            "Show your partner affection appropriately",
        ],
    },
    {
        "id": "workplace-difficult-boss",
        "category": "workplace",
        "title": "Managing Up: Difficult Boss",
        "description": "Learn to work effectively with a demanding or micromanaging supervisor.",
        "persona_name": "Director Williams",
        "persona_description": "Your boss who micromanages every detail, sends emails at midnight, and rarely gives positive feedback.",
        "persona_personality": "Anxious about outcomes, distrustful due to past team failures, actually insecure beneath the tough exterior.",
        "difficulty": "advanced",
        "objectives": [
            "Build trust through proactive communication",
            "Set professional boundaries",
            "Influence their management style",
        ],
        "tips": [
            "Anticipate their questions and answer them proactively",
            "Send updates before they ask",
            "Frame boundaries as helping them succeed",
        ],
    },
    {
        "id": "conflict-online-harassment",
        "category": "conflict",
        "title": "Dealing with Online Harassment",
        "description": "Practice responding to cyberbullying, trolling, or online harassment effectively.",
        "persona_name": "Anonymous Troll",
        "persona_description": "Someone who has been leaving negative comments on your social media and sending hostile messages. It's affecting your mental health.",
        "persona_personality": "Provocative, seeks reactions, escalates when engaged, backs down when ignored or reported.",
        "difficulty": "intermediate",
        "objectives": [
            "Protect your mental health",
            "Respond strategically or not at all",
            "Use platform tools and legal options",
        ],
        "tips": ["Don't engage or feed the troll", "Screenshot and document everything", "Report, block, and move on"],
    },
]

# ============== ACHIEVEMENT BADGES ==============

ACHIEVEMENTS = {
    "first_conversation": {
        "id": "first_conversation",
        "name": "Ice Breaker",
        "description": "Complete your first practice conversation",
        "icon": "chatbubble",
        "xp_reward": 50,
        "condition": {"type": "conversations_completed", "count": 1},
    },
    "five_conversations": {
        "id": "five_conversations",
        "name": "Getting Started",
        "description": "Complete 5 practice conversations",
        "icon": "trending-up",
        "xp_reward": 100,
        "condition": {"type": "conversations_completed", "count": 5},
    },
    "ten_conversations": {
        "id": "ten_conversations",
        "name": "Conversation Pro",
        "description": "Complete 10 practice conversations",
        "icon": "star",
        "xp_reward": 200,
        "condition": {"type": "conversations_completed", "count": 10},
    },
    "twenty_five_conversations": {
        "id": "twenty_five_conversations",
        "name": "Social Butterfly",
        "description": "Complete 25 practice conversations",
        "icon": "ribbon",
        "xp_reward": 500,
        "condition": {"type": "conversations_completed", "count": 25},
    },
    "fifty_conversations": {
        "id": "fifty_conversations",
        "name": "Master Communicator",
        "description": "Complete 50 practice conversations",
        "icon": "trophy",
        "xp_reward": 1000,
        "condition": {"type": "conversations_completed", "count": 50},
    },
    "dating_explorer": {
        "id": "dating_explorer",
        "name": "Dating Explorer",
        "description": "Complete 3 dating scenarios",
        "icon": "heart",
        "xp_reward": 150,
        "condition": {"type": "category_completed", "category": "dating", "count": 3},
    },
    "workplace_warrior": {
        "id": "workplace_warrior",
        "name": "Workplace Warrior",
        "description": "Complete 3 workplace scenarios",
        "icon": "briefcase",
        "xp_reward": 150,
        "condition": {"type": "category_completed", "category": "workplace", "count": 3},
    },
    "friendship_builder": {
        "id": "friendship_builder",
        "name": "Friendship Builder",
        "description": "Complete 3 friendship scenarios",
        "icon": "people",
        "xp_reward": 150,
        "condition": {"type": "category_completed", "category": "friendship", "count": 3},
    },
    "family_harmonizer": {
        "id": "family_harmonizer",
        "name": "Family Harmonizer",
        "description": "Complete 3 family scenarios",
        "icon": "home",
        "xp_reward": 150,
        "condition": {"type": "category_completed", "category": "family", "count": 3},
    },
    "networking_ninja": {
        "id": "networking_ninja",
        "name": "Networking Ninja",
        "description": "Complete 3 networking scenarios",
        "icon": "globe",
        "xp_reward": 150,
        "condition": {"type": "category_completed", "category": "networking", "count": 3},
    },
    "conflict_resolver": {
        "id": "conflict_resolver",
        "name": "Conflict Resolver",
        "description": "Complete 3 conflict resolution scenarios",
        "icon": "shield-checkmark",
        "xp_reward": 150,
        "condition": {"type": "category_completed", "category": "conflict", "count": 3},
    },
    "three_day_streak": {
        "id": "three_day_streak",
        "name": "Committed",
        "description": "Practice for 3 days in a row",
        "icon": "flame",
        "xp_reward": 100,
        "condition": {"type": "streak", "days": 3},
    },
    "seven_day_streak": {
        "id": "seven_day_streak",
        "name": "Week Warrior",
        "description": "Practice for 7 days in a row",
        "icon": "flame",
        "xp_reward": 250,
        "condition": {"type": "streak", "days": 7},
    },
    "thirty_day_streak": {
        "id": "thirty_day_streak",
        "name": "Monthly Master",
        "description": "Practice for 30 days in a row",
        "icon": "medal",
        "xp_reward": 1000,
        "condition": {"type": "streak", "days": 30},
    },
    "high_scorer": {
        "id": "high_scorer",
        "name": "High Achiever",
        "description": "Score 90+ on a conversation",
        "icon": "rocket",
        "xp_reward": 200,
        "condition": {"type": "score", "min_score": 90},
    },
    "perfect_score": {
        "id": "perfect_score",
        "name": "Perfectionist",
        "description": "Score 100 on a conversation",
        "icon": "diamond",
        "xp_reward": 500,
        "condition": {"type": "score", "min_score": 100},
    },
    "empathy_master": {
        "id": "empathy_master",
        "name": "Empathy Master",
        "description": "Reach 80+ empathy skill level",
        "icon": "heart-circle",
        "xp_reward": 300,
        "condition": {"type": "skill_level", "skill": "empathy", "level": 80},
    },
    "all_rounder": {
        "id": "all_rounder",
        "name": "All-Rounder",
        "description": "Complete at least one scenario in each category",
        "icon": "apps",
        "xp_reward": 500,
        "condition": {"type": "all_categories"},
    },
}

# XP Levels
XP_LEVELS = [
    {"level": 1, "xp_required": 0, "title": "Beginner"},
    {"level": 2, "xp_required": 100, "title": "Novice"},
    {"level": 3, "xp_required": 300, "title": "Apprentice"},
    {"level": 4, "xp_required": 600, "title": "Intermediate"},
    {"level": 5, "xp_required": 1000, "title": "Skilled"},
    {"level": 6, "xp_required": 1500, "title": "Advanced"},
    {"level": 7, "xp_required": 2200, "title": "Expert"},
    {"level": 8, "xp_required": 3000, "title": "Master"},
    {"level": 9, "xp_required": 4000, "title": "Grandmaster"},
    {"level": 10, "xp_required": 5500, "title": "Legend"},
]

# ══════════ SUBSCRIPTION HELPERS ══════════


async def check_conversation_limit(user) -> bool:
    if getattr(user, "full_access", False):
        return True
    effective_plan = compute_effective_plan(
        {
            "subscription_plan": getattr(user, "subscription_plan", "free"),
            "subscription_status": getattr(user, "subscription_status", "active"),
            "subscription_end_date": getattr(user, "subscription_end_date", None),
            "subscription_permanent": getattr(user, "subscription_permanent", False),
            "payment_verified": getattr(user, "payment_verified", False),
            "pending_subscription_transition": getattr(user, "pending_subscription_transition", None),
            "is_admin": getattr(user, "is_admin", False),
            "full_access": getattr(user, "full_access", False),
        }
    )
    plan = await get_subscription_plan_from_gps(effective_plan, default_plan_id="free") or {}
    limit = plan.get("daily_conversation_limit", 3)
    if limit == -1:
        return True
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    progress = await db.progress.find_one({"user_id": user.user_id}, {"_id": 0})
    if progress:
        last_date = progress.get("last_conversation_date")
        if last_date == today:
            return progress.get("daily_conversations", 0) < limit
    return True


async def can_access_scenario(user, scenario_difficulty: str) -> bool:
    if getattr(user, "full_access", False):
        return True
    effective_plan = compute_effective_plan(
        {
            "subscription_plan": getattr(user, "subscription_plan", "free"),
            "subscription_status": getattr(user, "subscription_status", "active"),
            "subscription_end_date": getattr(user, "subscription_end_date", None),
            "subscription_permanent": getattr(user, "subscription_permanent", False),
            "payment_verified": getattr(user, "payment_verified", False),
            "pending_subscription_transition": getattr(user, "pending_subscription_transition", None),
            "is_admin": getattr(user, "is_admin", False),
            "full_access": getattr(user, "full_access", False),
        }
    )
    plan = await get_subscription_plan_from_gps(effective_plan, default_plan_id="free") or {}
    return scenario_difficulty in plan.get("scenario_access", ["beginner"])


async def get_or_create_progress(user_id: str) -> UserProgress:
    progress = await db.progress.find_one({"user_id": user_id})
    if progress:
        return UserProgress(**progress)
    new_progress = UserProgress(user_id=user_id)
    await db.progress.insert_one(new_progress.dict())
    return new_progress


async def get_ai_response(conversation, user_message: str, scenario: dict) -> str:
    msgs = [{"role": m.role, "content": m.content} for m in conversation.messages[-10:]]
    return await _get_ai_response_helper(conversation.id, msgs, user_message, scenario)


# ══════════ ROUTES ══════════


@router.post("/ai-feedback")
async def submit_ai_feedback(request_body: AIResponseFeedbackRequest):
    """Collect AI response feedback for quality monitoring."""
    payload = request_body.dict()
    payload["id"] = str(uuid.uuid4())
    payload["status"] = "open"
    payload["admin_notes"] = []
    payload["reply_logs"] = []
    payload["resolved_at"] = None
    payload["responded_at"] = None
    payload["created_at"] = datetime.now(timezone.utc)
    await db.ai_feedback.insert_one(payload)
    return {"status": "ok", "id": payload["id"]}


@router.get("/scenarios")
async def get_scenarios(category: Optional[str] = None, request: Request = None):
    """Get all scenarios or filter by category"""
    user = await get_current_user(request) if request else None
    user_plan = await get_subscription_plan_from_gps(user.subscription_plan if user else "free", default_plan_id="free") or {}

    scenarios_with_access = []
    for s in SCENARIOS:
        scenario_copy = s.copy()
        scenario_copy["locked"] = s["difficulty"] not in user_plan.get("scenario_access", ["beginner"])
        scenarios_with_access.append(scenario_copy)

    if category:
        filtered = [s for s in scenarios_with_access if s["category"] == category]
        return {"scenarios": filtered}
    return {"scenarios": scenarios_with_access}


@router.get("/scenarios/{scenario_id}")
async def get_scenario(scenario_id: str):
    for scenario in SCENARIOS:
        if scenario["id"] == scenario_id:
            return scenario
    raise HTTPException(status_code=404, detail="Scenario not found")



async def _send_usage_warning(user_id: str, new_count: int, limit: int, plan: str):
    """Send in-app + push notification when user hits 80% or 100% of daily conversation limit."""
    from utils.notification_helper import create_notification
    import math

    try:
        threshold_80 = math.ceil(limit * 0.8)
        remaining = limit - new_count

        if new_count == limit:
            # At 100% — limit reached
            await create_notification(
                user_id=user_id,
                title="Daily Limit Reached",
                message=f"You've used all {limit} conversations for today. Upgrade your plan to keep practicing!",
                notif_type="usage_limit_reached",
                data={"current_plan": plan, "used": new_count, "limit": limit, "upgrade_url": "/subscription/plans"},
            )
        elif new_count == threshold_80 and threshold_80 < limit:
            # At 80% — warning
            await create_notification(
                user_id=user_id,
                title=f"Only {remaining} Conversation{'s' if remaining != 1 else ''} Left Today",
                message=f"You've used {new_count} of {limit} conversations today. Upgrade for more daily practice!",
                notif_type="usage_warning",
                data={"current_plan": plan, "used": new_count, "limit": limit, "upgrade_url": "/subscription/plans"},
            )
    except Exception as e:
        logger.warning(f"Usage warning notification failed for {user_id}: {e}")



@router.post("/conversations/start")
async def start_conversation(request_body: StartConversationRequest, request: Request):
    """Start a new practice conversation"""
    user = await get_current_user(request)

    # Find scenario
    scenario = None
    for s in SCENARIOS:
        if s["id"] == request_body.scenario_id:
            scenario = s
            break

    if not scenario:
        raise HTTPException(status_code=404, detail="Scenario not found")

    # Check subscription access
    if user:
        if not await can_access_scenario(user, scenario["difficulty"]):
            raise HTTPException(
                status_code=403, detail=f"Upgrade your plan to access {scenario['difficulty']} scenarios"
            )

        if not await check_conversation_limit(user):
            raise HTTPException(status_code=403, detail="Daily conversation limit reached. Upgrade for more!")

    # Create conversation
    conversation = Conversation(
        user_id=request_body.user_id,
        scenario_id=request_body.scenario_id,
        scenario_title=scenario["title"],
        category=scenario["category"],
    )

    # Generate opening message
    try:
        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"start-{conversation.id}",
            system_message=f"""You are {scenario["persona_name"]}, {scenario["persona_description"]}
Your personality: {scenario["persona_personality"]}
Generate a natural opening line to start the conversation. Keep it brief (1-2 sentences).""",
        ).with_model("openai", "gpt-4o")

        opening = await chat.send_message(UserMessage(text="Start the conversation with a natural opening."))
        opening_message = Message(role="assistant", content=opening.strip())
        conversation.messages.append(opening_message)
    except Exception as e:
        logger.error(f"Error generating opening: {e}")
        opening_message = Message(role="assistant", content="Hi there! Nice to meet you.")
        conversation.messages.append(opening_message)

    await db.conversations.insert_one(conversation.dict())

    # Update progress
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    progress = await get_or_create_progress(request_body.user_id)

    update_query = {"$inc": {"total_conversations": 1}}
    if progress.last_conversation_date == today:
        update_query["$inc"]["daily_conversations"] = 1
    else:
        update_query["$set"] = {"daily_conversations": 1, "last_conversation_date": today}

    await db.progress.update_one({"user_id": request_body.user_id}, update_query)

    # ── Usage warning notifications ──
    if user:
        plan = await get_subscription_plan_from_gps(user.subscription_plan, default_plan_id="free") or {}
        limit = plan.get("daily_conversation_limit", 3)
        if limit > 0:  # skip for unlimited (-1)
            new_count = (progress.daily_conversations + 1) if progress.last_conversation_date == today else 1
            asyncio.ensure_future(_send_usage_warning(request_body.user_id, new_count, limit, user.subscription_plan))

    return {"conversation": conversation.dict(), "scenario": scenario}


@router.post("/conversations/message")
async def send_message(request_body: SendMessageRequest):
    """Send a message and get AI response with feedback"""
    conv_data = await db.conversations.find_one({"id": request_body.conversation_id})
    if not conv_data:
        raise HTTPException(status_code=404, detail="Conversation not found")

    conversation = Conversation(**conv_data)

    scenario = None
    for s in SCENARIOS:
        if s["id"] == conversation.scenario_id:
            scenario = s
            break

    if not scenario:
        raise HTTPException(status_code=404, detail="Scenario not found")

    context = "\n".join(
        [f"{'User' if m.role == 'user' else scenario['persona_name']}: {m.content}" for m in conversation.messages[-5:]]
    )

    feedback = await analyze_message_with_ai(request_body.message, context, scenario)

    user_msg = Message(role="user", content=request_body.message, feedback=feedback)
    conversation.messages.append(user_msg)

    ai_response = await get_ai_response(conversation, request_body.message, scenario)
    assistant_msg = Message(role="assistant", content=ai_response)
    conversation.messages.append(assistant_msg)

    conversation.updated_at = datetime.utcnow()
    await db.conversations.update_one(
        {"id": conversation.id},
        {"$set": {"messages": [m.dict() for m in conversation.messages], "updated_at": conversation.updated_at}},
    )

    return {"assistant_message": ai_response, "feedback": feedback, "message_count": len(conversation.messages)}


@router.post("/conversations/{conversation_id}/complete")
async def complete_conversation(conversation_id: str, user_id: str):
    """Complete a conversation and get summary"""
    conv_data = await db.conversations.find_one({"id": conversation_id})
    if not conv_data:
        raise HTTPException(status_code=404, detail="Conversation not found")

    conversation = Conversation(**conv_data)
    user_messages = [m for m in conversation.messages if m.role == "user" and m.feedback]

    if user_messages:
        avg_scores = {"empathy": 0, "clarity": 0, "confidence": 0, "active_listening": 0, "emotional_intelligence": 0}
        for msg in user_messages:
            if msg.feedback and "scores" in msg.feedback:
                for skill, score in msg.feedback["scores"].items():
                    if skill in avg_scores:
                        avg_scores[skill] += score

        num_messages = len(user_messages)
        for skill in avg_scores:
            avg_scores[skill] = round(avg_scores[skill] / num_messages)

        overall_score = round(sum(avg_scores.values()) / len(avg_scores))
        all_strengths = []
        all_suggestions = []
        for msg in user_messages:
            if msg.feedback:
                all_strengths.extend(msg.feedback.get("strengths", []))
                all_suggestions.extend(msg.feedback.get("suggestions", []))

        strengths = list(set(all_strengths))[:3]
        suggestions = list(set(all_suggestions))[:3]
    else:
        avg_scores = {
            "empathy": 70,
            "clarity": 70,
            "confidence": 70,
            "active_listening": 70,
            "emotional_intelligence": 70,
        }
        overall_score = 70
        strengths = ["Completed the conversation"]
        suggestions = ["Keep practicing for better results"]

    overall_feedback = {
        "scores": avg_scores,
        "overall_score": overall_score,
        "strengths": strengths,
        "areas_to_improve": suggestions,
        "message_count": len(conversation.messages),
    }

    await db.conversations.update_one(
        {"id": conversation_id},
        {"$set": {"status": "completed", "overall_feedback": overall_feedback, "updated_at": datetime.utcnow()}},
    )

    # Update user progress
    progress = await get_or_create_progress(user_id)
    skill_changes = {}
    for skill, score in avg_scores.items():
        if score >= 70:
            change = min(5, (score - 70) // 10 + 1)
        else:
            change = 0
        skill_changes[skill] = change

    new_skills = {}
    for skill, change in skill_changes.items():
        current = progress.skills.get(skill, 50)
        new_skills[skill] = min(100, current + change)

    category_key = f"category_progress.{conversation.category}"

    # Calculate XP earned
    base_xp = 25  # Base XP for completing a conversation
    score_bonus = overall_score // 10  # Bonus based on score
    xp_earned = base_xp + score_bonus

    # Update streak
    today = datetime.utcnow().strftime("%Y-%m-%d")
    yesterday = (datetime.utcnow() - timedelta(days=1)).strftime("%Y-%m-%d")

    streak_update = {}
    if progress.streak_last_date == today:
        # Already practiced today, no streak change
        pass
    elif progress.streak_last_date == yesterday:
        # Continuing streak
        streak_update["current_streak"] = progress.current_streak + 1
        if progress.current_streak + 1 > progress.longest_streak:
            streak_update["longest_streak"] = progress.current_streak + 1
    else:
        # Streak broken or first time
        streak_update["current_streak"] = 1
    streak_update["streak_last_date"] = today

    # Update highest score
    score_update = {}
    if overall_score > progress.highest_score:
        score_update["highest_score"] = overall_score

    # Check for new achievements
    new_achievements = []
    completed_count = progress.completed_conversations + 1
    category_count = progress.category_progress.get(conversation.category, 0) + 1
    new_streak = streak_update.get("current_streak", progress.current_streak)

    for ach_id, achievement in ACHIEVEMENTS.items():
        if ach_id in progress.achievements:
            continue

        condition = achievement["condition"]
        earned = False

        if condition["type"] == "conversations_completed":
            earned = completed_count >= condition["count"]
        elif condition["type"] == "category_completed":
            if condition["category"] == conversation.category:
                earned = category_count >= condition["count"]
        elif condition["type"] == "streak":
            earned = new_streak >= condition["days"]
        elif condition["type"] == "score":
            earned = overall_score >= condition["min_score"]
        elif condition["type"] == "skill_level":
            skill_val = new_skills.get(condition["skill"], 50)
            earned = skill_val >= condition["level"]
        elif condition["type"] == "all_categories":
            all_cats = ["dating", "workplace", "friendship", "family", "networking", "conflict"]
            cat_progress = progress.category_progress.copy()
            cat_progress[conversation.category] = category_count
            earned = all(cat_progress.get(c, 0) > 0 for c in all_cats)

        if earned:
            new_achievements.append(ach_id)
            xp_earned += achievement["xp_reward"]

    # Calculate new level
    new_xp = progress.xp + xp_earned
    new_level = 1
    for level_data in XP_LEVELS:
        if new_xp >= level_data["xp_required"]:
            new_level = level_data["level"]

    # Update progress
    update_data = {
        "$inc": {
            "completed_conversations": 1,
            category_key: 1,
            "total_messages_sent": len([m for m in conversation.messages if m.role == "user"]),
        },
        "$set": {
            "skills": new_skills,
            "xp": new_xp,
            "level": new_level,
            "updated_at": datetime.utcnow(),
            **streak_update,
            **score_update,
        },
    }

    if new_achievements:
        update_data["$push"] = {"achievements": {"$each": new_achievements}}

    await db.progress.update_one({"user_id": user_id}, update_data)

    return {
        "summary": overall_feedback,
        "skill_changes": skill_changes,
        "xp_earned": xp_earned,
        "new_achievements": [ACHIEVEMENTS[a] for a in new_achievements],
        "level": new_level,
        "streak": streak_update.get("current_streak", progress.current_streak),
    }


@router.get("/conversations/{user_id}")
async def get_user_conversations(user_id: str, status: Optional[str] = None):
    query = {"user_id": user_id}
    if status:
        query["status"] = status
    conversations = await db.conversations.find(query, {"_id": 0}).sort("updated_at", -1).to_list(100)
    return {"conversations": conversations}


@router.get("/conversation/{conversation_id}")
async def get_conversation(conversation_id: str):
    conv = await db.conversations.find_one({"id": conversation_id}, {"_id": 0})
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conv


@router.get("/progress/{user_id}")
async def get_progress(user_id: str):
    progress = await get_or_create_progress(user_id)
    return progress.dict()


@router.get("/progress/daily-goal/{user_id}")
async def get_daily_goal(user_id: str):
    """Get the user's daily session goal and today's completion count."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    doc = await db.daily_goals.find_one({"user_id": user_id}, {"_id": 0})
    goal = doc.get("target", 3) if doc else 3
    # Count today's activities
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    today_count = await db.usage_analytics.count_documents(
        {"user_id": user_id, "timestamp": {"$gte": today_start.isoformat()}}
    )
    today_count += await db.tool_usage.count_documents(
        {"user_id": user_id, "timestamp": {"$gte": today_start.isoformat()}}
    )
    # Also count conversations from today
    today_convos = await db.conversations.count_documents({"user_id": user_id, "created_at": {"$gte": today_start}})
    today_count += today_convos
    return {
        "target": goal,
        "today_count": today_count,
        "date": today,
        "completed": today_count >= goal,
    }


@router.post("/progress/daily-goal/{user_id}")
async def set_daily_goal(user_id: str, payload: dict):
    """Set the user's daily session goal."""
    target = max(1, min(20, int(payload.get("target", 3))))
    await db.daily_goals.update_one(
        {"user_id": user_id},
        {"$set": {"user_id": user_id, "target": target, "updated_at": datetime.now(timezone.utc).isoformat()}},
        upsert=True,
    )
    return {"success": True, "target": target}


@router.post("/ai-feature-feedback")
async def submit_ai_feature_feedback(payload: dict):
    """Store user feedback on AI feature responses, then check quality threshold."""
    from utils.email_service import send_email

    feature = payload.get("feature", "unknown")
    rating = payload.get("rating", "up")

    await db.ai_feedback.insert_one(
        {
            "user_id": payload.get("user_id", "anonymous"),
            "feature": feature,
            "rating": rating,
            "comment": payload.get("comment", ""),
            "response_preview": (payload.get("response", ""))[:200],
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
    )

    # Check quality threshold after negative feedback
    if rating == "down" or (isinstance(rating, (int, float)) and rating <= 0):
        await _check_and_alert_feature_quality(feature, send_email)

    return {"success": True}


async def _check_and_alert_feature_quality(feature: str, send_email_fn) -> None:
    """Check if a feature dropped below quality threshold and send alert if needed."""
    try:
        from datetime import timedelta

        # Load alert settings
        settings = await db.quality_alert_settings.find_one({}, {"_id": 0}) or {}
        if not settings.get("enabled", True):
            return

        threshold = settings.get("threshold", 70)
        alert_email = settings.get("alert_email", os.environ.get("ADMIN_EMAILS", "admin@realaicoach.app"))

        # Get all feedback for this feature
        all_fb = await db.ai_feedback.find(
            {"$or": [{"feature": feature}, {"feature_key": feature}]}, {"_id": 0, "rating": 1}
        ).to_list(1000)

        if len(all_fb) < 3:
            return  # Not enough data

        positive = sum(
            1
            for f in all_fb
            if (f.get("rating") == "up" if isinstance(f.get("rating"), str) else (f.get("rating", 0) or 0) > 0)
        )
        pct = round(positive / len(all_fb) * 100, 1)

        if pct >= threshold:
            return  # Above threshold, no alert needed

        # Check if we already alerted in the last 24 hours for this feature
        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        recent_alert = await db.quality_alerts.find_one(
            {"feature": feature, "created_at": {"$gte": cutoff.isoformat()}}
        )
        if recent_alert:
            return  # Already alerted recently

        # Send alert email
        feature_display = feature.replace("-", " ").title()
        from utils.email_service import render_email_header_panel

        header_html = render_email_header_panel(
            title="Feature Quality Alert",
            subtitle=f"The {feature_display} AI feature dropped below threshold and needs review.",
            variant="security",
            accent="#EF4444",
            meta_label="Current Rating",
            meta_value=f"{pct}% thumbs-up",
        )
        admin_console_url = f"{(os.environ.get('FRONTEND_BASE_URL') or '').rstrip('/')}/admin-console"
        email_html = f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
          <div style="border-radius:20px;overflow:hidden;margin-bottom:18px;">{header_html}</div>
          <div style="background: #f9fafb; padding: 24px; border: 1px solid #e5e7eb; border-radius: 0 0 8px 8px;">
            <p style="font-size: 16px; color: #111827;">
              The <strong>{feature_display}</strong> AI feature has dropped below your quality threshold.
            </p>
            <div style="background: white; border-radius: 8px; padding: 16px; border: 1px solid #e5e7eb; margin: 16px 0;">
              <table style="width: 100%; border-collapse: collapse;">
                <tr>
                  <td style="padding: 8px 0; color: #6b7280;">Feature</td>
                  <td style="padding: 8px 0; font-weight: 700; color: #111827;">{feature_display}</td>
                </tr>
                <tr>
                  <td style="padding: 8px 0; color: #6b7280;">Current Rating</td>
                  <td style="padding: 8px 0; font-weight: 700; color: #EF4444;">{pct}% thumbs-up</td>
                </tr>
                <tr>
                  <td style="padding: 8px 0; color: #6b7280;">Threshold</td>
                  <td style="padding: 8px 0; font-weight: 700; color: #111827;">{threshold}%</td>
                </tr>
                <tr>
                  <td style="padding: 8px 0; color: #6b7280;">Total Ratings</td>
                  <td style="padding: 8px 0; font-weight: 700; color: #111827;">{len(all_fb)}</td>
                </tr>
              </table>
            </div>
            <p style="color: #6b7280; font-size: 14px;">
              Review the Feature Quality Monitor in the Admin Console to see recent complaints and take action.
            </p>
            <a href="{admin_console_url}" 
               style="display: inline-block; background: #1D4ED8; color: white; padding: 12px 24px; border-radius: 8px; text-decoration: none; font-weight: 700;">
              Open Admin Console
            </a>
          </div>
        </div>
        """

        result = await send_email_fn(
            recipient_email=alert_email,
            subject=f"[RealAICoach Alert] {feature_display} quality dropped to {pct}%",
            content=email_html,
        )

        # Log the alert
        await db.quality_alerts.insert_one(
            {
                "feature": feature,
                "pct": pct,
                "total_ratings": len(all_fb),
                "threshold": threshold,
                "alert_email": alert_email,
                "email_result": result.get("success", False),
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        )

        logger.info(f"Feature quality alert sent for {feature}: {pct}% (threshold {threshold}%)")
    except Exception as e:
        logger.error(f"Failed to check/send quality alert: {e}")


@router.get("/progress-trends/{user_id}")
async def get_progress_trends(user_id: str, days: int = 30):
    """Return daily activity trends, top features, and score history for a user."""
    from datetime import timedelta

    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)

    # Daily activity from usage_analytics
    day_map: dict[str, int] = {}
    for i in range(days):
        day_map[(start + timedelta(days=i)).strftime("%Y-%m-%d")] = 0

    activities = await db.usage_analytics.find(
        {"user_id": user_id, "timestamp": {"$gte": start.isoformat()}}, {"_id": 0, "timestamp": 1, "feature_id": 1}
    ).to_list(5000)

    feature_count: dict[str, int] = {}
    for act in activities:
        ts = act.get("timestamp")
        if isinstance(ts, str):
            try:
                dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            except Exception:
                continue
        else:
            dt = ts if ts else None
        if dt:
            day_map[dt.strftime("%Y-%m-%d")] = day_map.get(dt.strftime("%Y-%m-%d"), 0) + 1
        fid = act.get("feature_id", "unknown")
        feature_count[fid] = feature_count.get(fid, 0) + 1

    # Also count from tool_usage
    tool_activities = await db.tool_usage.find({"user_id": user_id}, {"_id": 0, "timestamp": 1, "feature": 1}).to_list(
        5000
    )
    for act in tool_activities:
        ts = act.get("timestamp")
        if isinstance(ts, str):
            try:
                dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            except Exception:
                continue
        else:
            dt = ts if ts else None
        if dt and dt >= start:
            day_map[dt.strftime("%Y-%m-%d")] = day_map.get(dt.strftime("%Y-%m-%d"), 0) + 1
        feat = act.get("feature", "unknown")
        feature_count[feat] = feature_count.get(feat, 0) + 1

    daily_activity = [{"date": d, "count": c} for d, c in sorted(day_map.items())]
    top_features = sorted(feature_count.items(), key=lambda x: x[1], reverse=True)[:8]

    # Recent sessions
    convos = (
        await db.conversations.find(
            {"user_id": user_id},
            {"_id": 0, "scenario_title": 1, "category": 1, "status": 1, "created_at": 1, "overall_feedback": 1},
        )
        .sort("created_at", -1)
        .limit(10)
        .to_list(10)
    )

    for c in convos:
        if isinstance(c.get("created_at"), datetime):
            c["created_at"] = c["created_at"].isoformat()

    return {
        "daily_activity": daily_activity,
        "top_features": [{"feature": f, "count": c} for f, c in top_features],
        "recent_sessions": convos,
        "total_activity_days": sum(1 for c in daily_activity if c["count"] > 0),
        "period_days": days,
    }


@router.get("/daily-tip")
async def get_daily_tip():
    import random

    tips = [
        {
            "title": "Active Listening",
            "content": "Show you're listening by nodding, making eye contact, and paraphrasing what the other person said.",
            "category": "general",
        },
        {
            "title": "The Power of 'I' Statements",
            "content": "Instead of 'You always...' try 'I feel... when...' It reduces defensiveness and opens dialogue.",
            "category": "conflict",
        },
        {
            "title": "Ask Open-Ended Questions",
            "content": "Questions that start with 'What', 'How', or 'Tell me about' invite deeper conversations.",
            "category": "connection",
        },
        {
            "title": "Mirror Body Language",
            "content": "Subtly matching the other person's posture and gestures builds rapport and trust.",
            "category": "general",
        },
        {
            "title": "Pause Before Responding",
            "content": "Taking a brief pause shows thoughtfulness and prevents reactive responses.",
            "category": "emotional_intelligence",
        },
        {
            "title": "Validate Before Problem-Solving",
            "content": "Sometimes people need to feel heard before they want solutions. Try 'That sounds really tough' first.",
            "category": "empathy",
        },
        {
            "title": "Express Appreciation Specifically",
            "content": "Instead of 'Thanks', try 'I really appreciated how you helped me with X. It made a difference.'",
            "category": "gratitude",
        },
        {
            "title": "Comfortable Silence",
            "content": "Not every moment needs to be filled with words. Comfortable silence shows confidence and allows processing.",
            "category": "confidence",
        },
    ]
    return random.choice(tips)


# ============== GAMIFICATION ENDPOINTS ==============


@router.get("/achievements")
async def get_all_achievements():
    """Get all available achievements"""
    return {"achievements": list(ACHIEVEMENTS.values())}


@router.get("/achievements/{user_id}")
async def get_user_achievements(user_id: str):
    """Get user's earned achievements"""
    progress = await get_or_create_progress(user_id)
    earned = [ACHIEVEMENTS[a] for a in progress.achievements if a in ACHIEVEMENTS]
    unearned = [a for a in ACHIEVEMENTS.values() if a["id"] not in progress.achievements]
    return {"earned": earned, "unearned": unearned, "total_earned": len(earned), "total_available": len(ACHIEVEMENTS)}


@router.get("/leaderboard")
async def get_leaderboard(request: Request, limit: int = 10):
    """Get top users by XP"""
    user = await get_current_user(request)
    if not user:
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=401, content={"detail": "Authentication required"})
    # Aggregate leaderboard from progress collection
    pipeline = [
        {"$sort": {"xp": -1}},
        {"$limit": limit},
        {"$project": {"_id": 0, "user_id": 1, "xp": 1, "level": 1, "completed_conversations": 1, "current_streak": 1}},
    ]
    results = await db.progress.aggregate(pipeline).to_list(limit)

    # Get user names
    leaderboard = []
    for i, entry in enumerate(results):
        user = await db.users.find_one({"user_id": entry["user_id"]}, {"_id": 0, "name": 1, "email": 1})
        name = user.get("name", "Anonymous") if user else "Anonymous"
        leaderboard.append(
            {
                "rank": i + 1,
                "name": name,
                "xp": entry.get("xp", 0),
                "level": entry.get("level", 1),
                "conversations": entry.get("completed_conversations", 0),
                "streak": entry.get("current_streak", 0),
            }
        )

    return {"leaderboard": leaderboard}


@router.get("/xp-levels")
async def get_xp_levels():
    """Get all XP level thresholds"""
    return {"levels": XP_LEVELS}


@router.get("/user-stats/{user_id}")
async def get_user_stats(request: Request, user_id: str):
    """Get comprehensive user statistics for gamification"""
    user = await get_current_user(request)
    if not user:
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=401, content={"detail": "Authentication required"})
    progress = await get_or_create_progress(user_id)

    # Find user's rank
    rank_result = await db.progress.count_documents({"xp": {"$gt": progress.xp}})
    user_rank = rank_result + 1

    # Calculate XP to next level
    current_level_xp = 0
    next_level_xp = 0
    current_title = "Beginner"
    next_title = None

    for i, level_data in enumerate(XP_LEVELS):
        if level_data["level"] == progress.level:
            current_level_xp = level_data["xp_required"]
            current_title = level_data["title"]
            if i + 1 < len(XP_LEVELS):
                next_level_xp = XP_LEVELS[i + 1]["xp_required"]
                next_title = XP_LEVELS[i + 1]["title"]
            break

    xp_to_next = next_level_xp - progress.xp if next_level_xp > 0 else 0
    level_progress = (
        ((progress.xp - current_level_xp) / (next_level_xp - current_level_xp) * 100)
        if next_level_xp > current_level_xp
        else 100
    )

    return {
        "xp": progress.xp,
        "level": progress.level,
        "title": current_title,
        "next_title": next_title,
        "xp_to_next_level": xp_to_next,
        "level_progress_percent": round(level_progress, 1),
        "rank": user_rank,
        "current_streak": progress.current_streak,
        "longest_streak": progress.longest_streak,
        "highest_score": progress.highest_score,
        "total_conversations": progress.completed_conversations,
        "total_messages": progress.total_messages_sent,
        "achievements_earned": len(progress.achievements),
        "achievements_total": len(ACHIEVEMENTS),
    }


# ============== VOICE MESSAGE ENDPOINT ==============


@router.post("/conversations/voice-message")
async def send_voice_message(request: VoiceMessageRequest):
    """
    Process a voice message - transcribes audio and responds with text.
    For voice-to-voice, frontend will use TTS to speak the response.
    """
    # Get conversation
    conv_data = await db.conversations.find_one({"id": request.conversation_id})
    if not conv_data:
        raise HTTPException(status_code=404, detail="Conversation not found")

    conversation = Conversation(**conv_data)

    # Get scenario
    scenario = next((s for s in SCENARIOS if s["id"] == conversation.scenario_id), None)
    if not scenario:
        raise HTTPException(status_code=404, detail="Scenario not found")

    try:
        # Use OpenAI Whisper for transcription via LiteLLM
        import base64
        import tempfile

        # Decode base64 audio
        audio_data = base64.b64decode(request.audio_base64)

        # Save to temp file (suffix drives transcription format detection)
        fmt = "".join(ch for ch in str(request.audio_format or "webm").lower() if ch.isalnum()) or "webm"
        with tempfile.NamedTemporaryFile(suffix=f".{fmt}", delete=False) as f:
            f.write(audio_data)
            temp_path = f.name

        # Transcribe using OpenAI Whisper
        import litellm

        with open(temp_path, "rb") as audio_file:
            transcript_response = await litellm.atranscription(
                model="whisper-1", file=audio_file, api_key=EMERGENT_LLM_KEY, api_base="https://llm.emergentagi.com"
            )

        # Clean up temp file
        os.unlink(temp_path)

        transcribed_text = transcript_response.text

        # Now process the transcribed text as a regular message
        # Build conversation history
        history_messages = []
        for msg in conversation.messages[-10:]:
            if msg.role == "assistant":
                history_messages.append({"role": "assistant", "content": msg.content})
            elif msg.role == "user":
                history_messages.append({"role": "user", "content": msg.content})

        # Generate AI response
        system_prompt = f"""You are {scenario["persona_name"]}, {scenario["persona_description"]}
Your personality: {scenario["persona_personality"]}
Scenario context: {scenario["description"]}

Respond naturally as this character would. Keep responses conversational and appropriate length (2-4 sentences typically).
Help the user practice their communication skills through realistic interaction."""

        chat = LlmChat(api_key=EMERGENT_LLM_KEY, session_id=f"coaching-{uuid.uuid4()}", system_message=system_prompt)

        for msg in history_messages:
            if msg["role"] == "user":
                chat.add_message(UserMessage(content=msg["content"]))
            else:
                chat.history.append({"role": "assistant", "content": msg["content"]})

        chat.add_message(UserMessage(content=transcribed_text))
        ai_response = await chat.send_message(UserMessage(text=transcribed_text))

        # Generate feedback
        feedback_prompt = f"""Analyze this voice message response in a {scenario["category"]} scenario:
User said: "{transcribed_text}"

Rate these skills (0-100):
1. Empathy - Understanding and acknowledging feelings
2. Clarity - Clear and understandable communication  
3. Confidence - Assertive without being aggressive
4. Active Listening - Building on what was said
5. Emotional Intelligence - Reading and responding to emotions

Provide brief, encouraging feedback. Return JSON:
{{"scores": {{"empathy": X, "clarity": X, "confidence": X, "active_listening": X, "emotional_intelligence": X}},
"overall_impression": "brief overall assessment",
"strengths": ["strength1", "strength2"],
"suggestions": ["suggestion1"]}}"""

        feedback_chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"voice-feedback-{uuid.uuid4()}",
            system_message="You are a communication coach. Analyze responses and provide constructive feedback in JSON format only.",
        ).with_model("openai", "gpt-4o")

        feedback_response = await feedback_chat.send_message(UserMessage(text=feedback_prompt))

        try:
            feedback_text = feedback_response.strip()
            if feedback_text.startswith("```"):
                feedback_text = feedback_text.split("```")[1]
                if feedback_text.startswith("json"):
                    feedback_text = feedback_text[4:]
            feedback = json.loads(feedback_text)
        except Exception:
            feedback = {
                "scores": {
                    "empathy": 70,
                    "clarity": 70,
                    "confidence": 70,
                    "active_listening": 70,
                    "emotional_intelligence": 70,
                },
                "overall_impression": "Good effort! Keep practicing.",
                "strengths": ["Engaged with the conversation"],
                "suggestions": ["Continue developing your voice communication skills"],
            }

        # Save messages
        user_message = Message(
            role="user",
            content=transcribed_text,
            timestamp=datetime.utcnow().isoformat(),
            feedback=feedback,
            is_voice=True,
        )

        assistant_message = Message(role="assistant", content=ai_response, timestamp=datetime.utcnow().isoformat())

        await db.conversations.update_one(
            {"id": request.conversation_id},
            {
                "$push": {"messages": {"$each": [user_message.dict(), assistant_message.dict()]}},
                "$set": {"updated_at": datetime.utcnow()},
            },
        )

        return {
            "transcribed_text": transcribed_text,
            "assistant_message": ai_response,
            "feedback": feedback,
            "is_voice_response": True,
        }

    except Exception as e:
        logger.error(f"Voice message processing failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to process voice message: {str(e)}")


# ============== ADVANCED AI COACHING (moved to routes/advanced_coaching.py) ==============
# ============== SCHOOL AI COACHING (moved to routes/school.py) ==============
