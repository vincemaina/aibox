# Phase 7: Cross-platform support

## Goal

Make `aibox` work on Linux and Windows in addition to macOS, with CI verifying each platform.

## Context

The spec deliberately scoped the MVP to macOS, but a closer code audit shows nothing in the runtime code is technically macOS-specific — the container is always Linux, the Python is stdlib, and the Docker CLI flags are platform-neutral. The real blockers are three concrete things:

1. **`-v C:\path:/workspace`** — Docker's `-v` syntax parses on `:`, which breaks on Windows drive-letter paths.
2. **Case-insensitive filesystems** (Windows, default macOS) — `C:\Foo` and `c:\foo` produce different project IDs when run from each spelling.
3. **UID/GID mismatch on Linux** — Docker Desktop on macOS and Windows translates bind-mount ownership transparently. Docker Engine on Linux does not. The container's `dev` user is UID 1000; files written to `/workspace` from inside the container land as UID 1000 on the host, which only matches the host user if they happen to be UID 1000.

Two ecosystem realities also worth handling:

- **WSL on Windows** — many Windows developers use Docker Engine inside WSL2 rather than Docker Desktop. Paths look POSIX-y (`/mnt/c/Users/...`) from inside WSL. Detecting and supporting this is cheap.
- **Docker Desktop's commercial licensing** — paid for medium/large company use. Supporting Docker Engine + WSL on Windows is a meaningful inclusivity win.

The test suite is already OS-agnostic (no real Docker calls), so most of the existing 80 tests just need their assertions updated for the new mount syntax.

## Tasks

### 1. Switch to `--mount` syntax in `docker.py`

`-v src:dst[:opts]` is replaced with `--mount type=bind,source=...,target=...` and `--mount type=volume,source=...,target=...`. Unambiguous parsing on every platform, no need to escape colons.

In `build_run_args`:

```python
# before
args += ["-v", f"{spec.identity.cwd}:/workspace"]

# after
args += ["--mount", f"type=bind,source={spec.identity.cwd},target=/workspace"]
```

Same for the four named volumes (use `type=volume`). The existing tmpfs mount (`--mount type=tmpfs,...`) already uses this syntax — consistent now.

Update `tests/test_docker.py` snapshot assertions for the new flag layout.

### 2. Path normalisation in `identity.py`

Case-insensitive filesystems produce inconsistent project IDs depending on how the user typed the path. Fix by lowercasing before hashing:

```python
def path_hash(path: Path) -> str:
    resolved = str(path.resolve()).lower().encode("utf-8")
    return hashlib.sha256(resolved).hexdigest()[:8]
```

This is cross-platform-safe — Linux paths are case-sensitive but identical strings lowercase to identical strings, so behaviour on Linux is unchanged when the user types paths consistently.

Slug derivation stays as-is — folder name is read from `.name` which already preserves the canonical case.

Add tests:

- Same path with different case capitalisation → same `project_id`.
- Linux: case-sensitive paths still produce stable IDs.

### 3. Linux UID/GID handling

Detect platform in `cli.py` and adjust the `--user` default when on Linux:

```python
import os
import platform

DEFAULT_USER = (
    f"{os.getuid()}:{os.getgid()}"
    if platform.system() == "Linux"
    else "dev"
)
```

This makes `--user` argparse default platform-aware. On macOS/Windows it stays `dev` (Docker Desktop translates UIDs); on Linux it becomes the host user's UID:GID.

Side-effect to handle: if the container runs as a UID with no matching user in `/etc/passwd`, `$HOME` may not point to a writable directory and tools that read `getpwuid()` (npm, ssh-keygen, etc.) warn. Two options:

**Option A (simpler):** entrypoint script that chowns `/home/dev` to the running UID and exports `HOME=/home/dev`. Runs as root, drops privileges via `gosu` or `su-exec`.

**Option B (no entrypoint):** mount `/home/dev` as the running user's home regardless of `dev` user. Requires the named volume to be pre-chowned. Fiddly.

**Recommendation: Option A.** Add `gosu` to the Dockerfile (~3MB), add `entrypoint.sh`, wire it as the image's `ENTRYPOINT`. Keeps `CMD ["/bin/bash"]` working.

### 4. WSL detection

When `aibox` is invoked from inside WSL2, paths look POSIX-style and Docker Engine is used directly (no Docker Desktop translation). The path-string-to-Docker handling needs to ensure we pass POSIX paths, not the WSL-from-Windows hybrid form.

Detection:

```python
def is_wsl() -> bool:
    return "microsoft" in platform.uname().release.lower()
```

In practice, when run from inside WSL, `Path.cwd()` already returns POSIX paths like `/home/foo/project`, so the `--mount` source value just works. Mostly we want to **detect** WSL so we can avoid Windows-specific code paths.

