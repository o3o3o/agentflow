from __future__ import annotations

import json

from typer.testing import CliRunner

from agentflow.cli import app

runner = CliRunner()


def test_validate_command_outputs_normalized_pipeline(tmp_path):
    pipeline_path = tmp_path / "pipeline.yaml"
    pipeline_path.write_text(
        "name: cli\nworking_dir: .\nnodes:\n  - id: alpha\n    agent: codex\n    prompt: hi\n",
        encoding="utf-8",
    )

    result = runner.invoke(app, ["validate", str(pipeline_path)])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["name"] == "cli"
    assert payload["nodes"][0]["id"] == "alpha"


def test_validate_resolves_working_dir_relative_to_pipeline_file(tmp_path, monkeypatch):
    pipeline_dir = tmp_path / "pipelines"
    pipeline_dir.mkdir()
    workdir = pipeline_dir / "workspace"
    workdir.mkdir()
    task_dir = workdir / "task"
    task_dir.mkdir()
    pipeline_path = pipeline_dir / "pipeline.yaml"
    pipeline_path.write_text(
        "name: cli\nworking_dir: workspace\nnodes:\n  - id: alpha\n    agent: codex\n    prompt: hi\n    target:\n      kind: local\n      cwd: task\n",
        encoding="utf-8",
    )
    other_dir = tmp_path / "elsewhere"
    other_dir.mkdir()
    monkeypatch.chdir(other_dir)

    result = runner.invoke(app, ["validate", str(pipeline_path)])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["working_dir"] == str(workdir.resolve())
    assert payload["nodes"][0]["target"]["cwd"] == str(task_dir.resolve())
