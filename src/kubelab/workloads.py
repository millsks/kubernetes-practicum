"""How the control plane reasons about workloads: QoS classes, rollout bounds, and why a Pod is unhappy."""

import math
from dataclasses import dataclass
from typing import Any

from kubelab._common import all_containers, as_dict, as_list
from kubelab.quantity import parse_cpu, parse_memory


def qos_class(pod_spec: dict[str, Any]) -> str:
    """Compute the Pod's quality-of-service class the way the kubelet does.

    * ``Guaranteed``: every container sets CPU and memory limits, and requests equal limits (a missing request
      defaults to its limit).
    * ``BestEffort``: no container sets any CPU or memory request or limit.
    * ``Burstable``: anything else.

    Args:
        pod_spec: A Pod spec.

    Returns:
        ``"Guaranteed"``, ``"Burstable"``, or ``"BestEffort"``.
    """
    containers = all_containers(pod_spec)
    any_set = False
    guaranteed = bool(containers)
    for container in containers:
        resources = as_dict(container.get("resources"))
        requests, limits = as_dict(resources.get("requests")), as_dict(resources.get("limits"))
        if any(k in requests or k in limits for k in ("cpu", "memory")):
            any_set = True
        for resource in ("cpu", "memory"):
            if resource not in limits:
                guaranteed = False
                continue
            parse = parse_cpu if resource == "cpu" else parse_memory
            request = requests.get(resource, limits[resource])
            if parse(request) != parse(limits[resource]):
                guaranteed = False
    if guaranteed:
        return "Guaranteed"
    return "Burstable" if any_set else "BestEffort"


def _resolve(value: int | str, replicas: int, *, round_up: bool) -> int:
    text = str(value).strip()
    if text.endswith("%"):
        exact = replicas * float(text[:-1]) / 100
        return math.ceil(exact) if round_up else math.floor(exact)
    number = int(text)
    if number < 0:
        raise ValueError(f"{value!r} must not be negative")
    return number


def rollout_bounds(replicas: int, max_surge: int | str = "25%", max_unavailable: int | str = "25%") -> tuple[int, int]:
    """Return the most Pods that may exist and the fewest that must stay available during a rolling update.

    Percentages are of ``replicas``: ``maxSurge`` rounds **up** and ``maxUnavailable`` rounds **down**, exactly as
    the Deployment controller does. Defaults are the Deployment defaults (25% each).

    Args:
        replicas: Desired replica count.
        max_surge: Absolute number or percentage string such as ``"25%"``.
        max_unavailable: Absolute number or percentage string.

    Returns:
        ``(max_pods, min_available)``.

    Raises:
        ValueError: If both resolve to zero (the rollout could never make progress) or a value is negative.
    """
    if replicas < 0:
        raise ValueError("replicas must not be negative")
    surge = _resolve(max_surge, replicas, round_up=True)
    unavailable = _resolve(max_unavailable, replicas, round_up=False)
    if surge == 0 and unavailable == 0 and replicas > 0:
        raise ValueError("maxSurge and maxUnavailable cannot both be 0")
    return replicas + surge, max(0, replicas - unavailable)


@dataclass(frozen=True, slots=True)
class PodIssue:
    """A diagnosis of what is wrong with a Pod.

    Attributes:
        reason: Short reason, such as ``ImagePullBackOff`` or ``OOMKilled``.
        container: Container the reason applies to, or ``""`` for Pod-level reasons.
        hint: What to check or fix next.
    """

    reason: str
    container: str
    hint: str


HINTS: dict[str, str] = {
    "Unschedulable": "No node fits: read the FailedScheduling event (requests too big, taint, selector, or PVC).",
    "ErrImagePull": "The image can't be pulled: check the name and tag, registry access, or kind load the image.",
    "ImagePullBackOff": "The image can't be pulled: check the name and tag, registry access, or kind load the image.",
    "CreateContainerConfigError": "A referenced ConfigMap, Secret, or key does not exist.",
    "CreateContainerError": "The runtime could not create the container: read the event message.",
    "OOMKilled": "The container went over its memory limit: raise the limit or fix the leak.",
    "CrashLoopBackOff": "The process keeps exiting: read kubectl logs --previous for the reason.",
    "Error": "The process exited with a non-zero code: read kubectl logs --previous.",
    "NotReady": "Running but failing its readiness probe: check the probe path, port, and timing.",
    "Completed": "Nothing is wrong: the Pod ran to completion.",
}


def pod_issue(pod: dict[str, Any]) -> PodIssue | None:
    """Diagnose a Pod from its ``status`` (as returned by ``kubectl get pod -o json``).

    The most specific cause wins: an ``OOMKilled`` last state is reported instead of the ``CrashLoopBackOff`` it
    causes, and a scheduling failure is reported before any container state.

    Args:
        pod: A Pod object including ``status``.

    Returns:
        The diagnosis, or ``None`` when the Pod is running and ready.
    """
    status = as_dict(pod.get("status"))
    if status.get("phase") == "Succeeded":
        return PodIssue("Completed", "", HINTS["Completed"])
    for condition in as_list(status.get("conditions")):
        condition = as_dict(condition)
        if condition.get("type") == "PodScheduled" and condition.get("status") == "False":
            return PodIssue("Unschedulable", "", HINTS["Unschedulable"])
    statuses = [
        as_dict(s) for s in [*as_list(status.get("initContainerStatuses")), *as_list(status.get("containerStatuses"))]
    ]
    for container in statuses:
        name = str(container.get("name", ""))
        last = as_dict(as_dict(container.get("lastState")).get("terminated"))
        now_terminated = as_dict(as_dict(container.get("state")).get("terminated"))
        if "OOMKilled" in (last.get("reason"), now_terminated.get("reason")):
            return PodIssue("OOMKilled", name, HINTS["OOMKilled"])
        waiting = as_dict(as_dict(container.get("state")).get("waiting")).get("reason")
        if waiting in HINTS:
            return PodIssue(str(waiting), name, HINTS[str(waiting)])
        if now_terminated and now_terminated.get("exitCode", 0) != 0:
            return PodIssue("Error", name, HINTS["Error"])
    if status.get("phase") == "Running":
        not_ready = [c for c in statuses if c.get("ready") is False]
        if not_ready:
            return PodIssue("NotReady", str(not_ready[0].get("name", "")), HINTS["NotReady"])
    return None
