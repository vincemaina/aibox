# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Working Practices

Always follow the conventions in [`claude-best-practices.md`](./claude-best-practices.md). Key practices to apply throughout this project:

- **CLAUDE.md in every subfolder**: Each directory should have its own `CLAUDE.md` describing the files and subfolders within it. Add a test that enforces this.
- **Plan before coding**: Use plan mode, and commit plan/roadmap docs to git so decisions are logged. Tightly couple roadmaps (actionable steps) to plans (full context briefs).
- **Roadmaps**: Maintain a top-level `ROADMAP.md` that links to feature- or phase-specific roadmap files.
- **Web research first**: Before touching unfamiliar tools/APIs/packages, do web research. Capture what you learn as a reusable skill where appropriate.
- **Test suites enforce practices**: Tests aren't just for code — use them to enforce Claude working practices (e.g. verifying every folder has a `CLAUDE.md`).
- **Small focused files + summaries**: Keep files small and let CLAUDE.md summaries provide orientation, so context windows stay efficient.
- **Subagents for parallel work**: Spawn subagents (and use worktrees when not running under Docker) to keep each context window focused on one task.
- **Definition of done**: Treat a task as done only when code compiles, tests pass, and any end-to-end check succeeds. Self-verify before reporting completion.

### aibox should deploy these practices into target projects

Implemented in phase 10. `aibox init` merges a template's `workspace/` into the project root (`claude-best-practices.md`, `CLAUDE.md`, a starter `.aibox.toml`, skills), and a template's `home/` syncs into the container's `/home/dev` on every `aibox run`.

The rule that governed the design still holds: **`aibox run` never writes to the host project.** Only the explicit `aibox init` touches the user's source tree, and it never overwrites without consent. The `home/` half is exempt because it lands on an aibox-managed Docker volume, not in the repo.

## Project Overview

`aibox` is a Python CLI tool that launches disposable, isolated Docker development containers from any local project directory. The primary use case is running Claude Code (or other AI coding agents) inside a sandboxed container where it can edit project files but cannot access host credentials, Git history, or remote repositories.

**Key security principles:**
- Containers are disposable; only user state persists in Docker volumes
- The agent may read history and commit locally by default (`--git commit`); `--git readonly` and `--git masked` dial that back. What is never permitted is host-side code execution: `.git/hooks` and `.git/config` are frozen in every mode. See [`plans/phase-9-git-access.md`](./plans/phase-9-git-access.md)
- `git` IS installed (agents need it to clone public repos and install Claude Code plugins/marketplaces), but the GitHub CLI (`gh`) is not, and no credentials are mounted — so the agent cannot authenticate to or push to remotes. Protecting shared history is the remote's job, via branch protection
- Host home directory is never mounted; only `/workspace`, `/home/dev`, `/tmp`, `/var/tmp`, `/opt` are visible
- No Docker socket, SSH keys, cloud credentials, or credential folders are mounted

## Architecture

The implementation uses a `src/` layout with these core modules:

- **`cli.py`**: Main entry point and argument parsing. Handles commands: `aibox`, `aibox run`, `aibox info`, `aibox remove-volume`, `aibox rebuild-image`. `aibox run` takes `--git` alongside the port/env/shell flags
- **`identity.py`**: Project identity derivation. Creates stable project IDs from folder name + path hash (8-char hash of resolved absolute path)
- **`docker.py`**: Docker operations. Builds/manages the image, creates/runs containers with proper mounts and volumes
- **`config.py`**: Project-level configuration. Parses `.aibox.toml` for ports, env vars, env files, custom shell, Docker args

- **`userconfig.py`**: User-level config (`~/.config/aibox/config.toml`, XDG-aware). Currently just `templates`
- **`templates.py`**: Project templates — resolve a git URL or local path, merge `workspace/` into the project, stage `home/` for the container to seed `/home/dev`

The Dockerfile lives in `src/aibox/image/Dockerfile` and is embedded/deployed by the CLI. The default image is `aibox-default:latest`.

## Project Structure

```
src/aibox/
  __init__.py
  cli.py           # Commands and argument parsing
  identity.py      # Project ID derivation
  docker.py        # Docker image/container management
  config.py        # .aibox.toml parsing
  userconfig.py    # ~/.config/aibox/config.toml parsing
  templates.py     # Project templates: fetch, merge, stage
  image/
    Dockerfile     # Default container image
    entrypoint.sh  # UID/GID retune, gosu drop, template home seeding
```

Note `image/` was called `templates/` before phase 10; it was renamed so it
wouldn't sit next to the unrelated `templates.py`.

## Key Implementation Details

### Project Naming
- **Project ID format**: `{folder-slug}-{8-char-path-hash}`
  - Example: `my-project-a1b2c3d4`
