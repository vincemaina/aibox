import pytest

from aibox import userconfig
from aibox.config import ConfigError


@pytest.fixture
def config_home(tmp_path, monkeypatch):
    """Point XDG_CONFIG_HOME at a tmp dir and return the aibox config dir."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    directory = tmp_path / "aibox"
    directory.mkdir()
    return directory


class TestPaths:
    def test_xdg_config_home_is_respected(self, tmp_path, monkeypatch):
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
        assert userconfig.config_dir() == tmp_path / "aibox"

    def test_falls_back_to_dot_config(self, monkeypatch, tmp_path):
        monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
        monkeypatch.setattr(userconfig.Path, "home", classmethod(lambda cls: tmp_path))
        assert userconfig.config_dir() == tmp_path / ".config" / "aibox"

    def test_xdg_cache_home_is_respected(self, tmp_path, monkeypatch):
        monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
        assert userconfig.cache_dir() == tmp_path / "aibox"

    def test_config_path_is_inside_config_dir(self, tmp_path, monkeypatch):
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
        assert userconfig.config_path().parent == userconfig.config_dir()


class TestLoad:
    def test_missing_file_returns_empty(self, config_home):
        assert userconfig.load() == userconfig.UserConfig()

    def test_loads_templates(self, config_home):
        (config_home / "config.toml").write_text(
            'templates = ["https://example.com/t.git", "~/local"]\n'
        )
        assert userconfig.load().templates == ["https://example.com/t.git", "~/local"]

    def test_unknown_key_raises(self, config_home):
        (config_home / "config.toml").write_text('nope = 1\n')
        with pytest.raises(ConfigError, match="unknown key"):
            userconfig.load()

    def test_non_list_templates_raises(self, config_home):
        (config_home / "config.toml").write_text('templates = "one"\n')
        with pytest.raises(ConfigError, match="must be a list"):
            userconfig.load()

    def test_non_string_entry_raises(self, config_home):
        (config_home / "config.toml").write_text("templates = [1]\n")
        with pytest.raises(ConfigError, match="must be a list"):
            userconfig.load()

    def test_malformed_toml_raises(self, config_home):
        (config_home / "config.toml").write_text("[[[\n")
        with pytest.raises(ConfigError, match="parse error"):
            userconfig.load()


class TestSave:
    def test_round_trips_through_load(self, config_home):
        userconfig.save(userconfig.UserConfig(templates=["https://x/y.git", "~/local"]))
        assert userconfig.load().templates == ["https://x/y.git", "~/local"]

    def test_empty_list_round_trips(self, config_home):
        userconfig.save(userconfig.UserConfig())
        assert userconfig.load().templates == []

    def test_creates_missing_directory(self, tmp_path, monkeypatch):
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "brand-new"))
        assert userconfig.save(userconfig.UserConfig()).is_file()

    def test_escapes_backslashes(self, config_home):
        # Windows paths would otherwise produce invalid TOML escapes.
        userconfig.save(userconfig.UserConfig(templates=[r"C:\Users\me\tpl"]))
        assert userconfig.load().templates == [r"C:\Users\me\tpl"]

    def test_exists_reflects_the_file(self, config_home):
        assert not userconfig.exists()
        userconfig.save(userconfig.UserConfig())
        assert userconfig.exists()


class TestProjectState:
    @pytest.fixture(autouse=True)
    def state_home(self, tmp_path, monkeypatch):
        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))

    def test_starts_empty(self):
        assert userconfig.declined_projects() == set()

    def test_records_and_reads_back(self):
        userconfig.decline_project("proj-abc")
        assert userconfig.declined_projects() == {"proj-abc"}

    def test_accumulates(self):
        userconfig.decline_project("a")
        userconfig.decline_project("b")
        assert userconfig.declined_projects() == {"a", "b"}

    def test_corrupt_state_is_ignored_not_fatal(self):
        path = userconfig.state_dir() / userconfig.STATE_FILENAME
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("not json {")
        assert userconfig.declined_projects() == set()

    def test_state_is_separate_from_config(self, tmp_path, monkeypatch):
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
        assert userconfig.state_dir() != userconfig.config_dir()
