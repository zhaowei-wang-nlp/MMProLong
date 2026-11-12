"""Resumable local production in small batches, with a token cap and disk reserve.

Each document's PNG pages are stored once. Canonical parquet uses relative image
paths; training_local parquet resolves those paths for the current machine.
"""

import argparse
import fcntl
import hashlib
import json
import math
import os
import random
import re
import shutil
import time
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

import requests
from api_parse_utils import image_special_token, item_template, system_template, user_template
from bs4 import BeautifulSoup
from corpus_budget import DiskReserveReached, TokenLedger, check_disk
from corpus_progress import write_progress
from public_vqa_pipeline import Runner, prepare, write_json


QUERIES = [
    ("Physics", "review cosmology"),
    ("Biology", "review biology"),
    ("Medicine", "review medical"),
    ("Earth Science", "review climate"),
    ("Economics", "survey economics"),
    ("Social Science", "survey social science"),
    ("Mathematics", "survey mathematics"),
    ("Engineering", "survey engineering"),
    ("Computer Science", "survey computer science"),
]


def load_json(path, default):
    return json.loads(path.read_text()) if path.exists() else default


def broad_arxiv_domain(categories):
    primary = categories.split()[0] if categories else ""
    if primary.startswith("physics.med-ph"):
        return "Medicine"
    if primary.startswith("physics.geo-ph"):
        return "Earth Science"
    if primary.startswith("physics.soc-ph"):
        return "Social Science"
    for prefix, domain in [
        ("math", "Mathematics"),
        ("stat", "Mathematics"),
        ("q-bio", "Biology"),
        ("q-fin", "Economics"),
        ("econ", "Economics"),
        ("cs", "Computer Science"),
        ("eess", "Engineering"),
    ]:
        if primary.startswith(prefix):
            return domain
    return "Physics"


def parse_arxiv_raw(content):
    feed = ET.fromstring(content)
    ns = {"o": "http://www.openarchives.org/OAI/2.0/", "a": "http://arxiv.org/OAI/arXivRaw/"}
    errors = [(e.attrib.get("code"), e.text) for e in feed.findall("o:error", ns)]
    records = []
    for record in feed.findall(".//o:record", ns):
        raw = record.find("o:metadata/a:arXivRaw", ns)
        if raw is None:
            continue
        aid = raw.findtext("a:id", "", ns)
        if not re.fullmatch(r"\d{4}\.\d{4,5}", aid):
            continue
        versions = [v.attrib.get("version", "v1") for v in raw.findall("a:version", ns)]
        version = max(versions or ["v1"], key=lambda v: int(v[1:]))
        records.append(
            {
                "arxiv_id": aid,
                "id": aid + version,
                "title": raw.findtext("a:title", "", ns),
                "authors": [raw.findtext("a:authors", "", ns)],
                "categories": raw.findtext("a:categories", "", ns),
                "license_url": raw.findtext("a:license", "", ns),
                "comments": raw.findtext("a:comments", "", ns),
                "datestamp": record.findtext("o:header/o:datestamp", "", ns),
                "record_xml": ET.tostring(record, encoding="unicode"),
            }
        )
    return records, feed.findtext(".//o:resumptionToken", "", ns), errors


def link_file(source, destination, policy):
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        return
    try:
        os.link(source, destination)
    except OSError:
        check_disk(destination.parent, policy, source.stat().st_size)
        shutil.copy2(source, destination)


