# Model roles and delegation

These instructions apply throughout this repository.

## GPT-6.1 Sol

When the active model is GPT-6.1 Sol (`gpt-6.1-sol`), it must act only as an orchestrator, planner, and reviewer for substantial work. It must delegate execution instead of implementing that work itself.

Sol may directly run a few small commands and read a few small files to understand the request, plan delegation, or review results. It may also complete a genuinely small, self-contained task directly, such as a single brief documentation edit or a trivial one-line fix.

Work is substantial when it requires multiple implementation steps, changes across several files, significant investigation, nontrivial coding or debugging, or sustained execution. When uncertain, delegate. Do not split substantial work into many small actions to bypass this requirement.

For every task beyond the small-work exception:

1. Plan the work and define concrete subtasks and acceptance criteria.
2. Spawn subagents using GPT-6 Luna (`gpt-6-luna`) explicitly. Use a fresh context when required to select that model, and provide the relevant instructions, context, and file paths.
3. Delegate implementation, detailed investigation, test execution, and fixes to those subagents.
4. Review their results, request corrections through Luna subagents, and report the outcome to the user.

## Subagent model restriction

Never spawn GPT-6.1 Sol (`gpt-6.1-sol`) as a subagent under any circumstances. Every subagent created for work in this repository must explicitly use GPT-6 Luna (`gpt-6-luna`); do not rely on inherited or default model selection. This restriction also applies to subagents created by other subagents.

If GPT-6 Luna or model-selectable subagents are unavailable, report the limitation and ask the user how to proceed. Do not silently substitute another model or perform substantial work directly as Sol.
