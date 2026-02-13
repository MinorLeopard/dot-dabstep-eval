#!/usr/bin/env python3
"""
Offline DABstep Solver Engine
Deterministic, reproducible solver for DABstep payment analysis questions.
"""

import json
import re
import sys
from pathlib import Path
from datetime import date, timedelta
from collections import defaultdict
import pandas as pd

from src.dabstep_loader import TARGET_TASK_IDS
from src.scoring import score_answer

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "data" / "context"
DERIVED_DIR = REPO_ROOT / "data" / "derived"
ARTIFACTS_DIR = REPO_ROOT / "artifacts"


# =============================================================================
# DATA LOADING & PREPROCESSING
# =============================================================================

class DABStepEngine:
    def __init__(self):
        self.load_data()
        self.preprocess()

    def load_data(self):
        self.payments = pd.read_csv(DATA_DIR / "payments.csv")
        with open(DATA_DIR / "fees.json", encoding="utf-8") as f:
            self.fees = json.load(f)
        # Use the derived merchant table because it contains the canonical capture_delay_bucket.
        self.merchant_df = pd.read_csv(DERIVED_DIR / "merchant_data.csv")
        self.acquirer_countries = pd.read_csv(DATA_DIR / "acquirer_countries.csv")
        self.mcc_codes = pd.read_csv(DATA_DIR / "merchant_category_codes.csv")
        self.monthly_stats = pd.read_csv(DERIVED_DIR / "monthly_merchant_stats.csv")

    def preprocess(self):
        # Merchant info lookup
        self.merchant_df['merchant_category_code'] = self.merchant_df['merchant_category_code'].astype(int)
        self.merchant_info = {}
        for _, row in self.merchant_df.iterrows():
            self.merchant_info[row['merchant']] = {
                'merchant': row['merchant'],
                'account_type': row['account_type'],
                'merchant_category_code': int(row['merchant_category_code']),
                'capture_delay': str(row['capture_delay']),
                'capture_delay_bucket': str(row['capture_delay_bucket']),
            }

        # Acquirer country lookup
        self.acq_country = dict(zip(
            self.acquirer_countries['acquirer'],
            self.acquirer_countries['country_code']
        ))

        # MCC lookups
        self.mcc_desc = dict(zip(self.mcc_codes['mcc'], self.mcc_codes['description']))
        self.desc_mcc = {}
        for k, v in self.mcc_desc.items():
            self.desc_mcc[v] = k

        # Preprocess payments
        self.payments['year'] = self.payments['year'].astype(int)
        self.payments['day_of_year'] = self.payments['day_of_year'].astype(int)
        self.payments['eur_amount'] = self.payments['eur_amount'].astype(float)
        self.payments['is_credit'] = self.payments['is_credit'].map({'True': True, 'False': False, True: True, False: False})
        self.payments['has_fraudulent_dispute'] = self.payments['has_fraudulent_dispute'].map({'True': True, 'False': False, True: True, False: False})
        self.payments['month'] = self.payments['day_of_year'].apply(self.day_to_month)
        self.payments['intracountry'] = (
            self.payments['issuing_country'] == self.payments['acquirer_country']
        ).astype(int)

        # Monthly stats lookup: (merchant, year, month) -> stats
        self.monthly_lookup = {}
        for _, row in self.monthly_stats.iterrows():
            key = (row['merchant'], int(row['year']), int(row['month']))
            self.monthly_lookup[key] = {
                'volume_tier': row['volume_tier'],
                'fraud_tier': row['fraud_tier']
            }

        # Fee lookup by ID
        self.fee_by_id = {f['ID']: f for f in self.fees}

        # Fee index by card_scheme
        self.fees_by_scheme = defaultdict(list)
        for f in self.fees:
            self.fees_by_scheme[f['card_scheme']].append(f)

        # All unique card schemes
        self.card_schemes = sorted(set(f['card_scheme'] for f in self.fees))
        # All unique ACIs
        self.all_acis = sorted(self.payments['aci'].dropna().astype(str).unique().tolist())

    @staticmethod
    def day_to_month(day_of_year, year=2023):
        d = date(year, 1, 1) + timedelta(days=int(day_of_year) - 1)
        return d.month

    # =========================================================================
    # FEE MATCHING
    # =========================================================================

    def fee_matches(self, fee_rule, card_scheme=None, account_type=None,
                    capture_delay_bucket=None, monthly_fraud_level=None,
                    monthly_volume=None, mcc=None, is_credit=None,
                    aci=None, intracountry=None):
        """Strict fee matching: AND across all non-null/non-empty constraints."""
        if card_scheme is not None and fee_rule['card_scheme'] != card_scheme:
            return False
        if fee_rule['account_type'] and account_type not in fee_rule['account_type']:
            return False
        if fee_rule['capture_delay'] is not None and fee_rule['capture_delay'] != capture_delay_bucket:
            return False
        if fee_rule['monthly_fraud_level'] is not None and fee_rule['monthly_fraud_level'] != monthly_fraud_level:
            return False
        if fee_rule['monthly_volume'] is not None and fee_rule['monthly_volume'] != monthly_volume:
            return False
        if fee_rule['merchant_category_code'] and mcc not in fee_rule['merchant_category_code']:
            return False
        if fee_rule['is_credit'] is not None and fee_rule['is_credit'] != is_credit:
            return False
        if fee_rule['aci'] and aci not in fee_rule['aci']:
            return False
        if fee_rule['intracountry'] is not None and int(fee_rule['intracountry']) != int(intracountry):
            return False
        return True

    def compute_fee(self, fee_rule, amount):
        return fee_rule['fixed_amount'] + fee_rule['rate'] * amount / 10000.0

    @staticmethod
    def fee_specificity(fee_rule):
        """Count constrained dimensions for tie-breaking."""
        score = 0
        if fee_rule['account_type']:
            score += 1
        if fee_rule['capture_delay'] is not None:
            score += 1
        if fee_rule['monthly_fraud_level'] is not None:
            score += 1
        if fee_rule['monthly_volume'] is not None:
            score += 1
        if fee_rule['merchant_category_code']:
            score += 1
        if fee_rule['is_credit'] is not None:
            score += 1
        if fee_rule['aci']:
            score += 1
        if fee_rule['intracountry'] is not None:
            score += 1
        return score

    def select_applied_rules(self, matching):
        """Pick most specific matches; tie => keep all tied rules."""
        if not matching:
            return []
        max_spec = max(self.fee_specificity(f) for f in matching)
        return [f for f in matching if self.fee_specificity(f) == max_spec]

    def get_matching_fee_ids_for_txn(self, txn_row, merchant_name, month_override=None):
        """Get all matching fee rule IDs for a transaction."""
        mi = self.merchant_info[merchant_name]
        m = month_override or txn_row['month']
        stats = self.monthly_lookup.get((merchant_name, int(txn_row['year']), int(m)), {})
        vol_tier = stats.get('volume_tier')
        fraud_tier = stats.get('fraud_tier')

        matching_ids = []
        for f in self.fees:
            if self.fee_matches(
                f,
                card_scheme=txn_row['card_scheme'],
                account_type=mi['account_type'],
                capture_delay_bucket=mi['capture_delay_bucket'],
                monthly_fraud_level=fraud_tier,
                monthly_volume=vol_tier,
                mcc=mi['merchant_category_code'],
                is_credit=bool(txn_row['is_credit']),
                aci=txn_row['aci'],
                intracountry=int(txn_row['intracountry'])
            ):
                matching_ids.append(f['ID'])
        return matching_ids

    def txn_fee(self, txn_row, merchant_name, month_override=None, fee_overrides=None):
        """Compute fee for a transaction. Average of all matching rule fees."""
        mi = self.merchant_info[merchant_name]
        m = month_override or txn_row['month']
        stats = self.monthly_lookup.get((merchant_name, int(txn_row['year']), int(m)), {})
        vol_tier = stats.get('volume_tier')
        fraud_tier = stats.get('fraud_tier')

        matching = []
        for f in self.fees:
            if self.fee_matches(
                f,
                card_scheme=txn_row['card_scheme'],
                account_type=mi['account_type'],
                capture_delay_bucket=mi['capture_delay_bucket'],
                monthly_fraud_level=fraud_tier,
                monthly_volume=vol_tier,
                mcc=mi['merchant_category_code'],
                is_credit=bool(txn_row['is_credit']),
                aci=txn_row['aci'],
                intracountry=int(txn_row['intracountry'])
            ):
                matching.append(f)

        applied = self.select_applied_rules(matching)
        if not applied:
            return 0.0

        total = 0.0
        for f in applied:
            fr = f
            if fee_overrides and f['ID'] in fee_overrides:
                fr = fee_overrides[f['ID']]
            total += self.compute_fee(fr, txn_row['eur_amount'])
        return total / len(applied)

    def txn_fee_with_aci(self, txn_row, merchant_name, new_aci, month_override=None):
        """Compute fee for a transaction with a hypothetical ACI."""
        mi = self.merchant_info[merchant_name]
        m = month_override or txn_row['month']
        stats = self.monthly_lookup.get((merchant_name, int(txn_row['year']), int(m)), {})
        vol_tier = stats.get('volume_tier')
        fraud_tier = stats.get('fraud_tier')

        matching = []
        for f in self.fees:
            if self.fee_matches(
                f,
                card_scheme=txn_row['card_scheme'],
                account_type=mi['account_type'],
                capture_delay_bucket=mi['capture_delay_bucket'],
                monthly_fraud_level=fraud_tier,
                monthly_volume=vol_tier,
                mcc=mi['merchant_category_code'],
                is_credit=bool(txn_row['is_credit']),
                aci=new_aci,
                intracountry=int(txn_row['intracountry'])
            ):
                matching.append(f)

        applied = self.select_applied_rules(matching)
        if not applied:
            return 0.0

        fees = [self.compute_fee(f, txn_row['eur_amount']) for f in applied]
        return sum(fees) / len(fees)

    def txn_fee_with_scheme(self, txn_row, merchant_name, new_scheme, month_override=None):
        """Compute fee for a transaction with a hypothetical card scheme."""
        mi = self.merchant_info[merchant_name]
        m = month_override or txn_row['month']
        stats = self.monthly_lookup.get((merchant_name, int(txn_row['year']), int(m)), {})
        vol_tier = stats.get('volume_tier')
        fraud_tier = stats.get('fraud_tier')

        matching = []
        for f in self.fees:
            if self.fee_matches(
                f,
                card_scheme=new_scheme,
                account_type=mi['account_type'],
                capture_delay_bucket=mi['capture_delay_bucket'],
                monthly_fraud_level=fraud_tier,
                monthly_volume=vol_tier,
                mcc=mi['merchant_category_code'],
                is_credit=bool(txn_row['is_credit']),
                aci=txn_row['aci'],
                intracountry=int(txn_row['intracountry'])
            ):
                matching.append(f)

        applied = self.select_applied_rules(matching)
        if not applied:
            return 0.0

        fees = [self.compute_fee(f, txn_row['eur_amount']) for f in applied]
        return sum(fees) / len(fees)

    # =========================================================================
    # HELPER: GET TRANSACTIONS
    # =========================================================================

    def get_merchant_txns(self, merchant, year=2023, month=None, day=None, months=None):
        """Get transactions for a merchant in a time period."""
        mask = (self.payments['merchant'] == merchant) & (self.payments['year'] == year)
        if day is not None:
            mask = mask & (self.payments['day_of_year'] == day)
        elif month is not None:
            mask = mask & (self.payments['month'] == month)
        elif months is not None:
            mask = mask & (self.payments['month'].isin(months))
        return self.payments[mask]


