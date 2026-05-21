# Phase 5: Configuration (`.aibox.toml`)

## Goal

Add optional project-level config via `.aibox.toml` and define exactly how CLI flags compose with it. This is the last functional layer before polish.

## Context

From [`PROMPT.md`](../PROMPT.md):

```toml
ports = ["3000:3000", "8000:8000"]
env = ["NODE_ENV=development"]
env_files = [".env"]
shell = "/bin/bash"
docker_args = ["--add-host=host.docker.internal:host-gateway"]
```

Merge rules (MVP):

- Ports, env, env-files, docker_args: **CLI appends to config**.
- Shell: **CLI overrides config**.
- `aibox run` does not auto-create `.aibox.toml`.

We use `tomllib` (stdlib, Python 3.11+). If we drop to 3.10, this becomes `tomli` (the only justified runtime dep).

## Tasks

1. **`src/aibox/config.py`**:

   - `@dataclass class ProjectConfig` with fields: `ports: list[str]`, `env: list[str]`, `env_files: list[str]`, `shell: str | None`, `docker_args: list[str]`. All default to empty list / `None`.
   - `load(project_root: pathlib.Path) -> ProjectConfig` — returns an empty config if `.aibox.toml` doesn't exist; raises `ConfigError` (subclass `RuntimeError`) on parse failure or unknown top-level keys.
   - `merge(config: ProjectConfig, cli_args: Namespace) -> RunSpec` — produces the final `RunSpec`:
     - Lists: `config.ports + cli_args.ports` (and same for env, env_files, docker_args).
     - Shell: `cli_args.shell` if it differs from the argparse default, else `config.shell`, else `/bin/bash`.
     - User: pass through CLI `--user` value.

2. **Validation**:
   - Reject unknown top-level keys (typo protection).
   - Reject non-string entries in list fields.
   - Surface friendly errors: `"\.aibox\.toml: 'shell' must be a string, got int"`.

3. **CLI wiring**:
   - In `cmd_run`, replace the phase-4 stub with `config.load(identity.cwd)` then `config.merge(...)`.
   - Catch `ConfigError` and print/exit cleanly.

4. **Tests** (`tests/test_config.py`):
   - Empty / missing file → all defaults.
   - Each field round-trips correctly.
   - Unknown key raises `ConfigError`.
   - Type errors (e.g. `shell = 1`) raise `ConfigError` with a useful message.
   - Merge: CLI ports appended after config ports, in order.
   - Merge: CLI `--shell` overrides config `shell`.
   - Merge: when no CLI `--shell` provided, config `shell` wins; when neither provided, `/bin/bash` wins.

## Files created or modified

```
src/aibox/config.py            # implementation
tests/test_config.py           # new
src/aibox/cli.py               # wire config.load + config.merge into cmd_run
```

## Acceptance criteria

- All config tests pass.
- A project with a valid `.aibox.toml` containing ports and env_files starts a container with the corresponding `-p` and `--env-file` flags.
- A typo'd key (e.g. `port = ...` instead of `ports`) produces a clear single-line error, no stack trace.
- CLI flags compose with config per the merge rules above.

## Decisions to flag during plan mode

- The "CLI overrides config" rule for `--shell` requires distinguishing "user did not pass `--shell`" from "user passed `--shell /bin/bash`". Use `default=None` in argparse and apply the `/bin/bash` fallback in `merge`, not in argparse.
- Whether to validate that env entries look like `KEY=VALUE`. Default: no — pass through and let Docker complain. Avoids over-engineering.
