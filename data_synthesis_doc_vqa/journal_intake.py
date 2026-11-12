"""Bounded, resumable journal-PDF prefetch, independent of the model worker.

Only public Crossref metadata and explicitly CC BY 4.0 article PDFs are used.
Rendering happens in separate processes because PyMuPDF is not thread safe.
Prepared inputs are transferred by hard link; the publication ledger stays with
the sole corpus writer. Source-topic labels are provisional until model review.
"""

import argparse
import fcntl
import hashlib
import json
import math
import os
import re
import shutil
import signal
import sqlite3
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import requests
from corpus_budget import DiskReserveReached, check_disk
from public_vqa_pipeline import has_explicit_third_party_figure_notice, prepare, write_json


USER_AGENT = "MMProLong-public-corpus/0.2 (https://github.com/zhaowei-wang-nlp/MMProLong)"
QUERIES = {
    "Biology": ["biology genetics ecology evolution", "molecular cellular biology", "biodiversity conservation"],
    "Medicine": [
        "clinical medicine systematic review",
        "public health epidemiology",
        "disease treatment clinical trial",
    ],
    "Earth Science": [
        "climate earth environmental science",
        "hydrology geography geology",
        "ocean atmosphere climate change",
    ],
    "Economics": [
        "economics financial markets economic growth",
        "labor income inequality economic policy",
        "agriculture economic development",
    ],
    "Social Science": [
        "social science sociology survey",
        "education psychology social behavior",
        "political science public policy",
    ],
    "Engineering": [
        "engineering materials manufacturing",
        "energy electrical engineering",
        "mechanical civil engineering",
    ],
    "Computer Science": ["computer science machine learning", "computer systems algorithms"],
    "Mathematics": ["mathematics mathematical modeling statistics", "applied mathematics probability"],
    "Physics": ["physics physical sciences", "statistical physics"],
}
JOURNALS = {
    "pone": "plosone",
    "pbio": "plosbiology",
    "pmed": "plosmedicine",
    "pgen": "plosgenetics",
    "ppat": "plospathogens",
    "pcbi": "ploscompbiol",
    "pntd": "plosntds",
    "pclm": "climate",
    "pgph": "globalpublichealth",
    "pwat": "water",
    "pdig": "digitalhealth",
    "pmen": "mentalhealth",
    "pstr": "sustainabilitytransformation",
}
STOPPING = False


def load(path, default):
    try:
        return json.loads(path.read_text())
    except FileNotFoundError:
        return default


def directory_bytes(path):
    total = 0
    for p in path.rglob("*"):
        try:
            if p.is_file():
                total += p.stat().st_size
        except FileNotFoundError:
            pass  # The consumer may have just claimed this prepared item.
    return total


def cc_by_40(url):
    parsed = urlparse(url or "")
    return (
        parsed.hostname in {"creativecommons.org", "www.creativecommons.org"}
        and parsed.path.rstrip("/") == "/licenses/by/4.0"
    )


def crossref_candidate(record, domain):
    license_url = next((x.get("URL") for x in record.get("license", []) if cc_by_40(x.get("URL"))), None)
    if not license_url:
        return None
    doi = record.get("DOI", "").lower()
    match = re.fullmatch(r"10\.1371/journal\.([a-z]+)\.(\d+)", doi)
    if match and match[1] in JOURNALS:
        source = "plos"
        pdf_url = f"https://journals.plos.org/{JOURNALS[match[1]]}/article/file?id={doi}&type=printable"
    elif re.fullmatch(r"10\.7554/elife\.\d+", doi):
        source = "elife"
        pdf_url = f"https://elifesciences.org/articles/{doi.rsplit('.', 1)[-1]}.pdf"
    else:
        return None
    return {
        "id": source + "-" + doi.replace("/", "-"),
        "doi": doi,
        "source": source,
        "source_url": "https://doi.org/" + doi,
        "pdf_url": pdf_url,
        "title": (record.get("title") or [doi])[0],
        "authors": [" ".join(filter(None, [a.get("given"), a.get("family")])) for a in record.get("author", [])],
        "license": "CC-BY-4.0",
        "license_url": license_url,
        "source_domain": domain,
        "domain_tag_method": "Crossref subject-query sampling; provisional until generator topic vote",
        "crossref_record": {
            k: record[k]
            for k in [
                "DOI",
                "title",
                "author",
                "license",
                "publisher",
                "container-title",
                "published",
                "URL",
                "link",
                "subject",
            ]
            if k in record
        },
    }


