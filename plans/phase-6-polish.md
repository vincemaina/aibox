# Phase 6: Polish

## Goal

Bring the project up to the spec's acceptance criteria for shipping the MVP: a real README, polished error messages, the subfolder-CLAUDE.md test enforced, and a manual end-to-end checklist run on macOS.

## Context

By this phase the code works. This phase is about making it pleasant to use, easy to onboard onto, and resistant to regressions.

## Tasks

1. **`README.md`** — covers everything from [`PROMPT.md`](../PROMPT.md)'s README requirements:

   - What `aibox` is and what problem it solves.
   - Install: `pip install -e .`.
   - Basic usage: `cd my-project && aibox`.
   - What gets mounted (`/workspace` bind + four named volumes).
   - What persists across runs (the four volumes).
   - What doesn't persist (everything else in the container filesystem).
   - Why `.git` is hidden — host stays the source of truth for version control.
   - Why Git and GitHub CLI aren't installed — Claude shouldn't be touching remote repos or commit history.
   - Why host credentials aren't mounted — explicit list of what isn't visible (SSH, dbt, Snowflake, GitHub, cloud).
   - Example `.aibox.toml`.
   - `aibox info`, `aibox remove-volume`, `aibox rebuild-image` examples.
   - Limitations / non-goals (call out: no Compose, no custom images, no Docker socket, no GitHub, no Claude pre-installed).

2. **Error message audit**:

   - Walk each error path and confirm: no stack trace, message names the cause and the fix.
   - "Docker is not running. Start Docker Desktop and try again." > "ConnectionRefusedError".
   - "Image build failed — see Docker output above." > Python traceback.
   - Volume removal "no such volume" silently skipped, only real failures surface.

3. **Working-practice tests**:

   - Confirm `tests/test_repo_structure.py` (from phase 1) still passes and now covers the new directories (`plans/`, etc.).
   - Add a test that asserts `ROADMAP.md` lists every plan file under `plans/` (catches a plan being added without being indexed).

4. **End-to-end manual checklist** (run on macOS, document the results in the PR/commit message):

   - [ ] Fresh checkout, `pip install -e .`, `aibox --help` works.
   - [ ] In a sample project: `aibox` builds the image and drops into a bash shell at `/workspace`.
   - [ ] `ls /workspace` shows project files; editing a file is reflected on the host.
   - [ ] `ls -la /workspace/.git` shows an empty tmpfs (or no `.git` if host has none).
   - [ ] `which git` inside the container returns nothing.
   - [ ] Installing an npm tool persists across runs (test by exiting and re-entering).
   - [ ] Two terminals running `aibox` in the same project work simultaneously — each has its own container, shared volumes.
   - [ ] `aibox info` prints the expected names.
   - [ ] `aibox remove-volume --force` removes the four project volumes.
   - [ ] `aibox rebuild-image` rebuilds the image.
   - [ ] No host credentials visible: `ls ~/.ssh`, `ls ~/.dbt`, etc. all empty/missing inside the container.

5. **Update `ROADMAP.md`**:
   - Set every phase status to `Done`.
   - Add a short "Future work" section listing the non-MVP items from `PROMPT.md` (Compose, custom images, Docker socket, GitHub integration, etc.) plus the "aibox seeds claude-best-practices.md into target projects" idea from `CLAUDE.md`.

## Files created or modified

```
README.md                              # new, per spec section
tests/test_repo_structure.py           # extend to check ROADMAP indexes plans
ROADMAP.md                             # statuses + future work
src/aibox/*.py                         # error message tweaks as needed
```

## Acceptance criteria

- All spec acceptance criteria from `PROMPT.md` pass via the manual checklist.
- `pytest` is green.
- `README.md` covers every required section.
- No user-facing error path produces a raw Python traceback.

## Decisions to flag during plan mode

- Whether to add a screenshot/asciinema demo to the README. MVP: skip, keep README text-only.
- Whether the "Future work" section should split out a separate `BACKLOG.md`. MVP: keep it inside `ROADMAP.md` to avoid yet another file.
