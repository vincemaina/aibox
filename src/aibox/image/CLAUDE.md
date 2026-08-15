# src/aibox/image/

Build inputs for the default container image (`aibox-default:latest`), shipped as
package data via `[tool.setuptools.package-data]` in `pyproject.toml`.

Named `image/` rather than `templates/` since phase 10 — `aibox.templates` is now
the *project template* module, and two things called "templates" next to each
other was a trap.

## Files

- `Dockerfile` — the default image. `docker.py` locates it with
  `importlib.resources.files("aibox.image")`, so this directory must stay an
  importable package (`__init__.py`) and stay listed in `package-data`.
- `entrypoint.sh` — runs as PID 1. Retunes the `dev` user to `HOST_UID`/`HOST_GID`
  and drops privileges via gosu on Linux; seeds template `home/` content from
  `/run/aibox-seed`.
- `agent-briefing.md` — orientation doc seeded to `~/.claude/CLAUDE.md` in every
  box, so agents know they're in a container and not on the user's machine. Copied
  by `templates.stage_home_seed`, not baked into the image — a volume only inherits
  image content when it's empty, so baking it would miss existing projects. Edit
  it and the next `aibox run` picks it up; no rebuild needed.

## Conventions

- Pinned versions live in `ARG`s (`NODE_VERSION`, `PLAYWRIGHT_VERSION`) so bumps
  are a one-line change.
- Anything added here costs every project — the image is shared. Weigh size.
- `entrypoint.sh` must handle both the root path (Linux, gosu drop) and the
  already-`dev` path (macOS/Windows). Logic added to only one branch is a bug
  that shows up on one platform.
- Changes here need `aibox rebuild-image` to take effect; existing containers
  and images are not rebuilt automatically.
