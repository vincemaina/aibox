"""`.aibox.toml` loader and CLI/config merge logic.

The merge rules (MVP):

- Lists (ports, env, env_files, docker_args): CLI flags are appended to config values.
- ``shell``: CLI ``--shell`` overrides config ``shell``. If neither is set, falls back to ``/bin/bash``.
- ``user``: passed through from CLI directly (default ``dev``).
"""

from __future__ import annotations

import argparse
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from .docker import RunSpec
from .identity import ProjectIdentity

CONFIG_FILENAME = ".aibox.toml"

_ALLOWED_KEYS = {"ports", "env", "env_files", "shell", "docker_args"}
_LIST_KEYS = {"ports", "env", "env_files", "docker_args"}


class ConfigError(RuntimeError):
    """Raised for malformed or invalid ``.aibox.toml`` content."""


@dataclass(frozen=True)
class ProjectConfig:
    ports: list[str] = field(default_factory=list)
    env: list[str] = field(default_factory=list)
    env_files: list[str] = field(default_factory=list)
    shell: str | None = None
    docker_args: list[str] = field(default_factory=list)


def load(project_root: Path) -> ProjectConfig:
    path = project_root / CONFIG_FILENAME
    if not path.is_file():
        return ProjectConfig()

    try:
        with path.open("rb") as fh:
            raw = tomllib.load(fh)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{CONFIG_FILENAME}: parse error: {exc}") from exc

    unknown = set(raw.keys()) - _ALLOWED_KEYS
    if unknown:
        raise ConfigError(
            f"{CONFIG_FILENAME}: unknown key(s): {', '.join(sorted(unknown))}. "
            f"Allowed: {', '.join(sorted(_ALLOWED_KEYS))}."
        )

    for key in _LIST_KEYS:
        if key not in raw:
            continue
        if not isinstance(raw[key], list):
            raise ConfigError(f"{CONFIG_FILENAME}: '{key}' must be a list of strings.")
        for item in raw[key]:
            if not isinstance(item, str):
                raise ConfigError(
                    f"{CONFIG_FILENAME}: '{key}' entries must be strings; got {type(item).__name__}."
                )

    if "shell" in raw and not isinstance(raw["shell"], str):
        raise ConfigError(
            f"{CONFIG_FILENAME}: 'shell' must be a string; got {type(raw['shell']).__name__}."
        )

    return ProjectConfig(
        ports=list(raw.get("ports", [])),
        env=list(raw.get("env", [])),
        env_files=list(raw.get("env_files", [])),
        shell=raw.get("shell"),
        docker_args=list(raw.get("docker_args", [])),
    )


def merge(
    config: ProjectConfig,
    cli_args: argparse.Namespace,
    identity: ProjectIdentity,
) -> RunSpec:
    shell = cli_args.shell if cli_args.shell is not None else (config.shell or "/bin/bash")
    return RunSpec(
        identity=identity,
        ports=config.ports + list(cli_args.port),
        env=config.env + list(cli_args.env),
        env_files=config.env_files + list(cli_args.env_file),
        docker_args=config.docker_args + list(cli_args.docker_arg),
        shell=shell,
        user=cli_args.user,
        mask_git=identity.git_present,
    )
