# Dot Context Snapshot

- Exported: **2026-02-12 11:10:48 UTC**
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
- Body length: **2800 chars**

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

### Fraud Questions
- ip_country, issuing_country, acquirer_country are THREE DIFFERENT fields
- Use whichever the question specifies
- "Fraud" = has_fraudulent_dispute = True
- General fraud questions: COUNT transactions
- Monthly fraud tier (for fee matching): volume-based ratio from monthly_merchant_stats

### Intracountry
Compute per transaction: 1 if payments.issuing_country = payments.acquirer_country, else 0.
Use payments.acquirer_country directly.

### Specificity Rule
- "Which fee IDs apply?" → ALL matching IDs
- "What fee is charged?" → most specific rule (most non-null criteria); average if tied

### Not Applicable
No fines, penalties, or surcharges exist. Only fee rules. If asked about nonexistent concepts: Not Applicable.

### Performance
Prefer single aggregate queries. Avoid iterative per-rule or per-ACI loops. Use GROUP BY and window functions.

### Output
FINAL_ANSWER: <answer>
```

## Asset: `org_instructions`
- Name: **DABStep Fee & Domain Instructions**
- Subtype: `note`
- Active: **true**
- Body length: **5843 chars**

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

### Fraud Questions
- ip_country, issuing_country, acquirer_country are THREE DIFFERENT fields
- Use whichever the question specifies
- "Fraud" = has_fraudulent_dispute = True
- General fraud questions: COUNT transactions
- Monthly fraud tier (for fee matching): volume-based ratio from monthly_merchant_stats

### Intracountry
Compute per transaction: 1 if payments.issuing_country = payments.acquirer_country, else 0.
Use payments.acquirer_country directly.

### Specificity Rule
- "Which fee IDs apply?" → ALL matching IDs
- "What fee is charged?" → most specific rule (most non-null criteria); average if tied

### Not Applicable
No fines, penalties, or surcharges exist. Only fee rules. If asked about nonexistent concepts: Not Applicable.

### Performance
Prefer single aggregate queries. Avoid iterative per-rule or per-ACI loops. Use GROUP BY and window functions.

### Output
FINAL_ANSWER: <answer>


## MANDATORY: Monthly Tier Lookup for Fee Questions
For ANY question about fees involving a specific merchant or time period:
1. FIRST look up the merchant's monthly stats:
   ```sql
   SELECT volume_tier, fraud_tier
   FROM uploads.main.monthly_merchant_stats
   WHERE merchant = '<merchant_name>' AND year = <year> AND month = <month>;
   ```
2. THEN filter the fees table using those tiers:
   ```sql
   WHERE (monthly_volume IS NULL OR monthly_volume = '<volume_tier>')
     AND (monthly_fraud_level IS NULL OR monthly_fraud_level = '<fraud_tier>')
   ```
3. NEVER skip this step — omitting tier filters produces a SUPERSET of fees → WRONG ANSWER.


## CRITICAL: day_of_year to Month Conversion for Fee Lookups
When a question specifies a date (e.g., 'the 10th of 2023' means day_of_year=10):
1. Convert day_of_year to month: Jan=1-31, Feb=32-59, Mar=60-90, Apr=91-120, May=121-151, Jun=152-181, Jul=182-212, Aug=213-243, Sep=244-273, Oct=274-304, Nov=305-334, Dec=335-365
2. Look up monthly_merchant_stats for that merchant/year/month
3. Use volume_tier and fraud_tier to filter fees
4. Also filter by the merchant's account_type, mcc, capture_delay_bucket, and the payment's card_scheme, aci, is_credit, intracountry
5. intracountry = CASE WHEN issuing_country = acquirer_country THEN 1 ELSE 0 END



## Answer Formatting Rules
- Follow the Guidelines section EXACTLY for format.
- For multiple choice: answer with the EXACT option text including letter (e.g., 'B. BE', not just 'NL').
- For decimals: match exact decimal places requested.
- For lists: comma-separated, no brackets.



## Fee Matching Filter Logic
- NULL or empty list in a fee field = wildcard (matches everything).
- For list fields: the value must be IN the list.
- intracountry: CASE WHEN issuing_country = acquirer_country THEN 1 ELSE 0 END.


## Fee Calculation Precision
fee = fixed_amount + (rate * eur_amount / 10000.0)
- Use DOUBLE precision throughout.
- Sum fees across ALL matching transactions.
- When comparing scenarios (delta), compute each scenario's total separately then subtract: delta = new_total - old_total.
- Preserve full decimal precision unless the guidelines request rounding.



## Fee Rule Matching Checklist
To find applicable fee IDs for a merchant+transaction:
1. Get merchant's: account_type, merchant_category_code, capture_delay_bucket, acquirer
2. Get transaction's: card_scheme, aci, is_credit
3. Compute: intracountry = (issuing_country = acquirer_country)
4. Get monthly tiers: volume_tier, fraud_tier from monthly_merchant_stats
5. A fee matches if ALL non-null criteria match:
   - card_scheme = exact match
   - account_type: list contains merchant's type (or empty = all)
   - aci: list contains payment's ACI (or empty = all)
   - mcc: list contains merchant's MCC (or empty = all)
   - is_credit: matches or NULL
   - intracountry: matches or NULL
   - capture_delay: matches merchant_data.capture_delay_bucket or NULL
   - monthly_volume: matches volume_tier or NULL
   - monthly_fraud_level: matches fraud_tier or NULL
```

