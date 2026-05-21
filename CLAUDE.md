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

When aibox prepares a project to run an AI agent inside the container, it should consider seeding the project root with:

- `claude-best-practices.md` — so any future Claude instance running in that project inherits the same working practices.
- A starter `.aibox.toml` (only when explicitly requested via something like `aibox init` — do not create it automatically on `aibox run`).

This is a non-MVP enhancement to keep in mind as the CLI evolves; the MVP should not write files into the host project automatically.

## Project Overview

`aibox` is a Python CLI tool that launches disposable, isolated Docker development containers from any local project directory. The primary use case is running Claude Code (or other AI coding agents) inside a sandboxed container where it can edit project files but cannot access host credentials, Git history, or remote repositories.

**Key security principles:**
- Containers are disposable; only user state persists in Docker volumes
- `.git` directory is hidden from containers (masked with tmpfs)
- Git and GitHub CLI are not installed in containers
- Host home directory is never mounted; only `/workspace`, `/home/dev`, `/tmp`, `/var/tmp`, `/opt` are visible
- No Docker socket, SSH keys, cloud credentials, or credential folders are mounted

## Architecture

The implementation uses a `src/` layout with these core modules:

- **`cli.py`**: Main entry point and argument parsing. Handles commands: `aibox`, `aibox run`, `aibox info`, `aibox remove-volume`, `aibox rebuild-image`
- **`identity.py`**: Project identity derivation. Creates stable project IDs from folder name + path hash (8-char hash of resolved absolute path)
- **`docker.py`**: Docker operations. Builds/manages the image, creates/runs containers with proper mounts and volumes
- **`config.py`**: Project-level configuration. Parses `.aibox.toml` for ports, env vars, env files, custom shell, Docker args

The Dockerfile template lives in `src/aibox/templates/Dockerfile` and is embedded/deployed by the CLI. The default image is `aibox-default:latest`.

## Project Structure

```
src/aibox/
  __init__.py
  cli.py           # Commands and argument parsing
  identity.py      # Project ID derivation
  docker.py        # Docker image/container management
  config.py        # .aibox.toml parsing
  templates/
    Dockerfile     # Default container image
```

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

Current project bind-mounted to `/workspace`. If `.git` exists on host, mask it with `--mount type=tmpfs,destination=/workspace/.git`.

### Docker Image Contents
Base: `python:3.12-slim`
- Non-root user `dev` with `/home/dev` as home
- User-local tool paths: `~/.npm-global/bin`, `~/.local/bin`, `/opt/bin` in PATH
- Tools: bash, curl, ca-certificates, build-essential, vim/nano, jq, ripgrep, fd-find, unzip, nodejs, npm
- **No Git, no GitHub CLI** (intentional — version control stays on host)

### Configuration (`.aibox.toml`)
Optional project-level config in the project root. Supports:
```toml
ports = ["3000:3000"]
env = ["NODE_ENV=development"]
env_files = [".env"]
shell = "/bin/bash"
docker_args = ["--add-host=host.docker.internal:host-gateway"]
```

CLI flags append to or override config values; `--shell` overrides config `shell`.

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
6. **Git safety**: Host `.git` must be masked. Do not add `--allow-git` unless trivial.
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
