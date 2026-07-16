"""Advanced AI Coaching routes: Real-time coaching, tone analysis, learning paths, role reversal, crisis simulator, multi-person, communication profile, conversation replay."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List, Dict
from datetime import datetime, timezone
import uuid
import os
import json
from emergentintegrations.llm.chat import LlmChat, UserMessage
from .db import db, EMERGENT_LLM_KEY, logger

router = APIRouter()


class RealTimeCoachingRequest(BaseModel):
    user_id: str
    message_draft: str
    scenario_context: Optional[str] = None
    conversation_history: Optional[List[Dict[str, str]]] = []


class ToneAnalysisRequest(BaseModel):
    user_id: str
    audio_base64: Optional[str] = None
    text: Optional[str] = None
    video_base64: Optional[str] = None


class LearningPathRequest(BaseModel):
    user_id: str
    focus_areas: Optional[List[str]] = []
    available_time_minutes: int = 15


class RoleReversalRequest(BaseModel):
    user_id: str
    scenario_id: str
    user_plays_difficult_person: bool = True


class CrisisSimulationRequest(BaseModel):
    user_id: str
    crisis_type: str
    time_limit_seconds: int = 60


class MultiPersonRequest(BaseModel):
    user_id: str
    scenario_type: str
    num_participants: int = 3


class CommunicationProfileRequest(BaseModel):
    user_id: str


class ConversationReplayRequest(BaseModel):
    user_id: str
    conversation_id: str
    alternative_response: Optional[str] = None


# Crisis scenarios for simulator
CRISIS_SCENARIOS = {
    "job_loss": {
        "title": "Breaking News of Job Loss",
        "description": "You need to tell your partner/family that you lost your job",
        "persona": "Your partner who depends on your income and has anxiety about finances",
        "pressure_points": ["They may panic", "They may blame you", "They need reassurance"],
        "time_limit": 90,
    },
    "breakup": {
        "title": "Ending a Relationship",
        "description": "You need to end a long-term relationship with someone who still loves you",
        "persona": "Your partner of 3 years who is blindsided by this conversation",
        "pressure_points": ["They will be emotional", "They may try to change your mind", "They deserve honesty"],
        "time_limit": 120,
    },
    "confrontation": {
        "title": "Confronting Dishonesty",
        "description": "You discovered someone close to you has been lying and need to confront them",
        "persona": "Your close friend who has been lying about something important",
        "pressure_points": ["They may deny it", "They may get defensive", "You need proof"],
        "time_limit": 90,
    },
    "bad_news": {
        "title": "Delivering Bad News",
        "description": "You need to tell someone about a death or serious illness in the family",
        "persona": "Your sibling who is far away and doesn't know yet",
        "pressure_points": ["They will be shocked", "They may need time to process", "Be prepared for any reaction"],
        "time_limit": 60,
    },
    "betrayal": {
        "title": "Addressing Betrayal",
        "description": "Someone betrayed your trust and you need to address it directly",
        "persona": "Your business partner who made decisions without consulting you",
        "pressure_points": ["Stay calm despite anger", "Focus on facts", "Decide on consequences"],
        "time_limit": 120,
    },
}

# Multi-person conversation scenarios
MULTI_PERSON_SCENARIOS = {
    "team_meeting": {
        "title": "Team Meeting Dynamics",
        "description": "Navigate a team meeting with different personalities and agendas",
        "participants": [
            {"name": "Sarah", "role": "Project Manager", "personality": "Organized, time-conscious, wants decisions"},
            {"name": "Mike", "role": "Developer", "personality": "Technical, detail-oriented, sometimes dismissive"},
            {"name": "Lisa", "role": "Designer", "personality": "Creative, passionate, can be defensive about work"},
        ],
    },
    "family_dinner": {
        "title": "Family Dinner Conversation",
        "description": "Navigate a family dinner with complex dynamics",
        "participants": [
            {"name": "Mom", "role": "Mother", "personality": "Caring but opinionated, wants everyone to get along"},
            {"name": "Dad", "role": "Father", "personality": "Traditional, avoids conflict, makes jokes to deflect"},
            {
                "name": "Sibling",
                "role": "Brother/Sister",
                "personality": "Competitive with you, seeks parental approval",
            },
        ],
    },
    "friend_group": {
        "title": "Friend Group Planning",
        "description": "Coordinate plans with friends who have different preferences",
        "participants": [
            {
                "name": "Alex",
                "role": "The Planner",
                "personality": "Organized, wants consensus, gets frustrated easily",
            },
            {
                "name": "Jordan",
                "role": "The Spontaneous One",
                "personality": "Goes with the flow, indecisive, agreeable",
            },
            {"name": "Casey", "role": "The Opinionated One", "personality": "Strong preferences, vocal, can dominate"},
        ],
    },
}

# Role-reversal scenarios
SCENARIOS = [
    {
        "id": "angry_customer",
        "title": "Angry Customer",
        "description": "Handle an upset customer who received a defective product",
        "persona_name": "Karen",
        "persona_description": "An irate customer",
        "persona_personality": "Demanding, loud, wants immediate resolution",
    },
    {
        "id": "difficult_coworker",
        "title": "Difficult Coworker",
        "description": "Address a coworker who takes credit for your work",
        "persona_name": "Dave",
        "persona_description": "A competitive colleague",
        "persona_personality": "Passive-aggressive, deflects blame, takes credit",
    },
    {
        "id": "tough_manager",
        "title": "Tough Manager",
        "description": "Request a raise from a notoriously difficult manager",
        "persona_name": "Ms. Stone",
        "persona_description": "A demanding manager",
        "persona_personality": "Results-driven, dismissive of personal issues, values data",
    },
    {
        "id": "critical_parent",
        "title": "Critical Parent",
        "description": "Tell a critical parent about a major life decision",
        "persona_name": "Parent",
        "persona_description": "A parent with strong opinions",
        "persona_personality": "Judgmental, worries excessively, compares to others",
    },
]


async def get_or_create_progress(user_id: str) -> dict:
    """Get or create a user's coaching progress record."""
    progress = await db.coaching_progress.find_one({"user_id": user_id}, {"_id": 0})
    if not progress:
        progress = {
            "user_id": user_id,
            "skills": {
                "empathy": 50,
                "clarity": 50,
                "assertiveness": 50,
                "active_listening": 50,
                "conflict_resolution": 50,
                "emotional_intelligence": 50,
                "persuasion": 50,
            },
            "sessions_completed": 0,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.coaching_progress.insert_one({**progress})

    # Ensure skills is accessible as dict attribute
    class ProgressObj:
        def __init__(self, d):
            self.__dict__.update(d)
            self.skills = d.get("skills", {})

    return ProgressObj(progress)


@router.post("/coaching/real-time")
async def real_time_coaching(request: RealTimeCoachingRequest):
    """
    Analyze a message draft and provide real-time suggestions before sending.
    """
    try:
        context = request.scenario_context or "general conversation"
        history = (
            "\n".join([f"{m['role']}: {m['content']}" for m in request.conversation_history[-5:]])
            if request.conversation_history
            else "No prior context"
        )

        prompt = f"""As a communication coach, analyze this message draft and provide suggestions.

Context: {context}
Conversation history:
{history}

User's draft message: "{request.message_draft}"

Analyze and provide:
1. Tone assessment (formal/casual/aggressive/passive/assertive)
2. Emotional impact prediction (how recipient might feel)
3. 2-3 alternative phrasings that might be more effective
4. Potential issues or red flags
5. Overall recommendation (send as-is, modify, reconsider)

Return JSON:
{{
    "tone": "assertive",
    "emotional_impact": "may feel understood but also challenged",
    "alternatives": [
        "Alternative 1...",
        "Alternative 2..."
    ],
    "issues": ["Issue 1 if any"],
    "recommendation": "modify",
    "recommendation_reason": "brief explanation",
    "confidence_score": 75
}}"""

        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"coaching-{uuid.uuid4()}",
            system_message="You are an expert communication coach. Provide helpful, constructive feedback in JSON format.",
        ).with_model("openai", "gpt-4o")

        response = await chat.send_message(UserMessage(text=prompt))

        try:
            response_text = response.strip()
            if response_text.startswith("```"):
                response_text = response_text.split("```")[1]
                if response_text.startswith("json"):
                    response_text = response_text[4:]
            result = json.loads(response_text)
        except Exception:
            result = {
                "tone": "neutral",
                "emotional_impact": "Unable to fully analyze",
                "alternatives": [request.message_draft],
                "issues": [],
                "recommendation": "send",
                "recommendation_reason": "Analysis incomplete",
                "confidence_score": 50,
            }

        return result

    except Exception as e:
        logger.error(f"Real-time coaching failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/coaching/tone-analysis")
