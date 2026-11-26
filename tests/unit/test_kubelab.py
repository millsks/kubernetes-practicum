"""Unit tests for kubelab: manifests, quantities, selectors, validation, workloads, kind configs, and lint."""

import copy
from pathlib import Path
from typing import Any

import pytest

import kubelab
from kubelab.manifests import ManifestError
from kubelab.quantity import QuantityError
from kubelab.selectors import SelectorError


def deployment(**overrides: Any) -> dict[str, Any]:
    obj: dict[str, Any] = {
        "apiVersion": "apps/v1",
        "kind": "Deployment",
        "metadata": {"name": "web", "labels": {"app": "web"}},
        "spec": {
            "replicas": 3,
            "selector": {"matchLabels": {"app": "web"}},
            "strategy": {"type": "RollingUpdate", "rollingUpdate": {"maxSurge": 1, "maxUnavailable": 0}},
            "template": {
                "metadata": {"labels": {"app": "web"}},
                "spec": {
                    "securityContext": {"runAsNonRoot": True, "seccompProfile": {"type": "RuntimeDefault"}},
                    "containers": [
                        {
                            "name": "app",
                            "image": "ghcr.io/stefanprodan/podinfo:6.7.1",
                            "ports": [{"containerPort": 9898, "name": "http"}],
                            "readinessProbe": {"httpGet": {"path": "/readyz", "port": "http"}},
                            "livenessProbe": {"httpGet": {"path": "/healthz", "port": "http"}},
                            "resources": {"requests": {"cpu": "50m", "memory": "64Mi"}, "limits": {"memory": "128Mi"}},
                            "securityContext": {
                                "allowPrivilegeEscalation": False,
                                "capabilities": {"drop": ["ALL"]},
                            },
                        }
                    ],
                },
            },
        },
    }
    obj.update(overrides)
    return obj


def pod_of(dep: dict[str, Any]) -> dict[str, Any]:
    return {
        "apiVersion": "v1",
        "kind": "Pod",
        "metadata": {"name": "p"},
        "spec": copy.deepcopy(dep["spec"]["template"]["spec"]),
    }


# ---------------- manifests ----------------


def test_load_manifests_multi_document_skips_empty() -> None:
    text = "---\napiVersion: v1\nkind: Namespace\nmetadata: {name: a}\n---\n# just a comment\n---\nkind: Pod\n"
    docs = kubelab.load_manifests(text)
    assert [d["kind"] for d in docs] == ["Namespace", "Pod"]


def test_load_manifests_errors() -> None:
    with pytest.raises(ManifestError, match="invalid YAML"):
        kubelab.load_manifests("a: [1, 2")
    with pytest.raises(ManifestError, match="not a mapping"):
        kubelab.load_manifests("- a\n- b\n")


def test_load_files_and_find(tmp_path: Path) -> None:
    (tmp_path / "a.yaml").write_text("kind: Service\nmetadata: {name: web}\n", encoding="utf-8")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "b.yml").write_text(
        "kind: Deployment\nmetadata: {name: web}\n---\nkind: Deployment\nmetadata: {name: api}\n"
    )
    docs = kubelab.load_files([tmp_path])
    assert len(docs) == 3
    assert len(kubelab.find(docs, "Deployment")) == 2
    assert kubelab.find(docs, "Deployment", "api")[0]["metadata"]["name"] == "api"
    assert kubelab.find(docs, "Pod") == []
    single = kubelab.load_files([tmp_path / "a.yaml"])
    assert single[0]["kind"] == "Service"
    (tmp_path / "bad.yaml").write_text("a: [", encoding="utf-8")
    with pytest.raises(ManifestError, match=r"bad\.yaml"):
        kubelab.load_files([tmp_path])


def test_dig() -> None:
    dep = deployment()
    assert kubelab.dig(dep, "spec.template.spec.containers.0.name") == "app"
    assert kubelab.dig(dep, "spec.template.spec.containers.5.name", "none") == "none"
    assert kubelab.dig(dep, "spec.missing") is None
    assert kubelab.dig(dep, "spec.replicas.deeper", 0) == 0


# ---------------- quantities ----------------


