#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/.." && pwd)"
. "$script_dir/custom-local-kimi-helpers.sh"
select_custom_local_kimi_pipeline_mode

python_bin="$(agentflow_repo_python "$repo_root")"

tmpdir="$(mktemp -d)"
stdout_path="$tmpdir/doctor.stdout"

cleanup() {
  local exit_code=$?
  trap - EXIT
  if [ "$exit_code" -eq 0 ]; then
    rm -rf "$tmpdir"
    return
  fi

  if [ -f "$stdout_path" ]; then
    printf "\nagentflow doctor stdout:\n" >&2
    sed -n '1,240p' "$stdout_path" >&2
  fi
  printf "\nkept tempdir for debugging: %s\n" "$tmpdir" >&2
}

trap cleanup EXIT

pipeline_name="custom-kimi${CUSTOM_LOCAL_KIMI_PIPELINE_SUFFIX}-doctor"
pipeline_path="$tmpdir/${pipeline_name}.py"
"$CUSTOM_LOCAL_KIMI_PIPELINE_WRITER" \
  "$pipeline_path" \
  "$pipeline_name" \
  "Temporary external doctor test for local Codex plus Claude-on-Kimi via ${CUSTOM_LOCAL_KIMI_PIPELINE_LABEL}."

printf "custom doctor pipeline path: %s\n" "$pipeline_path"

(
  cd "$repo_root"
  agentflow_run_with_timeout "$python_bin" "$python_bin" -m agentflow doctor "$pipeline_path" --output summary >"$stdout_path"
)

STDOUT_PATH="$stdout_path" EXPECTED_TRIGGER="$CUSTOM_LOCAL_KIMI_EXPECTED_TRIGGER" "$python_bin" - <<'PY'
import os
from pathlib import Path

stdout_path = Path(os.environ["STDOUT_PATH"])
stdout_text = stdout_path.read_text(encoding="utf-8")
expected_trigger = os.environ["EXPECTED_TRIGGER"]

required_fragments = (
    "Doctor: ok",
    "- bash_login_startup: ok - ",
    "- kimi_shell_helper: ok - `kimi` is available in `bash -lic`, exports `ANTHROPIC_API_KEY`, and sets `ANTHROPIC_BASE_URL=https://api.kimi.com/coding/`.",
    "- claude_ready: ok - Node `claude_review` (claude) can launch local Claude after the node shell bootstrap; `claude --version` succeeds in the prepared local shell.",
    "- codex_ready: ok - Node `codex_plan` (codex) can launch local Codex after the node shell bootstrap; `codex --version` succeeds in the prepared local shell.",
    "- launch_env_override: ok - Node `codex_plan`: Launch env clears current `OPENAI_BASE_URL` value ",
    "- launch_env_override: ok - Node `claude_review`: Launch env uses configured `ANTHROPIC_BASE_URL` value `https://api.kimi.com/coding/`",
    f"- bootstrap_env_override: ok - Node `claude_review`: Local shell bootstrap overrides current `ANTHROPIC_API_KEY` for this node via `{expected_trigger}` (`kimi` helper).",
    "Pipeline auto preflight: enabled - local Codex/Claude/Kimi nodes use a `kimi` shell bootstrap.",
    f"Pipeline auto preflight matches: codex_plan (codex) via `{expected_trigger}`, claude_review (claude) via `{expected_trigger}`",
)

for fragment in required_fragments:
    if fragment not in stdout_text:
        raise SystemExit(f"Missing doctor fragment {fragment!r}.\n--- stdout ---\n{stdout_text}")

accepted_codex_auth_fragments = (
    "- codex_auth: ok - Node `codex_plan` (codex) can authenticate local Codex after the node shell bootstrap via `OPENAI_API_KEY`.",
    "- codex_auth: ok - Node `codex_plan` (codex) can authenticate local Codex after the node shell bootstrap via `codex login status`.",
    "- codex_auth: ok - Node `codex_plan` (codex) can authenticate local Codex after the node shell bootstrap via `codex login status` or `OPENAI_API_KEY`.",
    "- codex_auth: ok - Node `codex_plan` (codex) can authenticate local Codex after the node shell bootstrap via `OPENAI_API_KEY` + `codex login status`.",
    "- codex_auth: ok - Node `codex_plan` (codex) can authenticate local Codex after the node shell bootstrap via `codex login status` + `OPENAI_API_KEY`.",
)
if not any(fragment in stdout_text for fragment in accepted_codex_auth_fragments):
    raise SystemExit(
        "Missing supported codex_auth fragment.\n"
        f"Accepted: {accepted_codex_auth_fragments!r}\n"
        f"--- stdout ---\n{stdout_text}"
    )

print("validated agentflow doctor summary for external custom pipeline")
PY
