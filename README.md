<p align="center">
  <img src="assets/banner.svg" alt="aibox — disposable docker containers for AI coding agents" width="480">
</p>

<p align="center">
  <a href="https://github.com/vincemaina/aibox/actions/workflows/ci.yml"><img src="https://github.com/vincemaina/aibox/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="./LICENSE"><img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="License: MIT"></a>
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.11%2B-blue.svg" alt="Python 3.11+"></a>
</p>

# aibox

`aibox` is a small Python CLI that launches a disposable Docker container from any local project directory. It is built for running Claude Code or another AI coding agent inside a sandbox where the agent can edit the current project files but cannot see your home directory, credentials, dbt profiles, Snowflake credentials, GitHub credentials, or your `.git` history.

## Why aibox

- **Your credentials stay invisible.** Your home directory is never mounted. No SSH keys, cloud credentials, dbt profiles, or `~/.aws` — the container simply cannot see them.
- **Your Git history is protected.** `/workspace/.git` is masked with an empty tmpfs, so an agent can't read your history or rewrite it.
- **The agent still can't reach your remotes.** `git` *is* installed, so agents can clone public repos and install Claude Code plugins — but with no `gh` and no mounted credentials, there's nothing to authenticate or push with.
- **No Docker socket.** The container can't escape by talking to the daemon that runs it.
- **Runs as a non-root user** (`dev`) matched to your host UID/GID, so files you create in `/workspace` are owned by you, not by root.
- **Disposable by default.** The container is removed on exit (`--rm`). Nothing accumulates.
- **But your setup persists.** `/home/dev`, `/tmp`, `/var/tmp`, and `/opt` are per-project named volumes, so npm globals, shell history, and Claude config survive across sessions.
- **Per-project isolation.** Each project gets its own volume set, keyed by a stable hash of its absolute path. Two projects never share state.
- **Ready for Claude Code out of the box.** Ships with a current Node.js LTS (Claude Code needs `node >=22`), plus git, ripgrep, fd, jq, and build-essential.
- **Zero runtime dependencies.** Pure Python standard library, shelling out to the `docker` CLI. No SDKs to install or keep in sync.
- **Configurable per project.** An optional `.aibox.toml` adds ports, env vars, env files, a custom shell, or raw Docker arguments.

The mental model:

- `/workspace` inside the container is a live bind mount of your project. Edit freely.
- `/home/dev`, `/tmp`, `/var/tmp`, `/opt` are per-project named volumes that persist across runs.
- Everything else (your real home, ssh keys, cloud credentials, dbt profiles, `.git` history) is invisible to the container.
- `git` is installed so the agent can clone public repos and install Claude Code plugins, but the GitHub CLI (`gh`) is not, and no credentials are mounted — so the agent can't push to or authenticate against your remotes. Your real `.git` history is masked.

## Requirements

