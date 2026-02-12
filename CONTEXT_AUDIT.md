# Context Audit — Pre-Loop 4

## Issues Found

### 1. Fees Table Description — Prescriptive SQL Patterns HARMFUL
The "SQL Join Pattern for Fee Matching" section contains LIKE-based matching examples:
```sql
f.account_type = '[]' OR CAST(f.account_type AS TEXT) LIKE '%' || 'R' || '%'
```
**Problem**: This LIKE pattern is unreliable (e.g., `'%R%'` matches unintended strings) and conflicts with how Dot naturally generates SQL. This caused Q1273 REGRESSION (was correct in loop 2, wrong in loop 3).

**Fix**: Remove prescriptive SQL. Keep only semantic matching rules.

### 2. Fees intracountry Column — Dot Thinks It Doesn't Exist
Q1681 trace: "intracountry column doesn't exist in the actual table"
The column DOES exist (DOUBLE type). The prescriptive SQL pattern may have confused Dot about column names.

**Fix**: Simplify the column comment. Ensure Dot knows intracountry is a real column.

### 3. is_credit Type Mismatch
fees.is_credit is VARCHAR ("true"/"false"/NULL), payments.is_credit is BOOLEAN.
Column user_comment on fees.is_credit mentions complex casting. This may confuse Dot.

**Fix**: Simplify to "Compare as strings: CAST(payments.is_credit AS VARCHAR) or just use string comparison."

### 4. Org Note (External Asset) — Too Verbose with SQL Templates
The 6955-char org note duplicates table-level documentation and includes SQL templates.
Dot has to reconcile multiple conflicting sources of SQL guidance.

**Fix**: Reduce to core rules only. No SQL templates. Let Dot generate SQL itself.

### 5. fees.intracountry Column Comment — Truncated
The user_comment is cut off mid-sentence. Should clarify computation.

### 6. Duplicate MCC Column
The fees table has both `mcc` and `merchant_category_code` columns with similar descriptions.
This is confusing. Clarify they are the same data.

## Relationships — OK
- payments.merchant → merchant_data.merchant ✓
- merchant_data.merchant_category_code → merchant_category_codes.mcc ✓
- merchant_data.primary_acquirer → acquirer_countries.acquirer ✓
- monthly_merchant_stats.merchant → merchant_data.merchant ✓ (new, correct)

## Action Plan
1. Replace fees table description SQL section with simpler semantic rules
2. Rewrite org note to be minimal and rule-focused (no SQL templates)
3. Update key column comments (intracountry, is_credit)
4. Add performance guidance to org note (avoid iterative queries)
