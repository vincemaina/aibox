# Phase 11: Browser testing and visual feedback

## Goal

Let an agent inside the box run a browser against the app it just built — drive it with Playwright, screenshot it, and assess the result.

## Context: what actually blocks this today

Measured in the real image (`aibox-default:latest`, Debian 13 trixie), not assumed:

- **Installing Playwright works.** `npx playwright install chromium` succeeds as the non-root `dev` user. Browsers land in `~/.cache/ms-playwright`, which is on the per-project home volume, so they survive across sessions. No change needed here.
- **Launching fails.** The Chromium binary needs 24 shared libraries the slim base doesn't have — `libglib-2.0.so.0`, `libnss3.so`, `libgbm.so.1`, `libX11.so.6`, and friends. The failure surfaces as `browserType.launch: Target page, context or browser has been closed`, with the real cause buried in the browser log:

  ```
  chrome-headless-shell: error while loading shared libraries:
  libglib-2.0.so.0: cannot open shared object file
  ```

- **The agent cannot fix this itself.** Those libraries need `apt-get`, which needs root. The container drops to `dev` and has no `sudo`, so `playwright install --with-deps` is impossible from inside. It has to be solved in the image.

So this is a one-line image problem wearing a confusing error message.

### Verified fix

```dockerfile
RUN npx --yes playwright@<pinned> install-deps chromium && rm -rf /var/lib/apt/lists/*
```

Letting Playwright resolve the package list matters: Debian 13 renamed most of these in the `t64` ABI transition (`libasound2` → `libasound2t64`, etc.), so a hand-written `apt-get install` list would rot. Playwright keeps the mapping current per distro.

Built and confirmed: Chromium launches headless and produces a correct, properly font-rendered screenshot, written to `/workspace` owned by the host user.

**Cost: 1.03 GB → 1.58 GB.** That +550 MB is the whole design question below.

### On "Claude should be able to *see* it"

Worth separating two things that sound like one:

- **The agent seeing its work** needs no GUI. Claude reads image files directly, so `page.screenshot()` into `/workspace` followed by reading the PNG is the complete loop — that's how the fix above was verified. Headless is sufficient.
- **A human watching the agent drive a browser** is the case where a GUI helps. Two ways to get it, in increasing cost:
  1. Publish the dev server port (`ports = ["3000:3000"]`, already supported) and look at the app in the host's own browser. Covers most of the need for zero extra work.
  2. Xvfb + `x11vnc` + noVNC on a published port, so headed mode is viewable in a browser tab. Real but niche; adds another ~100 MB and a process-supervision problem.

Recommendation: ship headless, keep (1) as the documented answer for looking at the app, and treat (2) as a separate opt-in phase only if watching the agent live turns out to matter.

## Design decision: where do the deps go?

The image is shared by every project, so the extra weight is charged to projects that will never open a browser.

| Option | Pros | Cons |
|--------|------|------|
| **A. Add to the default image** ✅ | One image, works everywhere, nothing to configure | Every project pays the size |
| **B. Second variant `aibox-browser:latest`** | Pay only where needed | `identity.image` becomes variable — touches `ensure_image`, `rebuild-image`, `info`; overlaps the "custom images" future-work item |
| **C. Runtime install** | No image change | Impossible — needs root. Rejected on evidence. |

**Chosen: A.** A variant image was considered and rejected as not worth the configuration surface for one capability. Measured cost came in below the estimate: **1.03 GB → 1.5 GB**. Revisit only if the default image keeps growing, at which point general custom-image support (not a browser-specific variant) is the right fix.

Browser *binaries* are deliberately **not** baked in. The image carries only the system libraries; the agent runs `npx playwright install chromium` itself, which needs no root and caches into `~/.cache/ms-playwright` on the per-project home volume, so it's a one-time cost per project. This keeps the image smaller and lets each project pin its own Playwright version, which matters because the browser build and the Playwright release are coupled.

## Tasks

1. ~~Decide A vs B.~~ Chose A.
2. ~~Add `install-deps chromium` to the Dockerfile, Playwright version pinned via a build arg alongside `NODE_VERSION`.~~ Done.
3. ~~Document the workflow: install Playwright, screenshot into `/workspace`, agent reads the PNG.~~ Done.
4. Browser launch is an image concern, not a CLI one, so there's nothing to unit-test — `build_run_args` is unchanged by this phase. Cover it in the deferred Docker-backed CI job instead.

## Files created or modified

```
src/aibox/templates/Dockerfile   # ARG PLAYWRIGHT_VERSION + install-deps chromium
README.md CLAUDE.md ROADMAP.md
```

## Acceptance criteria

All verified against the rebuilt image:

- ✅ In a fresh box, `npx playwright install chromium` then a headless launch + `page.screenshot()` succeeds with no manual setup and no root.
- ✅ The PNG lands in `/workspace` owned by the host user and renders text correctly (fonts present, properly antialiased).
- ✅ Browsers cache to `~/.cache/ms-playwright` on the home volume, so the download is once per project, not once per session.
- ✅ README documents the screenshot-and-read loop.

## Still open

- **Chromium only.** Firefox and WebKit each add their own dep set. Chromium covers most web testing; add the others only on demand.
- **Playwright version drift.** The image pins `PLAYWRIGHT_VERSION` for `install-deps` only. A project installing a much newer Playwright could in principle need a library the pinned deps don't provide. Bump the ARG when that happens; the failure mode is a clear missing-`.so` error.
- **`/dev/shm`.** Docker's default 64 MB can crash Chromium on heavy pages. Playwright passes `--disable-dev-shm-usage`, which mitigates it, but `--shm-size=1g` may be worth defaulting for projects driving real apps. Not done — waiting for a real failure rather than pre-emptively widening the runtime config.
- **Headed / GUI mode.** Out of scope by design: the agent sees via screenshots, and a human can look at the app by publishing its port. Xvfb + noVNC only becomes worthwhile if watching the agent drive a browser live turns out to matter.
- **Egress.** A browser is a much larger outbound surface, and interacts directly with the egress-firewall idea in `ROADMAP.md`'s big-feature list.