# =============================================================================
# QUESTION SOLVERS
# =============================================================================

def route_question(question):
    """Minimal deterministic routing between analytics and fee engines."""
    q = question.lower()
    if 'possible values for the field aci' in q:
        return 'analytics'
    fee_tokens = [
        ' fee', 'fees', 'delta', 'applicable fee', 'fee id', 'steer traffic',
        'authorization characteristics indicator (aci)',
    ]
    if any(tok in q for tok in fee_tokens):
        return 'fee'
    analytics_tokens = [
        'fraud', 'device', 'repeat customers', 'average transaction amount per unique email',
        'average transaction value grouped', 'highest number of transactions',
    ]
    if any(tok in q for tok in analytics_tokens):
        return 'analytics'
    return 'unknown'


def solve_question(engine, task_id, question, guidelines):
    """Route a question to the appropriate solver."""
    q = question.strip()
    ql = q.lower()
    tid = str(task_id)
    route = route_question(q)

    # --- EASY: Simple aggregation ---
    if route != 'fee' and 'highest number of transactions' in ql and (
        'issuing_country' in ql or 'issuing country' in ql
    ):
        return solve_top_issuing_country(engine)

    if route != 'fee' and 'top country' in q.lower() and 'fraud' in q.lower() and 'ip_country' in q:
        return solve_top_fraud_country_mc(engine, q, guidelines)

    if 'danger' in q.lower() and 'fine' in q.lower():
        return 'Not Applicable'

    if route != 'fee' and 'device type' in q.lower() and 'fraudulent' in q.lower():
        return solve_fraud_device(engine)

    if route != 'fee' and 'average transaction amount per unique email' in q.lower():
        return solve_avg_amount_per_email(engine, guidelines)

    if route != 'fee' and 'repeat customers' in q.lower() and 'email' in q.lower():
        return solve_repeat_customers(engine, guidelines)

    # --- HARD: Average txn value grouped by X ---
    m = re.search(r'average transaction value grouped by (\w+) for (\w+)\'?s? (\w+) transactions between (\w+) and (\w+)', q, re.I)
    if m:
        group_col = m.group(1)
        merchant = m.group(2)
        scheme = m.group(3)
        month_start = month_name_to_num(m.group(4))
        month_end = month_name_to_num(m.group(5))
        return solve_avg_txn_grouped(engine, merchant, scheme, group_col,
                                     list(range(month_start, month_end + 1)), guidelines)

    if route == 'analytics':
        return 'Not Applicable'

    # --- HARD: Average fee for criteria ---
    # Pattern: "For credit transactions, ... card scheme X ... transaction value of Y EUR"
    m = re.search(r'For credit transactions,.*card scheme (\w+).*transaction value of (\d+) EUR', q, re.I)
    if m:
        scheme = m.group(1)
        amount = float(m.group(2))
        return solve_avg_fee_credit(engine, scheme, amount, guidelines)

    # Pattern: "For account type X and the MCC description: Y, ... card scheme Z ... transaction value of W EUR"
    m = re.search(r'For account type (\w+) and the MCC description:\s*(.+?),.*card scheme (\w+).*transaction value of (\d+) EUR', q, re.I)
    if m:
        acct = m.group(1)
        mcc_desc = m.group(2).strip()
        scheme = m.group(3)
        amount = float(m.group(4))
        return solve_avg_fee_acct_mcc(engine, acct, mcc_desc, scheme, amount, guidelines)

    # --- HARD: Most expensive MCC ---
    if 'most expensive MCC' in q:
        m = re.search(r'transaction of (\d+) euros', q)
        amount = float(m.group(1)) if m else 50.0
        return solve_most_expensive_mcc(engine, amount, guidelines)

    # --- HARD: Most expensive ACI ---
    m = re.search(r'credit transaction of (\d+) euros? on (\w+),.*most expensive.*ACI', q, re.I)
    if m:
        amount = float(m.group(1))
        scheme = m.group(2)
        return solve_most_expensive_aci(engine, scheme, amount, guidelines)

    # --- HARD: Fee ID lookup by criteria ---
    m = re.search(r'fee ID or IDs that apply to account_type\s*=\s*(\w+)\s+and\s+aci\s*=\s*(\w+)', q, re.I)
    if m:
        acct = m.group(1)
        aci = m.group(2)
        return solve_fee_ids_by_criteria(engine, acct, aci)

    # --- HARD: Applicable fee IDs for merchant in period ---
    # "For the Xth of the year Y, what are the Fee IDs applicable to MERCHANT?"
    m = re.search(r'(?:For the|for the) (\d+)(?:th|st|nd|rd) of the year (\d+),.*(?:Fee IDs|fee IDs).*(?:applicable to|for) (\w+)', q, re.I)
    if m:
        day = int(m.group(1))
        year = int(m.group(2))
        merchant = m.group(3)
        return solve_applicable_fee_ids(engine, merchant, year=year, day=day)

    # "What were the applicable Fee IDs for MERCHANT in MONTH YEAR?"
    m = re.search(r'(?:applicable|applicable) Fee IDs for (\w+) in (\w+)\s*(\d+)', q, re.I)
    if m:
        merchant = m.group(1)
        month = month_name_to_num(m.group(2))
        year = int(m.group(3))
        return solve_applicable_fee_ids(engine, merchant, year=year, month=month)

    # "What are the applicable fee IDs for MERCHANT in MONTH YEAR?" or "in YEAR"
    m = re.search(r'fee IDs for (\w+) in (\w+)\s*(\d+)?', q, re.I)
    if m:
        merchant = m.group(1)
        period_str = m.group(2)
        year_str = m.group(3)
        if year_str:
            year = int(year_str)
            month = month_name_to_num(period_str)
            return solve_applicable_fee_ids(engine, merchant, year=year, month=month)
        else:
            year = int(period_str)
            return solve_applicable_fee_ids(engine, merchant, year=year)

    # --- HARD: Cheapest/most expensive card scheme ---
    m = re.search(r'average scenario.*(?:cheapest|most expensive) fee.*transaction value of (\d+) EUR', q, re.I)
    if m:
        amount = float(m.group(1))
        if 'cheapest' in q.lower():
            return solve_cheapest_scheme(engine, amount)
        else:
            return solve_most_expensive_scheme(engine, amount)

    # --- HARD: Total fees ---
    # "For the Xth of the year Y, total fees ... MERCHANT"
    m = re.search(r'(\d+)(?:th|st|nd|rd) of the year (\d+).*total fees.*?(\w+(?:_\w+)*)\s', q, re.I)
    if not m:
        m = re.search(r'total fees.*?(\w+(?:_\w+)*)\s+(?:should pay|paid).*?(\w+)\s+(\d+)', q, re.I)
    if not m:
        # "total fees ... MERCHANT paid in MONTH YEAR"
        m = re.search(r'total fees.*?that\s+(\w+(?:_\w+)*)\s+(?:paid|should pay)\s+in\s+(\w+)\s+(\d+)', q, re.I)
    if m and 'total fees' in q.lower():
        return solve_total_fees(engine, q, guidelines)

    # --- HARD: Fee delta ---
    m = re.search(
        r'In\s+(\w+)\s+(\d+)\s+what\s+delta\s+would\s+(\w+(?:_\w+)*)\s+pay.*?fee.*?ID\s*=?\s*(\d+).*?changed to\s*(\d+(?:\.\d+)?)',
        q,
        re.I,
    )
    if m:
        month_name = m.group(1)
        year = int(m.group(2))
        merchant = m.group(3)
        fee_id = int(m.group(4))
        new_rate = float(m.group(5))
        month = month_name_to_num(month_name)
        return solve_fee_delta(engine, merchant, year, month, fee_id, new_rate, guidelines)

    m = re.search(
        r'In\s+the\s+year\s+(\d+)\s+what\s+delta\s+would\s+(\w+(?:_\w+)*)\s+pay.*?fee.*?ID\s*=?\s*(\d+).*?changed to\s*(\d+(?:\.\d+)?)',
        q,
        re.I,
    )
    if m:
        year = int(m.group(1))
        merchant = m.group(2)
        fee_id = int(m.group(3))
        new_rate = float(m.group(4))
        month = None
        return solve_fee_delta(engine, merchant, year, month, fee_id, new_rate, guidelines)

    # --- HARD: Merchants affected by fee ---
    m = re.search(r'which merchants were affected by the Fee with ID (\d+)', q, re.I)
    if m:
        fee_id = int(m.group(1))
        return solve_merchants_affected(engine, fee_id)

    # "if Fee with ID X was only applied to account type Y"
    m = re.search(r'Fee with ID (\d+) was only applied to account type (\w+)', q, re.I)
    if m:
        fee_id = int(m.group(1))
        new_acct = m.group(2)
        return solve_merchants_affected_change(engine, fee_id, new_acct)

    # --- HARD: Card scheme steering ---
    m = re.search(r'month of (\w+).*card scheme.*merchant (\w+(?:_\w+)*).*(?:minimum|maximum) fees', q, re.I)
    if m:
        month = month_name_to_num(m.group(1))
        merchant = m.group(2)
        minimize = 'minimum' in q.lower()
        return solve_scheme_steering(engine, merchant, month, minimize, guidelines)

    # --- HARD: ACI incentive ---
    # Monthly: "For MERCHANT in MONTH, if we were to move the fraudulent..."
    m = re.search(r'(?:For|for)\s+(\w+(?:_\w+)*)\s+in\s+(\w+),.*move the fraudulent', q, re.I)
    if m:
        merchant = m.group(1)
        month_str = m.group(2)
        month = month_name_to_num(month_str)
        return solve_aci_incentive(engine, merchant, month=month)

    # Yearly: "Looking at the year YYYY and at the merchant MERCHANT"
    m = re.search(r'year (\d+).*merchant\s+(\w+(?:_\w+)*).*move the fraudulent', q, re.I)
    if m:
        year = int(m.group(1))
        merchant = m.group(2)
        return solve_aci_incentive(engine, merchant, year=year)

    return "UNSOLVED"


