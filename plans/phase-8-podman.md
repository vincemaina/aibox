# Phase 8: Podman support

## Goal

Make `aibox` work on rootless Podman (the default container engine on Fedora and RHEL) as well as Docker, and fix a `.git` masking failure discovered on Podman.

## Context

Podman is the default container engine on Fedora/RHEL and is gaining ground elsewhere as a rootless, daemonless Docker alternative. Its CLI is close enough to Docker's that `aibox`'s commands *appear* to work — which is precisely the danger. All findings below were verified empirically on Fedora, `podman 5.8.4`, rootless, SELinux `Enforcing`, host uid/gid 1000, project dirs tested on both btrfs and tmpfs.

Running the exact argument set `docker.py` builds today, against the real `aibox-default:latest` image built by `podman build`:

```
uid=1000(dev) gid=1000(dev)
read: cat: /workspace/file.txt: Permission denied
touch: cannot touch '/workspace/e2e.txt': Permission denied
GIT LEAK: cat: /workspace/.git/config: Permission denied
```

Three independent problems, each of which must be fixed for Podman to work at all.

### 1. `.git` masking silently fails — security regression

**This is the most serious finding, and it is a confidentiality failure in the tool's core promise.**

Podman enables `tmpcopyup` by default on tmpfs mounts: it copies the contents of the underlying directory into the newly mounted tmpfs. Docker's tmpfs mount is always empty. So `--mount type=tmpfs,target=/workspace/.git` mounts correctly and Podman then populates it with the host's real `.git`:

```
--mount type=tmpfs,target=/workspace/.git                 -> ls .git = "config", cat = SECRET-HISTORY
--mount type=tmpfs,target=/workspace/.git,notmpcopyup     -> ls .git = "" (correctly masked)
```

Writes still don't reach the host, so history can't be *modified* — but the agent gets full read access to commit history, remote URLs, and anything else in `.git`. The failure is silent: the container starts fine and `print_summary` reports `Git hidden: yes`.

Verified independently on tmpfs and on btrfs to rule out the host filesystem as a confounder.

### 2. Rootless Podman inverts the Linux UID logic

Rootless Podman runs the container in a user namespace. The default map is:

```
ctr_id  host_id  count
     0     1000      1        # container root == the invoking host user
     1   524288  65536        # container 1..65536 -> subuid range
```

So container uid 1000 (`dev`) maps to host uid ~525287, **not** to the invoking user. Docker on Linux uses the identity map, which is exactly why the current `entrypoint.sh` + `gosu` approach works there and fails here.

Verified matrix (SELinux relabeling applied, to isolate the UID variable):

| `--userns` | in-container user | `/workspace` write |
|---|---|---|
| default | root | OK (lands on host as uid 1000) |
| default | `dev` (uid 1000) | **Permission denied** |
| `keep-id` | `dev` | OK, host files owned by uid 1000 |
| `keep-id:uid=1000,gid=1000` | `dev` | OK, host files owned by uid 1000 |
| `keep-id:uid=1500,gid=1500` | `dev` | **Permission denied** (mismatch demo) |

Note the inversion: under rootless Podman, running as container *root* is the working case for bind mounts, and running unprivileged is what breaks. `aibox`'s threat model wants non-root, so `--userns=keep-id` is mandatory.

**The explicit `uid=`/`gid=` form is required.** Plain `keep-id` maps the host user to the *same numeric* uid inside the container. That coincides with `dev` only when the host user happens to be uid 1000. On a host user with uid 501 (common on macOS) or 1001, plain `keep-id` maps to a uid that isn't `dev`, and `--user dev` then fails. Pin to the image's `dev` uid, not the host's.

**Interaction with `entrypoint.sh`:** under `keep-id`, container init already starts as ctr-uid 1000, so the `if [ "$(id -u)" = "0" ]` branch is skipped and the script just `exec`s — the desired outcome. The `gosu` retune path must not run, so `HOST_UID`/`HOST_GID` should not be passed on the Podman path.

### 3. SELinux blocks the bind mount outright

A project dir under `$HOME` is labelled `unconfined_u:object_r:user_home_t:s0`. Container processes run as `container_t`, which has no access to `user_home_t`. Isolating the cause with `--security-opt label=disable`:

