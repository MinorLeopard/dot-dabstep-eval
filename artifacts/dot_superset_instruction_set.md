# Dot Anti-Superset Instruction Set

## Where supersets occurred
- `Q1681` (day-specific applicable Fee IDs) and `Q1753` (month-specific applicable Fee IDs) produced the same 47-ID list in run `20260212_103707_e8baeb`.
- Failure pattern: IDs were derived from merchant+tier constraints only; transaction-level constraints (`card_scheme`, `aci`, `is_credit`, `intracountry`) were not enforced per transaction.

## Mandatory anti-superset rules
1. For applicable Fee ID questions, start from `payments` rows in the exact requested window.
2. Join `payments -> merchant_data` and `monthly_merchant_stats` (merchant, year, month).
3. Match fees with strict AND using all constrained fields:
   - transaction: `card_scheme`, `is_credit`, `aci`, `intracountry`
   - merchant: `account_type`, `merchant_category_code`, `capture_delay_bucket`
   - tier: `monthly_volume`, `monthly_fraud_level`
4. Aggregate by fee `ID` and compute `supporting_txn_count = COUNT(DISTINCT psp_reference)`.
5. Keep only IDs with `supporting_txn_count > 0`.
6. Never return IDs from merchant-level filtering alone.
7. Day-specific tasks must use exact `day_of_year = D` (not whole-month window).

## SQL shape (template)
```sql
WITH txns AS (... exact date/month filtered payments ...),
joined AS (... txns + merchant_data + monthly tiers ...),
matched AS (
  SELECT f.ID, t.psp_reference
  FROM joined t
  JOIN fees f ON ... strict AND constraints ...
)
SELECT ID
FROM matched
GROUP BY ID
HAVING COUNT(DISTINCT psp_reference) > 0
ORDER BY ID;
```