- **OS**: macOS, Linux, or Windows. See [Platform notes](#platform-notes) below for the practical differences.
- **Python 3.11+**
- **Docker installed and running.** `aibox` shells out to the `docker` CLI; it won't start a container if Docker isn't available. Verify with `docker version`.

### Platform notes

| Platform | Docker option | Notes |
|----------|--------------|-------|
| **macOS** | [Docker Desktop](https://www.docker.com/products/docker-desktop/) | Tested. Bind-mount ownership is translated transparently. |
| **Linux** | Docker Engine (or Desktop) | Tested. The container's `dev` user is retuned at startup to match your host UID/GID via an entrypoint script, so files you create in `/workspace` are owned by you on the host. |
| **Windows** | [Docker Desktop](https://www.docker.com/products/docker-desktop/) **or** WSL2 + Docker Engine | Docker Desktop on Windows is paid for commercial use over a certain company size. WSL2 + Docker Engine is a free alternative — install Docker Engine inside a WSL2 distro and run `aibox` from inside WSL. |

On Linux, Docker Engine only accepts connections from members of the `docker` group. If `aibox` reports a permission error, add yourself and start a new login session:

```bash
sudo usermod -aG docker $USER   # then log out and back in
```

Note that `docker` group membership is effectively root-level access on the host.

Podman is **not** currently supported — its rootless UID mapping, SELinux labelling, and `tmpcopyup` behaviour all differ from Docker in ways that would silently unmask `.git`. See [`plans/phase-8-podman.md`](./plans/phase-8-podman.md). Fedora and RHEL users should install Docker Engine.

## Install

Make sure Docker is running first. Then install `aibox` globally with [pipx](https://pipx.pypa.io/) (recommended for CLI tools):

```bash
pipx install -e .
```

Or with regular pip:

```bash
pip install -e .          # runtime only
pip install -e ".[dev]"   # with pytest (for development)
```

Either way, the `aibox` command becomes globally available.

## Basic usage

From any project directory:

```bash
cd ~/projects/my-project
aibox
```

That:

1. Resolves a stable project ID from the folder name plus an 8-character hash of the absolute path.
2. Builds the default Docker image (`aibox-default:latest`) if it doesn't exist yet.
3. Starts an interactive container with the project bind-mounted at `/workspace`.
4. Masks `/workspace/.git` with a tmpfs (only when the host has a `.git` directory).
5. Drops you into `/bin/bash` as the `dev` user.
6. Removes the container when you exit. Volumes survive.

The same project always uses the same set of persistent volumes, so npm globals, shell history, Claude config, and anything under `/opt` carry across sessions.

## Commands

```bash
aibox                  # equivalent to `aibox run`
aibox run              # start an interactive container
aibox info             # print project paths, IDs, image, container, volume names
aibox remove-volume    # delete the 4 persistent volumes for this project (prompts)
aibox remove-volume --force
aibox rebuild-image    # rebuild aibox-default:latest
```

### `aibox run` flags

| Flag                                | Purpose                                                  |
|-------------------------------------|----------------------------------------------------------|
| `-p`, `--port HOST:CONTAINER`       | Publish a port. Repeatable.                              |
| `-e`, `--env KEY=VALUE`             | Set an environment variable. Repeatable.                 |
| `--env-file PATH`                   | Pass a `--env-file` to Docker. Repeatable.               |
| `--shell PATH`                      | Override the default `/bin/bash`.                        |
| `--docker-arg=ARG`                  | Raw passthrough to `docker run`. See note below.         |
| `--user USER`                       | Run as a different user inside the container.            |

**Note on `--docker-arg`:** when the value starts with `--`, use the `=` form (`--docker-arg=--add-host=host.docker.internal:host-gateway`). This is an argparse quirk, not an aibox bug.

## What gets mounted

| Host path                  | Container path  | Kind            |
|----------------------------|-----------------|-----------------|
| current working directory  | `/workspace`    | bind mount (live) |
| `aibox-home-{project-id}`  | `/home/dev`     | named volume    |
| `aibox-tmp-{project-id}`   | `/tmp`          | named volume    |
| `aibox-var-tmp-{project-id}` | `/var/tmp`    | named volume    |
| `aibox-opt-{project-id}`   | `/opt`          | named volume    |

If a `.git` directory exists on the host, a tmpfs is mounted at `/workspace/.git` to mask it inside the container.

## What persists across runs

The four named volumes above. Use them for:

- `/home/dev` — agent config, memories, shell history, npm-global installs.
- `/tmp`, `/var/tmp` — work-in-progress scratch.
- `/opt` — additional tools the agent installs.

Everything else (the rest of `/`) is part of the image and reset every time the container starts.

## What does **not** persist

Everything outside the four volumes. The container is `--rm`, so changes to `/etc`, `/usr`, `/lib` etc. are gone on exit. Persistent system changes belong in the Dockerfile — rebuild the image with `aibox rebuild-image`.

## Why your `.git` history is hidden

Your real commit history should stay under your control. The host `.git` directory is masked with a tmpfs, so even though `git` is available in the container, the agent sees an empty `.git` and cannot read or rewrite your history. You review and commit changes from your own IDE/terminal where the real `.git` lives.

## Git is installed, but `gh` and credentials are not

`git` is included in the image because agents legitimately need it — cloning public repos, installing Claude Code plugins and marketplaces (which are git-based), pulling reference code. What's deliberately absent:

- **No GitHub CLI (`gh`)** — the tool most geared toward authenticated remote GitHub operations.
- **No credentials** — no SSH keys, no GitHub tokens, no `~/.gitconfig`. So the agent can `git clone` public URLs and even `git init`/`commit` locally inside `/workspace`, but it **cannot push to your remotes or authenticate as you**.
- **Masked host `.git`** — see above.

Net effect: the agent gets git's read-only and local-only powers, not the ability to act against your remote repositories.

## Why host credentials aren't mounted

The container only sees `/workspace` and its four named volumes. Specifically, it does **not** see:

- `~/.ssh`
- `~/.dbt`, `profiles.yml`
- Snowflake credentials
- GitHub credentials, gh tokens
- AWS, GCP, Azure credential folders
- The Docker socket

This is particularly important for dbt and data projects: the agent can edit your project files without being able to query your warehouse.

## `.aibox.toml`

Optional, lives in the project root. CLI flags compose with it:

- list fields (`ports`, `env`, `env_files`, `docker_args`) — CLI appends to config.
- `shell` — CLI `--shell` overrides config.
- `user` — comes from CLI only.

Example:

```toml
ports = ["3000:3000", "8000:8000"]

env = [
  "NODE_ENV=development",
]

env_files = [
  ".env",
]

shell = "/bin/bash"

docker_args = [
  "--add-host=host.docker.internal:host-gateway",
]
```

`aibox` will not create this file automatically. It's optional.

## Removing a project's volumes

```bash
aibox remove-volume          # prompts before deleting
aibox remove-volume --force
```

This deletes only the volumes for the current project. Other projects' volumes are untouched.

## Rebuilding the image

```bash
aibox rebuild-image
```

Run this after changing the Dockerfile, or whenever you want to refresh the base image. All projects share the same `aibox-default:latest` image.

## Known limitations

- **Symlinked project directories are not tested cross-platform.** They likely work on macOS and Linux as-is. Behaviour on Windows (junction points vs symlinks, and symlinks that cross between WSL and Windows paths) is unverified. File an issue if you hit something.

## Non-goals

For the MVP, aibox deliberately does not support:

- Docker Compose
- Custom images (one default image only)
- Mounting the Docker socket
- GitHub authentication (`gh`, tokens, SSH keys) — `git` itself is installed, but the agent can't authenticate to remotes
- Installing Claude Code into the image (do that inside the container)
- Cloud credential mounting
- SSH key mounting
- Automatic port detection
- A background daemon
- Remote VM support
- Multi-agent orchestration
- UI/dashboard

See [`ROADMAP.md`](./ROADMAP.md) for future work and [`PROMPT.md`](./PROMPT.md) for the full specification.

## Contributing

See [`CONTRIBUTING.md`](./CONTRIBUTING.md) for development setup, test commands, and the repo layout.

For security issues, see [`SECURITY.md`](./SECURITY.md).

## License

[MIT](./LICENSE) © Vince Maina
