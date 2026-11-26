"""Checks for m02-lab1: a production-shaped podinfo Pod."""

import json
from pathlib import Path
from typing import Any

import kubelab


def load(workspace: Path) -> dict[str, Any]:
    path = workspace / "pod.yaml"
    assert path.is_file(), "pod.yaml is missing"
    docs = kubelab.load_manifests(path.read_text(encoding="utf-8"))
    assert len(docs) == 1, "pod.yaml should hold exactly one object"
    return docs[0]


def container(pod: dict[str, Any]) -> dict[str, Any]:
    containers = kubelab.dig(pod, "spec.containers", [])
    assert len(containers) == 1, "use exactly one container"
    return containers[0]


def test_identity(workspace: Path) -> None:
    pod = load(workspace)
    assert pod.get("kind") == "Pod" and kubelab.dig(pod, "metadata.name") == "podinfo"
    assert kubelab.dig(pod, "metadata.labels", {}).get("app.kubernetes.io/name") == "podinfo", (
        "add the label app.kubernetes.io/name: podinfo"
    )


def test_valid(workspace: Path) -> None:
    problems = kubelab.check_object(load(workspace))
    assert problems == [], "; ".join(problems)


def test_only_bare_pod_warning(workspace: Path) -> None:
    left = [w for w in kubelab.warnings(load(workspace)) if not w.startswith("bare Pod")]
    assert left == [], "fix these: " + "; ".join(left)


def test_container_and_port(workspace: Path) -> None:
    c = container(load(workspace))
    assert c.get("name") == "app"
    assert c.get("image") == "ghcr.io/stefanprodan/podinfo:6.7.1"
    assert {"containerPort": 9898, "name": "http"} in [
        {"containerPort": p.get("containerPort"), "name": p.get("name")} for p in c.get("ports", [])
    ], "expose containerPort 9898 named http"


def test_probes(workspace: Path) -> None:
    c = container(load(workspace))
    expected = {"startupProbe": "/healthz", "livenessProbe": "/healthz", "readinessProbe": "/readyz"}
    for probe, path in expected.items():
        http = kubelab.dig(c, f"{probe}.httpGet")
        assert isinstance(http, dict), f"{probe} should use httpGet"
        assert http.get("path") == path, f"{probe} should check {path}"
        assert http.get("port") == "http", f"{probe} should use the named port http"
    startup = c["startupProbe"]
    budget = startup.get("failureThreshold", 3) * startup.get("periodSeconds", 10)
    assert budget >= 30, f"the startup probe allows only {budget}s; allow at least 30"


def test_resources(workspace: Path) -> None:
    pod = load(workspace)
    c = container(pod)
    assert kubelab.qos_class(pod["spec"]) == "Burstable", "aim for the Burstable QoS class"
    requests = kubelab.dig(c, "resources.requests", {})
    limits = kubelab.dig(c, "resources.limits", {})
    assert kubelab.parse_cpu(requests["cpu"]) <= 0.1, "keep the CPU request at or below 100m"
    assert kubelab.parse_memory(requests["memory"]) >= 32 * 2**20, "request at least 32Mi of memory"
    assert kubelab.parse_memory(requests["memory"]) <= kubelab.parse_memory(limits["memory"]) <= 256 * 2**20, (
        "memory limit: at least the request, at most 256Mi"
    )
    assert "cpu" not in limits, "leave out the CPU limit (it causes throttling)"


def test_security(workspace: Path) -> None:
    pod = load(workspace)
    user = kubelab.dig(pod, "spec.securityContext.runAsUser")
    assert isinstance(user, int) and not isinstance(user, bool) and user > 0, (
        "set a numeric, non-zero runAsUser at Pod level"
    )
    assert kubelab.dig(container(pod), "securityContext.readOnlyRootFilesystem") is True, (
        "set readOnlyRootFilesystem: true"
    )


def test_live_pod_becomes_ready(workspace: Path, kube, namespace: str) -> None:  # type: ignore[no-untyped-def]
    kube("apply", "-n", namespace, "-f", str(workspace / "pod.yaml"))
    waited = kube("wait", "-n", namespace, "--for=condition=Ready", "pod/podinfo", "--timeout=120s", check=False)
    if waited.returncode != 0:
        described = kube("describe", "-n", namespace, "pod/podinfo", check=False).stdout
        raise AssertionError(f"the Pod did not become Ready:\n{described[-2500:]}")
    status = json.loads(kube("get", "-n", namespace, "pod/podinfo", "-o", "json").stdout)["status"]
    assert status.get("qosClass") == "Burstable"
