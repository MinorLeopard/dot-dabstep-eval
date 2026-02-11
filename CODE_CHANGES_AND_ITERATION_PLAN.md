# Code Changes & Iteration Plan for DABStep Score Improvement

> Baseline: `dot_dev10_agentic_v1.jsonl` — 3/10 (30%)
> Generated: 2026-02-12

---

## A. Repo Structure Summary

```
src/
  runner.py         — Main eval loop: load tasks → prompt → call Dot → parse → score → write JSONL
  prompting.py      — SYSTEM_INSTRUCTION constant + build_prompt() + parse_final_answer()
  scoring.py        — normalize_answer() + score_answer() (exact match with numeric tolerance)
  dot_client.py     — LiveDotClient (HTTP to Dot /api/agentic) + FakeDotClient
  dabstep_loader.py — Load tasks from HF or JSONL; filter target30
  analyze_failures.py — Summary stats + failure samples
data/
  context/          — Original data: fees.json, merchant_data.json, payments.csv, manual.md, etc.
  derived/          — fees.csv, merchant_data.csv (uploaded to Dot as data sources)
  dot_fee_instructions.md — Current org-level instructions injected into Dot
  relationships.yaml      — Table relationships configured in Dot
```

## B. Failure Classification (dot_dev10_agentic_v1)

| Q_ID | Difficulty | Failure Mode | Root Cause |
|------|-----------|-------------|------------|
| 70   | easy | Wrong answer ("yes" vs "Not Applicable") | **Concept confusion**: question asks about "fine" which doesn't exist in data model |
| 1273 | hard | Wrong numeric (0.117667 vs 0.120132) | **Wrong fee filter**: average fee across GlobalCard credit rules miscounted |
| 1305 | hard | Wrong numeric (0.135818 vs 0.123217) | **Wrong fee filter**: account_type + MCC filter not applied correctly |
| 1681 | hard | Superset (36 IDs vs 10) | **Missing monthly filters**: monthly_volume and monthly_fraud_level not computed |
| 1753 | hard | Superset (47 IDs vs 34) | **Missing monthly filters**: same as Q1681 |
| 1871 | hard | Wrong numeric (-0.9481 vs -0.9400) | **Cascading from wrong fee match**: wrong rule applied → wrong delta |
| 2697 | hard | Wrong ACI (B:71.58 vs E:13.57) | **Wrong optimization logic**: didn't find lowest-fee ACI correctly |

### Failure Mode Distribution

| Mode | Count | % of Failures |
|------|-------|---------------|
| Missing monthly_volume/fraud filter | 2 | 29% |
| Wrong fee rule filtering (null/empty semantics) | 2 | 29% |
| Concept doesn't exist → should be "Not Applicable" | 1 | 14% |
| Wrong optimization/delta computation (cascaded) | 2 | 29% |

---

## C. Code Changes

### C1. Prompt Changes (`src/prompting.py`)

#### Current SYSTEM_INSTRUCTION (line 12-26):
Generic "data analysis and business metrics" instruction with no schema or fee-matching guidance.

#### Proposed New SYSTEM_INSTRUCTION:

