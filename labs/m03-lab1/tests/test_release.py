"""Checks for m03-lab1: the Deployment, the CronJob, rollout predictions, and (live) a real rollout and rollback."""

import json
import tomllib
from pathlib import Path
from typing import Any

import kubelab

LABEL = {"app.kubernetes.io/name": "podinfo"}


def one(workspace: Path, filename: str, kind: str) -> dict[str, Any]:
    path = workspace / filename
    assert path.is_file(), f"{filename} is missing"
    docs = kubelab.load_manifests(path.read_text(encoding="utf-8"))
    assert len(docs) == 1 and docs[0].get("kind") == kind, f"{filename} should hold exactly one {kind}"
    return docs[0]


def deployment(workspace: Path) -> dict[str, Any]:
    return one(workspace, "deployment.yaml", "Deployment")


def cronjob(workspace: Path) -> dict[str, Any]:
    return one(workspace, "cronjob.yaml", "CronJob")


def test_deployment_valid_and_clean(workspace: Path) -> None:
    dep = deployment(workspace)
    assert kubelab.dig(dep, "metadata.name") == "podinfo"
    problems = kubelab.check_object(dep)
    assert problems == [], "; ".join(problems)
    warnings = kubelab.warnings(dep)
    assert warnings == [], "; ".join(warnings)


def test_labels(workspace: Path) -> None:
    dep = deployment(workspace)
    assert kubelab.dig(dep, "spec.selector.matchLabels") == LABEL, "select on app.kubernetes.io/name: podinfo"
    labels = kubelab.dig(dep, "spec.template.metadata.labels", {})
    assert labels.get("app.kubernetes.io/name") == "podinfo"


def test_strategy(workspace: Path) -> None:
    dep = deployment(workspace)
    assert kubelab.dig(dep, "spec.replicas") == 4
    assert kubelab.dig(dep, "spec.strategy.type") == "RollingUpdate"
    assert kubelab.dig(dep, "spec.strategy.rollingUpdate.maxSurge") == 1
    assert kubelab.dig(dep, "spec.strategy.rollingUpdate.maxUnavailable") == 0


def test_rollout_safety(workspace: Path) -> None:
    dep = deployment(workspace)
    assert 5 <= kubelab.dig(dep, "spec.minReadySeconds", 0) <= 30, "minReadySeconds between 5 and 30"
    assert 60 <= kubelab.dig(dep, "spec.progressDeadlineSeconds", 0) <= 600, (
        "progressDeadlineSeconds between 60 and 600"
    )
    assert 3 <= kubelab.dig(dep, "spec.revisionHistoryLimit", 0) <= 10, "revisionHistoryLimit between 3 and 10"
    cause = kubelab.dig(dep, "metadata.annotations", {}).get("kubernetes.io/change-cause", "")
    assert str(cause).strip(), "record a kubernetes.io/change-cause annotation"


def test_image_and_probe(workspace: Path) -> None:
    container = kubelab.pod_containers(deployment(workspace))[0]
    assert container.get("image") == "ghcr.io/stefanprodan/podinfo:6.7.0"
    assert kubelab.dig(container, "readinessProbe.httpGet.port") == "http", "readiness probe on the named port http"


def test_cronjob(workspace: Path) -> None:
    cj = cronjob(workspace)
    assert kubelab.dig(cj, "metadata.name") == "podinfo-report"
    problems = kubelab.check_object(cj)
    assert problems == [], "; ".join(problems)
    spec = cj["spec"]
    assert spec.get("timeZone"), "set timeZone"
    assert spec.get("concurrencyPolicy") == "Forbid"
    assert isinstance(spec.get("startingDeadlineSeconds"), int), "set startingDeadlineSeconds"
    assert spec.get("successfulJobsHistoryLimit", 3) <= 3
    assert spec.get("failedJobsHistoryLimit", 0) >= 1, "keep at least one failed Job"
    job = kubelab.dig(cj, "spec.jobTemplate.spec", {})
    assert job.get("backoffLimit", 6) <= 3, "backoffLimit at most 3"
    assert isinstance(job.get("activeDeadlineSeconds"), int), "set activeDeadlineSeconds"


def test_cronjob_container_hygiene(workspace: Path) -> None:
    warnings = [
        w for w in kubelab.warnings(cronjob(workspace)) if "image" in w or "requests" in w or "memory limit" in w
    ]
    assert warnings == [], "; ".join(warnings)


def test_predictions(workspace: Path) -> None:
    path = workspace / "rollout.toml"
    assert path.is_file(), "rollout.toml is missing"
    answers = tomllib.loads(path.read_text(encoding="utf-8"))
    dep = deployment(workspace)
    rolling = kubelab.dig(dep, "spec.strategy.rollingUpdate", {})
    expected = kubelab.rollout_bounds(
        kubelab.dig(dep, "spec.replicas", 1), rolling.get("maxSurge", "25%"), rolling.get("maxUnavailable", "25%")
    )
    assert (answers.get("max_pods"), answers.get("min_ready")) == expected, (
        "max_pods and min_ready should match your settings"
    )
    assert answers.get("revision_after_undo") == 3, "a rollback is a new revision"
    assert answers.get("scale_creates_revision") is False, "replicas isn't part of the Pod template"
    assert str(answers.get("skip_policy", "")).strip() == "Forbid"


def test_live_rollout_and_rollback(workspace: Path, kube, namespace: str) -> None:  # type: ignore[no-untyped-def]
    ns = ["-n", namespace]
    kube("apply", *ns, "-f", str(workspace / "deployment.yaml"), "-f", str(workspace / "cronjob.yaml"))
    kube("rollout", "status", *ns, "deploy/podinfo", "--timeout=180s")
    kube("set", "image", *ns, "deploy/podinfo", "app=ghcr.io/stefanprodan/podinfo:6.7.1")
    kube("rollout", "status", *ns, "deploy/podinfo", "--timeout=180s")
    kube("rollout", "undo", *ns, "deploy/podinfo")
    kube("rollout", "status", *ns, "deploy/podinfo", "--timeout=180s")
    dep = json.loads(kube("get", *ns, "deploy/podinfo", "-o", "json").stdout)
    assert dep["spec"]["template"]["spec"]["containers"][0]["image"].endswith(":6.7.0"), "undo should restore 6.7.0"
    assert dep["metadata"]["annotations"].get("deployment.kubernetes.io/revision") == "3"
    kube("create", "job", *ns, "report-now", "--from=cronjob/podinfo-report")
    kube("wait", *ns, "--for=condition=complete", "job/report-now", "--timeout=120s")
