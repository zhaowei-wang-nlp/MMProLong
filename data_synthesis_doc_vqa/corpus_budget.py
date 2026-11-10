"""Transactional token budget and disk reserve for resumable local production."""

import hashlib
import json
import re
import shutil
import sqlite3
import time
from pathlib import Path


class DiskReserveReached(RuntimeError):
    pass


def check_disk(path, policy, estimated_write_bytes=0):
    free = shutil.disk_usage(path).free
    reserve = int(policy["min_free_gib"] * 1024**3)
    headroom = int(policy.get("write_headroom_mib", 256) * 1024**2)
    if free - estimated_write_bytes < reserve + headroom:
        raise DiskReserveReached(f"Free space {free / 1024**3:.2f} GiB; reserve {reserve / 1024**3:.2f} GiB")
    return free


class TokenLedger:
    def __init__(self, root, policy):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.policy = policy
        self.db = sqlite3.connect(self.root / "corpus.sqlite")
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("""CREATE TABLE IF NOT EXISTS samples (
            id TEXT PRIMARY KEY, fingerprint TEXT UNIQUE NOT NULL, document_id TEXT NOT NULL,
            kind TEXT NOT NULL, tokens INTEGER NOT NULL, source_sha TEXT NOT NULL,
            record_json TEXT NOT NULL, admitted_at REAL NOT NULL,
            included INTEGER NOT NULL DEFAULT 1)""")
        self.db.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        saved = self.db.execute("SELECT value FROM settings WHERE key='target_tokens'").fetchone()
        if saved and int(saved[0]) != policy["target_tokens"]:
            raise ValueError("Existing ledger has a different token target")
        self.db.execute("INSERT OR IGNORE INTO settings VALUES ('target_tokens', ?)", (str(policy["target_tokens"]),))
        self.db.commit()

    def totals(self):
        rows = self.db.execute(
            "SELECT kind, COUNT(*), SUM(tokens) FROM samples WHERE included=1 GROUP BY kind"
        ).fetchall()
        return {k: {"samples": n, "tokens": tokens} for k, n, tokens in rows}

    def status(self):
        totals = self.totals()
        tokens = sum(v["tokens"] for v in totals.values())
        return {
            "target_tokens": self.policy["target_tokens"],
            "accepted_tokens": tokens,
            "accepted_samples": sum(v["samples"] for v in totals.values()),
            "by_kind": totals,
            "remaining_tokens": max(0, self.policy["target_tokens"] - tokens),
            "target_reached": self.policy["target_tokens"] - tokens <= self.policy["stop_tolerance_tokens"],
        }

    def next_kind(self, projected=None):
        totals = projected if projected is not None else {k: v["tokens"] for k, v in self.totals().items()}
        return min(self.policy["token_fractions"], key=lambda k: totals.get(k, 0) / self.policy["token_fractions"][k])

    def admit(self, row, document, tokens):
        try:
            from .public_vqa_pipeline import review_passes, validate
        except ImportError:
            from public_vqa_pipeline import review_passes, validate

        if validate(row, row["slot"], document) or not review_passes(
            row.get("verification", {}), row["slot"], document["page_count"]
        ):
            return "quality_rejected"
        if row.get("verification_context_pages") != list(range(document["page_count"])):
            return "context_mismatch"
        if row.get("generation_method") in {"released_prompt_window_v1", "document_tool_agent_v1"}:
            if row.get("verification_policy") != "two_independent_full_pdf_checks" or not review_passes(
                row.get("verification_secondary", {}), row["slot"], document["page_count"]
            ):
                return "secondary_review_missing"
            if row["slot"]["kind"] in {"single", "multi_local", "multi_distributed"}:
                if any(
                    review.get(field) is not False
                    for review in [row["verification"], row["verification_secondary"]]
                    for field in ["requires_arithmetic", "requires_numeric_comparison", "requires_counting"]
                ):
                    return "extraction_requires_reasoning"
            if row.get("generation_method") == "document_tool_agent_v1" and row["slot"]["kind"] == "unanswerable":
                if row.get("generation_text_pages") != list(range(document["page_count"])):
                    return "incomplete_agent_text_context"
        if row["slot"].get("require_document_novelty"):
            novelty = row.get("document_novelty_review", {})
            if (
                novelty.get("distinct") is not True
                or row["id"] not in novelty.get("compared_ids", [])
                or novelty.get("question_sha256") != hashlib.sha256(row["question"].encode()).hexdigest()
            ):
                return "novelty_review_missing"
        if document.get("exclude_from_public_release") or row.get("exclude_from_public_release"):
            return "rights_hold"
        if document.get("license") != "CC-BY-4.0" or document.get("explicit_rights_notice_pages"):
            return "rights_hold"
        if row.get("context_sha256") != document["sha256"]:
            return "context_mismatch"
        if not self.policy["min_sample_tokens"] <= tokens <= self.policy["max_sample_tokens"]:
            return "length_outside_range"
        kind = row["slot"]["kind"]
        if kind not in self.policy["token_fractions"]:
            return "unsupported_kind"
        normalized = re.sub(r"\W+", "", row["question"].casefold())
        fingerprint = hashlib.sha256((document["sha256"] + normalized).encode()).hexdigest()
        self.db.execute("BEGIN IMMEDIATE")
        try:
            current = self.db.execute("SELECT COALESCE(SUM(tokens),0) FROM samples WHERE included=1").fetchone()[0]
            if self.policy["target_tokens"] - current <= self.policy["stop_tolerance_tokens"]:
                self.db.rollback()
                return "target_reached"
            if current + tokens > self.policy["target_tokens"]:
                self.db.rollback()
                return "would_exceed_budget"
            row = {**row, "token_count": tokens, "token_metric": self.policy["token_metric"]}
            self.db.execute(
                "INSERT INTO samples (id,fingerprint,document_id,kind,tokens,source_sha,record_json,admitted_at) VALUES (?,?,?,?,?,?,?,?)",
                (
                    row["id"],
                    fingerprint,
                    row["document_id"],
                    kind,
                    tokens,
                    document["sha256"],
                    json.dumps(row, ensure_ascii=False),
                    time.time(),
                ),
            )
            self.db.commit()
            return "admitted"
        except sqlite3.IntegrityError:
            self.db.rollback()
            return "duplicate"
        except BaseException:
            self.db.rollback()
            raise

    def export_jsonl(self, path):
        path = Path(path)
        temp = path.with_suffix(path.suffix + ".tmp")
        with temp.open("w") as f:
            for (row,) in self.db.execute("SELECT record_json FROM samples WHERE included=1 ORDER BY admitted_at,id"):
                f.write(row + "\n")
        temp.replace(path)

    def close(self):
        self.db.close()

    def hold_documents(self, ids):
        for document_id in ids:
            self.db.execute("UPDATE samples SET included=0 WHERE document_id=?", (document_id,))
        self.db.commit()