def domain_order(counts, policy):
    weights = policy.get("domain_sampling_weights") or dict.fromkeys(policy["source_domains"], 1)
    total = max(1, sum(counts.values()))
    denominator = sum(weights.values())
    slack = policy.get("domain_share_slack", 0.02)
    eligible = [d for d, w in weights.items() if w > 0 and counts.get(d, 0) / total < w / denominator + slack]
    return sorted(eligible, key=lambda d: (counts.get(d, 0) / weights[d], d))


def corpus_counts(root):
    with sqlite3.connect(f"file:{root}/corpus.sqlite?mode=ro", uri=True, timeout=30) as db:
        tokens = db.execute("SELECT COALESCE(SUM(tokens),0) FROM samples WHERE included=1").fetchone()[0]
        ids = {r[0] for r in db.execute("SELECT DISTINCT document_id FROM samples WHERE included=1")}
    state = load(root / "state.json", {})
    active = root / "batches" / f"batch_{state.get('batch_index', 0):05d}"
    pending = load(active / "manifest.json", [])
    if not pending:
        pending = [load(p, {}) for p in (active / "sources").glob("*.metadata.json")]
    docs = {ident: load(root / "documents" / (ident + ".json"), {}) for ident in ids}
    docs.update({d["id"]: d for d in pending if d.get("id") and d["id"] not in docs})
    return tokens, Counter(d.get("source_domain", "Other") for d in docs.values()), docs


