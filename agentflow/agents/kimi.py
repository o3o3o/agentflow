from __future__ import annotations

import json
from pathlib import Path

from agentflow.agents.base import AgentAdapter
from agentflow.prepared import ExecutionPaths, PreparedExecution
from agentflow.specs import NodeSpec


class KimiAdapter(AgentAdapter):
    def prepare(self, node: NodeSpec, prompt: str, paths: ExecutionPaths) -> PreparedExecution:
        provider = self.provider_config(node.provider, node.agent)
        request = {
            "prompt": prompt,
            "model": node.model or "kimi-k2-turbo-preview",
            "provider": (provider.model_dump(mode="json") if provider else {"name": "moonshot", "base_url": "https://api.moonshot.ai/v1", "api_key_env": "KIMI_API_KEY", "env": {}}),
            "tools_mode": node.tools.value,
            "working_dir": paths.target_workdir,
            "capture": node.capture.value,
            "skills": node.skills,
            "mcps": [mcp.model_dump(mode="json") for mcp in node.mcps],
            "timeout_seconds": node.timeout_seconds,
        }
        relative_path = self.relative_runtime_file("kimi-request.json")
        runtime_files = {relative_path: json.dumps(request, ensure_ascii=False, indent=2)}
        executable = node.executable or "python3"
        command = [
            executable,
            "-m",
            "agentflow.remote.kimi_bridge",
            str(Path(paths.target_runtime_dir) / relative_path),
        ]
        command.extend(node.extra_args)
        env = dict(node.env)
        if provider:
            env.update(provider.env)
        return PreparedExecution(
            command=command,
            env=env,
            cwd=paths.target_workdir,
            trace_kind="kimi",
            runtime_files=runtime_files,
        )