@pytest.mark.parametrize(
    ("value", "cores"), [("250m", 0.25), ("1", 1.0), (2, 2.0), (0.5, 0.5), ("1.5", 1.5), ("100u", 0.0001)]
)
def test_parse_cpu(value: Any, cores: float) -> None:
    assert kubelab.parse_cpu(value) == pytest.approx(cores)


@pytest.mark.parametrize(
    ("value", "size"),
    [
        ("128Mi", 134217728),
        ("1Gi", 1073741824),
        ("1G", 1000000000),
        ("1k", 1000),
        ("64", 64),
        ("1.5Ki", 1536),
        ("1e3", 1000),
        ("0.5", 1),
    ],
)
def test_parse_memory(value: Any, size: int) -> None:
    assert kubelab.parse_memory(value) == size


@pytest.mark.parametrize("bad", ["abc", "12Q", "", "1 Gi", True])
def test_bad_quantities(bad: Any) -> None:
    with pytest.raises(QuantityError):
        kubelab.parse_quantity(bad)


def test_negative_quantities() -> None:
    with pytest.raises(QuantityError, match="negative"):
        kubelab.parse_cpu("-1")
    with pytest.raises(QuantityError, match="negative"):
        kubelab.parse_memory("-1Mi")


# ---------------- selectors ----------------


def test_plain_and_match_labels() -> None:
    labels = {"app": "web", "tier": "front"}
    assert kubelab.selector_matches({"app": "web"}, labels)
    assert not kubelab.selector_matches({"app": "api"}, labels)
    assert kubelab.selector_matches({"matchLabels": {"app": "web"}}, labels)
    assert not kubelab.selector_matches({"matchLabels": {"app": "web", "x": "y"}}, labels)
    assert kubelab.selector_matches(None, labels)
    assert kubelab.selector_matches({}, None)
    assert kubelab.selector_matches({"version": 2}, {"version": "2"})


@pytest.mark.parametrize(
    ("expr", "expected"),
    [
        ({"key": "tier", "operator": "In", "values": ["front", "back"]}, True),
        ({"key": "tier", "operator": "In", "values": ["back"]}, False),
        ({"key": "tier", "operator": "NotIn", "values": ["back"]}, True),
        ({"key": "zone", "operator": "NotIn", "values": ["a"]}, True),
        ({"key": "tier", "operator": "Exists"}, True),
        ({"key": "zone", "operator": "Exists"}, False),
        ({"key": "zone", "operator": "DoesNotExist"}, True),
    ],
)
def test_match_expressions(expr: dict[str, Any], expected: bool) -> None:
    assert kubelab.selector_matches({"matchExpressions": [expr]}, {"app": "web", "tier": "front"}) is expected


def test_selector_errors_and_select() -> None:
    with pytest.raises(SelectorError, match="unknown operator"):
        kubelab.selector_matches({"matchExpressions": [{"key": "a", "operator": "Gt"}]}, {})
    with pytest.raises(SelectorError, match="needs key"):
        kubelab.selector_matches({"matchExpressions": [{"key": "a"}]}, {})
    objs = [{"metadata": {"labels": {"app": "a"}}}, {"metadata": {"labels": {"app": "b"}}}, {"metadata": {}}]
    assert kubelab.select({"app": "a"}, objs) == [objs[0]]


# ---------------- validation ----------------


def test_valid_deployment_has_no_problems() -> None:
    assert kubelab.check_object(deployment()) == []


def test_identity_problems() -> None:
    assert kubelab.check_object([]) == ["a manifest must be a mapping"]  # type: ignore[arg-type]
    problems = kubelab.check_object({"metadata": {}})
    assert "kind: required" in problems
    assert "apiVersion: required" in problems
    assert "metadata.name: required" in problems
    wrong = kubelab.check_object({"apiVersion": "v1", "kind": "Deployment", "metadata": {"name": "Web_1"}})
    assert any("apps/v1" in p for p in wrong)
    assert any("DNS-1123 subdomain" in p for p in wrong)
    assert any(
        "DNS-1035" in p
        for p in kubelab.check_object(
            {"apiVersion": "v1", "kind": "Service", "metadata": {"name": "1web"}, "spec": {"ports": [{"port": 80}]}}
        )
    )
    assert any(
        "DNS-1123 label" in p
        for p in kubelab.check_object({"apiVersion": "v1", "kind": "Namespace", "metadata": {"name": "a.b"}})
    )
    assert kubelab.check_object({"apiVersion": "example.com/v1", "kind": "Widget", "metadata": {"name": "w"}}) == []


