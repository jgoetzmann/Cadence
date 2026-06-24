"""Prevent multiple Cadence processes from sharing one bot token."""

from __future__ import annotations

import socket

__all__ = ["InstanceLockError", "acquire_instance_lock"]

_INSTANCE_PORT = 47123


class InstanceLockError(Exception):
    """Raised when another Cadence process already holds the lock."""


def acquire_instance_lock() -> socket.socket:
    """Bind a localhost port for the lifetime of this process."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(("127.0.0.1", _INSTANCE_PORT))
    except OSError as exc:
        sock.close()
        msg = (
            "Another Cadence instance is already running. "
            "Stop it before starting a new one."
        )
        raise InstanceLockError(msg) from exc
    return sock
