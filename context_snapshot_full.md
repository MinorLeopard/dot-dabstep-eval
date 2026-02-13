# Dot Context Snapshot

- Exported: **2026-02-13 11:36:42 UTC**
- Base URL: **https://test.getdot.ai**

# Relationships

- **id=832498991** active=true type=foreign :: `uploads.main.merchant_data`(primary_acquirer) → `uploads.main.acquirer_countries`(acquirer)
- **id=1865993787** active=true type=foreign :: `uploads.main.merchant_data`(merchant_category_code) → `uploads.main.merchant_category_codes`(mcc)
- **id=558909981** active=true type=foreign :: `uploads.main.monthly_merchant_stats`(merchant) → `uploads.main.merchant_data`(merchant)
- **id=1014148648** active=true type=foreign :: `uploads.main.payments`(merchant) → `uploads.main.merchant_data`(merchant)

# External assets / Org notes

## Asset: `fee_calculation_guide`
- Name: **Fee Calculation SQL Query Guide**
- Subtype: `note`
- Active: **true**
- Body length: **3056 chars**

### Body
```markdown
## Fee Calculation SQL Query Guide

Always use SQL. Never guess.

### Tables
1. uploads.main.payments — transactions
2. uploads.main.merchant_data — merchant profiles (includes capture_delay_bucket)
3. uploads.main.fees — 1000 fee pricing rules
4. uploads.main.monthly_merchant_stats — pre-computed monthly volume/fraud tiers per merchant
5. uploads.main.acquirer_countries — acquirer to country mapping
6. uploads.main.merchant_category_codes — MCC lookup

### Fee Formula
fee = fixed_amount + (rate * eur_amount / 10000.0)

### Fee Matching
A fee rule matches when ALL its non-null/non-empty criteria are satisfied:
- NULL or empty list [] = wildcard (matches everything)
- card_scheme: exact match (never null)
- account_type: JSON array like ['R','D'] — match if merchant's type is in the list, or list is empty
- aci: JSON array like ['A','B'] — match if payment's ACI is in the list, or list is empty
- merchant_category_code / mcc: JSON array of integers — match if merchant's MCC is in the list, or list is empty
- is_credit: VARCHAR 'true'/'false'/NULL — NULL matches all
- intracountry: DOUBLE 1.0/0.0/NULL — 1 if issuing_country = acquirer_country, 0 otherwise, NULL matches all
- capture_delay: match against merchant_data.capture_delay_bucket (NOT raw capture_delay)
- monthly_volume: match against monthly_merchant_stats.volume_tier for that month
- monthly_fraud_level: match against monthly_merchant_stats.fraud_tier for that month

### MANDATORY: Monthly Tier Filter
For ANY question about fees for a merchant on a specific date or month:
1. Determine the month (day_of_year: Jan=1-31, Feb=32-59, Mar=60-90, etc.)
2. Look up volume_tier and fraud_tier from monthly_merchant_stats for that merchant/year/month
3. Filter fee rules: require monthly_volume IS NULL OR = volume_tier, AND monthly_fraud_level IS NULL OR = fraud_tier
Skipping this returns too many fee IDs (superset error).

### CRITICAL: "Applicable Fee IDs" Questions
When asked which fee IDs apply to a merchant on a date/month:
1. Query the ACTUAL TRANSACTIONS for that merchant/date from payments
2. For EACH transaction, find ALL matching fee rules using the transaction's card_scheme, aci, is_credit, and computed intracountry PLUS merchant attributes and monthly tiers
3. Return the UNION of all matching fee IDs across all transactions
Do NOT just filter by merchant attributes — transaction-level fields (card_scheme, aci, is_credit, intracountry) MUST come from actual data.

### Fraud Questions
- "Fraud" = has_fraudulent_dispute = True
- "Top country for fraud" = highest fraud RATE (volume-based: fraud_EUR / total_EUR), NOT count
- ip_country, issuing_country, acquirer_country are THREE DIFFERENT fields
- Use whichever the question specifies

### Specificity Rule
- "Which fee IDs apply?" → ALL matching IDs
- "What fee is charged?" → most specific rule (most non-null criteria); average if tied

### Not Applicable
No fines, penalties, or surcharges exist. Only fee rules. If asked about nonexistent concepts: Not Applicable.

### Output
FINAL_ANSWER: <answer>
```

