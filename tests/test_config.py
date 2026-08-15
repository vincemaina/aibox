import argparse

import pytest

from aibox.config import CONFIG_FILENAME, ConfigError, ProjectConfig, load, merge
from aibox.identity import resolve


@pytest.fixture
def identity(tmp_path):
    return resolve(tmp_path)


def make_namespace(**overrides) -> argparse.Namespace:
    defaults = dict(
        command="run",
        port=[],
        env=[],
        env_file=[],
        shell=None,
        docker_arg=[],
        user=None,
        git=None,
    )
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


class TestLoad:
    def test_missing_file_returns_empty_config(self, tmp_path):
        assert load(tmp_path) == ProjectConfig()

    def test_loads_every_field(self, tmp_path):
        (tmp_path / CONFIG_FILENAME).write_text(
            'ports = ["3000:3000", "8000:8000"]\n'
            'env = ["NODE_ENV=development"]\n'
            'env_files = [".env"]\n'
            'shell = "/bin/zsh"\n'
            'docker_args = ["--cap-add=SYS_PTRACE"]\n'
        )
        cfg = load(tmp_path)
        assert cfg.ports == ["3000:3000", "8000:8000"]
        assert cfg.env == ["NODE_ENV=development"]
        assert cfg.env_files == [".env"]
        assert cfg.shell == "/bin/zsh"
        assert cfg.docker_args == ["--cap-add=SYS_PTRACE"]

    def test_unknown_key_raises(self, tmp_path):
        (tmp_path / CONFIG_FILENAME).write_text('port = ["3000:3000"]\n')
        with pytest.raises(ConfigError, match="unknown key"):
            load(tmp_path)

    def test_non_string_in_list_raises(self, tmp_path):
        (tmp_path / CONFIG_FILENAME).write_text("ports = [3000]\n")
        with pytest.raises(ConfigError, match="entries must be strings"):
            load(tmp_path)

    def test_non_list_in_list_field_raises(self, tmp_path):
        (tmp_path / CONFIG_FILENAME).write_text('ports = "3000:3000"\n')
        with pytest.raises(ConfigError, match="must be a list"):
            load(tmp_path)

    def test_non_string_shell_raises(self, tmp_path):
        (tmp_path / CONFIG_FILENAME).write_text("shell = 1\n")
        with pytest.raises(ConfigError, match="'shell' must be a string"):
            load(tmp_path)

    def test_malformed_toml_raises(self, tmp_path):
        (tmp_path / CONFIG_FILENAME).write_text("not toml [[[\n")
        with pytest.raises(ConfigError, match="parse error"):
            load(tmp_path)

    @pytest.mark.parametrize("mode", ["masked", "readonly", "commit"])
    def test_loads_each_git_mode(self, tmp_path, mode):
        (tmp_path / CONFIG_FILENAME).write_text(f'git = "{mode}"\n')
        assert load(tmp_path).git == mode

    def test_invalid_git_mode_raises(self, tmp_path):
        (tmp_path / CONFIG_FILENAME).write_text('git = "readwrite"\n')
        with pytest.raises(ConfigError, match="'git' must be one of"):
            load(tmp_path)


class TestMerge:
    def test_cli_appends_to_config_lists(self, identity):
        cfg = ProjectConfig(
            ports=["1:1"],
            env=["A=1"],
            env_files=[".env"],
            docker_args=["--cap-add=SYS_PTRACE"],
        )
        args = make_namespace(
            port=["2:2"],
            env=["B=2"],
            env_file=[".env.local"],
            docker_arg=["--privileged"],
        )
        spec = merge(cfg, args, identity)
        assert spec.ports == ["1:1", "2:2"]
        assert spec.env == ["A=1", "B=2"]
        assert spec.env_files == [".env", ".env.local"]
        assert spec.docker_args == ["--cap-add=SYS_PTRACE", "--privileged"]

    def test_cli_shell_overrides_config(self, identity):
        spec = merge(ProjectConfig(shell="/bin/zsh"), make_namespace(shell="/bin/fish"), identity)
        assert spec.shell == "/bin/fish"

    def test_config_shell_wins_when_no_cli_shell(self, identity):
        spec = merge(ProjectConfig(shell="/bin/zsh"), make_namespace(shell=None), identity)
        assert spec.shell == "/bin/zsh"

    def test_default_shell_when_neither_set(self, identity):
        spec = merge(ProjectConfig(), make_namespace(shell=None), identity)
        assert spec.shell == "/bin/bash"

    def test_user_passes_through_from_cli(self, identity):
        spec = merge(ProjectConfig(), make_namespace(user="root"), identity)
        assert spec.user == "root"

    def test_user_none_passes_through(self, identity):
        spec = merge(ProjectConfig(), make_namespace(user=None), identity)
        assert spec.user is None

    def test_git_mode_defaults_to_commit(self, identity):
        spec = merge(ProjectConfig(), make_namespace(), identity)
        assert spec.git_mode == "commit"

    def test_config_git_wins_when_no_cli_flag(self, identity):
        spec = merge(ProjectConfig(git="masked"), make_namespace(), identity)
        assert spec.git_mode == "masked"

    def test_cli_git_overrides_config(self, identity):
        spec = merge(ProjectConfig(git="masked"), make_namespace(git="readonly"), identity)
        assert spec.git_mode == "readonly"
