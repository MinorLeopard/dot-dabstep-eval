# Failure Analysis Report

- **Results file:** `artifacts\runs\20260212_103707_e8baeb\results.jsonl`
- **Total questions:** 10
- **Correct:** 5
- **Accuracy:** 50.0%

## Error Type Breakdown

| Error Type | Count |
|------------|-------|
| wrong_answer | 2 |
| superset_answer | 2 |
| client_error | 1 |

## Error Category Classification

| Category | Count |
|----------|-------|
| missing_tier_filter | 2 |
| wrong_aggregation | 1 |
| formatting_error | 1 |
| format_missing | 1 |

## Per-Question Analysis

### Correct Answers

| QID | Difficulty | Answer | Latency |
|-----|-----------|--------|---------|
| 70 | easy | 'Not Applicable' | 13.2s |
| 5 | easy | 'NL' | 33.0s |
| 1464 | hard | '1, 2, 5, 6, 8, 9, 10, 12, 14, 15, 20, 2 | 51.2s |
| 1273 | hard | '0.120132' | 104.8s |
| 1305 | hard | '0.123217' | 217.8s |

### Failed Answers

#### Question 49 (easy)
- **Error type:** wrong_answer
- **Category:** wrong_aggregation
- **Expected:** `B. BE`
- **Got:** `A. NL`
- **Guidelines:** Answer must be in the form 'X. Y' where X is the option's letter chosen and Y is the option's country code. If a question does not have a relevant or applicable answer for the task, please respond wit
- **Has SQL:** False
- **SQL Error:** False
- **Response preview:** The top country by ip_country for fraud (by count of fraudulent transactions) is **NL** with 2,955 fraudulent transactions. Among the options provided, NL corresponds to option A.  FINAL_ANSWER: A. NL

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
- **Error type:** superset_answer
- **Category:** missing_tier_filter
- **Expected:** `384, 394, 276, 150, 536, 286, 163, 36, 680, 939, 428, 813, 556, 51, 53, 572, 960, 64, 709, 454, 595, 725, 473, 347, 477, 608, 868, 741, 231, 107, 626, 249, 123, 381`
- **Got:** `36, 51, 53, 64, 65, 80, 107, 123, 150, 163, 183, 231, 249, 276, 286, 304, 347, 381, 384, 394, 428, 454, 473, 477, 498, 536, 556, 572, 595, 608, 626, 631, 678, 680, 709, 725, 741, 813, 849, 861, 868, 871, 892, 924, 939, 942, 960`
- **Guidelines:** Answer must be a list of values in comma separated list, eg: A, B, C. If the answer is an empty list, reply with an empty string. If a question does not have a relevant or applicable answer for the ta
- **Has SQL:** False
- **SQL Error:** False
- **Response preview:** All account_type values are either NULL (wildcard, matches all) or contain 'R'. This looks correct. The 47 fee IDs match on all criteria: - merchant_category_code = '[]' (wildcard matches MCC 5942) - account_type is NULL or contains 'R'  - capture_delay is NULL or '<3' - monthly_volume is NULL or '1

#### Question 1871 (hard)
- **Error type:** wrong_answer
- **Category:** formatting_error
- **Expected:** `-0.94000000000005`
- **Got:** `-0.80054000000000`
- **Guidelines:** Answer must be just a number rounded to 14 decimals. If a question does not have a relevant or applicable answer for the task, please respond with 'Not Applicable'
- **Has SQL:** False
- **SQL Error:** False
- **Response preview:** The exact delta is -0.80054. The SQL returned -0.801 due to floating point, but the precise calculation with the actual transaction amounts gives -0.80054.  FINAL_ANSWER: -0.80054000000000

#### Question 2697 (hard)
- **Error type:** client_error
- **Category:** format_missing
- **Expected:** `E:13.57`
- **Got:** `None`
- **Guidelines:** Answer must be just the selected ACI to incentive and the associated cost rounded to 2 decimals in this format: {card_scheme}:{fee}. If a question does not have a relevant or applicable answer for the
- **Has SQL:** False
- **SQL Error:** False

## Suggested Instruction Updates

1. **Monthly Tier Filter**: Strengthen the instruction about MANDATORY monthly tier lookups. For fee ID questions by date, ALWAYS join monthly_merchant_stats to get volume_tier and fraud_tier BEFORE filtering fees. day_of_year must be converted to month correctly.
2. **Aggregation**: Clarify aggregation instructions: 'total' = SUM, 'average' = AVG, 'count' = COUNT. Check whether to aggregate over all rows or distinct values.
3. **Answer Formatting**: FINAL_ANSWER must exactly match the format in Guidelines. For multiple choice: answer with the EXACT letter+option from the choices. For decimals: match exact decimal places requested.
