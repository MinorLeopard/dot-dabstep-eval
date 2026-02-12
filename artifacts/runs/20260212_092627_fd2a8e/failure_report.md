# Failure Analysis Report

- **Results file:** `artifacts\runs\20260212_092627_fd2a8e\results.jsonl`
- **Total questions:** 10
- **Correct:** 0
- **Accuracy:** 0.0%

## Error Type Breakdown

| Error Type | Count |
|------------|-------|
| wrong_answer | 10 |

## Error Category Classification

| Category | Count |
|----------|-------|
| missing_tier_filter | 10 |

## Per-Question Analysis

### Failed Answers

#### Question 1712 (hard)
- **Error type:** wrong_answer
- **Category:** missing_tier_filter
- **Expected:** ``
- **Got:** `fake_3878d9e7`
- **Guidelines:** Answer must be just a number rounded to 2 decimals. If a question does not have a relevant or applicable answer for the task, please respond with 'Not Applicable'
- **Has SQL:** False
- **SQL Error:** False
- **Response preview:** Let me analyze this step by step. After careful consideration... FINAL_ANSWER: fake_3878d9e7

#### Question 1810 (hard)
- **Error type:** wrong_answer
- **Category:** missing_tier_filter
- **Expected:** ``
- **Got:** `fake_6120e99f`
- **Guidelines:** Answer must be a list of values in comma separated list, eg: A, B, C. If the answer is an empty list, reply with an empty string. If a question does not have a relevant or applicable answer for the ta
- **Has SQL:** False
- **SQL Error:** False
- **Response preview:** Let me analyze this step by step. After careful consideration... FINAL_ANSWER: fake_6120e99f

#### Question 1741 (hard)
- **Error type:** wrong_answer
- **Category:** missing_tier_filter
- **Expected:** ``
- **Got:** `fake_912791f2`
- **Guidelines:** Answer must be a list of values in comma separated list, eg: A, B, C. If the answer is an empty list, reply with an empty string. If a question does not have a relevant or applicable answer for the ta
- **Has SQL:** False
- **SQL Error:** False
- **Response preview:** Let me analyze this step by step. After careful consideration... FINAL_ANSWER: fake_912791f2

#### Question 1480 (hard)
- **Error type:** wrong_answer
- **Category:** missing_tier_filter
- **Expected:** ``
- **Got:** `fake_73a79151`
- **Guidelines:** Answer must be a list of values in comma separated list, eg: A, B, C. If the answer is an empty list, reply with an empty string. If a question does not have a relevant or applicable answer for the ta
- **Has SQL:** False
- **SQL Error:** False
- **Response preview:** Let me analyze this step by step. After careful consideration... FINAL_ANSWER: fake_73a79151

#### Question 1234 (hard)
- **Error type:** wrong_answer
- **Category:** missing_tier_filter
- **Expected:** ``
- **Got:** `fake_9c735666`
- **Guidelines:** Present your results broken down by grouping and sorted in ascending order. The final answer should be a list of this format: [grouping_i: amount_i, ]. When grouping by country use the country_code. T
- **Has SQL:** False
- **SQL Error:** False
- **Response preview:** Let me analyze this step by step. After careful consideration... FINAL_ANSWER: fake_9c735666

#### Question 2761 (hard)
- **Error type:** wrong_answer
- **Category:** missing_tier_filter
- **Expected:** ``
- **Got:** `fake_b1de156c`
- **Guidelines:** Answer must be just the selected card scheme and the associated cost rounded to 2 decimals in this format: {card_scheme}:{fee}. If a question does not have a relevant or applicable answer for the task
- **Has SQL:** False
- **SQL Error:** False
- **Response preview:** Let me analyze this step by step. After careful consideration... FINAL_ANSWER: fake_b1de156c

#### Question 1738 (hard)
- **Error type:** wrong_answer
- **Category:** missing_tier_filter
- **Expected:** ``
- **Got:** `fake_61c019a2`
- **Guidelines:** Answer must be just a number rounded to 2 decimals. If a question does not have a relevant or applicable answer for the task, please respond with 'Not Applicable'
- **Has SQL:** False
- **SQL Error:** False
- **Response preview:** Let me analyze this step by step. After careful consideration... FINAL_ANSWER: fake_61c019a2

#### Question 2564 (hard)
- **Error type:** wrong_answer
- **Category:** missing_tier_filter
- **Expected:** ``
- **Got:** `fake_2395d632`
- **Guidelines:** Answer must be a list of values in comma separated list, eg: A, B, C. If the answer is an empty list, reply with an empty string. If a question does not have a relevant or applicable answer for the ta
- **Has SQL:** False
- **SQL Error:** False
- **Response preview:** Let me analyze this step by step. After careful consideration... FINAL_ANSWER: fake_2395d632

#### Question 2644 (hard)
- **Error type:** wrong_answer
- **Category:** missing_tier_filter
- **Expected:** ``
- **Got:** `fake_d37c9a46`
- **Guidelines:** Answer must be just the selected card scheme and the associated cost rounded to 2 decimals in this format: {card_scheme}:{fee}. If a question does not have a relevant or applicable answer for the task
- **Has SQL:** False
- **SQL Error:** False
- **Response preview:** Let me analyze this step by step. After careful consideration... FINAL_ANSWER: fake_d37c9a46

#### Question 2536 (hard)
- **Error type:** wrong_answer
- **Category:** missing_tier_filter
- **Expected:** ``
- **Got:** `fake_de0dfbff`
- **Guidelines:** Answer must be just a number rounded to 6 decimals. If a question does not have a relevant or applicable answer for the task, please respond with 'Not Applicable'
- **Has SQL:** False
- **SQL Error:** False
- **Response preview:** Let me analyze this step by step. After careful consideration... FINAL_ANSWER: fake_de0dfbff

## Suggested Instruction Updates

1. **Monthly Tier Filter**: Strengthen the instruction about MANDATORY monthly tier lookups. Add explicit SQL template: 'For ANY fee question involving a merchant and time period, FIRST run: SELECT volume_tier, fraud_tier FROM monthly_merchant_stats WHERE merchant=... AND year=... AND month=...'
