from __future__ import annotations

import json
import math
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import pandas as pd


# ----------------------------
# Helpers
# ----------------------------

# Non-leap year month boundaries by day_of_year (1-indexed)
# Jan 1-31, Feb 32-59, Mar 60-90, Apr 91-120, May 121-151, Jun 152-181,
# Jul 182-212, Aug 213-243, Sep 244-273, Oct 274-304, Nov 305-334, Dec 335-365
_MONTH_ENDS = [31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334, 365]

def day_of_year_to_month(doy: int) -> int:
    for i, end in enumerate(_MONTH_ENDS, start=1):
        if doy <= end:
            return i
    return 12

def as_list(x: Any) -> list:
    if x is None:
        return []
    if isinstance(x, list):
        return x
    if isinstance(x, str):
        s = x.strip()
        if not s:
            return []
        # sometimes stored as "['A','B']" in strings
        try:
            val = json.loads(s)
            if isinstance(val, list):
                return val
        except Exception:
            pass
        return [s]
    return [x]

def explode_or_star(vals: list, star: str="*") -> list:
    # Empty list means "applies to all" -> represent as ["*"]
    return vals if vals else [star]


# ----------------------------
# Builders
# ----------------------------

def build_payments_enriched(data_dir: Path) -> pd.DataFrame:
    payments_path = data_dir / "payments.csv"
    merchant_path = data_dir / "merchant_data.json"

    payments = pd.read_csv(payments_path)
    with open(merchant_path, "r", encoding="utf-8") as f:
        merchant_data = json.load(f)

    md = pd.DataFrame(merchant_data)

    # ensure expected columns exist
    for col in ["merchant", "account_type", "merchant_category_code", "capture_delay_bucket"]:
        if col not in md.columns:
            raise ValueError(f"merchant_data.json missing column: {col}")

    # join
    out = payments.merge(
        md[["merchant", "account_type", "merchant_category_code", "capture_delay_bucket"]],
        on="merchant",
        how="left",
        validate="many_to_one",
    )

    # month
    out["month"] = out["day_of_year"].apply(lambda x: day_of_year_to_month(int(x)) if pd.notna(x) else None)

    # intracountry
    out["intracountry"] = (out["issuing_country"].astype(str) == out["acquirer_country"].astype(str)).astype(int)

    # convenience flags
    out["is_fraud"] = out["has_fraudulent_dispute"].astype(bool)

    return out


def build_fees_normalized(data_dir: Path, explode: bool = True) -> pd.DataFrame:
    fees_path = data_dir / "fees.json"
    with open(fees_path, "r", encoding="utf-8") as f:
        fees = json.load(f)

    df = pd.DataFrame(fees)

    # Normalize list-ish columns
    list_cols = ["account_type", "merchant_category_code", "aci"]
    for c in list_cols:
        if c not in df.columns:
            df[c] = None
        df[c] = df[c].apply(as_list)

    # Convert nullables to python None where needed
    for c in ["capture_delay", "monthly_fraud_level", "monthly_volume", "is_credit", "intracountry"]:
        if c not in df.columns:
            df[c] = None

    if not explode:
        # Keep lists as JSON strings (still useful for app-side matching)
        out = df.copy()
        for c in list_cols:
            out[c] = out[c].apply(lambda v: json.dumps(v))
        out["specificity_score"] = out.apply(_specificity_score_row, axis=1)
        return out

    # Explode into “* or value” columns for SQL-friendly matching
    rows = []
    for _, r in df.iterrows():
        acct_vals = explode_or_star(r["account_type"])
        mcc_vals  = explode_or_star(r["merchant_category_code"])
        aci_vals  = explode_or_star(r["aci"])

        cap_delay = r.get("capture_delay", None)
        fraud_tier = r.get("monthly_fraud_level", None)
        vol_tier = r.get("monthly_volume", None)
        is_credit = r.get("is_credit", None)
        intracountry = r.get("intracountry", None)

        for acct in acct_vals:
            for mcc in mcc_vals:
                for aci in aci_vals:
                    row = {
                        "id": r.get("ID"),
                        "card_scheme": r.get("card_scheme"),
                        "account_type": acct,
                        "merchant_category_code": mcc,
                        "aci": aci,
                        "capture_delay": cap_delay if cap_delay is not None else "*",
                        "monthly_fraud_level": fraud_tier if fraud_tier is not None else "*",
                        "monthly_volume": vol_tier if vol_tier is not None else "*",
                        "is_credit": is_credit if is_credit is not None else "*",
                        "intracountry": intracountry if intracountry is not None else "*",
                        "fixed_amount": r.get("fixed_amount", 0.0),
                        "rate": r.get("rate", 0.0),
                    }
                    row["specificity_score"] = _specificity_score_flat(row)
                    rows.append(row)

    return pd.DataFrame(rows)


