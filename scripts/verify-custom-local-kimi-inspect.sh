#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/.." && pwd)"
. "$script_dir/custom-local-kimi-helpers.sh"
select_custom_local_kimi_pipeline_mode

python_bin="$(agentflow_repo_python "$repo_root")"

tmpdir="$(mktemp -d)"
pipeline_name="custom-kimi${CUSTOM_LOCAL_KIMI_PIPELINE_SUFFIX}-inspect"
inspect_path="$tmpdir/${pipeline_name}.py"
stdout_path="$tmpdir/inspect.stdout"

cleanup() {
  local exit_code=$?
  trap - EXIT
  if [ "$exit_code" -eq 0 ]; then
    rm -rf "$tmpdir"
    return
  fi

  if [ -f "$stdout_path" ]; then
    printf "\nagentflow inspect stdout:\n" >&2
    sed -n '1,200p' "$stdout_path" >&2
  fi
  printf "\nkept tempdir for debugging: %s\n" "$tmpdir" >&2
}

trap cleanup EXIT

"$CUSTOM_LOCAL_KIMI_PIPELINE_WRITER" \
  "$inspect_path" \
  "$pipeline_name" \
  "Temporary external inspect test for local Codex plus Claude-on-Kimi via ${CUSTOM_LOCAL_KIMI_PIPELINE_LABEL}."

printf "custom inspect pipeline path: %s\n" "$inspect_path"

(
  cd "$repo_root"
  agentflow_run_with_timeout "$python_bin" "$python_bin" -m agentflow inspect "$inspect_path" --output summary >"$stdout_path"
)

PIPELINE_DIR="$tmpdir" STDOUT_PATH="$stdout_path" EXPECTED_TRIGGER="$CUSTOM_LOCAL_KIMI_EXPECTED_TRIGGER" EXPECTED_PIPELINE_NAME="$pipeline_name" EXPECTED_LAUNCH="$(
  case "$CUSTOM_LOCAL_KIMI_PIPELINE_MODE" in
    bootstrap)
      printf "%s" "Launch: bash -l -i -c 'command -v kimi >/dev/null 2>&1 && kimi && eval \"\$AGENTFLOW_TARGET_COMMAND\"'"
      ;;
    shell-init)
      printf "%s" "Launch: bash -l -i -c 'kimi && eval \"\$AGENTFLOW_TARGET_COMMAND\"'"
      ;;
    shell-wrapper)
      printf "%s" "Launch: bash -lic 'command -v kimi >/dev/null 2>&1 && kimi && eval \"\$AGENTFLOW_TARGET_COMMAND\"'"
      ;;
  esac
)" EXPECTED_BOOTSTRAP="$(
  case "$CUSTOM_LOCAL_KIMI_PIPELINE_MODE" in
    bootstrap)
      printf "%s" "Bootstrap: preset=kimi, shell=bash, login=true, startup="
      ;;
    shell-init)
      printf "%s" "Bootstrap: shell=bash, login=true, startup="
      ;;
    shell-wrapper)
      printf "%s" "Bootstrap: shell=bash -lic 'command -v kimi >/dev/null 2>&1 && kimi && {command}', login=true, startup="
      ;;
  esac
)" "$python_bin" - <<'PY'
import os
from pathlib import Path

pipeline_dir = Path(os.environ["PIPELINE_DIR"]).resolve()
stdout_path = Path(os.environ["STDOUT_PATH"])
stdout_text = stdout_path.read_text(encoding="utf-8")
expected_trigger = os.environ["EXPECTED_TRIGGER"]
expected_pipeline_name = os.environ["EXPECTED_PIPELINE_NAME"]
expected_launch = os.environ["EXPECTED_LAUNCH"]
expected_bootstrap = os.environ["EXPECTED_BOOTSTRAP"]

required_fragments = (
    f"Pipeline: {expected_pipeline_name}",
    f"Working dir: {pipeline_dir}",
    "Auto preflight: enabled - local Codex/Claude/Kimi nodes use a `kimi` shell bootstrap.",
    f"Auto preflight matches: codex_plan (codex) via `{expected_trigger}`, claude_review (claude) via `{expected_trigger}`",
    "- codex_plan [codex/local]",
    "- claude_review [claude/local]",
    "Provider: kimi, key=ANTHROPIC_API_KEY, url=https://api.kimi.com/coding/",
    expected_bootstrap,
    "Prepared: codex exec",
    "Prepared: claude -p",
    expected_launch,
)

for fragment in required_fragments:
    if fragment not in stdout_text:
        raise SystemExit(f"Missing inspect fragment {fragment!r}.\n--- stdout ---\n{stdout_text}")

cwd_fragment = f"Cwd: {pipeline_dir}"
if stdout_text.count(cwd_fragment) != 2:
    raise SystemExit(
        f"Expected both local nodes to resolve cwd to {pipeline_dir!s}.\n--- stdout ---\n{stdout_text}"
    )

print("validated agentflow inspect summary for external custom pipeline")
PY
