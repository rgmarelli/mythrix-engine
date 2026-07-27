# Markdown Rendering in Agent Chat

Extends the docked [Conversational Agent](../../interfaces/agent.md) chat panel.

## Problem

The agent's generation model produces replies that may contain markdown syntax (lists, emphasis, inline code, links). The backend API currently strips markdown decoration (bold, headings, bullets) from the reply text before it reaches the client, and the chat panel renders every message as plain text — so any markdown syntax that survives is shown as literal characters (e.g. `**bold**`, `- item`) rather than formatted output, making structured replies harder to read.

## Goals

- The backend API no longer strips markdown decoration from the agent's reply text — it returns the model's reply as generated.
- Assistant-authored message text in the chat panel is rendered with markdown formatting instead of as raw text.
- Rendering cannot execute or inject raw HTML sourced from the model's reply.

## Non-Goals

- Markdown parsing or formatting of user-authored messages, error messages, or reset dividers — these continue to render as plain text.
- A rich-text or markdown-assisted composer for authoring outgoing messages.
- Syntax highlighting within fenced code blocks.
- Rendering of non-markdown content such as LaTeX/math or diagram syntax.
- Any change to the structured chips/citations populated from tool results ([agent.md](../../interfaces/agent.md) FR-AG-19) — those remain backend-populated and are unaffected by this feature.

## Functional Requirements

- FR-AG-23: Each assistant-authored message's text is rendered with markdown formatting: at minimum, paragraphs, emphasis (bold/italic), ordered and unordered lists, inline code spans, fenced code blocks, and links are visually formatted rather than shown as literal syntax.
- FR-AG-24: Markdown rendering never executes script content or renders raw HTML tags present in the model's reply text; such content is escaped or stripped, not rendered as markup.
- FR-AG-25: User-authored messages, error messages, and reset dividers are unaffected by this feature and continue to render as plain text.
- FR-AG-26: The backend API's agent chat response returns the model's reply text without stripping markdown decoration (bold, headings, bullets); citation-marker stripping and validation are unaffected and continue to apply.