async def analyze_tone(request: ToneAnalysisRequest):
    """
    Analyze tone from text or audio input.
    """
    try:
        text_to_analyze = request.text

        # If audio provided, transcribe first
        if request.audio_base64 and not text_to_analyze:
            import base64
            import tempfile

            audio_data = base64.b64decode(request.audio_base64)
            with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as f:
                f.write(audio_data)
                temp_path = f.name

            import litellm

            with open(temp_path, "rb") as audio_file:
                transcript_response = await litellm.atranscription(
                    model="whisper-1", file=audio_file, api_key=EMERGENT_LLM_KEY, api_base="https://llm.emergentagi.com"
                )
            os.unlink(temp_path)
            text_to_analyze = transcript_response.text

        if not text_to_analyze:
            raise HTTPException(status_code=400, detail="No text or audio provided")

        prompt = f"""Analyze the tone and delivery of this message:

"{text_to_analyze}"

Provide detailed analysis:
1. Primary tone (confident/nervous/aggressive/passive/warm/cold)
2. Secondary tones detected
3. Confidence level (1-100)
4. Pace assessment (too fast/appropriate/too slow) - estimate from word patterns
5. Filler words detected
6. Power words used
7. Emotional undertone
8. Suggestions for improvement

Return JSON:
{{
    "primary_tone": "confident",
    "secondary_tones": ["warm", "assertive"],
    "confidence_level": 75,
    "pace": "appropriate",
    "filler_words": {{"um": 2, "like": 3}},
    "power_words": ["absolutely", "committed"],
    "emotional_undertone": "positive but slightly anxious",
    "transcript": "{text_to_analyze}",
    "suggestions": [
        "Reduce filler words",
        "Add more pauses for emphasis"
    ],
    "overall_score": 72
}}"""

        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"coaching-{uuid.uuid4()}",
            system_message="You are an expert speech and communication analyst.",
        )
        # Message added below
        response = await chat.send_message(UserMessage(text=prompt))

        try:
            response_text = response.strip()
            if response_text.startswith("```"):
                response_text = response_text.split("```")[1]
                if response_text.startswith("json"):
                    response_text = response_text[4:]
            result = json.loads(response_text)
        except Exception:
            result = {
                "primary_tone": "neutral",
                "confidence_level": 50,
                "transcript": text_to_analyze,
                "suggestions": ["Continue practicing"],
                "overall_score": 50,
            }

        return result

    except Exception as e:
        logger.error(f"Tone analysis failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/coaching/learning-path")
