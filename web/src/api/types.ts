// Wire types mirror the region-centric query response shape `routes.py`/
// `query_regions` emit (`core/models.py::RegionQueryResult`,
// `.model_dump(mode="json")`) — denormalized: every region carries its own
// `source` inline. `Hotspot`/`HotspotSegment`/`HotspotMatch` are this app's
// view-model names for `Region`/`Segment`/`Match` (existing component
// vocabulary — `HotspotCard`/`HotspotList`); `client.ts` is the single seam
// that maps the wire shape onto them. See
// specs/convergence-rollup-retrieval/plan.md.

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
  kind: 'concept' | 'exact';
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
  kind: 'concept' | 'exact';
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

// --- Agent chat (specs/in-app-agent-chat) ---
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
    | { interpretant: string; kind: 'concept' | 'exact'; score: number; segment_ordinal: number }[]
    | null;
}

export interface AgentTurnResponseWire {
  context: AgentContextWire;
  reply_text: string;
  cards: AgentCardWire[];
  instructions: unknown[];
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
  chips: { interpretant: string; kind: 'concept' | 'exact'; score: number; segmentOrdinal: number }[];
}

export type AgentCard = AgentCitationCard | AgentInterpretantChipsCard;

export interface AgentTurnResult {
  context: AgentContext;
  replyText: string;
  cards: AgentCard[];
  threadReset: boolean;
}
