# SPDX-FileCopyrightText: 2026 Guido Marelli
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Post-hoc grounding for the model-driven conversational turn (ADR-025) —
reached from `route_after_agent` whenever `agent_node` produces a reply with
no further tool calls, replacing `validate_citations_node`'s in-graph retry
(ADR-023, superseded).

Deterministic in everything except the one model call it makes: this node
calls `agent/fact_check.py::run_fact_check`, but every decision about what
to do with the result — trust it, discard it, score it, append a footer —
is code, not another prompted judgment. The fact-checker never receives the
answer's own text at all (only numbered sentences and evidence, ADR-025's
JSON-classification design) and never returns any — so there is no
reproduction step for the reply the user sees to survive or fail. The reply
returned to the user is always the primary model's own original answer,
verbatim, with at most a score footer appended.

On success, every classified sentence's verdict is logged individually at
`INFO` (`_log_verdicts`) — the aggregate score alone doesn't say which
sentence was marked unsupported or why, and a low score on a plausible-
looking answer is otherwise undiagnosable without re-running against a
local daemon."""

from __future__ import annotations

import logging

from langchain_core.messages import AIMessage, ToolMessage

from mythrix.agent.citation_grounding import evidence_from_tool_messages
from mythrix.agent.fact_check import SentenceVerdict, grounding_score, is_grounded, run_fact_check, split_sentences
from mythrix.agent.graph.state import AgentState
from mythrix.core.chat import ChatClient

logger = logging.getLogger(__name__)


def fact_check_node(state: AgentState, chat_client: ChatClient) -> dict:
    """Scores the just-produced reply's grounding against this turn's own
    tool results — found via `turn_start_index`, fixed once per turn, the
    same scoping `validate_citations_node` used.

    A turn with no citable evidence this turn (no tool calls, or only
    enumeration tools with nothing to cite), or an answer with no sentences
    at all, is a no-op: the reply already on `state["messages"]` stands. On
    any other failure (the call itself, or a response that could not be
    parsed into any usable verdicts, or one that tagged no claims), the
    original answer is returned as-is, with no footer. Otherwise a
    `grounding_score` is computed from the parsed verdicts and appended as a
    plain-text footer to the original answer."""
    turn_start_index = state.get("turn_start_index", 0)
    tool_messages = [m for m in state["messages"][turn_start_index:] if isinstance(m, ToolMessage)]
    evidence = evidence_from_tool_messages(tool_messages)
    if not evidence:
        logger.info("fact-check: skipped — no citable evidence this turn (no tools called, or listing-only)")
        return {}

    answer = str(state["messages"][-1].content)
    sentences = split_sentences(answer)
    if not sentences:
        logger.info("fact-check: skipped — answer has no sentences to classify")
        return {}

    verdicts = run_fact_check(chat_client, evidence=evidence, sentences=sentences)
    if verdicts is None:
        logger.warning("fact-check: call failed or returned an unparseable response — showing the original answer")
        return {}

    valid_ids = {e.grounding_id for e in evidence}
    score = grounding_score(verdicts, valid_ids)
    if score is None:
        logger.info("fact-check: no score — nothing was classified as a claim")
        return {}

    logger.info("fact-check: succeeded — grounding_score=%.2f", score)
    _log_verdicts(verdicts, sentences, valid_ids)
    return {"messages": [AIMessage(content=f"{answer}\n---\nfacts checked: {score:.0%}")]}


def _log_verdicts(verdicts: tuple[SentenceVerdict, ...], sentences: tuple[str, ...], valid_ids: set[str]) -> None:
    """One line per classified sentence — at `INFO`, not `DEBUG`: this app's
    production logging runs at `INFO` (`core/logging_config.py`), so a
    `DEBUG` call here would never actually surface and a low score would
    stay unexplainable outside a local debugging session. Shows exactly what
    the fact-checker decided and why `is_grounded` agreed or disagreed, so a
    surprising score (e.g. `25%` on an answer that reads as well-grounded)
    can be diagnosed straight from a normal deployment's logs."""
    for verdict in verdicts:
        sentence = sentences[verdict.index]
        grounded = is_grounded(verdict, valid_ids)
        status = "supported" if grounded else "unsupported"
        reason = "" if verdict.supported == grounded else " (claimed supported, no valid citation)"
        logger.info(
            "fact-check:   [%d] %s%s citations=%s — %r",
            verdict.index,
            status,
            reason,
            list(verdict.citations),
            sentence,
        )
