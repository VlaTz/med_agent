"""Thin LLM client using the OpenAI chat-completions contract.

Provider-agnostic by design: api key / base url / model all come from
environment variables (LLM_API_KEY / LLM_BASE_URL / LLM_MODEL, see
.env.example), not from a hardcoded provider default in code. Swapping
providers is a .env edit, not a code change.

Env vars are read lazily (inside functions, not as module-level constants) so
this works regardless of whether python-dotenv's load_dotenv() ran before or
after this module was first imported.
"""
from __future__ import annotations

import json
import os
from typing import Any, Optional

from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential


def _client() -> OpenAI:
    api_key = os.environ.get("LLM_API_KEY")
    if not api_key:
        raise RuntimeError("No API key found. Set LLM_API_KEY in your .env file (see .env.example).")
    base_url = os.environ.get("LLM_BASE_URL") or None
    # The openai SDK's own default timeout is 10 minutes; a provider-side hang (e.g. an
    # overloaded model alias) would otherwise sit silently for a very long time, tripled by
    # tenacity's 3 retries below. A firm per-request timeout turns that into a clear error.
    timeout = float(os.environ.get("LLM_TIMEOUT_SECONDS", "60"))
    return OpenAI(api_key=api_key, base_url=base_url, timeout=timeout)


def _default_model() -> str:
    model = os.environ.get("LLM_MODEL")
    if not model:
        raise RuntimeError("No model configured. Set LLM_MODEL in your .env file (see .env.example).")
    return model


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=20))
def chat(
    messages: list[dict[str, str]],
    *,
    model: Optional[str] = None,
    temperature: float = 0.2,
    json_mode: bool = False,
    tools: Optional[list[dict[str, Any]]] = None,
) -> str:
    """Single-shot chat completion, returns the assistant's text content."""
    client = _client()
    kwargs: dict[str, Any] = dict(model=model or _default_model(), messages=messages, temperature=temperature)
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    if tools:
        kwargs["tools"] = tools
    response = client.chat.completions.create(**kwargs)
    return response.choices[0].message.content or ""


def chat_json(messages: list[dict[str, str]], *, model: Optional[str] = None, temperature: float = 0.2) -> dict:
    """Chat completion forced into JSON mode, parsed into a dict.

    Raises json.JSONDecodeError if the model still returns malformed JSON after
    the request-level json_mode hint (caller decides whether to retry).
    """
    raw = chat(messages, model=model, temperature=temperature, json_mode=True)
    return json.loads(raw)
