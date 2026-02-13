# DABStep Dot Context Pack (Minimal, Canonical)

## Do this first
1. Determine question type: `fee total` / `delta` / `applicable fee IDs` / `fraud` / `general aggregation`.
2. Use the matching SQL template from section D.
3. Output only `FINAL_ANSWER: <answer>`.

## A) Tables (short + exact)

### `uploads.main.payments`
- Columns: `psp_reference, merchant, card_scheme, year, hour_of_day, minute_of_hour, day_of_year, is_credit, eur_amount, ip_country, issuing_country, device_type, ip_address, email_address, card_number, shopper_interaction, card_bin, has_fraudulent_dispute, is_refused_by_adyen, aci, acquirer_country`
- Meaning: transaction fact table (one row per payment).

### `uploads.main.merchant_data`
- Columns: `merchant, account_type, merchant_category_code, capture_delay, capture_delay_bucket, primary_acquirer, alternate_acquirer, acquirer`
- Meaning: merchant profile used for fee matching dimensions.

### `uploads.main.fees`
- Columns: `ID, card_scheme, account_type, capture_delay, monthly_fraud_level, monthly_volume, merchant_category_code, is_credit, aci, fixed_amount, rate, intracountry`
- Meaning: fee rules table.
- Wildcard reminder: `NULL` or empty list (`[]`) means "applies to all".

### `uploads.main.monthly_merchant_stats`
- Columns: `merchant, year, month, total_volume_eur, total_txn_count, fraud_volume_eur, fraud_txn_count, fraud_rate, volume_tier, fraud_tier`
- Meaning: precomputed monthly tiers; use `volume_tier` + `fraud_tier` for month/date fee questions.

### `uploads.main.acquirer_countries`
- Columns: `acquirer, country_code`
- Join key: `merchant_data.primary_acquirer -> acquirer_countries.acquirer` (lookup/reference only).

### `uploads.main.merchant_category_codes`
- Columns: `mcc, description`
- Join key: `merchant_data.merchant_category_code -> merchant_category_codes.mcc`.

## B) Relationship Map (joins)

- `payments.merchant = merchant_data.merchant`
- `monthly_merchant_stats` join key: `(merchant, year, month)`
- Fee matching uses:
  - Transaction fields: `payments.card_scheme, payments.is_credit, payments.aci, intracountry`
  - Merchant fields: `merchant_data.account_type, merchant_data.merchant_category_code, merchant_data.capture_delay_bucket`
  - Monthly tiers: `monthly_merchant_stats.volume_tier, monthly_merchant_stats.fraud_tier`

## C) Rules (minimal, canonical)

- Fee formula: `fee = fixed_amount + (rate * eur_amount / 10000.0)`.
- Fee matching is strict `AND` across all non-null/non-empty constraints.
- `NULL` or empty list (`[]`) means wildcard.
- Date/month fee questions must apply monthly tiers from `monthly_merchant_stats`.
- Use `merchant_data.capture_delay_bucket` directly for `fees.capture_delay` (do not remap raw capture delay).
- `intracountry = CASE WHEN issuing_country = acquirer_country THEN 1 ELSE 0 END`.
- If multiple rules match a transaction:
  - choose max specificity (most constrained fields),
  - if tie, average tied fee values.
- If no fee rule matches a transaction: fee is `0` (never drop transaction).
- "Applicable fee IDs" questions: get actual transactions for that period, find matches per transaction, return union of IDs.
- Fraud ranking questions use fraud **RATE** (EUR volume ratio), not count, unless question explicitly asks for count.
- If question asks for concepts not in data model (for example fines/penalties), answer `Not Applicable`.

### Common failure modes to avoid
- Missing monthly tier filter on date/month fee questions (returns supersets).
- Using raw `capture_delay` instead of `capture_delay_bucket`.
- Returning merchant-level fee ID supersets instead of transaction-level union.

## D) SQL templates (use as patterns)

### 1) Monthly tier lookup
```sql
SELECT volume_tier, fraud_tier
FROM uploads.main.monthly_merchant_stats
WHERE merchant = :merchant
  AND year = :year
  AND month = :month;
```

