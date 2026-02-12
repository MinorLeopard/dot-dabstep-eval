# Failure Analysis Report

- **Results file:** `artifacts\runs\20260212_101812_f7aa56\results.jsonl`
- **Total questions:** 10
- **Correct:** 4
- **Accuracy:** 40.0%

## Error Type Breakdown

| Error Type | Count |
|------------|-------|
| wrong_answer | 4 |
| wrong_list | 1 |
| superset_answer | 1 |

## Error Category Classification

| Category | Count |
|----------|-------|
| formatting_error | 2 |
| wrong_aggregation | 1 |
| precision_error | 1 |
| wrong_fee_match | 1 |
| missing_tier_filter | 1 |

## Per-Question Analysis

### Correct Answers

| QID | Difficulty | Answer | Latency |
|-----|-----------|--------|---------|
| 70 | easy | 'Not Applicable' | 22.8s |
| 5 | easy | 'NL' | 38.2s |
| 1273 | hard | '0.120132' | 103.3s |
| 1464 | hard | '1, 2, 5, 6, 8, 9, 10, 12, 14, 15, 20, 2 | 90.4s |

### Failed Answers

#### Question 49 (easy)
- **Error type:** wrong_answer
- **Category:** wrong_aggregation
- **Expected:** `B. BE`
- **Got:** `A. NL`
- **Guidelines:** Answer must be in the form 'X. Y' where X is the option's letter chosen and Y is the option's country code. If a question does not have a relevant or applicable answer for the task, please respond wit
- **Has SQL:** False
- **SQL Error:** False
- **Response preview:** The top country by ip_country for fraud (by count of fraudulent transactions) is **NL** with 2,955 fraudulent transactions. Among the given options, NL corresponds to option A.  FINAL_ANSWER: A. NL

#### Question 1305 (hard)
- **Error type:** wrong_answer
- **Category:** precision_error
- **Expected:** `0.123217`
- **Got:** `0.127795`
- **Guidelines:** Answer must be just a number expressed in EUR rounded to 6 decimals. If a question does not have a relevant or applicable answer for the task, please respond with 'Not Applicable'
- **Has SQL:** False
- **SQL Error:** False
- **Response preview:** The average fee is 0.12779487179487178. Rounded to 6 decimals: 0.127795.  FINAL_ANSWER: 0.127795

#### Question 1871 (hard)
- **Error type:** wrong_answer
- **Category:** formatting_error
- **Expected:** `-0.94000000000005`
- **Got:** `-0.94810300000000`
- **Guidelines:** Answer must be just a number rounded to 14 decimals. If a question does not have a relevant or applicable answer for the task, please respond with 'Not Applicable'
- **Has SQL:** False
- **SQL Error:** False
- **Response preview:** FINAL_ANSWER: -0.94810300000000

#### Question 1753 (hard)
- **Error type:** wrong_list
- **Category:** wrong_fee_match
- **Expected:** `384, 394, 276, 150, 536, 286, 163, 36, 680, 939, 428, 813, 556, 51, 53, 572, 960, 64, 709, 454, 595, 725, 473, 347, 477, 608, 868, 741, 231, 107, 626, 249, 123, 381`
- **Got:** `36, 51, 53, 64, 65, 107, 123, 150, 163, 183, 304, 381, 384, 394, 428, 473, 477, 498, 536, 572, 595, 608, 626, 631, 678, 680, 709, 725, 741, 813, 861, 892, 924, 942, 960`
- **Guidelines:** Answer must be a list of values in comma separated list, eg: A, B, C. If the answer is an empty list, reply with an empty string. If a question does not have a relevant or applicable answer for the ta
- **Has SQL:** False
- **SQL Error:** False
- **Response preview:** FINAL_ANSWER: 36, 51, 53, 64, 65, 107, 123, 150, 163, 183, 304, 381, 384, 394, 428, 473, 477, 498, 536, 572, 595, 608, 626, 631, 678, 680, 709, 725, 741, 813, 861, 892, 924, 942, 960

#### Question 2697 (hard)
- **Error type:** wrong_answer
- **Category:** formatting_error
- **Expected:** `E:13.57`
- **Got:** `C:88.26`
- **Guidelines:** Answer must be just the selected ACI to incentive and the associated cost rounded to 2 decimals in this format: {card_scheme}:{fee}. If a question does not have a relevant or applicable answer for the
- **Has SQL:** False
- **SQL Error:** False
- **Response preview:** I notice that ACIs D, E, F, and G only matched a subset of the 94 transactions. This means not all card schemes have fee rules for those ACIs. I need to ensure I'm comparing fairly - all 94 transactions need to be matched. Let me look at which ACIs have 100% match rate: A (100%), B (100%), C (100%).