- **Docker image**: `aibox-default:latest` (shared across all projects)
- **Container names**: `aibox-{project-id}-{timestamp}-{random}` (unique per session)
- **Volumes**: `aibox-{home|tmp|var-tmp|opt}-{project-id}`

### Docker Mounts
Use project-specific named volumes for persistence:
```
aibox-home-{project-id}    → /home/dev
aibox-tmp-{project-id}     → /tmp
aibox-var-tmp-{project-id} → /var/tmp
aibox-opt-{project-id}     → /opt
```

Current project bind-mounted to `/workspace`. If `.git` exists on the host, extra mounts are layered on top per the `--git` mode — see `docker._git_mount_args` and `plans/phase-9-git-access.md`.

### Docker Image Contents
Base: `python:3.12-slim`
- Non-root user `dev` with `/home/dev` as home
- User-local tool paths: `~/.npm-global/bin`, `~/.local/bin`, `/opt/bin` in PATH
- Tools: bash, curl, ca-certificates, build-essential, vim/nano, jq, ripgrep, fd-find, unzip, xz-utils, git, gosu
- Node.js from the official nodejs.org tarball (pinned via the `NODE_VERSION` build arg, checksum-verified against `SHASUMS256.txt`), **not** Debian's `nodejs` package. Debian ships v20, but Claude Code requires `node >=22`. Bump `NODE_VERSION` in the Dockerfile to move Node versions.
- Chromium's system libraries, via `npx playwright@$PLAYWRIGHT_VERSION install-deps chromium` at build time. Browser *binaries* are not baked in — the agent runs `npx playwright install chromium` itself, which needs no root and caches to `~/.cache/ms-playwright` on the home volume. The libs must be in the image because installing them needs apt/root and the container runs as `dev` with no sudo. Let Playwright resolve the package names; Debian 13's `t64` renames would rot a hardcoded apt list.
- `/etc/profile.d/aibox-path.sh` re-adds the user-local tool paths. `ENV PATH` alone is insufficient because `/etc/profile` assigns `PATH` outright, so login shells (`bash -l`, `su -`) would otherwise lose globally-installed tools like `claude`.
- **git included, `gh` excluded.** git lets agents clone public repos / install plugins. Without `gh` or mounted credentials the agent still can't push to or authenticate against remotes. The host `.git` is masked at runtime so history stays protected.

### Configuration (`.aibox.toml`)
Optional project-level config in the project root. Supports:
```toml
ports = ["3000:3000"]
env = ["NODE_ENV=development"]
env_files = [".env"]
shell = "/bin/bash"
git = "commit"   # "commit" (default) | "readonly" | "masked"
docker_args = ["--add-host=host.docker.internal:host-gateway"]
```

CLI flags append to or override config values; `--shell` and `--git` override config `shell` and `git`.

### Container Runtime
- User: `dev` (or `--user` override)
- Workdir: `/workspace`
- Command: `/bin/bash` (or `--shell` override)
- Flags: `--rm -it`
- Exit behavior: Container is removed; volumes persist

## Important Constraints & Design Principles

1. **Minimal dependencies**: Use only Python standard library unless there is a very strong reason not to.
2. **No shell=True**: Always use `subprocess.run([...])` with argument lists for safety.
3. **Readable over clever**: Prefer straightforward, maintainable Python.
4. **Cross-platform**: macOS, Linux, and Windows are all supported. The container is always Linux regardless of host. UID handling on Linux uses an entrypoint script that retunes the `dev` user via gosu.
5. **Credential safety**: Strict enforcement — no host home directory mounting.
6. **Git safety**: The boundary is the *host*, not the history. The agent commits locally by default; safety comes from the absence of credentials/`gh` (so it can't push) plus frozen `.git/hooks` and `.git/config` (so it can't make host git run its code). Never relax those two, in any mode.
7. **Container disposability**: Image/Dockerfile define system environment; container filesystem is ephemeral.

## Development Commands (to be established)

Once the project is set up with `pyproject.toml`:

```bash
pip install -e .          # Install CLI locally in editable mode
aibox                     # Run from any project directory
aibox info                # Show project details
aibox remove-volume       # Remove persistent volumes
aibox rebuild-image       # Rebuild the default Docker image
```

Testing, linting, and formatting commands to be defined as the project evolves.

## Error Handling

Handle expected errors cleanly without stack traces:
- Docker not installed or not running
- Image build failures
- Volume removal failures
- Docker run failures (return Docker exit code)

Return clear, user-friendly messages for these cases.

## References

- Working practices: [`claude-best-practices.md`](./claude-best-practices.md)
- Full specification: [`PROMPT.md`](./PROMPT.md)
- Target base image: `python:3.12-slim`
- Docker CLI args reference: Use standard Docker flags
