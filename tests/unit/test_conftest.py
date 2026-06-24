"""Verify shared conftest exports."""

from __future__ import annotations

from tests import conftest


def test_conftest_reexports_run_after() -> None:
    assert conftest.run_after is not None
    assert "run_after" in conftest.__all__
