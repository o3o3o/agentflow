from __future__ import annotations

import json
import subprocess
import textwrap
from pathlib import Path

from typer.testing import CliRunner

from agentflow.cli import app
from agentflow.doctor import (
    LocalToolchainReport,
    ShellBridgeRecommendation,
    _KIMI_BASE_URL_MISMATCH_EXIT_CODE,
    build_local_kimi_toolchain_report,
)


runner = CliRunner()


def _write_executable(path: Path, body: str) -> None:
    path.write_text(f"#!/usr/bin/env bash\nset -euo pipefail\n{body}", encoding="utf-8")
    path.chmod(0o755)


def _write_login_shell_home(home: Path) -> None:
    home.mkdir()
    (home / ".profile").write_text('if [ -f "$HOME/.bashrc" ]; then . "$HOME/.bashrc"; fi\n', encoding="utf-8")
    (home / ".bashrc").write_text("export PATH=\"$HOME/bin:$PATH\"\n", encoding="utf-8")


def test_build_local_kimi_toolchain_report_reports_startup_and_versions(
    monkeypatch,
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    _write_login_shell_home(home)

    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(
            args=args[0],
            returncode=0,
            stdout=(
                "ANTHROPIC_BASE_URL=https://api.kimi.com/coding/\n"
                "CODEX_AUTH=OPENAI_API_KEY + login\n"
                "CLAUDE_PATH=/tmp/bin/claude\n"
                "CLAUDE_VERSION=Claude Code 0.0.0\n"
                "CODEX_PATH=/tmp/bin/codex\n"
                "CODEX_VERSION=codex-cli 0.0.0\n"
            ),
            stderr="",
        )

    monkeypatch.setattr("agentflow.doctor._run_doctor_subprocess", fake_run)

    report = build_local_kimi_toolchain_report(home=home)

    assert report == LocalToolchainReport(
        status="ok",
        startup_files={
            "~/.bash_profile": "missing",
            "~/.bash_login": "missing",
            "~/.profile": "present",
        },
        bash_login_startup="~/.profile -> ~/.bashrc",
        shell_bridge=None,
        anthropic_base_url="https://api.kimi.com/coding/",
        codex_auth="OPENAI_API_KEY + login",
        codex_path="/tmp/bin/codex",
        codex_version="codex-cli 0.0.0",
        claude_path="/tmp/bin/claude",
        claude_version="Claude Code 0.0.0",
    )


def test_build_local_kimi_toolchain_report_keeps_base_url_on_failure(
    monkeypatch,
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    _write_login_shell_home(home)

    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(
            args=args[0],
            returncode=_KIMI_BASE_URL_MISMATCH_EXIT_CODE,
            stdout="ANTHROPIC_BASE_URL=https://kimi.invalid/\n",
            stderr="",
        )

    monkeypatch.setattr("agentflow.doctor._run_doctor_subprocess", fake_run)

    report = build_local_kimi_toolchain_report(home=home)

    assert report.status == "failed"
    assert report.anthropic_base_url == "https://kimi.invalid/"
    assert report.detail == (
        "`kimi` runs in `bash -lic`, but `ANTHROPIC_BASE_URL` is `https://kimi.invalid/` "
        "instead of `https://api.kimi.com/coding/`; the bundled smoke pipeline will not be able "
        "to route Claude through Kimi."
    )


def test_build_local_kimi_toolchain_report_requires_kimi_to_export_anthropic_env(
    monkeypatch,
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    bin_dir = home / "bin"
    bin_dir.mkdir()
    (home / ".profile").write_text('if [ -f "$HOME/.bashrc" ]; then . "$HOME/.bashrc"; fi\n', encoding="utf-8")
    (home / ".bashrc").write_text(
        'export PATH="$HOME/bin:$PATH"\n'
        "kimi() {\n"
        f"{textwrap.indent(':', '  ')}\n"
        "}\n",
        encoding="utf-8",
    )
    _write_executable(
        bin_dir / "codex",
        'if [ "${1:-}" = "login" ] && [ "${2:-}" = "status" ]; then\n'
        "  exit 0\n"
        "fi\n"
        'printf "codex-cli 0.0.0\\n"\n',
    )
    _write_executable(bin_dir / "claude", 'printf "Claude Code 0.0.0\\n"\n')
    monkeypatch.setenv("ANTHROPIC_API_KEY", "ambient-kimi-key")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://api.kimi.com/coding/")

    report = build_local_kimi_toolchain_report(home=home)

    assert report.status == "failed"
    assert report.detail == (
        "`kimi` runs in `bash -lic`, but it does not export `ANTHROPIC_API_KEY`; "
        "the bundled smoke pipeline will not be able to authenticate Claude-on-Kimi."
    )


def test_toolchain_local_command_renders_summary_with_shell_bridge(monkeypatch) -> None:
    report = LocalToolchainReport(
        status="failed",
        startup_files={
            "~/.bash_profile": "present",
            "~/.bash_login": "missing",
            "~/.profile": "present",
        },
        bash_login_startup="~/.bash_profile",
        shell_bridge=ShellBridgeRecommendation(
            target="~/.bash_profile",
            source="~/.bashrc",
            snippet='if [ -f "$HOME/.bashrc" ]; then\n  . "$HOME/.bashrc"\nfi\n',
            reason="Bash login startup uses `~/.bash_profile`, but it does not reference `~/.bashrc`.",
        ),
        codex_path="/tmp/bin/codex",
        codex_version="codex-cli 0.0.0",
        claude_path="/tmp/bin/claude",
        claude_version="Claude Code 0.0.0",
        detail="`kimi` is unavailable in `bash -lic`; add it to your bash startup files before running the bundled smoke pipeline.",
    )
    monkeypatch.setattr("agentflow.cli.build_local_kimi_toolchain_report", lambda: report)

    result = runner.invoke(app, ["toolchain-local", "--output", "summary"])

    assert result.exit_code == 1
    assert "Toolchain: failed" in result.stdout
    assert "~/.bash_profile: present" in result.stdout
    assert "bash login bridge target: ~/.bash_profile" in result.stdout
    assert "codex: /tmp/bin/codex (codex-cli 0.0.0)" in result.stdout
    assert "claude: /tmp/bin/claude (Claude Code 0.0.0)" in result.stdout
    assert '  . "$HOME/.bashrc"' in result.stdout
    assert "detail: `kimi` is unavailable in `bash -lic`" in result.stdout


def test_toolchain_local_command_emits_json(monkeypatch) -> None:
    report = LocalToolchainReport(
        status="ok",
        startup_files={
            "~/.bash_profile": "missing",
            "~/.bash_login": "missing",
            "~/.profile": "present",
        },
        bash_login_startup="~/.profile -> ~/.bashrc",
        shell_bridge=None,
        anthropic_base_url="https://api.kimi.com/coding/",
        codex_auth="OPENAI_API_KEY + login",
        codex_path="/tmp/bin/codex",
        codex_version="codex-cli 0.0.0",
        claude_path="/tmp/bin/claude",
        claude_version="Claude Code 0.0.0",
    )
    monkeypatch.setattr("agentflow.cli.build_local_kimi_toolchain_report", lambda: report)

    result = runner.invoke(app, ["toolchain-local", "--output", "json"])

    assert result.exit_code == 0
    assert json.loads(result.stdout) == {
        "status": "ok",
        "startup_files": {
            "~/.bash_profile": "missing",
            "~/.bash_login": "missing",
            "~/.profile": "present",
        },
        "bash_login_startup": "~/.profile -> ~/.bashrc",
        "shell_bridge": None,
        "anthropic_base_url": "https://api.kimi.com/coding/",
        "codex_auth": "OPENAI_API_KEY + login",
        "codex_path": "/tmp/bin/codex",
        "codex_version": "codex-cli 0.0.0",
        "claude_path": "/tmp/bin/claude",
        "claude_version": "Claude Code 0.0.0",
    }