```
--user root, no relabel                 -> Permission denied     (SELinux denial)
--user root, label=disable, no relabel  -> WRITE_OK              (proves it was SELinux)
```

On Fedora with enforcing SELinux, a bind mount without relabeling is completely inaccessible to the container, **even to container root**. This is independent of, and additional to, the UID problem.

**Use `relabel=shared` (`:z`), not `relabel=private` (`:Z`).** `:Z` stamps the directory with a unique per-container MCS category pair (`container_file_t:s0:c122,c532`). Since every `aibox run` is a fresh container with fresh categories, `:Z` forces a full recursive relabel on every run, and two concurrent sessions on one project lock each other out. Verified: `relabel=shared` yields `container_file_t:s0` with no category, and a second container accesses the same tree fine.

### Docker cannot express the relabel in `--mount` syntax

Docker's `--mount` does not support `relabel=` / `z` / `Z` at all — SELinux labels are only settable via the `-v` short syntax. There is therefore **no single mount string that works on both engines**, which forces an engine branch (see Task 3 for the decision).

### `podman-docker` is not a solution

The Fedora `podman-docker` package ships a `/usr/bin/docker` shell wrapper that `exec`s podman with identical argv. It solves only the binary-name problem. All three failures above are semantic, so the shim fixes none of them — a user with it installed gets an `aibox` that appears to work while silently leaking `.git` and failing to write `/workspace`.

It also makes detection *harder*: `shutil.which("docker")` returns a path that is actually Podman, so a naive name-based detector picks the wrong code path. **Detection must probe behaviour, not the binary name.** The wrapper also prints `Emulate Docker CLI using podman...` to stderr on every invocation until `/etc/containers/nodocker` exists.

### What already works unchanged

Encouragingly, most of the surface is compatible. Verified against podman 5.8.4:

| aibox invocation | Podman | Notes |
|---|---|---|
| `run --rm -it --name --workdir --user` | OK | identical |
| `-e FOO=bar`, `--env-file` | OK | identical |
| `--mount type=bind,...` | OK | needs `relabel=shared` added |
| `--mount type=volume,...` | OK | named volumes persist across `--rm` |
| `--mount type=tmpfs,...` | syntax OK | semantics differ — see problem 1 |
| `build -t X -f Dockerfile .` | OK | built the real aibox image clean (~90s, 801 MB, git 2.47.3, node v20) |
| `image inspect X` | OK | short name resolves; **exit 125** on missing (docker: 1) |
| `volume inspect X` | OK | **exit 125** on missing (docker: 1) |
| `volume rm X` | OK | exit 1 on missing; stderr contains `no such volume`, matching `docker.py:128` |
| `version --format '{{.Server.Version}}'` | OK | returns podman's version (`5.8.4`), not a Docker version |
| exit-code propagation from `run` | OK | verified `exit 42` -> 42 |

The differing exit codes need no change: `image_exists` and `volume_exists` already test `returncode == 0`, so 125 is handled correctly today. Worth an explicit regression test rather than a fix.

Scope note: this phase targets **rootless** Podman, the overwhelmingly common configuration and the one Fedora ships. Rootful Podman behaves like Docker for bind-mount ownership and must *not* get `keep-id` — gate on the detected rootless flag.

## Tasks

### 1. New module: `src/aibox/runtime.py`

Engine detection and capability reporting. Pure except for the probe subprocesses, which are cached per process.

```python
@dataclass(frozen=True)
class Runtime:
    binary: str          # "docker" | "podman" (path as invoked)
    engine: str          # "docker" | "podman"
    rootless: bool       # podman rootless -> keep-id needed
```

Detection order:

1. `AIBOX_ENGINE=docker|podman` env var, and/or an `engine` key in `.aibox.toml` — explicit escape hatch, highest precedence, no probing.
2. Otherwise probe **by behaviour**: run `<binary> --version` and check for the literal string `podman`. The `podman-docker` wrapper passes argv straight through, so `docker --version` under the shim prints `podman version 5.8.4` and is correctly identified.
3. Prefer a real `docker` when both are present (least surprise for existing users); fall back to `podman`.
4. For Podman, determine rootless via `podman info --format '{{.Host.Security.Rootless}}'` -> `true`/`false`.

Raise `DockerError` (or a renamed `EngineError`) with a clear message when neither binary is present.

### 2. Thread the runtime through `docker.py`

