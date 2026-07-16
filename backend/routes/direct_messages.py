"""Direct Messaging — Real-time P2P messaging between employers and candidates."""

from fastapi import APIRouter, HTTPException, Request
import re
from pydantic import BaseModel
from datetime import datetime, timezone
from typing import Optional
import uuid

from .db import db, get_current_user, logger

router = APIRouter(prefix="/messages")


def _gen_id(prefix: str = "msg") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


class NewConversation(BaseModel):
    recipient_id: str
    message: str
    subject: Optional[str] = None


class SendMessage(BaseModel):
    message: str


class MarkRead(BaseModel):
    message_ids: list = []


# ── Conversations ──


@router.post("/conversations")
async def start_conversation(payload: NewConversation, request: Request):
    """Start a new conversation or send to an existing one."""
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    if payload.recipient_id == user.user_id:
        raise HTTPException(status_code=400, detail="Cannot message yourself")

    # Check recipient exists
    recipient = await db.users.find_one(
        {"user_id": payload.recipient_id}, {"_id": 0, "user_id": 1, "name": 1, "email": 1, "avatar_url": 1}
    )
    if not recipient:
        raise HTTPException(status_code=404, detail="Recipient not found")

    # Check if conversation already exists between these two users
    existing = await db.direct_conversations.find_one(
        {
            "participants": {"$all": [user.user_id, payload.recipient_id]},
        },
        {"_id": 0, "conversation_id": 1},
    )

    now_iso = datetime.now(timezone.utc).isoformat()
    msg_id = _gen_id("msg")

    message_doc = {
        "message_id": msg_id,
        "sender_id": user.user_id,
        "sender_name": getattr(user, "name", ""),
        "content": payload.message,
        "read": False,
        "created_at": now_iso,
    }

    if existing:
        conv_id = existing["conversation_id"]
        await db.direct_conversations.update_one(
            {"conversation_id": conv_id},
            {
                "$set": {
                    "last_message": payload.message[:100],
                    "last_message_at": now_iso,
                    "last_sender_id": user.user_id,
                    "updated_at": now_iso,
                },
                "$inc": {f"unread.{payload.recipient_id}": 1},
            },
        )
        await db.direct_messages.insert_one({**message_doc, "conversation_id": conv_id})
    else:
        conv_id = _gen_id("conv")
        sender_info = {
            "user_id": user.user_id,
            "name": getattr(user, "name", ""),
            "email": getattr(user, "email", ""),
            "avatar_url": getattr(user, "avatar_url", None),
        }
        recipient_info = {
            "user_id": recipient["user_id"],
            "name": recipient.get("name", ""),
            "email": recipient.get("email", ""),
            "avatar_url": recipient.get("avatar_url"),
        }
        conv_doc = {
            "conversation_id": conv_id,
            "participants": [user.user_id, payload.recipient_id],
            "participant_info": {user.user_id: sender_info, payload.recipient_id: recipient_info},
            "subject": payload.subject,
            "last_message": payload.message[:100],
            "last_message_at": now_iso,
            "last_sender_id": user.user_id,
            "unread": {user.user_id: 0, payload.recipient_id: 1},
            "created_at": now_iso,
            "updated_at": now_iso,
        }
        await db.direct_conversations.insert_one(conv_doc)
        conv_doc.pop("_id", None)
        await db.direct_messages.insert_one({**message_doc, "conversation_id": conv_id})

    # Real-time WebSocket notification
    try:
        from utils.ws_manager import ws_manager

        await ws_manager.send_to_user(
            payload.recipient_id,
            {
                "type": "new_message",
                "conversation_id": conv_id,
                "sender_id": user.user_id,
                "sender_name": getattr(user, "name", ""),
                "message": payload.message[:100],
                "timestamp": now_iso,
            },
        )
    except Exception as e:
        logger.warning(f"WS push failed: {e}")

    # In-app notification
    try:
        from routes.notification_engine import emit_notification

        await emit_notification(
            user_id=payload.recipient_id,
            notif_type="new_direct_message",
            title=f"New message from {getattr(user, 'name', 'Someone')}",
            body=payload.message[:80],
            action_url="/messages",
            metadata={"conversation_id": conv_id, "sender_id": user.user_id},
        )
    except Exception as e:
        logger.warning(f"Message notification failed: {e}")

    # Email notification
    try:
        from utils.email_service import is_email_configured
        from utils.email_service import render_email_logo

        if is_email_configured() and recipient.get("email"):
            logo_html = render_email_logo(variant="compact")
            f"""
            <div style="font-family:-apple-system,sans-serif;max-width:560px;margin:0 auto;background:#0F1117;color:#E5E7EB;border-radius:16px;overflow:hidden;">
              <div style="background:linear-gradient(135deg,#3B82F6,#6366F1);padding:24px;text-align:center;">
                {logo_html}
                <div style="font-size:20px;font-weight:800;color:#fff;">New Message</div>
              </div>
              <div style="padding:20px;">
                <p style="color:#D1D5DB;font-size:14px;margin:0 0 10px;">Hi {recipient.get("name", "there")},</p>
                <p style="color:#D1D5DB;font-size:14px;margin:0 0 16px;"><strong>{getattr(user, "name", "Someone")}</strong> sent you a message:</p>
                <div style="background:#1F2937;border-radius:10px;padding:14px;margin:0 0 16px;">
                  <p style="color:#E5E7EB;font-size:14px;margin:0;">{payload.message[:200]}{"..." if len(payload.message) > 200 else ""}</p>
                </div>
                <p style="color:#6B7280;font-size:12px;text-align:center;">Log in to RealAICoach to reply</p>
              </div>
            </div>"""
            from utils.email_service import send_catalog_template
            await send_catalog_template(
                recipient_email=recipient["email"],
                template_key="direct_message_notification",
                recipient_name=recipient.get("name", ""),
                sender_name=getattr(user, 'name', 'Someone'),
                message_preview=payload.message[:200],
            )
    except Exception as e:
        logger.warning(f"Message email failed: {e}")

    return {
        "success": True,
        "conversation_id": conv_id,
        "message_id": msg_id,
        "is_new_conversation": not existing,
    }


