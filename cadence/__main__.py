"""Entry point for `python -m cadence`."""

from __future__ import annotations

from cadence.app import build_app
from cadence.config import ConfigError, Settings


def main() -> None:
    try:
        settings = Settings.load()
    except ConfigError as exc:
        raise SystemExit(str(exc)) from exc
    build_app(settings).run(settings.token)


if __name__ == "__main__":
    main()
