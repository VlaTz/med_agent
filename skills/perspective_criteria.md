---
name: perspective_criteria
used_by: [perspective_scorer]
---

# Perspectiveness scoring rubric

Score each mitotherapy direction (drug or drug-class x disease pair) from 0-100
using the weighted criteria below. Compute a sub-score 0-100 for each criterion,
then combine with the given weights. Show your arithmetic in `rationale`.

| Criterion | Weight | How to score |
|---|---|---|
| Evidence strength | 40% | Based on the mix of `evidence_level` across that direction's records: mostly `rct_double_blind`/`rct_open_label` -> 80-100; mostly `cohort`/`case_series` -> 40-70; mostly `preclinical`/`registered_trial` with no results -> 0-35. |
| Effect consistency & magnitude | 25% | Share of records with `effect_direction=improved` vs `worse`/`no_effect`, weighted by how many report a magnitude at all. Mixed or null results across most records caps this at 40. |
| Safety/tolerability signal | 15% | Presence of explicit adverse-event or tolerability statements in `notes`/outcome text. No safety data reported at all -> do not exceed 50 (absence of evidence is not evidence of safety). |
| Pipeline momentum | 20% | Count and recency (within the 3-5y window) of registered/ongoing trials for that direction. Zero recent trials -> low score even if older evidence is positive. |

## Rules
- A direction backed by a single small case series, however positive, cannot score above 55 overall -- cap it there regardless of the weighted sum, and say so in `rationale`.
- If mitotherapy for a direction has **no** standard-of-care comparator data in the dataset, state this explicitly in `rationale` and do not claim superiority over standard treatment.
- Rank directions strictly by final score, highest first. Ties break toward the direction with more total studies (`mitotherapy_n_studies` from the comparison step).
- Always name at least one "least perspective" direction when the input contains more than one direction -- do not produce an all-positive ranking.
