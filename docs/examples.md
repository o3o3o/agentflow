# Examples Guide

## Bundled Templates

| Template | Use it when | Key features |
| --- | --- | --- |
| `pipeline` | You want the smallest generic starter. | Codex plan, Claude implementation, Kimi review, final Codex merge. |
| `codex-repo-sweep-batched` | You want a large repo audit that still produces a readable handoff. | `node_defaults`, `agent_defaults`, `fanout_batches`, staged reducers. |
| `local-kimi-smoke` | You want the shortest real-agent local smoke path. | `bootstrap: kimi`. |
| `local-kimi-shell-init-smoke` | You want the explicit shell-init equivalent. | `shell: bash`, login shell flags, `shell_init: kimi`. |
| `local-kimi-shell-wrapper-smoke` | You want the bootstrap expressed as an explicit wrapper. | `target.shell` with `{command}` injection. |

## Python Examples

| Example | Use it when | Key features |
| --- | --- | --- |
| `airflow_like.py` | You want the smallest Python-authored DAG reference. | Static dependencies with `plan >> [implement, review]`. |
| `airflow_like_fuzz_batched.py` | You want a large shard campaign driven by generic count and batch fanout plus a periodic monitor. | `fanout_count(...)`, `fanout_batches(...)`, `schedule.every_seconds`, log-path-aware monitor node. |
| `airflow_like_fuzz_grouped.py` | You want a large shard campaign driven by matrix fanout and grouped reducers. | `fanout_matrix(...)`, `fanout_group_by(...)`, reducer-local scope helpers. |
