from __future__ import annotations

from pathlib import Path
from typing import Any

from agentflow.skills import compile_skill_prelude
from agentflow.specs import NodeResult, NodeSpec, NodeStatus, PipelineSpec
from agentflow.utils import render_template


def _node_result_context(result: NodeResult) -> dict[str, Any]:
    return {
        "status": result.status.value,
        "output": result.output,
        "final_response": result.final_response,
        "stdout": "\n".join(result.stdout_lines),
        "stderr": "\n".join(result.stderr_lines),
        "trace": [event.model_dump(mode="json") for event in result.trace_events],
    }


def _fanout_subset_context(member_nodes: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "ids": [member["id"] for member in member_nodes],
        "size": len(member_nodes),
        "nodes": member_nodes,
        "outputs": [member["output"] for member in member_nodes],
        "final_responses": [member["final_response"] for member in member_nodes],
        "statuses": [member["status"] for member in member_nodes],
        "values": [member.get("value") for member in member_nodes],
    }


def _fanout_has_output(member: dict[str, Any]) -> bool:
    output = member.get("output")
    return isinstance(output, str) and bool(output.strip())


def build_render_context(pipeline: PipelineSpec, results: dict[str, NodeResult]) -> dict[str, Any]:
    nodes: dict[str, Any] = {}
    for node_id, result in results.items():
        nodes[node_id] = _node_result_context(result)

    pipeline_nodes = pipeline.node_map
    fanouts: dict[str, Any] = {}
    for group_id, member_ids in pipeline.fanouts.items():
        member_nodes: list[dict[str, Any]] = []
        for member_id in member_ids:
            result = results.get(member_id, NodeResult(node_id=member_id))
            member_context = {"id": member_id, **_node_result_context(result)}
            pipeline_node = pipeline_nodes.get(member_id)
            if pipeline_node is not None and pipeline_node.fanout_group == group_id and pipeline_node.fanout_member:
                member_context.update(pipeline_node.fanout_member)
            member_nodes.append(member_context)
        subset_context = _fanout_subset_context(member_nodes)
        status_counts = {status.value: 0 for status in NodeStatus}
        for member in member_nodes:
            status_counts[member["status"]] = status_counts.get(member["status"], 0) + 1
        with_output_nodes = [member for member in member_nodes if _fanout_has_output(member)]
        without_output_nodes = [member for member in member_nodes if not _fanout_has_output(member)]
        fanout_context = {
            **subset_context,
            "status_counts": status_counts,
            "summary": {
                "total": len(member_nodes),
                "with_output": len(with_output_nodes),
                "without_output": len(without_output_nodes),
                **status_counts,
            },
            "with_output": _fanout_subset_context(with_output_nodes),
            "without_output": _fanout_subset_context(without_output_nodes),
        }
        for status in NodeStatus:
            fanout_context[status.value] = _fanout_subset_context(
                [member for member in member_nodes if member["status"] == status.value]
            )
        fanouts[group_id] = fanout_context
    return {"pipeline": pipeline.model_dump(mode="json"), "nodes": nodes, "fanouts": fanouts}


def render_node_prompt(
    pipeline: PipelineSpec,
    node: NodeSpec,
    results: dict[str, NodeResult],
) -> str:
    context = build_render_context(pipeline, results)
    prompt = render_template(node.prompt, context)
    skill_prelude = compile_skill_prelude(node.skills, pipeline.working_path)
    if skill_prelude:
        return f"Selected skills:\n{skill_prelude}\n\nTask:\n{prompt}"
    return prompt
