# Tasks: Markdown Rendering in Agent Chat

Derived from [`plan.md`](plan.md). Each task is independently verifiable; complete backend tasks before frontend ones so the panel is exercised against real (unstripped) reply text once wired up.

## Backend — stop stripping markdown (FR-AG-26)

- [ ] 1. In `api/src/mythrix/agent/turn_service.py:208`, change `reply_text=strip_markdown(strip_markers(visible_reply)),` to `reply_text=strip_markers(visible_reply),`.
- [ ] 2. Remove the now-unused `from mythrix.agent.notes import strip_markdown` import at `turn_service.py:26`.
- [ ] 3. Delete `api/src/mythrix/agent/notes.py`.
- [ ] 4. Delete `api/tests/unit/test_agent_notes.py`.
- [ ] 5. Run the backend test suite (`api/tests/unit/test_agent_turn_service.py`, `api/tests/unit/test_api.py`, and the full suite) and confirm it passes with no reference to `notes`/`strip_markdown` remaining (`grep -rn "strip_markdown\|agent.notes" api/`).
- [ ] 6. Run `ruff check .` / `ruff format .` over the `api/` changes.

## Frontend — dependency

- [ ] 7. Add `react-markdown` and `remark-gfm` to `web/package.json` dependencies and install.

## Frontend — render assistant messages as markdown (FR-AG-23–FR-AG-25)

- [ ] 8. In `AgentChatPanel.tsx`, import `ReactMarkdown` and `remarkGfm`.
- [ ] 9. In the `kind: 'ai'` branch (`AgentChatPanel.tsx:153-159`), replace `<div className="bubble">{item.text}</div>` with `<div className="bubble"><ReactMarkdown remarkPlugins={[remarkGfm]}>{item.text}</ReactMarkdown></div>`.
- [ ] 10. Confirm the `user` (line 138), `reset` (line 143), and `error` (line 149) branches are untouched — still plain-text interpolation.

## Frontend — styling

- [ ] 11. In `web/src/index.css`, move `white-space: pre-wrap` off `.agent-dock .bubble` (line ~1128-1134) and onto `.agent-dock .msg.user .bubble` only.
- [ ] 12. Add rules for markdown block children inside `.agent-dock .msg.ai .bubble` (paragraph spacing, list indent/markers, inline `code`/fenced `pre` monospace + background, link color), sized to the panel's existing 13.5px/1.55-line-height scale and using existing `--agent-*` custom properties — no new color tokens.

## Frontend — tests

- [ ] 13. In `AgentChatPanel.test.tsx`, add a case: an `ai` item whose `text` contains markdown (e.g. `**bold**` and a `- ` list) renders `<strong>`/`<ul>`/`<li>` elements, not literal syntax characters.
- [ ] 14. Add a case: an `ai` item whose `text` contains an HTML-like string (e.g. `<img onerror=alert(1)>`) renders as inert text — no live `<img>` element, no script execution.
- [ ] 15. Add/confirm a case: `user`, `error`, and `reset` items still render their literal text unchanged (regression guard for FR-AG-25).
- [ ] 16. Run `npm test` (Vitest) and `npm run lint` (oxlint) in `web/` and confirm both pass.

## Wrap-up

- [ ] 17. Fold FR-AG-23–FR-AG-26 from `spec.md` into `specs/interfaces/agent.md`'s "Chat panel" section (after FR-AG-22), and update the `FR-AG` range in `specs/spec.md`'s Requirements Index (§10) from `FR-AG-01–FR-AG-22` to `FR-AG-01–FR-AG-26`.
- [ ] 18. Confirm with the user that the feature is complete, then remove `specs/tmp/agent-chat-markdown/` (spec.md, plan.md, tasks.md) per the repo's SDD convention.
