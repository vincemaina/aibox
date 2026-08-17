import subprocess
from pathlib import Path

import pytest

from aibox import templates
from aibox.config import ProjectConfig
from aibox.templates import Action, TemplateError
from aibox.userconfig import UserConfig


REMOTE = "https://example.com/t.git"


@pytest.fixture
def cache(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    return tmp_path / "cache" / "aibox"


def fake_clone(monkeypatch):
    """Stand in for `git clone`, populating the staging dir it's given."""
    calls = {"n": 0}

    def run(args, *a, **kw):
        calls["n"] += 1
        (Path(args[-1]) / "workspace").mkdir(parents=True)
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(templates.subprocess, "run", run)
    return calls


def fail_clone(monkeypatch, stderr="could not resolve host"):
    monkeypatch.setattr(
        templates.subprocess,
        "run",
        lambda args, *a, **kw: subprocess.CompletedProcess(
            args=args, returncode=128, stdout="", stderr=stderr
        ),
    )


def make_template(root, workspace=None, home=None) -> "object":
    """Build a template directory from {relative path: content} mappings."""
    for name, files in (("workspace", workspace), ("home", home)):
        for relative, content in (files or {}).items():
            path = root / name / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
    return root


class TestRefsFor:
    def test_user_templates_used_when_project_silent(self):
        refs = templates.refs_for(UserConfig(templates=["a"]), ProjectConfig())
        assert refs == ["a"]

    def test_project_overrides_user(self):
        refs = templates.refs_for(
            UserConfig(templates=["a"]), ProjectConfig(templates=["b"])
        )
        assert refs == ["b"]

    def test_empty_project_list_is_an_opt_out(self):
        # [] is "none please", distinct from the key being absent.
        refs = templates.refs_for(UserConfig(templates=["a"]), ProjectConfig(templates=[]))
        assert refs == []


class TestResolve:
    def test_local_path_used_in_place(self, tmp_path):
        template = tmp_path / "t"
        template.mkdir()
        assert templates.resolve(str(template)) == template.resolve()

    def test_missing_local_path_raises(self, tmp_path):
        with pytest.raises(TemplateError, match="does not exist"):
            templates.resolve(str(tmp_path / "nope"))

    def test_expands_user_home(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        (tmp_path / "t").mkdir()
        assert templates.resolve("~/t") == (tmp_path / "t").resolve()

    def test_clone_failure_raises_and_cleans_up(self, cache, monkeypatch):
        import subprocess

        def fake_run(*a, **kw):
            return subprocess.CompletedProcess(args=a, returncode=1, stdout="", stderr="boom")

        monkeypatch.setattr(templates.subprocess, "run", fake_run)
        with pytest.raises(TemplateError, match="Failed to clone"):
            templates.resolve("https://example.com/t.git")
        # A half-cloned directory must not be left behind to be reused as valid.
        assert list((cache / "templates").glob("*")) == []

    def test_fresh_cache_is_not_refetched(self, cache, monkeypatch):
        calls = fake_clone(monkeypatch)
        templates.resolve(REMOTE)
        templates.resolve(REMOTE)
        assert calls["n"] == 1

    def test_stale_cache_is_refetched(self, cache, monkeypatch):
        # Without a TTL, editing your template repo would never reach new boxes.
        calls = fake_clone(monkeypatch)
        templates.resolve(REMOTE)
        templates.resolve(REMOTE, ttl=0)
        assert calls["n"] == 2

    def test_refresh_forces_a_refetch(self, cache, monkeypatch):
        calls = fake_clone(monkeypatch)
        templates.resolve(REMOTE)
        templates.resolve(REMOTE, refresh=True)
        assert calls["n"] == 2

    def test_local_paths_are_always_current(self, tmp_path, monkeypatch):
        # Read in place, never cached, so there is nothing to go stale.
        monkeypatch.setattr(
            templates.subprocess, "run", lambda *a, **kw: pytest.fail("cloned a local path")
        )
        local = tmp_path / "t"
        local.mkdir()
        assert templates.resolve(str(local), ttl=0) == local.resolve()

    def test_failed_refetch_falls_back_to_cache(self, cache, monkeypatch, capsys):
        # Being offline must not stop a box from starting.
        fake_clone(monkeypatch)
        first = templates.resolve(REMOTE)
        (first / "workspace" / "marker").write_text("original")

        fail_clone(monkeypatch)
        again = templates.resolve(REMOTE, refresh=True)
        assert again == first
        assert (again / "workspace" / "marker").read_text() == "original"
        assert "Using the cached copy" in capsys.readouterr().err

    def test_failed_refetch_leaves_cache_intact(self, cache, monkeypatch):
        fake_clone(monkeypatch)
        cached = templates.resolve(REMOTE)
        (cached / "workspace" / "keep").write_text("x")

        fail_clone(monkeypatch)
        templates.resolve(REMOTE, refresh=True)
        assert (cached / "workspace" / "keep").is_file()
        assert not list(cached.parent.glob("*.incoming"))

    def test_failed_first_clone_still_raises(self, cache, monkeypatch):
        fail_clone(monkeypatch)
        with pytest.raises(TemplateError, match="Failed to clone"):
            templates.resolve(REMOTE)

    def test_cached_clone_is_reused(self, cache, monkeypatch):
        calls = {"n": 0}

        def fake_run(*a, **kw):
            import subprocess

            calls["n"] += 1
            dest = a[0][-1]
            (templates.Path(dest) / "workspace").mkdir(parents=True)
            return subprocess.CompletedProcess(args=a, returncode=0, stdout="", stderr="")

        monkeypatch.setattr(templates.subprocess, "run", fake_run)
        first = templates.resolve("https://example.com/t.git")
        second = templates.resolve("https://example.com/t.git")
        assert first == second
        assert calls["n"] == 1


class TestPlanMerge:
    def test_all_new_files_are_creates(self, tmp_path):
        template = make_template(tmp_path / "t", workspace={"CLAUDE.md": "hi"})
        plan = templates.plan_merge(template, tmp_path / "proj")
        assert [e.action for e in plan.entries] == [Action.CREATE]
        assert plan.entries[0].relative == "CLAUDE.md"

    def test_identical_file_is_unchanged_not_conflict(self, tmp_path):
        template = make_template(tmp_path / "t", workspace={"CLAUDE.md": "same"})
        project = tmp_path / "proj"
        project.mkdir()
        (project / "CLAUDE.md").write_text("same")
        plan = templates.plan_merge(template, project)
        assert plan.of(Action.UNCHANGED) and not plan.of(Action.CONFLICT)

    def test_differing_file_is_conflict(self, tmp_path):
        template = make_template(tmp_path / "t", workspace={"CLAUDE.md": "theirs"})
        project = tmp_path / "proj"
        project.mkdir()
        (project / "CLAUDE.md").write_text("mine")
        plan = templates.plan_merge(template, project)
        assert len(plan.of(Action.CONFLICT)) == 1

    def test_nested_directories_merge(self, tmp_path):
        template = make_template(
            tmp_path / "t", workspace={".claude/skills/review/SKILL.md": "x"}
        )
        plan = templates.plan_merge(template, tmp_path / "proj")
        assert plan.entries[0].relative == ".claude/skills/review/SKILL.md"

    def test_template_git_dir_is_never_copied(self, tmp_path):
        template = tmp_path / "t"
        (template / "workspace" / ".git").mkdir(parents=True)
        (template / "workspace" / ".git" / "config").write_text("[core]")
        (template / "workspace" / "ok.md").write_text("ok")
        plan = templates.plan_merge(template, tmp_path / "proj")
        assert [e.relative for e in plan.entries] == ["ok.md"]

    def test_template_without_workspace_yields_empty_plan(self, tmp_path):
        template = make_template(tmp_path / "t", home={"a": "b"})
        assert templates.plan_merge(template, tmp_path / "proj").entries == []


class TestKeepBothPath:
    def test_inserts_aibox_before_extension(self, tmp_path):
        target = tmp_path / "CLAUDE.md"
        target.write_text("x")
        assert templates.keep_both_path(target).name == "CLAUDE.aibox.md"

    def test_numbers_upward_when_taken(self, tmp_path):
        (tmp_path / "CLAUDE.md").write_text("x")
        (tmp_path / "CLAUDE.aibox.md").write_text("x")
        assert templates.keep_both_path(tmp_path / "CLAUDE.md").name == "CLAUDE.aibox.1.md"


class TestStageHomeSeed:
    def test_briefing_is_seeded_even_without_templates(self, cache):
        staged = templates.stage_home_seed([], "proj-1")
        briefing = (staged / ".claude" / "CLAUDE.md").read_text()
        assert "running inside an aibox container" in briefing

    def test_workspace_only_template_still_gets_briefing(self, cache, tmp_path):
        template = make_template(tmp_path / "t", workspace={"a": "b"})
        staged = templates.stage_home_seed([template], "proj-1")
        assert (staged / ".claude" / "CLAUDE.md").is_file()

    def test_template_can_override_the_briefing(self, cache, tmp_path):
        template = make_template(tmp_path / "t", home={".claude/CLAUDE.md": "mine"})
        staged = templates.stage_home_seed([template], "proj-1")
        assert (staged / ".claude" / "CLAUDE.md").read_text() == "mine"

    def test_briefing_can_be_disabled(self, cache):
        staged = templates.stage_home_seed([], "proj-1", briefing=False)
        assert not (staged / ".claude").exists()

    def test_stages_home_content(self, cache, tmp_path):
        template = make_template(tmp_path / "t", home={".claude/skills/s/SKILL.md": "x"})
        staged = templates.stage_home_seed([template], "proj-1")
        assert (staged / ".claude" / "skills" / "s" / "SKILL.md").read_text() == "x"

    def test_later_template_wins(self, cache, tmp_path):
        first = make_template(tmp_path / "a", home={"f.md": "first"})
        second = make_template(tmp_path / "b", home={"f.md": "second"})
        staged = templates.stage_home_seed([first, second], "proj-1")
        assert (staged / "f.md").read_text() == "second"

    def test_restaging_clears_removed_files(self, cache, tmp_path):
        first = make_template(tmp_path / "a", home={"gone.md": "x"})
        templates.stage_home_seed([first], "proj-1")
        second = make_template(tmp_path / "b", home={"kept.md": "y"})
        staged = templates.stage_home_seed([second], "proj-1")
        assert not (staged / "gone.md").exists()
        assert (staged / "kept.md").exists()

    def test_projects_get_separate_seeds(self, cache, tmp_path):
        template = make_template(tmp_path / "t", home={"f.md": "x"})
        a = templates.stage_home_seed([template], "proj-a")
        b = templates.stage_home_seed([template], "proj-b")
        assert a != b