## Asset: `org_instructions`
- Name: **DABStep Fee & Domain Instructions**
- Subtype: `note`
- Active: **true**
- Body length: **5655 chars**

### Body
```markdown
## Fee Calculation Rules

Always use SQL. Never guess.

### Tables
1. uploads.main.payments — transactions
2. uploads.main.merchant_data — merchant profiles (includes capture_delay_bucket)
3. uploads.main.fees — 1000 fee pricing rules
4. uploads.main.monthly_merchant_stats — pre-computed monthly volume/fraud tiers per merchant
5. uploads.main.acquirer_countries — acquirer to country mapping
6. uploads.main.merchant_category_codes — MCC lookup

### Fee Formula
fee = fixed_amount + (rate * eur_amount / 10000.0)
- "relative fee" = rate (the variable basis-point component)
- "fixed fee" = fixed_amount (per-transaction EUR)

### Fee Matching — ALL Criteria Must Match
A fee rule matches when ALL its non-null/non-empty criteria are satisfied:
- NULL or empty list [] = wildcard (matches everything)
- card_scheme: exact match (never null)
- account_type: JSON array like ['R','D'] — match if merchant's type is in the list, or list is empty
- aci: JSON array like ['A','B'] — match if payment's ACI is in the list, or list is empty
- merchant_category_code / mcc: JSON array of integers — match if merchant's MCC is in the list, or list is empty
- is_credit: VARCHAR 'true'/'false'/NULL — NULL matches all. In payments is_credit is BOOLEAN; cast for comparison.
- intracountry: DOUBLE 1.0/0.0/NULL — 1 if issuing_country = acquirer_country, 0 otherwise, NULL matches all
- capture_delay: match against merchant_data.capture_delay_bucket (NOT raw capture_delay)
- monthly_volume: match against monthly_merchant_stats.volume_tier for that month
- monthly_fraud_level: match against monthly_merchant_stats.fraud_tier for that month

### MANDATORY: Monthly Tier Filter
For ANY question about fees for a merchant on a specific date or month:
1. Determine the month (day_of_year: Jan=1-31, Feb=32-59, Mar=60-90, Apr=91-120, May=121-151, Jun=152-181, Jul=182-212, Aug=213-243, Sep=244-273, Oct=274-304, Nov=305-334, Dec=335-365)
2. Look up volume_tier and fraud_tier from monthly_merchant_stats for that merchant/year/month
3. Filter fee rules: require monthly_volume IS NULL OR = volume_tier, AND monthly_fraud_level IS NULL OR = fraud_tier
Skipping this returns too many fee IDs (superset error).

### CRITICAL: "Applicable Fee IDs" for a Merchant on a Date/Month
When asked "what fee IDs apply to merchant X on date/month Y":
1. Get the ACTUAL TRANSACTIONS for that merchant on that date/month from payments table
2. For EACH transaction, find ALL fee rules matching that transaction's attributes:
   - card_scheme, aci, is_credit from the transaction
   - intracountry = CASE WHEN issuing_country = acquirer_country THEN 1 ELSE 0 END
   - account_type, merchant_category_code, capture_delay_bucket from merchant_data
   - volume_tier, fraud_tier from monthly_merchant_stats
3. Union ALL matching fee IDs across all transactions
4. Return the union as the answer

DO NOT just filter by merchant attributes alone — you MUST also filter by transaction-level attributes (card_scheme, aci, is_credit, intracountry) using actual transaction data.

### Specificity Rule
- "Which fee IDs apply?" → ALL matching IDs (union across all transactions)
- "What fee is charged?" → most specific rule (most non-null/non-empty criteria); average if tied
- Specificity = count of non-null, non-empty-list fields in the fee rule (card_scheme always counts as 1)

### Fee Delta Questions
When asked "what delta if fee X's rate changed to Y":
1. Find all transactions where fee X matches (using all matching criteria)
2. For each matching transaction: delta_txn = (new_rate - old_rate) * eur_amount / 10000.0
3. Sum all delta_txn values
4. "relative fee" means the rate field (basis points)

### ACI Steering / Optimization Questions
When asked "which ACI minimizes fees for fraudulent transactions":
1. Get the fraud transactions for the merchant/period (has_fraudulent_dispute = True)
2. For each candidate ACI (A through G):
   - For each fraud txn, replace aci with the candidate
   - Find matching fee rules for the modified transaction
   - Select the most specific rule(s), average if tied
   - Sum fees across all fraud transactions
3. Pick the ACI with the lowest total

### Fraud Questions
- ip_country, issuing_country, acquirer_country are THREE DIFFERENT fields
- Use whichever the question specifies
- "Fraud" = has_fraudulent_dispute = True
- **CRITICAL: "Top country for fraud" or "highest fraud" = highest fraud RATE (volume-based)**
  - Fraud rate = SUM(eur_amount WHERE has_fraudulent_dispute) / SUM(eur_amount) per group
  - This is a EUR volume RATIO, NOT a transaction count
  - Only use transaction count if the question explicitly says "number of fraud transactions"
- Monthly fraud tier (for fee matching): use pre-computed fraud_tier from monthly_merchant_stats

### Intracountry
Compute per transaction: 1 if payments.issuing_country = payments.acquirer_country, else 0.
Use payments.acquirer_country directly (it is ALREADY a country code, not an acquirer name).

### Not Applicable
No fines, penalties, or surcharges exist in the data. Only fee rules.
If asked about nonexistent concepts (fines, penalties, surcharges): answer "Not Applicable".

### Answer Formatting Rules
- Follow the Guidelines section EXACTLY for format.
- For multiple choice: answer with the EXACT option text including letter (e.g., 'B. BE', not just 'NL').
- For decimals: match exact decimal places requested.
- For lists: comma-separated, no brackets.
- For fee ID lists: just the numbers, comma-separated.

### Performance
Prefer single aggregate queries. Avoid iterative per-rule or per-ACI loops. Use GROUP BY and window functions.

### Output
FINAL_ANSWER: <answer>
```

