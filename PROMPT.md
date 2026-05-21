# Build `aibox`: a Python CLI for isolated AI coding containers

## Goal

Build a Python command line tool called `aibox`.

`aibox` should let me run a disposable Docker development container from any local project directory. The main use case is running Claude Code or another AI coding agent inside a container where it can edit the current project files, but cannot access the rest of my machine, my credentials, my dbt profiles, my Snowflake credentials, or my remote GitHub repositories.

I will install this CLI locally using:

```bash
pip install -e .
````

After installation, the `aibox` command should be globally available.

---

## Primary workflow

From any project directory:

```bash
cd ~/projects/my-project
aibox
```

This should:

1. Detect the current working directory.
2. Derive a stable project ID from the current folder name plus a short hash of the resolved absolute path.
3. Build the default Docker image if it does not already exist.
4. Start an interactive Docker container.
5. Bind mount the current project directory to `/workspace`.
6. Mount project-specific persistent Docker volumes for container/user state.
7. Hide the host `.git` directory inside the container.
8. Drop me into an interactive shell.
9. Delete the container when it exits.
10. Reuse the same project-specific volumes the next time I run `aibox` from the same directory.

The project files should remain my real local files, edited through the bind mount. The container itself should be disposable.

---

## Target platform

Target macOS for now.

Do not spend time solving Windows path issues.

Use clean Python/path handling where reasonable, but MVP support is macOS.

---

## Package requirements

Use Python.

Use a `pyproject.toml`.

Use a `src/` layout.

Expose a CLI command called:

```bash
aibox
```

Use only the Python standard library unless there is a very strong reason not to.

Use `subprocess.run([...])` with argument lists.

Do not use `shell=True`.

Keep the implementation simple, readable, and maintainable.

Suggested structure:

```text
aibox/
  pyproject.toml
  README.md
  src/
    aibox/
      __init__.py
      cli.py
      config.py
      docker.py
      identity.py
      templates/
        Dockerfile
```

This structure is a suggestion, not a hard requirement.

---

## Commands

Implement these commands:

```bash
aibox
aibox run
aibox info
aibox remove-volume
aibox rebuild-image
```

### `aibox`

Equivalent to:

```bash
aibox run
```

### `aibox run`

Starts an interactive Docker container for the current project.

Default shell:

```bash
/bin/bash
```

### `aibox info`

Prints useful information for the current project:

* resolved project path
* project folder slug
* project ID
* Docker image name
* expected container name prefix
* persistent volume names
* whether `.git` exists and will be hidden

### `aibox remove-volume`

Deletes the persistent Docker volumes for the current project.

This should delete:

* home volume
* tmp volume
* var tmp volume
* opt volume

Ask for confirmation before deleting, unless `--force` is passed.

Example:

```bash
aibox remove-volume
aibox remove-volume --force
```

### `aibox rebuild-image`

Rebuilds the default `aibox` Docker image.

---

## Project identity and naming

Derive a stable project ID from:

1. a slugified version of the current folder name
2. a short hash of the resolved absolute project path

Example:

```text
Folder name:
  my-project

Resolved absolute path:
  /Users/vince/projects/my-project

Project ID:
  my-project-a1b2c3d4
```

Use the resolved absolute path for the hash so that two projects with the same folder name do not collide.

Use an 8-character hash.

Example naming:

```text
Project ID:
  my-project-a1b2c3d4

Docker image:
  aibox-default:latest

Container name:
  aibox-my-project-a1b2c3d4-<unique-session-suffix>

Volumes:
  aibox-home-my-project-a1b2c3d4
  aibox-tmp-my-project-a1b2c3d4
  aibox-var-tmp-my-project-a1b2c3d4
  aibox-opt-my-project-a1b2c3d4
