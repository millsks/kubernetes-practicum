"""Checks for m02-lab2: triage.py, a standard-library Pod diagnosis tool."""

import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

FIXTURE = Path(__file__).parent / "fixtures" / "pods.json"
EXPECTED = [
    ("apps/too-big", "Unschedulable", "kubectl describe pod -n apps too-big"),
    ("apps/bad-tag", "ImagePullBackOff", "kubectl describe pod -n apps bad-tag"),
    ("default/no-secret", "CreateContainerConfigError", "kubectl describe pod -n default no-secret"),
    ("apps/leaky", "OOMKilled", "kubectl logs -n apps leaky -c app --previous"),
    ("apps/crashy", "CrashLoopBackOff", "kubectl logs -n apps crashy -c app --previous"),
    ("apps/init-stuck", "ErrImagePull", "kubectl describe pod -n apps init-stuck"),
    ("batch/exited", "Error", "kubectl logs -n batch exited -c task --previous"),
    ("apps/warming", "NotReady", "kubectl describe pod -n apps warming"),
]


@pytest.fixture
def script(workspace: Path) -> Path:
    path = workspace / "triage.py"
    assert path.is_file(), "triage.py is missing"
    return path


@pytest.fixture
def mod(script: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location("lab_triage", script)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def pods() -> list[dict]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))["items"]


def run(script: Path, *args: str, stdin: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(script), *args], input=stdin, capture_output=True, text=True, timeout=60, check=False
    )


def test_standard_library_only(script: Path) -> None:
    source = script.read_text(encoding="utf-8")
    assert not re.search(r"^\s*(import|from)\s+(kubelab|yaml)\b", source, re.M), "use only the standard library"


def test_diagnose(mod: ModuleType) -> None:
    by_name = {p["metadata"]["name"]: p for p in pods()}
    assert mod.diagnose(by_name["web-ok"]) is None
    assert mod.diagnose(by_name["job-done"]) is None, "completed Pods are healthy"
    assert mod.diagnose(by_name["leaky"]) == ("OOMKilled", "app"), (
        "OOMKilled is the root cause of that CrashLoopBackOff"
    )
    assert mod.diagnose(by_name["init-stuck"]) == ("ErrImagePull", "migrate"), "check init containers first"
    assert mod.diagnose(by_name["too-big"]) == ("Unschedulable", "")
    assert mod.diagnose(by_name["warming"]) == ("NotReady", "app")


def test_output_from_file(script: Path) -> None:
    done = run(script, str(FIXTURE))
    assert done.returncode == 1, "exit 1 when any Pod is unhealthy"
    lines = [tuple(line.split("\t")) for line in done.stdout.strip().splitlines()]
    assert lines == EXPECTED


def test_output_from_stdin(script: Path) -> None:
    done = run(script, stdin=FIXTURE.read_text(encoding="utf-8"))
    assert [tuple(line.split("\t")) for line in done.stdout.strip().splitlines()] == EXPECTED


def test_all_healthy(script: Path) -> None:
    healthy = {"items": [p for p in pods() if p["metadata"]["name"] in ("web-ok", "job-done")]}
    done = run(script, stdin=json.dumps(healthy))
    assert done.returncode == 0 and done.stdout.strip() == ""


def test_bad_input(script: Path) -> None:
    for text in ("not json", '{"kind": "List"}'):
        done = run(script, stdin=text)
        assert done.returncode == 2, f"exit 2 for bad input {text!r}"
        assert done.stderr.strip(), "explain the problem on standard error"
