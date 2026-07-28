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

// --- Agent chat (specs/interfaces/agent.md FR-AG-14–FR-AG-22) ---
// Wire shapes mirror `api/routes.py`'s `AgentUiSelection`/`AgentTurnRequest`/
// `AgentContext`/`AgentCard`/`AgentTurnResponse` — snake_case, as
// `.model_dump(mode="json")` sends them. `client.ts` is the single seam
// translating them onto the camelCase view-model types below.

export interface AgentUiSelectionWire {
  semiotic_system: string | null;
  sign: string | null;
  tradition: string | null;
  source_id: string | null;
  interpretant: string | null;
  min_score: number | null;
  region_id: string | null;
  locator: string | null;
}

export interface AgentTurnRequestWire {
  session_id: string;
  message: string;
  ui_selection: AgentUiSelectionWire;
}

export type AgentContextWire = AgentUiSelectionWire;

export interface AgentCardWire {
  type: 'citation' | 'interpretant_chips';
  source_label?: string | null;
  locator?: string | null;
  text?: string | null;
  chips?:
    | { interpretant: string; kind: 'concept' | 'exact' | 'filter'; score: number; segment_ordinal: number }[]
    | null;
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

export interface AgentTurnResponseWire {
  context: AgentContextWire;
  reply_text: string;
  cards: AgentCardWire[];
  instructions: AgentInstructionWire[];
  thread_reset: boolean;
}

// --- View model (as the UI consumes it — see client.ts) ---

export interface AgentUiSelection {
  semioticSystem: string | null;
  sign: string | null;
  tradition: string | null;
  sourceId: string | null;
  interpretant: string | null;
  minScore: number | null;
  regionId: string | null;
  locator: string | null;
}

export type AgentContext = AgentUiSelection;

export interface AgentCitationCard {
  type: 'citation';
  sourceLabel: string;
  locator: string;
  text: string;
}

export interface AgentInterpretantChipsCard {
  type: 'interpretant_chips';
  chips: { interpretant: string; kind: 'concept' | 'exact' | 'filter'; score: number; segmentOrdinal: number }[];
}

export type AgentCard = AgentCitationCard | AgentInterpretantChipsCard;

export type AgentInstruction = AgentInstructionWire;

export interface AgentTurnResult {
  context: AgentContext;
  replyText: string;
  cards: AgentCard[];
  instructions: AgentInstruction[];
  threadReset: boolean;
}
