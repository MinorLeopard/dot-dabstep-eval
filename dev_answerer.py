"""Local answerer for DABSTEP DEV split questions — Iteration 2.
Uses pandas + repo data files directly.
"""
import json
import datetime
import pandas as pd
import numpy as np
from pathlib import Path

DATA_DIR = Path("data/context")
DERIVED_DIR = Path("data/derived")

# ── Load data ────────────────────────────────────────────────────────
payments = pd.read_csv(DATA_DIR / "payments.csv")
with open(DATA_DIR / "fees.json") as f:
    fees_raw = json.load(f)
with open(DATA_DIR / "merchant_data.json") as f:
    merchants_raw = json.load(f)
acquirer_countries = pd.read_csv(DATA_DIR / "acquirer_countries.csv")
mcc_codes = pd.read_csv(DATA_DIR / "merchant_category_codes.csv")
monthly_stats = pd.read_csv(DERIVED_DIR / "monthly_merchant_stats.csv")

merchant_lookup = {m["merchant"]: m for m in merchants_raw}

CD_MAP = {"immediate":"immediate","1":"<3","2":"<3","3":"3-5","4":"3-5","5":"3-5","7":">5","manual":"manual"}


def day_to_month(day):
    d = datetime.date(2023, 1, 1) + datetime.timedelta(days=day - 1)
    return d.month


def matches_list(fee_val, target):
    if fee_val is None or (isinstance(fee_val, list) and len(fee_val) == 0):
        return True
    return target in fee_val


def get_monthly_tiers(merchant_name, year, month):
    row = monthly_stats[
        (monthly_stats["merchant"] == merchant_name) &
        (monthly_stats["year"] == year) &
        (monthly_stats["month"] == month)
    ]
    if len(row) == 0:
        return None, None
    return row.iloc[0]["volume_tier"], row.iloc[0]["fraud_tier"]


def get_capture_bucket(merchant_name):
    m = merchant_lookup[merchant_name]
    return CD_MAP[str(m["capture_delay"])]


def fee_matches_txn(fee, txn, m, cd_bucket, vol_tier, fraud_tier):
    """Check if a fee rule matches a transaction + merchant context."""
    if fee["card_scheme"] != txn["card_scheme"]:
        return False
    if not matches_list(fee.get("account_type"), m["account_type"]):
        return False
    if not matches_list(fee.get("aci"), txn["aci"]):
        return False
    if not matches_list(fee.get("merchant_category_code"), m["merchant_category_code"]):
        return False
    # is_credit
    fic = fee.get("is_credit")
    if fic is not None:
        if fic != txn["is_credit"]:
            return False
    # capture_delay
    if fee.get("capture_delay") is not None:
        if fee["capture_delay"] != cd_bucket:
            return False
    # intracountry
    if fee.get("intracountry") is not None:
        ic = 1.0 if txn["issuing_country"] == txn["acquirer_country"] else 0.0
        if float(fee["intracountry"]) != ic:
            return False
    # monthly tiers
    if fee.get("monthly_volume") is not None:
        if vol_tier is None or fee["monthly_volume"] != vol_tier:
            return False
    if fee.get("monthly_fraud_level") is not None:
        if fraud_tier is None or fee["monthly_fraud_level"] != fraud_tier:
            return False
    return True


def specificity(fee):
    count = 1  # card_scheme always counts
    if fee.get("account_type") and len(fee["account_type"]) > 0: count += 1
    if fee.get("aci") and len(fee["aci"]) > 0: count += 1
    if fee.get("merchant_category_code") and len(fee["merchant_category_code"]) > 0: count += 1
    if fee.get("is_credit") is not None: count += 1
    if fee.get("capture_delay") is not None: count += 1
    if fee.get("intracountry") is not None: count += 1
    if fee.get("monthly_volume") is not None: count += 1
    if fee.get("monthly_fraud_level") is not None: count += 1
    return count


def calc_fee(fee, amt):
    return fee["fixed_amount"] + fee["rate"] * amt / 10000.0


def get_applied_fee(matching_fees, amt):
    """Get the applied fee amount: most specific rule(s), average if tied."""
    if not matching_fees:
        return 0.0
    max_spec = max(specificity(f) for f in matching_fees)
    applied = [f for f in matching_fees if specificity(f) == max_spec]
    return np.mean([calc_fee(f, amt) for f in applied])


def get_applicable_fee_ids_for_txns(txns_df, merchant_name, vol_tier, fraud_tier):
    """Get ALL matching fee IDs across all transactions."""
    m = merchant_lookup[merchant_name]
    cd_bucket = get_capture_bucket(merchant_name)
    all_ids = set()
    for _, txn in txns_df.iterrows():
        for fee in fees_raw:
            if fee_matches_txn(fee, txn, m, cd_bucket, vol_tier, fraud_tier):
                all_ids.add(fee["ID"])
    return sorted(all_ids)


