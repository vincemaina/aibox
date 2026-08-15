# Phase 9: Git access modes

## Goal

Let the agent do real Git work — commit, branch, rebase — against the project's actual history, while keeping the paths that would let it execute code on the *host* closed.

## Context

The original design masked `.git` with a tmpfs on the grounds that the host's commit history is the safety net and the agent shouldn't be able to touch it. In practice that's the wrong trade:

- The agent can't arrange its work into a readable commit history, which is exactly the thing that makes an agent's output reviewable.
- It can't read history either, so it has no idea what the project's conventions or recent direction are.
- The protection it bought was largely redundant. There are no credentials in the container and no `gh`, so the agent can't push. Damage is local and recoverable from the remote.

The responsibility for protecting shared history moves to where it belongs: **branch protection rules on the remote**, and keeping repos private. aibox's job is to stop the agent reaching the *host*, not to stop it using Git.

### The part that genuinely is dangerous

Unmasking `.git` wholesale is not safe, and this is the reason the phase needs more than deleting one line. Git executes commands named in two places inside a git directory, and it does so **on the host**, under the user's account, the next time they run git:

- `hooks/` — `pre-commit`, `post-checkout`, and friends. An agent that writes `.git/hooks/pre-commit` gets arbitrary host execution the next time you commit from your IDE.
- `config` — `core.pager`, `core.editor`, `core.sshCommand`, `core.fsmonitor`, `filter.*.clean` / `.smudge`, `diff.*.textconv`, `alias.*`, `include.path`. All of these name a command, and all are read from the repo-local config.

That is a sandbox escape, not a git-hygiene issue, so both are held back even in the most permissive mode.

Repos with submodules have more than one git directory — `.git/modules/<path>/` is a full git dir with its own `config` and `hooks/`. Protecting only the top-level `.git` would leave a hole that's invisible until someone uses a submodule, so the protection is applied per git dir, enumerated at resolve time.

## Design

Three modes, selected by `--git` or `.aibox.toml`'s `git` key. `.git` arrives in the container for free via the `/workspace` bind mount, so every mode layers something on top of it:

| Mode | Mount(s) | Agent can |
|------|----------|-----------|
| `masked` | tmpfs over `/workspace/.git` | nothing — sees an empty git dir (the pre-phase-9 behaviour) |
| `readonly` | `.git` bind-mounted over itself with `readonly` | read history; change nothing |
| `commit` *(default)* | tmpfs over each `hooks/`; each `config` re-bound `readonly` | read history, commit, branch, rebase |

`commit` is the default, per the stance change above.

Read-only `config` blocks `git config`, `git remote add`, and `--set-upstream` inside the container. That's acceptable: with no push access those are near-useless, and the agent still has a writable `~/.gitconfig` on the per-project home volume for anything it genuinely needs to set.

Because the host's global `~/.gitconfig` is not mounted, a repo that relies on it for identity would fail with "please tell me who you are". `commit` mode therefore passes `GIT_AUTHOR_*` / `GIT_COMMITTER_*` defaulting to `aibox agent <agent@aibox.local>`. These go in before the user's own `-e` flags so `--env GIT_AUTHOR_NAME=...` overrides them, and the distinct identity makes sandbox commits obvious in `git log`.

## Tasks

1. `identity.py`: add `git_dirs(cwd)` returning the main `.git` plus every `.git/modules/**` git dir; expose it on `ProjectIdentity` so `build_run_args` stays free of filesystem I/O.
2. `docker.py`: add `GIT_MODES`, `DEFAULT_GIT_MODE`, `GIT_IDENTITY`; replace `RunSpec.mask_git` with `git_mode`; add `_git_mount_args`; emit the identity env in `commit` mode only.
3. `config.py`: accept and validate the `git` key; `--git` overrides config, config overrides the default.
4. `cli.py`: add `--git` with `choices`; make `aibox info` read the config so it reports the mode the project will actually use; replace the `Git hidden:` summary line with `Git access:`.
5. Tests: mount composition per mode, submodule coverage, identity env precedence, config validation, CLI flag plumbing.
6. Docs: `README.md`, `CLAUDE.md`, `SECURITY.md`.

## Files created or modified

```
src/aibox/identity.py     # git_dirs(), ProjectIdentity.git_dirs
src/aibox/docker.py       # git_mode, _git_mount_args, GIT_IDENTITY
src/aibox/config.py       # `git` key + validation
src/aibox/cli.py          # --git flag, info reads config, summary line
tests/test_docker.py      # TestGitModes
tests/test_config.py      # git load/validate/merge
tests/test_cli.py         # flag plumbing, summary field
README.md CLAUDE.md SECURITY.md ROADMAP.md
```

## Acceptance criteria

All verified end-to-end against a real repo, not just unit tests:

- `masked` — 0 commits visible, commit blocked.
- `readonly` — history visible, commit blocked.
- `commit` — history visible; commit and branch succeed; the commit is present in the host repo afterwards.
- In every mode, writing `.git/hooks/pre-commit` and setting `core.pager` from inside the container fail, and the host's existing hook and config are byte-for-byte unchanged after the run.
- Commits are attributed to `aibox agent <agent@aibox.local>` when the repo names no identity.

## Decisions flagged

- **Default is `commit`.** This is a deliberate loosening of a documented guarantee. `masked` remains one flag away, and `SECURITY.md` is updated so the advertised boundary matches reality.
- **`.git` as a *file*** (linked worktrees, submodule checkouts) is treated as "no git dir". The real git dir lives outside the project and isn't bind-mounted, so there's nothing to protect. Documented as a limitation rather than handled.
- **`.git/worktrees/<name>/config.worktree`** is not currently covered. It only exists for linked worktrees, which are already out of scope per the above. Revisit if worktree support lands.
- **Rejected: making `.git/config` writable.** It would restore `git remote add` at the cost of reopening the largest host-execution surface. Not worth it when the agent can't push anyway.
