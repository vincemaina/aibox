# Contributing

Thanks for taking an interest. `aibox` is small on purpose — boring, readable Python over clever abstractions.

## Development setup

```bash
git clone https://github.com/vincemaina/aibox.git
cd aibox
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

That gets you a working `aibox` command on the venv's PATH plus `pytest`.

## Running tests

```bash
pytest                  # full suite
pytest -v               # verbose
pytest tests/test_docker.py    # one file
pytest -k identity      # subset by keyword
```

The test suite never invokes real Docker — every `subprocess.run` call is mocked. It should finish in well under a second.

## Repo layout

- [`src/aibox/`](./src/aibox) — the package. Each module has its own [`CLAUDE.md`](./src/aibox/CLAUDE.md) describing what it does.
- [`tests/`](./tests) — pytest suite. One test file per source module.
- [`plans/`](./plans) — one markdown plan per development phase. Indexed by [`ROADMAP.md`](./ROADMAP.md).
- [`PROMPT.md`](./PROMPT.md) — the original specification.
- [`CLAUDE.md`](./CLAUDE.md) — working practices for AI coding agents in this repo.

## Platform support

- **macOS**, **Linux**, and **Windows** are all in CI (`.github/workflows/ci.yml`).
- The pytest suite is OS-agnostic — no real Docker calls, no platform branches in test assertions. The CI matrix is `{ubuntu-latest, macos-latest, windows-latest} × {3.11, 3.12, 3.13}`.
- A Docker-backed e2e job (real `docker build` + container run on Ubuntu) is in the [`ROADMAP.md`](./ROADMAP.md) Future Work list; not in CI today.

## Working practices

- **Stdlib only at runtime.** No runtime dependencies. `pytest` is the only dev dependency. If you think you need a third-party runtime dep, open an issue first.
- **Never `shell=True`.** Always pass argument lists to `subprocess.run`.
- **Compose arguments in pure functions.** All `docker run` arg composition lives in `build_run_args`, not scattered across the codebase, so tests can assert exact output.
- **Plan before coding.** For non-trivial changes, sketch the approach in a plan file under `plans/` (or extend an existing one) before writing code.
- **Tests enforce practices.** `tests/test_repo_structure.py` asserts every tracked directory has a `CLAUDE.md` and every phase plan is indexed in `ROADMAP.md`. If you add a directory or a plan, update those too.

## Submitting changes

1. Fork and branch from `main`.
2. Make focused changes — small PRs land faster.
3. Add tests for new behaviour.
4. Make sure `pytest` is green.
5. Open a PR. Briefly explain the *why*, not just the *what*.

## Reporting bugs

Open an issue at [github.com/vincemaina/aibox/issues](https://github.com/vincemaina/aibox/issues). Include:

- macOS version, Docker version (`docker version`), Python version.
- Exact command you ran.
- Output, including any error messages.
- What you expected.

For security issues, see [SECURITY.md](./SECURITY.md).
