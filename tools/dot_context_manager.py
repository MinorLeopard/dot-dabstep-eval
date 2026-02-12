"""Dot Context Manager — utility for managing Dot test environment context.

Manages:
- Table descriptions (via /api/save_table_doc)
- Table column descriptions (via /api/save_table_doc)
- Relationships (via /api/relationships)
- External assets / org notes (via /api/import_and_overwrite_external_asset)

Usage:
    python tools/dot_context_manager.py --action list-tables
    python tools/dot_context_manager.py --action list-relationships
    python tools/dot_context_manager.py --action update-table-desc --table-id uploads.main.fees --desc-file data/desc_fees.md
    python tools/dot_context_manager.py --action upsert-relationship --from-table X --to-table Y --from-cols a --to-cols b
    python tools/dot_context_manager.py --action upsert-note --note-id org_instructions --note-file data/dot_fee_instructions.md
    python tools/dot_context_manager.py --dry-run ...
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

AUDIT_LOG_DIR = Path("tools/audit_logs")


class DotContextManager:
    """Manages Dot context (tables, relationships, external assets) via API."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        dry_run: bool = False,
        timeout: float = 30.0,
    ) -> None:
        try:
            from dotenv import load_dotenv
            load_dotenv()
        except ImportError:
            pass

        self.api_key = api_key or os.environ.get("DOT_API_KEY", "")
        self.base_url = (base_url or os.environ.get("DOT_BASE_URL", "")).rstrip("/")
        if not self.api_key or not self.base_url:
            raise ValueError("DOT_API_KEY and DOT_BASE_URL must be set")

        self.dry_run = dry_run
        self._client = httpx.Client(
            base_url=self.base_url,
            headers={
                "X-API-KEY": self.api_key,
                "API-KEY": self.api_key,
                "Content-Type": "application/json",
            },
            timeout=timeout,
        )

    def _audit_log(self, action: str, before: dict | list | None, after: dict | list | None) -> None:
        AUDIT_LOG_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        log_entry = {
            "timestamp": ts,
            "action": action,
            "dry_run": self.dry_run,
            "before": before,
            "after": after,
        }
        log_path = AUDIT_LOG_DIR / f"{ts}_{action}.json"
        with open(log_path, "w", encoding="utf-8") as f:
            json.dump(log_entry, f, indent=2, ensure_ascii=False)
        logger.info("Audit log written: %s", log_path)

    # ── Tables ──────────────────────────────────────────────────────

    def list_tables(self, lite: bool = True) -> list[dict]:
        r = self._client.get("/api/tables", params={"lite": str(lite).lower()})
        r.raise_for_status()
        return r.json()

    def get_table(self, table_id: str) -> dict:
        r = self._client.get(f"/api/tables/{table_id}")
        r.raise_for_status()
        return r.json()

    def update_table_description(self, table_id: str, description: str) -> dict:
        before = self.get_table(table_id)
        payload = {
            "table": {
                "id": table_id,
                "description": description,
            }
        }
        if self.dry_run:
            logger.info("[DRY RUN] Would update table %s description (%d chars)", table_id, len(description))
            self._audit_log(f"update_table_desc_{table_id}", {"description": before.get("description", "")[:200]}, {"description": description[:200]})
            return {"dry_run": True}

        r = self._client.post("/api/save_table_doc", json=payload)
        r.raise_for_status()
        self._audit_log(f"update_table_desc_{table_id}", {"description": before.get("description", "")[:200]}, {"description": description[:200]})
        return r.json()

    def update_column_description(self, table_id: str, column_name: str, user_comment: str) -> dict:
        table = self.get_table(table_id)
        columns = table.get("columns", [])
        col_before = None
        for c in columns:
            if c.get("column_name") == column_name:
                col_before = c.get("user_comment", "")
                c["user_comment"] = user_comment
                break
        else:
            raise ValueError(f"Column {column_name} not found in {table_id}")

        payload = {
            "table": {
                "id": table_id,
                "columns": columns,
            }
        }
        if self.dry_run:
            logger.info("[DRY RUN] Would update column %s.%s user_comment", table_id, column_name)
            self._audit_log(f"update_col_{table_id}_{column_name}", {"user_comment": col_before[:200] if col_before else ""}, {"user_comment": user_comment[:200]})
            return {"dry_run": True}

        r = self._client.post("/api/save_table_doc", json=payload)
        r.raise_for_status()
        self._audit_log(f"update_col_{table_id}_{column_name}", {"user_comment": col_before[:200] if col_before else ""}, {"user_comment": user_comment[:200]})
        return r.json()

    # ── Relationships ───────────────────────────────────────────────

    def list_relationships(self) -> list[dict]:
        r = self._client.get("/api/relationships")
        r.raise_for_status()
        return r.json()

    def upsert_relationship(
        self,
        from_table: str,
        to_table: str,
        from_columns: list[str],
        to_columns: list[str],
        rel_type: str = "foreign",
        active: bool = True,
    ) -> dict:
        existing = self.list_relationships()

        # Check for existing matching relationship
        existing_id = None
        for rel in existing:
            if (rel["doc_id"] == from_table and rel["table"] == to_table
                    and rel["own_columns"] == from_columns and rel["columns"] == to_columns):
                existing_id = rel.get("relationship_id")
                logger.info("Relationship already exists (id=%s), will update", existing_id)
                break

        new_rel = {
            "doc_id": from_table,
            "table": to_table,
            "own_columns": from_columns,
            "columns": to_columns,
            "type": rel_type,
            "active": active,
            "incoming": False,
        }
        if existing_id is not None:
            new_rel["relationship_id"] = existing_id

        if self.dry_run:
            logger.info("[DRY RUN] Would upsert relationship: %s -> %s", from_table, to_table)
            self._audit_log("upsert_relationship", {"existing_id": existing_id}, new_rel)
            return {"dry_run": True}

        r = self._client.post("/api/relationships", json=[new_rel])
        r.raise_for_status()
        self._audit_log("upsert_relationship", {"existing_id": existing_id}, new_rel)
        return r.json()

    def delete_relationship(self, relationship_id: int) -> dict:
        if self.dry_run:
            logger.info("[DRY RUN] Would delete relationship %d", relationship_id)
            return {"dry_run": True}
        r = self._client.post("/api/relationships/delete", json=[relationship_id])
        r.raise_for_status()
        return r.json()

    # ── External Assets (org notes) ─────────────────────────────────

    def list_external_assets(self) -> list[dict]:
        r = self._client.get("/api/external_assets")
        r.raise_for_status()
        return r.json()

    def upsert_note(self, note_id: str, title: str, body: str) -> dict:
        asset = {
            "id": note_id,
            "subtype": "note",
            "name": title,
            "description": title,
            "dot_description": body,
            "active": True,
        }
        if self.dry_run:
            logger.info("[DRY RUN] Would upsert note %s (%d chars)", note_id, len(body))
            self._audit_log(f"upsert_note_{note_id}", None, {"title": title, "body_len": len(body)})
            return {"dry_run": True}

        r = self._client.post("/api/import_and_overwrite_external_asset", json={"external_asset": asset})
        r.raise_for_status()
        self._audit_log(f"upsert_note_{note_id}", None, {"title": title, "body_len": len(body)})
        return r.json()

    def delete_note(self, note_id: str) -> dict:
        if self.dry_run:
            logger.info("[DRY RUN] Would delete note %s", note_id)
            return {"dry_run": True}
        r = self._client.post("/api/delete_external_asset", params={"asset_id": note_id})
        r.raise_for_status()
        return r.json()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    parser = argparse.ArgumentParser(description="Dot Context Manager")
    parser.add_argument("--dry-run", action="store_true", help="Print requests without executing")
    parser.add_argument("--action", required=True, choices=[
        "list-tables", "get-table", "update-table-desc", "update-column-desc",
        "list-relationships", "upsert-relationship", "delete-relationship",
        "list-notes", "upsert-note", "delete-note",
    ])
    parser.add_argument("--table-id", help="Table ID for table operations")
    parser.add_argument("--desc-file", help="File containing description text")
    parser.add_argument("--column-name", help="Column name for column description updates")
    parser.add_argument("--comment", help="User comment for column")
    parser.add_argument("--from-table", help="Source table for relationship")
    parser.add_argument("--to-table", help="Target table for relationship")
    parser.add_argument("--from-cols", nargs="+", help="Source columns for relationship")
    parser.add_argument("--to-cols", nargs="+", help="Target columns for relationship")
    parser.add_argument("--rel-id", type=int, help="Relationship ID for deletion")
    parser.add_argument("--note-id", help="Note ID")
    parser.add_argument("--note-title", help="Note title")
    parser.add_argument("--note-file", help="File containing note body")
    args = parser.parse_args()

    mgr = DotContextManager(dry_run=args.dry_run)

    if args.action == "list-tables":
        for t in mgr.list_tables():
            print(f"  {t['name']} (active={t.get('active')}, rows={t.get('num_rows')})")

    elif args.action == "get-table":
        t = mgr.get_table(args.table_id)
        print(json.dumps(t, indent=2, ensure_ascii=False)[:5000])

    elif args.action == "update-table-desc":
        desc = Path(args.desc_file).read_text(encoding="utf-8")
        result = mgr.update_table_description(args.table_id, desc)
        print(f"Result: {result}")

    elif args.action == "update-column-desc":
        result = mgr.update_column_description(args.table_id, args.column_name, args.comment)
        print(f"Result: {result}")

    elif args.action == "list-relationships":
        for r in mgr.list_relationships():
            print(f"  {r['doc_id']}.{r['own_columns']} -> {r['table']}.{r['columns']} (id={r.get('relationship_id')}, active={r.get('active')})")

    elif args.action == "upsert-relationship":
        result = mgr.upsert_relationship(args.from_table, args.to_table, args.from_cols, args.to_cols)
        print(f"Result: {result}")

    elif args.action == "delete-relationship":
        result = mgr.delete_relationship(args.rel_id)
        print(f"Result: {result}")

    elif args.action == "list-notes":
        for a in mgr.list_external_assets():
            print(f"  {a.get('id')}: {a.get('name')} (active={a.get('active')})")

    elif args.action == "upsert-note":
        body = Path(args.note_file).read_text(encoding="utf-8") if args.note_file else ""
        result = mgr.upsert_note(args.note_id, args.note_title or args.note_id, body)
        print(f"Result: {result}")

    elif args.action == "delete-note":
        result = mgr.delete_note(args.note_id)
        print(f"Result: {result}")


if __name__ == "__main__":
    main()