```

Container names should be unique per session/process, not fixed per project.

This should allow me to run `aibox` in two terminals from the same project directory at the same time. Both containers should share the same project-specific persistent volumes, but closing one terminal should only stop/remove that one container.

Use a readable unique suffix, for example a timestamp plus short random token:

```text
aibox-my-project-a1b2c3d4-20260521-abc123
```

---

## Docker image

The default Dockerfile should live inside the `aibox` project.

The CLI should auto-build the default image if it does not exist.

Default image name:

```text
aibox-default:latest
```

Do not support custom images yet.

Do not use Docker Compose yet.

Do not mount the Docker socket.

Do not install Claude Code into the image. I will install Claude manually inside the container if needed.

---

## Default Docker image contents

Use a reasonably small base image, for example:

```Dockerfile
python:3.12-slim
```

Create a non-root user:

```text
user: dev
home: /home/dev
workspace: /workspace
```

Install useful basic tools:

* bash
* curl
* ca-certificates
* build-essential
* vim or nano
* jq
* ripgrep
* fd-find
* unzip
* nodejs
* npm

Do **not** install:

* git
* GitHub CLI / `gh`

The point is that Claude should not be encouraged to interact with version control or remote GitHub repositories. Git control should stay on the host machine, managed by me.

Set up user-local tool installation paths so that tools installed by the `dev` user are more likely to persist:

```Dockerfile
ENV HOME=/home/dev
ENV NPM_CONFIG_PREFIX=/home/dev/.npm-global
ENV PATH=/home/dev/.npm-global/bin:/home/dev/.local/bin:/opt/bin:$PATH
```

Ensure these directories exist and are owned by `dev`:

```text
/home/dev
/home/dev/.npm-global
/home/dev/.local
/opt
```

Make `/opt` writable by `dev`.

---

## Docker runtime behaviour

When `aibox run` starts a container:

Mount the current project directory to:

```text
/workspace
```

Mount persistent Docker volumes to these container paths:

```text
/home/dev
/tmp
/var/tmp
/opt
```

Use project-specific named Docker volumes:

```text
aibox-home-<project-id>:/home/dev
aibox-tmp-<project-id>:/tmp
aibox-var-tmp-<project-id>:/var/tmp
aibox-opt-<project-id>:/opt
```

Use:

```text
--rm
-it
--workdir /workspace
```

Run as user:

```text
dev
```

Default command:

```bash
/bin/bash
```

The project directory should be a live bind mount to the actual host working directory, not copied.

The container should be deleted when it exits.

The volumes should remain.

---

## Persistence model

The container itself is disposable.

These paths persist per project:

```text
/home/dev
/tmp
/var/tmp
/opt
```

These paths do not persist and should come from the image:

```text
/bin
/sbin
/usr
/usr/local
/lib
/lib64
/etc
/var, except /var/tmp
```

Important principle:

* User/agent state should persist in Docker volumes.
* System environment should be defined in the Dockerfile and changed by rebuilding the image.
* Do not try to persist the whole container filesystem.

The intended mental model:

```text
/workspace  = real project files on my Mac
/home/dev   = Claude/user home, memories, config, npm global installs, shell history
/tmp        = persistent temp files for this project
/var/tmp    = persistent longer-lived temp files
/opt        = persistent optional tools/apps Claude may create or install

Everything else = disposable image/container filesystem
```

---

## Git safety

The host project may have a `.git` directory.

By default, hide the host `.git` directory inside the container.

Docker does not support excluding `.git` from a bind mount directly, so mask it after mounting the project by mounting a tmpfs over:

```text
/workspace/.git
```

Example:

```bash
--mount type=tmpfs,destination=/workspace/.git
```

Only add this tmpfs mount if the host project actually has a `.git` directory.

Do not install `git` in the image.

Do not add an `--allow-git` option unless it is trivial. The MVP default is no Git access.

The point is:

* Claude can edit working files.
* Claude cannot inspect or modify the host `.git` directory.
* Claude cannot run git commands because git is not installed.
* I manage Git from my host IDE/terminal so I can review everything before committing.

---

## Credential safety

Do not mount the host home directory.

Do not mount:

* `~/.ssh`
* `~/.dbt`
* cloud credential folders
* Snowflake credentials
* dbt profiles
* GitHub credentials

Do not mount the Docker socket.

The container should only see:

* the current project directory at `/workspace`
* its own persistent `/home/dev`
* its own persistent `/tmp`
* its own persistent `/var/tmp`
* its own persistent `/opt`

This is particularly important for dbt projects. I want the AI to be able to edit dbt project files, but not have access to `profiles.yml` or live warehouse credentials.

---

## Project config

Support an optional project-level config file:

```text
.aibox.toml
```

The CLI should look for this file in the current project root.

Do not create `.aibox.toml` automatically during normal `aibox run`.

It is okay to add an `aibox init` command later, but not needed now.

The config file should support:

```toml
ports = ["3000:3000", "8000:8000"]

env = [
  "NODE_ENV=development"
]

env_files = [
  ".env"
]