# Tables

## Table: `uploads.main.payments`
- Name: **uploads.main.payments**
- Active: **true**
- Rows: **138236**

### Description
# uploads.main.payments

Transaction fact table containing one row per payment. This is the core table for fee calculation, fraud analysis, and payment analytics.

## Key Columns

- **psp_reference** - Unique payment transaction identifier (primary key)
- **merchant** - Name of the business accepting payment (joins to merchant_data)
- **card_scheme** - Payment network (TransactPlus, GlobalCard, NexPay, SwiftCharge)
- **year, day_of_year, hour_of_day, minute_of_hour** - Transaction timestamp components
- **is_credit** - Boolean flag: credit (1) or debit (0) card
- **eur_amount** - Transaction amount in EUR
- **ip_country** - Country from IP address
- **issuing_country** - Country of bank that issued the card
- **acquirer_country** - Country code of acquiring bank
- **device_type** - Device used for transaction
- **shopper_interaction** - Ecommerce or POS
- **aci** - Authorization Characteristics Indicator (A-G, see Fee Calculation Rules note)
- **has_fraudulent_dispute** - Boolean flag for fraud (used in fraud rate calculation)
- **is_refused_by_adyen** - Boolean flag for refusal

## Intracountry Calculation

For fee matching, calculate:
```sql
intracountry = CASE WHEN issuing_country = acquirer_country THEN 1 ELSE 0 END
```

## Usage Notes

- Use this table as the base for all fee calculations
- Join to `merchant_data` for merchant attributes needed in fee matching
- Join to `monthly_merchant_stats` for volume/fraud tiers when querying specific months
- For fraud rate: use EUR volume ratio, not transaction count
- Anonymized fields (ip_address, email_address, card_number) are hashed for privacy

