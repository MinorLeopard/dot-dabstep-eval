#!/usr/bin/env python3
"""
Convert DABStep context JSON/MD files into CSV tables that Dot can ingest as Data Sources.

Inputs (default relative paths):
  data/context/fees.json
  data/context/merchant_data.json
  data/context/manual.md
  data/context/payments-readme.md

Outputs:
  data/derived/fees.csv
  data/derived/merchant_data.csv
  data/derived/docs_rules.csv   (optional, for context as table)

This script is defensive:
- It flattens nested JSON using pandas.json_normalize()
- It tries to map to the schema Dot suggested, but will keep extra columns too
- It generates rule_id if missing
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Tuple

import pandas as pd


# -------------------------
# Helpers
# -------------------------

def _read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _ensure_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def _to_bool_or_blank(x: Any) -> Any:
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return ""
    if isinstance(x, bool):
        return int(x)
    s = str(x).strip().lower()
    if s in {"true", "t", "yes", "y", "1"}:
        return 1
    if s in {"false", "f", "no", "n", "0"}:
        return 0
    return ""


def _coerce_numeric_or_blank(x: Any) -> Any:
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return ""
    try:
        return float(str(x).strip())
    except Exception:
        return ""


def _first_existing(d: Dict[str, Any], keys: List[str]) -> Any:
    for k in keys:
        if k in d and d[k] not in (None, "", []):
            return d[k]
    return None


# -------------------------
# fees.json -> fees.csv
# -------------------------

FEES_COLUMNS = [
    "rule_id",
    "card_scheme",
    "is_credit",
    "aci",
    "account_type",
    "mcc",
    "monthly_volume_tier",
    "monthly_fraud_tier",
    "capture_delay",
    "intracountry",
    "fixed_amount",
    "rate",
]


def _extract_fee_rows(raw: Any) -> List[Dict[str, Any]]:
    """
    fees.json structure may vary. We handle:
    - list of fee rules
    - dict with key like "fees" / "rules" containing list
    - dict of id->rule
    """
    if isinstance(raw, list):
        return raw  # list of dicts
    if isinstance(raw, dict):
        # common wrappers
        for k in ("fees", "rules", "fee_rules", "data", "items"):
            if k in raw and isinstance(raw[k], list):
                return raw[k]
        # id -> rule dict
        if all(isinstance(v, dict) for v in raw.values()):
            out = []
            for rid, rule in raw.items():
                rule = dict(rule)
                rule.setdefault("rule_id", rid)
                out.append(rule)
            return out
    raise ValueError("Unsupported fees.json structure (expected list or dict of rules).")


def build_fees_df(fees_json: Any) -> pd.DataFrame:
    rows = _extract_fee_rows(fees_json)

    # flatten everything first
    df = pd.json_normalize(rows, sep="__")

    # Try to map from likely keys to canonical keys (best-effort).
    # We keep extra columns too, but ensure canonical columns exist for Dot.
    mapped: List[Dict[str, Any]] = []
    for i, r in enumerate(rows, 1):
        if not isinstance(r, dict):
            r = {"value": r}
        rule_id = _first_existing(r, ["rule_id", "id", "fee_id", "rule", "name"]) or i

        card_scheme = _first_existing(r, ["card_scheme", "scheme", "network", "cardNetwork", "brand"])
        is_credit = _first_existing(r, ["is_credit", "credit", "isCredit", "card_type", "cardType"])
        aci = _first_existing(r, ["aci", "auth_characteristic_indicator", "authIndicator"])
        account_type = _first_existing(r, ["account_type", "accountType"])
        mcc = _first_existing(r, ["mcc", "merchant_category_code", "merchantCategoryCode", "merchant_category"])
        monthly_volume_tier = _first_existing(r, ["monthly_volume_tier", "volume_tier", "monthlyVolumeTier"])
        monthly_fraud_tier = _first_existing(r, ["monthly_fraud_tier", "fraud_tier", "monthlyFraudTier"])
        capture_delay = _first_existing(r, ["capture_delay", "captureDelay", "capture", "delay"])
        intracountry = _first_existing(r, ["intracountry", "domestic", "is_domestic", "isDomestic"])

        fixed_amount = _first_existing(r, ["fixed_amount", "fixed", "fixedFee", "fixed_fee", "fixedAmount", "amount"])
        rate = _first_existing(r, ["rate", "bps", "basis_points", "basisPoints", "percent", "variable", "variableRate"])

        # Coerce types gently
        mapped.append({
            "rule_id": rule_id,
            "card_scheme": card_scheme or "",
            "is_credit": _to_bool_or_blank(is_credit),
            "aci": aci or "",
            "account_type": account_type or "",
            "mcc": int(mcc) if str(mcc).isdigit() else ("" if mcc in (None, "") else str(mcc)),
            "monthly_volume_tier": monthly_volume_tier or "",
            "monthly_fraud_tier": monthly_fraud_tier or "",
            "capture_delay": capture_delay or "",
            "intracountry": _to_bool_or_blank(intracountry),
            "fixed_amount": _coerce_numeric_or_blank(fixed_amount),
            "rate": _coerce_numeric_or_blank(rate),
        })

    fees_out = pd.DataFrame(mapped)

    # Ensure rule_id stable + unique
    if fees_out["rule_id"].duplicated().any():
        fees_out["rule_id"] = range(1, len(fees_out) + 1)

    # Put canonical columns first, then keep any extra flattened columns (optional).
    extras = [c for c in df.columns if c not in FEES_COLUMNS]
    merged = fees_out.copy()
    for c in extras:
        merged[c] = df[c].astype(str).fillna("")
    return merged


# -------------------------
# merchant_data.json -> merchant_data.csv
# -------------------------

MERCHANT_COLUMNS = [
    "merchant",
    "account_type",
    "merchant_category_code",
    "capture_delay",
    "primary_acquirer",
    "alternate_acquirer",
]


def _extract_merchant_rows(raw: Any) -> List[Dict[str, Any]]:
    """
    merchant_data.json may be:
    - list of merchants
    - dict with wrapper key
    - dict of merchant_name -> attributes
    """
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict):
        for k in ("merchants", "merchant_data", "data", "items"):
            if k in raw and isinstance(raw[k], list):
                return raw[k]
        # merchant_name -> attributes
        if all(isinstance(v, dict) for v in raw.values()):
            out = []
            for m, attrs in raw.items():
                row = dict(attrs)
                row.setdefault("merchant", m)
                out.append(row)
            return out
    raise ValueError("Unsupported merchant_data.json structure.")


def build_merchants_df(merchant_json: Any) -> pd.DataFrame:
    rows = _extract_merchant_rows(merchant_json)

    df = pd.json_normalize(rows, sep="__")

    mapped: List[Dict[str, Any]] = []
    for r in rows:
        if not isinstance(r, dict):
            r = {"value": r}

        merchant = _first_existing(r, ["merchant", "merchant_name", "name", "merchantId", "id"])
        account_type = _first_existing(r, ["account_type", "accountType"])
        mcc = _first_existing(r, ["merchant_category_code", "mcc", "merchantCategoryCode", "merchant_category"])
        capture_delay = _first_existing(r, ["capture_delay", "captureDelay", "capture", "delay"])
        primary_acquirer = _first_existing(r, ["primary_acquirer", "primaryAcquirer", "acquirer"])
        alternate_acquirer = _first_existing(r, ["alternate_acquirer", "alternateAcquirer", "backup_acquirer"])

        mapped.append({
            "merchant": merchant or "",
            "account_type": account_type or "",
            "merchant_category_code": int(mcc) if str(mcc).isdigit() else ("" if mcc in (None, "") else str(mcc)),
            "capture_delay": capture_delay or "",
            "primary_acquirer": primary_acquirer or "",
            "alternate_acquirer": alternate_acquirer or "",
        })

    out = pd.DataFrame(mapped)

    # Keep extra cols (optional)
    extras = [c for c in df.columns if c not in MERCHANT_COLUMNS]
    for c in extras:
        out[c] = df[c].astype(str).fillna("")
    return out


# -------------------------
# manual/readme -> docs_rules.csv
# -------------------------

def chunk_markdown(md_text: str, doc_name: str, chunk_chars: int = 1200) -> pd.DataFrame:
    # naive section split by markdown headers
    parts = re.split(r"(?m)^#{1,6}\s+", md_text)
    # keep the header titles too by re-finding them
    headers = re.findall(r"(?m)^#{1,6}\s+(.+)$", md_text)
    rows: List[Dict[str, Any]] = []

    if not headers:
        headers = ["(no headers)"]
        parts = [md_text]

    for idx, body in enumerate(parts):
        title = headers[idx - 1] if idx > 0 and (idx - 1) < len(headers) else headers[0]
        body = body.strip()
        if not body:
            continue

        # chunk within section
        for ci, start in enumerate(range(0, len(body), chunk_chars)):
            chunk = body[start:start + chunk_chars].strip()
            if not chunk:
                continue
            rows.append({
                "doc_name": doc_name,
                "section": title.strip(),
                "chunk_index": ci,
                "text": chunk,
            })
    return pd.DataFrame(rows)


# -------------------------
# Main
# -------------------------

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--context-dir", type=str, default="data/context", help="Folder containing original context files")
    ap.add_argument("--out-dir", type=str, default="data/derived", help="Output folder for derived CSVs")
    ap.add_argument("--skip-docs", action="store_true", help="Skip docs_rules.csv creation")
    args = ap.parse_args()

    context_dir = Path(args.context_dir)
    out_dir = Path(args.out_dir)
    _ensure_dir(out_dir / "placeholder.txt")

    fees_path = context_dir / "fees.json"
    merch_path = context_dir / "merchant_data.json"
    manual_path = context_dir / "manual.md"
    readme_path = context_dir / "payments-readme.md"

    print(f"[INFO] context_dir={context_dir.resolve()}")
    print(f"[INFO] out_dir={out_dir.resolve()}")

    # fees
    fees_json = _read_json(fees_path)
    fees_df = build_fees_df(fees_json)
    fees_out = out_dir / "fees.csv"
    fees_df.to_csv(fees_out, index=False)
    print(f"[OK] wrote {fees_out} rows={len(fees_df)} cols={len(fees_df.columns)}")
    print(fees_df.head(3).to_string(index=False))

    # merchants
    merch_json = _read_json(merch_path)
    merch_df = build_merchants_df(merch_json)
    merch_out = out_dir / "merchant_data.csv"
    merch_df.to_csv(merch_out, index=False)
    print(f"[OK] wrote {merch_out} rows={len(merch_df)} cols={len(merch_df.columns)}")
    print(merch_df.head(3).to_string(index=False))

    # docs
    if not args.skip_docs:
        docs_frames = []
        if manual_path.exists():
            docs_frames.append(chunk_markdown(manual_path.read_text(encoding="utf-8"), "manual.md"))
        if readme_path.exists():
            docs_frames.append(chunk_markdown(readme_path.read_text(encoding="utf-8"), "payments-readme.md"))
        if docs_frames:
            docs_df = pd.concat(docs_frames, ignore_index=True)
            docs_out = out_dir / "docs_rules.csv"
            docs_df.to_csv(docs_out, index=False)
            print(f"[OK] wrote {docs_out} rows={len(docs_df)} cols={len(docs_df.columns)}")
            print(docs_df.head(3).to_string(index=False))
        else:
            print("[WARN] no docs files found; skipped docs_rules.csv")

    print("\nNEXT:")
    print("1) Upload data/derived/fees.csv and data/derived/merchant_data.csv into Dot as Data Sources.")
    print("2) Confirm Dot exposes uploads.main.fees and uploads.main.merchant_data.")
    print("3) Add custom instructions (fee matching SQL) in Dot org instructions.")
    print("4) Re-run agentic on first 5 target tasks.")


if __name__ == "__main__":
    main()
