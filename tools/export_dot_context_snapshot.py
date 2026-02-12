# tools/export_dot_context_snapshot.py
"""
Export Dot test-env context snapshot to Markdown.

Includes:
- Relationships
- Table descriptions + column user comments (non-empty)
- External assets / org notes (id, name, active, and dot_description preview)

Usage:
  python tools/export_dot_context_snapshot.py --out context_snapshot.md
  python tools/export_dot_context_snapshot.py --out context_snapshot.md --include-full-notes
  python tools/export_dot_context_snapshot.py --out context_snapshot.md --tables uploads.main.fees uploads.main.payments
"""

from __future__ import annotations

import argparse
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

# Import your existing manager
from tools.dot_context_manager import DotContextManager


def _md_escape(s: str) -> str:
    return s.replace("\r\n", "\n").replace("\r", "\n")


def _trim(s: str, max_chars: int) -> str:
    s = _md_escape(s or "").strip()
    if len(s) <= max_chars:
        return s
    return s[:max_chars].rstrip() + "\n…(truncated)…"


def _first_lines(s: str, n: int = 25) -> str:
    s = _md_escape(s or "").strip()
    lines = s.split("\n")
    return "\n".join(lines[:n]).rstrip()


def _safe_bool(v) -> str:
    return "true" if bool(v) else "false"


def _format_table_section(table: dict) -> str:
    table_id = table.get("id") or table.get("name") or "UNKNOWN_TABLE"
    name = table.get("name", table_id)
    rows = table.get("num_rows", "unknown")
    active = table.get("active", True)

    desc = table.get("description", "") or ""
    desc = desc.strip()

    # Columns (only ones with user_comment)
    cols = table.get("columns", []) or []
    commented = []
    for c in cols:
        cc = (c.get("user_comment") or "").strip()
        if cc:
            commented.append((c.get("column_name", ""), cc))

    out = []
    out.append(f"## Table: `{table_id}`")
    out.append(f"- Name: **{name}**")
    out.append(f"- Active: **{_safe_bool(active)}**")
    out.append(f"- Rows: **{rows}**")

    out.append("\n### Description")
    if desc:
        out.append(_trim(desc, 5000))
    else:
        out.append("_<empty>_")

    out.append("\n### Column comments (non-empty)")
    if commented:
        for col_name, comment in commented:
            out.append(f"- `{col_name}`: {_trim(comment, 800)}")
    else:
        out.append("_<none>_")

    out.append("")  # spacing
    return "\n".join(out)


def _format_relationships(rels: list[dict]) -> str:
    out = []
    out.append("# Relationships\n")
    if not rels:
        out.append("_<none>_")
        return "\n".join(out)

    # Sort for stability
    def key(r):
        return (
            str(r.get("doc_id", "")),
            str(r.get("table", "")),
            ",".join(r.get("own_columns", []) or []),
            ",".join(r.get("columns", []) or []),
        )

    for r in sorted(rels, key=key):
        rid = r.get("relationship_id")
        active = r.get("active", True)
        rel_type = r.get("type", "")
        from_tbl = r.get("doc_id", "")
        to_tbl = r.get("table", "")
        from_cols = r.get("own_columns", [])
        to_cols = r.get("columns", [])
        out.append(
            f"- **id={rid}** active={_safe_bool(active)} type={rel_type} :: "
            f"`{from_tbl}`({', '.join(from_cols)}) → `{to_tbl}`({', '.join(to_cols)})"
        )
    out.append("")
    return "\n".join(out)


def _format_assets(assets: list[dict], include_full_notes: bool) -> str:
    out = []
    out.append("# External assets / Org notes\n")
    if not assets:
        out.append("_<none>_")
        return "\n".join(out)

    # Sort for stability
    assets_sorted = sorted(assets, key=lambda a: str(a.get("id", "")))

    for a in assets_sorted:
        aid = a.get("id", "")
        name = a.get("name", "") or a.get("description", "")
        subtype = a.get("subtype", "")
        active = a.get("active", True)

        body = a.get("dot_description", "") or ""
        body_len = len(body)

        out.append(f"## Asset: `{aid}`")
        out.append(f"- Name: **{name}**")
        out.append(f"- Subtype: `{subtype}`")
        out.append(f"- Active: **{_safe_bool(active)}**")
        out.append(f"- Body length: **{body_len} chars**")

        if body.strip():
            out.append("\n### Body")
            if include_full_notes:
                out.append("```markdown")
                out.append(_trim(body, 200000))  # hard safety cap
                out.append("```")
            else:
                out.append("```markdown")
                out.append(_first_lines(body, n=30))
                out.append("…(preview truncated)…")
                out.append("```")
        else:
            out.append("\n### Body\n_<empty>_")

        out.append("")  # spacing
    return "\n".join(out)


def _pick_table_ids(all_tables: list[dict], requested: Iterable[str] | None) -> list[str]:
    ids = [t.get("id") for t in all_tables if t.get("id")]
    if not requested:
        return ids

    requested_set = set(requested)
    # Allow selecting by either exact id or by name match
    picked = []
    for t in all_tables:
        tid = t.get("id")
        tname = t.get("name", "")
        if tid in requested_set or tname in requested_set:
            if tid:
                picked.append(tid)
    # Fall back: if user passed IDs that weren’t in list_tables(lite=True),
    # keep them anyway.
    for x in requested:
        if x not in picked and x in requested_set:
            picked.append(x)
    return picked


def main() -> None:
    parser = argparse.ArgumentParser(description="Export Dot context snapshot to Markdown")
    parser.add_argument("--out", default="context_snapshot.md", help="Output markdown file")
    parser.add_argument(
        "--include-full-notes",
        action="store_true",
        help="Include full org note bodies (can be large). Default is preview.",
    )
    parser.add_argument(
        "--tables",
        nargs="*",
        help="Optional list of table IDs or names to include (default: all tables).",
    )
    args = parser.parse_args()

    mgr = DotContextManager()

    # Fetch everything
    tables_lite = mgr.list_tables(lite=True)
    table_ids = _pick_table_ids(tables_lite, args.tables)

    rels = mgr.list_relationships()
    assets = mgr.list_external_assets()

    # Build markdown
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    base_url = os.environ.get("DOT_BASE_URL", "").rstrip("/")

    md_parts = []
    md_parts.append(f"# Dot Context Snapshot\n\n- Exported: **{now}**\n- Base URL: **{base_url}**\n")

    md_parts.append(_format_relationships(rels))
    md_parts.append(_format_assets(assets, include_full_notes=args.include_full_notes))

    md_parts.append("# Tables\n")
    for tid in table_ids:
        try:
            t = mgr.get_table(tid)
        except Exception as e:
            md_parts.append(f"## Table: `{tid}`\n\n**ERROR fetching table:** `{e}`\n")
            continue
        md_parts.append(_format_table_section(t))

    out_path = Path(args.out)
    out_path.write_text("\n".join(md_parts).strip() + "\n", encoding="utf-8")
    print(f"Wrote snapshot: {out_path.resolve()}")


if __name__ == "__main__":
    main()
