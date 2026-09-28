"""Tool: isolated calculation + charting sandbox.

Keeps numeric aggregation and matplotlib rendering out of subagent/LLM code
paths -- the analyst and scorer subagents call these pure functions instead of
asking the LLM to "do math".
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from src import i18n
from src.schemas import Arm, EffectDirection, StudyRecord

FIGURES_DIR = Path(__file__).resolve().parent.parent.parent / "outputs" / "figures"

_EVIDENCE_ORDER = [
    "rct_double_blind",
    "rct_open_label",
    "cohort",
    "case_series",
    "registered_trial",
    "preclinical",
    "other",
]

_EFFECT_SCORE = {
    EffectDirection.IMPROVED: 1.0,
    EffectDirection.MIXED: 0.5,
    EffectDirection.NO_EFFECT: 0.0,
    EffectDirection.WORSE: -1.0,
    EffectDirection.UNKNOWN: 0.0,
}


def arm_stats(records: list[StudyRecord], arm: Arm) -> dict:
    subset = [r for r in records if r.arm == arm]
    if not subset:
        return {"n_studies": 0, "total_n": 0, "mean_effect_score": 0.0, "evidence_mix": {}}
    total_n = sum(r.n or 0 for r in subset)
    mean_effect = sum(_EFFECT_SCORE.get(r.effect_direction, 0.0) for r in subset) / len(subset)
    evidence_mix = dict(Counter(r.study_type.value for r in subset))
    return {
        "n_studies": len(subset),
        "total_n": total_n,
        "mean_effect_score": round(mean_effect, 3),
        "evidence_mix": evidence_mix,
    }


def compare_arms(records: list[StudyRecord]) -> dict:
    return {
        "mitotherapy": arm_stats(records, Arm.MITOTHERAPY),
        "standard_of_care": arm_stats(records, Arm.STANDARD_OF_CARE),
        "combination": arm_stats(records, Arm.COMBINATION),
    }


def plot_effect_by_phase(records: list[StudyRecord], disease: str, filename: str) -> str:
    """Scatter of studies: phase (x) vs effect score (y), split mitotherapy vs standard, sized by n."""
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    phases = ["Preclinical", "I", "II", "III", "IV", "N/A"]
    phase_index = {p: i for i, p in enumerate(phases)}

    fig, ax = plt.subplots(figsize=(8, 5))
    colors = {Arm.MITOTHERAPY: "#2E86AB", Arm.STANDARD_OF_CARE: "#C73E1D", Arm.COMBINATION: "#6A994E"}
    for arm, color in colors.items():
        subset = [r for r in records if r.arm == arm]
        if not subset:
            continue
        xs = [phase_index.get(r.phase or "N/A", phase_index["N/A"]) for r in subset]
        ys = [_EFFECT_SCORE.get(r.effect_direction, 0.0) for r in subset]
        sizes = [max((r.n or 10), 10) for r in subset]
        ax.scatter(xs, ys, s=sizes, alpha=0.6, color=color, label=i18n.tr(arm.value, i18n.ARM_RU))

    ax.set_xticks(range(len(phases)))
    ax.set_xticklabels(phases)
    ax.set_yticks([-1, -0.5, 0, 0.5, 1])
    ax.set_yticklabels(["ухудшение", "смешанный-", "без эффекта", "смешанный+", "улучшение"])
    ax.set_xlabel("Фаза исследования")
    ax.set_ylabel("Заявленное направление эффекта")
    ax.set_title(f"Митотерапия vs стандарт лечения -- {disease}\n(размер маркера ~ размер выборки n)")
    ax.legend(loc="lower right")
    ax.grid(alpha=0.3)
    fig.tight_layout()

    out_path = FIGURES_DIR / filename
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    return str(out_path)


def plot_ranking(directions: list[str], scores: list[float], filename: str) -> str:
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    order = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
    directions = [directions[i] for i in order]
    scores = [scores[i] for i in order]

    fig, ax = plt.subplots(figsize=(10, max(3, 0.5 * len(directions))))
    colors = plt.cm.RdYlGn([s / 100 for s in scores])
    ax.barh(directions, scores, color=colors)
    ax.set_xlabel("Балл перспективности (0-100)")
    ax.set_title("Рейтинг направлений: митотерапия vs стандарт лечения", fontsize=12)
    ax.invert_yaxis()
    fig.tight_layout()

    out_path = FIGURES_DIR / filename
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    return str(out_path)
