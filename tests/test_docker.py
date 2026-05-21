import subprocess

import pytest

from aibox import docker
from aibox.docker import DockerError, RunSpec, build_run_args
from aibox.identity import resolve


@pytest.fixture
def identity(tmp_path):
    return resolve(tmp_path)


def make_spec(identity, **overrides) -> RunSpec:
    defaults = dict(
        identity=identity,
        ports=[],
        env=[],
        env_files=[],
        docker_args=[],
        shell="/bin/bash",
        user="dev",
        mask_git=False,
    )
    defaults.update(overrides)
    return RunSpec(**defaults)


class TestBuildRunArgs:
    def test_canonical_minimal_command(self, identity):
        spec = make_spec(identity)
        args = build_run_args(spec)
        expected = [
            "docker", "run", "--rm", "-it",
            "--name", identity.container,
            "--workdir", "/workspace",
            "--user", "dev",
            "-v", f"{identity.cwd}:/workspace",
            "-v", f"{identity.volumes['home']}:/home/dev",
            "-v", f"{identity.volumes['tmp']}:/tmp",
            "-v", f"{identity.volumes['var_tmp']}:/var/tmp",
            "-v", f"{identity.volumes['opt']}:/opt",
            identity.image,
            "/bin/bash",
        ]
        assert args == expected

    def test_mask_git_adds_tmpfs_mount(self, identity):
        args = build_run_args(make_spec(identity, mask_git=True))
        assert "--mount" in args
        idx = args.index("--mount")
        assert args[idx + 1] == "type=tmpfs,destination=/workspace/.git"

    def test_mask_git_false_omits_tmpfs(self, identity):
        args = build_run_args(make_spec(identity, mask_git=False))
        assert "--mount" not in args

    def test_ports_each_get_dash_p(self, identity):
        args = build_run_args(
            make_spec(identity, ports=["3000:3000", "8000:8000"])
        )
        port_pairs = [(args[i], args[i + 1]) for i in range(len(args) - 1) if args[i] == "-p"]
        assert port_pairs == [("-p", "3000:3000"), ("-p", "8000:8000")]

    def test_env_each_gets_dash_e(self, identity):
        args = build_run_args(make_spec(identity, env=["A=1", "B=2"]))
        pairs = [(args[i], args[i + 1]) for i in range(len(args) - 1) if args[i] == "-e"]
        assert pairs == [("-e", "A=1"), ("-e", "B=2")]

    def test_env_files_each_gets_env_file_flag(self, identity):
        args = build_run_args(make_spec(identity, env_files=[".env", ".env.local"]))
        pairs = [(args[i], args[i + 1]) for i in range(len(args) - 1) if args[i] == "--env-file"]
        assert pairs == [("--env-file", ".env"), ("--env-file", ".env.local")]

    def test_custom_shell_replaces_default(self, identity):
        args = build_run_args(make_spec(identity, shell="/bin/zsh"))
        assert args[-1] == "/bin/zsh"
        assert "/bin/bash" not in args

    def test_user_override(self, identity):
        args = build_run_args(make_spec(identity, user="root"))
        idx = args.index("--user")
        assert args[idx + 1] == "root"

    def test_raw_docker_args_appended_before_image(self, identity):
        extra = ["--add-host=host.docker.internal:host-gateway", "--cap-add=SYS_PTRACE"]
        args = build_run_args(make_spec(identity, docker_args=extra))
        image_index = args.index(identity.image)
        assert args[image_index - len(extra) : image_index] == extra


class TestCheckAvailable:
    def test_raises_when_binary_missing(self, monkeypatch):
        def boom(*a, **kw):
            raise FileNotFoundError
        monkeypatch.setattr(docker.subprocess, "run", boom)
        with pytest.raises(DockerError, match="not installed"):
            docker.check_available()

    def test_raises_when_daemon_down(self, monkeypatch):
        def fake_run(*a, **kw):
            return subprocess.CompletedProcess(args=a, returncode=1, stdout="", stderr="daemon down")
        monkeypatch.setattr(docker.subprocess, "run", fake_run)
        with pytest.raises(DockerError, match="not running"):
            docker.check_available()

    def test_succeeds_when_daemon_up(self, monkeypatch):
        def fake_run(*a, **kw):
            return subprocess.CompletedProcess(args=a, returncode=0, stdout="27.0.3", stderr="")
        monkeypatch.setattr(docker.subprocess, "run", fake_run)
        docker.check_available()  # no exception


class TestImageAndVolumeExists:
    @pytest.mark.parametrize("rc,expected", [(0, True), (1, False)])
    def test_image_exists_returns_based_on_exit_code(self, monkeypatch, rc, expected):
        monkeypatch.setattr(
            docker.subprocess, "run",
            lambda *a, **kw: subprocess.CompletedProcess(args=a, returncode=rc),
        )
        assert docker.image_exists("any") is expected

    @pytest.mark.parametrize("rc,expected", [(0, True), (1, False)])
    def test_volume_exists_returns_based_on_exit_code(self, monkeypatch, rc, expected):
        monkeypatch.setattr(
            docker.subprocess, "run",
            lambda *a, **kw: subprocess.CompletedProcess(args=a, returncode=rc),
        )
        assert docker.volume_exists("any") is expected


class TestEnsureImage:
    def test_short_circuits_when_image_exists(self, monkeypatch):
        called = {"build": False}
        monkeypatch.setattr(docker, "image_exists", lambda name: True)
        monkeypatch.setattr(docker, "rebuild_image", lambda name: called.update(build=True))
        docker.ensure_image("aibox-default:latest")
        assert called["build"] is False

    def test_builds_when_image_missing(self, monkeypatch):
        called = {"build": False}
        monkeypatch.setattr(docker, "image_exists", lambda name: False)
        monkeypatch.setattr(docker, "rebuild_image", lambda name: called.update(build=True))
        docker.ensure_image("aibox-default:latest")
        assert called["build"] is True


class TestRemoveVolume:
    def test_returns_silently_on_success(self, monkeypatch):
        monkeypatch.setattr(
            docker.subprocess, "run",
            lambda *a, **kw: subprocess.CompletedProcess(args=a, returncode=0, stdout="", stderr=""),
        )
        docker.remove_volume("v")  # no exception

    def test_swallows_no_such_volume(self, monkeypatch):
        monkeypatch.setattr(
            docker.subprocess, "run",
            lambda *a, **kw: subprocess.CompletedProcess(
                args=a, returncode=1, stdout="", stderr="Error: No such volume: v",
            ),
        )
        docker.remove_volume("v")  # no exception

    def test_raises_on_other_failure(self, monkeypatch):
        monkeypatch.setattr(
            docker.subprocess, "run",
            lambda *a, **kw: subprocess.CompletedProcess(
                args=a, returncode=1, stdout="", stderr="Error: volume is in use",
            ),
        )
        with pytest.raises(DockerError, match="in use"):
            docker.remove_volume("v")
