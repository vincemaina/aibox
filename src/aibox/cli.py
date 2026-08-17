"""aibox CLI entry point."""

from __future__ import annotations

import argparse
import dataclasses
import platform
import sys
from pathlib import PurePosixPath

from . import config, docker, identity, onboarding, templates, userconfig
from . import __version__
from .config import ConfigError
from .docker import DockerError, RunSpec
from .templates import Action, TemplateError


def _default_user() -> str | None:
    """Default value for the ``--user`` flag.

    - macOS/Windows: ``"dev"``. Docker Desktop translates bind-mount ownership
      transparently, so running directly as the in-image ``dev`` user is fine.
    - Linux: ``None`` (no ``--user`` flag passed). The container starts as root
      and the entrypoint retunes the ``dev`` user's UID/GID to match the host
      before dropping privileges via gosu.
    """
    if platform.system() == "Linux":
        return None
    return "dev"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="aibox",
        description="Run a disposable Docker container for AI coding agents.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command", metavar="command")

    run = subparsers.add_parser("run", help="Start an interactive container for the current project")
    run.add_argument("-p", "--port", action="append", default=[], metavar="HOST:CONTAINER")
    run.add_argument("-e", "--env", action="append", default=[], metavar="KEY=VALUE")
    run.add_argument("--env-file", action="append", default=[], metavar="PATH")
    run.add_argument("--shell", default=None, metavar="PATH")
    run.add_argument(
        "--git",
        choices=docker.GIT_MODES,
        default=None,
        help="How much of the host .git the agent gets. 'commit' (default) lets it "
        "read history and commit locally; 'readonly' lets it read only; 'masked' "
        "hides .git entirely.",
    )
    run.add_argument(
        "--docker-arg",
        action="append",
        default=[],
        metavar="ARG",
        help="Raw passthrough to docker run. Use --docker-arg=VALUE form when VALUE starts with --.",
    )
    run.add_argument(
        "--refresh",
        action="store_true",
        help="Re-fetch remote templates now instead of waiting for the cache to expire.",
    )
    run.add_argument(
        "--user",
        default=_default_user(),
        help="Override the container user. Default: 'dev' on macOS/Windows, "
        "host UID:GID on Linux (entrypoint handles the drop).",
    )

    init = subparsers.add_parser(
        "init", help="Seed this project from your configured template(s)"
    )
    init.add_argument(
        "--template",
        action="append",
        default=[],
        metavar="REF",
        help="Template git URL or local path. Repeatable. Overrides configured templates.",
    )
    init.add_argument(
        "--on-conflict",
        choices=("ask", "skip", "replace", "keep-both"),
        default="ask",
        help="What to do when a template file already exists and differs. "
        "Default: ask. Falls back to 'skip' when stdin isn't a terminal.",
    )
    init.add_argument(
        "--yes", action="store_true", help="Non-interactive; same as --on-conflict skip."
    )
    init.add_argument("--refresh", action="store_true", help="Re-clone cached templates")
    init.add_argument("--dry-run", action="store_true", help="Report the plan, write nothing")

    subparsers.add_parser(
        "setup", help="Configure your templates interactively (runs on first use)"
    )

    subparsers.add_parser("info", help="Show project paths, IDs, and volume names")

    remove = subparsers.add_parser("remove-volume", help="Delete persistent volumes for the current project")
    remove.add_argument("--force", action="store_true", help="Skip confirmation prompt")

    subparsers.add_parser("rebuild-image", help="Rebuild the default aibox Docker image")

    return parser


_GIT_SUMMARIES = {
    "masked": "masked (.git hidden)",
    "readonly": "read-only (history visible, not writable)",
    "commit": "commit (history visible, agent can commit; hooks + config frozen)",
}


def _git_summary(spec: RunSpec) -> str:
    if not spec.identity.git_present:
        return "n/a (no .git in this project)"
    return _GIT_SUMMARIES[spec.git_mode]


