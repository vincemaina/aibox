# tests/

Pytest test suite. Tests are plain functions, not `unittest.TestCase` classes.

## Files

- `test_cli_smoke.py` — argparse parser shape and subcommand dispatch.
- `test_cli.py` — behavioural tests per subcommand, all Docker mocked.
- `test_identity.py` — ID/name derivation, git-dir enumeration.
- `test_docker.py` — `build_run_args` composition (incl. git modes), availability checks, volume ops.
- `test_config.py` — `.aibox.toml` load/validate and CLI merge rules.
- `test_userconfig.py` — user-level config, XDG path resolution.
- `test_templates.py` — ref resolution, merge classification, home-seed staging.
- `test_onboarding.py` — first-run setup and the per-project import offer.
- `test_docs.py` — every CLI command and flag appears in `docs/documentation.html`, plus the SEO surface of the site.
- `test_repo_structure.py` — enforces the working-practice rules: every tracked directory has a `CLAUDE.md`, and `ROADMAP.md` references every plan file.

## Running

```bash
pytest               # full suite
pytest -k identity   # subset by name
pytest -x            # stop on first failure
```

## Conventions

- One test file per source module (`test_identity.py` mirrors `src/aibox/identity.py`).
- Tests that touch `docker.py` or `templates.py` mock `subprocess.run`. **Never invoke real Docker, and never clone over the network, from the suite.**
- Tests touching user-level config, state, or the template cache must set `XDG_CONFIG_HOME` / `XDG_STATE_HOME` / `XDG_CACHE_HOME` to a `tmp_path`, so a run never reads or writes the developer's real `~/.config`, `~/.local/state`, or `~/.cache`.
- **Interactive code paths must be proven non-blocking.** Tests for prompting flows monkeypatch `_ask` to `pytest.fail(...)` and assert the flow stays silent without a terminal. A regression here hangs CI rather than failing it, so cover it explicitly.
- Use `capsys` for stdout/stderr capture, `tmp_path` for filesystem isolation, `monkeypatch` to swap collaborators.
- Inject `now` and random sources into identity functions so container-name tests are deterministic.
