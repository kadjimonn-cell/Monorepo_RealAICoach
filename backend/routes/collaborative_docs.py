"""Collaborative Document Editing System.

Real-time co-editing for resumes and job descriptions with
cursor presence, version history, and conflict-free merging.
AI-powered writing assistant for content improvements.
"""

from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect
from datetime import datetime, timezone
from typing import Dict
import asyncio
import uuid
import json
import logging

from emergentintegrations.llm.chat import LlmChat, UserMessage
from .db import db, require_auth, EMERGENT_LLM_KEY
from utils.ws_heartbeat import MAX_UNANSWERED_PINGS, receive_text_with_heartbeat

router = APIRouter(prefix="/collab-docs")
logger = logging.getLogger("routes.collab_docs")

# In-memory editing sessions: doc_id -> {participants: {user_id: {ws, cursor, name}}}
_doc_sessions: Dict[str, Dict] = {}


@router.get("/")
async def list_documents(request: Request):
    """List collaborative documents accessible to the user."""
    user = await require_auth(request)
    docs = (
        await db.collab_documents.find(
            {"$or": [{"owner_id": user.user_id}, {"collaborators": user.user_id}, {"is_public": True}]},
            {"_id": 0, "content": 0},
        )
        .sort("updated_at", -1)
        .to_list(50)
    )
    return {"documents": docs}


@router.post("/")
async def create_document(request: Request):
    """Create a new collaborative document."""
    user = await require_auth(request)
    body = await request.json()
    now = datetime.now(timezone.utc).isoformat()

    doc = {
        "doc_id": f"doc_{uuid.uuid4().hex[:12]}",
        "title": body.get("title", "Untitled Document"),
        "doc_type": body.get("doc_type", "general"),
        "content": body.get("content", ""),
        "owner_id": user.user_id,
        "owner_name": user.name,
        "collaborators": body.get("collaborators", []),
        "is_public": body.get("is_public", False),
        "version": 1,
        "created_at": now,
        "updated_at": now,
    }
    await db.collab_documents.insert_one(doc)
    doc.pop("_id", None)

    # Save initial version
    await db.doc_versions.insert_one(
        {
            "version_id": f"ver_{uuid.uuid4().hex[:10]}",
            "doc_id": doc["doc_id"],
            "version": 1,
            "content": doc["content"],
            "title": doc["title"],
            "edited_by": user.user_id,
            "editor_name": user.name,
            "created_at": now,
        }
    )

    return {"success": True, "document": doc}


