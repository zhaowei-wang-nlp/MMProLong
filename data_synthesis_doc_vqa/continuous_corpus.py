"""Bounded continuous document scheduling, with independent durable admission.

Batches are storage/provenance units only. A slow document never prevents a free
worker from starting a document in another batch. Only the coordinator writes
the ledger and batch lifecycle; PDF/API work stays in the bounded thread pool.
"""

import json
import shutil
import threading
import time
from collections import deque
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from types import SimpleNamespace

from corpus_budget import DiskReserveReached, check_disk
from hybrid_vqa_pipeline import HybridRunner
from journal_intake import claim_ready, corpus_counts
from production_io import snapshot_lock
from public_vqa_pipeline import prepare, write_json


def read(path, default):
    return json.loads(path.read_text()) if path.exists() else default


class SharedActivity:
    def __init__(self, root):
        self.root, self.lock = root, threading.Lock()
        self.active = self.peak = self.completed = 0

    def record(self, delta, job):
        with self.lock:
            self.active += delta
            self.peak = max(self.peak, self.active)
            self.completed += delta < 0
            write_json(
                self.root / "api_activity.json",
                {
                    "mode": "continuous_documents",
                    "active_requests": self.active,
                    "peak_requests": self.peak,
                    "completed_attempts": self.completed,
                    "last_job": job,
                    "updated_at_unix": time.time(),
                },
            )


