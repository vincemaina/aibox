"""First-run setup and the per-project import offer.

The overriding rule under test: neither flow may ever block a non-interactive
run. Most of these assert that aibox stays quiet when there's no terminal.
"""

import pytest

from aibox import onboarding, templates, userconfig
from aibox.userconfig import UserConfig


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))


@pytest.fixture
def tty(monkeypatch):
    monkeypatch.setattr(onboarding, "interactive", lambda: True)


def answers(monkeypatch, *replies):
    """Feed scripted answers to every prompt, failing loudly if it wants more."""
    queue = list(replies)

    def fake_ask(prompt, default=""):
        assert queue, f"unexpected extra prompt: {prompt!r}"
        return queue.pop(0)

    monkeypatch.setattr(onboarding, "_ask", fake_ask)
    return queue


def make_template(root, workspace=None, home=None, loose=None):
    for name, files in (("workspace", workspace), ("home", home)):
        for relative, content in (files or {}).items():
            path = root / name / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
    for relative, content in (loose or {}).items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    root.mkdir(parents=True, exist_ok=True)
    return root


class TestInspect:
    def test_counts_both_directories(self, tmp_path):
        t = make_template(tmp_path / "t", workspace={"a": "1", "b": "2"}, home={"c": "3"})
        shape = templates.inspect(t)
        assert (shape.workspace_files, shape.home_files) == (2, 1)
        assert shape.is_usable

    def test_template_with_neither_directory_is_unusable(self, tmp_path):
        t = make_template(tmp_path / "t", loose={"CLAUDE.md": "x"})
        assert not templates.inspect(t).is_usable

    def test_stray_top_level_entries_are_reported(self, tmp_path):
        t = make_template(tmp_path / "t", loose={"CLAUDE.md": "x", "README.md": "y"})
        assert templates.inspect(t).stray_top_level == ["CLAUDE.md", "README.md"]

    def test_workspace_and_home_are_not_stray(self, tmp_path):
        t = make_template(tmp_path / "t", workspace={"a": "1"}, home={"b": "2"})
        assert templates.inspect(t).stray_top_level == []


class TestRunSetup:
    def test_skipped_when_config_already_exists(self, tty):
        userconfig.save(UserConfig(templates=["x"]))
        assert onboarding.run_setup() is None

    def test_forced_run_ignores_existing_config(self, tty, monkeypatch):
        userconfig.save(UserConfig(templates=["x"]))
        answers(monkeypatch, "")
        assert onboarding.run_setup(force=True) is not None

    def test_never_prompts_without_a_terminal(self, monkeypatch):
        monkeypatch.setattr(onboarding, "interactive", lambda: False)
        monkeypatch.setattr(
            onboarding, "_ask", lambda *a, **kw: pytest.fail("prompted with no tty")
        )
        assert onboarding.run_setup() is None

    def test_skipping_still_writes_config_so_it_asks_once(self, tty, monkeypatch):
        answers(monkeypatch, "")
        config = onboarding.run_setup()
        assert config.templates == []
        assert userconfig.exists()
        assert onboarding.run_setup() is None  # second run is silent

    def test_accepts_a_valid_template(self, tty, monkeypatch, tmp_path):
        t = make_template(tmp_path / "t", workspace={"CLAUDE.md": "x"})
        answers(monkeypatch, str(t), "")
        assert onboarding.run_setup().templates == [str(t)]

    def test_collects_several_templates_in_order(self, tty, monkeypatch, tmp_path):
        a = make_template(tmp_path / "a", workspace={"1": "1"})
        b = make_template(tmp_path / "b", home={"2": "2"})
        answers(monkeypatch, str(a), str(b), "")
        assert onboarding.run_setup().templates == [str(a), str(b)]

    def test_unusable_template_is_confirmed_before_use(self, tty, monkeypatch, tmp_path, capsys):
        t = make_template(tmp_path / "t", loose={"CLAUDE.md": "x"})
        answers(monkeypatch, str(t), "n", "")  # offered, declined, then finish
        assert onboarding.run_setup().templates == []
        out = capsys.readouterr().out
        assert "no workspace/ or home/" in out
        assert templates.DOCS_TEMPLATES_URL in out

    def test_unusable_template_can_be_kept_anyway(self, tty, monkeypatch, tmp_path):
        t = make_template(tmp_path / "t", loose={"CLAUDE.md": "x"})
        answers(monkeypatch, str(t), "y", "")
        assert onboarding.run_setup().templates == [str(t)]

    def test_bad_path_is_reported_not_raised(self, tty, monkeypatch, tmp_path, capsys):
        answers(monkeypatch, str(tmp_path / "nope"), "")
        assert onboarding.run_setup().templates == []
        assert "does not exist" in capsys.readouterr().out


class TestOfferImport:
    def _template(self, tmp_path):
        return make_template(tmp_path / "t", workspace={"CLAUDE.md": "x"})

    def test_offers_when_files_would_be_added(self, tty, monkeypatch, tmp_path):
        answers(monkeypatch, "y")
        assert onboarding.offer_import([self._template(tmp_path)], tmp_path / "p", "p-1")

    def test_silent_without_a_terminal(self, monkeypatch, tmp_path):
        monkeypatch.setattr(onboarding, "interactive", lambda: False)
        monkeypatch.setattr(
            onboarding, "_ask", lambda *a, **kw: pytest.fail("prompted with no tty")
        )
        assert not onboarding.offer_import([self._template(tmp_path)], tmp_path / "p", "p-1")

    def test_silent_without_templates(self, tty, monkeypatch, tmp_path):
        monkeypatch.setattr(
            onboarding, "_ask", lambda *a, **kw: pytest.fail("prompted with no templates")
        )
        assert not onboarding.offer_import([], tmp_path / "p", "p-1")

    def test_silent_when_nothing_new_to_add(self, tty, monkeypatch, tmp_path):
        template = self._template(tmp_path)
        project = tmp_path / "p"
        project.mkdir()
        (project / "CLAUDE.md").write_text("x")  # identical already
        monkeypatch.setattr(
            onboarding, "_ask", lambda *a, **kw: pytest.fail("prompted with nothing to add")
        )
        assert not onboarding.offer_import([template], project, "p-1")

    def test_not_now_declines_without_remembering(self, tty, monkeypatch, tmp_path):
        answers(monkeypatch, "n")
        assert not onboarding.offer_import([self._template(tmp_path)], tmp_path / "p", "p-1")
        assert userconfig.declined_projects() == set()

    def test_never_is_remembered_for_that_project_only(self, tty, monkeypatch, tmp_path):
        template = self._template(tmp_path)
        answers(monkeypatch, "never")
        assert not onboarding.offer_import([template], tmp_path / "p", "p-1")
        assert userconfig.declined_projects() == {"p-1"}

        # Silent for p-1 from now on...
        monkeypatch.setattr(
            onboarding, "_ask", lambda *a, **kw: pytest.fail("asked a declined project")
        )
        assert not onboarding.offer_import([template], tmp_path / "p", "p-1")

    def test_other_projects_are_still_offered(self, tty, monkeypatch, tmp_path):
        template = self._template(tmp_path)
        userconfig.decline_project("p-1")
        answers(monkeypatch, "y")
        assert onboarding.offer_import([template], tmp_path / "other", "p-2")

    def test_invalid_answer_reprompts(self, tty, monkeypatch, tmp_path):
        queue = answers(monkeypatch, "maybe", "y")
        assert onboarding.offer_import([self._template(tmp_path)], tmp_path / "p", "p-1")
        assert queue == []  # both answers consumed
