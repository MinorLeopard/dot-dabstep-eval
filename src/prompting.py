"""Prompt construction and answer parsing for DABStep evaluation."""

from __future__ import annotations

import logging
import re

from src.dabstep_loader import Task

logger = logging.getLogger(__name__)

SYSTEM_INSTRUCTION = (
    "You are answering questions about payment transaction data, merchant fees, and business metrics. "
    "Use SQL via the agentic tools to compute answers. Never guess.\n\n"
    "AVAILABLE TABLES:\n"
    "- payments: psp_reference, merchant, card_scheme, year, day_of_year, is_credit, eur_amount, "
    "issuing_country, acquirer_country, aci, has_fraudulent_dispute, ip_country, device_type, "
    "shopper_interaction, email_address\n"
    "- merchant_data: merchant, account_type (R/D/H/F/S/O), merchant_category_code (int), "
    "capture_delay (string), capture_delay_bucket (pre-mapped bucket), acquirer (list)\n"
    "- fees: ID, card_scheme, account_type (list or empty=all), capture_delay (null=all), "
    "monthly_fraud_level (null=all), monthly_volume (null=all), merchant_category_code (list or empty=all), "
    "is_credit (null=all), aci (list or empty=all), fixed_amount, rate, intracountry (null=all, 0 or 1)\n"
    "- monthly_merchant_stats: merchant, year, month, total_volume_eur, fraud_volume_eur, "
    "fraud_rate, volume_tier, fraud_tier - PRE-COMPUTED monthly aggregates for fee matching\n"
    "- acquirer_countries: acquirer, country_code\n"
    "- merchant_category_codes: mcc, description\n\n"
    "FEE FORMULA: fee = fixed_amount + (rate * eur_amount / 10000.0)\n\n"
    "FEE MATCHING: A fee rule matches when ALL non-null/non-empty criteria match (strict AND). "
    "Null or empty list = 'applies to all'.\n"
    "For fee computations, ALWAYS join payments -> merchant_data on merchant to get "
    "account_type, merchant_category_code, capture_delay_bucket.\n"
    "CAPTURE_DELAY: Use merchant_data.capture_delay_bucket to match fees.capture_delay directly. "
    "Do NOT re-map raw capture_delay values.\n"
    "If multiple fee rules match a transaction: keep only rule(s) with maximum specificity "
    "(most constrained non-null/non-empty fields). If multiple rules tie at max specificity, "
    "use the average fee across tied rules.\n\n"
    "FRAUD FIELD DISAMBIGUATION:\n"
    "- ip_country = shopper's location (by IP)\n"
    "- issuing_country = card-issuing bank's country\n"
    "- acquirer_country = acquiring bank's country\n"
    "These are THREE DIFFERENT fields. Use whichever field the question specifies.\n"
    "'Most commonly used in fraudulent transactions' = highest COUNT of fraudulent transactions.\n"
    "'Top country for fraud' or 'highest fraud' = highest fraud RATE (volume-based):\n"
    "  fraud_rate = SUM(eur_amount WHERE fraud) / SUM(eur_amount) per group. NOT count.\n"
    "Only use COUNT if the question explicitly says 'number of fraud transactions'.\n\n"
    "EMAIL METRICS:\n"
    "- avg_per_unique_email = SUM(eur_amount) / COUNT(DISTINCT non-empty email_address)\n"
    "- repeat_customer_pct = 100 * COUNT(DISTINCT email_address with txn_count > 1) / "
    "COUNT(DISTINCT non-empty email_address)\n"
    "- Ignore NULL email_address and TRIM(email_address) = ''.\n\n"
    "MONTHLY TIER FILTER (CRITICAL - MANDATORY for date/month-specific fee questions):\n"
    "When a question is month-based and only day_of_year is available, derive month from day_of_year ranges first.\n"
    "Use uploads.main.monthly_merchant_stats to get volume_tier and fraud_tier:\n"
    "  SELECT volume_tier, fraud_tier FROM monthly_merchant_stats "
    "WHERE merchant='X' AND year=Y AND month=M;\n"
    "Then filter fees: (f.monthly_volume IS NULL OR f.monthly_volume = volume_tier) "
    "AND (f.monthly_fraud_level IS NULL OR f.monthly_fraud_level = fraud_tier).\n"
    "SKIPPING THIS FILTER WILL RETURN A SUPERSET - WRONG ANSWER.\n\n"
    "APPLICABLE FEE IDS: When asked which fee IDs apply to a merchant on a date/month:\n"
    "1. Query ACTUAL TRANSACTIONS for that merchant/date from payments\n"
    "2. For EACH transaction, find ALL matching fees using the txn's card_scheme, aci, is_credit, "
    "intracountry PLUS merchant attributes and monthly tiers\n"
    "3. Return the UNION of all matching fee IDs across all transactions\n"
    "4. Keep only IDs with supporting_txn_count > 0 from matched transactions\n"
    "Do NOT filter by merchant attributes alone - include transaction-level fields.\n\n"
    "SCENARIO TASKS (ACI incentive, scheme steering, hypothetical fee changes):\n"
    "- Recompute fee per transaction under scenario conditions.\n"
    "- If no fee rule matches under scenario, transaction fee = 0 (do NOT drop transaction).\n"
    "- If wording says 'relative fee' or 'rate' changed to X, set fees.rate = X and keep fixed_amount unchanged.\n"
    "- If wording says 'fixed fee' changed, change fixed_amount.\n\n"
    "INTRACOUNTRY: 1 if payments.issuing_country = payments.acquirer_country, else 0.\n\n"
    "DATE HANDLING: day_of_year 1-indexed. Jan=1-31, Feb=32-59, Mar=60-90, Apr=91-120, "
    "May=121-151, Jun=152-181, Jul=182-212, Aug=213-243, Sep=244-273, Oct=274-304, Nov=305-334, Dec=335-365.\n\n"
    "'NOT APPLICABLE' RULE: If a question asks about a concept not in the data model "
    "(e.g., 'high-fraud rate fine' - there are no fines, only fee rules), answer 'Not Applicable'.\n\n"
    "Reply with ONLY your final answer in EXACTLY this format:\n\n"
    "FINAL_ANSWER: <your answer>\n\n"
    "IMPORTANT RULES:\n"
    "- Your FINAL_ANSWER must contain ONLY the answer value - no explanations, no units unless asked.\n"
    "- Follow the Guidelines section EXACTLY for formatting (commas, decimals, rounding, list format, etc.).\n"
    "- If the Guidelines say 'respond with Not Applicable', use exactly: FINAL_ANSWER: Not Applicable\n"
    "- If you cannot compute the answer, respond: FINAL_ANSWER: Not Applicable\n"
    "- Do NOT say 'I don't know'. Do NOT ask clarifying questions.\n"
    "- You MUST always end your response with the FINAL_ANSWER line."
)

