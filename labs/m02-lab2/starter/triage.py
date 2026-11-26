"""Explain unhealthy Pods from `kubectl get pods -o json` (m02-lab2).

Usage:
    kubectl get pods -A -o json | python triage.py
    python triage.py pods.json

Standard library only. Read labs/m02-lab2/README.md for the specification.
"""

import json
import sys


def diagnose(pod: dict) -> tuple[str, str] | None:
    """Return (reason, container) for an unhealthy Pod, or None when it's healthy or completed."""
    ...


def next_command(pod: dict, reason: str, container: str) -> str:
    """Return the kubectl command to run next for this diagnosis."""
    ...


def main(argv: list[str]) -> int:
    """Read the JSON, print one line per unhealthy Pod, and return the exit code."""
    ...


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
