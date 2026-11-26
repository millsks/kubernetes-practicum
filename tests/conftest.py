"""Shared fixtures for the practicum test suite."""

import json
import textwrap
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


def write_manifest(
    site: Path, parts: list[dict[str, object]], reference: list[dict[str, object]] | None = None
) -> None:
    js = site / "assets" / "js"
    js.mkdir(parents=True, exist_ok=True)
    payload = json.dumps({"title": "T", "parts": parts, "reference": reference or []})
    (js / "curriculum.js").write_text(f"window.CURRICULUM = {payload};\n", encoding="utf-8")


def page(body: str, *, title: str = "Page") -> str:
    return f"<!doctype html><html><head><title>{title}</title></head><body>{textwrap.dedent(body)}</body></html>"


@pytest.fixture
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture
def fake_repo(tmp_path: Path) -> Path:
    """A minimal practicum repository with one lab and a tiny site."""
    (tmp_path / "pixi.toml").write_text("[workspace]\nname = 'x'\n", encoding="utf-8")
    lab = tmp_path / "labs" / "m01-lab1"
    (lab / "starter").mkdir(parents=True)
    (lab / "tests").mkdir()
    (lab / "lab.toml").write_text('id = "m01-lab1"\ntitle = "Demo"\nmodule = "m01"\n', encoding="utf-8")
    (lab / "README.md").write_text("# Demo\n", encoding="utf-8")
    (lab / "starter" / "answer.txt").write_text("TODO\n", encoding="utf-8")
    (lab / "tests" / "test_demo.py").write_text(
        "import os\nfrom pathlib import Path\n\n"
        "def test_answer():\n    assert (Path(os.environ['PRACTICUM_SRC']) / 'answer.txt').read_text().strip() == '42'\n",
        encoding="utf-8",
    )
    site = tmp_path / "docs"
    write_manifest(site, [{"id": "part1", "modules": [{"id": "m01", "href": "modules/m01.html"}], "projects": []}])
    (site / "modules").mkdir()
    (site / "modules" / "m01.html").write_text(page("<main><h1>M01</h1></main>"), encoding="utf-8")
    return tmp_path
