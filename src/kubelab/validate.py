"""Structural validation of manifests: the mistakes the API server would reject, caught before you apply."""

import re
from typing import Any

from kubelab._common import all_containers, as_dict, as_list, pod_spec_of
from kubelab.quantity import QuantityError, parse_cpu, parse_memory
from kubelab.selectors import SelectorError, selector_matches

API_VERSIONS: dict[str, str] = {
    "Pod": "v1",
    "Service": "v1",
    "ConfigMap": "v1",
    "Secret": "v1",
    "Namespace": "v1",
    "Deployment": "apps/v1",
    "ReplicaSet": "apps/v1",
    "DaemonSet": "apps/v1",
    "StatefulSet": "apps/v1",
    "Job": "batch/v1",
    "CronJob": "batch/v1",
}
WORKLOADS = frozenset({"Deployment", "ReplicaSet", "DaemonSet", "StatefulSet"})

_DNS_LABEL = re.compile(r"^[a-z0-9]([-a-z0-9]*[a-z0-9])?$")
_DNS_SUBDOMAIN = re.compile(r"^[a-z0-9]([-a-z0-9]*[a-z0-9])?(\.[a-z0-9]([-a-z0-9]*[a-z0-9])?)*$")
_DNS_1035 = re.compile(r"^[a-z]([-a-z0-9]*[a-z0-9])?$")
_LABEL_NAME = re.compile(r"^[A-Za-z0-9]([-A-Za-z0-9_.]*[A-Za-z0-9])?$")
_PORT_NAME = re.compile(r"^[a-z0-9]([-a-z0-9]*[a-z0-9])?$")
_CRON_MACROS = frozenset({"@yearly", "@annually", "@monthly", "@weekly", "@daily", "@midnight", "@hourly"})
_PROBE_HANDLERS = ("httpGet", "tcpSocket", "exec", "grpc")


def is_dns_label(name: str) -> bool:
    """Tell whether ``name`` is a valid DNS-1123 label (container names, namespace names).

    Args:
        name: Candidate name.

    Returns:
        ``True`` for 1-63 lowercase letters, digits, and hyphens, starting and ending alphanumeric.
    """
    return len(name) <= 63 and bool(_DNS_LABEL.match(name))


def is_dns_subdomain(name: str) -> bool:
    """Tell whether ``name`` is a valid DNS-1123 subdomain (most object names).

    Args:
        name: Candidate name.

    Returns:
        ``True`` for up to 253 characters of dot-separated DNS labels.
    """
    return len(name) <= 253 and bool(_DNS_SUBDOMAIN.match(name))


def label_problems(labels: Any, where: str) -> list[str]:
    """Check label keys and values against the Kubernetes syntax rules.

    Args:
        labels: The labels mapping.
        where: Path used in messages, such as ``metadata.labels``.

    Returns:
        Problems found (empty when valid).
    """
    problems: list[str] = []
    if labels is None:
        return problems
    if not isinstance(labels, dict):
        return [f"{where}: must be a mapping of strings"]
    for key, value in labels.items():
        key = str(key)
        prefix, _, name = key.rpartition("/")
        if prefix and not is_dns_subdomain(prefix):
            problems.append(f"{where}: key {key!r} has an invalid prefix")
        if not (len(name) <= 63 and _LABEL_NAME.match(name)):
            problems.append(f"{where}: key {key!r} is not a valid label name")
        if not isinstance(value, str):
            problems.append(f"{where}.{key}: value {value!r} must be a string (quote numbers and booleans in YAML)")
        elif value and not (len(value) <= 63 and _LABEL_NAME.match(value)):
            problems.append(f"{where}.{key}: value {value!r} is not a valid label value")
    return problems


def check_object(obj: dict[str, Any]) -> list[str]:
    """Validate one manifest and return every problem found.

    Checks identity (``apiVersion``, ``kind``, ``metadata.name``), labels, and the kind-specific rules for Pods,
    workloads (Deployment, ReplicaSet, DaemonSet, StatefulSet), Jobs, CronJobs, and Services. Unknown kinds only get
    the identity checks.

    Args:
        obj: A manifest.

    Returns:
        Human-readable problems, each prefixed with the field path. Empty means valid.
    """
    if not isinstance(obj, dict):
        return ["a manifest must be a mapping"]
    problems: list[str] = []
    kind = obj.get("kind")
    if not kind:
        problems.append("kind: required")
    expected = API_VERSIONS.get(str(kind))
    if not obj.get("apiVersion"):
        problems.append("apiVersion: required")
    elif expected and obj["apiVersion"] != expected:
        problems.append(f"apiVersion: {kind} uses {expected!r}, not {obj['apiVersion']!r}")
    metadata = as_dict(obj.get("metadata"))
    name = metadata.get("name")
    if not name:
        problems.append("metadata.name: required")
    elif kind == "Service" and not (len(str(name)) <= 63 and _DNS_1035.match(str(name))):
        problems.append(f"metadata.name: {name!r} must start with a letter and be a DNS-1035 label for a Service")
    elif kind == "Namespace" and not is_dns_label(str(name)):
        problems.append(f"metadata.name: {name!r} is not a valid DNS-1123 label")
    elif not is_dns_subdomain(str(name)):
        problems.append(f"metadata.name: {name!r} is not a valid DNS-1123 subdomain (lowercase, digits, '-', '.')")
    problems += label_problems(metadata.get("labels"), "metadata.labels")
    spec = as_dict(obj.get("spec"))
    if kind == "Pod":
        problems += check_pod_spec(spec, "spec")
    elif kind in WORKLOADS:
        problems += _check_workload(str(kind), spec)
    elif kind == "Job":
        problems += _check_job(spec, "spec")
    elif kind == "CronJob":
        problems += _check_cronjob(spec)
    elif kind == "Service":
        problems += _check_service(spec)
    return problems