### Column comments (non-empty)
- `psp_reference`: unique payment transaction identifier
- `merchant`: Name of the business accepting the payment. Each merchant has associated attributes: account_type (R/D/H/F/S/O), merchant_category_code (MCC), capture_delay settings, and acquirer relationships. Merchant characteristics combined with transaction attributes determine processing fees. See merchant_data.json and 'Merchant Account Types' note for details.
- `card_scheme`: Card payment network that facilitated the transaction. Four schemes supported: TransactPlus, GlobalCard, NexPay, SwiftCharge (analogous to Visa, Mastercard, Amex, etc.). Each scheme has different interchange rates and fee structures. Critical dimension for fee calculation and financial reconciliation.
- `year`: transaction year
- `hour_of_day`: transaction hour (0-23)
- `minute_of_hour`: transaction minute (0-59)
- `day_of_year`: transaction day (1-366)
- `is_credit`: Indicates if card is credit (1=true) or debit (0=false). Critical fee driver - credit cards have higher processing fees than debit due to increased fraud risk and higher interchange rates charged by card schemes. Use for fee analysis and to understand merchant cost structure.
- `eur_amount`: transaction amount in EUR
- `ip_country`: country from IP address
- `issuing_country`: Country of the bank that issued the card to the cardholder. Compare with acquirer_country to identify domestic vs cross-border transactions - when issuing_country = acquirer_country (intracountry=true), fees are lower. Also compare with ip_country to detect geo-mismatches which may indicate fraud.
- `device_type`: device used for transaction
- `ip_address`: anonymized IP address of shopper
- `email_address`: anonymized shopper email address
- `card_number`: anonymized card number
- `shopper_interaction`: Transaction channel: 'Ecommerce' = online/card-not-present, 'POS' = in-person/card-present at physical point-of-sale. Card-present (POS) transactions typically have lower fraud risk and lower fees. Related to ACI - POS usually uses ACI A/B/C while Ecommerce uses D/E/F/G.
- `card_bin`: first 4-6 digits of card (BIN)
- `has_fraudulent_dispute`: Indicates if the issuing bank reported this transaction as fraudulent (1=fraud, 0=legitimate). Used to calculate monthly fraud rate = (fraudulent volume / total volume). Fraud rate directly impacts fee tier - merchants with >8.3% fraud pay significantly higher fees. Critical KPI to monitor. See 'Payment Processing Fee Calculation Model' note.
- `is_refused_by_adyen`: flag if transaction was refused by Adyen
- `aci`: Authorization Characteristics Indicator (ACI) - standardized code identifying transaction flow and authentication method. Values: A=Card Present Non-authenticated, B=Card Present Authenticated (PIN/signature), C=Tokenized Mobile Device (Apple/Google Pay), D=Card Not Present Card-on-File, E=Card Not Present Recurring Billing, F=Card Not Present 3D Secure, G=Card Not Present Non-3D Secure. Critical for fee calculation - more secure authentication (B, C, F) results in lower fees. See 'Authorization Characteristics Indicator' note for details.
- `acquirer_country`: Country code of the acquiring bank processing the transaction. Critical for fee calculation - when acquirer_country matches issuing_country (intracountry/domestic transaction), fees are significantly lower than cross-border. Use acquirer_countries table to map acquirer names to countries. Best practice: route transactions through local acquirers to minimize costs.

## Table: `uploads.main.merchant_category_codes`
- Name: **uploads.main.merchant_category_codes**
- Active: **true**
- Rows: **769**

### Description
# uploads.main.merchant_category_codes

Reference table mapping 4-digit MCC codes to industry descriptions. Used for lookup/reference only.

## Key Columns

- **mcc** - Four-digit Merchant Category Code (primary key)
- **description** - Human-readable industry description

## Usage

Join to `merchant_data.merchant_category_code` to get industry labels for reporting and analysis.

Join key: `merchant_data.merchant_category_code = merchant_category_codes.mcc`

