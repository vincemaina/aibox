# aibox

`aibox` is a small Python CLI that launches a disposable Docker container from any local project directory. It is built for running Claude Code or another AI coding agent inside a sandbox where the agent can edit the current project files but cannot see your home directory, credentials, dbt profiles, Snowflake credentials, GitHub credentials, or your `.git` history.

> macOS only. Windows path edge cases are explicitly out of scope.

## Install

```bash
pip install -e .          # runtime only
pip install -e ".[dev]"   # with pytest (for development)
```

This exposes a global `aibox` command.

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

## Why `.git` is hidden

Version control should stay on the host. The agent should be able to edit working files freely, but it should not inspect your commit history, push to remotes, or make commits on your behalf — that work happens in your IDE/terminal where you can review changes before publishing them.

## Why Git and GitHub CLI aren't installed

Same reason. The image doesn't include `git` or `gh` so the agent can't reach for them out of habit. If you need git operations, do them from the host.

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

## Non-goals

For the MVP, aibox deliberately does not support:

- Docker Compose
- Custom images (one default image only)
- Mounting the Docker socket
- GitHub integration (`gh`, tokens)
- Installing Claude Code into the image (do that inside the container)
- Cloud credential mounting
- SSH key mounting
- Windows
- Automatic port detection
- A background daemon
- Remote VM support
- Multi-agent orchestration
- UI/dashboard

See `ROADMAP.md` for future work and `PROMPT.md` for the full specification.