def check_pod_spec(spec: dict[str, Any], where: str = "spec") -> list[str]:
    """Validate a Pod spec: containers, names, images, ports, probes, and resources.

    Args:
        spec: The Pod spec mapping.
        where: Path prefix used in messages.

    Returns:
        Problems found.
    """
    problems: list[str] = []
    containers = as_list(spec.get("containers"))
    if not containers:
        problems.append(f"{where}.containers: at least one container is required")
    restart = spec.get("restartPolicy")
    if restart is not None and restart not in ("Always", "OnFailure", "Never"):
        problems.append(f"{where}.restartPolicy: {restart!r} must be Always, OnFailure, or Never")
    seen: set[str] = set()
    groups = (("initContainers", as_list(spec.get("initContainers"))), ("containers", containers))
    for group, items in groups:
        for i, raw in enumerate(items):
            path = f"{where}.{group}[{i}]"
            container = as_dict(raw)
            name = str(container.get("name") or "")
            if not name:
                problems.append(f"{path}.name: required")
            elif not is_dns_label(name):
                problems.append(f"{path}.name: {name!r} is not a valid DNS-1123 label")
            elif name in seen:
                problems.append(f"{path}.name: {name!r} is used by another container in this Pod")
            seen.add(name)
            if not container.get("image"):
                problems.append(f"{path}.image: required")
            if group == "initContainers":
                policy = container.get("restartPolicy")
                if policy is not None and policy != "Always":
                    problems.append(f"{path}.restartPolicy: only 'Always' (a native sidecar) is allowed here")
            problems += _check_container(container, path)
    return problems


def _check_container(container: dict[str, Any], path: str) -> list[str]:
    problems: list[str] = []
    port_names: set[str] = set()
    for j, raw in enumerate(as_list(container.get("ports"))):
        port = as_dict(raw)
        number = port.get("containerPort")
        if not isinstance(number, int) or isinstance(number, bool) or not 1 <= number <= 65535:
            problems.append(f"{path}.ports[{j}].containerPort: {number!r} must be an integer from 1 to 65535")
        port_name = port.get("name")
        if port_name is not None:
            port_name = str(port_name)
            if not (len(port_name) <= 15 and _PORT_NAME.match(port_name) and re.search("[a-z]", port_name)):
                problems.append(f"{path}.ports[{j}].name: {port_name!r} must be 1-15 lowercase letters, digits, '-'")
            elif port_name in port_names:
                problems.append(f"{path}.ports[{j}].name: {port_name!r} is used twice")
            port_names.add(port_name)
    for probe_kind in ("startupProbe", "livenessProbe", "readinessProbe"):
        if probe_kind in container:
            problems += _check_probe(as_dict(container[probe_kind]), port_names, f"{path}.{probe_kind}")
    problems += _check_resources(as_dict(container.get("resources")), f"{path}.resources")
    return problems


def _check_probe(probe: dict[str, Any], port_names: set[str], path: str) -> list[str]:
    handlers = [h for h in _PROBE_HANDLERS if h in probe]
    if len(handlers) != 1:
        return [f"{path}: needs exactly one of {', '.join(_PROBE_HANDLERS)}"]
    handler = handlers[0]
    if handler in ("httpGet", "tcpSocket"):
        port = as_dict(probe[handler]).get("port")
        if isinstance(port, str) and not port.isdigit() and port not in port_names:
            return [f"{path}.{handler}.port: no container port is named {port!r}"]
        if port is None:
            return [f"{path}.{handler}.port: required"]
    problems = []
    for field in ("periodSeconds", "timeoutSeconds", "failureThreshold", "successThreshold"):
        value = probe.get(field)
        if value is not None and (not isinstance(value, int) or value < 1):
            problems.append(f"{path}.{field}: must be a positive integer")
    return problems


def _check_resources(resources: dict[str, Any], path: str) -> list[str]:
    problems: list[str] = []
    parsed: dict[str, dict[str, float]] = {"requests": {}, "limits": {}}
    for section in ("requests", "limits"):
        for resource, value in as_dict(resources.get(section)).items():
            try:
                if resource == "cpu":
                    parsed[section]["cpu"] = parse_cpu(value)
                elif resource == "memory":
                    parsed[section]["memory"] = float(parse_memory(value))
            except QuantityError as exc:
                problems.append(f"{path}.{section}.{resource}: {exc}")
    for resource, request in parsed["requests"].items():
        limit = parsed["limits"].get(resource)
        if limit is not None and request > limit:
            problems.append(f"{path}: {resource} request is larger than its limit")
    return problems


