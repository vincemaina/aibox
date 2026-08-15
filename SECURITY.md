# Security policy

`aibox` exists to provide a sandbox between AI coding agents and a developer's host machine. If you find a way the sandbox can be bypassed, please report it responsibly.

## What's in scope

Bug reports are welcome for any path that breaks the documented isolation guarantees:

- **Container escape** — code running inside the container reaching the host filesystem outside `/workspace`.
- **Credential leak** — host paths like `~/.ssh`, `~/.dbt`, `~/.aws`, `~/.gnupg`, `~/.gitconfig`, etc. becoming readable from inside the container under any configuration.
- **Host code execution via `.git`** — anything the agent can write that causes *host-side* git to run a command. `.git/hooks/` and `.git/config` (and their submodule equivalents under `.git/modules/`) are held read-only in every `--git` mode precisely to prevent this; a way around that is a real vulnerability.
- **`.git` exposure beyond the selected mode** — e.g. history readable under `--git masked`, or `.git` writable under `--git readonly`.
- **Host writes outside `/workspace`** — writes inside the container affecting files outside the project directory on the host.
- **Docker socket exposure** — any path that surfaces `/var/run/docker.sock` or equivalent to the container without an explicit opt-in.

## What's out of scope

- Behaviour requiring `--user root` plus a deliberately permissive `--docker-arg`. Users can give themselves enough rope; that's expected.
- Anything the agent can do *inside* `/workspace`. That includes deleting or rewriting project files.
- **Anything the agent does to your local git history** under the default `--git commit` mode — committing, branching, rebasing, resetting, deleting branches. This is intended behaviour, not a vulnerability. The agent has no credentials and no `gh`, so it cannot push; the safety net is the remote plus branch protection rules, and the reflog. Use `--git readonly` or `--git masked` if you want the old guarantee.
- General Docker daemon security. That's upstream of `aibox`.

## How to report

Open a private security advisory via GitHub:

> https://github.com/vincemaina/aibox/security/advisories/new

Please include:

- A clear description of the issue.
- Reproduction steps (commands, `.aibox.toml` content, host setup).
- The impact you believe it has.
- A suggested fix if you have one.

Expect an acknowledgement within a few days. `aibox` is a personal project, not a funded one — fixes are best-effort.

## Supported versions

`aibox` is pre-1.0. Only the latest commit on `main` is supported. There is no LTS branch.
