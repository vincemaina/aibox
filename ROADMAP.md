# aibox Roadmap

High-level plan for building the `aibox` CLI. See [`PROMPT.md`](./PROMPT.md) for the full specification and [`CLAUDE.md`](./CLAUDE.md) for working practices.

## Phases

| #  | Phase                                              | Status   | Summary                                                                 |
|----|----------------------------------------------------|----------|-------------------------------------------------------------------------|
| 1  | [Scaffolding](./plans/phase-1-scaffolding.md)      | Done        | `pyproject.toml`, `src/` layout, entry point, test infrastructure.   |
| 2  | [Identity](./plans/phase-2-identity.md)            | Done        | Project ID, container name, image name, volume name derivation.      |
| 3  | [Docker module](./plans/phase-3-docker.md)         | Done        | Image build/check, container run, volume management, Dockerfile.     |
| 4  | [CLI commands](./plans/phase-4-cli-commands.md)    | Done        | `run`, `info`, `remove-volume`, `rebuild-image`, all flags.          |
| 5  | [Config](./plans/phase-5-config.md)                | Done        | `.aibox.toml` parsing and CLI merge rules.                           |
| 6  | [Polish](./plans/phase-6-polish.md)                | Done        | Error handling, README, end-to-end tests, subfolder CLAUDE.md files. |
| 7  | [Cross-platform support](./plans/phase-7-cross-platform.md) | Done        | macOS + Linux + Windows. `--mount` syntax, case-normalised path hash, Linux UID/GID handling, OS matrix in CI. |

## Guiding principles

These shape every phase. Full context in [`CLAUDE.md`](./CLAUDE.md) and [`claude-best-practices.md`](./claude-best-practices.md).

- **Stdlib only** unless there's a very strong reason otherwise (per [`PROMPT.md`](./PROMPT.md)).
- **No `shell=True`** — always pass argument lists to `subprocess.run`.
- **macOS-first** — don't burn time on Windows path edge cases.
- **Security non-negotiables** — no host home mount, no Docker socket, no SSH/cloud/dbt credentials, `.git` masked, no GitHub CLI (`gh`) or credentials in image. (`git` itself is installed so agents can clone public repos / install plugins; safety comes from the masked `.git` + absent credentials, not from withholding the binary.)
- **Boring code beats clever code** — readability and maintainability over abstraction.
- **Tests enforce practices** — at minimum, a test that every directory has a `CLAUDE.md` (per [`claude-best-practices.md`](./claude-best-practices.md)).

## Definition of done (project level)

Project is done when the acceptance criteria in `PROMPT.md` all pass:

- `pip install -e .` exposes a global `aibox` command.
- Running `aibox` from any project starts an interactive container with the project at `/workspace`.
- The four named volumes persist across runs and are project-specific.
- The host `.git` is masked when present.
- Git/GitHub CLI are absent from the image.
- No host credentials are mounted.
- `aibox info`, `aibox remove-volume`, and `aibox rebuild-image` behave per spec.
- README explains install, usage, what's mounted/persisted, why `.git` is hidden, why credentials aren't mounted, and how to manage volumes/images.

## How to use this roadmap

1. Pick the next phase whose status is `Not started`.
2. Open its plan file. Read context, tasks, files, and acceptance criteria.
3. Use plan mode in Claude Code to align on approach before any code changes.
4. Implement, run tests, self-verify against the phase's acceptance criteria.
5. Update the phase's status in this table to `Done` and move on.

If a plan turns out to be wrong as you work, update the plan file in the same commit as the code change — the plan is a living artifact, not a museum piece.

## Future work (post-MVP)

Captured here so the MVP scope stays tight. Promote items to their own plan file when picked up.

- **Seed `claude-best-practices.md` into target projects.** Per `CLAUDE.md`'s "aibox should deploy these practices" note. Likely an `aibox init` command that writes the file plus a starter `.aibox.toml`. Do not auto-create on `aibox run`.
- **Custom images.** Allow `.aibox.toml` to point at a different image or a project-local Dockerfile. Keeps the default image untouched.
- **Docker Compose support.** For projects that need sidecar services (Postgres, Redis, etc.).
- **GitHub integration.** Opt-in, scoped read-only token mount. Not the default.
- **Automatic port detection.** Read package.json / pyproject.toml / docker-compose.yml for likely ports.
- **`--allow-git-history` flag.** Opt-in to *unmask* the host `.git` so the agent can read commit history inside the container. (`git` itself is now always installed; this would only lift the tmpfs mask. Default stays masked.)
- **Remote VM support.** Same UX but the container runs on a remote host.
- **`--no-cache` for `rebuild-image`.** Useful when debugging the Dockerfile.
- **End-to-end test harness.** A pytest fixture that builds the image, runs a container, asserts behaviour. Slow, opt-in via a marker.
- **Docker-backed CI job.** Deferred from phase 7. A separate `ubuntu-latest` job (Docker is preinstalled on GitHub runners) that runs `docker build` + a smoke-test container run after the pytest matrix. Adds ~3 min/run; gate to `push` to `main` only to save PR minutes.
- **Symlink behaviour audit.** Phase 7 documents that symlinked project directories aren't tested cross-platform. Worth a proper audit: macOS symlinks, Linux symlinks, Windows junction points, WSL crossing into Windows paths. Likely fine in most cases but currently a known unknown.

## Big-feature ideas (researched, not scheduled)

Larger directions explored during a brainstorming session (2026-06). Captured for later; none are committed. Each would become its own phase + plan file if picked up. Research context: egress filtering is repeatedly named the #1 agent-hardening control (CSA/SANS/OWASP), and local agent "audit trail" tooling is an emerging, uncrowded space. The crowded/commodity spaces to avoid: thin Claude-in-Docker wrappers and managed cloud sandboxes (E2B, Vercel Sandbox, Docker Sandboxes).

- **① Trustworthy sandbox — egress firewall + session audit trail.** *(Strongest fit; deepens aibox's security identity.)* Two synergistic halves:
  - *Egress firewall:* route the agent's outbound traffic through a sidecar proxy container that enforces a domain allowlist/denylist and logs every request. Closes aibox's biggest current gap — egress is wide open today, so a compromised agent could exfiltrate anything it can see.
  - *Audit trail:* diff `/workspace` before/after (or inotify), collect the proxy's network log, and surface an `aibox report` at session end — files changed (+/- lines), commands run, domains contacted, anything blocked.
  - *Demo:* agent tries to `curl` a paste site → blocked + logged; on exit, a clean "receipt" of everything it touched. Depth: proxy/DNS/iptables networking, fs instrumentation, structured logging. Catch: domain-level filtering is clean; per-URL needs TLS interception (fiddly) — stick to domain-level.
- **② Fleet — multi-agent dashboard.** A live TUI (à la lazydocker/k9s) over all running aibox containers: project, uptime, CPU/mem, idle-vs-working, attach/kill/restart. Flashy and very demoable. Catch: crowded lane (Claude Squad, Composio orchestrator), and aibox's shared-volume + live bind-mount model means many agents on the *same* project trample each other — true parallel-on-one-project needs per-agent worktrees/copies, which fights the "edit your real files live" design. Fleet across *different* projects is easy; fleet on one project is the hard version. Natural to layer on top of ① later (surface each agent's live network/audit feed).
- **③ Time-travel snapshots.** Snapshot/branch/rollback "undo what the agent did." Rejected as low-fit: `/workspace` is a live bind mount to the host, so the state worth rolling back lives on the host, not in the container fs — snapshotting the container misses the point. Listed for completeness.
