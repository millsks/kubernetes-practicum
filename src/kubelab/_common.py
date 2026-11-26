"""Small helpers shared by the kubelab modules."""

from typing import Any

POD_TEMPLATE_PATHS: dict[str, tuple[str, ...]] = {
    "Pod": ("spec",),
    "Deployment": ("spec", "template", "spec"),
    "ReplicaSet": ("spec", "template", "spec"),
    "DaemonSet": ("spec", "template", "spec"),
    "StatefulSet": ("spec", "template", "spec"),
    "Job": ("spec", "template", "spec"),
    "CronJob": ("spec", "jobTemplate", "spec", "template", "spec"),
}


def as_dict(value: Any) -> dict[str, Any]:
    """Return ``value`` if it is a dict, otherwise an empty dict.

    Args:
        value: Anything.

    Returns:
        A dict safe to call ``.get`` on.
    """
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> list[Any]:
    """Return ``value`` if it is a list, otherwise an empty list.

    Args:
        value: Anything.

    Returns:
        A list safe to iterate.
    """
    return value if isinstance(value, list) else []


def pod_spec_of(obj: dict[str, Any]) -> dict[str, Any] | None:
    """Return the Pod spec inside a Pod or a workload, or ``None`` for kinds that have none.

    Args:
        obj: A manifest.

    Returns:
        The Pod spec dict, or ``None``.
    """
    path = POD_TEMPLATE_PATHS.get(str(obj.get("kind")))
    if path is None:
        return None
    current: Any = obj
    for part in path:
        current = as_dict(current).get(part)
    return as_dict(current)


def all_containers(spec: dict[str, Any]) -> list[dict[str, Any]]:
    """Return init containers followed by app containers.

    Args:
        spec: A Pod spec.

    Returns:
        Every container mapping in the spec.
    """
    return [as_dict(c) for c in [*as_list(spec.get("initContainers")), *as_list(spec.get("containers"))]]