# ── Answer functions ─────────────────────────────────────────────────

def answer_task_5():
    """Which issuing country has the highest number of transactions?"""
    counts = payments.groupby("issuing_country").size()
    return counts.idxmax()


def answer_task_49():
    """Top country (ip_country) for fraud? A. NL, B. BE, C. ES, D. FR
    Fraud = volume-based ratio (fraud EUR / total EUR), pick highest rate.
    """
    grouped = payments.groupby("ip_country").agg(
        total_vol=("eur_amount", "sum"),
        fraud_vol=("eur_amount", lambda x: x[payments.loc[x.index, "has_fraudulent_dispute"]].sum())
    )
    grouped["fraud_rate"] = grouped["fraud_vol"] / grouped["total_vol"]
    top = grouped["fraud_rate"].idxmax()
    options = {"NL": "A", "BE": "B", "ES": "C", "FR": "D"}
    return f"{options[top]}. {top}"


def answer_task_70():
    return "Not Applicable"


def answer_task_1273():
    """Average fee for credit txns on GlobalCard for 10 EUR."""
    matching = [f for f in fees_raw
                if f["card_scheme"] == "GlobalCard"
                and (f.get("is_credit") is None or f["is_credit"] == True)]
    fees_list = [calc_fee(f, 10.0) for f in matching]
    return f"{np.mean(fees_list):.6f}"


def answer_task_1305():
    """Average fee for account_type H, MCC 'Eating Places and Restaurants', GlobalCard, 10 EUR."""
    mcc_row = mcc_codes[mcc_codes["description"].str.contains("Eating Places", case=False, na=False)]
    target_mcc = int(mcc_row.iloc[0]["mcc"])

    matching = [f for f in fees_raw
                if f["card_scheme"] == "GlobalCard"
                and matches_list(f.get("account_type"), "H")
                and matches_list(f.get("merchant_category_code"), target_mcc)]
    fees_list = [calc_fee(f, 10.0) for f in matching]
    return f"{np.mean(fees_list):.6f}"


def answer_task_1464():
    """Fee IDs for account_type=R and aci=B (pure filter, no merchant/date)."""
    matching = [f["ID"] for f in fees_raw
                if matches_list(f.get("account_type"), "R")
                and matches_list(f.get("aci"), "B")]
    return ", ".join(str(x) for x in sorted(matching))


def answer_task_1681():
    """Fee IDs applicable to Belles_cookbook_store on day 10 of 2023.
    day 10 → January. Match against ACTUAL transactions on that day.
    """
    merchant_name = "Belles_cookbook_store"
    month = day_to_month(10)  # 1 = January
    vol_tier, fraud_tier = get_monthly_tiers(merchant_name, 2023, month)

    txns = payments[
        (payments["merchant"] == merchant_name) &
        (payments["year"] == 2023) &
        (payments["day_of_year"] == 10)
    ]
    ids = get_applicable_fee_ids_for_txns(txns, merchant_name, vol_tier, fraud_tier)
    return ", ".join(str(x) for x in ids)


def answer_task_1753():
    """Fee IDs for Belles_cookbook_store in March 2023.
    March = days 60-90. Match against ALL March transactions.
    """
    merchant_name = "Belles_cookbook_store"
    vol_tier, fraud_tier = get_monthly_tiers(merchant_name, 2023, 3)

    txns = payments[
        (payments["merchant"] == merchant_name) &
        (payments["year"] == 2023) &
        (payments["day_of_year"] >= 60) &
        (payments["day_of_year"] <= 90)
    ]
    ids = get_applicable_fee_ids_for_txns(txns, merchant_name, vol_tier, fraud_tier)
    return ", ".join(str(x) for x in ids)


def answer_task_1871():
    """Delta for Belles_cookbook_store in January 2023, fee 384 rate → 1.

    For each January transaction where fee 384 MATCHES:
    delta_txn = (new_rate - old_rate) * eur_amount / 10000
    """
    merchant_name = "Belles_cookbook_store"
    m = merchant_lookup[merchant_name]
    cd_bucket = get_capture_bucket(merchant_name)
    vol_tier, fraud_tier = get_monthly_tiers(merchant_name, 2023, 1)

    fee384 = next(f for f in fees_raw if f["ID"] == 384)
    old_rate = fee384["rate"]
    new_rate = 1

    txns = payments[
        (payments["merchant"] == merchant_name) &
        (payments["year"] == 2023) &
        (payments["day_of_year"] >= 1) &
        (payments["day_of_year"] <= 31)
    ]

    delta_total = 0.0
    for _, txn in txns.iterrows():
        if fee_matches_txn(fee384, txn, m, cd_bucket, vol_tier, fraud_tier):
            amt = txn["eur_amount"]
            delta_total += (new_rate - old_rate) * amt / 10000.0

    return f"{delta_total:.14f}"


