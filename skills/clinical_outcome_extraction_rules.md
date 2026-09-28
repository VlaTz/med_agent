---
name: clinical_outcome_extraction_rules
used_by: [data_extractor]
---

# Clinical outcome extraction rules

You are converting one abstract or registry entry into a single `StudyRecord`.
Extract only what the source text actually states.

## Field rules
- **drug**: the specific compound/intervention name as written (e.g. "MitoQ", "SS-31/elamipretide", "urolithin A", "levodopa"). Do not normalize brand vs generic names into each other.
- **arm**: classify the *specific intervention studied in this record* as:
  - `mitotherapy` -- mitochondria-targeted antioxidant, mitophagy/biogenesis modulator, mtDNA gene therapy, or mitochondrial transplantation.
  - `standard_of_care` -- the established, guideline-listed treatment for that disease (e.g. levodopa for Parkinson's, ACE inhibitors/beta-blockers for heart failure).
  - `combination` -- mitotherapy add-on to standard of care, studied together.
  - `placebo` -- placebo/vehicle-only arm reported as its own comparator.
- **outcome_measure**: name the primary endpoint as stated (e.g. "UPDRS-III score change at 12 weeks", "visual acuity, LogMAR"). If only a secondary endpoint is reported, use it but note this in `notes`.
- **effect_direction**: `improved` only if the result favors the intervention arm on its stated primary/reported endpoint with a stated or implied statistical comparison. Use `no_effect` for a reported null result, `worse` for a result favoring the comparator, `mixed` when primary and secondary endpoints disagree, `unknown` when the source has no results yet (e.g. a registry entry pre-completion).
- **effect_magnitude**: copy the reported number/statistic verbatim (e.g. "-4.2 points (95% CI -7.1 to -1.3), p=0.01"). Never compute or estimate a magnitude that is not stated.
- **n**: total enrolled/analyzed sample size for the arm or study, whichever the source reports at that level. If only combined enrollment is given, use that and note it applies to the whole study, not one arm.
- **phase**: use ClinicalTrials.gov phase vocabulary (`Preclinical`, `I`, `I/II`, `II`, `II/III`, `III`, `IV`, `N/A`). Preclinical/animal work is always `Preclinical`.

## Named-drug exceptions
- **Idebenone for LHON specifically**: idebenone (brand Raxone) is EMA-approved as the standard treatment for LHON. When `disease` is LHON, classify idebenone as `standard_of_care`, not `mitotherapy`, even though it is mechanistically a mitochondria-targeted antioxidant. For any other disease, classify idebenone as `mitotherapy`. Always apply this consistently -- do not let it vary record-to-record for the same disease.

## Hard constraints
- If a field is not stated in the source, leave it null. Do not fill gaps with typical/expected values from general knowledge.
- Every record must carry at least one identifier (`pmid`, `doi`, or `nct_id`) copied from the source hit -- never fabricate one.
- One abstract describing two arms (e.g. drug vs placebo within one RCT) becomes two `StudyRecord`s sharing the same identifier, one per `arm`.
