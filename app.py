"""Streamlit UI: единое окно запроса, живая трасса шагов агента,
затем итоговый отчёт, графики и таблица доказательств.

Запуск: streamlit run app.py
"""
from __future__ import annotations

import os

import streamlit as st
from dotenv import load_dotenv

load_dotenv()  # before importing src.* -- src.llm reads LLM_* env vars lazily, but this keeps load order obvious

from src import config, i18n
from src.orchestrator import run_query
from src.schemas import AgentEvent

st.set_page_config(page_title="Harness для митохондриальной медицины", layout="wide")

PHASE_LABELS = {
    "plan": "1. Оркестратор: план",
    "search": "2. Поисковик литературы",
    "extract": "3. Экстрактор данных",
    "review": "4. Ревьюер-валидатор",
    "compare": "5. Аналитик-сравнитель",
    "score": "6. Оценщик перспективности",
    "report": "7. Оркестратор: сборка отчёта",
}
PHASE_ORDER = list(PHASE_LABELS.keys())

EVENT_ICON = {
    "start": "▶️",
    "skill_loaded": "\U0001f4d8",
    "tool_call": "\U0001f527",
    "llm_call": "\U0001f9e0",
    "issue": "⚠️",
    "end": "✅",
}


def _sidebar() -> dict:
    st.sidebar.header("Настройки")
    api_key_override = st.sidebar.text_input(
        "LLM_API_KEY (опционально)",
        type="password",
        help="Нужно только если ключ ещё не задан в .env. Хранится только в этой сессии браузера.",
    )
    if api_key_override:
        os.environ["LLM_API_KEY"] = api_key_override

    disease = st.sidebar.selectbox(
        "Заболевание в фокусе",
        options=config.DEFAULT_DISEASES,
        format_func=lambda d: i18n.tr(d, i18n.DISEASE_RU),
    )
    available_drug_classes = config.DISEASE_DRUG_CLASSES.get(disease, config.DEFAULT_DRUG_CLASSES)
    drug_classes = st.sidebar.multiselect(
        "Митохондриально-таргетные классы препаратов",
        options=available_drug_classes,
        default=available_drug_classes,
        format_func=lambda d: i18n.tr(d, i18n.DRUG_CLASS_RU),
        help="Список классов препаратов зависит от выбранного заболевания -- показаны только "
        "те направления, которые реально изучаются для него.",
    )
    date_from = st.sidebar.number_input("Временное окно: с какого года", min_value=2015, max_value=2026, value=config.DEFAULT_DATE_FROM)
    return {"diseases": [disease], "drug_classes": drug_classes, "date_from": int(date_from)}


def _render_event_detail(box, event: AgentEvent) -> None:
    """Разворачивает полную информацию о событии: промпт/ответ LLM, результаты поиска,
    содержимое скилла, полный план и т.д. -- по явному требованию видеть детальные логи,
    а не только однострочные сообщения."""
    data = event.data or {}

    if event.event_type == "skill_loaded" and data.get("content"):
        with box.expander(f"Текст скилла «{data.get('skill')}»"):
            st.markdown(data["content"])

    elif event.event_type == "llm_call":
        if data.get("stage") == "request":
            with box.expander("Промпт → LLM"):
                if data.get("system_prompt"):
                    st.caption("System prompt")
                    st.code(data["system_prompt"], language="markdown")
                if data.get("user_prompt"):
                    st.caption("User prompt")
                    st.code(data["user_prompt"], language="markdown")
        elif data.get("stage") == "response":
            with box.expander("Ответ LLM (структурированный)"):
                st.json(data.get("response"))

    elif event.event_type == "tool_call":
        if "hits" in data:
            label = f"Результаты поиска ({data.get('n_hits', len(data['hits']))})"
            with box.expander(label):
                if data["hits"]:
                    st.dataframe(data["hits"], hide_index=True, width="stretch")
                else:
                    st.caption("Ничего не найдено по этому запросу.")
        elif "resolved_title" in data or "extracted_title" in data:
            with box.expander("Результат проверки цитаты"):
                st.write(f"Извлечённое название: {data.get('extracted_title')}")
                if data.get("found"):
                    st.write(f"Найдено в источнике: {data.get('resolved_title')}")
                    if data.get("resolved_url"):
                        st.write(f"Ссылка: {data['resolved_url']}")
                else:
                    st.write("Не найдено при повторном запросе к источнику.")
        elif "stats" in data:
            with box.expander("Рассчитанная статистика"):
                st.json(data["stats"])

    elif event.event_type == "end" and event.phase == "plan" and data.get("plan"):
        with box.expander("Полный план исследования", expanded=True):
            for step in data["plan"]["steps"]:
                tools = ", ".join(step["tools"]) or "—"
                skills = ", ".join(step["skills"]) or "—"
                st.markdown(
                    f"**{step['step']}** ({step['subagent']}) -- инструменты: {tools}; скиллы: {skills}\n\n{step['rationale']}"
                )


