# Model routing (model-router plugin)

Delegate these kinds of work to the matching subagent instead of doing them yourself, so each runs on the model suited to it:

- Opening or updating a pull request → `model-router:pr-opener` (Haiku)
- Creating, pulling, reading or updating tickets/issues → `model-router:ticket-manager` (Sonnet)
- Designing an implementation plan for a non-trivial change → `model-router:planner` (Opus)
- Writing code, when you are not running on Opus yourself → `model-router:implementer` (Opus)

If you are already running on Opus, implement code directly rather than delegating to the implementer. Pass each subagent everything it needs in its prompt, since it doesn't see this conversation. An explicit request from the user to handle something differently overrides this routing.
