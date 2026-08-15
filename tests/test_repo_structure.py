"""Enforces working-practice rules from claude-best-practices.md."""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

SKIP_DIR_NAMES = {".git", ".idea", "__pycache__", "node_modules"}


def _needs_claude_md(directory: Path) -> bool:
    rel = directory.relative_to(REPO_ROOT)
    parts = rel.parts
    if any(part.startswith(".") for part in parts):
        return False
    if any(part in SKIP_DIR_NAMES for part in parts):
        return False
    if any(part.endswith(".egg-info") for part in parts):
        return False
    if parts == ("src",):
        return False
    return True


def _directories_to_check() -> list[Path]:
    dirs = [REPO_ROOT]
    for path in sorted(REPO_ROOT.rglob("*")):
        if path.is_dir() and _needs_claude_md(path):
            dirs.append(path)
    return dirs


def test_every_tracked_directory_has_claude_md():
    missing = [
        str(d.relative_to(REPO_ROOT)) or "."
        for d in _directories_to_check()
        if not (d / "CLAUDE.md").exists()
    ]
    assert not missing, f"Directories missing CLAUDE.md: {missing}"


def test_roadmap_lists_every_phase_plan():
    roadmap = (REPO_ROOT / "ROADMAP.md").read_text()
    for plan in sorted((REPO_ROOT / "plans").glob("phase-*.md")):
        assert plan.name in roadmap, f"{plan.name} not referenced in ROADMAP.md"
