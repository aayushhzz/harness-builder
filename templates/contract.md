# Contract

goal: <GOAL>
output: <OUTPUT>

scope:
- <SCOPE_GLOB>

never:
- <NEVER_GLOB>

done_when:
- [ ] <CRITERION_1> (test: <TEST_NAME_1>)
- [ ] <CRITERION_2> (test: <TEST_NAME_2>)
- [ ] Full suite green (test: harness/checks.sh)

Each task-specific test above must fail before the change and pass after it (`harness/checks.sh` must already pass before starting).

tools:
- <TOOL_1>

retry_cap: 2
budget_minutes: <BUDGET_MINUTES>
budget_tokens: <BUDGET_TOKENS>
escalation: <CONTACT>
