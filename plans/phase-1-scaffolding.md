# Phase 1: Scaffolding

## Goal

Stand up the Python package skeleton so `pip install -e .` exposes a working (but stub) `aibox` command, and so subsequent phases can plug modules in without rewiring packaging.

## Context

This is a greenfield Python CLI. The spec requires:

- `pyproject.toml` (PEP 621 metadata).
- `src/` layout.
- Stdlib only — no runtime deps.
- Console-script entry point `aibox`.

Test infrastructure goes in this phase so every later phase can lean on it. We use **pytest** as a dev-only dependency — runtime code stays stdlib-only (matching `PROMPT.md`'s rule), but tests benefit from pytest's plain `assert`, fixtures, and `parametrize`.

## Tasks

1. **`pyproject.toml`**
   - `[project]` table: `name = "aibox"`, `version = "0.1.0"`, `requires-python = ">=3.11"` (`tomllib` is in stdlib from 3.11).
   - `[project.scripts]` exposing `aibox = "aibox.cli:main"`.
   - Build backend: `setuptools` with `package-dir = {"" = "src"}` and `packages = ["aibox", "aibox.templates"]`.
   - Include the `Dockerfile` template via `[tool.setuptools.package-data]` so it ships with the install.
   - Dev extras: `[project.optional-dependencies] dev = ["pytest"]`. Install with `pip install -e ".[dev]"`.
   - `[tool.pytest.ini_options]` with `testpaths = ["tests"]`.

2. **Package skeleton**
   - `src/aibox/__init__.py` — exposes `__version__`.
   - `src/aibox/cli.py` — `main()` function with an `argparse` parser, subcommands stubbed out to print "not implemented yet" and exit `0`. `aibox` (no subcommand) should delegate to `aibox run`.
   - `src/aibox/identity.py` — empty module (filled in phase 2).
   - `src/aibox/docker.py` — empty module (filled in phase 3).
   - `src/aibox/config.py` — empty module (filled in phase 5).
   - `src/aibox/templates/__init__.py` — empty; lets the templates dir ship as package data.
   - `src/aibox/templates/Dockerfile` — placeholder `FROM python:3.12-slim` line; full image in phase 3.

3. **Tests** (pytest-style — plain functions, plain `assert`):
   - `tests/test_cli_smoke.py` — verifies `aibox.cli.main(["--help"])` exits 0 and the help text lists all five commands. Use `capsys` to capture stdout.
   - `tests/test_repo_structure.py` — walks the repo and asserts every non-hidden directory (excluding `.git`, `.idea`, `__pycache__`, `tests`, `plans`, `templates`, `*.egg-info`) contains a `CLAUDE.md`. Enforces the [working-practice rule](../claude-best-practices.md).
   - No `tests/__init__.py` — pytest doesn't need it and omitting it avoids import-mode confusion.

4. **Subfolder `CLAUDE.md` files**
   - `src/aibox/CLAUDE.md` — describes the modules and their roles.
   - `tests/CLAUDE.md` — describes the test layout.
   - `plans/CLAUDE.md` — describes how plan docs are organised.

5. **Local install verification**
   - Run `pip install -e .` and confirm the `aibox` command resolves on PATH.
   - Run `aibox --help` and confirm the subcommands appear.

## Files created or modified

```
pyproject.toml                              # new
src/aibox/__init__.py                       # new
src/aibox/cli.py                            # new (stubs)
src/aibox/identity.py                       # new (empty)
src/aibox/docker.py                         # new (empty)
src/aibox/config.py                         # new (empty)
src/aibox/templates/__init__.py             # new
src/aibox/templates/Dockerfile              # new (placeholder)
src/aibox/CLAUDE.md                         # new
tests/CLAUDE.md                             # new
tests/test_cli_smoke.py                     # new
tests/test_repo_structure.py                # new
plans/CLAUDE.md                             # new
```

## Acceptance criteria

- `pip install -e ".[dev]"` succeeds and the `aibox` console script is on PATH.
- `aibox --help` prints usage listing `run`, `info`, `remove-volume`, `rebuild-image`.
- `pytest` (run from the repo root) passes.
- `tests/test_repo_structure.py` would fail if any tracked source directory lost its `CLAUDE.md`.

## Decisions to flag during plan mode

- Python ≥3.11 confirmed (needed for stdlib `tomllib`).
- pytest confirmed as the test runner (dev-only dependency; runtime code stays stdlib-only).