### 2) Total fees for merchant + month (includes fee=0 handling)
```sql
WITH txns AS (
  SELECT p.*,
         CASE WHEN p.issuing_country = p.acquirer_country THEN 1 ELSE 0 END AS intracountry
  FROM uploads.main.payments p
  WHERE p.merchant = :merchant AND p.year = :year AND p.day_of_year BETWEEN :d1 AND :d2
),
m AS (
  SELECT merchant, account_type, merchant_category_code, capture_delay_bucket
  FROM uploads.main.merchant_data
  WHERE merchant = :merchant
),
tier AS (
  SELECT volume_tier, fraud_tier
  FROM uploads.main.monthly_merchant_stats
  WHERE merchant = :merchant AND year = :year AND month = :month
),
matches AS (
  SELECT
    t.psp_reference,
    f.ID,
    (f.fixed_amount + (f.rate * t.eur_amount / 10000.0)) AS fee_value,
    (
      CASE WHEN f.account_type IS NOT NULL AND f.account_type <> '[]' THEN 1 ELSE 0 END +
      CASE WHEN f.capture_delay IS NOT NULL THEN 1 ELSE 0 END +
      CASE WHEN f.monthly_fraud_level IS NOT NULL THEN 1 ELSE 0 END +
      CASE WHEN f.monthly_volume IS NOT NULL THEN 1 ELSE 0 END +
      CASE WHEN f.merchant_category_code IS NOT NULL AND f.merchant_category_code <> '[]' THEN 1 ELSE 0 END +
      CASE WHEN f.is_credit IS NOT NULL THEN 1 ELSE 0 END +
      CASE WHEN f.aci IS NOT NULL AND f.aci <> '[]' THEN 1 ELSE 0 END +
      CASE WHEN f.intracountry IS NOT NULL THEN 1 ELSE 0 END
    ) AS spec
  FROM txns t
  CROSS JOIN m
  CROSS JOIN tier tm
  JOIN uploads.main.fees f ON
    f.card_scheme = t.card_scheme
    AND (f.account_type IS NULL OR f.account_type = '[]' OR m.account_type IN (SELECT value FROM json_each(f.account_type)))
    AND (f.capture_delay IS NULL OR f.capture_delay = m.capture_delay_bucket)
    AND (f.monthly_fraud_level IS NULL OR f.monthly_fraud_level = tm.fraud_tier)
    AND (f.monthly_volume IS NULL OR f.monthly_volume = tm.volume_tier)
    AND (f.merchant_category_code IS NULL OR f.merchant_category_code = '[]'
         OR m.merchant_category_code IN (SELECT CAST(value AS INTEGER) FROM json_each(f.merchant_category_code)))
    AND (f.is_credit IS NULL OR CAST(f.is_credit AS TEXT) = LOWER(CAST(t.is_credit AS TEXT)))
    AND (f.aci IS NULL OR f.aci = '[]' OR t.aci IN (SELECT value FROM json_each(f.aci)))
    AND (f.intracountry IS NULL OR CAST(f.intracountry AS INTEGER) = t.intracountry)
),
txn_fee AS (
  SELECT t.psp_reference,
         COALESCE(
           (
             SELECT AVG(m2.fee_value)
             FROM matches m2
             WHERE m2.psp_reference = t.psp_reference
               AND m2.spec = (SELECT MAX(m3.spec) FROM matches m3 WHERE m3.psp_reference = t.psp_reference)
           ),
           0.0
         ) AS fee
  FROM txns t
)
SELECT ROUND(SUM(fee), 2) AS total_fee_eur
FROM txn_fee;
```

### 3) Applicable fee IDs for merchant + date (transaction-level union)
```sql
WITH txns AS (
  SELECT p.*,
         CASE WHEN p.issuing_country = p.acquirer_country THEN 1 ELSE 0 END AS intracountry,
         CASE
           WHEN p.day_of_year BETWEEN 1 AND 31 THEN 1
           WHEN p.day_of_year BETWEEN 32 AND 59 THEN 2
           WHEN p.day_of_year BETWEEN 60 AND 90 THEN 3
           WHEN p.day_of_year BETWEEN 91 AND 120 THEN 4
           WHEN p.day_of_year BETWEEN 121 AND 151 THEN 5
           WHEN p.day_of_year BETWEEN 152 AND 181 THEN 6
           WHEN p.day_of_year BETWEEN 182 AND 212 THEN 7
           WHEN p.day_of_year BETWEEN 213 AND 243 THEN 8
           WHEN p.day_of_year BETWEEN 244 AND 273 THEN 9
           WHEN p.day_of_year BETWEEN 274 AND 304 THEN 10
           WHEN p.day_of_year BETWEEN 305 AND 334 THEN 11
           ELSE 12
         END AS month_num
  FROM uploads.main.payments p
  WHERE p.merchant = :merchant AND p.year = :year AND p.day_of_year = :day_of_year
),
m AS (
  SELECT merchant, account_type, merchant_category_code, capture_delay_bucket
  FROM uploads.main.merchant_data
  WHERE merchant = :merchant
)
SELECT DISTINCT f.ID
FROM txns t
JOIN uploads.main.monthly_merchant_stats ms
  ON ms.merchant = t.merchant AND ms.year = t.year AND ms.month = t.month_num
CROSS JOIN m
JOIN uploads.main.fees f ON
  f.card_scheme = t.card_scheme
  AND (f.account_type IS NULL OR f.account_type = '[]' OR m.account_type IN (SELECT value FROM json_each(f.account_type)))
  AND (f.capture_delay IS NULL OR f.capture_delay = m.capture_delay_bucket)
  AND (f.monthly_fraud_level IS NULL OR f.monthly_fraud_level = ms.fraud_tier)
  AND (f.monthly_volume IS NULL OR f.monthly_volume = ms.volume_tier)
  AND (f.merchant_category_code IS NULL OR f.merchant_category_code = '[]'
       OR m.merchant_category_code IN (SELECT CAST(value AS INTEGER) FROM json_each(f.merchant_category_code)))
  AND (f.is_credit IS NULL OR CAST(f.is_credit AS TEXT) = LOWER(CAST(t.is_credit AS TEXT)))
  AND (f.aci IS NULL OR f.aci = '[]' OR t.aci IN (SELECT value FROM json_each(f.aci)))
  AND (f.intracountry IS NULL OR CAST(f.intracountry AS INTEGER) = t.intracountry)
ORDER BY f.ID;
```

### 4) Fraud rate by group (volume-based)
```sql
SELECT
  :group_col AS group_value,
  SUM(CASE WHEN has_fraudulent_dispute = TRUE THEN eur_amount ELSE 0 END) / NULLIF(SUM(eur_amount), 0) AS fraud_rate
FROM uploads.main.payments
GROUP BY :group_col
ORDER BY fraud_rate DESC;
```

## E) Output format constraints

- Output only: `FINAL_ANSWER: <answer>`.
- No explanation text before/after answer.
- Apply rounding/format from the task guidelines.
