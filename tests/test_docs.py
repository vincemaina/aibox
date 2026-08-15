"""Keeps the published documentation honest.

The CLI is the contract users see, so every command and flag argparse accepts has
to appear in the reference page. Adding a flag without documenting it fails here
rather than shipping an undocumented feature.
"""

import html
import re
from pathlib import Path

import pytest

from aibox.cli import build_parser

REPO_ROOT = Path(__file__).resolve().parent.parent
DOCS = REPO_ROOT / "docs"
REFERENCE = DOCS / "documentation.html"
LANDING = DOCS / "index.html"

SITE_URL = "https://vincemaina.github.io/aibox/"


def _reference_text() -> str:
    return html.unescape(REFERENCE.read_text())


def _subparsers():
    parser = build_parser()
    for action in parser._actions:
        if isinstance(getattr(action, "choices", None), dict):
            return action.choices
    raise AssertionError("no subcommands found on the parser")


def _flags(parser) -> list[str]:
    return [
        option
        for action in parser._actions
        for option in action.option_strings
        if option not in ("-h", "--help")
    ]


@pytest.mark.parametrize("command", sorted(_subparsers()))
def test_every_command_is_documented(command):
    assert f"aibox {command}" in _reference_text(), (
        f"'aibox {command}' is not mentioned in docs/documentation.html"
    )


@pytest.mark.parametrize(
    "command,flag",
    sorted(
        (name, flag)
        for name, sub in _subparsers().items()
        for flag in _flags(sub)
    ),
)
def test_every_subcommand_flag_is_documented(command, flag):
    assert flag in _reference_text(), (
        f"'{flag}' (on 'aibox {command}') is not documented in docs/documentation.html"
    )


def test_global_flags_are_documented():
    for flag in _flags(build_parser()):
        assert flag in _reference_text(), f"global flag '{flag}' is undocumented"


class TestSeo:
    @pytest.mark.parametrize("page", [LANDING, REFERENCE])
    def test_has_unique_title_and_description(self, page):
        source = page.read_text()
        title = re.search(r"<title>(.+?)</title>", source, re.S)
        description = re.search(r'name="description" content="(.+?)"', source, re.S)
        assert title and 10 < len(title.group(1)) <= 70, "missing or overlong <title>"
        assert description and 50 < len(description.group(1)) <= 200, "bad meta description"

    def test_titles_differ_between_pages(self):
        pattern = r"<title>(.+?)</title>"
        assert re.search(pattern, LANDING.read_text(), re.S).group(1) != re.search(
            pattern, REFERENCE.read_text(), re.S
        ).group(1)

    @pytest.mark.parametrize("page", [LANDING, REFERENCE])
    def test_has_canonical_and_social_tags(self, page):
        source = page.read_text()
        for needle in ('rel="canonical"', 'property="og:title"', 'name="twitter:card"'):
            assert needle in source, f"{page.name} is missing {needle}"

    @pytest.mark.parametrize("page", [LANDING, REFERENCE])
    def test_has_exactly_one_h1_or_none(self, page):
        # The reference page leads with h2 under the site wordmark; the landing
        # page must have exactly one h1. Neither may have several.
        assert len(re.findall(r"<h1[ >]", page.read_text())) <= 1

    def test_referenced_assets_exist(self):
        for page in (LANDING, REFERENCE):
            for asset in re.findall(r'(?:href|src)="([^"#:]+\.(?:css|png|svg|js))"', page.read_text()):
                assert (DOCS / asset).exists(), f"{page.name} references missing {asset}"

    def test_og_image_is_absolute(self):
        # Relative og:image URLs are ignored by most scrapers.
        for page in (LANDING, REFERENCE):
            match = re.search(r'property="og:image" content="(.+?)"', page.read_text())
            assert match and match.group(1).startswith("https://"), page.name

    def test_sitemap_lists_every_page(self):
        sitemap = (DOCS / "sitemap.xml").read_text()
        for page in DOCS.glob("*.html"):
            url = SITE_URL if page.name == "index.html" else SITE_URL + page.name
            assert url in sitemap, f"{page.name} missing from sitemap.xml"

    def test_jekyll_is_disabled(self):
        assert (DOCS / ".nojekyll").exists()
