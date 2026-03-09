from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from agentflow.cli import app

runner = CliRunner()


@pytest.mark.parametrize("option", ["--rcfile", "--init-file"])
def test_inspect_command_treats_interactive_bash_rcfile_as_auth_source(
    tmp_path,
    monkeypatch,
    option: str,
):
    home = tmp_path / "home"
    home.mkdir()
    (home / "auth.bashrc").write_text("export ANTHROPIC_API_KEY=test-shell-key\n", encoding="utf-8")

    pipeline_path = tmp_path / "pipeline.yaml"
    pipeline_path.write_text(
        f"""name: inspect-claude-rcfile-provider-key
working_dir: .
nodes:
  - id: review
    agent: claude
    provider: anthropic
    prompt: hi
    target:
      kind: local
      shell: "env HOME={home} bash {option} $HOME/auth.bashrc -ic '{{command}}'"
""",
        encoding="utf-8",
    )
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    result = runner.invoke(app, ["inspect", str(pipeline_path), "--output", "json-summary"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["nodes"][0]["auth"] == "`ANTHROPIC_API_KEY` via `target.shell`"


@pytest.mark.parametrize("option", ["--rcfile", "--init-file"])
def test_doctor_with_pipeline_path_accepts_provider_credentials_from_interactive_bash_rcfile(
    tmp_path,
    monkeypatch,
    option: str,
):
    home = tmp_path / "home"
    home.mkdir()
    (home / "auth.bashrc").write_text("export ANTHROPIC_API_KEY=test-shell-key\n", encoding="utf-8")

    pipeline_path = tmp_path / "pipeline.yaml"
    pipeline_path.write_text(
        f"""name: doctor-claude-rcfile-provider-key
working_dir: .
nodes:
  - id: review
    agent: claude
    provider: anthropic
    prompt: hi
    target:
      kind: local
      shell: "env HOME={home} bash {option} $HOME/auth.bashrc -ic '{{command}}'"
""",
        encoding="utf-8",
    )
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    result = runner.invoke(app, ["doctor", str(pipeline_path), "--output", "summary"])

    assert result.exit_code == 0
    assert "provider_credentials" not in result.stdout
    assert "provider_credentials_probe" not in result.stdout


def test_inspect_command_treats_exec_prefixed_login_bash_startup_as_auth_source(
    tmp_path,
    monkeypatch,
):
    home = tmp_path / "home"
    home.mkdir()
    (home / ".profile").write_text('if [ -f "$HOME/.bashrc" ]; then . "$HOME/.bashrc"; fi\n', encoding="utf-8")
    (home / ".bashrc").write_text("export ANTHROPIC_API_KEY=test-shell-key\n", encoding="utf-8")

    pipeline_path = tmp_path / "pipeline.yaml"
    pipeline_path.write_text(
        f"""name: inspect-claude-exec-login-startup
working_dir: .
nodes:
  - id: review
    agent: claude
    provider: anthropic
    prompt: hi
    target:
      kind: local
      shell: "exec env HOME={home} bash -lic '{{command}}'"
""",
        encoding="utf-8",
    )
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    result = runner.invoke(app, ["inspect", str(pipeline_path), "--output", "json-summary"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["nodes"][0]["auth"] == "`ANTHROPIC_API_KEY` via local bash login and interactive startup files"
