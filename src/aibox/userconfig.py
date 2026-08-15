"""User-level config: settings that belong to the person, not to a project.

Deliberately separate from :mod:`aibox.config`, which reads a project's
``.aibox.toml``. Different file, different scope, different keys — merging them
into one loader would mean one set of allowed keys for two unrelated things.

Currently holds only ``templates``. A project-level ``templates`` key overrides
this one; see :func:`aibox.templates.refs_for`.
"""

from __future__ import annotations

import json
import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from .config import ConfigError

CONFIG_FILENAME = "config.toml"
STATE_FILENAME = "projects.json"

_ALLOWED_KEYS = {"templates"}


@dataclass(frozen=True)
class UserConfig:
    templates: list[str] = field(default_factory=list)


def config_dir() -> Path:
    """Directory holding the user-level config.

    ``$XDG_CONFIG_HOME/aibox`` when set (Linux/BSD convention), ``%APPDATA%\\aibox``
    on Windows, ``~/.config/aibox`` otherwise. macOS gets ``~/.config`` too rather
    than ``~/Library/Application Support`` — it's what CLI tools there actually use.
    """
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg) / "aibox"
    if os.name == "nt":
        appdata = os.environ.get("APPDATA")
        if appdata:
            return Path(appdata) / "aibox"
    return Path.home() / ".config" / "aibox"


def config_path() -> Path:
    return config_dir() / CONFIG_FILENAME


def cache_dir() -> Path:
    """Directory for cloned templates and staged seeds."""
    xdg = os.environ.get("XDG_CACHE_HOME")
    if xdg:
        return Path(xdg) / "aibox"
    if os.name == "nt":
        local = os.environ.get("LOCALAPPDATA")
        if local:
            return Path(local) / "aibox" / "cache"
    return Path.home() / ".cache" / "aibox"


def state_dir() -> Path:
    """Directory for state aibox remembers but the user never edits.

    Separate from the config dir on purpose: config is yours to hand-edit, state
    is ours to rewrite. Deleting it only makes aibox ask a question again.
    """
    xdg = os.environ.get("XDG_STATE_HOME")
    if xdg:
        return Path(xdg) / "aibox"
    if os.name == "nt":
        local = os.environ.get("LOCALAPPDATA")
        if local:
            return Path(local) / "aibox" / "state"
    return Path.home() / ".local" / "state" / "aibox"


def exists() -> bool:
    """Whether the user has been through setup. Drives first-run onboarding."""
    return config_path().is_file()


def _toml_string(value: str) -> str:
    # TOML basic strings escape the same way JSON does, which covers the
    # backslashes in Windows paths without hand-rolling an escaper.
    return json.dumps(value)


def save(config: UserConfig) -> Path:
    """Write the user-level config, creating the directory if needed."""
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    lines = [
        "# aibox user configuration.",
        "# Docs: https://vincemaina.github.io/aibox/documentation.html#templates",
        "",
        "# Templates seed new projects. Applied in order; a project's .aibox.toml",
        "# can override this list, and templates = [] opts a project out.",
    ]
    if config.templates:
        lines.append("templates = [")
        lines += [f"  {_toml_string(t)}," for t in config.templates]
        lines.append("]")
    else:
        lines.append("templates = []")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def declined_projects() -> set[str]:
    """Project IDs where the user asked not to be offered a template import."""
    path = state_dir() / STATE_FILENAME
    if not path.is_file():
        return set()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return set()
    return set(data.get("declined_import", []))


def decline_project(project_id: str) -> None:
    declined = declined_projects() | {project_id}
    path = state_dir() / STATE_FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"declined_import": sorted(declined)}, indent=2) + "\n",
        encoding="utf-8",
    )


def load() -> UserConfig:
    path = config_path()
    if not path.is_file():
        return UserConfig()

    try:
        with path.open("rb") as fh:
            raw = tomllib.load(fh)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{path}: parse error: {exc}") from exc

    unknown = set(raw.keys()) - _ALLOWED_KEYS
    if unknown:
        raise ConfigError(
            f"{path}: unknown key(s): {', '.join(sorted(unknown))}. "
            f"Allowed: {', '.join(sorted(_ALLOWED_KEYS))}."
        )

    templates = raw.get("templates", [])
    if not isinstance(templates, list) or not all(isinstance(t, str) for t in templates):
        raise ConfigError(f"{path}: 'templates' must be a list of strings.")

    return UserConfig(templates=list(templates))