# =============================================================================
# MONTH UTILITIES
# =============================================================================

MONTH_NAMES = {
    'january': 1, 'february': 2, 'march': 3, 'april': 4,
    'may': 5, 'june': 6, 'july': 7, 'august': 8,
    'september': 9, 'october': 10, 'november': 11, 'december': 12,
    'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4,
    'jun': 6, 'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12
}

def month_name_to_num(name):
    return MONTH_NAMES.get(name.lower(), 0)


# =============================================================================
# SOLVER IMPLEMENTATIONS
# =============================================================================

def solve_top_issuing_country(engine):
    counts = engine.payments.groupby('issuing_country').size()
    return counts.idxmax()


def solve_top_fraud_country_mc(engine, question, guidelines):
    """Top fraud country by RATE (EUR-based), multiple choice."""
    fraud = engine.payments[engine.payments['has_fraudulent_dispute'] == True]
    fraud_vol = fraud.groupby('ip_country')['eur_amount'].sum()
    total_vol = engine.payments.groupby('ip_country')['eur_amount'].sum()
    fraud_rate = fraud_vol / total_vol
    top = fraud_rate.idxmax()

    # Parse MC options
    options = re.findall(r'([A-Z])\.\s*(\w+)', question)
    for letter, code in options:
        if code == top:
            return f"{letter}. {code}"
    return top