# Tables

## Table: `uploads.main.payments`
- Name: **uploads.main.payments**
- Active: **true**
- Rows: **138236**

### Description
# Payment Transactions

Each row represents a single card payment transaction processed by the payment processor, uniquely identified by `psp_reference`. This is the core transaction fact table for payment analysis, fee calculation, and merchant performance monitoring.

## Business Context

This table captures the complete lifecycle of payment transactions from authorization through settlement. Transactions flow from cardholders through merchants, card schemes (TransactPlus, GlobalCard, NexPay, SwiftCharge), acquiring banks, and issuing banks.

## Key Use Cases

### Fee Calculation and Revenue Analysis
- Join with merchant metadata (merchant_data.json) to get account_type, MCC, capture_delay
- Join with fee rules (fees.json) matching on card_scheme, is_credit, aci, merchant characteristics
- Calculate fees using: `fee = fixed_amount + (rate × eur_amount / 10000)`
- Identify domestic vs cross-border by comparing issuing_country with acquirer_country

### Fraud Monitoring and Risk Management
- **Fraud Rate (VOLUME-based)**: `SUM(CASE WHEN has_fraudulent_dispute = 'True' THEN eur_amount ELSE 0 END) / SUM(eur_amount)` by merchant/month - this is the ratio used for fee tier matching
- **Fraud Transaction Count**: `COUNT(*) WHERE has_fraudulent_dispute = 'True'` - use for distribution analysis and rankings
- **Fraud Volume EUR**: `SUM(eur_amount WHERE has_fraudulent_dispute = 'True')` - total EUR amount of fraudulent transactions
- Target fraud rate <7.2% for optimal fees; >8.3% triggers significant fee increases
- Compare ip_country vs issuing_country vs acquirer_country to detect geo-mismatches
- Monitor fraud by ACI type - Type G (non-3D Secure) highest risk

### Authorization Performance
- Authorization rate: `1 - (SUM(is_refused_by_adyen) / COUNT(*))` - target >95%
- Analyze refusals by card_scheme, issuing_country, device_type to identify patterns
- Monitor by merchant to identify technical or risk issues

### Merchant Performance and Optimization
- Monthly volume by merchant (critical for fee tier qualification)
- Channel mix analysis (Ecommerce vs POS) - POS typically lower fees
- ACI distribution - ensure optimal authentication methods for fee minimization
- Domestic transaction percentage - maximize for lower costs

## Data Quality Notes

**Timestamp Construction**: Date/time stored as components requiring reconstruction:
- Full timestamp = `year + day_of_year + hour_of_day + minute_of_hour`
- day_of_year is 1-366 format (Julian day)
- Consider creating derived timestamp field for time-series analysis

**Anonymized Identifiers**: Hashed values enable privacy-safe analysis:
- `card_number`, `email_address`, `ip_address` are one-way hashed
- Can be used for repeat-customer, velocity, and behavior analyses
- ~19% NULL rate on ip_address, ~9% NULL on email_address
- **Repeat Customer Definition**: A shopper with the same `email_address` appearing in >1 transaction (use `GROUP BY email_address HAVING COUNT(*) > 1`)

