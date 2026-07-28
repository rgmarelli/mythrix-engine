# ADR-011 — The backend declares the agent's command vocabulary and how its instructions are executed

- **Status**: Accepted
- **Date**: 2026-07-28
- **Realized by**: [agent-capabilities.md](../interfaces/agent-capabilities.md) (new); [agnostic-query.md](../interfaces/agnostic-query.md) FR-AQ-14 (amended); [web-viewer.md](../interfaces/web-viewer.md) (amended)
- **Amends**: [ADR-010](adr-010-agnostic-adhoc-interpretant-query.md), whose hand-off left the `type`→endpoint mapping to the consumer

## Context

Two related things currently have no single owner.

**The command vocabulary is scattered across three modules and one browser
file, with no one able to enumerate it.** `/clear` is implemented in the
composer and never reaches the backend at all (FR-AG-22); `/summarize` lives in
`turn_service.py`; `/query` and `/query-confirm` live in `agent/adhoc_query.py`.
Nothing can answer "what commands exist?", so any help text, palette, or
autocomplete in the composer must restate the list, and that copy drifts the
moment a command is added, renamed, or removed. The failure is silent in both
directions: a command the browser doesn't list is invisible to users, and a
command the browser lists after the backend drops it fails with a
non-explanation.

**The execution binding for an instruction was left to the consumer.**
[ADR-010](adr-010-agnostic-adhoc-interpretant-query.md) had the confirmed turn
emit a transport-agnostic `execute_query` instruction and made mapping its
`type` to `POST /api/query/adhoc` the browser's job, so that the agent would
know nothing about transport. The cost is that a capability whose behavior is
entirely backend-decided is nonetheless half-defined in a separate deploy unit:
the backend can decide *whether* to emit an instruction and *what* is in it,
but not *what happens* when one arrives.

The question is where the seam between "the backend decides" and "the browser
decides" belongs — not whether the browser needs code. It does either way: some
component must turn a response into rendered state.

## Decision

Add one endpoint, `GET /api/agent/capabilities`, fetched once per application
load, that declares both:

1. **The command registry.** Every command the product offers, each with its
   name, argument syntax, one-line summary, whether it is listed to users, and
   `handled_by`: `server` (send it as an ordinary turn) or `client` (the
   consumer implements it and must not send it). `/clear` is the sole `client`
   command and the reason the field exists.
2. **The execution binding per instruction type.** For each `type` the backend
   can emit, how to execute it — including HTTP method and path — or `null`
   where a type is handled entirely inside the consumer.

The binding is **composed from closed vocabularies, not a template language**.
A binding names a `method`, a `path`, a `body` mode saying how to derive the
request body from the instruction's `payload`, and a `result` kind naming how
to interpret the response. Consumers implement a handler per `result` kind, not
per instruction type — so a new instruction type that reuses an existing kind
costs no consumer change at all. This is the part that makes the manifest
carry real authority rather than restating a constant: `execute_query` binds to
`{POST, /api/query/adhoc, body: payload, result: regions}`, and a later
instruction reusing `result: regions` is live the moment the backend declares
it.

