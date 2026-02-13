# Dot Context Diff (vs existing snapshot/note set)

## Scope
- Compared against: `context_snapshot_full.md`, `context_snapshot.md`, `data/dot_fee_instructions.md`, `data/dot_org_instructions_v2.md`.
- New pack: `artifacts/dot_context_updated.md`.

## What changed

### Kept (canonical invariants)
- Strict AND fee matching over all constrained fields.
- Null/empty-list wildcard semantics.
- Mandatory monthly tier filter for month/date fee questions.
- `capture_delay_bucket` usage (no raw remap).
- `intracountry = (issuing_country == acquirer_country)`.
- Fee formula and specificity policy (`max specificity`, tie => average).
- No-match transaction fee is `0` (do not drop transaction).
- "Applicable fee IDs" is union over actual transactions.
- Fraud rate vs count disambiguation.
- `Not Applicable` policy for unsupported concepts.

### Added
- Top-of-file "Do this first" routing checklist:
  - classify question type,
  - pick SQL template,
  - output `FINAL_ANSWER` only.
- Four compact SQL templates:
  - monthly tiers lookup,
  - total fees with specificity + fee=0 handling,
  - applicable fee IDs union for merchant/date,
  - fraud rate by group.
- Explicit "common failure modes" section (monthly tiers, capture delay bucket, supersets).

### Removed to reduce timeout risk
- Long business prose and KPI narratives from table descriptions.
- Repeated/overlapping rules across multiple note sections.
- Large column-by-column commentary blocks not needed for task execution.
- Extra optimization/background text not required for correctness.

## Resulting behavior target
- Smaller context payload with only execution-critical rules.
- Lower prompt/context bloat while preserving canonical solver semantics.