def test_label_problems() -> None:
    assert kubelab.label_problems(None, "x") == []
    assert kubelab.label_problems(["a"], "x") == ["x: must be a mapping of strings"]
    problems = kubelab.label_problems(
        {"Bad Prefix/app": "ok", "-bad": "ok", "v": 2, "ok": "has space", "example.com/team": "core", "empty": ""},
        "labels",
    )
    assert any("invalid prefix" in p for p in problems)
    assert any("'-bad' is not a valid label name" in p for p in problems)
    assert any("must be a string" in p for p in problems)
    assert any("'has space' is not a valid label value" in p for p in problems)
    assert len(problems) == 4


def test_name_helpers() -> None:
    assert kubelab.is_dns_label("web-1")
    assert not kubelab.is_dns_label("Web")
    assert not kubelab.is_dns_label("a" * 64)
    assert kubelab.is_dns_subdomain("api.v1.example")
    assert not kubelab.is_dns_subdomain("api..v1")


def test_pod_spec_problems() -> None:
    spec: dict[str, Any] = {
        "restartPolicy": "Sometimes",
        "initContainers": [{"name": "init", "image": "busybox:1.36", "restartPolicy": "OnFailure"}],
        "containers": [
            {
                "name": "app",
                "image": "x:1",
                "ports": [
                    {"containerPort": 70000, "name": "http"},
                    {"containerPort": 81, "name": "http"},
                    {"containerPort": 82, "name": "1234"},
                    {"containerPort": True},
                ],
                "readinessProbe": {"httpGet": {"path": "/", "port": "web"}},
                "livenessProbe": {"httpGet": {"path": "/"}},
                "startupProbe": {"exec": {"command": ["true"]}, "tcpSocket": {"port": 80}},
                "resources": {"requests": {"cpu": "2", "memory": "1Gi"}, "limits": {"cpu": "1", "memory": "lots"}},
            },
            {"name": "app"},
            {"image": "y:1"},
            {"name": "Bad_Name", "image": "z:1", "readinessProbe": {"tcpSocket": {"port": 80}, "periodSeconds": 0}},
        ],
    }
    problems = kubelab.check_pod_spec(spec)
    text = "\n".join(problems)
    assert "restartPolicy: 'Sometimes'" in text
    assert "native sidecar" in text
    assert "70000 must be an integer" in text
    assert "'http' is used twice" in text
    assert "'1234' must be 1-15" in text
    assert "True must be an integer" in text
    assert "no container port is named 'web'" in text
    assert "livenessProbe.httpGet.port: required" in text
    assert "needs exactly one of" in text
    assert "cpu request is larger than its limit" in text
    assert "'lots' is not a quantity" in text
    assert "'app' is used by another container" in text
    assert "containers[1].image: required" in text
    assert "containers[2].name: required" in text
    assert "'Bad_Name' is not a valid DNS-1123 label" in text
    assert "periodSeconds: must be a positive integer" in text
    assert kubelab.check_pod_spec({}) == ["spec.containers: at least one container is required"]


def test_pod_and_numeric_probe_ports_are_valid() -> None:
    pod = pod_of(deployment())
    pod["spec"]["containers"][0]["startupProbe"] = {"tcpSocket": {"port": 9898}}
    pod["spec"]["containers"][0]["livenessProbe"] = {"httpGet": {"path": "/", "port": "9898"}}
    pod["spec"]["initContainers"] = [{"name": "side", "image": "busybox:1.36", "restartPolicy": "Always"}]
    assert kubelab.check_object(pod) == []


def test_workload_problems() -> None:
    dep = deployment()
    dep["spec"]["selector"] = {"matchLabels": {"app": "other"}}
    dep["spec"]["replicas"] = -1
    dep["spec"]["template"]["spec"]["restartPolicy"] = "Never"
    problems = "\n".join(kubelab.check_object(dep))
    assert "does not match spec.template.metadata.labels" in problems
    assert "spec.replicas: -1" in problems
    assert "only allows 'Always'" in problems
    no_selector = deployment()
    no_selector["spec"]["selector"] = {}
    assert any("must not be empty" in p for p in kubelab.check_object(no_selector))
    bad_expr = deployment()
    bad_expr["spec"]["selector"] = {"matchExpressions": [{"key": "app", "operator": "Near"}]}
    assert any("unknown operator" in p for p in kubelab.check_object(bad_expr))