```python
SYSTEM_INSTRUCTION = (
    "You are answering questions about payment transaction data, merchant fees, and business metrics.\n\n"
    "AVAILABLE TABLES:\n"
    "- payments: psp_reference, merchant, card_scheme, year, day_of_year, is_credit, eur_amount, "
    "issuing_country, acquirer_country, aci, has_fraudulent_dispute, ip_country, device_type, shopper_interaction\n"
    "- merchant_data: merchant, account_type (R/D/H/F/S/O), merchant_category_code (int), "
    "capture_delay (string), acquirer (list)\n"
    "- fees: ID, card_scheme, account_type (list or empty=all), capture_delay (null=all, '<3'/'3-5'/'>5'/'immediate'/'manual'), "
    "monthly_fraud_level (null=all), monthly_volume (null=all), merchant_category_code (list or empty=all), "
    "is_credit (null=all), aci (list or empty=all), fixed_amount, rate, intracountry (null=all, 0 or 1)\n"
    "- acquirer_countries: acquirer, country_code\n"
    "- merchant_category_codes: mcc, description\n\n"
    "FEE FORMULA: fee = fixed_amount + (rate * eur_amount / 10000.0)\n\n"
    "FEE MATCHING: A fee rule matches when ALL its non-null/non-empty criteria match. "
    "Null or empty list means 'applies to all'.\n\n"
    "CAPTURE_DELAY MAPPING: merchant delay '1' or '2' → fee bucket '<3'; '3','4','5' → '3-5'; "
    "'7'+ → '>5'; 'immediate' → 'immediate'; 'manual' → 'manual'.\n\n"
    "MONTHLY AGGREGATION: When a question references a date/month, compute the merchant's "
    "monthly volume (SUM eur_amount) and fraud rate (SUM fraud_volume / SUM total_volume) for the "
    "FULL calendar month, then filter fee rules by monthly_volume and monthly_fraud_level tiers.\n\n"
    "INTRACOUNTRY: 1 if payments.issuing_country = payments.acquirer_country, else 0.\n\n"
    "DATE HANDLING: day_of_year is 1-indexed. Jan=1-31, Feb=32-59, Mar=60-90, Apr=91-120, "
    "May=121-151, Jun=152-181, Jul=182-212, Aug=213-243, Sep=244-273, Oct=274-304, "
    "Nov=305-334, Dec=335-365.\n\n"
    "'NOT APPLICABLE' RULE: Only answer about concepts in the data model. There are NO fines, "
    "penalties, or surcharges — only fee rules. If a question asks about something not in the data "
    "(e.g., 'fraud fine'), answer 'Not Applicable'.\n\n"
    "Reply with ONLY your final answer in EXACTLY this format:\n\n"
    "FINAL_ANSWER: <your answer>\n\n"
    "IMPORTANT RULES:\n"
    "- Your FINAL_ANSWER must contain ONLY the answer value — no explanations, no units unless asked.\n"
    "- Follow the Guidelines section EXACTLY for formatting.\n"
    "- If the Guidelines say 'respond with Not Applicable', use exactly: FINAL_ANSWER: Not Applicable\n"
    "- If you cannot compute the answer, respond: FINAL_ANSWER: Not Applicable\n"
    "- You MUST always end your response with the FINAL_ANSWER line."
)
```

**Key additions:**
1. Schema summary inline (saves Dot from having to discover it)
2. Fee formula and matching semantics
3. Capture delay mapping table
4. Monthly aggregation requirement
5. "Not Applicable" guidance for non-existent concepts
6. Date handling reference

#### New `build_prompt()` (line 31-38):

```python
def build_prompt(task: Task) -> str:
    """Build the full prompt for a DABStep task."""
    guidelines = task.metadata.get("guidelines", "")
    parts = [SYSTEM_INSTRUCTION]
    if guidelines:
        parts.append(f"Guidelines:\n{guidelines}")
    parts.append(f"Question: {task.question}")
    # Add a reminder at the end
    parts.append(
        "REMINDER: Use SQL to compute the answer. Apply ALL fee matching criteria "
        "including monthly_volume and monthly_fraud_level (compute from payments first). "
        "End with FINAL_ANSWER: <answer>"
    )
    return "\n\n".join(parts)
```

### C2. Answer Parsing Improvements (`src/prompting.py`)

#### Current `parse_final_answer` (line 57-70):
Uses `FINAL_ANSWER:\s*(.+?)(?:\n|$)` regex — reasonable but could be more robust.

#### Proposed additions:

```python
FINAL_ANSWER_PATTERN = re.compile(
    r"FINAL_ANSWER:\s*(.+?)(?:\n|$)", re.IGNORECASE
)

# Additional fallback patterns for when Dot uses slightly different formats
FALLBACK_PATTERNS = [
    re.compile(r"Final Answer:\s*(.+?)(?:\n|$)", re.IGNORECASE),
    re.compile(r"The answer is:\s*(.+?)(?:\n|$)", re.IGNORECASE),
    re.compile(r"Answer:\s*(.+?)(?:\n|$)", re.IGNORECASE),
]


def _clean_answer(raw: str) -> str:
    """Apply safe normalization to a parsed answer string."""
    answer = raw.strip()
    # Remove surrounding backticks
    if answer.startswith("```") and answer.endswith("```"):
        answer = answer[3:-3].strip()
    if answer.startswith("`") and answer.endswith("`"):
        answer = answer[1:-1].strip()
    # Remove surrounding quotes
    if len(answer) >= 2 and answer[0] == answer[-1] and answer[0] in ('"', "'"):
        answer = answer[1:-1].strip()
    # Remove trailing period (but not from decimal numbers)
    if answer.endswith(".") and not re.match(r"^-?\d+\.\d*\.$", answer):
        answer = answer[:-1].strip()
    # Remove "EUR " prefix if present (some answers include it)
    if answer.upper().startswith("EUR "):
        answer = answer[4:].strip()
    # Remove leading $ sign
    if answer.startswith("$"):
        answer = answer[1:].strip()
    # Collapse multiple spaces
    answer = re.sub(r"[ \t]+", " ", answer)
    return answer


def parse_final_answer(response_text: str) -> str | None:
    """Extract the FINAL_ANSWER from Dot's response.

    Uses the LAST match from primary pattern, with fallbacks.
    """
    matches = list(FINAL_ANSWER_PATTERN.finditer(response_text))
    if matches:
        answer = matches[-1].group(1).strip()
        return _clean_answer(answer)

    # Try fallback patterns
    for pat in FALLBACK_PATTERNS:
        matches = list(pat.finditer(response_text))
        if matches:
            answer = matches[-1].group(1).strip()
            return _clean_answer(answer)

    logger.warning("No FINAL_ANSWER found in response")
    return None
```

