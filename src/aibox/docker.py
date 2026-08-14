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


@dataclass(frozen=True)
class RunSpec:
    identity: ProjectIdentity
    ports: list[str]
    env: list[str]
    env_files: list[str]
    docker_args: list[str]
    shell: str
    user: str | None
    mask_git: bool


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
    dockerfile_ref = files("aibox.templates").joinpath("Dockerfile")
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

    if spec.mask_git:
        args += ["--mount", "type=tmpfs,target=/workspace/.git"]

    # The entrypoint uses these to retune the in-container `dev` user when running as root.
    uid, gid = _host_uid_gid()
    args += ["-e", f"HOST_UID={uid}", "-e", f"HOST_GID={gid}"]

    # Forward host terminal colour capability (added before user env so --env wins).
    args += _terminal_env_args()

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
