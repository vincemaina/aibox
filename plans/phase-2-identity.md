# Phase 2: Project Identity

## Goal

Implement deterministic, collision-resistant naming for project IDs, container names, image names, and volume names. This is the foundation for everything else: phase 3 needs these names to mount volumes correctly; phase 4 needs them to print `aibox info`.

## Context

From [`PROMPT.md`](../PROMPT.md):

- Project ID = `{folder-slug}-{8-char-hash-of-absolute-path}`.
- Hash the **resolved absolute** path so two projects with the same folder name don't collide.
- Container name = `aibox-{project-id}-{timestamp}-{short-random}` — unique per session, so two terminals can share volumes but have distinct containers.
- Volumes are stable per project; image name is global (`aibox-default:latest`).

## Tasks

1. **`src/aibox/identity.py`** — pure functions, no I/O beyond resolving paths:

   - `slugify(name: str) -> str`
     - Lowercase, ASCII-only, replace runs of non-alphanumeric with `-`, strip leading/trailing `-`. Empty → `project`.
   - `path_hash(path: pathlib.Path) -> str`
     - SHA-256 of the resolved absolute path bytes, first 8 hex chars.
   - `project_id(cwd: pathlib.Path) -> str`
     - `f"{slugify(cwd.name)}-{path_hash(cwd)}"`.
   - `image_name() -> str` → `"aibox-default:latest"`.
   - `volume_names(project_id: str) -> dict[str, str]`
     - Returns `{"home": "aibox-home-...", "tmp": "...", "var_tmp": "...", "opt": "..."}`.
   - `container_name(project_id: str, now: datetime | None = None, rand: str | None = None) -> str`
     - `f"aibox-{project_id}-{YYYYMMDD-HHMMSS}-{6-char-hex}"`.
     - Accept injectable `now` and `rand` so tests are deterministic.
   - `ProjectIdentity` dataclass (frozen) bundling `cwd`, `project_id`, `image`, `container`, `volumes`, and `git_present: bool` — used as the canonical handoff to `docker.py` and `cli.py`.
   - `resolve(cwd: pathlib.Path | None = None) -> ProjectIdentity` — top-level constructor.

2. **Tests** (`tests/test_identity.py`):

   - `slugify` covers spaces, underscores, mixed case, Unicode, empty, all-symbols.
   - `path_hash` is stable across calls and differs for different paths.
   - `project_id` is stable across calls for the same path and changes when the path changes.
   - Two projects with the same folder name but different parent dirs get different project IDs.
   - `container_name` produces unique names for two calls in the same second (random suffix differs).
   - `volume_names` keys match the four expected mount points.
   - `resolve` populates `git_present=True` when a `.git` dir exists, `False` otherwise — use `tempfile.TemporaryDirectory` to test both.

## Files created or modified

```
src/aibox/identity.py        # implementation
tests/test_identity.py       # new
```

## Acceptance criteria

- All identity tests pass with `pytest`.
- Calling `identity.resolve()` from two different directories returns different `project_id`s.
- Calling `identity.resolve()` twice from the same directory returns the same `project_id` and the same volume names — but a **different** container name.
- Folder names with spaces, capitals, and symbols slugify cleanly (e.g. `My Project!` → `my-project`).

## Decisions to flag during plan mode

- 8-char SHA-256 prefix is fine for collision resistance at the scale of one user's projects. If the user wants something shorter/longer, change here.
- Timestamp format in container names: `YYYYMMDD-HHMMSS` matches the spec example. Confirm before locking in.