@router.get("/{doc_id}")
async def get_document(doc_id: str, request: Request):
    """Get a collaborative document by ID."""
    user = await require_auth(request)
    doc = await db.collab_documents.find_one({"doc_id": doc_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    # Check access
    if (
        not doc.get("is_public")
        and user.user_id != doc["owner_id"]
        and user.user_id not in doc.get("collaborators", [])
    ):
        if not getattr(user, "is_admin", False):
            raise HTTPException(status_code=403, detail="Access denied")

    # Get active editors
    active_editors = []
    if doc_id in _doc_sessions:
        for uid, info in _doc_sessions[doc_id].get("participants", {}).items():
            active_editors.append({"user_id": uid, "name": info.get("name", ""), "cursor": info.get("cursor")})

    return {**doc, "active_editors": active_editors}


@router.put("/{doc_id}")
async def update_document(doc_id: str, request: Request):
    """Update document content (creates new version)."""
    user = await require_auth(request)
    body = await request.json()
    now = datetime.now(timezone.utc).isoformat()

    doc = await db.collab_documents.find_one({"doc_id": doc_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    new_version = doc.get("version", 0) + 1
    update = {
        "content": body.get("content", doc.get("content", "")),
        "title": body.get("title", doc.get("title", "")),
        "version": new_version,
        "updated_at": now,
        "last_editor": user.user_id,
        "last_editor_name": user.name,
    }
    await db.collab_documents.update_one({"doc_id": doc_id}, {"$set": update})

    # Save version history
    await db.doc_versions.insert_one(
        {
            "version_id": f"ver_{uuid.uuid4().hex[:10]}",
            "doc_id": doc_id,
            "version": new_version,
            "content": update["content"],
            "title": update["title"],
            "edited_by": user.user_id,
            "editor_name": user.name,
            "created_at": now,
        }
    )

    # Broadcast update to connected editors
    if doc_id in _doc_sessions:
        msg = json.dumps(
            {
                "type": "doc_update",
                "content": update["content"],
                "title": update["title"],
                "version": new_version,
                "edited_by": user.user_id,
                "editor_name": user.name,
            }
        )
        for uid, info in list(_doc_sessions[doc_id].get("participants", {}).items()):
            if uid != user.user_id:
                try:
                    await info["ws"].send_text(msg)
                except Exception:
                    pass

    return {"success": True, "version": new_version}


@router.get("/{doc_id}/versions")
async def get_versions(doc_id: str, request: Request):
    """Get version history for a document."""
    await require_auth(request)
    versions = await db.doc_versions.find({"doc_id": doc_id}, {"_id": 0}).sort("version", -1).to_list(50)
    return {"versions": versions}


@router.get("/{doc_id}/versions/{version_id}")
async def get_version(doc_id: str, version_id: str, request: Request):
    """Get a specific version of a document."""
    await require_auth(request)
    version = await db.doc_versions.find_one({"doc_id": doc_id, "version_id": version_id}, {"_id": 0})
    if not version:
        raise HTTPException(status_code=404, detail="Version not found")
    return version


@router.post("/{doc_id}/collaborators")
async def add_collaborator(doc_id: str, request: Request):
    """Add a collaborator to a document."""
    user = await require_auth(request)
    body = await request.json()
    collaborator_id = body.get("user_id", "")

    doc = await db.collab_documents.find_one({"doc_id": doc_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    if doc["owner_id"] != user.user_id and not getattr(user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Only owner can add collaborators")

    collaborators = doc.get("collaborators", [])
    if collaborator_id not in collaborators:
        collaborators.append(collaborator_id)
        await db.collab_documents.update_one({"doc_id": doc_id}, {"$set": {"collaborators": collaborators}})

    return {"success": True, "collaborators": collaborators}


@router.delete("/{doc_id}")
async def delete_document(doc_id: str, request: Request):
    """Delete a collaborative document."""
    user = await require_auth(request)
    doc = await db.collab_documents.find_one({"doc_id": doc_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    if doc["owner_id"] != user.user_id and not getattr(user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Only owner can delete")

    await db.collab_documents.delete_one({"doc_id": doc_id})
    await db.doc_versions.delete_many({"doc_id": doc_id})
    return {"success": True}


AI_ACTIONS = {
    "improve": {
        "system": "You are an expert writing coach. Improve the given text for clarity, professionalism, and impact. Maintain the same meaning but enhance tone, word choice, and structure. Return ONLY the improved text, no explanations.",
        "prompt_prefix": "Improve the following text:\n\n",
    },
    "grammar": {
        "system": "You are a meticulous proofreader. Fix all grammar, spelling, and punctuation errors. Do not change the meaning or style. Return ONLY the corrected text, no explanations.",
        "prompt_prefix": "Fix grammar and spelling in:\n\n",
    },
    "summarize": {
        "system": "You are a concise summarizer. Distill the key points from the text into a clear, brief summary with bullet points. Return ONLY the summary.",
        "prompt_prefix": "Summarize the key points:\n\n",
    },
    "expand": {
        "system": "You are a professional content writer. Expand on the given text by adding relevant details, examples, and depth while keeping the same tone and purpose. Return ONLY the expanded text.",
        "prompt_prefix": "Expand and elaborate on:\n\n",
    },
    "generate_template": {
        "system": "You are a professional document template specialist. Generate a well-structured template based on the document type and any context provided. Use clear sections, placeholders in [brackets], and professional formatting. Return ONLY the template content.",
        "prompt_prefix": "Generate a professional template:\n\n",
    },
}


@router.post("/ai-assist")
async def ai_assist(request: Request):
    """AI-powered writing assistance for collaborative documents."""
    await require_auth(request)
    body = await request.json()

    action = body.get("action", "")
    content = body.get("content", "")
    doc_type = body.get("doc_type", "general")
    custom_instruction = body.get("custom_instruction", "")

    if action not in AI_ACTIONS:
        raise HTTPException(status_code=400, detail=f"Invalid action. Choose from: {list(AI_ACTIONS.keys())}")

    if action != "generate_template" and not content.strip():
        raise HTTPException(status_code=400, detail="Content is required for this action")

    if not EMERGENT_LLM_KEY:
        raise HTTPException(status_code=500, detail="AI service not configured")

    action_config = AI_ACTIONS[action]

    # Build the prompt
    if action == "generate_template":
        type_labels = {
            "resume": "Resume / CV",
            "job_description": "Job Description",
            "cover_letter": "Cover Letter",
            "general": "Professional Document",
        }
        prompt = f"{action_config['prompt_prefix']}Document type: {type_labels.get(doc_type, doc_type)}"
        if content.strip():
            prompt += f"\nContext/notes: {content}"
    else:
        prompt = f"{action_config['prompt_prefix']}{content}"

    if custom_instruction:
        prompt += f"\n\nAdditional instruction: {custom_instruction}"

    try:
        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"collab-doc-ai-{uuid.uuid4().hex[:8]}",
            system_message=action_config["system"],
        ).with_model("openai", "gpt-4o")

        response = await chat.send_message(UserMessage(text=prompt))
        result_text = response.text if hasattr(response, "text") else str(response)

        return {
            "success": True,
            "action": action,
            "result": result_text,
            "doc_type": doc_type,
        }
    except Exception as e:
        logger.error(f"AI assist error: {e}")
        raise HTTPException(status_code=500, detail="AI processing failed")


# WebSocket for real-time collaborative editing
async def collab_doc_ws(ws: WebSocket, doc_id: str, user_id: str):
    """WebSocket for real-time document collaboration."""
    await ws.accept()

    # Get user name
    user = await db.users.find_one({"user_id": user_id}, {"_id": 0, "name": 1})
    user_name = user.get("name", "Unknown") if user else "Unknown"

    if doc_id not in _doc_sessions:
        _doc_sessions[doc_id] = {"participants": {}}
    _doc_sessions[doc_id]["participants"][user_id] = {"ws": ws, "name": user_name, "cursor": None}

    # Notify peers
    join_msg = json.dumps({"type": "editor_joined", "user_id": user_id, "name": user_name})
    for uid, info in list(_doc_sessions[doc_id]["participants"].items()):
        if uid != user_id:
            try:
                await info["ws"].send_text(join_msg)
            except Exception:
                pass

    # Send current editors list to the new participant
    editors = [{"user_id": uid, "name": info["name"]} for uid, info in _doc_sessions[doc_id]["participants"].items()]
    await ws.send_text(json.dumps({"type": "editors_list", "editors": editors}))

    try:
        unanswered_pings = 0
        while True:
            raw, unanswered_pings = await receive_text_with_heartbeat(ws, unanswered_pings)
            if unanswered_pings >= MAX_UNANSWERED_PINGS:
                raise asyncio.TimeoutError("collab docs heartbeat timeout")
            if raw is None:
                continue

            data = json.loads(raw)
            msg_type = data.get("type", "")

            if msg_type == "cursor_move":
                # Update cursor position and broadcast
                if doc_id in _doc_sessions and user_id in _doc_sessions[doc_id]["participants"]:
                    _doc_sessions[doc_id]["participants"][user_id]["cursor"] = data.get("cursor")
                broadcast = json.dumps(
                    {
                        "type": "cursor_update",
                        "user_id": user_id,
                        "name": user_name,
                        "cursor": data.get("cursor"),
                    }
                )
                for uid, info in list(_doc_sessions[doc_id]["participants"].items()):
                    if uid != user_id:
                        try:
                            await info["ws"].send_text(broadcast)
                        except Exception:
                            pass

            elif msg_type == "content_change":
                # Broadcast content change to other editors
                broadcast = json.dumps(
                    {
                        "type": "content_change",
                        "user_id": user_id,
                        "name": user_name,
                        "content": data.get("content", ""),
                        "selection": data.get("selection"),
                    }
                )
                for uid, info in list(_doc_sessions[doc_id]["participants"].items()):
                    if uid != user_id:
                        try:
                            await info["ws"].send_text(broadcast)
                        except Exception:
                            pass

            elif msg_type == "title_change":
                broadcast = json.dumps(
                    {
                        "type": "title_change",
                        "user_id": user_id,
                        "title": data.get("title", ""),
                    }
                )
                for uid, info in list(_doc_sessions[doc_id]["participants"].items()):
                    if uid != user_id:
                        try:
                            await info["ws"].send_text(broadcast)
                        except Exception:
                            pass

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.warning(f"Collab doc WS error: {e}")
    finally:
        if doc_id in _doc_sessions and user_id in _doc_sessions[doc_id]["participants"]:
            del _doc_sessions[doc_id]["participants"][user_id]
            leave_msg = json.dumps({"type": "editor_left", "user_id": user_id, "name": user_name})
            for uid, info in list(_doc_sessions[doc_id].get("participants", {}).items()):
                try:
                    await info["ws"].send_text(leave_msg)
                except Exception:
                    pass
            if not _doc_sessions[doc_id]["participants"]:
                del _doc_sessions[doc_id]
