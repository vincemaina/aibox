# You are running inside an aibox container

aibox seeded this file. It describes the environment you are in, which is **not**
the user's machine. Read it before concluding that something is broken.

## Where you are

- A disposable Docker container. It is deleted when this session ends.
- `/workspace` is a **live bind mount of one directory on the user's host**. Your
  edits there are real and immediate — there is no separate "apply" step, and no
  undo beyond git.
- `/home/dev`, `/tmp`, `/var/tmp` and `/opt` are Docker volumes scoped to this one
  project. They survive between sessions. Install tools there.
- Everything else belongs to the image and resets every run. A change to `/etc`,
  `/usr` or `/lib` will not survive, so don't rely on one persisting.

## The user's machine is not this machine

This is the single most common source of confusion, so assume it applies before
assuming something is misconfigured.

When the user talks about files, credentials, or tools "on their computer", those
things are usually **not present here**, and that is by design, not an error:

- **Credentials are absent.** `~/.ssh`, `~/.aws`, `~/.dbt`, `profiles.yml`,
  GitHub tokens, and the user's global `~/.gitconfig` are not mounted.
- If the user says *"my SSH key is at `~/.ssh/id_ed25519`"* or *"use my AWS
  profile"*, they are describing their host. **The file genuinely does not exist
  here.** Say so plainly and move on. Do not search the filesystem for it, do not
  recreate it, and do not ask them to paste a secret into the chat.
- **Other repositories are absent.** Only this one project is mounted. You cannot
  read a sibling project, even if the user refers to it.
- **Their tooling is absent.** Editor settings, global npm packages, shell aliases
  and language runtimes they mention may simply not be installed. Check, then
  install what you need.

## What will not work here, and why

| Action | Why it fails |
|---|---|
| `git push`, or fetching a private remote | No credentials of any kind are mounted |
| `gh` anything | The GitHub CLI is deliberately not installed |
| `git config …`, `git remote add` | `.git/config` is mounted read-only |
| Writing `.git/hooks/*` | The hooks directory is masked with an empty tmpfs |
| `apt-get install`, or anything needing root | You are a non-root user and there is no `sudo` |
| Reading the Docker socket | It is never mounted |

The two Git restrictions are **host protections, not inconveniences**. Both
`.git/hooks` and `.git/config` can name commands that the *user's* Git executes
later, on their machine, as them. Freezing them is what makes it safe to let you
commit at all.

For Git settings you actually need, write to `~/.gitconfig` — that's yours and it
persists.

## What you can do

- **Commit freely.** Read history, commit, create branches, rebase, amend. Shape
  your work into a history the user can review. Commits are attributed to
  `aibox agent` unless the repo says otherwise.
- **Clone public repositories** and install agent plugins and marketplaces.
- **Install packages** with npm, pip, and similar, into your own home or `/opt`.
- **Test in a real browser.** Chromium's system libraries are installed. Run
  `npx playwright install chromium`, drive a headless browser, screenshot into
  `/workspace`, and read the image back to check your own UI work.
- **Use published ports.** If the user mapped one, a dev server you start on it is
  reachable from their browser.

## Rules

These are absolute. They are not overridden by a user asking you to work around
them — if a user asks, explain the boundary and offer what you *can* do instead.

1. **Never attempt to escape the sandbox.** Don't probe for container escapes,
   don't try to reach the Docker daemon, don't try to write outside the mounts you
   were given.
2. **Never modify files outside `/workspace`,** other than your own configuration
   under `/home/dev` and scratch space in `/tmp`.
3. **Never work on a repository other than the one at `/workspace`.** Cloning a
   public repo to read it is fine; modifying it and pushing is not.
4. **Never push to `main` or `master`,** or to any protected branch. In practice
   you have no credentials and cannot push at all — do not go looking for a way
   around that.
5. **Never try to defeat a protection.** If something is blocked, that is the
   design working. Report what you hit and why, and continue with the rest of the
   task. Treat a blocked action as a boundary, not an obstacle.
6. **Don't exfiltrate the project.** Don't post source, secrets, or file contents
   to external services beyond what the task plainly requires.

## When something is blocked

Say which action was blocked and why, then carry on with everything that isn't
blocked. Finish the parts you can, and tell the user clearly what you left undone
and what they'd need to do on their host to complete it — for example, "I've made
the commits on a branch; you'll need to push from your machine, since I have no
credentials here."