@pytest.mark.parametrize(
    ("strategy", "message"),
    [
        ({"type": "BlueGreen"}, "must be RollingUpdate or Recreate"),
        ({"type": "Recreate", "rollingUpdate": {"maxSurge": 1}}, "not allowed with type Recreate"),
        ({"rollingUpdate": {"maxSurge": 0, "maxUnavailable": "0%"}}, "cannot both be 0"),
    ],
)
def test_strategy_problems(strategy: dict[str, Any], message: str) -> None:
    dep = deployment()
    dep["spec"]["strategy"] = strategy
    assert any(message in p for p in kubelab.check_object(dep))


def test_recreate_and_other_workloads_valid() -> None:
    dep = deployment()
    dep["spec"]["strategy"] = {"type": "Recreate"}
    assert kubelab.check_object(dep) == []
    for kind in ("ReplicaSet", "DaemonSet", "StatefulSet"):
        other = deployment(kind=kind)
        del other["spec"]["strategy"]
        assert kubelab.check_object(other) == [], kind


def cronjob(**spec: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "schedule": "*/5 * * * *",
        "jobTemplate": {
            "spec": {
                "template": {
                    "spec": {"restartPolicy": "OnFailure", "containers": [{"name": "t", "image": "busybox:1.36"}]}
                }
            }
        },
    }
    base.update(spec)
    return {"apiVersion": "batch/v1", "kind": "CronJob", "metadata": {"name": "tick"}, "spec": base}


def test_job_and_cronjob() -> None:
    assert kubelab.check_object(cronjob()) == []
    assert kubelab.check_object(cronjob(schedule="@hourly")) == []
    assert any("five fields" in p for p in kubelab.check_object(cronjob(schedule="* * *")))
    assert any("spec.schedule: required" in p for p in kubelab.check_object(cronjob(schedule="")))
    assert any("concurrencyPolicy" in p for p in kubelab.check_object(cronjob(concurrencyPolicy="Never")))
    no_template = cronjob()
    del no_template["spec"]["jobTemplate"]
    assert "spec.jobTemplate: required" in kubelab.check_object(no_template)
    job = {
        "apiVersion": "batch/v1",
        "kind": "Job",
        "metadata": {"name": "j"},
        "spec": {
            "backoffLimit": -1,
            "template": {"spec": {"restartPolicy": "Always", "containers": [{"name": "c", "image": "i:1"}]}},
        },
    }
    problems = kubelab.check_object(job)
    assert any("needs 'Never' or 'OnFailure'" in p for p in problems)
    assert any("backoffLimit" in p for p in problems)


def test_service() -> None:
    svc = {"apiVersion": "v1", "kind": "Service", "metadata": {"name": "web"}, "spec": {"ports": [{"port": 80}]}}
    assert kubelab.check_object(svc) == []
    svc["spec"] = {"type": "Fancy", "ports": [{"port": 0}, {"port": 81}]}
    text = "\n".join(kubelab.check_object(svc))
    assert "not a Service type" in text
    assert "ports[0].port: 0" in text
    assert "name: required when a Service has more than one port" in text
    svc["spec"] = {"type": "ClusterIP"}
    assert "spec.ports: at least one port is required" in kubelab.check_object(svc)
    svc["spec"] = {"type": "ExternalName", "externalName": "db.example.com"}
    assert kubelab.check_object(svc) == []


def test_pod_containers_and_spec_of() -> None:
    dep = deployment()
    assert [c["name"] for c in kubelab.pod_containers(dep)] == ["app"]
    assert kubelab.pod_containers({"kind": "Service"}) == []
    assert kubelab.pod_spec_of({"kind": "ConfigMap"}) is None
    cj = cronjob()
    assert kubelab.pod_spec_of(cj)["restartPolicy"] == "OnFailure"  # type: ignore[index]


# ---------------- workloads ----------------


def spec_with(*resources: dict[str, Any]) -> dict[str, Any]:
    return {"containers": [{"name": f"c{i}", "image": "i:1", "resources": r} for i, r in enumerate(resources)]}