Only **7 hardcoded `"docker"` literals** exist, all in `docker.py` (lines 61, 78, 87, 96, 121, 137). Replace each with `runtime.binary`. `check_available` becomes engine-aware, and its "Docker is not running / Install Docker Desktop" messages must not say "Docker" when the engine is Podman.

`build_run_args` gains a `Runtime` parameter. It stays pure, so the full engine matrix remains snapshot-testable without either engine installed — this is the main reason the change is cheap.

### 3. Engine-conditional mount and userns arguments

The bind mount is the one place the two engines genuinely diverge.

**Decision: branch the argument construction per engine; keep `--mount` on the Docker path.** The alternative — switching the bind to `-v "{cwd}:/workspace:z"` on both engines — would work but regresses phase 7's deliberate move to `--mount` for Windows drive-letter safety. Not worth undoing.

Podman path:

```
--mount type=bind,source={cwd},target=/workspace,relabel=shared
--mount type=tmpfs,target=/workspace/.git,notmpcopyup
--userns=keep-id:uid=1000,gid=1000          # rootless only
--user dev                                  # explicit, so entrypoint's root/gosu branch is skipped
# and: do NOT pass HOST_UID / HOST_GID
```

Docker path: unchanged from today.

**Decision: fix the `.git` leak with `notmpcopyup`, not an anonymous volume.** An empty anonymous volume (`--mount type=volume,target=/workspace/.git`) also masks correctly and was verified to work on Podman and leave no garbage behind under `--rm`. It has the appeal of being a single mechanism for both engines. But `notmpcopyup` is a Podman-only option that Docker rejects, so it leaves the proven Docker path *completely untouched* — zero regression risk on the engine we cannot test on Fedora. Mechanism uniformity is not worth risking the working path.

Pin the `keep-id` uid/gid to the image's `dev` uid (1000) as a named constant, cross-referenced to the `useradd` line in the Dockerfile. If the Dockerfile ever changes `dev`'s uid, this must change with it — worth a comment in both files.

### 4. Guard against relabeling sensitive directories

`relabel=shared` is **recursive and persistent on the host** — it survives container exit and nothing reverts it. Verified before/after:

```
before: unconfined_u:object_r:user_home_t:s0
after:  system_u:object_r:container_file_t:s0     (dir and every file beneath it)
```

The host user is `unconfined_t` on a stock Fedora workstation, so they keep full access and editors/git/IDEs keep working. But **confined** services lose access to that tree, and if a user runs `aibox` directly in `$HOME`, this recursively relabels their entire home directory including `~/.ssh`. Red Hat's guidance is explicit about not relabeling `/home`, `/etc`, `/var/log` and similar.

Refuse to run when the bind-mount root is `$HOME`, `/`, or any path under `/etc`, `/usr`, `/var`. This guard is cheap and worth having on **all** engines — running `aibox` at those roots is a mistake regardless of SELinux.

Print a one-time note the first time aibox relabels a directory, mentioning that `restorecon -R <dir>` reverts it.

### 5. Tests

- Snapshot tests for `build_run_args` across the matrix: docker / podman-rootless / podman-rootful. No engine required.
- **Regression test for the `.git` leak**: assert `notmpcopyup` is present on the Podman path whenever `mask_git` is set. This is the security-critical assertion — it should read unmistakably as such.
- Detection tests with a faked `--version` output, including the `podman-docker` shim case (binary named `docker`, output says `podman`).
- `AIBOX_ENGINE` override precedence.
- Sensitive-path guard: `$HOME`, `/`, `/etc/foo` rejected; a normal project dir accepted.
- Assert `image_exists`/`volume_exists` treat exit 125 as "absent" (guards the existing `== 0` logic against a future refactor to `== 1`).
- `keep-id` present when rootless, absent when rootful.

### 6. Documentation

- `README.md`: Podman as a supported engine, `AIBOX_ENGINE` override, the SELinux relabel caveat and `restorecon` escape hatch, and a note that `podman-docker` is unnecessary.
- `SECURITY.md`: document the `.git` masking mechanism per engine. If any version shipped with the Podman leak, say so plainly rather than quietly fixing it.
- `CLAUDE.md`: update the "Docker operations" description of `docker.py` and add `runtime.py` to the module list.
- `src/aibox/CLAUDE.md`: add `runtime.py`; note it is the second module allowed to shell out.
- `ROADMAP.md`: mark phase 8 status.
- `plans/CLAUDE.md`: the `## Files` list is missing `phase-7-cross-platform.md` — add it alongside `phase-8-podman.md`.

