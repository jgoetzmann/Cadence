"""Tests for cadence.instance_lock."""

from __future__ import annotations

import socket
from unittest.mock import MagicMock, patch

import pytest

from cadence.instance_lock import InstanceLockError, acquire_instance_lock


def test_acquire_instance_lock_returns_bound_socket() -> None:
    mock_sock = MagicMock(spec=socket.socket)

    with patch("cadence.instance_lock.socket.socket", return_value=mock_sock):
        sock = acquire_instance_lock()

    assert sock is mock_sock
    mock_sock.bind.assert_called_once_with(("127.0.0.1", 47123))


def test_acquire_instance_lock_raises_when_port_taken() -> None:
    first = MagicMock(spec=socket.socket)
    second = MagicMock(spec=socket.socket)
    second.bind.side_effect = OSError("address in use")

    with patch("cadence.instance_lock.socket.socket", side_effect=[first, second]):
        acquire_instance_lock()
        with pytest.raises(InstanceLockError, match="Another Cadence instance"):
            acquire_instance_lock()

    second.close.assert_called_once()


def test_acquire_instance_lock_closes_socket_on_bind_failure() -> None:
    mock_sock = MagicMock()
    mock_sock.bind.side_effect = OSError("address in use")

    with (
        patch("cadence.instance_lock.socket.socket", return_value=mock_sock),
        pytest.raises(InstanceLockError),
    ):
        acquire_instance_lock()

    mock_sock.close.assert_called_once()