def prepare_candidate(candidate, intake, policy):
    """Download, validate and render one complete PDF; publish prepared.json last."""
    intake = Path(intake)
    item = intake / "items" / candidate["id"]
    item.mkdir(parents=True, exist_ok=True)
    write_json(item / "candidate.json", candidate)
    prepared = item / "prepared.json"
    if prepared.exists():
        return {"status": "ready", "document": load(prepared, {})}
    source = item / "sources" / (candidate["id"] + ".pdf")
    source.parent.mkdir(exist_ok=True)
    started = time.monotonic()
    try:
        if not cc_by_40(candidate.get("license_url")):
            return {"status": "rejected", "reason": "license"}
        check_disk(intake, policy, 128 * 1024**2)
        if not source.exists():
            with requests.get(
                candidate["pdf_url"], stream=True, timeout=(15, 45), headers={"User-Agent": USER_AGENT}
            ) as response:
                if response.status_code in {429, 500, 502, 503, 504}:
                    return {
                        "status": "retry",
                        "reason": f"http_{response.status_code}",
                        "delay": max(
                            60,
                            min(
                                900,
                                int(response.headers.get("Retry-After", "60"))
                                if response.headers.get("Retry-After", "60").isdigit()
                                else 60,
                            ),
                        ),
                    }
                response.raise_for_status()
                temp = source.with_suffix(".download")
                with temp.open("wb") as stream:
                    for chunk in response.iter_content(1024 * 1024):
                        check_disk(intake, policy, len(chunk))
                        stream.write(chunk)
                        if stream.tell() > 64 * 1024**2 or time.monotonic() - started > 180:
                            raise ValueError("PDF download exceeds size or time limit")
                temp.replace(source)
        with source.open("rb") as stream:
            if stream.read(5) != b"%PDF-":
                raise ValueError("Response is not a PDF")
        import fitz

        with fitz.open(source) as pdf:
            pages = len(pdf)
            if not policy["min_document_pages"] <= pages <= policy["max_document_pages"]:
                return {"status": "rejected", "reason": "document_page_count", "pages": pages}
            texts = [page.get_text() for page in pdf]
            body = min(
                [
                    i
                    for i, text in enumerate(texts)
                    if i >= 8 and re.search(r"(?mi)^\s*(?:\d+\.?\s+)?(?:References|Bibliography)\s*$", text)
                ],
                default=pages,
            )
            notices = [i for i, text in enumerate(texts) if has_explicit_third_party_figure_notice(text)]
            image_tokens = sum(
                round(math.ceil(p.rect.width * 2) / 28) * round(math.ceil(p.rect.height * 2) / 28) + 2 for p in pdf
            )
        if (
            not policy["min_document_pages"] <= pages <= policy["max_document_pages"]
            or body < policy["min_content_pages"]
            or body / pages < policy.get("min_content_fraction", 0.6)
            or notices
            or not policy["min_sample_tokens"] - 1000 <= image_tokens <= policy["max_sample_tokens"] - 2000
        ):
            return {"status": "rejected", "reason": "document_eligibility", "pages": pages, "content_pages": body}
        metadata = {k: v for k, v in candidate.items() if k != "crossref_record"}
        metadata.update(
            paper_license_verified=True,
            sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
            page_count=pages,
            license_metadata_source="Crossref article license metadata",
            retrieved_on=datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat(),
            exclude_from_public_release=False,
            explicit_rights_notice_pages=[],
            rights_review_scope="article license plus explicit-notice scan; not exhaustive image clearance",
        )
        write_json(source.with_suffix(".metadata.json"), metadata)
        write_json(source.with_suffix(".license-record.json"), candidate["crossref_record"])
        docs = prepare(item, manifest_only=True, policy=policy)
        if len(docs) != 1:
            return {"status": "rejected", "reason": "rendered_context_eligibility"}
        write_json(prepared, docs[0])
        return {"status": "ready", "document": docs[0], "elapsed_seconds": round(time.monotonic() - started, 2)}
    except DiskReserveReached:
        return {"status": "retry", "reason": "disk_reserve", "delay": 60}
    except requests.RequestException as exc:
        code = getattr(getattr(exc, "response", None), "status_code", None)
        return {
            "status": "rejected" if code in {400, 404, 410} else "retry",
            "reason": f"http_{code}" if code else type(exc).__name__,
            "delay": 120,
        }
    except (ValueError, RuntimeError) as exc:
        return {"status": "rejected", "reason": type(exc).__name__}


