# Tasks: citation fact-checker

- [x] Write ADR-025; add it to `specs/architecture-decisions/README.md`'s index; update ADR-023's status line.
- [x] Write `spec.md`/`plan.md`/`tasks.md` (this file).
- [x] `agent/citation_grounding.py`: add `Evidence`, `evidence_from_get_sign_payload`, `evidence_from_query_sign_payload`, `evidence_from_segments_payload`, `evidence_from_tool_messages`; remove `uncited_valid_ids`.
- [x] `agent/citations.py`: widen `_MARKER_PATTERN`/`_STRIP_PATTERN` with `UNSUPPORTED`; add `grounding_score`.
- [x] `agent/fact_check.py` (new): `run_fact_check`.
- [x] `agent/prompts.py`: trim `SYSTEM_PROMPT`; delete the two pushback renderers; add `render_fact_check_prompt`.
- [x] `agent/graph/nodes/fact_check.py` (new): `fact_check_node`.
- [x] Delete `agent/graph/nodes/citation_check.py`.
- [x] `agent/graph/nodes/llm.py`: retarget `route_after_agent`'s final-answer branch.
- [x] `agent/graph/builder.py`: swap `validate_citations` wiring for `fact_check` (signature, node, edges).
- [x] `agent/graph/state.py`: remove `citation_retry_count`.
- [x] `agent/runner.py`: drop `citation_retry_count` from the initial state dict.
- [x] `core/config.py`: remove `citation_max_retries`; add `fact_check_model`.
- [x] `api/dependencies.py::get_agent_graph`: build and wire `fact_check_chat_client`.
- [x] `turn_service.py`: removed the now-dead `validate_citations_node`-exhausted-retries branch (nothing produces `CITATION_FAILURE_MESSAGE` at that point anymore); backstop check otherwise unchanged.
- [x] `tests/unit/graph_helpers.py::compile_graph`: update signature/default (`PassthroughChatClient`).
- [x] `tests/unit/test_agent_citations.py`: extend for `UNSUPPORTED`/`grounding_score`.
- [x] `tests/unit/test_agent_citation_grounding.py`: extend for `evidence_from_*`.
- [x] `tests/unit/test_agent_fact_check.py` (new): `run_fact_check` pure-function tests.
- [x] `tests/unit/test_agent_graph_nodes_fact_check.py` (new): node-level tests.
- [x] `tests/unit/test_agent_graph_nodes_llm.py`, `test_agent_turn_service.py`: removed the five retry-loop-specific tests (mechanism deleted); updated the rest.
- [x] `tests/unit/test_api_dependencies.py`: updated for the second derived (or separately constructed) fact-check model role; added coverage for a distinct `fact_check_model`.
- [x] `tests/integration/test_agent_grounding_ids.py`: retargeted at the fact-check node's output. Initially via a marker-based assertion, then rewritten to `_assert_reply_was_fact_checked` (footer-based): under the finalized design `fact_check_node` never persists the tagged text (with its `[G...]`/`[S...]`/`[UNSUPPORTED]` markers) anywhere — it builds its reply from the original answer plus a score footer, never the tagged text — so no marker ever reaches a stored or displayed message to inspect; the `facts checked: NN%` footer is the only externally observable pass/fail signal left.
- [x] `docs/agent-graph.md`: updated diagram, node table, §5, bounds table, turn-state table, related ADRs.
- [x] `docs/architecture.md`: updated the two references to "the citation-retry loop".
- [x] `ruff check . && ruff format --check .` over changed files — clean.
- [x] Run `pytest api/tests/unit` — 588 passed.
- [x] `api/dependencies.py::get_agent_graph`: fact-check role's `ChatOllama` derived with `reasoning=False`, regardless of whether it shares the agent's model or is a distinct `fact_check_model` — real-model testing found qwen3's default "thinking" pass made this narrow tagging-only call both slower and less reliable at obeying the additive-only instruction (ADR-025); a no-op for a model with no such mode. `tests/integration/test_agent_grounding_ids.py`'s `graph` fixture mirrors it. Covered by `test_the_fact_check_role_disables_thinking_mode` and the updated `test_a_distinct_fact_check_model_gets_its_own_construction` in `tests/unit/test_api_dependencies.py`.
- [x] Run `pytest api/tests/integration -m requires_ollama` against a local `qwen3:1.7b` daemon: baseline (thinking on) 3/7 passed. After `reasoning=False`: 5/7, then 6/7 across two separate full runs — consistent improvement, no regressions. Remaining failures are a known, narrow gap; see the new item below rather than re-running further.
- [x] `_normalize` (agent/graph/nodes/fact_check.py) didn't tolerate markdown list/whitespace restructuring — the fact-checker's tag pass on longer, bulleted `query_sign` answers occasionally reformatted list structure while tagging, failing the no-reword check and silently dropping the score footer (safe fallback: no corrupted text, just no score shown). Repro: `test_query_sign_reply_is_fact_checked_with_real_opaque_segment_ids_when_asked_to_cite` / `test_query_sign_reply_is_fact_checked_with_real_opaque_segment_ids_unprompted` (`tests/integration/test_agent_grounding_ids.py`), ~1-in-7 real-model runs. Fix, revised beyond the original plan of widening the comparison tolerance: normalize the *input*, not just the comparison. `citations.py` gains `flatten_for_fact_check` (strips markdown decoration and leading list/numbering markers, collapses to one plain paragraph) applied to the answer *before* it is sent to the fact-checker at all, and `normalize_for_comparison` (whitespace-only — the sole remaining drift once both sides are already flattened) for the no-reword check itself. Removes the model's opportunity to mangle formatting rather than tolerating it after the fact — the fact-checker's task is now a smaller, mechanical "insert tags into this plain text," never "faithfully reproduce this markdown/list layout while also inserting tags." Still not a fuzzy similarity threshold: a genuine word-level edit (e.g. dropping "not") still fails the check, since flattening never touches word content. Covered by `test_agent_citations.py` (`flatten_for_fact_check`/`normalize_for_comparison` unit tests) and `test_agent_graph_nodes_fact_check.py::test_the_answer_is_flattened_before_it_reaches_the_fact_checker_prompt`. Real-model re-verification against `tests/integration/test_agent_grounding_ids.py` still outstanding — see below.
- [x] Re-ran `pytest api/tests/integration -m requires_ollama` (the 3 previously-failing cases, `--log-cli-level=DEBUG`) against a local `qwen3:1.7b` daemon: 3/3 still failed, but none reproduced the list/bullet-reformatting scenario `flatten_for_fact_check` targets — real-model output is stochastic and this run's answers happened to be plain prose, not bulleted lists. The before/after debug logging (added to `fact_check_node`, kept permanently — see below) showed the actual causes instead: (1) `get_sign_unprompted` — the fact-checker appended a whole extra sentence not in the original (`"...Let me know if you'd like further details."`); (2) `query_sign_when_asked_to_cite` — the fact-checker *deleted* an entire clause (`"Citations: The Pictorial Key to the Tarot, p. 143."`) and replaced it with a bare `[Gceeb9e]` tag; (3) `query_sign_unprompted` — unrelated flake, the primary model called `get_sign` with `tradition: ''`, got a tool error, and never called `query_sign`, so there was no evidence to fact-check at all (not a fact-check node issue). (1) and (2) are genuine content edits, correctly rejected by the no-reword check exactly as designed — not a regression, and not evidence the flatten fix is wrong, just that this run didn't exercise the bug it was written for. They do reconfirm the still-open item below is real and unresolved.
- [x] `agent/graph/nodes/fact_check.py::fact_check_node`: on a no-reword discard, the warning log also carries the exact flattened answer sent and the tagged output received. Originally added at `DEBUG` level, then promoted to `WARNING` (folded into the one existing discard log call) after discovering `core/logging_config.py::configure_logging` runs the whole app at `INFO` by design — a `DEBUG` call there is silently dropped in production regardless of code version, so it never actually surfaced in a real deployment's logs. `WARNING` matches the level the discard notice itself already logs at, so the detail is visible with no server config change.
- [x] `api/dependencies.py`: pinned `temperature=0.0` for the fact-check role's model (same `derive_chat_model` call as `reasoning=False`) — the role is a mechanical copy-and-tag pass, not a generative one, so sampling variance only cost reliability. Re-ran the real-`qwen3:1.7b` grounding-ids suite twice after this: first run 4/5 passed (the two previously-diagnosed content-drop/addition cases both now score 100%), second run 4/5 passed again with a fresh instance of the same still-open, already-tracked failure category. Covered by `test_the_fact_check_role_pins_temperature_to_zero` in `tests/unit/test_api_dependencies.py`.
- [x] `tests/integration/test_agent_grounding_ids.py::_grounding_ids`: fixed to skip a tool message whose content is a plain-text invocation error (`json.JSONDecodeError`) instead of crashing — found via the real-model run above, when the primary model malformed a tool call's args, got an error, and successfully retried; unrelated to the fact-check node itself.
- [x] Regression test added for a second real production reply ("explain the passages in simple words", 2026-08-04): a numbered list with bolded headers and markdown hard line breaks (trailing double-space before each newline). Verified `flatten_for_fact_check` on the literal text from that log collapses it to clean plain prose (no `1.`, `**`, or `\n` survive) — `test_flatten_handles_a_numbered_list_with_trailing_markdown_line_breaks` (`test_agent_citations.py`) and `test_a_bolded_numbered_list_with_markdown_line_breaks_is_flattened_and_scored` (`test_agent_graph_nodes_fact_check.py`, node-level, `fetch_segments` evidence). Since the production log's `answer` text reproduces cleanly through the current `flatten_for_fact_check`, the discard in that log most likely came from a server process still running code from before this session's fix (not restarted) — the WARNING log line's wording is unchanged between old and new code, so the log alone can't distinguish the two; ask the user to confirm after restarting the API process, and enable DEBUG logging (now permanent on `fact_check_node`) if it recurs.
- [x] A third real production case (2026-08-04 23:24:43, "explain current passages in simple words"): the WARNING-with-detail logging above showed the actual diff for the first time — the flattened input sent to the fact-checker was already clean plain prose (`flatten_for_fact_check` working correctly), but the tagged output *duplicated* a whole clause ("Age: Abraham was 100, Sarah 90, yet God's promise came true.") and reordered surrounding sentences. Confirmed this is a real content edit, correctly caught and discarded by the no-reword check — not a flatten/normalize bug.
- [x] Decided (superseding the "keep or revert the anti-substitution instruction" item): rather than tune the existing prompt further, dropped `question` entirely from `render_fact_check_prompt`/`run_fact_check`'s signatures and the node's call site (it carried no information any instruction used, and the "User's question:\n...\nAnswer to annotate:\n..." framing plausibly invited chat-continuation behavior — re-answering, closing remarks, reordering — matching the exact failure shapes seen across all three real production cases: an added sentence, a deleted clause replaced by a bare tag, and now a duplicated+reordered clause). Rewrote the prompt to a plain text-annotation framing (`Text:` / `Evidence:`, per the user's explicit ordering — text before evidence), dropped the redundant triple restatement of "don't rewrite" down to one line, and removed the `"(denotation)"` worked example. User-approved before implementation per CLAUDE.md. `spec.md` FR-FC-02/FR-FC-04/FR-FC-11 updated, new FR-FC-12 added for the flatten-before-send behavior. `597 passed` after the change; `ruff` clean.
- [x] Real-model re-verification of the simplified, question-free prompt (`Text:`/`Evidence:`, closing "Return only the text above..."): 3/5 passed. All 3 failures shared one new, *consistent* (not sporadic) pattern: the model appended the entire `Evidence:` block verbatim — every `[id] Source — locator: "text"` item — onto the end of its tagged output. Root cause: once `Evidence:` sits directly before the closing instruction, `"the text above"` is ambiguous between "the Answer section" and "everything above this line, including Evidence" — the old prompt never had this ambiguity (it said "the *answer* text", and Evidence never sat adjacent to the closing line). A real regression from the reordering, not a pre-existing issue.
- [x] Fix (user-approved): renamed the annotated section from `Text:` to `Answer:` — considered `Statement:` too but rejected it for colliding with "a sentence that states a claim" (the sub-unit language the instructions already use); `Answer` has no such collision and is unambiguous against `Evidence`. Closing instruction rewritten to name the section explicitly and explicitly exclude `Evidence`: `"Return only the Answer section above with tags inserted. Do not include the Evidence section, or any part of it, in your output."` `597 passed`; `ruff` clean.
- [x] Real-model re-verification of the `Answer:`-labeled prompt: **4/5 passed**, and the evidence-echo pattern was gone entirely (0 occurrences in the full log) — confirms the fix. The one remaining failure is the same already-tracked, still-open category: the model appended one brand-new invented sentence not in the original answer ("...where it represents positive energy and spiritual awakening." + an added "The Sun symbolizes joy [G2d7321]."), correctly caught and discarded by the no-reword check.

## Revision (2026-08-05): sentence-indexed JSON classification

Directed after the tag-and-reproduce design above kept finding new
reproduction-drift failure shapes despite every fix. See ADR-025's Revision
section and `plan.md`'s Revision section for the design; tasks below are
this revision's own checklist, independent of the (historical, unmodified)
checklist above.

- [x] Amend ADR-025 in place (uncommitted, not yet an accepted decision) —
  Decision/Consequences/Alternatives rewritten for the JSON-classification
  design, new Revision section added.
- [x] Update `spec.md` (FR-FC-02/03/04/07/08/09/11 rewritten, FR-FC-12
  removed, non-goals extended) and `plan.md` (Revision section appended).
- [x] `agent/fact_check.py`: add `split_sentences`, `SentenceVerdict`,
  `_parse_verdicts`/`_safe_json_loads`; change `run_fact_check`'s signature
  to take `sentences` and return `tuple[SentenceVerdict, ...] | None`; move
  `grounding_score` here with the stricter valid-citation rule.
- [x] `agent/prompts.py`: rewrite `render_fact_check_prompt` for the
  sentence-indexed JSON schema (id+text evidence only, no source/locator —
  confirmed with the user).
- [x] `agent/citations.py`: drop `UNSUPPORTED` from `_MARKER_PATTERN`/
  `_STRIP_PATTERN`; remove the text-based `grounding_score`,
  `flatten_for_fact_check`, `normalize_for_comparison`.
- [x] `agent/graph/nodes/fact_check.py`: rewritten — `split_sentences` →
  `run_fact_check` → `grounding_score`, no flatten step, no no-reword
  comparison.
- [x] `api/dependencies.py`: fact-check role's derived model gains
  `format="json"` (confirmed with the user); `_FACT_CHECK_NUM_PREDICT`
  lowered `2048` → `512`.
- [x] `tests/unit/test_agent_fact_check.py`: rewritten for `split_sentences`
  and JSON parsing (clean, fenced, prose-wrapped, malformed, missing
  `results`, out-of-range index, non-boolean `supported`, duplicate index)
  plus `grounding_score`'s stricter rule.
- [x] `tests/unit/test_agent_citations.py`: trimmed back to the
  pre-ADR-025 marker vocabulary and cases.
- [x] `tests/unit/test_agent_graph_nodes_fact_check.py`: rewritten against
  JSON-response fakes; no-reword-specific test replaced with an
  unparseable-response test.
- [x] `tests/unit/graph_helpers.py::PassthroughChatClient`: docstring
  updated (fallback is now a JSON parse failure, not a no-reword mismatch;
  behavior itself unchanged).
- [x] `ruff check . && ruff format --check .` and `pytest api/tests/unit` — clean, 605 passed.
- [x] Real-model verification against a local daemon
  (`MYTHRIX_GENERATION_MODEL=qwen3:1.7b`, `MYTHRIX_FACT_CHECK_MODEL=phi4-mini:latest`,
  via an adapted scratchpad script mirroring `api/dependencies.py`'s actual
  role-construction logic — `test_agent_grounding_ids.py`'s own `graph`
  fixture always derives the fact-check role from the agent's own model,
  so it can't exercise a genuinely distinct `fact_check_model`): 5/5
  scenarios got a `facts checked: NN%` footer — every JSON classification
  parsed successfully, no call failures or unparseable responses.
- [x] `docs/agent-graph.md`: updated for the sentence-classification design
  (§5's `fact_check` description, node table, turn-state table);
  `docs/architecture.md` had no stale wording to fix.
- [x] `tests/integration/test_agent_grounding_ids.py`: mirrored
  `format="json"`/lowered `num_predict` in the `graph` fixture; updated
  stale tag/no-reword docstrings for the classification design.

## Fix: sentence-splitting fragmented markdown lists (2026-08-05)

Real production log (`explain the fragments in simple words`) surfaced a
bug in the redesign's own `split_sentences`: a naive `.`/`!`/`?` boundary
regex treated the period in a markdown numbered-list marker (`1.`, `2.`) as
a sentence end on its own, producing a garbage fragment like `"Key points:
\n1."` sent to the fact-checker as if it were a real sentence — the same
list-formatting problem the *old*, since-deleted `flatten_for_fact_check`
used to solve, which turned out not to be reproduction-only after all.

- [x] `agent/fact_check.py::split_sentences`: rewritten to strip a leading
  list marker (`-`, `*`, `+`, `•`, `1.`, `2)`, ...) and markdown decoration
  per line, and to split *each line independently* rather than joining
  lines into one paragraph first — a line break is itself a sentence
  boundary now, so a header line with no terminal punctuation (e.g. `"Key
  points:"`) survives as its own sentence instead of fusing with the next
  line's first clause. Verified against the exact real-model example
  (user-provided expected split) before landing.
- [x] `tests/unit/test_agent_fact_check.py`: added list-marker-stripping,
  line-boundary, and numbered-list-fragmentation regression cases.
- [x] `agent/fact_check.py::run_fact_check`: added `INFO`-level logging of
  the full rendered prompt and the model's response (pretty-printed JSON
  when parseable, `_pretty`/`_extract_json`, not a `%r`-escaped single
  line) — the parsed verdicts alone didn't show what the model was actually
  asked to classify, needed to diagnose the bug above from production logs
  in the first place.
- [x] `agent/graph/nodes/fact_check.py`: added `_log_verdicts`, one `INFO`
  line per classified sentence (index, supported/unsupported, citations,
  sentence text) — the aggregate `grounding_score` alone didn't explain a
  surprising low score.
- [x] Fixed an unrelated one-line corruption in `fact_check_node` (the
  footer literal had become `"\n> facts checked: ..."` instead of
  `"\n---\nfacts checked: ..."` during this session's editing — isolated to
  that one line, confirmed via `grep` across the repo). The existing
  integration test's footer regex (`\nfacts checked: (\d+)%$`) doesn't
  anchor on `---`, so it didn't catch this; a unit test's exact-string
  assertion did.

## Fix: prompt was too strict about literal wording (2026-08-05)

Real-model testing (`phi4-mini`) after the split fix still produced
low scores (e.g. `grounding_score=0.33`) on answers that read as
well-grounded — the prompt's "fully supported by the Evidence" framing
punished faithful paraphrase/summary as if it were fabrication, not just
genuine hallucination.

- [x] `agent/prompts.py::render_fact_check_prompt`: rewritten (user-directed
  and user-authored wording, approved per CLAUDE.md) — reframed as
  "hallucination detector" rather than literal-wording fact-checker;
  explicitly accepts faithful summaries/reasonable paraphrases as
  supported; reserves `unsupported` for a sentence that introduces new
  factual information, an interpretation stated as fact, or a conclusion
  the evidence does not reasonably support.
- [x] Real-model re-verification of the reframed prompt against
  `qwen3:1.7b`/`phi4-mini:latest`: 5/5 scenarios still got a footer
  (structural success unaffected), but this run's raw logged prompt/response
  (new `INFO` logging above) surfaced a second, distinct bug — see below —
  rather than confirming the leniency fix alone; re-verified again after
  that fix (see "Fix: completeness contract" below).

## Fix: sentence-boundary regex fragmented a citation abbreviation (2026-08-05)

The new prompt/response logging (above) caught a second real splitting bug
in the same production-log family: `"(p. 143)"` split into `"...(p."` and
`"143), where it is..."` — the period in `p.` read as a sentence end because
it happened to be followed by whitespace, exactly like any other terminal
punctuation. The resulting fragment carried no claim of its own, and the
real model (`phi4-mini`) simply left it out of `results` rather than
erroring — silently undercounting the answer's actual claims, and the
likely cause of an earlier-observed "missing sentence" symptom that
predated this fix.

- [x] `agent/fact_check.py::_SENTENCE_BOUNDARY`: added a negative lookahead
  excluding a digit immediately after the boundary
  (`(?<=[.!?])\s+(?!\d)`) — covers `"p."`, `"pp."`, `"No."`, `"Vol."`,
  `"Fig."`, and any other short citation abbreviation the same way, without
  naming any of them individually. Verified against the exact real-model
  example before landing; the trade-off (a genuine sentence starting with a
  digit merges into the previous one instead of splitting) is accepted as
  rare and lower-cost than fragmenting.
- [x] `tests/unit/test_agent_fact_check.py`: added a page-citation
  regression case and a plain-boundary sanity check.

## Fix: completeness contract — force one result per sentence (2026-08-05)

Directed after the logging above showed the model silently omitting an
index from `results` rather than misclassifying it — not just for
fragments the splitting bugs produced, but potentially for any sentence the
model found awkward, since the original schema's "omit sentences with no
factual claims" instruction gave it an easy excuse to do so for *any*
sentence, not only a genuine non-claim one.

- [x] `agent/prompts.py::render_fact_check_prompt`: rewritten (user-authored
  contract, approved per CLAUDE.md) — states the exact sentence count and
  requires exactly that many results, in order, each with `"index": i`
  matching its position. Replaces the omit-if-no-claim convention with an
  explicit `"claim": false` value per sentence, so "no factual claim" is now
  something the model must positively state for every index rather than a
  silent non-appearance it could default into for any sentence.
- [x] `agent/fact_check.py::_parse_verdicts`: parses the new `claim` field
  — `"claim": false` skips the entry (contributes no verdict, same as an
  absent index always did); a missing `claim` field defaults to treating
  the entry as a claim, so a pre-contract response shape still parses.
  Tolerance for a genuinely missing index is unchanged — the contract is a
  stronger instruction to the model, not a hard requirement the parser
  enforces, consistent with never fully trusting model compliance.
- [x] `tests/unit/test_agent_fact_check.py`: added cases for the prompt's
  completeness wording, an explicit `"claim": false` skip, and a
  missing-`claim`-field backward-compatibility case.
- [x] Real-model re-verification of the completeness contract against
  `qwen3:1.7b`/`phi4-mini:latest`: 5/5 scenarios passed. Confirmed directly
  from the logged raw JSON (`explain-passages`, 9 sentences): the model
  returned all 9 entries, with `"claim": false` explicitly set on every
  non-claim sentence (headers/transitions, indices 0/3/5/8) instead of
  omitting them — no more silent gaps. The `"(p. 143)"` abbreviation case
  also confirmed fixed: it now stays one sentence instead of fragmenting.
