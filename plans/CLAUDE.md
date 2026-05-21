# plans/

One markdown plan per development phase. Indexed by [`../ROADMAP.md`](../ROADMAP.md).

## Plan structure

Each plan follows the same shape:

1. **Goal** — one-sentence outcome.
2. **Context** — dependencies, prior work, background.
3. **Tasks** — concrete, ordered, actionable steps.
4. **Files created or modified** — explicit list.
5. **Acceptance criteria** — how we know the phase is done.
6. **Decisions to flag during plan mode** — open questions worth raising before coding.

## Lifecycle

- Before starting a phase, re-enter plan mode in Claude Code, read the relevant plan, and align on the **Decisions to flag** section.
- Update the plan in the same commit as the code if the plan turns out to be wrong. Plans are living docs, not history.
- When a phase is complete, update its status in `ROADMAP.md` to `Done`.

## Files

- `phase-1-scaffolding.md`
- `phase-2-identity.md`
- `phase-3-docker.md`
- `phase-4-cli-commands.md`
- `phase-5-config.md`
- `phase-6-polish.md`

A test (`tests/test_repo_structure.py`) asserts every `phase-*.md` here is referenced from `ROADMAP.md`, so adding a new plan without indexing it will fail CI.