def _specificity_score_row(r: pd.Series) -> int:
    # higher = more specific
    score = 0
    # list criteria
    score += 1 if r["account_type"] else 0
    score += 1 if r["merchant_category_code"] else 0
    score += 1 if r["aci"] else 0
    # scalar criteria
    for c in ["capture_delay", "monthly_fraud_level", "monthly_volume", "is_credit", "intracountry"]:
        score += 1 if pd.notna(r.get(c)) and r.get(c) is not None else 0
    return score

def _specificity_score_flat(row: dict) -> int:
    score = 0
    score += 1 if row["account_type"] != "*" else 0
    score += 1 if row["merchant_category_code"] != "*" else 0
    score += 1 if row["aci"] != "*" else 0
    score += 1 if row["capture_delay"] != "*" else 0
    score += 1 if row["monthly_fraud_level"] != "*" else 0
    score += 1 if row["monthly_volume"] != "*" else 0
    score += 1 if row["is_credit"] != "*" else 0
    score += 1 if row["intracountry"] != "*" else 0
    return score


def write_sqlite(db_path: Path, payments_enriched: pd.DataFrame, fees_normalized: pd.DataFrame) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()

    con = sqlite3.connect(str(db_path))
    try:
        payments_enriched.to_sql("payments_enriched", con, index=False)
        fees_normalized.to_sql("fees_normalized", con, index=False)

        cur = con.cursor()
        # indexes for typical matching
        cur.execute("CREATE INDEX idx_pe_merchant_month ON payments_enriched(merchant, year, month)")
        cur.execute("CREATE INDEX idx_pe_match ON payments_enriched(card_scheme, aci, is_credit, intracountry)")
        cur.execute("CREATE INDEX idx_fn_match ON fees_normalized(card_scheme, aci, is_credit, intracountry)")
        cur.execute("CREATE INDEX idx_fn_filters ON fees_normalized(account_type, merchant_category_code, capture_delay, monthly_volume, monthly_fraud_level)")
        con.commit()
    finally:
        con.close()


def main() -> None:
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", type=Path, default=Path("data"), help="repo data folder")
    ap.add_argument("--out-dir", type=Path, default=Path("data_sources"), help="output folder")
    ap.add_argument("--no-explode-fees", action="store_true", help="do not explode list fields in fees")
    ap.add_argument("--sqlite", action="store_true", help="also write dabstep.sqlite with indexes")
    args = ap.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)

    pe = build_payments_enriched(args.data_dir)
    pe_path = args.out_dir / "payments_enriched.csv"
    pe.to_csv(pe_path, index=False)
    print(f"Wrote {pe_path} ({len(pe):,} rows)")

    fn = build_fees_normalized(args.data_dir, explode=not args.no_explode_fees)
    fn_path = args.out_dir / "fees_normalized.csv"
    fn.to_csv(fn_path, index=False)
    print(f"Wrote {fn_path} ({len(fn):,} rows)")

    if args.sqlite:
        db_path = args.out_dir / "dabstep.sqlite"
        write_sqlite(db_path, pe, fn)
        print(f"Wrote {db_path}")

if __name__ == "__main__":
    main()