async def generate_learning_path(request: LearningPathRequest):
    """
    Generate a personalized learning path based on user's progress and goals.
    """
    try:
        progress = await get_or_create_progress(request.user_id)

        # Identify weak areas from skills
        weak_skills = sorted(progress.skills.items(), key=lambda x: x[1])[:3]
        focus_areas = request.focus_areas or [skill[0] for skill in weak_skills]

        # Get user's conversation history for pattern analysis
        await (
            db.conversations.find({"user_id": request.user_id, "status": "completed"})
            .sort("created_at", -1)
            .limit(10)
            .to_list(10)
        )

        prompt = f"""Create a personalized 7-day communication learning path.

User Profile:
- Current skills: {json.dumps(progress.skills)}
- Completed conversations: {progress.completed_conversations}
- Focus areas requested: {focus_areas}
- Available time per day: {request.available_time_minutes} minutes
- Current level: {progress.level}

Create a structured learning plan with daily exercises.

Return JSON:
{{
    "path_title": "Your Personal Communication Journey",
    "focus_summary": "Brief description of focus",
    "total_days": 7,
    "daily_time_minutes": {request.available_time_minutes},
    "days": [
        {{
            "day": 1,
            "theme": "Day theme",
            "objectives": ["Objective 1", "Objective 2"],
            "exercises": [
                {{
                    "title": "Exercise name",
                    "type": "practice|reflection|scenario",
                    "duration_minutes": 5,
                    "description": "What to do",
                    "scenario_id": "optional-scenario-id"
                }}
            ],
            "tip_of_day": "Quick tip"
        }}
    ],
    "expected_improvements": ["Improvement 1", "Improvement 2"],
    "milestone_rewards": [
        {{"day": 3, "achievement": "Midway Master", "xp": 100}},
        {{"day": 7, "achievement": "Path Complete", "xp": 250}}
    ]
}}"""

        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"coaching-{uuid.uuid4()}",
            system_message="You are a personal communication coach creating customized learning paths.",
        )
        # Message added below
        response = await chat.send_message(UserMessage(text=prompt))

        try:
            response_text = response.strip()
            if response_text.startswith("```"):
                response_text = response_text.split("```")[1]
                if response_text.startswith("json"):
                    response_text = response_text[4:]
            learning_path = json.loads(response_text)
        except Exception:
            # Default learning path
            learning_path = {
                "path_title": "Communication Foundations",
                "focus_summary": "Building core communication skills",
                "total_days": 7,
                "daily_time_minutes": request.available_time_minutes,
                "days": [
                    {
                        "day": i + 1,
                        "theme": f"Day {i + 1}: Practice",
                        "objectives": ["Practice active listening", "Express clearly"],
                        "exercises": [
                            {
                                "title": "Daily Practice",
                                "type": "scenario",
                                "duration_minutes": 10,
                                "description": "Complete one scenario",
                            }
                        ],
                        "tip_of_day": "Focus on understanding before responding",
                    }
                    for i in range(7)
                ],
                "expected_improvements": ["Better clarity", "Improved empathy"],
                "milestone_rewards": [{"day": 7, "achievement": "Path Complete", "xp": 250}],
            }

        # Save to database
        await db.learning_paths.update_one(
            {"user_id": request.user_id},
            {"$set": {"path": learning_path, "started_at": datetime.utcnow(), "current_day": 1}},
            upsert=True,
        )

        return learning_path

    except Exception as e:
        logger.error(f"Learning path generation failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/coaching/learning-path/{user_id}")
