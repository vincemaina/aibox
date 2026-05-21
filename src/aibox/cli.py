"""aibox CLI entry point."""

from __future__ import annotations

import argparse
import sys


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="aibox",
        description="Run a disposable Docker container for AI coding agents.",
    )
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


def cmd_run(args: argparse.Namespace) -> int:
    print("aibox run: not implemented yet (phase 4)", file=sys.stderr)
    return 0


def cmd_info(args: argparse.Namespace) -> int:
    print("aibox info: not implemented yet (phase 4)", file=sys.stderr)
    return 0


def cmd_remove_volume(args: argparse.Namespace) -> int:
    print("aibox remove-volume: not implemented yet (phase 4)", file=sys.stderr)
    return 0


def cmd_rebuild_image(args: argparse.Namespace) -> int:
    print("aibox rebuild-image: not implemented yet (phase 4)", file=sys.stderr)
    return 0


HANDLERS = {
    "run": cmd_run,
    "info": cmd_info,
    "remove-volume": cmd_remove_volume,
    "rebuild-image": cmd_rebuild_image,
}


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    command = args.command or "run"
    if command == "run" and args.command is None:
        run_parser_args = build_parser().parse_args(["run"])
        for key, value in vars(run_parser_args).items():
            if key != "command" and not hasattr(args, key):
                setattr(args, key, value)

    return HANDLERS[command](args)


if __name__ == "__main__":
    sys.exit(main())
