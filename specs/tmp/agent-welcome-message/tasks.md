# Tasks: Agent welcome/help message

1. [x] Add `WelcomeMessage` component to `web/src/components/AgentChatPanel.tsx`:
   greeting, listed-commands list wired to `onAccept`, guarded on
   `capabilities` being non-null (FR-AG-47).
2. [x] Wire the render site: in `.thread`, render `<WelcomeMessage>` when
   `items.length === 0`.
3. [x] Add `.welcome-command-*` CSS rules to `web/src/index.css`, on the
   app's existing `--agent-*` tokens.
4. [x] Manually verify in the running app: new tab shows the greeting +
   listed commands; clicking a command fills the composer without sending;
   sending a message hides the welcome message; `/clear` brings it back;
   missing-capabilities degrades to greeting-only.
5. [x] Add FR-AG-45–FR-AG-47 to `specs/interfaces/agent.md`'s "Chat panel"
   section.
6. [x] Restyle per `mythrix-redesign.html`: stacked command cards instead of
   the inline `CommandLabel` row, on the current palette. Fixed the
   `.msg.ai` grid-track/`.bubble` overflow-wrap bug this exposed.
7. [x] Remove the contextual proposition chip (`/summarize` /
   `/query`) — not part of the mock, dropped per user decision. Updated
   `spec.md`/`plan.md`/`agent.md` and tests accordingly.
8. [ ] Update `docs/TODO.md` if this item is tracked there (it currently
   isn't — confirm before adding).
