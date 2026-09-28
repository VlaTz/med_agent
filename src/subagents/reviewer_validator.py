"""Subagent 5: reviewer-validator.

Re-verifies every citation against the source APIs (deterministic, no LLM) and
applies the judgment-heavy checks from skills/citation_validation_checklist.md
(numbers traceable, no unsupported superlatives, correct scope) via one batched
LLM call. High-severity issues cause a record to be dropped from the final
report.
"""
from __future__ import annotations

import difflib

from src.logging_utils import EventBus
from src.schemas import ReviewIssue, StudyRecord
from src.subagents.base import llm_call_json, load_skills
from src.tools import clinicaltrials, pubmed

ACTOR = "reviewer_validator"
PHASE = "review"

SYSTEM_PROMPT_TEMPLATE = """You are the final reviewer for a mitochondrial-medicine research \
harness. Apply the checklist below to the given records, focusing ONLY on checks 3, 4 and 5 \
(numbers traceable, no unsupported superlatives, correct disease/drug scope) -- identifier \
resolution and title matching have already been checked deterministically upstream and are \
provided to you as {{"resolved": true/false}} per record.

{skills}

Return ONLY a JSON object: {{"issues": [{{"record_ref": "pmid/doi/nct_id", "issue_type": "...", \
"severity": "low|medium|high", "detail": "..."}}, ...]}}. Return an empty list if a record has no \
issues -- do not invent issues to have something to report. Write "detail" in Russian; keep \
"issue_type" and "severity" exactly as specified (low|medium|high) in English.
"""


def _record_ref(record: StudyRecord) -> str:
    return record.pmid or record.doi or record.nct_id or record.title


def _verify_and_check_identity(bus: EventBus, record: StudyRecord) -> tuple[bool, list[ReviewIssue]]:
    """Deterministic checks: does the ID resolve, and does the title match?"""
    ref = _record_ref(record)
    resolved = None
    if record.pmid or record.doi:
        resolved = pubmed.lookup_by_id(pmid=record.pmid, doi=record.doi)
        bus.emit(
            ACTOR, PHASE, "tool_call", f"verify_citation(pmid={record.pmid}, doi={record.doi})",
            tool="pubmed.lookup_by_id", ref=ref, found=resolved is not None,
            extracted_title=record.title,
            resolved_title=resolved.title if resolved else None,
            resolved_url=resolved.url if resolved else None,
        )
    elif record.nct_id:
        resolved = clinicaltrials.lookup_by_nct(record.nct_id)
        bus.emit(
            ACTOR, PHASE, "tool_call", f"verify_citation(nct_id={record.nct_id})",
            tool="clinicaltrials.lookup_by_nct", ref=ref, found=resolved is not None,
            extracted_title=record.title,
            resolved_title=resolved.title if resolved else None,
            resolved_url=resolved.url if resolved else None,
        )

    issues: list[ReviewIssue] = []
    if resolved is None:
        issues.append(ReviewIssue(record_ref=ref, issue_type="unverifiable_citation", severity="high", detail="Идентификатор не найден при повторном запросе к исходному API."))
        return False, issues

    similarity = difflib.SequenceMatcher(None, record.title.lower(), resolved.title.lower()).ratio()
    if similarity < 0.6:
        issues.append(ReviewIssue(record_ref=ref, issue_type="number_mismatch", severity="high", detail=f"Схожесть заголовков с источником при повторном запросе: {similarity:.2f} -- вероятно, при извлечении привязан неверный идентификатор."))
        return False, issues
    return True, issues


def run(bus: EventBus, studies: list[StudyRecord]) -> tuple[list[StudyRecord], list[ReviewIssue]]:
    bus.emit(ACTOR, PHASE, "start", f"Проверка {len(studies)} записей")
    skills_text = load_skills(bus, ACTOR, PHASE, ["citation_validation_checklist"])
    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(skills=skills_text)

    all_issues: list[ReviewIssue] = []
    resolved_flags: dict[str, bool] = {}
    for record in studies:
        ok, issues = _verify_and_check_identity(bus, record)
        resolved_flags[_record_ref(record)] = ok
        all_issues.extend(issues)

    payload = [
        {
            "record_ref": _record_ref(r),
            "resolved": resolved_flags[_record_ref(r)],
            "drug": r.drug,
            "disease": r.disease,
            "n": r.n,
            "effect_direction": r.effect_direction.value,
            "effect_magnitude": r.effect_magnitude,
            "notes": r.notes,
        }
        for r in studies
    ]
    if payload:
        result = llm_call_json(bus, ACTOR, PHASE, system_prompt, f"Records to check:\n{payload}", label="checklist_review")
        for raw in result.get("issues", []):
            try:
                all_issues.append(ReviewIssue(**raw))
            except Exception:
                continue

    high_severity_refs = {i.record_ref for i in all_issues if i.severity == "high"}
    kept = [r for r in studies if _record_ref(r) not in high_severity_refs]

    bus.emit(ACTOR, PHASE, "end", f"Оставлено {len(kept)}/{len(studies)} записей, зафиксировано замечаний: {len(all_issues)}", n_issues=len(all_issues), n_dropped=len(studies) - len(kept))
    return kept, all_issues