async def get_learning_path(user_id: str):
    """Get user's current learning path"""
    path_data = await db.learning_paths.find_one({"user_id": user_id}, {"_id": 0})
    if not path_data:
        return {"has_path": False, "message": "No learning path found. Generate one first."}
    return {"has_path": True, **path_data}


@router.post("/coaching/role-reversal/start")
async def start_role_reversal(request: RoleReversalRequest):
    """
    Start a role reversal session where user plays the difficult person.
    """
    try:
        scenario = next((s for s in SCENARIOS if s["id"] == request.scenario_id), None)
        if not scenario:
            raise HTTPException(status_code=404, detail="Scenario not found")

        # Create reversed scenario
        reversal_id = f"reversal_{str(uuid.uuid4())[:8]}"

        system_prompt = f"""You are now playing the role of a person practicing their communication skills.
        
Original scenario: {scenario["title"]}
Original context: {scenario["description"]}

YOU are now the one who needs to respond well. The user is playing {scenario["persona_name"]} - {scenario["persona_description"]}.
Their personality: {scenario["persona_personality"]}

Your job is to DEMONSTRATE good communication by:
1. Showing empathy and understanding
2. Using clear, respectful language
3. Finding common ground
4. De-escalating tension

After each exchange, briefly explain (in parentheses) WHY your response was effective.

Start by introducing yourself and the situation you want to discuss."""

        chat = LlmChat(api_key=EMERGENT_LLM_KEY, session_id=f"coaching-{uuid.uuid4()}", system_message=system_prompt)

        initial_response = await chat.send_message(
            UserMessage(text="Start the scenario. Introduce yourself and the situation.")
        )

        # Store session
        session_data = {
            "id": reversal_id,
            "user_id": request.user_id,
            "scenario_id": request.scenario_id,
            "original_scenario": scenario,
            "messages": [{"role": "assistant", "content": initial_response}],
            "mode": "role_reversal",
            "created_at": datetime.utcnow(),
        }
        await db.role_reversals.insert_one(session_data)

        return {
            "session_id": reversal_id,
            "scenario_title": f"Role Reversal: {scenario['title']}",
            "your_role": f"You are {scenario['persona_name']} - {scenario['persona_description']}",
            "ai_role": "The AI will demonstrate ideal responses",
            "opening_message": initial_response,
            "instructions": "Respond as the difficult person would. Watch how the AI handles your responses.",
        }

    except Exception as e:
        logger.error(f"Role reversal start failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/coaching/role-reversal/{session_id}/message")