def test_qos_class() -> None:
    assert kubelab.qos_class(spec_with({})) == "BestEffort"
    assert kubelab.qos_class({"containers": []}) == "BestEffort"
    guaranteed = {"limits": {"cpu": "500m", "memory": "128Mi"}}
    assert kubelab.qos_class(spec_with(guaranteed)) == "Guaranteed"
    equal = {"requests": {"cpu": "0.5", "memory": "128Mi"}, "limits": {"cpu": "500m", "memory": "128Mi"}}
    assert kubelab.qos_class(spec_with(equal, guaranteed)) == "Guaranteed"
    assert kubelab.qos_class(spec_with({"requests": {"cpu": "100m"}})) == "Burstable"
    smaller = {"requests": {"cpu": "100m", "memory": "64Mi"}, "limits": {"cpu": "500m", "memory": "128Mi"}}
    assert kubelab.qos_class(spec_with(smaller)) == "Burstable"
    assert kubelab.qos_class(spec_with(guaranteed, {})) == "Burstable"


@pytest.mark.parametrize(
    ("args", "expected"),
    [
        ((4, 1, 0), (5, 4)),
        ((4, "25%", "25%"), (5, 3)),
        ((10, "25%", "25%"), (13, 8)),
        ((3, "50%", "50%"), (5, 2)),
        ((1, "25%", "25%"), (2, 1)),
        ((0, 0, 0), (0, 0)),
        ((4, 0, 2), (4, 2)),
    ],
)
def test_rollout_bounds(args: tuple[Any, ...], expected: tuple[int, int]) -> None:
    assert kubelab.rollout_bounds(*args) == expected


def test_rollout_bounds_errors() -> None:
    with pytest.raises(ValueError, match="both be 0"):
        kubelab.rollout_bounds(4, 0, "0%")
    with pytest.raises(ValueError, match="both be 0"):
        kubelab.rollout_bounds(3, "0%", "10%")
    with pytest.raises(ValueError, match="negative"):
        kubelab.rollout_bounds(-1)
    with pytest.raises(ValueError, match="negative"):
        kubelab.rollout_bounds(3, -1, 1)


def status(**fields: Any) -> dict[str, Any]:
    return {"status": fields}


def cstat(name: str = "app", **fields: Any) -> dict[str, Any]:
    return {"name": name, **fields}


def test_pod_issue() -> None:
    assert kubelab.pod_issue(status(phase="Succeeded")).reason == "Completed"  # type: ignore[union-attr]
    unscheduled = status(phase="Pending", conditions=[{"type": "PodScheduled", "status": "False"}])
    assert kubelab.pod_issue(unscheduled).reason == "Unschedulable"  # type: ignore[union-attr]
    pull = status(phase="Pending", containerStatuses=[cstat(state={"waiting": {"reason": "ImagePullBackOff"}})])
    issue = kubelab.pod_issue(pull)
    assert issue is not None and issue.reason == "ImagePullBackOff" and issue.container == "app"
    oom = status(
        phase="Running",
        containerStatuses=[
            cstat(state={"waiting": {"reason": "CrashLoopBackOff"}}, lastState={"terminated": {"reason": "OOMKilled"}})
        ],
    )
    assert kubelab.pod_issue(oom).reason == "OOMKilled"  # type: ignore[union-attr]
    crash = status(phase="Running", containerStatuses=[cstat(state={"waiting": {"reason": "CrashLoopBackOff"}})])
    assert kubelab.pod_issue(crash).reason == "CrashLoopBackOff"  # type: ignore[union-attr]
    config = status(
        phase="Pending", containerStatuses=[cstat(state={"waiting": {"reason": "CreateContainerConfigError"}})]
    )
    assert "ConfigMap" in kubelab.pod_issue(config).hint  # type: ignore[union-attr]
    failed = status(phase="Failed", containerStatuses=[cstat(state={"terminated": {"reason": "Error", "exitCode": 3}})])
    assert kubelab.pod_issue(failed).reason == "Error"  # type: ignore[union-attr]
    unready = status(
        phase="Running",
        containerStatuses=[
            cstat("side", ready=True, state={"running": {}}),
            cstat("app", ready=False, state={"running": {}}),
        ],
    )
    issue = kubelab.pod_issue(unready)
    assert issue is not None and issue.reason == "NotReady" and issue.container == "app"
    healthy = status(
        phase="Running",
        conditions=[{"type": "PodScheduled", "status": "True"}],
        containerStatuses=[cstat(ready=True, state={"running": {}})],
    )
    assert kubelab.pod_issue(healthy) is None
    init = status(phase="Pending", initContainerStatuses=[cstat("init", state={"waiting": {"reason": "ErrImagePull"}})])
    assert kubelab.pod_issue(init).container == "init"  # type: ignore[union-attr]
    assert kubelab.pod_issue({}) is None