Because a declared path drives a real HTTP call, the manifest is **bounded, not
free-form**: a `path` is a same-origin absolute path, and a `method` comes from
a fixed set — `{GET, QUERY}`, **every member safe and idempotent**
([RFC 10008](https://www.rfc-editor.org/rfc/rfc10008.html)). A consumer rejects
anything else rather than dialing it. The manifest configures which of the
API's own read endpoints an instruction reaches; it is not a general-purpose
request description, and no declaration it can carry causes a write.

Ad-hoc query execution is therefore `QUERY /api/query/adhoc`, not `POST`. The
request carries content because a term list with directives is structured, not
because anything is being created or modified — which is precisely the case
RFC 10008 defines QUERY for. The distinction is load-bearing rather than
cosmetic here: the method is now *published* to every consumer as part of a
contract, so declaring `POST` would assert "this may change state, do not retry
blindly" about an operation that is a pure read. It would also forfeit the
safe-methods-only invariant above, since a vocabulary containing POST can
express a state-changing binding.

`GET /api/agent/capabilities` is a static description of the running build. It
reads no session, takes no parameters, varies per deployment rather than per
user, and stays independent of ADR-010's per-turn `instructions` — which
continue to carry `{type, payload}` and no transport detail of their own.

## Consequences

- Adding, renaming, or retiring a command becomes a backend-only change for
  discovery, help text, and routing. A command whose entire effect is a reply
  needs no consumer change whatsoever.
- The `type`→endpoint mapping stops being a constant maintained in a second
  deploy unit, which removes a class of silent version skew: an instruction the
  consumer cannot execute is now *detectably* unbound rather than quietly
  unhandled.
- Instructions themselves stay transport-agnostic, so ADR-010's hand-off shape
  is unchanged. What moved is *who states the mapping* — the backend, in one
  place, once per load — not what an instruction contains.
- The consumer gains a generic execution step: it issues a request the server
  named. This is a real widening of what the browser will do on the server's
  say-so, but a narrow one — the safe-methods-only vocabulary means the widening
  is "the browser will perform a read the server names", not "a request the
  server names". Within a same-origin API the residual risk is that a bug in the
  manifest points a capability at the wrong *read* of the same API: a functional
  bug, not an escalation, and one that cannot corrupt state.
- Choosing QUERY costs the endpoint its entry in the generated API docs for now:
  FastAPI emits an OpenAPI 3.1 document, and `query` as a path-item key is only
  valid from OpenAPI 3.2. The route, its validation, and its tests are
  unaffected — verified against this repo's FastAPI/Starlette — and nothing in
  the repository consumes the OpenAPI document. The cost resolves when FastAPI
  emits 3.2.
- QUERY is not a "simple" method for CORS, so the browser preflights it and the
  API's `allow_methods` must name it. A same-origin production build never
  preflights; the dev server, which is cross-origin, always will.
- Configurability is genuine but not unlimited: a `result` kind the consumer
  has no handler for cannot be introduced by declaration alone. The manifest
  buys free reuse of existing kinds, not free introduction of new ones. This
  is a bound worth stating plainly, because it is the difference between this
  decision and the illusion of one.
- One added startup dependency, and one staleness mode: a long-lived tab holds
  the manifest its load fetched, so a mid-session backend deploy can leave it
  describing the previous build. Bounded by the same fallback that covers a
  failed fetch — commands still send, replies still render, instruction
  execution is skipped with a visible notice.

## Alternatives considered

- **Keep the mapping in the consumer** (ADR-010 as written). Rejected on the
  user's explicit direction, having weighed it: the mapping's dynamism is
  bounded by the consumer needing a handler per result kind regardless, so the
  narrow reading is that a manifest only relocates a constant. The `result`-kind
  vocabulary is what settles it — with handlers keyed on kinds rather than
  types, the backend really can introduce a capability without a browser
  deploy, which the consumer-owned mapping cannot do at any price.
- **Let the confirmed turn run retrieval and return results inline**, removing
  instructions and the manifest together. Rejected: it breaks FR-AQ-13's
  boundary (the agent turn touches neither store), makes agent-turn latency
  equal retrieval latency, and pushes full region payloads through the agent
  session — while FR-AQ-18's directly-callable endpoint would still be
  required.
- **Declare `POST /api/query/adhoc`** (the endpoint as first built). Rejected:
  the operation is a pure read whose content is a structured term list, so POST
  misstates it — and once the method is published in the manifest, that
  misstatement is contract, telling consumers a safe operation may not be
  retried. Keeping POST in the method vocabulary would additionally give up the
  safe-methods-only invariant.
- **A general request-template language in the manifest** (header maps, path
  interpolation, response field paths). Rejected: it re-implements an RPC
  framework in configuration, moves logic to a place with no type checking and
  no tests, and expands the trust boundary far past the closed
  method/path/body/result vocabularies actually needed.
- **Publish OpenAPI and have the consumer resolve bindings from it.** Rejected:
  it describes every endpoint's shape but says nothing about which capability
  reaches which endpoint, which is the entire question here.