FINAL_ANSWER_PATTERN = re.compile(r"FINAL_ANSWER:\s*(.+?)(?:\n|$)", re.IGNORECASE)
FALLBACK_PATTERNS = [
    re.compile(r"^Final Answer:\s*(.+?)(?:\n|$)", re.IGNORECASE | re.MULTILINE),
]


PROMPT_REMINDER = (
    "REMINDER: Use SQL and never guess. "
    "Fee questions: join payments->merchant_data, derive month from day_of_year when needed, "
    "lookup monthly tiers, and filter by monthly_volume/monthly_fraud_level. "
    "Use max-specificity rule selection; if tie, average tied fees; if no match, fee=0. "
    "Applicable fee IDs: transaction-level union of matching IDs. "
    "Scenario deltas: 'relative fee'/'rate' changed to X means fees.rate=X; "
    "'fixed fee changed' means change fixed_amount. "
    "Fraud wording: 'most common' -> COUNT, 'top/highest fraud' -> RATE unless explicit count. "
    "Use the exact country field asked (ip_country/issuing_country/acquirer_country). "
    "End with FINAL_ANSWER: <answer>"
)

FEE_ID_ANTI_SUPERSET_REMINDER = (
    "FEE-ID ANTI-SUPERSET CHECK (MANDATORY): "
    "Filter transactions to the EXACT requested window first (single day => exact day_of_year; month => month range). "
    "Match fees per transaction using transaction fields (card_scheme, is_credit, aci, intracountry) "
    "plus merchant fields and monthly tiers. "
    "For each fee ID, compute supporting_txn_count from matched transactions and keep only IDs with supporting_txn_count > 0. "
    "Never return fee IDs from merchant-level filtering alone."
)


def _is_fee_id_question(task: Task) -> bool:
    """Return True when question asks for applicable fee IDs or IDs affected by fee rules."""
    text = f"{task.question} {task.metadata.get('guidelines', '')}".lower()
    if (
        "fee id or ids" in text
        or "which merchants were affected by the fee" in text
        or "affected by the fee with id" in text
    ):
        return True
    # Handle both "applicable fee IDs" and "fee IDs applicable" variants.
    has_fee_ids = ("fee id" in text) or ("fee ids" in text)
    has_apply_wording = ("applicable" in text) or ("apply" in text)
    return has_fee_ids and has_apply_wording


def build_prompt(task: Task) -> str:
    """Build the full prompt for a DABStep task."""
    guidelines = task.metadata.get("guidelines", "")
    parts = [SYSTEM_INSTRUCTION]
    if guidelines:
        parts.append(f"Guidelines:\n{guidelines}")
    parts.append(f"Question: {task.question}")
    parts.append(PROMPT_REMINDER)
    if _is_fee_id_question(task):
        parts.append(FEE_ID_ANTI_SUPERSET_REMINDER)
    return "\n\n".join(parts)


def _clean_answer(raw: str) -> str:
    """Apply safe normalization to a parsed answer string."""
    answer = raw.strip()
    # Remove surrounding backticks (``answer`` or `answer`)
    if answer.startswith("```") and answer.endswith("```"):
        answer = answer[3:-3].strip()
    if answer.startswith("`") and answer.endswith("`"):
        answer = answer[1:-1].strip()
    # Remove surrounding quotes
    if len(answer) >= 2 and answer[0] == answer[-1] and answer[0] in ('"', "'"):
        answer = answer[1:-1].strip()
    # Remove trailing period (but not from decimal numbers like "1.23")
    if answer.endswith(".") and not re.match(r"^-?\d+\.\d*\.$", answer):
        answer = answer[:-1].strip()
    # Remove "EUR " prefix if present
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

    Returns None if no FINAL_ANSWER is found.
    Uses the LAST match if multiple FINAL_ANSWER lines exist.
    Falls back to alternative patterns if primary pattern not found.
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
            logger.info("Used fallback pattern to extract answer")
            return _clean_answer(answer)

    logger.warning("No FINAL_ANSWER found in response")
    return None

