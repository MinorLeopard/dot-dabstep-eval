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
    "issuing_country, acquirer_country, aci, has_fraudulent_dispute, ip_country, device_type, shopper_interaction\n"
    "- merchant_data: merchant, account_type (R/D/H/F/S/O), merchant_category_code (int), "
    "capture_delay (string), acquirer (list)\n"
    "- fees: ID, card_scheme, account_type (list or empty=all), capture_delay (null=all), "
    "monthly_fraud_level (null=all), monthly_volume (null=all), merchant_category_code (list or empty=all), "
    "is_credit (null=all), aci (list or empty=all), fixed_amount, rate, intracountry (null=all, 0 or 1)\n"
    "- acquirer_countries: acquirer, country_code\n"
    "- merchant_category_codes: mcc, description\n\n"
    "FEE FORMULA: fee = fixed_amount + (rate * eur_amount / 10000.0)\n\n"
    "FEE MATCHING: A fee rule matches when ALL non-null/non-empty criteria match. "
    "Null or empty list = 'applies to all'.\n\n"
    "CAPTURE_DELAY MAPPING: Merchant delay '1','2' -> fee bucket '<3'; '3','4','5' -> '3-5'; "
    "'7'+ -> '>5'; 'immediate' -> 'immediate'; 'manual' -> 'manual'.\n\n"
    "FRAUD: 'Fraud' means transactions where has_fraudulent_dispute='True'. "
    "When a question asks 'top country for fraud' or 'fraudulent transactions', COUNT the transactions. "
    "The monthly_fraud_level fee field uses a VOLUME ratio (fraud_eur/total_eur), but general fraud questions use counts.\n\n"
    "MONTHLY AGGREGATION (CRITICAL — for fee-matching questions only): "
    "When finding applicable fee IDs or computing fees for a merchant on a specific date/month, "
    "you MUST first compute the merchant's monthly stats for the FULL calendar month:\n"
    "  monthly_vol = SUM(eur_amount) for all merchant transactions in that month\n"
    "  monthly_fraud_rate = SUM(eur_amount WHERE fraud=True) / SUM(eur_amount)\n"
    "Then EXCLUDE fee rules whose monthly_volume or monthly_fraud_level don't match:\n"
    "  Volume tiers: <100k | 100k-1m | 1m-5m | >5m\n"
    "  Fraud tiers: <7.2% | 7.2%-7.7% | 7.7%-8.3% | >8.3%\n"
    "A fee with monthly_volume='<100k' only matches merchants with vol < 100000 EUR that month. "
    "A fee with monthly_volume=NULL matches any volume. DO NOT SKIP THIS FILTER.\n\n"
    "INTRACOUNTRY: 1 if payments.issuing_country = payments.acquirer_country, else 0.\n\n"
    "DATE HANDLING: day_of_year 1-indexed. Jan=1-31, Feb=32-59, Mar=60-90, Apr=91-120, "
    "May=121-151, Jun=152-181, Jul=182-212, Aug=213-243, Sep=244-273, Oct=274-304, Nov=305-334, Dec=335-365.\n\n"
    "'NOT APPLICABLE' RULE: If a question asks about a concept not in the data model "
    "(e.g., 'high-fraud rate fine' — there are no fines, only fee rules), answer 'Not Applicable'.\n\n"
    "Reply with ONLY your final answer in EXACTLY this format:\n\n"
    "FINAL_ANSWER: <your answer>\n\n"
    "IMPORTANT RULES:\n"
    "- Your FINAL_ANSWER must contain ONLY the answer value — no explanations, no units unless asked.\n"
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
    "REMINDER: Use SQL to compute the answer. "
    "For fee-related questions, apply ALL matching criteria including monthly_volume "
    "and monthly_fraud_level (compute from payments table for the full calendar month first). "
    "Map merchant capture_delay to fee buckets: '1','2'->'<3'; '3','4','5'->'3-5'; '7'->'>5'. "
    "End with FINAL_ANSWER: <answer>"
)


def build_prompt(task: Task) -> str:
    """Build the full prompt for a DABStep task."""
    guidelines = task.metadata.get("guidelines", "")
    parts = [SYSTEM_INSTRUCTION]
    if guidelines:
        parts.append(f"Guidelines:\n{guidelines}")
    parts.append(f"Question: {task.question}")
    parts.append(PROMPT_REMINDER)
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