### C3. Scoring Improvements (`src/scoring.py`)

#### Current scoring (line 42-68):
Basic exact match with numeric tolerance. No list comparison.

#### Proposed: Add set-based comparison for comma-separated lists:

```python
def _try_parse_list(s: str) -> list[str] | None:
    """Try to parse a comma-separated list answer."""
    if "," not in s:
        return None
    items = [item.strip() for item in s.split(",") if item.strip()]
    if len(items) < 2:
        return None
    return items


def score_answer(parsed_answer: str | None, ground_truth: str) -> tuple[int, str | None]:
    if parsed_answer is None:
        return 0, "format_missing"

    norm_parsed = normalize_answer(parsed_answer)
    norm_truth = normalize_answer(ground_truth)

    # Try numeric comparison first
    parsed_num = _try_parse_float(norm_parsed)
    truth_num = _try_parse_float(norm_truth)

    if parsed_num is not None and truth_num is not None:
        if math.isclose(parsed_num, truth_num, rel_tol=1e-4, abs_tol=NUMERIC_TOLERANCE):
            return 1, None
        return 0, "wrong_answer"

    # Try list comparison (order-independent for comma-separated lists)
    parsed_list = _try_parse_list(norm_parsed)
    truth_list = _try_parse_list(norm_truth)
    if parsed_list is not None and truth_list is not None:
        if set(parsed_list) == set(truth_list):
            return 1, None
        # Check if it's a subset/superset for better error tagging
        parsed_set = set(parsed_list)
        truth_set = set(truth_list)
        if parsed_set > truth_set:
            return 0, "superset_answer"
        if parsed_set < truth_set:
            return 0, "subset_answer"
        return 0, "wrong_list"

    # String exact match
    if norm_parsed == norm_truth:
        return 1, None

    return 0, "wrong_answer"
```

**Note:** Check whether the DABStep official scorer does set-based or order-sensitive comparison. If order-sensitive, remove the set comparison. If set-based, this helps catch partial-credit and classify errors better.

### C4. Retry Logic for SQL Errors (`src/dot_client.py`)

#### Current: Only retries on HTTP 502 (line 306-315).

#### Proposed: Add application-level retry when response contains SQL error:

```python
def query(self, prompt: str, chat_id: str | None = None) -> DotResponse:
    """Send a prompt to Dot and return the response.

    If the response indicates a SQL error, sends a follow-up message
    asking Dot to fix and re-execute.
    """
    if chat_id is None:
        chat_id = uuid.uuid4().hex

    response = self._query_single(prompt, chat_id)

    # Check for SQL error indicators in the response
    sql_error_patterns = [
        "SQL error", "syntax error", "no such table", "no such column",
        "ambiguous column", "SQLITE_ERROR", "OperationalError",
    ]

    if any(pat.lower() in response.text.lower() for pat in sql_error_patterns):
        logger.warning("SQL error detected in response for chat_id=%s, requesting correction", chat_id)
        correction_prompt = (
            "The previous SQL query had an error. Please fix the SQL and try again. "
            "Remember to end with FINAL_ANSWER: <answer>"
        )
        # Use same chat_id to maintain conversation context
        try:
            response = self._query_single(correction_prompt, chat_id)
        except Exception:
            pass  # Return original response if retry fails

    return response
```

### C5. Enhanced Instrumentation (`src/runner.py`)

#### Add to the record dict (line 153-168):