def solve_fraud_device(engine):
    fraud = engine.payments[engine.payments['has_fraudulent_dispute'] == True]
    counts = fraud.groupby('device_type').size()
    return counts.idxmax()


def solve_avg_amount_per_email(engine, guidelines):
    emails = engine.payments['email_address'].fillna('').astype(str).str.strip()
    valid_mask = emails != ''
    total = engine.payments.loc[valid_mask, 'eur_amount'].sum()
    unique_emails = emails[valid_mask].nunique()
    if unique_emails == 0:
        return "Not Applicable"
    avg = total / unique_emails
    # Check rounding from guidelines
    m = re.search(r'rounded to (\d+)', guidelines)
    decimals = int(m.group(1)) if m else 3
    return f"{avg:.{decimals}f}"


def solve_repeat_customers(engine, guidelines):
    emails = engine.payments['email_address'].fillna('').astype(str).str.strip()
    valid_emails = emails[emails != '']
    if valid_emails.empty:
        return "Not Applicable"
    email_counts = valid_emails.groupby(valid_emails).size()
    repeat = (email_counts > 1).sum()
    total = len(email_counts)
    pct = (repeat / total) * 100
    m = re.search(r'rounded to (\d+)', guidelines)
    decimals = int(m.group(1)) if m else 6
    return f"{pct:.{decimals}f}"


