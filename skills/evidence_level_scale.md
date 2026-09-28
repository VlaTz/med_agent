---
name: evidence_level_scale
used_by: [data_extractor, perspective_scorer]
---

# Evidence level scale

Assign exactly one level to every study/trial record, from strongest to weakest.
Base the assignment on the *design* reported in the abstract/registry entry, not on
the outcome or on how promising the drug sounds.

| Level | Label | Criteria |
|---|---|---|
| 1 | `rct_double_blind` | Randomized, double-blind (or double-dummy), placebo- or active-controlled, published results |
| 2 | `rct_open_label` | Randomized, open-label or single-blind, published results |
| 3 | `cohort` | Prospective or retrospective cohort, non-randomized comparison group |
| 4 | `case_series` | Case series / case report / single-arm open trial with published results |
| 5 | `registered_trial` | ClinicalTrials.gov entry with no published results yet (recruiting, active, or completed-no-results) |
| 6 | `preclinical` | Animal model, cell culture, or ex vivo only |
| 7 | `other` | Anything that does not fit above (reviews, editorials, protocols without data) |

## Rules
- Set the `evidence_level` field to the string in the **Label** column (e.g. `case_series`), never the number in the **Level** column. `evidence_level` is always a string, never an integer.
- If the abstract does not state blinding explicitly but says "randomized controlled trial", default to `rct_open_label`, not `rct_double_blind` -- do not assume blinding.
- A ClinicalTrials.gov record with a `results` section populated is **not** `registered_trial`; extract it as whatever design it reports (usually `rct_double_blind` or `rct_open_label`).
- Never invent a level higher than what the source text supports. When genuinely ambiguous, choose the lower (weaker) level and note the ambiguity in `notes`.