def safe_link(source, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        if os.path.samefile(source, destination):
            return
        if hashlib.sha256(source.read_bytes()).digest() != hashlib.sha256(destination.read_bytes()).digest():
            raise ValueError("Prefetched document conflicts with existing asset")
        return
    os.link(source, destination)


def claim_ready(root, batch, limit, counts, policy):
    """A receipt is written only after every page and source file has a root link."""
    intake = root / "intake"
    candidates = [(p.parent, load(p, {})) for p in (intake / "items").glob("*/prepared.json")]
    selected = []
    while candidates and len(selected) < limit:
        order = domain_order(counts, policy)
        available = [(item, doc) for item, doc in candidates if doc["source_domain"] in order]
        if not available:
            break
        item, doc = min(available, key=lambda x: (order.index(x[1]["source_domain"]), x[1]["id"]))
        candidates.remove((item, doc))
        ident = doc["id"]
        claim = load(item / "claim.json", {})
        if claim and claim["batch"] != batch.name:
            continue
        write_json(item / "claim.json", {"batch": batch.name, "document_id": ident})
        check_disk(root, policy)
        for source in (item / "sources").iterdir():
            if source.name.endswith(".download"):
                continue
            safe_link(source, root / "sources" / source.name)
            safe_link(source, batch / "sources" / source.name)
        for index in range(doc["page_count"]):
            name = f"page{index:03d}.png"
            safe_link(item / "images" / ident / name, root / "images" / ident / name)
        write_json(root / "documents" / (ident + ".json"), doc)
        write_json(
            intake / "receipts" / (ident + ".json"),
            {"document_id": ident, "batch": batch.name, "sha256": doc["sha256"]},
        )
        shutil.rmtree(item)
        counts[doc["source_domain"]] += 1
        selected.append(doc)
    return selected


class Intake:
    def __init__(self, root, policy_path):
        self.root, self.policy_path = root, policy_path
        self.path = root / "intake"
        self.path.mkdir(exist_ok=True)
        self.state = load(
            self.path / "state.json",
            {"queues": {}, "offsets": {}, "seen": [], "inflight": {}, "completed": {}, "query_indices": {}},
        )
        for candidate in self.state["inflight"].values():
            if not (self.path / "items" / candidate["id"] / "prepared.json").exists():
                self.state["queues"].setdefault(candidate["source_domain"], []).insert(0, candidate)
        self.state["inflight"] = {}
        self.session = requests.Session()
        self.session.headers["User-Agent"] = USER_AGENT
        self.cooldown = {}
        self.last_discovery = 0

    def save(self):
        write_json(self.path / "state.json", self.state)

    def discover(self, domain):
        if time.time() < self.cooldown.get(domain, 0):
            return
        index = self.state["query_indices"].get(domain, 0)
        queries = QUERIES[domain]
        query = queries[index % len(queries)]
        # PLOS includes medicine, biology, environment, economics and social sciences.
        prefix = "10.7554" if domain in {"Biology", "Medicine"} and index % 4 == 3 else "10.1371"
        key = domain + "|" + prefix + "|" + query
        offset = self.state["offsets"].get(key, 0)
        self.state["query_indices"][domain] = index + 1
        if offset >= 10000:
            self.cooldown[domain] = time.time() + 3600
            return
        time.sleep(max(0, 1.0 - (time.monotonic() - self.last_discovery)))
        try:
            response = self.session.get(
                "https://api.crossref.org/works",
                params={
                    "filter": f"prefix:{prefix},from-pub-date:2016-01-01,until-pub-date:{datetime.now(ZoneInfo('Asia/Shanghai')).date()}",
                    "query": query,
                    "rows": 100,
                    "offset": offset,
                },
                timeout=(10, 30),
            )
            response.raise_for_status()
            message = response.json()["message"]
            seen = set(self.state["seen"])
            added = 0
            for record in message["items"]:
                candidate = crossref_candidate(record, domain)
                if candidate and candidate["id"] not in seen:
                    seen.add(candidate["id"])
                    self.state["seen"].append(candidate["id"])
                    self.state["queues"].setdefault(domain, []).append(candidate)
                    added += 1
            self.state["offsets"][key] = offset + len(message["items"]) if message["items"] else 10000
            self.cooldown[domain] = time.time() + (2 if added else 15)
            print("JOURNAL_CANDIDATES", domain, prefix, added, flush=True)
        except (requests.RequestException, ValueError, KeyError) as exc:
            self.cooldown[domain] = time.time() + 60
            print("JOURNAL_DISCOVERY_RETRY", domain, type(exc).__name__, flush=True)
        finally:
            self.last_discovery = time.monotonic()
            self.save()

    def run(self, stop_file=None, owner_pid=None):
        policy = load(self.policy_path, {})
        futures = {}
        last_stats, last_status, buffer_bytes = 0, 0, 0
        with ProcessPoolExecutor(max_workers=policy.get("intake_workers", 4)) as pool:
            while True:
                policy = load(self.policy_path, {})
                for future in list(futures):
                    if not future.done():
                        continue
                    candidate = futures.pop(future)
                    try:
                        result = future.result()
                    except Exception as exc:
                        result = {"status": "retry", "reason": type(exc).__name__, "delay": 120}
                    self.state["inflight"].pop(candidate["id"], None)
                    if result["status"] == "retry":
                        candidate["retry_at"] = time.time() + result.get("delay", 60)
                        self.state["queues"].setdefault(candidate["source_domain"], []).append(candidate)
                    else:
                        self.state["completed"][candidate["id"]] = {k: v for k, v in result.items() if k != "document"}
                    if result["status"] == "rejected":
                        write_json(
                            self.path / "rejections" / (candidate["id"] + ".json"),
                            {"candidate": candidate, "result": result},
                        )
                        shutil.rmtree(self.path / "items" / candidate["id"], ignore_errors=True)
                    print("JOURNAL_RESULT", candidate["id"], result["status"], result.get("reason", ""), flush=True)
                    self.save()
                if time.time() - last_stats > 20:
                    tokens, base_counts, docs = corpus_counts(self.root)
                    buffer_bytes = directory_bytes(self.path / "items")
                    last_stats = time.time()
                owner_gone = False
                if owner_pid:
                    try:
                        os.kill(owner_pid, 0)
                    except ProcessLookupError:
                        owner_gone = True
                stopping = (
                    STOPPING
                    or owner_gone
                    or (stop_file and stop_file.exists())
                    or tokens >= policy["target_tokens"] - policy["stop_tolerance_tokens"]
                )
                ready = [d for p in (self.path / "items").glob("*/prepared.json") if (d := load(p, {}))]
                counts = base_counts.copy()
                counts.update(d["source_domain"] for d in ready if d["id"] not in docs)
                counts.update(c["source_domain"] for c in futures.values())
                capacity = (
                    len(ready) + len(futures) < policy.get("prefetch_documents", 256)
                    and buffer_bytes < policy.get("prefetch_max_gib", 12) * 1024**3
                )
                disk_ok = shutil.disk_usage(self.root).free > (policy["min_free_gib"] + 4) * 1024**3
                if not stopping and capacity and disk_ok and len(futures) < policy.get("intake_workers", 4):
                    for domain in domain_order(counts, policy):
                        queue = self.state["queues"].setdefault(domain, [])
                        if not queue:
                            self.discover(domain)
                        eligible = next((i for i, c in enumerate(queue) if c.get("retry_at", 0) <= time.time()), None)
                        if eligible is None:
                            continue
                        candidate = queue.pop(eligible)
                        if (
                            candidate["id"] in docs
                            or (self.path / "receipts" / (candidate["id"] + ".json")).exists()
                            or (self.path / "items" / candidate["id"] / "prepared.json").exists()
                        ):
                            continue
                        self.state["inflight"][candidate["id"]] = candidate
                        self.save()
                        futures[pool.submit(prepare_candidate, candidate, str(self.path), policy)] = candidate
                        break
                if time.time() - last_status >= 10 or stopping:
                    write_json(
                        self.path / "status.json",
                        {
                            "pid": os.getpid(),
                            "phase": "stopping"
                            if stopping
                            else "prefetching"
                            if capacity and disk_ok
                            else "buffer_full",
                            "ready_documents": len(ready),
                            "inflight_documents": len(futures),
                            "ready_domains": dict(Counter(d["source_domain"] for d in ready)),
                            "admitted_tokens": tokens,
                            "projected_document_domains": dict(counts),
                            "buffer_gib": round(buffer_bytes / 1024**3, 3),
                            "updated_at_unix": time.time(),
                        },
                    )
                    last_status = time.time()
                if stopping and not futures:
                    return
                time.sleep(0.2 if futures and capacity and len(futures) < policy.get("intake_workers", 4) else 2)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--stop-file", type=Path)
    parser.add_argument("--owner-pid", type=int)
    args = parser.parse_args()

    def stop(*_):
        global STOPPING
        STOPPING = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    (args.root / "intake").mkdir(exist_ok=True)
    with (args.root / "intake" / "run.lock").open("w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return
        Intake(args.root, args.policy).run(args.stop_file, args.owner_pid)


if __name__ == "__main__":
    main()