### Column comments (non-empty)
- `mcc`: Four-digit Merchant Category Code assigned by card schemes (Visa, Mastercard, etc.) to classify merchant business types. Used for risk assessment, fraud detection, and fee determination. Over 400 standard codes exist. Join to merchant data or derive from merchant table to understand industry distribution. Critical for fee calculation - different MCCs have different interchange rates and risk profiles.
- `description`: Human-readable description of the merchant category. Examples: 'Restaurants, Eating Places' (5812), 'Hotels, Motels, Resorts' (7011), 'Computer Programming, Data Processing' (7372). Use to enrich transaction reports, industry analysis, and merchant segmentation. Some descriptions include specific brand names (airlines, hotel chains) for specialized MCCs.

## Table: `uploads.main.acquirer_countries`
- Name: **uploads.main.acquirer_countries**
- Active: **true**
- Rows: **8**

### Description
# uploads.main.acquirer_countries

Reference table mapping acquirer names to their operating countries. Used for lookup/reference only.

## Key Columns

- **acquirer** - Acquirer bank name (primary key)
- **country_code** - ISO 2-letter country code where acquirer operates

## Usage Note

This is a **lookup table only**. The `payments.acquirer_country` field is already a country code (e.g., "NL", "US", "IT") and does NOT require joining to this table.

Use this table to:
- Map `merchant_data.primary_acquirer` (acquirer name) to countries
- Understand acquirer geographic coverage

**Do NOT use for intracountry calculation** - `payments.acquirer_country` is already the country code needed.

### Column comments (non-empty)
- `acquirer`: Unique identifier for acquiring banks that process card payments on behalf of merchants. Examples: gringotts, medici, bank_of_springfield, dagoberts_vault. Each merchant works with one or more acquirers (listed in merchant_data.json). Use to map acquirer_country in payments table to specific acquiring bank names.
- `country_code`: ISO 2-letter country code where the acquirer operates. Critical for identifying domestic (intracountry) vs cross-border transactions. When payments.issuing_country = acquirer_countries.country_code (via payments.acquirer_country), the transaction qualifies for lower 'intracountry' fees. Use to optimize routing strategies for fee reduction.

## Table: `uploads.main.merchant_data`
- Name: **uploads.main.merchant_data**
- Active: **true**
- Rows: **30**

### Description
# uploads.main.merchant_data

Merchant profile table used for fee matching dimensions. One row per merchant.

## Key Columns

- **merchant** - Unique merchant identifier (primary key, joins to payments.merchant)
- **account_type** - Business model classification (R/D/H/F/S/O)
- **merchant_category_code** - 4-digit MCC code (joins to merchant_category_codes)
- **capture_delay** - Raw capture timing setting
- **capture_delay_bucket** - Pre-computed bucket for fee matching (immediate, <3, 3-5, >5, manual)
- **primary_acquirer** - Main acquiring bank(s) for merchant
- **acquirer** - All acquiring banks associated with merchant

## Usage in Fee Matching

This table provides merchant-level attributes required for fee matching:
- Use **capture_delay_bucket** (not raw capture_delay) when matching to fees.capture_delay
- account_type and merchant_category_code are matched against fees table wildcards
- Join on payments.merchant = merchant_data.merchant

## Critical Rules

- ALWAYS use `capture_delay_bucket` for fee matching, never remap from raw `capture_delay`
- primary_acquirer links to acquirer_countries table for acquirer geography lookup

