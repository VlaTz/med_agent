"""Root orchestrator: metaprompt, plan, delegation, final assembly.

Pipeline order deliberately runs the reviewer-validator right after
extraction rather than at the very end: comparison and perspective scoring
should be computed from a citation-checked set of records, not have their
conclusions built on records that later turn out to be unverifiable. This
deviation from the illustrative "search -> extract -> compare -> score ->
visualize -> report" order in the brief is itself logged as a plan decision
below.
"""
from __future__ import annotations

import os
import re
from datetime import datetime
from pathlib import Path

from src import i18n
from src.logging_utils import EventBus
from src.schemas import FinalReport, Plan, PlanStep
from src.subagents import comparator_analyst, data_extractor, literature_searcher, perspective_scorer, reviewer_validator
from src.subagents.base import llm_call_json

LOGS_DIR = Path(__file__).resolve().parent.parent / "outputs" / "logs"
REPORTS_DIR = Path(__file__).resolve().parent.parent / "outputs" / "reports"

ORCHESTRATOR_ACTOR = "orchestrator"

METAPROMPT = """You are the root orchestrator of a research harness for mitochondrial medicine. \
You never analyze literature yourself -- you only decide scope and delegate to specialized \
subagents, each of which will receive only the /skills files relevant to its task.

Scope discipline: mitochondrial medicine only (mitochondria-targeted antioxidants, mitophagy/\
biogenesis modulators, mtDNA gene therapy, mitochondrial transplantation) versus standard of care \
for the SAME diseases. Refuse scope creep -- if the user query drifts into unrelated pharmacology \
or asks for a clinical recommendation for a specific patient, note that in "scope_notes" and keep \
the plan focused on the research-review task only.

Given the user's query and the fixed disease/drug-class scope below, produce a short rationale \
(1-2 sentences each) for why each pipeline step matters for THIS query -- do not change the step \
list itself, just justify it.

Return ONLY a JSON object:
{
  "scope_notes": "...",
  "step_rationale": {
    "search": "...", "extract": "...", "review": "...", "compare": "...", "score": "...", "report": "..."
  }
}
""" + i18n.RU_OUTPUT_INSTRUCTION

PLAIN_SUMMARY_SYSTEM_PROMPT = """You explain findings from a mitochondrial-medicine research \
harness to a general reader with no medical or scientific background -- someone who has never \
heard of a clinical trial phase or an evidence-level scale. You are given already-computed \
comparisons, rankings and limitations -- do not invent new facts, numbers, drug names or claims; \
only re-express what you are given, in plain everyday language.

Rules:
- Zero unexplained jargon. If you must use a term like "клиническое испытание" or "доклиническое \
исследование", explain it in the same sentence in a few simple words (e.g. "исследование не на \
людях, а в лаборатории/на животных").
- Short sentences. Use everyday comparisons instead of statistics where possible (e.g. "участвовало \
очень мало людей" instead of "n=8").
- Explicitly name which direction looks most promising and which looks least promising in this \
data, and briefly say why in plain terms.
- Explicitly and clearly state that this is a summary of research literature, NOT medical advice, \
and NOT a recommendation for any specific person's treatment -- a reader must not walk away \
thinking this tells them what to do about their own health.
- End with one short sentence reminding the reader to talk to a real doctor for any personal \
medical decision.
- Length: 120-220 words, plain text (a few short paragraphs), no markdown headers, no bullet lists.

Return ONLY a JSON object: {"plain_summary": "..."}
""" + i18n.RU_OUTPUT_INSTRUCTION

_FIXED_STEPS = [
    ("search", "literature_searcher", ["pubmed.search_literature", "clinicaltrials.search_trials"], []),
    ("extract", "data_extractor", ["structured_parse"], ["clinical_outcome_extraction_rules", "evidence_level_scale"]),
    ("review", "reviewer_validator", ["verify_citation"], ["citation_validation_checklist"]),
    ("compare", "comparator_analyst", ["sandbox.compare_arms", "sandbox.plot_effect_by_phase"], []),
    ("score", "perspective_scorer", ["sandbox.plot_ranking"], ["perspective_criteria", "evidence_level_scale"]),
    ("report", "orchestrator", [], []),
]


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:60] or "query"


