// SPDX-FileCopyrightText: 2026 Guido Marelli
// SPDX-License-Identifier: AGPL-3.0-or-later

// Wire types mirror the region-centric query response shape `routes.py`/
// `query_regions` emit (`core/models.py::RegionQueryResult`,
// `.model_dump(mode="json")`) — denormalized: every region carries its own
// `source` inline. `Hotspot`/`HotspotSegment`/`HotspotMatch` are this app's
// view-model names for `Region`/`Segment`/`Match` (existing component
// vocabulary — `HotspotCard`/`HotspotList`); `client.ts` is the single seam
// that maps the wire shape onto them. See
// specs/retrieval/ranking.md.

export interface Tradition {
  id: string;
  slug: string;
  name: string;
  domain: string;
  description: string;
}

export interface Source {
  id: string;
  domain: string;
  citation_label: string;
  title: string;
  author: string;
  publication_year: number | null;
  license: string;
  uri: string;
  description: string;
  content_hash: string;
  ingested_at: string | null;
  // Names the segmenter this source's chunks came from (e.g.
  // 'scripture_verse', 'numbered_section', 'chapter_section') — empty for a
  // source with no declared structure. Used by `HotspotDetailPanel` to tell
  // a self-describing segment (a verse or numbered section, already fully
  // named by its own `locator`) apart from a `chapter_section` segment,
  // whose leading/trailing edge may or may not be the source's own edge.
  structure_scheme: string;
}

export interface SignSummary {
  slug: string;
  canonical_name: string;
  sign_type: string;
  semiotic_system: string;
  tradition_slugs: string[];
}

export interface SourceFacet {
  id: string;
  label: string;
  count: number;
}

export interface InterpretantFacet {
  value: string;
  count: number;
}

export interface Facets {
  sources: SourceFacet[];
  interpretants: InterpretantFacet[];
}

// --- Wire shape (as `/api/query` sends it) ---

export interface RegionSegment {
  ordinal: number;
  locator: string;
  text: string;
  section: string;
}

export interface RegionMatch {
  interpretant: string;
  kind: 'concept' | 'exact' | 'filter';
  score: number;
  exact_value: boolean;
  segment_ordinal: number;
}

export interface Region {
  region_id: string;
  source: Source;
  locator: string;
  score: number;
  convergence_count: number;
  segments: RegionSegment[];
  matches: RegionMatch[];
}

export interface RegionQueryResult {
  facets: Facets;
  regions: Region[];
}

// --- View model (as the UI consumes it — see client.ts) ---

export interface HotspotSegment {
  ordinal: number;
  locator: string;
  text: string;
  section: string;
}

export interface HotspotMatch {
  interpretant: string;
  kind: 'concept' | 'exact' | 'filter';
  score: number;
  exactValue: boolean;
  segmentOrdinal: number;
}

export interface Hotspot {
  regionId: string;
  source: Source;
  locator: string;
  score: number;
  convergenceCount: number;
  segments: HotspotSegment[];
  matches: HotspotMatch[];
}

export interface HotspotQueryResult {
  facets: Facets;
  hotspots: Hotspot[];
}

// --- Hotspot context expansion ---
// Wire/view-model pair for `GET /api/regions/extend` — the server-side
// boundary logic behind the detail panel's Add Context action. Unlike
// `Region`/`Hotspot`, this is not a ranked retrieval hit: no score,
// convergence count, or matches, just a wider verbatim read plus whether
// each edge has already reached its bound.

export interface ExtendedRegionWire {
  region_id: string;
  locator: string;
  segments: RegionSegment[];
  leading_bounded: boolean;
  trailing_bounded: boolean;
}

export interface ExtendedRegion {
  regionId: string;
  locator: string;
  segments: HotspotSegment[];
  leadingBounded: boolean;
  trailingBounded: boolean;
}

// A widened hotspot context, as lifted up to tab-level state so it survives
// navigating away and back to that hotspot.
// `null` clears it (nothing grew past the hotspot's own original span, or the
// user explicitly cleared it via "Clear Context"). Carries the full displayed
// state, not just the coordinate/locator sent to the agent, so returning to a
// hotspot restores exactly what was on screen rather than only its original
// segments. Identical in shape to `ExtendedRegion` — a distinct alias only so
// call sites read as "the currently active one for this hotspot, or none".
export type ExtendedRegionRef = ExtendedRegion | null;

// --- Agent chat (specs/interfaces/agent.md FR-AG-14–FR-AG-22) ---
// Wire shapes mirror `api/routes.py`'s `AgentContext`/`AgentTurnRequest`/
// `AgentTurnResponse` — snake_case, as
// `.model_dump(mode="json")` sends them. `client.ts` is the single seam
// translating them onto the camelCase view-model types below.

