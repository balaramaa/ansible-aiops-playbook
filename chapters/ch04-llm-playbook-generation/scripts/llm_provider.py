"""
llm_provider.py — Chapter 4, Listing 4-3
Provider abstraction layer for OpenAI, Anthropic, and Ollama.

Author : Balaramakrishna Alti
GitHub : https://github.com/balaramaa/ansible-aiops-playbook

Usage:
    from llm_provider import get_provider
    provider = get_provider()           # auto-detect
    provider = get_provider("ollama")   # force Ollama
    response = provider.generate(system_prompt, user_prompt)
    print(response.content)

Environment variables:
    OPENAI_API_KEY      — enables OpenAI provider
    ANTHROPIC_API_KEY   — enables Anthropic provider
    LLM_PROVIDER        — force provider: openai | anthropic | ollama | auto
    OLLAMA_BASE_URL     — Ollama URL (default: http://localhost:11434)
    OLLAMA_MODEL        — Ollama model (default: codellama)
"""

from __future__ import annotations
import os, time, logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

log = logging.getLogger(__name__)


@dataclass
class LLMResponse:
    """Standardized response from any LLM provider."""
    content: str
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    elapsed_seconds: float

    def __str__(self):
        return (f"[{self.provider}/{self.model}] "
                f"{self.input_tokens}+{self.output_tokens} tokens "
                f"in {self.elapsed_seconds}s")


class LLMProvider(ABC):
    """Abstract base class — all providers implement this interface."""

    @abstractmethod
    def generate(self,
                 system_prompt: str,
                 user_prompt: str,
                 temperature: float = 0.0,
                 max_tokens: int = 4096) -> LLMResponse:
        """Generate a completion given system and user prompts."""
        pass


class OpenAIProvider(LLMProvider):
    """OpenAI GPT-4o provider."""

    def __init__(self, model: str = "gpt-4o"):
        try:
            import openai
        except ImportError:
            raise ImportError("pip3 install openai")
        self.client = openai.OpenAI(api_key=os.environ["OPENAI_API_KEY"])
        self.model = model

    def generate(self, system_prompt, user_prompt,
                 temperature=0.0, max_tokens=4096) -> LLMResponse:
        start = time.time()
        response = self.client.chat.completions.create(
            model=self.model,
            temperature=temperature,
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_prompt},
            ]
        )
        return LLMResponse(
            content=response.choices[0].message.content,
            provider="openai",
            model=response.model,
            input_tokens=response.usage.prompt_tokens,
            output_tokens=response.usage.completion_tokens,
            elapsed_seconds=round(time.time() - start, 2)
        )


class AnthropicProvider(LLMProvider):
    """Anthropic Claude provider."""

    def __init__(self, model: str = "claude-sonnet-4-6"):
        try:
            import anthropic
        except ImportError:
            raise ImportError("pip3 install anthropic")
        self.client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        self.model = model

    def generate(self, system_prompt, user_prompt,
                 temperature=0.0, max_tokens=4096) -> LLMResponse:
        start = time.time()
        message = self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}]
        )
        return LLMResponse(
            content=message.content[0].text,
            provider="anthropic",
            model=message.model,
            input_tokens=message.usage.input_tokens,
            output_tokens=message.usage.output_tokens,
            elapsed_seconds=round(time.time() - start, 2)
        )


class OllamaProvider(LLMProvider):
    """Ollama local LLM provider — free, no API key required."""

    def __init__(self,
                 model: str = None,
                 base_url: str = None):
        try:
            import requests
            self.requests = requests
        except ImportError:
            raise ImportError("pip3 install requests")
        self.model    = model    or os.environ.get("OLLAMA_MODEL", "codellama")
        self.base_url = base_url or os.environ.get("OLLAMA_BASE_URL",
                                                    "http://localhost:11434")
        self._verify_ollama()

    def _verify_ollama(self):
        """Check Ollama is running and the model is available."""
        try:
            r = self.requests.get(f"{self.base_url}/api/tags", timeout=5)
            r.raise_for_status()
            models = [m["name"] for m in r.json().get("models", [])]
            if not any(self.model in m for m in models):
                log.warning(f"Model '{self.model}' not found. "
                            f"Pull with: ollama pull {self.model}")
        except Exception as e:
            log.warning(f"Ollama not reachable at {self.base_url}: {e}")

    def generate(self, system_prompt, user_prompt,
                 temperature=0.0, max_tokens=4096) -> LLMResponse:
        start = time.time()
        payload = {
            "model": self.model,
            "prompt": f"{system_prompt}\n\n{user_prompt}",
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            }
        }
        response = self.requests.post(
            f"{self.base_url}/api/generate",
            json=payload, timeout=180
        )
        response.raise_for_status()
        data = response.json()
        return LLMResponse(
            content=data.get("response", ""),
            provider="ollama",
            model=self.model,
            input_tokens=data.get("prompt_eval_count", 0),
            output_tokens=data.get("eval_count", 0),
            elapsed_seconds=round(time.time() - start, 2)
        )


def get_provider(provider: Optional[str] = None) -> LLMProvider:
    """
    Factory function — returns the appropriate LLM provider.

    Provider selection order:
    1. Explicit provider argument
    2. LLM_PROVIDER environment variable
    3. Auto-detect: OpenAI → Anthropic → Ollama

    Args:
        provider: 'openai' | 'anthropic' | 'ollama' | 'auto' | None

    Returns:
        Configured LLMProvider instance
    """
    p = (provider or os.environ.get("LLM_PROVIDER", "auto")).lower()

    if p in ("openai", "auto") and os.environ.get("OPENAI_API_KEY"):
        log.info("Provider: OpenAI (GPT-4o)")
        return OpenAIProvider()

    if p in ("anthropic", "auto") and os.environ.get("ANTHROPIC_API_KEY"):
        log.info("Provider: Anthropic (Claude)")
        return AnthropicProvider()

    if p == "openai":
        raise EnvironmentError("OPENAI_API_KEY not set")
    if p == "anthropic":
        raise EnvironmentError("ANTHROPIC_API_KEY not set")

    log.info("Provider: Ollama (local — free)")
    return OllamaProvider()
