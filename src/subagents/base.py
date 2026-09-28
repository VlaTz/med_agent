"""Shared plumbing for subagents: skill injection + logged LLM calls.

Every subagent is a thin module (not a class hierarchy) that calls
`load_skills` to pull its assigned /skills files and `llm_call` to talk to the
model -- both go through the shared EventBus so the orchestrator's log and the
Streamlit UI see the same stream of "start / skill_loaded / llm_call / end"
events regardless of which subagent is running.
"""
from __future__ import annotations

import json
from pathlib import Path

from src import llm
from src.logging_utils import EventBus

SKILLS_DIR = Path(__file__).resolve().parent.parent.parent / "skills"


def load_skills(bus: EventBus, actor: str, phase: str, names: list[str]) -> str:
    """Read the given /skills/<name>.md files and log that they were injected."""
    blocks = []
    for name in names:
        path = SKILLS_DIR / f"{name}.md"
        content = path.read_text(encoding="utf-8")
        blocks.append(content)
        bus.emit(actor, phase, "skill_loaded", f"Загружен скилл «{name}»", skill=name, path=str(path), content=content)
    return "\n\n---\n\n".join(blocks)


def llm_call_json(
    bus: EventBus,
    actor: str,
    phase: str,
    system_prompt: str,
    user_prompt: str,
    *,
    label: str = "llm_call",
) -> dict:
    bus.emit(
        actor,
        phase,
        "llm_call",
        f"{label}: запрос структурированного ответа",
        stage="request",
        system_prompt=system_prompt,
        user_prompt=user_prompt,
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    try:
        result = llm.chat_json(messages)
    except json.JSONDecodeError:
        # one retry with an explicit nudge -- cheaper than a full backoff loop
        messages.append({"role": "user", "content": "Your last reply was not valid JSON. Reply with ONLY a JSON object."})
        result = llm.chat_json(messages)
    bus.emit(
        actor,
        phase,
        "llm_call",
        f"{label}: структурированный ответ получен",
        stage="response",
        response=result,
    )
    return result