def _render_trace(events: list[AgentEvent], containers: dict) -> None:
    """Добавляет очередное событие в статус-контейнер своей фазы, создавая его при первом обращении."""
    event = events[-1]
    phase = event.phase if event.phase in PHASE_LABELS else "plan"
    if phase not in containers:
        containers[phase] = st.status(PHASE_LABELS[phase], state="running", expanded=True)
    box = containers[phase]
    icon = EVENT_ICON.get(event.event_type, "•")
    box.write(f"{icon} `{event.actor}` -- {event.message}")
    _render_event_detail(box, event)
    if event.event_type == "end":
        box.update(label=f"{PHASE_LABELS[phase]} -- готово", state="complete")


def _run(query: str, diseases: list[str], drug_classes: list[str], date_from: int):
    containers: dict[str, object] = {}
    events: list[AgentEvent] = []

    st.subheader("Трассировка работы агента")
    current_agent_box = st.empty()

    def on_event(event: AgentEvent) -> None:
        events.append(event)
        info = i18n.AGENT_INFO.get(event.actor, {"name": event.actor, "role": ""})
        current_agent_box.info(f"\U0001f916 Сейчас работает: **{info['name']}** (`{event.actor}`) -- {info['role']}")
        _render_trace(events, containers)

    with st.spinner("Harness выполняется...", show_time=True):
        report = run_query(
            query=query,
            diseases=diseases,
            drug_classes=drug_classes,
            date_from=date_from,
            on_event=on_event,
        )
    return report


def _render_report(report) -> None:
    if report.plain_summary:
        st.subheader("\U0001f4a1 Простыми словами")
        with st.container(border=True):
            st.markdown(report.plain_summary)
        st.caption("Дальше -- та же информация подробно, с научными терминами и ссылками на источники.")
        st.divider()

    st.subheader("Рейтинг направлений")
    if report.rankings:
        if report.ranking_figure_path:
            st.image(report.ranking_figure_path)
            st.caption(i18n.CHART_GUIDE_RANKING)
        st.dataframe(
            [
                {
                    "Ранг": s.rank,
                    "Направление": s.direction,
                    "Заболевание": i18n.tr(s.disease, i18n.DISEASE_RU),
                    "Балл": round(s.score, 1),
                    "Доказательность": s.evidence_level_summary,
                }
                for s in report.rankings
            ],
            hide_index=True,
            width="stretch",
        )
    else:
        st.info("В извлечённых данных по этому запросу не найдено ни одного направления митотерапии.")

    cols = st.columns(max(1, len(report.comparisons)))
    for col, comparison in zip(cols, report.comparisons):
        with col:
            st.markdown(f"**{i18n.tr(comparison.disease, i18n.DISEASE_RU)}**")
            st.caption(comparison.summary)
            if comparison.figure_path:
                st.image(comparison.figure_path)
                st.caption(i18n.CHART_GUIDE_EFFECT_BY_PHASE)

    st.subheader("Таблица доказательств")
    st.dataframe(
        [
            {
                "Препарат": s.drug,
                "Заболевание": i18n.tr(s.disease, i18n.DISEASE_RU),
                "Рука": i18n.tr(s.arm.value, i18n.ARM_RU),
                "Фаза": s.phase,
                "n": s.n,
                "Уровень доказательности": i18n.tr(s.evidence_level, i18n.STUDY_TYPE_RU) if s.evidence_level else None,
                "Эффект": i18n.tr(s.effect_direction.value, i18n.EFFECT_DIRECTION_RU),
                "ID": s.pmid or s.doi or s.nct_id,
            }
            for s in report.studies
        ],
        hide_index=True,
        width="stretch",
    )

    if report.review_issues:
        with st.expander(f"Замечания валидатора ({len(report.review_issues)})"):
            for issue in report.review_issues:
                severity_ru = i18n.tr(issue.severity, i18n.SEVERITY_RU)
                st.write(f"**[{severity_ru}] {issue.issue_type}** ({issue.record_ref}): {issue.detail}")

    st.subheader("Полный отчёт")
    st.download_button("Скачать report.md", report.markdown, file_name="report.md", mime="text/markdown")
    with st.expander("Показать отчёт в Markdown", expanded=False):
        st.markdown(report.markdown)


