// Mirrors the SSE event payload shapes `stream_query`/`routes.py` emit
// (`core/models.py`'s Pydantic models, `.model_dump(mode="json")`) —
// denormalized: every passage carries its own `source`/`tradition` inline,
// no id-based lookup table (see specs/query-viewer-web-ui/plan.md's
// "Streaming design").

export interface Tradition {
  id: string;
  slug: string;
  name: string;
  domain: string;
  description: string;
}

export interface Source {
  id: string;
  title: string;
  author: string;
  publication_year: number | null;
  license: string;
  uri: string;
  content_hash: string;
  ingested_at: string | null;
}

export interface Attribute {
  id: string;
  key: string;
  value: string;
  value_type: string;
  position: number;
  retrievable: boolean;
}

export interface Citation {
  source: Source;
  locator: string;
}

export interface RelationshipFact {
  relationship_type: string;
  target_symbol: Symbol;
  according_to_tradition: Tradition;
  description: string;
  symmetric: boolean;
  confidence: string;
  target_semantic_facts: Attribute[];
  citation: Citation | null;
}

export interface Symbol {
  id: string;
  slug: string;
  canonical_name: string;
  symbol_type: string;
  notes: string;
  properties: Attribute[];
  relationships: RelationshipFact[];
}

export interface Interpretation {
  id: string;
  symbol_id: string;
  tradition: Tradition;
  display_name: string;
  summary: string;
  attributes: Attribute[];
  citations: Citation[];
  created_at: string;
}

export interface GraphFacts {
  symbol: Symbol;
  interpretation: Interpretation;
}

export interface RetrievedPassage {
  chunk_id: string;
  source: Source;
  tradition: Tradition;
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

export interface SymbolSummary {
  slug: string;
  canonical_name: string;
  symbol_type: string;
  tradition_slugs: string[];
}
