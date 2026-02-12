# Failure Analysis Report

- **Results file:** `artifacts\runs\20260212_100850_5d290c\results.jsonl`
- **Total questions:** 10
- **Correct:** 5
- **Accuracy:** 50.0%

## Error Type Breakdown

| Error Type | Count |
|------------|-------|
| wrong_answer | 3 |
| superset_answer | 1 |
| wrong_list | 1 |

## Error Category Classification

| Category | Count |
|----------|-------|
| formatting_error | 2 |
| wrong_aggregation | 1 |
| missing_tier_filter | 1 |
| wrong_filter | 1 |

## Per-Question Analysis

### Correct Answers

| QID | Difficulty | Answer | Latency |
|-----|-----------|--------|---------|
| 5 | easy | 'NL' | 22.7s |
| 70 | easy | 'Not Applicable' | 23.7s |
| 1273 | hard | '0.120132' | 89.0s |
| 1305 | hard | '0.123217' | 113.8s |
| 1464 | hard | '1, 2, 5, 6, 8, 9, 10, 12, 14, 15, 20, 2 | 85.0s |

### Failed Answers

#### Question 49 (easy)
- **Error type:** wrong_answer
- **Category:** wrong_aggregation
- **Expected:** `B. BE`
- **Got:** `A. NL`
- **Guidelines:** Answer must be in the form 'X. Y' where X is the option's letter chosen and Y is the option's country code. If a question does not have a relevant or applicable answer for the task, please respond wit
- **Has SQL:** False
- **SQL Error:** False
- **Response preview:** The top country by ip_country for fraud (by count of fraudulent transactions) is **NL** with 2,955 fraudulent transactions. Among the given options: A. NL, B. BE, C. ES, D. FR — NL has the highest count.  FINAL_ANSWER: A. NL

#### Question 1681 (hard)
- **Error type:** superset_answer
- **Category:** missing_tier_filter
- **Expected:** `741, 709, 454, 813, 381, 536, 473, 572, 477, 286`
- **Got:** `36, 51, 53, 64, 65, 80, 107, 123, 150, 163, 183, 231, 249, 276, 286, 304, 347, 381, 384, 394, 428, 454, 473, 477, 498, 536, 556, 572, 595, 608, 626, 631, 678, 680, 709, 725, 741, 813, 849, 861, 868, 871, 892, 924, 939, 942, 960`
- **Guidelines:** Answer must be a list of values in comma separated list, eg: A, B, C. If the answer is an empty list, reply with an empty string. If a question does not have a relevant or applicable answer for the ta
- **Has SQL:** False
- **SQL Error:** False
- **Response preview:** FINAL_ANSWER: 36, 51, 53, 64, 65, 80, 107, 123, 150, 163, 183, 231, 249, 276, 286, 304, 347, 381, 384, 394, 428, 454, 473, 477, 498, 536, 556, 572, 595, 608, 626, 631, 678, 680, 709, 725, 741, 813, 849, 861, 868, 871, 892, 924, 939, 942, 960

#### Question 1753 (hard)
- **Error type:** wrong_list
- **Category:** wrong_filter
- **Expected:** `384, 394, 276, 150, 536, 286, 163, 36, 680, 939, 428, 813, 556, 51, 53, 572, 960, 64, 709, 454, 595, 725, 473, 347, 477, 608, 868, 741, 231, 107, 626, 249, 123, 381`
- **Got:** `80, 231, 249, 276, 286, 347, 454, 556, 849, 868, 871, 939`
- **Guidelines:** Answer must be a list of values in comma separated list, eg: A, B, C. If the answer is an empty list, reply with an empty string. If a question does not have a relevant or applicable answer for the ta
- **Has SQL:** False
- **SQL Error:** False
- **Response preview:** I've verified all 12 fee IDs. Each one correctly: - Has account_type containing 'R' or is empty - Has merchant_category_code as empty `[]` (matches all) — none specifically list 5942 but none exclude it - Has capture_delay as NULL or '<3' - Has monthly_volume as NULL or '100k-1m' - Has monthly_fraud

#### Question 1871 (hard)
- **Error type:** wrong_answer
- **Category:** formatting_error
- **Expected:** `-0.94000000000005`
- **Got:** `-0.94810300000000`
- **Guidelines:** Answer must be just a number rounded to 14 decimals. If a question does not have a relevant or applicable answer for the task, please respond with 'Not Applicable'
- **Has SQL:** False
- **SQL Error:** False
- **Response preview:** FINAL_ANSWER: -0.94810300000000

#### Question 2697 (hard)
- **Error type:** wrong_answer
- **Category:** formatting_error
- **Expected:** `E:13.57`
- **Got:** `E:16.63`
- **Guidelines:** Answer must be just the selected ACI to incentive and the associated cost rounded to 2 decimals in this format: {card_scheme}:{fee}. If a question does not have a relevant or applicable answer for the
- **Has SQL:** False
- **SQL Error:** False
- **Response preview:** The question asks which ACI to incentivize users to move to (different from the current ACI G). The current fraudulent transactions are all ACI G with a total fee of 61.05.  Looking at the options that are **different** from G (since we're moving fraudulent transactions to a different ACI): - A: 89.

## Suggested Instruction Updates

1. **Monthly Tier Filter**: Strengthen the instruction about MANDATORY monthly tier lookups. For fee ID questions by date, ALWAYS join monthly_merchant_stats to get volume_tier and fraud_tier BEFORE filtering fees. day_of_year must be converted to month correctly.
2. **Aggregation**: Clarify aggregation instructions: 'total' = SUM, 'average' = AVG, 'count' = COUNT. Check whether to aggregate over all rows or distinct values.
3. **Filtering**: Add explicit day_of_year to month conversion: Jan=1-31, Feb=32-59, Mar=60-90, Apr=91-120. NULL in fees means 'matches all', not 'matches NULL'.
4. **Answer Formatting**: FINAL_ANSWER must exactly match the format in Guidelines. For multiple choice: answer with the EXACT letter+option from the choices. For decimals: match exact decimal places requested.
