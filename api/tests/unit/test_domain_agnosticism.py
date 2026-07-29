# SPDX-FileCopyrightText: 2026 Guido Marelli
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Domain-agnosticism guardrail (CON-SYS-01, T23): `src/mythrix/core` and
`src/mythrix/cli` must never contain a domain-specific literal in actual code —
domain content belongs only in `data/` and `tests/fixtures/`.

Docstrings and comments are stripped before checking, since explaining *why*
something is domain-agnostic legitimately requires naming example domains
(e.g. "a tarot card related to a Kabbalah symbol" appears throughout this
codebase's own rationale comments) — the guardrail's job is to catch a
domain-specific field, class, or branch of logic actually entering `core`/`cli`,
not to forbid the word "tarot" from ever appearing in a comment.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

SRC_ROOT = Path(__file__).parent.parent.parent / "src" / "mythrix"
CORE_ROOT = SRC_ROOT / "core"
CLI_ROOT = SRC_ROOT / "cli"

DENY_LIST = (
    "tarot",
    "card",
    "kabbalah",
    "qabalah",
    "sephirah",
    "sephiroth",
    "sefirot",
    "arcana",
    "hebrew",
    "golden dawn",
    "waite",
    "crowley",
    "partzuf",
    "atzilut",
    "beriah",
    "ietzirah",
    "asiah",
    "samekh",
    "tiphareth",
    "yesod",
    "the fool",
    "the tower",
)


def _strip_docstrings_and_comments(path: Path) -> str:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))

    for node in ast.walk(tree):
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            docstring = ast.get_docstring(node, clean=False)
            if docstring:
                source = source.replace(docstring, "", 1)

    return "\n".join(line.split("#", 1)[0] for line in source.splitlines())


def _python_files(root: Path) -> list[Path]:
    return sorted(root.rglob("*.py"))


ALL_FILES = _python_files(CORE_ROOT) + _python_files(CLI_ROOT)


@pytest.mark.parametrize("path", ALL_FILES, ids=lambda p: str(p.relative_to(SRC_ROOT)))
def test_no_domain_specific_literals_in_code(path: Path) -> None:
    code = _strip_docstrings_and_comments(path).lower()
    matches = [term for term in DENY_LIST if re.search(rf"\b{re.escape(term)}\b", code)]
    assert not matches, f"{path}: domain-specific literal(s) found outside docstrings/comments: {matches}"


def test_deny_list_actually_catches_a_planted_violation(tmp_path: Path) -> None:
    """Sanity check for the guardrail itself: plant a real domain literal in
    code (not a comment) and confirm the check would have caught it."""
    planted = tmp_path / "planted.py"
    planted.write_text('SYMBOL_TYPE = "tarot-card"\n', encoding="utf-8")

    code = _strip_docstrings_and_comments(planted).lower()
    matches = [term for term in DENY_LIST if re.search(rf"\b{re.escape(term)}\b", code)]

    assert matches
