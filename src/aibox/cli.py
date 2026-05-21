"""aibox CLI entry point."""

from __future__ import annotations

import argparse
import sys

from . import config, docker, identity
from . import __version__
from .config import ConfigError
from .docker import DockerError, RunSpec


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
        "--docker-arg",
        action="append",
        default=[],
        metavar="ARG",
        help="Raw passthrough to docker run. Use --docker-arg=VALUE form when VALUE starts with --.",
    )
    run.add_argument("--user", default="dev")

    subparsers.add_parser("info", help="Show project paths, IDs, and volume names")

    remove = subparsers.add_parser("remove-volume", help="Delete persistent volumes for the current project")
    remove.add_argument("--force", action="store_true", help="Skip confirmation prompt")

    subparsers.add_parser("rebuild-image", help="Rebuild the default aibox Docker image")

    return parser


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
    print(f"Git hidden:     {'yes' if spec.mask_git else 'no'}")
    print()


def cmd_run(args: argparse.Namespace) -> int:
    docker.check_available()
    ident = identity.resolve()
    cfg = config.load(ident.cwd)
    spec = config.merge(cfg, args, ident)
    docker.ensure_image(spec.identity.image)
    print_summary(spec, header="Starting aibox")
    return docker.run_container(spec)


def cmd_info(args: argparse.Namespace) -> int:
    ident = identity.resolve()
    spec = RunSpec(
        identity=ident,
        ports=[],
        env=[],
        env_files=[],
        docker_args=[],
        shell="/bin/bash",
        user="dev",
        mask_git=ident.git_present,
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
    except (DockerError, ConfigError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
