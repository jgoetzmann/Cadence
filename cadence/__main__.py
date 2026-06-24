"""Entry point for `python -m cadence`."""

from __future__ import annotations

from cadence.app import build_app
from cadence.config import ConfigError, Settings
from cadence.instance_lock import InstanceLockError, acquire_instance_lock


def main() -> None:
    try:
        settings = Settings.load()
    except ConfigError as exc:
        raise SystemExit(str(exc)) from exc
    try:
        lock_socket = acquire_instance_lock()
    except InstanceLockError as exc:
        raise SystemExit(str(exc)) from exc
    _ = lock_socket  # held until process exit
    build_app(settings).run(settings.token)


if __name__ == "__main__":
    main()
