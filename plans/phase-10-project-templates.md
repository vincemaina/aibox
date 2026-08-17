# Phase 10: Project templates

## Goal

`aibox init` seeds a project with a personal set of agent-guidance files — `CLAUDE.md`, `claude-best-practices.md`, `.claude/skills/`, tool-choice conventions — pulled from a template repository, **merging** into whatever the project already has rather than overwriting it.

## Context

Every project the user starts wants the same scaffolding: how Claude should work, which tools to reach for (e.g. "use `backlog.md` for project management"), which skills should be available. Copying that by hand each time is the problem this solves.

This is the concrete form of the note already in `CLAUDE.md` ("aibox should deploy these practices into target projects") and of the `aibox init` item in `ROADMAP.md`'s future-work list. That note also fixes one decision up front: **templates apply on explicit `aibox init` only, never automatically on `aibox run`.** `aibox run` must not write to the user's project.

## Design

### Two destinations

The files worth templating fall into two groups that want opposite handling, so a template declares both:

```
template-repo/
├── workspace/          → merged into the project, on `aibox init` only
│   ├── CLAUDE.md
│   ├── claude-best-practices.md
│   └── .aibox.toml
└── home/               → synced into /home/dev, on every `aibox run`
    └── .claude/skills/
```

- **`workspace/`** is repo guidance: committed, seen by collaborators and by Claude running on the *host*. It's the user's source tree, so it is never overwritten without consent and only ever touched by an explicit `aibox init`.
- **`home/`** is personal agent tooling. It lands on the per-project home volume, which is aibox-managed disposable state, so it can be refreshed on every run without asking. This keeps personal skills out of the repo entirely — useful for projects you don't own.

`home/` sync is last-writer-wins across templates and overwrites its own files each run: the template is the source of truth. It only ever touches paths the template defines; the rest of `/home/dev` is left alone.

Both directories are optional; a template may provide only one.

### The built-in agent briefing

aibox seeds its own `.claude/CLAUDE.md` through the same `home/` path, before any user template, so every box gets it whether or not templates are configured.

It's there to correct an agent's default assumption that the user's machine is its machine. Without it agents hunt for credentials that were never mounted, retry pushes they cannot authenticate, and treat deliberate protections as bugs to route around — each of which costs turns and can end in the agent doing something unwanted. The document states where it is, what won't work and *why*, what it can freely do, and a short list of absolute rules (no sandbox escape, nothing outside `/workspace`, no other repos, no pushing to `main`, never defeat a protection).

Because it's written first, a template supplying its own `home/.claude/CLAUDE.md` overrides it. That's the right precedence — the user's word wins — and it's documented so anyone doing it knows to carry the guidance across. Source lives at `src/aibox/image/agent-briefing.md` and ships as package data.

### Where the template is configured

Templates are a property of *the user*, not of a project — the whole point is that a brand-new empty directory can be seeded. A project-local `.aibox.toml` can't express that, so this phase introduces aibox's first **user-level config**, at `$XDG_CONFIG_HOME/aibox/config.toml` (falling back to `~/.config/aibox/config.toml`, and the platform equivalent on Windows):

```toml
templates = [
  "https://github.com/vincemaina/claude-starter",
  "~/dotfiles/aibox-template",           # local paths allowed too
]
```

A list, applied in order, so a general starter can be layered with a language-specific one. A project's `.aibox.toml` may override with its own `templates` key.

### Fetching and cache freshness

Remote templates are `git clone --depth 1` into a cache at `~/.cache/aibox/templates/<hash-of-url>`. Cloning does not execute hooks from the remote, so the fetch itself is safe. The template's own `.git` is never copied into the target.

The first implementation cached **forever**, refreshed only by `aibox init --refresh`. That was a genuine defect rather than a missing nicety: `aibox run` never passed `refresh`, so editing your template repo could never reach a new box, and the documented promise that `home/` "refreshes on every run" was true only relative to the cache — not to the repo that is actually the source of truth.

Now:

- **A 24-hour TTL.** Past that, the next command re-fetches, so a pushed change propagates on its own. Under it, `aibox run` stays off the network.
- **`--refresh` on `run` as well as `init`**, and `aibox setup` always fetches fresh, since reporting the structure of a stale clone during setup would be misleading.
- **Local paths are never cached.** Read in place, so they're always current — which makes a local path the natural way to iterate on a template before pushing.
- **Fail-soft.** A failed fetch with a usable cached copy warns and proceeds. Being offline must not stop a box from starting.
- **Staged swap.** Re-cloning goes to `<name>.incoming` and is renamed over the cache only on success. Deleting first would destroy the copy the offline fallback depends on — the first cut of this had exactly that bug.

`file://` counts as remote. It's a git URL pointing at a repository, not a directory of template files, so it has to go through clone.

### Merge semantics for `workspace/`

Walk the template tree; for each file, compute the target path and classify it:

- Target missing → **create**.
- Target exists with **identical bytes** → **unchanged**. Not a conflict, and crucially not a prompt: this is what makes re-running `aibox init` a silent no-op after the user has already accepted everything.
- Target exists and differs → **conflict**, resolved interactively (default):

  ```
  CLAUDE.md already exists.
    [k] keep mine   [r] replace   [b] keep both   [d] diff
  > _
  ```

  `keep both` writes the template's copy as `CLAUDE.aibox.md`, numbering upward if that's taken too.

Interactive prompting can't be the only path, so `--on-conflict {ask,skip,replace,keep-both}` forces a policy, and a non-TTY stdin falls back to `skip` with a printed report rather than hanging. `--yes` is an alias for `--on-conflict skip`.