export interface AgentContextWire {
  semiotic_system: string | null;
  sign: string | null;
  tradition: string | null;
  interpretant: string | null;
  min_score: number | null;
  region_id: string | null;
  locator: string | null;
  // The active hotspot's widened structural coordinate/citation, once Add
  // Context has grown it — null whenever the user hasn't widened the active
  // hotspot's context. Additive
  // to `region_id`/`locator`, never a replacement: those remain the
  // hotspot's own identity.
  extended_region_id: string | null;
  extended_locator: string | null;
}

export interface AgentTurnRequestWire {
  session_id: string;
  message: string;
  ui_selection: AgentContextWire;
  // The regions the viewer is currently displaying, in display order
  // (specs/interfaces/augmentation.md FR-AU-12) — a sibling of `ui_selection`,
  // not a field on it: this changes on every keystroke in the hotspot search
  // box, and a changed `ui_selection` is what resets the thread.
  visible_regions: string[];
}

// An agent instruction (specs/interfaces/agnostic-query.md FR-AQ-07,
// FR-AQ-13–14): `type` names the action, `payload` carries whatever it needs,
// and neither carries transport detail. How a type is executed comes from the
// capabilities document, not from here.
//
// `type` is deliberately an open `string`, not a union of the types this build
// knows: the backend is the authority on what exists, so a type this frontend
// has never heard of has to be *representable* in order to be reported rather
// than executed (FR-CAP-13). A closed union would make that case unwritable
// and push the mismatch to runtime, where nothing checks it.
export interface AgentInstructionWire {
  type: string;
  payload: Record<string, unknown>;
}

// --- Agent capabilities (specs/interfaces/agent-capabilities.md) ---
// The backend declares the command vocabulary and how each instruction type is
// executed; this app implements handlers per `result` kind, never per
// instruction type (FR-CAP-11), so a new type reusing a known kind needs no
// change here. Every method in `SafeMethod` is safe and idempotent, which is
// what makes a declared binding unable to express a write (FR-CAP-16).

export type SafeMethod = 'GET' | 'QUERY';
export type BodyMode = 'payload';
export type ResultKind = 'regions';

export interface InstructionBindingWire {
  method: string;
  path: string;
  body: string;
  result: string;
}

export interface CommandSpecWire {
  name: string;
  args: string | null;
  summary: string;
  handled_by: 'server' | 'client';
  listed: boolean;
}

export interface InstructionSpecWire {
  type: string;
  binding: InstructionBindingWire | null;
}

export interface AgentCapabilitiesWire {
  commands: CommandSpecWire[];
  instructions: InstructionSpecWire[];
}

export interface CommandSpec {
  name: string;
  args: string | null;
  summary: string;
  handledBy: 'server' | 'client';
  listed: boolean;
}

// Narrowed at the client seam (`toCapabilities`): a binding only reaches this
// shape if its method, path, body mode, and result kind all passed FR-CAP-09/10,
// so anything holding one may treat it as executable.
export interface InstructionBinding {
  method: SafeMethod;
  path: string;
  body: BodyMode;
  result: ResultKind;
}

export interface AgentCapabilities {
  commands: CommandSpec[];
  // A declared type with no binding maps to `null` — handled in-app, no request
  // (FR-CAP-07). An absent key is an undeclared type, which is an error
  // (FR-CAP-13); the two are deliberately distinguishable.
  bindings: Record<string, InstructionBinding | null>;
}

// A turn is a sequence of events ending in exactly one `turn` event
// (augmentation.md FR-AU-22, ADR-015), so a run that takes minutes can report
// progress as it goes. An ordinary turn is the terminal event alone.
export interface AgentTurnResponseWire {
  event: 'turn';
  context: AgentContextWire;
  reply_text: string;
  instructions: AgentInstructionWire[];
  thread_reset: boolean;
}

export interface AgentMessageEventWire {
  event: 'message';
  text: string;
}

export interface AgentInstructionEventWire {
  event: 'instruction';
  instruction: AgentInstructionWire;
}

export type AgentTurnEventWire = AgentMessageEventWire | AgentInstructionEventWire | AgentTurnResponseWire;

// --- View model (as the UI consumes it — see client.ts) ---

export interface AgentContext {
  semioticSystem: string | null;
  sign: string | null;
  tradition: string | null;
  interpretant: string | null;
  minScore: number | null;
  regionId: string | null;
  locator: string | null;
  extendedRegionId: string | null;
  extendedLocator: string | null;
}

export type AgentInstruction = AgentInstructionWire;

export interface AgentTurnResult {
  context: AgentContext;
  replyText: string;
  instructions: AgentInstruction[];
  threadReset: boolean;
}

// One region's generated reading, held against the region it names for as
// long as that region is displayed (augmentation.md FR-AU-26). `label` is the
// `[R#]` marker the consolidation cites it by.
export interface Augmentation {
  label: string;
  text: string;
}
