"""Project identity: stable IDs, container names, image names, volume names.

Everything in this module is a pure function (no side effects beyond resolving
paths and reading a tiny piece of filesystem state in ``resolve``). The CLI and
docker layers depend on this module to produce all the names they pass to
Docker, so naming logic is centralised here.
"""

from __future__ import annotations

import hashlib
import re
import secrets
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

IMAGE_NAME = "aibox-default:latest"

_VOLUME_SUFFIXES = {
    "home": "home",
    "tmp": "tmp",
    "var_tmp": "var-tmp",
    "opt": "opt",
}


def slugify(name: str) -> str:
    """Lowercase ASCII slug. Falls back to ``project`` for empty results."""
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "project"


def path_hash(path: Path) -> str:
    """8-char hex SHA-256 of the resolved absolute path (case-normalised).

    Lowercasing the path string keeps project IDs stable on case-insensitive
    filesystems (default macOS HFS+/APFS, Windows NTFS) where ``Path.resolve()``
    can preserve whatever case the user typed.
    """
    resolved = str(path.resolve()).lower().encode("utf-8")
    return hashlib.sha256(resolved).hexdigest()[:8]


def project_id(cwd: Path) -> str:
    return f"{slugify(cwd.name)}-{path_hash(cwd)}"


def image_name() -> str:
    return IMAGE_NAME


def volume_names(pid: str) -> dict[str, str]:
    return {key: f"aibox-{suffix}-{pid}" for key, suffix in _VOLUME_SUFFIXES.items()}


def container_name(
    pid: str,
    now: datetime | None = None,
    rand: str | None = None,
) -> str:
    """``aibox-{pid}-{YYYYMMDD-HHMMSS}-{6 hex chars}``.

    ``now`` and ``rand`` are injectable so tests can assert exact output.
    """
    if now is None:
        now = datetime.now()
    if rand is None:
        rand = secrets.token_hex(3)
    return f"aibox-{pid}-{now.strftime('%Y%m%d-%H%M%S')}-{rand}"


@dataclass(frozen=True)
class ProjectIdentity:
    cwd: Path
    project_id: str
    image: str
    container: str
    volumes: dict[str, str]
    git_present: bool


def resolve(cwd: Path | None = None) -> ProjectIdentity:
    cwd = (cwd if cwd is not None else Path.cwd()).resolve()
    pid = project_id(cwd)
    return ProjectIdentity(
        cwd=cwd,
        project_id=pid,
        image=image_name(),
        container=container_name(pid),
        volumes=volume_names(pid),
        git_present=(cwd / ".git").is_dir(),
    )
