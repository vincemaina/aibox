# Phase 3: Docker Module

## Goal

Wrap all Docker CLI interactions in a single module with a narrow, testable surface. Define the default image's Dockerfile to spec, with the right tools and explicitly no Git.

## Context

The CLI shells out to `docker`. We never use the Docker SDK (would be a runtime dep) and never use `shell=True`. Every Docker call goes through this module so that tests can monkey-patch one boundary.

Key behaviours from [`PROMPT.md`](../PROMPT.md):

- Auto-build `aibox-default:latest` if missing.
- Bind-mount the project at `/workspace`.
- Mount four named volumes (home, tmp, var-tmp, opt).
- Mask `/workspace/.git` with tmpfs when the host has a `.git`.
- `--rm -it`, user `dev`, workdir `/workspace`, default command `/bin/bash`.
- Container is deleted on exit; volumes persist.

## Tasks

1. **`src/aibox/templates/Dockerfile`** — final version:

   - `FROM python:3.12-slim`.
   - `apt-get install` (single layer, `--no-install-recommends`, then clean lists): `bash`, `curl`, `ca-certificates`, `build-essential`, `vim`, `nano`, `jq`, `ripgrep`, `fd-find`, `unzip`, `nodejs`, `npm`.
   - **No** `git`, **no** `gh`.
   - Create user `dev` (`useradd -m -s /bin/bash dev`).
   - Create and chown `/home/dev/.npm-global`, `/home/dev/.local`, `/opt` to `dev`. Make `/opt` writable by `dev`.
   - `ENV HOME=/home/dev`, `NPM_CONFIG_PREFIX=/home/dev/.npm-global`, `PATH=/home/dev/.npm-global/bin:/home/dev/.local/bin:/opt/bin:$PATH`.
   - `USER dev`, `WORKDIR /workspace`, `CMD ["/bin/bash"]`.

2. **`src/aibox/docker.py`** — functions:

   - `class DockerError(RuntimeError)` — typed error so CLI can produce clean messages.
   - `check_available() -> None` — runs `docker version --format {{.Server.Version}}`; raises `DockerError` with a human-readable message if the binary is missing or the daemon is down.
   - `image_exists(name: str) -> bool` — `docker image inspect <name>`, return code-based.
   - `build_image(name: str, dockerfile_path: pathlib.Path, context_dir: pathlib.Path) -> None` — streams output to stdout/stderr, raises on non-zero.
   - `ensure_image(name: str) -> None` — `if not image_exists(name): build_image(...)`. Resolves the bundled Dockerfile via `importlib.resources` so it works after `pip install`.
   - `rebuild_image(name: str) -> None` — always rebuilds (no `--no-cache` by default; consider flag later).
   - `volume_exists(name: str) -> bool` — `docker volume inspect`.
   - `remove_volume(name: str) -> None` — `docker volume rm`; ignore "no such volume" but raise on other failures.
   - `RunSpec` dataclass — captures everything needed to start a container: identity, ports, env, env-files, docker_args, shell, user, mask_git.
   - `build_run_args(spec: RunSpec) -> list[str]` — pure function, returns the full `docker run ...` arg list. **All composition logic lives here** so tests can assert exact arg ordering without invoking Docker.
   - `run_container(spec: RunSpec) -> int` — invokes `docker run` via `subprocess.run` with `check=False`, returns the exit code (so the CLI can propagate it).

3. **Tests** (`tests/test_docker.py`):

   - `build_run_args` snapshot-style tests: cover the basic case, with ports, with env, with env-file, with custom shell, with `--docker-arg` passthrough, with `mask_git=True` adding the tmpfs flag and with `mask_git=False` omitting it, with `--user root` override.
   - Mock `subprocess.run` to test `image_exists` / `volume_exists` return-code handling.
   - Test that `ensure_image` short-circuits when image already exists.
   - Test that `check_available` raises `DockerError` (not stack trace) on a stubbed missing binary.

## Files created or modified

```
src/aibox/templates/Dockerfile     # full image
src/aibox/docker.py                # implementation
tests/test_docker.py               # new
```

## Acceptance criteria

- All docker-module tests pass without invoking real Docker.
- Building the image once locally (manually verified): `docker build -f src/aibox/templates/Dockerfile -t aibox-default:latest .` succeeds and the resulting image contains `node`, `npm`, `rg`, `fd`/`fdfind`, `jq`, but `which git` returns non-zero.
- `build_run_args` output for a representative spec matches the spec's required flags exactly, including `--rm -it --workdir /workspace --user dev`.

## Decisions to flag during plan mode

- Whether to suppress Docker build output or stream it. Default: stream so the user can see progress.
- Whether `rebuild-image` should use `--no-cache`. Default: no, user can force via a flag later.
