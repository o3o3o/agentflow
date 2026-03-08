from __future__ import annotations

import json
import queue
import threading
from collections import defaultdict
from pathlib import Path
from uuid import uuid4

from agentflow.specs import RunEvent, RunRecord
from agentflow.utils import ensure_dir


class RunStore:
    def __init__(self, base_dir: str | Path = ".agentflow/runs") -> None:
        self.base_dir = ensure_dir(Path(base_dir))
        self._runs: dict[str, RunRecord] = {}
        self._locks: defaultdict[str, threading.Lock] = defaultdict(threading.Lock)
        self._subscribers: defaultdict[str, set[queue.Queue[RunEvent]]] = defaultdict(set)
        self._events_cache: defaultdict[str, list[RunEvent]] = defaultdict(list)

    async def create_run(self, record: RunRecord | None = None) -> RunRecord:
        if record is None:
            raise ValueError("create_run requires a RunRecord")
        self._runs[record.id] = record
        await self.persist_run(record.id)
        return record

    def new_run_id(self) -> str:
        return uuid4().hex

    async def persist_run(self, run_id: str) -> None:
        record = self._runs[run_id]
        run_dir = ensure_dir(self.base_dir / run_id)
        lock = self._locks[run_id]
        with lock:
            (run_dir / "run.json").write_text(record.model_dump_json(indent=2), encoding="utf-8")

    async def append_event(self, run_id: str, event: RunEvent) -> None:
        lock = self._locks[run_id]
        with lock:
            run_dir = ensure_dir(self.base_dir / run_id)
            with (run_dir / "events.jsonl").open("a", encoding="utf-8") as handle:
                handle.write(event.model_dump_json())
                handle.write("\n")
            self._events_cache[run_id].append(event)
        for subscriber in list(self._subscribers[run_id]):
            subscriber.put_nowait(event)

    def get_run(self, run_id: str) -> RunRecord:
        return self._runs[run_id]

    def list_runs(self) -> list[RunRecord]:
        return list(self._runs.values())

    def get_events(self, run_id: str) -> list[RunEvent]:
        return list(self._events_cache[run_id])

    async def subscribe(self, run_id: str) -> queue.Queue[RunEvent]:
        subscriber: queue.Queue[RunEvent] = queue.Queue()
        self._subscribers[run_id].add(subscriber)
        return subscriber

    async def unsubscribe(self, run_id: str, subscriber: queue.Queue[RunEvent]) -> None:
        self._subscribers[run_id].discard(subscriber)
