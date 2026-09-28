"""Subagent 3: comparator-analyst.

Aggregates structured records per disease via the sandbox tool (deterministic
math, no LLM involved in the numbers), then asks the LLM only for a short
narrative interpretation of the already-computed stats.
"""
from __future__ import annotations

from src import i18n
from src.logging_utils import EventBus
from src.schemas import ComparisonResult, StudyRecord
from src.subagents.base import llm_call_json
from src.tools import sandbox

ACTOR = "comparator_analyst"
PHASE = "compare"

SYSTEM_PROMPT = """You are a research analyst comparing mitochondria-targeted therapies against \
standard of care for a specific disease. You are given already-computed aggregate statistics \
(study counts, sample sizes, mean effect-direction scores, evidence-level mix) -- do not \
recompute or contradict these numbers, only interpret them.

Return ONLY a JSON object: {"summary": "2-4 sentence plain-language summary of what the numbers \
show, explicitly naming which arm looks more favorable and how strong the evidence base is"}.
Be honest about small sample sizes or thin evidence -- do not oversell.
""" + i18n.RU_OUTPUT_INSTRUCTION


def run(bus: EventBus, studies: list[StudyRecord], diseases: list[str]) -> list[ComparisonResult]:
    bus.emit(ACTOR, PHASE, "start", f"Сравнение митотерапии со стандартом лечения по: {diseases}")
    results: list[ComparisonResult] = []

    for disease in diseases:
        subset = [s for s in studies if s.disease.lower() == disease.lower()]
        stats = sandbox.compare_arms(subset)
        bus.emit(ACTOR, PHASE, "tool_call", f"sandbox.compare_arms('{disease}')", tool="sandbox.compare_arms", disease=disease, stats=stats)

        figure_path = None
        if subset:
            filename = f"effect_by_phase_{disease.lower().replace(' ', '_')}.png"
            figure_path = sandbox.plot_effect_by_phase(subset, i18n.tr(disease, i18n.DISEASE_RU), filename)
            bus.emit(ACTOR, PHASE, "tool_call", f"sandbox.plot_effect_by_phase('{disease}') -> {filename}", tool="sandbox.plot_effect_by_phase", disease=disease, figure=figure_path)

        user_prompt = f"Disease: {disease}\nComputed stats: {stats}\nTotal studies in this disease: {len(subset)}"
        narrative = llm_call_json(bus, ACTOR, PHASE, SYSTEM_PROMPT, user_prompt, label=f"narrative_{disease}")

        results.append(
            ComparisonResult(
                disease=disease,
                mitotherapy_n_studies=stats["mitotherapy"]["n_studies"],
                standard_n_studies=stats["standard_of_care"]["n_studies"],
                summary=narrative.get("summary", ""),
                stats=stats,
                figure_path=figure_path,
            )
        )

    bus.emit(ACTOR, PHASE, "end", f"Построено {len(results)} сравнений по заболеваниям")
    return results
