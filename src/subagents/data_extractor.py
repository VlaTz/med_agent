"""Subagent 2: data extractor.

Converts raw search hits (abstracts / registry summaries) into structured
StudyRecord objects, under skills/clinical_outcome_extraction_rules.md and
skills/evidence_level_scale.md.
"""
from __future__ import annotations

from pydantic import ValidationError

from src.logging_utils import EventBus
from src.schemas import SourceRecord, StudyRecord
from src.subagents.base import llm_call_json, load_skills

ACTOR = "data_extractor"
PHASE = "extract"
BATCH_SIZE = 6

_EVIDENCE_LEVEL_BY_NUMBER = {
    1: "rct_double_blind",
    2: "rct_open_label",
    3: "cohort",
    4: "case_series",
    5: "registered_trial",
    6: "preclinical",
    7: "other",
}


def _normalize_evidence_level(value):
    """The model sometimes returns the numeric 'Level' column from the skill's table
    instead of the string 'Label' column -- coerce either into the string enum value."""
    if value is None or isinstance(value, str):
        return value
    if isinstance(value, (int, float)):
        return _EVIDENCE_LEVEL_BY_NUMBER.get(int(value), str(value))
    return str(value)

SYSTEM_PROMPT_TEMPLATE = """You are a clinical data extraction specialist. You convert raw \
literature/trial-registry hits into structured StudyRecord objects for a mitochondrial-medicine \
research harness. Follow the skills below exactly; they are the ground truth for how to fill \
every field.

{skills}

Return ONLY a JSON object: {{"records": [<StudyRecord-shaped dict>, ...]}}. One input hit may \
produce more than one record if it reports more than one arm (see the extraction rules). Every \
output record MUST include the "source_key" field copied verbatim from its input hit, so it can \
be traced back.

If a hit is a general review/mechanistic article, editorial, or anything else that does not \
describe a specific drug being studied in a specific arm (i.e. you cannot confidently fill both \
"drug" and "arm"), do NOT emit a record for it at all -- skip that hit entirely rather than \
emitting a record with null/guessed required fields. It is correct and expected for the output \
"records" list to contain fewer entries than input hits, or even be empty.

StudyRecord fields: pmid, doi, nct_id, url, title, year, disease, drug, target, arm \
(mitotherapy|standard_of_care|combination|placebo), phase, n, study_type \
(rct_double_blind|rct_open_label|cohort|case_series|preclinical|registered_trial|other), \
outcome_measure, effect_direction (improved|no_effect|worse|mixed|unknown), effect_magnitude, \
evidence_level, notes.

All fields except "notes" must stay faithful to the source text (drug/disease names, outcome \
measures, magnitudes as reported) -- do not translate them. Write the "notes" field in Russian.
"""


def _hit_to_prompt_dict(hit: SourceRecord, key: str) -> dict:
    return {
        "source_key": key,
        "pmid": hit.pmid,
        "doi": hit.doi,
        "nct_id": hit.nct_id,
        "url": hit.url,
        "title": hit.title,
        "year": hit.year,
        "abstract": (hit.abstract or "")[:2500],
    }


def run(bus: EventBus, hits: list[SourceRecord], diseases: list[str], drug_classes: list[str]) -> list[StudyRecord]:
    bus.emit(ACTOR, PHASE, "start", f"Извлечение структурированных данных из {len(hits)} источников")
    skills_text = load_skills(bus, ACTOR, PHASE, ["clinical_outcome_extraction_rules", "evidence_level_scale"])
    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(skills=skills_text)

    keyed_hits = {(h.pmid or h.doi or h.nct_id or h.title): h for h in hits}
    keys = list(keyed_hits.keys())

    extracted: list[StudyRecord] = []
    for i in range(0, len(keys), BATCH_SIZE):
        batch_keys = keys[i : i + BATCH_SIZE]
        batch_payload = [_hit_to_prompt_dict(keyed_hits[k], k) for k in batch_keys]
        user_prompt = (
            f"Diseases in scope: {diseases}\nDrug classes in scope: {drug_classes}\n\n"
            f"Hits to extract (JSON list):\n{batch_payload}"
        )
        result = llm_call_json(bus, ACTOR, PHASE, system_prompt, str(user_prompt), label=f"extract_batch_{i // BATCH_SIZE + 1}")

        for raw in result.get("records", []):
            source_key = raw.pop("source_key", None)
            source_hit = keyed_hits.get(source_key)
            raw.setdefault("pmid", source_hit.pmid if source_hit else None)
            raw.setdefault("doi", source_hit.doi if source_hit else None)
            raw.setdefault("nct_id", source_hit.nct_id if source_hit else None)
            raw.setdefault("url", source_hit.url if source_hit else None)
            if not raw.get("title") and source_hit:
                raw["title"] = source_hit.title
            raw["evidence_level"] = _normalize_evidence_level(raw.get("evidence_level"))
            try:
                extracted.append(StudyRecord(**raw))
            except ValidationError as e:
                detail = "; ".join(f"{'.'.join(str(p) for p in err['loc'])}: {err['msg']}" for err in e.errors())
                log_ref = source_key or raw.get("pmid") or raw.get("doi") or raw.get("nct_id") or "неизвестный источник"
                bus.emit(ACTOR, PHASE, "issue", f"Запись из {log_ref} отброшена как некорректная: {detail}", source_key=source_key, raw=raw)

    bus.emit(ACTOR, PHASE, "end", f"Извлечено {len(extracted)} структурированных записей")
    return extracted
