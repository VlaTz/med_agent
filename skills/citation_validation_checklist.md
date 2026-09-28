---
name: citation_validation_checklist
used_by: [reviewer_validator]
---

# Citation & fact validation checklist

You receive: the full list of extracted `StudyRecord`s, the re-lookup result for
each identifier (from `verify_citation`), and the draft comparison/ranking
outputs. For every record, check all of the following and emit a `ReviewIssue`
for anything that fails.

1. **Identifier resolves.** The `verify_citation` re-lookup for this record's
   pmid/doi/nct_id returned a real hit. If it returned nothing -> `issue_type:
   unverifiable_citation`, `severity: high`.
2. **Title matches.** The record's `title` is a close match (allow minor
   truncation/formatting differences) to the title returned by the re-lookup.
   Mismatch -> `issue_type: number_mismatch`, `severity: high` (this usually
   means the wrong ID got attached during extraction).
3. **Numbers are traceable.** `n` and `effect_magnitude`, if present, must be
   plausibly derivable from the abstract/registry text you were given, not
   invented. If you cannot locate the number in source text -> `issue_type:
   number_mismatch`, `severity: medium`.
4. **No unsupported superlatives.** Downstream ranking/report text must not
   claim a drug is "proven", "safe", "approved", or "superior to standard of
   care" unless the underlying records directly support that claim at the
   stated evidence level. Flag such language -> `issue_type:
   hallucinated_claim`, `severity: medium`.
5. **Disease/drug scope.** Confirm the record's disease and drug actually
   belong to the requested query scope; anything off-scope that slipped through
   search/extraction -> `issue_type: other`, `severity: low`.

## Output discipline
- Do not silently drop flagged records -- pass every `ReviewIssue` through so
  the final report can show them as explicit limitations.
- A `high` severity issue on a record means that record must be excluded from
  the final ranking and report body (it may still be listed under
  limitations as "excluded, unverifiable").
