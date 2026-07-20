// Mirrors the SSE event payload shapes `stream_query`/`routes.py` emit
// (`core/models.py`'s Pydantic models, `.model_dump(mode="json")`) —
// denormalized: every passage carries its own `source` inline, no id-based
// lookup table (see specs/query-viewer-web-ui/plan.md's "Streaming design").

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

export interface Property {
  id: string;
  key: string;
  value: string;
  position: number;
}

export interface QueryDirective {
  directive: string;
  as_token: string;
}

export interface Interpretant {
  id: string;
  type: string;
  value: string;
  position: number;
  query: QueryDirective | null;
}

export interface Citation {
  source: Source;
  locator: string;
}

export interface IntersemioticInterpretant {
  relationship: string;
  target_sign: Sign;
  according_to: Tradition;
  description: string;
  symmetric: boolean;
  confidence: string;
  target_interpretants: Interpretant[];
  citation: Citation | null;
}

export interface Sign {
  id: string;
  slug: string;
  canonical_name: string;
  sign_type: string;
  semiotic_system: string;
  notes: string;
  properties: Property[];
  intersemiotic_interpretants: IntersemioticInterpretant[];
}

export interface Manifestation {
  id: string;
  sign_id: string;
  tradition: Tradition;
  display_name: string;
  denotation: string;
  properties: Property[];
  interpretants: Interpretant[];
  citations: Citation[];
  created_at: string;
}

export interface GraphFacts {
  sign: Sign;
  manifestation: Manifestation;
}

export interface RetrievedPassage {
  chunk_id: string;
  source: Source;
  text: string;
  locator: string;
  score: number;
  chunk_index: number;
  char_start: number;
  char_end: number;
  embedding_model: string;
}

export interface ConceptCandidates {
  concept: string;
  passages: RetrievedPassage[];
}

export interface ConceptMatchScore {
  concept: string;
  score: number;
  exact_value: boolean;
}

export interface MergedCandidate {
  passage: RetrievedPassage;
  matches: ConceptMatchScore[];
  combined_score: number;
}

export interface ConceptPairCandidates {
  concepts: string[];
  candidates: MergedCandidate[];
}

export interface SignSummary {
  slug: string;
  canonical_name: string;
  sign_type: string;
  semiotic_system: string;
  tradition_slugs: string[];
}