@router.get("/conversations")
async def get_conversations(request: Request, page: int = 1, limit: int = 30):
    """Get all conversations for the current user (inbox)."""
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    total = await db.direct_conversations.count_documents({"participants": user.user_id})
    convos = (
        await db.direct_conversations.find({"participants": user.user_id}, {"_id": 0})
        .sort("last_message_at", -1)
        .skip((page - 1) * limit)
        .limit(limit)
        .to_list(limit)
    )

    # Add other participant info
    for c in convos:
        other_id = [p for p in c.get("participants", []) if p != user.user_id]
        if other_id:
            info = c.get("participant_info", {}).get(other_id[0], {})
            c["other_user"] = info
        c["my_unread"] = c.get("unread", {}).get(user.user_id, 0)

    total_unread = sum(c.get("my_unread", 0) for c in convos)

    return {
        "conversations": convos,
        "total": total,
        "total_unread": total_unread,
        "page": page,
    }


@router.get("/conversations/{conv_id}")
async def get_conversation_messages(conv_id: str, request: Request, page: int = 1, limit: int = 50):
    """Get messages in a conversation."""
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    conv = await db.direct_conversations.find_one(
        {"conversation_id": conv_id, "participants": user.user_id}, {"_id": 0}
    )
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    total = await db.direct_messages.count_documents({"conversation_id": conv_id})
    messages = (
        await db.direct_messages.find({"conversation_id": conv_id}, {"_id": 0})
        .sort("created_at", -1)
        .skip((page - 1) * limit)
        .limit(limit)
        .to_list(limit)
    )
    messages.reverse()

    # Mark messages as read
    await db.direct_messages.update_many(
        {"conversation_id": conv_id, "sender_id": {"$ne": user.user_id}, "read": False},
        {"$set": {"read": True, "read_at": datetime.now(timezone.utc).isoformat()}},
    )
    await db.direct_conversations.update_one({"conversation_id": conv_id}, {"$set": {f"unread.{user.user_id}": 0}})

    other_id = [p for p in conv.get("participants", []) if p != user.user_id]
    other_info = conv.get("participant_info", {}).get(other_id[0], {}) if other_id else {}

    return {
        "conversation": conv,
        "messages": messages,
        "total": total,
        "other_user": other_info,
        "page": page,
    }


