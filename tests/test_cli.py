"""Behavioural tests for each CLI subcommand.

All Docker interaction is mocked. `identity.resolve` is patched to point at a
``tmp_path`` so tests don't depend on the cwd.
"""

import platform

import pytest

from aibox import cli, docker, identity
from aibox.cli import main
from aibox.docker import DockerError


@pytest.fixture
def fake_identity(monkeypatch, tmp_path):
    ident = identity.resolve(tmp_path)
    monkeypatch.setattr(cli.identity, "resolve", lambda *a, **kw: ident)
    monkeypatch.setattr(cli.docker, "check_available", lambda: None)
    monkeypatch.setattr(cli.docker, "ensure_image", lambda name: None)
    monkeypatch.setattr(cli.docker, "rebuild_image", lambda name: None)
    return ident


class TestCmdInfo:
    def test_prints_all_summary_fields(self, fake_identity, capsys):
        assert main(["info"]) == 0
        out = capsys.readouterr().out
        for line in (
            "Project path:",
            "Project ID:",
            "Container:",
            "Image:",
            "Home volume:",
            "Tmp volume:",
            "Var tmp volume:",
            "Opt volume:",
            "Git hidden:",
        ):
            assert line in out
        assert fake_identity.project_id in out
        assert fake_identity.image in out
        for volume in fake_identity.volumes.values():
            assert volume in out


class TestCmdRun:
    def test_returns_docker_exit_code(self, fake_identity, monkeypatch):
        monkeypatch.setattr(cli.docker, "run_container", lambda spec: 42)
        assert main(["run"]) == 42

    def test_no_args_defaults_to_run(self, fake_identity, monkeypatch):
        called = {"ran": False}

        def fake_run(spec):
            called["ran"] = True
            return 0

        monkeypatch.setattr(cli.docker, "run_container", fake_run)
        assert main([]) == 0
        assert called["ran"] is True

    def test_passes_flags_into_run_spec(self, fake_identity, monkeypatch):
        captured = {}
        monkeypatch.setattr(cli.docker, "run_container", lambda spec: captured.setdefault("spec", spec) or 0)
        main(["run", "-p", "3000:3000", "-e", "X=1", "--shell", "/bin/zsh", "--user", "root"])
        spec = captured["spec"]
        assert spec.ports == ["3000:3000"]
        assert spec.env == ["X=1"]
        assert spec.shell == "/bin/zsh"
        assert spec.user == "root"

    def test_mask_git_follows_identity(self, monkeypatch, tmp_path):
        (tmp_path / ".git").mkdir()
        ident = identity.resolve(tmp_path)
        monkeypatch.setattr(cli.identity, "resolve", lambda *a, **kw: ident)
        monkeypatch.setattr(cli.docker, "check_available", lambda: None)
        monkeypatch.setattr(cli.docker, "ensure_image", lambda name: None)
        captured = {}
        monkeypatch.setattr(cli.docker, "run_container", lambda spec: captured.setdefault("spec", spec) or 0)
        main(["run"])
        assert captured["spec"].mask_git is True


class TestCmdRemoveVolume:
    def _all_volumes_exist(self, monkeypatch):
        monkeypatch.setattr(cli.docker, "volume_exists", lambda name: True)

    def test_force_skips_prompt_and_removes(self, fake_identity, monkeypatch):
        self._all_volumes_exist(monkeypatch)
        removed = []
        monkeypatch.setattr(cli.docker, "remove_volume", lambda name: removed.append(name))
        assert main(["remove-volume", "--force"]) == 0
        assert removed == list(fake_identity.volumes.values())

    def test_prompt_yes_removes(self, fake_identity, monkeypatch):
        self._all_volumes_exist(monkeypatch)
        removed = []
        monkeypatch.setattr(cli.docker, "remove_volume", lambda name: removed.append(name))
        monkeypatch.setattr("builtins.input", lambda prompt: "y")
        assert main(["remove-volume"]) == 0
        assert len(removed) == 4

    def test_prompt_no_aborts(self, fake_identity, monkeypatch):
        self._all_volumes_exist(monkeypatch)
        removed = []
        monkeypatch.setattr(cli.docker, "remove_volume", lambda name: removed.append(name))
        monkeypatch.setattr("builtins.input", lambda prompt: "n")
        assert main(["remove-volume"]) == 0
        assert removed == []

    def test_skips_volumes_that_do_not_exist(self, fake_identity, monkeypatch, capsys):
        monkeypatch.setattr(cli.docker, "volume_exists", lambda name: False)
        removed = []
        monkeypatch.setattr(cli.docker, "remove_volume", lambda name: removed.append(name))
        assert main(["remove-volume", "--force"]) == 0
        assert removed == []
        assert "Skipped" in capsys.readouterr().out


class TestPlatformAwareDefaultUser:
    def test_macos_default_is_dev(self, monkeypatch):
        monkeypatch.setattr(cli.platform, "system", lambda: "Darwin")
        assert cli._default_user() == "dev"

    def test_windows_default_is_dev(self, monkeypatch):
        monkeypatch.setattr(cli.platform, "system", lambda: "Windows")
        assert cli._default_user() == "dev"

    def test_linux_default_is_none(self, monkeypatch):
        monkeypatch.setattr(cli.platform, "system", lambda: "Linux")
        assert cli._default_user() is None


class TestCmdRebuildImage:
    def test_calls_rebuild(self, monkeypatch):
        called = {}
        monkeypatch.setattr(cli.docker, "check_available", lambda: None)
        monkeypatch.setattr(cli.docker, "rebuild_image", lambda name: called.setdefault("name", name))
        assert main(["rebuild-image"]) == 0
        assert called["name"] == "aibox-default:latest"


class TestErrorHandling:
    def test_docker_error_prints_clean_message(self, monkeypatch, capsys):
        def boom():
            raise DockerError("daemon down")
        monkeypatch.setattr(cli.docker, "check_available", boom)
        assert main(["rebuild-image"]) == 1
        err = capsys.readouterr().err
        assert "daemon down" in err
        assert "Traceback" not in err
