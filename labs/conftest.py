"""Shared fixtures for lab checks.

``pixi run grade <lab>`` copies your workspace to ``build/labs/<lab>/`` and sets ``PRACTICUM_SRC`` to that copy, so
checks can read and run your files without ever changing ``work/``. ``pixi run grade-live <lab>`` also sets
``PRACTICUM_LIVE=1``, which enables checks that apply your work to the ``primer`` kind cluster.
"""

import os
import shutil
import subprocess
import uuid
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

_source = os.environ.get("PRACTICUM_SRC")
if _source is None:
    raise RuntimeError("Run lab checks with `pixi run grade <lab>` so PRACTICUM_SRC is set.")

LIVE = os.environ.get("PRACTICUM_LIVE") == "1"
CONTEXT = os.environ.get("PRACTICUM_CONTEXT", "kind-primer")

Kube = Callable[..., subprocess.CompletedProcess[str]]


@pytest.fixture
def workspace() -> Path:
    """The staged copy of the workspace being graded."""
    return Path(_source).resolve()


@pytest.fixture
def kube() -> Kube:
    """Run ``kubectl --context kind-primer ...``; skips unless grading with ``--live`` and the cluster answers.

    Call it like ``kube("get", "nodes", "-o", "json")``. Pass ``check=False`` to inspect a failure yourself and
    ``stdin="..."`` to pipe text in. Output is captured as text.
    """
    if not LIVE:
        pytest.skip("live check: run `pixi run grade-live <lab>` against your primer cluster")
    kubectl = shutil.which("kubectl")
    if kubectl is None:
        pytest.skip("live check: kubectl is not on PATH (run through Pixi, or brew install kubectl)")
    assert kubectl is not None

    def run(
        *args: str, check: bool = True, stdin: str | None = None, timeout: int = 300
    ) -> subprocess.CompletedProcess[str]:
        done = subprocess.run(
            [kubectl, "--context", CONTEXT, *args],
            input=stdin,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        if check and done.returncode != 0:
            pytest.fail(f"kubectl {' '.join(args)} failed:\n{done.stderr[-2000:]}")
        return done

    if run("get", "--raw", "/readyz", check=False, timeout=20).returncode != 0:
        pytest.skip(f"live check: the {CONTEXT} context does not answer; is Colima running and the cluster created?")
    return run


@pytest.fixture
def namespace(kube: Kube) -> Iterator[str]:
    """A fresh namespace on the primer cluster, deleted after the check."""
    name = f"lab-{uuid.uuid4().hex[:8]}"
    kube("create", "namespace", name)
    try:
        yield name
    finally:
        kube("delete", "namespace", name, "--wait=false", check=False)
