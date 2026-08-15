"""Docker CLI wrapper.

All ``subprocess.run`` calls in the project live here. Composition of
``docker run`` arguments is in the pure function :func:`build_run_args` so it
can be snapshot-tested without invoking Docker.
"""

from __future__ import annotations

import os
import platform
import subprocess
from dataclasses import dataclass
from importlib.resources import as_file, files
from pathlib import Path

from .identity import ProjectIdentity


class DockerError(RuntimeError):
    """User-facing Docker failure. Caught at the CLI boundary."""


#: Where staged template ``home/`` content is bind-mounted for the entrypoint to
#: copy into ``/home/dev``. Defined here rather than in ``templates`` because
#: that module imports ``config``, which imports this one.
SEED_MOUNT = "/run/aibox-seed"

#: How much of the host ``.git`` the container gets. See :func:`_git_mount_args`.
GIT_MODES = ("masked", "readonly", "commit")
DEFAULT_GIT_MODE = "commit"

#: Author/committer used when the repo itself names no identity. The host's
#: global ``~/.gitconfig`` isn't mounted, so without these ``git commit`` fails
#: with "please tell me who you are". A distinct identity also makes it obvious
#: in ``git log`` which commits came from the sandbox.
GIT_IDENTITY = {
    "GIT_AUTHOR_NAME": "aibox agent",
    "GIT_AUTHOR_EMAIL": "agent@aibox.local",
    "GIT_COMMITTER_NAME": "aibox agent",
    "GIT_COMMITTER_EMAIL": "agent@aibox.local",
}


@dataclass(frozen=True)
class RunSpec:
    identity: ProjectIdentity
    ports: list[str]
    env: list[str]
    env_files: list[str]
    docker_args: list[str]
    shell: str
    user: str | None
    git_mode: str
    #: Staged template ``home/`` content to seed ``/home/dev`` with, if any.
    home_seed: Path | None = None


def _host_uid_gid() -> tuple[int, int]:
    """Return (uid, gid) of the invoking host user, with sane fallbacks on Windows."""
    uid = getattr(os, "getuid", lambda: 1000)()
    gid = getattr(os, "getgid", lambda: 1000)()
    return uid, gid


def _terminal_env_args() -> list[str]:
    """Forward the host terminal's TERM/COLORTERM so colour support matches.

    `docker run -it` otherwise defaults TERM to `xterm` (8 colours) instead of
    the host's value (often `xterm-256color` → 256 colours). The matching
    terminfo entries ship with the image's ncurses. Added before the user's own
    `-e` flags so an explicit `--env TERM=...` still wins.
    """
    args: list[str] = []
    for var in ("TERM", "COLORTERM"):
        value = os.environ.get(var)
        if value:
            args += ["-e", f"{var}={value}"]
    return args


def _git_mount_args(spec: RunSpec) -> list[str]:
    """Mounts controlling the agent's access to the host ``.git``.

    ``.git`` arrives inside the container for free as part of the ``/workspace``
    bind mount, so every mode here is about layering something on top of it:

    - ``masked``   — tmpfs over ``.git``. The agent sees an empty git dir and can
      neither read history nor commit. This was the original default.
    - ``readonly`` — bind ``.git`` over itself read-only. History is readable,
      nothing in it can be changed.
    - ``commit``   — ``.git`` stays writable so the agent can commit, branch, and
      rebase. Two things are held back, because both are executed by *host* git
      the next time you run it and would otherwise be a route out of the
      sandbox: ``hooks/`` is replaced with a root-owned tmpfs, and ``config`` is
      re-bound read-only (it can name commands via ``core.pager``,
      ``core.sshCommand``, ``filter.*``, and friends). Applied to submodule git
      dirs too. Container-local git config still works via ``~/.gitconfig``,
      which lives on the per-project home volume.
    """
    if not spec.identity.git_dirs:
        return []

    if spec.git_mode == "masked":
        return ["--mount", "type=tmpfs,target=/workspace/.git"]

    def target(path: Path) -> str:
        return f"/workspace/{path.relative_to(spec.identity.cwd).as_posix()}"

    if spec.git_mode == "readonly":
        root = spec.identity.git_dirs[0]
        return ["--mount", f"type=bind,source={root},target={target(root)},readonly"]

    args: list[str] = []
    for git_dir in spec.identity.git_dirs:
        args += ["--mount", f"type=tmpfs,target={target(git_dir / 'hooks')}"]
        config = git_dir / "config"
        if config.is_file():
            args += [
                "--mount",
                f"type=bind,source={config},target={target(config)},readonly",
            ]
    return args


