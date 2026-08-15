"""Behavioural tests for each CLI subcommand.

All Docker interaction is mocked. `identity.resolve` is patched to point at a
``tmp_path`` so tests don't depend on the cwd.
"""

import platform

import pytest

from aibox import cli, docker, identity
from aibox.cli import main
from aibox.docker import DockerError


@pytest.fixture(autouse=True)
def isolated_user_dirs(monkeypatch, tmp_path):
    """Never read or write the developer's real ~/.config or ~/.cache."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg-config"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "xdg-cache"))


@pytest.fixture
def fake_identity(monkeypatch, tmp_path):
    ident = identity.resolve(tmp_path)
    monkeypatch.setattr(cli.identity, "resolve", lambda *a, **kw: ident)
    monkeypatch.setattr(cli.docker, "check_available", lambda: None)
    monkeypatch.setattr(cli.docker, "ensure_image", lambda name: None)
    monkeypatch.setattr(cli.docker, "rebuild_image", lambda name: None)
    return ident


def write_template(root, workspace=None, home=None):
    for name, files in (("workspace", workspace), ("home", home)):
        for relative, content in (files or {}).items():
            path = root / name / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
    return root


class TestCmdInit:
    def test_reports_when_no_templates_configured(self, fake_identity, capsys):
        assert main(["init"]) == 0
        assert "No templates configured" in capsys.readouterr().out

    def test_creates_files_from_template(self, fake_identity, tmp_path, capsys):
        template = write_template(tmp_path / "tpl", workspace={"CLAUDE.md": "hi"})
        assert main(["init", "--template", str(template), "--yes"]) == 0
        assert (fake_identity.cwd / "CLAUDE.md").read_text() == "hi"
        assert "created" in capsys.readouterr().out

    def test_dry_run_writes_nothing(self, fake_identity, tmp_path):
        template = write_template(tmp_path / "tpl", workspace={"CLAUDE.md": "hi"})
        main(["init", "--template", str(template), "--dry-run"])
        assert not (fake_identity.cwd / "CLAUDE.md").exists()

    def test_skip_keeps_existing_file(self, fake_identity, tmp_path):
        template = write_template(tmp_path / "tpl", workspace={"CLAUDE.md": "theirs"})
        (fake_identity.cwd / "CLAUDE.md").write_text("mine")
        main(["init", "--template", str(template), "--on-conflict", "skip"])
        assert (fake_identity.cwd / "CLAUDE.md").read_text() == "mine"

    def test_replace_overwrites(self, fake_identity, tmp_path):
        template = write_template(tmp_path / "tpl", workspace={"CLAUDE.md": "theirs"})
        (fake_identity.cwd / "CLAUDE.md").write_text("mine")
        main(["init", "--template", str(template), "--on-conflict", "replace"])
        assert (fake_identity.cwd / "CLAUDE.md").read_text() == "theirs"

    def test_keep_both_writes_alongside(self, fake_identity, tmp_path):
        template = write_template(tmp_path / "tpl", workspace={"CLAUDE.md": "theirs"})
        (fake_identity.cwd / "CLAUDE.md").write_text("mine")
        main(["init", "--template", str(template), "--on-conflict", "keep-both"])
        assert (fake_identity.cwd / "CLAUDE.md").read_text() == "mine"
        assert (fake_identity.cwd / "CLAUDE.aibox.md").read_text() == "theirs"

    def test_non_tty_falls_back_to_skip(self, fake_identity, tmp_path, monkeypatch, capsys):
        # The default policy is "ask"; with no terminal it must not block.
        monkeypatch.setattr(cli.sys.stdin, "isatty", lambda: False)
        template = write_template(tmp_path / "tpl", workspace={"CLAUDE.md": "theirs"})
        (fake_identity.cwd / "CLAUDE.md").write_text("mine")
        assert main(["init", "--template", str(template)]) == 0
        assert "not a terminal" in capsys.readouterr().out
        assert (fake_identity.cwd / "CLAUDE.md").read_text() == "mine"

    def test_identical_file_reported_unchanged(self, fake_identity, tmp_path, capsys):
        template = write_template(tmp_path / "tpl", workspace={"CLAUDE.md": "same"})
        (fake_identity.cwd / "CLAUDE.md").write_text("same")
        main(["init", "--template", str(template), "--yes"])
        assert "unchanged" in capsys.readouterr().out

    def test_home_dir_is_not_written_to_project(self, fake_identity, tmp_path):
        template = write_template(
            tmp_path / "tpl",
            workspace={"CLAUDE.md": "x"},
            home={".claude/skills/s/SKILL.md": "y"},
        )
        main(["init", "--template", str(template), "--yes"])
        assert not (fake_identity.cwd / ".claude").exists()

    def test_bad_template_path_is_a_clean_error(self, fake_identity, tmp_path, capsys):
        assert main(["init", "--template", str(tmp_path / "nope")]) == 1
        assert "Error:" in capsys.readouterr().err


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
            "Git access:",
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

    def _capture_spec(self, monkeypatch, tmp_path, argv):
        (tmp_path / ".git").mkdir(exist_ok=True)
        ident = identity.resolve(tmp_path)
        monkeypatch.setattr(cli.identity, "resolve", lambda *a, **kw: ident)
        monkeypatch.setattr(cli.docker, "check_available", lambda: None)
        monkeypatch.setattr(cli.docker, "ensure_image", lambda name: None)
        captured = {}
        monkeypatch.setattr(cli.docker, "run_container", lambda spec: captured.setdefault("spec", spec) or 0)
        main(argv)
        return captured["spec"]

    def test_git_mode_defaults_to_commit(self, monkeypatch, tmp_path):
        spec = self._capture_spec(monkeypatch, tmp_path, ["run"])
        assert spec.git_mode == "commit"

    @pytest.mark.parametrize("mode", ["masked", "readonly", "commit"])
    def test_git_flag_selects_mode(self, monkeypatch, tmp_path, mode):
        spec = self._capture_spec(monkeypatch, tmp_path, ["run", "--git", mode])
        assert spec.git_mode == mode

    def test_agent_briefing_is_always_seeded(self, monkeypatch, tmp_path):
        # Even with no templates configured, every box gets the orientation doc.
        spec = self._capture_spec(monkeypatch, tmp_path, ["run"])
        assert spec.home_seed is not None
        assert (spec.home_seed / ".claude" / "CLAUDE.md").is_file()
        assert docker.SEED_MOUNT in " ".join(docker.build_run_args(spec))

    def test_template_home_is_staged_and_mounted(self, monkeypatch, tmp_path):
        template = write_template(tmp_path / "tpl", home={".claude/skills/s/SKILL.md": "y"})
        (tmp_path / ".aibox.toml").write_text(f'templates = ["{template}"]\n')
        spec = self._capture_spec(monkeypatch, tmp_path, ["run"])
        assert spec.home_seed is not None
        assert (spec.home_seed / ".claude" / "skills" / "s" / "SKILL.md").read_text() == "y"
        assert docker.SEED_MOUNT in " ".join(docker.build_run_args(spec))

    def test_workspace_only_template_does_not_add_home_files(self, monkeypatch, tmp_path):
        template = write_template(tmp_path / "tpl", workspace={"CLAUDE.md": "x"})
        (tmp_path / ".aibox.toml").write_text(f'templates = ["{template}"]\n')
        spec = self._capture_spec(monkeypatch, tmp_path, ["run"])
        seeded = sorted(p.name for p in spec.home_seed.rglob("*") if p.is_file())
        assert seeded == ["CLAUDE.md"]  # the briefing only


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
