"""Event bus: every orchestrator/subagent/tool decision flows through here.

Fans out to (a) a JSONL file for reproducible run logs and (b) an optional
callback so a UI (Streamlit) can render steps live as they happen.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Callable, Optional

from src.schemas import AgentEvent

EventCallback = Callable[[AgentEvent], None]


class EventBus:
    def __init__(self, log_path: Path, on_event: Optional[EventCallback] = None):
        self.log_path = log_path
        self.on_event = on_event
        os.makedirs(log_path.parent, exist_ok=True)
        self._fh = open(log_path, "a", encoding="utf-8")

    def emit(self, actor: str, phase: str, event_type: str, message: str, **data) -> AgentEvent:
        event = AgentEvent(actor=actor, phase=phase, event_type=event_type, message=message, data=data)
        self._fh.write(event.model_dump_json() + "\n")
        self._fh.flush()
        if self.on_event:
            self.on_event(event)
        return event

    def close(self) -> None:
        self._fh.close()