### Column comments (non-empty)
- `merchant`: unique merchant identifier
- `account_type`: merchant business model classification (e.g., Retail, Digital, Hospitality, Franchise, SaaS)
- `merchant_category_code`: 4-digit industry code (MCC) assigned by card schemes; defines merchant's business type
- `capture_delay`: Merchant's configured capture timing - specific value like "immediate", "1", "2", "3", "7", "manual". CRITICAL: Must map to fee rule buckets for matching: immediate→immediate, 1/2→<3, 3/4/5→3-5, 7→>5, manual→manual. This is the RAW merchant setting; use capture_delay_bucket for pre-mapped bucket value. Lower delays (immediate/<3) typically result in lower fees.
- `capture_delay_bucket`: MANDATORY FOR FEE MATCHING. Pre-computed capture delay bucket that matches fees.capture_delay values directly. Values: immediate, <3 (1-2 days), 3-5 (3-5 days), >5 (7+ days), manual. Derived from raw capture_delay using mapping: immediate→immediate, 1/2→<3, 3/4/5→3-5, 7→>5, manual→manual. ALWAYS use this pre-computed field when matching with fees table - do NOT recompute from raw capture_delay to avoid mapping errors.
- `primary_acquirer`: main acquiring bank(s) for merchant, used for settlement and acquirer country lookup
- `acquirer`: list of all acquiring banks associated with merchant (may include multiple, encoded as string)

## Table: `uploads.main.monthly_merchant_stats`
- Name: **uploads.main.monthly_merchant_stats**
- Active: **true**
- Rows: **60**

### Description
# uploads.main.monthly_merchant_stats

Precomputed monthly tiers for volume and fraud. One row per merchant/month. **MANDATORY for date/month fee calculations.**

## Key Columns

- **merchant, year, month** - Composite primary key
- **total_volume_eur** - Total payment volume in EUR for merchant/month
- **total_txn_count** - Total transaction count
- **fraud_volume_eur** - Fraudulent payment volume in EUR
- **fraud_txn_count** - Fraudulent transaction count
- **fraud_rate** - fraud_volume_eur / total_volume_eur (volume-based ratio)
- **volume_tier** - Pre-computed tier (<100k, 100k-1m, 1m-5m, >5m)
- **fraud_tier** - Pre-computed tier (<7.2%, 7.2%-7.7%, 7.7%-8.3%, >8.3%)

## Critical Usage Rules

**MANDATORY for fee matching on specific dates/months:**
- Use `volume_tier` to match against `fees.monthly_volume`
- Use `fraud_tier` to match against `fees.monthly_fraud_level`
- **NEVER skip this table** - failure to include monthly tiers returns incorrect superset of fees

**Date to month conversion:**
- Days 1-31 → Month 1
- Days 32-59 → Month 2
- Days 60-90 → Month 3
- etc.

## Usage Example

```sql
-- Get monthly tiers
SELECT volume_tier, fraud_tier
FROM uploads.main.monthly_merchant_stats
WHERE merchant = :merchant AND year = :year AND month = :month
```

## Do Not Recompute

These tiers are pre-computed and canonical. Do NOT recalculate from payments table.

### Column comments (non-empty)
- `merchant`: merchant identifier (business name)
- `year`: calendar year of aggregated stats
- `month`: calendar month of aggregated stats (1–12)
- `total_volume_eur`: total processed payment volume in EUR for merchant/month
- `total_txn_count`: total number of transactions processed for merchant/month
- `fraud_volume_eur`: total EUR volume of transactions flagged as fraudulent for merchant/month
- `fraud_txn_count`: number of fraudulent transactions for merchant/month
- `fraud_rate`: ratio of fraud_volume_eur to total_volume_eur (fraudulent volume share)
- `volume_tier`: processed volume category for merchant/month (e.g., <100k, 100k–1m)
- `fraud_tier`: fraud rate category for merchant/month (e.g., <7.2%, 7.2%–7.7%, >8.3%)

## Table: `uploads.main.fees`
- Name: **uploads.main.fees**
- Active: **true**
- Rows: **1000**

### Description
# uploads.main.fees

Fee rules table defining pricing structure. One row per fee rule (1,000 rules total).

## Key Columns

