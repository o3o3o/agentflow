from __future__ import annotations

import asyncio
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agentflow.agents.registry import AdapterRegistry, default_adapter_registry
from agentflow.context import render_node_prompt
from agentflow.prepared import ExecutionPaths
from agentflow.runners.registry import RunnerRegistry, default_runner_registry
from agentflow.specs import NodeResult, NodeStatus, PipelineSpec, RunEvent, RunRecord, RunStatus
from agentflow.store import RunStore
from agentflow.success import evaluate_success
from agentflow.traces import create_trace_parser
from agentflow.utils import ensure_dir, utcnow_iso


@dataclass(slots=True)
class Orchestrator:
    store: RunStore
    adapters: AdapterRegistry = default_adapter_registry
    runners: RunnerRegistry = default_runner_registry

    async def submit(self, pipeline: PipelineSpec) -> RunRecord:
        run_id = self.store.new_run_id()
        run = RunRecord(
            id=run_id,
            status=RunStatus.PENDING,
            pipeline=pipeline,
            nodes={node.id: NodeResult(node_id=node.id) for node in pipeline.nodes},
        )
        await self.store.create_run(run)

        def _background() -> None:
            asyncio.run(self.run(run_id))

        threading.Thread(target=_background, name=f"agentflow-{run_id}", daemon=True).start()
        return run

    async def wait(self, run_id: str, timeout: float | None = None) -> RunRecord:
        async def _poll() -> RunRecord:
            while True:
                record = self.store.get_run(run_id)
                if record.status in {RunStatus.COMPLETED, RunStatus.FAILED}:
                    return record
                await asyncio.sleep(0.05)

        if timeout is None:
            return await _poll()
        return await asyncio.wait_for(_poll(), timeout=timeout)

    def _build_paths(self, pipeline: PipelineSpec, run_id: str, node_id: str, node_target: Any) -> ExecutionPaths:
        host_workdir = pipeline.working_path
        host_runtime_dir = ensure_dir(self.store.base_dir / run_id / "runtime" / node_id)
        app_root = Path(__file__).resolve().parents[1]
        if node_target.kind == "container":
            target_workdir = node_target.workdir_mount
            target_runtime_dir = node_target.runtime_mount
        elif node_target.kind == "aws_lambda":
            target_workdir = node_target.remote_workdir
            target_runtime_dir = f"{node_target.remote_workdir.rstrip('/')}/.agentflow-runtime/{node_id}"
        else:
            target_workdir = node_target.cwd or str(host_workdir)
            target_runtime_dir = str(host_runtime_dir)
        return ExecutionPaths(
            host_workdir=host_workdir,
            host_runtime_dir=host_runtime_dir,
            target_workdir=target_workdir,
            target_runtime_dir=target_runtime_dir,
            app_root=app_root,
        )

    async def _publish(self, run_id: str, event_type: str, *, node_id: str | None = None, **data: Any) -> None:
        await self.store.append_event(run_id, RunEvent(run_id=run_id, type=event_type, node_id=node_id, data=data))

    async def _execute_node(self, run_id: str, node_id: str) -> None:
        record = self.store.get_run(run_id)
        pipeline = record.pipeline
        node = pipeline.node_map[node_id]
        result = record.nodes[node_id]
        result.status = NodeStatus.RUNNING
        result.started_at = utcnow_iso()
        await self._publish(run_id, "node_started", node_id=node_id)

        prompt = render_node_prompt(pipeline, node, record.nodes)
        paths = self._build_paths(pipeline, run_id, node_id, node.target)
        adapter = self.adapters.get(node.agent)
        runner = self.runners.get(node.target.kind)
        prepared = adapter.prepare(node, prompt, paths)
        parser = create_trace_parser(node.agent, node.id)

        async def on_output(stream_name: str, line: str) -> None:
            if stream_name == "stdout":
                result.stdout_lines.append(line)
                for event in parser.feed(line):
                    result.trace_events.append(event)
                    await self._publish(run_id, "node_trace", node_id=node_id, trace=event.model_dump(mode="json"))
            else:
                result.stderr_lines.append(line)
                event = parser.emit("stderr", "stderr", line, line, source="stderr")
                result.trace_events.append(event)
                await self._publish(run_id, "node_trace", node_id=node_id, trace=event.model_dump(mode="json"))

        raw = await runner.execute(node, prepared, paths, on_output)
        result.exit_code = raw.exit_code
        result.final_response = parser.finalize() or "\n".join(result.stdout_lines).strip()
        result.output = result.final_response if node.capture.value == "final" else "\n".join(result.stdout_lines)
        success_ok, success_details = evaluate_success(node, result, pipeline.working_path)
        result.success = success_ok
        result.success_details = success_details
        result.finished_at = utcnow_iso()
        result.status = NodeStatus.COMPLETED if raw.exit_code == 0 and success_ok else NodeStatus.FAILED
        await self._publish(
            run_id,
            "node_completed" if result.status == NodeStatus.COMPLETED else "node_failed",
            node_id=node_id,
            exit_code=result.exit_code,
            success=result.success,
            output=result.output,
            final_response=result.final_response,
            success_details=result.success_details,
        )
        await self.store.persist_run(run_id)

    async def run(self, run_id: str) -> RunRecord:
        record = self.store.get_run(run_id)
        pipeline = record.pipeline
        record.status = RunStatus.RUNNING
        await self._publish(run_id, "run_started", pipeline=pipeline.model_dump(mode="json"))
        await self.store.persist_run(run_id)

        node_map = pipeline.node_map
        remaining = set(node_map)
        in_progress: dict[str, asyncio.Task[None]] = {}
        semaphore = asyncio.Semaphore(pipeline.concurrency)

        async def launch(node_id: str) -> None:
            async with semaphore:
                await self._execute_node(run_id, node_id)

        while remaining or in_progress:
            ready = [
                node_id
                for node_id in list(remaining)
                if all(record.nodes[dependency].status == NodeStatus.COMPLETED for dependency in node_map[node_id].depends_on)
            ]
            blocked = [
                node_id
                for node_id in list(remaining)
                if any(record.nodes[dependency].status in {NodeStatus.FAILED, NodeStatus.SKIPPED} for dependency in node_map[node_id].depends_on)
            ]
            for node_id in blocked:
                record.nodes[node_id].status = NodeStatus.SKIPPED
                record.nodes[node_id].finished_at = utcnow_iso()
                remaining.remove(node_id)
                await self._publish(run_id, "node_skipped", node_id=node_id, reason="upstream_failure")
            for node_id in ready:
                if node_id not in in_progress:
                    remaining.remove(node_id)
                    in_progress[node_id] = asyncio.create_task(launch(node_id))
            if not in_progress:
                break
            done, _ = await asyncio.wait(in_progress.values(), return_when=asyncio.FIRST_COMPLETED)
            finished_ids = [node_id for node_id, task in in_progress.items() if task in done]
            for node_id in finished_ids:
                task = in_progress.pop(node_id)
                await task

        if any(node.status == NodeStatus.FAILED for node in record.nodes.values()):
            record.status = RunStatus.FAILED
        else:
            record.status = RunStatus.COMPLETED
        record.finished_at = utcnow_iso()
        await self._publish(run_id, "run_completed", status=record.status.value)
        await self.store.persist_run(run_id)
        return record
