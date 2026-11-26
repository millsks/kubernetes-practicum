"""Whole-repository quality gates: the site is valid, every exercise is solvable, every lab starter is unsolved."""

from pathlib import Path

import pytest

from practicum.exercises import check_page_exercises
from practicum.labs import discover_labs, starter_fails
from practicum.site import check_site
from tests.conftest import REPO_ROOT

pytestmark = pytest.mark.integration

PAGES = sorted((REPO_ROOT / "docs").rglob("*.html"))
LABS = discover_labs(REPO_ROOT)


def test_site_has_no_issues() -> None:
    issues = check_site(REPO_ROOT / "docs")
    assert not issues, "\n".join(f"{i.path}: {i.message}" for i in issues)


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.relative_to(REPO_ROOT / "docs").as_posix())
def test_exercise_solutions_pass(page: Path) -> None:
    failures = [r for r in check_page_exercises(page) if not r.ok]
    assert not failures, "\n".join(f"{r.id}: {r.detail}" for r in failures)


@pytest.mark.parametrize("lab", LABS, ids=lambda lab: lab.id)
def test_lab_starter_is_unsolved(lab: object) -> None:
    assert starter_fails(REPO_ROOT, lab)  # type: ignore[arg-type]


@pytest.mark.parametrize("lab", LABS, ids=lambda lab: lab.id)
def test_lab_has_brief_and_module_page(lab: object) -> None:
    brief = lab.brief.read_text(encoding="utf-8")  # type: ignore[attr-defined]
    assert brief.startswith("# "), "a lab brief starts with a level-1 heading"
    pages = "".join(p.read_text(encoding="utf-8") for p in (REPO_ROOT / "docs" / "modules").glob("*.html"))
    assert lab.id in pages, f"no module page mentions {lab.id}"  # type: ignore[attr-defined]


def test_library_styles_load_before_course_styles() -> None:
    # Regression: CodeMirror's stylesheet was appended after course.css and won every tie,
    # leaving editors white in dark mode and fixed at 300px tall.
    course_js = (REPO_ROOT / "docs" / "assets" / "js" / "course.js").read_text(encoding="utf-8")
    load_css = course_js[course_js.index("function loadCss") : course_js.index("const icon")]
    assert "first.before(link)" in load_css
    assert "head.append(h(" not in load_css
