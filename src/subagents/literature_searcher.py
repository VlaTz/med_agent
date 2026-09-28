"""Subagent 1: literature searcher.

Turns the orchestrator's plan (diseases, drug classes, date window) into
concrete search queries, executes them against the PubMed/Europe PMC and
ClinicalTrials.gov tools, and deduplicates the raw hits.
"""
from __future__ import annotations

import re

from src.logging_utils import EventBus
from src.schemas import Plan, SourceRecord
from src.subagents.base import llm_call_json
from src.tools import clinicaltrials, pubmed

ACTOR = "literature_searcher"
PHASE = "search"

SYSTEM_PROMPT = """You are a biomedical literature search strategist working inside a research \
harness for mitochondrial medicine. Given a list of diseases and mitochondria-targeted drug \
classes, produce concise, high-recall search queries.

Return ONLY a JSON object of the form:
{
  "pubmed_queries": ["query string", ...],
  "ctgov_pairs": [{"condition": "...", "intervention": "..."}, ...]
}

Rules:
- For each disease, include at least one query covering the mitochondria-targeted compounds AND \
one covering its standard-of-care comparator, so both arms can be compared later.
- Keep each pubmed query short (3-8 words), using AND/OR sparingly; these hit a real search API, \
not a chat model.
- Do NOT include any date filter, year, or syntax like "2021/01/01[PDAT]" in the query strings -- \
the date window is applied automatically by the search tool. A query containing date syntax will \
return zero results against this API.
- Produce at most 3 pubmed_queries and 2 ctgov_pairs per disease.
- Always write query/condition/intervention strings in English, even if the user's query is in \
another language -- these hit English-language biomedical databases.
"""

def _strip_date_syntax(query: str) -> str:
    """Defensive cleanup: the model occasionally adds PDAT/year filters despite the prompt
    rule against it, which silently zeroes out Europe PMC results."""
    cleaned = re.sub(r"\d{4}(/\d{2}/\d{2})?(\[[A-Za-z]+\])?", "", query)
    return re.sub(r"\s+", " ", cleaned).strip()


def _hit_summary(h: SourceRecord) -> dict:
    """Compact view of a hit for the UI/log -- drops the verbose raw API payload."""
    return {
        "source": h.source,
        "pmid": h.pmid,
        "doi": h.doi,
        "nct_id": h.nct_id,
        "title": h.title,
        "year": h.year,
        "url": h.url,
        "abstract": (h.abstract or "")[:500],
    }


def run(bus: EventBus, plan: Plan, max_results_per_query: int = 8) -> list[SourceRecord]:
    bus.emit(ACTOR, PHASE, "start", f"Поиск литературы по: {plan.diseases}")

    user_prompt = (
        f"Diseases: {plan.diseases}\n"
        f"Mitochondria-targeted drug classes in scope: {plan.drug_classes}\n"
        f"Date window: since {plan.date_from}."
    )
    strategy = llm_call_json(bus, ACTOR, PHASE, SYSTEM_PROMPT, user_prompt, label="search_strategy")

    records: dict[str, SourceRecord] = {}

    for raw_query in strategy.get("pubmed_queries", []):
        query = _strip_date_syntax(raw_query)
        if not query:
            continue
        hits = pubmed.search_literature(query, year_from=plan.date_from, max_results=max_results_per_query)
        bus.emit(ACTOR, PHASE, "tool_call", f"Поиск в Europe PMC: '{query}' -> {len(hits)} результатов", tool="pubmed.search_literature", query=query, n_hits=len(hits), hits=[_hit_summary(h) for h in hits])
        for h in hits:
            key = h.pmid or h.doi or h.title
            records[key] = h

    for pair in strategy.get("ctgov_pairs", []):
        cond, intr = pair.get("condition", ""), pair.get("intervention", "")
        hits = clinicaltrials.search_trials(cond, intr, year_from=plan.date_from, max_results=max_results_per_query)
        bus.emit(ACTOR, PHASE, "tool_call", f"Поиск в ClinicalTrials.gov: {cond} / {intr} -> {len(hits)} результатов", tool="clinicaltrials.search_trials", condition=cond, intervention=intr, n_hits=len(hits), hits=[_hit_summary(h) for h in hits])
        for h in hits:
            key = h.nct_id or h.title
            records[key] = h

    result = list(records.values())
    bus.emit(ACTOR, PHASE, "end", f"Поиск завершён: {len(result)} уникальных записей")
    return result
