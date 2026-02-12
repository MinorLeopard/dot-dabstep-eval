# Delta Report — Loop 4 vs Loop 2 (Baseline)

## Score Summary

| Loop | Completed | Score | Accuracy |
|------|-----------|-------|----------|
| 2    | 10/10     | 4/10  | 40%      |
| 3    | 7/10      | 3/7   | 43%      |
| 4    | 10/10     | 4/10  | 40%      |

## Per-Question Comparison

| QID  | Diff | L2 Score | L4 Score | L4 Error     | L4 Lat  | Change from L2           |
|------|------|----------|----------|--------------|---------|--------------------------|
| 5    | easy | 1        | 1        | —            | 19s     | Same                     |
| 49   | easy | 0        | 0        | wrong_answer | 18s     | Same (NL vs BE)          |
| 70   | easy | 1        | 1        | —            | 6s      | Same                     |
| 1273 | hard | 1        | 0        | wrong_answer | 44s     | **REGRESSION** (L3 broke it) |
| 1305 | hard | 0        | **1**    | —            | 163s    | **NEW WIN** (was timeout) |
| 1464 | hard | 1        | 1        | —            | 37s     | Same                     |
| 1681 | hard | 0        | 0        | client_error | 1201s   | Still timeout            |
| 1753 | hard | 0        | 0        | superset     | 98s     | Changed: superset 47→47 (was 47) |
| 1871 | hard | 0        | 0        | wrong_answer | 856s    | **No longer timeout** (was 600s) |
| 2697 | hard | 0        | 0        | wrong_answer | 305s    | **No longer timeout** (was 600s) |

## Gains
- **Q1305**: Timeout → Correct (+1). Fee matching with H/MCC/GlobalCard now works.
- **Q1871**: Timeout → Completes (wrong answer). Reduced from 600s hard timeout to 856s with answer.
- **Q2697**: Timeout → Completes (wrong answer). Reduced from 600s hard timeout to 305s with answer.

## Losses
- **Q1273**: Was correct in L2 (0.120132), now 0.117667 since L3 context changes.

## Net: +0 (gained Q1305, lost Q1273), but 2 fewer timeouts

## Detailed Failure Analysis

### Q1273 — Average fee regression (PERSISTENT since L3)
- **Question**: "For credit transactions, average fee GlobalCard would charge for 10 EUR?"
- **Dot answer**: 0.117667 (wrong, expected 0.120132)
- **Root cause**: is_credit matching changed after context updates. Dot likely filters `is_credit = 'true'` (exact) instead of `(is_credit IS NULL OR is_credit = 'true')`, OR includes `is_credit = 'false'` rules.
- **Fix idea**: Clarify in org note that for credit transactions, matching should include rules where is_credit IS NULL (wildcard) or is_credit = 'true'.

### Q49 — ip_country fraud (PERSISTENT across all loops)
- **Question**: "Top country (ip_country) for fraud? A. NL, B. BE, C. ES, D. FR"
- **Dot answer**: A. NL (2,955 txns)
- **Root cause**: Dot consistently counts fraud by ip_country and gets NL. The ground truth is BE. This might be: (a) Dot grouping by wrong field, (b) different fraud definition, (c) filter applied.
- **Fix idea**: Investigate — likely a Dot internal SQL issue beyond our control.

### Q1753 — Superset (47 IDs vs 34 expected)
- **Dot's 47 IDs**: ALL 34 expected IDs are included, plus 13 extra
- **Extra IDs**: 65, 80, 183, 304, 498, 631, 678, 849, 861, 871, 892, 924, 942
- **Root cause**: Dot misses one matching criterion (capture_delay, intracountry, or is_credit)
- **Fix idea**: Strengthen fee matching guidance — ensure ALL criteria are checked

### Q1681 — Timeout (1201s, both attempts)
- **Question**: Fee IDs for Belles_cookbook_store on Jan 10, 2023
- **Root cause**: Dot's SQL is too complex or iterative, causing server timeout
- **Fix idea**: Performance guidance already in org note. May be a Dot-side issue.

### Q1871 — Wrong delta (-0.80054 vs -0.94000)
- **Question**: Delta if fee ID=384 rate changed to 1 for Belles_cookbook_store in Jan 2023
- **Root cause**: Complex multi-step computation — Dot computes a close but incorrect delta
- **Fix idea**: Limited — this requires precise fee matching + counterfactual calculation

### Q2697 — Wrong ACI (F:72.62 vs E:13.57)
- **Question**: Best ACI for lowest fees on fraudulent txns for Belles_cookbook_store in Jan
- **Dot response**: 6587 chars of self-doubt. Identified E as lowest (16.63) but chose F because "recurring billing doesn't make sense for a bookstore."
- **Root cause**: Dot applied business judgment instead of pure math
- **Fix idea**: Add guidance: "Always choose the mathematical minimum. Do not apply business judgment."

## Improvement Opportunities for Loop 5

1. **Fix is_credit matching** — Add explicit rule: "For credit transactions, match is_credit IS NULL OR is_credit = 'true'. For debit, match IS NULL OR 'false'."
2. **Anti-business-judgment rule** — "When asked for lowest/cheapest, pick the mathematical minimum."
3. **Strengthen all-criteria matching** — Remind that ALL non-null criteria must match.
