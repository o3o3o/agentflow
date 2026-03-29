from agentflow import DAG, claude, codex

with DAG(
    "local-real-agents-kimi-shell-wrapper-smoke",
    description="Minimal parallel real-agent smoke test for local Codex plus Claude-on-Kimi via an explicit target.shell Kimi wrapper.",
    working_dir=".",
    concurrency=2,
    local_target_defaults={
        "shell": "bash -lic 'command -v kimi >/dev/null 2>&1 && kimi && {command}'",
    },
) as dag:
    codex(
        task_id="codex_plan",
        env={"OPENAI_BASE_URL": ""},
        prompt="Reply with exactly: codex ok\n",
        timeout_seconds=180,
        success_criteria=[{"kind": "output_contains", "value": "codex ok"}],
    )
    claude(
        task_id="claude_review",
        provider="kimi",
        prompt="Reply with exactly: claude ok\n",
        timeout_seconds=180,
        success_criteria=[{"kind": "output_contains", "value": "claude ok"}],
    )

print(dag.to_json())