async def role_reversal_message(session_id: str, user_id: str, message: str):
    """Send a message in a role reversal session"""
    session = await db.role_reversals.find_one({"id": session_id})
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    scenario = session["original_scenario"]

    system_prompt = f"""You are demonstrating ideal communication skills in response to a difficult person.
    
Context: {scenario["description"]}
The user is playing {scenario["persona_name"]} who is: {scenario["persona_personality"]}

Respond with empathy, clarity, and effectiveness. After your response, add (in parentheses) a brief explanation of the technique you used."""

    chat = LlmChat(api_key=EMERGENT_LLM_KEY, session_id=f"coaching-{uuid.uuid4()}", system_message=system_prompt)

    # Add history
    for msg in session["messages"][-6:]:
        if msg["role"] == "user":
            chat.add_message(UserMessage(content=msg["content"]))
        else:
            chat.history.append({"role": "assistant", "content": msg["content"]})

    # Message added below
    response = await chat.send_message(UserMessage(text=message))

    # Update session
    await db.role_reversals.update_one(
        {"id": session_id},
        {
            "$push": {
                "messages": {
                    "$each": [{"role": "user", "content": message}, {"role": "assistant", "content": response}]
                }
            }
        },
    )

    return {"response": response, "technique_demonstrated": True}


@router.post("/coaching/crisis-simulator/start")
async def start_crisis_simulation(request: CrisisSimulationRequest):
    """Start a time-pressured crisis communication simulation"""
    if request.crisis_type not in CRISIS_SCENARIOS:
        raise HTTPException(status_code=400, detail=f"Unknown crisis type. Available: {list(CRISIS_SCENARIOS.keys())}")

    crisis = CRISIS_SCENARIOS[request.crisis_type]
    sim_id = f"crisis_{str(uuid.uuid4())[:8]}"

    system_prompt = f"""You are simulating a crisis conversation. Be realistic and challenging.

Scenario: {crisis["title"]}
Context: {crisis["description"]}
Your role: {crisis["persona"]}

Important behaviors:
- React emotionally and realistically
- Apply pressure points: {crisis["pressure_points"]}
- Don't make it easy, but be fair
- If the user handles it well, gradually become more receptive

The user has {request.time_limit_seconds} seconds to resolve this. Keep responses concise but impactful."""

    chat = LlmChat(api_key=EMERGENT_LLM_KEY, session_id=f"crisis-{sim_id}", system_message=system_prompt).with_model(
        "openai", "gpt-4o"
    )

    opening = await chat.send_message(
        UserMessage(text="Start the conversation. Set the scene and confront the user with the crisis situation.")
    )

    session_data = {
        "id": sim_id,
        "user_id": request.user_id,
        "crisis_type": request.crisis_type,
        "crisis_data": crisis,
        "time_limit": request.time_limit_seconds,
        "messages": [{"role": "assistant", "content": opening, "timestamp": datetime.utcnow().isoformat()}],
        "started_at": datetime.utcnow(),
        "status": "active",
    }
    await db.crisis_simulations.insert_one(session_data)

    return {
        "simulation_id": sim_id,
        "crisis_title": crisis["title"],
        "context": crisis["description"],
        "time_limit_seconds": request.time_limit_seconds,
        "opening_message": opening,
        "pressure_points": crisis["pressure_points"],
        "started_at": datetime.utcnow().isoformat(),
    }


