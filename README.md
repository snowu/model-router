# model-router

A Claude Code plugin that runs each kind of work on the model suited to it. Chores go to cheaper models and thinking goes to Opus.

| Work | Subagent | Model |
|---|---|---|
| Opening or updating PRs | `model-router:pr-opener` | Haiku |
| Creating, pulling or updating tickets | `model-router:ticket-manager` | Sonnet |
| Implementation plans | `model-router:planner` | Opus (high effort) |
| Writing code, when the main session isn't Opus | `model-router:implementer` | Opus |

A `SessionStart` hook adds a short routing note to every session, so Claude delegates to these agents without being asked.

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

## Use

Ask as you normally would ("open a PR for this", "pull ticket ABC-123", "plan out the auth refactor"), and Claude hands the work to the matching agent. You can also call one directly with `@agent-model-router:planner`.

The ticket agent uses whichever tracker MCP server is connected (Jira, Linear and so on), and falls back to `gh issue`.

## Customize

- **Change a model**: edit the `model:` line in `plugins/model-router/agents/<agent>.md`. It accepts `haiku`, `sonnet`, `opus`, `fable`, a full model ID, or `inherit`.
- **Change when Claude delegates**: edit `plugins/model-router/hooks/routing.md`.
- **Force every subagent onto one model**: set `CLAUDE_CODE_SUBAGENT_MODEL`. Note that a `model:` set in an agent's frontmatter takes precedence over it.

## Limits

Routing is guidance, not enforcement. Claude usually delegates, but it can still do a task itself. The main session stays on whatever model you picked with `/model`. A good setup is Sonnet as the main model, so plans and code go up to Opus and PRs go down to Haiku. Another is Opus as the main model, which delegates only the chores.

## License

MIT
