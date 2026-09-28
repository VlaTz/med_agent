"""Subagent 4: perspective scorer.

Ranks mitotherapy directions (drug x disease) under skills/perspective_criteria.md
and skills/evidence_level_scale.md.
"""
from __future__ import annotations

from collections import Counter, defaultdict

from src import i18n
from src.logging_utils import EventBus
from src.schemas import Arm, ComparisonResult, PerspectiveScore, StudyRecord
from src.subagents.base import llm_call_json, load_skills
from src.tools import sandbox

ACTOR = "perspective_scorer"
PHASE = "score"

SYSTEM_PROMPT_TEMPLATE = """You are scoring how promising each mitochondria-targeted therapy \
direction is, using the rubric below. Score every direction you are given -- do not skip any.

{skills}

Return ONLY a JSON object: {{"scores": [{{"direction": "drug name", "disease": "...", \
"score": 0-100, "rationale": "...", "evidence_level_summary": "..."}}, ...]}}
""" + i18n.RU_OUTPUT_INSTRUCTION


def _direction_key(record: StudyRecord) -> tuple[str, str]:
    """Group by normalized drug name so e.g. 'idebenone' and 'Idebenone' from different
    extraction batches don't split into two separate ranked directions."""
    return (record.drug.strip().lower(), record.disease.strip().lower())


def run(bus: EventBus, studies: list[StudyRecord], comparisons: list[ComparisonResult]) -> tuple[list[PerspectiveScore], str | None]:
    bus.emit(ACTOR, PHASE, "start", "Оценка перспективности направлений митотерапии")
    skills_text = load_skills(bus, ACTOR, PHASE, ["perspective_criteria", "evidence_level_scale"])
    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(skills=skills_text)

    grouped: dict[tuple[str, str], list[StudyRecord]] = defaultdict(list)
    for record in studies:
        if record.arm in (Arm.MITOTHERAPY, Arm.COMBINATION):
            grouped[_direction_key(record)].append(record)

    if not grouped:
        bus.emit(ACTOR, PHASE, "end", "Направлений митотерапии для оценки не найдено")
        return [], None

    direction_payload = []
    for (_drug_key, _disease_key), records in grouped.items():
        drug = Counter(r.drug.strip() for r in records).most_common(1)[0][0]
        disease = Counter(r.disease.strip() for r in records).most_common(1)[0][0]
        stats = sandbox.arm_stats(records, Arm.MITOTHERAPY) if any(r.arm == Arm.MITOTHERAPY for r in records) else sandbox.arm_stats(records, Arm.COMBINATION)
        comparison = next((c for c in comparisons if c.disease.lower() == disease.lower()), None)
        direction_payload.append(
            {
                "direction": drug,
                "disease": disease,
                "stats": stats,
                "standard_of_care_n_studies": comparison.standard_n_studies if comparison else 0,
                "evidence_levels": [r.evidence_level for r in records],
                "effect_directions": [r.effect_direction.value for r in records],
            }
        )

    user_prompt = f"Directions to score (JSON list):\n{direction_payload}"
    result = llm_call_json(bus, ACTOR, PHASE, system_prompt, user_prompt, label="score_all_directions")

    scores: list[PerspectiveScore] = []
    for item in result.get("scores", []):
        scores.append(
            PerspectiveScore(
                direction=item.get("direction", "unknown"),
                disease=item.get("disease", "unknown"),
                score=float(item.get("score", 0)),
                rank=0,
                rationale=item.get("rationale", ""),
                evidence_level_summary=item.get("evidence_level_summary", ""),
            )
        )

    scores.sort(key=lambda s: s.score, reverse=True)
    for i, s in enumerate(scores, start=1):
        s.rank = i

    figure_path = None
    if scores:
        figure_path = sandbox.plot_ranking(
            [f"{s.direction} ({s.disease})" for s in scores],
            [s.score for s in scores],
            "perspective_ranking.png",
        )
        bus.emit(ACTOR, PHASE, "tool_call", f"sandbox.plot_ranking -> {figure_path}", tool="sandbox.plot_ranking", figure=figure_path)

    bus.emit(ACTOR, PHASE, "end", f"Ранжировано направлений: {len(scores)}")
    return scores, figure_path
