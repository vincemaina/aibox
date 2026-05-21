# Phase 4: CLI Commands

## Goal

Wire the identity and docker modules into a working `aibox` CLI. After this phase, the spec's primary workflow (`cd project && aibox`) should work end to end (config support comes in phase 5).

## Context

The CLI is a thin orchestration layer:

1. Resolve project identity (phase 2).
2. Optionally load `.aibox.toml` (phase 5 — stubbed here).
3. Compose a `RunSpec` (phase 3).
4. Print the startup summary.
5. Delegate to `docker.run_container`.
6. Return the container's exit code as the CLI exit code.

`argparse` from stdlib is enough — no `click`, no `typer`.

## Tasks

1. **Argument parsing** in `src/aibox/cli.py`:

   - Top-level parser with subparsers: `run`, `info`, `remove-volume`, `rebuild-image`.
   - If no subcommand is given, default to `run` (matches `aibox` ≡ `aibox run`).
   - `run` flags:
     - `-p/--port` (repeatable, `action="append"`)
     - `-e/--env` (repeatable)
     - `--env-file` (repeatable)
     - `--shell` (single, default `"/bin/bash"`)
     - `--docker-arg` (repeatable, raw passthrough)
     - `--user` (single, default `"dev"`)
   - `remove-volume` flag: `--force`.

2. **Commands**:

   - `cmd_run(args)`:
     1. `identity.resolve()`.
     2. (Phase 5 hook) Load `.aibox.toml` and merge with `args`. For phase 4, just use CLI args directly.
     3. `docker.check_available()`.
     4. `docker.ensure_image(identity.image)`.
     5. Build `RunSpec`.
     6. Print startup summary (see format in `PROMPT.md`).
     7. Return `docker.run_container(spec)` as the exit code.
   - `cmd_info(args)`:
     - `identity.resolve()`, print the same fields in the same format as the startup summary, without launching anything.
   - `cmd_remove_volume(args)`:
     - `identity.resolve()`.
     - If not `--force`, prompt: `Delete 4 volumes for <project_id>? [y/N]` — exit 0 on no.
     - For each of the four volumes: if `volume_exists`, `remove_volume` and print confirmation; otherwise print "not present, skipping".
   - `cmd_rebuild_image(args)`:
     - `docker.check_available()`, then `docker.rebuild_image(image_name())`.

3. **Startup summary helper**:
   - One function that prints the block (`Project path`, `Project ID`, `Container`, `Image`, `Home volume`, `Tmp volume`, `Var tmp volume`, `Opt volume`, `Git hidden`) given a `RunSpec` and identity. Reused by `cmd_run` and `cmd_info`.

4. **Error handling**:
   - Wrap the top-level dispatch in a try/except for `DockerError` and `FileNotFoundError` (docker binary missing). Print the message to stderr and `sys.exit(1)`. No stack traces for these.

5. **Tests** (`tests/test_cli.py`):
   - Argument parsing: each flag captured into the right namespace field, repeatables accumulate, defaults applied.
   - `cmd_info` output snapshot.
   - `cmd_remove_volume` with `--force` skips the prompt; without `--force` and answering `n` doesn't remove.
   - Monkey-patch `docker.run_container` to return 42 and assert `cmd_run` returns 42.

## Files created or modified

```
src/aibox/cli.py            # full implementation
tests/test_cli.py           # new
```

## Acceptance criteria

- `aibox`, `aibox run`, `aibox info`, `aibox remove-volume`, `aibox rebuild-image` all work.
- `aibox info` matches the startup summary format from `PROMPT.md`.
- All flag combinations from the spec are accepted and forwarded correctly.
- Manual end-to-end check on macOS: from a real project directory, `aibox` builds the image (first time), starts a container, drops into bash at `/workspace`, project files visible, `.git` masked, exit returns to host, volumes survive a second invocation.

## Decisions to flag during plan mode

- Behaviour when the user runs `aibox` outside a real directory (e.g. inside the aibox repo itself during dev) — should still work, just produces an `aibox-aibox-XXXXXXXX` project. Confirm that's fine.
- Whether `remove-volume`'s confirmation prompt should default to N (safer) — yes per spec convention.
