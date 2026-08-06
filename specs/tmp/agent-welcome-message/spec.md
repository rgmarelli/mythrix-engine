# Spec: Agent welcome/help message

## Problem

A tab's agent thread starts empty (a new tab, or right after `/clear`) with
nothing in it but the context strip. A first-time user has no in-panel signal
of what the agent can do or how to start — they have to already know the
command vocabulary or type something exploratory.

## Goals

- When the active tab's thread has no items, the panel shows a short
  greeting and the vocabulary of listed commands.
- The command list stays truthful to the capabilities document — it is never
  a second, hand-maintained list of commands.
- The message disappears the moment the thread gains its first item, and
  reappears under the same empty condition after `/clear`.
- Degrades the same way the rest of the panel already does when the
  capabilities document failed to load (FR-CAP-14): a plain greeting, no
  command list.
- Visually: matches the card-per-command layout piloted in
  `mythrix-redesign.html` (name on its own line, description below), on the
  app's existing color tokens — not that mock's own palette.

## Non-goals

- No backend change. Nothing here adds a capabilities-document field, a new
  instruction type, or an LLM call — the message is assembled entirely from
  data the panel already holds (`capabilities`).
- No persistence of "seen/dismissed" state — the empty-thread condition is
  itself the trigger, exactly like FR-WEB-09's empty-tab state; there is no
  separate onboarding flag to track.
- Not a substitute for the in-composer command-palette affordance
  (FR-WEB-18) — this is a one-time, whole-thread state, not a per-keystroke
  one.
- No contextual "next action" proposition (e.g. suggesting `/summarize` when
  a hotspot is selected). Trialed and dropped: it wasn't part of the
  `mythrix-redesign.html` mock this message's visuals were aligned to, and
  the command list alone already covers that ground.

## Functional requirements

Numbered to extend `specs/interfaces/agent.md`'s "Chat panel" section
(FR-AG-14–FR-AG-36), which already covers this panel's web-UI-specific
behavior.

- FR-AG-45: When the active tab's thread holds no items, the panel renders a
  welcome message in place of the (otherwise empty) thread: a short greeting,
  followed by every command the capabilities document declares `listed: true`
  (FR-CAP-06), each shown with its argument syntax and summary. The message is
  replaced by the ordinary thread the moment the tab's `agentItems` gains its
  first item, and is shown again whenever that condition recurs (a new tab,
  or after `/clear`, FR-AG-22).
- FR-AG-46: Each listed command shown in the welcome message is clickable:
  selecting one fills the composer with that command's name and a trailing
  space, identically to accepting a completion from the in-composer command
  list (FR-WEB-22). It does not send the message.
- FR-AG-47: When the capabilities document is unavailable (FR-CAP-14), the
  welcome message shows only the greeting — no command list — consistent
  with how the rest of the panel already treats a missing capabilities
  document.

## Open questions

None — interactivity (clickable list), the visual restyle basis
(`mythrix-redesign.html`, current palette), and dropping the proposition chip
were all confirmed with the user before this revision.