### 5. Dockerfile changes

- Add `gosu` package.
- Add `ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]`.
- Keep `CMD ["/bin/bash"]`.
- Bundle `entrypoint.sh` via package-data, copied into the image at build.

`entrypoint.sh` outline:

```bash
#!/usr/bin/env bash
set -e

# If running as root with a different target UID, fix ownership and drop privileges.
if [ "$(id -u)" = "0" ] && [ -n "${TARGET_UID:-}" ]; then
  chown -R "${TARGET_UID}:${TARGET_GID:-${TARGET_UID}}" /home/dev /opt
  exec gosu "${TARGET_UID}:${TARGET_GID:-${TARGET_UID}}" "$@"
fi

# Otherwise just exec the command.
exec "$@"
```

Pass `TARGET_UID`/`TARGET_GID` as env vars from `cli.py` on Linux. On macOS/Windows the entrypoint is a no-op.

Actually — re-reading: if we use `--user $UID:$GID` we never start as root, so chown won't work. Pick one approach:

- **Path 1:** start as root, chown home, drop via gosu (entrypoint does the work).
- **Path 2:** use `--user $UID:$GID`, pre-create the volume with `docker volume create` and `docker run --rm -v vol:/home/dev alpine chown -R UID:GID /home/dev` on first use.

**Recommended: Path 1.** Self-contained, one-time cost per container start (~10ms), no external state.

### 6. CI matrix

Update `.github/workflows/ci.yml`:

```yaml
strategy:
  fail-fast: false
  matrix:
    os: [ubuntu-latest, macos-latest, windows-latest]
    python-version: ["3.11", "3.12", "3.13"]
```

This runs pytest (which doesn't invoke Docker) on every combination. Catches Python-level issues per platform.

**Optional:** a separate job that runs the full Docker-backed flow on `ubuntu-latest` (where Docker is preinstalled on GitHub runners). Adds confidence but slows CI by ~3 minutes. Worth it.

### 7. Documentation updates

- `README.md` Requirements section: list macOS, Linux, Windows (Docker Desktop or WSL2 + Docker Engine).
- `README.md` Install: note pipx works on all three.
- `CLAUDE.md`: drop the "macOS focus" line; replace with "Cross-platform, tested on macOS/Linux/Windows".
- `CONTRIBUTING.md`: note the CI matrix and how to run platform-specific tests locally.
- `ROADMAP.md`: move "Windows support" out of Future Work into completed phase 7.

## Files created or modified

```
src/aibox/docker.py                          # --mount syntax
src/aibox/identity.py                        # case-normalise path hash
src/aibox/cli.py                             # platform-aware --user default, WSL detection, TARGET_UID env
src/aibox/templates/Dockerfile               # gosu + ENTRYPOINT
src/aibox/templates/entrypoint.sh            # new — UID/GID fixup
pyproject.toml                               # package-data for entrypoint.sh
tests/test_docker.py                         # --mount assertions, env-var passing
tests/test_identity.py                       # case-normalisation tests
tests/test_cli.py                            # platform-aware default user test
.github/workflows/ci.yml                     # OS matrix
README.md                                    # Requirements/Install update
CONTRIBUTING.md                              # platform notes
CLAUDE.md                                    # drop macOS-only language
ROADMAP.md                                   # move Windows support, mark phase 7 done
```

## Acceptance criteria

- `pytest` is green on all of: macOS, Ubuntu, Windows (verified via CI matrix).
- `aibox info` runs correctly on all three platforms.
- `aibox run` produces a working interactive container on all three:
  - macOS — already verified.
  - Linux — files written from inside the container in `/workspace` are owned by the invoking user on the host. No permission errors when installing npm globals.
  - Windows — works from PowerShell, cmd, and from inside WSL2. Path with spaces (`C:\Users\Test User\my-project`) works.
- No regression in the existing 80 tests.
- README badges show CI green for all matrix entries.

## Decisions to flag during plan mode

- **`gosu` vs `su-exec` vs `tini`** for privilege dropping. `gosu` is the most common; ~3MB. Confirm we're OK adding it to the image.
- **CI Docker-backed e2e job.** Slows CI by ~3 minutes per run. Worth it for confidence, optional for cost. Recommend yes, gated to `push` events only (skip on PRs to save minutes).
- **What "supported" means.** Without continuous manual testing on Windows, we should commit only to "tested on every CI run" not "guaranteed bug-free." Open to issues being filed and fixed reactively.
- **Docker Desktop alternative on Windows.** Document WSL2 + Docker Engine as an explicit supported path, since many users won't have Desktop licences.
- **Symlinks in project directories.** Untested cross-platform behaviour. Likely fine, but worth a one-off check.
