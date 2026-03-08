from agentflow.defaults import default_smoke_pipeline_path
from agentflow.loader import load_pipeline_from_path


def test_bundled_smoke_pipeline_runs_codex_in_login_shell():
    pipeline = load_pipeline_from_path(default_smoke_pipeline_path())
    codex_node = next(node for node in pipeline.nodes if node.id == "codex_plan")
    claude_node = next(node for node in pipeline.nodes if node.id == "claude_review")

    assert codex_node.target.kind == "local"
    assert codex_node.target.shell == "bash"
    assert codex_node.target.shell_login is True
    assert codex_node.target.shell_interactive is True
    assert claude_node.target.shell_init == "kimi"
