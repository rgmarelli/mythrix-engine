# Plan: Agent welcome/help message

## Architecture

Entirely within `web/src/components/AgentChatPanel.tsx` and its stylesheet.
No API client change, no `useTabs` change — `items.length === 0` is already
observable where the thread renders, and `capabilities` is already a prop of
this component.

## Approach

1. **`WelcomeMessage` component**, local to `AgentChatPanel.tsx`, alongside
   the existing small components (`AgentMark`, `ConfirmActions`, etc.). Props:
   `capabilities: AgentCapabilities | null`, `onAccept: (name: string) =>
   void`.

2. **Render site**: in the `.thread` div, replace the current
   `items.map(...)` block's output with a conditional — when `items.length
   === 0`, render `<WelcomeMessage .../>` instead of mapping (the `isSending`
   spinner block after it is unaffected; it can't be true with an empty
   thread since sending appends a user item first).

3. **Greeting text**: static copy, one or two lines, no per-hotspot
   templating.

4. **Command list**: `capabilities?.commands.filter(c => c.listed)`, each
   rendered as its own stacked card — command name+args on one line, summary
   on the next — matching `mythrix-redesign.html`'s `.command-row` structure.
   This replaced an earlier inline `code + summary` row (reusing the shared
   `CommandLabel` component the composer's own palette uses): that layout put
   two independently-wrapping flex children on one line, and a long argument
   syntax (`/query term[:exact|:filter], …`) overflowed the dock. One block
   per line has nothing to fight over. Each card is a `<button>` calling
   `onAccept(command.name)`, wired to the same `accept()` function the
   palette already uses (`editInput(`${name} `)`) — one implementation of
   "accept a command name," not two.

5. **Degrade path**: when `capabilities` is `null`, `WelcomeMessage` renders
   only the greeting `<p>` — the command list is simply not rendered
   (`capabilities &&` guard), no separate branch needed.

6. **Styling**: `.welcome-command-list`/`.welcome-command-row`/
   `.welcome-command-name`/`.welcome-command-desc` rules near the existing
   `.thread`/`.msg` rules in the shell stylesheet, on the app's own
   `--agent-*` tokens (not `mythrix-redesign.html`'s own `--violet`/`--gold`
   tokens — the mock was a visual reference for layout, not a palette swap).
   Also fixed a pre-existing overflow bug this surfaced: `.msg.ai`'s grid
   track was `1fr` with no `minmax`, so an unconstrained fr track sizes to
   its content's max-content width instead of shrinking to wrap — changed to
   `minmax(0, 1fr)`, plus `overflow-wrap: anywhere` on `.bubble`. This is a
   general fix (every AI message benefits), not welcome-message-specific.

## Trade-offs

- Keeping this as one component inside `AgentChatPanel.tsx` (vs. a new file)
  matches the file's existing convention of small, local, non-exported
  helper components for this exact panel — there's no reuse case yet that
  would justify extraction.
- No contextual "next action" chip (e.g. `/summarize` when a hotspot is
  selected). One was built and then removed: it wasn't in the
  `mythrix-redesign.html` mock this message's visuals now follow, and the
  user confirmed dropping it rather than keeping/restyling it.

## Affected files

- `web/src/components/AgentChatPanel.tsx` — `WelcomeMessage` component,
  render-site change.
- `web/src/index.css` — `.welcome-command-*` rules; `.msg.ai` grid-track and
  `.bubble` overflow-wrap fix.
- `specs/interfaces/agent.md` — FR-AG-45–FR-AG-47 in the "Chat panel"
  section (done).
