# tests/

Pytest test suite. Tests are plain functions, not `unittest.TestCase` classes.

## Files

- `test_cli_smoke.py` — argparse parser shape and subcommand dispatch.
- `test_repo_structure.py` — enforces the working-practice rules: every tracked directory has a `CLAUDE.md`, and `ROADMAP.md` references every plan file.

Future phases will add:

- `test_identity.py` (phase 2)
- `test_docker.py` (phase 3)
- `test_cli.py` (phase 4 — replaces the phase-1 smoke test)
- `test_config.py` (phase 5)

## Running

```bash
pytest               # full suite
pytest -k identity   # subset by name
pytest -x            # stop on first failure
```

## Conventions

- One test file per source module (`test_identity.py` mirrors `src/aibox/identity.py`).
- Tests that touch `docker.py` mock `subprocess.run`. **Never invoke real Docker from the suite.**
- Use `capsys` for stdout/stderr capture, `tmp_path` for filesystem isolation, `monkeypatch` to swap collaborators.
- Inject `now` and random sources into identity functions so container-name tests are deterministic.