**Geographic Dimensions**: Three country fields serve different purposes:
- `ip_country`: Shopper's location at transaction time
- `issuing_country`: Bank that issued the card
- `acquirer_country`: Country code of the acquiring bank processing for merchant (ALREADY a country code like "NL", "US", "IT" - NOT an acquirer name)
- Comparing these reveals cross-border patterns and fraud indicators
- **CRITICAL**: `acquirer_country` is already a country code. Do NOT confuse with acquirer names from `acquirer_countries` table which maps acquirer NAMES to countries.

## Critical Relationships

- **merchant** → merchant_data (account_type, MCC, capture_delay, primary_acquirer)
- **acquirer_country** is ALREADY a country code (no lookup needed) - compares directly with issuing_country for intracountry calculation
- **merchant_data.primary_acquirer** (acquirer NAME) → acquirer_countries.acquirer (to get acquirer's country)
- **card_scheme + merchant attributes + transaction attributes** → fees (fee rule matching)
- **merchant_data.merchant_category_code** → merchant_category_codes.mcc (industry descriptions)

## Key Performance Indicators (KPIs)

1. **Authorization Rate**: Target >95% - percentage of non-refused transactions
2. **Fraud Rate (VOLUME-based)**: Target <7.2% - ratio of fraudulent EUR volume to total EUR volume (NOT transaction count)
3. **Chargeback Rate**: Target <1% - monitor for scheme compliance
4. **Average Transaction Value**: By merchant, scheme, channel
5. **Domestic Transaction %**: Maximize for fee optimization
6. **ACI Distribution**: Ensure secure authentication methods (B, C, F over G)

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
# Merchant Category Codes (MCC) Reference

This is a dimension/lookup table mapping four-digit Merchant Category Codes to their human-readable descriptions. MCCs are standardized codes assigned by card schemes (Visa, Mastercard) to classify merchant business types.

## Purpose

- **Transaction Enrichment**: Join to payments or merchant data to add industry labels
- **Industry Analysis**: Group transactions by category for reporting and benchmarking
- **Fee Calculation**: MCCs are a key input to fee rule matching - different industries have different processing costs and risk profiles
- **Risk Assessment**: High-risk MCCs (travel, digital goods, gambling) typically have higher fees and stricter monitoring

## MCC Code Structure

- **First 2 digits**: Broad industry category (e.g., 54xx = Restaurants, 70xx = Hotels/Lodging)
- **Last 2 digits**: Specific subcategory

## Common MCC Examples in Merchant Data

- **5812**: Restaurants, Eating Places (Hospitality merchants)
- **5814**: Fast Food Restaurants (Hospitality merchants)
- **5942**: Bookstores (Retail merchants)
- **7372**: Computer Programming, Data Processing (Digital/SaaS merchants)
- **7993**: Golf Courses - Public (Franchise/Platform merchants)
- **7997**: Membership Clubs - Sports, Recreation, Athletic (Franchise merchants)
- **8011**: Doctors and Physicians
- **8021**: Dentists and Orthodontists
- **8062**: Hospitals
- **8299**: Schools and Educational Services (SaaS/Platform merchants)

## Usage in Fee Calculation

MCCs influence processing fees through:
1. **Interchange rate qualification**: Some MCCs receive preferential rates (healthcare, utilities)
2. **Risk premiums**: High-risk MCCs (travel, digital) pay higher fees
3. **Fee rule matching**: fees.json contains MCC-specific rules with different fixed_amount and rate values

## Data Quality Notes

- The "Unnamed: 0" column is an internal index and can be ignored for analysis
- Each MCC is unique and maps to exactly one description
- Some descriptions include specific brand names (airlines, hotel chains) for specialized industry codes

### Column comments (non-empty)
- `mcc`: Four-digit Merchant Category Code assigned by card schemes (Visa, Mastercard, etc.) to classify merchant business types. Used for risk assessment, fraud detection, and fee determination. Over 400 standard codes exist. Join to merchant data or derive from merchant table to understand industry distribution. Critical for fee calculation - different MCCs have different interchange rates and risk profiles.
- `description`: Human-readable description of the merchant category. Examples: 'Restaurants, Eating Places' (5812), 'Hotels, Motels, Resorts' (7011), 'Computer Programming, Data Processing' (7372). Use to enrich transaction reports, industry analysis, and merchant segmentation. Some descriptions include specific brand names (airlines, hotel chains) for specialized MCCs.

## Table: `uploads.main.acquirer_countries`
- Name: **uploads.main.acquirer_countries**
- Active: **true**
- Rows: **8**

### Description
# Acquirer-Country Mapping

Dimension table mapping acquiring banks to their operating countries. Acquirers are financial institutions that process card payment transactions on behalf of merchants.

## Purpose

- **Geographic Routing Analysis**: Understand which acquirers operate in which countries
- **Intracountry Transaction Identification**: Critical for fee optimization - when issuing_country = acquirer country, fees are significantly lower (20-50% reduction)
- **Merchant-Acquirer Relationships**: Cross-reference with merchant_data.json to see which acquirers each merchant uses
- **Strategic Routing**: Enable analysis of routing strategies to maximize domestic transaction percentage

## Business Context

Acquiring banks are regional - each operates in specific countries. Merchants may work with multiple acquirers to support transactions in different markets.

**Best Practice**: Route transactions through local acquirers (same country as card issuer) to minimize fees and maximize authorization rates.

## Available Acquirers

- **gringotts** (GB - United Kingdom)
- **medici** (IT - Italy)
- **bank_of_springfield** (US - United States)
- **dagoberts_vault** (NL - Netherlands)
- **dagoberts_geldpakhuis** (NL - Netherlands)
- **tellsons_bank** (GB - United Kingdom)
- **the_savings_and_loan_bank** (US - United States)
- **lehman_brothers** (US - United States)

## Usage Examples

**Identify Cross-Border Transactions**:
```sql
SELECT *
FROM payments p
LEFT JOIN acquirer_countries ac ON p.acquirer_country = ac.country_code
WHERE p.issuing_country != ac.country_code
```

**Calculate Domestic Transaction Rate by Merchant**:
```sql
SELECT merchant,
  SUM(CASE WHEN issuing_country = acquirer_country THEN 1 ELSE 0 END) / COUNT(*) as domestic_rate
FROM payments
GROUP BY merchant
```

## Relationship to Fee Calculation

The `intracountry` field in fee rules (fees.json) is determined by comparing:
- **issuing_country** (from payments table)
- **country_code** (from this table, via acquirer_country)

When they match: `intracountry = true` → Lower fees
When they differ: `intracountry = false` → Higher cross-border fees

### Column comments (non-empty)
- `acquirer`: Unique identifier for acquiring banks that process card payments on behalf of merchants. Examples: gringotts, medici, bank_of_springfield, dagoberts_vault. Each merchant works with one or more acquirers (listed in merchant_data.json). Use to map acquirer_country in payments table to specific acquiring bank names.
- `country_code`: ISO 2-letter country code where the acquirer operates. Critical for identifying domestic (intracountry) vs cross-border transactions. When payments.issuing_country = acquirer_countries.country_code (via payments.acquirer_country), the transaction qualifies for lower 'intracountry' fees. Use to optimize routing strategies for fee reduction.

## Table: `uploads.main.fees`
- Name: **uploads.main.fees**
- Active: **true**
- Rows: **1000**

### Description
# Fee Rules

Each row represents a single fee pricing rule used to calculate per-transaction processing fees. This table contains **1,000 fee rules** covering all combinations of merchant and transaction characteristics.

## Fee Calculation Formula

```
fee = fixed_amount + (rate × eur_amount / 10000.0)
```

Where:
- `fixed_amount` - Per-transaction fee in EUR (e.g., €0.10)
- `rate` - Basis points (e.g., 19 = 0.19%)
- `eur_amount` - Transaction amount from payments table

## Wildcard Matching Logic

**CRITICAL**: Fee rules use **wildcard matching** where empty list (`[]`) or NULL values mean "applies to all":

- Empty list `[]` or NULL in a column = rule matches ANY value for that criterion
- A fee rule matches a payment if **ALL non-empty/non-null criteria match**
- List fields (account_type, aci, mcc/merchant_category_code) match if the value is IN the list OR list is empty `[]`
- When multiple rules match, context determines behavior:
  - **"Which fee IDs apply/are applicable?"** → Return ALL matching fee IDs (no specificity filter)
  - **"What fee would be charged?" / "Total fees" / "Calculate the fee"** → Select the MOST SPECIFIC rule (most non-null/non-empty criteria)
- **Specificity count** = number of non-null, non-empty-list criteria in the fee rule. Higher count = more specific.

### Matching Criteria

A fee rule MATCHES a payment/merchant combination if **ALL** of the following are true:

| Fee Column | Matches Against | Source | Match Logic |
|-----------|----------------|--------|-------------|
| `card_scheme` | `card_scheme` | payments | ALWAYS required (never null), must match exactly |
| `is_credit` | `is_credit` | payments | NULL OR equals payment value (with type casting) |
| `aci` | `aci` | payments | Empty list `[]` OR payment value IN list |
| `account_type` | `account_type` | merchant_data | Empty list `[]` OR merchant value IN list |
| `mcc` / `merchant_category_code` | `merchant_category_code` | merchant_data | Empty list `[]` OR merchant MCC IN list |
| `capture_delay` | `capture_delay_bucket` | merchant_data | NULL OR matches merchant's bucket (see mapping below) |
| `monthly_fraud_level` | (computed monthly) | payments | NULL OR computed fraud ratio matches tier |
| `monthly_volume` | (computed monthly) | payments | NULL OR computed EUR volume matches tier |
| `intracountry` | (computed per txn) | payments | NULL OR matches (issuing_country = acquirer_country) |

### Intracountry Calculation

The `intracountry` field requires a runtime calculation:

```sql
intracountry = CASE
  WHEN issuing_country = acquirer_country THEN 1
  ELSE 0
END
```

- `1` = Domestic transaction (same country)
- `0` = Cross-border transaction (different countries)

## Fee Matching Rules (Semantic)

**For date/month-specific fee questions**: Use the monthly_merchant_stats table to look up the merchant's volume_tier and fraud_tier for that month. Then filter fee rules accordingly.

**List column matching**: The columns account_type, aci, and merchant_category_code/mcc contain JSON-style arrays like ['R', 'D'] or [5812, 5942]. A fee rule matches if the array is empty [] (matches all) or the target value appears in the array.

**Intracountry**: The intracountry column is 1.0 (domestic), 0.0 (cross-border), or NULL (matches all). Compute from payments: 1 if issuing_country = acquirer_country, else 0.

**is_credit**: Stored as VARCHAR text in fees ("true"/"false"/NULL). In payments it is BOOLEAN. Compare appropriately.

**capture_delay**: Use merchant_data.capture_delay_bucket which already maps to the fee bucket values (immediate, <3, 3-5, >5, manual). Match directly against fees.capture_delay.

## Column Details

### Rule Segmentation

- **`card_scheme`**: TransactPlus, GlobalCard, NexPay, SwiftCharge (or empty = all)
- **`is_credit`**: "true" (credit card), "false" (debit card), or empty = all
- **`aci`**: Array of ACI codes (A-G) or empty = all authentication types
- **`account_type`**: Array of merchant types (R, D, H, F, S, O) or empty = all
- **`mcc`**: Array of merchant category codes or empty = all industries
- **`capture_delay`**: immediate, <3, 3-5, >5, manual, or empty = all
- **`monthly_volume`**: <100k, 100k-1m, 1m-5m, >5m, or empty = all (80% NULL)
- **`monthly_fraud_level`**: <7.2%, 7.2%-7.7%, 7.7%-8.3%, >8.3%, or empty = all (90% NULL)
- **`intracountry`**: 1.0 (domestic), 0.0 (cross-border), or NULL = all

### Fee Components

- **`fixed_amount`**: Per-transaction fixed fee (€0.01 to €0.12)
- **`rate`**: Variable fee in basis points (25 to 86 bps typical range)

## Key Use Cases

1. **Fee Calculation**: Join with payments + merchant_data to calculate actual fees
2. **Fee Optimization**: Identify which merchant behaviors trigger higher fees
3. **Scenario Modeling**: Predict fee impact of volume changes, authentication improvements
4. **Revenue Forecasting**: Model fee income under different transaction mixes

## Data Quality

- **Sample size**: 1,000 rules covering all dimensional combinations
-
…(truncated)…

### Column comments (non-empty)
- `rule_id`: unique fee rule identifier
- `card_scheme`: card network (e.g., TransactPlus, SwiftCharge)
- `is_credit`: Credit card flag. Values: "true" (credit card only), "false" (debit card only), NULL (WILDCARD - applies to BOTH credit AND debit). CRITICAL WILDCARD RULE: When filtering for "credit transactions", include rules where is_credit = NULL OR is_credit = 'true' (exclude 'false'). When filtering for "debit transactions", include rules where is_credit = NULL OR is_credit = 'false' (exclude 'true'). NULL means the fee rule applies to ALL card types. payments.is_credit is BOOLEAN, this field is VARCHAR - cast both to TEXT for comparison.
- `aci`: authorization characteristics indicator codes (authentication method)
- `account_type`: merchant account type(s) (e.g., R, D, H, F, S)
- `mcc`: merchant category code(s) (industry classification)
- `capture_delay`: settlement timing after authorization (immediate, <3, 3-5, >5, manual)
- `fixed_amount`: per-transaction fixed fee (EUR)
- `rate`: variable fee in basis points (0.01% units)
- `ID`: unique row identifier (primary key)
- `monthly_fraud_level`: monthly fraud rate tier (e.g., <3%, 3%-5%, >8.3%)
- `monthly_volume`: monthly transaction volume tier (e.g., <100k, 100k-1m, >5m)
- `merchant_category_code`: merchant category code(s) (alternative to mcc)
- `intracountry`: MANDATORY MATCHING CRITERION. Domestic vs cross-border indicator. Values: 1.0 (domestic - issuing_country = acquirer_country), 0.0 (cross-border - different countries), NULL (WILDCARD - applies to both domestic and cross-border). Calculate at runtime: CASE WHEN issuing_country = acquirer_country THEN 1 ELSE 0 END. When matching fee rules, if intracountry is NULL, the rule applies to ALL transactions. If 1.0, only domestic. If 0.0, only cross-border. Domestic transactions have significantly lower fees.

## Table: `uploads.main.merchant_data`
- Name: **uploads.main.merchant_data**
- Active: **true**
- Rows: **30**

### Description
Each row represents a merchant configuration/profile used to enrich transactions for analytics and fee-rule matching. Key attributes include account_type, merchant_category_code (MCC), and capture_delay (raw setting plus a pre-bucketed capture_delay_bucket) which drive pricing, settlement-timing analysis, and segmentation by industry/business model. Use this table to join onto payments by merchant, and to look up MCC metadata and acquirer geography via the referenced merchant_category_codes and acquirer_countries tables (primary_acquirer/acquirer may contain multiple acquirers encoded as a string).

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
# Monthly Merchant Stats - AUTHORITATIVE SOURCE FOR FEE MATCHING

Each row represents a merchant's aggregated payment performance for a given **natural calendar month** (year, month), uniquely identified by (merchant, year, month).

## Purpose

This is the **AUTHORITATIVE PRE-COMPUTED SOURCE** for:
- `volume_tier` - Used to filter `fees.monthly_volume` during fee rule matching
- `fraud_tier` - Used to filter `fees.monthly_fraud_level` during fee rule matching

**CRITICAL FOR FEE MATCHING**: When questions reference a specific date or month, ALWAYS use this table to lookup the merchant's `volume_tier` and `fraud_tier` for that month. Do NOT recompute from payments table unless this table is unavailable.

## Data Dictionary

- **total_volume_eur**: SUM(eur_amount) for merchant/month
- **fraud_volume_eur**: SUM(eur_amount WHERE has_fraudulent_dispute = 'True') for merchant/month
- **fraud_rate**: fraud_volume_eur / total_volume_eur (VOLUME-based ratio, NOT transaction count)
- **volume_tier**: Pre-computed tier (<100k, 100k-1m, 1m-5m, >5m) matching `fees.monthly_volume` values
- **fraud_tier**: Pre-computed tier (<7.2%, 7.2%-7.7%, 7.7%-8.3%, >8.3%) matching `fees.monthly_fraud_level` values

## Usage for Fee Matching

```sql
-- CORRECT: Use this table for fee matching
SELECT mms.volume_tier, mms.fraud_tier
FROM monthly_merchant_stats mms
WHERE mms.merchant = '<merchant_name>'
  AND mms.year = 2023
  AND mms.month = 1  -- January

-- Then filter fees:
WHERE (fees.monthly_volume IS NULL OR fees.monthly_volume = mms.volume_tier)
  AND (fees.monthly_fraud_level IS NULL OR fees.monthly_fraud_level = mms.fraud_tier)
```

Useful for monthly trend monitoring, merchant benchmarking, and tier-based fee/risk reporting.

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
