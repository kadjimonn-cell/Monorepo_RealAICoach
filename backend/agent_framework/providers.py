"""Provider abstraction layer — agents never touch a vendor SDK directly."""

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class AIProvider(ABC):
    """Standard interface every AI provider must implement."""

    name: str = "base"

    @abstractmethod
    async def complete(
        self,
        *,
        model: str,
        system_message: str,
        prompt: str,
        session_id: str,
        timeout_seconds: float = 45.0,
        feature: str = "agent_framework",
        user_id: Optional[str] = None,
    ) -> str:
        """Return the model's text completion."""


class EmergentProvider(AIProvider):
    """Provider backed by the platform's existing Emergent LLM gateway.

    One class serves multiple logical providers (openai / anthropic / google)
    via the `vendor` routing parameter, so agent profiles stay vendor-agnostic.
    """

    def __init__(self, vendor: str):
        self.vendor = vendor
        self.name = vendor

    async def complete(
        self,
        *,
        model: str,
        system_message: str,
        prompt: str,
        session_id: str,
        timeout_seconds: float = 45.0,
        feature: str = "agent_framework",
        user_id: Optional[str] = None,
    ) -> str:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        from routes.db import EMERGENT_LLM_KEY
        from services.llm_usage_logger import log_llm_call

        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=session_id,
            system_message=system_message,
        ).with_model(self.vendor, model)

        def _blocking():
            return asyncio.run(chat.send_message(UserMessage(text=prompt)))

        t0 = time.time()
        try:
            response = await asyncio.wait_for(
                asyncio.to_thread(_blocking), timeout=timeout_seconds
            )
            text = response.text if hasattr(response, "text") else str(response)
            await log_llm_call(
                model=model, provider=self.vendor, feature=feature, user_id=user_id,
                session_id=session_id, prompt_text=prompt, response_text=text,
                latency_ms=int((time.time() - t0) * 1000), success=True,
            )
            return text.strip()
        except asyncio.TimeoutError:
            await log_llm_call(
                model=model, provider=self.vendor, feature=feature, user_id=user_id,
                session_id=session_id, prompt_text=prompt, response_text="",
                success=False, error="timeout",
            )
            raise TimeoutError(f"Provider '{self.vendor}' timed out after {timeout_seconds}s")


class ProviderRegistry:
    """Central registry — new providers plug in without core changes."""

    def __init__(self):
        self._providers: Dict[str, AIProvider] = {}

    def register(self, provider: AIProvider) -> None:
        self._providers[provider.name] = provider

    def get(self, name: str) -> AIProvider:
        provider = self._providers.get(name)
        if not provider:
            raise KeyError(f"Unknown AI provider '{name}'. Registered: {list(self._providers)}")
        return provider

    def list_names(self) -> list:
        return sorted(self._providers.keys())


provider_registry = ProviderRegistry()
for _vendor in ("openai", "anthropic", "google"):
    provider_registry.register(EmergentProvider(_vendor))