class ContinuousProduction:
    def __init__(self, corpus):
        self.corpus, self.root = corpus, corpus.root
        self.workers = corpus.policy["workers"]
        self.runners, self.done, self.queue = {}, {}, deque()
        self.activity = SharedActivity(self.root)
        self.client = None
        self.pause_for_disk = False
        self.last_status = 0
        self.drain = self.root / "DRAIN"
        self.controller_stop = self.root / "production_4b_20261108" / "STOP"

    def persist(self):
        self.corpus.state["streaming_batches"] = list(self.runners)
        write_json(self.root / "state.json", self.corpus.state)
        active = [
            ident for name, runner in self.runners.items() for ident in runner.docs if ident not in self.done[name]
        ]
        write_json(self.root / "active_documents.json", {"document_ids": active, "updated_at_unix": time.time()})

    def attach(self, batch):
        runner = HybridRunner(
            SimpleNamespace(
                root=batch,
                env_file=self.corpus.args.env_file,
                model=self.corpus.policy["model"],
                disk_policy=self.corpus.policy,
                qa_per_call=1,
                activity_path=self.root / "api_activity.json",
                document_novelty_check=True,
                pipelined_document_jobs=True,
            )
        )
        if self.client is None:
            self.client = runner.client
        else:
            runner.client.close()
            runner.client = self.client
        runner.record_activity = self.activity.record
        self.runners[batch.name] = runner
        self.done[batch.name] = read(batch / "completed_documents.json", {})
        for ident in runner.docs:
            if ident not in self.done[batch.name]:
                self.queue.append((batch.name, ident))

    def recover(self):
        names = list(self.corpus.state.get("streaming_batches", []))
        # Adopt the legacy worker's unfinished batch without discarding cached QA.
        legacy = self.root / "batches" / f"batch_{self.corpus.state['batch_index']:05d}"
        if not names and legacy.exists() and any((legacy / "sources").glob("*.metadata.json")):
            names.append(legacy.name)
            self.corpus.state["batch_index"] += 1
        for name in names:
            batch = self.root / "batches" / name
            if not (batch / "manifest.json").exists():
                cached = {
                    p.stem.removesuffix(".metadata"): read(p, {}) for p in (batch / "sources").glob("*.metadata.json")
                }
                cached = {
                    ident: read(self.root / "documents" / (ident + ".json"), doc) for ident, doc in cached.items()
                }
                docs = prepare(batch, manifest_only=True, policy=self.corpus.policy, prepared_documents=cached)
                write_json(batch / "plan.json", self.corpus.make_plan(docs))
            self.attach(batch)
        self.persist()

    def add_batch(self):
        corpus = self.corpus
        check_disk(self.root, corpus.policy)
        batch = self.root / "batches" / f"batch_{corpus.state['batch_index']:05d}"
        batch.mkdir(parents=True, exist_ok=True)
        for folder in ["images", "teacher"]:
            (self.root / folder).mkdir(exist_ok=True)
            if not (batch / folder).exists():
                (batch / folder).symlink_to(self.root / folder, target_is_directory=True)
        _, counts, _ = corpus_counts(self.root)
        docs = claim_ready(self.root, batch, corpus.policy["documents_per_batch"], counts, corpus.policy)
        if not docs:
            return False
        # The allocated batch is durable before subsequent preparation can fail.
        corpus.state["batch_index"] += 1
        write_json(self.root / "state.json", {**corpus.state, "streaming_batches": [*self.runners, batch.name]})
        docs = prepare(batch, manifest_only=True, policy=corpus.policy, prepared_documents={d["id"]: d for d in docs})
        totals = {k: v["tokens"] for k, v in corpus.ledger.totals().items()}
        counters = {k: v["samples"] for k, v in corpus.ledger.totals().items()}
        # Reserve the planned task mix of every in-flight document as well as
        # actual admissions, so filling the queue cannot skew task proportions.
        for name, runner in self.runners.items():
            for slot in runner.plan:
                if slot["document_id"] not in self.done[name]:
                    kind = slot["kind"]
                    totals[kind] = totals.get(kind, 0) + sum(runner.docs[slot["document_id"]]["image_tokens"])
                    counters[kind] = counters.get(kind, 0) + 1
        write_json(batch / "plan.json", corpus.make_plan(docs, projected=totals, projected_counts=counters))
        self.attach(batch)
        self.persist()
        return True

    def finish(self, name, ident, future):
        runner = self.runners[name]
        error = None
        try:
            future.result()
        except DiskReserveReached:
            self.pause_for_disk = True
            return  # Keep this document resumable, including every candidate.
        except Exception as exc:
            error = type(exc).__name__
        with snapshot_lock(self.root):
            outcomes = (
                self.corpus.commit(runner.root, [runner.docs[ident]], rebuild_exports=False) if error is None else {}
            )
            self.done[name][ident] = {"outcomes": dict(outcomes), "error_type": error, "at_unix": time.time()}
            write_json(runner.root / "completed_documents.json", self.done[name])
            if ident not in self.corpus.state["processed"]:
                self.corpus.state["processed"].append(ident)
            self.persist()
        print("DOCUMENT_COMMITTED", ident, json.dumps(dict(outcomes)), error or "ok", flush=True)
        # Release multi-turn message/image memory immediately after this document.
        runner._agents.pop(ident, None)
        runner._contexts.pop(ident, None)
        if len(self.done[name]) == len(runner.docs):
            write_json(
                runner.root / "streaming_complete.json", {"at_unix": time.time(), "documents": len(runner.docs)}
            )
            del self.runners[name]
            del self.done[name]
            with snapshot_lock(self.root):
                self.persist()
            shutil.rmtree(runner.root / "transport_cache", ignore_errors=True)

    def stopping(self):
        return (
            self.pause_for_disk
            or self.drain.exists()
            or self.controller_stop.exists()
            or self.corpus.ledger.status()["target_reached"]
        )

    def run(self):
        with snapshot_lock(self.root):
            self.recover()
        futures = {}
        with ThreadPoolExecutor(max_workers=self.workers) as pool:
            while futures or not self.stopping():
                if not self.stopping() and len(self.queue) < self.workers // 2:
                    try:
                        with snapshot_lock(self.root):
                            self.add_batch()
                    except DiskReserveReached:
                        self.pause_for_disk = True
                while self.queue and len(futures) < self.workers and not self.stopping():
                    name, ident = self.queue.popleft()
                    future = pool.submit(
                        self.runners[name].run_document, ident, 0, self.corpus.policy["rounds_per_batch"]
                    )
                    futures[future] = (name, ident)
                if time.monotonic() - self.last_status > 30:
                    self.corpus.status(
                        "continuous_generation",
                        active_documents=len(futures),
                        queued_documents=len(self.queue),
                        active_batches=list(self.runners),
                        api_max_concurrency=self.corpus.policy["api_max_concurrency"],
                    )
                    self.last_status = time.monotonic()
                if not futures:
                    if self.stopping():
                        break
                    time.sleep(2)
                    continue
                finished, _ = wait(futures, timeout=1, return_when=FIRST_COMPLETED)
                for future in finished:
                    name, ident = futures.pop(future)
                    try:
                        self.finish(name, ident, future)
                    except DiskReserveReached:
                        self.pause_for_disk = True
                    # Fill the vacated slot before handling the next completion.
                    if self.queue and not self.stopping():
                        next_name, next_id = self.queue.popleft()
                        new = pool.submit(
                            self.runners[next_name].run_document, next_id, 0, self.corpus.policy["rounds_per_batch"]
                        )
                        futures[new] = (next_name, next_id)
        if self.client:
            self.client.close()
        self.corpus.status(
            "paused_disk_reserve"
            if self.pause_for_disk
            else "target_reached"
            if self.corpus.ledger.status()["target_reached"]
            else "drained"
        )


def run_continuous(corpus):
    ContinuousProduction(corpus).run()
