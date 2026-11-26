"""Discover, start, and grade the hands-on labs.

Each lab lives in ``labs/<id>/`` with a ``lab.toml``, a ``README.md`` brief, a ``starter/`` workspace that you copy
into ``work/<id>/`` and complete, and a ``tests/`` directory of checks. Labs with ``sample = true`` start from a copy of
the shared project in ``sample/`` with the starter's files laid over it. Labs ship without reference solutions: the
checks are the specification, and ``practicum check-labs`` proves each starter fails them so no check passes vacuously.
"""

import os
import shutil
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

SOURCE_ENV_VAR = "PRACTICUM_SRC"
LIVE_ENV_VAR = "PRACTICUM_LIVE"


class LabError(RuntimeError):
    """Raised for an unknown lab or an invalid lab definition."""


class Source(StrEnum):
    """Which copy of a lab's workspace a grading run checks."""

    WORK = "work"
    STARTER = "starter"


@dataclass(frozen=True, slots=True)
class Lab:
    """A hands-on lab defined by a ``lab.toml`` file.

    Attributes:
        id: Identifier such as ``m02-lab1``.
        title: Human-readable title.
        module: Module the lab belongs to, such as ``m02``.
        path: Directory holding the lab definition.
        sample: Whether the workspace starts from the shared project in ``sample/``.
    """

    id: str
    title: str
    module: str
    path: Path
    sample: bool = False

    @property
    def starter_dir(self) -> Path:
        """Directory containing the starter workspace."""
        return self.path / "starter"

    @property
    def tests_dir(self) -> Path:
        """Directory containing the checks."""
        return self.path / "tests"

    @property
    def brief(self) -> Path:
        """The lab's README brief."""
        return self.path / "README.md"

    def work_dir(self, root: Path) -> Path:
        """Return the learner's working copy location.

        Args:
            root: Repository root.

        Returns:
            The path ``work/<lab id>`` under ``root``.
        """
        return root / "work" / self.id

    def build_dir(self, root: Path) -> Path:
        """Return the scratch copy that grading runs against.

        Args:
            root: Repository root.

        Returns:
            The path ``build/labs/<lab id>`` under ``root``.
        """
        return root / "build" / "labs" / self.id


def load_lab(lab_dir: Path) -> Lab:
    """Load a lab definition from ``lab_dir/lab.toml``.

    Args:
        lab_dir: Directory containing ``lab.toml``.

    Returns:
        The parsed lab.

    Raises:
        LabError: If the file is missing or lacks required keys.
    """
    config_path = lab_dir / "lab.toml"
    try:
        data = tomllib.loads(config_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise LabError(f"missing {config_path}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise LabError(f"invalid TOML in {config_path}: {exc}") from exc
    try:
        lab = Lab(
            id=str(data["id"]),
            title=str(data["title"]),
            module=str(data["module"]),
            path=lab_dir,
            sample=bool(data.get("sample", False)),
        )
    except KeyError as exc:
        raise LabError(f"{config_path} is missing key {exc.args[0]!r}") from exc
    if lab.id != lab_dir.name:
        raise LabError(f"{config_path}: id {lab.id!r} must match the directory name {lab_dir.name!r}")
    return lab


def discover_labs(root: Path) -> list[Lab]:
    """Return every lab under ``root/labs`` sorted by id.

    Args:
        root: Repository root.

    Returns:
        Labs ordered by identifier.
    """
    return sorted((load_lab(p.parent) for p in (root / "labs").glob("*/lab.toml")), key=lambda lab: lab.id)


def get_lab(root: Path, lab_id: str) -> Lab:
    """Look up a lab by id.

    Args:
        root: Repository root.
        lab_id: Identifier such as ``m02-lab1``.

    Returns:
        The matching lab.

    Raises:
        LabError: If no lab matches.
    """
    for lab in discover_labs(root):
        if lab.id == lab_id:
            return lab
    raise LabError(f"unknown lab {lab_id!r}; run `pixi run labs` to list them")


def start_lab(root: Path, lab: Lab, *, force: bool = False) -> Path:
    """Copy a lab's starter workspace into the learner's ``work/`` directory.

    Args:
        root: Repository root.
        lab: Lab to start.
        force: Replace an existing working copy.

    Returns:
        The working copy directory.

    Raises:
        LabError: If a working copy exists and ``force`` is false.
    """
    destination = lab.work_dir(root)
    if destination.exists():
        if not force:
            raise LabError(f"{destination} already exists; pass --force to start over (your work will be replaced)")
        shutil.rmtree(destination)
    _copy_starter(root, lab, destination)
    return destination


def _copy_starter(root: Path, lab: Lab, destination: Path) -> None:
    ignore = shutil.ignore_patterns("__pycache__", ".pytest_cache")
    if lab.sample:
        shutil.copytree(root / "sample", destination, ignore=ignore)
    shutil.copytree(lab.starter_dir, destination, ignore=ignore, dirs_exist_ok=True)


def resolve_source(root: Path, lab: Lab, source: Source | None) -> tuple[Source, Path]:
    """Pick which workspace a grading run checks.

    With no explicit choice the learner's working copy is preferred, falling back to the starter.

    Args:
        root: Repository root.
        lab: Lab being graded.
        source: Explicit source, or ``None`` to choose automatically.

    Returns:
        The chosen source and its directory.
    """
    if source is None:
        source = Source.WORK if lab.work_dir(root).is_dir() else Source.STARTER
    return source, lab.work_dir(root) if source is Source.WORK else lab.starter_dir


def stage_workspace(root: Path, lab: Lab, source: Source) -> Path:
    """Copy the workspace being graded to ``build/labs/<id>`` so checks never modify your work.

    Args:
        root: Repository root.
        lab: Lab being graded.
        source: Which workspace to copy. The starter is laid over the sample project, as ``start`` would.

    Returns:
        The staged copy.
    """
    staged = lab.build_dir(root)
    if staged.exists():
        shutil.rmtree(staged)
    if source is Source.STARTER:
        _copy_starter(root, lab, staged)
    else:
        shutil.copytree(lab.work_dir(root), staged, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"))
    return staged


def grade_lab(
    root: Path,
    lab: Lab,
    *,
    source: Source | None = None,
    live: bool = False,
    extra_args: list[str] | None = None,
    quiet: bool = False,
) -> int:
    """Run a lab's checks against a staged copy of the chosen workspace.

    Args:
        root: Repository root.
        lab: Lab to grade.
        source: Which workspace to check; see :func:`resolve_source`.
        live: Also run checks against your local kind cluster (they skip without one).
        extra_args: Additional arguments forwarded to pytest.
        quiet: Suppress pytest output (used by ``check-labs``).

    Returns:
        The pytest exit code (0 means every check passed).
    """
    chosen, _ = resolve_source(root, lab, source)
    staged = stage_workspace(root, lab, chosen)
    env = {**os.environ, SOURCE_ENV_VAR: str(staged)}
    if live:
        env[LIVE_ENV_VAR] = "1"
    command = [sys.executable, "-m", "pytest", str(lab.tests_dir), "-p", "no:cacheprovider", *(extra_args or [])]
    if quiet:
        command.append("-q")
    completed = subprocess.run(command, cwd=root, env=env, check=False, capture_output=quiet)
    return completed.returncode


def starter_fails(root: Path, lab: Lab) -> bool:
    """Tell whether a lab's untouched starter fails its checks, as it must.

    Args:
        root: Repository root.
        lab: Lab to check.

    Returns:
        ``True`` when at least one check fails against the starter.
    """
    return grade_lab(root, lab, source=Source.STARTER, quiet=True) != 0
