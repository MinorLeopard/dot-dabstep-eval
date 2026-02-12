# Context Update Log — Loop 4

## Changes Applied (relative to Loop 3)

### 1. Fees Table Description (Updated)
- **Removed**: Prescriptive SQL JOIN patterns (LIKE-based list membership matching)
- **Kept**: Semantic matching rules, wildcard logic, intracountry computation
- **Added**: Cleaner matching criteria table, specificity rule explanation
- **Rationale**: Prescriptive SQL patterns caused Q1273 regression and Q1681 column confusion in Loop 3

### 2. fees.intracountry Column (Restored)
- Column was missing from fees table after Loop 3 changes (13 columns → now 14)
- Added with comment: "Domestic vs cross-border indicator (1.0=domestic, 0.0=cross-border, NULL=all)"
- **Rationale**: Q1681 failure in Loop 3 — Dot reported "intracountry column doesn't exist"

### 3. fees.is_credit Column Comment (Simplified)
- Old: Complex casting guidance with SQL examples
- New: "Credit card indicator. Values: 'true' (credit), 'false' (debit), NULL (matches both). Stored as VARCHAR text. When matching against payments.is_credit (BOOLEAN), compare as text strings."
- **Rationale**: Simpler is better — let Dot figure out casting

### 4. Org Note / External Asset (Rewritten)
- Old: 6955 chars with SQL templates and verbose examples
- New: 2800 chars, minimal semantic rules only
- No SQL templates — only describes WHAT to match, not HOW to write SQL
- Sections: Tables, Fee Formula, Fee Matching, Monthly Tier Filter, Fraud Questions, Intracountry, Specificity Rule, Not Applicable, Performance, Output
- **Rationale**: Multiple SQL sources (table desc + org note + prompt) created conflicting guidance

### 5. Prompt (prompting.py) — Unchanged from Loop 3
- SYSTEM_INSTRUCTION: Has table schemas, fee formula, capture_delay, fraud fields, monthly tier filter, intracountry, date handling
- PROMPT_REMINDER: Emphasizes monthly_merchant_stats lookup, capture_delay_bucket, fraud field specificity

## Expected Impact
- Q1273: Should recover (prescriptive SQL removed)
- Q1305: May improve (cleaner list matching)
- Q1681: Should improve (intracountry column restored)
- Q49: Unchanged (persistent reasoning error, not a context issue)
- Q1753, Q1871, Q2697: May improve from cleaner overall context
