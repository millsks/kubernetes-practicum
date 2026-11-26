"""kubelab: small, model-free helpers for learning Kubernetes manifests.

The same code runs in the browser (Pyodide) for lesson exercises and locally for lab checks. It reads YAML, parses
resource quantities, matches label selectors, validates objects the way the API server would, flags best-practice
gaps, checks kind cluster configs, and diagnoses unhappy Pods. It never talks to a cluster.
"""

from kubelab._common import pod_spec_of
from kubelab.kind import PortMapping, check_kind_config, node_roles, port_mappings
from kubelab.lint import warnings
from kubelab.manifests import Manifest, ManifestError, dig, find, load_files, load_manifests
from kubelab.quantity import QuantityError, parse_cpu, parse_memory, parse_quantity
from kubelab.selectors import SelectorError, select, selector_matches
from kubelab.validate import (
    check_object,
    check_pod_spec,
    is_dns_label,
    is_dns_subdomain,
    label_problems,
    pod_containers,
)
from kubelab.workloads import PodIssue, pod_issue, qos_class, rollout_bounds

__all__ = [
    "Manifest",
    "ManifestError",
    "PodIssue",
    "PortMapping",
    "QuantityError",
    "SelectorError",
    "check_kind_config",
    "check_object",
    "check_pod_spec",
    "dig",
    "find",
    "is_dns_label",
    "is_dns_subdomain",
    "label_problems",
    "load_files",
    "load_manifests",
    "node_roles",
    "parse_cpu",
    "parse_memory",
    "parse_quantity",
    "pod_containers",
    "pod_issue",
    "pod_spec_of",
    "port_mappings",
    "qos_class",
    "rollout_bounds",
    "select",
    "selector_matches",
    "warnings",
]
