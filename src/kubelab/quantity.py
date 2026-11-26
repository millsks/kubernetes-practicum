"""Parse Kubernetes resource quantities such as ``250m`` CPU and ``128Mi`` memory."""

import re

_QUANTITY = re.compile(r"^([+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)([a-zA-Z]*)$")
_BINARY = {"Ki": 2**10, "Mi": 2**20, "Gi": 2**30, "Ti": 2**40, "Pi": 2**50, "Ei": 2**60}
_DECIMAL = {"": 1, "n": 1e-9, "u": 1e-6, "m": 1e-3, "k": 1e3, "M": 1e6, "G": 1e9, "T": 1e12, "P": 1e15, "E": 1e18}


class QuantityError(ValueError):
    """Raised for a value that is not a valid Kubernetes quantity."""


def parse_quantity(value: str | int | float) -> float:
    """Parse any quantity into a plain number in base units.

    ``1Gi`` (binary suffix) is 1073741824, ``1G`` (decimal) is 1000000000, ``250m`` is 0.25.

    Args:
        value: A quantity string, or a number (YAML often gives ``cpu: 1`` as an int).

    Returns:
        The value as a float.

    Raises:
        QuantityError: If the value is not a valid quantity.
    """
    if isinstance(value, bool):
        raise QuantityError(f"{value!r} is not a quantity")
    if isinstance(value, int | float):
        return float(value)
    match = _QUANTITY.match(str(value).strip())
    if not match:
        raise QuantityError(f"{value!r} is not a quantity")
    number, suffix = float(match.group(1)), match.group(2)
    if suffix in _BINARY:
        return number * _BINARY[suffix]
    if suffix in _DECIMAL:
        return number * _DECIMAL[suffix]
    raise QuantityError(f"{value!r} has an unknown suffix {suffix!r}")


def parse_cpu(value: str | int | float) -> float:
    """Parse a CPU quantity into cores: ``"500m"`` → 0.5, ``2`` → 2.0.

    Args:
        value: CPU quantity.

    Returns:
        Cores as a float.

    Raises:
        QuantityError: If the value is invalid or negative.
    """
    cores = parse_quantity(value)
    if cores < 0:
        raise QuantityError(f"CPU {value!r} is negative")
    return cores


def parse_memory(value: str | int | float) -> int:
    """Parse a memory quantity into bytes: ``"128Mi"`` → 134217728, ``"1G"`` → 1000000000.

    Args:
        value: Memory quantity.

    Returns:
        Bytes as an int (rounded up, as the kubelet does).

    Raises:
        QuantityError: If the value is invalid or negative.
    """
    amount = parse_quantity(value)
    if amount < 0:
        raise QuantityError(f"memory {value!r} is negative")
    whole = int(amount)
    return whole if whole == amount else whole + 1