class Corpus:
    def __init__(self, args):
        self.args = args
        self.root = args.root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.policy = json.loads(args.policy.read_text())
        self.ledger = TokenLedger(self.root, self.policy)
        holds = load_json(self.root / "release_exclusions.json", {}).get("document_ids", [])
        self.ledger.hold_documents(holds)
        self.state = load_json(
            self.root / "state.json",
            {"batch_index": 0, "query_index": 0, "offsets": {}, "queue": [], "seen": [], "processed": []},
        )
        if self.state.get("discovery_api") != "arxiv_atom":
            self.state.update(discovery_api="arxiv_atom", offsets={}, query_index=0, discovery_seeded=False)
        self.session = requests.Session()
        self.session.headers["User-Agent"] = "MMProLong-public-corpus/0.1 (research document intake)"
        self._tokenizer = None
        self._last_public_request = 0.0
        write_json(self.root / "policy.json", self.policy)

    def public_get(self, url, **kwargs):
        time.sleep(max(0.0, 3.0 - (time.monotonic() - self._last_public_request)))
        try:
            return self.session.get(url, **kwargs)
        finally:
            self._last_public_request = time.monotonic()

    def status(self, phase, **extra):
        status = {
            **self.ledger.status(),
            "phase": phase,
            "updated_at_unix": time.time(),
            "free_gib": round(shutil.disk_usage(self.root).free / 1024**3, 2),
            "disk_reserve_gib": self.policy["min_free_gib"],
            "model": self.policy["model"],
            "model_workers": self.policy["workers"],
            "qa_per_call": self.policy.get("qa_per_call", 5),
            **extra,
        }
        write_json(self.root / "status.json", status)
        write_json(self.root / "state.json", self.state)
        write_progress(self.root, status, self.policy)
        print(json.dumps(status, ensure_ascii=False), flush=True)

    @property
    def tokenizer(self):
        if self._tokenizer is None:
            from transformers import AutoTokenizer

            self._tokenizer = AutoTokenizer.from_pretrained("Qwen/Qwen2.5-VL-7B-Instruct")
        return self._tokenizer

    def formatted(self, row, doc):
        answer = row["answer"] if isinstance(row["answer"], str) else json.dumps(row["answer"], ensure_ascii=False)
        context = "\n\n".join(item_template.format(doc_id=doc["id"], page_id=p) for p in range(doc["page_count"]))
        text = user_template.format(question=row["question"], context=context)
        tokens = sum(doc["image_tokens"]) + sum(
            len(self.tokenizer.encode(t, add_special_tokens=False))
            for t in text.split(image_special_token)
            if t.strip()
        )
        tokens += len(self.tokenizer.encode(system_template + " " + answer, add_special_tokens=False))
        conversations = json.dumps(
            [
                {"from": "human", "value": text.replace(image_special_token, "<image>")},
                {"from": "gpt", "value": system_template + " " + answer},
            ],
            ensure_ascii=False,
        )
        return tokens, conversations

    def commit(self, batch_root, documents, *, rebuild_exports=True):
        import pyarrow as pa
        import pyarrow.parquet as pq

        stored_bytes = (
            self.ledger.db.execute(
                "SELECT COALESCE(SUM(LENGTH(record_json)),0) FROM samples WHERE included=1"
            ).fetchone()[0]
            if rebuild_exports
            else 0
        )
        incoming_bytes = sum(p.stat().st_size for p in (batch_root / "accepted").glob("*.json"))
        check_disk(
            self.root, self.policy, (stored_bytes + incoming_bytes) * 3 if rebuild_exports else incoming_bytes * 3
        )
        lookup = {d["id"]: d for d in documents}
        prefix = "*" + documents[0]["id"] + "*" if len(documents) == 1 and not rebuild_exports else "*"
        domain_votes = {}
        for p in (batch_root / "calls").glob(prefix + "_generate.json"):
            call = load_json(p, {})
            try:
                domain = json.loads(call.get("content", "{}")).get("document_domain")
            except json.JSONDecodeError:
                continue
            ids = {s.get("document_id") for s in call.get("request_payload", {}).get("slots", [])}
            if domain in {*self.policy["source_domains"], "Language and Literature", "Other"} and len(ids) == 1:
                domain_votes.setdefault(next(iter(ids)), Counter())[domain] += 1
        for doc_id, votes in domain_votes.items():
            winner, count = votes.most_common(1)[0]
            if count > sum(votes.values()) / 2 and doc_id in lookup:
                lookup[doc_id]["source_domain"] = winner
                lookup[doc_id]["domain_tag_method"] = "majority of full-context generator domain labels"
                lookup[doc_id]["domain_votes"] = dict(votes)
                write_json(self.root / "documents" / (doc_id + ".json"), lookup[doc_id])
        # New window/agent routes classify from independent full-document reviews,
        # rather than claiming that a cropped generator saw the entire PDF.
        verification_votes = {}
        allowed_domains = {*self.policy["source_domains"], "Language and Literature", "Other"}
        for p in (batch_root / "calls").glob(prefix + "_verify*.json"):
            call = load_json(p, {})
            ident, domain = call.get("document_id"), call.get("result", {}).get("document_domain")
            if ident in lookup and domain in allowed_domains:
                verification_votes.setdefault(ident, Counter())[domain] += 1
        for ident, votes in verification_votes.items():
            winner, count = votes.most_common(1)[0]
            if count > sum(votes.values()) / 2:
                lookup[ident].update(
                    source_domain=winner,
                    domain_tag_method="majority of independent full-document verifier topic labels",
                    domain_votes=dict(votes),
                )
                write_json(self.root / "documents" / (ident + ".json"), lookup[ident])
        outcomes = Counter()
        accepted_pattern = documents[0]["id"] + "_*.json" if len(documents) == 1 and not rebuild_exports else "*.json"
        for p in sorted((batch_root / "accepted").glob(accepted_pattern)):
            check_disk(self.root, self.policy)
            row = json.loads(p.read_text())
            if row["document_id"] not in lookup:
                continue
            doc = lookup[row["document_id"]]
            tokens, conversations = self.formatted(row, doc)
            row.update(
                conversations=conversations,
                images=[f"images/{doc['id']}/page{i:03d}.png" for i in range(doc["page_count"])],
                source_domain=doc.get("source_domain", "Unclassified"),
                domain_tag_method=doc.get("domain_tag_method", ""),
                source_name="mmprolong_public_" + row["slot"]["kind"],
            )
            outcomes[self.ledger.admit(row, doc, tokens)] += 1
        if not rebuild_exports:
            return outcomes
        # Rebuild the small reference-only exports from committed ledger state.
        # No page image bytes are duplicated in parquet.
        admitted = [
            json.loads(r[0])
            for r in self.ledger.db.execute("SELECT record_json FROM samples WHERE included=1 ORDER BY id")
        ]
        simple = [
            {
                "id": r["id"],
                "document_id": r["document_id"],
                "conversations": r["conversations"],
                "images": r["images"],
                "kind": r["slot"]["kind"],
                "source_name": "mmprolong_public_" + r["slot"]["kind"],
                "token_count": r["token_count"],
                "evidence_pages": r["evidence_pages"],
                "answerable": r["answerable"],
                "source_url": r["source_url"],
                "license": r["license"],
                "context_sha256": r["context_sha256"],
            }
            for r in admitted
        ]
        if simple:
            check_disk(self.root, self.policy, sum(len(json.dumps(r)) for r in admitted) * 3)
            self.ledger.export_jsonl(self.root / "corpus.jsonl")
            for folder, absolute in [("training", False), ("training_local", True)]:
                rows = [{**r, "images": [str(self.root / p) for p in r["images"]]} if absolute else r for r in simple]
                target = self.root / folder / "data.parquet"
                target.parent.mkdir(exist_ok=True)
                table = pa.Table.from_pylist(rows)
                index = table.schema.get_field_index("evidence_pages")
                table = table.set_column(
                    index, "evidence_pages", pa.array([r["evidence_pages"] for r in rows], type=pa.list_(pa.int64()))
                )
                tmp = target.with_suffix(".parquet.tmp")
                pq.write_table(table, tmp, compression="zstd")
                tmp.replace(target)
        self.status("batch_committed", commit_outcomes=dict(outcomes))
        return outcomes

    def bootstrap(self, pilot):
        check_disk(self.root, self.policy)
        docs = json.loads((pilot / "manifest.json").read_text())
        held = set(load_json(pilot / "release_exclusions.json", {}).get("document_ids", []))
        keep = [d for d in docs if d["id"] not in held and not d.get("exclude_from_public_release")]
        write_json(self.root / "release_exclusions.json", {"document_ids": sorted(held)})
        bundle = self.root / "batches" / "bootstrap"
        (bundle / "accepted").mkdir(parents=True, exist_ok=True)
        for d in keep:
            d["source_domain"] = d.get("broad_domain", "Computer Science")
            d["domain_tag_method"] = "pilot manual topic assignment"
            write_json(self.root / "documents" / (d["id"] + ".json"), d)
            for p in (pilot / "images" / d["id"]).glob("*.png"):
                link_file(p, self.root / "images" / d["id"] / p.name, self.policy)
            for suffix in [".pdf", ".metadata.json", ".license-page.html"]:
                source = pilot / "sources" / (d["id"] + suffix)
                if source.exists():
                    link_file(source, self.root / "sources" / source.name, self.policy)
            if d["id"] not in self.state["processed"]:
                self.state["processed"].append(d["id"])
        for p in (pilot / "accepted").glob("*.json"):
            r = json.loads(p.read_text())
            if r["document_id"] in {d["id"] for d in keep}:
                write_json(bundle / "accepted" / p.name, r)
        write_json(bundle / "manifest.json", keep)
        self.commit(bundle, keep)

    def discover(self):
        if self.policy.get("bulk_catalog"):
            return self.discover_bulk()
        topic, query = QUERIES[self.state["query_index"] % len(QUERIES)]
        self.state["query_index"] += 1
        offset = self.state["offsets"].get(query, 0)
        url = "https://export.arxiv.org/api/query?" + urlencode(
            {
                "search_query": " AND ".join("all:" + word for word in query.split()),
                "sortBy": "submittedDate",
                "sortOrder": "descending",
                "max_results": 25,
                "start": offset,
            }
        )
        self.status("discovering_sources", query=query, offset=offset)
        response = None
        for attempt in range(2):
            try:
                response = self.public_get(url, timeout=45)
                response.raise_for_status()
                break
            except requests.RequestException as exc:
                self.status(
                    "source_search_failed",
                    query=query,
                    error_type=type(exc).__name__,
                    http_status=getattr(getattr(exc, "response", None), "status_code", None),
                    attempt=attempt + 1,
                )
                if attempt == 1:
                    return None
                time.sleep(3)
        try:
            feed = ET.fromstring(response.content)
        except ET.ParseError:
            self.status("source_search_failed", query=query, error_type="InvalidAtomResponse")
            return None
        namespace = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}
        added = 0
        for entry in feed.findall("atom:entry", namespace):
            aid = re.sub(r"v\d+$", "", entry.findtext("atom:id", default="", namespaces=namespace).split("/")[-1])
            if aid in self.state["seen"] or not re.fullmatch(r"\d{4}\.\d{4,5}", aid):
                continue
            self.state["seen"].append(aid)
            comment = entry.findtext("arxiv:comment", default="", namespaces=namespace)
            pages = re.search(r"\b(\d+)\s+pages\b", comment, re.I)
            if pages and not self.policy["min_document_pages"] <= int(pages[1]) <= self.policy["max_document_pages"]:
                continue
            self.state["queue"].append({"arxiv_id": aid, "source_domain": topic})
            added += 1
        self.state["offsets"][query] = offset + 25
        self.status("source_candidates_added", added=added)
        time.sleep(3)
        return added

    def discover_bulk(self):
        if self.state.get("oai_complete"):
            return 0
        params = {"verb": "ListRecords"}
        token = self.state.get("oai_resumption_token")
        if token:
            params["resumptionToken"] = token
        else:
            params.update(
                metadataPrefix="arXivRaw",
                **{
                    "from": self.state.get("oai_from", self.policy.get("bulk_catalog_from", "2026-01-01")),
                    "until": self.state.setdefault(
                        "oai_until", datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
                    ),
                },
            )
        url = "https://oaipmh.arxiv.org/oai?" + urlencode(params)
        self.status("discovering_sources", source_interface="arxiv_oai_bulk")
        check_disk(self.root, self.policy, 16 * 1024**2)
        try:
            response = self.public_get(url, timeout=90)
            response.raise_for_status()
            records, next_token, errors = parse_arxiv_raw(response.content)
        except (requests.RequestException, ET.ParseError) as exc:
            self.status("source_search_failed", source_interface="arxiv_oai_bulk", error_type=type(exc).__name__)
            return None
        if errors:
            if errors[0][0] == "badResumptionToken":
                self.state["oai_resumption_token"] = None
                self.state["oai_from"] = self.state.get("oai_last_datestamp", self.policy["bulk_catalog_from"])
                self.status("source_search_failed", error_type="ExpiredMetadataCursor")
                return None
            if errors[0][0] == "noRecordsMatch":
                self.state["oai_complete"] = True
                self.status("source_candidates_added", added=0, source_interface="arxiv_oai_bulk")
                return 0
            self.status("source_search_failed", error_type=errors[0][0])
            return None
        added = 0
        seen = set(self.state["seen"])
        for record in records:
            aid = record["arxiv_id"]
            if aid in seen:
                continue
            self.state["seen"].append(aid)
            seen.add(aid)
            if "creativecommons.org/licenses/by/4.0/" not in record["license_url"]:
                continue
            pages = re.search(r"\b(\d+)\s+pages\b", record["comments"], re.I)
            if pages and not self.policy["min_document_pages"] <= int(pages[1]) <= self.policy["max_document_pages"]:
                continue
            relative = Path("catalog_records") / (aid + ".json")
            write_json(self.root / relative, record)
            self.state["queue"].append(
                {
                    "arxiv_id": aid,
                    "source_domain": broad_arxiv_domain(record["categories"]),
                    "catalog_record": str(relative),
                }
            )
            added += 1
        self.state["oai_resumption_token"] = next_token or None
        self.state["oai_complete"] = not bool(next_token)
        if records:
            self.state["oai_last_datestamp"] = max(r["datestamp"] for r in records)
        self.status("source_candidates_added", added=added, scanned=len(records), source_interface="arxiv_oai_bulk")
        return added

    def acquire(self, candidate, batch):
        import fitz
        from public_vqa_pipeline import has_explicit_third_party_figure_notice

        aid = candidate["arxiv_id"]
        if aid in {re.sub(r"v\d+$", "", doc_id) for doc_id in self.state["processed"]}:
            return None
        check_disk(self.root, self.policy, 64 * 1024**2)
        catalog = load_json(self.root / candidate["catalog_record"], {}) if candidate.get("catalog_record") else None
        if catalog:
            if "creativecommons.org/licenses/by/4.0/" not in catalog["license_url"]:
                return None
            vid = catalog["id"]
            licenses = [catalog["license_url"]]
            title_text, authors = catalog["title"], catalog["authors"]
            proof, proof_suffix = catalog["record_xml"], ".license-record.xml"
        else:
            response = self.public_get("https://arxiv.org/abs/" + aid, timeout=45)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
            licenses = [
                a["href"] for a in soup.select("a[href]") if "creativecommons.org/licenses/by/4.0/" in a["href"]
            ]
            if not licenses:
                return None
            versions = [
                a["href"].split("/")[-1]
                for a in soup.select(".submission-history a[href]")
                if re.search(r"/abs/" + re.escape(aid) + r"v\d+$", a["href"])
            ]
            vid = versions[-1] if versions else aid + "v1"
            title_text = soup.select_one("h1.title").get_text(" ", strip=True).removeprefix("Title: ")
            authors = [a.get_text(" ", strip=True) for a in soup.select(".authors a")]
            proof, proof_suffix = response.text, ".license-page.html"
        if vid in self.state["processed"]:
            return None
        source = self.root / "sources" / (vid + ".pdf")
        source.parent.mkdir(parents=True, exist_ok=True)
        if not source.exists():
            time.sleep(3)
            with self.public_get("https://arxiv.org/pdf/" + vid, stream=True, timeout=60) as result:
                result.raise_for_status()
                content_length = int(result.headers.get("Content-Length", 0))
                if content_length > 64 * 1024**2:
                    return None
                check_disk(self.root, self.policy, max(content_length, 16 * 1024**2))
                temp = source.with_suffix(".pdf.download")
                try:
                    with temp.open("wb") as f:
                        for chunk in result.iter_content(1024 * 1024):
                            check_disk(self.root, self.policy, len(chunk))
                            f.write(chunk)
                            if f.tell() > 64 * 1024**2:
                                raise ValueError("Source exceeds pilot per-document size cap")
                    temp.replace(source)
                except BaseException:
                    temp.unlink(missing_ok=True)
                    raise
        with source.open("rb") as file:
            if file.read(5) != b"%PDF-":
                raise ValueError("Downloaded response is not a PDF")
        with fitz.open(source) as doc:
            n = len(doc)
            predicted_image_tokens = sum(
                round(math.ceil(p.rect.width * 2) / 28) * round(math.ceil(p.rect.height * 2) / 28) + 2 for p in doc
            )
            notices = [i + 1 for i, p in enumerate(doc) if has_explicit_third_party_figure_notice(p.get_text())]
            refs = [
                i
                for i, p in enumerate(doc)
                if i >= 8 and re.search(r"(?mi)^\s*(?:\d+\.?\s+)?(?:References|Bibliography)\s*$", p.get_text())
            ]
            body = min(refs, default=n)
        if (
            notices
            or not self.policy["min_document_pages"] <= n <= self.policy["max_document_pages"]
            or body < self.policy["min_content_pages"]
            or body / n < 0.6
            or predicted_image_tokens < self.policy["min_sample_tokens"] - 1000
            or predicted_image_tokens > self.policy["max_sample_tokens"] - 2000
        ):
            write_json(
                self.root / "source_rejections" / (vid + ".json"),
                {"id": vid, "page_count": n, "content_pages": body, "explicit_rights_notice_pages": notices},
            )
            self.state["processed"].append(vid)
            return None
        metadata = {
            "id": vid,
            "source": "arxiv",
            "title": title_text,
            "authors": authors,
            "source_url": "https://arxiv.org/abs/" + vid,
            "pdf_url": "https://arxiv.org/pdf/" + vid,
            "license": "CC-BY-4.0",
            "license_url": licenses[0],
            "paper_license_verified": True,
            "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            "page_count": n,
            "source_domain": candidate["source_domain"],
            "domain_tag_method": "arXiv primary category mapping"
            if catalog
            else "search topic; provisional, not final subject classification",
            "license_metadata_source": "arxiv_oai" if catalog else "arxiv_abstract_page",
            "retrieved_on": datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat(),
            "exclude_from_public_release": False,
            "explicit_rights_notice_pages": [],
            "rights_review_scope": "article license plus explicit-notice scan; not exhaustive image clearance",
        }
        write_json(source.with_suffix(".metadata.json"), metadata)
        source.with_suffix(proof_suffix).write_text(proof)
        for suffix in [".pdf", ".metadata.json", proof_suffix]:
            link_file(self.root / "sources" / (vid + suffix), batch / "sources" / (vid + suffix), self.policy)
        self.status("source_selected", document_id=vid, pages=n, source_topic=candidate["source_domain"])
        time.sleep(3)
        return metadata

    def make_plan(self, documents, *, projected=None, projected_counts=None):
        rng = random.Random(self.state["batch_index"] + 20261023)
        totals = projected if projected is not None else {k: v["tokens"] for k, v in self.ledger.totals().items()}
        counters = (
            projected_counts
            if projected_counts is not None
            else {k: v["samples"] for k, v in self.ledger.totals().items()}
        )
        plan = []
        planned_tokens = 0
        remaining = self.ledger.status()["remaining_tokens"]
        for d in documents:
            for i in range(self.policy["questions_per_document"]):
                if planned_tokens >= remaining + self.policy["max_sample_tokens"]:
                    return plan
                kind = self.ledger.next_kind(totals)
                totals[kind] = totals.get(kind, 0) + sum(d["image_tokens"])
                planned_tokens += sum(d["image_tokens"])
                body = d["content_page_count"]
                serial = counters.get(kind, 0)
                counters[kind] = serial + 1
                s = {
                    "id": f"{d['id']}_{kind}_{i:03d}",
                    "kind": kind,
                    "document_id": d["id"],
                    "require_document_novelty": self.policy.get("document_novelty_check", False),
                    "allowed_evidence_pages": list(range(body)),
                }
                if kind == "single":
                    quartile = serial % 4
                    s.update(
                        needle_count=1,
                        allowed_evidence_pages=list(range(quartile * body // 4, (quartile + 1) * body // 4)),
                    )
                elif kind == "multi_local":
                    length = rng.randint(8, min(15, body))
                    start = rng.randint(0, body - length)
                    s.update(
                        needle_count=2 if serial % 3 else 3,
                        local_window=[start, start + length - 1],
                        allowed_evidence_pages=list(range(start, start + length)),
                    )
                elif kind == "multi_distributed":
                    s.update(
                        needle_count=[2, 2, 3, 2, 3, 4][serial % 6],
                        distance_bin="medium" if serial % 2 == 0 else "far",
                    )
                elif kind == "reasoning":
                    s.update(needle_count=1 if serial % 2 else 2)
                else:
                    s.update(
                        needle_count=0, subtype="missing_detail" if serial % 2 == 0 else "missing_required_operand"
                    )
                plan.append(s)
        return plan

    def run(self):
        if self.policy.get("continuous_document_jobs"):
            from continuous_corpus import run_continuous

            return run_continuous(self)
        completed = 0
        if not self.state.get("discovery_seeded") and not self.policy.get("journal_prefetch"):
            for _ in QUERIES:
                check_disk(self.root, self.policy)
                self.discover()
                if self.policy.get("bulk_catalog") and len(self.state["queue"]) >= 128:
                    break
            self.state["discovery_seeded"] = True
            write_json(self.root / "state.json", self.state)
        while not self.ledger.status()["target_reached"]:
            updated_policy = json.loads(self.args.policy.read_text())
            if updated_policy["target_tokens"] != self.policy["target_tokens"]:
                raise ValueError("Cannot change the corpus token target during a run")
            self.policy = updated_policy
            self.ledger.policy = updated_policy
            write_json(self.root / "policy.json", self.policy)
            self.ledger.hold_documents(load_json(self.root / "release_exclusions.json", {}).get("document_ids", []))
            check_disk(self.root, self.policy)
            if self.args.max_batches is not None and completed >= self.args.max_batches:
                self.status("batch_limit_reached")
                return
            batch = self.root / "batches" / f"batch_{self.state['batch_index']:05d}"
            batch.mkdir(parents=True, exist_ok=True)
            for folder in ["images", "teacher"]:
                (self.root / folder).mkdir(exist_ok=True)
                if not (batch / folder).exists():
                    (batch / folder).symlink_to(self.root / folder, target_is_directory=True)
            if not (batch / "manifest.json").exists():
                selected = {p.stem for p in (batch / "sources").glob("*.pdf")}
                discovery_attempts = 0
                failed_discoveries = 0
                progress = self.ledger.status()
                average = (
                    progress["accepted_tokens"] / progress["accepted_samples"]
                    if progress["accepted_samples"]
                    else 100000
                )
                needed_documents = min(
                    self.policy["documents_per_batch"],
                    max(
                        1,
                        math.ceil(
                            progress["remaining_tokens"] / (average * self.policy["questions_per_document"] * 0.75)
                        ),
                    ),
                )
                # Domain balance changes only when a new source joins this batch.
                # Avoid re-reading the entire growing document catalog per candidate.
                topic_documents = {p.stem: load_json(p, {}) for p in (self.root / "documents").glob("*.json")}
                for p in (batch / "sources").glob("*.metadata.json"):
                    doc = load_json(p, {})
                    topic_documents[doc["id"]] = doc
                topic_counts = Counter(d.get("source_domain", "") for d in topic_documents.values())
                if self.policy.get("journal_prefetch"):
                    from journal_intake import corpus_counts

                    # Failed historical candidates must not consume the domain quota.
                    _, topic_counts, _ = corpus_counts(self.root)
                while len(selected) < needed_documents:
                    check_disk(self.root, self.policy)
                    if self.policy.get("journal_prefetch"):
                        from journal_intake import claim_ready, domain_order

                        added = claim_ready(
                            self.root, batch, needed_documents - len(selected), topic_counts, self.policy
                        )
                        selected.update(d["id"] for d in added)
                        if len(selected) >= needed_documents:
                            break
                        allowed_domains = domain_order(topic_counts, self.policy)
                        eligible = [
                            i for i, c in enumerate(self.state["queue"]) if c["source_domain"] in allowed_domains
                        ]
                        if not eligible:
                            intake = load_json(self.root / "intake/status.json", {})
                            self.status(
                                "waiting_for_prefetched_documents",
                                selected_documents=len(selected),
                                required_documents=needed_documents,
                                intake_ready=intake.get("ready_documents", 0),
                                intake_inflight=intake.get("inflight_documents", 0),
                            )
                            time.sleep(5)
                            continue
                    else:
                        eligible = list(range(len(self.state["queue"])))
                    if not self.state["queue"]:
                        found = self.discover()
                        failed_discoveries += found is None
                        discovery_attempts += 1
                        if discovery_attempts >= len(QUERIES) * 2 and not self.state["queue"]:
                            self.status(
                                "stopped_source_network" if failed_discoveries else "source_discovery_exhausted",
                                discovery_attempts=discovery_attempts,
                                failed_discoveries=failed_discoveries,
                            )
                            return
                        continue
                    candidate_index = min(
                        eligible,
                        key=lambda i: topic_counts[self.state["queue"][i]["source_domain"]],
                    )
                    candidate = self.state["queue"][candidate_index]
                    self.status("checking_source", arxiv_id=candidate["arxiv_id"])
                    try:
                        d = self.acquire(candidate, batch)
                        self.state["consecutive_source_failures"] = 0
                        self.state["queue"].pop(candidate_index)
                        write_json(self.root / "state.json", self.state)
                    except DiskReserveReached:
                        raise
                    except (requests.RequestException, ValueError) as exc:
                        self.status(
                            "source_request_failed", error_type=type(exc).__name__, arxiv_id=candidate["arxiv_id"]
                        )
                        code = getattr(getattr(exc, "response", None), "status_code", None)
                        if isinstance(exc, requests.RequestException) and code not in (400, 404, 410):
                            failures = self.state.get("consecutive_source_failures", 0) + 1
                            self.state["consecutive_source_failures"] = failures
                            if failures >= 3:
                                self.status("stopped_source_network", arxiv_id=candidate["arxiv_id"])
                                return
                            time.sleep(15)
                            continue
                        self.state["queue"].pop(candidate_index)
                        time.sleep(3)
                        continue
                    if d:
                        if d["id"] not in selected:
                            topic_counts[d.get("source_domain", "")] += 1
                        selected.add(d["id"])
                prepared_documents = {}
                if self.policy.get("journal_prefetch"):
                    for ident in selected:
                        receipt = load_json(self.root / "intake/receipts" / (ident + ".json"), {})
                        doc = load_json(self.root / "documents" / (ident + ".json"), {})
                        if receipt.get("sha256") and receipt["sha256"] == doc.get("sha256"):
                            prepared_documents[ident] = doc
                self.status(
                    "preparing_batch",
                    batch=batch.name,
                    documents=len(selected),
                    cached_documents=len(prepared_documents),
                )
                docs = prepare(batch, manifest_only=True, policy=self.policy, prepared_documents=prepared_documents)
                for d in docs:
                    write_json(self.root / "documents" / (d["id"] + ".json"), d)
                write_json(batch / "plan.json", self.make_plan(docs))
            docs = json.loads((batch / "manifest.json").read_text())
            self.status("generating_batch", batch=batch.name, documents=len(docs))
            runner_class = Runner
            if self.policy.get("generation_engine") == "hybrid_agentic_v1":
                from hybrid_vqa_pipeline import HybridRunner

                runner_class = HybridRunner
            runner = runner_class(
                SimpleNamespace(
                    root=batch,
                    env_file=self.args.env_file,
                    model=self.policy["model"],
                    disk_policy=self.policy,
                    qa_per_call=self.policy.get("qa_per_call", 5),
                    activity_path=self.root / "api_activity.json",
                    document_novelty_check=self.policy.get("document_novelty_check", False),
                    pipelined_document_jobs=self.policy.get("pipelined_document_jobs", False),
                )
            )
            try:
                runner.run(self.policy["workers"], self.policy["rounds_per_batch"])
            finally:
                runner.client.close()
            outcomes = self.commit(batch, docs)
            if docs and not outcomes.get("admitted") and not outcomes.get("duplicate"):
                self.status("stopped_batch_without_accepted_data", batch=batch.name)
                return
            for d in docs:
                if d["id"] not in self.state["processed"]:
                    self.state["processed"].append(d["id"])
            self.state["batch_index"] += 1
            completed += 1
            self.status("ready_for_next_batch")
        self.status("target_reached")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=["bootstrap", "run", "export", "status"])
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument(
        "--policy", type=Path, default=Path(__file__).parents[1] / "configs/mmprolong/public_corpus_5b.json"
    )
    parser.add_argument("--pilot-root", type=Path)
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--max-batches", type=int)
    args = parser.parse_args()
    from production_io import snapshot_lock

    args.root.mkdir(parents=True, exist_ok=True)
    with snapshot_lock(args.root):
        corpus = Corpus(args)
    if args.stage == "status":
        print(json.dumps({**load_json(corpus.root / "status.json", {}), **corpus.ledger.status()}, ensure_ascii=False))
        corpus.ledger.close()
        return
    with (corpus.root / "run.lock").open("w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit("A corpus process already holds this workspace lock")
        try:
            if args.stage == "bootstrap":
                if not args.pilot_root:
                    parser.error("--pilot-root required")
                corpus.bootstrap(args.pilot_root)
            elif args.stage == "run":
                if not args.env_file:
                    parser.error("--env-file required")
                corpus.run()
            elif args.stage == "export":
                corpus.commit(corpus.root / "_ledger_export", [])
                corpus.status("exports_rebuilt")
            else:
                corpus.status("status_requested")
        except DiskReserveReached as exc:
            corpus.status("paused_disk_reserve", reason=str(exc))
        except Exception as exc:
            corpus.status("stopped_error", error_type=type(exc).__name__)
            raise
        finally:
            corpus.ledger.close()


if __name__ == "__main__":
    main()
