"""Project templates: fetch, merge into a project, stage for the container.

A template is a directory (local, or a git repo that gets cloned into the cache)
with up to two top-level directories:

``workspace/``
    Repo guidance — ``CLAUDE.md``, best practices, a starter ``.aibox.toml``.
    Merged into the user's project by ``aibox init`` only, and never overwritten
    without consent: this is their source tree.

``home/``
    Personal agent tooling — skills, agent config. Synced into ``/home/dev`` on
    every ``aibox run``. That's a per-project Docker volume, i.e. aibox-managed
    disposable state, so it can be refreshed freely and never touches the repo.

Note on conventions: ``docker.py`` owns every ``docker`` invocation; this module
owns every ``git`` invocation. Both keep subprocess use out of the rest of the
package. Neither ever uses ``shell=True``.
"""

from __future__ import annotations

import filecmp
import hashlib
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from enum import Enum
from importlib.resources import files
from pathlib import Path

from .config import ProjectConfig
from .docker import SEED_MOUNT
from .identity import slugify
from .userconfig import UserConfig, cache_dir

WORKSPACE_DIR = "workspace"
HOME_DIR = "home"

#: Built-in orientation doc, shipped as package data and seeded into every box.
BRIEFING_FILE = "agent-briefing.md"

#: Linked from onboarding when a template's layout looks wrong.
DOCS_TEMPLATES_URL = "https://vincemaina.github.io/aibox/documentation.html#templates"

#: How long a cloned template is reused before aibox re-fetches it. Without a
#: ceiling, editing your template repo would never reach new boxes. A day keeps
#: `aibox run` off the network almost always while staying roughly current.
CACHE_TTL_SECONDS = 24 * 60 * 60


def _warn(message: str) -> None:
    print(f"aibox: {message}", file=sys.stderr)

#: Never copied out of a template, whatever it contains.
_EXCLUDED = {".git"}


class TemplateError(RuntimeError):
    """User-facing template failure. Caught at the CLI boundary."""


class Action(Enum):
    CREATE = "create"
    UNCHANGED = "unchanged"
    CONFLICT = "conflict"


@dataclass(frozen=True)
class Entry:
    source: Path
    target: Path
    action: Action
    #: Target path relative to the project root, for display.
    relative: str


@dataclass
class MergePlan:
    entries: list[Entry] = field(default_factory=list)

    def of(self, action: Action) -> list[Entry]:
        return [e for e in self.entries if e.action is action]


def refs_for(user: UserConfig, project: ProjectConfig) -> list[str]:
    """Template refs to apply, project overriding user-level.

    ``project.templates`` is ``None`` when the key is absent and ``[]`` when it's
    present but empty — the latter is a deliberate opt-out, so the two can't be
    collapsed with ``or``.
    """
    if project.templates is not None:
        return list(project.templates)
    return list(user.templates)


def _is_remote(ref: str) -> bool:
    """Whether a ref is something to clone rather than read in place.

    ``file://`` counts: it's a git URL pointing at a repository, not a directory
    of template files, so it has to go through clone like any other remote.
    """
    return bool(re.match(r"^(https?://|git://|ssh://|file://|git@)", ref))


def _cache_path(ref: str) -> Path:
    digest = hashlib.sha256(ref.encode("utf-8")).hexdigest()[:8]
    name = slugify(re.sub(r"\.git$", "", ref).rsplit("/", 1)[-1])
    return cache_dir() / "templates" / f"{name}-{digest}"


def _fetched_marker(dest: Path) -> Path:
    return dest.parent / f"{dest.name}.fetched"


def _age(dest: Path) -> float:
    """Seconds since this template was last fetched. ``inf`` if never/unknown."""
    marker = _fetched_marker(dest)
    try:
        return time.time() - float(marker.read_text())
    except (OSError, ValueError):
        return float("inf")