```python
record = {
    "question_id": task.question_id,
    "difficulty": task.difficulty,
    "guidelines": task.metadata.get("guidelines", ""),
    "chat_id": chat_id,
    "prompt": prompt,
    "dot_response_raw": raw_text,
    "parsed_answer": parsed_answer,
    "ground_truth": task.ground_truth,
    "score": sc,
    "error_type": error_type,
    "dot_mode": dot_mode,
    "dot_status": dot_status,
    "dot_error_body": dot_error_body,
    "latency_s": latency_s,
    # NEW fields:
    "response_length": len(raw_text),
    "has_sql_in_response": bool(re.search(r'\bSELECT\b', raw_text, re.IGNORECASE)),
    "has_sql_error": bool(re.search(r'(?:SQL error|syntax error|no such table|OperationalError)', raw_text, re.IGNORECASE)),
    "question_type": _classify_question_type(task.question, task.metadata.get("guidelines", "")),
}
```

Add a question classifier:

```python
def _classify_question_type(question: str, guidelines: str) -> str:
    """Classify question type for analysis."""
    q_lower = question.lower()
    g_lower = guidelines.lower()
    if "fee id" in q_lower or "fee ids" in q_lower:
        return "fee_id_list"
    if "average fee" in q_lower:
        return "average_fee"
    if "total fee" in q_lower:
        return "total_fee"
    if "delta" in q_lower or "changed to" in q_lower:
        return "fee_delta"
    if "incentiv" in q_lower or "move" in q_lower and "aci" in q_lower:
        return "aci_optimization"
    if "comma separated" in g_lower:
        return "list_answer"
    if "yes or no" in g_lower:
        return "boolean"
    if "country code" in g_lower:
        return "country"
    if "rounded to" in g_lower:
        return "numeric"
    return "other"
```

### C6. Dot Org Instructions Update

The current `data/dot_fee_instructions.md` needs to be updated to match `DOT_INSTRUCTIONS_OPTIMIZED.md`. The key additions are:

1. **Monthly volume/fraud computation** — currently completely absent
2. **Capture delay mapping** — currently absent (the SQL pattern just checks `f.capture_delay = '' OR f.capture_delay = md.capture_delay` which is WRONG because merchant has "1" but fee rules have "<3")
3. **"Not Applicable" guidance** — not present
4. **Date handling reference** — not present

The current SQL pattern in `dot_fee_instructions.md` (line 26-49) has this critical bug:
```sql
(f.capture_delay = '' OR f.capture_delay = md.capture_delay)
```
This checks if fee's capture_delay equals merchant's capture_delay literally, but the merchant stores "1" and the fee stores "<3". They will NEVER match. This needs to be:
```sql
(f.capture_delay IS NULL
  OR (md.capture_delay = 'immediate' AND f.capture_delay = 'immediate')
  OR (md.capture_delay IN ('1','2') AND f.capture_delay = '<3')
  OR (md.capture_delay IN ('3','4','5') AND f.capture_delay = '3-5')
  OR (CAST(md.capture_delay AS INTEGER) > 5 AND f.capture_delay = '>5')
  OR (md.capture_delay = 'manual' AND f.capture_delay = 'manual'))
```

Also the fee matching SQL is completely missing monthly_volume and monthly_fraud_level filters.

---

## D. Prioritized Iteration Plan

### Stage 1: Fix Top Failure Modes (Expected: +3-4 points)

**Priority 1: Update Dot org instructions** (`data/dot_fee_instructions.md`)
- Add monthly volume/fraud computation steps
- Fix capture_delay mapping
- Add "Not Applicable" guidance
- Upload the updated instructions to Dot

**Priority 2: Update SYSTEM_INSTRUCTION** (`src/prompting.py`)
- Inject schema, fee matching rules, and capture_delay mapping into the prompt
- Add REMINDER at end of prompt

**Priority 3: Test on dev10**
```bash
python -m src.runner --client live --dot-mode agentic --source hf --split dev --limit 10 --run-id dot_dev10_agentic_v2
```

**Success criteria:**
- Q70: "Not Applicable" ✓
- Q1273: 0.120132 ✓
- Q1305: 0.123217 ✓
- Q1681: exactly 10 IDs ✓
- Q1753: exactly 34 IDs ✓
- Target: 6/10+ (from 3/10)

### Stage 2: Instruction Tuning + Few-Shot (Expected: +1-2 points)

**Priority 1: Add few-shot examples to the prompt for hard question types:**
- Fee ID listing: show example of computing monthly stats → filtering
- Average fee: show example of averaging across all matching rules
- Fee delta: show worked example
- ACI optimization: show worked example

