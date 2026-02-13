# Dot Context Diff v2.1 (vs previous `artifacts/dot_context_updated_v2.md`)

## What changed
1. Added explicit fee-rule selection policy:
   - keep only max-specificity matching rules
   - if tie at max specificity, average tied fees
2. Added mandatory fee-join statement:
   - always join `payments -> merchant_data` for `account_type`, `merchant_category_code`, `capture_delay_bucket`
3. Added month-derivation rule for monthly tiers:
   - for month-based fee questions with only `day_of_year`, derive month first before tier lookup
4. Added fee-change wording semantics:
   - "relative fee" / "rate" changed to `X` => set `fees.rate = X` only
   - "fixed fee" changed => change `fixed_amount`
5. Tightened email empty handling:
   - treat NULL and `TRIM(email_address) = ''` as empty
6. Added anti-superset fee-ID guardrails:
   - require per-ID `supporting_txn_count > 0` from transaction-level matches
   - forbid merchant-only fee-ID derivation
   - applicable-ID template now explicitly groups by ID and filters to transaction-supported IDs

## Why
- These are the remaining high-impact fee-engine ambiguities that can shift hard fee totals and delta answers.
- Instructions were kept concise to reduce timeout risk while preserving required invariants.

## Not changed
- No solver logic or runner behavior.
- No Dot upload actions were triggered.
