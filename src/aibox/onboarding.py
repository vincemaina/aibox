"""Interactive first-run setup and the per-project template offer.

Two flows live here, both of which must degrade safely:

- :func:`run_setup` — asks for a template repo the first time aibox is used, checks
  its layout, and writes the user-level config.
- :func:`offer_import` — on a project that has never been seeded, asks whether to
  import the template's ``workspace/`` files.

Neither may ever block a non-interactive run. Both check for a terminal first and
return quietly when there isn't one, so scripts and CI keep working. Everything
here is prompts and printing; the actual work is in :mod:`aibox.templates`.
"""

from __future__ import annotations

import sys
from pathlib import Path

from . import templates, userconfig
from .templates import Action, TemplateError
from .userconfig import UserConfig

RULE = "─" * 60


def interactive() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty()


def _ask(prompt: str, default: str = "") -> str:
    try:
        answer = input(prompt).strip()
    except EOFError:
        return default
    return answer or default


def _describe(shape: templates.TemplateShape) -> None:
    """Report what we found, so a wrong layout is obvious rather than silent."""
    if shape.workspace_files:
        print(
            f"    workspace/  {shape.workspace_files} file(s)"
            "  → merged into your projects"
        )
    if shape.home_files:
        print(
            f"    home/       {shape.home_files} file(s)"
            "  → loaded into the container"
        )

    if shape.is_usable:
        return

    print("\n  This template has no workspace/ or home/ directory, so it would")
    print("  do nothing. aibox expects:\n")
    print("    your-template/")
    print("    ├── workspace/   files merged into each project (CLAUDE.md, ...)")
    print("    └── home/        files loaded into the container (.claude/skills/)")
    if shape.stray_top_level:
        found = ", ".join(shape.stray_top_level[:6])
        print(f"\n  Found at the top level instead: {found}")
        print("  If those are meant for your projects, move them into workspace/.")
    print(f"\n  Guide: {templates.DOCS_TEMPLATES_URL}")


def _try_template(ref: str) -> str | None:
    """Resolve and check one ref. Returns it if the user wants to keep it."""
    print("\n  Fetching…")
    try:
        # Always fetch fresh during setup: the user is actively configuring this,
        # and reporting the structure of a stale clone would be misleading.
        resolved = templates.resolve(ref, refresh=True)
    except TemplateError as exc:
        print(f"  {exc}")
        return None

    shape = templates.inspect(resolved)
    _describe(shape)

    if shape.is_usable:
        return ref
    return ref if _ask("\n  Use it anyway? [y/N]: ").lower() in ("y", "yes") else None


def run_setup(force: bool = False) -> UserConfig | None:
    """First-run setup. Returns the saved config, or ``None`` if it didn't run."""
    if not force and userconfig.exists():
        return None
    if not interactive():
        return None

    print(f"\n{RULE}")
    print("  Welcome to aibox")
    print(RULE)
    print("\n  Templates seed every project with your own agent guidance —")
    print("  a CLAUDE.md, your working practices, your skills — so you don't")
    print("  set them up by hand each time.")
    print(f"\n  Guide: {templates.DOCS_TEMPLATES_URL}")

    refs: list[str] = []
    while True:
        prompt = (
            "\n  Template repo URL or local path (Enter to skip): "
            if not refs
            else "\n  Another template (Enter to finish): "
        )
        ref = _ask(prompt)
        if not ref:
            break
        kept = _try_template(ref)
        if kept:
            refs.append(kept)
            print("  Added.")

    config = UserConfig(templates=refs)
    path = userconfig.save(config)

    print(f"\n  Saved to {path}")
    if refs:
        print("  Run `aibox init` in a project to import these files.")
    else:
        print("  No templates configured. Add some later with `aibox setup`.")
    print(f"{RULE}\n")
    return config


def _importable(resolved: list[Path], project: Path) -> int:
    """How many files a template would newly create in this project."""
    return sum(
        len(templates.plan_merge(template, project).of(Action.CREATE))
        for template in resolved
    )


def offer_import(resolved: list[Path], project: Path, project_id: str) -> bool:
    """Ask whether to seed a project that hasn't been seeded before.

    Returns True if the caller should run the import. Silent — and False — when
    there's nothing to add, when there's no terminal, or when the user has
    already said "never" for this project.
    """
    if not resolved or not interactive():
        return False
    if project_id in userconfig.declined_projects():
        return False

    count = _importable(resolved, project)
    if not count:
        return False

    print(f"\n  This project doesn't have your template files yet.")
    print(f"  {count} file(s) would be added. Nothing existing is overwritten.")

    while True:
        answer = _ask("  Import them? [Y]es  [n]ot now  [never]: ", "y").lower()
        if answer in ("y", "yes"):
            return True
        if answer in ("n", "no", "not now"):
            return False
        if answer == "never":
            userconfig.decline_project(project_id)
            print("  Won't ask again for this project.")
            return False
        print("  Please answer y, n, or never.")