def print_summary(spec: RunSpec, header: str) -> None:
    ident = spec.identity
    print()
    print(header)
    print()
    print(f"Project path:   {ident.cwd}")
    print(f"Project ID:     {ident.project_id}")
    print(f"Container:      {ident.container}")
    print(f"Image:          {ident.image}")
    print(f"Home volume:    {ident.volumes['home']}")
    print(f"Tmp volume:     {ident.volumes['tmp']}")
    print(f"Var tmp volume: {ident.volumes['var_tmp']}")
    print(f"Opt volume:     {ident.volumes['opt']}")
    print(f"Git access:     {_git_summary(spec)}")
    print()


def cmd_run(args: argparse.Namespace) -> int:
    docker.check_available()

    # First time through, walk the user into a template setup — the config file
    # is otherwise undiscoverable. Skipped entirely without a terminal.
    onboarding.run_setup()

    ident = identity.resolve()
    cfg = config.load(ident.cwd)
    spec = config.merge(cfg, args, ident)

    refs = templates.refs_for(userconfig.load(), cfg)
    resolved = templates.load_all(refs, refresh=args.refresh)

    if onboarding.offer_import(resolved, ident.cwd, ident.project_id):
        results = _merge_templates(resolved, ident.cwd, policy="ask", dry_run=False)
        _print_init_summary(results, resolved, dry_run=False)

    # The built-in agent briefing plus any templates' `home/` content, refreshed
    # on every run — it lives on the per-project volume, not in the user's repo,
    # so there's nothing to protect.
    spec = dataclasses.replace(
        spec, home_seed=templates.stage_home_seed(resolved, ident.project_id)
    )

    docker.ensure_image(spec.identity.image)
    print_summary(spec, header="Starting aibox")
    return docker.run_container(spec)


def _resolve_refs(args: argparse.Namespace, project_root) -> list[str]:
    """Template refs for this project: CLI, else project config, else user config."""
    if args.template:
        return list(args.template)
    return templates.refs_for(userconfig.load(), config.load(project_root))


def _prompt_conflict(entry) -> str:
    """Ask what to do about one clashing file. Returns a policy for that file."""
    choices = {"k": "skip", "r": "replace", "b": "keep-both"}
    print(f"\n  {entry.relative} already exists and differs.")
    while True:
        answer = input(
            "    [k] keep mine  [r] replace  [b] keep both  [d] diff > "
        ).strip().lower()
        if answer == "d":
            _print_diff(entry)
            continue
        if answer in choices:
            return choices[answer]
        print("    Please enter k, r, b, or d.")


def _print_diff(entry) -> None:
    import difflib

    try:
        mine = entry.target.read_text().splitlines(keepends=True)
        theirs = entry.source.read_text().splitlines(keepends=True)
    except (OSError, UnicodeDecodeError):
        print("    (binary or unreadable — can't diff)")
        return
    diff = list(
        difflib.unified_diff(mine, theirs, fromfile="yours", tofile="template", n=2)
    )
    if not diff:
        print("    (no textual difference)")
    for line in diff[:200]:
        print(f"    {line.rstrip()}")
    if len(diff) > 200:
        print(f"    … {len(diff) - 200} more lines")


def _apply_entry(entry, policy: str, results: dict) -> None:
    if policy == "skip":
        results["skipped"].append(entry.relative)
    elif policy == "replace":
        templates.copy(entry.source, entry.target)
        results["replaced"].append(entry.relative)
    elif policy == "keep-both":
        alt = templates.keep_both_path(entry.target)
        templates.copy(entry.source, alt)
        results["created"].append(PurePosixPath(entry.relative).with_name(alt.name).as_posix())
        results["skipped"].append(entry.relative)


def _merge_templates(
    resolved: list, project, policy: str, dry_run: bool
) -> dict:
    """Apply every template's ``workspace/`` to a project. Shared by run and init."""
    results = {"created": [], "replaced": [], "skipped": [], "unchanged": []}
    warned = False

    for template in resolved:
        for entry in templates.plan_merge(template, project).entries:
            if entry.action is Action.UNCHANGED:
                results["unchanged"].append(entry.relative)
            elif entry.action is Action.CREATE:
                if not dry_run:
                    templates.copy(entry.source, entry.target)
                results["created"].append(entry.relative)
            elif dry_run:
                results["skipped"].append(entry.relative)
            else:
                chosen = policy
                if chosen == "ask":
                    # Only mention the fallback once, and only if a conflict
                    # actually arises — otherwise it's noise on a clean run.
                    if sys.stdin.isatty():
                        chosen = _prompt_conflict(entry)
                    else:
                        chosen = "skip"
                        if not warned:
                            print("stdin is not a terminal — keeping your files on conflict.")
                            warned = True
                _apply_entry(entry, chosen, results)
    return results