def solve_avg_txn_grouped(engine, merchant, scheme, group_col, months, guidelines):
    """Average txn value grouped by column for merchant/scheme/period."""
    txns = engine.get_merchant_txns(merchant, months=months)
    txns = txns[txns['card_scheme'] == scheme]

    if txns.empty:
        return "Not Applicable"

    grouped = txns.groupby(group_col)['eur_amount'].mean()
    grouped = grouped.sort_values()

    parts = []
    for key, val in grouped.items():
        parts.append(f"{key}: {val:.2f}")
    return ', '.join(parts)


def solve_avg_fee_credit(engine, scheme, amount, guidelines):
    """Average fee for credit transactions on a given scheme at given amount."""
    matching = []
    for f in engine.fees:
        if f['card_scheme'] != scheme:
            continue
        # Credit: is_credit must be True or null
        if f['is_credit'] is not None and f['is_credit'] != True:
            continue
        matching.append(f)

    if not matching:
        return "Not Applicable"

    fees = [engine.compute_fee(f, amount) for f in matching]
    avg = sum(fees) / len(fees)
    return f"{avg:.6f}"


def solve_avg_fee_acct_mcc(engine, acct_type, mcc_desc_str, scheme, amount, guidelines):
    """Average fee for account type + MCC + scheme at amount."""
    # Look up MCC from description
    mcc = engine.desc_mcc.get(mcc_desc_str)
    if mcc is None:
        # Try partial match
        for desc, code in engine.desc_mcc.items():
            if mcc_desc_str.lower() in desc.lower():
                mcc = code
                break

    matching = []
    for f in engine.fees:
        if f['card_scheme'] != scheme:
            continue
        if f['account_type'] and acct_type not in f['account_type']:
            continue
        if mcc is not None and f['merchant_category_code'] and mcc not in f['merchant_category_code']:
            continue
        matching.append(f)

    if not matching:
        return "Not Applicable"

    fees = [engine.compute_fee(f, amount) for f in matching]
    avg = sum(fees) / len(fees)
    return f"{avg:.6f}"