## Files created or modified

```
src/aibox/runtime.py                # new — engine detection + capabilities
src/aibox/docker.py                 # runtime.binary, engine-conditional args, path guard
src/aibox/cli.py                    # runtime wiring, engine-aware --user default, engine in summary
src/aibox/config.py                 # optional `engine` key
tests/test_runtime.py               # new — detection, override, shim case
tests/test_docker.py                # engine matrix snapshots, .git leak regression test
tests/test_config.py                # `engine` key
README.md                           # Podman support, SELinux caveat
SECURITY.md                         # per-engine .git masking
CLAUDE.md                           # runtime.py in module list
src/aibox/CLAUDE.md                 # runtime.py
plans/CLAUDE.md                     # index phase-7 and phase-8
ROADMAP.md                          # phase 8 row
```

## Acceptance criteria

- `pytest` green, no regression in the existing 93 tests.
- On Fedora rootless Podman + SELinux enforcing, `aibox run`:
  - `/workspace` is readable **and** writable from inside the container;
  - files created in the container are owned by the invoking host user and editable from the host;
  - `/workspace/.git` is **empty** — verified by `cat /workspace/.git/config` failing with "No such file or directory";
  - the four named volumes persist across runs;
  - `git` and `node` work inside the container.
- `aibox info` reports which engine was detected.
- Docker path produces a byte-identical argument list to today's (snapshot test proves no regression).
- `AIBOX_ENGINE=podman` forces the Podman path even when `docker` is present, and vice versa.
- `aibox run` from `$HOME` is refused with a clear message.

The full Podman invocation was already verified end-to-end during investigation, so this is a known-reachable target:

```
uid=1000(dev) gid=1000(dev) groups=1000(dev)
read: hello
WORKSPACE WRITE: OK
GIT MASKED: []  leak=[No such file or directory]
HOME VOLUME WRITE: OK
git version 2.47.3
v20.19.2
```

## Decisions to flag during plan mode

1. **Ship the `.git` fix separately and first?** It is a security fix for anyone already running aibox under Podman, and it is a two-line change. Bundling it into a large engine-support PR delays it and buries it in the diff. Recommend a standalone commit ahead of this phase.
2. **`notmpcopyup` vs anonymous volume** for masking — recommended `notmpcopyup` above (zero risk to the Docker path), but the anonymous volume's single-mechanism appeal is a legitimate counter-argument *if* someone can verify it on real Docker first.
3. **Is the `$HOME`/system-path guard in scope for this phase**, or its own smaller change? It is engine-independent and arguably a pre-existing gap.
4. **Rootful Podman**: assume Docker-like behaviour and skip `keep-id`, or explicitly refuse to run until someone can test it? Untested either way.
5. **CI**: the pytest matrix needs no engine, so it costs nothing. A Podman-backed integration job is possible (`ubuntu-latest` can install podman), but it would be the project's first engine-backed CI. Related deferred item already in `ROADMAP.md` Future Work.
6. **`DOCKER_HOST` convention deliberately not implemented.** It is the dominant Podman-compat convention (Testcontainers, Quarkus) but only applies to tools speaking the Docker *API* over a socket. aibox shells out to the CLI and never touches the socket, so honouring `DOCKER_HOST` would be cargo-culting.

## References

- [Understanding rootless Podman's user namespace modes — Red Hat](https://www.redhat.com/en/blog/rootless-podman-user-namespace-modes)
- [podman-run(1) — `--mount` / `--volume` / `--userns`](https://docs.podman.io/en/latest/markdown/podman-run.1.html)
- [My advice on SELinux container labeling — Red Hat Developer](https://developers.redhat.com/articles/2025/04/11/my-advice-selinux-container-labeling)
- [Docker bind mounts — `relabel` not supported via `--mount`](https://docs.docker.com/engine/storage/bind-mounts/)
- [containers/podman#16721 — Docker-compatible version info](https://github.com/containers/podman/issues/16721)
- [containers/podman#24934 — `keep-id:uid=,gid=` changes container init user](https://github.com/containers/podman/issues/24934)