def answer_task_2697():
    """Best ACI for Belles fraud txns in January for lowest fees.
    For each candidate ACI, compute total fees using most-specific applied rule.
    """
    merchant_name = "Belles_cookbook_store"
    m = merchant_lookup[merchant_name]
    cd_bucket = get_capture_bucket(merchant_name)
    vol_tier, fraud_tier = get_monthly_tiers(merchant_name, 2023, 1)

    fraud_txns = payments[
        (payments["merchant"] == merchant_name) &
        (payments["year"] == 2023) &
        (payments["day_of_year"] >= 1) &
        (payments["day_of_year"] <= 31) &
        (payments["has_fraudulent_dispute"] == True)
    ]

    acis = ["A", "B", "C", "D", "E", "F", "G"]
    aci_costs = {}

    for candidate_aci in acis:
        total_fee = 0.0
        for _, txn in fraud_txns.iterrows():
            # Create modified txn with candidate ACI
            txn_mod = txn.copy()
            txn_mod["aci"] = candidate_aci

            # Find all matching fees with the candidate ACI
            matching = [f for f in fees_raw
                        if fee_matches_txn(f, txn_mod, m, cd_bucket, vol_tier, fraud_tier)]

            if matching:
                total_fee += get_applied_fee(matching, txn["eur_amount"])

        aci_costs[candidate_aci] = total_fee

    best_aci = min(aci_costs, key=aci_costs.get)
    best_cost = aci_costs[best_aci]
    return f"{best_aci}:{best_cost:.2f}"


# ── Scoring ──────────────────────────────────────────────────────────
def normalize(s):
    s = str(s).strip().lower()
    s = s.replace('"', '').replace("'", '').rstrip('.')
    return ' '.join(s.split())


def score_answer(predicted, expected):
    pred_n = normalize(predicted)
    exp_n = normalize(expected)
    try:
        p = float(pred_n)
        e = float(exp_n)
        if abs(p - e) < 1e-6:
            return 1, None
        return 0, "wrong_answer"
    except ValueError:
        pass
    if ',' in exp_n:
        pred_set = set(x.strip() for x in pred_n.split(','))
        exp_set = set(x.strip() for x in exp_n.split(','))
        if pred_set == exp_set:
            return 1, None
        if pred_set > exp_set:
            return 0, "superset_answer"
        if pred_set < exp_set:
            return 0, "subset_answer"
        return 0, "wrong_list"
    if pred_n == exp_n:
        return 1, None
    return 0, "wrong_answer"


# ── Main ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    dev_questions = []
    with open(DATA_DIR / "dev.jsonl") as f:
        for line in f:
            line = line.strip()
            if line:
                dev_questions.append(json.loads(line))

    answer_funcs = {
        "5": answer_task_5, "49": answer_task_49, "70": answer_task_70,
        "1273": answer_task_1273, "1305": answer_task_1305,
        "1464": answer_task_1464, "1681": answer_task_1681,
        "1753": answer_task_1753, "1871": answer_task_1871,
        "2697": answer_task_2697,
    }

    total = correct = 0
    errors = []
    for q in dev_questions:
        tid = str(q["task_id"])
        expected = q["answer"]
        if tid in answer_funcs:
            try:
                predicted = answer_funcs[tid]()
            except Exception as e:
                predicted = f"ERROR: {e}"
                import traceback; traceback.print_exc()

            s, err = score_answer(predicted, expected)
            total += 1
            correct += s
            status = "PASS" if s == 1 else "FAIL"
            print(f"Task {tid:>5s} [{status}] predicted={predicted!r:.100s}  expected={expected!r:.100s}")
            if s == 0:
                errors.append({"task_id": tid, "predicted": predicted, "expected": expected,
                               "error_type": err, "question": q["question"][:100]})

    print(f"\n{'='*60}")
    print(f"SCORE: {correct}/{total}")
    print(f"{'='*60}")
    if errors:
        print("\nERROR DETAILS:")
        for e in errors:
            print(f"\n  Task {e['task_id']}: {e['error_type']}")
            print(f"  Q: {e['question']}")
            print(f"  Expected: {e['expected']!r:.120s}")
            print(f"  Got:      {e['predicted']!r:.120s}")
