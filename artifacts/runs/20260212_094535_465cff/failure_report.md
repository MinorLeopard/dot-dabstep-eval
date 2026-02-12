# Failure Analysis Report

- **Results file:** `artifacts\runs\20260212_094535_465cff\results.jsonl`
- **Total questions:** 10
- **Correct:** 5
- **Accuracy:** 50.0%

## Error Type Breakdown

| Error Type | Count |
|------------|-------|
| wrong_answer | 3 |
| wrong_list | 1 |
| superset_answer | 1 |

## Error Category Classification

| Category | Count |
|----------|-------|
| missing_tier_filter | 2 |
| formatting_error | 2 |
| wrong_aggregation | 1 |

## Per-Question Analysis

### Correct Answers

| QID | Difficulty | Answer | Latency |
|-----|-----------|--------|---------|
| 5 | easy | 'NL' | 20.9s |
| 70 | easy | 'Not Applicable' | 22.8s |
| 1273 | hard | '0.120132' | 68.3s |
| 1464 | hard | '1, 2, 5, 6, 8, 9, 10, 12, 14, 15, 20, 2 | 45.0s |
| 1305 | hard | '0.123217' | 215.2s |

### Failed Answers

#### Question 49 (easy)
- **Error type:** wrong_answer
- **Category:** wrong_aggregation
- **Expected:** `B. BE`
- **Got:** `A. NL`
- **Guidelines:** Answer must be in the form 'X. Y' where X is the option's letter chosen and Y is the option's country code. If a question does not have a relevant or applicable answer for the task, please respond wit
- **Has SQL:** False
- **SQL Error:** False
- **Response preview:** The top country by ip_country for fraud (by count of fraudulent transactions) is **NL** with 2,955 fraudulent transactions.  FINAL_ANSWER: A. NL

#### Question 1681 (hard)
- **Error type:** wrong_list
- **Category:** missing_tier_filter
- **Expected:** `741, 709, 454, 813, 381, 536, 473, 572, 477, 286`
- **Got:** `16, 27, 34, 39, 49, 62, 66, 72, 74, 80, 85, 102, 106, 126, 131, 141, 151, 153, 182, 194, 220, 231, 236, 237, 249, 252, 260, 265, 273, 276, 286, 291, 297, 298, 300, 326, 327, 331, 347, 352, 360, 368, 377, 396, 404, 408, 409, 414, 418, 420, 423, 424, 439, 452, 454, 455, 464, 489, 520, 522, 525, 540, 542, 543, 544, 556, 561, 564, 579, 580, 582, 587, 612, 616, 625, 628, 645, 649, 650, 653, 659, 661, 665, 673, 674, 690, 693, 701, 703, 706, 716, 728, 737, 742, 745, 757, 762, 779, 781, 784, 787, 811, 821, 822, 827, 841, 849, 851, 868, 871, 884, 888, 890, 894, 900, 902, 921, 922, 923, 925, 936, 938, 939, 964, 969, 971, 976, 985, 994, 999`
- **Guidelines:** Answer must be a list of values in comma separated list, eg: A, B, C. If the answer is an empty list, reply with an empty string. If a question does not have a relevant or applicable answer for the ta
- **Has SQL:** False
- **SQL Error:** False
- **Response preview:** FINAL_ANSWER: 16, 27, 34, 39, 49, 62, 66, 72, 74, 80, 85, 102, 106, 126, 131, 141, 151, 153, 182, 194, 220, 231, 236, 237, 249, 252, 260, 265, 273, 276, 286, 291, 297, 298, 300, 326, 327, 331, 347, 352, 360, 368, 377, 396, 404, 408, 409, 414, 418, 420, 423, 424, 439, 452, 454, 455, 464, 489, 520, 52

#### Question 2697 (hard)
- **Error type:** wrong_answer
- **Category:** formatting_error
- **Expected:** `E:13.57`
- **Got:** `C:88.26`
- **Guidelines:** Answer must be just the selected ACI to incentive and the associated cost rounded to 2 decimals in this format: {card_scheme}:{fee}. If a question does not have a relevant or applicable answer for the
- **Has SQL:** False
- **SQL Error:** False
- **Response preview:** The issue is clear - some card_scheme × ACI combinations don't have any matching fee rules, causing some transactions to be dropped (not matched). For ACIs A, B, C, all 94 transactions match. For D, E, F only 44 match. For G, only 30 match.  Since we need to move ALL fraudulent transactions to a sin

#### Question 1753 (hard)
- **Error type:** superset_answer
- **Category:** missing_tier_filter
- **Expected:** `384, 394, 276, 150, 536, 286, 163, 36, 680, 939, 428, 813, 556, 51, 53, 572, 960, 64, 709, 454, 595, 725, 473, 347, 477, 608, 868, 741, 231, 107, 626, 249, 123, 381`
- **Got:** `36, 51, 53, 64, 65, 80, 107, 123, 150, 163, 183, 231, 249, 276, 286, 304, 347, 381, 384, 394, 428, 454, 473, 477, 498, 536, 556, 572, 595, 608, 626, 631, 678, 680, 709, 725, 741, 813, 849, 861, 868, 871, 892, 924, 939, 942, 960`
- **Guidelines:** Answer must be a list of values in comma separated list, eg: A, B, C. If the answer is an empty list, reply with an empty string. If a question does not have a relevant or applicable answer for the ta
- **Has SQL:** False
- **SQL Error:** False
- **Response preview:** FINAL_ANSWER: 36, 51, 53, 64, 65, 80, 107, 123, 150, 163, 183, 231, 249, 276, 286, 304, 347, 381, 384, 394, 428, 454, 473, 477, 498, 536, 556, 572, 595, 608, 626, 631, 678, 680, 709, 725, 741, 813, 849, 861, 868, 871, 892, 924, 939, 942, 960

#### Question 1871 (hard)
- **Error type:** wrong_answer
- **Category:** formatting_error
- **Expected:** `-0.94000000000005`
- **Got:** `-0.94810300000000`
- **Guidelines:** Answer must be just a number rounded to 14 decimals. If a question does not have a relevant or applicable answer for the task, please respond with 'Not Applicable'
- **Has SQL:** False
- **SQL Error:** False
- **Response preview:** The delta is -0.94810300000000.  FINAL_ANSWER: -0.94810300000000

## Suggested Instruction Updates

1. **Monthly Tier Filter**: Strengthen the instruction about MANDATORY monthly tier lookups. For fee ID questions by date, ALWAYS join monthly_merchant_stats to get volume_tier and fraud_tier BEFORE filtering fees. day_of_year must be converted to month correctly.
2. **Aggregation**: Clarify aggregation instructions: 'total' = SUM, 'average' = AVG, 'count' = COUNT. Check whether to aggregate over all rows or distinct values.
3. **Answer Formatting**: FINAL_ANSWER must exactly match the format in Guidelines. For multiple choice: answer with the EXACT letter+option from the choices. For decimals: match exact decimal places requested.