def build_plan(bus: EventBus, query: str, diseases: list[str], drug_classes: list[str], date_from: int) -> Plan:
    bus.emit(ORCHESTRATOR_ACTOR, "plan", "start", "Строится план исследования")
    user_prompt = f"User query: {query}\nDiseases in scope: {diseases}\nDrug classes in scope: {drug_classes}"
    rationale = llm_call_json(bus, ORCHESTRATOR_ACTOR, "plan", METAPROMPT, user_prompt, label="plan_rationale")

    step_rationale = rationale.get("step_rationale", {})
    steps = [
        PlanStep(step=name, subagent=subagent, tools=tools, skills=skills, rationale=step_rationale.get(name) or "(обоснование для этого шага не получено)")
        for name, subagent, tools, skills in _FIXED_STEPS
    ]
    plan = Plan(query=query, diseases=diseases, drug_classes=drug_classes, date_from=date_from, steps=steps)
    bus.emit(
        ORCHESTRATOR_ACTOR, "plan", "end",
        f"План готов: {len(steps)} шагов. Область охвата: {rationale.get('scope_notes', '')}",
        plan=plan.model_dump(mode="json"),
    )
    return plan


def _disease_ru(disease: str) -> str:
    return i18n.tr(disease, i18n.DISEASE_RU)


def _build_plain_summary(
    bus: EventBus,
    plan: Plan,
    comparisons: list,
    rankings: list,
    limitations: list[str],
) -> str:
    """Re-explains the already-computed findings in plain language for a non-expert reader.
    Deliberately fed only the derived results (not raw abstracts), so it can only rephrase
    conclusions that were already reached elsewhere in the pipeline -- it cannot introduce a
    new claim the technical sections don't already support."""
    bus.emit(ORCHESTRATOR_ACTOR, "report", "start", "Готовится резюме простыми словами")
    payload = {
        "diseases": [_disease_ru(d) for d in plan.diseases],
        "comparisons": [{"disease": _disease_ru(c.disease), "summary": c.summary} for c in comparisons],
        "rankings": [
            {"direction": s.direction, "disease": _disease_ru(s.disease), "score": s.score, "rationale": s.rationale}
            for s in rankings
        ],
        "limitations": limitations,
    }
    user_prompt = f"Исходный запрос пользователя: {plan.query}\n\nДанные для пересказа простыми словами (JSON):\n{payload}"
    result = llm_call_json(bus, ORCHESTRATOR_ACTOR, "report", PLAIN_SUMMARY_SYSTEM_PROMPT, user_prompt, label="plain_summary")
    summary = result.get("plain_summary", "").strip()
    bus.emit(ORCHESTRATOR_ACTOR, "report", "end", "Резюме простыми словами готово")
    return summary


