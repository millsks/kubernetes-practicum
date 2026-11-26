"""Checks for m01-lab1: active, reconcile, and converge."""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest


@pytest.fixture
def rc(workspace: Path) -> ModuleType:
    path = workspace / "reconciler.py"
    assert path.is_file(), "reconciler.py is missing"
    spec = importlib.util.spec_from_file_location("lab_reconciler", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["lab_reconciler"] = module
    spec.loader.exec_module(module)
    return module


def pod(
    name: str,
    phase: str = "Running",
    ready: bool = True,
    node: str | None = "primer-worker",
    deleting: bool = False,
    created: int = 0,
) -> dict:
    return {"name": name, "phase": phase, "ready": ready, "node": node, "deleting": deleting, "created": created}


def test_active(rc: ModuleType) -> None:
    pods = [
        pod("a"),
        pod("b", phase="Pending", ready=False, node=None),
        pod("c", deleting=True),
        pod("d", phase="Failed"),
        pod("e", phase="Succeeded"),
    ]
    assert [p["name"] for p in rc.active(pods)] == ["a", "b"]


def test_noop(rc: ModuleType) -> None:
    pods = [pod("web-1"), pod("web-2")]
    assert rc.reconcile(2, pods) == {"create": [], "delete": []}


def test_negative(rc: ModuleType) -> None:
    with pytest.raises(ValueError):
        rc.reconcile(-1, [])


def test_create_from_nothing(rc: ModuleType) -> None:
    assert rc.reconcile(3, []) == {"create": ["web-1", "web-2", "web-3"], "delete": []}


def test_create_fills_gaps_and_avoids_terminating_names(rc: ModuleType) -> None:
    pods = [pod("web-1"), pod("web-2", deleting=True), pod("web-4")]
    result = rc.reconcile(4, pods)
    assert result == {"create": ["web-3", "web-5"], "delete": []}, (
        "web-2 still exists while terminating: don't reuse it"
    )


def test_prefix(rc: ModuleType) -> None:
    assert rc.reconcile(1, [], prefix="api")["create"] == ["api-1"]


def test_scale_down_prefers_unscheduled_then_unready_then_newest(rc: ModuleType) -> None:
    pods = [
        pod("web-1", created=1),
        pod("web-2", created=5),
        pod("web-3", created=3, ready=False),
        pod("web-4", created=2, phase="Pending", ready=False, node=None),
        pod("web-5", created=4),
    ]
    assert rc.reconcile(3, pods)["delete"] == ["web-3", "web-4"]
    assert rc.reconcile(2, pods)["delete"] == ["web-2", "web-3", "web-4"]


def test_tie_break_by_name(rc: ModuleType) -> None:
    pods = [pod("web-b", created=7), pod("web-a", created=7), pod("web-c", created=1)]
    assert rc.reconcile(2, pods)["delete"] == ["web-a"]


def test_never_deletes_terminating(rc: ModuleType) -> None:
    pods = [pod("web-1"), pod("web-2", deleting=True, created=9), pod("web-3", created=2)]
    result = rc.reconcile(1, pods)
    assert "web-2" not in result["delete"], "web-2 is already terminating"
    assert result["delete"] == ["web-3"]


def test_failed_pods_are_cleaned_up_and_replaced(rc: ModuleType) -> None:
    pods = [pod("web-1"), pod("web-2", phase="Failed"), pod("web-3", phase="Failed", deleting=True)]
    assert rc.reconcile(2, pods) == {"create": ["web-4"], "delete": ["web-2"]}


def test_converge_from_empty(rc: ModuleType) -> None:
    final, rounds = rc.converge(3, [])
    assert rounds == 1
    assert len(final) == 3 and all(p["phase"] == "Running" and p["ready"] for p in final)
    assert len({p["name"] for p in final}) == 3, "names must be unique"


def test_converge_is_idempotent(rc: ModuleType) -> None:
    final, _ = rc.converge(4, [pod("web-1"), pod("web-9", phase="Failed")])
    again, rounds = rc.converge(4, final)
    assert rounds == 0, "a converged state needs no further action"
    assert again == final


def test_converge_scale_down(rc: ModuleType) -> None:
    pods = [pod(f"web-{i}", created=i) for i in range(1, 6)]
    final, rounds = rc.converge(2, pods)
    assert rounds == 1
    assert sorted(p["name"] for p in final) == ["web-1", "web-2"], "the newest Pods go first"


def test_converge_gives_up(rc: ModuleType, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(rc, "settle", lambda pods: [])
    with pytest.raises(RuntimeError):
        rc.converge(2, [], max_rounds=3)
