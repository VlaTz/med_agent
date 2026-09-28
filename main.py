"""Reproducible CLI run of the mitochondrial-medicine research harness.

Usage:
    python main.py                       # runs the 2 built-in example queries
    python main.py "your query here"     # runs a single custom query
"""
from __future__ import annotations

import sys

from dotenv import load_dotenv

load_dotenv()  # before importing src.* -- src.llm reads LLM_* env vars lazily, but this keeps load order obvious

from src import config, i18n
from src.orchestrator import run_query
from src.schemas import AgentEvent

# Windows consoles often default to a legacy codepage (e.g. cp1251) that can't encode
# every Cyrillic/emoji/arrow character this harness prints -- force UTF-8 on stdout so a
# print() never crashes the run over a display-only encoding limitation.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass


def make_print_event():
    """Fresh closure per query run so the "agent changed" banner re-fires at the start
    of every new query, not just once across the whole process."""
    last_actor = {"value": None}

    def print_event(event: AgentEvent) -> None:
        if event.actor != last_actor["value"]:
            info = i18n.AGENT_INFO.get(event.actor, {"name": event.actor, "role": ""})
            print(f"\n>>> Текущий агент: {info['name']} ({event.actor})")
            if info["role"]:
                print(f"    {info['role']}")
            last_actor["value"] = event.actor
        tag = f"[{event.actor}:{event.phase}:{event.event_type}]"
        print(f"{tag:55s} {event.message}")

    return print_event


def main() -> None:
    queries = sys.argv[1:] or config.EXAMPLE_QUERIES

    for query in queries:
        print("\n" + "=" * 100)
        print(f"ЗАПРОС: {query}")
        print("=" * 100)
        report = run_query(
            query=query,
            diseases=config.DEFAULT_DISEASES,
            drug_classes=config.DEFAULT_DRUG_CLASSES,
            date_from=config.DEFAULT_DATE_FROM,
            on_event=make_print_event(),
        )
        print("\n--- ИТОГ ---")
        print(f"Оставлено записей: {len(report.studies)}")
        print(f"Замечаний валидатора: {len(report.review_issues)}")
        print("Топ направлений:")
        for s in report.rankings[:3]:
            print(f"  #{s.rank} {s.direction} ({i18n.tr(s.disease, i18n.DISEASE_RU)}) -- балл {s.score:.0f}")
        print("Аутсайдеры:")
        for s in report.rankings[-2:]:
            print(f"  #{s.rank} {s.direction} ({i18n.tr(s.disease, i18n.DISEASE_RU)}) -- балл {s.score:.0f}")


if __name__ == "__main__":
    main()
