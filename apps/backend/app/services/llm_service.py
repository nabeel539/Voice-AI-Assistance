"""
CIMET Reconnect — Large Language Model (LLM) Service

Decoupled interface and OpenAI implementation for generating conversational responses
and performing structured extraction via Pydantic models.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Type, TypeVar
from openai import OpenAI
from pydantic import BaseModel

from app.config import get_settings

T = TypeVar("T", bound=BaseModel)


class LLMService(ABC):
    """Abstract interface for LLM providers."""

    @abstractmethod
    def generate_chat_response(
        self,
        messages: List[Dict[str, str]],
        system_prompt: Optional[str] = None,
        temperature: float = 0.3,
    ) -> str:
        """Generate conversational reply text."""
        ...

    @abstractmethod
    def parse_structured(
        self,
        prompt: str,
        response_model: Type[T],
        system_prompt: Optional[str] = None,
    ) -> T:
        """Extract structured data adhering to a Pydantic schema."""
        ...


class OpenAILLMService(LLMService):
    """OpenAI LLM provider using modern client with structured output support."""

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        settings = get_settings()
        self._api_key = api_key or settings.openai_api_key
        self._model = model or settings.openai_llm_model or "gpt-4o"
        self._client: Optional[OpenAI] = None

    def _get_client(self) -> OpenAI:
        if self._client is None:
            self._client = OpenAI(api_key=self._api_key)
        return self._client

    def generate_chat_response(
        self,
        messages: List[Dict[str, str]],
        system_prompt: Optional[str] = None,
        temperature: float = 0.3,
    ) -> str:
        client = self._get_client()
        full_messages = []
        if system_prompt:
            full_messages.append({"role": "system", "content": system_prompt})
        full_messages.extend(messages)

        resp = client.chat.completions.create(
            model=self._model,
            messages=full_messages,
            temperature=temperature,
        )
        return resp.choices[0].message.content or ""

    def parse_structured(
        self,
        prompt: str,
        response_model: Type[T],
        system_prompt: Optional[str] = None,
    ) -> T:
        client = self._get_client()
        full_messages = []
        if system_prompt:
            full_messages.append({"role": "system", "content": system_prompt})
        full_messages.append({"role": "user", "content": prompt})

        # Use OpenAI structured output parsing
        completion = client.beta.chat.completions.parse(
            model=self._model,
            messages=full_messages,
            response_format=response_model,
        )
        return completion.choices[0].message.parsed


class MockLLMService(LLMService):
    """Mock LLM service for testing."""

    def __init__(self, mock_response: str = "Thank you, I have recorded that."):
        self.mock_response = mock_response

    def generate_chat_response(
        self,
        messages: List[Dict[str, str]],
        system_prompt: Optional[str] = None,
        temperature: float = 0.3,
    ) -> str:
        return self.mock_response

    def parse_structured(
        self,
        prompt: str,
        response_model: Type[T],
        system_prompt: Optional[str] = None,
    ) -> T:
        # Default mock factory or dummy instance
        return response_model.model_construct()