def _clone(ref: str, dest: Path) -> subprocess.CompletedProcess:
    """Clone into a staging dir and swap on success.

    Never delete the cached copy before the replacement exists — a failed fetch
    must leave the previous template intact for the offline fallback to use.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    staging = dest.parent / f"{dest.name}.incoming"
    shutil.rmtree(staging, ignore_errors=True)

    result = subprocess.run(
        ["git", "clone", "--depth", "1", "--quiet", ref, str(staging)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        shutil.rmtree(staging, ignore_errors=True)
        return result

    shutil.rmtree(dest, ignore_errors=True)
    staging.replace(dest)
    _fetched_marker(dest).write_text(str(time.time()))
    return result


def resolve(ref: str, refresh: bool = False, ttl: float = CACHE_TTL_SECONDS) -> Path:
    """Turn a template ref into a local directory.

    Local paths are read in place, so they're always current. Remote refs are
    shallow-cloned into the cache and re-cloned when the copy is older than
    ``ttl`` — otherwise editing your template repo would never reach new boxes.
    ``refresh`` forces it regardless of age.

    Re-cloning is a delete-and-clone rather than a pull: templates are tiny, and
    it can't end up in a half-merged state.

    A failed fetch with a usable cached copy is **not** an error. Being offline
    shouldn't stop a box from starting, so it warns and uses what it has.
    Cloning runs no hooks from the remote, so the fetch itself executes nothing.
    """
    if not _is_remote(ref):
        path = Path(ref).expanduser()
        if not path.is_dir():
            raise TemplateError(f"Template path does not exist: {path}")
        return path.resolve()

    dest = _cache_path(ref)
    cached = dest.is_dir()

    if cached and not refresh and _age(dest) < ttl:
        return dest

    result = _clone(ref, dest)
    if result.returncode == 0:
        return dest

    # git prints several lines of advice; the first one is the actual cause.
    error = next((line for line in (result.stderr or "").splitlines() if line.strip()), "")
    if cached and dest.is_dir():
        _warn(f"Couldn't update template '{ref}' — {error.strip()}")
        _warn("Using the cached copy.")
        return dest
    raise TemplateError(f"Failed to clone template '{ref}': {error.strip()}")


def _walk(root: Path):
    """Every file under ``root``, excluding ``_EXCLUDED`` directories."""
    for path in sorted(root.rglob("*")):
        if any(part in _EXCLUDED for part in path.relative_to(root).parts):
            continue
        if path.is_file():
            yield path


def subdir(template: Path, name: str) -> Path | None:
    """``template/name`` if it exists and holds anything, else ``None``."""
    path = template / name
    if not path.is_dir():
        return None
    return path if any(_walk(path)) else None


@dataclass(frozen=True)
class TemplateShape:
    """What a template actually contains, for reporting back during setup."""

    path: Path
    workspace_files: int
    home_files: int

    @property
    def is_usable(self) -> bool:
        """A template with neither directory silently does nothing."""
        return bool(self.workspace_files or self.home_files)

    @property
    def stray_top_level(self) -> list[str]:
        """Top-level entries that are neither ``workspace/`` nor ``home/``.

        Usually the sign of a template whose files sit at the root, which is the
        most common way to get the layout wrong.
        """
        if not self.path.is_dir():
            return []
        return sorted(
            entry.name
            for entry in self.path.iterdir()
            if entry.name not in (WORKSPACE_DIR, HOME_DIR) and entry.name not in _EXCLUDED
        )


def inspect(template: Path) -> TemplateShape:
    def count(name: str) -> int:
        directory = template / name
        return len(list(_walk(directory))) if directory.is_dir() else 0

    return TemplateShape(
        path=template,
        workspace_files=count(WORKSPACE_DIR),
        home_files=count(HOME_DIR),
    )


def plan_merge(template: Path, project: Path) -> MergePlan:
    """Classify every file in a template's ``workspace/`` against the project.

    Identical bytes count as ``UNCHANGED``, not ``CONFLICT``. That distinction is
    what makes a second ``aibox init`` silent instead of re-asking about every
    file the user already accepted.
    """
    plan = MergePlan()
    source_root = subdir(template, WORKSPACE_DIR)
    if source_root is None:
        return plan

    for source in _walk(source_root):
        relative = source.relative_to(source_root)
        target = project / relative
        if not target.exists():
            action = Action.CREATE
        elif target.is_file() and filecmp.cmp(source, target, shallow=False):
            action = Action.UNCHANGED
        else:
            action = Action.CONFLICT
        plan.entries.append(
            Entry(source=source, target=target, action=action, relative=relative.as_posix())
        )
    return plan


def copy(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def keep_both_path(target: Path) -> Path:
    """``CLAUDE.md`` -> ``CLAUDE.aibox.md``, numbering up if that's taken too."""
    candidate = target.with_name(f"{target.stem}.aibox{target.suffix}")
    counter = 1
    while candidate.exists():
        candidate = target.with_name(f"{target.stem}.aibox.{counter}{target.suffix}")
        counter += 1
    return candidate


def _write_briefing(staged: Path) -> None:
    """Seed the built-in orientation doc as the agent's in-container memory.

    Agents otherwise assume the user's machine is this machine, and waste turns
    hunting for credentials that were never mounted or trying to work around
    protections that are deliberate. Written first so a user template providing
    its own ``.claude/CLAUDE.md`` still wins.
    """
    briefing = files("aibox.image").joinpath(BRIEFING_FILE)
    target = staged / ".claude" / "CLAUDE.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(briefing.read_text(encoding="utf-8"), encoding="utf-8")


def stage_home_seed(
    templates: list[Path], project_id: str, briefing: bool = True
) -> Path:
    """Flatten the built-in briefing and every template's ``home/`` into one dir.

    Later sources overwrite earlier ones, matching the config order. Always
    returns a directory: the briefing alone is reason enough to mount it.
    """
    staged = cache_dir() / "seed" / project_id
    if staged.exists():
        shutil.rmtree(staged)
    staged.mkdir(parents=True)

    if briefing:
        _write_briefing(staged)

    for template in templates:
        source = subdir(template, HOME_DIR)
        if source is None:
            continue
        for path in _walk(source):
            copy(path, staged / path.relative_to(source))
    return staged


def load_all(refs: list[str], refresh: bool = False, **kwargs) -> list[Path]:
    try:
        return [resolve(ref, refresh=refresh, **kwargs) for ref in refs]
    except TemplateError:
        raise
    except OSError as exc:
        raise TemplateError(f"Could not read template: {exc}") from exc


__all__ = [
    "Action",
    "Entry",
    "MergePlan",
    "TemplateError",
    "SEED_MOUNT",
    "copy",
    "keep_both_path",
    "load_all",
    "plan_merge",
    "refs_for",
    "resolve",
    "stage_home_seed",
    "subdir",
]
