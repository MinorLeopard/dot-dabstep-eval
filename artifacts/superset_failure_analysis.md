# Superset Failure Analysis (Dot vs Local)

## Evidence from historical Dot runs
- Run `artifacts/runs/20260212_103707_e8baeb/results.jsonl`
  - `Q1681` (`For the 10th of 2023... applicable Fee IDs for Belles_cookbook_store`) => `superset_answer`
  - `Q1753` (`applicable fee IDs ... in March 2023`) => `superset_answer`
- Both questions returned the same 47 IDs, while ground truth differs (`10` IDs for Q1681 and `34` IDs for Q1753).

## Why this is a superset bug
- Returned IDs were derived from merchant+tier constraints only.
- Transaction-level constraints were not enforced per transaction:
  - `payments.card_scheme`
  - `payments.is_credit`
  - `payments.aci`
  - `intracountry`
- Day-specific window was effectively treated like a broad merchant/month filter.

## Fix strategy applied
1. Added prompt guardrail for applicable Fee ID questions:
   - exact requested time window first
   - strict per-transaction matching
   - keep only IDs with `supporting_txn_count > 0`
2. Added context note guardrails with the same rules and SQL template hints.
3. Added dedicated anti-superset instruction pack for Dot uploads.

## Expected impact
- Prevent merchant-level fee ID supersets.
- Reduce repeated “same large list” outputs across day/month questions.
- Align Dot behavior with local deterministic solver semantics.

## Post-patch sanity check
- Run `results/20260213_135449_b56fa0.jsonl` (`Q1681` only):
  - Prompt included `FEE-ID ANTI-SUPERSET CHECK`.
  - Output changed from historical supersets to a near-ground-truth subset (`9` IDs vs expected `10`), indicating the superset failure mode was reduced.