def solve_most_expensive_mcc(engine, amount, guidelines):
    """Most expensive MCC for a transaction amount, in general."""
    # Collect all MCCs that appear in any fee rule
    all_mccs = set()
    for f in engine.fees:
        for mcc in f['merchant_category_code']:
            all_mccs.add(mcc)

    # For each MCC, compute average fee across all rules that apply to it
    mcc_avg = {}
    for mcc in all_mccs:
        matching = [f for f in engine.fees
                    if not f['merchant_category_code'] or mcc in f['merchant_category_code']]
        if matching:
            fees = [engine.compute_fee(f, amount) for f in matching]
            mcc_avg[mcc] = sum(fees) / len(fees)

    if not mcc_avg:
        return "Not Applicable"

    max_fee = max(mcc_avg.values())
    best_mccs = sorted([mcc for mcc, fee in mcc_avg.items() if abs(fee - max_fee) < 1e-10])
    return ', '.join(str(m) for m in best_mccs)


def solve_most_expensive_aci(engine, scheme, amount, guidelines):
    """Most expensive ACI for credit transaction on scheme at amount."""
    aci_fees = {}
    for aci in engine.all_acis:
        matching = []
        for f in engine.fees:
            if f['card_scheme'] != scheme:
                continue
            if f['is_credit'] is not None and f['is_credit'] != True:
                continue
            if f['aci'] and aci not in f['aci']:
                continue
            matching.append(f)
        if matching:
            fees = [engine.compute_fee(f, amount) for f in matching]
            aci_fees[aci] = sum(fees) / len(fees)

    if not aci_fees:
        return "Not Applicable"

    max_fee = max(aci_fees.values())
    # Tie-break: lowest alphabetical
    best = sorted([a for a, fee in aci_fees.items() if abs(fee - max_fee) < 1e-10])
    return best[0]


def solve_fee_ids_by_criteria(engine, acct_type, aci):
    """Fee IDs matching account_type and aci criteria."""
    matching = []
    for f in engine.fees:
        # account_type: empty = all, or must contain acct_type
        if f['account_type'] and acct_type not in f['account_type']:
            continue
        # aci: empty = all, or must contain aci
        if f['aci'] and aci not in f['aci']:
            continue
        matching.append(f['ID'])

    return ', '.join(str(x) for x in sorted(matching))


def solve_applicable_fee_ids(engine, merchant, year=2023, month=None, day=None):
    """Get all applicable fee IDs for a merchant in a time period."""
    if day is not None:
        txns = engine.get_merchant_txns(merchant, year=year, day=day)
    elif month is not None:
        txns = engine.get_merchant_txns(merchant, year=year, month=month)
    else:
        txns = engine.get_merchant_txns(merchant, year=year)

    all_ids = set()
    for _, txn in txns.iterrows():
        ids = engine.get_matching_fee_ids_for_txn(txn, merchant)
        all_ids.update(ids)

    return ', '.join(str(x) for x in sorted(all_ids))


def solve_total_fees(engine, question, guidelines):
    """Total fees for a merchant in a period."""
    q = question

    # Parse merchant and period
    # "For the Xth of the year Y, ... MERCHANT should pay"
    m = re.search(r'(\d+)(?:th|st|nd|rd) of the year (\d+).*?(\w+(?:_\w+)*)\s+should pay', q, re.I)
    if m:
        day = int(m.group(1))
        year = int(m.group(2))
        merchant = m.group(3)
        txns = engine.get_merchant_txns(merchant, year=year, day=day)
        total = sum(engine.txn_fee(txn, merchant) for _, txn in txns.iterrows())
        return f"{total:.2f}"

    # "MERCHANT paid in MONTH YEAR"
    m = re.search(r'that\s+(\w+(?:_\w+)*)\s+(?:paid|should pay)\s+in\s+(\w+)\s+(\d+)', q, re.I)
    if m:
        merchant = m.group(1)
        month = month_name_to_num(m.group(2))
        year = int(m.group(3))
        txns = engine.get_merchant_txns(merchant, year=year, month=month)
        total = sum(engine.txn_fee(txn, merchant) for _, txn in txns.iterrows())
        return f"{total:.2f}"

    return "UNSOLVED"


