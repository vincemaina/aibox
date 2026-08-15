# docs/

The public site at <https://vincemaina.github.io/aibox/>, served by GitHub Pages
from this folder on `main` (Settings → Pages → Deploy from a branch → `main` / `/docs`).

Hand-written static HTML. **No build step, no framework, no npm.** Edit the files
and push; GitHub serves them as-is. `.nojekyll` stops Pages running Jekyll over them.

## Files

- `index.html` — landing page. Purpose, benefits, features, install, FAQ.
- `documentation.html` — the full reference: every command and flag, both config
  files, Git modes, templates, browser testing, security model, troubleshooting.
- `style.css` — shared stylesheet for both pages.
- `og-image.png` — 1200×630 social preview, referenced by absolute URL in the meta
  tags. Regenerate it by rendering an HTML card with Playwright inside an aibox
  container, which is how the current one was made.
- `robots.txt`, `sitemap.xml` — update the sitemap when adding a page.

## Design system

Direction is an **engineering spec sheet**, chosen because the product *is* a
boundary and a manifest of what crosses it.

- **Signature element:** the container-boundary ledger in the hero — two columns
  (inside the box / stays on your machine) split by a labelled dashed spine. It's
  the product rendered as data. Keep it as the one bold element and let the rest
  stay quiet.
- **Type:** the IBM Plex superfamily — Condensed for display (uppercase, tight),
  Sans for body, Mono for commands and manifest rows. Loaded from Google Fonts
  with a system fallback stack.
- **Colour:** the two accents are semantic, not decorative — `--seal` (green,
  permitted) and `--stamp` (orange, denied). Don't use them for anything else.
  Every colour is a token on `:root`, redefined under `prefers-color-scheme: dark`.

## Conventions

- **Every colour and size comes from a token.** No hard-coded hex outside `:root`.
- **Both themes, always.** Test light and dark; the palette inverts via tokens.
- **Accessibility floor:** visible focus rings, real landmarks, `prefers-reduced-motion`
  respected, responsive to 390px.
- **No external requests except the font stylesheet.** No analytics, no CDNs.
- **SEO surface is deliberate.** Each page carries a unique `<title>` and meta
  description, canonical URL, Open Graph and Twitter tags, and JSON-LD. The
  landing page's `FAQPage` block must stay in sync with the visible FAQ — Google
  penalises structured data that doesn't match the page.

## Keeping it honest

`tests/test_docs.py` asserts every CLI command and flag in `cli.build_parser()`
appears in `documentation.html`. Add a flag without documenting it and the suite
fails. If you rename a command, the test tells you which page to update.