@router.post("/conversations/{conv_id}/send")
async def send_in_conversation(conv_id: str, payload: SendMessage, request: Request):
    """Send a message in an existing conversation."""
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    conv = await db.direct_conversations.find_one(
        {"conversation_id": conv_id, "participants": user.user_id}, {"_id": 0, "conversation_id": 1, "participants": 1}
    )
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    now_iso = datetime.now(timezone.utc).isoformat()
    msg_id = _gen_id("msg")
    recipient_id = [p for p in conv["participants"] if p != user.user_id][0]

    message_doc = {
        "message_id": msg_id,
        "conversation_id": conv_id,
        "sender_id": user.user_id,
        "sender_name": getattr(user, "name", ""),
        "content": payload.message,
        "read": False,
        "created_at": now_iso,
    }
    await db.direct_messages.insert_one(message_doc)
    message_doc.pop("_id", None)

    await db.direct_conversations.update_one(
        {"conversation_id": conv_id},
        {
            "$set": {
                "last_message": payload.message[:100],
                "last_message_at": now_iso,
                "last_sender_id": user.user_id,
                "updated_at": now_iso,
            },
            "$inc": {f"unread.{recipient_id}": 1},
        },
    )

    # Real-time push
    try:
        from utils.ws_manager import ws_manager

        await ws_manager.send_to_user(
            recipient_id,
            {
                "type": "new_message",
                "conversation_id": conv_id,
                "sender_id": user.user_id,
                "sender_name": getattr(user, "name", ""),
                "message": payload.message[:100],
                "message_id": msg_id,
                "timestamp": now_iso,
            },
        )
    except Exception:
        pass

    # Notification
    try:
        from routes.notification_engine import emit_notification

        await emit_notification(
            user_id=recipient_id,
            notif_type="new_direct_message",
            title=f"Message from {getattr(user, 'name', 'Someone')}",
            body=payload.message[:80],
            action_url="/messages",
        )
    except Exception:
        pass

    return {"success": True, "message_id": msg_id, "message": message_doc}


@router.get("/unread-count")
async def get_unread_count(request: Request):
    """Get total unread message count for the current user."""
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    pipeline = [
        {"$match": {"participants": user.user_id}},
        {"$group": {"_id": None, "total": {"$sum": f"$unread.{user.user_id}"}}},
    ]
    result = await db.direct_conversations.aggregate(pipeline).to_list(1)
    total = result[0]["total"] if result else 0
    return {"unread": total}


@router.get("/search-users")
async def search_users(request: Request, q: str = "", role: str = ""):
    """Search for users to message."""
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    if not q or len(q) < 2:
        return {"users": []}

    query = {
        "$or": [
            {"name": {"$regex": re.escape(str(q)), "$options": "i"}},
            {"email": {"$regex": re.escape(str(q)), "$options": "i"}},
        ],
        "user_id": {"$ne": user.user_id},
    }
    if role:
        query["roles"] = role

    users = (
        await db.users.find(query, {"_id": 0, "user_id": 1, "name": 1, "email": 1, "avatar_url": 1, "roles": 1})
        .limit(10)
        .to_list(10)
    )

    return {"users": users}


# ── Read Receipts & Typing Indicators ──


@router.post("/conversations/{conv_id}/read")
async def mark_messages_read(conv_id: str, request: Request):
    """Mark all messages in a conversation as read for the current user. Sends read receipt via WebSocket."""
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    conv = await db.direct_conversations.find_one(
        {"conversation_id": conv_id, "participants": user.user_id}, {"_id": 0, "conversation_id": 1, "participants": 1}
    )
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    now_iso = datetime.now(timezone.utc).isoformat()

    # Mark all unread messages from the other person as read
    result = await db.direct_messages.update_many(
        {"conversation_id": conv_id, "sender_id": {"$ne": user.user_id}, "read": False},
        {"$set": {"read": True, "read_at": now_iso}},
    )

    # Reset unread counter for current user
    await db.direct_conversations.update_one(
        {"conversation_id": conv_id}, {"$set": {f"unread.{user.user_id}": 0, f"last_read.{user.user_id}": now_iso}}
    )

    # Send read receipt via WebSocket to the other participant
    other_id = [p for p in conv["participants"] if p != user.user_id][0]
    try:
        from utils.ws_manager import ws_manager

        await ws_manager.send_to_user(
            other_id,
            {
                "type": "read_receipt",
                "conversation_id": conv_id,
                "reader_id": user.user_id,
                "read_at": now_iso,
                "count": result.modified_count,
            },
        )
    except Exception:
        pass

    return {"success": True, "marked_read": result.modified_count}


@router.post("/conversations/{conv_id}/typing")
async def send_typing_indicator(conv_id: str, request: Request):
    """Broadcast typing indicator to the other participant in the conversation via WebSocket."""
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    conv = await db.direct_conversations.find_one(
        {"conversation_id": conv_id, "participants": user.user_id}, {"_id": 0, "participants": 1}
    )
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    other_id = [p for p in conv["participants"] if p != user.user_id][0]
    try:
        from utils.ws_manager import ws_manager

        await ws_manager.send_to_user(
            other_id,
            {
                "type": "typing_indicator",
                "conversation_id": conv_id,
                "user_id": user.user_id,
                "user_name": getattr(user, "name", ""),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )
    except Exception:
        pass

    return {"success": True}
