"""Best-practice warnings for Pods and workloads: valid YAML that will still hurt you in production."""

from typing import Any

from kubelab._common import as_dict, as_list, pod_spec_of

LONG_RUNNING = frozenset({"Pod", "Deployment", "ReplicaSet", "DaemonSet", "StatefulSet"})


def _image_tag(image: str) -> str | None:
    if "@" in image:
        return "digest"
    last = image.rsplit("/", 1)[-1]
    return last.split(":", 1)[1] if ":" in last else None


def warnings(obj: dict[str, Any]) -> list[str]:
    """Return best-practice warnings for one manifest.

    Covers image tags, requests and limits, probes, the restricted Pod Security settings, host namespaces, and
    bare Pods. Kinds without Pods return an empty list.

    Args:
        obj: A manifest.

    Returns:
        Warnings, each prefixed with the container it concerns where relevant.
    """
    kind = str(obj.get("kind"))
    spec = pod_spec_of(obj)
    if spec is None:
        return []
    found: list[str] = []
    if kind == "Pod":
        found.append("bare Pod: nothing recreates it if it or its node dies; use a Deployment")
    for flag in ("hostNetwork", "hostPID", "hostIPC"):
        if spec.get(flag) is True:
            found.append(f"{flag}: shares the node's namespace; avoid unless you are writing node software")
    pod_security = as_dict(spec.get("securityContext"))
    for raw in as_list(spec.get("containers")):
        container = as_dict(raw)
        name = str(container.get("name", "?"))
        image = str(container.get("image", ""))
        tag = _image_tag(image)
        if tag is None or tag == "latest":
            found.append(f"{name}: image {image!r} has no fixed tag; pin a version so rollouts are repeatable")
        resources = as_dict(container.get("resources"))
        requests, limits = as_dict(resources.get("requests")), as_dict(resources.get("limits"))
        if "cpu" not in requests or "memory" not in requests:
            found.append(f"{name}: set CPU and memory requests so the scheduler can place it")
        if "memory" not in limits:
            found.append(f"{name}: set a memory limit so one leak can't starve the node")
        if kind in LONG_RUNNING and "readinessProbe" not in container:
            found.append(f"{name}: add a readinessProbe so traffic waits until it can serve")
        if kind in LONG_RUNNING and "livenessProbe" not in container:
            found.append(f"{name}: add a livenessProbe so a wedged process is restarted")
        security = as_dict(container.get("securityContext"))
        if not (security.get("runAsNonRoot") is True or pod_security.get("runAsNonRoot") is True):
            found.append(f"{name}: set runAsNonRoot: true")
        if security.get("allowPrivilegeEscalation") is not False:
            found.append(f"{name}: set allowPrivilegeEscalation: false")
        if security.get("privileged") is True:
            found.append(f"{name}: privileged containers can take over the node")
        if "ALL" not in [str(c) for c in as_list(as_dict(security.get("capabilities")).get("drop"))]:
            found.append(f"{name}: drop all capabilities (capabilities.drop: [ALL])")
        seccomp = as_dict(security.get("seccompProfile")) or as_dict(pod_security.get("seccompProfile"))
        if seccomp.get("type") not in ("RuntimeDefault", "Localhost"):
            found.append(f"{name}: set seccompProfile.type: RuntimeDefault")
    return found