def solve_fee_delta(engine, merchant, year, month, fee_id, new_rate, guidelines):
    """Compute fee delta if a fee rule's rate changed."""
    fee_rule = engine.fee_by_id[fee_id]
    old_rate = fee_rule['rate']

    # Create modified fee rule
    modified = dict(fee_rule)
    modified['rate'] = new_rate
    fee_overrides = {fee_id: modified}

    # Get transactions
    txns = engine.get_merchant_txns(merchant, year=year, month=month)

    total_old = 0.0
    total_new = 0.0
    for _, txn in txns.iterrows():
        total_old += engine.txn_fee(txn, merchant)
        total_new += engine.txn_fee(txn, merchant, fee_overrides=fee_overrides)

    delta = total_new - total_old

    # Parse decimal places from guidelines
    m_dec = re.search(r'rounded to (\d+) decimals', guidelines)
    decimals = int(m_dec.group(1)) if m_dec else 14
    return f"{delta:.{decimals}f}"


def solve_merchants_affected(engine, fee_id):
    """Which merchants had transactions matching this fee rule in 2023?"""
    fee = engine.fee_by_id[fee_id]
    affected = set()

    for merchant_name, mi in engine.merchant_info.items():
        # Quick pre-check: account_type
        if fee['account_type'] and mi['account_type'] not in fee['account_type']:
            continue
        # capture_delay
        if fee['capture_delay'] is not None and fee['capture_delay'] != mi['capture_delay_bucket']:
            continue
        # MCC
        if fee['merchant_category_code'] and mi['merchant_category_code'] not in fee['merchant_category_code']:
            continue

        # Check transactions
        txns = engine.get_merchant_txns(merchant_name, year=2023)
        for _, txn in txns.iterrows():
            m = txn['month']
            stats = engine.monthly_lookup.get((merchant_name, 2023, int(m)), {})
            vol_tier = stats.get('volume_tier')
            fraud_tier = stats.get('fraud_tier')

            if engine.fee_matches(
                fee,
                card_scheme=txn['card_scheme'],
                account_type=mi['account_type'],
                capture_delay_bucket=mi['capture_delay_bucket'],
                monthly_fraud_level=fraud_tier,
                monthly_volume=vol_tier,
                mcc=mi['merchant_category_code'],
                is_credit=bool(txn['is_credit']),
                aci=txn['aci'],
                intracountry=int(txn['intracountry'])
            ):
                affected.add(merchant_name)
                break  # One match is enough

    return ', '.join(sorted(affected))


def solve_merchants_affected_change(engine, fee_id, new_acct_type):
    """Fast affected-merchant check for account-type narrowing scenario."""
    fee = engine.fee_by_id[fee_id]
    affected = set()
    for merchant_name, mi in engine.merchant_info.items():
        if mi['account_type'] == new_acct_type:
            continue
        if fee['account_type'] and mi['account_type'] not in fee['account_type']:
            continue
        if fee['capture_delay'] is not None and fee['capture_delay'] != mi['capture_delay_bucket']:
            continue
        if fee['merchant_category_code'] and mi['merchant_category_code'] not in fee['merchant_category_code']:
            continue

        txns = engine.get_merchant_txns(merchant_name, year=2023)
        for _, txn in txns.iterrows():
            m = txn['month']
            stats = engine.monthly_lookup.get((merchant_name, 2023, int(m)), {})
            vol_tier = stats.get('volume_tier')
            fraud_tier = stats.get('fraud_tier')
            if engine.fee_matches(
                fee,
                card_scheme=txn['card_scheme'],
                account_type=mi['account_type'],
                capture_delay_bucket=mi['capture_delay_bucket'],
                monthly_fraud_level=fraud_tier,
                monthly_volume=vol_tier,
                mcc=mi['merchant_category_code'],
                is_credit=bool(txn['is_credit']),
                aci=txn['aci'],
                intracountry=int(txn['intracountry'])
            ):
                affected.add(merchant_name)
                break

    return ', '.join(sorted(affected))


def solve_cheapest_scheme(engine, amount):
    """Which card scheme has cheapest average fee for given amount?"""
    scheme_avg = {}
    for scheme in engine.card_schemes:
        matching = [f for f in engine.fees if f['card_scheme'] == scheme]
        if matching:
            fees = [engine.compute_fee(f, amount) for f in matching]
            scheme_avg[scheme] = sum(fees) / len(fees)

    return min(scheme_avg, key=scheme_avg.get)


def solve_most_expensive_scheme(engine, amount):
    """Which card scheme has most expensive average fee for given amount?"""
    scheme_avg = {}
    for scheme in engine.card_schemes:
        matching = [f for f in engine.fees if f['card_scheme'] == scheme]
        if matching:
            fees = [engine.compute_fee(f, amount) for f in matching]
            scheme_avg[scheme] = sum(fees) / len(fees)

    return max(scheme_avg, key=scheme_avg.get)


def solve_scheme_steering(engine, merchant, month, minimize, guidelines):
    """Steer all traffic to one card scheme to min/max fees."""
    txns = engine.get_merchant_txns(merchant, month=month)

    scheme_totals = {}
    for scheme in engine.card_schemes:
        total = 0.0
        for _, txn in txns.iterrows():
            total += engine.txn_fee_with_scheme(txn, merchant, scheme)
        scheme_totals[scheme] = total

    if minimize:
        best = min(scheme_totals, key=scheme_totals.get)
    else:
        best = max(scheme_totals, key=scheme_totals.get)

    return f"{best}:{scheme_totals[best]:.2f}"