@router.get("/coaching/crisis-simulator/scenarios")
async def get_crisis_scenarios():
    """Get all available crisis scenarios"""
    return {"scenarios": CRISIS_SCENARIOS}


@router.post("/coaching/multi-person/start")
async def start_multi_person_conversation(request: MultiPersonRequest):
    """Start a multi-person conversation simulation"""
    if request.scenario_type not in MULTI_PERSON_SCENARIOS:
        raise HTTPException(
            status_code=400, detail=f"Unknown scenario. Available: {list(MULTI_PERSON_SCENARIOS.keys())}"
        )

    scenario = MULTI_PERSON_SCENARIOS[request.scenario_type]
    conv_id = f"multi_{str(uuid.uuid4())[:8]}"

    participants_desc = "\n".join(
        [f"- {p['name']} ({p['role']}): {p['personality']}" for p in scenario["participants"]]
    )

    system_prompt = f"""You are simulating a multi-person conversation. You play ALL the other participants.

Scenario: {scenario["title"]}
Context: {scenario["description"]}

Participants you're playing:
{participants_desc}

Rules:
1. Each response should include reactions from 1-3 participants
2. Format: [Name]: Their message
3. Show realistic group dynamics and interruptions
4. Different participants should have different reactions
5. Create opportunities for the user to practice managing group dynamics

Start the conversation with the participants discussing something, then one of them addresses the user."""

    chat = LlmChat(api_key=EMERGENT_LLM_KEY, session_id=f"multi-{conv_id}", system_message=system_prompt).with_model(
        "openai", "gpt-4o"
    )

    opening = await chat.send_message(
        UserMessage(
            text="Begin the multi-person conversation. Have the participants start talking, then one of them addresses the user."
        )
    )

    session_data = {
        "id": conv_id,
        "user_id": request.user_id,
        "scenario_type": request.scenario_type,
        "scenario_data": scenario,
        "participants": scenario["participants"],
        "messages": [{"role": "assistant", "content": opening}],
        "created_at": datetime.utcnow(),
    }
    await db.multi_person_conversations.insert_one(session_data)

    return {
        "conversation_id": conv_id,
        "scenario_title": scenario["title"],
        "description": scenario["description"],
        "participants": scenario["participants"],
        "opening_message": opening,
    }


@router.get("/coaching/multi-person/scenarios")
async def get_multi_person_scenarios():
    """Get all available multi-person scenarios"""
    return {"scenarios": MULTI_PERSON_SCENARIOS}


