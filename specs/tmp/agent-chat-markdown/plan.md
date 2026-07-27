# Plan: Markdown Rendering in Agent Chat

Ground truth: [`spec.md`](spec.md). Two affected layers: the backend API's reply-cleanup step (`api/src/mythrix/agent/`) and the frontend chat panel (`web/src/components/AgentChatPanel.tsx`).

## Backend: stop stripping markdown (FR-AG-26)

Currently `run_chat_turn` (`api/src/mythrix/agent/turn_service.py:208`) builds the response with:

```python
reply_text=strip_markdown(strip_markers(visible_reply)),
```

`strip_markdown` (`api/src/mythrix/agent/notes.py:16-24`) is a regex-based pass that removes `**bold**`, `#`-headings, and `- `/`* ` bullet markers — added specifically because the UI rendered `reply_text` as plain text (per the module's own docstring, `notes.py:1-5`). That reason no longer holds once the frontend renders markdown, so this pass is removed outright rather than kept dormant:

- `turn_service.py:208`: change to `reply_text=strip_markers(visible_reply)` (drop the `strip_markdown(...)` wrapper).
- `turn_service.py:26`: drop the now-unused `from mythrix.agent.notes import strip_markdown` import.
- Delete `api/src/mythrix/agent/notes.py` and its test `api/tests/unit/test_agent_notes.py` — `strip_markdown` has no other caller, so the module becomes dead code, not a reusable utility worth keeping around.
- `strip_markers` (from `mythrix.core.synthesis.citations`) is untouched — it strips citation-marker syntax (a distinct, unrelated concern from markdown decoration) and keeps applying before the reply leaves the function, preserving FR-AG-06's citation-validation behavior.
- No system-prompt change: the Explore pass found no actual "avoid markdown" instruction in `agent/prompts.py`'s `SYSTEM_PROMPT` to remove — only the post-hoc regex pass existed. Nothing to add either; the model is free to use markdown or not, and the frontend now handles either case.

## Frontend: render it (FR-AG-23–FR-AG-25)

Render only `kind: 'ai'` message text (`AgentChatPanel.tsx:156`) through a markdown-to-React renderer. Leave `kind: 'user'` (line 138), `kind: 'reset'` (line 143), and `kind: 'error'` (line 149) exactly as plain-text interpolation — this satisfies FR-AG-25 by construction rather than by a separate check.

## Dependency

Add `react-markdown` (+ `remark-gfm` for tables/strikethrough/autolinks, matching the level of formatting implied by FR-AG-23) to `web/package.json`. `react-markdown` renders to React elements directly — it never uses `dangerouslySetInnerHTML` and does not parse embedded raw HTML into live DOM by default, which satisfies FR-AG-24 with no extra sanitizer dependency. No `rehype-raw` (the plugin that would re-enable raw HTML passthrough) is added, and none should be, since that's precisely the behavior FR-AG-24 rules out.

## Changes

- **`AgentChatPanel.tsx:153-159`** (the `kind: 'ai'` branch): replace `<div className="bubble">{item.text}</div>` with `<div className="bubble"><ReactMarkdown remarkPlugins={[remarkGfm]}>{item.text}</ReactMarkdown></div>`.
- **`web/src/index.css:1128-1134`** (`.agent-dock .bubble`): `white-space: pre-wrap` is currently what preserves line breaks for plain text. Once AI text is rendered as real block elements (`<p>`, `<ul>`, `<pre>`), that rule fights markdown's own block spacing. Scope `white-space: pre-wrap` to `.agent-dock .msg.user .bubble` only, and add rendering rules for the AI bubble's markdown children — paragraph margins, list indent/markers, `code`/`pre` monospace + background, and link color — sized to match the panel's existing 13.5px/1.55-line-height type scale and using the existing `--agent-*` custom properties for color, not new tokens.
- **No change** to `AgentCards` (lines 48-71), `ThreadItem`, or any `/api/*` route shape (`AgentTurnResponse.reply_text` stays a `str`) — only the *content* of `reply_text` changes (unstripped), not its type or the route contract.

## Trade-offs considered

- **`react-markdown` vs. `marked`/`markdown-it` + manual injection**: the latter would need `dangerouslySetInnerHTML` plus a sanitizer (e.g. DOMPurify) to safely satisfy FR-AG-24, adding a second dependency and a manual-escaping surface to get wrong. `react-markdown` gets the no-raw-HTML guarantee from its default AST-to-React rendering, at the cost of being a slightly heavier dependency — acceptable since bundle size isn't a stated constraint here.
- **Streaming/incremental markdown parsing**: out of scope — `item.text` for an `ai` item already arrives complete in one piece (no token-streaming into the thread today), so the renderer only ever needs to parse a finished string.

## Testing

- **Backend**: remove `api/tests/unit/test_agent_notes.py` (its subject is deleted). Checked `test_agent_turn_service.py` and `test_api.py`'s existing `reply_text`/`body["reply_text"]` assertions (lines 72-73, 185-186, 204-205, 234, and 419-420, 468-469) — none assert on stripped markdown decoration specifically (they check citation-marker absence and plain content), so none need updating; citation-marker-stripping behavior is unaffected by this change.
- **Frontend**: extend `AgentChatPanel.test.tsx`: an `ai` item whose `text` contains markdown (e.g. a list and bold text) renders formatted elements (`<ul>`/`<li>`, `<strong>`), not literal `**`/`-` characters; an `ai` item whose `text` contains an HTML-like string (e.g. `<img onerror=...>`) renders it as inert text, not a live element; `user`/`error`/`reset` items are unchanged (still render their literal text, unaffected by the new renderer).
