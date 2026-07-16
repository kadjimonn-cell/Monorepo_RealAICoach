from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from pydantic import BaseModel
from typing import Optional
import uuid
import os
import shutil
from emergentintegrations.llm.chat import LlmChat, UserMessage
from .db import db, EMERGENT_LLM_KEY, logger, has_basic_access, User

router = APIRouter()

# ── Models ──


class StartCallRequest(BaseModel):
    user_id: str
    contact_id: str
    mode: str = "voice"


class CallResponse(BaseModel):
    text: str
    audio_base64: Optional[str] = None  # For future server-side TTS
    status: str = "success"


# ── Mock Data ──
MOCK_CONTACTS = [
    {
        "id": "ai-assistant",
        "name": "AI Assistant",
        "avatar": "https://i.pravatar.cc/150?u=ai",
        "status": "online",
        "phone": "AI-800-HELP",
        "is_ai": True,
    },
    {
        "id": "c1",
        "name": "Sarah Connor",
        "avatar": "https://i.pravatar.cc/150?u=1",
        "status": "online",
        "phone": "+1 555 0101",
        "is_ai": False,
    },
    {
        "id": "c2",
        "name": "John Smith",
        "avatar": "https://i.pravatar.cc/150?u=2",
        "status": "offline",
        "phone": "+1 555 0102",
        "is_ai": False,
    },
]

# ── Routes ──


@router.get("/phone/contacts/{user_id}")
async def get_contacts(user_id: str):
    return {"contacts": MOCK_CONTACTS}


@router.post("/phone/call/start")
async def start_call(request: StartCallRequest):
    # Check premium
    user_doc = await db.users.find_one({"user_id": request.user_id}, {"_id": 0})
    user = User(**user_doc) if user_doc else None
    # Allow if premium/basic or privileged OR if it's the specific "AI Assistant" (freemium teaser)
    is_premium = has_basic_access(user)

    if request.contact_id != "ai-assistant" and not is_premium:
        raise HTTPException(status_code=403, detail="Premium required for this contact")

    session_id = str(uuid.uuid4())
    return {"session_id": session_id, "status": "connected"}


@router.post("/phone/chat")
async def phone_chat(
    user_id: str = Form(...),
    session_id: str = Form(...),
    text_input: Optional[str] = Form(None),
    audio_file: Optional[UploadFile] = File(None),
):
    """
    Handle voice interaction:
    1. If audio provided -> Transcribe (Whisper) -> Get AI Response
    2. If text provided -> Get AI Response
    """
    try:
        user_message = text_input

        # 1. Transcribe Audio if present (Using OpenAI Whisper via Emergent Key)
        if audio_file:
            # Save temp file
            temp_filename = f"temp_{uuid.uuid4()}.m4a"
            with open(temp_filename, "wb") as buffer:
                shutil.copyfileobj(audio_file.file, buffer)

            try:
                # Use standard OpenAI client with Emergent Key for Whisper
                # We construct the client manually as emergentintegrations might not have a helper for Audio yet
                from openai import AsyncOpenAI

                client = AsyncOpenAI(api_key=EMERGENT_LLM_KEY, base_url="https://llm.emergentagent.com/v1")

                with open(temp_filename, "rb") as audio:
                    transcription = await client.audio.transcriptions.create(model="whisper-1", file=audio)
                user_message = transcription.text
            except Exception as e:
                logger.error(f"Whisper Error: {e}")
                # Fallback if whisper fails or user didn't speak clearly
                # If we received audio but failed to transcribe, we assume silence or error
                if not user_message:
                    user_message = "Hello?"
            finally:
                if os.path.exists(temp_filename):
                    os.remove(temp_filename)

        if not user_message:
            return CallResponse(text="I didn't catch that.")

        # 2. Get AI Response (Brain)
        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"phone-{session_id}",
            system_message="""You are a helpful AI Assistant on a phone call. 
            Keep your responses concise (1-2 sentences) and conversational. 
            Do not use markdown or emojis, as this will be spoken via Text-to-Speech.""",
        ).with_model("openai", "gpt-4o")

        response = await chat.send_message(UserMessage(text=user_message))
        ai_text = (response.text if hasattr(response, "text") else str(response)).strip()

        return CallResponse(text=ai_text)

    except Exception as e:
        logger.error(f"Phone chat error: {e}")
        return CallResponse(text="I'm having trouble connecting. Please try again.")
