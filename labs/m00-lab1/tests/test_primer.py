"""Checks for m00-lab1: the primer kind config, runtime answers, and (live) the running cluster."""

import json
import re
import tomllib
from pathlib import Path
from typing import Any

import kubelab


def config(workspace: Path) -> dict[str, Any]:
    path = workspace / "kind-primer.yaml"
    assert path.is_file(), "kind-primer.yaml is missing"
    text = path.read_text(encoding="utf-8")
    assert "TODO" not in text, "replace the TODO comment once the file is done"
    docs = kubelab.load_manifests(text)
    assert len(docs) == 1, "kind-primer.yaml should hold exactly one document"
    return docs[0]


def answers(workspace: Path) -> dict[str, Any]:
    path = workspace / "answers.toml"
    assert path.is_file(), "answers.toml is missing"
    return tomllib.loads(path.read_text(encoding="utf-8"))


def norm(value: Any) -> str:
    return " ".join(str(value).lower().split())


def test_config_is_valid(workspace: Path) -> None:
    problems = kubelab.check_kind_config(config(workspace))
    assert problems == [], "; ".join(problems)


def test_name_and_nodes(workspace: Path) -> None:
    cfg = config(workspace)
    assert cfg.get("name") == "primer", "name the cluster primer"
    assert kubelab.node_roles(cfg) == ["control-plane", "worker", "worker"], "one control-plane node, then two workers"


def test_port_mapping(workspace: Path) -> None:
    mappings = kubelab.port_mappings(config(workspace))
    assert kubelab.PortMapping("control-plane", 30080, 8080, "TCP") in mappings, (
        "map containerPort 30080 to hostPort 8080 (TCP) on the control-plane node"
    )
    assert len(mappings) == 1, "publish only the one port"


def test_runtime_answers(workspace: Path) -> None:
    a = answers(workspace)
    assert norm(a.get("pod_runtime")) == "containerd", "pod_runtime: which runtime does the kubelet drive over CRI?"
    assert norm(a.get("node_engine")) == "docker", "node_engine: what creates kind's node containers here?"
    assert norm(a.get("inspect_cli")) == "crictl", "inspect_cli: the CRI debugging CLI inside each node"


def test_load_command(workspace: Path) -> None:
    command = norm(answers(workspace).get("load_command"))
    assert command.startswith("kind load docker-image "), "start with: kind load docker-image"
    tokens = command.split()
    assert "app:0.1.0" in tokens, "load the image app:0.1.0"
    joined = " ".join(tokens)
    assert re.search(r"(--name[ =]primer|-n primer)\b", joined), "target the primer cluster with --name primer"


def test_colima_size(workspace: Path) -> None:
    a = answers(workspace)
    assert isinstance(a.get("colima_cpus"), int) and a["colima_cpus"] >= 4, "start Colima with at least 4 CPUs"
    assert isinstance(a.get("colima_memory_gb"), int | float) and a["colima_memory_gb"] >= 6, (
        "give Colima at least 6 GB"
    )


def test_live_cluster(kube) -> None:  # type: ignore[no-untyped-def]
    nodes = json.loads(kube("get", "nodes", "-o", "json").stdout)["items"]
    assert len(nodes) == 3, f"expected 3 nodes, found {len(nodes)}"
    roles = sorted(
        "control-plane" if "node-role.kubernetes.io/control-plane" in n["metadata"].get("labels", {}) else "worker"
        for n in nodes
    )
    assert roles == ["control-plane", "worker", "worker"]
    for node in nodes:
        name = node["metadata"]["name"]
        assert name.startswith("primer-"), f"{name}: is this the primer cluster?"
        ready = [c for c in node["status"]["conditions"] if c["type"] == "Ready"]
        assert ready and ready[0]["status"] == "True", f"{name} is not Ready"
        runtime = node["status"]["nodeInfo"]["containerRuntimeVersion"]
        assert runtime.startswith("containerd://"), f"{name} runs {runtime}, expected containerd"