Directories always merge; an existing `.claude/skills/` gains the template's skills without losing its own. Nothing is ever deleted, and the template's own `.git` is never copied.

`aibox init` prints a summary of what it did, and `--dry-run` reports the plan without writing (treating conflicts as skips).

### Syncing `home/` into the container

`aibox run` stages every template's `home/` into one directory under the cache (in config order, later wins), bind-mounts it read-only at `/run/aibox-seed`, and `entrypoint.sh` copies it into `/home/dev`.

The copy has to happen in *both* entrypoint branches. On Linux the container starts as root and drops via gosu, so the copy is followed by a chown; on macOS/Windows it starts as `dev` directly, and `dev` can write its own home. Seeding only the root branch would silently do nothing on macOS.

## Tasks

1. `userconfig.py` — locate and parse the user-level config. Separate from `config.py`: different file, different scope, different keys.
2. `templates.py` — resolve a ref (git URL or local path) to a directory, clone-and-cache for remotes.
3. `templates.py` — the merge walk producing a `MergePlan` of create/unchanged/conflict entries, so `--dry-run`, the interactive path, and the forced policies all share one classifier.
4. `templates.py` — stage the combined `home/` seed for `aibox run`.
5. `entrypoint.sh` — copy `/run/aibox-seed` into `/home/dev` in both branches.
6. `cli.py` — `aibox init`; wire the seed mount into `aibox run`.
7. `config.py` — project-level `templates` override, distinguishing absent from empty.
8. Tests.

## Files created or modified

```
src/aibox/userconfig.py    # new — user-level config
src/aibox/templates.py     # new — fetch, cache, merge, stage
src/aibox/image/           # renamed from src/aibox/templates/ to free the name
src/aibox/cli.py           # aibox init; seed mount on run
src/aibox/config.py        # project-level `templates` override
src/aibox/docker.py        # seed mount in build_run_args
src/aibox/image/entrypoint.sh
tests/test_templates.py, tests/test_userconfig.py   # new
README.md CLAUDE.md ROADMAP.md pyproject.toml
```

## Acceptance criteria

All verified end-to-end against a real template repo and a real container:

- ✅ `aibox init` in an empty directory reproduces the template's `workspace/`.
- ✅ In a project with a differing `CLAUDE.md` and its own `.claude/skills/mine/`: prompts for `CLAUDE.md`, `[d]` shows a unified diff, `[b]` writes `CLAUDE.aibox.md`, `mine/` is untouched, and the template's `review/` skill is added alongside.
- ✅ Files already matching the template are reported `unchanged` and never rewritten or re-prompted.
- ✅ Non-TTY stdin never hangs; it prints why and falls back to skip.
- ✅ `--dry-run` writes nothing.
- ✅ A local-path template works with no network.
- ✅ The template's `.git` never appears in the target.
- ✅ After a run, `home/.claude/skills/personal/` is in the box owned by `dev` and writable, and absent from the project's `git status`.

**Not fully idempotent, by design.** A file the user chose to *keep* still differs from the template, so it is re-reported (and re-prompted) next time. That's the correct signal — the divergence is still pending — and `--yes` / `--on-conflict skip` makes it quiet. Recording per-file "I already decided this" would need persistent state; deliberately not built.

## Decided

- **Two destinations** (`workspace/` + `home/`), fixed by convention.
- **Interactive conflict resolution** by default, with `--on-conflict` and a non-TTY fallback.
- **User-level config**, overridable per project.

## Onboarding (added after first use)

A config file nobody knows about gets used by nobody, so two interactive flows were added in `onboarding.py`:

- **First-run setup.** When `~/.config/aibox/config.toml` is missing, `aibox run` walks the user through choosing a template, then writes the file. `aibox setup` re-runs it on demand. Skipping still writes the file (with `templates = []`), so the question is asked exactly once rather than every run.
- **Structure validation.** Setup resolves each ref and reports what it found. A template with neither `workspace/` nor `home/` would silently do nothing, so it prints the expected layout, lists stray top-level entries (the usual mistake is files at the repo root), and links to the docs. The user can still opt to keep it.
- **Per-project import offer.** On `aibox run` in a project with unimported template files: `[Y]es / [n]ot now / [never]`. `never` is recorded per project ID in `~/.local/state/aibox/projects.json`.

Two design points worth keeping:

- **Nothing may block a non-interactive run.** Both flows check `interactive()` (stdin *and* stdout are TTYs) and return quietly otherwise. A hang in CI is worse than a missed prompt, so tests monkeypatch `_ask` to fail and assert silence.
- **Config and state are separate directories.** Config is the user's to edit; state is aibox's to rewrite. Clearing state re-asks a question, it never destroys settings.

The offer is stateless about "already imported" — it simply asks whether the merge plan would *create* anything. That keeps it silent once a project is seeded without another marker file to maintain.

## Still open

- **Per-template destination config.** The `workspace/` + `home/` split is convention for now. A future `aibox.toml` *inside* the template could let each template declare its own mapping, decided when the template is set up rather than baked into the directory layout.
- **Templates are a trust boundary.** A template can carry `.claude/settings.json` with hooks, which then run in *host* Claude sessions once committed. Fine for your own template, dangerous for someone else's. Consider warning on first use of an unseen ref.
- **Variable substitution** (project name, year, author) is out of scope. It turns a file copy into a templating engine. Revisit only if plain copying proves insufficient.