# ---------------- kind ----------------


def kind_config(**overrides: Any) -> dict[str, Any]:
    config: dict[str, Any] = {
        "kind": "Cluster",
        "apiVersion": "kind.x-k8s.io/v1alpha4",
        "name": "primer",
        "nodes": [
            {
                "role": "control-plane",
                "extraPortMappings": [{"containerPort": 30080, "hostPort": 8080, "protocol": "TCP"}],
            },
            {"role": "worker"},
            {"role": "worker"},
        ],
    }
    config.update(overrides)
    return config


def test_kind_config_valid() -> None:
    config = kind_config()
    assert kubelab.check_kind_config(config) == []
    assert kubelab.node_roles(config) == ["control-plane", "worker", "worker"]
    assert kubelab.port_mappings(config) == [kubelab.PortMapping("control-plane", 30080, 8080, "TCP")]
    assert kubelab.node_roles({"kind": "Cluster"}) == ["control-plane"]


def test_kind_config_problems() -> None:
    config = kind_config(kind="Cluser", apiVersion="v1", name="Primer")
    config["nodes"] = [
        {
            "role": "worker",
            "extraPortMappings": [
                {"containerPort": "30080", "hostPort": 8080},
                {"containerPort": 1, "hostPort": 8080, "protocol": "HTTP"},
            ],
        },
        {"role": "master", "extraPortMappings": [{"containerPort": 2, "hostPort": 8080}]},
    ]
    text = "\n".join(kubelab.check_kind_config(config))
    assert "kind: must be 'Cluster'" in text
    assert "apiVersion: must be" in text
    assert "name: 'Primer'" in text
    assert "'master' must be" in text
    assert "at least one control-plane" in text
    assert "containerPort: '30080'" in text
    assert "protocol: 'HTTP'" in text
    assert "8080 is already mapped" in text
    assert kubelab.port_mappings(config) == [
        kubelab.PortMapping("worker", 1, 8080, "HTTP"),
        kubelab.PortMapping("master", 2, 8080, "TCP"),
    ]


# ---------------- lint ----------------


def test_lint_clean_deployment() -> None:
    assert kubelab.warnings(deployment()) == []
    assert kubelab.warnings({"kind": "Service"}) == []


def test_lint_everything_wrong() -> None:
    pod = {
        "kind": "Pod",
        "metadata": {"name": "p"},
        "spec": {
            "hostNetwork": True,
            "containers": [
                {"name": "a", "image": "nginx", "securityContext": {"privileged": True}},
                {"name": "b", "image": "registry:5000/team/app:latest"},
                {
                    "name": "c",
                    "image": "app@sha256:abc",
                    "resources": {"requests": {"cpu": "1", "memory": "1Gi"}, "limits": {"memory": "1Gi"}},
                },
            ],
        },
    }
    text = "\n".join(kubelab.warnings(pod))
    assert "bare Pod" in text
    assert "hostNetwork" in text
    assert "a: image 'nginx' has no fixed tag" in text
    assert "b: image 'registry:5000/team/app:latest' has no fixed tag" in text
    assert "c: image" not in text
    assert "a: set CPU and memory requests" in text
    assert "c: set CPU and memory requests" not in text
    assert "a: set a memory limit" in text
    assert "readinessProbe" in text and "livenessProbe" in text
    assert "runAsNonRoot" in text
    assert "allowPrivilegeEscalation" in text
    assert "privileged containers" in text
    assert "drop all capabilities" in text
    assert "seccompProfile" in text


def test_lint_jobs_skip_probe_warnings() -> None:
    cj = cronjob()
    text = "\n".join(kubelab.warnings(cj))
    assert "readinessProbe" not in text
    assert "requests" in text
