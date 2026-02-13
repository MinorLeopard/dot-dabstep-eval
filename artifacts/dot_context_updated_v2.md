# DABStep Dot Context v2.1 (Concise Canonical)

## Do this first
1. Determine question type: `fee total` / `delta` / `applicable fee IDs` / `fraud` / `general aggregation`.
2. Use the matching SQL template.
3. Output only `FINAL_ANSWER: <answer>`.

## Tables

### `uploads.main.payments`
- Columns: `psp_reference, merchant, card_scheme, year, day_of_year, is_credit, eur_amount, ip_country, issuing_country, acquirer_country, aci, has_fraudulent_dispute, device_type, shopper_interaction, email_address, ...`
- One row per transaction.

### `uploads.main.merchant_data`
- Columns: `merchant, account_type, merchant_category_code, capture_delay, capture_delay_bucket, primary_acquirer, acquirer, ...`
- Merchant attributes used in fee matching.

### `uploads.main.fees`
- Columns: `ID, card_scheme, account_type, capture_delay, monthly_fraud_level, monthly_volume, merchant_category_code, is_credit, aci, fixed_amount, rate, intracountry`
- Wildcard semantics: `NULL` or empty list (`[]`) means "applies to all".

### `uploads.main.monthly_merchant_stats`
- Columns: `merchant, year, month, total_volume_eur, fraud_volume_eur, fraud_rate, volume_tier, fraud_tier`
- Precomputed monthly tiers for fee filtering.

### Lookup tables
- `uploads.main.acquirer_countries(acquirer, country_code)`
- `uploads.main.merchant_category_codes(mcc, description)`

## Joins and matching map
- `payments.merchant = merchant_data.merchant`
- `monthly_merchant_stats` join key: `(merchant, year, month)`
- For any fee computation, always join `payments -> merchant_data` first to fetch:
  - `account_type`
  - `merchant_category_code`
  - `capture_delay_bucket`
- Fee matching dimensions:
  - Transaction: `card_scheme, is_credit, aci, intracountry`
  - Merchant: `account_type, merchant_category_code, capture_delay_bucket`
  - Monthly tiers: `volume_tier, fraud_tier`

## Core rules
- Fee formula: `fee = fixed_amount + (rate * eur_amount / 10000.0)`.
- Matching is strict `AND` across all constrained fee fields.
- `capture_delay` must use `merchant_data.capture_delay_bucket` (no raw remap).
- `intracountry = CASE WHEN issuing_country = acquirer_country THEN 1 ELSE 0 END`.
- For month/date fee questions, monthly tier filter is mandatory:
  - if only `day_of_year` is given, derive month from day-of-year ranges first
  - `(monthly_volume IS NULL OR monthly_volume = volume_tier)`
  - `(monthly_fraud_level IS NULL OR monthly_fraud_level = fraud_tier)`
- If multiple fee rules match a transaction:
  - keep only max-specificity matches (most constrained fields)
  - if tie at max specificity, average tied fee values
- If no matching fee rule exists for a transaction: fee is `0` (never drop the txn).

## Scenario rules
- Applies to ACI incentive, scheme steering, and hypothetical fee-change tasks.
- Recompute fee per transaction under scenario conditions.
- If no rule matches under scenario, fee is `0`.
- If wording says `relative fee` or `rate` changed to `X`: set `fees.rate = X`, keep `fixed_amount` unchanged.
- If wording says `fixed fee` changed: change `fixed_amount`.

## Fraud and analytics disambiguation
- "Most commonly used in fraudulent transactions" => **COUNT** of fraudulent rows.
- "Top/highest fraud" => **RATE** = fraudulent EUR / total EUR, unless question explicitly asks for count.
- Use the exact country field asked (`ip_country` vs `issuing_country` vs `acquirer_country`).

## Email metrics
- `avg_per_unique_email = SUM(eur_amount) / COUNT(DISTINCT non-empty email_address)`
- `repeat_customer_pct = 100 * COUNT(DISTINCT email_address with txn_count>1) / COUNT(DISTINCT non-empty email_address)`
- Treat NULL and `TRIM(email_address) = ''` as empty.

## Applicable fee IDs rule
- For merchant+date/month questions:
1. Query actual transactions for that merchant and period.
2. Match fees per transaction using transaction + merchant + monthly-tier dimensions.
3. Return union of matching `ID`s across all transactions.

## Not Applicable rule
- If the concept is not present in the model (for example fines/penalties), answer `Not Applicable`.

## SQL templates

### Monthly tier lookup
```sql
SELECT volume_tier, fraud_tier
FROM uploads.main.monthly_merchant_stats
WHERE merchant = :merchant AND year = :year AND month = :month;
```

### Applicable fee IDs (merchant + day_of_year)
```sql
-- Build merchant/date transactions.
-- Derive month from day_of_year, compute intracountry, join merchant_data + monthly_merchant_stats.
-- Match fees with strict AND and return DISTINCT fee IDs.
```

### Total fees (merchant + month/date)
```sql
-- Per transaction: match fees -> keep max specificity -> tie-average fee.
-- If no match, transaction fee = 0.
-- Sum all transaction fees and round per task guideline.
```

### Fraud rate by group
```sql
SELECT grp,
       SUM(CASE WHEN has_fraudulent_dispute THEN eur_amount ELSE 0 END) / NULLIF(SUM(eur_amount),0) AS fraud_rate
FROM ...
GROUP BY grp
ORDER BY fraud_rate DESC;
```

## Output constraints
- Output exactly: `FINAL_ANSWER: <answer>`
- No extra prose.
- Follow task guideline formatting and rounding exactly.
