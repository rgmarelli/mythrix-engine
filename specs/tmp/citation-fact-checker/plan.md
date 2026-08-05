# Plan: citation fact-checker

Realizes the spec via ADR-025's design. Full rationale/alternatives live in
ADR-025; this file is the concrete file-by-file mechanics.

## New modules

**`api/src/mythrix/agent/fact_check.py`** — graph/LangChain-agnostic core.

```python
@dataclass(frozen=True)
class Evidence:
    grounding_id: str
    source: str
    locator: str
    text: str

def run_fact_check(chat_client: ChatClient, *, evidence: list[Evidence], answer: str) -> str | None:
    ...
```

Renders `prompts.py::render_fact_check_prompt(tuple(evidence), answer)`,
calls `chat_client.invoke(prompt)`, catches `MythrixError` → `None` (same
pattern as `agent/tools/_shared.py::_generated`). No parsing beyond
`.strip()` — plain text in, plain text out, matching every existing
generative tool.

**`api/src/mythrix/agent/graph/nodes/fact_check.py`** — replaces
`agent/graph/nodes/citation_check.py` (deleted).

```python
def fact_check_node(state: AgentState, chat_client: ChatClient) -> dict:
```

Logic: gather this turn's `ToolMessage`s via `state["turn_start_index"]`;
`evidence = evidence_from_tool_messages(tool_messages)`; if empty, return
`{}` (FR-FC-05). Otherwise call `run_fact_check`; on `None` or on the
tag-stripped output not matching the original answer (FR-FC-04, via
`strip_all_markers` + whitespace normalization), log a warning and return
`{}` (FR-FC-06). Otherwise compute `citations.grounding_score(annotated,
valid_ids)`; if not `None`, append the `\n---\nfacts checked: NN%` footer
(FR-FC-07/09) to `annotated` before returning it as the new final
`AIMessage`; if `None`, return `annotated` as-is (FR-FC-08's stripping still
applies downstream, in `turn_service.py`, unchanged).

## Extended modules

**`api/src/mythrix/agent/citation_grounding.py`** — new evidence-reading
layer, alongside the existing `grounding_ids`/`only_listing_tools_called`:

- `evidence_from_get_sign_payload(payload: dict) -> list[Evidence]`
- `evidence_from_query_sign_payload(payload: dict) -> list[Evidence]`
- `evidence_from_segments_payload(payload: list) -> list[Evidence]`
- `evidence_from_tool_messages(tool_messages: list[ToolMessage]) -> list[Evidence]`
  — dispatches by `message.name` to the three above (FR-FC-11: only this
  one function knows about `ToolMessage`).

Remove `uncited_valid_ids` (only caller, `validate_citations_node`, is
deleted).

**`api/src/mythrix/agent/citations.py`**:

- `_MARKER_PATTERN` gains `|UNSUPPORTED` as a fifth alternative;
  `_STRIP_PATTERN` gains it too (stripped like `G`/`S`/`C`, unlike `R`).
- New `grounding_score(text: str, valid_ids: set[str]) -> float | None`
  (FR-FC-07): `extract_markers(text)`, count members of `valid_ids` as
  supported and literal `"UNSUPPORTED"` as unsupported, return
  `supported / (supported + unsupported)` or `None` if both are zero.
