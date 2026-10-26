# Benchmark results

Raw results behind the findings in the main README. They were all recorded on 2026-10-26 with Claude Code 2.1.310, Opus 5.5, Sonnet 5.5 and Haiku 5.5. Re-render any run with `python3 bench/report.py bench/results/<run>`.

| Run | Setups | Tasks | Effort | Reps | Notes |
|---|---|---|---|---|---|
| `20261026-202147` | opus-solo, routed | feature, file-bug, open-pr | default | 3 | `--permission-mode bypassPermissions` |
| `20261026-203713` | opus-solo, routed | feature | medium | 3 | `--permission-mode bypassPermissions` |
| `20261026-204057` | opus-solo, routed-opus | feature, file-bug, open-pr | medium | 3 | `--permission-mode bypassPermissions` |
| `20261026-233111` | opus-solo, routed-opus | file-bug-long, open-pr-long | medium | 1 | `--permission-mode auto`, ~106k-token warm-up |

Three other runs were discarded:
- One had a command allowlist that blocked the routed agents' `gh` calls.
- One was aborted with no output.
- One used `--resume` for the long-session tasks and hit a usage limit. Resuming also turned out to rebuild the prompt cache and report the session's cumulative cost, so the runner now keeps both messages in one live session instead.
