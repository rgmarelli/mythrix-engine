# SPDX-FileCopyrightText: 2026 Guido Marelli
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Shared INFO-level, human-readable logging setup for the API process
(Agent Pipeline Logging and Query Endpoint Logging specs). `configure_logging()`
is called once, from `mythrix/api/app.py::create_app()`; every module's own
`logging.getLogger(__name__)` then inherits the configured handler and level.
Never called from the CLI, so CLI runs stay silent (no handler installed,
below the logging module's `WARNING` lastResort floor)."""

from __future__ import annotations

import logging

_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"


def configure_logging(level: int = logging.INFO) -> None:
    """Installs the shared format/level via `logging.basicConfig`, which only
    acts if the root logger has no handler yet — safe to call more than once
    (e.g. from both logging features' setup)."""
    logging.basicConfig(level=level, format=_FORMAT)


def truncate(text: str, limit: int = 5000) -> str:
    """Returns `text` unchanged at or under `limit` characters; otherwise the
    first `limit` characters plus a marker noting the full length. Pure
    string slicing — cannot raise on any `str` input."""
    if len(text) <= limit:
        return text
    return f"{text[:limit]}…[truncated, {len(text)} chars total]"