- `extract_markers`, `find_invalid_markers`, `strip_markers`,
  `strip_all_markers`, `CITATION_FAILURE_MESSAGE` are unchanged and keep
  their current callers (`turn_service.py`'s `/augment`-and-backstop path).

**`api/src/mythrix/agent/prompts.py`**:

- `SYSTEM_PROMPT` drops its citation-marker bullet (FR-FC-01).
- `render_citation_pushback`/`render_missing_citation_pushback` deleted (no
  caller once the retry loop is gone).
- New `render_fact_check_prompt(evidence: tuple[Evidence, ...], answer: str) -> str`.
  The original draft also took `question: str` and rendered a `"User's
  question:\n..."` section ahead of the evidence; dropped after real-model
  testing kept finding content duplicated/reordered/added while tagging —
  the Q&A framing plausibly invited chat-continuation behavior from a
  chat-tuned model rather than the narrow text-annotation task intended.
  `question` carried no information any instruction in the prompt used, so
  it was removed from the signature entirely rather than kept unused
  (FR-FC-02, FR-FC-11 updated in `spec.md` to match). Reordered to
  `Answer:` before `Evidence:` (previously `Answer to annotate:` came
  last). A first pass labeled this section `Text:` and closed with "Return
  only the text above with tags inserted"; real-model testing found that
  ambiguous enough (once `Evidence:` sat between `Text:` and the closing
  line) that qwen3:1.7b consistently echoed the whole evidence block back
  into its output. Renamed to `Answer:` (unambiguous against `Evidence:`,
  unlike `Text:` or the considered-and-rejected `Statement:`, which
  collides with "a sentence that states a claim") and the closing
  instruction now names the `Answer` section explicitly and explicitly
  excludes `Evidence`.

**`api/src/mythrix/agent/graph/nodes/llm.py`**: `route_after_agent`'s
final-answer branch returns `"fact_check"` instead of `"validate_citations"`.

**`api/src/mythrix/agent/graph/builder.py`**: `compile_agent_graph` drops
`citation_max_retries: int`, gains `fact_check_chat_client: ChatClient`.
Registers `fact_check` node and a direct edge to `END` (no conditional
routing back to `agent`).

**`api/src/mythrix/agent/graph/state.py`**: remove `citation_retry_count`.

**`api/src/mythrix/agent/runner.py`**: `stream_turn` drops
`"citation_retry_count": 0` from the initial state dict.

**`api/src/mythrix/core/config.py`**: remove `citation_max_retries`; add
`fact_check_model: str | None = None` (falls back to `agent_model`, then
`generation_model` — same resolution order `agent_model` itself uses).

**`api/src/mythrix/api/dependencies.py`**: `get_agent_graph` builds a third
`ChatClient` role — `derive_chat_model(llm, num_predict=...)` wrapped in
`OllamaChatClient` when `fact_check_model` is unset or equals the agent's
own model, otherwise a genuinely separate `create_chat_model(model=settings.fact_check_model, ...)`
— and passes it to `compile_agent_graph` as `fact_check_chat_client`.

## Deleted

- `api/src/mythrix/agent/graph/nodes/citation_check.py`
  (`validate_citations_node`, `route_after_citation_check`).
- `agent/prompts.py::render_citation_pushback`/`render_missing_citation_pushback`.
- `agent/citation_grounding.py::uncited_valid_ids`.
- `Settings.citation_max_retries`.

## Unaffected (explicitly verified, not just assumed)

- `turn_service.py` — no changes. `_ungrounded_markers`/`_build_valid_marker_ids`
  keep validating `/augment`'s `[R#]` markers (FR-FC-10) and continue to run
  redundantly on the conversational path's now-fact-checked reply, same as
  they did on `validate_citations_node`'s output before.
- `agent/graph/nodes/augment.py`, `agent/graph/nodes/summary.py` — untouched
  (out of scope; FR-FC-11 makes future adoption a call-site change only).

## Testing

See ADR-025/plan-mode document's Testing section for the full breakdown;
summary: new `test_agent_fact_check.py`, new
`test_agent_graph_nodes_fact_check.py`, extended `test_agent_citations.py`
and `test_agent_citation_grounding.py`, updated `graph_helpers.py`/
`test_agent_graph_builder.py` signatures, updated
`tests/integration/test_agent_grounding_ids.py` to inspect the fact-check
node's output instead of the primary model's raw output.

## Revision (2026-08-05): sentence-indexed JSON classification

Everything above this section describes the original mechanics — a
tag-and-reproduce design verified by a no-reword text comparison. It was
revised, before ever being committed, after six distinct real-`qwen3:1.7b`
failure shapes were found hardening that design (see ADR-025's Context and
Revision sections for the failure record). This section supersedes the
mechanics above; the original text is left in place as the record of what
was tried and why it changed, not deleted.

**What changed:**

- `agent/fact_check.py` gains `split_sentences(text: str) -> tuple[str, ...]`
  (deterministic, regex-based on `.`/`!`/`?` + whitespace) and
  `SentenceVerdict` (`index: int`, `supported: bool`, `citations: tuple[str, ...]`).
  `run_fact_check`'s signature changes to
  `(chat_client, *, evidence: list[Evidence], sentences: tuple[str, ...]) -> tuple[SentenceVerdict, ...] | None`
  — it now parses the model's JSON response into verdicts (tolerant of a
  markdown code fence or surrounding prose; skips an individual malformed
  entry rather than discarding the whole response) instead of returning
  text verbatim.
- `grounding_score` moves from `agent/citations.py` to `agent/fact_check.py`
  (different signature: `(verdicts: tuple[SentenceVerdict, ...], valid_ids: set[str]) -> float | None`).
  A verdict counts as supported only when `supported=True` *and* at least
  one of its citations is a real id — the boolean alone is not trusted.
- `agent/citations.py` reverts the `UNSUPPORTED` marker addition and drops
  `flatten_for_fact_check`/`normalize_for_comparison` (both unused once the
  fact-checker never touches the answer's text).
- `agent/graph/nodes/fact_check.py` drops the no-reword comparison entirely:
  it calls `split_sentences`, then `run_fact_check`, then `grounding_score`,
  and falls back to the original answer with no footer on any `None`.
- `agent/prompts.py::render_fact_check_prompt` signature changes to
  `(evidence: tuple[Evidence, ...], sentences: tuple[str, ...]) -> str`,
  rendering numbered sentences and an evidence block (id + text only, no
  source/locator) and instructing the model to return the JSON shape above.
- `api/dependencies.py`: the fact-check role's derived `ChatOllama` gains
  `format="json"` alongside `reasoning=False`; `_FACT_CHECK_NUM_PREDICT`
  drops from `2048` to `512` (a JSON classification is a few short lines
  regardless of answer length, unlike the old design's full-answer echo).

**What's unaffected:** `agent/citation_grounding.py`'s `Evidence`/
`evidence_from_*` extractors, the graph wiring (`builder.py`/`llm.py`/
`state.py`/`runner.py`), `core/config.py`'s `fact_check_model` setting, and
everything under "Unaffected" above.
