"""Acceptance traceability — T3-08."""

from __future__ import annotations

import ast
import re
from pathlib import Path

REQUIRED_STORIES = frozenset({f"US-{index}" for index in range(1, 9)})
US_PATTERN = re.compile(r"US-\d+")


def _collect_story_ids_from_docstrings(module_path: Path) -> set[str]:
    source = module_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            docstring = ast.get_docstring(node)
            if docstring is None:
                continue
            found.update(US_PATTERN.findall(docstring))
    return found


def test_t3_08_all_user_stories_referenced_in_acceptance_tests() -> None:
    """T3-08: every US-# user story is referenced by at least one acceptance test."""
    integration_dir = Path(__file__).resolve().parent
    acceptance_modules = sorted(integration_dir.glob("test_acceptance_*.py"))
    assert acceptance_modules, "expected at least one test_acceptance_*.py module"

    found: set[str] = set()
    for module_path in acceptance_modules:
        if module_path.name == "test_acceptance_traceability.py":
            continue
        found.update(_collect_story_ids_from_docstrings(module_path))

    missing = REQUIRED_STORIES - found
    assert not missing, f"acceptance tests missing user story references: {sorted(missing)}"