def _install_hint() -> str:
    """Platform-appropriate advice for getting a Docker daemon running."""
    if platform.system() == "Linux":
        return "Install Docker Engine and start it with 'sudo systemctl start docker'."
    return "Install Docker Desktop and make sure it is running."


def check_available() -> None:
    try:
        result = subprocess.run(
            ["docker", "version", "--format", "{{.Server.Version}}"],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError as exc:
        raise DockerError(
            f"Docker is not installed or not on PATH. {_install_hint()}"
        ) from exc
    if result.returncode == 0:
        return

    # A reachable-but-forbidden socket is a distinct failure from a dead daemon:
    # on Linux it usually means the user is not in the `docker` group. Reporting
    # it as "not running" sends people off restarting a daemon that is already up.
    stderr = result.stderr or ""
    if "permission denied" in stderr.lower():
        message = "Permission denied connecting to the Docker daemon."
        if platform.system() == "Linux":
            message += (
                " Add yourself to the 'docker' group with"
                " 'sudo usermod -aG docker $USER', then log out and back in"
                " for the change to take effect."
            )
        raise DockerError(message)

    raise DockerError(f"Docker is not running. {_install_hint()}")


def image_exists(name: str) -> bool:
    result = subprocess.run(
        ["docker", "image", "inspect", name],
        capture_output=True,
        check=False,
    )
    return result.returncode == 0


def volume_exists(name: str) -> bool:
    result = subprocess.run(
        ["docker", "volume", "inspect", name],
        capture_output=True,
        check=False,
    )
    return result.returncode == 0


def build_image(name: str, dockerfile_path: Path, context_dir: Path) -> None:
    result = subprocess.run(
        ["docker", "build", "-t", name, "-f", str(dockerfile_path), str(context_dir)],
        check=False,
    )
    if result.returncode != 0:
        raise DockerError(f"Image build failed (exit code {result.returncode}).")


def _with_bundled_dockerfile(action):
    dockerfile_ref = files("aibox.image").joinpath("Dockerfile")
    with as_file(dockerfile_ref) as path:
        action(path)


def ensure_image(name: str) -> None:
    if image_exists(name):
        return
    rebuild_image(name)


def rebuild_image(name: str) -> None:
    _with_bundled_dockerfile(lambda path: build_image(name, path, path.parent))


def remove_volume(name: str) -> None:
    result = subprocess.run(
        ["docker", "volume", "rm", name],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode == 0:
        return
    if "no such volume" in (result.stderr or "").lower():
        return
    raise DockerError(
        f"Failed to remove volume '{name}': {(result.stderr or '').strip()}"
    )


def build_run_args(spec: RunSpec) -> list[str]:
    args: list[str] = [
        "docker", "run", "--rm", "-it",
        "--name", spec.identity.container,
        "--workdir", "/workspace",
    ]

    if spec.user is not None:
        args += ["--user", spec.user]

    args += [
        "--mount", f"type=bind,source={spec.identity.cwd},target=/workspace",
        "--mount", f"type=volume,source={spec.identity.volumes['home']},target=/home/dev",
        "--mount", f"type=volume,source={spec.identity.volumes['tmp']},target=/tmp",
        "--mount", f"type=volume,source={spec.identity.volumes['var_tmp']},target=/var/tmp",
        "--mount", f"type=volume,source={spec.identity.volumes['opt']},target=/opt",
    ]

    args += _git_mount_args(spec)

    # Read-only: the entrypoint copies out of it, nothing writes back into it.
    if spec.home_seed is not None:
        args += [
            "--mount",
            f"type=bind,source={spec.home_seed},target={SEED_MOUNT},readonly",
        ]

    # The entrypoint uses these to retune the in-container `dev` user when running as root.
    uid, gid = _host_uid_gid()
    args += ["-e", f"HOST_UID={uid}", "-e", f"HOST_GID={gid}"]

    # Forward host terminal colour capability (added before user env so --env wins).
    args += _terminal_env_args()

    # Fallback commit identity. Like the terminal vars, these go before the
    # user's own -e flags so `--env GIT_AUTHOR_NAME=...` still wins.
    if spec.git_mode == "commit":
        for key, value in GIT_IDENTITY.items():
            args += ["-e", f"{key}={value}"]

    for port in spec.ports:
        args += ["-p", port]
    for env in spec.env:
        args += ["-e", env]
    for env_file in spec.env_files:
        args += ["--env-file", env_file]

    args += list(spec.docker_args)
    args += [spec.identity.image, spec.shell]
    return args


def run_container(spec: RunSpec) -> int:
    result = subprocess.run(build_run_args(spec), check=False)
    return result.returncode
