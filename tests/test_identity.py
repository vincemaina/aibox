import re
from datetime import datetime

import pytest

from aibox.identity import (
    IMAGE_NAME,
    ProjectIdentity,
    container_name,
    image_name,
    path_hash,
    project_id,
    resolve,
    slugify,
    volume_names,
)


class TestSlugify:
    @pytest.mark.parametrize(
        "name,expected",
        [
            ("my-project", "my-project"),
            ("My Project", "my-project"),
            ("my_project", "my-project"),
            ("MyProject", "myproject"),
            ("my-project!", "my-project"),
            ("---my---project---", "my-project"),
            ("foo  bar___baz", "foo-bar-baz"),
            ("123-abc", "123-abc"),
            ("café", "caf"),
        ],
    )
    def test_examples(self, name, expected):
        assert slugify(name) == expected

    def test_empty_falls_back_to_project(self):
        assert slugify("") == "project"

    def test_all_symbols_falls_back_to_project(self):
        assert slugify("!@#$%") == "project"


class TestPathHash:
    def test_stable_across_calls(self, tmp_path):
        assert path_hash(tmp_path) == path_hash(tmp_path)

    def test_differs_for_different_paths(self, tmp_path):
        other = tmp_path / "other"
        other.mkdir()
        assert path_hash(tmp_path) != path_hash(other)

    def test_is_eight_lowercase_hex_chars(self, tmp_path):
        assert re.fullmatch(r"[0-9a-f]{8}", path_hash(tmp_path))

    def test_case_normalised(self, tmp_path):
        """Hash should derive from the lowercased resolved path.

        Belt-and-suspenders: ``Path.resolve()`` typically canonicalises case on
        macOS/Windows already, but we lowercase too to keep project IDs stable
        regardless of FS quirks.
        """
        import hashlib
        p = tmp_path / "MixedCase"
        p.mkdir()
        expected = hashlib.sha256(str(p.resolve()).lower().encode("utf-8")).hexdigest()[:8]
        assert path_hash(p) == expected


class TestProjectId:
    def test_stable_for_same_path(self, tmp_path):
        assert project_id(tmp_path) == project_id(tmp_path)

    def test_changes_with_path(self, tmp_path):
        a = tmp_path / "a"
        b = tmp_path / "b"
        a.mkdir()
        b.mkdir()
        assert project_id(a) != project_id(b)

    def test_same_folder_name_different_parent_differs(self, tmp_path):
        a = tmp_path / "left" / "my-project"
        b = tmp_path / "right" / "my-project"
        a.mkdir(parents=True)
        b.mkdir(parents=True)
        assert project_id(a) != project_id(b)
        assert project_id(a).startswith("my-project-")
        assert project_id(b).startswith("my-project-")

    def test_uses_slugified_folder_name(self, tmp_path):
        d = tmp_path / "My Project!"
        d.mkdir()
        assert project_id(d).startswith("my-project-")


class TestImageName:
    def test_constant(self):
        assert image_name() == IMAGE_NAME == "aibox-default:latest"


class TestVolumeNames:
    def test_keys(self):
        assert set(volume_names("pid").keys()) == {"home", "tmp", "var_tmp", "opt"}

    def test_values(self):
        names = volume_names("my-project-12345678")
        assert names["home"] == "aibox-home-my-project-12345678"
        assert names["tmp"] == "aibox-tmp-my-project-12345678"
        assert names["var_tmp"] == "aibox-var-tmp-my-project-12345678"
        assert names["opt"] == "aibox-opt-my-project-12345678"


class TestContainerName:
    def test_format_with_injected_values(self):
        name = container_name(
            "my-project-12345678",
            now=datetime(2026, 5, 21, 14, 30, 0),
            rand="abc123",
        )
        assert name == "aibox-my-project-12345678-20260521-143000-abc123"

    def test_random_suffix_differs_in_same_second(self):
        same_instant = datetime(2026, 5, 21, 14, 30, 0)
        a = container_name("p", now=same_instant)
        b = container_name("p", now=same_instant)
        assert a != b

    def test_random_suffix_is_six_hex_chars(self):
        name = container_name("p", now=datetime(2026, 5, 21, 0, 0, 0))
        suffix = name.rsplit("-", 1)[-1]
        assert re.fullmatch(r"[0-9a-f]{6}", suffix)


class TestResolve:
    def test_returns_frozen_dataclass(self, tmp_path):
        identity = resolve(tmp_path)
        assert isinstance(identity, ProjectIdentity)
        with pytest.raises(Exception):
            identity.image = "other"  # frozen

    def test_no_git_present(self, tmp_path):
        identity = resolve(tmp_path)
        assert identity.git_present is False

    def test_git_present_when_dot_git_is_a_dir(self, tmp_path):
        (tmp_path / ".git").mkdir()
        assert resolve(tmp_path).git_present is True

    def test_git_absent_when_dot_git_is_a_file(self, tmp_path):
        (tmp_path / ".git").write_text("gitdir: elsewhere")
        assert resolve(tmp_path).git_present is False

    def test_populates_all_fields(self, tmp_path):
        identity = resolve(tmp_path)
        assert identity.cwd == tmp_path.resolve()
        assert identity.image == image_name()
        assert identity.project_id == project_id(tmp_path)
        assert identity.container.startswith(f"aibox-{identity.project_id}-")
        assert identity.volumes == volume_names(identity.project_id)

    def test_uses_cwd_when_no_argument(self, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        identity = resolve()
        assert identity.cwd == tmp_path.resolve()
