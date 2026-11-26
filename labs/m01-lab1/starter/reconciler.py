"""A ReplicaSet controller's decision logic, in plain Python (m01-lab1).

A Pod is a dict:

    {"name": "web-1", "phase": "Running", "ready": True, "node": "primer-worker", "deleting": False, "created": 3}

``phase`` is one of Pending, Running, Succeeded, Failed. ``node`` is None until the Pod is scheduled. ``deleting`` is
True once a delete has been requested (the Pod is terminating). ``created`` is a creation counter: higher is newer.

Read labs/m01-lab1/README.md for the full specification. Implement ``active``, ``reconcile``, and ``converge``.
``apply_actions`` and ``settle`` are provided: they play the part of the API server, scheduler, and kubelet.
"""

from itertools import count


def active(pods: list[dict]) -> list[dict]:
    """Return the Pods that count toward the replica total."""
    ...


def reconcile(desired: int, pods: list[dict], prefix: str = "web") -> dict[str, list[str]]:
    """Return {"create": [names], "delete": [names]}, both sorted, to move ``pods`` toward ``desired``."""
    ...


def converge(desired: int, pods: list[dict], prefix: str = "web", max_rounds: int = 10) -> tuple[list[dict], int]:
    """Reconcile, apply, and settle until reconcile asks for nothing. Return (final pods, rounds that acted)."""
    ...


# ---------------------------------------------------------------- provided: the rest of the cluster

_clock = count(1000)
NODES = ("primer-worker", "primer-worker2")


def apply_actions(pods: list[dict], actions: dict[str, list[str]]) -> list[dict]:
    """Play the API server: mark deleted Pods as terminating and add new Pending Pods. Returns a new list."""
    to_delete = set(actions.get("delete", []))
    updated = [{**p, "deleting": p["deleting"] or p["name"] in to_delete} for p in pods]
    for name in actions.get("create", []):
        updated.append({"name": name, "phase": "Pending", "ready": False, "node": None, "deleting": False, "created": next(_clock)})
    return updated


def settle(pods: list[dict]) -> list[dict]:
    """Play the scheduler and kubelet: terminating Pods disappear; Pending Pods get a node and become ready."""
    settled = []
    for i, pod in enumerate(p for p in pods if not p["deleting"]):
        if pod["phase"] == "Pending":
            pod = {**pod, "phase": "Running", "ready": True, "node": pod["node"] or NODES[i % len(NODES)]}
        settled.append(pod)
    return settled