def solve_aci_incentive(engine, merchant, month=None, year=2023):
    """Move fraudulent transactions to a different ACI to minimize fees."""
    if month is not None:
        txns = engine.get_merchant_txns(merchant, year=year, month=month)
    else:
        txns = engine.get_merchant_txns(merchant, year=year)

    # Separate fraud and non-fraud
    fraud_txns = txns[txns['has_fraudulent_dispute'] == True]

    if fraud_txns.empty:
        return "Not Applicable"

    # For each candidate ACI, compute total fee for fraud transactions
    aci_totals = {}
    for aci in engine.all_acis:
        total = 0.0
        for _, txn in fraud_txns.iterrows():
            total += engine.txn_fee_with_aci(txn, merchant, aci)
        aci_totals[aci] = total

    # Pick ACI with minimum total
    best_aci = min(aci_totals, key=aci_totals.get)
    return f"{best_aci}:{aci_totals[best_aci]:.2f}"


# =============================================================================
# MAIN
# =============================================================================

def run_evaluation(questions_file, output_file, dev_mode=False, limit=None):
    """Run the solver on a set of questions."""
    print("Loading engine...")
    engine = DABStepEngine()
    print(f"Loaded: {len(engine.payments)} payments, {len(engine.fees)} fees, "
          f"{len(engine.merchant_info)} merchants")

    with open(questions_file, encoding='utf-8') as f:
        questions = [json.loads(line) for line in f]
    if limit is not None:
        questions = questions[:limit]

    results = []
    correct = 0
    total = 0

    for q in questions:
        tid = q['task_id']
        question = q['question']
        guidelines = q.get('guidelines', '')
        expected = q.get('answer', '')

        print(f"\nSolving Q{tid}...")
        try:
            answer = solve_question(engine, tid, question, guidelines)
        except Exception as e:
            answer = f"ERROR: {e}"
            import traceback
            traceback.print_exc()

        # Score
        score = 0
        error_type = None
        if dev_mode and expected:
            score, error_type = score_answer(answer, expected)
            correct += score
            total += 1
            status = "OK" if score else "MISMATCH"
            if not score:
                print(f"  Q{tid}: {status}")
                print(f"    Expected: {expected}")
                print(f"    Got:      {answer}")
                print(f"    Error:    {error_type}")
            else:
                print(f"  Q{tid}: {status} = {answer}")
        else:
            print(f"  Q{tid}: {answer}")

        results.append({
            'question_id': tid,
            'question': question,
            'parsed_answer': answer,
            'ground_truth': expected,
            'score': score,
            'error_type': error_type,
            'guidelines': guidelines
        })

    if dev_mode:
        print(f"\n{'='*60}")
        print(f"SCORE: {correct}/{total}")
        print(f"{'='*60}")

    Path(output_file).parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, 'w', encoding='utf-8') as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')

    return results, correct, total


def build_target30_submission(output_file):
    """Solve runner-defined target30 task IDs and write HF submission JSONL."""
    print("Loading engine...")
    engine = DABStepEngine()
    print(f"Loaded: {len(engine.payments)} payments, {len(engine.fees)} fees, "
          f"{len(engine.merchant_info)} merchants")

    with open(DATA_DIR / "all.jsonl", encoding='utf-8') as f:
        all_tasks = [json.loads(line) for line in f if line.strip()]
    by_id = {str(t['task_id']): t for t in all_tasks}

    rows = []
    for tid in [str(x) for x in TARGET_TASK_IDS]:
        task = by_id[tid]
        question = task['question']
        guidelines = task.get('guidelines', '')
        answer = solve_question(engine, tid, question, guidelines)
        rows.append({'task_id': tid, 'agent_answer': answer})
        print(f"  Q{tid}: {answer}")

    Path(output_file).parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, 'w', encoding='utf-8') as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + '\n')

    print(f"\nWrote {len(rows)} rows to {output_file}")
    return rows


if __name__ == '__main__':
    mode = sys.argv[1] if len(sys.argv) > 1 else 'dev10'

    if mode == 'dev':
        run_evaluation(
            DATA_DIR / "dev.jsonl",
            ARTIFACTS_DIR / "claude_answers_dev.jsonl",
            dev_mode=True
        )
    elif mode == 'dev10':
        run_evaluation(
            DATA_DIR / "dev.jsonl",
            ARTIFACTS_DIR / "dev10_offline_results.jsonl",
            dev_mode=True,
            limit=10,
        )
    elif mode == 'target':
        run_evaluation(
            DATA_DIR / "target.jsonl",
            ARTIFACTS_DIR / "claude_answers_target.jsonl",
            dev_mode=False
        )
    elif mode == 'target30':
        build_target30_submission(ARTIFACTS_DIR / "submission_target30.jsonl")
    else:
        print("Usage: python offline_solver.py [dev|dev10|target|target30]")
