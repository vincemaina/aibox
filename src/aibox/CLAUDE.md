# src/aibox/

The `aibox` Python package. Modules:

- `cli.py` — argparse entry point. Dispatches to subcommand handlers (`cmd_run`, `cmd_init`, `cmd_setup`, `cmd_info`, `cmd_remove_volume`, `cmd_rebuild_image`).
- `onboarding.py` — the two interactive flows: first-run template setup, and the per-project import offer.
- `identity.py` — project ID, container name, image name, volume name, git-dir derivation. Pure functions only.
- `docker.py` — wraps every `docker` CLI invocation.
- `config.py` — project-level `.aibox.toml` loader and CLI/config merge logic.
- `userconfig.py` — user-level `~/.config/aibox/config.toml` loader, plus config/cache dir resolution.
- `templates.py` — project templates: resolve a ref, merge `workspace/` into the project, stage `home/` for the container.
- `image/` — Dockerfile and entrypoint for the default image. See its own `CLAUDE.md`.

## Conventions

- Standard library only at runtime. No runtime dependencies.
- Never use `shell=True`. Always pass argument lists to `subprocess.run`.
- `identity.py` is pure. `config.py` / `userconfig.py` do no I/O beyond reading their config file.
- Subprocess use is confined to two modules, split by the binary they own:
  `docker.py` owns every `docker` invocation, `templates.py` owns every `git`
  invocation. Nothing else shells out.
- `build_run_args` must stay a pure function of `RunSpec` — filesystem lookups
  belong in `identity.resolve` or the CLI, so the arg composition stays snapshot-testable.
- **Interactive code must never block a non-interactive run.** Anything that
  prompts checks `onboarding.interactive()` first and degrades to a safe default.
  A hang in CI is worse than a missed prompt. Tests assert this per flow.
- `userconfig` holds two separate things: **config** the user hand-edits, and
  **state** aibox rewrites (declined import offers). Different directories, so
  clearing state never destroys settings.
- Errors that should be user-visible inherit from a typed exception (e.g. `DockerError`, `ConfigError`) and are caught at the CLI boundary in `cli.py` so end users never see a stack trace.

## Phase status

See [`../../ROADMAP.md`](../../ROADMAP.md). Modules are filled in across phases 2–5; phase 1 leaves them as docstring-only placeholders.