def _report_markdown(plan: Plan, report: FinalReport) -> str:
    diseases_ru = ", ".join(_disease_ru(d) for d in plan.diseases)
    lines = [
        f"# Harness для анализа исследований в митохондриальной медицине -- мини-обзор",
        "",
        f"**Запрос:** {plan.query}",
        f"**Заболевания:** {diseases_ru}",
        f"**Временное окно:** с {plan.date_from} по настоящее время",
        f"**Сгенерировано:** {report.generated_at.isoformat()} UTC",
        "",
        "> Это автоматизированный инструмент исследовательского скрининга, а не систематический обзор "
        "и не клиническая рекомендация для конкретного пациента. См. раздел «Ограничения» ниже.",
        "",
    ]
    if report.plain_summary:
        lines.append("## Простыми словами")
        lines.append("")
        lines.append(report.plain_summary)
        lines.append("")
        lines.append(
            "*Дальше -- та же информация подробно, с научными терминами, ссылками на источники "
            "и цифрами, для тех, кому это важно проверить.*"
        )
        lines.append("")

    lines.append("## Обоснование плана")
    lines.append("")
    for step in plan.steps:
        lines.append(f"- **{step.step}** ({step.subagent}): {step.rationale}")
    lines.append("")

    lines.append("## Сравнение: митотерапия vs стандарт лечения")
    lines.append("")
    for c in report.comparisons:
        lines.append(f"### {_disease_ru(c.disease)}")
        lines.append("")
        lines.append(c.summary)
        lines.append("")
        lines.append(f"- Исследований митотерапии: {c.mitotherapy_n_studies} | Исследований стандарта лечения: {c.standard_n_studies}")
        if c.figure_path:
            rel = os.path.relpath(c.figure_path, REPORTS_DIR)
            lines.append(f"\n![Эффект по фазам -- {_disease_ru(c.disease)}]({Path(rel).as_posix()})\n")
            lines.append(f"*{i18n.CHART_GUIDE_EFFECT_BY_PHASE}*")
            lines.append("")

    lines.append("## Рейтинг направлений")
    lines.append("")
    if report.ranking_figure_path:
        rel = os.path.relpath(report.ranking_figure_path, REPORTS_DIR)
        lines.append(f"![Рейтинг направлений]({Path(rel).as_posix()})")
        lines.append("")
        lines.append(f"*{i18n.CHART_GUIDE_RANKING}*")
        lines.append("")
    lines.append("| Ранг | Направление | Заболевание | Балл | Доказательность | Обоснование |")
    lines.append("|---|---|---|---|---|---|")
    for s in report.rankings:
        lines.append(f"| {s.rank} | {s.direction} | {_disease_ru(s.disease)} | {s.score:.0f} | {s.evidence_level_summary} | {s.rationale} |")
    lines.append("")

    lines.append("## Таблица доказательств")
    lines.append("")
    lines.append("| Препарат | Заболевание | Рука | Фаза | n | Уровень доказательности | Эффект | Источник |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for s in report.studies:
        ident = s.pmid and f"PMID:{s.pmid}" or s.doi and f"DOI:{s.doi}" or s.nct_id or ""
        link = s.url or ""
        source_cell = f"[{ident}]({link})" if link else ident
        arm_ru = i18n.tr(s.arm.value, i18n.ARM_RU)
        study_type_ru = i18n.tr(s.evidence_level, i18n.STUDY_TYPE_RU) if s.evidence_level else "-"
        effect_ru = i18n.tr(s.effect_direction.value, i18n.EFFECT_DIRECTION_RU)
        lines.append(f"| {s.drug} | {_disease_ru(s.disease)} | {arm_ru} | {s.phase or '-'} | {s.n or '-'} | {study_type_ru} | {effect_ru} | {source_cell} |")
    lines.append("")

    lines.append("## Ограничения")
    lines.append("")
    for lim in report.limitations:
        lines.append(f"- {lim}")
    if report.review_issues:
        lines.append("")
        lines.append("### Замечания валидатора")
        lines.append("")
        for issue in report.review_issues:
            severity_ru = i18n.tr(issue.severity, i18n.SEVERITY_RU)
            lines.append(f"- **[{severity_ru}] {issue.issue_type}** ({issue.record_ref}): {issue.detail}")

    return "\n".join(lines)


def run_query(
    query: str,
    diseases: list[str],
    drug_classes: list[str],
    date_from: int,
    on_event=None,
) -> FinalReport:
    slug = _slugify(query)
    ts = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    log_path = LOGS_DIR / f"{ts}_{slug}.jsonl"
    bus = EventBus(log_path, on_event=on_event)

    try:
        plan = build_plan(bus, query, diseases, drug_classes, date_from)

        hits = literature_searcher.run(bus, plan)
        studies = data_extractor.run(bus, hits, diseases, drug_classes)
        kept_studies, review_issues = reviewer_validator.run(bus, studies)
        comparisons = comparator_analyst.run(bus, kept_studies, diseases)
        rankings, ranking_figure = perspective_scorer.run(bus, kept_studies, comparisons)

        limitations = [
            f"Окно поиска ограничено периодом с {date_from} по настоящее время и источниками Europe PMC + ClinicalTrials.gov v2; серая литература и не-англоязычные источники не учитывались.",
            "Это автоматизированный инструмент экспресс-скрининга, а не систематический обзор/метаанализ и не клиническая рекомендация для конкретного пациента.",
            f"{len(studies) - len(kept_studies)} из {len(studies)} извлечённых записей были отброшены после проверки цитирований (см. замечания валидатора).",
        ]

        plain_summary = _build_plain_summary(bus, plan, comparisons, rankings, limitations)

        bus.emit(ORCHESTRATOR_ACTOR, "report", "start", "Сборка итогового отчёта")
        report = FinalReport(
            query=query,
            plan=plan,
            studies=kept_studies,
            comparisons=comparisons,
            rankings=rankings,
            ranking_figure_path=ranking_figure,
            review_issues=review_issues,
            limitations=limitations,
            plain_summary=plain_summary,
        )
        report.markdown = _report_markdown(plan, report)

        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        report_path = REPORTS_DIR / f"{ts}_{slug}.md"
        report_path.write_text(report.markdown, encoding="utf-8")
        bus.emit(ORCHESTRATOR_ACTOR, "report", "end", f"Отчёт записан в {report_path}")
        return report
    finally:
        bus.close()
