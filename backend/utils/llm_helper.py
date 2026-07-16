import asyncio
import json
import logging
import time
from emergentintegrations.llm.chat import LlmChat, UserMessage
from routes.db import EMERGENT_LLM_KEY
from services.llm_usage_logger import log_llm_call

logger = logging.getLogger(__name__)


def _send_message_blocking(chat, message):
    # emergentintegrations' send_message awaits a SYNCHRONOUS litellm.completion(),
    # which blocks the event loop and serializes all concurrent LLM calls.
    # Running it on a worker thread restores true concurrency and keeps the API responsive.
    return asyncio.run(chat.send_message(message))


async def generate_verified_json(
    prompt: str, system_message: str, session_id: str, model: str = "gpt-4o", max_retries: int = 2,
    feature: str = "verified_json", user_id: str | None = None,
):
    """
    Generates JSON with a retry mechanism for robustness.
    Includes a self-correction step if JSON parsing fails.
    """
    current_prompt = prompt

    for attempt in range(max_retries + 1):
        try:
            chat = LlmChat(
                api_key=EMERGENT_LLM_KEY,
                session_id=f"{session_id}-try-{attempt}",
                system_message=system_message + "\n\nCRITICAL: Return ONLY valid JSON. No markdown formatting.",
            ).with_model("openai", model)

            # Hard ceiling so upstream LLM 502s don't stall the caller's event loop
            t0 = time.time()
            response = await asyncio.wait_for(
                asyncio.to_thread(_send_message_blocking, chat, UserMessage(text=current_prompt)),
                timeout=20.0,
            )
            latency_ms = int((time.time() - t0) * 1000)
            text = response.text if hasattr(response, "text") else str(response)

            await log_llm_call(
                model=model, provider="openai", feature=feature, user_id=user_id,
                session_id=session_id, prompt_text=current_prompt, response_text=text,
                latency_ms=latency_ms, success=True,
            )

            # Clean text
            clean_text = text.strip()
            if clean_text.startswith("```json"):
                clean_text = clean_text[7:]
            if clean_text.startswith("```"):
                clean_text = clean_text[3:]
            if clean_text.endswith("```"):
                clean_text = clean_text[:-3]
            clean_text = clean_text.strip()

            return json.loads(clean_text)

        except asyncio.TimeoutError:
            logger.warning(f"LLM timeout (Attempt {attempt}) — upstream 20s ceiling hit")
            await log_llm_call(
                model=model, provider="openai", feature=feature, user_id=user_id,
                session_id=session_id, prompt_text=current_prompt, response_text="",
                success=False, error="timeout",
            )
            if attempt == max_retries:
                raise ValueError("LLM upstream timeout")
        except json.JSONDecodeError as e:
            logger.warning(f"JSON Parse Error (Attempt {attempt}): {e}")
            # Feed the error back to the model to correct itself
            current_prompt = (
                f"Previous response was invalid JSON. Error: {str(e)}. \nPlease fix the JSON and return it."
            )

        except Exception as e:
            logger.error(f"LLM Error (Attempt {attempt}): {e}")
            await log_llm_call(
                model=model, provider="openai", feature=feature, user_id=user_id,
                session_id=session_id, prompt_text=current_prompt, response_text="",
                success=False, error=str(e)[:200],
            )
            if attempt == max_retries:
                raise e

    raise ValueError("Failed to generate valid JSON after retries")


async def generate_verified_text(prompt: str, system_message: str, session_id: str,
                                 feature: str = "verified_text", user_id: str | None = None):
    """
    Generates text with a 'Critique & Refine' step for higher accuracy.
    """
    # 1. Draft
    draft_chat = LlmChat(
        api_key=EMERGENT_LLM_KEY, session_id=f"{session_id}-draft", system_message=system_message
    ).with_model("openai", "gpt-4o")

    t0 = time.time()
    draft_resp = await asyncio.wait_for(
        draft_chat.send_message(UserMessage(text=prompt)),
        timeout=20.0,
    )
    draft_text = draft_resp.text if hasattr(draft_resp, "text") else str(draft_resp)
    await log_llm_call(
        model="gpt-4o", provider="openai", feature=f"{feature}:draft", user_id=user_id,
        session_id=session_id, prompt_text=prompt, response_text=draft_text,
        latency_ms=int((time.time() - t0) * 1000), success=True,
    )

    # 2. Critique (Self-Correction) - Optional optimization: Only do this for complex queries?
    # For "No Mistake" requirement, we do it.
    critique_chat = LlmChat(
        api_key=EMERGENT_LLM_KEY,
        session_id=f"{session_id}-critique",
        system_message="You are a Fact Checker. Review the draft response for accuracy, logic, and safety. If it's correct, output 'VERIFIED'. If not, provide the corrected version directly.",
    ).with_model("openai", "gpt-4o")

    critique_prompt = f"Original Query: {prompt}\n\nDraft Response: {draft_text}\n\nReview:"
    t1 = time.time()
    critique_resp = await asyncio.wait_for(
        critique_chat.send_message(UserMessage(text=critique_prompt)),
        timeout=20.0,
    )
    critique_text = critique_resp.text if hasattr(critique_resp, "text") else str(critique_resp)
    await log_llm_call(
        model="gpt-4o", provider="openai", feature=f"{feature}:critique", user_id=user_id,
        session_id=session_id, prompt_text=critique_prompt, response_text=critique_text,
        latency_ms=int((time.time() - t1) * 1000), success=True,
    )

    if "VERIFIED" in critique_text and len(critique_text) < 50:
        return draft_text
    else:
        # If the critique rewrote it, use that
        return critique_text.replace("VERIFIED", "").strip()
