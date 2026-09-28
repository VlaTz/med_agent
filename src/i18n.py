"""Russian display labels for the English-language vocabulary the pipeline
reasons over internally (Pydantic enums, config.py scope strings).

The schema/config layer stays in English on purpose: StudyType/Arm/
EffectDirection values are matched against LLM output and against each other
(e.g. disease-name filtering in comparator_analyst), so changing them risks
silently breaking that matching. This module only maps values to Russian
labels at render time, for the UI and the Markdown report.
"""
from __future__ import annotations

ARM_RU = {
    "mitotherapy": "митотерапия",
    "standard_of_care": "стандарт лечения",
    "combination": "комбинация",
    "placebo": "плацебо",
}

STUDY_TYPE_RU = {
    "rct_double_blind": "РКИ, двойное слепое",
    "rct_open_label": "РКИ, открытое",
    "cohort": "когортное",
    "case_series": "серия случаев",
    "preclinical": "доклиника",
    "registered_trial": "зарегистрировано (без результатов)",
    "other": "другое",
}

EFFECT_DIRECTION_RU = {
    "improved": "улучшение",
    "no_effect": "без эффекта",
    "worse": "ухудшение",
    "mixed": "смешанный",
    "unknown": "неизвестно",
}

SEVERITY_RU = {
    "low": "низкая",
    "medium": "средняя",
    "high": "высокая",
}

DISEASE_RU = {
    "Parkinson's disease": "болезнь Паркинсона",
    "Leber hereditary optic neuropathy (LHON)": "наследственная оптическая нейропатия Лебера (LHON)",
}

DRUG_CLASS_RU = {
    "mitochondria-targeted antioxidants (MitoQ, SkQ1, elamipretide/SS-31)": "митохондриально-таргетные антиоксиданты (MitoQ, SkQ1, эламипретид/SS-31)",
    "mitophagy/biogenesis modulators (urolithin A, NAD+ precursors)": "модуляторы биогенеза и митофагии (уролитин A, NAD+-прекурсоры)",
    "mtDNA gene therapy / mitochondrial replacement": "генная терапия мтДНК / замещение митохондрий",
}


def tr(value: str | None, mapping: dict[str, str]) -> str | None:
    """Look up a Russian label; falls back to the original value if unmapped
    (e.g. a disease/drug name the model produced that isn't in our fixed scope)."""
    if value is None:
        return value
    return mapping.get(value, value)


CHART_GUIDE_EFFECT_BY_PHASE = (
    "Как читать этот график: по горизонтали -- фаза исследования (Preclinical = не на людях, "
    "а в лаборатории/на животных; I-IV -- фазы клинических испытаний на людях; N/A -- обычно "
    "наблюдательные/когортные данные по уже применяемому лечению, без формальной фазы). "
    "По вертикали -- какое направление эффекта заявлено в первоисточнике: это категория "
    "(ухудшение / без эффекта / улучшение и т.д.), а не сила эффекта -- шкала не показывает, "
    "*насколько* сильно исследование улучшило или ухудшило состояние. Размер точки ~ размер "
    "выборки (n): чем крупнее точка, тем больше участников. Цвет -- рука исследования: синий = "
    "митотерапия, оранжевый = стандарт лечения, зелёный = комбинация."
)

CHART_GUIDE_RANKING = (
    "Как читать этот график: каждый столбик -- одно направление терапии (препарат + "
    "заболевание), балл 0-100 рассчитан по фиксированной эвристике (сила доказательств, "
    "устойчивость эффекта, сигналы безопасности, активность исследовательского пайплайна -- "
    "см. skills/perspective_criteria.md). Это не официальный рейтинг и не показатель "
    "клинической эффективности сам по себе, а объяснимая (можно посмотреть обоснование по "
    "каждому баллу) оценка того, насколько многообещающе выглядит направление именно в этом "
    "наборе данных."
)

AGENT_INFO = {
    "orchestrator": {
        "name": "Оркестратор",
        "role": (
            "Разбирает запрос пользователя, строит план исследования (поиск → извлечение → "
            "ревью → сравнение → оценка → отчёт), решает, какие субагенты и /skills нужны для "
            "конкретного запроса, распределяет задачи и в конце собирает итоговый отчёт."
        ),
    },
    "literature_searcher": {
        "name": "Поисковик литературы",
        "role": (
            "Превращает область запроса (заболевания, классы препаратов) в конкретные поисковые "
            "запросы и ищет публикации в Europe PMC и исследования в ClinicalTrials.gov."
        ),
    },
    "data_extractor": {
        "name": "Экстрактор данных",
        "role": (
            "Извлекает из найденных абстрактов/карточек исследований структурированные записи: "
            "препарат, мишень, заболевание, фаза, n, тип исследования, исход, эффект, уровень "
            "доказательности."
        ),
    },
    "reviewer_validator": {
        "name": "Ревьюер-валидатор",
        "role": (
            "Повторно проверяет каждую цитату по исходным API (PubMed/ClinicalTrials.gov), "
            "ищет неподтверждённые числа и необоснованные формулировки; записи с серьёзными "
            "замечаниями исключаются из дальнейшего анализа."
        ),
    },
    "comparator_analyst": {
        "name": "Аналитик-сравнитель",
        "role": (
            "Считает агрегированную статистику по каждому заболеванию и сравнивает "
            "митохондриально-таргетную терапию со стандартом лечения, строит график."
        ),
    },
    "perspective_scorer": {
        "name": "Оценщик перспективности",
        "role": (
            "Ранжирует направления терапии по перспективности на основе силы доказательств, "
            "устойчивости эффекта, сигналов безопасности и активности исследовательского пайплайна."
        ),
    },
}


RU_OUTPUT_INSTRUCTION = (
    "\n\nWrite every free-text/narrative value (not JSON keys, not the fixed "
    "enumerated values you were told to use) in Russian."
)
