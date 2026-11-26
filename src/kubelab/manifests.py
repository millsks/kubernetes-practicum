"""Load Kubernetes manifests from YAML text or files into plain dictionaries."""

from collections.abc import Iterable
from pathlib import Path
from typing import Any

import yaml

Manifest = dict[str, Any]


class ManifestError(ValueError):
    """Raised when text is not valid YAML or a document is not a mapping."""


def load_manifests(text: str) -> list[Manifest]:
    """Parse one or more YAML documents (separated by ``---``) into dictionaries.

    Empty documents are skipped, so a trailing ``---`` or a file of comments is harmless.

    Args:
        text: YAML text.

    Returns:
        One dictionary per non-empty document, in order.

    Raises:
        ManifestError: If the YAML is invalid or a document is not a mapping.
    """
    try:
        documents = list(yaml.safe_load_all(text))
    except yaml.YAMLError as exc:
        raise ManifestError(f"invalid YAML: {exc}") from exc
    manifests: list[Manifest] = []
    for index, document in enumerate(documents):
        if document is None:
            continue
        if not isinstance(document, dict):
            raise ManifestError(f"document {index + 1} is a {type(document).__name__}, not a mapping")
        manifests.append(document)
    return manifests


def load_files(paths: Iterable[Path]) -> list[Manifest]:
    """Load every manifest from the given files (directories are searched for ``*.yaml`` and ``*.yml``).

    Args:
        paths: Files or directories.

    Returns:
        Manifests in path order.

    Raises:
        ManifestError: If a file is invalid; the message names the file.
    """
    manifests: list[Manifest] = []
    for path in paths:
        files = sorted([*path.rglob("*.yaml"), *path.rglob("*.yml")]) if path.is_dir() else [path]
        for file in files:
            try:
                manifests.extend(load_manifests(file.read_text(encoding="utf-8")))
            except ManifestError as exc:
                raise ManifestError(f"{file.name}: {exc}") from exc
    return manifests


def find(manifests: Iterable[Manifest], kind: str, name: str | None = None) -> list[Manifest]:
    """Return the manifests of one kind, optionally with one name.

    Args:
        manifests: Manifests to search.
        kind: Kind such as ``Deployment`` (case-sensitive, as in YAML).
        name: ``metadata.name`` to match, or ``None`` for any.

    Returns:
        Matching manifests in their original order.
    """
    return [
        m
        for m in manifests
        if m.get("kind") == kind and (name is None or (m.get("metadata") or {}).get("name") == name)
    ]


def dig(obj: Any, path: str, default: Any = None) -> Any:
    """Read a nested field with a dotted path; numeric parts index lists.

    Args:
        obj: A manifest or any nested structure of dicts and lists.
        path: Dotted path such as ``spec.template.spec.containers.0.image``.
        default: Value returned when any part is missing.

    Returns:
        The value found, or ``default``.
    """
    current = obj
    for part in path.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        elif isinstance(current, list) and part.isdigit() and int(part) < len(current):
            current = current[int(part)]
        else:
            return default
    return current
