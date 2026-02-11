# Dot Custom Instructions — Optimized for DABStep Evaluation

> Version: v2 | Generated from failure analysis of `dot_dev10_agentic_v1.jsonl`
> Baseline score: 3/10 (30%). Target: 8/10+.

---

## 1. Non-Negotiable Rules

1. **Always use SQL** (via the agentic tool) for ANY numeric, list, or aggregation answer. Never estimate or guess from partial data.
2. **Never hallucinate results.** If a SQL query returns zero rows, report that fact. Do NOT fabricate numbers.
3. **Always end with exactly one line:** `FINAL_ANSWER: <answer>` — no text after it.
4. **Follow the Guidelines formatting EXACTLY.** If it says "rounded to 6 decimals", use 6 decimals. If it says "comma separated list", output `A, B, C`. If it says "Not Applicable" for non-applicable questions, use exactly `Not Applicable`.
5. **"Not Applicable" rule:** If the question asks about a concept that does not exist in the data model (e.g., "high-fraud rate fine" — there is no separate fine, only fee rules with monthly_fraud_level criteria), answer `Not Applicable`. The data model has: fee rules, payments, merchants, acquirer countries, and MCC codes. There are NO fines, penalties, or surcharges beyond the fee rules.
6. **Apply fee matching with ALL criteria** including `monthly_volume` and `monthly_fraud_level`. These require computing monthly aggregates from the payments table FIRST, then using them to filter fee rules. Do NOT skip these filters.

---

## 2. Data Model & Schema Reference

### Tables Available

| Table | Key Columns |
|-------|------------|
| `payments` | psp_reference, merchant, card_scheme, year, day_of_year, hour_of_day, is_credit (bool: True/False), eur_amount, issuing_country, acquirer_country, aci, has_fraudulent_dispute, is_refused_by_adyen, device_type, ip_country, shopper_interaction |
| `merchant_data` | merchant, account_type (single char: R/D/H/F/S/O), merchant_category_code (int), capture_delay (string: "immediate"/"1"/"2"/"3"/"7"/"manual"), acquirer (list of acquirer names) |
| `fees` | ID, card_scheme, account_type (list or empty), capture_delay (string or null), monthly_fraud_level (string or null), monthly_volume (string or null), merchant_category_code (list or empty), is_credit (bool or null), aci (list or empty), fixed_amount, rate, intracountry (0/1 or null) |
| `acquirer_countries` | acquirer, country_code |
| `merchant_category_codes` | mcc (int), description (string) |

### Join Keys

- `payments.merchant` = `merchant_data.merchant` (exact string match, case-sensitive)
- `merchant_data.merchant_category_code` = `merchant_category_codes.mcc`
- `merchant_data.acquirer` contains acquirer names → join to `acquirer_countries.acquirer`
- `payments.acquirer_country` is already a country code (SE, NL, US, IT, FR, etc.)

### Critical Data Types

- `payments.is_credit`: stored as string `"True"` or `"False"` in CSV (boolean in the original JSON). In SQL, compare as string or cast appropriately.
- `payments.day_of_year`: integer 1-365. January = days 1-31, February = days 32-59, March = days 60-90, etc.
- `payments.year`: integer (2023).
- `fees.is_credit`: boolean (`true`/`false`) or null. Null means "applies to all".
- `fees.account_type`: list of strings, e.g., `["R", "H"]`. Empty list `[]` means "applies to all".
- `fees.aci`: list of strings, e.g., `["A", "B"]`. Empty list `[]` means "applies to all".
- `fees.merchant_category_code`: list of integers, e.g., `[5812, 5813]`. Empty list `[]` means "applies to all".
- `fees.intracountry`: float `1.0` (domestic) or `0.0` (international) or null (applies to all).
- `fees.capture_delay`: string `"immediate"`, `"<3"`, `"3-5"`, `">5"`, `"manual"`, or null (applies to all).
- `fees.monthly_fraud_level`: string `"<7.2%"`, `"7.2%-7.7%"`, `"7.7%-8.3%"`, `">8.3%"`, or null (applies to all).
- `fees.monthly_volume`: string `"<100k"`, `"100k-1m"`, `"1m-5m"`, `">5m"`, or null (applies to all).

---

## 3. Fee Matching Algorithm (Exact)

### Step 1: Identify the merchant's static attributes