- **ID** - Unique fee rule identifier (primary key)
- **card_scheme** - Card network (required match to payments.card_scheme)
- **account_type** - JSON array of account types ([] = wildcard)
- **capture_delay** - Settlement delay bucket (NULL = wildcard)
- **monthly_fraud_level** - Fraud tier (NULL = wildcard)
- **monthly_volume** - Volume tier (NULL = wildcard)
- **merchant_category_code** - JSON array of MCCs ([] = wildcard)
- **is_credit** - Card type filter ("true"/"false"/NULL)
- **aci** - JSON array of ACI codes ([] = wildcard)
- **intracountry** - Domestic vs cross-border filter ("true"/"false"/NULL)
- **fixed_amount** - Fixed fee in EUR
- **rate** - Variable fee in basis points

## Fee Formula

```
fee = fixed_amount + (rate * eur_amount / 10000.0)
```

## Wildcard Rules

- **NULL** = applies to all values
- **[]** (empty JSON array) = applies to all values
- Non-null/non-empty = must match exactly

## Matching Logic

Fee matching is strict `AND` across all non-null/non-empty constraints:
1. `card_scheme` must match exactly (required)
2. All other fields: NULL/[] = pass automatically, otherwise must match
3. If multiple rules match: select highest specificity (most constraints), average if tied
4. If no rules match: fee is 0 (never drop transaction)

## Intracountry Matching

Calculate transaction's intracountry flag:
```sql
intracountry = CASE WHEN issuing_country = acquirer_country THEN 1 ELSE 0 END
```

Match against fees.intracountry:
- fees.intracountry = NULL → applies to both domestic and cross-border
- fees.intracountry = "true" → applies only when intracountry = 1
- fees.intracountry = "false" → applies only when intracountry = 0

## JSON Array Matching

For columns stored as JSON arrays (account_type, merchant_category_code, aci):
```sql
-- String arrays
(fees.account_type = '[]' OR value IN (SELECT value FROM json_each(fees.account_type)))

-- Integer arrays (MCC)
(fees.merchant_category_code = '[]' OR value IN (SELECT CAST(value AS INTEGER) FROM json_each(fees.merchant_category_code)))
```

## Usage Notes

- See SQL Templates & Query Patterns note for complete fee calculation queries
- Use specificity calculation to resolve multiple matching rules
- Monthly tier filters (volume_tier, fraud_tier) must come from monthly_merchant_stats

### Column comments (non-empty)
- `ID`: Primary key - unique identifier for each fee rule (also called rule_id in some contexts)
- `card_scheme`: Card payment network - must match payments.card_scheme exactly for rule to apply
- `account_type`: Merchant account types this rule applies to. JSON array format: ["R", "D"] or [] for wildcard (all types). Match against merchant_data.account_type.
- `capture_delay`: Settlement delay bucket. Values: immediate, <3, 3-5, >5, manual, or NULL for wildcard. Match against merchant_data.capture_delay_bucket.
- `monthly_fraud_level`: Fraud tier from monthly_merchant_stats. Values: <7.2%, 7.2%-7.7%, 7.7%-8.3%, >8.3%, or NULL (applies to all fraud levels)
- `monthly_volume`: Volume tier from monthly_merchant_stats. Values: <100k, 100k-1m, 1m-5m, >5m, or NULL (applies to all volumes)
- `merchant_category_code`: Merchant category codes. JSON array format: [5812, 7997] or [] for wildcard (all MCCs). Match against merchant_data.merchant_category_code.
- `is_credit`: Credit vs debit card filter. Values: "true" (credit only), "false" (debit only), NULL (both). Match against CAST(payments.is_credit AS TEXT).
- `aci`: Authorization Characteristics Indicator codes. JSON array: ["A", "B"] or [] for wildcard. Match against payments.aci.
- `fixed_amount`: Fixed fee component in EUR. Total fee = fixed_amount + (rate * eur_amount / 10000)
- `rate`: Variable fee rate in basis points (1 bp = 0.01%). Applied as rate * eur_amount / 10000
- `intracountry`: ✅ NOW PRESENT! Domestic vs cross-border filter. Values: "true" (domestic only - issuing_country = acquirer_country), "false" (cross-border only), NULL (applies to both). 56% NULL, 22.5% false, 21.4% true. Fee IDs 304, 861, 871 have "true" (domestic-only).
