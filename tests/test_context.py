from __future__ import annotations

from pathlib import Path

from agentflow.context import build_render_context, render_node_prompt
from agentflow.loader import load_pipeline_from_data
from agentflow.specs import NodeResult, NodeStatus


def _fanout_pipeline(tmp_path: Path):
    return load_pipeline_from_data(
        {
            "name": "fanout-context",
            "working_dir": str(tmp_path),
            "nodes": [
                {
                    "id": "worker",
                    "fanout": {
                        "as": "shard",
                        "values": [
                            {"target": "libpng", "seed": 1001},
                            {"target": "sqlite", "seed": 2002},
                            {"target": "openssl", "seed": 3003},
                        ],
                    },
                    "agent": "codex",
                    "prompt": "worker {{ shard.target }} seed {{ shard.seed }}",
                },
                {
                    "id": "merge",
                    "agent": "codex",
                    "depends_on": ["worker"],
                    "prompt": (
                        "completed={{ fanouts.worker.summary.completed }}/{{ fanouts.worker.size }} "
                        "failed={{ fanouts.worker.summary.failed }} :: "
                        "{% for shard in fanouts.worker.with_output.nodes %}"
                        "{{ shard.id }}={{ shard.target }}:{{ shard.output }};"
                        "{% endfor %}"
                    ),
                },
            ],
        },
        base_dir=tmp_path,
    )


def test_build_render_context_exposes_fanout_status_and_output_subsets(tmp_path: Path):
    pipeline = _fanout_pipeline(tmp_path)
    results = {
        "worker_0": NodeResult(node_id="worker_0", status=NodeStatus.COMPLETED, output="ok libpng"),
        "worker_1": NodeResult(node_id="worker_1", status=NodeStatus.FAILED, output="retry sqlite"),
        "worker_2": NodeResult(node_id="worker_2", status=NodeStatus.COMPLETED, output=""),
        "merge": NodeResult(node_id="merge"),
    }

    context = build_render_context(pipeline, results)
    worker = context["fanouts"]["worker"]

    assert worker["size"] == 3
    assert worker["summary"]["total"] == 3
    assert worker["summary"]["completed"] == 2
    assert worker["summary"]["failed"] == 1
    assert worker["summary"]["with_output"] == 2
    assert worker["summary"]["without_output"] == 1
    assert worker["status_counts"]["completed"] == 2
    assert worker["status_counts"]["failed"] == 1
    assert [node["id"] for node in worker["completed"]["nodes"]] == ["worker_0", "worker_2"]
    assert [node["id"] for node in worker["failed"]["nodes"]] == ["worker_1"]
    assert [node["id"] for node in worker["with_output"]["nodes"]] == ["worker_0", "worker_1"]
    assert [node["id"] for node in worker["without_output"]["nodes"]] == ["worker_2"]
    assert worker["failed"]["nodes"][0]["target"] == "sqlite"
    assert worker["completed"]["nodes"][1]["seed"] == 3003


def test_render_node_prompt_can_use_fanout_summary_and_filtered_nodes(tmp_path: Path):
    pipeline = _fanout_pipeline(tmp_path)
    results = {
        "worker_0": NodeResult(node_id="worker_0", status=NodeStatus.COMPLETED, output="ok libpng"),
        "worker_1": NodeResult(node_id="worker_1", status=NodeStatus.FAILED, output="retry sqlite"),
        "worker_2": NodeResult(node_id="worker_2", status=NodeStatus.COMPLETED, output=""),
        "merge": NodeResult(node_id="merge"),
    }

    rendered = render_node_prompt(pipeline, pipeline.node_map["merge"], results)

    assert rendered == (
        "completed=2/3 failed=1 :: "
        "worker_0=libpng:ok libpng;"
        "worker_1=sqlite:retry sqlite;"
    )