@router.post("/coaching/communication-profile")
async def generate_communication_profile(request: CommunicationProfileRequest):
    """Generate a comprehensive communication style profile for a user"""
    try:
        progress = await get_or_create_progress(request.user_id)

        # Get conversation history
        conversations = (
            await db.conversations.find({"user_id": request.user_id, "status": "completed"})
            .sort("created_at", -1)
            .limit(20)
            .to_list(20)
        )

        # Analyze patterns
        all_messages = []
        all_feedback = []
        category_performance = {}

        for conv in conversations:
            cat = conv.get("category", "unknown")
            if cat not in category_performance:
                category_performance[cat] = {"scores": [], "count": 0}

            if conv.get("overall_feedback"):
                category_performance[cat]["scores"].append(conv["overall_feedback"].get("overall_score", 0))
                category_performance[cat]["count"] += 1

            for msg in conv.get("messages", []):
                if msg.get("role") == "user":
                    all_messages.append(msg.get("content", ""))
                    if msg.get("feedback"):
                        all_feedback.append(msg["feedback"])

        # Create profile prompt
        sample_messages = all_messages[:10] if all_messages else ["No messages yet"]

        prompt = f"""Analyze this user's communication patterns and create a detailed profile.

User Statistics:
- Total completed conversations: {progress.completed_conversations}
- Current skill levels: {json.dumps(progress.skills)}
- Category performance: {json.dumps({k: {"avg_score": sum(v["scores"]) / len(v["scores"]) if v["scores"] else 0, "count": v["count"]} for k, v in category_performance.items()})}

Sample of user's messages:
{chr(10).join(sample_messages[:10])}

Create a comprehensive communication profile:

Return JSON:
{{
    "communication_style": {{
        "primary_style": "assertive/passive/aggressive/passive-aggressive/assertive-empathetic",
        "secondary_style": "optional secondary style",
        "style_description": "2-3 sentence description of their style"
    }},
    "strengths": [
        {{"skill": "skill name", "evidence": "why this is a strength", "score": 85}}
    ],
    "growth_areas": [
        {{"skill": "skill name", "evidence": "why this needs work", "recommendation": "how to improve"}}
    ],
    "personality_traits": {{
        "openness": 75,
        "conscientiousness": 80,
        "extraversion": 60,
        "agreeableness": 85,
        "emotional_stability": 70
    }},
    "communication_dna": {{
        "directness": 70,
        "warmth": 80,
        "formality": 50,
        "assertiveness": 65,
        "empathy": 85,
        "clarity": 75
    }},
    "best_suited_for": ["type of conversations they excel at"],
    "challenging_for": ["type of conversations that challenge them"],
    "famous_communicator_match": {{
        "name": "Famous person with similar style",
        "reason": "Why they match"
    }},
    "personalized_tips": [
        "Specific tip 1",
        "Specific tip 2",
        "Specific tip 3"
    ]
}}"""

        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"coaching-{uuid.uuid4()}",
            system_message="You are an expert communication psychologist creating detailed profiles.",
        )
        # Message added below
        response = await chat.send_message(UserMessage(text=prompt))

        try:
            response_text = response.strip()
            if response_text.startswith("```"):
                response_text = response_text.split("```")[1]
                if response_text.startswith("json"):
                    response_text = response_text[4:]
            profile = json.loads(response_text)
        except Exception:
            profile = {
                "communication_style": {
                    "primary_style": "developing",
                    "style_description": "Your communication style is still being analyzed. Complete more conversations for a detailed profile.",
                },
                "strengths": [],
                "growth_areas": [],
                "personalized_tips": ["Complete more conversations to unlock your full profile"],
            }

        # Add stats
        profile["stats"] = {
            "conversations_analyzed": len(conversations),
            "messages_analyzed": len(all_messages),
            "current_skills": progress.skills,
            "level": progress.level,
            "xp": progress.xp,
        }

        # Save profile
        await db.communication_profiles.update_one(
            {"user_id": request.user_id}, {"$set": {"profile": profile, "updated_at": datetime.utcnow()}}, upsert=True
        )

        return profile

    except Exception as e:
        logger.error(f"Profile generation failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/coaching/communication-profile/{user_id}")
async def get_communication_profile(user_id: str):
    """Get user's saved communication profile"""
    profile_data = await db.communication_profiles.find_one({"user_id": user_id}, {"_id": 0})
    if not profile_data:
        return {"has_profile": False, "message": "No profile found. Generate one first."}
    return {"has_profile": True, **profile_data}


