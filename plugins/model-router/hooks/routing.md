# Model routing (model-router plugin)

Subagents on cheaper models can take over chores, but each one starts with an empty context. Handing work over also costs you turns: writing the agent's instructions, then reading and checking its result. Delegate only when that overhead is smaller than doing the work yourself:

- **Opening or updating a pull request** → `model-router:pr-opener` (Haiku). Worth it when this session's context is already large or the PR involves several steps (branching, committing, pushing). In a short session, do it yourself.
- **Creating, pulling or updating tickets/issues** → `model-router:ticket-manager` (Sonnet). Same rule. A single quick `gh issue` call is cheaper done directly.
- **Designing an implementation plan for a non-trivial change** → `model-router:planner` (Opus).
- **Writing code** → only delegate to `model-router:implementer` (Opus) if you are not running on Opus yourself. If you are on Opus, implement directly.

Pass each subagent everything it needs in its prompt, since it doesn't see this conversation. An explicit request from the user to handle something differently overrides this routing.
