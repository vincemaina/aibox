# src/aibox/

The `aibox` Python package. Modules:

- `cli.py` — argparse entry point. Dispatches to subcommand handlers (`cmd_run`, `cmd_info`, `cmd_remove_volume`, `cmd_rebuild_image`).
- `identity.py` — project ID, container name, image name, volume name derivation. Pure functions only.
- `docker.py` — wraps every `docker` CLI invocation. All `subprocess.run` calls in the project live here.
- `config.py` — `.aibox.toml` loader and CLI/config merge logic.
- `templates/Dockerfile` — default container image, shipped as package data via `[tool.setuptools.package-data]`.

## Conventions

- Standard library only at runtime. No runtime dependencies.
- Never use `shell=True`. Always pass argument lists to `subprocess.run`.
- `identity.py` and `config.py` are pure — no I/O beyond reading the config file from disk.
- `docker.py` is the only module that shells out to external binaries.
- Errors that should be user-visible inherit from a typed exception (e.g. `DockerError`, `ConfigError`) and are caught at the CLI boundary in `cli.py` so end users never see a stack trace.

## Phase status

See [`../../ROADMAP.md`](../../ROADMAP.md). Modules are filled in across phases 2–5; phase 1 leaves them as docstring-only placeholders.
