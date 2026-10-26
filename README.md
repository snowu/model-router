# model-router

A Claude Code plugin that sends each kind of work to a model suited to it, plus a benchmark that measures whether doing so saves money.

**The short answer: mostly it doesn't.** In a short session, handing chores to cheaper models costs more than letting Opus do them. Late in a long session it roughly breaks even. What lowered cost in these tests was doing chores in a **fresh session** and choosing a cheaper **main model**. Details are in [Findings](#findings).

## What's in the plugin

| Work | Subagent | Model |
|---|---|---|
| Opening or updating PRs | `model-router:pr-opener` | Haiku |
| Creating, pulling or updating tickets | `model-router:ticket-manager` | Sonnet |
| Implementation plans | `model-router:planner` | Opus (medium effort) |
| Writing code, when the main session isn't Opus | `model-router:implementer` | Opus (medium effort) |

A `SessionStart` hook adds a short routing note to each session ([`hooks/routing.md`](plugins/model-router/hooks/routing.md)). It tells Claude to hand PRs and tickets to these agents only when the session's context is already large or the chore takes several steps, since that's the only case where the benchmark showed a saving.

## Install

```bash
claude plugin marketplace add snowu/model-router
claude plugin install model-router@model-router
```

Or, inside a session:

```
/plugin marketplace add snowu/model-router
/plugin install model-router@model-router
```

You can also call an agent directly: `@agent-model-router:planner`. The ticket agent uses whichever tracker MCP server is connected (Jira, Linear and so on), and falls back to `gh issue`.

## Findings

Each benchmark run gives Claude a task in a throwaway sandbox (see [Benchmark](#benchmark)) and grades the result, including with hidden tests. Every run counted below passed, so neither setup saved money by doing the job worse. Costs are Claude Code's own per-model numbers at list price, subagents included.

The setups:
- **opus-solo**: Opus does everything.
- **routed**: Sonnet as the main model, with this plugin.
- **routed-opus**: Opus as the main model, handing PRs and tickets down.

**Fresh session**, medium effort, mean of 3 runs:

| Task | opus-solo | routed | routed-opus |
|---|---|---|---|
| Ticket → plan → implement → PR | $0.149 | $0.208 (+40%) | $0.220 (+50%) |
| File a bug ticket | $0.094 | — | $0.173 (+84%) |
| Open a PR for finished changes | $0.098 | — | $0.121 (+23%) |

At Claude Code's default effort, `routed` was cheaper on the two chores: −22% on the bug ticket and −42% on the PR. That saving came from **Sonnet running the main session**. The subagents themselves cost almost nothing, with Haiku at under a cent per PR.

**Late in a long session** (~106k tokens of code already read), medium effort, 1 run each:

| Task | opus-solo | routed-opus |
|---|---|---|
| File a bug ticket | $0.223 | $0.290 (+30%) |
| Open a PR for finished changes | $0.402 | $0.314 (−22%) |

**Why routing rarely pays**
- **Context, not output, drives the cost.** A chore costs little to *write*. The expense is every turn re-reading the session's context. The same PR cost $0.10 in a fresh session and $0.40 in a long one.
- **Handing work over costs something on both sides.** The subagent starts cold and rebuilds its context. Opus still spends turns writing the instructions and checking the result. In a fresh session that costs more than Opus doing the chore itself.
- **A long session changes the balance.** There, every Opus turn is expensive, so a multi-step chore done by Haiku saves money. A short one still doesn't.

**What actually lowered cost in these tests**
1. **Doing chores in a fresh session** (or after `/clear`): a PR cost $0.10 instead of $0.40.
2. **Running the main session on Sonnet** for housekeeping work: 22–42% cheaper on chores.
3. **Routing multi-step chores late in long sessions**: about 20% cheaper, but measured on one run only.

Subagents are still useful for keeping noise out of the main context and for running work in parallel. Those are reasons other than cost.

**Limits:** the sample project is small and synthetic, there are only 1–3 runs per cell, and costs vary by about ±20% between identical runs. Raw data is in [`bench/results/`](bench/results/).

## Benchmark

`bench/` runs the same tasks under each setup:
- **Sandbox:** every run gets a copy of a small Python project, a local bare repo as `origin`, and a fake `gh` that serves a canned ticket and records `issue create` / `pr create` calls. Nothing reaches GitHub.
- **Long-session tasks (`*-long`):** the session first reads ~106k tokens of generated code, then gets the chore as a second message in the same live session. Only the second message's cost is counted.

```bash
python3 bench/run.py --reps 3 --effort medium                      # short tasks: opus-solo vs routed
python3 bench/run.py --configs opus-solo,routed-opus --effort medium \
    --tasks file-bug-long,open-pr-long --budget 5                    # long-session tasks (~$2 per run)
python3 bench/report.py                                             # latest run's summary
```

Sessions run with `--permission-mode bypassPermissions` by default. A command allowlist would penalize whichever model phrases its shell commands differently. Pass `--permission-mode auto` to keep Claude Code's safety classifier on. Each run is capped by `--budget` (USD, default 3).

Headless runs count against your plan's usage like any other session. The long-session warm-ups are the expensive part, at about $1.70 each.

## Customize

- **Change a model:** edit the `model:` line in `plugins/model-router/agents/<agent>.md`. It accepts `haiku`, `sonnet`, `opus`, `fable`, a full model ID, or `inherit`.
- **Change when Claude delegates:** edit `plugins/model-router/hooks/routing.md`.
- **Add your own setup to the benchmark:** add an entry to `CONFIGS` in `bench/run.py`.

## License

MIT
