# Agent Capabilities

A single, backend-owned declaration of the chat commands the product offers and
how a consumer executes the instructions the agent emits
([agent.md](agent.md) FR-AG-19, [agnostic-query.md](agnostic-query.md)
FR-AQ-07, FR-AQ-13), scoped by
[ADR-011](../architecture-decisions/adr-011-backend-declared-agent-capabilities.md).

## Vocabulary

- **capabilities document**: The complete declaration served by the capabilities
  endpoint: a command registry and an instruction-binding registry.
- **command**: A chat message the composer treats as an instruction to the
  system rather than as conversation, identified by its leading token
  (e.g. `/clear`, `/query`).
- **execution binding**: The declaration of how one instruction type is
  executed — request method, path, how the request body derives from the
  instruction's payload, and how the response is interpreted.
- **result kind**: A named response interpretation (e.g. `regions`) that a
  consumer implements a handler for. Bindings reference result kinds; consumers
  implement result kinds, not instruction types.

## Functional requirements

### The capabilities document

- FR-CAP-01: A read-only endpoint serves the capabilities document. It takes no
  parameters, reads no session or user state, and returns the same document for
  every caller of a given running build.
- FR-CAP-02: The capabilities document declares the complete set of commands the
  build offers and the complete set of instruction types it can emit. No command
  and no instruction type exists outside it.
- FR-CAP-03: A consumer fetches the capabilities document once per application
  load. It is not refetched per turn.

### Command registry

- FR-CAP-04: Each declared command carries its name (including the leading `/`),
  its argument syntax or an indication that it takes none, a one-line summary,
  whether it is listed to users, and where it is handled.
- FR-CAP-05: A command declares `handled_by` as either `server` — the consumer
  sends it to the agent as an ordinary turn — or `client` — the consumer
  implements it locally and never sends it to the agent ([agent.md](agent.md)
  FR-AG-22).
- FR-CAP-06: A command declared unlisted is omitted from user-facing command
  listings and help, and is otherwise handled identically to a listed one. A
  command a consumer emits programmatically rather than one a user types is
  declared unlisted.

### Instruction bindings

- FR-CAP-07: Each declared instruction type carries either an execution binding
  or an explicit statement that it has none. An instruction type with no binding
  is handled entirely within the consumer and triggers no request.
- FR-CAP-08: An execution binding declares a request method, a request path, the
  mode by which the request body derives from the instruction's payload, and the
  result kind naming how the response is interpreted.
- FR-CAP-09: A binding's method comes from a fixed set of methods, every one of
  them safe and idempotent, and its path is a same-origin absolute path. A
  consumer rejects a binding whose method or path falls outside these bounds,
  without issuing a request, and reports the instruction as unexecutable.
- FR-CAP-10: A binding's body mode and result kind each come from a fixed,
  declared vocabulary. A binding naming a body mode or result kind the consumer
  does not implement is reported as unexecutable, without issuing a request.
- FR-CAP-11: A consumer dispatches a response by the binding's result kind, not
  by the instruction's type. Two instruction types declaring the same result
  kind are rendered by the same consumer handling.
- FR-CAP-12: The `payload` body mode sends the instruction's payload, unmodified,
  as the request body. The payload of an instruction whose binding names this
  mode is a valid request body for the bound endpoint.

### Consumer behavior

- FR-CAP-13: A consumer executes an instruction only through its declared
  binding. An instruction whose type is absent from the capabilities document is
  ignored and reported as unrecognized; it is never executed by inference from
  its type or payload.
- FR-CAP-14: When the capabilities document cannot be retrieved, the consumer
  degrades rather than failing: ordinary turns are still sent and replies still
  rendered, user-facing command listings are unavailable, and any instruction
  received is reported as unexecutable rather than acted on.
- FR-CAP-15: A client-handled command's local behavior does not depend on the
  capabilities document being retrieved. The document governs whether such a
  command is listed and whether it is routed to the agent, not whether the
  consumer implements it.
- FR-CAP-16: Executing an instruction never changes server state. Because every
  method a binding may name is safe, a declared binding cannot direct a consumer
  to perform a state-changing request, and a consumer may retry a failed
  execution without regard to partial effects.

## Non-goals

- Per-user, per-session, or per-tab variation in the capabilities document — it
  describes the running build, not a caller's entitlements.
- Any request detail beyond method, path, body mode, and result kind: no header
  declarations, no path interpolation, no query-parameter templating, no
  response field paths. A binding selects among the API's own endpoints; it does
  not describe arbitrary requests.
- Cross-origin or absolute-URL bindings, and bindings naming an unsafe method (FR-CAP-09, FR-CAP-16).
- Introducing a new result kind by declaration alone — a result kind requires
  consumer handling to exist (ADR-011).
- Refetching or invalidating the document mid-session in response to a backend
  deployment.
- Serving the agent's tool set ([agent.md](agent.md) FR-AG-03), system prompt, or
  model configuration. Tools are selected by the model, never by a consumer, and
  are not commands.
