from pathlib import Path

import pytest

from practicum.labs import (
    LIVE_ENV_VAR,
    SOURCE_ENV_VAR,
    LabError,
    Source,
    discover_labs,
    get_lab,
    grade_lab,
    load_lab,
    resolve_source,
    stage_workspace,
    start_lab,
    starter_fails,
)


def test_load_lab_reads_fields(fake_repo: Path) -> None:
    lab = load_lab(fake_repo / "labs" / "m01-lab1")
    assert (lab.id, lab.title, lab.module) == ("m01-lab1", "Demo", "m01")
    assert lab.starter_dir.name == "starter"
    assert lab.tests_dir.name == "tests"
    assert lab.brief.name == "README.md"
    assert lab.work_dir(fake_repo) == fake_repo / "work" / "m01-lab1"
    assert lab.build_dir(fake_repo) == fake_repo / "build" / "labs" / "m01-lab1"


def test_load_lab_missing_file(tmp_path: Path) -> None:
    with pytest.raises(LabError, match="missing"):
        load_lab(tmp_path)


def test_load_lab_invalid_toml(tmp_path: Path) -> None:
    (tmp_path / "lab.toml").write_text("id = ", encoding="utf-8")
    with pytest.raises(LabError, match="invalid TOML"):
        load_lab(tmp_path)


def test_load_lab_missing_key(tmp_path: Path) -> None:
    (tmp_path / "lab.toml").write_text('id = "x"\n', encoding="utf-8")
    with pytest.raises(LabError, match="missing key 'title'"):
        load_lab(tmp_path)


def test_load_lab_id_must_match_directory(tmp_path: Path) -> None:
    lab_dir = tmp_path / "m09-lab1"
    lab_dir.mkdir()
    (lab_dir / "lab.toml").write_text('id = "m09-lab2"\ntitle = "T"\nmodule = "m09"\n', encoding="utf-8")
    with pytest.raises(LabError, match="must match the directory name"):
        load_lab(lab_dir)


def test_discover_sorts_by_id(fake_repo: Path) -> None:
    other = fake_repo / "labs" / "m00-lab1"
    other.mkdir()
    (other / "lab.toml").write_text('id = "m00-lab1"\ntitle = "Zero"\nmodule = "m00"\n', encoding="utf-8")
    assert [lab.id for lab in discover_labs(fake_repo)] == ["m00-lab1", "m01-lab1"]


def test_get_lab_unknown(fake_repo: Path) -> None:
    assert get_lab(fake_repo, "m01-lab1").title == "Demo"
    with pytest.raises(LabError, match="unknown lab 'm99-lab1'"):
        get_lab(fake_repo, "m99-lab1")


def test_start_copies_and_refuses_to_overwrite(fake_repo: Path) -> None:
    lab = get_lab(fake_repo, "m01-lab1")
    work = start_lab(fake_repo, lab)
    assert (work / "answer.txt").read_text(encoding="utf-8") == "TODO\n"
    (work / "answer.txt").write_text("42\n", encoding="utf-8")
    with pytest.raises(LabError, match="already exists"):
        start_lab(fake_repo, lab)
    start_lab(fake_repo, lab, force=True)
    assert (work / "answer.txt").read_text(encoding="utf-8") == "TODO\n"


def test_resolve_source_prefers_work(fake_repo: Path) -> None:
    lab = get_lab(fake_repo, "m01-lab1")
    assert resolve_source(fake_repo, lab, None) == (Source.STARTER, lab.starter_dir)
    start_lab(fake_repo, lab)
    assert resolve_source(fake_repo, lab, None) == (Source.WORK, lab.work_dir(fake_repo))
    assert resolve_source(fake_repo, lab, Source.STARTER)[0] is Source.STARTER


def test_stage_workspace_replaces_previous_copy(fake_repo: Path) -> None:
    lab = get_lab(fake_repo, "m01-lab1")
    first = stage_workspace(fake_repo, lab, Source.STARTER)
    (first / "stale.txt").write_text("x", encoding="utf-8")
    second = stage_workspace(fake_repo, lab, Source.STARTER)
    assert not (second / "stale.txt").exists()
    start_lab(fake_repo, lab)
    (lab.work_dir(fake_repo) / "mine.txt").write_text("y", encoding="utf-8")
    assert (stage_workspace(fake_repo, lab, Source.WORK) / "mine.txt").is_file()


def test_sample_labs_lay_starter_over_sample(fake_repo: Path) -> None:
    (fake_repo / "sample" / "pkg").mkdir(parents=True)
    (fake_repo / "sample" / "pkg" / "code.py").write_text("x = 1\n", encoding="utf-8")
    (fake_repo / "sample" / "answer.txt").write_text("sample\n", encoding="utf-8")
    lab_dir = fake_repo / "labs" / "m01-lab1"
    (lab_dir / "lab.toml").write_text(
        'id = "m01-lab1"\ntitle = "Demo"\nmodule = "m01"\nsample = true\n', encoding="utf-8"
    )
    lab = get_lab(fake_repo, "m01-lab1")
    assert lab.sample
    work = start_lab(fake_repo, lab)
    assert (work / "pkg" / "code.py").is_file()
    assert (work / "answer.txt").read_text(encoding="utf-8") == "TODO\n", "starter files win over sample files"
    assert (stage_workspace(fake_repo, lab, Source.STARTER) / "pkg" / "code.py").is_file()


def test_grade_runs_checks_against_staged_copy(fake_repo: Path) -> None:
    lab = get_lab(fake_repo, "m01-lab1")
    assert grade_lab(fake_repo, lab, quiet=True) != 0
    work = start_lab(fake_repo, lab)
    (work / "answer.txt").write_text("42\n", encoding="utf-8")
    assert grade_lab(fake_repo, lab, quiet=True) == 0
    assert (work / "answer.txt").read_text(encoding="utf-8") == "42\n"


def test_grade_sets_environment(fake_repo: Path) -> None:
    lab = get_lab(fake_repo, "m01-lab1")
    (lab.tests_dir / "test_env.py").write_text(
        "import os\n\n"
        f"def test_env():\n    assert os.environ['{SOURCE_ENV_VAR}'].endswith('m01-lab1')\n"
        f"    assert os.environ.get('{LIVE_ENV_VAR}') == '1'\n",
        encoding="utf-8",
    )
    assert grade_lab(fake_repo, lab, live=True, extra_args=["-k", "test_env"], quiet=True) == 0


def test_starter_fails(fake_repo: Path) -> None:
    lab = get_lab(fake_repo, "m01-lab1")
    assert starter_fails(fake_repo, lab)
    (lab.starter_dir / "answer.txt").write_text("42\n", encoding="utf-8")
    assert not starter_fails(fake_repo, lab)
