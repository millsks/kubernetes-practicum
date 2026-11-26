"""Label selectors: the way Services, ReplicaSets, and Deployments choose their Pods."""

from collections.abc import Mapping
from typing import Any


class SelectorError(ValueError):
    """Raised for a malformed selector."""


def selector_matches(selector: Mapping[str, Any] | None, labels: Mapping[str, str] | None) -> bool:
    """Tell whether a label selector selects an object with ``labels``.

    Accepts both forms: a Service-style plain mapping (``{"app": "web"}``) and a workload-style selector with
    ``matchLabels`` and/or ``matchExpressions``. Every requirement must hold. An empty selector matches everything,
    as the API defines it (which is why Deployments forbid one).

    Args:
        selector: The selector, or ``None`` (treated as empty).
        labels: The object's labels, or ``None`` (treated as no labels).

    Returns:
        ``True`` when every requirement is satisfied.

    Raises:
        SelectorError: For an unknown operator or a malformed expression.
    """
    selector = dict(selector or {})
    labels = dict(labels or {})
    if "matchLabels" not in selector and "matchExpressions" not in selector:
        return all(labels.get(k) == str(v) for k, v in selector.items())
    match_labels = selector.get("matchLabels") or {}
    if any(labels.get(k) != str(v) for k, v in match_labels.items()):
        return False
    return all(_expression_holds(expr, labels) for expr in selector.get("matchExpressions") or [])


def _expression_holds(expr: Mapping[str, Any], labels: Mapping[str, str]) -> bool:
    try:
        key, operator = expr["key"], expr["operator"]
    except (KeyError, TypeError) as exc:
        raise SelectorError(f"expression {expr!r} needs key and operator") from exc
    values = [str(v) for v in expr.get("values") or []]
    if operator == "In":
        return key in labels and labels[key] in values
    if operator == "NotIn":
        return key not in labels or labels[key] not in values
    if operator == "Exists":
        return key in labels
    if operator == "DoesNotExist":
        return key not in labels
    raise SelectorError(f"unknown operator {operator!r}")


def select(selector: Mapping[str, Any] | None, objects: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return the objects whose ``metadata.labels`` the selector matches.

    Args:
        selector: Selector in either form.
        objects: Manifests to filter.

    Returns:
        The selected objects, in order.
    """
    return [o for o in objects if selector_matches(selector, (o.get("metadata") or {}).get("labels"))]