def _check_workload(kind: str, spec: dict[str, Any]) -> list[str]:
    problems: list[str] = []
    selector = spec.get("selector")
    template = as_dict(spec.get("template"))
    labels = as_dict(template.get("metadata")).get("labels")
    if not selector or not (as_dict(selector).get("matchLabels") or as_dict(selector).get("matchExpressions")):
        problems.append("spec.selector: required and must not be empty")
    else:
        try:
            if not selector_matches(selector, labels):
                problems.append("spec.selector: does not match spec.template.metadata.labels")
        except SelectorError as exc:
            problems.append(f"spec.selector: {exc}")
    problems += label_problems(labels, "spec.template.metadata.labels")
    replicas = spec.get("replicas")
    if replicas is not None and (not isinstance(replicas, int) or isinstance(replicas, bool) or replicas < 0):
        problems.append(f"spec.replicas: {replicas!r} must be a non-negative integer")
    pod = as_dict(template.get("spec"))
    restart = pod.get("restartPolicy")
    if restart not in (None, "Always"):
        problems.append(f"spec.template.spec.restartPolicy: a {kind} only allows 'Always'")
    problems += check_pod_spec(pod, "spec.template.spec")
    if kind == "Deployment":
        problems += _check_strategy(as_dict(spec.get("strategy")))
    return problems


def _check_strategy(strategy: dict[str, Any]) -> list[str]:
    kind = strategy.get("type", "RollingUpdate")
    rolling = strategy.get("rollingUpdate")
    if kind not in ("RollingUpdate", "Recreate"):
        return [f"spec.strategy.type: {kind!r} must be RollingUpdate or Recreate"]
    if kind == "Recreate":
        return ["spec.strategy.rollingUpdate: not allowed with type Recreate"] if rolling else []
    rolling = as_dict(rolling)
    surge, unavailable = rolling.get("maxSurge", "25%"), rolling.get("maxUnavailable", "25%")
    if str(surge) in ("0", "0%") and str(unavailable) in ("0", "0%"):
        return ["spec.strategy.rollingUpdate: maxSurge and maxUnavailable cannot both be 0"]
    return []


def _check_job(spec: dict[str, Any], where: str) -> list[str]:
    problems: list[str] = []
    pod = as_dict(as_dict(spec.get("template")).get("spec"))
    if pod.get("restartPolicy") not in ("Never", "OnFailure"):
        problems.append(f"{where}.template.spec.restartPolicy: a Job needs 'Never' or 'OnFailure'")
    backoff = spec.get("backoffLimit")
    if backoff is not None and (not isinstance(backoff, int) or backoff < 0):
        problems.append(f"{where}.backoffLimit: must be a non-negative integer")
    problems += check_pod_spec(pod, f"{where}.template.spec")
    return problems


def _check_cronjob(spec: dict[str, Any]) -> list[str]:
    problems: list[str] = []
    schedule = str(spec.get("schedule") or "")
    if not schedule:
        problems.append("spec.schedule: required")
    elif schedule not in _CRON_MACROS and len(schedule.split()) != 5:
        problems.append(f"spec.schedule: {schedule!r} needs five fields: minute hour day-of-month month day-of-week")
    policy = spec.get("concurrencyPolicy")
    if policy is not None and policy not in ("Allow", "Forbid", "Replace"):
        problems.append(f"spec.concurrencyPolicy: {policy!r} must be Allow, Forbid, or Replace")
    if "jobTemplate" not in spec:
        problems.append("spec.jobTemplate: required")
    else:
        problems += _check_job(as_dict(as_dict(spec["jobTemplate"]).get("spec")), "spec.jobTemplate.spec")
    return problems


def _check_service(spec: dict[str, Any]) -> list[str]:
    problems: list[str] = []
    service_type = spec.get("type", "ClusterIP")
    if service_type not in ("ClusterIP", "NodePort", "LoadBalancer", "ExternalName"):
        problems.append(f"spec.type: {service_type!r} is not a Service type")
    ports = as_list(spec.get("ports"))
    if service_type != "ExternalName" and not ports:
        problems.append("spec.ports: at least one port is required")
    for i, raw in enumerate(ports):
        number = as_dict(raw).get("port")
        if not isinstance(number, int) or not 1 <= number <= 65535:
            problems.append(f"spec.ports[{i}].port: {number!r} must be an integer from 1 to 65535")
        if len(ports) > 1 and not as_dict(raw).get("name"):
            problems.append(f"spec.ports[{i}].name: required when a Service has more than one port")
    return problems


def pod_containers(obj: dict[str, Any]) -> list[dict[str, Any]]:
    """Return every container (init first) of a Pod or a workload's Pod template.

    Args:
        obj: A manifest.

    Returns:
        Container mappings; empty for kinds without Pods.
    """
    spec = pod_spec_of(obj)
    return all_containers(spec) if spec is not None else []