shell = "/bin/bash"

docker_args = [
  "--add-host=host.docker.internal:host-gateway"
]
```

CLI flags should override or extend `.aibox.toml` values in a sensible way.

For the MVP, simple behaviour is fine:

* config provides defaults
* CLI-provided ports/env/env-files/docker-args are appended
* CLI-provided shell overrides config shell

---

## CLI flags for `aibox run`

Support:

```bash
-p / --port
```

Repeatable.

Example:

```bash
aibox run -p 3000:3000 -p 8000:8000
```

Support:

```bash
-e / --env
```

Repeatable.

Example:

```bash
aibox run -e NODE_ENV=development
```

Support:

```bash
--env-file
```

Repeatable.

Example:

```bash
aibox run --env-file .env
```

Support:

```bash
--shell
```

Default:

```bash
/bin/bash
```

Support:

```bash
--docker-arg
```

Repeatable. This should pass through extra raw Docker arguments for advanced usage.

Support:

```bash
--user
```

Optional override, for example:

```bash
aibox run --user root
```

If no user is provided, run as `dev`.

---

## Startup output

On `aibox run`, print a short startup summary before entering the container.

Include:

```text
Project path:
Project ID:
Container:
Image:
Home volume:
Tmp volume:
Var tmp volume:
Opt volume:
Git hidden:
```

Then start the interactive shell.

Example:

```text
Starting aibox

Project path:   /Users/vince/projects/my-project
Project ID:     my-project-a1b2c3d4
Container:      aibox-my-project-a1b2c3d4-20260521-abc123
Image:          aibox-default:latest
Home volume:    aibox-home-my-project-a1b2c3d4
Tmp volume:     aibox-tmp-my-project-a1b2c3d4
Var tmp volume: aibox-var-tmp-my-project-a1b2c3d4
Opt volume:     aibox-opt-my-project-a1b2c3d4
Git hidden:     yes
```

---

## Error handling

Handle expected errors cleanly.

If Docker is not installed or not available, print a clear error.

If Docker is not running, print a clear error.

If the image build fails, print a clear error.

If Docker run fails, return the Docker exit code.

If volume removal fails, print a clear error.

Avoid stack traces for normal user-facing errors.

---

## README requirements

Create a `README.md` explaining:

1. What `aibox` is.
2. How to install it locally:

```bash
pip install -e .
```

3. Basic usage:

```bash
cd my-project
aibox
```

4. What gets mounted.
5. What persists.
6. What does not persist.
7. Why `.git` is hidden.
8. Why Git/GitHub CLI are not installed.
9. Why host credentials are not mounted.
10. Example `.aibox.toml`.
11. How to remove a project’s persistent volumes:

```bash
aibox remove-volume
```

12. How to rebuild the image:

```bash
aibox rebuild-image
```

---

## Non-goals for MVP

Do not build these yet:

* Docker Compose support
* custom image support
* Docker socket mounting
* GitHub integration
* installing Claude Code into the image
* cloud credential mounting
* SSH key mounting
* Windows support
* automatic port detection
* a background daemon
* remote VM support
* multi-agent orchestration
* UI/dashboard

Keep the MVP focused.

---

## Acceptance criteria

After implementation, I should be able to run:

```bash
pip install -e .
```

Then from any project:

```bash
cd ~/projects/example
aibox
```

Expected behaviour:

* If the default image does not exist, it is built automatically.
* A container starts interactively.
* The project is available at `/workspace`.
* The shell starts in `/workspace`.
* `/home/dev`, `/tmp`, `/var/tmp`, and `/opt` persist across runs for the same project.
* The container is removed when I exit.
* The volumes remain after exit.
* Running `aibox` again from the same project reuses the same volumes.
* Running `aibox` from another project uses different volumes.
* Running `aibox` twice from the same project in two terminals creates two separate containers that share the same project volumes.
* The host `.git` directory is not visible inside the container.
* Git is not installed in the container.
* Host credentials are not mounted.
* `aibox info` prints the expected names and paths.
* `aibox remove-volume` removes the project volumes after confirmation.
* `aibox rebuild-image` rebuilds the default image.

---

## Implementation notes

Please first inspect this prompt and create a short implementation plan before coding.

Keep the implementation minimal and robust.

Prefer boring, readable Python over clever abstractions.

Do not over-engineer this into a platform.

The goal is a clean, safe, local AI coding container workflow.
