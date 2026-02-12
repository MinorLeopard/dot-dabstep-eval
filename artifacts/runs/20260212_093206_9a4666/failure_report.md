# Failure Analysis Report

- **Results file:** `artifacts\runs\20260212_093206_9a4666\results.jsonl`
- **Total questions:** 5
- **Correct:** 0
- **Accuracy:** 0.0%

## Error Type Breakdown

| Error Type | Count |
|------------|-------|
| wrong_answer | 5 |

## Error Category Classification

| Category | Count |
|----------|-------|
| missing_tier_filter | 5 |

## Per-Question Analysis

### Failed Answers

#### Question 5 (easy)
- **Error type:** wrong_answer
- **Category:** missing_tier_filter
- **Expected:** `NL`
- **Got:** `fake_d70e456a`
- **Guidelines:** Answer must be just the country code. If a question does not have a relevant or applicable answer for the task, please respond with 'Not Applicable'
- **Has SQL:** False
- **SQL Error:** False
- **Response preview:** Let me analyze this step by step. After careful consideration... FINAL_ANSWER: fake_d70e456a

#### Question 49 (easy)
- **Error type:** wrong_answer
- **Category:** missing_tier_filter
- **Expected:** `B. BE`
- **Got:** `fake_4d91f204`
- **Guidelines:** Answer must be in the form 'X. Y' where X is the option's letter chosen and Y is the option's country code. If a question does not have a relevant or applicable answer for the task, please respond wit
- **Has SQL:** False
- **SQL Error:** False
- **Response preview:** Let me analyze this step by step. After careful consideration... FINAL_ANSWER: fake_4d91f204

#### Question 70 (easy)
- **Error type:** wrong_answer
- **Category:** missing_tier_filter
- **Expected:** `Not Applicable`
- **Got:** `fake_38ed8610`
- **Guidelines:** Answer must be just either yes or no. If a question does not have a relevant or applicable answer for the task, please respond with 'Not Applicable'
- **Has SQL:** False
- **SQL Error:** False
- **Response preview:** Let me analyze this step by step. After careful consideration... FINAL_ANSWER: fake_38ed8610

#### Question 1273 (hard)
- **Error type:** wrong_answer
- **Category:** missing_tier_filter
- **Expected:** `0.120132`
- **Got:** `fake_35f8806c`
- **Guidelines:** Answer must be just a number expressed in EUR rounded to 6 decimals. If a question does not have a relevant or applicable answer for the task, please respond with 'Not Applicable'
- **Has SQL:** False
- **SQL Error:** False
- **Response preview:** Let me analyze this step by step. After careful consideration... FINAL_ANSWER: fake_35f8806c

#### Question 1305 (hard)
- **Error type:** wrong_answer
- **Category:** missing_tier_filter
- **Expected:** `0.123217`
- **Got:** `fake_5f159fd3`
- **Guidelines:** Answer must be just a number expressed in EUR rounded to 6 decimals. If a question does not have a relevant or applicable answer for the task, please respond with 'Not Applicable'
- **Has SQL:** False
- **SQL Error:** False
- **Response preview:** Let me analyze this step by step. After careful consideration... FINAL_ANSWER: fake_5f159fd3

## Suggested Instruction Updates

1. **Monthly Tier Filter**: Strengthen the instruction about MANDATORY monthly tier lookups. Add explicit SQL template: 'For ANY fee question involving a merchant and time period, FIRST run: SELECT volume_tier, fraud_tier FROM monthly_merchant_stats WHERE merchant=... AND year=... AND month=...'
