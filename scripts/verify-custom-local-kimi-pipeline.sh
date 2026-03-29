#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/.." && pwd)"
. "$script_dir/custom-local-kimi-helpers.sh"
select_custom_local_kimi_pipeline_mode

python_bin="$(agentflow_repo_python "$repo_root")"
pipeline_name="custom-kimi${CUSTOM_LOCAL_KIMI_PIPELINE_SUFFIX}-check-local"
pipeline_description="Temporary external real-agent check-local test for local Codex plus Claude-on-Kimi via ${CUSTOM_LOCAL_KIMI_PIPELINE_LABEL}."
expected_trigger="$CUSTOM_LOCAL_KIMI_EXPECTED_TRIGGER"

tmpdir="$(mktemp -d)"
pipeline_path="$tmpdir/${pipeline_name}.py"
stdout_path="$tmpdir/check-local.stdout"
stderr_path="$tmpdir/check-local.stderr"

cleanup() {
  local exit_code=$?
  trap - EXIT
  if [ "$exit_code" -eq 0 ]; then
    rm -rf "$tmpdir"
    return
  fi

  if [ -f "$stderr_path" ]; then
    printf "\nagentflow check-local stderr:\n" >&2
    sed -n '1,200p' "$stderr_path" >&2
  fi
  if [ -f "$stdout_path" ]; then
    printf "\nagentflow check-local stdout:\n" >&2
    sed -n '1,200p' "$stdout_path" >&2
  fi
  printf "\nkept tempdir for debugging: %s\n" "$tmpdir" >&2
}

trap cleanup EXIT

"$CUSTOM_LOCAL_KIMI_PIPELINE_WRITER" \
  "$pipeline_path" \
  "$pipeline_name" \
  "$pipeline_description"

printf "custom pipeline path: %s\n" "$pipeline_path"

(
  cd "$repo_root"
  agentflow_run_with_timeout "$python_bin" "$python_bin" -m agentflow check-local "$pipeline_path" --output json-summary >"$stdout_path" 2>"$stderr_path"
)

STDOUT_PATH="$stdout_path" STDERR_PATH="$stderr_path" PIPELINE_NAME="$pipeline_name" EXPECTED_TRIGGER="$expected_trigger" "$python_bin" - <<'PY'
import json
import os
from pathlib import Path

stdout_path = Path(os.environ["STDOUT_PATH"])
stderr_path = Path(os.environ["STDERR_PATH"])
stdout_text = stdout_path.read_text(encoding="utf-8")
stderr_text = stderr_path.read_text(encoding="utf-8")
expected_pipeline_name = os.environ["PIPELINE_NAME"]
expected_trigger = os.environ["EXPECTED_TRIGGER"]

run_payload = json.loads(stdout_text)
if run_payload.get("status") != "completed":
    raise SystemExit(f"Unexpected check-local run status in stdout JSON: {run_payload}")

pipeline = run_payload.get("pipeline") or {}
if pipeline.get("name") != expected_pipeline_name:
    raise SystemExit(f"Unexpected pipeline summary in stdout JSON: {run_payload}")

nodes = {node.get("id"): node for node in run_payload.get("nodes", [])}
expected_nodes = {"codex_plan", "claude_review"}
if set(nodes) != expected_nodes:
    raise SystemExit(f"Unexpected node ids in stdout JSON: {sorted(nodes)}")

for node_id, expected_preview in (("codex_plan", "codex ok"), ("claude_review", "claude ok")):
    node = nodes[node_id]
    if node.get("status") != "completed":
        raise SystemExit(f"Node {node_id!r} did not complete: {node}")
    preview = node.get("preview") or ""
    if expected_preview not in preview:
        raise SystemExit(f"Node {node_id!r} preview missing {expected_preview!r}: {node}")

preflight_payload = json.loads(stderr_text)
if preflight_payload.get("status") != "ok":
    raise SystemExit(f"Unexpected preflight status in stderr JSON: {preflight_payload}")

checks = preflight_payload.get("checks")
if not isinstance(checks, list):
    raise SystemExit(f"Missing preflight checks in stderr JSON: {preflight_payload}")

required_checks = {"bash_login_startup", "kimi_shell_helper", "claude_ready", "codex_ready", "codex_auth"}
present_checks = {check.get("name") for check in checks if isinstance(check, dict)}
missing_checks = sorted(required_checks - present_checks)
if missing_checks:
    raise SystemExit(f"Missing preflight checks in stderr JSON: {missing_checks}\n--- stderr ---\n{stderr_text}")

bootstrap_override_details = [
    check.get("detail")
    for check in checks
    if isinstance(check, dict) and check.get("name") == "bootstrap_env_override"
]
expected_override_fragment = f"via `{expected_trigger}` (`kimi` helper)."
if not any(isinstance(detail, str) and expected_override_fragment in detail for detail in bootstrap_override_details):
    raise SystemExit(
        f"Missing bootstrap override detail {expected_override_fragment!r} in stderr JSON.\n--- stderr ---\n{stderr_text}"
    )

auto_preflight = (preflight_payload.get("pipeline") or {}).get("auto_preflight") or {}
if auto_preflight.get("enabled") is not True:
    raise SystemExit(f"Expected auto preflight to be enabled in stderr JSON: {preflight_payload}")
if auto_preflight.get("reason") != "local Codex/Claude/Kimi nodes use a `kimi` shell bootstrap.":
    raise SystemExit(f"Unexpected auto preflight reason in stderr JSON: {preflight_payload}")

expected_matches = {
    f"codex_plan (codex) via `{expected_trigger}`",
    f"claude_review (claude) via `{expected_trigger}`",
}
if set(auto_preflight.get("match_summary") or []) != expected_matches:
    raise SystemExit(f"Unexpected auto preflight matches in stderr JSON: {preflight_payload}")

print("validated agentflow check-local json-summary stdout and preflight stderr")
PY