def cmd_init(args: argparse.Namespace) -> int:
    ident = identity.resolve()
    refs = _resolve_refs(args, ident.cwd)
    if not refs:
        print(
            "No templates configured. Run `aibox setup`, or add them to "
            f"{userconfig.config_path()}:\n\n"
            '  templates = ["https://github.com/you/your-template"]\n\n'
            "or pass --template REF."
        )
        return 0

    resolved = templates.load_all(refs, refresh=args.refresh)
    results = _merge_templates(
        resolved,
        ident.cwd,
        policy="skip" if args.yes else args.on_conflict,
        dry_run=args.dry_run,
    )
    _print_init_summary(results, resolved, args.dry_run)
    return 0


def cmd_setup(args: argparse.Namespace) -> int:
    if not onboarding.interactive():
        print(
            "`aibox setup` is interactive and needs a terminal. Write "
            f"{userconfig.config_path()} directly instead.",
            file=sys.stderr,
        )
        return 1
    onboarding.run_setup(force=True)
    return 0


def _print_init_summary(results: dict, resolved: list, dry_run: bool) -> None:
    print()
    for label, key in (
        ("created", "created"),
        ("replaced", "replaced"),
        ("kept yours", "skipped"),
    ):
        for name in results[key]:
            print(f"  {label:>10}  {name}")
    if not any(results[k] for k in ("created", "replaced", "skipped")):
        print("  Nothing to do — project already matches the template.")

    counts = ", ".join(
        f"{len(results[k])} {k}"
        for k in ("created", "replaced", "skipped", "unchanged")
        if results[k]
    )
    print(f"\n{counts or 'no changes'}{' (dry run — nothing written)' if dry_run else ''}")
    if results["skipped"] and not dry_run:
        print("\nCompare against the template at:")
        for template in resolved:
            print(f"  {template / templates.WORKSPACE_DIR}")


def cmd_info(args: argparse.Namespace) -> int:
    ident = identity.resolve()
    cfg = config.load(ident.cwd)
    spec = RunSpec(
        identity=ident,
        ports=[],
        env=[],
        env_files=[],
        docker_args=[],
        shell="/bin/bash",
        user=_default_user(),
        git_mode=cfg.git or docker.DEFAULT_GIT_MODE,
    )
    print_summary(spec, header="aibox project info")
    return 0


def cmd_remove_volume(args: argparse.Namespace) -> int:
    docker.check_available()
    ident = identity.resolve()
    volumes = list(ident.volumes.values())

    if not args.force:
        print(f"This will delete {len(volumes)} volumes for project '{ident.project_id}':")
        for v in volumes:
            print(f"  {v}")
        response = input("Continue? [y/N]: ").strip().lower()
        if response not in ("y", "yes"):
            print("Aborted.")
            return 0

    for v in volumes:
        if docker.volume_exists(v):
            docker.remove_volume(v)
            print(f"Removed: {v}")
        else:
            print(f"Skipped (not present): {v}")
    return 0


def cmd_rebuild_image(args: argparse.Namespace) -> int:
    docker.check_available()
    name = identity.image_name()
    print(f"Rebuilding {name}...")
    docker.rebuild_image(name)
    print("Done.")
    return 0


HANDLERS = {
    "run": cmd_run,
    "init": cmd_init,
    "setup": cmd_setup,
    "info": cmd_info,
    "remove-volume": cmd_remove_volume,
    "rebuild-image": cmd_rebuild_image,
}


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    if not argv:
        argv = ["run"]

    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        return HANDLERS[args.command](args)
    except (DockerError, ConfigError, TemplateError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