_PIPELINE = [
    ("literature_searcher", ["pubmed.search_literature", "clinicaltrials.search_trials"], []),
    ("data_extractor", ["structured_parse"], ["clinical_outcome_extraction_rules", "evidence_level_scale"]),
    ("reviewer_validator", ["verify_citation"], ["citation_validation_checklist"]),
    ("comparator_analyst", ["sandbox.compare_arms", "sandbox.plot_effect_by_phase"], []),
    ("perspective_scorer", ["sandbox.plot_ranking"], ["perspective_criteria", "evidence_level_scale"]),
]

_ARROW = "<div style='text-align:center; font-size:1.4rem; margin:-0.4rem 0;'>⬇️</div>"


def _render_architecture() -> None:
    st.subheader("Как устроен Harness")
    st.caption(
        "Оркестратор строит план и делегирует шаги специализированным субагентам, подгружая "
        "каждому только нужные ему /skills. Порядок ниже -- фактический порядок выполнения в "
        "этом прототипе."
    )

    orch = i18n.AGENT_INFO["orchestrator"]
    with st.container(border=True):
        st.markdown(f"**\U0001f9ed {orch['name']}** -- построение плана")
        st.write(orch["role"])

    st.markdown(_ARROW, unsafe_allow_html=True)

    for i, (actor, tools, skills) in enumerate(_PIPELINE, start=1):
        info = i18n.AGENT_INFO[actor]
        with st.container(border=True):
            st.markdown(f"**{i}. {info['name']}** `{actor}`")
            st.write(info["role"])
            cols = st.columns(2)
            cols[0].caption(f"\U0001f527 Инструменты: {', '.join(tools) or '—'}")
            cols[1].caption(f"\U0001f4d8 Skills: {', '.join(skills) or '—'}")
        st.markdown(_ARROW, unsafe_allow_html=True)

    with st.container(border=True):
        st.markdown(f"**\U0001f9ed {orch['name']}** -- сборка отчёта")
        st.write(
            "Собирает итоговый Markdown-отчёт: рейтинг направлений, таблицу доказательств, "
            "графики сравнения и раздел с ограничениями."
        )

    st.info(
        "Порядок отличается от иллюстративного в задании (поиск → извлечение → сравнение → "
        "оценка → визуализация → отчёт): ревьюер-валидатор здесь идёт сразу после извлечения, "
        "чтобы сравнение и рейтинг строились уже на проверенном по цитированию наборе данных, "
        "а не опирались на записи, факт-чек которых происходит только постфактум."
    )


def main() -> None:
    st.title("Harness для анализа исследований в митохондриальной медицине")
    st.caption(
        "Прототип для исследовательского скрининга: не систематический обзор и не клиническая "
        "рекомендация для конкретного пациента. Фокус: митохондриально-таргетные препараты vs "
        "стандарт лечения."
    )

    settings = _sidebar()

    tab_run, tab_architecture = st.tabs(["Исследование", "Архитектура"])

    with tab_architecture:
        _render_architecture()

    with tab_run:
        query = st.text_area(
            "Исследовательский запрос",
            value=config.EXAMPLE_QUERIES[0],
            height=90,
        )
        example = st.selectbox("...или выберите пример запроса", ["(свой запрос, используйте поле выше)"] + config.EXAMPLE_QUERIES)
        if example != "(свой запрос, используйте поле выше)":
            query = example

        if st.button("Запустить harness", type="primary", disabled=not query.strip()):
            if not os.environ.get("LLM_API_KEY"):
                st.error("API-ключ не найден. Укажите LLM_API_KEY в файле .env или вставьте его в сайдбаре.")
                st.stop()
            report = _run(query, settings["diseases"], settings["drug_classes"], settings["date_from"])
            st.divider()
            _render_report(report)


if __name__ == "__main__":
    main()
