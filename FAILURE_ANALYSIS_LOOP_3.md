# Failure Analysis — Loop 3

## Score Summary

| Loop | Completed | Score | Accuracy |
|------|-----------|-------|----------|
| 2    | 10/10     | 4/10  | 40%      |
| 3    | 7/10      | 3/7   | 43%      |

## Per-Question Delta (Loop 2 → Loop 3)

| QID  | Diff | L2 Score | L3 Score | L2 Error        | L3 Error      | L2 Lat | L3 Lat | Change         |
|------|------|----------|----------|-----------------|---------------|--------|--------|----------------|
| 5    | easy | 1        | 1        | —               | —             | 20s    | 21s    | Same           |
| 49   | easy | 0        | 0        | wrong_answer    | wrong_answer  | 24s    | 27s    | Same           |
| 70   | easy | 1        | 1        | —               | —             | 9s     | 6s     | Same           |
| 1273 | hard | 1        | 0        | —               | wrong_answer  | 56s    | 45s    | **REGRESSION** |
| 1305 | hard | 0        | 0        | timeout (600s)  | wrong_answer  | 600s   | 74s    | No timeout     |
| 1464 | hard | 1        | 1        | —               | —             | 67s    | 33s    | Faster         |
| 1681 | hard | 0        | 0        | superset (47)   | subset (1)    | 79s    | 287s   | Tier applied   |
| 1753 | hard | 0        | —        | superset (47)   | not reached   | 240s   | —      | —              |
| 1871 | hard | 0        | —        | timeout (600s)  | not reached   | 600s   | —      | —              |
| 2697 | hard | 0        | —        | timeout (600s)  | not reached   | 602s   | —      | —              |

## Detailed Failure Analysis

### Q49 — ip_country fraud (PERSISTENT)
- **Question**: "top country (ip_country) for fraud?" Options: NL, BE, ES, FR
- **Dot answer**: A. NL (2,955 fraudulent txns)
- **Ground truth**: B. BE
- **Root cause**: Dot queries fraud by ip_country but gets NL. Either:
  a) Dot is caching stale SQL results, or
  b) Dot is actually grouping by a different field, or
  c) The SQL it's running has a subtle filter that changes the ranking
- **Category**: Reasoning misinterpretation — Dot may be counting differently
- **Fix needed**: Investigate whether Dot's SQL is correct; might need to verify by running the query ourselves

### Q1273 — Average fee REGRESSION
- **Question**: "average fee for GlobalCard credit, txn value 10 EUR"
- **Loop 2**: 0.120132 (CORRECT)
- **Loop 3**: 0.117667 (WRONG)
- **Root cause**: The updated fees table description's SQL join pattern introduced confusion. Dot now matches a different set of fee rules. The `is_credit` type casting guidance or the list membership LIKE pattern may have caused Dot to incorrectly filter rules.
- **Category**: Ambiguous table description (caused by our changes)
- **Fix needed**: Revert prescriptive SQL patterns from fees table description. Keep descriptions semantic, not syntactic.

### Q1305 — Average fee (IMPROVED — no longer timeout)
- **Question**: "average fee for account type H, MCC 5812, GlobalCard, txn 10 EUR"
- **Loop 2**: Timeout (600s)
- **Loop 3**: 0.111667 (wrong, expected 0.123217), completed in 74s
- **Root cause**: Dot now completes the query (performance improvement) but gets wrong result. Likely same list membership matching issue as Q1273 — matching wrong number of fee rules.
- **Category**: List membership matching error
- **Fix needed**: Same as Q1273 — fix list membership matching guidance

### Q1681 — Fee IDs (CHANGED — superset→subset)
- **Question**: "Fee IDs for Belles_cookbook_store on Jan 10, 2023"
- **Loop 2**: 47 IDs (superset, expected 10)
- **Loop 3**: 1 ID (subset, expected 10)
- **Dot trace**: "intracountry column doesn't exist in the actual table" — Dot hit a column error and fell back to overly restrictive matching
- **Root cause**:
  1. Monthly tier filter now applied (good — volume_tier="100k-1m" matches)
  2. But intracountry matching failed causing SQL errors
  3. Only 1 rule survived the broken matching
- **Category**: Table description ambiguity causing SQL errors
- **Fix needed**: Clarify intracountry column existence and type. Remove prescriptive SQL that confuses Dot.

## Root Cause Summary

| Category | QIDs | Description |
|----------|------|-------------|
| Prescriptive SQL patterns causing confusion | 1273, 1305, 1681 | The updated fees table description with SQL join patterns confused Dot's own query generation |
| Persistent reasoning error | 49 | ip_country fraud grouping — unchanged by context updates |

## Key Insight

**The fees table description update HURT more than it helped.** The SQL JOIN pattern we added conflicted with how Dot naturally generates SQL. We need to:
1. REVERT the prescriptive SQL from the fees table description
2. Keep descriptions SEMANTIC (what the data means) not SYNTACTIC (how to write SQL)
3. Keep the monthly_merchant_stats reference and relationship (those are semantic improvements)
