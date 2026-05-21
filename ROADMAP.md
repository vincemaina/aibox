# aibox Roadmap

High-level plan for building the `aibox` CLI. See [`PROMPT.md`](./PROMPT.md) for the full specification and [`CLAUDE.md`](./CLAUDE.md) for working practices.

## Phases

| #  | Phase                                              | Status   | Summary                                                                 |
|----|----------------------------------------------------|----------|-------------------------------------------------------------------------|
| 1  | [Scaffolding](./plans/phase-1-scaffolding.md)      | Done        | `pyproject.toml`, `src/` layout, entry point, test infrastructure.   |
| 2  | [Identity](./plans/phase-2-identity.md)            | Not started | Project ID, container name, image name, volume name derivation.      |
| 3  | [Docker module](./plans/phase-3-docker.md)         | Not started | Image build/check, container run, volume management, Dockerfile.     |
| 4  | [CLI commands](./plans/phase-4-cli-commands.md)    | Not started | `run`, `info`, `remove-volume`, `rebuild-image`, all flags.          |
| 5  | [Config](./plans/phase-5-config.md)                | Not started | `.aibox.toml` parsing and CLI merge rules.                           |
| 6  | [Polish](./plans/phase-6-polish.md)                | Not started | Error handling, README, end-to-end tests, subfolder CLAUDE.md files. |

## Guiding principles

These shape every phase. Full context in [`CLAUDE.md`](./CLAUDE.md) and [`claude-best-practices.md`](./claude-best-practices.md).

- **Stdlib only** unless there's a very strong reason otherwise (per [`PROMPT.md`](./PROMPT.md)).
- **No `shell=True`** — always pass argument lists to `subprocess.run`.
- **macOS-first** — don't burn time on Windows path edge cases.
- **Security non-negotiables** — no host home mount, no Docker socket, no SSH/cloud/dbt credentials, `.git` masked, no Git/GitHub CLI in image.
- **Boring code beats clever code** — readability and maintainability over abstraction.
- **Tests enforce practices** — at minimum, a test that every directory has a `CLAUDE.md` (per [`claude-best-practices.md`](./claude-best-practices.md)).

## Definition of done (project level)

Project is done when the acceptance criteria in `PROMPT.md` all pass:

- `pip install -e .` exposes a global `aibox` command.
- Running `aibox` from any project starts an interactive container with the project at `/workspace`.
- The four named volumes persist across runs and are project-specific.
- The host `.git` is masked when present.
- Git/GitHub CLI are absent from the image.
- No host credentials are mounted.
- `aibox info`, `aibox remove-volume`, and `aibox rebuild-image` behave per spec.
- README explains install, usage, what's mounted/persisted, why `.git` is hidden, why credentials aren't mounted, and how to manage volumes/images.

## How to use this roadmap

1. Pick the next phase whose status is `Not started`.
2. Open its plan file. Read context, tasks, files, and acceptance criteria.
3. Use plan mode in Claude Code to align on approach before any code changes.
4. Implement, run tests, self-verify against the phase's acceptance criteria.
5. Update the phase's status in this table to `Done` and move on.

If a plan turns out to be wrong as you work, update the plan file in the same commit as the code change — the plan is a living artifact, not a museum piece.
