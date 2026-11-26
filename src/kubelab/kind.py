"""Check a kind cluster configuration file (``kind.x-k8s.io/v1alpha4``) before you create the cluster."""

from dataclasses import dataclass
from typing import Any

from kubelab._common import as_dict, as_list
from kubelab.validate import is_dns_label

KIND_API_VERSION = "kind.x-k8s.io/v1alpha4"


@dataclass(frozen=True, slots=True)
class PortMapping:
    """One ``extraPortMappings`` entry: traffic to ``host_port`` on your Mac reaches ``container_port`` on the node.

    Attributes:
        role: Role of the node that publishes the port.
        container_port: Port inside the node container (often a NodePort).
        host_port: Port on the host (your Mac, through Colima).
        protocol: ``TCP``, ``UDP``, or ``SCTP``.
    """

    role: str
    container_port: int
    host_port: int
    protocol: str = "TCP"


def node_roles(config: dict[str, Any]) -> list[str]:
    """Return the role of every node, in order. No ``nodes`` list means one control-plane node.

    Args:
        config: A kind cluster configuration.

    Returns:
        Roles such as ``["control-plane", "worker", "worker"]``.
    """
    nodes = as_list(config.get("nodes"))
    if not nodes:
        return ["control-plane"]
    return [str(as_dict(n).get("role", "control-plane")) for n in nodes]


def port_mappings(config: dict[str, Any]) -> list[PortMapping]:
    """Return every ``extraPortMappings`` entry across all nodes.

    Args:
        config: A kind cluster configuration.

    Returns:
        The mappings; entries with non-integer ports are skipped (``check_kind_config`` reports them).
    """
    mappings: list[PortMapping] = []
    for node in as_list(config.get("nodes")):
        node = as_dict(node)
        role = str(node.get("role", "control-plane"))
        for raw in as_list(node.get("extraPortMappings")):
            entry = as_dict(raw)
            container, host = entry.get("containerPort"), entry.get("hostPort")
            if isinstance(container, int) and isinstance(host, int):
                mappings.append(PortMapping(role, container, host, str(entry.get("protocol", "TCP"))))
    return mappings


def check_kind_config(config: dict[str, Any]) -> list[str]:
    """Validate a kind cluster configuration.

    Args:
        config: The parsed YAML document.

    Returns:
        Problems found (empty when valid).
    """
    problems: list[str] = []
    if config.get("kind") != "Cluster":
        problems.append("kind: must be 'Cluster'")
    if config.get("apiVersion") != KIND_API_VERSION:
        problems.append(f"apiVersion: must be {KIND_API_VERSION!r}")
    name = config.get("name")
    if name is not None and not is_dns_label(str(name)):
        problems.append(f"name: {name!r} must be lowercase letters, digits, and '-'")
    roles = node_roles(config)
    for i, role in enumerate(roles):
        if role not in ("control-plane", "worker"):
            problems.append(f"nodes[{i}].role: {role!r} must be 'control-plane' or 'worker'")
    if "control-plane" not in roles:
        problems.append("nodes: at least one control-plane node is required")
    host_ports: set[tuple[int, str]] = set()
    for i, node in enumerate(as_list(config.get("nodes"))):
        for j, raw in enumerate(as_list(as_dict(node).get("extraPortMappings"))):
            entry = as_dict(raw)
            path = f"nodes[{i}].extraPortMappings[{j}]"
            for field in ("containerPort", "hostPort"):
                value = entry.get(field)
                if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= 65535:
                    problems.append(f"{path}.{field}: {value!r} must be an integer from 1 to 65535")
            protocol = str(entry.get("protocol", "TCP"))
            if protocol not in ("TCP", "UDP", "SCTP"):
                problems.append(f"{path}.protocol: {protocol!r} must be TCP, UDP, or SCTP")
            key = (entry.get("hostPort"), protocol)
            if isinstance(key[0], int):
                if key in host_ports:
                    problems.append(f"{path}.hostPort: {key[0]} is already mapped; a host port can be used once")
                host_ports.add((key[0], protocol))
    return problems