**Priority 2: Tune capture_delay and intracountry handling**
- Verify Belles_cookbook_store (capture_delay="1") always maps to "<3"
- Verify acquirer_country is used from payments table, not from merchant_data

**Priority 3: Test on dev10 + expand to target30 subset**
```bash
python -m src.runner --client live --dot-mode agentic --source hf --split dev --limit 10 --run-id dot_dev10_agentic_v3
python -m src.runner --client live --dot-mode agentic --source hf --target30 --target-n 5 --run-id dot_target5_agentic_v3
```

**Success criteria:**
- dev10: 8/10+
- target5: 3/5+

### Stage 3: Reliability & Latency (Expected: +0-1 points, stability improvement)

**Priority 1: SQL error retry**
- Implement correction prompt on SQL error detection
- Log SQL queries and errors in JSONL

**Priority 2: Timeout tuning**
- Current timeout: 300s. Some questions take 200s (Q2697: 191s).
- Consider increasing to 600s for hard fee optimization questions.

**Priority 3: Response extraction robustness**
- Add fallback answer patterns
- Handle edge cases in `_extract_assistant_text`

**Priority 4: Full target30 run**
```bash
python -m src.runner --client live --dot-mode agentic --source hf --target30 --run-id dot_target30_v3
```

---

## E. Metrics to Track

| Metric | Current | Stage 1 Target | Stage 2 Target | Stage 3 Target |
|--------|---------|---------------|----------------|----------------|
| Dev10 accuracy | 30% (3/10) | 60%+ (6/10) | 80%+ (8/10) | 90%+ (9/10) |
| % questions with SQL executed | ~80% | 100% | 100% | 100% |
| SQL error rate | unknown | <10% | <5% | <2% |
| Parse failure rate | 0% | 0% | 0% | 0% |
| p95 latency (seconds) | 201s | <120s | <120s | <90s |
| "Not Applicable" precision | 0% | 100% | 100% | 100% |
| Fee ID list exact match | 33% (1/3) | 100% | 100% | 100% |
| Numeric answer accuracy | 0% (0/3) | 67%+ | 100% | 100% |

---

## F. Ablation Experiments

1. **Schema in prompt vs. not**: Does inlining the schema summary help Dot find the right columns?
2. **REMINDER at end vs. not**: Does adding a final reminder reduce format failures?
3. **Timeout 300s vs 600s**: Do longer timeouts help hard fee optimization questions?
4. **Few-shot examples vs. zero-shot**: Do worked examples for fee matching improve accuracy?
5. **Monthly stats pre-computed**: Should we pre-compute monthly stats as a materialized view / extra table in Dot?
6. **Capture delay bucket column**: Should we add a `capture_delay_bucket` column to merchant_data.csv mapping "1" → "<3" etc., so Dot doesn't need to compute the mapping?

---

## G. Quick-Win Data Changes (No Ground Truth Impact)

### G1: Add `capture_delay_bucket` to merchant_data.csv

In `tools/convertJSONtoCSV.py`, add after line 232:

```python
# Map capture_delay to fee-matching bucket
delay = str(capture_delay) if capture_delay else ""
if delay == "immediate":
    capture_delay_bucket = "immediate"
elif delay in ("1", "2"):
    capture_delay_bucket = "<3"
elif delay in ("3", "4", "5"):
    capture_delay_bucket = "3-5"
elif delay == "manual":
    capture_delay_bucket = "manual"
elif delay.isdigit() and int(delay) > 5:
    capture_delay_bucket = ">5"
else:
    capture_delay_bucket = ""
```

Then add `"capture_delay_bucket": capture_delay_bucket` to the mapped dict.

This lets Dot do `f.capture_delay IS NULL OR f.capture_delay = md.capture_delay_bucket` directly.

### G2: Pre-compute monthly aggregates table

Create a `monthly_merchant_stats.csv` with columns:
- merchant, month (1-12), year
- total_volume_eur, total_txn_count
- fraud_volume_eur, fraud_txn_count, fraud_rate
- volume_tier ("<100k", "100k-1m", "1m-5m", ">5m")
- fraud_tier ("<7.2%", "7.2%-7.7%", "7.7%-8.3%", ">8.3%")

Upload to Dot as `monthly_merchant_stats`. This eliminates the need for Dot to compute monthly aggregates at query time, removing the #1 failure mode.