@router.post("/coaching/conversation-replay")
async def replay_conversation(request: ConversationReplayRequest):
    """Analyze a past conversation and provide detailed feedback with what-if analysis"""
    try:
        conv = await db.conversations.find_one({"id": request.conversation_id})
        if not conv:
            raise HTTPException(status_code=404, detail="Conversation not found")

        # Build conversation transcript
        transcript = []
        for msg in conv.get("messages", []):
            role = "You" if msg["role"] == "user" else conv.get("scenario_title", "AI")
            transcript.append(f"{role}: {msg['content']}")

        transcript_text = "\n".join(transcript)

        # If alternative response provided, analyze that too
        what_if_analysis = None
        if request.alternative_response:
            what_if_prompt = f"""Original conversation:
{transcript_text}

The user wants to know: What if they had said this instead at some point:
"{request.alternative_response}"

Analyze how this would have changed the conversation outcome.

Return JSON:
{{
    "original_outcome": "Brief description of how original went",
    "alternative_outcome": "How it would have gone with the alternative",
    "impact_score": 75,
    "would_improve": true,
    "explanation": "Detailed explanation of the difference"
}}"""

            what_if_chat = LlmChat(
                api_key=EMERGENT_LLM_KEY,
                session_id=f"coaching-{uuid.uuid4()}",
                system_message="You are a conversation analyst.",
            )
            # Message added below
            what_if_response = await what_if_chat.send_message(UserMessage(text=what_if_prompt))

            try:
                what_if_text = what_if_response.strip()
                if what_if_text.startswith("```"):
                    what_if_text = what_if_text.split("```")[1]
                    if what_if_text.startswith("json"):
                        what_if_text = what_if_text[4:]
                what_if_analysis = json.loads(what_if_text)
            except Exception:
                what_if_analysis = {"explanation": "Could not analyze alternative"}

        # Main analysis
        analysis_prompt = f"""Analyze this completed conversation in detail:

Scenario: {conv.get("scenario_title", "Unknown")}
Category: {conv.get("category", "Unknown")}

Transcript:
{transcript_text}

Provide a detailed replay analysis:

Return JSON:
{{
    "overall_assessment": "2-3 sentence summary",
    "key_moments": [
        {{
            "moment": "Quote or description",
            "type": "turning_point|missed_opportunity|excellent_response|problematic",
            "analysis": "Why this was significant",
            "better_alternative": "What could have been said (if applicable)"
        }}
    ],
    "emotional_arc": {{
        "start": "emotional state at beginning",
        "middle": "how it evolved",
        "end": "final emotional state"
    }},
    "skills_demonstrated": [
        {{"skill": "skill name", "rating": 80, "evidence": "specific example"}}
    ],
    "skills_to_practice": [
        {{"skill": "skill name", "why": "explanation", "exercise": "suggested practice"}}
    ],
    "conversation_score": 75,
    "replayability_value": "high/medium/low - whether reviewing again would help"
}}"""

        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"coaching-{uuid.uuid4()}",
            system_message="You are an expert conversation analyst providing detailed feedback.",
        )
        chat.add_message(UserMessage(content=analysis_prompt))
        response = await chat.send_message(UserMessage(text="Analyze this conversation and return the JSON analysis."))

        try:
            response_text = response.strip()
            if response_text.startswith("```"):
                response_text = response_text.split("```")[1]
                if response_text.startswith("json"):
                    response_text = response_text[4:]
            analysis = json.loads(response_text)
        except Exception:
            analysis = {
                "overall_assessment": "Analysis could not be completed",
                "conversation_score": conv.get("overall_feedback", {}).get("overall_score", 0),
            }

        if what_if_analysis:
            analysis["what_if_analysis"] = what_if_analysis

        analysis["conversation_id"] = request.conversation_id
        analysis["transcript"] = transcript

        return analysis

    except Exception as e:
        logger.error(f"Conversation replay failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