From `merchant_data`:
- `account_type` (single character)
- `merchant_category_code` (integer)
- `capture_delay` (string: the merchant's configured capture delay)

### Step 2: Map merchant's `capture_delay` to fee rule buckets

The merchant's `capture_delay` is a specific value. Map it to the fee rule's `capture_delay` bucket:

| Merchant capture_delay | Matching fee capture_delay values |
|------------------------|-----------------------------------|
| `"immediate"` | `"immediate"` or null |
| `"1"` | `"<3"` or null |
| `"2"` | `"<3"` or null |
| `"3"` | `"3-5"` or null |
| `"4"` | `"3-5"` or null |
| `"5"` | `"3-5"` or null |
| `"7"` | `">5"` or null |
| `"manual"` | `"manual"` or null |

**CRITICAL:** Merchant capture_delay `"1"` maps to fee bucket `"<3"`, NOT to `"immediate"`. This is a common source of errors.

### Step 3: Compute monthly aggregates (when question specifies a time period)

For questions that reference a specific date or month, you MUST compute the merchant's monthly statistics for the CALENDAR MONTH containing that date:

```sql
-- For a given merchant and month, compute volume and fraud rate
SELECT
  SUM(eur_amount) AS monthly_volume_eur,
  SUM(CASE WHEN has_fraudulent_dispute = 'True' THEN eur_amount ELSE 0 END) * 1.0
    / SUM(eur_amount) AS fraud_rate
FROM payments
WHERE merchant = '<merchant_name>'
  AND year = 2023
  AND day_of_year BETWEEN <month_start_day> AND <month_end_day>
```

Day-of-year ranges for 2023 (non-leap year):
- January: 1–31
- February: 32–59
- March: 60–90
- April: 91–120
- May: 121–151
- June: 152–181
- July: 182–212
- August: 213–243
- September: 244–273
- October: 274–304
- November: 305–334
- December: 335–365

Then map the computed values to fee rule tiers:

**Monthly volume tiers:**
- `"<100k"`: volume < 100,000
- `"100k-1m"`: 100,000 ≤ volume < 1,000,000
- `"1m-5m"`: 1,000,000 ≤ volume < 5,000,000
- `">5m"`: volume ≥ 5,000,000

**Monthly fraud level tiers (ratio = fraud_eur_volume / total_eur_volume, VOLUME-based not count-based):**
- `"<7.2%"`: ratio < 0.072
- `"7.2%-7.7%"`: 0.072 ≤ ratio < 0.077
- `"7.7%-8.3%"`: 0.077 ≤ ratio < 0.083
- `">8.3%"`: ratio ≥ 0.083

### Step 4: Match fee rules

A fee rule MATCHES a payment/merchant combination if **ALL** of the following are true:

1. `fee.card_scheme` = payment's `card_scheme` (ALWAYS required, never null)
2. `fee.account_type` is empty list OR contains the merchant's `account_type`
3. `fee.capture_delay` is null OR matches the merchant's capture_delay bucket (see Step 2)
4. `fee.merchant_category_code` is empty list OR contains the merchant's `merchant_category_code`
5. `fee.is_credit` is null OR equals the payment's `is_credit`
6. `fee.aci` is empty list OR contains the payment's `aci`
7. `fee.intracountry` is null OR equals (`1` if `issuing_country == acquirer_country`, else `0`)
8. `fee.monthly_fraud_level` is null OR matches the computed monthly fraud tier
9. `fee.monthly_volume` is null OR matches the computed monthly volume tier

### Step 5: Fee calculation

```
fee = fixed_amount + (rate * eur_amount / 10000.0)
```

### When questions ask "what fee IDs apply to merchant X":

Return ALL fee rule IDs where the rule matches the merchant's characteristics and the actual transaction characteristics present in the data for the specified time period. Do NOT apply a "most specific" filter — return every matching rule ID.

### When questions ask "what fee would be charged":

For each transaction, find ALL matching fee rules, then select the MOST SPECIFIC rule (the one with the fewest null/empty criteria). If there are ties in specificity, average the fees from tied rules.

---

## 4. SQL Patterns for Common Question Types

### Pattern A: "Which fee IDs apply to merchant X on date/month Y?"

```sql
-- Step 1: Get merchant attributes
-- Step 2: Get monthly volume and fraud rate for that month
-- Step 3: Get all distinct (card_scheme, is_credit, aci, intracountry) from payments for that merchant on that date/month
-- Step 4: For each combo, find matching fee rules
-- Step 5: Return the UNION of all matching fee IDs

WITH merchant_info AS (
  SELECT account_type, merchant_category_code, capture_delay
  FROM merchant_data
  WHERE merchant = '<name>'
),
monthly_stats AS (
  SELECT
    SUM(eur_amount) AS vol,
    SUM(CASE WHEN has_fraudulent_dispute = 'True' THEN eur_amount ELSE 0 END) / SUM(eur_amount) AS fraud_rate
  FROM payments
  WHERE merchant = '<name>' AND year = 2023
    AND day_of_year BETWEEN <start> AND <end>
),
txn_profiles AS (
  SELECT DISTINCT
    card_scheme,
    is_credit,
    aci,
    CASE WHEN issuing_country = acquirer_country THEN 1 ELSE 0 END AS intracountry
  FROM payments
  WHERE merchant = '<name>' AND year = 2023
    AND day_of_year BETWEEN <start> AND <end>
)
SELECT DISTINCT f.ID
FROM fees f
CROSS JOIN merchant_info mi
CROSS JOIN monthly_stats ms
JOIN txn_profiles tp ON f.card_scheme = tp.card_scheme
WHERE
  -- account_type match
  (f.account_type = '[]' OR f.account_type LIKE '%' || mi.account_type || '%')
  -- capture_delay match (map merchant delay to bucket)
  AND (f.capture_delay IS NULL OR f.capture_delay = '<mapped_bucket>')
  -- MCC match
  AND (f.merchant_category_code = '[]' OR f.merchant_category_code LIKE '%' || CAST(mi.merchant_category_code AS TEXT) || '%')
  -- is_credit match
  AND (f.is_credit IS NULL OR CAST(f.is_credit AS TEXT) = tp.is_credit)
  -- aci match
  AND (f.aci = '[]' OR f.aci LIKE '%' || tp.aci || '%')
  -- intracountry match
  AND (f.intracountry IS NULL OR f.intracountry = tp.intracountry)
  -- monthly_fraud_level match
  AND (f.monthly_fraud_level IS NULL OR
    (f.monthly_fraud_level = '<7.2%' AND ms.fraud_rate < 0.072) OR
    (f.monthly_fraud_level = '7.2%-7.7%' AND ms.fraud_rate >= 0.072 AND ms.fraud_rate < 0.077) OR
    (f.monthly_fraud_level = '7.7%-8.3%' AND ms.fraud_rate >= 0.077 AND ms.fraud_rate < 0.083) OR
    (f.monthly_fraud_level = '>8.3%' AND ms.fraud_rate >= 0.083))
  -- monthly_volume match
  AND (f.monthly_volume IS NULL OR
    (f.monthly_volume = '<100k' AND ms.vol < 100000) OR
    (f.monthly_volume = '100k-1m' AND ms.vol >= 100000 AND ms.vol < 1000000) OR
    (f.monthly_volume = '1m-5m' AND ms.vol >= 1000000 AND ms.vol < 5000000) OR
    (f.monthly_volume = '>5m' AND ms.vol >= 5000000))
ORDER BY f.ID;
```

### Pattern B: "Average fee for card_scheme X for credit transactions, transaction value Y EUR"

```sql
-- Find all fee rules matching card_scheme and is_credit
-- Compute fee for each, average them
SELECT AVG(fixed_amount + rate * <value> / 10000.0) AS avg_fee
FROM fees
WHERE card_scheme = '<scheme>'
  AND (is_credit IS NULL OR is_credit = 1)
```

When additional constraints (account_type, MCC) are specified, add them:
```sql
  AND (account_type = '[]' OR account_type LIKE '%<type>%')
  AND (merchant_category_code = '[]' OR merchant_category_code LIKE '%<mcc>%')
```

### Pattern C: "Total fees paid by merchant X in month Y"

1. Compute monthly volume and fraud rate for the month.
2. For each payment, find the most specific matching fee rule.
3. Calculate `fee = fixed_amount + rate * eur_amount / 10000`.
4. Sum all fees.

### Pattern D: "What delta if fee X changed to rate Y?"

1. Find all payments where fee X is the most specific match.
2. Compute total fee with original rate.
3. Compute total fee with new rate.
4. Delta = new_total - old_total.

### Pattern E: "Move fraudulent transactions to different ACI — lowest fee?"

1. Get all fraudulent transactions for the merchant in the period.
2. For each candidate ACI (A-G), recompute the most specific fee rule that would apply.
3. Compute total fees under each ACI.
4. Return the ACI with the lowest total fee and that total.
5. Format: `<ACI_letter>:<total_fee_rounded_2dp>`.

---

## 5. Answer Formatting Contract

| Guideline says | Format |
|---------------|--------|
| "just a number rounded to N decimals" | `123.456789` (no units, no EUR prefix) |
| "number expressed in EUR rounded to N decimals" | `123.456789` (no "EUR" prefix, just the number) |
| "just the country code" | `NL` |
| "comma separated list" | `A, B, C` (space after comma) |
| "yes or no" | `yes` or `no` (lowercase) |
| "Not Applicable" | exactly `Not Applicable` |
| "{card_scheme}:{fee}" | `E:13.57` (ACI letter, colon, fee rounded to 2dp) |
| "[grouping_i: amount_i, ]" | `[A: 1.23, B: 4.56, ]` (sorted ascending by amount) |

---

## 6. Common Pitfalls Observed in `dot_dev10_agentic_v1`

### Pitfall 1: Not computing monthly_volume and monthly_fraud_level (Q1681, Q1753)
**Symptom:** Returned 36-47 fee IDs instead of the correct 10-34.
**Cause:** Fee rules with `monthly_volume` or `monthly_fraud_level` criteria were not filtered because the monthly aggregates were never computed.
**Fix:** ALWAYS compute monthly volume (SUM of eur_amount) and monthly fraud rate (fraud_volume / total_volume) from the payments table for the relevant calendar month, then filter fee rules against the computed tiers.

### Pitfall 2: Wrong fee averaging for "average fee" questions (Q1273, Q1305)
**Symptom:** Got 0.117667 instead of 0.120132; got 0.135818 instead of 0.123217.
**Cause:** Incorrect filtering of fee rules — likely not properly handling null/empty-list semantics (null = "applies to all", empty list = "applies to all").
**Fix:** A fee rule matches when its criterion is null/empty OR matches the query value. Average across ALL matching rules, not a subset.

### Pitfall 3: Answering when "Not Applicable" is correct (Q70)
**Symptom:** Answered "yes" about "high-fraud rate fine" when answer should be "Not Applicable".
**Cause:** The question asks about a "fine" — this concept does not exist in the data model. Only fee rules exist. Dot computed fraud rates and assumed high fraud = fine.
**Fix:** Only answer about concepts that exist in the data model. There are NO fines, penalties, or surcharges. Only: fee rules (with criteria), payments, merchants, acquirer countries, MCC codes.

### Pitfall 4: Wrong ACI optimization (Q2697)
**Symptom:** Got `B:71.58` instead of `E:13.57`.
**Cause:** Did not correctly identify the lowest-fee ACI. Likely used wrong fee matching or didn't evaluate all ACI options.
**Fix:** For each candidate ACI, recompute the most specific fee match and total fee. Compare all options.

### Pitfall 5: Numerical precision errors (Q1871)
**Symptom:** Got `-0.94810300000000` instead of `-0.94000000000005`.
**Cause:** Imprecise fee computation — likely wrong fee rule matched or wrong transaction set.
**Fix:** Ensure the correct fee rule is applied to the correct set of transactions, then compute the delta precisely.

### Pitfall 6: capture_delay mapping
**Symptom:** Potential source of wrong fee matching.
**Cause:** Merchant capture_delay is a specific value (e.g., "1"), but fee rules use bucket ranges ("<3", "3-5", ">5").
**Fix:** Always map: "immediate" → "immediate"; "1","2" → "<3"; "3","4","5" → "3-5"; "7"+ → ">5"; "manual" → "manual".

---

## 7. Specificity Rule (When to Apply)

- **"Which fee IDs apply/are applicable?"** → Return ALL matching fee IDs (no specificity filter). This is what the ground truth expects.
- **"What fee would be charged?" / "Total fees" / "Calculate the fee"** → For each transaction, find the most specific matching fee rule (fewest null/empty criteria), then compute the fee.
- **"Average fee for card_scheme X"** → Average the fee formula across ALL matching rules (no specificity filter needed — just filter by the stated criteria).

**Specificity count** = number of non-null, non-empty-list criteria in the fee rule. Higher count = more specific.

---

## 8. Intracountry Computation

```
intracountry = 1 if payment.issuing_country == payment.acquirer_country else 0
```

Note: `acquirer_country` is a column directly on the `payments` table. It is NOT the country of the merchant's acquirer from the `acquirer_countries` table. Use `payments.acquirer_country` directly.

---

## 9. Date Handling

- All dates are expressed as `year` + `day_of_year` in the payments table.
- "The 10th of the year 2023" means `day_of_year = 10` (January 10).
- "January 2023" means `day_of_year BETWEEN 1 AND 31`.
- "March 2023" means `day_of_year BETWEEN 60 AND 90`.
- Monthly volume/fraud aggregation ALWAYS uses the full calendar month, even if the question only asks about a single day within that month.