#### Question 1681 (hard)
- **Error type:** superset_answer
- **Category:** missing_tier_filter
- **Expected:** `741, 709, 454, 813, 381, 536, 473, 572, 477, 286`
- **Got:** `1, 2, 4, 8, 11, 12, 16, 18, 20, 21, 22, 25, 27, 32, 33, 34, 36, 39, 40, 41, 45, 49, 51, 53, 54, 57, 58, 59, 61, 62, 64, 65, 66, 70, 71, 72, 74, 76, 80, 83, 84, 85, 91, 93, 96, 98, 99, 100, 101, 102, 103, 104, 106, 107, 108, 111, 115, 117, 118, 122, 123, 126, 127, 128, 129, 130, 131, 132, 133, 135, 141, 143, 144, 146, 150, 151, 152, 153, 157, 158, 160, 161, 162, 163, 164, 165, 166, 171, 173, 174, 179, 180, 182, 183, 184, 190, 191, 194, 197, 199, 202, 205, 214, 217, 220, 231, 233, 234, 235, 236, 237, 240, 244, 246, 249, 251, 252, 255, 259, 260, 263, 264, 265, 267, 269, 272, 273, 276, 281, 285, 286, 288, 291, 293, 297, 298, 300, 301, 302, 303, 304, 308, 310, 315, 318, 320, 326, 327, 328, 330, 331, 332, 334, 335, 337, 338, 339, 340, 347, 348, 349, 352, 353, 358, 360, 361, 362, 367, 368, 371, 372, 373, 375, 377, 380, 381, 382, 383, 384, 385, 387, 391, 392, 394, 396, 400, 404, 407, 408, 409, 410, 414, 416, 417, 418, 420, 421, 423, 424, 428, 429, 430, 431, 432, 433, 434, 435, 439, 440, 441, 445, 447, 448, 451, 452, 454, 455, 460, 461, 464, 468, 473, 474, 475, 477, 480, 482, 486, 488, 489, 490, 491, 492, 496, 498, 503, 505, 507, 509, 510, 511, 513, 514, 520, 521, 522, 525, 533, 535, 536, 540, 541, 542, 543, 544, 547, 548, 553, 555, 556, 557, 559, 561, 564, 565, 572, 573, 576, 579, 580, 582, 587, 589, 594, 595, 600, 608, 609, 612, 613, 614, 615, 616, 619, 621, 622, 624, 625, 626, 628, 630, 631, 633, 635, 637, 640, 641, 644, 645, 647, 648, 649, 650, 653, 654, 658, 659, 660, 661, 662, 665, 667, 673, 674, 675, 676, 677, 678, 680, 682, 685, 689, 690, 692, 693, 694, 698, 701, 703, 706, 708, 709, 710, 712, 716, 720, 721, 725, 726, 728, 729, 730, 733, 734, 735, 737, 738, 741, 742, 745, 749, 752, 753, 757, 759, 762, 764, 766, 769, 773, 774, 775, 777, 778, 779, 781, 782, 784, 785, 786, 787, 788, 789, 790, 794, 795, 797, 803, 806, 811, 813, 815, 817, 821, 822, 827, 834, 836, 838, 840, 841, 842, 844, 848, 849, 850, 851, 858, 861, 863, 865, 866, 868, 871, 874, 876, 878, 880, 882, 884, 886, 888, 890, 891, 892, 893, 894, 896, 898, 900, 902, 907, 912, 913, 916, 918, 920, 921, 922, 923, 924, 925, 927, 928, 929, 931, 936, 937, 938, 939, 942, 945, 947, 950, 953, 958, 960, 961, 964, 967, 969, 971, 976, 980, 981, 985, 988, 989, 994, 995, 999, 1000`
- **Guidelines:** Answer must be a list of values in comma separated list, eg: A, B, C. If the answer is an empty list, reply with an empty string. If a question does not have a relevant or applicable answer for the ta
- **Has SQL:** False
- **SQL Error:** False
- **Response preview:** FINAL_ANSWER: 1, 2, 4, 8, 11, 12, 16, 18, 20, 21, 22, 25, 27, 32, 33, 34, 36, 39, 40, 41, 45, 49, 51, 53, 54, 57, 58, 59, 61, 62, 64, 65, 66, 70, 71, 72, 74, 76, 80, 83, 84, 85, 91, 93, 96, 98, 99, 100, 101, 102, 103, 104, 106, 107, 108, 111, 115, 117, 118, 122, 123, 126, 127, 128, 129, 130, 131, 13

## Suggested Instruction Updates

1. **Monthly Tier Filter**: Strengthen the instruction about MANDATORY monthly tier lookups. For fee ID questions by date, ALWAYS join monthly_merchant_stats to get volume_tier and fraud_tier BEFORE filtering fees. day_of_year must be converted to month correctly.
2. **Fee ID Matching**: Fee matching requires checking ALL criteria simultaneously. Each fee field that is non-null must match the transaction. intracountry is computed per-transaction, not per-merchant.
3. **Numeric Precision**: Fee calculations must use precise arithmetic. fee = fixed_amount + (rate * eur_amount / 10000.0). Ensure all intermediate values preserve full precision. Use the exact fee rate from the matching rule.
4. **Aggregation**: Clarify aggregation instructions: 'total' = SUM, 'average' = AVG, 'count' = COUNT. Check whether to aggregate over all rows or distinct values.
5. **Answer Formatting**: FINAL_ANSWER must exactly match the format in Guidelines. For multiple choice: answer with the EXACT letter+option from the choices. For decimals: match exact decimal places requested.
